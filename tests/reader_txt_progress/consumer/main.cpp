/* SPDX-License-Identifier: MIT
 * Installed-consumer probe for EXReaderTxtProgress. Actions-only: it links the
 * installed product modules exactly as a host does and never reaches into an
 * SDK archive or a private header.
 *
 * The test wires are written as explicit JSON because the probe must be able to
 * create history shapes (concurrent siblings, an anchor v1 record, a record with
 * an unknown parent) that the product commands intentionally refuse to produce.
 */
#include <reader_txt_progress.h>
#include <reader_projection.h>
#include <reader_revisions.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

namespace {
struct check {
  std::string name;
  int pass = 0;
  std::string detail;
};
struct report {
  std::vector<check> checks;
  int failures = 0;
  void add(const char *name, bool ok, const std::string &detail) {
    check row;
    row.name = name;
    row.pass = ok ? 1 : 0;
    row.detail = detail;
    if (!ok) ++failures;
    checks.push_back(row);
    std::printf("%s %s %s\n", ok ? "PASS" : "FAIL", name, detail.c_str());
  }
};
std::string quoted(const std::string &text) {
  std::string out = "\"";
  for (char c : text) {
    if (c == '"' || c == '\\') { out += '\\'; out += c; }
    else if ((unsigned char)c < 0x20) { char buffer[8]; std::snprintf(buffer, sizeof(buffer), "\\u%04x", (unsigned)(unsigned char)c); out += buffer; }
    else out += c;
  }
  return out + "\"";
}
bool hex32(const char *text) {
  if (!text || std::strlen(text) != 32) return false;
  for (int i = 0; i < 32; ++i) {
    const char c = text[i];
    if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return false;
  }
  return true;
}
std::string fresh_id(reader_revisions *history) {
  char id[33] = {0};
  reader_revision_error detail{};
  if (reader_revision_new_id(id, &detail) != READER_REV_OK) return std::string();
  (void)history;
  return std::string(id);
}
/* One progress revision envelope; anchor v2 points carry no quote bytes. */
std::string progress_wire(const std::string &id, const std::string &key, unsigned version,
                          long long start, const char *exact, const char *suffix,
                          const std::vector<std::string> &parents, const char *parser) {
  std::string out = "{\"version\":1,\"id\":" + quoted(id) + ",\"entity_kind\":\"progress\",\"entity_key\":" +
    quoted(key) + ",\"operation\":\"put\",\"location_kind\":\"reflow_global\",\"parents\":[";
  for (size_t i = 0; i < parents.size(); ++i) {
    if (i) out += ',';
    out += quoted(parents[i]);
  }
  out += "],\"payload\":{\"book_key\":" + quoted(key) +
    ",\"location\":{\"mode\":\"reflow_global\",\"parser_version\":" + quoted(parser) +
    ",\"anchor_version\":" + std::to_string(version) + ",\"selector\":{\"exact\":" + quoted(exact) +
    ",\"prefix\":\"\",\"suffix\":" + quoted(suffix) + ",\"start\":" + std::to_string(start) +
    ",\"end\":" + std::to_string(start + (long long)std::strlen(exact));
  if (version == 2) out += ",\"chapter\":null";
  out += "}}}}";
  return out;
}
reader_revision_status history_open(const std::string &path, int raw, reader_revisions **out,
                                    reader_revision_error *detail) {
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
  if (raw) return reader_revisions_open_raw_v3(path.c_str(), out, detail);
#else
  (void)raw;
#endif
  return reader_revisions_open(path.c_str(), out, detail);
}
reader_revision_status history_local(reader_revisions *history, int raw, const std::string &wire,
                                     reader_revision_info *info, int *created,
                                     reader_revision_error *detail) {
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
  if (raw) return reader_revision_local_raw_v3(history, wire.data(), wire.size(), info, created, detail);
#else
  (void)raw;
#endif
  return reader_revision_local(history, wire.data(), wire.size(), info, created, detail);
}
reader_revision_status history_receive(reader_revisions *history, int raw, const std::string &wire,
                                       reader_revision_info *info, int *created,
                                       reader_revision_error *detail) {
  reader_revision_info validated{};
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
  if (raw) {
    const auto status = reader_revision_validate_raw_v3(history, wire.data(), wire.size(), NULL, &validated, detail);
    if (status != READER_REV_OK) return status;
    return reader_revision_receive_raw_v3(history, wire.data(), wire.size(), validated.sha256, info, created, detail);
  }
#else
  (void)raw;
#endif
  const auto status = reader_revision_validate(history, wire.data(), wire.size(), NULL, &validated, detail);
  if (status != READER_REV_OK) return status;
  return reader_revision_receive(history, wire.data(), wire.size(), validated.sha256, info, created, detail);
}
reader_revision_status history_get(reader_revisions *history, int raw, const char *id, char **wire,
                                   size_t *bytes, reader_revision_info *info,
                                   reader_revision_error *detail) {
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
  if (raw) return reader_revision_get_raw_v3(history, id, wire, bytes, info, detail);
#else
  (void)raw;
#endif
  return reader_revision_get(history, id, wire, bytes, info, detail);
}
struct head_list {
  std::vector<std::string> ids;
};
int collect_head(void *context, const reader_revision_head *head) {
  static_cast<head_list *>(context)->ids.push_back(head->revision_id);
  return 0;
}
head_list heads_of(reader_revisions *history, int raw, const std::string &key) {
  head_list list;
  reader_revision_state graph{};
  reader_revision_error detail{};
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
  if (raw) {
    reader_revision_heads_raw_v3(history, "progress", key.c_str(), collect_head, &list, &graph, &detail);
    return list;
  }
#else
  (void)raw;
#endif
  reader_revision_heads(history, "progress", key.c_str(), collect_head, &list, &graph, &detail);
  return list;
}
}  // namespace

