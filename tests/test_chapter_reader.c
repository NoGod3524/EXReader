/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <miniz.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks;
static exr_error error;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"chapter reader check %u at line %d: status %d %s\n",checks,__LINE__,error.code,error.message);exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static uint64_t fnv(uint64_t h, const void *data, size_t size) {
  const unsigned char *p = data;
  size_t i;
  for (i = 0; i < size; i++) {
    h ^= p[i];
    h *= 1099511628211ULL;
  }
  return h;
}
static uint64_t fnv_u64(uint64_t h, uint64_t value) { return fnv(h, &value, sizeof(value)); }
static uint64_t fnv_scale(uint64_t h, double value) {
  long long q = (long long)llround(value * 100.0);
  return fnv_u64(h, (uint64_t)q);
}

typedef struct {
  uint64_t hash;
  size_t lines, glyphs, boxes, start, end;
} page_sample;

static page_sample hash_layout(const exr_layout *layout) {
  page_sample s;
  const exr_page *pages;
  const exr_line *lines;
  const exr_glyph *glyphs;
  const exr_box *boxes;
  size_t count = 0, i;
  memset(&s, 0, sizeof(s));
  s.hash = 1469598103934665603ULL;
  pages = exr_layout_pages(layout, &count);
  if (!pages || !count) return s;
  s.start = pages[0].start;
  s.end = pages[0].end;
  for (i = 0; i < count; i++) {
    s.hash = fnv_u64(s.hash, pages[i].start);
    s.hash = fnv_u64(s.hash, pages[i].end);
    s.hash = fnv_u64(s.hash, pages[i].line_count);
    s.hash = fnv_u64(s.hash, pages[i].box_count);
  }
  lines = exr_layout_lines(layout, &s.lines);
  for (i = 0; i < s.lines; i++) {
    s.hash = fnv_u64(s.hash, lines[i].start);
    s.hash = fnv_u64(s.hash, lines[i].end);
    s.hash = fnv_u64(s.hash, lines[i].glyph_start);
    s.hash = fnv_u64(s.hash, lines[i].glyph_count);
    s.hash = fnv_scale(s.hash, lines[i].x);
    s.hash = fnv_scale(s.hash, lines[i].y);
    s.hash = fnv_scale(s.hash, lines[i].width);
    s.hash = fnv_scale(s.hash, lines[i].height);
  }
  glyphs = exr_layout_glyphs(layout, &s.glyphs);
  for (i = 0; i < s.glyphs; i++) {
    s.hash = fnv_u64(s.hash, glyphs[i].start);
    s.hash = fnv_u64(s.hash, glyphs[i].end);
    s.hash = fnv_u64(s.hash, glyphs[i].codepoint);
    s.hash = fnv_u64(s.hash, glyphs[i].glyph);
    s.hash = fnv_u64(s.hash, glyphs[i].node);
    s.hash = fnv_u64(s.hash, glyphs[i].font_index);
    s.hash = fnv_u64(s.hash, glyphs[i].color);
    s.hash = fnv_u64(s.hash, glyphs[i].flags);
    s.hash = fnv_u64(s.hash, glyphs[i].cluster_start);
    s.hash = fnv_u64(s.hash, glyphs[i].cluster_end);
    s.hash = fnv_u64(s.hash, glyphs[i].boundaries);
    s.hash = fnv_u64(s.hash, glyphs[i].bidi_level);
    s.hash = fnv_scale(s.hash, glyphs[i].x);
    s.hash = fnv_scale(s.hash, glyphs[i].baseline);
    s.hash = fnv_scale(s.hash, glyphs[i].advance);
    s.hash = fnv_scale(s.hash, glyphs[i].size);
  }
  boxes = exr_layout_boxes(layout, &s.boxes);
  for (i = 0; i < s.boxes; i++) {
    s.hash = fnv_u64(s.hash, (uint64_t)boxes[i].kind);
    s.hash = fnv_u64(s.hash, boxes[i].node);
    s.hash = fnv_u64(s.hash, boxes[i].page);
    s.hash = fnv_u64(s.hash, boxes[i].start);
    s.hash = fnv_u64(s.hash, boxes[i].end);
    s.hash = fnv_u64(s.hash, boxes[i].flags);
    s.hash = fnv_u64(s.hash, boxes[i].background);
    s.hash = fnv_u64(s.hash, boxes[i].border_color);
    s.hash = fnv_scale(s.hash, boxes[i].x);
    s.hash = fnv_scale(s.hash, boxes[i].y);
    s.hash = fnv_scale(s.hash, boxes[i].width);
    s.hash = fnv_scale(s.hash, boxes[i].height);
    s.hash = fnv_scale(s.hash, boxes[i].border_width);
  }
  return s;
}

