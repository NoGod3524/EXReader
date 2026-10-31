/* SPDX-License-Identifier: MIT */
#include <exr_wh3_win.h>
#include <sddl.h>
#include <winternl.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#define RPINS 64u
#define RSEAL 1288u
#define RBYTES 1352u
/* The current-user hive is the independent trust anchor, not a sidecar in the
   migration namespace. Every owned key has an explicit user+SYSTEM-only DACL. */
struct wh3wr_registration {
 HKEY key;
 wh3wg_gate *gate;
 HANDLE target,pins[RPINS];
 wchar_t library[MAX_PATH],root[MAX_PATH],paths[RPINS][MAX_PATH],route[65];
 wh3w_identity ids[5],pinids[RPINS];
 unsigned np,mode; void *cap;
 unsigned char record[RBYTES];
 wh3wg_grant grant;char domain[49];
};
static int rid(HANDLE h,wh3w_identity *id,int directory) {
 FILE_ID_INFO f;BY_HANDLE_FILE_INFORMATION b;
 if(!GetFileInformationByHandleEx(h,FileIdInfo,&f,sizeof(f))||
    !GetFileInformationByHandle(h,&b)||
    (b.dwFileAttributes&FILE_ATTRIBUTE_REPARSE_POINT)||
    !!(b.dwFileAttributes&FILE_ATTRIBUTE_DIRECTORY)!=!!directory||
    (!directory&&b.nNumberOfLinks!=1))return 0;
 id->volume=f.VolumeSerialNumber;id->file=f.FileId;return 1;
}
static int reqid(const wh3w_identity *a,const wh3w_identity *b) {
 return a->volume==b->volume&&!memcmp(&a->file,&b->file,16);
}
static void rput(unsigned char *p,uint64_t x) {
 unsigned k;for(k=0;k<8;k++){p[k]=(unsigned char)x;x>>=8;}
}
static uint64_t rget(const unsigned char *p) {
 unsigned k;uint64_t x=0;for(k=0;k<8;k++)x|=((uint64_t)p[k])<<(8*k);return x;
}
static int rhex(const char *p,size_t n) {
 size_t k;for(k=0;k<n;k++)if(!((p[k]>='0'&&p[k]<='9')||(p[k]>='a'&&p[k]<='f')))return 0;
 return !p[n];
}
static TOKEN_USER *ruser(void) {
 HANDLE token;DWORD size=0;TOKEN_USER *user;
 if(!OpenThreadToken(GetCurrentThread(),TOKEN_QUERY,TRUE,&token)){
  if(GetLastError()!=ERROR_NO_TOKEN||!OpenProcessToken(GetCurrentProcess(),TOKEN_QUERY,&token))return NULL;
 }
 (void)GetTokenInformation(token,TokenUser,NULL,0,&size);
 user=malloc(size);
 if(!user||!GetTokenInformation(token,TokenUser,user,size,&size)){free(user);user=NULL;}
 CloseHandle(token);return user;
}
static int rsecure(HKEY key,PSID user) {
 DWORD size=0,revision,link_type=0,link_size=0;PSECURITY_DESCRIPTOR sd=NULL;
 SECURITY_DESCRIPTOR_CONTROL control;PSID owner;PACL acl;BOOL present,defaulted;
 unsigned k;int ok=0,has_user=0,has_system=0;
 /* Open the link itself and refuse it, including an unknown inspection error. */
 if(RegQueryValueExW(key,L"SymbolicLinkValue",NULL,&link_type,NULL,&link_size)!=ERROR_FILE_NOT_FOUND)return 0;
 if(RegGetKeySecurity(key,OWNER_SECURITY_INFORMATION|DACL_SECURITY_INFORMATION,NULL,&size)!=ERROR_INSUFFICIENT_BUFFER)return 0;
 sd=malloc(size);if(!sd)return 0;
 if(RegGetKeySecurity(key,OWNER_SECURITY_INFORMATION|DACL_SECURITY_INFORMATION,sd,&size)!=ERROR_SUCCESS||
    !GetSecurityDescriptorOwner(sd,&owner,&defaulted)||!EqualSid(owner,user)||
    !GetSecurityDescriptorControl(sd,&control,&revision)||!(control&SE_DACL_PROTECTED)||
    !GetSecurityDescriptorDacl(sd,&present,&acl,&defaulted)||!present||!acl||!IsValidAcl(acl))goto done;
 for(k=0;k<acl->AceCount;k++){
  ACCESS_ALLOWED_ACE *ace;PSID sid;
  if(!GetAce(acl,k,(void **)&ace)||ace->Header.AceType!=ACCESS_ALLOWED_ACE_TYPE||ace->Header.AceFlags)goto done;
  sid=(PSID)&ace->SidStart;
  if(!IsValidSid(sid)||(ace->Mask&KEY_ALL_ACCESS)!=KEY_ALL_ACCESS)goto done;
  if(EqualSid(sid,user))has_user=1;
  else if(IsWellKnownSid(sid,WinLocalSystemSid))has_system=1;
  else goto done;
 }
 ok=has_user&&has_system;
done:free(sd);return ok;
}
static int ropenkey(const wchar_t *route,int create,HKEY *out) {
 TOKEN_USER *user=NULL;LPWSTR sid=NULL;PSECURITY_DESCRIPTOR sd=NULL;
 wchar_t sddl[512];HKEY hive=NULL,software=NULL,base=NULL,key=NULL;
 SECURITY_ATTRIBUTES sa;DWORD disposition=0;int ok=0;
 REGSAM access=KEY_READ|KEY_WOW64_64KEY|(create?KEY_WRITE:0);
 *out=NULL;user=ruser();if(!user)goto done;
 if(create){
  if(!ConvertSidToStringSidW(user->User.Sid,&sid))goto done;
  if(swprintf_s(sddl,512,L"O:%lsD:P(A;;KA;;;SY)(A;;KA;;;%ls)",sid,sid)<0||
     !ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl,SDDL_REVISION_1,&sd,NULL))goto done;
  memset(&sa,0,sizeof(sa));sa.nLength=sizeof(sa);sa.lpSecurityDescriptor=sd;
 }
 if(RegOpenCurrentUser(access,&hive)!=ERROR_SUCCESS||
    RegOpenKeyExW(hive,L"Software",REG_OPTION_OPEN_LINK,access,&software)!=ERROR_SUCCESS)goto done;
 {DWORD type=0,n=0;if(RegQueryValueExW(software,L"SymbolicLinkValue",NULL,&type,NULL,&n)!=ERROR_FILE_NOT_FOUND)goto done;}
 {
  LSTATUS status=RegOpenKeyExW(software,L"EXReaderC02Admission",REG_OPTION_OPEN_LINK,access,&base);
  if(status==ERROR_FILE_NOT_FOUND&&create){
   if(RegCreateKeyExW(software,L"EXReaderC02Admission",0,NULL,REG_OPTION_NON_VOLATILE,
        access,&sa,&base,&disposition)!=ERROR_SUCCESS)goto done;
  }else if(status!=ERROR_SUCCESS)goto done;
 }
 if(!rsecure(base,user->User.Sid))goto done;
 if(create){
  if(RegCreateKeyExW(base,route,0,NULL,REG_OPTION_NON_VOLATILE,access,&sa,&key,&disposition)!=ERROR_SUCCESS||
     disposition!=REG_CREATED_NEW_KEY||RegFlushKey(base)!=ERROR_SUCCESS)goto done;
 }else if(RegOpenKeyExW(base,route,REG_OPTION_OPEN_LINK,access,&key)!=ERROR_SUCCESS)goto done;
 if(!rsecure(key,user->User.Sid))goto done;
 *out=key;key=NULL;ok=1;
