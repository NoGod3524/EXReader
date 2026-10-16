/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static exr_error error;
static unsigned checks;
static exr_font *font;
#define CHECK(x) do { checks++; if (!(x)) { \
  fprintf(stderr, "line %d: %s (%d: %s)\n", __LINE__, #x, (int)error.code, error.message); \
  exit(1); } } while (0)
#define OK(x) CHECK((x) == EXR_OK)

static void same_page(const exr_layout *actual, const exr_layout *expected) {
  size_t count, expected_count, i;
  const exr_page *a = exr_layout_pages(actual, &count);
  const exr_page *b = exr_layout_pages(expected, &expected_count);
  const exr_glyph *ga, *gb;
  exr_bitmap ba = {0}, bb = {0};
  CHECK(count == 1 && expected_count == 1);
  CHECK(a->start == b->start && a->end == b->end && a->line_count == b->line_count);
  ga = exr_layout_glyphs(actual, &count);
  gb = exr_layout_glyphs(expected, &expected_count);
  CHECK(count == expected_count);
  for (i = 0; i < count; i++) {
    CHECK(ga[i].start == gb[i].start && ga[i].end == gb[i].end);
    CHECK(ga[i].codepoint == gb[i].codepoint && ga[i].glyph == gb[i].glyph);
    CHECK(ga[i].x == gb[i].x && ga[i].baseline == gb[i].baseline && !ga[i].page);
  }
  OK(exr_render_page(actual, font, 0, &ba, &error));
  OK(exr_render_page(expected, font, 0, &bb, &error));
  CHECK(ba.width == bb.width && ba.height == bb.height && ba.stride == bb.stride);
  CHECK(!memcmp(ba.pixels, bb.pixels, (size_t)ba.stride * ba.height));
  exr_bitmap_free(&ba);
  exr_bitmap_free(&bb);
}

static exr_document *document(void) {
  const char *style = "margin:0;page-break-before:always;line-height:20px";
  exr_attribute attrs[5];
  exr_node_input nodes[12] = {
      {EXR_NODE_DOCUMENT, SIZE_MAX, NULL, NULL, NULL, 0},
      {EXR_NODE_CHAPTER, 0, NULL, NULL, NULL, 0}};
  char large[513];
  exr_chapter_input chapter = {"pages", "pages.unit", 1, 1};
  exr_document_input input = {"Page cache", nodes, 12, &chapter, 1, NULL, 0};
  exr_document *doc = NULL;
  size_t i;
  memset(large, 'A', sizeof(large) - 1);
  large[sizeof(large) - 1] = 0;
  for (i = 0; i < 5; i++) {
    size_t n = 2 + 2 * i;
    attrs[i] = (exr_attribute){"style", style};
    nodes[n] = (exr_node_input){EXR_NODE_PARAGRAPH, 1, NULL, NULL, &attrs[i], 1};
    nodes[n + 1] = (exr_node_input){EXR_NODE_TEXT, n, NULL, i == 2 ? large : "AAAA", NULL, 0};
  }
  OK(exr_document_create(&input, &doc, &error));
  return doc;
}

