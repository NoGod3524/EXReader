/* SPDX-License-Identifier: MIT
 * Real NTFS admission custody. Publication proof remains an explicit control;
 * production host wiring is verified by its separate installed consumers. */
#define WH3W_TEST_ENTRY wh3w_native_reference_main
#include "../windows_coordinator_native_journal_20261030/wh3_win_test.c"
#include <lm_win_lease.h>
#define DOMAIN_ID HX40 "01234567"
typedef struct {
 wchar_t root[MAX_PATH];wh3w_identity ids[3],gate_id;wh_binding b;wh_gates gates;
 wh3wg_grant grant,finished_grant;wh3_tip tip;HANDLE ready,go;
 unsigned mode,stop,reached;int opened,began,finished;
} gate_shared;
enum { G_PROBE=1,G_SHARED_HOLD,G_OWNER_HOLD,G_BEGIN,G_FINISH };
static wh3wg_gate *gate;
static wh3w_identity gate_ids[2];
static wh3wg_grant admitted;
static HANDLE gm,gr,gg;
static gate_shared *gs;
typedef struct {int allow,calls;} proof_control;
static int prove_terminal(void *context,const wh3_tip *tip) {
 proof_control *p=context;p->calls++;return p->allow&&tip->line_count>1;
}
static void gate_path(wchar_t out[MAX_PATH]) {
 swprintf_s(out,MAX_PATH,L"%ls\\admission.bin",f.root);
}
static void gate_close_all(void) {
 wh3w_close(f.store);f.store=NULL;(void)wh3wg_close(gate);gate=NULL;
 if(gs)UnmapViewOfFile(gs);if(gm)CloseHandle(gm);if(gr)CloseHandle(gr);if(gg)CloseHandle(gg);
 gs=NULL;gm=gr=gg=NULL;fixture_close();
}
static int gate_open(unsigned mode,const wh3wg_grant *grant,const wh3w_controls *controls) {
 return wh3wg_open(f.root,gate_ids,DOMAIN_ID,grant,mode,controls,&gate);
}
static int gate_fixture(const char *name) {
 wchar_t path[MAX_PATH];HANDLE h;int ok;
 gate_close_all();case_start(name);ok=fixture_new();expect(ok,"native fixture");if(!ok)return 0;
 gate_path(path);h=CreateFileW(path,GENERIC_READ|GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_WRITE,
   NULL,CREATE_NEW,FILE_FLAG_WRITE_THROUGH,NULL);
 if(h==INVALID_HANDLE_VALUE){expect(0,"create empty enrollment object");return 0;}
 ok=FlushFileBuffers(h)!=0;CloseHandle(h);expect(ok,"flush empty object");
 gate_ids[0]=f.ids[0];expect(capture_id(path,0,&gate_ids[1]),"trusted gate identity");
 expect(gate_open(WH3WG_ENROLL,NULL,NULL),"explicit bootstrap custody");
 if(!gate)return 0;
 expect(wh3wg_enroll(gate,&admitted),"durable initial grant");
 expect(wh3wg_close(gate),"release bootstrap");gate=NULL;return 1;
}
static int pending(const wh3w_controls *controls,void **cap) {
 wh3_tip empty;empty_tip(&empty);
 if(!gate_open(WH3WG_OWNER,&admitted,controls))return 0;
 return wh3wg_begin(gate,&f.b,&f.g,&empty,cap);
}
static int terminal(void *cap,wh3_tip *after) {
 wh3_tip before;size_t i;int ok;
 wh3wg_domain(gate,&f.domain);
 if(!open_store()||!builder_start(&built,&f.b,&f.g))return 0;
 ok=builder_event(&built,1,NULL,NULL,NULL,NULL)
   &&builder_event(&built,2,DOMAIN_ID,NULL,NULL,NULL)
   &&builder_event(&built,3,NULL,NULL,NULL,NULL)
   &&builder_event(&built,4,NULL,NULL,HX64,NULL)
   &&builder_event(&built,5,NULL,NULL,NULL,HX64)
   &&builder_event(&built,6,NULL,DOMAIN_ID,NULL,NULL)
   &&builder_event(&built,7,NULL,NULL,NULL,NULL)
   &&builder_event(&built,8,NULL,NULL,NULL,NULL)
   &&builder_event(&built,9,NULL,NULL,NULL,NULL)
   &&builder_event(&built,10,NULL,NULL,NULL,NULL)
   &&builder_event(&built,11,NULL,NULL,NULL,NULL)
   &&builder_event(&built,12,NULL,NULL,NULL,NULL);
 if(!ok)return 0;empty_tip(&before);
 for(i=0;i<built.n;i++){
  if(wh3w_append(f.store,cap,&before,built.lines[i],after)!=WH3_TX_OK)return 0;
  before=*after;
 }
 return 1;
}
static void gate_barrier(void *context,unsigned at) {
 gate_shared *v=context;
 if(at==v->stop){v->reached=at;SetEvent(v->ready);if(WaitForSingleObject(v->go,15000)!=WAIT_OBJECT_0)ExitProcess(94);}
}
static HANDLE gate_spawn(unsigned mode,unsigned stop,const wh3wg_grant *grant) {
 SECURITY_ATTRIBUTES sa={sizeof(sa),NULL,TRUE};wchar_t exe[MAX_PATH],command[2*MAX_PATH];
 STARTUPINFOW si;PROCESS_INFORMATION pi;
 if(!gs){
  gm=CreateFileMappingW(INVALID_HANDLE_VALUE,&sa,PAGE_READWRITE,0,sizeof(gate_shared),NULL);
  gr=CreateEventW(&sa,TRUE,FALSE,NULL);gg=CreateEventW(&sa,TRUE,FALSE,NULL);
  if(!gm||!gr||!gg)return NULL;
  gs=MapViewOfFile(gm,FILE_MAP_ALL_ACCESS,0,0,sizeof(*gs));if(!gs)return NULL;
 }
 memset(gs,0,sizeof(*gs));ResetEvent(gr);ResetEvent(gg);
 wcscpy_s(gs->root,MAX_PATH,f.root);memcpy(gs->ids,f.ids,sizeof(f.ids));
 gs->gate_id=gate_ids[1];gs->b=f.b;gs->gates=f.g;gs->grant=*grant;
 gs->ready=gr;gs->go=gg;gs->mode=mode;gs->stop=stop;
 if(!GetModuleFileNameW(NULL,exe,MAX_PATH))return NULL;
 swprintf_s(command,2*MAX_PATH,L"\"%ls\" --gate-child %llu",exe,(unsigned long long)(uintptr_t)gm);
 memset(&si,0,sizeof(si));si.cb=sizeof(si);memset(&pi,0,sizeof(pi));
 if(!CreateProcessW(exe,command,NULL,NULL,TRUE,CREATE_NO_WINDOW,NULL,NULL,&si,&pi))return NULL;
 printf("OBS gate_child mode=%u pid=%lu barrier=%u\n",mode,(unsigned long)pi.dwProcessId,stop);
 CloseHandle(pi.hThread);return pi.hProcess;
}
static int gate_child(const char *handle) {
 HANDLE mapping=(HANDLE)(uintptr_t)_strtoui64(handle,NULL,10);gate_shared *v;
 wh3w_controls controls={0};wh3_tip empty;void *cap=NULL;proof_control proof={1,0};
 v=MapViewOfFile(mapping,FILE_MAP_ALL_ACCESS,0,0,sizeof(*v));if(!v)return 90;
 memset(&f,0,sizeof(f));setup_callbacks();wcscpy_s(f.root,MAX_PATH,v->root);
 memcpy(f.ids,v->ids,sizeof(f.ids));f.b=v->b;f.g=v->gates;
 gate_ids[0]=v->ids[0];gate_ids[1]=v->gate_id;
 controls.context=v;controls.phase=gate_barrier;
 v->opened=gate_open(v->mode==G_PROBE||v->mode==G_SHARED_HOLD?WH3WG_SHARED:WH3WG_OWNER,&v->grant,&controls);
 if(v->mode==G_SHARED_HOLD||v->mode==G_OWNER_HOLD){
  SetEvent(v->ready);if(WaitForSingleObject(v->go,15000)!=WAIT_OBJECT_0)return 95;
 }else if(v->opened&&(v->mode==G_BEGIN||v->mode==G_FINISH)){
  empty_tip(&empty);v->began=wh3wg_begin(gate,&f.b,&f.g,&empty,&cap);
  if(v->began&&v->mode==G_FINISH&&terminal(cap,&v->tip))
   v->finished=wh3wg_finish(gate,cap,f.store,&v->tip,prove_terminal,&proof,&v->finished_grant);
 }
 wh3w_close(f.store);(void)wh3wg_close(gate);UnmapViewOfFile(v);return 0;
}
static int gate_probe(const wh3wg_grant *grant) {
 HANDLE h=gate_spawn(G_PROBE,0,grant);if(!finish(h,0))return -1;return gs->opened;
}
static void initial_case(void) {
 wh3wg_gate *second=NULL;
 if(!gate_fixture("explicit-enrollment-and-shared-custody"))return;
 expect(!gate_open(WH3WG_ENROLL,NULL,NULL),"never reinitialize nonempty object");
 expect(gate_open(WH3WG_SHARED,&admitted,NULL),"shared exact grant");
 expect(wh3wg_open(f.root,gate_ids,DOMAIN_ID,&admitted,WH3WG_SHARED,NULL,&second),"two live shared holders");
 expect(wh3wg_check(gate)&&wh3wg_check(second),"both native locks live");
 (void)wh3wg_close(second);expect(gate_probe(&admitted)==1,"fresh process shares");
}
static void bad_object(unsigned kind,const char *name) {
 wchar_t path[MAX_PATH];unsigned char *data=NULL;DWORD bytes=0;wh3wg_grant wrong=admitted;
 if(!gate_fixture(name))return;gate_path(path);wrong=admitted;
 if(kind==0)expect(DeleteFileW(path)!=0,"remove fixture gate");
 if(kind==1)expect(replace_bytes(path,"x",1),"truncate fixture gate");
 if(kind==2)wrong.generation++;
 if(kind==3)wrong.seal[0]=wrong.seal[0]=='a'?'b':'a';
 if(kind==4){
  expect(read_bytes(path,&data,&bytes)&&bytes==344,"read enrolled record");
  if(!data)return;data[9]=1;wh_sha256_hex(data,280,(char *)data+280);
  /* The string terminator is outside the 344-byte persisted record. */
  expect(replace_bytes(path,data,bytes),"reseal invalid canonical bytes");free(data);
 }
 if(kind==5)gate_ids[1].file.Identifier[0]^=1;
 if(kind==6){
  wchar_t alias[MAX_PATH];swprintf_s(alias,MAX_PATH,L"%ls\\hardlink",f.base);
  expect(CreateHardLinkW(alias,path,NULL)!=0,"create gate alias");
 }
 expect(!gate_open(WH3WG_SHARED,&wrong,NULL),"ordinary admission refused");
 expect(!gate_open(WH3WG_ENROLL,NULL,NULL),"no bootstrap repair");
}
static void held_case(unsigned mode) {
 HANDLE h;int ready;wh3wg_gate *reader=NULL;
 if(!gate_fixture(mode==G_SHARED_HOLD?"shared-child-excludes-owner":"owner-child-excludes-reader"))return;
 h=gate_spawn(mode,0,&admitted);expect(h!=NULL,"spawn native holder");if(!h)return;
 ready=WaitForSingleObject(gr,15000)==WAIT_OBJECT_0&&gs->opened;expect(ready,"child holds admission lock");
 if(!ready){(void)finish(h,1);return;}
 if(mode==G_SHARED_HOLD)expect(!gate_open(WH3WG_OWNER,&admitted,NULL),"owner cannot cross live reader");
 else expect(!wh3wg_open(f.root,gate_ids,DOMAIN_ID,&admitted,WH3WG_SHARED,NULL,&reader),"reader cannot cross owner");
 expect(finish(h,1),"kill holder");expect(gate_open(WH3WG_OWNER,&admitted,NULL),"kernel releases terminated holder");
}
static void pending_case(void) {
 void *cap=NULL,*borrow=NULL;wh3wg_gate *other=NULL;
 if(!gate_fixture("pending-and-nonrevocable-journal-borrow"))return;
 expect(pending(NULL,&cap)&&cap!=NULL,"PENDING persisted before capability");
 wh3wg_domain(gate,&f.domain);
 expect(f.domain.enter(f.domain.context,cap,&f.b,&borrow),"native domain borrow");
 expect(!wh3wg_close(gate),"close refused during borrow");
 expect(f.domain.validate(f.domain.context,borrow),"borrow survives refused close");
 expect(!wh3wg_open(f.root,gate_ids,DOMAIN_ID,&admitted,WH3WG_SHARED,NULL,&other),"reader excluded while owner lives");
 f.domain.leave(f.domain.context,borrow);expect(wh3wg_close(gate),"abandon owner without CLEAN");gate=NULL;
 expect(gate_probe(&admitted)==0,"PENDING persists in a fresh process");
}
static void begin_fault(unsigned fault,const char *name) {
 wh3w_controls control={0};void *cap=(void *)(uintptr_t)1;
 if(!gate_fixture(name))return;control.fault=fault;control.fault_phase=WH3WG_BEGIN_WRITTEN;
 expect(!pending(&control,&cap)&&cap==NULL,"failed BEGIN issues no capability");
 expect(!wh3wg_check(gate),"failed holder poisoned");
 expect(wh3wg_close(gate),"close failed holder");gate=NULL;
 expect(gate_probe(&admitted)==0,"partial or unacknowledged PENDING refuses restart");
}
static void journal_fault(void) {
 void *cap=NULL;wh3_tip before,after;char line[EXR_WH_LINE_MAX];int token=0;
 if(!gate_fixture("journal-uncertainty-needs-no-new-gate-write"))return;
 expect(pending(NULL,&cap),"persistent PENDING");wh3wg_domain(gate,&f.domain);
 f.control.fault=WH3W_FLUSH_FAIL;f.control.fault_phase=WH3W_BEGIN_FLUSHED;
 expect(open_store(),"native journal with real gate");if(!f.store)return;
 empty_tip(&before);(void)wh_manifest(&f.b,&f.g,line);
 expect(wh3w_append(f.store,&token,&before,line,&after)==WH3_TX_MISMATCH,"foreign capability refused");
 expect(wh3w_append(f.store,cap,&before,line,&after)==WH3_TX_UNCERTAIN,"journal fault propagates uncertainty");
 expect(!wh3wg_check(gate),"native domain poisoned");
 wh3w_close(f.store);f.store=NULL;(void)wh3wg_close(gate);gate=NULL;
 expect(gate_probe(&admitted)==0,"original PENDING alone isolates fresh readers");
}
static void finish_case(unsigned fault,int proof_ok,int complete,const char *name) {
 void *cap=NULL;wh3_tip actual;wh3wg_grant next,unchanged;wh3w_controls control={0};proof_control proof={proof_ok,0};
 int ok;
 if(!gate_fixture(name))return;
 control.fault=fault;control.fault_phase=WH3WG_CLEAN_WRITTEN;
 expect(pending(&control,&cap),"begin domain");
 if(complete)expect(terminal(cap,&actual),"complete native terminal journal");
 else {wh3wg_domain(gate,&f.domain);expect(open_store(),"empty journal");empty_tip(&actual);}
 next=admitted;unchanged=next;
 ok=wh3wg_finish(gate,cap,f.store,&actual,prove_terminal,&proof,&next);
 expect(ok==(!fault&&proof_ok&&complete),"finish exact classification");
 if(ok)expect(next.generation==admitted.generation+1&&strcmp(next.seal,admitted.seal),"new exact grant returned");
 else expect(!memcmp(&next,&unchanged,sizeof(next)),"failure never advances trusted grant");
 expect(proof.calls==(complete?1:0),"proof only follows a valid terminal journal");
 wh3w_close(f.store);f.store=NULL;(void)wh3wg_close(gate);gate=NULL;
 expect(gate_probe(&admitted)==0,"old grant never auto-adopts newer bytes");
 if(ok)expect(gate_probe(&next)==1,"acknowledged exact grant admits");
 if(fault==WH3W_FLUSH_FAIL||fault==WH3W_READBACK_FAIL){
  proof_control recovery={1,0};wh3wg_grant recovered;
  expect(gate_open(WH3WG_RECOVER,&admitted,NULL),"fresh recovery custody");
  wh3wg_domain(gate,&f.domain);expect(open_store(),"read actual terminal journal");
  expect(wh3wg_reconcile(gate,f.store,&actual,prove_terminal,&recovery,&recovered),"explicit exact lost-finish reconciliation");
  wh3w_close(f.store);f.store=NULL;(void)wh3wg_close(gate);gate=NULL;
  expect(gate_probe(&recovered)==1,"only independently re-proved grant admits");
 }
}
static void killed(unsigned point,const char *name) {
 HANDLE h;int ready;unsigned mode=point>=WH3WG_CLEAN_WRITTEN?G_FINISH:G_BEGIN;
 if(!gate_fixture(name))return;
 h=gate_spawn(mode,point,&admitted);expect(h!=NULL,"spawn gate owner");if(!h)return;
 ready=WaitForSingleObject(gr,15000)==WAIT_OBJECT_0&&gs->reached==point;
 printf("OBS gate_reached=%u expected=%u\n",gs->reached,point);
 expect(ready,"exact gate barrier");expect(finish(h,1),"kill at deterministic gate phase");if(!ready)return;
 expect(gate_probe(&admitted)==0,"fresh reader refused with old trusted grant");
}
static void resume_case(void) {
 void *cap=NULL,*fresh=NULL;wh3_tip before,after,wrong;char line[EXR_WH_LINE_MAX];
 if(!gate_fixture("recovery-requires-exact-journal-tip"))return;
 expect(pending(NULL,&cap),"begin");wh3wg_domain(gate,&f.domain);expect(open_store(),"journal");
 empty_tip(&before);(void)wh_manifest(&f.b,&f.g,line);
 expect(wh3w_append(f.store,cap,&before,line,&after)==WH3_TX_OK,"one acknowledged transaction");
 wh3w_close(f.store);f.store=NULL;(void)wh3wg_close(gate);gate=NULL;
 expect(gate_open(WH3WG_RECOVER,&admitted,NULL),"fresh exclusive recovery");
 wh3wg_domain(gate,&f.domain);expect(open_store(),"complete actual journal");
 wrong=after;wrong.line_count=0;
 expect(!wh3wg_resume(gate,&f.b,&f.g,f.store,&wrong,&fresh)&&fresh==NULL,"stale tip refused without capability");
 expect(wh3wg_resume(gate,&f.b,&f.g,f.store,&after,&fresh)&&fresh!=NULL,"only exact actual tip resumes");
}
static void c01_drift(void) {
 lm_wl_lease *lease=NULL;lm_wl_error error;wchar_t path[MAX_PATH];unsigned char *data=NULL;
 DWORD n=0;void *cap=NULL;unsigned k;
 if(!gate_fixture("frozen-c01-generation-drift-cannot-clear-domain"))return;
 expect(lm_wl_acquire(f.root,DOMAIN_ID,LM_WL_EXCLUSIVE,0,&lease,&error)==LM_WL_OK,"frozen C01 exclusive");
 expect(lm_wl_exclusive_begin(lease,&error)==LM_WL_OK,"frozen C01 PENDING");lm_wl_release(lease);lease=NULL;
 expect(pending(NULL,&cap),"independent durable domain PENDING");(void)wh3wg_close(gate);gate=NULL;
 swprintf_s(path,MAX_PATH,L"%ls\\%hs.lease",f.root,DOMAIN_ID);
 expect(read_bytes(path,&data,&n)&&n==80,"read unchanged C01 layout");if(!data)return;
 for(k=0;k<16;k++)data[64+k]=0;data[64]=5;
 expect(replace_bytes(path,data,n),"plant generation 5 with PENDING 0");free(data);
 expect(lm_wl_acquire(f.root,DOMAIN_ID,LM_WL_SHARED,0,&lease,&error)==LM_WL_OK,"raw C01 shared admits drifted header");
 expect(lm_wl_generation(lease)==5&&!lm_wl_pending(lease),"observe actual drift");lm_wl_release(lease);
 expect(gate_probe(&admitted)==0,"domain still refuses in fresh process");
}

