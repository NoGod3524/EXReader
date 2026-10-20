/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static exr_error error;
static unsigned checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr, "colrv1 line %d: %s (%d %s)\n", __LINE__, #x, error.code, error.message); exit(1); } } while (0)
#define OK(x) CHECK((x) == EXR_OK)

typedef struct { unsigned calls, after; } cancel_state;
static int cancelled(void *context) { cancel_state *s = context; return ++s->calls > s->after; }

static unsigned render_page_width = 440;
static unsigned render_page_height = 400;

static exr_font *open_font(const char *directory, const char *name) {
  char path[4096];
  exr_font *font = NULL;
  snprintf(path, sizeof(path), "%s/%s", directory, name);
  OK(exr_font_open(path, &font, &error));
  return font;
}

static exr_bitmap render_glyph(exr_font *font, uint32_t id, float size, uint32_t color,
                               unsigned flags, float clip_left, float clip_right,
                               const exr_control *control, exr_status *status) {
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
  config.page = (exr_layout_options){render_page_width, render_page_height, 0, size, 1, 0};
  page.width = render_page_width; page.height = render_page_height;
  page.content.end = 1; page.content.line_count = 1; page.paint_count = 1;
  line.end = 1; line.glyph_count = 1; line.x = 0; line.y = 0; line.width = 1; line.height = 1;
  glyph.end = glyph.cluster_end = 1; glyph.codepoint = 'A'; glyph.glyph = id;
  glyph.x = 220; glyph.baseline = 200; glyph.advance = size;
  glyph.size = glyph.line_height = size; glyph.node = SIZE_MAX;
  glyph.color = color; glyph.flags = flags;
  glyph.clip_left = clip_left; glyph.clip_right = clip_right > 0 ? clip_right : (float)render_page_width;
  input.struct_size = sizeof(input);
  input.pages = &page; input.page_count = 1;
  input.glyphs = &glyph; input.glyph_count = 1;
  input.lines = &line; input.line_count = 1;
  input.paints = &paint; input.paint_count = 1;
  if (exr_layout_create_positioned(document, font, &input, &config, &layout, &error) != EXR_OK) {
    fprintf(stderr, "colrv1 layout failed glyph %u size %g page %u clip %g..%g: %s\n", id, (double)size,
            render_page_width, (double)clip_left, (double)glyph.clip_right, error.message);
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
    fprintf(stderr, "colrv1: missing bitmap at %u,%u\n", x, y);
    exit(1);
  }
  p = bitmap->pixels + (size_t)y*bitmap->stride + (size_t)x*4;
  if (abs((int)p[0] - (int)r) > tolerance || abs((int)p[1] - (int)g) > tolerance ||
      abs((int)p[2] - (int)b) > tolerance) {
    fprintf(stderr, "colrv1 pixel %u,%u = %u,%u,%u expected %u,%u,%u\n", x, y, p[0], p[1], p[2], r, g, b);
    exit(1);
  }
}

static void white(const exr_bitmap *bitmap, unsigned x, unsigned y) { near(bitmap, x, y, 255, 255, 255, 0); }

static exr_bitmap scene(exr_font *font, uint32_t id) {
  exr_status status;
  exr_bitmap bitmap = render_glyph(font, id, 100, 0x000000ff, 0, 0, 440, NULL, &status);
  CHECK(status == EXR_OK);
  return bitmap;
}

