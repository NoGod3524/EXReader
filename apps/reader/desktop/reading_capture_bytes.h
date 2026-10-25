/* SPDX-License-Identifier: MIT */
#ifndef READER_PRIVATE_CAPTURE_BYTES_H
#define READER_PRIVATE_CAPTURE_BYTES_H
#include <stdlib.h>
#include <string.h>
#include <reader_reading_state.h>

/* App-private pending capture, NOT revision wire or an SDK serialization API.
   Magic EXRPCAP\0, format u32=1, writer u32, mode u32, reserved u32=0,
   then part/page/start/end u64. All integers are little endian. Six blobs follow
   in chapter/path/page_id/exact/prefix/suffix order: present u8, length u32,
   exactly length bytes. NULL requires present=0,length=0; present=1,length=0
   is an allocated empty string after decode. No terminators are stored.
   Fixed selectors use only their explicit sizes and may contain NUL bytes.
   Other fields are C text: encoded text ends at its first terminator; decoding
   rejects embedded NUL in every text blob. SDK/wire suitability is not granted.

   Success alone replaces output arguments. Caller must release any prior
   output before a successful replacement. Encoded output uses the free below;
   decoded char fields use malloc and are compatible with reader_rs_record_free.
   Identity/envelope/note fields stay zero; has_location denotes a stored capture,
   not a navigable location (in particular, NULL exact is not navigation proof).
   No support for EXRRD001, GTK keyfiles, filesystem, SQL, or old pending parsing. */
#define READER_PRIVATE_CAPTURE_MAX_BYTES ((size_t)1048576)
#define READER_PRIVATE_CAPTURE_MAX_BLOB ((size_t)65536)

static inline void reader_private_capture_free(void *p) { free(p); }

static inline void reader_private_capture_detail_put(unsigned char *p, uint64_t n, unsigned count) {
  unsigned i; for(i=0;i<count;i++) { p[i]=(unsigned char)(n&255u); n>>=8; }
}
static inline uint64_t reader_private_capture_detail_get(const unsigned char *p,unsigned count) {
  unsigned i;uint64_t n=0;for(i=0;i<count;i++)n|=(uint64_t)p[i]<<(8u*i);return n;
}
static inline exr_status reader_private_capture_detail_text(const char *p,size_t *n) {
  size_t i;*n=0;if(!p)return EXR_OK;
  for(i=0;i<=READER_PRIVATE_CAPTURE_MAX_BLOB;i++)if(!p[i]){*n=i;return EXR_OK;}
  return EXR_LIMIT;
}
static inline void reader_private_capture_detail_release(reader_rs_record *r) {
  free(r->chapter);free(r->part_path);free(r->page_id);
  free(r->exact);free(r->prefix);free(r->suffix);
}

static inline exr_status reader_private_capture_encode(const reader_rs_capture *capture,
  size_t part,unsigned writer_version,unsigned char **out,size_t *size) {
  static const unsigned char magic[8]={'E','X','R','P','C','A','P',0};
  const char *fields[6]={NULL,NULL,NULL,NULL,NULL,NULL};
  size_t lengths[6]={0,0,0,0,0,0},start,end,total=56,at=56,i;
  unsigned char *data;exr_status status;
  if(!capture||!out||!size||writer_version<1||writer_version>3||
     capture->mode<READER_RS_REFLOW_GLOBAL||capture->mode>READER_RS_FIXED_PAGE||
     (writer_version==3&&capture->mode!=READER_RS_FIXED_PAGE))return EXR_ARGUMENT;
  fields[1]=capture->part_path;
  if(capture->mode==READER_RS_FIXED_PAGE) {
    const exr_fixed_anchor *a=capture->fixed;
    if(!a||capture->anchor)return EXR_ARGUMENT;
    start=a->start;end=a->end;fields[2]=a->page_id;
    fields[3]=a->exact;fields[4]=a->prefix;fields[5]=a->suffix;
    lengths[3]=a->exact_size;lengths[4]=a->prefix_size;lengths[5]=a->suffix_size;
    if(end<start||end-start!=lengths[3])return EXR_ARGUMENT;
  } else {
    const exr_anchor *a=capture->anchor;
    if(!a||capture->fixed)return EXR_ARGUMENT;
    start=a->start;end=a->end;fields[0]=a->chapter;
    fields[3]=a->exact;fields[4]=a->prefix;fields[5]=a->suffix;
    if(end<start)return EXR_ARGUMENT;
  }
  /* Round trips must fit the specified 64-bit private representation. */
#if SIZE_MAX > UINT64_MAX
  if(part>UINT64_MAX||capture->page>UINT64_MAX||start>UINT64_MAX||end>UINT64_MAX)return EXR_LIMIT;
#endif
  for(i=0;i<6;i++) {
    if(i<3||capture->mode!=READER_RS_FIXED_PAGE) {
      status=reader_private_capture_detail_text(fields[i],&lengths[i]);if(status!=EXR_OK)return status;
    }
    if(lengths[i]>READER_PRIVATE_CAPTURE_MAX_BLOB)return EXR_LIMIT;
    if(!fields[i]&&lengths[i])return EXR_ARGUMENT;
    if(total>READER_PRIVATE_CAPTURE_MAX_BYTES-5||lengths[i]>READER_PRIVATE_CAPTURE_MAX_BYTES-total-5)return EXR_LIMIT;
    total+=5+lengths[i];
  }
  if(capture->mode!=READER_RS_FIXED_PAGE&&fields[3]&&end-start!=lengths[3])return EXR_ARGUMENT;
  data=(unsigned char *)malloc(total);if(!data)return EXR_MEMORY;
  memcpy(data,magic,8);reader_private_capture_detail_put(data+8,1,4);
  reader_private_capture_detail_put(data+12,writer_version,4);
  reader_private_capture_detail_put(data+16,(unsigned)capture->mode,4);
  reader_private_capture_detail_put(data+20,0,4);
  reader_private_capture_detail_put(data+24,(uint64_t)part,8);
  reader_private_capture_detail_put(data+32,(uint64_t)capture->page,8);
  reader_private_capture_detail_put(data+40,(uint64_t)start,8);
  reader_private_capture_detail_put(data+48,(uint64_t)end,8);
  for(i=0;i<6;i++) {
    data[at]=(unsigned char)(fields[i]!=NULL);reader_private_capture_detail_put(data+at+1,(uint64_t)lengths[i],4);at+=5;
    if(lengths[i]){memcpy(data+at,fields[i],lengths[i]);}
    at+=lengths[i];
  }
  *out=data;*size=total;return EXR_OK;
}

