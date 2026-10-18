/* SPDX-License-Identifier: GPL-3.0-only */
#include "internal.h"
typedef union {
  size_t size;
#ifdef _MSC_VER
  /* MSVC's C headers omit max_align_t; preserve its 16-byte malloc alignment. */
  __declspec(align(16)) unsigned char alignment[16];
#else
  max_align_t alignment;
#endif
} allocation;
#ifdef _MSC_VER
#define IMAGE_TLS __declspec(thread)
#else
#define IMAGE_TLS _Thread_local
#endif
static IMAGE_TLS size_t working_bytes;
static IMAGE_TLS int allocation_limited;
static IMAGE_TLS int allocation_failed;
static void *image_allocate(size_t n) {
  allocation *p;
  if (n > 128 * 1024 * 1024 - working_bytes) {
    allocation_limited = 1;
    return NULL;
  }
  p = malloc(sizeof(*p) + n);
  if (!p) {
    allocation_failed = 1;
    return NULL;
  }
  p->size = n;
  working_bytes += n;
  return p + 1;
}
static void image_free(void *memory) {
  allocation *p;
  if (!memory)
    return;
  p = (allocation *)memory - 1;
  working_bytes -= p->size;
  free(p);
}
static void *image_reallocate(void *memory, size_t n) {
  allocation *p, *next;
  size_t old;
  if (!memory)
    return image_allocate(n);
  p = (allocation *)memory - 1;
  old = p->size;
  if (n > 128 * 1024 * 1024 - (working_bytes - old)) {
    allocation_limited = 1;
    return NULL;
  }
  next = realloc(p, sizeof(*p) + n);
  if (!next) {
    allocation_failed = 1;
    return NULL;
  }
  next->size = n;
  working_bytes = working_bytes - old + n;
  return next + 1;
}
#define STBI_MALLOC image_allocate
#define STBI_REALLOC image_reallocate
#define STBI_FREE image_free
#define STB_IMAGE_IMPLEMENTATION
#define STB_IMAGE_STATIC
#define STBI_ONLY_PNG
#define STBI_ONLY_JPEG
#define STBI_NO_GIF
#define STBI_NO_STDIO
#define STBI_MAX_DIMENSIONS INT_MAX /* Dimensions are checked after reading the header. */
#include <stb_image.h>
/* Reuse the pinned stb entropy/IDCT and row resamplers. Its public JPEG loader
   converts CMYK to RGB too early for PDF Decode, color keys and ICCBased.
   Row reconstruction follows stb_image's load_jpeg_image (dual MIT/public domain). */
