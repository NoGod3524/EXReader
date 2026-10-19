/* SPDX-License-Identifier: GPL-3.0-only */
/* ISO 32000-1 8.7.4.5.3: axial shading (type 2). The gradient is baked into a
   one-row RGBA bitmap whose u axis follows the shading axis; the caller paints it
   with the current clip, alpha and blend, so clipping and transparency keep using
   the existing paths. */
#include "pdf_internal.h"
#include "pdf_function_internal.h"

#define SHADING_SAMPLES 512u
#define SHADING_EXTEND_SPAN 1.0 /* one axis length of constant colour past each end */

static int number(exr_pdf_file *file,uint32_t id,double *out) {
  const exr_pdf_value *v=exr_pdf_value_at(file,id);
  if(!v || (v->kind!=EXR_PDF_INT && v->kind!=EXR_PDF_REAL)) return 0;
  *out=v->kind==EXR_PDF_INT ? (double)v->u.integer : v->u.number;
  return isfinite(*out);
}
static void multiply(const double a[6],const double b[6],double out[6]) {
  out[0]=a[0]*b[0]+a[2]*b[1]; out[1]=a[1]*b[0]+a[3]*b[1];
  out[2]=a[0]*b[2]+a[2]*b[3]; out[3]=a[1]*b[2]+a[3]*b[3];
  out[4]=a[0]*b[4]+a[2]*b[5]+a[4]; out[5]=a[1]*b[4]+a[3]*b[5]+a[5];
}

