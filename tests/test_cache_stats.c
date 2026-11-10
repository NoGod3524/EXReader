/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
_Static_assert(sizeof(exr_pager_cache_stats) == 2*sizeof(size_t), "legacy return layout");

static exr_error error;
static unsigned checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr, "line %d: %s: %s\n", __LINE__, #x, error.message); exit(1); } } while (0)
#define OK(x) CHECK((x) == EXR_OK)

static exr_pager_cache_stats_v1 snapshot(exr_pager *pager) {
  exr_pager_cache_stats old = exr_pager_cache_statistics(pager);
  exr_pager_cache_stats_v1 stats = {sizeof(stats), 0, 0, 0};
  OK(exr_pager_cache_stats_get(pager, &stats, &error));
  CHECK(old.hits == stats.hits && old.misses == stats.misses);
  return stats;
}

int main(int argc, char **argv) {
  exr_font *font = NULL;
  exr_document *doc = NULL;
  exr_pager *pager = NULL;
  const exr_layout *page = NULL;
  exr_layout *owned = NULL;
  exr_layout_config config = exr_layout_config_defaults();
  exr_pager_cache_stats_v1 stats = {0};
  exr_font_cache_stats cold = {0}, warm = {0};
  exr_bitmap before = {0}, after = {0};
  struct { exr_pager_cache_stats_v1 stats; uint64_t tail; } larger;
  char text[8192]; size_t i;
  CHECK(argc == 2);
  for (i = 0; i < sizeof(text); i++) text[i] = "AV a aV "[i % 8];
  OK(exr_font_open(argv[1], &font, &error));
  OK(exr_document_open_memory(EXR_TXT, text, sizeof(text), &doc, &error));
  config.page = (exr_layout_options){160, 112, 8, 16, 1.25f, 0};
  OK(exr_pager_create(doc, font, &config, &pager, &error));
  OK(exr_pager_set_cache(pager, 10, 0, &error));
  CHECK(exr_pager_cache_stats_get(pager, &stats, &error) == EXR_ARGUMENT);
  stats.struct_size = sizeof(stats)-1;
  CHECK(exr_pager_cache_stats_get(pager, &stats, &error) == EXR_ARGUMENT);
  stats.struct_size = sizeof(stats);
  CHECK(exr_pager_cache_stats_get(NULL, &stats, &error) == EXR_ARGUMENT);
  CHECK(exr_pager_cache_stats_get(pager, NULL, &error) == EXR_ARGUMENT);
  CHECK(exr_pager_cache_statistics(NULL).hits == 0 && exr_pager_cache_statistics(NULL).misses == 0);
  stats = snapshot(pager); CHECK(!stats.requests && !stats.hits && !stats.misses);
  CHECK(exr_pager_get(pager, 0, NULL, &error) == EXR_ARGUMENT);
  stats = snapshot(pager); CHECK(!stats.requests);
  for (i = 0; i < 10; i++) {
    OK(exr_pager_get(pager, i, &page, &error)); CHECK(page);
    stats = snapshot(pager); CHECK(stats.requests == i+1 && stats.hits == 0 && stats.misses == i+1);
  }
  for (i = 0; i < 10; i++) {
    OK(exr_pager_get(pager, i, &page, &error)); CHECK(page);
    stats = snapshot(pager); CHECK(stats.requests == 11+i && stats.hits == i+1 && stats.misses == 10);
  }
  printf("10 pages, two passes: requests=%" PRIu64 " legacy/new hits=%" PRIu64 " misses=%" PRIu64 "\n", stats.requests, stats.hits, stats.misses);
  cold.struct_size = warm.struct_size = sizeof(cold);
  OK(exr_render_page_color(page, exr_layout_font(page), 0, &before, &error));
  OK(exr_font_cache_stats_get(exr_layout_font(page), &cold, &error));
  OK(exr_render_page_color(page, exr_layout_font(page), 0, &after, &error));
  OK(exr_font_cache_stats_get(exr_layout_font(page), &warm, &error));
  CHECK(warm.glyph_hits > cold.glyph_hits && warm.glyph_misses == cold.glyph_misses);
  CHECK(warm.glyph_requests == warm.glyph_hits + warm.glyph_misses);
  CHECK(warm.shaping_requests == warm.shaping_hits + warm.shaping_misses);
  CHECK(before.stride == after.stride && before.height == after.height);
  CHECK(!memcmp(before.pixels, after.pixels, (size_t)before.stride * before.height));
  exr_bitmap_free(&before); exr_bitmap_free(&after);
  larger.stats.struct_size = sizeof(larger); larger.tail = UINT64_C(0x123456789abcdef0);
  OK(exr_pager_cache_stats_get(pager, &larger.stats, &error));
  CHECK(larger.stats.struct_size == sizeof(stats) && larger.tail == UINT64_C(0x123456789abcdef0));
  CHECK(exr_pager_get(pager, SIZE_MAX, &page, &error) == EXR_ARGUMENT);
  stats = snapshot(pager); CHECK(stats.requests == 21 && stats.hits == 10 && stats.misses == 11);
  exr_pager_free(pager); pager = NULL;
  OK(exr_pager_create(doc, font, &config, &pager, &error));
  for (i = 0; i < 10; i++) {
    OK(exr_pager_next(pager, &owned, &error)); CHECK(owned);
    exr_layout_free(owned); owned = NULL;
    stats = snapshot(pager); CHECK(stats.requests == i+1 && !stats.hits && !stats.misses);
  }
  CHECK(exr_pager_get(pager, 0, &page, &error) == EXR_ARGUMENT);
  stats = snapshot(pager); CHECK(stats.requests == 10 && !stats.hits && !stats.misses);
  exr_pager_free(pager); exr_document_free(doc); exr_font_free(font);
  printf("pager cache compatibility: %u checks passed\n", checks);
  return 0;
}
