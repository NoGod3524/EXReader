/* SPDX-License-Identifier: MIT
 * Installed registry adapter + frozen SDK; explicit test orchestration is not
 * the production migration coordinator or its worker recovery engine. */
#define WH3W_TEST_ENTRY wh3w_native_reference_main
#include "../windows_coordinator_native_journal_20261030/wh3_win_test.c"
#include <exr/library.h>
#include <sddl.h>
static wh3wr_registration *registration;
static wchar_t reglib[MAX_PATH];
static const char original[]="C02 registered original\n",published[]="C02 published original\n";
typedef struct {
 wchar_t library[MAX_PATH];wh_binding b;wh_gates g;
 HANDLE ready,go;unsigned mode,stop;int opened,sdk_opened,reached;
} reg_shared;
static HANDLE rm,rrdy,rgo;
static reg_shared *rs;
static int utf8_path(const wchar_t *wide,char narrow[4*MAX_PATH]) {
 return WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide,-1,narrow,4*MAX_PATH,NULL,NULL)>0;
}
static int sdk_seed(const wchar_t *path,const char *text) {
 char narrow[4*MAX_PATH];exr_library *lib=NULL;exr_error error={0};int64_t book=0;int ok;
 if(!utf8_path(path,narrow)||exr_library_open(narrow,&lib,&error)!=EXR_OK)return 0;
 ok=exr_library_import(lib,EXR_TXT,text,strlen(text),"C02",&book,&error)==EXR_OK&&book>0;
 exr_library_close(lib);return ok;
}
static int sdk_prove(void *context,const wchar_t *path) {
 const char *expected=context;char narrow[4*MAX_PATH],bytes[128];exr_library *lib=NULL;
 exr_error error={0};exr_book *books=NULL;size_t n=0;exr_source source={0};int ok=0;
 if(!utf8_path(path,narrow)||exr_library_open(narrow,&lib,&error)!=EXR_OK)return 0;
 if(exr_library_books(lib,NULL,&books,&n,&error)!=EXR_OK||n!=1||
    exr_library_source(lib,books[0].id,&source,&error)!=EXR_OK||source.size!=strlen(expected)||source.size>sizeof(bytes))goto done;
 ok=source.read_at(source.context,0,bytes,(size_t)source.size)==source.size&&!memcmp(bytes,expected,(size_t)source.size);
done:
 if(source.release)source.release(source.context);exr_books_free(books,n);exr_library_close(lib);return ok;
}
static int reg_prove(void *context,const wh3_tip *tip) {
 return tip->line_count==13&&sdk_prove(context,reglib);
}
static int initial_refuse(void *context,const wchar_t *path) {(void)context;(void)path;return 0;}
static void reg_close_all(void) {
 wh3w_close(f.store);f.store=NULL;
 expect(wh3wr_close(registration),"registration closes only after journal");registration=NULL;
 fixture_close();
}
static int reg_fixture(const char *name,int enroll) {
 wchar_t path[MAX_PATH];HANDLE h;
 if(registration){wh3w_close(f.store);f.store=NULL;(void)wh3wr_close(registration);registration=NULL;}
 case_start(name);if(!fixture_new()){expect(0,"native fixture");return 0;}
 swprintf_s(reglib,MAX_PATH,L"%ls\\library.sqlite",f.parent);
 expect(sdk_seed(reglib,original),"real frozen SDK initial library");
 swprintf_s(path,MAX_PATH,L"%ls\\admission.bin",f.root);
 h=CreateFileW(path,GENERIC_READ|GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,CREATE_NEW,0,NULL);
 if(h==INVALID_HANDLE_VALUE){expect(0,"create empty admission");return 0;}
 expect(FlushFileBuffers(h)!=0,"flush empty admission");CloseHandle(h);
 if(enroll&&!wh3wr_enroll(reglib,f.root,sdk_prove,(void *)original)){expect(0,"explicit registry enrollment with actual SDK proof");return 0;}
 return 1;
}
static int reg_open(unsigned mode,const wh3w_controls *controls) {
 return wh3wr_open(reglib,mode,controls,&registration);
}
static void reg_barrier(void *context,unsigned phase_number) {
 reg_shared *shared=context;
 if(shared->stop==phase_number){shared->reached=(int)phase_number;SetEvent(shared->ready);
  if(WaitForSingleObject(shared->go,15000)!=WAIT_OBJECT_0)ExitProcess(93);}
}
static HANDLE reg_spawn(unsigned mode,unsigned stop) {
 SECURITY_ATTRIBUTES sa={sizeof(sa),NULL,TRUE};wchar_t exe[MAX_PATH],command[2*MAX_PATH];STARTUPINFOW si={0};PROCESS_INFORMATION pi={0};
 if(!rs){
  rm=CreateFileMappingW(INVALID_HANDLE_VALUE,&sa,PAGE_READWRITE,0,sizeof(*rs),NULL);
  rrdy=CreateEventW(&sa,TRUE,FALSE,NULL);rgo=CreateEventW(&sa,TRUE,FALSE,NULL);
  if(!rm||!rrdy||!rgo)return NULL;rs=MapViewOfFile(rm,FILE_MAP_ALL_ACCESS,0,0,sizeof(*rs));if(!rs)return NULL;
 }
 memset(rs,0,sizeof(*rs));ResetEvent(rrdy);ResetEvent(rgo);
 wcscpy_s(rs->library,MAX_PATH,reglib);rs->b=f.b;rs->g=f.g;
 rs->ready=rrdy;rs->go=rgo;rs->mode=mode;rs->stop=stop;
 if(!GetModuleFileNameW(NULL,exe,MAX_PATH))return NULL;
 swprintf_s(command,2*MAX_PATH,L"\"%ls\" --registry-child %llu",exe,(unsigned long long)(uintptr_t)rm);
 si.cb=sizeof(si);
 if(!CreateProcessW(exe,command,NULL,NULL,TRUE,CREATE_NO_WINDOW,NULL,NULL,&si,&pi))return NULL;
 CloseHandle(pi.hThread);return pi.hProcess;
}
static int reg_child(const char *handle) {
 HANDLE mapping=(HANDLE)(uintptr_t)_strtoui64(handle,NULL,10);
 reg_shared *shared=MapViewOfFile(mapping,FILE_MAP_ALL_ACCESS,0,0,sizeof(*shared));
 wh3wr_registration *r=NULL;wh3w_controls controls={0};void *cap=NULL;wh3_tip tip;
 if(!shared)return 90;controls.context=shared;controls.phase=reg_barrier;
 shared->opened=wh3wr_open(shared->library,shared->mode,&controls,&r);
 if(shared->opened&&shared->mode==WH3WG_SHARED)shared->sdk_opened=sdk_prove((void *)original,shared->library);
 if(shared->opened&&shared->stop==WH3WG_BEGIN_DURABLE){
  f.b=shared->b;f.g=shared->g;empty_tip(&tip);
  (void)wh3wr_begin(r,&shared->b,&shared->g,&tip,&cap);
 }else if(shared->stop==1){SetEvent(shared->ready);if(WaitForSingleObject(shared->go,15000)!=WAIT_OBJECT_0)return 94;}
 (void)wh3wr_close(r);UnmapViewOfFile(shared);return 0;
}
static int reg_probe(unsigned mode) {
 HANDLE child=reg_spawn(mode,0);if(!finish(child,0))return -1;
 return rs->opened;
}
static HKEY fixture_key(void) {
 wchar_t upper[MAX_PATH],path[128];char hash[65];HKEY key=NULL;unsigned k;
 if(!LCMapStringEx(LOCALE_NAME_INVARIANT,LCMAP_UPPERCASE,reglib,-1,upper,MAX_PATH,NULL,NULL,0))return NULL;
 wh_sha256_hex(upper,wcslen(upper)*sizeof(wchar_t),hash);
 wcscpy_s(path,128,L"Software\\EXReaderC02Admission\\");
 {size_t offset=wcslen(path);for(k=0;k<65;k++)path[offset+k]=(wchar_t)hash[k];}
 if(RegOpenKeyExW(HKEY_CURRENT_USER,path,REG_OPTION_OPEN_LINK,KEY_ALL_ACCESS|KEY_WOW64_64KEY,&key)!=ERROR_SUCCESS)return NULL;
 return key;
}
static int reg_terminal(void *cap,wh3_tip *after) {
 wh3_tip before;size_t i;int ok;
 if(!wh3wr_journal(registration,&f.b,&f.g,NULL,&f.store)||!builder_start(&built,&f.b,&f.g))return 0;
 ok=builder_event(&built,1,NULL,NULL,NULL,NULL)&&builder_event(&built,2,HX40 "01234567",NULL,NULL,NULL)
  &&builder_event(&built,3,NULL,NULL,NULL,NULL)&&builder_event(&built,4,NULL,NULL,HX64,NULL)
  &&builder_event(&built,5,NULL,NULL,NULL,HX64)&&builder_event(&built,6,NULL,HX40 "01234567",NULL,NULL)
  &&builder_event(&built,7,NULL,NULL,NULL,NULL)&&builder_event(&built,8,NULL,NULL,NULL,NULL)
  &&builder_event(&built,9,NULL,NULL,NULL,NULL)&&builder_event(&built,10,NULL,NULL,NULL,NULL)
  &&builder_event(&built,11,NULL,NULL,NULL,NULL)&&builder_event(&built,12,NULL,NULL,NULL,NULL);
 if(!ok)return 0;empty_tip(&before);
 for(i=0;i<built.n;i++){if(wh3w_append(f.store,cap,&before,built.lines[i],after)!=WH3_TX_OK)return 0;before=*after;}
 return 1;
}
static void unknown_case(void) {
 if(!reg_fixture("missing-registry-never-initializes",0))return;
 expect(!reg_open(WH3WG_SHARED,NULL),"no caller-invented grant");
 expect(reg_probe(WH3WG_SHARED)==0&&!rs->sdk_opened,"fresh process refuses before SDK");
 expect(wh3wr_enroll(reglib,f.root,sdk_prove,(void *)original),"separate explicit enrollment");
 expect(reg_open(WH3WG_SHARED,NULL)&&wh3wr_check(registration),"trusted recorded grant");
 reg_close_all();
}
static void shared_case_registry(void) {
 wh3wr_registration *second=NULL;
 if(!reg_fixture("registered-shared-actual-sdk",1))return;
 expect(reg_open(WH3WG_SHARED,NULL),"first registered reader");
 expect(wh3wr_open(reglib,WH3WG_SHARED,NULL,&second),"second registered reader");
 expect(reg_probe(WH3WG_SHARED)==1&&rs->sdk_opened,"cross-process SDK reader shares custody");
 expect(reg_probe(WH3WG_OWNER)==0,"owner excluded while readers live");
 expect(wh3wr_close(second),"second reader close");reg_close_all();
 expect(reg_probe(WH3WG_OWNER)==1,"owner enters after last reader");
}
static void source_borrow_case(void) {
 char narrow[4*MAX_PATH],bytes[128];exr_library *lib=NULL;exr_book *books=NULL;size_t n=0;
 exr_source source={0};exr_error error={0};
 if(!reg_fixture("actual-sdk-source-outlives-parent",1))return;
 expect(reg_open(WH3WG_SHARED,NULL),"shared custody before SDK");
 expect(utf8_path(reglib,narrow)&&exr_library_open(narrow,&lib,&error)==EXR_OK,"SDK open under admission");
 if(!lib){reg_close_all();return;}
 expect(exr_library_books(lib,NULL,&books,&n,&error)==EXR_OK&&n==1,"SDK book identity");
 if(n!=1){exr_books_free(books,n);exr_library_close(lib);reg_close_all();return;}
 expect(exr_library_source(lib,books[0].id,&source,&error)==EXR_OK,"real retained SDK source");
 exr_books_free(books,n);exr_library_close(lib);
 if(source.release){
  expect(source.read_at(source.context,0,bytes,strlen(original))==strlen(original)&&!memcmp(bytes,original,strlen(original)),"source reads after parent SDK close");
  expect(reg_probe(WH3WG_OWNER)==0,"source borrow still excludes migrator");
  source.release(source.context);
 }
 reg_close_all();expect(reg_probe(WH3WG_OWNER)==1,"final borrower release permits owner");
}
static void owner_first_case(void) {
 HANDLE child;
 if(!reg_fixture("owner-first-blocks-real-sdk-open",1))return;
 child=reg_spawn(WH3WG_OWNER,1);expect(child!=NULL,"spawn owner");if(!child)return;
 expect(WaitForSingleObject(rrdy,15000)==WAIT_OBJECT_0&&rs->opened,"actual exclusive owner ready");
 expect(!reg_open(WH3WG_SHARED,NULL),"ordinary reader refused");
 SetEvent(rgo);expect(finish(child,0),"owner terminal");
 expect(reg_open(WH3WG_SHARED,NULL),"shared reader after owner exits");reg_close_all();
}
static void kill_case(void) {
 HANDLE child;
 if(!reg_fixture("killed-pending-owner-fresh-reader-refused",1))return;
 child=reg_spawn(WH3WG_OWNER,WH3WG_BEGIN_DURABLE);expect(child!=NULL,"spawn pending owner");if(!child)return;
 expect(WaitForSingleObject(rrdy,15000)==WAIT_OBJECT_0&&rs->reached==WH3WG_BEGIN_DURABLE,"observed durable pending barrier");
 expect(finish(child,1),"kill actual owner at barrier");
 expect(reg_probe(WH3WG_SHARED)==0&&!rs->sdk_opened,"new process cannot adopt pending generation");
}
static void bad_target(int hardlink) {
 wchar_t other[MAX_PATH];
 if(!reg_fixture(hardlink?"target-hardlink-refused":"target-replacement-refused",1))return;
 swprintf_s(other,MAX_PATH,L"%ls\\other.sqlite",f.parent);
 if(hardlink)expect(CreateHardLinkW(other,reglib,NULL)!=0,"actual extra target hardlink");
 else {expect(MoveFileW(reglib,other)!=0,"retain original target");expect(CopyFileW(other,reglib,TRUE)!=0,"actual different target FileID");}
 expect(!reg_open(WH3WG_SHARED,NULL),"trusted target identity refuses changed object");
}
static void bad_registry(int acl) {
 HKEY key;unsigned char bytes[1353];DWORD size=1352,type=0;PSECURITY_DESCRIPTOR sd=NULL;
 if(!reg_fixture(acl?"untrusted-registry-acl-refused":"resealed-registry-identity-refused",1))return;
 key=fixture_key();expect(key!=NULL,"open test registry record");if(!key)return;
 if(acl){
  expect(ConvertStringSecurityDescriptorToSecurityDescriptorW(L"D:P(A;;KA;;;WD)",SDDL_REVISION_1,&sd,NULL)!=0,"explicit weak ACL control");
  if(sd){expect(RegSetKeySecurity(key,DACL_SECURITY_INFORMATION|PROTECTED_DACL_SECURITY_INFORMATION,sd)==ERROR_SUCCESS,"apply weak ACL");LocalFree(sd);}
 }else{
  expect(RegQueryValueExW(key,L"Binding",NULL,&type,bytes,&size)==ERROR_SUCCESS&&size==1352,"read trusted record");
  bytes[136]^=1;wh_sha256_hex(bytes,1288,(char *)bytes+1288);
  expect(RegSetValueExW(key,L"Binding",0,REG_BINARY,bytes,1352)==ERROR_SUCCESS,"reseal wrong native root identity");
 }
 RegCloseKey(key);expect(!reg_open(WH3WG_SHARED,NULL),"bad independent binding rejected");
}
static void missing_gate(void) {
 wchar_t path[MAX_PATH];
 if(!reg_fixture("missing-gate-not-recreated",1))return;
 swprintf_s(path,MAX_PATH,L"%ls\\admission.bin",f.root);expect(DeleteFileW(path)!=0,"remove admission fixture");
 expect(!reg_open(WH3WG_SHARED,NULL),"missing registered gate refused");
 expect(GetFileAttributesW(path)==INVALID_FILE_ATTRIBUTES&&GetLastError()==ERROR_FILE_NOT_FOUND,"no automatic replacement");
}
static void publication_case(int fail_clean) {
 wh3w_controls controls={0};wh3_tip tip,empty;void *cap=NULL;wchar_t stage[MAX_PATH],backup[MAX_PATH];
 if(!reg_fixture(fail_clean?"unknown-clean-requires-explicit-reconciliation":"actual-publication-advances-trusted-target",1))return;
 if(fail_clean){controls.fault=WH3W_FLUSH_FAIL;controls.fault_phase=WH3WG_CLEAN_WRITTEN;}
 expect(reg_open(WH3WG_OWNER,&controls),"owner from trusted registration");if(!registration)return;
 empty_tip(&empty);expect(wh3wr_begin(registration,&f.b,&f.g,&empty,&cap),"durable pending precedes staging");if(!cap){reg_close_all();return;}
 swprintf_s(stage,MAX_PATH,L"%ls\\stage.sqlite",f.parent);swprintf_s(backup,MAX_PATH,L"%ls\\retained.sqlite",f.parent);
 expect(sdk_seed(stage,published),"actual staged SDK database");
 expect(wh3wr_prepare_publish(registration),"release target pin only under live pending");
 {
  HANDLE deletion;DWORD deletion_error,parent_error,save_error,publish_error;int saved;
  deletion=CreateFileW(reglib,DELETE,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,NULL,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,NULL);
  deletion_error=deletion==INVALID_HANDLE_VALUE?GetLastError():0;if(deletion!=INVALID_HANDLE_VALUE)CloseHandle(deletion);
  deletion=CreateFileW(f.parent,FILE_ADD_FILE|FILE_READ_ATTRIBUTES,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_EXISTING,FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,NULL);
  parent_error=deletion==INVALID_HANDLE_VALUE?GetLastError():0;if(deletion!=INVALID_HANDLE_VALUE)CloseHandle(deletion);
  saved=MoveFileW(reglib,backup)!=0;save_error=saved?0:GetLastError();
  printf("OBS publication delete_open_error=%lu parent_write_error=%lu absolute_rename=%d error=%lu\n",
    (unsigned long)deletion_error,(unsigned long)parent_error,saved,(unsigned long)save_error);
  expect(deletion_error==0&&parent_error==ERROR_SHARING_VIOLATION&&!saved&&save_error==ERROR_SHARING_VIOLATION,
    "strong directory custody remains unchanged");
  {
   wh3w_identity stage_id,bad_id;wh3_tx_status status;
   expect(capture_id(stage,0,&stage_id),"independently captured staged FileID");bad_id=stage_id;bad_id.file.Identifier[0]^=1;
   expect(wh3wr_publish(registration,L"stage.sqlite",&bad_id,L"retained.sqlite")==WH3_TX_MISMATCH,
     "wrong stage identity makes no publication");
   expect(wh3wr_publish(registration,L"..\\stage.sqlite",&stage_id,L"retained.sqlite")==WH3_TX_MISMATCH,
     "publication refuses path traversal");
   status=wh3wr_publish(registration,L"stage.sqlite",&stage_id,L"retained.sqlite");
   publish_error=status==WH3_TX_OK?0:GetLastError();
   printf("OBS handle_publication status=%d error=%lu\n",(int)status,(unsigned long)publish_error);
   expect(status==WH3_TX_OK,"actual target namespace publication");
   expect(sdk_prove((void *)original,backup),"old actual SDK library retained");
   deletion=CreateFileW(f.parent,GENERIC_WRITE|DELETE,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,NULL,
     OPEN_EXISTING,FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,NULL);
   expect(deletion==INVALID_HANDLE_VALUE&&GetLastError()==ERROR_SHARING_VIOLATION,"publication never relaxes parent pins");
   if(deletion!=INVALID_HANDLE_VALUE)CloseHandle(deletion);
  }
 }
 expect(reg_terminal(cap,&tip),"complete acknowledged native journal");
 if(fail_clean){
  expect(!wh3wr_finish(registration,f.store,&tip,reg_prove,(void *)published),"unknown clean yields no registry advance");
  reg_close_all();expect(reg_probe(WH3WG_SHARED)==0&&!rs->sdk_opened,"fresh reader rejects visible unacknowledged CLEAN");
  expect(reg_open(WH3WG_RECOVER,NULL),"explicit recovery uses old trusted grant");
  expect(wh3wr_journal(registration,&f.b,&f.g,NULL,&f.store),"recover exact complete original journal");
 }
 expect(wh3wr_finish(registration,f.store,&tip,reg_prove,(void *)published),"actual SDK publication proof advances registry");
 expect(!wh3wr_close(registration),"journal retains registration until close");
 reg_close_all();expect(reg_open(WH3WG_SHARED,NULL),"fresh reader accepts new exact grant and target");
 expect(sdk_prove((void *)published,reglib),"real SDK observes independently verified published content");reg_close_all();
}
static void bad_initial(void) {
 if(!reg_fixture("failed-bootstrap-proof-never-registers",0))return;
 expect(!wh3wr_enroll(reglib,f.root,initial_refuse,NULL),"initial proof refusal");
 expect(!reg_open(WH3WG_SHARED,NULL),"no trusted grant after failed proof");
 expect(!wh3wr_enroll(reglib,f.root,sdk_prove,(void *)original),"no automatic bootstrap replay");
}
static void short_begin_case(void) {
 wh3w_controls controls={0};wh3_tip empty;void *cap=NULL;
 if(!reg_fixture("short-pending-write-grants-no-capability",1))return;
 controls.fault=WH3W_SHORT_WRITE;controls.fault_phase=WH3WG_BEGIN_WRITTEN;
 expect(reg_open(WH3WG_OWNER,&controls),"exclusive owner");empty_tip(&empty);
 expect(!wh3wr_begin(registration,&f.b,&f.g,&empty,&cap)&&!cap,"partial native pending never authorizes mutation");
 reg_close_all();expect(reg_probe(WH3WG_SHARED)==0&&!rs->sdk_opened,"torn gate refuses fresh SDK open");
}
int main(int argc,char **argv) {
 if(argc==3&&!strcmp(argv[1],"--registry-child"))return reg_child(argv[2]);
 if(argc==3&&!strcmp(argv[1],"--probe-owner")){
  wchar_t path[MAX_PATH];wh3wr_registration *r=NULL;int ok;
  if(!MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,argv[2],-1,path,MAX_PATH))return 3;
  ok=wh3wr_open(path,WH3WG_OWNER,NULL,&r);(void)wh3wr_close(r);return ok?0:10;
 }
 if(argc==2&&(!strcmp(argv[1],"--prepare-host")||!strcmp(argv[1],"--prepare-unregistered")||!strcmp(argv[1],"--prepare-pending"))){
  char path[4*MAX_PATH];wh3_tip empty;void *cap=NULL;
  if(!reg_fixture("actual-product-startup",strcmp(argv[1],"--prepare-unregistered")!=0))return 1;
  if(!strcmp(argv[1],"--prepare-pending")){
   empty_tip(&empty);if(!reg_open(WH3WG_OWNER,NULL)||!wh3wr_begin(registration,&f.b,&f.g,&empty,&cap))return 1;
   reg_close_all();
  }
  if(!utf8_path(reglib,path))return 1;printf("HOST_LIBRARY %s\n",path);
  if(!utf8_path(f.root,path))return 1;printf("HOST_GATE %s\n",path);return failures?1:0;
 }
 unknown_case();shared_case_registry();source_borrow_case();owner_first_case();kill_case();
 bad_target(0);bad_target(1);bad_registry(0);bad_registry(1);missing_gate();
 publication_case(0);publication_case(1);bad_initial();short_begin_case();
 fixture_close();if(rs)UnmapViewOfFile(rs);if(rm)CloseHandle(rm);if(rrdy)CloseHandle(rrdy);if(rgo)CloseHandle(rgo);
 printf("{\"source\":\"%s\",\"cases\":%u,\"checks\":%u,\"failed\":%u,\"passed\":%s,\"actual_sdk\":true,\"trusted_registry\":true,\"production_coordinator\":false,\"full_c02_acceptance\":false}\n",
   CANDIDATE_SOURCE_SHA,cases,checks,failures,failures?"false":"true");
 return failures?1:0;
}
