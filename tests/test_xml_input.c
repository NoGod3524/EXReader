/* SPDX-License-Identifier: MIT */
#include "../src/document_internal.h"
#include "exreader.h"
#include <miniz.h>
#include <stdio.h>

static exr_error error;
static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message);exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static void append(exr_buffer *b,const char *s) { CHECK(exr_append(b,s,strlen(s))); }
typedef struct { size_t offsets[32],nodes[32],count;int cancel; } trace;
static exr_status position(void *context,size_t offset,size_t node) {
  trace *t=context;
  CHECK(t->count<32);
  t->offsets[t->count]=offset;t->nodes[t->count++]=node;
  return t->cancel && t->count==2 ? EXR_CANCELLED : EXR_OK;
}
static exr_document *empty(void) {
  exr_document *d=calloc(1,sizeof(*d));CHECK(d);
  d->format=EXR_EPUB;d->resource_count=d->resource_capacity=1;
  d->resources=calloc(1,sizeof(*d->resources));CHECK(d->resources);
  d->resources[0]=(exr_resource){exr_copy("main",4),exr_copy("OPS/main.xhtml",14),
    exr_copy("application/xhtml+xml",21),exr_copy("",0)};
  CHECK(d->resources[0].id && d->resources[0].path && d->resources[0].media_type && d->resources[0].properties);
  return d;
}
static void equal(const exr_document *a,const exr_document *b) {
  size_t i,j;
  CHECK(a->node_count==b->node_count && a->count==b->count && a->size==b->size);
  CHECK(!memcmp(a->text,b->text,a->size));
  for(i=0;i<a->count;i++) CHECK(a->blocks[i].start==b->blocks[i].start &&
    a->blocks[i].end==b->blocks[i].end && a->blocks[i].heading==b->blocks[i].heading);
  for(i=0;i<a->node_count;i++) {
    const exr_node *x=&a->nodes[i],*y=&b->nodes[i];
    CHECK(x->kind==y->kind && x->parent==y->parent && x->first_child==y->first_child &&
      x->next_sibling==y->next_sibling && x->chapter==y->chapter && x->start==y->start && x->end==y->end);
    CHECK((!x->name && !y->name) || (x->name && y->name && !strcmp(x->name,y->name)));
    CHECK((!x->text && !y->text) || (x->text && y->text && !strcmp(x->text,y->text)));
    CHECK(x->attribute_count==y->attribute_count);
    for(j=0;j<x->attribute_count;j++) CHECK(!strcmp(x->attributes[j].name,y->attributes[j].name) &&
      !strcmp(x->attributes[j].value,y->attributes[j].value));
    if(x->kind==EXR_NODE_TEXT) {
      char *path=NULL,*other=NULL;exr_cfi_point p={i,0,0},copy;
      OK(exr_document_cfi_path_create(a,0,&p,NULL,&path,&error));
      OK(exr_document_cfi_path_create(b,0,&p,NULL,&other,&error));CHECK(!strcmp(path,other));
      OK(exr_document_cfi_path_resolve(b,0,path,NULL,&copy,&error));CHECK(copy.node==i && !copy.offset);
      exr_free(path);exr_free(other);
    }
  }
}
static void chunks(const char *xml,size_t size,const size_t *steps,size_t count) {
  exr_document *whole=empty();trace baseline={0};size_t i,j;
  OK(exr_xhtml_positions(whole,xml,size,0,position,&baseline,&error));
  OK(exr_model_finish(whole,&error));CHECK(baseline.count>=4);
  for(i=0;i<baseline.count;i++) CHECK(baseline.offsets[i]<size && xml[baseline.offsets[i]]=='<');
  for(i=0;i<count;i++) {
    exr_document *d=empty();exr_xml_tree_parser *p=NULL;trace t={0};
    OK(exr_xml_tree_begin(d,0,1,1,"html",position,&t,&p,&error));
    for(j=0;j<size;) {
      size_t n=size-j<steps[i] ? size-j : steps[i];OK(exr_xml_tree_feed(p,xml+j,n,0));j+=n;
    }
    OK(exr_xml_tree_feed(p,NULL,0,1));
    CHECK(exr_xml_tree_feed(p,NULL,0,1)==EXR_ARGUMENT);
    exr_xml_tree_free(p);OK(exr_model_finish(d,&error));equal(whole,d);
    CHECK(t.count==baseline.count && !memcmp(t.offsets,baseline.offsets,t.count*sizeof(size_t)) &&
      !memcmp(t.nodes,baseline.nodes,t.count*sizeof(size_t)));
    exr_document_free(d);
  }
  exr_document_free(whole);
}
static void failures(void) {
  const char *invalid[]={"<wrong/>","<html><body>","<!DOCTYPE html [<!ENTITY local 'x'>]><html><body>&local;</body></html>"};
  size_t i;
  for(i=0;i<sizeof(invalid)/sizeof(*invalid);i++) {
    exr_document *d=empty();exr_xml_tree_parser *p=NULL;size_t at=0;exr_status status=EXR_OK;
    OK(exr_xml_tree_begin(d,0,1,1,"html",NULL,NULL,&p,&error));
    while(invalid[i][at] && status==EXR_OK) { status=exr_xml_tree_feed(p,invalid[i]+at,1,0);at++; }
    if(status==EXR_OK) status=exr_xml_tree_feed(p,NULL,0,1);
    CHECK(status==EXR_FORMAT);CHECK(exr_xml_tree_feed(p,NULL,0,1)==status);
    exr_xml_tree_free(p);exr_document_free(d);
  }
  { exr_document *d=empty();exr_xml_tree_parser *p=NULL;
    OK(exr_xml_tree_begin(d,0,1,1,"html",NULL,NULL,&p,&error));
    CHECK(exr_xml_tree_feed(p,"x",(size_t)128*1024*1024+1,0)==EXR_LIMIT);
    exr_xml_tree_free(p);exr_document_free(d);
  }
  { const char xml[]="<html><body><p>A</p></body></html>";exr_document *d=empty();exr_xml_tree_parser *p=NULL;trace t={0};
    t.cancel=1;OK(exr_xml_tree_begin(d,0,1,1,"html",position,&t,&p,&error));
    CHECK(exr_xml_tree_feed(p,xml,sizeof(xml)-1,1)==EXR_CANCELLED && error.code==EXR_CANCELLED);
    exr_xml_tree_free(p);exr_document_free(d);
  }
  exr_xml_tree_free(NULL);
}
static void *book(const char *xml,size_t size,int level,size_t *bytes) {
  const char container[]="<container><rootfiles><rootfile full-path=\"OPS/package.opf\"/></rootfiles></container>";
  const char package[]="<package><metadata><title>Input chunks</title></metadata><manifest><item id=\"main\" href=\"main.xhtml\" media-type=\"application/xhtml+xml\"/></manifest><spine><itemref idref=\"main\"/></spine></package>";
  mz_zip_archive z={0};void *out=NULL;
  CHECK(mz_zip_writer_init_heap(&z,0,0));
  CHECK(mz_zip_writer_add_mem(&z,"mimetype","application/epub+zip",20,0));
  CHECK(mz_zip_writer_add_mem(&z,"META-INF/container.xml",container,sizeof(container)-1,0));
  CHECK(mz_zip_writer_add_mem(&z,"OPS/package.opf",package,sizeof(package)-1,0));
  CHECK(mz_zip_writer_add_mem(&z,"OPS/main.xhtml",xml,size,(mz_uint)level));
  CHECK(mz_zip_writer_finalize_heap_archive(&z,&out,bytes));CHECK(mz_zip_writer_end(&z));return out;
}
typedef struct { const unsigned char *bytes;size_t size,expected;int stop; } source;
static size_t read_at(void *context,uint64_t at,void *buffer,size_t n) {
  source *s=context;CHECK(at<=s->size && n<=s->size-(size_t)at);
  memcpy(buffer,s->bytes+(size_t)at,n);return n;
}
static int cancelled(void *context) { return ((source *)context)->stop; }
static void progress(void *context,exr_stage stage,uint64_t completed,uint64_t total) {
  source *s=context;
  if(stage==EXR_STAGE_READ && total==s->expected && completed>=32768) s->stop=1;
}
static void archive_input(const char *xml,size_t size) {
  int level;exr_document *expected=empty();
  OK(exr_xhtml(expected,xml,size,0,1,1,&error));OK(exr_model_finish(expected,&error));
  for(level=0;level<=6;level+=6) {
    size_t bytes;unsigned char *data=book(xml,size,level,&bytes);exr_document *d=NULL;
    exr_publication *p=NULL;source input={data,bytes,size,0};
    exr_source src={bytes,read_at,NULL,&input,{0}};
    OK(exr_document_open_memory(EXR_EPUB,data,bytes,&d,&error));equal(expected,d);exr_document_free(d);
    OK(exr_publication_open_source(&src,&p,&error));OK(exr_publication_load(p,0,&d,&error));
    equal(expected,d);exr_document_free(d);exr_publication_free(p);p=NULL;
    src.control=(exr_control){cancelled,progress,&input};
    OK(exr_publication_open_source(&src,&p,&error));
    CHECK(exr_publication_load(p,0,&d,&error)==EXR_CANCELLED && !d && input.stop);
    exr_publication_free(p);p=NULL;input.stop=0;memset(&src.control,0,sizeof(src.control));
    /* Alter only the retained chapter CRC; both complete and lazy loads must reject it. */
    { size_t at;int changed=0;
      for(at=0;at+46+14<=bytes;at++) if(!memcmp(data+at,"PK\1\2",4) &&
          data[at+28]==14 && !data[at+29] && !memcmp(data+at+46,"OPS/main.xhtml",14)) {
        data[at+16]^=1;changed=1;break;
      }
      CHECK(changed);
    }
    CHECK(exr_document_open_memory(EXR_EPUB,data,bytes,&d,&error)==EXR_FORMAT && !d);
    OK(exr_publication_open_source(&src,&p,&error));
    CHECK(exr_publication_load(p,0,&d,&error)==EXR_FORMAT && !d);
    exr_publication_free(p);mz_free(data);
  }
  exr_document_free(expected);
}
int main(void) {
  const char small[]="<html xmlns=\"http://www.w3.org/1999/xhtml\"><head><title>Title</title></head><body><p id=\"one\">A &amp; B \xc3\xa9 \xf0\x9f\x98\x80<![CDATA[ <raw> ]]><span xml:lang=\"en\">end</span></p></body></html>";
  const size_t tiny[]={1,2,7,31,32768},large[]={17,4093,32767,32768,32769,65536};
  exr_buffer xml={0};size_t i;
  chunks(small,sizeof(small)-1,tiny,sizeof(tiny)/sizeof(*tiny));failures();
  append(&xml,"<html xmlns=\"http://www.w3.org/1999/xhtml\"><head/><body data-note=\"");
  for(i=0;i<70000;i++) CHECK(exr_append(&xml,"x",1));
  append(&xml,"\"><p id=\"long\">");
  for(i=0;i<8192;i++) append(&xml,"Words &amp; \xc3\xa9. ");
  append(&xml,"</p></body></html>");
  chunks(xml.data,xml.size,large,sizeof(large)/sizeof(*large));archive_input(xml.data,xml.size);
  free(xml.data);printf("%u XML input checks passed\n",checks);return 0;
}
