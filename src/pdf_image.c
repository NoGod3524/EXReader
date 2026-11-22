/* SPDX-License-Identifier: MIT */
/* The feature macro must precede every system header: including <stdio.h>
   first fixes glibc's feature set and leaves clock_gettime undeclared. */
#if !defined(_WIN32) && !defined(_POSIX_C_SOURCE)
#define _POSIX_C_SOURCE 200809L
#endif
#include <stdio.h>
#include "pdf_raster_internal.h"
#include "pdf_jpx_internal.h"
#include <errno.h>
#include <time.h>
#ifdef _WIN32
#include <windows.h>
#endif
typedef struct { exr_pdf_file *file; exr_error error; } image_reader;
typedef struct { uint32_t active[16]; size_t depth,live; } image_chain;
/* All PDF-owned textures have this private header, including mask children. */
typedef struct { exr_vector_texture texture;size_t refs;unsigned uncacheable,uses_intent; } pdf_texture;
static uint32_t get(image_reader *r,uint32_t dict,const char *key) {
  uint32_t id=EXR_PDF_NONE; if(r->error.code==EXR_OK) exr_pdf_resolve(r->file,exr_pdf_get(r->file,dict,key),&id,&r->error);
  if(id!=EXR_PDF_NONE && exr_pdf_value_at(r->file,id)->kind==EXR_PDF_NULL) id=EXR_PDF_NONE;
  return id;
}
static int integer(image_reader *r,uint32_t id,uint32_t *out) {
  const exr_pdf_value *v=exr_pdf_value_at(r->file,id);
  if(!v || v->kind!=EXR_PDF_INT || v->u.integer<0 || (uint64_t)v->u.integer>UINT32_MAX) return 0;
  *out=(uint32_t)v->u.integer; return 1;
}
static int image_boolean(image_reader *r,uint32_t id,int *out) {
  const exr_pdf_value *v=exr_pdf_value_at(r->file,id);
  if(!v) { *out=0; return 1; }
  if(v->kind!=EXR_PDF_BOOL) return 0;
  *out=v->u.integer!=0; return 1;
}
static uint32_t resolve(image_reader *r,uint32_t id) {
  uint32_t out=EXR_PDF_NONE; if(r->error.code==EXR_OK) exr_pdf_resolve(r->file,id,&out,&r->error); return out;
}
static unsigned sample_at(const unsigned char *bytes,size_t index,unsigned bits) {
  if(bits==8) return bytes[index];
  if(bits==16) return ((unsigned)bytes[index*2]<<8)|bytes[index*2+1];
  if(bits==4) return (bytes[index>>1]>>((1-(index&1))<<2))&0x0fu;
  if(bits==2) return (bytes[index>>2]>>((3-(index&3))<<1))&0x03u;
  return (bytes[index>>3]>>(7-(index&7)))&0x01u;
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
  if(--((pdf_texture *)texture)->refs) return;
  release_texture(texture->mask,chain);
  if(chain && texture->bitmap.pixels) chain->live-=(size_t)texture->bitmap.stride*texture->bitmap.height;
  free(texture->bitmap.pixels); free(texture);
}
void exr_pdf_image_release(exr_vector_texture *texture) { release_texture(texture,NULL); }
/* A decoded pixel is a pure function of its raw samples unless a matte mixes
   in the soft mask, so repeated sample tuples can reuse the converted bytes. */
