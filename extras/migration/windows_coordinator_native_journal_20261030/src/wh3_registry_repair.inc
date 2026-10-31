/* SPDX-License-Identifier: MIT
 * Included by wh3_registry.c to share the existing protected registry and
 * native identity primitives. No ordinary open enters this repair path. */
#include <exr_wh3_repair.h>
#include <stddef.h>
#define RRMAX (64u*1024u*1024u)
#define RRPATH (MAX_PATH+192u)
#pragma pack(push,1)
typedef struct {wh3w_identity id;uint64_t bytes;char sha[65];} rr_archive;
typedef struct {
 char magic[8];unsigned char binding[RBYTES];char input_sha[65],nonce[33];
 rr_archive archive[3];uint64_t keep[3];uint32_t gate_bytes;
 unsigned char gate[1032];char predecessor[65],seal[65];
} rr_plan;
#pragma pack(pop)
typedef struct {unsigned char *data;DWORD bytes;wh3w_identity id;char sha[65];} rr_blob;
static void rr_free(rr_blob *b) {free(b->data);memset(b,0,sizeof(*b));}
static int rr_seek(HANDLE h,uint64_t offset) {
 LARGE_INTEGER pos;pos.QuadPart=(LONGLONG)offset;return SetFilePointerEx(h,pos,NULL,FILE_BEGIN)!=0;
}
static int rr_read(HANDLE h,rr_blob *b) {
 LARGE_INTEGER size,after;wh3w_identity id;DWORD n=0;int ok=0;
 memset(b,0,sizeof(*b));
 if(!rid(h,&b->id,0)||!GetFileSizeEx(h,&size)||size.QuadPart<0||size.QuadPart>RRMAX)return 0;
 b->bytes=(DWORD)size.QuadPart;b->data=malloc(b->bytes?b->bytes:1);if(!b->data)return 0;
 if(!rr_seek(h,0)||!ReadFile(h,b->data,b->bytes,&n,NULL)||n!=b->bytes||
    !rid(h,&id,0)||!reqid(&id,&b->id)||!GetFileSizeEx(h,&after)||after.QuadPart!=size.QuadPart)goto done;
 wh_sha256_hex(b->data,b->bytes,b->sha);ok=1;
done:if(!ok)rr_free(b);return ok;
}
static int rr_plan_read(HKEY key,rr_plan *p) {
 DWORD type=0,n=sizeof(*p);char sha[65];size_t k;
 if(RegQueryValueExW(key,L"Repair",NULL,&type,(BYTE *)p,&n)!=ERROR_SUCCESS||
    type!=REG_BINARY||n!=sizeof(*p)||memcmp(p->magic,"WH3RPR01",8)||
    !rrecord_valid(p->binding)||!rhex(p->input_sha,64)||!rhex(p->nonce,32)||
    !rhex(p->predecessor,64)||!rhex(p->seal,64)||p->gate_bytes>sizeof(p->gate))return 0;
 wh_sha256_hex(p,offsetof(rr_plan,seal),sha);if(memcmp(sha,p->seal,65))return 0;
 for(k=0;k<3;k++)if(p->archive[k].bytes>RRMAX||!rhex(p->archive[k].sha,64)||
    p->keep[k]>RRMAX)return 0;
 for(k=p->gate_bytes;k<sizeof(p->gate);k++)if(p->gate[k])return 0;
 return p->keep[0]==p->gate_bytes&&p->keep[1]<=p->archive[1].bytes&&p->keep[2]<=p->archive[2].bytes;
}
static int rr_applied(HKEY key,const rr_plan *p) {
 DWORD n=65,type=0;char sha[65];
 return RegQueryValueExW(key,L"RepairApplied",NULL,&type,(BYTE *)sha,&n)==ERROR_SUCCESS&&
   type==REG_BINARY&&n==65&&!memcmp(sha,p->seal,65);
}
static int rr_archive_path(wh3wr_registration *r,const rr_plan *p,unsigned k,wchar_t path[RRPATH]) {
 HANDLE root;wh3w_identity id;wchar_t physical[MAX_PATH+128];DWORD n;int ok;
 if(k>=3)return 0;
 root=CreateFileW(r->root,FILE_READ_ATTRIBUTES,FILE_SHARE_READ,NULL,OPEN_EXISTING,
   FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,NULL);
 if(root==INVALID_HANDLE_VALUE)return 0;
 ok=rid(root,&id,1)&&reqid(&id,&r->ids[0]);
 n=ok?GetFinalPathNameByHandleW(root,physical,MAX_PATH+128,FILE_NAME_NORMALIZED|VOLUME_NAME_GUID):0;
 CloseHandle(root);
 return n&&n<MAX_PATH+128&&swprintf_s(path,RRPATH,L"%ls\\repair-%hs-%u.raw",physical,p->nonce,k)>0;
}
static int rr_history(wh3wr_registration *r,const rr_plan *p) {
 wchar_t name[80];rr_plan check;DWORD n=sizeof(check),type=0;
 if(swprintf_s(name,80,L"Repair-%hs",p->seal)<0)return 0;
 if(rabsent(r->key,name)){
  if(RegSetValueExW(r->key,name,0,REG_BINARY,(const BYTE *)p,sizeof(*p))!=ERROR_SUCCESS||
     RegFlushKey(r->key)!=ERROR_SUCCESS)return 0;
 }
 return RegQueryValueExW(r->key,name,NULL,&type,(BYTE *)&check,&n)==ERROR_SUCCESS&&
   type==REG_BINARY&&n==sizeof(check)&&!memcmp(p,&check,sizeof(check));
}
static int rr_archives(wh3wr_registration *,const rr_plan *,HANDLE [3],rr_blob [3]);
static int rr_evidence(wh3wr_registration *r,const rr_plan *p) {
 HANDLE files[3]={INVALID_HANDLE_VALUE,INVALID_HANDLE_VALUE,INVALID_HANDLE_VALUE};
 rr_blob raw[3]={{0}};unsigned k;int ok=rr_archives(r,p,files,raw);
 /* The protected repair plan is a minimum acknowledged history, not merely
    permission to parse any older complete native pair. */
 if(ok)for(k=1;k<3;k++){
  wchar_t path[MAX_PATH];HANDLE current=INVALID_HANDLE_VALUE;rr_blob actual={0};
  if(swprintf_s(path,MAX_PATH,L"%ls\\%ls",r->root,k==1?L"journal.bin":L"intent.bin")<0){ok=0;break;}
  current=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,NULL);
  ok=current!=INVALID_HANDLE_VALUE&&rr_read(current,&actual)&&reqid(&actual.id,&r->ids[k+1])&&
     actual.bytes>=p->keep[k]&&!memcmp(actual.data,raw[k].data,(size_t)p->keep[k]);
  if(current!=INVALID_HANDLE_VALUE)CloseHandle(current);rr_free(&actual);if(!ok)break;
 }
 for(k=0;k<3;k++){rr_free(&raw[k]);if(files[k]!=INVALID_HANDLE_VALUE)CloseHandle(files[k]);}
 return ok;
}
static int rrepair_access(wh3wr_registration *r,int recovery) {
 rr_plan p;
 if(rabsent(r->key,L"Repair"))return 1;
 return recovery&&rr_plan_read(r->key,&p)&&rtbound(r,p.binding)&&rr_applied(r->key,&p)&&rr_evidence(r,&p);
}
static int rrepair_retire(wh3wr_registration *r) {
 rr_plan p;
 if(rabsent(r->key,L"Repair"))return 1;
 if(!rr_plan_read(r->key,&p)||!rtbound(r,p.binding)||!rr_applied(r->key,&p)||
    r->grant.generation!=rget(p.binding+56)+1||!rr_history(r,&p)||!rr_evidence(r,&p)||!rcurrent(r))return 0;
 /* A stale Applied digest is inert without an active Repair value. */
 return RegDeleteValueW(r->key,L"Repair")==ERROR_SUCCESS&&RegFlushKey(r->key)==ERROR_SUCCESS&&rabsent(r->key,L"Repair");
}
static int rr_input(wh3wr_registration *r,
 int (*validate)(void *,const void *,size_t,wh_binding *,wh_gates *),void *context,
 wh_binding *binding,wh_gates *gates,char input_sha[65]) {
 wchar_t name[80];unsigned char *bytes=NULL;DWORD n=0,got,type=0;char sha[65];int ok=0;
 if(!rtname(r,WH3WR_INPUT,name)||!rcurrent(r)||!ridentity(r,0)||
    RegQueryValueExW(r->key,name,NULL,&type,NULL,&n)!=ERROR_SUCCESS||type!=REG_BINARY||
    n<RTH+64||n>RTH+RTMAX+64)return 0;
 bytes=malloc(n);if(!bytes)return 0;got=n;
 if(RegQueryValueExW(r->key,name,NULL,&type,bytes,&got)!=ERROR_SUCCESS||type!=REG_BINARY||got!=n||
    memcmp(bytes,"WH3TXN01",8)||rget(bytes+8)!=WH3WR_INPUT||rget(bytes+16)!=n-RTH-64||
    !rtbound(r,bytes+24))goto done;
 wh_sha256_hex(bytes,n-64,sha);
 if(memcmp(sha,bytes+n-64,64)||!validate(context,bytes+RTH,n-RTH-64,binding,gates))goto done;
 wh_sha256_hex(bytes+RTH,n-RTH-64,input_sha);ok=rcurrent(r)&&ridentity(r,0);
done:free(bytes);return ok;
}
static int rr_root_pins(wh3wr_registration *r) {
 size_t k,len=wcslen(r->root);wchar_t path[MAX_PATH];wh3w_identity actual;
 for(k=3;k<=len;k++)if(k==3||k==len||r->root[k]==L'\\'){
  HANDLE h;if(r->np==RPINS)return 0;
  memcpy(path,r->root,k*sizeof(wchar_t));path[k]=0;
  h=CreateFileW(path,FILE_LIST_DIRECTORY|FILE_READ_ATTRIBUTES,FILE_SHARE_READ,NULL,
    OPEN_EXISTING,FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,NULL);
  if(h==INVALID_HANDLE_VALUE)return 0;
  r->pins[r->np]=h;wcscpy_s(r->paths[r->np],MAX_PATH,path);
  if(!rid(h,&r->pinids[r->np],1)){r->np++;return 0;}r->np++;
 }
 actual=r->pinids[r->np-1];return reqid(&actual,&r->ids[0]);
}
static int rr_raw_open(const wchar_t *library,wh3wr_registration **out,HANDLE files[3]) {
 const wchar_t *names[]={L"admission.bin",L"journal.bin",L"intent.bin"};
 wh3wr_registration *r=calloc(1,sizeof(*r));wchar_t path[MAX_PATH];OVERLAPPED lock={0};
 unsigned k;wh3w_identity actual;int ok=0;HKEY write=NULL;
 *out=NULL;if(!r)return 0;r->target=INVALID_HANDLE_VALUE;r->mode=WH3WG_RECOVER;
 if(!rpath(library,r->library,r->route)||!(r->enrollment_mutex=rmutex(r->route))||
    !ropenkey(r->route,0,&r->key)||!rread(r->key,r->record)||!rdecode(r)||
    !rabsent(r->key,L"Checkpoint")||!rpins(r)||!rr_root_pins(r)||!rtarget(r,1,0)||!rlegacy(r->library))goto done;
 for(k=0;k<3;k++){
  if(swprintf_s(path,MAX_PATH,L"%ls\\%ls",r->root,names[k])<0)goto done;
  files[k]=CreateFileW(path,GENERIC_READ|GENERIC_WRITE,FILE_SHARE_READ|(k?0:FILE_SHARE_WRITE),NULL,
    OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT|FILE_FLAG_WRITE_THROUGH,NULL);
  if(files[k]==INVALID_HANDLE_VALUE||!rid(files[k],&actual,0)||!reqid(&actual,&r->ids[k+1]))goto done;
  if(!k&&!LockFileEx(files[k],LOCKFILE_FAIL_IMMEDIATELY|LOCKFILE_EXCLUSIVE_LOCK,0,MAXDWORD,0,&lock))goto done;
 }
 if(!ridentity(r,0)||!rcurrent(r)||
    RegOpenKeyExW(r->key,L"",REG_OPTION_OPEN_LINK,KEY_READ|KEY_SET_VALUE|KEY_WOW64_64KEY,&write)!=ERROR_SUCCESS)goto done;
 RegCloseKey(r->key);r->key=write;*out=r;ok=1;
done:if(!ok)(void)wh3wr_close(r);return ok;
}

