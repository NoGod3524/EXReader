/* SPDX-License-Identifier: MIT */
/* Native fault harness: compile the identical engine with narrow call-boundary
 * fault injection. Installed consumer's original 29 assertions remain separate. */
#include "lm_win_engine.h"
#include "lm.h"
#include <stdio.h>
#include <string.h>
static int force_query,force_termination,delay_hash,hash_calls,wrong_image;
static BOOL WINAPI checked_query(HANDLE j,JOBOBJECTINFOCLASS c,LPVOID p,DWORD n,LPDWORD r){
 if(force_query){SetLastError(ERROR_INVALID_HANDLE);return FALSE;}
 return QueryInformationJobObject(j,c,p,n,r);
}
static BOOL WINAPI checked_terminate(HANDLE j,UINT code){
 if(force_termination){SetLastError(ERROR_ACCESS_DENIED);return FALSE;}
 return TerminateJobObject(j,code);
}
static BOOL WINAPI checked_image(HANDLE p,DWORD flags,LPWSTR path,PDWORD n){
 BOOL ok=QueryFullProcessImageNameW(p,flags,path,n);
 if(ok&&wrong_image&&*n)path[0]=L'X';
 return ok;
}
#define QueryFullProcessImageNameW checked_image
#define QueryInformationJobObject checked_query
#define TerminateJobObject checked_terminate
#define lm_we_hash delayed_hash
#include "../../../extras/migration/windows_recovery_engine_20261030/engine.c"
#undef QueryFullProcessImageNameW
#undef QueryInformationJobObject
#undef TerminateJobObject
#undef lm_we_hash
extern int lm_we_hash(HANDLE,char[65],wr_identity*,wr_error*);
int delayed_hash(HANDLE h,char sha[65],wr_identity *id,wr_error *e){
 int ok=lm_we_hash(h,sha,id,e);hash_calls++;
 if(delay_hash&&hash_calls==2)Sleep(1200);
 return ok;
}
static int checks,failed;
#define CHECK(x) do{checks++;if(!(x)){failed++;fprintf(stderr,"boundary check %d line %d failed\n",checks,__LINE__);}}while(0)
int main(int argc,char **argv){
 wr_context *root=calloc(1,sizeof(*root));wr_error error={0};lm_we_result result;
 WCHAR path[WR_PATH],worker[WR_PATH],descendant[WR_PATH];HANDLE target=INVALID_HANDLE_VALUE,probe;
 char sha[65],child_sha[65];uint64_t bytes=0;const char *nonce="0123456789abcdef0123456789abcdef";
 if(argc!=4||!root)return 2;
 CHECK(wr_utf8(argv[1],path,&error)&&wr_utf8(argv[2],worker,&error)&&wr_utf8(argv[3],descendant,&error));
 CHECK(wr_prepare(root,path,1,&error));if(failed)goto done;
 CHECK(wr_write_new(root,L"target.fixture","retained-byte-observation",25,1,&target,&error));
 CloseHandle(target);target=wr_open(root,L"target.fixture",GENERIC_READ,FILE_SHARE_READ,0,&error);
 CHECK(target!=INVALID_HANDLE_VALUE&&lm_sha_file(argv[2],sha,&bytes));
 CHECK(!lm_we_observe(root,target,L"worker.exe",sha,nonce,L"relative.bin",30000,&result,&error)&&!strcmp(error.reason,"observer-worker-absolute"));
 CHECK(!lm_we_observe(root,target,L"C:worker.exe",sha,nonce,L"drive-relative.bin",30000,&result,&error)&&!strcmp(error.reason,"observer-worker-absolute"));
 CHECK(!lm_we_observe(root,target,L"\\worker.exe",sha,nonce,L"root-relative.bin",30000,&result,&error)&&!strcmp(error.reason,"observer-worker-absolute"));
 wrong_image=1;
 CHECK(!lm_we_observe(root,target,worker,sha,nonce,L"wrong-launch.bin",30000,&result,&error));
 CHECK(result.state==LM_WE_REFUSED&&!strcmp(error.reason,"observer-launch-image-binding")&&lm_we_gate==0);
 wrong_image=0;
 delay_hash=1;hash_calls=0;
 CHECK(!lm_we_observe(root,target,worker,sha,nonce,L"late.bin",1000,&result,&error));
 CHECK(result.state==LM_WE_REFUSED&&!strcmp(error.reason,"observer-final-deadline")&&error.native==ERROR_TIMEOUT);
 CHECK(result.worker_terminal&&result.descendants_terminal&&lm_we_gate==0);
 delay_hash=0;
 CHECK(lm_sha_file(argv[3],child_sha,&bytes));
 force_query=1;force_termination=1;
 CHECK(!lm_we_observe(root,target,descendant,child_sha,nonce,L"quarantine.bin",30000,&result,&error));
 CHECK(result.state==LM_WE_UNCERTAIN&&result.worker_terminal&&!result.descendants_terminal&&error.cleanup_unconfirmed);
 CHECK(lm_we_gate==2&&lm_we_quarantine!=NULL);
 CHECK(WaitForSingleObject(lm_we_quarantine->retained[0],0)==WAIT_OBJECT_0);
 {JOBOBJECT_BASIC_ACCOUNTING_INFORMATION a;
 CHECK(QueryInformationJobObject(lm_we_quarantine->retained[2],JobObjectBasicAccountingInformation,&a,sizeof(a),NULL)&&a.ActiveProcesses>0);}
 CHECK(!lm_we_observe(root,target,worker,sha,nonce,L"after.bin",30000,&result,&error)&&!strcmp(error.reason,"observer-quarantined-or-busy")&&result.state==LM_WE_UNCERTAIN);
 CloseHandle(target);target=INVALID_HANDLE_VALUE;wr_close(root);
 probe=CreateFileW(worker,GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,NULL,OPEN_EXISTING,0,NULL);
 /* Quarantine image is descendant executable, not the earlier observer. */
 if(probe!=INVALID_HANDLE_VALUE)CloseHandle(probe);
 probe=CreateFileW(descendant,GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,NULL,OPEN_EXISTING,0,NULL);
 CHECK(probe==INVALID_HANDLE_VALUE);if(probe!=INVALID_HANDLE_VALUE)CloseHandle(probe);
 force_query=0;force_termination=0;
 CHECK(TerminateJobObject(lm_we_quarantine->retained[2],125));
done:
 if(target!=INVALID_HANDLE_VALUE)CloseHandle(target);wr_close(root);free(root);
 printf("{\"checks\":%d,\"failed\":%d,\"passed\":%s,\"test_only_fault_injection\":true}\n",checks,failed,failed?"false":"true");
 return failed?1:0;
}
