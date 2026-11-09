/* SPDX-License-Identifier: MIT */
/* Test-only byte oracle: invokes the production codecs, without HTML parsing. */
#include "formats_internal.h"
#include <stdio.h>
static unsigned u16(const unsigned char *p) { return ((unsigned)p[0]<<8)|p[1]; }
static uint32_t u32(const unsigned char *p) { return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3]; }
int main(int argc,char **argv) {
  unsigned char *data=NULL; size_t size=0,i,count=0,text_count=0; exr_error e={0};
  exr_buffer text={0}; exr_mobi_record *records=NULL; exr_mobi_huff *huff=NULL;
  exr_status status=EXR_FORMAT; unsigned compression=2,flags=0; FILE *f;
  if(argc!=4) return 2;
  status=exr_read(argv[2],&data,&size,&e); if(status!=EXR_OK) goto done;
  if(!strcmp(argv[1],"palmdoc")) {
    exr_mobi_record r={data,size}; status=exr_mobi_palmdoc(&r,&text,&e);
  } else {
    const unsigned char *h; size_t first,n;
    status=EXR_FORMAT;
    if(size<78 || memcmp(data+60,"BOOKMOBI",8)) goto done;
    count=u16(data+76); if(count<2 || count>(size-78)/8) goto done;
    records=calloc(count,sizeof(*records)); if(!records) goto done;
    for(i=0;i<count;i++) {
      size_t start=u32(data+78+i*8),end=i+1<count ? u32(data+86+i*8) : size;
      if(start>end || end>size) goto done;
      records[i]=(exr_mobi_record){data+start,end-start};
    }
    if(records[0].size<244) goto done;
    h=records[0].data; compression=u16(h); text_count=u16(h+8); flags=u16(h+242);
    if(!text_count || text_count>=count) goto done;
    if(compression==0x4448) {
      first=u32(h+112); n=u32(h+116); if(first>=count || n>count-first) goto done;
      status=exr_mobi_huff_open(records+first,n,&huff,&e); if(status!=EXR_OK) goto done;
    }
    printf("{\"compression\":%u,\"declared_bytes\":%u,\"record_bytes\":[",compression,u32(h+4));
    for(i=1;i<=text_count;i++) {
      exr_mobi_record r=records[i]; size_t before=text.size; unsigned bit;
      status=EXR_FORMAT;
      for(bit=1;bit<16;bit++) if(flags&(1u<<bit)) {
        size_t n_=0,used=0; unsigned c_=0;
        do { if(used>=r.size || used==4) goto done; c_=r.data[r.size-1-used]; n_|=(size_t)(c_&127)<<(7*used++); } while(!(c_&128));
        if(n_<used || n_>r.size) goto done;
        r.size-=n_;
      }
      if(flags&1) { size_t n_; if(!r.size) goto done; n_=(r.data[r.size-1]&3)+1; if(n_>r.size) goto done; r.size-=n_; }
      if(compression==0x4448) status=exr_mobi_huff_decode(huff,r.data,r.size,&text,&e);
      else if(compression==2) status=exr_mobi_palmdoc(&r,&text,&e);
      else if(compression==1) status=exr_append(&text,r.data,r.size) ? EXR_OK : EXR_MEMORY;
      else goto done;
      if(status!=EXR_OK) goto done;
      printf("%s%zu",i==1 ? "" : ",",text.size-before);
    }
    printf("],\"decoded_bytes\":%zu}\n",text.size);
  }
  if(status==EXR_OK) {
    f=fopen(argv[3],"wb"); if(!f) { status=EXR_IO; goto done; }
    if(fwrite(text.data,1,text.size,f)!=text.size) status=EXR_IO;
    if(fclose(f)) status=EXR_IO;
  }
done:
  if(status!=EXR_OK) fprintf(stderr,"%d: %s\n",status,e.message);
  exr_mobi_huff_free(huff); free(records); free(data); free(text.data); return status==EXR_OK ? 0 : 1;
}
