/* SPDX-License-Identifier: MIT */
/* S19 host feature library: the five reviewed optional packages driven through
 * their installed public headers from inside a real product DSO. Every call
 * below is a real business operation on real files created in this job; there
 * is no mock, no in-process stub and no test hook.
 *
 * The DSO links EXReader::exreader (the installed shared SDK) plus the five
 * unchanged module targets, exactly once each, through
 * EXReaderHostFeatureLink. It never links a second SDK copy. */
#include <exreader.h>
#include <reader_font_library.h>
#include <reader_original_export.h>
#include <reader_annotation_export.h>
#include <reader_annotation_import.h>
#include <reader_jump_history.h>
#include <reader_sync_view.h>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <chrono>
#include <iterator>
#include <string>
#include <thread>
#include <vector>

#if defined(_WIN32)
#define EXR_S19_EXPORT __declspec(dllexport)
#else
#define EXR_S19_EXPORT __attribute__((visibility("default")))
#endif

namespace fs = std::filesystem;

extern "C" {
struct exr_host_features_request {
  const char *work;      /* existing private working directory */
  const char *fixtures;  /* directory with font.ttf and book.txt */
  const char *dav_url;   /* real loopback TLS DAV root URL ending in '/' */
  const char *dav_auth;  /* Basic authorization value for that fixture */
  const char *report;    /* JSON report path */
};
EXR_S19_EXPORT int exr_host_features_run(const struct exr_host_features_request *request,
                                          char *error, size_t error_bytes);
EXR_S19_EXPORT const char *exr_host_features_sdk_version(void);
EXR_S19_EXPORT const void *exr_host_features_sdk_version_pointer(void);
EXR_S19_EXPORT int exr_host_features_module_count(void);
}