exr_status exr_pdf_shading_draw(exr_pdf_file *file,exr_pdf_file *resource_file,uint32_t resources,
                                uint32_t value,const double ctm[6],unsigned intent,
                                exr_pdf_shading_fn emit,void *context,
                                const exr_control *control,exr_error *e) {
  uint32_t id,coords_id,function_id,cs_id;const exr_pdf_value *v;double coords[4],t;
  int extend0=0,extend1=0,type=0;unsigned i,components=1;
  exr_pdf_colorspace *space=NULL;exr_pdf_function *function=NULL;
  exr_bitmap bitmap={0};double matrix[6],local[6];exr_status status=EXR_OK;
  if(!emit) return exr_fail(e,EXR_UNSUPPORTED,"Drawing consumer does not support PDF shadings");
  if(exr_pdf_resolve(file,value,&value,e)!=EXR_OK) return e->code;
  v=exr_pdf_value_at(file,value);
  if(!v || v->kind!=EXR_PDF_DICT) return exr_fail(e,EXR_FORMAT,"PDF shading is not a dictionary");
  if(exr_pdf_resolve(file,exr_pdf_get(file,value,"ShadingType"),&id,e)!=EXR_OK) return e->code;
  { double n; if(!number(file,id,&n)) return exr_fail(e,EXR_FORMAT,"Invalid PDF shading type"); type=(int)n; }
  if(type!=2) return exr_fail(e,EXR_UNSUPPORTED,"Only axial PDF shadings are implemented");
  if(exr_pdf_resolve(file,exr_pdf_get(file,value,"Coords"),&coords_id,e)!=EXR_OK) return e->code;
  v=exr_pdf_value_at(file,coords_id);
  if(!v || v->kind!=EXR_PDF_ARRAY) return exr_fail(e,EXR_FORMAT,"Invalid PDF shading coordinates");
  { uint32_t at=v->first;
    for(i=0;i<4;i++) {
      uint32_t item;
      if(at==EXR_PDF_NONE || exr_pdf_resolve(file,at,&item,e)!=EXR_OK) return exr_fail(e,EXR_FORMAT,"Invalid PDF shading coordinates");
      if(!number(file,item,&coords[i])) return exr_fail(e,EXR_FORMAT,"Invalid PDF shading coordinates");
      at=exr_pdf_value_at(file,at)->next;
    }
  }
  if(exr_pdf_get(file,value,"Extend")!=EXR_PDF_NONE) {
    if(exr_pdf_resolve(file,exr_pdf_get(file,value,"Extend"),&id,e)!=EXR_OK) return e->code;
    v=exr_pdf_value_at(file,id);
    if(v && v->kind==EXR_PDF_ARRAY) {
      uint32_t at=v->first;
      for(i=0;i<2 && at!=EXR_PDF_NONE;i++) {
        uint32_t item;const exr_pdf_value *flag;
        if(exr_pdf_resolve(file,at,&item,e)!=EXR_OK) break;
        flag=exr_pdf_value_at(file,item);
        if(flag && flag->kind==EXR_PDF_BOOL) { if(i==0) extend0=flag->u.integer!=0; else extend1=flag->u.integer!=0; }
        at=exr_pdf_value_at(file,at)->next;
      }
    }
  }
  if(exr_pdf_resolve(file,exr_pdf_get(file,value,"ColorSpace"),&cs_id,e)!=EXR_OK) return e->code;
  status=exr_pdf_colorspace_open(file,cs_id,resource_file,resources,control,&space,e);
  if(status!=EXR_OK) return status;
  components=exr_pdf_colorspace_components(space);
  if(exr_pdf_resolve(file,exr_pdf_get(file,value,"Function"),&function_id,e)!=EXR_OK) { exr_pdf_colorspace_free(space); return e->code; }
  status=exr_pdf_function_open(file,function_id,components,control,&function,e);
  if(status!=EXR_OK) { exr_pdf_colorspace_free(space); return status; }

  bitmap.width=SHADING_SAMPLES;bitmap.height=1;bitmap.channels=4;bitmap.stride=SHADING_SAMPLES*4;
  bitmap.pixels=calloc((size_t)bitmap.stride,1);
  if(!bitmap.pixels) { exr_pdf_function_free(function);exr_pdf_colorspace_free(space);return exr_fail(e,EXR_MEMORY,"PDF shading bitmap allocation failed"); }
  {
    double t0=extend0 ? -SHADING_EXTEND_SPAN : 0.0, t1=extend1 ? 1.0+SHADING_EXTEND_SPAN : 1.0;
    for(i=0;i<SHADING_SAMPLES;i++) {
      double out[4]={0},rgb[3]={0},u;
      unsigned char *p=bitmap.pixels+i*4;
      u=t0+((double)i+0.5)/SHADING_SAMPLES*(t1-t0);
      t=u<0 ? 0 : u>1 ? 1 : u;
      status=exr_pdf_function_eval(function,t,out,e);
      if(status!=EXR_OK) break;
      status=exr_pdf_colorspace_rgb_intent(space,out,rgb,intent,e);
      if(status!=EXR_OK) break;
      p[0]=(unsigned char)floor(fmax(0,fmin(1,rgb[0]))*255+.5);
      p[1]=(unsigned char)floor(fmax(0,fmin(1,rgb[1]))*255+.5);
      p[2]=(unsigned char)floor(fmax(0,fmin(1,rgb[2]))*255+.5);
      p[3]=(u<0 && !extend0) || (u>1 && !extend1) ? 0 : 255;
    }
    if(status==EXR_OK) {
      /* Map (u,v) in [0,1]^2 onto the axis band; the perpendicular span only has
         to cover the clip, so it is deliberately generous. */
      const double ax=coords[2]-coords[0],ay=coords[3]-coords[1],len=hypot(ax,ay);
      double px,py,h;
      if(len<=0) status=exr_fail(e,EXR_FORMAT,"Degenerate PDF axial shading");
      if(status==EXR_OK) {
        px=-ay/len;py=ax/len;h=64;
        local[0]=ax*(t1-t0);local[1]=ay*(t1-t0);
        local[2]=px*2*h;local[3]=py*2*h;
        local[4]=coords[0]+t0*ax-h*px;local[5]=coords[1]+t0*ay-h*py;
        multiply(ctm,local,matrix);
        status=emit(context,&bitmap,matrix,NULL,e);
      }
    }
  }
  free(bitmap.pixels);exr_pdf_function_free(function);exr_pdf_colorspace_free(space);
  return status;
}
