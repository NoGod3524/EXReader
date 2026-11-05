/* SPDX-License-Identifier: MIT */
#include <exr_pc02_repair_scan.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

#define RS_STATE 368u
#define RS_STATE_SEAL 304u
#define RS_MAX_STATES 4096u
#define RS_HEAD 464u
#define RS_HEAD_RECORD 272u
#define RS_MAX_ACK 256u
#define RS_ENVELOPE 568u
#define RS_FLOOR 352u
#define RS_ACK 296u

static uint64_t rs64(const unsigned char *p){
 uint64_t v=0;
 for(unsigned k=0;k<8;k++)v|=(uint64_t)p[k]<<(k*8);
 return v;
}
static void rsput64(unsigned char *p,uint64_t v){
 for(unsigned k=0;k<8;k++)p[k]=(unsigned char)(v>>(k*8));
}
static pc02_identity rsid(const unsigned char *p){
 pc02_identity id={rs64(p),rs64(p+8)};
 return id;
}
static int rsame(pc02_identity a,pc02_identity b){
 return a.device==b.device&&a.inode==b.inode;
}
static void rsputid(unsigned char *p,pc02_identity id){
 rsput64(p,id.device);
 rsput64(p+8,id.inode);
}
static int rshex(const unsigned char *p){
 for(unsigned k=0;k<64;k++)if(!((p[k]>='0'&&p[k]<='9')||(p[k]>='a'&&p[k]<='f')))return 0;
 return 1;
}
static int rszero(const unsigned char *p){
 for(unsigned k=0;k<64;k++)if(p[k]!='0')return 0;
 return 1;
}
static int rsdigest(const char p[65],int nonzero){
 return p&&p[64]==0&&rshex((const unsigned char *)p)&&
  (!nonzero||!rszero((const unsigned char *)p));
}
static void rscopy(char out[65],const unsigned char *p){
 memcpy(out,p,64);
 out[64]=0;
}
static int rssealed(const unsigned char *raw,size_t prefix,const char magic[8]){
 char digest[65];
 if(memcmp(raw,magic,8)||!rshex(raw+prefix))return 0;
 wh_sha256_hex(raw,prefix,digest);
 return !memcmp(digest,raw+prefix,64);
}
static void rsseal(unsigned char *raw,size_t prefix){
 char digest[65];
 wh_sha256_hex(raw,prefix,digest);
 memcpy(raw+prefix,digest,64);
}
static int rsblob(const pc02rs_blob *blob){
 return blob&&blob->identity.inode&&blob->data&&blob->bytes;
}
static int rsstate_record(const unsigned char *r,pc02rs_state *s){
 static const unsigned char zero[7]={0};
 char previous[65];
 uint64_t generation;
 pc02_identity target;
 if(!rssealed(r,RS_STATE_SEAL,"PC02S001")||memcmp(r+9,zero,7)||
    rs64(r+16)!=s->count+1||!rshex(r+32)||!rshex(r+96)||!rshex(r+160))return 0;
 if(s->count)memcpy(previous,s->seal,65);
 else{memset(previous,'0',64);previous[64]=0;}
 if(memcmp(r+240,previous,64))return 0;
 generation=rs64(r+24);
 target=rsid(r+224);
 if(!target.inode)return 0;
 if(!s->count){
  if(r[8]!='I'||generation||!rszero(r+32)||!rszero(r+96)||!rszero(r+160))return 0;
 }else if(r[8]=='B'){
  if((s->kind!='I'&&s->kind!='C')||s->generation==UINT64_MAX||
     generation!=s->generation+1||rszero(r+32)||rszero(r+96)||!rszero(r+160)||
     !rsame(target,s->target))return 0;
  memcpy(s->previous_clean,previous,65);
  s->pending.generation=generation;
  rscopy(s->pending.manifest,r+32);
  rscopy(s->pending.input,r+96);
  rscopy(s->pending.seal,r+RS_STATE_SEAL);
 }else if(r[8]=='C'){
  if(s->kind!='B'||generation!=s->generation||
     memcmp(r+32,s->pending.manifest,64)||memcmp(r+96,s->pending.input,64)||rszero(r+160))return 0;
 }else return 0;
 s->count++;
 s->sequence=s->count;
 s->kind=r[8];
 s->generation=generation;
 s->target=target;
 rscopy(s->seal,r+RS_STATE_SEAL);
 rscopy(s->terminal,r+160);
 return 1;
}
int pc02rs_state_prefix(const pc02rs_blob *blob,pc02rs_state *out){
 pc02rs_state scan={0};
 if(out)memset(out,0,sizeof(*out));
 if(!out||!rsblob(blob)||blob->bytes<RS_STATE||
    blob->bytes>(size_t)RS_STATE*RS_MAX_STATES)return 0;
 scan.keep_bytes=blob->bytes/RS_STATE*RS_STATE;
 scan.tail_bytes=blob->bytes-scan.keep_bytes;
 for(size_t at=0;at<scan.keep_bytes;at+=RS_STATE){
  if(!rsstate_record(blob->data+at,&scan))return 0;
 }
 wh_sha256_hex(blob->data,blob->bytes,scan.raw_sha256);
 wh_sha256_hex(blob->data,scan.keep_bytes,scan.prefix_sha256);
 *out=scan;
 return 1;
}
int pc02rs_state_next(const pc02rs_state *s,unsigned char kind,
 const char manifest[65],const char input[65],const char terminal[65],
 const pc02_identity *target,unsigned char out[368]){
 unsigned char r[RS_STATE]={0};
 pc02rs_state check;
 uint64_t generation;
 if(out)memset(out,0,RS_STATE);
 if(!s||!out||!target||!target->inode||!s->count||s->count>=RS_MAX_STATES||
    s->sequence!=s->count||!rsdigest(s->seal,1)||!rsdigest(manifest,1)||
    !rsdigest(input,1)||!rsdigest(terminal,0))return 0;
 if(kind=='B'){
  if((s->kind!='I'&&s->kind!='C')||s->generation==UINT64_MAX||
     s->sequence+1>RS_MAX_STATES-2||!rsame(*target,s->target)||
     !rszero((const unsigned char *)terminal))return 0;
  generation=s->generation+1;
 }else if(kind=='C'){
  if(s->kind!='B'||s->generation!=s->pending.generation||
     memcmp(manifest,s->pending.manifest,65)||memcmp(input,s->pending.input,65)||
     rszero((const unsigned char *)terminal))return 0;
  generation=s->generation;
 }else return 0;
 memcpy(r,"PC02S001",8);
 r[8]=kind;
 rsput64(r+16,s->sequence+1);
 rsput64(r+24,generation);
 memcpy(r+32,manifest,64);
 memcpy(r+96,input,64);
 memcpy(r+160,terminal,64);
 rsputid(r+224,*target);
 memcpy(r+240,s->seal,64);
 rsseal(r,RS_STATE_SEAL);
 check=*s;
 if(!rsstate_record(r,&check))return 0;
 memcpy(out,r,sizeof(r));
 return 1;
}
static int rssame_state(const pc02rs_state *a,const pc02rs_state *b){
 return a->count==b->count&&a->keep_bytes==b->keep_bytes&&a->tail_bytes==b->tail_bytes&&
  a->kind==b->kind&&a->sequence==b->sequence&&a->generation==b->generation&&
  rsame(a->target,b->target)&&!memcmp(a->seal,b->seal,65)&&
  !memcmp(a->previous_clean,b->previous_clean,65)&&!memcmp(a->terminal,b->terminal,65)&&
  !memcmp(a->raw_sha256,b->raw_sha256,65)&&!memcmp(a->prefix_sha256,b->prefix_sha256,65)&&
  a->pending.generation==b->pending.generation&&
  !memcmp(a->pending.seal,b->pending.seal,65)&&
  !memcmp(a->pending.manifest,b->pending.manifest,65)&&
  !memcmp(a->pending.input,b->pending.input,65);
}
int pc02rs_state_tail(const pc02rs_blob *blob,const pc02rs_state *known,
 const unsigned char expected[368]){
 pc02rs_state scan;
 unsigned char next[RS_STATE];
 char manifest[65],input[65],terminal[65];
 pc02_identity target;
 if(!known||!expected||!pc02rs_state_prefix(blob,&scan)||!rssame_state(known,&scan)||
    !scan.tail_bytes||scan.tail_bytes>=RS_STATE)return 0;
 rscopy(manifest,expected+32);
 rscopy(input,expected+96);
 rscopy(terminal,expected+160);
 target=rsid(expected+224);
 if(!pc02rs_state_next(&scan,expected[8],manifest,input,terminal,&target,next)||
    memcmp(next,expected,RS_STATE))return 0;
 return !memcmp(blob->data+scan.keep_bytes,expected,scan.tail_bytes);
}
static int rsbinding(const unsigned char raw[304]){
 if(!rssealed(raw,240,"PC02B001")||!rshex(raw+96)||rszero(raw+96)||
    !rshex(raw+160)||rszero(raw+160))return 0;
 const size_t offsets[]={8,24,40,56,72,224};
 for(size_t k=0;k<sizeof(offsets)/sizeof(offsets[0]);k++)if(!rsid(raw+offsets[k]).inode)return 0;
 return 1;
}
static int rscontext(const unsigned char header[464],const pc02_pending_record *exact){
 unsigned char begin[RS_STATE]={0};
 char seal[65];
 uint64_t generation;
 if(!header||!exact||!exact->generation||!rsdigest(exact->seal,1)||
    !rsdigest(exact->manifest,1)||!rsdigest(exact->input,1)||
    !rssealed(header,400,"PC02F001")||!rsbinding(header+80)||
    !rsid(header+384).inode||rs64(header+8)!=exact->generation||
    memcmp(header+16,exact->input,64))return 0;
 generation=rs64(header+80+88);
 if(generation==UINT64_MAX||generation+1!=exact->generation||
    exact->generation>(RS_MAX_STATES-2)/2)return 0;
 /* Reconstruct the original B solely from the independently registered
    previous clean Binding and the caller's exact manifest/input descriptor. */
 memcpy(begin,"PC02S001",8);
 begin[8]='B';
 rsput64(begin+16,exact->generation*2);
 rsput64(begin+24,exact->generation);
 memcpy(begin+32,exact->manifest,64);
 memcpy(begin+96,exact->input,64);
 memset(begin+160,'0',64);
 memcpy(begin+224,header+80+40,16);
 memcpy(begin+240,header+80+96,64);
 wh_sha256_hex(begin,RS_STATE_SEAL,seal);
 return !memcmp(seal,exact->seal,65);
}
static int rsack(const pc02rs_blob *blob,size_t slot,const pc02_pending_record *exact,
 char *line,size_t *line_bytes,char line_sha[65],char raw_sha[65]){
 const unsigned char *r;
 uint64_t size;
 char digest[65];
 if(!rsblob(blob)||!line||!line_bytes||blob->bytes<RS_ACK+1+64||
    blob->bytes>RS_ACK+2047+64)return 0;
 r=blob->data;
 size=rs64(r+224);
 if(memcmp(r,"PC02ACK1",8)||!rsame(rsid(r+8),blob->identity)||rs64(r+24)!=slot||
    memcmp(r+32,exact->manifest,64)||memcmp(r+96,exact->input,64)||
    memcmp(r+160,exact->seal,64)||size<1||size>2047||
    blob->bytes!=RS_ACK+(size_t)size+64||memchr(r+RS_ACK,0,(size_t)size)||
    !rshex(r+232)||!rshex(r+blob->bytes-64))return 0;
 wh_sha256_hex(r+RS_ACK,(size_t)size,digest);
 if(memcmp(digest,r+232,64))return 0;
 wh_sha256_hex(r,blob->bytes-64,digest);
 if(memcmp(digest,r+blob->bytes-64,64))return 0;
 wh_sha256_hex(r,blob->bytes,raw_sha);
 rscopy(line_sha,r+232);
 memcpy(line,r+RS_ACK,(size_t)size);
 line[size]=0;
 *line_bytes=(size_t)size;
 return 1;
}
static int rsfloor(const pc02rs_blob *blob,size_t slot,const pc02rs_blob *ack,
 const char line_sha[65],const char ack_sha[65],const char previous_line[65],
 const char previous_floor[65],const unsigned char header[464],
 const pc02_pending_record *exact,char whole_sha[65]){
 const unsigned char *r,*p;
 char digest[65];
 if(!rsblob(blob)||blob->bytes!=RS_ENVELOPE+RS_FLOOR+64)return 0;
 r=blob->data;
 p=r+RS_ENVELOPE;
 if(memcmp(r,"PC02M001",8)||rs64(r+8)!=3||rs64(r+16)!=exact->generation||
    rs64(r+24)!=RS_FLOOR||!rsame(rsid(r+32),blob->identity)||
    memcmp(r+48,header+80,304)||memcmp(r+352,exact->input,64)||
    memcmp(r+416,exact->seal,64)||rs64(r+480)!=slot||!rshex(r+488)||
    !rsame(rsid(r+552),rsid(header+384))||!rshex(r+blob->bytes-64))return 0;
 wh_sha256_hex(p,RS_FLOOR,digest);
 if(memcmp(digest,r+488,64))return 0;
 wh_sha256_hex(r,blob->bytes-64,digest);
 if(memcmp(digest,r+blob->bytes-64,64))return 0;
 if(rs64(p)!=slot-1||memcmp(p+8,previous_line,64)||memcmp(p+72,previous_floor,64)||
    rs64(p+136)!=slot||memcmp(p+144,line_sha,64)||memcmp(p+208,exact->manifest,64)||
    !rsame(rsid(p+272),ack->identity)||memcmp(p+288,ack_sha,64))return 0;
 wh_sha256_hex(r,blob->bytes,whole_sha);
 return 1;
}
int pc02rs_transaction(const pc02rs_blob *head,const unsigned char expected_header[464],
 const pc02rs_blob *floors,size_t floor_count,const pc02rs_blob *acks,size_t ack_count,
 const wh_binding *binding,const wh_gates *gates,const pc02_pending_record *exact,pc02rs_tx *out){
 pc02rs_tx result={0};
 char manifest[EXR_WH_LINE_MAX],digest[65],previous_line[65],previous_floor[65],previous_head[65];
 char line_sha[RS_MAX_ACK][65],ack_sha[RS_MAX_ACK][65],floor_sha[RS_MAX_ACK][65];
 const char *lines[RS_MAX_ACK];
 char *storage=NULL;
 size_t head_count,head_keep,head_tail;
 int ok=0;
 if(out)memset(out,0,sizeof(*out));
 if(!out||!rsblob(head)||!expected_header||head->bytes<RS_HEAD||
    head->bytes>RS_HEAD+RS_HEAD_RECORD*RS_MAX_ACK||
    floor_count>RS_MAX_ACK||ack_count>RS_MAX_ACK||floor_count>ack_count||
    ack_count-floor_count>1||(floor_count&&!floors)||(ack_count&&!acks)||
    !binding||!gates||!rscontext(expected_header,exact)||
    memcmp(head->data,expected_header,RS_HEAD)||
    !rsame(rsid(expected_header+384),head->identity)||
    !wh_manifest(binding,gates,manifest))return 0;
 wh_sha256_hex(manifest,strlen(manifest),digest);
 if(memcmp(digest,exact->manifest,65))return 0;
 head_count=(head->bytes-RS_HEAD)/RS_HEAD_RECORD;
 head_keep=RS_HEAD+head_count*RS_HEAD_RECORD;
 head_tail=head->bytes-head_keep;
 if(head_count>floor_count||floor_count-head_count>1||
    ((head_count<floor_count||head_tail)&&ack_count!=floor_count)||
    (head_tail&&head_count==floor_count))return 0;
 if(ack_count){
  storage=malloc(ack_count*EXR_WH_LINE_MAX);
  if(!storage)return 0;
 }
 for(size_t k=0;k<ack_count;k++){
  size_t count=0;
  char *line=storage+k*EXR_WH_LINE_MAX;
  if(!rsack(&acks[k],k+1,exact,line,&count,line_sha[k],ack_sha[k]))goto done;
  lines[k]=line;
  if(!k&&(count!=strlen(manifest)||memcmp(line,manifest,count)))goto done;
 }
 if(ack_count&&!wh_journal_check(binding,gates,lines,ack_count))goto done;
 memset(previous_line,'0',64);
 previous_line[64]=0;
 memset(previous_floor,'0',64);
 previous_floor[64]=0;
 for(size_t k=0;k<floor_count;k++){
  if(!rsfloor(&floors[k],k+1,&acks[k],line_sha[k],ack_sha[k],previous_line,previous_floor,
              expected_header,exact,floor_sha[k]))goto done;
  memcpy(previous_line,line_sha[k],65);
  memcpy(previous_floor,floor_sha[k],65);
 }
 rscopy(previous_head,expected_header+400);
 for(size_t k=0;k<head_count;k++){
  const unsigned char *record=head->data+RS_HEAD+k*RS_HEAD_RECORD;
  if(!rssealed(record,208,"PC02H001")||rs64(record+8)!=k+1||
     memcmp(record+16,line_sha[k],64)||memcmp(record+80,floor_sha[k],64)||
     memcmp(record+144,previous_head,64))goto done;
  rscopy(previous_head,record+208);
 }
 if(head_count<floor_count){
  memcpy(result.next_head,"PC02H001",8);
  rsput64(result.next_head+8,head_count+1);
  memcpy(result.next_head+16,line_sha[head_count],64);
  memcpy(result.next_head+80,floor_sha[head_count],64);
  memcpy(result.next_head+144,previous_head,64);
  rsseal(result.next_head,208);
  if(head_tail&&memcmp(head->data+head_keep,result.next_head,head_tail))goto done;
 }
 for(size_t k=1;k<ack_count;k++){
  unsigned sequence=0,event=0;
  if(sscanf(lines[k],"EXRWH2 %u %u",&sequence,&event)!=2||sequence!=k)goto done;
  if(event==9)result.publish_intent=1;
  if(event==11)result.committed=1;
  if(event==14)result.aborted=1;
  if(k+1==ack_count&&event==12)result.terminal=1;
 }
 result.ack_count=ack_count;
 result.floor_count=floor_count;
 result.head_count=head_count;
 result.head_keep_bytes=head_keep;
 result.head_tail_bytes=head_tail;
 memcpy(result.manifest_sha256,digest,65);
 if(ack_count)memcpy(result.last_line_sha256,line_sha[ack_count-1],65);
 else{memset(result.last_line_sha256,'0',64);result.last_line_sha256[64]=0;}
 wh_sha256_hex(head->data,head->bytes,result.head_raw_sha256);
 wh_sha256_hex(head->data,head_keep,result.head_prefix_sha256);
 *out=result;
 ok=1;
done:
 free(storage);
 return ok;
}
