/* SPDX-License-Identifier: MIT */
/* Installed C++ consumer for the reader application boundaries.

   It is compiled only against installed packages (preferences, revisions and
   reading-state) and never reaches into a source tree. Every public call is
   wrapped so a C++ exception that escapes a C ABI is a named failure instead of
   a green run. The same translation unit carries the bounded, deterministic
   mutation loop and the single-case replay entry used after a sanitizer abort. */

#include <reader_preferences.h>
#include <reader_reading_state.h>
#include <reader_revisions.h>

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

namespace {

struct violation {
  std::string text;
};
struct escaped_exception {
  std::string call;
};

/* A real C++ exception crossing a public C ABI is a boundary defect, not input
   data: it is reported under its own name and never converted into a status. */
template <class Status, class Call> Status abi(const char *name, Call call) {
  try {
    return call();
  } catch (const violation &) {
    throw;
  } catch (...) {
    throw escaped_exception{name};
  }
}

void require(bool condition, const char *text) {
  if (!condition) throw violation{text};
}

std::string quote(const std::string &value) {
  std::string out(1, '"');
  for (unsigned char c : value) {
    if (c == '"' || c == '\\') {
      out += '\\';
      out += static_cast<char>(c);
    } else if (c < 0x20) {
      char buffer[8];
      std::snprintf(buffer, sizeof buffer, "\\u%04x", static_cast<unsigned>(c));
      out += buffer;
    } else {
      out += static_cast<char>(c);
    }
  }
  out += '"';
  return out;
}

void field(std::string &out, const char *key, const std::string &value) {
  if (!out.empty()) out += ',';
  out += quote(key);
  out += ':';
  out += value;
}
void number(std::string &out, const char *key, long long value) {
  field(out, key, std::to_string(value));
}
void boolean(std::string &out, const char *key, bool value) {
  field(out, key, value ? "true" : "false");
}
std::string decimal(float value) {
  char buffer[48];
  std::snprintf(buffer, sizeof buffer, "%.6g", static_cast<double>(value));
  return std::string(buffer);
}
std::string color(const uint8_t value[4]) {
  char buffer[16];
  std::snprintf(buffer, sizeof buffer, "#%02X%02X%02X%02X", static_cast<unsigned>(value[0]),
                static_cast<unsigned>(value[1]), static_cast<unsigned>(value[2]),
                static_cast<unsigned>(value[3]));
  return std::string(buffer);
}
void emit(const std::string &fields) { std::cout << "{" << fields << "}\n"; }

bool read_file(const std::string &path, std::string &out) {
  std::ifstream input(std::filesystem::u8path(path), std::ios::binary);
  if (!input) return false;
  std::ostringstream data;
  data << input.rdbuf();
  out = data.str();
  return true;
}
bool write_file(const std::string &path, const std::string &data) {
  std::ofstream output(std::filesystem::u8path(path), std::ios::binary | std::ios::trunc);
  if (!output) return false;
  output.write(data.data(), static_cast<std::streamsize>(data.size()));
  output.flush();
  return static_cast<bool>(output);
}
void remove_file(const std::string &path) {
  std::error_code ignored;
  (void)std::filesystem::remove(std::filesystem::u8path(path), ignored);
}

/* ------------------------------------------------------------------ */
/* preferences: settings-file boundary                                 */
/* ------------------------------------------------------------------ */

bool preferences_known(int value) { return value >= 0 && value <= 7; }

const char *preferences_name(reader_preferences_status status) {
  const char *name = reader_preferences_status_name(status);
  return name ? name : "";
}

reader_preferences sentinel() {
  reader_preferences value = reader_preferences_defaults();
  value.font_size = 7.25f;
  value.line_spacing = 2.5f;
  value.paragraph_spacing = 1.5f;
  value.margin = 3.5f;
  value.theme = static_cast<uint32_t>(READER_PREFERENCES_THEME_DARK);
  value.page_turn_direction = static_cast<uint32_t>(READER_PREFERENCES_TURN_RTL);
  value.page_turn_input = static_cast<uint32_t>(READER_PREFERENCES_INPUT_SWIPE);
  value.fixed_page_zoom = 250;
  return value;
}

void append_record(std::string &out, const reader_preferences &value) {
  field(out, "font_size", decimal(value.font_size));
  field(out, "line_spacing", decimal(value.line_spacing));
  field(out, "paragraph_spacing", decimal(value.paragraph_spacing));
  field(out, "margin", decimal(value.margin));
  number(out, "theme", static_cast<long long>(value.theme));
  number(out, "page_turn_direction", static_cast<long long>(value.page_turn_direction));
  number(out, "page_turn_input", static_cast<long long>(value.page_turn_input));
  number(out, "fixed_page_zoom", static_cast<long long>(value.fixed_page_zoom));
  field(out, "light_foreground", quote(color(value.light_foreground)));
  field(out, "light_background", quote(color(value.light_background)));
  field(out, "dark_foreground", quote(color(value.dark_foreground)));
  field(out, "dark_background", quote(color(value.dark_background)));
}

std::string preferences_observe(const std::string &bytes, const std::string &path,
                                size_t limit) {
  require(write_file(path, bytes), "cannot stage the preferences case");
  reader_preferences value = sentinel();
  const reader_preferences before = value;
  reader_preferences_load_options options{};
  reader_preferences_load_options *pointer = nullptr;
  if (limit != 0) {
    options.struct_size = static_cast<uint32_t>(sizeof(options));
    options.max_file_bytes = limit;
    pointer = &options;
  }
  reader_preferences_error error{};
  reader_preferences_status status = abi<reader_preferences_status>(
      "reader_preferences_load",
      [&] { return reader_preferences_load(path.c_str(), &value, pointer, &error); });
  require(preferences_known(static_cast<int>(status)), "load status is outside the documented set");
  require(std::memchr(error.message, 0, sizeof(error.message)) != nullptr,
          "load error message is not NUL terminated");
  const bool changed = std::memcmp(&before, &value, sizeof(value)) != 0;
  if (status != READER_PREFERENCES_OK) {
    require(!changed, "a failed load modified the caller record");
  } else {
    reader_preferences_error validate_error{};
    require(reader_preferences_validate(&value, &validate_error) == READER_PREFERENCES_OK,
            "a loaded record does not validate");
  }
  std::string out;
  number(out, "status", static_cast<long long>(status));
  field(out, "name", quote(preferences_name(status)));
  field(out, "message", quote(std::string(error.message, std::strlen(error.message))));
  number(out, "offset", static_cast<long long>(error.offset));
  number(out, "system_error", static_cast<long long>(error.system_error));
  boolean(out, "memory_changed", changed);
  append_record(out, value);
  return out;
}

/* ------------------------------------------------------------------ */
/* revisions and reading wire                                          */
/* ------------------------------------------------------------------ */

bool revision_known(int value) { return value >= 0 && value <= 12; }
bool reading_known(int value) { return value >= 0 && value <= 7; }

const char *revision_name(reader_revision_status status) {
  switch (status) {
    case READER_REV_OK: return "OK";
    case READER_REV_ARGUMENT: return "ARGUMENT";
    case READER_REV_MEMORY: return "MEMORY";
    case READER_REV_DATABASE: return "DATABASE";
    case READER_REV_FORMAT: return "FORMAT";
    case READER_REV_LIMIT: return "LIMIT";
    case READER_REV_HASH: return "HASH";
    case READER_REV_COLLISION: return "COLLISION";
    case READER_REV_MISSING_PARENT: return "MISSING_PARENT";
    case READER_REV_CYCLE: return "CYCLE";
    case READER_REV_UNSAFE: return "UNSAFE";
    case READER_REV_OWNER: return "OWNER";
    case READER_REV_NOT_FOUND: return "NOT_FOUND";
    default: return "UNKNOWN";
  }
}
const char *reading_name(reader_rs_status status) {
  switch (status) {
    case READER_RS_OK: return "OK";
    case READER_RS_ARGUMENT: return "ARGUMENT";
    case READER_RS_MEMORY: return "MEMORY";
    case READER_RS_SDK: return "SDK";
    case READER_RS_REVISION: return "REVISION";
    case READER_RS_NOT_REPRESENTABLE: return "NOT_REPRESENTABLE";
    case READER_RS_UNRESOLVED: return "UNRESOLVED";
    case READER_RS_IDENTITY: return "IDENTITY";
    default: return "UNKNOWN";
  }
}

struct store_handle {
  reader_revisions *store = nullptr;
  reader_revision_error error{};

