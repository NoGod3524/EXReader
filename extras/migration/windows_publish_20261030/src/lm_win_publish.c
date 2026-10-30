/* SPDX-License-Identifier: MIT */
#include "lm_win_publish.h"
#include <winternl.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#include <stddef.h>
typedef struct {BOOLEAN replace; HANDLE root; ULONG bytes; WCHAR name[1];} rename_info;
typedef char handle_layout[(offsetof(rename_info,root)==sizeof(HANDLE))?1:-1];
typedef char name_layout[(offsetof(rename_info,name)==2*sizeof(HANDLE)+sizeof(ULONG))?1:-1];
static int fail(wr_error *e,const char *why) {
  if(e){e->native=GetLastError();e->reason=why;}return 0;
}
static int refuse(wr_error *e,const char *why) {
  SetLastError(ERROR_INVALID_DATA);return fail(e,why);
}
static int leaf(wr_context *c,const WCHAR *s,wr_error *e) {
  WCHAR unused[WR_PATH];return s&&wr_join(c,s,unused,e);
}
static int digest(HANDLE h,const wr_identity *want,const char *sha,wr_error *e) {
  void *bytes=NULL;size_t n=0;wr_identity id;char got[65];int ok;
  if(!wr_identity_get(h,0,&id,e)||!wr_identity_equal(&id,want)||id.size!=want->size)
    return refuse(e,"publish-source-identity");
  if(!wr_read(h,&bytes,&n,WR_RECORD_MAX,e))return 0;
  lm_sha_bytes(bytes,n,got);free(bytes);ok=!strcmp(sha,got);
  return ok?1:refuse(e,"publish-source-bytes");
}
static int named(wr_context *c,const WCHAR *name,HANDLE h,
                 const wr_identity *want,wr_error *e) {
  WCHAR p[WR_PATH];HANDLE check;wr_identity id;int ok;
  if(!wr_join(c,name,p,e))return 0;
  check=CreateFileW(p,FILE_READ_ATTRIBUTES|READ_CONTROL,
    FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,NULL,OPEN_EXISTING,
    FILE_FLAG_OPEN_REPARSE_POINT,NULL);
  if(check==INVALID_HANDLE_VALUE)return fail(e,"publish-source-entry");
  ok=wr_identity_get(check,0,&id,e)&&wr_identity_equal(&id,want);
  if(!CloseHandle(check))return fail(e,"publish-source-check-close");
  if(!ok)return refuse(e,"publish-source-entry-identity");
  return wr_private_acl(h,0,c,e);
}
typedef struct {
 wr_context *metadata;HANDLE parent;wr_identity parent_id,root_id;
 const WCHAR *parent_path;void *context;
 int (*recheck)(void *,wr_error *);
} publish_view;
static int old_check(void *p,wr_error *e){return wr_recheck((wr_context*)p,e);}
static int publish(publish_view *v,HANDLE source,const WCHAR *source_leaf,
                  const WCHAR *public_leaf,const wr_identity *expected,
                  const char expected_sha[65],lm_wp_result *r,wr_error *e) {
  wr_context *c=v->metadata;
  typedef NTSTATUS (NTAPI *set_fn)(HANDLE,PIO_STATUS_BLOCK,PVOID,ULONG,FILE_INFORMATION_CLASS);
  typedef ULONG (WINAPI *err_fn)(NTSTATUS);
  HMODULE dll;FARPROC symbol;set_fn set;err_fn translate;rename_info *info=NULL;
  IO_STATUS_BLOCK io;NTSTATUS status;HANDLE check=INVALID_HANDLE_VALUE;
  WCHAR path[WR_PATH],source_path[WR_PATH];wr_identity parent,id;size_t n,i;
  int ok=0;DWORD absent;
  if(!r)return refuse(e,"publish-result-required");memset(r,0,sizeof(*r));
  if(!c||!v->parent||!expected||!expected_sha||source==INVALID_HANDLE_VALUE||
      !leaf(c,source_leaf,e)||!leaf(c,public_leaf,e))return refuse(e,"publish-arguments");
  for(i=0;i<64;i++)if(!((expected_sha[i]>='0'&&expected_sha[i]<='9')||
     (expected_sha[i]>='a'&&expected_sha[i]<='f')))return refuse(e,"publish-sha-format");
  if(expected_sha[64])return refuse(e,"publish-sha-terminator");
  if(!v->recheck(v->context,e)||!wr_identity_get(v->parent,1,&parent,e)||
     !wr_identity_equal(&parent,&v->parent_id)||
     parent.volume!=v->root_id.volume||expected->volume!=parent.volume)
    return refuse(e,"publish-parent-binding");
  if(!named(c,source_leaf,source,expected,e)||!digest(source,expected,expected_sha,e))return 0;
  if(wcslen(v->parent_path)+wcslen(public_leaf)+2>=WR_PATH)
    return refuse(e,"publish-path-bound");
  swprintf(path,WR_PATH,L"%ls\\%ls",v->parent_path,public_leaf);
  if(!wr_join(c,source_leaf,source_path,e))return 0;
  /* Inspect absence only to reject unknown states; native no-replace is authority. */
  if(GetFileAttributesW(path)!=INVALID_FILE_ATTRIBUTES)return refuse(e,"publish-destination-exists");
  absent=GetLastError();if(absent!=ERROR_FILE_NOT_FOUND)return fail(e,"publish-destination-unknown");
  dll=GetModuleHandleW(L"ntdll.dll");
  if(!dll)return refuse(e,"publish-native-module");
  symbol=GetProcAddress(dll,"NtSetInformationFile");memcpy(&set,&symbol,sizeof(set));
  symbol=GetProcAddress(dll,"RtlNtStatusToDosError");memcpy(&translate,&symbol,sizeof(translate));
  if(!set||!translate)return refuse(e,"publish-native-api");
  n=wcslen(public_leaf)*sizeof(WCHAR);info=calloc(1,sizeof(*info)+n);
  if(!info)return refuse(e,"publish-allocation");
  info->replace=FALSE;info->root=v->parent;info->bytes=(ULONG)n;
  memcpy(info->name,public_leaf,n);memset(&io,0,sizeof(io));
  if(!v->recheck(v->context,e)||!named(c,source_leaf,source,expected,e)||
     !digest(source,expected,expected_sha,e))goto done;
  r->rename_attempted=1;
  status=set(source,&io,info,(ULONG)(sizeof(*info)+n),(FILE_INFORMATION_CLASS)10);
  r->ntstatus=status;r->io_status=io.Status;
  if(status!=0||io.Status!=0){SetLastError(translate(status?status:io.Status));fail(e,"publish-native-no-replace");goto done;}
  r->published=1;
  if(!wr_flush(source,e)||!v->recheck(v->context,e)||!digest(source,expected,expected_sha,e))goto done;
  check=CreateFileW(path,FILE_READ_ATTRIBUTES|READ_CONTROL,
    FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,NULL,OPEN_EXISTING,
    FILE_FLAG_OPEN_REPARSE_POINT,NULL);
  if(check==INVALID_HANDLE_VALUE){fail(e,"publish-destination-open");goto done;}
  if(!wr_identity_get(check,0,&id,e)||!wr_identity_equal(&id,expected)||
     !wr_private_acl(check,0,c,e)){refuse(e,"publish-destination-binding");goto done;}
  if(GetFileAttributesW(source_path)!=INVALID_FILE_ATTRIBUTES||
     GetLastError()!=ERROR_FILE_NOT_FOUND){refuse(e,"publish-source-not-absent");goto done;}
  r->identity=id;memcpy(r->sha,expected_sha,65);r->verified=1;ok=1;
done:
  free(info);if(check!=INVALID_HANDLE_VALUE&&!CloseHandle(check)){r->verified=0;ok=fail(e,"publish-destination-close");}
  return ok;
}

