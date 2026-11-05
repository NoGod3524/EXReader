/* SPDX-License-Identifier: MIT */
#ifndef LM_WE_LAUNCH_H
#define LM_WE_LAUNCH_H
/* Private suspended launcher. The frozen adapter cannot authenticate an image
 * before ResumeThread. Namespace pins remain live across all of these checks. */
static int lm_we_spawn_bound(HANDLE job,HANDLE image,const WCHAR *exe,WCHAR *command,
 HANDLE *handles,size_t count,HANDLE input,HANDLE output,wr_process *p,wr_error *e){
 STARTUPINFOEXW s;PROCESS_INFORMATION pi;SIZE_T size=0;BOOL member=FALSE;
 size_t i;int ok=0;DWORD saved=0,n=WR_PATH;WCHAR expected[WR_PATH],actual[WR_PATH];
 const char *why="observer-launch-inherit";int initialized=0;
 memset(p,0,sizeof(*p));memset(&s,0,sizeof(s));memset(&pi,0,sizeof(pi));
 s.StartupInfo.cb=sizeof(s);s.StartupInfo.dwFlags=STARTF_USESTDHANDLES;
 s.StartupInfo.hStdInput=input;s.StartupInfo.hStdOutput=output;s.StartupInfo.hStdError=output;
 if(wr_cleanup_uncertain()){p->cleanup_unconfirmed=1;if(e)e->cleanup_unconfirmed=1;SetLastError(ERROR_BUSY);return fail(e,"observer-launch-quarantined");}
 if(!count||count>8)return fail(e,"observer-launch-inherit-bound");
 for(i=0;i<count;i++)if(!SetHandleInformation(handles[i],HANDLE_FLAG_INHERIT,HANDLE_FLAG_INHERIT))goto done;
 n=GetFinalPathNameByHandleW(image,expected,WR_PATH,FILE_NAME_NORMALIZED|VOLUME_NAME_NT);
 if(!n||n>=WR_PATH){why="observer-launch-native-path";goto done;}
 InitializeProcThreadAttributeList(NULL,1,0,&size);
 s.lpAttributeList=malloc(size);if(!s.lpAttributeList){why="observer-launch-allocation";goto done;}
 if(!InitializeProcThreadAttributeList(s.lpAttributeList,1,0,&size))goto done;
 initialized=1;
 if(!UpdateProcThreadAttribute(s.lpAttributeList,0,PROC_THREAD_ATTRIBUTE_HANDLE_LIST,handles,sizeof(HANDLE)*count,NULL,NULL))goto done;
 why="observer-launch-create-suspended";
 if(!CreateProcessW(exe,command,NULL,NULL,TRUE,CREATE_SUSPENDED|EXTENDED_STARTUPINFO_PRESENT|CREATE_NO_WINDOW,NULL,NULL,&s.StartupInfo,&pi))goto done;
 /* Native device paths cannot be redirected by a caller's drive-relative
  * resolution. Pinned ancestors plus deny-write/delete image custody make
  * this exact native pathname identify the already hashed image. */
 why="observer-launch-image-binding";n=WR_PATH;
 if(!QueryFullProcessImageNameW(pi.hProcess,PROCESS_NAME_NATIVE,actual,&n))goto kill;
 if(n>=WR_PATH||wcscmp(expected,actual)){SetLastError(ERROR_INVALID_DATA);goto kill;}
 {WCHAR device_path[WR_PATH+16];HANDLE check;wr_identity expected_id,actual_id;
 if(swprintf(device_path,WR_PATH+16,L"\\\\?\\GLOBALROOT%ls",actual)<0)goto kill;
 check=CreateFileW(device_path,FILE_READ_ATTRIBUTES,FILE_SHARE_READ,NULL,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,NULL);
 if(check==INVALID_HANDLE_VALUE)goto kill;
 member=wr_identity_get(image,0,&expected_id,e)&&wr_identity_get(check,0,&actual_id,e)&&wr_identity_equal(&expected_id,&actual_id);
 CloseHandle(check);if(!member){SetLastError(ERROR_INVALID_DATA);goto kill;}
 }
 member=FALSE;why="observer-launch-job-binding";
 if(!IsProcessInJob(pi.hProcess,job,&member))goto kill;
 if(!member&&!AssignProcessToJobObject(job,pi.hProcess))goto kill;
 member=FALSE;
 if(!IsProcessInJob(pi.hProcess,job,&member)||!member){SetLastError(ERROR_INVALID_DATA);goto kill;}
 why="observer-launch-resume";
 if(ResumeThread(pi.hThread)==(DWORD)-1)goto kill;
 p->process=pi.hProcess;p->thread=pi.hThread;p->pid=pi.dwProcessId;ok=1;goto done;
kill:
 saved=GetLastError();
 {DWORD cleanup=0,waited;
  if(!TerminateProcess(pi.hProcess,125))cleanup=GetLastError();
  waited=WaitForSingleObject(pi.hProcess,10000);
  if(e){e->cleanup_native=waited==WAIT_FAILED?GetLastError():cleanup;e->wait_result=waited;}
  if(waited!=WAIT_OBJECT_0){
   p->process=pi.hProcess;p->thread=pi.hThread;p->pid=pi.dwProcessId;p->cleanup_unconfirmed=1;
   if(e)e->cleanup_unconfirmed=1;
  }else{CloseHandle(pi.hThread);CloseHandle(pi.hProcess);}
 }
 SetLastError(saved);
done:
 saved=GetLastError();
 if(initialized)DeleteProcThreadAttributeList(s.lpAttributeList);
 free(s.lpAttributeList);
 for(i=0;i<count;i++)SetHandleInformation(handles[i],HANDLE_FLAG_INHERIT,0);
 SetLastError(saved);if(!ok)fail(e,why);return ok;
}
#endif