typedef struct { uint64_t key; unsigned char valid,rgba[4],inks[4]; } pixel_memo;
#define PIXEL_MEMO_SLOTS 1024u
static pixel_memo *memo_slot(pixel_memo *memo,uint64_t packed) {
  return memo+(size_t)(((packed^(packed>>32))*UINT64_C(0x9E3779B97F4A7C15))>>54);
}
static exr_status convert_color_row(const exr_pdf_colorspace *space,const unsigned char *samples,unsigned char *pixels,
  size_t width,unsigned channels,unsigned bits,const double *decode,unsigned intent,pixel_memo *memo,exr_error *error) {
  double values[EXR_PDF_COLOR_BATCH*4],rgb[EXR_PDF_COLOR_BATCH*3];
  struct { unsigned char *pixel; pixel_memo *slot; uint64_t key; } pending[EXR_PDF_COLOR_BATCH];
  size_t x=0;
  while(x<width) {
    size_t count=0,i;
    for(;x<width && count<EXR_PDF_COLOR_BATCH;x++) {
      unsigned char *p=pixels+x*4;
      unsigned k,raws[4];uint64_t packed=0;pixel_memo *slot=NULL;
      for(k=0;k<channels;k++) raws[k]=samples ? sample_at(samples,x*channels+k,bits) : p[k];
      if(memo) {
        for(k=0;k<channels;k++) packed=(packed<<bits)|raws[k];
        slot=memo_slot(memo,packed);
        if(slot->valid && slot->key==packed) { memcpy(p,slot->rgba,4);continue; }
      }
      for(k=0;k<channels;k++) {
        double unit=(double)raws[k]/((1u<<bits)-1);
        values[count*channels+k]=decode[k*2]+unit*(decode[k*2+1]-decode[k*2]);
      }
      pending[count].pixel=p;pending[count].slot=slot;pending[count].key=packed;count++;
    }
    if(count) {
      exr_status status=exr_pdf_colorspace_rgb_batch(space,values,count,rgb,intent,error);
      if(status!=EXR_OK) return status;
      for(i=0;i<count;i++) {
        unsigned char *p=pending[i].pixel;pixel_memo *slot=pending[i].slot;unsigned k;
        for(k=0;k<3;k++) p[k]=(unsigned char)floor(rgb[i*3+k]*255+.5);
        p[3]=255;
        if(slot) { slot->key=pending[i].key;memcpy(slot->rgba,p,4);slot->valid=1; }
      }
    }
  }
  return EXR_OK;
}
static exr_status decode_image(exr_pdf_file *file,uint32_t image,exr_pdf_file *resource_file,uint32_t resources,uint32_t color,
                                 unsigned intent,exr_vector_texture **out,exr_raster_work *work,const exr_control *control,exr_error *e,
                                 image_chain *chain,unsigned *kind,exr_bitmap *inks) {
  image_reader r={0}; uint32_t width,height,bits=1,id,key[2*EXR_PDF_MAX_COLORANTS]={0}; unsigned channels=1,k,indexed=0,color_key=0;
  int stencil=0,interpolate=0; double decode[2*EXR_PDF_MAX_COLORANTS]={0,1}; exr_pdf_colorspace *space=NULL;
  const unsigned char *bytes; unsigned char *jpx_samples=NULL; size_t size,row,y,x,owned=0,jpx_live=0; exr_raster_work local_work={0}; exr_bitmap bitmap={0}; exr_vector_texture *mask_texture=NULL; const exr_pdf_value *v;
  uint32_t mask=EXR_PDF_NONE; unsigned soft=0,entered=0,charged=0,matte=0,own_intent=0; double matte_rgb[4]={0};
  exr_pdf_stream_codec codec=EXR_PDF_STREAM_RAW; uint32_t parameters=EXR_PDF_NONE; pixel_memo *memo=NULL;
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
  if(!image_boolean(&r,get(&r,image,"ImageMask"),&stencil) || !image_boolean(&r,get(&r,image,"Interpolate"),&interpolate)) goto invalid;
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
  if(mask!=EXR_PDF_NONE && exr_pdf_name_is(file,mask,"None")) mask=EXR_PDF_NONE;
  if(mask!=EXR_PDF_NONE && exr_pdf_diag_skip(EXR_DIAG_SOFTMASK)) {
    soft=1;
    mask=EXR_PDF_NONE;
  }
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
    status=channels==4 ? exr_jpeg_cmyk_decode(bytes,size,control,&bitmap,&r.error) : exr_image_decode_control(bytes,size,control,&bitmap,&r.error);
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
      own_intent=1;
      const char *names[4]={"Perceptual","RelativeColorimetric","Saturation","AbsoluteColorimetric"}; unsigned n;int found=0;
      for(n=0;n<4;n++) if(exr_pdf_name_is(file,ri,names[n])) { intent=n;found=1;break; }
      if(!found) { exr_fail(&r.error,EXR_FORMAT,"Invalid PDF image rendering intent"); goto done; }
    }
  }
  if(mask!=EXR_PDF_NONE) {
    unsigned mask_kind=0;
    if(decode_image(file,mask,resource_file,resources,0xffffffff,intent,&mask_texture,work,control,&r.error,chain,&mask_kind,NULL)!=EXR_OK) goto done;
    if((soft && mask_kind!=1) || (!soft && mask_kind!=0)) goto invalid;
  }
  if(matte && (!mask_texture || mask_texture->bitmap.width!=width || mask_texture->bitmap.height!=height || mask_texture->mask)) goto invalid;
  {
    exr_pdf_color_space dev_space=exr_pdf_colorspace_device(space);
    int device_8bit=(bits==8 && !stencil && !color_key && (dev_space==EXR_PDF_DEVICE_GRAY || dev_space==EXR_PDF_DEVICE_RGB));
    int jpeg_rgba=codec==EXR_PDF_STREAM_JPEG && device_8bit && !matte;
    int fast_device_8bit=codec!=EXR_PDF_STREAM_JPEG && device_8bit;
    size_t row_cost=(size_t)width*(stencil ? 1 : exr_pdf_colorspace_cost(space));
    unsigned char (*matte_lut)[3][256]=NULL;
    if(jpeg_rgba) for(k=0;k<channels;k++) if(decode[k*2]!=0 || decode[k*2+1]!=1) { jpeg_rgba=0;break; }
    if(fast_device_8bit && matte) matte_lut=malloc(256*sizeof(*matte_lut));
    if(jpeg_rgba) {
      /* The decoder has already produced the exact pixels. Masks are attached
         separately; sample work and cancellation still apply to each row. */
      for(y=0;y<height;y++) {
        if(!(y&63) && exr_control_cancel(control,&r.error)!=EXR_OK) goto done;
        if(!exr_vector_work(work,row_cost)) { exr_fail(&r.error,EXR_LIMIT,"PDF image sample/function work exceeds budget"); goto done; }
      }
    } else if(fast_device_8bit && !matte) {
      unsigned char lut[3][256];
      uint32_t gray_rgba[256];
      for(k=0;k<channels;k++) {
        unsigned raw;
        for(raw=0;raw<256;raw++) {
          double unit=(double)raw/255.;
          double val=decode[2*k]+unit*(decode[2*k+1]-decode[2*k]);
          val=fmax(0,fmin(1,val));
          lut[k][raw]=(unsigned char)floor(val*255+.5);
        }
      }
      if(channels==1) {
        unsigned raw;
        for(raw=0;raw<256;raw++) {
          unsigned char g=lut[0][raw],px[4]={g,g,g,255};
          memcpy(&gray_rgba[raw],px,4);
        }
      }
      for(y=0;y<height;y++) {
        const unsigned char *s=bytes+y*row;
        unsigned char *p=bitmap.pixels+y*bitmap.stride;
        if(!(y&63) && exr_control_cancel(control,&r.error)!=EXR_OK) goto done;
        if(!exr_vector_work(work,row_cost)) { exr_fail(&r.error,EXR_LIMIT,"PDF image sample/function work exceeds budget"); goto done; }
        if(channels==1) {
          for(x=0;x<width;x++) memcpy(p+x*4,&gray_rgba[s[x]],4);
        } else {
          for(x=0;x<width;x++,s+=3,p+=4) {
            p[0]=lut[0][s[0]]; p[1]=lut[1][s[1]]; p[2]=lut[2][s[2]]; p[3]=255;
          }
        }
      }
    } else if(fast_device_8bit && matte && matte_lut) {
      unsigned char matte_ready[256]={0};
      uint32_t opaque_black;
      { unsigned char z[4]={0,0,0,255}; memcpy(&opaque_black,z,4); }
      for(y=0;y<height;y++) {
        const unsigned char *s=bytes+y*row;
        const unsigned char *m=mask_texture->bitmap.pixels+y*mask_texture->bitmap.stride;
        unsigned char *p=bitmap.pixels+y*bitmap.stride;
        unsigned last_ma=256;
        unsigned char (*mlut)[256]=NULL;
        if(!(y&63) && exr_control_cancel(control,&r.error)!=EXR_OK) { free(matte_lut); goto done; }
        if(!exr_vector_work(work,row_cost)) { free(matte_lut); exr_fail(&r.error,EXR_LIMIT,"PDF image sample/function work exceeds budget"); goto done; }
        if(channels==3) {
          for(x=0;x<width;x++,s+=3,m+=4,p+=4) {
            unsigned ma=m[0];
            if(!ma) { memcpy(p,&opaque_black,4); continue; }
            if(ma!=last_ma) {
              if(!matte_ready[ma]) {
                double a=ma/255.;
                for(k=0;k<3;k++) {
                  unsigned raw;
                  for(raw=0;raw<256;raw++) {
                    double unit=(double)raw/255.;
                    double val=decode[2*k]+unit*(decode[2*k+1]-decode[2*k]);
                    val=fmax(0,fmin(1,matte_rgb[k]+(val-matte_rgb[k])/a));
                    matte_lut[ma][k][raw]=(unsigned char)floor(val*255+.5);
                  }
                }
                matte_ready[ma]=1;
              }
              last_ma=ma;
              mlut=matte_lut[ma];
            }
            p[0]=mlut[0][s[0]]; p[1]=mlut[1][s[1]]; p[2]=mlut[2][s[2]]; p[3]=255;
          }
        } else {
          for(x=0;x<width;x++,s++,m+=4,p+=4) {
            unsigned ma=m[0],g;
            if(!ma) { memcpy(p,&opaque_black,4); continue; }
            if(ma!=last_ma) {
              if(!matte_ready[ma]) {
                double a=ma/255.; unsigned raw;
                for(raw=0;raw<256;raw++) {
                  double unit=(double)raw/255.;
                  double val=decode[0]+unit*(decode[1]-decode[0]);
                  val=fmax(0,fmin(1,matte_rgb[0]+(val-matte_rgb[0])/a));
                  matte_lut[ma][0][raw]=(unsigned char)floor(val*255+.5);
                }
                matte_ready[ma]=1;
              }
              last_ma=ma;
              mlut=matte_lut[ma];
            }
            g=mlut[0][s[0]];
            p[0]=(unsigned char)g; p[1]=(unsigned char)g; p[2]=(unsigned char)g; p[3]=255;
          }
        }
      }
      free(matte_lut);
    } else {
      int batch=!stencil && !matte && !color_key && (!inks || !inks->pixels) && exr_pdf_colorspace_can_batch(space);
      if(!matte && channels*bits<=64) memo=calloc(PIXEL_MEMO_SLOTS,sizeof(*memo)); /* optional: NULL just disables reuse */
      for(y=0;y<height;y++) {
        if(!(y&63) && exr_control_cancel(control,&r.error)!=EXR_OK) goto done;
        if(!exr_vector_work(work,row_cost)) { exr_fail(&r.error,EXR_LIMIT,"PDF image sample/function work exceeds budget"); goto done; }
        if(batch) {
          if(convert_color_row(space,codec==EXR_PDF_STREAM_JPEG ? NULL : bytes+y*row,bitmap.pixels+y*bitmap.stride,
            width,channels,bits,decode,intent,memo,&r.error)!=EXR_OK) goto done;
          continue;
        }
        for(x=0;x<width;x++) {
          double values[EXR_PDF_MAX_COLORANTS]; unsigned char *p=bitmap.pixels+y*bitmap.stride+x*4; unsigned transparent=color_key;
          unsigned raws[EXR_PDF_MAX_COLORANTS]; pixel_memo *slot=NULL;
          for(k=0;k<channels;k++) raws[k]=codec==EXR_PDF_STREAM_JPEG ? p[k] : sample_at(bytes+y*row,(size_t)x*channels+k,bits);
          if(memo) {
            uint64_t packed=0;
            for(k=0;k<channels;k++) packed=(packed<<bits)|raws[k];
            slot=memo_slot(memo,packed);
            if(slot->valid && slot->key==packed) {
              memcpy(p,slot->rgba,4);
              if(inks && inks->pixels) memcpy(inks->pixels+y*inks->stride+x*4,slot->inks,4);
              continue;
            }
            slot->valid=0; slot->key=packed;
          }
          for(k=0;k<channels;k++) {
            unsigned raw=raws[k];
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
          if(slot) {
            memcpy(slot->rgba,p,4);
            if(inks && inks->pixels) memcpy(slot->inks,inks->pixels+y*inks->stride+x*4,4);
            slot->valid=1;
          }
        }
      }
    }
  }
  if(r.error.code==EXR_OK && exr_control_cancel(control,&r.error)==EXR_OK) {
    pdf_texture *owned_texture=calloc(1,sizeof(*owned_texture));
    exr_vector_texture *texture=(exr_vector_texture *)owned_texture;
    if(!texture) { exr_fail(&r.error,EXR_MEMORY,"PDF image layer allocation failed"); goto done; }
    /* Matte was reversed using this object's decoded mask. A local intent
       replaces the caller's intent for both the image and its descendants. */
    owned_texture->uses_intent=!own_intent && (exr_pdf_colorspace_uses_intent(space) ||
      (mask_texture && ((pdf_texture *)mask_texture)->uses_intent));
    owned_texture->refs=1;owned_texture->uncacheable=(channels*bits>64 ? 2u : 0u)|
      (!exr_pdf_colorspace_cacheable(space) ? 4u : 0u)|(stencil ? 8u : 0u)|
      /* A child stencil is decoded with fixed white, independent of fill color. */
      (mask_texture ? ((pdf_texture *)mask_texture)->uncacheable&~8u : 0u);
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
  release_texture(mask_texture,chain); free(bitmap.pixels); free(memo); exr_pdf_colorspace_free(space);
  if(r.error.code!=EXR_OK && inks) { free(inks->pixels);memset(inks,0,sizeof(*inks)); }
  if(e) *e=r.error;
  return r.error.code;
}
exr_status exr_pdf_image_load(exr_pdf_file *file,uint32_t image,uint32_t resources,uint32_t color,
                               exr_vector_texture **out,exr_raster_work *work,const exr_control *control,exr_error *e) {
  return exr_pdf_image_load_from(file,image,file,resources,color,1,out,work,control,e);
}
typedef struct {
  uint32_t image,length;unsigned native,intent;
  exr_vector_texture *texture;exr_bitmap inks;size_t bytes,work,used;
} image_cache_entry;
typedef struct {
  image_cache_entry entries[128];size_t byte_limit,entry_limit,clock;
  unsigned profile;
  exr_pdf_image_cache_stats stats;
} image_cache;
static void cache_evict(image_cache *cache,image_cache_entry *entry) {
  cache->stats.bytes-=entry->bytes;cache->stats.entries--;
  exr_pdf_image_release(entry->texture);free(entry->inks.pixels);memset(entry,0,sizeof(*entry));
}
static void cache_free(void *data) {
  image_cache *cache=data;size_t i;if(!cache) return;
  for(i=0;i<128;i++) if(cache->entries[i].texture) cache_evict(cache,cache->entries+i);
  free(cache);
}
static image_cache *cache_get(exr_pdf_file *file) {
  void **slot=exr_pdf_image_cache_slot(file,cache_free);image_cache *cache;
  if(!slot) return NULL;
  if(!*slot) {
    const char *limit=getenv("EXR_PDF_IMAGE_CACHE_BYTES");
    const char *profile=getenv("EXR_PDF_IMAGE_PROFILE");
    cache=calloc(1,sizeof(*cache));if(!cache) return NULL;
    cache->byte_limit=(size_t)64*1024*1024;cache->entry_limit=128;
    cache->profile=profile && !strcmp(profile,"1");
    if(limit && *limit>='0' && *limit<='9') {
      char *end;unsigned long long bytes;errno=0;bytes=strtoull(limit,&end,10);
      if(!errno && !*end && bytes<=SIZE_MAX) cache->byte_limit=(size_t)bytes;
    }
    *slot=cache;
  }
  return *slot;
}
void exr_pdf_image_cache_limits(exr_pdf_file *file,size_t bytes,size_t entries) {
  image_cache *cache=cache_get(file);size_t i;if(!cache) return;
  for(i=0;i<128;i++) if(cache->entries[i].texture) cache_evict(cache,cache->entries+i);
  cache->byte_limit=bytes;cache->entry_limit=entries<128 ? entries : 128;
}
void exr_pdf_image_cache_report(exr_pdf_file *file,exr_pdf_image_cache_stats *out) {
  image_cache *cache=cache_get(file);if(out) *out=cache ? cache->stats : (exr_pdf_image_cache_stats){0};
}
static size_t texture_bytes(const exr_vector_texture *texture) {
  return texture ? sizeof(pdf_texture)+(size_t)texture->bitmap.stride*texture->bitmap.height+texture_bytes(texture->mask) : 0;
}
static int bitmap_copy(const exr_bitmap *source,exr_bitmap *out) {
  *out=*source;
  if(source->pixels) {
    size_t bytes=(size_t)source->stride*source->height;
    out->pixels=malloc(bytes);if(!out->pixels) return 0;
    memcpy(out->pixels,source->pixels,bytes);
  }
  return 1;
}
static double image_time_ms(void) {
#ifdef _WIN32
  LARGE_INTEGER t,frequency;QueryPerformanceCounter(&t);QueryPerformanceFrequency(&frequency);
  return (double)t.QuadPart*1000/(double)frequency.QuadPart;
#else
  struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (double)t.tv_sec*1000+t.tv_nsec/1e6;
#endif
}
/* Ablation EXR_ATTRIBUTION_SKIP=image-decode: an opaque placeholder with the
   image's size, /Interpolate and /SMask structure, built without reading the
   payload, so the paint path runs unchanged and decode cost is t(full)-t(this). */
static uint32_t diag_dict_value(exr_pdf_file *file,uint32_t image,const char *key) {
  uint32_t id=EXR_PDF_NONE; exr_error ignored={0};
  if(exr_pdf_resolve(file,exr_pdf_get(file,image,key),&id,&ignored)!=EXR_OK) return EXR_PDF_NONE;
  return id;
}
static exr_vector_texture *diag_placeholder(exr_pdf_file *file,uint32_t image,unsigned depth) {
  const exr_pdf_value *w=exr_pdf_value_at(file,diag_dict_value(file,image,"Width")),*h=exr_pdf_value_at(file,diag_dict_value(file,image,"Height"));
  const exr_pdf_value *interpolate=exr_pdf_value_at(file,diag_dict_value(file,image,"Interpolate"));
  uint32_t smask=diag_dict_value(file,image,"SMask"); pdf_texture *t;
  if(!w || !h || w->kind!=EXR_PDF_INT || h->kind!=EXR_PDF_INT || w->u.integer<1 || h->u.integer<1 || w->u.integer>8192 || h->u.integer>8192) return NULL;
  if(!(t=calloc(1,sizeof(*t)))) return NULL;
  t->refs=1; t->texture.bitmap.width=(uint32_t)w->u.integer; t->texture.bitmap.height=(uint32_t)h->u.integer;
  t->texture.bitmap.channels=4; t->texture.bitmap.stride=t->texture.bitmap.width*4;
  t->texture.interpolate=interpolate && interpolate->kind==EXR_PDF_BOOL && interpolate->u.integer;
  t->texture.bitmap.pixels=malloc((size_t)t->texture.bitmap.stride*t->texture.bitmap.height);
  if(!t->texture.bitmap.pixels) { free(t); return NULL; }
  memset(t->texture.bitmap.pixels,255,(size_t)t->texture.bitmap.stride*t->texture.bitmap.height);
  if(!depth && smask!=EXR_PDF_NONE && exr_pdf_value_at(file,smask) && exr_pdf_value_at(file,smask)->kind==EXR_PDF_STREAM) {
    t->texture.mask=diag_placeholder(file,smask,1); t->texture.mask_mode=1;
  }
  return &t->texture;
}
static exr_status load_cached(exr_pdf_file *file,uint32_t image,exr_pdf_file *resource_file,uint32_t resources,uint32_t color,
  unsigned intent,exr_vector_texture **out,exr_bitmap *inks,exr_raster_work *work,const exr_control *control,exr_error *e) {
  image_chain chain={0};unsigned kind=0;size_t before,i,bytes;exr_raster_work local_work={0};exr_status status;
  double started=0;
  image_cache *cache=NULL;image_cache_entry *entry=NULL;
  uint32_t length=0,length_id;const exr_pdf_value *length_value;
  if(out) *out=NULL;
  if(inks) memset(inks,0,sizeof(*inks));
  if(!file || !out) return exr_fail(e,EXR_ARGUMENT,"Missing PDF image input/output");
  if(exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
  if(exr_pdf_resolve(file,image,&image,e)!=EXR_OK) return e ? e->code : EXR_FORMAT;
  if(!work) work=&local_work;
  /* Inline operand arenas borrow a different resource file and are deliberately
     uncached. Parsed stream value IDs are unique and stable within this file. */
  if(file==resource_file) cache=cache_get(file);
  if(cache) {
    if(exr_pdf_resolve(file,exr_pdf_get(file,image,"Length"),&length_id,e)!=EXR_OK) return e ? e->code : EXR_FORMAT;
    length_value=exr_pdf_value_at(file,length_id);
    if(!length_value || length_value->kind!=EXR_PDF_INT || length_value->u.integer<0 || (uint64_t)length_value->u.integer>UINT32_MAX) cache=NULL;
    else length=(uint32_t)length_value->u.integer;
  }
  if(cache && cache->byte_limit && cache->entry_limit) {
    for(i=0;i<128;i++) {
      image_cache_entry *candidate=cache->entries+i;
      if(candidate->texture && candidate->image==image && candidate->length==length && candidate->native==(inks!=NULL) &&
         (!((pdf_texture *)candidate->texture)->uses_intent || candidate->intent==intent)) {
        if(!exr_vector_work(work,candidate->work)) return exr_fail(e,EXR_LIMIT,"PDF image sample/function work exceeds budget");
        if(inks && !bitmap_copy(&candidate->inks,inks)) return exr_fail(e,EXR_MEMORY,"PDF cached ink allocation failed");
        candidate->used=++cache->clock;cache->stats.hits++;
        ((pdf_texture *)candidate->texture)->refs++;*out=candidate->texture;
        return exr_fail(e,EXR_OK,"");
      }
    }
  }
  if(cache) cache->stats.misses++;
  { if(exr_pdf_diag_skip(EXR_DIAG_IMAGE_DECODE) && !inks) {
      *out=diag_placeholder(file,image,0);
      return *out ? exr_fail(e,EXR_OK,"") : exr_fail(e,EXR_UNSUPPORTED,"image-decode ablation placeholder unavailable");
    } }
  before=work->used;
  if(cache && cache->profile) started=image_time_ms();
  status=decode_image(file,image,resource_file,resources,color,intent,out,work,control,e,&chain,&kind,inks);
  if(cache && cache->profile) cache->stats.decode_ms+=image_time_ms()-started;
  if(cache && cache->profile && getenv("EXR_ATTRIBUTION_TRACE")) { const exr_vector_texture *t=status==EXR_OK ? *out : NULL;
    fprintf(stderr,"IMGDEC %u %.6f %u %u %d\n",(unsigned)image,image_time_ms()-started,t ? (unsigned)t->bitmap.width : 0u,t ? (unsigned)t->bitmap.height : 0u,t && t->mask ? 1 : 0); }
  if(status==EXR_OK && cache) {
    unsigned skip=((pdf_texture *)*out)->uncacheable;
    if(skip&2) cache->stats.wide_bypasses++;
    if(skip&12) cache->stats.state_bypasses++;
  }
  if(status!=EXR_OK || !cache || !cache->byte_limit || !cache->entry_limit || ((pdf_texture *)*out)->uncacheable) return status;
  bytes=texture_bytes(*out)+(inks && inks->pixels ? (size_t)inks->stride*inks->height : 0);
  if(bytes>cache->byte_limit) return status;
  while(cache->stats.bytes>cache->byte_limit-bytes || cache->stats.entries>=cache->entry_limit) {
    image_cache_entry *oldest=NULL;
    for(i=0;i<128;i++) if(cache->entries[i].texture && (!oldest || cache->entries[i].used<oldest->used)) oldest=cache->entries+i;
    cache_evict(cache,oldest);cache->stats.evictions++;
  }
  for(i=0;i<128;i++) if(!cache->entries[i].texture) { entry=cache->entries+i;break; }
  if(inks && !bitmap_copy(inks,&entry->inks)) return status; /* optional cache */
  entry->image=image;entry->length=length;entry->native=inks!=NULL;entry->intent=intent;
  entry->texture=*out;((pdf_texture *)*out)->refs++;
  entry->bytes=bytes;entry->work=work->used-before;entry->used=++cache->clock;
  cache->stats.bytes+=bytes;cache->stats.entries++;
  return status;
}
exr_status exr_pdf_image_load_from(exr_pdf_file *file,uint32_t image,exr_pdf_file *resource_file,uint32_t resources,uint32_t color,
                               unsigned intent,exr_vector_texture **out,exr_raster_work *work,const exr_control *control,exr_error *e) {
  return load_cached(file,image,resource_file,resources,color,intent,out,NULL,work,control,e);
}
exr_status exr_pdf_image_load_inks(exr_pdf_file *file,uint32_t image,exr_pdf_file *resource_file,uint32_t resources,uint32_t color,
  unsigned intent,exr_vector_texture **out,exr_bitmap *inks,exr_raster_work *work,const exr_control *control,exr_error *e) {
  return load_cached(file,image,resource_file,resources,color,intent,out,inks,work,control,e);
}
exr_status exr_pdf_image_decode(exr_pdf_file *file,uint32_t image,uint32_t resources,uint32_t color,
                                 exr_bitmap *out,int *interpolate,exr_raster_work *work,const exr_control *control,exr_error *e) {
  exr_vector_texture *texture=NULL; exr_status status; exr_raster_work local_work={0};
  if(out) memset(out,0,sizeof(*out));
  if(interpolate) *interpolate=0;
  if(!out || !interpolate) return exr_fail(e,EXR_ARGUMENT,"Missing PDF decoded image output");
  if(!work) work=&local_work;
  status=exr_pdf_image_load(file,image,resources,color,&texture,work,control,e);
  if(status!=EXR_OK) return status;
  if(!texture->mask) {
    if(((pdf_texture *)texture)->refs==1) { *out=texture->bitmap;texture->bitmap.pixels=NULL; }
    else if(!bitmap_copy(&texture->bitmap,out)) status=exr_fail(e,EXR_MEMORY,"PDF decoded image copy allocation failed");
  }
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
