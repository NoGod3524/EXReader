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
 wchar_t library[MAX_PATH],root[MAX_PATH];wh_binding b;wh_gates g;
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
 wcscpy_s(rs->library,MAX_PATH,reglib);wcscpy_s(rs->root,MAX_PATH,f.root);rs->b=f.b;rs->g=f.g;
 rs->ready=rrdy;rs->go=rgo;rs->mode=mode;rs->stop=stop;
 if(!GetModuleFileNameW(NULL,exe,MAX_PATH))return NULL;
 swprintf_s(command,2*MAX_PATH,L"\"%ls\" --registry-child %llu",exe,(unsigned long long)(uintptr_t)rm);
 si.cb=sizeof(si);
 if(!CreateProcessW(exe,command,NULL,NULL,TRUE,CREATE_NO_WINDOW,NULL,NULL,&si,&pi))return NULL;
 CloseHandle(pi.hThread);return pi.hProcess;
}
static int coordinator_child(reg_shared *shared);
static int member_child(reg_shared *shared);
static int reg_child(const char *handle) {
 HANDLE mapping=(HANDLE)(uintptr_t)_strtoui64(handle,NULL,10);
 reg_shared *shared=MapViewOfFile(mapping,FILE_MAP_ALL_ACCESS,0,0,sizeof(*shared));
 wh3wr_registration *r=NULL;wh3w_controls controls={0};void *cap=NULL;wh3_tip tip;
 if(!shared)return 90;
 if(shared->stop==600)return coordinator_child(shared);
 if(shared->stop>=WH3WR_MEMBER_PROVED)return member_child(shared);
 if(shared->stop>=WH3WR_EPOCH_INTENT){
  controls.context=shared;controls.phase=reg_barrier;
  return wh3wr_next_epoch(shared->library,sdk_prove,(void *)original,&controls)?0:96;
 }
 controls.context=shared;controls.phase=reg_barrier;
 if(shared->stop>=WH3WR_ENROLL_RESERVED){
  int ok=wh3wr_enroll_controlled(shared->library,shared->root,sdk_prove,(void *)original,&controls);
  UnmapViewOfFile(shared);return ok?0:95;
 }
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
 wchar_t upper[MAX_PATH],canonical[MAX_PATH],parent[MAX_PATH],path[128];char hash[65];
 unsigned char bytes[32+2*MAX_PATH];wh3w_identity id;HKEY key=NULL;size_t n;unsigned k;
 if(!GetLongPathNameW(reglib,canonical,MAX_PATH))return NULL;
 n=(size_t)(wcsrchr(reglib,L'\\')-reglib);if(n==2)n=3;
 memcpy(parent,reglib,n*sizeof(wchar_t));parent[n]=0;
 if(!capture_id(parent,1,&id)||!LCMapStringEx(LOCALE_NAME_INVARIANT,LCMAP_UPPERCASE,
    wcsrchr(canonical,L'\\')+1,-1,upper,MAX_PATH,NULL,NULL,0))return NULL;
 memcpy(bytes,"WH3LOC01",8);
 for(k=0;k<8;k++)bytes[8+k]=(unsigned char)(id.volume>>(8*k));
 memcpy(bytes+16,&id.file,16);n=wcslen(upper)*sizeof(wchar_t);memcpy(bytes+32,upper,n);
 wh_sha256_hex(bytes,32+n,hash);
 wcscpy_s(path,128,L"Software\\EXReaderC02Admission\\");
 {size_t offset=wcslen(path);for(k=0;k<65;k++)path[offset+k]=(wchar_t)hash[k];}
 if(RegOpenKeyExW(HKEY_CURRENT_USER,path,REG_OPTION_OPEN_LINK,KEY_ALL_ACCESS|KEY_WOW64_64KEY,&key)!=ERROR_SUCCESS)return NULL;
 return key;
}
static int reg_build_terminal(void) {
 int ok;if(!builder_start(&built,&f.b,&f.g))return 0;
 ok=builder_event(&built,1,NULL,NULL,NULL,NULL)&&builder_event(&built,2,HX40 "01234567",NULL,NULL,NULL)
  &&builder_event(&built,3,NULL,NULL,NULL,NULL)&&builder_event(&built,4,NULL,NULL,HX64,NULL)
  &&builder_event(&built,5,NULL,NULL,NULL,HX64)&&builder_event(&built,6,NULL,HX40 "01234567",NULL,NULL)
  &&builder_event(&built,7,NULL,NULL,NULL,NULL)&&builder_event(&built,8,NULL,NULL,NULL,NULL)
  &&builder_event(&built,9,NULL,NULL,NULL,NULL)&&builder_event(&built,10,NULL,NULL,NULL,NULL)
  &&builder_event(&built,11,NULL,NULL,NULL,NULL)&&builder_event(&built,12,NULL,NULL,NULL,NULL);
 return ok;
}
static int reg_prefix(void *cap,size_t count,wh3_tip *after) {
 wh3_tip before;size_t i;
 if(!wh3wr_journal(registration,&f.b,&f.g,NULL,&f.store)||!reg_build_terminal()||count>built.n)return 0;
 empty_tip(&before);
 for(i=0;i<count;i++){if(wh3w_append(f.store,cap,&before,built.lines[i],after)!=WH3_TX_OK)return 0;before=*after;}
 return 1;
}
static int reg_terminal(void *cap,wh3_tip *after) {return reg_prefix(cap,13,after);}

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
 expect(!wh3wr_recover_enrollment(reglib,initial_refuse,NULL),"recovery repeats initial proof");
 expect(!reg_open(WH3WG_SHARED,NULL),"failed repeated proof never admits");
 expect(wh3wr_recover_enrollment(reglib,sdk_prove,(void *)original),"explicit enrollment recovery with actual SDK proof");
 expect(reg_open(WH3WG_SHARED,NULL),"recovered initial grant admits");reg_close_all();
}
static void short_begin_case(void) {
 wh3w_controls controls={0};wh3_tip empty;void *cap=NULL;
 if(!reg_fixture("short-pending-write-grants-no-capability",1))return;
 controls.fault=WH3W_SHORT_WRITE;controls.fault_phase=WH3WG_BEGIN_WRITTEN;
 expect(reg_open(WH3WG_OWNER,&controls),"exclusive owner");empty_tip(&empty);
 expect(!wh3wr_begin(registration,&f.b,&f.g,&empty,&cap)&&!cap,"partial native pending never authorizes mutation");
 reg_close_all();expect(reg_probe(WH3WG_SHARED)==0&&!rs->sdk_opened,"torn gate refuses fresh SDK open");
}
static unsigned initial_proofs;
static int counted_initial(void *context,const wchar_t *path) {
 initial_proofs++;return sdk_prove(context,path);
}
static void enrollment_kill(unsigned at) {
 HANDLE child;char name[80];wchar_t alternate[MAX_PATH];int bound=at==WH3WR_ENROLL_BOUND;
 snprintf(name,sizeof(name),"enrollment-process-kill-%u",at);
 if(!reg_fixture(name,0))return;
 child=reg_spawn(WH3WG_ENROLL,at);expect(child!=NULL,"spawn real enrollment owner");if(!child)return;
 expect(WaitForSingleObject(rrdy,15000)==WAIT_OBJECT_0&&rs->reached==(int)at,"exact enrollment persistence barrier");
 if(at==WH3WR_ENROLL_RESERVED){
  swprintf_s(alternate,MAX_PATH,L"%ls\\other-enrollment",f.parent);initial_proofs=0;
  expect(!wh3wr_enroll_created(reglib,alternate,0,counted_initial,(void *)original),"same target cannot enroll through another root concurrently");
  expect(initial_proofs==0,"competing enrollment never reaches SDK proof");
 }
 expect(finish(child,1),"terminate enrollment process at barrier");
 expect(reg_probe(WH3WG_SHARED)==bound,"fresh process accepts only independently committed Binding");
 if(!bound){
  initial_proofs=0;
  if(at==WH3WR_ENROLL_RESERVED){
   expect(!wh3wr_recover_enrollment(reglib,counted_initial,(void *)original)&&initial_proofs==0,"empty reservation never invents an intent");
   expect(wh3wr_enroll(reglib,f.root,counted_initial,(void *)original),"explicit retry verifies existing empty native set");
  }else expect(wh3wr_recover_enrollment(reglib,counted_initial,(void *)original),"recover exact enrollment intent");
  expect(initial_proofs==1,"recovery actually opens and verifies SDK content");
 }
 expect(reg_probe(WH3WG_SHARED)==1&&rs->sdk_opened,"completed enrollment opens real SDK in fresh process");
}
static void enrollment_policy(unsigned marker,int directory) {
 const wchar_t *suffixes[]={L".migration-recovery",L".migration-pending.json",L".migrate-lock"};
 wchar_t path[MAX_PATH];char name[80];LARGE_INTEGER size;HANDLE h;
 snprintf(name,sizeof(name),"enrollment-retains-legacy-policy-%u-%d",marker,directory);
 if(!reg_fixture(name,0))return;
 swprintf_s(path,MAX_PATH,L"%ls%ls",reglib,suffixes[marker]);
 if(directory)expect(CreateDirectoryW(path,NULL)!=0,"real legacy policy directory");
 else {h=CreateFileW(path,GENERIC_WRITE,0,NULL,CREATE_NEW,0,NULL);
  expect(h!=INVALID_HANDLE_VALUE,"real legacy policy file");if(h!=INVALID_HANDLE_VALUE)CloseHandle(h);}
 initial_proofs=0;
 expect(!wh3wr_enroll(reglib,f.root,counted_initial,(void *)original)&&initial_proofs==0,"policy refuses before SDK proof");
 expect(GetFileAttributesW(path)!=INVALID_FILE_ATTRIBUTES,"policy object retained");
 swprintf_s(path,MAX_PATH,L"%ls\\admission.bin",f.root);
 h=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_EXISTING,0,NULL);
 expect(h!=INVALID_HANDLE_VALUE&&GetFileSizeEx(h,&size)&&size.QuadPart==0,"policy never initializes gate");
 if(h!=INVALID_HANDLE_VALUE)CloseHandle(h);
}
static void enrollment_bad(unsigned kind) {
 wchar_t path[MAX_PATH],other[MAX_PATH];char name[80];unsigned char *bytes=NULL;DWORD n=0;
 snprintf(name,sizeof(name),"enrollment-recovery-refuses-mutation-%u",kind);
 if(!reg_fixture(name,0))return;
 expect(!wh3wr_enroll(reglib,f.root,initial_refuse,NULL),"retain incomplete enrollment");
 if(kind==0){
  swprintf_s(path,MAX_PATH,L"%ls\\admission.bin",f.root);
  expect(read_bytes(path,&bytes,&n)&&n==344,"read exact initial record");
  if(bytes&&n){expect(replace_bytes(path,bytes,n-1),"plant torn initial record");free(bytes);}
 }else if(kind==1){
  swprintf_s(other,MAX_PATH,L"%ls\\original.sqlite",f.parent);
  expect(MoveFileW(reglib,other)&&CopyFileW(other,reglib,TRUE),"replace actual target FileID");
 }else if(kind==2){
  HKEY key=fixture_key();unsigned char record[1353];DWORD size=1352,type=0;
  expect(key!=NULL,"open initial-intent registry control");
  if(key){
   expect(RegQueryValueExW(key,L"Enrollment",NULL,&type,record,&size)==ERROR_SUCCESS&&size==1352,"read independent enrollment intent");
   record[64]=record[64]=='a'?'b':'a';wh_sha256_hex(record,1288,(char *)record+1288);
   expect(RegSetValueExW(key,L"Enrollment",0,REG_BINARY,record,1352)==ERROR_SUCCESS,"reseal wrong expected initial grant");RegCloseKey(key);
  }
 }else{
  swprintf_s(path,MAX_PATH,L"%ls\\journal.bin",f.root);expect(DeleteFileW(path)!=0,"remove enrolled journal object");
 }
 initial_proofs=0;
 expect(!wh3wr_recover_enrollment(reglib,counted_initial,(void *)original)&&initial_proofs==0,"mutated enrollment refuses before SDK");
 expect(reg_probe(WH3WG_SHARED)==0&&!rs->sdk_opened,"no admission from rejected recovery");
 if(kind==3)expect(GetFileAttributesW(path)==INVALID_FILE_ATTRIBUTES&&GetLastError()==ERROR_FILE_NOT_FOUND,"missing object never recreated");
}
static void drive_alias_case(void) {
 wchar_t drive[3]={0,L':',0},alias[MAX_PATH],alternate[MAX_PATH],target[MAX_PATH+8],short_path[MAX_PATH];
 wh3w_identity a={0},b={0};DWORD used=GetLogicalDrives();int letter;wh3wr_registration *other=NULL;
 if(!reg_fixture("drive-alias-cannot-enroll-a-second-domain",1))return;
 expect(used!=0,"native drive inventory");if(!used)return;
 for(letter=25;letter>=15;letter--)if(!(used&(1u<<letter)))break;
 expect(letter>=15,"unused private drive letter");if(letter<15)return;drive[0]=(wchar_t)(L'A'+letter);
 swprintf_s(target,MAX_PATH+8,L"\\??\\%ls",f.parent);
 expect(DefineDosDeviceW(DDD_RAW_TARGET_PATH|DDD_NO_BROADCAST_SYSTEM,drive,target)!=0,"actual DOS drive alias");
 {wchar_t root[4]={drive[0],L':',L'\\',0},fs[32];
  expect(GetDriveTypeW(root)==DRIVE_FIXED&&GetVolumeInformationW(root,NULL,0,NULL,NULL,NULL,fs,32)&&!_wcsicmp(fs,L"NTFS"),
    "drive alias meets the actual local-NTFS routing prerequisites");}
 swprintf_s(alias,MAX_PATH,L"%ls\\library.sqlite",drive);
 expect(capture_id(reglib,0,&a)&&capture_id(alias,0,&b)&&a.volume==b.volume&&!memcmp(&a.file,&b.file,16),
    "alias resolves to exactly the same native target");
 swprintf_s(alternate,MAX_PATH,L"%ls\\other-domain",f.parent);initial_proofs=0;
 expect(!wh3wr_enroll_created(alias,alternate,0,counted_initial,(void *)original),
    "another path spelling cannot create independent admission");
 expect(initial_proofs==0,"alias duplicate refuses before SDK proof");
 expect(reg_open(WH3WG_OWNER,NULL),"original domain still owns target");
 expect(!wh3wr_open(alias,WH3WG_SHARED,NULL,&other),"alias cannot bypass exclusive original owner");
 (void)wh3wr_close(other);reg_close_all();
 short_path[0]=0;
 {DWORD short_length=GetShortPathNameW(reglib,short_path,MAX_PATH);
 printf("OBS short_alias_available=%d native_error=%lu\n",short_length&&short_length<MAX_PATH&&_wcsicmp(short_path,reglib)!=0,(unsigned long)(short_length?0:GetLastError()));}
 if(short_path[0]&&_wcsicmp(short_path,reglib)){
  swprintf_s(alternate,MAX_PATH,L"%ls\\short-domain",f.parent);initial_proofs=0;
  expect(capture_id(short_path,0,&b)&&a.volume==b.volume&&!memcmp(&a.file,&b.file,16),"actual short-name alias");
  expect(!wh3wr_enroll_created(short_path,alternate,0,counted_initial,(void *)original)&&initial_proofs==0,
    "short-name alias cannot enroll a second gate");
 }
 expect(DefineDosDeviceW(DDD_RAW_TARGET_PATH|DDD_REMOVE_DEFINITION|DDD_EXACT_MATCH_ON_REMOVE|
    DDD_NO_BROADCAST_SYSTEM,drive,target)!=0,"remove only this fixture drive mapping");
 expect(reg_open(WH3WG_SHARED,NULL),"original registered path remains admitted");reg_close_all();
}
/* This provider exercises the real frozen coordinator, native journal, actual
   registry and SDK. The one-book transformer is fixture orchestration only. */
