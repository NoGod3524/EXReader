/* SPDX-License-Identifier: MIT */
/* ISO 32000-1 8.7.4.5: axial (type 2) and radial (type 3) shadings. Each is baked
   into an RGBA bitmap that the caller paints with the current clip, alpha and
   blend, so clipping and transparency keep using the existing paths. */
#include "pdf_internal.h"
#include "pdf_function_internal.h"
#include <limits.h>

#define AXIAL_SAMPLES 512u
#define AXIAL_EXTEND_SPAN 1.0  /* one axis length of constant colour past each end */
#define RADIAL_SAMPLES 512u    /* square resolution of the radial bitmap */

static int number(exr_pdf_file *file,uint32_t id,double *out) {
  const exr_pdf_value *v=exr_pdf_value_at(file,id);
  if(!v || (v->kind!=EXR_PDF_INT && v->kind!=EXR_PDF_REAL)) return 0;
  *out=v->kind==EXR_PDF_INT ? (double)v->u.integer : v->u.number;
  return isfinite(*out);
}
static exr_status numbers(exr_pdf_file *file,uint32_t id,double *out,unsigned count,exr_error *e) {
  const exr_pdf_value *v=exr_pdf_value_at(file,id);uint32_t at;
  if(!v || v->kind!=EXR_PDF_ARRAY) return exr_fail(e,EXR_FORMAT,"PDF shading field must be a numeric array");
  at=v->first;
  for(unsigned i=0;i<count;i++) {
    uint32_t item,next;v=exr_pdf_value_at(file,at);
    if(!v) return exr_fail(e,EXR_FORMAT,"PDF shading array has too few values");
    next=v->next;
    if(exr_pdf_resolve(file,at,&item,e)!=EXR_OK) return e->code;
    if(!number(file,item,out+i)) return exr_fail(e,EXR_FORMAT,"Invalid PDF shading numeric value");
    at=next;
  }
  return at==EXR_PDF_NONE ? EXR_OK : exr_fail(e,EXR_FORMAT,"PDF shading array has too many values");
}
static void multiply(const double a[6],const double b[6],double out[6]) {
  out[0]=a[0]*b[0]+a[2]*b[1]; out[1]=a[1]*b[0]+a[3]*b[1];
  out[2]=a[0]*b[2]+a[2]*b[3]; out[3]=a[1]*b[2]+a[3]*b[3];
  out[4]=a[0]*b[4]+a[2]*b[5]+a[4]; out[5]=a[1]*b[4]+a[3]*b[5]+a[5];
}
/* Parameter t of the cone through the two circles; 0 when the point misses it. */
static int radial_parameter(double px,double py,const double coords[6],double *out) {
  const double x0=coords[0],y0=coords[1],r0=coords[2],x1=coords[3],y1=coords[4],r1=coords[5];
  const double dx=x1-x0,dy=y1-y0,dr=r1-r0;
  const double ox=px-x0,oy=py-y0;
  const double a=dx*dx+dy*dy-dr*dr;
  const double b=-2*(ox*dx+oy*dy+r0*dr);
  const double c=ox*ox+oy*oy-r0*r0;
  if(fabs(a)<1e-12) {
    if(fabs(b)<1e-12) return 0;
    *out=-c/b;
    return 1;
  }
  { double disc=b*b-4*a*c,lo,hi; int roots=0;
    if(disc<0) return 0;
    disc=sqrt(disc);
    lo=(-b-disc)/(2*a);hi=(-b+disc)/(2*a);
    roots=1;
    if(lo>hi) { double swap=lo;lo=hi;hi=swap; }
    if(lo>=0) *out=lo; else if(hi>=0) *out=hi; else return 0;
    return roots;
  }
}
static void store(exr_bitmap *bitmap,size_t index,const double rgb[3],unsigned char alpha) {
  unsigned char *p=bitmap->pixels+index*4;
  p[0]=(unsigned char)floor(fmax(0,fmin(1,rgb[0]))*255+.5);
  p[1]=(unsigned char)floor(fmax(0,fmin(1,rgb[1]))*255+.5);
  p[2]=(unsigned char)floor(fmax(0,fmin(1,rgb[2]))*255+.5);
  p[3]=alpha;
}
static exr_status sample(exr_pdf_function *function,exr_pdf_colorspace *space,unsigned intent,
                         double t,double rgb[3],exr_bitmap *inks,size_t index,size_t *work,exr_error *e) {
  double out[EXR_PDF_MAX_COLORANTS]={0};
  if(!exr_vector_work(work,exr_pdf_function_cost(function)+exr_pdf_colorspace_cost(space)))
    return exr_fail(e,EXR_LIMIT,"PDF shading samples exceed work budget");
  exr_status status=exr_pdf_function_eval(function,t,out,e);
  if(status!=EXR_OK) return status;
  if(inks->pixels) { unsigned k;for(k=0;k<4;k++) inks->pixels[index*4+k]=(unsigned char)floor(fmax(0,fmin(1,out[k]))*255+.5); }
  return exr_pdf_colorspace_rgb_intent(space,out,rgb,intent,e);
}