namespace {

char *g_error = nullptr;
size_t g_error_bytes = 0;

int fail(int code, const std::string &message) {
  if (g_error && g_error_bytes) {
    std::snprintf(g_error, g_error_bytes, "%s", message.c_str());
  }
  std::fprintf(stderr, "S19 feature failure code=%d: %s\n", code, message.c_str());
  return code;
}

std::string read_file(const fs::path &path) {
  std::ifstream stream(path, std::ios::binary);
  std::string data((std::istreambuf_iterator<char>(stream)), std::istreambuf_iterator<char>());
  return data;
}

void write_file(const fs::path &path, const std::string &data) {
  std::ofstream stream(path, std::ios::binary);
  stream.write(data.data(), (std::streamsize)data.size());
}

std::string json_escape(const std::string &value) {
  std::string out = "\"";
  for (unsigned char c : value) {
    if (c == '"' || c == '\\') { out += '\\'; out += (char)c; }
    else if (c < 32) { char buffer[8]; std::snprintf(buffer, sizeof(buffer), "\\u%04x", c); out += buffer; }
    else out += (char)c;
  }
  return out + "\"";
}

std::string number(unsigned long long value) { return std::to_string(value); }

/* ---------------- 1. annotation import/export (one feature, two modules) ----- */
struct annotation_counts {
  int export_status = -1, import_status = -1;
  unsigned long long annotations = 0, head_wires = 0, jsonl_bytes = 0, markdown_bytes = 0;
  unsigned long long created = 0, committed = 0, duplicates = 0, omitted_history = 0;
  int jsonl_published = 0, markdown_published = 0, validated = 0;
  unsigned long long preview_items = 0, preview_metadata = 0, next_index = 0;
  std::string error;
};

const char *const kBookText =
    "A real installed host capture needs enough surrounding text for a stable anchor.";
const char *const kBookTitle = "S19 host feature original";

std::string book_wire(const std::string &id, const std::string &key, size_t bytes) {
  return "{\"version\":1,\"id\":\"" + id + "\",\"entity_kind\":\"book\",\"entity_key\":\"" + key +
         "\",\"operation\":\"put\",\"location_kind\":\"none\",\"parents\":[],\"payload\":{\"format\":\"txt\"," +
         "\"source_sha256\":\"" + key.substr(key.find(':') + 1) + "\",\"source_bytes\":" +
         std::to_string(bytes) + ",\"title\":\"" + kBookTitle + "\",\"author\":\"\",\"favorite\":false}}";
}

std::string revision_id(unsigned sequence) {
  char buffer[33];
  std::snprintf(buffer, sizeof(buffer), "%032x", sequence);
  return buffer;
}

bool receive_wire(reader_revisions *store, const std::string &wire, std::string *error) {
  reader_revision_info info{};
  reader_revision_error revision_error{};
  if (reader_revision_validate(store, wire.data(), wire.size(), nullptr, &info, &revision_error) != READER_REV_OK) {
    *error = std::string("validate: ") + revision_error.message;
    return false;
  }
  std::string sha = info.sha256;
  int created = 0;
  if (reader_revision_receive(store, wire.data(), wire.size(), sha.c_str(), &info, &created,
                              &revision_error) != READER_REV_OK) {
    *error = std::string("receive: ") + revision_error.message;
    return false;
  }
  return true;
}

struct text_capture {
  exr_document *document = nullptr;
  exr_anchor anchor{};
  text_capture() = default;
  text_capture(const text_capture &) = delete;
  text_capture &operator=(const text_capture &) = delete;
  ~text_capture() {
    if (document) {
      exr_anchor_free(&anchor);
      exr_document_free(document);
    }
  }
  bool open(size_t start, size_t end, std::string *error) {
    exr_error sdk_error{};
    if (exr_document_open_memory(EXR_TXT, kBookText, std::strlen(kBookText), &document, &sdk_error) != EXR_OK) {
      *error = std::string("document: ") + sdk_error.message;
      return false;
    }
    if (exr_anchor_create(document, start, end, &anchor, &sdk_error) != EXR_OK) {
      *error = std::string("anchor: ") + sdk_error.message;
      return false;
    }
    return true;
  }
  reader_rs_capture capture() const {
    reader_rs_capture value{};
    value.mode = READER_RS_REFLOW_GLOBAL;
    value.anchor = &anchor;
    return value;
  }
};

int preview_item(void *context, const reader_annotation_import_item *item) {
  annotation_counts *counts = static_cast<annotation_counts *>(context);
  /* Preview before the commit: the real receiving graph, never an invention. */
  counts->preview_items++;
  (void)item;
  return 0;
}

int preview_metadata(void *context, const reader_annotation_import_metadata *metadata) {
  annotation_counts *counts = static_cast<annotation_counts *>(context);
  counts->preview_metadata++;
  (void)metadata;
  return 0;
}

int seed_annotations(const fs::path &work, const std::string &book_key,
                     annotation_counts *counts) {
  reader_revisions *sender = nullptr;
  reader_revision_error revision_error{};
  fs::path store_path = work / "annotations-sender.sqlite";
  if (reader_revisions_open(store_path.string().c_str(), &sender, &revision_error) != READER_REV_OK) {
    counts->error = std::string("open sender: ") + revision_error.message;
    return 11;
  }
  std::string error;
  size_t bytes = std::strlen(kBookText);
  if (!receive_wire(sender, book_wire(revision_id(0x5100), book_key, bytes), &error)) {
    counts->error = "book head: " + error;
    reader_revisions_close(&sender, &revision_error);
    return 12;
  }
  text_capture capture;
  if (!capture.open(2, 12, &error)) {
    counts->error = error;
    reader_revisions_close(&sender, &revision_error);
    return 13;
  }
  reader_rs_capture cap = capture.capture();
  const char *notes[2] = {"first real annotation", "second real annotation"};
  for (unsigned index = 0; index < 2; index++) {
    reader_rs_envelope envelope{};
    envelope.revision_id = nullptr;
    std::string id = revision_id(0x5200 + index);
    std::string annotation = std::string(32, (char)('a' + index));
    envelope.revision_id = id.c_str();
    envelope.operation = "put";
    envelope.entity_kind = "annotation";
    envelope.book_key = book_key.c_str();
    envelope.annotation_id = annotation.c_str();
    envelope.note_text = notes[index];
    envelope.parser_version = exr_version();
    char *wire = nullptr;
    size_t wire_bytes = 0;
    reader_rs_error reading_error{};
    if (reader_rs_encode_v2(sender, &envelope, &cap, 0, &wire, &wire_bytes, &reading_error) != READER_RS_OK) {
      counts->error = std::string("encode: ") + reading_error.message;
      reader_revisions_close(&sender, &revision_error);
      return 14;
    }
    std::string stored(wire, wire_bytes);
    reader_rs_free(wire);
    if (!receive_wire(sender, stored, &error)) {
      counts->error = "annotation head: " + error;
      reader_revisions_close(&sender, &revision_error);
      return 15;
    }
  }
  fs::path jsonl = work / "annotations.jsonl";
  fs::path markdown = work / "annotations.md";
  std::error_code ignored;
  fs::remove(jsonl, ignored);
  fs::remove(markdown, ignored);
  reader_annotation_export_options options{};
  options.struct_size = sizeof(options);
  options.revisions = sender;
  options.book_key = book_key.c_str();
  options.book_title = kBookTitle;
  std::string jsonl_text = jsonl.string();
  std::string markdown_text = markdown.string();
  options.jsonl_path = jsonl_text.c_str();
  options.markdown_path = markdown_text.c_str();
  reader_annotation_export_stats exported{};
  reader_annotation_export_error export_error{};
  counts->export_status = (int)reader_annotation_export_run(&options, &exported, &export_error);
  counts->annotations = exported.annotations;
  counts->head_wires = exported.head_wires;
  counts->jsonl_bytes = exported.jsonl_bytes;
  counts->markdown_bytes = exported.markdown_bytes;
  counts->jsonl_published = exported.jsonl_published;
  counts->markdown_published = exported.markdown_published;
  if (counts->export_status != READER_ANNOTATION_EXPORT_OK) {
    counts->error = std::string("export: ") + export_error.message;
    reader_revisions_close(&sender, &revision_error);
    return 16;
  }
  reader_revisions_close(&sender, &revision_error);

  reader_revisions *receiver = nullptr;
  fs::path receiver_path = work / "annotations-receiver.sqlite";
  fs::remove(receiver_path, ignored);
  if (reader_revisions_open(receiver_path.string().c_str(), &receiver, &revision_error) != READER_REV_OK) {
    counts->error = std::string("open receiver: ") + revision_error.message;
    return 17;
  }
  /* The host already holds the original, so its book head exists in the
   * receiving store before any annotation head is replayed. */
  if (!receive_wire(receiver, book_wire(revision_id(0x5300), book_key, bytes), &error)) {
    counts->error = "receiver book head: " + error;
    reader_revisions_close(&receiver, &revision_error);
    return 17;
  }
  reader_annotation_import_options import{};
  import.struct_size = sizeof(import);
  import.revisions = receiver;
  std::string import_path = jsonl.string();
  import.jsonl_path = import_path.c_str();
  import.target_book_key = book_key.c_str();
  import.item = preview_item;
  import.metadata = preview_metadata;
  import.context = counts;
  reader_annotation_import_stats imported{};
  reader_annotation_import_error import_error{};
  counts->import_status = (int)reader_annotation_import_run(&import, &imported, &import_error);
  counts->created = imported.created;
  counts->committed = imported.committed;
  counts->duplicates = imported.duplicates;
  counts->omitted_history = imported.omitted_history;
  counts->validated = imported.validated;
  counts->next_index = imported.next_index;
  reader_revisions_close(&receiver, &revision_error);
  if (counts->import_status != READER_AI_OK) {
    counts->error = std::string("import: ") + import_error.message;
    return 18;
  }
  return 0;
}

/* ---------------- 2. font library through the SDK lease -------------------- */
struct font_counts {
  int status = -1, created = 0, count = 0, removed = -1, released = -1;
  int glyph_A = 0, glyph_0 = 0;
  unsigned long long bytes = 0, font_count = 0;
  std::string hash;
};

int import_font(const fs::path &work, const fs::path &fixture, font_counts *counts) {
  fs::path directory = work / "fonts";
  fs::create_directories(directory);
  rfl_library *library = nullptr;
  rfl_error error{};
  rfl_limits limits = rfl_limits_default();
  counts->status = (int)rfl_open(directory.string().c_str(), &limits, &library, &error);
  if (counts->status != RFL_OK) return 21;
  rfl_record record{};
  std::string path = fixture.string();
  counts->status = (int)rfl_import_file(library, path.c_str(), "S19 primary font", nullptr, &record,
                                        &counts->created, &error);
  if (counts->status != RFL_OK) {
    rfl_close(library, &error);
    return 22;
  }
  counts->hash = record.hash;
  counts->bytes = record.bytes;
  size_t entries = 0;
  if (rfl_count(library, &entries, &error) != RFL_OK) {
    rfl_close(library, &error);
    return 23;
  }
  counts->count = (int)entries;
  rfl_lease *lease = nullptr;
  if (rfl_font_open(library, record.hash, 0, &lease, &error) != RFL_OK) {
    rfl_close(library, &error);
    return 24;
  }
  exr_font *font = nullptr;
  if (rfl_lease_font(lease, &font, &error) != RFL_OK) {
    rfl_lease_release(lease, &error);
    rfl_close(library, &error);
    return 25;
  }
  /* Real use of the borrowed SDK font; the lease owns it, never exr_font_free. */
  counts->font_count = exr_font_count(font);
  counts->glyph_A = exr_font_has_glyph(font, 0, 'A');
  counts->glyph_0 = exr_font_has_glyph(font, 0, '0');
  counts->released = (int)rfl_lease_release(lease, &error);
  counts->removed = (int)rfl_remove(library, record.hash, &error);
  int closed = (int)rfl_close(library, &error);
  if (counts->released != RFL_OK || counts->removed != RFL_OK || closed != RFL_OK) return 26;
  return 0;
}

/* ---------------- 3. original export through the SDK library --------------- */
struct original_counts {
  int status = -1, committed = 0, created = 0, durable = 0;
  int sdk_status = 0, format = -1;
  unsigned long long bytes = 0, source_bytes = 0;
  int bytes_match = 0;
  std::string sha256, path, display;
};

int owner_enter(void *) { return 0; }
void owner_leave(void *) {}

int export_original(const fs::path &work, const fs::path &book, original_counts *counts,
                    std::string *book_key) {
  exr_library *library = nullptr;
  exr_error sdk_error{};
  fs::path library_path = work / "library.sqlite";
  std::error_code ignored;
  fs::remove(library_path, ignored);
  if (exr_library_open(library_path.string().c_str(), &library, &sdk_error) != EXR_OK) return 31;
  std::string bytes = read_file(book);
  int64_t book_id = 0;
  if (exr_library_import(library, EXR_TXT, bytes.data(), bytes.size(), kBookTitle, &book_id,
                         &sdk_error) != EXR_OK) {
    exr_library_close(library);
    return 32;
  }
  roe_owner owner{owner_enter, owner_leave, nullptr};
  roe_exporter *exporter = nullptr;
  if (roe_create(library, &owner, &exporter) != ROE_OK) {
    exr_library_close(library);
    return 33;
  }
  fs::path directory = work / "originals";
  fs::create_directories(directory);
  roe_selection selection{book_id, "s19-original"};
  std::string directory_path = directory.string();
  roe_options options{};
  options.directory = directory_path.c_str();
  options.naming = ROE_DISPLAY_NAME;
  roe_result *result = nullptr;
  counts->status = (int)roe_run(exporter, &selection, 1, &options, &result);
  if (result && result->count == 1) {
    const roe_item &item = result->items[0];
    counts->committed = item.committed;
    counts->created = item.created;
    counts->durable = item.durable;
    counts->sdk_status = (int)item.sdk_status;
    counts->format = (int)item.format;
    counts->bytes = item.bytes;
    counts->sha256 = item.original_sha256;
    counts->path = item.output_path;
    if (item.output_path[0]) {
      std::string exported = read_file(fs::path(item.output_path));
      counts->bytes_match = exported == bytes;
    }
  } else if (counts->status == ROE_OK) {
    counts->status = -2;
  }
  if (result) roe_result_free(result);
  roe_destroy(&exporter);
  exr_library_close(library);
  counts->source_bytes = bytes.size();
  *book_key = "txt:" + counts->sha256;
  if (counts->status != ROE_OK) return 34;
  if (!counts->committed || !counts->bytes_match) return 35;
  return 0;
}

/* ---------------- 4. jump history over a real landing ---------------------- */
struct history_counts {
  int commits = 0, peek = -1, complete = -1, resolve = -1, open = -1, close = -1;
  unsigned long long count = 0, cursor = 99, cursor_after = 99, wire_bytes = 0, generation = 0;
  int can_back = 0;
  std::string error;
};

int record_history(const fs::path &work, const std::string &book_key, history_counts *counts) {
  reader_revisions *store = nullptr;
  reader_revision_error revision_error{};
  fs::path store_path = work / "history.sqlite";
  std::error_code ignored;
  fs::remove(store_path, ignored);
  if (reader_revisions_open(store_path.string().c_str(), &store, &revision_error) != READER_REV_OK) return 41;
  reader_jh *history = nullptr;
  reader_jh_error history_error{};
  counts->open = (int)reader_jh_open(nullptr, &history, &history_error);
  if (counts->open != READER_JH_OK) {
    reader_revisions_close(&store, &revision_error);
    return 42;
  }
  text_capture first, second;
  std::string error;
  /* History commits a progress position: anchor-v2 progress requires a point,
   * while the annotation path above intentionally captures a selected range. */
  if (!first.open(0, 0, &error) || !second.open(20, 20, &error)) {
    counts->error = error;
    reader_jh_close(&history, &history_error);
    reader_revisions_close(&store, &revision_error);
    return 43;
  }
  const reader_rs_capture captures[2] = {first.capture(), second.capture()};
  for (unsigned index = 0; index < 2; index++) {
    reader_jh_position position{};
    position.book_key = book_key.c_str();
    position.parser_version = exr_version();
    position.kind = index == 0 ? READER_JH_PAGE : READER_JH_SEARCH;
    position.capture = &captures[index];
    position.part = 0;
    reader_jh_result result{};
    reader_jh_status status = reader_jh_commit(history, store, &position, &result, &history_error);
    if (status != READER_JH_OK) {
      /* Closing zeroes the caller's error objects; preserve the actual refusal first. */
      counts->error = "commit index=" + std::to_string(index) +
          " status=" + std::to_string((int)status) +
          " rs=" + std::to_string((int)history_error.rs_code) +
          " gap=" + std::to_string((int)history_error.gap) +
          " revision=" + std::to_string(history_error.revision_code) +
          " message=" + history_error.message;
      reader_jh_close(&history, &history_error);
      reader_revisions_close(&store, &revision_error);
      return 44;
    }
    counts->commits++;
    counts->generation = result.generation;
  }
  reader_jh_state state{};
  state.struct_version = READER_JH_STRUCT_VERSION;
  if (reader_jh_state_get(history, &state, &history_error) != READER_JH_OK ||
      state.count != 2 || state.cursor != 1 || !state.can_back) {
    reader_jh_close(&history, &history_error);
    reader_revisions_close(&store, &revision_error);
    return 45;
  }
  counts->count = state.count;
  counts->cursor = state.cursor;
  counts->can_back = state.can_back;
  reader_jh_item item{};
  counts->peek = (int)reader_jh_peek(history, READER_JH_BACK, &item, &history_error);
  if (counts->peek != READER_JH_OK) {
    reader_jh_close(&history, &history_error);
    reader_revisions_close(&store, &revision_error);
    return 46;
  }
  counts->wire_bytes = item.wire_bytes;
  reader_rs_record record{};
  reader_rs_error reading_error{};
  if (reader_rs_decode(store, item.wire, item.wire_bytes, &record, &reading_error) != READER_RS_OK) {
    reader_jh_item_release(&item);
    reader_jh_close(&history, &history_error);
    reader_revisions_close(&store, &revision_error);
    return 47;
  }
  exr_anchor_match match{};
  reader_rs_status resolved = reader_rs_resolve_reflow(first.document, &record, nullptr, &match, &reading_error);
  counts->resolve = (resolved == READER_RS_OK && match.state == EXR_ANCHOR_FOUND) ? 1 : 0;
  reader_rs_record_free(&record);
  if (!counts->resolve) {
    reader_jh_item_release(&item);
    reader_jh_close(&history, &history_error);
    reader_revisions_close(&store, &revision_error);
    return 48;
  }
  counts->complete = (int)reader_jh_complete(history, &item, &history_error);
  reader_jh_item_release(&item);
  reader_jh_state after{};
  after.struct_version = READER_JH_STRUCT_VERSION;
  reader_jh_state_get(history, &after, &history_error);
  counts->cursor_after = after.cursor;
  counts->close = (int)reader_jh_close(&history, &history_error);
  reader_revisions_close(&store, &revision_error);
  if (counts->complete != READER_JH_OK || counts->cursor_after != 0 || counts->close != READER_JH_OK) return 49;
  return 0;
}

/* ---------------- 5. read-only sync status over a real session ------------ */
struct sync_counts {
  int create = -1, start = -1, cancel = -1, close = -1, destroy = -1, capture = -1, capture_outbox = -1;
  int phase = -1, final_phase = -1, summary_status = -1, observe_state = -1, mirrored = 0;
  int outbox_included = 0;
  unsigned long long shard_count = 0, completed_shards = 0, pending = 0, rows = 0;
  std::string phase_text, cursor;
};

int read_sync_status(const fs::path &work, const char *dav_url, const char *dav_auth,
                     sync_counts *counts) {
  fs::path private_directory = work / "session-private";
  fs::path original_directory = work / "session-originals";
  fs::path store = work / "session-product";
  fs::create_directories(private_directory);
  fs::create_directories(original_directory);
  fs::create_directories(store);
  fs::path product = store / "product.sqlite";
  std::error_code ignored;
  fs::remove(product, ignored);
  reader_session_config config{};
  std::string product_path = product.string();
  std::string private_path = private_directory.string();
  std::string original_path = original_directory.string();
  config.product_path = product_path.c_str();
  config.private_directory = private_path.c_str();
  config.original_directory = original_path.c_str();
  config.account_id = "s19-fixture-account";
  config.dav.root_url = dav_url;
  config.dav.authorization = dav_auth;
  config.dav.timeout_ms = 5000;
  reader_session *session = nullptr;
  counts->create = (int)reader_session_create(&config, &session);
  if (counts->create != READER_SESSION_OK) return 51;
  counts->start = (int)reader_session_start(session);
  reader_sync_view_options options{};
  options.row_limit = 16;
  reader_sync_view_snapshot *snapshot = nullptr;
  reader_sync_view_error view_error{};
  counts->capture = (int)reader_sync_view_capture(session, nullptr, &options, &snapshot, &view_error);
  if (counts->capture == READER_SYNC_VIEW_OK && snapshot) {
    reader_sync_view_summary summary{};
    if (reader_sync_view_summary_get(snapshot, &summary) == READER_SYNC_VIEW_OK) {
      counts->summary_status = 0;
      counts->phase = (int)summary.phase;
      counts->shard_count = summary.shard_count;
      counts->completed_shards = summary.completed_shards;
      counts->pending = summary.pending_records;
      counts->cursor = summary.cursor;
      counts->outbox_included = summary.outbox_included;
    }
    reader_sync_view_release(&snapshot);
  }
  counts->phase_text = reader_sync_view_phase_text((reader_sync_view_phase)counts->phase);
  if (counts->capture != READER_SYNC_VIEW_OK) {
    reader_session_request_close(session);
    reader_session_destroy(&session);
    return 52;
  }
  /* A second capture with a real product store attached reads the outbox page. */
  reader_revisions *store_handle = nullptr;
  reader_revision_error revision_error{};
  fs::path outbox_path = work / "session-outbox.sqlite";
  fs::remove(outbox_path, ignored);
  if (reader_revisions_open(outbox_path.string().c_str(), &store_handle, &revision_error) == READER_REV_OK) {
    reader_sync_view_options with_outbox{};
    with_outbox.row_limit = 8;
    reader_sync_view_snapshot *second = nullptr;
    counts->capture_outbox = (int)reader_sync_view_capture(session, store_handle, &with_outbox, &second, &view_error);
    if (counts->capture_outbox == READER_SYNC_VIEW_OK && second) {
      reader_sync_view_summary summary{};
      if (reader_sync_view_summary_get(second, &summary) == READER_SYNC_VIEW_OK) {
        counts->outbox_included = summary.outbox_included;
        counts->pending = summary.pending_records;
      }
      reader_sync_view_row row{};
      size_t copied = 0;
      if (reader_sync_view_rows(second, 0, &row, 1, &copied) == READER_SYNC_VIEW_OK) counts->rows = copied;
      reader_sync_view_release(&second);
    }
    reader_revisions_close(&store_handle, &revision_error);
  }
  counts->cancel = (int)reader_session_cancel(session);
  for (int attempt = 0; attempt < 200; attempt++) {
    reader_session_snapshot observed{};
    if (reader_session_observe(session, &observed) == READER_SESSION_OK &&
        (observed.state == READER_SESSION_CANCELLED || observed.state == READER_SESSION_FINISHED ||
         observed.state == READER_SESSION_FAILED || observed.state == READER_SESSION_CLOSED)) {
      break;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(25));
  }
  /* At a settled state the view phase and the session state are one-to-one, so
   * the mirror is checked without racing the background worker. */
  {
    reader_sync_view_options settled{};
    settled.row_limit = 4;
    reader_sync_view_snapshot *pair = nullptr;
    reader_sync_view_error pair_error{};
    if (reader_sync_view_capture(session, nullptr, &settled, &pair, &pair_error) == READER_SYNC_VIEW_OK &&
        pair) {
      reader_sync_view_summary summary{};
      if (reader_sync_view_summary_get(pair, &summary) == READER_SYNC_VIEW_OK) {
        counts->final_phase = (int)summary.phase;
        reader_session_snapshot observed{};
        if (reader_session_observe(session, &observed) == READER_SESSION_OK) {
          counts->observe_state = (int)observed.state;
          counts->mirrored = ((int)summary.phase == (int)observed.state) ? 1 : 0;
        }
      }
      reader_sync_view_release(&pair);
    }
  }
  counts->close = (int)reader_session_request_close(session);
  for (int attempt = 0; attempt < 600; attempt++) {
    reader_session_snapshot observed{};
    if (reader_session_observe(session, &observed) == READER_SESSION_OK &&
        observed.state == READER_SESSION_CLOSED) {
      break;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(25));
  }
  counts->destroy = (int)reader_session_destroy(&session);
  /* BUSY is the documented "the worker has not reached CLOSED yet" answer; the
   * code is recorded, and the process exits immediately afterwards. */
  if (counts->destroy != READER_SESSION_OK && counts->destroy != READER_SESSION_BUSY) return 53;
  return 0;
}

}  // namespace

