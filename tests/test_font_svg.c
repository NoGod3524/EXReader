/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static exr_error error;
static unsigned checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr, "svg font line %d: %s (%d %s)\n", __LINE__, #x, error.code, error.message); exit(1); } } while (0)
#define OK(x) CHECK((x) == EXR_OK)

enum {
  GID_RECT = 2, GID_TWO_RECTS, GID_PATH_CURVE, GID_CIRCLE, GID_ELLIPSE, GID_POLYGON,
  GID_POLYLINE, GID_STROKE_CAPS, GID_EVENODD, GID_GROUP_OPACITY, GID_FILL_OPACITY,
  GID_CURRENT_COLOR, GID_TRANSFORM_MATRIX, GID_TRANSFORM_ROTATE, GID_VIEWBOX_SCALED,
  GID_ARC, GID_NAMED_COLOR, GID_RGB_COLOR, GID_NESTED_GROUPS, GID_DEFS_IGNORED,
  GID_NO_VIEWBOX, GID_GZIP, GID_BAD_DOCTYPE, GID_BAD_SCRIPT, GID_BAD_IMAGE, GID_BAD_USE,
  GID_BAD_GRADIENT, GID_BAD_STYLE, GID_BAD_MASK, GID_BAD_EXTERNAL_IMAGE, GID_BAD_PARSE,
  GID_BAD_ENTITY, GID_BAD_PRESERVE, GID_BAD_NESTED, GID_BAD_MANY, GID_BAD_ROUNDED,
  GID_BAD_TRANSFORM, GID_SHARED_A, GID_SHARED_B,
  GID_BAD_ATTRS, GID_BAD_ATTR_SIZE, GID_BAD_VIEWBOX, GID_BAD_CIRCLE, GID_BAD_DASH, GID_BAD_SEGMENTS
};

typedef struct { unsigned calls, after; } cancel_state;
static int cancelled(void *context) { cancel_state *s = context; return ++s->calls > s->after; }

static exr_font *open_font(const char *directory, const char *name) {
  char path[4096];
  exr_font *font = NULL;
  snprintf(path, sizeof(path), "%s/%s", directory, name);
  OK(exr_font_open(path, &font, &error));
  return font;
}

static exr_bitmap render_glyph(exr_font *font, uint32_t id, float size, uint32_t color,
                               unsigned flags, const exr_control *control, exr_status *status) {
  exr_document *document = NULL;
  exr_layout *layout = NULL;
  exr_layout_config config = exr_layout_config_defaults();
  exr_positioned_page page = {0};
  exr_positioned_input input = {0};
  exr_line line = {0};
  exr_paint paint = {EXR_PAINT_GLYPH, 0, 0};
  exr_glyph glyph = {0};
  exr_bitmap bitmap = {0};
  OK(exr_document_open_memory(EXR_TXT, "A", 1, &document, &error));
  config.page = (exr_layout_options){440, 400, 0, size, 1, 0};
  page.width = 440; page.height = 400;
  page.content.end = 1; page.content.line_count = 1; page.paint_count = 1;
  line.end = 1; line.glyph_count = 1; line.x = 0; line.y = 0; line.width = 1; line.height = 1;
  glyph.end = glyph.cluster_end = 1; glyph.codepoint = 'A'; glyph.glyph = id;
  glyph.x = 220; glyph.baseline = 200; glyph.advance = size;
  glyph.size = glyph.line_height = size; glyph.node = SIZE_MAX;
  glyph.color = color; glyph.flags = flags; glyph.clip_right = 440;
  input.struct_size = sizeof(input);
  input.pages = &page; input.page_count = 1;
  input.glyphs = &glyph; input.glyph_count = 1;
  input.lines = &line; input.line_count = 1;
  input.paints = &paint; input.paint_count = 1;
  if (exr_layout_create_positioned(document, font, &input, &config, &layout, &error) != EXR_OK) {
    fprintf(stderr, "svg layout failed for glyph %u size %g: %s\n", id, (double)size, error.message);
    exit(1);
  }
  *status = control ? exr_render_page_ex(layout, NULL, 0, 4, control, &bitmap, &error)
                    : exr_render_page_color(layout, NULL, 0, &bitmap, &error);
  exr_layout_free(layout);
  exr_document_free(document);
  return bitmap;
}

