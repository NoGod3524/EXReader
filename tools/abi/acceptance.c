/* SPDX-License-Identifier: MIT */
#include <exreader.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define REQUIRE(condition) do { if (!(condition)) { fprintf(stderr, "FAIL line=%d status=%d %s\n", __LINE__, (int)error.code, error.message); goto done; } } while (0)
#define OK(call) REQUIRE((call) == EXR_OK)

/* The caller creates output_dir. All five checks fail closed; no screenshots
   or return values are borrowed from a previous run. */
int exr_acceptance(const char *book, const char *font_path, const char *output_dir) {
  exr_publication *publication = NULL;
  exr_document *document = NULL;
  exr_font *font = NULL;
  exr_layout *small = NULL, *large = NULL;
  exr_bitmap bitmap = {0};
  exr_error error = {0};
  exr_text_annotation note = {0}, imported = {0};
  exr_anchor_match match = {0};
  exr_search_result result = {0};
  exr_layout_options options = {360, 480, 24, 18, 1.5f, 8};
  char path[4096], *json = NULL;
  size_t json_size = 0, pages = 0, large_pages = 0, glyph_count = 0, changed = 0;
  FILE *file = NULL;
  int exit_code = 1;
  OK(exr_publication_open(book, &publication, &error));
  OK(exr_publication_load(publication, 0, &document, &error));
  OK(exr_font_open(font_path, &font, &error));
  OK(exr_layout_create(document, font, &options, &small, &error));
  const exr_page *page = exr_layout_pages(small, &pages);
  REQUIRE(page && pages >= 20);
  printf("PASS open status=0 pages=%zu\n", pages);
  for (size_t i = 0; i < 20; ++i) {
    OK(exr_render_page_color(small, exr_layout_font(small), i, &bitmap, &error));
    REQUIRE(bitmap.pixels && bitmap.channels == 4);
    REQUIRE(snprintf(path, sizeof(path), "%s/page-%02zu.png", output_dir, i+1) < (int)sizeof(path));
    OK(exr_bitmap_write_png(&bitmap, path, &error));
    exr_bitmap_free(&bitmap);
  }
  printf("PASS turn status=0 rendered=20 last=page-20.png\n");
  OK(exr_publication_search(publication, (exr_text_position){0, 0}, "deliveryneedle",
                            EXR_SEARCH_CASE_SENSITIVE, NULL, &result, &error));
  REQUIRE(result.found && result.part == 0 && result.length == strlen("deliveryneedle"));
  printf("PASS search status=0 found=1 part=%zu offset=%zu length=%zu\n", result.part, result.offset, result.length);
  options.font_size = 24;
  OK(exr_layout_create(document, font, &options, &large, &error));
  const exr_page *large_page = exr_layout_pages(large, &large_pages);
  REQUIRE(large_page && large_pages > pages && large_page[0].end < page[0].end);
  OK(exr_render_page_color(large, exr_layout_font(large), 0, &bitmap, &error));
  REQUIRE(snprintf(path, sizeof(path), "%s/font-24.png", output_dir) < (int)sizeof(path));
  OK(exr_bitmap_write_png(&bitmap, path, &error));
  printf("PASS fontsize status=0 from=18 to=24 pages_before=%zu pages_after=%zu\n", pages, large_pages);
  note.id = "platform-highlight-1"; note.source = "urn:exreader:platform-smoke"; note.text = "highlight";
  OK(exr_anchor_create(document, result.offset, result.offset+result.length, &note.anchor, &error));
  OK(exr_text_annotation_export(&note, &json, &json_size, &error));
  REQUIRE(snprintf(path, sizeof(path), "%s/highlight.json", output_dir) < (int)sizeof(path));
  file = fopen(path, "wb");
  REQUIRE(file && fwrite(json, 1, json_size, file) == json_size);
  { int closed = fclose(file); file = NULL; REQUIRE(closed == 0); }
  /* Re-read the stored annotation; validate persistence as well as serialization. */
  memset(json, 0, json_size);
  file = fopen(path, "rb");
  REQUIRE(file && fread(json, 1, json_size, file) == json_size);
  { int closed = fclose(file); file = NULL; REQUIRE(closed == 0); }
  OK(exr_text_annotation_import(json, json_size, &imported, &error));
  OK(exr_anchor_resolve(document, &imported.anchor, &match, &error));
  REQUIRE(match.state == EXR_ANCHOR_FOUND && match.start == result.offset && match.end == result.offset+result.length);
  const exr_glyph *glyphs = exr_layout_glyphs(large, &glyph_count);
  /* Highlight painting belongs to the host. This reference overlay uses the
     engine's UTF-8 ranges and glyph positions; it does not claim native UI QA. */
  for (size_t i = 0; i < glyph_count; ++i) {
    const exr_glyph *g = &glyphs[i];
    if (g->page || g->end <= match.start || g->start >= match.end || g->flags & EXR_GLYPH_HIDDEN) continue;
    for (int y = (int)(g->baseline-g->size); y < (int)(g->baseline+g->size/4); ++y)
      for (int x = (int)g->x; x < (int)(g->x+g->advance); ++x)
        if (x >= 0 && y >= 0 && x < (int)bitmap.width && y < (int)bitmap.height) {
          unsigned char *pixel = bitmap.pixels + (size_t)y*bitmap.stride + (size_t)x*4;
          unsigned char blue = (unsigned char)(pixel[2]/2);
          if (pixel[2] != blue) ++changed;
          pixel[2] = blue;
        }
  }
  REQUIRE(changed > 0);
  REQUIRE(snprintf(path, sizeof(path), "%s/highlight.png", output_dir) < (int)sizeof(path));
  OK(exr_bitmap_write_png(&bitmap, path, &error));
  printf("PASS highlight status=0 stored=1 resolved=FOUND changed_pixels=%zu\n", changed);
  printf("PASS acceptance checks=5\n");
  exit_code = 0;
done:
  if (file) fclose(file);
  exr_free(json);
  exr_anchor_free(&note.anchor);
  exr_text_annotation_free(&imported);
  exr_bitmap_free(&bitmap);
  exr_layout_free(large); exr_layout_free(small);
  exr_font_free(font); exr_document_free(document); exr_publication_free(publication);
  return exit_code;
}

#ifndef EXR_ACCEPTANCE_IOS
int main(int argc, char **argv) {
  if (argc != 4) { fprintf(stderr, "usage: exreader-acceptance book.epub font.ttf output-directory\n"); return 2; }
  return exr_acceptance(argv[1], argv[2], argv[3]);
}
#endif
