/* SPDX-License-Identifier: MIT */
/* Render one intrinsic color glyph through the public SDK for reference
   comparisons. Positioned layout keeps placement independent of text shaping. */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static exr_error error;
#define OK(x) do { exr_status s_=(x); if(s_!=EXR_OK) { fprintf(stderr,"%s:%d: %s (%d %s)\n",__FILE__,__LINE__,#x,s_,error.message); return 1; } } while(0)

int main(int argc, char **argv) {
  exr_font *font = NULL;
  exr_document *document = NULL;
  exr_layout *layout = NULL;
  exr_layout_config config = exr_layout_config_defaults();
  exr_positioned_page page = {0};
  exr_positioned_input input = {0};
  exr_line line = {0};
  exr_paint paint = {EXR_PAINT_GLYPH, 0, 0};
  exr_glyph glyph = {0};
  exr_bitmap bitmap = {0};
  long glyph_id;
  double size, x, baseline;
  unsigned width, height;
  if (argc != 9) {
    fprintf(stderr, "Usage: %s font.ttf glyph-id size x baseline width height out.png\n", argv[0]);
    return 2;
  }
  glyph_id = strtol(argv[2], NULL, 10);
  size = atof(argv[3]);
  x = atof(argv[4]);
  baseline = atof(argv[5]);
  width = (unsigned)strtoul(argv[6], NULL, 10);
  height = (unsigned)strtoul(argv[7], NULL, 10);
  OK(exr_font_open(argv[1], &font, &error));
  OK(exr_document_open_memory(EXR_TXT, "A", 1, &document, &error));
  config.page = (exr_layout_options){width, height, 0, size, 1, 0};
  page.width = width; page.height = height;
  page.content.end = 1; page.content.line_count = 1; page.paint_count = 1;
  line.end = 1; line.glyph_count = 1; line.x = 0; line.y = 0; line.width = 1; line.height = 1;
  glyph.end = glyph.cluster_end = 1; glyph.codepoint = 'A'; glyph.glyph = (uint32_t)glyph_id;
  glyph.x = (float)x; glyph.baseline = (float)baseline; glyph.advance = (float)size;
  glyph.size = glyph.line_height = (float)size; glyph.node = SIZE_MAX;
  glyph.color = 0x000000ff; glyph.clip_right = (float)width;
  input.struct_size = sizeof(input);
  input.pages = &page; input.page_count = 1;
  input.glyphs = &glyph; input.glyph_count = 1;
  input.lines = &line; input.line_count = 1;
  input.paints = &paint; input.paint_count = 1;
  OK(exr_layout_create_positioned(document, font, &input, &config, &layout, &error));
  OK(exr_render_page_color(layout, NULL, 0, &bitmap, &error));
  OK(exr_bitmap_write_png(&bitmap, argv[8], &error));
  exr_bitmap_free(&bitmap);
  exr_layout_free(layout);
  exr_document_free(document);
  exr_font_free(font);
  return 0;
}
