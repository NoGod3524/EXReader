/* SPDX-License-Identifier: MIT */
/* TXT reading position over the product revision store.
 *
 * A TXT original has no SDK book identity: the product content identity
 * (format:sha256 of the immutable bytes) plus a canonical byte offset in the
 * SDK's whole-document normalized projection is the position. The wire form is
 * the existing reading anchor v2 point selector inside reflow_global, so no SDK
 * identity, page number or new entity is invented.
 *
 * Every write is one product revision whose parents are the complete observed
 * head set. Concurrent, pending or blocked histories, a stale observed head, a
 * legacy (anchor v1) head and an exhausted history all refuse without touching
 * the retained records.
 */
#include <reader_txt_progress.h>
#include <reader_commands.h>
#include <reader_projection.h>
#include <reader_reading_commands.h>
#include <reader_reading_state.h>
#include <reader_revisions.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <new>

struct reader_txt_progress {
  reader_revisions *store;
  int raw;
};

namespace {
constexpr size_t kContextBytes = READER_TXP_CONTEXT_BYTES;
constexpr size_t kContextScalars = READER_TXP_CONTEXT_SCALARS;

void clear_error(reader_txp_error *error) {
  if (!error) return;
  std::memset(error, 0, sizeof(*error));
  error->selection_kind = static_cast<int>(READER_SELECTION_MISSING);
}
reader_txp_status refuse(reader_txp_error *error, reader_txp_status code, const char *message) {
  if (error) {
    error->code = code;
    std::snprintf(error->message, sizeof(error->message), "%s", message ? message : "");
  }
  return code;
}
bool lower_hex(const char *text, size_t count) {
  for (size_t i = 0; i < count; ++i) {
    const char c = text[i];
    if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return false;
  }
  return text[count] == 0;
}
/* This module persists positions only for product TXT originals. */
bool txt_key(const char *key) {
  if (!key) return false;
  if (std::strncmp(key, "txt:", 4) != 0) return false;
  return lower_hex(key + 4, 64);
}
size_t scalar_length(const unsigned char *bytes, size_t remaining, bool *ok) {
  const unsigned c = bytes[0];
  if (c < 0x80) {
    if (!c) { *ok = false; return 0; }
    return 1;
  }
  size_t length;
  unsigned value;
  if ((c & 0xe0) == 0xc0) { length = 2; value = c & 0x1fu; }
  else if ((c & 0xf0) == 0xe0) { length = 3; value = c & 0x0fu; }
  else if ((c & 0xf8) == 0xf0) { length = 4; value = c & 0x07u; }
  else { *ok = false; return 0; }
  if (length > remaining) { *ok = false; return 0; }
  for (size_t i = 1; i < length; ++i) {
    if ((bytes[i] & 0xc0) != 0x80) { *ok = false; return 0; }
    value = (value << 6) | (bytes[i] & 0x3fu);
  }
  if ((length == 2 && value < 0x80) || (length == 3 && value < 0x800) ||
      (length == 4 && value < 0x10000) || value > 0x10ffff ||
      (value >= 0xd800 && value <= 0xdfff)) { *ok = false; return 0; }
  return length;
}
reader_txp_status revision_refusal(reader_txp_error *error, reader_revision_status status,
                                   const reader_revision_error &detail) {
  if (error) {
    error->revision_code = static_cast<int>(status);
    std::snprintf(error->message, sizeof(error->message), "%s",
                  detail.message[0] ? detail.message : "Reading revision was refused");
  }
  return status == READER_REV_LIMIT ? READER_TXP_LIMIT : READER_TXP_REVISION;
}
reader_revision_status open_store(reader_txt_progress *store, const char *path,
                                  reader_revision_error *detail) {
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
  if (store->raw) return reader_revisions_open_raw_v3(path, &store->store, detail);
#else
  (void)store;
#endif
  return reader_revisions_open(path, &store->store, detail);
}
reader_revision_status selected(reader_txt_progress *store, const char *key, char **wire,
                                size_t *bytes, reader_revision_info *info,
                                reader_revision_selection *selection, reader_revision_error *detail) {
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
  if (store->raw)
    return reader_revision_selected_raw_v3(store->store, "progress", key, wire, bytes, info, selection, detail);
#endif
  return reader_revision_selected(store->store, "progress", key, wire, bytes, info, selection, detail);
}
reader_revision_status book_length(reader_txt_progress *store, const char *key, uint64_t *bytes,
                                   reader_revision_error *detail) {
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
  if (store->raw) return reader_revision_book_identity_raw_v3(store->store, key, bytes, detail);
#endif
  return reader_revision_book_identity(store->store, key, bytes, detail);
}
reader_rs_status decode(reader_txt_progress *store, const void *wire, size_t bytes,
                        reader_rs_record *record, reader_rs_error *detail) {
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
  if (store->raw) return reader_rs_decode_raw_v3(store->store, wire, bytes, record, detail);
#endif
  return reader_rs_decode(store->store, wire, bytes, record, detail);
}
reader_command_status apply_book(reader_txt_progress *store, const reader_command_context *context,
                                 const reader_book_command *input, reader_command_result *result,
                                 reader_command_error *detail) {
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
  if (store->raw) return reader_command_apply_book_raw_v3(context, input, result, detail);
#endif
  return reader_command_apply_book(context, input, result, detail);
}
reader_rc_status apply_progress(reader_txt_progress *store, const reader_rc_context *context,
                                const reader_rc_command *input, reader_rc_result *result,
                                reader_rc_error *detail) {
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
  if (store->raw) return reader_rc_apply_raw_v3(context, input, 2u, result, detail);
#endif
  return reader_rc_apply(context, input, result, detail);
}
reader_txp_status selection_refusal(reader_txp_error *error, const reader_revision_selection &selection) {
  if (error) error->selection_kind = static_cast<int>(selection.kind);
  switch (selection.kind) {
    case READER_SELECTION_CONCURRENT:
      return refuse(error, READER_TXP_CONFLICT, "This book has several concurrent progress heads; every record is kept and nothing is selected or written");
    case READER_SELECTION_PENDING_PARENTS:
      return refuse(error, READER_TXP_PENDING, "A progress head is missing its parents; history stays pending and nothing is written");
    case READER_SELECTION_BLOCKED_RESTORE:
      return refuse(error, READER_TXP_BLOCKED, "Progress history needs an explicit restore; nothing is selected or written");
    default:
      return refuse(error, READER_TXP_UNSAFE, "Progress history is not a single complete safe head; nothing is written");
  }
}
bool same_position(const reader_rs_record &record, const reader_txp_position &position) {
  if (record.start != position.offset || record.end != position.offset) return false;
  const size_t saved = record.suffix ? record.suffix_size : 0;
  if (saved != position.context_bytes) return false;
  if (!saved) return true;
  return std::memcmp(record.suffix, position.context, saved) == 0;
}
}  // namespace

