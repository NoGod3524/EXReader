/* SPDX-License-Identifier: MIT */
/* Compile the production publication shim with only its OS primitive substituted. */
#include "opds_internal.h"
#include "opds_fs.h"
#include <errno.h>
static int fault;
#ifdef _WIN32
#include <windows.h>
static BOOL call_move(const wchar_t *a,const wchar_t *b,DWORD flags) { return MoveFileExW(a,b,flags); }
static BOOL fault_move(const wchar_t *a,const wchar_t *b,DWORD flags) {
  if(fault) {
    if(fault==2) {
      HANDLE h=CreateFileW(b,GENERIC_WRITE,0,NULL,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,NULL);DWORD n;
      if(h==INVALID_HANDLE_VALUE) return FALSE;
      WriteFile(h,"other writer",12,&n,NULL);CloseHandle(h);
    }
    SetLastError(ERROR_NOT_SUPPORTED);return FALSE;
  }
  return call_move(a,b,flags);
}
#define MoveFileExW fault_move
#else
#include <sys/stat.h>
#include <unistd.h>
static int call_link(const char *a,const char *b) { return link(a,b); }
static int fault_link(const char *a,const char *b) {
  if(fault) {
    if(fault==2) { FILE *f=fopen(b,"wbx");if(!f) return -1;fputs("other writer",f);fclose(f); }
    errno=EOPNOTSUPP;return -1;
  }
  return call_link(a,b);
}
#define link fault_link
#endif
#include "../../extras/opds/src/opds_fs.c"
static unsigned checks;
static void require(int yes,const char *name) { if(!yes) { fprintf(stderr,"FAIL %s\n",name);exit(1); }checks++; }
static void put(const char *path,const char *text) { FILE *f=opds_fopen_new(path);require(f!=NULL,"create test file");fputs(text,f);require(fclose(f)==0,"close test file"); }
static int equals(const char *path,const char *text) { char data[40]={0};FILE *f=opds_fopen_read(path);size_t n;if(!f) return 0;n=fread(data,1,sizeof data,f);fclose(f);return n==strlen(text)&&!memcmp(data,text,n); }
static int publish_main(int argc,char **argv) {
  char tmp[1100],dest[1100];if(argc!=2) return 2;
  snprintf(tmp,sizeof tmp,"%s/temp.bin",argv[1]);snprintf(dest,sizeof dest,"%s/dest.bin",argv[1]);
  put(tmp,"new download");fault=1;
  require(opds_publish(tmp,dest,0)==-1,"unsupported atomic primitive refuses publication");
  require(opds_path_kind(dest)==0&&equals(tmp,"new download"),"absent destination and temporary file unchanged");
  fault=2;
  require(opds_publish(tmp,dest,0)==-1,"atomic failure after another writer publishes is refused");
  require(equals(dest,"other writer")&&equals(tmp,"new download"),"other writer is never overwritten");
  fault=0;
  require(opds_publish(tmp,dest,0)==1,"existing destination returns conflict");
  require(equals(dest,"other writer")&&equals(tmp,"new download"),"normal conflict preserves both files");
  require(opds_publish(tmp,dest,1)==0,"explicit replace remains available");
  require(equals(dest,"new download")&&opds_path_kind(tmp)==0,"replacement publishes complete bytes");
  require(opds_remove(dest)==0,"cleanup");
  printf("{\"passed\":true,\"checks\":%u,\"primitive_failure\":true,\"other_writer_preserved\":true}\n",checks);return 0;
}
#define example_main publish_main
#include "../../extras/opds/examples/entry.h"
