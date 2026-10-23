/* SPDX-License-Identifier: MIT */
#include <exr_sideload.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#endif

static exr_error error;
static unsigned checks, cases;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr, "line %d: %s (%d: %s)\n", __LINE__, #x, (int)error.code, error.message); exit(1); } } while (0)
#define OK(x) CHECK((x) == EXR_OK)

typedef struct {
  const unsigned char *bytes;
  size_t size, calls, short_read;
  int releases, cancelled, copy_started, cancel_copy, fail_copy, fail_read;
} memory_source;

static size_t memory_read(void *context, uint64_t offset, void *buffer, size_t size) {
  memory_source *memory = context;
  size_t got = size;
  memory->calls++;
  if (memory->fail_read) return 0;
  if (offset > memory->size || size > memory->size - (size_t)offset) return 0;
  if (offset == 0 && size == 65536 && memory->size > 65536) memory->copy_started = 1;
  if (memory->fail_copy && memory->copy_started && offset >= 65536) return 0;
  if (memory->short_read && got > memory->short_read) got = memory->short_read;
  memcpy(buffer, memory->bytes + (size_t)offset, got);
  if (memory->cancel_copy && memory->copy_started && offset == 0 && got == 65536) memory->cancelled = 1;
  return got;
}
static void memory_release(void *context) { ((memory_source *)context)->releases++; }
static int memory_cancelled(void *context) { return ((memory_source *)context)->cancelled; }
static exr_source source_for(memory_source *memory, const void *bytes, size_t size) {
  exr_source source = {0};
  memset(memory, 0, sizeof(*memory));
  memory->bytes = bytes; memory->size = size;
  source.size = size; source.read_at = memory_read; source.release = memory_release; source.context = memory;
  source.control.cancelled = memory_cancelled; source.control.context = memory;
  return source;
}
static void passed(const char *name) { cases++; printf("PASS %s\n", name); }
static size_t book_count(exr_library *library) {
  exr_book *books = NULL; size_t count = 0;
  OK(exr_library_books(library, NULL, &books, &count, &error));
  exr_books_free(books, count); return count;
}
static unsigned char *fixture(const char *root, const char *name, size_t *size) {
  char path[4096]; FILE *file; long length; unsigned char *bytes;
  CHECK(snprintf(path, sizeof(path), "%s/%s", root, name) > 0);
  file = fopen(path, "rb"); CHECK(file != NULL);
  CHECK(!fseek(file, 0, SEEK_END) && (length = ftell(file)) > 0 && !fseek(file, 0, SEEK_SET));
  *size = (size_t)length; bytes = malloc(*size); CHECK(bytes != NULL);
  CHECK(fread(bytes, 1, *size, file) == *size && !fclose(file)); return bytes;
}
static void source_matches(exr_library *library, int64_t id, const unsigned char *bytes, size_t size) {
  exr_source stored = {0}; unsigned char buffer[4096]; size_t at = 0;
  OK(exr_library_source(library, id, &stored, &error)); CHECK(stored.size == size && stored.release);
  while (at < size) {
    size_t wanted = size - at < sizeof(buffer) ? size - at : sizeof(buffer);
    CHECK(stored.read_at(stored.context, at, buffer, wanted) == wanted && !memcmp(buffer, bytes + at, wanted));
    at += wanted;
  }
  stored.release(stored.context);
}
static void write_utf8(const char *path, const void *bytes, size_t size) {
  FILE *file;
#ifdef _WIN32
  wchar_t wide[4096];
  CHECK(MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1, wide, 4096) > 0);
  file = _wfopen(wide, L"wb");
#else
  file = fopen(path, "wb");
#endif
  CHECK(file && fwrite(bytes, 1, size, file) == size && !fclose(file));
}
static void remove_utf8(const char *path) {
#ifdef _WIN32
  wchar_t wide[4096];
  CHECK(MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1, wide, 4096) > 0);
  CHECK(!_wremove(wide));
#else
  CHECK(!remove(path));
#endif
}

