/* SPDX-License-Identifier: MIT
 * Real NTFS I/O and subprocess tests. Provider/domain callbacks are controls;
 * this executable does not claim production owner or SDK admission coverage. */
#define main wh3w_legacy_main_not_run
#include "../windows_coordinator_hardening_20261030/wh_test.c"
#undef main
#include <exr_wh3_win.h>
#include <stdlib.h>
#include <wchar.h>
#include <winioctl.h>
#define INTENT_BYTES 424u
#define INTENT_SEAL 360u
enum { CHILD_APPEND=1, CHILD_PROBE, CHILD_HOLD, CHILD_STALE, CHILD_NEXT };
typedef struct {
 wchar_t root[MAX_PATH];
 wh3w_identity ids[3];wh_binding b;wh_gates g;HANDLE ready,go;
 unsigned mode,stop,reached;int opened,status,finished;wh3_tip expected,after;
 char first[EXR_WH_LINE_MAX],next[EXR_WH_LINE_MAX];
} shared_case;
typedef struct {
 wchar_t base[MAX_PATH],parent[MAX_PATH],root[MAX_PATH];
 wh3w_identity ids[3];wh_binding b;wh_gates g;
 mock owner;wh3w_domain domain;wh3w_controls control;
 unsigned entered,left,poisoned,revoke_at;wh3w_store *store;
 HANDLE mapping,ready,go;shared_case *shared;
} fixture;
static fixture f;
static unsigned cases;
static const char *label;
static builder built;
static void case_start(const char *name) {
 label=name;cases++;printf("CASE %u %s\n",cases,name);fflush(stdout);
}
static void expect(int ok,const char *what) { check(ok,label,what); }
static int domain_enter(void *ctx,void *cap,const wh_binding *b,void **guard) {
 fixture *x=ctx;
 if(cap!=&x->owner.token||x->owner.fail_check||memcmp(b,&x->b,sizeof(*b)))return 0;
 x->entered++;*guard=x;return 1;
}
static int domain_valid(void *ctx,void *guard) {
 fixture *x=ctx;return guard==x&&!x->owner.fail_check;
}
static void domain_poison(void *ctx,void *guard,const char *why) {
 fixture *x=ctx;(void)guard;(void)why;x->poisoned++;
}
static void domain_leave(void *ctx,void *guard) {
 fixture *x=ctx;(void)guard;x->left++;
}
static void barrier(void *ctx,unsigned at) {
 fixture *x=ctx;
 if(at==x->revoke_at)x->owner.fail_check=1;
 if(x->shared&&at==x->shared->stop) {
  x->shared->reached=at;SetEvent(x->shared->ready);
  if(WaitForSingleObject(x->shared->go,15000)!=WAIT_OBJECT_0)ExitProcess(91);
 }
}
static void setup_callbacks(void) {
 mock_init(&f.owner);
 f.domain.context=&f;f.domain.enter=domain_enter;f.domain.validate=domain_valid;
 f.domain.poison=domain_poison;f.domain.leave=domain_leave;
 f.control.context=&f;f.control.phase=barrier;
}
static void leaf_path(const wchar_t *root,unsigned which,wchar_t out[MAX_PATH]) {
 swprintf_s(out,MAX_PATH,L"%ls\\%ls",root,which?L"intent.bin":L"journal.bin");
}
static int capture_id(const wchar_t *path,int dir,wh3w_identity *out) {
 FILE_ID_INFO id;HANDLE h;int ok;
 h=CreateFileW(path,FILE_READ_ATTRIBUTES,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,
   NULL,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT|(dir?FILE_FLAG_BACKUP_SEMANTICS:0),NULL);
 if(h==INVALID_HANDLE_VALUE)return 0;
 ok=GetFileInformationByHandleEx(h,FileIdInfo,&id,sizeof(id))!=0;CloseHandle(h);
 if(ok){out->volume=id.VolumeSerialNumber;out->file=id.FileId;}return ok;
}
static int create_files(const wchar_t *root) {
 unsigned i;wchar_t path[MAX_PATH];
 for(i=0;i<2;i++){
  HANDLE h;leaf_path(root,i,path);
  h=CreateFileW(path,GENERIC_READ|GENERIC_WRITE,FILE_SHARE_READ,NULL,CREATE_NEW,0,NULL);
  if(h==INVALID_HANDLE_VALUE)return 0;
  if(!FlushFileBuffers(h)){CloseHandle(h);return 0;}CloseHandle(h);
 }
 return 1;
}
static void fixture_close(void) {
 wh3w_close(f.store);f.store=NULL;
 if(f.shared){UnmapViewOfFile(f.shared);f.shared=NULL;}
 if(f.mapping)CloseHandle(f.mapping);
 if(f.ready)CloseHandle(f.ready);
 if(f.go)CloseHandle(f.go);
 f.mapping=f.ready=f.go=NULL;
}
static int fixture_new(void) {
 wchar_t path[MAX_PATH],relative[MAX_PATH];unsigned i;
 fixture_close();memset(&f,0,sizeof(f));setup_callbacks();
 f.b=binding_of();snprintf(f.b.platform,sizeof(f.b.platform),"windows-2022");f.g=gates_of('a');
 (void)CreateDirectoryW(L"evidence",NULL);
 (void)CreateDirectoryW(L"evidence\\native-files",NULL);
 swprintf_s(relative,MAX_PATH,L"evidence\\native-files\\case-%03u",cases);
 if(!GetFullPathNameW(relative,MAX_PATH,f.base,NULL)||!CreateDirectoryW(f.base,NULL))return 0;
 swprintf_s(f.parent,MAX_PATH,L"%ls\\a",f.base);swprintf_s(f.root,MAX_PATH,L"%ls\\b",f.parent);
 if(!CreateDirectoryW(f.parent,NULL)||!CreateDirectoryW(f.root,NULL)||!create_files(f.root))return 0;
 if(!capture_id(f.root,1,&f.ids[0]))return 0;
 for(i=0;i<2;i++){leaf_path(f.root,i,path);if(!capture_id(path,0,&f.ids[i+1]))return 0;}
 return 1;
}
static int open_store(void) {
 return wh3w_open(f.root,f.ids,&f.b,&f.g,&f.domain,&f.control,&f.store);
}
static void empty_tip(wh3_tip *t) {
 char m[EXR_WH_LINE_MAX];memset(t,0,sizeof(*t));(void)wh_manifest(&f.b,&f.g,m);
 wh_sha256_hex(m,strlen(m),t->manifest_sha);memset(t->last_line_sha,'0',64);
}
static int append_lines(size_t n) {
 wh3_tip before,after;size_t k;empty_tip(&before);
 build_to_publish(&f.b,&f.g,&built,1);if(n>built.n)return 0;
 for(k=0;k<n;k++){
  if(wh3w_append(f.store,&f.owner.token,&before,built.lines[k],&after)!=WH3_TX_OK)return 0;
  before=after;
 }
 return 1;
}
static int read_bytes(const wchar_t *path,unsigned char **data,DWORD *n) {
 HANDLE h;LARGE_INTEGER z;DWORD got;int ok;*data=NULL;*n=0;
 h=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_EXISTING,0,NULL);
 if(h==INVALID_HANDLE_VALUE)return 0;
 if(!GetFileSizeEx(h,&z)||z.QuadPart<0||z.QuadPart>2*1024*1024){CloseHandle(h);return 0;}
 *n=(DWORD)z.QuadPart;*data=malloc((size_t)*n+1);
 if(!*data){CloseHandle(h);return 0;}
 ok=ReadFile(h,*data,*n,&got,NULL)&&got==*n;CloseHandle(h);
 if(!ok){free(*data);*data=NULL;}return ok;
}
static int replace_bytes(const wchar_t *path,const void *data,DWORD n) {
 HANDLE h;DWORD put;int ok;
 h=CreateFileW(path,GENERIC_WRITE,0,NULL,CREATE_ALWAYS,0,NULL);
 if(h==INVALID_HANDLE_VALUE)return 0;
 ok=WriteFile(h,data,n,&put,NULL)&&put==n&&FlushFileBuffers(h);CloseHandle(h);return ok;
}
static int fingerprint(char out[131]) {
 unsigned i;wchar_t path[MAX_PATH];unsigned char *data;DWORD n;
 for(i=0;i<2;i++){
  leaf_path(f.root,i,path);if(!read_bytes(path,&data,&n))return 0;
  wh_sha256_hex(data,n,out+i*65);free(data);
 }
 out[130]=0;return 1;
}
static int make_shared(void) {
 SECURITY_ATTRIBUTES sa={sizeof(sa),NULL,TRUE};
 f.mapping=CreateFileMappingW(INVALID_HANDLE_VALUE,&sa,PAGE_READWRITE,0,sizeof(shared_case),NULL);
 f.ready=CreateEventW(&sa,TRUE,FALSE,NULL);f.go=CreateEventW(&sa,TRUE,FALSE,NULL);
 if(!f.mapping||!f.ready||!f.go)return 0;
 f.shared=MapViewOfFile(f.mapping,FILE_MAP_ALL_ACCESS,0,0,sizeof(shared_case));
 if(!f.shared)return 0;
 memset(f.shared,0,sizeof(*f.shared));wcscpy_s(f.shared->root,MAX_PATH,f.root);
 memcpy(f.shared->ids,f.ids,sizeof(f.ids));f.shared->b=f.b;f.shared->g=f.g;
 f.shared->ready=f.ready;f.shared->go=f.go;empty_tip(&f.shared->expected);
 build_to_publish(&f.b,&f.g,&built,1);
 strcpy_s(f.shared->first,EXR_WH_LINE_MAX,built.lines[0]);
 strcpy_s(f.shared->next,EXR_WH_LINE_MAX,built.lines[1]);return 1;
}
static HANDLE spawn(unsigned mode,unsigned stop) {
 wchar_t exe[MAX_PATH],command[2*MAX_PATH];STARTUPINFOW si;PROCESS_INFORMATION pi;
 if(!f.shared&&!make_shared())return NULL;
 ResetEvent(f.ready);ResetEvent(f.go);
 f.shared->mode=mode;f.shared->stop=stop;f.shared->reached=0;
 f.shared->opened=0;f.shared->status=-1;f.shared->finished=0;
 if(!GetModuleFileNameW(NULL,exe,MAX_PATH))return NULL;
 swprintf_s(command,2*MAX_PATH,L"\"%ls\" --child %llu",exe,(unsigned long long)(uintptr_t)f.mapping);
 memset(&si,0,sizeof(si));si.cb=sizeof(si);memset(&pi,0,sizeof(pi));
 if(!CreateProcessW(exe,command,NULL,NULL,TRUE,CREATE_NO_WINDOW,NULL,NULL,&si,&pi))return NULL;
 printf("OBS child mode=%u pid=%lu barrier=%u\n",mode,(unsigned long)pi.dwProcessId,stop);
 CloseHandle(pi.hThread);return pi.hProcess;
}
static int finish(HANDLE child,int kill) {
 DWORD exit=99;int ok;if(!child)return 0;
 if(kill&&!TerminateProcess(child,77)){CloseHandle(child);return 0;}
 ok=WaitForSingleObject(child,20000)==WAIT_OBJECT_0;
 if(ok)ok=GetExitCodeProcess(child,&exit)&&exit==(kill?77u:0u);
 if(!ok)(void)TerminateProcess(child,92);CloseHandle(child);return ok;
}
static int fresh_probe(void) {
 HANDLE h=spawn(CHILD_PROBE,0);
 if(!finish(h,0)||!f.shared->finished)return -1;return f.shared->opened;
}
static int child_main(const char *handle) {
 shared_case *v;wh3_tip after;HANDLE mapping=(HANDLE)(uintptr_t)_strtoui64(handle,NULL,10);
 v=MapViewOfFile(mapping,FILE_MAP_ALL_ACCESS,0,0,sizeof(*v));if(!v)return 90;
 memset(&f,0,sizeof(f));setup_callbacks();f.shared=v;
 wcscpy_s(f.root,MAX_PATH,v->root);memcpy(f.ids,v->ids,sizeof(f.ids));f.b=v->b;f.g=v->g;
 v->opened=open_store();
 if(v->mode==CHILD_HOLD){SetEvent(v->ready);if(WaitForSingleObject(v->go,15000)!=WAIT_OBJECT_0)return 93;}
 else if(v->opened&&v->mode!=CHILD_PROBE){
  v->status=wh3w_append(f.store,&f.owner.token,&v->expected,
    v->mode==CHILD_NEXT?v->next:v->first,&after);
  if(v->status==WH3_TX_OK)v->after=after;
 }
 wh3w_close(f.store);v->finished=1;UnmapViewOfFile(v);return 0;
}

