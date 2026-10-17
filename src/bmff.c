/* SPDX-License-Identifier: GPL-3.0-only */
#include "bmff_internal.h"
uint32_t exr_bmff_be16(const unsigned char *p) { return (uint32_t)p[0]<<8|p[1]; }
uint32_t exr_bmff_be32(const unsigned char *p) { return exr_bmff_be16(p)<<16|exr_bmff_be16(p+2); }
uint64_t exr_bmff_be64(const unsigned char *p) { return (uint64_t)exr_bmff_be32(p)<<32|exr_bmff_be32(p+4); }
exr_status exr_bmff_fail(exr_bmff_reader *io,const char *message) { return exr_fail(io->error,EXR_FORMAT,"%s",message); }
exr_status exr_bmff_read(exr_bmff_reader *io,uint64_t at,void *out,size_t size) {
  size_t done=0;
  if(at>io->source->size || size>io->source->size-at) return exr_bmff_fail(io,"ISO-BMFF field exceeds source");
  if(size>io->limit-io->bytes) return exr_fail(io->error,EXR_LIMIT,"ISO-BMFF operation exceeds read budget");
  io->bytes+=size;
  while(done<size) {
    size_t got; exr_status status=exr_control_cancel(io->control,io->error); if(status!=EXR_OK) return status;
    got=io->source->read_at(io->source->context,at+done,(unsigned char *)out+done,size-done);
    if(!got || got>size-done) return exr_fail(io->error,EXR_IO,"Invalid or short ISO-BMFF source read");
    done+=got;
  }
  return EXR_OK;
}
exr_status exr_bmff_at(exr_bmff_reader *io,uint64_t at,uint64_t end,exr_bmff_box *box) {
  unsigned char bytes[16]; uint64_t size; unsigned header=8; exr_status status;
  if(++io->boxes>65536) return exr_fail(io->error,EXR_LIMIT,"ISO-BMFF box count exceeds 65536");
  if(at>end || end-at<8) return exr_bmff_fail(io,"Truncated ISO-BMFF box header");
  status=exr_bmff_read(io,at,bytes,8); if(status!=EXR_OK) return status;
  size=exr_bmff_be32(bytes); box->type=exr_bmff_be32(bytes+4);
  if(size==1) { if(end-at<16) return exr_bmff_fail(io,"Truncated ISO-BMFF extended box"); status=exr_bmff_read(io,at+8,bytes+8,8); if(status!=EXR_OK) return status; size=exr_bmff_be64(bytes+8); header=16; }
  else if(!size) size=end-at;
  if(box->type==EXR_BMFF_TYPE('u','u','i','d')) header+=16;
  if(size<header || size>end-at) return exr_bmff_fail(io,"Invalid ISO-BMFF box size");
  box->data=at+header; box->end=at+size; return EXR_OK;
}
exr_status exr_bmff_child(exr_bmff_reader *io,const exr_bmff_box *parent,uint32_t type,int required,exr_bmff_box *out) {
  uint64_t at=parent->data; memset(out,0,sizeof(*out));
  while(at<parent->end) {
    exr_bmff_box child; exr_status status=exr_bmff_at(io,at,parent->end,&child); if(status!=EXR_OK) return status;
    if(child.type==type) { if(out->end) return exr_bmff_fail(io,"Duplicate ISO-BMFF structural box"); *out=child; }
    at=child.end;
  }
  return required && !out->end ? exr_bmff_fail(io,"Missing ISO-BMFF structural box") : EXR_OK;
}
exr_status exr_bmff_header(exr_bmff_reader *io,const exr_bmff_box *box,void *bytes,size_t size) {
  if(size>box->end-box->data) return exr_bmff_fail(io,"Truncated ISO-BMFF box fields");
  return exr_bmff_read(io,box->data,bytes,size);
}
exr_status exr_bmff_time(exr_bmff_reader *io,const exr_bmff_box *box,uint32_t *scale,uint64_t *duration) {
  unsigned char b[32]; exr_status status=exr_bmff_header(io,box,b,4); if(status!=EXR_OK) return status;
  if(b[1] || b[2] || b[3] || b[0]>1) return exr_bmff_fail(io,"Unsupported ISO-BMFF time header version/flags");
  status=exr_bmff_header(io,box,b,b[0] ? 32 : 20); if(status!=EXR_OK) return status;
  if(b[0]) { *scale=exr_bmff_be32(b+20); *duration=exr_bmff_be64(b+24); } else { *scale=exr_bmff_be32(b+12); *duration=exr_bmff_be32(b+16); }
  return *scale ? EXR_OK : exr_bmff_fail(io,"Zero ISO-BMFF timescale");
}