static void modes(exr_document *doc, const exr_layout_config *config) {
  exr_pager *pager = NULL;
  exr_layout *owned = (exr_layout *)(uintptr_t)1;
  const exr_layout *borrowed = (const exr_layout *)(uintptr_t)1;
  CHECK(!exr_pager_cached_count(NULL) && !exr_pager_cached_bytes(NULL));
  CHECK(exr_pager_set_cache(NULL, 1, 0, &error) == EXR_ARGUMENT);
  CHECK(exr_pager_get(NULL, 0, &borrowed, &error) == EXR_ARGUMENT && !borrowed);
  OK(exr_pager_create(doc, font, config, &pager, &error));
  CHECK(exr_pager_set_cache(pager, 0, 0, &error) == EXR_ARGUMENT);
  CHECK(exr_pager_set_cache(pager, 65, 0, &error) == EXR_ARGUMENT);
  OK(exr_pager_next(pager, &owned, &error));
  CHECK(owned && !exr_pager_cached_count(pager));
  CHECK(exr_pager_get(pager, 0, &borrowed, &error) == EXR_ARGUMENT && !borrowed);
  CHECK(exr_pager_set_cache(pager, 1, 0, &error) == EXR_ARGUMENT);
  exr_layout_free(owned);
  exr_pager_free(pager);
  OK(exr_pager_create(doc, font, config, &pager, &error));
  OK(exr_pager_set_cache(pager, 2, 0, &error));
  CHECK(exr_pager_next(pager, &owned, &error) == EXR_ARGUMENT && !owned);
  CHECK(exr_pager_get(pager, 0, NULL, &error) == EXR_ARGUMENT);
  OK(exr_pager_get(pager, 0, &borrowed, &error));
  CHECK(borrowed && exr_pager_cached_count(pager) == 1);
  CHECK(exr_pager_next(pager, &owned, &error) == EXR_ARGUMENT && !owned);
  exr_pager_free(pager);
}

static void continuation(exr_document *doc, const exr_layout_config *config,
                           exr_layout *const *expected) {
  exr_pager *pager = NULL;
  const exr_layout *page = NULL, *first;
  size_t before, bytes;
  OK(exr_pager_create(doc, font, config, &pager, &error));
  OK(exr_pager_get(pager, 0, &page, &error));
  first = page;
  bytes = exr_layout_memory_size(page);
  CHECK(exr_pager_cached_count(pager) == 1 && exr_pager_cached_bytes(pager) == bytes);
  same_page(page, expected[0]);
  before = exr_pager_position(pager);
  OK(exr_pager_get(pager, 0, &page, &error));
  CHECK(page == first && exr_pager_position(pager) == before);
  CHECK(exr_pager_cached_bytes(pager) == bytes);
  OK(exr_pager_get(pager, 1, &page, &error));
  CHECK(exr_pager_position(pager) > before && exr_pager_cached_count(pager) == 1);
  same_page(page, expected[1]);
  OK(exr_pager_get(pager, 3, &page, &error));
  same_page(page, expected[3]);
  before = exr_pager_position(pager);
  OK(exr_pager_get(pager, 0, &page, &error));
  CHECK(exr_pager_position(pager) < before);
  same_page(page, expected[0]);
  first = page;
  bytes = exr_pager_cached_bytes(pager);
  CHECK(exr_pager_get(pager, 5, &page, &error) == EXR_ARGUMENT && !page);
  CHECK(exr_pager_cached_count(pager) == 1 && exr_pager_cached_bytes(pager) == bytes);
  same_page(first, expected[0]);
  before = exr_pager_position(pager);
  OK(exr_pager_get(pager, 0, &page, &error));
  CHECK(page == first && exr_pager_position(pager) == before);
  OK(exr_pager_get(pager, 2, &page, &error));
  same_page(page, expected[2]);
  exr_pager_free(pager);
}

