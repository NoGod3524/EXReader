/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static exr_error error;
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "line %d: %s: %s\n", __LINE__, #x, error.message); exit(1); } } while (0)
#define OK(x) CHECK((x) == EXR_OK)
static int cancel(void *context) { (void)context; return 1; }

int main(int argc, char **argv) {
  exr_publication *pub = NULL;
  exr_document *doc = NULL;
  exr_font *font = NULL;
  exr_pager *pager = NULL;
  exr_layout *owned = NULL;
  const exr_layout *page = NULL, *hit = NULL;
  exr_bitmap before = {0}, after = {0};
  exr_layout_config config = exr_layout_config_defaults();
  exr_pager_cache_stats layout = {0};
  exr_font_cache_stats cold = {0}, warm = {0};
  CHECK(argc == 3);
  layout.struct_size = sizeof(layout);
  cold.struct_size = warm.struct_size = sizeof(cold);
  OK(exr_font_open(argv[2], &font, &error));
  OK(exr_publication_open(argv[1], &pub, &error));
  CHECK(exr_publication_warmup(NULL, font, &config, 1, &error) == EXR_ARGUMENT);
  CHECK(exr_publication_warmup(pub, NULL, &config, 1, &error) == EXR_ARGUMENT);
  OK(exr_publication_warmup(pub, font, &config, 0, &error));
  OK(exr_publication_load(pub, 0, &doc, &error));
  OK(exr_pager_create(doc, font, &config, &pager, &error));
  OK(exr_pager_get(pager, 0, &page, &error));
  OK(exr_render_page_color(page, exr_layout_font(page), 0, &before, &error));
  OK(exr_font_cache_stats_get(exr_layout_font(page), &cold, &error));
  OK(exr_pager_get(pager, 0, &hit, &error)); CHECK(hit == page);
  OK(exr_render_page_color(hit, exr_layout_font(hit), 0, &after, &error));
  OK(exr_font_cache_stats_get(exr_layout_font(hit), &warm, &error));
  CHECK(warm.glyph_hits > cold.glyph_hits);
  CHECK(before.stride == after.stride && before.height == after.height);
  CHECK(!memcmp(before.pixels, after.pixels, (size_t)before.stride * before.height));
  exr_bitmap_free(&after);
  OK(exr_pager_cache_stats_get(pager, &layout, &error));
  CHECK(layout.requests == 2 && layout.hits == 1 && layout.misses == 1);
  layout.struct_size = 0;
  CHECK(exr_pager_cache_stats_get(pager, &layout, &error) == EXR_ARGUMENT);
  CHECK(exr_pager_cache_stats_get(NULL, &layout, &error) == EXR_ARGUMENT);
  CHECK(exr_pager_cache_stats_get(pager, NULL, &error) == EXR_ARGUMENT);
  exr_pager_free(pager); pager = NULL;
  exr_font_free(font); font = NULL;
  OK(exr_font_open(argv[2], &font, &error));
  OK(exr_font_cache_stats_get(font, &cold, &error));
  CHECK(!cold.glyph_requests && !cold.shaping_requests);
  config.control.cancelled = cancel;
  CHECK(exr_publication_warmup(pub, font, &config, 2, &error) == EXR_CANCELLED);
  config.control.cancelled = NULL;
  OK(exr_publication_warmup(pub, font, &config, 2, &error));
  OK(exr_font_cache_stats_get(font, &warm, &error));
  CHECK(warm.glyph_requests > 0 && warm.shaping_requests > 0);
  cold = warm;
  OK(exr_pager_create(doc, font, &config, &pager, &error));
  OK(exr_pager_next(pager, &owned, &error)); CHECK(owned);
  OK(exr_render_page_color(owned, exr_layout_font(owned), 0, &after, &error));
  OK(exr_font_cache_stats_get(exr_layout_font(owned), &warm, &error));
  CHECK(warm.glyph_hits > cold.glyph_hits);
  CHECK(before.stride == after.stride && before.height == after.height);
  CHECK(!memcmp(before.pixels, after.pixels, (size_t)before.stride * before.height));
  layout.struct_size = sizeof(layout);
  OK(exr_pager_cache_stats_get(pager, &layout, &error));
  CHECK(layout.requests == 1 && layout.hits == 0 && layout.misses == 1);
  exr_bitmap_free(&after); exr_bitmap_free(&before);
  exr_layout_free(owned); exr_pager_free(pager); exr_document_free(doc);
  OK(exr_publication_warmup(pub, font, NULL, 1000, &error));
  exr_publication_free(pub); exr_font_free(font);
  puts("batch cache counters, warmup cancellation and pixel equivalence passed");
  return 0;
}
