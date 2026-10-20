/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "fixtures/wp7/reference.h"

static exr_error error;
static unsigned checks;
static const char *fixtures;
#define CHECK(x) do { checks++; if (!(x)) {   fprintf(stderr, "line %d: %s (%d: %s)\n", __LINE__, #x, (int)error.code, error.message);   exit(1); } } while (0)
#define OK(x) CHECK((x) == EXR_OK)
#define TOL 1.5f

typedef struct { char name[64]; exr_font *font; } cached_font;
static cached_font cache[32];
static size_t cache_count;

static exr_font *open_font(const char *name) {
  char path[4096];
  size_t i;
  for (i = 0; i < cache_count; i++) if (!strcmp(cache[i].name, name)) return cache[i].font;
  CHECK(cache_count < sizeof(cache)/sizeof(*cache));
  snprintf(path, sizeof(path), "%s/fonts/%s", fixtures, name);
  OK(exr_font_open(path, &cache[cache_count].font, &error));
  snprintf(cache[cache_count].name, sizeof(cache[cache_count].name), "%s", name);
  return cache[cache_count++].font;
}

static int near(float a, float b) { return isfinite(a) && fabsf(a-b) <= TOL; }

static void reference_cases(void) {
  size_t c, total = 0;
  for (c = 0; c < sizeof(wp7_reference)/sizeof(*wp7_reference); c++) {
    const wp7_case *r = &wp7_reference[c];
    exr_font *font = open_font(r->font);
    exr_shape_options o = exr_shape_defaults();
    exr_shaped_glyph *g = NULL;
    size_t n = 0, i, visible = 0, previous = 0;
    o.font_size = 200.0f;
    o.direction = EXR_DIRECTION_LTR;
    o.script = EXR_TAG(r->script[0], r->script[1], r->script[2], r->script[3]);
    OK(exr_shape(font, 0, r->text, r->size, &o, &g, &n, &error));
    for (i = 0; i < n; i++) {
      size_t k;
      if (g[i].flags & EXR_GLYPH_HIDDEN) continue;
      CHECK(visible < r->count);
      CHECK(g[i].glyph == r->glyphs[visible].glyph);
      CHECK(g[i].start <= g[i].end && g[i].end <= r->size);
      CHECK(g[i].start >= previous); previous = g[i].start;
      CHECK(g[i].start <= r->glyphs[visible].cluster_start &&
            (r->glyphs[visible].cluster_start < g[i].end ||
             (g[i].end == r->size && r->glyphs[visible].cluster_start == g[i].end)));
      CHECK(near(g[i].advance_x, r->glyphs[visible].ax));
      CHECK(near(g[i].advance_y, r->glyphs[visible].ay));
      CHECK(near(g[i].offset_x, r->glyphs[visible].x));
      CHECK(near(g[i].offset_y, r->glyphs[visible].y));
      for (k = i+1; k < n; k++)
        if (!(g[k].flags & EXR_GLYPH_HIDDEN) && g[k].start < g[i].start) CHECK(0);
      visible++; total++;
    }
    CHECK(visible == r->count);
    exr_free(g);
  }
  CHECK(total > 700);
}

static int cancel(void *context) { unsigned *calls = context; return ++*calls > 4; }

