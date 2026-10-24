/* SPDX-License-Identifier: MIT */
/* Installed-prefix composition consumer (C++17).
   Links every optional package from ONE installed prefix and runs the composed
   product flow: real import -> in-book search capture -> reading-anchor v2
   encode -> product revision -> native WebDAV transfer -> resolve on a second
   SDK library, with preferences, batch import, typed commands, desktop
   metadata, credentials and the account session in the same link graph.
   Only installed headers and the exported find_package() targets are used. */
#include <catalog.h>
#include <exr/document.h>
#include <exr/library.h>
#include <exreader.h>
#include <exr_credentials.h>
#include <exr_sideload.h>
#include <exr_webdav.h>
#include <reader_batch_import.h>
#include <reader_commands.h>
#include <reader_metadata.h>
#include <reader_preferences.h>
#include <reader_projection.h>
#include <reader_reading_state.h>
#include <reader_revisions.h>
#include <reader_search.h>
#include <reader_session.h>
#include <reader_sync.h>

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <map>
#include <string>
#include <thread>
#include <vector>

namespace fs = std::filesystem;

namespace {
/* ---------------- report ---------------- */
std::string esc(const std::string &s) {
  static const char hex[] = "0123456789abcdef";
  std::string out = "\"";
  for (unsigned char c : s) {
    if (c == '"' || c == '\\') { out += '\\'; out += (char)c; }
    else if (c < 0x20) { out += "\\u00"; out += hex[c >> 4]; out += hex[c & 15]; }
    else out += (char)c;
  }
  return out + "\"";
}
struct object {
  std::vector<std::pair<std::string, std::string>> fields;
  object &set(const std::string &k, const std::string &raw) { fields.emplace_back(k, raw); return *this; }
  object &str(const std::string &k, const std::string &v) { return set(k, esc(v)); }
  object &num(const std::string &k, unsigned long long v) { return set(k, std::to_string(v)); }
  object &flag(const std::string &k, bool v) { return set(k, v ? "true" : "false"); }
  std::string dump() const {
    std::string out = "{";
    for (size_t i = 0; i < fields.size(); ++i) { if (i) out += ','; out += esc(fields[i].first) + ":" + fields[i].second; }
    return out + "}";
  }
};
std::string array(const std::vector<std::string> &items) {
  std::string out = "[";
  for (size_t i = 0; i < items.size(); ++i) { if (i) out += ','; out += items[i]; }
  return out + "]";
}
std::vector<std::string> checks;
size_t failures = 0;
void check(bool ok, const std::string &name, const std::string &detail = "") {
  if (!ok) { ++failures; std::fprintf(stderr, "FAIL %s %s\n", name.c_str(), detail.c_str()); }
  checks.push_back(object().str("name", name).flag("pass", ok).str("detail", detail).dump());
}
void stage(const char *what) { std::printf("stage: %s\n", what); std::fflush(stdout); }
[[noreturn]] void fatal(const std::string &what) { std::fprintf(stderr, "FATAL %s\n", what.c_str()); std::exit(2); }
std::string read_file(const std::string &path) {
  std::ifstream in(fs::u8path(path), std::ios::binary);
  if (!in) fatal("cannot read " + path);
  return std::string((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
}
void write_file(const std::string &path, const std::string &data) {
  std::ofstream out(fs::u8path(path), std::ios::binary);
  out.write(data.data(), (std::streamsize)data.size());
  if (!out) fatal("cannot write " + path);
}
void require_directory(const fs::path &path) { fs::create_directories(path); }

/* ---------------- SDK helpers ---------------- */
exr_error sdk_error{};
#define SDK(call) do { sdk_error = exr_error{}; exr_status s_ = (call); \
  if (s_ != EXR_OK) fatal(std::string(#call) + ": " + sdk_error.message); } while (0)

struct store_side {
  std::string name, library_path, product_path;
  exr_library *library = nullptr;
  reader_revisions *revisions = nullptr;
  reader_catalog *catalog = nullptr;
};
void open_side(store_side &side) {
  exr_error error{};
  if (exr_library_open(side.library_path.c_str(), &side.library, &error) != EXR_OK)
    fatal(side.name + " library: " + error.message);
  reader_revision_error revision_error{};
  if (reader_revisions_open(side.product_path.c_str(), &side.revisions, &revision_error) != READER_REV_OK)
    fatal(side.name + " revisions: " + revision_error.message);
  reader_catalog_error catalog_error{};
  if (reader_catalog_open(side.product_path.c_str(), &side.catalog, &catalog_error))
    fatal(side.name + " catalog: " + catalog_error.message);
}
void close_side(store_side &side) {
  if (side.library) exr_library_close(side.library);
  side.library = nullptr;
  reader_revision_error revision_error{};
  if (side.revisions) reader_revisions_close(&side.revisions, &revision_error);
  reader_catalog_error catalog_error{};
  if (side.catalog) reader_catalog_close(&side.catalog, &catalog_error);
}
std::string new_revision_id() {
  char id[33]{};
  reader_revision_error error{};
  if (reader_revision_new_id(id, &error) != READER_REV_OK) fatal("revision id");
  return id;
}
struct head_collector { std::vector<std::string> ids; };
int collect_head(void *context, const reader_revision_head *head) {
  static_cast<head_collector *>(context)->ids.emplace_back(head->revision_id);
  return 0;
}
struct outbox_collector { std::vector<std::string> ids; };
int collect_outbox(void *context, const reader_revision_outbox_row *row) {
  static_cast<outbox_collector *>(context)->ids.emplace_back(row->info.revision_id);
  return 0;
}
size_t shard_of(const std::string &revision_id) {
  return (size_t)std::stoul(revision_id.substr(0, 2), nullptr, 16);
}
std::vector<std::string> pending_outbox(reader_revisions *store) {
  outbox_collector collector;
  reader_revision_error error{};
  reader_revision_outbox(store, 100, collect_outbox, &collector, &error);
  return collector.ids;
}

/* ---------------- batch import ---------------- */
struct batch_observer {
  size_t imported = 0, duplicate = 0, failed = 0;
  std::map<std::string, int64_t> ids;
};
void observe_result(void *context, size_t index, const reader_batch_result *result) {
  (void)index;
  auto *observer = static_cast<batch_observer *>(context);
  if (result->status == READER_BATCH_ITEM_IMPORTED) {
    ++observer->imported;
    observer->ids[std::string(result->path)] = result->book_id;
  } else if (result->status == READER_BATCH_ITEM_DUPLICATE) {
    ++observer->duplicate;
  } else {
    ++observer->failed;
  }
}

/* ---------------- arguments ---------------- */
struct arguments {
  std::string fixtures, work, report, webdav_root, authorization;
  std::map<std::string, std::string> shas;
};

int run(const arguments &args) {
  const std::string text_sha = args.shas.at("txt");
  const std::string text_path = args.fixtures + "/sample.txt";
  const std::string epub_path = args.fixtures + "/layout.epub";
  const std::string pdf_path = args.fixtures + "/pdf-public-text.pdf";

  const fs::path work = fs::u8path(args.work);
  for (const char *name : {"A", "B", "inbox", "staging", "settings", "A-originals", "A-cache",
                           "B-cache", "D-cache", "D-originals"})
    require_directory(work / name);
  write_file((work / "inbox" / "sample.txt").u8string(), read_file(text_path));
  write_file((work / "inbox" / "layout.epub").u8string(), read_file(epub_path));

  size_t network_pushed = 0, network_pulled = 0, originals_exported = 0;
  size_t session_pushed = 0, session_pulled = 0, session_sweeps = 0;
  size_t metadata_committed = 0;
  std::string resolved_state = "MISSING";
  const bool networked = !args.webdav_root.empty();

  /* 1. Platform secure storage. Opening validates the namespace and allocates;
        no service is contacted, so a runner without a keyring stays honest. */
  stage("credentials");
  {
    exr_credentials_store *store = nullptr;
    check(exr_credentials_open("org.exreader.composition", &store) == EXR_CRED_OK && store,
          "installed credentials package validates a namespace", "open");
    uint8_t buffer[EXR_CREDENTIALS_SECRET_MAX]{};
    size_t length = 1;
    const exr_credentials_status status = exr_credentials_get(
        store, "00000000-0000-4000-8000-000000000000", buffer, sizeof buffer, &length);
    check(status == EXR_CRED_NOT_FOUND || status == EXR_CRED_UNAVAILABLE,
          "credentials never invent a record", exr_credentials_status_name(status));
    check(length == 0, "credentials report no length for a missing record");
    exr_credentials_wipe(buffer, sizeof buffer);
    bool wiped = true;
    for (uint8_t value : buffer) if (value) wiped = false;
    check(wiped, "credentials wipe clears the caller buffer");
    check(std::strcmp(exr_credentials_status_name(EXR_CRED_UNAVAILABLE), "UNAVAILABLE") == 0,
          "credentials expose a secret-free status token");
    exr_credentials_close(store);
  }

  /* 2. Device preferences: real save/load through the installed package. */
  stage("preferences");
  const std::string settings_path = (work / "settings" / "preferences.json").u8string();
  {
    reader_preferences_error error{};
    reader_preferences preferences = reader_preferences_defaults();
    check(reader_preferences_validate(&preferences, &error) == READER_PREFERENCES_OK,
          "installed preferences validate their defaults", error.message);
    preferences.font_size = 13.5f;
    preferences.margin = 32.0f;
    check(reader_preferences_save(&preferences, settings_path.c_str(), nullptr, &error) == READER_PREFERENCES_OK,
          "preferences save a device document", error.message);
    reader_preferences loaded = reader_preferences_defaults();
    check(reader_preferences_load(settings_path.c_str(), &loaded, nullptr, &error) == READER_PREFERENCES_OK,
          "preferences reload their own document", error.message);
    check(loaded.font_size == preferences.font_size && loaded.margin == preferences.margin,
          "preferences round-trip exact values");
    check(reader_preferences_effective_theme(&loaded, READER_PREFERENCES_THEME_DARK) ==
              reader_preferences_effective_theme(&preferences, READER_PREFERENCES_THEME_DARK),
          "preferences resolve the same effective theme");
    reader_preferences invalid = reader_preferences_defaults();
    invalid.font_size = 2.0f;
    check(reader_preferences_validate(&invalid, &error) == READER_PREFERENCES_RANGE,
          "preferences refuse an out-of-range size", error.message);
    check(reader_preferences_abi_version() == READER_PREFERENCES_ABI_VERSION,
          "preferences report their own ABI");
  }

  /* 3. One product provider carries catalog, history and the SDK library. */
  stage("product");
  store_side a{"A", (work / "A" / "library.sqlite").u8string(), (work / "A" / "product.sqlite").u8string()};
  store_side b{"B", (work / "B" / "library.sqlite").u8string(), (work / "B" / "product.sqlite").u8string()};
  open_side(a);
  open_side(b);
  {
    size_t migration_bytes = 0;
    const char *migration = reader_catalog_migration(&migration_bytes);
    check(migration && migration_bytes > 0 && std::strstr(migration, "CREATE TABLE reader_books"),
          "installed catalog ships the unchanged schema1 migration", std::to_string(migration_bytes));
  }

  /* 4. Batch import composes sideload: two candidates from one directory. */
  stage("batch import");
  int64_t text_book = 0, epub_book = 0;
  {
    std::string inbox = (work / "inbox").u8string();
    reader_batch_scan_options scan{};
    reader_batch_scan_options_init(&scan);
    scan.root = inbox.c_str();
    scan.recursive = 0;
    scan.batch_size = 8;
    reader_batch_enumerator *enumerator = nullptr;
    reader_batch_error error{};
    check(reader_batch_enumerate_open(&scan, &enumerator, &error) == READER_BATCH_OK,
          "batch enumeration opens the installed package", error.message);
    struct batch { reader_batch_candidate *items; size_t count; };
    std::vector<batch> batches;
    std::vector<std::string> stored;
    std::vector<exr_format> formats;
    for (;;) {
      reader_batch_candidate *items = nullptr;
      size_t count = 0;
      int complete = 0, truncated = 0;
      const reader_batch_status status =
          reader_batch_enumerate_next(enumerator, &items, &count, &complete, &truncated, &error);
      if (status != READER_BATCH_OK) { check(false, "batch enumeration step", error.message); break; }
      if (count) {
        batches.push_back(batch{items, count});
        for (size_t i = 0; i < count; ++i) {
          stored.emplace_back(items[i].path);
          formats.push_back(items[i].format);
        }
      }
      if (complete || truncated) break;
    }
    reader_batch_enumerate_close(enumerator);
    check(stored.size() == 2, "batch enumeration finds exactly the two real documents",
          std::to_string(stored.size()));

    std::vector<reader_batch_item> items;
    for (size_t i = 0; i < stored.size(); ++i) {
      reader_batch_item item{};
      item.struct_size = sizeof item;
      item.path = stored[i].c_str();
      item.title = nullptr;
      item.format = formats[i];
      items.push_back(item);
    }
    std::string staging = (work / "staging").u8string();
    reader_batch_import_options options{};
    reader_batch_import_options_init(&options);
    options.staging_dir = staging.c_str();
    batch_observer observer;
    options.on_result = observe_result;
    options.on_result_context = &observer;
    reader_batch_result *results = nullptr;
    size_t result_count = 0;
    const reader_batch_status status = reader_batch_import(a.library, items.data(), items.size(), &options,
                                                           &results, &result_count, &error);
    check(status == READER_BATCH_OK && result_count == items.size(),
          "batch import reaches a terminal result for every item", error.message);
    check(observer.imported == 2 && observer.failed == 0,
          "batch import commits both documents through sideload",
          std::to_string(observer.imported) + "/" + std::to_string(observer.failed));
    for (const auto &entry : observer.ids) {
      if (entry.first.find("sample.txt") != std::string::npos) text_book = entry.second;
      if (entry.first.find("layout.epub") != std::string::npos) epub_book = entry.second;
    }
    check(text_book > 0 && epub_book > 0, "batch import reports both SDK book identities");
    if (results) reader_batch_results_free(results, result_count);
    for (const auto &batch : batches) reader_batch_candidates_free(batch.items, batch.count);
    batches.clear();
    check(std::strcmp(reader_batch_status_name(READER_BATCH_OK), "OK") == 0,
          "batch import exposes a stable status token");
  }

  /* 5. Explicit sideload import of a fixed-page document. */
  stage("sideload");
  int64_t pdf_book = 0;
  {
    exr_error error{};
    exr_sideload_result result{};
    result.struct_size = sizeof result;
    const std::string staged = (work / "staging" / "fixed.pdf").u8string();
    write_file(staged, read_file(pdf_path));
    const exr_status status = exr_sideload_import_file(a.library, EXR_PDF, staged.c_str(), "fixed", nullptr,
                                                       &result, &error);
    check(status == EXR_OK && result.created == 1 && result.book_id > 0,
          "sideload imports a fixed-page original", error.message);
    pdf_book = result.book_id;
    int present = 0;
    reader_catalog_error catalog_error{};
    check(reader_catalog_has_local(a.catalog, pdf_book, &present, &catalog_error) == 0 && present == 0,
          "sideload never writes product metadata on its own", catalog_error.message);
  }

  /* 6. Typed book command: metadata + history + outbox in one transaction. */
  stage("commands");
  const std::string book_key = "txt:" + text_sha;
  const std::string book_title = "Composed sample";
  const uint64_t text_bytes = (uint64_t)read_file(text_path).size();
  {
    reader_book_command command{};
    command.operation = READER_COMMAND_PUT;
    command.book_key = book_key.c_str();
    command.format = "txt";
    command.source_sha256 = text_sha.c_str();
    command.title = book_title.c_str();
    command.author = "composition";
    command.sort_title = book_title.c_str();
    command.source_bytes = text_bytes;
    command.favorite = 0;
    reader_command_context context{a.revisions, nullptr, nullptr, 0};
    reader_command_result result{};
    reader_command_error error{};
    check(reader_command_apply_book(&context, &command, &result, &error) == READER_COMMAND_OK && result.created &&
              result.applied,
          "typed book command commits metadata history and outbox", error.message);
    struct row_view { std::string title, author; int favorite = -1; };
    row_view observed;
    int found = 0;
    reader_catalog_error catalog_error{};
    check(reader_catalog_find(a.catalog, book_key.c_str(), nullptr,
                              [](void *context, const reader_catalog_row *row) {
                                auto *value = static_cast<row_view *>(context);
                                value->title = row->title;
                                value->author = row->author;
                                value->favorite = row->favorite;
                                return 0;
                              }, &observed, &found, &catalog_error) == 0 && found == 1,
          "typed book command projects the product row", catalog_error.message);
    check(observed.title == book_title && observed.author == "composition" && observed.favorite == 0,
          "typed book command stores the exact supplied metadata");
  }

  /* 7. Search capture -> reading v2 encode -> revision -> selected -> decode. */
  stage("search and reading");
  exr_document *document_a = nullptr;
  size_t text_size = 0;
  const char *text = nullptr;
  std::string annotation_wire;
  size_t quote_start = 0, quote_end = 0, point_offset = 0;
  unsigned anchor_version = 0;
  {
    SDK(exr_library_document(a.library, text_book, &document_a, &sdk_error));
    text = exr_document_text(document_a, &text_size);
    check(text && text_size == text_bytes, "the SDK resolves the imported reflow text",
          std::to_string(text_size));
    const std::string query = "\xE5\xBC\x95\xE6\x93\x8E\xE6\x8E\x8C\xE6\x8E\xA7";  /* 引擎掌控 */
    const std::string whole(text ? text : "", text ? text_size : 0);
    const size_t located = whole.find(query);
    check(located != std::string::npos, "the fixture carries the searchable literal");
    point_offset = located == std::string::npos ? 0 : located;

    reader_search_options options{};
    options.struct_size = sizeof options;
    options.source_key = book_key.c_str();
    reader_search *search = nullptr;
    reader_search_error error{};
    check(reader_search_open_reflow(document_a, query.data(), query.size(), &options, &search, &error) ==
              READER_SEARCH_OK && search,
          "installed search opens over the public document", error.message);
    reader_search_result result{};
    check(reader_search_next(search, 8, &result, &error) == READER_SEARCH_OK,
          "installed search returns a real batch", error.message);
    check(result.count >= 1 && result.hits[0].start == point_offset &&
              result.hits[0].end == point_offset + query.size(),
          "search returns the exact byte range of the literal", std::to_string(result.count));
    check(result.count >= 1 && result.hits[0].mode == READER_SEARCH_REFLOW,
          "search reports the reflow route");
    std::string exact = query;
    if (result.count >= 1 && result.hits[0].anchor.exact) exact = result.hits[0].anchor.exact;
    check(exact == query, "the search hit carries the exact SDK quote");
    quote_start = result.count ? result.hits[0].start : 0;
    quote_end = result.count ? result.hits[0].end : 0;
    reader_search_cursor cursor{};
    check(reader_search_cursor_get(search, &cursor, &error) == READER_SEARCH_OK && cursor.version == 2 &&
              std::strcmp(cursor.source_key, book_key.c_str()) == 0,
          "search binds its cursor to the verified source identity", error.message);
    reader_search_stats stats{};
    check(reader_search_stats_get(search, &stats, &error) == READER_SEARCH_OK &&
              stats.hits_returned == result.count,
          "search accounts for the returned hits");

    reader_rs_capture capture{};
    capture.mode = READER_RS_REFLOW_GLOBAL;
    capture.anchor = result.count ? &result.hits[0].anchor : nullptr;
    const reader_rs_gap gap = capture.anchor ? reader_rs_classify(&capture) : READER_RS_GAP_POINT;
    check(capture.anchor && gap == READER_RS_GAP_NONE,
          "the search capture is losslessly representable", std::to_string((int)gap));

    /* progress: a genuine SDK point at the hit start */
    exr_anchor point_anchor{};
    SDK(exr_anchor_create(document_a, quote_start, quote_start, &point_anchor, &sdk_error));
    reader_rs_capture point_capture{};
    point_capture.mode = READER_RS_REFLOW_GLOBAL;
    point_capture.anchor = &point_anchor;
    check(reader_rs_classify(&point_capture) == READER_RS_GAP_POINT,
          "a real SDK progress point is classified as a point");
    const std::string parser_version = std::string("exreader-sdk-") + exr_version();
    {
      const std::string revision = new_revision_id();
      reader_rs_envelope envelope{};
      envelope.revision_id = revision.c_str();
      envelope.operation = "put";
      envelope.entity_kind = "progress";
      envelope.book_key = book_key.c_str();
      envelope.parents = nullptr;
      envelope.parent_count = 0;
      envelope.parser_version = parser_version.c_str();
      reader_rs_error reading_error{};
      char *wire = nullptr;
      size_t bytes = 0;
      check(reader_rs_encode_v2(a.revisions, &envelope, &point_capture, 0, &wire, &bytes, &reading_error) ==
                READER_RS_OK,
            "reading v2 encodes the SDK progress point", reading_error.message);
      reader_revision_info info{};
      reader_revision_error revision_error{};
      int created = 0;
      const bool committed = wire && reader_revision_local_reading(a.revisions, wire, bytes, nullptr, 0, &info,
                                                                  &created, &revision_error) == READER_REV_OK &&
                             created;
      check(committed, "reading v2 progress commits through the product transaction", revision_error.message);
      if (wire) reader_rs_free(wire);
    }
    /* annotation: the captured search range with its exact quote */
    {
      const std::string revision = new_revision_id();
      const std::string annotation_id = new_revision_id();
      const std::string key = book_key + ":" + annotation_id;
      reader_rs_envelope envelope{};
      envelope.revision_id = revision.c_str();
      envelope.operation = "put";
      envelope.entity_kind = "annotation";
      envelope.book_key = book_key.c_str();
      envelope.annotation_id = annotation_id.c_str();
      envelope.parents = nullptr;
      envelope.parent_count = 0;
      envelope.note_text = "composition quote";
      envelope.parser_version = parser_version.c_str();
      reader_rs_error reading_error{};
      char *wire = nullptr;
      size_t bytes = 0;
      check(reader_rs_encode_v2(a.revisions, &envelope, &capture, 0, &wire, &bytes, &reading_error) == READER_RS_OK,
            "reading v2 encodes the search capture", reading_error.message);
      reader_revision_info info{};
      reader_revision_error revision_error{};
      int created = 0;
      const bool committed = wire && reader_revision_local_reading(a.revisions, wire, bytes, nullptr, 0, &info,
                                                                  &created, &revision_error) == READER_REV_OK &&
                             created;
      check(committed, "reading v2 annotation commits through the product transaction", revision_error.message);
      if (wire) {
        annotation_wire.assign(wire, bytes);
        reader_rs_free(wire);
      }
      head_collector heads;
      reader_revision_state state{};
      check(reader_revision_heads(a.revisions, "annotation", key.c_str(), collect_head, &heads, &state,
                                  &revision_error) == READER_REV_OK && heads.ids.size() == 1 &&
                heads.ids[0] == revision,
            "the committed annotation is the single head", revision_error.message);
      char *selected = nullptr;
      size_t selected_bytes = 0;
      reader_revision_info selected_info{};
      reader_revision_selection selection{};
      check(reader_revision_selected(a.revisions, "annotation", key.c_str(), &selected, &selected_bytes,
                                     &selected_info, &selection, &revision_error) == READER_REV_OK &&
                selection.kind == READER_SELECTION_SAFE,
            "the committed annotation selects as a safe head", revision_error.message);
      reader_rs_record record{};
      check(selected && reader_rs_decode(a.revisions, selected, selected_bytes, &record, &reading_error) ==
                READER_RS_OK,
            "reading v2 decodes its own retained bytes", reading_error.message);
      check(record.anchor_version == 2 && record.start == quote_start && record.end == quote_end &&
                record.exact && exact == record.exact,
            "the decoded record keeps the exact search selector",
            std::to_string(record.start) + ".." + std::to_string(record.end));
      check(selected && selected_bytes == annotation_wire.size() &&
                std::memcmp(selected, annotation_wire.data(), selected_bytes) == 0,
            "the retained bytes equal the encoded wire");
      anchor_version = (unsigned)record.anchor_version;
      reader_rs_record_free(&record);
      if (selected) reader_revision_bytes_free(selected);
    }
    exr_anchor_free(&point_anchor);
    if (result.hits) reader_search_result_free(&result);
    reader_search_close(&search, &error);
  }

  /* 8. Desktop metadata over the same product provider. */
  stage("metadata");
  {
    const std::string pending = (work / "settings" / "pending-metadata.json").u8string();
    reader_metadata_owner *owner = nullptr;
    reader_metadata_error error{};
    check(reader_metadata_open(a.product_path.c_str(), pending.c_str(), &owner, &error) == READER_METADATA_OK,
          "desktop metadata opens on the product provider", error.message);
    reader_metadata_snapshot *snapshot = nullptr;
    check(reader_metadata_prepare_book(owner, book_key.c_str(), &snapshot, &error) == READER_METADATA_OK && snapshot,
          "desktop metadata prepares the composed book", error.message);
    const reader_metadata_view *view = reader_metadata_snapshot_view(snapshot);
    check(view && view->present && view->head_count >= 1,
          "the prepared snapshot carries the complete head set");
    if (view) {
      reader_book_command edit = view->book;
      edit.operation = READER_COMMAND_PUT;
      edit.favorite = 1;
      reader_metadata_result staged{}, applied{};
      check(reader_metadata_stage_book(owner, snapshot, &edit, &staged, &error) == READER_METADATA_OK,
            "desktop metadata stages a durable intent", error.message);
      check(reader_metadata_apply_pending(owner, &applied, &error) == READER_METADATA_OK && applied.committed,
            "desktop metadata applies its intent", error.message);
      metadata_committed = applied.committed ? 1u : 0u;
      check(reader_metadata_finish_pending(owner, &applied, &error) == READER_METADATA_OK,
            "desktop metadata finishes the intent", error.message);
    }
    reader_metadata_snapshot_free(snapshot);
    reader_metadata_close(&owner, &error);
    int found = 0;
    int favorite = -1;
    reader_catalog_error catalog_error{};
    check(reader_catalog_metadata(a.catalog, book_key.c_str(),
                                  [](void *context, const reader_catalog_row *row) {
                                    *static_cast<int *>(context) = row->favorite;
                                    return 0;
                                  }, &favorite, &found, &catalog_error) == 0 && found == 1 && favorite == 1,
          "the metadata intent reaches the product row", catalog_error.message);
  }

  /* 9. Native WebDAV: publish from A, receive on B, resolve on the second SDK. */
  stage("webdav");
  if (networked) {
    const std::string originals = (work / "A-originals").u8string();
    {
      uint64_t written = 0;
      exr_error error{};
      check(exr_sideload_export_original(a.library, text_book, (originals + "/" + text_sha + ".txt").c_str(),
                                        nullptr, &written, &error) == EXR_OK && written == text_bytes,
            "sideload exports the exact immutable original", error.message);
      ++originals_exported;
    }
    exr_webdav_config configuration{};
    configuration.root_url = args.webdav_root.c_str();
    configuration.authorization = args.authorization.c_str();
    configuration.timeout_ms = 30000;
    exr_webdav_error dav_error{};
    exr_webdav_client *dav = nullptr;
    check(exr_webdav_create(&configuration, &dav, &dav_error) == EXR_DAV_OK && dav,
          "native TLS client accepts the composition root", dav_error.message);

    struct original_context { std::string directory, sha, format; };
    original_context originals_context{originals, text_sha, "txt"};
    auto original_path = [](void *context, const char *key, char *out, size_t capacity) -> int {
      const auto *value = static_cast<const original_context *>(context);
      (void)key;
      const std::string path = value->directory + "/" + value->sha + "." + value->format;
      if (path.size() >= capacity) return 1;
      std::memcpy(out, path.c_str(), path.size() + 1);
      return 0;
    };

    std::vector<std::string> pushed_ids = pending_outbox(a.revisions);
    check(pushed_ids.size() >= 3, "the composition queued book and reading revisions",
          std::to_string(pushed_ids.size()));
    {
      std::string cache = (work / "A-cache").u8string();
      reader_sync_config sync_configuration{};
      sync_configuration.dav = dav;
      sync_configuration.revisions = a.revisions;
      sync_configuration.private_directory = cache.c_str();
      sync_configuration.original = original_path;
      sync_configuration.context = &originals_context;
      reader_sync *sync = nullptr;
      reader_sync_error sync_error{};
      check(reader_sync_create(&sync_configuration, &sync, &sync_error) == READER_SYNC_OK,
            "native sync binds the composition handles", sync_error.message);
      const unsigned shard = pushed_ids.empty() ? 0u : (unsigned)shard_of(pushed_ids[0]);
      reader_sync_report report{};
      std::string cursor;
      do {
        if (reader_sync_step(sync, shard, cursor.c_str(), 100, nullptr, &report, &sync_error) != READER_SYNC_OK)
          fatal("native push step " + std::to_string(sync_error.code) + "/" +
                std::to_string(sync_error.http_status) + " " + sync_error.message);
        check(report.pending_metadata == 0 && report.pending_local_original == 0,
              "the push verified every referenced original");
        network_pushed += report.pushed;
        cursor = report.after;
      } while (!report.shard_complete);
      check(network_pushed >= pushed_ids.size(),
            "every queued revision reached the immutable remote store", std::to_string(network_pushed));
      check(pending_outbox(a.revisions).empty(), "the verified publication acknowledged the outbox");
      reader_sync_free(sync);
    }

    std::vector<std::string> shards;
    for (const auto &id : pushed_ids) {
      const std::string name = std::to_string(shard_of(id));
      bool known = false;
      for (const auto &existing : shards) if (existing == name) known = true;
      if (!known) shards.push_back(name);
    }
    {
      std::string cache = (work / "B-cache").u8string();
      reader_sync_config sync_configuration{};
      sync_configuration.dav = dav;
      sync_configuration.revisions = b.revisions;
      sync_configuration.private_directory = cache.c_str();
      sync_configuration.original = nullptr;
      sync_configuration.context = nullptr;
      reader_sync *sync = nullptr;
      reader_sync_error sync_error{};
      check(reader_sync_create(&sync_configuration, &sync, &sync_error) == READER_SYNC_OK,
            "the receiving side binds its own provider", sync_error.message);
      for (const auto &name : shards) {
        const unsigned shard = (unsigned)std::stoul(name);
        reader_sync_report report{};
        std::string cursor;
        do {
          if (reader_sync_step(sync, shard, cursor.c_str(), 100, nullptr, &report, &sync_error) != READER_SYNC_OK)
            fatal("native pull step " + std::to_string(sync_error.code) + "/" +
                  std::to_string(sync_error.http_status) + " " + sync_error.message);
          network_pulled += report.pulled;
          cursor = report.after;
        } while (!report.shard_complete);
      }
      check(network_pulled >= pushed_ids.size(), "the receiver adopted every published revision",
            std::to_string(network_pulled));
      reader_sync_free(sync);
    }
    exr_webdav_free(dav);

    const std::string cached = (work / "B-cache" / (text_sha + ".txt")).u8string();
    check(fs::exists(fs::u8path(cached)), "the receiver downloaded the verified original bytes");
    const std::string delivered = read_file(cached);
    check(delivered == read_file(text_path), "the downloaded original is byte-identical");
    exr_error import_error{};
    int64_t receiver_book = 0;
    check(exr_library_import(b.library, EXR_TXT, delivered.data(), delivered.size(), "receiver", &receiver_book,
                             &import_error) == EXR_OK && receiver_book > 0,
          "the receiver SDK imports the delivered original", import_error.message);
    exr_document *document_b = nullptr;
    SDK(exr_library_document(b.library, receiver_book, &document_b, &sdk_error));
    size_t receiver_size = 0;
    const char *receiver_text = exr_document_text(document_b, &receiver_size);
    check(receiver_text && receiver_size == text_size &&
              std::string(receiver_text, receiver_size) == std::string(text, text_size),
          "the second SDK library exposes the identical text");

    std::vector<std::string> keys;
    reader_revision_error revision_error{};
    reader_revision_entities_page(b.revisions, "annotation", nullptr, 1, 100,
                                  [](void *context, const reader_revision_entity_row *row) {
                                    static_cast<std::vector<std::string> *>(context)->emplace_back(row->entity_key);
                                    return 0;
                                  }, &keys, &revision_error);
    check(keys.size() == 1, "the receiver retained exactly one annotation entity", std::to_string(keys.size()));
    char *retained = nullptr;
    size_t retained_bytes = 0;
    reader_revision_info retained_info{};
    reader_revision_selection selection{};
    bool selected = false;
    if (!keys.empty())
      selected = reader_revision_selected(b.revisions, "annotation", keys[0].c_str(), &retained, &retained_bytes,
                                          &retained_info, &selection, &revision_error) == READER_REV_OK &&
                 selection.kind == READER_SELECTION_SAFE;
    check(selected, "the received annotation is a safe head on the second provider", revision_error.message);
    check(retained && retained_bytes == annotation_wire.size() &&
              std::memcmp(retained, annotation_wire.data(), retained_bytes) == 0,
          "WebDAV preserved the exact retained revision bytes");
    reader_rs_record received_record{};
    reader_rs_error reading_error{};
    check(retained && reader_rs_decode(b.revisions, retained, retained_bytes, &received_record, &reading_error) ==
              READER_RS_OK,
          "the receiver decodes the transported record", reading_error.message);
    exr_anchor_match match{};
    const reader_rs_status resolve = retained
        ? reader_rs_resolve_reflow(document_b, &received_record, nullptr, &match, &reading_error)
        : READER_RS_ARGUMENT;
    check(resolve == READER_RS_OK && match.state == EXR_ANCHOR_FOUND && match.start == quote_start &&
              match.end == quote_end,
          "the second SDK resolves the transported selector exactly", reading_error.message);
    resolved_state = match.state == EXR_ANCHOR_FOUND ? "FOUND"
        : match.state == EXR_ANCHOR_AMBIGUOUS ? "AMBIGUOUS"
        : match.state == EXR_ANCHOR_LEGACY ? "LEGACY" : "MISSING";
    check(received_record.anchor_version == 2, "the transported record keeps anchor version 2");
    reader_rs_record_free(&received_record);
    if (retained) reader_revision_bytes_free(retained);
    exr_document_free(document_b);
  }

  /* 10. Account session: one owned worker sweep over its own provider. */
  stage("session");
  if (networked) {
    const fs::path d = work / "D";
    require_directory(d);
    store_side c{"C", (d / "library.sqlite").u8string(), (d / "product.sqlite").u8string()};
    open_side(c);
    exr_error import_error{};
    int64_t session_book = 0;
    const std::string text_data = read_file(text_path);
    check(exr_library_import(c.library, EXR_TXT, text_data.data(), text_data.size(), "session", &session_book,
                             &import_error) == EXR_OK,
          "the session provider imports its own original", import_error.message);
    reader_book_command command{};
    command.operation = READER_COMMAND_PUT;
    command.book_key = book_key.c_str();
    command.format = "txt";
    command.source_sha256 = text_sha.c_str();
    command.title = book_title.c_str();
    command.author = "composition";
    command.sort_title = book_title.c_str();
    command.source_bytes = text_bytes;
    command.favorite = 0;
    {
      reader_command_context context{c.revisions, nullptr, nullptr, 0};
      reader_command_result result{};
      reader_command_error error{};
      check(reader_command_apply_book(&context, &command, &result, &error) == READER_COMMAND_OK,
            "the session provider seeds its own queued book", error.message);
      uint64_t written = 0;
      exr_error export_error{};
      const std::string destination = (work / "D-originals" / (text_sha + ".txt")).u8string();
      check(exr_sideload_export_original(c.library, session_book, destination.c_str(), nullptr, &written,
                                         &export_error) == EXR_OK,
            "the session provider stages its immutable original", export_error.message);
      ++originals_exported;
    }
    const std::string product_path = (d / "product.sqlite").u8string();
    close_side(c);

    std::string private_directory = (work / "D-cache").u8string();
    std::string original_directory = (work / "D-originals").u8string();
    const std::string account = "7f1a9f7e-3c2b-4f5a-9d6e-1a2b3c4d5e6f";
    reader_session_config session_config{};
    session_config.product_path = product_path.c_str();
    session_config.private_directory = private_directory.c_str();
    session_config.original_directory = original_directory.c_str();
    session_config.account_id = account.c_str();
    session_config.dav.root_url = args.webdav_root.c_str();
    session_config.dav.authorization = args.authorization.c_str();
    session_config.dav.timeout_ms = 30000;
    reader_session *session = nullptr;
    check(reader_session_create(&session_config, &session) == READER_SESSION_OK && session,
          "the installed session package creates one owned worker");
    check(reader_session_start(session) == READER_SESSION_OK, "the session accepts a sweep request");
    reader_session_snapshot snapshot{};
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(240);
    for (;;) {
      reader_session_observe(session, &snapshot);
      if (snapshot.state == READER_SESSION_FINISHED || snapshot.state == READER_SESSION_FAILED ||
          snapshot.state == READER_SESSION_CANCELLED) break;
      if (std::chrono::steady_clock::now() > deadline) break;
      std::this_thread::sleep_for(std::chrono::milliseconds(20));
    }
    check(snapshot.state == READER_SESSION_FINISHED && snapshot.status == READER_SESSION_OK,
          "the session finished one complete sweep",
          std::to_string((int)snapshot.state) + " " + snapshot.error.message);
    session_pushed = (size_t)snapshot.pushed;
    session_pulled = (size_t)snapshot.pulled;
    session_sweeps = (size_t)snapshot.completed_sweeps;
    check(snapshot.completed_sweeps >= 1 && snapshot.completed_shards == 256,
          "the session swept all 256 shards", std::to_string(snapshot.completed_shards));
    check(session_pushed >= 1, "the session pushed its own queued revision", std::to_string(session_pushed));
    check(session_pulled >= 3, "the session pulled the published revisions", std::to_string(session_pulled));
    check(reader_session_request_close(session) == READER_SESSION_OK, "the session begins a non-blocking close");
    for (;;) {
      reader_session_observe(session, &snapshot);
      if (snapshot.state == READER_SESSION_CLOSED) break;
      if (std::chrono::steady_clock::now() > deadline) break;
      std::this_thread::sleep_for(std::chrono::milliseconds(20));
    }
    check(snapshot.state == READER_SESSION_CLOSED, "the session worker reached CLOSED");
    check(reader_session_destroy(&session) == READER_SESSION_OK && session == nullptr,
          "the closed session is destroyed");
  }

  /* 11. Close every handle. */
  if (document_a) exr_document_free(document_a);
  close_side(b);
  close_side(a);

  std::printf("checks=%zu failures=%zu pushed=%zu pulled=%zu\n", checks.size(), failures, network_pushed,
              network_pulled);
  std::string document = object()
      .str("probe", "composition")
      .num("check_count", checks.size())
      .num("failures", failures)
      .flag("native_webdav", networked)
      .num("network_pushed", network_pushed)
      .num("network_pulled", network_pulled)
      .num("originals_exported", originals_exported)
      .num("session_pushed", session_pushed)
      .num("session_pulled", session_pulled)
      .num("session_sweeps", session_sweeps)
      .num("metadata_committed", metadata_committed)
      .num("anchor_version", anchor_version)
      .str("resolved_state", resolved_state)
      .num("quote_start", quote_start)
      .num("quote_end", quote_end)
      .set("checks", array(checks))
      .dump();
  std::ofstream output(fs::u8path(args.report), std::ios::binary);
  output << document << "\n";
  return failures ? 1 : 0;
}
}  // namespace

int main(int argc, char **argv) {
  arguments args;
  for (int i = 1; i + 1 < argc; i += 2) {
    const std::string key = argv[i], value = argv[i + 1];
    if (key == "--fixtures") args.fixtures = value;
    else if (key == "--work") args.work = value;
    else if (key == "--report") args.report = value;
    else if (key == "--webdav-root") args.webdav_root = value;
    else if (key == "--sha") {
      const size_t equal = value.find('=');
      if (equal == std::string::npos) { std::fprintf(stderr, "bad --sha\n"); return 2; }
      args.shas[value.substr(0, equal)] = value.substr(equal + 1);
    } else { std::fprintf(stderr, "unknown argument %s\n", key.c_str()); return 2; }
  }
  const char *authorization = std::getenv("READER_TEST_AUTH");
  if (authorization) args.authorization = authorization;
  if (args.fixtures.empty() || args.work.empty() || args.report.empty() || args.shas.count("txt") == 0) {
    std::fprintf(stderr, "usage: probe --fixtures DIR --work DIR --report FILE [--webdav-root URL] --sha role=hex\n");
    return 2;
  }
  try {
    return run(args);
  } catch (const std::exception &error) {
    std::fprintf(stderr, "FATAL %s\n", error.what());
    return 2;
  }
}
