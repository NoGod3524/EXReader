/* Compile with the unchanged main headers; run against the candidate DLL. */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>

_Static_assert(sizeof(exr_pager_cache_stats) == 2*sizeof(size_t), "legacy ABI");
static exr_error error;
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "line %d: %s\n", __LINE__, #x); exit(1); } } while (0)
int main(int argc, char **argv) {
  exr_font *font = NULL;
  exr_document *doc = NULL;
  exr_pager *pager = NULL;
  exr_layout *owned = NULL;
  const exr_layout *page = NULL;
  exr_layout_config config = exr_layout_config_defaults();
  exr_pager_cache_stats stats;
  char text[8192]; size_t i;
  CHECK(argc == 2);
  for (i = 0; i < sizeof(text); i++) text[i] = "AV a aV "[i % 8];
  CHECK(exr_font_open(argv[1], &font, &error) == EXR_OK);
  CHECK(exr_document_open_memory(EXR_TXT, text, sizeof(text), &doc, &error) == EXR_OK);
  config.page = (exr_layout_options){160, 112, 8, 16, 1.25f, 0};
  CHECK(exr_pager_create(doc, font, &config, &pager, &error) == EXR_OK);
  for (i = 0; i < 10; i++) {
    CHECK(exr_pager_next(pager, &owned, &error) == EXR_OK && owned);
    exr_layout_free(owned);
  }
  stats = exr_pager_cache_statistics(pager); CHECK(!stats.hits && !stats.misses);
  exr_pager_free(pager); pager = NULL;
  CHECK(exr_pager_create(doc, font, &config, &pager, &error) == EXR_OK);
  CHECK(exr_pager_set_cache(pager, 10, 0, &error) == EXR_OK);
  for (i = 0; i < 20; i++) CHECK(exr_pager_get(pager, i%10, &page, &error) == EXR_OK && page);
  stats = exr_pager_cache_statistics(pager); CHECK(stats.hits == 10 && stats.misses == 10);
  stats = exr_pager_cache_statistics(NULL); CHECK(!stats.hits && !stats.misses);
  exr_pager_free(pager); exr_document_free(doc); exr_font_free(font);
  puts("unchanged main headers/binary: sequential hits=0 misses=0; cached hits=10 misses=10; NULL=0/0");
  return 0;
}