int main(int argc, char **argv) {
  if (argc < 3) {
    std::fprintf(stderr, "usage: txtp-probe <work-dir> <report.json> [raw]\n");
    return 2;
  }
  const std::string work = argv[1];
  const std::string report_path = argv[2];
  const int raw = argc > 3 && std::strcmp(argv[3], "raw") == 0;
  const std::string db_path = work + "/txtp.sqlite";
  std::remove(db_path.c_str());
  report out;

  reader_txt_progress *store = NULL;
  reader_txp_error error{};
  reader_txp_status status = reader_txp_open(db_path.c_str(), raw, &store, &error);
  out.add("store_open", status == READER_TXP_OK, error.message);
  if (status != READER_TXP_OK) {
    std::printf("store open failed: %s\n", error.message);
    return 1;
  }
  reader_revisions *history = NULL;
  reader_revision_error history_error{};
  const reader_revision_status opened = history_open(db_path, raw, &history, &history_error);
  out.add("history_open", opened == READER_REV_OK, history_error.message);

  const char *sha = "1111111111111111111111111111111111111111111111111111111111111111";
  const std::string key = std::string("txt:") + sha;

  /* 1. bounded capture: 32 scalars / 128 bytes on a scalar boundary */
  {
    const std::string ascii(40, 'a');
    reader_txp_position position{};
    status = reader_txp_capture(&position, 4096, ascii.c_str(), ascii.size(), &error);
    const bool ascii_ok = status == READER_TXP_OK && position.offset == 4096 && position.context_bytes == 32;
    reader_txp_position multi{};
    const std::string scalars = std::string(31, 'b') + "\xc3\xa9" + "0123456789";
    const reader_txp_status second = reader_txp_capture(&multi, 0, scalars.c_str(), scalars.size(), &error);
    const bool multi_ok = second == READER_TXP_OK && multi.context_bytes == 33;
    reader_txp_position wide{};
    const std::string wide_text = std::string(31, 'c') + "\xe4\xb8\xad\xe6\x96\x87";
    const reader_txp_status third = reader_txp_capture(&wide, 0, wide_text.c_str(), wide_text.size(), &error);
    /* 31 one-byte scalars + one three-byte scalar = 34 bytes, still inside 128 */
    out.add("capture_bounds", ascii_ok && multi_ok && third == READER_TXP_OK && wide.context_bytes == 34,
            "ascii=" + std::to_string(position.context_bytes) + " multi=" + std::to_string(multi.context_bytes) +
            " wide=" + std::to_string(wide.context_bytes));
    /* every scalar is kept whole: the two-byte scalar after 31 ASCII would need
       33 bytes; stop before it instead of splitting it. */
    reader_txp_position boundary{};
    const std::string split = std::string(32, 'd') + "\xe4\xb8\xad";
    const reader_txp_status fourth = reader_txp_capture(&boundary, 0, split.c_str(), split.size(), &error);
    out.add("capture_scalar_boundary", fourth == READER_TXP_OK && boundary.context_bytes == 32,
            "bytes=" + std::to_string(boundary.context_bytes));
  }
  /* 2. malformed UTF-8 and NUL are refused, never escaped */
  {
    reader_txp_position position{};
    const reader_txp_status truncated = reader_txp_capture(&position, 0, "\xc3", 1, &error);
    const reader_txp_status nul = reader_txp_capture(&position, 0, "a\0b", 3, &error);
    const reader_txp_status overlong = reader_txp_capture(&position, 0, "\xc0\xaf", 2, &error);
    const reader_txp_status surrogate = reader_txp_capture(&position, 0, "\xed\xa0\x80", 3, &error);
    out.add("capture_utf8_rejected", truncated == READER_TXP_ARGUMENT && nul == READER_TXP_ARGUMENT &&
            overlong == READER_TXP_ARGUMENT && surrogate == READER_TXP_ARGUMENT,
            "truncated=" + std::to_string((int)truncated) + " nul=" + std::to_string((int)nul) +
            " overlong=" + std::to_string((int)overlong) + " surrogate=" + std::to_string((int)surrogate));
  }
  /* 3. retained book identity: created once, never rewritten */
  reader_txp_book book{};
  book.book_key = key.c_str();
  book.title = "Probe TXT";
  book.author = "Actions";
  book.sort_title = "probe txt";
  book.source_bytes = 16792975;
  book.favorite = 0;
  {
    reader_txp_result first{};
    const reader_txp_status created = reader_txp_ensure_book(store, &book, &first, &error);
    reader_txp_result again{};
    const reader_txp_status repeated = reader_txp_ensure_book(store, &book, &again, &error);
    reader_txp_book wrong = book;
    wrong.source_bytes = 12345;
    reader_txp_result mismatch{};
    const reader_txp_status refused = reader_txp_ensure_book(store, &wrong, &mismatch, &error);
    out.add("book_bootstrap_created", created == READER_TXP_OK && first.created == 1 && hex32(first.revision_id),
            "created=" + std::to_string(first.created) + " id=" + first.revision_id);
    out.add("book_bootstrap_idempotent", repeated == READER_TXP_OK && again.created == 0,
            "second_created=" + std::to_string(again.created));
    out.add("book_identity_mismatch", refused == READER_TXP_IDENTITY, "status=" + std::to_string((int)refused));
  }
  /* 4. save, duplicate suppression, load, context matching */
  reader_txp_position saved{};
  {
    const char window[] = "Perf Import 0000 line 0000 of the deterministic probe";
    reader_txp_capture(&saved, 8299, window, 32, &error);
    reader_txp_result write{};
    const reader_txp_status first = reader_txp_save(store, key.c_str(), "3.41.0", &saved, &write, &error);
    out.add("save_created", first == READER_TXP_OK && write.created == 1 && hex32(write.revision_id) && write.bytes > 0,
            "id=" + std::string(write.revision_id) + " bytes=" + std::to_string(write.bytes));
    reader_txp_result duplicate{};
    const reader_txp_status again = reader_txp_save(store, key.c_str(), "3.41.0", &saved, &duplicate, &error);
    out.add("save_unchanged_no_duplicate", again == READER_TXP_OK && duplicate.unchanged == 1 && duplicate.created == 0,
            "unchanged=" + std::to_string(duplicate.unchanged) + " created=" + std::to_string(duplicate.created));
    reader_txp_position loaded{};
    reader_txp_result meta{};
    const reader_txp_status read = reader_txp_load(store, key.c_str(), &loaded, &meta, &error);
    out.add("load_roundtrip", read == READER_TXP_OK && loaded.offset == saved.offset &&
            loaded.context_bytes == saved.context_bytes &&
            std::memcmp(loaded.context, saved.context, saved.context_bytes) == 0,
            "offset=" + std::to_string((unsigned long long)loaded.offset) + " bytes=" + std::to_string(loaded.context_bytes));
    int matches = -1;
    const std::string page = std::string(200, 'x') + window + "tail";
    const reader_txp_status inside = reader_txp_match(&saved, page.c_str(), 8299 - 200, page.size(), &matches, &error);
    const bool inside_ok = inside == READER_TXP_OK && matches == 1;
    const std::string other = std::string(200, 'x') + "Perf Import 0001 line 0001 of the deterministic probe tail";
    const reader_txp_status differs = reader_txp_match(&saved, other.c_str(), 8299 - 200, other.size(), &matches, &error);
    const bool differs_ok = differs == READER_TXP_OK && matches == 0;
    const reader_txp_status outside = reader_txp_match(&saved, page.c_str(), 9000, 50, &matches, &error);
    out.add("match_window", inside_ok && differs_ok && outside == READER_TXP_ARGUMENT,
            "inside=" + std::to_string(inside_ok) + " differs=" + std::to_string(differs_ok) +
            " outside=" + std::to_string((int)outside));
  }
  /* 5. concurrent heads: nothing is selected, written or dropped */
  {
    head_list before = heads_of(history, raw, key);
    const std::string parent = before.ids.empty() ? std::string() : before.ids[0];
    int written = 0;
    for (int i = 0; i < 2; ++i) {
      const std::string wire = progress_wire(fresh_id(history), key, 2, 100 + i * 10, "", "sibling",
                                             parent.empty() ? std::vector<std::string>{} : std::vector<std::string>{parent}, "3.41.0");
      reader_revision_info info{};
      int created = 0;
      reader_revision_error detail{};
      const reader_revision_status inserted = history_local(history, raw, wire, &info, &created, &detail);
      if (inserted == READER_REV_OK && created) ++written;
      else std::printf("sibling insert %d %s\n", (int)inserted, detail.message);
    }
    head_list after = heads_of(history, raw, key);
    reader_txp_result refused{};
    const reader_txp_status save = reader_txp_save(store, key.c_str(), "3.41.0", &saved, &refused, &error);
    reader_txp_position loaded{};
    reader_txp_result meta{};
    const reader_txp_status load = reader_txp_load(store, key.c_str(), &loaded, &meta, &error);
    head_list stable = heads_of(history, raw, key);
    out.add("conflict_refused", written == 2 && after.ids.size() >= 2 && save == READER_TXP_CONFLICT &&
            load == READER_TXP_CONFLICT && stable.ids.size() == after.ids.size(),
            "written=" + std::to_string(written) + " heads=" + std::to_string(after.ids.size()) +
            " save=" + std::to_string((int)save) + " load=" + std::to_string((int)load) +
            " stable=" + std::to_string(stable.ids.size()));
  }
  /* 6. an anchor v1 progress record is kept, reported, and never chosen */
  {
    const char *legacy_sha = "2222222222222222222222222222222222222222222222222222222222222222";
    const std::string legacy_key = std::string("txt:") + legacy_sha;
    reader_txp_book legacy_book{};
    legacy_book.book_key = legacy_key.c_str();
    legacy_book.title = "Legacy TXT";
    legacy_book.author = "Actions";
    legacy_book.sort_title = "legacy txt";
    legacy_book.source_bytes = 4096;
    legacy_book.favorite = 0;
    reader_txp_result bootstrapped{};
    const reader_txp_status boot = reader_txp_ensure_book(store, &legacy_book, &bootstrapped, &error);
    const std::string legacy_id = fresh_id(history);
    const std::string wire = progress_wire(legacy_id, legacy_key, 1, 0, "hello", "", {}, "3.40.0");
    reader_revision_info info{};
    int created = 0;
    reader_revision_error detail{};
    const reader_revision_status inserted = history_local(history, raw, wire, &info, &created, &detail);
    reader_txp_position loaded{};
    reader_txp_result meta{};
    const reader_txp_status load = reader_txp_load(store, legacy_key.c_str(), &loaded, &meta, &error);
    reader_txp_position point{};
    reader_txp_capture(&point, 64, "after the legacy record", 23, &error);
    reader_txp_result appended{};
    const reader_txp_status append = reader_txp_save(store, legacy_key.c_str(), "3.41.0", &point, &appended, &error);
    reader_txp_position reloaded{};
    reader_txp_result meta2{};
    const reader_txp_status reload = reader_txp_load(store, legacy_key.c_str(), &reloaded, &meta2, &error);
    char *retained = NULL;
    size_t retained_bytes = 0;
    reader_revision_info legacy_info{};
    const reader_revision_status fetched = history_get(history, raw, legacy_id.c_str(), &retained,
                                                        &retained_bytes, &legacy_info, &detail);
    const bool unchanged = fetched == READER_REV_OK && retained_bytes == wire.size() &&
      std::memcmp(retained, wire.data(), wire.size()) == 0;
    out.add("legacy_preserved", boot == READER_TXP_OK && inserted == READER_REV_OK && created == 1 &&
            load == READER_TXP_LEGACY && append == READER_TXP_OK && appended.created == 1 &&
            reload == READER_TXP_OK && reloaded.offset == 64 && unchanged,
            "boot=" + std::to_string((int)boot) + " insert=" + std::to_string((int)inserted) +
            " load=" + std::to_string((int)load) + " append=" + std::to_string((int)append) +
            " reload=" + std::to_string((int)reload) + " retained=" + std::to_string(unchanged));
    reader_revision_bytes_free(retained);
  }
  /* 7. a head with an unknown parent stays pending and is never guessed */
  {
    const char *pending_sha = "3333333333333333333333333333333333333333333333333333333333333333";
    const std::string pending_key = std::string("txt:") + pending_sha;
    reader_txp_book pending_book{};
    pending_book.book_key = pending_key.c_str();
    pending_book.title = "Pending TXT";
    pending_book.author = "Actions";
    pending_book.sort_title = "pending txt";
    pending_book.source_bytes = 2048;
    pending_book.favorite = 0;
    reader_txp_result bootstrapped{};
    const reader_txp_status boot = reader_txp_ensure_book(store, &pending_book, &bootstrapped, &error);
    const std::string wire = progress_wire(fresh_id(history), pending_key, 2, 16, "", "pending",
                                           {std::string(32, 'a')}, "3.41.0");
    reader_revision_info info{};
    int created = 0;
    reader_revision_error detail{};
    const reader_revision_status received = history_receive(history, raw, wire, &info, &created, &detail);
    reader_txp_position loaded{};
    reader_txp_result meta{};
    const reader_txp_status load = reader_txp_load(store, pending_key.c_str(), &loaded, &meta, &error);
    reader_txp_position point{};
    reader_txp_capture(&point, 32, "pending write", 13, &error);
    reader_txp_result written{};
    const reader_txp_status save = reader_txp_save(store, pending_key.c_str(), "3.41.0", &point, &written, &error);
    head_list heads = heads_of(history, raw, pending_key);
    out.add("pending_refused", boot == READER_TXP_OK && received == READER_REV_OK && created == 1 &&
            load == READER_TXP_PENDING && save == READER_TXP_PENDING && heads.ids.size() == 1,
            "received=" + std::to_string((int)received) + " load=" + std::to_string((int)load) +
            " save=" + std::to_string((int)save) + " heads=" + std::to_string(heads.ids.size()));
  }
  /* 8. the raw capability cannot be requested from a legacy build */
#ifndef EXR_READER_SELECTOR_BYTES_CANDIDATE
  {
    reader_txt_progress *rejected = NULL;
    const reader_txp_status refused = reader_txp_open(db_path.c_str(), 1, &rejected, &error);
    out.add("raw_capability_refused", refused == READER_TXP_ARGUMENT && rejected == NULL,
            "status=" + std::to_string((int)refused));
  }
#else
  out.add("raw_capability_refused", true, "raw build accepts the explicit capability by design");
#endif

  reader_revisions_close(&history, NULL);
  reader_txp_close(&store);

  FILE *file = std::fopen(report_path.c_str(), "wb");
  if (!file) return 1;
  std::fprintf(file, "{\n  \"ok\": %s,\n  \"db\": %s,\n  \"raw\": %s,\n  \"book_key\": %s,\n  \"checks\": [\n",
               out.failures ? "false" : "true", quoted(db_path).c_str(), raw ? "true" : "false", quoted(key).c_str());
  for (size_t i = 0; i < out.checks.size(); ++i) {
    std::fprintf(file, "    {\"name\": %s, \"pass\": %s, \"detail\": %s}%s\n",
                 quoted(out.checks[i].name).c_str(), out.checks[i].pass ? "true" : "false",
                 quoted(out.checks[i].detail).c_str(), i + 1 == out.checks.size() ? "" : ",");
  }
  std::fprintf(file, "  ]\n}\n");
  std::fclose(file);
  std::printf("checks=%zu failures=%d\n", out.checks.size(), out.failures);
  return out.failures ? 1 : 0;
}
