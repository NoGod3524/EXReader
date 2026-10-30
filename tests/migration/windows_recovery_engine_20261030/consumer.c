/* SPDX-License-Identifier: MIT */
#include "lm_win_engine.h"
#include "lm.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static int checks,failed;
#define CHECK(x) do{checks++;if(!(x)){failed++;fprintf(stderr,"check %d line %d failed\n",checks,__LINE__);}}while(0)
int main(int argc,char **argv){
 wr_context *root=calloc(1,sizeof(*root));wr_error error={0};wr_identity id;
 HANDLE target=INVALID_HANDLE_VALUE,h=INVALID_HANDLE_VALUE;WCHAR path[WR_PATH],worker[WR_PATH];
 char worker_sha[65];void *bytes=NULL;size_t size=0;lm_we_result result;
 const char *nonce="0123456789abcdef0123456789abcdef";
 if(argc!=6||!root)return 2;
 CHECK(wr_utf8(argv[1],path,&error));CHECK(wr_utf8(argv[2],worker,&error));
 CHECK(wr_prepare(root,path,1,&error));if(failed)goto done;
 CHECK(wr_write_new(root,L"target.fixture","retained-byte-observation",25,1,&target,&error));
 /* Writer-owning handle must prevent the observer's read-only custody lease. */
 CHECK(!lm_we_observe(root,target,worker,argv[3],nonce,L"writer-refusal.bin",30000,&result,&error));
 CHECK(result.state!=LM_WE_OBSERVED);
 if(target!=INVALID_HANDLE_VALUE){CloseHandle(target);target=INVALID_HANDLE_VALUE;}
 target=wr_open(root,L"target.fixture",GENERIC_READ,FILE_SHARE_READ,0,&error);
 CHECK(target!=INVALID_HANDLE_VALUE);if(target==INVALID_HANDLE_VALUE)goto done;
 {int observed=lm_we_observe(root,target,worker,argv[3],nonce,L"observed.bin",30000,&result,&error);fprintf(stderr,"observer diagnostic reason=%s native=%lu state=%d exit=%lu worker_terminal=%d descendants_terminal=%d cleanup=%d\n",error.reason?error.reason:"none",error.native,(int)result.state,result.worker_exit,result.worker_terminal,result.descendants_terminal,error.cleanup_unconfirmed);fprintf(stderr,"job query_error=%lu initial_active=%lu last_active=%lu diagnostic_samples=%lu\n",result.job_query_error,result.active_initial,result.active_last,result.diagnostic_samples);CHECK(observed);}
 CHECK(result.state==LM_WE_OBSERVED&&result.worker_terminal&&result.descendants_terminal&&result.worker_exit==0);
 CHECK(strlen(result.target)==48&&strlen(result.root)==48&&strlen(result.parent)==48);
 CHECK(result.bytes==25&&!strcmp(result.source,argv[4]));
 CHECK(!strcmp(result.nonce,nonce)&&!strcmp(result.worker_sha,argv[3]));
 CHECK(wr_identity_get(target,0,&id,&error));{char full[49];wr_identity_text(&id,full);CHECK(!strcmp(full,result.target));}
 lm_sha_bytes("retained-byte-observation",25,worker_sha);CHECK(!strcmp(worker_sha,result.target_sha));
 CHECK(!lm_we_observe(root,target,worker,argv[3],nonce,L"observed.bin",30000,&result,&error));
 CHECK(result.state!=LM_WE_OBSERVED);
 strcpy(worker_sha,argv[3]);worker_sha[63]=worker_sha[63]=='0'?'1':'0';
 CHECK(!lm_we_observe(root,target,worker,worker_sha,nonce,L"wrong-image.bin",30000,&result,&error));
 CHECK(!lm_we_observe(root,target,worker,argv[3],"bad",L"bad-nonce.bin",30000,&result,&error));
 CHECK(!lm_we_observe(root,target,worker,argv[3],nonce,L"bad-timeout.bin",60001,&result,&error));
 h=wr_open(root,L"observed.bin",GENERIC_READ,FILE_SHARE_READ,0,&error);
 CHECK(h!=INVALID_HANDLE_VALUE&&wr_read(h,&bytes,&size,4096,&error)&&size>300);
 {HANDLE event=CreateEventW(NULL,TRUE,FALSE,NULL),empty=NULL;uint64_t size64=0;WCHAR stalled[WR_PATH];
 CHECK(event!=NULL);
 memset(&error,0,sizeof(error));memset(&result,0,sizeof(result));
 CHECK(!lm_we_wait_zero(event,GetTickCount64()+100,&result,&error)&&result.job_query_error!=0);
 if(event)CloseHandle(event);
 empty=wr_job(&error);CHECK(empty!=NULL);
 CHECK(lm_we_wait_zero(empty,GetTickCount64()+100,&result,&error));if(empty)CloseHandle(empty);
 CHECK(wr_utf8(argv[5],stalled,&error)&&lm_sha_file(argv[5],worker_sha,&size64));
 memset(&error,0,sizeof(error));
 CHECK(!lm_we_observe(root,target,stalled,worker_sha,nonce,L"deadline.bin",500,&result,&error));
 fprintf(stderr,"deadline diagnostic reason=%s native=%lu state=%d exit=%lu worker_terminal=%d descendants_terminal=%d cleanup=%d cleanup_native=%lu wait=%lu\n",error.reason?error.reason:"none",error.native,(int)result.state,result.worker_exit,result.worker_terminal,result.descendants_terminal,error.cleanup_unconfirmed,error.cleanup_native,error.wait_result);
 CHECK(result.state!=LM_WE_OBSERVED&&result.worker_terminal&&result.descendants_terminal&&!error.cleanup_unconfirmed);
 }
done:
 if(h!=INVALID_HANDLE_VALUE)CloseHandle(h);free(bytes);
 if(target!=INVALID_HANDLE_VALUE)CloseHandle(target);
 wr_close(root);free(root);
 printf("{\"checks\":%d,\"failed\":%d,\"passed\":%s,\"migration_admission\":false,\"full_p0_acceptance\":false}\n",checks,failed,failed?"false":"true");
 return failed?1:0;
}
