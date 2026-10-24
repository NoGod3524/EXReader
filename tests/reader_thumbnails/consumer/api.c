/* SPDX-License-Identifier: MIT */
/* Independent C11 consumer: only <reader_thumbnails.h> and the SDK. Walks the whole
   ownership cycle with a generated PNG: argv[1] work directory, argv[2] PNG path. */
#include <reader_thumbnails.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned char *load(const char *path, size_t *size) {
  FILE *f = fopen(path, "rb");
  unsigned char *data;
  long n;
  if (!f) return NULL;
  fseek(f, 0, SEEK_END); n = ftell(f); fseek(f, 0, SEEK_SET);
  if (n <= 0) { fclose(f); return NULL; }
  data = (unsigned char *)malloc((size_t)n);
  if (!data || fread(data, 1, (size_t)n, f) != (size_t)n) { fclose(f); free(data); return NULL; }
  fclose(f); *size = (size_t)n;
  return data;
}

int main(int argc, char **argv) {
  rth_limits limits = rth_limits_defaults();
  rth_request request = rth_request_defaults();
  rth_book book;
  rth_cache *cache = NULL;
  rth_thumbnail thumb, again;
  rth_error error;
  rth_stats stats;
  char sha[65];
  size_t size = 0;
  unsigned char *png;
  if (argc < 3) return 10;
  if (strcmp(RTH_VERSION, "0.1.0") || RTH_EDGE_HARD_MAX != 1024u || RTH_ENTRIES_HARD_MAX != 4096u ||
      RTH_TOTAL_BYTES_HARD_MAX != 536870912ull || RTH_SOURCE_PIXELS_HARD_MAX != 16777216ull) return 1;
  if (limits.struct_size != sizeof(limits) || limits.max_edge != 512u || request.struct_size != sizeof(request)) return 2;
  rth_sha256_hex("abc", 3, sha);
  if (strcmp(sha, "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")) return 3;
  memset(&book, 0, sizeof(book));
  book.format = (int)EXR_EPUB;
  memcpy(book.sha256, sha, 65);
  if (rth_cache_open(argv[1], &limits, &cache, &error) != RTH_OK || !cache) return 4;
  png = load(argv[2], &size);
  if (!png) return 5;
  request.width = 8; request.height = 8;
  memset(&thumb, 0xa5, sizeof(thumb));
  if (rth_cover_from_encoded(cache, &book, png, size, &request, NULL, &thumb, &error) != RTH_OK) return 6;
  if (thumb.origin != RTH_ORIGIN_AUTHOR_COVER || thumb.width != 8u || thumb.height != 4u || thumb.stride != 32u ||
      !thumb.pixels || thumb.from_cache || !thumb.stored) return 7;
  if (rth_cover_from_encoded(cache, &book, png, size, &request, NULL, &again, &error) != RTH_OK) return 8;
  if (!again.from_cache || again.width != 8u || memcmp(again.pixels, thumb.pixels, 8u * 4u * 4u) != 0) return 9;
  rth_thumbnail_free(&thumb);
  if (rth_cover_from_encoded(cache, &book, NULL, 0, &request, NULL, &thumb, &error) != RTH_OK || thumb.origin != RTH_ORIGIN_NONE ||
      thumb.pixels) return 11;
  if (rth_cover_from_encoded(NULL, &book, png, size, &request, NULL, &thumb, &error) != RTH_ARGUMENT || thumb.pixels) return 12;
  if (rth_cache_stats(cache, &stats, &error) != RTH_OK || stats.entries != 1u || stats.hits != 1u || stats.stores != 1u ||
      stats.bytes == 0u) return 13;
  rth_thumbnail_free(&again);
  rth_cache_close(cache);
  free(png);
  puts("c-consumer-ok");
  return 0;
}