  reader_revision_status open(const std::string &path) {
    return abi<reader_revision_status>(
        "reader_revisions_open",
        [&] { return reader_revisions_open(path.c_str(), &store, &error); });
  }
  ~store_handle() {
    if (!store) return;
    try {
      reader_revision_error ignored{};
      reader_revisions_close(&store, &ignored);
    } catch (...) {
      store = nullptr;
    }
  }
  store_handle() = default;
  store_handle(const store_handle &) = delete;
  store_handle &operator=(const store_handle &) = delete;

  void close() {
    if (!store) return;
    reader_revision_error close_error{};
    reader_revision_status status = abi<reader_revision_status>(
        "reader_revisions_close", [&] { return reader_revisions_close(&store, &close_error); });
    require(status == READER_REV_OK, "the product catalog did not close cleanly");
    require(store == nullptr, "close did not release the store");
  }
};

struct rs_wire_guard {
  char *value = nullptr;
  ~rs_wire_guard() { reader_rs_free(value); }
  rs_wire_guard() = default;
  rs_wire_guard(const rs_wire_guard &) = delete;
  rs_wire_guard &operator=(const rs_wire_guard &) = delete;
};
struct revision_bytes_guard {
  char *value = nullptr;
  ~revision_bytes_guard() { reader_revision_bytes_free(value); }
  revision_bytes_guard() = default;
  revision_bytes_guard(const revision_bytes_guard &) = delete;
  revision_bytes_guard &operator=(const revision_bytes_guard &) = delete;
};
struct record_guard {
  reader_rs_record *value;
  explicit record_guard(reader_rs_record *record) : value(record) {}
  ~record_guard() { reader_rs_record_free(value); }
  record_guard(const record_guard &) = delete;
  record_guard &operator=(const record_guard &) = delete;
};

struct outbox_observer {
  std::vector<std::string> ids;
  std::vector<long long> attempts;
  std::vector<std::string> errors;
};

int outbox_visit(void *opaque, const reader_revision_outbox_row *row) {
  auto *observer = static_cast<outbox_observer *>(opaque);
  observer->ids.emplace_back(row->info.revision_id);
  observer->attempts.push_back(static_cast<long long>(row->attempts));
  observer->errors.emplace_back(row->last_error ? row->last_error : "");
  return 0;
}

outbox_observer read_outbox(reader_revisions *store) {
  outbox_observer observer;
  reader_revision_error error{};
  reader_revision_status status = abi<reader_revision_status>(
      "reader_revision_outbox",
      [&] { return reader_revision_outbox(store, 100, outbox_visit, &observer, &error); });
  require(status == READER_REV_OK, "the outbox could not be read");
  return observer;
}

void append_info(std::string &out, const reader_revision_info &info) {
  field(out, "revision_id", quote(info.revision_id));
  field(out, "entity_kind", quote(info.entity_kind));
  field(out, "entity_key", quote(info.entity_key));
  field(out, "operation", quote(info.operation));
  field(out, "location_kind", quote(info.location_kind));
  field(out, "sha256", quote(info.sha256));
  number(out, "bytes", static_cast<long long>(info.bytes));
  number(out, "parent_count", static_cast<long long>(info.parent_count));
  field(out, "book_key", quote(info.book_key));
  number(out, "source_bytes", static_cast<long long>(info.source_bytes));
}

std::string wire_validate_observe(reader_revisions *store, const std::string &bytes,
                                  const char *expected) {
  reader_revision_info info{};
  reader_revision_error error{};
  reader_revision_status status = abi<reader_revision_status>(
      "reader_revision_validate", [&] {
        return reader_revision_validate(store, bytes.data(), bytes.size(), expected, &info,
                                        &error);
      });
  require(revision_known(static_cast<int>(status)),
          "validate status is outside the documented set");
  require(std::memchr(error.message, 0, sizeof(error.message)) != nullptr,
          "validate error message is not NUL terminated");
  if (status != READER_REV_OK) {
    reader_revision_info zero{};
    require(std::memcmp(&zero, &info, sizeof(info)) == 0,
            "a failed validate published stale revision info");
  } else {
    require(info.bytes == bytes.size(), "a validated byte count differs from the input");
    require(std::strlen(info.sha256) == 64, "a validated SHA-256 is not 64 characters");
    require(info.sha256[0] != 0, "a validated SHA-256 is empty");
  }
  std::string out;
  number(out, "status", static_cast<long long>(status));
  field(out, "name", quote(revision_name(status)));
  field(out, "message", quote(std::string(error.message, std::strlen(error.message))));
  append_info(out, info);
  return out;
}

std::string wire_decode_observe(reader_revisions *store, const std::string &bytes) {
  reader_rs_record record{};
  record_guard guard{&record};
  reader_rs_error error{};
  reader_rs_status status = abi<reader_rs_status>("reader_rs_decode", [&] {
    return reader_rs_decode(store, bytes.data(), bytes.size(), &record, &error);
  });
  require(reading_known(static_cast<int>(status)),
          "decode status is outside the documented set");
  require(std::memchr(error.message, 0, sizeof(error.message)) != nullptr,
          "decode error message is not NUL terminated");
  std::string out;
  number(out, "status", static_cast<long long>(status));
  field(out, "name", quote(reading_name(status)));
  field(out, "message", quote(std::string(error.message, std::strlen(error.message))));
  if (status == READER_RS_OK) {
    require(record.entity_kind[0] != 0, "a decoded entity kind is empty");
    require(record.operation[0] != 0, "a decoded operation is empty");
    require(record.has_location == 0 || record.has_location == 1,
            "the decoded location flag is not a boolean");
    if (record.has_location) {
      require(record.mode == READER_RS_REFLOW_GLOBAL || record.mode == READER_RS_EPUB_CHAPTER ||
                  record.mode == READER_RS_FIXED_PAGE,
              "the decoded mode is outside the documented set");
      require(record.exact != nullptr, "the decoded selector has no exact text");
      require(record.anchor_version == 1 || record.anchor_version == 2,
              "the decoded anchor version is outside 1/2");
      if (record.anchor_version == 2) {
        require(record.end >= record.start && record.end - record.start == record.exact_size,
                "the decoded span disagrees with the quote bytes");
      }
      if (record.mode == READER_RS_EPUB_CHAPTER) {
        require(record.part_path != nullptr, "an EPUB decode lost its part path");
      }
      if (record.mode == READER_RS_FIXED_PAGE) {
        require(record.page_id != nullptr, "a fixed-page decode lost its page id");
      }
    }
    field(out, "entity_kind", quote(record.entity_kind));
    field(out, "operation", quote(record.operation));
    field(out, "book_key", quote(record.book_key));
    field(out, "annotation_id", quote(record.annotation_id));
    number(out, "mode", static_cast<long long>(record.mode));
    number(out, "has_location", static_cast<long long>(record.has_location));
    field(out, "parser_version", quote(record.parser_version));
    number(out, "anchor_version", static_cast<long long>(record.anchor_version));
    number(out, "start", static_cast<long long>(record.start));
    number(out, "end", static_cast<long long>(record.end));
    number(out, "exact_size", static_cast<long long>(record.exact_size));
    number(out, "page", static_cast<long long>(record.page));
    number(out, "part", static_cast<long long>(record.part));
    field(out, "part_path", record.part_path ? quote(record.part_path) : "null");
    field(out, "page_id", record.page_id ? quote(record.page_id) : "null");
    field(out, "chapter", record.chapter ? quote(record.chapter) : "null");
    field(out, "exact",
          record.exact ? quote(std::string(record.exact, record.exact_size)) : "null");
  } else {
    reader_rs_record zero{};
    require(std::memcmp(&zero, &record, sizeof(record)) == 0,
            "a failed decode left a partially filled record");
  }
  return out;
}

std::string readable_bytes(reader_revisions *store, const reader_revision_info &info,
                              const std::string &expected) {
  revision_bytes_guard retained;
  size_t retained_bytes = 0;
  reader_revision_info fetched{};
  reader_revision_error error{};
  reader_revision_status status = abi<reader_revision_status>(
      "reader_revision_get", [&] {
        return reader_revision_get(store, info.revision_id, &retained.value, &retained_bytes,
                                   &fetched, &error);
      });
  require(status == READER_REV_OK && retained.value != nullptr,
          "a retained revision is not readable");
  require(std::string(retained.value, retained_bytes) == expected,
          "the retained bytes differ from the input");
  require(std::memcmp(&fetched, &info, sizeof(info)) == 0,
          "the retained metadata differs from the accepted one");
  return "readable";
}

/* Validate-then-receive: the module itself produces the transport SHA, so the
   loop never has to guess one. A refused validation uses a fixed wrong SHA so
   the refusal path is still exercised. Remote receive stores history only and
   never queues a local outbox row. */
std::string wire_receive_observe(reader_revisions *store, const std::string &bytes) {
  reader_revision_info validated{};
  reader_revision_error error{};
  reader_revision_status validated_status = abi<reader_revision_status>(
      "reader_revision_validate", [&] {
        return reader_revision_validate(store, bytes.data(), bytes.size(), nullptr, &validated,
                                        &error);
      });
  require(revision_known(static_cast<int>(validated_status)),
          "pre-receive validate status is outside the documented set");
  const char *sha =
      validated_status == READER_REV_OK
          ? validated.sha256
          : "0000000000000000000000000000000000000000000000000000000000000000";
  const outbox_observer before = read_outbox(store);
  reader_revision_info info{};
  reader_revision_error receive_error{};
  int created = 0;
  reader_revision_status received = abi<reader_revision_status>(
      "reader_revision_receive", [&] {
        return reader_revision_receive(store, bytes.data(), bytes.size(), sha, &info, &created,
                                       &receive_error);
      });
  require(revision_known(static_cast<int>(received)),
          "receive status is outside the documented set");
  require(created == 0 || created == 1, "receive created flag is not a boolean");
  require(std::memchr(receive_error.message, 0, sizeof(receive_error.message)) != nullptr,
          "receive error message is not NUL terminated");
  const outbox_observer after = read_outbox(store);
  require(after.ids.size() == before.ids.size(),
          "a remote receive changed the local pending queue");
  if (created) {
    require(received == READER_REV_OK, "a created revision reported a failure status");
    require(std::memcmp(&info, &validated, sizeof(info)) == 0,
            "the accepted revision metadata differs from the validated one");
    (void)readable_bytes(store, info, bytes);
  }
  std::string out;
  number(out, "status", static_cast<long long>(received));
  field(out, "name", quote(revision_name(received)));
  field(out, "message",
        quote(std::string(receive_error.message, std::strlen(receive_error.message))));
  number(out, "created", created);
  number(out, "validated_status", static_cast<long long>(validated_status));
  append_info(out, info);
  return out;
}

/* Local pending intent: a created local revision must add exactly one outbox
   row, stay byte-identical when read back, and let one verified ack remove only
   the queue row while history stays. */
std::string wire_local_observe(reader_revisions *store, const std::string &bytes) {
  reader_revision_info validated{};
  reader_revision_error validate_error{};
  reader_revision_status validated_status = abi<reader_revision_status>(
      "reader_revision_validate", [&] {
        return reader_revision_validate(store, bytes.data(), bytes.size(), nullptr, &validated,
                                        &validate_error);
      });
  require(revision_known(static_cast<int>(validated_status)),
          "pre-local validate status is outside the documented set");
  const outbox_observer before = read_outbox(store);
  reader_revision_info info{};
  reader_revision_error local_error{};
  int created = 0;
  reader_revision_status status = abi<reader_revision_status>(
      "reader_revision_local", [&] {
        return reader_revision_local(store, bytes.data(), bytes.size(), &info, &created,
                                     &local_error);
      });
  require(revision_known(static_cast<int>(status)),
          "local status is outside the documented set");
  require(created == 0 || created == 1, "local created flag is not a boolean");
  require(std::memchr(local_error.message, 0, sizeof(local_error.message)) != nullptr,
          "local error message is not NUL terminated");
  const outbox_observer after = read_outbox(store);
  if (created) {
    require(status == READER_REV_OK, "a created local revision reported a failure status");
    require(after.ids.size() == before.ids.size() + 1,
            "an accepted local revision did not queue exactly one row");
    (void)readable_bytes(store, info, bytes);
    reader_revision_error ack_error{};
    reader_revision_status acked = abi<reader_revision_status>(
        "reader_revision_ack", [&] {
          return reader_revision_ack(store, info.revision_id, info.sha256, &ack_error);
        });
    require(acked == READER_REV_OK, "a freshly queued revision could not be acknowledged");
    const outbox_observer drained = read_outbox(store);
    require(drained.ids.size() == before.ids.size(),
            "acknowledgement did not remove exactly the queued row");
  } else {
    require(after.ids.size() == before.ids.size(),
            "a refused or duplicate local write changed the pending queue");
  }
  std::string out;
  number(out, "status", static_cast<long long>(status));
  field(out, "name", quote(revision_name(status)));
  field(out, "message", quote(std::string(local_error.message, std::strlen(local_error.message))));
  number(out, "created", created);
  number(out, "validated_status", static_cast<long long>(validated_status));
  append_info(out, info);
  return out;
}

/* ------------------------------------------------------------------ */
/* deterministic mutation                                              */
/* ------------------------------------------------------------------ */

struct rng {
  uint64_t state;
  uint64_t next() {
    state += 0x9e3779b97f4a7c15ULL;
    uint64_t value = state;
    value = (value ^ (value >> 30)) * 0xbf58476d1ce4e5b9ULL;
    value = (value ^ (value >> 27)) * 0x94d049bb133111ebULL;
    return value ^ (value >> 31);
  }
};

const char *const kPreferencesTokens[] = {
    "\"", "}", "{", ",", ":", "0", "1", "-1", "1e999", "true", "null",
    "\"system\"", "\"#FFFFFF\"", "\xef\xbb\xbf", "font_size", "format_version", "margin"};
const char *const kWireTokens[] = {"\"", "}", ",",       ":",         "null",    "true",
                                   "0",  "1", "-1",      "[]",        "{}",      "\xc3\x28",
                                   "entity_kind", "progress", "annotation", "selector",
                                   "parents", "exact"};

std::string mutate(const std::string &base, rng &random, size_t cap,
                   const char *const *tokens, size_t token_count) {
  std::string out = base;
  if (out.size() > cap) out.resize(cap);
  const size_t operations = 1u + static_cast<size_t>(random.next() % 6u);
  for (size_t op = 0; op < operations; ++op) {
    if (out.empty()) {
      out.push_back(static_cast<char>('a' + static_cast<unsigned>(random.next() % 26u)));
      continue;
    }
    const size_t at = static_cast<size_t>(random.next() % out.size());
    switch (static_cast<unsigned>(random.next() % 12u)) {
      case 0:
        out[at] = static_cast<char>(out[at] ^ static_cast<char>(1u << (random.next() % 8u)));
        break;
      case 1:
        out[at] = static_cast<char>(random.next() & 0xffu);
        break;
      case 2:
        if (out.size() < cap) {
          out.insert(out.begin() + static_cast<long>(at),
                     static_cast<char>(random.next() & 0xffu));
        }
        break;
      case 3: {
        size_t count = 1u + static_cast<size_t>(random.next() % 8u);
        count = std::min(count, out.size() - at);
        out.erase(at, count);
        break;
      }
      case 4: {
        size_t count = 1u + static_cast<size_t>(random.next() % 16u);
        count = std::min(count, out.size() - at);
        out.insert(at, out.substr(at, count));
        break;
      }
      case 5: {
        const std::string token(tokens[random.next() % token_count]);
        if (out.size() + token.size() <= cap) out += token;
        break;
      }
      case 6:
        if (at + 1 < out.size()) std::swap(out[at], out[at + 1]);
        break;
      case 7:
        out.resize(at);
        break;
      case 8:
        out[at] = static_cast<char>('0' + static_cast<unsigned>(random.next() % 10u));
        break;
      case 9: {
        size_t count = 1u + static_cast<size_t>(random.next() % 32u);
        if (out.size() + count <= cap) {
          const char filler = static_cast<char>(' ' + static_cast<unsigned>(random.next() % 0x5eu));
          out.insert(at, std::string(count, filler));
        }
        break;
      }
      case 10: {
        const size_t other = static_cast<size_t>(random.next() % out.size());
        if (other != at) std::swap(out[at], out[other]);
        break;
      }
      default:
        out.push_back(static_cast<char>(random.next() & 0xffu));
        break;
    }
  }
  return out;
}

/* ------------------------------------------------------------------ */
/* case contexts                                                       */
/* ------------------------------------------------------------------ */

struct case_context {
  std::string workdir;
  std::string database;
  std::string preferences_path;
  reader_revisions *store = nullptr;
};

std::string observe(const std::string &target, case_context &context, const std::string &bytes) {
  if (target == "preferences") {
    return preferences_observe(bytes, context.preferences_path, 0);
  }
  require(context.store != nullptr, "wire targets need an opened product catalog");
  if (target == "wire-validate") return wire_validate_observe(context.store, bytes, nullptr);
  if (target == "wire-decode") return wire_decode_observe(context.store, bytes);
  if (target == "wire-receive") return wire_receive_observe(context.store, bytes);
  if (target == "wire-local") return wire_local_observe(context.store, bytes);
  throw violation{"unknown fuzz target"};
}

/* ------------------------------------------------------------------ */
/* commands                                                            */
/* ------------------------------------------------------------------ */

int command_preferences_defaults() {
  std::string out;
  append_record(out, reader_preferences_defaults());
  number(out, "abi_version", static_cast<long long>(reader_preferences_abi_version()));
  number(out, "struct_size", static_cast<long long>(sizeof(reader_preferences)));
  emit(out);
  return 0;
}

int command_preferences_load(const std::vector<std::string> &args) {
  require(args.size() >= 3, "preferences-load needs a path");
  const size_t limit = args.size() > 3 ? static_cast<size_t>(std::stoull(args[3])) : 0;
  std::string bytes;
  require(read_file(args[2], bytes), "the preferences case is unreadable");
  case_context context{"", "", args[2] + ".staged", nullptr};
  emit(preferences_observe(bytes, context.preferences_path, limit));
  return 0;
}

int command_preferences_save(const std::vector<std::string> &args) {
  require(args.size() >= 4, "preferences-save needs a path and a preset");
  reader_preferences value = reader_preferences_defaults();
  if (args[3] == "custom") {
    value.font_size = 33.5f;
    value.line_spacing = 1.75f;
    value.paragraph_spacing = 20.0f;
    value.margin = 64.0f;
    value.theme = static_cast<uint32_t>(READER_PREFERENCES_THEME_DARK);
    value.page_turn_direction = static_cast<uint32_t>(READER_PREFERENCES_TURN_RTL);
    value.page_turn_input = static_cast<uint32_t>(READER_PREFERENCES_INPUT_HARDWARE_KEYS);
    value.fixed_page_zoom = 175;
    value.dark_foreground[0] = 0x11u;
    value.dark_background[3] = 0xfeu;
  } else if (args[3] == "invalid") {
    value.font_size = 3.0f;
  } else {
    require(args[3] == "defaults", "unknown save preset");
  }
  reader_preferences_error error{};
  reader_preferences_status status = abi<reader_preferences_status>(
      "reader_preferences_save",
      [&] { return reader_preferences_save(&value, args[2].c_str(), nullptr, &error); });
  require(preferences_known(static_cast<int>(status)), "save status is outside the documented set");
  require(std::memchr(error.message, 0, sizeof(error.message)) != nullptr,
          "save error message is not NUL terminated");
  std::string out;
  number(out, "status", static_cast<long long>(status));
  field(out, "name", quote(preferences_name(status)));
  field(out, "message", quote(std::string(error.message, std::strlen(error.message))));
  emit(out);
  return 0;
}

int command_preferences_status_name(const std::vector<std::string> &args) {
  require(args.size() >= 3, "preferences-status-name needs a value");
  const int raw = std::stoi(args[2]);
  const char *name = reader_preferences_status_name(static_cast<reader_preferences_status>(raw));
  require(name != nullptr, "status name is null");
  require(std::strlen(name) < 32, "status name is not a bounded static string");
  std::string out;
  number(out, "value", raw);
  field(out, "name", quote(name));
  emit(out);
  return 0;
}

int command_preferences_import_legacy(const std::vector<std::string> &args) {
  require(args.size() >= 3, "preferences-import-legacy needs a mask");
  const bool invalid_merge = args.size() > 3 && args[3] == "invalid";
  reader_preferences value = reader_preferences_defaults();
  reader_preferences_legacy legacy{};
  legacy.struct_size = static_cast<uint32_t>(sizeof(legacy));
  legacy.present = static_cast<uint32_t>(std::stoul(args[2], nullptr, 0));
  legacy.font_size = invalid_merge ? 1.0f : 30.0f;
  legacy.line_spacing = 2.0f;
  legacy.paragraph_spacing = 4.0f;
  legacy.margin = 30.0f;
  legacy.theme = static_cast<uint32_t>(READER_PREFERENCES_THEME_DARK);
  legacy.page_turn_direction = static_cast<uint32_t>(READER_PREFERENCES_TURN_RTL);
  legacy.page_turn_input = static_cast<uint32_t>(READER_PREFERENCES_INPUT_SWIPE);
  legacy.fixed_page_zoom = 250;
  for (int i = 0; i < 4; ++i) {
    legacy.light_foreground[i] = static_cast<uint8_t>(0x10u + static_cast<unsigned>(i));
    legacy.light_background[i] = static_cast<uint8_t>(0x20u + static_cast<unsigned>(i));
    legacy.dark_foreground[i] = static_cast<uint8_t>(0x30u + static_cast<unsigned>(i));
    legacy.dark_background[i] = static_cast<uint8_t>(0x40u + static_cast<unsigned>(i));
  }
  reader_preferences_import_report report{};
  report.struct_size = static_cast<uint32_t>(sizeof(report));
  report.applied = 0xffffffffu;
  report.preserved = 0xffffffffu;
  const reader_preferences before = value;
  reader_preferences_error error{};
  reader_preferences_status status = abi<reader_preferences_status>(
      "reader_preferences_import_legacy", [&] {
        return reader_preferences_import_legacy(&value, &legacy, &report, &error);
      });
  require(preferences_known(static_cast<int>(status)),
          "import status is outside the documented set");
  require(std::memchr(error.message, 0, sizeof(error.message)) != nullptr,
          "import error message is not NUL terminated");
  if (status != READER_PREFERENCES_OK) {
    require(std::memcmp(&before, &value, sizeof(value)) == 0,
            "a failed legacy import modified the record");
  }
  std::string out;
  number(out, "status", static_cast<long long>(status));
  field(out, "name", quote(preferences_name(status)));
  field(out, "message", quote(std::string(error.message, std::strlen(error.message))));
  number(out, "applied", static_cast<long long>(report.applied));
  number(out, "preserved", static_cast<long long>(report.preserved));
  append_record(out, value);
  emit(out);
  return 0;
}

int command_preferences_theme(const std::vector<std::string> &args) {
  require(args.size() >= 4, "preferences-theme needs a stored and a system value");
  const int stored = std::stoi(args[2]);
  const int system = std::stoi(args[3]);
  reader_preferences value = reader_preferences_defaults();
  value.theme = static_cast<uint32_t>(stored);
  const reader_preferences *record = stored == 0 ? nullptr : &value;
  const reader_preferences_theme resolved =
      reader_preferences_effective_theme(record, static_cast<reader_preferences_theme>(system));
  std::string out;
  number(out, "stored", stored);
  number(out, "system", system);
  number(out, "resolved", static_cast<long long>(resolved));
  emit(out);
  return 0;
}

int command_wire_validate(const std::vector<std::string> &args) {
  require(args.size() >= 4, "wire-validate needs a database and a case file");
  std::string bytes;
  require(read_file(args[3], bytes), "the wire case is unreadable");
  const char *expected = args.size() > 4 && args[4] != "-" ? args[4].c_str() : nullptr;
  store_handle handle;
  require(handle.open(args[2]) == READER_REV_OK, "the product catalog did not open");
  const std::string fields = wire_validate_observe(handle.store, bytes, expected);
  handle.close();
  emit(fields);
  return 0;
}

int command_wire_decode(const std::vector<std::string> &args) {
  require(args.size() >= 4, "wire-decode needs a database and a case file");
  std::string bytes;
  require(read_file(args[3], bytes), "the wire case is unreadable");
  store_handle handle;
  require(handle.open(args[2]) == READER_REV_OK, "the product catalog did not open");
  const std::string fields = wire_decode_observe(handle.store, bytes);
  handle.close();
  emit(fields);
  return 0;
}

int command_wire_receive(const std::vector<std::string> &args) {
  require(args.size() >= 5, "wire-receive needs a database, a case file and a SHA or -");
  std::string bytes;
  require(read_file(args[3], bytes), "the wire case is unreadable");
  store_handle handle;
  require(handle.open(args[2]) == READER_REV_OK, "the product catalog did not open");
  const char *sha = args[4] == "-" ? nullptr : args[4].c_str();
  reader_revision_info info{};
  reader_revision_error error{};
  int created = 0;
  reader_revision_status status = abi<reader_revision_status>(
      "reader_revision_receive", [&] {
        return reader_revision_receive(handle.store, bytes.data(), bytes.size(), sha, &info,
                                       &created, &error);
      });
  require(revision_known(static_cast<int>(status)), "receive status is outside the documented set");
  require(created == 0 || created == 1, "receive created flag is not a boolean");
  require(std::memchr(error.message, 0, sizeof(error.message)) != nullptr,
          "receive error message is not NUL terminated");
  if (status != READER_REV_OK) require(created == 0, "a refused receive reported a created row");
  std::string out;
  number(out, "status", static_cast<long long>(status));
  field(out, "name", quote(revision_name(status)));
  field(out, "message", quote(std::string(error.message, std::strlen(error.message))));
  number(out, "created", created);
  append_info(out, info);
  emit(out);
  handle.close();
  return 0;
}

int command_wire_local(const std::vector<std::string> &args) {
  require(args.size() >= 4, "wire-local needs a database and a case file");
  std::string bytes;
  require(read_file(args[3], bytes), "the wire case is unreadable");
  store_handle handle;
  require(handle.open(args[2]) == READER_REV_OK, "the product catalog did not open");
  reader_revision_info info{};
  reader_revision_error error{};
  int created = 0;
  reader_revision_status status = abi<reader_revision_status>(
      "reader_revision_local", [&] {
        return reader_revision_local(handle.store, bytes.data(), bytes.size(), &info, &created,
                                     &error);
      });
  require(revision_known(static_cast<int>(status)), "local status is outside the documented set");
  require(created == 0 || created == 1, "local created flag is not a boolean");
  require(std::memchr(error.message, 0, sizeof(error.message)) != nullptr,
          "local error message is not NUL terminated");
  std::string out;
  number(out, "status", static_cast<long long>(status));
  field(out, "name", quote(revision_name(status)));
  field(out, "message", quote(std::string(error.message, std::strlen(error.message))));
  number(out, "created", created);
  append_info(out, info);
  emit(out);
  handle.close();
  return 0;
}

int command_wire_outbox(const std::vector<std::string> &args) {
  require(args.size() >= 3, "wire-outbox needs a database");
  store_handle handle;
  require(handle.open(args[2]) == READER_REV_OK, "the product catalog did not open");
  const outbox_observer rows = read_outbox(handle.store);
  std::string out;
  number(out, "count", static_cast<long long>(rows.ids.size()));
  std::string ids;
  for (size_t i = 0; i < rows.ids.size(); ++i) {
    std::string row;
    field(row, "id", quote(rows.ids[i]));
    number(row, "attempts", rows.attempts[i]);
    field(row, "last_error", quote(rows.errors[i]));
    if (i) ids += ',';
    ids += "{" + row + "}";
  }
  field(out, "rows", "[" + ids + "]");
  emit(out);
  handle.close();
  return 0;
}

int command_wire_get(const std::vector<std::string> &args) {
  require(args.size() >= 5, "wire-get needs a database, an id and an output path");
  store_handle handle;
  require(handle.open(args[2]) == READER_REV_OK, "the product catalog did not open");
  revision_bytes_guard wire;
  size_t bytes = 0;
  reader_revision_info info{};
  reader_revision_error error{};
  reader_revision_status status = abi<reader_revision_status>(
      "reader_revision_get", [&] {
        return reader_revision_get(handle.store, args[3].c_str(), &wire.value, &bytes, &info,
                                   &error);
      });
  require(revision_known(static_cast<int>(status)), "get status is outside the documented set");
  require(std::memchr(error.message, 0, sizeof(error.message)) != nullptr,
          "get error message is not NUL terminated");
  if (status == READER_REV_OK) {
    require(wire.value != nullptr && bytes > 0, "a successful get returned no bytes");
    require(write_file(args[4], std::string(wire.value, bytes)),
            "cannot write the retained bytes");
  } else {
    require(wire.value == nullptr && bytes == 0, "a failed get returned bytes");
  }
  std::string out;
  number(out, "status", static_cast<long long>(status));
  field(out, "name", quote(revision_name(status)));
  field(out, "message", quote(std::string(error.message, std::strlen(error.message))));
  append_info(out, info);
  emit(out);
  handle.close();
  return 0;
}

int command_wire_retry(const std::vector<std::string> &args) {
  require(args.size() >= 5, "wire-retry needs a database, an id and a reason");
  store_handle handle;
  require(handle.open(args[2]) == READER_REV_OK, "the product catalog did not open");
  reader_revision_error error{};
  const int reason = std::stoi(args[4]);
  reader_revision_status status = abi<reader_revision_status>(
      "reader_revision_retry", [&] {
        return reader_revision_retry(handle.store, args[3].c_str(),
                                     static_cast<reader_revision_status>(reason), &error);
      });
  require(revision_known(static_cast<int>(status)), "retry status is outside the documented set");
  std::string out;
  number(out, "status", static_cast<long long>(status));
  field(out, "name", quote(revision_name(status)));
  field(out, "message", quote(std::string(error.message, std::strlen(error.message))));
  emit(out);
  handle.close();
  return 0;
}

int command_wire_ack(const std::vector<std::string> &args) {
  require(args.size() >= 5, "wire-ack needs a database, an id and a SHA");
  store_handle handle;
  require(handle.open(args[2]) == READER_REV_OK, "the product catalog did not open");
  reader_revision_error error{};
  reader_revision_status status = abi<reader_revision_status>(
      "reader_revision_ack",
      [&] { return reader_revision_ack(handle.store, args[3].c_str(), args[4].c_str(), &error); });
  require(revision_known(static_cast<int>(status)), "ack status is outside the documented set");
  std::string out;
  number(out, "status", static_cast<long long>(status));
  field(out, "name", quote(revision_name(status)));
  field(out, "message", quote(std::string(error.message, std::strlen(error.message))));
  emit(out);
  handle.close();
  return 0;
}

int command_wire_heads(const std::vector<std::string> &args) {
  require(args.size() >= 5, "wire-heads needs a database, a kind and a key");
  store_handle handle;
  require(handle.open(args[2]) == READER_REV_OK, "the product catalog did not open");
  reader_revision_state state{};
  reader_revision_error error{};
  reader_revision_status status = abi<reader_revision_status>(
      "reader_revision_heads", [&] {
        return reader_revision_heads(handle.store, args[3].c_str(), args[4].c_str(), nullptr,
                                     nullptr, &state, &error);
      });
  require(revision_known(static_cast<int>(status)), "heads status is outside the documented set");
  require(std::memchr(error.message, 0, sizeof(error.message)) != nullptr,
          "heads error message is not NUL terminated");
  std::string out;
  number(out, "status", static_cast<long long>(status));
  field(out, "name", quote(revision_name(status)));
  number(out, "revisions", static_cast<long long>(state.revisions));
  number(out, "heads", static_cast<long long>(state.heads));
  number(out, "missing_parents", static_cast<long long>(state.missing_parents));
  number(out, "foreign_parents", static_cast<long long>(state.foreign_parents));
  number(out, "projection_safe", static_cast<long long>(state.projection_safe));
  number(out, "deleted", static_cast<long long>(state.deleted));
  number(out, "requires_restore", static_cast<long long>(state.requires_restore));
  emit(out);
  handle.close();
  return 0;
}

/* ------------------------------------------------------------------ */
/* encode: reading-state capture to wire                               */
/* ------------------------------------------------------------------ */

int command_encode(const std::vector<std::string> &args) {
  require(args.size() >= 5, "encode needs a database, a case name and an output path");
  const std::string kind = args[3];
  store_handle handle;
  require(handle.open(args[2]) == READER_REV_OK, "the product catalog did not open");

  const std::string book_key = "epub:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
  const std::string annotation_id = "fedcba9876543210fedcba9876543210";
  const std::string revision_id = "0123456789abcdef0123456789abcdef";

  char exact[] = "alpha";
  char empty[] = "";
  char chapter[] = "OEBPS/ch1.xhtml";
  char note[] = "note";
  char parser[] = "j23-fuzz/1";

  exr_anchor anchor{};
  anchor.start = 0;
  anchor.end = 5;
  anchor.exact = exact;
  anchor.prefix = empty;
  anchor.suffix = empty;
  anchor.chapter = nullptr;

  exr_fixed_anchor fixed{};
  char page_id[] = "page-1";
  char fixed_exact[] = "abc";
  char nul_exact[] = {'a', 0, 'b', 0};
  fixed.start = 0;
  fixed.end = 3;
  fixed.page_id = page_id;
  fixed.exact = fixed_exact;
  fixed.prefix = nullptr;
  fixed.suffix = nullptr;
  fixed.exact_size = 3;
  fixed.prefix_size = 0;
  fixed.suffix_size = 0;

  reader_rs_capture capture{};
  capture.mode = READER_RS_REFLOW_GLOBAL;
  capture.anchor = &anchor;
  capture.part_path = nullptr;
  capture.fixed = nullptr;
  capture.page = 0;

  reader_rs_envelope envelope{};
  envelope.revision_id = revision_id.c_str();
  envelope.operation = "put";
  envelope.entity_kind = "annotation";
  envelope.book_key = book_key.c_str();
  envelope.annotation_id = annotation_id.c_str();
  envelope.parents = nullptr;
  envelope.parent_count = 0;
  envelope.note_text = note;
  envelope.parser_version = parser;

  rs_wire_guard wire;
  size_t bytes = 0;
  reader_rs_error error{};
  reader_rs_status status = READER_RS_OK;

  if (kind == "v1-annotation") {
    status = abi<reader_rs_status>("reader_rs_encode", [&] {
      return reader_rs_encode(handle.store, &envelope, &capture, &wire.value, &bytes, &error);
    });
  } else if (kind == "v2-point") {
    envelope.entity_kind = "progress";
    envelope.book_key = book_key.c_str();
    envelope.annotation_id = nullptr;
    envelope.note_text = nullptr;
    anchor.exact = empty;
    anchor.start = 0;
    anchor.end = 0;
    status = abi<reader_rs_status>("reader_rs_encode_v2", [&] {
      return reader_rs_encode_v2(handle.store, &envelope, &capture, 0, &wire.value, &bytes, &error);
    });
  } else if (kind == "v1-chapter") {
    envelope.entity_kind = "progress";
    envelope.annotation_id = nullptr;
    envelope.note_text = nullptr;
    anchor.chapter = chapter;
    status = abi<reader_rs_status>("reader_rs_encode", [&] {
      return reader_rs_encode(handle.store, &envelope, &capture, &wire.value, &bytes, &error);
    });
  } else if (kind == "v2-nul") {
    capture.mode = READER_RS_FIXED_PAGE;
    capture.fixed = &fixed;
    fixed.exact = nul_exact;
    fixed.exact_size = 3;
    status = abi<reader_rs_status>("reader_rs_encode_v2", [&] {
      return reader_rs_encode_v2(handle.store, &envelope, &capture, 0, &wire.value, &bytes, &error);
    });
  } else if (kind == "argument") {
    envelope.entity_kind = nullptr;
    status = abi<reader_rs_status>("reader_rs_encode", [&] {
      return reader_rs_encode(handle.store, &envelope, &capture, &wire.value, &bytes, &error);
    });
  } else {
    throw violation{"unknown encode case"};
  }

  require(reading_known(static_cast<int>(status)), "encode status is outside the documented set");
  require(std::memchr(error.message, 0, sizeof(error.message)) != nullptr,
          "encode error message is not NUL terminated");
  if (status == READER_RS_OK) {
    require(wire.value != nullptr && bytes > 0, "a successful encode returned no bytes");
    require(write_file(args[4], std::string(wire.value, bytes)),
            "cannot write the encoded wire");
  } else {
    require(wire.value == nullptr && bytes == 0, "a refused encode returned bytes");
  }
  std::string out;
  number(out, "status", static_cast<long long>(status));
  field(out, "name", quote(reading_name(status)));
  field(out, "message", quote(std::string(error.message, std::strlen(error.message))));
  number(out, "gap", static_cast<long long>(error.gap));
  number(out, "bytes", static_cast<long long>(bytes));
  emit(out);
  handle.close();
  return 0;
}

/* ------------------------------------------------------------------ */
/* bounded fuzz loop and single-case replay                            */
/* ------------------------------------------------------------------ */

struct fuzz_arguments {
  std::string target;
  std::string seeds;
  uint64_t iterations = 0;
  uint64_t seed = 0;
  uint64_t budget_ms = 0;
  std::string journal;
  std::string current;
  std::string workdir;
};

std::vector<std::pair<std::string, std::string>> load_seeds(const std::string &directory) {
  std::vector<std::pair<std::string, std::string>> seeds;
  std::error_code error;
  for (const auto &entry : std::filesystem::directory_iterator(std::filesystem::u8path(directory),
                                                               error)) {
    if (!entry.is_regular_file(error)) continue;
    std::string bytes;
    require(read_file(entry.path().string(), bytes), "a fuzz seed is unreadable");
    seeds.emplace_back(entry.path().filename().string(), bytes);
  }
  require(!seeds.empty(), "the fuzz seed directory is empty");
  std::sort(seeds.begin(), seeds.end());
  return seeds;
}

long long milliseconds_since(const std::chrono::steady_clock::time_point &start) {
  return std::chrono::duration_cast<std::chrono::milliseconds>(
             std::chrono::steady_clock::now() - start)
      .count();
}

std::string hex64(uint64_t value) {
  char buffer[32];
  std::snprintf(buffer, sizeof buffer, "%016llx", static_cast<unsigned long long>(value));
  return std::string(buffer);
}

int command_fuzz(const std::vector<std::string> &args) {
  require(args.size() >= 10, "fuzz needs ten arguments");
  fuzz_arguments options{args[2], args[3], std::stoull(args[4]), std::stoull(args[5]),
                         std::stoull(args[9]), args[6], args[7], args[8]};
  const bool preferences_target = options.target == "preferences";
  require(preferences_target || options.target == "wire-validate" ||
              options.target == "wire-decode" || options.target == "wire-receive" ||
              options.target == "wire-local",
          "unknown fuzz target");

  const auto seeds = load_seeds(options.seeds);
  const size_t cap = preferences_target ? 70000u : 300000u;
  rng random{options.seed ? options.seed : 0x6a32332d66757a7aULL};

  case_context context;
  context.workdir = options.workdir;
  context.preferences_path = options.current + ".prefs";
  store_handle handle;
  if (!preferences_target) {
    context.database = options.workdir + "/fuzz-" + options.target + ".db";
    remove_file(context.database);
    require(handle.open(context.database) == READER_REV_OK, "the fuzz catalog did not open");
    context.store = handle.store;
  }

  std::ofstream journal(options.journal, std::ios::binary | std::ios::app);
  require(static_cast<bool>(journal), "the crash journal is not writable");

  const auto start = std::chrono::steady_clock::now();
  uint64_t completed = 0;
  bool budget_stopped = false;
  for (uint64_t iteration = 0; iteration < options.iterations; ++iteration) {
    if (options.budget_ms != 0 &&
        static_cast<uint64_t>(milliseconds_since(start)) >= options.budget_ms) {
      budget_stopped = true;
      break;
    }
    const auto &base = seeds[static_cast<size_t>(random.next() % seeds.size())];
    std::string input = mutate(base.second, random, cap, preferences_target ? kPreferencesTokens
                                                                            : kWireTokens,
                               preferences_target
                                   ? sizeof(kPreferencesTokens) / sizeof(kPreferencesTokens[0])
                                   : sizeof(kWireTokens) / sizeof(kWireTokens[0]));
    if ((random.next() & 3u) == 0) {
      input = mutate(input, random, cap,
                     preferences_target ? kPreferencesTokens : kWireTokens,
                     preferences_target
                         ? sizeof(kPreferencesTokens) / sizeof(kPreferencesTokens[0])
                         : sizeof(kWireTokens) / sizeof(kWireTokens[0]));
    }
    require(write_file(options.current, input), "cannot stage the current fuzz case");
    journal << "iter=" << iteration << " seed=" << hex64(random.state)
            << " base=" << base.first << " bytes=" << input.size() << '\n';
    journal.flush();
    require(static_cast<bool>(journal), "the crash journal stopped accepting writes");
    /* observe() throws on a boundary violation; the journal already names the
       exact iteration, so the driver can replay the staged file. */
    (void)observe(options.target, context, input);
    ++completed;
  }
  journal.close();

  std::string out;
  field(out, "target", quote(options.target));
  number(out, "iterations", static_cast<long long>(completed));
  number(out, "requested", static_cast<long long>(options.iterations));
  number(out, "seed", static_cast<long long>(options.seed));
  field(out, "stop", quote(budget_stopped ? "budget" : "iterations"));
  number(out, "elapsed_ms", milliseconds_since(start));
  std::error_code size_error;
  const auto current_bytes = std::filesystem::file_size(
      std::filesystem::u8path(options.current), size_error);
  number(out, "current_bytes", size_error ? 0 : static_cast<long long>(current_bytes));
  emit(out);
  if (!preferences_target) handle.close();
  return 0;
}

int command_replay(const std::vector<std::string> &args) {
  require(args.size() >= 4, "replay needs a target, a case file and a work directory");
  const std::string target = args[2];
  std::string bytes;
  require(read_file(args[3], bytes), "the replay case is unreadable");
  case_context context;
  context.workdir = args[4];
  context.preferences_path = args[4] + "/replay-prefs.json";
  store_handle handle;
  if (target != "preferences") {
    context.database = args[4] + "/replay-" + target + ".db";
    remove_file(context.database);
    require(handle.open(context.database) == READER_REV_OK, "the replay catalog did not open");
    context.store = handle.store;
  }
  const std::string fields = observe(target, context, bytes);
  if (target != "preferences") handle.close();
  emit(fields);
  return 0;
}

}  // namespace

