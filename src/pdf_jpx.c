/* SPDX-License-Identifier: MIT */
#include "base_internal.h"
#include "pdf_jpx_internal.h"
#include <openjpeg.h>

#define JPX_PAYLOAD ((size_t)64*1024*1024)
#define JPX_MEMORY ((size_t)64*1024*1024)
typedef struct {
  const unsigned char *data;
  size_t size,offset;
  const exr_control *control;
  int cancelled,invalid;
} jpx_input;
static int jpx_cancel(jpx_input *s) {
  if(s->control && s->control->cancelled && s->control->cancelled(s->control->context)) s->cancelled=1;
  return s->cancelled;
}
static OPJ_SIZE_T jpx_read(void *dst,OPJ_SIZE_T count,void *context) {
  jpx_input *s=(jpx_input *)context;
  size_t n;
  if(jpx_cancel(s) || s->offset==s->size) return (OPJ_SIZE_T)-1;
  n=s->size-s->offset;
  if(count<n) n=count;
  memcpy(dst,s->data+s->offset,n);s->offset+=n;
  return n;
}
static OPJ_OFF_T jpx_skip(OPJ_OFF_T count,void *context) {
  jpx_input *s=(jpx_input *)context;
  if(jpx_cancel(s)) return -1;
  if(count<0) {
    /* Avoid negating the minimum signed offset. */
    uint64_t n=(uint64_t)(-(count+1))+1;
    if(n>s->offset) { s->invalid=1;return -1; }
    s->offset-=(size_t)n;
  } else {
    if((uint64_t)count>s->size-s->offset) { s->invalid=1;return -1; }
    s->offset+=(size_t)count;
  }
  return count;
}
static OPJ_BOOL jpx_seek(OPJ_OFF_T offset,void *context) {
  jpx_input *s=(jpx_input *)context;
  if(jpx_cancel(s)) return OPJ_FALSE;
  if(offset<0 || (uint64_t)offset>s->size) { s->invalid=1;return OPJ_FALSE; }
  s->offset=(size_t)offset;return OPJ_TRUE;
}
static void jpx_message(const char *message,void *context) { (void)message;(void)context; }
static uint32_t jpx_u32(const unsigned char *p) {
  return (uint32_t)p[0]<<24|(uint32_t)p[1]<<16|(uint32_t)p[2]<<8|p[3];
}
/* Inspect JP2 channel metadata before OpenJPEG can expand a palette or apply
   embedded alpha. The explicit PDF colour space owns component interpretation. */
