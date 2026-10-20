/* SPDX-License-Identifier: MIT */
/* ISO 32000-1 8.7.4.5. Axial/radial sources sample the actual device clip.
   The bitmap path remains available for legacy drawing consumers. */
#include "pdf_internal.h"
#include "pdf_function_internal.h"
#include "icc_internal.h"
#include <limits.h>
#include <float.h>

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
static int radial_parameter(double px,double py,const double coords[6],int extend0,int extend1,double *out) {
  double scale=fmax(fabs(px),fabs(py)),c[6],roots[2],a,b,d,dx,dy,dr,ox,oy,best=0;unsigned i,n=0;int found=0;
  /* Normalize before subtracting or squaring, including large coordinates that
     a small CTM maps into an ordinary device viewport. */
  for(i=0;i<6;i++) scale=fmax(scale,fabs(coords[i]));
  if(!scale) return 0;
  for(i=0;i<6;i++) c[i]=coords[i]/scale;
  dx=c[3]-c[0];dy=c[4]-c[1];dr=c[5]-c[2];ox=px/scale-c[0];oy=py/scale-c[1];
  a=dx*dx+dy*dy-dr*dr;b=-2*(ox*dx+oy*dy+c[2]*dr);d=ox*ox+oy*oy-c[2]*c[2];
  if(!a) { if(b) roots[n++]=-d/b; }
  else {
    double product=4*a*d,disc=b*b-product;
    if(disc<0 && disc>=-8*DBL_EPSILON*(b*b+fabs(product))) disc=0;
    if(disc<0) return 0;
    if(!disc) roots[n++]=-b/(2*a);
    else {
      double q=-.5*(b+copysign(sqrt(disc),b));
      roots[n++]=q/a;roots[n++]=d/q;
    }
  }
  /* ISO 32000-1 8.7.4.5.4: the last admissible circle wins. Reject negative
     radii and disabled extensions before selecting, rather than after. */
  for(i=0;i<n;i++) {
    double t=roots[i],radius=fma(t,dr,c[2]);
    if(!isfinite(t) || !isfinite(radius) || radius<0 || (t<0 && !extend0) || (t>1 && !extend1)) continue;
    if(!found || t>best) { best=t;found=1; }
  }
  if(found) *out=best;
  return found;
}
static void store(exr_bitmap *bitmap,size_t index,const double rgb[3],unsigned char alpha) {
  unsigned char *p=bitmap->pixels+index*4;
  p[0]=(unsigned char)floor(fmax(0,fmin(1,rgb[0]))*255+.5);
  p[1]=(unsigned char)floor(fmax(0,fmin(1,rgb[1]))*255+.5);
  p[2]=(unsigned char)floor(fmax(0,fmin(1,rgb[2]))*255+.5);
  p[3]=alpha;
}
static exr_status sample(exr_pdf_function *function,exr_pdf_colorspace *space,unsigned intent,
                         const double *input,double rgb[3],exr_bitmap *inks,size_t index,size_t *work,exr_error *e) {
  double out[EXR_PDF_MAX_COLORANTS]={0};
  if(!exr_vector_work(work,exr_pdf_function_cost(function)+exr_pdf_colorspace_cost(space)))
    return exr_fail(e,EXR_LIMIT,"PDF shading samples exceed work budget");
  exr_status status=exr_pdf_function_eval_inputs(function,input,out,e);
  if(status!=EXR_OK) return status;
  if(inks->pixels) { unsigned k;for(k=0;k<4;k++) inks->pixels[index*4+k]=(unsigned char)floor(fmax(0,fmin(1,out[k]))*255+.5); }
  return exr_pdf_colorspace_rgb_intent(space,out,rgb,intent,e);
}

