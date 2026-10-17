/* SPDX-License-Identifier: GPL-3.0-only */
#include "pdf_raster_internal.h"
typedef struct { exr_pdf_file *file; exr_error error; } image_reader;
static uint32_t get(image_reader *r,uint32_t dict,const char *key) {
  uint32_t id=EXR_PDF_NONE; if(r->error.code==EXR_OK) exr_pdf_resolve(r->file,exr_pdf_get(r->file,dict,key),&id,&r->error);
  if(id!=EXR_PDF_NONE && exr_pdf_value_at(r->file,id)->kind==EXR_PDF_NULL) id=EXR_PDF_NONE;
  return id;
}
static int name_is(image_reader *r,uint32_t id,const char *name) {
  size_t n; const unsigned char *bytes=exr_pdf_bytes(r->file,id,&n);
  return bytes && exr_pdf_value_at(r->file,id)->kind==EXR_PDF_NAME && n==strlen(name) && !memcmp(bytes,name,n);
}
static int integer(image_reader *r,uint32_t id,uint32_t *out) {
  const exr_pdf_value *v=exr_pdf_value_at(r->file,id);
  if(!v || v->kind!=EXR_PDF_INT || v->u.integer<0 || (uint64_t)v->u.integer>UINT32_MAX) return 0;
  *out=(uint32_t)v->u.integer; return 1;
}
static int boolean(image_reader *r,uint32_t id,int *out) {
  const exr_pdf_value *v=exr_pdf_value_at(r->file,id);
  if(!v) { *out=0; return 1; }
  if(v->kind!=EXR_PDF_BOOL) return 0;
  *out=v->u.integer!=0; return 1;
}
static unsigned components(image_reader *r,uint32_t id) {
  return name_is(r,id,"DeviceGray") ? 1 : name_is(r,id,"DeviceRGB") ? 3 : name_is(r,id,"DeviceCMYK") ? 4 : 0;
}
static unsigned sample(const unsigned char *bytes,size_t bit,unsigned bits) {
  unsigned i,v=0; for(i=0;i<bits;i++) v=(v<<1)|((bytes[(bit+i)/8]>>(7-(bit+i)%8))&1); return v;
}
exr_status exr_pdf_image_decode(exr_pdf_file *file,uint32_t image,uint32_t resources,uint32_t color,
                                 exr_bitmap *out,int *interpolate,size_t *work,const exr_control *control,exr_error *e) {
  image_reader r={0}; uint32_t width,height,bits=1,id; unsigned channels=1,k; int stencil=0; double decode[8]={0,1,0,1,0,1,0,1};
  const unsigned char *bytes; size_t size,row,y,x,local_work=0; exr_bitmap bitmap={0}; const exr_pdf_value *v;
  if(out) memset(out,0,sizeof(*out));
  if(interpolate) *interpolate=0;
  if(!file || !out || !interpolate) return exr_fail(e,EXR_ARGUMENT,"Missing PDF image input/output");
  r.file=file; if(!work) work=&local_work;
  if(exr_control_cancel(control,&r.error)!=EXR_OK) goto done;
  if(exr_pdf_resolve(file,image,&image,&r.error)!=EXR_OK) goto done;
  v=exr_pdf_value_at(file,image); if(!v || v->kind!=EXR_PDF_STREAM) goto invalid;
  if(!integer(&r,get(&r,image,"Width"),&width) || !integer(&r,get(&r,image,"Height"),&height) || !width || !height) goto invalid;
  if(width>8192 || height>8192 || width>(size_t)16*1024*1024/height) { exr_fail(&r.error,EXR_LIMIT,"PDF image exceeds 16 million pixels"); goto done; }
  if(!boolean(&r,get(&r,image,"ImageMask"),&stencil) || !boolean(&r,get(&r,image,"Interpolate"),interpolate)) goto invalid;
  id=get(&r,image,"BitsPerComponent");
  if((id!=EXR_PDF_NONE || !stencil) && !integer(&r,id,&bits)) goto invalid;
  if((stencil && bits!=1) || (bits!=1 && bits!=2 && bits!=4 && bits!=8 && bits!=16)) goto invalid;
  id=get(&r,image,"ColorSpace");
  if(stencil) { if(id!=EXR_PDF_NONE) goto invalid; }
  else {
    channels=components(&r,id);
    if(!channels && id!=EXR_PDF_NONE && exr_pdf_value_at(file,id)->kind==EXR_PDF_NAME) {
      uint32_t spaces=get(&r,resources,"ColorSpace"); size_t n; const unsigned char *name=exr_pdf_bytes(file,id,&n); char key[128];
      if(n>=sizeof(key) || memchr(name,0,n)) goto invalid;
      memcpy(key,name,n); key[n]=0; id=get(&r,spaces,key); channels=components(&r,id);
    }
    if(!channels) { exr_fail(&r.error,EXR_FORMAT,"Non-device PDF image color space is unsupported"); goto done; }
  }
  if(get(&r,image,"Mask")!=EXR_PDF_NONE || get(&r,image,"SMask")!=EXR_PDF_NONE || get(&r,image,"SMaskInData")!=EXR_PDF_NONE) {
    exr_fail(&r.error,EXR_FORMAT,"PDF image masks are not implemented yet"); goto done;
  }
  id=get(&r,image,"Decode");
  if(id!=EXR_PDF_NONE) {
    uint32_t at; v=exr_pdf_value_at(file,id); if(v->kind!=EXR_PDF_ARRAY) goto invalid; at=v->first;
    for(k=0;k<2*channels;k++) {
      uint32_t value; if(at==EXR_PDF_NONE || exr_pdf_resolve(file,at,&value,&r.error)!=EXR_OK) goto invalid;
      v=exr_pdf_value_at(file,value); if(!v || (v->kind!=EXR_PDF_INT && v->kind!=EXR_PDF_REAL)) goto invalid;
      decode[k]=v->kind==EXR_PDF_INT ? (double)v->u.integer : v->u.number;
      if(!isfinite(decode[k]) || fabs(decode[k])>1e7) goto invalid;
      at=exr_pdf_value_at(file,at)->next;
    }
    if(at!=EXR_PDF_NONE) goto invalid;
  }
  if(stencil && !((decode[0]==0 && decode[1]==1) || (decode[0]==1 && decode[1]==0))) goto invalid;
  if(r.error.code!=EXR_OK || exr_pdf_stream_data(file,image,&bytes,&size,&r.error)!=EXR_OK) goto done;
  row=((size_t)width*channels*bits+7)/8;
  if(row>SIZE_MAX/height || row*height!=size) goto invalid;
  bitmap.width=width; bitmap.height=height; bitmap.channels=4; bitmap.stride=width*4; bitmap.pixels=malloc((size_t)bitmap.stride*height);
  if(!bitmap.pixels) { exr_fail(&r.error,EXR_MEMORY,"PDF image pixel allocation failed"); goto done; }
  for(y=0;y<height;y++) {
    if(!(y&63) && exr_control_cancel(control,&r.error)!=EXR_OK) goto done;
    if(!exr_vector_work(work,(size_t)width*channels)) { exr_fail(&r.error,EXR_LIMIT,"PDF image sample work exceeds budget"); goto done; }
    for(x=0;x<width;x++) {
      double values[4]={0}; unsigned char *p=bitmap.pixels+y*bitmap.stride+x*4;
      for(k=0;k<channels;k++) {
        double unit=(double)sample(bytes+y*row,(x*channels+k)*bits,bits)/((1u<<bits)-1);
        values[k]=fmax(0,fmin(1,decode[2*k]+unit*(decode[2*k+1]-decode[2*k])));
      }
      if(stencil) { p[0]=(unsigned char)(color>>24); p[1]=(unsigned char)(color>>16); p[2]=(unsigned char)(color>>8); p[3]=(unsigned char)floor((1-values[0])*255+.5); }
      else {
        if(channels==1) p[0]=p[1]=p[2]=(unsigned char)floor(values[0]*255+.5);
        else if(channels==3) for(k=0;k<3;k++) p[k]=(unsigned char)floor(values[k]*255+.5);
        else for(k=0;k<3;k++) p[k]=(unsigned char)floor((1-fmin(1,values[k]+values[3]))*255+.5);
        p[3]=255;
      }
    }
  }
  if(exr_control_cancel(control,&r.error)==EXR_OK) { *out=bitmap; memset(&bitmap,0,sizeof(bitmap)); } goto done;
invalid:
  if(r.error.code==EXR_OK) exr_fail(&r.error,EXR_FORMAT,"Invalid PDF image dictionary, samples or Decode array");
done:
  free(bitmap.pixels); if(r.error.code!=EXR_OK) *interpolate=0;
  if(e) *e=r.error;
  return r.error.code;
}