static void near(const exr_bitmap *bitmap, unsigned x, unsigned y, unsigned r, unsigned g, unsigned b, int tolerance) {
  const unsigned char *p;
  if (!bitmap->pixels) {
    fprintf(stderr, "svg font: missing bitmap at %u,%u\n", x, y);
    exit(1);
  }
  p = bitmap->pixels + (size_t)y*bitmap->stride + (size_t)x*4;
  if (abs((int)p[0] - (int)r) > tolerance || abs((int)p[1] - (int)g) > tolerance ||
      abs((int)p[2] - (int)b) > tolerance) {
    fprintf(stderr, "svg pixel %u,%u = %u,%u,%u expected %u,%u,%u\n", x, y, p[0], p[1], p[2], r, g, b);
    exit(1);
  }
}

static void white(const exr_bitmap *bitmap, unsigned x, unsigned y) { near(bitmap, x, y, 255, 255, 255, 0); }

static exr_bitmap scene(exr_font *font, uint32_t id) {
  exr_status status;
  exr_bitmap bitmap = render_glyph(font, id, 100, 0x000000ff, 0, NULL, &status);
  CHECK(status == EXR_OK);
  return bitmap;
}

static void information(const char *directory) {
  exr_font *font = open_font(directory, "svgfont.ttf");
  exr_font *plain = open_font(directory, "primary.ttf");
  exr_font *colr = open_font(directory, "colrv1.ttf");
  exr_font_color_info info;
  unsigned id;
  for (id = 2; id <= 23; id++) {
    memset(&info, 0, sizeof(info)); info.struct_size = sizeof(info);
    OK(exr_font_color_info_get(font, 0, id, &info, NULL, &error));
    CHECK(info.kind == EXR_FONT_COLOR_SVG && !info.has_clip_box);
  }
  memset(&info, 0, sizeof(info)); info.struct_size = sizeof(info);
  OK(exr_font_color_info_get(font, 0, 39, &info, NULL, &error));
  CHECK(info.kind == EXR_FONT_COLOR_SVG);
  memset(&info, 0, sizeof(info)); info.struct_size = sizeof(info);
  OK(exr_font_color_info_get(font, 0, 0, &info, NULL, &error));
  CHECK(info.kind == EXR_FONT_COLOR_NONE);
  memset(&info, 0, sizeof(info)); info.struct_size = sizeof(info);
  OK(exr_font_color_info_get(plain, 0, 0, &info, NULL, &error));
  CHECK(info.kind == EXR_FONT_COLOR_NONE);
  memset(&info, 0, sizeof(info)); info.struct_size = sizeof(info);
  OK(exr_font_color_info_get(colr, 0, 7, &info, NULL, &error));
  CHECK(info.kind == EXR_FONT_COLOR_COLR_V1);
  exr_font_free(font);
  exr_font_free(plain);
  exr_font_free(colr);
}

static unsigned read16(const unsigned char *p) { return (unsigned)p[0] << 8 | p[1]; }
static uint32_t read32(const unsigned char *p) {
  return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 | (uint32_t)p[2] << 8 | p[3];
}

