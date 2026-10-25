/* SPDX-License-Identifier: MIT */
/* S13 CBZ leading-slash candidate acceptance probe.
   Built against the installed public SDK only (EXReader::exreader). It never
   includes private headers, never rewrites the archive it is handed, and prints
   one JSON report so an independent checker can authenticate every claim. */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static exr_error error;
static char *out;
static size_t used, room;

static void put(const char *bytes, size_t size) {
  if (used + size + 1 > room) {
    size_t grown = room ? room : 4096;
    char *next;
    while (used + size + 1 > grown) grown *= 2;
    next = realloc(out, grown);
    if (!next) { fprintf(stderr, "probe output allocation failed\n"); exit(2); }
    out = next;
    room = grown;
  }
  memcpy(out + used, bytes, size);
  used += size;
  out[used] = 0;
}
static void text(const char *s) { put(s, strlen(s)); }
static void number(long long v) { char t[32]; snprintf(t, sizeof t, "%lld", v); text(t); }
static void real_number(double v) { char t[64]; snprintf(t, sizeof t, "%.17g", v); text(t); }
static void quoted(const char *s) {
  const unsigned char *p = (const unsigned char *)(s ? s : "");
  text("\"");
  while (*p) {
    if (*p == '"' || *p == '\\') { char e[3]; e[0] = '\\'; e[1] = (char)*p; e[2] = 0; text(e); }
    else if (*p < 0x20 || *p == 0x7f) { char e[8]; snprintf(e, sizeof e, "\\u%04x", *p); text(e); }
    else put((const char *)p, 1);
    p++;
  }
  text("\"");
}
static int first_member, object_depth;
static int pending[16];
static void start_object(void) {
  pending[object_depth++] = first_member;
  text("{");
  first_member = 1;
}
static void end_object(void) {
  text("}");
  if (object_depth > 0 && object_depth - 1 < 16) first_member = pending[--object_depth];
}
static void member(const char *name) {
  if (!first_member) text(",");
  first_member = 0;
  quoted(name);
  text(":");
}
static void number_member(const char *name, long long value) { member(name); number(value); }
static void text_member(const char *name, const char *value) { member(name); quoted(value); }
static void flag_member(const char *name, int value) { member(name); text(value ? "true" : "false"); }
static void size_member(const char *name, size_t value) {
  member(name);
  if (value == (size_t)-1) text("null"); else number((long long)value);
}

static unsigned long long fnv_update(unsigned long long h, const unsigned char *bytes, size_t size) {
  while (size--) { h ^= *bytes++; h *= 1099511628211ull; }
  return h;
}
static unsigned long long bitmap_digest(const exr_bitmap *b) {
  unsigned long long h = 1469598103934665603ull;
  uint32_t y, row;
  if (!b->pixels) return 0;
  row = b->width * b->channels;
  for (y = 0; y < b->height; y++) h = fnv_update(h, b->pixels + (size_t)y * b->stride, row);
  return h;
}
static void digest_member(const char *name, unsigned long long h) {
  char t[32];
  snprintf(t, sizeof t, "%016llx", h);
  text_member(name, t);
}
static void error_member(void) { text_member("message", error.message); }

/* Delivered image layer, so a page identity can be compared with the decoded
   bytes of the archive member that carries that name. */
