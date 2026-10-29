/* SPDX-License-Identifier: MIT */
#include "lm_recovery_win32_platform.h"
#include <aclapi.h>
#include <winternl.h>
#include <sddl.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#include <stdio.h>
static int wr_launch_blocked;
int wr_cleanup_uncertain(void){return wr_launch_blocked;}
static int wr_fail(wr_error *e,const char *why){if(e){e->native=GetLastError();e->reason=why;}return 0;}
static int wr_refuse(wr_error *e,const char *why){SetLastError(ERROR_INVALID_DATA);return wr_fail(e,why);}
int wr_utf8(const char *s,WCHAR out[WR_PATH],wr_error *e){if(!s||!MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,s,-1,out,WR_PATH))return wr_fail(e,"utf8");return 1;}
int wr_identity_get(HANDLE h,int dir,wr_identity *id,wr_error *e){FILE_ID_INFO f;FILE_STANDARD_INFO s;FILE_ATTRIBUTE_TAG_INFO a;
 memset(id,0,sizeof(*id));if(!GetFileInformationByHandleEx(h,FileIdInfo,&f,sizeof(f))||!GetFileInformationByHandleEx(h,FileStandardInfo,&s,sizeof(s))||!GetFileInformationByHandleEx(h,FileAttributeTagInfo,&a,sizeof(a)))return wr_fail(e,"file-id-query");
 if((a.FileAttributes&FILE_ATTRIBUTE_REPARSE_POINT)||!!s.Directory!=!!dir||s.DeletePending||(!dir&&s.NumberOfLinks!=1)||s.EndOfFile.QuadPart<0)return wr_refuse(e,"file-kind-or-alias");
 id->volume=f.VolumeSerialNumber;memcpy(id->file,f.FileId.Identifier,16);id->attributes=a.FileAttributes;id->links=s.NumberOfLinks;id->size=(ULONGLONG)s.EndOfFile.QuadPart;return 1;}
int wr_identity_equal(const wr_identity *a,const wr_identity *b){return a->volume==b->volume&&!memcmp(a->file,b->file,16);}
void wr_identity_text(const wr_identity *id,char out[49]){unsigned i;sprintf(out,"%016llx",(unsigned long long)id->volume);for(i=0;i<16;i++)sprintf(out+16+2*i,"%02x",id->file[i]);out[48]=0;}
static int wr_security(wr_context *c,wr_error *e){HANDLE token=NULL;DWORD n=0,z;TOKEN_USER *user=NULL;PACL acl=(PACL)c->acl;
 if(!OpenProcessToken(GetCurrentProcess(),TOKEN_QUERY,&token))return wr_fail(e,"token-open");
 GetTokenInformation(token,TokenUser,NULL,0,&n);if(!n||n>65536){CloseHandle(token);return wr_refuse(e,"token-size");}user=malloc(n);if(!user){CloseHandle(token);return wr_refuse(e,"allocation");}
 if(!GetTokenInformation(token,TokenUser,user,n,&n)||!CopySid(sizeof(c->user),c->user,user->User.Sid)){free(user);CloseHandle(token);return wr_fail(e,"token-user");}free(user);CloseHandle(token);
 z=sizeof(c->system);if(!CreateWellKnownSid(WinLocalSystemSid,NULL,c->system,&z))return wr_fail(e,"system-sid");z=sizeof(c->admins);if(!CreateWellKnownSid(WinBuiltinAdministratorsSid,NULL,c->admins,&z))return wr_fail(e,"admins-sid");
 if(!InitializeAcl(acl,sizeof(c->acl),ACL_REVISION)||!AddAccessAllowedAceEx(acl,ACL_REVISION,OBJECT_INHERIT_ACE|CONTAINER_INHERIT_ACE,FILE_ALL_ACCESS,c->user))return wr_fail(e,"private-acl");
 if(!EqualSid(c->user,c->system)&&!AddAccessAllowedAceEx(acl,ACL_REVISION,OBJECT_INHERIT_ACE|CONTAINER_INHERIT_ACE,FILE_ALL_ACCESS,c->system))return wr_fail(e,"private-system-acl");
 if(!InitializeSecurityDescriptor(&c->descriptor,SECURITY_DESCRIPTOR_REVISION)||!SetSecurityDescriptorOwner(&c->descriptor,c->user,FALSE)||!SetSecurityDescriptorDacl(&c->descriptor,TRUE,acl,FALSE)||!SetSecurityDescriptorControl(&c->descriptor,SE_DACL_PROTECTED,SE_DACL_PROTECTED))return wr_fail(e,"private-descriptor");
 c->security.nLength=sizeof(c->security);c->security.lpSecurityDescriptor=&c->descriptor;c->security.bInheritHandle=FALSE;return 1;}
