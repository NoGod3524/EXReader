/* SPDX-License-Identifier: MIT */
/* Hosts may call setlocale(LC_ALL, "") (gtk_init does). CSS lengths, the
   reader-style stylesheet and DOCX-derived styles must not depend on the
   locale's decimal separator. Exit code 77 skips when no comma locale exists. */
#include "exreader.h"
#include <locale.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static exr_error error;
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "locale numbers line %d: %s (%d %s)\n", __LINE__, #x, error.code, error.message); exit(1); } } while (0)
#define OK(x) CHECK((x) == EXR_OK)

static int comma_locale(void) {
  static const char *names[] = {"de_DE.UTF-8", "de_DE.utf8", "de_DE", "de-DE", "German_Germany.1252",
                                "fr_FR.UTF-8", "fr_FR", "fr-FR", "ru_RU.UTF-8", "ru-RU"};
  size_t i;
  for (i = 0; i < sizeof(names) / sizeof(*names); i++) {
    char text[16];
    if (!setlocale(LC_ALL, names[i])) continue;
    snprintf(text, sizeof(text), "%.1f", 0.5);
    if (strcmp(text, "0.5")) return 1;
  }
  setlocale(LC_ALL, "C");
  return 0;
}

/* First-line-to-second-line distance and first baseline of a styled paragraph. */
static void styled_lines(const char *font_path, const char *style, float out[3]) {
  exr_attribute attribute = {"style", style};
  exr_node_input nodes[] = {
    {EXR_NODE_DOCUMENT, SIZE_MAX, NULL, NULL, NULL, 0},
    {EXR_NODE_CHAPTER, 0, NULL, NULL, NULL, 0},
    {EXR_NODE_PARAGRAPH, 1, "p", NULL, &attribute, 1},
    {EXR_NODE_TEXT, 2, NULL, "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron", NULL, 0},
    {EXR_NODE_PARAGRAPH, 1, "p", NULL, NULL, 0},
    {EXR_NODE_TEXT, 4, NULL, "second", NULL, 0}};
  exr_chapter_input chapter = {"c", "c.xhtml", 1, 1};
  exr_document_input input = {"locale", nodes, 6, &chapter, 1, NULL, 0};
  exr_layout_config config = exr_layout_config_defaults();
  exr_document *doc = NULL;
  exr_font *font = NULL;
  exr_layout *layout = NULL;
  const exr_line *lines;
  size_t count = 0, i;
  config.document_css = 1;
  OK(exr_document_create(&input, &doc, &error));
  OK(exr_font_open(font_path, &font, &error));
  OK(exr_layout_create_ex(doc, font, &config, &layout, &error));
  lines = exr_layout_lines(layout, &count);
  CHECK(count >= 3);
  for (i = 0; i < 3; i++) out[i] = lines[i].y;
  exr_layout_free(layout);
  exr_font_free(font);
  exr_document_free(doc);
}

static void reader_css(char css[1024]) {
  exr_reader_style style = exr_reader_style_defaults();
  exr_layout_config config = exr_layout_config_defaults();
  style.line_height = 1.75f;
  style.letter_spacing = .05f;
  style.paragraph_spacing = .5f;
  OK(exr_reader_style_config(&style, 360, 640, 1, &config, css, &error));
}

/* Concatenated style attributes of a DOCX import. */
static char *docx_styles(const char *path) {
  FILE *file = fopen(path, "rb");
  long size;
  char *bytes, *styles;
  size_t count = 0, i, used = 0;
  exr_document *doc = NULL;
  const exr_node *nodes;
  CHECK(file && !fseek(file, 0, SEEK_END) && (size = ftell(file)) > 0 && !fseek(file, 0, SEEK_SET));
  bytes = malloc((size_t)size);
  CHECK(bytes && fread(bytes, 1, (size_t)size, file) == (size_t)size);
  fclose(file);
  OK(exr_document_open_memory(EXR_DOCX, bytes, (size_t)size, &doc, &error));
  free(bytes);
  nodes = exr_document_nodes(doc, &count);
  styles = calloc(1, 65536);
  CHECK(styles);
  for (i = 0; i < count; i++) {
    const char *style = exr_node_attribute(&nodes[i], "style");
    size_t n = style ? strlen(style) : 0;
    if (n && used + n + 2 < 65536) { memcpy(styles + used, style, n); used += n; styles[used++] = '\n'; }
  }
  exr_document_free(doc);
  return styles;
}

int main(int argc, char **argv) {
  static const char *styles[] = {"line-height:3.9", "margin-top:2.5em", "font-size:30.5px", "line-height:3"};
  char font[4096], docx[4096], css_c[1024], css_comma[1024];
  float c_lines[4][3], comma_lines[4][3];
  char *docx_c, *docx_comma;
  size_t i;
  if (argc != 2) return 2;
  snprintf(font, sizeof(font), "%s/fonts/primary.ttf", argv[1]);
  snprintf(docx, sizeof(docx), "%s/docx-edit/heading.docx", argv[1]);

  setlocale(LC_ALL, "C");
  for (i = 0; i < 4; i++) styled_lines(font, styles[i], c_lines[i]);
  reader_css(css_c);
  docx_c = docx_styles(docx);
  /* The fixtures must exercise fractional values at all. */
  CHECK(c_lines[0][1] - c_lines[0][0] > c_lines[3][1] - c_lines[3][0]);
  CHECK(strstr(css_c, "1.75") && strstr(docx_c, ".0000"));

  if (!comma_locale()) { puts("locale numbers: no decimal-comma locale installed; skipped"); return 77; }
  for (i = 0; i < 4; i++) {
    styled_lines(font, styles[i], comma_lines[i]);
    CHECK(!memcmp(c_lines[i], comma_lines[i], sizeof(c_lines[i])));
  }
  reader_css(css_comma);
  CHECK(!strcmp(css_c, css_comma));
  docx_comma = docx_styles(docx);
  CHECK(!strcmp(docx_c, docx_comma));
  printf("locale numbers: layout, reader style and DOCX styles match under %s\n", setlocale(LC_NUMERIC, NULL));
  free(docx_c);
  free(docx_comma);
  return 0;
}