exr_status exr_pdf_shading_draw(exr_pdf_file *file,exr_pdf_file *resource_file,uint32_t resources,
                                uint32_t value,const double ctm[6],const exr_pdf_paint_state *paint,size_t *work,
                                exr_pdf_shading_fn emit,void *context,unsigned native_cmyk,
                                const exr_control *control,exr_error *e) {
  uint32_t id,coords_id,function_id,cs_id;const exr_pdf_value *v;double coords[6]={0},domain[2]={0,1},t;
  size_t local_work=0;int stream;
  unsigned intent=paint->intent;
  int extend0=0,extend1=0,type=0;unsigned i,components=1,ncoords;
  exr_pdf_colorspace *space=NULL;exr_pdf_function *function=NULL;
  exr_bitmap bitmap={0},inks={0};double matrix[6],local[6];exr_status status=EXR_OK;
  if(!emit) return exr_fail(e,EXR_UNSUPPORTED,"Drawing consumer does not support PDF shadings");
  if(!work) work=&local_work;
  if(exr_pdf_resolve(file,value,&value,e)!=EXR_OK) return e->code;
  v=exr_pdf_value_at(file,value);
  /* Mesh shadings are streams; axial and radial shadings are plain dictionaries. */
  if(!v || (v->kind!=EXR_PDF_DICT && v->kind!=EXR_PDF_STREAM)) return exr_fail(e,EXR_FORMAT,"PDF shading is not a dictionary");
  stream=v->kind==EXR_PDF_STREAM;
  if(exr_pdf_resolve(file,exr_pdf_get(file,value,"ShadingType"),&id,e)!=EXR_OK) return e->code;
  { double n;
    if(!number(file,id,&n) || n<1 || n>INT_MAX || n!=floor(n)) return exr_fail(e,EXR_FORMAT,"Invalid PDF shading type");
    if(n>7) return exr_fail(e,EXR_UNSUPPORTED,"Unsupported PDF shading type");
    type=(int)n;
  }
  if(type>=4 && type<=7) {
    status=exr_pdf_shading_mesh(file,resource_file,resources,value,type,ctm,paint,work,emit,context,native_cmyk,control,e);
    return status;
  }
  if(stream) return exr_fail(e,EXR_FORMAT,"PDF shading is not a dictionary");
  if(type!=2 && type!=3) return exr_fail(e,EXR_UNSUPPORTED,"Only axial, radial and mesh PDF shadings are implemented");
  ncoords=type==2 ? 4u : 6u;
  if(exr_pdf_resolve(file,exr_pdf_get(file,value,"Coords"),&coords_id,e)!=EXR_OK) return e->code;
  status=numbers(file,coords_id,coords,ncoords,e);if(status!=EXR_OK) return status;
  if(exr_pdf_resolve(file,exr_pdf_get(file,value,"Domain"),&id,e)!=EXR_OK) return e->code;
  v=exr_pdf_value_at(file,id);
  if(v && v->kind!=EXR_PDF_NULL) {
    status=numbers(file,id,domain,2,e);if(status!=EXR_OK) return status;
    if(domain[0]>domain[1]) return exr_fail(e,EXR_FORMAT,"Invalid PDF shading domain order");
  }
  if(type==3 && (coords[2]<0 || coords[5]<0)) return exr_fail(e,EXR_FORMAT,"Invalid PDF radial shading radii");
  if(exr_pdf_resolve(file,exr_pdf_get(file,value,"Extend"),&id,e)!=EXR_OK) return e->code;
  v=exr_pdf_value_at(file,id);
  if(v && v->kind!=EXR_PDF_NULL) {
    uint32_t at=v->first;
    if(v->kind!=EXR_PDF_ARRAY) return exr_fail(e,EXR_FORMAT,"PDF shading Extend must contain two booleans");
    for(i=0;i<2;i++) {
      uint32_t item,next;v=exr_pdf_value_at(file,at);
      if(!v) return exr_fail(e,EXR_FORMAT,"PDF shading Extend has too few values");
      next=v->next;
      if(exr_pdf_resolve(file,at,&item,e)!=EXR_OK) return e->code;
      v=exr_pdf_value_at(file,item);
      if(!v || v->kind!=EXR_PDF_BOOL) return exr_fail(e,EXR_FORMAT,"PDF shading Extend values must be boolean");
      if(!i) extend0=v->u.integer!=0;else extend1=v->u.integer!=0;
      at=next;
    }
    if(at!=EXR_PDF_NONE) return exr_fail(e,EXR_FORMAT,"PDF shading Extend has too many values");
  }
  if(exr_pdf_resolve(file,exr_pdf_get(file,value,"ColorSpace"),&cs_id,e)!=EXR_OK) return e->code;
  status=exr_pdf_colorspace_open(file,cs_id,resource_file,resources,control,&space,e);
  if(status!=EXR_OK) return status;
  components=exr_pdf_colorspace_components(space);
  if(exr_pdf_resolve(file,exr_pdf_get(file,value,"Function"),&function_id,e)!=EXR_OK) { exr_pdf_colorspace_free(space); return e->code; }
  status=exr_pdf_function_open(file,function_id,components,control,&function,e);
  if(status!=EXR_OK) { exr_pdf_colorspace_free(space); return status; }

  if(type==2) {
    double t0=extend0 ? -AXIAL_EXTEND_SPAN : 0.0, t1=extend1 ? 1.0+AXIAL_EXTEND_SPAN : 1.0;
    bitmap.width=AXIAL_SAMPLES;bitmap.height=1;bitmap.channels=4;
    bitmap.stride=AXIAL_SAMPLES*4;
    bitmap.pixels=calloc((size_t)bitmap.stride,1);
    if(!bitmap.pixels) { exr_pdf_function_free(function);exr_pdf_colorspace_free(space);return exr_fail(e,EXR_MEMORY,"PDF shading bitmap allocation failed"); }
    if(native_cmyk && exr_pdf_colorspace_device(space)==EXR_PDF_DEVICE_CMYK) {
      inks=bitmap;inks.pixels=calloc((size_t)bitmap.stride*bitmap.height,1);
      if(!inks.pixels) { status=exr_fail(e,EXR_MEMORY,"PDF shading ink allocation failed");goto done; }
    }
    for(i=0;i<AXIAL_SAMPLES && status==EXR_OK;i++) {
      if(exr_control_cancel(control,e)!=EXR_OK) { status=EXR_CANCELLED;break; }
      double rgb[3]={0},u=t0+((double)i+0.5)/AXIAL_SAMPLES*(t1-t0);
      t=u<0 ? 0 : u>1 ? 1 : u;
      status=sample(function,space,intent,domain[0]*(1-t)+domain[1]*t,rgb,&inks,i,work,e);
      store(&bitmap,i,rgb,((u<0 && !extend0) || (u>1 && !extend1)) ? 0 : 255);
    }
    if(status==EXR_OK) {
      const double ax=coords[2]-coords[0],ay=coords[3]-coords[1],len=hypot(ax,ay);
      double px,py,h;
      if(len<=0) status=exr_fail(e,EXR_FORMAT,"Degenerate PDF axial shading");
      if(status==EXR_OK) {
        px=-ay/len;py=ax/len;h=1e4;
        local[0]=ax*(t1-t0);local[1]=ay*(t1-t0);
        local[2]=px*2*h;local[3]=py*2*h;
        local[4]=coords[0]+t0*ax-h*px;local[5]=coords[1]+t0*ay-h*py;
        multiply(ctm,local,matrix);
        status=emit(context,&bitmap,inks.pixels ? &inks : NULL,matrix,paint,e);
      }
    }
  } else {
    /* The union of both circles bounds every painted point. */
    double left=fmin(coords[0]-coords[2],coords[3]-coords[5]);
    double top=fmin(coords[1]-coords[2],coords[4]-coords[5]);
    double right=fmax(coords[0]+coords[2],coords[3]+coords[5]);
    double bottom=fmax(coords[1]+coords[2],coords[4]+coords[5]);
    if(!(right>left) || !(bottom>top)) { status=exr_fail(e,EXR_FORMAT,"Degenerate PDF radial shading");goto done; }
    /* An extended radial shading has no outer boundary: its last colour covers
       the whole clip. Grow the emitted quad by one gradient span per side so
       clipping regions larger than the circles still receive that colour. */
    if(extend0 || extend1) {
      double padx=right-left,pady=bottom-top;
      left-=padx;right+=padx;top-=pady;bottom+=pady;
    }
    bitmap.width=RADIAL_SAMPLES;bitmap.height=RADIAL_SAMPLES;bitmap.channels=4;
    bitmap.stride=RADIAL_SAMPLES*4;
    bitmap.pixels=calloc((size_t)bitmap.stride*RADIAL_SAMPLES,1);
    if(!bitmap.pixels) { exr_pdf_function_free(function);exr_pdf_colorspace_free(space);return exr_fail(e,EXR_MEMORY,"PDF shading bitmap allocation failed"); }
    if(native_cmyk && exr_pdf_colorspace_device(space)==EXR_PDF_DEVICE_CMYK) {
      inks=bitmap;inks.pixels=calloc((size_t)bitmap.stride*bitmap.height,1);
      if(!inks.pixels) { status=exr_fail(e,EXR_MEMORY,"PDF shading ink allocation failed");goto done; }
    }
    for(i=0;i<RADIAL_SAMPLES*RADIAL_SAMPLES && status==EXR_OK;i++) {
      unsigned row=i/RADIAL_SAMPLES,col=i%RADIAL_SAMPLES;
      if(!col && exr_control_cancel(control,e)!=EXR_OK) { status=EXR_CANCELLED;break; }
      if(!col && !exr_vector_work(work,RADIAL_SAMPLES)) { status=exr_fail(e,EXR_LIMIT,"PDF radial shading scan exceeds work budget");break; }
      double x=left+((double)col+0.5)/RADIAL_SAMPLES*(right-left);
      double y=top+((double)row+0.5)/RADIAL_SAMPLES*(bottom-top);
      double rgb[3]={0};
      if(!radial_parameter(x,y,coords,&t)) { store(&bitmap,i,rgb,0); continue; }
      if(t<0) { if(!extend0) { store(&bitmap,i,rgb,0); continue; } t=0; }
      if(t>1) { if(!extend1) { store(&bitmap,i,rgb,0); continue; } t=1; }
      status=sample(function,space,intent,domain[0]*(1-t)+domain[1]*t,rgb,&inks,i,work,e);
      store(&bitmap,i,rgb,255);
    }
    if(status==EXR_OK) {
      local[0]=right-left;local[1]=0;local[2]=0;local[3]=bottom-top;
      local[4]=left;local[5]=top;
      multiply(ctm,local,matrix);
      status=emit(context,&bitmap,inks.pixels ? &inks : NULL,matrix,paint,e);
    }
  }
done:
  free(inks.pixels);free(bitmap.pixels);exr_pdf_function_free(function);exr_pdf_colorspace_free(space);
  return status;
}
