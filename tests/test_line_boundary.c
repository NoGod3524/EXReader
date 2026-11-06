/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static exr_error error;
static unsigned checks;
static const char *scenario;
static exr_font *font;
#define CHECK(x) do { checks++; if (!(x)) { \
  fprintf(stderr, "%s line %d: %s (%d: %s)\n", scenario, __LINE__, #x, \
          (int)error.code, error.message); exit(1); } } while (0)
#define OK(x) CHECK((x) == EXR_OK)
static int near(float a, float b) { return isfinite(a) && fabsf(a - b) < 0.02f; }
static exr_font *open_font(const char *directory, const char *name) {
  char path[4096];
  exr_font *out = NULL;
  CHECK(snprintf(path, sizeof(path), "%s/%s", directory, name) > 0);
  OK(exr_font_open(path, &out, &error));
  return out;
}
static exr_layout_config config(void) {
  exr_layout_config c = exr_layout_config_defaults();
  c.page = (exr_layout_options){120, 80, 8, 20, 1.2f, 0};
  return c;
}
static exr_document *document(const char *text, const char *style, int table) {
  exr_attribute attrs = {"style", style};
  exr_node_input nodes[] = {
      {EXR_NODE_DOCUMENT, SIZE_MAX, NULL, NULL, NULL, 0},
      {EXR_NODE_CHAPTER, 0, NULL, NULL, NULL, 0},
      {EXR_NODE_PARAGRAPH, 1, NULL, NULL, &attrs, 1},
      {EXR_NODE_TEXT, 2, NULL, text, NULL, 0},
      {EXR_NODE_CELL, 3, NULL, NULL, NULL, 0},
      {EXR_NODE_TEXT, 4, NULL, text, NULL, 0}};
  exr_chapter_input chapter = {"line", "line.unit", 1, 1};
  exr_document_input input = {"Line boundaries", nodes, table ? 6 : 4, &chapter, 1, NULL, 0};
  exr_document *doc = NULL;
  if (table) {
    nodes[2].kind = EXR_NODE_TABLE;
    nodes[3] = (exr_node_input){EXR_NODE_ROW, 2, NULL, NULL, NULL, 0};
  }
  OK(exr_document_create(&input, &doc, &error));
  return doc;
}
static exr_layout *layout(exr_document *doc, const exr_layout_config *c) {
  exr_layout *l = NULL;
  OK(exr_layout_create_ex(doc, font, c, &l, &error));
  return l;
}
static void compare_page(const exr_layout *whole, size_t page, const exr_layout *single) {
  const exr_page *a = &exr_layout_pages(whole, NULL)[page], *b;
  const exr_line *al = exr_layout_lines(whole, NULL), *bl = exr_layout_lines(single, NULL);
  const exr_glyph *ag = exr_layout_glyphs(whole, NULL), *bg = exr_layout_glyphs(single, NULL);
  exr_bitmap x = {0}, y = {0};
  size_t count, i, j;
  b = exr_layout_pages(single, &count);
  CHECK(count == 1 && a->start == b->start && a->end == b->end && a->line_count == b->line_count);
  for (i = 0; i < a->line_count; i++) {
    const exr_line *u = &al[a->line_start + i], *v = &bl[i];
    CHECK(u->start == v->start && u->end == v->end && u->glyph_count == v->glyph_count);
    CHECK(near(u->x, v->x) && near(u->y, v->y) && near(u->width, v->width));
    for (j = 0; j < u->glyph_count; j++) {
      const exr_glyph *p = &ag[u->glyph_start + j], *q = &bg[v->glyph_start + j];
      CHECK(p->glyph == q->glyph && p->start == q->start && p->end == q->end);
      CHECK(p->cluster_start == q->cluster_start && p->cluster_end == q->cluster_end);
      CHECK(p->bidi_level == q->bidi_level && p->flags == q->flags);
      CHECK(near(p->x, q->x) && near(p->baseline, q->baseline) && near(p->advance, q->advance));
      CHECK(near(p->offset_x, q->offset_x) && near(p->offset_y, q->offset_y));
    }
  }
  OK(exr_render_page_color(whole, font, page, &x, &error));
  OK(exr_render_page_color(single, font, 0, &y, &error));
  CHECK(x.stride == y.stride && x.height == y.height);
  CHECK(!memcmp(x.pixels, y.pixels, (size_t)x.stride * x.height));
  exr_bitmap_free(&x); exr_bitmap_free(&y);
}
static void modes(exr_document *doc, const exr_layout_config *c) {
  exr_layout *whole = layout(doc, c), *page = NULL;
  exr_pager *pager = NULL;
  const exr_layout *cached = NULL;
  size_t count, i;
  exr_layout_pages(whole, &count);
  OK(exr_pager_create(doc, font, c, &pager, &error));
  for (i = 0; i < count; i++) {
    OK(exr_pager_next(pager, &page, &error)); CHECK(page);
    compare_page(whole, i, page); exr_layout_free(page);
  }
  OK(exr_pager_next(pager, &page, &error)); CHECK(!page);
  exr_pager_free(pager);
  OK(exr_pager_create(doc, font, c, &pager, &error));
  OK(exr_pager_set_cache(pager, 2, 1024 * 1024, &error));
  OK(exr_pager_get(pager, count - 1, &cached, &error)); compare_page(whole, count - 1, cached);
  OK(exr_pager_get(pager, 0, &cached, &error)); compare_page(whole, 0, cached);
  OK(exr_pager_get(pager, count - 1, &cached, &error)); compare_page(whole, count - 1, cached);
  CHECK(exr_pager_cached_count(pager) <= 2 && exr_pager_cached_bytes(pager) <= 1024 * 1024);
  exr_pager_free(pager); exr_layout_free(whole);
}
static void pair_boundaries(void) {
  exr_layout_config c = config();
  exr_document *doc;
  exr_layout *l;
  const exr_glyph *g;
  const exr_line *lines;
  size_t n, i;
  scenario = "pair positioning stays within its line";
  for (i = 0; i < 2; i++) {
    doc = document("AV", i ? "width:12px;margin:0;text-align:right" : "width:12px;margin:0", 0);
    l = layout(doc, &c); g = exr_layout_glyphs(l, &n); CHECK(n == 2);
    lines = exr_layout_lines(l, &n); CHECK(n == 2);
    CHECK(g[0].glyph == 2 && g[1].glyph == 3);
    CHECK(near(g[0].advance, 12) && near(g[1].advance, 12));
    CHECK(near(g[0].offset_x, 0) && near(g[1].offset_x, 0) && near(g[1].offset_y, 0));
    CHECK(near(lines[0].width, 12) && near(lines[1].width, 12));
    CHECK(near(lines[0].x, c.page.margin));
    CHECK(exr_layout_hit_test(l, 0, g[0].x + 5.5f, g[0].baseline - 2) == 0);
    CHECK(exr_layout_hit_test(l, 0, g[0].x + 6.5f, g[0].baseline - 2) == 1);
    exr_layout_free(l); modes(doc, &c); exr_document_free(doc);
  }
  scenario = "positive second pair value applies only within one line";
  doc = document("AV", "width:30px;margin:0", 0); l = layout(doc, &c);
  g = exr_layout_glyphs(l, &n); CHECK(n == 2);
  CHECK(near(g[0].advance, 10) && near(g[1].advance, 11));
  CHECK(near(g[1].offset_x, 2.4f) && near(g[1].offset_y, 1.6f));
  exr_layout_free(l); exr_document_free(doc);
  scenario = "reshaping growth retreats to an earlier soft boundary";
  doc = document("a bcAV", "width:46px;margin:0", 0); l = layout(doc, &c);
  lines = exr_layout_lines(l, &n); CHECK(n == 2);
  CHECK(lines[0].start == 0 && lines[0].end == 2 && near(lines[0].width, 15));
  CHECK(lines[1].start == 2 && lines[1].end == 6 && near(lines[1].width, 41));
  exr_layout_free(l); modes(doc, &c); exr_document_free(doc);
  scenario = "table cell previews use the same boundary shaping";
  doc = document("AV", "width:12px;margin:0", 1); l = layout(doc, &c);
  g = exr_layout_glyphs(l, &n); CHECK(n == 2);
  CHECK(near(g[0].advance, 12) && near(g[1].advance, 12) && near(g[1].offset_x, 0));
  exr_layout_free(l); modes(doc, &c); exr_document_free(doc);
}
static void cursive_and_arabic(void) {
  exr_layout_config c = config();
  exr_document *doc;
  exr_layout *l;
  const exr_glyph *g;
  size_t n, i;
  scenario = "cursive outgoing and incoming attachments stop at a wrap";
  doc = document("xy", "width:10px;margin:0", 0); l = layout(doc, &c);
  g = exr_layout_glyphs(l, &n); CHECK(n == 2);
  for (i = 0; i < n; i++) CHECK(near(g[i].advance, 10) && near(g[i].offset_x, 0) && near(g[i].offset_y, 0));
  exr_layout_free(l); modes(doc, &c); exr_document_free(doc);
  scenario = "Arabic emergency lines use isolated joining forms";
  doc = document("\xd8\xa8\xd8\xa8\xd8\xa8", "width:12px;margin:0;text-align:start", 0);
  l = layout(doc, &c); g = exr_layout_glyphs(l, &n); CHECK(n == 3);
  for (i = 0; i < n; i++) {
    CHECK(g[i].glyph == 19 && (g[i].bidi_level & 1));
    CHECK(near(g[i].advance, 12) && near(g[i].offset_x, 0) && near(g[i].offset_y, 0));
  }
  exr_layout_free(l); modes(doc, &c); exr_document_free(doc);
  scenario = "ligature clusters remain indivisible";
  doc = document("fififi", "width:9px;margin:0", 0); l = layout(doc, &c);
  g = exr_layout_glyphs(l, &n); CHECK(n == 3);
  for (i = 0; i < n; i++) CHECK(g[i].glyph == 7 && g[i].start == i*2 && g[i].end == i*2 + 2);
  exr_layout_free(l); modes(doc, &c); exr_document_free(doc);
}
static void pagination(void) {
  exr_layout_config c = config();
  char text[129];
  size_t i;
  exr_document *doc;
  scenario = "pending finalized lines survive page pause and cache replay";
  for (i = 0; i < 64; i++) { text[i*2] = 'A'; text[i*2 + 1] = 'V'; }
  text[128] = 0;
  doc = document(text, "width:12px;margin:0;text-align:right", 0);
  modes(doc, &c); exr_document_free(doc);
}
static void long_inline_marks(void) {
  const size_t marks = 8191, size = 1 + marks*2;
  char *text = malloc(size + 1);
  exr_layout_config c = config();
  exr_document *doc;
  exr_layout *l;
  const exr_glyph *g;
  size_t i, n;
  scenario = "8191 inline marks retain their complete source cluster";
  CHECK(text); text[0] = 'a';
  for (i = 0; i < marks; i++) memcpy(text + 1 + i*2, i + 1 == marks ? "\xcc\x87" : "\xcc\x81", 2);
  text[size] = 0;
  doc = document(text, "width:30px;margin:0", 0); l = layout(doc, &c);
  g = exr_layout_glyphs(l, &n); CHECK(n == marks + 1);
  for (i = 0; i < n; i++) {
    CHECK(g[i].start == 0 && g[i].end == size && g[i].cluster_start == 0 && g[i].cluster_end == size);
    if (i) {
      CHECK(near(g[i].advance, 0));
      CHECK(near(g[i].offset_x, i == marks ? -2.4f : -4));
      CHECK(near(g[i].offset_y, i == marks ? 17.8f : 14));
    }
  }
  exr_layout_free(l); exr_document_free(doc); free(text);
}
static void queue_budget(const char *directory) {
  const size_t repeats = 100000;
  char *text = malloc(repeats*4 + 1);
  exr_layout_config c = config();
  exr_document *doc;
  exr_pager *pager = NULL;
  exr_layout *page = (exr_layout *)(uintptr_t)1;
  exr_font *saved = font;
  size_t i;
  scenario = "cumulative queue payload is bounded for an unbreakable no-OT run";
  CHECK(text);
  for (i = 0; i < repeats; i++) memcpy(text + i*4, "A\xe2\x81\xa0", 4);
  text[repeats*4] = 0;
  font = open_font(directory, "primary.ttf");
  doc = document(text, "margin:0", 0);
  OK(exr_pager_create(doc, font, &c, &pager, &error));
  CHECK(exr_pager_next(pager, &page, &error) == EXR_LIMIT && !page);
  CHECK(strstr(error.message, "Line buffer") != NULL);
  exr_pager_free(pager); exr_document_free(doc); exr_font_free(font); font = saved; free(text);
}
static exr_status cjk_replacement(void *context,const char *language,const char *word,size_t size,
                                exr_hyphen_emit_fn emit,void *target,const exr_control *control,exr_error *e) {
  exr_hyphen_break item={4,3,8,"aa",context,2,strlen(context)};
  (void)language;(void)control;
  return size==8 && !memcmp(word,"aaaaaaaa",8) ? emit(target,&item,e):EXR_OK;
}
static void cjk_space_punctuation(void) {
  const char *punctuation[]={"\xef\xbc\x9a","\xef\xbc\x9b"};
  char replacement[32];
  exr_hyphen_discretionary_provider provider={sizeof(provider),cjk_replacement,NULL,replacement};
  exr_hyphenator *h=NULL;
  exr_layout_config c=config();
  size_t p,mode;
  scenario="Chinese SP colon/semicolon tailoring and display reconstruction";
  OK(exr_hyphenator_create_discretionary(&provider,&h,&error));
  for(p=0;p<2;p++)for(mode=0;mode<4;mode++) {
    char text[128],style[128],prefix[128];unsigned char *map=NULL;
    exr_document *doc;exr_layout *l=NULL;
    size_t n,nl,i,j,found=0,inserted=0;const exr_glyph *g;const exr_line *lines;
    uint32_t cp=p ? 0xff1b:0xff1a;
    snprintf(replacement,sizeof(replacement),"\xe7\x94\xb2 %s\xe4\xb9\x99",punctuation[p]);
    snprintf(text,sizeof(text),"%s\xe7\x94\xb2\xe4\xb9\x99 %s\xe4\xb8\x99\xe4\xb8\x81",
             mode==3 ? "aaaaaaaa ":"",punctuation[p]);
    /* The public analyzer must continue to apply default Unicode LB18. */
    OK(exr_text_analyze(text,strlen(text),&map,&error));
    i=(mode==3 ? 9:0)+7;
    CHECK((map[i]&EXR_BOUNDARY_LINE) && !(map[i]&EXR_BOUNDARY_GLUE));exr_free(map);
    snprintf(style,sizeof(style),"width:%upx;margin:0;hyphens:auto",mode==0 ? 1:mode==1 ? 35:mode==2 ? 300:70);
    {
      exr_attribute attrs[]={{"style",style},{"lang","und"}};
      exr_node_input nodes[]={
        {EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0},{EXR_NODE_CHAPTER,0,NULL,NULL,NULL,0},
        {EXR_NODE_PARAGRAPH,1,"p",NULL,attrs,2},{EXR_NODE_TEXT,2,NULL,prefix,NULL,0},
        {EXR_NODE_ELEMENT,2,"span",NULL,NULL,0},{EXR_NODE_TEXT,4,NULL,text+i,NULL,0}};
      exr_chapter_input chapter={"kinsoku","kinsoku.unit",1,1};
      exr_document_input input={"Cross-node punctuation",nodes,6,&chapter,1,NULL,0};
      memcpy(prefix,text,i);prefix[i]=0;doc=NULL;
      OK(exr_document_create(&input,&doc,&error));
    }
    OK(exr_layout_create_hyphenated(doc,font,&c,mode==3 ? h:NULL,&l,&error));
    g=exr_layout_glyphs(l,&n);lines=exr_layout_lines(l,&nl);
    for(i=0;i<n;i++) {
      if(g[i].codepoint==cp) {
        CHECK((g[i].boundaries&EXR_BOUNDARY_GLUE) && !(g[i].boundaries&EXR_BOUNDARY_LINE));
        found++;inserted+=!!(g[i].flags&EXR_GLYPH_GENERATED);
      }
    }
    CHECK(found==(mode==3 ? 2:1) && inserted==(mode==3 ? 1:0));
    for(i=0;i<nl;i++)for(j=lines[i].glyph_start;j<lines[i].glyph_start+lines[i].glyph_count;j++) {
      if((g[j].flags&EXR_GLYPH_HIDDEN) || g[j].codepoint==32)continue;
      CHECK(g[j].codepoint!=cp);break;
    }
    exr_layout_free(l);if(mode<3)modes(doc,&c);exr_document_free(doc);
  }
  exr_hyphenator_free(h);
  {
    /* A different NS scalar keeps its default SP opportunity. */
    exr_document *doc=document("\xe7\x94\xb2 \xe3\x80\x85\xe4\xb9\x99","width:300px;margin:0",0);
    exr_layout *l=layout(doc,&c);size_t n,i;const exr_glyph *g=exr_layout_glyphs(l,&n);
    for(i=0;i<n;i++)if(g[i].codepoint==0x3005)CHECK((g[i].boundaries&EXR_BOUNDARY_LINE) && !(g[i].boundaries&EXR_BOUNDARY_GLUE));
    exr_layout_free(l);exr_document_free(doc);
  }
  {
    /* Keep explicit <br/> and paragraph-start punctuation at the line head. */
    exr_node_input nodes[]={
      {EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0},{EXR_NODE_CHAPTER,0,NULL,NULL,NULL,0},
      {EXR_NODE_PARAGRAPH,1,"p",NULL,NULL,0},{EXR_NODE_TEXT,2,NULL,"\xe7\x94\xb2 ",NULL,0},
      {EXR_NODE_BREAK,2,"br",NULL,NULL,0},{EXR_NODE_TEXT,2,NULL,"\xef\xbc\x9a\xe4\xb9\x99",NULL,0},
      {EXR_NODE_PARAGRAPH,1,"p",NULL,NULL,0},{EXR_NODE_TEXT,6,NULL,"\xef\xbc\x9b\xe4\xb9\x99",NULL,0}};
    exr_chapter_input chapter={"kinsoku","kinsoku.unit",1,1};
    exr_document_input input={"Hard breaks",nodes,8,&chapter,1,NULL,0};
    exr_document *doc=NULL;exr_layout *l;size_t n,i,heads=0;
    const exr_line *lines;const exr_glyph *g;
    OK(exr_document_create(&input,&doc,&error));l=layout(doc,&c);
    g=exr_layout_glyphs(l,NULL);lines=exr_layout_lines(l,&n);
    for(i=0;i<n;i++)if(lines[i].glyph_count) {
      uint32_t cp=g[lines[i].glyph_start].codepoint;heads+=cp==0xff1a || cp==0xff1b;
    }
    CHECK(heads==2);exr_layout_free(l);modes(doc,&c);exr_document_free(doc);
  }
}
int main(int argc, char **argv) {
  scenario = "setup"; CHECK(argc == 3);
  font = open_font(argv[1], "line-boundary.ttf");
  pair_boundaries(); cursive_and_arabic(); pagination(); long_inline_marks(); queue_budget(argv[2]);
  cjk_space_punctuation();
  exr_font_free(font);
  printf("EXReader line boundaries: %u checks passed\n", checks);
  return 0;
}
