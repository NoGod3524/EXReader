/* SPDX-License-Identifier: MIT */
/* Installed-SDK consumer for the reader real-corpus acceptance package.
   It never links against build-tree objects: CMake resolves EXReader::exreader
   from the installed SDK prefix. One process handles one document. */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <ctype.h>
#include <time.h>

#ifdef _WIN32
#include <direct.h>
#define make_dir(p) _mkdir(p)
#else
#include <sys/stat.h>
#define make_dir(p) mkdir((p), 0777)
#endif

typedef struct {
  int ok;
  size_t width, height, channels, stride;
  uint64_t fnv;
} render_info;

static uint64_t fnv1a(const unsigned char *p, size_t n) {
  uint64_t h = 1469598103934665603ULL;
  for (size_t i = 0; i < n; i++) { h ^= p[i]; h *= 1099511628211ULL; }
  return h;
}

static void json_string(const char *s) {
  if (!s) { fputs("null", stdout); return; }
  putchar('"');
  for (const unsigned char *p = (const unsigned char *)s; *p; p++) {
    switch (*p) {
      case '"': fputs("\\\"", stdout); break;
      case '\\': fputs("\\\\", stdout); break;
      case '\n': fputs("\\n", stdout); break;
      case '\r': fputs("\\r", stdout); break;
      case '\t': fputs("\\t", stdout); break;
      default:
        if (*p < 0x20) printf("\\u%04x", *p); else putchar(*p);
    }
  }
  putchar('"');
}

static double now_ms(void) {
  struct timespec ts;
  timespec_get(&ts, TIME_UTC);
  return (double)ts.tv_sec * 1000.0 + (double)ts.tv_nsec / 1e6;
}

static void render_bitmap(const exr_bitmap *bitmap, render_info *out) {
  memset(out, 0, sizeof(*out));
  if (!bitmap || !bitmap->pixels || !bitmap->width || !bitmap->height ||
      !bitmap->stride || (bitmap->channels != 1 && bitmap->channels != 4)) return;
  size_t bytes = (size_t)bitmap->stride * bitmap->height;
  out->ok = 1;
  out->width = bitmap->width; out->height = bitmap->height;
  out->channels = bitmap->channels; out->stride = bitmap->stride;
  out->fnv = fnv1a(bitmap->pixels, bytes);
}

static void print_render(const char *name, const render_info *r) {
  printf("\"%s\":{\"outcome\":\"%s\",\"width\":%zu,\"height\":%zu,\"channels\":%zu,\"stride\":%zu,\"fnv1a64\":\"%016llx\"}",
         name, r->ok ? "ok" : "failed", r->width, r->height, r->channels, r->stride,
         (unsigned long long)r->fnv);
}

typedef struct {
  size_t pages;
  int has_title;
  char title[1024];
} part_info;

static void store_title(char *dst, size_t cap, const char *src) {
  if (!src) { dst[0] = 0; return; }
  snprintf(dst, cap, "%s", src);
}

/* Renders page 0 and the final page while counting sequentially. Keeps the
   previous two page layouts so the final page and the preceding page can be
   rendered without a second full pass. */
