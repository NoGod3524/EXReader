/* SPDX-License-Identifier: MIT */
/* Installed-package consumer (C++): the SDK-owner phase. It preserves a staged download,
   imports it through the public sideload route and proves that the network phase never
   claimed readability on its own. */
#include "reader_opds_import.h"
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

namespace {

FILE *g_out = nullptr;
int g_failures = 0;

void json_escape(FILE *f, const char *text) {
  for (; text && *text; text++) {
    unsigned char ch = static_cast<unsigned char>(*text);
    if (ch == '"' || ch == '\\') std::fprintf(f, "\\%c", ch);
    else if (ch == '\n') std::fputs("\\n", f);
    else if (ch == '\r') std::fputs("\\r", f);
    else if (ch == '\t') std::fputs("\\t", f);
    else if (ch < 0x20) std::fprintf(f, "\\u%04x", ch);
    else std::fputc(ch, f);
  }
}

void record(const char *id, bool ok, const char *detail) {
  std::fprintf(g_out, "{\"id\":\"%s\",\"ok\":%s,\"detail\":\"", id, ok ? "true" : "false");
  json_escape(g_out, detail);
  std::fputs("\"}\n", g_out);
  std::fflush(g_out);
  if (!ok) g_failures++;
}

void recordf(const char *id, bool ok, const char *fmt, ...) {
  char buffer[900];
  va_list ap;
  va_start(ap, fmt);
  std::vsnprintf(buffer, sizeof buffer, fmt, ap);
  va_end(ap);
  record(id, ok, buffer);
}

int cancelled_now(void *context) { return *static_cast<int *>(context); }

bool acquire(reader_opds_browser *browser, const char *url, size_t pick, reader_opds_acquired *staged,
             opds_error *error, bool replace = false) {
  reader_opds_page *page = nullptr;
  size_t i, k;
  reader_opds_status status = reader_opds_open(browser, url, nullptr, &page, error);
  if (status != READER_OPDS_OK || page == nullptr) return false;
  for (i = 0; i < page->entry_count; i++)
    for (k = 0; k < page->entries[i].link_count; k++)
      if (page->entries[i].links[k].acquire == READER_OPDS_ACQ_FREE) {
        if (pick == 0) {
          reader_opds_acquire_options options;
          options.struct_size = sizeof options;
          options.replace_existing = replace ? 1 : 0;
          options.max_bytes = 0;
          status = reader_opds_acquire(browser, page, i, k, &options, nullptr, staged, error);
          reader_opds_page_free(page);
          return status == READER_OPDS_OK;
        }
        pick--;
      }
  reader_opds_page_free(page);
  return false;
}

}  // namespace