typedef struct { unsigned images, w, h, channels; unsigned long long digest; } layer_state;
static exr_status on_image(void *context, const exr_image_layer *image, const double matrix[6], double alpha, exr_error *e) {
  layer_state *state = context;
  (void)matrix; (void)alpha; (void)e;
  if (!state->images) {
    state->w = image->bitmap.width;
    state->h = image->bitmap.height;
    state->channels = image->bitmap.channels;
    state->digest = bitmap_digest(&image->bitmap);
  }
  state->images++;
  return EXR_OK;
}
static void render_page(exr_fixed_document *d, size_t page) {
  exr_bitmap bitmap = {0};
  exr_status status = exr_fixed_render(d, page, 1, NULL, &bitmap, &error);
  number_member("page", (long long)page);
  number_member("status", status);
  if (status == EXR_OK) {
    number_member("width", bitmap.width);
    number_member("height", bitmap.height);
    number_member("channels", bitmap.channels);
    digest_member("digest", bitmap_digest(&bitmap));
  } else error_member();
  exr_bitmap_free(&bitmap);
}
static void draw_page(exr_fixed_document *d, size_t page) {
  exr_draw_sink sink = {0};
  layer_state state = {0};
  exr_status status;
  sink.image = on_image;
  sink.context = &state;
  status = exr_fixed_draw(d, page, NULL, &sink, NULL, &error);
  number_member("page", (long long)page);
  number_member("status", status);
  number_member("images", state.images);
  if (state.images) {
    number_member("width", state.w);
    number_member("height", state.h);
    number_member("channels", state.channels);
    digest_member("digest", state.digest);
  }
  if (status != EXR_OK) error_member();
}
static void report_pages(exr_fixed_document *d) {
  size_t count = 0, i;
  const exr_fixed_page *pages = exr_fixed_pages(d, &count);
  member("page_count"); number((long long)count);
  member("ids"); text("[");
  for (i = 0; i < count; i++) { if (i) text(","); quoted(pages[i].id); }
  text("]");
  member("geometry"); text("[");
  for (i = 0; i < count; i++) {
    if (i) text(",");
    start_object();
    number_member("index", (long long)i);
    number_member("width", (long long)(pages[i].geometry.bounds[2] - pages[i].geometry.bounds[0]));
    number_member("height", (long long)(pages[i].geometry.bounds[3] - pages[i].geometry.bounds[1]));
    flag_member("y_down", pages[i].geometry.y_down);
    member("unit_scale"); real_number(pages[i].geometry.unit_scale);
    end_object();
  }
  text("]");
}
static size_t sample_pages(size_t count, size_t sample[3]) {
  size_t n = 0;
  if (!count) return 0;
  sample[n++] = 0;
  if (count > 2) sample[n++] = count / 2;
  if (count > 1) sample[n++] = count - 1;
  return n;
}
static void report_samples(exr_fixed_document *d) {
  size_t count = 0, sample[3], n, i;
  exr_fixed_pages(d, &count);
  n = sample_pages(count, sample);
  member("render"); text("[");
  for (i = 0; i < n; i++) { if (i) text(","); start_object(); render_page(d, sample[i]); end_object(); }
  text("]");
  member("draw"); text("[");
  for (i = 0; i < n; i++) { if (i) text(","); start_object(); draw_page(d, sample[i]); end_object(); }
  text("]");
}
/* A page index one past the end must fail without a partial bitmap and must not
   disturb the page that was rendered before and after the refusal. */
static void report_fallback(exr_fixed_document *d) {
  size_t count = 0, page;
  exr_bitmap bitmap = {0};
  unsigned long long before = 0, after = 0;
  exr_status status;
  exr_fixed_pages(d, &count);
  member("fallback"); start_object();
  number_member("page", (long long)count);
  status = exr_fixed_render(d, count, 1, NULL, &bitmap, &error);
  number_member("status", status);
  flag_member("empty_bitmap", bitmap.width == 0 && bitmap.height == 0 && bitmap.pixels == NULL);
  error_member();
  exr_bitmap_free(&bitmap);
  if (!count) { end_object(); return; }
  page = count - 1;
  if (exr_fixed_render(d, page, 1, NULL, &bitmap, &error) == EXR_OK) before = bitmap_digest(&bitmap);
  exr_bitmap_free(&bitmap);
  memset(&bitmap, 0, sizeof bitmap);
  status = exr_fixed_render(d, count, 1, NULL, &bitmap, &error);
  number_member("repeat_status", status);
  exr_bitmap_free(&bitmap);
  memset(&bitmap, 0, sizeof bitmap);
  if (exr_fixed_render(d, page, 1, NULL, &bitmap, &error) == EXR_OK) after = bitmap_digest(&bitmap);
  exr_bitmap_free(&bitmap);
  digest_member("last_digest", before);
  flag_member("stable", before != 0 && before == after);
  end_object();
}
/* CBZ pages carry no text, so capture is a point bookmark: the selector keeps
   the page identity and an empty range, and resolve never invents a range. */
