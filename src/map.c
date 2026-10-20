/* SPDX-License-Identifier: MIT */
#if defined(__linux__) && !defined(_DEFAULT_SOURCE)
#define _DEFAULT_SOURCE
#endif
#include "base_internal.h"
#ifdef _WIN32
#include <windows.h>
#else
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#endif
exr_status exr_map_file(const char *path,exr_mapping *mapping,exr_error *error) {
  if(!path || !mapping) return exr_fail(error,EXR_ARGUMENT,"Invalid mapping arguments");
  memset(mapping,0,sizeof(*mapping));
#ifdef _WIN32
  { int length=MultiByteToWideChar(CP_UTF8,0,path,-1,NULL,0);wchar_t *wide;HANDLE file,section;LARGE_INTEGER size;void *address;
    if(length<=0) return exr_fail(error,EXR_ARGUMENT,"Publication path is not UTF-8");
    wide=malloc((size_t)length*sizeof(*wide));if(!wide) return exr_fail(error,EXR_MEMORY,"Mapping path allocation failed");
    MultiByteToWideChar(CP_UTF8,0,path,-1,wide,length);
    file=CreateFileW(wide,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,NULL,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,NULL);
    free(wide);
    if(file==INVALID_HANDLE_VALUE) return exr_fail(error,EXR_IO,"Cannot open mapped publication");
    if(!GetFileSizeEx(file,&size) || size.QuadPart<=0 || (uint64_t)size.QuadPart>SIZE_MAX) { CloseHandle(file);return exr_fail(error,EXR_LIMIT,"Invalid or oversized mapped publication"); }
    section=CreateFileMappingW(file,NULL,PAGE_READONLY,0,0,NULL);
    if(!section) { CloseHandle(file);return exr_fail(error,EXR_IO,"Cannot create publication mapping"); }
    address=MapViewOfFile(section,FILE_MAP_READ,0,0,0);
    if(!address) { CloseHandle(section);CloseHandle(file);return exr_fail(error,EXR_IO,"Cannot map publication view"); }
    mapping->address=address;mapping->size=(size_t)size.QuadPart;mapping->file=file;mapping->mapping=section;
    return EXR_OK;
  }
#else
  { int fd=open(path,O_RDONLY);struct stat info;void *address;
    if(fd<0) return exr_fail(error,EXR_IO,"Cannot open mapped publication");
    if(fstat(fd,&info) || info.st_size<=0 || (uint64_t)info.st_size>SIZE_MAX) { close(fd);return exr_fail(error,EXR_LIMIT,"Invalid or oversized mapped publication"); }
    address=mmap(NULL,(size_t)info.st_size,PROT_READ,MAP_PRIVATE,fd,0);
    close(fd);
    if(address==MAP_FAILED) return exr_fail(error,EXR_IO,"Cannot map publication");
    mapping->address=address;mapping->size=(size_t)info.st_size;
    return EXR_OK;
  }
#endif
}
exr_status exr_map_anonymous(size_t size,exr_mapping *mapping,exr_error *error) {
  if(!mapping || !size) return exr_fail(error,EXR_ARGUMENT,"Invalid anonymous mapping arguments");
  memset(mapping,0,sizeof(*mapping));
#ifdef _WIN32
  { HANDLE section;void *address;ULONGLONG length=(ULONGLONG)size;
    section=CreateFileMappingW(INVALID_HANDLE_VALUE,NULL,PAGE_READWRITE,(DWORD)(length>>32),(DWORD)(length&0xffffffffu),NULL);
    if(!section) return exr_fail(error,EXR_MEMORY,"Cannot create anonymous mapping");
    address=MapViewOfFile(section,FILE_MAP_READ|FILE_MAP_WRITE,0,0,0);
    if(!address) { CloseHandle(section);return exr_fail(error,EXR_MEMORY,"Cannot map anonymous view"); }
    mapping->address=address;mapping->size=size;mapping->mapping=section;
    return EXR_OK;
  }
#else
#ifndef MAP_ANONYMOUS
#define MAP_ANONYMOUS MAP_ANON
#endif
  { void *address=mmap(NULL,size,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    if(address==MAP_FAILED) return exr_fail(error,EXR_MEMORY,"Cannot map anonymous storage");
    mapping->address=address;mapping->size=size;
    return EXR_OK;
  }
#endif
}
void exr_unmap(exr_mapping *mapping) {
  if(!mapping) return;
#ifdef _WIN32
  if(mapping->address) UnmapViewOfFile(mapping->address);
  if(mapping->mapping) CloseHandle((HANDLE)mapping->mapping);
  if(mapping->file) CloseHandle((HANDLE)mapping->file);
#else
  if(mapping->address) munmap(mapping->address,mapping->size);
#endif
  memset(mapping,0,sizeof(*mapping));
}