static void text_and_dedup(exr_library *library) {
  const unsigned char text[] = "Alpha borrowed bytes; progress and notes survive duplicate imports.";
  memory_source memory; exr_source source = source_for(&memory, text, sizeof(text) - 1);
  exr_sideload_result result = {sizeof(result), 0, 0}; int64_t id, note_id = 0;
  exr_book *books = NULL; exr_note note = {0}, *notes = NULL; size_t count = 0;
  memory.short_read = 3;
  OK(exr_sideload_import_source(library, EXR_TXT, &source, "Original title", NULL, &result, &error));
  CHECK(result.book_id > 0 && result.created && memory.calls > 1 && !memory.releases);
  id = result.book_id; source_matches(library, id, text, sizeof(text) - 1);
  OK(exr_library_books(library, NULL, &books, &count, &error)); CHECK(count == 1);
  books[0].position = 5; books[0].favorite = 1; OK(exr_library_update(library, &books[0], &error));
  exr_books_free(books, count);
  note.book_id = id; note.start = 0; note.end = 5; note.text = "Keep this note";
  OK(exr_library_note(library, &note, &note_id, &error));
  OK(exr_sideload_import_source(library, EXR_TXT, &source, "Do not rename", NULL, &result, &error));
  CHECK(result.book_id == id && !result.created && book_count(library) == 1 && !memory.releases);
  OK(exr_library_books(library, NULL, &books, &count, &error));
  CHECK(count == 1 && !strcmp(books[0].title, "Original title") && books[0].favorite && books[0].position == 5);
  exr_books_free(books, count);
  OK(exr_library_notes(library, id, &notes, &count, &error));
  CHECK(count == 1 && notes[0].id == note_id && !strcmp(notes[0].text, "Keep this note"));
  exr_notes_free(notes, count);
  memory.cancelled = 1;
  CHECK(exr_sideload_import_source(library, EXR_TXT, &source, NULL, NULL, &result, &error) == EXR_CANCELLED);
  CHECK(!result.book_id && !result.created && book_count(library) == 1 && !memory.releases);
  source.release(source.context); CHECK(memory.releases == 1);
  passed("borrowed_short_reads_exact_dedup_preserves_progress_notes_and_old_book");
}

static void format_routes(exr_library *library, const char *root, const char *work) {
  const char *names[] = {"sample.epub", "comic.cbz", "sample.html", "sample.fb2", "sample.docx", "sample.rtf", "sample.mobi"};
  const exr_format formats[] = {EXR_EPUB, EXR_CBZ, EXR_HTML, EXR_FB2, EXR_DOCX, EXR_RTF, EXR_MOBI};
  for (size_t i = 0; i < sizeof(formats) / sizeof(formats[0]); i++) {
    size_t size; unsigned char *bytes = fixture(root, names[i], &size);
    memory_source memory; exr_source source = source_for(&memory, bytes, size);
    exr_sideload_result result = {sizeof(result), 0, 0}; int64_t id;
    memory.short_read = 11;
    OK(exr_sideload_import_source(library, formats[i], &source, names[i], NULL, &result, &error));
    CHECK(result.created && result.book_id > 0 && !memory.releases); id = result.book_id;
    source_matches(library, id, bytes, size);
    if (formats[i] == EXR_EPUB) {
      exr_library_epub_info info = {0}; info.struct_size = sizeof(info);
      OK(exr_library_epub_info_get(library, id, &info, &error)); CHECK(info.bounded_storage && !info.global_extent_known);
    }
    char path[4096]; CHECK(snprintf(path, sizeof(path), "%s/%s", root, names[i]) > 0);
    OK(exr_sideload_import_file(library, formats[i], path, "No duplicate rename", NULL, &result, &error));
    CHECK(result.book_id == id && !result.created && !memory.releases);
    source.release(source.context); CHECK(memory.releases == 1); free(bytes); passed(names[i]);
  }
  {
    size_t size; unsigned char *bytes = fixture(root, "pdf-public.pdf", &size); char path[4096];
    memory_source memory; exr_source source = source_for(&memory, bytes, size);
    exr_sideload_result result = {sizeof(result), 0, 0}; exr_sideload_options options = {0};
    exr_fixed_document *document = NULL; size_t pages = 0; int64_t id;
    CHECK(snprintf(path, sizeof(path), "%s/\xe6\xb5\x8b\xe8\xaf\x95-stable.pdf", work) > 0);
    write_utf8(path, bytes, size);
    CHECK(exr_sideload_import_source(library, EXR_PDF, &source, NULL, NULL, &result, &error) == EXR_UNSUPPORTED);
    CHECK(!result.book_id && !result.created && !memory.calls && !memory.releases);
    OK(exr_sideload_import_file(library, EXR_PDF, path, "\xe4\xb8\xad\xe6\x96\x87 PDF", NULL, &result, &error));
    CHECK(result.created && result.book_id > 0); id = result.book_id; source_matches(library, id, bytes, size);
    OK(exr_library_fixed_source(library, id, NULL, &document, &error));
    CHECK(exr_fixed_pages(document, &pages) && pages > 0); exr_fixed_free(document);
    OK(exr_sideload_import_file(library, EXR_PDF, path, "No duplicate rename", NULL, &result, &error));
    CHECK(result.book_id == id && !result.created);
    options.struct_size = sizeof(options); options.control.cancelled = memory_cancelled; options.control.context = &memory;
    memory.cancelled = 1;
    CHECK(exr_sideload_import_file(library, EXR_PDF, path, NULL, &options, &result, &error) == EXR_CANCELLED);
    CHECK(!result.book_id && !result.created); source_matches(library, id, bytes, size);
    source.release(source.context); CHECK(memory.releases == 1);
    remove_utf8(path); free(bytes); passed("stable_utf8_pdf_file_exact_dedup_and_pre_call_cancel");
  }
}

