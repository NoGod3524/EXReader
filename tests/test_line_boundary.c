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
  /* These width oracles exercise break opportunities without paragraph indent. */
  c.user_css="* {text-indent:0}";
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
    /* A Latin left neighbor retains SP and its default NS opportunity. */
    exr_document *doc=document("A \xe3\x80\x85\xe4\xb9\x99","width:300px;margin:0",0);
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
/* Exercise feed, emergency wrapping and display_scan independently, with the
   protected boundary crossing an inline node in the original source. */
static void kinsoku_layout(const char *left,const char *right,uint32_t protected_cp) {
  char replacement[64],prefix[64],suffix[64],style[80];
  exr_hyphen_discretionary_provider provider={sizeof(provider),cjk_replacement,NULL,replacement};
  exr_hyphenator *h=NULL;exr_layout_config c=config();size_t mode;
  snprintf(replacement,sizeof(replacement),"%s%s",left,right);
  OK(exr_hyphenator_create_discretionary(&provider,&h,&error));
  for(mode=0;mode<4;mode++) {
    exr_document *doc=NULL;exr_layout *l=NULL;size_t n,nl,i,j,found=0,generated=0;
    const exr_glyph *g;const exr_line *lines;
    snprintf(prefix,sizeof(prefix),"%s%s",mode==3 ? "aaaaaaaa ":"",left);
    snprintf(suffix,sizeof(suffix),"%s\xe7\x94\xb2",right);
    snprintf(style,sizeof(style),"width:%upx;margin:0;hyphens:auto",mode==0 ? 1:mode==1 ? 35:mode==2 ? 300:70);
    {
      exr_attribute attrs[]={{"style",style},{"lang","und"}};
      exr_node_input nodes[]={
        {EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0},{EXR_NODE_CHAPTER,0,NULL,NULL,NULL,0},
        {EXR_NODE_PARAGRAPH,1,"p",NULL,attrs,2},{EXR_NODE_TEXT,2,NULL,prefix,NULL,0},
        {EXR_NODE_ELEMENT,2,"span",NULL,NULL,0},{EXR_NODE_TEXT,4,NULL,suffix,NULL,0}};
      exr_chapter_input chapter={"kinsoku","kinsoku.unit",1,1};
      exr_document_input input={"Kinsoku spaces",nodes,6,&chapter,1,NULL,0};
      OK(exr_document_create(&input,&doc,&error));
    }
    CHECK(strchr(exr_document_text(doc,NULL),' ')!=NULL);
    OK(exr_layout_create_hyphenated(doc,font,&c,mode==3 ? h:NULL,&l,&error));
    g=exr_layout_glyphs(l,&n);lines=exr_layout_lines(l,&nl);
    for(i=0;i<n;i++)if(g[i].codepoint==protected_cp) {
      CHECK((g[i].boundaries&EXR_BOUNDARY_GLUE) && !(g[i].boundaries&EXR_BOUNDARY_LINE));
      found++;generated+=!!(g[i].flags&EXR_GLYPH_GENERATED);
      for(j=0;j<nl;j++)if(i>=lines[j].glyph_start && i<lines[j].glyph_start+lines[j].glyph_count) {
        size_t k=i;
        while(k>lines[j].glyph_start && (g[k-1].codepoint==32 || (g[k-1].flags&EXR_GLYPH_HIDDEN)))k--;
        CHECK(k>lines[j].glyph_start);break;
      }
      CHECK(j<nl);
    }
    CHECK(found==(mode==3 ? 2:1) && generated==(mode==3 ? 1:0));
    exr_layout_free(l);if(mode<3)modes(doc,&c);exr_document_free(doc);
  }
  exr_hyphenator_free(h);
}
static void cjk_space_kinsoku_set(void) {
  /* All 16 members of the probe's head_bad | tail_bad, not a colon-only sample. */
  const struct {const char *utf8;uint32_t cp;} punctuation[]={
    {"\xe3\x80\x82",0x3002},{"\xe3\x80\x81",0x3001},{"\xef\xbc\x8c",0xff0c},
    {"\xef\xbc\x8e",0xff0e},{"\xef\xbc\x89",0xff09},{"\xe3\x80\x8d",0x300d},
    {"\xe3\x80\x8f",0x300f},{"\xef\xbc\x81",0xff01},{"\xef\xbc\x9f",0xff1f},
    {"\xef\xbc\x9a",0xff1a},{"\xef\xbc\x9b",0xff1b},{"\xe2\x80\x9d",0x201d},
    {"\xef\xbc\x88",0xff08},{"\xe3\x80\x8c",0x300c},{"\xe3\x80\x8e",0x300e},
    {"\xe2\x80\x9c",0x201c}};
  size_t i;scenario="SP plus every Chinese kinsoku scalar stays on one line";
  for(i=0;i<sizeof(punctuation)/sizeof(*punctuation);i++) {
    char right[32];snprintf(right,sizeof(right),"%s\xe4\xb9\x99",punctuation[i].utf8);
    /* Latin A keeps the SP in the projection so this still tests tailoring. */
    kinsoku_layout("\xe7\x94\xb2" "A ",right,punctuation[i].cp);
  }
}
static void cjk_opening_space_text(void) {
  const char *opening[]={"\xef\xbc\x88","\xe3\x80\x8c","\xe3\x80\x8e","\xe2\x80\x9c"};
  size_t i;scenario="opening punctuation plus SP plus text cannot leave an opening at the tail";
  for(i=0;i<sizeof(opening)/sizeof(*opening);i++) {
    char left[32];snprintf(left,sizeof(left),"\xe7\x94\xb2%s ",opening[i]);
    kinsoku_layout(left,"A",0x41);
  }
}
static void latin_quote_spaces(void) {
  const char *texts[]={"A \xe2\x80\x9c" "A","A \xe2\x80\x9d" "A","A\xe2\x80\x9c A"};
  exr_layout_config c=config();size_t t;
  scenario="Latin quote spaces retain default Unicode boundaries";
  for(t=0;t<sizeof(texts)/sizeof(*texts);t++) {
    unsigned char *map=NULL;exr_document *doc=document(texts[t],"width:35px;margin:0",0);
    exr_layout *l=layout(doc,&c);size_t n,i;const exr_glyph *g=exr_layout_glyphs(l,&n);
    unsigned mask=EXR_BOUNDARY_LINE|EXR_BOUNDARY_GLUE|EXR_BOUNDARY_MANDATORY;
    OK(exr_text_analyze(texts[t],strlen(texts[t]),&map,&error));
    for(i=0;i<n;i++)CHECK((g[i].boundaries&mask)==(map[g[i].start]&mask));
    exr_free(map);exr_layout_free(l);modes(doc,&c);exr_document_free(doc);
  }
}
static void cjk_punctuation_pair(void) {
  exr_layout_config c=config();
  exr_document *doc=document("\xe3\x80\x82\xe3\x80\x8c\xe7\x94\xb2","width:50px;margin:0",0);
  exr_layout *l=layout(doc,&c);size_t n;
  const exr_glyph *g=exr_layout_glyphs(l,&n);
  const exr_line *lines;
  scenario="two fullwidth punctuation fit in 1.5em";
  CHECK(n==3);lines=exr_layout_lines(l,&n);CHECK(n==1);
  CHECK(near(g[0].advance,10) && near(g[1].advance,20));
  CHECK(near(g[1].x-g[0].x,10) && near(lines[0].width,50));
  CHECK(near(g[0].size,20) && near(g[1].size,20));
  CHECK(near(g[0].offset_x,0) && near(g[1].offset_x,0));
  exr_layout_free(l);modes(doc,&c);exr_document_free(doc);
}
static void cjk_punctuation_three(void) {
  exr_layout_config c=config();
  exr_document *doc=document("\xe3\x80\x82\xe3\x80\x8d\xe3\x80\x8c\xe7\x94\xb2","width:60px;margin:0",0);
  exr_layout *l=layout(doc,&c);size_t n;
  const exr_glyph *g=exr_layout_glyphs(l,&n);const exr_line *lines;
  scenario="three punctuation save 1em without reducing below 0.5em";
  CHECK(n==4);lines=exr_layout_lines(l,&n);CHECK(n==1);
  CHECK(near(g[0].advance,10) && near(g[1].advance,10) && near(g[2].advance,20));
  CHECK(near(g[1].x-g[0].x,10) && near(g[2].x-g[1].x,10));
  CHECK(near(g[2].x+g[2].advance-g[0].x,40) && near(lines[0].width,60));
  exr_layout_free(l);modes(doc,&c);exr_document_free(doc);
}
static void cjk_punctuation_wrap(void) {
  exr_layout_config c=config();size_t hard;
  scenario="terminal pair fits one em; hard break opening uses half an em";
  for(hard=0;hard<2;hard++) {
    exr_document *doc;
    exr_layout *l;size_t n,i,found=0;
    if(hard) {
      exr_node_input nodes[]={
        {EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0},{EXR_NODE_CHAPTER,0,NULL,NULL,NULL,0},
        {EXR_NODE_PARAGRAPH,1,"p",NULL,NULL,0},{EXR_NODE_TEXT,2,NULL,"\xe3\x80\x82",NULL,0},
        {EXR_NODE_BREAK,2,"br",NULL,NULL,0},{EXR_NODE_TEXT,2,NULL,"\xe3\x80\x8c",NULL,0}};
      exr_chapter_input chapter={"compression","compression.unit",1,1};
      exr_document_input input={"Hard break",nodes,6,&chapter,1,NULL,0};
      doc=NULL;OK(exr_document_create(&input,&doc,&error));
    } else doc=document("\xe3\x80\x82\xe3\x80\x8c","width:20px;margin:0",0);
    l=layout(doc,&c);
    const exr_glyph *g=exr_layout_glyphs(l,&n);const exr_line *lines;
    for(i=0;i<n;i++)if(g[i].codepoint==0x3002 || g[i].codepoint==0x300c) {
      CHECK(near(g[i].advance,hard && g[i].codepoint==0x3002 ? 20:10));found++;
    }
    CHECK(found==2);lines=exr_layout_lines(l,&n);CHECK(n==(hard ? 2:1));
    CHECK(near(lines[0].width,20));
    if(hard) CHECK(near(lines[1].width,10));
    exr_layout_free(l);modes(doc,&c);exr_document_free(doc);
  }
}
static void cjk_punctuation_exclusions(void) {
  const char *texts[]={",.","\xe3\x80\x82\xe2\x80\xaf\xe3\x80\x8c","\xe3\x80\x82" "A\xe3\x80\x8c"};
  exr_layout_config c=config();size_t k;
  scenario="ASCII punctuation and intervening narrow NBSP/text stay unchanged";
  for(k=0;k<3;k++) {
    exr_document *doc=document(texts[k],"width:100px;margin:0",0);
    exr_layout *l=layout(doc,&c);size_t n,i;const exr_glyph *g=exr_layout_glyphs(l,&n);
    for(i=0;i<n;i++)CHECK(near(g[i].advance,20));
    exr_layout_free(l);exr_document_free(doc);
  }
}