done:
 if(key)RegCloseKey(key);if(base)RegCloseKey(base);if(software)RegCloseKey(software);if(hive)RegCloseKey(hive);
 if(sd)LocalFree(sd);if(sid)LocalFree(sid);free(user);return ok;
}
static int rpath(const wchar_t *input,wchar_t out[MAX_PATH],wchar_t route[65]) {
 wchar_t upper[MAX_PATH],drive[4],fs[32];DWORD n;size_t k,len;char hash[65];
 if(!input)return 0;n=GetFullPathNameW(input,MAX_PATH,out,NULL);
 if(n<4||n>=MAX_PATH||out[1]!=L':'||out[2]!=L'\\'||wcschr(out+2,L':')||out[n-1]==L'\\')return 0;
 for(k=3;k<n;k++)if(out[k]==L'\\'&&(out[k-1]==L'.'||out[k-1]==L' '||out[k-1]==L'\\'))return 0;
 if(out[n-1]==L'.'||out[n-1]==L' ')return 0;
 drive[0]=out[0];drive[1]=L':';drive[2]=L'\\';drive[3]=0;
 if(GetDriveTypeW(drive)!=DRIVE_FIXED||!GetVolumeInformationW(drive,NULL,0,NULL,NULL,NULL,fs,32)||_wcsicmp(fs,L"NTFS"))return 0;
 if(!LCMapStringEx(LOCALE_NAME_INVARIANT,LCMAP_UPPERCASE,out,-1,upper,MAX_PATH,NULL,NULL,0))return 0;
 len=wcslen(upper);wh_sha256_hex(upper,len*sizeof(wchar_t),hash);
 for(k=0;k<65;k++)route[k]=(wchar_t)hash[k];return 1;
}
static int rpins(wh3wr_registration *r) {
 size_t k,len=wcslen(r->library);wchar_t part[MAX_PATH];
 for(k=3;k<len;k++)if(k==3||r->library[k]==L'\\'){
  HANDLE h;if(r->np==RPINS)return 0;memcpy(part,r->library,k*sizeof(wchar_t));part[k]=0;
  h=CreateFileW(part,FILE_LIST_DIRECTORY|FILE_READ_ATTRIBUTES,FILE_SHARE_READ,NULL,OPEN_EXISTING,
       FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,NULL);
  if(h==INVALID_HANDLE_VALUE)return 0;
  r->pins[r->np]=h;wcscpy_s(r->paths[r->np],MAX_PATH,part);
  if(!rid(h,&r->pinids[r->np],1)){r->np++;return 0;}r->np++;
 }
 return r->np!=0;
}
static int rtarget(wh3wr_registration *r,int missing,int exact) {
 wh3w_identity id;
 r->target=CreateFileW(r->library,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,NULL);
 if(r->target==INVALID_HANDLE_VALUE)return missing&&GetLastError()==ERROR_FILE_NOT_FOUND;
 if(!rid(r->target,&id,0)||(exact&&!reqid(&id,&r->ids[4])))return 0;
 return 1;
}
static int ridentity(wh3wr_registration *r,int target) {
 unsigned k;wh3w_identity id;
 for(k=0;k<r->np;k++){
  HANDLE h;int ok;
  if(!rid(r->pins[k],&id,1)||!reqid(&id,&r->pinids[k]))return 0;
  h=CreateFileW(r->paths[k],FILE_READ_ATTRIBUTES,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_EXISTING,
      FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,NULL);
  if(h==INVALID_HANDLE_VALUE)return 0;
  ok=rid(h,&id,1)&&reqid(&id,&r->pinids[k]);CloseHandle(h);if(!ok)return 0;
 }
 return !target||(r->target!=INVALID_HANDLE_VALUE&&rid(r->target,&id,0)&&reqid(&id,&r->ids[4]));
}
static int rread(HKEY key,unsigned char bytes[RBYTES]) {
 DWORD type=0,n=RBYTES;char hash[65];
 if(RegQueryValueExW(key,L"Binding",NULL,&type,bytes,&n)!=ERROR_SUCCESS||type!=REG_BINARY||n!=RBYTES||
    memcmp(bytes,"WH3REG01",8))return 0;
 wh_sha256_hex(bytes,RSEAL,hash);return !memcmp(hash,bytes+RSEAL,64);
}
static int rcurrent(wh3wr_registration *r) {
 HKEY key=NULL;unsigned char bytes[RBYTES];int ok;
 if(!ropenkey(r->route,0,&key))return 0;
 ok=rread(key,bytes)&&!memcmp(bytes,r->record,RBYTES);RegCloseKey(key);return ok;
}
static void rencode(wh3wr_registration *r,unsigned char bytes[RBYTES]) {
 unsigned k;char hash[65];memset(bytes,0,RBYTES);memcpy(bytes,"WH3REG01",8);
 memcpy(bytes+8,r->domain,48);rput(bytes+56,r->grant.generation);memcpy(bytes+64,r->grant.seal,64);
 for(k=0;k<5;k++){rput(bytes+128+k*24,r->ids[k].volume);memcpy(bytes+136+k*24,&r->ids[k].file,16);}
 memcpy(bytes+248,r->library,(wcslen(r->library)+1)*sizeof(wchar_t));
 memcpy(bytes+768,r->root,(wcslen(r->root)+1)*sizeof(wchar_t));
 wh_sha256_hex(bytes,RSEAL,hash);memcpy(bytes+RSEAL,hash,64);
}
static int rdecode(wh3wr_registration *r) {
 unsigned k;unsigned char canonical[RBYTES];wchar_t library[MAX_PATH],route[65],root[MAX_PATH];
 memcpy(r->domain,r->record+8,48);r->domain[48]=0;
 r->grant.generation=rget(r->record+56);memcpy(r->grant.seal,r->record+64,64);r->grant.seal[64]=0;
 if(!rhex(r->domain,48)||!rhex(r->grant.seal,64))return 0;
 for(k=0;k<5;k++){r->ids[k].volume=rget(r->record+128+k*24);memcpy(&r->ids[k].file,r->record+136+k*24,16);}
 memcpy(library,r->record+248,sizeof(library));memcpy(root,r->record+768,sizeof(root));
 if(!wmemchr(library,0,MAX_PATH)||!wmemchr(root,0,MAX_PATH)||
    _wcsicmp(library,r->library)||!rpath(root,r->root,route)||_wcsicmp(root,r->root))return 0;
 /* Preserve the stored spelling in the canonical encoding; lookup is case-insensitive. */
 wcscpy_s(r->library,MAX_PATH,library);
 rencode(r,canonical);return !memcmp(canonical,r->record,RBYTES);
}
static int rwrite(wh3wr_registration *r,int initial) {
 unsigned char next[RBYTES],check[RBYTES];DWORD type=0,n=0;
 if(initial){
  if(RegQueryValueExW(r->key,L"Binding",NULL,&type,NULL,&n)!=ERROR_FILE_NOT_FOUND)return 0;
 }else if(!rcurrent(r))return 0;
 rencode(r,next);
 if(RegSetValueExW(r->key,L"Binding",0,REG_BINARY,next,RBYTES)!=ERROR_SUCCESS||
    RegFlushKey(r->key)!=ERROR_SUCCESS||!rread(r->key,check)||memcmp(next,check,RBYTES))return 0;
 memcpy(r->record,next,RBYTES);return rcurrent(r);
}
int wh3wr_close(wh3wr_registration *r) {
 unsigned k;if(!r)return 1;
 if(r->gate&&!wh3wg_close(r->gate))return 0;
 if(r->target!=INVALID_HANDLE_VALUE)CloseHandle(r->target);
 for(k=0;k<r->np;k++)CloseHandle(r->pins[k]);
 if(r->key)RegCloseKey(r->key);free(r);return 1;
}
int wh3wr_open(const wchar_t *library,unsigned mode,const wh3w_controls *controls,wh3wr_registration **out) {
 wh3wr_registration *r;int ok=0;
 if(out)*out=NULL;if(!out||(mode!=WH3WG_SHARED&&mode!=WH3WG_OWNER&&mode!=WH3WG_RECOVER))return 0;
 r=calloc(1,sizeof(*r));if(!r)return 0;r->target=INVALID_HANDLE_VALUE;r->mode=mode;
 if(!rpath(library,r->library,r->route)||!ropenkey(r->route,0,&r->key)||!rread(r->key,r->record)||!rdecode(r)||!rpins(r))goto done;
 if(!wh3wg_open(r->root,r->ids,r->domain,&r->grant,mode,controls,&r->gate)||
    !rcurrent(r)||!rtarget(r,mode==WH3WG_RECOVER,mode!=WH3WG_RECOVER)||!ridentity(r,mode!=WH3WG_RECOVER))goto done;
 /* Readers need query rights only. Owners get write rights only after custody. */
 if(mode!=WH3WG_SHARED){
  HKEY write=NULL;
  if(RegOpenKeyExW(r->key,L"",REG_OPTION_OPEN_LINK,KEY_READ|KEY_SET_VALUE|KEY_WOW64_64KEY,&write)!=ERROR_SUCCESS)goto done;
  RegCloseKey(r->key);r->key=write;
 }
 *out=r;ok=1;
done:if(!ok)(void)wh3wr_close(r);return ok;
}
int wh3wr_enroll(const wchar_t *library,const wchar_t *root,
 int (*prove)(void *,const wchar_t *),void *context) {
 wh3wr_registration *r;HANDLE files[3]={INVALID_HANDLE_VALUE,INVALID_HANDLE_VALUE,INVALID_HANDLE_VALUE};
 const wchar_t *names[3]={L"admission.bin",L"journal.bin",L"intent.bin"};
 wchar_t route[65],path[MAX_PATH];unsigned k;int ok=0;char domain[49];
 if(!prove)return 0;r=calloc(1,sizeof(*r));if(!r)return 0;r->target=INVALID_HANDLE_VALUE;
 if(!rpath(library,r->library,r->route)||!rpath(root,r->root,route)||!rpins(r)||!rtarget(r,0,0)||!rid(r->target,&r->ids[4],0))goto done;
 {
  HANDLE h=CreateFileW(r->root,FILE_LIST_DIRECTORY|FILE_READ_ATTRIBUTES,FILE_SHARE_READ,NULL,OPEN_EXISTING,
    FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,NULL);
  if(h==INVALID_HANDLE_VALUE)goto done;
  ok=rid(h,&r->ids[0],1);CloseHandle(h);if(!ok)goto done;ok=0;
 }
 for(k=0;k<3;k++){
  LARGE_INTEGER size;
  swprintf_s(path,MAX_PATH,L"%ls\\%ls",r->root,names[k]);
  files[k]=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ|(k?0:FILE_SHARE_WRITE),NULL,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,NULL);
  if(files[k]==INVALID_HANDLE_VALUE||!rid(files[k],&r->ids[k+1],0)||!GetFileSizeEx(files[k],&size)||size.QuadPart)goto done;
 }
 {unsigned char id[24];static const char hex[]="0123456789abcdef";rput(id,r->ids[0].volume);memcpy(id+8,&r->ids[0].file,16);
  for(k=0;k<24;k++){domain[k*2]=hex[id[k]>>4];domain[k*2+1]=hex[id[k]&15];}domain[48]=0;memcpy(r->domain,domain,49);}
 if(!wh3wg_open(r->root,r->ids,r->domain,NULL,WH3WG_ENROLL,NULL,&r->gate)||
    !ropenkey(r->route,1,&r->key)||!wh3wg_enroll(r->gate,&r->grant)||!ridentity(r,1)||
    !prove(context,r->library)||!ridentity(r,1)||!wh3wg_check(r->gate))goto done;
 for(k=0;k<3;k++){LARGE_INTEGER size;if(!GetFileSizeEx(files[k],&size)||(k&&size.QuadPart))goto done;}
 ok=rwrite(r,1);