int wr_private_acl(HANDLE h,int dir,wr_context *c,wr_error *e){PSECURITY_DESCRIPTOR sd=NULL;PSID owner=NULL;PACL acl=NULL;SECURITY_DESCRIPTOR_CONTROL control;DWORD revision,rc;unsigned i,users=0,systems=0;int ok=0;
 rc=GetSecurityInfo(h,SE_FILE_OBJECT,OWNER_SECURITY_INFORMATION|DACL_SECURITY_INFORMATION,&owner,NULL,&acl,NULL,&sd);if(rc!=ERROR_SUCCESS){SetLastError(rc);return wr_fail(e,"acl-query");}
 if(!owner||!EqualSid(owner,c->user)||!acl||!GetSecurityDescriptorControl(sd,&control,&revision)||!(control&SE_DACL_PROTECTED)||acl->AceCount!=(EqualSid(c->user,c->system)?1:2))goto done;
 for(i=0;i<acl->AceCount;i++){ACCESS_ALLOWED_ACE *a=NULL;if(!GetAce(acl,i,(void**)&a)||a->Header.AceType!=ACCESS_ALLOWED_ACE_TYPE||a->Mask!=FILE_ALL_ACCESS||a->Header.AceFlags!=(dir?(OBJECT_INHERIT_ACE|CONTAINER_INHERIT_ACE):0))goto done;
  if(EqualSid(&a->SidStart,c->user))users++;else if(EqualSid(&a->SidStart,c->system))systems++;else goto done;}
 ok=users==1&&systems==(EqualSid(c->user,c->system)?0:1);
 done:LocalFree(sd);return ok?1:wr_refuse(e,"private-acl-shape");}
/* SDK-created regular files may inherit only the same two allowed SIDs.
 * Adapter records still require the stronger explicit protected descriptor. */
int wr_data_acl(HANDLE h,wr_context *c,wr_error *e){PSECURITY_DESCRIPTOR sd=NULL;PSID owner=NULL;PACL acl=NULL;DWORD rc;unsigned i,u=0,y=0;int ok=0;
 rc=GetSecurityInfo(h,SE_FILE_OBJECT,OWNER_SECURITY_INFORMATION|DACL_SECURITY_INFORMATION,&owner,NULL,&acl,NULL,&sd);if(rc){SetLastError(rc);return wr_fail(e,"data-acl-query");}
 if(!owner||!EqualSid(owner,c->user)||!acl||acl->AceCount!=(EqualSid(c->user,c->system)?1:2))goto done;
 for(i=0;i<acl->AceCount;i++){ACCESS_ALLOWED_ACE *a=NULL;if(!GetAce(acl,i,(void**)&a)||a->Header.AceType!=ACCESS_ALLOWED_ACE_TYPE||a->Mask!=FILE_ALL_ACCESS||(a->Header.AceFlags!=0&&a->Header.AceFlags!=INHERITED_ACE))goto done;if(EqualSid(&a->SidStart,c->user))u++;else if(EqualSid(&a->SidStart,c->system))y++;else goto done;}
 ok=u==1&&y==(EqualSid(c->user,c->system)?0:1);
 done:LocalFree(sd);return ok?1:wr_refuse(e,"data-acl-shape");}
