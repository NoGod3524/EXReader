/* SPDX-License-Identifier: MIT */
/* Installed C++ consumer of EXReaderNavigation. Expectations come from the fixture
   generator's hand-written TSV lists and from independent scans of a second, separately
   opened SDK object, never from the module's own paths. Cloud only. */
#include <reader_navigation.h>
#include <exr/core.h>
#include <exr/formats.h>
#include <exr/pdf.h>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <functional>
#include <map>
#include <sstream>
#include <string>
#include <vector>

namespace {
const uint64_t NONE = READER_NAVIGATION_NONE;
exr_error g_se;
struct check_record { std::string name; bool pass; };
std::vector<check_record> g_checks;
int g_failures = 0;
void check(const std::string &name, bool ok) {
  g_checks.push_back({name, ok});
  if (!ok) { g_failures++; std::fprintf(stderr, "FAIL: %s\n", name.c_str()); }
}
void sdk(exr_status s, const char *what) {
  if (s != EXR_OK) { std::fprintf(stderr, "SDK failure in %s: %d %s\n", what, (int)s, g_se.message); std::exit(2); }
}
std::string hexs(const std::string &s) {
  static const char *d = "0123456789abcdef"; std::string o;
  for (unsigned char c : s) { o.push_back(d[c >> 4]); o.push_back(d[c & 15]); }
  return o;
}
uint64_t fnv(uint64_t h, const std::string &s) {
  for (unsigned char c : s) { h ^= c; h *= 1099511628211ull; }
  h ^= 0xff; h *= 1099511628211ull; return h;
}
std::vector<unsigned char> slurp(const std::string &path) {
  std::ifstream f(path, std::ios::binary);
  if (!f) { std::fprintf(stderr, "cannot read %s\n", path.c_str()); std::exit(2); }
  return std::vector<unsigned char>((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());
}
uint64_t hash_bytes(const std::vector<unsigned char> &v) {
  uint64_t h = 14695981039346656037ull;
  for (unsigned char c : v) { h ^= c; h *= 1099511628211ull; }
  return h;
}
const char *outcome_name(reader_navigation_status s) {
  switch (s) {
    case READER_NAVIGATION_OK: return "ok";
    case READER_NAVIGATION_PART_ONLY: return "part_only";
    case READER_NAVIGATION_NEEDS_HOST: return "needs_host";
    case READER_NAVIGATION_UNRESOLVED: return "unresolved";
    case READER_NAVIGATION_RANGE: return "range";
    case READER_NAVIGATION_AMBIGUOUS: return "ambiguous";
    default: return "other";
  }
}

struct row_copy {
  uint64_t index, parent, part; uint32_t depth, child_count, target_class;
  std::string label, href, base, role, part_path, part_id;
};
struct tgt {
  reader_navigation_target t;
  tgt() { std::memset(&t, 0, sizeof(t)); }
  ~tgt() { reader_navigation_target_free(&t); }
};
reader_navigation_resolve_options ropt(uint64_t explicit_part = NONE, const exr_control *c = nullptr) {
  reader_navigation_resolve_options o; std::memset(&o, 0, sizeof(o));
  o.struct_size = sizeof(o); o.explicit_part = explicit_part; if (c) o.control = *c; return o;
}
reader_navigation_options nopt(uint32_t nodes = 0, uint32_t depth = 0, uint64_t text = 0, const exr_control *c = nullptr) {
  reader_navigation_options o; std::memset(&o, 0, sizeof(o));
  o.struct_size = sizeof(o); o.max_nodes = nodes; o.max_depth = depth; o.max_text_bytes = text; if (c) o.control = *c; return o;
}
std::vector<row_copy> copy_page(const reader_navigation_page &p) {
  std::vector<row_copy> v;
  for (size_t i = 0; i < p.count; i++) {
    const reader_navigation_row &r = p.rows[i];
    v.push_back({r.index, r.parent, r.part, r.depth, r.child_count, r.target_class, r.label, r.href, r.base, r.role, r.part_path, r.part_id});
  }
  return v;
}
/* Pages through the whole snapshot and checks the paging contract on the way. */
std::vector<row_copy> all_rows(reader_navigation *n, size_t step, bool *contract) {
  std::vector<row_copy> all; uint64_t first = 0; bool ok = true;
  for (;;) {
    reader_navigation_page p; reader_navigation_error e;
    if (reader_navigation_rows(n, first, step, &p, &e) != READER_NAVIGATION_OK) { ok = false; break; }
    if (p.count > step || p.count > READER_NAVIGATION_PAGE_MAX) ok = false;
    if (p.count == 0 && first != p.total) ok = false;
    for (const row_copy &r : copy_page(p)) all.push_back(r);
    uint64_t next = p.next, total = p.total; size_t count = p.count;
    reader_navigation_page_free(&p);
    if (next == NONE) { if (first + count != total) ok = false; break; }
    if (next != first + count) { ok = false; break; }
    first = next;
  }
  if (contract) *contract = ok;
  return all;
}
std::string digest_rows(const std::vector<row_copy> &rows) {
  uint64_t h = 14695981039346656037ull;
  for (const row_copy &r : rows) {
    h = fnv(h, std::to_string(r.index) + "/" + std::to_string(r.parent) + "/" + std::to_string(r.part) + "/" + std::to_string(r.depth) +
               "/" + std::to_string(r.child_count) + "/" + std::to_string(r.target_class));
    h = fnv(h, r.label); h = fnv(h, r.href); h = fnv(h, r.base); h = fnv(h, r.role); h = fnv(h, r.part_path); h = fnv(h, r.part_id);
  }
  char b[32]; std::snprintf(b, sizeof(b), "%016llx", (unsigned long long)h); return b;
}

exr_publication *open_pub(const std::string &path) {
  exr_publication *p = nullptr; sdk(exr_publication_open(path.c_str(), &p, &g_se), "publication_open"); return p;
}
std::vector<std::string> part_paths(exr_publication *p) {
  size_t n = 0; const exr_part *parts = exr_publication_parts(p, &n); std::vector<std::string> v;
  for (size_t i = 0; i < n; i++) v.push_back(parts[i].path);
  return v;
}
bool node_has_id(exr_publication *p, size_t part, uint64_t node, const std::string &id) {
  exr_document *d = nullptr;
  if (exr_publication_load(p, part, &d, &g_se) != EXR_OK) return false;
  size_t n = 0; const exr_node *nodes = exr_document_nodes(d, &n);
  const char *v = node < n ? exr_node_attribute(&nodes[node], "id") : nullptr;
  bool ok = v && id == v; exr_document_free(d); return ok;
}
bool doc_node_has_id(const exr_document *d, uint64_t node, const std::string &id) {
  size_t n = 0; const exr_node *nodes = exr_document_nodes(d, &n);
  const char *v = node < n ? exr_node_attribute(&nodes[node], "id") : nullptr;
  return v && id == v;
}
std::string fragment_of(const std::string &href) {
  size_t h = href.find('#'); return h == std::string::npos ? "" : href.substr(h + 1);
}

struct expect_row { uint64_t index; int64_t parent; std::string role, label, href, part, outcome, base; };
std::vector<expect_row> read_tsv(const std::string &path) {
  std::ifstream f(path, std::ios::binary); std::string line; std::vector<expect_row> v;
  while (std::getline(f, line)) {
    if (line.empty()) continue;
    std::vector<std::string> c; std::stringstream ss(line); std::string cell;
    while (std::getline(ss, cell, '\t')) c.push_back(cell);
    while (c.size() < 8) c.push_back("");
    v.push_back({(uint64_t)std::stoull(c[0]), std::stoll(c[1]), c[2], c[3], c[4], c[5], c[6], c[7]});
  }
  return v;
}

struct case_report {
  std::string id; size_t rows = 0, roots = 0, depth_levels = 0, text_bytes = 0;
  size_t ok = 0, part_only = 0, needs_host = 0, unresolved = 0, range = 0, ambiguous = 0, other = 0, mislocated = 0;
  std::string digest;
};
std::vector<case_report> g_cases;

/* ---------- one real EPUB: snapshot, TSV oracle, second-object confirmation ---------- */
void epub_case(const std::string &id, const std::string &dir, const std::string &file, const std::string &tsv) {
  const std::string path = dir + "/" + file;
  uint64_t before = hash_bytes(slurp(path));
  std::vector<expect_row> want = read_tsv(dir + "/" + tsv);
  exr_publication *a = open_pub(path), *b = open_pub(path); /* b: independent second object */
  reader_navigation *nav = nullptr; reader_navigation_error e;
  check(id + ": snapshot opens", reader_navigation_open_publication(a, nullptr, &nav, &e) == READER_NAVIGATION_OK && nav);
  if (!nav) std::exit(2);
  reader_navigation_info info; reader_navigation_info_get(nav, &info, &e);
  size_t pc = 0; exr_publication_parts(a, &pc);
  check(id + ": info is authored and counts the spine", info.kind == READER_NAVIGATION_AUTHORED && info.part_count == pc &&
        info.source == READER_NAVIGATION_FROM_PUBLICATION && info.author_outline == 1 && info.node_count == want.size());
  bool contract = false; std::vector<row_copy> rows = all_rows(nav, 100, &contract);
  check(id + ": paging contract holds with 100 rows", contract && rows.size() == want.size());
  bool c5 = false; std::vector<row_copy> rows5 = all_rows(nav, 5, &c5);
  check(id + ": 5-row paging equals 100-row paging", c5 && digest_rows(rows) == digest_rows(rows5));
  /* Verbatim against the SDK's own borrowed entries. */
  const exr_navigation *raw = nullptr; size_t rn = 0;
  sdk(exr_publication_navigation(a, &raw, &rn, &g_se), "navigation");
  bool same = rn == rows.size(), distinct = true;
  for (size_t i = 0; same && i < rn; i++) {
    const row_copy &r = rows[i];
    same = r.label == raw[i].label && r.href == raw[i].href && r.base == raw[i].base && r.role == raw[i].role &&
           r.parent == (raw[i].parent == SIZE_MAX ? NONE : raw[i].parent) && r.part == (raw[i].part == SIZE_MAX ? NONE : raw[i].part) && r.index == i;
  }
  check(id + ": rows equal the SDK's entries in order, parent, label, href, base, role and part", same);
  reader_navigation_page pg; reader_navigation_rows(nav, 0, 100, &pg, &e);
  for (size_t i = 0; i < pg.count && i < rn; i++)
    if (pg.rows[i].label == raw[i].label || pg.rows[i].href == raw[i].href || pg.rows[i].role == raw[i].role) distinct = false;
  reader_navigation_page_free(&pg);
  check(id + ": row strings are copies, not SDK pointers", distinct);
  case_report rep; rep.id = id; rep.rows = rows.size(); rep.roots = info.root_count; rep.depth_levels = info.depth_levels;
  rep.text_bytes = info.text_bytes; rep.digest = digest_rows(rows);
  bool oracle = rows.size() == want.size();
  for (size_t i = 0; oracle && i < want.size(); i++) {
    const row_copy &r = rows[i]; const expect_row &w = want[i];
    bool resolved = w.outcome == "ok" || w.outcome == "part_only";
    bool good = r.label == w.label && r.href == w.href && r.role == w.role && r.base == w.base &&
                r.parent == (w.parent < 0 ? NONE : (uint64_t)w.parent) && (r.part != NONE) == resolved &&
                (!resolved || r.part_path == w.part);
    if (!good) std::fprintf(stderr, "oracle mismatch %s row %zu: label=[%s] href=[%s] role=[%s] part=%llu path=[%s]\n", id.c_str(), i,
                            r.label.c_str(), r.href.c_str(), r.role.c_str(), (unsigned long long)r.part, r.part_path.c_str());
    oracle = oracle && good;
  }
  check(id + ": every row matches the hand-written expectation list", oracle);
  /* Resolve on the object the snapshot came from and on the second one. */
  std::vector<std::string> bpaths = part_paths(b);
  bool outcomes = true, nodes_ok = true, ids_ok = true, same_ab = true, amb_ok = true;
  for (size_t i = 0; i < want.size() && i < rows.size(); i++) {
    tgt ta, tb; reader_navigation_error ea, eb;
    reader_navigation_status sa = reader_navigation_resolve_publication(nav, i, a, nullptr, &ta.t, &ea);
    reader_navigation_status sb = reader_navigation_resolve_publication(nav, i, b, nullptr, &tb.t, &eb);
    std::string got = outcome_name(sa);
    if (got != want[i].outcome || sb != sa) {
      outcomes = false; rep.other++;
      std::fprintf(stderr, "outcome mismatch %s row %zu: want %s got %s (%d %s)\n", id.c_str(), i, want[i].outcome.c_str(), got.c_str(), (int)sa, ea.message);
    } else if (got == "ok") rep.ok++; else if (got == "part_only") rep.part_only++; else if (got == "needs_host") rep.needs_host++;
    else if (got == "unresolved") rep.unresolved++; else if (got == "range") rep.range++; else if (got == "ambiguous") rep.ambiguous++;
    std::string frag = fragment_of(rows[i].href);
    if (sa == READER_NAVIGATION_OK || sa == READER_NAVIGATION_PART_ONLY) {
      bool located = ta.t.kind == READER_NAVIGATION_RESULT_SPINE && ta.t.part < bpaths.size() && ta.t.part_path &&
                     bpaths[(size_t)ta.t.part] == ta.t.part_path && want[i].part == ta.t.part_path && ta.t.part_id &&
                     tb.t.part == ta.t.part && tb.t.node == ta.t.node && tb.t.row == i;
      if (!located) { rep.mislocated++; same_ab = false; }
      if (!frag.empty() && sa == READER_NAVIGATION_OK) {
        if (ta.t.node == NONE || !ta.t.fragment || frag != ta.t.fragment) nodes_ok = false;
        else if (!node_has_id(b, (size_t)ta.t.part, ta.t.node, frag)) ids_ok = false;
      }
      if (sa == READER_NAVIGATION_PART_ONLY && ta.t.node != NONE) nodes_ok = false;
      if (frag.empty() && ta.t.node != NONE) nodes_ok = false;
    } else if (ta.t.kind != 0 && sa != READER_NAVIGATION_AMBIGUOUS) {
      outcomes = false;
    }
    if (sa == READER_NAVIGATION_AMBIGUOUS) {
      std::vector<uint64_t> cand;
      for (size_t k = 0; k < bpaths.size(); k++) if (bpaths[k] == want[i].part) cand.push_back(k);
      bool list = ta.t.part == NONE && ta.t.candidate_count == cand.size() && cand.size() >= 2;
      for (size_t k = 0; list && k < cand.size(); k++) list = ta.t.candidates[k] == cand[k];
      for (size_t k = 0; list && k < cand.size(); k++) {
        tgt te; reader_navigation_error ee;
        reader_navigation_status se = reader_navigation_resolve_publication(nav, i, b, nullptr, &te.t, &ee);
        (void)se;
        reader_navigation_resolve_options o = ropt(cand[k]);
        reader_navigation_status s2 = reader_navigation_resolve_publication(nav, i, b, &o, &te.t, &ee);
        std::string f2 = fragment_of(rows[i].href);
        list = s2 == READER_NAVIGATION_OK && te.t.part == cand[k] && te.t.part_path && want[i].part == te.t.part_path &&
               (f2.empty() || (te.t.node != NONE && node_has_id(b, (size_t)cand[k], te.t.node, f2)));
      }
      /* A part with a different path, or an index beyond the book, is refused. */
      uint64_t other = NONE;
      for (size_t k = 0; k < bpaths.size(); k++) if (bpaths[k] != want[i].part) { other = k; break; }
      tgt tm; reader_navigation_error em;
      reader_navigation_resolve_options om = ropt(other), orange = ropt(bpaths.size() + 5);
      list = list && other != NONE && reader_navigation_resolve_publication(nav, i, b, &om, &tm.t, &em) == READER_NAVIGATION_MISMATCH && tm.t.kind == 0;
      list = list && reader_navigation_resolve_publication(nav, i, b, &orange, &tm.t, &em) == READER_NAVIGATION_RANGE;
      amb_ok = amb_ok && list;
    }
  }
  check(id + ": every row resolves to its expected outcome on both SDK objects", outcomes);
  check(id + ": resolved targets name the same spine index and path on the second object", same_ab);
  check(id + ": fragment targets carry the node and part-only never carries one", nodes_ok);
  check(id + ": the fragment node's id is confirmed on the second independent SDK object", ids_ok);
  if (rep.ambiguous) check(id + ": repeated spine paths list every candidate and only an explicit matching part resolves", amb_ok);
  /* Hierarchy queries agree with parent fields. */
  bool tree = true;
  for (size_t i = 0; i < rows.size(); i++) {
    reader_navigation_page cp; uint64_t first = 0; std::vector<uint64_t> got;
    for (;;) {
      if (reader_navigation_children(nav, i, first, 2, &cp, &e) != READER_NAVIGATION_OK) { tree = false; break; }
      for (size_t k = 0; k < cp.count; k++) got.push_back(cp.rows[k].index);
      uint64_t next = cp.next; reader_navigation_page_free(&cp); if (next == NONE) break; first = next;
    }
    std::vector<uint64_t> expect;
    for (const row_copy &r : rows) if (r.parent == i) expect.push_back(r.index);
    if (got != expect || expect.size() != rows[i].child_count) tree = false;
  }
  { reader_navigation_page cp; std::vector<uint64_t> roots;
    tree = tree && reader_navigation_children(nav, NONE, 0, 100, &cp, &e) == READER_NAVIGATION_OK;
    for (size_t k = 0; k < cp.count; k++) roots.push_back(cp.rows[k].index);
    size_t expected_roots = 0; for (const row_copy &r : rows) if (r.parent == NONE) expected_roots++;
    tree = tree && roots.size() == expected_roots && cp.total == expected_roots; reader_navigation_page_free(&cp);
    tree = tree && reader_navigation_children(nav, rows.size(), 0, 1, &cp, &e) == READER_NAVIGATION_RANGE && !cp.rows; }
  check(id + ": children queries equal the original parent links", tree);
  /* The same snapshot is wrong for another book. */
  {
    /* Same paths and ids would be the same book, so pick one with a different spine. */
    exr_publication *other = open_pub(dir + (file == "repeated.epub" ? "/nav3.epub" : "/repeated.epub"));
    tgt t; reader_navigation_error ee;
    check(id + ": a different book is refused with MISMATCH", rows.empty() ||
          reader_navigation_resolve_publication(nav, 0, other, nullptr, &t.t, &ee) == READER_NAVIGATION_MISMATCH);
    exr_publication_free(other);
  }
  /* Document source gives the same rows and resolves on the document's own nodes. */
  {
    exr_document *doc = nullptr; sdk(exr_document_open(path.c_str(), &doc, &g_se), "document_open");
    reader_navigation *dn = nullptr;
    check(id + ": document snapshot opens", reader_navigation_open_document(doc, nullptr, &dn, &e) == READER_NAVIGATION_OK && dn);
    bool equal = false, resolved = true;
    if (dn) {
      std::vector<row_copy> drows = all_rows(dn, 100, nullptr);
      equal = drows.size() == rows.size();
      for (size_t i = 0; equal && i < rows.size(); i++)
        equal = drows[i].label == rows[i].label && drows[i].href == rows[i].href && drows[i].base == rows[i].base &&
                drows[i].role == rows[i].role && drows[i].parent == rows[i].parent && drows[i].part == rows[i].part &&
                drows[i].target_class == rows[i].target_class;
      for (size_t i = 0; i < drows.size() && i < want.size(); i++) {
        tgt t; reader_navigation_error ee;
        reader_navigation_status s = reader_navigation_resolve_document(dn, i, doc, nullptr, &t.t, &ee);
        std::string frag = fragment_of(rows[i].href);
        if (outcome_name(s) != want[i].outcome) resolved = false;
        if (s == READER_NAVIGATION_OK && !frag.empty() && (t.t.node == NONE || !doc_node_has_id(doc, t.t.node, frag))) resolved = false;
        if (s == READER_NAVIGATION_OK && t.t.kind != READER_NAVIGATION_RESULT_CHAPTER) resolved = false;
      }
      reader_navigation_close(&dn, &e);
    }
    check(id + ": document rows equal publication rows", equal);
    check(id + ": document targets resolve to the same outcomes with confirmed nodes", resolved);
    exr_document_free(doc);
  }
  /* The snapshot outlives the SDK object it was taken from. */
  exr_publication_free(a);
  bool alive = digest_rows(all_rows(nav, 7, nullptr)) == rep.digest;
  check(id + ": snapshot rows are unchanged after the publication is freed", alive);
  reader_navigation_close(&nav, &e); exr_publication_free(b);
  check(id + ": the original file bytes are unchanged", hash_bytes(slurp(path)) == before);
  g_cases.push_back(rep);
}

/* ---------- custom publications ---------- */
struct custom_book {
  std::vector<std::string> paths, ids, labels, hrefs, bases, roles; std::vector<exr_part> parts; std::vector<exr_navigation> nav;
  std::vector<size_t> parents, partsel; exr_publication *pub = nullptr;
};
exr_status custom_load(void *context, size_t part, exr_document **out, exr_error *e) {
  const custom_book &book = *(const custom_book *)context;
  const exr_node_input nodes[] = {
    {EXR_NODE_DOCUMENT, SIZE_MAX, "document", nullptr, nullptr, 0},
    {EXR_NODE_CHAPTER, 0, "chapter", nullptr, nullptr, 0},
    {EXR_NODE_PARAGRAPH, 1, "p", nullptr, nullptr, 0},
    {EXR_NODE_TEXT, 2, nullptr, "A", nullptr, 0}
  };
  const exr_chapter_input chapter = {book.ids[part].c_str(), book.paths[part].c_str(), 1, 1};
  exr_document_input input{};
  input.title = "custom chapter"; input.nodes = nodes; input.node_count = 4;
  input.chapters = &chapter; input.chapter_count = 1;
  return exr_document_create(&input, out, e);
}
void build(custom_book &b) {
  b.parts.clear(); b.nav.clear();
  for (size_t i = 0; i < b.paths.size(); i++) b.parts.push_back({b.ids[i].c_str(), b.paths[i].c_str(), "", 1});
  for (size_t i = 0; i < b.labels.size(); i++)
    b.nav.push_back({b.parents[i], b.partsel[i], b.labels[i].c_str(), b.hrefs[i].c_str(), b.bases[i].c_str(), b.roles[i].c_str()});
  exr_publication_input in; std::memset(&in, 0, sizeof(in));
  in.title = "custom"; in.parts = b.parts.data(); in.part_count = b.parts.size(); in.load = custom_load; in.context = &b;
  in.navigation = b.nav.empty() ? nullptr : b.nav.data(); in.navigation_count = b.nav.size();
  sdk(exr_publication_create(&in, &b.pub, &g_se), "publication_create");
}
void add(custom_book &b, size_t parent, size_t part, const std::string &label, const std::string &href, const std::string &base = "Nav/nav.xhtml") {
  b.parents.push_back(parent); b.partsel.push_back(part); b.labels.push_back(label); b.hrefs.push_back(href); b.bases.push_back(base); b.roles.push_back("toc");
}
reader_navigation_status resolve_custom(reader_navigation *n, uint64_t row, custom_book &b, uint64_t ex, tgt &t, reader_navigation_error &e) {
  reader_navigation_resolve_options o = ropt(ex);
  return reader_navigation_resolve_publication(n, row, b.pub, &o, &t.t, &e);
}
void custom_cases() {
  const std::string a_umlaut = "Text/\xc3\xa4.xhtml";
  custom_book b;
  b.paths = {"Text/a.xhtml", a_umlaut, a_umlaut, "x.xhtml"}; b.ids = {"p0", "p1", "p2", "p3"};
  add(b, SIZE_MAX, SIZE_MAX, "dup", "../Text/%C3%A4.xhtml");                         /* 0 */
  add(b, SIZE_MAX, SIZE_MAX, "dup frag", "../Text/%C3%A4.xhtml#x");                  /* 1 */
  add(b, SIZE_MAX, 0, "sdk part", "../Text/a.xhtml");                                /* 2 */
  add(b, SIZE_MAX, SIZE_MAX, "https", "https://example.test/a");                     /* 3 */
  add(b, SIZE_MAX, SIZE_MAX, "mailto", "mailto:a@example.test");                     /* 4 */
  add(b, SIZE_MAX, SIZE_MAX, "network", "//host/p.xhtml");                           /* 5 */
  add(b, SIZE_MAX, SIZE_MAX, "upper scheme", "HTTP://EXAMPLE.TEST/");                /* 6 */
  add(b, SIZE_MAX, SIZE_MAX, "no href", "");                                         /* 7 */
  add(b, SIZE_MAX, SIZE_MAX, "above root", "../../x.xhtml");                         /* 8 */
  add(b, SIZE_MAX, SIZE_MAX, "absolute", "/abs.xhtml");                              /* 9 */
  add(b, SIZE_MAX, SIZE_MAX, "backslash", "a\\b.xhtml");                             /* 10 */
  add(b, SIZE_MAX, SIZE_MAX, "single match, SDK none", "../x.xhtml");                /* 11 */
  add(b, SIZE_MAX, SIZE_MAX, "bad escape", "%zz.xhtml");                             /* 12 */
  add(b, SIZE_MAX, SIZE_MAX, "missing", "../Text/none.xhtml");                       /* 13 */
  build(b);
  {
    exr_document *chapter = nullptr;
    sdk(exr_publication_load(b.pub, 1, &chapter, &g_se), "custom chapter load");
    size_t resource = SIZE_MAX, node = SIZE_MAX;
    check("custom: the independent SDK fixture has a chapter and reports a missing fragment",
      exr_document_resolve(chapter, 0, "#x", &resource, &node, &g_se) == EXR_OK && node == SIZE_MAX);
    exr_document_free(chapter);
  }
  reader_navigation *n = nullptr; reader_navigation_error e;
  check("custom: snapshot opens", reader_navigation_open_publication(b.pub, nullptr, &n, &e) == READER_NAVIGATION_OK && n);
  tgt t;
  check("custom: a path repeated in the spine is AMBIGUOUS and never the first match",
        reader_navigation_resolve_publication(n, 0, b.pub, nullptr, &t.t, &e) == READER_NAVIGATION_AMBIGUOUS && t.t.part == NONE &&
        t.t.candidate_count == 2 && t.t.candidates[0] == 1 && t.t.candidates[1] == 2);
  { tgt t2; check("custom: explicit spine index 2 resolves the second repeated item with its verbatim path",
        resolve_custom(n, 0, b, 2, t2, e) == READER_NAVIGATION_OK && t2.t.part == 2 && a_umlaut == t2.t.part_path && std::string(t2.t.part_id) == "p2" && t2.t.node == NONE); }
  { tgt t2; check("custom: explicit spine index 1 resolves the first repeated item", resolve_custom(n, 0, b, 1, t2, e) == READER_NAVIGATION_OK && t2.t.part == 1); }
  { tgt t2; check("custom: explicit index of another path is MISMATCH", resolve_custom(n, 0, b, 0, t2, e) == READER_NAVIGATION_MISMATCH && t2.t.kind == 0); }
  { tgt t2; check("custom: explicit index beyond the book is RANGE", resolve_custom(n, 0, b, 99, t2, e) == READER_NAVIGATION_RANGE); }
  { tgt t2; check("custom: a missing fragment keeps the part and no node (PART_ONLY)",
        resolve_custom(n, 1, b, 1, t2, e) == READER_NAVIGATION_PART_ONLY && t2.t.part == 1 && t2.t.node == NONE && t2.t.fragment && std::string(t2.t.fragment) == "x"); }
  { tgt t2; check("custom: an SDK-resolved part rejects a different explicit index", resolve_custom(n, 2, b, 1, t2, e) == READER_NAVIGATION_MISMATCH);
    tgt t3; check("custom: an SDK-resolved part accepts its own explicit index", resolve_custom(n, 2, b, 0, t3, e) == READER_NAVIGATION_OK && t3.t.part == 0); }
  for (uint64_t r : {3, 4, 5, 6}) { tgt t2; check("custom: external row " + std::to_string(r) + " is NEEDS_HOST even with an explicit index",
        resolve_custom(n, r, b, 1, t2, e) == READER_NAVIGATION_NEEDS_HOST && t2.t.kind == 0); }
  { tgt t2; check("custom: a row without href is UNRESOLVED", resolve_custom(n, 7, b, NONE, t2, e) == READER_NAVIGATION_UNRESOLVED); }
  for (uint64_t r : {8, 9, 10, 12}) { tgt t2; check("custom: out-of-container or malformed row " + std::to_string(r) + " is RANGE",
        resolve_custom(n, r, b, NONE, t2, e) == READER_NAVIGATION_RANGE && t2.t.kind == 0); }
  { tgt t2; check("custom: one path match that the SDK left unresolved is not guessed", resolve_custom(n, 11, b, NONE, t2, e) == READER_NAVIGATION_UNRESOLVED);
    check("custom: a missing target is UNRESOLVED", resolve_custom(n, 13, b, NONE, t2, e) == READER_NAVIGATION_UNRESOLVED);
    check("custom: a row beyond the snapshot is RANGE", resolve_custom(n, 14, b, NONE, t2, e) == READER_NAVIGATION_RANGE); }
  /* CFI on a publication without the built-in EPUB provider is refused. */
  { tgt t2; reader_navigation_status s = reader_navigation_resolve_cfi(n, b.pub, "/6/2!/4/2", nullptr, &t2.t, &e);
    check("custom: a CFI without the EPUB provider fails and yields no target", s != READER_NAVIGATION_OK && t2.t.kind == 0);
    check("custom: an empty CFI is ARGUMENT", reader_navigation_resolve_cfi(n, b.pub, "", nullptr, &t2.t, &e) == READER_NAVIGATION_ARGUMENT);
    check("custom: a document-only call on a publication snapshot is ARGUMENT", reader_navigation_resolve_page(n, 0, nullptr, nullptr, &t2.t, &e) == READER_NAVIGATION_ARGUMENT); }
  /* Cancellation and reentrancy on resolve. */
  struct state { int polls = 0, at = 0; reader_navigation *nav = nullptr; int busy_seen = 0; };
  state st;
  exr_control counting; std::memset(&counting, 0, sizeof(counting)); counting.context = &st;
  counting.cancelled = [](void *c) -> int { state *s = (state *)c; s->polls++; return s->at && s->polls == s->at; };
  { reader_navigation_resolve_options o = ropt(2, &counting); tgt t2;
    check("custom: a clean resolve completes", reader_navigation_resolve_publication(n, 0, b.pub, &o, &t2.t, &e) == READER_NAVIGATION_OK);
    int total = st.polls; bool all = total > 0;
    for (int k = 1; k <= total; k++) {
      st.polls = 0; st.at = k; tgt t3;
      reader_navigation_status s = reader_navigation_resolve_publication(n, 0, b.pub, &o, &t3.t, &e);
      all = all && s == READER_NAVIGATION_CANCELLED && t3.t.kind == 0 && !t3.t.part_path;
    }
    st.at = 0; st.polls = 0; tgt t4;
    check("custom: cancelling at every poll point of resolve yields CANCELLED and no target", all);
    check("custom: resolve succeeds again after cancellation", reader_navigation_resolve_publication(n, 0, b.pub, &o, &t4.t, &e) == READER_NAVIGATION_OK && t4.t.part == 2); }
  {
    st.nav = n; exr_control re; std::memset(&re, 0, sizeof(re)); re.context = &st;
    re.cancelled = [](void *c) -> int {
      state *s = (state *)c; reader_navigation_page pg; reader_navigation_info info; reader_navigation_error x; reader_navigation *copy = s->nav;
      if (reader_navigation_rows(s->nav, 0, 1, &pg, &x) == READER_NAVIGATION_BUSY && !pg.rows) s->busy_seen++;
      if (reader_navigation_info_get(s->nav, &info, &x) == READER_NAVIGATION_BUSY) s->busy_seen++;
      if (reader_navigation_children(s->nav, NONE, 0, 1, &pg, &x) == READER_NAVIGATION_BUSY) s->busy_seen++;
      if (reader_navigation_close(&copy, &x) == READER_NAVIGATION_BUSY && copy == s->nav) s->busy_seen++;
      return 0;
    };
    reader_navigation_resolve_options o = ropt(2, &re); tgt t2;
    reader_navigation_status s = reader_navigation_resolve_publication(n, 0, b.pub, &o, &t2.t, &e);
    check("custom: reentrant rows/info/children/close from a control callback return BUSY and the outer call succeeds",
          s == READER_NAVIGATION_OK && st.busy_seen >= 4 && st.busy_seen % 4 == 0);
    reader_navigation_page pg; check("custom: the snapshot is usable after a reentrancy attempt", reader_navigation_rows(n, 0, 100, &pg, &e) == READER_NAVIGATION_OK && pg.count == b.labels.size());
    reader_navigation_page_free(&pg);
  }
  reader_navigation_close(&n, &e);
  exr_publication_free(b.pub);
  check("custom: a bad options struct size is ARGUMENT", [&] {
    custom_book s; s.paths = {"a"}; s.ids = {"i"}; add(s, SIZE_MAX, SIZE_MAX, "x", "a"); build(s);
    reader_navigation_options o = nopt(); o.struct_size = 3; reader_navigation *x = nullptr;
    bool ok = reader_navigation_open_publication(s.pub, &o, &x, &e) == READER_NAVIGATION_ARGUMENT && !x;
    reader_navigation_options big = nopt(READER_NAVIGATION_NODES_MAX + 1);
    ok = ok && reader_navigation_open_publication(s.pub, &big, &x, &e) == READER_NAVIGATION_ARGUMENT && !x;
    reader_navigation_options bigd = nopt(0, READER_NAVIGATION_DEPTH_MAX + 1);
    ok = ok && reader_navigation_open_publication(s.pub, &bigd, &x, &e) == READER_NAVIGATION_ARGUMENT && !x;
    ok = ok && reader_navigation_open_publication(nullptr, nullptr, &x, &e) == READER_NAVIGATION_ARGUMENT;
    exr_publication_free(s.pub); return ok; }());
}

/* ---------- limits ---------- */
void limit_cases() {
  reader_navigation_error e;
  auto flat = [](size_t count, size_t label_bytes) {
    custom_book s; s.paths = {"a.xhtml"}; s.ids = {"i"};
    for (size_t i = 0; i < count; i++) add(s, SIZE_MAX, 0, std::string(label_bytes, 'x') + std::to_string(i), "a.xhtml", "n.xhtml");
    return s; };
  { custom_book s = flat(150, 4); build(s); reader_navigation *n = nullptr;
    reader_navigation_options o = nopt(100);
    check("limits: 150 rows with max_nodes 100 are refused, not truncated", reader_navigation_open_publication(s.pub, &o, &n, &e) == READER_NAVIGATION_LIMIT && !n);
    o = nopt(150);
    check("limits: exactly max_nodes is accepted", reader_navigation_open_publication(s.pub, &o, &n, &e) == READER_NAVIGATION_OK && n);
    reader_navigation_info info; bool ok = n && reader_navigation_info_get(n, &info, &e) == READER_NAVIGATION_OK && info.node_count == 150;
    check("limits: the accepted snapshot has all 150 rows", ok); reader_navigation_close(&n, &e);
    o = nopt(0, 0, 500); s.pub = s.pub;
    check("limits: text over max_text_bytes is refused", reader_navigation_open_publication(s.pub, &o, &n, &e) == READER_NAVIGATION_LIMIT && !n);
    exr_publication_free(s.pub); }
  { custom_book s; s.paths = {"a.xhtml"}; s.ids = {"i"};
    for (size_t i = 0; i < 5; i++) add(s, i ? i - 1 : SIZE_MAX, 0, "d" + std::to_string(i), "a.xhtml", "n.xhtml");
    build(s); reader_navigation *n = nullptr; reader_navigation_options o = nopt(0, 4);
    check("limits: five levels with max_depth 4 are refused", reader_navigation_open_publication(s.pub, &o, &n, &e) == READER_NAVIGATION_LIMIT && !n);
    o = nopt(0, 5); bool ok = reader_navigation_open_publication(s.pub, &o, &n, &e) == READER_NAVIGATION_OK && n;
    reader_navigation_info info; ok = ok && reader_navigation_info_get(n, &info, &e) == READER_NAVIGATION_OK && info.depth_levels == 5;
    check("limits: exactly max_depth levels are accepted and counted", ok); reader_navigation_close(&n, &e); exr_publication_free(s.pub); }
  for (size_t depth : {size_t(64), size_t(65)}) {
    custom_book s; s.paths = {"a.xhtml"}; s.ids = {"i"};
    for (size_t i = 0; i < depth; i++) add(s, i ? i - 1 : SIZE_MAX, 0, "d", "a.xhtml", "n.xhtml");
    build(s); reader_navigation *n = nullptr;
    reader_navigation_status st = reader_navigation_open_publication(s.pub, nullptr, &n, &e);
    check("limits: a chain of " + std::to_string(depth) + " levels is " + (depth == 64 ? "accepted" : "refused") + " at the default depth",
          depth == 64 ? (st == READER_NAVIGATION_OK && n) : (st == READER_NAVIGATION_LIMIT && !n));
    reader_navigation_close(&n, &e); exr_publication_free(s.pub);
  }
  { custom_book s = flat(READER_NAVIGATION_NODES_MAX, 0); build(s); reader_navigation *n = nullptr;
    check("limits: 10000 rows are accepted by default", reader_navigation_open_publication(s.pub, nullptr, &n, &e) == READER_NAVIGATION_OK && n);
    bool contract = false; std::vector<row_copy> rows = all_rows(n, 100, &contract);
    bool order = rows.size() == READER_NAVIGATION_NODES_MAX;
    for (size_t i = 0; order && i < rows.size(); i++) order = rows[i].index == i && rows[i].label == std::to_string(i);
    check("limits: 10000 rows page as 100 pages of 100 in original order", contract && order);
    reader_navigation_close(&n, &e); exr_publication_free(s.pub); }
}

/* ---------- cancellation of open, empty and damaged navigation ---------- */
void open_cases(const std::string &dir) {
  reader_navigation_error e;
  exr_publication *p = open_pub(dir + "/nav3.epub");
  struct state { int polls = 0, at = 0; } st;
  exr_control c; std::memset(&c, 0, sizeof(c)); c.context = &st;
  c.cancelled = [](void *x) -> int { state *s = (state *)x; s->polls++; return s->at && s->polls == s->at; };
  reader_navigation_options o = nopt(0, 0, 0, &c); reader_navigation *n = nullptr;
  bool clean = reader_navigation_open_publication(p, &o, &n, &e) == READER_NAVIGATION_OK && n;
  std::string reference = clean ? digest_rows(all_rows(n, 100, nullptr)) : "";
  reader_navigation_close(&n, &e);
  int total = st.polls; bool all = clean && total > 0;
  for (int k = 1; k <= total; k++) {
    st.polls = 0; st.at = k;
    all = all && reader_navigation_open_publication(p, &o, &n, &e) == READER_NAVIGATION_CANCELLED && !n;
  }
  st.at = 0; st.polls = 0;
  bool retry = reader_navigation_open_publication(p, &o, &n, &e) == READER_NAVIGATION_OK && n && digest_rows(all_rows(n, 100, nullptr)) == reference;
  check("open: cancelling at every poll point yields CANCELLED with no handle", all);
  check("open: a retry after cancellation returns the identical snapshot", retry);
  reader_navigation_close(&n, &e); exr_publication_free(p);

  p = open_pub(dir + "/empty.epub");
  reader_navigation_info info;
  bool ok = reader_navigation_open_publication(p, nullptr, &n, &e) == READER_NAVIGATION_OK && n &&
            reader_navigation_info_get(n, &info, &e) == READER_NAVIGATION_OK && info.node_count == 0 && info.author_outline == 0 &&
            info.kind == READER_NAVIGATION_AUTHORED && info.depth_levels == 0;
  reader_navigation_page pg; ok = ok && reader_navigation_rows(n, 0, 10, &pg, &e) == READER_NAVIGATION_OK && pg.count == 0 && pg.total == 0 && pg.next == NONE;
  reader_navigation_page_free(&pg);
  ok = ok && reader_navigation_children(n, NONE, 0, 10, &pg, &e) == READER_NAVIGATION_OK && pg.count == 0 && pg.total == 0;
  reader_navigation_page_free(&pg);
  check("empty: a book without authored navigation gives an empty snapshot that is not an author outline", ok);
  g_cases.push_back({"empty", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, digest_rows({})});
  reader_navigation_close(&n, &e); exr_publication_free(p);

  for (const char *name : {"broken.epub", "entity.epub", "missing-ncx.epub"}) {
    p = open_pub(dir + "/" + name); n = reinterpret_cast<reader_navigation *>(1);
    reader_navigation_status s = reader_navigation_open_publication(p, nullptr, &n, &e);
    check(std::string("damaged: ") + name + " is CORRUPT with no handle and an SDK code", s == READER_NAVIGATION_CORRUPT && !n && e.sdk_code == (int)EXR_FORMAT);
    exr_publication_free(p);
  }
}

/* ---------- CFI on the repeated-spine book ---------- */
void cfi_cases(const std::string &dir) {
  reader_navigation_error e;
  exr_publication *a = open_pub(dir + "/repeated.epub"), *b = open_pub(dir + "/repeated.epub");
  reader_navigation *n = nullptr;
  check("cfi: snapshot opens", reader_navigation_open_publication(a, nullptr, &n, &e) == READER_NAVIGATION_OK && n);
  std::vector<std::string> paths = part_paths(a);
  bool distinct = true, firm = true;
  for (size_t part = 0; part < 2 && part < paths.size(); part++) {
    exr_document *d = nullptr; sdk(exr_publication_load(a, part, &d, &g_se), "load");
    size_t count = 0; const exr_node *nodes = exr_document_nodes(d, &count); size_t text = SIZE_MAX;
    for (size_t i = 0; i < count; i++) if (nodes[i].kind == EXR_NODE_TEXT) { text = i; break; }
    exr_cfi_point pt = {text, 0, 0}; char *cfi = nullptr;
    if (text == SIZE_MAX || exr_publication_cfi_create(a, part, d, &pt, nullptr, &cfi, &g_se) != EXR_OK) { firm = false; exr_document_free(d); continue; }
    std::string original_text = nodes[text].text ? nodes[text].text : "";
    tgt t; reader_navigation_status s = reader_navigation_resolve_cfi(n, b, cfi, nullptr, &t.t, &e);
    bool good = s == READER_NAVIGATION_OK && t.t.kind == READER_NAVIGATION_RESULT_CFI && t.t.part == part && t.t.part_path &&
                paths[part] == t.t.part_path && t.t.cfi && std::string(cfi) == t.t.cfi && t.t.cfi_node != NONE;
    if (good) { /* the point's node, confirmed on a fresh load on the second object */
      exr_document *fresh = nullptr; sdk(exr_publication_load(b, part, &fresh, &g_se), "load");
      size_t fc = 0; const exr_node *fn = exr_document_nodes(fresh, &fc);
      good = t.t.cfi_node < fc && fn[t.t.cfi_node].kind == EXR_NODE_TEXT && std::string(fn[t.t.cfi_node].text ? fn[t.t.cfi_node].text : "") == original_text;
      exr_document_free(fresh);
    }
    distinct = distinct && good;
    exr_free(cfi); exr_document_free(d);
  }
  check("cfi: a CFI of each repeated spine item resolves to that spine index, not the first path match", distinct && firm);
  { tgt t; check("cfi: an invalid CFI is refused and yields no target",
        reader_navigation_resolve_cfi(n, a, "/6/9999!/4/2", nullptr, &t.t, &e) != READER_NAVIGATION_OK && t.t.kind == 0 && !t.t.cfi);
    std::string huge(READER_NAVIGATION_CFI_MAX + 1, '1');
    check("cfi: a CFI over 4096 bytes is ARGUMENT", reader_navigation_resolve_cfi(n, a, huge.c_str(), nullptr, &t.t, &e) == READER_NAVIGATION_ARGUMENT);
    exr_publication *other = open_pub(dir + "/nav3.epub");
    check("cfi: a CFI against another book is MISMATCH", reader_navigation_resolve_cfi(n, other, "/6/2!/4/2", nullptr, &t.t, &e) == READER_NAVIGATION_MISMATCH);
    exr_publication_free(other); }
  reader_navigation_close(&n, &e); exr_publication_free(a); exr_publication_free(b);
}

/* ---------- fixed documents: by-page entries only ---------- */
exr_status draw_none(void *, size_t, const double *, const exr_draw_sink *, const exr_control *, exr_error *) { return EXR_OK; }
exr_fixed_document *make_fixed(const std::vector<std::string> &ids) {
  std::vector<exr_fixed_page> pages(ids.size());
  for (size_t i = 0; i < ids.size(); i++) {
    std::memset(&pages[i], 0, sizeof(pages[i])); pages[i].id = ids[i].c_str(); pages[i].geometry.bounds[2] = 100; pages[i].geometry.bounds[3] = 100; pages[i].geometry.unit_scale = 1;
  }
  exr_fixed_input in; std::memset(&in, 0, sizeof(in));
  in.struct_size = sizeof(in); in.title = "f"; in.pages = pages.data(); in.page_count = pages.size(); in.draw = draw_none;
  exr_fixed_document *d = nullptr; sdk(exr_fixed_create(&in, &d, &g_se), "fixed_create"); return d;
}
void page_cases(const std::string &dir) {
  reader_navigation_error e;
  const std::string path = dir + "/pages.pdf"; std::vector<unsigned char> bytes = slurp(path); uint64_t before = hash_bytes(bytes);
  exr_fixed_open_options oo; std::memset(&oo, 0, sizeof(oo)); oo.struct_size = sizeof(oo);
  exr_fixed_document *a = nullptr, *b = nullptr;
  sdk(exr_fixed_open_memory(EXR_PDF, bytes.data(), bytes.size(), &oo, &a, &g_se), "pdf open");
  sdk(exr_fixed_open_memory(EXR_PDF, bytes.data(), bytes.size(), &oo, &b, &g_se), "pdf open second");
  reader_navigation *n = nullptr;
  check("pages: a PDF gives a by-page snapshot", reader_navigation_open_pages(a, nullptr, &n, &e) == READER_NAVIGATION_OK && n);
  reader_navigation_info info; reader_navigation_info_get(n, &info, &e);
  size_t pc = 0; const exr_fixed_page *pages = exr_fixed_pages(a, &pc);
  check("pages: it is flagged as pages and never as an author outline", info.kind == READER_NAVIGATION_PAGES && info.author_outline == 0 &&
        info.source == READER_NAVIGATION_FROM_FIXED && info.node_count == pc && pc == 3);
  std::vector<row_copy> rows = all_rows(n, 2, nullptr); bool role = rows.size() == pc, outline = false;
  for (size_t i = 0; role && i < rows.size(); i++) {
    role = rows[i].role == "page" && rows[i].part == i && rows[i].part_id == pages[i].id && rows[i].parent == NONE &&
           rows[i].target_class == READER_NAVIGATION_TARGET_PAGE && !rows[i].label.empty();
    if (rows[i].label.find("Authored Outline Title") != std::string::npos) outline = true;
  }
  check("pages: every page is a root row with role page, its page id and no PDF outline text", role && !outline);
  bool located = true; std::vector<std::string> unique_ids;
  size_t pc2 = 0; const exr_fixed_page *pages2 = exr_fixed_pages(b, &pc2);
  for (size_t i = 0; i < rows.size(); i++) {
    tgt t; reader_navigation_status s = reader_navigation_resolve_page(n, i, b, nullptr, &t.t, &e);
    located = located && s == READER_NAVIGATION_OK && t.t.kind == READER_NAVIGATION_RESULT_PAGE && t.t.part == i && !t.t.part_path &&
              i < pc2 && std::string(t.t.part_id) == pages2[i].id && t.t.node == NONE;
  }
  check("pages: each page row is confirmed on a second independently opened PDF", located);
  { exr_fixed_document *other = make_fixed({"x", "y", "z"}); tgt t;
    check("pages: another document is MISMATCH", reader_navigation_resolve_page(n, 0, other, nullptr, &t.t, &e) == READER_NAVIGATION_MISMATCH);
    exr_fixed_free(other); }
  { reader_navigation_options o = nopt(2); reader_navigation *x = nullptr;
    check("pages: more pages than max_nodes are refused", reader_navigation_open_pages(a, &o, &x, &e) == READER_NAVIGATION_LIMIT && !x); }
  reader_navigation_close(&n, &e); exr_fixed_free(a); exr_fixed_free(b);
  check("pages: the PDF bytes are unchanged", hash_bytes(slurp(path)) == before);
}

void write_report(const std::string &path) {
  std::ofstream f(path, std::ios::binary);
  f << "{\n  \"failures\": " << g_failures << ",\n  \"checks\": [\n";
  for (size_t i = 0; i < g_checks.size(); i++) {
    std::string n; for (char c : g_checks[i].name) { if (c == '"' || c == '\\') n.push_back('\\'); if ((unsigned char)c >= 32) n.push_back(c); }
    f << "    {\"name\": \"" << n << "\", \"pass\": " << (g_checks[i].pass ? "true" : "false") << "}" << (i + 1 < g_checks.size() ? "," : "") << "\n";
  }
  f << "  ],\n  \"cases\": [\n";
  for (size_t i = 0; i < g_cases.size(); i++) {
    const case_report &c = g_cases[i];
    f << "    {\"id\": \"" << c.id << "\", \"rows\": " << c.rows << ", \"roots\": " << c.roots << ", \"depth_levels\": " << c.depth_levels
      << ", \"text_bytes\": " << c.text_bytes << ", \"ok\": " << c.ok << ", \"part_only\": " << c.part_only << ", \"needs_host\": " << c.needs_host
      << ", \"unresolved\": " << c.unresolved << ", \"range\": " << c.range << ", \"ambiguous\": " << c.ambiguous << ", \"other\": " << c.other
      << ", \"mislocated\": " << c.mislocated << ", \"digest\": \"" << c.digest << "\"}" << (i + 1 < g_cases.size() ? "," : "") << "\n";
  }
  f << "  ]\n}\n";
}
}

int main(int argc, char **argv) {
  std::string dir, report;
  for (int i = 1; i + 1 < argc; i += 2) {
    std::string k = argv[i]; if (k == "--fixtures") dir = argv[i + 1]; else if (k == "--report") report = argv[i + 1];
  }
  if (dir.empty() || report.empty()) { std::fprintf(stderr, "usage: navigation-probe --fixtures DIR --report FILE\n"); return 2; }
  std::memset(&g_se, 0, sizeof(g_se));
  epub_case("epub3-nav", dir, "nav3.epub", "nav3.tsv");
  epub_case("epub2-ncx", dir, "ncx2.epub", "ncx2.tsv");
  epub_case("epub3-repeated-spine", dir, "repeated.epub", "repeated.tsv");
  open_cases(dir);
  custom_cases();
  limit_cases();
  cfi_cases(dir);
  page_cases(dir);
  write_report(report);
  std::printf("checks=%zu failures=%d\n", g_checks.size(), g_failures);
  return g_failures ? 1 : 0;
}