static exr_status count_and_render_part(exr_document *doc, exr_font *font, int first,
                                        render_info *first_render, render_info *last_render,
                                        render_info *back_render, size_t *pages,
                                        exr_error *error) {
  exr_layout_config config = exr_layout_config_defaults();
  exr_pager *pager = NULL;
  exr_layout *prev = NULL, *prev2 = NULL, *page = NULL;
  exr_status status;
  size_t index = 0;
  config.page = (exr_layout_options){720, 1040, 36, 28, 1.5f, 10};
  config.document_css = 1;
  status = exr_pager_create(doc, font, &config, &pager, error);
  if (status != EXR_OK) return status;
  for (;;) {
    status = exr_pager_next(pager, &page, error);
    if (status != EXR_OK || !page) break;
    index++;
    if (first && index == 1) {
      exr_bitmap bitmap = {0};
      exr_status rs = exr_render_page_color(page, exr_layout_font(page), 0, &bitmap, error);
      if (rs == EXR_OK) render_bitmap(&bitmap, first_render);
      exr_bitmap_free(&bitmap);
    }
    exr_layout_free(prev2);
    prev2 = prev; prev = page; page = NULL;
  }
  if (status == EXR_OK && prev) {
    if (last_render) {
      exr_bitmap bitmap = {0};
      exr_status rs = exr_render_page_color(prev, exr_layout_font(prev), 0, &bitmap, error);
      if (rs == EXR_OK) render_bitmap(&bitmap, last_render);
      exr_bitmap_free(&bitmap);
    }
    if (back_render && prev2) {
      exr_bitmap bitmap = {0};
      exr_status rs = exr_render_page_color(prev2, exr_layout_font(prev2), 0, &bitmap, error);
      if (rs == EXR_OK) render_bitmap(&bitmap, back_render);
      exr_bitmap_free(&bitmap);
    }
  }
  exr_layout_free(prev); exr_layout_free(prev2); exr_layout_free(page);
  exr_pager_free(pager);
  *pages = index;
  return status;
}

static exr_status render_part_page(exr_document *doc, exr_font *font, size_t index,
                                   render_info *out, exr_error *error) {
  exr_layout_config config = exr_layout_config_defaults();
  exr_pager *pager = NULL;
  const exr_layout *page = NULL;
  exr_status status;
  config.page = (exr_layout_options){720, 1040, 36, 28, 1.5f, 10};
  config.document_css = 1;
  status = exr_pager_create(doc, font, &config, &pager, error);
  if (status != EXR_OK) return status;
  status = exr_pager_set_cache(pager, 4, 64u * 1024u * 1024u, error);
  if (status == EXR_OK) status = exr_pager_set_checkpoints(pager, 64, 8u * 1024u * 1024u, 16, error);
  if (status == EXR_OK) status = exr_pager_get(pager, index, &page, error);
  if (status == EXR_OK && page) {
    exr_bitmap bitmap = {0};
    status = exr_render_page_color(page, exr_layout_font(page), 0, &bitmap, error);
    if (status == EXR_OK) render_bitmap(&bitmap, out);
    exr_bitmap_free(&bitmap);
  } else if (status == EXR_OK) status = EXR_FORMAT;
  exr_pager_free(pager);
  return status;
}

static int read_file_bytes(const char *path, void **data, size_t *size) {
  FILE *f = fopen(path, "rb");
  long n;
  if (!f) return 0;
  if (fseek(f, 0, SEEK_END) != 0) { fclose(f); return 0; }
  n = ftell(f);
  if (n < 0 || fseek(f, 0, SEEK_SET) != 0) { fclose(f); return 0; }
  *data = n ? malloc((size_t)n) : NULL;
  if (n && (!*data || fread(*data, 1, (size_t)n, f) != (size_t)n)) {
    free(*data); *data = NULL; fclose(f); return 0;
  }
  fclose(f); *size = (size_t)n; return 1;
}

static exr_format parse_format(const char *name) {
  if (!strcmp(name, "TXT")) return EXR_TXT;
  if (!strcmp(name, "HTML")) return EXR_HTML;
  if (!strcmp(name, "FB2")) return EXR_FB2;
  if (!strcmp(name, "EPUB")) return EXR_EPUB;
  if (!strcmp(name, "DOCX")) return EXR_DOCX;
  if (!strcmp(name, "RTF")) return EXR_RTF;
  if (!strcmp(name, "MOBI")) return EXR_MOBI;
  if (!strcmp(name, "PDF")) return EXR_PDF;
  if (!strcmp(name, "CBZ")) return EXR_CBZ;
  return EXR_CUSTOM;
}