static void happy(void) {
 wh3_session *s;wh3_backend backend;wh_provider provider;wh_report report;
 case_start("installed-native-full-run");expect(fixture_new(),"fixture");
 if(!open_store()){expect(0,"open");return;}expect(1,"open");
 provider_of(&provider,&f.owner);backend.abi=EXR_WH3_ABI;backend.context=f.store;backend.append=wh3w_append;
 s=wh3_create(&f.b,&f.g,&provider,&backend);expect(s!=NULL,"session");if(!s)return;
 expect(wh3_run(s,&report)==WH_COMPLETED,"durable run");
 expect(f.owner.release_calls==1&&f.poisoned==0,"owner release only after successful transactions");
 expect(f.entered==f.left&&f.entered>10,"balanced nonrevocable borrows");
 expect(wh3_dispose(s)==1,"clean disposal");
 wh3w_close(f.store);f.store=NULL;expect(fresh_probe()==1,"new process validates full disk history");
}
static void cas_mismatch(unsigned mode,const char *name) {
 wh3_tip old,after;char first[EXR_WH_LINE_MAX],before[131]={0},now[131]={0};wh3_tx_status result;
 case_start(name);expect(fixture_new()&&open_store(),"fixture/open");if(!f.store)return;
 empty_tip(&old);(void)wh_manifest(&f.b,&f.g,first);
 if(mode==0)old.line_count=1;
 if(mode==1)old.last_line_sha[0]='a';
 if(mode==2)old.manifest_sha[0]=old.manifest_sha[0]=='a'?'b':'a';
 if(mode==3){expect(append_lines(1),"advance actual disk");}
 if(mode==4)first[5]^=1;
 if(mode==5)f.owner.fail_check=1;
 if(mode==6)f.revoke_at=WH3W_PRE_BEGIN;
 expect(fingerprint(before),"capture before");
 result=wh3w_append(f.store,&f.owner.token,&old,first,&after);
 expect(result==WH3_TX_MISMATCH,"MISMATCH");
 expect(fingerprint(now)&&!memcmp(before,now,sizeof(before)),"both files byte-identical");
 expect(f.owner.release_calls==0&&f.owner.discard_calls==0&&f.owner.inspect_calls==0,"no downstream effects");
}
static void crash(unsigned point,const char *name) {
 HANDLE child;int ready,complete;char before[131]={0},now[131]={0};
 case_start(name);expect(fixture_new(),"fixture");
 child=spawn(CHILD_APPEND,point);expect(child!=NULL,"spawn writer");if(!child)return;
 ready=WaitForSingleObject(f.ready,15000)==WAIT_OBJECT_0&&f.shared->reached==point;
 printf("OBS reached=%u expected=%u\n",f.shared->reached,point);
 expect(ready,"exact phase barrier");expect(finish(child,1),"terminate process at barrier");if(!ready)return;
 expect(fingerprint(before),"capture killed bytes");
 complete=point==WH3W_PRE_BEGIN||point==WH3W_ACK_WRITTEN||point==WH3W_ACK_FLUSHED;
 expect(fresh_probe()==complete,"fresh process exact recovery classification");
 expect(fingerprint(now)&&!memcmp(before,now,sizeof(before)),"probe never repairs or changes bytes");
 if(point==WH3W_ACK_WRITTEN||point==WH3W_ACK_FLUSHED){
  child=spawn(CHILD_STALE,0);expect(finish(child,0),"stale caller process exits");
  expect(f.shared->opened&&f.shared->status==WH3_TX_MISMATCH,"lost receipt does not upgrade old expected");
  expect(fingerprint(now)&&!memcmp(before,now,sizeof(before)),"stale recovery writes nothing");
  f.shared->expected.line_count=1;
  wh_sha256_hex(f.shared->first,strlen(f.shared->first),f.shared->expected.last_line_sha);
  child=spawn(CHILD_NEXT,0);expect(finish(child,0),"exact newtip recovery process");
  expect(f.shared->status==WH3_TX_OK&&f.shared->after.line_count==2,"only exact newtip continues");
 }
}
static void fault(unsigned kind,unsigned point,const char *name) {
 wh3_session *s;wh3_backend backend;wh_provider provider;wh_report report;
 case_start(name);expect(fixture_new(),"fixture");f.control.fault=kind;f.control.fault_phase=point;
 expect(open_store(),"open");if(!f.store)return;
 provider_of(&provider,&f.owner);backend.abi=EXR_WH3_ABI;backend.context=f.store;backend.append=wh3w_append;
 s=wh3_create(&f.b,&f.g,&provider,&backend);expect(s!=NULL,"session");if(!s)return;
 expect(wh3_run(s,&report)==WH_UNCERTAIN,"UNCERTAIN after attempted BEGIN");
 expect(f.poisoned==1&&report.live_lease&&wh3_dispose(s)==0,"poison and capability retained");
 expect(f.owner.release_calls==0&&f.owner.discard_calls==0&&f.owner.inspect_calls==0,"no downstream effects");
 wh3w_close(f.store);f.store=NULL;expect(fresh_probe()==0,"poison suffix/dangling BEGIN survives close and new process");
}
static void writers(int child_first) {
 HANDLE child;int ready;wh3w_store *other=NULL;wchar_t alias[MAX_PATH];size_t i;
 case_start(child_first?"writer-child-first":"writer-parent-first");expect(fixture_new(),"fixture");
 if(child_first){
  child=spawn(CHILD_HOLD,0);expect(child!=NULL,"spawn holder");if(!child)return;
  ready=WaitForSingleObject(f.ready,15000)==WAIT_OBJECT_0&&f.shared->opened;
  expect(ready,"child holds files");if(!ready){(void)finish(child,1);return;}
  expect(!open_store(),"second process writer refused");
  SetEvent(f.go);expect(finish(child,0),"holder exits");
  expect(open_store(),"writer opens after holder closes");
 }else{
  expect(open_store(),"parent holds files");if(!f.store)return;
  expect(fresh_probe()==0,"other process writer refused");
  wcscpy_s(alias,MAX_PATH,f.root);
  for(i=0;alias[i];i++)if(alias[i]>=L'a'&&alias[i]<=L'z')alias[i]-=L'a'-L'A';
  expect(!wh3w_open(alias,f.ids,&f.b,&f.g,&f.domain,&f.control,&other),"case alias is same locked object");
  wh3w_close(other);wh3w_close(f.store);f.store=NULL;
  expect(fresh_probe()==1,"new writer after close");
 }
}
static void read_sharing(int reader_first) {
 wchar_t path[MAX_PATH];HANDLE h;
 case_start(reader_first?"readonly-first":"writer-before-readonly");expect(fixture_new(),"fixture");
 leaf_path(f.root,0,path);
 if(!reader_first)expect(open_store(),"writer open");
 h=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_EXISTING,0,NULL);
 expect(h!=INVALID_HANDLE_VALUE,"compatible read-only handle");
 if(reader_first)expect(open_store(),"writer compatible with existing reader");
 expect(f.store!=NULL,"both handles live");if(h!=INVALID_HANDLE_VALUE)CloseHandle(h);
}
static void hardlink_case(int after) {
 wchar_t path[MAX_PATH],alias[MAX_PATH];BOOL linked;DWORD error;wh3_tip old,out;
 char line[EXR_WH_LINE_MAX],before[131]={0},now[131]={0};
 case_start(after?"hardlink-after-open":"hardlink-before-open");expect(fixture_new(),"fixture");
 leaf_path(f.root,0,path);swprintf_s(alias,MAX_PATH,L"%ls\\alias.bin",f.base);
 if(after){expect(open_store(),"open");if(!f.store)return;}
 linked=CreateHardLinkW(alias,path,NULL);error=GetLastError();
 printf("OBS hardlink_after=%d created=%d error=%lu\n",after,(int)linked,(unsigned long)error);
 if(!after){expect(linked!=0,"initial hardlink really created");expect(!open_store(),"multiple links refused");return;}
 expect(fingerprint(before),"before");
 empty_tip(&old);(void)wh_manifest(&f.b,&f.g,line);
 if(linked){
  expect(wh3w_append(f.store,&f.owner.token,&old,line,&out)==WH3_TX_MISMATCH,"link count revalidated before write");
  expect(fingerprint(now)&&!memcmp(before,now,sizeof(before)),"identity refusal changes neither file");
 }else{
  expect(error==ERROR_SHARING_VIOLATION,"OS denied link with sharing violation");
  expect(wh3w_append(f.store,&f.owner.token,&old,line,&out)==WH3_TX_OK,"unchanged object still usable");
 }
}
static void ancestry(void) {
 const wchar_t *paths[3];wchar_t moved[MAX_PATH];unsigned k;
 case_start("pinned-ancestors-rename-delete-write");expect(fixture_new(),"fixture");
 paths[0]=f.base;paths[1]=f.parent;paths[2]=f.root;
 for(k=0;k<3;k++){
  swprintf_s(moved,MAX_PATH,L"%ls-renamed",paths[k]);
  expect(MoveFileW(paths[k],moved)!=0,"baseline nonempty directory can be renamed");
  expect(MoveFileW(moved,paths[k])!=0,"baseline name restored");
 }
 expect(open_store(),"pins acquired");if(!f.store)return;
 for(k=0;k<3;k++){
  HANDLE h;DWORD error;BOOL moved_ok;
  swprintf_s(moved,MAX_PATH,L"%ls-renamed",paths[k]);
  moved_ok=MoveFileW(paths[k],moved);error=GetLastError();
  expect(!moved_ok&&error==ERROR_SHARING_VIOLATION,"actual rename blocked by share mode");
  h=CreateFileW(paths[k],DELETE,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,NULL,
    OPEN_EXISTING,FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,NULL);error=GetLastError();
  expect(h==INVALID_HANDLE_VALUE&&error==ERROR_SHARING_VIOLATION,"delete-capable open blocked before nonempty check");
  if(h!=INVALID_HANDLE_VALUE)CloseHandle(h);
  h=CreateFileW(paths[k],GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,NULL,
    OPEN_EXISTING,FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,NULL);error=GetLastError();
  expect(h==INVALID_HANDLE_VALUE&&error==ERROR_SHARING_VIOLATION,"reparse-capable write handle blocked");
  if(h!=INVALID_HANDLE_VALUE)CloseHandle(h);
 }
}
static void rebind_during_open(void) {
 HANDLE child;wchar_t moved[MAX_PATH];int ready;BOOL changed;DWORD error;
 case_start("unpinned-descendant-rebind-during-open");expect(fixture_new(),"fixture");
 swprintf_s(moved,MAX_PATH,L"%ls-old",f.root);
 expect(MoveFileW(f.root,moved)!=0,"baseline target rename works");
 expect(MoveFileW(moved,f.root)!=0,"baseline target restored");
 /* Only the volume root is pinned. Pinning the target parent would already
    prevent the namespace write, so that is not a successful-rebind fixture. */
 child=spawn(CHILD_PROBE,WH3W_PINNED_BASE+1);expect(child!=NULL,"spawn opener");if(!child)return;
 ready=WaitForSingleObject(f.ready,15000)==WAIT_OBJECT_0;
 expect(ready&&f.shared->reached==WH3W_PINNED_BASE+1,"volume root pinned, target parent not opened");
 if(!ready){(void)finish(child,1);return;}
 changed=MoveFileW(f.root,moved);error=GetLastError();
 printf("OBS midopen root_move=%d error=%lu reached=%u\n",(int)changed,(unsigned long)error,f.shared->reached);
 expect(changed!=0,"unopened descendant actually moved");
 expect(CreateDirectoryW(f.root,NULL)&&create_files(f.root),"replacement objects installed");
 SetEvent(f.go);expect(finish(child,0),"opener finishes");expect(!f.shared->opened,"trusted root ID rejects new input binding");
}

