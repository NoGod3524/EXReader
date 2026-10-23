/* SPDX-License-Identifier: MIT */
/* ISO 32000-1 11.6.5.2 graphics-state soft masks: render the G form into a
   page-sized 8-bit mask. Alpha uses the group alpha; Luminosity composites the
   group over BC and takes the 0.3/0.59/0.11 luminance. TR uses the bounded PDF function evaluator. */
#include "pdf_raster_internal.h"
#include "icc_internal.h"
#include "pdf_function_internal.h"
#include <math.h>
#include <string.h>
#include <stdio.h>

static exr_status fail(exr_error *e, exr_status code, const char *message) { return exr_fail(e, code, message); }
static int number(exr_pdf_file *file, uint32_t id, double *out) {
  const exr_pdf_value *v = exr_pdf_value_at(file, id);
  if (!v || (v->kind != EXR_PDF_INT && v->kind != EXR_PDF_REAL)) return 0;
  *out = v->kind == EXR_PDF_INT ? (double)v->u.integer : v->u.number;
  return isfinite(*out) && fabs(*out) <= 1e7;
}
static int numbers(exr_pdf_file *file, uint32_t array, double *out, size_t count) {
  const exr_pdf_value *v = exr_pdf_value_at(file, array);
  uint32_t at; size_t i;
  if (!v || v->kind != EXR_PDF_ARRAY) return 0;
  at = v->first;
  for (i = 0; i < count; i++) {
    uint32_t value;
    if (at == EXR_PDF_NONE || exr_pdf_resolve(file, at, &value, NULL) != EXR_OK || !number(file, value, &out[i])) return 0;
    at = exr_pdf_value_at(file, at)->next;
  }
  return at == EXR_PDF_NONE;
}
static void multiply(const double a[6], const double b[6], double out[6]) {
  out[0] = a[0] * b[0] + a[2] * b[1]; out[1] = a[1] * b[0] + a[3] * b[1];
  out[2] = a[0] * b[2] + a[2] * b[3]; out[3] = a[1] * b[2] + a[3] * b[3];
  out[4] = a[0] * b[4] + a[2] * b[5] + a[4]; out[5] = a[1] * b[4] + a[3] * b[5] + a[5];
}

