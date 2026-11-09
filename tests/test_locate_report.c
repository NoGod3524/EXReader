/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%s)\n",__LINE__,#x,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static exr_publication *open_book(const char *dir) {
  char path[4096]; exr_publication *p=NULL;
  snprintf(path,sizeof(path),"%s/toc-missing-anchors.epub",dir);
  OK(exr_publication_open(path,&p,&error)); return p;
}
static void report(exr_publication *p,uint64_t total,uint64_t exact,uint64_t fallback,uint64_t part,uint64_t anchor) {
  exr_locate_report r=exr_publication_locate_report(p);
  CHECK(r.total_entries==total && r.resolved_exact==exact && r.resolved_part_start==fallback &&
    r.missing_part==part && r.missing_anchor==anchor);
}
static void entries(const char *dir) {
  exr_publication *p=open_book(dir); const exr_toc_entry *toc; size_t n,i,missing;
  exr_location loc; exr_target part={SIZE_MAX,NULL,SIZE_MAX};
  OK(exr_publication_toc(p,&toc,&n,&error)); CHECK(n==5); report(p,0,0,0,0,0);
  for(i=0;i<n;i++) {
    OK(exr_publication_locate(p,&toc[i].target,&loc,&error));
    CHECK(loc.part==0);
    CHECK(loc.state==(i<3 ? EXR_LINK_FOUND : EXR_LINK_ANCHOR_MISSING));
    if(i>=3) CHECK(loc.offset==0);
  }
  report(p,5,3,2,0,2);
  OK(exr_publication_locate(p,&toc[3].target,&loc,&error)); report(p,6,3,3,0,3);
  exr_publication_missing_targets(p,&missing); CHECK(missing==2);
  OK(exr_publication_locate(p,&part,&loc,&error));
  CHECK(loc.state==EXR_LINK_PART_MISSING && loc.part==SIZE_MAX && loc.offset==SIZE_MAX);
  report(p,7,3,3,1,3);
  part=(exr_target){0,NULL,SIZE_MAX};
  OK(exr_publication_locate(p,&part,&loc,&error)); CHECK(loc.offset==0); report(p,8,4,3,1,3);
  part.offset=0;
  OK(exr_publication_locate(p,&part,&loc,&error)); report(p,9,5,3,1,3);
  part.part=99; CHECK(exr_publication_locate(p,&part,&loc,&error)==EXR_ARGUMENT);
  CHECK(exr_publication_locate(p,NULL,&loc,&error)==EXR_ARGUMENT);
  CHECK(exr_publication_locate(p,&toc[0].target,NULL,&error)==EXR_ARGUMENT);
  report(p,12,5,3,1,3); exr_publication_free(p);
}
static void reset(const char *dir) {
  exr_publication *a=open_book(dir),*b=open_book(dir); exr_location loc; size_t missing,index;
  exr_target target={0,"absent",SIZE_MAX};
  report(NULL,0,0,0,0,0); exr_publication_locate_report_reset(NULL);
  OK(exr_publication_locate(a,&target,&loc,&error)); report(a,1,0,1,0,1); report(b,0,0,0,0,0);
  exr_publication_locate_report_reset(a); report(a,0,0,0,0,0);
  exr_publication_missing_targets(a,&missing); CHECK(missing==1);
  OK(exr_publication_locate(a,&target,&loc,&error)); CHECK(loc.offset==0); report(a,1,0,1,0,1);
  exr_publication_locate_report_reset(a);
  OK(exr_publication_target_at(a,0,0,&index,&error)); report(a,5,3,2,0,2);
  exr_publication_locate_report_reset(a);
  OK(exr_publication_target_at(a,0,0,&index,&error)); report(a,0,0,0,0,0);
  CHECK(exr_publication_locate(NULL,&target,&loc,&error)==EXR_ARGUMENT); report(b,0,0,0,0,0);
  exr_publication_free(a); exr_publication_free(b);
}
int main(int argc,char **argv) {
  CHECK(argc==3);
  if(!strcmp(argv[2],"entries")) entries(argv[1]);
  else if(!strcmp(argv[2],"reset")) reset(argv[1]); else CHECK(0);
  printf("locate report %s: %u checks passed\n",argv[2],checks); return 0;
}
