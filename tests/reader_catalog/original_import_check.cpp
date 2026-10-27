#include "original_import.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#ifdef _WIN32
#include <process.h>
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#else
#include <unistd.h>
#endif
static void require(bool ok,const char *what) { if(!ok) { std::fprintf(stderr,"FAIL: %s\n",what); std::exit(1); } }
static int count(void *p,const reader_catalog_row *) { ++*static_cast<int *>(p);return 0; }
static void stop(void *p,int event) { if(event==*static_cast<int *>(p)) {
#ifdef _WIN32
  _exit(42);
#else
  _exit(42);
#endif
} }
static int cancel(void *p) { return ++*static_cast<int *>(p)>260; }
int main(int argc,char **argv) {
  require(argc==6,"arguments"); const char *db=argv[1],*root=argv[2],*src=argv[3],*name=argv[4],*mode=argv[5];
  reader_catalog *c=nullptr;reader_catalog_error e{}; require(!reader_catalog_open(db,&c,&e),e.message);
  const char *expected="txt:4f45393b25817f506a51b56cc5d61599556e4dd5b0bd59aa00f7eb43cbfc0a86";
  char key[69]={},path[4096];
  if(!std::strcmp(mode,"corrupt")) {
    require(reader_original_verified_path(c,root,expected,path,sizeof(path))==ROI_CORRUPT,"reject corrupted original");
#ifdef _WIN32
    void *held=nullptr; uint64_t bytes=0;
    require(reader_original_verified_handle(c,root,expected,nullptr,&held,&bytes)==ROI_CORRUPT && !held && !bytes,"reject corrupted held original");
#endif
    require(!reader_catalog_close(&c,&e),e.message); return 0;
  }
  if(!std::strcmp(mode,"crash1")||!std::strcmp(mode,"crash2")||!std::strcmp(mode,"crash3")) {
    int event=mode[5]-'0';reader_original_callbacks cb{&event,nullptr,stop};
    reader_original_import(c,root,src,name,"Large","Author","Large",&cb,key);require(false,"crash callback");
  } else if(!std::strcmp(mode,"recover")) {
    int n=0;require(!reader_catalog_page(c,nullptr,nullptr,20,count,&n,&e),e.message);require(n==0,"staged hidden");
    require(reader_original_recover(c,root)==ROI_OK,"recover");
    require(reader_original_import(c,root,src,name,"Large","Author","Large",nullptr,key)==ROI_OK,"import after recovery");
  } else if(!std::strcmp(mode,"published")) {
    int n=0;require(!reader_catalog_page(c,nullptr,nullptr,20,count,&n,&e),e.message);require(n==0,"published staged hidden");
    require(reader_original_recover(c,root)==ROI_OK,"recover publication");
  } else if(!std::strcmp(mode,"cancel")) {
    int calls=0;reader_original_callbacks cb{&calls,cancel,nullptr};
    require(reader_original_import(c,root,src,name,"Large","Author","Large",&cb,key)==ROI_CANCELLED,"cancellation");
    require(reader_original_recover(c,root)==ROI_OK,"recover cancelled");
    require(reader_original_import(c,root,src,name,"Large","Author","Large",nullptr,key)==ROI_OK,"import after cancel");
  } else if(!std::strcmp(mode,"import")) {
    require(reader_original_import(c,root,src,name,"Large","Author","Large",nullptr,key)==ROI_OK,"import");
  } else require(false,"unknown mode");
  require(reader_original_verified_path(c,root,expected,path,sizeof(path))==ROI_OK,"verified reopen");
#ifdef _WIN32
  {
    void *held=nullptr; uint64_t bytes=0;
    require(reader_original_verified_handle(c,root,expected,nullptr,&held,&bytes)==ROI_OK && held && bytes>0,"verified held handle");
    int wide_count=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,path,-1,nullptr,0);
    require(wide_count>0,"path conversion");
    std::wstring wide(static_cast<size_t>(wide_count),L'\0');
    require(MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,path,-1,&wide[0],wide_count)==wide_count,"path conversion");
    HANDLE writer=CreateFileW(wide.c_str(),GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,nullptr,OPEN_EXISTING,0,nullptr);
    require(writer==INVALID_HANDLE_VALUE && GetLastError()==ERROR_SHARING_VIOLATION,"held original denies writes");
    require(!DeleteFileW(wide.c_str()) && GetLastError()==ERROR_SHARING_VIOLATION,"held original denies deletion");
    require(CloseHandle(static_cast<HANDLE>(held))!=0,"release verified handle");
    int calls=260; reader_original_callbacks cb{&calls,cancel,nullptr}; held=nullptr; bytes=0;
    require(reader_original_verified_handle(c,root,expected,&cb,&held,&bytes)==ROI_CANCELLED && !held && !bytes,"cancel verification");
  }
#endif
  require(reader_original_import(c,root,src,name,"Different","Other","Different",nullptr,key)==ROI_DUPLICATE,"duplicate");
  require(!std::strcmp(key,expected),"fixture identity"); int n=0;require(!reader_catalog_page(c,nullptr,nullptr,20,count,&n,&e)&&n==1,"one visible row");
  require(!reader_catalog_close(&c,&e),e.message);std::puts("verified original, duplicate and shelf"); return 0;
}
