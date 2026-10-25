/* SPDX-License-Identifier: MIT
 * Portable acceptance suite for the installed desktop drop package: strict
 * UTF-8/UTF-16 handling, URI decoding, item classification, hard limits,
 * cancellation, reentrancy and concurrent parsing. It runs against a tree the
 * suite creates under the current directory; no user file is touched.
 */
#include <exr_desktop_drop.h>
#include "report.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#include <direct.h>
#include <process.h>
#include <windows.h>
#define SEP_CHAR '\\'
#define mkdir_one(p) _mkdir(p)
#else
#include <pthread.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#define SEP_CHAR '/'
#define mkdir_one(p) mkdir(p, 0700)
#endif

static char base_dir[1200];

typedef struct {
  exr_drop_item_status status;
  const char *path; /* NULL means "no path expected" */
} spec;

static void join_native(char *out, size_t room, const char *leaf) {
  snprintf(out, room, "%s%c%s", base_dir, SEP_CHAR, leaf);
}

static void to_uri(const char *native, char *out, size_t room) {
  size_t used, index;
#ifdef _WIN32
  const char *prefix = "file:///";
#else
  const char *prefix = "file://";
#endif
  used = (size_t)snprintf(out, room, "%s", prefix);
  for (index = 0; native[index] && used + 2 < room; index++)
    out[used++] = native[index] == '\\' ? '/' : native[index];
  out[used] = 0;
}

static int path_is(const exr_drop_item *item, const char *expected) {
  return item->path && strcmp(item->path, expected) == 0;
}

static void prepare_tree(void) {
  char leaf[1300];
  FILE *file;
  size_t length;
#ifdef _WIN32
  if (!_getcwd(base_dir, sizeof(base_dir))) base_dir[0] = 0;
  for (char *p = base_dir; *p; p++)
    if (*p == '/') *p = '\\';
#else
  if (!getcwd(base_dir, sizeof(base_dir))) base_dir[0] = 0;
#endif
  length = strlen(base_dir);
  snprintf(base_dir + length, sizeof(base_dir) - length, "%cexr-drop-check", SEP_CHAR);
  mkdir_one(base_dir);
  join_native(leaf, sizeof(leaf), "a.txt");
  file = fopen(leaf, "wb");
  if (file) {
    fputs("x", file);
    fclose(file);
  }
  join_native(leaf, sizeof(leaf), "sub");
  mkdir_one(leaf);
}

/* Set to 1 around the gnome-copied-files cases so the shared helpers parse the
   gnome flavour; every other case uses text/uri-list. */
static int g_gnome;

static exr_drop_status parse_list(const char *payload, size_t size, exr_drop_request **out) {
  return g_gnome ? exr_drop_request_from_gnome_files(payload, size, EXR_DROP_ORIGIN_TEXT, NULL, out)
                 : exr_drop_request_from_uri_list(payload, size, EXR_DROP_ORIGIN_TEXT, NULL, out);
}