static void directory_failures(const char *directory) {
  char path[4096];
  FILE *file;
  long length;
  unsigned char *bytes;
  size_t table = 0, list, record;
  unsigned i, variant;
  snprintf(path, sizeof(path), "%s/svgfont.ttf", directory);
  file = fopen(path, "rb"); CHECK(file != NULL);
  CHECK(!fseek(file, 0, SEEK_END)); length = ftell(file); CHECK(length > 12);
  rewind(file); bytes = malloc((size_t)length); CHECK(bytes != NULL);
  CHECK(fread(bytes, 1, (size_t)length, file) == (size_t)length); fclose(file);
  for (i = 0; i < read16(bytes + 4); i++) {
    size_t at = 12 + (size_t)i*16;
    CHECK(at + 16 <= (size_t)length);
    if (!memcmp(bytes + at, "SVG ", 4)) table = read32(bytes + at + 8);
  }
  CHECK(table && table + 12 <= (size_t)length);
  list = table + read32(bytes + table + 2);
  CHECK(list + 14 <= (size_t)length);
  record = list + 2;
  for (variant = 0; variant < 2; variant++) {
    exr_font *font = NULL;
    exr_font_input input = {bytes, (size_t)length, 0};
    exr_font_color_info info = {0};
    if (!variant) bytes[table + 6] = 1;
    else {
      size_t document = list + read32(bytes + record + 4);
      CHECK(document < (size_t)length);
      bytes[table + 6] = 0;
      memset(bytes + record + 8, 0, 4); bytes[record + 11] = 1;
      bytes[document] = 0x1f;
    }
    OK(exr_font_create_glyphs(&input, 1, &font, &error));
    info.struct_size = sizeof(info);
    if (!variant) {
      CHECK(exr_font_color_info_get(font, 0, GID_RECT, &info, NULL, &error) == EXR_FONT);
      CHECK(info.kind == EXR_FONT_COLOR_NONE);
      CHECK(exr_font_color_info_get(font, 0, GID_RECT, &info, NULL, NULL) == EXR_FONT);
    } else {
      exr_status status;
      exr_bitmap image = render_glyph(font, GID_RECT, 100, 0x000000ff, 0, NULL, &status);
      CHECK(status == EXR_FORMAT && !image.pixels);
    }
    exr_font_free(font);
  }
  free(bytes);
}

static void shapes(exr_font *font) {
  exr_bitmap image;
  image = scene(font, GID_RECT);
  near(&image, 250, 150, 224, 32, 32, 1);
  white(&image, 220, 150);
  white(&image, 320, 150);
  exr_bitmap_free(&image);
  image = scene(font, GID_TWO_RECTS);
  near(&image, 250, 150, 255, 0, 0, 1);
  near(&image, 290, 150, 0, 0, 255, 1);
  exr_bitmap_free(&image);
  image = scene(font, GID_CIRCLE);
  near(&image, 270, 150, 0, 128, 255, 1);
  white(&image, 232, 112);
  exr_bitmap_free(&image);
  image = scene(font, GID_ELLIPSE);
  near(&image, 270, 150, 255, 128, 0, 1);
  exr_bitmap_free(&image);
  image = scene(font, GID_POLYGON);
  near(&image, 270, 170, 128, 0, 255, 1);
  white(&image, 270, 100);
  exr_bitmap_free(&image);
  image = scene(font, GID_POLYLINE);
  {
    const unsigned char *p = image.pixels + (size_t)160*image.stride + (size_t)240*4;
    CHECK(p[0] < 160 && p[1] < 160 && p[2] < 160);
  }
  exr_bitmap_free(&image);
  image = scene(font, GID_STROKE_CAPS);
  near(&image, 270, 150, 32, 64, 255, 1);
  white(&image, 270, 170);
  exr_bitmap_free(&image);
  image = scene(font, GID_EVENODD);
  near(&image, 240, 150, 192, 0, 64, 1);
  white(&image, 270, 150);
  exr_bitmap_free(&image);
  image = scene(font, GID_NAMED_COLOR);
  near(&image, 250, 150, 0, 128, 0, 1);
  exr_bitmap_free(&image);
  image = scene(font, GID_RGB_COLOR);
  near(&image, 250, 150, 10, 20, 30, 0);
  exr_bitmap_free(&image);
  image = scene(font, GID_ARC);
  near(&image, 270, 120, 64, 96, 192, 1);
  exr_bitmap_free(&image);
  image = scene(font, GID_GZIP);
  near(&image, 250, 150, 32, 192, 32, 1);
  exr_bitmap_free(&image);
  image = scene(font, GID_SHARED_A);
  near(&image, 250, 150, 192, 32, 32, 1);
  exr_bitmap_free(&image);
  image = scene(font, GID_SHARED_B);
  near(&image, 270, 150, 32, 32, 192, 1);
  white(&image, 230, 150);
  exr_bitmap_free(&image);
}

