/* SPDX-License-Identifier: MIT */
/* Compile as a console check or -shared bridge. Both call the production host
   startup helper; EXR_FONTHOST_CONFIG isolates discovery without changing fonts. */
#include <windows.h>
static const wchar_t *check_module;
static DWORD WINAPI check_module_filename(HMODULE module, LPWSTR path, DWORD capacity) {
  if (!check_module) return GetModuleFileNameW(module, path, capacity);
  size_t size = wcslen(check_module);
  if (size >= capacity) return 0;
  memcpy(path, check_module, (size + 1) * sizeof(*path));
  return (DWORD)size;
}
#define GetModuleFileNameW check_module_filename
#include "../reader.c"
#undef GetModuleFileNameW

__declspec(dllexport) exr_status host_check_font_open(const char *path, exr_font **out, exr_error *error) {
  const char *config = getenv("EXR_FONTHOST_CONFIG");
  wchar_t *wide = config ? host_wide(config, strlen(config)) : NULL;
  wchar_t *module = path ? host_wide(path, strlen(path)) : NULL;
  check_module = module;
  module_directory(g.data_dir, HOST_PATH);
  exr_status status = host_open_body_font(L"", wide ? wide : L"", error);
  free(wide); free(module); check_module = NULL;
  *out = g.font; g.font = NULL;
  exr_font_manager_free(g.font_manager); g.font_manager = NULL;
  return status;
}

int main(int argc, char **argv) {
  exr_error error = {0}; exr_font *font = NULL;
  if (argc != 3 && argc != 5) return 2;
  exr_status status = host_check_font_open(NULL, &font, &error);
  if (status != EXR_OK) { fprintf(stderr, "%s\n", error.message); return 3; }
  char *utf8 = host_utf8(g.font_path);
  exr_font_axis *axes = NULL; size_t count = 0;
  exr_font_axes(font, 0, &axes, &count, NULL);
  double weight = 0;
  for (size_t i = 0; i < count; i++) if (axes[i].tag == 0x77676874u) weight = axes[i].value;
  printf("%s\nfallback=%d;weight=%.0f;faces=%zu\n", utf8, g.font_fell_back, weight, exr_font_count(font));
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
  int passed = strstr(utf8, argv[1]) != NULL && g.font_fell_back == atoi(argv[2]);
  free(utf8); exr_free(axes); exr_font_free(font);
  return passed ? 0 : 4;
}
