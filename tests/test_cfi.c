/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <miniz.h>
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
static void full_point(exr_document *d,size_t chapter,exr_cfi_point point) {
  char *a=NULL,*b=NULL; exr_cfi_point result; size_t mapped;
  OK(exr_document_cfi_create(d,chapter,&point,NULL,&a,&error));
  OK(exr_document_cfi_resolve(d,a,NULL,&mapped,&result,&error)); CHECK(mapped==chapter && point.side==result.side);
  OK(exr_document_cfi_create(d,mapped,&result,NULL,&b,&error)); CHECK(!strcmp(a,b)); exr_free(a); exr_free(b);
}
static void full_fixtures(const char *dir) {
  const char *files[]={"layout.epub","font-book.epub","navigation-epub2.epub","navigation-epub3.epub","navigation-repeated.epub"}; size_t i,j,k,count,n;
  for(i=0;i<5;i++) {
    char path[4096]; exr_document *d=NULL; const exr_node *nodes; const exr_chapter *chapters;
    snprintf(path,sizeof(path),"%s/%s",dir,files[i]); OK(exr_document_open(path,&d,&error)); nodes=exr_document_nodes(d,&n); chapters=exr_document_chapters(d,&count);
    for(j=0;j<count;j++) if(chapters[j].in_spine) {
      for(k=0;k<n;k++) if(nodes[k].chapter==j && nodes[k].kind==EXR_NODE_TEXT && nodes[nodes[k].parent].kind!=EXR_NODE_CHAPTER) break;
      CHECK(k<n); full_point(d,j,(exr_cfi_point){k,0,2});
    }
    exr_document_free(d);
  }
}
static void full_custom(void) {
  const char *container="<container><rootfiles><rootfile full-path='OPS/book.opf'/></rootfiles></container>";
  const char *opf="<package xmlns='http://www.idpf.org/2007/opf'><metadata/><extra/><manifest><item id='a' href='a.xhtml' media-type='application/xhtml+xml'/><item id='aux' href='aux.xhtml' media-type='application/xhtml+xml'/></manifest><more/><spine id='sp'><extension/><itemref id='s1' idref='a'/><itemref id='s2' idref='a' linear='no'/></spine></package>";
  const char *html="<html xmlns='http://www.w3.org/1999/xhtml'><head/><body id='b'><p id='p'>A😀B</p></body></html>";
  mz_zip_archive zip={0}; void *archive=NULL; size_t size=0,i,count,mapped; exr_document *d=NULL; const exr_node *nodes; exr_cfi_point point,out; char *cfi=NULL; exr_control control={0};
  const char *bad[]={"epubcfi(/10[sp]/4[s1]!/4[b]/2[p]/1:99)","epubcfi(/10/4[missing]!/4)","epubcfi(/10[sp]/4[s1; s=b]!/4)","epubcfi(/10[sp]/4[s1][;s=b]!/4)","epubcfi(/10/4[;s=b]!/4)","epubcfi(/6/2!/4)","epubcfi(/10/4!/4!/2)","epubcfi(/10/4!/4,/2,/4)","epubcfi(/10/4/1!/4)","epubcfi(/10/4/0!/4)","epubcfi(/10/4)","#epubcfi(/10/4!/4)"};
  CHECK(mz_zip_writer_init_heap(&zip,0,0)); CHECK(mz_zip_writer_add_mem(&zip,"META-INF/container.xml",container,strlen(container),0)); CHECK(mz_zip_writer_add_mem(&zip,"OPS/book.opf",opf,strlen(opf),0)); CHECK(mz_zip_writer_add_mem(&zip,"OPS/a.xhtml",html,strlen(html),0)); CHECK(mz_zip_writer_add_mem(&zip,"OPS/aux.xhtml",html,strlen(html),0)); CHECK(mz_zip_writer_finalize_heap_archive(&zip,&archive,&size)); mz_zip_writer_end(&zip);
  OK(exr_document_open_memory(EXR_EPUB,archive,size,&d,&error));
  { exr_publication *publication=NULL; exr_document *part=NULL; size_t nc;
    OK(exr_publication_open_memory(EXR_EPUB,archive,size,&publication,&error)); OK(exr_publication_load(publication,1,&part,&error)); nodes=exr_document_nodes(part,&nc);
    for(i=0;i<nc;i++) if(nodes[i].kind==EXR_NODE_TEXT) break; CHECK(i<nc); point=(exr_cfi_point){i,0,0};
    CHECK(exr_document_cfi_create(part,0,&point,NULL,&cfi,&error)==EXR_FORMAT && !cfi);
    { exr_document *resolved=NULL; exr_cfi_point found; size_t target; char *again=NULL;
      OK(exr_publication_cfi_create(publication,1,part,&point,NULL,&cfi,&error)); CHECK(strstr(cfi,"/6[s2]!"));
      OK(exr_publication_cfi_resolve(publication,cfi,NULL,&target,&resolved,&found,&error)); CHECK(target==1 && found.offset==0 && resolved);
      OK(exr_publication_cfi_create(publication,target,resolved,&found,NULL,&again,&error)); CHECK(!strcmp(again,cfi)); exr_free(again); exr_free(cfi); cfi=NULL;
      exr_publication_free(publication); publication=NULL; same(resolved,0,found); exr_document_free(resolved);
    }
    exr_document_free(part);
  }
  mz_free(archive); nodes=exr_document_nodes(d,&count);
  for(i=0;i<count;i++) if(nodes[i].chapter==0 && nodes[i].kind==EXR_NODE_TEXT) break; CHECK(i<count); point=(exr_cfi_point){i,2,0};
  OK(exr_document_cfi_create(d,0,&point,NULL,&cfi,&error)); CHECK(!strcmp(cfi,"epubcfi(/10[sp]/4[s1]!/4[b]/2[p]/1:2)")); exr_free(cfi);
  OK(exr_document_cfi_resolve(d,"epubcfi(/6[sp]/2[s2]!/4[b]/2[p]/1:2)",NULL,&mapped,&out,&error)); CHECK(mapped==1 && nodes[out.node].chapter==1 && out.offset==2);
  for(i=0;i<sizeof(bad)/sizeof(*bad);i++) CHECK(exr_document_cfi_resolve(d,bad[i],NULL,&mapped,&out,&error)==EXR_FORMAT && mapped==SIZE_MAX && out.node==SIZE_MAX);
  for(i=0;i<count;i++) if(nodes[i].chapter==2 && nodes[i].kind==EXR_NODE_TEXT) break; CHECK(i<count); point=(exr_cfi_point){i,0,0};
  CHECK(exr_document_cfi_create(d,2,&point,NULL,&cfi,&error)==EXR_FORMAT && !cfi);
  control.cancelled=cancel; CHECK(exr_document_cfi_resolve(d,"epubcfi(/10/4!/4)",&control,&mapped,&out,&error)==EXR_CANCELLED && mapped==SIZE_MAX && out.node==SIZE_MAX);
  CHECK(exr_document_cfi_create(d,0,&point,&control,&cfi,&error)==EXR_CANCELLED && !cfi);
  exr_document_free(d);
}
typedef struct { exr_publication *publication; int attempted; exr_status nested; } reentry;
static void reenter(void *context,exr_stage stage,uint64_t done,uint64_t total) {
  reentry *r=context; exr_document *d=NULL; exr_cfi_point point; size_t part; exr_error local;
  (void)stage; (void)done; (void)total;
  if(!r->attempted) { r->attempted=1; r->nested=exr_publication_cfi_resolve(r->publication,"epubcfi(/6/2!/4)",NULL,&part,&d,&point,&local); }
}
static exr_status never_load(void *context,size_t part,exr_document **out,exr_error *e) { (void)context; (void)part; (void)e; *out=NULL; return EXR_IO; }
static void lazy_cfi(void) {
  const char *container="<container><rootfiles><rootfile full-path='book.opf'/></rootfiles></container>";
  const char *opf="<package><metadata/><manifest><item id='a' href='a.xhtml' media-type='application/xhtml+xml'/><item id='b' href='b.xhtml' media-type='application/xhtml+xml'/></manifest><spine><itemref idref='a'/><itemref idref='b'/></spine></package>";
  const char *html="<html><head/><body><p>Readable</p></body></html>"; const char *names[]={"META-INF/container.xml","book.opf","a.xhtml","b.xhtml"}; const char *values[]={container,opf,html,"<html"};
  mz_zip_archive zip={0}; void *bytes=NULL; size_t n,i,count,part; exr_publication *p=NULL,*other=NULL; exr_document *a=NULL,*foreign=NULL,*out=NULL; const exr_node *nodes; exr_cfi_point point,result; exr_control control={0}; reentry attempt={0}; char *cfi=NULL;
  CHECK(mz_zip_writer_init_heap(&zip,0,0)); for(i=0;i<4;i++) CHECK(mz_zip_writer_add_mem(&zip,names[i],values[i],strlen(values[i]),0)); CHECK(mz_zip_writer_finalize_heap_archive(&zip,&bytes,&n)); mz_zip_writer_end(&zip);
  CHECK(exr_document_open_memory(EXR_EPUB,bytes,n,&out,&error)==EXR_FORMAT && !out);
  OK(exr_publication_open_memory(EXR_EPUB,bytes,n,&p,&error)); OK(exr_publication_load(p,0,&a,&error)); nodes=exr_document_nodes(a,&count); for(i=0;i<count;i++) if(nodes[i].kind==EXR_NODE_TEXT) break; CHECK(i<count); point=(exr_cfi_point){i,3,2};
  OK(exr_publication_cfi_create(p,0,a,&point,NULL,&cfi,&error));
  attempt.publication=p; control.progress=reenter; control.context=&attempt;
  OK(exr_publication_cfi_resolve(p,cfi,&control,&part,&out,&result,&error)); CHECK(attempt.attempted && attempt.nested==EXR_ARGUMENT && part==0 && result.offset==3 && result.side==2); exr_document_free(out);
  CHECK(exr_publication_cfi_resolve(p,"epubcfi(/6/4!/4)",NULL,&part,&out,&result,&error)==EXR_FORMAT && !out && part==SIZE_MAX && result.node==SIZE_MAX);
  OK(exr_publication_open_memory(EXR_EPUB,bytes,n,&other,&error)); mz_free(bytes); OK(exr_publication_load(other,0,&foreign,&error));
  { char *invalid=NULL; CHECK(exr_publication_cfi_create(p,0,foreign,&point,NULL,&invalid,&error)==EXR_ARGUMENT && !invalid); }
  control=(exr_control){cancel,NULL,NULL}; CHECK(exr_publication_cfi_resolve(p,cfi,&control,&part,&out,&result,&error)==EXR_CANCELLED && !out && part==SIZE_MAX && result.node==SIZE_MAX);
  exr_free(cfi); exr_document_free(a); exr_document_free(foreign); exr_publication_free(p); exr_publication_free(other);
  { exr_part part_input={"custom","custom.xhtml","Custom",1}; exr_publication_input input={0}; input.parts=&part_input; input.part_count=1; input.load=never_load;
    OK(exr_publication_create(&input,&p,&error)); CHECK(exr_publication_cfi_resolve(p,"epubcfi(/6/2!/4)",NULL,&part,&out,&result,&error)==EXR_FORMAT && !out && part==SIZE_MAX && result.node==SIZE_MAX); exr_publication_free(p);
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
  exr_document_free(d); fixtures(argv[1]); full_fixtures(argv[1]); full_custom(); lazy_cfi(); printf("%u chapter CFI checks passed\n",checks); return 0;
}
