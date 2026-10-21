/* SPDX-License-Identifier: MIT */
#include "style_internal.h"
#include <miniz.h>
#include <stdio.h>

static exr_error error;
static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"style budget line %d: %s (%d)\n",__LINE__,#x,error.code);exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
#define BUDGET ((size_t)32*1024*1024)
static exr_document *document(const char *xml) {
  exr_document *d=NULL;
  OK(exr_xml_memory_tree(xml,strlen(xml),"html",&d,&error));d->format=EXR_EPUB;
  OK(exr_model_finish(d,&error));return d;
}
static void compare(const exr_document *d,const exr_layout_config *config) {
  exr_style *a=NULL,*b=NULL;
  exr_font_rule *af=NULL,*bf=NULL;
  size_t an=0,bn=0,i,retained;
  exr_style_memory memory;
  OK(exr_compute_styles(d,config,&a,&af,&an,&error));
  OK(exr_compute_styles_bounded(d,config,BUDGET,&b,&bf,&bn,&memory,&error));
  CHECK(an==bn && (!an || !memcmp(af,bf,an*sizeof(*af))));
  retained=d->node_count*sizeof(*b)+memory.retained_fonts_bytes;
  for(i=0;i<d->node_count;i++) {
    exr_style x=a[i],y=b[i];
    CHECK((!x.family && !y.family) || (x.family && y.family && !strcmp(x.family,y.family)));
    x.family=y.family=NULL;CHECK(!memcmp(&x,&y,sizeof(x)));
    if(b[i].family_owned) retained+=strlen(b[i].family)+1;
  }
  CHECK(memory.retained_bytes==retained && memory.peak_bytes>=retained && memory.peak_bytes<=BUDGET);
  if(bn) CHECK(memory.retained_fonts_bytes==64*sizeof(*bf));
  exr_styles_free(a,d->node_count);free(af);exr_styles_free(b,d->node_count);free(bf);
  a=NULL;af=NULL;an=0;
  {
    size_t peak=memory.peak_bytes;
    CHECK(exr_compute_styles_bounded(d,config,peak-1,&a,&af,&an,&memory,&error)==EXR_LIMIT);
    CHECK(a==NULL && af==NULL && an==0 && memory.retained_bytes==0 && memory.peak_bytes<peak);
    OK(exr_compute_styles_bounded(d,config,peak,&a,&af,&an,&memory,&error));
    CHECK(memory.peak_bytes==peak);
    exr_styles_free(a,d->node_count);free(af);
  }
}
static void add_css_resource(exr_document *d,const void *bytes,size_t size,int archive) {
  exr_resource *resources=realloc(d->resources,2*sizeof(*resources));
  CHECK(resources!=NULL);d->resources=resources;
  resources[1]=(exr_resource){exr_copy("css",3),exr_copy("book.css",8),exr_copy("text/css",8),exr_copy("",0)};
  CHECK(resources[1].id && resources[1].path && resources[1].media_type && resources[1].properties);
  d->resource_count=d->resource_capacity=2;
  if(!archive) {
    d->resource_data=calloc(2,sizeof(*d->resource_data));CHECK(d->resource_data!=NULL);
    d->resource_data[1].bytes=malloc(size ? size : 1);CHECK(d->resource_data[1].bytes!=NULL);
    memcpy(d->resource_data[1].bytes,bytes,size);d->resource_data[1].size=size;
  } else {
    mz_zip_archive zip={0};void *data=NULL;size_t length=0;
    CHECK(mz_zip_writer_init_heap(&zip,0,0));
    CHECK(mz_zip_writer_add_mem(&zip,"book.css",bytes,size,MZ_DEFAULT_COMPRESSION));
    CHECK(mz_zip_writer_finalize_heap_archive(&zip,&data,&length));CHECK(mz_zip_writer_end(&zip));
    d->archive=malloc(length);CHECK(d->archive!=NULL);memcpy(d->archive,data,length);d->archive_size=length;mz_free(data);
  }
}
static int cancelled(void *context) { (void)context;return 1; }
static void external(void) {
  const char *xml="<html><head><link rel='stylesheet' href='book.css'/></head><body><p class='x'>test</p></body></html>";
  const char *css="p{color:#123456}.x{font-family:Example;font-size:19px}";
  int archive;
  exr_layout_config config=exr_layout_config_defaults();
  for(archive=0;archive<2;archive++) {
    exr_document *d=document(xml);
    exr_style *styles=NULL;exr_font_rule *fonts=NULL;size_t count=0;
    exr_style_memory memory;
    add_css_resource(d,css,strlen(css),archive);compare(d,&config);
    config.control.cancelled=cancelled;
    CHECK(exr_compute_styles_bounded(d,&config,BUDGET,&styles,&fonts,&count,&memory,&error)==EXR_CANCELLED);
    CHECK(!styles && !fonts && !count);config.control.cancelled=NULL;
    exr_document_free(d);
  }
  {
    unsigned char utf16[]={0xff,0xfe,'p',0,'{',0,'c',0,'o',0,'l',0,'o',0,'r',0,':',0,'r',0,'e',0,'d',0,'}',0};
    exr_document *d=document(xml);add_css_resource(d,utf16,sizeof(utf16),1);compare(d,&config);exr_document_free(d);
  }
  {
    size_t size=2*1024*1024;
    char *css_large=malloc(size);
    exr_document *d=document(xml);exr_style *styles=NULL;exr_font_rule *fonts=NULL;size_t count=0;
    exr_style_memory memory;
    CHECK(css_large!=NULL);memset(css_large,' ',size);memcpy(css_large,"p{color:red}",12);
    add_css_resource(d,css_large,size,1);free(css_large);
    CHECK(exr_compute_styles_bounded(d,&config,256*1024,&styles,&fonts,&count,&memory,&error)==EXR_LIMIT);
    CHECK(!styles && !fonts && !count && memory.retained_bytes==0 && memory.peak_bytes<=256*1024);
    exr_document_free(d);
  }
}
int main(void) {
  exr_layout_config config=exr_layout_config_defaults();
  exr_document *d=document("<html><head><style>@font-face{font-family:Example;src:url(font.ttf)}p{color:red;font-family:Example}body > p.x{font-size:21px}</style></head><body><p class='x' style='margin:2px;border:1px solid blue'>text <em>more</em></p><table><tr><td>cell</td></tr></table></body></html>");
  compare(d,&config);exr_document_free(d);external();
  printf("%u bounded style checks passed\n",checks);return 0;
}
