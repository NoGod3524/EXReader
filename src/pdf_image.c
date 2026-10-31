/* SPDX-License-Identifier: MIT */
#include "pdf_raster_internal.h"
#include "pdf_jpx_internal.h"
typedef struct { exr_pdf_file *file; exr_error error; } image_reader;
typedef struct { uint32_t active[16]; size_t depth,live; } image_chain;
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
static uint32_t resolve(image_reader *r,uint32_t id) {
  uint32_t out=EXR_PDF_NONE; if(r->error.code==EXR_OK) exr_pdf_resolve(r->file,id,&out,&r->error); return out;
}
static unsigned sample(const unsigned char *bytes,size_t bit,unsigned bits) {
  unsigned i,v=0; for(i=0;i<bits;i++) v=(v<<1)|((bytes[(bit+i)/8]>>(7-(bit+i)%8))&1); return v;
}
static int jpeg_frame(const unsigned char *data,size_t size,uint32_t width,uint32_t height,unsigned channels) {
  size_t at=2;
  if(size<4 || data[0]!=0xff || data[1]!=0xd8) return 0;
  while(at<size) {
    unsigned marker,length;
    if(data[at++]!=0xff) return 0;
    while(at<size && data[at]==0xff) at++;
    if(at==size) return 0;
    marker=data[at++];
    if(marker==0xd9 || marker==0xda || !marker) return 0;
    if(marker==1 || (marker>=0xd0 && marker<=0xd8)) continue;
    if(size-at<2) return 0;
    length=((unsigned)data[at]<<8)|data[at+1];
    if(length<2 || length>size-at) return 0;
    if(marker==0xc0 || marker==0xc1 || marker==0xc2) {
      return length==8+3*channels && data[at+2]==8 && data[at+7]==channels &&
        (((unsigned)data[at+3]<<8)|data[at+4])==height && (((unsigned)data[at+5]<<8)|data[at+6])==width;
    }
    at+=length;
  }
  return 0;
}
static void release_texture(exr_vector_texture *texture,image_chain *chain) {
  if(!texture) return;
  release_texture(texture->mask,chain);
  if(chain && texture->bitmap.pixels) chain->live-=(size_t)texture->bitmap.stride*texture->bitmap.height;
  free(texture->bitmap.pixels); free(texture);
}
void exr_pdf_image_release(exr_vector_texture *texture) { release_texture(texture,NULL); }
static int image_name_is(exr_pdf_file *file,uint32_t id,const char *name) {
  const exr_pdf_value *v=exr_pdf_value_at(file,id);size_t n;const unsigned char *bytes;
  if(!v || v->kind!=EXR_PDF_NAME) return 0;
  bytes=exr_pdf_bytes(file,id,&n);
  return bytes && n==strlen(name) && !memcmp(bytes,name,n);
}
static exr_status decode_image(exr_pdf_file *file,uint32_t image,exr_pdf_file *resource_file,uint32_t resources,uint32_t color,
                                 unsigned intent,exr_vector_texture **out,size_t *work,const exr_control *control,exr_error *e,
                                 image_chain *chain,unsigned *kind,exr_bitmap *inks) {
  image_reader r={0}; uint32_t width,height,bits=1,id,key[2*EXR_PDF_MAX_COLORANTS]={0}; unsigned channels=1,k,indexed=0,color_key=0;
  int stencil=0,interpolate=0; double decode[2*EXR_PDF_MAX_COLORANTS]={0,1}; exr_pdf_colorspace *space=NULL;
  const unsigned char *bytes; unsigned char *jpx_samples=NULL; size_t size,row,y,x,local_work=0,owned=0,jpx_live=0; exr_bitmap bitmap={0}; exr_vector_texture *mask_texture=NULL; const exr_pdf_value *v;
  uint32_t mask=EXR_PDF_NONE; unsigned soft=0,entered=0,charged=0,matte=0; double matte_rgb[4]={0};
  exr_pdf_stream_codec codec=EXR_PDF_STREAM_RAW; uint32_t parameters=EXR_PDF_NONE;
  if(out) *out=NULL;
  if(inks) memset(inks,0,sizeof(*inks));
  if(!file || !out) return exr_fail(e,EXR_ARGUMENT,"Missing PDF image input/output");
  r.file=file; if(!work) work=&local_work;
  if(exr_control_cancel(control,&r.error)!=EXR_OK) goto done;
  if(exr_pdf_resolve(file,image,&image,&r.error)!=EXR_OK) goto done;
  v=exr_pdf_value_at(file,image); if(!v || v->kind!=EXR_PDF_STREAM) goto invalid;
  if(chain->depth==16) { exr_fail(&r.error,EXR_LIMIT,"PDF image mask nesting exceeds 16"); goto done; }
  for(x=0;x<chain->depth;x++) if(chain->active[x]==image) goto invalid;
  chain->active[chain->depth++]=image; entered=1;
  if(!integer(&r,get(&r,image,"Width"),&width) || !integer(&r,get(&r,image,"Height"),&height) || !width || !height) goto invalid;
  if(width>8192 || height>8192 || width>(size_t)16*1024*1024/height) { exr_fail(&r.error,EXR_LIMIT,"PDF image exceeds 16 million pixels"); goto done; }
  if(!boolean(&r,get(&r,image,"ImageMask"),&stencil) || !boolean(&r,get(&r,image,"Interpolate"),&interpolate)) goto invalid;
  id=get(&r,image,"BitsPerComponent");
  if((id!=EXR_PDF_NONE || !stencil) && !integer(&r,id,&bits)) goto invalid;
  if((stencil && bits!=1) || (bits!=1 && bits!=2 && bits!=4 && bits!=8 && bits!=16)) goto invalid;
  id=get(&r,image,"ColorSpace");
  if(stencil) { if(id!=EXR_PDF_NONE) goto invalid; }
  else {
    if(exr_pdf_colorspace_open(file,id,resource_file,resources,control,&space,&r.error)!=EXR_OK) goto done;
    channels=exr_pdf_colorspace_components(space); indexed=exr_pdf_colorspace_indexed(space);
    exr_pdf_colorspace_ranges(space,decode);
    if(!channels || (indexed && bits==16)) { if(r.error.code==EXR_OK) exr_fail(&r.error,EXR_FORMAT,"Unsupported or invalid PDF image color space"); goto done; }
    if(indexed) decode[1]=(1u<<bits)-1;
  }
  id=get(&r,image,"SMaskInData");
  if(id!=EXR_PDF_NONE) { uint32_t value; if(!integer(&r,id,&value) || value) goto invalid; }
  mask=get(&r,image,"SMask");
  if(mask!=EXR_PDF_NONE && name_is(&r,mask,"None")) mask=EXR_PDF_NONE;
  if(mask!=EXR_PDF_NONE) {
    uint32_t at;
    if(stencil || exr_pdf_value_at(file,mask)->kind!=EXR_PDF_STREAM) goto invalid;
    soft=1; id=get(&r,mask,"Matte");
    if(id!=EXR_PDF_NONE) {
      double values[4]={0};
      if(exr_pdf_colorspace_device(space)!=EXR_PDF_DEVICE_GRAY && exr_pdf_colorspace_device(space)!=EXR_PDF_DEVICE_RGB &&
         exr_pdf_colorspace_device(space)!=EXR_PDF_DEVICE_CMYK) { exr_fail(&r.error,EXR_FORMAT,"PDF image matte colour space is unsupported"); goto done; }
      v=exr_pdf_value_at(file,id); if(v->kind!=EXR_PDF_ARRAY) goto invalid; at=v->first;
      for(k=0;k<channels;k++) {
        uint32_t value=resolve(&r,at); v=exr_pdf_value_at(file,value);
        if(!v || (v->kind!=EXR_PDF_INT && v->kind!=EXR_PDF_REAL)) goto invalid;
        values[k]=v->kind==EXR_PDF_INT ? (double)v->u.integer : v->u.number;
        if(!isfinite(values[k]) || values[k]<0 || values[k]>1) goto invalid;
        at=exr_pdf_value_at(file,at)->next;
      }
      if(at!=EXR_PDF_NONE) goto invalid;
      for(k=0;k<channels;k++) matte_rgb[k]=values[k];
      matte=1;
    }
  }
  id=soft ? EXR_PDF_NONE : get(&r,image,"Mask");
  if(id!=EXR_PDF_NONE) {
    uint32_t at; v=exr_pdf_value_at(file,id); if(stencil) goto invalid;
    if(v->kind==EXR_PDF_STREAM) mask=id;
    else {
      if(v->kind!=EXR_PDF_ARRAY) goto invalid;
      at=v->first;
      for(k=0;k<2*channels;k++) {
        if(at==EXR_PDF_NONE || !integer(&r,resolve(&r,at),&key[k]) || key[k]>((1u<<bits)-1)) goto invalid;
        at=exr_pdf_value_at(file,at)->next;
      }
      if(at!=EXR_PDF_NONE) goto invalid;
      for(k=0;k<channels;k++) if(key[2*k]>key[2*k+1]) goto invalid;
      color_key=1;
    }
  }
  if(r.error.code!=EXR_OK || exr_pdf_image_payload(file,image,&bytes,&size,&codec,&parameters,&r.error)!=EXR_OK) goto done;
  /* PDF 1.7 sections 3.3.8/4.8.4: non-mask JPX ignores Decode, including Indexed. */
  id=codec==EXR_PDF_STREAM_JPX && !stencil ? EXR_PDF_NONE : get(&r,image,"Decode");
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
  if(r.error.code!=EXR_OK) goto done;
  row=((size_t)width*channels*bits+7)/8;
  owned=(size_t)width*height*4;
  if(inks && exr_pdf_colorspace_device(space)==EXR_PDF_DEVICE_CMYK) owned*=2;
  if(owned>(size_t)128*1024*1024-chain->live) { exr_fail(&r.error,EXR_LIMIT,"PDF image/mask pixels exceed 128 MiB"); goto done; }
  chain->live+=owned; charged=1;
  if(codec==EXR_PDF_STREAM_JPX) {
    size_t decoded_size=0,planes;exr_status status;
    if(stencil) goto invalid;
    if((size_t)width*height>((size_t)64*1024*1024)/sizeof(int32_t)/channels) {
      exr_fail(&r.error,EXR_LIMIT,"PDF JPX component planes exceed workspace budget");goto done;
    }
    planes=(size_t)width*height*channels*sizeof(int32_t);
    if(row>(size_t)64*1024*1024/height || row*height>(size_t)64*1024*1024-planes ||
       planes+row*height>(size_t)128*1024*1024-chain->live) {
      exr_fail(&r.error,EXR_LIMIT,"PDF JPX samples exceed payload or image-chain budget");goto done;
    }
    jpx_live=planes+row*height;chain->live+=jpx_live;
    status=exr_pdf_jpx_decode(bytes,size,width,height,channels,bits,(int)indexed,control,&jpx_samples,&decoded_size,&r.error);
    if(status!=EXR_OK) { if(r.error.code==EXR_OK) r.error.code=status;goto done; }
    if(decoded_size!=row*height) goto invalid;
    /* The adapter has destroyed its component planes before handing off bytes. */
    chain->live-=planes;jpx_live-=planes;
    bytes=jpx_samples;size=decoded_size;
  }
  if(inks && exr_pdf_colorspace_device(space)==EXR_PDF_DEVICE_CMYK) {
    inks->width=width;inks->height=height;inks->stride=width*4;inks->channels=4;
    inks->pixels=malloc((size_t)inks->stride*height);
    if(!inks->pixels) { exr_fail(&r.error,EXR_MEMORY,"PDF native ink allocation failed");goto done; }
  }
  if(codec==EXR_PDF_STREAM_JPEG) {
    exr_status status;
    id=get(&r,parameters,"ColorTransform"); if(r.error.code!=EXR_OK) goto done;
    if(stencil || indexed || bits!=8 || (channels!=1 && channels!=3 && channels!=4) || id!=EXR_PDF_NONE) {
      exr_fail(&r.error,EXR_FORMAT,"PDF JPEG stencil/indexed/ColorTransform override is unsupported"); goto done;
    }
    if(!jpeg_frame(bytes,size,width,height,channels)) goto invalid;
    status=channels==4 ? exr_jpeg_cmyk_decode(bytes,size,control,&bitmap,&r.error) : exr_image_decode(bytes,size,&bitmap,&r.error);
    if(status!=EXR_OK) { if(r.error.code==EXR_OK) r.error.code=status; goto done; }
    if(bitmap.width!=width || bitmap.height!=height) goto invalid;
  } else {
    if(row>SIZE_MAX/height || row*height!=size) goto invalid;
    bitmap.width=width; bitmap.height=height; bitmap.channels=4; bitmap.stride=width*4; bitmap.pixels=malloc((size_t)bitmap.stride*height);
    if(!bitmap.pixels) { exr_fail(&r.error,EXR_MEMORY,"PDF image pixel allocation failed"); goto done; }
  }
  /* ISO 32000-1 8.6.5.8: an image may override the graphics-state intent. */
  { uint32_t ri=EXR_PDF_NONE;
    if(exr_pdf_resolve(file,exr_pdf_get(file,image,"Intent"),&ri,&r.error)!=EXR_OK) goto done;
    if(ri!=EXR_PDF_NONE && exr_pdf_value_at(file,ri)->kind!=EXR_PDF_NULL) {
      const char *names[4]={"Perceptual","RelativeColorimetric","Saturation","AbsoluteColorimetric"}; unsigned n;int found=0;
      for(n=0;n<4;n++) if(image_name_is(file,ri,names[n])) { intent=n;found=1;break; }
      if(!found) { exr_fail(&r.error,EXR_FORMAT,"Invalid PDF image rendering intent"); goto done; }
    }
  }
  if(mask!=EXR_PDF_NONE) {
    unsigned mask_kind=0;
    if(decode_image(file,mask,resource_file,resources,0xffffffff,intent,&mask_texture,work,control,&r.error,chain,&mask_kind,NULL)!=EXR_OK) goto done;
    if((soft && mask_kind!=1) || (!soft && mask_kind!=0)) goto invalid;
  }
  if(matte && (!mask_texture || mask_texture->bitmap.width!=width || mask_texture->bitmap.height!=height || mask_texture->mask)) goto invalid;
  for(y=0;y<height;y++) {
    if(!(y&63) && exr_control_cancel(control,&r.error)!=EXR_OK) goto done;
    if(!exr_vector_work(work,(size_t)width*(stencil ? 1 : exr_pdf_colorspace_cost(space)))) { exr_fail(&r.error,EXR_LIMIT,"PDF image sample/function work exceeds budget"); goto done; }
    for(x=0;x<width;x++) {
      double values[EXR_PDF_MAX_COLORANTS]; unsigned char *p=bitmap.pixels+y*bitmap.stride+x*4; unsigned transparent=color_key;
      for(k=0;k<channels;k++) {
        unsigned raw=codec==EXR_PDF_STREAM_JPEG ? p[k] : sample(bytes+y*row,(x*channels+k)*bits,bits);
        double unit=(double)raw/((1u<<bits)-1);
        if(color_key && (raw<key[2*k] || raw>key[2*k+1])) transparent=0;
        values[k]=decode[2*k]+unit*(decode[2*k+1]-decode[2*k]);
      }
      if(matte) {
        double a=mask_texture->bitmap.pixels[y*mask_texture->bitmap.stride+x*4]/255.;
        for(k=0;k<channels;k++) values[k]=a>0 ? fmax(0,fmin(1,matte_rgb[k]+(values[k]-matte_rgb[k])/a)) : 0;
      }
      if(inks && inks->pixels) for(k=0;k<4;k++)
        inks->pixels[y*inks->stride+x*4+k]=(unsigned char)floor(fmax(0,fmin(1,values[k]))*255+.5);
      if(stencil) { p[0]=(unsigned char)(color>>24); p[1]=(unsigned char)(color>>16); p[2]=(unsigned char)(color>>8); p[3]=(unsigned char)floor((1-values[0])*255+.5); }
      else {
        double rgb[3]; if(exr_pdf_colorspace_rgb_intent(space,values,rgb,intent,&r.error)!=EXR_OK) goto done;
        for(k=0;k<3;k++) p[k]=(unsigned char)floor(rgb[k]*255+.5);
        p[3]=exr_pdf_colorspace_no_paint(space) ? 0 : 255;
        if(transparent) p[3]=0;
      }
    }
  }
  if(r.error.code==EXR_OK && exr_control_cancel(control,&r.error)==EXR_OK) {
    exr_vector_texture *texture=calloc(1,sizeof(*texture));
    if(!texture) { exr_fail(&r.error,EXR_MEMORY,"PDF image layer allocation failed"); goto done; }
    texture->bitmap=bitmap; texture->mask=mask_texture; texture->interpolate=interpolate!=0;
    texture->mask_mode=soft ? 1 : 2; texture->has_matte=0;
    *kind=stencil ? 0 : exr_pdf_colorspace_device(space) ? (unsigned)exr_pdf_colorspace_device(space) : 5; *out=texture; memset(&bitmap,0,sizeof(bitmap)); mask_texture=NULL; charged=0;
  }
  goto done;
invalid:
  if(r.error.code==EXR_OK) exr_fail(&r.error,EXR_FORMAT,"Invalid PDF image dictionary, samples or Decode array");
done:
  if(entered) chain->depth--;
  chain->live-=jpx_live;free(jpx_samples);
  if(charged) chain->live-=owned;
  release_texture(mask_texture,chain); free(bitmap.pixels); exr_pdf_colorspace_free(space);
  if(r.error.code!=EXR_OK && inks) { free(inks->pixels);memset(inks,0,sizeof(*inks)); }
  if(e) *e=r.error;
  return r.error.code;
}
exr_status exr_pdf_image_load(exr_pdf_file *file,uint32_t image,uint32_t resources,uint32_t color,
                               exr_vector_texture **out,size_t *work,const exr_control *control,exr_error *e) {
  return exr_pdf_image_load_from(file,image,file,resources,color,1,out,work,control,e);
}
exr_status exr_pdf_image_load_from(exr_pdf_file *file,uint32_t image,exr_pdf_file *resource_file,uint32_t resources,uint32_t color,
                               unsigned intent,exr_vector_texture **out,size_t *work,const exr_control *control,exr_error *e) {
  image_chain chain={0}; unsigned kind=0;
  return decode_image(file,image,resource_file,resources,color,intent,out,work,control,e,&chain,&kind,NULL);
}
exr_status exr_pdf_image_load_inks(exr_pdf_file *file,uint32_t image,exr_pdf_file *resource_file,uint32_t resources,uint32_t color,
  unsigned intent,exr_vector_texture **out,exr_bitmap *inks,size_t *work,const exr_control *control,exr_error *e) {
  image_chain chain={0};unsigned kind=0;
  return decode_image(file,image,resource_file,resources,color,intent,out,work,control,e,&chain,&kind,inks);
}
exr_status exr_pdf_image_decode(exr_pdf_file *file,uint32_t image,uint32_t resources,uint32_t color,
                                 exr_bitmap *out,int *interpolate,size_t *work,const exr_control *control,exr_error *e) {
  exr_vector_texture *texture=NULL; exr_status status; size_t local_work=0;
  if(out) memset(out,0,sizeof(*out));
  if(interpolate) *interpolate=0;
  if(!out || !interpolate) return exr_fail(e,EXR_ARGUMENT,"Missing PDF decoded image output");
  if(!work) work=&local_work;
  status=exr_pdf_image_load(file,image,resources,color,&texture,work,control,e);
  if(status!=EXR_OK) return status;
  if(!texture->mask) { *out=texture->bitmap; texture->bitmap.pixels=NULL; }
  else {
    double matrix[6]={texture->bitmap.width,0,0,texture->bitmap.height,0,0};
    *out=texture->bitmap; out->pixels=calloc((size_t)out->stride*out->height,1);
    if(!out->pixels) status=exr_fail(e,EXR_MEMORY,"PDF flattened image allocation failed");
    else status=exr_vector_texture_paint(out,texture,matrix,1,NULL,work,control,e);
  }
  if(status==EXR_OK) *interpolate=(int)texture->interpolate;
  else { free(out->pixels); memset(out,0,sizeof(*out)); }
  exr_pdf_image_release(texture); return status;
}