static void rollback_cases(exr_library *library, const char *root) {
  size_t original_size, size; unsigned char *original = fixture(root, "comic.cbz", &original_size), *bytes;
  size_t before = book_count(library); exr_sideload_result result = {sizeof(result), 0, 0};
  memory_source memory; exr_source source;
  /* A legal maximum ZIP comment makes the stored original cross a 64 KiB chunk.
     It changes no image, central directory or SDK expectation. */
  CHECK(original_size >= 22 && !memcmp(original + original_size - 22, "PK\005\006", 4));
  CHECK(original[original_size - 2] == 0 && original[original_size - 1] == 0);
  size = original_size + 65535; bytes = malloc(size); CHECK(bytes != NULL);
  memcpy(bytes, original, original_size); memset(bytes + original_size, 'c', 65535);
  bytes[original_size - 2] = 255; bytes[original_size - 1] = 255; free(original);
  source = source_for(&memory, bytes, size); memory.fail_copy = 1;
  CHECK(exr_sideload_import_source(library, EXR_CBZ, &source, "Must roll back", NULL, &result, &error) == EXR_IO);
  CHECK(memory.copy_started && !result.book_id && !result.created && !memory.releases && book_count(library) == before);
  source = source_for(&memory, bytes, size); memory.cancel_copy = 1;
  CHECK(exr_sideload_import_source(library, EXR_CBZ, &source, "Must roll back", NULL, &result, &error) == EXR_CANCELLED);
  CHECK(memory.copy_started && !result.book_id && !result.created && !memory.releases && book_count(library) == before);
  source = source_for(&memory, bytes, size);
  OK(exr_sideload_import_source(library, EXR_CBZ, &source, "Recovered import", NULL, &result, &error));
  CHECK(result.created && book_count(library) == before + 1 && !memory.releases);
  int64_t id = result.book_id; source_matches(library, id, bytes, size);
  source = source_for(&memory, bytes, size); memory.cancel_copy = 1;
  CHECK(exr_sideload_import_source(library, EXR_CBZ, &source, NULL, NULL, &result, &error) == EXR_CANCELLED);
  CHECK(memory.copy_started && !result.book_id && !result.created && book_count(library) == before + 1);
  source_matches(library, id, bytes, size);
  source.release(source.context); CHECK(memory.releases == 1); free(bytes);
  passed("actual_stream_insert_io_cancel_rollback_and_cancelled_duplicate_retains_old_book");
}

