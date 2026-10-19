/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
static int render_main(int argc, char **argv) {
  exr_document *doc = NULL;
  exr_font *font = NULL;
  exr_layout *layout = NULL;
  exr_bitmap bitmap = {0};
  exr_error error = {0};
  size_t pages = 0, bytes = 0, page = 0;
  exr_layout_options options = exr_layout_defaults();
  clock_t start = clock();
  int result = 1;
  if (argc < 4) {
    fprintf(stderr,
            "EXReader C %s\nUsage: exreader-render book font.ttf output.png "
            "[page] [width] [height]\n",
            exr_version());
    return 2;
  }
  if (argc > 4)
    page = (size_t)strtoull(argv[4], NULL, 10);
  if (argc > 5)
    options.width = strtof(argv[5], NULL);
  if (argc > 6)
    options.height = strtof(argv[6], NULL);
  if (exr_document_open(argv[1], &doc, &error) != EXR_OK ||
      exr_font_open(argv[2], &font, &error) != EXR_OK ||
      exr_layout_create(doc, font, &options, &layout, &error) != EXR_OK)
    goto done;
  exr_document_text(doc, &bytes);
  exr_layout_pages(layout, &pages);
  if (exr_render_page_color(layout, font, page, &bitmap, &error) != EXR_OK ||
      (strstr(argv[3], ".png") ? exr_bitmap_write_png(&bitmap, argv[3], &error)
                               : exr_bitmap_write_bmp(&bitmap, argv[3], &error)) != EXR_OK)
    goto done;
  printf("EXReader C %s: %zu UTF-8 bytes, %zu pages, rendered page %zu, %.3f "
         "CPU seconds\n",
         exr_version(), bytes, pages, page, (double)(clock() - start) / CLOCKS_PER_SEC);
  result = 0;
done:
  if (result)
    fprintf(stderr, "Error %d: %s\n", (int)error.code, error.message);
  exr_bitmap_free(&bitmap);
  exr_layout_free(layout);
  exr_font_free(font);
  exr_document_free(doc);
  return result;
}

#ifdef _WIN32
#include <windows.h>
#include <shellapi.h>
int main(void) {
  int argc = 0, i, result = 2;
  wchar_t **wide = CommandLineToArgvW(GetCommandLineW(), &argc);
  char **argv;
  if (!wide)
    return 2;
  argv = calloc((size_t)argc + 1, sizeof(*argv));
  if (!argv) {
    LocalFree(wide);
    return 2;
  }
  for (i = 0; i < argc; i++) {
    int n = WideCharToMultiByte(CP_UTF8, 0, wide[i], -1, NULL, 0, NULL, NULL);
    if (!n || !(argv[i] = malloc((size_t)n)))
      goto done;
    if (!WideCharToMultiByte(CP_UTF8, 0, wide[i], -1, argv[i], n, NULL, NULL))
      goto done;
  }
  result = render_main(argc, argv);
done:
  for (i = 0; i < argc; i++)
    free(argv[i]);
  free(argv);
  LocalFree(wide);
  return result;
}
#else
int main(int argc, char **argv) { return render_main(argc, argv); }
#endif