static int wr_leaf(const WCHAR *s){const WCHAR *p;size_t n=wcslen(s);WCHAR stem[32];size_t k=0;if(!n||n>240||s[n-1]==L'.'||s[n-1]==L' ')return 0;
 for(p=s;*p;p++)if(*p<32||wcschr(L"\\/:*?\"<>|",*p))return 0;
 while(k<n&&s[k]!=L'.'&&k<31){stem[k]=s[k];k++;}stem[k]=0;
 if(!_wcsicmp(stem,L"CON")||!_wcsicmp(stem,L"PRN")||!_wcsicmp(stem,L"AUX")||!_wcsicmp(stem,L"NUL")||(k==4&&(!_wcsnicmp(stem,L"COM",3)||!_wcsnicmp(stem,L"LPT",3))&&stem[3]>=L'1'&&stem[3]<=L'9'))return 0;return wcscmp(s,L".")&&wcscmp(s,L"..");}
int wr_join(wr_context *c,const WCHAR *leaf,WCHAR out[WR_PATH],wr_error *e){if(!wr_leaf(leaf)||wcslen(c->path)+wcslen(leaf)+2>=WR_PATH)return wr_refuse(e,"leaf-path");swprintf(out,WR_PATH,L"%ls\\%ls",c->path,leaf);return 1;}
static HANDLE wr_pin_one(const WCHAR *path,wr_identity *id,wr_error *e){HANDLE h=CreateFileW(path,FILE_READ_ATTRIBUTES|READ_CONTROL,FILE_SHARE_READ,NULL,OPEN_EXISTING,FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,NULL);if(h==INVALID_HANDLE_VALUE){wr_fail(e,"ancestor-open");return h;}if(!wr_identity_get(h,1,id,e)){CloseHandle(h);return INVALID_HANDLE_VALUE;}return h;}
static HANDLE wr_create_directory_bound(HANDLE parent,const WCHAR *leaf,wr_context *c,wr_identity *id,wr_error *e){
 typedef NTSTATUS (NTAPI *create_fn)(PHANDLE,ACCESS_MASK,POBJECT_ATTRIBUTES,PIO_STATUS_BLOCK,PLARGE_INTEGER,ULONG,ULONG,ULONG,ULONG,PVOID,ULONG);
 typedef ULONG (WINAPI *error_fn)(NTSTATUS);
 HMODULE module=GetModuleHandleW(L"ntdll.dll");create_fn create=(create_fn)GetProcAddress(module,"NtCreateFile");error_fn translate=(error_fn)GetProcAddress(module,"RtlNtStatusToDosError");
 OBJECT_ATTRIBUTES object;UNICODE_STRING name;IO_STATUS_BLOCK io;NTSTATUS status;HANDLE h=INVALID_HANDLE_VALUE;size_t bytes=wcslen(leaf)*sizeof(WCHAR);
 if(!create||!translate||!wr_leaf(leaf)||bytes>65532){wr_refuse(e,"native-directory-api");return INVALID_HANDLE_VALUE;}
 memset(&object,0,sizeof(object));memset(&io,0,sizeof(io));name.Buffer=(WCHAR*)leaf;name.Length=(USHORT)bytes;name.MaximumLength=(USHORT)(bytes+2);
 object.Length=sizeof(object);object.RootDirectory=parent;object.ObjectName=&name;object.Attributes=0x40;object.SecurityDescriptor=&c->descriptor;
 /* Public NtCreateFile: FILE_CREATE=2, DIRECTORY_FILE=1, WRITE_THROUGH=2,
  * SYNCHRONOUS_IO_NONALERT=0x20, OPEN_REPARSE_POINT=0x00200000. No backup intent. */
 status=create(&h,FILE_LIST_DIRECTORY|FILE_TRAVERSE|FILE_READ_ATTRIBUTES|READ_CONTROL|SYNCHRONIZE,&object,&io,NULL,FILE_ATTRIBUTE_DIRECTORY,FILE_SHARE_READ,2,1|2|0x20|0x00200000,NULL,0);
 if(e){e->ntstatus=status;e->io_information=io.Information;}if(status!=0||io.Status!=0){if(h!=INVALID_HANDLE_VALUE)CloseHandle(h);SetLastError(translate(status?status:io.Status));wr_fail(e,"native-directory-create");return INVALID_HANDLE_VALUE;}
 if(io.Information!=2||!wr_identity_get(h,1,id,e)||!wr_private_acl(h,1,c,e)){CloseHandle(h);wr_refuse(e,"native-created-directory-binding");return INVALID_HANDLE_VALUE;}
 return h;
}
static int wr_inventory_at(const WCHAR *path,unsigned depth,unsigned *entries,ULONGLONG *bytes,wr_error *e){WCHAR pattern[WR_PATH],child[WR_PATH];WIN32_FIND_DATAW data;HANDLE find=INVALID_HANDLE_VALUE,pin=INVALID_HANDLE_VALUE;wr_identity id;DWORD code;int ok=0;
 if(depth>16||wcslen(path)+3>=WR_PATH)return wr_refuse(e,"inventory-depth");pin=wr_pin_one(path,&id,e);if(pin==INVALID_HANDLE_VALUE)return 0;swprintf(pattern,WR_PATH,L"%ls\\*",path);find=FindFirstFileW(pattern,&data);if(find==INVALID_HANDLE_VALUE){if(GetLastError()==ERROR_FILE_NOT_FOUND){ok=1;goto done;}wr_fail(e,"inventory-open");goto done;}
 do{if(!wcscmp(data.cFileName,L".")||!wcscmp(data.cFileName,L".."))continue;if(++*entries>4096||wcslen(path)+wcslen(data.cFileName)+2>=WR_PATH){wr_refuse(e,"entry-budget");goto done;}swprintf(child,WR_PATH,L"%ls\\%ls",path,data.cFileName);
  if(data.dwFileAttributes&FILE_ATTRIBUTE_REPARSE_POINT)continue; /* metadata only; actual open refuses */
  if(data.dwFileAttributes&FILE_ATTRIBUTE_DIRECTORY){if(!wr_inventory_at(child,depth+1,entries,bytes,e))goto done;}
  else{ULONGLONG size=((ULONGLONG)data.nFileSizeHigh<<32)|data.nFileSizeLow;if(size>WR_WRITE_TOTAL||*bytes>WR_WRITE_TOTAL-size){wr_refuse(e,"root-byte-budget");goto done;}*bytes+=size;}
 }while(FindNextFileW(find,&data));code=GetLastError();if(code!=ERROR_NO_MORE_FILES){SetLastError(code);wr_fail(e,"inventory-enumeration");goto done;}ok=1;
 done:if(find!=INVALID_HANDLE_VALUE)FindClose(find);if(pin!=INVALID_HANDLE_VALUE)CloseHandle(pin);return ok;}
