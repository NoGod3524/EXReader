/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static exr_error error;
static unsigned checks;
static const char *fixtures;
static exr_font *font;
#define CHECK(x)                                                                                   \
  do {                                                                                             \
    checks++;                                                                                      \
    if (!(x)) {                                                                                    \
      fprintf(stderr, "line %d: %s (%d: %s)\n", __LINE__, #x, (int)error.code, error.message);     \
      exit(1);                                                                                     \
    }                                                                                              \
  } while (0)
#define OK(x) CHECK((x) == EXR_OK)

static void reject(const exr_document_input *input, exr_status expected) {
  exr_document *doc = (exr_document *)(uintptr_t)1;
  exr_status status = exr_document_create(input, &doc, &error);
  CHECK(status == expected && error.code == expected && !doc);
  CHECK(error.message[0]);
}

static void *fixture_png(size_t *size) {
  exr_document *doc = NULL;
  const exr_resource *resources;
  void *bytes = NULL;
  char path[4096];
  size_t count, i;
  snprintf(path, sizeof(path), "%s/layout.epub", fixtures);
  OK(exr_document_open(path, &doc, &error));
  resources = exr_document_resources(doc, &count);
  for (i = 0; i < count; i++)
    if (!strcmp(resources[i].media_type, "image/png")) {
      OK(exr_document_resource(doc, i, &bytes, size, &error));
      break;
    }
  CHECK(bytes && *size);
  exr_document_free(doc);
  return bytes;
}

static exr_document *construct(void) {
  char title[] = "Host supplied document";
  char paragraph[] = "  alpha \t";
  char tail[] = " \n tail  ";
  char classname[] = "body";
  char stylesheet[] = ".body {font-size:26px;color:#1256ab} image {width:96px}";
  char properties[] = "host-extension";
  unsigned char empty = 0;
  size_t png_size;
  void *png = fixture_png(&png_size);
  exr_attribute paragraph_attrs[] = {{"class", classname}, {"id", "paragraph"}};
  exr_attribute link_attrs[] = {{"href", "../aux%23%25%3F.unit#note"}};
  exr_attribute image_attrs[] = {{"src", "../images/pic.png"}, {"width", "96"}, {"height", "48"}};
  exr_attribute css_attrs[] = {{"rel", "stylesheet"}, {"href", "../theme/style.css"}};
  exr_attribute note_attrs[] = {{"id", "note"}};
  exr_node_input nodes[] = {
      {EXR_NODE_DOCUMENT, SIZE_MAX, NULL, NULL, NULL, 0},
      {EXR_NODE_CHAPTER, 0, "unit", NULL, NULL, 0},
      {EXR_NODE_ELEMENT, 1, "http://www.w3.org/1999/xhtml|link", NULL, css_attrs, 2},
      {EXR_NODE_HEADING, 1, NULL, NULL, NULL, 0},
      {EXR_NODE_TEXT, 3, NULL, "Heading", NULL, 0},
      {EXR_NODE_PARAGRAPH, 1, NULL, NULL, paragraph_attrs, 2},
      {EXR_NODE_TEXT, 5, NULL, paragraph, NULL, 0},
      {EXR_NODE_LINK, 5, "reference", NULL, link_attrs, 1},
      {EXR_NODE_TEXT, 7, NULL, "\xe4\xb8\xad\xe6\x96\x87", NULL, 0},
      {EXR_NODE_TEXT, 5, NULL, tail, NULL, 0},
      {EXR_NODE_IMAGE, 1, NULL, NULL, image_attrs, 3},
      {EXR_NODE_CHAPTER, 0, NULL, NULL, NULL, 0},
      {EXR_NODE_NOTE, 11, "host-note", NULL, note_attrs, 1},
      {EXR_NODE_TEXT, 12, NULL, "Auxiliary text outside reading order.", NULL, 0}};
  exr_chapter_input chapters[] = {{"main", "chapters/main.unit", 1, 1},
                                  {"notes", "aux#%?.unit", 11, 0}};
  exr_resource_input resources[] = {
      {{"picture", "images/pic.png", "image/png", properties}, png, png_size},
      {{"css", "theme/style.css", "text/css", NULL}, stylesheet, sizeof(stylesheet) - 1},
      {{"missing", "attachments/missing", "application/octet-stream", NULL}, NULL, 0},
      {{"empty", "attachments/empty", "application/octet-stream", NULL}, &empty, 0}};
  exr_document_input input = {title,     nodes, sizeof(nodes) / sizeof(*nodes), chapters, 2,
                              resources, 4};
  exr_document *doc = NULL;
  void *copy = NULL;
  size_t size;
  OK(exr_document_create(&input, &doc, &error));
  CHECK(doc && error.code == EXR_OK && !error.message[0]);
  OK(exr_document_resource(doc, 0, &copy, &size, &error));
  CHECK(size == png_size && !memcmp(copy, png, size) && copy != png);
  exr_free(copy);
  memset(title, '!', sizeof(title) - 1);
  memset(paragraph, '!', sizeof(paragraph) - 1);
  memset(tail, '!', sizeof(tail) - 1);
  memset(classname, '!', sizeof(classname) - 1);
  memset(stylesheet, '!', sizeof(stylesheet) - 1);
  memset(properties, '!', sizeof(properties) - 1);
  memset(png, 0, png_size);
  exr_free(png);
  memset(nodes, 0, sizeof(nodes));
  memset(chapters, 0, sizeof(chapters));
  memset(resources, 0, sizeof(resources));
  return doc;
}

static void integration(void) {
  exr_document *doc = construct(), *roundtrip = NULL;
  exr_layout *layout = NULL;
  exr_bitmap bitmap = {0};
  const char *text = exr_document_text(doc, NULL);
  const exr_node *nodes;
  const exr_chapter *chapters;
  const exr_resource *resources;
  const exr_glyph *glyphs;
  const exr_box *boxes, *image = NULL;
  const exr_bitmap *decoded;
  const exr_block *blocks;
  void *bytes = NULL;
  size_t count, resource, node, start, end, size, i;
  CHECK(exr_document_format(doc) == EXR_CUSTOM);
  CHECK(!strcmp(exr_document_title(doc), "Host supplied document"));
  CHECK(!strcmp(text, "Heading\nalpha \xe4\xb8\xad\xe6\x96\x87 tail"));
  nodes = exr_document_nodes(doc, &count);
  CHECK(count == 14 && nodes[0].parent == SIZE_MAX && nodes[0].first_child == 1);
  CHECK(nodes[1].next_sibling == 11 && nodes[11].next_sibling == SIZE_MAX);
  CHECK(!nodes[3].name && !nodes[5].name && !strcmp(nodes[7].name, "reference"));
  CHECK(!strcmp(nodes[6].text, "  alpha \t") &&
        !strcmp(exr_node_attribute(&nodes[5], "class"), "body"));
  CHECK(nodes[4].start == 0 && nodes[4].end == strlen("Heading"));
  CHECK(nodes[8].end - nodes[8].start >= 6 && nodes[8].end <= strlen(text));
  CHECK(nodes[11].start == SIZE_MAX && nodes[12].start == SIZE_MAX && nodes[13].start == SIZE_MAX);
  for (i = 1; i < count; i++)
    CHECK(nodes[i].parent < i && nodes[i].chapter == (i < 11 ? 0u : 1u));
  chapters = exr_document_chapters(doc, &count);
  CHECK(count == 2 && chapters[0].root == 1 && chapters[0].resource == SIZE_MAX);
  CHECK(chapters[0].in_spine && chapters[0].linear && !chapters[1].in_spine);
  resources = exr_document_resources(doc, &count);
  CHECK(count == 4 && !strcmp(resources[0].properties, "host-extension"));
  blocks = exr_document_blocks(doc, &count);
  CHECK(count == 2 && blocks[0].heading == 1 && !blocks[1].heading);
  OK(exr_document_find(doc, "\xe4\xb8\xad\xe6\x96\x87", 0, &start, &end, &error));
  CHECK(end - start == 6 && !memcmp(text + start, "\xe4\xb8\xad\xe6\x96\x87", 6));
  OK(exr_document_resolve(doc, 0, "../aux%23%25%3F.unit#note", &resource, &node, &error));
  CHECK(resource == SIZE_MAX && node == 12);
  OK(exr_document_resolve(doc, 0, "#paragraph", &resource, &node, &error));
  CHECK(resource == SIZE_MAX && node == 5);
  OK(exr_document_resolve(doc, 1, "chapters/main.unit#paragraph", &resource, &node, &error));
  CHECK(resource == SIZE_MAX && node == 5);
  OK(exr_document_resolve(doc, 0, "../images/pic.png", &resource, &node, &error));
  CHECK(resource == 0 && node == SIZE_MAX);
  OK(exr_document_resource(doc, 3, &bytes, &size, &error));
  CHECK(bytes && size == 0);
  exr_free(bytes);
  bytes = (void *)(uintptr_t)1;
  size = 123;
  CHECK(exr_document_resource(doc, 2, &bytes, &size, &error) == EXR_FORMAT && !bytes && !size);
  OK(exr_document_export(doc, EXR_TXT, &bytes, &size, &error));
  CHECK(size == strlen(text) && !memcmp(bytes, text, size));
  exr_free(bytes);
  OK(exr_document_export(doc, EXR_EPUB, &bytes, &size, &error));
  OK(exr_document_open_memory(EXR_EPUB, bytes, size, &roundtrip, &error));
  CHECK(!strcmp(exr_document_text(roundtrip, NULL), text));
  exr_document_free(roundtrip);
  exr_free(bytes);
  OK(exr_layout_create(doc, font, NULL, &layout, &error));
  glyphs = exr_layout_glyphs(layout, &count);
  CHECK(count > 0);
  for (i = 0; i < count; i++) {
    CHECK(glyphs[i].node < 11 && glyphs[i].end <= strlen(text));
    if (glyphs[i].node == 4)
      CHECK(glyphs[i].flags & 1);
    else
      CHECK(fabsf(glyphs[i].size - 26) < 0.1f && glyphs[i].color == 0x1256abff);
  }
  boxes = exr_layout_boxes(layout, &count);
  for (i = 0; i < count; i++)
    if (boxes[i].kind == EXR_BOX_IMAGE)
      image = &boxes[i];
  CHECK(image && image->resource == 0 && !image->flags);
  CHECK(fabsf(image->width - 96) < 0.1f && fabsf(image->height - 48) < 0.1f);
  decoded = exr_layout_image(layout, 0);
  CHECK(decoded && decoded->channels == 4 && decoded->width == 96 && decoded->height == 48);
  exr_document_free(doc);
  OK(exr_render_page_color(layout, font, image->page, &bitmap, &error));
  CHECK(bitmap.channels == 4);
  {
    size_t x = (size_t)(image->x + image->width / 2);
    size_t y = (size_t)(image->y + image->height / 2);
    const unsigned char *pixel = bitmap.pixels + y * bitmap.stride + x * 4;
    CHECK(x < bitmap.width && y < bitmap.height);
    CHECK(pixel[0] == 30 && pixel[1] == 180 && pixel[2] == 60 && pixel[3] == 255);
  }
  exr_bitmap_free(&bitmap);
  exr_layout_free(layout);
}

static void generic_names(void) {
  exr_attribute style[] = {{"style", "font-size:31px;color:#812345"}};
  exr_attribute hidden[] = {{"hidden", ""}};
  exr_node_input nodes[] = {
      {EXR_NODE_DOCUMENT, SIZE_MAX, NULL, NULL, NULL, 0},
      {EXR_NODE_CHAPTER, 0, NULL, NULL, NULL, 0},
      {EXR_NODE_HEADING, 1, "head", NULL, NULL, 0},
      {EXR_NODE_TEXT, 2, NULL, "Visible heading", NULL, 0},
      {EXR_NODE_ELEMENT, 1, "script", NULL, NULL, 0},
      {EXR_NODE_TEXT, 4, NULL, "Visible body ", NULL, 0},
      {EXR_NODE_ELEMENT, 4, "div", NULL, NULL, 0},
      {EXR_NODE_ELEMENT, 6, "strong", NULL, NULL, 0},
      {EXR_NODE_TEXT, 7, NULL, "plain strong ", NULL, 0},
      {EXR_NODE_ELEMENT, 4, "http://www.w3.org/1999/xhtml|strong", NULL, NULL, 0},
      {EXR_NODE_TEXT, 9, NULL, "XHTML strong", NULL, 0},
      {EXR_NODE_PARAGRAPH, 1, NULL, NULL, style, 1},
      {EXR_NODE_TEXT, 11, NULL, "Styled generic", NULL, 0},
      {EXR_NODE_PARAGRAPH, 1, NULL, NULL, hidden, 1},
      {EXR_NODE_TEXT, 13, NULL, "Hidden generic", NULL, 0},
      {EXR_NODE_ELEMENT, 1, "http://www.w3.org/1999/xhtml|head", NULL, NULL, 0},
      {EXR_NODE_TEXT, 15, NULL, "Hidden metadata", NULL, 0}};
  exr_chapter_input chapter = {NULL, "generic.unit", 1, 1};
  exr_document_input input = {NULL, nodes, sizeof(nodes) / sizeof(*nodes), &chapter, 1, NULL, 0};
  exr_document *doc = NULL;
  exr_layout *layout = NULL;
  const exr_node *built;
  const exr_glyph *glyphs;
  size_t i, count, seen = 0;
  OK(exr_document_create(&input, &doc, &error));
  CHECK(!strcmp(exr_document_text(doc, NULL),
                "Visible heading\nVisible body plain strong XHTML strong\nStyled generic"));
  built = exr_document_nodes(doc, NULL);
  CHECK(built[14].start == SIZE_MAX && built[16].start == SIZE_MAX);
  OK(exr_layout_create(doc, font, NULL, &layout, &error));
  glyphs = exr_layout_glyphs(layout, &count);
  for (i = 0; i < count; i++) {
    if (glyphs[i].node == 3) {
      CHECK(glyphs[i].flags & 1);
      seen |= 1;
    } else if (glyphs[i].node == 8) {
      CHECK(!(glyphs[i].flags & 1));
      seen |= 2;
    } else if (glyphs[i].node == 10) {
      CHECK(glyphs[i].flags & 1);
      seen |= 4;
    } else if (glyphs[i].node == 12) {
      CHECK(fabsf(glyphs[i].size - 31) < 0.1f && glyphs[i].color == 0x812345ff);
      seen |= 8;
    }
    CHECK(glyphs[i].node < 13);
  }
  CHECK(seen == 15);
  exr_layout_free(layout);
  exr_document_free(doc);
}

static void validation(void) {
  exr_node_input nodes[] = {{EXR_NODE_DOCUMENT, SIZE_MAX, NULL, NULL, NULL, 0},
                            {EXR_NODE_CHAPTER, 0, NULL, NULL, NULL, 0},
                            {EXR_NODE_PARAGRAPH, 1, NULL, NULL, NULL, 0},
                            {EXR_NODE_TEXT, 2, NULL, "text", NULL, 0}};
  exr_chapter_input chapter = {"main", "main.unit", 1, 1};
  exr_document_input input = {NULL, nodes, 4, &chapter, 1, NULL, 0};
  exr_attribute attrs[] = {{"id", "one"}, {"id", "two"}};
  exr_resource_input resources[] = {{{"one", "one.bin", NULL, NULL}, "x", 1},
                                    {{"two", "two.bin", NULL, NULL}, "y", 1}};
  exr_document *doc = NULL;
  const char *bad_paths[] = {"",     "/absolute", "../escape",     "a/./b", "a/../b",
                             "a//b", "a\\b",      "https:example", "a/",    "a\nfile"};
  size_t i;
  reject(NULL, EXR_ARGUMENT);
  CHECK(exr_document_create(&input, NULL, &error) == EXR_ARGUMENT);
  input.nodes = NULL;
  reject(&input, EXR_ARGUMENT);
  input.nodes = nodes;
  input.node_count = 0;
  reject(&input, EXR_ARGUMENT);
  input.node_count = 4;
  input.chapters = NULL;
  reject(&input, EXR_ARGUMENT);
  input.chapters = &chapter;
  input.chapter_count = 0;
  reject(&input, EXR_ARGUMENT);
  input.chapter_count = 1;
  nodes[0].kind = EXR_NODE_ELEMENT;
  reject(&input, EXR_ARGUMENT);
  nodes[0].kind = EXR_NODE_DOCUMENT;
  nodes[0].parent = 0;
  reject(&input, EXR_ARGUMENT);
  nodes[0].parent = SIZE_MAX;
  nodes[3].parent = 3;
  reject(&input, EXR_ARGUMENT);
  nodes[3].parent = 0;
  reject(&input, EXR_ARGUMENT);
  nodes[3].parent = 2;
  nodes[2].kind = EXR_NODE_CHAPTER;
  reject(&input, EXR_ARGUMENT);
  nodes[2].kind = EXR_NODE_PARAGRAPH;
  nodes[3].kind = (exr_node_kind)999;
  reject(&input, EXR_ARGUMENT);
  nodes[3].kind = EXR_NODE_TEXT;
  nodes[3].text = NULL;
  reject(&input, EXR_ARGUMENT);
  nodes[3].text = "\xc0\xaf";
  reject(&input, EXR_ENCODING);
  nodes[3].text = "text";
  input.title = "\xed\xa0\x80";
  reject(&input, EXR_ENCODING);
  input.title = NULL;
  nodes[2].text = "not a text node";
  reject(&input, EXR_ARGUMENT);
  nodes[2].text = NULL;
  nodes[2].attribute_count = 1;
  reject(&input, EXR_ARGUMENT);
  nodes[2].attributes = attrs;
  nodes[2].attribute_count = 2;
  reject(&input, EXR_ARGUMENT);
  nodes[2].attribute_count = 1;
  attrs[0].value = "\xf4\x90\x80\x80";
  reject(&input, EXR_ENCODING);
  attrs[0].value = NULL;
  reject(&input, EXR_ARGUMENT);
  attrs[0].value = "one";
  attrs[0].name = "";
  reject(&input, EXR_ARGUMENT);
  attrs[0].name = "id";
  nodes[2].attributes = NULL;
  nodes[2].attribute_count = 0;
  chapter.root = 2;
  reject(&input, EXR_ARGUMENT);
  chapter.root = 1;
  for (i = 0; i < sizeof(bad_paths) / sizeof(*bad_paths); i++) {
    chapter.path = bad_paths[i];
    reject(&input, EXR_ARGUMENT);
  }
  chapter.path = "main.unit";
  input.resources = resources;
  input.resource_count = 2;
  resources[1].info.path = resources[0].info.path;
  reject(&input, EXR_ARGUMENT);
  resources[1].info.path = "two.bin";
  resources[1].info.id = resources[0].info.id;
  reject(&input, EXR_ARGUMENT);
  resources[1].info.id = "two";
  resources[0].data = NULL;
  reject(&input, EXR_ARGUMENT);
  resources[0].data = "x";
  resources[0].size = (size_t)32 * 1024 * 1024 + 1;
  reject(&input, EXR_LIMIT);
  resources[0].size = 1;
  for (i = 0; i < sizeof(bad_paths) / sizeof(*bad_paths); i++) {
    resources[0].info.path = bad_paths[i];
    reject(&input, EXR_ARGUMENT);
  }
  resources[0].info.path = "one.bin";
  OK(exr_document_create(&input, &doc, &error));
  exr_document_free(doc);
  resources[0].info.path = "main.unit";
  OK(exr_document_create(&input, &doc, &error));
  {
    size_t resource, node;
    const exr_chapter *matched = exr_document_chapters(doc, NULL);
    CHECK(matched[0].resource == 0);
    OK(exr_document_resolve(doc, 0, "#", &resource, &node, &error));
    CHECK(resource == 0 && node == 1);
  }
  exr_document_free(doc);
  {
    exr_node_input preorder[] = {{EXR_NODE_DOCUMENT, SIZE_MAX, NULL, NULL, NULL, 0},
                                 {EXR_NODE_CHAPTER, 0, NULL, NULL, NULL, 0},
                                 {EXR_NODE_PARAGRAPH, 1, NULL, NULL, NULL, 0},
                                 {EXR_NODE_PARAGRAPH, 1, NULL, NULL, NULL, 0},
                                 {EXR_NODE_TEXT, 2, NULL, "late child", NULL, 0}};
    input.nodes = preorder;
    input.node_count = sizeof(preorder) / sizeof(*preorder);
    reject(&input, EXR_ARGUMENT);
  }
  {
    exr_node_input leaf[] = {{EXR_NODE_DOCUMENT, SIZE_MAX, NULL, NULL, NULL, 0},
                             {EXR_NODE_CHAPTER, 0, NULL, NULL, NULL, 0},
                             {EXR_NODE_IMAGE, 1, NULL, NULL, NULL, 0},
                             {EXR_NODE_TEXT, 2, NULL, "ignored child", NULL, 0}};
    input.nodes = leaf;
    input.node_count = sizeof(leaf) / sizeof(*leaf);
    reject(&input, EXR_ARGUMENT);
    leaf[2].kind = EXR_NODE_BREAK;
    reject(&input, EXR_ARGUMENT);
    leaf[2].kind = EXR_NODE_TEXT;
    leaf[2].text = "parent text";
    reject(&input, EXR_ARGUMENT);
  }
  {
    exr_node_input deep[260] = {{0}};
    deep[0].kind = EXR_NODE_DOCUMENT;
    deep[0].parent = SIZE_MAX;
    for (i = 1; i < sizeof(deep) / sizeof(*deep); i++) {
      deep[i].kind = i == 1 ? EXR_NODE_CHAPTER : EXR_NODE_ELEMENT;
      deep[i].parent = i - 1;
    }
    input.nodes = deep;
    input.node_count = sizeof(deep) / sizeof(*deep);
    reject(&input, EXR_LIMIT);
  }
  {
    exr_node_input reordered[] = {{EXR_NODE_DOCUMENT, SIZE_MAX, NULL, NULL, NULL, 0},
                                  {EXR_NODE_CHAPTER, 0, NULL, NULL, NULL, 0},
                                  {EXR_NODE_HEADING, 1, "host-heading", NULL, NULL, 0},
                                  {EXR_NODE_TEXT, 2, NULL, "First", NULL, 0},
                                  {EXR_NODE_CHAPTER, 0, NULL, NULL, NULL, 0},
                                  {EXR_NODE_PARAGRAPH, 4, NULL, NULL, NULL, 0},
                                  {EXR_NODE_TEXT, 5, NULL, "Second", NULL, 0}};
    exr_chapter_input order[] = {{"second", "second.unit", 4, 1}, {"first", "first.unit", 1, 1}};
    const exr_node *built;
    const exr_block *blocks;
    size_t count, resource, node;
    input.nodes = reordered;
    input.node_count = sizeof(reordered) / sizeof(*reordered);
    input.chapters = order;
    input.chapter_count = 2;
    input.resources = NULL;
    input.resource_count = 0;
    OK(exr_document_create(&input, &doc, &error));
    CHECK(!strcmp(exr_document_text(doc, NULL), "Second\nFirst"));
    built = exr_document_nodes(doc, NULL);
    CHECK(built[1].chapter == 1 && built[4].chapter == 0);
    blocks = exr_document_blocks(doc, &count);
    CHECK(count == 2 && blocks[1].heading == 1);
    OK(exr_document_resolve(doc, 0, "first.unit", &resource, &node, &error));
    CHECK(resource == SIZE_MAX && node == 1);
    exr_document_free(doc);
    order[1].root = 4;
    reject(&input, EXR_ARGUMENT);
    order[1].root = 1;
    order[1].path = order[0].path;
    reject(&input, EXR_ARGUMENT);
    order[1].path = "first.unit";
    order[1].id = order[0].id;
    reject(&input, EXR_ARGUMENT);
    input.chapter_count = 1;
    reject(&input, EXR_ARGUMENT);
  }
}

int main(int argc, char **argv) {
  const char *font_path = getenv("EXR_TEST_FONT");
  if (argc < 2 || argc > 3) {
    fprintf(stderr, "usage: test_construct fixtures [font]\n");
    return 2;
  }
  fixtures = argv[1];
  if (argc == 3)
    font_path = argv[2];
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
  integration();
  generic_names();
  validation();
  exr_font_free(font);
  printf("%u document construction checks passed\n", checks);
  return 0;
}
