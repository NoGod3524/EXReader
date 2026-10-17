/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static void same(exr_document *d,size_t chapter,exr_cfi_point point) {
  char *a=NULL,*b=NULL; exr_cfi_point copy;
  OK(exr_document_cfi_path_create(d,chapter,&point,NULL,&a,&error)); CHECK(a);
  OK(exr_document_cfi_path_resolve(d,chapter,a,NULL,&copy,&error)); CHECK(copy.side==point.side);
  OK(exr_document_cfi_path_create(d,chapter,&copy,NULL,&b,&error)); CHECK(!strcmp(a,b)); exr_free(a); exr_free(b);
}
static void resolve(exr_document *d,const char *path,size_t node,size_t offset,unsigned side) {
  exr_cfi_point p; OK(exr_document_cfi_path_resolve(d,0,path,NULL,&p,&error)); CHECK(p.node==node && p.offset==offset && p.side==side);
}
static exr_document *custom(int duplicate) {
  exr_attribute attrs[]={{"id","body[,;]()^"}},para[]={{"http://www.w3.org/XML/1998/namespace|id","p"}};
  exr_node_input nodes[]={
    {EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0}, /*0*/
    {EXR_NODE_CHAPTER,0,NULL,NULL,NULL,0},
    {EXR_NODE_ELEMENT,1,"html",NULL,NULL,0},
    {EXR_NODE_TEXT,2,NULL,"\n",NULL,0},
    {EXR_NODE_ELEMENT,2,"head",NULL,NULL,0},
    {EXR_NODE_TEXT,2,NULL,"\n",NULL,0},
    {EXR_NODE_ELEMENT,2,"body",NULL,attrs,1}, /*6*/
    {EXR_NODE_PARAGRAPH,6,"p",NULL,para,1},
    {EXR_NODE_TEXT,7,NULL,"A😀",NULL,0},
    {EXR_NODE_TEXT,7,NULL,"B",NULL,0},
    {EXR_NODE_ELEMENT,7,"em",NULL,NULL,0}, /*10*/
    {EXR_NODE_TEXT,10,NULL,"xy",NULL,0},
    {EXR_NODE_TEXT,7,NULL," ",NULL,0},
    {EXR_NODE_IMAGE,7,"img",NULL,NULL,0},
    {EXR_NODE_PARAGRAPH,6,"p",NULL,NULL,0}};
  exr_chapter_input chapter={"main","main.xhtml",1,1}; exr_document_input input={"CFI",nodes,15,&chapter,1,NULL,0}; exr_document *d=NULL;
  if(duplicate) { nodes[14].attributes=para; nodes[14].attribute_count=1; }
  OK(exr_document_create(&input,&d,&error)); return d;
}
static int cancel(void *c) { (void)c; return 1; }
static void fixtures(const char *dir) {
  const char *files[]={"layout.epub","font-book.epub","navigation-epub2.epub"}; size_t i,j,count;
  for(i=0;i<3;i++) {
    char path[4096]; exr_document *d=NULL; const exr_node *nodes;
    snprintf(path,sizeof(path),"%s/%s",dir,files[i]); OK(exr_document_open(path,&d,&error)); nodes=exr_document_nodes(d,&count);
    for(j=0;j<count;j++) if(nodes[j].kind==EXR_NODE_TEXT && nodes[j].parent!=SIZE_MAX && nodes[nodes[j].parent].kind!=EXR_NODE_CHAPTER) {
      const unsigned char *p=(const unsigned char *)nodes[j].text; size_t length=0,k;
      for(k=0;p[k];k++) if((p[k]&0xc0)!=0x80) length+=p[k]>=0xf0 ? 2 : 1;
      same(d,nodes[j].chapter,(exr_cfi_point){j,0,0}); same(d,nodes[j].chapter,(exr_cfi_point){j,length,2});
    }
    exr_document_free(d);
  }
}
int main(int argc,char **argv) {
  exr_document *d=custom(0); exr_cfi_point point={8,2,0},out; char *path=NULL; size_t i; exr_control control={0};
  const char *bad[]={"/04","/4/2/1:01","/4/2/1:184467440737095516160","/4/2/1:5","/4/2/1:0[wrong]","/4/2/1:0[;s=x]","/4/2/1:0[;s=b]/2","/4/2/2:0","/4/2/2!","/4/2/99","/4/2/100","/4/2/0/2","/4/2[missing]","/4[]","/4[^q]","/4[unterminated","epubcfi(/4)","/4/2,/2,/4"};
  CHECK(argc==2);
  OK(exr_document_cfi_path_create(d,0,&point,NULL,&path,&error)); CHECK(!strcmp(path,"/4[body^[^,^;^]^(^)^^]/2[p]/1:2")); exr_free(path);
  for(i=0;i<=3;i++) same(d,0,(exr_cfi_point){8,i,0}); /* Includes surrogate interior. */
  same(d,0,(exr_cfi_point){9,0,1}); same(d,0,(exr_cfi_point){9,1,2}); same(d,0,(exr_cfi_point){13,SIZE_MAX,1}); same(d,0,(exr_cfi_point){2,SIZE_MAX,0});
  for(i=0;i<=5;i++) same(d,0,(exr_cfi_point){7,i,0});
  resolve(d,"/4/2/1:3",8,3,0); resolve(d,"/4/2/1:4",9,1,0); resolve(d,"/4/2/2/1",11,0,0);
  resolve(d,"/4/2/0",7,0,0); resolve(d,"/4/2/6",7,5,0); resolve(d,"/4/2/5:0",7,5,0);
  resolve(d,"/4/4/1:0",14,0,0); resolve(d,"/4/4[p]/1:1",8,1,0); /* ID relocates a stale path. */
  resolve(d,"/4/2/2[;s=a]",10,SIZE_MAX,2); resolve(d,"/4/2/1:1[;s=b]",8,1,1);
  for(i=0;i<sizeof(bad)/sizeof(*bad);i++) CHECK(exr_document_cfi_path_resolve(d,0,bad[i],NULL,&out,&error)==EXR_FORMAT && out.node==SIZE_MAX && out.offset==SIZE_MAX && !out.side);
  point.offset=4; CHECK(exr_document_cfi_path_create(d,0,&point,NULL,&path,&error)==EXR_ARGUMENT && !path);
  point=(exr_cfi_point){7,7,0}; CHECK(exr_document_cfi_path_create(d,0,&point,NULL,&path,&error)==EXR_ARGUMENT && !path);
  control.cancelled=cancel; point=(exr_cfi_point){8,0,0}; CHECK(exr_document_cfi_path_create(d,0,&point,&control,&path,&error)==EXR_CANCELLED && !path);
  CHECK(exr_document_cfi_path_resolve(d,0,"/4",&control,&out,&error)==EXR_CANCELLED && out.node==SIZE_MAX);
  CHECK(exr_document_cfi_path_resolve(d,0,"/4[\xff]",NULL,&out,&error)==EXR_ENCODING && out.node==SIZE_MAX);
  exr_document_free(d); d=custom(1);
  CHECK(exr_document_cfi_path_resolve(d,0,"/4/6[p]",NULL,&out,&error)==EXR_FORMAT && out.node==SIZE_MAX);
  resolve(d,"/4/2[p]",7,SIZE_MAX,0);
  { char *large=malloc(65538); CHECK(large); memset(large,'/',65537); large[65537]=0; CHECK(exr_document_cfi_path_resolve(d,0,large,NULL,&out,&error)==EXR_LIMIT && out.node==SIZE_MAX); free(large); }
  CHECK(exr_document_cfi_path_resolve(d,1,"/4",NULL,&out,&error)==EXR_ARGUMENT && out.node==SIZE_MAX);
  CHECK(exr_document_cfi_path_create(d,0,NULL,NULL,&path,&error)==EXR_ARGUMENT && !path);
  exr_document_free(d); fixtures(argv[1]); printf("%u chapter CFI checks passed\n",checks); return 0;
}
