/* SPDX-License-Identifier: MIT */
/* Standalone libFuzzer entry point; see sevenz-anchorstats.md for build command. */
#include "exr/formats.h"
#include "lzma_internal.h"
#include <miniz.h>
typedef struct { const unsigned char *data; size_t size; } fuzz_source;
static size_t read_fuzz(void *context,uint64_t offset,void *out,size_t n) {
  fuzz_source *s=context;
  if(offset>=s->size) return 0;
  if(n>s->size-(size_t)offset) n=s->size-(size_t)offset;
  memcpy(out,s->data+(size_t)offset,n); return n;
}
static uint64_t little(const unsigned char *s,unsigned n) {
  uint64_t value=0; unsigned i;
  for(i=0;i<n;i++) value|=(uint64_t)s[i]<<(8*i);
  return value;
}
static void checksum(unsigned char *to,const unsigned char *data,size_t n) {
  uint32_t value=(uint32_t)mz_crc32(0,data,n); unsigned i;
  for(i=0;i<4;i++) to[i]=(unsigned char)(value>>(8*i));
}
int LLVMFuzzerTestOneInput(const unsigned char *data,size_t size) {
  exr_error error; exr_sevenz *z=NULL; exr_sevenz_options options=exr_sevenz_options_defaults();
  fuzz_source input={data,size}; exr_source source={size,read_fuzz,NULL,&input,{0}};
  size_t i,count,n; void *out; unsigned char *fixed=NULL;
  options.max_header_size=options.max_unpack_size=65536;
  /* Repair outer CRCs so mutations can reach directory parsing. The original
     CRC rejection paths are also covered by test_sevenz.c. */
  if(size>=32 && !memcmp(data,"7z\xbc\xaf\x27\x1c",6)) {
    uint64_t offset=little(data+12,8),length=little(data+20,8);
    fixed=malloc(size);
    if(fixed) {
      memcpy(fixed,data,size);
      if(offset<=size-32 && length<=size-32-offset) checksum(fixed+28,fixed+32+(size_t)offset,(size_t)length);
      checksum(fixed+8,fixed+12,20); input.data=fixed;
    }
  }
  if(exr_sevenz_open_source(&source,&options,&z,&error)==EXR_OK) {
    const exr_sevenz_entry *entries=exr_sevenz_entries(z,&count);
    if(count>8) count=8;
    for(i=0;i<count;i++) if(!entries[i].is_directory) {
      exr_sevenz_extract(z,i,&out,&n,&error); free(out);
    }
    exr_sevenz_free(z);
  }
  free(fixed);
  if(size>=8) {
    int two=data[0]&1; size_t props=two ? 1 : 5,at=1+props;
    n=(size_t)data[at]+((size_t)data[at+1]<<8); at+=2;
    out=malloc(n ? n : 1);
    if(out) { exr_lzma_decode(two,data+1,props,data+at,size-at,out,n,NULL,&error); free(out); }
  }
  return 0;
}