static void budgets(exr_document *doc, const exr_layout_config *config,
                      exr_layout *const *expected) {
  exr_pager *pager = NULL;
  const exr_layout *page = NULL, *first, *second;
  size_t small = exr_layout_memory_size(expected[0]);
  size_t other = exr_layout_memory_size(expected[1]);
  size_t large = exr_layout_memory_size(expected[2]);
  size_t third = exr_layout_memory_size(expected[3]), before;
  CHECK(large > small + other && small == other && small == third);
  OK(exr_pager_create(doc, font, config, &pager, &error));
  OK(exr_pager_set_cache(pager, 3, 0, &error));
  OK(exr_pager_get(pager, 0, &page, &error));
  first = page;
  OK(exr_pager_get(pager, 1, &page, &error));
  OK(exr_pager_get(pager, 3, &page, &error));
  CHECK(exr_pager_cached_count(pager) == 3 && exr_pager_cached_bytes(pager) == small + other + third);
  OK(exr_pager_get(pager, 0, &page, &error));
  CHECK(page == first);
  OK(exr_pager_set_cache(pager, 2, 0, &error));
  CHECK(exr_pager_cached_count(pager) == 2 && exr_pager_cached_bytes(pager) == small + third);
  OK(exr_pager_set_cache(pager, 2, small, &error));
  CHECK(exr_pager_cached_count(pager) == 1 && exr_pager_cached_bytes(pager) == small);
  OK(exr_pager_get(pager, 0, &page, &error));
  CHECK(page == first);
  OK(exr_pager_set_cache(pager, 2, small - 1, &error));
  CHECK(!exr_pager_cached_count(pager) && !exr_pager_cached_bytes(pager));
  CHECK(exr_pager_get(pager, 0, &page, &error) == EXR_LIMIT && !page);
  CHECK(!exr_pager_cached_bytes(pager));
  OK(exr_pager_set_cache(pager, 2, small + other, &error));
  OK(exr_pager_get(pager, 0, &page, &error));
  first = page;
  OK(exr_pager_get(pager, 1, &page, &error));
  second = page;
  CHECK(exr_pager_cached_count(pager) == 2 && exr_pager_cached_bytes(pager) == small + other);
  OK(exr_pager_get(pager, 0, &page, &error));
  CHECK(page == first);
  CHECK(exr_pager_get(pager, 2, &page, &error) == EXR_LIMIT && !page);
  CHECK(exr_pager_cached_count(pager) == 2 && exr_pager_cached_bytes(pager) == small + other);
  same_page(first, expected[0]);
  same_page(second, expected[1]);
  /* The failed request did not change LRU: page 1 is still the oldest entry. */
  OK(exr_pager_get(pager, 3, &page, &error));
  same_page(page, expected[3]);
  before = exr_pager_position(pager);
  OK(exr_pager_get(pager, 0, &page, &error));
  CHECK(page == first && exr_pager_position(pager) == before);
  OK(exr_pager_set_cache(pager, 2, 0, &error));
  OK(exr_pager_get(pager, 2, &page, &error));
  same_page(page, expected[2]);
  first = page;
  OK(exr_pager_set_cache(pager, 1, large, &error));
  CHECK(exr_pager_cached_count(pager) == 1 && exr_pager_cached_bytes(pager) == large);
  OK(exr_pager_get(pager, 2, &page, &error));
  CHECK(page == first);
  OK(exr_pager_set_cache(pager, 1, small, &error));
  CHECK(!exr_pager_cached_count(pager));
  OK(exr_pager_get(pager, 0, &page, &error));
  CHECK(exr_pager_get(pager, 2, &page, &error) == EXR_LIMIT && !page);
  OK(exr_pager_set_cache(pager, 1, large, &error));
  OK(exr_pager_get(pager, 2, &page, &error));
  same_page(page, expected[2]);
  exr_pager_free(pager);
}

