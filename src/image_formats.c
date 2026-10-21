/* SPDX-License-Identifier: MIT */
/* Optional CBZ/graphics image codecs. The always-built PNG/JPEG/BMP/GIF path
   lives in images.c; this file adds multi-page and animated probes plus the
   optional WebP, TIFF and AVIF decoders. All decoders share the same dimension,
   expanded-byte and page limits and zero their output on failure. */
#include "graphics_internal.h"
#include <stb_image.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#if defined(EXR_ENABLE_IMAGE_WEBP)
#include <webp/decode.h>
#include <webp/demux.h>
#endif
#if defined(EXR_ENABLE_IMAGE_TIFF)
#include <tiffio.h>
#endif
#if defined(EXR_ENABLE_IMAGE_AVIF)
#include <avif/avif.h>
#endif

#define EXR_IMAGE_MAX_DIMENSION 8192u
#define EXR_IMAGE_MAX_PIXELS ((size_t)16 * 1024 * 1024)
#define EXR_IMAGE_MAX_PAGES 4096u
#define EXR_IMAGE_MAX_EXPANDED ((size_t)256 * 1024 * 1024)
#define EXR_IMAGE_GIF_MAX_EXPANDED ((size_t)96 * 1024 * 1024)

typedef enum {
  EXR_IMAGE_UNKNOWN = 0, EXR_IMAGE_PNG, EXR_IMAGE_JPEG, EXR_IMAGE_GIF,
  EXR_IMAGE_BMP, EXR_IMAGE_WEBP, EXR_IMAGE_TIFF, EXR_IMAGE_AVIF
} image_kind;

static uint32_t le16(const unsigned char *p) { return (uint32_t)p[0] | ((uint32_t)p[1] << 8); }
#if defined(EXR_ENABLE_IMAGE_WEBP)
static uint32_t le32(const unsigned char *p) { return le16(p) | (le16(p + 2) << 16); }
#endif

static image_kind detect(const void *data,size_t size) {
  const unsigned char *p = data;
  size_t i;
  if(!p || !size) return EXR_IMAGE_UNKNOWN;
  if(size >= 8 && !memcmp(p,"\x89PNG\r\n\x1a\n",8)) return EXR_IMAGE_PNG;
  if(size >= 3 && p[0] == 0xff && p[1] == 0xd8 && p[2] == 0xff) return EXR_IMAGE_JPEG;
  if(size >= 6 && (!memcmp(p,"GIF87a",6) || !memcmp(p,"GIF89a",6))) return EXR_IMAGE_GIF;
  if(size >= 14 && p[0] == 'B' && p[1] == 'M') return EXR_IMAGE_BMP;
  if(size >= 12 && !memcmp(p,"RIFF",4) && !memcmp(p + 8,"WEBP",4)) return EXR_IMAGE_WEBP;
  if(size >= 4 && ((p[0] == 'I' && p[1] == 'I' && p[2] == 42 && p[3] == 0) ||
                   (p[0] == 'M' && p[1] == 'M' && p[2] == 0 && p[3] == 42) ||
                   (p[0] == 'I' && p[1] == 'I' && p[2] == 43 && p[3] == 0) ||
                   (p[0] == 'M' && p[1] == 'M' && p[2] == 0 && p[3] == 43))) return EXR_IMAGE_TIFF;
  if(size >= 12 && !memcmp(p + 4,"ftyp",4)) {
    size_t limit = size < 64 ? size : 64;
    for(i = 8; i + 4 <= limit; i += 4)
      if(!memcmp(p + i,"avif",4) || !memcmp(p + i,"avis",4)) return EXR_IMAGE_AVIF;
  }
  return EXR_IMAGE_UNKNOWN;
}
#if !defined(EXR_ENABLE_IMAGE_WEBP) || !defined(EXR_ENABLE_IMAGE_TIFF) || !defined(EXR_ENABLE_IMAGE_AVIF)
static exr_status unavailable(const char *name,exr_error *e) {
  return exr_fail(e,EXR_UNSUPPORTED,"%s image decoding is not enabled in this build",name);
}
#endif
static void clear_bitmap(exr_bitmap *bitmap) {
  if(!bitmap) return;
  free(bitmap->pixels);
  memset(bitmap,0,sizeof(*bitmap));
}
static exr_status image_limits(uint32_t width,uint32_t height,size_t pages,exr_error *e) {
  if(!width || !height || width > EXR_IMAGE_MAX_DIMENSION || height > EXR_IMAGE_MAX_DIMENSION ||
     (size_t)width * height > EXR_IMAGE_MAX_PIXELS)
    return exr_fail(e,EXR_LIMIT,"Image exceeds 16 million pixels or 8192 dimensions");
  if(!pages) return exr_fail(e,EXR_FORMAT,"Image contains no pages");
  if(pages > EXR_IMAGE_MAX_PAGES) return exr_fail(e,EXR_LIMIT,"Animated/multi-page image exceeds 4096 pages");
  return EXR_OK;
}

