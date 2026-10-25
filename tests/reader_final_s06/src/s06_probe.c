/* SPDX-License-Identifier: MIT */
/* S06 unified import-entry matrix probe.
 *
 * A real host program built only against installed packages:
 *   EXReader (frozen SDK), EXReaderSideload, EXReaderDesktopDrop.
 *
 * For one platform it performs the five entry scenarios a reader host owes a
 * user - local file, system open/share, cloud download to sideload, an already
 * present identical original, and a bad file - plus the identity, cancel and
 * reopen checks that back them, then reports every named case as one JSONL
 * record. No case is inferred from another platform, and no result is produced
 * without the real call having run. */
#include "sha256.h"
#include "s06_handoff.h"
#include <exr_desktop_drop.h>
#include <exr_sideload.h>
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#ifdef _WIN32
#include <direct.h>
#include <windows.h>
#endif

#define S06_PATH 4096
#define S06_DETAIL 512

static const char *fixture_dir;
static const char *work_dir;
static const char *cloud_dir;
static const char *platform_name;
static exr_error error;
static exr_library *library;
static unsigned case_count;
static unsigned failure_count;

/* ----------------------------------------------------------------- output -- */
static void json_escape(const char *in, char *out, size_t size) {
  size_t at = 0;
  for (; *in && at + 8 < size; in++) {
    unsigned char byte = (unsigned char)*in;
    if (byte == '"' || byte == '\\') { out[at++] = '\\'; out[at++] = (char)byte; }
    else if (byte < 0x20) at += (size_t)snprintf(out + at, size - at, "\\u%04x", byte);
    else out[at++] = (char)byte;
  }
  out[at] = 0;
}

static void report(const char *name, int ok, const char *fmt, ...) {
  char detail[S06_DETAIL * 2], escaped[S06_DETAIL * 6];
  va_list arguments;
  detail[0] = 0;
  if (fmt) {
    va_start(arguments, fmt);
    vsnprintf(detail, sizeof(detail), fmt, arguments);
    va_end(arguments);
  }
  json_escape(detail, escaped, sizeof(escaped));
  case_count++;
  if (!ok) failure_count++;
  printf("{\"case\":\"%s\",\"status\":\"%s\",\"detail\":\"%s\"}\n", name, ok ? "pass" : "fail", escaped);
  fflush(stdout);
}

/* ------------------------------------------------------------ filesystem -- */
static int make_dir(const char *path) {
#ifdef _WIN32
  int made = _mkdir(path);
#else
  int made = mkdir(path, 0700);
#endif
  return made == 0 || errno == EEXIST;
}

static int remove_path(const char *path) {
#ifdef _WIN32
  wchar_t wide[S06_PATH];
  if (!MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1, wide, S06_PATH)) return 0;
  return _wremove(wide) == 0;
#else
  return remove(path) == 0;
#endif
}

static int join_path(char *out, size_t size, const char *dir, const char *name) {
  int written = snprintf(out, size, "%s/%s", dir, name);
  return written > 0 && (size_t)written < size;
}

static FILE *open_mode(const char *path, const wchar_t *wide_mode, const char *mode) {
#ifdef _WIN32
  wchar_t wide[S06_PATH];
  if (!MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1, wide, S06_PATH)) return NULL;
  return _wfopen(wide, wide_mode);
#else
  (void)wide_mode;
  return fopen(path, mode);
#endif
}

static int read_file(const char *path, unsigned char **bytes, size_t *size) {
  FILE *file = open_mode(path, L"rb", "rb");
  long length;
  *bytes = NULL;
  *size = 0;
  if (!file) return 0;
  if (fseek(file, 0, SEEK_END) != 0 || (length = ftell(file)) < 0 || fseek(file, 0, SEEK_SET) != 0) {
    fclose(file);
    return 0;
  }
  if (length > 0) {
    *bytes = (unsigned char *)malloc((size_t)length);
    if (!*bytes || fread(*bytes, 1, (size_t)length, file) != (size_t)length) {
      free(*bytes);
      *bytes = NULL;
      fclose(file);
      return 0;
    }
  }
  *size = (size_t)length;
  fclose(file);
  return 1;
}

static int write_file(const char *path, const void *bytes, size_t size) {
  FILE *file = open_mode(path, L"wb", "wb");
  int ok;
  if (!file) return 0;
  ok = size == 0 || fwrite(bytes, 1, size, file) == size;
  if (fclose(file) != 0) ok = 0;
  return ok;
}

static void sha256_of(const void *bytes, size_t size, char hex[65]) {
  s06_sha256 hash;
  unsigned char digest[32];
  s06_sha256_init(&hash);
  s06_sha256_update(&hash, bytes, size);
  s06_sha256_finish(&hash, digest);
  s06_sha256_hex(digest, hex);
}

static int sha256_of_file(const char *path, char hex[65], size_t *size_out) {
  unsigned char *bytes = NULL;
  size_t size = 0;
  if (!read_file(path, &bytes, &size)) return 0;
  sha256_of(bytes, size, hex);
  if (size_out) *size_out = size;
  free(bytes);
  return 1;
}

