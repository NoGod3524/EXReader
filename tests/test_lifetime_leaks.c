/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#if defined(_MSC_VER) && defined(_DEBUG)
#include <crtdbg.h>
#define HAVE_CRT_HEAP 1
#endif

static exr_error error;
#define CHECK(condition) do { if (!(condition)) { \
  fprintf(stderr, "FAIL %s:%d: %s (%s)\n", __FILE__, __LINE__, #condition, error.message); \
  exit(1); } } while (0)
#define OK(expression) CHECK((expression) == EXR_OK)

/* The CRT run links static SDK components: the executable and every dependency
   use the same debug heap. MSVC ASan disables these CRT counters, so a deliberate
   17-byte allocation must be detected before accepting any CRT leak evidence. */
static void crt_control(void) {
#ifdef HAVE_CRT_HEAP
  _CrtMemState before, after, delta;
  void *allocation;
  int changed;
  _CrtSetReportMode(_CRT_WARN, _CRTDBG_MODE_FILE);
  _CrtSetReportFile(_CRT_WARN, _CRTDBG_FILE_STDERR);
  memset(&delta, 0, sizeof(delta));
  _CrtMemCheckpoint(&before);
  allocation = malloc(17);
  CHECK(allocation != NULL);
  _CrtMemCheckpoint(&after);
  changed = _CrtMemDifference(&delta, &before, &after);
  CHECK(changed && delta.lCounts[_NORMAL_BLOCK] == 1 && delta.lSizes[_NORMAL_BLOCK] == 17);
  free(allocation);
  _CrtMemCheckpoint(&after);
  CHECK(!_CrtMemDifference(&delta, &before, &after));
  puts("CRT_CONTROL detected_blocks=1 detected_bytes=17 after_free_blocks=0 after_free_bytes=0");
#else
  CHECK(!"CRT checking requires a static MSVC Debug build");
#endif
}

static void use_book(const char *font_path, const char *book_path) {
  exr_font *font = NULL;
  exr_publication *publication = NULL;
  exr_document *document = NULL;
  exr_pager *pager = NULL;
  exr_layout *page = NULL;
  exr_fixed_document *fixed = NULL;
  exr_fixed_text *text = NULL;
  exr_bitmap bitmap = {0};
  size_t count = 0;
  const char *extension = strrchr(book_path, '.');
  OK(exr_font_open(font_path, &font, &error));
  CHECK(exr_validate(font));
  if (extension && (!strcmp(extension, ".pdf") || !strcmp(extension, ".cbz"))) {
    exr_fixed_open_options options = {0};
    options.struct_size = sizeof(options);
    options.fallback_font = font;
    OK(exr_fixed_open(book_path, &options, &fixed, &error));
    CHECK(exr_validate(fixed));
    CHECK(exr_fixed_pages(fixed, &count) && count > 0);
    OK(exr_fixed_render(fixed, 0, 0.5, NULL, &bitmap, &error));
    OK(exr_fixed_load_text(fixed, 0, NULL, &text, &error));
    CHECK(text && exr_validate(text));
    exr_fixed_text_regions(text, &count);
    exr_fixed_text_free(text);
    exr_bitmap_free(&bitmap);
    exr_fixed_free(fixed);
  } else {
    exr_layout_config config = exr_layout_config_defaults();
    config.page.width = 600;
    config.page.height = 800;
    if (extension && (!strcmp(extension, ".epub") || !strcmp(extension, ".mobi"))) {
      OK(exr_publication_open(book_path, &publication, &error));
      CHECK(exr_validate(publication));
      CHECK(exr_publication_parts(publication, &count) && count > 0);
      OK(exr_publication_load(publication, 0, &document, &error));
    } else {
      OK(exr_document_open(book_path, &document, &error));
    }
    CHECK(exr_validate(document));
    CHECK(exr_document_title(document) != NULL);
    exr_document_text(document, &count);
    OK(exr_pager_create(document, font, &config, &pager, &error));
    CHECK(exr_validate(pager));
    OK(exr_pager_next(pager, &page, &error));
    if (page) {
      CHECK(exr_validate(page));
      exr_layout_glyphs(page, &count);
      OK(exr_render_page_color(page, exr_layout_font(page), 0, &bitmap, &error));
      CHECK(bitmap.pixels && bitmap.width && bitmap.height);
      exr_bitmap_free(&bitmap);
      exr_layout_free(page);
    }
    exr_pager_free(pager);
    exr_document_free(document);
    exr_publication_free(publication);
  }
  exr_font_free(font);
}

int main(int argc, char **argv) {
  exr_lifetime_count counts[128];
  size_t count, i;
  int first = 2, book, crt = 0;
#ifdef HAVE_CRT_HEAP
  _CrtMemState before, after, delta;
#endif
  /* The runner requires LSan to detect this lost handle. This also verifies
     that the diagnostic registry drops its roots instead of hiding leaks. */
  if (argc == 2 && !strcmp(argv[1], "--lsan-control")) {
    exr_document *lost = NULL;
    OK(exr_document_open_memory(EXR_TXT, "intentional SDK leak", 19, &lost, &error));
    CHECK(lost != NULL);
    puts("LSAN_CONTROL deliberately unreleased SDK document");
    return 0;
  }
  if (argc < 3) {
    fprintf(stderr, "usage: %s FONT [--crt] BOOK...\n", argv[0]);
    return 2;
  }
  if (!strcmp(argv[2], "--crt")) {
    crt = 1;
    first++;
    crt_control();
  }
  CHECK(argc > first);
  puts("LIFETIME_LEAKS start");
  fflush(stdout);
  for (book = first; book < argc; book++) {
#ifdef HAVE_CRT_HEAP
    if (crt) _CrtMemCheckpoint(&before);
#endif
    use_book(argv[1], argv[book]);
    count = exr_debug_counts(counts, sizeof(counts) / sizeof(counts[0]));
    CHECK(count <= sizeof(counts) / sizeof(counts[0]));
    for (i = 0; i < count; i++)
      CHECK(counts[i].created == counts[i].freed && counts[i].live == 0);
    exr_debug_cleanup();
#ifdef HAVE_CRT_HEAP
    if (crt) {
      _CrtMemCheckpoint(&after);
      if (_CrtMemDifference(&delta, &before, &after)) {
        _CrtMemDumpStatistics(&delta);
        _CrtMemDumpAllObjectsSince(&before);
        CHECK(!"book left CRT heap allocations");
      }
    }
#endif
    printf("BOOK %d PASS live=0%s\n", book - first + 1,
           crt ? " heap_blocks=0 heap_bytes=0" : "");
    fflush(stdout);
  }
  count = exr_debug_counts(counts, sizeof(counts) / sizeof(counts[0]));
  for (i = 0; i < count; i++)
    printf("COUNT %s %zu %zu %zu\n", counts[i].type, counts[i].created,
           counts[i].freed, counts[i].live);
  printf("SUMMARY books=%d live=0%s\n", argc - first,
         crt ? " heap_blocks=0 heap_bytes=0" : "");
  return 0;
}
