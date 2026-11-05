/* SPDX-License-Identifier: MIT */
#include <lm_win_restart_reader.h>
#include <lm_win_record_bridge.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
static int save(const WCHAR *path,const lm_wr_record *r){
 lm_sb b;FILE *f;int ok;lm_sb_init(&b);if(!lm_wr_record_encode(r,&b))return 0;
 f=_wfopen(path,L"wb");if(!f){lm_sb_free(&b);return 0;}
 ok=fwrite(b.p,1,b.n,f)==b.n;if(fclose(f))ok=0;lm_sb_free(&b);return ok;
}
static int load(const WCHAR *path,lm_wr_record *r){
 char bytes[LM_WR_RECORD_MAX+1];FILE *f;size_t n;
 f=_wfopen(path,L"rb");if(!f)return 0;n=fread(bytes,1,sizeof(bytes),f);fclose(f);
 return lm_wr_record_decode(bytes,n,r);
}
static void leaf_of(WCHAR leaf[64],const char id[49]){
 size_t i;for(i=0;i<48;i++)leaf[i]=(WCHAR)id[i];memcpy(leaf+48,L".lease",7*sizeof(WCHAR));
}
static void printable(const WCHAR *in,char *out,size_t cap){
 size_t i=0;for(;*in&&i+2<cap;in++){
  if(*in==L'\\'){out[i++]='\\';out[i++]='\\';}
  else if(*in>0&&*in<128)out[i++]=(char)*in;
  else out[i++]='?';
 }
 out[i]=0;
}
static long long lease_bytes(const WCHAR *dir,const char id[49]){
 WCHAR path[WR_PATH+64],leaf[64];WIN32_FILE_ATTRIBUTE_DATA data;
 leaf_of(leaf,id);
 if(swprintf(path,WR_PATH+64,L"%ls\\%ls",dir,leaf)<0)return -1;
 if(!GetFileAttributesExW(path,GetFileExInfoStandard,&data))return -1;
 return ((long long)data.nFileSizeHigh<<32)|(long long)data.nFileSizeLow;
}
static const char *why(const wr_error *e){return e->reason?e->reason:"none";}
/* Deterministic reproduction of the acquire window: empty the lease between the
 * reader's pre-validation and the provider acquire, so the provider's OPEN_ALWAYS
 * branch re-initialises it and clears PENDING. */
static void truncate_lease(const WCHAR *path){
 HANDLE h=CreateFileW(path,GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_EXISTING,0,NULL);
 if(h!=INVALID_HANDLE_VALUE){if(!SetEndOfFile(h)){}CloseHandle(h);}
}
/* The same window, but the file ends up in a state the adapter must NOT repair:
 * a valid header for this identity with an advanced generation and no PENDING.
 * That is indistinguishable from a real concurrent commit, so the reader has to
 * refuse and keep custody instead of writing anything back. */