static void expect_items(const char *name, exr_drop_status want_status, const char *payload, size_t size,
    const spec *specs, size_t spec_count, size_t duplicates, size_t overflow) {
  exr_drop_request *request = NULL;
  exr_drop_status status = parse_list(payload, size, &request);
  char detail[480];
  exr_drop_request_info info;
  size_t index;
  if (status != want_status) {
    snprintf(detail, sizeof(detail), "status=%s want=%s", exr_drop_status_name(status),
        exr_drop_status_name(want_status));
    report_fail(name, detail);
    exr_drop_request_release(request);
    return;
  }
  if (status != EXR_DROP_OK) {
    report_expect(name, request == NULL, request ? "request not null" : exr_drop_status_name(status));
    exr_drop_request_release(request);
    return;
  }
  memset(&info, 0, sizeof(info));
  info.struct_size = sizeof(info);
  if (exr_drop_request_get_info(request, &info) != EXR_DROP_OK) {
    report_fail(name, "get_info failed");
    exr_drop_request_release(request);
    return;
  }
  if (info.item_count != spec_count) {
    snprintf(detail, sizeof(detail), "item_count=%zu want=%zu", info.item_count, spec_count);
    report_fail(name, detail);
    exr_drop_request_release(request);
    return;
  }
  if (info.duplicate_count != duplicates || info.overflow_count != overflow
      || info.truncated != (overflow != 0)) {
    snprintf(detail, sizeof(detail), "duplicates=%zu/%zu overflow=%zu/%zu truncated=%d", info.duplicate_count,
        duplicates, info.overflow_count, overflow, info.truncated);
    report_fail(name, detail);
    exr_drop_request_release(request);
    return;
  }
  for (index = 0; index < spec_count; index++) {
    exr_drop_item item;
    memset(&item, 0, sizeof(item));
    item.struct_size = sizeof(item);
    if (exr_drop_request_get_item(request, index, &item) != EXR_DROP_OK) {
      report_fail(name, "get_item failed");
      exr_drop_request_release(request);
      return;
    }
    if (item.status != specs[index].status) {
      snprintf(detail, sizeof(detail), "item%zu status=%s want=%s", index,
          exr_drop_item_status_name(item.status), exr_drop_item_status_name(specs[index].status));
      report_fail(name, detail);
      exr_drop_request_release(request);
      return;
    }
    if (specs[index].path) {
      if (!path_is(&item, specs[index].path)) {
        snprintf(detail, sizeof(detail), "item%zu path=%s want=%s", index, item.path ? item.path : "(null)",
            specs[index].path);
        report_fail(name, detail);
        exr_drop_request_release(request);
        return;
      }
    } else if (item.path) {
      snprintf(detail, sizeof(detail), "item%zu unexpected path=%s", index, item.path);
      report_fail(name, detail);
      exr_drop_request_release(request);
      return;
    }
  }
  {
    char ok[64];
    snprintf(ok, sizeof(ok), "items=%zu", spec_count);
    report_pass(name, ok);
  }
  exr_drop_request_release(request);
}

static void expect_status(const char *name, exr_drop_status want, const char *payload, size_t size) {
  exr_drop_request *request = NULL;
  exr_drop_status status = parse_list(payload, size, &request);
  char detail[256];
  if (status == want && request == NULL) {
    report_pass(name, exr_drop_status_name(status));
    return;
  }
  snprintf(detail, sizeof(detail), "status=%s want=%s request=%s", exr_drop_status_name(status),
      exr_drop_status_name(want), request ? "set" : "null");
  report_fail(name, detail);
  exr_drop_request_release(request);
}

/* ---- cancellation and reentrancy ------------------------------------- */
static int cancel_after_one(void *context) {
  int *seen = (int *)context;
  (*seen)++;
  return *seen > 1;
}

static int g_reentrant_ok;
static int reentrant_cancel(void *context) {
  exr_drop_request *inner = NULL;
  exr_drop_status status;
  (void)context;
  status = exr_drop_request_from_uri_list("https://example.invalid/x", 25, EXR_DROP_ORIGIN_TEXT, NULL, &inner);
  g_reentrant_ok = status == EXR_DROP_OK && inner != NULL;
  if (inner) {
    exr_drop_request_info info;
    memset(&info, 0, sizeof(info));
    info.struct_size = sizeof(info);
    exr_drop_request_get_info(inner, &info);
    g_reentrant_ok = g_reentrant_ok && info.item_count == 1;
  }
  exr_drop_request_release(inner);
  return 1;
}

/* ---- worker thread --------------------------------------------------- */
typedef struct {
  int failures;
} worker_state;

#ifdef _WIN32
static unsigned __stdcall parse_worker(void *arg)
#else
static void *parse_worker(void *arg)
#endif
{
  worker_state *state = (worker_state *)arg;
  int iteration;
  for (iteration = 0; iteration < 200; iteration++) {
    exr_drop_request *request = NULL;
    exr_drop_request_info info;
    exr_drop_item item;
    if (exr_drop_request_from_uri_list("trash:///x.epub", 14, EXR_DROP_ORIGIN_TEXT, NULL, &request)
        != EXR_DROP_OK) {
      state->failures++;
      break;
    }
    memset(&info, 0, sizeof(info));
    info.struct_size = sizeof(info);
    memset(&item, 0, sizeof(item));
    item.struct_size = sizeof(item);
    if (exr_drop_request_get_info(request, &info) != EXR_DROP_OK || info.item_count != 1
        || exr_drop_request_get_item(request, 0, &item) != EXR_DROP_OK
        || item.status != EXR_DROP_ITEM_VIRTUAL)
      state->failures++;
    exr_drop_request_release(request);
  }
  return
#ifdef _WIN32
      0;
#else
      NULL;
#endif
}

