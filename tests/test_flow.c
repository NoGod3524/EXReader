/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static exr_error error;
static unsigned checks;
static const char *fixtures, *output_dir;
static exr_font *font;
#define CHECK(x)                                                                                   \
  do {                                                                                             \
    checks++;                                                                                      \
    if (!(x)) {                                                                                    \
      fprintf(stderr, "line %d: %s (%s)\n", __LINE__, #x, error.message);                          \
      exit(1);                                                                                     \
    }                                                                                              \
  } while (0)
#define OK(x) CHECK((x) == EXR_OK)
static int near(float a, float b) { return fabsf(a - b) < 0.1f; }
static exr_document *open_book(const char *name) {
  char path[4096];
  exr_document *doc = NULL;
  snprintf(path, sizeof(path), "%s/%s", fixtures, name);
  OK(exr_document_open(path, &doc, &error));
  return doc;
}
static size_t id(const exr_document *doc, const char *name) {
  size_t n, i;
  const exr_node *nodes = exr_document_nodes(doc, &n);
  for (i = 0; i < n; i++) {
    const char *value = exr_node_attribute(&nodes[i], "id");
    if (value && !strcmp(value, name))
      return i;
  }
  CHECK(0);
  return SIZE_MAX;
}
static const exr_glyph *glyph(const exr_document *doc, const exr_layout *layout, const char *name) {
  size_t node = id(doc, name), n, i;
  const exr_node *nodes = exr_document_nodes(doc, NULL);
  const exr_glyph *g = exr_layout_glyphs(layout, &n);
  for (i = 0; i < n; i++) {
    size_t parent = g[i].node;
    while (parent != SIZE_MAX) {
      if (parent == node)
        return &g[i];
      parent = nodes[parent].parent;
    }
  }
  return NULL;
}
static const exr_glyph *require_glyph(const exr_document *doc, const exr_layout *layout,
                                      const char *name) {
  const exr_glyph *g = glyph(doc, layout, name);
  CHECK(g);
  return g;
}
static const exr_box *get_box(const exr_document *doc, const exr_layout *layout, const char *name,
                              exr_box_kind kind) {
  size_t node = id(doc, name), n, i;
  const exr_box *boxes = exr_layout_boxes(layout, &n);
  for (i = 0; i < n; i++)
    if (boxes[i].node == node && boxes[i].kind == kind)
      return &boxes[i];
  CHECK(0);
  return NULL;
}
static void geometry(const exr_layout *layout, exr_layout_options o) {
  size_t np, nl, ng, nb, i, j;
  const exr_page *p = exr_layout_pages(layout, &np);
  const exr_line *l = exr_layout_lines(layout, &nl);
  const exr_glyph *g = exr_layout_glyphs(layout, &ng);
  const exr_box *b = exr_layout_boxes(layout, &nb);
  CHECK(np > 0);
  for (i = 0; i < np; i++) {
    CHECK(p[i].line_start + p[i].line_count <= nl);
    CHECK(p[i].box_start + p[i].box_count <= nb);
    for (j = p[i].line_start; j < p[i].line_start + p[i].line_count; j++)
      CHECK(l[j].page == i);
    for (j = p[i].box_start; j < p[i].box_start + p[i].box_count; j++)
      CHECK(b[j].page == i);
  }
  for (i = 0; i < nl; i++) {
    CHECK(isfinite(l[i].x) && isfinite(l[i].y) && isfinite(l[i].height));
    CHECK(l[i].y >= o.margin - 0.1f && l[i].y + l[i].height <= o.height - o.margin + 0.1f);
    CHECK(l[i].glyph_start + l[i].glyph_count <= ng && l[i].glyph_count);
  }
  for (i = 0; i < ng; i++) {
    CHECK(isfinite(g[i].baseline) && isfinite(g[i].advance) && g[i].page < np);
    CHECK(g[i].start < g[i].end && g[i].clip_left < g[i].clip_right);
  }
  for (i = 0; i < nb; i++) {
    CHECK(isfinite(b[i].height) && isfinite(b[i].width) && b[i].width > 0 && b[i].height >= 0);
    CHECK(b[i].x >= o.margin - 0.1f && b[i].x + b[i].width <= o.width - o.margin + 0.1f);
    CHECK(b[i].y >= o.margin - 0.1f && b[i].y + b[i].height <= o.height - o.margin + 0.1f);
  }
}
static void save_png(const exr_bitmap *b, const char *name) {
  char path[4096];
  snprintf(path, sizeof(path), "%s/%s", output_dir, name);
  OK(exr_bitmap_write_png(b, path, &error));
}
static void pixel_at(const exr_bitmap *bitmap, const exr_box *box, float fraction, unsigned r,
                     unsigned g, unsigned b, int tolerance) {
  size_t x = (size_t)(box->x + box->width * fraction), y = (size_t)(box->y + box->height / 2);
  const unsigned char *p;
  CHECK(x < bitmap->width && y < bitmap->height && bitmap->channels == 4);
  p = bitmap->pixels + y * bitmap->stride + x * 4;
  CHECK(abs((int)p[0] - (int)r) <= tolerance && abs((int)p[1] - (int)g) <= tolerance &&
        abs((int)p[2] - (int)b) <= tolerance && p[3] == 255);
}
static void styled_book(void) {
  exr_document *doc = open_book("layout.epub");
  exr_layout *layout = NULL, *override = NULL, *plain = NULL;
  exr_layout_config config = exr_layout_config_defaults();
  exr_bitmap rgba = {0}, again = {0}, gray = {0};
  const exr_box *png, *jpeg, *span, *right, *lower, *wide;
  const exr_bitmap *decoded;
  const exr_glyph *g;
  size_t i, n;
  OK(exr_layout_create_ex(doc, font, &config, &layout, &error));
  geometry(layout, config.page);
  CHECK(near(require_glyph(doc, layout, "intro")->size, 24));
  CHECK(near(require_glyph(doc, layout, "intro")->x, config.page.margin + 24));
  g = require_glyph(doc, layout, "bold");
  CHECK(near(g->size, 30) && (g->flags & 1));
  CHECK(require_glyph(doc, layout, "italic")->flags & 2);
  CHECK(near(require_glyph(doc, layout, "panel")->size, 18));
  CHECK(require_glyph(doc, layout, "priority")->color == 0x008000ff);
  CHECK(require_glyph(doc, layout, "order")->color == 0x0000ffff);
  CHECK(near(require_glyph(doc, layout, "invalid")->size, 23));
  CHECK(near(require_glyph(doc, layout, "scope")->size, config.page.font_size));
  CHECK(!glyph(doc, layout, "hidden"));
  CHECK(strstr(exr_document_text(doc, NULL), "Hidden by stylesheet."));
  span = get_box(doc, layout, "span", EXR_BOX_CELL);
  right = get_box(doc, layout, "right", EXR_BOX_CELL);
  lower = get_box(doc, layout, "lower", EXR_BOX_CELL);
  wide = get_box(doc, layout, "wide", EXR_BOX_CELL);
  CHECK(near(span->height, right->height + lower->height));
  CHECK(near(span->width + right->width, wide->width));
  CHECK(near(span->y, right->y) && near(lower->y, right->y + right->height));
  CHECK(span->page == lower->page && right->page == lower->page);
  g = require_glyph(doc, layout, "right");
  CHECK(exr_layout_hit_test(layout, g->page, g->x + 0.1f, g->baseline - 3) == g->start);
  png = get_box(doc, layout, "png", EXR_BOX_IMAGE);
  jpeg = get_box(doc, layout, "jpeg", EXR_BOX_IMAGE);
  CHECK(!png->flags && !jpeg->flags && near(png->width, 192) && near(png->height, 96));
  CHECK(near(png->x, (config.page.width - png->width) / 2));
  decoded = exr_layout_image(layout, png->resource);
  CHECK(decoded && decoded->channels == 4 && decoded->width == 96 && decoded->height == 48);
  CHECK(decoded->pixels[95 * 4 + 3] == 128);
  {
    void *encoded = NULL;
    size_t bytes;
    exr_bitmap independent = {0};
    OK(exr_document_resource(doc, png->resource, &encoded, &bytes, &error));
    OK(exr_image_decode(encoded, bytes, &independent, &error));
    CHECK(independent.channels == 4 && independent.stride == decoded->stride);
    CHECK(!memcmp(independent.pixels, decoded->pixels, (size_t)decoded->stride * decoded->height));
    exr_bitmap_free(&independent);
    exr_free(encoded);
    CHECK(exr_image_decode(NULL, 0, &independent, &error) == EXR_ARGUMENT && !independent.pixels);
  }
  CHECK(!exr_layout_image(layout, SIZE_MAX) && !exr_layout_image(NULL, 0));
  OK(exr_render_page_color(layout, font, png->page, &rgba, &error));
  pixel_at(&rgba, png, 0.16f, 220, 40, 30, 0);
  pixel_at(&rgba, png, 0.5f, 30, 180, 60, 0);
  pixel_at(&rgba, png, 0.84f, 137, 152, 237, 1);
  save_png(&rgba, "native-styled-page.png");
  OK(exr_render_page(layout, font, png->page, &gray, &error));
  CHECK(gray.channels == 1 && gray.width == rgba.width && gray.height == rgba.height);
  exr_bitmap_free(&gray);
  OK(exr_render_page_color(layout, font, jpeg->page, &again, &error));
  pixel_at(&again, jpeg, 0.5f, 32, 128, 192, 3);
  exr_bitmap_free(&again);
  config.user_css = "#intro { font-size: 28px; text-align:right; } #priority {color:purple} "
                    ".hidden {display:block}";
  OK(exr_layout_create_ex(doc, font, &config, &override, &error));
  CHECK(near(require_glyph(doc, override, "intro")->size, 28));
  CHECK(require_glyph(doc, override, "intro")->x > require_glyph(doc, layout, "intro")->x);
  CHECK(require_glyph(doc, override, "priority")->color == 0x800080ff &&
        glyph(doc, override, "hidden"));
  config.document_css = 0;
  config.user_css = "#intro { font-size: 26px }";
  OK(exr_layout_create_ex(doc, font, &config, &plain, &error));
  CHECK(near(require_glyph(doc, plain, "intro")->size, 26));
  CHECK(require_glyph(doc, plain, "priority")->color == 0x000000ff && glyph(doc, plain, "hidden"));
  CHECK(near(require_glyph(doc, plain, "panel")->size, config.page.font_size));
  exr_layout_free(override);
  exr_layout_free(plain);
  /* Cached metrics must distinguish bold/normal and font size after another layout. */
  config = exr_layout_config_defaults();
  OK(exr_layout_create_ex(doc, font, &config, &plain, &error));
  g = exr_layout_glyphs(plain, &n);
  {
    const exr_glyph *original = exr_layout_glyphs(layout, &i);
    CHECK(i == n);
    for (i = 0; i < n; i++)
      CHECK(g[i].advance == original[i].advance && g[i].x == original[i].x &&
            g[i].page == original[i].page);
  }
  exr_layout_free(plain);
  exr_document_free(doc);
  OK(exr_render_page_color(layout, font, png->page, &again, &error));
  CHECK(!memcmp(rgba.pixels, again.pixels, (size_t)rgba.stride * rgba.height));
  CHECK(decoded->pixels[95 * 4 + 3] == 128);
  exr_bitmap_free(&rgba);
  exr_bitmap_free(&again);
  exr_layout_free(layout);
}
static void pagination(void) {
  exr_document *doc = open_book("layout-table.epub");
  exr_layout *layout = NULL;
  exr_layout_options o = exr_layout_defaults();
  size_t n, i;
  o.width = 400;
  o.height = 320;
  o.margin = 20;
  OK(exr_layout_create(doc, font, &o, &layout, &error));
  geometry(layout, o);
  exr_layout_pages(layout, &n);
  CHECK(n > 2);
  for (i = 0; i < 30; i++) {
    char name[32];
    const exr_box *left, *right;
    const exr_glyph *g;
    snprintf(name, sizeof(name), "left%u", (unsigned)i);
    left = get_box(doc, layout, name, EXR_BOX_CELL);
    snprintf(name, sizeof(name), "right%u", (unsigned)i);
    right = get_box(doc, layout, name, EXR_BOX_CELL);
    CHECK(left->page == right->page && near(left->y, right->y) &&
          near(left->height, right->height));
    g = require_glyph(doc, layout, name);
    CHECK(exr_layout_hit_test(layout, g->page, g->x, g->baseline - 2) == g->start);
    CHECK(exr_layout_page_at(layout, g->start) == g->page);
  }
  exr_layout_free(layout);
  exr_document_free(doc);
  doc = open_book("layout-break.epub");
  layout = NULL;
  OK(exr_layout_create(doc, font, &o, &layout, &error));
  CHECK(require_glyph(doc, layout, "before")->page == 0 &&
        require_glyph(doc, layout, "after")->page == 1);
  exr_layout_free(layout);
  exr_document_free(doc);
  doc = open_book("layout-tall.epub");
  layout = NULL;
  OK(exr_layout_create(doc, font, &o, &layout, &error));
  { size_t pages;exr_layout_pages(layout,&pages);CHECK(pages>1); }
  geometry(layout,o);exr_layout_free(layout);
  exr_document_free(doc);
  doc = open_book("layout-padding.epub");
  layout = NULL;
  o.height = 300;
  OK(exr_layout_create(doc, font, &o, &layout, &error));
  geometry(layout, o);
  exr_layout_free(layout);
  exr_document_free(doc);
}
typedef struct {
  int calls, releases, mode;
} decoder_state;
static exr_status host_decode(void *context, const exr_resource *resource, const void *bytes,
                              size_t n, exr_bitmap *out, exr_error *e) {
  decoder_state *state = context;
  static const unsigned char pixels[12] = {10, 20, 30, 255, 40, 50, 60, 255, 0, 0, 0, 0};
  (void)e;
  state->calls++;
  CHECK(!strcmp(resource->media_type, "image/png") && n > 8 &&
        !memcmp(bytes, "\x89PNG\r\n\x1a\n", 8));
  out->width = 2;
  out->height = 1;
  out->stride = 12;
  out->channels = state->mode == 1 ? 1 : 4;
  out->pixels = malloc(12);
  CHECK(out->pixels);
  memcpy(out->pixels, pixels, 12);
  return state->mode == 2 ? EXR_FORMAT : state->mode == 3 ? EXR_MEMORY : EXR_OK;
}
static void host_release(void *context, exr_bitmap *bitmap) {
  decoder_state *state = context;
  state->releases++;
  free(bitmap->pixels);
  memset(bitmap, 0, sizeof(*bitmap));
}
static void images_and_limits(void) {
  exr_document *doc = open_book("layout-image.epub");
  exr_layout *layout = NULL;
  exr_layout_config config = exr_layout_config_defaults();
  exr_bitmap bitmap = {0};
  size_t n, i;
  const exr_box *box;
  decoder_state state = {0};
  OK(exr_layout_create_ex(doc, font, &config, &layout, &error));
  exr_layout_pages(layout, &n);
  CHECK(n == 1);
  exr_layout_glyphs(layout, &n);
  CHECK(n == 0);
  box = get_box(doc, layout, "image", EXR_BOX_IMAGE);
  OK(exr_render_page_color(layout, font, 0, &bitmap, &error));
  pixel_at(&bitmap, box, 0.16f, 220, 40, 30, 0);
  save_png(&bitmap, "native-image-page.png");
  {
    char path[4096];
    snprintf(path, sizeof(path), "%s/native-image-page.bmp", output_dir);
    OK(exr_bitmap_write_bmp(&bitmap, path, &error));
  }
  exr_bitmap_free(&bitmap);
  exr_layout_free(layout);
  layout = NULL;
  config.decode_image = host_decode;
  config.image_context = &state;
  CHECK(exr_layout_create_ex(doc, font, &config, &layout, &error) == EXR_ARGUMENT && !layout);
  CHECK(!state.calls && !state.releases);
  config.release_image = host_release;
  OK(exr_layout_create_ex(doc, font, &config, &layout, &error));
  box = get_box(doc, layout, "image", EXR_BOX_IMAGE);
  CHECK(state.calls == 1 && state.releases == 1 && !box->flags);
  CHECK(exr_layout_image(layout, box->resource)->stride == 8);
  OK(exr_render_page_color(layout, font, 0, &bitmap, &error));
  pixel_at(&bitmap, box, 0.16f, 10, 20, 30, 0);
  exr_bitmap_free(&bitmap);
  exr_layout_free(layout);
  layout = NULL;
  state.mode = 1;
  CHECK(exr_layout_create_ex(doc, font, &config, &layout, &error) == EXR_ARGUMENT && !layout &&
        error.message[0]);
  CHECK(state.calls == 2 && state.releases == 2);
  state.mode = 2;
  OK(exr_layout_create_ex(doc, font, &config, &layout, &error));
  CHECK(get_box(doc, layout, "image", EXR_BOX_IMAGE)->flags == 1);
  exr_layout_free(layout);
  layout = NULL;
  state.mode = 3;
  CHECK(exr_layout_create_ex(doc, font, &config, &layout, &error) == EXR_MEMORY && !layout);
  CHECK(state.calls == 4 && state.releases == 4);
  exr_document_free(doc);
  doc = open_book("layout-placeholder.epub");
  for (i = 0; i < 32; i++) {
    OK(exr_layout_create(doc, font, NULL, &layout, &error));
    box = exr_layout_boxes(layout, &n);
    CHECK(n == 2 && box[0].flags == 1 && box[1].flags == 1);
    exr_layout_free(layout);
    layout = NULL;
  }
  exr_document_free(doc);
  doc = open_book("layout-huge.epub");
  CHECK(exr_layout_create(doc, font, NULL, &layout, &error) == EXR_LIMIT && !layout);
  exr_document_free(doc);
  doc = open_book("layout-damaged.epub");
  for (i = 0; i < 32; i++) {
    OK(exr_layout_create(doc, font, NULL, &layout, &error));
    box = exr_layout_boxes(layout, &n);
    CHECK(n == 1 && box->flags == 1);
    exr_layout_free(layout);
    layout = NULL;
  }
  exr_document_free(doc);
}
static void css_failures(void) {
  exr_document *doc = open_book("layout-malformed-css.epub");
  exr_layout *layout = NULL;
  exr_layout_config config = exr_layout_config_defaults();
  const exr_box *b;
  char *large = malloc(1024 * 1024 + 2);
  CHECK(large);
  OK(exr_layout_create_ex(doc, font, &config, &layout, &error));
  CHECK(require_glyph(doc, layout, "target")->color == 0x123456ff);
  exr_layout_free(layout);
  layout = NULL;
  config.user_css = "#target { padding: 7px; padding: 20px invalid; border: 2px solid blue; "
                    "border: 4px dotted bad; background: #abc; }";
  OK(exr_layout_create_ex(doc, font, &config, &layout, &error));
  b = get_box(doc, layout, "target", EXR_BOX_BLOCK);
  CHECK(near(b->border_width, 2) && b->border_color == 0x0000ffff && b->background == 0xaabbccff);
  CHECK(near(require_glyph(doc, layout, "target")->x, b->x + 9));
  exr_layout_free(layout);
  layout = NULL;
  config.user_css = "#target { display:none }";
  OK(exr_layout_create_ex(doc, font, &config, &layout, &error));
  CHECK(!glyph(doc, layout, "target"));
  exr_layout_free(layout);
  layout = NULL;
  memset(large, ' ', 1024 * 1024 + 1);
  large[1024 * 1024 + 1] = 0;
  config.user_css = large;
  CHECK(exr_layout_create_ex(doc, font, &config, &layout, &error) == EXR_LIMIT && !layout);
  free(large);
  exr_document_free(doc);
}
int main(int argc, char **argv) {
  const char *font_path = getenv("EXR_TEST_FONT");
  CHECK(argc == 3);
  fixtures = argv[1];
  output_dir = argv[2];
#ifdef _WIN32
  if (!font_path)
    font_path = "C:/Windows/Fonts/arial.ttf";
#elif defined(__APPLE__)
  if (!font_path)
    font_path = "/System/Library/Fonts/Supplemental/Arial.ttf";
#else
  if (!font_path)
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf";
#endif
  OK(exr_font_open(font_path, &font, &error));
  styled_book();
  pagination();
  images_and_limits();
  css_failures();
  exr_font_free(font);
  printf("EXReader flow: %u checks passed\n", checks);
  return 0;
}