/* ---- GIF structure walk (dimensions and frame count without decoding) ---- */
static exr_status gif_probe(const unsigned char *p,size_t size,uint32_t *width,uint32_t *height,size_t *pages,exr_error *e) {
  size_t at = 13, frames = 0;
  unsigned packed;
  if(size < 13 || (memcmp(p,"GIF87a",6) && memcmp(p,"GIF89a",6))) return exr_fail(e,EXR_FORMAT,"Invalid GIF header");
  *width = le16(p + 6); *height = le16(p + 8); packed = p[10];
  if(packed & 0x80) at += (size_t)3 * ((size_t)2 << (packed & 7));
  if(at > size) return exr_fail(e,EXR_FORMAT,"Truncated GIF color table");
  while(at < size) {
    unsigned block = p[at++];
    if(block == 0x3b) break;
    if(block == 0x21) {
      if(at >= size) return exr_fail(e,EXR_FORMAT,"Truncated GIF extension");
      at++;
      while(at < size) {
        unsigned n = p[at++];
        if(!n) break;
        if(n > size - at) return exr_fail(e,EXR_FORMAT,"Truncated GIF extension data");
        at += n;
      }
      if(at > size) return exr_fail(e,EXR_FORMAT,"Truncated GIF extension data");
    } else if(block == 0x2c) {
      if(size - at < 9) return exr_fail(e,EXR_FORMAT,"Truncated GIF image descriptor");
      packed = p[at + 8];
      at += 9;
      if(packed & 0x80) at += (size_t)3 * ((size_t)2 << (packed & 7));
      if(at >= size) return exr_fail(e,EXR_FORMAT,"Truncated GIF local color table");
      at++; /* LZW minimum code size */
      while(at < size) {
        unsigned n = p[at++];
        if(!n) break;
        if(n > size - at) return exr_fail(e,EXR_FORMAT,"Truncated GIF image data");
        at += n;
      }
      frames++;
      if(frames > EXR_IMAGE_MAX_PAGES) return exr_fail(e,EXR_LIMIT,"GIF exceeds 4096 frames");
    } else return exr_fail(e,EXR_FORMAT,"Invalid GIF block");
  }
  if(!frames) return exr_fail(e,EXR_FORMAT,"GIF contains no frames");
  *pages = frames;
  return image_limits(*width,*height,*pages,e);
}
static exr_status gif_decode(const unsigned char *data,size_t size,size_t page,const exr_control *control,exr_bitmap *out,exr_error *e) {
  int w = 0,h = 0,frames = 0,comp = 0;
  int *delays = NULL;
  unsigned char *all;
  size_t bytes,row;
  exr_status status;
  if(page > EXR_IMAGE_MAX_PAGES) return exr_fail(e,EXR_LIMIT,"GIF frame index exceeds 4096");
  all = stbi_load_gif_from_memory(data,(int)size,&delays,&w,&h,&frames,&comp,4);
  if(!all) {
    stbi_image_free(delays);
    return exr_fail(e,EXR_FORMAT,"GIF decoding failed");
  }
  status = image_limits((uint32_t)w,(uint32_t)h,(size_t)frames,e);
  if(status == EXR_OK && page >= (size_t)frames) status = exr_fail(e,EXR_LIMIT,"GIF page index exceeds frame count");
  bytes = (size_t)w * (size_t)h * 4;
  if(status == EXR_OK && (bytes > EXR_IMAGE_GIF_MAX_EXPANDED || bytes > EXR_IMAGE_GIF_MAX_EXPANDED / (size_t)frames))
    status = exr_fail(e,EXR_LIMIT,"GIF expanded frames exceed the 96 MiB decode budget");
  if(status == EXR_OK) {
    out->pixels = malloc(bytes);
    if(!out->pixels) status = exr_fail(e,EXR_MEMORY,"GIF pixel allocation failed");
  }
  if(status == EXR_OK) {
    out->width = (uint32_t)w; out->height = (uint32_t)h; out->stride = (uint32_t)w * 4; out->channels = 4;
    for(row = 0; row < (size_t)h; row++) {
      if(!(row & 31) && exr_control_cancel(control,e) != EXR_OK) { status = EXR_CANCELLED; break; }
      memcpy(out->pixels + row * out->stride,all + page * bytes + row * out->stride,out->stride);
    }
  }
  stbi_image_free(all); stbi_image_free(delays);
  if(status != EXR_OK) clear_bitmap(out);
  return status;
}

