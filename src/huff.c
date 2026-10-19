/* SPDX-License-Identifier: MIT */
/* HUFF/CDIC field semantics: KindleUnpack reference, credited in THIRD_PARTY_NOTICES.md. */
#include "internal.h"
typedef struct {
  const unsigned char *encoded,*decoded;
  size_t encoded_size,size;
  unsigned state,literal;
} phrase;
struct exr_mobi_huff {
  unsigned lengths[256],terminal[256];
  uint64_t fast_max[256],minimum[33],maximum[33];
  phrase *phrases;
  size_t count,loaded,memory,work,symbols;
};
static uint32_t be32(const unsigned char *p) {
  return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];
}
static unsigned be16(const unsigned char *p) { return ((unsigned)p[0]<<8)|p[1]; }
void exr_mobi_huff_free(exr_mobi_huff *h) {
  size_t i;
  if(!h) return;
  for(i=0;i<h->loaded;i++) if(!h->phrases[i].literal) free((void *)h->phrases[i].decoded);
  free(h->phrases); free(h);
}
exr_status exr_mobi_huff_open(const exr_mobi_record *records,size_t count,exr_mobi_huff **out,exr_error *e) {
  exr_mobi_huff *h=NULL; size_t i,j,loaded=0,total=0,off1,off2;
  const unsigned char *data;
  exr_status status=EXR_FORMAT;
  *out=NULL;
  if(!records || count<2) return exr_fail(e,EXR_FORMAT,"HUFF requires CDIC dictionaries");
  data=records[0].data;
  if(records[0].size<24 || memcmp(data,"HUFF",4) || be32(data+4)!=24) goto failed;
  off1=be32(data+8); off2=be32(data+12);
  if(off1<24 || off2<24 || off1>records[0].size || records[0].size-off1<1024 ||
      off2>records[0].size || records[0].size-off2<256) goto failed;
  h=calloc(1,sizeof(*h)); if(!h) { status=EXR_MEMORY; goto failed; }
  for(i=0;i<256;i++) {
    uint32_t entry=be32(data+off1+i*4); unsigned length=entry&31;
    if(!length || (length<=8 && !(entry&128))) goto failed;
    h->lengths[i]=length; h->terminal[i]=(entry&128)!=0;
    h->fast_max[i]=(((uint64_t)(entry>>8)+1)<<(32-length))-1;
  }
  for(i=1;i<=32;i++) {
    h->minimum[i]=(uint64_t)be32(data+off2+(i-1)*8)<<(32-i);
    h->maximum[i]=(((uint64_t)be32(data+off2+(i-1)*8+4)+1)<<(32-i))-1;
  }
  for(i=1;i<count;i++) {
    uint32_t declared,bits; size_t n;
    data=records[i].data;
    if(records[i].size<16 || memcmp(data,"CDIC",4) || be32(data+4)!=16) goto failed;
    declared=be32(data+8); bits=be32(data+12);
    if(!declared || bits>16) goto failed;
    if(declared>1024u*1024) { status=EXR_LIMIT; goto failed; }
    if(i==1) total=declared;
    else if(declared!=total) goto failed;
    if(loaded>=total) goto failed;
    n=(size_t)1<<bits; if(n>total-loaded) n=total-loaded;
    if(n>(records[i].size-16)/2) goto failed;
    loaded+=n;
  }
  if(loaded!=total) goto failed;
  h->phrases=calloc(total,sizeof(*h->phrases));
  if(!h->phrases) { status=EXR_MEMORY; goto failed; } h->count=total;
  loaded=0;
  for(i=1;i<count;i++) {
    size_t n=(size_t)1<<be32(records[i].data+12); data=records[i].data;
    if(n>total-loaded) n=total-loaded;
    for(j=0;j<n;j++) {
      size_t offset=be16(data+16+j*2),size; unsigned encoded; phrase *p=&h->phrases[loaded+j];
      if(offset<n*2 || offset>records[i].size-16 || records[i].size-16-offset<2) goto failed;
      encoded=be16(data+16+offset); size=encoded&32767;
      if(size>records[i].size-18-offset) goto failed;
      p->encoded=data+18+offset; p->encoded_size=size; p->literal=(encoded&32768)!=0;
      if(p->literal) { p->decoded=p->encoded; p->size=size; p->state=2; }
      h->loaded=loaded+j+1;
    }
    loaded+=n;
  }
  if(loaded!=total) goto failed;
  *out=h; return exr_fail(e,EXR_OK,"");
failed:
  exr_mobi_huff_free(h);
  return exr_fail(e,status,status==EXR_FORMAT ? "Invalid HUFF/CDIC tables" : "HUFF dictionary allocation limit exceeded");
}
static exr_status append(exr_mobi_huff *h,exr_buffer *out,const unsigned char *data,size_t size,exr_error *e) {
  size_t need,next; char *grown;
  if(size>EXR_MAX_TEXT-out->size || size>EXR_MAX_INPUT*2-h->work)
    return exr_fail(e,EXR_LIMIT,"HUFF output or expansion work exceeds limit");
  if(!size) return EXR_OK;
  need=out->size+size+1;
  if(need>out->capacity) {
    next=out->capacity ? out->capacity : 64;
    while(next<need) next=next>(EXR_MAX_TEXT+1)/2 ? EXR_MAX_TEXT+1 : next*2;
    if(next-out->capacity>EXR_MAX_INPUT-h->memory) return exr_fail(e,EXR_LIMIT,"HUFF decoded working memory exceeds 128 MiB");
    grown=realloc(out->data,next); if(!grown) return exr_fail(e,EXR_MEMORY,"HUFF expansion allocation failed");
    h->memory+=next-out->capacity; out->capacity=next; out->data=grown;
  }
  memcpy(out->data+out->size,data,size); out->size+=size; out->data[out->size]=0; h->work+=size;
  return EXR_OK;
}
static exr_status decode(exr_mobi_huff *h,const unsigned char *data,size_t size,exr_buffer *out,unsigned depth,exr_error *e);
static exr_status expand(exr_mobi_huff *h,size_t index,unsigned depth,exr_error *e) {
  phrase *p=&h->phrases[index]; exr_buffer buffer={0}; exr_status status;
  if(p->state==2) return EXR_OK;
  if(p->state==1) return exr_fail(e,EXR_FORMAT,"Cyclic CDIC phrase");
  if(depth>=64) return exr_fail(e,EXR_LIMIT,"CDIC phrase nesting exceeds 64");
  p->state=1; status=decode(h,p->encoded,p->encoded_size,&buffer,depth+1,e);
  if(status!=EXR_OK) { h->memory-=buffer.capacity; free(buffer.data); p->state=0; return status; }
  p->decoded=(const unsigned char *)buffer.data; p->size=buffer.size; p->state=2;
  return EXR_OK;
}
static exr_status decode(exr_mobi_huff *h,const unsigned char *data,size_t size,exr_buffer *out,unsigned depth,exr_error *e) {
  size_t position=0; uint64_t window=0; unsigned available=0;
  while(position<size || available) {
    uint32_t code; uint64_t maximum,index; unsigned length,slot; exr_status status;
    while(available<32 && position<size) { window=(window<<8)|data[position++]; available+=8; }
    code=available>=32 ? (uint32_t)(window>>(available-32)) : (uint32_t)(window<<(32-available));
    slot=code>>24; length=h->lengths[slot]; maximum=h->fast_max[slot];
    if(length>available && position==size) break;
    if(!h->terminal[slot]) {
      while(length<=32 && (uint64_t)code<h->minimum[length]) {
        length++;
        if(length>32) return exr_fail(e,EXR_FORMAT,"Invalid HUFF code prefix");
        if(length>available && position==size) return EXR_OK;
      }
      if(length>32) return exr_fail(e,EXR_FORMAT,"Invalid HUFF code prefix");
      maximum=h->maximum[length];
    }
    if(length>available) break;
    if(maximum<code) return exr_fail(e,EXR_FORMAT,"Invalid HUFF code interval");
    index=(maximum-code)>>(32-length);
    if(index>=h->count) return exr_fail(e,EXR_FORMAT,"HUFF code exceeds phrase dictionary");
    if(++h->symbols>EXR_MAX_INPUT) return exr_fail(e,EXR_LIMIT,"HUFF symbol work exceeds limit");
    available-=length; window&=available ? (UINT64_C(1)<<available)-1 : 0;
    status=expand(h,(size_t)index,depth,e); if(status!=EXR_OK) return status;
    status=append(h,out,h->phrases[index].decoded,h->phrases[index].size,e); if(status!=EXR_OK) return status;
  }
  return EXR_OK;
}
exr_status exr_mobi_huff_decode(exr_mobi_huff *h,const void *data,size_t size,exr_buffer *out,exr_error *e) {
  return decode(h,data,size,out,0,e);
}