exr_status exr_jpeg_cmyk_decode(const void *data,size_t size,const exr_control *control,
                               exr_bitmap *out,exr_error *e) {
  stbi__context context; stbi__jpeg *jpeg=NULL; stbi__resample rows[4];
  unsigned char *planes[4]; uint32_t width,height,y,x; unsigned k;
  exr_status status;
  memset(out,0,sizeof(*out));
  status=exr_image_dimensions(data,size,&width,&height,e); if(status!=EXR_OK) return status;
  if(exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
  jpeg=calloc(1,sizeof(*jpeg)); if(!jpeg) return exr_fail(e,EXR_MEMORY,"JPEG component state allocation failed");
  stbi__start_mem(&context,data,(int)size); context.img_n=0; jpeg->s=&context; stbi__setup_jpeg(jpeg);
  status=EXR_FORMAT;
  if(!stbi__decode_jpeg_image(jpeg)) goto done;
  if(context.img_n!=4 || context.img_x!=width || context.img_y!=height ||
     (jpeg->app14_color_transform!=-1 && jpeg->app14_color_transform!=0 && jpeg->app14_color_transform!=2)) goto done;
  if(exr_control_cancel(control,e)!=EXR_OK) { status=EXR_CANCELLED; goto done; }
  for(k=0;k<4;k++) {
    stbi__resample *r=&rows[k];
    jpeg->img_comp[k].linebuf=image_allocate((size_t)width+3);
    if(!jpeg->img_comp[k].linebuf) goto done;
    r->hs=jpeg->img_h_max/jpeg->img_comp[k].h; r->vs=jpeg->img_v_max/jpeg->img_comp[k].v;
    r->ystep=r->vs/2; r->w_lores=((int)width+r->hs-1)/r->hs; r->ypos=0;
    r->line0=r->line1=jpeg->img_comp[k].data;
    if(r->hs==1 && r->vs==1) r->resample=resample_row_1;
    else if(r->hs==1 && r->vs==2) r->resample=stbi__resample_row_v_2;
    else if(r->hs==2 && r->vs==1) r->resample=stbi__resample_row_h_2;
    else if(r->hs==2 && r->vs==2) r->resample=jpeg->resample_row_hv_2_kernel;
    else r->resample=stbi__resample_row_generic;
  }
  out->pixels=malloc((size_t)width*height*4);
  if(!out->pixels) { status=EXR_MEMORY; goto done; }
  for(y=0;y<height;y++) {
    unsigned char *p=out->pixels+(size_t)y*width*4;
    if(!(y&63) && exr_control_cancel(control,e)!=EXR_OK) { status=EXR_CANCELLED; goto done; }
    for(k=0;k<4;k++) {
      stbi__resample *r=&rows[k]; int bottom=r->ystep>=r->vs/2;
      planes[k]=r->resample(jpeg->img_comp[k].linebuf,bottom ? r->line1 : r->line0,
                            bottom ? r->line0 : r->line1,r->w_lores,r->hs);
      if(++r->ystep>=r->vs) {
        r->ystep=0; r->line0=r->line1;
        if(++r->ypos<jpeg->img_comp[k].y) r->line1+=jpeg->img_comp[k].w2;
      }
    }
    if(jpeg->app14_color_transform==2) {
      jpeg->YCbCr_to_RGB_kernel(p,planes[0],planes[1],planes[2],(int)width,4);
      for(x=0;x<width;x++) { for(k=0;k<3;k++) p[x*4+k]=(unsigned char)(255-p[x*4+k]); p[x*4+3]=planes[3][x]; }
    } else for(x=0;x<width;x++) for(k=0;k<4;k++) p[x*4+k]=planes[k][x];
  }
  out->width=width; out->height=height; out->stride=width*4; out->channels=4; status=EXR_OK;
done:
  stbi__cleanup_jpeg(jpeg); free(jpeg);
  if(status!=EXR_OK) {
    free(out->pixels); memset(out,0,sizeof(*out));
    if(status!=EXR_CANCELLED) status=allocation_limited ? EXR_LIMIT : allocation_failed ? EXR_MEMORY : status;
    return exr_fail(e,status,"Four-component JPEG decoding failed");
  }
  return exr_fail(e,EXR_OK,"");
}
exr_status exr_image_dimensions(const void *data,size_t n,uint32_t *width,uint32_t *height,exr_error *e) {
  int w,h,channels;
  if(width) *width=0;
  if(height) *height=0;
  if(!data || !n || !width || !height) return exr_fail(e,EXR_ARGUMENT,"Invalid image header input/output");
  if(n>32*1024*1024) return exr_fail(e,EXR_LIMIT,"Encoded image exceeds 32 MiB");
  allocation_limited=allocation_failed=0;
  if(!stbi_info_from_memory(data,(int)n,&w,&h,&channels))
    return exr_fail(e,allocation_failed ? EXR_MEMORY : EXR_FORMAT,"Unsupported or damaged PNG/JPEG image header");
  if(w<=0 || h<=0 || w>8192 || h>8192 || (size_t)w*(size_t)h>16*1024*1024)
    return exr_fail(e,EXR_LIMIT,"Image exceeds 16 million pixels");
  *width=(uint32_t)w; *height=(uint32_t)h; return exr_fail(e,EXR_OK,"");
}
exr_status exr_image_decode(const void *data, size_t n, exr_bitmap *out, exr_error *e) {
  int w, h, channels; uint32_t width,height; exr_status status;
  unsigned char *pixels;
  if (!out)
    return exr_fail(e, EXR_ARGUMENT, "Missing image output");
  memset(out, 0, sizeof(*out));
  status=exr_image_dimensions(data,n,&width,&height,e); if(status!=EXR_OK) return status;
  w=(int)width;h=(int)height;
  pixels = stbi_load_from_memory(data, (int)n, &w, &h, &channels, 4);
  if (!pixels)
    return exr_fail(e,
                    allocation_limited  ? EXR_LIMIT
                    : allocation_failed ? EXR_MEMORY
                                        : EXR_FORMAT,
                    "PNG/JPEG decoding failed");
  out->pixels = malloc((size_t)w * (size_t)h * 4);
  if (!out->pixels) {
    stbi_image_free(pixels);
    return exr_fail(e, EXR_MEMORY, "Image pixel allocation failed");
  }
  memcpy(out->pixels, pixels, (size_t)w * (size_t)h * 4);
  stbi_image_free(pixels);
  out->width = (uint32_t)w;
  out->height = (uint32_t)h;
  out->stride = (uint32_t)w * 4;
  out->channels = 4;
  return EXR_OK;
}