static int same_path(const char *left, const char *right) {
  size_t index = 0;
  if (!left || !right) return 0;
  for (;;) {
    char a = left[index], b = right[index];
    if (a == '\\') a = '/';
    if (b == '\\') b = '/';
#ifdef _WIN32
    if (a >= 'A' && a <= 'Z') a = (char)(a - 'A' + 'a');
    if (b >= 'A' && b <= 'Z') b = (char)(b - 'A' + 'a');
#endif
    if (a != b) return 0;
    if (!a) return 1;
    index++;
  }
}

/* ---------------------------------------------------------------- library -- */
static size_t count_books(exr_library *handle, int *ok) {
  exr_book *books = NULL;
  size_t count = 0;
  *ok = handle && exr_library_books(handle, NULL, &books, &count, &error) == EXR_OK;
  exr_books_free(books, count);
  return *ok ? count : 0;
}

static int source_matches(exr_library *handle, int64_t id, const unsigned char *bytes, size_t size,
    char *detail, size_t detail_size) {
  exr_source stored = {0};
  unsigned char buffer[4096];
  size_t at = 0;
  if (exr_library_source(handle, id, &stored, &error) != EXR_OK) {
    snprintf(detail, detail_size, "exr_library_source failed: %s", error.message);
    return 0;
  }
  if (stored.size != size) {
    snprintf(detail, detail_size, "stored original is %llu bytes, source is %zu",
        (unsigned long long)stored.size, size);
    if (stored.release) stored.release(stored.context);
    return 0;
  }
  while (at < size) {
    size_t wanted = size - at < sizeof(buffer) ? size - at : sizeof(buffer);
    if (stored.read_at(stored.context, at, buffer, wanted) != wanted ||
        memcmp(buffer, bytes + at, wanted) != 0) {
      snprintf(detail, detail_size, "stored original differs at byte %zu", at);
      if (stored.release) stored.release(stored.context);
      return 0;
    }
    at += wanted;
  }
  if (stored.release) stored.release(stored.context);
  snprintf(detail, detail_size, "%zu bytes identical", size);
  return 1;
}

static int export_matches(exr_library *handle, int64_t id, const char *destination,
    const unsigned char *bytes, size_t size, char *detail, size_t detail_size) {
  uint64_t written = 0;
  unsigned char *exported = NULL;
  size_t exported_size = 0;
  exr_status status = exr_sideload_export_original(handle, id, destination, NULL, &written, &error);
  if (status != EXR_OK) {
    snprintf(detail, detail_size, "export failed: status %d %s", (int)status, error.message);
    return 0;
  }
  if (written != (uint64_t)size) {
    snprintf(detail, detail_size, "exported %llu bytes, original is %zu", (unsigned long long)written, size);
    return 0;
  }
  if (!read_file(destination, &exported, &exported_size)) {
    snprintf(detail, detail_size, "cannot read the exported original");
    return 0;
  }
  if (exported_size != size || memcmp(exported, bytes, size) != 0) {
    snprintf(detail, detail_size, "exported original differs from the source bytes");
    free(exported);
    return 0;
  }
  free(exported);
  snprintf(detail, detail_size, "exported %zu bytes identical", size);
  return 1;
}

/* -------------------------------------------------- borrowed memory source -- */
typedef struct {
  const unsigned char *bytes;
  size_t size;
} memory_view;

static size_t memory_read(void *context, uint64_t offset, void *buffer, size_t size) {
  memory_view *view = (memory_view *)context;
  size_t available;
  if (!view || offset >= view->size) return 0;
  available = view->size - (size_t)offset;
  if (size > available) size = available;
  memcpy(buffer, view->bytes + (size_t)offset, size);
  return size;
}

static void memory_release(void *context) { (void)context; }

static int cancel_flag;
static int cancel_now(void *context) {
  (void)context;
  return cancel_flag;
}

/* ------------------------------------------------------------------- data -- */
typedef struct {
  const char *name;
  unsigned char *bytes;
  size_t size;
  char sha[65];
  char path[S06_PATH];
  int64_t id;
} held_fixture;

typedef struct {
  const char *name;
  exr_format format;
  const char *tag;
} format_row;

static const format_row format_rows[] = {
  {"sample.txt", EXR_TXT, "txt"},
  {"sample.html", EXR_HTML, "html"},
  {"sample.fb2", EXR_FB2, "fb2"},
  {"sample.epub", EXR_EPUB, "epub"},
  {"sample.docx", EXR_DOCX, "docx"},
  {"sample.rtf", EXR_RTF, "rtf"},
  {"sample.mobi", EXR_MOBI, "mobi"},
  {"pdf-public.pdf", EXR_PDF, "pdf"},
  {"comic.cbz", EXR_CBZ, "cbz"}
};
#define FORMAT_COUNT (sizeof(format_rows) / sizeof(format_rows[0]))

static int load_fixture(const char *name, held_fixture *out) {
  char path[S06_PATH];
  memset(out, 0, sizeof(*out));
  out->name = name;
  if (!join_path(path, sizeof(path), fixture_dir, name)) return 0;
  if (!read_file(path, &out->bytes, &out->size) || out->size == 0) {
    free(out->bytes);
    out->bytes = NULL;
    return 0;
  }
  sha256_of(out->bytes, out->size, out->sha);
  return 1;
}

