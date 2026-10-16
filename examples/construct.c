/* SPDX-License-Identifier: GPL-3.0-only */
#include <exreader.h>
#include <stdio.h>

/* A host parser produces semantic nodes. Names and attributes can retain its own vocabulary. */
static int example_main(int argc, char **argv) {
  const char css[] =
      ".body {font-size:24px;line-height:1.5;color:#214565} emphasis {font-weight:bold}";
  const exr_attribute body[] = {{"class", "body"}, {"source-line", "12"}};
  const exr_node_input nodes[] = {
      {EXR_NODE_DOCUMENT, SIZE_MAX, NULL, NULL, NULL, 0},
      {EXR_NODE_CHAPTER, 0, NULL, NULL, NULL, 0},
      {EXR_NODE_ELEMENT, 1, "http://www.w3.org/1999/xhtml|link", NULL,
       (const exr_attribute[]){{"rel", "stylesheet"}, {"href", "theme.css"}}, 2},
      {EXR_NODE_HEADING, 1, NULL, NULL, NULL, 0},
      {EXR_NODE_TEXT, 3, NULL, "An open document model", NULL, 0},
      {EXR_NODE_PARAGRAPH, 1, "verse", NULL, body, 2},
      {EXR_NODE_TEXT, 5, NULL, "A host parser supplies ", NULL, 0},
      {EXR_NODE_ELEMENT, 5, "emphasis", NULL, NULL, 0},
      {EXR_NODE_TEXT, 7, NULL, "its own document structure", NULL, 0},
      {EXR_NODE_TEXT, 5, NULL, ". The C engine computes text positions, lines and pages.", NULL,
       0}};
  const exr_chapter_input chapter = {"chapter-one", "chapter.custom", 1, 1};
  const exr_resource_input resource = {
      {"theme", "theme.css", "text/css", NULL}, css, sizeof(css) - 1};
  const exr_document_input input = {
      "Host document", nodes, sizeof(nodes) / sizeof(*nodes), &chapter, 1, &resource, 1};
  exr_document *doc = NULL;
  exr_font *font = NULL;
  exr_layout *layout = NULL;
  exr_bitmap bitmap = {0};
  exr_error error = {0};
  exr_status status;
  if (argc != 3) {
    fprintf(stderr, "usage: exreader-construct-example font.ttf output.png\n");
    return 2;
  }
  status = exr_document_create(&input, &doc, &error);
  if (status == EXR_OK)
    status = exr_font_open(argv[1], &font, &error);
  if (status == EXR_OK)
    status = exr_layout_create(doc, font, NULL, &layout, &error);
  exr_document_free(doc);
  if (status == EXR_OK)
    status = exr_render_page_color(layout, font, 0, &bitmap, &error);
  if (status == EXR_OK)
    status = exr_bitmap_write_png(&bitmap, argv[2], &error);
  exr_bitmap_free(&bitmap);
  exr_layout_free(layout);
  exr_font_free(font);
  if (status != EXR_OK) {
    fprintf(stderr, "%s\n", error.message);
    return 1;
  }
  printf("EXReader C %s: constructed and rendered a host document\n", exr_version());
  return 0;
}
#include "entry.h"