static int rr_archives(wh3wr_registration *r,const rr_plan *p,HANDLE files[3],rr_blob raw[3]) {
 unsigned k;wchar_t path[RRPATH];
 for(k=0;k<3;k++){
  if(!rr_archive_path(r,p,k,path))return 0;
  files[k]=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,NULL);
  if(files[k]==INVALID_HANDLE_VALUE||!rr_read(files[k],&raw[k])||
     !reqid(&raw[k].id,&p->archive[k].id)||raw[k].bytes!=p->archive[k].bytes||
     memcmp(raw[k].sha,p->archive[k].sha,65))return 0;
 }
 return 1;
}
static int rr_scan(HANDLE files[3],wh3wr_registration *r,const wh_binding *binding,const wh_gates *gates,
 wh3r_scan *ack,wh3r_gate_scan *gate) {
 return wh3r_scan_ack(files[1],files[2],binding,gates,ack)&&
   wh3r_scan_gate(files[0],r->domain,&r->grant,binding,gates,ack,gate);
}
static int rr_plan_targets(const rr_plan *p,const wh3r_scan *ack,const wh3r_gate_scan *gate) {
 return p->keep[0]==gate->target_bytes&&p->gate_bytes==gate->target_bytes&&
   p->keep[1]==ack->journal_keep_bytes&&p->keep[2]==ack->intent_keep_bytes&&
   !memcmp(p->gate,gate->target,gate->target_bytes);
}
static int rr_nonce(char out[33]) {
 HCRYPTPROV provider=0;unsigned char bytes[16];static const char hex[]="0123456789abcdef";unsigned k;int ok;
 if(!CryptAcquireContextW(&provider,NULL,NULL,PROV_RSA_AES,CRYPT_VERIFYCONTEXT))return 0;
 ok=CryptGenRandom(provider,sizeof(bytes),bytes)!=0;CryptReleaseContext(provider,0);if(!ok)return 0;
 for(k=0;k<16;k++){out[2*k]=hex[bytes[k]>>4];out[2*k+1]=hex[bytes[k]&15];}out[32]=0;return 1;
}
static int rr_store(wh3wr_registration *r,rr_plan *p,const rr_plan *old) {
 rr_plan check;
 if(!rcurrent(r)||!ridentity(r,0)||(old?(!rr_plan_read(r->key,&check)||memcmp(old,&check,sizeof(check))):
    !rabsent(r->key,L"Repair")))return 0;
 wh_sha256_hex(p,offsetof(rr_plan,seal),p->seal);
 return RegSetValueExW(r->key,L"Repair",0,REG_BINARY,(const BYTE *)p,sizeof(*p))==ERROR_SUCCESS&&
   RegFlushKey(r->key)==ERROR_SUCCESS&&rr_plan_read(r->key,&check)&&!memcmp(p,&check,sizeof(check));
}
static int rr_create(wh3wr_registration *r,HANDLE files[3],const wh_binding *binding,const wh_gates *gates,
 const char input_sha[65],const rr_plan *old,rr_plan *p,wh3r_scan *ack,wh3r_gate_scan *gate) {
 HANDLE archives[3]={INVALID_HANDLE_VALUE,INVALID_HANDLE_VALUE,INVALID_HANDLE_VALUE};
 rr_blob raw[3]={{0}},copy={0};wchar_t path[RRPATH];unsigned k;DWORD written;int ok=0;
 memset(p,0,sizeof(*p));memcpy(p->magic,"WH3RPR01",8);memcpy(p->binding,r->record,RBYTES);
 memcpy(p->input_sha,input_sha,65);memset(p->predecessor,'0',64);
 if(old){memcpy(p->predecessor,old->seal,65);if(!rr_history(r,old))goto done;}
 if(!rr_nonce(p->nonce))goto done;
 for(k=0;k<3;k++){
  if(!rr_read(files[k],&raw[k])||!reqid(&raw[k].id,&r->ids[k+1])||!rr_archive_path(r,p,k,path))goto done;
  archives[k]=CreateFileW(path,GENERIC_READ|GENERIC_WRITE,FILE_SHARE_READ,NULL,CREATE_NEW,
    FILE_FLAG_OPEN_REPARSE_POINT|FILE_FLAG_WRITE_THROUGH,NULL);
  if(archives[k]==INVALID_HANDLE_VALUE||!WriteFile(archives[k],raw[k].data,raw[k].bytes,&written,NULL)||
     written!=raw[k].bytes||!FlushFileBuffers(archives[k])||!rr_read(archives[k],&copy)||
     copy.bytes!=raw[k].bytes||memcmp(copy.sha,raw[k].sha,65))goto done;
  p->archive[k].id=copy.id;p->archive[k].bytes=copy.bytes;memcpy(p->archive[k].sha,copy.sha,65);rr_free(&copy);
 }
 if(!rr_scan(archives,r,binding,gates,ack,gate)||(!ack->unack_tail&&!gate->needs_write))goto done;
 p->keep[0]=gate->target_bytes;p->keep[1]=ack->journal_keep_bytes;p->keep[2]=ack->intent_keep_bytes;
 p->gate_bytes=(uint32_t)gate->target_bytes;memcpy(p->gate,gate->target,gate->target_bytes);
 ok=rr_store(r,p,old);
done:
 rr_free(&copy);for(k=0;k<3;k++){rr_free(&raw[k]);if(archives[k]!=INVALID_HANDLE_VALUE)CloseHandle(archives[k]);}
 return ok;
}
static int rr_apply(wh3wr_registration *r,HANDLE files[3],const rr_plan *p,
 const wh_binding *binding,const wh_gates *gates,const char input_sha[65],
 wh3r_scan *ack,wh3r_gate_scan *gate,const wh3w_controls *controls) {
 HANDLE archives[3]={INVALID_HANDLE_VALUE,INVALID_HANDLE_VALUE,INVALID_HANDLE_VALUE};
 rr_blob raw[3]={{0}},current[3]={{0}},after={0};const unsigned char *target[3];
 unsigned order[3]={1,2,0},at,k;DWORD written;int ok=0;rr_plan check;
 if(memcmp(p->binding,r->record,RBYTES)||memcmp(p->input_sha,input_sha,65)||
    !rr_archives(r,p,archives,raw)||!rr_scan(archives,r,binding,gates,ack,gate)||
    !rr_plan_targets(p,ack,gate))goto done;
 target[0]=p->gate;target[1]=raw[1].data;target[2]=raw[2].data;
 /* Read every actual source before writing any one of them. Accept only the
    archived original, the planned result, or a prefix of the one B extension. */
 for(k=0;k<3;k++){
  int original,planned,extension;
  if(!rr_read(files[k],&current[k])||!reqid(&current[k].id,&r->ids[k+1]))goto done;
  original=current[k].bytes==raw[k].bytes&&!memcmp(current[k].sha,raw[k].sha,65);
  planned=current[k].bytes==p->keep[k]&&!memcmp(current[k].data,target[k],current[k].bytes);
  extension=!k&&raw[k].bytes<p->keep[k]&&current[k].bytes>=raw[k].bytes&&current[k].bytes<p->keep[k]&&
     !memcmp(current[k].data,target[k],current[k].bytes);
  if(!original&&!planned&&!extension)goto done;
 }
 for(at=0;at<3;at++){
  k=order[at];
  if(!rcurrent(r)||!ridentity(r,0)||!rr_plan_read(r->key,&check)||memcmp(p,&check,sizeof(check)))goto done;
  if(current[k].bytes<p->keep[k]){
   DWORD remaining=(DWORD)(p->keep[k]-current[k].bytes);
   if(k||!rr_seek(files[k],current[k].bytes)||
      !WriteFile(files[k],target[k]+current[k].bytes,remaining,&written,NULL)||written!=remaining)goto done;
  }
  if(!rr_seek(files[k],p->keep[k])||!SetEndOfFile(files[k])||!FlushFileBuffers(files[k])||
     !rr_read(files[k],&after)||!reqid(&after.id,&r->ids[k+1])||
     after.bytes!=p->keep[k]||memcmp(after.data,target[k],after.bytes))goto done;
  rr_free(&after);rphase(controls,WH3WR_REPAIR_JOURNAL+at);
 }
 if(!rcurrent(r)||!ridentity(r,0)||
    RegSetValueExW(r->key,L"RepairApplied",0,REG_BINARY,(const BYTE *)p->seal,65)!=ERROR_SUCCESS||
    RegFlushKey(r->key)!=ERROR_SUCCESS||!rr_applied(r->key,p))goto done;
 rphase(controls,WH3WR_REPAIR_APPLIED);ok=1;
done:
 rr_free(&after);for(k=0;k<3;k++){rr_free(&raw[k]);rr_free(&current[k]);if(archives[k]!=INVALID_HANDLE_VALUE)CloseHandle(archives[k]);}
 return ok;
}
int wh3wr_repair_prepare(const wchar_t *library,
 int (*validate)(void *,const void *,size_t,wh_binding *,wh_gates *),void *context,
 const wh3w_controls *controls) {
 wh3wr_registration *r=NULL;wh3w_store *journal=NULL;wh_binding binding;wh_gates gates;char input_sha[65];
 HANDLE files[3]={INVALID_HANDLE_VALUE,INVALID_HANDLE_VALUE,INVALID_HANDLE_VALUE};
 wh3r_scan *ack=NULL;wh3r_gate_scan gate;rr_plan plan,old;unsigned k;int ok=0,existing=0;
 if(!validate)return 0;ack=calloc(1,sizeof(*ack));if(!ack)return 0;
 /* Valid complete pairs require no repair and no archival side effects. This
    also covers an already-committed generation and lost caller receipts. */
 if(wh3wr_open(library,WH3WG_RECOVER,NULL,&r)){
  if(rr_input(r,validate,context,&binding,&gates,input_sha)&&
     wh3wr_journal(r,&binding,&gates,NULL,&journal)&&
     wh3w_read(journal,ack->lines,EXR_WH_MAX_JOURNAL,&ack->count,&ack->tip))ok=1;
  wh3w_close(journal);journal=NULL;(void)wh3wr_close(r);r=NULL;if(ok)goto done;
 }
 if(!rr_raw_open(library,&r,files)||!rr_input(r,validate,context,&binding,&gates,input_sha))goto done;
 existing=!rabsent(r->key,L"Repair");
 if(existing){
  if(!rr_plan_read(r->key,&old)||!rtbound(r,old.binding)||!rr_evidence(r,&old))goto done;
  if(!rr_applied(r->key,&old)){plan=old;goto apply;}
  /* A later crash may need another bounded repair. Preserve the previous
     plan and its archives before replacing the active authority value. */
 }
 if(!rr_scan(files,r,&binding,&gates,ack,&gate))goto done;
 if(!ack->unack_tail&&!gate.needs_write){ok=1;goto done;}
 if(!rr_create(r,files,&binding,&gates,input_sha,existing?&old:NULL,&plan,ack,&gate))goto done;
 rphase(controls,WH3WR_REPAIR_PLANNED);
apply:
 ok=rr_apply(r,files,&plan,&binding,&gates,input_sha,ack,&gate,controls);
done:
 for(k=0;k<3;k++)if(files[k]!=INVALID_HANDLE_VALUE)CloseHandle(files[k]);
 (void)wh3wr_close(r);free(ack);return ok;
}