static void cjk_justification(void) {
  const char *text="\u7532\u7532\u7532\u7532\u7532\u7532";
  exr_layout_config c=config();size_t mode;
  c.page.height=120;
  scenario="CJK spacing cap, final line, center, heading and vertical projection";
  for(mode=0;mode<5;mode++) {
    exr_document *doc=document(text,mode==1 ? "height:83px;margin:0;writing-mode:vertical-rl":
      mode==2 ? "width:83px;margin:0;text-align:center":"width:83px;margin:0",0);
    if(mode==3) { /* Heading through the public constructor. */
      exr_document_free(doc);
      exr_attribute attr={"style","width:83px;margin:0"};
      exr_node_input nodes[]={{EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0},
        {EXR_NODE_CHAPTER,0,NULL,NULL,NULL,0},{EXR_NODE_HEADING,1,"h1",NULL,&attr,1},
        {EXR_NODE_TEXT,2,NULL,text,NULL,0}};
      exr_chapter_input ch={"heading","heading.unit",1,1};
      exr_document_input in={"Heading",nodes,4,&ch,1,NULL,0};
      OK(exr_document_create(&in,&doc,&error));
    }
    if(mode==4) { exr_document_free(doc);doc=document("\u7532\u7532","width:83px;margin:0",0); }
    exr_layout *l=layout(doc,&c);size_t n,i;
    const exr_line *lines=exr_layout_lines(l,&n);const exr_glyph *g=exr_layout_glyphs(l,NULL);
    if(mode<2) {
      CHECK(n==2);
      CHECK(near(mode ? lines[0].height:lines[0].width,83));
      CHECK(near(mode ? lines[1].height:lines[1].width,40));
      for(i=0;i<3;i++) {
        float delta=(mode ? g[i+1].baseline-g[i].baseline:g[i+1].x-g[i].x)-g[i].advance;
        CHECK(delta>=0 && delta<=.08f*g[i].size && near(delta,1));
      }
      CHECK(near(mode ? g[5].baseline-g[4].baseline:g[5].x-g[4].x,20));
    } else {
      for(i=1;i<lines[0].glyph_count;i++) CHECK(near(g[i].x-g[i-1].x,g[i-1].advance));
    }
    exr_layout_free(l);modes(doc,&c);exr_document_free(doc);
  }
  scenario="spacing over cap tries half-em punctuation compression first";
  exr_document *doc=document("\u7532\u3002\u7532\u7532\u7532","width:70px;margin:0",0);
  exr_layout *l=layout(doc,&c);size_t n;const exr_line *lines=exr_layout_lines(l,&n);
  const exr_glyph *g=exr_layout_glyphs(l,NULL);
  CHECK(n==2 && lines[0].glyph_count==4 && near(lines[0].width,70));
  CHECK(near(g[1].advance,10) && near(g[0].advance,20) && near(g[2].advance,20));
  exr_layout_free(l);modes(doc,&c);exr_document_free(doc);
  scenario="punctuation stays fullwidth when the spacing cap already suffices";
  doc=document("\u7532\u3002\u7532\u7532\u7532","width:83px;margin:0",0);
  l=layout(doc,&c);g=exr_layout_glyphs(l,NULL);lines=exr_layout_lines(l,&n);
  CHECK(n==2 && lines[0].glyph_count==4 && near(g[1].advance,20));
  CHECK(near(g[1].x-g[0].x-g[0].advance,1));
  exr_layout_free(l);modes(doc,&c);exr_document_free(doc);
  scenario="terminal punctuation pair owns one em and opening owns half an em";
  doc=document("\u300c\u7532\u3002\u300d","width:100px;margin:0",0);
  l=layout(doc,&c);g=exr_layout_glyphs(l,&n);CHECK(n==4);
  CHECK(near(g[0].advance,10) && near(g[2].advance+g[3].advance,20));
  CHECK(near(g[0].offset_x,-10));
  CHECK(near(g[1].x-g[0].x,10) && near(g[3].x+g[3].advance-g[2].x,20));
  exr_layout_free(l);modes(doc,&c);exr_document_free(doc);
}