/* ------------------------------------------------------ nine format sweep -- */
static void formats_group(const char *work) {
  exr_library *formats_library = NULL;
  char library_path[S06_PATH], detail[S06_DETAIL];
  size_t index, proved = 0;
  if (!join_path(library_path, sizeof(library_path), work, "s06-formats.sqlite")) {
    report("nine_formats_library_open", 0, "work path too long");
    return;
  }
  remove_path(library_path);
  if (exr_library_open(library_path, &formats_library, &error) != EXR_OK) {
    report("nine_formats_library_open", 0, "exr_library_open failed: %s", error.message);
    return;
  }
  for (index = 0; index < FORMAT_COUNT; index++) {
    char case_name[128], path[S06_PATH], export_path[S06_PATH], hex[65];
    unsigned char *bytes = NULL;
    size_t size = 0;
    exr_sideload_result result = {sizeof(result), 0, 0};
    exr_status status;
    int ok = 0;
    snprintf(case_name, sizeof(case_name), "format_%s_import_readback_dedupe", format_rows[index].tag);
    if (!join_path(path, sizeof(path), fixture_dir, format_rows[index].name) ||
        !read_file(path, &bytes, &size) || size == 0) {
      report(case_name, 0, "cannot read fixture %s", format_rows[index].name);
      free(bytes);
      continue;
    }
    status = exr_sideload_import_file(formats_library, format_rows[index].format, path,
        format_rows[index].name, NULL, &result, &error);
    if (status != EXR_OK || !result.created || result.book_id <= 0) {
      report(case_name, 0, "first import status %d created %d: %s",
          (int)status, result.created, error.message);
      free(bytes);
      continue;
    }
    ok = source_matches(formats_library, result.book_id, bytes, size, detail, sizeof(detail));
    if (ok) {
      exr_sideload_result again = {sizeof(again), 0, 0};
      status = exr_sideload_import_file(formats_library, format_rows[index].format, path,
          "renamed duplicate", NULL, &again, &error);
      if (status != EXR_OK || again.created || again.book_id != result.book_id) {
        ok = 0;
        snprintf(detail, sizeof(detail), "duplicate import status %d created %d id %lld",
            (int)status, again.created, (long long)again.book_id);
      }
    }
    if (ok) {
      snprintf(export_path, sizeof(export_path), "%s/exports/format-%s.original", work, format_rows[index].tag);
      ok = export_matches(formats_library, result.book_id, export_path, bytes, size, detail, sizeof(detail));
    }
    if (ok) {
      sha256_of(bytes, size, hex);
      snprintf(detail, sizeof(detail), "%zu bytes, sha256 %s", size, hex);
      proved++;
    }
    report(case_name, ok, "%s", detail);
    free(bytes);
  }
  {
    int count_ok = 0;
    size_t count = count_books(formats_library, &count_ok);
    report("nine_formats_all_nine_measured", proved == FORMAT_COUNT && count_ok && count == FORMAT_COUNT,
        "%zu of %zu formats proved, library holds %zu books", proved, FORMAT_COUNT, count);
  }
  {
    exr_library *reopened = NULL;
    int before_ok = 0, after_ok = 0;
    exr_book *books = NULL;
    size_t before = count_books(formats_library, &before_ok), after = 0;
    exr_library_close(formats_library);
    if (exr_library_open(library_path, &reopened, &error) != EXR_OK) {
      report("nine_formats_library_reopen", 0, "reopen failed: %s", error.message);
      return;
    }
    after_ok = exr_library_books(reopened, NULL, &books, &after, &error) == EXR_OK;
    exr_books_free(books, after);
    report("nine_formats_library_reopen", before_ok && after_ok && after == before,
        "%zu books before and %zu after reopen", before, after);
    exr_library_close(reopened);
  }
}

/* ------------------------------------------------------------ local file -- */
static void local_file_group(const char *work, held_fixture *epub, held_fixture *fb2, held_fixture *cbz) {
  char private_path[S06_PATH], unicode_path[S06_PATH];
  exr_sideload_result result = {sizeof(result), 0, 0};
  exr_status status;

  epub->id = 0;
  if (!join_path(private_path, sizeof(private_path), work, "local/host-private.epub") ||
      !write_file(private_path, epub->bytes, epub->size)) {
    report("local_file_private_path_import", 0, "cannot stage the host-private copy");
  } else {
    status = exr_sideload_import_file(library, EXR_EPUB, private_path, "S06 local original",
        NULL, &result, &error);
    if (status == EXR_OK && result.created) {
      epub->id = result.book_id;
      snprintf(epub->path, sizeof(epub->path), "%s", private_path);
    }
    report("local_file_private_path_import", status == EXR_OK && result.created && result.book_id > 0,
        "status %d created %d id %lld: %s", (int)status, result.created,
        (long long)result.book_id, error.message);
  }

  if (!join_path(unicode_path, sizeof(unicode_path), work,
          "local/\xe6\x9c\xac\xe5\x9c\xb0 \xe5\xaf\xbc\xe5\x85\xa5 \xe7\xa4\xba\xe4\xbe\x8b.fb2") ||
      !write_file(unicode_path, fb2->bytes, fb2->size)) {
    report("local_file_utf8_path_import", 0, "cannot stage the UTF-8 named copy");
  } else {
    exr_sideload_result unicode_result = {sizeof(unicode_result), 0, 0};
    status = exr_sideload_import_file(library, EXR_FB2, unicode_path, "UTF-8 path", NULL,
        &unicode_result, &error);
    report("local_file_utf8_path_import", status == EXR_OK && unicode_result.created,
        "status %d created %d: %s", (int)status, unicode_result.created, error.message);
  }

  {
    memory_view view;
    exr_source source = {0};
    exr_sideload_result source_result = {sizeof(source_result), 0, 0};
    view.bytes = cbz->bytes;
    view.size = cbz->size;
    source.size = cbz->size;
    source.read_at = memory_read;
    source.release = memory_release;
    source.context = &view;
    status = exr_sideload_import_source(library, EXR_CBZ, &source, "Comic via borrowed source",
        NULL, &source_result, &error);
    report("local_file_source_route_cbz", status == EXR_OK && source_result.created,
        "status %d created %d: %s", (int)status, source_result.created, error.message);
  }

  {
    char detail[S06_DETAIL];
    int ok = epub->id > 0 && source_matches(library, epub->id, epub->bytes, epub->size,
        detail, sizeof(detail));
    report("local_file_original_readback_exact", ok, "%s", detail);
  }
}

