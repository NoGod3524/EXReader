#include "font_internal.h"
#include <stddef.h>
#include <stdio.h>
int main(void) {
  printf("exr_font sizeof=%zu alignof=%zu raster_cache=%zu manager_required=%zu\n",
    sizeof(exr_font),(size_t)_Alignof(exr_font),offsetof(exr_font,raster_cache),offsetof(exr_font,manager_required));
  return 0;
}