static int wr_reserve(wr_context *c,size_t add,wr_error *e){unsigned count=0;ULONGLONG bytes=0;if(!wr_inventory_at(c->path,0,&count,&bytes,e))return 0;if(count>=4096||add>WR_WRITE_TOTAL||bytes>WR_WRITE_TOTAL-add)return wr_refuse(e,"root-reservation");return 1;}
HANDLE wr_directory_new(wr_context *c,const WCHAR *leaf,wr_identity *id,wr_error *e){if(!wr_recheck(c,e)||!wr_reserve(c,0,e))return INVALID_HANDLE_VALUE;return wr_create_directory_bound(c->directory,leaf,c,id,e);}
int wr_prepare(wr_context *c,const WCHAR *path,int create,wr_error *e){WCHAR full[WR_PATH],part[WR_PATH],volume[WR_PATH],fs[32];size_t n,i,start;DWORD flags=0;wr_identity id;HANDLE h;
 memset(c,0,sizeof(*c));c->directory=INVALID_HANDLE_VALUE;if(!wr_security(c,e))return 0;
 n=wcslen(path);if(n<4||n>=WR_PATH||!((path[0]>=L'A'&&path[0]<=L'Z')||(path[0]>=L'a'&&path[0]<=L'z'))||path[1]!=L':'||path[2]!=L'\\'||wcschr(path+2,L':')||wcschr(path,L'/')||path[n-1]==L'\\')return wr_refuse(e,"absolute-local-path");
 if(!GetFullPathNameW(path,WR_PATH,full,NULL)||_wcsicmp(path,full))return wr_refuse(e,"canonical-path");
 volume[0]=path[0];volume[1]=L':';volume[2]=L'\\';volume[3]=0;if(GetDriveTypeW(volume)!=DRIVE_FIXED)return wr_refuse(e,"local-fixed-volume-required");
 wcsncpy(part,path,3);part[3]=0;h=wr_pin_one(part,&id,e);if(h==INVALID_HANDLE_VALUE)return 0;c->pins[c->count]=h;c->identities[c->count]=id;wcscpy(c->paths[c->count++],part);
 if(!GetVolumeInformationByHandleW(h,NULL,0,NULL,NULL,&flags,fs,32)||_wcsicmp(fs,L"NTFS")||!(flags&FILE_PERSISTENT_ACLS))return wr_refuse(e,"ntfs-acls-required");
 /* Outside ancestors are pinned namespace components, not private ACLs. */
 for(start=3;start<n;start=i+1){WCHAR leaf[256];for(i=start;i<n&&path[i]!=L'\\';i++);if(i-start>=256||c->count>=WR_PINS)return wr_refuse(e,"path-depth");wcsncpy(leaf,path+start,i-start);leaf[i-start]=0;if(!wr_leaf(leaf))return wr_refuse(e,"path-component");wcsncpy(part,path,i);part[i]=0;
  if(i==n&&create)h=wr_create_directory_bound(c->pins[c->count-1],leaf,c,&id,e);else h=wr_pin_one(part,&id,e);if(h==INVALID_HANDLE_VALUE)return 0;c->pins[c->count]=h;c->identities[c->count]=id;wcscpy(c->paths[c->count++],part);
  if(i==n){if(!wr_private_acl(h,1,c,e))return 0;c->directory=h;c->root=id;wcscpy(c->path,part);} /* Outside ancestors are pinned namespace components, not private ACLs. */
 }
 return wr_recheck(c,e);}
