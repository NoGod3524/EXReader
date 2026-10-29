/* SPDX-License-Identifier: MIT
 * Native qualification consumer only. Frozen scanner/oracle source is included
 * explicitly, unmodified; this is not linked into a product executable. */
#define main frozen_preflight_entry
#include "../recovery_preflight_20261029/probe.c"
#undef main
#include "lm_recovery_win32_platform.h"
#include <bcrypt.h>
#include <aclapi.h>
#include <sddl.h>

static wr_context *wc;
static wr_error we={0,"none"};
static HANDLE job_handle;
static char wn[33],producer[65],wphase[64]="start",root_id[49];
static WCHAR wroot[WR_PATH],self_exe[WR_PATH];
static int target_sdk_open_attempted,finish_status=-1,commit_requested,worker_waited,contained;
static unsigned stage_serial;
static lm_sb telemetry,os_events;static unsigned os_event_count;
static void os_log(void *unused,int code,const char *message){(void)unused;if(os_event_count>=32||!message||strlen(message)>2048){failed=1;reason="sqlite-log-bound";return;}if(os_event_count++)lm_sb_str(&os_events,",");lm_sb_fmt(&os_events,"{\"phase\":\"%s\",\"code\":%d,\"message\":",wphase,code);lm_sb_json(&os_events,message,strlen(message));lm_sb_str(&os_events,"}");if(os_events.oom||os_events.n>131072){failed=1;reason="sqlite-log-bound";}}
static int launch_child(const char *variant);
static int raw_target_id(wr_identity *id);
static HANDLE child_output_pin=INVALID_HANDLE_VALUE;
static wr_identity slot_ids[4],use_ids[4],anchor_identity;static char anchor_sha[65];static int anchor_seen;
static char unused_catalog[4096];
static char parent_request_sha[65];static wr_identity parent_request_identity;
static char request_sha[65];static wr_identity request_identity,child_target_identity;static int request_seen;
static ULONGLONG deadline;
static jv *wparse(const char *s,size_t n){char err[128];return lm_json_parse(s,n,err,sizeof(err));}
static const char *wstr(const jv *j,const char *key){const jv *v=lm_get(j,key);return v&&v->t==J_STR&&strlen(v->s)==v->n?v->s:"";}
static int wf(const char *s){if(!failed){reason=s;failed=1;}return 0;}
static int wok(int value){return value?1:wf(we.reason?we.reason:"adapter-error");}
static int wp(char out[4096],const char *leaf){if(snprintf(out,4096,"%s/%s",root,leaf)>=4096)return wf("path-bound");return 1;}
static int wfile(const char *leaf,const void *p,size_t n){WCHAR w[WR_PATH];if(!wok(wr_utf8(leaf,w,&we)))return 0;return wok(wr_write_new(wc,w,p,n,1,NULL,&we));}
static int wbytes(const WCHAR *leaf,char **p,size_t *n){HANDLE h=wr_open(wc,leaf,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,0,&we);int ok;if(h==INVALID_HANDLE_VALUE)return wok(0);ok=wr_read(h,(void**)p,n,WR_RECORD_MAX,&we);if(!CloseHandle(h))ok=0;return wok(ok);}
static int wmetadata(const WCHAR *leaf,wr_identity *id){HANDLE h=wr_open(wc,leaf,0,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,0,&we);int ok;if(h==INVALID_HANDLE_VALUE)return wok(0);ok=wr_identity_get(h,0,id,&we);CloseHandle(h);return wok(ok);}
static int wexe(void){WCHAR path[WR_PATH];DWORD length;char utf8[12288];lm_mirror_file f;lm_err e={{0},{0}};
 length=GetModuleFileNameW(NULL,path,WR_PATH);if(!length||length>=WR_PATH||!WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,path,-1,utf8,sizeof(utf8),NULL,NULL))return wf("executable-path");wcscpy(self_exe,path);
 if(!lm_mirror_snapshot(utf8,1,LIMIT,&f,NULL,NULL,&e)||!f.present)return wf("executable-hash");strcpy(producer,f.sha);return 1;}
static int ancestor_observations(void){unsigned i;int ok=1;lm_sb_str(&telemetry,",\"outside_ancestors\":[");
 for(i=0;i+1<wc->count;i++){PSECURITY_DESCRIPTOR sd=NULL;LPWSTR sddl=NULL;char acl[4096],path[12288],identity[49];DWORD error;wr_identity current;
 if(telemetry.n>1024*1024||!wr_identity_get(wc->pins[i],1,&current,&we)||!wr_identity_equal(&current,&wc->identities[i])){wf("ancestor-evidence-bound");ok=0;break;}
 error=GetSecurityInfo(wc->pins[i],SE_FILE_OBJECT,OWNER_SECURITY_INFORMATION|DACL_SECURITY_INFORMATION,NULL,NULL,NULL,NULL,&sd);
 if(error||!ConvertSecurityDescriptorToStringSecurityDescriptorW(sd,SDDL_REVISION_1,OWNER_SECURITY_INFORMATION|DACL_SECURITY_INFORMATION,&sddl,NULL)||!WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,sddl,-1,acl,sizeof(acl),NULL,NULL)||!WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wc->paths[i],-1,path,sizeof(path),NULL,NULL)){if(sd)LocalFree(sd);if(sddl)LocalFree(sddl);wf("ancestor-acl-observation-unavailable");ok=0;break;}
 wr_identity_text(&current,identity);if(i)lm_sb_str(&telemetry,",");lm_sb_str(&telemetry,"{\"path\":");lm_sb_json(&telemetry,path,strlen(path));lm_sb_fmt(&telemetry,",\"identity\":\"%s\",\"attributes\":%lu,\"requested_access\":%lu,\"requested_share\":%lu,\"type\":\"nonreparse-directory\",\"classification\":\"outside-pinned-not-private\",\"observed_sddl\":",identity,current.attributes,(DWORD)(FILE_TRAVERSE|FILE_READ_ATTRIBUTES|READ_CONTROL),(DWORD)FILE_SHARE_READ);lm_sb_json(&telemetry,acl,strlen(acl));lm_sb_str(&telemetry,"}");LocalFree(sd);LocalFree(sddl);if(telemetry.oom){wf("ancestor-evidence-allocation");ok=0;break;}}
 lm_sb_str(&telemetry,"]");return ok&&!failed;}
