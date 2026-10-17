/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error;
static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) {fprintf(stderr,"line %d: %s (%d: %s)\n", \
 __LINE__,#x,(int)error.code,error.message);exit(1);} } while(0)
#define OK(x) CHECK((x)==EXR_OK)
typedef struct {
  int cancel; exr_stage stop; uint64_t after;
  size_t polls, progress, cancel_after, rejected;
  exr_pager *pager;
} job;
static int cancelled(void *context) {
  job *j=context; j->polls++;
  if(j->cancel_after && j->polls>=j->cancel_after) j->cancel=1;
  return j->cancel;
}
static void progress(void *context,exr_stage stage,uint64_t done,uint64_t total) {
  job *j=context; j->progress++;
  CHECK(stage>=EXR_STAGE_READ && stage<=EXR_STAGE_RENDER);
  CHECK(!total || done<=total);
  if(j->stop==stage && done>=j->after) j->cancel=1;
  if(j->pager) {
    exr_error local;
    CHECK(exr_pager_set_control(j->pager,NULL,&local)==EXR_ARGUMENT);
    j->rejected++;
  }
}
static exr_control control(job *j) { return (exr_control){cancelled,progress,j}; }
static exr_document *document(void) {
  char text[32769]; size_t i; exr_document *doc=NULL;
  for(i=0;i<4096;i++) memcpy(text+i*8,"AV fi a ",8); text[32768]=0;
  OK(exr_document_open_memory(EXR_TXT,text,32768,&doc,&error)); return doc;
}
static exr_layout_config config(void) {
  exr_layout_config c=exr_layout_config_defaults();
  c.page=(exr_layout_options){120,96,8,20,1.2f,0}; return c;
}
static void layout_and_render(exr_document *doc,exr_font *font) {
  exr_layout_config c=config(); exr_layout *layout=(exr_layout *)(uintptr_t)1;
  exr_bitmap image={0},plain={0}; exr_control callbacks; job j={0};
  j.stop=EXR_STAGE_STYLE; c.control=control(&j);
  CHECK(exr_layout_create_ex(doc,font,&c,&layout,&error)==EXR_CANCELLED && !layout);
  CHECK(error.code==EXR_CANCELLED && j.progress>0);
  c=config(); OK(exr_layout_create_ex(doc,font,&c,&layout,&error));
  memset(&j,0,sizeof(j)); j.stop=EXR_STAGE_RENDER; j.after=1; callbacks=control(&j);
  CHECK(exr_render_page_ex(layout,NULL,0,4,&callbacks,&image,&error)==EXR_CANCELLED);
  CHECK(!image.pixels && !image.width && !image.height && j.progress>1);
  memset(&j,0,sizeof(j)); callbacks=control(&j);
  OK(exr_render_page_ex(layout,NULL,0,4,&callbacks,&image,&error));
  OK(exr_render_page_color(layout,NULL,0,&plain,&error));
  CHECK(image.stride==plain.stride && image.height==plain.height);
  CHECK(!memcmp(image.pixels,plain.pixels,(size_t)image.stride*image.height));
  exr_bitmap_free(&image); exr_bitmap_free(&plain); exr_layout_free(layout);
}
static void pager(exr_document *doc,exr_font *font) {
  exr_layout_config c=config(); exr_pager *p=NULL,*baseline=NULL;
  const exr_layout *cached=NULL,*page=NULL,*expected=NULL; exr_layout *owned=NULL;
  exr_control callbacks; exr_bitmap a={0},b={0}; job j={0};
  OK(exr_pager_create(doc,font,&c,&p,&error));
  OK(exr_pager_set_checkpoints(p,16,4*1024*1024,4,&error));
  OK(exr_pager_get(p,0,&cached,&error));
  j.stop=EXR_STAGE_LAYOUT; j.after=512; j.pager=p; callbacks=control(&j);
  OK(exr_pager_set_control(p,&callbacks,&error));
  CHECK(exr_pager_get(p,40,&page,&error)==EXR_CANCELLED && !page);
  CHECK(j.cancel && j.rejected>0 && exr_pager_cached_count(p)==1);
  OK(exr_pager_get(p,0,&page,&error)); CHECK(page==cached);
  j.cancel=0; j.pager=NULL; OK(exr_pager_set_control(p,NULL,&error));
  OK(exr_pager_get(p,20,&page,&error)); CHECK(exr_pager_statistics(p).restored_checkpoints>0);
  OK(exr_pager_create(doc,font,&c,&baseline,&error)); OK(exr_pager_get(baseline,20,&expected,&error));
  OK(exr_render_page(page,NULL,0,&a,&error)); OK(exr_render_page(expected,NULL,0,&b,&error));
  CHECK(a.stride==b.stride && a.height==b.height && !memcmp(a.pixels,b.pixels,(size_t)a.stride*a.height));
  exr_bitmap_free(&a); exr_bitmap_free(&b); exr_pager_free(p); exr_pager_free(baseline);
  memset(&j,0,sizeof(j)); c.control=control(&j); OK(exr_pager_create(doc,font,&c,&p,&error));
  j.cancel=1; CHECK(exr_pager_next(p,&owned,&error)==EXR_CANCELLED && !owned);
  exr_pager_free(p); CHECK(exr_pager_set_control(NULL,NULL,&error)==EXR_ARGUMENT);
}
static void shaping(exr_font *font) {
  char *text=malloc(1+8191*2+1); size_t i,count=99; exr_shaped_glyph *out=(void *)(uintptr_t)1;
  exr_shape_options options=exr_shape_defaults(); job j={0};
  CHECK(text); text[0]='a';
  for(i=0;i<8191;i++) memcpy(text+1+i*2,"\xcc\x81",2); text[16383]=0;
  j.cancel_after=100; options.control=control(&j);
  CHECK(exr_shape(font,0,text,16383,&options,&out,&count,&error)==EXR_CANCELLED);
  CHECK(!out && !count && j.polls>=100);
  memset(&options.control,0,sizeof(options.control));
  OK(exr_shape(font,0,text,16383,&options,&out,&count,&error)); CHECK(count==8192);
  exr_free(out); free(text);
}
typedef struct { void *data; size_t size,releases,reads; } bytes;
static size_t read_at(void *context,uint64_t at,void *out,size_t size) {
  bytes *b=context; CHECK(at<=b->size && size<=b->size-(size_t)at);
  memcpy(out,(unsigned char *)b->data+(size_t)at,size); b->reads++; return size;
}
static void release(void *context) { ((bytes *)context)->releases++; }
static void source(const char *directory) {
  char path[4096]; FILE *file; long size; bytes b={0}; job j={0};
  exr_source input={0}; exr_publication *p=NULL; exr_document *doc=NULL;
  CHECK(snprintf(path,sizeof(path),"%s/font-book.epub",directory)>0);
  file=fopen(path,"rb"); CHECK(file && !fseek(file,0,SEEK_END)); size=ftell(file); CHECK(size>0);
  b.size=(size_t)size; b.data=malloc(b.size); CHECK(b.data && !fseek(file,0,SEEK_SET));
  CHECK(fread(b.data,1,b.size,file)==b.size && !fclose(file));
  input.size=b.size; input.read_at=read_at; input.release=release; input.context=&b;
  j.stop=EXR_STAGE_READ; j.after=1; input.control=control(&j);
  CHECK(exr_publication_open_source(&input,&p,&error)==EXR_CANCELLED && !p);
  CHECK(b.reads>0 && !b.releases);
  memset(&j,0,sizeof(j)); input.control=control(&j); OK(exr_publication_open_source(&input,&p,&error));
  j.cancel=1; CHECK(exr_publication_load(p,0,&doc,&error)==EXR_CANCELLED && !doc);
  j.cancel=0; OK(exr_publication_load(p,0,&doc,&error)); exr_document_free(doc);
  exr_publication_free(p); CHECK(b.releases==1); free(b.data);
}
int main(int argc,char **argv) {
  char path[4096]; exr_font *font=NULL; exr_document *doc;
  CHECK(argc==2); CHECK(snprintf(path,sizeof(path),"%s/shaping/shaping.ttf",argv[1])>0);
  OK(exr_font_open(path,&font,&error)); doc=document();
  layout_and_render(doc,font); pager(doc,font); shaping(font); source(argv[1]);
  exr_document_free(doc); exr_font_free(font);
  printf("Operation control: %u checks passed\n",checks); return 0;
}