static char seam_identity[49];
static void drift_lease(const WCHAR *path){
 unsigned char buf[80];HANDLE h;DWORD put=0;size_t i;
 memset(buf,0,sizeof buf);memcpy(buf,"EXRLEASE1\n",10);
 for(i=0;i<48;i++)buf[10+i]=(unsigned char)seam_identity[i];
 buf[58]='\n';buf[64]=5; /* generation 5, PENDING 0 */
 h=CreateFileW(path,GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_EXISTING,0,NULL);
 if(h==INVALID_HANDLE_VALUE)return;
 if(!SetEndOfFile(h)){}
 if(!WriteFile(h,buf,sizeof buf,&put,NULL)){}
 CloseHandle(h);
}
int main(int argc,char **argv){
 static wr_context c,lc;WCHAR root[WR_PATH],reader[WR_PATH],leases[WR_PATH],manifest[WR_PATH],slotpath[WR_PATH],moved[WR_PATH];
 wr_error e={0};lm_wl_error le={0};lm_wl_lease *lease=NULL,*shared=NULL;lm_wl_status ls;
 lm_wr_record record={0},next;wr_identity id;lm_rb *bridge=NULL;lm_wp_custody *custody=NULL;
 lm_rb_result first,last;lm_wp_result publication;HANDLE target=INVALID_HANDLE_VALUE,h;
 const char payload[]="restart payload\n";char sha[65],lease_id[49],pathbuf[WR_PATH*2];const char *open_reason;
 lm_rr *reader_obj=NULL;lm_rr_result result;uint64_t generation=0;
 int opened,checked,write_denied,rename_denied,after_fail;unsigned i;long long bytes;
 if(argc!=4||!wr_utf8(argv[2],root,&e))return 2;
 swprintf(leases,WR_PATH,L"%ls-lease",root);swprintf(manifest,WR_PATH,L"%ls-expected.json",root);
 if(!strcmp(argv[1],"fixture")){
  if(!wr_prepare(&c,root,1,&e)||!wr_prepare(&lc,leases,1,&e))return 3;wr_close(&lc);
  if(!wr_write_new(&c,L"target.bin",payload,sizeof(payload)-1,1,&target,&e)||
     !wr_identity_get(target,0,&id,&e))return 4;
  memcpy(record.source,SOURCE_SHA,41);memset(record.run,'b',32);record.run[32]=0;
  wr_identity_text(&c.root,record.root);wr_identity_text(&c.identities[c.count-2],record.parent);
  wr_identity_text(&id,record.target);lm_sha_bytes(payload,sizeof(payload)-1,sha);memcpy(record.payload_sha,sha,65);
  if(!save(manifest,&record))return 5;
  if(lm_wl_acquire(leases,record.root,LM_WL_EXCLUSIVE,0,&lease,&le)!=LM_WL_OK||
     lm_wl_exclusive_begin(lease,&le)!=LM_WL_OK)return 6;
  if(!lm_rb_prepare(&c,target,&record,2,&bridge,&e)||
     !lm_wp_custody_prepare(&c,&custody,&e)||!lm_rb_attach(bridge,custody,&e))return 7;
  wr_close(&c);
  if(strcmp(argv[3],"before")){
   if(!lm_rb_write_once(bridge,0,&record,&first,&e))return 8;
   if(strcmp(argv[3],"record")){
    if(!lm_wp_publish_prepared(custody,target,L"target.bin",L"published.bin",&id,sha,&publication,&e))return 9;
    if(strcmp(argv[3],"published")){
     next=record;next.ordinal=1;next.phase=1;
     wr_identity_text(&first.identity,next.previous_id);memcpy(next.previous_sha,first.sha,65);
     if(!lm_rb_write_once(bridge,1,&next,&last,&e))return 10;
    }
   }
  }
  printf("ready-%s\n",argv[3]);fflush(stdout);Sleep(INFINITE);return 11;
 }
 if(!load(manifest,&record))return 12;memcpy(lease_id,record.root,49);
 if(!strcmp(argv[1],"leasepath")){
  WCHAR path[WR_PATH+64],leaf[64];
  leaf_of(leaf,lease_id);
  if(swprintf(path,WR_PATH+64,L"%ls\\%ls",leases,leaf)<0)return 13;
  printable(path,pathbuf,sizeof pathbuf);
  printf("{\"lease\":\"%s\"}\n",pathbuf);return 0;
 }
 if(!strcmp(argv[1],"shared")){
  ls=lm_wl_acquire(leases,record.root,LM_WL_SHARED,0,&shared,&le);
  if(shared)lm_wl_release(shared);
  printf("{\"stale\":%s,\"status\":%d}\n",ls==LM_WL_STALE?"true":"false",(int)ls);return 0;
 }
 if(!strcmp(argv[3],"generation"))generation=1;
 if(!strcmp(argv[3],"root"))record.root[47]=record.root[47]=='0'?'1':'0';
 if(!strcmp(argv[3],"session"))record.run[31]='c';
 wcscpy(reader,root);
 if(!strcmp(argv[3],"missing-root"))wcscat(reader,L"\\absent-sub");
 if(!strcmp(argv[3],"window-race"))lm_rr_set_window_probe(truncate_lease);
 if(!strcmp(argv[3],"window-drift")){
  memcpy(seam_identity,lease_id,49);
  lm_rr_set_window_probe(drift_lease);
 }
 opened=lm_rr_open(leases,lease_id,generation,reader,L"target.bin",L"published.bin",&record,2,&reader_obj,&result,&e);
 open_reason=why(&e);
 checked=opened&&lm_rr_check(reader_obj,&e);write_denied=rename_denied=0;
 if(!strcmp(argv[3],"window-drift")){
  /* The refused object keeps exclusive custody; stay alive so the caller can
     measure whether shared admission is still blocked, then be killed. */
  printf("{\"source\":\"%s\",\"opened\":%s,\"class\":%d,\"checked\":%s,\"lease_restored\":%s,\"open_reason\":\"%s\",\"reason\":\"%s\",\"native\":%lu}\n",
   SOURCE_SHA,opened?"true":"false",(int)result.classification,checked?"true":"false",
   result.lease_restored?"true":"false",open_reason,why(&e),(unsigned long)e.native);
  fflush(stdout);Sleep(INFINITE);
 }
 if(!strcmp(argv[3],"drift")){
  if(!(opened&&checked)){
   printf("{\"opened\":false,\"checked\":false,\"class\":%d,\"reason\":\"%s\"}\n",(int)result.classification,why(&e));
   lm_rr_close(reader_obj);return 0;
  }
  puts("ready-reader");fflush(stdout);
  for(i=0;i<200;i++){
   Sleep(100);
   if(!lm_rr_check(reader_obj,&e)){
    printf("{\"check_failed\":true,\"reason\":\"%s\"}\n",why(&e));fflush(stdout);
    lm_rr_close(reader_obj);return 0;
   }
  }
  puts("{\"check_failed\":false}");fflush(stdout);lm_rr_close(reader_obj);return 0;
 }
 if(checked){
  swprintf(slotpath,WR_PATH,L"%ls\\bridge-slot-00.rec",root);
  h=CreateFileW(slotpath,GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,NULL,OPEN_EXISTING,0,NULL);
  write_denied=h==INVALID_HANDLE_VALUE;if(h!=INVALID_HANDLE_VALUE)CloseHandle(h);
  swprintf(moved,WR_PATH,L"%ls-moved",root);rename_denied=!MoveFileExW(root,moved,0);
  if(!strcmp(argv[3],"hold")){puts("ready-reader");fflush(stdout);Sleep(INFINITE);}
 }
 /* A refused open must not leave pins behind: the private root must still be
   renameable. Restored immediately so the caller's file inventory is unchanged. */
 after_fail=0;
 if(!checked){
  swprintf(moved,WR_PATH,L"%ls-moved",root);
  if(MoveFileExW(root,moved,0)){
   after_fail=1;
   if(!MoveFileExW(moved,root,0))after_fail=0;
  }
 }
 bytes=lease_bytes(leases,lease_id);
 printf("{\"source\":\"%s\",\"opened\":%s,\"class\":%d,\"valid\":%u,\"checked\":%s,\"pending\":%d,\"generation\":%llu,\"published\":%d,\"write_denied\":%s,\"rename_denied\":%s,\"after_fail_rename\":%s,\"lease_restored\":%s,\"lease_bytes\":%lld,\"open_reason\":\"%s\",\"reason\":\"%s\",\"native\":%lu,\"sdk_open_attempts\":0,\"commit_acknowledged\":false,\"recovery_admission\":false}\n",
 SOURCE_SHA,opened?"true":"false",(int)result.classification,result.valid_records,checked?"true":"false",
 result.pending,(unsigned long long)result.generation,result.published,write_denied?"true":"false",
 rename_denied?"true":"false",after_fail?"true":"false",result.lease_restored?"true":"false",
 bytes,open_reason,why(&e),(unsigned long)e.native);
 lm_rr_close(reader_obj);return 0;
}