/* -------------------------------------------------------- system handoff -- */
static void handoff_group(const char *work, held_fixture *epub) {
  char pasted[S06_PATH], folder[S06_PATH], absent[S06_PATH], detail[S06_DETAIL];
  s06_handoff_result handoff;
  const char *single[1];
  const char *pair[2];
  int staged, delivered = 0;
  int count_ok = 0;
  size_t before = count_books(library, &count_ok);
  (void)before;

  staged = join_path(pasted, sizeof(pasted), work, "handoff/pasted.epub") &&
           write_file(pasted, epub->bytes, epub->size) &&
           join_path(folder, sizeof(folder), work, "handoff/folder") && make_dir(folder) &&
           join_path(absent, sizeof(absent), work, "handoff/absent.epub");
  if (!staged) {
    report("system_handoff_delivers_file", 0, "cannot stage the handoff fixtures");
  } else {
    memset(&handoff, 0, sizeof(handoff));
    single[0] = pasted;
    if (!s06_handoff_deliver(single, 1, &handoff)) {
      report("system_handoff_delivers_file", 0, "platform handoff unavailable: %s", handoff.detail);
    } else {
      delivered = handoff.delivered && handoff.item_count == 1 && handoff.file_count == 1 &&
                  handoff.kind[0] == EXR_DROP_ITEM_FILE && same_path(handoff.path[0], pasted);
      report("system_handoff_delivers_file", delivered,
          "adapter status %d, %zu items / %zu files, kind %zu, delivered '%s' expected '%s'",
          handoff.status, handoff.item_count, handoff.file_count,
          handoff.item_count ? handoff.kind[0] : 0,
          handoff.item_count ? handoff.path[0] : "", pasted);
    }
  }

  if (delivered) {
    exr_sideload_result result = {sizeof(result), 0, 0};
    exr_status status = exr_sideload_import_file(library, EXR_EPUB, handoff.path[0],
        "Handed over by the system", NULL, &result, &error);
    report("system_handoff_imports_delivered_file", status == EXR_OK && result.created,
        "status %d created %d: %s", (int)status, result.created, error.message);
  } else {
    report("system_handoff_imports_delivered_file", 0, "no delivered file to import");
  }

  if (staged) {
    int mid_ok = 0;
    size_t mid = count_books(library, &mid_ok);
    memset(&handoff, 0, sizeof(handoff));
    single[0] = folder;
    if (!s06_handoff_deliver(single, 1, &handoff)) {
      report("system_handoff_directory_ignored", 0, "platform handoff unavailable: %s", handoff.detail);
    } else {
      int after_ok = 0;
      size_t after = count_books(library, &after_ok);
      int ok = handoff.delivered && handoff.item_count == 1 && handoff.file_count == 0 &&
               handoff.kind[0] == EXR_DROP_ITEM_DIRECTORY && after_ok && mid_ok && after == mid;
      report("system_handoff_directory_ignored", ok,
          "status %d, %zu items / %zu files, kind %zu, books %zu -> %zu (a directory is never imported)",
          handoff.status, handoff.item_count, handoff.file_count,
          handoff.item_count ? handoff.kind[0] : 0, mid, after);
    }

    memset(&handoff, 0, sizeof(handoff));
    single[0] = absent;
    if (!s06_handoff_deliver(single, 1, &handoff)) {
      report("system_handoff_missing_path_rejected", 0, "platform handoff unavailable: %s", handoff.detail);
    } else {
      int ok = handoff.delivered && handoff.item_count == 1 && handoff.file_count == 0 &&
               handoff.kind[0] == EXR_DROP_ITEM_MISSING;
      report("system_handoff_missing_path_rejected", ok,
          "status %d, %zu items / %zu files, kind %zu", handoff.status, handoff.item_count,
          handoff.file_count, handoff.item_count ? handoff.kind[0] : 0);
    }

    memset(&handoff, 0, sizeof(handoff));
    pair[0] = pasted;
    pair[1] = absent;
    if (!s06_handoff_deliver(pair, 2, &handoff)) {
      report("system_handoff_multi_file_all_delivered", 0, "platform handoff unavailable: %s", handoff.detail);
    } else {
      int ok = handoff.delivered && handoff.item_count == 2 && handoff.file_count == 1 &&
               handoff.directory_count == 0;
      report("system_handoff_multi_file_all_delivered", ok,
          "status %d, %zu items / %zu files", handoff.status, handoff.item_count, handoff.file_count);
    }
  } else {
    report("system_handoff_directory_ignored", 0, "handoff fixtures were not staged");
    report("system_handoff_missing_path_rejected", 0, "handoff fixtures were not staged");
    report("system_handoff_multi_file_all_delivered", 0, "handoff fixtures were not staged");
  }
  (void)detail;
}