static int initialize(void){lm_sb b;unsigned i;char id[49],uid[49];WCHAR leaf[48];wr_identity x;HANDLE h;lm_sb_init(&b);
 if(!wfile("outer.lock",wn,32))goto done;
 for(i=0;i<4;i++){swprintf(leaf,48,L"slot-%u.lock",i);if(!wok(wr_write_new(wc,leaf,wn,32,1,&h,&we)))goto done;if(!wok(wr_identity_get(h,0,&slot_ids[i],&we))){CloseHandle(h);goto done;}CloseHandle(h);
  swprintf(leaf,48,L"use-%u.json",i);if(!wok(wr_write_new(wc,leaf,"",0,1,&h,&we)))goto done;if(!wok(wr_identity_get(h,0,&use_ids[i],&we))){CloseHandle(h);goto done;}CloseHandle(h);}
 wr_identity_text(&wc->root,root_id);lm_sb_fmt(&b,"{\"format\":\"WRN1\",\"root\":\"%s\",\"producer\":\"%s\",\"nonce\":\"%s\",\"slots\":[",root_id,producer,wn);
 for(i=0;i<4;i++){wr_identity_text(&slot_ids[i],id);wr_identity_text(&use_ids[i],uid);lm_sb_fmt(&b,"%s[\"%s\",\"%s\"]",i?",":"",id,uid);}lm_sb_str(&b,"]}\n");
 if(b.oom||b.n>WR_RECORD_MAX){wf("anchor-bound");goto done;}wfile("anchor.json",b.p,b.n);
 done:lm_sb_free(&b);(void)x;return !failed;}
static int anchor(void){char *p=NULL;size_t n=0; jv *a=NULL;lm_err e={{0},{0}};const jv *rows,*x;unsigned i;char id[49];WCHAR leaf[48];wr_identity got;
 if(!wbytes(L"anchor.json",&p,&n))goto done;{wr_identity now;char sha[65];if(!wmetadata(L"anchor.json",&now))goto done;lm_sha_bytes(p,n,sha);if(anchor_seen&&(!wr_identity_equal(&now,&anchor_identity)||strcmp(sha,anchor_sha))){wf("anchor-changed");goto done;}if(!anchor_seen){anchor_identity=now;strcpy(anchor_sha,sha);anchor_seen=1;}}a=wparse(p,n);if(!a||a->t!=J_OBJ||a->n!=5||strcmp(wstr(a,"format"),"WRN1")||strcmp(wstr(a,"producer"),producer)||strcmp(wstr(a,"nonce"),wn)){wf("anchor-envelope");goto done;}
 wr_identity_text(&wc->root,id);if(strcmp(wstr(a,"root"),id)){wf("anchor-root-identity");goto done;}strcpy(root_id,id);rows=lm_get(a,"slots");if(!rows||rows->t!=J_ARR||rows->n!=4){wf("anchor-slots");goto done;}
 for(i=0;i<4;i++){x=rows->items[i];if(!x||x->t!=J_ARR||x->n!=2||x->items[0]->t!=J_STR||x->items[1]->t!=J_STR||x->items[0]->n!=48||x->items[1]->n!=48||strlen(x->items[0]->s)!=48||strlen(x->items[1]->s)!=48){wf("anchor-slot-shape");goto done;}
  swprintf(leaf,48,L"slot-%u.lock",i);if(!wmetadata(leaf,&got))goto done;wr_identity_text(&got,id);if(strcmp(id,x->items[0]->s)){wf("anchored-slot-replaced");goto done;}slot_ids[i]=got;
  swprintf(leaf,48,L"use-%u.json",i);if(!wmetadata(leaf,&got))goto done;wr_identity_text(&got,id);if(strcmp(id,x->items[1]->s)){wf("anchored-use-replaced");goto done;}use_ids[i]=got;}
 done:free(p);lm_json_free(a);return !failed;}
static int slots_free(void){unsigned i;WCHAR name[48];HANDLE h;for(i=0;i<4;i++){swprintf(name,48,L"slot-%u.lock",i);h=wr_open(wc,name,GENERIC_READ|GENERIC_WRITE,0,0,&we);if(h==INVALID_HANDLE_VALUE)return wok(0);CloseHandle(h);}return 1;}
static int wrendezvous(const char *phase){char leaf[96],*data=NULL;WCHAR w[96];HANDLE h;size_t n;lm_sb b;strcpy(wphase,phase);lm_sb_init(&b);lm_sb_fmt(&b,"{\"phase\":\"%s\",\"nonce\":\"%s\",\"pid\":%lu,\"sdk_open_attempted\":%s}\n",phase,wn,GetCurrentProcessId(),target_sdk_open_attempted?"true":"false");snprintf(leaf,sizeof(leaf),"%s.ready",phase);if(!wfile(leaf,b.p,b.n)){lm_sb_free(&b);return 0;}lm_sb_free(&b);
 snprintf(leaf,sizeof(leaf),"%s.go",phase);if(!wok(wr_utf8(leaf,w,&we)))return 0;
 while(GetTickCount64()<deadline){h=wr_open(wc,w,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,0,&we);if(h!=INVALID_HANDLE_VALUE){int ok=wr_read(h,(void**)&data,&n,128,&we);CloseHandle(h);if(!ok){free(data);return wok(0);}ok=n==32&&!memcmp(data,wn,32);free(data);return ok?wok(wr_recheck(wc,&we)):wf("rendezvous-token");}if(we.native!=ERROR_FILE_NOT_FOUND)return wok(0);Sleep(10);}return wf("rendezvous-deadline");}
static HANDLE take_slot(unsigned index,const char *kind,const WCHAR *output,const wr_identity *expected_output,const char *request_fault){WCHAR leaf[48];HANDLE h=INVALID_HANDLE_VALUE,u=INVALID_HANDLE_VALUE;wr_identity id,output_id;HANDLE od;lm_sb b;DWORD n;char sid[49],oid[49],uid[49],tid[49];wr_identity target_id;LARGE_INTEGER zero;lm_sb_init(&b);
 if(index>=4||!anchor())goto done;swprintf(leaf,48,L"slot-%u.lock",index);h=wr_open(wc,leaf,GENERIC_READ|GENERIC_WRITE,0,0,&we);if(h==INVALID_HANDLE_VALUE){wok(0);goto done;}
 if(!wr_identity_get(h,0,&id,&we)||!wr_identity_equal(&id,&slot_ids[index])){wf("slot-actual-handle");goto done;}
 if(wcslen(wc->path)+15>=WR_PATH||_wcsnicmp(output,wc->path,wcslen(wc->path))||wcscmp(output+wcslen(wc->path),L"\\worker-output")){wf("child-output-path");goto done;}
 od=CreateFileW(output,FILE_READ_ATTRIBUTES|READ_CONTROL,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,NULL,OPEN_EXISTING,FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,NULL);if(od==INVALID_HANDLE_VALUE){wf("output-open");goto done;}if(!wr_identity_get(od,1,&output_id,&we)){CloseHandle(od);wok(0);goto done;}CloseHandle(od);if(!wr_identity_equal(&output_id,expected_output)){wf("created-output-replaced");goto done;}
 swprintf(leaf,48,L"use-%u.json",index);u=wr_open(wc,leaf,GENERIC_READ|GENERIC_WRITE,FILE_SHARE_READ,0,&we);if(u==INVALID_HANDLE_VALUE){wok(0);goto done;}
 if(!wr_identity_get(u,0,&id,&we)||!wr_identity_equal(&id,&use_ids[index])||id.size){wf("use-once");goto done;}
 if(!raw_target_id(&target_id))goto done;wr_identity_text(&target_id,tid);wr_identity_text(&slot_ids[index],sid);wr_identity_text(&use_ids[index],uid);wr_identity_text(&output_id,oid);
 lm_sb_fmt(&b,"{\"kind\":\"%s\",\"nonce\":\"%s\",\"root\":\"%s\",\"slot\":%u,\"slot_id\":\"%s\",\"use_id\":\"%s\",\"producer\":\"%s\",\"output_id\":\"%s\",\"target_id\":\"%s\"}\n",kind,!strcmp(request_fault,"nonce")?"00000000000000000000000000000000":wn,root_id,index,sid,uid,!strcmp(request_fault,"producer")?"0000000000000000000000000000000000000000000000000000000000000000":producer,!strcmp(request_fault,"output")?"000000000000000000000000000000000000000000000000":oid,tid);
 zero.QuadPart=0;if(b.oom||b.n>4096||!SetFilePointerEx(u,zero,NULL,FILE_BEGIN)||!WriteFile(u,b.p,(DWORD)b.n,&n,NULL)||n!=b.n||!wr_flush(u,&we)){wok(0);goto done;}{void *check=NULL;size_t size=0;if(!wr_read(u,&check,&size,4096,&we)||size!=b.n||memcmp(check,b.p,size)){free(check);wf("use-write-reread");goto done;}free(check);}if(!wr_identity_get(u,0,&parent_request_identity,&we)){wok(0);goto done;}lm_sha_bytes(b.p,b.n,parent_request_sha);CloseHandle(u);u=INVALID_HANDLE_VALUE;
 done:lm_sb_free(&b);if(u!=INVALID_HANDLE_VALUE)CloseHandle(u);if(failed&&h!=INVALID_HANDLE_VALUE){CloseHandle(h);h=INVALID_HANDLE_VALUE;}return h;}
