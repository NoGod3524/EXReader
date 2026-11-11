/* SPDX-License-Identifier: MIT */
#include <exr/graphics.h>
#include <stdio.h>

int main(void) {
  exr_canvas_config config = {0};
  exr_canvas *canvas = NULL;
  exr_bitmap bitmap = {0};
  exr_error error = {0};
  config.width = 32;
  config.height = 32;
  config.channels = 4;
  config.background = 0x336699FFu;
  exr_status status = exr_canvas_create(&config, &canvas, &error);
  if (status == EXR_OK) status = exr_canvas_take(canvas, &bitmap, &error);
  if (status == EXR_OK) printf("canvas transferred: %u x %u\n", bitmap.width, bitmap.height);
  else fprintf(stderr, "%s\n", error.message);
  exr_bitmap_free(&bitmap);
  exr_canvas_free(canvas);
  return status == EXR_OK ? 0 : 1;
}
