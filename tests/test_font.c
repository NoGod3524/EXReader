/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <limits.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static exr_error error;
static unsigned checks;
static exr_font_input sources[4];
#define CHECK(x) do { checks++; if (!(x)) { \
  fprintf(stderr, "line %d: %s (%d: %s)\n", __LINE__, #x, (int)error.code, error.message); \
  exit(1); } } while (0)
#define OK(x) CHECK((x) == EXR_OK)

static void load(const char *dir, const char *name, exr_font_input *out) {
  char path[4096];
  long size;
  void *bytes;
  FILE *file;
  snprintf(path, sizeof(path), "%s/%s", dir, name);
  file = fopen(path, "rb");
  CHECK(file && !fseek(file, 0, SEEK_END));
  size = ftell(file);
  CHECK(size > 0 && !fseek(file, 0, SEEK_SET));
  bytes = malloc((size_t)size);
  CHECK(bytes && fread(bytes, 1, (size_t)size, file) == (size_t)size);
  CHECK(!fclose(file));
  *out = (exr_font_input){bytes, (size_t)size, 0};
}
static exr_font *create(const exr_font_input *input, size_t count) {
  exr_font *font = NULL;
  OK(exr_font_create(input, count, &font, &error));
  CHECK(font && exr_font_count(font) == count);
  return font;
}
static void reject(const exr_font_input *input, size_t count, exr_status code) {
  exr_font *font = (exr_font *)(uintptr_t)1;
  CHECK(exr_font_create(input, count, &font, &error) == code);
  CHECK(!font && error.code == code && error.message[0]);
}
static exr_document *document(const char *const *parts, size_t count, int table) {
  exr_node_input nodes[32] = {{EXR_NODE_DOCUMENT, SIZE_MAX, NULL, NULL, NULL, 0},
                             {EXR_NODE_CHAPTER, 0, NULL, NULL, NULL, 0}};
  exr_attribute small = {"style", "font-size:20px"}, large = {"style", "font-size:24px"};
  exr_chapter_input chapter = {"font", "font.unit", 1, 1};
  exr_document_input input = {"Fonts", nodes, 0, &chapter, 1, NULL, 0};
  exr_document *doc = NULL;
  size_t base = 3, parent = 2, i;
  nodes[2] = (exr_node_input){EXR_NODE_PARAGRAPH, 1, NULL, NULL, NULL, 0};
  if (table) {
    nodes[2].kind = EXR_NODE_TABLE;
    nodes[3] = (exr_node_input){EXR_NODE_ROW, 2, NULL, NULL, NULL, 0};
    nodes[4] = (exr_node_input){EXR_NODE_CELL, 3, NULL, NULL, NULL, 0};
    nodes[5] = (exr_node_input){EXR_NODE_PARAGRAPH, 4, NULL, NULL, NULL, 0};
    parent = 5;
    base = 6;
  }
  CHECK(count < 12);
  for (i = 0; i < count; i++) {
    nodes[base + 2*i] = (exr_node_input){EXR_NODE_ELEMENT, parent, NULL, NULL,
                                          i % 2 ? &large : &small, 1};
    nodes[base + 2*i+1] = (exr_node_input){EXR_NODE_TEXT, base + 2*i, NULL, parts[i], NULL, 0};
  }
  input.node_count = base + 2*count;
  OK(exr_document_create(&input, &doc, &error));
  return doc;
}
static exr_layout *layout(exr_document *doc, exr_font *font) {
  exr_layout_config config = exr_layout_config_defaults();
  exr_layout *lay = NULL;
  config.page = (exr_layout_options){240, 240, 8, 20, 1, 0};
  OK(exr_layout_create_ex(doc, font, &config, &lay, &error));
  return lay;
}
static void validation(const char *directory) {
  exr_font_input bad, list[33];
  exr_font *font = (exr_font *)(uintptr_t)1;
  char path[4096];
  size_t i;
  reject(NULL, 1, EXR_ARGUMENT);
  reject(sources, 0, EXR_ARGUMENT);
  reject(sources, 33, EXR_LIMIT);
  CHECK(exr_font_create(sources, 1, NULL, &error) == EXR_ARGUMENT);
  bad = sources[0]; bad.data = NULL; reject(&bad, 1, EXR_ARGUMENT);
  bad = sources[0]; bad.size = 0; reject(&bad, 1, EXR_ARGUMENT);
  bad = sources[0]; bad.size = SIZE_MAX; reject(&bad, 1, EXR_LIMIT);
  bad = sources[0]; bad.face_index = UINT_MAX; reject(&bad, 1, EXR_ARGUMENT);
  bad = sources[0]; bad.face_index = 99; reject(&bad, 1, EXR_FONT);
  bad = (exr_font_input){"not a font", 10, 0}; reject(&bad, 1, EXR_FONT);
  list[0] = sources[0]; list[1] = bad; reject(list, 2, EXR_FONT); /* Partial cleanup. */
  list[1] = sources[0]; list[1].size = (size_t)128*1024*1024;
  reject(list, 2, EXR_LIMIT); /* Validate total before reading any oversized buffer. */
  for (i = 0; i < 32; i++) list[i] = sources[0];
  font = create(list, 32);
  CHECK(exr_font_has_glyph(font, 31, 'A'));
  exr_font_free(font);
  list[31] = sources[1];
  font = create(list, 32);
  {
    const char *parts[] = {"a\xcc\x81"};
    exr_document *doc = document(parts, 1, 0);
    exr_layout *lay = layout(doc, font);
    size_t n;
    const exr_glyph *g = exr_layout_glyphs(lay, &n);
    CHECK(n == 2 && g[0].font_index == 31 && g[1].font_index == 31);
    exr_layout_free(lay); exr_document_free(doc);
  }
  exr_font_free(font);
  CHECK(!exr_font_count(NULL) && !exr_font_has_glyph(NULL, 0, 'A'));
  font = create(sources, 2);
  CHECK(exr_font_has_glyph(font, 0, 'a') && !exr_font_has_glyph(font, 0, 0x301));
  CHECK(exr_font_has_glyph(font, 1, 0x301) && exr_font_has_glyph(font, 1, 0x1f600));
  CHECK(!exr_font_has_glyph(font, 2, 'A') && !exr_font_has_glyph(font, SIZE_MAX, 'A'));
  CHECK(!exr_font_has_glyph(font, 0, 0xd800) && !exr_font_has_glyph(font, 0, 0x110000));
  exr_font_free(font);
  CHECK(exr_font_open(NULL, &font, &error) == EXR_ARGUMENT && !font);
  CHECK(exr_font_open("missing-font.ttf", &font, &error) == EXR_IO && !font);
  snprintf(path, sizeof(path), "%s/primary.ttf", directory);
  OK(exr_font_open(path, &font, &error));
  CHECK(exr_font_count(font) == 1 && exr_font_has_glyph(font, 0, 'A'));
  exr_font_free(font);
  bad = sources[3]; bad.face_index = 1;
  font = create(&bad, 1);
  CHECK(exr_font_has_glyph(font, 0, 0x7532));
  exr_font_free(font);
  bad.face_index = 2; reject(&bad, 1, EXR_FONT);
}
static void selection(void) {
  const char *parts[] = {"A\xe7\x94\xb2V\xf0\x9f\x98\x80\xce\xa9"};
  const char *accent[] = {"a", "\xcc\x81"};
  const char *hidden[] = {"A\xe2\x80\x8d"};
  exr_font *font = create(sources, 2);
  exr_document *doc = document(parts, 1, 0);
  exr_layout *lay = layout(doc, font);
  size_t n, i;
  const exr_glyph *g = exr_layout_glyphs(lay, &n);
  const exr_line *lines;
  CHECK(n == 5);
  CHECK(g[0].font_index == 0 && g[1].font_index == 1 && g[2].font_index == 0 &&
        g[3].font_index == 1 && g[4].font_index == 0);
  for (i = 0; i < 4; i++) CHECK(g[i].glyph && !(g[i].flags & EXR_GLYPH_MISSING));
  CHECK(!g[4].glyph && (g[4].flags & EXR_GLYPH_MISSING));
  CHECK(fabsf(g[1].x - g[0].x - g[0].advance) < 0.01f); /* No cross-face A/V kerning. */
  CHECK(fabsf(g[2].x - g[1].x - g[1].advance) < 0.01f);
  CHECK(g[0].advance == 10 && g[1].advance == 18);
  lines = exr_layout_lines(lay, &n);
  CHECK(n == 1 && lines[0].height >= 32); /* Actual fallback ascent/descent. */
  exr_layout_free(lay); exr_document_free(doc);
  doc = document(accent, 2, 0); lay = layout(doc, font);
  g = exr_layout_glyphs(lay, &n);
  CHECK(n == 2 && g[0].font_index == 1 && g[1].font_index == 1);
  CHECK(g[0].cluster_start == 0 && g[0].cluster_end == 3 && g[1].cluster_end == 3);
  CHECK(g[0].size == 20 && g[1].size == 24 && g[1].advance == 0);
  exr_layout_free(lay); exr_document_free(doc);
  doc = document(hidden, 1, 0); lay = layout(doc, font);
  g = exr_layout_glyphs(lay, &n);
  CHECK(n == 2 && !g[0].font_index && !g[1].font_index);
  CHECK((g[1].flags & EXR_GLYPH_HIDDEN) && !(g[1].flags & EXR_GLYPH_MISSING));
  exr_layout_free(lay); exr_document_free(doc);
  {
    const char *word[] = {"AV"};
    doc = document(word, 1, 0); lay = layout(doc, font);
    g = exr_layout_glyphs(lay, &n);
    CHECK(n == 2 && fabsf(g[1].x - g[0].x - 8) < 0.01f); /* Primary kerning -2px. */
    exr_layout_free(lay); exr_document_free(doc);
  }
  exr_font_free(font);
  {
    exr_font_input split[] = {sources[0], sources[2]};
    font = create(split, 2);
    doc = document(accent, 2, 0); lay = layout(doc, font);
    g = exr_layout_glyphs(lay, &n);
    CHECK(n == 2 && !g[0].font_index && g[1].font_index == 1);
    CHECK(!(g[0].flags & EXR_GLYPH_MISSING) && !(g[1].flags & EXR_GLYPH_MISSING));
    exr_layout_free(lay); exr_document_free(doc); exr_font_free(font);
  }
  {
    exr_font_input reverse[] = {sources[1], sources[0]};
    font = create(reverse, 2);
    doc = document(parts, 1, 0); lay = layout(doc, font);
    g = exr_layout_glyphs(lay, &n);
    CHECK(!g[0].font_index && !g[1].font_index && g[0].advance == 18);
    exr_layout_free(lay); exr_document_free(doc); exr_font_free(font);
  }
}
static void rendering(void) {
  const char *part[] = {"\xe7\x94\xb2"};
  exr_font *stack = create(sources, 2), *direct = create(sources + 1, 1);
  exr_document *doc = document(part, 1, 0);
  exr_layout *a = layout(doc, stack), *b = layout(doc, direct);
  exr_bitmap ba = {0}, bb = {0};
  size_t i, ink = 0;
  exr_document_free(doc); /* Layout owns all required text placement. */
  OK(exr_render_page(a, stack, 0, &ba, &error));
  OK(exr_render_page(b, direct, 0, &bb, &error));
  CHECK(ba.width == bb.width && ba.height == bb.height && ba.stride == bb.stride);
  CHECK(!memcmp(ba.pixels, bb.pixels, (size_t)ba.stride*ba.height));
  for (i = 0; i < (size_t)ba.stride*ba.height; i++) if (ba.pixels[i] < 200) ink++;
  CHECK(ink > 100);
  exr_bitmap_free(&ba); exr_bitmap_free(&bb);
  OK(exr_render_page_color(a, stack, 0, &ba, &error));
  OK(exr_render_page_color(b, direct, 0, &bb, &error));
  CHECK(!memcmp(ba.pixels, bb.pixels, (size_t)ba.stride*ba.height));
  exr_bitmap_free(&ba); exr_bitmap_free(&bb);
  CHECK(exr_render_page(a, direct, 0, &ba, &error) == EXR_FONT && !ba.pixels);
  exr_layout_free(a); exr_layout_free(b);
  doc = document(part, 1, 1); a = layout(doc, stack);
  {
    size_t n;
    const exr_glyph *g = exr_layout_glyphs(a, &n);
    CHECK(n == 1 && g[0].font_index == 1 && g[0].glyph);
  }
  OK(exr_render_page(a, stack, 0, &ba, &error));
  exr_bitmap_free(&ba); exr_layout_free(a); exr_document_free(doc);
  exr_font_free(stack); exr_font_free(direct);
}
static void copied_inputs(void) {
  exr_font_input input = sources[1];
  void *copy = malloc(input.size);
  exr_font *font;
  CHECK(copy);
  memcpy(copy, input.data, input.size); input.data = copy;
  font = create(&input, 1);
  memset(copy, 0, input.size); free(copy);
  CHECK(exr_font_has_glyph(font, 0, 0x7532));
  {
    const char *part[] = {"\xe7\x94\xb2"};
    exr_document *doc = document(part, 1, 0);
    exr_layout *lay = layout(doc, font);
    exr_bitmap bitmap = {0};
    OK(exr_render_page(lay, font, 0, &bitmap, &error));
    exr_bitmap_free(&bitmap); exr_layout_free(lay); exr_document_free(doc);
  }
  exr_font_free(font);
}
static exr_status load_part(void *context, size_t part, exr_document **out, exr_error *e) {
  const char text[] = "A\xe7\x94\xb2";
  unsigned *calls = context;
  (void)part;
  (*calls)++;
  return exr_document_open_memory(EXR_TXT, text, sizeof(text)-1, out, e);
}
static void session_and_pages(void) {
  exr_font *font = create(sources, 2);
  exr_part part = {"one", "one.txt", "One", 1};
  unsigned calls = 0;
  exr_publication_input input = {"Fonts", &part, 1, load_part, &calls, NULL, NULL, 0};
  exr_publication *publication = NULL;
  exr_session *session = NULL;
  const exr_document *doc;
  const exr_layout *lay, *cached;
  const exr_glyph *g;
  exr_bitmap bitmap = {0};
  size_t n;
  OK(exr_publication_create(&input, &publication, &error));
  OK(exr_session_create(publication, font, NULL, 1, &session, &error));
  exr_publication_free(publication);
  OK(exr_session_get(session, 0, &doc, &lay, &error));
  g = exr_layout_glyphs(lay, &n);
  CHECK(n == 2 && !g[0].font_index && g[1].font_index == 1);
  OK(exr_render_page_color(lay, font, 0, &bitmap, &error));
  exr_bitmap_free(&bitmap);
  OK(exr_session_get(session, 0, &doc, &cached, &error));
  CHECK(cached == lay && calls == 1);
  exr_session_free(session);
  {
    const char *parts[] = {"\xe4\xb9\x99\xe4\xb9\x99\xe4\xb9\x99\xe4\xb9\x99"};
    exr_document *book = document(parts, 1, 0);
    exr_layout *pages = NULL;
    exr_layout_config config = exr_layout_config_defaults();
    config.page = (exr_layout_options){48, 48, 4, 20, 1, 0};
    OK(exr_layout_create_ex(book, font, &config, &pages, &error));
    exr_layout_pages(pages, &n);
    CHECK(n == 2); /* Two 18px glyphs fit; fallback needs 32px per line/page. */
    g = exr_layout_glyphs(pages, &n);
    CHECK(n == 4 && !g[0].page && g[2].page == 1);
    exr_layout_free(pages); exr_document_free(book);
  }
  exr_font_free(font);
}
static void variation_sequences(const char *dir) {
  const char *texts[]={"A\xef\xb8\x8f","A\xef\xb8\x8e","a\xef\xb8\x8f","\xe7\x94\xb2\xf3\xa0\x84\x80","\xe7\x94\xb2\xf3\xa0\x84\x81","\xe4\xb8\x80\xf3\xa0\x84\x80"};
  const uint32_t ids[]={3,2,4,6,3,6}; const float advances[]={70,90,50,110,70,110};
  exr_font_input input={0}; exr_font *font; exr_shape_options options=exr_shape_defaults(); exr_shaped_glyph *shaped=NULL; size_t i,n;
  load(dir,"uvs.ttf",&input); font=create(&input,1); free((void *)input.data); options.font_size=100;
  CHECK(exr_font_has_glyph(font,0,'A') && !exr_font_has_glyph(font,0,0xfe0f));
  for(i=0;i<6;i++) {
    OK(exr_shape(font,0,texts[i],strlen(texts[i]),&options,&shaped,&n,&error));
    CHECK(n==1 && shaped[0].glyph==ids[i] && !shaped[0].start && shaped[0].end==strlen(texts[i]) && fabsf(shaped[0].advance_x-advances[i])<.02f && !(shaped[0].flags&(EXR_GLYPH_HIDDEN|EXR_GLYPH_MISSING))); exr_free(shaped);
  }
  OK(exr_shape(font,0,"A\xef\xb8\x8d",4,&options,&shaped,&n,&error));
  CHECK(n==2 && shaped[0].glyph==2 && (shaped[1].flags&EXR_GLYPH_HIDDEN) && !shaped[1].advance_x && shaped[0].end==4 && shaped[1].end==4); exr_free(shaped);
  OK(exr_shape(font,0,"A\xef\xb8\x8f\xef\xb8\x8f",7,&options,&shaped,&n,&error));
  CHECK(n==2 && shaped[0].glyph==3 && (shaped[1].flags&EXR_GLYPH_HIDDEN) && !shaped[1].advance_x && shaped[0].end==7); exr_free(shaped);
  OK(exr_shape(font,0,"\xef\xb8\x8f",3,&options,&shaped,&n,&error)); CHECK(n==1 && (shaped[0].flags&EXR_GLYPH_HIDDEN)); exr_free(shaped);
  OK(exr_shape_vertical(font,0,texts[3],strlen(texts[3]),&options,&shaped,&n,&error)); CHECK(n==1 && shaped[0].glyph==6 && shaped[0].advance_y==-100); exr_free(shaped);
  { const char *parts[]={"A","\xef\xb8\x8f"}; exr_document *doc=document(parts,2,0); exr_layout *lay=layout(doc,font); const exr_glyph *g=exr_layout_glyphs(lay,&n); exr_bitmap image={0};
    CHECK(n==1 && g[0].glyph==3 && g[0].cluster_start==0 && g[0].cluster_end==4);
    exr_document_free(doc); exr_font_free(font); OK(exr_render_page_color(lay,NULL,0,&image,&error)); exr_bitmap_free(&image); exr_layout_free(lay);
  }
  { exr_document *doc=NULL; exr_pager *pager=NULL; exr_layout *whole=NULL; exr_layout_config config=exr_layout_config_defaults(); size_t count;
    char text[121]; for(i=0;i<30;i++) memcpy(text+i*4,texts[0],4); text[120]=0;
    load(dir,"uvs.ttf",&input); font=create(&input,1); free((void *)input.data);
    OK(exr_document_open_memory(EXR_TXT,text,120,&doc,&error)); config.page=(exr_layout_options){80,80,0,20,1,0}; config.user_css="p {margin:0}";
    OK(exr_layout_create_ex(doc,font,&config,&whole,&error)); exr_layout_pages(whole,&count); CHECK(count>=2);
    OK(exr_pager_create(doc,font,&config,&pager,&error));
    for(i=0;i<count;i++) { exr_layout *part=NULL; exr_bitmap a={0},b={0}; const exr_glyph *g;
      OK(exr_pager_next(pager,&part,&error)); CHECK(part); g=exr_layout_glyphs(part,&n); CHECK(n);
      for(size_t j=0;j<n;j++) CHECK(g[j].glyph==3 && g[j].cluster_end-g[j].cluster_start==4);
      OK(exr_render_page_color(whole,NULL,i,&a,&error)); OK(exr_render_page_color(part,NULL,0,&b,&error));
      CHECK(a.width==b.width && a.height==b.height && !memcmp(a.pixels,b.pixels,(size_t)a.stride*a.height)); exr_bitmap_free(&a); exr_bitmap_free(&b); exr_layout_free(part);
    }
    { exr_layout *part=NULL; OK(exr_pager_next(pager,&part,&error)); CHECK(!part); }
    exr_pager_free(pager); exr_layout_free(whole); exr_document_free(doc); exr_font_free(font);
  }
  { exr_font_input inputs[2]={sources[0],{0}}; const char *parts[]={"A\xef\xb8\x8f A\xef\xb8\x8d A"}; exr_document *doc; exr_layout *lay; const exr_glyph *g;
    load(dir,"uvs.ttf",&inputs[1]); font=create(inputs,2); free((void *)inputs[1].data);
    doc=document(parts,1,0); lay=layout(doc,font); g=exr_layout_glyphs(lay,&n);
    CHECK(n==6 && g[0].font_index==1 && g[0].glyph==3 && g[2].font_index==0 && g[2].glyph==2 && (g[3].flags&EXR_GLYPH_HIDDEN) && !g[5].font_index);
    exr_layout_free(lay); exr_document_free(doc);
    parts[0]=texts[5]; doc=document(parts,1,0); lay=layout(doc,font); g=exr_layout_glyphs(lay,&n);
    CHECK(n==1 && g[0].font_index==1 && g[0].glyph==6 && !(g[0].flags&EXR_GLYPH_MISSING));
    exr_layout_free(lay); exr_document_free(doc); exr_font_free(font);
  }
}
int main(int argc, char **argv) {
  size_t i;
  if (argc != 2) return 2;
  load(argv[1], "primary.ttf", &sources[0]); load(argv[1], "fallback.ttf", &sources[1]);
  load(argv[1], "marks.ttf", &sources[2]); load(argv[1], "collection.ttc", &sources[3]);
  validation(argv[1]); selection(); rendering(); copied_inputs(); session_and_pages(); variation_sequences(argv[1]);
  for (i = 0; i < 4; i++) free((void *)sources[i].data);
  printf("%u font fallback checks passed\n", checks);
  return 0;
}