int wr_recheck(wr_context *c,wr_error *e){unsigned i;for(i=0;i<c->count;i++){wr_identity held,actual;HANDLE h;if(!wr_identity_get(c->pins[i],1,&held,e)||!wr_identity_equal(&held,&c->identities[i]))return wr_refuse(e,"held-parent-changed");h=wr_pin_one(c->paths[i],&actual,e);if(h==INVALID_HANDLE_VALUE)return 0;CloseHandle(h);if(!wr_identity_equal(&held,&actual))return wr_refuse(e,"parent-path-changed");}return c->directory!=INVALID_HANDLE_VALUE?wr_private_acl(c->directory,1,c,e):wr_refuse(e,"missing-root");}
HANDLE wr_open(wr_context *c,const WCHAR *leaf,DWORD access,DWORD sharing,int create,wr_error *e){WCHAR p[WR_PATH];HANDLE h;wr_identity id;SECURITY_DESCRIPTOR sd;BYTE aclbuf[512];PACL acl=(PACL)aclbuf;SECURITY_ATTRIBUTES sa;DWORD saved;
 if(!wr_recheck(c,e)||!wr_join(c,leaf,p,e))return INVALID_HANDLE_VALUE;
 if(create&&!wr_reserve(c,0,e))return INVALID_HANDLE_VALUE;
 if(create&&++c->entries>4096){wr_refuse(e,"entry-budget");return INVALID_HANDLE_VALUE;}
 if(!InitializeAcl(acl,sizeof(aclbuf),ACL_REVISION)||!AddAccessAllowedAce(acl,ACL_REVISION,FILE_ALL_ACCESS,c->user)||(!EqualSid(c->user,c->system)&&!AddAccessAllowedAce(acl,ACL_REVISION,FILE_ALL_ACCESS,c->system))||!InitializeSecurityDescriptor(&sd,SECURITY_DESCRIPTOR_REVISION)||!SetSecurityDescriptorOwner(&sd,c->user,FALSE)||!SetSecurityDescriptorDacl(&sd,TRUE,acl,FALSE)||!SetSecurityDescriptorControl(&sd,SE_DACL_PROTECTED,SE_DACL_PROTECTED)){wr_fail(e,"file-descriptor");return INVALID_HANDLE_VALUE;}
 sa.nLength=sizeof(sa);sa.lpSecurityDescriptor=&sd;sa.bInheritHandle=FALSE;
 h=CreateFileW(p,access|FILE_READ_ATTRIBUTES|READ_CONTROL,sharing,create?&sa:NULL,create?CREATE_NEW:OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL|FILE_FLAG_OPEN_REPARSE_POINT|FILE_FLAG_WRITE_THROUGH,NULL);
 if(h==INVALID_HANDLE_VALUE){wr_fail(e,"regular-open");return h;}if(!wr_identity_get(h,0,&id,e)||!wr_private_acl(h,0,c,e)){saved=e?e->native:ERROR_INVALID_DATA;CloseHandle(h);SetLastError(saved);return INVALID_HANDLE_VALUE;}return h;}