static void information(const char *directory) {
  exr_font *font = open_font(directory, "colrv1.ttf");
  exr_font *variable = open_font(directory, "colrv1-var.ttf");
  exr_font *v0 = open_font(directory, "color.ttf");
  exr_font *plain = open_font(directory, "primary.ttf");
  exr_font_color_info info;
  size_t glyphs;
  memset(&info, 0, sizeof(info)); info.struct_size = sizeof(info);
  OK(exr_font_color_info_get(font, 0, 7, &info, NULL, &error));
  CHECK(info.kind == EXR_FONT_COLOR_COLR_V1 && !info.has_clip_box && !info.variable);
  memset(&info, 0, sizeof(info)); info.struct_size = sizeof(info);
  OK(exr_font_color_info_get(font, 0, 38, &info, NULL, &error));
  CHECK(info.kind == EXR_FONT_COLOR_COLR_V1 && info.has_clip_box);
  CHECK(fabsf(info.clip_box[0] - 100) < .01f && fabsf(info.clip_box[1] - 100) < .01f &&
        fabsf(info.clip_box[2] - 700) < .01f && fabsf(info.clip_box[3] - 700) < .01f);
  memset(&info, 0, sizeof(info)); info.struct_size = sizeof(info);
  OK(exr_font_color_info_get(variable, 0, 3, &info, NULL, &error));
  CHECK(info.kind == EXR_FONT_COLOR_COLR_V1 && info.variable);
  memset(&info, 0, sizeof(info)); info.struct_size = sizeof(info);
  OK(exr_font_color_info_get(v0, 0, 2, &info, NULL, &error));
  CHECK(info.kind == EXR_FONT_COLOR_COLR_V0);
  memset(&info, 0, sizeof(info)); info.struct_size = sizeof(info);
  OK(exr_font_color_info_get(plain, 0, 0, &info, NULL, &error));
  CHECK(info.kind == EXR_FONT_COLOR_NONE);
  memset(&info, 0, sizeof(info));
  CHECK(exr_font_color_info_get(font, 0, 7, &info, NULL, &error) == EXR_ARGUMENT);
  info.struct_size = sizeof(info) - 1;
  CHECK(exr_font_color_info_get(font, 0, 7, &info, NULL, &error) == EXR_ARGUMENT);
  {
    unsigned char storage[sizeof(exr_font_color_info) + 8];
    memset(storage, 0, sizeof(storage));
    ((exr_font_color_info *)storage)->struct_size = sizeof(storage);
    OK(exr_font_color_info_get(font, 0, 7, (exr_font_color_info *)storage, NULL, &error));
    ((exr_font_color_info *)storage)->kind = EXR_FONT_COLOR_COLR_V1;
    ((exr_font_color_info *)storage)->struct_size = sizeof(storage);
    storage[sizeof(storage) - 1] = 1;
    CHECK(exr_font_color_info_get(font, 0, 7, (exr_font_color_info *)storage, NULL, &error) == EXR_ARGUMENT);
  }
  memset(&info, 0, sizeof(info)); info.struct_size = sizeof(info);
  CHECK(exr_font_color_info_get(font, 0, 9999, &info, NULL, &error) == EXR_ARGUMENT);
  CHECK(exr_font_color_info_get(font, 9, 7, &info, NULL, &error) == EXR_ARGUMENT);
  {
    cancel_state state = {0, 0};
    exr_control control = {0};
    control.context = &state; control.cancelled = cancelled;
    memset(&info, 0, sizeof(info)); info.struct_size = sizeof(info);
    CHECK(exr_font_color_info_get(font, 0, 7, &info, &control, &error) == EXR_CANCELLED);
  }
  glyphs = exr_font_count(font);
  CHECK(glyphs == 1);
  exr_font_free(font);
  exr_font_free(variable);
  exr_font_free(v0);
  exr_font_free(plain);
}