static void style(exr_font *font) {
  exr_bitmap image;
  image = scene(font, GID_GROUP_OPACITY);
  near(&image, 250, 150, 255, 127, 127, 1);
  exr_bitmap_free(&image);
  image = scene(font, GID_FILL_OPACITY);
  near(&image, 250, 150, 255, 127, 127, 1);
  exr_bitmap_free(&image);
  image = scene(font, GID_CURRENT_COLOR);
  near(&image, 250, 150, 0, 0, 0, 0);
  exr_bitmap_free(&image);
  {
    exr_status status;
    image = render_glyph(font, GID_CURRENT_COLOR, 100, 0x00ff00ff, 0, NULL, &status);
    CHECK(status == EXR_OK);
    near(&image, 250, 150, 0, 255, 0, 0);
    exr_bitmap_free(&image);
  }
  image = scene(font, GID_DEFS_IGNORED);
  near(&image, 260, 150, 0, 255, 0, 1);
  white(&image, 220, 150);
  exr_bitmap_free(&image);
  image = scene(font, GID_NO_VIEWBOX);
  near(&image, 250, 150, 128, 64, 0, 1);
  exr_bitmap_free(&image);
}

static void transforms(exr_font *font) {
  exr_bitmap image;
  image = scene(font, GID_TRANSFORM_MATRIX);
  near(&image, 250, 140, 0, 160, 160, 1);
  exr_bitmap_free(&image);
  image = scene(font, GID_TRANSFORM_ROTATE);
  near(&image, 270, 150, 160, 0, 160, 1);
  white(&image, 240, 120);
  exr_bitmap_free(&image);
  image = scene(font, GID_VIEWBOX_SCALED);
  near(&image, 260, 140, 0, 128, 64, 1);
  white(&image, 230, 140);
  exr_bitmap_free(&image);
  image = scene(font, GID_NESTED_GROUPS);
  near(&image, 250, 130, 255, 160, 0, 1);
  white(&image, 290, 130);
  exr_bitmap_free(&image);
  /* id-selected glyphs from one shared document. */
  image = scene(font, GID_SHARED_A);
  white(&image, 250, 190);
  exr_bitmap_free(&image);
}

static void rejections(exr_font *font) {
  static const struct { unsigned id; exr_status status; } cases[] = {
    {GID_BAD_DOCTYPE, EXR_UNSUPPORTED}, {GID_BAD_SCRIPT, EXR_UNSUPPORTED},
    {GID_BAD_IMAGE, EXR_UNSUPPORTED}, {GID_BAD_USE, EXR_UNSUPPORTED},
    {GID_BAD_GRADIENT, EXR_UNSUPPORTED}, {GID_BAD_STYLE, EXR_UNSUPPORTED},
    {GID_BAD_MASK, EXR_UNSUPPORTED}, {GID_BAD_EXTERNAL_IMAGE, EXR_UNSUPPORTED},
    {GID_BAD_PARSE, EXR_FORMAT}, {GID_BAD_ENTITY, EXR_UNSUPPORTED},
    {GID_BAD_PRESERVE, EXR_UNSUPPORTED}, {GID_BAD_NESTED, EXR_LIMIT},
    {GID_BAD_MANY, EXR_LIMIT}, {GID_BAD_ROUNDED, EXR_UNSUPPORTED},
    {GID_BAD_TRANSFORM, EXR_UNSUPPORTED}, {GID_BAD_ATTRS, EXR_LIMIT},
    {GID_BAD_ATTR_SIZE, EXR_LIMIT}, {GID_BAD_VIEWBOX, EXR_UNSUPPORTED},
    {GID_BAD_CIRCLE, EXR_FORMAT}, {GID_BAD_DASH, EXR_UNSUPPORTED},
    {GID_BAD_SEGMENTS, EXR_LIMIT}
  };
  size_t i;
  for (i = 0; i < sizeof(cases)/sizeof(cases[0]); i++) {
    exr_status status;
    exr_bitmap image = render_glyph(font, cases[i].id, 100, 0x000000ff, 0, NULL, &status);
    if (status != cases[i].status)
      fprintf(stderr, "SVG rejection glyph %u: expected %d got %d (%s)\n", cases[i].id, cases[i].status, status, error.message);
    CHECK(status == cases[i].status && !image.pixels);
  }
}