static int request_canonical(const jv *j,const char *raw,size_t n,unsigned index){lm_sb b;uint64_t ordinal;int ok=0;lm_sb_init(&b);
 if(n>4096||!j||j->t!=J_OBJ||j->n!=9||!lm_json_uint(lm_get(j,"slot"),&ordinal)||ordinal!=index)goto done;
 lm_sb_str(&b,"{\"kind\":");lm_sb_json(&b,wstr(j,"kind"),strlen(wstr(j,"kind")));lm_sb_str(&b,",\"nonce\":");lm_sb_json(&b,wstr(j,"nonce"),strlen(wstr(j,"nonce")));lm_sb_str(&b,",\"root\":");lm_sb_json(&b,wstr(j,"root"),strlen(wstr(j,"root")));lm_sb_fmt(&b,",\"slot\":%u,\"slot_id\":",index);lm_sb_json(&b,wstr(j,"slot_id"),strlen(wstr(j,"slot_id")));lm_sb_str(&b,",\"use_id\":");lm_sb_json(&b,wstr(j,"use_id"),strlen(wstr(j,"use_id")));lm_sb_str(&b,",\"producer\":");lm_sb_json(&b,wstr(j,"producer"),strlen(wstr(j,"producer")));lm_sb_str(&b,",\"output_id\":");lm_sb_json(&b,wstr(j,"output_id"),strlen(wstr(j,"output_id")));lm_sb_str(&b,",\"target_id\":");lm_sb_json(&b,wstr(j,"target_id"),strlen(wstr(j,"target_id")));lm_sb_str(&b,"}\n");ok=!b.oom&&b.n==n&&!memcmp(b.p,raw,n);
 done:lm_sb_free(&b);return ok;}
static int child_envelope(unsigned index,HANDLE lease,const WCHAR *output,const char *expected,int pin){char *p=NULL;size_t n;WCHAR leaf[48];jv *j=NULL;lm_err e={{0},{0}};wr_identity id,oi;char text[49];HANDLE d=INVALID_HANDLE_VALUE,compete=INVALID_HANDLE_VALUE;
 if(index>=4||!anchor())goto done;if(!wr_identity_get(lease,0,&id,&we)||!wr_identity_equal(&id,&slot_ids[index])){wf("inherited-slot-identity");goto done;}
 swprintf(leaf,48,L"slot-%u.lock",index);compete=wr_open(wc,leaf,GENERIC_READ|GENERIC_WRITE,0,0,&we);if(compete!=INVALID_HANDLE_VALUE){CloseHandle(compete);wf("inherited-sharing-not-exclusive");goto done;}if(we.native!=ERROR_SHARING_VIOLATION){wok(0);goto done;}
 swprintf(leaf,48,L"use-%u.json",index);if(!wbytes(leaf,&p,&n))goto done;
 {char digest[65];wr_identity current;lm_sha_bytes(p,n,digest);if(!wmetadata(leaf,&current))goto done;if(request_seen&&(!wr_identity_equal(&current,&request_identity)||strcmp(digest,request_sha))){wf("child-request-changed");goto done;}if(!request_seen){request_identity=current;strcpy(request_sha,digest);request_seen=1;}}
 j=wparse(p,n);if(!request_canonical(j,p,n,index)||strcmp(wstr(j,"kind"),expected)||strcmp(wstr(j,"nonce"),wn)||strcmp(wstr(j,"root"),root_id)||strcmp(wstr(j,"producer"),producer)){wf("child-request-envelope");goto done;}
 wr_identity_text(&slot_ids[index],text);if(strcmp(wstr(j,"slot_id"),text)){wf("child-request-slot");goto done;}wr_identity_text(&use_ids[index],text);if(strcmp(wstr(j,"use_id"),text)){wf("child-request-use");goto done;}
 {uint64_t z;if(!lm_json_uint(lm_get(j,"slot"),&z)||z!=index){wf("child-request-slot-number");goto done;}}
 if(_wcsnicmp(output,wc->path,wcslen(wc->path))||wcscmp(output+wcslen(wc->path),L"\\worker-output")){wf("child-output-path");goto done;}
 d=CreateFileW(output,FILE_READ_ATTRIBUTES|READ_CONTROL,pin?FILE_SHARE_READ:FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,NULL,OPEN_EXISTING,FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,NULL);if(d==INVALID_HANDLE_VALUE||!wr_identity_get(d,1,&oi,&we)||!wr_private_acl(d,1,wc,&we)){wf("child-output-identity");goto done;}wr_identity_text(&oi,text);if(strcmp(wstr(j,"output_id"),text)){wf("child-output-replaced");goto done;}
 {wr_identity target_now;if(!raw_target_id(&target_now))goto done;wr_identity_text(&target_now,text);if(strcmp(wstr(j,"target_id"),text)){wf("child-target-request");goto done;}}
 if(pin&&child_output_pin==INVALID_HANDLE_VALUE){child_output_pin=d;d=INVALID_HANDLE_VALUE;}
 done:if(d!=INVALID_HANDLE_VALUE)CloseHandle(d);free(p);lm_json_free(j);return !failed;}
