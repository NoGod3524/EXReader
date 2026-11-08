/* SPDX-License-Identifier: MIT */
/* Exercise the actual host lookup with a private Windows font directory.
   Build like reader.c, linking the same shell objects; place the executable in
   a disposable directory. No installed font is renamed or removed. */
#include <windows.h>
static UINT WINAPI test_windows_directory(LPWSTR path, UINT capacity) {
  return GetEnvironmentVariableW(L"EXR_TEST_WINDOWS", path, capacity);
}
#define GetWindowsDirectoryW test_windows_directory
#include "../reader.c"
#undef GetWindowsDirectoryW

int main(int argc, char **argv) {
  wchar_t chosen[HOST_PATH], sans[HOST_PATH], dir[HOST_PATH];
  exr_error error = {0}; exr_font *font = NULL; int fallback = 0;
  if (argc != 3 && argc != 5) return 2;
  module_directory(dir, HOST_PATH);
  path_join(sans, HOST_PATH, dir, L"Reader.otf");
  copy_wstring(g.data_dir, HOST_PATH, dir);
  exr_status status = host_open_body_font(sans, &font, chosen, HOST_PATH, &fallback, &error);
  if (status != EXR_OK) { fprintf(stderr, "%s\n", error.message); return 3; }
  host_log_body_font(chosen, fallback);
  char *utf8 = host_utf8(chosen);
  exr_font_axis *axes = NULL; size_t count = 0;
  exr_font_axes(font, 0, &axes, &count, NULL);
  double weight = 0;
  for (size_t i = 0; i < count; i++) if (axes[i].tag == 0x77676874u) weight = axes[i].value;
  printf("%s\nfallback=%d;weight=%.0f;faces=%zu\n", utf8, fallback, weight, exr_font_count(font));
  if (argc == 5) {
    char text[4096]; FILE *input = fopen(argv[4], "rb");
    if (!input) return 5;
    size_t bytes = fread(text, 1, sizeof(text), input); fclose(input);
    exr_shape_options options = exr_shape_defaults();
    exr_shaped_glyph *glyphs = NULL; size_t glyph_count = 0;
    options.font_size = (float)atof(argv[3]);
    if (exr_shape(font, 0, text, bytes, &options, &glyphs, &glyph_count, &error) != EXR_OK) return 5;
    for (size_t i = 0; i < glyph_count; i++)
      printf("glyph=%zu,%zu,%.6f\n", glyphs[i].start, glyphs[i].end, (double)glyphs[i].advance_x);
    exr_free(glyphs);
  }
  int passed = strstr(utf8, argv[1]) != NULL && fallback == atoi(argv[2]);
  free(utf8); exr_free(axes); exr_font_free(font);
  return passed ? 0 : 4;
}
