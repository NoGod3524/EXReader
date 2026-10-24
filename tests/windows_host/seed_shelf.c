/* SPDX-License-Identifier: MIT */
#define _CRT_SECURE_NO_WARNINGS
#include <exreader.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do { if(!(x)) { fprintf(stderr,"FAIL %d %s (%s)\n",__LINE__,#x,error.message);exit(1); } } while(0)
int main(int argc,char **argv) {
  if(argc!=2) return 2;
  exr_library *library=NULL;exr_error error={0};
  CHECK(exr_library_open(argv[1],&library,&error)==EXR_OK);
  for(unsigned i=0;i<2202;i++) {
    char title[64],body[160];int64_t id=0;int created=0;
    snprintf(title,sizeof(title),"Shelf %04u",i);
    snprintf(body,sizeof(body),"Shelf original %04u. Read this book and return to the same shelf position.\n",i);
    CHECK(exr_library_import_unique(library,EXR_TXT,body,strlen(body),title,&id,&created,&error)==EXR_OK && created);
    exr_book book={0};book.id=id;book.title=title;book.author=i%17==0 ? "Author %_!":"Reader";book.tags="";
    CHECK(exr_library_update(library,&book,&error)==EXR_OK);
  }
  exr_book *books=NULL;size_t count=0;
  CHECK(exr_library_books(library,"",&books,&count,&error)==EXR_OK && count==2202);
  exr_books_free(books,count);exr_library_close(library);
  puts("{\"public_sdk_originals\":2202,\"created\":2202,\"accepted\":true}");return 0;
}
