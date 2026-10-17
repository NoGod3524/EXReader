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
exr_status exr_bmff_table_box(exr_bmff_reader *io,const exr_bmff_box *box,exr_bmff_table *table,unsigned width,int bounded) {
  unsigned char b[8]; uint64_t bytes; exr_status status=exr_bmff_header(io,box,b,8); if(status!=EXR_OK) return status;
  if(exr_bmff_be32(b)) return exr_bmff_fail(io,"Unsupported ISO-BMFF table version/flags");
  table->count=exr_bmff_be32(b+4); table->at=box->data+8; table->width=width;
  if(!table->count) return exr_bmff_fail(io,"Empty ISO-BMFF sample table");
  if(bounded && table->count>65536u) return exr_fail(io->error,EXR_LIMIT,"ISO-BMFF table exceeds 65536 runs");
  bytes=(uint64_t)table->count*width;
  return bytes<=box->end-table->at ? EXR_OK : exr_bmff_fail(io,"Truncated ISO-BMFF table entries");
}
exr_status exr_bmff_size_box(exr_bmff_reader *io,const exr_bmff_box *box,exr_bmff_table *table) {
  unsigned char b[12]; uint64_t n; exr_status status=exr_bmff_header(io,box,b,12); if(status!=EXR_OK) return status;
  if(exr_bmff_be32(b)) return exr_bmff_fail(io,"Unsupported ISO-BMFF sample-size version/flags");
  table->count=exr_bmff_be32(b+8); table->at=box->data+12;
  if(box->type==EXR_BMFF_TYPE('s','t','s','z')) { table->constant=exr_bmff_be32(b+4); table->width=32; }
  else {
    if(b[4] || b[5] || b[6] || (b[7]!=4 && b[7]!=8 && b[7]!=16)) return exr_bmff_fail(io,"Invalid compact ISO-BMFF sample sizes");
    table->width=b[7];
  }
  if(!table->count || table->constant>65536) return exr_bmff_fail(io,"Empty/oversized ISO-BMFF media samples");
  n=table->constant ? 0 : ((uint64_t)table->count*table->width+7)/8;
  return n<=box->end-table->at ? EXR_OK : exr_bmff_fail(io,"Truncated ISO-BMFF sample-size table");
}
exr_status exr_bmff_sample_size(exr_bmff_reader *io,const exr_bmff_table *table,uint32_t sample,uint32_t *size) {
  unsigned char b[4]; exr_status status;
  if(sample>=table->count) return exr_bmff_fail(io,"ISO-BMFF sample index exceeds table");
  if(table->constant) *size=table->constant;
  else {
    unsigned width=table->width; size_t bytes=width==4 ? 1 : width/8;
    status=exr_bmff_read(io,table->at+(uint64_t)sample*width/8,b,bytes); if(status!=EXR_OK) return status;
    *size=width==4 ? ((sample&1) ? b[0]&15 : b[0]>>4) : width==8 ? b[0] : width==16 ? exr_bmff_be16(b) : exr_bmff_be32(b);
  }
  return *size && *size<=65536 ? EXR_OK : exr_bmff_fail(io,"ISO-BMFF media sample exceeds 64 KiB or is empty");
}
exr_status exr_bmff_sc_entry(exr_bmff_reader *io,const exr_bmff_table *table,uint32_t index,uint32_t values[3]) {
  unsigned char b[12]; exr_status status;
  if(index>=table->count) return exr_bmff_fail(io,"ISO-BMFF sample-to-chunk index exceeds table");
  status=exr_bmff_read(io,table->at+(uint64_t)index*12,b,12); if(status!=EXR_OK) return status;
  values[0]=exr_bmff_be32(b); values[1]=exr_bmff_be32(b+4); values[2]=exr_bmff_be32(b+8);
  return EXR_OK;
}
exr_status exr_bmff_validate_sc(exr_bmff_reader *io,const exr_bmff_table *sizes,const exr_bmff_table *chunks,const exr_bmff_table *sc) {
  uint32_t i,current[3]={0},next[3]={0}; uint64_t samples=0; exr_status status=exr_bmff_sc_entry(io,sc,0,current); if(status!=EXR_OK) return status;
  if(current[0]!=1) return exr_bmff_fail(io,"ISO-BMFF first sample-to-chunk entry must start at chunk 1");
  for(i=0;i<sc->count;i++) {
    uint64_t end=(uint64_t)chunks->count+1,count;
    if(i+1<sc->count) { status=exr_bmff_sc_entry(io,sc,i+1,next); if(status!=EXR_OK) return status; end=next[0]; }
    if(!current[0] || current[0]>chunks->count || end<=current[0] || end>(uint64_t)chunks->count+1 || !current[1] || current[2]!=1) return exr_bmff_fail(io,"Invalid ISO-BMFF sample-to-chunk run");
    count=(end-current[0])*current[1];
    if(count>sizes->count-samples) return exr_bmff_fail(io,"ISO-BMFF chunk sample counts exceed size table");
    samples+=count; if(i+1<sc->count) memcpy(current,next,sizeof(current));
  }
  return samples==sizes->count ? EXR_OK : exr_bmff_fail(io,"ISO-BMFF sample-to-chunk coverage is incomplete");
}
exr_status exr_bmff_chunk_offset(exr_bmff_reader *io,const exr_bmff_table *table,uint32_t chunk,uint64_t *offset) {
  unsigned char b[8]; exr_status status;
  if(chunk>=table->count) return exr_bmff_fail(io,"ISO-BMFF chunk index exceeds offset table");
  status=exr_bmff_read(io,table->at+(uint64_t)chunk*table->width,b,table->width); if(status!=EXR_OK) return status;
  *offset=table->width==8 ? exr_bmff_be64(b) : exr_bmff_be32(b); return EXR_OK;
}