static void limits(exr_font *font) {
  exr_status status;
  exr_bitmap image;
  {
    unsigned i;
    for (i = 0; i <= 3; i++) {
      cancel_state state = {0, i};
      exr_control control = {0};
      control.context = &state; control.cancelled = cancelled;
      image = render_glyph(font, GID_RECT, 100, 0x000000ff, 0, &control, &status);
      CHECK(status == EXR_CANCELLED && !image.pixels);
    }
  }
  image = render_glyph(font, GID_RECT, 100, 0x00ff0080, 0, NULL, &status);
  CHECK(status == EXR_OK);
  near(&image, 250, 150, 239, 143, 143, 2);
  exr_bitmap_free(&image);
  image = render_glyph(font, GID_RECT, 100, 0x000000ff, EXR_GLYPH_VERTICAL, NULL, &status);
  CHECK(status == EXR_OK);
  near(&image, 250, 150, 224, 32, 32, 1);
  exr_bitmap_free(&image);
  image = render_glyph(font, GID_RECT, 100, 0x000000ff, EXR_GLYPH_VERTICAL | EXR_GLYPH_SIDEWAYS, NULL, &status);
  CHECK(status == EXR_OK);
  near(&image, 250, 240, 224, 32, 32, 1);
  white(&image, 250, 150);
  exr_bitmap_free(&image);
}

static void layout_identity(exr_font *font) {
  exr_document *document = NULL;
  exr_layout *layout = NULL;
  exr_layout_config config = exr_layout_config_defaults();
  const exr_glyph *glyphs;
  size_t count, i;
  exr_bitmap image = {0};
  config.page = (exr_layout_options){600, 200, 0, 100, 1, 0};
  OK(exr_document_open_memory(EXR_TXT, "ABC", 3, &document, &error));
  OK(exr_layout_create_ex(document, font, &config, &layout, &error));
  glyphs = exr_layout_glyphs(layout, &count);
  CHECK(count == 3 && glyphs[0].glyph == 2 && glyphs[1].glyph == 3 && glyphs[2].glyph == 4);
  for (i = 0; i < count; i++) {
    size_t hit = exr_layout_hit_test(layout, 0, glyphs[i].x + 1,
                                     glyphs[i].baseline - glyphs[i].size/3);
    CHECK(hit == glyphs[i].cluster_start);
  }
  OK(exr_render_page_color(layout, NULL, 0, &image, &error));
  exr_bitmap_free(&image);
  exr_layout_free(layout);
  exr_document_free(document);
}

int main(int argc, char **argv) {
  exr_font *font;
  CHECK(argc == 3);
  font = open_font(argv[1], "svgfont.ttf");
  information(argv[1]);
  directory_failures(argv[1]);
  shapes(font);
  style(font);
  transforms(font);
  rejections(font);
  limits(font);
  layout_identity(font);
  exr_font_free(font);
  printf("%u SVG font element, transform, rejection, limit and identity checks passed\n", checks);
  return 0;
}