static int raw_target_id(wr_identity *id){WCHAR path[WR_PATH];HANDLE h;int ok;if(!wr_join(wc,L"library.sqlite",path,&we))return wok(0);h=CreateFileW(path,FILE_READ_ATTRIBUTES|READ_CONTROL,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,NULL,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,NULL);if(h==INVALID_HANDLE_VALUE)return wf("target-metadata-open");ok=wr_identity_get(h,0,id,&we)&&wr_data_acl(h,wc,&we);CloseHandle(h);return wok(ok);}
typedef struct {wr_identity id;char sha[65];size_t size;int present;char path[4096];} bound_file;
static bound_file baseline_ref,scan_ref,result_ref;
static int file_ref(const char *path,bound_file *ref,int compare){WCHAR wide[WR_PATH];HANDLE h=INVALID_HANDLE_VALUE;wr_identity id;void *bytes=NULL;size_t n=0;char sha[65];int ok=0;
 if(!wr_recheck(wc,&we)||!wr_utf8(path,wide,&we))return wok(0);
 h=CreateFileW(wide,GENERIC_READ|READ_CONTROL,FILE_SHARE_READ,NULL,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,NULL);
 if(h==INVALID_HANDLE_VALUE){we.native=GetLastError();return wf("bound-evidence-open");}
 if(!wr_identity_get(h,0,&id,&we)||!wr_data_acl(h,wc,&we)||!wr_read(h,&bytes,&n,LIMIT,&we)){wok(0);goto done;}lm_sha_bytes(bytes,n,sha);
 if(compare){if(!ref->present||!wr_identity_equal(&ref->id,&id)||ref->size!=n||strcmp(ref->sha,sha)){wf("bound-evidence-changed");goto done;}}
 else{ref->id=id;ref->size=n;strcpy(ref->sha,sha);if(strlen(path)>=sizeof(ref->path)){wf("bound-path");goto done;}strcpy(ref->path,path);ref->present=1;}ok=1;
 done:free(bytes);if(!CloseHandle(h)){wf("bound-close");ok=0;}return ok;}
static int evidence_recheck(void){return file_ref(baseline_ref.path,&baseline_ref,1)&&file_ref(scan_ref.path,&scan_ref,1)&&file_ref(result_ref.path,&result_ref,1);}
static int used_outputs(void){unsigned i;WCHAR leaf[64],path[WR_PATH];char *p=NULL;size_t n=0;jv *j=NULL;wr_identity id;HANDLE h;char text[49];int ok=0;
 for(i=0;i<4;i++){swprintf(leaf,64,L"use-%u.json",i);if(!wbytes(leaf,&p,&n))goto done;if(!n){free(p);p=NULL;continue;}j=wparse(p,n);
 if(!request_canonical(j,p,n,i)||strlen(wstr(j,"target_id"))!=48||strcmp(wstr(j,"nonce"),wn)||strcmp(wstr(j,"root"),root_id)||strcmp(wstr(j,"producer"),producer)||(strcmp(wstr(j,"kind"),"sdkchild")&&strcmp(wstr(j,"kind"),"scanner")&&strcmp(wstr(j,"kind"),"holder"))){wf("retained-use-envelope");goto done;}
 {wr_identity current_target;if(!raw_target_id(&current_target))goto done;wr_identity_text(&current_target,text);if(strcmp(text,wstr(j,"target_id"))){wf("retained-target-replaced");goto done;}}
 wr_identity_text(&slot_ids[i],text);if(strcmp(text,wstr(j,"slot_id"))){wf("retained-use-slot");goto done;}wr_identity_text(&use_ids[i],text);if(strcmp(text,wstr(j,"use_id"))){wf("retained-use-identity");goto done;}
 {uint64_t slot;if(!lm_json_uint(lm_get(j,"slot"),&slot)||slot!=i){wf("retained-use-ordinal");goto done;}}
 if(i||!wr_join(wc,L"worker-output",path,&we)){wf("unsupported-used-slot");goto done;}
 h=CreateFileW(path,FILE_READ_ATTRIBUTES|READ_CONTROL,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,NULL,OPEN_EXISTING,FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,NULL);
 if(h==INVALID_HANDLE_VALUE){wf("retained-output-missing");goto done;}if(!wr_identity_get(h,1,&id,&we)||!wr_private_acl(h,1,wc,&we)){CloseHandle(h);wok(0);goto done;}CloseHandle(h);wr_identity_text(&id,text);if(strcmp(text,wstr(j,"output_id"))){wf("retained-output-replaced");goto done;}
 free(p);p=NULL;lm_json_free(j);j=NULL;}
 ok=1;
 done:free(p);lm_json_free(j);return ok&&!failed;}
static int mutate(exr_library *owner,const char *title){exr_book *books=NULL;size_t count=0,i;exr_error e={0};int found=0;sdk_status=exr_library_books(owner,"",&books,&count,&e);if(sdk_status!=EXR_OK)return wf("sdk-books");for(i=0;i<count;i++)if(books[i].id==1){exr_book b=books[i];b.title=(char*)title;sdk_status=exr_library_update(owner,&b,&e);found=1;break;}exr_books_free(books,count);return found&&sdk_status==EXR_OK?1:wf("sdk-mutate");}
static int native_scan(const char *output){sqlite3 *db=NULL;lm_sb b;char path[4096];int ok=0;lm_sb_init(&b);if(!open_db(target,0,&db)||!execsql(db,"BEGIN")||!canonical(db,&b,0)||!tx(db,0))goto done;
 if(!wp(path,output)||!wfile(output,b.p,b.n))goto done;ok=1;
 done:close_db(&db);lm_sb_free(&b);return ok&&!failed;}
