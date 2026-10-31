/* SPDX-License-Identifier: MIT */
#include <exr_wh3_repair.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define RREC 424u
#define RSEAL 360u
#define RJMAX ((EXR_WH_LINE_MAX+3u)*EXR_WH_MAX_JOURNAL)
#define RIMAX (RREC*2u*EXR_WH_MAX_JOURNAL+1u)
typedef struct {unsigned char *data;size_t size;wh3w_identity id;char sha[65];} rimage;
typedef struct {
 const wh_binding *binding;const wh_gates *gates;
 rimage journal,intent;
 char manifest[EXR_WH_LINE_MAX],manifest_sha[65];
 char lines[EXR_WH_MAX_JOURNAL][EXR_WH_LINE_MAX];
 size_t ends[EXR_WH_MAX_JOURNAL],complete;
} rscan_work;
static uint64_t rget(const unsigned char *p) {
 uint64_t n=0;unsigned k;for(k=0;k<8;k++)n|=(uint64_t)p[k]<<(8*k);return n;
}
static void rput(unsigned char *p,uint64_t n) {
 unsigned k;for(k=0;k<8;k++){p[k]=(unsigned char)n;n>>=8;}
}
static int rid(HANDLE h,wh3w_identity *id) {
 FILE_ID_INFO info;BY_HANDLE_FILE_INFORMATION basic;
 if(h==INVALID_HANDLE_VALUE||!GetFileInformationByHandleEx(h,FileIdInfo,&info,sizeof(info))||
    !GetFileInformationByHandle(h,&basic)||basic.nNumberOfLinks!=1||
    (basic.dwFileAttributes&(FILE_ATTRIBUTE_DIRECTORY|FILE_ATTRIBUTE_REPARSE_POINT)))return 0;
 id->volume=info.VolumeSerialNumber;id->file=info.FileId;return 1;
}
static int reqid(const wh3w_identity *a,const wh3w_identity *b) {
 return a->volume==b->volume&&!memcmp(&a->file,&b->file,16);
}
static int rsize(HANDLE h,size_t maximum,size_t *out) {
 LARGE_INTEGER size;if(!GetFileSizeEx(h,&size)||size.QuadPart<0||(uint64_t)size.QuadPart>maximum)return 0;
 *out=(size_t)size.QuadPart;return 1;
}
static int rread(HANDLE h,unsigned char *data,size_t size) {
 LARGE_INTEGER zero;size_t at=0;zero.QuadPart=0;
 if(!SetFilePointerEx(h,zero,NULL,FILE_BEGIN))return 0;
 while(at<size){
  DWORD got=0,want=(DWORD)((size-at)>65536u?65536u:size-at);
  if(!ReadFile(h,data+at,want,&got,NULL)||got!=want)return 0;at+=got;
 }
 return 1;
}
static int rimage_read(HANDLE h,size_t maximum,rimage *image) {
 size_t after;wh3w_identity id;
 if(!rid(h,&image->id)||!rsize(h,maximum,&image->size))return 0;
 image->data=malloc(image->size?image->size:1);if(!image->data)return 0;
 if(!rread(h,image->data,image->size)||!rid(h,&id)||!reqid(&id,&image->id)||
    !rsize(h,maximum,&after)||after!=image->size)return 0;
 wh_sha256_hex(image->data,image->size,image->sha);return 1;
}
static int rimage_again(HANDLE h,size_t maximum,rimage *image) {
 size_t before,after;wh3w_identity id;char sha[65];
 if(!rid(h,&id)||!reqid(&id,&image->id)||!rsize(h,maximum,&before)||before!=image->size||
    !rread(h,image->data,image->size)||!rid(h,&id)||!reqid(&id,&image->id)||
    !rsize(h,maximum,&after)||after!=image->size)return 0;
 wh_sha256_hex(image->data,image->size,sha);return !memcmp(sha,image->sha,65);
}
static int rhx(unsigned char c){return (c>='0'&&c<='9')||(c>='a'&&c<='f');}
static int rprefix(const unsigned char *data,size_t size,size_t offset,const void *expected,size_t n) {
 size_t available;if(size<=offset)return 1;available=size-offset;if(available>n)available=n;
 return !memcmp(data+offset,expected,available);
}
static int rframes(rscan_work *w) {
 size_t at=0;w->complete=0;
 while(at<w->journal.size){
  const unsigned char *p=w->journal.data+at;size_t n;
  if(w->journal.size-at<4)return 1;
  n=(size_t)p[0]|(size_t)p[1]<<8|(size_t)p[2]<<16|(size_t)p[3]<<24;
  if(!n||n>=EXR_WH_LINE_MAX||w->complete>=EXR_WH_MAX_JOURNAL)return 0;
  if(w->journal.size-at-4<n)return 1;
  if(memchr(p+4,0,n))return 0;
  memcpy(w->lines[w->complete],p+4,n);w->lines[w->complete][n]=0;
  at+=4+n;w->ends[w->complete++]=at;
 }
 return 1;
}
static int rjournal_check(rscan_work *w,size_t n,const char *next) {
 const char *lines[EXR_WH_MAX_JOURNAL];size_t k;
 if(n+(next?1u:0u)>EXR_WH_MAX_JOURNAL)return 0;
 for(k=0;k<n;k++)lines[k]=w->lines[k];if(next)lines[n++]=next;
 return !n||wh_journal_check(w->binding,w->gates,lines,n);
}
/* A partial body must be a prefix of at least one canonical legal next FSM
   record. Introduced IDs/digests are filled only where bytes were observed;
   unobserved bytes are not treated as trusted evidence. */
