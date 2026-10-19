/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static exr_document *make(const char *a,const char *b,const char *c,const char *tail) {
  exr_node_input nodes[]={{EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0},{EXR_NODE_CHAPTER,0,NULL,NULL,NULL,0},
    {EXR_NODE_ELEMENT,1,"html",NULL,NULL,0},{EXR_NODE_ELEMENT,2,"head",NULL,NULL,0},{EXR_NODE_ELEMENT,2,"body",NULL,NULL,0},
    {EXR_NODE_PARAGRAPH,4,"p",NULL,NULL,0},{EXR_NODE_TEXT,5,NULL,a,NULL,0},{EXR_NODE_ELEMENT,5,"em",NULL,NULL,0},{EXR_NODE_TEXT,7,NULL,b,NULL,0},
    {EXR_NODE_TEXT,5,NULL,c,NULL,0},{EXR_NODE_PARAGRAPH,4,"p",NULL,NULL,0},{EXR_NODE_TEXT,10,NULL,tail,NULL,0}};
  exr_chapter_input chapter={"main","main.xhtml",1,1}; exr_document_input input={"Assertions",nodes,12,&chapter,1,NULL,0}; exr_document *d=NULL;
  OK(exr_document_create(&input,&d,&error)); return d;
}
static void locate(exr_document *d,const char *cfi,size_t node,size_t offset,unsigned side) {
  exr_cfi_point p; OK(exr_document_cfi_path_resolve(d,0,cfi,NULL,&p,&error)); CHECK(p.node==node && p.offset==offset && p.side==side);
}
typedef struct { int stopped,starts; } cancel_state;
static int cancel(void *context) { return ((cancel_state *)context)->stopped; }
static void progress(void *context,exr_stage stage,uint64_t done,uint64_t total) { cancel_state *s=context; (void)stage; (void)total; if(done==1 && ++s->starts>1) s->stopped=1; }
static void full(exr_document *original) {
  exr_document *d=NULL; void *zip=NULL; size_t size,i,count,chapter; const exr_node *nodes; exr_cfi_point point,found; char *cfi=NULL,*quoted;
  OK(exr_document_export_epub(original,NULL,&zip,&size,&error)); OK(exr_document_open_memory(EXR_EPUB,zip,size,&d,&error)); exr_free(zip);
  nodes=exr_document_nodes(d,&count); for(i=0;i<count;i++) if(nodes[i].kind==EXR_NODE_TEXT && !strcmp(nodes[i].text,"A😀")) break; CHECK(i<count); point=(exr_cfi_point){i,0,0};
  OK(exr_document_cfi_create(d,0,&point,NULL,&cfi,&error)); size=strlen(cfi); quoted=malloc(size+64); CHECK(quoted); memcpy(quoted,cfi,size-1); strcpy(quoted+size-1,"[A😀,B])");
  OK(exr_document_cfi_resolve(d,quoted,NULL,&chapter,&found,&error)); CHECK(chapter==0 && found.node==i && found.offset==3);
  exr_free(cfi); free(quoted); point.offset=3;
  OK(exr_document_cfi_create_quoted(d,0,&point,2,NULL,&cfi,&error));
  OK(exr_document_cfi_resolve(d,cfi,NULL,&chapter,&found,&error)); CHECK(found.node==i && found.offset==3); exr_free(cfi);
  { exr_publication *p=NULL; exr_document *part=NULL,*resolved=NULL; const exr_node *v;
    OK(exr_document_export_epub(original,NULL,&zip,&size,&error)); OK(exr_publication_open_memory(EXR_EPUB,zip,size,&p,&error)); exr_free(zip); OK(exr_publication_load(p,0,&part,&error));
    v=exr_document_nodes(part,&count); for(i=0;i<count;i++) if(v[i].kind==EXR_NODE_TEXT && !strcmp(v[i].text,"A😀")) break; CHECK(i<count); point=(exr_cfi_point){i,3,1};
    OK(exr_publication_cfi_create_quoted(p,0,part,&point,2,NULL,&cfi,&error)); OK(exr_publication_cfi_resolve(p,cfi,NULL,&chapter,&resolved,&found,&error)); CHECK(chapter==0 && found.offset==3 && found.side==1);
    exr_free(cfi); exr_document_free(part); exr_document_free(resolved); exr_publication_free(p);
  }
  exr_document_free(d);
}
int main(void) {
  exr_document *d=make("A😀","B"," \t\n C","repeated repeated"); exr_cfi_point point; exr_control control={0}; cancel_state stopped={0}; size_t i;
  const char *bad[]={"/4/4/1:0[repeat,ed]","/4/2/1:0[absent]","/4/2/1:0[A,B,C]","/4/2/1:0[,]","/4/2/1:0[before;unknown=x]","/4/2/1:0[before,after;s=x]"};
  locate(d,"/4/2/1:3[A😀,B]",6,3,0); locate(d,"/4/2/2/1:0[A😀,B]",8,0,0);
  locate(d,"/4/2/1:0[A😀,B]",6,3,0); locate(d,"/4/2/1:99[A😀,B]",6,3,0); locate(d,"/4/2/1:2[A😀,B]",6,3,0);
  locate(d,"/4/4/1:0[A😀,B]",6,3,0); locate(d,"/4/2/1:0[A😀]",6,3,0); locate(d,"/4/2/1:0[,B C]",6,3,0);
  locate(d,"/4/2/3:1[B ,C]",9,1,0); locate(d,"/4/2/3:0[B, C]",9,0,0); locate(d,"/4/2/3:99[B ,C]",9,1,0);
  locate(d,"/4/2/1:0[A😀,B;s=a]",6,3,2); locate(d,"/4/4/1:6[repeat,ed]",11,6,0);
  for(i=0;i<sizeof(bad)/sizeof(*bad);i++) CHECK(exr_document_cfi_path_resolve(d,0,bad[i],NULL,&point,&error)==EXR_FORMAT && point.node==SIZE_MAX && point.offset==SIZE_MAX);
  control.cancelled=cancel; control.progress=progress; control.context=&stopped;
  CHECK(exr_document_cfi_path_resolve(d,0,"/4/2/1:0[A😀,B]",&control,&point,&error)==EXR_CANCELLED && point.node==SIZE_MAX);
  { exr_document *changed=make("XXA😀","B"," \t\n C","repeated repeated"); exr_cfi_point p={6,3,2},found; char *path=NULL;
    OK(exr_document_cfi_path_create_quoted(d,0,&p,2,NULL,&path,&error)); CHECK(!strcmp(path,"/4/2/1:3[A😀,B ;s=a]"));
    OK(exr_document_cfi_path_resolve(changed,0,path,NULL,&found,&error)); CHECK(found.node==6 && found.offset==5 && found.side==2); exr_free(path);
    p.offset=2; CHECK(exr_document_cfi_path_create_quoted(d,0,&p,2,NULL,&path,&error)==EXR_ARGUMENT && !path); p.offset=3; p.side=3;
    CHECK(exr_document_cfi_path_create_quoted(d,0,&p,2,NULL,&path,&error)==EXR_ARGUMENT && !path); p.side=0;
    CHECK(exr_document_cfi_path_create_quoted(d,0,&p,0,NULL,&path,&error)==EXR_ARGUMENT && !path);
    CHECK(exr_document_cfi_path_create_quoted(d,0,&p,33,NULL,&path,&error)==EXR_ARGUMENT && !path); exr_document_free(changed);
  }
  full(d); exr_document_free(d);
  d=make("x[1],(^)","","",""); locate(d,"/4/2/1:5[x^[1^]^,,^(^^^)]",6,5,0); exr_document_free(d);
  d=make("","","",""); { char *path=NULL; exr_cfi_point p={6,0,0}; OK(exr_document_cfi_path_create_quoted(d,0,&p,2,NULL,&path,&error)); CHECK(!strcmp(path,"/4/2/1:0")); exr_free(path); } CHECK(exr_document_cfi_path_resolve(d,0,"/4/2/1:0[absent]",NULL,&point,&error)==EXR_FORMAT && point.node==SIZE_MAX); exr_document_free(d);
  printf("%u CFI text assertion checks passed\n",checks); return 0;
}