static int sdk_owner(const char *op){exr_library *owner=NULL;exr_error e={0};wr_identity before,after;int ok=0;char *expected=NULL,*observed=NULL;size_t en=0,on=0;
 if(!anchor()||!slots_free()||!used_outputs()||!raw_target_id(&before)||!wrendezvous("before-sdk"))goto done;if(!anchor()||!slots_free()||!raw_target_id(&after)||!wr_identity_equal(&before,&after)){wf("target-preopen-replaced");goto done;}
 target_sdk_open_attempted=1;sdk_status=exr_library_migration_open(target,&owner,&e);if(sdk_status!=EXR_OK){wf("sdk-open");goto done;}
 if(!wrendezvous("owner-held"))goto done;
 if(!strcmp(op,"handoff")||!strcmp(op,"scan")){if(!launch_child("scanner"))goto done;}
 if(!strcmp(op,"handoff")){
  {char path[4096];if(!wp(path,"baseline.bin")||!file_ref(path,&baseline_ref,0)||!wp(path,"worker-output/baseline.bin")||!file_ref(path,&scan_ref,0)||!wp(path,"child-result.json")||!file_ref(path,&result_ref,0))goto done;}
  if(!wbytes(L"baseline.bin",&expected,&en))goto done;
  {char scanpath[4096];if(!wp(scanpath,"worker-output/baseline.bin")||!read_bytes(scanpath,&observed,&on))goto done;}
  if(en!=on||memcmp(expected,observed,en)){wf("current-baseline-parity-mismatch");goto done;}
  if(!wrendezvous("compared")||!used_outputs()||!evidence_recheck()||!raw_target_id(&after)||!wr_identity_equal(&before,&after)||!anchor()||!mutate(owner,"windows-native-planned-title"))goto done;
  if(!wfile("prepared.json","{\"operation\":\"title-only\",\"product_admission\":false}\n",strlen("{\"operation\":\"title-only\",\"product_admission\":false}\n")))goto done;
  if(!wrendezvous("mutation-held")||!used_outputs()||!evidence_recheck()||!raw_target_id(&after)||!wr_identity_equal(&before,&after)||!anchor())goto done;commit_requested=1;strcpy(wphase,"sdk-finish");finish_status=exr_library_migration_finish(owner,1,&e);strcpy(wphase,"after-finish");sdk_status=finish_status;if(finish_status!=EXR_OK){wf("sdk-commit");goto done;}
 }else{if(!mutate(owner,"uncommitted-windows-native-title")||!wrendezvous("mutation-held"))goto done;strcpy(wphase,"sdk-finish");finish_status=exr_library_migration_finish(owner,0,&e);strcpy(wphase,"after-finish");sdk_status=finish_status;}
 if(!wrendezvous("owner-finished"))goto done;exr_library_close(owner);owner=NULL;
 if(!raw_target_id(&after)||!wr_identity_equal(&before,&after)||!anchor()||(commit_requested&&(!used_outputs()||!evidence_recheck())))goto done;
 if(commit_requested&&!wfile("ack.json","{\"actual_sdk_commit\":0,\"product_admission\":false}\n",strlen("{\"actual_sdk_commit\":0,\"product_admission\":false}\n")))goto done;
 if(!wrendezvous("owner-closed")||!anchor()||!raw_target_id(&after)||!wr_identity_equal(&before,&after)||(commit_requested&&(!used_outputs()||!evidence_recheck())))goto done;ok=1;
 done:if(owner){if(finish_status==-1)finish_status=exr_library_migration_finish(owner,0,&e);exr_library_close(owner);}free(expected);free(observed);return ok&&!failed;}
static int private_child(unsigned slot,HANDLE lease,HANDLE go,const WCHAR *output,const char *kind){char token[32];DWORD n;exr_library *owner=NULL;exr_error e={0};int ok=0;
 if(!child_envelope(slot,lease,output,kind,0)||!raw_target_id(&child_target_identity))goto done;
 if(!strcmp(mode,"prepin-child")&&!wrendezvous("child-before-pin"))goto done;
 if(!ReadFile(go,token,32,&n,NULL)||n!=32||memcmp(token,wn,32)){wf("child-owner-go-absent");goto done;}
 if(!child_envelope(slot,lease,output,kind,1)||!wok(wr_recheck(wc,&we)))goto done;{wr_identity now;if(!raw_target_id(&now)||!wr_identity_equal(&now,&child_target_identity)){wf("child-target-changed");goto done;}}
 if(!strcmp(kind,"sdkchild")){target_sdk_open_attempted=1;sdk_status=exr_library_migration_open(target,&owner,&e);if(sdk_status!=EXR_OK){wf("child-sdk-open");goto done;}}
 if(!wrendezvous(!strcmp(kind,"holder")?"grandchild-live":"child-live")||!child_envelope(slot,lease,output,kind,1))goto done;
 if(!strcmp(kind,"scanner")){
  sqlite3 *reader=NULL,*check=NULL;lm_sb b,other;char output_utf8[12288];const char *saved_root=root;int valid=0;
  lm_sb_init(&b);lm_sb_init(&other);
  if(!WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,output,-1,output_utf8,sizeof(output_utf8),NULL,NULL)){wf("scanner-output-utf8");goto scan_done;}
  root=output_utf8;snprintf(unused_catalog,sizeof(unused_catalog),"%s/catalog.unused",root);catalog=unused_catalog;snprintf(baseline,sizeof(baseline),"%s/baseline.bin",root);snprintf(clonepath,sizeof(clonepath),"%s/clone.sqlite",root);snprintf(intent,sizeof(intent),"%s/intent.json",root);snprintf(decision,sizeof(decision),"%s/decision.json",root);snprintf(mutexpath,sizeof(mutexpath),"%s/migration.mutex",root);snprintf(custody,sizeof(custody),"%s/custody.txt",root);
  if(!namespace_check()||!open_db(target,0,&reader)||!execsql(reader,"BEGIN")||!canonical(reader,&b,0)||!tx(reader,0)||!backup_clone(reader)||!tx(reader,0))goto scan_done;
  if(!open_db(clonepath,0,&check)||!execsql(check,"BEGIN")||!canonical(check,&other,0)||b.n!=other.n||memcmp(b.p,other.p,b.n)){wf("scanner-copy-parity");goto scan_done;}
  if(!close_db(&check)||!close_db(&reader)||!sdk_clone_check()||!write_new(baseline,b.p,b.n))goto scan_done;valid=1;
 scan_done:close_db(&check);close_db(&reader);lm_sb_free(&b);lm_sb_free(&other);root=saved_root;if(!valid)goto done;
 }
 if(owner){finish_status=exr_library_migration_finish(owner,0,&e);exr_library_close(owner);owner=NULL;if(finish_status!=EXR_OK){wf("child-sdk-finish");goto done;}}
 {lm_sb result;lm_sb_init(&result);lm_sb_fmt(&result,"{\"format\":\"WRN-child-1\",\"kind\":\"%s\",\"nonce\":\"%s\",\"root\":\"%s\",\"producer\":\"%s\",\"request_sha256\":\"%s\",\"pid\":%lu,\"sdk_status\":%d,\"finish_status\":%d,\"complete\":true}\n",kind,wn,root_id,producer,request_sha,GetCurrentProcessId(),sdk_status,finish_status);if(result.oom||!wfile("child-result.json",result.p,result.n)){lm_sb_free(&result);goto done;}lm_sb_free(&result);}ok=1;
 done:if(owner){finish_status=exr_library_migration_finish(owner,0,&e);exr_library_close(owner);}CloseHandle(go);
 /* Lease retained through report flush and process exit, never unlocked. */
 (void)lease;return ok&&!failed;}
static int relay_child(unsigned slot,HANDLE lease,HANDLE go,const WCHAR *output){HANDLE rd=NULL,wr=NULL,list[3];SECURITY_ATTRIBUTES sa={sizeof(sa),NULL,TRUE};wr_process grand={0};WCHAR command[16384];char token[32];DWORD n;int ok=0;
 if(!child_envelope(slot,lease,output,"holder",0))goto done;
 if(!ReadFile(go,token,32,&n,NULL)||n!=32||memcmp(token,wn,32)){wf("relay-go-absent");goto done;}
 if(!child_envelope(slot,lease,output,"holder",0)||!CreatePipe(&rd,&wr,&sa,0)||!SetHandleInformation(wr,HANDLE_FLAG_INHERIT,0)){wf("relay-control");goto done;}
 swprintf(command,16384,L"\"%ls\" hold-child \"%ls\" %hs %llu %llu \"%ls\" 0",self_exe,wroot,wn,(unsigned long long)(uintptr_t)lease,(unsigned long long)(uintptr_t)rd,output);
 list[0]=lease;list[1]=rd;list[2]=GetStdHandle(STD_OUTPUT_HANDLE);
 if(!wr_spawn(job_handle,self_exe,command,list,3,rd,list[2],0,&grand,&we)){wok(0);goto done;}
 if(!WriteFile(wr,wn,32,&n,NULL)||n!=32){wf("relay-go-write");goto done;}
 /* Intentional parent exit under the independently owned job. Closing a process
  * handle is not termination; the supervisor owns/reaps the still-live job. */
 CloseHandle(grand.thread);CloseHandle(grand.process);memset(&grand,0,sizeof(grand));ok=1;
 done:if(!ok&&grand.process){wr_terminate(&grand,&we);wr_process_close(&grand);}if(rd)CloseHandle(rd);if(wr)CloseHandle(wr);CloseHandle(go);return ok&&!failed;}
