/* SPDX-License-Identifier: MIT */
#include <exr_wh3_win.h>
#include <exr/library.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>
typedef struct {size_t books;uint64_t bytes;} proof_result;
static int prove_library(void *context,const wchar_t *path) {
 proof_result *result=context;char utf8[4*MAX_PATH];unsigned char buffer[65536];
 exr_library *library=NULL;exr_book *books=NULL;exr_error error={0};exr_source source={0};
 size_t n=0,k;int ok=0;uint64_t total=0;
 if(!WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,path,-1,utf8,sizeof(utf8),NULL,NULL)||
    exr_library_open(utf8,&library,&error)!=EXR_OK)goto done;
 if(exr_library_books(library,NULL,&books,&n,&error)!=EXR_OK)goto done;
 for(k=0;k<n;k++){
  uint64_t offset=0;
  if(exr_library_source(library,books[k].id,&source,&error)!=EXR_OK)goto done;
  if(!source.read_at||!source.release||UINT64_MAX-total<source.size)goto done;
  while(offset<source.size){
   size_t want=(size_t)((source.size-offset)>sizeof(buffer)?sizeof(buffer):(source.size-offset));
   if(source.read_at(source.context,offset,buffer,want)!=want)goto done;
   offset+=want;
  }
  total+=source.size;source.release(source.context);memset(&source,0,sizeof(source));
 }
 result->books=n;result->bytes=total;ok=1;
done:
 if(source.release)source.release(source.context);
 exr_books_free(books,n);exr_library_close(library);return ok;
}
static int absolute(const wchar_t *input,wchar_t output[MAX_PATH]) {
 DWORD n=GetFullPathNameW(input,MAX_PATH,output,NULL);
 return n>3&&n<MAX_PATH&&output[1]==L':'&&output[2]==L'\\';
}
int wmain(int argc,wchar_t **argv) {
 wchar_t library[MAX_PATH],root[MAX_PATH];proof_result result={0};wh3wr_registration *admission=NULL;int ok=0;
 if(argc<3||!absolute(argv[2],library))goto usage;
 if(!wcscmp(argv[1],L"check")){
  if(argc!=3)goto usage;
  ok=wh3wr_open(library,WH3WG_SHARED,NULL,&admission)&&
     prove_library(&result,library)&&wh3wr_check(admission);
  if(!wh3wr_close(admission))ok=0;
 }else if(!wcscmp(argv[1],L"next-epoch")){
  if(argc!=3)goto usage;
  ok=wh3wr_next_epoch(library,prove_library,&result,NULL);
 }else if(!wcscmp(argv[1],L"recover-enrollment")){
  if(argc!=3)goto usage;
  ok=wh3wr_recover_enrollment(library,prove_library,&result);
 }else if(!wcscmp(argv[1],L"enroll")||!wcscmp(argv[1],L"create")){
  if(argc!=4||!absolute(argv[3],root))goto usage;
  ok=wh3wr_enroll_created(library,root,!wcscmp(argv[1],L"create"),prove_library,&result);
 }else goto usage;
 printf("{\"admitted\":%s,\"books\":%llu,\"original_bytes\":%llu}\n",ok?"true":"false",
   (unsigned long long)result.books,(unsigned long long)result.bytes);
 if(!ok)fputs("Admission refused; existing files and recovery evidence were retained.\n",stderr);
 return ok?0:2;
usage:
 fputs("Usage: exreader-c02-admission create|enroll LIBRARY NEW_DOMAIN_ROOT\n"
       "       exreader-c02-admission recover-enrollment|next-epoch|check LIBRARY\n",stderr);
 return 64;
}
