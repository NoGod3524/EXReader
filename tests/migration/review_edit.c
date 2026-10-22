/* SPDX-License-Identifier: MIT */
#include <exreader.h>
#include <string.h>
/* Modify a synthetic library using the same public API available to a host. */
int main(int argc, char **argv) {
  exr_library *library = NULL;
  exr_error error = {0};
  exr_book *books = NULL;
  size_t count = 0, i;
  int result = 1;
  if (argc != 3 || exr_library_open(argv[1], &library, &error) != EXR_OK) return 2;
  if (exr_library_books(library, "", &books, &count, &error) != EXR_OK) goto done;
  for (i = 0; i < count && result; i++) {
    if (!strcmp(argv[2], "reflow-text") && books[i].format == EXR_TXT) {
      exr_note *notes = NULL;
      size_t n = 0;
      if (exr_library_notes(library, books[i].id, &notes, &n, &error) == EXR_OK && n)
        result = exr_library_note_text(library, notes[0].id, "edited after migration", &error) != EXR_OK;
      exr_notes_free(notes, n);
    } else if ((!strcmp(argv[2], "fixed-range") || !strcmp(argv[2], "fixed-text")) && books[i].format == EXR_PDF) {
      exr_fixed_note *notes = NULL;
      size_t n = 0;
      if (exr_library_fixed_notes(library, books[i].id, &notes, &n, &error) == EXR_OK && n) {
        exr_fixed_note changed = notes[0];
        int64_t id = changed.id;
        if (!strcmp(argv[2], "fixed-range")) changed.start = changed.end = 0;
        else changed.text = "edited after migration";
        result = exr_library_fixed_note(library, &changed, NULL, &id, &error) != EXR_OK;
      }
      exr_fixed_notes_free(notes, n);
    }
  }
done:
  exr_books_free(books, count);
  exr_library_close(library);
  return result;
}