/* ------------------------------------------------ cloud download to sideload -- */
static void cloud_group(held_fixture *epub, held_fixture *pdf) {
  char cloud_epub[S06_PATH], cloud_pdf[S06_PATH], hex_epub[65], hex_pdf[65];
  size_t size_epub = 0, size_pdf = 0;
  int epub_ok, pdf_ok;

  if (!cloud_dir || !cloud_dir[0]) {
    report("cloud_download_matches_pinned_fixture", 0, "no --cloud directory was handed to the probe");
    report("cloud_download_import_new_book", 0, "no cloud download available");
    report("cloud_download_duplicate_matches_local_book", 0, "no cloud download available");
    return;
  }
  if (!join_path(cloud_epub, sizeof(cloud_epub), cloud_dir, "sample.epub") ||
      !join_path(cloud_pdf, sizeof(cloud_pdf), cloud_dir, "pdf-public.pdf")) {
    report("cloud_download_matches_pinned_fixture", 0, "cloud path too long");
    report("cloud_download_import_new_book", 0, "cloud path too long");
    report("cloud_download_duplicate_matches_local_book", 0, "cloud path too long");
    return;
  }
  epub_ok = sha256_of_file(cloud_epub, hex_epub, &size_epub);
  pdf_ok = sha256_of_file(cloud_pdf, hex_pdf, &size_pdf);
  report("cloud_download_matches_pinned_fixture",
      epub_ok && pdf_ok && !strcmp(hex_epub, epub->sha) && size_epub == epub->size &&
          !strcmp(hex_pdf, pdf->sha) && size_pdf == pdf->size,
      "downloaded epub sha256 %s (%zu B) vs pinned %s (%zu B); downloaded pdf sha256 %s (%zu B) vs pinned %s (%zu B)",
      hex_epub, size_epub, epub->sha, epub->size, hex_pdf, size_pdf, pdf->sha, pdf->size);

  {
    exr_sideload_result result = {sizeof(result), 0, 0};
    exr_status status = exr_sideload_import_file(library, EXR_PDF, cloud_pdf,
        "Downloaded from the cloud", NULL, &result, &error);
    report("cloud_download_import_new_book", status == EXR_OK && result.created && result.book_id > 0,
        "status %d created %d id %lld: %s", (int)status, result.created,
        (long long)result.book_id, error.message);
  }
  {
    exr_sideload_result result = {sizeof(result), 0, 0};
    exr_status status = exr_sideload_import_file(library, EXR_EPUB, cloud_epub,
        "Downloaded duplicate of the local original", NULL, &result, &error);
    report("cloud_download_duplicate_matches_local_book",
        status == EXR_OK && !result.created && epub->id > 0 && result.book_id == epub->id,
        "status %d created %d id %lld, local original id %lld",
        (int)status, result.created, (long long)result.book_id, (long long)epub->id);
  }
}

