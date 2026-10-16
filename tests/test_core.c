/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x)                                                                                   \
  do {                                                                                             \
    if (!(x)) {                                                                                    \
      fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #x);                                 \
      exit(1);                                                                                     \
    }                                                                                              \
    checks++;                                                                                      \
  } while (0)
#define OK(x)                                                                                      \
  do {                                                                                             \
    exr_status status = (x);                                                                       \
    if (status != EXR_OK) {                                                                        \
      fprintf(stderr, "FAIL %s:%d: %s (%d: %s)\n", __FILE__, __LINE__, #x, (int)status,            \
              error.message);                                                                      \
      exit(1);                                                                                     \
    }                                                                                              \
    checks++;                                                                                      \
  } while (0)
static unsigned checks;
static exr_error error;
static char fixtures[2048], build_dir[2048];
static const char *path(const char *name) {
  static char p[4096];
  snprintf(p, sizeof(p), "%s/%s", fixtures, name);
  return p;
}
static unsigned char *read_bytes(const char *file, size_t *n) {
  FILE *f = fopen(file, "rb");
  long size;
  unsigned char *p;
  CHECK(f);
  CHECK(!fseek(f, 0, SEEK_END));
  size = ftell(f);
  CHECK(size > 0);
  rewind(f);
  p = malloc((size_t)size);
  CHECK(p);
  CHECK(fread(p, 1, (size_t)size, f) == (size_t)size);
  fclose(f);
  *n = (size_t)size;
  return p;
}
static void test_formats(void) {
  const char *names[] = {"sample.txt",  "utf16.txt",   "sample.html", "sample.fb2",
                         "sample.epub", "sample.docx", "sample.rtf",  "sample.mobi"};
  const char *needles[] = {"Native C layout",
                           "中文 UTF16 😀",
                           "HTML & 中文 😀",
                           "FB2 中文 reading.",
                           "Second spine item, read first.",
                           "DOCX 中文 reading.",
                           "中文 😀",
                           "MOBI native reading."};
  size_t i, n;
  exr_document *doc = NULL;
  for (i = 0; i < 8; i++) {
    const char *text;
    OK(exr_document_open(path(names[i]), &doc, &error));
    text = exr_document_text(doc, &n);
    CHECK(text && n && strstr(text, needles[i]));
    CHECK(!strstr(text, "SECRET"));
    if (i == 4) {
      CHECK(!strcmp(exr_document_title(doc), "Native EPUB"));
      CHECK(strstr(text, "Second spine") < strstr(text, "First spine"));
    }
    if (i == 3)
      CHECK(!strcmp(exr_document_title(doc), "Native FB2"));
    exr_document_free(doc);
    doc = NULL;
  }
  CHECK(exr_document_open(path("entity.fb2"), &doc, &error) != EXR_OK && !doc);
  CHECK(exr_document_open(path("deep.fb2"), &doc, &error) != EXR_OK && !doc);
  CHECK(exr_document_open(path("unsafe.epub"), &doc, &error) != EXR_OK && !doc);
  CHECK(exr_document_open(path("bomb.epub"), &doc, &error) != EXR_OK && !doc);
  {
    const unsigned char invalid[] = {0xc0, 0xaf};
    CHECK(exr_document_open_memory(EXR_TXT, invalid, sizeof(invalid), &doc, &error) ==
          EXR_ENCODING);
  }
  {
    const unsigned char invalid[] = {0xff, 0xfe, 0, 0xd8};
    CHECK(exr_document_open_memory(EXR_TXT, invalid, sizeof(invalid), &doc, &error) ==
          EXR_ENCODING);
  }
  {
    const unsigned char empty[] = {0xef, 0xbb, 0xbf};
    CHECK(exr_document_open_memory(EXR_TXT, empty, sizeof(empty), &doc, &error) == EXR_FORMAT);
  }
  CHECK(exr_document_open_memory(EXR_TXT, "x", (size_t)128 * 1024 * 1024 + 1, &doc, &error) ==
        EXR_LIMIT);
}
static size_t node_with_id(const exr_node *nodes, size_t count, const char *id) {
  size_t i;
  for (i = 0; i < count; i++) {
    const char *value = exr_node_attribute(&nodes[i], "id");
    if (value && !strcmp(value, id))
      return i;
  }
  CHECK(0);
  return SIZE_MAX;
}
static void test_structure(void) {
  exr_document *doc = NULL;
  const exr_node *nodes;
  const exr_chapter *chapters;
  const exr_resource *resources;
  const char *text;
  size_t count, nc, nr, bytes, i, edges = 0, resource, target, paragraph, table, item;
  unsigned char *input;
  void *data = NULL;
  input = read_bytes(path("structure.epub"), &bytes);
  OK(exr_document_open_memory(EXR_EPUB, input, bytes, &doc, &error));
  memset(input, 0, bytes);
  free(input); /* The document owns the compressed source needed by resource reads. */
  nodes = exr_document_nodes(doc, &count);
  chapters = exr_document_chapters(doc, &nc);
  resources = exr_document_resources(doc, &nr);
  text = exr_document_text(doc, &bytes);
  CHECK(nodes && count > 60 && nc == 4 && nr == 8);
  CHECK(nodes[0].kind == EXR_NODE_DOCUMENT && nodes[0].parent == SIZE_MAX);
  CHECK(!strcmp(chapters[0].id, "second") && !strcmp(chapters[1].id, "first"));
  CHECK(chapters[2].in_spine && !chapters[2].linear);
  CHECK(!chapters[3].in_spine && !chapters[3].linear);
  CHECK(nodes[chapters[2].root].start == SIZE_MAX && nodes[chapters[3].root].start == SIZE_MAX);
  CHECK(strstr(text, "Second in manifest") < strstr(text, "First in manifest"));
  CHECK(strstr(text, "Alpha bold 中文 & tail."));
  CHECK(!strstr(text, "SECRET") && !strstr(text, "Auxiliary note") && !strstr(text, "#123456"));
  CHECK(!strcmp(resources[0].path, "OPS Book/text/100%-first.xhtml"));
  CHECK(!strcmp(resources[5].properties, "cover-image"));
  for (i = 0; i < count; i++) {
    size_t child, last = 0;
    if (i)
      CHECK(nodes[i].parent < i && nodes[i].chapter < nc);
    if (nodes[i].start != SIZE_MAX) {
      CHECK(nodes[i].start <= nodes[i].end && nodes[i].end <= bytes);
      CHECK(nodes[i].start == bytes || ((unsigned char)text[nodes[i].start] & 0xc0) != 0x80);
      CHECK(nodes[i].end == bytes || ((unsigned char)text[nodes[i].end] & 0xc0) != 0x80);
    }
    for (child = nodes[i].first_child; child != SIZE_MAX; child = nodes[child].next_sibling) {
      CHECK(child < count && child > i && child > last && nodes[child].parent == i);
      last = child;
      edges++;
    }
  }
  CHECK(edges == count - 1);
  paragraph = node_with_id(nodes, count, "local");
  table = node_with_id(nodes, count, "table");
  item = node_with_id(nodes, count, "item");
  CHECK(nodes[paragraph].kind == EXR_NODE_PARAGRAPH);
  CHECK(!strcmp(exr_node_attribute(&nodes[paragraph], "class"), "body"));
  CHECK(!strcmp(exr_node_attribute(&nodes[paragraph], "style"), "text-indent: 2em"));
  CHECK(nodes[paragraph].end - nodes[paragraph].start == strlen("Alpha bold 中文 & tail."));
  CHECK(nodes[table].kind == EXR_NODE_TABLE);
  CHECK(nodes[item].kind == EXR_NODE_LIST_ITEM && nodes[nodes[item].parent].kind == EXR_NODE_LIST);
  {
    int image = 0, cell = 0, style = 0, nav = 0, strong = 0;
    for (i = 0; i < count; i++) {
      if (nodes[i].kind == EXR_NODE_IMAGE) {
        CHECK(!strcmp(exr_node_attribute(&nodes[i], "alt"), "Small & original"));
        OK(exr_document_resolve(doc, nodes[i].chapter, exr_node_attribute(&nodes[i], "src"),
                                &resource, &target, &error));
        CHECK(resource == 5 && target == SIZE_MAX);
        image++;
      }
      if (nodes[i].kind == EXR_NODE_CELL && exr_node_attribute(&nodes[i], "colspan")) {
        CHECK(!strcmp(exr_node_attribute(&nodes[i], "colspan"), "2"));
        cell++;
      }
      if (nodes[i].text && strstr(nodes[i].text, ".body { color:")) {
        CHECK(nodes[i].start == SIZE_MAX);
        style++;
      }
      if (nodes[i].name && !strcmp(nodes[i].name, "http://www.w3.org/1999/xhtml|strong"))
        strong++;
      if (nodes[i].name && !strcmp(nodes[i].name, "http://www.w3.org/1999/xhtml|nav")) {
        CHECK(!strcmp(exr_node_attribute(&nodes[i], "http://www.idpf.org/2007/ops|type"), "toc"));
        nav++;
      }
    }
    CHECK(image == 1 && cell == 1 && style == 1 && nav == 1 && strong == 1);
  }
  OK(exr_document_resolve(doc, 0, "", &resource, &target, &error));
  CHECK(resource == 1 && target == chapters[0].root);
  OK(exr_document_resolve(doc, 0, "#local", &resource, &target, &error));
  CHECK(target == paragraph);
  OK(exr_document_resolve(doc, 0, "100%25-first.xhtml#anchor%20one", &resource, &target, &error));
  CHECK(resource == 0 && target == node_with_id(nodes, count, "anchor one"));
  OK(exr_document_resolve(doc, 1, "#anchor%20one", &resource, &target, &error));
  CHECK(resource == 0 && target == node_with_id(nodes, count, "anchor one"));
  OK(exr_document_resolve(doc, 0, "../notes.xhtml#%E6%B3%A8%E9%87%8A", &resource, &target, &error));
  CHECK(resource == 2 && target == node_with_id(nodes, count, "注释"));
  CHECK(nodes[target].kind == EXR_NODE_NOTE && nodes[target].start == SIZE_MAX);
  OK(exr_document_resolve(doc, 3, "text/第二章.xhtml#local", &resource, &target, &error));
  CHECK(target == paragraph);
  OK(exr_document_resolve(doc, 0, "#absent", &resource, &target, &error));
  CHECK(resource == 1 && target == SIZE_MAX);
  OK(exr_document_resolve(doc, 0, "unknown.xhtml", &resource, &target, &error));
  CHECK(resource == SIZE_MAX && target == SIZE_MAX);
  {
    const char *bad[] = {"https://example.org",
                         "//example.org/a",
                         "../../../escape",
                         "%2fetc/passwd",
                         "%43%3a/secret",
                         "..%5csecret",
                         "%00",
                         "#%ff",
                         "chapter.xhtml?query"};
    for (i = 0; i < sizeof(bad) / sizeof(*bad); i++)
      CHECK(exr_document_resolve(doc, 0, bad[i], &resource, &target, &error) == EXR_ARGUMENT);
  }
  OK(exr_document_resource(doc, 4, &data, &bytes, &error));
  CHECK(bytes == strlen(".body { font-size: 1.2em; }\n") && !memcmp(data, ".body", 5));
  exr_free(data);
  data = NULL;
  CHECK(exr_document_resource(doc, 6, &data, &bytes, &error) == EXR_FORMAT && !data && !bytes);
  CHECK(exr_document_resource(doc, 7, &data, &bytes, &error) == EXR_LIMIT && !data && !bytes);
  CHECK(exr_document_resource(doc, nr, &data, &bytes, &error) == EXR_ARGUMENT && !data);
  OK(exr_document_resource(doc, 5, &data, &bytes, &error));
  exr_document_free(doc);
  doc = NULL;
  CHECK(bytes > 8 && !memcmp(data, "\x89PNG\r\n\x1a\n", 8));
  exr_free(data);
  data = NULL;
  {
    exr_library *library = NULL;
    int64_t id;
    char database[4096];
    snprintf(database, sizeof(database), "%s/structure-library.sqlite", build_dir);
    remove(database);
    input = read_bytes(path("structure.epub"), &bytes);
    OK(exr_library_open(database, &library, &error));
    OK(exr_library_import(library, EXR_EPUB, input, bytes, NULL, &id, &error));
    free(input);
    exr_library_close(library);
    OK(exr_library_open(database, &library, &error));
    OK(exr_library_document(library, id, &doc, &error));
    exr_document_chapters(doc, &nc);
    CHECK(nc == 4);
    OK(exr_document_resolve(doc, 0, "../notes.xhtml#注释", &resource, &target, &error));
    CHECK(resource == 2 && target != SIZE_MAX);
    OK(exr_document_resource(doc, 5, &data, &bytes, &error));
    CHECK(bytes > 8 && !memcmp(data, "\x89PNG\r\n\x1a\n", 8));
    exr_free(data);
    exr_document_free(doc);
    doc = NULL;
    exr_library_close(library);
  }
  {
    const char *bad[] = {"structure-missing.epub", "structure-duplicate.epub",
                         "structure-entity.epub", "structure-deep.epub", "structure-broken.epub"};
    for (i = 0; i < sizeof(bad) / sizeof(*bad); i++)
      CHECK(exr_document_open(path(bad[i]), &doc, &error) != EXR_OK && !doc);
  }
  CHECK(exr_document_open(path("structure-attrs.epub"), &doc, &error) == EXR_LIMIT && !doc);
  CHECK(exr_document_open(path("structure-nodes.epub"), &doc, &error) == EXR_LIMIT && !doc);
  OK(exr_document_open(path("structure-image.epub"), &doc, &error));
  CHECK(!exr_document_text(doc, &bytes)[0] && bytes == 0);
  exr_document_nodes(doc, &count);
  CHECK(count > 1);
  exr_document_free(doc);
  doc = NULL;
  OK(exr_document_open_memory(EXR_TXT, "One\nTwo", 7, &doc, &error));
  nodes = exr_document_nodes(doc, &count);
  CHECK(count == 6 && nodes[2].kind == EXR_NODE_PARAGRAPH && nodes[3].kind == EXR_NODE_TEXT);
  CHECK(!strcmp(nodes[3].text, "One") && nodes[3].start == 0 && nodes[3].end == 3);
  exr_document_free(doc);
}
static void test_layout(const char *font_path) {
  exr_document *doc = NULL;
  exr_font *font = NULL;
  exr_layout *wide = NULL, *narrow = NULL;
  exr_layout_options o = exr_layout_defaults();
  size_t pages, count, i, nlines, nglyphs, start, end, bytes;
  const exr_page *p;
  const exr_line *lines;
  const exr_glyph *glyphs;
  exr_bitmap bitmap = {0};
  char output[4096];
  unsigned ink = 0;
  OK(exr_document_open(path("sample.txt"), &doc, &error));
  OK(exr_font_open(font_path, &font, &error));
  OK(exr_layout_create(doc, font, &o, &wide, &error));
  p = exr_layout_pages(wide, &pages);
  lines = exr_layout_lines(wide, &nlines);
  glyphs = exr_layout_glyphs(wide, &nglyphs);
  CHECK(pages > 1 && nlines > pages && nglyphs > nlines);
  exr_document_text(doc, &bytes);
  for (i = 0; i < pages; i++) {
    CHECK(p[i].start < p[i].end);
    CHECK(p[i].end <= bytes);
    CHECK(exr_layout_page_at(wide, p[i].start) == i);
  }
  for (i = 0; i < nglyphs; i++) {
    CHECK(glyphs[i].start < glyphs[i].end);
    CHECK(glyphs[i].page < pages);
    CHECK(glyphs[i].x >= o.margin - 1);
    CHECK(glyphs[i].x + glyphs[i].advance <= o.width - o.margin + 1);
    CHECK(isfinite(glyphs[i].baseline));
  }
  CHECK(exr_layout_hit_test(wide, 0, glyphs[0].x, lines[0].y) == glyphs[0].start);
  CHECK(exr_layout_hit_test(wide, pages + 1, 0, 0) == SIZE_MAX);
  OK(exr_document_find(doc, "中文", 0, &start, &end, &error));
  CHECK(start != SIZE_MAX && end > start);
  o.width = 420;
  OK(exr_layout_create(doc, font, &o, &narrow, &error));
  exr_layout_pages(narrow, &count);
  CHECK(count > pages);
  CHECK(exr_layout_page_at(narrow, start) != SIZE_MAX);
  CHECK(exr_layout_page_at(wide, start) != SIZE_MAX);
  OK(exr_render_page(wide, font, 0, &bitmap, &error));
  for (i = 0; i < (size_t)bitmap.stride * bitmap.height; i++)
    if (bitmap.pixels[i] < 200)
      ink++;
  CHECK(ink > 1000);
  snprintf(output, sizeof(output), "%s/native-page.bmp", build_dir);
  OK(exr_bitmap_write_bmp(&bitmap, output, &error));
  snprintf(output, sizeof(output), "%s/native-page.png", build_dir);
  OK(exr_bitmap_write_png(&bitmap, output, &error));
  exr_bitmap_free(&bitmap);
  o.width = NAN;
  {
    exr_layout *bad = NULL;
    CHECK(exr_layout_create(doc, font, &o, &bad, &error) == EXR_ARGUMENT && !bad);
  }
  {
    exr_font *fresh = NULL;
    exr_layout *warm_layout = NULL, *cold_layout = NULL;
    const exr_glyph *warm, *cold;
    size_t nw, nc, j;
    o = exr_layout_defaults();
    o.font_size = 32;
    OK(exr_layout_create(doc, font, &o, &warm_layout, &error));
    OK(exr_font_open(font_path, &fresh, &error));
    OK(exr_layout_create(doc, fresh, &o, &cold_layout, &error));
    warm = exr_layout_glyphs(warm_layout, &nw);
    cold = exr_layout_glyphs(cold_layout, &nc);
    CHECK(nw == nc);
    for (j = 0; j < nw; j++) {
      CHECK(warm[j].advance == cold[j].advance);
      CHECK(warm[j].page == cold[j].page);
      CHECK(warm[j].x == cold[j].x);
    }
    exr_layout_free(warm_layout);
    exr_layout_free(cold_layout);
    exr_font_free(fresh);
  }
  exr_layout_free(wide);
  exr_layout_free(narrow);
  exr_font_free(font);
  exr_document_free(doc);
}
static void test_library(void) {
  exr_library *l = NULL, *restored = NULL;
  exr_book *books = NULL;
  exr_note note = {0}, *notes = NULL;
  size_t n, count, blob_size;
  unsigned char *bytes;
  void *blob = NULL;
  int64_t id, note_id;
  char db[4096], backup[4096];
  exr_document *doc = NULL;
  snprintf(db, sizeof(db), "%s/test-library.sqlite", build_dir);
  snprintf(backup, sizeof(backup), "%s/test-backup.sqlite", build_dir);
  remove(db);
  remove(backup);
  bytes = read_bytes(path("sample.epub"), &n);
  CHECK(exr_library_open(path("foreign.sqlite"), &l, &error) == EXR_DATABASE && l == NULL);
  CHECK(exr_library_open(path("future.sqlite"), &l, &error) == EXR_DATABASE && l == NULL);
  OK(exr_library_open(db, &l, &error));
  OK(exr_library_import(l, EXR_EPUB, bytes, n, NULL, &id, &error));
  CHECK(id > 0);
  free(bytes);
  OK(exr_library_books(l, "Native EPUB", &books, &count, &error));
  CHECK(count == 1 && books[0].id == id);
  {
    exr_book edited = books[0];
    edited.title = "Own title 100%";
    edited.tags = "中文,fiction";
    edited.favorite = 1;
    edited.position = 12;
    OK(exr_library_update(l, &edited, &error));
  }
  exr_books_free(books, count);
  books = NULL;
  OK(exr_library_books(l, "%", &books, &count, &error));
  CHECK(count == 1 && !strcmp(books[0].title, "Own title 100%"));
  exr_books_free(books, count);
  books = NULL;
  OK(exr_library_cover(l, id, "cover", 5, &error));
  OK(exr_library_blob(l, id, 1, &blob, &blob_size, &error));
  CHECK(blob_size == 5 && !memcmp(blob, "cover", 5));
  exr_free(blob);
  note.book_id = id;
  note.start = 0;
  note.end = 6;
  note.text = "Native annotation";
  OK(exr_library_note(l, &note, &note_id, &error));
  CHECK(note_id > 0);
  note.id = note_id;
  note.text = "Updated annotation";
  OK(exr_library_note(l, &note, &note_id, &error));
  note.end = SIZE_MAX;
  CHECK(exr_library_note(l, &note, &note_id, &error) != EXR_OK);
  OK(exr_library_backup(l, backup, &error));
  exr_library_close(l);
  l = NULL;
  OK(exr_library_open(db, &l, &error));
  OK(exr_library_books(l, "中文", &books, &count, &error));
  CHECK(count == 1 && books[0].position == 12 && books[0].favorite == 1);
  exr_books_free(books, count);
  books = NULL;
  OK(exr_library_notes(l, id, &notes, &count, &error));
  CHECK(count == 1 && !strcmp(notes[0].text, "Updated annotation"));
  exr_notes_free(notes, count);
  notes = NULL;
  OK(exr_library_document(l, id, &doc, &error));
  CHECK(strstr(exr_document_text(doc, NULL), "Second spine"));
  exr_document_free(doc);
  OK(exr_library_delete(l, id, &error));
  OK(exr_library_notes(l, id, &notes, &count, &error));
  CHECK(count == 0);
  exr_notes_free(notes, count);
  CHECK(exr_library_blob(l, id, 0, &blob, &blob_size, &error) == EXR_ARGUMENT);
  OK(exr_library_open(backup, &restored, &error));
  OK(exr_library_books(restored, "", &books, &count, &error));
  CHECK(count == 1);
  exr_books_free(books, count);
  exr_library_close(restored);
  exr_library_close(l);
}
static void test_exports(void) {
  exr_format formats[] = {EXR_TXT, EXR_HTML, EXR_FB2, EXR_EPUB, EXR_DOCX, EXR_RTF};
  exr_document *doc = NULL, *copy = NULL;
  size_t i, n;
  void *data = NULL;
  const char *sample = "Text <>&\"'{} \\ 中文 😀\nSecond paragraph.";
  OK(exr_document_open_memory(EXR_TXT, sample, strlen(sample), &doc, &error));
  for (i = 0; i < 6; i++) {
    OK(exr_document_export(doc, formats[i], &data, &n, &error));
    CHECK(data && n);
    OK(exr_document_open_memory(formats[i], data, n, &copy, &error));
    CHECK(!strcmp(exr_document_text(doc, NULL), exr_document_text(copy, NULL)));
    exr_document_free(copy);
    exr_free(data);
  }
  exr_document_free(doc);
}
static void test_mutations(void) {
  const char *names[] = {"sample.fb2", "sample.epub", "sample.docx", "sample.rtf", "sample.mobi"};
  exr_format formats[] = {EXR_FB2, EXR_EPUB, EXR_DOCX, EXR_RTF, EXR_MOBI};
  size_t f;
  for (f = 0; f < 5; f++) {
    size_t n, i;
    unsigned char *bytes = read_bytes(path(names[f]), &n);
    size_t limit = n < 200 ? n : 200;
    for (i = 0; i < limit; i++) {
      exr_document *doc = NULL;
      unsigned char original = bytes[i];
      bytes[i] ^= (unsigned char)(0xa5 + i);
      (void)exr_document_open_memory(formats[f], bytes, n, &doc, &error);
      exr_document_free(doc);
      bytes[i] = original;
      checks++;
    }
    free(bytes);
  }
}
int main(int argc, char **argv) {
  const char *font = getenv("EXR_TEST_FONT");
  CHECK(argc == 3);
  snprintf(fixtures, sizeof(fixtures), "%s", argv[1]);
  snprintf(build_dir, sizeof(build_dir), "%s", argv[2]);
#ifdef _WIN32
  if (!font)
    font = "C:/Windows/Fonts/arial.ttf";
#elif defined(__APPLE__)
  if (!font)
    font = "/System/Library/Fonts/Supplemental/Arial.ttf";
#else
  if (!font)
    font = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf";
#endif
  test_formats();
  test_structure();
  test_layout(font);
  test_library();
  test_exports();
  test_mutations();
  printf("EXReader C %s: %u checks passed\n", exr_version(), checks);
  return 0;
}
