/* SPDX-License-Identifier: MIT */
#include <exr/core.h>
#include <stdio.h>
#include <string.h>

#define SDK_FUNCTIONS(X) \
  X(const char *, exr_version, (void)) \
  X(uint32_t, exr_abi_version, (void)) \
  X(exr_status, exr_publication_open, (const char *, exr_publication **, exr_error *)) \
  X(const char *, exr_publication_title, (const exr_publication *)) \
  X(const exr_part *, exr_publication_parts, (const exr_publication *, size_t *)) \
  X(exr_status, exr_publication_load, (exr_publication *, size_t, exr_document **, exr_error *)) \
  X(void, exr_publication_free, (exr_publication *)) \
  X(void, exr_document_free, (exr_document *)) \
  X(exr_status, exr_font_open, (const char *, exr_font **, exr_error *)) \
  X(void, exr_font_free, (exr_font *)) \
  X(exr_status, exr_layout_create, (const exr_document *, exr_font *, const exr_layout_options *, exr_layout **, exr_error *)) \
  X(const exr_page *, exr_layout_pages, (const exr_layout *, size_t *)) \
  X(exr_font *, exr_layout_font, (const exr_layout *)) \
  X(void, exr_layout_free, (exr_layout *)) \
  X(exr_status, exr_render_page_color, (const exr_layout *, exr_font *, size_t, exr_bitmap *, exr_error *)) \
  X(exr_status, exr_bitmap_write_png, (const exr_bitmap *, const char *, exr_error *)) \
  X(void, exr_bitmap_free, (exr_bitmap *))

#ifdef CONSUMER_RUNTIME
#include "abi_symbols.h"
#ifdef _WIN32
#include <windows.h>
typedef HMODULE library_handle;
typedef FARPROC symbol_address;
static library_handle open_library(const char *path) { return LoadLibraryA(path); }
static symbol_address lookup(library_handle lib, const char *name) { return GetProcAddress(lib, name); }
static void close_library(library_handle lib) { FreeLibrary(lib); }
#else
#include <dlfcn.h>
typedef void *library_handle;
typedef void *symbol_address;
static library_handle open_library(const char *path) { return dlopen(path, RTLD_NOW | RTLD_LOCAL); }
static symbol_address lookup(library_handle lib, const char *name) { return dlsym(lib, name); }
static void close_library(library_handle lib) { dlclose(lib); }
#endif
#define DECLARE(result, name, arguments) static result (*sdk_##name) arguments;
#else
#define DECLARE(result, name, arguments) static result (*const sdk_##name) arguments = name;
#endif
SDK_FUNCTIONS(DECLARE)
#undef DECLARE

static int check_version(void) {
  unsigned header[3], library[3];
  char trailing;
  const char *version = sdk_exr_version();
  uint32_t abi = sdk_exr_abi_version();
  if (!version || sscanf(EXR_SDK_VERSION, "%u.%u.%u%c", &header[0], &header[1], &header[2], &trailing) != 3 ||
      sscanf(version, "%u.%u.%u%c", &library[0], &library[1], &library[2], &trailing) != 3) {
    fprintf(stderr, "SDK_VERSION_INVALID: header=%s library=%s\n", EXR_SDK_VERSION, version ? version : "(null)");
    return 0;
  }
  if (abi != EXR_ABI_VERSION) {
    fprintf(stderr, "SDK_ABI_MISMATCH: header=%u library=%u\n", (unsigned)EXR_ABI_VERSION, (unsigned)abi);
    return 0;
  }
  for (size_t i = 0; i < 3; ++i) {
    if (header[i] < library[i]) break;
    if (header[i] > library[i]) {
      fprintf(stderr, "SDK_VERSION_MISMATCH: header=%s library=%s; headers require a newer SDK library\n", EXR_SDK_VERSION, version);
      return 0;
    }
  }
  printf("PASS version header=%s library=%s abi=%u\n", EXR_SDK_VERSION, version, (unsigned)abi);
  return 1;
}

