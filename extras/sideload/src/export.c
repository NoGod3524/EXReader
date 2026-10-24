/* SPDX-License-Identifier: MIT */
#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#define _FILE_OFFSET_BITS 64
#endif
#include "exr_sideload.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#include <bcrypt.h>
#else
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#ifdef __ANDROID__
#include <sys/syscall.h>
#include <linux/fs.h>
#endif
#endif

static exr_status failure(exr_error *error,exr_status code,const char *message) {
  if(error){error->code=code;snprintf(error->message,sizeof(error->message),"%s",message);}
  return code;
}
static exr_status poll(const exr_control *control,uint64_t done,uint64_t total,exr_error *error) {
  if(control->cancelled&&control->cancelled(control->context))return failure(error,EXR_CANCELLED,"Original export cancelled before publication");
  if(control->progress)control->progress(control->context,EXR_STAGE_EXPORT,done,total);
  if(control->cancelled&&control->cancelled(control->context))return failure(error,EXR_CANCELLED,"Original export cancelled before publication");
  return EXR_OK;
}
#ifdef _WIN32
static wchar_t *wide(const char *path) {
  int size=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,path,-1,NULL,0);
  wchar_t *value;
  if(size<=0)return NULL;
  value=malloc((size_t)size*sizeof(*value));if(!value)return NULL;
  if(!MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,path,-1,value,size)){free(value);return NULL;}
  return value;
}
#endif

