/* SPDX-License-Identifier: MIT */
#include <exr/font_manager.h>
#include <stdio.h>

int main(int argc, char **argv) {
  exr_font_location location = {0};
  exr_font_manager_options options = {0};
  exr_font_manager *manager = NULL;
  exr_font *font = NULL;
  exr_error error = {0};
  exr_status status;
  size_t count = 0;
  if (argc != 2) { fprintf(stderr, "usage: font font-directory\n"); return 2; }
  location.path = argv[1];
  location.kind = EXR_FONT_LOCATION_DIRECTORY;
  options.struct_size = sizeof(options);
  options.locations = &location;
  options.location_count = 1;
  status = exr_font_manager_create(&options, &manager, &error);
  if (status == EXR_OK)
    status = exr_font_manager_create_font(manager, NULL, EXR_FONT_STYLE_REGULAR,
                                          &font, NULL, &count, &error);
  if (status == EXR_OK) printf("fallback faces=%zu\n", count);
  else fprintf(stderr, "%s\n", error.message);
  exr_font_free(font);
  exr_font_manager_free(manager);
  return status == EXR_OK ? 0 : 1;
}