extern "C" EXR_S19_EXPORT const char *exr_host_features_sdk_version(void) { return exr_version(); }

extern "C" EXR_S19_EXPORT const void *exr_host_features_sdk_version_pointer(void) {
  return (const void *)exr_version();
}

extern "C" EXR_S19_EXPORT int exr_host_features_module_count(void) { return 5; }

extern "C" EXR_S19_EXPORT int exr_host_features_run(const struct exr_host_features_request *request,
                                                   char *error, size_t error_bytes) {
  g_error = error;
  g_error_bytes = error_bytes;
  if (error && error_bytes) error[0] = 0;
  if (!request || !request->work || !request->fixtures || !request->report || !request->dav_url) {
    return fail(1, "request needs work, fixtures, dav_url and report");
  }
  fs::path work = fs::path(request->work);
  fs::path fixtures = fs::path(request->fixtures);
  fs::create_directories(work);
  fs::path font = fixtures / (std::string("font.ttf"));
  fs::path book = fixtures / (std::string("book.txt"));
  if (!fs::exists(font) || !fs::exists(book)) return fail(2, "fixtures font.ttf/book.txt missing");

  font_counts fonts;
  int code = import_font(work, font, &fonts);
  if (code) return fail(code, "font library failed at step " + std::to_string(code));

  original_counts originals;
  std::string book_key;
  code = export_original(work, book, &originals, &book_key);
  if (code) return fail(code, "original export failed at step " + std::to_string(code));

  annotation_counts annotations;
  code = seed_annotations(work, book_key, &annotations);
  if (code) return fail(code, "annotations failed: " + annotations.error);

  history_counts history;
  code = record_history(work, book_key, &history);
  if (code) return fail(code, "jump history failed at step " + std::to_string(code) + ": " + history.error);

  sync_counts sync;
  code = read_sync_status(work, request->dav_url, request->dav_auth, &sync);
  if (code) return fail(code, "sync status failed at step " + std::to_string(code));

  std::string report = "{";
  report += "\"sdk_version\":" + json_escape(exr_version()) + ",";
  report += "\"sdk_version_pointer\":" +
            number((unsigned long long)(uintptr_t)exr_version()) + ",";
  report += "\"modules\":" + number(5) + ",";
  report += "\"font\":{" + std::string("\"imported\":") + number(fonts.created) +
            ",\"entries\":" + number(fonts.count) + ",\"bytes\":" + number(fonts.bytes) +
            ",\"hash\":" + json_escape(fonts.hash) + ",\"font_count\":" + number(fonts.font_count) +
            ",\"glyph_A\":" + number(fonts.glyph_A) + ",\"glyph_0\":" + number(fonts.glyph_0) +
            ",\"released\":" + number(fonts.released) + ",\"removed\":" + number(fonts.removed) + "},";
  report += "\"original\":{\"status\":" + number(originals.status) +
            ",\"committed\":" + number(originals.committed) + ",\"created\":" + number(originals.created) +
            ",\"durable\":" + number(originals.durable) + ",\"format\":" + number(originals.format) +
            ",\"bytes\":" + number(originals.bytes) + ",\"source_bytes\":" + number(originals.source_bytes) +
            ",\"bytes_match\":" + number(originals.bytes_match) +
            ",\"sha256\":" + json_escape(originals.sha256) +
            ",\"path\":" + json_escape(originals.path) + "},";
  report += "\"book_key\":" + json_escape(book_key) + ",";
  report += "\"annotations\":{\"export_status\":" + number(annotations.export_status) +
            ",\"annotations\":" + number(annotations.annotations) +
            ",\"head_wires\":" + number(annotations.head_wires) +
            ",\"jsonl_published\":" + number(annotations.jsonl_published) +
            ",\"markdown_published\":" + number(annotations.markdown_published) +
            ",\"jsonl_bytes\":" + number(annotations.jsonl_bytes) +
            ",\"markdown_bytes\":" + number(annotations.markdown_bytes) +
            ",\"import_status\":" + number(annotations.import_status) +
            ",\"validated\":" + number(annotations.validated) +
            ",\"created\":" + number(annotations.created) +
            ",\"committed\":" + number(annotations.committed) +
            ",\"duplicates\":" + number(annotations.duplicates) +
            ",\"omitted_history\":" + number(annotations.omitted_history) +
            ",\"next_index\":" + number(annotations.next_index) +
            ",\"preview_items\":" + number(annotations.preview_items) +
            ",\"preview_metadata\":" + number(annotations.preview_metadata) + "},";
  report += "\"history\":{\"commits\":" + number(history.commits) + ",\"count\":" + number(history.count) +
            ",\"cursor\":" + number(history.cursor) + ",\"can_back\":" + number(history.can_back) +
            ",\"peek\":" + number(history.peek) + ",\"resolve\":" + number(history.resolve) +
            ",\"complete\":" + number(history.complete) + ",\"cursor_after\":" + number(history.cursor_after) +
            ",\"wire_bytes\":" + number(history.wire_bytes) + ",\"generation\":" + number(history.generation) +
            ",\"closed\":" + number(history.close) + "},";
  report += "\"sync\":{\"create\":" + number(sync.create) + ",\"start\":" + number(sync.start) +
            ",\"capture\":" + number(sync.capture) + ",\"capture_outbox\":" + number(sync.capture_outbox) +
            ",\"phase\":" + number(sync.phase) + ",\"final_phase\":" + number(sync.final_phase) +
            ",\"phase_text\":" + json_escape(sync.phase_text) +
            ",\"summary_status\":" + number(sync.summary_status) +
            ",\"observe_state\":" + number(sync.observe_state) + ",\"mirrored\":" + number(sync.mirrored) +
            ",\"outbox_included\":" + number(sync.outbox_included) +
            ",\"shard_count\":" + number(sync.shard_count) +
            ",\"completed_shards\":" + number(sync.completed_shards) +
            ",\"pending\":" + number(sync.pending) + ",\"rows\":" + number(sync.rows) +
            ",\"cursor\":" + json_escape(sync.cursor) + ",\"cancel\":" + number(sync.cancel) +
            ",\"close\":" + number(sync.close) + ",\"destroy\":" + number(sync.destroy) + "}}";
  write_file(fs::path(request->report), report);
  return 0;
}