static void solid_scenes(exr_font *font) {
  exr_bitmap image;
  exr_status status;
  image = scene(font, 7);            /* solid */
  near(&image, 250, 150, 255, 0, 0, 0);
  white(&image, 210, 150);
  exr_bitmap_free(&image);
  image = scene(font, 9);            /* solid_half */
  near(&image, 250, 150, 127, 255, 127, 1);
  exr_bitmap_free(&image);
  image = scene(font, 10);           /* layers */
  near(&image, 230, 150, 255, 0, 0, 0);
  near(&image, 270, 150, 0, 0, 255, 0);
  exr_bitmap_free(&image);
  image = scene(font, 11);           /* layers_overlap */
  near(&image, 230, 150, 255, 0, 0, 0);
  near(&image, 260, 160, 127, 0, 127, 2);
  exr_bitmap_free(&image);
  image = scene(font, 38);           /* clipbox */
  near(&image, 250, 160, 255, 0, 0, 0);
  white(&image, 225, 160);
  white(&image, 295, 160);
  exr_bitmap_free(&image);
  /* Foreground alpha multiplies the whole surface. */
  image = render_glyph(font, 7, 100, 0x00000000, 0, 0, 440, NULL, &status);
  CHECK(status == EXR_OK);
  white(&image, 250, 150);
  exr_bitmap_free(&image);
  image = render_glyph(font, 7, 100, 0x00ff0080, 0, 0, 440, NULL, &status);
  CHECK(status == EXR_OK);
  near(&image, 250, 150, 255, 127, 127, 1);
  exr_bitmap_free(&image);
  /* 0xffff takes the text foreground instead of CPAL. */
  image = render_glyph(font, 8, 100, 0x00ff00ff, 0, 0, 440, NULL, &status);
  CHECK(status == EXR_OK);
  near(&image, 250, 150, 0, 255, 0, 0);
  exr_bitmap_free(&image);
  /* Synthetic bold/italic are not applied to intrinsic colour. */
  image = render_glyph(font, 7, 100, 0x000000ff, EXR_GLYPH_BOLD | EXR_GLYPH_ITALIC, 0, 440, NULL, &status);
  CHECK(status == EXR_OK);
  near(&image, 250, 150, 255, 0, 0, 0);
  exr_bitmap_free(&image);
  /* Decorations still use the text colour around the colour glyph. */
  image = render_glyph(font, 21, 100, 0x102030ff, EXR_GLYPH_UNDERLINE, 0, 440, NULL, &status);
  CHECK(status == EXR_OK);
  near(&image, 300, 212, 16, 32, 48, 1);
  exr_bitmap_free(&image);
}

static void gradient_scenes(exr_font *font) {
  exr_bitmap image;
  image = scene(font, 12);           /* linear */
  near(&image, 230, 150, 255, 67, 0, 3);
  near(&image, 250, 150, 255, 194, 0, 3);
  near(&image, 270, 150, 188, 188, 67, 4);
  exr_bitmap_free(&image);
  image = scene(font, 13);           /* linear_p2 */
  near(&image, 250, 150, 255, 194, 0, 3);
  exr_bitmap_free(&image);
  image = scene(font, 14);           /* linear_shear: t = (x-y)/800 */
  near(&image, 270, 180, 255, 198, 0, 4);
  near(&image, 230, 170, 255, 0, 0, 0);
  exr_bitmap_free(&image);
  image = scene(font, 15);           /* linear_alpha: premultiplied stops */
  near(&image, 230, 150, 255, 25, 25, 3);
  exr_bitmap_free(&image);
  image = scene(font, 16);           /* linear_repeat */
  near(&image, 230, 150, 188, 0, 67, 4);
  near(&image, 250, 150, 61, 0, 194, 4);
  exr_bitmap_free(&image);
  image = scene(font, 17);           /* radial */
  near(&image, 260, 160, 255, 6, 0, 8);
  near(&image, 280, 160, 249, 249, 6, 8);
  near(&image, 296, 160, 44, 44, 211, 10);
  exr_bitmap_free(&image);
  image = scene(font, 18);           /* radial_offset */
  near(&image, 250, 160, 255, 0, 0, 2);
  near(&image, 270, 160, 255, 134, 0, 6);
  near(&image, 290, 160, 121, 121, 134, 8);
  exr_bitmap_free(&image);
  image = scene(font, 19);           /* sweep */
  near(&image, 260, 180, 130, 130, 130, 8);
  near(&image, 280, 160, 2, 2, 253, 6);
  near(&image, 260, 140, 255, 128, 0, 6);
  near(&image, 240, 160, 253, 253, 2, 6);
  exr_bitmap_free(&image);
  image = scene(font, 39);           /* clipbox_gradient */
  near(&image, 240, 160, 255, 131, 0, 4);
  white(&image, 228, 160);
  exr_bitmap_free(&image);
  image = scene(font, 40);           /* layer_gradient */
  near(&image, 230, 150, 255, 0, 0, 0);
  near(&image, 280, 160, 255, 9, 0, 10);
  exr_bitmap_free(&image);
}

