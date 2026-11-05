/* SPDX-License-Identifier: MIT */
#include "lm_win_engine.h"
#include "protocol.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
static int fail(wr_error *e,const char *why){if(e){e->reason=why;e->native=GetLastError();}return 0;}
#include "boundary.h"
#include "launch.h"
static int empty_job(HANDLE job){
 JOBOBJECT_BASIC_ACCOUNTING_INFORMATION a;
 return QueryInformationJobObject(job,JobObjectBasicAccountingInformation,&a,sizeof(a),NULL)&&a.ActiveProcesses==0;
}
int lm_we_wait_zero(HANDLE job,ULONGLONG deadline,lm_we_result *out,wr_error *e){
 JOBOBJECT_BASIC_ACCOUNTING_INFORMATION accounting;int first=1;
 if(!out)return fail(e,"observer-result-null");
 out->job_query_error=0;out->diagnostic_samples=0;
 for(;;){ULONGLONG now;DWORD pause;
  SetLastError(ERROR_SUCCESS);
  if(!QueryInformationJobObject(job,JobObjectBasicAccountingInformation,&accounting,sizeof(accounting),NULL)){
   out->job_query_error=GetLastError();return fail(e,"observer-job-query");
  }
  if(first){out->active_initial=accounting.ActiveProcesses;first=0;}
  out->active_last=accounting.ActiveProcesses;
  if(!accounting.ActiveProcesses){if(GetTickCount64()>deadline){SetLastError(ERROR_TIMEOUT);return fail(e,"observer-accounting-deadline");}return 1;}
  now=GetTickCount64();if(now>=deadline){SetLastError(ERROR_TIMEOUT);return fail(e,"observer-descendant-deadline");}
  pause=(DWORD)((deadline-now)>10?10:(deadline-now));Sleep(pause);out->diagnostic_samples++;
 }
}
int lm_we_observe(wr_context *root,HANDLE target,const WCHAR *worker_path,
 const char expected_worker_sha[65],const char nonce[33],const WCHAR *leaf,
 DWORD timeout_ms,lm_we_result *out,wr_error *e){
 HANDLE target_pin=INVALID_HANDLE_VALUE,image=INVALID_HANDLE_VALUE,output=INVALID_HANDLE_VALUE,job=NULL,input=NULL,write_end=NULL,child_target=NULL;
 HANDLE inherited[3];wr_process process={0};wr_identity target_before,target_after,image_id,parent_id;
 lm_we_request request;lm_we_response *response=NULL;size_t length=0;
 char hash[65],target_hash[65];DWORD wrote=0,status=STILL_ACTIVE;WCHAR command[WR_PATH+80],target_path[WR_PATH],launch_path[WR_PATH];int ok=0,started=0;
 ULONGLONG observation_deadline=GetTickCount64()+timeout_ms;
 lm_we_custody *custody=NULL;
 SECURITY_ATTRIBUTES sa={sizeof(sa),NULL,TRUE};
 if(!out)return fail(e,"observer-result-null");
 memset(out,0,sizeof(*out));memset(&request,0,sizeof(request));
 if(!root||root->count<2||root->count>WR_PINS||!expected_worker_sha||!nonce||!worker_path||
 !timeout_ms||timeout_ms>60000)return fail(e,"observer-argument-bound");
 if(wcslen(worker_path)>=WR_PATH||wcschr(worker_path,L'"'))return fail(e,"observer-worker-path");
 if(wcslen(worker_path)<3||!((worker_path[0]>=L'A'&&worker_path[0]<=L'Z')||(worker_path[0]>=L'a'&&worker_path[0]<=L'z'))||worker_path[1]!=L':'||worker_path[2]!=L'\\'){SetLastError(ERROR_INVALID_NAME);return fail(e,"observer-worker-absolute");}
 {LONG gate=InterlockedCompareExchange(&lm_we_gate,1,0);if(gate!=0){if(gate==2){out->state=LM_WE_UNCERTAIN;if(e)e->cleanup_unconfirmed=1;}SetLastError(ERROR_BUSY);return fail(e,"observer-quarantined-or-busy");}}
 custody=calloc(1,sizeof(*custody));if(!custody){fail(e,"observer-custody-allocation");goto done;}
 if(!wr_recheck(root,e)||!wr_identity_get(root->pins[root->count-2],1,&parent_id,e)||
 !wr_identity_get(target,0,&target_before,e))goto done;
 {DWORD n=GetFinalPathNameByHandleW(target,target_path,WR_PATH,FILE_NAME_NORMALIZED);
 if(!n||n>=WR_PATH){fail(e,"observer-target-path");goto done;}
 target_pin=CreateFileW(target_path,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,NULL);
 if(target_pin==INVALID_HANDLE_VALUE||!wr_identity_get(target_pin,0,&target_after,e)||
 !wr_identity_equal(&target_before,&target_after)){fail(e,"observer-target-custody");goto done;}}
 image=CreateFileW(worker_path,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,NULL);
 if(image==INVALID_HANDLE_VALUE||!lm_we_hash(image,hash,&image_id,e))goto done;
 if(strnlen(expected_worker_sha,65)!=64||strcmp(hash,expected_worker_sha)){fail(e,"observer-worker-hash");goto done;}
 if(!lm_we_pin_worker(custody,root,image,e))goto done;
 {DWORD n=GetFinalPathNameByHandleW(image,launch_path,WR_PATH,FILE_NAME_NORMALIZED|VOLUME_NAME_DOS);if(!n||n>=WR_PATH){fail(e,"observer-launch-dos-path");goto done;}}
 memcpy(request.magic,"EXRWINOBSERVE1",14);memcpy(request.source,LM_WE_SOURCE,41);
 if(strnlen(nonce,33)!=32){fail(e,"observer-nonce");goto done;}
 memcpy(request.nonce,nonce,33);memcpy(request.worker_sha,hash,65);
 wr_identity_text(&root->root,request.root);wr_identity_text(&parent_id,request.parent);
 wr_identity_text(&target_before,request.target);
 if(!lm_we_request_valid(&request)){fail(e,"observer-request");goto done;}
 if(!DuplicateHandle(GetCurrentProcess(),target_pin,GetCurrentProcess(),&child_target,
 FILE_READ_DATA|FILE_READ_ATTRIBUTES|SYNCHRONIZE,TRUE,0)){fail(e,"observer-target-duplicate");goto done;}
 if(!CreatePipe(&input,&write_end,&sa,sizeof(request))||
 !SetHandleInformation(write_end,HANDLE_FLAG_INHERIT,0)){fail(e,"observer-pipe");goto done;}
 output=wr_open(root,leaf,GENERIC_READ|GENERIC_WRITE,FILE_SHARE_READ,1,e);
 if(output==INVALID_HANDLE_VALUE)goto done;
 job=wr_job(e);if(!job)goto done;
 if(!WriteFile(write_end,&request,sizeof(request),&wrote,NULL)||wrote!=sizeof(request)){fail(e,"observer-request-write");goto done;}
 CloseHandle(write_end);write_end=NULL;
 if(swprintf(command,sizeof(command)/sizeof(*command),L"\"%ls\" %llu",launch_path,(unsigned long long)(uintptr_t)child_target)<0){fail(e,"observer-command");goto done;}
 inherited[0]=input;inherited[1]=output;inherited[2]=child_target;
 if(!lm_we_spawn_bound(job,image,launch_path,command,inherited,3,input,output,&process,e))goto done;
 started=1;
 {ULONGLONG now=GetTickCount64();
 if(now>=observation_deadline){SetLastError(ERROR_TIMEOUT);fail(e,"observer-total-deadline");goto done;}
 if(!wr_wait(&process,(DWORD)(observation_deadline-now),&status,e))goto done;}
 out->worker_terminal=1;out->worker_exit=status;
 if(!lm_we_wait_zero(job,observation_deadline,out,e))goto done;
 out->descendants_terminal=1;
 if(status||!wr_recheck(root,e)||!wr_identity_get(target,0,&target_after,e)||
 !wr_identity_equal(&target_before,&target_after)){fail(e,"observer-terminal-or-identity");goto done;}
 if(!wr_read(output,(void**)&response,&length,sizeof(*response),e)||length!=sizeof(*response)||
 memcmp(&response->request,&request,sizeof(request))||response->observed!=1||
 response->bytes!=target_after.size){fail(e,"observer-response-binding");goto done;}
 if(!lm_we_hash(target_pin,target_hash,&target_after,e)||memcmp(target_hash,response->target_sha,65)||
 !wr_identity_equal(&target_before,&target_after)){fail(e,"observer-parent-readback");goto done;}
 memcpy(out->source,request.source,41);memcpy(out->nonce,request.nonce,33);
 memcpy(out->root,request.root,49);memcpy(out->parent,request.parent,49);
 memcpy(out->target,request.target,49);memcpy(out->worker_sha,request.worker_sha,65);
 memcpy(out->target_sha,target_hash,65);out->bytes=response->bytes;
 if(lm_we_expired(observation_deadline,e))goto done;
 out->state=LM_WE_OBSERVED;ok=1;
done:
 if(started&&!out->descendants_terminal){
  int terminal=0;ULONGLONG deadline=GetTickCount64()+10000;
  if(TerminateJobObject(job,125)){
   do{DWORD actual=STILL_ACTIVE;
    /* Job accounting and process signaling are separate observations. Never
       release process ownership merely because the accounting count is zero. */
    if(WaitForSingleObject(process.process,0)==WAIT_OBJECT_0&&empty_job(job)&&
       GetExitCodeProcess(process.process,&actual)&&actual!=STILL_ACTIVE){
     out->worker_exit=actual;terminal=1;break;
    }
    Sleep(10);
   }while(GetTickCount64()<deadline);
  }
  if(terminal){out->worker_terminal=1;out->descendants_terminal=1;}
  else{out->state=LM_WE_UNCERTAIN;if(e)e->cleanup_unconfirmed=1;}
 }
 if(process.cleanup_unconfirmed){out->state=LM_WE_UNCERTAIN;if(e)e->cleanup_unconfirmed=1;}
 if(out->state==LM_WE_UNCERTAIN)goto quarantine;
 wr_process_close(&process);
 if(process.cleanup_unconfirmed){out->state=LM_WE_UNCERTAIN;if(e)e->cleanup_unconfirmed=1;goto quarantine;}
 free(response);if(job)CloseHandle(job);
 if(output!=INVALID_HANDLE_VALUE)CloseHandle(output);if(image!=INVALID_HANDLE_VALUE)CloseHandle(image);
 if(target_pin!=INVALID_HANDLE_VALUE)CloseHandle(target_pin);if(input)CloseHandle(input);if(write_end)CloseHandle(write_end);if(child_target)CloseHandle(child_target);
 lm_we_custody_close(custody);InterlockedExchange(&lm_we_gate,0);
 return ok&&out->state==LM_WE_OBSERVED;
quarantine:
  /* Never release custody on an unproven terminal state. Permanent process-
   * lifetime quarantine is intentional; there is no unsafe reset API. */
  custody->retained[0]=process.process;custody->retained[1]=process.thread;
  custody->retained[2]=job;custody->retained[3]=output;custody->retained[4]=image;
  custody->retained[5]=target_pin;custody->retained[6]=input;
  custody->retained[7]=write_end;custody->retained[8]=child_target;
  lm_we_quarantine=custody;InterlockedExchange(&lm_we_gate,2);
  free(response);return 0;

}