static void report_capture(exr_fixed_document *d) {
  size_t count = 0, page, regions = 0, text_size = 0;
  const exr_fixed_page *pages = exr_fixed_pages(d, &count);
  exr_fixed_text *snapshot = NULL;
  exr_fixed_anchor anchor = {0};
  exr_anchor_match match;
  exr_status status, other_status;
  member("capture"); start_object();
  if (!count) { end_object(); return; }
  page = count / 2;
  number_member("page", (long long)page);
  text_member("page_id", pages[page].id);
  status = exr_fixed_load_text(d, page, NULL, &snapshot, &error);
  number_member("text_status", status);
  if (status == EXR_OK) {
    const char *body = exr_fixed_text_string(snapshot, &text_size);
    const exr_text_region *list = exr_fixed_text_regions(snapshot, &regions);
    (void)list;
    number_member("text_size", (long long)text_size);
    number_member("regions", (long long)regions);
    flag_member("empty_text", body != NULL && text_size == 0);
    status = exr_fixed_anchor_create(pages[page].id, snapshot, 0, 0, &anchor, &error);
    number_member("capture_status", status);
    if (status == EXR_OK) {
      size_member("exact_size", anchor.exact_size);
      size_member("prefix_size", anchor.prefix_size);
      size_member("suffix_size", anchor.suffix_size);
      text_member("anchor_page_id", anchor.page_id ? anchor.page_id : "");
      status = exr_fixed_anchor_resolve(pages[page].id, snapshot, &anchor, NULL, &match, &error);
      number_member("resolve_status", status);
      number_member("resolve_state", match.state);
      size_member("resolve_start", match.start);
      size_member("resolve_end", match.end);
      if (count > 1) {
        other_status = exr_fixed_anchor_resolve(pages[0].id, snapshot, &anchor, NULL, &match, &error);
        number_member("other_status", other_status);
        number_member("other_state", match.state);
        size_member("other_start", match.start);
        size_member("other_end", match.end);
      }
    }
  }
  end_object();
  exr_fixed_anchor_free(&anchor);
  exr_fixed_text_free(snapshot);
}
static int same_pages(exr_fixed_document *left, exr_fixed_document *right, int *geometries) {
  size_t a = 0, b = 0, i;
  const exr_fixed_page *x = exr_fixed_pages(left, &a);
  const exr_fixed_page *y = exr_fixed_pages(right, &b);
  int ids = a == b;
  *geometries = a == b;
  for (i = 0; ids && i < a; i++) if (strcmp(x[i].id, y[i].id)) ids = 0;
  for (i = 0; *geometries && i < a; i++)
    if (x[i].geometry.bounds[2] != y[i].geometry.bounds[2] || x[i].geometry.bounds[3] != y[i].geometry.bounds[3] ||
        x[i].geometry.unit_scale != y[i].geometry.unit_scale || x[i].geometry.y_down != y[i].geometry.y_down) *geometries = 0;
  return ids;
}
static void report_reopen(const char *path, exr_fixed_document *first) {
  exr_fixed_document *second = NULL;
  exr_status status = exr_fixed_open(path, NULL, &second, &error);
  size_t count = 0, sample[3], n, i;
  int geometries = 0, ids = 1, renders = 1;
  member("reopen"); start_object();
  number_member("status", status);
  if (status != EXR_OK) { error_member(); end_object(); return; }
  ids = same_pages(first, second, &geometries);
  flag_member("ids_equal", ids);
  flag_member("geometry_equal", geometries);
  exr_fixed_pages(first, &count);
  n = sample_pages(count, sample);
  for (i = 0; renders && i < n; i++) {
    exr_bitmap a = {0}, b = {0};
    unsigned long long da = 0, db = 0;
    if (exr_fixed_render(first, sample[i], 1, NULL, &a, &error) == EXR_OK) da = bitmap_digest(&a);
    if (exr_fixed_render(second, sample[i], 1, NULL, &b, &error) == EXR_OK) db = bitmap_digest(&b);
    exr_bitmap_free(&a);
    exr_bitmap_free(&b);
    if (!da || da != db) renders = 0;
  }
  flag_member("render_equal", renders);
  end_object();
  exr_fixed_free(second);
}
/* Durable page identity: the stored reader keeps the same page IDs, a captured
   note keeps the page ID, and a second connection resolves both again. */