int wr_flush(HANDLE h,wr_error *e){if(!FlushFileBuffers(h))return wr_fail(e,"file-flush");return 1;}
int wr_write_new(wr_context *c,const WCHAR *leaf,const void *p,size_t size,int sync,HANDLE *retained,wr_error *e){HANDLE h;size_t off=0;DWORD n;int ok=0;if(retained)*retained=INVALID_HANDLE_VALUE;if(size>WR_RECORD_MAX||c->written>WR_WRITE_TOTAL-size)return wr_refuse(e,"write-reservation");if(!wr_reserve(c,size,e))return 0;c->written+=size;
 h=wr_open(c,leaf,GENERIC_READ|GENERIC_WRITE|DELETE,FILE_SHARE_READ,1,e);if(h==INVALID_HANDLE_VALUE)return 0;
 while(off<size){if(!WriteFile(h,(const char*)p+off,(DWORD)(size-off),&n,NULL)||!n){wr_fail(e,"file-write");goto done;}off+=n;}if(sync&&!wr_flush(h,e))goto done;{void *readback=NULL;size_t length=0;wr_identity held,entry;HANDLE check=INVALID_HANDLE_VALUE;
  if(!wr_identity_get(h,0,&held,e)||!wr_read(h,&readback,&length,WR_RECORD_MAX,e)){free(readback);goto done;}
  if(length!=size||(size&&memcmp(readback,p,size))){free(readback);wr_refuse(e,"write-readback-mismatch");goto done;}free(readback);
  check=wr_open(c,leaf,0,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,0,e);if(check==INVALID_HANDLE_VALUE)goto done;
  if(!wr_identity_get(check,0,&entry,e)||!wr_identity_equal(&held,&entry)){CloseHandle(check);wr_refuse(e,"write-path-identity");goto done;}if(!CloseHandle(check)){wr_fail(e,"write-check-close");goto done;}
 }if(!wr_recheck(c,e))goto done;ok=1;
 done:if(ok&&retained)*retained=h;else if(!CloseHandle(h)&&ok)ok=wr_fail(e,"file-close");return ok;}
