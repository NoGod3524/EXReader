/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static void *read_book(const char *dir,const char *name,size_t *size) {
  char path[4096]; FILE *file; long length; void *data;
  snprintf(path,sizeof(path),"%s/%s",dir,name); file=fopen(path,"rb"); CHECK(file);
  CHECK(!fseek(file,0,SEEK_END)); length=ftell(file); CHECK(length>0); rewind(file);
  *size=(size_t)length; data=malloc(*size); CHECK(data && fread(data,1,*size,file)==*size); fclose(file); return data;
}
static size_t book_count(exr_library *library) {
  exr_book *books=NULL; size_t count; OK(exr_library_books(library,"",&books,&count,&error));
  exr_books_free(books,count); return count;
}
static void imported(exr_library *library,const char *dir,const char *name,exr_format format,
                       int wanted,const char *override) {
  void *input,*blob=NULL,*expected=NULL; size_t size,n,expected_size=0,count,i;
  int64_t id=0; exr_document *doc=NULL; const exr_resource *resources; exr_book *books=NULL;
  input=read_book(dir,name,&size); OK(exr_document_open_memory(format,input,size,&doc,&error));
  resources=exr_document_resources(doc,&count);
  if(wanted) for(i=0;i<count;i++) if(!strcmp(resources[i].media_type,"image/png")) {
    OK(exr_document_resource(doc,i,&expected,&expected_size,&error)); break;
  }
  if(wanted) CHECK(expected && expected_size && expected_size<=8*1024*1024);
  OK(exr_library_import(library,format,input,size,override,&id,&error)); CHECK(id>0);
  OK(exr_library_blob(library,id,1,&blob,&n,&error));
  CHECK(n==expected_size && (wanted ? blob && !memcmp(blob,expected,n) : !blob)); exr_free(blob);
  OK(exr_library_blob(library,id,0,&blob,&n,&error)); CHECK(n==size && !memcmp(blob,input,size)); exr_free(blob);
  OK(exr_library_books(library,"",&books,&count,&error));
  for(i=0;i<count;i++) if(books[i].id==id) break;
  CHECK(i<count && !strcmp(books[i].title,override ? override : exr_document_title(doc)));
  exr_books_free(books,count); exr_free(expected); exr_document_free(doc); free(input);
}
int main(int argc,char **argv) {
  exr_library *library=NULL; void *input; size_t n,rows; int64_t id=99;
  CHECK(argc==2); OK(exr_library_open(":memory:",&library,&error));
  imported(library,argv[1],"cover-import.epub",EXR_EPUB,1,"Chosen title");
  imported(library,argv[1],"rich.fb2",EXR_FB2,1,NULL);
  imported(library,argv[1],"kf8-metadata.azw3",EXR_MOBI,1,NULL);
  imported(library,argv[1],"cover-import-boundary.epub",EXR_EPUB,1,NULL);
  imported(library,argv[1],"cover-import-large.epub",EXR_EPUB,0,NULL);
  imported(library,argv[1],"cover-import-no-flag.epub",EXR_EPUB,0,NULL);
  rows=book_count(library); CHECK(rows==6);
  input=read_book(argv[1],"cover-import-missing.epub",&n);
  CHECK(exr_library_import(library,EXR_EPUB,input,n,NULL,&id,&error)!=EXR_OK && !id);
  CHECK(book_count(library)==rows); free(input); exr_library_close(library);
  printf("%u library cover import checks passed\n",checks); return 0;
}
