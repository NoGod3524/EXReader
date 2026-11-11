/* SPDX-License-Identifier: MIT */
#include <exr/formats.h>
#include <exr/render.h>
#include <stdio.h>

int main(int argc, char **argv) {
  const char text[] = "Hello from EXReader.";
  exr_document *document = NULL;
  exr_font *font = NULL;
  exr_layout *layout = NULL;
  exr_bitmap bitmap = {0};
  exr_error error = {0};
  exr_status status;
  if (argc != 3) { fprintf(stderr, "usage: render font.ttf output.png\n"); return 2; }
  status = exr_document_open_memory(EXR_TXT, text, sizeof(text) - 1, &document, &error);
  if (status == EXR_OK) status = exr_font_open(argv[1], &font, &error);
  if (status == EXR_OK) status = exr_layout_create(document, font, NULL, &layout, &error);
  if (status == EXR_OK)
    status = exr_render_page_background(layout, font, 0, 4, 0xF5EEDCFFu, NULL,
                                        &bitmap, &error);
  if (status == EXR_OK) {
    printf("RGBA %u x %u, stride=%u bytes\n", bitmap.width, bitmap.height, bitmap.stride);
    status = exr_bitmap_write_png(&bitmap, argv[2], &error);
  }
  if (status != EXR_OK) fprintf(stderr, "%s\n", error.message);
  exr_bitmap_free(&bitmap);
  exr_layout_free(layout);
  exr_font_free(font);
  exr_document_free(document);
  return status == EXR_OK ? 0 : 1;
}