done:
 for(k=0;k<3;k++)if(files[k]!=INVALID_HANDLE_VALUE)CloseHandle(files[k]);
 if(!wh3wr_close(r))return 0;return ok;
}
int wh3wr_check(wh3wr_registration *r) {
 return r&&ridentity(r,1)&&rcurrent(r)&&wh3wg_check(r->gate);
}
int wh3wr_journal(wh3wr_registration *r,const wh_binding *b,const wh_gates *g,
 const wh3w_controls *controls,wh3w_store **out) {
 wh3w_identity ids[3];wh3w_domain domain;
 if(out)*out=NULL;if(!r||!out||r->mode==WH3WG_SHARED||!rcurrent(r)||!wh3wg_check(r->gate))return 0;
 ids[0]=r->ids[0];ids[1]=r->ids[2];ids[2]=r->ids[3];wh3wg_domain(r->gate,&domain);
 return wh3w_open(r->root,ids,b,g,&domain,controls,out);
}
int wh3wr_begin(wh3wr_registration *r,const wh_binding *b,const wh_gates *g,
 const wh3_tip *tip,void **cap) {
 if(cap)*cap=NULL;if(!r||!cap||r->mode!=WH3WG_OWNER||r->cap||!wh3wr_check(r))return 0;
 if(!wh3wg_begin(r->gate,b,g,tip,&r->cap))return 0;*cap=r->cap;return 1;
}
int wh3wr_resume(wh3wr_registration *r,const wh_binding *b,const wh_gates *g,
 wh3w_store *store,const wh3_tip *tip,void **cap) {
 if(cap)*cap=NULL;if(!r||!cap||r->mode!=WH3WG_RECOVER||r->cap||!rcurrent(r)||!ridentity(r,0))return 0;
 if(!wh3wg_resume(r->gate,b,g,store,tip,&r->cap))return 0;*cap=r->cap;return 1;
}
int wh3wr_prepare_publish(wh3wr_registration *r) {
 if(!r||!r->cap||!ridentity(r,0)||!rcurrent(r)||!wh3wg_check(r->gate))return 0;
 if(r->target!=INVALID_HANDLE_VALUE){CloseHandle(r->target);r->target=INVALID_HANDLE_VALUE;}return 1;
}
/* A leaf-only native rename uses the source handle's actual parent. Absolute
   MoveFile paths reopen that parent for FILE_ADD_FILE and conflict with our
   intentional no-write pins. Never relax those pins or replace an existing leaf. */