static void transform_scenes(exr_font *font) {
  exr_bitmap image;
  image = scene(font, 20);           /* translate */
  near(&image, 290, 150, 255, 0, 0, 0);
  white(&image, 240, 150);
  exr_bitmap_free(&image);
  image = scene(font, 21);           /* scale */
  near(&image, 240, 180, 255, 0, 0, 0);
  white(&image, 270, 150);
  exr_bitmap_free(&image);
  image = scene(font, 22);           /* scale_center */
  near(&image, 260, 160, 255, 0, 0, 0);
  white(&image, 235, 160);
  exr_bitmap_free(&image);
  image = scene(font, 23);           /* scale_uniform */
  near(&image, 240, 180, 255, 0, 0, 0);
  exr_bitmap_free(&image);
  image = scene(font, 24);           /* rotate 90 about origin */
  near(&image, 180, 180, 255, 0, 0, 0);
  white(&image, 250, 150);
  exr_bitmap_free(&image);
  image = scene(font, 25);           /* rotate about center */
  near(&image, 260, 180, 255, 0, 0, 0);
  white(&image, 240, 140);
  exr_bitmap_free(&image);
  image = scene(font, 26);           /* rotate 180 about center */
  near(&image, 280, 150, 255, 0, 0, 0);
  white(&image, 240, 150);
  exr_bitmap_free(&image);
  image = scene(font, 27);           /* skew x' = x - y */
  near(&image, 250, 190, 255, 0, 0, 0);
  near(&image, 300, 190, 255, 255, 255, 0);
  white(&image, 320, 190);
  exr_bitmap_free(&image);
  image = scene(font, 28);           /* skew y' = y + x */
  near(&image, 225, 190, 255, 0, 0, 0);
  near(&image, 250, 160, 255, 0, 0, 0);
  white(&image, 250, 60);
  exr_bitmap_free(&image);
  image = scene(font, 29);           /* affine transform */
  near(&image, 250, 170, 255, 0, 0, 0);
  white(&image, 225, 170);
  exr_bitmap_free(&image);
}

static void composite_scenes(exr_font *font) {
  exr_bitmap image;
  exr_status status;
  image = scene(font, 30);           /* PaintColrGlyph */
  near(&image, 250, 150, 255, 0, 0, 0);
  exr_bitmap_free(&image);
  image = scene(font, 31);           /* SRC_OVER */
  near(&image, 250, 150, 0, 0, 255, 0);
  near(&image, 230, 150, 255, 0, 0, 0);
  exr_bitmap_free(&image);
  image = scene(font, 32);           /* multiply: blue * yellow -> black */
  near(&image, 250, 150, 0, 0, 0, 0);
  near(&image, 230, 150, 0, 0, 255, 0);
  exr_bitmap_free(&image);
  image = scene(font, 33);           /* screen: red + blue -> magenta */
  near(&image, 250, 150, 255, 0, 255, 0);
  exr_bitmap_free(&image);
  image = scene(font, 34);           /* difference: red - yellow -> green */
  near(&image, 250, 150, 0, 255, 0, 0);
  exr_bitmap_free(&image);
  image = scene(font, 35);           /* luminosity */
  {
    const unsigned char *p = image.pixels + (size_t)160*image.stride + (size_t)250*4;
    CHECK(p[0] > p[1] && p[0] > p[2] && p[0] < 200);
  }
  exr_bitmap_free(&image);
  image = render_glyph(font, 36, 100, 0x000000ff, 0, 0, 440, NULL, &status);
  CHECK(status == EXR_UNSUPPORTED && !image.pixels);
  image = render_glyph(font, 37, 100, 0x000000ff, 0, 0, 440, NULL, &status);
  CHECK(status == EXR_UNSUPPORTED && !image.pixels);
}