static exr_status load_transfer(exr_pdf_file *file,uint32_t mask,const exr_control *control,
                                exr_pdf_function **out,exr_error *e) {
  uint32_t id;const exr_pdf_value *v;size_t size;const unsigned char *name;
  *out=NULL;
  if(exr_pdf_resolve(file,exr_pdf_get(file,mask,"TR"),&id,e)!=EXR_OK) return e->code;
  v=exr_pdf_value_at(file,id);
  if(!v || v->kind==EXR_PDF_NULL) return EXR_OK;
  if(v->kind==EXR_PDF_NAME) {
    name=exr_pdf_bytes(file,id,&size);
    if(size==8 && !memcmp(name,"Identity",8)) return EXR_OK;
    return exr_fail(e,EXR_FORMAT,"Invalid PDF soft mask transfer name");
  }
  return exr_pdf_function_open(file,id,1,control,out,e);
}
static exr_status build_mask(exr_pdf_file *file, uint32_t mask, const double set_matrix[6],
                                   unsigned width, unsigned height, unsigned char **out,
                                   size_t *work,size_t *active_mask_bytes, const exr_control *control, exr_error *e) {
  uint32_t form, id, resources = EXR_PDF_NONE; const unsigned char *data = NULL; size_t size = 0, i,local_work=0;
  double matrix[6], local[6], box[4], bc[4] = {0, 0, 0, 0}; unsigned char *pixels = NULL, *result = NULL;
  const exr_pdf_value *v; int kind = 0, count = 0; exr_bitmap bitmap = {0}; exr_pdf_raster_config config = {0}; exr_status status;
  exr_pdf_function *function=NULL;size_t sample_cost;int group;
  *out = NULL;
  if(!work) work=&local_work;
  status = exr_pdf_soft_mask_kind(file, mask, &kind, e); if (status != EXR_OK) return status;
  if (exr_pdf_resolve(file, mask, &mask, e) != EXR_OK) return e->code;
  if (exr_pdf_resolve(file, exr_pdf_get(file, mask, "G"), &form, e) != EXR_OK) return e->code;
  if (exr_pdf_stream_data(file, form, &data, &size, e) != EXR_OK) return e->code;
  if (exr_pdf_resolve(file, exr_pdf_get(file, form, "BBox"), &id, e) != EXR_OK) return e->code;
  if (!numbers(file, id, box, 4) || box[0] > box[2] || box[1] > box[3]) return fail(e, EXR_FORMAT, "Invalid PDF soft mask bounding box");
  local[0] = 1; local[1] = 0; local[2] = 0; local[3] = 1; local[4] = 0; local[5] = 0;
  if (exr_pdf_resolve(file, exr_pdf_get(file, form, "Matrix"), &id, e) != EXR_OK) return e->code;
  if (id != EXR_PDF_NONE) { v = exr_pdf_value_at(file, id); if (v->kind != EXR_PDF_NULL && !numbers(file, id, local, 6)) return fail(e, EXR_FORMAT, "Invalid PDF soft mask matrix"); }
  multiply(set_matrix, local, matrix);
  if (exr_pdf_resolve(file, exr_pdf_get(file, form, "Resources"), &resources, e) != EXR_OK) return e->code;
  if (resources == EXR_PDF_NONE || exr_pdf_value_at(file, resources)->kind == EXR_PDF_NULL) resources = EXR_PDF_NONE;
  if(exr_pdf_resolve(file,exr_pdf_get(file,form,"Group"),&id,e)!=EXR_OK) return e->code;
  status=exr_pdf_group_rgb(file,id,EXR_PDF_GROUP_MASK_CONTEXT,&group,e);if(status!=EXR_OK) return status;
  config.group_present=1;
  config.group_flags=(group&EXR_PDF_GROUP_ISOLATED ? EXR_GROUP_ISOLATED : 0)|
    (group&EXR_PDF_GROUP_KNOCKOUT ? EXR_GROUP_KNOCKOUT : 0)|
    (group&EXR_PDF_GROUP_RGB ? EXR_GROUP_RGB : 0)|(group&EXR_PDF_GROUP_GRAY ? EXR_GROUP_GRAY : 0)|
    (group&EXR_PDF_GROUP_CMYK ? EXR_GROUP_CMYK : 0);
  if (kind) {
    if (exr_pdf_resolve(file, exr_pdf_get(file, mask, "BC"), &id, e) != EXR_OK) return e->code;
    if (id != EXR_PDF_NONE && exr_pdf_value_at(file, id)->kind != EXR_PDF_NULL) {
      double tmp[4];
      v = exr_pdf_value_at(file, id);
      { uint32_t at = v->first; while (at != EXR_PDF_NONE && count < 4) { uint32_t value; if (exr_pdf_resolve(file, at, &value, e) != EXR_OK || !number(file, value, &tmp[count])) return fail(e, EXR_FORMAT, "Invalid PDF soft mask backdrop"); count++; at = exr_pdf_value_at(file, at)->next; } }
      if (count == 1) { bc[0] = bc[1] = bc[2] = tmp[0]; }
      else if (count == 3) { bc[0] = tmp[0]; bc[1] = tmp[1]; bc[2] = tmp[2]; }
      else if (count == 4) { exr_icc *profile=NULL;status=exr_icc_default_cmyk(control,&profile,e);if(status!=EXR_OK) return status;exr_device_cmyk_rgb(profile,tmp,bc,1);status=exr_icc_deferred_status(profile,e);exr_icc_free(profile);if(status!=EXR_OK) return status; }
      else return fail(e, EXR_FORMAT, "Invalid PDF soft mask backdrop length");
    }
  }
  config.width = width; config.height = height; config.channels = 4; config.background = 0;
  if(kind) {
    config.background=255;
    for(unsigned k=0;k<3;k++) config.background|=(uint32_t)fmax(0,fmin(255,floor(bc[k]*255+.5)))<<(24-8*k);
  }
  config.work=work;config.active_mask_bytes=active_mask_bytes;
  config.initial_clip=box;config.initial_clip_transform=matrix;config.mask_budget=0;
  status = exr_pdf_raster_content(file, resources, data, size, matrix, &config, control, &bitmap, e);
  if (status != EXR_OK) return status;
  status=load_transfer(file,mask,control,&function,e);
  if(status!=EXR_OK) { free(bitmap.pixels);return status; }
  sample_cost=1+(kind ? 8 : 0)+exr_pdf_function_cost(function);
  result = malloc((size_t)width * height);
  if (!result) { exr_pdf_function_free(function);free(bitmap.pixels); return fail(e, EXR_MEMORY, "PDF soft mask allocation failed"); }
  pixels = bitmap.pixels;
  for(size_t y=0;y<height;y++) {
    status=exr_control_cancel(control,e);
    if(status==EXR_OK && !exr_vector_work(work,(size_t)width*sample_cost))
      status=exr_fail(e,EXR_LIMIT,"PDF soft mask samples exceed work budget");
    if(status!=EXR_OK) goto done;
    for(size_t x=0;x<width;x++) {
      double a,value,output[4];i=y*width+x;a=pixels[i*4+3]/255.;
      value=a;
      if(kind) {
        double v0=pixels[i*4]/255.*a+bc[0]*(1-a);
        double v1=pixels[i*4+1]/255.*a+bc[1]*(1-a);
        double v2=pixels[i*4+2]/255.*a+bc[2]*(1-a);
        value=.3*v0+.59*v1+.11*v2;
      }
      if(function) {
        status=exr_pdf_function_eval(function,value,output,e);
        if(status!=EXR_OK) goto done;
        value=output[0];
      }
      result[i]=(unsigned char)fmax(0,fmin(255,floor(value*255+.5)));
    }
  }
  status=EXR_OK;
done:
  exr_pdf_function_free(function);
  if(status!=EXR_OK) { free(result);free(bitmap.pixels);return status; }
  free(bitmap.pixels);
  *out = result;
  return EXR_OK;
}

/* Bound recursive mask G/SMask graphs independently on each calling thread. */
#ifdef _MSC_VER
static __declspec(thread) unsigned mask_depth;
#else
static _Thread_local unsigned mask_depth;
#endif
exr_status exr_pdf_soft_mask_build(exr_pdf_file *file,uint32_t mask,const double matrix[6],
  unsigned width,unsigned height,unsigned char **out,size_t *work,size_t *active_mask_bytes,const exr_control *control,exr_error *e) {
  exr_status status;*out=NULL;
  if(mask_depth==16) return exr_fail(e,EXR_LIMIT,"PDF soft mask nesting exceeds 16");
  mask_depth++;status=build_mask(file,mask,matrix,width,height,out,work,active_mask_bytes,control,e);mask_depth--;
  return status;
}