static void controls(void) {
  static const struct { const char *script, *font, *sample; } cases[] = {
    {"beng","beng-synthetic.ttf","\xe0\xa6\x95"},
    {"taml","taml-synthetic.ttf","\xe0\xae\x95"},
    {"telu","telu-synthetic.ttf","\xe0\xb0\x95"},
    {"knda","knda-synthetic.ttf","\xe0\xb2\x95"},
    {"mlym","mlym-synthetic.ttf","\xe0\xb4\x95"},
    {"thai","thai-synthetic.ttf","\xe0\xb8\x81"},
    {"khmr","khmr-synthetic.ttf","\xe1\x9e\x80"},
    {"mymr","mymr-synthetic.ttf","\xe1\x80\x80"}
  };
  size_t k;
  for (k = 0; k < sizeof(cases)/sizeof(*cases); k++) {
    exr_font *font = open_font(cases[k].font);
    exr_shape_options o = exr_shape_defaults();
    exr_shaped_glyph *g = (void *)(uintptr_t)1;
    size_t n = 99, i, size = 3*20000;
    char *text = malloc(size);
    unsigned calls = 0;
    CHECK(text);
    for (i = 0; i < 20000; i++) memcpy(text+3*i, cases[k].sample, 3);
    o.script = EXR_TAG(cases[k].script[0],cases[k].script[1],cases[k].script[2],cases[k].script[3]);
    o.control.cancelled = cancel; o.control.context = &calls;
    CHECK(exr_shape(font,0,text,size,&o,&g,&n,&error) == EXR_CANCELLED && !g && !n && calls > 4);
    o = exr_shape_defaults(); g = (void *)(uintptr_t)1; n = 99;
    CHECK(exr_shape(font,0,"\xff",1,&o,&g,&n,&error) == EXR_ENCODING && !g && !n);
    g = (void *)(uintptr_t)1; n = 99;
    CHECK(exr_shape(font,0,"A",(size_t)64*1024*1024+1,&o,&g,&n,&error) == EXR_LIMIT && !g && !n);
    g = (void *)(uintptr_t)1; n = 99;
    CHECK(exr_shape(font,0,NULL,1,&o,&g,&n,&error) == EXR_ARGUMENT && !g && !n);
    g = (void *)(uintptr_t)1; n = 99;
    OK(exr_shape(font,0,NULL,0,&o,&g,&n,&error)); CHECK(!g && !n);
    free(text);
  }
}

static void bidi_and_breaks(void) {
  const char mixed[] = "\xd8\xa8"                 /* Arabic beh */
                       "\xe0\xa6\x95\xe0\xa6\xbf"  /* Bengali ki */
                       "\xe0\xb8\x81\xe0\xb8\xb3"  /* Thai ko + sara am */
                       "\xe0\xa4\x95\xe0\xa4\xbf"  /* Devanagari ki */
                       "A";
  size_t size = sizeof(mixed)-1, count = 0, i, n = 0;
  unsigned char *boundaries = NULL;
  exr_bidi *bidi = NULL;
  const exr_bidi_scalar *scalars;
  size_t *order = NULL;
  OK(exr_text_analyze(mixed,size,&boundaries,&error));
  CHECK(boundaries[size] & EXR_BOUNDARY_GRAPHEME);
  CHECK(boundaries[size] & EXR_BOUNDARY_MANDATORY);
  CHECK(boundaries[size] & EXR_BOUNDARY_LINE);
  OK(exr_bidi_analyze(mixed,size,EXR_DIRECTION_AUTO,&bidi,&error));
  scalars = exr_bidi_scalars(bidi,&count);
  CHECK(count > 5 && scalars);
  OK(exr_bidi_reorder(bidi,0,count,&order,&n,&error));
  CHECK(n > 0 && order);
  exr_free(order); exr_bidi_free(bidi); exr_free(boundaries);
  {
    const char conjunct[] = "\xe0\xa6\x95\xe0\xa7\x8d\xe0\xa6\xb7";
    size_t len = sizeof(conjunct)-1;
    OK(exr_text_analyze(conjunct,len,&boundaries,&error));
    CHECK(boundaries[len] & EXR_BOUNDARY_GRAPHEME);
    CHECK(!(boundaries[3] & EXR_BOUNDARY_GRAPHEME));
    exr_free(boundaries);
  }
  (void)i;
}