#if defined(EXR_ENABLE_IMAGE_WEBP)
static exr_status webp_probe(const unsigned char *data,size_t size,uint32_t *width,uint32_t *height,size_t *pages,exr_error *e) {
  int w = 0,h = 0; size_t at;
  if(!WebPGetInfo(data,size,&w,&h) || w <= 0 || h <= 0) return exr_fail(e,EXR_FORMAT,"Invalid WebP header");
  *pages = 1;
  for(at = 12; at + 8 <= size; ) {
    uint32_t n = le32(data + at + 4);
    if(!memcmp(data + at,"ANMF",4)) { *pages = 0; break; }
    if(n > size - at - 8) break;
    at += 8 + n + (n & 1u);
  }
  if(!*pages) {
    WebPData bitstream = {data,size}; WebPAnimDecoderOptions options; WebPAnimInfo info; WebPAnimDecoder *decoder;
    if(!WebPAnimDecoderOptionsInit(&options)) return exr_fail(e,EXR_MEMORY,"WebP decoder option allocation failed");
    options.color_mode = MODE_RGBA; options.use_threads = 0;
    decoder = WebPAnimDecoderNew(&bitstream,&options);
    if(!decoder) return exr_fail(e,EXR_FORMAT,"Invalid WebP animation");
    if(!WebPAnimDecoderGetInfo(decoder,&info)) { WebPAnimDecoderDelete(decoder); return exr_fail(e,EXR_FORMAT,"Invalid WebP animation info"); }
    *pages = info.frame_count ? info.frame_count : 1;
    w = (int)info.canvas_width; h = (int)info.canvas_height;
    WebPAnimDecoderDelete(decoder);
  }
  *width = (uint32_t)w; *height = (uint32_t)h;
  return image_limits(*width,*height,*pages,e);
}
static exr_status webp_decode(const unsigned char *data,size_t size,size_t page,const exr_control *control,exr_bitmap *out,exr_error *e) {
  uint32_t width = 0,height = 0; size_t pages = 0,bytes; exr_status status;
  status = webp_probe(data,size,&width,&height,&pages,e);
  if(status != EXR_OK) return status;
  if(page >= pages) return exr_fail(e,EXR_LIMIT,"WebP page index exceeds frame count");
  bytes = (size_t)width * height * 4;
  if(pages > 1 && (bytes > EXR_IMAGE_MAX_EXPANDED / pages))
    return exr_fail(e,EXR_LIMIT,"WebP animation expand exceeds the decode budget");
  out->pixels = malloc(bytes);
  if(!out->pixels) return exr_fail(e,EXR_MEMORY,"WebP pixel allocation failed");
  out->width = width; out->height = height; out->stride = width * 4; out->channels = 4;
  if(pages == 1) {
    if(!WebPDecodeRGBAInto(data,size,out->pixels,(int)bytes,(int)out->stride)) { clear_bitmap(out); return exr_fail(e,EXR_FORMAT,"WebP decoding failed"); }
  } else {
    WebPData bitstream = {data,size}; WebPAnimDecoderOptions options; WebPAnimDecoder *decoder; uint8_t *buffer = NULL; int timestamp = 0; size_t i;
    if(!WebPAnimDecoderOptionsInit(&options)) { clear_bitmap(out); return exr_fail(e,EXR_MEMORY,"WebP decoder option allocation failed"); }
    options.color_mode = MODE_RGBA; options.use_threads = 0;
    decoder = WebPAnimDecoderNew(&bitstream,&options);
    if(!decoder) { clear_bitmap(out); return exr_fail(e,EXR_FORMAT,"Invalid WebP animation"); }
    for(i = 0; i <= page; i++) {
      if(exr_control_cancel(control,e) != EXR_OK) { status = EXR_CANCELLED; break; }
      if(!WebPAnimDecoderGetNext(decoder,&buffer,&timestamp)) { status = exr_fail(e,EXR_FORMAT,"WebP animation frame decoding failed"); break; }
    }
    if(status == EXR_OK) memcpy(out->pixels,buffer,bytes);
    WebPAnimDecoderDelete(decoder);
    if(status != EXR_OK) { clear_bitmap(out); return status; }
  }
  if(exr_control_cancel(control,e) != EXR_OK) { clear_bitmap(out); return EXR_CANCELLED; }
  return EXR_OK;
}
#endif