extern "C" reader_txp_status reader_txp_open(const char *utf8_path, int raw_capability,
                                             reader_txt_progress **out, reader_txp_error *error) {
  clear_error(error);
  if (out) *out = NULL;
  if (!utf8_path || !utf8_path[0] || !out) return refuse(error, READER_TXP_ARGUMENT, "Missing product database path");
#ifndef EXR_READER_SELECTOR_BYTES_CANDIDATE
  if (raw_capability) return refuse(error, READER_TXP_ARGUMENT, "Raw store capability is not part of this build");
#endif
  reader_txt_progress *store = new (std::nothrow) reader_txt_progress();
  if (!store) return refuse(error, READER_TXP_MEMORY, "Cannot allocate the TXT position store");
  store->store = NULL;
  store->raw = raw_capability ? 1 : 0;
  reader_revision_error detail{};
  const reader_revision_status opened = open_store(store, utf8_path, &detail);
  if (opened != READER_REV_OK) {
    if (store->store) reader_revisions_close(&store->store, NULL);
    delete store;
    if (error) {
      error->code = READER_TXP_STORE;
      error->revision_code = static_cast<int>(opened);
      std::snprintf(error->message, sizeof(error->message), "%s",
                    detail.message[0] ? detail.message : "Cannot open the product revision store");
    }
    return READER_TXP_STORE;
  }
  *out = store;
  return READER_TXP_OK;
}

extern "C" void reader_txp_close(reader_txt_progress **store) {
  if (!store || !*store) return;
  if ((*store)->store) reader_revisions_close(&(*store)->store, NULL);
  delete *store;
  *store = NULL;
}

