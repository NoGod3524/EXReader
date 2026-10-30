/* SPDX-License-Identifier: MIT */
#include "lm_win_restart_reader.h"
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
/* Pinned C01 provider layout (extras/migration/windows_admission_lease_20261030):
 * 80-byte lease file = 64-byte identity header + generation(u64) + pending(u64).
 * The provider is frozen and outside this worktree, so its two weaknesses are
 * contained here instead of patched: it opens the lease file with OPEN_ALWAYS
 * (a deleted lease would be silently re-initialised) and it caches
 * generation/pending at acquire time (its own check re-verifies only the
 * 64-byte header). This adapter therefore (a) qualifies the lease namespace with
 * deny-delete pins and exact size/header/generation/PENDING reads before any
 * lease handle exists, and (b) re-reads the full 80-byte region from disk on
 * every check instead of trusting either the provider cache or its own cache. */
#define RR_LEASE_SIZE 80u
#define RR_HDR_ID 58u
#define RR_GEN_OFFSET 64u
#define RR_PENDING_OFFSET 72u
struct lm_rr {
 lm_wl_lease *lease;wr_context context;int initialized,qualified,lease_pinned;
 HANDLE lease_dir,lease_file;DWORD lease_volume,lease_index_high,lease_index_low;
 char identity[49];uint64_t generation,gen_disk,pending_disk;
 HANDLE files[32],target;unsigned opened;
 wr_identity ids[32],target_id;char hashes[32][65],payload[65];
 lm_rr_class classification;WCHAR source[WR_PATH],dest[WR_PATH];int published;
};
static int refuse(wr_error *e,const char *why){
 SetLastError(ERROR_INVALID_DATA);if(e){e->native=ERROR_INVALID_DATA;e->reason=why;}return 0;
}
static int native(wr_error *e,const char *why){
 if(e){e->native=GetLastError();e->reason=why;}return 0;
}
static int eqtext(const wr_identity *id,const char *text){
 char s[49];wr_identity_text(id,s);return !strcmp(s,text);
}
static int same(const lm_wr_record *a,const lm_wr_record *b){
 return !strcmp(a->source,b->source)&&!strcmp(a->run,b->run)&&
 !strcmp(a->root,b->root)&&!strcmp(a->parent,b->parent)&&
 !strcmp(a->target,b->target)&&!strcmp(a->payload_sha,b->payload_sha);
}
static int hash(HANDLE h,const wr_identity *want,size_t max,const char *sha,wr_error *e){
 void *bytes=NULL;size_t n=0;wr_identity id;char actual[65];int ok;
 if(!wr_identity_get(h,0,&id,e)||!wr_identity_equal(&id,want)||id.size!=want->size)
  return refuse(e,"restart-held-identity");
 if(!wr_read(h,&bytes,&n,max,e))return 0;
 lm_sha_bytes(bytes,n,actual);free(bytes);ok=!strcmp(actual,sha);
 return ok?1:refuse(e,"restart-held-bytes");
}
static int presence(const WCHAR *p,int *exists,wr_error *e){
 DWORD a=GetFileAttributesW(p);if(a!=INVALID_FILE_ATTRIBUTES){*exists=1;return 1;}
 if(GetLastError()!=ERROR_FILE_NOT_FOUND)return native(e,"restart-namespace-unknown");
 *exists=0;return 1;
}
static uint64_t read64(const unsigned char *p){uint64_t v;memcpy(&v,p,sizeof v);return v;}
static int pread_exact(HANDLE h,uint64_t off,void *buf,size_t n){
 OVERLAPPED o;DWORD got=0;memset(&o,0,sizeof(o));
 o.Offset=(DWORD)off;o.OffsetHigh=(DWORD)(off>>32);
 return ReadFile(h,buf,(DWORD)n,&got,&o)&&got==(DWORD)n;
}
static int header_ok(const unsigned char *h,const char id[49]){
 static const char magic[10]={'E','X','R','L','E','A','S','E','1','\n'};
 unsigned i;
 if(memcmp(h,magic,10)||memcmp(h+10,id,48)||h[RR_HDR_ID]!='\n')return 0;
 for(i=RR_HDR_ID+1;i<RR_GEN_OFFSET;i++)if(h[i])return 0;
 return 1;
}
static int identity_ok(const char id[49]){
 size_t i;
 for(i=0;i<48;i++)if(!((id[i]>='0'&&id[i]<='9')||(id[i]>='a'&&id[i]<='f')))return 0;
 return id[48]==0;
}
static void lease_leaf(WCHAR leaf[64],const char id[49]){
 size_t i;for(i=0;i<48;i++)leaf[i]=(WCHAR)id[i];
 memcpy(leaf+48,L".lease",7*sizeof(WCHAR));
}
/* Qualify the lease namespace BEFORE the provider may create or initialise it. */
static int lease_pin(lm_rr *r,const WCHAR *dir,const char id[49],uint64_t want,wr_error *e){
 WCHAR leaf[64],path[WR_PATH+64];unsigned char hdr[RR_LEASE_SIZE];
 LARGE_INTEGER size;BY_HANDLE_FILE_INFORMATION fi;
 if(wcslen(dir)+64>=WR_PATH)return refuse(e,"restart-lease-path");
 r->lease_dir=CreateFileW(dir,FILE_READ_ATTRIBUTES|READ_CONTROL|SYNCHRONIZE,
  FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_EXISTING,
  FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,NULL);
 if(r->lease_dir==INVALID_HANDLE_VALUE)return native(e,"restart-lease-dir");
 if(!GetFileInformationByHandle(r->lease_dir,&fi))return native(e,"restart-lease-dir-info");
 if(!(fi.dwFileAttributes&FILE_ATTRIBUTE_DIRECTORY)||(fi.dwFileAttributes&FILE_ATTRIBUTE_REPARSE_POINT))
  return refuse(e,"restart-lease-dir-kind");
 r->lease_pinned=1;                               /* deny-delete from here on */
 if(!identity_ok(id))return refuse(e,"restart-lease-identity");
 lease_leaf(leaf,id);
 memcpy(r->identity,id,49);
 if(swprintf(path,WR_PATH+64,L"%ls\\%ls",dir,leaf)<0)return refuse(e,"restart-lease-path");
 r->lease_file=CreateFileW(path,GENERIC_READ|FILE_READ_ATTRIBUTES|READ_CONTROL|SYNCHRONIZE,
  FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_EXISTING,
  FILE_ATTRIBUTE_NORMAL|FILE_FLAG_OPEN_REPARSE_POINT,NULL);
 if(r->lease_file==INVALID_HANDLE_VALUE)return native(e,"restart-lease-missing");
 if(!GetFileInformationByHandle(r->lease_file,&fi))return native(e,"restart-lease-info");
 if((fi.dwFileAttributes&(FILE_ATTRIBUTE_DIRECTORY|FILE_ATTRIBUTE_REPARSE_POINT))||fi.nNumberOfLinks!=1)
  return refuse(e,"restart-lease-kind");
 r->lease_volume=fi.dwVolumeSerialNumber;
 r->lease_index_high=fi.nFileIndexHigh;r->lease_index_low=fi.nFileIndexLow;
 if(!GetFileSizeEx(r->lease_file,&size))return native(e,"restart-lease-size");
 if(size.QuadPart==0)return refuse(e,"restart-lease-empty");
 if(size.QuadPart!=(LONGLONG)RR_LEASE_SIZE)return refuse(e,"restart-lease-size");
 if(!pread_exact(r->lease_file,0,hdr,RR_LEASE_SIZE))return native(e,"restart-lease-read");
 if(!header_ok(hdr,id))return refuse(e,"restart-lease-header");
 r->gen_disk=read64(hdr+RR_GEN_OFFSET);r->pending_disk=read64(hdr+RR_PENDING_OFFSET);
 if(r->gen_disk!=want)return refuse(e,"restart-lease-generation");
 if(r->pending_disk!=1)return refuse(e,"restart-lease-pending");
 return 1;
}
/* Reader-owned shared window over [0,80): independent of the provider's own
 * 4096/4097 admission locks, so it never collides with a live C01 holder. */