static void failures(exr_font *font) {
  exr_status status;
  exr_bitmap image;
  unsigned id;
  for (id = 41; id <= 42; id++) {
    image = render_glyph(font, id, 100, 0x000000ff, 0, 0, 440, NULL, &status);
    CHECK(status == EXR_FONT && !image.pixels);
  }
  image = render_glyph(font, 43, 100, 0x000000ff, 0, 0, 440, NULL, &status);
  CHECK(status == EXR_LIMIT && !image.pixels);
  image = render_glyph(font, 44, 100, 0x000000ff, 0, 0, 440, NULL, &status);
  CHECK(status == EXR_LIMIT && !image.pixels);
  render_page_width = 5000;
  render_page_height = 5000;
  image = render_glyph(font, 7, 4000, 0x000000ff, 0, 0, 0, NULL, &status);
  CHECK(status == EXR_LIMIT && !image.pixels);
  render_page_width = 440;
  render_page_height = 400;
  {
    unsigned i;
    for (i = 0; i <= 6; i += 3) {
      cancel_state state = {0, i};
      exr_control control = {0};
      control.context = &state; control.cancelled = cancelled;
      image = render_glyph(font, 10, 100, 0x000000ff, 0, 0, 440, &control, &status);
      CHECK(status == EXR_CANCELLED && !image.pixels);
    }
    {
      cancel_state state = {0, 1};
      exr_control control = {0};
      control.context = &state; control.cancelled = cancelled;
      image = render_glyph(font, 17, 100, 0x000000ff, 0, 0, 440, &control, &status);
      CHECK(status == EXR_CANCELLED && !image.pixels);
    }
  }
}

static void orientation(exr_font *font) {
  exr_bitmap image;
  exr_status status;
  image = render_glyph(font, 7, 100, 0x000000ff, EXR_GLYPH_VERTICAL, 0, 440, NULL, &status);
  CHECK(status == EXR_OK);
  near(&image, 250, 150, 255, 0, 0, 0);
  exr_bitmap_free(&image);
  image = render_glyph(font, 7, 100, 0x000000ff, EXR_GLYPH_VERTICAL, 170, 190, NULL, &status);
  CHECK(status == EXR_OK);
  near(&image, 250, 180, 255, 0, 0, 0);
  white(&image, 250, 150);
  exr_bitmap_free(&image);
  image = render_glyph(font, 7, 100, 0x000000ff, EXR_GLYPH_VERTICAL | EXR_GLYPH_SIDEWAYS, 0, 440, NULL, &status);
  CHECK(status == EXR_OK);
  near(&image, 250, 240, 255, 0, 0, 0);
  white(&image, 250, 150);
  exr_bitmap_free(&image);
  {
    exr_document *document = NULL;
    exr_layout *layout = NULL;
    exr_layout_config config = exr_layout_config_defaults();
    const exr_glyph *glyphs;
    const exr_line *line;
    size_t count, line_count;
    config.page = (exr_layout_options){200, 400, 0, 100, 1, 0};
    config.user_css = "p {writing-mode:vertical-rl}";
    OK(exr_document_open_memory(EXR_TXT, "A", 1, &document, &error));
    OK(exr_layout_create_ex(document, font, &config, &layout, &error));
    glyphs = exr_layout_glyphs(layout, &count);
    line = exr_layout_lines(layout, &line_count);
    CHECK(count == 1 && line != NULL && line_count == 1 && line[0].height > 0 &&
          (glyphs[0].flags & EXR_GLYPH_VERTICAL) && glyphs[0].glyph == 7 && glyphs[0].advance > 0);
    OK(exr_render_page_color(layout, NULL, 0, &image, &error));
    CHECK(image.pixels != NULL && image.width == 200 && image.height == 400);

    exr_bitmap_free(&image);
    exr_layout_free(layout);
    exr_document_free(document);
  }
}

static void variable(const char *directory) {
  char path[4096];
  FILE *file;
  long size;
  unsigned char *data;
  exr_font_input input = {0};
  exr_font *font;
  exr_font_coordinate coordinate = {0};
  exr_bitmap image;
  exr_status status;
  snprintf(path, sizeof(path), "%s/colrv1-var.ttf", directory);
  file = fopen(path, "rb");
  CHECK(file != NULL);
  fseek(file, 0, SEEK_END); size = ftell(file); rewind(file);
  data = malloc((size_t)size);
  CHECK(data && fread(data, 1, (size_t)size, file) == (size_t)size);
  fclose(file);
  input.data = data; input.size = (size_t)size; input.face_index = 0;
  coordinate.tag = EXR_TAG('w', 'g', 'h', 't');
  coordinate.value = 400;
  OK(exr_font_create_variable(&input, 1, &coordinate, 1, &font, &error));
  image = render_glyph(font, 3, 100, 0x000000ff, 0, 0, 440, NULL, &status);
  CHECK(status == EXR_OK);
  near(&image, 250, 150, 255, 191, 191, 2);
  exr_bitmap_free(&image);
  exr_font_free(font);
  coordinate.value = 900;
  OK(exr_font_create_variable(&input, 1, &coordinate, 1, &font, &error));
  image = render_glyph(font, 3, 100, 0x000000ff, 0, 0, 440, NULL, &status);
  CHECK(status == EXR_OK);
  near(&image, 250, 150, 255, 64, 64, 2);
  exr_bitmap_free(&image);
  image = render_glyph(font, 4, 100, 0x000000ff, 0, 0, 440, NULL, &status);
  CHECK(status == EXR_OK);
  near(&image, 250, 150, 255, 191, 191, 2);
  exr_bitmap_free(&image);
  exr_font_free(font);
  free(data);
}