int main(int argc, char **argv) {
  exr_publication *publication = NULL;
  exr_document *document = NULL;
  exr_font *font = NULL;
  exr_layout *layout = NULL;
  exr_bitmap bitmap = {0};
  exr_error error = {0};
  const exr_layout_options options = {360, 480, 24, 18, 1.5f, 8};
  size_t parts = 0, total_pages = 0;
  int exit_code = 1;
#ifdef CONSUMER_RUNTIME
  library_handle lib;
  if (argc != 5) { fprintf(stderr, "usage: consumer book font output.png absolute-library-path\n"); return 2; }
  lib = open_library(argv[4]);
  if (!lib) { fprintf(stderr, "SDK_LOAD_FAILED: %s\n", argv[4]); return 3; }
#define BIND(result, name, arguments) do { \
    symbol_address address = lookup(lib, #name); \
    _Static_assert(sizeof(address) == sizeof(sdk_##name), "loader function pointer size"); \
    if (!address) { fprintf(stderr, "SDK_SYMBOL_MISSING: %s\n", #name); close_library(lib); return 3; } \
    memcpy(&sdk_##name, &address, sizeof(address)); \
  } while (0);
  SDK_FUNCTIONS(BIND)
#undef BIND
#else
  if (argc != 4) { fprintf(stderr, "usage: consumer book font output.png\n"); return 2; }
#endif
  if (!check_version()) {
#ifdef CONSUMER_RUNTIME
    close_library(lib);
#endif
    return 4;
  }
#ifdef CONSUMER_RUNTIME
  for (size_t i = 0; i < sizeof(abi_symbols) / sizeof(abi_symbols[0]); ++i) {
    if (!lookup(lib, abi_symbols[i])) {
      fprintf(stderr, "SDK_SYMBOL_MISSING: %s\n", abi_symbols[i]);
      exit_code = 3;
      goto done;
    }
  }
  printf("PASS runtime symbols=%zu\n", sizeof(abi_symbols) / sizeof(abi_symbols[0]));
#endif
#define REQUIRE(condition, detail) do { if (!(condition)) { fprintf(stderr, "SDK_CONSUMER_FAILED: %s status=%d %s\n", detail, (int)error.code, error.message); goto done; } } while (0)
#define OK(call) REQUIRE((call) == EXR_OK, #call)
  OK(sdk_exr_publication_open(argv[1], &publication, &error));
  REQUIRE(sdk_exr_publication_title(publication) && *sdk_exr_publication_title(publication), "book title is empty");
  REQUIRE(sdk_exr_publication_parts(publication, &parts) && parts, "book has no parts");
  OK(sdk_exr_font_open(argv[2], &font, &error));
  for (size_t part = 0; part < parts; ++part) {
    size_t pages = 0;
    OK(sdk_exr_publication_load(publication, part, &document, &error));
    OK(sdk_exr_layout_create(document, font, &options, &layout, &error));
    REQUIRE(sdk_exr_layout_pages(layout, &pages) && pages, "part has no pages");
    total_pages += pages;
    if (part == 0) {
      size_t ink = 0;
      OK(sdk_exr_render_page_color(layout, sdk_exr_layout_font(layout), 0, &bitmap, &error));
      REQUIRE(bitmap.pixels && bitmap.channels == 4 && bitmap.width && bitmap.height, "rendered bitmap is empty");
      for (uint32_t y = 0; y < bitmap.height; ++y)
        for (uint32_t x = 0; x < bitmap.width; ++x) {
          const unsigned char *pixel = bitmap.pixels + (size_t)y * bitmap.stride + (size_t)x * 4;
          if (pixel[0] < 240 || pixel[1] < 240 || pixel[2] < 240) ++ink;
        }
      REQUIRE(ink, "rendered page contains no ink");
      OK(sdk_exr_bitmap_write_png(&bitmap, argv[3], &error));
      sdk_exr_bitmap_free(&bitmap);
    }
    sdk_exr_layout_free(layout); layout = NULL;
    sdk_exr_document_free(document); document = NULL;
  }
  printf("PASS mode=%s title=\"%s\" pages=%zu render=%s\n", CONSUMER_MODE,
         sdk_exr_publication_title(publication), total_pages, argv[3]);
  exit_code = 0;
done:
  sdk_exr_bitmap_free(&bitmap);
  sdk_exr_layout_free(layout);
  sdk_exr_font_free(font);
  sdk_exr_document_free(document);
  sdk_exr_publication_free(publication);
#ifdef CONSUMER_RUNTIME
  close_library(lib);
#endif
  return exit_code;
}