int wr_read(HANDLE h,void **bytes,size_t *size,size_t max,wr_error *e){wr_identity before,after;LARGE_INTEGER at;DWORD got;size_t off=0;char *p=NULL;*bytes=NULL;*size=0;
 if(!wr_identity_get(h,0,&before,e)||before.size>max||before.size>SIZE_MAX-1)return wr_refuse(e,"read-size");p=malloc((size_t)before.size+1);if(!p)return wr_refuse(e,"allocation");at.QuadPart=0;if(!SetFilePointerEx(h,at,NULL,FILE_BEGIN)){free(p);return wr_fail(e,"read-seek");}
 while(off<(size_t)before.size){DWORD amount=(DWORD)(((size_t)before.size-off)>65536?65536:((size_t)before.size-off));if(!ReadFile(h,p+off,amount,&got,NULL)||!got){free(p);return wr_fail(e,"read-short");}off+=got;}
 {char extra;if(!ReadFile(h,&extra,1,&got,NULL)||got){free(p);return wr_refuse(e,"read-growth");}}
 if(!wr_identity_get(h,0,&after,e)||!wr_identity_equal(&before,&after)||before.size!=after.size){free(p);return wr_refuse(e,"read-identity");}p[off]=0;*bytes=p;*size=off;return 1;}
int wr_rename_new(wr_context *c,HANDLE h,const WCHAR *leaf,wr_error *e){size_t n;FILE_RENAME_INFO *info;wr_identity id;WCHAR p[WR_PATH];int ok;if(!wr_recheck(c,e)||!wr_join(c,leaf,p,e)||!wr_identity_get(h,0,&id,e)||id.volume!=c->root.volume)return wr_refuse(e,"rename-binding");n=wcslen(leaf)*sizeof(WCHAR);info=calloc(1,sizeof(*info)+n);if(!info)return wr_refuse(e,"allocation");info->ReplaceIfExists=FALSE;info->RootDirectory=c->directory;info->FileNameLength=(DWORD)n;memcpy(info->FileName,leaf,n);ok=SetFileInformationByHandle(h,FileRenameInfo,info,(DWORD)(sizeof(*info)+n));free(info);if(!ok)return wr_fail(e,"rename-no-replace");if(!wr_flush(h,e)||!wr_recheck(c,e))return 0;return 1;}
HANDLE wr_job(wr_error *e){HANDLE h=CreateJobObjectW(NULL,NULL);JOBOBJECT_EXTENDED_LIMIT_INFORMATION x;JOBOBJECT_BASIC_UI_RESTRICTIONS ui;if(!h){wr_fail(e,"job-create");return NULL;}memset(&x,0,sizeof(x));x.BasicLimitInformation.LimitFlags=JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE|JOB_OBJECT_LIMIT_PROCESS_MEMORY|JOB_OBJECT_LIMIT_JOB_MEMORY|JOB_OBJECT_LIMIT_PROCESS_TIME;x.ProcessMemoryLimit=512ull*1024*1024;x.JobMemoryLimit=1024ull*1024*1024;x.BasicLimitInformation.PerProcessUserTimeLimit.QuadPart=60ll*10000000;
 if(!SetInformationJobObject(h,JobObjectExtendedLimitInformation,&x,sizeof(x))){CloseHandle(h);wr_fail(e,"job-limits");return NULL;}(void)ui;return h;}