/* ------------------------------------------------------- identical original -- */
static void duplicate_group(const char *work, held_fixture *epub) {
  char copy_path[S06_PATH], detail[S06_DETAIL];
  int count_ok = 0;
  size_t before = count_books(library, &count_ok);

  {
    exr_sideload_result result = {sizeof(result), 0, 0};
    int after_ok = 0;
    exr_status status = exr_sideload_import_file(library, EXR_EPUB, epub->path,
        "Renamed duplicate", NULL, &result, &error);
    size_t after = count_books(library, &after_ok);
    report("duplicate_same_path_created_zero",
        status == EXR_OK && !result.created && epub->id > 0 && result.book_id == epub->id &&
            after_ok && after == before,
        "status %d created %d id %lld, books %zu -> %zu (original id %lld)",
        (int)status, result.created, (long long)result.book_id, before, after, (long long)epub->id);
  }
  {
    exr_sideload_result result = {sizeof(result), 0, 0};
    int after_ok = 0;
    exr_status status;
    int staged = join_path(copy_path, sizeof(copy_path), work, "duplicate/another-name.epub") &&
                 write_file(copy_path, epub->bytes, epub->size);
    size_t after;
    if (!staged) {
      report("duplicate_renamed_copy_created_zero", 0, "cannot stage the renamed copy");
      goto renamed_done;
    }
    status = exr_sideload_import_file(library, EXR_EPUB, copy_path, "Third title",
        NULL, &result, &error);
    after = count_books(library, &after_ok);
    report("duplicate_renamed_copy_created_zero",
        status == EXR_OK && !result.created && epub->id > 0 && result.book_id == epub->id &&
            after_ok && after == before,
        "status %d created %d id %lld, books %zu -> %zu", (int)status, result.created,
        (long long)result.book_id, before, after);
  }
renamed_done:
  {
    exr_book *books = NULL;
    size_t count = 0, index;
    int found = 0, title_ok = 0, progress_ok = 0;
    if (exr_library_books(library, NULL, &books, &count, &error) == EXR_OK) {
      for (index = 0; index < count; index++) {
        if (books[index].id != epub->id) continue;
        found = 1;
        title_ok = books[index].title && !strcmp(books[index].title, "S06 local original");
        progress_ok = books[index].favorite == 1 && books[index].position == 7;
      }
      exr_books_free(books, count);
    }
    {
      exr_note *notes = NULL;
      size_t note_count = 0;
      int notes_ok = exr_library_notes(library, epub->id, &notes, &note_count, &error) == EXR_OK &&
                     note_count == 1 && notes[0].text && !strcmp(notes[0].text, "S06 keep this note");
      exr_notes_free(notes, note_count);
      report("duplicate_preserves_title_progress_notes",
          found && title_ok && progress_ok && notes_ok,
          "book found %d, title preserved %d, progress preserved %d, note preserved %d",
          found, title_ok, progress_ok, notes_ok);
    }
  }
  {
    exr_sideload_options options = {0};
    exr_sideload_result result = {sizeof(result), 0, 0};
    exr_status status;
    int after_ok = 0;
    size_t after;
    options.struct_size = sizeof(options);
    options.control.cancelled = cancel_now;
    cancel_flag = 1;
    status = exr_sideload_import_file(library, EXR_EPUB, epub->path, NULL, &options, &result, &error);
    cancel_flag = 0;
    after = count_books(library, &after_ok);
    {
      int ok = status == EXR_CANCELLED && !result.book_id && !result.created && after_ok &&
               after == before && source_matches(library, epub->id, epub->bytes, epub->size,
                   detail, sizeof(detail));
      report("duplicate_cancel_retains_old_book", ok,
          "status %d created %d, books %zu -> %zu, old original %s",
          (int)status, result.created, before, after, detail);
    }
  }
}

/* --------------------------------------------------------------- bad file -- */
static void bad_group(const char *work, held_fixture *epub) {
  char truncated[S06_PATH], garbage[S06_PATH], empty[S06_PATH], absent[S06_PATH], detail[S06_DETAIL];
  int count_ok = 0;
  size_t before = count_books(library, &count_ok);
  int staged;

  staged = join_path(truncated, sizeof(truncated), work, "bad/truncated.epub") &&
           write_file(truncated, epub->bytes, epub->size / 3) &&
           join_path(garbage, sizeof(garbage), work, "bad/garbage.epub") &&
           join_path(empty, sizeof(empty), work, "bad/empty.epub") && write_file(empty, "", 0) &&
           join_path(absent, sizeof(absent), work, "bad/absent.epub");
  if (!staged) {
    report("bad_truncated_rejected", 0, "cannot stage the bad-file fixtures");
    report("bad_garbage_rejected", 0, "cannot stage the bad-file fixtures");
    report("bad_empty_rejected", 0, "cannot stage the bad-file fixtures");
    report("bad_missing_path_rejected", 0, "cannot stage the bad-file fixtures");
    report("bad_zero_rows_after_rejection", 0, "cannot stage the bad-file fixtures");
    return;
  }
  {
    unsigned char junk[512];
    unsigned value = 0x12345678u;
    size_t index;
    for (index = 0; index < sizeof(junk); index++) {
      value = value * 1103515245u + 12345u;
      junk[index] = (unsigned char)(value >> 16);
    }
    if (!write_file(garbage, junk, sizeof(junk))) {
      report("bad_garbage_rejected", 0, "cannot write the garbage payload");
    } else {
      exr_sideload_result result = {sizeof(result), 0, 0};
      exr_status status = exr_sideload_import_file(library, EXR_EPUB, garbage, NULL, NULL, &result, &error);
      report("bad_garbage_rejected",
          status != EXR_OK && status != EXR_CANCELLED && !result.book_id && !result.created,
          "status %d (%s), created %d", (int)status, error.message, result.created);
    }
  }
  {
    exr_sideload_result result = {sizeof(result), 0, 0};
    exr_status status = exr_sideload_import_file(library, EXR_EPUB, truncated, NULL, NULL, &result, &error);
    report("bad_truncated_rejected",
        status != EXR_OK && status != EXR_CANCELLED && !result.book_id && !result.created,
        "%zu of %zu bytes kept, status %d (%s)", epub->size / 3, epub->size, (int)status, error.message);
  }
  {
    exr_sideload_result result = {sizeof(result), 0, 0};
    exr_status status = exr_sideload_import_file(library, EXR_EPUB, empty, NULL, NULL, &result, &error);
    report("bad_empty_rejected", status == EXR_FORMAT && !result.book_id && !result.created,
        "status %d (%s)", (int)status, error.message);
  }
  {
    exr_sideload_result result = {sizeof(result), 0, 0};
    exr_status status = exr_sideload_import_file(library, EXR_EPUB, absent, NULL, NULL, &result, &error);
    report("bad_missing_path_rejected", status == EXR_IO && !result.book_id && !result.created,
        "status %d (%s)", (int)status, error.message);
  }
  {
    int after_ok = 0;
    size_t after = count_books(library, &after_ok);
    int original_ok = source_matches(library, epub->id, epub->bytes, epub->size, detail, sizeof(detail));
    report("bad_zero_rows_after_rejection", after_ok && after == before && original_ok,
        "books %zu -> %zu, existing original %s", before, after, detail);
  }
}