typedef struct {
  double coords[6];const double *rgb;const unsigned char *inks;size_t *work;
  unsigned type,extend0,extend1;
} shading_source;
static exr_status source_sample(void *context,double x,double y,unsigned space,double color[4],double *shape,double *opacity,exr_error *e) {
  shading_source *s=context;double t=0;unsigned index,count=space==EXR_GROUP_CMYK ? 4 : 3;double fraction;
  if(!exr_vector_work(s->work,s->type==2 ? 1 : 2)) return exr_fail(e,EXR_LIMIT,"PDF shading scan exceeds work budget");
  *shape=0;*opacity=1;
  if(s->type==2) {
    double scale=fmax(fabs(x),fabs(y)),c[4],dx,dy,len;
    for(unsigned k=0;k<4;k++) scale=fmax(scale,fabs(s->coords[k]));
    for(unsigned k=0;k<4;k++) c[k]=s->coords[k]/scale;
    dx=c[2]-c[0];dy=c[3]-c[1];len=hypot(dx,dy);
    if(!len) return exr_fail(e,EXR_LIMIT,"PDF axial shading exceeds coordinate precision");
    t=((x/scale-c[0])*(dx/len)+(y/scale-c[1])*(dy/len))/len;
    if(!isfinite(t)) return exr_fail(e,EXR_LIMIT,"PDF axial shading exceeds coordinate precision");
    if((t<0 && !s->extend0) || (t>1 && !s->extend1)) return EXR_OK;
  } else if(!radial_parameter(x,y,s->coords,s->extend0,s->extend1,&t)) return EXR_OK;
  t=fmax(0,fmin(1,t))*(AXIAL_SAMPLES-1);index=(unsigned)floor(t);fraction=t-index;
  if(index==AXIAL_SAMPLES-1) { index--;fraction=1; }
  if(space==EXR_GROUP_CMYK && !s->inks) return exr_fail(e,EXR_UNSUPPORTED,"PDF shading source lacks native CMYK samples");
  for(unsigned k=0;k<count;k++) {
    double a=space==EXR_GROUP_CMYK ? s->inks[index*4+k]/255. : s->rgb[index*3+k];
    double b=space==EXR_GROUP_CMYK ? s->inks[(index+1)*4+k]/255. : s->rgb[(index+1)*3+k];
    color[k]=fmax(0,fmin(1,a*(1-fraction)+b*fraction));
  }
  *shape=1;return EXR_OK;
}
static exr_status source_draw(exr_pdf_function *function,exr_pdf_colorspace *space,unsigned intent,
  unsigned type,const double coords[6],const double domain[4],int extend0,int extend1,
  const double matrix[6],const exr_pdf_paint_state *paint,size_t *work,exr_pdf_source_fn emit,void *context,
  unsigned native_cmyk,const exr_control *control,exr_error *e) {
  shading_source data={0};exr_paint_source source={sizeof(source),source_sample,&data};exr_bitmap inks={0};exr_status status=EXR_OK;exr_icc *profile=NULL;
  unsigned device=exr_pdf_colorspace_device(space);
  double *rgb=malloc(AXIAL_SAMPLES*3*sizeof(*rgb));
  if(!rgb) return exr_fail(e,EXR_MEMORY,"PDF shading colour table allocation failed");
  if(native_cmyk) {
    inks.pixels=malloc(AXIAL_SAMPLES*4);
    if(!inks.pixels) { free(rgb);return exr_fail(e,EXR_MEMORY,"PDF shading ink table allocation failed"); }
  }
  if(native_cmyk && device!=EXR_PDF_DEVICE_CMYK) status=exr_icc_default_cmyk(control,&profile,e);
  for(unsigned i=0;i<AXIAL_SAMPLES && status==EXR_OK;i++) {
    double t=(double)i/(AXIAL_SAMPLES-1),input=domain[0]*(1-t)+domain[1]*t;
    status=exr_control_cancel(control,e);if(status!=EXR_OK) break;
    status=sample(function,space,intent,&input,rgb+i*3,&inks,i,work,e);if(status!=EXR_OK) break;
    if(native_cmyk && device!=EXR_PDF_DEVICE_CMYK) {
      if(!exr_vector_work(work,exr_icc_cost(profile))) { status=exr_fail(e,EXR_LIMIT,"PDF shading conversion exceeds work budget");break; }
      double cmyk[4];exr_device_cmyk_from_rgb(profile,rgb+i*3,cmyk);
      for(unsigned k=0;k<4;k++) inks.pixels[i*4+k]=(unsigned char)floor(fmax(0,fmin(1,cmyk[k]))*255+.5);
    }
  }
  if(status==EXR_OK) status=exr_icc_deferred_status(profile,e);
  if(status==EXR_OK) {
    memcpy(data.coords,coords,sizeof(data.coords));data.type=type;data.extend0=extend0;data.extend1=extend1;
    data.work=work;data.rgb=rgb;data.inks=inks.pixels;
    status=emit(context,&source,matrix,paint,e);
  }
  exr_icc_free(profile);free(inks.pixels);free(rgb);return status;
}
exr_status exr_pdf_shading_draw(exr_pdf_file *file,exr_pdf_file *resource_file,uint32_t resources,
                                uint32_t value,const double ctm[6],const exr_pdf_paint_state *paint,size_t *work,
                                exr_pdf_shading_fn emit,exr_pdf_source_fn source,void *context,unsigned native_cmyk,
                                const exr_control *control,exr_error *e) {
  uint32_t id,coords_id,function_id,cs_id;const exr_pdf_value *v;double coords[6]={0},domain[4]={0,1,0,1},t;
  double function_matrix[6]={1,0,0,1,0,0};
  size_t local_work=0;int stream;
  unsigned intent=paint->intent;
  int extend0=0,extend1=0,type=0;unsigned i,components=1,ncoords;
  exr_pdf_colorspace *space=NULL;exr_pdf_function *function=NULL;
  exr_bitmap bitmap={0},inks={0};double matrix[6],local[6];exr_status status=EXR_OK;
  if(!emit && !source) return exr_fail(e,EXR_UNSUPPORTED,"Drawing consumer does not support PDF shadings");
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
    if(!emit) return exr_fail(e,EXR_UNSUPPORTED,"Drawing consumer lacks bitmap shading support");
    status=exr_pdf_shading_mesh(file,resource_file,resources,value,type,ctm,paint,work,emit,context,native_cmyk,control,e);
    return status;
  }
  if(stream) return exr_fail(e,EXR_FORMAT,"PDF shading is not a dictionary");
  if(type!=1 && type!=2 && type!=3) return exr_fail(e,EXR_UNSUPPORTED,"Unsupported PDF shading type");
  if(type!=1) {
    ncoords=type==2 ? 4u : 6u;
    if(exr_pdf_resolve(file,exr_pdf_get(file,value,"Coords"),&coords_id,e)!=EXR_OK) return e->code;
    status=numbers(file,coords_id,coords,ncoords,e);if(status!=EXR_OK) return status;
  } else {
    if(exr_pdf_resolve(file,exr_pdf_get(file,value,"Matrix"),&id,e)!=EXR_OK) return e->code;
    v=exr_pdf_value_at(file,id);
    if(v && v->kind!=EXR_PDF_NULL) { status=numbers(file,id,function_matrix,6,e);if(status!=EXR_OK) return status; }
  }
  if(exr_pdf_resolve(file,exr_pdf_get(file,value,"Domain"),&id,e)!=EXR_OK) return e->code;
  v=exr_pdf_value_at(file,id);
  if(v && v->kind!=EXR_PDF_NULL) {
    status=numbers(file,id,domain,type==1 ? 4 : 2,e);if(status!=EXR_OK) return status;
    if(domain[0]>domain[1] || (type==1 && domain[2]>domain[3])) return exr_fail(e,EXR_FORMAT,"Invalid PDF shading domain order");
  }
  if(type==3 && (coords[2]<0 || coords[5]<0)) return exr_fail(e,EXR_FORMAT,"Invalid PDF radial shading radii");
  if(exr_pdf_resolve(file,exr_pdf_get(file,value,"Extend"),&id,e)!=EXR_OK) return e->code;
  v=exr_pdf_value_at(file,id);
  if(type!=1 && v && v->kind!=EXR_PDF_NULL) {
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
  if(exr_pdf_colorspace_indexed(space)) { exr_pdf_colorspace_free(space);return exr_fail(e,EXR_FORMAT,"PDF function, axial and radial shadings cannot use Indexed colour"); }
  components=exr_pdf_colorspace_components(space);
  if(exr_pdf_resolve(file,exr_pdf_get(file,value,"Function"),&function_id,e)!=EXR_OK) { exr_pdf_colorspace_free(space); return e->code; }
  status=exr_pdf_function_open_components(file,function_id,type==1 ? 2 : 1,components,control,&function,e);
  if(status!=EXR_OK) { exr_pdf_colorspace_free(space); return status; }
  if(type==3 && !coords[2] && !coords[5]) goto done;
  if(type==2 && coords[0]==coords[2] && coords[1]==coords[3]) { status=exr_fail(e,EXR_FORMAT,"Degenerate PDF axial shading");goto done; }
  if(type!=1 && source) {
    status=source_draw(function,space,intent,(unsigned)type,coords,domain,extend0,extend1,ctm,paint,work,source,context,native_cmyk,control,e);
    goto done;
  }
  if(!emit) { status=exr_fail(e,EXR_UNSUPPORTED,"Drawing consumer lacks bitmap shading support");goto done; }

  if(type==1) {
    double combined[6],edge[6];
    if(domain[0]==domain[1] || domain[2]==domain[3]) goto done;
    multiply(ctm,function_matrix,combined);
    for(unsigned k=0;k<3;k++) {
      double x=k==1 ? domain[1] : domain[0],y=k==2 ? domain[3] : domain[2];
      edge[k*2]=combined[0]*x+combined[2]*y+combined[4];edge[k*2+1]=combined[1]*x+combined[3]*y+combined[5];
    }
    matrix[0]=edge[2]-edge[0];matrix[1]=edge[3]-edge[1];matrix[2]=edge[4]-edge[0];matrix[3]=edge[5]-edge[1];matrix[4]=edge[0];matrix[5]=edge[1];
    for(unsigned k=0;k<6;k++) if(!isfinite(matrix[k]) || fabs(matrix[k])>1e7) { status=exr_fail(e,EXR_LIMIT,"PDF function shading device transform exceeds budget");goto done; }
    if(matrix[0]*matrix[3]==matrix[1]*matrix[2]) goto done;
    bitmap.width=bitmap.height=RADIAL_SAMPLES;bitmap.channels=4;bitmap.stride=RADIAL_SAMPLES*4;
    bitmap.pixels=calloc((size_t)bitmap.stride*bitmap.height,1);
    if(!bitmap.pixels) { status=exr_fail(e,EXR_MEMORY,"PDF function shading allocation failed");goto done; }
    if(native_cmyk && exr_pdf_colorspace_device(space)==EXR_PDF_DEVICE_CMYK) {
      inks=bitmap;inks.pixels=calloc((size_t)bitmap.stride*bitmap.height,1);
      if(!inks.pixels) { status=exr_fail(e,EXR_MEMORY,"PDF function shading ink allocation failed");goto done; }
    }
    for(i=0;i<RADIAL_SAMPLES*RADIAL_SAMPLES && status==EXR_OK;i++) {
      unsigned row=i/RADIAL_SAMPLES,col=i%RADIAL_SAMPLES;double rgb[3]={0},u=(col+.5)/RADIAL_SAMPLES,vv=(row+.5)/RADIAL_SAMPLES;
      double input[2]={domain[0]*(1-u)+domain[1]*u,domain[2]*(1-vv)+domain[3]*vv};
      if(!col && exr_control_cancel(control,e)!=EXR_OK) { status=EXR_CANCELLED;break; }
      status=sample(function,space,intent,input,rgb,&inks,i,work,e);store(&bitmap,i,rgb,255);
    }
    if(status==EXR_OK) status=emit(context,&bitmap,inks.pixels ? &inks : NULL,matrix,paint,e);
  } else if(type==2) {
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
      { double input=domain[0]*(1-t)+domain[1]*t;status=sample(function,space,intent,&input,rgb,&inks,i,work,e); }
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
      if(!radial_parameter(x,y,coords,extend0,extend1,&t)) { store(&bitmap,i,rgb,0); continue; }
      if(t<0) { if(!extend0) { store(&bitmap,i,rgb,0); continue; } t=0; }
      if(t>1) { if(!extend1) { store(&bitmap,i,rgb,0); continue; } t=1; }
      { double input=domain[0]*(1-t)+domain[1]*t;status=sample(function,space,intent,&input,rgb,&inks,i,work,e); }
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
