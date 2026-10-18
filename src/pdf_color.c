/* SPDX-License-Identifier: GPL-3.0-only */
#include "pdf_internal.h"
#include "pdf_function_internal.h"
#include "icc_internal.h"
typedef enum { SPACE_GRAY,SPACE_RGB,SPACE_CMYK,SPACE_CALGRAY,SPACE_CALRGB,SPACE_LAB,SPACE_INDEXED,SPACE_ICC,SPACE_TINT,SPACE_ALL } space_kind;
struct exr_pdf_colorspace {
  space_kind kind; unsigned components,high; int no_paint;
  double ranges[2*EXR_PDF_MAX_COLORANTS],gamma[3],matrix[9],transform[9],offset[3];
  unsigned char palette[1024];
  struct exr_pdf_colorspace *alternate;
  exr_pdf_function *function;
  exr_icc *icc;
};
typedef struct {
  exr_pdf_file *resources_file; uint32_t resources;
  const exr_control *control; exr_error *error;
  struct { exr_pdf_file *file; uint32_t value; } active[16];
} color_reader;
static int name_is(exr_pdf_file *file,uint32_t id,const char *name) {
  size_t size; const unsigned char *bytes=exr_pdf_bytes(file,id,&size); const exr_pdf_value *v=exr_pdf_value_at(file,id);
  return v && v->kind==EXR_PDF_NAME && size==strlen(name) && !memcmp(bytes,name,size);
}
static int resolve(color_reader *r,exr_pdf_file *file,uint32_t id,uint32_t *out) {
  return exr_pdf_resolve(file,id,out,r->error)==EXR_OK;
}
static uint32_t get(color_reader *r,exr_pdf_file *file,uint32_t dict,const char *key) {
  uint32_t id=EXR_PDF_NONE; const exr_pdf_value *v;
  if(r->error->code==EXR_OK) (void)resolve(r,file,exr_pdf_get(file,dict,key),&id);
  v=exr_pdf_value_at(file,id); return v && v->kind==EXR_PDF_NULL ? EXR_PDF_NONE : id;
}
static int number(exr_pdf_file *file,uint32_t id,double *out) {
  const exr_pdf_value *v=exr_pdf_value_at(file,id);
  if(!v || (v->kind!=EXR_PDF_INT && v->kind!=EXR_PDF_REAL)) return 0;
  *out=v->kind==EXR_PDF_INT ? (double)v->u.integer : v->u.number;
  return isfinite(*out) && fabs(*out)<=1e7;
}
static int array(color_reader *r,exr_pdf_file *file,uint32_t id,uint32_t *values,size_t count) {
  const exr_pdf_value *v=exr_pdf_value_at(file,id); uint32_t at; size_t i;
  if(!v || v->kind!=EXR_PDF_ARRAY) return 0;
  at=v->first;
  for(i=0;i<count;i++) {
    uint32_t next; v=exr_pdf_value_at(file,at); if(!v) return 0; next=v->next;
    if(!resolve(r,file,at,&values[i])) return 0;
    at=next;
  }
  return at==EXR_PDF_NONE;
}
static int numbers(color_reader *r,exr_pdf_file *file,uint32_t id,double *values,size_t count) {
  uint32_t ids[9]; size_t i;
  if(count>9 || !array(r,file,id,ids,count)) return 0;
  for(i=0;i<count;i++) if(!number(file,ids[i],&values[i])) return 0;
  return 1;
}
static double clamp(double value,double low,double high) { return fmax(low,fmin(high,value)); }
static double transfer(double linear) {
  linear=clamp(linear,0,1);
  return linear<=0.0031308 ? 12.92*linear : 1.055*pow(linear,1/2.4)-0.055;
}
static double lab_inverse(double value) { return value>=6.0/29 ? value*value*value : (108.0/841)*(value-4.0/29); }
exr_status exr_pdf_colorspace_rgb(const exr_pdf_colorspace *s,const double *values,double rgb[3],exr_error *error) {
  double v[EXR_PDF_MAX_COLORANTS],xyz[3]={0}; unsigned i,j;
  if(exr_pdf_colorspace_no_paint(s)) { memset(rgb,0,3*sizeof(double)); return EXR_OK; }
  for(i=0;i<s->components;i++) v[i]=clamp(values[i],s->ranges[2*i],s->ranges[2*i+1]);
  if(s->kind==SPACE_GRAY) { rgb[0]=rgb[1]=rgb[2]=v[0]; return EXR_OK; }
  /* All is an ink tint on every output colorant; additive sRGB inverts it. */
  if(s->kind==SPACE_ALL) { rgb[0]=rgb[1]=rgb[2]=1-v[0]; return EXR_OK; }
  if(s->kind==SPACE_RGB) { memcpy(rgb,v,3*sizeof(double)); return EXR_OK; }
  if(s->kind==SPACE_CMYK) { for(i=0;i<3;i++) rgb[i]=1-fmin(1,v[i]+v[3]); return EXR_OK; }
  if(s->kind==SPACE_INDEXED) {
    unsigned index=(unsigned)floor(v[0]+.5); for(i=0;i<3;i++) rgb[i]=s->palette[index*4+i]/255.0; return EXR_OK;
  }
  if(s->kind==SPACE_ICC) return s->icc ? exr_icc_rgb(s->icc,v,rgb,error) : exr_pdf_colorspace_rgb(s->alternate,v,rgb,error);
  if(s->kind==SPACE_TINT) {
    double alternate[4]={0}; exr_status status=exr_pdf_function_eval_inputs(s->function,v,alternate,error);
    return status==EXR_OK ? exr_pdf_colorspace_rgb(s->alternate,alternate,rgb,error) : status;
  }
  if(s->kind==SPACE_CALGRAY) {
    double gray=pow(v[0],s->gamma[0]); for(i=0;i<3;i++) xyz[i]=gray*s->matrix[i];
  } else if(s->kind==SPACE_CALRGB) {
    for(i=0;i<3;i++) v[i]=pow(v[i],s->gamma[i]);
    for(i=0;i<3;i++) for(j=0;j<3;j++) xyz[i]+=s->matrix[j*3+i]*v[j];
  } else {
    double m=(v[0]+16)/116;
    xyz[0]=s->matrix[0]*lab_inverse(m+v[1]/500); xyz[1]=lab_inverse(m); xyz[2]=s->matrix[2]*lab_inverse(m-v[2]/200);
  }
  for(i=0;i<3;i++) {
    double linear=s->offset[i];
    for(j=0;j<3;j++) linear+=s->transform[3*i+j]*xyz[j];
    rgb[i]=transfer(linear);
  }
  return EXR_OK;
}
/* Fixed output policy: Bradford adaptation to D65, relative XYZ black-point
   compensation, linear sRGB conversion and final clipping to its gamut. */