/* ------------------------------------------- cancel before / export / reopen -- */
static void identity_group(const char *work, held_fixture *epub, held_fixture *docx) {
  int count_ok = 0;
  size_t before = count_books(library, &count_ok);
  char cancel_path[S06_PATH], export_path[S06_PATH], detail[S06_DETAIL];

  if (!join_path(cancel_path, sizeof(cancel_path), work, "local/cancelled.docx") ||
      !write_file(cancel_path, docx->bytes, docx->size)) {
    report("cancel_before_commit_zero_rows", 0, "cannot stage the cancellation input");
  } else {
    exr_sideload_options options = {0};
    exr_sideload_result result = {sizeof(result), 0, 0};
    exr_status status;
    int after_ok = 0;
    size_t after;
    options.struct_size = sizeof(options);
    options.control.cancelled = cancel_now;
    cancel_flag = 1;
    status = exr_sideload_import_file(library, EXR_DOCX, cancel_path, NULL, &options, &result, &error);
    cancel_flag = 0;
    after = count_books(library, &after_ok);
    report("cancel_before_commit_zero_rows",
        status == EXR_CANCELLED && !result.book_id && !result.created && after_ok && after == before,
        "memory route status %d created %d, books %zu -> %zu", (int)status, result.created, before, after);
  }
  if (!join_path(cancel_path, sizeof(cancel_path), work, "local/cancelled.epub") ||
      !write_file(cancel_path, epub->bytes, epub->size)) {
    report("cancel_before_commit_stream_zero_rows", 0, "cannot stage the cancellation input");
  } else {
    exr_sideload_options options = {0};
    exr_sideload_result result = {sizeof(result), 0, 0};
    exr_status status;
    int after_ok = 0;
    size_t after;
    options.struct_size = sizeof(options);
    options.control.cancelled = cancel_now;
    cancel_flag = 1;
    status = exr_sideload_import_file(library, EXR_EPUB, cancel_path, NULL, &options, &result, &error);
    cancel_flag = 0;
    after = count_books(library, &after_ok);
    report("cancel_before_commit_stream_zero_rows",
        status == EXR_CANCELLED && !result.book_id && !result.created && after_ok && after == before,
        "stream route status %d created %d, books %zu -> %zu", (int)status, result.created, before, after);
  }

  if (!join_path(export_path, sizeof(export_path), work, "exports/local-epub.original")) {
    report("original_export_matches_sha256", 0, "export path too long");
    report("original_export_atomic_no_overwrite", 0, "export path too long");
    return;
  }
  remove_path(export_path);
  {
    char hex[65], note[S06_DETAIL];
    size_t exported_size = 0;
    int ok = export_matches(library, epub->id, export_path, epub->bytes, epub->size,
        detail, sizeof(detail));
    if (ok && sha256_of_file(export_path, hex, &exported_size))
      snprintf(note, sizeof(note), "%s, sha256 %s", detail, hex);
    else
      snprintf(note, sizeof(note), "%s", detail);
    report("original_export_matches_sha256", ok, "%s", note);
  }
  {
    exr_sideload_options options = {0};
    uint64_t written = 0;
    unsigned char *kept = NULL;
    size_t kept_size = 0;
    exr_status status;
    char hex_before[65], hex_after[65];
    int ok;
    options.struct_size = sizeof(options);
    sha256_of_file(export_path, hex_before, NULL);
    status = exr_sideload_export_original(library, epub->id, export_path, &options, &written, &error);
    ok = status != EXR_OK && written == 0 && read_file(export_path, &kept, &kept_size) &&
         kept_size == epub->size && !memcmp(kept, epub->bytes, epub->size);
    free(kept);
    sha256_of_file(export_path, hex_after, NULL);
    report("original_export_atomic_no_overwrite", ok && !strcmp(hex_before, hex_after),
        "second export status %d (%s), existing file sha256 %s -> %s",
        (int)status, error.message, hex_before, hex_after);
  }
}

static void reopen_group(const char *work, held_fixture *epub, size_t expected_books) {
  char library_path[S06_PATH], detail[S06_DETAIL];
  exr_library *reopened = NULL;
  exr_book *books = NULL;
  size_t count = 0;
  int count_ok, original_ok;
  if (!join_path(library_path, sizeof(library_path), work, "s06-library.sqlite")) {
    report("committed_result_survives_reopen", 0, "work path too long");
    return;
  }
  exr_library_close(library);
  library = NULL;
  if (exr_library_open(library_path, &reopened, &error) != EXR_OK) {
    report("committed_result_survives_reopen", 0, "reopen failed: %s", error.message);
    return;
  }
  count_ok = exr_library_books(reopened, NULL, &books, &count, &error) == EXR_OK;
  exr_books_free(books, count);
  original_ok = source_matches(reopened, epub->id, epub->bytes, epub->size, detail, sizeof(detail));
  report("committed_result_survives_reopen",
      count_ok && count == expected_books && original_ok,
      "%zu books reopened (expected %zu), committed original %s", count, expected_books, detail);
  exr_library_close(reopened);
}

