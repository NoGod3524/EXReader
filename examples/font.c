/* SPDX-License-Identifier: MIT */
#include <exreader.h>
#include <stdio.h>
#include <stdlib.h>
#ifdef _WIN32
#include <windows.h>
#endif

static FILE *open_utf8(const char *path) {
#ifdef _WIN32
  FILE *file;
  int n = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1, NULL, 0);
  wchar_t *wide = n ? malloc((size_t)n * sizeof(*wide)) : NULL;
  if (!wide)
    return NULL;
  if (!MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1, wide, n)) {
    free(wide);
    return NULL;
  }
  file = _wfopen(wide, L"rb");
  free(wide);
  return file;
#else
  return fopen(path, "rb");
#endif
}
static int read_font(const char *path, exr_font_input *input) {
  FILE *file = open_utf8(path);
  long size;
  if (!file)
    return 0;
  if (fseek(file, 0, SEEK_END) || (size = ftell(file)) <= 0 ||
      size > 128 * 1024 * 1024 || fseek(file, 0, SEEK_SET)) {
    fclose(file);
    return 0;
  }
  input->size = (size_t)size;
  input->data = malloc(input->size);
  if (!input->data || fread((void *)input->data, 1, input->size, file) != input->size) {
    fclose(file);
    return 0;
  }
  return fclose(file) == 0;
}
static int example_main(int argc, char **argv) {
  const char text[] = "A\xe7\x94\xb2 a\xcc\x81";
  exr_font_input inputs[2] = {{0}, {0}};
  exr_font *font = NULL;
  exr_document *doc = NULL;
  exr_layout *layout = NULL;
  exr_bitmap bitmap = {0};
  exr_error error = {0};
  exr_status status;
  size_t i, count;
  if (argc != 4) {
    fprintf(stderr, "usage: exreader-font-example primary.ttf fallback.ttf output.png\n");
    return 2;
  }
  if (!read_font(argv[1], &inputs[0]) || !read_font(argv[2], &inputs[1])) {
    fprintf(stderr, "Could not read supplied font bytes\n");
    free((void *)inputs[0].data); free((void *)inputs[1].data);
    return 1;
  }
  status = exr_font_create(inputs, 2, &font, &error);
  free((void *)inputs[0].data); free((void *)inputs[1].data);
  if (status == EXR_OK)
    status = exr_document_open_memory(EXR_TXT, text, sizeof(text)-1, &doc, &error);
  if (status == EXR_OK)
    status = exr_layout_create(doc, font, NULL, &layout, &error);
  if (status == EXR_OK) {
    const exr_glyph *glyphs = exr_layout_glyphs(layout, &count);
    for (i = 0; i < count; i++)
      printf("U+%04X: font %zu, glyph %u%s\n", (unsigned)glyphs[i].codepoint,
             glyphs[i].font_index, (unsigned)glyphs[i].glyph,
             glyphs[i].flags & EXR_GLYPH_MISSING ? " (missing)" : "");
    status = exr_render_page_color(layout, font, 0, &bitmap, &error);
  }
  if (status == EXR_OK)
    status = exr_bitmap_write_png(&bitmap, argv[3], &error);
  if (status != EXR_OK)
    fprintf(stderr, "%s\n", error.message);
  exr_bitmap_free(&bitmap); exr_layout_free(layout);
  exr_document_free(doc); exr_font_free(font);
  return status == EXR_OK ? 0 : 1;
}
#include "entry.h"
