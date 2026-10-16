/* SPDX-License-Identifier: GPL-3.0-only */
#include <exreader.h>
#include <stdio.h>
#include <stdlib.h>

static const exr_part parts[] = {{"one", "parts/one.unit", "First part", 1},
                                 {"two", "parts/two.unit", "Second part", 1},
                                 {"three", "parts/three.unit", "Third part", 1}};
static exr_status load(void *context, size_t part, exr_document **out, exr_error *error) {
  static const char *texts[] = {"This first part is not loaded by the default example.",
                                "A host-defined part, loaded only when requested. The C engine "
                                "builds its document tree and lays out this part independently.",
                                "This third part is not loaded by the default example."};
  exr_node_input nodes[] = {{EXR_NODE_DOCUMENT, SIZE_MAX, NULL, NULL, NULL, 0},
                             {EXR_NODE_CHAPTER, 0, NULL, NULL, NULL, 0},
                             {EXR_NODE_PARAGRAPH, 1, NULL, NULL, NULL, 0},
                             {EXR_NODE_TEXT, 2, NULL, texts[part], NULL, 0}};
  exr_chapter_input chapter = {parts[part].id, parts[part].path, 1, 1};
  exr_document_input input = {parts[part].title, nodes, 4, &chapter, 1, NULL, 0};
  (*(size_t *)context)++;
  return exr_document_create(&input, out, error);
}
static int example_main(int argc, char **argv) {
  exr_publication *publication = NULL;
  exr_session *session = NULL;
  exr_font *font = NULL;
  const exr_document *doc;
  const exr_layout *layout;
  exr_bitmap bitmap = {0};
  exr_error error = {0};
  exr_status status;
  size_t loaded = 0, count, part = 1;
  if (argc != 3 && argc != 5) {
    fprintf(stderr, "usage: exreader-lazy-example font.ttf output.png [book.epub part-index]\n");
    return 2;
  }
  if (argc == 5) {
    char *end;
    unsigned long value = strtoul(argv[4], &end, 10);
    if (end == argv[4] || *end || argv[4][0] == '-' || value > 9999)
      return 2;
    part = (size_t)value;
    status = exr_publication_open(argv[3], &publication, &error);
  } else {
    exr_publication_input input = {"Host lazy example", parts, 3, load, &loaded, NULL};
    status = exr_publication_create(&input, &publication, &error);
  }
  if (status == EXR_OK)
    status = exr_font_open(argv[1], &font, &error);
  if (status == EXR_OK)
    status = exr_session_create(publication, font, NULL, 1, &session, &error);
  exr_publication_parts(publication, &count);
  exr_publication_free(publication);
  if (status == EXR_OK)
    status = exr_session_get(session, part, &doc, &layout, &error);
  if (status == EXR_OK)
    status = exr_render_page_color(layout, font, 0, &bitmap, &error);
  if (status == EXR_OK)
    status = exr_bitmap_write_png(&bitmap, argv[2], &error);
  if (status == EXR_OK)
    printf("EXReader C %s: requested part %zu of %zu; %zu resident%s\n", exr_version(),
           part, count, exr_session_cached(session), argc == 3 && loaded == 1 ? "; one loader call" : "");
  else
    fprintf(stderr, "%s\n", error.message);
  exr_bitmap_free(&bitmap);
  exr_session_free(session);
  exr_font_free(font);
  return status == EXR_OK ? 0 : 1;
}
#include "entry.h"
