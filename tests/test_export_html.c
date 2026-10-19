/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <miniz.h>
#include <expat.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static void valid(const void *data,size_t size) {
  XML_Parser p=XML_ParserCreateNS(NULL,'|'); CHECK(p); CHECK(XML_Parse(p,data,(int)size,XML_TRUE)==XML_STATUS_OK); XML_ParserFree(p);
}
static void compare(const char *dir,const char *name) {
  char path[4096],*entry=NULL; exr_document *d=NULL; void *html=NULL,*epub=NULL,*data,*other; size_t hn,en,n,m,i; mz_zip_archive h={0},e={0};
  const exr_chapter *chapters; const exr_resource *resources; size_t count;
  snprintf(path,sizeof(path),"%s/%s",dir,name); OK(exr_document_open(path,&d,&error));
  OK(exr_document_export_html_bundle(d,NULL,&html,&hn,&entry,&error)); CHECK(html && hn && entry);
  OK(exr_document_export_epub(d,NULL,&epub,&en,&error)); CHECK(mz_zip_reader_init_mem(&h,html,hn,0)); CHECK(mz_zip_reader_init_mem(&e,epub,en,0));
  CHECK(mz_zip_reader_locate_file(&h,"mimetype",NULL,0)<0 && mz_zip_reader_locate_file(&h,"META-INF/container.xml",NULL,0)<0);
  data=mz_zip_reader_extract_file_to_heap(&h,entry,&n,0); CHECK(data); valid(data,n); mz_free(data);
  chapters=exr_document_chapters(d,&count); for(i=0;i<count;i++) {
    data=mz_zip_reader_extract_file_to_heap(&h,chapters[i].path,&n,0); other=mz_zip_reader_extract_file_to_heap(&e,chapters[i].path,&m,0);
    CHECK(data && other && n==m && !memcmp(data,other,n)); valid(data,n); mz_free(data); mz_free(other);
  }
  resources=exr_document_resources(d,&count); for(i=0;i<count;i++) {
    data=mz_zip_reader_extract_file_to_heap(&h,resources[i].path,&n,0); other=mz_zip_reader_extract_file_to_heap(&e,resources[i].path,&m,0);
    CHECK(data && other && n==m && !memcmp(data,other,n)); mz_free(other);
    if(strcmp(resources[i].media_type,"application/xhtml+xml")) { OK(exr_document_resource(d,i,&other,&m,&error)); CHECK(m==n && !memcmp(data,other,n)); exr_free(other); }
    mz_free(data);
  }
  mz_zip_reader_end(&h); mz_zip_reader_end(&e); exr_free(html); exr_free(epub); exr_free(entry); exr_document_free(d);
}
static int cancel(void *context) { (void)context; return 1; }
static void progress_cancel(void *context,exr_stage stage,uint64_t done,uint64_t total) { (void)stage; if(total && done==total) *(int *)context=1; }
static int flag(void *context) { return *(int *)context; }
static void custom(void) {
  exr_node_input nodes[]={{EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0},{EXR_NODE_CHAPTER,0,NULL,NULL,NULL,0},{EXR_NODE_PARAGRAPH,1,NULL,NULL,NULL,0},{EXR_NODE_TEXT,2,NULL,"Text & <书>",NULL,0}};
  exr_chapter_input chapter={"Main","exreader-index-0.xhtml",1,1};
  exr_document_input input={"Title & <书>",nodes,4,&chapter,1,NULL,0}; exr_document *d=NULL; exr_control control={0};
  void *data=NULL,*body; size_t size,n; char *entry=NULL; mz_zip_archive zip={0}; int stop=0;
  OK(exr_document_create(&input,&d,&error)); OK(exr_document_export_html_bundle(d,NULL,&data,&size,&entry,&error)); CHECK(!strcmp(entry,"exreader-index-1.xhtml"));
  CHECK(mz_zip_reader_init_mem(&zip,data,size,0)); body=mz_zip_reader_extract_file_to_heap(&zip,entry,&n,0); CHECK(body); valid(body,n);
  { char *text=malloc(n+1); CHECK(text); memcpy(text,body,n); text[n]=0; CHECK(strstr(text,"Title &amp; &lt;书&gt;") && strstr(text,"href=\"exreader-index-0.xhtml\"")); free(text); }
  mz_free(body); mz_zip_reader_end(&zip); exr_free(data); exr_free(entry);
  control.cancelled=cancel; data=(void *)(uintptr_t)1; entry=(char *)(uintptr_t)1; size=5;
  CHECK(exr_document_export_html_bundle(d,&control,&data,&size,&entry,&error)==EXR_CANCELLED && !data && !size && !entry);
  control.cancelled=flag; control.progress=progress_cancel; control.context=&stop;
  CHECK(exr_document_export_html_bundle(d,&control,&data,&size,&entry,&error)==EXR_CANCELLED && !data && !size && !entry);
  CHECK(exr_document_export_html_bundle(d,NULL,&data,&size,NULL,&error)==EXR_ARGUMENT && !data && !size);
  exr_document_free(d); OK(exr_document_open_memory(EXR_TXT,"Text",4,&d,&error)); OK(exr_document_export_html_bundle(d,NULL,&data,&size,&entry,&error)); exr_free(data); exr_free(entry); exr_document_free(d);
  nodes[2].name="bad:name"; OK(exr_document_create(&input,&d,&error)); CHECK(exr_document_export_html_bundle(d,NULL,&data,&size,&entry,&error)==EXR_FORMAT && !data && !size && !entry); exr_document_free(d); nodes[2].name=NULL;
  { exr_resource_input resource={{"image","missing.png","image/png",""},NULL,0}; input.resources=&resource; input.resource_count=1;
    OK(exr_document_create(&input,&d,&error)); CHECK(exr_document_export_html_bundle(d,NULL,&data,&size,&entry,&error)!=EXR_OK && !data && !size && !entry); exr_document_free(d);
  }
}
int main(int argc,char **argv) {
  CHECK(argc==2); compare(argv[1],"layout.epub"); compare(argv[1],"font-book.epub"); compare(argv[1],"navigation-epub2.epub"); compare(argv[1],"navigation-epub3.epub"); compare(argv[1],"navigation-repeated.epub"); custom();
  printf("%u structured HTML checks passed\n",checks); return 0;
}