extern "C" reader_txp_status reader_txp_capture(reader_txp_position *position, uint64_t offset,
                                                const char *bytes, size_t size,
                                                reader_txp_error *error) {
  clear_error(error);
  if (!position) return refuse(error, READER_TXP_ARGUMENT, "Missing captured position");
  std::memset(position, 0, sizeof(*position));
  position->offset = offset;
  if (!size) return READER_TXP_OK;
  if (!bytes) return refuse(error, READER_TXP_ARGUMENT, "Captured context bytes are missing");
  size_t used = 0, scalars = 0;
  while (used < size && scalars < kContextScalars) {
    bool ok = true;
    const size_t length = scalar_length(reinterpret_cast<const unsigned char *>(bytes) + used,
                                        size - used, &ok);
    if (!ok) return refuse(error, READER_TXP_ARGUMENT, "Captured context is not strict UTF-8 without NUL");
    if (used + length > kContextBytes) break;
    used += length;
    ++scalars;
  }
  std::memcpy(position->context, bytes, used);
  position->context[used] = 0;
  position->context_bytes = used;
  return READER_TXP_OK;
}

extern "C" reader_txp_status reader_txp_ensure_book(reader_txt_progress *store,
                                                    const reader_txp_book *book,
                                                    reader_txp_result *result,
                                                    reader_txp_error *error) {
  clear_error(error);
  if (result) std::memset(result, 0, sizeof(*result));
  if (!store || !store->store || !book || !result) return refuse(error, READER_TXP_ARGUMENT, "Missing book identity arguments");
  if (!txt_key(book->book_key)) return refuse(error, READER_TXP_ARGUMENT, "A TXT book key must be txt:<sha256>");
  if (!book->source_bytes) return refuse(error, READER_TXP_ARGUMENT, "The verified original length is required");
  if (!book->title || !book->author || !book->sort_title) return refuse(error, READER_TXP_ARGUMENT, "Retained book metadata is required");
  std::snprintf(result->book_key, sizeof(result->book_key), "%s", book->book_key);
  reader_revision_error detail{};
  uint64_t retained = 0;
  reader_revision_status status = book_length(store, book->book_key, &retained, &detail);
  if (status == READER_REV_OK) {
    if (retained != book->source_bytes) {
      return refuse(error, READER_TXP_IDENTITY, "The retained original length differs from the supplied identity");
    }
    result->created = 0;
    return READER_TXP_OK;
  }
  if (status != READER_REV_NOT_FOUND) return revision_refusal(error, status, detail);
  reader_command_context context{};
  context.store = store->store;
  reader_book_command command{};
  command.operation = READER_COMMAND_PUT;
  command.book_key = book->book_key;
  command.format = "txt";
  command.source_sha256 = book->book_key + 4;
  command.title = book->title;
  command.author = book->author;
  command.sort_title = book->sort_title;
  command.source_bytes = book->source_bytes;
  command.favorite = book->favorite ? 1 : 0;
  reader_command_result applied{};
  reader_command_error failure{};
  const reader_command_status code = apply_book(store, &context, &command, &applied, &failure);
  if (code != READER_COMMAND_OK) {
    if (error) {
      error->command_code = static_cast<int>(code);
      std::snprintf(error->message, sizeof(error->message), "%s",
                    failure.message[0] ? failure.message : "The retained book identity was refused");
    }
    return code == READER_COMMAND_ARGUMENT ? READER_TXP_ARGUMENT : READER_TXP_REVISION;
  }
  result->created = applied.created ? 1 : 0;
  std::snprintf(result->revision_id, sizeof(result->revision_id), "%s", applied.revision_id);
  std::snprintf(result->sha256, sizeof(result->sha256), "%s", applied.revision.sha256);
  result->bytes = applied.revision.bytes;
  return READER_TXP_OK;
}