static int launch_child(const char *variant){HANDLE lease=INVALID_HANDLE_VALUE,input=NULL,output=NULL,go_write=NULL;HANDLE list[4];SECURITY_ATTRIBUTES sa={sizeof(sa),NULL,TRUE};wr_process child={0};WCHAR outpath[WR_PATH],command[16384],logleaf[64];DWORD n,status;int ok=0;const char *kind=!strcmp(variant,"wrong-kind")?"unknown":!strcmp(variant,"scanner")?"scanner":!strcmp(variant,"descendant")?"holder":"sdkchild";wr_identity created_output;HANDLE output_dir=INVALID_HANDLE_VALUE;
 if(!anchor()||!slots_free()||!wr_join(wc,L"worker-output",outpath,&we))goto done;
 output_dir=wr_directory_new(wc,L"worker-output",&created_output,&we);if(output_dir==INVALID_HANDLE_VALUE){wok(0);goto done;}
 lease=take_slot(0,kind,outpath,&created_output,!strcmp(variant,"wrong-nonce")?"nonce":!strcmp(variant,"wrong-producer")?"producer":!strcmp(variant,"wrong-output")?"output":"none");if(lease==INVALID_HANDLE_VALUE)goto done;CloseHandle(output_dir);output_dir=INVALID_HANDLE_VALUE;
 if(!CreatePipe(&input,&go_write,&sa,0)||!SetHandleInformation(go_write,HANDLE_FLAG_INHERIT,0)){wf("go-pipe");goto done;}
 swprintf(logleaf,64,L"worker-log.txt");output=wr_open(wc,logleaf,GENERIC_WRITE,FILE_SHARE_READ,1,&we);if(output==INVALID_HANDLE_VALUE){wok(0);goto done;}
 swprintf(command,16384,L"\"%ls\" %hs \"%ls\" %hs %llu %llu \"%ls\" %llu",self_exe,!strcmp(kind,"scanner")?"scan-child":!strcmp(kind,"holder")?"relay-child":!strcmp(variant,"prepin")?"prepin-child":"child",wroot,wn,(unsigned long long)(uintptr_t)lease,(unsigned long long)(uintptr_t)input,outpath,(unsigned long long)(uintptr_t)(!strcmp(kind,"holder")?job_handle:NULL));
 list[0]=lease;list[1]=input;list[2]=output;list[3]=job_handle;
 if(!strcmp(variant,"request-pause")&&!wrendezvous("request-published"))goto done;
 if(!wr_spawn(job_handle,self_exe,command,list,!strcmp(kind,"holder")?4:3,input,output,!strcmp(variant,"assign-fail"),&child,&we)){wok(0);goto done;}contained=1;
 CloseHandle(input);input=NULL;CloseHandle(lease);lease=INVALID_HANDLE_VALUE;
 if(!strcmp(variant,"spawn-gap")){CloseHandle(go_write);go_write=NULL;}
 if(!wrendezvous("child-spawned"))goto done;
 if(go_write&&(!WriteFile(go_write,wn,32,&n,NULL)||n!=32)){lm_sb_fmt(&telemetry,",\"go_native_error\":%lu",GetLastError());CloseHandle(go_write);go_write=NULL;}
 if(!wok(wr_wait(&child,(DWORD)(deadline>GetTickCount64()?deadline-GetTickCount64():0),&status,&we)))goto done;worker_waited=1;
 if(status){wf("child-nonzero");goto done;}
 if(!wrendezvous("child-waited"))goto done;
 if(!anchor()||!slots_free())goto done;
 {char *bytes=NULL,*req=NULL;size_t size=0,rn=0;jv *result=NULL;char digest[65];uint64_t pid=0;
 if(!wbytes(L"child-result.json",&bytes,&size)||!wbytes(L"use-0.json",&req,&rn)){free(bytes);free(req);goto done;}lm_sha_bytes(req,rn,digest);{wr_identity now;if(!wmetadata(L"use-0.json",&now)||!wr_identity_equal(&now,&parent_request_identity)||strcmp(digest,parent_request_sha)){free(bytes);free(req);wf("parent-request-changed");goto done;}}result=wparse(bytes,size);
 if(!result||result->t!=J_OBJ||result->n!=10||strcmp(wstr(result,"format"),"WRN-child-1")||strcmp(wstr(result,"kind"),kind)||strcmp(wstr(result,"nonce"),wn)||strcmp(wstr(result,"root"),root_id)||strcmp(wstr(result,"producer"),producer)||strcmp(wstr(result,"request_sha256"),digest)||!lm_json_uint(lm_get(result,"pid"),&pid)||pid!=child.pid||!lm_get(result,"complete")||lm_get(result,"complete")->t!=J_BOOL||!lm_get(result,"complete")->b){wf("child-result-binding");}if(!failed){const jv *ack=lm_get(result,"finish_status"),*status_value=lm_get(result,"sdk_status");double expected_finish=!strcmp(kind,"sdkchild")?0:-1;if(!ack||ack->t!=J_NUM||ack->num!=expected_finish||!status_value||status_value->t!=J_NUM||status_value->num!=expected_finish)wf("child-result-sdk-status");}free(bytes);free(req);lm_json_free(result);if(failed)goto done;}
 ok=1;
 done:if(!ok)lm_sb_fmt(&telemetry,",\"original_failure_native\":%lu",we.native);if(output_dir!=INVALID_HANDLE_VALUE)CloseHandle(output_dir);if(!ok&&child.process)wr_terminate(&child,&we);wr_process_close(&child);if(input)CloseHandle(input);if(go_write)CloseHandle(go_write);if(output&&output!=INVALID_HANDLE_VALUE){FlushFileBuffers(output);CloseHandle(output);}if(lease!=INVALID_HANDLE_VALUE)CloseHandle(lease);return ok&&!failed;}