static void layout_identity(exr_font *font) {
  exr_document *document = NULL;
  exr_layout *layout = NULL;
  exr_layout_config config = exr_layout_config_defaults();
  const exr_glyph *glyphs;
  size_t count, i;
  exr_bitmap expected = {0}, actual = {0};
  config.page = (exr_layout_options){400, 200, 0, 100, 1, 0};
  OK(exr_document_open_memory(EXR_TXT, "ABCD", 4, &document, &error));
  OK(exr_layout_create_ex(document, font, &config, &layout, &error));
  glyphs = exr_layout_glyphs(layout, &count);
  CHECK(count == 4);
  for (i = 0; i < count; i++) {
    CHECK(glyphs[i].cluster_start == i && glyphs[i].cluster_end == i + 1);
    CHECK(glyphs[i].glyph == 7 + i);
  }
  OK(exr_render_page_color(layout, NULL, 0, &expected, &error));
  near(&expected, 40, 60, 255, 0, 0, 0);
  for (i = 0; i < count; i++) {
    size_t hit = exr_layout_hit_test(layout, 0, glyphs[i].x + 1,
                                     glyphs[i].baseline - glyphs[i].size/3);
    CHECK(hit == glyphs[i].cluster_start);
  }
  {
    exr_pager *pager = NULL;
    exr_layout *part = NULL;
    OK(exr_pager_create(document, font, &config, &pager, &error));
    OK(exr_pager_next(pager, &part, &error));
    CHECK(part != NULL);
    OK(exr_render_page_color(part, NULL, 0, &actual, &error));
    CHECK(expected.width == actual.width && expected.height == actual.height &&
          !memcmp(expected.pixels, actual.pixels, (size_t)expected.stride*expected.height));
    exr_bitmap_free(&actual);
    exr_layout_free(part);
    exr_pager_free(pager);
  }
  exr_bitmap_free(&expected);
  exr_layout_free(layout);
  exr_document_free(document);
}

int main(int argc, char **argv) {
  exr_font *font;
  exr_document *document = NULL;
  exr_layout *layout = NULL;
  exr_layout_config config;
  exr_bitmap image = {0};
  CHECK(argc == 3);
  font = open_font(argv[1], "colrv1.ttf");
  information(argv[1]);
  solid_scenes(font);
  gradient_scenes(font);
  transform_scenes(font);
  composite_scenes(font);
  failures(font);
  orientation(font);
  layout_identity(font);
  exr_font_free(font);
  variable(argv[1]);
  /* Pager recovery on a vertical multi-page document. */
  font = open_font(argv[1], "colrv1.ttf");
  config = exr_layout_config_defaults();
  CHECK(argc == 3);
  config.page = (exr_layout_options){200, 200, 0, 100, 1, 0};
  config.user_css = "p {margin:0}";
  OK(exr_document_open_memory(EXR_TXT, "AAAAAAAAAA", 10, &document, &error));
  OK(exr_layout_create_ex(document, font, &config, &layout, &error));
  OK(exr_render_page_color(layout, NULL, 0, &image, &error));
  exr_bitmap_free(&image);
  exr_layout_free(layout);
  exr_document_free(document);
  exr_font_free(font);
  printf("%u COLR v1 paint, gradient, transform, composite, limit and identity checks passed\n", checks);
  return 0;
}