extern "C" reader_txp_status reader_txp_save(reader_txt_progress *store, const char *book_key,
                                            const char *parser_version,
                                            const reader_txp_position *position,
                                            reader_txp_result *result,
                                            reader_txp_error *error) {
  clear_error(error);
  if (result) std::memset(result, 0, sizeof(*result));
  if (!store || !store->store || !position || !result) return refuse(error, READER_TXP_ARGUMENT, "Missing progress arguments");
  if (!txt_key(book_key)) return refuse(error, READER_TXP_ARGUMENT, "A TXT book key must be txt:<sha256>");
  if (!parser_version || !parser_version[0]) return refuse(error, READER_TXP_ARGUMENT, "A parser version is required");
  if (position->offset > static_cast<uint64_t>(SIZE_MAX)) return refuse(error, READER_TXP_ARGUMENT, "The captured offset exceeds this process");
  if (position->context_bytes > kContextBytes) return refuse(error, READER_TXP_ARGUMENT, "The captured context exceeds its bound");
  std::snprintf(result->book_key, sizeof(result->book_key), "%s", book_key);
  reader_revision_error detail{};
  uint64_t retained = 0;
  const reader_revision_status identity = book_length(store, book_key, &retained, &detail);
  if (identity == READER_REV_NOT_FOUND) return refuse(error, READER_TXP_BOOTSTRAP, "Verified book history is absent; the position cannot be written yet");
  if (identity != READER_REV_OK) return revision_refusal(error, identity, detail);

  char *wire = NULL;
  size_t bytes = 0;
  reader_revision_info head{};
  reader_revision_selection selection{};
  const reader_revision_status current = selected(store, book_key, &wire, &bytes, &head, &selection, &detail);
  if (current == READER_REV_UNSAFE) {
    const reader_txp_status refused = selection_refusal(error, selection);
    reader_revision_bytes_free(wire);
    return refused;
  }
  if (current != READER_REV_OK && current != READER_REV_NOT_FOUND) {
    reader_revision_bytes_free(wire);
    return revision_refusal(error, current, detail);
  }
  const char *const observed[1] = {head.revision_id};
  const size_t observed_count = current == READER_REV_OK ? 1u : 0u;
  if (current == READER_REV_OK) {
    /* An unchanged position is not written again: no new history, no new queue
       row, and the retained bytes stay exactly as they are. */
    reader_rs_record record{};
    reader_rs_error decode_error{};
    const reader_rs_status decoded = decode(store, wire, bytes, &record, &decode_error);
    const bool same = decoded == READER_RS_OK && same_position(record, *position);
    if (decoded == READER_RS_OK) reader_rs_record_free(&record);
    if (same) {
      std::snprintf(result->revision_id, sizeof(result->revision_id), "%s", head.revision_id);
      std::snprintf(result->sha256, sizeof(result->sha256), "%s", head.sha256);
      result->bytes = head.bytes;
      result->unchanged = 1;
      reader_revision_bytes_free(wire);
      return READER_TXP_OK;
    }
  }
  reader_revision_bytes_free(wire);

  exr_anchor anchor{};
  anchor.start = static_cast<size_t>(position->offset);
  anchor.end = anchor.start;
  anchor.exact = const_cast<char *>("");
  anchor.prefix = const_cast<char *>("");
  anchor.suffix = const_cast<char *>(position->context);
  anchor.chapter = NULL;
  reader_rs_capture capture{};
  capture.mode = READER_RS_REFLOW_GLOBAL;
  capture.anchor = &anchor;

  char revision[33] = {0};
  reader_revision_error id_detail{};
  const reader_revision_status generated = reader_revision_new_id(revision, &id_detail);
  if (generated != READER_REV_OK) return revision_refusal(error, generated, id_detail);

  reader_rc_context context{};
  context.store = store->store;
  context.revision_id = revision;
  context.expected_heads = observed_count ? observed : NULL;
  context.expected_count = observed_count;
  context.parser_version = parser_version;
  reader_rc_command command{};
  command.kind = READER_RC_PROGRESS;
  command.operation = READER_RC_PUT;
  command.book_key = book_key;
  command.capture = &capture;
  reader_rc_result applied{};
  reader_rc_error failure{};
  const reader_rc_status code = apply_progress(store, &context, &command, &applied, &failure);
  if (code == READER_RC_OK) {
    std::snprintf(result->revision_id, sizeof(result->revision_id), "%s", applied.revision_id);
    std::snprintf(result->sha256, sizeof(result->sha256), "%s", applied.sha256);
    result->bytes = applied.bytes;
    result->created = applied.created ? 1 : 0;
    return READER_TXP_OK;
  }
  if (error) {
    error->command_code = static_cast<int>(code);
    error->revision_code = static_cast<int>(failure.revision.code);
    std::snprintf(error->message, sizeof(error->message), "%s",
                  failure.message[0] ? failure.message : "The reading revision was refused");
  }
  switch (code) {
    case READER_RC_UNSAFE: return READER_TXP_UNSAFE;
    case READER_RC_ENCODE: return READER_TXP_REVISION;
    case READER_RC_ARGUMENT: return READER_TXP_ARGUMENT;
    case READER_RC_MEMORY: return READER_TXP_MEMORY;
    case READER_RC_SOURCE: return READER_TXP_UNSAFE;
    case READER_RC_REVISION:
    default:
      if (failure.revision.code == READER_REV_LIMIT) return refuse(error, READER_TXP_LIMIT, "The revision history for this book reached its limit; the retained position is unchanged");
      return READER_TXP_REVISION;
  }
}