exr_status exr_sideload_export_original(exr_library *library,int64_t book_id,const char *destination,
    const exr_sideload_options *options,uint64_t *bytes_written,exr_error *error) {
  exr_source source={0};exr_control control={0};exr_status status=EXR_OK;
  uint64_t limit=EXR_SIDELOAD_STREAM_LIMIT,offset=0;
  unsigned char buffer[65536];char *temporary=NULL;size_t length;int temporary_created=0;
#ifdef _WIN32
  HANDLE file=INVALID_HANDLE_VALUE;wchar_t *target=NULL,*temp=NULL;
#else
  int file=-1;
#endif
  if(error)memset(error,0,sizeof(*error));
  if(bytes_written)*bytes_written=0;
  if(!library||book_id<=0||!destination||!destination[0]||!bytes_written||
      (options&&options->struct_size<sizeof(*options)))return failure(error,EXR_ARGUMENT,"Missing original export arguments or complete options");
  if(options){control=options->control;if(options->max_input_bytes&&options->max_input_bytes<limit)limit=options->max_input_bytes;}
  status=poll(&control,0,0,error);if(status!=EXR_OK)return status;
  status=exr_library_source(library,book_id,&source,error);if(status!=EXR_OK)return status;
  if(!source.read_at||!source.release||!source.size){status=failure(error,EXR_IO,"Original source is unavailable or empty");goto cleanup;}
  if(source.size>limit){status=failure(error,EXR_LIMIT,"Original export exceeds its byte limit");goto cleanup;}
  length=strlen(destination);
  if(length>32700){status=failure(error,EXR_LIMIT,"Original export path is too long");goto cleanup;}
  temporary=malloc(length+64);if(!temporary){status=failure(error,EXR_MEMORY,"Cannot allocate original export path");goto cleanup;}
#ifdef _WIN32
  {
    unsigned char random[16];static const char hex[]="0123456789abcdef";size_t i;
    target=wide(destination);if(!target){status=failure(error,EXR_ARGUMENT,"Original export path is not UTF-8");goto cleanup;}
    if(BCryptGenRandom(NULL,random,sizeof(random),BCRYPT_USE_SYSTEM_PREFERRED_RNG)<0){status=failure(error,EXR_IO,"Cannot create private original export name");goto cleanup;}
    memcpy(temporary,destination,length);memcpy(temporary+length,".exr-export-",12);
    for(i=0;i<sizeof(random);i++){temporary[length+12+i*2]=hex[random[i]>>4];temporary[length+13+i*2]=hex[random[i]&15];}
    temporary[length+44]=0;temp=wide(temporary);if(!temp){status=failure(error,EXR_MEMORY,"Cannot allocate original export path");goto cleanup;}
    file=CreateFileW(temp,GENERIC_WRITE,0,NULL,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,NULL);
    if(file==INVALID_HANDLE_VALUE){status=failure(error,EXR_IO,"Cannot create private original export");goto cleanup;}
    temporary_created=1;
  }
#else
  snprintf(temporary,length+64,"%s.exr-export-XXXXXX",destination);
  file=mkstemp(temporary);
  if(file<0){status=failure(error,EXR_IO,"Cannot create private original export");goto cleanup;}
  temporary_created=1;
#endif
  while(offset<source.size){
    size_t wanted=(source.size-offset)<sizeof(buffer)?(size_t)(source.size-offset):sizeof(buffer),got,at=0;
    status=poll(&control,offset,source.size,error);if(status!=EXR_OK)goto cleanup;
    got=source.read_at(source.context,offset,buffer,wanted);
    if(!got||got>wanted){status=failure(error,EXR_IO,"Original source changed or returned an incomplete read");goto cleanup;}
    while(at<got){
#ifdef _WIN32
      DWORD written=0;
      if(!WriteFile(file,buffer+at,(DWORD)(got-at),&written,NULL)||!written){status=failure(error,EXR_IO,"Original export write failed");goto cleanup;}
      at+=written;
#else
      ssize_t written=write(file,buffer+at,got-at);
      if(written<0&&errno==EINTR)continue;
      if(written<=0){status=failure(error,EXR_IO,"Original export write failed");goto cleanup;}
      at+=(size_t)written;
#endif
    }
    offset+=got;
  }
  status=poll(&control,source.size,source.size,error);if(status!=EXR_OK)goto cleanup;
#ifdef _WIN32
  if(!FlushFileBuffers(file)){status=failure(error,EXR_IO,"Cannot flush original export");goto cleanup;}
  {int closed=CloseHandle(file);file=INVALID_HANDLE_VALUE;if(!closed){status=failure(error,EXR_IO,"Cannot close original export");goto cleanup;}}
#else
  if(fsync(file)!=0){status=failure(error,EXR_IO,"Cannot flush original export");goto cleanup;}
  {int closed=close(file);file=-1;if(closed!=0){status=failure(error,EXR_IO,"Cannot close original export");goto cleanup;}}
#endif
  /* End the SDK borrow before publishing a file that can cross worker queues. */
  source.release(source.context);source.release=NULL;
  status=poll(&control,offset,offset,error);if(status!=EXR_OK)goto cleanup;
#ifdef _WIN32
  if(!MoveFileExW(temp,target,MOVEFILE_WRITE_THROUGH)){status=failure(error,EXR_IO,"Original export destination exists or publication failed");goto cleanup;}
#elif defined(__ANDROID__)
  /* App SELinux permits rename, not hard links. The NDK syscall entry keeps
     API26 support; unsupported filesystems fail without a replacing fallback. */
  if(syscall(SYS_renameat2,AT_FDCWD,temporary,AT_FDCWD,destination,RENAME_NOREPLACE)!=0){status=failure(error,EXR_IO,"Original export destination exists or publication failed");goto cleanup;}
  temporary_created=0;
#else
  /* link is an atomic no-replace publish on the same app-private filesystem. */
  if(link(temporary,destination)!=0){status=failure(error,EXR_IO,"Original export destination exists or publication failed");goto cleanup;}
#endif
  *bytes_written=offset;
cleanup:
  if(source.release)source.release(source.context);
#ifdef _WIN32
  if(file!=INVALID_HANDLE_VALUE)CloseHandle(file);
  if(temporary_created&&temp)DeleteFileW(temp);
  free(temp);free(target);
#else
  if(file>=0)close(file);
  if(temporary_created)unlink(temporary);
#endif
  free(temporary);return status;
}