/* Deterministic LCG: the fixed random plan is part of the evidence record. */

static void add(mz_zip_archive *zip,const char *name,const char *data) {
  CHECK(mz_zip_writer_add_mem(zip,name,data,strlen(data),MZ_DEFAULT_COMPRESSION));
}
typedef struct { void *bytes;size_t size,reads,released;int fail; } book_source;
static size_t book_read(void *context,uint64_t offset,void *data,size_t size) {
  book_source *source=context;source->reads++;
  if(source->fail || offset>source->size || size>source->size-offset) return 0;
  if(size>137) size=137;
  memcpy(data,(const char *)source->bytes+(size_t)offset,size);return size;
}
static void book_release(void *context) { book_source *source=context;source->released++;mz_free(source->bytes);source->bytes=NULL; }
static exr_publication *book(int vertical,book_source *source) {
  static const char *container="<container><rootfiles><rootfile full-path='OPS/book.opf'/></rootfiles></container>";
  static const char *package="<package><metadata/><manifest><item id='c' href='c.xhtml' media-type='application/xhtml+xml'/><item id='d' href='d.xhtml' media-type='application/xhtml+xml'/></manifest><spine><itemref idref='c'/><itemref idref='d'/></spine></package>";
  mz_zip_archive zip={0};
  char *xml=calloc(1,1024*1024);size_t at=0,i,size=0;
  void *data=NULL;exr_publication *publication=NULL;
  CHECK(xml!=NULL);
  at+=(size_t)sprintf(xml+at,"<html xmlns='http://www.w3.org/1999/xhtml' style='%s'><head><style>p{margin-bottom:3px}.float{float:left;width:68px}table{width:170px}td{padding:2px}section{color:#203040}</style></head><body><section lang='en' style='padding:2px'>",vertical ? "writing-mode:vertical-rl" : "");
  for(i=0;i<400;i++) {
    at+=(size_t)sprintf(xml+at,"<p id='p%zu'>Window %zu: Read the same document with <em>stable global coordinates</em>, words and spaces. The page continues across real paragraph boundaries. More text for wrapping.</p>",i,i);
    if(i==100) at+=(size_t)sprintf(xml+at,"<p>Unicode 😀 é 字 a^b,[x](y);&amp; text.</p>");
    if(i%17==3) at+=(size_t)sprintf(xml+at,"<div class='float'>%s<p>Small floated words wrap.</p></div>",i==3 ? "<style>.float p{font-size:13px}</style>" : "");
    if(i%17==8) at+=(size_t)sprintf(xml+at,"<table>%s<tr><td colspan='2'>first spanning cell</td></tr><tr><td>third row</td><td>fourth cell</td></tr></table>",i==8 ? "<style>td{color:#302010}</style>" : "");
    if(i%17==12) at+=(size_t)sprintf(xml+at,"<p dir='rtl'>مرحبا بالعالم <span dir='ltr'>abc 123</span> שלום <ruby>%s字<rt>zi</rt></ruby></p>",i==12 ? "<style>rt{color:#203040}</style>" : "");
    if(vertical && i%40==9) at+=(size_t)sprintf(xml+at,"<div style='writing-mode:horizontal-tb'><p>Local horizontal text inside a vertical viewport.</p></div>");
    if(i%20==19) at+=(size_t)sprintf(xml+at,"</section><section lang='en' style='padding:2px'>");
  }
  at+=(size_t)sprintf(xml+at,"</section><style>em{color:#704020}p{letter-spacing:0.1px}</style></body></html>");
  CHECK(at<1024*1024);
  CHECK(mz_zip_writer_init_heap(&zip,0,0));
  add(&zip,"mimetype","application/epub+zip");add(&zip,"META-INF/container.xml",container);
  add(&zip,"OPS/book.opf",package);add(&zip,"OPS/c.xhtml",xml);add(&zip,"OPS/d.xhtml",xml);
  CHECK(mz_zip_writer_finalize_heap_archive(&zip,&data,&size));CHECK(mz_zip_writer_end(&zip));
  if(source) {
    exr_source input={.size=size,.read_at=book_read,.release=book_release,.context=source};source->bytes=data;source->size=size;
    OK(exr_publication_open_source(&input,&publication,&error));
  } else { OK(exr_publication_open_memory(EXR_EPUB,data,size,&publication,&error));mz_free(data); }
  free(xml);return publication;
}
static int cancelled(void *context) { (void)context;return 1; }
static void page_work_budget(exr_font *font) {
  const size_t paragraphs=16386,letters=256;
  const char *container="<container><rootfiles><rootfile full-path='book.opf'/></rootfiles></container>";
  const char *package="<package><metadata/><manifest><item id='c' href='c.xhtml' media-type='application/xhtml+xml'/></manifest><spine><itemref idref='c'/></spine></package>";
  mz_zip_archive zip={0};void *data=NULL;size_t size=0,at=0,i,total=0,pages=0,count;
  char *xml=malloc(paragraphs*(letters+7)+100);
  exr_publication *publication=NULL;exr_pager *pager=NULL;exr_layout *page=NULL;
  exr_layout_config config=exr_layout_config_defaults();
  exr_chapter_options options=exr_chapter_options_defaults();
  CHECK(xml!=NULL);at+=(size_t)sprintf(xml+at,"<html><body>");
  for(i=0;i<paragraphs;i++) {
    memcpy(xml+at,"<p>",3);at+=3;memset(xml+at,'a',letters);at+=letters;memcpy(xml+at,"</p>",4);at+=4;
  }
  at+=(size_t)sprintf(xml+at,"</body></html>");
  CHECK(mz_zip_writer_init_heap(&zip,0,0));add(&zip,"mimetype","application/epub+zip");
  add(&zip,"META-INF/container.xml",container);add(&zip,"book.opf",package);add(&zip,"c.xhtml",xml);
  CHECK(mz_zip_writer_finalize_heap_archive(&zip,&data,&size));CHECK(mz_zip_writer_end(&zip));free(xml);
  OK(exr_publication_open_memory(EXR_EPUB,data,size,&publication,&error));mz_free(data);
  config.page=(exr_layout_options){1024,1024,16,8,1.25f,0};config.document_css=0;
  options.window_bytes=2*1024*1024;
  OK(exr_publication_pager_create(publication,0,font,&config,&options,&pager,&error));exr_publication_free(publication);
  for(;;) {
    OK(exr_pager_next(pager,&page,&error));if(!page) break;
    exr_layout_glyphs(page,&count);total+=count;pages++;
    CHECK(pages<10000);exr_layout_free(page);page=NULL;
  }
  CHECK(total==paragraphs*letters && total>4*1024*1024);
  CHECK(exr_pager_chapter_statistics(pager).windows_evicted>0);
  exr_pager_free(pager);
}
typedef struct { const char *expected;size_t offset,end,calls;exr_pager *pager;int reject; } text_check;
static exr_status text_sink(void *context,const char *text,size_t size,exr_error *e) {
  text_check *s=context;exr_layout *page=NULL;
  CHECK(size && size<=32768);CHECK(s->offset+size<=s->end);
  CHECK(!memcmp(text,s->expected+s->offset,size));
  CHECK(((unsigned char)text[0]&0xc0)!=0x80);
  CHECK(exr_pager_next(s->pager,&page,e)==EXR_ARGUMENT);CHECK(page==NULL);
  s->offset+=size;s->calls++;
  return s->reject ? EXR_IO : EXR_OK;
}
static void queries(exr_publication *publication,exr_document *document,exr_font *font,
                    const exr_layout_config *config,const page_sample *first) {
  exr_chapter_options options=exr_chapter_options_defaults();
  exr_pager *pager=NULL;exr_layout *page=NULL;exr_cfi_point point={0},resolved;
  exr_anchor expected={0},actual={0};exr_anchor_match match;
  const exr_node *nodes;const char *text;size_t count,size,i,part;
  char *reference=NULL,*cfi=NULL,*other=NULL;exr_control stop={0};
  nodes=exr_document_nodes(document,&count);text=exr_document_text(document,&size);
  for(i=0;i<count;i++) if(nodes[i].text && strstr(nodes[i].text,"Window 239:")) { point=(exr_cfi_point){i,17,0};break; }
  CHECK(i<count);options.window_bytes=512;
  for(part=0;part<2;part++) {
    exr_document *snapshot=NULL;
    OK(exr_publication_load(publication,part,&snapshot,&error));
    OK(exr_publication_pager_create(publication,part,font,config,&options,&pager,&error));
    for(i=0;i<=32;i+=16) {
      OK(exr_publication_cfi_create_quoted(publication,part,snapshot,&point,i ? i : 1,NULL,&reference,&error));
      OK(exr_pager_cfi_create(pager,&point,i ? i : 1,NULL,&cfi,&error));CHECK(!strcmp(cfi,reference));
      OK(exr_pager_cfi_resolve(pager,cfi,NULL,&resolved,&error));
      CHECK(resolved.node==point.node && resolved.offset==point.offset && resolved.side==point.side);
      if(i==32) {
        char *colon=strstr(cfi,":17[");CHECK(colon!=NULL);CHECK(colon[1]=='1' && colon[2]=='7');
        colon[2]='8';
        OK(exr_pager_cfi_resolve(pager,cfi,NULL,&resolved,&error));
        CHECK(resolved.node==point.node && resolved.offset==point.offset);
      }
      exr_free(cfi);exr_free(reference);cfi=reference=NULL;
    }
    OK(exr_publication_cfi_create(publication,part,snapshot,&point,NULL,&reference,&error));
    OK(exr_pager_cfi_create(pager,&point,0,NULL,&cfi,&error));CHECK(!strcmp(cfi,reference));
    exr_free(cfi);exr_free(reference);cfi=reference=NULL;
    { exr_cfi_point unicode;
      for(i=0;i<count;i++) if(nodes[i].text && strstr(nodes[i].text,"Unicode")) break;
      CHECK(i<count);unicode=(exr_cfi_point){i,8,0};
      OK(exr_publication_cfi_create_quoted(publication,part,snapshot,&unicode,32,NULL,&reference,&error));
      OK(exr_pager_cfi_create(pager,&unicode,32,NULL,&cfi,&error));CHECK(!strcmp(cfi,reference));
      OK(exr_pager_cfi_resolve(pager,cfi,NULL,&resolved,&error));CHECK(resolved.node==unicode.node && resolved.offset==unicode.offset);
      exr_free(cfi);exr_free(reference);cfi=reference=NULL;
      unicode.offset=9;CHECK(exr_pager_cfi_create(pager,&unicode,4,NULL,&cfi,&error)==EXR_ARGUMENT);CHECK(cfi==NULL);
    }
    CHECK(exr_publication_cfi_create(publication,1-part,snapshot,&point,NULL,&other,&error)==EXR_ARGUMENT);CHECK(other==NULL);
    /* Build another part's route with its own snapshot. */
    { exr_document *alternate=NULL;OK(exr_publication_load(publication,1-part,&alternate,&error));
      OK(exr_publication_cfi_create(publication,1-part,alternate,&point,NULL,&other,&error));exr_document_free(alternate); }
    CHECK(exr_pager_cfi_resolve(pager,other,NULL,&resolved,&error)==EXR_ARGUMENT);CHECK(resolved.node==SIZE_MAX);exr_free(other);other=NULL;
    { text_check check={text,0,size,0,pager,0};
      OK(exr_pager_read_text(pager,0,size,text_sink,&check,NULL,&error));CHECK(check.offset==size && check.calls>10);
      check.offset=100;check.end=30000;check.calls=0;
      OK(exr_pager_read_text(pager,100,30000,text_sink,&check,NULL,&error));CHECK(check.offset==30000 && check.calls>1);
      check.offset=0;check.end=size;check.reject=1;
      CHECK(exr_pager_read_text(pager,0,size,text_sink,&check,NULL,&error)==EXR_IO);
    }
    OK(exr_anchor_create(snapshot,100,30000,&expected,&error));
    OK(exr_pager_anchor_create(pager,100,30000,NULL,&actual,&error));
    CHECK(!strcmp(expected.exact,actual.exact) && !strcmp(expected.prefix,actual.prefix) && !strcmp(expected.suffix,actual.suffix));
    OK(exr_pager_anchor_resolve(pager,&actual,NULL,&match,&error));CHECK(match.state==EXR_ANCHOR_FOUND && match.start==100 && match.end==30000);
    exr_anchor_free(&expected);exr_anchor_free(&actual);
    OK(exr_pager_next(pager,&page,&error));CHECK(page!=NULL);CHECK(hash_layout(page).hash==first->hash);exr_layout_free(page);page=NULL;
    stop.cancelled=cancelled;
    CHECK(exr_pager_cfi_create(pager,&point,4,&stop,&cfi,&error)==EXR_CANCELLED);CHECK(cfi==NULL);
    exr_pager_free(pager);pager=NULL;exr_document_free(snapshot);
  }
}
int main(int argc,char **argv) {
  exr_publication *publication=book(0,NULL);exr_document *document=NULL;
  exr_font *font=NULL;exr_pager *pager=NULL;exr_layout *page=NULL;
  exr_layout_config config=exr_layout_config_defaults();
  exr_chapter_options options=exr_chapter_options_defaults();
  page_sample expected[96];size_t i,j;char path[2048];
  static const size_t windows[]={512,2048,16384};
  static const size_t random[]={95,3,48,1,94,4,36,2,93,92,72};
  CHECK(argc==2);snprintf(path,sizeof(path),"%s/primary.ttf",argv[1]);
  OK(exr_font_open(path,&font,&error));OK(exr_publication_load(publication,0,&document,&error));
  config.page.width=240;config.page.height=200;config.page.margin=12;config.page.font_size=14;
  OK(exr_pager_create(document,font,&config,&pager,&error));
  for(i=0;i<96;i++) { OK(exr_pager_next(pager,&page,&error));CHECK(page!=NULL);expected[i]=hash_layout(page);exr_layout_free(page);page=NULL; }
  exr_pager_free(pager);pager=NULL;
  queries(publication,document,font,&config,&expected[0]);
  for(j=0;j<sizeof(windows)/sizeof(*windows);j++) {
    exr_chapter_stats stats;
    options.window_bytes=windows[j];
    OK(exr_publication_pager_create(publication,0,font,&config,&options,&pager,&error));
    for(i=0;i<96;i++) {
      page_sample actual;
      OK(exr_pager_next(pager,&page,&error));CHECK(page!=NULL);actual=hash_layout(page);
      if(actual.hash!=expected[i].hash) fprintf(stderr,"window=%zu page=%zu hashes=%llu/%llu ranges=%zu:%zu/%zu:%zu\n",windows[j],i,(unsigned long long)actual.hash,(unsigned long long)expected[i].hash,actual.start,actual.end,expected[i].start,expected[i].end);
      CHECK(actual.hash==expected[i].hash);exr_layout_free(page);page=NULL;
    }
    stats=exr_pager_chapter_statistics(pager);
    CHECK(stats.windows_loaded>1);CHECK(stats.windows_evicted>0);
    CHECK(stats.index_bytes+stats.parse_workspace_bytes<=options.workspace_budget);
    CHECK(stats.explicit_snapshot_bytes==0);
    exr_pager_free(pager);pager=NULL;
  }
  options.window_bytes=1024;
  OK(exr_publication_pager_create(publication,0,font,&config,&options,&pager,&error));
  OK(exr_pager_set_cache(pager,1,1024*1024,&error));
  OK(exr_pager_set_checkpoints(pager,4,2*1024*1024,2,&error));
  for(i=0;i<sizeof(random)/sizeof(*random);i++) {
    const exr_layout *cached=NULL;page_sample actual;
    OK(exr_pager_get(pager,random[i],&cached,&error));CHECK(cached!=NULL);
    actual=hash_layout(cached);CHECK(actual.hash==expected[random[i]].hash);
  }
  CHECK(exr_pager_statistics(pager).restored_checkpoints>0);
  CHECK(exr_pager_chapter_statistics(pager).windows_evicted>0);
  exr_pager_free(pager);pager=NULL;
  config.control.cancelled=cancelled;
  CHECK(exr_publication_pager_create(publication,0,font,&config,&options,&pager,&error)==EXR_CANCELLED);CHECK(pager==NULL);
  config.control.cancelled=NULL;options.window_bytes=0;
  CHECK(exr_publication_pager_create(publication,0,font,&config,&options,&pager,&error)==EXR_ARGUMENT);CHECK(pager==NULL);
  exr_document_free(document);exr_publication_free(publication);
  publication=book(1,NULL);document=NULL;options=exr_chapter_options_defaults();options.window_bytes=512;
  OK(exr_publication_load(publication,0,&document,&error));OK(exr_pager_create(document,font,&config,&pager,&error));
  for(i=0;i<96;i++) { OK(exr_pager_next(pager,&page,&error));CHECK(page!=NULL);expected[i]=hash_layout(page);exr_layout_free(page);page=NULL; }
  exr_pager_free(pager);pager=NULL;
  OK(exr_publication_pager_create(publication,0,font,&config,&options,&pager,&error));
  for(i=0;i<96;i++) { OK(exr_pager_next(pager,&page,&error));CHECK(page!=NULL);CHECK(exr_layout_writing_mode(page)==EXR_WRITING_VERTICAL_RL);CHECK(hash_layout(page).hash==expected[i].hash);exr_layout_free(page);page=NULL; }
  CHECK(exr_pager_chapter_statistics(pager).windows_evicted>1);exr_pager_free(pager);
  exr_document_free(document);exr_publication_free(publication);pager=NULL;
  { book_source source={0};
    publication=book(0,&source);options.window_bytes=512;
    OK(exr_publication_pager_create(publication,0,font,&config,&options,&pager,&error));
    exr_publication_free(publication);publication=NULL;CHECK(!source.released);
    source.fail=1;
    CHECK(exr_pager_next(pager,&page,&error)==EXR_IO);CHECK(page==NULL);
    exr_pager_free(pager);pager=NULL;CHECK(source.released==1);
  }
  publication=book(0,NULL);options.workspace_budget=1024*1024;
  CHECK(exr_publication_pager_create(publication,0,font,&config,&options,&pager,&error)==EXR_LIMIT);CHECK(pager==NULL);
  exr_publication_free(publication);page_work_budget(font);exr_font_free(font);
  printf("%u chapter reader equivalence and recovery checks passed\n",checks);return 0;
}