static int rcandidate(rscan_work *w,size_t count,unsigned event,const unsigned char *partial,
 size_t partial_size,size_t declared,const unsigned char *new_sha,size_t new_sha_bytes,
 size_t *length) {
 char candidate[EXR_WH_LINE_MAX],values[4][65],previous[65],bind[65],seal[65],tail;
 const char *pointers[EXR_WH_MAX_JOURNAL];size_t starts[4]={0},widths[4]={0},body,n,k,j,last_unknown=0;
 unsigned old_seq,old_event;int used;
 if(count>=EXR_WH_MAX_JOURNAL)return 0;
 if(!count){
  if(event||!rprefix(partial,partial_size,0,w->manifest,strlen(w->manifest))||
     partial_size>strlen(w->manifest))return 0;
  n=strlen(w->manifest);
  if((declared&&declared!=n)||(new_sha_bytes&&memcmp(new_sha,w->manifest_sha,new_sha_bytes)))return 0;
  *length=n;return 1;
 }
 memset(values,0,sizeof(values));
 for(k=0;k<4;k++)strcpy_s(values[k],sizeof(values[k]),"-");
 memcpy(previous,w->manifest_sha,65);memcpy(bind,w->manifest_sha,65);
 if(count>1){
  char prior_previous[65];
  used=sscanf(w->lines[count-1],"EXRWH2 %u %u %48s %48s %64s %64s %64s %64s %64s %c",
    &old_seq,&old_event,values[0],values[1],values[2],values[3],prior_previous,bind,previous,&tail);
  if(used!=9)return 0;(void)old_seq;(void)old_event;
 }
 if((event==2||event==15)&&!strcmp(values[0],"-"))widths[0]=48;
 if(event==6&&!strcmp(values[1],"-"))widths[1]=48;
 if(event==4&&!strcmp(values[2],"-"))widths[2]=64;
 if(event==5&&!strcmp(values[3],"-"))widths[3]=64;
 used=snprintf(candidate,sizeof(candidate),"EXRWH2 %zu %u ",count,event);
 if(used<=0||(size_t)used>=sizeof(candidate))return 0;n=(size_t)used;
 for(k=0;k<4;k++){
  starts[k]=n;
  if(widths[k]){memset(values[k],'0',widths[k]);values[k][widths[k]]=0;last_unknown=n+widths[k];}
  used=snprintf(candidate+n,sizeof(candidate)-n,"%s ",values[k]);
  if(used<=0||(size_t)used>=sizeof(candidate)-n)return 0;n+=(size_t)used;
 }
 used=snprintf(candidate+n,sizeof(candidate)-n,"%s %s",previous,bind);
 if(used<=0||(size_t)used>=sizeof(candidate)-n-66)return 0;body=n+(size_t)used;
 for(k=0;k<4;k++)if(widths[k]){
  for(j=0;j<widths[k]&&starts[k]+j<partial_size;j++){
   if(!rhx(partial[starts[k]+j]))return 0;candidate[starts[k]+j]=(char)partial[starts[k]+j];
  }
 }
 wh_sha256_hex(candidate,body,seal);
 candidate[body]=' ';memcpy(candidate+body+1,seal,65);n=body+65;
 if((declared&&declared!=n)||partial_size>n||(partial_size&&memcmp(candidate,partial,partial_size)))return 0;
 for(k=0;k<count;k++)pointers[k]=w->lines[k];pointers[count]=candidate;
 if(!wh_journal_check(w->binding,w->gates,pointers,count+1))return 0;
 if(new_sha_bytes&&partial_size>=last_unknown){
  wh_sha256_hex(candidate,n,seal);if(memcmp(new_sha,seal,new_sha_bytes))return 0;
 }
 *length=n;return 1;
}
static int rpossible(rscan_work *w,size_t count,const unsigned char *partial,size_t partial_size,
 size_t declared,const unsigned char *new_sha,size_t new_sha_bytes,size_t *length) {
 unsigned event;
 if(!count)return rcandidate(w,count,0,partial,partial_size,declared,new_sha,new_sha_bytes,length);
 for(event=1;event<=17;event++)if(rcandidate(w,count,event,partial,partial_size,declared,new_sha,new_sha_bytes,length))return 1;
 return 0;
}
static int rnext(rscan_work *w,size_t count,size_t declared,const unsigned char new_sha[64],int *complete) {
 size_t at=count?w->ends[count-1]:0,remaining=w->journal.size-at,length=0;unsigned char header[4];
 const unsigned char *body=NULL;size_t body_size=0;
 *complete=0;
 if(count>=EXR_WH_MAX_JOURNAL||w->complete<count)return 0;
 header[0]=(unsigned char)declared;header[1]=(unsigned char)(declared>>8);
 header[2]=(unsigned char)(declared>>16);header[3]=(unsigned char)(declared>>24);
 if(!rprefix(w->journal.data+at,remaining,0,header,4))return 0;
 if(remaining>4){body=w->journal.data+at+4;body_size=remaining-4;}
 if(w->complete>count){
  char hash[65];
  if(w->ends[count]-at!=declared+4||strlen(w->lines[count])!=declared||!rjournal_check(w,count+1,NULL))return 0;
  wh_sha256_hex(w->lines[count],declared,hash);
  if(memcmp(hash,new_sha,64))return 0;*complete=1;return 1;
 }
 if(w->complete!=count||remaining>declared+4)return 0;
 return rpossible(w,count,body,body_size,declared,new_sha,64,&length);
}
static int rbegin(rscan_work *w,size_t count,const unsigned char *record,size_t size,
 const char last[65],size_t *declared) {
 unsigned char known[RSEAL]={0};char old_tip[65],hash[65];size_t k,n=0,available;
 if(!size||size>RREC||count>=EXR_WH_MAX_JOURNAL)return 0;
 memcpy(known,"WH3INT01",8);known[8]='B';rput(known+16,count+1);rput(known+24,count);
 memcpy(known+40,w->manifest_sha,64);
 if(count)wh_sha256_hex(w->lines[count-1],strlen(w->lines[count-1]),old_tip);
 else{memset(old_tip,'0',64);old_tip[64]=0;}
 memcpy(known+104,old_tip,64);memcpy(known+296,last,64);
 if(!rprefix(record,size,0,known,32)||!rprefix(record,size,40,known+40,128)||
    !rprefix(record,size,232,known+232,128))return 0;
 available=size>168?size-168:0;if(available>64)available=64;
 for(k=0;k<available;k++)if(!rhx(record[168+k]))return 0;
 if(size>=40){
  uint64_t value=rget(record+32);if(!value||value>=EXR_WH_LINE_MAX)return 0;n=(size_t)value;
  if(!count&&!rprefix(record,size,168,w->manifest_sha,64))return 0;
 }else{
  /* At most 17 event shapes exist; check the partial length against a legal
     full next record, rather than accepting arbitrary short header bytes. */
  unsigned event;int possible=0;
  for(event=0;event<=17;event++){
   unsigned char length_bytes[8];size_t candidate=0;
   if((!count&&event)||(count&&!event)||
      !rcandidate(w,count,event,NULL,0,0,available?record+168:NULL,available,&candidate))continue;
   rput(length_bytes,candidate);
   if(rprefix(record,size,32,length_bytes,8)){n=candidate;possible=1;break;}
  }
  if(!possible)return 0;
 }
 if(size>RSEAL){
  wh_sha256_hex(record,RSEAL,hash);
  if(!rprefix(record,size,RSEAL,hash,64))return 0;
 }
 if(size<RREC){
  size_t end=count?w->ends[count-1]:0,shape=0;
  if(w->journal.size!=end||!rpossible(w,count,NULL,0,n,available?record+168:NULL,available,&shape))return 0;
 }else{
  int complete=0;
  if(!rnext(w,count,n,record+168,&complete))return 0;
 }
 *declared=n;return 1;
}
static void rack(const unsigned char begin[RREC],unsigned char ack[RREC]) {
 char seal[65];memcpy(ack,begin,RREC);ack[8]='A';
 memcpy(ack+232,begin+RSEAL,64);memcpy(ack+296,begin+RSEAL,64);
 wh_sha256_hex(ack,RSEAL,seal);memcpy(ack+RSEAL,seal,64);
}
int wh3r_scan_ack(HANDLE journal,HANDLE intent,const wh_binding *binding,
 const wh_gates *gates,wh3r_scan *out) {
 rscan_work *w=NULL;size_t end=0,count=0,logical=0;char last[65];int ok=0;
 if(out)memset(out,0,sizeof(*out));
 if(!out||!binding||!gates||journal==intent)return 0;
 w=calloc(1,sizeof(*w));if(!w)return 0;w->binding=binding;w->gates=gates;
 if(!wh_manifest(binding,gates,w->manifest)||
    !rimage_read(journal,RJMAX,&w->journal)||!rimage_read(intent,RIMAX,&w->intent)||
    reqid(&w->journal.id,&w->intent.id)||!rframes(w))goto done;
 wh_sha256_hex(w->manifest,strlen(w->manifest),w->manifest_sha);
 logical=w->intent.size;
 if(logical&&w->intent.data[logical-1]==0xff)logical--;
 memset(last,'0',64);last[64]=0;
 while(end<logical){
  const unsigned char *begin=w->intent.data+end;size_t remaining=logical-end,n=0;
  unsigned char ack[RREC];int next_complete=0;
  if(remaining<RREC){
   if(!rbegin(w,count,begin,remaining,last,&n))goto done;
   break;
  }
  if(!rbegin(w,count,begin,RREC,last,&n)||!rnext(w,count,n,begin+168,&next_complete))goto done;
  rack(begin,ack);
  if(remaining<2u*RREC){
   size_t partial=remaining-RREC;
   if(w->complete>count+1||w->journal.size>(count?w->ends[count-1]:0)+n+4||
      (partial&&(!next_complete||memcmp(begin+RREC,ack,partial))))goto done;
   break;
  }
  if(!next_complete||memcmp(begin+RREC,ack,RREC))goto done;
  count++;end+=2u*RREC;memcpy(last,ack+RSEAL,64);last[64]=0;
 }
 /* No extra journal bytes may exist unless a matching final BEGIN was seen. */
 if(end==logical&&w->journal.size!=(count?w->ends[count-1]:0))goto done;
 if(!rjournal_check(w,count,NULL))goto done;
 out->journal_identity=w->journal.id;out->intent_identity=w->intent.id;
 out->journal_bytes=w->journal.size;out->intent_bytes=w->intent.size;
 out->journal_keep_bytes=count?w->ends[count-1]:0;out->intent_keep_bytes=end;
 memcpy(out->journal_sha256,w->journal.sha,65);memcpy(out->intent_sha256,w->intent.sha,65);
 out->count=count;out->tip.line_count=count;memcpy(out->tip.manifest_sha,w->manifest_sha,65);
 if(count)wh_sha256_hex(w->lines[count-1],strlen(w->lines[count-1]),out->tip.last_line_sha);
 else{memset(out->tip.last_line_sha,'0',64);out->tip.last_line_sha[64]=0;}
 for(size_t k=0;k<count;k++)memcpy(out->lines[k],w->lines[k],strlen(w->lines[k])+1);
 out->unack_tail=out->journal_bytes!=out->journal_keep_bytes||out->intent_bytes!=out->intent_keep_bytes;
 if(!rimage_again(journal,RJMAX,&w->journal)||!rimage_again(intent,RIMAX,&w->intent))goto done;
 ok=1;
done:
 if(w){free(w->journal.data);free(w->intent.data);free(w);}
 if(!ok){memset(out,0,sizeof(*out));SetLastError(ERROR_INVALID_DATA);}return ok;
}

