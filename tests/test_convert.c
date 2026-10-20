/* SPDX-License-Identifier: MIT */
/* WP12-lite SDK matrix and preserve/render regression. Inputs come from
   tools/generate_conversion_corpus.py; this test consumes the SDK directly. */
#include "exreader.h"
#include <miniz.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static exr_error error;
static unsigned checks, passed, failed;
static FILE *json_file;
static char current[512];
static const char *targets[] = {"txt", "html", "fb2", "epub", "docx", "rtf"};
static const exr_format target_formats[] = {EXR_TXT, EXR_HTML, EXR_FB2, EXR_EPUB, EXR_DOCX, EXR_RTF};
static unsigned combo_expected[6][6], combo_passed[6][6];
static unsigned preserve_expected[4], preserve_passed[4];
static unsigned render_expected, render_passed;
static unsigned mobile_expected[6], mobile_passed[6];
static unsigned case_records;

typedef struct { char *data; size_t size, capacity; } buffer;
static int append(buffer *b, const void *data, size_t size) {
  if (b->size + size + 1 > b->capacity) {
    size_t capacity = b->capacity ? b->capacity : 256;
    char *next;
    while (capacity < b->size + size + 1) capacity *= 2;
    next = realloc(b->data, capacity);
    if (!next) return 0;
    b->data = next; b->capacity = capacity;
  }
  memcpy(b->data + b->size, data, size);
  b->size += size; b->data[b->size] = 0;
  return 1;
}
static int append_scalar(buffer *b, unsigned cp) {
  char bytes[4]; size_t n;
  if (cp < 0x80) { bytes[0] = (char)cp; n = 1; }
  else if (cp < 0x800) { bytes[0] = (char)(0xc0 | (cp >> 6)); bytes[1] = (char)(0x80 | (cp & 63)); n = 2; }
  else if (cp < 0x10000) { bytes[0] = (char)(0xe0 | (cp >> 12)); bytes[1] = (char)(0x80 | ((cp >> 6) & 63)); bytes[2] = (char)(0x80 | (cp & 63)); n = 3; }
  else { bytes[0] = (char)(0xf0 | (cp >> 18)); bytes[1] = (char)(0x80 | ((cp >> 12) & 63)); bytes[2] = (char)(0x80 | ((cp >> 6) & 63)); bytes[3] = (char)(0x80 | (cp & 63)); n = 4; }
  return append(b, bytes, n);
}
static int utf8(const unsigned char *p, size_t n, size_t *used, unsigned *cp) {
  if (!n) return 0;
  if (p[0] < 0x80) { *cp = p[0]; *used = 1; return 1; }
  if ((p[0] & 0xe0) == 0xc0 && n >= 2 && (p[1] & 0xc0) == 0x80) { *cp = ((unsigned)(p[0] & 31) << 6) | (p[1] & 63); *used = 2; return *cp >= 0x80; }
  if ((p[0] & 0xf0) == 0xe0 && n >= 3 && (p[1] & 0xc0) == 0x80 && (p[2] & 0xc0) == 0x80) {
    *cp = ((unsigned)(p[0] & 15) << 12) | ((unsigned)(p[1] & 63) << 6) | (p[2] & 63); *used = 3;
    return *cp >= 0x800 && (*cp < 0xd800 || *cp > 0xdfff);
  }
  if ((p[0] & 0xf8) == 0xf0 && n >= 4 && (p[1] & 0xc0) == 0x80 && (p[2] & 0xc0) == 0x80 && (p[3] & 0xc0) == 0x80) {
    *cp = ((unsigned)(p[0] & 7) << 18) | ((unsigned)(p[1] & 63) << 12) | ((unsigned)(p[2] & 63) << 6) | (p[3] & 63);
    *used = 4; return *cp >= 0x10000 && *cp <= 0x10ffff;
  }
  return 0;
}
static int normalize(const char *text, size_t size, buffer *out) {
  size_t at = 0; int pending = 0, any = 0;
  while (at < size) {
    unsigned cp; size_t used;
    if (!utf8((const unsigned char *)text + at, size - at, &used, &cp)) return 0;
    at += used;
    if (cp == ' ' || cp == '\t' || cp == '\n' || cp == '\r' || cp == '\f' || cp == '\v') { if (any) pending = 1; continue; }
    if (pending) { append(out, " ", 1); pending = 0; }
    append_scalar(out, cp); any = 1;
  }
  return 1;
}
static void json_escape(FILE *f, const char *s) {
  fputc('"', f);
  for (; s && *s; s++) {
    unsigned char c = (unsigned char)*s;
    if (c == '"' || c == '\\') { fputc('\\', f); fputc(c, f); }
    else if (c == '\n') fputs("\\n", f);
    else if (c == '\r') fputs("\\r", f);
    else if (c == '\t') fputs("\\t", f);
    else if (c < 0x20) fprintf(f, "\\u%04x", c);
    else fputc(c, f);
  }
  fputc('"', f);
}
static void record(const char *profile, const char *in, const char *out, int ok, const char *detail) {
  checks++;
  if (ok) passed++; else failed++;
  if (json_file) {
    if (case_records++) fputs(",\n", json_file);
    fputs("{\"case\":", json_file); json_escape(json_file, current);
    fputs(",\"profile\":", json_file); json_escape(json_file, profile);
    fputs(",\"input_format\":", json_file); json_escape(json_file, in);
    fputs(",\"output_format\":", json_file); json_escape(json_file, out);
    fputs(",\"status\":", json_file); json_escape(json_file, ok ? "pass" : "fail");
    fputs(",\"detail\":", json_file); json_escape(json_file, detail ? detail : "");
    fputs("}\n", json_file);
  }
  if (!ok) fprintf(stderr, "FAIL %s %s->%s %s (%s)\n", current, in, out, detail ? detail : "", error.message);
}
static exr_document *open_path(const char *path) {
  exr_document *doc = NULL;
  if (exr_document_open(path, &doc, &error) != EXR_OK) {
    fprintf(stderr, "open %s failed: %s\n", path, error.message);
    return NULL;
  }
  return doc;
}
static int text_ok(exr_document *a, exr_document *b) {
  size_t an = 0, bn = 0;
  const char *at = exr_document_text(a, &an), *bt = exr_document_text(b, &bn);
  buffer na = {0}, nb = {0};
  int ok;
  if (!normalize(at ? at : "", an, &na) || !normalize(bt ? bt : "", bn, &nb)) ok = 0;
  else ok = na.size == nb.size && (!na.size || !memcmp(na.data, nb.data, na.size));
  free(na.data); free(nb.data);
  return ok;
}
static int blocks_in_order(exr_document *a, exr_document *b) {
  size_t an = 0, bn = 0, i;
  const exr_block *blocks = exr_document_blocks(a, &an);
  size_t bsize = 0;
  const char *bt = exr_document_text(b, &bsize);
  buffer nb = {0};
  size_t position = 0;
  int ok = 1;
  if (!normalize(bt ? bt : "", bsize, &nb)) return 0;
  for (i = 0; i < an && ok; i++) {
    buffer block = {0};
    size_t j;
    if (blocks[i].end <= blocks[i].start) continue;
    if (!normalize((const char *)exr_document_text(a, NULL) + blocks[i].start,
                   blocks[i].end - blocks[i].start, &block)) { ok = 0; free(block.data); break; }
    if (!block.size) { free(block.data); continue; }
    for (j = position; j + block.size <= nb.size; j++)
      if (!memcmp(nb.data + j, block.data, block.size)) break;
    if (j + block.size > nb.size) ok = 0;
    else position = j + block.size;
    free(block.data);
  }
  free(nb.data);
  return ok;
}
static int find_resource(const exr_document *doc, const char *path, size_t *index) {
  const exr_resource *resources;
  size_t count, i;
  resources = exr_document_resources(doc, &count);
  for (i = 0; i < count; i++) if (resources[i].path && !strcmp(resources[i].path, path)) { *index = i; return 1; }
  return 0;
}
static int resources_ok(exr_document *a, exr_document *b) {
  const exr_resource *ra, *rb;
  size_t na, nb, i, j;
  ra = exr_document_resources(a, &na); rb = exr_document_resources(b, &nb);
  for (i = 0; i < na; i++) {
    if (!find_resource(b, ra[i].path, &j)) return 0;
    if (strcmp(ra[i].media_type ? ra[i].media_type : "", rb[j].media_type ? rb[j].media_type : "")) return 0;
    if (ra[i].media_type && !strcmp(ra[i].media_type, "application/xhtml+xml")) continue;
    {
      void *ba = NULL, *bb = NULL; size_t sa = 0, sb = 0; exr_error e = {0};
      if (exr_document_resource(a, i, &ba, &sa, &e) != EXR_OK ||
          exr_document_resource(b, j, &bb, &sb, &e) != EXR_OK || sa != sb || (sa && memcmp(ba, bb, sa))) {
        exr_free(ba); exr_free(bb); return 0;
      }
      exr_free(ba); exr_free(bb);
    }
  }
  return 1;
}
static int spine_ok(exr_document *a, exr_document *b, int strict_paths) {
  const exr_chapter *ca, *cb; size_t na, nb, i, j = 0;
  ca = exr_document_chapters(a, &na); cb = exr_document_chapters(b, &nb);
  for (i = 0; i < na; i++) if (ca[i].in_spine) {
    while (j < nb && !cb[j].in_spine) j++;
    if (j >= nb || ca[i].linear != cb[j].linear) return 0;
    /* A standalone XHTML input has no authored package path; the exporter
       generates a collision-free chapter path. Reading order and linear flags
       are still compared. EPUB inputs must retain their exact paths. */
    if (strict_paths && (!ca[i].path || !cb[j].path || strcmp(ca[i].path, cb[j].path))) return 0;
    j++;
  }
  while (j < nb && !cb[j].in_spine) j++;
  return j >= nb;
}
static int links_ok(exr_document *a, exr_document *b) {
  const exr_node *nodes; size_t count, i;
  nodes = exr_document_nodes(a, &count);
  for (i = 0; i < count; i++) {
    const char *href = exr_node_attribute(&nodes[i], "href");
    size_t ra = SIZE_MAX, rb = SIZE_MAX, na = SIZE_MAX, nb = SIZE_MAX;
    exr_error e = {0};
    if (!href || !*href || strchr(href, ':')) continue;
    if (exr_document_resolve(a, nodes[i].chapter, href, &ra, &na, &e) != EXR_OK) return 0;
    if (exr_document_resolve(b, nodes[i].chapter, href, &rb, &nb, &e) != EXR_OK) return 0;
    if ((ra == SIZE_MAX) != (rb == SIZE_MAX)) return 0;
    if ((na == SIZE_MAX) != (nb == SIZE_MAX)) return 0;
  }
  return 1;
}
static int render_compare(exr_document *a, exr_document *b, exr_font *font) {
  exr_layout_config config = exr_layout_config_defaults();
  exr_layout *la = NULL, *lb = NULL;
  const exr_page *pa, *pb; size_t na, nb, i;
  const exr_glyph *ga, *gb; size_t gna, gnb;
  int ok = 0;
  config.page = (exr_layout_options){240, 160, 12, 18, 1.3f, 0};
  config.document_css = 1;
  if (exr_layout_create_ex(a, font, &config, &la, &error) != EXR_OK) goto done;
  if (exr_layout_create_ex(b, font, &config, &lb, &error) != EXR_OK) goto done;
  pa = exr_layout_pages(la, &na); pb = exr_layout_pages(lb, &nb);
  if (na != nb) goto done;
  for (i = 0; i < na; i++) {
    exr_bitmap ba = {0}, bb = {0};
    if (pa[i].start != pb[i].start || pa[i].end != pb[i].end) goto done;
    if (exr_render_page(la, NULL, i, &ba, &error) != EXR_OK ||
        exr_render_page(lb, NULL, i, &bb, &error) != EXR_OK) {
      exr_bitmap_free(&ba); exr_bitmap_free(&bb); goto done;
    }
    if (ba.width != bb.width || ba.height != bb.height || ba.stride != bb.stride ||
        memcmp(ba.pixels, bb.pixels, (size_t)ba.stride * ba.height)) {
      exr_bitmap_free(&ba); exr_bitmap_free(&bb); goto done;
    }
    exr_bitmap_free(&ba); exr_bitmap_free(&bb);
  }
  ga = exr_layout_glyphs(la, &gna); gb = exr_layout_glyphs(lb, &gnb);
  if (gna != gnb) goto done;
  for (i = 0; i < gna; i++) {
    if (ga[i].start != gb[i].start || ga[i].end != gb[i].end ||
        ga[i].glyph != gb[i].glyph || ga[i].font_index != gb[i].font_index) goto done;
    if (fabs((double)ga[i].x - (double)gb[i].x) > 0.01 ||
        fabs((double)ga[i].baseline - (double)gb[i].baseline) > 0.01 ||
        fabs((double)ga[i].advance - (double)gb[i].advance) > 0.01 ||
        fabs((double)ga[i].size - (double)gb[i].size) > 0.01) goto done;
  }
  ok = 1;
done:
  exr_layout_free(la); exr_layout_free(lb);
  return ok;
}
static int html_bundle_ok(exr_document *source, const void *data, size_t size, const char *entry) {
  mz_zip_archive zip; const exr_chapter *chapters; const exr_resource *resources;
  size_t nc, nr, i; int ok = 0;
  memset(&zip, 0, sizeof(zip));
  if (!mz_zip_reader_init_mem(&zip, data, size, 0)) return 0;
  {
    size_t n = 0; void *body = mz_zip_reader_extract_file_to_heap(&zip, entry, &n, 0);
    exr_document *d = NULL; exr_error e = {0};
    if (!body) goto done;
    ok = exr_document_open_memory(EXR_HTML, body, n, &d, &e) == EXR_OK;
    exr_document_free(d); mz_free(body);
    if (!ok) goto done;
  }
  chapters = exr_document_chapters(source, &nc);
  for (i = 0; i < nc; i++) if (chapters[i].path && *chapters[i].path &&
      mz_zip_reader_locate_file(&zip, chapters[i].path, NULL, 0) < 0) { ok = 0; goto done; }
  resources = exr_document_resources(source, &nr);
  for (i = 0; i < nr; i++) if (resources[i].path && *resources[i].path &&
      mz_zip_reader_locate_file(&zip, resources[i].path, NULL, 0) < 0) { ok = 0; goto done; }
  ok = 1;
done:
  mz_zip_reader_end(&zip);
  return ok;
}
static void text_case(const char *corpus, const char *fmt, const char *theme, const char *rel) {
  char path[4096], label[256];
  exr_document *source;
  snprintf(path, sizeof(path), "%s/%s", corpus, rel);
  snprintf(label, sizeof(label), "%s-%s", fmt, theme);
  snprintf(current, sizeof(current), "%s", label);
  source = open_path(path);
  if (!source) return;
  for (int t = 0; t < 6; t++) {
    void *data = NULL; size_t size = 0;
    exr_document *out = NULL;
    int ok = 1; char detail[128] = "";
    if (exr_document_export_control(source, target_formats[t], NULL, &data, &size, &error) != EXR_OK) {
      ok = 0; snprintf(detail, sizeof(detail), "export: %s", error.message);
    } else if (!data || !size) { ok = 0; snprintf(detail, sizeof(detail), "empty export"); }
    else if (exr_document_open_memory(target_formats[t], data, size, &out, &error) != EXR_OK) {
      ok = 0; snprintf(detail, sizeof(detail), "reopen: %s", error.message);
    } else if (target_formats[t] == EXR_TXT) {
      size_t an = 0, bn = 0;
      const char *at = exr_document_text(source, &an), *bt = exr_document_text(out, &bn);
      ok = an == bn && (!an || !memcmp(at, bt, an));
      if (!ok) snprintf(detail, sizeof(detail), "TXT bytes differ");
    } else {
      ok = text_ok(source, out) && blocks_in_order(source, out);
      if (!ok) snprintf(detail, sizeof(detail), "normalized text or paragraph order differs");
    }
    record("text", fmt, targets[t], ok, detail);
    for (int s = 0; s < 6; s++) if (!strcmp(fmt, targets[s])) {
      combo_expected[s][t]++; if (ok) combo_passed[s][t]++;
    }
    exr_document_free(out); exr_free(data);
  }
  exr_document_free(source);
}
static void mobile_case(const char *corpus, const char *variant, const char *name, const char *rel) {
  char path[4096];
  exr_document *source;
  snprintf(path, sizeof(path), "%s/%s", corpus, rel);
  snprintf(current, sizeof(current), "mobile-%s-%s", variant, name);
  source = open_path(path);
  if (!source) return;
  for (int t = 0; t < 6; t++) {
    void *data = NULL; size_t size = 0; exr_document *out = NULL;
    int ok = 1; char detail[128] = "";
    if (exr_document_export_control(source, target_formats[t], NULL, &data, &size, &error) != EXR_OK) {
      ok = 0; snprintf(detail, sizeof(detail), "export: %s", error.message);
    } else if (exr_document_open_memory(target_formats[t], data, size, &out, &error) != EXR_OK) {
      ok = 0; snprintf(detail, sizeof(detail), "reopen: %s", error.message);
    } else if (target_formats[t] == EXR_TXT) {
      size_t an = 0, bn = 0; const char *at = exr_document_text(source, &an), *bt = exr_document_text(out, &bn);
      ok = an == bn && (!an || !memcmp(at, bt, an));
      if (!ok) snprintf(detail, sizeof(detail), "TXT bytes differ");
    } else {
      ok = text_ok(source, out) && blocks_in_order(source, out);
      if (!ok) snprintf(detail, sizeof(detail), "normalized text or paragraph order differs");
    }
    record("text", variant, targets[t], ok, detail);
    mobile_expected[t]++; if (ok) mobile_passed[t]++;
    exr_document_free(out); exr_free(data);
  }
  exr_document_free(source);
}
static void preserve_case(const char *corpus, const char *input_format, const char *theme,
                          const char *rel, exr_font *font) {
  char path[4096];
  exr_document *source;
  snprintf(path, sizeof(path), "%s/%s", corpus, rel);
  snprintf(current, sizeof(current), "preserve-%s-%s", input_format, theme);
  source = open_path(path);
  if (!source) return;
  for (int mode = 0; mode < 2; mode++) {
    void *data = NULL, *entry_owned = NULL; size_t size = 0; exr_document *out = NULL;
    int ok = 1; char detail[160] = "";
    int slot = (!strcmp(input_format, "epub") ? 0 : 2) + mode;
    preserve_expected[slot]++;
    if (mode == 0) {
      if (exr_document_export_epub(source, NULL, &data, &size, &error) != EXR_OK) {
        ok = 0; snprintf(detail, sizeof(detail), "export_epub: %s", error.message);
      } else if (exr_document_open_memory(EXR_EPUB, data, size, &out, &error) != EXR_OK) {
        ok = 0; snprintf(detail, sizeof(detail), "reopen epub: %s", error.message);
      } else {
        int text = text_ok(source, out), spine = spine_ok(source, out, !strcmp(input_format, "epub")),
            resources = resources_ok(source, out), links = links_ok(source, out);
        ok = text && spine && resources && links;
        if (!ok) snprintf(detail, sizeof(detail), "epub text=%d spine=%d resources=%d links=%d",
                          text, spine, resources, links);
        else if (font) {
          render_expected++;
          if (render_compare(source, out, font)) render_passed++;
          else { ok = 0; snprintf(detail, sizeof(detail), "render pages/glyphs/pixels differ"); }
        }
      }
    } else {
      char *entry = NULL;
      if (exr_document_export_html_bundle(source, NULL, &data, &size, &entry, &error) != EXR_OK) {
        ok = 0; snprintf(detail, sizeof(detail), "export_html_bundle: %s", error.message);
      } else if (!entry || !*entry) { ok = 0; snprintf(detail, sizeof(detail), "missing entry path"); }
      else if (!html_bundle_ok(source, data, size, entry)) { ok = 0; snprintf(detail, sizeof(detail), "bundle entry/chapters/resources differ"); }
      entry_owned = entry;
    }
    record("preserve", input_format, mode ? "html" : "epub", ok, detail);
    if (ok) preserve_passed[slot]++;
    exr_document_free(out); exr_free(data); exr_free(entry_owned);
  }
  exr_document_free(source);
}
static char **read_lines(const char *path, size_t *count) {
  FILE *f = fopen(path, "rb"); char line[4096]; char **lines = NULL;
  *count = 0;
  if (!f) { fprintf(stderr, "cannot read %s\n", path); return NULL; }
  while (fgets(line, sizeof(line), f)) {
    size_t n = strlen(line);
    char *copy;
    while (n && (line[n - 1] == '\n' || line[n - 1] == '\r')) line[--n] = 0;
    if (!n) continue;
    copy = malloc(n + 1); if (!copy) break;
    memcpy(copy, line, n + 1);
    {
      char **next = realloc(lines, (*count + 1) * sizeof(*next));
      if (!next) { free(copy); break; }
      lines = next; lines[(*count)++] = copy;
    }
  }
  fclose(f);
  return lines;
}
static void split(char *line, char **fields, size_t count) {
  size_t i = 0; char *p = line;
  for (i = 0; i < count; i++) {
    fields[i] = p;
    p = strchr(p, '|');
    if (p) *p++ = 0; else break;
  }
}
int main(int argc, char **argv) {
  char matrix_path[4096], mobile_path[4096], font_path[4096];
  char **lines; size_t count, i;
  exr_font *font = NULL;
  if (argc < 3) { fprintf(stderr, "usage: %s CORPUS FONT [JSON]\n", argv[0]); return 2; }
  snprintf(font_path, sizeof(font_path), "%s", argv[2]);
  if (exr_font_open(font_path, &font, &error) != EXR_OK) {
    fprintf(stderr, "font open failed: %s\n", error.message);
    return 2;
  }
  if (argc > 3) {
    json_file = fopen(argv[3], "wb");
    if (json_file) fputs("{\"schema\":1,\"cases\":[\n", json_file);
  }
  snprintf(matrix_path, sizeof(matrix_path), "%s/matrix.txt", argv[1]);
  lines = read_lines(matrix_path, &count);
  if (!lines) return 2;
  for (i = 0; i < count; i++) {
    char *fields[4]; split(lines[i], fields, 4);
    if (!strcmp(fields[0], "text")) text_case(argv[1], fields[1], fields[2], fields[3]);
    free(lines[i]);
  }
  free(lines);
  snprintf(mobile_path, sizeof(mobile_path), "%s/mobile.txt", argv[1]);
  lines = read_lines(mobile_path, &count);
  if (lines) {
    for (i = 0; i < count; i++) {
      char *fields[4]; split(lines[i], fields, 4);
      if (!strcmp(fields[0], "mobile")) mobile_case(argv[1], fields[1], fields[2], fields[3]);
      free(lines[i]);
    }
    free(lines);
  }
  for (i = 0; i < 10; i++) {
    char rel[128]; char theme[64];
    static const char *themes[] = {"ascii","chinese","rtl","supplementary","special",
                                   "whitespace","structure","multichapter","long","metadata"};
    snprintf(theme, sizeof(theme), "%s", themes[i]);
    snprintf(rel, sizeof(rel), "preserve/epub/%s.epub", theme);
    preserve_case(argv[1], "epub", theme, rel, font);
    snprintf(rel, sizeof(rel), "preserve/xhtml/%s.xhtml", theme);
    preserve_case(argv[1], "xhtml", theme, rel, font);
  }
  if (json_file) {
    fprintf(json_file, "],\"kind\":\"sdk-matrix\",\"engine_version\":\"%s\","
            "\"expected\":%u,\"actual\":%u,\"passed\":%u,\"failed\":%u,\"checks\":%u,"
            "\"text_combos\":[", exr_version(), passed + failed, passed + failed, passed, failed, checks);
    for (int s = 0; s < 6; s++) for (int t = 0; t < 6; t++)
      fprintf(json_file, "%s{\"input\":\"%s\",\"output\":\"%s\",\"expected\":%u,\"passed\":%u}",
              (s || t) ? "," : "", targets[s], targets[t], combo_expected[s][t], combo_passed[s][t]);
    fprintf(json_file, "],\"mobile_combos\":[");
    for (int t = 0; t < 6; t++)
      fprintf(json_file, "%s{\"input\":\"mobi/kf8\",\"output\":\"%s\",\"expected\":%u,\"passed\":%u}",
              t ? "," : "", targets[t], mobile_expected[t], mobile_passed[t]);
    fprintf(json_file, "],\"preserve_combos\":[");
    for (int s = 0; s < 4; s++)
      fprintf(json_file, "%s{\"input\":\"%s\",\"output\":\"%s\",\"expected\":%u,\"passed\":%u}",
              s ? "," : "", s < 2 ? "epub" : "xhtml", s % 2 ? "html" : "epub",
              preserve_expected[s], preserve_passed[s]);
    fprintf(json_file, "],\"render\":{\"expected\":%u,\"passed\":%u}}\n", render_expected, render_passed);
    fclose(json_file);
  }
  exr_font_free(font);
  printf("convert matrix: %u checks, %u passed, %u failed; %u render checks (%u passed)\n",
         checks, passed, failed, render_expected, render_passed);
  return failed ? 1 : 0;
}
