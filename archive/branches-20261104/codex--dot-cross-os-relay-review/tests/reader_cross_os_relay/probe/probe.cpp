/* SPDX-License-Identifier: MIT */
/* Installed C++ consumer for the cross-OS artifact relay.

   One executable, three roles, each a separate process on a separate OS:
     send     : import the four originals, export them, create metadata,
                organization and eighteen real reading captures in a fresh
                product store and publish them over native HTTPS WebDAV.
     receive  : start from an EMPTY store, pull only what the relayed service
                directory holds (originals + immutable wires), resolve every
                capture with its own SDK, then write return revisions back.
     confirm  : another empty store on the sender's OS reads the returned tree.
   Databases and SDK libraries never cross the relay. All expectations (digests,
   titles, quotes, states) come from the pinned plan file, not from sender output. */
#define main legacy_probe_main
#include "../../reader_reading_state/consumer/probe.cpp"
#undef main
#include <reader_sync.h>
#include <exr_sideload.h>
#include <filesystem>
#include <functional>
#include <set>

namespace {
std::string mode_name, webdav_root, work, plan_path, transport_path, return_path;
bool return_edit = false;
std::map<std::string, std::string> plan_str;                  /* str rows */
std::map<std::string, std::pair<std::string, std::string>> plan_case; /* id -> state, quote hex */
std::vector<std::string> plan_case_order;
size_t network_pushed = 0, network_pulled = 0, originals_exported = 0, metadata_projected = 0, cancelled_attempts = 0, reopen_count = 0;

std::string unhex(const std::string &h) {
  std::string o;
  if (h == "-") return o;
  for (size_t i = 0; i + 1 < h.size(); i += 2) o += (char)std::stoi(h.substr(i, 2), nullptr, 16);
  return o;
}
std::vector<std::string> split_tab(const std::string &line) {
  std::vector<std::string> out;
  size_t start = 0;
  for (;;) {
    size_t at = line.find('\t', start);
    out.push_back(line.substr(start, at == std::string::npos ? std::string::npos : at - start));
    if (at == std::string::npos) return out;
    start = at + 1;
  }
}
std::vector<std::vector<std::string>> read_rows(const std::string &path) {
  std::vector<std::vector<std::string>> rows;
  std::istringstream in(read_file(path));
  std::string line;
  while (std::getline(in, line)) {
    if (!line.empty() && line.back() == '\r') line.pop_back();
    if (!line.empty()) rows.push_back(split_tab(line));
  }
  return rows;
}
const std::string &S(const std::string &key) {
  auto it = plan_str.find(key);
  if (it == plan_str.end()) fatal("plan lacks " + key);
  return it->second;
}
std::string cache_dir() { return work + "/B-cache"; }
std::string cached_original(const std::string &role) { return cache_dir() + "/" + shas[role] + "." + formats[role]; }
unsigned shard_of(const std::string &id) { return (unsigned)std::stoul(id.substr(0, 2), nullptr, 16); }
const char *kRoles[] = {"txt", "epub", "pdf", "cbz"};

/* ---------- revisions ---------- */
std::string parents_json(const std::vector<std::string> &p) {
  std::string o = "[";
  for (size_t i = 0; i < p.size(); i++) o += (i ? "," : "") + esc(p[i]);
  return o + "]";
}
std::string make_wire(const std::string &id, const char *kind, const std::string &key, const char *op, const std::vector<std::string> &parents, const std::string &payload) {
  return "{\"version\":1,\"id\":" + esc(id) + ",\"entity_kind\":" + esc(kind) + ",\"entity_key\":" + esc(key) + ",\"operation\":" + esc(op) +
         ",\"location_kind\":\"none\",\"parents\":" + parents_json(parents) + ",\"payload\":" + payload + "}";
}
std::string book_payload(const std::string &role, const std::string &title, const std::string &author, bool favorite) {
  return "{\"format\":" + esc(formats[role]) + ",\"source_sha256\":" + esc(shas[role]) + ",\"source_bytes\":" + num(sizes[role]) + ",\"title\":" + esc(title) +
         ",\"author\":" + esc(author) + ",\"favorite\":" + boolean(favorite) + "}";
}
struct revrow { std::string label, kind, key, id, sha; size_t bytes = 0; };
std::vector<revrow> sent_revs;
revrow commit_local(side &s, const std::string &label, const char *kind, const std::string &key, const char *op, const std::vector<std::string> &parents,
                    const std::string &payload, const std::string &fixed_id = "") {
  std::string id = fixed_id.empty() ? new_id() : fixed_id, wire = make_wire(id, kind, key, op, parents, payload);
  reader_revision_info info{};
  reader_revision_error e{};
  int created = 0;
  if (reader_revision_local(s.store, wire.data(), wire.size(), &info, &created, &e) != READER_REV_OK || !created) fatal("local " + label + ": " + e.message);
  revrow r{label, kind, key, id, info.sha256, wire.size()};
  sent_revs.push_back(r);
  return r;
}
revrow commit_book(side &s, const std::string &label, const std::string &role, const std::string &title, const std::string &author, bool favorite,
                   const std::vector<std::string> &parents, const std::string &sort_title) {
  std::string id = new_id(), wire = make_wire(id, "book", keys[role], "put", parents, book_payload(role, title, author, favorite));
  std::vector<const char *> expected;
  for (auto &p : parents) expected.push_back(p.c_str());
  reader_revision_info info{};
  reader_revision_error e{};
  int created = 0, applied = 0;
  if (reader_revision_local_project(s.store, wire.data(), wire.size(), expected.empty() ? nullptr : expected.data(), expected.size(), sort_title.c_str(), &info, &created,
                                    &applied, &e) != READER_REV_OK || !created || !applied)
    fatal("atomic book metadata and outbox " + label + ": " + e.message);
  revrow r{label, "book", keys[role], id, info.sha256, wire.size()};
  sent_revs.push_back(r);
  return r;
}

/* ---------- native transport ---------- */
std::string original_root;
int original_path(void *, const char *key, char *out, size_t capacity) {
  std::string value = key;
  size_t colon = value.find(':');
  std::string path = original_root + "/" + value.substr(colon + 1) + "." + value.substr(0, colon);
  if (path.size() >= capacity) return 1;
  std::memcpy(out, path.c_str(), path.size() + 1);
  return 0;
}
int always_cancel(void *) { return 1; }
struct net_side {
  exr_webdav_client *dav = nullptr;
  reader_sync *sync = nullptr;
  net_side(side &device, const std::string &folder, bool has_originals) {
    std::filesystem::create_directories(std::filesystem::u8path(folder));
    exr_webdav_config config{};
    config.root_url = webdav_root.c_str();
    config.authorization = std::getenv("READER_TEST_AUTH");
    config.timeout_ms = 20000;
    exr_webdav_error de{};
    if (!config.authorization || exr_webdav_create(&config, &dav, &de) != EXR_DAV_OK) fatal("native transport create");
    reader_sync_config options{};
    options.dav = dav;
    options.revisions = device.store;
    options.private_directory = folder.c_str();
    if (has_originals) options.original = original_path;
    reader_sync_error se{};
    if (reader_sync_create(&options, &sync, &se) != READER_SYNC_OK) fatal("native sync create");
  }
  ~net_side() { reader_sync_free(sync); exr_webdav_free(dav); }
  /* Pre-cancelled step: must fail before changing anything. */
  reader_sync_status cancelled_step(unsigned shard) {
    exr_webdav_control control{always_cancel, nullptr, nullptr};
    reader_sync_report report{};
    reader_sync_error error{};
    reader_sync_status st = reader_sync_step(sync, shard, "", 100, &control, &report, &error);
    if (st != READER_SYNC_OK) ++cancelled_attempts;
    return st;
  }
  reader_sync_report step_shard(unsigned shard, bool require_complete_originals = false) {
    std::string cursor;
    reader_sync_report report{}, last{};
    do {
      reader_sync_error error{};
      if (reader_sync_step(sync, shard, cursor.c_str(), 100, nullptr, &report, &error) != READER_SYNC_OK)
        fatal("real native HTTPS step " + std::to_string(error.code) + "/" + std::to_string(error.http_status) + " " + error.message);
      if (require_complete_originals) expect(!report.pending_metadata && !report.pending_local_original, "native transfer has verified book originals");
      network_pushed += report.pushed;
      network_pulled += report.pulled;
      cursor = report.after;
      last = report;
    } while (!report.shard_complete);
    return last;
  }
};

void push_all(side &device, bool has_originals, const std::string &folder) {
  auto outgoing = pending(device);
  if (outgoing.empty()) fatal("native transport has no queued revisions");
  net_side n(device, folder, has_originals);
  n.step_shard(shard_of(outgoing.front().id));
  expect(pending(device).empty(), std::string(device.name) + " conditional publication and GET verification ack the whole outbox");
}

/* ---------- plan ---------- */
void load_plan() {
  for (auto &row : read_rows(plan_path)) {
    if (row[0] == "str" && row.size() == 3) plan_str[row[1]] = row[2];
    else if (row[0] == "case" && row.size() == 4) { plan_case[row[1]] = {row[2], row[3]}; plan_case_order.push_back(row[1]); }
    else fatal("bad plan row");
  }
}
std::string sort_for(const std::string &title) {
  for (const char *role : kRoles) {
    if (S(std::string("title_") + role) == title) return S(std::string("sort_") + role);
  }
  if (title == S("return_title_epub")) return S("return_sort_epub");
  fatal("no pinned sort title for a received title");
}

/* ---------- case table (same eighteen captures as the in-process probe) ---------- */
struct sent_case { std::string id, mode, kind, key, rev, sha; size_t bytes, part, start, end; std::string state; };
std::vector<sent_case> sent_cases;
std::string last_key_for_report;

using resolver = std::function<reader_rs_status(const reader_rs_record *, exr_anchor_match *)>;
void capture_case(const char *name, const char *role, const char *kind, const reader_rs_capture &capture, size_t part, const resolver &own) {
  std::string id = new_id(), aid = new_id(), key = keys[role] + (!std::strcmp(kind, "annotation") ? ":" + aid : "");
  auto observed = heads(A, kind, key);
  std::vector<const char *> parent;
  for (const auto &h : observed) parent.push_back(h.c_str());
  reader_rs_envelope envelope{};
  envelope.revision_id = id.c_str();
  envelope.operation = "put";
  envelope.entity_kind = kind;
  envelope.book_key = keys[role].c_str();
  envelope.annotation_id = aid.c_str();
  envelope.parents = parent.data();
  envelope.parent_count = parent.size();
  envelope.note_text = name;
  envelope.parser_version = parser_version.c_str();
  char *wire = nullptr;
  size_t bytes = 0;
  reader_rs_error error{};
  if (reader_rs_encode_v2(A.store, &envelope, &capture, part, &wire, &bytes, &error) != READER_RS_OK) fatal(std::string(name) + " encode: " + error.message);
  std::string exact(wire, bytes);
  reader_rs_free(wire);
  reader_revision_info info{};
  reader_revision_error re{};
  int created = 0;
  if (reader_revision_local_reading(A.store, exact.data(), exact.size(), parent.empty() ? nullptr : parent.data(), parent.size(), &info, &created, &re) != READER_REV_OK || !created)
    fatal(std::string(name) + " commit: " + re.message);
  reader_rs_record record{};
  if (reader_rs_decode(A.store, exact.data(), exact.size(), &record, &error) != READER_RS_OK) fatal(std::string(name) + " sender decode");
  exr_anchor_match match{};
  own(&record, &match);
  size_t start = capture.mode == READER_RS_FIXED_PAGE ? capture.fixed->start : capture.anchor->start;
  size_t end = capture.mode == READER_RS_FIXED_PAGE ? capture.fixed->end : capture.anchor->end;
  expect(match.state == (plan_case.at(name).first == "AMBIGUOUS" ? EXR_ANCHOR_AMBIGUOUS : EXR_ANCHOR_FOUND), std::string(name) + " sender-side capture self-check (not receiver proof)");
  sent_cases.push_back({name, capture.mode == READER_RS_REFLOW_GLOBAL ? "reflow_global" : capture.mode == READER_RS_EPUB_CHAPTER ? "epub_chapter" : "fixed_page", kind, key, id,
                        info.sha256, exact.size(), part, start, end, state_name(match.state)});
  reader_rs_record_free(&record);
}

void run_sender() {
  std::string orig = work + "/A-originals";
  original_root = orig;
  std::filesystem::create_directories(std::filesystem::u8path(orig));
  open_side(A);
  for (const char *role : kRoles) import(A, role, !std::strcmp(role, "txt") ? EXR_TXT : !std::strcmp(role, "epub") ? EXR_EPUB : !std::strcmp(role, "pdf") ? EXR_PDF : EXR_CBZ, std::strcmp(role, "txt") != 0);
  for (const char *role : kRoles) attach(A, role, !std::strcmp(role, "txt") ? "reflow_global" : !std::strcmp(role, "epub") ? "epub_chapter" : "fixed_page");
  for (const char *role : kRoles) {
    std::string destination = orig + "/" + shas[role] + "." + formats[role];
    uint64_t bytes = 0;
    exr_error error{};
    if (exr_sideload_export_original(A.lib, A.ids[role], destination.c_str(), nullptr, &bytes, &error) != EXR_OK || bytes != sizes[role]) fatal("SDK original export");
    ++originals_exported;
  }
  /* Unicode metadata: NFC, NFD, Russian, emoji exactly as pinned in the plan. */
  for (const char *role : kRoles)
    commit_book(A, std::string("book-") + role, role, S(std::string("title_") + role), S(std::string("author_") + role), true, {}, S(std::string("sort_") + role));
  /* Organization: conflict, tombstone, pending-parent, shelf and membership. */
  std::string tag_conflict = new_id(), tag_tomb = new_id(), tag_pending = new_id(), shelf = new_id();
  revrow root = commit_local(A, "conflict-root", "tag", tag_conflict, "put", {}, "{\"name\":" + esc(S("tag_root")) + "}");
  commit_local(A, "conflict-a", "tag", tag_conflict, "put", {root.id}, "{\"name\":" + esc(S("tag_a")) + "}");
  commit_local(A, "conflict-b", "tag", tag_conflict, "put", {root.id}, "{\"name\":" + esc(S("tag_b")) + "}");
  revrow t1 = commit_local(A, "tomb-put", "tag", tag_tomb, "put", {}, "{\"name\":" + esc(S("tag_tomb")) + "}");
  commit_local(A, "tomb-delete", "tag", tag_tomb, "delete", {t1.id}, "null");
  revrow p1 = commit_local(A, "pending-parent", "tag", tag_pending, "put", {}, "{\"name\":" + esc(S("tag_parent")) + "}");
  std::string child_id = new_id();
  while (shard_of(child_id) == shard_of(p1.id)) child_id = new_id();
  commit_local(A, "pending-child", "tag", tag_pending, "put", {p1.id}, "{\"name\":" + esc(S("tag_child")) + "}", child_id);
  commit_local(A, "shelf", "shelf", shelf, "put", {}, "{\"name\":" + esc(S("shelf_name")) + ",\"parent_id\":null,\"ordinal\":0}");
  std::string member_key = "shelf:" + shelf + ":" + keys["txt"];
  commit_local(A, "membership", "membership", member_key, "put", {},
               "{\"book_key\":" + esc(keys["txt"]) + ",\"collection_kind\":\"shelf\",\"collection_id\":" + esc(shelf) + ",\"ordinal\":0}");

  /* Eighteen real captures, in the pinned order. */
  exr_document *ta = nullptr;
  SDK(exr_library_document(A.lib, A.ids["txt"], &ta, &e_));
  size_t text_bytes = 0;
  const char *text = exr_document_text(ta, &text_bytes);
  std::string t(text, text_bytes);
  auto txt = [&](const char *name, const char *kind, size_t start, size_t end) {
    exr_anchor anchor{};
    SDK(exr_anchor_create(ta, start, end, &anchor, &e_));
    reader_rs_capture capture{};
    capture.mode = READER_RS_REFLOW_GLOBAL;
    capture.anchor = &anchor;
    capture_case(name, "txt", kind, capture, 0, [&](const reader_rs_record *r, exr_anchor_match *m) { return reader_rs_resolve_reflow(ta, r, nullptr, m, nullptr); });
    exr_anchor_free(&anchor);
  };
  size_t emoji = locate(t, "\xF0\x9F\x99\x82");
  txt("txt-progress-start", "progress", 0, 0);
  txt("txt-progress-multibyte", "progress", emoji, emoji);
  txt("txt-progress-end", "progress", text_bytes, text_bytes);
  size_t point = locate(t, "Tail alpha");
  txt("txt-bookmark", "annotation", point, point);
  txt("txt-highlight", "annotation", emoji, emoji + 4);
  size_t ambiguous = locate(t, "AMBIGUOUS TARGET", 1);
  txt("txt-ambiguous", "annotation", ambiguous, ambiguous + std::strlen("AMBIGUOUS TARGET"));

  std::string epub = read_file(paths["epub"]);
  int64_t gaid = 0;
  SDK(exr_library_import(A.lib, EXR_EPUB, epub.data(), epub.size(), "global", &gaid, &e_));
  exr_document *ga = nullptr;
  SDK(exr_library_document(A.lib, gaid, &ga, &e_));
  size_t gn = 0;
  const char *gt = exr_document_text(ga, &gn);
  const std::string chapter_quote = unhex(plan_case.at("epub-global-highlight").second);
  size_t chapter = locate(std::string(gt, gn), chapter_quote);
  for (int point_only = 0; point_only < 2; point_only++) {
    exr_anchor anchor{};
    SDK(exr_anchor_create(ga, chapter, chapter + (point_only ? 0 : chapter_quote.size()), &anchor, &e_));
    reader_rs_capture capture{};
    capture.mode = READER_RS_REFLOW_GLOBAL;
    capture.anchor = &anchor;
    capture_case(point_only ? "epub-global-progress" : "epub-global-highlight", "epub", point_only ? "progress" : "annotation", capture, 0,
                 [&](const reader_rs_record *r, exr_anchor_match *m) { return reader_rs_resolve_reflow(ga, r, nullptr, m, nullptr); });
    exr_anchor_free(&anchor);
  }
  exr_font *fnt = nullptr;
  SDK(exr_font_open(S("font").c_str(), &fnt, &e_));
  exr_publication *pa = nullptr;
  {
    exr_source source{};
    SDK(exr_library_source(A.lib, A.ids["epub"], &source, &e_));
    exr_error e{};
    if (exr_publication_open_source(&source, &pa, &e) != EXR_OK) { source.release(source.context); fatal("publication open"); }
  }
  size_t parts_count = 0;
  const exr_part *parts = exr_publication_parts(pa, &parts_count);
  expect(parts_count == 3, "fixture retains repeated spine path");
  for (size_t part = 0; part < parts_count; part++) {
    exr_layout_config config = exr_layout_config_defaults();
    exr_chapter_options options = exr_chapter_options_defaults();
    exr_pager *ap = nullptr;
    SDK(exr_publication_pager_create(pa, part, fnt, &config, &options, &ap, &e_));
    exr_anchor anchor{};
    SDK(exr_pager_anchor_create(ap, 0, 0, nullptr, &anchor, &e_));
    reader_rs_capture capture{};
    capture.mode = READER_RS_EPUB_CHAPTER;
    capture.anchor = &anchor;
    capture.part_path = parts[part].path;
    auto own = [&](const reader_rs_record *r, exr_anchor_match *m) { reader_rs_error error{}; return reader_rs_resolve_epub(pa, ap, part, r, nullptr, m, &error); };
    std::string name = "epub-bookmark-part-" + num(part);
    capture_case(name.c_str(), "epub", "annotation", capture, part, own);
    if (part == 1) capture_case("epub-chapter-progress", "epub", "progress", capture, part, own);
    exr_anchor_free(&anchor);
    exr_pager_free(ap);
  }
  exr_publication_free(pa);
  exr_font_free(fnt);
  for (const char *role : {"pdf", "cbz"}) {
    exr_fixed_open_options options{};
    options.struct_size = sizeof(options);
    exr_fixed_document *fa = nullptr;
    SDK(exr_library_fixed(A.lib, A.ids[role], &options, &fa, &e_));
    size_t pc = 0;
    const exr_fixed_page *pages = exr_fixed_pages(fa, &pc);
    auto fixed = [&](const char *name, const char *kind, size_t page, size_t start, size_t end) {
      exr_fixed_text *page_text = nullptr;
      SDK(exr_fixed_load_text(fa, page, nullptr, &page_text, &e_));
      exr_fixed_anchor anchor{};
      SDK(exr_fixed_anchor_create(pages[page].id, page_text, start, end, &anchor, &e_));
      reader_rs_capture capture{};
      capture.mode = READER_RS_FIXED_PAGE;
      capture.fixed = &anchor;
      capture.page = page;
      capture_case(name, role, kind, capture, 0, [&](const reader_rs_record *r, exr_anchor_match *m) { size_t resolved = SIZE_MAX; return reader_rs_resolve_fixed(fa, r, nullptr, &resolved, m, nullptr); });
      exr_fixed_anchor_free(&anchor);
      exr_fixed_text_free(page_text);
    };
    if (!std::strcmp(role, "pdf")) {
      exr_fixed_text *p = nullptr;
      SDK(exr_fixed_load_text(fa, 0, nullptr, &p, &e_));
      size_t pn = 0;
      const char *pt = exr_fixed_text_string(p, &pn);
      const std::string quote = unhex(plan_case.at("pdf-highlight").second);
      size_t at = locate(std::string(pt, pn), quote);
      exr_fixed_text_free(p);
      fixed("pdf-highlight", "annotation", 0, at, at + quote.size());
      fixed("pdf-bookmark", "annotation", 0, at, at);
      fixed("pdf-textless-bookmark", "annotation", 2, 0, 0);
      fixed("pdf-progress", "progress", 1, 0, 0);
    } else {
      fixed("cbz-bookmark", "annotation", 1, 0, 0);
      fixed("cbz-progress", "progress", 1, 0, 0);
    }
    exr_fixed_free(fa);
  }
  exr_document_free(ga);
  exr_document_free(ta);
  expect(sent_cases.size() == 18, "eighteen real captures were created");
  size_t total = pending(A).size();
  expect(total == 4 + 3 + 2 + 2 + 2 + 18, "outbox holds exactly the created revisions");

  /* Reopen the store, then retry: a cancelled publication changes nothing, the next one commits. */
  close_side(A);
  open_side(A);
  ++reopen_count;
  expect(pending(A).size() == total, "outbox survives actual library/catalog reopen");
  {
    net_side n(A, work + "/A-net", true);
    expect(n.cancelled_step(shard_of(pending(A).front().id)) != READER_SYNC_OK, "cancelled publication reports failure");
    expect(pending(A).size() == total, "cancelled publication keeps the whole outbox");
  }
  push_all(A, true, work + "/A-net");
  expect(network_pushed == total, "every revision was conditionally published exactly once");
  {
    net_side again(A, work + "/A-net", true);
    reader_sync_report r = again.step_shard(shard_of(sent_revs.front().id));
    (void)r;
  }
  expect(network_pushed == total, "an idempotent second sweep publishes nothing new");

  std::ostringstream out;
  for (const auto &r : sent_revs) out << "rev\t" << r.label << "\t" << r.kind << "\t" << r.key << "\t" << r.id << "\t" << r.sha << "\t" << r.bytes << "\n";
  for (const auto &c : sent_cases)
    out << "case\t" << c.id << "\t" << c.mode << "\t" << c.kind << "\t" << c.key << "\t" << c.rev << "\t" << c.sha << "\t" << c.bytes << "\t" << c.part << "\t" << c.start << "\t" << c.end << "\t" << c.state << "\n";
  std::ofstream(transport_path, std::ios::binary) << out.str();
  close_side(A);
}

/* ---------- receiver / confirmer ---------- */
struct world {
  exr_document *tb = nullptr, *gb = nullptr;
  exr_publication *pub = nullptr;
  exr_font *font = nullptr;
  std::vector<exr_pager *> pagers;
  exr_fixed_document *fixed_doc[2] = {nullptr, nullptr}; /* pdf, cbz */
};
world W;
std::string id_of(const std::string &label, const std::vector<std::vector<std::string>> &rows) {
  for (auto &r : rows) if (r[0] == "rev" && r[1] == label) return r[4];
  fatal("transport lacks " + label);
}
std::string sha_of(const std::string &label, const std::vector<std::vector<std::string>> &rows) {
  for (auto &r : rows) if (r[0] == "rev" && r[1] == label) return r[5];
  fatal("transport lacks " + label);
}
std::string key_of(const std::string &label, const std::vector<std::vector<std::string>> &rows) {
  for (auto &r : rows) if (r[0] == "rev" && r[1] == label) return r[3];
  fatal("transport lacks " + label);
}

void sweep_all(net_side &n, bool strict) {
  /* Counters describe the whole store, so zero is required once the final shard of the sweep is done. */
  for (unsigned shard = 0; shard < 256; shard++) n.step_shard(shard, strict && shard == 255);
}
void project_received_books(const std::string &epub_title_override) {
  std::vector<reader_revision_info> rows;
  reader_revision_error error{};
  if (reader_revision_entities_page(B.store, "book", nullptr, 1, 100, [](void *context, const reader_revision_entity_row *row) {
        if (row->selection.kind != READER_SELECTION_SAFE || row->selection.graph.deleted) fatal("received book metadata is not safe");
        ((std::vector<reader_revision_info> *)context)->push_back(row->info);
        return 0;
      }, &rows, &error) != READER_REV_OK || rows.size() != 4)
    fatal("received book discovery");
  (void)epub_title_override;
  for (const auto &row : rows) {
    char *title = nullptr;
    if (reader_revision_book_title(B.store, row.revision_id, &title, &error) != READER_REV_OK) fatal("received book title");
    if (reader_revision_project(B.store, "book", row.entity_key, row.revision_id, sort_for(title).c_str(), nullptr, &error) != READER_REV_OK) fatal("received safe metadata projection");
    reader_revision_bytes_free(title);
    ++metadata_projected;
  }
}
void check_book_metadata(const std::string &epub_title, bool epub_favorite) {
  for (const char *role : kRoles) {
    std::string title = !std::strcmp(role, "epub") ? epub_title : S(std::string("title_") + role);
    bool favorite = !std::strcmp(role, "epub") ? epub_favorite : true;
    struct observed_t { std::string title, author; bool favorite, mapped; int64_t sdk; bool ok = false; } o{title, S(std::string("author_") + role), favorite, false, B.ids[role]};
    int found = 0;
    reader_catalog_error error{};
    if (reader_catalog_find(B.catalog, keys[role].c_str(), nullptr, [](void *context, const reader_catalog_row *row) {
          auto &v = *(observed_t *)context;
          v.ok = v.title == row->title && row->favorite == (v.favorite ? 1 : 0) && v.author == row->author && v.sdk == row->sdk_book_id;
          return 0;
        }, &o, &found, &error))
      fatal("received book catalog mapping");
    expect(found && o.ok, std::string("received ") + role + " metadata preserves exact title/author/favorite and maps to the receiver's own SDK ID");
  }
}
std::string text_slice(const char *text, size_t n, size_t start, size_t end) { return start <= end && end <= n ? std::string(text + start, end - start) : std::string("<out of range>"); }

std::vector<std::string> case_reports;
size_t cases_found = 0, cases_mislocated = 0, cases_ambiguous = 0;
void verify_case(const std::vector<std::string> &row) {
  const std::string &id = row[1], &mode = row[2], &kind = row[3], &rev = row[5], &sha = row[6];
  size_t part = (size_t)std::stoull(row[8]);
  auto expected = plan_case.find(id);
  if (expected == plan_case.end()) fatal("unpinned case " + id);
  std::string quote = unhex(expected->second.second);
  char *wire = nullptr;
  size_t bytes = 0;
  reader_revision_info info{};
  reader_revision_error re{};
  if (reader_revision_get(B.store, rev.c_str(), &wire, &bytes, &info, &re) != READER_REV_OK) fatal(id + " revision missing on receiver");
  expect(sha == info.sha256 && bytes == (size_t)std::stoull(row[7]), id + " receiver holds the exact relayed wire bytes");
  reader_rs_record record{};
  reader_rs_error error{};
  if (reader_rs_decode(B.store, wire, bytes, &record, &error) != READER_RS_OK) fatal(id + " receiver decode");
  reader_revision_bytes_free(wire);
  expect(record.anchor_version == 2, id + " decodes anchor v2");
  size_t exact_n = record.exact ? (record.exact_size ? record.exact_size : std::strlen(record.exact)) : 0;
  std::string exact(record.exact ? record.exact : "", exact_n);
  exr_anchor_match match{};
  reader_rs_status st = READER_RS_ARGUMENT;
  std::string slice;
  bool have_slice = false;
  if (mode == "reflow_global") {
    exr_document *doc = row[4].compare(0, 4, "txt:") == 0 ? W.tb : W.gb;
    st = reader_rs_resolve_reflow(doc, &record, nullptr, &match, nullptr);
    size_t n = 0;
    const char *text = exr_document_text(doc, &n);
    slice = text_slice(text, n, match.start, match.end);
    have_slice = true;
  } else if (mode == "epub_chapter") {
    size_t routed = SIZE_MAX;
    expect(reader_rs_epub_record_part(W.pub, &record, &routed, &error) == READER_RS_OK && routed == part, id + " routes to its own spine index");
    st = reader_rs_resolve_epub(W.pub, W.pagers.at(part), part, &record, nullptr, &match, &error);
  } else {
    exr_fixed_document *doc = row[4].compare(0, 4, "pdf:") == 0 ? W.fixed_doc[0] : W.fixed_doc[1];
    size_t page = SIZE_MAX;
    st = reader_rs_resolve_fixed(doc, &record, nullptr, &page, &match, nullptr);
    if (page != SIZE_MAX) {
      exr_fixed_text *pt = nullptr;
      exr_error load_error{};
      if (exr_fixed_load_text(doc, page, nullptr, &pt, &load_error) == EXR_OK) {
        size_t n = 0;
        const char *text = exr_fixed_text_string(pt, &n);
        slice = text_slice(text ? text : "", n, match.start, match.end);
        have_slice = true;
        exr_fixed_text_free(pt);
      }
    }
  }
  const bool want_found = expected->second.first == "FOUND";
  bool correct = want_found ? st == READER_RS_OK && match.state == EXR_ANCHOR_FOUND && match.start == record.start && match.end == record.end
                            : st == READER_RS_UNRESOLVED && match.state == EXR_ANCHOR_AMBIGUOUS;
  expect(correct, id + " only exact FOUND permits navigation; ambiguity never locates");
  expect(exact == quote, id + " wire quote equals the pinned quote");
  if (want_found && have_slice && !quote.empty()) expect(slice == quote, id + " receiver SDK text at the located range equals the pinned quote");
  if (match.state == EXR_ANCHOR_FOUND) { ++cases_found; if (match.start != record.start || match.end != record.end) ++cases_mislocated; }
  if (match.state == EXR_ANCHOR_AMBIGUOUS) ++cases_ambiguous;
  case_reports.push_back(object().str("id", id).str("mode", mode).str("kind", kind).set("part", num(part)).set("start", num(match.start)).set("end", num(match.end))
                             .str("state", state_name(match.state)).str("revision_id", rev).str("wire_sha256", info.sha256).set("wire_bytes", num(bytes)).str("entity_key", row[4]).dump());
  reader_rs_record_free(&record);
}

void open_world() {
  for (const char *role : kRoles) { paths[role] = cached_original(role); sizes[role] = read_file(paths[role]).size(); }
  import(B, "txt", EXR_TXT, false);
  import(B, "epub", EXR_EPUB, true);
  import(B, "pdf", EXR_PDF, true);
  import(B, "cbz", EXR_CBZ, true);
  attach(B, "txt", "reflow_global");
  attach(B, "epub", "epub_chapter");
  attach(B, "pdf", "fixed_page");
  attach(B, "cbz", "fixed_page");
  SDK(exr_library_document(B.lib, B.ids["txt"], &W.tb, &e_));
  std::string epub = read_file(paths["epub"]);
  int64_t gbid = 0;
  SDK(exr_library_import(B.lib, EXR_EPUB, epub.data(), epub.size(), "global", &gbid, &e_));
  SDK(exr_library_document(B.lib, gbid, &W.gb, &e_));
  SDK(exr_font_open(S("font").c_str(), &W.font, &e_));
  exr_source source{};
  SDK(exr_library_source(B.lib, B.ids["epub"], &source, &e_));
  exr_error e{};
  if (exr_publication_open_source(&source, &W.pub, &e) != EXR_OK) { source.release(source.context); fatal("publication open"); }
  size_t count = 0;
  exr_publication_parts(W.pub, &count);
  for (size_t part = 0; part < count; part++) {
    exr_layout_config config = exr_layout_config_defaults();
    exr_chapter_options options = exr_chapter_options_defaults();
    exr_pager *p = nullptr;
    SDK(exr_publication_pager_create(W.pub, part, W.font, &config, &options, &p, &e_));
    W.pagers.push_back(p);
  }
  exr_fixed_open_options options{};
  options.struct_size = sizeof(options);
  SDK(exr_library_fixed(B.lib, B.ids["pdf"], &options, &W.fixed_doc[0], &e_));
  SDK(exr_library_fixed(B.lib, B.ids["cbz"], &options, &W.fixed_doc[1], &e_));
}
void close_world() {
  for (auto *p : W.pagers) exr_pager_free(p);
  W.pagers.clear();
  exr_publication_free(W.pub);
  exr_font_free(W.font);
  exr_document_free(W.tb);
  exr_document_free(W.gb);
  exr_fixed_free(W.fixed_doc[0]);
  exr_fixed_free(W.fixed_doc[1]);
  W = world();
}

reader_revision_selection select_state(const char *kind, const std::string &key, std::string *wire_out, reader_revision_info *info_out, reader_revision_status *status_out) {
  char *wire = nullptr;
  size_t bytes = 0;
  reader_revision_selection selection{};
  reader_revision_info info{};
  reader_revision_error e{};
  reader_revision_status st = reader_revision_selected(B.store, kind, key.c_str(), &wire, &bytes, &info, &selection, &e);
  if (wire) { if (wire_out) wire_out->assign(wire, bytes); reader_revision_bytes_free(wire); }
  if (info_out) *info_out = info;
  if (status_out) *status_out = st;
  return selection;
}

void verify_scenarios(const std::vector<std::vector<std::string>> &rows, bool returned) {
  /* Exact bytes for every relayed revision. */
  size_t checked = 0;
  for (auto &r : rows) {
    if (r[0] != "rev") continue;
    char *wire = nullptr;
    size_t bytes = 0;
    reader_revision_info info{};
    reader_revision_error e{};
    bool ok = reader_revision_get(B.store, r[4].c_str(), &wire, &bytes, &info, &e) == READER_REV_OK && r[5] == info.sha256 && bytes == (size_t)std::stoull(r[6]);
    reader_revision_bytes_free(wire);
    expect(ok, "relayed revision " + r[1] + " retained with exact sha256 and length");
    ++checked;
  }
  expect(checked == (returned ? 16u : 13u), "all non-capture revisions were checked");
  std::string conflict_key = key_of("conflict-root", rows);
  std::vector<std::string> conflict_heads = heads(B, "tag", conflict_key);
  std::string wire;
  reader_revision_status st;
  reader_revision_selection sel = select_state("tag", conflict_key, &wire, nullptr, &st);
  if (!returned) {
    expect(conflict_heads.size() == 2 && st == READER_REV_UNSAFE && sel.kind == READER_SELECTION_CONCURRENT, "concurrent tag heads stay visible and never auto-select");
    std::set<std::string> want{id_of("conflict-a", rows), id_of("conflict-b", rows)}, have(conflict_heads.begin(), conflict_heads.end());
    expect(want == have, "both concurrent heads are the relayed revisions");
  } else {
    expect(conflict_heads.size() == 1 && st == READER_REV_OK && sel.kind == READER_SELECTION_SAFE, "returned merge leaves one safe tag head");
  }
  sel = select_state("tag", key_of("tomb-put", rows), &wire, nullptr, &st);
  expect(st == READER_REV_OK && sel.kind == READER_SELECTION_SAFE && sel.graph.deleted && wire.find("\"operation\":\"delete\"") != std::string::npos, "tombstone is a retained safe delete");
  sel = select_state("tag", key_of("pending-parent", rows), &wire, nullptr, &st);
  expect(st == READER_REV_OK && sel.kind == READER_SELECTION_SAFE && wire.find(id_of("pending-child", rows)) != std::string::npos, "child head is safe once its parent arrived");
  sel = select_state("shelf", key_of("shelf", rows), &wire, nullptr, &st);
  expect(st == READER_REV_OK && sel.kind == READER_SELECTION_SAFE && wire.find(S("shelf_name")) != std::string::npos, "shelf name survives byte exact");
  sel = select_state("membership", key_of("membership", rows), &wire, nullptr, &st);
  if (!returned) expect(st == READER_REV_OK && sel.kind == READER_SELECTION_SAFE && !sel.graph.deleted, "membership is live");
  else expect(st == READER_REV_OK && sel.kind == READER_SELECTION_SAFE && sel.graph.deleted, "returned membership tombstone is the safe head");
}

void write_report(const std::string &path) {
  object report;
  report.set("cases", array(case_reports)).set("checks", array(checks)).set("failures", num(failures)).set("receiver_found", num(cases_found))
      .set("receiver_mislocated", num(cases_mislocated)).set("receiver_ambiguous", num(cases_ambiguous)).str("mode", mode_name)
      .set("network_pushed", num(network_pushed)).set("network_pulled", num(network_pulled)).set("originals_exported", num(originals_exported))
      .set("metadata_projected", num(metadata_projected)).set("cancelled_attempts", num(cancelled_attempts)).set("reopens", num(reopen_count));
  std::ofstream(path, std::ios::binary) << report.dump() << "\n";
}

void run_receiver(bool confirm) {
  auto rows = read_rows(transport_path);
  std::vector<std::vector<std::string>> returned_rows;
  if (confirm) returned_rows = read_rows(return_path);
  std::filesystem::create_directories(std::filesystem::u8path(cache_dir()));
  B.lib_path = work + "/B-library.sqlite";
  B.product_path = work + "/B-product.sqlite";
  open_side(B);
  std::string child = id_of("pending-child", rows), parent = id_of("pending-parent", rows);
  {
    net_side n(B, cache_dir(), false);
    if (!confirm) {
      expect(n.cancelled_step(shard_of(child)) != READER_SYNC_OK, "cancelled pull reports failure");
      std::vector<std::string> before = heads(B, "tag", key_of("pending-parent", rows));
      expect(before.empty(), "cancelled pull stored nothing");
      n.step_shard(shard_of(child));
      reader_revision_state state{};
      auto h = heads(B, "tag", key_of("pending-parent", rows), &state);
      std::string wire;
      reader_revision_status st;
      reader_revision_selection sel = select_state("tag", key_of("pending-parent", rows), &wire, nullptr, &st);
      expect(h.size() == 1 && h[0] == child && state.missing_parents >= 1 && st == READER_REV_UNSAFE && sel.kind == READER_SELECTION_PENDING_PARENTS,
             "child arriving before its parent is retained as pending and never projected");
    }
  }
  if (!confirm) {
    close_side(B);
    open_side(B);
    ++reopen_count;
    std::string wire;
    reader_revision_status st;
    reader_revision_selection sel = select_state("tag", key_of("pending-parent", rows), &wire, nullptr, &st);
    expect(st == READER_REV_UNSAFE && sel.kind == READER_SELECTION_PENDING_PARENTS, "pending parent survives actual store reopen");
  }
  {
    net_side n(B, cache_dir(), false);
    sweep_all(n, true);
  }
  expect(pending(B).empty(), "a receiver pull queues nothing for publication");
  (void)parent;
  /* Reopen again before reading everything back. */
  close_side(B);
  open_side(B);
  ++reopen_count;
  project_received_books("");
  open_world();
  std::string epub_title = S("title_epub");
  bool epub_fav = true;
  if (confirm) { epub_title = S("return_title_epub"); epub_fav = false; }
  /* Titles must be projected after every head arrived; confirm re-projects the returned edit. */
  check_book_metadata(epub_title, epub_fav);
  verify_scenarios(confirm ? returned_rows : rows, confirm);
  for (auto &r : rows) if (r[0] == "case") verify_case(r);
  expect(case_reports.size() == plan_case_order.size() && plan_case_order.size() == 18, "all eighteen pinned captures were read back");
  expect(cases_found == 17 && cases_ambiguous == 1 && cases_mislocated == 0, "17 FOUND and 1 planted ambiguity with zero mislocation");
  if (confirm) {
    for (auto &r : returned_rows) {
      if (r[0] != "retcase") continue;
      char *wire = nullptr;
      size_t bytes = 0;
      reader_revision_info info{};
      reader_revision_error re{};
      expect(reader_revision_get(B.store, r[4].c_str(), &wire, &bytes, &info, &re) == READER_REV_OK && r[5] == info.sha256, "returned reading capture retained exactly");
      reader_rs_record record{};
      reader_rs_error error{};
      expect(reader_rs_decode(B.store, wire, bytes, &record, &error) == READER_RS_OK, "returned reading capture decodes");
      reader_revision_bytes_free(wire);
      exr_anchor_match match{};
      reader_rs_status st = reader_rs_resolve_reflow(W.tb, &record, nullptr, &match, nullptr);
      size_t n = 0;
      const char *text = exr_document_text(W.tb, &n);
      expect(st == READER_RS_OK && match.state == EXR_ANCHOR_FOUND && text_slice(text, n, match.start, match.end) == unhex(r[6]) && match.start == record.start,
             "returned reading capture is located by the original sender's OS at the pinned quote");
      reader_rs_record_free(&record);
    }
  }
  if (!confirm && return_edit) {
    /* Return leg: metadata edit, conflict merge, membership tombstone, a new capture. */
    std::vector<std::string> epub_heads = heads(B, "book", keys["epub"]);
    expect(epub_heads.size() == 1, "book has one head before the returned edit");
    std::string original_author = S("author_epub");
    std::string edit_id = new_id();
    std::string edit_wire = make_wire(edit_id, "book", keys["epub"], "put", epub_heads, book_payload("epub", S("return_title_epub"), original_author, false));
    std::vector<const char *> expected_heads;
    for (auto &h : epub_heads) expected_heads.push_back(h.c_str());
    reader_revision_info info{};
    reader_revision_error re{};
    int created = 0, applied = 0;
    if (reader_revision_local_project(B.store, edit_wire.data(), edit_wire.size(), expected_heads.data(), expected_heads.size(), S("return_sort_epub").c_str(), &info, &created, &applied, &re) != READER_REV_OK || !created || !applied)
      fatal(std::string("returned book edit: ") + re.message);
    sent_revs.push_back({"return-book-edit", "book", keys["epub"], edit_id, info.sha256, edit_wire.size()});
    std::string tag_key = key_of("conflict-root", rows);
    commit_local(B, "return-tag-merge", "tag", tag_key, "put", heads(B, "tag", tag_key), "{\"name\":" + esc(S("tag_merge")) + "}");
    commit_local(B, "return-membership-delete", "membership", key_of("membership", rows), "delete", heads(B, "membership", key_of("membership", rows)), "null");
    exr_anchor anchor{};
    size_t n = 0;
    const char *text = exr_document_text(W.tb, &n);
    std::string quote = unhex(S("return_quote_hex"));
    size_t at = locate(std::string(text, n), quote);
    SDK(exr_anchor_create(W.tb, at, at + quote.size(), &anchor, &e_));
    reader_rs_capture capture{};
    capture.mode = READER_RS_REFLOW_GLOBAL;
    capture.anchor = &anchor;
    std::string rid = new_id(), aid = new_id(), key = keys["txt"] + ":" + aid;
    reader_rs_envelope envelope{};
    envelope.revision_id = rid.c_str();
    envelope.operation = "put";
    envelope.entity_kind = "annotation";
    envelope.book_key = keys["txt"].c_str();
    envelope.annotation_id = aid.c_str();
    envelope.note_text = "returned-highlight";
    envelope.parser_version = parser_version.c_str();
    char *wire = nullptr;
    size_t wire_bytes = 0;
    reader_rs_error error{};
    if (reader_rs_encode_v2(B.store, &envelope, &capture, 0, &wire, &wire_bytes, &error) != READER_RS_OK) fatal(std::string("returned capture encode: ") + error.message);
    std::string exact(wire, wire_bytes);
    reader_rs_free(wire);
    if (reader_revision_local_reading(B.store, exact.data(), exact.size(), nullptr, 0, &info, &created, &re) != READER_REV_OK || !created) fatal("returned capture commit");
    exr_anchor_free(&anchor);
    std::ostringstream out;
    for (const auto &r : sent_revs) out << "rev\t" << r.label << "\t" << r.kind << "\t" << r.key << "\t" << r.id << "\t" << r.sha << "\t" << r.bytes << "\n";
    out << "retcase\treturned-highlight\treflow_global\t" << key << "\t" << rid << "\t" << info.sha256 << "\t" << hexbytes(quote.data(), quote.size()) << "\n";
    /* The returned file also carries the original rows so the confirmer can look up unchanged labels. */
    for (auto &r : rows) if (r[0] == "rev") out << "rev\t" << r[1] << "\t" << r[2] << "\t" << r[3] << "\t" << r[4] << "\t" << r[5] << "\t" << r[6] << "\n";
    std::ofstream(return_path, std::ios::binary) << out.str();
    original_root = cache_dir();
    push_all(B, true, cache_dir());
    expect(pending(B).empty(), "returned revisions were published and acknowledged");
  }
  close_world();
  /* Final reopen: durable read-back without any SDK note copies. */
  close_side(B);
  open_side(B);
  ++reopen_count;
  std::string persisted;
  reader_revision_status st;
  reader_revision_selection sel = select_state("tag", key_of("conflict-root", rows), &persisted, nullptr, &st);
  expect(st == READER_REV_OK && sel.kind == READER_SELECTION_SAFE, "organization state survives the final reopen");
  close_side(B);
}
}  // namespace