typedef struct {
 void *cap;wh3_tip tip;wh3w_identity before,staged;char lease[49],stage_id[49];
 wh_record row;char original_bytes[128];size_t original_size;
 wchar_t stage[MAX_PATH];unsigned published,checks_after_publish,proofs,released;
 size_t terminal_count;reg_shared *barrier;unsigned round;
} run_fixture;
static void run_identity(const wh3w_identity *id,char out[49]) {
 static const char hex[]="0123456789abcdef";unsigned char bytes[24];unsigned i;
 for(i=0;i<8;i++)bytes[i]=(unsigned char)(id->volume>>(8*i));
 memcpy(bytes+8,&id->file,16);
 for(i=0;i<24;i++){out[2*i]=hex[bytes[i]>>4];out[2*i+1]=hex[bytes[i]&15];}out[48]=0;
}
static int run_metadata(void) {
 char data[64];size_t n=0;
 return wh3wr_transaction_read(registration,WH3WR_INPUT,data,sizeof(data),&n)&&
    n==26&&!memcmp(data,"fixture-coordinator-input",26)&&
    wh3wr_transaction_read(registration,WH3WR_PREPARED,data,sizeof(data),&n)&&
    n==29&&!memcmp(data,"fixture-coordinator-prepared",29);
}
static int run_read(const wchar_t *path,wh_record *row,char bytes[128],size_t *length) {
 char narrow[4*MAX_PATH];exr_library *lib=NULL;exr_error error={0};exr_book *books=NULL;
 exr_source source={0};size_t n=0;wh3w_identity id;int ok=0;
 memset(row,0,sizeof(*row));*length=0;
 if(!capture_id(path,0,&id)||!utf8_path(path,narrow)||exr_library_open(narrow,&lib,&error)!=EXR_OK)return 0;
 if(exr_library_books(lib,NULL,&books,&n,&error)!=EXR_OK||n!=1||
    exr_library_source(lib,books[0].id,&source,&error)!=EXR_OK||source.size>=128||
    source.read_at(source.context,0,bytes,(size_t)source.size)!=source.size)goto done;
 *length=(size_t)source.size;bytes[*length]=0;
 run_identity(&id,row->id);strcpy_s(row->path,sizeof(row->path),"books/one/original.txt");
 row->size=source.size;wh_sha256_hex(bytes,*length,row->sha);ok=1;
done:
 if(source.release)source.release(source.context);exr_books_free(books,n);exr_library_close(lib);return ok;
}
static wh_step run_check(void *context,void *cap) {
 run_fixture *r=context;
 if(cap!=r->cap||!wh3wr_check(registration))return WH_STEP_UNCERTAIN;
 if(r->published)r->checks_after_publish++;return WH_STEP_OK;
}
static wh_step run_acquire(void *context,const wh_binding *b,const wh_gates *g,void **cap,char id[49]) {
 run_fixture *r=context;wh3w_identity root;
 *cap=NULL;
 if(!reg_open(WH3WG_OWNER,NULL))return WH_STEP_FAILED;
 empty_tip(&r->tip);
 if(!wh3wr_transaction_write(registration,WH3WR_INPUT,"fixture-coordinator-input",26))return WH_STEP_UNCERTAIN;
 if(!wh3wr_begin(registration,b,g,&r->tip,&r->cap))return WH_STEP_UNCERTAIN;
 *cap=r->cap;
 if(!wh3wr_journal(registration,b,g,NULL,&f.store)||!capture_id(f.root,1,&root)||
    !capture_id(reglib,0,&r->before))return WH_STEP_UNCERTAIN;
 run_identity(&root,r->lease);memcpy(id,r->lease,49);return WH_STEP_OK;
}
static wh_step run_reacquire(void *context,const wh_binding *b,const wh_gates *g,
 const char *prior,void **cap,char id[49]) {
 run_fixture *r=context;wh3_tip actual;size_t count=0;char (*lines)[EXR_WH_LINE_MAX];
 wchar_t retained[MAX_PATH];wh3w_identity original_id;char stage_id[49];
 *cap=NULL;if(strcmp(prior,r->lease)||!reg_open(WH3WG_RECOVER,NULL))return WH_STEP_FAILED;
 if(!run_metadata())return WH_STEP_UNCERTAIN;
 lines=calloc(EXR_WH_MAX_JOURNAL,sizeof(*lines));if(!lines)return WH_STEP_UNCERTAIN;
 if(!wh3wr_journal(registration,b,g,NULL,&f.store)||
    !wh3w_read(f.store,lines,EXR_WH_MAX_JOURNAL,&count,&actual)||
    actual.line_count!=r->tip.line_count||memcmp(actual.manifest_sha,r->tip.manifest_sha,65)||
    memcmp(actual.last_line_sha,r->tip.last_line_sha,65)){free(lines);return WH_STEP_UNCERTAIN;}
 free(lines);
 if(!wh3wr_resume(registration,b,g,f.store,&r->tip,&r->cap))return WH_STEP_UNCERTAIN;
 *cap=r->cap;memcpy(id,r->lease,49);
 swprintf_s(retained,MAX_PATH,L"%ls\\coordinator-retained.sqlite",f.parent);
 if(!capture_id(retained,0,&original_id)||memcmp(&original_id,&r->before,sizeof(original_id))||
    !run_read(retained,&r->row,r->original_bytes,&r->original_size)||
    !capture_id(reglib,0,&r->staged))return WH_STEP_UNCERTAIN;
 run_identity(&r->staged,stage_id);
 if(strcmp(stage_id,r->stage_id))return WH_STEP_UNCERTAIN;
 r->published=1;return WH_STEP_OK;
}
static wh_step run_snapshot(void *context,void *cap,wh_record *rows,size_t max,size_t *n) {
 run_fixture *r=context;*n=0;
 if(run_check(context,cap)!=WH_STEP_OK||!max||
    !run_read(reglib,&r->row,r->original_bytes,&r->original_size))return WH_STEP_UNCERTAIN;
 rows[0]=r->row;*n=1;return WH_STEP_OK;
}
static wh_step run_import(void *context,void *cap,const wh_record *rows,size_t n,char id[49]) {
 run_fixture *r=context;
 if(run_check(context,cap)!=WH_STEP_OK||n!=1||memcmp(rows,&r->row,sizeof(*rows)))return WH_STEP_UNCERTAIN;
 swprintf_s(r->stage,MAX_PATH,L"%ls\\%ls",f.parent,r->round?L"coordinator2-stage.sqlite":L"coordinator-stage.sqlite");
 if(!sdk_seed(r->stage,r->original_bytes)||!capture_id(r->stage,0,&r->staged))return WH_STEP_UNCERTAIN;
 run_identity(&r->staged,r->stage_id);memcpy(id,r->stage_id,49);return WH_STEP_OK;
}
static int run_content(run_fixture *r,const wchar_t *path,const char *expected) {
 wh_record row;char bytes[128],content[65];size_t size=0;
 return run_read(path,&row,bytes,&size)&&wh_content_digest(&row,1,content)&&
   !strcmp(content,expected)&&size==r->original_size&&!memcmp(bytes,r->original_bytes,size);
}
static wh_step run_verify(void *context,void *cap,const char *id,const wh_record *rows,size_t n) {
 run_fixture *r=context;char content[65];wh3w_identity actual;
 if(run_check(context,cap)!=WH_STEP_OK||strcmp(id,r->stage_id)||n!=1||
    !wh_content_digest(rows,n,content)||!capture_id(r->stage,0,&actual)||
    memcmp(&actual,&r->staged,sizeof(actual))||!run_content(r,r->stage,content)||
    !wh3wr_transaction_write(registration,WH3WR_PREPARED,"fixture-coordinator-prepared",29))return WH_STEP_UNCERTAIN;
 return WH_STEP_OK;
}
static wh_step run_publish(void *context,void *cap,const char *id,wh_pub *pub) {
 run_fixture *r=context;*pub=WH_PUB_UNKNOWN;
 if(run_check(context,cap)!=WH_STEP_OK||strcmp(id,r->stage_id)||
    wh3wr_publish(registration,r->round?L"coordinator2-stage.sqlite":L"coordinator-stage.sqlite",&r->staged,
      r->round?L"coordinator2-retained.sqlite":L"coordinator-retained.sqlite")!=WH3_TX_OK)return WH_STEP_UNCERTAIN;
 r->published=1;
 if(r->barrier)reg_barrier(r->barrier,600);
 *pub=WH_PUB_YES;return WH_STEP_OK;
}
static wh_step run_inspect(void *context,void *cap,const char *id,const char *content,wh_pub *pub) {
 run_fixture *r=context;wh3w_identity actual;*pub=WH_PUB_UNKNOWN;
 if(run_check(context,cap)!=WH_STEP_OK||strcmp(id,r->stage_id)||
    !capture_id(reglib,0,&actual)||memcmp(&actual,&r->staged,sizeof(actual))||
    !run_content(r,reglib,content))return WH_STEP_UNCERTAIN;
 *pub=WH_PUB_YES;return WH_STEP_OK;
}
static wh_step run_discard(void *context,void *cap,const char *id) {
 (void)context;(void)cap;(void)id;return WH_STEP_UNCERTAIN;
}
static wh3_tx_status run_append(void *context,void *cap,const wh3_tip *expected,
 const char *line,wh3_tip *actual) {
 run_fixture *r=context;wh3_tx_status status=wh3w_append(f.store,cap,expected,line,actual);
 if(status==WH3_TX_OK)r->tip=*actual;return status;
}
static int run_terminal_proof(void *context,const wh3_tip *tip) {
 run_fixture *r=context;char content[65];wh_pub publication=WH_PUB_UNKNOWN;r->proofs++;
 return tip->line_count==(r->terminal_count?r->terminal_count:13)&&tip->line_count==r->tip.line_count&&
   !memcmp(tip->last_line_sha,r->tip.last_line_sha,65)&&wh_content_digest(&r->row,1,content)&&
   run_inspect(r,r->cap,r->stage_id,content,&publication)==WH_STEP_OK&&publication==WH_PUB_YES;
}
static wh_step run_release(void *context,void *cap) {
 run_fixture *r=context;
 if(run_check(context,cap)!=WH_STEP_OK||
    !wh3wr_finish(registration,f.store,&r->tip,run_terminal_proof,r))return WH_STEP_UNCERTAIN;
 wh3w_close(f.store);f.store=NULL;
 if(!wh3wr_close(registration))return WH_STEP_UNCERTAIN;
 registration=NULL;r->cap=NULL;r->released=1;return WH_STEP_OK;
}
static void coordinator_case(void) {
 run_fixture r={0};wh_provider p={0};wh3_backend backend;wh3_session *session;
 wh_report report;wh_status status;wh3w_identity actual;
 if(!reg_fixture("real-coordinator-publishes-before-commit-and-release",1))return;
 p.abi=EXR_WH_ABI;p.identity_sha=f.b.provider;p.context=&r;p.acquire=run_acquire;p.reacquire=run_reacquire;
 p.check=run_check;p.snapshot=run_snapshot;p.import_rows=run_import;p.verify=run_verify;
 p.publish=run_publish;p.inspect=run_inspect;p.discard=run_discard;p.release=run_release;
 backend.abi=EXR_WH3_ABI;backend.context=&r;backend.append=run_append;
 session=wh3_create(&f.b,&f.g,&p,&backend);expect(session!=NULL,"real ABI3 coordinator");if(!session)return;
 status=wh3_run(session,&report);
 printf("OBS real_coordinator status=%d detail=%s seq=%u after_publish_checks=%u proof=%u released=%u\n",
   (int)status,report.detail,report.seq,r.checks_after_publish,r.proofs,r.released);
 expect(status==WH_COMPLETED&&!report.live_lease&&!report.poisoned,"actual coordinator reaches durable commit and release");
 expect(r.tip.line_count==13&&r.checks_after_publish>=4&&r.proofs==1&&r.released,"post-publication checks and independent terminal proof execute");
 expect(capture_id(reglib,0,&actual)&&!memcmp(&actual,&r.staged,sizeof(actual))&&
    memcmp(&actual,&r.before,sizeof(actual)),"new actual target replaces original identity");
 expect(wh3_dispose(session),"completed real coordinator disposes");
 expect(reg_probe(WH3WG_SHARED)==1&&rs->sdk_opened,"fresh process reads verified original from published target");
 expect(reg_open(WH3WG_SHARED,NULL)&&wh3wr_check(registration),"new trusted target matches ordinary admission");reg_close_all();
}
static void recover_missing_case(void) {
 wh3_tip empty;void *cap=NULL;wchar_t retained[MAX_PATH];
 if(!reg_fixture("recovery-checks-observed-missing-target",1))return;
 empty_tip(&empty);expect(reg_open(WH3WG_OWNER,NULL)&&wh3wr_begin(registration,&f.b,&f.g,&empty,&cap),"durable pending before missing-target control");
 reg_close_all();swprintf_s(retained,MAX_PATH,L"%ls\\missing-retained.sqlite",f.parent);
 expect(MoveFileW(reglib,retained)!=0,"retain actual original outside target leaf");
 expect(reg_open(WH3WG_RECOVER,NULL)&&wh3wr_check(registration),"explicit recovery observes and rechecks missing target");
 expect(sdk_seed(reglib,published),"actual unexpected target appears");
 expect(!wh3wr_check(registration),"recovery refuses silently adopting new target");reg_close_all();
 expect(reg_probe(WH3WG_SHARED)==0&&!rs->sdk_opened,"pending target change never admits ordinary reader");
}
static wh3_session *run_session(run_fixture *r) {
 wh_provider p={0};wh3_backend backend;
 p.abi=EXR_WH_ABI;p.identity_sha=f.b.provider;p.context=r;p.acquire=run_acquire;p.reacquire=run_reacquire;
 p.check=run_check;p.snapshot=run_snapshot;p.import_rows=run_import;p.verify=run_verify;
 p.publish=run_publish;p.inspect=run_inspect;p.discard=run_discard;p.release=run_release;
 backend.abi=EXR_WH3_ABI;backend.context=r;backend.append=run_append;
 return wh3_create(&f.b,&f.g,&p,&backend);
}
static int coordinator_child(reg_shared *shared) {
 run_fixture r={0};wh3_session *session;wh_report report;wh_status status;
 f.b=shared->b;f.g=shared->g;wcscpy_s(reglib,MAX_PATH,shared->library);
 wcscpy_s(f.root,MAX_PATH,shared->root);wcscpy_s(f.parent,MAX_PATH,shared->library);
 *wcsrchr(f.parent,L'\\')=0;r.barrier=shared;
 session=run_session(&r);if(!session)return 91;
 status=wh3_run(session,&report);return status==WH_COMPLETED?0:92;
}
static void coordinator_recovery_case(void) {
 run_fixture r={0};wh3_session *session;wh_report report;wh_status status;HANDLE child;
 char (*lines)[EXR_WH_LINE_MAX]=NULL;const char *pointers[EXR_WH_MAX_JOURNAL];size_t count=0,i;
 unsigned seq=0,event=0;wh3_tip bad;void *cap=NULL;
 if(!reg_fixture("killed-real-coordinator-recovers-actual-published-target",1))return;
 expect(capture_id(reglib,0,&r.before),"independent pre-publication native target");
 child=reg_spawn(WH3WG_OWNER,600);expect(child!=NULL,"spawn real coordinator");if(!child)return;
 expect(WaitForSingleObject(rrdy,15000)==WAIT_OBJECT_0&&rs->reached==600,"actual publication barrier before success journal");
 expect(finish(child,1),"kill real coordinator at observed barrier");
 expect(reg_probe(WH3WG_SHARED)==0&&!rs->sdk_opened,"new reader remains refused after publisher death");
 expect(reg_open(WH3WG_RECOVER,NULL),"fresh recovery custody");
 expect(wh3wr_journal(registration,&f.b,&f.g,NULL,&f.store),"open original native journal");
 lines=calloc(EXR_WH_MAX_JOURNAL,sizeof(*lines));expect(lines!=NULL,"allocate bounded recovery prefix");
 if(!lines){reg_close_all();return;}
 expect(wh3w_read(f.store,lines,EXR_WH_MAX_JOURNAL,&count,&r.tip)&&count==10,
   "read complete independently acknowledged publish-intent prefix");
 if(count!=10){free(lines);reg_close_all();return;}
 expect(sscanf(lines[count-1],"EXRWH2 %u %u %48s %48s",&seq,&event,r.lease,r.stage_id)==4&&
    seq==9&&event==9,"actual historical stage identity is evidence only");
 bad=r.tip;bad.last_line_sha[0]=bad.last_line_sha[0]=='a'?'b':'a';
 expect(!wh3wr_resume(registration,&f.b,&f.g,f.store,&bad,&cap)&&!cap,
    "wrong supplied prefix never upgrades to actual tip");
 reg_close_all();
 r.terminal_count=14;session=run_session(&r);expect(session!=NULL,"new recovery coordinator facade");
 if(!session){free(lines);return;}
 for(i=0;i<count;i++)pointers[i]=lines[i];
 status=wh3_recover(session,pointers,count,&report);
 printf("OBS real_recovery status=%d detail=%s seq=%u proof=%u released=%u\n",
   (int)status,report.detail,report.seq,r.proofs,r.released);
 expect(status==WH_COMPLETED&&!report.live_lease&&!report.poisoned,"fresh actual coordinator confirms publication and completes");
 expect(r.tip.line_count==14&&r.proofs==1&&r.released,"recovery journal and independent content proof precede release");
 expect(wh3_dispose(session),"completed recovery facade disposes");free(lines);
 expect(reg_probe(WH3WG_SHARED)==1&&rs->sdk_opened,"fresh process reads only after recovered CLEAN");
 expect(reg_open(WH3WG_SHARED,NULL)&&wh3wr_check(registration),"recovered trusted target is current");reg_close_all();
}
static int registry_root(wchar_t root[MAX_PATH]) {
 HKEY key=fixture_key();unsigned char record[1352];DWORD size=sizeof(record),type=0;int ok;
 if(!key)return 0;
 ok=RegQueryValueExW(key,L"Binding",NULL,&type,record,&size)==ERROR_SUCCESS&&type==REG_BINARY&&size==sizeof(record);
 RegCloseKey(key);if(!ok)return 0;memcpy(root,record+768,2*MAX_PATH);
 return wmemchr(root,0,MAX_PATH)!=NULL;
}
static void transaction_case(unsigned kind) {
 char name[80],data[64];size_t size=0;wh3_tip empty;void *cap=NULL;
 snprintf(name,sizeof(name),"immutable-transaction-record-%u",kind);
 if(!reg_fixture(name,1))return;
 expect(reg_open(WH3WG_OWNER,NULL),"transaction owner from trusted current domain");
 expect(wh3wr_transaction_write(registration,WH3WR_INPUT,"fixture-input",14),"persist immutable input before pending");
 expect(!wh3wr_transaction_write(registration,WH3WR_INPUT,"changed",8),"input cannot be replaced");
 expect(wh3wr_transaction_read(registration,WH3WR_INPUT,data,sizeof(data),&size)&&size==14&&
    !memcmp(data,"fixture-input",14),"read original acknowledged input");
 expect(!wh3wr_transaction_read(registration,WH3WR_INPUT,data,4,&size)&&size==0,"bounded read refuses short output");
 if(kind){
  HKEY key=fixture_key();unsigned char record[1352],bytes[1601];DWORD n=sizeof(record),type=0;wchar_t value[80];unsigned i;
  expect(key!=NULL,"open explicit tamper control");
  if(key){
   expect(RegQueryValueExW(key,L"Binding",NULL,&type,record,&n)==ERROR_SUCCESS&&n==sizeof(record),"read independent binding");
   wcscpy_s(value,80,L"Transaction-");for(i=0;i<48;i++)value[12+i]=(wchar_t)record[8+i];value[60]=0;
   n=1600;
   expect(RegQueryValueExW(key,value,NULL,&type,bytes,&n)==ERROR_SUCCESS&&n==24+1352+14+64,"read canonical transaction envelope");
   if(n==24+1352+14+64){
    if(kind==1)bytes[24+1288]^=1;
    else {char hash[65];bytes[24+136]^=1;wh_sha256_hex(bytes+24,1288,hash);memcpy(bytes+24+1288,hash,64);}
    wh_sha256_hex(bytes,n-64,(char *)bytes+n-64);
    expect(RegSetValueExW(key,value,0,REG_BINARY,bytes,n)==ERROR_SUCCESS,"rehash outer envelope after semantic mutation");
   }
   RegCloseKey(key);
  }
  expect(!wh3wr_transaction_read(registration,WH3WR_INPUT,data,sizeof(data),&size)&&size==0,"resealed inner corruption or wrong authority is refused");
 }else{
  expect(!wh3wr_transaction_write(registration,WH3WR_PREPARED,"early",6),"no prepared evidence before mutation capability");
  empty_tip(&empty);expect(wh3wr_begin(registration,&f.b,&f.g,&empty,&cap),"durable pending after trusted input");
  expect(wh3wr_transaction_write(registration,WH3WR_PREPARED,"fixture-stage",14),"persist verified-stage record under live cap");
  expect(!wh3wr_transaction_write(registration,WH3WR_PREPARED,"changed",8),"stage proof cannot be replaced");
 }
 reg_close_all();
 if(!kind){
  initial_proofs=0;
  expect(!wh3wr_next_epoch(reglib,counted_initial,(void *)original,NULL)&&initial_proofs==0,
    "checkpoint cannot bypass pending or call SDK for it");
  expect(reg_probe(WH3WG_SHARED)==0&&!rs->sdk_opened,"metadata close leaves pending refused");
 }
}
static int raw_gate_read(const wchar_t *root,unsigned char **bytes,DWORD sizes[3]) {
 const wchar_t *names[]={L"admission.bin",L"journal.bin",L"intent.bin"};wchar_t path[MAX_PATH];unsigned i;
 for(i=0;i<3;i++){swprintf_s(path,MAX_PATH,L"%ls\\%ls",root,names[i]);if(!read_bytes(path,&bytes[i],&sizes[i]))return 0;}return 1;
}
static int raw_gate_same(const wchar_t *root,unsigned char **before,const DWORD sizes[3]) {
 unsigned char *after[3]={0};DWORD n[3]={0};unsigned i;int ok=raw_gate_read(root,after,n);
 for(i=0;i<3;i++){if(n[i]!=sizes[i]||(n[i]&&(!before[i]||!after[i]||memcmp(before[i],after[i],n[i]))))ok=0;free(after[i]);}return ok;
}
static void epoch_repeat_case(void) {
 run_fixture first={0},second={0};wh3_session *session;wh_report report;unsigned i;
 unsigned char *bytes[3]={0};DWORD sizes[3]={0};wchar_t prior[MAX_PATH];wh3w_identity old_id,new_id;
 if(!reg_fixture("two-actual-coordinators-retain-prior-native-epoch",1))return;
 wcscpy_s(prior,MAX_PATH,f.root);expect(capture_id(prior,1,&old_id),"original native epoch identity");
 session=run_session(&first);expect(session!=NULL,"first actual coordinator");if(!session)return;
 expect(wh3_run(session,&report)==WH_COMPLETED&&wh3_dispose(session),"first actual publication completes");
 expect(reg_open(WH3WG_OWNER,NULL)&&run_metadata(),"original immutable inputs remain readable after trusted target advances");reg_close_all();
 expect(raw_gate_read(prior,bytes,sizes),"preserve full previous native pair and gate");
 expect(wh3wr_next_epoch(reglib,sdk_prove,(void *)original,NULL),"explicit independently proven clean checkpoint");
 expect(raw_gate_same(prior,bytes,sizes),"every original native byte retained unchanged");
 for(i=0;i<3;i++)free(bytes[i]);
 expect(registry_root(f.root)&&capture_id(f.root,1,&new_id)&&memcmp(&old_id,&new_id,sizeof(old_id)),"new registered native root identity");
 expect(reg_open(WH3WG_OWNER,NULL),"owner uses new independent epoch");
 {char data[64];size_t n;expect(!wh3wr_transaction_read(registration,WH3WR_INPUT,data,sizeof(data),&n),"previous input cannot bind new epoch");}
 reg_close_all();second.round=1;session=run_session(&second);expect(session!=NULL,"second actual coordinator");if(!session)return;
 expect(wh3_run(session,&report)==WH_COMPLETED&&wh3_dispose(session),"second actual publication uses a fresh journal");
 expect(reg_open(WH3WG_OWNER,NULL)&&run_metadata(),"second exact transaction provenance");reg_close_all();
 expect(reg_probe(WH3WG_SHARED)==1&&rs->sdk_opened,"fresh reader admits the second verified target");
}
static void epoch_kill_case(unsigned phase) {
 char name[100];wchar_t prior[MAX_PATH],next[MAX_PATH];HANDLE child;unsigned i;
 unsigned char *bytes[3]={0};DWORD sizes[3]={0};
 snprintf(name,sizeof(name),"checkpoint-process-death-%u",phase);
 if(!reg_fixture(name,1))return;
 wcscpy_s(prior,MAX_PATH,f.root);expect(raw_gate_read(prior,bytes,sizes),"capture original checkpoint source bytes");
 child=reg_spawn(WH3WG_OWNER,phase);expect(child!=NULL,"spawn real checkpoint owner");if(!child)return;
 expect(WaitForSingleObject(rrdy,15000)==WAIT_OBJECT_0&&rs->reached==(int)phase,"observe exact durable checkpoint barrier");
 expect(finish(child,1),"kill checkpoint owner at observed phase");
 expect(reg_probe(WH3WG_SHARED)==(phase==WH3WR_EPOCH_RETIRED?1:0),"ordinary admission follows durable checkpoint completion");
 expect(wh3wr_next_epoch(reglib,sdk_prove,(void *)original,NULL),"explicit recovery re-proves target and resolves checkpoint");
 expect(raw_gate_same(prior,bytes,sizes),"original checkpoint source files remain byte-identical");
 for(i=0;i<3;i++)free(bytes[i]);
 expect(registry_root(next)&&_wcsicmp(next,prior),"new trusted root retains old root");
 expect(reg_probe(WH3WG_SHARED)==1&&rs->sdk_opened,"fresh SDK reader after confirmed checkpoint");
}
static void checkpoint_bad_case(int replaced) {
 wchar_t root[MAX_PATH],path[MAX_PATH],saved[MAX_PATH];HANDLE child,h;HKEY key;
 if(!reg_fixture(replaced?"checkpoint-refuses-replaced-new-journal":"checkpoint-refuses-malformed-intent",1))return;
 if(replaced){
  child=reg_spawn(WH3WG_OWNER,WH3WR_EPOCH_BOUND);expect(child!=NULL,"spawn checkpoint publication");if(!child)return;
  expect(WaitForSingleObject(rrdy,15000)==WAIT_OBJECT_0&&rs->reached==WH3WR_EPOCH_BOUND,"new binding durable but checkpoint still pending");
  expect(finish(child,1),"kill at published checkpoint");
  expect(registry_root(root),"read independently stored new root");
  swprintf_s(path,MAX_PATH,L"%ls\\journal.bin",root);swprintf_s(saved,MAX_PATH,L"%ls\\original-journal.bin",root);
  expect(MoveFileW(path,saved)!=0,"preserve original journal object");
  h=CreateFileW(path,GENERIC_WRITE,0,NULL,CREATE_NEW,0,NULL);expect(h!=INVALID_HANDLE_VALUE,"actual replacement journal identity");
  if(h!=INVALID_HANDLE_VALUE)CloseHandle(h);
 }else{
  key=fixture_key();expect(key!=NULL,"open malformed-intent control");
  if(key){expect(RegSetValueExW(key,L"Checkpoint",0,REG_BINARY,(const BYTE *)"WH3CKP01",8)==ERROR_SUCCESS,
    "write truncated checkpoint intent");RegCloseKey(key);}
 }
 initial_proofs=0;
 expect(!wh3wr_next_epoch(reglib,counted_initial,(void *)original,NULL)&&initial_proofs==0,
    "bad checkpoint refuses before any SDK proof");
 expect(reg_probe(WH3WG_SHARED)==0&&!rs->sdk_opened,"bad checkpoint remains quarantined");
}
typedef struct {
 wh3w_identity old_id,new_id;DWORD old_size,new_size;char old_sha[65],new_sha[65];
 int old_present,reject;unsigned calls;
} member_proof;
typedef struct {member_proof database,mirror;int has_mirror;} member_terminal;
static int member_hash(HANDLE h,char hash[65],DWORD *size) {
 LARGE_INTEGER n,zero;unsigned char *bytes;DWORD got=0;int ok;
 zero.QuadPart=0;if(h==INVALID_HANDLE_VALUE||!GetFileSizeEx(h,&n)||n.QuadPart<0||n.QuadPart>1048576)return 0;
 bytes=malloc((size_t)n.QuadPart+1);if(!bytes)return 0;
 ok=SetFilePointerEx(h,zero,NULL,FILE_BEGIN)&&ReadFile(h,bytes,(DWORD)n.QuadPart,&got,NULL)&&got==(DWORD)n.QuadPart;
 if(ok){wh_sha256_hex(bytes,got,hash);*size=got;}free(bytes);return ok;
}
static int member_capture(const wchar_t *path,wh3w_identity *id,char hash[65],DWORD *size) {
 HANDLE h;int ok;
 h=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,NULL);
 if(h==INVALID_HANDLE_VALUE)return 0;
 ok=capture_id(path,0,id)&&member_hash(h,hash,size);CloseHandle(h);return ok;
}
static int member_prove(void *context,HANDLE old,HANDLE staged) {
 member_proof *proof=context;char hash[65];DWORD size;proof->calls++;
 if(proof->reject||!!proof->old_present!=(old!=INVALID_HANDLE_VALUE))return 0;
 if(proof->old_present&&(!member_hash(old,hash,&size)||size!=proof->old_size||memcmp(hash,proof->old_sha,65)))return 0;
 return member_hash(staged,hash,&size)&&size==proof->new_size&&!memcmp(hash,proof->new_sha,65);
}
static int member_seed_file(const wchar_t *path,const char *bytes) {
 HANDLE h=CreateFileW(path,GENERIC_WRITE,FILE_SHARE_READ,NULL,CREATE_NEW,FILE_FLAG_WRITE_THROUGH,NULL);DWORD n;int ok;
 if(h==INVALID_HANDLE_VALUE)return 0;
 ok=WriteFile(h,bytes,(DWORD)strlen(bytes),&n,NULL)&&n==strlen(bytes)&&FlushFileBuffers(h);CloseHandle(h);return ok;
}
static int member_prepare(member_proof *proof,void **cap,wh3_tip *tip) {
 wchar_t path[MAX_PATH];wh3_tip empty;memset(proof,0,sizeof(*proof));
 if(!reg_open(WH3WG_OWNER,NULL)||!member_capture(reglib,&proof->old_id,proof->old_sha,&proof->old_size))return 0;
 proof->old_present=1;
 if(!wh3wr_transaction_write(registration,WH3WR_INPUT,proof,sizeof(*proof)))return 0;
 empty_tip(&empty);
 if(!wh3wr_begin(registration,&f.b,&f.g,&empty,cap))return 0;
 swprintf_s(path,MAX_PATH,L"%ls\\member-stage.sqlite",f.parent);
 return sdk_seed(path,published)&&member_capture(path,&proof->new_id,proof->new_sha,&proof->new_size)&&
    wh3wr_transaction_write(registration,WH3WR_PREPARED,proof,sizeof(*proof))&&reg_prefix(*cap,10,tip);
}
static int member_terminal_prove(void *context,const wh3_tip *tip) {
 member_terminal *terminal=context;wchar_t path[MAX_PATH];wh3w_identity id;char hash[65];DWORD size;
 if(tip->line_count!=13||!sdk_prove((void *)published,reglib))return 0;
 swprintf_s(path,MAX_PATH,L"%ls\\member-retained.sqlite",f.parent);
 if(!member_capture(path,&id,hash,&size)||memcmp(&id,&terminal->database.old_id,sizeof(id))||
    size!=terminal->database.old_size||memcmp(hash,terminal->database.old_sha,65))return 0;
 if(terminal->has_mirror){
  swprintf_s(path,MAX_PATH,L"%ls\\mirror.json",f.parent);
  if(!member_capture(path,&id,hash,&size)||memcmp(&id,&terminal->mirror.new_id,sizeof(id))||
     size!=terminal->mirror.new_size||memcmp(hash,terminal->mirror.new_sha,65))return 0;
  if(terminal->mirror.old_present){
   swprintf_s(path,MAX_PATH,L"%ls\\retained-mirror.json",f.parent);
   if(!member_capture(path,&id,hash,&size)||memcmp(&id,&terminal->mirror.old_id,sizeof(id))||
      size!=terminal->mirror.old_size||memcmp(hash,terminal->mirror.old_sha,65))return 0;
  }
 }
 return 1;
}
static int member_finish(void *cap,wh3_tip *tip,member_terminal *proof) {
 size_t i;wh3_tip before=*tip;
 if(!reg_build_terminal()||before.line_count!=10)return 0;
 for(i=10;i<built.n;i++){if(wh3w_append(f.store,cap,&before,built.lines[i],tip)!=WH3_TX_OK)return 0;before=*tip;}
 return wh3wr_finish(registration,f.store,tip,member_terminal_prove,proof);
}
static void member_roundtrip_case(int old_mirror) {
 member_terminal proof={0};void *cap=NULL;wh3_tip tip;wchar_t path[MAX_PATH];wh3w_identity after;
 if(!reg_fixture(old_mirror?"compound-existing-mirror-handle-proof":"compound-new-mirror-handle-proof",1))return;
 expect(member_prepare(&proof.database,&cap,&tip),"native pending, immutable images and publish-intent prefix");if(!cap)return;
 swprintf_s(path,MAX_PATH,L"%ls\\occupied.sqlite",f.parent);
 expect(member_seed_file(path,"foreign retained object"),"real unexpected retention object");
 expect(wh3wr_publish_member(registration,L"library.sqlite",&proof.database.old_id,L"member-stage.sqlite",
    &proof.database.new_id,L"occupied.sqlite",member_prove,&proof.database,NULL)==WH3_TX_MISMATCH,"never overwrite unexpected retained object");
 proof.database.reject=1;
 expect(wh3wr_publish_member(registration,L"library.sqlite",&proof.database.old_id,L"member-stage.sqlite",
    &proof.database.new_id,L"member-retained.sqlite",member_prove,&proof.database,NULL)==WH3_TX_MISMATCH,"actual-handle proof refusal performs no rename");
 expect(sdk_prove((void *)original,reglib),"original SDK target remains unchanged after refusal");
 proof.database.reject=0;
 expect(wh3wr_publish_member(registration,L"library.sqlite",&proof.database.old_id,L"member-stage.sqlite",
    &proof.database.new_id,L"member-retained.sqlite",member_prove,&proof.database,NULL)==WH3_TX_OK,"handle-verified actual database publication");
 expect(wh3wr_check(registration),"live target identity after checked publication");
 expect(wh3wr_publish_member(registration,L"library.sqlite",&proof.database.old_id,L"member-stage.sqlite",
    &proof.database.new_id,L"member-retained.sqlite",member_prove,&proof.database,NULL)==WH3_TX_OK,"exact already-published state is verified again");
 proof.has_mirror=1;proof.mirror.old_present=old_mirror;
 if(old_mirror){
  swprintf_s(path,MAX_PATH,L"%ls\\mirror.json",f.parent);
  expect(member_seed_file(path,"old ledger")&&member_capture(path,&proof.mirror.old_id,proof.mirror.old_sha,&proof.mirror.old_size),"capture actual previous mirror");
 }
 swprintf_s(path,MAX_PATH,L"%ls\\stage-mirror.json",f.parent);
 expect(member_seed_file(path,"verified new ledger")&&member_capture(path,&proof.mirror.new_id,proof.mirror.new_sha,&proof.mirror.new_size),"capture actual staged mirror");
 expect(wh3wr_publish_member(registration,L"mirror.json",old_mirror?&proof.mirror.old_id:NULL,L"stage-mirror.json",
    &proof.mirror.new_id,old_mirror?L"retained-mirror.json":NULL,member_prove,&proof.mirror,NULL)==WH3_TX_OK,"second publication member uses the same exclusive domain");
 expect(reg_probe(WH3WG_SHARED)==0&&!rs->sdk_opened,"compound publication remains closed before terminal proof");
 expect(member_finish(cap,&tip,&proof),"all members independently prove before CLEAN");
 reg_close_all();
 expect(capture_id(reglib,0,&after)&&!memcmp(&after,&proof.database.new_id,sizeof(after)),"actual new database identity retained");
 expect(reg_probe(WH3WG_SHARED)==1,"fresh reader after compound proof"); 
}
static int member_child(reg_shared *shared) {
 member_proof proof;void *cap=NULL;wh3_tip tip;wh3w_controls controls={0};
 f.b=shared->b;f.g=shared->g;wcscpy_s(reglib,MAX_PATH,shared->library);
 wcscpy_s(f.root,MAX_PATH,shared->root);wcscpy_s(f.parent,MAX_PATH,shared->library);*wcsrchr(f.parent,L'\\')=0;
 controls.context=shared;controls.phase=reg_barrier;
 if(!member_prepare(&proof,&cap,&tip))return 97;
 return wh3wr_publish_member(registration,L"library.sqlite",&proof.old_id,L"member-stage.sqlite",&proof.new_id,
    L"member-retained.sqlite",member_prove,&proof,&controls)==WH3_TX_OK?0:98;
}
static void member_kill_case(unsigned phase) {
 char name[100];HANDLE child;member_terminal proof={0};member_proof input={0};size_t size=0,count=0;
 wh3_tip tip;void *cap=NULL;char (*lines)[EXR_WH_LINE_MAX];wh3w_identity before;char before_sha[65];DWORD before_size;
 snprintf(name,sizeof(name),"native-member-process-death-%u",phase);
 if(!reg_fixture(name,1))return;
 expect(member_capture(reglib,&before,before_sha,&before_size),"independent original content and native identity");
 child=reg_spawn(WH3WG_OWNER,phase);expect(child!=NULL,"spawn checked native publisher");if(!child)return;
 expect(WaitForSingleObject(rrdy,15000)==WAIT_OBJECT_0&&rs->reached==(int)phase,"observe exact native publication barrier");
 expect(finish(child,1),"kill actual checked publisher");
 expect(reg_probe(WH3WG_SHARED)==0&&!rs->sdk_opened,"pending native namespace never admits fresh reader");
 expect(reg_open(WH3WG_RECOVER,NULL),"fresh exclusive reconciliation holder");
 expect(wh3wr_transaction_read(registration,WH3WR_INPUT,&input,sizeof(input),&size)&&size==sizeof(input)&&
    !memcmp(&input.old_id,&before,sizeof(before))&&input.old_size==before_size&&!memcmp(input.old_sha,before_sha,65),"independent original registration proof");
 expect(wh3wr_transaction_read(registration,WH3WR_PREPARED,&proof.database,sizeof(proof.database),&size)&&
    size==sizeof(proof.database)&&!memcmp(&proof.database.old_id,&before,sizeof(before))&&
    proof.database.old_size==before_size&&!memcmp(proof.database.old_sha,before_sha,65),"acknowledged staged native proof survives death");
 expect(wh3wr_journal(registration,&f.b,&f.g,NULL,&f.store),"reopen exact original journal");
 lines=calloc(EXR_WH_MAX_JOURNAL,sizeof(*lines));expect(lines!=NULL,"bounded original prefix storage");if(!lines)return;
 expect(wh3w_read(f.store,lines,EXR_WH_MAX_JOURNAL,&count,&tip)&&count==10,"complete original publish-intent prefix");
 free(lines);
 expect(wh3wr_resume(registration,&f.b,&f.g,f.store,&tip,&cap),"fresh capability for exact acknowledged prefix");
 expect(wh3wr_publish_member(registration,L"library.sqlite",&proof.database.old_id,L"member-stage.sqlite",
    &proof.database.new_id,L"member-retained.sqlite",member_prove,&proof.database,NULL)==WH3_TX_OK,"complete or confirm only the exact retained/staged native state");
 expect(member_finish(cap,&tip,&proof),"verified original and actual target precede recovered CLEAN");
 reg_close_all();expect(reg_probe(WH3WG_SHARED)==1,"fresh reader after independently proven namespace repair");
}
int main(int argc,char **argv) {
 if(argc==3&&!strcmp(argv[1],"--registry-child"))return reg_child(argv[2]);
 if(argc==3&&!strcmp(argv[1],"--probe-owner")){
  wchar_t path[MAX_PATH];wh3wr_registration *r=NULL;int ok;
  if(!MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,argv[2],-1,path,MAX_PATH))return 3;
  ok=wh3wr_open(path,WH3WG_OWNER,NULL,&r);(void)wh3wr_close(r);return ok?0:10;
 }
 if(argc==2&&(!strcmp(argv[1],"--prepare-host")||!strcmp(argv[1],"--prepare-unregistered")||!strcmp(argv[1],"--prepare-pending")||!strcmp(argv[1],"--prepare-enrollment-failure"))){
  char path[4*MAX_PATH];wh3_tip empty;void *cap=NULL;
  if(!reg_fixture("actual-product-startup",strcmp(argv[1],"--prepare-unregistered")!=0&&strcmp(argv[1],"--prepare-enrollment-failure")!=0))return 1;
  if(!strcmp(argv[1],"--prepare-enrollment-failure")&&wh3wr_enroll(reglib,f.root,initial_refuse,NULL))return 1;
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
 {unsigned i;for(i=WH3WR_ENROLL_RESERVED;i<=WH3WR_ENROLL_BOUND;i++)enrollment_kill(i);
  for(i=0;i<3;i++){enrollment_policy(i,0);enrollment_policy(i,1);}
  for(i=0;i<4;i++)enrollment_bad(i);}
 drive_alias_case();coordinator_case();recover_missing_case();coordinator_recovery_case();
 {unsigned i;for(i=0;i<3;i++)transaction_case(i);epoch_repeat_case();
  for(i=WH3WR_EPOCH_INTENT;i<=WH3WR_EPOCH_RETIRED;i++)epoch_kill_case(i);}
 checkpoint_bad_case(0);checkpoint_bad_case(1);
 member_roundtrip_case(0);member_roundtrip_case(1);
 {unsigned i;for(i=WH3WR_MEMBER_PROVED;i<=WH3WR_MEMBER_FLUSHED;i++)member_kill_case(i);}
 fixture_close();if(rs)UnmapViewOfFile(rs);if(rm)CloseHandle(rm);if(rrdy)CloseHandle(rrdy);if(rgo)CloseHandle(rgo);
 printf("{\"source\":\"%s\",\"cases\":%u,\"checks\":%u,\"failed\":%u,\"passed\":%s,\"actual_sdk\":true,\"trusted_registry\":true,\"production_coordinator\":false,\"full_c02_acceptance\":false}\n",
   CANDIDATE_SOURCE_SHA,cases,checks,failures,failures?"false":"true");
 return failures?1:0;
}