static inline exr_status reader_private_capture_decode(const void *bytes,size_t size,reader_rs_record *out) {
  static const unsigned char magic[8]={'E','X','R','P','C','A','P',0};
  const unsigned char *data=(const unsigned char *)bytes,*values[6];
  size_t lengths[6],at=56,i;unsigned present[6],writer,mode;uint64_t stored_writer,stored_mode;
  uint64_t part,page,start,end;reader_rs_record result;char **targets[6];
  if(!bytes||!out)return EXR_ARGUMENT;
  if(size>READER_PRIVATE_CAPTURE_MAX_BYTES)return EXR_LIMIT;
  if(size<86||memcmp(data,magic,8)||reader_private_capture_detail_get(data+8,4)!=1||
     reader_private_capture_detail_get(data+20,4)!=0)return EXR_FORMAT;
  stored_writer=reader_private_capture_detail_get(data+12,4);stored_mode=reader_private_capture_detail_get(data+16,4);
  if(stored_writer<1||stored_writer>3||stored_mode<1||stored_mode>3||(stored_writer==3&&stored_mode!=3))return EXR_FORMAT;
  writer=(unsigned)stored_writer;mode=(unsigned)stored_mode;
  part=reader_private_capture_detail_get(data+24,8);page=reader_private_capture_detail_get(data+32,8);
  start=reader_private_capture_detail_get(data+40,8);end=reader_private_capture_detail_get(data+48,8);
  if(end<start)return EXR_FORMAT;
#if SIZE_MAX < UINT64_MAX
  if(part>SIZE_MAX||page>SIZE_MAX||start>SIZE_MAX||end>SIZE_MAX)return EXR_FORMAT;
#endif
  for(i=0;i<6;i++) {
    uint64_t length;
    if(at>size||size-at<5)return EXR_FORMAT;
    present[i]=data[at];length=reader_private_capture_detail_get(data+at+1,4);at+=5;
    if(present[i]>1||(!present[i]&&length)||length>READER_PRIVATE_CAPTURE_MAX_BLOB||length>(uint64_t)(size-at))return EXR_FORMAT;
    lengths[i]=(size_t)length;values[i]=data+at;
    if((i<3||mode!=3)&&lengths[i]&&memchr(values[i],0,lengths[i]))return EXR_FORMAT;
    at+=lengths[i];
  }
  if(at!=size||(mode==3&&(present[0]||end-start!=(uint64_t)lengths[3]))||
     (mode!=3&&present[2])||(mode!=3&&present[3]&&end-start!=(uint64_t)lengths[3]))return EXR_FORMAT;
  memset(&result,0,sizeof(result));result.mode=(reader_rs_mode)mode;result.anchor_version=writer;
  result.has_location=1;result.part=part;result.page=page;result.start=start;result.end=end;
  result.exact_size=lengths[3];result.prefix_size=lengths[4];result.suffix_size=lengths[5];
  targets[0]=&result.chapter;targets[1]=&result.part_path;targets[2]=&result.page_id;
  targets[3]=&result.exact;targets[4]=&result.prefix;targets[5]=&result.suffix;
  for(i=0;i<6;i++)if(present[i]) {
    *targets[i]=(char *)malloc(lengths[i]+1);
    if(!*targets[i]){reader_private_capture_detail_release(&result);return EXR_MEMORY;}
    if(lengths[i]){memcpy(*targets[i],values[i],lengths[i]);}
    (*targets[i])[lengths[i]]=0;
  }
  *out=result;return EXR_OK;
}
#endif