static void simplified_mixed_punctuation(void) {
  const char *texts[]={
    "\u53d1\u540e\u91cc\u53f0\u5e72\u4e91\uff0c\u56fd\u6c49\u4e66\u95e8\u98ce\u4e1c\u8f66\u9a6c\uff01",
    "\u4ed6\u95ee\uff1a\u201c\u5934\u53d1\u540e\u9762\u6709\u4ec0\u4e48\uff1f\u201d\u5979\u8bf4\uff1a\u201c\u662f123\u4e2a\u5b57\u3002\u201d",
    "\u7b2c12\u7ae0,\u4e00\u4e8c\u4e09.\u56db\u4e94\u516d!\u4e03\u516b\u4e5d?\uff08\u7b2c2026\u5e74\uff09\u3002",
    "\u7b80\u4f53\uff0c\u201c\u6df7\u7528\u3002\u201d\u201c\u5168\u89d2\uff01\u201d\u534a\u89d2,\u6807\u70b9;\u6d4b\u8bd5:\u7ed3\u675f\u3002"};
  size_t t,w,mode;
  scenario="simplified mixed punctuation: edges and identical whole/pager/session output";
  for(t=0;t<sizeof(texts)/sizeof(texts[0]);t++)for(w=83;w<=123;w+=20)for(mode=0;mode<2;mode++) {
    char style[128];exr_layout_config c=config();exr_document *doc;exr_layout *l;
    size_t count,i,j;const exr_line *lines;const exr_glyph *g;
    snprintf(style,sizeof(style),mode ? "height:%zupx;margin:0;writing-mode:vertical-rl":"width:%zupx;margin:0",w);
    doc=document(texts[t],style,0);l=layout(doc,&c);
    lines=exr_layout_lines(l,&count);g=exr_layout_glyphs(l,NULL);
    for(i=0;i<count;i++) {
      const exr_glyph *first=NULL,*last=NULL;
      for(j=0;j<lines[i].glyph_count;j++) {
        const exr_glyph *v=g+lines[i].glyph_start+j;
        if(!(v->flags&EXR_GLYPH_HIDDEN) && v->codepoint>32) {if(!first)first=v;last=v;}
      }
      if(!first)continue;
      CHECK(first->codepoint!=0xff0c && first->codepoint!=0x3002 && first->codepoint!=0xff01 &&
            first->codepoint!=0xff1f && first->codepoint!=0x201d && first->codepoint!=0xff09);
      CHECK(first->codepoint>=128 || !strchr(",.!?:;)",(int)first->codepoint));
      CHECK(last->codepoint!=0x201c && last->codepoint!=0xff08);
    }
    exr_layout_free(l);modes(doc,&c);exr_document_free(doc);
  }
}

