/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static void valid(const char *dir,const char *name,const char *expected,size_t chapters) {
  char path[4096]; exr_document *doc=NULL,*copy=NULL; size_t n,i,bold=0; void *data=NULL;
  const exr_chapter *parts; const exr_node *nodes;
  snprintf(path,sizeof(path),"%s/%s",dir,name); OK(exr_document_open(path,&doc,&error));
  CHECK(!strcmp(exr_document_text(doc,NULL),expected));
  parts=exr_document_chapters(doc,&n); CHECK(n==chapters);
  for(i=0;i<n;i++) {
    size_t size; OK(exr_document_resource(doc,parts[i].resource,&data,&size,&error));
    CHECK(size && !memcmp(data,"<html",5)); exr_free(data); data=NULL;
    CHECK(parts[i].in_spine && parts[i].linear);
  }
  nodes=exr_document_nodes(doc,&n);
  for(i=0;i<n;i++) if(nodes[i].name && strstr(nodes[i].name,"|b") && !strcmp(strrchr(nodes[i].name,'|'),"|b")) bold++;
  if(strstr(expected,"bold")) CHECK(bold==1);
  if(!strcmp(name,"kf8-flows.azw3")) {
    const exr_resource *r=exr_document_resources(doc,&n); CHECK(n==3 && !strcmp(r[0].path,"flow0001.bin"));
    OK(exr_document_resource(doc,0,&data,&n,&error)); CHECK(n==strlen("p { color: #123456; }") && !memcmp(data,"p {",3)); exr_free(data);
  }
  OK(exr_document_export_epub(doc,NULL,&data,&n,&error));
  OK(exr_document_open_memory(EXR_EPUB,data,n,&copy,&error)); exr_free(data);
  CHECK(!strcmp(exr_document_text(copy,NULL),expected)); exr_document_free(copy); exr_document_free(doc);
}
int main(int argc,char **argv) {
  const char *bad[]={"indx","pointer","idxt","total","tagx","controls","mask","ordt","version","insert-before","insert-after","length","file","missing-fragment","extra-fragment","overlap","label","fdst","xml","orphan","fdst-gap","vwi","short-header","decreasing-idxt"};
  const char *text="Chapter one\nA bold passage.\nChapter two\nSecond passage."; size_t i;
  CHECK(argc==2);
  valid(argv[1],"kf8-basic.azw3",text,2); valid(argv[1],"kf8-multirecord.azw3",text,2); valid(argv[1],"kf8-multicontrol.azw3",text,2);
  valid(argv[1],"kf8-flows.azw3",text,2);
  valid(argv[1],"kf8-unsplit.azw3","Chapter one\nA bold passage.",1);
  valid(argv[1],"kf8-two-inserts.azw3","One.\nTwo.",1);
  valid(argv[1],"kf8-zero-fragments.azw3","",1);
  for(i=0;i<sizeof(bad)/sizeof(*bad);i++) {
    char path[4096]; exr_document *doc=(exr_document *)(uintptr_t)1; exr_status status;
    snprintf(path,sizeof(path),"%s/kf8-bad-%s.azw3",argv[1],bad[i]); status=exr_document_open(path,&doc,&error);
    if(status!=EXR_FORMAT) fprintf(stderr,"fixture %s returned %d\n",bad[i],status);
    CHECK(status==EXR_FORMAT && !doc && error.code==EXR_FORMAT && error.message[0]);
  }
  printf("%u KF8 checks passed\n",checks); return 0;
}