#if defined(EXR_ENABLE_IMAGE_TIFF)
typedef struct { const unsigned char *data; size_t size,at; } tiff_memory;
static tmsize_t tiff_read(thandle_t handle,void *buffer,tmsize_t size) {
  tiff_memory *m = handle; size_t n;
  if(!m || size < 0 || m->at >= m->size) return 0;
  n = (size_t)size < m->size - m->at ? (size_t)size : m->size - m->at;
  memcpy(buffer,m->data + m->at,n); m->at += n; return (tmsize_t)n;
}
static tmsize_t tiff_write(thandle_t handle,void *buffer,tmsize_t size) { (void)handle;(void)buffer;(void)size;return -1; }
static toff_t tiff_seek(thandle_t handle,toff_t offset,int whence) {
  tiff_memory *m = handle; uint64_t next;
  if(!m) return (toff_t)-1;
  if(whence == SEEK_SET) next = offset;
  else if(whence == SEEK_CUR) next = (uint64_t)m->at + offset;
  else if(whence == SEEK_END) next = (uint64_t)m->size + offset;
  else return (toff_t)-1;
  if(next > m->size) return (toff_t)-1;
  m->at = (size_t)next; return (toff_t)next;
}
static int tiff_close(thandle_t handle) { (void)handle; return 0; }
static toff_t tiff_size(thandle_t handle) { tiff_memory *m = handle; return m ? (toff_t)m->size : 0; }
static int tiff_map(thandle_t handle,void **base,toff_t *size) {
  tiff_memory *m = handle; if(!m) return 0; *base = (void *)m->data; *size = (toff_t)m->size; return 1;
}
static void tiff_unmap(thandle_t handle,void *base,toff_t size) { (void)handle;(void)base;(void)size; }
static TIFF *tiff_open(const unsigned char *data,size_t size,tiff_memory *memory,exr_error *e) {
  TIFFOpenOptions *options; TIFF *tif;
  options = TIFFOpenOptionsAlloc();
  if(!options) { exr_fail(e,EXR_MEMORY,"TIFF option allocation failed"); return NULL; }
  TIFFOpenOptionsSetMaxSingleMemAlloc(options,(tmsize_t)64 * 1024 * 1024);
  TIFFOpenOptionsSetMaxCumulatedMemAlloc(options,(tmsize_t)128 * 1024 * 1024);
  memory->data = data; memory->size = size; memory->at = 0;
  tif = TIFFClientOpenExt("memory","r",(thandle_t)memory,tiff_read,tiff_write,tiff_seek,tiff_close,tiff_size,tiff_map,tiff_unmap,options);
  TIFFOpenOptionsFree(options);
  if(!tif) exr_fail(e,EXR_FORMAT,"Invalid TIFF header or directory");
  return tif;
}
static exr_status tiff_probe(const unsigned char *data,size_t size,uint32_t *width,uint32_t *height,size_t *pages,exr_error *e) {
  tiff_memory memory; TIFF *tif = tiff_open(data,size,&memory,e); tdir_t count,i;
  if(!tif) return e ? e->code : EXR_FORMAT;
  count = TIFFNumberOfDirectories(tif);
  if(!count) { TIFFClose(tif); return exr_fail(e,EXR_FORMAT,"TIFF contains no directories"); }
  if(count > EXR_IMAGE_MAX_PAGES) { TIFFClose(tif); return exr_fail(e,EXR_LIMIT,"TIFF exceeds 4096 pages"); }
  for(i = 0; i < count; i++) {
    uint32_t w = 0,h = 0;
    if(!TIFFSetDirectory(tif,i) || !TIFFGetField(tif,TIFFTAG_IMAGEWIDTH,&w) || !TIFFGetField(tif,TIFFTAG_IMAGELENGTH,&h)) {
      TIFFClose(tif); return exr_fail(e,EXR_FORMAT,"Invalid TIFF directory dimensions");
    }
    if(image_limits(w,h,1,e) != EXR_OK) { TIFFClose(tif); return e ? e->code : EXR_LIMIT; }
    if(i == 0) { *width = w; *height = h; }
  }
  TIFFClose(tif); *pages = count;
  return image_limits(*width,*height,*pages,e);
}
static exr_status tiff_decode(const unsigned char *data,size_t size,size_t page,const exr_control *control,exr_bitmap *out,exr_error *e) {
  tiff_memory memory; TIFF *tif; uint32_t w = 0,h = 0; size_t bytes; exr_status status = EXR_OK;
  if(page > EXR_IMAGE_MAX_PAGES) return exr_fail(e,EXR_LIMIT,"TIFF page index exceeds 4096");
  tif = tiff_open(data,size,&memory,e);
  if(!tif) return e ? e->code : EXR_FORMAT;
  if(!TIFFSetDirectory(tif,(tdir_t)page) || !TIFFGetField(tif,TIFFTAG_IMAGEWIDTH,&w) || !TIFFGetField(tif,TIFFTAG_IMAGELENGTH,&h)) {
    TIFFClose(tif); return exr_fail(e,EXR_LIMIT,"TIFF page index exceeds directory count or has invalid dimensions");
  }
  status = image_limits(w,h,1,e);
  if(status == EXR_OK && exr_control_cancel(control,e) != EXR_OK) status = EXR_CANCELLED;
  bytes = (size_t)w * h * 4;
  if(status == EXR_OK) {
    out->pixels = malloc(bytes);
    if(!out->pixels) status = exr_fail(e,EXR_MEMORY,"TIFF pixel allocation failed");
    else { out->width = w; out->height = h; out->stride = w * 4; out->channels = 4; }
  }
  if(status == EXR_OK && !TIFFReadRGBAImageOriented(tif,w,h,(uint32_t *)out->pixels,ORIENTATION_TOPLEFT,0))
    status = exr_fail(e,EXR_FORMAT,"TIFF decoding failed");
  /* libtiff returns associated-alpha ABGR words. Public bitmaps and the
     shared image compositor use straight RGBA, independent of host endian. */
  for(size_t y=0;status==EXR_OK && y<h;y++) {
    if(!(y&31) && exr_control_cancel(control,e)!=EXR_OK) { status=EXR_CANCELLED;break; }
    for(size_t x=0;x<w;x++) {
      size_t at=y*w+x;uint32_t sample=((uint32_t *)out->pixels)[at];
      unsigned alpha=TIFFGetA(sample),rgb[3]={TIFFGetR(sample),TIFFGetG(sample),TIFFGetB(sample)};
      unsigned char *pixel=out->pixels+at*4;
      for(unsigned k=0;k<3;k++) {
        unsigned value=alpha ? (rgb[k]*255+alpha/2)/alpha : 0;
        pixel[k]=(unsigned char)(value>255 ? 255 : value);
      }
      pixel[3]=(unsigned char)alpha;
    }
  }
  if(status == EXR_OK && exr_control_cancel(control,e) != EXR_OK) status = EXR_CANCELLED;
  TIFFClose(tif);
  if(status != EXR_OK) clear_bitmap(out);
  return status;
}
#endif