static int basic(const char *op,const char *arg){HANDLE h=INVALID_HANDLE_VALUE,r=INVALID_HANDLE_VALUE;WCHAR leaf[WR_PATH];wr_identity a,b;void *data=NULL;size_t n=0;int ok=0;const char payload[]="canonical-native-record\n";
 if(!strcmp(op,"slots"))return anchor()&&slots_free()&&used_outputs();
 if(!strcmp(op,"completion")){if(!anchor()||!slots_free()||!used_outputs())return 0;return wf("restart-has-no-actual-wait-proof");}
 if(!strcmp(op,"token")){WCHAR stage_name[96];if(!wok(wr_utf8(arg,leaf,&we)))return 0;swprintf(stage_name,96,L"_token-%hs-%lu",wn,GetCurrentProcessId());if(!wok(wr_write_new(wc,stage_name,wn,32,1,&h,&we)))goto done;ok=wok(wr_rename_new(wc,h,leaf,&we));goto done;}
 if(!strcmp(op,"scan"))return native_scan(arg);
 if(!anchor())goto done;
 if(!strcmp(op,"complete-failed")){if(!wok(wr_write_new(wc,L"complete.json","{\"looks_complete\":true}\n",sizeof("{\"looks_complete\":true}\n")-1,0,NULL,&we)))goto done;r=wr_open(wc,L"complete.json",GENERIC_READ,FILE_SHARE_READ,0,&we);if(r==INVALID_HANDLE_VALUE){wok(0);goto done;}if(wr_flush(r,&we)){wf("readonly-flush-unexpected-success");goto done;}lm_sb_fmt(&telemetry,",\"native_refusal\":%lu",we.native);if(we.native!=ERROR_ACCESS_DENIED){wf("flush-native-code");goto done;}wf("complete-record-flush-unverified");goto done;}
 if(!strcmp(op,"write-denied")){DWORD written;h=wr_open(wc,L"anchor.json",GENERIC_READ,FILE_SHARE_READ,0,&we);if(h==INVALID_HANDLE_VALUE){wok(0);goto done;}if(WriteFile(h,"x",1,&written,NULL)){wf("readonly-write-succeeded");goto done;}we.native=GetLastError();lm_sb_fmt(&telemetry,",\"native_refusal\":%lu",we.native);ok=we.native==ERROR_ACCESS_DENIED;if(!ok)wf("write-native-code");goto done;}
 if(!strcmp(op,"identity")){wr_identity_text(&wc->root,root_id);ok=wr_recheck(wc,&we);goto done;}
 if(!strcmp(op,"read")){if(!wok(wr_utf8(arg,leaf,&we)))goto done;r=wr_open(wc,leaf,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,0,&we);if(r==INVALID_HANDLE_VALUE){wok(0);goto done;}ok=wok(wr_read(r,&data,&n,WR_RECORD_MAX,&we));goto done;}
 if(!strcmp(op,"write")){if(!wok(wr_utf8(arg,leaf,&we)))goto done;ok=wok(wr_write_new(wc,leaf,payload,sizeof(payload)-1,1,NULL,&we));goto done;}
 if(!strcmp(op,"partial")){if(!wok(wr_write_new(wc,L"partial.json","{\"state\":",9,0,&h,&we)))goto done;if(!wrendezvous("partial-written"))goto done;wf("partial-record-not-authority");goto done;}
 if(!strcmp(op,"partial-check")){char *p=NULL;jv *j;lm_err e={{0},{0}};if(!wbytes(L"partial.json",&p,&n))goto done;j=wparse(p,n);free(p);lm_json_free(j);if(!j){wf("partial-record-refused");goto done;}wf("unexpected-complete-record");goto done;}
 if(!wok(wr_write_new(wc,L"source.bin",payload,sizeof(payload)-1,1,&h,&we)))goto done;if(!wok(wr_identity_get(h,0,&a,&we)))goto done;
 if(!strcmp(op,"flush-denied")){CloseHandle(h);h=INVALID_HANDLE_VALUE;r=wr_open(wc,L"source.bin",GENERIC_READ,FILE_SHARE_READ,0,&we);if(r==INVALID_HANDLE_VALUE){wok(0);goto done;}if(wr_flush(r,&we)){wf("readonly-flush-unexpected-success");goto done;}lm_sb_fmt(&telemetry,",\"native_refusal\":%lu",we.native);ok=we.native==ERROR_ACCESS_DENIED; if(!ok)wf("flush-native-code");goto done;}
 if(!strcmp(op,"rename")){ok=wok(wr_rename_new(wc,h,L"published.bin",&we));if(!ok)goto done;if(!wok(wr_identity_get(h,0,&b,&we))||!wr_identity_equal(&a,&b)){wf("rename-identity");goto done;}if(!wrendezvous("renamed"))goto done;goto done;}
 if(!strcmp(op,"rename-paused")){CloseHandle(h);h=INVALID_HANDLE_VALUE;if(!wrendezvous("before-rename"))goto done;h=wr_open(wc,L"source.bin",GENERIC_READ|GENERIC_WRITE|DELETE,FILE_SHARE_READ,0,&we);if(h==INVALID_HANDLE_VALUE){wok(0);goto done;}if(!wr_identity_get(h,0,&b,&we)||!wr_identity_equal(&a,&b)){wf("rename-source-replaced");goto done;}ok=wok(wr_rename_new(wc,h,L"published.bin",&we));goto done;}
 if(!strcmp(op,"postflush")){if(!wrendezvous("file-flushed"))goto done;ok=1;goto done;}
 if(!strcmp(op,"directory-flush")){BOOL result=FlushFileBuffers(wc->directory);DWORD code=result?0:GetLastError();lm_sb_fmt(&telemetry,",\"directory_flush_result\":%s,\"directory_flush_native\":%lu",result?"true":"false",code);ok=1;goto done;}
 if(!strcmp(op,"parent-pin")){if(!wrendezvous("parent-pinned"))goto done;ok=wok(wr_write_new(wc,L"confined.bin",payload,sizeof(payload)-1,1,NULL,&we));goto done;}
 if(!strcmp(op,"write-read")){if(!wok(wr_read(h,&data,&n,WR_RECORD_MAX,&we)))goto done;ok=n==sizeof(payload)-1&&!memcmp(data,payload,n);if(!ok)wf("write-read-mismatch");goto done;}
 wf("unknown-native-mode");
 done:if(h!=INVALID_HANDLE_VALUE)CloseHandle(h);if(r!=INVALID_HANDLE_VALUE)CloseHandle(r);free(data);return ok&&!failed;}