static void limits_and_arguments(exr_library *library, const char *work) {
  const unsigned char text[] = "bounded input"; memory_source memory;
  exr_source source = source_for(&memory, text, sizeof(text) - 1);
  exr_sideload_result result = {sizeof(result), 99, 1}; exr_sideload_options options = {0};
  size_t before = book_count(library); char path[4096];
  options.struct_size = sizeof(options); options.max_input_bytes = 2;
  CHECK(exr_sideload_import_source(library, EXR_TXT, &source, NULL, &options, &result, &error) == EXR_LIMIT);
  CHECK(!result.book_id && !result.created && !memory.calls);
  source.size = EXR_SIDELOAD_MEMORY_LIMIT + 1;
  CHECK(exr_sideload_import_source(library, EXR_TXT, &source, NULL, NULL, &result, &error) == EXR_LIMIT);
  source.size = EXR_SIDELOAD_STREAM_LIMIT + 1;
  CHECK(exr_sideload_import_source(library, EXR_EPUB, &source, NULL, NULL, &result, &error) == EXR_LIMIT);
  source.size = 0;
  CHECK(exr_sideload_import_source(library, EXR_TXT, &source, NULL, NULL, &result, &error) == EXR_FORMAT);
  CHECK(!memory.calls && !memory.releases);
  source.size = sizeof(text) - 1;
  CHECK(exr_sideload_import_source(library, EXR_CUSTOM, &source, NULL, NULL, &result, &error) == EXR_UNSUPPORTED);
  CHECK(exr_sideload_import_source(library, EXR_TXT, NULL, NULL, NULL, &result, &error) == EXR_ARGUMENT);
  CHECK(exr_sideload_import_file(library, EXR_TXT, NULL, NULL, NULL, &result, &error) == EXR_ARGUMENT);
  CHECK(snprintf(path, sizeof(path), "%s/missing-sideload.txt", work) > 0);
  CHECK(exr_sideload_import_file(library, EXR_TXT, path, NULL, NULL, &result, &error) == EXR_IO);
  CHECK(!result.book_id && !result.created && book_count(library) == before);
  CHECK(snprintf(path, sizeof(path), "%s/sideload-limited.txt", work) > 0);
  write_utf8(path, text, sizeof(text) - 1);
  CHECK(exr_sideload_import_file(library, EXR_TXT, path, NULL, &options, &result, &error) == EXR_LIMIT);
  write_utf8(path, text, 0);
  CHECK(exr_sideload_import_file(library, EXR_TXT, path, NULL, NULL, &result, &error) == EXR_FORMAT);
  remove_utf8(path);
  memory.fail_read = 1;
  CHECK(exr_sideload_import_source(library, EXR_TXT, &source, NULL, NULL, &result, &error) == EXR_IO);
  CHECK(!result.book_id && !result.created && !memory.releases && book_count(library) == before);
  memory.fail_read = 0;
  options.struct_size = offsetof(exr_sideload_options, control);
  CHECK(exr_sideload_import_source(library, EXR_TXT, &source, NULL, &options, &result, &error) == EXR_ARGUMENT);
  result.struct_size = sizeof(size_t); result.book_id = 99; result.created = 7;
  CHECK(exr_sideload_import_source(library, EXR_TXT, &source, NULL, NULL, &result, &error) == EXR_ARGUMENT);
  CHECK(result.book_id == 99 && result.created == 7);
  {
    struct { exr_sideload_result result; unsigned char tail[16]; } extended;
    memset(&extended, 0x5a, sizeof(extended)); extended.result.struct_size = sizeof(extended);
    OK(exr_sideload_import_source(library, EXR_TXT, &source, NULL, NULL, &extended.result, &error));
    CHECK(extended.result.book_id > 0 && extended.result.created);
    for (size_t i = 0; i < sizeof(extended.tail); i++) CHECK(extended.tail[i] == 0x5a);
  }
  passed("explicit_limits_empty_missing_unsupported_and_struct_size_guards");
}

int main(int argc, char **argv) {
  exr_library *library = NULL; char path[4096]; size_t count;
  CHECK(argc == 3);
  CHECK(snprintf(path, sizeof(path), "%s/sideload-library.sqlite", argv[2]) > 0); remove(path);
  OK(exr_library_open(path, &library, &error));
  text_and_dedup(library); format_routes(library, argv[1], argv[2]);
  rollback_cases(library, argv[1]); limits_and_arguments(library, argv[2]);
  count = book_count(library); exr_library_close(library); library = NULL;
  OK(exr_library_open(path, &library, &error)); CHECK(book_count(library) == count);
  exr_library_close(library); CHECK(!remove(path)); passed("committed_books_survive_library_reopen");
  printf("{\"passed\":true,\"checks\":%u,\"cases\":%u,\"formats\":9,\"public_sdk_only\":true}\n", checks, cases);
  return 0;
}