static int calibration(exr_pdf_colorspace *s,const double white[3],const double black[3]) {
  static const double bradford[9]={.8951,.2664,-.1614,-.7502,1.7135,.0367,.0389,-.0685,1.0296};
  static const double inverse[9]={.9869929055,-.1470542564,.1599626517,.4323052697,.5183602715,.0492912282,-.0085286646,.0400428217,.9684866958};
  static const double destination[3]={.95047,1,1.08883};
  static const double srgb[9]={3.2404542,-1.5371385,-.4985314,-.9692660,1.8760108,.0415560,.0556434,-.2040259,1.0572252};
  double ratio[3],adapt[9]={0},adapted_black[3]={0},scale[3],offset[3]; unsigned i,j,k;
  for(i=0;i<3;i++) {
    double source=0,target=0;
    for(j=0;j<3;j++) { source+=bradford[i*3+j]*white[j]; target+=bradford[i*3+j]*destination[j]; }
    if(source<=1e-12) return 0;
    ratio[i]=target/source;
  }
  for(i=0;i<3;i++) for(j=0;j<3;j++) for(k=0;k<3;k++) adapt[i*3+j]+=inverse[i*3+k]*ratio[k]*bradford[k*3+j];
  for(i=0;i<3;i++) {
    for(j=0;j<3;j++) adapted_black[i]+=adapt[i*3+j]*black[j];
    adapted_black[i]=fmax(0,adapted_black[i]);
    if(destination[i]-adapted_black[i]<=1e-12) return 0;
    scale[i]=destination[i]/(destination[i]-adapted_black[i]); offset[i]=-adapted_black[i]*scale[i];
  }
  for(i=0;i<3;i++) {
    for(k=0;k<3;k++) s->offset[i]+=srgb[i*3+k]*offset[k];
    for(j=0;j<3;j++) for(k=0;k<3;k++) s->transform[i*3+j]+=srgb[i*3+k]*scale[k]*adapt[k*3+j];
  }
  return 1;
}
static exr_pdf_colorspace *device(space_kind kind,unsigned components) {
  exr_pdf_colorspace *s=calloc(1,sizeof(*s)); unsigned i;
  if(s) { s->kind=kind; s->components=components; for(i=0;i<components;i++) s->ranges[i*2+1]=1; }
  return s;
}
static exr_status open_space(color_reader *r,exr_pdf_file *file,uint32_t id,unsigned depth,exr_pdf_colorspace **out) {
  exr_pdf_colorspace *s=NULL; const exr_pdf_value *v; uint32_t ids[5],dict,value; size_t i; unsigned channels;
  double white[3]={0},black[3]={0}; exr_status status=EXR_FORMAT;
  *out=NULL;
  if(depth==16) return exr_fail(r->error,EXR_LIMIT,"PDF color space nesting exceeds 16");
  if(exr_control_cancel(r->control,r->error)!=EXR_OK) return EXR_CANCELLED;
  if(!resolve(r,file,id,&id)) return r->error->code;
  for(i=0;i<depth;i++) if(r->active[i].file==file && r->active[i].value==id) return exr_fail(r->error,EXR_FORMAT,"Cyclic PDF color space");
  r->active[depth].file=file; r->active[depth].value=id;
  v=exr_pdf_value_at(file,id); if(!v) goto bad;
  if(name_is(file,id,"DeviceGray") || name_is(file,id,"DeviceRGB") || name_is(file,id,"DeviceCMYK")) {
    channels=name_is(file,id,"DeviceGray") ? 1 : name_is(file,id,"DeviceRGB") ? 3 : 4;
    s=device(channels==1 ? SPACE_GRAY : channels==3 ? SPACE_RGB : SPACE_CMYK,channels); if(!s) goto memory;
    *out=s; return EXR_OK;
  }
  if(v->kind==EXR_PDF_NAME) {
    const unsigned char *bytes; size_t n; char key[128]; uint32_t spaces;
    bytes=exr_pdf_bytes(file,id,&n); if(!n || n>=sizeof(key) || memchr(bytes,0,n)) goto bad;
    memcpy(key,bytes,n); key[n]=0; spaces=get(r,r->resources_file,r->resources,"ColorSpace"); value=get(r,r->resources_file,spaces,key);
    if(r->error->code!=EXR_OK) goto bad;
    return open_space(r,r->resources_file,value,depth+1,out);
  }
  if(v->kind!=EXR_PDF_ARRAY || v->first==EXR_PDF_NONE || !resolve(r,file,v->first,&value)) goto bad;
  if(name_is(file,value,"Indexed")) {
    const unsigned char *lookup; size_t length; exr_pdf_colorspace *base=NULL;
    if(!array(r,file,id,ids,4)) goto bad;
    v=exr_pdf_value_at(file,ids[2]); if(!v || v->kind!=EXR_PDF_INT || v->u.integer<0 || v->u.integer>255) goto bad;
    s=device(SPACE_INDEXED,1); if(!s) goto memory; s->high=(unsigned)v->u.integer; s->ranges[1]=s->high;
    status=open_space(r,file,ids[1],depth+1,&base); if(status!=EXR_OK) goto done;
    if(base->kind==SPACE_INDEXED) { exr_pdf_colorspace_free(base); goto bad; }
    v=exr_pdf_value_at(file,ids[3]);
    if(v && v->kind==EXR_PDF_STRING) lookup=exr_pdf_bytes(file,ids[3],&length);
    else if(v && v->kind==EXR_PDF_STREAM) { status=exr_pdf_stream_data(file,ids[3],&lookup,&length,r->error); if(status!=EXR_OK) { exr_pdf_colorspace_free(base); goto done; } }
    else { exr_pdf_colorspace_free(base); goto bad; }
    if(length!=((size_t)s->high+1)*base->components) { exr_pdf_colorspace_free(base); goto bad; }
    for(i=0;i<=s->high;i++) {
      double values[EXR_PDF_MAX_COLORANTS],rgb[3]; unsigned k;
      if(!(i&63) && exr_control_cancel(r->control,r->error)!=EXR_OK) { exr_pdf_colorspace_free(base); status=EXR_CANCELLED; goto done; }
      for(k=0;k<base->components;k++) values[k]=base->ranges[2*k]+lookup[i*base->components+k]/255.0*(base->ranges[2*k+1]-base->ranges[2*k]);
      status=exr_pdf_colorspace_rgb(base,values,rgb,r->error);
      if(status!=EXR_OK) { exr_pdf_colorspace_free(base); goto done; }
      for(k=0;k<3;k++) s->palette[i*4+k]=(unsigned char)floor(rgb[k]*255+.5);
      s->palette[i*4+3]=255;
    }
    s->no_paint=exr_pdf_colorspace_no_paint(base);
    exr_pdf_colorspace_free(base); *out=s; return EXR_OK;
  }
  if(name_is(file,value,"DeviceN")) {
    uint32_t at,names[EXR_PDF_MAX_COLORANTS]; size_t lengths[EXR_PDF_MAX_COLORANTS]; const unsigned char *labels[EXR_PDF_MAX_COLORANTS];
    unsigned n=0,j,all_none=1;
    if(!array(r,file,id,ids,4)) {
      if(!array(r,file,id,ids,5)) goto bad;
      v=exr_pdf_value_at(file,ids[4]); if(!v || (v->kind!=EXR_PDF_DICT && v->kind!=EXR_PDF_NULL)) goto bad;
    }
    v=exr_pdf_value_at(file,ids[1]); if(!v || v->kind!=EXR_PDF_ARRAY) goto bad;
    for(at=v->first;at!=EXR_PDF_NONE;) {
      uint32_t next; const exr_pdf_value *entry=exr_pdf_value_at(file,at); if(!entry) goto bad; next=entry->next;
      if(n==EXR_PDF_MAX_COLORANTS) { status=exr_fail(r->error,EXR_LIMIT,"DeviceN exceeds 32 colorants"); goto done; }
      if(!resolve(r,file,at,&names[n])) goto bad;
      v=exr_pdf_value_at(file,names[n]); labels[n]=exr_pdf_bytes(file,names[n],&lengths[n]);
      if(!v || v->kind!=EXR_PDF_NAME || !labels[n] || !lengths[n] || memchr(labels[n],0,lengths[n]) || name_is(file,names[n],"All")) goto bad;
      if(lengths[n]>127) { status=exr_fail(r->error,EXR_LIMIT,"DeviceN colorant name exceeds 127 bytes"); goto done; }
      if(!name_is(file,names[n],"None")) {
        all_none=0;
        for(j=0;j<n;j++) if(lengths[j]==lengths[n] && !memcmp(labels[j],labels[n],lengths[n])) goto bad;
      }
      n++; at=next;
    }
    if(!n) goto bad;
    s=device(SPACE_TINT,n); if(!s) goto memory; s->no_paint=all_none;
    if(all_none) { *out=s; return EXR_OK; }
    status=open_space(r,file,ids[2],depth+1,&s->alternate); if(status!=EXR_OK) goto done;
    if(s->alternate->kind==SPACE_INDEXED || s->alternate->kind==SPACE_TINT || s->alternate->kind==SPACE_ALL) goto bad;
    status=exr_pdf_function_open_inputs(file,ids[3],n,s->alternate->components,r->control,&s->function,r->error); if(status!=EXR_OK) goto done;
    *out=s; return EXR_OK;
  }
  if(name_is(file,value,"Separation")) {
    const unsigned char *name; size_t length;
    if(!array(r,file,id,ids,4)) goto bad;
    v=exr_pdf_value_at(file,ids[1]); name=exr_pdf_bytes(file,ids[1],&length);
    if(!v || v->kind!=EXR_PDF_NAME || !name || !length || memchr(name,0,length)) goto bad;
    s=device(name_is(file,ids[1],"All") ? SPACE_ALL : SPACE_TINT,1); if(!s) goto memory;
    s->no_paint=name_is(file,ids[1],"None");
    if(s->no_paint || s->kind==SPACE_ALL) { *out=s; return EXR_OK; }
    status=open_space(r,file,ids[2],depth+1,&s->alternate); if(status!=EXR_OK) goto done;
    if(s->alternate->kind==SPACE_INDEXED || s->alternate->kind==SPACE_TINT || s->alternate->kind==SPACE_ALL) goto bad;
    status=exr_pdf_function_open(file,ids[3],s->alternate->components,r->control,&s->function,r->error);
    if(status!=EXR_OK) goto done;
    *out=s; return EXR_OK;
  }
  if(!array(r,file,id,ids,2)) goto bad;
  if(name_is(file,value,"ICCBased")) {
    const exr_pdf_value *n; uint32_t alternate;
    v=exr_pdf_value_at(file,ids[1]); if(!v || v->kind!=EXR_PDF_STREAM) goto bad;
    value=get(r,file,ids[1],"N"); n=exr_pdf_value_at(file,value);
    if(!n || n->kind!=EXR_PDF_INT || (n->u.integer!=1 && n->u.integer!=3 && n->u.integer!=4)) goto bad;
    channels=(unsigned)n->u.integer; s=device(SPACE_ICC,channels); if(!s) goto memory;
    value=get(r,file,ids[1],"Range"); if(value!=EXR_PDF_NONE && !numbers(r,file,value,s->ranges,channels*2)) goto bad;
    for(i=0;i<channels;i++) if(s->ranges[2*i]>s->ranges[2*i+1]) goto bad;
#ifdef EXR_ENABLE_ICC
    { const unsigned char *profile;size_t size;
      status=exr_pdf_stream_data(file,ids[1],&profile,&size,r->error);if(status!=EXR_OK) goto done;
      status=exr_icc_open(profile,size,channels,r->control,&s->icc,r->error);if(status!=EXR_OK) goto done;
      if(s->icc) { *out=s;return EXR_OK; }
    }
#endif
    alternate=get(r,file,ids[1],"Alternate");
    if(alternate==EXR_PDF_NONE) { s->alternate=device(channels==1 ? SPACE_GRAY : channels==3 ? SPACE_RGB : SPACE_CMYK,channels); if(!s->alternate) goto memory; }
    else { status=open_space(r,file,alternate,depth+1,&s->alternate); if(status!=EXR_OK) goto done; }
    if(s->alternate->components!=channels) goto bad;
    *out=s; return EXR_OK;
  }
  if(!name_is(file,value,"CalGray") && !name_is(file,value,"CalRGB") && !name_is(file,value,"Lab")) goto bad;
  channels=name_is(file,value,"CalGray") ? 1 : 3;
  s=device(channels==1 ? SPACE_CALGRAY : name_is(file,value,"Lab") ? SPACE_LAB : SPACE_CALRGB,channels); if(!s) goto memory;
  dict=ids[1]; v=exr_pdf_value_at(file,dict); if(!v || v->kind!=EXR_PDF_DICT) goto bad;
  if(!numbers(r,file,get(r,file,dict,"WhitePoint"),white,3) || white[0]<=0 || white[1]!=1 || white[2]<=0) goto bad;
  value=get(r,file,dict,"BlackPoint"); if(value!=EXR_PDF_NONE && !numbers(r,file,value,black,3)) goto bad;
  for(i=0;i<3;i++) { if(black[i]<0) goto bad; s->gamma[i]=1; }
  if(s->kind==SPACE_CALGRAY || s->kind==SPACE_CALRGB) {
    value=get(r,file,dict,"Gamma");
    if(value!=EXR_PDF_NONE && (channels==1 ? !number(file,value,&s->gamma[0]) : !numbers(r,file,value,s->gamma,3))) goto bad;
    for(i=0;i<channels;i++) if(s->gamma[i]<=0) goto bad;
  }
  if(s->kind==SPACE_CALRGB) {
    s->matrix[0]=s->matrix[4]=s->matrix[8]=1;
    value=get(r,file,dict,"Matrix"); if(value!=EXR_PDF_NONE && !numbers(r,file,value,s->matrix,9)) goto bad;
  } else memcpy(s->matrix,white,3*sizeof(double));
  if(s->kind==SPACE_LAB) {
    s->ranges[1]=100; s->ranges[2]=s->ranges[4]=-100; s->ranges[3]=s->ranges[5]=100;
    value=get(r,file,dict,"Range"); if(value!=EXR_PDF_NONE && !numbers(r,file,value,s->ranges+2,4)) goto bad;
    if(s->ranges[2]>s->ranges[3] || s->ranges[4]>s->ranges[5]) goto bad;
  }
  if(r->error->code!=EXR_OK) goto bad;
  if(!calibration(s,white,black)) { status=exr_fail(r->error,EXR_FORMAT,"Nonphysical PDF CIE white/black point for sRGB conversion"); goto done; }
  *out=s; return EXR_OK;
memory:
  status=exr_fail(r->error,EXR_MEMORY,"PDF color space allocation failed"); goto done;
bad:
  if(r->error->code==EXR_OK) exr_fail(r->error,EXR_FORMAT,"Unsupported or invalid PDF color space");
  status=r->error->code;
done:
  exr_pdf_colorspace_free(s); return status;
}
exr_status exr_pdf_colorspace_open(exr_pdf_file *file,uint32_t value,exr_pdf_file *resource_file,
  uint32_t resources,const exr_control *control,exr_pdf_colorspace **out,exr_error *error) {
  exr_error local={0}; color_reader r={0}; exr_status status;
  if(out) *out=NULL;
  if(!file || !resource_file || !out) return exr_fail(error,EXR_ARGUMENT,"Missing PDF color space input/output");
  r.resources_file=resource_file; r.resources=resources; r.control=control; r.error=error ? error : &local; memset(r.error,0,sizeof(*r.error));
  status=open_space(&r,file,value,0,out); return status==EXR_OK ? exr_fail(error,EXR_OK,"") : status;
}
void exr_pdf_colorspace_free(exr_pdf_colorspace *s) { if(s) { exr_pdf_colorspace_free(s->alternate); exr_pdf_function_free(s->function); exr_icc_free(s->icc); free(s); } }
size_t exr_pdf_colorspace_memory(const exr_pdf_colorspace *s) { return s ? sizeof(*s)+exr_pdf_colorspace_memory(s->alternate)+exr_pdf_function_memory(s->function)+exr_icc_memory(s->icc) : 0; }
int exr_pdf_colorspace_no_paint(const exr_pdf_colorspace *s) { return s && (s->no_paint || exr_pdf_colorspace_no_paint(s->alternate)); }
size_t exr_pdf_colorspace_cost(const exr_pdf_colorspace *s) { return !s ? 0 : exr_pdf_colorspace_no_paint(s) ? s->components : s->components+exr_pdf_function_cost(s->function)+exr_icc_cost(s->icc)+exr_pdf_colorspace_cost(s->alternate); }
unsigned exr_pdf_colorspace_components(const exr_pdf_colorspace *s) { return s ? s->components : 0; }
exr_pdf_color_space exr_pdf_colorspace_device(const exr_pdf_colorspace *s) {
  return !s ? 0 : s->kind==SPACE_GRAY ? EXR_PDF_DEVICE_GRAY : s->kind==SPACE_RGB ? EXR_PDF_DEVICE_RGB : s->kind==SPACE_CMYK ? EXR_PDF_DEVICE_CMYK : 0;
}
int exr_pdf_colorspace_indexed(const exr_pdf_colorspace *s) { return s && s->kind==SPACE_INDEXED; }
void exr_pdf_colorspace_ranges(const exr_pdf_colorspace *s,double *ranges) { memcpy(ranges,s->ranges,2*s->components*sizeof(double)); }
void exr_pdf_colorspace_initial(const exr_pdf_colorspace *s,double *values) {
  unsigned i; memset(values,0,s->components*sizeof(double));
  for(i=0;i<s->components;i++) values[i]=clamp((s->kind==SPACE_CMYK && i==3) || s->kind==SPACE_TINT || s->kind==SPACE_ALL ? 1 : 0,s->ranges[i*2],s->ranges[i*2+1]);
}