/* -------------------------------------------------------------------- main -- */
static int usage(void) {
  fprintf(stderr, "usage: s06-matrix-probe --fixtures DIR --work DIR --platform NAME [--cloud DIR]\n");
  return 2;
}

int main(int argc, char **argv) {
  held_fixture epub, fb2, cbz, pdf, docx;
  char library_path[S06_PATH], sub[S06_PATH];
  char escaped_work[4096], escaped_fixtures[4096], escaped_cloud[4096];
  int index;
  size_t expected_books = 0;
  int count_ok = 0;

  for (index = 1; index < argc; index++) {
    const char *value = index + 1 < argc ? argv[index + 1] : NULL;
    if (!strcmp(argv[index], "--fixtures") && value) { fixture_dir = value; index++; }
    else if (!strcmp(argv[index], "--work") && value) { work_dir = value; index++; }
    else if (!strcmp(argv[index], "--platform") && value) { platform_name = value; index++; }
    else if (!strcmp(argv[index], "--cloud") && value) { cloud_dir = value; index++; }
    else return usage();
  }
  if (!fixture_dir || !work_dir || !platform_name) return usage();

  memset(&epub, 0, sizeof(epub));
  memset(&fb2, 0, sizeof(fb2));
  memset(&cbz, 0, sizeof(cbz));
  memset(&pdf, 0, sizeof(pdf));
  memset(&docx, 0, sizeof(docx));
  if (!join_path(sub, sizeof(sub), work_dir, "local") || !make_dir(work_dir) ||
      !make_dir(sub) || !join_path(sub, sizeof(sub), work_dir, "handoff") || !make_dir(sub) ||
      !join_path(sub, sizeof(sub), work_dir, "exports") || !make_dir(sub) ||
      !join_path(sub, sizeof(sub), work_dir, "duplicate") || !make_dir(sub) ||
      !join_path(sub, sizeof(sub), work_dir, "bad") || !make_dir(sub)) {
    fprintf(stderr, "cannot prepare the work directory %s\n", work_dir);
    return 2;
  }

  json_escape(work_dir, escaped_work, sizeof(escaped_work));
  json_escape(fixture_dir, escaped_fixtures, sizeof(escaped_fixtures));
  escaped_cloud[0] = 0;
  if (cloud_dir) json_escape(cloud_dir, escaped_cloud, sizeof(escaped_cloud));
  printf("{\"case\":\"__probe\",\"platform\":\"%s\",\"fixtures\":\"%s\",\"work\":\"%s\",\"cloud\":\"%s\"}\n",
      platform_name, escaped_fixtures, escaped_work, escaped_cloud);
  fflush(stdout);

  if (!load_fixture("sample.epub", &epub) || !load_fixture("sample.fb2", &fb2) ||
      !load_fixture("comic.cbz", &cbz) || !load_fixture("pdf-public.pdf", &pdf) ||
      !load_fixture("sample.docx", &docx)) {
    fprintf(stderr, "cannot read the pinned fixtures under %s\n", fixture_dir);
    return 2;
  }

  formats_group(work_dir);

  if (!join_path(library_path, sizeof(library_path), work_dir, "s06-library.sqlite")) return 2;
  remove_path(library_path);
  if (exr_library_open(library_path, &library, &error) != EXR_OK) {
    fprintf(stderr, "exr_library_open failed: %s\n", error.message);
    return 2;
  }

  local_file_group(work_dir, &epub, &fb2, &cbz);
  if (epub.id > 0) {
    exr_book *books = NULL;
    size_t count = 0;
    if (exr_library_books(library, NULL, &books, &count, &error) == EXR_OK) {
      size_t at;
      for (at = 0; at < count; at++) {
        if (books[at].id != epub.id) continue;
        books[at].position = 7;
        books[at].favorite = 1;
        if (exr_library_update(library, &books[at], &error) != EXR_OK)
          fprintf(stderr, "progress capture failed: %s\n", error.message);
      }
      exr_books_free(books, count);
    }
    {
      exr_note note = {0};
      int64_t note_id = 0;
      note.book_id = epub.id;
      note.start = 0;
      note.end = 5;
      note.text = "S06 keep this note";
      if (exr_library_note(library, &note, &note_id, &error) != EXR_OK)
        fprintf(stderr, "note capture failed: %s\n", error.message);
    }
  }

  handoff_group(work_dir, &epub);
  cloud_group(&epub, &pdf);
  duplicate_group(work_dir, &epub);
  bad_group(work_dir, &epub);
  identity_group(work_dir, &epub, &docx);
  expected_books = count_books(library, &count_ok);
  reopen_group(work_dir, &epub, expected_books);

  printf("{\"case\":\"__summary\",\"platform\":\"%s\",\"failed\":%u,\"cases\":%u}\n",
      platform_name, failure_count, case_count);
  fflush(stdout);
  return failure_count == 0 ? 0 : 1;
}
