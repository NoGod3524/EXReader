/* SPDX-License-Identifier: MIT
 * Public shared-library consumer; create/reopen are separate process launches.
 */
#include <exreader.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define REQUIRE(c) do { if (!(c)) { fprintf(log, "FAIL line=%d status=%d %s\n", __LINE__, (int)error.code, error.message); goto done; } } while (0)
#define OK(c) REQUIRE((c) == EXR_OK)

int platform_probe(const char *book, const char *font_path, const char *out, int reopen) {
  char path[4096], *json = NULL;
  FILE *log = stdout, *file = NULL;
  exr_error error = {0};
  exr_publication *publication = NULL;
  exr_document *document = NULL;
  exr_font *font = NULL;
  exr_layout *layout = NULL;
  exr_bitmap bitmap = {0};
  exr_text_annotation note = {0}, imported = {0};
  exr_anchor_match match = {0};
  exr_search_result hit = {0};
  exr_layout_options options = {360, 480, 24, 18, 1.5f, 8};
  size_t pages = 0, count = 0, json_size = 0, ink = 0, hits = 0;
  uint64_t checksum = UINT64_C(14695981039346656037);
  int result = 1;
  if (snprintf(path, sizeof(path), "%s/%s.log", out, reopen ? "reopen" : "create") >= (int)sizeof(path)) return 2;
  log = fopen(path, "w");
  if (!log) return 2;
  setvbuf(log, NULL, _IONBF, 0);
  const char *version = exr_version();
  REQUIRE(version && *version);
  fprintf(log, "PASS load version=%s abi=%u mode=%s\n", version, exr_abi_version(), reopen ? "reopen" : "create");
  OK(exr_publication_open(book, &publication, &error));
  OK(exr_publication_load(publication, 0, &document, &error));
  OK(exr_font_open(font_path, &font, &error));
  OK(exr_layout_create(document, font, &options, &layout, &error));
  const exr_page *page = exr_layout_pages(layout, &pages);
  REQUIRE(page && pages > 0);
  fprintf(log, "PASS open pages=%zu\n", pages);
  OK(exr_render_page_color(layout, exr_layout_font(layout), 0, &bitmap, &error));
  REQUIRE(bitmap.pixels && bitmap.width && bitmap.height && bitmap.channels == 4 && bitmap.stride >= bitmap.width*4);
  for (uint32_t y = 0; y < bitmap.height; ++y) {
    const unsigned char *row = bitmap.pixels + (size_t)y*bitmap.stride;
    for (uint32_t x = 0; x < bitmap.width; ++x) {
      if (row[x*4] < 245 || row[x*4+1] < 245 || row[x*4+2] < 245) ++ink;
      for (unsigned c = 0; c < 4; ++c) { checksum ^= row[x*4+c]; checksum *= UINT64_C(1099511628211); }
    }
  }
  REQUIRE(ink > 0 && ink < (size_t)bitmap.width*bitmap.height);
  REQUIRE(snprintf(path, sizeof(path), "%s/%s.png", out, reopen ? "reopen" : "page") < (int)sizeof(path));
  OK(exr_bitmap_write_png(&bitmap, path, &error));
  REQUIRE(snprintf(path, sizeof(path), "%s/%s.rgba", out, reopen ? "reopen" : "page") < (int)sizeof(path));
  file = fopen(path, "wb");
  REQUIRE(file);
  for (uint32_t y = 0; y < bitmap.height; ++y)
    REQUIRE(fwrite(bitmap.pixels + (size_t)y*bitmap.stride, 4, bitmap.width, file) == bitmap.width);
  { int closed = fclose(file); file = NULL; REQUIRE(!closed); }
  fprintf(log, "PASS render width=%u height=%u ink_pixels=%zu pixel_fnv1a64=%016" PRIx64 "\n", bitmap.width, bitmap.height, ink, checksum);
  OK(exr_publication_search(publication, (exr_text_position){0, 0}, "deliveryneedle", EXR_SEARCH_CASE_SENSITIVE, NULL, &hit, &error));
  REQUIRE(hit.found && hit.part == 0 && hit.length == strlen("deliveryneedle"));
  fprintf(log, "PASS search hits_at_least=1 part=%zu offset=%zu length=%zu\n", hit.part, hit.offset, hit.length);
  OK(exr_publication_search_all(publication, "deliveryneedle", EXR_SEARCH_CASE_SENSITIVE, NULL, NULL, NULL, &hits, &error));
  REQUIRE(hits == 1000);
  fprintf(log, "PASS search_all needle=deliveryneedle hits=%zu\n", hits);
  const exr_glyph *glyphs = exr_layout_glyphs(layout, &count), *first = NULL;
  for (size_t i = 0; i < count; ++i)
    if (glyphs[i].end > hit.offset && glyphs[i].start < hit.offset+hit.length && !(glyphs[i].flags & EXR_GLYPH_HIDDEN)) { first = &glyphs[i]; break; }
  REQUIRE(first);
  if (!reopen) {
    note.id = "platform-runtime-highlight"; note.source = "urn:exreader:platform-smoke"; note.text = "highlight";
    OK(exr_anchor_create(document, hit.offset, hit.offset+hit.length, &note.anchor, &error));
    OK(exr_text_annotation_export(&note, &json, &json_size, &error));
    REQUIRE(snprintf(path, sizeof(path), "%s/highlight.json", out) < (int)sizeof(path));
    file = fopen(path, "wb");
    REQUIRE(file && fwrite(json, 1, json_size, file) == json_size);
    { int closed = fclose(file); file = NULL; REQUIRE(!closed); }
    REQUIRE(snprintf(path, sizeof(path), "%s/position.txt", out) < (int)sizeof(path));
    file = fopen(path, "w");
    REQUIRE(file && fprintf(file, "%zu %zu %zu %zu %.9g %.9g %016" PRIx64 "\n", hit.part, hit.offset, hit.offset+hit.length, first->page, (double)first->x, (double)first->baseline, checksum) > 0);
    { int closed = fclose(file); file = NULL; REQUIRE(!closed); }
    fprintf(log, "STORED highlight; awaiting independent process reopen\n");
  } else {
    size_t part, start, end, old_page;
    float x, baseline;
    uint64_t old_checksum;
    REQUIRE(snprintf(path, sizeof(path), "%s/position.txt", out) < (int)sizeof(path));
    file = fopen(path, "r");
    REQUIRE(file && fscanf(file, "%zu %zu %zu %zu %f %f %" SCNx64, &part, &start, &end, &old_page, &x, &baseline, &old_checksum) == 7);
    { int closed = fclose(file); file = NULL; REQUIRE(!closed); }
    REQUIRE(snprintf(path, sizeof(path), "%s/highlight.json", out) < (int)sizeof(path));
    file = fopen(path, "rb");
    REQUIRE(file && fseek(file, 0, SEEK_END) == 0);
    long length = ftell(file);
    REQUIRE(length > 0 && length < 1048576 && fseek(file, 0, SEEK_SET) == 0);
    json_size = (size_t)length;
    json = malloc(json_size+1);
    REQUIRE(json && fread(json, 1, json_size, file) == json_size);
    json[json_size] = 0;
    { int closed = fclose(file); file = NULL; REQUIRE(!closed); }
    OK(exr_text_annotation_import(json, json_size, &imported, &error));
    OK(exr_anchor_resolve(document, &imported.anchor, &match, &error));
    REQUIRE(match.state == EXR_ANCHOR_FOUND && match.start == start && match.end == end);
    REQUIRE(part == hit.part && start == hit.offset && end == hit.offset+hit.length);
    REQUIRE(first->page == old_page && first->x == x && first->baseline == baseline && old_checksum == checksum);
    size_t changed = 0;
    for (size_t i = 0; i < count; ++i) {
      const exr_glyph *g = &glyphs[i];
      if (g->page || g->end <= start || g->start >= end || g->flags & EXR_GLYPH_HIDDEN) continue;
      for (int y = (int)(g->baseline-g->size); y < (int)(g->baseline+g->size/4); ++y)
        for (int x2 = (int)g->x; x2 < (int)(g->x+g->advance); ++x2)
          if (x2 >= 0 && y >= 0 && x2 < (int)bitmap.width && y < (int)bitmap.height) {
            unsigned char *pixel = bitmap.pixels + (size_t)y*bitmap.stride + (size_t)x2*4;
            unsigned char blue = (unsigned char)(pixel[2]/2);
            changed += pixel[2] != blue; pixel[2] = blue;
          }
    }
    REQUIRE(changed > 0);
    REQUIRE(snprintf(path, sizeof(path), "%s/highlight.png", out) < (int)sizeof(path));
    OK(exr_bitmap_write_png(&bitmap, path, &error));
    fprintf(log, "PASS annotation independent_process=1 part=%zu start=%zu end=%zu page=%zu x=%.9g baseline=%.9g changed_pixels=%zu\n", part, start, end, old_page, (double)x, (double)baseline, changed);
    fprintf(log, "PASS platform checks=5/5\n");
  }
  result = 0;
done:
  if (file) fclose(file);
  if (reopen) free(json); else exr_free(json);
  exr_anchor_free(&note.anchor); exr_text_annotation_free(&imported);
  exr_bitmap_free(&bitmap); exr_layout_free(layout);
  exr_font_free(font); exr_document_free(document); exr_publication_free(publication);
  fclose(log);
  return result;
}

#ifndef PLATFORM_PROBE_EMBEDDED
int main(int argc, char **argv) {
  if (argc != 5 || (strcmp(argv[4], "create") && strcmp(argv[4], "reopen"))) {
    fprintf(stderr, "usage: platform-probe book.epub font.otf output-directory create|reopen\n"); return 2;
  }
  return platform_probe(argv[1], argv[2], argv[3], !strcmp(argv[4], "reopen"));
}
#endif