typedef struct {
  exr_pager *pager;
  unsigned decoded, released;
} image_provider;
static exr_status decode(void *context, const exr_resource *resource,
                           const void *encoded, size_t size, exr_bitmap *rgba, exr_error *e) {
  static unsigned char pixels[] = {19, 77, 155, 255};
  image_provider *source = context;
  const exr_layout *borrowed = (const exr_layout *)(uintptr_t)1;
  exr_layout *owned = (exr_layout *)(uintptr_t)1;
  exr_error nested;
  (void)e;
  CHECK(resource && encoded && size == 1);
  source->decoded++;
  CHECK(exr_pager_get(source->pager, 0, &borrowed, &nested) == EXR_ARGUMENT && !borrowed);
  CHECK(exr_pager_next(source->pager, &owned, &nested) == EXR_ARGUMENT && !owned);
  CHECK(exr_pager_set_cache(source->pager, 2, 0, &nested) == EXR_ARGUMENT);
  *rgba = (exr_bitmap){1, 1, 4, pixels, 4};
  return EXR_OK;
}
static void release(void *context, exr_bitmap *rgba) {
  image_provider *source = context;
  source->released++;
  memset(rgba, 0, sizeof(*rgba));
}
static void images(void) {
  unsigned char encoded = 1;
  exr_attribute src = {"src", "assets/pixel.custom"};
  exr_attribute after = {"style", "page-break-before:always"};
  exr_node_input nodes[] = {
      {EXR_NODE_DOCUMENT, SIZE_MAX, NULL, NULL, NULL, 0},
      {EXR_NODE_CHAPTER, 0, NULL, NULL, NULL, 0},
      {EXR_NODE_IMAGE, 1, NULL, NULL, &src, 1},
      {EXR_NODE_PARAGRAPH, 1, NULL, NULL, &after, 1},
      {EXR_NODE_TEXT, 3, NULL, "AAAA", NULL, 0}};
  exr_chapter_input chapter = {"image", "image.unit", 1, 1};
  exr_resource_input resource = {{"pixel", "assets/pixel.custom", "image/custom", ""}, &encoded, 1};
  exr_document_input input = {"Image cache", nodes, 5, &chapter, 1, &resource, 1};
  exr_layout_config config = exr_layout_config_defaults();
  image_provider source = {0};
  exr_document *doc = NULL;
  const exr_layout *page = NULL;
  const exr_bitmap *bitmap;
  exr_bitmap rendered = {0};
  config.decode_image = decode;
  config.release_image = release;
  config.image_context = &source;
  OK(exr_document_create(&input, &doc, &error));
  OK(exr_pager_create(doc, font, &config, &source.pager, &error));
  OK(exr_pager_get(source.pager, 0, &page, &error));
  CHECK(source.decoded == 1 && source.released == 1);
  bitmap = exr_layout_image(page, 0);
  CHECK(bitmap && bitmap->width == 1 && bitmap->pixels[0] == 19 && bitmap->pixels[2] == 155);
  OK(exr_pager_get(source.pager, 1, &page, &error));
  OK(exr_pager_get(source.pager, 0, &page, &error));
  CHECK(source.decoded == 1 && source.released == 1);
  bitmap = exr_layout_image(page, 0);
  CHECK(bitmap && bitmap->pixels[0] == 19);
  OK(exr_render_page_color(page, font, 0, &rendered, &error));
  exr_bitmap_free(&rendered);
  exr_pager_free(source.pager);
  exr_document_free(doc);
}

int main(int argc, char **argv) {
  exr_document *doc;
  exr_pager *pager = NULL;
  exr_layout *expected[5], *eof = (exr_layout *)(uintptr_t)1;
  exr_layout_config config = exr_layout_config_defaults();
  char path[4096];
  size_t i;
  CHECK(argc == 2);
  CHECK(snprintf(path, sizeof(path), "%s/primary.ttf", argv[1]) > 0);
  OK(exr_font_open(path, &font, &error));
  doc = document();
  config.page = (exr_layout_options){900, 600, 16, 16, 1.25f, 0};
  OK(exr_pager_create(doc, font, &config, &pager, &error));
  for (i = 0; i < 5; i++) {
    OK(exr_pager_next(pager, &expected[i], &error));
    CHECK(expected[i]);
  }
  OK(exr_pager_next(pager, &eof, &error));
  CHECK(!eof);
  exr_pager_free(pager);
  modes(doc, &config);
  continuation(doc, &config, expected);
  budgets(doc, &config, expected);
  for (i = 0; i < 5; i++) exr_layout_free(expected[i]);
  exr_document_free(doc);
  images();
  exr_font_free(font);
  printf("%u page cache checks passed\n", checks);
  return 0;
}