static int native_main(int argc,char **argv){const char *op,*arg="none";int ok=0;HANDLE outer=INVALID_HANDLE_VALUE;WCHAR targetw[WR_PATH];char target_utf8[12288];
 if(!getenv("GITHUB_ACTIONS")||strcmp(getenv("GITHUB_ACTIONS"),"true")||argc<4)return 2;op=argv[1];mode=op;root=argv[2];if(strlen(argv[3])!=32||strspn(argv[3],"0123456789abcdef")!=32)return 2;strcpy(wn,argv[3]);nonce=wn;deadline=GetTickCount64()+115000;
 if(sqlite3_config(SQLITE_CONFIG_LOG,os_log,NULL)!=SQLITE_OK)return 2;
 if(SQLITE_VERSION_NUMBER!=3054000||sqlite3_libversion_number()!=3054000||strcmp(SQLITE_SOURCE_ID,sqlite3_sourceid())||strcmp(exr_version(),"3.42.0")||exr_abi_version()!=1)return 2;
 wc=calloc(1,sizeof(*wc));if(!wc)return 2;lm_sb_init(&telemetry);lm_sb_init(&os_events);fault="none";lm_binary_stdout();if(!wr_utf8(root,wroot,&we)||!wexe()||!wok(wr_prepare(wc,wroot,!strcmp(op,"init"),&we)))goto done;
 {PSECURITY_DESCRIPTOR descriptor=NULL;LPWSTR sddl=NULL;char text[4096];DWORD error=GetSecurityInfo(wc->directory,SE_FILE_OBJECT,OWNER_SECURITY_INFORMATION|DACL_SECURITY_INFORMATION,NULL,NULL,NULL,NULL,&descriptor);
 if(error||!ConvertSecurityDescriptorToStringSecurityDescriptorW(descriptor,SDDL_REVISION_1,OWNER_SECURITY_INFORMATION|DACL_SECURITY_INFORMATION,&sddl,NULL)||!WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,sddl,-1,text,sizeof(text),NULL,NULL)){if(descriptor)LocalFree(descriptor);if(sddl)LocalFree(sddl);wf("root-acl-evidence");goto done;}lm_sb_str(&telemetry,",\"actual_root_sddl\":");lm_sb_json(&telemetry,text,strlen(text));LocalFree(descriptor);LocalFree(sddl);}
 if(!ancestor_observations())goto done;
 if(!wr_join(wc,L"library.sqlite",targetw,&we)||!WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,targetw,-1,target_utf8,sizeof(target_utf8),NULL,NULL)){wf("target-utf8");goto done;}target=target_utf8;
 if(!strcmp(op,"init")){ok=initialize();goto done;}
 if(!strcmp(op,"child")||!strcmp(op,"scan-child")||!strcmp(op,"relay-child")||!strcmp(op,"hold-child")||!strcmp(op,"prepin-child")){HANDLE lease,go;WCHAR output[WR_PATH];if(argc!=8){wf("child-arity");goto done;}lease=(HANDLE)(uintptr_t)_strtoui64(argv[4],NULL,10);go=(HANDLE)(uintptr_t)_strtoui64(argv[5],NULL,10);if(!wr_utf8(argv[6],output,&we)){wok(0);goto done;}job_handle=(HANDLE)(uintptr_t)_strtoui64(argv[7],NULL,10);if(!strcmp(op,"relay-child"))ok=relay_child(0,lease,go,output);else ok=private_child(0,lease,go,output,!strcmp(op,"scan-child")?"scanner":!strcmp(op,"hold-child")?"holder":"sdkchild");goto done;}
 if(!strcmp(op,"mkdir")){wr_identity id;HANDLE h;WCHAR leaf[WR_PATH];if(argc<5||!wr_utf8(argv[4],leaf,&we)){wf("mkdir-argument");goto done;}h=wr_directory_new(wc,leaf,&id,&we);if(h==INVALID_HANDLE_VALUE){wok(0);goto done;}CloseHandle(h);ok=1;goto done;}
 if(!strcmp(op,"copy")){char *p=NULL;size_t n=0;lm_mirror_file f;lm_err e={{0},{0}};if(argc!=7){wf("copy-arity");goto done;}if(!lm_mirror_snapshot(argv[6],1,WR_RECORD_MAX,&f,&p,&n,&e)||!f.present){wf("copy-input");free(p);goto done;}ok=wfile(argv[4],p,n);free(p);goto done;}
 if(argc>4)arg=argv[4];if(argc>5)job_handle=(HANDLE)(uintptr_t)_strtoui64(argv[5],NULL,10);
 if(strcmp(op,"token")&&strcmp(op,"scan")){outer=wr_open(wc,L"outer.lock",GENERIC_READ|GENERIC_WRITE,0,0,&we);if(outer==INVALID_HANDLE_VALUE){wok(0);goto done;}}
 if(!strcmp(op,"owner"))ok=sdk_owner(arg);
 else if(!strcmp(op,"launch")){if(!job_handle){wf("owned-job-required");goto done;}ok=launch_child(arg);}
 else ok=basic(op,arg);
 done:lm_sb_str(&telemetry,",\"sqlite_events\":[");if(os_events.p)lm_sb_add(&telemetry,os_events.p,os_events.n);lm_sb_str(&telemetry,"]");lm_sb_free(&os_events);if(wr_cleanup_uncertain())wf("cleanup-unconfirmed");lm_sb_fmt(&telemetry,",\"directory_create_ntstatus\":%ld,\"directory_create_information\":%llu",we.ntstatus,(unsigned long long)we.io_information);lm_sb_fmt(&telemetry,",\"rename_attempted\":%s,\"rename_ntstatus\":%ld,\"rename_io_status\":%ld,\"rename_information\":%llu",we.rename_attempted?"true":"false",we.rename_ntstatus,we.rename_io_status,(unsigned long long)we.rename_information);lm_sb_fmt(&telemetry,",\"cleanup_unconfirmed\":%s,\"cleanup_native\":%lu,\"cleanup_wait_result\":%lu",(we.cleanup_unconfirmed||wr_cleanup_uncertain())?"true":"false",we.cleanup_native,we.wait_result);if(outer!=INVALID_HANDLE_VALUE)CloseHandle(outer);if(wc){wr_close(wc);free(wc);}printf("{\"passed\":%s,\"reason\":\"%s\",\"native_error\":%lu,\"phase\":\"%s\",\"source_producer\":\"%s\",\"root_id\":\"%s\",\"target_sdk_open_attempted\":%s,\"sdk_status\":%d,\"finish_status\":%d,\"commit_requested\":%s,\"worker_waited\":%s,\"contained\":%s,\"directory_fsync_equivalent\":false,\"physical_power_loss_qualified\":false,\"product_admission\":false,\"full_p0_acceptance\":false%s}\n",ok&&!failed?"true":"false",reason,we.native,wphase,producer,root_id,target_sdk_open_attempted?"true":"false",sdk_status,finish_status,commit_requested?"true":"false",worker_waited?"true":"false",contained?"true":"false",telemetry.p?telemetry.p:"");fflush(stdout);lm_sb_free(&telemetry);return ok&&!failed?0:3;}

/* Native Unicode arguments are converted strictly; no process-codepage assumption. */
int wmain(int argc,wchar_t **wide){char **args=NULL;size_t total=0;int i,result=2;if(argc<1||argc>16)return 2;args=calloc((size_t)argc+1,sizeof(*args));if(!args)return 2;
 for(i=0;i<argc;i++){int size=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide[i],-1,NULL,0,NULL,NULL);if(size<=0||size>16384||total+(size_t)size>65536)goto done;total+=(size_t)size;args[i]=malloc((size_t)size);if(!args[i]||!WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide[i],-1,args[i],size,NULL,NULL))goto done;}
 result=native_main(argc,args);
 done:for(i=0;i<argc;i++)free(args[i]);free(args);return result;}
