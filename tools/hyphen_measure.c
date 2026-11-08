/* SPDX-License-Identifier: MIT */
/* Hyphenation measurement harness.
   hyphen_measure BOOK FONT MODE [EVENTS.tsv] [FONT_PX]
   MODE: base   no hyphenator (pre-feature behaviour)
         none   built-in hyphenator + user CSS hyphens:none
         manual built-in hyphenator, no auto default (CSS default)
         auto   built-in hyphenator, auto-by-default
   All modes force text-align:justify. Prints one JSON line. EVENTS.tsv gets one
   "part\tleft\tright" row per generated hyphen (the word fragments around it).
   "stretched" counts justified lines whose added inter-word space exceeds 0.5 em
   in total; "loose" those exceeding 0.5 em per space; "text_hash" is an FNV-1a hash of the logical text copied back out of
   the pages (generated glyphs skipped, whitespace dropped). */
#include "exreader.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned long long fnv(unsigned long long h, const void *p, size_t n) {
  const unsigned char *b = p;
  while (n--) { h ^= *b++; h *= 1099511628211ull; }
  return h;
}
static int blank(unsigned char c) { return c == ' ' || c == '\n' || c == '\t' || c == '\r'; }

int main(int argc, char **argv) {
  exr_font *font = NULL; exr_publication *pub = NULL; exr_document *doc = NULL;
  exr_pager *pager = NULL; exr_layout *page = NULL; exr_hyphenator *hy = NULL;
  exr_error err = {0}; exr_layout_config cfg = exr_layout_config_defaults();
  size_t parts = 0, pages = 0, stretched = 0, loose = 0, justified = 0, lines_total = 0, events = 0, text_len = 0;
  unsigned long long layout_hash = 14695981039346656037ull, text_hash = 14695981039346656037ull;
  FILE *ev = NULL; const char *mode; float px = 28; exr_status st;
  if (argc < 4) return 2;
  mode = argv[3];
  if (argc > 4 && strcmp(argv[4], "-")) ev = fopen(argv[4], "wb");
  if (argc > 5) px = (float)atof(argv[5]);
  st = exr_font_open(argv[2], &font, &err); if (st != EXR_OK) goto done;
#ifndef HYPH_NO_BUILTIN /* build with this define against a pre-feature library for the true baseline */
  if (strcmp(mode, "base")) {
    st = exr_hyphenator_create_builtin(0, 0, !strcmp(mode, "auto"), NULL, &hy, &err); if (st != EXR_OK) goto done;
  }
#endif
  cfg.page = (exr_layout_options){720, 1040, 36, px, 1.5f, 10};
  cfg.user_css = !strcmp(mode, "none") ? "*{hyphens:none!important}p,div,li,blockquote{text-align:justify}"
                                       : "p,div,li,blockquote{text-align:justify}";
  st = exr_publication_open(argv[1], &pub, &err); if (st != EXR_OK) goto done;
  (void)exr_publication_parts(pub, &parts);
  for (size_t part = 0; part < parts; part++) {
    const char *text; size_t text_size = 0, emitted = 0;
    st = exr_publication_load(pub, part, &doc, &err); if (st != EXR_OK) goto done;
    text = exr_document_text(doc, &text_size);
    st = exr_pager_create(doc, font, &cfg, &pager, &err); if (st != EXR_OK) goto done;
    if (hy) { st = exr_pager_set_hyphenator(pager, hy, &err); if (st != EXR_OK) goto done; }
    for (;;) {
      size_t gn = 0, ln = 0; const exr_glyph *g; const exr_line *l;
      st = exr_pager_next(pager, &page, &err); if (st != EXR_OK) goto done;
      if (!page) break;
      pages++;
      g = exr_layout_glyphs(page, &gn); l = exr_layout_lines(page, &ln);
      layout_hash = fnv(layout_hash, &gn, sizeof gn);
      for (size_t i = 0; i < gn; i++) {
        long x = lroundf(g[i].x * 4), y = lroundf(g[i].baseline * 4);
        layout_hash = fnv(layout_hash, &g[i].codepoint, 4); layout_hash = fnv(layout_hash, &g[i].glyph, 4);
        layout_hash = fnv(layout_hash, &x, sizeof x); layout_hash = fnv(layout_hash, &y, sizeof y);
        layout_hash = fnv(layout_hash, &g[i].flags, sizeof g[i].flags);
        if ((g[i].flags & EXR_GLYPH_GENERATED) && g[i].start == g[i].end) {
          if (ev && g[i].codepoint == 0x2010) {
            size_t a = g[i].start, b = g[i].start;
            while (a > 0 && ((text[a - 1] | 32) >= 'a' && (text[a - 1] | 32) <= 'z')) a--;
            while (b < text_size && ((text[b] | 32) >= 'a' && (text[b] | 32) <= 'z')) b++;
            fprintf(ev, "%zu\t%.*s\t%.*s\n", part, (int)(g[i].start - a), text + a, (int)(b - g[i].start), text + g[i].start);
          }
          if (g[i].codepoint == 0x2010) events++;
          continue;
        }
        if (g[i].flags & EXR_GLYPH_GENERATED) continue;
        if (g[i].start < g[i].end && g[i].end <= text_size) {
          size_t from = g[i].start > emitted ? g[i].start : emitted;
          for (size_t k = from; k < g[i].end; k++) if (!blank((unsigned char)text[k])) {
            text_hash = fnv(text_hash, text + k, 1); text_len++;
          }
          if (g[i].end > emitted) emitted = g[i].end;
        }
      }
      for (size_t i = 0; i < ln; i++) {
        double adv = 0, first_x, last_edge; size_t spaces = 0, a = l[i].glyph_start, n = l[i].glyph_count;
        if (!n || a + n > gn) continue;
        lines_total++;
        first_x = g[a].x; last_edge = g[a + n - 1].x + g[a + n - 1].advance;
        for (size_t k = a; k < a + n; k++) { adv += g[k].advance; spaces += g[k].codepoint == ' '; }
        if (spaces && last_edge - first_x - adv > 0.5) {
          justified++;
          if (last_edge - first_x - adv > 0.5 * g[a].size) stretched++;
          if ((last_edge - first_x - adv) / (double)spaces > 0.5 * g[a].size) loose++;
        }
      }
      exr_layout_free(page); page = NULL;
    }
    exr_pager_free(pager); pager = NULL; exr_document_free(doc); doc = NULL;
  }
done:
  if (st != EXR_OK) fprintf(stderr, "error %d: %s\n", (int)st, err.message);
  if (ev) fclose(ev);
  exr_layout_free(page); exr_pager_free(pager); exr_document_free(doc);
  exr_publication_free(pub); exr_hyphenator_free(hy); exr_font_free(font);
  printf("{\"mode\":\"%s\",\"status\":%d,\"parts\":%zu,\"pages\":%zu,\"lines\":%zu,\"justified\":%zu,"
         "\"stretched\":%zu,\"loose\":%zu,\"hyphens\":%zu,\"layout_hash\":\"%016llx\",\"text_hash\":\"%016llx\",\"text_len\":%zu}\n",
         mode, (int)st, parts, pages, lines_total, justified, stretched, loose, events, layout_hash, text_hash, text_len);
  return st == EXR_OK ? 0 : 1;
}
