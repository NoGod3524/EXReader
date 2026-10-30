/* SPDX-License-Identifier: MIT */
#include <lm_win_restart_reader.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#ifndef LM_RR_TEST_AFTER_ACQUIRE
#error This consumer must only compile with its private test seam.
#endif
static unsigned hook_calls;
static int continue_line(void){
 char line[16];
 return fgets(line,sizeof line,stdin)!=NULL && !strcmp(line,"\n");
}
/* Defined only by this test executable; never declared in the installed header. */
void lm_rr_test_after_acquire(const WCHAR *path){
 (void)path;hook_calls++;
 puts("acquired-ready");fflush(stdout);
 if(!continue_line())ExitProcess(20);
}
static int load(const WCHAR *path,lm_wr_record *r){
 char bytes[LM_WR_RECORD_MAX+1];FILE *f;size_t n;
 f=_wfopen(path,L"rb");if(!f)return 0;
 n=fread(bytes,1,sizeof(bytes),f);fclose(f);
 return lm_wr_record_decode(bytes,n,r);
}
static int helper(const WCHAR *path,int drift){
 HANDLE h;OVERLAPPED o;unsigned char bytes[80];DWORD got=0,put=0;
 LARGE_INTEGER zero;uint64_t generation=5,pending=0;
 h=CreateFileW(path,GENERIC_READ|GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_WRITE,
  NULL,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,NULL);
 if(h==INVALID_HANDLE_VALUE)return 30;
 if(drift){
  if(!ReadFile(h,bytes,sizeof bytes,&got,NULL)||got!=sizeof bytes){CloseHandle(h);return 31;}
  memcpy(bytes+64,&generation,8);memcpy(bytes+72,&pending,8);
  zero.QuadPart=0;
  if(!SetFilePointerEx(h,zero,NULL,FILE_BEGIN)||
     !WriteFile(h,bytes,sizeof bytes,&put,NULL)||put!=sizeof bytes||
     !FlushFileBuffers(h)){CloseHandle(h);return 32;}
 }
 memset(&o,0,sizeof o);
 if(!LockFileEx(h,LOCKFILE_EXCLUSIVE_LOCK|LOCKFILE_FAIL_IMMEDIATELY,0,80,0,&o)){
  CloseHandle(h);return 33;
 }
 puts("window-held");fflush(stdout);
 if(!continue_line()){CloseHandle(h);return 34;}
 if(!UnlockFileEx(h,0,80,0,&o)){CloseHandle(h);return 35;}
 CloseHandle(h);puts("window-released");fflush(stdout);return 0;
}
int main(int argc,char **argv){
 WCHAR root[WR_PATH],leases[WR_PATH],manifest[WR_PATH];
 lm_wr_record expected;lm_rr *reader=NULL;lm_rr_result result;wr_error e={0};
 int opened,checked;const char *open_reason;DWORD open_native;
 if(argc!=4||!wr_utf8(argv[2],root,&e))return 2;
 if(!strcmp(argv[1],"helper"))return helper(root,!strcmp(argv[3],"drift"));
 if(strcmp(argv[1],"reader"))return 3;
 if(swprintf(leases,WR_PATH,L"%ls-lease",root)<0||
    swprintf(manifest,WR_PATH,L"%ls-expected.json",root)<0)return 4;
 if(!load(manifest,&expected))return 5;
 opened=lm_rr_open(leases,expected.root,0,root,L"target.bin",L"published.bin",
  &expected,2,&reader,&result,&e);
 open_reason=e.reason?e.reason:"none";open_native=e.native;
 checked=reader?lm_rr_check(reader,&e):0;
 printf("{\"source\":\"%s\",\"opened\":%s,\"object_retained\":%s,"
  "\"classification\":%d,\"checked\":%s,\"hook_calls\":%u,"
  "\"open_reason\":\"%s\",\"open_native\":%lu,\"check_reason\":\"%s\","
  "\"result_generation_unconfirmed\":%llu,\"result_pending_unconfirmed\":%d,"
  "\"lease_restored\":%s}\n",
  SOURCE_SHA,opened?"true":"false",reader?"true":"false",
  (int)result.classification,checked?"true":"false",hook_calls,
  open_reason,(unsigned long)open_native,e.reason?e.reason:"none",
  (unsigned long long)result.generation,result.pending,result.lease_restored?"true":"false");
 fflush(stdout);
 if(!continue_line()){lm_rr_close(reader);return 6;}
 lm_rr_close(reader);puts("reader-closed");fflush(stdout);return 0;
}