static void retained_store(void) {
 void *cap=NULL;
 if(!gate_fixture("open-journal-retains-domain-storage"))return;
 expect(pending(NULL,&cap),"begin");wh3wg_domain(gate,&f.domain);
 expect(open_store(),"attach native journal");
 expect(!wh3wg_close(gate),"gate cannot close beneath an open journal");
 expect(wh3wg_check(gate),"refused close preserves custody");
 wh3w_close(f.store);f.store=NULL;
 expect(wh3wg_close(gate),"last journal reference permits close");gate=NULL;
 expect(gate_probe(&admitted)==0,"closing last reference does not clear PENDING");
}
int main(int argc,char **argv) {
 if(argc==3&&!strcmp(argv[1],"--gate-child"))return gate_child(argv[2]);
 initial_case();
 bad_object(0,"missing-gate");bad_object(1,"truncated-gate");
 bad_object(2,"wrong-generation");bad_object(3,"wrong-trusted-seal");
 bad_object(4,"resealed-reserved-byte");bad_object(5,"wrong-native-identity");bad_object(6,"hardlinked-gate");
 held_case(G_SHARED_HOLD);held_case(G_OWNER_HOLD);pending_case();
 begin_fault(WH3W_SHORT_WRITE,"short-pending-write");
 begin_fault(WH3W_FLUSH_FAIL,"failed-pending-flush");
 begin_fault(WH3W_READBACK_FAIL,"failed-pending-readback");
 journal_fault();
 finish_case(0,1,0,"nonterminal-never-clean");finish_case(0,0,1,"publication-not-proven");
 finish_case(0,1,1,"terminal-proof-then-exact-clean-grant");
 finish_case(WH3W_SHORT_WRITE,1,1,"short-clean-write");
 finish_case(WH3W_FLUSH_FAIL,1,1,"failed-clean-flush-old-grant-refused");
 finish_case(WH3W_READBACK_FAIL,1,1,"failed-clean-readback-old-grant-refused");
 killed(WH3WG_BEGIN_WRITTEN,"kill-pending-before-flush");
 killed(WH3WG_BEGIN_DURABLE,"kill-pending-before-capability-return");
 killed(WH3WG_CLEAN_WRITTEN,"kill-clean-before-flush");
 killed(WH3WG_CLEAN_DURABLE,"kill-clean-before-grant-return");
 resume_case();c01_drift();retained_store();gate_close_all();
 printf("{\"source\":\"%s\",\"cases\":%u,\"checks\":%u,\"failed\":%u,\"passed\":%s,"
   "\"persistent_gate\":true,\"frozen_c01_drift\":true,\"publication_proof_control\":true,\"real_owner_wiring\":false}\n",
   CANDIDATE_SOURCE_SHA,cases,checks,failures,failures?"false":"true");
 return failures?1:0;
}
