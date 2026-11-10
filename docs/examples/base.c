/* SPDX-License-Identifier: MIT */
#include <exr/base.h>
#include <stdio.h>

int main(void) {
  exr_page_geometry page = {{0, 0, 612, 792}, 1, 0, 0};
  exr_viewport viewport = {0};
  exr_error error = {0};
  exr_status status = exr_viewport_create(&page, 96.0 / 72.0, &viewport, &error);
  if (status == EXR_OK)
    printf("SDK %s, ABI %u: %.0f x %.0f pixels\n", exr_version(),
           (unsigned)exr_abi_version(), viewport.width, viewport.height);
  else
    fprintf(stderr, "%s\n", error.message);
  return status == EXR_OK ? 0 : 1;
}