static int jpx_boxes(const unsigned char *p,size_t size,int indexed,int nested) {
  size_t at=0;
  while(at<size) {
    uint64_t length;
    uint32_t type;
    size_t header=8;
    if(size-at<8) return 0;
    length=jpx_u32(p+at);type=jpx_u32(p+at+4);
    if(length==1) {
      if(size-at<16) return 0;
      length=(uint64_t)jpx_u32(p+at+8)<<32|jpx_u32(p+at+12);header=16;
    } else if(!length) length=size-at;
    if(length<header || length>size-at) return 0;
    if(type==0x63646566u) return 0; /* cdef, including associated alpha */
    if(!indexed && (type==0x70636c72u || type==0x636d6170u)) return 0;
    if(type==0x6a703268u) {
      if(nested || !jpx_boxes(p+at+header,(size_t)length-header,indexed,1)) return 0;
    }
    at+=(size_t)length;
  }
  return 1;
}
exr_status exr_pdf_jpx_decode(const void *data,size_t size,unsigned width,
  unsigned height,unsigned components,unsigned bits,int indexed,
  const exr_control *control,unsigned char **samples,size_t *sample_size,exr_error *e) {
  static const unsigned char signature[12]={0,0,0,12,0x6a,0x50,0x20,0x20,13,10,0x87,10};
  const unsigned char *bytes=(const unsigned char *)data;
  jpx_input input;
  opj_dparameters_t params;
  opj_codec_t *codec=NULL;
  opj_stream_t *stream=NULL;
  opj_image_t *image=NULL;
  unsigned char *packed=NULL;
  size_t pixels,row,total,planes,y,x;
  unsigned c;
  int jp2;
  exr_status status=EXR_FORMAT;
  if(samples) *samples=NULL;
  if(sample_size) *sample_size=0;
  if(!samples || !sample_size || !data || !size || !width || !height || !components ||
     (bits!=1 && bits!=2 && bits!=4 && bits!=8 && bits!=16))
    return exr_fail(e,EXR_ARGUMENT,"Invalid JPX decode arguments");
  if((status=exr_control_cancel(control,e))!=EXR_OK) return status;
  if(size>JPX_PAYLOAD || width>8192 || height>8192 || components>32 ||
     (size_t)width*height>16u*1024u*1024u)
    return exr_fail(e,EXR_LIMIT,"JPX image exceeds decode budget");
  pixels=(size_t)width*height;
  row=((size_t)width*components*bits+7)/8;
  total=row*height;planes=pixels*components*sizeof(OPJ_INT32);
  if(total>JPX_PAYLOAD || planes>JPX_MEMORY-total)
    return exr_fail(e,EXR_LIMIT,"JPX component planes exceed decode budget");
  jp2=size>=12 && !memcmp(bytes,signature,12);
  if(!jp2 && !(size>=4 && bytes[0]==255 && bytes[1]==0x4f && bytes[2]==255 && bytes[3]==0x51))
    return exr_fail(e,EXR_FORMAT,"Invalid JPX stream signature");
  if(jp2 && !jpx_boxes(bytes,size,indexed,0))
    return exr_fail(e,EXR_UNSUPPORTED,"Unsupported JPX channel metadata");
  memset(&input,0,sizeof(input));input.data=bytes;input.size=size;input.control=control;
  codec=opj_create_decompress(jp2 ? OPJ_CODEC_JP2 : OPJ_CODEC_J2K);
  stream=opj_stream_create(4096,OPJ_TRUE);
  if(!codec || !stream) { status=EXR_MEMORY;goto done; }
  opj_set_error_handler(codec,jpx_message,NULL);
  opj_set_warning_handler(codec,jpx_message,NULL);
  opj_set_info_handler(codec,jpx_message,NULL);
  opj_set_default_decoder_parameters(&params);
  params.flags|=OPJ_DPARAMETERS_IGNORE_PCLR_CMAP_CDEF_FLAG;
  if(!opj_setup_decoder(codec,&params) || !opj_decoder_set_strict_mode(codec,OPJ_TRUE) ||
     !opj_codec_set_threads(codec,1)) { status=EXR_UNSUPPORTED;goto done; }
  opj_stream_set_user_data(stream,&input,NULL);
  opj_stream_set_user_data_length(stream,size);
  opj_stream_set_read_function(stream,jpx_read);
  opj_stream_set_skip_function(stream,jpx_skip);
  opj_stream_set_seek_function(stream,jpx_seek);
  status=EXR_FORMAT;
  if(!opj_read_header(stream,codec,&image)) goto done;
  if(!image || image->x0 || image->y0 || image->x1!=width || image->y1!=height || image->numcomps!=components) goto done;
  for(c=0;c<components;c++) {
    opj_image_comp_t *comp=&image->comps[c];
    if(comp->dx!=1 || comp->dy!=1 || comp->x0 || comp->y0 || comp->w!=width || comp->h!=height ||
       comp->prec!=bits || comp->sgnd || comp->alpha || comp->factor) {
      status=EXR_UNSUPPORTED;goto done;
    }
  }
  /* All component dimensions and allocation products are bounded before decode. */
  if(jpx_cancel(&input) || !opj_decode(codec,stream,image) || !opj_end_decompress(codec,stream) || input.invalid) goto done;
  packed=(unsigned char *)calloc(total,1);
  if(!packed) { status=EXR_MEMORY;goto done; }
  for(y=0;y<height;y++) {
    size_t bit=y*row*8;
    if(jpx_cancel(&input)) goto done;
    for(x=0;x<width;x++) for(c=0;c<components;c++) {
      OPJ_INT32 value;
      unsigned b;
      if(!image->comps[c].data) goto done;
      value=image->comps[c].data[y*width+x];
      if(value<0 || (uint32_t)value>=((uint32_t)1<<bits)) goto done;
      for(b=bits;b;b--,bit++) packed[bit>>3]|=(unsigned char)(((uint32_t)value>>(b-1)&1)<<(7-(bit&7)));
    }
  }
  *samples=packed;*sample_size=total;packed=NULL;status=EXR_OK;
done:
  free(packed);
  if(image) opj_image_destroy(image);
  if(stream) opj_stream_destroy(stream);
  if(codec) opj_destroy_codec(codec);
  if(input.cancelled) status=EXR_CANCELLED;
  if(status!=EXR_OK) return exr_fail(e,status,"JPX image decode failed");
  return EXR_OK;
}