static void fallback_and_selection(void) {
  const char *names[] = {"beng-real.ttf","thai-real.ttf"};
  exr_font_input inputs[2];
  unsigned char *data[2] = {NULL,NULL};
  size_t sizes[2] = {0,0}, i;
  exr_font *font = NULL;
  for (i = 0; i < 2; i++) {
    char path[4096]; FILE *f;
    snprintf(path,sizeof(path),"%s/fonts/%s",fixtures,names[i]);
    f = fopen(path,"rb"); CHECK(f);
    fseek(f,0,SEEK_END); sizes[i] = (size_t)ftell(f); fseek(f,0,SEEK_SET);
    data[i] = malloc(sizes[i]); CHECK(data[i]);
    CHECK(fread(data[i],1,sizes[i],f) == sizes[i]); fclose(f);
    inputs[i].data = data[i]; inputs[i].size = sizes[i]; inputs[i].face_index = 0;
  }
  OK(exr_font_create(inputs,2,&font,&error));
  CHECK(exr_font_count(font) == 2);
  CHECK(exr_font_has_glyph(font,0,0x0995));
  CHECK(exr_font_has_glyph(font,1,0x0E01));
  CHECK(!exr_font_has_glyph(font,1,0x0995));
  {
    exr_shape_options o = exr_shape_defaults(); exr_shaped_glyph *g = NULL; size_t n = 0;
    o.font_size = 200; o.script = EXR_TAG('b','e','n','g');
    OK(exr_shape(font,0,"\xe0\xa6\x95\xe0\xa6\xbf",6,&o,&g,&n,&error));
    CHECK(n >= 1); exr_free(g);
    o.script = EXR_TAG('t','h','a','i');
    OK(exr_shape(font,1,"\\xe0\\xb8\\x81\xe0\xb8\xb3",6,&o,&g,&n,&error));
    CHECK(n >= 1);
    for (i = 0; i < n; i++) { CHECK(g[i].start < g[i].end); if (i) CHECK(g[i].start >= g[i-1].start); }
    exr_free(g);
  }
  exr_font_free(font);
  for (i = 0; i < 2; i++) free(data[i]);
}

static void pagination_recovery(void) {
  exr_document *doc = NULL; exr_pager *pager = NULL; exr_layout *page = NULL;
  exr_layout_config config = exr_layout_config_defaults();
  char text[8192]; size_t at = 0, i, pages = 0, *starts = NULL;
  exr_node_input nodes[] = {{EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0},
    {EXR_NODE_CHAPTER,0,NULL,NULL,NULL,0},{EXR_NODE_PARAGRAPH,1,"p",NULL,NULL,0},
    {EXR_NODE_TEXT,2,NULL,text,NULL,0}};
  exr_chapter_input chapter = {"main","main",1,1};
  exr_document_input input = {"WP7 pagination",nodes,4,&chapter,1,NULL,0};
  for (i = 0; i < 150; i++) {
    const char *word = "\xe0\xa6\xb0\xe0\xa6\x95\xe0\xa6\xbf ";
    memcpy(text+at,word,strlen(word)); at += strlen(word);
  }
  text[at] = 0;
  OK(exr_document_create(&input,&doc,&error));
  config.page.width = 120; config.page.height = 160; config.page.margin = 10; config.page.font_size = 18;
  OK(exr_pager_create(doc,open_font("beng-real.ttf"),&config,&pager,&error));
  starts = malloc(sizeof(*starts)*256);
  CHECK(starts);
  for (;;) {
    size_t n; const exr_glyph *g;
    OK(exr_pager_next(pager,&page,&error)); if (!page) break;
    CHECK(pages < 256);
    g = exr_layout_glyphs(page,&n); CHECK(n);
    starts[pages] = g[0].start;
    for (i = 0; i < n; i++) CHECK(g[i].start <= g[i].cluster_start && g[i].cluster_end <= at);
    pages++; exr_layout_free(page); page = NULL;
  }
  CHECK(pages > 1);
  exr_pager_free(pager); pager = NULL;
  OK(exr_pager_create(doc,open_font("beng-real.ttf"),&config,&pager,&error));
  OK(exr_pager_set_cache(pager,4,256*1024,&error));
  OK(exr_pager_set_checkpoints(pager,8,256*1024,4,&error));
  for (i = 0; i < pages; i++) {
    const exr_layout *got = NULL; const exr_glyph *g; size_t n;
    OK(exr_pager_get(pager,(i*7+3)%pages,&got,&error)); CHECK(got);
    g = exr_layout_glyphs(got,&n); CHECK(n);
    CHECK(g[0].start == starts[(i*7+3)%pages]);
  }
  free(starts); exr_pager_free(pager); exr_document_free(doc);
}

int main(int argc, char **argv) {
  size_t i;
  CHECK(argc == 2); fixtures = argv[1];
  reference_cases();
  controls();
  bidi_and_breaks();
  fallback_and_selection();
  pagination_recovery();
  for (i = 0; i < cache_count; i++) exr_font_free(cache[i].font);
  printf("EXReader WP7 scripts: %u checks passed\n", checks);
  return 0;
}