int main(int argc, char **argv) {
  scenario = "setup"; CHECK(argc == 3);
  font = open_font(argv[1], "line-boundary.ttf");
  pair_boundaries(); cursive_and_arabic(); pagination(); long_inline_marks(); queue_budget(argv[2]);
  cjk_space_punctuation();
  exr_font_free(font);
  font = open_font(argv[2], "cjk-punctuation.ttf");
  cjk_space_kinsoku_set();cjk_opening_space_text();
  cjk_justification();cjk_punctuation_pair();cjk_punctuation_three();cjk_punctuation_wrap();cjk_punctuation_exclusions();
  simplified_mixed_punctuation();
  exr_font_free(font);
  font = open_font(argv[2], "latin-punctuation.ttf");
  latin_quote_spaces();
  {
    exr_layout_config c=config();
    exr_document *doc=document("\xe2\x80\x94\xe2\x80\x94\xe2\x80\x9c\xe2\x80\x9d","width:100px;margin:0",0);
    exr_layout *l=layout(doc,&c);size_t n,i;const exr_glyph *g=exr_layout_glyphs(l,&n);
    scenario="Latin em dashes and quotes stay unchanged even with em-wide metrics";
    CHECK(n==4);for(i=0;i<n;i++)CHECK(near(g[i].advance,20));
    exr_layout_free(l);modes(doc,&c);exr_document_free(doc);
  }
  exr_font_free(font);
  printf("EXReader line boundaries: %u checks passed\n", checks);
  return 0;
}