static int junction(const wchar_t *alias,const wchar_t *target) {
 struct {
  DWORD tag;WORD length,reserved;WORD sub_offset,sub_length,print_offset,print_length;
  wchar_t buffer[2*MAX_PATH+16];
 } r;
 wchar_t substitute[MAX_PATH+8];size_t a,b;HANDLE h;DWORD done;int ok;
 if(!CreateDirectoryW(alias,NULL))return 0;
 swprintf_s(substitute,MAX_PATH+8,L"\\??\\%ls",target);a=wcslen(substitute);b=wcslen(target);
 memset(&r,0,sizeof(r));r.tag=IO_REPARSE_TAG_MOUNT_POINT;
 r.sub_length=(WORD)(a*sizeof(wchar_t));r.print_offset=(WORD)((a+1)*sizeof(wchar_t));
 r.print_length=(WORD)(b*sizeof(wchar_t));r.length=(WORD)(8+(a+b+2)*sizeof(wchar_t));
 memcpy(r.buffer,substitute,(a+1)*sizeof(wchar_t));memcpy(r.buffer+a+1,target,(b+1)*sizeof(wchar_t));
 h=CreateFileW(alias,GENERIC_WRITE,0,NULL,OPEN_EXISTING,
    FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,NULL);
 if(h==INVALID_HANDLE_VALUE)return 0;
 ok=DeviceIoControl(h,FSCTL_SET_REPARSE_POINT,&r,(DWORD)r.length+8,NULL,0,&done,NULL)!=0;
 CloseHandle(h);return ok;
}
static void initial_reparse(void) {
 wchar_t alias[MAX_PATH];wh3w_store *store=NULL;
 case_start("initial-reparse-ancestor");expect(fixture_new(),"fixture");
 swprintf_s(alias,MAX_PATH,L"%ls\\junction",f.base);
 expect(junction(alias,f.root),"real junction created");
 expect(!wh3w_open(alias,f.ids,&f.b,&f.g,&f.domain,&f.control,&store),"initial reparse refused");
 wh3w_close(store);
}
static void reseal(unsigned char *data,DWORD n,int wrong_ack) {
 DWORD pos;char prev[65],hash[65],begin[65];
 memset(prev,'0',64);prev[64]=0;memset(begin,0,sizeof(begin));
 for(pos=0;pos<n;pos+=INTENT_BYTES){
  unsigned char *r=data+pos;memcpy(r+296,prev,64);
  if(r[8]=='A'){
   memcpy(r+232,begin,64);
   if(wrong_ack&&pos==INTENT_BYTES)r[232]=r[232]=='a'?'b':'a';
  }
  wh_sha256_hex(r,INTENT_SEAL,hash);memcpy(r+INTENT_SEAL,hash,64);
  if(r[8]=='B')memcpy(begin,hash,65);memcpy(prev,hash,65);
 }
}
static void corrupt(unsigned mode,const char *name) {
 wchar_t path[MAX_PATH];unsigned char *data=NULL;DWORD n=0;char before[131]={0},after[131]={0};
 case_start(name);expect(fixture_new()&&open_store(),"fixture/open");if(!f.store)return;
 expect(append_lines(3),"three genuine durable transactions");wh3w_close(f.store);f.store=NULL;
 leaf_path(f.root,mode==5?0:1,path);expect(read_bytes(path,&data,&n),"raw fixture read");if(!data)return;
 if(mode==0)n=0; /* No implicit bootstrap of an existing journal. */
 if(mode==1){data[9]=1;reseal(data,n,0);}
 if(mode==2){
  memcpy(data+2*INTENT_BYTES,data,2*INTENT_BYTES);
  data[2*INTENT_BYTES+16]=2;data[3*INTENT_BYTES+16]=2;
  reseal(data,n,0); /* Duplicate count zero, skip count one, later reaches three. */
 }
 if(mode==3)reseal(data,n,1);
 if(mode==4){data[16]=7;data[INTENT_BYTES+16]=7;reseal(data,n,0);}
 if(mode==5){
  DWORD first=(DWORD)data[0]|((DWORD)data[1]<<8)|((DWORD)data[2]<<16)|((DWORD)data[3]<<24);
  data[4+first+4+10]^=1; /* Preserve manifest, count, and the complete last line. */
 }
 if(mode==6)n--; /* Torn canonical record. */
 expect(replace_bytes(path,data,n),"write planted mutation");free(data);
 expect(fingerprint(before),"capture mutated files");
 expect(fresh_probe()==0,"new process refuses semantically invalid store");
 expect(fingerprint(after)&&!memcmp(before,after,sizeof(before)),"refusal never repairs bytes");
}
static void bad_identity(unsigned which) {
 char before[131]={0},after[131]={0};wh3w_identity saved;
 case_start(which==0?"wrong-root-id":which==1?"wrong-journal-id":"wrong-intent-id");
 expect(fixture_new(),"fixture");saved=f.ids[which];f.ids[which].file.Identifier[0]^=1;
 expect(fingerprint(before),"before");expect(!open_store(),"trusted identity mismatch");
 expect(fingerprint(after)&&!memcmp(before,after,sizeof(before)),"open refusal zero mutation");
 f.ids[which]=saved;
}
static void revoke_after_begin(void) {
 wh3_tip expected,after;char line[EXR_WH_LINE_MAX];
 case_start("domain-revoked-after-begin");expect(fixture_new()&&open_store(),"fixture/open");if(!f.store)return;
 f.revoke_at=WH3W_BEGIN_FLUSHED;empty_tip(&expected);(void)wh_manifest(&f.b,&f.g,line);
 expect(wh3w_append(f.store,&f.owner.token,&expected,line,&after)==WH3_TX_UNCERTAIN,"UNCERTAIN");
 expect(f.poisoned==1&&f.entered==f.left,"poison callback, borrow balanced");
 wh3w_close(f.store);f.store=NULL;expect(fresh_probe()==0,"durable unresolved intent");
}
#ifndef WH3W_TEST_ENTRY
#define WH3W_TEST_ENTRY main
#endif
int WH3W_TEST_ENTRY(int argc,char **argv) {
 if(argc==3&&!strcmp(argv[1],"--child"))return child_main(argv[2]);
 happy();
 cas_mismatch(0,"cas-count");cas_mismatch(1,"cas-full-tail");cas_mismatch(2,"cas-manifest");
 cas_mismatch(3,"cas-advanced-actual");cas_mismatch(4,"invalid-prospective-chain");
 cas_mismatch(5,"invalid-capability");cas_mismatch(6,"revoked-at-prebegin");
 crash(WH3W_PRE_BEGIN,"kill-prebegin");crash(WH3W_BEGIN_PARTIAL,"kill-partial-begin");
 crash(WH3W_BEGIN_FLUSHED,"kill-begin-flushed");
 crash(WH3W_JOURNAL_HEADER_PARTIAL,"kill-partial-length-header");
 crash(WH3W_JOURNAL_BODY_PARTIAL,"kill-partial-body");crash(WH3W_JOURNAL_WRITTEN,"kill-journal-written");
 crash(WH3W_JOURNAL_FLUSHED,"kill-journal-flushed");crash(WH3W_ACK_PARTIAL,"kill-partial-ack");
 crash(WH3W_ACK_WRITTEN,"kill-ack-before-flush-confirmation");crash(WH3W_ACK_FLUSHED,"kill-durable-ack-before-return");
 fault(WH3W_SHORT_WRITE,WH3W_BEGIN_PARTIAL,"short-begin");
 fault(WH3W_SHORT_WRITE,WH3W_JOURNAL_HEADER_PARTIAL,"short-length-header");
 fault(WH3W_SHORT_WRITE,WH3W_JOURNAL_BODY_PARTIAL,"short-body");
 fault(WH3W_SHORT_WRITE,WH3W_ACK_PARTIAL,"short-ack");
 fault(WH3W_FLUSH_FAIL,WH3W_BEGIN_FLUSHED,"failed-begin-flush");
 fault(WH3W_FLUSH_FAIL,WH3W_JOURNAL_FLUSHED,"failed-journal-flush");
 fault(WH3W_FLUSH_FAIL,WH3W_ACK_FLUSHED,"failed-ack-flush");
 fault(WH3W_READBACK_FAIL,0,"failed-independent-readback");
 writers(0);writers(1);read_sharing(0);read_sharing(1);
 hardlink_case(0);hardlink_case(1);ancestry();initial_reparse();rebind_during_open();
 corrupt(0,"reject-implicit-bootstrap");corrupt(1,"resealed-reserved-byte");
 corrupt(2,"resealed-duplicate-gap");corrupt(3,"resealed-wrong-ack-binding");
 corrupt(4,"resealed-sequence-gap");corrupt(5,"same-tip-interior-corruption");
 corrupt(6,"torn-intent-record");bad_identity(0);bad_identity(1);bad_identity(2);revoke_after_begin();
 fixture_close();
 printf("{\"source\":\"%s\",\"cases\":%u,\"checks\":%u,\"failed\":%u,\"passed\":%s,"
        "\"native_io\":true,\"subprocess_crash\":true,\"power_loss\":false,\"real_owner_wiring\":false}\n",
        CANDIDATE_SOURCE_SHA,cases,checks,failures,failures?"false":"true");
 return failures?1:0;
}
