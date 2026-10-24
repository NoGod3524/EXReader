/* SPDX-License-Identifier: MIT */
/* Installed C++ consumer of EXReaderAnnotationView. Everything is built through
   public APIs in Actions: product schema1 history by reader_revision_receive/local,
   a real SDK library with progress and notes, and independent expectations from
   direct reader_revision_annotations_page/heads/get scans. */
#include <reader_annotation_view.h>
#include <reader_projection.h>
#include <reader_reading_state.h>
#include <exreader.h>
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <functional>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

namespace {
/* ---------- report ---------- */
std::string esc(const std::string &s) {
  static const char hex[] = "0123456789abcdef"; std::string o = "\"";
  for (unsigned char c : s) {
    if (c == '"' || c == '\\') { o += '\\'; o += (char)c; }
    else if (c < 0x20) { o += "\\u00"; o += hex[c >> 4]; o += hex[c & 15]; }
    else o += (char)c;
  }
  return o + "\"";
}
std::string num(unsigned long long v) { return std::to_string(v); }
struct object {
  std::vector<std::pair<std::string, std::string>> fields;
  object &set(const std::string &k, const std::string &raw) { fields.emplace_back(k, raw); return *this; }
  object &str(const std::string &k, const std::string &v) { return set(k, esc(v)); }
  std::string dump() const {
    std::string o = "{";
    for (size_t i = 0; i < fields.size(); i++) { if (i) o += ","; o += esc(fields[i].first) + ":" + fields[i].second; }
    return o + "}";
  }
};
std::vector<std::string> checks;
size_t failures = 0;
const size_t A_COUNT = 1203;
/* Crash-safe evidence: every check first records the exact step in progress.txt
   and then rewrites the whole report, so an unexpected fault still names its
   location and keeps the real result of every check that already ran. Only a
   report with complete=true is a finished run; the judge rejects anything else. */
std::string g_work, g_trace = "start", g_book_a_key, g_product_digest, g_sdk_digest;
size_t g_book_a_final = 0;
void write_report(bool complete);
[[noreturn]] void fatal(const std::string &what) { std::fprintf(stderr, "FATAL %s\n", what.c_str()); std::exit(2); }
void trace(const std::string &tag) {
  g_trace = tag;
  std::fprintf(stderr, "TRACE %s\n", tag.c_str()); std::fflush(stderr);
  if (g_work.empty()) return;
  std::ofstream out(g_work + "/progress.txt", std::ios::binary | std::ios::trunc);
  if (out) { out << tag << "\n"; out.flush(); }
}
void expect(bool ok, const std::string &name, const std::string &detail = "") {
  trace("check:" + name);
  if (!ok) { failures++; std::fprintf(stderr, "FAIL %s %s\n", name.c_str(), detail.c_str()); std::fflush(stderr); }
  checks.push_back(object().str("name", name).set("pass", ok ? "true" : "false").str("detail", detail).dump());
  write_report(false);
}
std::string read_file(const std::string &path) {
  std::ifstream in(path, std::ios::binary); if (!in) fatal("cannot read " + path);
  std::ostringstream s; s << in.rdbuf(); return s.str();
}
void write_file(const std::string &path, const std::string &data) {
  std::ofstream out(path, std::ios::binary); if (!out) fatal("cannot write " + path); out << data;
}
uint64_t fnv(const std::string &s) { uint64_t h = 14695981039346656037ull; for (unsigned char c : s) { h ^= c; h *= 1099511628211ull; } return h; }
std::string hex64(uint64_t v) { char b[20]; std::snprintf(b, sizeof b, "%016llx", (unsigned long long)v); return b; }

/* Compact SHA-256 for the transport digest that receive requires. */
std::string sha256_hex(const std::string &data) {
  static const uint32_t k[64] = {0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
  uint32_t h[8] = {0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
  std::string m = data; uint64_t bits = (uint64_t)data.size() * 8; m += (char)0x80;
  while (m.size() % 64 != 56) m += (char)0;
  for (int i = 7; i >= 0; i--) m += (char)((bits >> (i * 8)) & 0xff);
  auto rr = [](uint32_t x, int n) { return (x >> n) | (x << (32 - n)); };
  for (size_t off = 0; off < m.size(); off += 64) {
    uint32_t w[64];
    for (int i = 0; i < 16; i++) w[i] = ((uint32_t)(unsigned char)m[off + i * 4] << 24) | ((uint32_t)(unsigned char)m[off + i * 4 + 1] << 16) | ((uint32_t)(unsigned char)m[off + i * 4 + 2] << 8) | (uint32_t)(unsigned char)m[off + i * 4 + 3];
    for (int i = 16; i < 64; i++) { uint32_t s0 = rr(w[i - 15], 7) ^ rr(w[i - 15], 18) ^ (w[i - 15] >> 3), s1 = rr(w[i - 2], 17) ^ rr(w[i - 2], 19) ^ (w[i - 2] >> 10); w[i] = w[i - 16] + s0 + w[i - 7] + s1; }
    uint32_t a = h[0], b = h[1], c = h[2], d = h[3], e = h[4], f = h[5], g = h[6], hh = h[7];
    for (int i = 0; i < 64; i++) {
      uint32_t t1 = hh + (rr(e, 6) ^ rr(e, 11) ^ rr(e, 25)) + ((e & f) ^ (~e & g)) + k[i] + w[i], t2 = (rr(a, 2) ^ rr(a, 13) ^ rr(a, 22)) + ((a & b) ^ (a & c) ^ (b & c));
      hh = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
    }
    h[0] += a; h[1] += b; h[2] += c; h[3] += d; h[4] += e; h[5] += f; h[6] += g; h[7] += hh;
  }
  char out[65]; for (int i = 0; i < 8; i++) std::snprintf(out + i * 8, 9, "%08x", h[i]);
  return out;
}

/* ---------- deterministic IDs and wire rendering ---------- */
uint64_t mix(uint64_t x) {
  x += 0x9E3779B97F4A7C15ull; x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9ull; x = (x ^ (x >> 27)) * 0x94D049BB133111EBull; return x ^ (x >> 31);
}
std::set<std::string> used_ids;
std::string mkid(char tag, uint64_t n) {
  uint64_t a = mix(((uint64_t)(unsigned char)tag << 56) ^ n), b = mix(a ^ 0x5bd1e995ull);
  char buf[40]; std::snprintf(buf, sizeof buf, "%016llx%016llx", (unsigned long long)a, (unsigned long long)b);
  if (!used_ids.insert(buf).second) fatal("id collision");
  return buf;
}
uint64_t rev_counter = 0;

reader_revisions *store = nullptr;
std::vector<std::pair<std::string, std::string>> history; /* revision id -> exact wire */
std::set<std::string> entity_keys;

void write_report(bool complete) {
  if (g_work.empty()) return;
  std::string json = "[";
  for (size_t i = 0; i < checks.size(); i++) { if (i) json += ","; json += checks[i]; }
  json += "]";
  object report;
  report.str("module_version", READER_ANNOTATION_VIEW_VERSION).str("revisions_version", READER_REVISIONS_VERSION)
        .set("checks", json).set("checks_total", num(checks.size())).set("checks_failed", num(failures))
        .set("history_revisions", num(history.size())).set("book_a_initial", num(A_COUNT))
        .set("book_a_final", num(g_book_a_final)).str("book_a_key", g_book_a_key)
        .str("product_digest", g_product_digest).str("sdk_digest", g_sdk_digest)
        .set("complete", complete ? "true" : "false").str("last_trace", g_trace);
  write_file(g_work + "/report.json", report.dump() + "\n");
}

struct spec {
  std::string book, aid, rev, op = "put", mode = "reflow_global";
  std::vector<std::string> parents;
  int anchor = 2;
  std::string exact, prefix, suffix, text, part_path, page_id, chapter;
  bool has_chapter = false;
  uint64_t start = 0, end = 0, part = 0, page = 0;
};
std::string render(const spec &s) {
  std::string loc = "{\"mode\":" + esc(s.mode) + ",\"parser_version\":\"3.40.0\",\"anchor_version\":" + num((unsigned)s.anchor);
  if (s.mode == "epub_chapter") { loc += ",\"part_path\":" + esc(s.part_path); if (s.anchor == 2) loc += ",\"part\":" + num(s.part); }
  if (s.mode == "fixed_page") loc += ",\"page_id\":" + esc(s.page_id) + ",\"page\":" + num(s.page);
  loc += ",\"selector\":{\"exact\":" + esc(s.exact) + ",\"prefix\":" + esc(s.prefix) + ",\"suffix\":" + esc(s.suffix) +
         ",\"start\":" + num(s.start) + ",\"end\":" + num(s.end);
  if (s.anchor == 2 && s.mode == "reflow_global") loc += ",\"chapter\":" + (s.has_chapter ? esc(s.chapter) : std::string("null"));
  loc += "}}";
  std::string parents = "[";
  for (size_t i = 0; i < s.parents.size(); i++) { if (i) parents += ","; parents += esc(s.parents[i]); }
  parents += "]";
  std::string payload = "null";
  if (s.op != "delete")
    payload = "{\"book_key\":" + esc(s.book) + ",\"annotation_id\":" + esc(s.aid) + ",\"location\":" + loc + ",\"text\":" + esc(s.text) + "}";
  return "{\"version\":1,\"id\":" + esc(s.rev) + ",\"entity_kind\":\"annotation\",\"entity_key\":" + esc(s.book + ":" + s.aid) +
         ",\"operation\":" + esc(s.op) + ",\"location_kind\":" + esc(s.mode) + ",\"parents\":" + parents + ",\"payload\":" + payload + "}";
}
void submit(const spec &s, bool local = false) {
  std::string wire = render(s);
  reader_revision_info info{}; reader_revision_error e{};
  reader_revision_status st = reader_revision_validate(store, wire.data(), wire.size(), nullptr, &info, &e);
  if (st != READER_REV_OK) fatal("validate " + s.rev + ": " + e.message);
  int created = 0;
  if (local) st = reader_revision_local(store, wire.data(), wire.size(), &info, &created, &e);
  else st = reader_revision_receive(store, wire.data(), wire.size(), sha256_hex(wire).c_str(), &info, &created, &e);
  if (st != READER_REV_OK || !created) fatal("submit " + s.rev + ": " + e.message);
  history.emplace_back(s.rev, wire); entity_keys.insert(s.book + ":" + s.aid);
}
spec mk(const std::string &book, const std::string &aid, const std::string &mode) {
  spec s; s.book = book; s.aid = aid; s.mode = mode; s.rev = mkid('r', ++rev_counter); return s;
}
void quote(spec &s, const std::string &exact, uint64_t start) { s.exact = exact; s.prefix = "before "; s.suffix = " after"; s.start = start; s.end = start + exact.size(); }
void point(spec &s, uint64_t at) { s.exact.clear(); s.prefix = "p"; s.suffix = "s"; s.start = s.end = at; }

/* ---------- ground truth ---------- */
struct truth_item {
  reader_av_state state = READER_AV_STATE_SAFE; reader_av_kind kind = READER_AV_KIND_UNAVAILABLE;
  spec head; size_t revisions = 1, heads = 1, missing = 0;
};
std::map<std::string, std::map<std::string, truth_item>> truth;
reader_av_kind kind_of(const spec &s) {
  if (s.op == "delete") return READER_AV_KIND_TOMBSTONE;
  if (s.exact.empty() && s.start == s.end) return READER_AV_KIND_BOOKMARK;
  return s.text.empty() ? READER_AV_KIND_HIGHLIGHT : READER_AV_KIND_NOTE;
}
void reg(const spec &head, reader_av_state state, size_t revisions, size_t heads, size_t missing = 0) {
  truth_item t; t.state = state; t.head = head; t.revisions = revisions; t.heads = heads; t.missing = missing;
  t.kind = state == READER_AV_STATE_SAFE ? kind_of(head) : READER_AV_KIND_UNAVAILABLE;
  truth[head.book][head.aid] = t;
}
void make_reflow(const std::string &book, char tag, uint64_t i, int cls) {
  std::string aid = mkid(tag, i), n = std::to_string(i);
  spec s = mk(book, aid, "reflow_global");
  switch (cls) {
    case 0: point(s, i * 3); s.text = "书签 " + n; submit(s); reg(s, READER_AV_STATE_SAFE, 1, 1); break;
    case 1: s.anchor = 1; quote(s, "quote one " + n, i * 10); s.prefix = std::string(300, 'p'); submit(s); reg(s, READER_AV_STATE_SAFE, 1, 1); break;
    case 2: quote(s, "quote two " + n, i * 10); submit(s); reg(s, READER_AV_STATE_SAFE, 1, 1); break;
    case 3: s.anchor = 1; quote(s, "quote three " + n, i * 10); s.text = "笔记 🙂 " + n; submit(s); reg(s, READER_AV_STATE_SAFE, 1, 1); break;
    case 4: quote(s, "quote four " + n, i * 10); s.text = "note \"four\" " + n; s.has_chapter = true; s.chapter = "c1.xhtml"; submit(s); reg(s, READER_AV_STATE_SAFE, 1, 1); break;
    case 5: {
      quote(s, "quote five " + n, i * 10); s.text = "to delete"; submit(s);
      spec d = mk(book, aid, "reflow_global"); d.op = "delete"; d.parents = {s.rev}; submit(d); reg(d, READER_AV_STATE_SAFE, 2, 1); break;
    }
    case 6: {
      quote(s, "quote six " + n, i * 10); s.text = "first"; submit(s);
      spec d = mk(book, aid, "reflow_global"); d.op = "delete"; d.parents = {s.rev}; submit(d);
      spec r = mk(book, aid, "reflow_global"); r.op = "restore"; r.parents = {d.rev}; quote(r, "quote six " + n, i * 10); r.text = "restored"; submit(r);
      reg(r, READER_AV_STATE_SAFE, 3, 1); break;
    }
    case 7: {
      quote(s, "quote seven " + n, i * 10); s.text = "root"; submit(s);
      spec a = mk(book, aid, "reflow_global"); a.parents = {s.rev}; quote(a, "quote seven " + n, i * 10); a.text = "branch a"; submit(a);
      spec b = mk(book, aid, "reflow_global"); b.parents = {s.rev}; quote(b, "quote seven " + n, i * 10); b.text = "branch b"; submit(b);
      reg(a, READER_AV_STATE_CONCURRENT, 3, 2); break;
    }
    case 8: quote(s, "quote eight " + n, i * 10); s.text = "orphan"; s.parents = {mkid('m', i)}; submit(s); reg(s, READER_AV_STATE_PENDING_PARENTS, 1, 1, 1); break;
    case 9: {
      quote(s, "quote nine " + n, i * 10); s.text = "first"; submit(s);
      spec d = mk(book, aid, "reflow_global"); d.op = "delete"; d.parents = {s.rev}; submit(d);
      spec x = mk(book, aid, "reflow_global"); x.parents = {d.rev}; quote(x, "quote nine " + n, i * 10); x.text = "implicit revive"; submit(x);
      reg(x, READER_AV_STATE_BLOCKED_RESTORE, 3, 1); break;
    }
    case 10: {
      quote(s, "quote ten " + n, i * 10); submit(s);
      spec e = mk(book, aid, "reflow_global"); e.parents = {s.rev}; quote(e, "quote ten " + n, i * 10); e.text = "edited"; submit(e);
      reg(e, READER_AV_STATE_SAFE, 2, 1); break;
    }
    default: {
      std::string wide; for (int k = 0; k < 1000; k++) wide += "字";
      s.anchor = 1; quote(s, wide, i * 10); submit(s); reg(s, READER_AV_STATE_SAFE, 1, 1); break;
    }
  }
}

/* ---------- direct public scans (independent of the module) ---------- */
struct refrow {
  std::string id, rev, sha; reader_selection_kind kind = READER_SELECTION_MISSING; reader_revision_state graph{}; size_t bytes = 0;
};
struct refctx { std::vector<refrow> rows; };
int ref_visit(void *c, const reader_revision_annotation_row *row) {
  refrow r; r.id = row->annotation_id; r.kind = row->selection.kind; r.graph = row->selection.graph;
  if (row->selection.kind == READER_SELECTION_SAFE) { r.rev = row->info.revision_id; r.sha = row->info.sha256; r.bytes = row->info.bytes; }
  static_cast<refctx *>(c)->rows.push_back(r); return 0;
}
std::vector<refrow> ref_scan(const std::string &book, int direction, size_t limit) {
  std::vector<refrow> all; std::string after; bool has = false;
  for (int guard = 0; guard < 100000; guard++) {
    refctx c; reader_revision_error e{};
    if (reader_revision_annotations_page(store, book.c_str(), has ? after.c_str() : nullptr, direction, limit, ref_visit, &c, &e) != READER_REV_OK)
      fatal(std::string("reference page: ") + e.message);
    for (auto &r : c.rows) all.push_back(r);
    if (c.rows.size() < limit) return all;
    trace("refpage:" + book.substr(0, 8) + ":" + std::to_string(direction) + ":" + std::to_string(all.size()));
    has = true; after = c.rows.back().id;
  }
  fatal("reference scan did not terminate");
}
std::vector<std::string> ids_of(const std::vector<refrow> &rows) { std::vector<std::string> o; for (auto &r : rows) o.push_back(r.id); return o; }
reader_av_state state_of(reader_selection_kind k) {
  switch (k) {
    case READER_SELECTION_SAFE: return READER_AV_STATE_SAFE; case READER_SELECTION_CONCURRENT: return READER_AV_STATE_CONCURRENT;
    case READER_SELECTION_PENDING_PARENTS: return READER_AV_STATE_PENDING_PARENTS;
    case READER_SELECTION_BLOCKED_RESTORE: return READER_AV_STATE_BLOCKED_RESTORE; default: return READER_AV_STATE_MISSING;
  }
}

/* ---------- module helpers ---------- */
struct view_guard {
  reader_av_view *v = nullptr;
  ~view_guard() { reader_av_error e{}; if (v) reader_av_close(&v, &e); }
};
reader_av_view *open_view(const std::string &book, const reader_av_options *o = nullptr) {
  reader_av_view *v = nullptr; reader_av_error e{};
  if (reader_av_open(store, book.c_str(), o, &v, &e) != READER_AV_OK) fatal(std::string("open view: ") + e.message);
  return v;
}
std::string str_or_null(const char *s, size_t n) { return s ? "S" + std::string(s, n) : "N"; }
std::string item_error(const reader_av_item &it, const refrow &ref, const truth_item &t) {
  auto bad = [&](const std::string &what) { return std::string(it.annotation_id) + ": " + what; };
  if (ref.id != it.annotation_id) return bad("id differs from the direct public scan");
  if (it.state != state_of(ref.kind)) return bad("state differs from the direct public scan");
  if (it.state != t.state) return bad("state differs from construction");
  if (it.revisions != ref.graph.revisions || it.heads != ref.graph.heads || it.missing_parents != ref.graph.missing_parents ||
      it.foreign_parents != ref.graph.foreign_parents || it.deleted != (ref.graph.deleted ? 1 : 0) || it.requires_restore != (ref.graph.requires_restore ? 1 : 0))
    return bad("graph counts differ from the direct public scan");
  if (it.revisions != t.revisions || it.heads != t.heads || it.missing_parents != t.missing) return bad("graph counts differ from construction");
  if (it.resolution != READER_AV_RESOLUTION_NOT_ATTEMPTED) return bad("resolution is not NOT_ATTEMPTED");
  if (it.state != READER_AV_STATE_SAFE) {
    if (it.kind != READER_AV_KIND_UNAVAILABLE || it.content_available || it.revision_id[0] || it.sha256[0] || it.operation[0] || it.wire_bytes ||
        it.mode != READER_AV_MODE_NONE || it.has_location || it.legacy_anchor || it.anchor_version || it.parser_version[0] || it.has_part || it.part ||
        it.has_page || it.page || it.start || it.end || it.part_path || it.page_id || it.exact || it.prefix || it.suffix || it.chapter || it.note_text ||
        it.exact_size || it.prefix_size || it.suffix_size || it.note_size)
      return bad("non-SAFE item exposes body or revision identity");
    return "";
  }
  const spec &h = t.head;
  if (it.kind != t.kind) return bad("kind differs from construction");
  if (ref.rev != it.revision_id || h.rev != it.revision_id || ref.sha != it.sha256 || ref.bytes != it.wire_bytes) return bad("revision identity differs");
  if (h.op != it.operation) return bad("operation differs");
  reader_av_mode mode = h.mode == "reflow_global" ? READER_AV_MODE_REFLOW : h.mode == "epub_chapter" ? READER_AV_MODE_EPUB : READER_AV_MODE_FIXED;
  if (it.mode != mode) return bad("mode differs");
  if (it.kind == READER_AV_KIND_TOMBSTONE) {
    if (it.content_available || it.has_location || it.exact || it.note_text || it.part_path || it.page_id || it.chapter) return bad("tombstone carries a body");
    return "";
  }
  if (!it.content_available || !it.has_location || it.anchor_version != (uint64_t)h.anchor || it.legacy_anchor != (h.anchor == 1 ? 1 : 0) ||
      std::strcmp(it.parser_version, "3.40.0") != 0) return bad("location header differs");
  if (it.start != h.start || it.end != h.end) return bad("offset hints differ");
  if (str_or_null(it.exact, it.exact_size) != "S" + h.exact || str_or_null(it.prefix, it.prefix_size) != "S" + h.prefix ||
      str_or_null(it.suffix, it.suffix_size) != "S" + h.suffix || str_or_null(it.note_text, it.note_size) != "S" + h.text) return bad("quote/context/note bytes differ");
  bool want_chapter = h.anchor == 2 && h.mode == "reflow_global" && h.has_chapter;
  if ((it.chapter != nullptr) != want_chapter || (want_chapter && h.chapter != it.chapter)) return bad("chapter scope differs");
  bool epub = h.mode == "epub_chapter", fixed = h.mode == "fixed_page";
  if ((it.part_path != nullptr) != epub || (epub && h.part_path != it.part_path)) return bad("part path differs");
  if (it.has_part != ((epub && h.anchor == 2) ? 1 : 0) || it.part != ((epub && h.anchor == 2) ? h.part : 0)) return bad("spine index differs");
  if ((it.page_id != nullptr) != fixed || (fixed && h.page_id != it.page_id) || it.has_page != (fixed ? 1 : 0) || it.page != (fixed ? h.page : 0)) return bad("fixed page route differs");
  return "";
}
struct scan_result {
  size_t pages = 0, items = 0, early_complete = 0, empty_incomplete = 0, bad_items = 0; bool ok = true, last_complete = false;
  std::string error; std::vector<std::string> ids;
  std::map<int, size_t> by_state, by_kind;
};
scan_result scan(reader_av_view *v, const std::string &book, int direction, size_t limit, const std::vector<refrow> *ref) {
  scan_result r; reader_av_cursor cur{}; reader_av_error e{};
  if (reader_av_cursor_start(v, direction, &cur, &e) != READER_AV_OK) fatal(std::string("cursor start: ") + e.message);
  std::vector<refrow> expected;
  if (ref) { expected = *ref; if (direction == -1) std::reverse(expected.begin(), expected.end()); }
  for (int guard = 0; guard < 100000; guard++) {
    reader_av_page p{};
    if (reader_av_page_get(v, &cur, limit, &p, &e) != READER_AV_OK) { r.ok = false; r.error = e.message; break; }
    r.pages++;
    if (!p.complete && p.count == 0) r.empty_incomplete++;
    for (size_t i = 0; i < p.count; i++) {
      const reader_av_item &it = p.items[i];
      if (ref) {
        size_t at = r.ids.size();
        if (at >= expected.size()) { r.bad_items++; r.error = "more items than the direct scan"; }
        else {
          auto found = truth[book].find(it.annotation_id);
          std::string err = found == truth[book].end() ? std::string("unknown id") : item_error(it, expected[at], found->second);
          if (!err.empty()) { r.bad_items++; if (r.error.empty()) r.error = err; }
        }
      }
      r.ids.push_back(it.annotation_id); r.by_state[it.state]++; r.by_kind[it.kind]++; r.items++;
    }
    trace("page:" + book.substr(0, 8) + ":" + std::to_string(direction) + ":" + std::to_string(limit) + ":" + std::to_string(r.pages));
    if (!p.complete && p.count < limit && !p.budget_stopped) r.early_complete++;
    bool done = p.complete; r.last_complete = p.complete; cur = p.next;
    reader_av_page_free(&p);
    if (done) break;
  }
  if (ref && r.ids.size() != expected.size()) { r.ok = false; if (r.error.empty()) r.error = "item count differs from the direct scan"; }
  return r;
}
std::string page_digest(const reader_av_page &p) {
  std::string d = num(p.count) + (p.complete ? "C" : "-");
  for (size_t i = 0; i < p.count; i++) {
    const reader_av_item &it = p.items[i];
    d += "|" + std::string(it.annotation_id) + "," + num(it.state) + "," + num(it.kind) + "," + num(it.revisions) + "," + it.revision_id + "," + it.sha256 + "," +
         num(it.wire_bytes) + "," + num(it.mode) + "," + num(it.start) + "," + num(it.end) + "," + num(it.part) + "," + num(it.page) + "," +
         str_or_null(it.part_path, it.part_path ? std::strlen(it.part_path) : 0) + "," + str_or_null(it.page_id, it.page_id ? std::strlen(it.page_id) : 0) + "," +
         str_or_null(it.exact, it.exact_size) + "," + str_or_null(it.prefix, it.prefix_size) + "," + str_or_null(it.suffix, it.suffix_size) + "," +
         str_or_null(it.chapter, it.chapter ? std::strlen(it.chapter) : 0) + "," + str_or_null(it.note_text, it.note_size);
  }
  return d;
}

/* ---------- product and SDK state dumps ---------- */
struct head_ctx { std::string out; };
int head_visit(void *c, const reader_revision_head *h) {
  static_cast<head_ctx *>(c)->out += std::string("H:") + h->revision_id + "," + h->operation + "," + h->sha256 + "," + std::to_string(h->complete) + "," + std::to_string(h->requires_restore) + ";";
  return 0;
}
int outbox_visit(void *c, const reader_revision_outbox_row *r) {
  static_cast<head_ctx *>(c)->out += std::string("O:") + r->info.revision_id + "," + std::to_string((long long)r->queue_id) + "," + std::to_string((long long)r->attempts) + "," +
                                      (r->last_error ? r->last_error : "") + "," + std::string(r->wire) + ";";
  return 0;
}
std::string product_dump(const std::string &db_path) {
  std::string out;
  for (auto &h : history) {
    char *wire = nullptr; size_t bytes = 0; reader_revision_info info{}; reader_revision_error e{};
    if (reader_revision_get(store, h.first.c_str(), &wire, &bytes, &info, &e) != READER_REV_OK) fatal(std::string("history get: ") + e.message);
    out += "R:" + h.first + "," + std::string(info.sha256) + "," + std::string(wire, bytes) + ";"; reader_revision_bytes_free(wire);
  }
  for (auto &k : entity_keys) {
    head_ctx c; reader_revision_state st{}; reader_revision_error e{};
    if (reader_revision_heads(store, "annotation", k.c_str(), head_visit, &c, &st, &e) != READER_REV_OK) fatal(std::string("heads: ") + e.message);
    out += "E:" + k + "," + std::to_string(st.revisions) + "," + std::to_string(st.heads) + "," + std::to_string(st.missing_parents) + "," + std::to_string(st.deleted) + ";" + c.out;
  }
  head_ctx c; reader_revision_error e{};
  if (reader_revision_outbox(store, 100, outbox_visit, &c, &e) != READER_REV_OK) fatal(std::string("outbox: ") + e.message);
  out += c.out; out += "F:" + hex64(fnv(read_file(db_path))) + "," + std::to_string(read_file(db_path).size());
  return out;
}
std::string sdk_dump(exr_library *lib, int64_t book, const std::string &lib_path) {
  std::string out; exr_error e{};
  exr_anchor point{}; exr_anchor_state state{};
  if (exr_library_progress_get(lib, book, &point, &state, &e) != EXR_OK) fatal(std::string("progress_get: ") + e.message);
  out += "P:" + std::to_string((int)state) + "," + std::to_string(point.start) + "," + std::to_string(point.end) + "," + (point.exact ? point.exact : "~") + ";";
  exr_anchor_free(&point);
  exr_note *notes = nullptr; size_t count = 0;
  if (exr_library_notes(lib, book, &notes, &count, &e) != EXR_OK) fatal(std::string("notes: ") + e.message);
  for (size_t i = 0; i < count; i++)
    out += "N:" + std::to_string((long long)notes[i].id) + "," + std::to_string(notes[i].start) + "," + std::to_string(notes[i].end) + "," + (notes[i].text ? notes[i].text : "~") + "," +
           (notes[i].anchor.exact ? notes[i].anchor.exact : "~") + ";";
  exr_notes_free(notes, count);
  out += "F:" + hex64(fnv(read_file(lib_path))) + "," + std::to_string(read_file(lib_path).size());
  return out;
}

/* ---------- cancellation and reentry ---------- */
struct canceler {
  uint64_t calls = 0, at = 0; int mode = 0; reader_av_view **view = nullptr; size_t busy_page = 0, busy_close = 0, start_ok = 0;
};
int cancel_cb(void *context) {
  canceler *k = static_cast<canceler *>(context); k->calls++;
  if (k->mode == 1 && k->view && *k->view) {
    reader_av_page p{}; reader_av_cursor c{}; reader_av_error e{};
    if (reader_av_page_get(*k->view, &c, 1, &p, &e) == READER_AV_BUSY && p.items == nullptr && p.count == 0) k->busy_page++;
    reader_av_view *same = *k->view;
    if (reader_av_close(&same, &e) == READER_AV_BUSY && same == *k->view) k->busy_close++;
    reader_av_cursor s{}; if (reader_av_cursor_start(*k->view, 1, &s, &e) == READER_AV_OK) k->start_ok++;
    reader_av_page_free(&p);
  }
  return k->at && k->calls == k->at;
}
}

int main(int argc, char **argv) {
  std::string work, book_path, book_sha;
  for (int i = 1; i + 1 < argc; i += 2) {
    std::string a = argv[i];
    if (a == "--work") work = argv[i + 1]; else if (a == "--book") book_path = argv[i + 1]; else if (a == "--sha") book_sha = argv[i + 1];
  }
  if (work.empty() || book_path.empty() || book_sha.size() != 64) fatal("usage: probe --work DIR --book FILE --sha SHA256");
  g_work = work;
  trace("main:start");
  std::string db_path = work + "/product.sqlite", lib_path = work + "/sdk.sqlite";

  trace("main:sdk");
  /* SDK library with a real book, progress and notes (separate from the product catalog). */
  exr_library *lib = nullptr; exr_error ee{}; int64_t sdk_book = 0;
  if (exr_library_open(lib_path.c_str(), &lib, &ee) != EXR_OK) fatal(std::string("library open: ") + ee.message);
  std::string book_bytes = read_file(book_path);
  if (exr_library_import(lib, EXR_TXT, book_bytes.data(), book_bytes.size(), "annotation-view", &sdk_book, &ee) != EXR_OK) fatal(std::string("import: ") + ee.message);
  {
    exr_document *doc = nullptr; exr_anchor point{};
    if (exr_library_document(lib, sdk_book, &doc, &ee) != EXR_OK) fatal(std::string("document: ") + ee.message);
    if (exr_anchor_create(doc, 6, 6, &point, &ee) != EXR_OK) fatal(std::string("anchor: ") + ee.message);
    if (exr_library_progress(lib, sdk_book, &point, &ee) != EXR_OK) fatal(std::string("progress: ") + ee.message);
    exr_anchor_free(&point);
    exr_note note{}; int64_t nid = 0; note.book_id = sdk_book; note.start = 0; note.end = 5; note.text = const_cast<char *>("sdk note");
    if (exr_library_note(lib, &note, &nid, &ee) != EXR_OK) fatal(std::string("note: ") + ee.message);
    exr_document_free(doc);
  }

  trace("main:product_store");
  reader_revision_error re{};
  if (reader_revisions_open(db_path.c_str(), &store, &re) != READER_REV_OK) fatal(std::string("revisions open: ") + re.message);
  const std::string A = "txt:" + book_sha, B = "txt:" + mkid('k', 2) + mkid('k', 3), C = "txt:" + mkid('k', 4) + mkid('k', 5),
                    E = "epub:" + mkid('k', 6) + mkid('k', 7), P = "pdf:" + mkid('k', 8) + mkid('k', 9), Z = "txt:" + mkid('k', 10) + mkid('k', 11);
  g_book_a_key = A;

  /* ---------- dataset ---------- */
  trace("dataset:A");
  for (uint64_t i = 0; i < A_COUNT; i++) make_reflow(A, 'a', i, (int)(i % 12));
  trace("dataset:B");
  for (uint64_t i = 0; i < 100; i++) make_reflow(B, 'b', i, (int)(i % 5));
  trace("dataset:C");
  for (uint64_t i = 0; i < 120; i++) { /* large notes for the page-byte budget */
    spec s = mk(C, mkid('c', i), "reflow_global"); quote(s, "big " + std::to_string(i), i * 10);
    s.text = std::to_string(i) + ":" + std::string(65000, 'n'); submit(s); reg(s, READER_AV_STATE_SAFE, 1, 1);
  }
  trace("dataset:largest");
  { /* largest legal exact and note fields in one item */
    spec s = mk(C, mkid('c', 5000), "reflow_global"); quote(s, std::string(65536, 'x'), 0); s.text = std::string(65536, 'y'); submit(s); reg(s, READER_AV_STATE_SAFE, 1, 1);
  }
  trace("dataset:EPUB");
  { /* EPUB: duplicate spine path a.xhtml at parts 0 and 2, a v1 anchor without a part, and a bookmark; first five via the local outbox path */
    const char *paths[] = {"a.xhtml", "a.xhtml", "a.xhtml", "b.xhtml", "a.xhtml"};
    for (int i = 0; i < 5; i++) {
      spec s = mk(E, mkid('e', (uint64_t)i), "epub_chapter"); s.part_path = paths[i];
      if (i == 0) { s.part = 0; quote(s, "Repeated spine chapter", 4); }
      if (i == 1) { s.part = 2; quote(s, "Repeated spine chapter", 4); }
      if (i == 2) { s.anchor = 1; quote(s, "Repeated spine chapter", 4); s.text = "legacy no part"; }
      if (i == 3) { s.part = 1; point(s, 0); s.text = "chapter two mark"; }
      if (i == 4) { s.part = 2; quote(s, "second copy", 30); s.text = "note on part 2"; }
      submit(s, true); reg(s, READER_AV_STATE_SAFE, 1, 1);
    }
  }
  trace("dataset:PDF");
  { /* PDF/CBZ fixed pages: textless page point, v1 and v2 highlights, note */
    for (int i = 0; i < 4; i++) {
      spec s = mk(P, mkid('p', (uint64_t)i), "fixed_page"); s.page_id = "page-" + std::to_string(i + 1); s.page = (uint64_t)i;
      if (i == 0) { s.exact.clear(); s.prefix.clear(); s.suffix.clear(); s.start = s.end = 0; s.text = "textless page"; s.page_id = "page-3"; s.page = 2; }
      if (i == 1) { s.anchor = 1; quote(s, "page text v1", 2); }
      if (i == 2) quote(s, "page text v2", 9);
      if (i == 3) { quote(s, "page note", 1); s.text = "fixed note"; }
      submit(s); reg(s, READER_AV_STATE_SAFE, 1, 1);
    }
  }
  expect(history.size() > 2000, "dataset_history_size", std::to_string(history.size()) + " retained revisions");

  /* ---------- independent expectations ---------- */
  trace("section:independent_expectations");
  const std::vector<std::string> books = {A, B, C, E, P};
  std::map<std::string, std::vector<refrow>> ref;
  for (auto &b : books) {
    trace("refbook:" + b.substr(0, 8));
    ref[b] = ref_scan(b, 1, 100);
    std::vector<refrow> down = ref_scan(b, -1, 7); std::reverse(down.begin(), down.end());
    expect(ids_of(down) == ids_of(ref[b]), "direct_scan_ascending_equals_descending", b.substr(0, 8) + " " + std::to_string(down.size()));
    std::set<std::string> uniq(ids_of(ref[b]).begin(), ids_of(ref[b]).end());
    std::vector<std::string> sorted = ids_of(ref[b]); std::sort(sorted.begin(), sorted.end());
    std::set<std::string> want; for (auto &kv : truth[b]) want.insert(kv.first);
    expect(uniq.size() == ref[b].size() && sorted == ids_of(ref[b]) && uniq == want, "direct_scan_matches_construction", b.substr(0, 8) + " " + std::to_string(ref[b].size()));
  }
  expect(ref[A].size() == A_COUNT && A_COUNT > 1000, "book_has_more_than_1000_annotations", std::to_string(ref[A].size()));
  expect(ref[B].size() == 100, "book_has_exactly_100_annotations", std::to_string(ref[B].size()));
  { std::map<int, size_t> n; for (auto &r : ref[A]) n[(int)state_of(r.kind)]++;
    expect(n[READER_AV_STATE_SAFE] > 0 && n[READER_AV_STATE_CONCURRENT] > 0 && n[READER_AV_STATE_PENDING_PARENTS] > 0 && n[READER_AV_STATE_BLOCKED_RESTORE] > 0,
           "direct_scan_has_safe_concurrent_pending_blocked", "safe=" + num(n[1]) + " concurrent=" + num(n[2]) + " pending=" + num(n[3]) + " blocked=" + num(n[4])); }
  { std::set<std::string> a(ids_of(ref[A]).begin(), ids_of(ref[A]).end()); bool overlap = false;
    for (auto &b : {B, C, E, P}) for (auto &id : ids_of(ref[b])) if (a.count(id)) overlap = true;
    expect(!overlap, "annotation_ids_are_distinct_across_books"); }

  /* ---------- read-only section: capture state ---------- */
  trace("section:capture_state");
  const std::string product_before = product_dump(db_path), sdk_before = sdk_dump(lib, sdk_book, lib_path);
  g_product_digest = hex64(fnv(product_before)); g_sdk_digest = hex64(fnv(sdk_before));
  expect(product_before.size() > 1000000, "product_dump_covers_history_outbox_and_database", std::to_string(product_before.size()));

  std::map<std::string, scan_result> forward;
  trace("section:forward_scans");
  { view_guard g; g.v = open_view(A);
    for (size_t limit : {(size_t)100, (size_t)1, (size_t)7, (size_t)33}) {
      trace("scanA:" + std::to_string(limit));
      scan_result r = scan(g.v, A, 1, limit, &ref[A]);
      if (limit == 100) forward["A100"] = r;
      expect(r.ok && r.bad_items == 0 && r.ids == ids_of(ref[A]) && r.last_complete && r.early_complete == 0 && r.empty_incomplete == 0,
             "forward_scan_matches_direct_public_pages_limit_" + std::to_string(limit), "pages=" + num(r.pages) + " items=" + num(r.items) + " " + r.error);
    }
    trace("scanA:reverse");
    scan_result d = scan(g.v, A, -1, 100, &ref[A]);
    std::vector<std::string> down = ids_of(ref[A]); std::reverse(down.begin(), down.end());
    expect(d.ok && d.bad_items == 0 && d.ids == down && d.last_complete, "reverse_scan_matches_direct_public_pages", "pages=" + num(d.pages) + " " + d.error);
    scan_result f = forward["A100"];
    expect(f.pages == 13, "limit_100_over_1203_is_13_pages", std::to_string(f.pages));
    expect(f.by_state[READER_AV_STATE_SAFE] > 0 && f.by_state[READER_AV_STATE_CONCURRENT] > 0 && f.by_state[READER_AV_STATE_PENDING_PARENTS] > 0 &&
           f.by_state[READER_AV_STATE_BLOCKED_RESTORE] > 0 && f.by_kind[READER_AV_KIND_BOOKMARK] > 0 && f.by_kind[READER_AV_KIND_HIGHLIGHT] > 0 &&
           f.by_kind[READER_AV_KIND_NOTE] > 0 && f.by_kind[READER_AV_KIND_TOMBSTONE] > 0 && f.by_kind[READER_AV_KIND_UNAVAILABLE] > 0,
           "all_states_and_kinds_are_distinguished", "bookmark=" + num(f.by_kind.at(READER_AV_KIND_BOOKMARK)) + " tombstone=" + num(f.by_kind.at(READER_AV_KIND_TOMBSTONE)));

    /* continuation and reverse */
    trace("section:continuation");
    reader_av_cursor c0{}; reader_av_error e{}; reader_av_cursor_start(g.v, 1, &c0, &e);
    reader_av_page p1{}, p2{}, back{}, before_first{};
    reader_av_status s1 = reader_av_page_get(g.v, &c0, 100, &p1, &e);
    reader_av_status s2 = reader_av_page_get(g.v, &p1.next, 100, &p2, &e);
    reader_av_status s3 = reader_av_page_get(g.v, &p2.reverse, 100, &back, &e);
    reader_av_status s4 = reader_av_page_get(g.v, &p1.reverse, 100, &before_first, &e);
    bool same = s1 == READER_AV_OK && s2 == READER_AV_OK && s3 == READER_AV_OK && s4 == READER_AV_OK && back.count == 100;
    for (size_t i = 0; same && i < 100; i++) same = std::strcmp(back.items[i].annotation_id, p1.items[99 - i].annotation_id) == 0;
    expect(same && !p1.complete && !p2.complete && !back.complete, "reverse_cursor_returns_previous_100_in_descending_order");
    expect(s4 == READER_AV_OK && before_first.count == 0 && before_first.complete, "reverse_of_first_page_is_empty_and_complete");
    expect(s2 == READER_AV_OK && std::strcmp(p2.items[0].annotation_id, ref[A][100].id.c_str()) == 0 && p2.next.has_after && p1.next.has_after, "next_cursor_continues_without_overlap");
    reader_av_error er{};
    expect(reader_av_page_set_resolution(&p1, 3, READER_AV_RESOLUTION_AMBIGUOUS, &er) == READER_AV_OK && p1.items[3].resolution == READER_AV_RESOLUTION_AMBIGUOUS &&
           p1.items[4].resolution == READER_AV_RESOLUTION_NOT_ATTEMPTED && reader_av_page_set_resolution(&p1, 100, READER_AV_RESOLUTION_FOUND, &er) == READER_AV_ARGUMENT &&
           reader_av_page_set_resolution(&p1, 0, (reader_av_resolution)99, &er) == READER_AV_ARGUMENT, "host_resolution_is_recorded_only_in_the_snapshot");
    reader_av_page_free(&p1); reader_av_page_free(&p2); reader_av_page_free(&back); reader_av_page_free(&before_first);
    expect(p1.items == nullptr && p1.count == 0, "page_free_zeroes_the_page");

    /* 100-item page boundary: exactly 100 rows -> full page then empty complete page */
    trace("section:boundary_100");
    view_guard gb; gb.v = open_view(B);
    reader_av_cursor cb{}; reader_av_cursor_start(gb.v, 1, &cb, &e);
    reader_av_page q1{}, q2{};
    reader_av_status t1 = reader_av_page_get(gb.v, &cb, 100, &q1, &e), t2 = reader_av_page_get(gb.v, &q1.next, 100, &q2, &e);
    expect(t1 == READER_AV_OK && t2 == READER_AV_OK && q1.count == 100 && !q1.complete && q2.count == 0 && q2.complete && q2.next.complete,
           "exact_100_items_yield_full_page_then_empty_complete_page");
    reader_av_page q3{}; expect(reader_av_page_get(gb.v, &q2.next, 100, &q3, &e) == READER_AV_OK && q3.count == 0 && q3.complete, "complete_cursor_stays_complete");
    reader_av_page_free(&q1); reader_av_page_free(&q2); reader_av_page_free(&q3);
    scan_result rb = scan(gb.v, B, 1, 100, &ref[B]);
    expect(rb.ok && rb.bad_items == 0 && rb.ids == ids_of(ref[B]) && rb.pages == 2, "second_book_scan_matches_direct_pages", rb.error);
  }

  /* books: epub duplicate spine/v1/v2, fixed pages, empty book, large items */
  for (auto &pair : std::vector<std::pair<std::string, std::string>>{{E, "epub_v1_v2_duplicate_spine"}, {P, "fixed_pages_textless_v1_v2"}, {C, "large_notes_default_budget"}}) {
    trace("section:book_" + pair.second);
    view_guard g; g.v = open_view(pair.first);
    scan_result r = scan(g.v, pair.first, 1, 100, &ref[pair.first]);
    expect(r.ok && r.bad_items == 0 && r.ids == ids_of(ref[pair.first]), "scan_" + pair.second, "items=" + num(r.items) + " " + r.error);
  }
  { view_guard g; g.v = open_view(E); reader_av_cursor c{}; reader_av_error e{}; reader_av_cursor_start(g.v, 1, &c, &e); reader_av_page p{};
    bool ok = reader_av_page_get(g.v, &c, 100, &p, &e) == READER_AV_OK && p.count == 5;
    size_t with_part = 0, without = 0, dup = 0;
    for (size_t i = 0; ok && i < p.count; i++) { if (p.items[i].has_part) with_part++; else if (p.items[i].mode == READER_AV_MODE_EPUB && p.items[i].kind != READER_AV_KIND_UNAVAILABLE) without++;
      for (size_t j = 0; j < i; j++) if (p.items[i].part_path && p.items[j].part_path && !std::strcmp(p.items[i].part_path, p.items[j].part_path) && p.items[i].has_part && p.items[j].has_part && p.items[i].part != p.items[j].part) dup++; }
    expect(ok && with_part == 4 && without == 1 && dup > 0, "duplicate_spine_path_is_told_apart_by_part_and_v1_has_no_part", "v2=" + num(with_part) + " v1=" + num(without));
    reader_av_page_free(&p); }
  { view_guard g; g.v = open_view(Z); scan_result r = scan(g.v, Z, 1, 100, nullptr);
    expect(r.ok && r.items == 0 && r.pages == 1 && r.last_complete, "book_without_annotations_is_one_empty_complete_page"); }
  { view_guard g; g.v = open_view(C); reader_av_cursor c{}; reader_av_error e{}; reader_av_cursor_start(g.v, 1, &c, &e); reader_av_page p{};
    bool found = false; if (reader_av_page_get(g.v, &c, 100, &p, &e) == READER_AV_OK) for (size_t i = 0; i < p.count; i++) if (p.items[i].exact_size == 65536 && p.items[i].note_size == 65536) found = true;
    reader_av_page more{}; if (!found && reader_av_page_get(g.v, &p.next, 100, &more, &e) == READER_AV_OK) for (size_t i = 0; i < more.count; i++) if (more.items[i].exact_size == 65536 && more.items[i].note_size == 65536) found = true;
    expect(found && p.output_bytes <= READER_AV_PAGE_BYTES_DEFAULT, "largest_legal_fields_roundtrip_within_default_budget", "output=" + num(p.output_bytes));
    reader_av_page_free(&p); reader_av_page_free(&more); }

  /* page byte budget */
  trace("section:page_budget");
  { reader_av_options o{}; o.struct_size = sizeof(o); o.max_page_bytes = READER_AV_PAGE_BYTES_MIN;
    view_guard g; g.v = open_view(C, &o); reader_av_cursor cur{}; reader_av_error e{}; reader_av_cursor_start(g.v, 1, &cur, &e);
    std::vector<std::string> ids; size_t pages = 0, stopped = 0; bool ok = true, bounded = true, nonempty = true;
    for (int guard = 0; guard < 1000; guard++) {
      reader_av_page p{}; if (reader_av_page_get(g.v, &cur, 100, &p, &e) != READER_AV_OK) { ok = false; break; }
      pages++; if (p.budget_stopped) stopped++;
      bounded = bounded && p.output_bytes <= o.max_page_bytes && p.wire_bytes <= o.max_page_bytes;
      nonempty = nonempty && (p.count > 0 || p.complete);
      for (size_t i = 0; i < p.count; i++) ids.push_back(p.items[i].annotation_id);
      bool done = p.complete; cur = p.next; reader_av_page_free(&p); if (done) break;
    }
    expect(ok && stopped > 0 && pages > 3 && bounded && nonempty && ids == ids_of(ref[C]), "page_budget_stops_before_a_row_and_resumes_without_loss", "pages=" + num(pages) + " stopped=" + num(stopped));
    reader_av_options bad[3]; for (auto &b : bad) { std::memset(&b, 0, sizeof b); b.struct_size = sizeof(b); }
    bad[0].max_page_bytes = READER_AV_PAGE_BYTES_MIN - 1; bad[1].max_page_bytes = READER_AV_PAGE_BYTES_MAX + 1; bad[2].struct_size = 1;
    reader_av_view *v = nullptr; bool refused = true; for (auto &b : bad) refused = refused && reader_av_open(store, C.c_str(), &b, &v, &e) == READER_AV_ARGUMENT && v == nullptr;
    expect(refused, "invalid_budget_and_option_size_are_refused"); }

  /* cross-book and cursor refusal */
  trace("section:cross_book");
  { view_guard ga, gb; ga.v = open_view(A); gb.v = open_view(B); reader_av_error e{};
    reader_av_cursor ca{}; reader_av_cursor_start(ga.v, 1, &ca, &e); reader_av_page p{};
    bool refused = reader_av_page_get(gb.v, &ca, 10, &p, &e) == READER_AV_CURSOR && p.items == nullptr && p.count == 0;
    reader_av_cursor flipped = ca; flipped.book_key[5] = flipped.book_key[5] == 'a' ? 'b' : 'a';
    refused = refused && reader_av_page_get(ga.v, &flipped, 10, &p, &e) == READER_AV_CURSOR;
    reader_av_cursor bind = ca; bind.binding ^= 1; refused = refused && reader_av_page_get(ga.v, &bind, 10, &p, &e) == READER_AV_CURSOR;
    reader_av_cursor ver = ca; ver.version = 2; refused = refused && reader_av_page_get(ga.v, &ver, 10, &p, &e) == READER_AV_CURSOR;
    reader_av_cursor dir = ca; dir.direction = 0; refused = refused && reader_av_page_get(ga.v, &dir, 10, &p, &e) == READER_AV_CURSOR;
    reader_av_cursor upper = ca; upper.has_after = 1; std::memset(upper.after_id, 'A', 32); refused = refused && reader_av_page_get(ga.v, &upper, 10, &p, &e) == READER_AV_CURSOR;
    reader_av_cursor stray = ca; stray.after_id[0] = 'a'; refused = refused && reader_av_page_get(ga.v, &stray, 10, &p, &e) == READER_AV_CURSOR;
    expect(refused, "cursor_of_another_book_binding_version_direction_or_shape_is_refused");
    reader_av_cursor foreign = ca; foreign.has_after = 1; std::memcpy(foreign.after_id, ref[B][0].id.c_str(), 32);
    bool only_a = reader_av_page_get(ga.v, &foreign, 100, &p, &e) == READER_AV_OK;
    std::set<std::string> aset(ids_of(ref[A]).begin(), ids_of(ref[A]).end());
    for (size_t i = 0; only_a && i < p.count; i++) only_a = aset.count(p.items[i].annotation_id) == 1 && std::strcmp(p.items[i].annotation_id, foreign.after_id) > 0;
    expect(only_a, "a_foreign_after_id_never_leaks_another_books_rows");
    reader_av_page_free(&p);
    reader_av_view *v = nullptr; std::string badkey = "txt:" + std::string(64, 'z');
    bool bad_open = reader_av_open(store, "txt", nullptr, &v, &e) == READER_AV_ARGUMENT && v == nullptr && reader_av_open(nullptr, A.c_str(), nullptr, &v, &e) == READER_AV_ARGUMENT &&
                    reader_av_open(store, nullptr, nullptr, &v, &e) == READER_AV_ARGUMENT;
    view_guard gz; gz.v = open_view(badkey); reader_av_cursor cz{}; reader_av_cursor_start(gz.v, 1, &cz, &e);
    bool bad_page = reader_av_page_get(gz.v, &cz, 10, &p, &e) == READER_AV_REVISION && e.revision_code != 0 && p.items == nullptr;
    expect(bad_open && bad_page, "invalid_book_keys_are_refused_by_open_or_the_store");
    reader_av_cursor cur{}; reader_av_cursor_start(ga.v, 1, &cur, &e);
    bool args = reader_av_page_get(ga.v, &cur, 0, &p, &e) == READER_AV_ARGUMENT && reader_av_page_get(ga.v, &cur, 101, &p, &e) == READER_AV_ARGUMENT &&
                reader_av_page_get(ga.v, nullptr, 10, &p, &e) == READER_AV_ARGUMENT && reader_av_page_get(ga.v, &cur, 10, nullptr, &e) == READER_AV_ARGUMENT &&
                reader_av_page_get(nullptr, &cur, 10, &p, &e) == READER_AV_ARGUMENT && reader_av_cursor_start(ga.v, 2, &cur, &e) == READER_AV_ARGUMENT &&
                reader_av_close(nullptr, &e) == READER_AV_ARGUMENT;
    expect(args, "limit_direction_and_null_arguments_are_refused"); }

  /* owner thread */
  trace("section:owner_thread");
  { view_guard g; g.v = open_view(A); reader_av_cursor c{}; reader_av_error e{}; reader_av_cursor_start(g.v, 1, &c, &e);
    reader_av_status page_status = READER_AV_OK, close_status = READER_AV_OK; bool empty = false;
    std::thread other([&] {
      reader_av_page p{}; reader_av_error oe{}; page_status = reader_av_page_get(g.v, &c, 5, &p, &oe); empty = p.items == nullptr && p.count == 0;
      reader_av_view *same = g.v; close_status = reader_av_close(&same, &oe); reader_av_page_free(&p);
    });
    other.join();
    reader_av_page p{}; bool usable = reader_av_page_get(g.v, &c, 5, &p, &e) == READER_AV_OK && p.count == 5; reader_av_page_free(&p);
    expect(page_status == READER_AV_OWNER && close_status == READER_AV_OWNER && empty && usable, "another_thread_is_refused_and_the_handle_survives"); }

  /* cancellation at every poll point */
  trace("section:cancel");
  { canceler k; view_guard g; reader_av_options o{}; o.struct_size = sizeof(o); o.cancel = cancel_cb; o.cancel_context = &k; g.v = open_view(A, &o);
    reader_av_error e{}; reader_av_cursor c{}; reader_av_cursor_start(g.v, 1, &c, &e); reader_av_page base{};
    bool ok = reader_av_page_get(g.v, &c, 100, &base, &e) == READER_AV_OK; const std::string want = page_digest(base); const uint64_t total = base.polls;
    expect(ok && total > 100 && k.calls == total, "poll_count_is_reported_and_exact", "polls=" + num(total) + " calls=" + num(k.calls));
    size_t cancelled = 0, clean = 0, retried = 0, exact_calls = 0;
    for (uint64_t at = 1; at <= total; at++) {
      trace("cancel:at=" + std::to_string(at) + "/" + std::to_string(total));
      k.calls = 0; k.at = at; reader_av_page p{}; reader_av_cursor before = c;
      reader_av_status st = reader_av_page_get(g.v, &c, 100, &p, &e);
      if (st == READER_AV_CANCELLED) cancelled++;
      if (p.items == nullptr && p.count == 0 && std::memcmp(&before, &c, sizeof c) == 0) clean++;
      if (k.calls == at) exact_calls++;
      k.at = 0; reader_av_page again{}; if (reader_av_page_get(g.v, &c, 100, &again, &e) == READER_AV_OK && page_digest(again) == want) retried++;
      reader_av_page_free(&again); reader_av_page_free(&p);
    }
    expect(cancelled == total && clean == total && exact_calls == total && retried == total, "cancel_at_every_poll_point_discards_the_page_and_retry_is_identical", "points=" + num(total) + " cancelled=" + num(cancelled));
    k.calls = 0; k.at = total + 1; reader_av_page past{}; expect(reader_av_page_get(g.v, &c, 100, &past, &e) == READER_AV_OK && page_digest(past) == want, "cancel_after_the_last_poll_changes_nothing");
    reader_av_page_free(&past); reader_av_page_free(&base);
    /* the descending and budget-stopped paths poll too */
    k.at = 0; k.calls = 0; reader_av_cursor d{}; reader_av_cursor_start(g.v, -1, &d, &e); reader_av_page down{};
    expect(reader_av_page_get(g.v, &d, 100, &down, &e) == READER_AV_OK && down.polls == k.calls && down.polls > 100, "descending_page_polls_the_same_way");
    reader_av_page_free(&down); }

  /* reentry */
  trace("section:reentry");
  { canceler k; k.mode = 1; view_guard g; reader_av_options o{}; o.struct_size = sizeof(o); o.cancel = cancel_cb; o.cancel_context = &k; g.v = open_view(A, &o); k.view = &g.v;
    reader_av_error e{}; reader_av_cursor c{}; reader_av_cursor_start(g.v, 1, &c, &e); reader_av_page p{};
    bool ok = reader_av_page_get(g.v, &c, 100, &p, &e) == READER_AV_OK && p.count == 100;
    expect(ok && k.busy_page == p.polls && k.busy_close == p.polls && k.start_ok == p.polls && g.v != nullptr, "reentrant_page_and_close_from_the_cancel_callback_are_busy_and_change_nothing",
           "polls=" + num(p.polls) + " busy_page=" + num(k.busy_page) + " busy_close=" + num(k.busy_close));
    reader_av_page_free(&p);
    reader_av_page q{}; expect(reader_av_page_get(g.v, &c, 5, &q, &e) == READER_AV_OK && q.count == 5, "view_is_usable_after_refused_reentry"); reader_av_page_free(&q); }

  /* product history, outbox, database and SDK progress/notes are unchanged */
  trace("section:capture_after");
  const std::string product_after = product_dump(db_path), sdk_after = sdk_dump(lib, sdk_book, lib_path);
  expect(product_after == product_before, "product_history_outbox_and_database_unchanged_after_all_reads", "digest=" + hex64(fnv(product_after)) + " bytes=" + num(product_after.size()));
  expect(sdk_after == sdk_before && sdk_before.find("N:") != std::string::npos && sdk_before.find("P:") != std::string::npos, "sdk_progress_notes_and_library_file_unchanged_after_all_reads",
         "digest=" + hex64(fnv(sdk_after)) + " bytes=" + num(sdk_after.size()));

  /* concurrent insert and tombstone between pages */
  trace("section:concurrency");
  { view_guard g; g.v = open_view(A); reader_av_error e{}; reader_av_cursor c{}; reader_av_cursor_start(g.v, 1, &c, &e); reader_av_page p1{};
    bool got = reader_av_page_get(g.v, &c, 100, &p1, &e) == READER_AV_OK && p1.count == 100;
    std::vector<std::string> first; for (size_t i = 0; got && i < p1.count; i++) first.push_back(p1.items[i].annotation_id);
    const std::string last = first.back(); reader_av_cursor next = p1.next;
    std::string low, high;
    for (uint64_t k = 0; k < 4000 && low.empty(); k++) { std::string id = mkid('n', k); if (id < last) low = id; }
    high = mkid('n', 90000); while (high < last) high = mkid('n', 90001 + rev_counter++);
    /* shown id tombstoned, a later SAFE note tombstoned, one insert before and one after the cursor */
    std::string victim_shown, victim_later;
    for (auto &r : ref[A]) { const truth_item &t = truth[A][r.id];
      if (t.state == READER_AV_STATE_SAFE && t.kind == READER_AV_KIND_NOTE) { if (r.id <= last && victim_shown.empty()) victim_shown = r.id; if (r.id > last && victim_later.empty()) victim_later = r.id; } }
    bool setup = got && !low.empty() && !victim_shown.empty() && !victim_later.empty();
    if (setup) {
      for (const std::string &id : {victim_shown, victim_later}) { spec d = mk(A, id, "reflow_global"); d.op = "delete"; d.parents = {truth[A][id].head.rev}; submit(d); reg(d, READER_AV_STATE_SAFE, truth[A][id].revisions + 1, 1); }
      for (const std::string &id : {low, high}) { spec s = mk(A, id, "reflow_global"); quote(s, "inserted " + id.substr(0, 4), 7); s.text = "inserted"; submit(s); reg(s, READER_AV_STATE_SAFE, 1, 1); }
    }
    std::vector<refrow> ref2 = ref_scan(A, 1, 100); ref[A] = ref2; g_book_a_final = ref2.size();
    std::vector<refrow> tail; for (auto &r : ref2) if (r.id > last) tail.push_back(r);
    std::vector<std::string> rest; bool ok = setup; reader_av_cursor cur = next; std::string err;
    for (int guard = 0; ok && guard < 1000; guard++) {
      reader_av_page p{}; if (reader_av_page_get(g.v, &cur, 100, &p, &e) != READER_AV_OK) { ok = false; break; }
      for (size_t i = 0; i < p.count; i++) {
        size_t at = rest.size(); rest.push_back(p.items[i].annotation_id);
        if (at < tail.size()) { std::string m = item_error(p.items[i], tail[at], truth[A][p.items[i].annotation_id]); if (!m.empty() && err.empty()) err = m; }
      }
      bool done = p.complete; cur = p.next; reader_av_page_free(&p); if (done) break;
    }
    std::set<std::string> shown(first.begin(), first.end()); bool dup = false; for (auto &id : rest) if (shown.count(id)) dup = true;
    expect(ok && setup && !dup && rest == ids_of(tail) && err.empty() && std::find(rest.begin(), rest.end(), low) == rest.end() && std::find(rest.begin(), rest.end(), high) != rest.end(),
           "concurrent_insert_and_tombstone_between_pages_has_no_duplicate_or_gap", "rest=" + num(rest.size()) + " tail=" + num(tail.size()) + " " + err);
    if (setup) { reader_av_cursor c2{}; reader_av_cursor_start(g.v, 1, &c2, &e); reader_av_page lp{};
      bool tomb = false; reader_av_cursor cc = c2;
      for (int guard = 0; guard < 1000; guard++) { reader_av_page p{}; if (reader_av_page_get(g.v, &cc, 100, &p, &e) != READER_AV_OK) break;
        for (size_t i = 0; i < p.count; i++) if (victim_later == p.items[i].annotation_id && p.items[i].kind == READER_AV_KIND_TOMBSTONE && p.items[i].state == READER_AV_STATE_SAFE && !p.items[i].exact && !p.items[i].note_text) tomb = true;
        bool done = p.complete; cc = p.next; reader_av_page_free(&p); if (done) break; }
      expect(tomb, "tombstone_is_shown_as_safe_deletion_without_a_body"); reader_av_page_free(&lp);
      scan_result full = scan(g.v, A, 1, 100, &ref[A]); expect(full.ok && full.bad_items == 0 && full.ids == ids_of(ref[A]) && full.ids.size() == A_COUNT + 2, "rescan_after_mutation_equals_new_direct_scan", full.error); }
    reader_av_page_free(&p1); }

  /* snapshot lifetime: close view, store and SDK, then read the page */
  trace("section:lifetime");
  { reader_revisions *store2 = nullptr; reader_revision_error r2{};
    if (reader_revisions_open(db_path.c_str(), &store2, &r2) != READER_REV_OK) fatal(std::string("second store: ") + r2.message);
    reader_av_view *v = nullptr; reader_av_error e{}; reader_av_open(store2, A.c_str(), nullptr, &v, &e);
    reader_av_cursor c{}; reader_av_cursor_start(v, 1, &c, &e); reader_av_page p{};
    bool got = reader_av_page_get(v, &c, 100, &p, &e) == READER_AV_OK && p.count == 100; const std::string before = got ? page_digest(p) : "";
    reader_av_close(&v, &e); reader_revisions_close(&store2, &r2); exr_library_close(lib); lib = nullptr;
    std::string after = got ? page_digest(p) : "~";
    expect(got && v == nullptr && store2 == nullptr && before == after && before.size() > 10000, "page_is_readable_after_view_store_and_sdk_are_closed", "digest=" + hex64(fnv(after)));
    reader_av_page_free(&p); }

  reader_revision_error ce{}; reader_revisions_close(&store, &ce);
  trace("main:done");
  write_report(true);
  std::printf("checks=%zu failed=%zu\n", checks.size(), failures); std::fflush(stdout);
  return failures ? 1 : 0;
}
