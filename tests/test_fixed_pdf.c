/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#define NEAR(a,b) CHECK(fabs((a)-(b))<1e-8)
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static unsigned char *load(const char *dir,const char *name,size_t *size) {
  char path[4096]; FILE *f; long n; unsigned char *bytes;
  snprintf(path,sizeof(path),"%s/%s",dir,name); f=fopen(path,"rb"); CHECK(f && !fseek(f,0,SEEK_END)); n=ftell(f); CHECK(n>0); rewind(f);
  *size=(size_t)n; bytes=malloc(*size); CHECK(bytes && fread(bytes,1,*size,f)==*size); fclose(f); return bytes;
}
static void pixel(const exr_bitmap *b,unsigned x,unsigned y,unsigned r,unsigned g,unsigned blue) {
  const unsigned char *p=b->pixels+(size_t)y*b->stride+x*4; CHECK(b->channels==4 && p[0]==r && p[1]==g && p[2]==blue && p[3]==255);
}
typedef struct { exr_fixed_document *document; size_t paths,images; int stop; } inspection;
static exr_status inspect_path(void *context,const exr_path_segment *segments,size_t count,const double matrix[6],const exr_draw_style *style,exr_error *e) {
  inspection *i=context; size_t pages; (void)e;
  CHECK(count>=4 && segments[0].points[0].x==500 && matrix && matrix[0]==.01 && style->flags==EXR_DRAW_FILL);
  CHECK(exr_fixed_pages(i->document,&pages) && pages==5); i->paths++; return i->stop ? EXR_CANCELLED : EXR_OK;
}
static exr_status inspect_image(void *context,const exr_image_layer *image,const double matrix[6],double alpha,exr_error *e) {
  inspection *i=context; (void)e; CHECK(image->bitmap.width==2 && image->mask && image->mask->bitmap.width==1 && image->mask->bitmap.pixels[0]==128 && matrix && alpha==1); i->images++; return EXR_OK;
}
static int cancel(void *context) { return *(int *)context; }
static void cancel_progress(void *context,exr_stage stage,uint64_t completed,uint64_t total) { (void)stage; (void)total; if(completed) *(int *)context=1; }
static void public_pages(const char *dir) {
  unsigned char *bytes; size_t size,count; exr_fixed_document *d=NULL; exr_bitmap b; exr_draw_sink sink={0}; inspection inspect={0}; const exr_fixed_page *pages;
  bytes=load(dir,"pdf-public.pdf",&size); OK(exr_fixed_open_memory(EXR_PDF,bytes,size,NULL,&d,&error)); memset(bytes,0,size); free(bytes);
  pages=exr_fixed_pages(d,&count); CHECK(count==5 && !strcmp(pages[0].id,"page-1") && pages[1].geometry.bounds[3]==16);
  OK(exr_fixed_render(d,0,1,NULL,&b,&error)); CHECK(b.width==12 && b.height==12); pixel(&b,6,10,0,0,0); pixel(&b,1,10,255,255,255); exr_bitmap_free(&b);
  CHECK(exr_fixed_render(d,1,1,NULL,&b,&error)==EXR_FORMAT && !b.pixels); /* Missing host font. */
  OK(exr_fixed_render(d,0,1,NULL,&b,&error)); pixel(&b,6,10,0,0,0); exr_bitmap_free(&b);
  CHECK(exr_fixed_render(d,2,1,NULL,&b,&error)==EXR_FORMAT && !b.pixels); /* Unsupported lazy image codec. */
  OK(exr_fixed_render(d,0,1,NULL,&b,&error)); pixel(&b,6,10,0,0,0); exr_bitmap_free(&b);
  OK(exr_fixed_render(d,4,1,NULL,&b,&error)); pixel(&b,0,5,255,127,127); pixel(&b,0,10,127,127,255); exr_bitmap_free(&b);
  inspect.document=d; sink.path=inspect_path; sink.context=&inspect;
  OK(exr_fixed_draw(d,0,NULL,&sink,NULL,&error)); CHECK(inspect.paths==1);
  OK(exr_fixed_draw(d,2,NULL,&sink,NULL,&error)); CHECK(inspect.paths==1); /* Image ignored without decoding. */
  sink.image=inspect_image; OK(exr_fixed_draw(d,4,NULL,&sink,NULL,&error)); CHECK(inspect.images==1);
  inspect.stop=1; CHECK(exr_fixed_draw(d,0,NULL,&sink,NULL,&error)==EXR_CANCELLED && error.code==EXR_CANCELLED);
  OK(exr_fixed_render(d,0,1,NULL,&b,&error)); exr_bitmap_free(&b); exr_fixed_free(d);
}
static void fallback_and_options(const char *dir) {
  unsigned char *bytes,*font_bytes; size_t size,font_size; exr_font *font=NULL; exr_font_input source={0}; exr_fixed_open_options options={0}; exr_fixed_document *d=NULL; exr_bitmap b; int stopped=0;
  font_bytes=load(dir,"fonts/collection.ttc",&font_size); source.data=font_bytes; source.size=font_size; source.face_index=1; OK(exr_font_create_glyphs(&source,1,&font,&error)); free(font_bytes);
  options.struct_size=sizeof(options); options.fallback_font=font;
  CHECK(exr_fixed_open_memory(EXR_PDF,"not a PDF",9,&options,&d,&error)==EXR_FORMAT && !d && exr_font_count(font)==1);
  bytes=load(dir,"pdf-public.pdf",&size); options.control.cancelled=cancel; options.control.context=&stopped; options.control.progress=cancel_progress;
  CHECK(exr_fixed_open_memory(EXR_PDF,bytes,size,&options,&d,&error)==EXR_CANCELLED && !d && exr_font_count(font)==1);
  memset(&options.control,0,sizeof(options.control)); OK(exr_fixed_open_memory(EXR_PDF,bytes,size,&options,&d,&error)); free(bytes); exr_font_free(font);
  OK(exr_fixed_render(d,1,1,NULL,&b,&error)); CHECK(b.width==12 && b.height==16); pixel(&b,7,5,0,0,0); exr_bitmap_free(&b); /* TTC face 1, not face 0. */
  CHECK(exr_fixed_render(d,3,1,NULL,&b,&error)==EXR_FORMAT && !b.pixels); /* Bad embedded program must not use the fallback. */
  OK(exr_fixed_render(d,1,1,NULL,&b,&error)); pixel(&b,7,5,0,0,0); exr_bitmap_free(&b); exr_fixed_free(d);
  memset(&options,0,sizeof(options)); CHECK(exr_fixed_open_memory(EXR_PDF,"x",1,&options,&d,&error)==EXR_ARGUMENT && !d);
  { struct { exr_fixed_open_options options; unsigned char tail[8]; } extended={0}; extended.options.struct_size=sizeof(extended); extended.tail[0]=1;
    bytes=load(dir,"pdf-public.pdf",&size); CHECK(exr_fixed_open_memory(EXR_PDF,bytes,size,&extended.options,&d,&error)==EXR_ARGUMENT && !d);
    extended.tail[0]=0; OK(exr_fixed_open_memory(EXR_PDF,bytes,size,&extended.options,&d,&error)); free(bytes); exr_fixed_free(d);
  }
}
static void semantic_text(const char *dir) {
  exr_fixed_document *d=NULL; exr_fixed_text *t=NULL; const exr_text_region *r; size_t size,count; unsigned char *bytes;
  exr_control control={0}; int stopped=1; const char *utf8;
  bytes=load(dir,"pdf-public-text.pdf",&size); OK(exr_fixed_open_memory(EXR_PDF,bytes,size,NULL,&d,&error)); free(bytes);
  control.cancelled=cancel; control.context=&stopped;
  CHECK(exr_fixed_load_text(d,0,&control,&t,&error)==EXR_CANCELLED && !t);
  CHECK(exr_fixed_load_text(d,1,NULL,&t,&error)==EXR_FORMAT && !t); /* Partial content must not escape. */
  CHECK(exr_fixed_load_text(d,2,NULL,&t,&error)==EXR_FORMAT && !t); /* Invalid font geometry. */
  OK(exr_fixed_load_text(d,3,NULL,&t,&error)); CHECK(exr_fixed_text_string(t,&size) && !size); CHECK(!exr_fixed_text_regions(t,&count) && !count); exr_fixed_text_free(t); t=NULL;
  OK(exr_fixed_load_text(d,0,NULL,&t,&error)); exr_fixed_free(d);
  utf8=exr_fixed_text_string(t,&size); r=exr_fixed_text_regions(t,&count);
  CHECK(size==14 && !memcmp(utf8,"Afi\xe4\xb8\x80\0AAA\xf0\x9f\x98\x80",14) && count==8);
  CHECK(r[0].start==0 && r[0].end==1 && r[1].start==1 && r[1].end==3 && r[3].start==6 && r[3].end==7);
  NEAR(r[0].quad[0],210); NEAR(r[0].quad[1],626.6); NEAR(r[0].quad[2],215); NEAR(r[0].quad[5],653.6);
  CHECK(!r[0].flags && r[4].flags==EXR_REGION_INVISIBLE && r[6].flags==EXR_REGION_VERTICAL && r[7].flags==EXR_REGION_VERTICAL);
  NEAR(r[5].quad[0],15); NEAR(r[5].quad[1],21.6); NEAR(r[5].quad[5],48.6); /* Nested Form transforms. */
  NEAR(r[6].quad[0],94.9); NEAR(r[6].quad[1],200); NEAR(r[6].quad[3],179.98); NEAR(r[6].quad[4],105.1);
  { size_t start,end,hit,selected_count; exr_text_region *selected=NULL;
    OK(exr_fixed_text_find(t,"fi",2,0,NULL,&start,&end,&error)); CHECK(start==1 && end==3);
    OK(exr_fixed_text_select(t,start,end,NULL,&selected,&selected_count,&error)); CHECK(selected_count==1 && selected[0].start==1 && selected[0].end==3); exr_free(selected);
    OK(exr_fixed_text_hit(t,211,630,0,EXR_REGION_INVISIBLE,NULL,&hit,&error)); CHECK(hit==0);
    { exr_fixed_anchor anchor={0}; exr_anchor_match match;
      OK(exr_fixed_anchor_create("page-1",t,start,end,&anchor,&error));
      OK(exr_fixed_anchor_resolve("page-1",t,&anchor,NULL,&match,&error)); CHECK(match.state==EXR_ANCHOR_FOUND && match.start==1 && match.end==3); exr_fixed_anchor_free(&anchor);
    }
  }
  exr_fixed_text_free(t);
  /* Semantic extraction works without host or even usable embedded outlines. */
  bytes=load(dir,"pdf-public.pdf",&size); OK(exr_fixed_open_memory(EXR_PDF,bytes,size,NULL,&d,&error)); free(bytes);
  OK(exr_fixed_load_text(d,1,NULL,&t,&error)); CHECK(exr_fixed_text_string(t,&size) && size==1); exr_fixed_text_free(t);
  OK(exr_fixed_load_text(d,3,NULL,&t,&error)); CHECK(exr_fixed_text_string(t,&size) && size==1); exr_fixed_text_free(t);
  OK(exr_fixed_load_text(d,2,NULL,&t,&error)); CHECK(exr_fixed_text_string(t,&size) && !size); exr_fixed_text_free(t); exr_fixed_free(d);
}
int main(int argc,char **argv) {
  char path[4096]; exr_fixed_document *d=NULL; exr_bitmap b;
  CHECK(argc==2); semantic_text(argv[1]); public_pages(argv[1]); fallback_and_options(argv[1]);
  snprintf(path,sizeof(path),"%s/pdf-public.pdf",argv[1]); OK(exr_fixed_open(path,NULL,&d,&error)); CHECK(!strcmp(exr_fixed_title(d),"pdf-public.pdf")); OK(exr_fixed_render(d,0,1,NULL,&b,&error)); exr_bitmap_free(&b); exr_fixed_free(d);
  CHECK(exr_fixed_open_memory(EXR_EPUB,"x",1,NULL,&d,&error)==EXR_FORMAT && !d);
  CHECK(exr_fixed_open_memory(EXR_PDF,NULL,1,NULL,&d,&error)==EXR_ARGUMENT && !d);
  CHECK(exr_fixed_open_memory(EXR_PDF,"x",(size_t)128*1024*1024+1,NULL,&d,&error)==EXR_LIMIT && !d);
  printf("%u public fixed PDF checks passed\n",checks); return 0;
}
