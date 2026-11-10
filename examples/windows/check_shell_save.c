/* SPDX-License-Identifier: MIT */
/* Checks the production persistence functions, including deterministic crash windows. */
#define WIN32_LEAN_AND_MEAN
#define SHELL_SAVE_TESTING
#include "shell_save.h"
#include <assert.h>
#include <stdio.h>

static const char *pause_stage;
static int corrupt_readback,corrupt_temp,block_rollback;
static wchar_t ready[4096];
static void shell_save_checkpoint(const wchar_t *path,const char *stage) {
  int temp=wcslen(path)>=4 && !wcscmp(path+wcslen(path)-4,L".tmp");
  if((corrupt_readback && !strcmp(stage,"readback")) || (corrupt_temp && temp && !strcmp(stage,"flushed"))) {
    HANDLE file=CreateFileW(path,GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_EXISTING,0,NULL);
    assert(file!=INVALID_HANDLE_VALUE);DWORD written=0;
    assert(WriteFile(file,"!",1,&written,NULL) && written==1);assert(FlushFileBuffers(file));CloseHandle(file);
    if(block_rollback && !strcmp(stage,"readback")) {
      wchar_t blocked[4096];assert(shell_save_suffix(blocked,4096,path,L".tmp"));
      assert(CreateDirectoryW(blocked,NULL));
    }
    corrupt_readback=corrupt_temp=0;
  }
  if(pause_stage && temp && !strcmp(stage,pause_stage)) {
    HANDLE signal=CreateFileW(ready,GENERIC_WRITE,FILE_SHARE_READ,NULL,CREATE_ALWAYS,0,NULL);
    assert(signal!=INVALID_HANDLE_VALUE);CloseHandle(signal);
    for(;;)Sleep(25); /* Parent uses Stop-Process -Force while the real write is paused. */
  }
}
static int valid(const char *data,size_t size,void *unused) {
  (void)unused;return size>2 && data[0]=='{' && data[size-2]=='}' && data[size-1]=='\n';
}
static const char old[]="{\"version\":1,\"text\":\"previous complete version\"}\n";
static const char changed[]="{\"version\":1,\"text\":\"new note, UTF-8: 中文 😀\"}\n";
int main(int argc,char **argv) {
  SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);
  assert(argc>=3);wchar_t directory[3500],path[4096],auto_path[4096];
  assert(MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,argv[2],-1,directory,3500));
  CreateDirectoryW(directory,NULL);swprintf(path,4096,L"%ls\\atomic.json",directory);
  assert(shell_save_suffix(auto_path,4096,path,L".autosave"));
  if(!strcmp(argv[1],"kill")) {
    assert(argc==4);pause_stage=argv[3];swprintf(ready,4096,L"%ls\\ready",directory);
    size_t size=1024*1024;char *large=malloc(size);assert(large);
    memset(large,'x',size);memcpy(large,"{\"text\":\"",9);memcpy(large+size-4,"\"}\n",4);size--;
    int result=shell_save_replace(path,large,size,valid,NULL,NULL);free(large);return result!=1;
  }
  assert(!strcmp(argv[1],"selftest"));
  assert(shell_save_crc("123456789",9)==0xcbf43926u);
  assert(shell_save_replace(path,old,sizeof(old)-1,valid,NULL,NULL)==1);
  assert(shell_save_autosave(path,changed,sizeof(changed)-1,valid,NULL)==1);
  assert(shell_save_equal(path,old,sizeof(old)-1,valid,NULL));
  char *recovered=NULL;size_t size=0;
  assert(shell_save_recovery(path,&recovered,&size,valid,NULL)==1);
  assert(size==sizeof(changed)-1 && !memcmp(recovered,changed,size));free(recovered);
  /* Truncation, wrong CRC, and valid CRC with invalid structure all reject safely. */
  char *wrapped=NULL;assert(shell_save_read(auto_path,&wrapped,&size)==1);
  assert(shell_save_flush(auto_path,wrapped,size-1,NULL));
  assert(shell_save_recovery(path,&recovered,&size,valid,NULL)==-1);
  assert(shell_save_autosave(path,changed,sizeof(changed)-1,valid,NULL)==1);
  wrapped[24]^=1;assert(shell_save_flush(auto_path,wrapped,sizeof(changed)-1+24,NULL));free(wrapped);
  assert(shell_save_recovery(path,&recovered,&size,valid,NULL)==-1);
  assert(shell_save_autosave(path,"broken",6,NULL,NULL)==1);
  assert(shell_save_recovery(path,&recovered,&size,valid,NULL)==-1);
  assert(shell_save_discard(path));assert(shell_save_recovery(path,&recovered,&size,valid,NULL)==0);
  assert(shell_save_replace(path,"broken",6,valid,NULL,NULL)==0);
  assert(shell_save_equal(path,old,sizeof(old)-1,valid,NULL));
  corrupt_temp=1;assert(shell_save_replace(path,changed,sizeof(changed)-1,valid,NULL,NULL)==0);
  assert(shell_save_equal(path,old,sizeof(old)-1,valid,NULL));
  WIN32_FILE_ATTRIBUTE_DATA before,after;
  assert(GetFileAttributesExW(path,GetFileExInfoStandard,&before));
  corrupt_readback=1;assert(shell_save_replace(path,changed,sizeof(changed)-1,valid,NULL,NULL)==0);
  assert(shell_save_equal(path,old,sizeof(old)-1,valid,NULL));
  assert(GetFileAttributesExW(path,GetFileExInfoStandard,&after));
  assert(CompareFileTime(&before.ftLastWriteTime,&after.ftLastWriteTime)==0);
  wchar_t backup[4096],temp_path[4096];
  assert(shell_save_suffix(backup,4096,path,L".bak"));assert(shell_save_suffix(temp_path,4096,path,L".tmp"));
  corrupt_readback=block_rollback=1;
  assert(shell_save_replace(path,changed,sizeof(changed)-1,valid,NULL,NULL)==-1);
  assert(shell_save_equal(backup,old,sizeof(old)-1,valid,NULL));
  assert(RemoveDirectoryW(temp_path));block_rollback=0;
  assert(MoveFileExW(backup,path,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH));
  DeleteFileW(path);corrupt_readback=1;
  assert(shell_save_replace(path,changed,sizeof(changed)-1,valid,NULL,NULL)==0);
  assert(GetFileAttributesW(path)==INVALID_FILE_ATTRIBUTES);
  assert(shell_save_replace(path,old,sizeof(old)-1,valid,NULL,NULL)==1);
  assert(shell_save_autosave(path,changed,sizeof(changed)-1,valid,NULL)==1);
  /* Test ordering explicitly; filesystem and wall clocks need not tick together. */
  WIN32_FILE_ATTRIBUTE_DATA copy;assert(GetFileAttributesExW(auto_path,GetFileExInfoStandard,&copy));
  ULARGE_INTEGER next;next.LowPart=copy.ftLastWriteTime.dwLowDateTime;next.HighPart=copy.ftLastWriteTime.dwHighDateTime;next.QuadPart++;
  FILETIME newer={next.LowPart,next.HighPart};
  assert(shell_save_replace(path,changed,sizeof(changed)-1,valid,NULL,&newer)==1);
  assert(shell_save_recovery(path,&recovered,&size,valid,NULL)==0);
  assert(shell_save_discard(path));
  puts("PASS CRC32; length; truncation; payload CRC; structure; discard; timestamp; temp validation; readback rollback; failed rollback retains backup; first-save rollback");
  return 0;
}
