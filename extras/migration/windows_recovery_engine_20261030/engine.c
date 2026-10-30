/* SPDX-License-Identifier: MIT */
#include "lm_win_engine.h"
#include "protocol.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
static int fail(wr_error *e,const char *why){if(e){e->reason=why;e->native=GetLastError();}return 0;}
static int empty_job(HANDLE job){
 JOBOBJECT_BASIC_ACCOUNTING_INFORMATION a;
 return QueryInformationJobObject(job,JobObjectBasicAccountingInformation,&a,sizeof(a),NULL)&&a.ActiveProcesses==0;
}
int lm_we_observe(wr_context *root,HANDLE target,const WCHAR *worker_path,
 const char expected_worker_sha[65],const char nonce[33],const WCHAR *leaf,
 DWORD timeout_ms,lm_we_result *out,wr_error *e){
 HANDLE target_pin=INVALID_HANDLE_VALUE,image=INVALID_HANDLE_VALUE,output=INVALID_HANDLE_VALUE,job=NULL,input=NULL,write_end=NULL,child_target=NULL;
 HANDLE inherited[3];wr_process process={0};wr_identity target_before,target_after,image_id,parent_id;
 lm_we_request request;lm_we_response *response=NULL;size_t length=0;
 char hash[65],target_hash[65];DWORD wrote=0,status=STILL_ACTIVE;WCHAR command[WR_PATH+80],target_path[WR_PATH];int ok=0,started=0;
 ULONGLONG observation_deadline=GetTickCount64()+timeout_ms;
 SECURITY_ATTRIBUTES sa={sizeof(sa),NULL,TRUE};
 if(!out)return fail(e,"observer-result-null");
 memset(out,0,sizeof(*out));memset(&request,0,sizeof(request));
 if(!root||root->count<2||!expected_worker_sha||!nonce||!worker_path||
 !timeout_ms||timeout_ms>60000)return fail(e,"observer-argument-bound");
 if(wcslen(worker_path)>=WR_PATH||wcschr(worker_path,L'"'))return fail(e,"observer-worker-path");
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
 if(swprintf(command,sizeof(command)/sizeof(*command),L"\"%ls\" %llu",worker_path,(unsigned long long)(uintptr_t)child_target)<0){fail(e,"observer-command");goto done;}
 inherited[0]=input;inherited[1]=output;inherited[2]=child_target;
 if(!wr_spawn(job,worker_path,command,inherited,3,input,output,0,&process,e))goto done;
 started=1;
 if(!wr_wait(&process,timeout_ms,&status,e))goto done;
 out->worker_terminal=1;out->worker_exit=status;
 {JOBOBJECT_BASIC_ACCOUNTING_INFORMATION accounting;BOOL queried;
  SetLastError(ERROR_SUCCESS);
  queried=QueryInformationJobObject(job,JobObjectBasicAccountingInformation,&accounting,sizeof(accounting),NULL);
  out->job_query_error=queried?ERROR_SUCCESS:GetLastError();
  out->active_initial=out->active_last=queried?accounting.ActiveProcesses:MAXDWORD;
  if(!queried||accounting.ActiveProcesses){
   /* Diagnostic only: original immediate-zero assertion still fails even if
      accounting later reaches zero. Observations never extend total timeout. */
   ULONGLONG until=GetTickCount64()+1000;if(until>observation_deadline)until=observation_deadline;
   while(queried&&out->active_last&&GetTickCount64()+10<=until){
    Sleep(10);SetLastError(ERROR_SUCCESS);
    queried=QueryInformationJobObject(job,JobObjectBasicAccountingInformation,&accounting,sizeof(accounting),NULL);
    out->diagnostic_samples++;
    if(!queried){out->job_query_error=GetLastError();break;}
    out->active_last=accounting.ActiveProcesses;
   }
   SetLastError(out->job_query_error?out->job_query_error:ERROR_BUSY);
   fail(e,"observer-live-descendants");goto done;
  }
 }
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
 out->state=LM_WE_OBSERVED;ok=1;
done:
 if(started&&!out->descendants_terminal){
  int terminal=0;ULONGLONG deadline=GetTickCount64()+10000;
  if(TerminateJobObject(job,125)){
   do{if(empty_job(job)){terminal=1;break;}Sleep(10);}while(GetTickCount64()<deadline);
  }
  if(terminal){out->worker_terminal=1;out->descendants_terminal=1;}
  else{out->state=LM_WE_UNCERTAIN;if(e)e->cleanup_unconfirmed=1;}
 }
 if(process.cleanup_unconfirmed){out->state=LM_WE_UNCERTAIN;if(e)e->cleanup_unconfirmed=1;}
 wr_process_close(&process);
 if(process.cleanup_unconfirmed){out->state=LM_WE_UNCERTAIN;if(e)e->cleanup_unconfirmed=1;}
 free(response);if(job)CloseHandle(job);
 if(output!=INVALID_HANDLE_VALUE)CloseHandle(output);if(image!=INVALID_HANDLE_VALUE)CloseHandle(image);
 if(target_pin!=INVALID_HANDLE_VALUE)CloseHandle(target_pin);if(input)CloseHandle(input);if(write_end)CloseHandle(write_end);if(child_target)CloseHandle(child_target);
 return ok&&out->state==LM_WE_OBSERVED;
}
