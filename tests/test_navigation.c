/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error;
static unsigned checks;
#define CHECK(x) do {checks++;if(!(x)){fprintf(stderr,"line %d: %s (%d: %s)\n", \
 __LINE__,#x,(int)error.code,error.message);exit(1);}}while(0)
#define OK(x) CHECK((x)==EXR_OK)
static exr_publication *open_book(const char *dir,const char *name) {
  char path[4096];exr_publication *p=NULL;
  CHECK(snprintf(path,sizeof(path),"%s/%s",dir,name)>0);
  OK(exr_publication_open(path,&p,&error));return p;
}
static void books(const char *directory) {
  const char *files[]={"navigation-epub2.epub","navigation-epub3.epub","navigation-repeated.epub"};
  size_t f,i,n,again_count;const exr_navigation *v,*again;
  for(f=0;f<3;f++) {
    exr_publication *p=open_book(directory,files[f]);
    OK(exr_publication_navigation(p,&v,&n,&error));CHECK(n==6 && v);
    CHECK(!strcmp(v[0].label,"First & chapter") && !strcmp(v[1].label,"\xe5\xad\x90\xe8\x8a\x82"));
    CHECK(v[0].parent==SIZE_MAX && v[1].parent==0 && v[2].parent==SIZE_MAX && v[3].parent==2);
    CHECK(v[0].part==(f==2 ? SIZE_MAX:0) && v[1].part==(f==2 ? 2u:1u));
    CHECK(!strcmp(v[2].label,"Group") && !v[2].href[0] && v[2].part==SIZE_MAX);
    CHECK(!strcmp(v[4].role,"page-list") && !strcmp(v[4].label,"1"));
    CHECK(!strcmp(v[5].role,f ? "landmarks":"nav-list"));
    CHECK(!strcmp(v[3].label,f ? "Outside":"Again"));
    CHECK(v[3].part==(f ? SIZE_MAX:0));
    for(i=0;i<n;i++) {
      CHECK(!strcmp(v[i].base,f ? "OPS/Nav/nav.xhtml":"OPS/Nav/main.ncx"));
      CHECK(v[i].parent==SIZE_MAX || v[i].parent<i);
    }
    OK(exr_publication_navigation(p,&again,&again_count,&error));CHECK(v==again && n==again_count);
    exr_publication_free(p);
  }
  for(f=0;f<3;f++) {
    const char *invalid[]={"navigation-broken.epub","navigation-entity.epub","navigation-missing.epub"};
    exr_publication *p=open_book(directory,invalid[f]);exr_document *doc=NULL;
    for(i=0;i<2;i++) {
      v=(const exr_navigation *)(uintptr_t)1;n=99;
      CHECK(exr_publication_navigation(p,&v,&n,&error)==EXR_FORMAT && !v && !n);
    }
    OK(exr_publication_load(p,0,&doc,&error));CHECK(!strcmp(exr_document_text(doc,NULL),"A"));
    exr_document_free(doc);exr_publication_free(p);
  }
  {
    exr_publication *p=open_book(directory,"navigation-empty.epub");
    OK(exr_publication_navigation(p,&v,&n,&error));CHECK(!v && !n);exr_publication_free(p);
  }
}
typedef struct {unsigned calls,releases;} provider;
static exr_status load(void *context,size_t part,exr_document **out,exr_error *e) {
  (void)part;((provider *)context)->calls++;return exr_document_open_memory(EXR_TXT,"A",1,out,e);
}
static void release(void *context) {((provider *)context)->releases++;}
static void custom(void) {
  provider host={0};exr_part part={"unit","arbitrary.unit","Host",1};
  char label[]="Root",target[]="custom:resource#time=90";
  exr_navigation values[]={{SIZE_MAX,SIZE_MAX,label,target,"urn:host:base","urn:host:audio"},
                            {0,0,"Child",NULL,NULL,"toc"}};
  exr_publication_input input={0};exr_publication *p=NULL;const exr_navigation *v=NULL;size_t n;
  input.parts=&part;input.part_count=1;input.load=load;input.context=&host;input.release=release;
  input.navigation=values;input.navigation_count=2;
  OK(exr_publication_create(&input,&p,&error));memset(label,'x',4);memset(target,'y',strlen(target));
  OK(exr_publication_navigation(p,&v,&n,&error));CHECK(n==2 && !host.calls);
  CHECK(!strcmp(v[0].label,"Root") && !strcmp(v[0].href,"custom:resource#time=90"));
  CHECK(!strcmp(v[0].role,"urn:host:audio") && v[1].part==0 && !v[1].href[0]);
  exr_publication_free(p);CHECK(host.releases==1);
  host.releases=0;values[0].parent=0;
  CHECK(exr_publication_create(&input,&p,&error)==EXR_ARGUMENT && !p && !host.releases);
  values[0].parent=SIZE_MAX;values[1].part=1;
  CHECK(exr_publication_create(&input,&p,&error)==EXR_ARGUMENT && !p && !host.releases);
  values[1].part=0;values[0].label="\xff";
  CHECK(exr_publication_create(&input,&p,&error)==EXR_ENCODING && !p && !host.releases);
  input.navigation_count=10001;
  CHECK(exr_publication_create(&input,&p,&error)==EXR_LIMIT && !p && !host.releases);
  input.navigation_count=1;input.navigation=NULL;
  CHECK(exr_publication_create(&input,&p,&error)==EXR_ARGUMENT && !p);
  v=(const exr_navigation *)(uintptr_t)1;n=99;
  CHECK(exr_publication_navigation(NULL,&v,&n,&error)==EXR_ARGUMENT && !v && !n);
}
typedef struct {void *data;size_t size,reads,releases,reentry;int cancel;exr_publication *publication;} source_state;
static int cancelled(void *context) {return ((source_state *)context)->cancel;}
static size_t read_at(void *context,uint64_t at,void *out,size_t size) {
  source_state *s=context;const exr_navigation *nav=NULL;size_t n;
  CHECK(at<=s->size && size<=s->size-(size_t)at);s->reads++;
  if(s->publication) {
    exr_error local;
    CHECK(exr_publication_navigation(s->publication,&nav,&n,&local)==EXR_ARGUMENT && !nav && !n);
    s->reentry++;
  }
  memcpy(out,(unsigned char *)s->data+(size_t)at,size);return size;
}
static void release_source(void *context) {((source_state *)context)->releases++;}
static void lazy_source(const char *directory) {
  source_state state={0};exr_source input={0};char path[4096];FILE *file;long size;
  const exr_navigation *v=NULL,*same=NULL;size_t n,reads;
  CHECK(snprintf(path,sizeof(path),"%s/navigation-epub3.epub",directory)>0);
  file=fopen(path,"rb");CHECK(file && !fseek(file,0,SEEK_END));size=ftell(file);CHECK(size>0);
  state.size=(size_t)size;state.data=malloc(state.size);CHECK(state.data && !fseek(file,0,SEEK_SET));
  CHECK(fread(state.data,1,state.size,file)==state.size && !fclose(file));
  input.size=state.size;input.read_at=read_at;input.release=release_source;input.context=&state;
  input.control.cancelled=cancelled;input.control.context=&state;
  OK(exr_publication_open_source(&input,&state.publication,&error));reads=state.reads;
  state.cancel=1;CHECK(exr_publication_navigation(state.publication,&v,&n,&error)==EXR_CANCELLED && !v && !n);
  state.cancel=0;OK(exr_publication_navigation(state.publication,&v,&n,&error));
  CHECK(n==6 && state.reads>reads && state.reentry>0);reads=state.reads;
  OK(exr_publication_navigation(state.publication,&same,&n,&error));CHECK(v==same && state.reads==reads);
  exr_publication_free(state.publication);CHECK(state.releases==1);free(state.data);
}
int main(int argc,char **argv) {
  CHECK(argc==2);books(argv[1]);custom();lazy_source(argv[1]);
  printf("Navigation: %u checks passed\n",checks);return 0;
}