int main(int argc, char **argv) {
  std::vector<std::string> args;
  for (int index = 0; index < argc; ++index) args.emplace_back(argv[index]);
  if (args.size() < 2) {
    emit("\"usage\":\"boundary-cpp-consumer <command> ...\"");
    return 2;
  }
  try {
    const std::string &command = args[1];
    if (command == "preferences-defaults") return command_preferences_defaults();
    if (command == "preferences-load") return command_preferences_load(args);
    if (command == "preferences-save") return command_preferences_save(args);
    if (command == "preferences-status-name") return command_preferences_status_name(args);
    if (command == "preferences-import-legacy") return command_preferences_import_legacy(args);
    if (command == "preferences-theme") return command_preferences_theme(args);
    if (command == "wire-validate") return command_wire_validate(args);
    if (command == "wire-decode") return command_wire_decode(args);
    if (command == "wire-receive") return command_wire_receive(args);
    if (command == "wire-local") return command_wire_local(args);
    if (command == "wire-outbox") return command_wire_outbox(args);
    if (command == "wire-get") return command_wire_get(args);
    if (command == "wire-retry") return command_wire_retry(args);
    if (command == "wire-ack") return command_wire_ack(args);
    if (command == "wire-heads") return command_wire_heads(args);
    if (command == "encode") return command_encode(args);
    if (command == "fuzz") return command_fuzz(args);
    if (command == "replay") return command_replay(args);
    emit("\"usage\":\"unknown command\"");
    return 2;
  } catch (const violation &problem) {
    emit("\"violation\":" + quote(problem.text));
    return 3;
  } catch (const escaped_exception &problem) {
    emit("\"violation\":" + quote("C++ exception escaped " + problem.call));
    return 4;
  } catch (const std::exception &problem) {
    emit("\"error\":" + quote(problem.what()));
    return 2;
  }
}