static int lease_window(lm_rr *r,wr_error *e){
 OVERLAPPED o;memset(&o,0,sizeof(o));
 if(!LockFileEx(r->lease_file,LOCKFILE_FAIL_IMMEDIATELY,0,RR_LEASE_SIZE,0,&o))
  return native(e,"restart-lease-window");
 return 1;
}
static int lease_verify(lm_rr *r,wr_error *e){
 unsigned char hdr[RR_LEASE_SIZE];BY_HANDLE_FILE_INFORMATION fi;
 if(!GetFileInformationByHandle(r->lease_file,&fi))return native(e,"restart-lease-info");
 if(fi.dwVolumeSerialNumber!=r->lease_volume||fi.nFileIndexHigh!=r->lease_index_high||
    fi.nFileIndexLow!=r->lease_index_low)return refuse(e,"restart-lease-identity");
 if(fi.nNumberOfLinks!=1)return refuse(e,"restart-lease-kind");
 if(!pread_exact(r->lease_file,0,hdr,RR_LEASE_SIZE))return native(e,"restart-lease-read");
 if(!header_ok(hdr,r->identity))return refuse(e,"restart-lease-header");
 if(read64(hdr+RR_GEN_OFFSET)!=r->gen_disk||read64(hdr+RR_PENDING_OFFSET)!=r->pending_disk)
  return refuse(e,"restart-lease-disk-drift");
 if(lm_wl_generation(r->lease)!=r->gen_disk)return refuse(e,"restart-lease-cache-drift");
 if(!lm_wl_pending(r->lease)||r->pending_disk!=1)return refuse(e,"restart-lease-state");
 return 1;
}
static int lease_check(lm_rr *r,wr_error *e){
 lm_wl_error le={0};
 if(lm_wl_check(r->lease,&le)!=LM_WL_OK)return refuse(e,"restart-lease-state");
 if(!lease_verify(r,e))return 0;
 return lm_wl_require_generation(r->lease,r->generation)==LM_WL_OK?
  1:refuse(e,"restart-lease-state");
}
static int namespace_check(lm_rr *r,wr_error *e){
 WIN32_FIND_DATAW data;HANDLE find;WCHAR pattern[WR_PATH],leaf[40];unsigned seen=0,i;int known;
 if(swprintf(pattern,WR_PATH,L"%ls\\bridge-slot-*.rec",r->context.path)<0)
  return refuse(e,"restart-scan-path");
 find=FindFirstFileW(pattern,&data);if(find==INVALID_HANDLE_VALUE)return native(e,"restart-scan");
 do{
  known=0;for(i=0;i<r->opened;i++){swprintf(leaf,40,L"bridge-slot-%02u.rec",i);
   if(!wcscmp(data.cFileName,leaf)){known=1;break;}}
  if(!known){FindClose(find);return refuse(e,"restart-extra-slot");}
  seen++;
 }while(FindNextFileW(find,&data));
 if(GetLastError()!=ERROR_NO_MORE_FILES){FindClose(find);return native(e,"restart-scan-end");}
 if(!FindClose(find))return native(e,"restart-scan-close");
 return seen==r->opened?1:refuse(e,"restart-slot-count");
}
int lm_rr_check(lm_rr *r,wr_error *e){
 unsigned i;int source,dest;
 if(!r||r->classification==LM_RR_REFUSED||r->classification==LM_RR_NAMESPACE_CONFLICT||
    !r->qualified||!lease_check(r,e)||!wr_recheck(&r->context,e)||!namespace_check(r,e))
  return refuse(e,"restart-not-qualified");
 if(!presence(r->source,&source,e)||!presence(r->dest,&dest,e)||
    source==dest||dest!=r->published)return refuse(e,"restart-namespace-changed");
 for(i=0;i<r->opened;i++)if(!hash(r->files[i],&r->ids[i],LM_WR_RECORD_MAX,r->hashes[i],e)||
    !wr_private_acl(r->files[i],0,&r->context,e))return 0;
 return hash(r->target,&r->target_id,WR_RECORD_MAX,r->payload,e)&&
  wr_private_acl(r->target,0,&r->context,e)&&lease_check(r,e);
}
void lm_rr_close(lm_rr *r){
 unsigned i;if(!r)return;
 for(i=0;i<r->opened;i++)CloseHandle(r->files[i]);
 if(r->target!=INVALID_HANDLE_VALUE)CloseHandle(r->target);
 /* initialized, not qualified: a failed wr_prepare can already hold pins. */
 if(r->initialized)wr_close(&r->context);
 if(r->lease_file!=INVALID_HANDLE_VALUE)CloseHandle(r->lease_file);
 if(r->lease_dir!=INVALID_HANDLE_VALUE)CloseHandle(r->lease_dir);
 lm_wl_release(r->lease);free(r);
}
int lm_rr_open(const WCHAR *lease_dir,const char lease_identity[49],
 uint64_t generation,const WCHAR *root,const WCHAR *source_leaf,const WCHAR *public_leaf,
 const lm_wr_record *expected,unsigned slots,lm_rr **out,lm_rr_result *result,wr_error *e){
 lm_rr *r=NULL;lm_wl_error le={0};lm_sb encoded;lm_wr_record previous={0},record;
 unsigned i,valid=0;int reserved=0,source,dest;WCHAR leaf[40],unused[WR_PATH];
 void *bytes=NULL;size_t size=0,j;int zero;HANDLE h;
 if(!out||!result)return refuse(e,"restart-output");*out=NULL;memset(result,0,sizeof(*result));
 lm_sb_init(&encoded);
 if(!root||!source_leaf||!public_leaf||!expected||expected->ordinal||!slots||slots>32||
    !lm_wr_record_encode(expected,&encoded)){
  lm_sb_free(&encoded);return refuse(e,"restart-arguments");
 }
 lm_sb_free(&encoded);r=calloc(1,sizeof(*r));
 if(!r)return refuse(e,"restart-allocation");
 r->target=INVALID_HANDLE_VALUE;r->lease_dir=INVALID_HANDLE_VALUE;
 r->lease_file=INVALID_HANDLE_VALUE;r->generation=generation;
 *out=r;result->slots=slots;
 if(!lease_pin(r,lease_dir,lease_identity,generation,e))goto fail;
 if(lm_wl_acquire(lease_dir,lease_identity,LM_WL_EXCLUSIVE,0,&r->lease,&le)!=LM_WL_OK){
  refuse(e,"restart-exclusive-acquire");goto fail;
 }
 if(!lease_window(r,e))goto fail;
 result->generation=lm_wl_generation(r->lease);result->pending=lm_wl_pending(r->lease);
 if(!lease_check(r,e))goto done;
 r->initialized=1;
 if(!wr_prepare(&r->context,root,0,e)){
  /* wr_prepare pins ancestors before it can fail; drop them at once and keep
     only the lease custody this object was created for. */
  wr_close(&r->context);r->initialized=0;goto done;
 }
 r->qualified=1;
 if(r->context.count<2||!eqtext(&r->context.root,expected->root)||
    !eqtext(&r->context.identities[r->context.count-2],expected->parent)||
    !wr_join(&r->context,source_leaf,r->source,e)||
    !wr_join(&r->context,public_leaf,unused,e)){
  refuse(e,"restart-root-binding");goto done;
 }
 if(wcslen(r->context.paths[r->context.count-2])+wcslen(public_leaf)+2>=WR_PATH){
  refuse(e,"restart-path-limit");goto done;
 }
 swprintf(r->dest,WR_PATH,L"%ls\\%ls",r->context.paths[r->context.count-2],public_leaf);
 if(!presence(r->source,&source,e)||!presence(r->dest,&dest,e))goto done;
 if(source==dest){r->classification=LM_RR_NAMESPACE_CONFLICT;goto done;}
 r->published=dest;
 h=CreateFileW(dest?r->dest:r->source,GENERIC_READ|READ_CONTROL,FILE_SHARE_READ,NULL,
   OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,NULL);
 if(h==INVALID_HANDLE_VALUE){native(e,"restart-target-open");goto done;}
 r->target=h;
 if(!wr_identity_get(h,0,&r->target_id,e)||!eqtext(&r->target_id,expected->target)||
    !wr_private_acl(h,0,&r->context,e)){
  refuse(e,"restart-target-binding");goto done;
 }
 memcpy(r->payload,expected->payload_sha,65);
 if(!hash(h,&r->target_id,WR_RECORD_MAX,r->payload,e))goto done;
 for(i=0;i<slots;i++){
  swprintf(leaf,40,L"bridge-slot-%02u.rec",i);
  h=wr_open(&r->context,leaf,GENERIC_READ,FILE_SHARE_READ,0,e);
  if(h==INVALID_HANDLE_VALUE)goto done;r->files[r->opened++]=h;
  if(!wr_identity_get(h,0,&r->ids[i],e)||!wr_private_acl(h,0,&r->context,e)||
     !wr_read(h,&bytes,&size,LM_WR_RECORD_MAX,e))goto done;
  lm_sha_bytes(bytes,size,r->hashes[i]);zero=size==LM_WR_RECORD_MAX;
  for(j=0;zero&&j<size;j++)if(((unsigned char*)bytes)[j])zero=0;
  if(zero){reserved=1;free(bytes);bytes=NULL;continue;}
  if(reserved||!lm_wr_record_decode(bytes,size,&record)||record.ordinal!=i||
     !same(&record,expected)||(i&&!lm_wr_record_links(&record,&previous,&r->ids[i-1]))){
   refuse(e,"restart-record-chain");goto done;
  }
  free(bytes);bytes=NULL;previous=record;valid++;
 }
 r->classification=valid==slots?LM_RR_COMPLETE_EVIDENCE:valid?LM_RR_PREFIX:LM_RR_RESERVED;
 if(!lm_rr_check(r,e))r->classification=LM_RR_REFUSED;
done:
 free(bytes);result->classification=r->classification;result->valid_records=valid;
 result->published=r->published;result->target=r->target_id;
 for(i=0;i<r->opened;i++)result->records[i]=r->ids[i];
 return 1;
fail:
 /* No custody was established: release every pin/handle and hand back nothing. */
 free(bytes);result->classification=LM_RR_REFUSED;result->valid_records=0;
 result->published=0;*out=NULL;lm_rr_close(r);return 0;
}