int main(int argc, char **argv) {
  reader_opds_config config;
  reader_opds_browser *browser;
  reader_opds_acquired staged, broken;
  exr_library *library = nullptr;
  exr_error sdk_error;
  exr_sideload_result result;
  opds_error error;
  std::string db_path;
  int zero = 0, one = 1;

  if (argc < 4) {
    std::fprintf(stderr, "usage: %s <staging-dir> <plain-base> <out-jsonl>\n", argv[0]);
    return 2;
  }
  g_out = std::fopen(argv[3], "wb");
  if (!g_out) return 2;
  db_path = std::string(argv[1]) + "/import.db";

  reader_opds_config_defaults(&config);
  config.staging_dir = argv[1];
  browser = reader_opds_browser_create(&config, &error);
  if (!browser) {
    record("import_browser", false, error.message);
    std::fclose(g_out);
    return 1;
  }
  if (!acquire(browser, (std::string(argv[2]) + "/opds1/catalog.xml").c_str(), 0, &staged, &error)) {
    record("import_acquire", false, error.message);
    std::fclose(g_out);
    reader_opds_browser_free(browser);
    return 1;
  }
  record("import_acquire", true, staged.path);

  std::memset(&sdk_error, 0, sizeof sdk_error);
  if (exr_library_open(db_path.c_str(), &library, &sdk_error) != EXR_OK) {
    record("import_library_open", false, sdk_error.message);
    reader_opds_browser_free(browser);
    std::fclose(g_out);
    return 1;
  }

  std::memset(&result, 0, sizeof result);
  result.struct_size = sizeof result;
  exr_status status = reader_opds_import_staged(library, &staged, "OPDS fixture", nullptr, &result, &sdk_error);
  int64_t first_book = result.book_id;
  recordf("import_ok", status == EXR_OK && result.book_id > 0 && result.created == 1, "status=%d book=%lld created=%d %s",
          static_cast<int>(status), static_cast<long long>(result.book_id), result.created, sdk_error.message);

  std::memset(&result, 0, sizeof result);
  result.struct_size = sizeof result;
  status = reader_opds_import_staged(library, &staged, "OPDS fixture again", nullptr, &result, &sdk_error);
  recordf("import_duplicate_accepted", status == EXR_OK && result.book_id > 0 && result.book_id != first_book,
          "status=%d first=%lld second=%lld", static_cast<int>(status), static_cast<long long>(first_book),
          static_cast<long long>(result.book_id));

  {
    reader_opds_acquired descriptor = staged;
    descriptor.bytes += 1;
    std::memset(&result, 0, sizeof result);
    result.struct_size = sizeof result;
    status = reader_opds_import_staged(library, &descriptor, "tampered size", nullptr, &result, &sdk_error);
    recordf("import_descriptor_size_mismatch", status == EXR_IO && result.book_id == 0 && result.created == 0,
            "status=%d", static_cast<int>(status));
  }
  {
    reader_opds_acquired descriptor = staged;
    descriptor.media_type[0] = 0;
    std::strcpy(descriptor.media_type, "text/plain");
    std::memset(&result, 0, sizeof result);
    result.struct_size = sizeof result;
    status = reader_opds_import_staged(library, &descriptor, "wrong type", nullptr, &result, &sdk_error);
    recordf("import_media_type_refused", status == EXR_UNSUPPORTED, "status=%d", static_cast<int>(status));
  }
  {
    reader_opds_acquired empty;
    std::memset(&empty, 0, sizeof empty);
    empty.struct_size = sizeof empty;
    std::memset(&result, 0, sizeof result);
    result.struct_size = sizeof result;
    status = reader_opds_import_staged(library, &empty, "no descriptor", nullptr, &result, &sdk_error);
    recordf("import_descriptor_required", status == EXR_ARGUMENT, "status=%d", static_cast<int>(status));
  }
  {
    std::vector<unsigned char> bytes;
    std::FILE *file = std::fopen(staged.path, "rb");
    unsigned char chunk[4096];
    size_t read = 0;
    while (file && (read = std::fread(chunk, 1, sizeof chunk, file)) > 0) bytes.insert(bytes.end(), chunk, chunk + read);
    if (file) std::fclose(file);
    bool tampered = false;
    if (bytes.size() > 64) {
      bytes[40] ^= 0x5a;
      file = std::fopen(staged.path, "r+b");
      if (file) {
        std::fwrite(bytes.data(), 1, bytes.size(), file);
        std::fclose(file);
        tampered = true;
      }
    }
    std::memset(&result, 0, sizeof result);
    result.struct_size = sizeof result;
    status = reader_opds_import_staged(library, &staged, "tampered bytes", nullptr, &result, &sdk_error);
    recordf("import_digest_mismatch", tampered && status == EXR_IO && result.book_id == 0, "tampered=%d status=%d",
            tampered ? 1 : 0, static_cast<int>(status));
  }

  if (!acquire(browser, (std::string(argv[2]) + "/opds1/broken.xml").c_str(), 0, &broken, &error)) {
    record("import_broken_acquire", false, error.message);
  } else {
    record("import_broken_acquire", true, broken.path);
    std::memset(&result, 0, sizeof result);
    result.struct_size = sizeof result;
    status = reader_opds_import_staged(library, &broken, "broken container", nullptr, &result, &sdk_error);
    recordf("import_broken_rejected_by_sdk", status != EXR_OK && result.book_id == 0 && result.created == 0,
            "status=%d message=%.120s", static_cast<int>(status), sdk_error.message);
  }

  std::memset(&result, 0, sizeof result);
  result.struct_size = sizeof result;
  status = reader_opds_import_staged(library, &staged, "cancelled", nullptr, &result, &sdk_error);
  (void)status;

  if (acquire(browser, (std::string(argv[2]) + "/opds1/catalog.xml").c_str(), 0, &staged, &error, true)) {
    exr_control control;
    control.cancelled = cancelled_now;
    control.progress = nullptr;
    control.context = &one;
    std::memset(&result, 0, sizeof result);
    result.struct_size = sizeof result;
    status = reader_opds_import_staged(library, &staged, "cancelled", &control, &result, &sdk_error);
    recordf("import_cancelled_before_commit", status == EXR_CANCELLED && result.book_id == 0, "status=%d",
            static_cast<int>(status));
    control.context = &zero;
    std::memset(&result, 0, sizeof result);
    result.struct_size = sizeof result;
    status = reader_opds_import_staged(library, &staged, "after cancel", &control, &result, &sdk_error);
    recordf("import_library_usable_after_failure", status == EXR_OK && result.book_id > 0, "status=%d book=%lld",
            static_cast<int>(status), static_cast<long long>(result.book_id));
  } else {
    record("import_cancelled_before_commit", false, error.message);
  }

  recordf("import_library_open", true, "db=%s", db_path.c_str());
  exr_library_close(library);
  reader_opds_browser_free(browser);
  std::fclose(g_out);
  return g_failures ? 1 : 0;
}