static int fixed_format(exr_format f) { return f == EXR_PDF || f == EXR_CBZ; }

int main(int argc, char **argv) {
  const char *file = NULL, *format_name = NULL, *font_path = NULL, *outdir = NULL, *query = NULL;
  exr_format format;
  exr_font *font = NULL;
  exr_library *library = NULL;
  exr_document *doc = NULL;
  exr_publication *publication = NULL;
  exr_fixed_document *fixed = NULL;
  exr_error error = {0};
  exr_status status;
  int64_t book_id = 0;
  void *blob = NULL;
  size_t blob_size = 0, parts = 0, total_pages = 0, reopen_pages = 0;
  char readback_path[4096];
  char library_path[4096];
  char title[1024] = {0};
  part_info *part = NULL;
  int import_ok = 0, readback_ok = 0, open_ok = 0, toc_ok = 0;
  int pages_ok = 0, seq_ok = 0, find_ok = 0, anchor_capture = 0, anchor_resolve = 0, anchor_reopen = 0;
  int reopen_ok = 0;
  const char *open_kind = "reflow";
  char find_outcome[32] = "not_exposed";
  size_t find_part = SIZE_MAX, find_page = SIZE_MAX, find_start = SIZE_MAX, find_end = SIZE_MAX;
  char anchor_state_same[32] = "none", anchor_state_reopen[32] = "none";
  char anchor_reopen_error[256] = "";
  size_t metadata_entries = 0, fixed_text_pages = 0;
  char first_key[256] = {0};
  size_t toc_count = 0;
  char toc_label[512] = {0};
  size_t part_index = 0;
  render_info first_render = {0}, middle_render = {0}, last_render = {0}, back_render = {0};
  double t0 = now_ms(), t_import = 0, t_open = 0, t_pages = 0, t_find = 0, t_reopen = 0;
  exr_anchor anchor = {0};
  exr_fixed_anchor fanchor = {0};
  size_t anchor_page = SIZE_MAX;
  int have_anchor = 0, have_fanchor = 0;

  if (argc < 7) {
    fprintf(stderr, "usage: %s --format F --file PATH --font PATH --out DIR --query TEXT\n", argv[0]);
    return 2;
  }
  for (int i = 1; i + 1 < argc; i += 2) {
    if (!strcmp(argv[i], "--format")) format_name = argv[i + 1];
    else if (!strcmp(argv[i], "--file")) file = argv[i + 1];
    else if (!strcmp(argv[i], "--font")) font_path = argv[i + 1];
    else if (!strcmp(argv[i], "--out")) outdir = argv[i + 1];
    else if (!strcmp(argv[i], "--query")) query = argv[i + 1];
    else { fprintf(stderr, "unknown argument %s\n", argv[i]); return 2; }
  }
  if (!file || !format_name || !font_path || !outdir || !query) return 2;
  format = parse_format(format_name);
  if (format == EXR_CUSTOM) { fprintf(stderr, "unknown format %s\n", format_name); return 2; }
  make_dir(outdir);
  snprintf(readback_path, sizeof(readback_path), "%s/readback.bin", outdir);
  snprintf(library_path, sizeof(library_path), "%s/library.sqlite", outdir);

  status = exr_font_open(font_path, &font, &error);
  if (status != EXR_OK) { fprintf(stderr, "font: %s\n", error.message); return 3; }

  /* 1. Public import plus original-byte readback through the library API. */
  t_import = now_ms();
  status = exr_library_open(library_path, &library, &error);
  if (status == EXR_OK) {
    if (fixed_format(format)) {
      status = exr_library_import_file(library, format, file, NULL, &book_id, &error);
    } else {
      void *bytes = NULL; size_t bytes_size = 0;
      if (!read_file_bytes(file, &bytes, &bytes_size)) status = EXR_IO;
      else status = exr_library_import(library, format, bytes, bytes_size, NULL, &book_id, &error);
      free(bytes);
    }
    if (status == EXR_OK) import_ok = 1;
    if (status == EXR_OK) status = exr_library_blob(library, book_id, 0, &blob, &blob_size, &error);
    if (status == EXR_OK && blob_size) {
      FILE *f = fopen(readback_path, "wb");
      if (f && fwrite(blob, 1, blob_size, f) == blob_size) readback_ok = 1;
      if (f) fclose(f);
    }
    exr_free(blob); blob = NULL;
    exr_library_close(library); library = NULL;
  }
  t_import = now_ms() - t_import;

  /* 2. Open through the installed public API. EPUB uses the indexed publication. */
  t_open = now_ms();
  if (format == EXR_EPUB) {
    status = exr_publication_open(file, &publication, &error);
    if (status == EXR_OK) {
      open_ok = 1;
      store_title(title, sizeof(title), exr_publication_title(publication));
      const exr_part *p = exr_publication_parts(publication, &parts);
      (void)p;
    }
  } else if (fixed_format(format)) {
    exr_fixed_open_options options = {0};
    options.struct_size = sizeof(options);
    options.fallback_font = font;
    open_kind = "fixed";
    status = exr_fixed_open(file, &options, &fixed, &error);
    if (status == EXR_OK) {
      const exr_fixed_page *pages = exr_fixed_pages(fixed, &parts);
      (void)pages;
      open_ok = 1;
      store_title(title, sizeof(title), exr_fixed_title(fixed));
    }
  } else {
    status = exr_document_open(file, &doc, &error);
    if (status == EXR_OK) {
      open_ok = 1; parts = 1;
      store_title(title, sizeof(title), exr_document_title(doc));
    }
  }
  t_open = now_ms() - t_open;

  /* 3. Metadata and authored navigation. */
  if (open_ok) {
    if (fixed) {
      exr_metadata_entry *entries = NULL;
      size_t count = 0;
      status = exr_fixed_load_metadata(fixed, NULL, &entries, &count, &error);
      if (status == EXR_OK) {
        metadata_entries = count;
        if (count) store_title(first_key, sizeof(first_key), entries[0].key);
        exr_metadata_free(entries, count);
      }
    }
    if (publication) {
      const exr_navigation *nav = NULL;
      size_t count = 0;
      status = exr_publication_navigation(publication, &nav, &count, &error);
      if (status == EXR_OK) { toc_ok = 1; toc_count = count; if (count) store_title(toc_label, sizeof(toc_label), nav[0].label); }
    } else if (doc) {
      exr_navigation *nav = NULL;
      size_t count = 0;
      status = exr_document_navigation(doc, &nav, &count, &error);
      if (status == EXR_OK) { toc_ok = 1; toc_count = count; if (count) store_title(toc_label, sizeof(toc_label), nav[0].label); exr_navigation_free(nav, count); }
    }
  }

  /* 4. Page traversal: first, middle, last, sequential order, and one step back. */
  t_pages = now_ms();
  if (open_ok) {
    if (fixed) {
      const exr_fixed_page *fp = exr_fixed_pages(fixed, &total_pages);
      if (fp && total_pages) {
        size_t mid = total_pages / 2;
        seq_ok = 1;
        for (size_t i = 0; i < total_pages; i++) {
          exr_fixed_text *text = NULL;
          status = exr_fixed_load_text(fixed, i, NULL, &text, &error);
          exr_fixed_text_free(text);
          if (status != EXR_OK) { seq_ok = 0; break; }
        }
        if (total_pages) {
          double w = (fp[0].geometry.bounds[2] - fp[0].geometry.bounds[0]) * fp[0].geometry.unit_scale;
          double h = (fp[0].geometry.bounds[3] - fp[0].geometry.bounds[1]) * fp[0].geometry.unit_scale;
          double scale = (w > 0 && h > 0) ? (720.0 / (w > h ? w : h)) : 1.0;
          if (scale > 1) scale = 1;
          exr_bitmap bitmap = {0};
          if (exr_fixed_render(fixed, 0, scale, NULL, &bitmap, &error) == EXR_OK) render_bitmap(&bitmap, &first_render);
          exr_bitmap_free(&bitmap);
          if (exr_fixed_render(fixed, mid, scale, NULL, &bitmap, &error) == EXR_OK) render_bitmap(&bitmap, &middle_render);
          exr_bitmap_free(&bitmap);
          if (exr_fixed_render(fixed, total_pages - 1, scale, NULL, &bitmap, &error) == EXR_OK) render_bitmap(&bitmap, &last_render);
          exr_bitmap_free(&bitmap);
          if (total_pages > 1 && exr_fixed_render(fixed, total_pages - 2, scale, NULL, &bitmap, &error) == EXR_OK) render_bitmap(&bitmap, &back_render);
          exr_bitmap_free(&bitmap);
          pages_ok = first_render.ok && middle_render.ok && last_render.ok && back_render.ok && seq_ok;
        }
      }
    } else {
      part = calloc(parts ? parts : 1, sizeof(*part));
      if (!part) return 4;
      int count_ok = 1;
      for (part_index = 0; part_index < parts; part_index++) {
        exr_document *pd = doc;
        if (publication) {
          status = exr_publication_load(publication, part_index, &pd, &error);
          if (status != EXR_OK) { count_ok = 0; break; }
        }
        store_title(part[part_index].title, sizeof(part[part_index].title), exr_document_title(pd));
        part[part_index].has_title = part[part_index].title[0] != 0;
        render_info first = {0}, last = {0}, back = {0};
        status = count_and_render_part(pd, font, part_index == 0, &first,
                                       part_index + 1 == parts ? &last : NULL,
                                       part_index + 1 == parts ? &back : NULL,
                                       &part[part_index].pages, &error);
        if (part_index == 0) first_render = first;
        if (part_index + 1 == parts) { last_render = last; back_render = back; }
        total_pages += part[part_index].pages;
        if (publication) exr_document_free(pd);
        if (status != EXR_OK) { count_ok = 0; break; }
      }
      /* If the final part has a single page, take the preceding page from the
         last part that has at least two pages. */
      if (count_ok && !back_render.ok) {
        for (size_t i = parts; i-- > 0;) {
          if (part[i].pages >= 2) {
            exr_document *pd = doc;
            if (publication) status = exr_publication_load(publication, i, &pd, &error);
            else status = EXR_OK;
            if (status == EXR_OK) {
              render_info b = {0};
              if (render_part_page(pd, font, part[i].pages - 2, &b, &error) == EXR_OK) back_render = b;
            }
            if (publication) exr_document_free(pd);
            break;
          }
        }
      }
      /* Middle page: locate its part and use cached random access. */
      if (count_ok && total_pages) {
        size_t mid = total_pages / 2, seen = 0, target_part = 0, target_page = 0;
        for (size_t i = 0; i < parts; i++) {
          if (mid < seen + part[i].pages) { target_part = i; target_page = mid - seen; break; }
          seen += part[i].pages;
        }
        exr_document *pd = doc;
        if (publication) status = exr_publication_load(publication, target_part, &pd, &error);
        else status = EXR_OK;
        if (status == EXR_OK) {
          render_info mid_render = {0};
          status = render_part_page(pd, font, target_page, &mid_render, &error);
          if (status == EXR_OK) middle_render = mid_render;
        }
        if (publication) exr_document_free(pd);
        seq_ok = count_ok && total_pages > 0;
        pages_ok = first_render.ok && middle_render.ok && last_render.ok && back_render.ok && count_ok;
      }
    }
  }
  t_pages = now_ms() - t_pages;

  /* 5. Exact text search plus capture/resolve of a real anchor. */
  t_find = now_ms();
  if (open_ok) {
    if (fixed) {
      const exr_fixed_page *fp = exr_fixed_pages(fixed, &total_pages);
      size_t text_pages = 0;
      for (size_t i = 0; i < total_pages; i++) {
        exr_fixed_text *text = NULL;
        status = exr_fixed_load_text(fixed, i, NULL, &text, &error);
        if (status != EXR_OK) break;
        size_t n = 0;
        exr_fixed_text_string(text, &n);
        if (n) text_pages++;
        if (!have_fanchor && status == EXR_OK && n) {
          size_t start = SIZE_MAX, end = SIZE_MAX;
          exr_status fs = exr_fixed_text_find(text, query, strlen(query), 0, NULL, &start, &end, &error);
          if (fs == EXR_OK && start != SIZE_MAX) {
            const char *pid = fp[i].id ? fp[i].id : "";
            if (exr_fixed_anchor_create(pid, text, start, end, &fanchor, &error) == EXR_OK) {
              exr_anchor_match match = {0};
              if (exr_fixed_anchor_resolve(pid, text, &fanchor, NULL, &match, &error) == EXR_OK &&
                  match.state == EXR_ANCHOR_FOUND) {
                have_fanchor = 1; find_ok = 1; anchor_capture = 1; anchor_resolve = 1;
                anchor_page = i; find_page = i; find_start = start; find_end = end;
                snprintf(anchor_state_same, sizeof(anchor_state_same), "FOUND");
              }
            }
          }
        }
        exr_fixed_text_free(text);
      }
      fixed_text_pages = text_pages;
      if (text_pages == 0) snprintf(find_outcome, sizeof(find_outcome), "empty");
      else if (find_ok) snprintf(find_outcome, sizeof(find_outcome), "found");
      else snprintf(find_outcome, sizeof(find_outcome), "miss");
    } else {
      size_t found_part = SIZE_MAX;
      for (size_t i = 0; i < parts && found_part == SIZE_MAX; i++) {
        exr_document *pd = doc;
        if (publication) {
          status = exr_publication_load(publication, i, &pd, &error);
          if (status != EXR_OK) break;
        }
        size_t start = SIZE_MAX, end = SIZE_MAX;
        status = exr_document_find(pd, query, 0, &start, &end, &error);
        if (status == EXR_OK && start != SIZE_MAX) {
          if (exr_anchor_create(pd, start, end, &anchor, &error) == EXR_OK) {
            exr_anchor_match match = {0};
            if (exr_anchor_resolve(pd, &anchor, &match, &error) == EXR_OK && match.state == EXR_ANCHOR_FOUND) {
              found_part = i; find_ok = 1; anchor_capture = 1; anchor_resolve = 1;
              find_start = start; find_end = end;
              snprintf(anchor_state_same, sizeof(anchor_state_same), "FOUND");
            }
          }
        }
        if (publication) exr_document_free(pd);
      }
      if (found_part != SIZE_MAX) {
        find_part = found_part;
        snprintf(find_outcome, sizeof(find_outcome), "found");
      } else snprintf(find_outcome, sizeof(find_outcome), "miss");
    }
  }
  t_find = now_ms() - t_find;

  /* 6. Reopen the same source; recount and resolve the captured anchor again. */
  t_reopen = now_ms();
  if (open_ok) {
    if (publication) { exr_publication_free(publication); publication = NULL; }
    if (doc) { exr_document_free(doc); doc = NULL; }
    if (fixed) { exr_fixed_free(fixed); fixed = NULL; }
    error.message[0] = 0;
    if (format == EXR_EPUB) {
      status = exr_publication_open(file, &publication, &error);
      if (status == EXR_OK) {
        size_t n = 0;
        exr_publication_parts(publication, &n);
        for (size_t i = 0; i < n; i++) {
          exr_document *pd = NULL;
          if (exr_publication_load(publication, i, &pd, &error) != EXR_OK) break;
          size_t pages = 0;
          status = count_and_render_part(pd, font, 0, NULL, NULL, NULL, &pages, &error);
          reopen_pages += pages;
          exr_document_free(pd);
          if (status != EXR_OK) break;
        }
        if (status == EXR_OK) reopen_ok = 1;
      }
    } else if (fixed_format(format)) {
      exr_fixed_open_options options = {0};
      options.struct_size = sizeof(options); options.fallback_font = font;
      status = exr_fixed_open(file, &options, &fixed, &error);
      if (status == EXR_OK) { exr_fixed_pages(fixed, &reopen_pages); reopen_ok = 1; }
    } else {
      status = exr_document_open(file, &doc, &error);
      if (status == EXR_OK) {
        size_t pages = 0;
        status = count_and_render_part(doc, font, 0, NULL, NULL, NULL, &pages, &error);
        reopen_pages = pages; reopen_ok = status == EXR_OK;
      }
    }
    if (reopen_ok && have_anchor) {
      exr_document *pd = doc;
      if (publication && find_part != SIZE_MAX) {
        if (exr_publication_load(publication, find_part, &pd, &error) != EXR_OK) {
          pd = NULL;
          snprintf(anchor_reopen_error, sizeof(anchor_reopen_error), "%s", error.message);
        }
      }
      if (pd) {
        exr_anchor_match match = {0};
        if (exr_anchor_resolve(pd, &anchor, &match, &error) == EXR_OK && match.state == EXR_ANCHOR_FOUND)
          anchor_reopen = 1;
        snprintf(anchor_state_reopen, sizeof(anchor_state_reopen), "%s",
                 match.state == EXR_ANCHOR_FOUND ? "FOUND" : match.state == EXR_ANCHOR_AMBIGUOUS ? "AMBIGUOUS" :
                 match.state == EXR_ANCHOR_LEGACY ? "LEGACY" : "MISSING");
      }
      if (publication) exr_document_free(pd);
    }
    if (reopen_ok && have_fanchor && fixed) {
      exr_fixed_text *text = NULL;
      const exr_fixed_page *fp = exr_fixed_pages(fixed, &reopen_pages);
      if (anchor_page < reopen_pages && fp &&
          exr_fixed_load_text(fixed, anchor_page, NULL, &text, &error) == EXR_OK) {
        exr_anchor_match match = {0};
        if (exr_fixed_anchor_resolve(fp[anchor_page].id ? fp[anchor_page].id : "", text, &fanchor, NULL, &match, &error) == EXR_OK &&
            match.state == EXR_ANCHOR_FOUND) anchor_reopen = 1;
        snprintf(anchor_state_reopen, sizeof(anchor_state_reopen), "%s",
                 match.state == EXR_ANCHOR_FOUND ? "FOUND" : match.state == EXR_ANCHOR_AMBIGUOUS ? "AMBIGUOUS" :
                 match.state == EXR_ANCHOR_LEGACY ? "LEGACY" : "MISSING");
        exr_fixed_text_free(text);
      }
    }
  }
  t_reopen = now_ms() - t_reopen;


  printf("{\"schema\":1,\"file\":{\"path\":");
  json_string(file);
  printf(",\"format\":\"%s\"},\"program\":{\"sdk_version\":", format_name);
  json_string(exr_version());
  printf(",\"abi\":%u,\"font\":", exr_abi_version());
  json_string(font_path);
  printf("},\"ops\":{");
  printf("\"import\":\"%s\",", import_ok ? "ok" : "failed");
  printf("\"readback\":\"%s\",", readback_ok ? "ok" : "failed");
  printf("\"open\":\"%s\",", open_ok ? "ok" : "failed");
  printf("\"metadata.title\":\"%s\",", !open_ok ? "skipped" : title[0] ? "nonempty" : "empty");
  printf("\"metadata.entries\":\"%s\",", !open_ok ? "skipped" : fixed ? (metadata_entries ? "nonempty" : "empty") : "not_exposed");
  printf("\"toc\":\"%s\",", !open_ok ? "skipped" : fixed ? "not_exposed" : toc_ok ? (toc_count ? "nonempty" : "empty") : "failed");
  printf("\"pages.first\":\"%s\",", !open_ok ? "skipped" : first_render.ok ? "ok" : "failed");
  printf("\"pages.middle\":\"%s\",", !open_ok ? "skipped" : middle_render.ok ? "ok" : "failed");
  printf("\"pages.last\":\"%s\",", !open_ok ? "skipped" : last_render.ok ? "ok" : "failed");
  printf("\"pages.sequential\":\"%s\",", !open_ok ? "skipped" : seq_ok ? "ok" : "failed");
  printf("\"pages.back\":\"%s\",", !open_ok ? "skipped" : back_render.ok ? "ok" : "failed");
  printf("\"find\":\"%s\",", !open_ok ? "skipped" : fixed && !total_pages ? "empty" : find_outcome);
  printf("\"anchor.capture\":\"%s\",", !open_ok ? "skipped" : anchor_capture ? "ok" : (fixed && fixed_text_pages == 0) ? "not_exposed" : "failed");
  printf("\"anchor.resolve\":\"%s\",", !open_ok ? "skipped" : anchor_resolve ? "found" : (fixed && fixed_text_pages == 0) ? "not_exposed" : "failed");
  printf("\"anchor.resolve_reopen\":\"%s\",", !open_ok ? "skipped" : anchor_reopen ? "found" : (fixed && fixed_text_pages == 0) ? "not_exposed" : "failed");
  printf("\"reopen\":\"%s\"", reopen_ok ? "ok" : "failed");
  printf("},\"detail\":{");
  printf("\"kind\":\"%s\",\"parts\":%zu,\"pages\":%zu,\"reopen_pages\":%zu,", open_kind, parts, total_pages, reopen_pages);
  printf("\"title\":"); json_string(title); printf(",");
  printf("\"toc_count\":%zu,\"toc_first\":", toc_count); json_string(toc_label); printf(",");
  printf("\"metadata_entries\":%zu,\"metadata_first_key\":", metadata_entries); json_string(first_key); printf(",");
  printf("\"find\":{\"query\":"); json_string(query);
  if (find_part == SIZE_MAX) printf(",\"part\":null"); else printf(",\"part\":%zu", find_part);
  if (find_page == SIZE_MAX) printf(",\"page\":null"); else printf(",\"page\":%zu", find_page);
  if (find_start == SIZE_MAX) printf(",\"start\":null"); else printf(",\"start\":%zu", find_start);
  if (find_end == SIZE_MAX) printf(",\"end\":null}"); else printf(",\"end\":%zu}", find_end);
  printf(",");
  printf("\"anchor_state_same\":"); json_string(anchor_state_same); printf(",");
  printf("\"anchor_state_reopen\":"); json_string(anchor_state_reopen); printf(",\"anchor_reopen_error\":"); json_string(anchor_reopen_error); printf(",");
  printf("\"first\":"); print_render("r", &first_render); printf(",\"middle\":");
  print_render("r", &middle_render); printf(",\"last\":");
  print_render("r", &last_render); printf(",\"back\":");
  print_render("r", &back_render);
  printf("},\"timings_ms\":{\"import\":%.3f,\"open\":%.3f,\"pages\":%.3f,\"find\":%.3f,\"reopen\":%.3f,\"total\":%.3f}}\n",
         t_import, t_open, t_pages, t_find, t_reopen, now_ms() - t0);

  (void)pages_ok;
  exr_fixed_anchor_free(&fanchor);
  exr_anchor_free(&anchor);
  free(part);
  if (publication) exr_publication_free(publication);
  if (doc) exr_document_free(doc);
  if (fixed) exr_fixed_free(fixed);
  exr_font_free(font);
  return 0;
}