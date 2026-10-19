/* SPDX-License-Identifier: MIT */
/* ISO 32000-1 11.6.5.2 graphics-state soft masks: render the G form into a
   page-sized 8-bit mask. Alpha uses the group alpha; Luminosity composites the
   group over BC and takes the 0.3/0.59/0.11 luminance. TR supports Identity. */
#include "pdf_raster_internal.h"
#include "icc_internal.h"
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

/* Exponential transfer function (ISO 32000-1 7.10.2.2): C0 + x^N (C1 - C0). */
typedef struct { int present; double c0, c1, n; } mask_transfer;
static double transfer(double x,const mask_transfer *state) {
  if (!state->present) return x;
  return state->c0 + pow(fmax(0, fmin(1, x)), state->n) * (state->c1 - state->c0);
}
static exr_status load_transfer(exr_pdf_file *file, uint32_t mask, mask_transfer *state,exr_error *e) {
  uint32_t id, at; const exr_pdf_value *v, *array; size_t i;
  state->present = 0; state->c0 = 0; state->c1 = 1; state->n = 1;
  if (exr_pdf_resolve(file, exr_pdf_get(file, mask, "TR"), &id, e) != EXR_OK) return e->code;
  if (id == EXR_PDF_NONE || exr_pdf_value_at(file, id)->kind == EXR_PDF_NULL) return EXR_OK;
  if (exr_pdf_value_at(file, id)->kind != EXR_PDF_DICT) return EXR_OK;  /* /Identity */
  state->present = 1;
  for (i = 0; i < 2; i++) {
    const char *key = i ? "C1" : "C0";
    double *target = i ? &state->c1 : &state->c0;
    if (exr_pdf_resolve(file, exr_pdf_get(file, id, key), &at, e) != EXR_OK) return e->code;
    v = exr_pdf_value_at(file, at);
    if (!v || v->kind == EXR_PDF_NULL) continue;
    if (v->kind != EXR_PDF_ARRAY) return fail(e, EXR_FORMAT, "Invalid PDF soft mask transfer function");
    array = v;
    { uint32_t first = array->first; if (first == EXR_PDF_NONE) continue; if (exr_pdf_resolve(file, first, &at, e) != EXR_OK || !number(file, at, target)) return fail(e, EXR_FORMAT, "Invalid PDF soft mask transfer function"); }
  }
  if (exr_pdf_resolve(file, exr_pdf_get(file, id, "N"), &at, e) != EXR_OK) return e->code;
  v = exr_pdf_value_at(file, at);
  if (v && v->kind != EXR_PDF_NULL && !number(file, at, &state->n)) return fail(e, EXR_FORMAT, "Invalid PDF soft mask transfer function");
  if (state->n <= 0) return fail(e, EXR_FORMAT, "Invalid PDF soft mask transfer exponent");
  return EXR_OK;
}
static exr_status build_mask(exr_pdf_file *file, uint32_t mask, const double set_matrix[6],
                                   unsigned width, unsigned height, unsigned char **out,
                                   size_t *work, const exr_control *control, exr_error *e) {
  uint32_t form, id, resources = EXR_PDF_NONE; const unsigned char *data = NULL; size_t size = 0, i,local_work=0;
  double matrix[6], local[6], box[4], bc[4] = {0, 0, 0, 0}, clip[4]; unsigned char *pixels = NULL, *result = NULL;
  const exr_pdf_value *v; int kind = 0, count = 0; exr_bitmap bitmap = {0}; exr_pdf_raster_config config = {0}; exr_status status;
  mask_transfer state;
  *out = NULL;
  if(!work) work=&local_work;
  status = exr_pdf_soft_mask_kind(file, mask, &kind, e); if (status != EXR_OK) return status;
  status = load_transfer(file, mask, &state,e); if (status != EXR_OK) return status;
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
  /* Device-space clip from the transformed BBox corners. */
  {
    double xs[4], ys[4]; int corner;
    for (corner = 0; corner < 4; corner++) {
      double x = box[(corner & 1) ? 2 : 0], y = box[(corner & 2) ? 3 : 1];
      xs[corner] = matrix[0] * x + matrix[2] * y + matrix[4];
      ys[corner] = matrix[1] * x + matrix[3] * y + matrix[5];
    }
    clip[0] = fmax(0, fmin(fmin(xs[0], xs[1]), fmin(xs[2], xs[3])));
    clip[1] = fmax(0, fmin(fmin(ys[0], ys[1]), fmin(ys[2], ys[3])));
    clip[2] = fmin((double)width, fmax(fmax(xs[0], xs[1]), fmax(xs[2], xs[3])));
    clip[3] = fmin((double)height, fmax(fmax(ys[0], ys[1]), fmax(ys[2], ys[3])));
    if (clip[2] <= clip[0] || clip[3] <= clip[1]) return fail(e, EXR_FORMAT, "PDF soft mask is outside the device area");
  }
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
  config.work=work;
  config.initial_clip = clip; config.mask_budget = 0;
  status = exr_pdf_raster_content(file, resources, data, size, matrix, &config, control, &bitmap, e);
  if (status != EXR_OK) return status;
  result = malloc((size_t)width * height);
  if (!result) { free(bitmap.pixels); return fail(e, EXR_MEMORY, "PDF soft mask allocation failed"); }
  pixels = bitmap.pixels;
  for(size_t y=0;y<height;y++) {
      status=exr_control_cancel(control,e);
      if(status==EXR_OK && !exr_vector_work(work,(size_t)width*(1+(kind ? 8 : 0)+(state.present ? 16 : 0))))
        status=exr_fail(e,EXR_LIMIT,"PDF soft mask samples exceed work budget");
      if(status!=EXR_OK) { free(result);free(bitmap.pixels);return status; }
    for(size_t x=0;x<width;x++) {
    i=y*width+x;
    double a = pixels[i * 4 + 3] / 255.;
    if (kind) {
      double v0 = pixels[i * 4] / 255. * a + bc[0] * (1 - a);
      double v1 = pixels[i * 4 + 1] / 255. * a + bc[1] * (1 - a);
      double v2 = pixels[i * 4 + 2] / 255. * a + bc[2] * (1 - a);
      double lum = .3 * v0 + .59 * v1 + .11 * v2;
      result[i] = (unsigned char)fmax(0, fmin(255, floor(transfer(lum,&state) * 255 + .5)));
    } else { double a2 = transfer(a,&state); result[i] = (unsigned char)fmax(0, fmin(255, floor(a2 * 255 + .5))); }
    }
  }
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
  unsigned width,unsigned height,unsigned char **out,size_t *work,const exr_control *control,exr_error *e) {
  exr_status status;*out=NULL;
  if(mask_depth==16) return exr_fail(e,EXR_LIMIT,"PDF soft mask nesting exceeds 16");
  mask_depth++;status=build_mask(file,mask,matrix,width,height,out,work,control,e);mask_depth--;
  return status;
}