#if defined(EXR_ENABLE_IMAGE_AVIF)
static avifDecoder *avif_open(const unsigned char *data,size_t size,exr_error *e) {
  avifDecoder *decoder = avifDecoderCreate();
  avifResult result;
  if(!decoder) { exr_fail(e,EXR_MEMORY,"AVIF decoder allocation failed"); return NULL; }
  decoder->maxThreads = 1;
  decoder->imageSizeLimit = (uint32_t)EXR_IMAGE_MAX_PIXELS;
  decoder->imageDimensionLimit = EXR_IMAGE_MAX_DIMENSION;
  decoder->strictFlags = AVIF_STRICT_DISABLED;
  result = avifDecoderSetIOMemory(decoder,data,size);
  if(result == AVIF_RESULT_OK) result = avifDecoderParse(decoder);
  if(result != AVIF_RESULT_OK) {
    exr_fail(e,EXR_FORMAT,"AVIF parse failed: %s",avifResultToString(result));
    avifDecoderDestroy(decoder); return NULL;
  }
  return decoder;
}
static exr_status avif_probe(const unsigned char *data,size_t size,uint32_t *width,uint32_t *height,size_t *pages,exr_error *e) {
  avifDecoder *decoder = avif_open(data,size,e);
  if(!decoder) return e ? e->code : EXR_FORMAT;
  if(!decoder->imageCount) { avifDecoderDestroy(decoder); return exr_fail(e,EXR_FORMAT,"AVIF contains no frames"); }
  *width = decoder->image->width; *height = decoder->image->height; *pages = decoder->imageCount;
  avifDecoderDestroy(decoder);
  return image_limits(*width,*height,*pages,e);
}
static exr_status avif_decode(const unsigned char *data,size_t size,size_t page,const exr_control *control,exr_bitmap *out,exr_error *e) {
  avifDecoder *decoder; avifRGBImage rgb; avifResult result; size_t i; uint32_t w,h; exr_status status;
  if(page > EXR_IMAGE_MAX_PAGES) return exr_fail(e,EXR_LIMIT,"AVIF page index exceeds 4096");
  decoder = avif_open(data,size,e);
  if(!decoder) return e ? e->code : EXR_FORMAT;
  if(page >= (size_t)decoder->imageCount) { avifDecoderDestroy(decoder); return exr_fail(e,EXR_LIMIT,"AVIF page index exceeds frame count"); }
  result = AVIF_RESULT_OK;
  for(i = 0; i <= page; i++) {
    if(exr_control_cancel(control,e) != EXR_OK) { status = EXR_CANCELLED; goto done; }
    result = avifDecoderNextImage(decoder);
    if(result != AVIF_RESULT_OK) break;
  }
  if(result != AVIF_RESULT_OK) { status = exr_fail(e,EXR_FORMAT,"AVIF decoding failed: %s",avifResultToString(result)); goto done; }
  w = decoder->image->width; h = decoder->image->height;
  status = image_limits(w,h,1,e); if(status != EXR_OK) goto done;
  out->pixels = malloc((size_t)w * h * 4);
  if(!out->pixels) { status = exr_fail(e,EXR_MEMORY,"AVIF pixel allocation failed"); goto done; }
  out->width = w; out->height = h; out->stride = w * 4; out->channels = 4;
  avifRGBImageSetDefaults(&rgb,decoder->image);
  rgb.width = w; rgb.height = h; rgb.depth = 8; rgb.format = AVIF_RGB_FORMAT_RGBA;
  rgb.pixels = out->pixels; rgb.rowBytes = out->stride;
  result = avifImageYUVToRGB(decoder->image,&rgb);
  if(result != AVIF_RESULT_OK) status = exr_fail(e,EXR_FORMAT,"AVIF color conversion failed: %s",avifResultToString(result));
  if(status == EXR_OK && exr_control_cancel(control,e) != EXR_OK) status = EXR_CANCELLED;
done:
  avifDecoderDestroy(decoder);
  if(status != EXR_OK) clear_bitmap(out);
  return status;
}
#endif