static int rleaf(const wchar_t *leaf) {
 size_t k,n;if(!leaf||(n=wcslen(leaf))==0||n>=MAX_PATH||leaf[n-1]==L'.'||leaf[n-1]==L' ')return 0;
 for(k=0;k<n;k++)if(leaf[k]<32||wcschr(L"\\/:*?\"<>|",leaf[k]))return 0;
 return wcscmp(leaf,L".")&&wcscmp(leaf,L"..");
}
static int rrename(HANDLE file,const wchar_t *leaf) {
 typedef LONG (NTAPI *set_info_fn)(HANDLE,PIO_STATUS_BLOCK,PVOID,ULONG,ULONG);
 typedef ULONG (WINAPI *error_fn)(LONG);
 struct {BOOLEAN replace;HANDLE root;ULONG length;WCHAR name[MAX_PATH];} info;
 IO_STATUS_BLOCK io;HMODULE ntdll=GetModuleHandleW(L"ntdll.dll");LONG status;
 set_info_fn set_info;error_fn error;
 if(!ntdll||!rleaf(leaf)){SetLastError(ERROR_INVALID_NAME);return 0;}
 set_info=(set_info_fn)GetProcAddress(ntdll,"NtSetInformationFile");
 error=(error_fn)GetProcAddress(ntdll,"RtlNtStatusToDosError");
 if(!set_info||!error){SetLastError(ERROR_PROC_NOT_FOUND);return 0;}
 memset(&info,0,sizeof(info));memset(&io,0,sizeof(io));
 info.length=(ULONG)(wcslen(leaf)*sizeof(wchar_t));memcpy(info.name,leaf,info.length);
 status=set_info(file,&io,&info,sizeof(info),10u); /* FileRenameInformation */
 if(status!=0||io.Status!=0){SetLastError(error(status?status:io.Status));return 0;}
 return 1;
}
wh3_tx_status wh3wr_publish(wh3wr_registration *r,const wchar_t *stage_leaf,
 const wh3w_identity *stage_identity,const wchar_t *retained_leaf) {
 wchar_t stage[MAX_PATH];const wchar_t *target_leaf;size_t parent_length;
 HANDLE staged=INVALID_HANDLE_VALUE,old=INVALID_HANDLE_VALUE;wh3w_identity id;int ok=0;DWORD error=ERROR_INVALID_PARAMETER;wh3_tx_status result=WH3_TX_MISMATCH;
 if(!r||!stage_identity||!r->cap||r->mode==WH3WG_SHARED||!rleaf(stage_leaf)||!rleaf(retained_leaf)||
    !ridentity(r,0)||!rcurrent(r)||!wh3wg_check(r->gate))goto done;
 target_leaf=wcsrchr(r->library,L'\\')+1;parent_length=(size_t)(target_leaf-r->library);
 if(!_wcsicmp(stage_leaf,target_leaf)||!_wcsicmp(retained_leaf,target_leaf)||
    !_wcsicmp(stage_leaf,retained_leaf)||parent_length+wcslen(stage_leaf)>=MAX_PATH)goto done;
 memcpy(stage,r->library,parent_length*sizeof(wchar_t));wcscpy_s(stage+parent_length,MAX_PATH-parent_length,stage_leaf);
 staged=CreateFileW(stage,GENERIC_READ|GENERIC_WRITE|DELETE,FILE_SHARE_READ,NULL,OPEN_EXISTING,
   FILE_FLAG_OPEN_REPARSE_POINT|FILE_FLAG_WRITE_THROUGH,NULL);
 if(staged==INVALID_HANDLE_VALUE){error=GetLastError();goto done;}
 if(!rid(staged,&id,0)||!reqid(&id,stage_identity)||reqid(&id,&r->ids[4])||!FlushFileBuffers(staged))goto done;
 if(!wh3wr_prepare_publish(r))goto done;
 old=CreateFileW(r->library,GENERIC_READ|GENERIC_WRITE|DELETE,FILE_SHARE_READ,NULL,OPEN_EXISTING,
   FILE_FLAG_OPEN_REPARSE_POINT|FILE_FLAG_WRITE_THROUGH,NULL);
 if(old==INVALID_HANDLE_VALUE){error=GetLastError();goto done;}
 if(!rid(old,&id,0)||!reqid(&id,&r->ids[4])||!FlushFileBuffers(old)||
    !ridentity(r,0)||!rcurrent(r)||!wh3wg_check(r->gate))goto done;
 result=WH3_TX_UNCERTAIN;
 if(!rrename(old,retained_leaf)){error=GetLastError();goto done;}
 if(!ridentity(r,0)||!rcurrent(r)||!wh3wg_check(r->gate))goto done;
 if(!rrename(staged,target_leaf)){error=GetLastError();goto done;}
 if(!FlushFileBuffers(old)||!FlushFileBuffers(staged)){error=GetLastError();goto done;}
 ok=1;
done:
 if(old!=INVALID_HANDLE_VALUE)CloseHandle(old);
 if(staged!=INVALID_HANDLE_VALUE)CloseHandle(staged);
 if(ok){
  ok=rtarget(r,0,0)&&rid(r->target,&id,0)&&reqid(&id,stage_identity)&&
     ridentity(r,0)&&rcurrent(r)&&wh3wg_check(r->gate);
  if(!ok)error=ERROR_INVALID_DATA;
 }
 if(ok)return WH3_TX_OK;
 if(result==WH3_TX_UNCERTAIN){wh3w_domain domain;wh3wg_domain(r->gate,&domain);domain.poison(domain.context,r->cap,"publisher-uncertain");}
 SetLastError(error);return result;
}
int wh3wr_finish(wh3wr_registration *r,wh3w_store *store,const wh3_tip *tip,
 int (*prove)(void *,const wh3_tip *),void *context) {
 wh3wg_grant grant;wh3w_identity target;
 if(!r||!prove||r->mode==WH3WG_SHARED||!ridentity(r,0)||!rcurrent(r))return 0;
 if(r->target==INVALID_HANDLE_VALUE&&!rtarget(r,0,0))return 0;
 if(!rid(r->target,&target,0))return 0;
 if(r->cap){
  if(!wh3wg_finish(r->gate,r->cap,store,tip,prove,context,&grant))return 0;
 }else{
  if(r->mode!=WH3WG_RECOVER||!wh3wg_reconcile(r->gate,store,tip,prove,context,&grant))return 0;
 }
 {wh3w_identity after;if(!ridentity(r,0)||!rid(r->target,&after,0)||!reqid(&target,&after))return 0;}
 r->grant=grant;r->ids[4]=target;r->cap=NULL;
 return rwrite(r,0);
}
