/* SPDX-License-Identifier: MIT */
#include <exr_wh3_repair.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#define REC 424u
#define PAIR (2u*REC)
#define GREC 344u
#ifndef CANDIDATE_SOURCE_SHA
#define CANDIDATE_SOURCE_SHA "0000000000000000000000000000000000000000"
#endif
typedef struct {
 wh_binding binding;wh_gates gates;char domain[49];wh3wg_grant initial;
 wchar_t directory[MAX_PATH],native[MAX_PATH],journal_path[MAX_PATH],intent_path[MAX_PATH],gate_path[MAX_PATH];
 HANDLE journal,intent,gate;wh3w_identity ids[3],gate_ids[2];
 unsigned char *native_journal,*native_intent,*native_gate,*edit_journal,*edit_intent,*edit_gate;
 size_t journal_size,intent_size,gate_size,ends[EXR_WH_MAX_JOURNAL],lines_count;
 char lines[EXR_WH_MAX_JOURNAL][EXR_WH_LINE_MAX];
 wh3r_scan *scan;wh3r_gate_scan gate_scan;
 FILE *observations;unsigned cases,checks,failed,observed;const char *name;
} fixture;
static fixture *f;static int builder_cap;
static void check(int ok,const char *what) {
 f->checks++;
 if(!ok){f->failed++;if(f->failed<50)fprintf(stderr,"FAIL %s: %s\n",f->name,what);}
}
static void begin_case(const char *name){f->name=name;f->cases++;printf("CASE %u %s\n",f->cases,name);}
static void close_handle(HANDLE *h){if(*h&&*h!=INVALID_HANDLE_VALUE)CloseHandle(*h);*h=INVALID_HANDLE_VALUE;}
static void fill(char *text,size_t n,char c){memset(text,c,n);text[n]=0;}
static void setup_binding(const char *source) {
 memset(&f->binding,0,sizeof(f->binding));memset(&f->gates,0,sizeof(f->gates));
 strcpy_s(f->binding.source,sizeof(f->binding.source),source);strcpy_s(f->binding.run,sizeof(f->binding.run),"1");
 strcpy_s(f->binding.attempt,sizeof(f->binding.attempt),"1");fill(f->binding.artifact,64,'a');
 strcpy_s(f->binding.platform,sizeof(f->binding.platform),"windows-ntfs");
 strcpy_s(f->binding.sdk,sizeof(f->binding.sdk),"3.42.0-8357eafa");fill(f->binding.provider,64,'b');
 fill(f->gates.admission,64,'c');fill(f->gates.publisher,64,'d');fill(f->gates.recovery,64,'e');
 fill(f->gates.observer,64,'f');fill(f->gates.fault,64,'1');fill(f->domain,48,'2');
}
static int identity(HANDLE h,wh3w_identity *id) {
 FILE_ID_INFO info;if(!GetFileInformationByHandleEx(h,FileIdInfo,&info,sizeof(info)))return 0;
 id->volume=info.VolumeSerialNumber;id->file=info.FileId;return 1;
}
static int same_id(const wh3w_identity *a,const wh3w_identity *b){return a->volume==b->volume&&!memcmp(&a->file,&b->file,16);}
static HANDLE open_file(const wchar_t *path,DWORD creation) {
 return CreateFileW(path,GENERIC_READ|GENERIC_WRITE,FILE_SHARE_READ,NULL,creation,FILE_FLAG_OPEN_REPARSE_POINT,NULL);
}
static int bytes_read(HANDLE h,unsigned char **bytes,size_t *size) {
 LARGE_INTEGER n,zero;DWORD got=0;zero.QuadPart=0;*bytes=NULL;*size=0;
 if(!GetFileSizeEx(h,&n)||n.QuadPart<0||n.QuadPart>1024*1024)return 0;
 *size=(size_t)n.QuadPart;*bytes=malloc(*size?*size:1);if(!*bytes)return 0;
 return SetFilePointerEx(h,zero,NULL,FILE_BEGIN)&&ReadFile(h,*bytes,(DWORD)*size,&got,NULL)&&got==*size;
}
static int path_read(const wchar_t *path,unsigned char **bytes,size_t *size) {
 HANDLE h=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,NULL);
 int ok;if(h==INVALID_HANDLE_VALUE)return 0;ok=bytes_read(h,bytes,size);CloseHandle(h);return ok;
}
static int bytes_write(HANDLE h,const unsigned char *bytes,size_t size) {
 LARGE_INTEGER zero;DWORD put;zero.QuadPart=0;
 return SetFilePointerEx(h,zero,NULL,FILE_BEGIN)&&SetEndOfFile(h)&&
  WriteFile(h,bytes,(DWORD)size,&put,NULL)&&put==size&&FlushFileBuffers(h);
}
static int path_write(const wchar_t *path,const unsigned char *bytes,size_t size) {
 HANDLE h=open_file(path,CREATE_NEW);int ok;if(h==INVALID_HANDLE_VALUE)return 0;ok=bytes_write(h,bytes,size);CloseHandle(h);return ok;
}
static int builder_append(void *context,const char *line) {
 fixture *x=context;
 if(x->lines_count>=EXR_WH_MAX_JOURNAL||strlen(line)>=EXR_WH_LINE_MAX)return 1;
 strcpy_s(x->lines[x->lines_count++],EXR_WH_LINE_MAX,line);return 0;
}
static wh_step acquire(void *context,const wh_binding *b,const wh_gates *g,void **cap,char lease[49]) {
 (void)context;(void)b;(void)g;*cap=&builder_cap;fill(lease,48,'3');return WH_STEP_OK;
}
static wh_step reacquire(void *context,const wh_binding *b,const wh_gates *g,const char *prior,void **cap,char lease[49]) {
 (void)prior;return acquire(context,b,g,cap,lease);
}
static wh_step provider_check(void *context,void *cap){(void)context;return cap==&builder_cap?WH_STEP_OK:WH_STEP_FAILED;}
static wh_step snapshot(void *context,void *cap,wh_record *rows,size_t capacity,size_t *count) {
 (void)context;if(cap!=&builder_cap||!capacity)return WH_STEP_FAILED;memset(rows,0,sizeof(*rows));
 fill(rows[0].id,48,'4');strcpy_s(rows[0].path,sizeof(rows[0].path),"fixture.exrpack");
 rows[0].size=123;fill(rows[0].sha,64,'5');*count=1;return WH_STEP_OK;
}
static wh_step import_rows(void *context,void *cap,const wh_record *rows,size_t n,char stage[49]) {
 (void)context;(void)rows;if(cap!=&builder_cap||n!=1)return WH_STEP_FAILED;fill(stage,48,'6');return WH_STEP_OK;
}
static wh_step verify(void *context,void *cap,const char *stage,const wh_record *rows,size_t n) {
 (void)context;(void)stage;(void)rows;return cap==&builder_cap&&n==1?WH_STEP_OK:WH_STEP_FAILED;
}
static wh_step publish(void *context,void *cap,const char *stage,wh_pub *pub) {
 (void)context;(void)stage;if(cap!=&builder_cap)return WH_STEP_FAILED;*pub=WH_PUB_YES;return WH_STEP_OK;
}
static wh_step inspect(void *context,void *cap,const char *stage,const char *content,wh_pub *pub) {
 (void)content;return publish(context,cap,stage,pub);
}
static wh_step discard(void *context,void *cap,const char *stage){(void)stage;return provider_check(context,cap);}
static wh_step release(void *context,void *cap){return provider_check(context,cap);}
static int build_history(void) {
 wh_provider provider;wh_session *session;wh_report report;memset(&provider,0,sizeof(provider));
 provider.abi=EXR_WH_ABI;provider.identity_sha=f->binding.provider;provider.context=f;
 provider.acquire=acquire;provider.reacquire=reacquire;provider.check=provider_check;provider.snapshot=snapshot;
 provider.import_rows=import_rows;provider.verify=verify;provider.publish=publish;provider.inspect=inspect;
 provider.discard=discard;provider.release=release;
 session=wh_create(&f->binding,&f->gates,&provider,builder_append,f);if(!session)return 0;
 return wh_run(session,&report)==WH_COMPLETED&&f->lines_count==13&&wh_dispose(session);
}
static int proof(void *context,const wh3_tip *tip){(void)context;return tip->line_count==13;}
static void empty_tip(wh3_tip *tip) {
 char manifest[EXR_WH_LINE_MAX];memset(tip,0,sizeof(*tip));wh_manifest(&f->binding,&f->gates,manifest);
 wh_sha256_hex(manifest,strlen(manifest),tip->manifest_sha);fill(tip->last_line_sha,64,'0');
}
static int native_fixture(void) {
 wchar_t path[MAX_PATH];HANDLE h=INVALID_HANDLE_VALUE,root=INVALID_HANDLE_VALUE;wh3wg_gate *gate=NULL;
 wh3w_store *store=NULL;wh3w_domain domain;wh3wg_grant completed;wh3_tip tip,next;void *cap=NULL;size_t k,offset=0;
 int ok=0;
 if(!CreateDirectoryW(f->native,NULL))goto done;
 root=CreateFileW(f->native,FILE_READ_ATTRIBUTES,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_EXISTING,
   FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,NULL);
 if(root==INVALID_HANDLE_VALUE||!identity(root,&f->ids[0]))goto done;f->gate_ids[0]=f->ids[0];close_handle(&root);
 swprintf_s(path,MAX_PATH,L"%ls\\journal.bin",f->native);h=open_file(path,CREATE_NEW);
 if(h==INVALID_HANDLE_VALUE||!identity(h,&f->ids[1]))goto done;close_handle(&h);
 swprintf_s(path,MAX_PATH,L"%ls\\intent.bin",f->native);h=open_file(path,CREATE_NEW);
 if(h==INVALID_HANDLE_VALUE||!identity(h,&f->ids[2]))goto done;close_handle(&h);
 swprintf_s(path,MAX_PATH,L"%ls\\admission.bin",f->native);h=open_file(path,CREATE_NEW);
 if(h==INVALID_HANDLE_VALUE||!identity(h,&f->gate_ids[1]))goto done;close_handle(&h);
 if(!wh3wg_open(f->native,f->gate_ids,f->domain,NULL,WH3WG_ENROLL,NULL,&gate)||
    !wh3wg_enroll(gate,&f->initial))goto done;
 empty_tip(&tip);
 if(!wh3wg_begin(gate,&f->binding,&f->gates,&tip,&cap))goto done;
 wh3wg_domain(gate,&domain);
 if(!wh3w_open(f->native,f->ids,&f->binding,&f->gates,&domain,NULL,&store))goto done;
 for(k=0;k<f->lines_count;k++){
  if(wh3w_append(store,cap,&tip,f->lines[k],&next)!=WH3_TX_OK)goto done;
  tip=next;offset+=4+strlen(f->lines[k]);f->ends[k]=offset;
 }
 if(!wh3wg_finish(gate,cap,store,&tip,proof,NULL,&completed))goto done;
 wh3w_close(store);store=NULL;
 if(!wh3wg_close(gate))goto done;gate=NULL;
 swprintf_s(path,MAX_PATH,L"%ls\\journal.bin",f->native);
 if(!path_read(path,&f->native_journal,&f->journal_size))goto done;
 swprintf_s(path,MAX_PATH,L"%ls\\intent.bin",f->native);
 if(!path_read(path,&f->native_intent,&f->intent_size))goto done;
 swprintf_s(path,MAX_PATH,L"%ls\\admission.bin",f->native);
 if(!path_read(path,&f->native_gate,&f->gate_size))goto done;
 if(f->journal_size!=offset||f->intent_size!=f->lines_count*PAIR||f->gate_size!=3u*GREC)goto done;
 f->edit_journal=malloc(f->journal_size+8);f->edit_intent=malloc(f->intent_size+8);f->edit_gate=malloc(f->gate_size+8);
 if(!f->edit_journal||!f->edit_intent||!f->edit_gate)goto done;ok=1;
done:
 close_handle(&h);close_handle(&root);wh3w_close(store);if(gate)wh3wg_close(gate);return ok;
}
static int scan_image(const unsigned char *journal,size_t jsize,const unsigned char *intent,size_t isize,
 size_t expected,int tail,int accepted) {
 unsigned char *after=NULL;size_t n=0;char jsha[65],isha[65];int result;wh3w_identity journal_id,intent_id;
 check(bytes_write(f->journal,journal,jsize)&&bytes_write(f->intent,intent,isize),"write only isolated observation fixtures");
 wh_sha256_hex(journal,jsize,jsha);wh_sha256_hex(intent,isize,isha);
 result=wh3r_scan_ack(f->journal,f->intent,&f->binding,&f->gates,f->scan);
 check(result==accepted,"accept exactly the legal raw state");
 if(result){
  check(identity(f->journal,&journal_id)&&identity(f->intent,&intent_id)&&
    same_id(&journal_id,&f->scan->journal_identity)&&same_id(&intent_id,&f->scan->intent_identity),"actual input identities are observed");
  check(f->scan->count==expected&&f->scan->tip.line_count==expected,"every complete ACK is observed exactly");
  check(f->scan->journal_bytes==jsize&&f->scan->intent_bytes==isize&&
    f->scan->journal_keep_bytes==(expected?f->ends[expected-1]:0)&&f->scan->intent_keep_bytes==expected*PAIR,"exact original sizes and acknowledged boundaries");
  check(f->scan->unack_tail==tail&&!memcmp(jsha,f->scan->journal_sha256,65)&&!memcmp(isha,f->scan->intent_sha256,65),"raw SHA and unacknowledged suffix are independently observed");
  for(size_t k=0;k<expected;k++)check(!strcmp(f->scan->lines[k],f->lines[k]),"acknowledged canonical line retained");
 }else{
  check(!f->scan->count&&!f->scan->journal_bytes&&!f->scan->intent_bytes&&!f->scan->tip.line_count,"failed scan clears evidence output");
 }
 check(bytes_read(f->journal,&after,&n)&&n==jsize&&!memcmp(after,journal,n),"journal source bytes never change");free(after);after=NULL;
 check(bytes_read(f->intent,&after,&n)&&n==isize&&!memcmp(after,intent,n),"intent source bytes never change");free(after);
 f->observed++;
 fprintf(f->observations,"{\"case\":\"%s\",\"observation\":%u,\"journal_bytes\":%zu,\"intent_bytes\":%zu,\"journal_sha256\":\"%s\",\"intent_sha256\":\"%s\",\"accepted\":%s,\"count\":%zu,\"expected_count\":%zu}\n",
   f->name,f->observed,jsize,isize,jsha,isha,result?"true":"false",result?f->scan->count:0,expected);return result;
}
static size_t prefix(size_t count){return count?f->ends[count-1]:0;}
static void basic_cases(void) {
 begin_case("empty-native-pair");scan_image(f->native_journal,0,f->native_intent,0,0,0,1);
 begin_case("complete-native-pair");scan_image(f->native_journal,f->journal_size,f->native_intent,f->intent_size,13,0,1);
 begin_case("all-complete-ACK-prefixes");
 for(size_t count=1;count<=13;count++)scan_image(f->native_journal,prefix(count),f->native_intent,count*PAIR,count,0,1);
 begin_case("one-native-poison-byte-without-BEGIN");
 f->edit_intent[0]=0xff;scan_image(f->native_journal,0,f->edit_intent,1,0,1,1);
 begin_case("every-complete-ACK-plus-poison-is-still-acknowledged");
 for(size_t count=1;count<=13;count++){
  memcpy(f->edit_intent,f->native_intent,count*PAIR);f->edit_intent[count*PAIR]=0xff;
  scan_image(f->native_journal,prefix(count),f->edit_intent,count*PAIR+1,count,1,1);
 }
 begin_case("same-native-object-is-not-a-pair");
 check(!wh3r_scan_ack(f->journal,f->journal,&f->binding,&f->gates,f->scan),"identical handles refuse even for an empty pair");
 {HANDLE duplicate=ReOpenFile(f->journal,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,FILE_FLAG_OPEN_REPARSE_POINT);
  check(duplicate!=INVALID_HANDLE_VALUE&&!wh3r_scan_ack(f->journal,duplicate,&f->binding,&f->gates,f->scan),"different handles of one object refuse");close_handle(&duplicate);}
}
static void interrupted_cases(void) {
 static const size_t bases[]={0,5,12};
 begin_case("every-byte-partial-BEGIN-with-and-without-poison");
 for(size_t b=0;b<3;b++)for(size_t cut=1;cut<REC;cut++){
  size_t base=bases[b],ilen=base*PAIR+cut;
  scan_image(f->native_journal,prefix(base),f->native_intent,ilen,base,1,1);
  memcpy(f->edit_intent,f->native_intent,ilen);f->edit_intent[ilen]=0xff;
  scan_image(f->native_journal,prefix(base),f->edit_intent,ilen+1,base,1,1);
 }
 begin_case("every-byte-partial-journal-frame-with-complete-BEGIN");
 for(size_t b=0;b<3;b++){
  size_t base=bases[b],frame=prefix(base+1)-prefix(base);
  for(size_t cut=0;cut<frame;cut++)scan_image(f->native_journal,prefix(base)+cut,f->native_intent,base*PAIR+REC,base,1,1);
 }
 begin_case("complete-unacknowledged-journal-line");
 for(size_t b=0;b<3;b++){size_t base=bases[b];
  scan_image(f->native_journal,prefix(base+1),f->native_intent,base*PAIR+REC,base,1,1);}
 begin_case("every-byte-partial-ACK-with-and-without-poison");
 for(size_t b=0;b<3;b++)for(size_t cut=1;cut<REC;cut++){
  size_t base=bases[b],ilen=base*PAIR+REC+cut;
  scan_image(f->native_journal,prefix(base+1),f->native_intent,ilen,base,1,1);
  memcpy(f->edit_intent,f->native_intent,ilen);f->edit_intent[ilen]=0xff;
  scan_image(f->native_journal,prefix(base+1),f->edit_intent,ilen+1,base,1,1);
 }
}
static void reseal(unsigned char *record) {char hash[65];wh_sha256_hex(record,360,hash);memcpy(record+360,hash,64);}
static void remake_ack(unsigned char *begin) {
 unsigned char *ack=begin+REC;memcpy(ack,begin,REC);ack[8]='A';
 memcpy(ack+232,begin+360,64);memcpy(ack+296,begin+360,64);reseal(ack);
}
static void keep_negative(unsigned index,const unsigned char *journal,size_t jsize,const unsigned char *intent,size_t isize) {
 wchar_t path[MAX_PATH];
 swprintf_s(path,MAX_PATH,L"%ls\\negative-%02u-journal.bin",f->directory,index);check(path_write(path,journal,jsize),"retain independent raw negative journal");
 swprintf_s(path,MAX_PATH,L"%ls\\negative-%02u-intent.bin",f->directory,index);check(path_write(path,intent,isize),"retain independent raw negative intent");
}
static void semantic_negative_cases(void) {
 static const size_t begin_fields[]={9,16,24,32,40,104,168,232,296};
 static const size_t ack_fields[]={9,16,24,32,40,104,168,232,296};unsigned saved=0;
 begin_case("resealed-complete-BEGIN-internal-contradictions");
 for(size_t k=0;k<sizeof(begin_fields)/sizeof(begin_fields[0]);k++){
  unsigned char *record;memcpy(f->edit_intent,f->native_intent,6*PAIR);record=f->edit_intent+5*PAIR;
  record[begin_fields[k]]^=1;reseal(record);remake_ack(record);
  scan_image(f->native_journal,prefix(6),f->edit_intent,6*PAIR,0,0,0);
  keep_negative(++saved,f->native_journal,prefix(6),f->edit_intent,6*PAIR);
 }
 begin_case("resealed-complete-ACK-internal-contradictions");
 for(size_t k=0;k<sizeof(ack_fields)/sizeof(ack_fields[0]);k++){
  unsigned char *record;memcpy(f->edit_intent,f->native_intent,6*PAIR);record=f->edit_intent+5*PAIR+REC;
  record[ack_fields[k]]^=1;reseal(record);
  scan_image(f->native_journal,prefix(6),f->edit_intent,6*PAIR,0,0,0);
  keep_negative(++saved,f->native_journal,prefix(6),f->edit_intent,6*PAIR);
 }
 begin_case("empty-intent-nonempty-journal-and-missing-BEGIN");
 scan_image(f->native_journal,prefix(1),f->native_intent,0,0,0,0);
 scan_image(f->native_journal,prefix(6),f->native_intent,5*PAIR,0,0,0);
 begin_case("complete-ACK-never-rewound-to-hide-incomplete-journal");
 scan_image(f->native_journal,prefix(6)-1,f->native_intent,6*PAIR,0,0,0);
 begin_case("partial-ACK-needs-complete-journal-and-exact-canonical-prefix");
 scan_image(f->native_journal,prefix(6)-1,f->native_intent,5*PAIR+REC+212,0,0,0);
 memcpy(f->edit_intent,f->native_intent,5*PAIR+REC+212);f->edit_intent[5*PAIR+REC+16]^=1;
 scan_image(f->native_journal,prefix(6),f->edit_intent,5*PAIR+REC+212,0,0,0);
 begin_case("partial-BEGIN-rejects-complete-known-field-conflict");
 memcpy(f->edit_intent,f->native_intent,5*PAIR+212);f->edit_intent[5*PAIR+9]=1;
 scan_image(f->native_journal,prefix(5),f->edit_intent,5*PAIR+212,0,0,0);
 begin_case("partial-body-must-prefix-a-legal-canonical-next-line");
 memcpy(f->edit_journal,f->native_journal,prefix(5)+5);f->edit_journal[prefix(5)+4]='X';
 scan_image(f->edit_journal,prefix(5)+5,f->native_intent,5*PAIR+REC,0,0,0);
 begin_case("complete-resealed-FSM-violation-is-not-an-unacknowledged-tail");
 {size_t at=prefix(5)+4,n=strlen(f->lines[5]);char hash[65];unsigned char *record;
  memcpy(f->edit_journal,f->native_journal,prefix(6));f->edit_journal[at+9]='8';
  wh_sha256_hex(f->edit_journal+at,n-65,hash);memcpy(f->edit_journal+at+n-64,hash,64);
  memcpy(f->edit_intent,f->native_intent,6*PAIR);record=f->edit_intent+5*PAIR;
  wh_sha256_hex(f->edit_journal+at,n,hash);memcpy(record+168,hash,64);reseal(record);remake_ack(record);
  scan_image(f->edit_journal,prefix(6),f->edit_intent,6*PAIR,0,0,0);
  keep_negative(++saved,f->edit_journal,prefix(6),f->edit_intent,6*PAIR);
 }
 begin_case("two-append-tails-and-extra-poison-are-not-one-interruption");
 scan_image(f->native_journal,prefix(7),f->native_intent,5*PAIR+REC,0,0,0);
 f->edit_intent[0]=0xff;f->edit_intent[1]=0xff;scan_image(f->native_journal,0,f->edit_intent,2,0,0,0);
}
static int gate_image(const unsigned char *gate,size_t size,const wh3wg_grant *trusted,
 int accepted,size_t target,int needs_write,int clean) {
 unsigned char *after=NULL;size_t n=0;char hash[65];int result;
 check(bytes_write(f->gate,gate,size),"write only isolated admission observation fixture");
 wh_sha256_hex(gate,size,hash);
 result=wh3r_scan_gate(f->gate,f->domain,trusted,&f->binding,&f->gates,f->scan,&f->gate_scan);
 check(result==accepted,"gate accepts only the initial independently bound epoch");
 if(result)check(f->gate_scan.bytes==size&&!memcmp(f->gate_scan.sha256,hash,65)&&
  f->gate_scan.target_bytes==target&&f->gate_scan.gate_keep_bytes==(size<target?GREC:target)&&f->gate_scan.needs_write==needs_write&&f->gate_scan.complete_clean==clean&&
  !memcmp(f->gate_scan.target,f->native_gate,target),"gate plan matches actual canonical native bytes");
 else check(!f->gate_scan.bytes&&!f->gate_scan.target_bytes,"failed gate output is cleared");
 check(bytes_read(f->gate,&after,&n)&&n==size&&!memcmp(after,gate,n),"admission source bytes never change");free(after);return result;
}
static void gate_cases(void) {
 begin_case("initial-CLEAN-empty-pair-no-repair");
 scan_image(f->native_journal,0,f->native_intent,0,0,0,1);
 gate_image(f->native_gate,GREC,&f->initial,1,GREC,0,0);
 begin_case("all-canonical-partial-BEGIN-gates-plan-complete-PENDING");
 for(size_t cut=1;cut<GREC;cut++)gate_image(f->native_gate,GREC+cut,&f->initial,1,2u*GREC,1,0);
 begin_case("complete-PENDING-gate-preserves-acknowledged-pair");
 scan_image(f->native_journal,f->journal_size,f->native_intent,f->intent_size,13,0,1);
 gate_image(f->native_gate,2u*GREC,&f->initial,1,2u*GREC,0,0);
 begin_case("all-canonical-partial-CLEAN-gates-plan-PENDING-only");
 for(size_t cut=1;cut<GREC;cut++)gate_image(f->native_gate,2u*GREC+cut,&f->initial,1,2u*GREC,1,0);
 begin_case("complete-CLEAN-gate-never-dropped");
 gate_image(f->native_gate,3u*GREC,&f->initial,1,3u*GREC,0,1);
 begin_case("gate-full-and-partial-CLEAN-need-exact-terminal-ACK");
 scan_image(f->native_journal,prefix(10),f->native_intent,10*PAIR,10,0,1);
 gate_image(f->native_gate,2u*GREC+212,&f->initial,0,0,0,0);
 gate_image(f->native_gate,3u*GREC,&f->initial,0,0,0,0);
 begin_case("gate-partial-BEGIN-cannot-explain-any-journal-effect");
 gate_image(f->native_gate,GREC+212,&f->initial,0,0,0,0);
 begin_case("initial-gate-does-not-adopt-foreign-journal");
 gate_image(f->native_gate,GREC,&f->initial,0,0,0,0);
 begin_case("gate-complete-CLEAN-plus-unacknowledged-pair-tail-is-contradictory");
 memcpy(f->edit_intent,f->native_intent,f->intent_size);f->edit_intent[f->intent_size]=0xff;
 scan_image(f->native_journal,f->journal_size,f->edit_intent,f->intent_size+1,13,1,1);
 gate_image(f->native_gate,3u*GREC,&f->initial,0,0,0,0);
 begin_case("gate-unknown-prefix-and-noninitial-grant-refuse");
 scan_image(f->native_journal,0,f->native_intent,0,0,0,1);
 memcpy(f->edit_gate,f->native_gate,GREC+212);f->edit_gate[GREC+9]=1;
 gate_image(f->edit_gate,GREC+212,&f->initial,0,0,0,0);
 {wh3wg_grant other=f->initial;other.generation=1;gate_image(f->native_gate,GREC,&other,0,0,0,0);}
}
static int observe_mode(int argc,wchar_t **argv) {
 char source[41];HANDLE j=INVALID_HANDLE_VALUE,i=INVALID_HANDLE_VALUE;int result=0;
 if(argc!=5||wcslen(argv[4])!=40)return 64;
 for(size_t k=0;k<40;k++)source[k]=(char)argv[4][k];source[40]=0;setup_binding(source);
 j=CreateFileW(argv[2],GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,NULL);
 i=CreateFileW(argv[3],GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,NULL);
 if(j!=INVALID_HANDLE_VALUE&&i!=INVALID_HANDLE_VALUE)result=wh3r_scan_ack(j,i,&f->binding,&f->gates,f->scan);
 printf("{\"accepted\":%s,\"count\":%zu,\"journal_keep_bytes\":%llu,\"intent_keep_bytes\":%llu,\"unack_tail\":%s}\n",
  result?"true":"false",result?f->scan->count:0,(unsigned long long)f->scan->journal_keep_bytes,
  (unsigned long long)f->scan->intent_keep_bytes,f->scan->unack_tail?"true":"false");
 close_handle(&j);close_handle(&i);return result?0:2;
}
int wmain(int argc,wchar_t **argv) {
 wchar_t path[MAX_PATH];DWORD n;int ok=0;
 f=calloc(1,sizeof(*f));if(!f)return 3;f->scan=calloc(1,sizeof(*f->scan));if(!f->scan)return 3;
 f->journal=f->intent=f->gate=INVALID_HANDLE_VALUE;setup_binding(CANDIDATE_SOURCE_SHA);
 if(argc>1&&!wcscmp(argv[1],L"--observe"))return observe_mode(argc,argv);
 if(argc!=2){fputs("Usage: coordinator-repair-scan-check NEW_EVIDENCE_DIRECTORY\n",stderr);goto done;}
 n=GetFullPathNameW(argv[1],MAX_PATH,f->directory,NULL);
 if(!n||n>MAX_PATH-100||!CreateDirectoryW(f->directory,NULL))goto done;
 swprintf_s(f->native,MAX_PATH,L"%ls\\native",f->directory);
 swprintf_s(f->journal_path,MAX_PATH,L"%ls\\observed-journal.bin",f->directory);
 swprintf_s(f->intent_path,MAX_PATH,L"%ls\\observed-intent.bin",f->directory);
 swprintf_s(f->gate_path,MAX_PATH,L"%ls\\observed-admission.bin",f->directory);
 swprintf_s(path,MAX_PATH,L"%ls\\observations.jsonl",f->directory);
 if(_wfopen_s(&f->observations,path,L"wb")||!f->observations||!build_history()||!native_fixture())goto done;
 f->journal=open_file(f->journal_path,CREATE_NEW);f->intent=open_file(f->intent_path,CREATE_NEW);f->gate=open_file(f->gate_path,CREATE_NEW);
 if(f->journal==INVALID_HANDLE_VALUE||f->intent==INVALID_HANDLE_VALUE||f->gate==INVALID_HANDLE_VALUE)goto done;
 basic_cases();interrupted_cases();semantic_negative_cases();gate_cases();ok=f->failed==0;
 printf("{\"source\":\"%s\",\"cases\":%u,\"checks\":%u,\"observations\":%u,\"failed\":%u,\"passed\":%s,\"native_io\":true,\"read_only_scanner\":true,\"process_kill\":false,\"production_repair\":false}\n",
  CANDIDATE_SOURCE_SHA,f->cases,f->checks,f->observed,f->failed,ok?"true":"false");
done:
 if(!ok&&f->checks==0)fprintf(stderr,"native fixture setup failed, Windows error %lu\n",GetLastError());
 if(f->observations)fclose(f->observations);
 close_handle(&f->journal);close_handle(&f->intent);close_handle(&f->gate);
 free(f->native_journal);free(f->native_intent);free(f->native_gate);free(f->edit_journal);free(f->edit_intent);free(f->edit_gate);
 free(f->scan);free(f);return ok?0:1;
}