extern "C" reader_txp_status reader_txp_load(reader_txt_progress *store, const char *book_key,
                                             reader_txp_position *position,
                                             reader_txp_result *result,
                                             reader_txp_error *error) {
  clear_error(error);
  if (position) std::memset(position, 0, sizeof(*position));
  if (result) std::memset(result, 0, sizeof(*result));
  if (!store || !store->store || !position || !result) return refuse(error, READER_TXP_ARGUMENT, "Missing progress arguments");
  if (!txt_key(book_key)) return refuse(error, READER_TXP_ARGUMENT, "A TXT book key must be txt:<sha256>");
  char *wire = NULL;
  size_t bytes = 0;
  reader_revision_info head{};
  reader_revision_selection selection{};
  reader_revision_error detail{};
  const reader_revision_status status = selected(store, book_key, &wire, &bytes, &head, &selection, &detail);
  if (status == READER_REV_NOT_FOUND) {
    reader_revision_bytes_free(wire);
    return refuse(error, READER_TXP_MISSING, "No reading position is retained for this book");
  }
  if (status == READER_REV_UNSAFE) {
    reader_revision_bytes_free(wire);
    return selection_refusal(error, selection);
  }
  if (status != READER_REV_OK) {
    reader_revision_bytes_free(wire);
    return revision_refusal(error, status, detail);
  }
  reader_rs_record record{};
  reader_rs_error decode_error{};
  const reader_rs_status decoded = decode(store, wire, bytes, &record, &decode_error);
  reader_revision_bytes_free(wire);
  if (decoded != READER_RS_OK) {
    if (error) {
      error->message[0] = 0;
      std::snprintf(error->message, sizeof(error->message), "%s",
                    decode_error.message[0] ? decode_error.message : "The retained record cannot be decoded");
    }
    return READER_TXP_REVISION;
  }
  std::snprintf(result->revision_id, sizeof(result->revision_id), "%s", head.revision_id);
  std::snprintf(result->sha256, sizeof(result->sha256), "%s", head.sha256);
  std::snprintf(result->book_key, sizeof(result->book_key), "%s", book_key);
  result->bytes = head.bytes;
  reader_txp_status outcome = READER_TXP_OK;
  const bool point = record.has_location && record.mode == READER_RS_REFLOW_GLOBAL &&
    record.anchor_version == 2 && record.start == record.end && record.exact_size == 0;
  if (!point || (record.book_key[0] && std::strcmp(record.book_key, book_key) != 0)) {
    outcome = READER_TXP_LEGACY;
    if (error) {
      std::snprintf(error->message, sizeof(error->message), "%s",
                    point ? "The retained record belongs to another book identity"
                          : "The retained record is not an anchor v2 point selector; it is kept untouched");
    }
  } else {
    const size_t copied = record.suffix ? (record.suffix_size > kContextBytes ? kContextBytes : record.suffix_size) : 0;
    position->offset = record.start;
    if (copied) std::memcpy(position->context, record.suffix, copied);
    position->context[copied] = 0;
    position->context_bytes = copied;
  }
  reader_rs_record_free(&record);
  if (outcome != READER_TXP_OK && error && !error->code) error->code = outcome;
  return outcome;
}

extern "C" reader_txp_status reader_txp_match(const reader_txp_position *position,
                                              const char *window, uint64_t window_offset,
                                              size_t window_bytes, int *matches,
                                              reader_txp_error *error) {
  clear_error(error);
  if (matches) *matches = 0;
  if (!position || !matches) return refuse(error, READER_TXP_ARGUMENT, "Missing position or match output");
  if (!position->context_bytes) {
    *matches = 1;
    return READER_TXP_OK;
  }
  if (!window) return refuse(error, READER_TXP_ARGUMENT, "Missing projected window");
  if (position->offset < window_offset) return refuse(error, READER_TXP_ARGUMENT, "The projected window starts after the saved point");
  const uint64_t relative = position->offset - window_offset;
  if (relative > static_cast<uint64_t>(window_bytes) ||
      position->context_bytes > window_bytes - static_cast<size_t>(relative)) {
    return refuse(error, READER_TXP_ARGUMENT, "The projected window does not cover the saved point");
  }
  *matches = std::memcmp(window + static_cast<size_t>(relative), position->context,
                         position->context_bytes) == 0 ? 1 : 0;
  return READER_TXP_OK;
}
