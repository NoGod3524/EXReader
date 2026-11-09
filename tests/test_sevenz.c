/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static const char text[]="The quick brown fox jumps over the lazy reader.\n";
typedef struct { unsigned char *data; size_t size,reads,body_reads; int released,cancel,short_read; } memory;
static size_t read_memory(void *context,uint64_t offset,void *out,size_t n) {
  memory *m=context; m->reads++;
  if(offset==32) m->body_reads++;
  if(offset>=m->size) return 0;
  if(n>m->size-(size_t)offset) n=m->size-(size_t)offset;
  if(m->short_read && n>7) n=7;
  memcpy(out,m->data+(size_t)offset,n); return n;
}
static void release_memory(void *context) { ((memory *)context)->released++; }
static int cancelled(void *context) { return ((memory *)context)->cancel; }
static exr_source source(memory *m) {
  exr_source s={m->size,read_memory,release_memory,m,{cancelled,NULL,m}}; return s;
}
static memory load(const char *dir,const char *name) {
  char path[4096]; FILE *file; memory m={0}; long n;
  snprintf(path,sizeof(path),"%s/sevenz/%s.7z",dir,name);
  file=fopen(path,"rb"); CHECK(file!=NULL); CHECK(!fseek(file,0,SEEK_END)); n=ftell(file); CHECK(n>=0);
  m.size=(size_t)n; m.data=malloc(m.size ? m.size : 1); CHECK(m.data!=NULL);
  rewind(file); CHECK(fread(m.data,1,m.size,file)==m.size); fclose(file); return m;
}
static exr_sevenz *open_book(const char *dir,const char *name,const exr_sevenz_options *options) {
  char path[4096]; exr_sevenz *z=NULL;
  snprintf(path,sizeof(path),"%s/sevenz/%s.7z",dir,name);
  OK(exr_sevenz_open(path,options,&z,&error)); return z;
}
static void member(exr_sevenz *z,size_t i,const char *expected) {
  void *data=NULL; size_t n=0,j,prefix=(sizeof(text)-1)*257;
  OK(exr_sevenz_extract(z,i,&data,&n,&error)); CHECK(data!=NULL);
  if(expected) CHECK(n==strlen(expected) && !memcmp(data,expected,n));
  else {
    CHECK(n==prefix+256*8);
    for(j=0;j<n;j++) CHECK(((unsigned char *)data)[j]==(j<prefix ? (unsigned char)text[j%(sizeof(text)-1)] : (j-prefix)%256));
  }
  exr_free(data);
}
static void codecs(const char *dir) {
  const char *files[]={"codecs","properties"}; size_t i,j,n;
  const exr_sevenz_entry *entries; exr_sevenz *z;
  for(i=0;i<2;i++) {
    z=open_book(dir,files[i],NULL); entries=exr_sevenz_entries(z,&n); CHECK(n==(i ? 6u : 5u));
    for(j=n;j>0;j--) { CHECK(!entries[j-1].is_directory); member(z,j-1,NULL); }
    exr_sevenz_free(z);
  }
  z=open_book(dir,"nested",NULL); entries=exr_sevenz_entries(z,&n); CHECK(n==5);
  CHECK(entries[0].is_directory && entries[1].is_directory && entries[4].is_directory);
  CHECK(!strcmp(entries[2].path,"漫画/卷一/page.txt")); member(z,2,"Nested chapter text.\n"); member(z,3,"");
  exr_sevenz_free(z);
  z=open_book(dir,"empty",NULL); entries=exr_sevenz_entries(z,&n); CHECK(n==2);
  CHECK(entries[1].is_directory && !entries[0].size); member(z,0,""); exr_sevenz_free(z);
  z=open_book(dir,"7zip-lzma",NULL); entries=exr_sevenz_entries(z,&n); CHECK(n==2);
  for(i=0;i<n;i++) member(z,i,!strcmp(entries[i].path,"first.txt") ? "Reference first file.\n" : "Reference nested file.\n");
  exr_sevenz_free(z);
  z=open_book(dir,"7zip-lzma2",NULL); entries=exr_sevenz_entries(z,&n); CHECK(n==2);
  for(i=0;i<n;i++) member(z,i,!strcmp(entries[i].path,"first.txt") ? "Reference first file.\n" : "Reference nested file.\n");
  exr_sevenz_free(z);
}
static void safety(const char *dir) {
  const char *files[]={"traversal","backslash","nested-traversal","absolute","drive","ads","dot",
    "oversized-count","truncated-name","invalid-utf16","unsupported"};
  size_t i,n; exr_sevenz *z=NULL; void *data=(void *)1;
  exr_sevenz_options options=exr_sevenz_options_defaults();
  memory m; exr_source s;
  for(i=0;i<sizeof(files)/sizeof(*files);i++) {
    exr_status status;
    m=load(dir,files[i]); s=source(&m); status=exr_sevenz_open_source(&s,NULL,&z,&error);
    CHECK(status==(i==7 ? EXR_LIMIT : (i==9 ? EXR_ENCODING : (i==10 ? EXR_UNSUPPORTED : EXR_FORMAT))));
    CHECK(!z && !m.released); free(m.data);
  }
  /* Packed input and requested file fit; the solid block's decoded size does not. */
  options.max_unpack_size=1024;
  z=open_book(dir,"lzma2-solid",&options); n=9;
  CHECK(exr_sevenz_extract(z,1,&data,&n,&error)==EXR_LIMIT); CHECK(data==NULL && n==0); exr_sevenz_free(z);
  options.max_header_size=8;
  { char path[4096]; snprintf(path,sizeof(path),"%s/sevenz/lzma2-solid.7z",dir);
    CHECK(exr_sevenz_open(path,&options,&z,&error)==EXR_LIMIT && !z); }
  m=load(dir,"lzma2-solid"); s=source(&m);
  for(i=0;i<m.size;i++) { s.size=i; CHECK(exr_sevenz_open_source(&s,NULL,&z,&error)!=EXR_OK && !z); }
  CHECK(!m.released); s.size=m.size;
  /* Body corruption must not be read during listing, and must fail extraction. */
  m.data[32]^=128; OK(exr_sevenz_open_source(&s,NULL,&z,&error));
  CHECK(exr_sevenz_extract(z,0,&data,&n,&error)==EXR_FORMAT && !data && !n);
  exr_sevenz_free(z); CHECK(m.released==1); free(m.data);
  m=load(dir,"lzma2-solid"); s=source(&m); m.data[m.size-1]^=1;
  CHECK(exr_sevenz_open_source(&s,NULL,&z,&error)==EXR_FORMAT && !z && !m.released); free(m.data);
  CHECK(exr_sevenz_open_source(NULL,NULL,&z,&error)==EXR_ARGUMENT && !z);
  CHECK(exr_sevenz_extract(NULL,0,&data,&n,&error)==EXR_ARGUMENT && !data && !n);
  CHECK(!exr_sevenz_entries(NULL,&n) && !n); exr_sevenz_free(NULL);
}
static void source_contract(const char *dir) {
  memory m=load(dir,"lzma2-solid"); exr_source s=source(&m); exr_sevenz *z=NULL;
  size_t n; const exr_sevenz_entry *entries; void *data;
  m.short_read=1; OK(exr_sevenz_open_source(&s,NULL,&z,&error));
  CHECK(m.reads>3 && !m.body_reads && !m.released);
  entries=exr_sevenz_entries(z,&n); CHECK(n==2 && !strcmp(entries[1].path,"second.txt"));
  member(z,1,"Single requested file.\n"); CHECK(m.body_reads==1); member(z,0,NULL);
  m.cancel=1; CHECK(exr_sevenz_extract(z,0,&data,&n,&error)==EXR_CANCELLED && !data && !n);
  exr_sevenz_free(z); CHECK(m.released==1);
  m.released=0; CHECK(exr_sevenz_open_source(&s,NULL,&z,&error)==EXR_CANCELLED && !z && !m.released);
  free(m.data);
}
int main(int argc,char **argv) {
  CHECK(argc==3);
  if(!strcmp(argv[2],"codecs")) codecs(argv[1]);
  else if(!strcmp(argv[2],"safety")) safety(argv[1]);
  else if(!strcmp(argv[2],"source")) source_contract(argv[1]); else CHECK(0);
  printf("7Z %s: %u checks passed\n",argv[2],checks); return 0;
}
