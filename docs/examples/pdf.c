/* SPDX-License-Identifier: MIT */
#include <exr/pdf.h>
#include <stdio.h>

int main(int argc, char **argv) {
  exr_fixed_document *document = NULL;
  exr_bitmap bitmap = {0};
  exr_error error = {0};
  exr_status status;
  if (argc != 3) { fprintf(stderr, "usage: pdf input.pdf output.png\n"); return 2; }
  status = exr_fixed_open(argv[1], NULL, &document, &error);
  if (status == EXR_OK)
    status = exr_fixed_render(document, 0, 96.0 / 72.0, NULL, &bitmap, &error);
  if (status == EXR_OK) status = exr_bitmap_write_png(&bitmap, argv[2], &error);
  if (status != EXR_OK) fprintf(stderr, "%s\n", error.message);
  exr_bitmap_free(&bitmap);
  exr_fixed_free(document);
  return status == EXR_OK ? 0 : 1;
}