/* A per-domain production epoch has exactly I0, then B1 and optional C1.
   Planning a PENDING target never grants authority to publish or clear it. */
static void rgate_record(unsigned char record[WH3R_GATE_RECORD_BYTES],unsigned char state,
 uint64_t seq,uint64_t generation,const char domain[49],const char manifest[65],
 uint64_t count,const char tip[65],const char previous[65]) {
 char seal[65];memset(record,0,WH3R_GATE_RECORD_BYTES);memcpy(record,"WH3GATE1",8);record[8]=state;
 rput(record+16,seq);rput(record+24,generation);memcpy(record+32,domain,48);
 memcpy(record+80,manifest,64);rput(record+144,count);memcpy(record+152,tip,64);
 memcpy(record+216,previous,64);wh_sha256_hex(record,280,seal);memcpy(record+280,seal,64);
}
static int rgate_ack(const wh_binding *binding,const wh_gates *gates,const wh3r_scan *ack,char manifest[65]) {
 const char *lines[EXR_WH_MAX_JOURNAL];char text[EXR_WH_LINE_MAX],last[65];size_t k;
 if(!ack||ack->count>EXR_WH_MAX_JOURNAL||ack->tip.line_count!=ack->count||
    !wh_manifest(binding,gates,text))return 0;
 wh_sha256_hex(text,strlen(text),manifest);
 if(memcmp(manifest,ack->tip.manifest_sha,65)||ack->intent_keep_bytes!=ack->count*2u*RREC)return 0;
 if(!ack->count){
  memset(last,'0',64);last[64]=0;return !memcmp(last,ack->tip.last_line_sha,65)&&!ack->journal_keep_bytes;
 }
 for(k=0;k<ack->count;k++)lines[k]=ack->lines[k];
 if(!wh_journal_check(binding,gates,lines,ack->count))return 0;
 wh_sha256_hex(ack->lines[ack->count-1],strlen(ack->lines[ack->count-1]),last);
 return !memcmp(last,ack->tip.last_line_sha,65);
}
int wh3r_scan_gate(HANDLE admission,const char domain[49],const wh3wg_grant *trusted,
 const wh_binding *binding,const wh_gates *gates,const wh3r_scan *ack,wh3r_gate_scan *out) {
 rimage image={0};unsigned char expected[3u*WH3R_GATE_RECORD_BYTES];char zero[65],manifest[65],initial[65],begin[65];
 size_t k,n,keep=0,target=0;int ok=0,clean=0;unsigned sequence,event;
 if(out)memset(out,0,sizeof(*out));
 if(!out||!domain||!trusted||trusted->generation||!binding||!gates||!ack)return 0;
 for(k=0;k<48;k++)if(!rhx((unsigned char)domain[k]))return 0;if(domain[48])return 0;
 if(!rgate_ack(binding,gates,ack,manifest)||!rimage_read(admission,sizeof(expected),&image)||
    image.size<WH3R_GATE_RECORD_BYTES)goto done;
 memset(zero,'0',64);zero[64]=0;
 rgate_record(expected,'I',1,0,domain,zero,0,zero,zero);
 memcpy(initial,expected+280,64);initial[64]=0;
 if(memcmp(initial,trusted->seal,65)||memcmp(image.data,expected,WH3R_GATE_RECORD_BYTES))goto done;
 rgate_record(expected+WH3R_GATE_RECORD_BYTES,'B',2,1,domain,manifest,0,zero,initial);
 memcpy(begin,expected+WH3R_GATE_RECORD_BYTES+280,64);begin[64]=0;
 n=image.size-WH3R_GATE_RECORD_BYTES;
 if(!n){
  if(ack->count||ack->journal_bytes||ack->intent_bytes)goto done;
  keep=target=WH3R_GATE_RECORD_BYTES;
 }else if(n<=WH3R_GATE_RECORD_BYTES){
  if(memcmp(image.data+WH3R_GATE_RECORD_BYTES,expected+WH3R_GATE_RECORD_BYTES,n))goto done;
  if(n<WH3R_GATE_RECORD_BYTES&&(ack->count||ack->journal_bytes||ack->intent_bytes))goto done;
  keep=n==WH3R_GATE_RECORD_BYTES?2u*WH3R_GATE_RECORD_BYTES:WH3R_GATE_RECORD_BYTES;
  target=2u*WH3R_GATE_RECORD_BYTES;
 }else{
  if(memcmp(image.data+WH3R_GATE_RECORD_BYTES,expected+WH3R_GATE_RECORD_BYTES,WH3R_GATE_RECORD_BYTES)||
     ack->unack_tail||ack->journal_bytes!=ack->journal_keep_bytes||ack->intent_bytes!=ack->intent_keep_bytes||
     ack->count<2||sscanf(ack->lines[ack->count-1],"EXRWH2 %u %u",&sequence,&event)!=2||event!=12)goto done;
  rgate_record(expected+2u*WH3R_GATE_RECORD_BYTES,'C',3,1,domain,manifest,ack->tip.line_count,ack->tip.last_line_sha,begin);
  n-=WH3R_GATE_RECORD_BYTES;
  if(n>WH3R_GATE_RECORD_BYTES||memcmp(image.data+2u*WH3R_GATE_RECORD_BYTES,expected+2u*WH3R_GATE_RECORD_BYTES,n))goto done;
  clean=n==WH3R_GATE_RECORD_BYTES;
  keep=target=clean?3u*WH3R_GATE_RECORD_BYTES:2u*WH3R_GATE_RECORD_BYTES;
 }
 if(!rimage_again(admission,sizeof(expected),&image))goto done;
 out->identity=image.id;out->bytes=image.size;memcpy(out->sha256,image.sha,65);
 out->gate_keep_bytes=keep;out->target_bytes=target;memcpy(out->target,expected,target);
 out->needs_write=image.size!=target||memcmp(image.data,expected,target);out->complete_clean=clean;ok=1;
done:
 free(image.data);if(!ok){memset(out,0,sizeof(*out));SetLastError(ERROR_INVALID_DATA);}return ok;
}
