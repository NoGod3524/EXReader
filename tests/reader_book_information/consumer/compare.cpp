/* SPDX-License-Identifier: MIT */
/* Independent installed-package consumer: recomputes every snapshot field from
 * the public product/SDK APIs (never from the module's internals) and exercises
 * thread, lifetime and reentrancy rules. */
#include <reader_book_information.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <thread>
#include <vector>

namespace {

struct Problem { std::vector<std::string> items; };
struct Property { std::string key, value; bool key_cut = false, value_cut = false; };

std::string quote(const std::string &text) {
  std::string out = "\"";
  for (unsigned char c : text) {
    if (c == '"' || c == '\\') { out += '\\'; out += static_cast<char>(c); }
    else if (c < 0x20) { char buffer[8]; std::snprintf(buffer, sizeof(buffer), "\\u%04x", c); out += buffer; }
    else out += static_cast<char>(c);
  }
  return out + "\"";
}

std::string truncate(const std::string &text, size_t cap, bool *cut) {
  if (text.size() <= cap) { if (cut) *cut = false; return text; }
  size_t n = cap;
  while (n > 0 && (static_cast<unsigned char>(text[n]) & 0xc0) == 0x80) n--;
  if (cut) *cut = true;
  return text.substr(0, n);
}

struct Product {
  std::string key, format, location, title, author;
  uint64_t bytes = 0;
  int64_t sdk_id = 0;
  int favorite = 0, deleted = 0;
  bool found = false;
};

int capture_product(void *context, const reader_catalog_row *row) {
  Product *p = static_cast<Product *>(context);
  p->key = row->book_key ? row->book_key : "";
  p->format = row->format ? row->format : "";
  p->location = row->location_kind ? row->location_kind : "";
  p->title = row->title ? row->title : "";
  p->author = row->author ? row->author : "";
  p->bytes = row->source_bytes;
  p->sdk_id = row->sdk_book_id;
  p->favorite = row->favorite ? 1 : 0;
  p->deleted = row->deleted ? 1 : 0;
  return 0;
}

void expect(Problem &problem, bool condition, const char *message, const std::string &detail = std::string()) {
  if (!condition) problem.items.push_back(std::string(message) + (detail.empty() ? "" : (": " + detail)));
}

bool same_properties(const reader_book_information_view *view, const std::vector<Property> &expected,
                     size_t omitted, Problem &problem) {
  bool ok = true;
  if (view->property_count != expected.size()) { problem.items.push_back("property count differs"); ok = false; }
  if (view->properties_omitted != omitted) { problem.items.push_back("omitted property count differs"); ok = false; }
  if (!view->properties && view->property_count) { problem.items.push_back("missing property array"); return false; }
  for (size_t i = 0; i < expected.size() && i < view->property_count; i++) {
    if (std::string(view->properties[i].key) != expected[i].key ||
        std::string(view->properties[i].value) != expected[i].value ||
        (view->properties[i].key_truncated != 0) != expected[i].key_cut ||
        (view->properties[i].value_truncated != 0) != expected[i].value_cut) {
      problem.items.push_back("property " + std::to_string(i) + " differs");
      ok = false;
      break;
    }
  }
  return ok;
}

std::string key_digest(const std::string &key) {
  size_t colon = key.find(':');
  return colon == std::string::npos ? std::string() : key.substr(colon + 1);
}

int command_fields(int argc, char **argv) {
  Problem problem;
  if (argc != 8) { std::puts("{\"ok\":false,\"problems\":[\"usage\"]}"); return 2; }
  const char *catalog_path = argv[2], *library_path = argv[3], *key = argv[4];
  const int expected_availability = std::atoi(argv[5]);
  const int expected_identity = std::atoi(argv[6]);
  const int expected_parser = std::atoi(argv[7]);
  reader_catalog *catalog = nullptr;
  exr_library *library = nullptr;
  reader_catalog_error catalog_error{};
  exr_error sdk_error{};
  Product product;
  int found = 0;
  if (reader_catalog_open(catalog_path, &catalog, &catalog_error) != 0) {
    std::puts("{\"ok\":false,\"problems\":[\"catalog open\"]}");
    return 2;
  }
  if (exr_library_open(library_path, &library, &sdk_error) != EXR_OK) {
    std::puts("{\"ok\":false,\"problems\":[\"library open\"]}");
    reader_catalog_close(&catalog, &catalog_error);
    return 2;
  }
  if (reader_catalog_metadata(catalog, key, capture_product, &product, &found, &catalog_error) != 0 || !found) {
    std::puts("{\"ok\":false,\"problems\":[\"catalog metadata\"]}");
    exr_library_close(library);
    reader_catalog_close(&catalog, &catalog_error);
    return 2;
  }
  reader_book_information_options options{};
  options.struct_size = sizeof(options);
  options.verify_source = 1;
  options.read_parser_fields = 1;
  reader_book_information *snapshot = nullptr;
  reader_book_information_error error{};
  const int status = static_cast<int>(reader_book_information_read(catalog, library, key, &options,
                                                                   &snapshot, &error));
  const reader_book_information_view *view = reader_book_information_get(snapshot);
  expect(problem, status == 0 && view != nullptr, "read did not succeed", error.message);
  if (!view) {
    std::printf("{\"ok\":false,\"problems\":[%s]}\n", quote(problem.items.empty() ? "no view" : problem.items[0]).c_str());
    reader_book_information_free(snapshot);
    exr_library_close(library);
    reader_catalog_close(&catalog, &catalog_error);
    return 1;
  }

  /* Product fields: recomputed from the catalog, including the documented caps. */
  bool cut = false;
  expect(problem, view->struct_size >= sizeof(reader_book_information_view), "view struct_size");
  expect(problem, std::string(view->book_key ? view->book_key : "") == product.key, "product book_key");
  expect(problem, std::string(view->format ? view->format : "") == product.format, "product format");
  expect(problem, std::string(view->location_kind ? view->location_kind : "") == product.location, "product location_kind");
  const std::string title = truncate(product.title, READER_BOOK_INFORMATION_MAX_TEXT_BYTES, &cut);
  expect(problem, std::string(view->title ? view->title : "") == title, "product title");
  expect(problem, (view->title_truncated != 0) == cut, "product title truncation flag");
  const std::string author = truncate(product.author, READER_BOOK_INFORMATION_MAX_TEXT_BYTES, &cut);
  expect(problem, std::string(view->author ? view->author : "") == author, "product author");
  expect(problem, (view->author_truncated != 0) == cut, "product author truncation flag");
  expect(problem, (view->author_known != 0) == !product.author.empty(), "author_known");
  expect(problem, view->favorite == product.favorite, "favorite");
  expect(problem, view->deleted == product.deleted, "deleted");
  expect(problem, view->product_source_bytes == product.bytes, "product source bytes");

  /* Local state, recomputed from the public SDK. */
  expect(problem, static_cast<int>(view->availability) == expected_availability, "availability class");
  expect(problem, static_cast<int>(view->identity) == expected_identity, "identity class");
  const std::string digest = key_digest(key);
  if (view->identity == READER_BOOK_INFORMATION_IDENTITY_SHA256) {
    expect(problem, view->verified_sha256 && digest == view->verified_sha256, "verified sha256 differs from key digest");
    expect(problem, view->verified_bytes == product.bytes, "verified bytes differ");
  } else if (view->identity == READER_BOOK_INFORMATION_IDENTITY_SIZE_ONLY) {
    expect(problem, view->verified_sha256 == nullptr, "size-only identity must not claim a digest");
    expect(problem, view->verified_bytes == product.bytes, "size-only verified bytes differ");
  } else {
    expect(problem, view->verified_sha256 == nullptr && view->verified_bytes == 0, "unchecked identity claims data");
  }

  /* Parser fields, recomputed from the public fixed/EPUB readers. */
  std::vector<Property> expected;
  size_t omitted = 0;
  int parser_status = READER_BOOK_INFORMATION_PARSER_NO_PUBLIC_FIELDS;
  int pages_known = 0;
  uint64_t pages = 0;
  std::string parser_title;
  bool parser_title_cut = false;
  int epub_known = 0, epub_bounded = 0, epub_extent = 0;
  const bool present = expected_availability == READER_BOOK_INFORMATION_LOCAL_PRESENT;
  if (present && (product.format == "pdf" || product.format == "cbz")) {
    exr_fixed_open_options open_options{};
    exr_fixed_document *document = nullptr;
    open_options.struct_size = sizeof(open_options);
    if (exr_library_fixed_source(library, product.sdk_id, &open_options, &document, &sdk_error) == EXR_OK) {
      size_t count = 0;
      const exr_fixed_page *page_array = exr_fixed_pages(document, &count);
      (void)page_array;
      pages_known = 1;
      pages = static_cast<uint64_t>(count);
      const char *title_value = exr_fixed_title(document);
      if (title_value && title_value[0]) parser_title = truncate(title_value, READER_BOOK_INFORMATION_MAX_TEXT_BYTES, &parser_title_cut);
      exr_metadata_entry *entries = nullptr;
      if (exr_fixed_load_metadata(document, nullptr, &entries, &count, &sdk_error) == EXR_OK) {
        parser_status = READER_BOOK_INFORMATION_PARSER_OK;
        for (size_t i = 0; i < count; i++) {
          if (expected.size() >= READER_BOOK_INFORMATION_MAX_PROPERTIES || !entries[i].key || !entries[i].value ||
              !entries[i].key[0]) {
            omitted++;
            continue;
          }
          Property property;
          property.key = truncate(entries[i].key, READER_BOOK_INFORMATION_MAX_KEY_BYTES, &property.key_cut);
          property.value = truncate(entries[i].value, READER_BOOK_INFORMATION_MAX_TEXT_BYTES, &property.value_cut);
          expected.push_back(property);
        }
        exr_metadata_free(entries, count);
      } else {
        parser_status = READER_BOOK_INFORMATION_PARSER_FAILED;
      }
      exr_fixed_free(document);
    } else {
      parser_status = READER_BOOK_INFORMATION_PARSER_FAILED;
    }
  } else if (present && product.format == "epub") {
    exr_library_epub_info info{};
    info.struct_size = sizeof(info);
    if (exr_library_epub_info_get(library, product.sdk_id, &info, &sdk_error) == EXR_OK) {
      parser_status = READER_BOOK_INFORMATION_PARSER_OK;
      epub_known = 1;
      epub_bounded = info.bounded_storage ? 1 : 0;
      epub_extent = info.global_extent_known ? 1 : 0;
    } else {
      parser_status = READER_BOOK_INFORMATION_PARSER_FAILED;
    }
  }
  expect(problem, static_cast<int>(view->parser_status) == parser_status, "parser status");
  expect(problem, static_cast<int>(view->parser_status) == expected_parser, "expected parser status");
  expect(problem, view->page_count_known == pages_known, "page count known");
  expect(problem, view->page_count == pages, "page count");
  expect(problem, std::string(view->parser_title ? view->parser_title : "") == parser_title, "parser title");
  expect(problem, (view->parser_title_truncated != 0) == parser_title_cut, "parser title truncation flag");
  expect(problem, view->epub_mode_known == epub_known, "epub mode known");
  expect(problem, view->epub_bounded_storage == epub_bounded, "epub bounded storage");
  expect(problem, view->epub_global_extent_known == epub_extent, "epub global extent");
  same_properties(view, expected, omitted, problem);

  /* The local SDK ID must never appear in the view. */
  const std::string sdk_id = std::to_string(product.sdk_id);
  auto leaks = [&sdk_id](const char *text) { return text && sdk_id != "0" && std::strstr(text, sdk_id.c_str()) != nullptr; };
  bool leak = leaks(view->book_key) || leaks(view->title) || leaks(view->author) || leaks(view->parser_title) ||
              leaks(view->verified_sha256);
  for (size_t i = 0; i < view->property_count; i++) leak = leak || leaks(view->properties[i].value);
  expect(problem, !leak, "view exposes the local SDK ID");

  std::string out = "{\"ok\":";
  out += problem.items.empty() ? "true" : "false";
  out += ",\"problems\":[";
  for (size_t i = 0; i < problem.items.size(); i++) { if (i) out += ","; out += quote(problem.items[i]); }
  out += "],\"property_count\":" + std::to_string(view->property_count);
  out += ",\"omitted\":" + std::to_string(view->properties_omitted);
  out += ",\"pages\":" + std::to_string(view->page_count);
  out += "}\n";
  std::fputs(out.c_str(), stdout);
  const int result = problem.items.empty() ? 0 : 1;
  reader_book_information_free(snapshot);
  exr_library_close(library);
  reader_catalog_close(&catalog, &catalog_error);
  return result;
}

bool read_ok(reader_catalog *catalog, exr_library *library, const char *key, int verify, int parser,
             reader_book_information **snapshot, std::string &detail) {
  reader_book_information_options options{};
  reader_book_information_error error{};
  options.struct_size = sizeof(options);
  options.verify_source = verify;
  options.read_parser_fields = parser;
  const int status = static_cast<int>(reader_book_information_read(catalog, library, key, &options, snapshot, &error));
  if (status != 0) detail = error.message;
  return status == 0 && *snapshot != nullptr;
}

int command_threads(int argc, char **argv) {
  if (argc != 5) { std::puts("{\"ok\":false,\"problems\":[\"usage\"]}"); return 2; }
  reader_catalog *catalog = nullptr;
  exr_library *library = nullptr;
  reader_catalog_error catalog_error{};
  exr_error sdk_error{};
  if (reader_catalog_open(argv[2], &catalog, &catalog_error) != 0 ||
      exr_library_open(argv[3], &library, &sdk_error) != EXR_OK) {
    std::puts("{\"ok\":false,\"problems\":[\"open\"]}");
    return 2;
  }
  Problem problem;
  int foreign_status = 0;
  reader_book_information *foreign = nullptr;
  std::thread worker([&] {
    reader_book_information_options options{};
    reader_book_information_error error{};
    options.struct_size = sizeof(options);
    foreign_status = static_cast<int>(reader_book_information_read(catalog, library, argv[4], &options, &foreign, &error));
  });
  worker.join();
  expect(problem, foreign_status != 0, "a foreign-thread read must refuse");
  expect(problem, foreign == nullptr, "a refused read must not publish a snapshot");
  reader_book_information_free(foreign);

  reader_book_information *snapshot = nullptr;
  std::string detail;
  const bool ok = read_ok(catalog, library, argv[4], 1, 1, &snapshot, detail);
  expect(problem, ok, "owner-thread read failed", detail);
  if (ok) {
    const reader_book_information_view *view = reader_book_information_get(snapshot);
    std::vector<std::string> first;
    first.push_back(view->title ? view->title : "");
    first.push_back(view->author ? view->author : "");
    first.push_back(view->parser_title ? view->parser_title : "");
    first.push_back(view->verified_sha256 ? view->verified_sha256 : "");
    for (size_t i = 0; i < view->property_count; i++) {
      first.push_back(std::string(view->properties[i].key) + "=" + view->properties[i].value);
    }
    std::vector<std::string> second;
    std::thread reader([&] {
      const reader_book_information_view *again = reader_book_information_get(snapshot);
      second.push_back(again->title ? again->title : "");
      second.push_back(again->author ? again->author : "");
      second.push_back(again->parser_title ? again->parser_title : "");
      second.push_back(again->verified_sha256 ? again->verified_sha256 : "");
      for (size_t i = 0; i < again->property_count; i++) {
        second.push_back(std::string(again->properties[i].key) + "=" + again->properties[i].value);
      }
    });
    reader.join();
    expect(problem, first == second, "immutable view differs across threads");
    expect(problem, reader_book_information_get(snapshot) == view, "view pointer is not stable");
    expect(problem, !first.empty() && !first[0].empty(), "view text is empty");
  }
  reader_book_information_free(snapshot);
  exr_library_close(library);
  reader_catalog_close(&catalog, &catalog_error);
  std::printf("{\"ok\":%s,\"foreign_status\":%d,\"problems\":[", problem.items.empty() ? "true" : "false", foreign_status);
  for (size_t i = 0; i < problem.items.size(); i++) { if (i) std::fputs(",", stdout); std::fputs(quote(problem.items[i]).c_str(), stdout); }
  std::puts("]}");
  return problem.items.empty() ? 0 : 1;
}

int command_lifetime(int argc, char **argv) {
  if (argc != 5) { std::puts("{\"ok\":false,\"problems\":[\"usage\"]}"); return 2; }
  reader_catalog *catalog = nullptr;
  exr_library *library = nullptr;
  reader_catalog_error catalog_error{};
  exr_error sdk_error{};
  if (reader_catalog_open(argv[2], &catalog, &catalog_error) != 0 ||
      exr_library_open(argv[3], &library, &sdk_error) != EXR_OK) {
    std::puts("{\"ok\":false,\"problems\":[\"open\"]}");
    return 2;
  }
  reader_book_information *snapshot = nullptr;
  std::string detail;
  Problem problem;
  expect(problem, read_ok(catalog, library, argv[4], 1, 1, &snapshot, detail), "read failed", detail);
  std::vector<std::string> saved;
  const reader_book_information_view *view = reader_book_information_get(snapshot);
  if (view) {
    saved.push_back(view->book_key ? view->book_key : "");
    saved.push_back(view->title ? view->title : "");
    saved.push_back(view->author ? view->author : "");
    saved.push_back(view->parser_title ? view->parser_title : "");
    saved.push_back(view->verified_sha256 ? view->verified_sha256 : "");
    for (size_t i = 0; i < view->property_count; i++) {
      saved.push_back(std::string(view->properties[i].key) + "=" + view->properties[i].value);
    }
  }
  exr_library_close(library);
  library = nullptr;
  if (reader_catalog_close(&catalog, &catalog_error) != 0) problem.items.push_back("catalog close failed");
  std::vector<std::string> after;
  if (view) {
    after.push_back(view->book_key ? view->book_key : "");
    after.push_back(view->title ? view->title : "");
    after.push_back(view->author ? view->author : "");
    after.push_back(view->parser_title ? view->parser_title : "");
    after.push_back(view->verified_sha256 ? view->verified_sha256 : "");
    for (size_t i = 0; i < view->property_count; i++) {
      after.push_back(std::string(view->properties[i].key) + "=" + view->properties[i].value);
    }
  }
  expect(problem, !saved.empty() && saved == after, "snapshot changed after the stores closed");
  reader_book_information_free(snapshot);
  std::printf("{\"ok\":%s,\"strings\":%d,\"problems\":[", problem.items.empty() ? "true" : "false",
              static_cast<int>(saved.size()));
  for (size_t i = 0; i < problem.items.size(); i++) { if (i) std::fputs(",", stdout); std::fputs(quote(problem.items[i]).c_str(), stdout); }
  std::puts("]}");
  return problem.items.empty() ? 0 : 1;
}

struct Reentrant {
  reader_catalog *catalog = nullptr;
  exr_library *library = nullptr;
  const char *key = nullptr;
  int inner = -1;
  int calls = 0;
};

int reentrant_cancel(void *context) {
  Reentrant *state = static_cast<Reentrant *>(context);
  state->calls++;
  reader_book_information_options options{};
  reader_book_information_error error{};
  reader_book_information *snapshot = nullptr;
  options.struct_size = sizeof(options);
  state->inner = static_cast<int>(reader_book_information_read(state->catalog, state->library, state->key,
                                                               &options, &snapshot, &error));
  reader_book_information_free(snapshot);
  return 1;
}

int command_reentrant(int argc, char **argv) {
  if (argc != 5) { std::puts("{\"ok\":false,\"problems\":[\"usage\"]}"); return 2; }
  reader_catalog *catalog = nullptr;
  exr_library *library = nullptr;
  reader_catalog_error catalog_error{};
  exr_error sdk_error{};
  if (reader_catalog_open(argv[2], &catalog, &catalog_error) != 0 ||
      exr_library_open(argv[3], &library, &sdk_error) != EXR_OK) {
    std::puts("{\"ok\":false,\"problems\":[\"open\"]}");
    return 2;
  }
  Reentrant state;
  state.catalog = catalog;
  state.library = library;
  state.key = argv[4];
  reader_book_information_options options{};
  reader_book_information_error error{};
  reader_book_information *snapshot = nullptr;
  options.struct_size = sizeof(options);
  options.verify_source = 1;
  options.cancelled = reentrant_cancel;
  options.context = &state;
  const int outer = static_cast<int>(reader_book_information_read(catalog, library, argv[4], &options, &snapshot, &error));
  Problem problem;
  expect(problem, outer == static_cast<int>(READER_BOOK_INFORMATION_CANCELLED), "outer call was not cancelled");
  expect(problem, state.inner == static_cast<int>(READER_BOOK_INFORMATION_REENTRANT), "inner call was not refused as reentrant");
  expect(problem, snapshot == nullptr, "cancelled call published a snapshot");
  reader_book_information_free(snapshot);
  exr_library_close(library);
  reader_catalog_close(&catalog, &catalog_error);
  std::printf("{\"ok\":%s,\"outer\":%d,\"inner\":%d,\"problems\":[", problem.items.empty() ? "true" : "false",
              outer, state.inner);
  for (size_t i = 0; i < problem.items.size(); i++) { if (i) std::fputs(",", stdout); std::fputs(quote(problem.items[i]).c_str(), stdout); }
  std::puts("]}");
  return problem.items.empty() ? 0 : 1;
}

}  /* namespace */

int main(int argc, char **argv) {
  if (argc < 2) return 2;
  const std::string command = argv[1];
  if (command == "fields") return command_fields(argc, argv);
  if (command == "threads") return command_threads(argc, argv);
  if (command == "lifetime") return command_lifetime(argc, argv);
  if (command == "reentrant") return command_reentrant(argc, argv);
  std::puts("{\"ok\":false,\"problems\":[\"unknown command\"]}");
  return 2;
}