static void report_library(const char *path, const char *database, exr_fixed_document *direct) {
  exr_library *library = NULL, *again = NULL;
  exr_fixed_document *stored = NULL, *restored = NULL;
  exr_fixed_note note = {0}, *notes = NULL;
  size_t count = 0, note_count = 0, sample[3], n = 1, i;
  int64_t book = 0, note_id = 0;
  int created = 0, ids = 0, geometries = 0;
  exr_status status;
  unsigned long long direct_digest = 0, stored_digest = 0, restored_digest = 0;
  exr_bitmap bitmap = {0};
  member("library"); start_object();
  remove(database);
  status = exr_library_open(database, &library, &error);
  number_member("open_status", status);
  if (status != EXR_OK) { error_member(); end_object(); return; }
  status = exr_library_import_file_unique(library, EXR_CBZ, path, NULL, &book, &created, &error);
  number_member("import_status", status);
  number_member("created", created);
  if (status != EXR_OK) { error_member(); exr_library_close(library); end_object(); return; }
  status = exr_library_fixed(library, book, NULL, &stored, &error);
  number_member("stored_status", status);
  if (status == EXR_OK) {
    ids = same_pages(direct, stored, &geometries);
    flag_member("ids_equal", ids);
    flag_member("geometry_equal", geometries);
    exr_fixed_pages(direct, &count);
    n = sample_pages(count, sample);
    i = n > 1 ? sample[1] : 0;
    number_member("page", (long long)i);
    if (exr_fixed_render(direct, i, 1, NULL, &bitmap, &error) == EXR_OK) direct_digest = bitmap_digest(&bitmap);
    exr_bitmap_free(&bitmap);
    if (exr_fixed_render(stored, i, 1, NULL, &bitmap, &error) == EXR_OK) stored_digest = bitmap_digest(&bitmap);
    exr_bitmap_free(&bitmap);
    digest_member("direct_digest", direct_digest);
    digest_member("stored_digest", stored_digest);
    flag_member("render_equal", direct_digest != 0 && direct_digest == stored_digest);
    note.book_id = book;
    note.page = i;
    note.text = "s13 page identity";
    status = exr_library_fixed_note(library, &note, NULL, &note_id, &error);
    number_member("note_status", status);
    number_member("note_id", (long long)note_id);
    if (status == EXR_OK) {
      status = exr_library_fixed_notes(library, book, &notes, &note_count, &error);
      number_member("notes_status", status);
      number_member("note_count", (long long)note_count);
      text_member("note_page_id", note_count ? notes[0].anchor.page_id : "");
      flag_member("note_page_matches", note_count > 0 && !strcmp(notes[0].anchor.page_id, exr_fixed_pages(direct, &count)[i].id));
      exr_fixed_notes_free(notes, note_count);
      notes = NULL;
      note_count = 0;
    }
  }
  exr_fixed_free(stored);
  stored = NULL;
  exr_library_close(library);
  library = NULL;
  status = exr_library_open(database, &again, &error);
  number_member("reopen_status", status);
  if (status == EXR_OK) {
    status = exr_library_fixed(again, book, NULL, &restored, &error);
    number_member("restored_status", status);
    if (status == EXR_OK && n) {
      i = n > 1 ? sample[1] : 0;
      if (exr_fixed_render(restored, i, 1, NULL, &bitmap, &error) == EXR_OK) restored_digest = bitmap_digest(&bitmap);
      exr_bitmap_free(&bitmap);
      digest_member("restored_digest", restored_digest);
      flag_member("render_reopen_equal", restored_digest != 0 && restored_digest == direct_digest);
    }
    exr_fixed_free(restored);
    restored = NULL;
    status = exr_library_fixed_notes(again, book, &notes, &note_count, &error);
    number_member("note_reopen_status", status);
    number_member("note_reopen_count", (long long)note_count);
    text_member("note_reopen_page_id", note_count ? notes[0].anchor.page_id : "");
    flag_member("note_reopen_matches", note_count > 0 && direct_digest != 0 && !strcmp(notes[0].anchor.page_id, exr_fixed_pages(direct, &count)[n > 1 ? sample[1] : 0].id));
    exr_fixed_notes_free(notes, note_count);
    notes = NULL;
  }
  exr_library_close(again);
  end_object();
}

