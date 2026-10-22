/* SPDX-License-Identifier: MIT */
/* CI-only fixture through the unchanged public memory-import API. */
#include <exreader.h>
#include <stdio.h>
#include <stdlib.h>
int main(int argc, char **argv) {
  FILE *input; long length; void *bytes; exr_library *library = NULL;
  exr_library_epub_info info = {sizeof(info), 0, 0}; exr_error error = {0};
  exr_status status; int64_t id = 0;
  if (argc != 3 || !(input = fopen(argv[2], "rb"))) return 2;
  if (fseek(input, 0, SEEK_END) || (length = ftell(input)) <= 0 || fseek(input, 0, SEEK_SET)) return 3;
  bytes = malloc((size_t)length);
  if (!bytes || fread(bytes, 1, (size_t)length, input) != (size_t)length || fclose(input)) return 4;
  status = exr_library_open(argv[1], &library, &error);
  if (status == EXR_OK) status = exr_library_import(library, EXR_EPUB, bytes, (size_t)length, "Legacy memory import", &id, &error);
  if (status == EXR_OK) status = exr_library_epub_info_get(library, id, &info, &error);
  exr_library_close(library); free(bytes);
  if (status != EXR_OK || info.bounded_storage || !info.global_extent_known) return 5;
  printf("public memory import remains legacy: id=%lld\n", (long long)id); return 0;
}
