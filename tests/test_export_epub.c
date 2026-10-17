/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <miniz.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error;
static unsigned checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static exr_document *load(const char *dir,const char *name) {
  char path[4096]; exr_document *d=NULL;
  snprintf(path,sizeof(path),"%s/%s",dir,name); OK(exr_document_open(path,&d,&error)); return d;
}
static void roundtrip(const char *dir,const char *name,int paint) {
  exr_document *a=load(dir,name), *b=NULL;
  const exr_resource *ra,*rb; const exr_chapter *ca,*cb;
  void *zip=NULL; size_t n,na,nb,i,j,sa,sb; const char *ta,*tb;
  OK(exr_document_export_epub(a,NULL,&zip,&n,&error)); CHECK(zip && n>20);
  OK(exr_document_open_memory(EXR_EPUB,zip,n,&b,&error));
  ta=exr_document_text(a,&sa); tb=exr_document_text(b,&sb); CHECK(sa==sb && !memcmp(ta,tb,sa));
  ca=exr_document_chapters(a,&na); cb=exr_document_chapters(b,&nb); CHECK(nb>=na);
  for(i=0;i<na;i++) if(ca[i].in_spine) {
    CHECK(i<nb && !strcmp(ca[i].path,cb[i].path));
    CHECK(ca[i].linear==cb[i].linear && cb[i].in_spine);
  }
  ra=exr_document_resources(a,&na); rb=exr_document_resources(b,&nb);
  for(i=0;i<na;i++) {
    for(j=0;j<nb;j++) if(!strcmp(ra[i].path,rb[j].path)) break;
    CHECK(j<nb && !strcmp(ra[i].media_type,rb[j].media_type));
    CHECK(!strcmp(ra[i].properties,rb[j].properties));
    if(strcmp(ra[i].media_type,"application/xhtml+xml")) {
      void *ba=NULL,*bb=NULL;
      OK(exr_document_resource(a,i,&ba,&sa,&error)); OK(exr_document_resource(b,j,&bb,&sb,&error));
      CHECK(sa==sb && !memcmp(ba,bb,sa)); exr_free(ba); exr_free(bb);
    }
  }
  if(paint) {
    exr_font *f=NULL; exr_layout *la=NULL,*lb=NULL; exr_bitmap pa={0},pb={0};
    exr_layout_config config=exr_layout_config_defaults(); char path[4096];
    config.page=(exr_layout_options){240,160,12,18,1.3f,0};
    snprintf(path,sizeof(path),"%s/fonts/primary.ttf",dir); OK(exr_font_open(path,&f,&error));
    OK(exr_layout_create_ex(a,f,&config,&la,&error)); OK(exr_layout_create_ex(b,f,&config,&lb,&error));
    exr_layout_pages(la,&na); exr_layout_pages(lb,&nb); CHECK(na==nb);
    for(i=0;i<na;i++) {
      OK(exr_render_page(la,NULL,i,&pa,&error)); OK(exr_render_page(lb,NULL,i,&pb,&error));
      CHECK(pa.width==pb.width && pa.height==pb.height && pa.stride==pb.stride);
      CHECK(!memcmp(pa.pixels,pb.pixels,(size_t)pa.stride*pa.height));
      exr_bitmap_free(&pa); exr_bitmap_free(&pb);
    }
    exr_layout_free(la); exr_layout_free(lb); exr_font_free(f);
  }
  {
    exr_publication *original=NULL,*copy=NULL; const exr_navigation *va,*vb;
    char path[4096]; size_t ac,bc;
    snprintf(path,sizeof(path),"%s/%s",dir,name); OK(exr_publication_open(path,&original,&error));
    OK(exr_publication_open_memory(EXR_EPUB,zip,n,&copy,&error));
    OK(exr_publication_navigation(original,&va,&ac,&error));
    OK(exr_publication_navigation(copy,&vb,&bc,&error));
    if(ac) {
      CHECK(ac==bc);
      /* NCX synthesis groups independent navigation categories by role. */
      for(i=0;i<ac;i++) {
        for(j=0;j<bc;j++) if(!strcmp(va[i].label,vb[j].label) && !strcmp(va[i].role,vb[j].role)) break;
        CHECK(j<bc && va[i].part==vb[j].part);
        CHECK((va[i].parent==SIZE_MAX)==(vb[j].parent==SIZE_MAX));
        if(va[i].parent!=SIZE_MAX) CHECK(!strcmp(va[va[i].parent].label,vb[vb[j].parent].label));
      }
    }
    exr_publication_free(original); exr_publication_free(copy);
  }
  exr_free(zip); exr_document_free(a); exr_document_free(b);
}
static int cancel(void *ctx) { (void)ctx; return 1; }
static void custom(void) {
  const exr_attribute attrs[]={{"id","a\t\n\r&\""},{"urn:test|值","数据"},{"http://www.w3.org/XML/1998/namespace|lang","zh"}};
  exr_node_input nodes[]={
    {EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0},
    {EXR_NODE_CHAPTER,0,NULL,NULL,NULL,0},
    {EXR_NODE_ELEMENT,1,"http://www.w3.org/1999/xhtml|html",NULL,NULL,0},
    {EXR_NODE_ELEMENT,2,"http://www.w3.org/1999/xhtml|body",NULL,NULL,0},
    {EXR_NODE_PARAGRAPH,3,"http://www.w3.org/1999/xhtml|p",NULL,attrs,3},
    {EXR_NODE_TEXT,4,NULL,"A\rB\nC\t<&",NULL,0}};
  exr_chapter_input chapter={"main","目录/a#%? &.xhtml",1,1};
  exr_document_input input={"Title & 文",nodes,6,&chapter,1,NULL,0};
  exr_document *d=NULL,*copy=NULL; void *bytes=NULL; size_t size=0,i,count;
  const exr_node *v; exr_control control={0};
  OK(exr_document_create(&input,&d,&error));
  OK(exr_document_export_epub(d,NULL,&bytes,&size,&error));
  OK(exr_document_open_memory(EXR_EPUB,bytes,size,&copy,&error));
  v=exr_document_nodes(copy,&count);
  for(i=0;i<count;i++) if(v[i].kind==EXR_NODE_PARAGRAPH) break;
  CHECK(i<count); CHECK(!strcmp(exr_node_attribute(&v[i],"id"),attrs[0].value));
  CHECK(!strcmp(exr_node_attribute(&v[i],"urn:test|值"),attrs[1].value));
  CHECK(!strcmp(exr_node_attribute(&v[i],attrs[2].name),attrs[2].value));
  CHECK(v[i].first_child!=SIZE_MAX && !strcmp(v[v[i].first_child].text,nodes[5].text));
  exr_free(bytes); exr_document_free(copy);
  control.cancelled=cancel;
  bytes=(void *)(uintptr_t)1; size=123;
  CHECK(exr_document_export_epub(d,&control,&bytes,&size,&error)==EXR_CANCELLED);
  CHECK(!bytes && !size); exr_document_free(d);
  nodes[4].name="bad:name";
  OK(exr_document_create(&input,&d,&error));
  CHECK(exr_document_export_epub(d,NULL,&bytes,&size,&error)==EXR_FORMAT); CHECK(!bytes && !size);
  exr_document_free(d); nodes[4].name="http://www.w3.org/1999/xhtml|p";
  {
    exr_resource_input resource={{"missing","missing.png","image/png",""},NULL,0};
    input.resources=&resource; input.resource_count=1;
    OK(exr_document_create(&input,&d,&error));
    CHECK(exr_document_export_epub(d,NULL,&bytes,&size,&error)!=EXR_OK); CHECK(!bytes && !size);
    exr_document_free(d);
    resource.info.path=chapter.path; resource.data="x"; resource.size=1;
    OK(exr_document_create(&input,&d,&error));
    CHECK(exr_document_export_epub(d,NULL,&bytes,&size,&error)==EXR_FORMAT); CHECK(!bytes && !size);
    exr_document_free(d); input.resources=NULL; input.resource_count=0;
  }
  chapter.path="mimetype"; OK(exr_document_create(&input,&d,&error));
  CHECK(exr_document_export_epub(d,NULL,&bytes,&size,&error)==EXR_FORMAT); CHECK(!bytes && !size);
  exr_document_free(d);
}
static void plain_and_encrypted(void) {
  exr_document *d=NULL,*copy=NULL; void *bytes=NULL,*modified=NULL; size_t size,n=0,i;
  mz_zip_archive reader={0},writer={0};
  const char *text="Heading\n\nBody & text.";
  OK(exr_document_open_memory(EXR_TXT,text,strlen(text),&d,&error));
  OK(exr_document_export_epub(d,NULL,&bytes,&size,&error));
  OK(exr_document_open_memory(EXR_EPUB,bytes,size,&copy,&error));
  CHECK(strstr(exr_document_text(copy,NULL),"Body & text.")); exr_document_free(copy);
  CHECK(mz_zip_reader_init_mem(&reader,bytes,size,0)); CHECK(mz_zip_writer_init_heap(&writer,0,0));
  for(i=0;i<mz_zip_reader_get_num_files(&reader);i++) {
    mz_zip_archive_file_stat info; void *data;
    CHECK(mz_zip_reader_file_stat(&reader,(mz_uint)i,&info));
    data=mz_zip_reader_extract_to_heap(&reader,(mz_uint)i,&n,0); CHECK(data);
    CHECK(mz_zip_writer_add_mem(&writer,info.m_filename,data,n,0)); mz_free(data);
  }
  CHECK(mz_zip_writer_add_mem(&writer,"META-INF/encryption.xml","<encryption/>",13,0));
  CHECK(mz_zip_writer_finalize_heap_archive(&writer,&modified,&n));
  mz_zip_reader_end(&reader); mz_zip_writer_end(&writer); exr_free(bytes); bytes=NULL;
  OK(exr_document_open_memory(EXR_EPUB,modified,n,&copy,&error));
  CHECK(exr_document_export_epub(copy,NULL,&bytes,&size,&error)==EXR_FORMAT); CHECK(!bytes && !size);
  { char *entry=NULL; CHECK(exr_document_export_html_bundle(copy,NULL,&bytes,&size,&entry,&error)==EXR_FORMAT); CHECK(!bytes && !size && !entry); }
  mz_free(modified); exr_document_free(copy); exr_document_free(d);
}
int main(int argc,char **argv) {
  CHECK(argc==2);
  roundtrip(argv[1],"layout.epub",1);
  roundtrip(argv[1],"font-book.epub",1);
  roundtrip(argv[1],"navigation-epub2.epub",0);
  roundtrip(argv[1],"navigation-epub3.epub",0);
  roundtrip(argv[1],"navigation-repeated.epub",0);
  custom(); plain_and_encrypted(); printf("%u structured EPUB checks passed\n",checks); return 0;
}