int main(void) {
  char uri[2200], native[1300], payload[4200];
  spec one[1];
  spec many[256];
  exr_drop_request *request = NULL;
  exr_drop_request_info info;
  exr_drop_control control;
  size_t index;
  int cancelled_seen = 0;
  worker_state state = {0};

  prepare_tree();

  /* ---- local files, directories and missing paths ------------------- */
  join_native(native, sizeof(native), "a.txt");
  to_uri(native, uri, sizeof(uri));
  one[0].status = EXR_DROP_ITEM_FILE;
  one[0].path = native;
  expect_items("uri_file_existing", EXR_DROP_OK, uri, strlen(uri), one, 1, 0, 0);

  join_native(native, sizeof(native), "sub");
  to_uri(native, uri, sizeof(uri));
  one[0].status = EXR_DROP_ITEM_DIRECTORY;
  one[0].path = native;
  expect_items("uri_directory_not_recursed", EXR_DROP_OK, uri, strlen(uri), one, 1, 0, 0);

  join_native(native, sizeof(native), "missing.epub");
  to_uri(native, uri, sizeof(uri));
  one[0].status = EXR_DROP_ITEM_MISSING;
  one[0].path = native;
  expect_items("uri_missing_path", EXR_DROP_OK, uri, strlen(uri), one, 1, 0, 0);

  join_native(native, sizeof(native), "exr drop \xe4\xb8\xad\xe6\x96\x87.epub");
  one[0].status = EXR_DROP_ITEM_MISSING;
  one[0].path = native;
  {
#ifdef _WIN32
    size_t used = (size_t)snprintf(payload, sizeof(payload), "file:///");
#else
    size_t used = (size_t)snprintf(payload, sizeof(payload), "file://");
#endif
    for (index = 0; native[index] && used + 8 < sizeof(payload); index++) {
      unsigned char c = (unsigned char)native[index];
      if (c == '\\') {
        payload[used++] = '/';
        continue;
      }
      if (c == ' ' || c >= 0x80) used += (size_t)snprintf(payload + used, sizeof(payload) - used, "%%%02X", c);
      else payload[used++] = (char)c;
    }
    payload[used] = 0;
    expect_items("uri_percent_encoded_utf8", EXR_DROP_OK, payload, used, one, 1, 0, 0);
  }
  {
    char localhost_uri[2300];
    join_native(native, sizeof(native), "a.txt");
    to_uri(native, uri, sizeof(uri));
    one[0].status = EXR_DROP_ITEM_FILE;
    one[0].path = native;
    snprintf(localhost_uri, sizeof(localhost_uri), "file://localhost%s", uri + 7);
    expect_items("uri_localhost_is_local", EXR_DROP_OK, localhost_uri, strlen(localhost_uri), one, 1, 0, 0);
  }

  /* ---- remote and virtual ------------------------------------------- */
  one[0].status = EXR_DROP_ITEM_REMOTE_HOST;
  one[0].path = NULL;
  expect_items("uri_remote_host", EXR_DROP_OK, "file://server/share/x.epub",
      strlen("file://server/share/x.epub"), one, 1, 0, 0);
  one[0].status = EXR_DROP_ITEM_REMOTE_URL;
  expect_items("uri_remote_url_https", EXR_DROP_OK, "https://example.invalid/x.epub",
      strlen("https://example.invalid/x.epub"), one, 1, 0, 0);
  expect_items("uri_remote_url_smb", EXR_DROP_OK, "smb://nas/books/x.epub",
      strlen("smb://nas/books/x.epub"), one, 1, 0, 0);
  one[0].status = EXR_DROP_ITEM_VIRTUAL;
  expect_items("uri_virtual_trash", EXR_DROP_OK, "trash:///x.epub", strlen("trash:///x.epub"), one, 1, 0, 0);
  expect_items("uri_virtual_mtp", EXR_DROP_OK, "mtp://device/1.epub", strlen("mtp://device/1.epub"), one, 1, 0,
      0);

  /* ---- rejected entries -------------------------------------------- */
  one[0].status = EXR_DROP_ITEM_INVALID;
  one[0].path = NULL;
  expect_items("uri_bad_percent_hex", EXR_DROP_OK, "file:///a%ZZ.epub", strlen("file:///a%ZZ.epub"), one, 1, 0,
      0);
  expect_items("uri_short_percent", EXR_DROP_OK, "file:///a%4", strlen("file:///a%4"), one, 1, 0, 0);
  expect_items("uri_percent_nul", EXR_DROP_OK, "file:///a%00b", strlen("file:///a%00b"), one, 1, 0, 0);
  expect_items("uri_query_rejected", EXR_DROP_OK, "file:///a?x=1", strlen("file:///a?x=1"), one, 1, 0, 0);
  expect_items("uri_fragment_rejected", EXR_DROP_OK, "file:///a#frag", strlen("file:///a#frag"), one, 1, 0, 0);
  expect_items("uri_space_rejected", EXR_DROP_OK, "file:///a b.epub", strlen("file:///a b.epub"), one, 1, 0,
      0);
  expect_items("uri_relative_rejected", EXR_DROP_OK, "relative.epub", strlen("relative.epub"), one, 1, 0, 0);
  expect_items("uri_control_byte_rejected", EXR_DROP_OK, "file:///a\x01.epub", strlen("file:///a\x01.epub"),
      one, 1, 0, 0);
  expect_items("uri_scheme_too_short", EXR_DROP_OK, "f:/x", strlen("f:/x"), one, 1, 0, 0);
  one[0].status = EXR_DROP_ITEM_BAD_ENCODING;
  expect_items("uri_percent_bad_utf8", EXR_DROP_OK, "file:///a%FF.epub", strlen("file:///a%FF.epub"), one, 1,
      0, 0);
  expect_items("uri_percent_overlong_utf8", EXR_DROP_OK, "file:///a%C0%AF.epub",
      strlen("file:///a%C0%AF.epub"), one, 1, 0, 0);
  expect_items("uri_percent_surrogate_utf8", EXR_DROP_OK, "file:///a%ED%A0%80.epub",
      strlen("file:///a%ED%A0%80.epub"), one, 1, 0, 0);
  expect_items("uri_utf8_raw_invalid", EXR_DROP_OK, "file:///a\xC3.epub", strlen("file:///a\xC3.epub"), one, 1,
      0, 0);

  /* ---- list framing ------------------------------------------------- */
  join_native(native, sizeof(native), "a.txt");
  to_uri(native, uri, sizeof(uri));
  one[0].status = EXR_DROP_ITEM_FILE;
  one[0].path = native;
  snprintf(payload, sizeof(payload), "\xEF\xBB\xBF# comment\r\n\r\n%s\r\n", uri);
  expect_items("list_bom_comment_blank", EXR_DROP_OK, payload, strlen(payload), one, 1, 0, 0);
  snprintf(payload, sizeof(payload), "%s\r%s\r\n%s", uri, uri, uri);
  expect_items("list_cr_crlf_duplicates", EXR_DROP_OK, payload, strlen(payload), one, 1, 2, 0);
  expect_status("list_empty_is_empty", EXR_DROP_EMPTY, "", 0);
  expect_status("list_blank_only_is_empty", EXR_DROP_EMPTY, " \r\n\t\r\n# only\r\n",
      strlen(" \r\n\t\r\n# only\r\n"));
  expect_status("argument_null_with_size", EXR_DROP_ARGUMENT, NULL, 5);
  {
    char gnome[2300];
    g_gnome = 1;
    snprintf(gnome, sizeof(gnome), "copy\n%s", uri);
    expect_items("gnome_copy_prefix", EXR_DROP_OK, gnome, strlen(gnome), one, 1, 0, 0);
    snprintf(gnome, sizeof(gnome), "cut\r\n%s\r\n", uri);
    expect_items("gnome_cut_prefix", EXR_DROP_OK, gnome, strlen(gnome), one, 1, 0, 0);
    g_gnome = 0;
  }

  /* ---- limits ------------------------------------------------------- */
  {
    char *large = (char *)malloc(EXR_DROP_MAX_INPUT_BYTES + 32);
    if (!large) {
      report_skip("limit_payload_too_large", "allocation failed");
    } else {
      memset(large, 'a', EXR_DROP_MAX_INPUT_BYTES + 16);
      large[EXR_DROP_MAX_INPUT_BYTES + 16] = 0;
      expect_status("limit_payload_too_large", EXR_DROP_TOO_LARGE, large, EXR_DROP_MAX_INPUT_BYTES + 16);
      free(large);
    }
  }
  {
    size_t used = 0;
    char *list = (char *)malloc(64 * 400);
    if (!list) {
      report_skip("limit_item_cap", "allocation failed");
    } else {
      for (index = 0; index < 300; index++) {
        used += (size_t)snprintf(list + used, 64, "https://example.invalid/%03zu\n", index);
        if (index < 256) {
          many[index].status = EXR_DROP_ITEM_REMOTE_URL;
          many[index].path = NULL;
        }
      }
      expect_items("limit_item_cap", EXR_DROP_OK, list, used, many, 256, 0, 44);
      free(list);
    }
  }
  {
    char *long_native = (char *)malloc(EXR_DROP_MAX_PATH_BYTES + 200);
    char *long_uri = (char *)malloc(EXR_DROP_MAX_PATH_BYTES + 300);
    if (!long_native || !long_uri) {
      report_skip("limit_path_too_long", "allocation failed");
    } else {
      size_t used = 0;
#ifdef _WIN32
      long_native[used++] = 'C';
      long_native[used++] = ':';
      long_native[used++] = '\\';
#else
      long_native[used++] = '/';
#endif
      while (used < EXR_DROP_MAX_PATH_BYTES + 100) long_native[used++] = 'a';
      long_native[used] = 0;
      to_uri(long_native, long_uri, EXR_DROP_MAX_PATH_BYTES + 300);
      one[0].status = EXR_DROP_ITEM_TOO_LONG;
      one[0].path = NULL;
      expect_items("limit_path_too_long", EXR_DROP_OK, long_uri, strlen(long_uri), one, 1, 0, 0);
    }
    free(long_native);
    free(long_uri);
  }

  /* ---- cancellation and argument guards ----------------------------- */
  control.struct_size = sizeof(control);
  control.cancelled = cancel_after_one;
  control.context = &cancelled_seen;
  {
    snprintf(payload, sizeof(payload), "%s\n%s\n%s\n", uri, uri, uri);
    request = NULL;
    if (exr_drop_request_from_uri_list(payload, strlen(payload), EXR_DROP_ORIGIN_TEXT, &control, &request)
            == EXR_DROP_CANCELLED
        && request == NULL)
      report_pass("cancel_after_first_entry", "cancelled with no request");
    else {
      report_fail("cancel_after_first_entry", "cancellation not reported");
      exr_drop_request_release(request);
    }
  }
  control.cancelled = reentrant_cancel;
  control.context = NULL;
  request = NULL;
  if (exr_drop_request_from_uri_list(uri, strlen(uri), EXR_DROP_ORIGIN_TEXT, &control, &request)
          == EXR_DROP_CANCELLED
      && request == NULL && g_reentrant_ok)
    report_pass("reentrant_parse_in_cancel", "nested parse inside the poll is safe");
  else {
    report_fail("reentrant_parse_in_cancel", "nested parse or cancellation changed the outcome");
    exr_drop_request_release(request);
  }
  control.struct_size = sizeof(control) - 1;
  control.cancelled = NULL;
  request = NULL;
  if (exr_drop_request_from_uri_list(uri, strlen(uri), EXR_DROP_ORIGIN_TEXT, &control, &request) == EXR_DROP_ARGUMENT
      && request == NULL)
    report_pass("control_struct_size_rejected", "wrong struct_size refused");
  else
    report_fail("control_struct_size_rejected", "wrong struct_size accepted");
  request = NULL;
  if (exr_drop_request_from_uri_list(uri, strlen(uri), (exr_drop_origin)0, NULL, &request) == EXR_DROP_ARGUMENT)
    report_pass("origin_range_rejected", "origin 0 refused");
  else
    report_fail("origin_range_rejected", "origin 0 accepted");

  /* ---- UTF-16 ------------------------------------------------------- */
  {
    uint16_t units[64];
    static const char head[] = "C:\\exr\\a.epub";
    size_t used = 0;
    for (index = 0; head[index]; index++) units[used++] = (uint16_t)(unsigned char)head[index];
    units[used++] = 0xD800;
    units[used] = 0;
    request = NULL;
    if (exr_drop_request_from_utf16(units, used, EXR_DROP_UTF16_NUL_LIST, EXR_DROP_ORIGIN_TEXT, NULL, &request)
        == EXR_DROP_OK) {
      memset(&info, 0, sizeof(info));
      info.struct_size = sizeof(info);
      exr_drop_request_get_info(request, &info);
      {
        exr_drop_item item;
        memset(&item, 0, sizeof(item));
        item.struct_size = sizeof(item);
        exr_drop_request_get_item(request, 0, &item);
        report_expect("utf16_unpaired_surrogate",
            info.item_count == 1 && item.status == EXR_DROP_ITEM_BAD_ENCODING, "one rejected entry");
      }
      exr_drop_request_release(request);
    } else {
      report_fail("utf16_unpaired_surrogate", "parse failed");
    }
  }
  {
    uint16_t units[8] = {'h', 't', 't', 'p', 's', ':', '/', 0};
    request = NULL;
    if (exr_drop_request_from_utf16(units, 7, EXR_DROP_UTF16_LINES, EXR_DROP_ORIGIN_TEXT, NULL, &request)
        == EXR_DROP_OK) {
      exr_drop_request_release(request);
      report_pass("utf16_lines_basic", "single line accepted");
    } else {
      report_fail("utf16_lines_basic", "parse failed");
    }
  }
  {
    uint16_t units[64];
#ifdef _WIN32
    static const char head[] = "C:\\astral-";
    const char *expected = "C:\\astral-\xF0\x9D\x9B\x80.e";
#else
    static const char head[] = "/tmp/astral-";
    const char *expected = "/tmp/astral-\xF0\x9D\x9B\x80.e";
#endif
    size_t used = 0;
    for (index = 0; head[index]; index++) units[used++] = (uint16_t)(unsigned char)head[index];
    units[used++] = 0xD835; /* U+1D6C0 */
    units[used++] = 0xDEC0;
    units[used++] = (uint16_t)'.';
    units[used++] = (uint16_t)'e';
    units[used++] = 0;
    request = NULL;
    if (exr_drop_request_from_utf16(units, used, EXR_DROP_UTF16_NUL_LIST, EXR_DROP_ORIGIN_TEXT, NULL, &request)
        == EXR_DROP_OK) {
      exr_drop_item item;
      memset(&item, 0, sizeof(item));
      item.struct_size = sizeof(item);
      exr_drop_request_get_item(request, 0, &item);
      report_expect("utf16_surrogate_pair",
          item.status == EXR_DROP_ITEM_MISSING && item.path && strcmp(item.path, expected) == 0,
          item.path ? item.path : "no path");
      exr_drop_request_release(request);
    } else {
      report_fail("utf16_surrogate_pair", "parse failed");
    }
  }
  {
    uint16_t units[2] = {0x41, 0};
    request = NULL;
    if (exr_drop_request_from_utf16(units, 1, (exr_drop_utf16_layout)9, EXR_DROP_ORIGIN_TEXT, NULL, &request)
        == EXR_DROP_ARGUMENT)
      report_pass("utf16_layout_rejected", "layout 9 refused");
    else
      report_fail("utf16_layout_rejected", "layout 9 accepted");
  }
  {
    size_t units_count = EXR_DROP_MAX_INPUT_BYTES / 2 + 1;
    uint16_t *units = (uint16_t *)calloc(units_count, sizeof(uint16_t));
    if (!units) {
      report_skip("utf16_payload_too_large", "allocation failed");
    } else {
      request = NULL;
      if (exr_drop_request_from_utf16(units, units_count, EXR_DROP_UTF16_NUL_LIST, EXR_DROP_ORIGIN_TEXT, NULL,
              &request) == EXR_DROP_TOO_LARGE)
        report_pass("utf16_payload_too_large", "budget enforced");
      else
        report_fail("utf16_payload_too_large", "budget accepted");
      free(units);
    }
  }

  /* ---- UTF-8 array entry -------------------------------------------- */
  {
    const char *entries[2];
    join_native(native, sizeof(native), "a.txt");
    entries[0] = native;
    entries[1] = "https://example.invalid/b.epub";
    request = NULL;
    if (exr_drop_request_from_utf8_list(entries, 2, EXR_DROP_ORIGIN_TEXT, NULL, &request) == EXR_DROP_OK) {
      memset(&info, 0, sizeof(info));
      info.struct_size = sizeof(info);
      exr_drop_request_get_info(request, &info);
      report_expect("utf8_list_two_entries",
          info.item_count == 2 && info.file_count == 1 && info.origin == EXR_DROP_ORIGIN_TEXT,
          "file plus remote URL");
      exr_drop_request_release(request);
    } else {
      report_fail("utf8_list_two_entries", "parse failed");
    }
    {
      const char *bad[1] = {NULL};
      request = NULL;
      if (exr_drop_request_from_utf8_list(bad, 1, EXR_DROP_ORIGIN_TEXT, NULL, &request) == EXR_DROP_ARGUMENT)
        report_pass("utf8_list_null_entry", "NULL entry refused");
      else
        report_fail("utf8_list_null_entry", "NULL entry accepted");
    }
    {
      const char *broken[1] = {"file:///a\xC3.epub"};
      request = NULL;
      if (exr_drop_request_from_utf8_list(broken, 1, EXR_DROP_ORIGIN_TEXT, NULL, &request) == EXR_DROP_OK) {
        exr_drop_item item;
        memset(&item, 0, sizeof(item));
        item.struct_size = sizeof(item);
        exr_drop_request_get_item(request, 0, &item);
        report_expect("utf8_list_bad_encoding_item", item.status == EXR_DROP_ITEM_BAD_ENCODING,
            "invalid UTF-8 item");
        exr_drop_request_release(request);
      } else {
        report_fail("utf8_list_bad_encoding_item", "parse failed");
      }
    }
  }

  /* ---- accessors ----------------------------------------------------- */
  {
    exr_drop_item item;
    request = NULL;
    exr_drop_request_from_uri_list(uri, strlen(uri), EXR_DROP_ORIGIN_TEXT, NULL, &request);
    memset(&info, 0, sizeof(info));
    info.struct_size = sizeof(info) - 1;
    report_expect("get_info_struct_size", exr_drop_request_get_info(request, &info) == EXR_DROP_ARGUMENT,
        "wrong struct_size refused");
    memset(&item, 0, sizeof(item));
    item.struct_size = sizeof(item);
    report_expect("get_item_out_of_range", exr_drop_request_get_item(request, 99, &item) == EXR_DROP_ARGUMENT,
        "index 99 refused");
    memset(&item, 0, sizeof(item));
    report_expect("get_item_struct_size", exr_drop_request_get_item(request, 0, &item) == EXR_DROP_ARGUMENT,
        "struct_size 0 refused");
    memset(&info, 0, sizeof(info));
    info.struct_size = sizeof(info);
    report_expect("get_info_null_request", exr_drop_request_get_info(NULL, &info) == EXR_DROP_ARGUMENT,
        "NULL request refused");
    exr_drop_request_release(request);
  }
  exr_drop_request_release(NULL);
  report_pass("release_null_is_safe", "no crash");

  /* ---- thread safety ------------------------------------------------- */
  {
#ifdef _WIN32
    HANDLE thread = (HANDLE)_beginthreadex(NULL, 0, parse_worker, &state, 0, NULL);
    if (!thread) {
      report_skip("concurrent_parse", "thread creation failed");
    } else {
      WaitForSingleObject(thread, INFINITE);
      CloseHandle(thread);
      report_expect("concurrent_parse", state.failures == 0, "200 parses on a worker thread");
    }
#else
    pthread_t thread;
    if (pthread_create(&thread, NULL, parse_worker, &state) != 0) {
      report_skip("concurrent_parse", "thread creation failed");
    } else {
      pthread_join(thread, NULL);
      report_expect("concurrent_parse", state.failures == 0, "200 parses on a worker thread");
    }
#endif
  }

  /* ---- status names -------------------------------------------------- */
  {
    int ok = 1;
    int status;
    for (status = EXR_DROP_OK; status <= (int)EXR_DROP_WRONG_THREAD; status++)
      if (!exr_drop_status_name((exr_drop_status)status)
          || strcmp(exr_drop_status_name((exr_drop_status)status), "unknown") == 0)
        ok = 0;
    for (status = EXR_DROP_ITEM_FILE; status <= (int)EXR_DROP_ITEM_NOT_REGULAR; status++)
      if (!exr_drop_item_status_name((exr_drop_item_status)status)
          || strcmp(exr_drop_item_status_name((exr_drop_item_status)status), "unknown") == 0)
        ok = 0;
    report_expect("status_names_complete", ok, "every code has a name");
  }

  return report_summary("portable");
}
