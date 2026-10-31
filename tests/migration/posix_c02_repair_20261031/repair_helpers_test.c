/* SPDX-License-Identifier: MIT */
#define _GNU_SOURCE 1
#define _DARWIN_C_SOURCE 1
#include <exr_pc02_repair_scan.h>
#include <exr_pc02_repair_store.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#if defined(__APPLE__)
#include <sys/acl.h>
#include <membership.h>
#include <uuid/uuid.h>
#elif defined(__linux__)
#include <sys/xattr.h>
#endif
#define S 368u
#define H 464u
#define R 272u
#define N 13u
#define F 984u
#define A 2408u
#define LIMIT (4u*1024u*1024u)
static unsigned cases,checks,failed,case_checks,case_failed;
static const char *case_name;
static void done_case(void){
 if(!case_name)return;
 printf("{\"case\":\"%s\",\"checks\":%u,\"failed\":%u}\n",case_name,case_checks,case_failed);
 fflush(stdout);
 case_name=NULL;
}
static void begin_case(const char *name){
 done_case();cases++;case_name=name;case_checks=case_failed=0;
}
static void check_at(int value,const char *expr,unsigned line){
 checks++;case_checks++;
 if(!value){
  failed++;case_failed++;
  fprintf(stderr,"FAIL line %u case %s: %s errno %d\n",line,case_name,expr,errno);
 }
}
#define CHECK(x) check_at(!!(x),#x,__LINE__)
#define REQUIRE(x) do{if(!(x)){fprintf(stderr,"FIXTURE line %u: %s errno %d\n",__LINE__,#x,errno);exit(2);}}while(0)
static uint64_t get64(const unsigned char *p){
 uint64_t n=0;
 for(unsigned k=0;k<8;k++)n|=(uint64_t)p[k]<<(8*k);
 return n;
}
static void put64(unsigned char *p,uint64_t n){
 for(unsigned k=0;k<8;k++)p[k]=(unsigned char)(n>>(8*k));
}
static pc02_identity id(unsigned n){pc02_identity value={17,n};return value;}
static void putid(unsigned char *p,pc02_identity v){put64(p,v.device);put64(p+8,v.inode);}
static int same_id(pc02_identity a,pc02_identity b){return a.device==b.device&&a.inode==b.inode;}
static void hexfill(char out[65],char c){memset(out,c,64);out[64]=0;}
static void seal(unsigned char *p,size_t n){
 char digest[65];wh_sha256_hex(p,n,digest);memcpy(p+n,digest,64);
}
static void change_hex(unsigned char *p){*p=*p=='a'?'b':'a';}
static void state_bytes(unsigned char out[S],unsigned char kind,uint64_t sequence,uint64_t generation,
 const char *manifest,const char *input,const char *terminal,pc02_identity target,const char *previous){
 memset(out,0,S);memcpy(out,"PC02S001",8);out[8]=kind;
 put64(out+16,sequence);put64(out+24,generation);
 memcpy(out+32,manifest,64);memcpy(out+96,input,64);memcpy(out+160,terminal,64);
 putid(out+224,target);memcpy(out+240,previous,64);seal(out,304);
}
typedef struct {
 wh_binding binding;
 wh_gates gates;
 pc02_pending_record exact;
 unsigned char state[3*S],origin[304],header[H],head[H+N*R],ack[N][A],floor[N][F];
 pc02rs_blob acks[N],floors[N],head_blob;
 char lines[N][EXR_WH_LINE_MAX];
 size_t line_bytes[N];
} fixture;
static void rebind(fixture *f){
 for(unsigned k=0;k<N;k++){
  f->acks[k].identity=id(200+k);f->acks[k].data=f->ack[k];
  f->acks[k].bytes=296+f->line_bytes[k]+64;
  f->floors[k].identity=id(300+k);f->floors[k].data=f->floor[k];f->floors[k].bytes=F;
 }
 f->head_blob.identity=id(105);f->head_blob.data=f->head;f->head_blob.bytes=sizeof(f->head);
}
static void fixture_make(fixture *f){
 char zero[65],prior[65],token[49],snap[65],content[65],digest[65],whole_floor[65],head_seal[65];
 const char *pointers[N];
 memset(f,0,sizeof(*f));hexfill(zero,'0');
 strcpy(f->binding.source,SOURCE_SHA);strcpy(f->binding.run,"1");strcpy(f->binding.attempt,"1");
 hexfill(f->binding.artifact,'a');hexfill(f->binding.provider,'b');strcpy(f->binding.sdk,"3.42.0-8357eafa");
#ifdef __APPLE__
 strcpy(f->binding.platform,"macos-apfs");
#else
 strcpy(f->binding.platform,"linux-ext4");
#endif
 const char *names[]={"admission","publisher","recovery","observer","fault"};
 char *gates[]={f->gates.admission,f->gates.publisher,f->gates.recovery,f->gates.observer,f->gates.fault};
 for(unsigned k=0;k<5;k++)wh_sha256_hex(names[k],strlen(names[k]),gates[k]);
 REQUIRE(wh_manifest(&f->binding,&f->gates,f->lines[0]));
 f->line_bytes[0]=strlen(f->lines[0]);
 wh_sha256_hex(f->lines[0],f->line_bytes[0],f->exact.manifest);
 memcpy(prior,f->exact.manifest,65);memset(token,'1',48);token[48]=0;
 hexfill(snap,'d');hexfill(content,'e');
 for(unsigned event=1;event<=12;event++){
  char prefix[EXR_WH_LINE_MAX];
  int n=snprintf(prefix,sizeof(prefix),"EXRWH2 %u %u %s %s %s %s %s %s",
   event,event,event>=2?token:"-",event>=6?token:"-",event>=4?snap:"-",
   event>=5?content:"-",prior,f->exact.manifest);
  REQUIRE(n>0&&(size_t)n<sizeof(prefix)-66);
  wh_sha256_hex(prefix,(size_t)n,digest);
  memcpy(f->lines[event],prefix,(size_t)n);f->lines[event][n]=' ';
  memcpy(f->lines[event]+n+1,digest,65);f->line_bytes[event]=(size_t)n+65;
  memcpy(prior,digest,65);
 }
 for(unsigned k=0;k<N;k++)pointers[k]=f->lines[k];
 REQUIRE(wh_journal_check(&f->binding,&f->gates,pointers,N));
 hexfill(f->exact.input,'c');f->exact.generation=1;
 state_bytes(f->state,'I',1,0,zero,zero,zero,id(100),zero);
 char initial[65],pending[65],terminal[65];
 memcpy(initial,f->state+304,64);initial[64]=0;
 state_bytes(f->state+S,'B',2,1,f->exact.manifest,f->exact.input,zero,id(100),initial);
 memcpy(pending,f->state+S+304,64);pending[64]=0;memcpy(f->exact.seal,pending,65);
 wh_sha256_hex(f->lines[N-1],f->line_bytes[N-1],terminal);
 state_bytes(f->state+2*S,'C',3,1,f->exact.manifest,f->exact.input,terminal,id(101),pending);
 memcpy(f->origin,"PC02B001",8);
 putid(f->origin+8,id(1));putid(f->origin+24,id(2));putid(f->origin+40,id(100));
 putid(f->origin+56,id(3));putid(f->origin+72,id(4));put64(f->origin+88,0);
 memcpy(f->origin+96,initial,64);memset(f->origin+160,'f',64);putid(f->origin+224,id(5));seal(f->origin,240);
 memcpy(f->header,"PC02F001",8);put64(f->header+8,1);memcpy(f->header+16,f->exact.input,64);
 memcpy(f->header+80,f->origin,304);putid(f->header+384,id(105));seal(f->header,400);
 memcpy(f->head,f->header,H);memcpy(whole_floor,zero,65);memcpy(prior,zero,65);
 memcpy(head_seal,f->header+400,64);head_seal[64]=0;
 for(unsigned k=0;k<N;k++){
  unsigned char *a=f->ack[k],*m=f->floor[k],*p=m+568,*h=f->head+H+k*R;
  memcpy(a,"PC02ACK1",8);putid(a+8,id(200+k));put64(a+24,k+1);
  memcpy(a+32,f->exact.manifest,64);memcpy(a+96,f->exact.input,64);memcpy(a+160,f->exact.seal,64);
  put64(a+224,f->line_bytes[k]);wh_sha256_hex(f->lines[k],f->line_bytes[k],digest);
  memcpy(a+232,digest,64);memcpy(a+296,f->lines[k],f->line_bytes[k]);seal(a,296+f->line_bytes[k]);
  memcpy(m,"PC02M001",8);put64(m+8,3);put64(m+16,1);put64(m+24,352);putid(m+32,id(300+k));
  memcpy(m+48,f->origin,304);memcpy(m+352,f->exact.input,64);memcpy(m+416,f->exact.seal,64);
  put64(m+480,k+1);putid(m+552,id(105));put64(p,k);memcpy(p+8,prior,64);
  memcpy(p+72,whole_floor,64);put64(p+136,k+1);memcpy(p+144,digest,64);
  memcpy(p+208,f->exact.manifest,64);putid(p+272,id(200+k));
  wh_sha256_hex(a,296+f->line_bytes[k]+64,whole_floor);memcpy(p+288,whole_floor,64);
  wh_sha256_hex(p,352,whole_floor);memcpy(m+488,whole_floor,64);seal(m,F-64);
  wh_sha256_hex(m,F,whole_floor);memcpy(h,"PC02H001",8);put64(h+8,k+1);
  memcpy(h+16,digest,64);memcpy(h+80,whole_floor,64);memcpy(h+144,head_seal,64);seal(h,208);
  memcpy(prior,digest,65);memcpy(head_seal,h+208,64);head_seal[64]=0;
 }
 rebind(f);
}
static int transaction(fixture *f,size_t a,size_t floors,size_t bytes,pc02rs_tx *out){
 f->head_blob.bytes=bytes;
 return pc02rs_transaction(&f->head_blob,f->header,f->floors,floors,f->acks,a,&f->binding,&f->gates,&f->exact,out);
}
static void save_vector(int directory,const char *name,const void *data,size_t bytes){
 int fd=openat(directory,name,O_RDWR|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
 REQUIRE(fd>=0);
 size_t done=0;
 while(done<bytes){
  ssize_t n=write(fd,(const unsigned char *)data+done,bytes-done);REQUIRE(n>0);done+=(size_t)n;
 }
 REQUIRE(!fsync(fd));REQUIRE(!close(fd));
}
static void state_tests(fixture *f,int vectors){
 unsigned char raw[3*S],expected[S],changed[S];
 pc02rs_state s,known;pc02rs_blob blob={id(4),raw,3*S};
 memcpy(raw,f->state,sizeof(raw));
 begin_case("valid-complete-I-B-C");
 CHECK(pc02rs_state_prefix(&blob,&s));
 CHECK(s.count==3&&s.kind=='C'&&s.generation==1&&s.tail_bytes==0&&s.keep_bytes==3*S);
 CHECK(same_id(s.target,id(101))&&s.pending.generation==1&&!memcmp(s.pending.seal,f->exact.seal,65));
 char digest[65];wh_sha256_hex(raw,sizeof(raw),digest);
 CHECK(!memcmp(digest,s.raw_sha256,65)&&!memcmp(digest,s.prefix_sha256,65));
 save_vector(vectors,"state-canonical.bin",raw,sizeof(raw));
 begin_case("partial-B-each-byte-prefix");
 for(size_t tail=1;tail<S;tail++){
  memcpy(raw,f->state,sizeof(raw));blob.bytes=S+tail;
  CHECK(pc02rs_state_prefix(&blob,&s)&&s.count==1&&s.tail_bytes==tail&&s.kind=='I');
  CHECK(pc02rs_state_tail(&blob,&s,f->state+S));raw[S+tail-1]^=1;
  CHECK(pc02rs_state_prefix(&blob,&s));CHECK(!pc02rs_state_tail(&blob,&s,f->state+S));
 }
 begin_case("partial-C-each-byte-prefix");
 for(size_t tail=1;tail<S;tail++){
  memcpy(raw,f->state,sizeof(raw));blob.bytes=2*S+tail;
  CHECK(pc02rs_state_prefix(&blob,&s)&&s.count==2&&s.tail_bytes==tail&&s.kind=='B');
  CHECK(pc02rs_state_tail(&blob,&s,f->state+2*S));raw[2*S+tail-1]^=1;
  CHECK(pc02rs_state_prefix(&blob,&s));CHECK(!pc02rs_state_tail(&blob,&s,f->state+2*S));
 }
 begin_case("initial-I-partial-refused");
 memcpy(raw,f->state,sizeof(raw));blob.bytes=S-1;CHECK(!pc02rs_state_prefix(&blob,&s));
 blob.bytes=0;CHECK(!pc02rs_state_prefix(&blob,&s));
 begin_case("complete-state-resealed-contradictions");
 const size_t offsets[]={S+9,S+16,S+24,S+232,S+240,2*S+32,2*S+96,2*S+160};
 for(size_t k=0;k<sizeof(offsets)/sizeof(offsets[0]);k++){
  memcpy(raw,f->state,sizeof(raw));raw[offsets[k]]^=1;
  size_t record=offsets[k]/S;seal(raw+record*S,304);blob.bytes=record==2?3*S:2*S;
  CHECK(!pc02rs_state_prefix(&blob,&s));
 }
 memcpy(raw,f->state,sizeof(raw));memset(raw+2*S+160,'0',64);seal(raw+2*S,304);
 blob.bytes=sizeof(raw);CHECK(!pc02rs_state_prefix(&blob,&s));
 save_vector(vectors,"state-complete-contradiction.bin",raw,sizeof(raw));
 begin_case("complete-clean-never-retired-as-partial");
 memcpy(raw,f->state,sizeof(raw));blob.bytes=sizeof(raw);
 CHECK(pc02rs_state_prefix(&blob,&s)&&s.count==3&&s.kind=='C');
 CHECK(!pc02rs_state_tail(&blob,&s,f->state+2*S));
 known=s;known.count=2;known.keep_bytes=2*S;known.tail_bytes=S;
 CHECK(!pc02rs_state_tail(&blob,&known,f->state+2*S));
 raw[3*S-1]^=1;CHECK(!pc02rs_state_prefix(&blob,&s));
 begin_case("state-next-canonical-B-C-and-illegal-tuples");
 memcpy(raw,f->state,sizeof(raw));blob.bytes=S;REQUIRE(pc02rs_state_prefix(&blob,&s));
 char zero[65],terminal[65];hexfill(zero,'0');memcpy(terminal,f->state+2*S+160,64);terminal[64]=0;
 pc02_identity target=id(100);
 CHECK(pc02rs_state_next(&s,'B',f->exact.manifest,f->exact.input,zero,&target,expected));
 CHECK(!memcmp(expected,f->state+S,S));target=id(999);
 CHECK(!pc02rs_state_next(&s,'B',f->exact.manifest,f->exact.input,zero,&target,expected));target=id(100);
 CHECK(!pc02rs_state_next(&s,'B',f->exact.manifest,f->exact.input,terminal,&target,expected));
 CHECK(!pc02rs_state_next(&s,'C',f->exact.manifest,f->exact.input,terminal,&target,expected));
 blob.bytes=2*S;REQUIRE(pc02rs_state_prefix(&blob,&s));target=id(101);
 CHECK(pc02rs_state_next(&s,'C',f->exact.manifest,f->exact.input,terminal,&target,expected));
 CHECK(!memcmp(expected,f->state+2*S,S));
 CHECK(!pc02rs_state_next(&s,'C',f->exact.manifest,f->exact.input,zero,&target,expected));
 blob.bytes=2*S+1;REQUIRE(pc02rs_state_prefix(&blob,&s));memcpy(changed,f->state+2*S,S);
 put64(changed+16,4);seal(changed,304);CHECK(!pc02rs_state_tail(&blob,&s,changed));
 begin_case("state-finish-capacity-boundary");
 size_t count=4093;unsigned char *long_state=malloc((count+2)*S);REQUIRE(long_state);
 memcpy(long_state,f->state,S);char prior[65];memcpy(prior,f->state+304,64);prior[64]=0;
 for(size_t seq=2;seq<=count;seq++){
  unsigned char kind=(seq&1)?'C':'B';uint64_t generation=seq/2;
  state_bytes(long_state+(seq-1)*S,kind,seq,generation,f->exact.manifest,f->exact.input,
   kind=='B'?zero:terminal,id(100),prior);
  memcpy(prior,long_state+(seq-1)*S+304,64);prior[64]=0;
 }
 pc02rs_blob big={id(4),long_state,count*S};REQUIRE(pc02rs_state_prefix(&big,&s));target=id(100);
 CHECK(pc02rs_state_next(&s,'B',f->exact.manifest,f->exact.input,zero,&target,expected));
 memcpy(long_state+count*S,expected,S);big.bytes=(count+1)*S;REQUIRE(pc02rs_state_prefix(&big,&s));
 CHECK(pc02rs_state_next(&s,'C',f->exact.manifest,f->exact.input,terminal,&target,expected));
 memcpy(long_state+(count+1)*S,expected,S);big.bytes=(count+2)*S;REQUIRE(pc02rs_state_prefix(&big,&s));
 CHECK(s.count==4095&&s.kind=='C');CHECK(!pc02rs_state_next(&s,'B',f->exact.manifest,f->exact.input,zero,&target,expected));
 save_vector(vectors,"state-capacity-prefix.bin",long_state,big.bytes);free(long_state);
}
static void transaction_tests(fixture *f,int vectors){
 pc02rs_tx out;char digest[65];
 begin_case("complete-real-ACK-floor-head-chain");
 CHECK(transaction(f,N,N,sizeof(f->head),&out));
 CHECK(out.ack_count==N&&out.floor_count==N&&out.head_count==N&&!out.head_tail_bytes);
 CHECK(out.publish_intent&&out.committed&&!out.aborted&&out.terminal);
 save_vector(vectors,"head-canonical.bin",f->head,sizeof(f->head));
 save_vector(vectors,"head-expected-header.bin",f->header,sizeof(f->header));
 for(unsigned k=0;k<N;k++){
  char name[64];snprintf(name,sizeof(name),"ack-%03u.bin",k+1);save_vector(vectors,name,f->ack[k],f->acks[k].bytes);
  snprintf(name,sizeof(name),"floor-%03u.bin",k+1);save_vector(vectors,name,f->floor[k],F);
 }
 begin_case("head-partial-each-byte-prefix");
 for(size_t tail=1;tail<R;tail++){
  size_t at=H+(N-1)*R+tail-1;
  CHECK(transaction(f,N,N,H+(N-1)*R+tail,&out)&&out.head_count==N-1&&out.head_tail_bytes==tail);
  CHECK(!memcmp(out.next_head,f->head+H+(N-1)*R,R));f->head[at]^=1;
  CHECK(!transaction(f,N,N,H+(N-1)*R+tail,&out));f->head[at]^=1;
 }
 begin_case("head-without-next-floor-refused");CHECK(!transaction(f,N-1,N-1,H+(N-1)*R+1,&out));
 begin_case("complete-head-record-never-rollback");
 put64(f->head+H+(N-1)*R+8,N+1);seal(f->head+H+(N-1)*R,208);
 CHECK(!transaction(f,N,N,sizeof(f->head),&out));fixture_make(f);
 f->head[sizeof(f->head)-1]^=1;CHECK(!transaction(f,N,N,sizeof(f->head),&out));fixture_make(f);
 begin_case("production352-rejects272-component");
 unsigned char component[568+272+64];memcpy(component,f->floor[0],568+272);put64(component+24,272);
 wh_sha256_hex(component+568,272,digest);memcpy(component+488,digest,64);seal(component,sizeof(component)-64);
 f->floors[0].data=component;f->floors[0].bytes=sizeof(component);
 CHECK(!transaction(f,N,N,sizeof(f->head),&out));fixture_make(f);
 begin_case("ACK-floor-head-single-interruption-combinations");
 CHECK(transaction(f,N,N,H+(N-1)*R,&out)&&out.head_count==N-1&&!out.head_tail_bytes);
 CHECK(transaction(f,N,N-1,H+(N-1)*R,&out)&&out.ack_count==out.floor_count+1);
 CHECK(!transaction(f,N,N-2,H+(N-2)*R,&out));CHECK(!transaction(f,N,N,H+(N-2)*R,&out));
 CHECK(!transaction(f,N,N-1,H+(N-2)*R,&out));CHECK(!transaction(f,N,N-1,H+(N-2)*R+1,&out));
 begin_case("ACK-actual-native-ID-rebinding-refused");
 f->acks[0].identity.inode++;CHECK(!transaction(f,N,N,sizeof(f->head),&out));fixture_make(f);
 begin_case("ACK-resealed-input-and-Bseal-contradictions");
 change_hex(f->ack[0]+96);seal(f->ack[0],f->acks[0].bytes-64);
 CHECK(!transaction(f,N,N,sizeof(f->head),&out));fixture_make(f);
 change_hex(f->ack[0]+160);seal(f->ack[0],f->acks[0].bytes-64);
 CHECK(!transaction(f,N,N,sizeof(f->head),&out));fixture_make(f);
 begin_case("ACK-canonical-journal-FSM-required");
 unsigned char *ack=f->ack[1];REQUIRE(ack[296+9]=='1');ack[296+9]='3';
 wh_sha256_hex(ack+296,f->line_bytes[1],digest);memcpy(ack+232,digest,64);seal(ack,f->acks[1].bytes-64);
 CHECK(!transaction(f,N,N,sizeof(f->head),&out));fixture_make(f);
 begin_case("FLOOR-actual-ACK-ID-and-whole-bytes-required");
 putid(f->floor[0]+568+272,id(999));wh_sha256_hex(f->floor[0]+568,352,digest);
 memcpy(f->floor[0]+488,digest,64);seal(f->floor[0],F-64);
 CHECK(!transaction(f,N,N,sizeof(f->head),&out));fixture_make(f);
 change_hex(f->floor[0]+568+288);wh_sha256_hex(f->floor[0]+568,352,digest);
 memcpy(f->floor[0]+488,digest,64);seal(f->floor[0],F-64);
 CHECK(!transaction(f,N,N,sizeof(f->head),&out));fixture_make(f);
 begin_case("floor-head-envelope-native-ID-and-origin-refused");
 f->floors[0].identity.inode++;CHECK(!transaction(f,N,N,sizeof(f->head),&out));fixture_make(f);
 f->head_blob.identity.inode++;CHECK(!transaction(f,N,N,sizeof(f->head),&out));fixture_make(f);
 f->floor[0][48+40]^=1;seal(f->floor[0],F-64);
 CHECK(!transaction(f,N,N,sizeof(f->head),&out));fixture_make(f);
 begin_case("floor-hole-and-duplicate-slot-refused");
 pc02rs_blob first=f->floors[0];f->floors[0]=f->floors[1];
 CHECK(!transaction(f,N,N,sizeof(f->head),&out));f->floors[0]=first;f->acks[1]=f->acks[0];
 CHECK(!transaction(f,N,N,sizeof(f->head),&out));fixture_make(f);
}
static int new_raw(int directory,const char *name,const void *data,size_t bytes){
 int fd=openat(directory,name,O_RDWR|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);REQUIRE(fd>=0);
 size_t done=0;
 while(done<bytes){
  ssize_t n=pwrite(fd,(const unsigned char *)data+done,bytes-done,(off_t)done);REQUIRE(n>0);done+=(size_t)n;
 }
 REQUIRE(!fsync(fd));return fd;
}
static pc02_identity actual_id(int fd){
 struct stat s;REQUIRE(!fstat(fd,&s));pc02_identity v={(uint64_t)s.st_dev,(uint64_t)s.st_ino};return v;
}
static int blob_equals(int fd,const pc02rp_info *info,const unsigned char *raw,size_t bytes){
 pc02rp_blob b={0};
 int ok=pc02rp_read_raw(fd,LIMIT,&b)&&same_id(b.info.identity,info->identity)&&b.info.bytes==bytes&&
  b.bytes==bytes&&!memcmp(b.info.sha256,info->sha256,65)&&!memcmp(b.data,raw,bytes);
 pc02rp_free(&b);return ok;
}
static void wrapper_variant(int directory,const char *name,const pc02rp_blob *original,int variant){
 int fd=new_raw(directory,name,NULL,0);unsigned char *raw=malloc(original->bytes);REQUIRE(raw);
 memcpy(raw,original->data,original->bytes);putid(raw+32,actual_id(fd));
 if(variant==1)put64(raw+24,get64(raw+24)+1);
 if(variant==2)put64(raw+8,2);
 if(variant==3)put64(raw+16,2);
 if(variant==4)change_hex(raw+48);
 seal(raw,original->bytes-64);
 if(variant==0)raw[original->bytes-1]^=1;
 REQUIRE(pwrite(fd,raw,original->bytes,0)==(ssize_t)original->bytes);
 REQUIRE(!fsync(fd));REQUIRE(!close(fd));free(raw);
}
static int bad_acl(int fd,int directory){
#if defined(__linux__)
 unsigned char raw[44]={0};
 const uint32_t values[]={2,1,directory?7u:6u,UINT32_MAX,2,4,(uint32_t)geteuid()+1,
                         4,0,UINT32_MAX,16,0,UINT32_MAX,32,0,UINT32_MAX};
 size_t at=0;
 for(size_t k=0;k<sizeof(values)/sizeof(values[0]);k++){
  size_t bytes=k==0||k%3==0?4:2;
  for(size_t j=0;j<bytes;j++)raw[at++]=(unsigned char)(values[k]>>(8*j));
 }
 if(at!=sizeof(raw))return 0;
 return fsetxattr(fd,directory?"system.posix_acl_default":"system.posix_acl_access",raw,sizeof(raw),0)==0;
#elif defined(__APPLE__)
 (void)directory;
 acl_t acl=acl_init(1);
 acl_entry_t entry;
 acl_permset_t perms;
 uuid_t owner;
 int ok=acl&&mbr_uid_to_uuid(geteuid(),owner)==0&&acl_create_entry(&acl,&entry)==0&&
  acl_set_tag_type(entry,ACL_EXTENDED_ALLOW)==0&&acl_set_qualifier(entry,owner)==0&&
  acl_get_permset(entry,&perms)==0&&acl_add_perm(perms,ACL_WRITE_DATA)==0&&
  acl_set_permset(entry,perms)==0&&acl_set_fd_np(fd,acl,ACL_TYPE_EXTENDED)==0;
 if(acl&&acl_free(acl))ok=0;
 return ok;
#else
 (void)fd;
 (void)directory;
 return 0;
#endif
}
static void store_tests(int directory){
 static const unsigned char source[]="original raw bytes\n",payload[]="a bounded independent repair plan";
 pc02rp_blob raw={0},decoded={0};pc02rp_info observed={0},saved={0},original={0},plan={0};
 int fd=new_raw(directory,"source-raw",source,sizeof(source)-1);
 pc02_identity source_id=actual_id(fd);char digest[65];wh_sha256_hex(source,sizeof(source)-1,digest);
 begin_case("actual-FD-double-read-hash-and-position");REQUIRE(lseek(fd,3,SEEK_SET)==3);
 CHECK(pc02rp_read_raw(fd,LIMIT,&raw));
 CHECK(raw.bytes==sizeof(source)-1&&same_id(raw.info.identity,source_id)&&raw.info.bytes==sizeof(source)-1&&
  !memcmp(raw.data,source,sizeof(source)-1)&&!memcmp(raw.info.sha256,digest,65));
 CHECK(lseek(fd,0,SEEK_CUR)==3);observed=raw.info;pc02rp_free(&raw);
 CHECK(pc02rp_archive(fd,directory,"archive-raw",LIMIT,&original,&saved));
 CHECK(same_id(original.identity,source_id)&&!same_id(saved.identity,source_id)&&original.bytes==saved.bytes&&
  !memcmp(original.sha256,saved.sha256,65));CHECK(blob_equals(fd,&observed,source,sizeof(source)-1));
 begin_case("zero-byte-raw-archive-preserved");
 int empty=new_raw(directory,"source-empty",NULL,0);
 CHECK(pc02rp_read_raw(empty,0,&raw)&&raw.bytes==0&&raw.info.bytes==0&&raw.data!=NULL);pc02rp_free(&raw);
 CHECK(pc02rp_archive(empty,directory,"archive-empty",LIMIT,&original,&saved));
 CHECK(original.bytes==0&&saved.bytes==0&&!same_id(original.identity,saved.identity));
 wh_sha256_hex("",0,digest);CHECK(!memcmp(original.sha256,digest,65)&&!memcmp(saved.sha256,digest,65));CHECK(!close(empty));
 begin_case("new-wrapper112-readback-and-actual-self-ID");
 CHECK(pc02rp_write(directory,"plan-1",1,1,payload,sizeof(payload)-1,&plan));
 CHECK(pc02rp_read(directory,"plan-1",1,1,&plan,&decoded));
 CHECK(decoded.bytes==sizeof(payload)-1&&decoded.info.bytes==112+sizeof(payload)-1+64&&
  !memcmp(decoded.data,payload,sizeof(payload)-1));pc02rp_free(&decoded);
 int plan_fd=openat(directory,"plan-1",O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
 REQUIRE(plan_fd>=0&&pc02rp_read_raw(plan_fd,LIMIT,&raw));
 CHECK(same_id(plan.identity,actual_id(plan_fd))&&raw.bytes==plan.bytes&&!memcmp(raw.data,"PC02R001",8)&&
  get64(raw.data+8)==1&&get64(raw.data+16)==1&&get64(raw.data+24)==sizeof(payload)-1);
 CHECK(get64(raw.data+32)==plan.identity.device&&get64(raw.data+40)==plan.identity.inode);
 begin_case("same-bytes-new-native-ID-refused");
 int rebound=new_raw(directory,"same-bytes-rebound",raw.data,raw.bytes);
 CHECK(!same_id(actual_id(rebound),plan.identity));
 CHECK(!pc02rp_read(directory,"same-bytes-rebound",1,1,NULL,&decoded));
 CHECK(!pc02rp_read(directory,"same-bytes-rebound",1,1,&plan,&decoded));
 CHECK(blob_equals(plan_fd,&plan,raw.data,raw.bytes));CHECK(!close(rebound));
 begin_case("complete-wrapper-footer-and-length-refused");
 wrapper_variant(directory,"bad-footer",&raw,0);wrapper_variant(directory,"bad-length",&raw,1);
 CHECK(!pc02rp_read(directory,"bad-footer",1,1,NULL,&decoded));
 CHECK(!pc02rp_read(directory,"bad-length",1,1,NULL,&decoded));CHECK(blob_equals(plan_fd,&plan,raw.data,raw.bytes));
 begin_case("wrapper-kind-sequence-and-payload-hash-refused");
 wrapper_variant(directory,"wrong-kind",&raw,2);wrapper_variant(directory,"wrong-sequence",&raw,3);
 wrapper_variant(directory,"wrong-payload-hash",&raw,4);
 CHECK(!pc02rp_read(directory,"wrong-kind",1,1,NULL,&decoded));
 CHECK(!pc02rp_read(directory,"wrong-sequence",1,1,NULL,&decoded));
 CHECK(!pc02rp_read(directory,"wrong-payload-hash",1,1,NULL,&decoded));
 CHECK(pc02rp_read(directory,"wrong-kind",2,1,NULL,&decoded));pc02rp_free(&decoded);
 CHECK(pc02rp_read(directory,"wrong-sequence",1,2,NULL,&decoded));pc02rp_free(&decoded);
 begin_case("native-NOREPLACE-preserves-final-and-source");
 CHECK(!pc02rp_write(directory,"plan-1",99,99,"contradiction",13,&saved));
 CHECK(!pc02rp_archive(fd,directory,"plan-1",LIMIT,&original,&saved));
 CHECK(blob_equals(plan_fd,&plan,raw.data,raw.bytes));CHECK(blob_equals(fd,&observed,source,sizeof(source)-1));
 struct stat names;
 CHECK(!fstatat(directory,"plan-1",&names,AT_SYMLINK_NOFOLLOW)&&(uint64_t)names.st_ino==plan.identity.inode);
 begin_case("NOFOLLOW-FIFO-and-unsafe-directory-refused");
 REQUIRE(!mkfifoat(directory,"fifo-plan",0600));
 alarm(2);
 CHECK(!pc02rp_read(directory,"fifo-plan",1,1,NULL,&decoded));
 alarm(0);
 REQUIRE(!symlinkat("plan-1",directory,"alias-plan"));
 CHECK(!pc02rp_read(directory,"alias-plan",1,1,NULL,&decoded));
 CHECK(!pc02rp_archive(fd,directory,"alias-plan",LIMIT,&original,&saved));
 CHECK(!fstatat(directory,"alias-plan",&names,AT_SYMLINK_NOFOLLOW)&&S_ISLNK(names.st_mode));
 REQUIRE(!mkdirat(directory,"unsafe-directory",0700));
 int unsafe=openat(directory,"unsafe-directory",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
 REQUIRE(unsafe>=0&&!fchmod(unsafe,0755));
 CHECK(!pc02rp_write(unsafe,"must-not-exist",1,1,payload,sizeof(payload)-1,&saved));
 CHECK(fstatat(unsafe,"must-not-exist",&names,AT_SYMLINK_NOFOLLOW)<0&&errno==ENOENT);
 CHECK(!close(unsafe));CHECK(blob_equals(plan_fd,&plan,raw.data,raw.bytes));
 begin_case("source-hardlink-and-permission-refused");
 int linked=new_raw(directory,"source-hardlinked",source,sizeof(source)-1);
 REQUIRE(!linkat(directory,"source-hardlinked",directory,"source-hardlink",0));
 CHECK(!pc02rp_read_raw(linked,LIMIT,&decoded));
 CHECK(!pc02rp_archive(linked,directory,"must-not-archive-linked",LIMIT,&original,&saved));
 CHECK(!fstat(linked,&names)&&names.st_nlink==2);CHECK(!close(linked));
 int permissions=new_raw(directory,"source-readable",source,sizeof(source)-1);REQUIRE(!fchmod(permissions,0644));
 CHECK(!pc02rp_read_raw(permissions,LIMIT,&decoded));
 CHECK(!pc02rp_archive(permissions,directory,"must-not-archive-readable",LIMIT,&original,&saved));CHECK(!close(permissions));
 int acl_source=new_raw(directory,"source-extra-acl",source,sizeof(source)-1);
 REQUIRE(bad_acl(acl_source,0));
 CHECK(!fstat(acl_source,&names)&&(names.st_mode&07777)==0600);
 CHECK(!pc02rp_read_raw(acl_source,LIMIT,&decoded));
 CHECK(!pc02rp_archive(acl_source,directory,"must-not-archive-extra-acl",LIMIT,&original,&saved));
 CHECK(!close(acl_source));
 REQUIRE(!mkdirat(directory,"acl-directory",0700));
 int acl_directory=openat(directory,"acl-directory",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
 REQUIRE(acl_directory>=0&&bad_acl(acl_directory,1));
 CHECK(!fstat(acl_directory,&names)&&(names.st_mode&07777)==0700);
 CHECK(!pc02rp_write(acl_directory,"must-not-exist",1,1,payload,sizeof(payload)-1,&saved));
 CHECK(!close(acl_directory));
 begin_case("raw-maximum-enforced-and-originals-retained");
 CHECK(!pc02rp_read_raw(fd,sizeof(source)-2,&decoded));
 int large=new_raw(directory,"source-too-large",NULL,0);REQUIRE(!ftruncate(large,(off_t)LIMIT+1)&&!fsync(large));
 CHECK(!pc02rp_read_raw(large,LIMIT,&decoded));
 CHECK(!pc02rp_archive(large,directory,"must-not-archive-large",LIMIT,&original,&saved));
 CHECK(!fstat(large,&names)&&names.st_size==(off_t)LIMIT+1);
 CHECK(blob_equals(fd,&observed,source,sizeof(source)-1));CHECK(blob_equals(plan_fd,&plan,raw.data,raw.bytes));
 CHECK(!close(large));pc02rp_free(&raw);CHECK(!close(plan_fd));CHECK(!close(fd));
}
int main(int argc,char **argv){
 const char *actions=getenv("GITHUB_ACTIONS");
 if(argc!=2||!actions||strcmp(actions,"true")||geteuid()==0||getuid()!=geteuid()){
  fputs("Actions-only, native nonroot helper fixtures.\n",stderr);return 64;
 }
 umask(0077);int root=open(argv[1],O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);REQUIRE(root>=0);
 REQUIRE(!mkdirat(root,"vectors",0700));REQUIRE(!mkdirat(root,"store",0700));
 int vectors=openat(root,"vectors",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
 int store=openat(root,"store",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);REQUIRE(vectors>=0&&store>=0);
 fixture *f=malloc(sizeof(*f));REQUIRE(f);fixture_make(f);state_tests(f,vectors);
 fixture_make(f);transaction_tests(f,vectors);store_tests(store);free(f);
 REQUIRE(!fsync(vectors)&&!fsync(store)&&!fsync(root));REQUIRE(!close(vectors)&&!close(store)&&!close(root));done_case();
 printf("{\"source\":\"%s\",\"cases\":%u,\"checks\":%u,\"failed\":%u,\"passed\":%s,"
  "\"actual_sdk\":false,\"production_repair\":false,\"native_posix\":true,\"euid\":%lu}\n",
  SOURCE_SHA,cases,checks,failed,failed?"false":"true",(unsigned long)geteuid());
 return failed?1:0;
}