int lm_wp_publish(wr_context *c,HANDLE source,const WCHAR *from,const WCHAR *to,
 const wr_identity *id,const char sha[65],lm_wp_result *r,wr_error *e) {
 publish_view v;
 if(!c||c->count<2){if(r)memset(r,0,sizeof(*r));return refuse(e,"publish-context");}
 v.metadata=c;v.parent=c->pins[c->count-2];v.parent_id=c->identities[c->count-2];
 v.root_id=c->root;v.parent_path=c->paths[c->count-2];v.context=c;v.recheck=old_check;
 return publish(&v,source,from,to,id,sha,r,e);
}
/* Distinct custody type: never passed as wr_context to an original adapter API.
 * Directory writes are admitted from initial acquisition; DELETE is never shared.
 * The original context stays untouched until its caller explicitly closes it. */
struct lm_wp_custody {
 wr_context metadata; /* only ACL SIDs and root path, no original pins */
 HANDLE pins[WR_PINS];wr_identity ids[WR_PINS];WCHAR paths[WR_PINS][WR_PATH];
 unsigned count;
};
static int prepared_check(void *value,wr_error *e) {
 lm_wp_custody *p=(lm_wp_custody*)value;unsigned i;wr_identity held,entry;HANDLE h;
 if(!p||p->count<2)return refuse(e,"prepared-context");
 for(i=0;i<p->count;i++){
  if(!wr_identity_get(p->pins[i],1,&held,e)||!wr_identity_equal(&held,&p->ids[i]))
   return refuse(e,"prepared-held-identity");
  h=CreateFileW(p->paths[i],FILE_TRAVERSE|FILE_READ_ATTRIBUTES|READ_CONTROL,
    FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_EXISTING,
    FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,NULL);
  if(h==INVALID_HANDLE_VALUE)return fail(e,"prepared-path-open");
  if(!wr_identity_get(h,1,&entry,e)||!wr_identity_equal(&held,&entry)){
   CloseHandle(h);return refuse(e,"prepared-path-identity");
  }
  if(!CloseHandle(h))return fail(e,"prepared-check-close");
 }
 return wr_private_acl(p->pins[p->count-1],1,&p->metadata,e);
}
int lm_wp_custody_check(lm_wp_custody *p,wr_error *e){return prepared_check(p,e);}
void lm_wp_custody_close(lm_wp_custody *p) {
 if(!p)return;while(p->count)CloseHandle(p->pins[--p->count]);free(p);
}
int lm_wp_custody_prepare(wr_context *old,lm_wp_custody **out,wr_error *e) {
 lm_wp_custody *p;unsigned i;wr_identity actual;HANDLE h;
 if(!out)return refuse(e,"prepared-output");*out=NULL;
 if(!old||old->count<2||old->count>WR_PINS||!wr_recheck(old,e))
  return refuse(e,"prepared-original-qualification");
 p=calloc(1,sizeof(*p));if(!p)return refuse(e,"prepared-allocation");
 memcpy(p->metadata.user,old->user,sizeof(old->user));
 memcpy(p->metadata.system,old->system,sizeof(old->system));
 wcscpy(p->metadata.path,old->path);
 for(i=0;i<old->count;i++){
  h=CreateFileW(old->paths[i],FILE_TRAVERSE|FILE_READ_ATTRIBUTES|READ_CONTROL,
    FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_EXISTING,
    FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,NULL);
  if(h==INVALID_HANDLE_VALUE){fail(e,"prepared-pin-open");goto bad;}
  p->pins[p->count++]=h;p->ids[i]=old->identities[i];wcscpy(p->paths[i],old->paths[i]);
  if(!wr_identity_get(h,1,&actual,e)||!wr_identity_equal(&actual,&old->identities[i])){
   refuse(e,"prepared-transfer-identity");goto bad;
  }
 }
 if(!wr_recheck(old,e)||!prepared_check(p,e))goto bad;
 *out=p;return 1;
bad:lm_wp_custody_close(p);return 0;
}
int lm_wp_publish_prepared(lm_wp_custody *p,HANDLE source,const WCHAR *from,
 const WCHAR *to,const wr_identity *id,const char sha[65],lm_wp_result *r,wr_error *e) {
 publish_view v;
 if(!p||p->count<2){if(r)memset(r,0,sizeof(*r));return refuse(e,"prepared-context");}
 v.metadata=&p->metadata;v.parent=p->pins[p->count-2];v.parent_id=p->ids[p->count-2];
 v.root_id=p->ids[p->count-1];v.parent_path=p->paths[p->count-2];v.context=p;v.recheck=prepared_check;
 return publish(&v,source,from,to,id,sha,r,e);
}