static exr_status probe_page(const unsigned char *data,size_t size,uint32_t *width,uint32_t *height,size_t *pages,exr_error *e) {
  image_kind kind;
  if(!data || !size || !width || !height || !pages) return exr_fail(e,EXR_ARGUMENT,"Invalid image header input/output");
  *width = *height = 0; *pages = 0;
  kind = detect(data,size);
  switch(kind) {
    case EXR_IMAGE_PNG:
    case EXR_IMAGE_JPEG:
    case EXR_IMAGE_BMP: {
      int w = 0,h = 0,channels = 0;
      if(!stbi_info_from_memory(data,(int)size,&w,&h,&channels) || w <= 0 || h <= 0)
        return exr_fail(e,EXR_FORMAT,"Unsupported or damaged image header");
      *width = (uint32_t)w; *height = (uint32_t)h; *pages = 1;
      return image_limits(*width,*height,*pages,e);
    }
    case EXR_IMAGE_GIF: return gif_probe(data,size,width,height,pages,e);
    case EXR_IMAGE_WEBP:
#if defined(EXR_ENABLE_IMAGE_WEBP)
      return webp_probe(data,size,width,height,pages,e);
#else
      return unavailable("WebP",e);
#endif
    case EXR_IMAGE_TIFF:
#if defined(EXR_ENABLE_IMAGE_TIFF)
      return tiff_probe(data,size,width,height,pages,e);
#else
      return unavailable("TIFF",e);
#endif
    case EXR_IMAGE_AVIF:
#if defined(EXR_ENABLE_IMAGE_AVIF)
      return avif_probe(data,size,width,height,pages,e);
#else
      return unavailable("AVIF",e);
#endif
    default:
      return exr_fail(e,EXR_FORMAT,"Unsupported image format");
  }
}

