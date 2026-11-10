/* SPDX-License-Identifier: MIT */
/* Win32 document persistence, independent of the editor and the SDK. */
#ifndef EXR_SHELL_SAVE_H
#define EXR_SHELL_SAVE_H
#include <windows.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

#define SHELL_SAVE_LIMIT ((size_t)32 * 1024 * 1024)
#define SHELL_SAVE_HEADER 24u
#define SHELL_SAVE_TIMER 0x5844
typedef int (*shell_save_validate)(const char *,size_t,void *);
typedef struct {
  int dirty;
  uint64_t revision,autosaved;
} shell_save_state;

static uint32_t shell_save_crc(const void *bytes,size_t size) {
  const unsigned char *p=bytes;uint32_t crc=~0u;
  for(size_t i=0;i<size;i++) {
    crc^=p[i];
    for(int bit=0;bit<8;bit++)crc=(crc>>1)^(0xedb88320u & (0u-(crc&1u)));
  }
  return ~crc;
}
static int shell_save_suffix(wchar_t *out,size_t capacity,const wchar_t *path,const wchar_t *suffix) {
  size_t n=wcslen(path),s=wcslen(suffix);
  if(n+s>=capacity)return 0;
  memcpy(out,path,n*sizeof(*out));memcpy(out+n,suffix,(s+1)*sizeof(*out));return 1;
}
/* Missing and unreadable files are distinct: never silently replace an unreadable original. */
static int shell_save_read(const wchar_t *path,char **bytes,size_t *size) {
  *bytes=NULL;*size=0;
  HANDLE file=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,NULL);
  if(file==INVALID_HANDLE_VALUE)return GetLastError()==ERROR_FILE_NOT_FOUND ? 0:-1;
  LARGE_INTEGER length;DWORD got=0;int ok=0;
  if(GetFileSizeEx(file,&length) && length.QuadPart>=0 && length.QuadPart<=(LONGLONG)(SHELL_SAVE_LIMIT+SHELL_SAVE_HEADER)) {
    char *data=malloc((size_t)length.QuadPart+1);
    if(data) {
      if(ReadFile(file,data,(DWORD)length.QuadPart,&got,NULL) && got==(DWORD)length.QuadPart) {
        data[got]=0;*bytes=data;*size=got;ok=1;
      } else free(data);
    }
  }
  CloseHandle(file);return ok ? 1:-1;
}
static int shell_save_equal(const wchar_t *path,const char *bytes,size_t size,shell_save_validate validate,void *context) {
  char *readback=NULL;size_t count=0;
  int ok=shell_save_read(path,&readback,&count)==1 && count==size && !memcmp(readback,bytes,size) &&
    (!validate || validate(readback,count,context));
  free(readback);return ok;
}
#ifdef SHELL_SAVE_TESTING
/* Only the check executable supplies fault injection; absent from the shipping host. */
static void shell_save_checkpoint(const wchar_t *path,const char *stage);
#define SHELL_SAVE_CHECK(path,stage) shell_save_checkpoint(path,stage)
#else
#define SHELL_SAVE_CHECK(path,stage) ((void)0)
#endif
static int shell_save_flush(const wchar_t *path,const char *bytes,size_t size,const FILETIME *time) {
  HANDLE file=CreateFileW(path,GENERIC_WRITE,FILE_SHARE_READ,NULL,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);
  if(file==INVALID_HANDLE_VALUE)return 0;
  int ok=1;
  for(size_t at=0;ok && at<size;) {
    DWORD written=0,chunk=(DWORD)(size-at>65536 ? 65536:size-at);
    ok=WriteFile(file,bytes+at,chunk,&written,NULL) && written==chunk;
    at+=written;
    SHELL_SAVE_CHECK(path,"writing");
  }
  if(ok && time)ok=SetFileTime(file,NULL,NULL,time)!=0;
  if(ok)ok=FlushFileBuffers(file)!=0;
  if(!CloseHandle(file))ok=0;
  if(ok)SHELL_SAVE_CHECK(path,"flushed");
  return ok;
}
/* 1: committed and verified; 0: failed, original restored; -1: rollback failed (.bak retained). */
static int shell_save_replace(const wchar_t *path,const char *bytes,size_t size,
    shell_save_validate validate,void *context,const FILETIME *time) {
  wchar_t temp[4096],backup[4096];char *old=NULL;size_t oldsize=0;int result=0;
  if(size>SHELL_SAVE_LIMIT+SHELL_SAVE_HEADER || !shell_save_suffix(temp,4096,path,L".tmp") ||
     !shell_save_suffix(backup,4096,path,L".bak") || (validate && !validate(bytes,size,context)))return 0;
  int existed=shell_save_read(path,&old,&oldsize);
  if(existed<0)return 0;
  WIN32_FILE_ATTRIBUTE_DATA attributes;
  if(existed && !GetFileAttributesExW(path,GetFileExInfoStandard,&attributes)) {free(old);return 0;}
  if(!shell_save_flush(temp,bytes,size,time) || !shell_save_equal(temp,bytes,size,validate,context))goto done;
  if(existed && (!shell_save_flush(backup,old,oldsize,&attributes.ftLastWriteTime) || !shell_save_equal(backup,old,oldsize,NULL,NULL)))goto done;
  SHELL_SAVE_CHECK(temp,"before-replace");
  if(!MoveFileExW(temp,path,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH))goto done;
  SHELL_SAVE_CHECK(path,"readback");
  if(shell_save_equal(path,bytes,size,validate,context)) {result=1;DeleteFileW(backup);}
  else if(existed) {
    /* Keep .bak until rollback itself is verified, including a second I/O failure. */
    if(!shell_save_flush(temp,old,oldsize,&attributes.ftLastWriteTime) ||
       !shell_save_equal(temp,old,oldsize,NULL,NULL) ||
       !MoveFileExW(temp,path,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH) ||
       !shell_save_equal(path,old,oldsize,NULL,NULL))result=-1;
    else DeleteFileW(backup);
  } else if(!DeleteFileW(path) && GetLastError()!=ERROR_FILE_NOT_FOUND)result=-1;
done:
  DeleteFileW(temp);free(old);return result;
}
static void shell_save_put(unsigned char *out,uint64_t value,size_t count) {
  for(size_t i=0;i<count;i++){out[i]=(unsigned char)value;value>>=8;}
}
static uint64_t shell_save_get(const unsigned char *in,size_t count) {
  uint64_t value=0;for(size_t i=0;i<count;i++)value|=(uint64_t)in[i]<<(i*8);return value;
}
typedef struct {shell_save_validate validate;void *context;} shell_save_envelope;
static int shell_save_unwrap(const char *bytes,size_t size,void *context) {
  const unsigned char *h=(const unsigned char *)bytes;shell_save_envelope *e=context;
  return size>=SHELL_SAVE_HEADER && !memcmp(h,"EXRAUTO1",8) &&
    shell_save_get(h+8,8)==size-SHELL_SAVE_HEADER &&
    shell_save_get(h+20,4)==shell_save_crc(h,20) &&
    shell_save_get(h+16,4)==shell_save_crc(h+SHELL_SAVE_HEADER,size-SHELL_SAVE_HEADER) &&
    (!e->validate || e->validate(bytes+SHELL_SAVE_HEADER,size-SHELL_SAVE_HEADER,e->context));
}
static int shell_save_autosave(const wchar_t *original,const char *bytes,size_t size,
    shell_save_validate validate,void *context) {
  wchar_t path[4096];
  if(size>SHELL_SAVE_LIMIT || !shell_save_suffix(path,4096,original,L".autosave"))return 0;
  char *wrapped=malloc(size+SHELL_SAVE_HEADER);if(!wrapped)return 0;
  memcpy(wrapped,"EXRAUTO1",8);shell_save_put((unsigned char *)wrapped+8,size,8);
  shell_save_put((unsigned char *)wrapped+16,shell_save_crc(bytes,size),4);
  shell_save_put((unsigned char *)wrapped+20,shell_save_crc(wrapped,20),4);
  memcpy(wrapped+SHELL_SAVE_HEADER,bytes,size);
  WIN32_FILE_ATTRIBUTE_DATA attr;FILETIME time;GetSystemTimeAsFileTime(&time);
  if(GetFileAttributesExW(original,GetFileExInfoStandard,&attr) && CompareFileTime(&time,&attr.ftLastWriteTime)<=0) {
    ULARGE_INTEGER next;next.LowPart=attr.ftLastWriteTime.dwLowDateTime;next.HighPart=attr.ftLastWriteTime.dwHighDateTime;
    next.QuadPart++;time.dwLowDateTime=next.LowPart;time.dwHighDateTime=next.HighPart;
  }
  shell_save_envelope envelope={validate,context};
  int ok=shell_save_replace(path,wrapped,size+SHELL_SAVE_HEADER,shell_save_unwrap,&envelope,&time);
  free(wrapped);return ok;
}
/* 0: no newer copy; 1: valid newer copy; -1: damaged/unreadable copy. */
static int shell_save_recovery(const wchar_t *original,char **bytes,size_t *size,
    shell_save_validate validate,void *context) {
  wchar_t path[4096];WIN32_FILE_ATTRIBUTE_DATA copy,source;*bytes=NULL;*size=0;
  if(!shell_save_suffix(path,4096,original,L".autosave"))return -1;
  if(!GetFileAttributesExW(path,GetFileExInfoStandard,&copy))return GetLastError()==ERROR_FILE_NOT_FOUND ? 0:-1;
  if(GetFileAttributesExW(original,GetFileExInfoStandard,&source)) {
    if(CompareFileTime(&copy.ftLastWriteTime,&source.ftLastWriteTime)<=0)return 0;
  } else if(GetLastError()!=ERROR_FILE_NOT_FOUND)return -1;
  shell_save_envelope envelope={validate,context};char *wrapped=NULL;size_t count=0;
  if(shell_save_read(path,&wrapped,&count)!=1 || !shell_save_unwrap(wrapped,count,&envelope)) {free(wrapped);return -1;}
  *size=count-SHELL_SAVE_HEADER;memmove(wrapped,wrapped+SHELL_SAVE_HEADER,*size);wrapped[*size]=0;*bytes=wrapped;return 1;
}
static int shell_save_discard(const wchar_t *original) {
  wchar_t path[4096];if(!shell_save_suffix(path,4096,original,L".autosave"))return 0;
  return DeleteFileW(path) || GetLastError()==ERROR_FILE_NOT_FOUND;
}
#endif
