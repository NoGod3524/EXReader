/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error;
static unsigned checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr,"line %d: %s (%s)\n",__LINE__,#x,error.message); exit(1); } } while (0)
#define OK(x) CHECK((x)==EXR_OK)
static exr_publication *open_book(const char *dir,const char *file) {
  char path[4096]; exr_publication *p=NULL;
  CHECK(snprintf(path,sizeof(path),"%s/%s",dir,file)>0);
  OK(exr_publication_open(path,&p,&error)); return p;
}
static void at(exr_publication *p,const exr_target *target,const char *text) {
  exr_location result; exr_document *d=NULL; const char *value; size_t reverse;
  OK(exr_publication_locate(p,target,&result,&error));
  CHECK(result.state==EXR_LINK_FOUND && result.part==0);
  OK(exr_publication_load(p,0,&d,&error)); value=exr_document_text(d,NULL);
  CHECK(!strncmp(value+result.offset,text,strlen(text)));
  OK(exr_publication_target_at(p,0,result.offset,&reverse,&error));
  CHECK(reverse!=SIZE_MAX); exr_document_free(d);
}
static void navigation(const char *dir,int ncx) {
  const exr_toc_entry *toc,*again; size_t n,second,index; exr_location pos;
  exr_publication *p=open_book(dir,ncx ? "toc-ncx.epub" : "toc-nav.epub");
  OK(exr_publication_toc(p,&toc,&n,&error)); CHECK(n==4);
  CHECK(toc[0].source==(ncx ? EXR_TOC_NCX : EXR_TOC_NAV));
  CHECK(toc[0].level==1 && toc[1].level==2 && toc[2].level==1);
  CHECK(toc[0].target.part==0 && toc[1].target.part==0);
  CHECK(!strcmp(toc[0].title,ncx ? "NCX first" : "First & title"));
  CHECK(!strcmp(toc[1].target.fragment,"\xe5\xad\x90\xe7\xab\xa0"));
  CHECK(toc[0].play_order==(ncx ? 8u : SIZE_MAX));
  CHECK(toc[1].play_order==(ncx ? 2u : SIZE_MAX));
  if (ncx) CHECK(toc[2].play_order==0 && toc[3].play_order==SIZE_MAX);
  else CHECK(toc[2].target.part==SIZE_MAX && toc[3].level==2);
  at(p,&toc[0].target,"\xe7\xac\xac\xe4\xb8\x80\xe7\xab\xa0");
  at(p,&toc[1].target,"\xe7\xac\xac\xe4\xba\x8c\xe7\xab\xa0");
  OK(exr_publication_locate(p,&toc[1].target,&pos,&error));
  OK(exr_publication_target_at(p,0,pos.offset,&index,&error)); CHECK(index==1);
  OK(exr_publication_toc(p,&again,&second,&error)); CHECK(toc==again && n==second);
  exr_publication_free(p);
  if (ncx) {
    p=open_book(dir,"toc-pages-only.epub");
    OK(exr_publication_toc(p,&toc,&n,&error)); CHECK(n==4 && toc[0].source==EXR_TOC_NCX);
    exr_publication_free(p);
    p=open_book(dir,"toc-split.epub");
    OK(exr_publication_toc(p,&toc,&n,&error)); CHECK(n==4);
    CHECK(toc[0].target.part==1 && toc[1].target.part==0);
    OK(exr_publication_locate(p,&toc[0].target,&pos,&error)); CHECK(pos.part==1 && pos.state==EXR_LINK_FOUND);
    exr_publication_free(p);
    p=open_book(dir,"toc-license-nav.epub");
    OK(exr_publication_toc(p,&toc,&n,&error)); CHECK(n==4 && toc[0].source==EXR_TOC_NCX);
    exr_publication_free(p);
  }
}
static void recovery(const char *dir) {
  const char *files[]={"toc-recovery.epub","toc-no-navigation.epub","toc-semantic.epub"};
  size_t f,n,i; const exr_toc_entry *toc;
  for (f=0;f<3;f++) {
    exr_publication *p=open_book(dir,files[f]);
    OK(exr_publication_toc(p,&toc,&n,&error)); CHECK(n==(f==2 ? 2u : 3u));
    for (i=0;i<n;i++) {
      CHECK(toc[i].source==EXR_TOC_RECOVERED && toc[i].target.offset!=SIZE_MAX);
      at(p,&toc[i].target,f==2 ? (i ? "Child" : "Heading") :
        (i ? "\xe7\xac\xac" : "\xe7\xac\xac\xe4\xb8\x80\xe5\x9b\x9e Recovered heading"));
    }
    CHECK(toc[0].level==1 && toc[1].level==(f==2 ? 2u : 1u));
    exr_publication_free(p);
  }
  {
    exr_publication *p=open_book(dir,"toc-recovery-repeated.epub");
    OK(exr_publication_toc(p,&toc,&n,&error)); CHECK(n==4);
    CHECK(!strcmp(toc[0].title,toc[3].title) && toc[3].target.offset>toc[0].target.offset);
    exr_publication_free(p);
    p=open_book(dir,"toc-recovery-boundary.epub");
    OK(exr_publication_toc(p,&toc,&n,&error)); CHECK(n==2 && toc[0].target.part==1);
    exr_publication_free(p);
  }
}
static void fragments(const char *dir) {
  exr_publication *p=open_book(dir,"toc-nav.epub");
  exr_target target; exr_location result; char fragment[2048]; size_t n,index;
  const exr_target *missing; exr_document *d=NULL;
  const char *base="OPS/Text/A B.xhtml";
  OK(exr_publication_resolve_href(p,base,"#Legacy",fragment,&target,&error));
  at(p,&target,"after.");
  OK(exr_publication_resolve_href(p,"OPS/Nav/nav.xhtml","../Text/a%20b.XHTML#%53tart",fragment,&target,&error));
  CHECK(target.part==0 && !strcmp(fragment,"Start")); at(p,&target,"\xe7\xac\xac");
  OK(exr_publication_resolve_href(p,base,"#Case",fragment,&target,&error)); at(p,&target,"One");
  OK(exr_publication_resolve_href(p,base,"#case",fragment,&target,&error)); at(p,&target,"Two");
  OK(exr_publication_resolve_href(p,base,"#CASE",fragment,&target,&error));
  OK(exr_publication_locate(p,&target,&result,&error));
  CHECK(result.state==EXR_LINK_ANCHOR_MISSING && result.offset==0);
  OK(exr_publication_locate(p,&target,&result,&error));
  missing=exr_publication_missing_targets(p,&n);
  /* Reverse lookup also requests the fixture's broken TOC target. */
  CHECK(n==2 && missing && !strcmp(missing[n-1].fragment,"CASE"));
  OK(exr_publication_resolve_href(p,base,"#",fragment,&target,&error));
  OK(exr_publication_locate(p,&target,&result,&error)); CHECK(result.state==EXR_LINK_FOUND && !result.offset);
  OK(exr_publication_resolve_href(p,base,"#empty",fragment,&target,&error));
  OK(exr_publication_locate(p,&target,&result,&error)); CHECK(result.state==EXR_LINK_FOUND && result.offset>0);
  OK(exr_publication_resolve_href(p,base,"missing.xhtml#x",fragment,&target,&error)); CHECK(target.part==SIZE_MAX);
  OK(exr_publication_locate(p,&target,&result,&error)); CHECK(result.state==EXR_LINK_PART_MISSING && result.offset==SIZE_MAX);
  CHECK(exr_publication_resolve_href(p,base,"https://example.org/#x",fragment,&target,&error)==EXR_ARGUMENT);
  CHECK(exr_publication_resolve_href(p,base,"#%00",fragment,&target,&error)==EXR_ARGUMENT);
  CHECK(exr_publication_resolve_href(p,base,"../../../escape",fragment,&target,&error)==EXR_ARGUMENT);
  target=(exr_target){0,"",SIZE_MAX-1};
  CHECK(exr_publication_locate(p,&target,&result,&error)==EXR_ARGUMENT && result.offset==SIZE_MAX);
  CHECK(exr_publication_target_at(p,0,SIZE_MAX,&index,&error)==EXR_ARGUMENT && index==SIZE_MAX);
  OK(exr_publication_load(p,0,&d,&error));
  OK(exr_document_locate(d,"legacy",&result,&error)); CHECK(result.state==EXR_LINK_FOUND);
  OK(exr_document_locate(d,"absent",&result,&error)); CHECK(result.state==EXR_LINK_ANCHOR_MISSING && !result.offset);
  OK(exr_document_locate(d,"duplicate",&result,&error));
  CHECK(result.state==EXR_LINK_FOUND && !strncmp(exr_document_text(d,NULL)+result.offset,"First duplicate",15));
  OK(exr_document_locate(d,"unprojected",&result,&error));
  CHECK(result.state==EXR_LINK_FOUND && !strncmp(exr_document_text(d,NULL)+result.offset,"Following",9));
  exr_document_free(d); exr_publication_free(p);
  p=open_book(dir,"toc-unicodecase.epub");
  OK(exr_publication_resolve_href(p,"OPS/Nav/nav.xhtml","../Text/%C3%A9tage.xhtml#%C3%A9tage",fragment,&target,&error));
  CHECK(target.part==0); at(p,&target,"Accent"); exr_publication_free(p);
  p=open_book(dir,"navigation-repeated.epub");
  OK(exr_publication_resolve_href(p,"OPS/Nav/nav.xhtml","../Text/a.xhtml#start",fragment,&target,&error));
  CHECK(target.part==SIZE_MAX);
  OK(exr_publication_locate(p,&target,&result,&error)); CHECK(result.state==EXR_LINK_PART_MISSING);
  exr_publication_free(p);
  CHECK(exr_publication_locate(NULL,&target,&result,&error)==EXR_ARGUMENT);
}
int main(int argc,char **argv) {
  CHECK(argc==3);
  if (!strcmp(argv[2],"nav")) navigation(argv[1],0);
  else if (!strcmp(argv[2],"ncx")) navigation(argv[1],1);
  else if (!strcmp(argv[2],"recovery")) recovery(argv[1]);
  else if (!strcmp(argv[2],"fragment")) fragments(argv[1]);
  else CHECK(0);
  printf("TOC %s: %u checks passed\n",argv[2],checks); return 0;
}