int main(int argc, char **argv) {
  std::string fixtures, report_path, font;
  for (int i = 1; i + 1 < argc; i += 2) {
    std::string k = argv[i], v = argv[i + 1];
    if (k == "--mode") mode_name = v;
    else if (k == "--work") work = v;
    else if (k == "--report") report_path = v;
    else if (k == "--font") font = v;
    else if (k == "--webdav-root") webdav_root = v;
    else if (k == "--plan") plan_path = v;
    else if (k == "--transport") transport_path = v;
    else if (k == "--return") return_path = v;
    else if (k == "--return-edit") return_edit = v == "1";
    else if (k == "--fixtures") fixtures = v;
    else if (k == "--sha") { size_t equal = v.find('='); shas[v.substr(0, equal)] = v.substr(equal + 1); }
    else fatal("unknown argument " + k);
  }
  if (mode_name.empty() || work.empty() || webdav_root.empty() || plan_path.empty() || transport_path.empty() || report_path.empty()) fatal("missing argument");
  load_plan();
  plan_str["font"] = font;
  const char *roles[][3] = {{"txt", "book.txt", "txt"}, {"epub", "book.epub", "epub"}, {"pdf", "pages.pdf", "pdf"}, {"cbz", "pages.cbz", "cbz"}};
  for (auto &r : roles) {
    if (!shas.count(r[0])) fatal("missing pinned digest");
    formats[r[0]] = r[2];
    keys[r[0]] = std::string(r[2]) + ":" + shas[r[0]];
    if (mode_name == "send") { paths[r[0]] = fixtures + "/" + r[1]; sizes[r[0]] = read_file(paths[r[0]]).size(); }
  }
  parser_version = std::string("exreader-sdk-") + exr_version();
  std::filesystem::create_directories(std::filesystem::u8path(work));
  if (mode_name == "send") {
    A.lib_path = work + "/A-library.sqlite";
    A.product_path = work + "/A-product.sqlite";
    run_sender();
  } else if (mode_name == "receive" || mode_name == "confirm") {
    run_receiver(mode_name == "confirm");
  } else fatal("unknown mode");
  write_report(report_path);
  return failures ? 1 : 0;
}
