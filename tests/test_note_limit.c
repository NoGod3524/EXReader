/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define NOTE_LIMIT ((size_t)64 * 1024 * 1024)
static exr_error error;
static unsigned checks;
#define CHECK(x)                                                                                   \
  do {                                                                                             \
    checks++;                                                                                      \
    if (!(x)) {                                                                                    \
      fprintf(stderr, "line %d: %s (%d: %s)\n", __LINE__, #x, (int)error.code, error.message);     \
      exit(1);                                                                                     \
    }                                                                                              \
  } while (0)
#define OK(x) CHECK((x) == EXR_OK)

static exr_note *read_notes(exr_library *library, int64_t book, size_t expected) {
  exr_note *notes = NULL;
  size_t count = SIZE_MAX;
  OK(exr_library_notes(library, book, &notes, &count, &error));
  CHECK(count == expected);
  return notes;
}

static int64_t import_book(exr_library *library) {
  int64_t book = 0;
  OK(exr_library_import(library, EXR_TXT, "target", 6, "Note limit", &book, &error));
  CHECK(book > 0);
  return book;
}

static void aliased_id(void) {
  exr_library *library = NULL;
  exr_note input = {0}, *notes;
  int64_t original;
  OK(exr_library_open(":memory:", &library, &error));
  input.book_id = import_book(library);
  input.end = 6;
  input.text = "original";
  OK(exr_library_note(library, &input, &input.id, &error));
  original = input.id;
  CHECK(original > 0);
  input.text = "edited";
  OK(exr_library_note(library, &input, &input.id, &error));
  CHECK(input.id == original);
  notes = read_notes(library, input.book_id, 1);
  CHECK(notes[0].id == original && !strcmp(notes[0].text, "edited"));
  CHECK(notes[0].anchor.exact && !strcmp(notes[0].anchor.exact, "target"));
  exr_notes_free(notes, 1);
  input.text = "edited again";
  OK(exr_library_note(library, &input, &input.id, &error));
  CHECK(input.id == original);
  notes = read_notes(library, input.book_id, 1);
  CHECK(notes[0].id == original && !strcmp(notes[0].text, "edited again"));
  exr_notes_free(notes, 1);
  exr_library_close(library);
}

static void rejected_writes(exr_library *library, int64_t book, int64_t existing, char *large) {
  exr_note input = {0}, *notes;
  int64_t id = -1;
  large[NOTE_LIMIT] = 'x';
  large[NOTE_LIMIT + 1] = 0;
  input.book_id = book;
  input.start = 0;
  input.end = 6;
  input.text = large;
  CHECK(exr_library_note(library, &input, &id, &error) == EXR_LIMIT);
  CHECK(id == 0 && error.code == EXR_LIMIT);
  input.id = existing;
  id = -1;
  CHECK(exr_library_note(library, &input, &id, &error) == EXR_LIMIT);
  CHECK(id == 0 && error.code == EXR_LIMIT);
  notes = read_notes(library, book, 1);
  CHECK(notes[0].id == existing && !strcmp(notes[0].text, "small"));
  CHECK(notes[0].start == 0 && notes[0].end == 6);
  CHECK(notes[0].anchor.exact && !strcmp(notes[0].anchor.exact, "target"));
  exr_notes_free(notes, 1);
}

static void exact_boundary(char *large) {
  exr_library *library = NULL;
  exr_note input = {0}, *notes;
  int64_t book, id, existing;
  OK(exr_library_open(":memory:", &library, &error));
  book = import_book(library);
  large[NOTE_LIMIT] = 0;
  input.book_id = book;
  input.end = 6;
  input.text = large;
  OK(exr_library_note(library, &input, &existing, &error));
  CHECK(existing > 0);
  notes = read_notes(library, book, 1);
  CHECK(strlen(notes[0].text) == NOTE_LIMIT && !memcmp(notes[0].text, large, NOTE_LIMIT));
  exr_notes_free(notes, 1);
  input.id = existing;
  input.text = "small";
  OK(exr_library_note(library, &input, &id, &error));
  CHECK(id == existing);
  rejected_writes(library, book, existing, large);
  /* An update at the exact boundary must remain readable and editable too. */
  large[NOTE_LIMIT] = 0;
  input.text = large;
  OK(exr_library_note(library, &input, &id, &error));
  CHECK(id == existing);
  notes = read_notes(library, book, 1);
  CHECK(strlen(notes[0].text) == NOTE_LIMIT && !memcmp(notes[0].text, large, NOTE_LIMIT));
  exr_notes_free(notes, 1);
  input.text = "small";
  OK(exr_library_note(library, &input, &id, &error));
  input.id = 0;
  input.text = "second";
  OK(exr_library_note(library, &input, &id, &error));
  CHECK(id > 0 && id != existing);
  notes = read_notes(library, book, 2);
  CHECK(!strcmp(notes[0].text, "small") && !strcmp(notes[1].text, "second"));
  exr_notes_free(notes, 2);
  exr_library_close(library);
}

static void persistent_reopen(const char *directory, char *large) {
  char path[4096];
  exr_library *library = NULL;
  exr_note input = {0}, *notes;
  int64_t book, id, existing;
  CHECK(snprintf(path, sizeof(path), "%s/note-limit.sqlite", directory) > 0);
  remove(path);
  OK(exr_library_open(path, &library, &error));
  book = import_book(library);
  input.book_id = book;
  input.end = 6;
  input.text = "small";
  OK(exr_library_note(library, &input, &existing, &error));
  rejected_writes(library, book, existing, large);
  exr_library_close(library);
  library = NULL;
  OK(exr_library_open(path, &library, &error));
  notes = read_notes(library, book, 1);
  CHECK(notes[0].id == existing && !strcmp(notes[0].text, "small"));
  exr_notes_free(notes, 1);
  input.id = existing;
  input.text = "after reopen";
  OK(exr_library_note(library, &input, &id, &error));
  CHECK(id == existing);
  input.id = 0;
  input.text = "normal insert";
  OK(exr_library_note(library, &input, &id, &error));
  CHECK(id > 0 && id != existing);
  notes = read_notes(library, book, 2);
  CHECK(!strcmp(notes[0].text, "after reopen") && !strcmp(notes[1].text, "normal insert"));
  exr_notes_free(notes, 2);
  exr_library_close(library);
  CHECK(remove(path) == 0);
}

int main(int argc, char **argv) {
  char *large;
  CHECK(argc == 2);
  large = malloc(NOTE_LIMIT + 2);
  CHECK(large);
  memset(large, 'x', NOTE_LIMIT + 1);
  large[NOTE_LIMIT + 1] = 0;
  aliased_id();
  exact_boundary(large);
  persistent_reopen(argv[1], large);
  free(large);
  printf("%u annotation text limit checks passed\n", checks);
  return 0;
}