static int probe_cbz(const char *path, const char *database) {
  exr_fixed_document *document = NULL;
  exr_status status = exr_fixed_open(path, NULL, &document, &error);
  start_object();
  text_member("mode", "probe");
  text_member("input", path);
  member("open"); start_object();
  number_member("status", status);
  if (status == EXR_OK) text_member("title", exr_fixed_title(document));
  else error_member();
  end_object();
  if (status == EXR_OK) {
    report_pages(document);
    report_samples(document);
    report_fallback(document);
    report_capture(document);
    report_reopen(path, document);
    if (database) report_library(path, database, document);
    exr_fixed_free(document);
  }
  end_object();
  return 0;
}
static int probe_image(const char *path) {
  FILE *file = fopen(path, "rb");
  long size;
  unsigned char *data;
  exr_bitmap bitmap = {0};
  exr_status status;
  if (!file || fseek(file, 0, SEEK_END)) { fprintf(stderr, "cannot open %s\n", path); return 2; }
  size = ftell(file);
  if (size < 0) { fclose(file); return 2; }
  rewind(file);
  data = malloc((size_t)size ? (size_t)size : 1);
  if (!data || fread(data, 1, (size_t)size, file) != (size_t)size) { fclose(file); free(data); return 2; }
  fclose(file);
  status = exr_image_decode(data, (size_t)size, &bitmap, &error);
  start_object();
  text_member("mode", "image");
  text_member("input", path);
  member("open"); start_object();
  number_member("status", status);
  if (status == EXR_OK) {
    number_member("width", bitmap.width);
    number_member("height", bitmap.height);
    number_member("channels", bitmap.channels);
    digest_member("digest", bitmap_digest(&bitmap));
  } else error_member();
  end_object();
  end_object();
  exr_bitmap_free(&bitmap);
  free(data);
  return 0;
}
int main(int argc, char **argv) {
  int status = 0;
  if (argc == 3 && !strcmp(argv[1], "--image")) status = probe_image(argv[2]);
  else if ((argc == 3 || argc == 4) && !strcmp(argv[1], "--probe")) status = probe_cbz(argv[2], argc == 4 ? argv[3] : NULL);
  else { fprintf(stderr, "usage: %s --probe <file.cbz> [library.sqlite] | --image <image>\n", argv[0]); return 2; }
  if (status == 0) { fwrite(out ? out : "", 1, used, stdout); fputc('\n', stdout); }
  free(out);
  return status;
}