exr_status exr_image_page_count(const void *data,size_t size,size_t *count,exr_error *e) {
  uint32_t w,h;
  if(!count) return exr_fail(e,EXR_ARGUMENT,"Missing image page count output");
  *count = 0;
  return probe_page(data,size,&w,&h,count,e);
}
exr_status exr_image_page_dimensions(const void *data,size_t size,size_t page,uint32_t *width,uint32_t *height,exr_error *e) {
  size_t pages;
  exr_status status;
  if(!width || !height) return exr_fail(e,EXR_ARGUMENT,"Missing image dimension output");
  *width = *height = 0;
  status = probe_page(data,size,width,height,&pages,e);
  if(status != EXR_OK) return status;
  if(page >= pages) { *width = *height = 0; return exr_fail(e,EXR_LIMIT,"Image page index exceeds page count"); }
  if(page) {
    /* Re-probe walking directories/frames for codecs whose pages can differ. */
    uint32_t w = 0,h = 0; size_t n = 0;
#if defined(EXR_ENABLE_IMAGE_TIFF)
    if(detect(data,size) == EXR_IMAGE_TIFF) {
      tiff_memory memory; TIFF *tif = tiff_open(data,size,&memory,e);
      if(!tif) return e ? e->code : EXR_FORMAT;
      if(!TIFFSetDirectory(tif,(tdir_t)page) || !TIFFGetField(tif,TIFFTAG_IMAGEWIDTH,&w) || !TIFFGetField(tif,TIFFTAG_IMAGELENGTH,&h)) {
        TIFFClose(tif); return exr_fail(e,EXR_LIMIT,"TIFF page index exceeds directory count");
      }
      TIFFClose(tif); *width = w; *height = h; return image_limits(w,h,1,e);
    }
#endif
    status = probe_page(data,size,&w,&h,&n,e);
    if(status == EXR_OK && page < n) { *width = w; *height = h; }
  }
  return status;
}
exr_status exr_image_decode_page_control(const void *data,size_t size,size_t page,const exr_control *control,exr_bitmap *out,exr_error *e) {
  uint32_t width = 0,height = 0; size_t pages = 0; exr_status status; image_kind kind;
  if(!out) return exr_fail(e,EXR_ARGUMENT,"Missing image output");
  memset(out,0,sizeof(*out));
  status = probe_page(data,size,&width,&height,&pages,e);
  if(status != EXR_OK) return status;
  if(page >= pages) return exr_fail(e,EXR_LIMIT,"Image page index exceeds page count");
  if(exr_control_cancel(control,e) != EXR_OK) return EXR_CANCELLED;
  kind = detect(data,size);
  /* Reject a multi-frame expansion before the codec allocates its frame
     array. GIF compositing needs every preceding frame; WebP animation keeps
     one canvas but walks preceding frames. */
  if(kind == EXR_IMAGE_GIF && pages > 1 && (size_t)width * height * 4 > EXR_IMAGE_GIF_MAX_EXPANDED / pages)
    return exr_fail(e,EXR_LIMIT,"GIF expanded frames exceed the 96 MiB decode budget");
  if(kind == EXR_IMAGE_WEBP && pages > 1 && (size_t)width * height * 4 > EXR_IMAGE_MAX_EXPANDED / pages)
    return exr_fail(e,EXR_LIMIT,"WebP expanded frames exceed the decode budget");
  switch(kind) {
    case EXR_IMAGE_PNG:
    case EXR_IMAGE_JPEG:
    case EXR_IMAGE_BMP: {
      int w = (int)width,h = (int)height,channels = 0;
      unsigned char *pixels = stbi_load_from_memory(data,(int)size,&w,&h,&channels,4);
      if(!pixels) return exr_fail(e,EXR_FORMAT,"Image decoding failed");
      if((size_t)w * h * 4 > EXR_IMAGE_MAX_EXPANDED) { stbi_image_free(pixels); return exr_fail(e,EXR_LIMIT,"Image expand exceeds decode budget"); }
      out->pixels = malloc((size_t)w * h * 4);
      if(!out->pixels) { stbi_image_free(pixels); return exr_fail(e,EXR_MEMORY,"Image pixel allocation failed"); }
      memcpy(out->pixels,pixels,(size_t)w * h * 4);
      stbi_image_free(pixels);
      out->width = (uint32_t)w; out->height = (uint32_t)h; out->stride = (uint32_t)w * 4; out->channels = 4;
      return EXR_OK;
    }
    case EXR_IMAGE_GIF: return gif_decode(data,size,page,control,out,e);
    case EXR_IMAGE_WEBP:
#if defined(EXR_ENABLE_IMAGE_WEBP)
      return webp_decode(data,size,page,control,out,e);
#else
      return unavailable("WebP",e);
#endif
    case EXR_IMAGE_TIFF:
#if defined(EXR_ENABLE_IMAGE_TIFF)
      return tiff_decode(data,size,page,control,out,e);
#else
      return unavailable("TIFF",e);
#endif
    case EXR_IMAGE_AVIF:
#if defined(EXR_ENABLE_IMAGE_AVIF)
      return avif_decode(data,size,page,control,out,e);
#else
      return unavailable("AVIF",e);
#endif
    default: return exr_fail(e,EXR_FORMAT,"Unsupported image format");
  }
}
exr_status exr_image_decode_page(const void *data,size_t size,size_t page,exr_bitmap *out,exr_error *e) {
  return exr_image_decode_page_control(data,size,page,NULL,out,e);
}
exr_status exr_image_decode_control(const void *data,size_t size,const exr_control *control,exr_bitmap *out,exr_error *e) {
  return exr_image_decode_page_control(data,size,0,control,out,e);
}
