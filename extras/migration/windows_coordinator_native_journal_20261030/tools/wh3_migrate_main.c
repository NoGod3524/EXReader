/* SPDX-License-Identifier: MIT */
#include <exr_wh3_win.h>
#include "../../src/lm.h"
#include "wh3_transform.h"
#include "wh3_build.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#include <wincrypt.h>
/* This version has one synchronous owner, and launches no importer workers.
   All private SDK owners and sources close before publishing any member. */
#pragma pack(push,1)
typedef struct {wh3w_identity id;uint64_t size;char sha[65];} c02_file;
typedef struct {
 char magic[8];wh_binding binding;wh_gates gates;
 wchar_t pack[MAX_PATH],library[MAX_PATH];
 wchar_t stages[2][64],retained[2][64];char token[49];
 c02_file original,mirror,pack_file;
 wh3w_identity staged[2];uint32_t mirror_present,allow_partial;
} c02_input;
typedef struct {char magic[8],input_sha[65];c02_file files[2];} c02_prepared;
#pragma pack(pop)
typedef struct {
 wchar_t requested_library[MAX_PATH];
 c02_input input;c02_prepared prepared;wh3wr_registration *registration;
 wh3w_store *journal;void *cap;wh3_tip tip;wh3w_controls controls;
 HANDLE pack,pack_parents[128],original,mirror,stages[2];size_t parent_count;
 wchar_t paths[2][MAX_PATH],retained[2][MAX_PATH],mirror_path[MAX_PATH];
 char library_utf8[4*MAX_PATH],pack_utf8[4*MAX_PATH],stage_utf8[4*MAX_PATH],mirror_utf8[4*MAX_PATH],old_mirror_utf8[4*MAX_PATH];
 int recovered,has_prepared,publish_intent,published,aborted;unsigned member;const char *operation;
 char lines[EXR_WH_MAX_JOURNAL][EXR_WH_LINE_MAX];const char *line_ptrs[EXR_WH_MAX_JOURNAL];size_t line_count;
} c02_owner;
static int c02_physical(HANDLE,char [4*MAX_PATH]);
static int c02_quiet_handle(HANDLE);
static void c02_close(HANDLE *h){if(*h&&*h!=INVALID_HANDLE_VALUE)CloseHandle(*h);*h=INVALID_HANDLE_VALUE;}
static int c02_identity(HANDLE h,wh3w_identity *id) {
 FILE_ID_INFO info;BY_HANDLE_FILE_INFORMATION basic;FILE_ATTRIBUTE_TAG_INFO tag;
 if(!GetFileInformationByHandle(h,&basic)||basic.nNumberOfLinks!=1||
    !GetFileInformationByHandleEx(h,FileAttributeTagInfo,&tag,sizeof(tag))||
    (tag.FileAttributes&(FILE_ATTRIBUTE_DIRECTORY|FILE_ATTRIBUTE_REPARSE_POINT))||
    !GetFileInformationByHandleEx(h,FileIdInfo,&info,sizeof(info)))return 0;
 id->volume=info.VolumeSerialNumber;id->file=info.FileId;return 1;
}
static int c02_same(const wh3w_identity *a,const wh3w_identity *b){return a->volume==b->volume&&!memcmp(&a->file,&b->file,16);}
static int c02_hash(HANDLE h,c02_file *out) {
 unsigned char bytes[65536];LARGE_INTEGER size,zero;DWORD n;lm_sha sha;uint64_t total=0;wh3w_identity after;
 zero.QuadPart=0;memset(out,0,sizeof(*out));
 if(!c02_identity(h,&out->id)||!GetFileSizeEx(h,&size)||size.QuadPart<0||!SetFilePointerEx(h,zero,NULL,FILE_BEGIN))return 0;
 lm_sha_init(&sha);
 for(;;){if(!ReadFile(h,bytes,sizeof(bytes),&n,NULL))return 0;if(!n)break;
  if(UINT64_MAX-total<n)return 0;total+=n;lm_sha_add(&sha,bytes,n);}
 if(total!=(uint64_t)size.QuadPart||!c02_identity(h,&after)||!c02_same(&after,&out->id))return 0;
 out->size=total;lm_sha_hex(&sha,out->sha);return 1;
}
static int c02_equal(const c02_file *a,const c02_file *b){return c02_same(&a->id,&b->id)&&a->size==b->size&&!memcmp(a->sha,b->sha,65);}
static HANDLE c02_open(const wchar_t *path,DWORD access,DWORD sharing,DWORD creation) {
 HANDLE h=CreateFileW(path,access,sharing,NULL,creation,FILE_FLAG_OPEN_REPARSE_POINT,NULL);wh3w_identity id;
 if(h!=INVALID_HANDLE_VALUE&&!c02_identity(h,&id))c02_close(&h);
 return h;
}
static int c02_file_matches(const wchar_t *path,const c02_file *file) {
 HANDLE h=c02_open(path,GENERIC_READ,FILE_SHARE_READ,OPEN_EXISTING);c02_file actual;int ok=0;
 if(h!=INVALID_HANDLE_VALUE)ok=c02_hash(h,&actual)&&c02_equal(&actual,file);c02_close(&h);return ok;
}
static int c02_id_matches(const wchar_t *path,const wh3w_identity *id) {
 HANDLE h=c02_open(path,FILE_READ_ATTRIBUTES,FILE_SHARE_READ|FILE_SHARE_WRITE,OPEN_EXISTING);wh3w_identity actual;int ok=0;
 if(h!=INVALID_HANDLE_VALUE)ok=c02_identity(h,&actual)&&c02_same(&actual,id);c02_close(&h);return ok;
}
static int c02_absent(const wchar_t *path) {
 HANDLE h=CreateFileW(path,FILE_READ_ATTRIBUTES,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,NULL);
 if(h!=INVALID_HANDLE_VALUE){CloseHandle(h);return 0;}return GetLastError()==ERROR_FILE_NOT_FOUND;
}
static int c02_wide_text(const wchar_t *text,size_t cap,int leaf) {
 size_t n=0,k;while(n<cap&&text[n])n++;if(!n||n==cap)return 0;
 for(k=n+1;k<cap;k++)if(text[k])return 0;
 if(leaf){if(text[n-1]==L'.'||text[n-1]==L' ')return 0;for(k=0;k<n;k++)if(text[k]<32||wcschr(L"\\/:*?\"<>|",text[k]))return 0;}
 return 1;
}
static int c02_hex(const char *text,size_t n) {
 size_t k;for(k=0;k<n;k++)if(!((text[k]>='0'&&text[k]<='9')||(text[k]>='a'&&text[k]<='f')))return 0;return text[n]==0;
}
static void c02_id_text(const wh3w_identity *id,char out[49]) {
 unsigned char bytes[24];static const char hex[]="0123456789abcdef";unsigned k;
 for(k=0;k<8;k++)bytes[k]=(unsigned char)(id->volume>>(8*k));memcpy(bytes+8,&id->file,16);
 for(k=0;k<24;k++){out[2*k]=hex[bytes[k]>>4];out[2*k+1]=hex[bytes[k]&15];}out[48]=0;
}
static int c02_utf8(const wchar_t *path,char out[4*MAX_PATH]) {
 return WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,path,-1,out,4*MAX_PATH,NULL,NULL)>0;
}
static int c02_absolute(const wchar_t *input,wchar_t out[MAX_PATH]) {
 DWORD n;memset(out,0,MAX_PATH*sizeof(wchar_t));n=GetFullPathNameW(input,MAX_PATH,out,NULL);
 return n>3&&n<MAX_PATH&&out[1]==L':'&&out[2]==L'\\'&&!wcschr(out+2,L':');
}
static int c02_sibling(const wchar_t *library,const wchar_t *leaf,wchar_t out[MAX_PATH]) {
 const wchar_t *slash=wcsrchr(library,L'\\');size_t n;if(!slash)return 0;n=(size_t)(slash-library)+1;
 if(n+wcslen(leaf)>=MAX_PATH)return 0;memset(out,0,MAX_PATH*sizeof(wchar_t));
 memcpy(out,library,n*sizeof(wchar_t));wcscpy_s(out+n,MAX_PATH-n,leaf);return 1;
}
static int c02_paths(c02_owner *o) {
 size_t k;
 if(wcslen(o->input.library)+16>=MAX_PATH)return 0;
 swprintf_s(o->mirror_path,MAX_PATH,L"%ls.legacy-map.json",o->input.library);
 for(k=0;k<2;k++)if(!c02_sibling(o->input.library,o->input.stages[k],o->paths[k])||
   !c02_sibling(o->input.library,o->input.retained[k],o->retained[k]))return 0;
 return c02_utf8(o->input.library,o->library_utf8)&&c02_utf8(o->input.pack,o->pack_utf8)&&
 c02_utf8(o->paths[0],o->stage_utf8)&&c02_utf8(o->paths[1],o->mirror_utf8)&&c02_utf8(o->mirror_path,o->old_mirror_utf8);
}
static int c02_pack_pin(c02_owner *o) {
 wchar_t path[MAX_PATH];size_t k,n=wcslen(o->input.pack);FILE_ATTRIBUTE_TAG_INFO tag;c02_file actual;
 wcscpy_s(path,MAX_PATH,o->input.pack);
 for(k=3;k<n;k++)if(k==3||path[k]==L'\\'){
  HANDLE h;wchar_t saved=path[k];if(o->parent_count>=128)return 0;path[k]=0;
  h=CreateFileW(path,FILE_LIST_DIRECTORY|FILE_READ_ATTRIBUTES,FILE_SHARE_READ,NULL,OPEN_EXISTING,
    FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,NULL);path[k]=saved;
  if(h==INVALID_HANDLE_VALUE)return 0;o->pack_parents[o->parent_count++]=h;
  if(!GetFileInformationByHandleEx(h,FileAttributeTagInfo,&tag,sizeof(tag))||
     !(tag.FileAttributes&FILE_ATTRIBUTE_DIRECTORY)||(tag.FileAttributes&FILE_ATTRIBUTE_REPARSE_POINT))return 0;
 }
 o->pack=c02_open(o->input.pack,GENERIC_READ,FILE_SHARE_READ,OPEN_EXISTING);
 if(o->pack==INVALID_HANDLE_VALUE||!c02_hash(o->pack,&actual))return 0;
 if(o->recovered)return c02_equal(&actual,&o->input.pack_file);
 o->input.pack_file=actual;return 1;
}
static void c02_phase(void *context,unsigned phase) {
 c02_owner *o=context;(void)o;(void)phase;
#ifdef WH3_MIGRATION_TEST_CONTROLS
 const char *want=getenv("EXR_C02_PHASE"),*seq=getenv("EXR_C02_SEQUENCE"),*member=getenv("EXR_C02_MEMBER");
 const char *ready=getenv("EXR_C02_READY"),*resume=getenv("EXR_C02_RESUME");HANDLE a,b;
 if(!want||strtoul(want,NULL,10)!=phase||(seq&&strtoull(seq,NULL,10)!=o->tip.line_count)||
    (member&&strtoul(member,NULL,10)!=o->member)||!ready||!resume)return;
 a=OpenEventA(EVENT_MODIFY_STATE,FALSE,ready);b=OpenEventA(SYNCHRONIZE,FALSE,resume);
 if(!a||!b)ExitProcess(91);
 printf("{\"barrier\":%u,\"sequence\":%llu,\"member\":%u}\n",phase,(unsigned long long)o->tip.line_count,o->member);fflush(stdout);
 if(!SetEvent(a)||WaitForSingleObject(b,120000)!=WAIT_OBJECT_0)ExitProcess(92);
 CloseHandle(a);CloseHandle(b);
#endif
}
static void c02_gates(wh_gates *g) {
 wh_sha256_hex("C02-native-registry-admission-v1",strlen("C02-native-registry-admission-v1"),g->admission);
 wh_sha256_hex("C02-compound-member-publication-v1",strlen("C02-compound-member-publication-v1"),g->publisher);
 wh_sha256_hex("C02-exact-prefix-recovery-v1",strlen("C02-exact-prefix-recovery-v1"),g->recovery);
 wh_sha256_hex("C02-actual-SDK-migration-proof-v1",strlen("C02-actual-SDK-migration-proof-v1"),g->observer);
 wh_sha256_hex("C02-synchronous-owner-v1",strlen("C02-synchronous-owner-v1"),g->fault);
}
static int c02_binding(c02_owner *o) {
 wchar_t executable[MAX_PATH];HANDLE h;DWORD n;c02_file file;wh_binding *b=&o->input.binding;
 n=GetModuleFileNameW(NULL,executable,MAX_PATH);if(!n||n>=MAX_PATH)return 0;
 h=c02_open(executable,GENERIC_READ,FILE_SHARE_READ,OPEN_EXISTING);
 if(h==INVALID_HANDLE_VALUE)return 0;
 if(!c02_hash(h,&file)){CloseHandle(h);return 0;}CloseHandle(h);
 strcpy_s(b->source,sizeof(b->source),WH3_BUILD_SOURCE);strcpy_s(b->run,sizeof(b->run),WH3_BUILD_RUN);
 strcpy_s(b->attempt,sizeof(b->attempt),WH3_BUILD_ATTEMPT);strcpy_s(b->artifact,sizeof(b->artifact),file.sha);
 strcpy_s(b->platform,sizeof(b->platform),"windows-ntfs");strcpy_s(b->sdk,sizeof(b->sdk),"3.42.0-8357eafa");
 strcpy_s(b->provider,sizeof(b->provider),WH3_PROVIDER_SHA);c02_gates(&o->input.gates);return wh_binding_valid(b);
}
static int c02_input_valid(c02_owner *o,const wchar_t *library) {
 c02_input *i=&o->input;wh_gates gates;char manifest[EXR_WH_LINE_MAX];size_t k;
 if(memcmp(i->magic,"C02IN001",8)||!wh_binding_valid(&i->binding)||
    strcmp(i->binding.provider,WH3_PROVIDER_SHA)||strcmp(i->binding.sdk,"3.42.0-8357eafa")||
    strcmp(i->binding.platform,"windows-ntfs")||!c02_hex(i->token,48)||
    !c02_wide_text(i->library,MAX_PATH,0)||!c02_wide_text(i->pack,MAX_PATH,0)||
    wcscmp(library,i->library)||i->mirror_present>1||i->allow_partial>1||
    !c02_hex(i->original.sha,64)||!c02_hex(i->pack_file.sha,64))return 0;
 c02_gates(&gates);if(memcmp(&gates,&i->gates,sizeof(gates))||!wh_manifest(&i->binding,&i->gates,manifest))return 0;
 for(k=0;k<2;k++)if(!c02_wide_text(i->stages[k],64,1)||!c02_wide_text(i->retained[k],64,1))return 0;
 if(i->mirror_present){if(!c02_hex(i->mirror.sha,64))return 0;}
 else{c02_file zero={0};if(memcmp(&zero,&i->mirror,sizeof(zero)))return 0;}
 for(k=0;k<2;k++){
  wchar_t expected[64];
  swprintf_s(expected,64,L"c02-%hs-%u.stage",i->token,(unsigned)k);
  if(wcscmp(expected,i->stages[k]))return 0;
  swprintf_s(expected,64,L"c02-%hs-%u.retained",i->token,(unsigned)k);
  if(wcscmp(expected,i->retained[k]))return 0;
 }
 return c02_paths(o);
}
static int c02_repair_input(void *context,const void *data,size_t size,wh_binding *binding,wh_gates *gates) {
 c02_owner *o=context;if(size!=sizeof(o->input))return 0;
 memcpy(&o->input,data,size);if(!c02_input_valid(o,o->requested_library))return 0;
 *binding=o->input.binding;*gates=o->input.gates;return 1;
}
static int c02_prepared_read(c02_owner *o) {
 size_t size=0,k;char hash[65];
 if(!wh3wr_transaction_read(o->registration,WH3WR_PREPARED,&o->prepared,sizeof(o->prepared),&size)||
    size!=sizeof(o->prepared)||memcmp(o->prepared.magic,"C02OUT01",8))return 0;
 wh_sha256_hex(&o->input,sizeof(o->input),hash);if(memcmp(hash,o->prepared.input_sha,65))return 0;
 for(k=0;k<2;k++)if(!c02_same(&o->prepared.files[k].id,&o->input.staged[k])||
    !c02_hex(o->prepared.files[k].sha,64)||!o->prepared.files[k].size)return 0;
 o->has_prepared=1;return 1;
}
static int c02_create_input(c02_owner *o,const wchar_t *library,const wchar_t *pack,int partial) {
 HCRYPTPROV random=0;unsigned char token[24];unsigned k;static const char hex[]="0123456789abcdef";
 memcpy(o->input.magic,"C02IN001",8);wcscpy_s(o->input.library,MAX_PATH,library);
 wcscpy_s(o->input.pack,MAX_PATH,pack);o->input.allow_partial=(uint32_t)partial;
 o->operation="input-binary-binding";if(!c02_binding(o))return 0;
 o->operation="input-pack-custody";if(!c02_pack_pin(o))return 0;
 o->operation="input-random-token";if(!CryptAcquireContextW(&random,NULL,NULL,PROV_RSA_AES,CRYPT_VERIFYCONTEXT))return 0;
 k=(unsigned)CryptGenRandom(random,sizeof(token),token);CryptReleaseContext(random,0);if(!k)return 0;
 for(k=0;k<24;k++){o->input.token[2*k]=hex[token[k]>>4];o->input.token[2*k+1]=hex[token[k]&15];}
 for(k=0;k<2;k++){
  swprintf_s(o->input.stages[k],64,L"c02-%hs-%u.stage",o->input.token,k);
  swprintf_s(o->input.retained[k],64,L"c02-%hs-%u.retained",o->input.token,k);
 }
 o->operation="input-paths";if(!c02_paths(o))return 0;
 o->operation="input-original";o->original=c02_open(library,GENERIC_READ,FILE_SHARE_READ,OPEN_EXISTING);
 if(o->original==INVALID_HANDLE_VALUE||!c02_hash(o->original,&o->input.original))return 0;
 o->operation="input-mirror";o->mirror=c02_open(o->mirror_path,GENERIC_READ,FILE_SHARE_READ,OPEN_EXISTING);
 if(o->mirror==INVALID_HANDLE_VALUE){if(!c02_absent(o->mirror_path))return 0;}
 else{if(!c02_hash(o->mirror,&o->input.mirror))return 0;o->input.mirror_present=1;}
 o->operation="input-private-objects";
 for(k=0;k<2;k++){
  HANDLE created;
  if(!c02_absent(o->retained[k]))return 0;
  created=c02_open(o->paths[k],GENERIC_READ|GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_WRITE,CREATE_NEW);
  if(created==INVALID_HANDLE_VALUE)return 0;
  if(!c02_identity(created,&o->input.staged[k])||!FlushFileBuffers(created)){CloseHandle(created);return 0;}
  o->stages[k]=ReOpenFile(created,FILE_READ_ATTRIBUTES,FILE_SHARE_READ|FILE_SHARE_WRITE,FILE_FLAG_OPEN_REPARSE_POINT);
  CloseHandle(created);if(o->stages[k]==INVALID_HANDLE_VALUE)return 0;
 }
 o->operation="input-canonical-schema";if(!c02_input_valid(o,library))return 0;
 o->operation="input-durable-record";if(!wh3wr_transaction_write(o->registration,WH3WR_INPUT,&o->input,sizeof(o->input)))return 0;
 c02_phase(o,900);return 1;
}
static int c02_original_state(c02_owner *o) {
 HANDLE h=c02_open(o->input.library,FILE_READ_ATTRIBUTES,FILE_SHARE_READ|FILE_SHARE_WRITE,OPEN_EXISTING);
 int quiet=h!=INVALID_HANDLE_VALUE&&c02_quiet_handle(h);c02_close(&h);if(!quiet)return 0;
 if(!c02_file_matches(o->input.library,&o->input.original)||
    !(o->input.mirror_present?c02_file_matches(o->mirror_path,&o->input.mirror):c02_absent(o->mirror_path)))return 0;
 return c02_id_matches(o->paths[0],&o->input.staged[0])&&c02_id_matches(o->paths[1],&o->input.staged[1])&&
    c02_absent(o->retained[0])&&c02_absent(o->retained[1]);
}
static int c02_published_state(c02_owner *o) {
 if(!o->has_prepared||!c02_file_matches(o->input.library,&o->prepared.files[0])||
    !c02_file_matches(o->mirror_path,&o->prepared.files[1])||
    !c02_file_matches(o->retained[0],&o->input.original)||!c02_absent(o->paths[0])||!c02_absent(o->paths[1])||
    !(o->input.mirror_present?c02_file_matches(o->retained[1],&o->input.mirror):c02_absent(o->retained[1])))return 0;
  HANDLE image=c02_open(o->input.library,FILE_READ_ATTRIBUTES,FILE_SHARE_READ|FILE_SHARE_WRITE,OPEN_EXISTING);
 HANDLE mirror=c02_open(o->mirror_path,FILE_READ_ATTRIBUTES,FILE_SHARE_READ|FILE_SHARE_WRITE,OPEN_EXISTING);
 wh3w_identity image_id,mirror_id;
 int physical=image!=INVALID_HANDLE_VALUE&&mirror!=INVALID_HANDLE_VALUE&&
   c02_identity(image,&image_id)&&c02_same(&image_id,&o->prepared.files[0].id)&&
   c02_identity(mirror,&mirror_id)&&c02_same(&mirror_id,&o->prepared.files[1].id)&&
   c02_physical(image,o->library_utf8)&&c02_physical(mirror,o->old_mirror_utf8);
 c02_close(&image);c02_close(&mirror);if(!physical)return 0;
 if(!wh3t_verify(o->pack,o->library_utf8,o->pack_utf8,o->old_mirror_utf8))return 0;
 return c02_file_matches(o->input.library,&o->prepared.files[0])&&c02_file_matches(o->mirror_path,&o->prepared.files[1]);
}
static wh_step c02_check(void *context,void *cap) {
 c02_owner *o=context;wh3w_identity pack;
 return cap&&cap==o->cap&&wh3wr_check(o->registration)&&c02_identity(o->pack,&pack)&&
   c02_same(&pack,&o->input.pack_file.id)?WH_STEP_OK:WH_STEP_UNCERTAIN;
}
static wh_step c02_acquire(void *context,const wh_binding *binding,const wh_gates *gates,void **cap,char lease[49]) {
 c02_owner *o=context;
 if(!(o->recovered?wh3wr_resume(o->registration,binding,gates,o->journal,&o->tip,&o->cap):
    wh3wr_begin(o->registration,binding,gates,&o->tip,&o->cap)))return WH_STEP_UNCERTAIN;
 *cap=o->cap;memcpy(lease,o->input.token,49);c02_phase(o,901);return c02_check(o,o->cap);
}
static wh_step c02_reacquire(void *context,const wh_binding *binding,const wh_gates *gates,const char *prior,void **cap,char lease[49]) {
 c02_owner *o=context;
 if((prior[0]&&strcmp(prior,o->input.token))||
    !wh3wr_resume(o->registration,binding,gates,o->journal,&o->tip,&o->cap))return WH_STEP_UNCERTAIN;
 *cap=o->cap;memcpy(lease,o->input.token,49);return c02_check(o,o->cap);
}
static size_t c02_rows(c02_owner *o,wh_record *rows) {
 const c02_file *files[3];const char *names[3];size_t n=0,k;
 files[n]=&o->input.original;names[n++]="library.sqlite";
 if(o->input.mirror_present){files[n]=&o->input.mirror;names[n++]="mirror.json";}
 files[n]=&o->input.pack_file;names[n++]="pack.exrpack";
 for(k=0;k<n;k++){memset(&rows[k],0,sizeof(rows[k]));c02_id_text(&files[k]->id,rows[k].id);
  strcpy_s(rows[k].path,sizeof(rows[k].path),names[k]);rows[k].size=files[k]->size;memcpy(rows[k].sha,files[k]->sha,65);}
 return n;
}
static wh_step c02_snapshot(void *context,void *cap,wh_record *rows,size_t capacity,size_t *count) {
 c02_owner *o=context;
 if(c02_check(o,cap)!=WH_STEP_OK||capacity<3||!c02_original_state(o))return WH_STEP_UNCERTAIN;
 if(o->recovered&&!o->line_count)return WH_STEP_FAILED;
 *count=c02_rows(o,rows);c02_phase(o,902);return WH_STEP_OK;
}
static int c02_physical(HANDLE handle,char out[4*MAX_PATH]) {
 wchar_t path[MAX_PATH+128];DWORD n=GetFinalPathNameByHandleW(handle,path,MAX_PATH+128,FILE_NAME_NORMALIZED|VOLUME_NAME_GUID);
 return n>0&&n<MAX_PATH+128&&WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,path,-1,out,4*MAX_PATH,NULL,NULL)>0;
}
static int c02_quiet_handle(HANDLE handle) {
 const wchar_t *suffix[]={L"-wal",L"-shm",L"-journal"};wchar_t path[MAX_PATH+144];DWORD n;unsigned k;
 n=GetFinalPathNameByHandleW(handle,path,MAX_PATH+128,FILE_NAME_NORMALIZED|VOLUME_NAME_GUID);
 if(!n||n>=MAX_PATH+128)return 0;
 for(k=0;k<3;k++){
  DWORD attributes,error;path[n]=0;
  if(wcscat_s(path,MAX_PATH+144,suffix[k]))return 0;
  attributes=GetFileAttributesW(path);error=attributes==INVALID_FILE_ATTRIBUTES?GetLastError():0;
  if(attributes!=INVALID_FILE_ATTRIBUTES||error!=ERROR_FILE_NOT_FOUND)return 0;
 }
 return 1;
}
static int c02_private_copy(c02_owner *o) {
 HANDLE stage=c02_open(o->paths[0],GENERIC_READ|GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_WRITE,OPEN_EXISTING);
 wh3w_identity id;LARGE_INTEGER size,zero;unsigned char bytes[65536];DWORD count,written;int ok=0;
 zero.QuadPart=0;
 if(stage==INVALID_HANDLE_VALUE||!c02_quiet_handle(o->original)||!c02_identity(stage,&id)||!c02_same(&id,&o->input.staged[0])||
    !GetFileSizeEx(stage,&size)||size.QuadPart||!SetFilePointerEx(o->original,zero,NULL,FILE_BEGIN))goto done;
 for(;;){
  if(!ReadFile(o->original,bytes,sizeof(bytes),&count,NULL))goto done;
  if(!count)break;
  if(!WriteFile(stage,bytes,count,&written,NULL)||written!=count)goto done;
 }
 if(!c02_quiet_handle(o->original)||!FlushFileBuffers(stage)||!c02_identity(stage,&id)||!c02_same(&id,&o->input.staged[0])||
    !c02_physical(stage,o->stage_utf8)||!c02_physical(o->stages[1],o->mirror_utf8)||
    (o->input.mirror_present&&!c02_physical(o->mirror,o->old_mirror_utf8)))goto done;
 ok=1;
done:
 c02_close(&stage);return ok;
}
static wh_step c02_import(void *context,void *cap,const wh_record *rows,size_t count,char stage[49]) {
 c02_owner *o=context;wh_record expected[3];size_t n=c02_rows(o,expected);
 if(c02_check(o,cap)!=WH_STEP_OK||count!=n||memcmp(rows,expected,n*sizeof(*rows))||!c02_original_state(o))return WH_STEP_UNCERTAIN;
 if(!c02_private_copy(o)||!wh3t_build(o->pack,o->pack_utf8,o->stage_utf8,o->mirror_utf8,
    o->input.mirror_present?o->old_mirror_utf8:NULL,(int)o->input.allow_partial))
  return c02_original_state(o)?WH_STEP_FAILED:WH_STEP_UNCERTAIN;
 if(!c02_id_matches(o->paths[0],&o->input.staged[0])||!c02_id_matches(o->paths[1],&o->input.staged[1]))return WH_STEP_UNCERTAIN;
 memcpy(stage,o->input.token,49);c02_phase(o,903);return WH_STEP_OK;
}
static wh_step c02_verify(void *context,void *cap,const char *stage,const wh_record *rows,size_t count) {
 c02_owner *o=context;size_t k;wh_record expected[3];size_t n=c02_rows(o,expected);
 if(c02_check(o,cap)!=WH_STEP_OK||strcmp(stage,o->input.token)||count!=n||memcmp(rows,expected,n*sizeof(*rows))||
    !c02_original_state(o)||!wh3t_verify(o->pack,o->stage_utf8,o->pack_utf8,o->mirror_utf8))return WH_STEP_UNCERTAIN;
 memcpy(o->prepared.magic,"C02OUT01",8);wh_sha256_hex(&o->input,sizeof(o->input),o->prepared.input_sha);
 for(k=0;k<2;k++){
  HANDLE h=c02_open(o->paths[k],GENERIC_READ|GENERIC_WRITE,FILE_SHARE_READ,OPEN_EXISTING);int ok=0;
  if(h!=INVALID_HANDLE_VALUE)ok=FlushFileBuffers(h)&&c02_hash(h,&o->prepared.files[k])&&c02_same(&o->prepared.files[k].id,&o->input.staged[k]);
  c02_close(&h);if(!ok)return WH_STEP_UNCERTAIN;
 }
 if(!wh3wr_transaction_write(o->registration,WH3WR_PREPARED,&o->prepared,sizeof(o->prepared)))return WH_STEP_UNCERTAIN;
 o->has_prepared=1;c02_phase(o,904);return WH_STEP_OK;
}
static int c02_member_proof(void *context,HANDLE old,HANDLE staged) {
 c02_owner *o=context;c02_file actual;const c02_file *original=o->member?&o->input.mirror:&o->input.original;
 int old_present=!o->member||o->input.mirror_present;
 return (old_present?(old!=INVALID_HANDLE_VALUE&&c02_hash(old,&actual)&&c02_equal(&actual,original)):old==INVALID_HANDLE_VALUE)&&
 c02_hash(staged,&actual)&&c02_equal(&actual,&o->prepared.files[o->member]);
}
static int c02_publish_members(c02_owner *o) {
 const wchar_t *target[2]={wcsrchr(o->input.library,L'\\')+1,wcsrchr(o->mirror_path,L'\\')+1};unsigned k;
 if(!o->has_prepared)return 0;
 c02_close(&o->original);c02_close(&o->mirror);c02_close(&o->stages[0]);c02_close(&o->stages[1]);
 for(k=0;k<2;k++){
  const wh3w_identity *original=(!k||o->input.mirror_present)?(k?&o->input.mirror.id:&o->input.original.id):NULL;
  o->member=k;
  if(wh3wr_publish_member(o->registration,target[k],original,o->input.stages[k],&o->input.staged[k],
    original?o->input.retained[k]:NULL,c02_member_proof,o,&o->controls)!=WH3_TX_OK)return 0;
  c02_phase(o,905+k);
 }
 return c02_published_state(o);
}
static wh_step c02_publish(void *context,void *cap,const char *stage,wh_pub *published) {
 c02_owner *o=context;*published=WH_PUB_UNKNOWN;
 if(c02_check(o,cap)!=WH_STEP_OK||strcmp(stage,o->input.token)||!c02_publish_members(o))return WH_STEP_UNCERTAIN;
 *published=WH_PUB_YES;o->published=1;return WH_STEP_OK;
}
static wh_step c02_inspect(void *context,void *cap,const char *stage,const char *content,wh_pub *published) {
 c02_owner *o=context;wh_record rows[3];char expected[65];size_t n=c02_rows(o,rows);*published=WH_PUB_UNKNOWN;
 if(c02_check(o,cap)!=WH_STEP_OK||!wh_content_digest(rows,n,expected)||(content[0]&&strcmp(content,expected))||
    (stage[0]&&strcmp(stage,o->input.token)))return WH_STEP_UNCERTAIN;
 if(o->publish_intent){
  if(strcmp(stage,o->input.token)||!content[0]||!c02_prepared_read(o)||!c02_publish_members(o))return WH_STEP_UNCERTAIN;
  o->published=1;*published=WH_PUB_YES;return WH_STEP_OK;
 }
 if(!c02_original_state(o))return WH_STEP_UNCERTAIN;
 o->aborted=1;*published=WH_PUB_NO;return WH_STEP_OK;
}
static wh_step c02_discard(void *context,void *cap,const char *stage) {
 c02_owner *o=context;
 if(c02_check(o,cap)!=WH_STEP_OK||strcmp(stage,o->input.token)||!c02_original_state(o))return WH_STEP_UNCERTAIN;
 /* Preserve the identified private objects as evidence. No workers exist. */
 o->aborted=1;return WH_STEP_OK;
}
static int c02_terminal_proof(void *context,const wh3_tip *tip) {
 c02_owner *o=context;size_t count=0;wh3_tip actual;unsigned sequence,event;int committed=0,aborted=0;
 if(!wh3w_read(o->journal,o->lines,EXR_WH_MAX_JOURNAL,&count,&actual)||actual.line_count!=tip->line_count||memcmp(actual.manifest_sha,tip->manifest_sha,65)||memcmp(actual.last_line_sha,tip->last_line_sha,65))return 0;
 for(size_t k=1;k<count;k++){
  if(sscanf(o->lines[k],"EXRWH2 %u %u",&sequence,&event)!=2)return 0;
  if(event==11)committed=1;if(event==14)aborted=1;
 }
 if(committed&&!aborted)return c02_published_state(o);
 if(aborted&&!committed)return c02_original_state(o);
 return 0;
}
static wh_step c02_release(void *context,void *cap) {
 c02_owner *o=context;
 if(c02_check(o,cap)!=WH_STEP_OK)return WH_STEP_UNCERTAIN;
 c02_phase(o,907);
 if(!wh3wr_finish(o->registration,o->journal,&o->tip,c02_terminal_proof,o))return WH_STEP_UNCERTAIN;
 o->cap=NULL;c02_phase(o,908);return WH_STEP_OK;
}
static wh3_tx_status c02_append(void *context,void *cap,const wh3_tip *expected,const char *line,wh3_tip *actual) {
 c02_owner *o=context;wh3_tx_status status=wh3w_append(o->journal,cap,expected,line,actual);
 if(status==WH3_TX_OK)o->tip=*actual;return status;
}
static int c02_history(c02_owner *o) {
 unsigned sequence,event=0;size_t k;
 if(!wh3w_read(o->journal,o->lines,EXR_WH_MAX_JOURNAL,&o->line_count,&o->tip))return 0;
 for(k=0;k<o->line_count;k++)o->line_ptrs[k]=o->lines[k];
 if(!o->line_count)return 1;
 if(!wh_journal_check(&o->input.binding,&o->input.gates,o->line_ptrs,o->line_count))return 0;
 for(k=1;k<o->line_count;k++){
  if(sscanf(o->lines[k],"EXRWH2 %u %u",&sequence,&event)!=2)return 0;
  if(event==9)o->publish_intent=1;
 }
 return 1;
}
static void c02_cleanup(c02_owner *o) {
 size_t k;c02_close(&o->original);c02_close(&o->mirror);c02_close(&o->pack);
 for(k=0;k<2;k++)c02_close(&o->stages[k]);for(k=0;k<o->parent_count;k++)c02_close(&o->pack_parents[k]);
 wh3w_close(o->journal);wh3wr_close(o->registration);free(o);
}
int wmain(int argc,wchar_t **argv) {
 wchar_t library[MAX_PATH],pack[MAX_PATH];c02_owner *o=NULL;wh_provider provider;wh3_backend backend;
 wh3_session *session=NULL;wh_report report={0};int recover,ok=0,partial=0;size_t size=0;
 if(argc==2&&!wcscmp(argv[1],L"--version")){
  printf("exreader-c02-migrate %s provider=%s SDK=3.42.0\n",WH3_BUILD_SOURCE,WH3_PROVIDER_SHA);return 0;
 }
 if(argc<3||!c02_absolute(argv[2],library))goto usage;
 recover=!wcscmp(argv[1],L"recover");
 if(!recover&&wcscmp(argv[1],L"migrate")&&wcscmp(argv[1],L"verify"))goto usage;
 if(recover){if(argc!=3)goto usage;}
 else{if(argc<4||!c02_absolute(argv[3],pack))goto usage;
  if(argc==5&&!wcscmp(argv[4],L"--allow-partial"))partial=1;else if(argc!=4)goto usage;}
 o=calloc(1,sizeof(*o));if(!o)return 3;o->recovered=recover;
 o->original=o->mirror=o->pack=o->stages[0]=o->stages[1]=INVALID_HANDLE_VALUE;
 o->controls.context=o;o->controls.phase=c02_phase;wcscpy_s(o->requested_library,MAX_PATH,library);
#ifdef WH3_MIGRATION_TEST_CONTROLS
 {const char *short_gate=getenv("EXR_C02_GATE_SHORT");if(short_gate){
   unsigned at=(unsigned)strtoul(short_gate,NULL,10);
   if(at!=WH3WG_BEGIN_WRITTEN&&at!=WH3WG_CLEAN_WRITTEN)goto done;
   o->controls.fault=WH3W_SHORT_WRITE;o->controls.fault_phase=at;
 }}
#endif
 if(!wcscmp(argv[1],L"verify")){
  wcscpy_s(o->input.library,MAX_PATH,library);wcscpy_s(o->input.pack,MAX_PATH,pack);
  if(!wh3wr_open(library,WH3WG_SHARED,NULL,&o->registration)||!c02_paths(o)||!c02_pack_pin(o))goto done;
  {
   wchar_t physical[MAX_PATH+128];wchar_t mirror[MAX_PATH+144];
   if(!wh3wr_library_path(o->registration,physical,MAX_PATH+128)||
      swprintf_s(mirror,MAX_PATH+144,L"%ls.legacy-map.json",physical)<0||
      !c02_utf8(physical,o->library_utf8)||!c02_utf8(mirror,o->old_mirror_utf8))goto done;
  }
  ok=wh3t_verify(o->pack,o->library_utf8,o->pack_utf8,o->old_mirror_utf8)&&wh3wr_check(o->registration);goto done;
 }
 if(recover&&!wh3wr_repair_prepare(library,c02_repair_input,o,&o->controls))goto done;
 o->operation="exclusive-admission";
 if(!wh3wr_open(library,recover?WH3WG_RECOVER:WH3WG_OWNER,&o->controls,&o->registration))goto done;
 if(recover){
  if(!wh3wr_transaction_read(o->registration,WH3WR_INPUT,&o->input,sizeof(o->input),&size)||size!=sizeof(o->input)||
     !c02_input_valid(o,library)||!c02_pack_pin(o))goto done;
 }else if(!c02_create_input(o,library,pack,partial))goto done;
 o->operation="exact-journal-open";
 if(!wh3wr_journal(o->registration,&o->input.binding,&o->input.gates,&o->controls,&o->journal)||!c02_history(o))goto done;
 if(recover&&!o->line_count&&wh3wr_clean(o->registration)&&c02_original_state(o)){
  puts("{\"status\":\"abandoned_before_admission\",\"live_capability\":false}");ok=1;goto done;
 }
 if(recover&&o->line_count){
  unsigned sequence,event;
  if(sscanf(o->lines[o->line_count-1],"EXRWH2 %u %u",&sequence,&event)==2&&event==12){
   o->has_prepared=c02_prepared_read(o);
   if(wh3wr_finish(o->registration,o->journal,&o->tip,c02_terminal_proof,o)){ok=1;goto done;}
   /* PENDING may still need a fresh exact capability and terminal retry. */
  }
 }
 memset(&provider,0,sizeof(provider));provider.abi=EXR_WH_ABI;provider.identity_sha=WH3_PROVIDER_SHA;provider.context=o;
 provider.acquire=c02_acquire;provider.reacquire=c02_reacquire;provider.check=c02_check;provider.snapshot=c02_snapshot;
 provider.import_rows=c02_import;provider.verify=c02_verify;provider.publish=c02_publish;provider.inspect=c02_inspect;
 provider.discard=c02_discard;provider.release=c02_release;
 memset(&backend,0,sizeof(backend));backend.abi=EXR_WH3_ABI;backend.context=o;backend.append=c02_append;
 session=wh3_create(&o->input.binding,&o->input.gates,&provider,&backend);if(!session)goto done;
 if(recover){
  if(!o->line_count)wh3_run(session,&report);
  else wh3_recover(session,o->line_ptrs,o->line_count,&report);
 }else{
  if(o->line_count)goto done;
  wh3_run(session,&report);
 }
 printf("{\"status\":\"%s\",\"detail\":\"%s\",\"sequence\":%u,\"live_capability\":%s,\"source\":\"%s\",\"provider\":\"%s\"}\n",
   wh_status_name(report.status),report.detail,report.seq,report.live_lease?"true":"false",WH3_BUILD_SOURCE,WH3_PROVIDER_SHA);
 ok=report.status==WH_COMPLETED||report.status==WH_ROLLED_BACK;
 if(ok&&!wh3_dispose(session))ok=0;
done:
 if(!ok)fprintf(stderr,"C02 refused or pending; immutable inputs and native evidence retained (operation %s, Windows error %lu).\n",o&&o->operation?o->operation:"initial",GetLastError());
 c02_cleanup(o);return ok?(report.status==WH_ROLLED_BACK&&!recover?3:0):2;
usage:
 fputs("Usage: exreader-c02-migrate migrate LIBRARY PACK [--allow-partial]\n"
       "       exreader-c02-migrate recover LIBRARY\n"
       "       exreader-c02-migrate verify LIBRARY PACK\n"
       "Start each later migration with exreader-c02-admission next-epoch LIBRARY.\n",stderr);
 return 64;
}
