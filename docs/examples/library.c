/* SPDX-License-Identifier: MIT */
#include <exr/library.h>
#include <stdio.h>

int main(void) {
  const char text[] = "A stored book.";
  exr_library *library = NULL;
  exr_book *books = NULL;
  size_t count = 0;
  int64_t id = 0;
  exr_error error = {0};
  exr_status status = exr_library_open(":memory:", &library, &error);
  if (status == EXR_OK)
    status = exr_library_import(library, EXR_TXT, text, sizeof(text) - 1, "Example", &id, &error);
  if (status == EXR_OK) status = exr_library_books(library, NULL, &books, &count, &error);
  if (status == EXR_OK) printf("stored books=%zu\n", count);
  else fprintf(stderr, "%s\n", error.message);
  exr_books_free(books, count);
  exr_library_close(library);
  return status == EXR_OK ? 0 : 1;
}