int wr_spawn(HANDLE job,const WCHAR *exe,WCHAR *command,HANDLE *handles,size_t count,HANDLE input,HANDLE output,int fault,wr_process *p,wr_error *e){STARTUPINFOEXW s;PROCESS_INFORMATION pi;SIZE_T size=0;BOOL member=FALSE;size_t i;int ok=0;DWORD saved=0;memset(p,0,sizeof(*p));memset(&s,0,sizeof(s));memset(&pi,0,sizeof(pi));s.StartupInfo.cb=sizeof(s);s.StartupInfo.dwFlags=STARTF_USESTDHANDLES;s.StartupInfo.hStdInput=input;s.StartupInfo.hStdOutput=output;s.StartupInfo.hStdError=output;
 if(wr_launch_blocked)return wr_refuse(e,"cleanup-unconfirmed-no-launch");if(!count||count>8)return wr_refuse(e,"inherit-list-bound");for(i=0;i<count;i++)if(!SetHandleInformation(handles[i],HANDLE_FLAG_INHERIT,HANDLE_FLAG_INHERIT))goto done;
 InitializeProcThreadAttributeList(NULL,1,0,&size);s.lpAttributeList=malloc(size);if(!s.lpAttributeList){wr_refuse(e,"allocation");goto done;}if(!InitializeProcThreadAttributeList(s.lpAttributeList,1,0,&size))goto done;
 if(!UpdateProcThreadAttribute(s.lpAttributeList,0,PROC_THREAD_ATTRIBUTE_HANDLE_LIST,handles,sizeof(HANDLE)*count,NULL,NULL))goto attrs;
 if(!CreateProcessW(exe,command,NULL,NULL,TRUE,CREATE_SUSPENDED|EXTENDED_STARTUPINFO_PRESENT|CREATE_NO_WINDOW,NULL,NULL,&s.StartupInfo,&pi))goto attrs;
 if(fault){if(AssignProcessToJobObject(NULL,pi.hProcess)){SetLastError(ERROR_INVALID_DATA);}goto kill;/* actual invalid-job native failure, before resume */}
 if(!IsProcessInJob(pi.hProcess,job,&member))goto kill;if(!member&&!AssignProcessToJobObject(job,pi.hProcess))goto kill;
 member=FALSE;if(!IsProcessInJob(pi.hProcess,job,&member)||!member){SetLastError(ERROR_INVALID_DATA);goto kill;}
 if(ResumeThread(pi.hThread)==(DWORD)-1)goto kill;p->process=pi.hProcess;p->thread=pi.hThread;p->pid=pi.dwProcessId;ok=1;goto attrs;
 kill:saved=GetLastError();{
 DWORD cleanup=0,waited;if(!TerminateProcess(pi.hProcess,125))cleanup=GetLastError();waited=WaitForSingleObject(pi.hProcess,10000);
 if(e){e->cleanup_native=waited==WAIT_FAILED?GetLastError():cleanup;e->wait_result=waited;}
 if(waited!=WAIT_OBJECT_0){p->process=pi.hProcess;p->thread=pi.hThread;p->pid=pi.dwProcessId;p->cleanup_unconfirmed=1;wr_launch_blocked=1;if(e)e->cleanup_unconfirmed=1;}
 else{CloseHandle(pi.hThread);CloseHandle(pi.hProcess);}SetLastError(saved);
 }
 attrs:DeleteProcThreadAttributeList(s.lpAttributeList);
 done:if(!ok){saved=GetLastError();wr_fail(e,"spawn-contained-before-resume");}free(s.lpAttributeList);for(i=0;i<count;i++)SetHandleInformation(handles[i],HANDLE_FLAG_INHERIT,0);if(!ok)SetLastError(saved);return ok;}
int wr_wait(wr_process *p,DWORD ms,DWORD *status,wr_error *e){DWORD wait=WaitForSingleObject(p->process,ms);if(wait!=WAIT_OBJECT_0){if(e)e->wait_result=wait;if(wait!=WAIT_FAILED)SetLastError(ERROR_TIMEOUT);return wr_fail(e,wait==WAIT_FAILED?"process-wait-failed":"process-deadline");}if(!GetExitCodeProcess(p->process,status)||*status==STILL_ACTIVE)return wr_fail(e,"process-exit-status");return 1;}
int wr_terminate(wr_process *p,wr_error *e){DWORD status;if(p->process&&WaitForSingleObject(p->process,0)!=WAIT_OBJECT_0&&!TerminateProcess(p->process,125))return wr_fail(e,"terminate-owned-process");return wr_wait(p,10000,&status,e);}
void wr_process_close(wr_process *p){if(p->process&&WaitForSingleObject(p->process,0)!=WAIT_OBJECT_0){p->cleanup_unconfirmed=1;wr_launch_blocked=1;return;}if(p->thread)CloseHandle(p->thread);if(p->process)CloseHandle(p->process);memset(p,0,sizeof(*p));}
void wr_close(wr_context *c){while(c->count)CloseHandle(c->pins[--c->count]);c->directory=INVALID_HANDLE_VALUE;}
