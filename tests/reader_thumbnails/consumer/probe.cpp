// SPDX-License-Identifier: MIT
// Installed C++ consumer of EXReaderThumbnails against the frozen SDK. Expectations
// for pixels come from tests/reader_thumbnails/make_fixtures.py (independent integer
// box filter); fixed-document sources are real PDF/CBZ originals opened by the SDK.
#include <reader_thumbnails.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <functional>
#include <map>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#else
#include <sys/stat.h>
#endif

extern "C" {
unsigned long long thumb_peak_rss(void);
unsigned long long thumb_current_rss(void);
int thumb_thread_count(void);
}

namespace fs = std::filesystem;
using Bytes = std::vector<unsigned char>;

namespace {

struct Result { std::string name; bool pass; std::string detail; };
std::vector<Result> results;
std::vector<std::string> skipped;
struct Measure {
  std::string id;
  uint64_t cache_entries, cache_bytes, decoded_bytes, rss_before, rss_after, peak_rss;
  uint64_t scanned_files = 0, peak_retained = 0;
};
std::vector<Measure> measures;

void check(const std::string& name, bool pass, const std::string& detail = "") {
  results.push_back({name, pass, detail});
  std::printf("%s %s%s%s\n", pass ? "PASS" : "FAIL", name.c_str(), detail.empty() ? "" : " :: ", detail.c_str());
  std::fflush(stdout);
}
[[noreturn]] void fatal(const std::string& what) {
  std::printf("FATAL %s\n", what.c_str());
  std::fflush(stdout);
  std::exit(2);
}
std::string num(uint64_t v) { return std::to_string(v); }

Bytes read_file(const fs::path& p) {
  std::ifstream in(p, std::ios::binary);
  if (!in) fatal("cannot read " + p.string());
  return Bytes((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
}
void write_file(const fs::path& p, const Bytes& b) {
  std::ofstream out(p, std::ios::binary | std::ios::trunc);
  out.write(reinterpret_cast<const char*>(b.data()), (std::streamsize)b.size());
  if (!out.good()) fatal("cannot write " + p.string());
}
std::string sha(const Bytes& b) {
  char out[65];
  rth_sha256_hex(b.data(), b.size(), out);
  return out;
}
rth_book mk_book(int format, const std::string& hex) {
  rth_book b;
  std::memset(&b, 0, sizeof(b));
  b.format = format;
  std::snprintf(b.sha256, sizeof(b.sha256), "%s", hex.c_str());
  return b;
}
rth_request req(uint32_t w, uint32_t h, uint32_t page = 0, uint32_t bg = 0xffffffffu) {
  rth_request r = rth_request_defaults();
  r.width = w; r.height = h; r.page = page; r.background = bg;
  return r;
}
struct Thumb {
  rth_thumbnail t;
  Thumb() { std::memset(&t, 0, sizeof(t)); }
  ~Thumb() { rth_thumbnail_free(&t); }
  Thumb(const Thumb&) = delete;
  Thumb& operator=(const Thumb&) = delete;
  Bytes px() const { return t.pixels ? Bytes(t.pixels, t.pixels + (size_t)t.height * t.stride) : Bytes(); }
  const unsigned char* at(uint32_t x, uint32_t y) const { return t.pixels + (size_t)y * t.stride + (size_t)x * 4u; }
};
bool near_px(const unsigned char* p, int r, int g, int b, int a, int tol = 2) {
  return std::abs((int)p[0] - r) <= tol && std::abs((int)p[1] - g) <= tol && std::abs((int)p[2] - b) <= tol && std::abs((int)p[3] - a) <= tol;
}
rth_cache* open_cache(const fs::path& dir, const rth_limits* limits = nullptr) {
  rth_cache* c = nullptr;
  rth_error e;
  if (rth_cache_open(dir.u8string().c_str(), limits, &c, &e) != RTH_OK || !c) fatal("cache open: " + std::string(e.message));
  return c;
}
rth_stats stats_of(rth_cache* c) {
  rth_stats s;
  std::memset(&s, 0, sizeof(s));
  s.struct_size = sizeof(s);
  rth_error e;
  if (rth_cache_stats(c, &s, &e) != RTH_OK) fatal("stats: " + std::string(e.message));
  return s;
}
uint64_t dir_bytes(const fs::path& d) {
  uint64_t n = 0;
  for (const auto& it : fs::directory_iterator(d)) {
    std::string name = it.path().filename().string();
    if (name.rfind("rth-", 0) == 0 && name.size() > 4 && name.compare(name.size() - 4, 4, ".rth") == 0) n += fs::file_size(it.path());
  }
  return n;
}
std::vector<fs::path> files_with(const fs::path& d, const std::string& prefix, const std::string& suffix) {
  std::vector<fs::path> v;
  for (const auto& it : fs::directory_iterator(d)) {
    std::string name = it.path().filename().string();
    if (name.rfind(prefix, 0) == 0 && name.size() >= suffix.size() && name.compare(name.size() - suffix.size(), suffix.size(), suffix) == 0) v.push_back(it.path());
  }
  std::sort(v.begin(), v.end());
  return v;
}
rth_status cover(rth_cache* c, const rth_book& b, const Bytes& png, uint32_t w, uint32_t h, Thumb& t,
                 const rth_control* ctl = nullptr, rth_error* err = nullptr) {
  rth_request r = req(w, h);
  rth_error local;
  return rth_cover_from_encoded(c, &b, png.empty() ? nullptr : png.data(), png.size(), &r, ctl, &t.t, err ? err : &local);
}
Bytes from_hex(const std::string& s) {
  Bytes out;
  for (size_t i = 0; i + 1 < s.size(); i += 2) out.push_back((unsigned char)std::stoi(s.substr(i, 2), nullptr, 16));
  return out;
}

struct Expect { std::string name; uint32_t bw, bh, ow, oh; Bytes px; };
struct Canceller { int target; int polls; };
int cancel_cb(void* ctx) {
  Canceller* c = static_cast<Canceller*>(ctx);
  ++c->polls;
  return c->polls >= c->target ? 1 : 0;
}

std::map<std::string, Bytes> fx;       // generated originals
std::map<std::string, Bytes> repo;     // repository fixtures
std::vector<Expect> expects;
fs::path work_root;

const Expect& expect_of(const std::string& name, uint32_t bw, uint32_t bh) {
  for (const Expect& e : expects) if (e.name == name && e.bw == bw && e.bh == bh) return e;
  fatal("missing expectation " + name);
}
fs::path fresh(const std::string& name) {
  fs::path p = work_root / name;
  fs::remove_all(p);
  fs::create_directories(p);
  return p;
}
exr_fixed_document* open_fixed(exr_format format, const Bytes& b) {
  exr_fixed_document* d = nullptr;
  exr_error e;
  std::memset(&e, 0, sizeof(e));
  if (exr_fixed_open_memory(format, b.data(), b.size(), nullptr, &d, &e) != EXR_OK || !d) fatal(std::string("fixed open: ") + e.message);
  return d;
}
exr_library* open_library(const fs::path& p) {
  exr_library* l = nullptr;
  exr_error e;
  std::memset(&e, 0, sizeof(e));
  if (exr_library_open(p.u8string().c_str(), &l, &e) != EXR_OK || !l) fatal(std::string("library open: ") + e.message);
  return l;
}
int64_t import_memory(exr_library* l, exr_format f, const Bytes& b, const char* title) {
  int64_t id = 0;
  exr_error e;
  std::memset(&e, 0, sizeof(e));
  if (exr_library_import(l, f, b.data(), b.size(), title, &id, &e) != EXR_OK) fatal(std::string("import: ") + e.message);
  return id;
}
Bytes library_blob(exr_library* l, int64_t id, int cover_flag) {
  void* data = nullptr;
  size_t n = 0;
  exr_error e;
  std::memset(&e, 0, sizeof(e));
  if (exr_library_blob(l, id, cover_flag, &data, &n, &e) != EXR_OK) fatal(std::string("blob: ") + e.message);
  Bytes out;
  if (data && n) out.assign(static_cast<unsigned char*>(data), static_cast<unsigned char*>(data) + n);
  exr_free(data);
  return out;
}
std::string book_snapshot(exr_library* l) {
  exr_book* books = nullptr;
  size_t n = 0;
  exr_error e;
  std::memset(&e, 0, sizeof(e));
  if (exr_library_books(l, nullptr, &books, &n, &e) != EXR_OK) fatal("books");
  std::string s;
  for (size_t i = 0; i < n; ++i)
    s += num((uint64_t)books[i].id) + "|" + (books[i].title ? books[i].title : "") + "|" + num((uint64_t)books[i].position) + "|" + std::to_string(books[i].status) + "|" + std::to_string(books[i].favorite) + ";";
  exr_books_free(books, n);
  return s;
}
void measure(const std::string& id, rth_cache* c, const fs::path& dir, uint64_t decoded, uint64_t before) {
  rth_stats s = stats_of(c);
  Measure m;
  m.id = id;
  m.cache_entries = s.entries;
  m.cache_bytes = dir_bytes(dir);
  m.decoded_bytes = decoded;
  m.rss_before = before;
  m.rss_after = thumb_current_rss();
  m.peak_rss = thumb_peak_rss();
  m.scanned_files = s.scanned_files;
  m.peak_retained = s.peak_retained_entries;
  measures.push_back(m);
}
// Records the bounded-scan figures of the last open: candidates inspected, the largest
// retained entry set (bounded by max_entries), cache bytes and whole-process RSS.
void measure_scan(const std::string& id, rth_cache* c, const fs::path& dir, uint64_t before) {
  rth_stats s = stats_of(c);
  Measure m;
  m.id = id;
  m.cache_entries = s.entries;
  m.cache_bytes = dir_bytes(dir);
  m.decoded_bytes = 0;
  m.rss_before = before;
  m.rss_after = thumb_current_rss();
  m.peak_rss = thumb_peak_rss();
  m.scanned_files = s.scanned_files;
  m.peak_retained = s.peak_retained_entries;
  measures.push_back(m);
}

// ---------------------------------------------------------------------------
void test_exact() {
  fs::path dir = fresh("exact");
  rth_cache* c = open_cache(dir);
  for (const Expect& e : expects) {
    const Bytes& png = fx[e.name + ".png"];
    rth_book b = mk_book((int)EXR_EPUB, sha(png));
    Thumb t;
    rth_status st = cover(c, b, png, e.bw, e.bh, t);
    std::string label = e.name + " into " + num(e.bw) + "x" + num(e.bh);
    check("exact: " + label + " equals the independent expectation",
          st == RTH_OK && t.t.origin == RTH_ORIGIN_AUTHOR_COVER && t.t.width == e.ow && t.t.height == e.oh && t.px() == e.px && !t.t.from_cache && t.t.stored,
          st == RTH_OK ? "dims " + num(t.t.width) + "x" + num(t.t.height) : "status " + num(st));
    Thumb again;
    st = cover(c, b, png, e.bw, e.bh, again);
    check("exact: " + label + " second request is a cache hit with identical pixels",
          st == RTH_OK && again.t.from_cache == 1 && !again.t.stored && again.px() == e.px && again.t.decoded_bytes == 0);
  }
  auto dims = [&](const std::string& n, uint32_t bw, uint32_t bh, uint32_t ow, uint32_t oh) {
    const Bytes& png = fx[n + ".png"];
    rth_book b = mk_book((int)EXR_EPUB, sha(png));
    Thumb t;
    rth_status st = cover(c, b, png, bw, bh, t);
    return st == RTH_OK && t.t.width == ow && t.t.height == oh && t.t.stride == ow * 4u;
  };
  check("aspect: 300x100 into 60x60 is 60x20", dims("wide300x100", 60, 60, 60, 20));
  check("aspect: 100x300 into 60x60 is 20x60", dims("tall100x300", 60, 60, 20, 60));
  check("aspect: a 10x10 source is never upscaled into 64x64", dims("small10x10", 64, 64, 10, 10));
  check("aspect: 10x10 into 4x7 is 4x4", dims("small10x10", 4, 7, 4, 4));
  {
    const Bytes& png = fx["alpha8x8.png"];
    Thumb t;
    cover(c, mk_book((int)EXR_EPUB, sha(png)), png, 8, 8, t);
    bool shape = t.t.pixels && t.t.width == 8 && t.t.height == 8;
    check("alpha: fully transparent source texels stay alpha 0 with RGB 0", shape && near_px(t.at(0, 0), 0, 0, 0, 0, 0) && near_px(t.at(3, 7), 0, 0, 0, 0, 0));
    check("alpha: a 50% texel keeps alpha 128 and its straight colour", shape && near_px(t.at(4, 3), 0, 255, 0, 128, 0));
    check("alpha: opaque texels stay opaque", shape && near_px(t.at(7, 7), 0, 0, 255, 255, 0));
    Thumb g;
    const Bytes& gp = fx["grad16x8.png"];
    cover(c, mk_book((int)EXR_EPUB, sha(gp)), gp, 8, 8, g);
    bool opaque = g.t.pixels != nullptr;
    for (uint32_t y = 0; opaque && y < g.t.height; ++y) for (uint32_t x = 0; x < g.t.width; ++x) opaque = opaque && g.at(x, y)[3] == 255;
    check("alpha: an opaque source scales to an opaque thumbnail", opaque);
  }
  rth_cache_close(c);
}

void test_missing() {
  fs::path dir = fresh("missing");
  rth_cache* c = open_cache(dir);
  rth_book none = mk_book((int)EXR_EPUB, std::string(64, 'a'));
  Thumb t;
  rth_status st = cover(c, none, Bytes(), 64, 64, t);
  check("missing cover: host with no encoded cover gets the normal placeholder", st == RTH_OK && t.t.origin == RTH_ORIGIN_NONE && !t.t.pixels && t.t.width == 0 && t.t.height == 0);
  fs::path lp = dir / "library.db";
  exr_library* lib = open_library(lp);
  uint64_t entries0 = stats_of(c).entries;
  struct Case { const char* label; const char* file; bool bounded; };
  Case cases[] = {{"EPUB whose package declares no cover", "cover-none.epub", false},
                  {"EPUB whose 8 MiB+ cover stays in the source", "cover-import-large.epub", false},
                  {"bounded file import of a cover-bearing EPUB", "cover-import.epub", true}};
  for (const Case& cs : cases) {
    const Bytes& epub = fx.count(cs.file) ? fx[cs.file] : repo[cs.file];
    int64_t id = 0;
    exr_error e;
    std::memset(&e, 0, sizeof(e));
    if (cs.bounded) {
      fs::path p = dir / cs.file;
      write_file(p, epub);
      if (exr_library_import_file(lib, EXR_EPUB, p.u8string().c_str(), "bounded", &id, &e) != EXR_OK) fatal(std::string("bounded import: ") + e.message);
    } else {
      id = import_memory(lib, EXR_EPUB, epub, "memory");
    }
    rth_request r = req(64, 64);
    rth_book b = mk_book((int)EXR_EPUB, sha(epub));
    Thumb x;
    rth_error err;
    st = rth_cover_from_library(c, lib, id, &b, &r, nullptr, &x.t, &err);
    check(std::string("missing cover: ") + cs.label + " is a placeholder, not an error", st == RTH_OK && x.t.origin == RTH_ORIGIN_NONE && !x.t.pixels);
  }
  check("missing cover: placeholders create no cache entry", stats_of(c).entries == entries0 && files_with(dir, "rth-", ".rth").empty());
  {
    const Bytes& epub = repo["cover-import.epub"];
    int64_t id = import_memory(lib, EXR_EPUB, epub, "cover");
    Bytes blob = library_blob(lib, id, 1);
    uint32_t sw = 0, sh = 0;
    exr_error e;
    std::memset(&e, 0, sizeof(e));
    bool dimmed = !blob.empty() && exr_image_page_dimensions(blob.data(), blob.size(), 0, &sw, &sh, &e) == EXR_OK;
    rth_request r = req(128, 128);
    rth_book b = mk_book((int)EXR_EPUB, sha(epub));
    Thumb x;
    rth_error err;
    st = rth_cover_from_library(c, lib, id, &b, &r, nullptr, &x.t, &err);
    bool ratio = dimmed && x.t.width && x.t.height && (uint64_t)std::abs((int64_t)x.t.width * sh - (int64_t)x.t.height * sw) <= std::max(sw, sh);
    check("library cover: the stored cover becomes an author-cover thumbnail inside the box with the source aspect",
          st == RTH_OK && x.t.origin == RTH_ORIGIN_AUTHOR_COVER && x.t.width <= 128 && x.t.height <= 128 && ratio,
          "source " + num(sw) + "x" + num(sh) + " thumbnail " + num(x.t.width) + "x" + num(x.t.height));
    Thumb y;
    st = rth_cover_from_library(c, lib, id, &b, &r, nullptr, &y.t, &err);
    check("library cover: the second request is a cache hit", st == RTH_OK && y.t.from_cache == 1 && y.px() == x.px());
  }
  {
    const Bytes& epub = fx["cover-exact.epub"];
    int64_t id = import_memory(lib, EXR_EPUB, epub, "exact");
    rth_request r = req(4, 4);
    rth_book b = mk_book((int)EXR_EPUB, sha(epub));
    Thumb x;
    rth_error err;
    rth_status st2 = rth_cover_from_library(c, lib, id, &b, &r, nullptr, &x.t, &err);
    const Expect& e = expect_of("alpha8x8", 4, 4);
    check("library cover: exr_library_blob(cover=1) pixels equal the independent expectation", st2 == RTH_OK && x.t.width == e.ow && x.t.height == e.oh && x.px() == e.px);
    Thumb viaEncoded;
    cover(c, mk_book((int)EXR_EPUB, std::string(64, 'c')), library_blob(lib, id, 1), 4, 4, viaEncoded);
    check("library cover: host-supplied encoded cover gives the same pixels as the library path", viaEncoded.px() == x.px());
  }
  exr_library_close(lib);
  rth_cache_close(c);
}

void test_previews() {
  fs::path dir = fresh("preview");
  rth_cache* c = open_cache(dir);
  const Bytes& pdf = fx["pages2.pdf"];
  rth_book pb = mk_book((int)EXR_PDF, sha(pdf));
  exr_fixed_document* doc = open_fixed(EXR_PDF, pdf);
  rth_error err;
  rth_request r0 = req(100, 100, 0);
  Thumb p0;
  uint64_t before = thumb_current_rss();
  rth_status st = rth_preview_from_fixed(c, doc, &pb, &r0, nullptr, &p0.t, &err);
  check("preview: PDF page 1 renders 100x50 and is labelled a first-page preview, not an author cover",
        st == RTH_OK && p0.t.origin == RTH_ORIGIN_FIRST_PAGE_PREVIEW && p0.t.origin != RTH_ORIGIN_AUTHOR_COVER && p0.t.width == 100 && p0.t.height == 50, err.message);
  check("preview: PDF page 1 left half is red and right half is blue", p0.t.pixels && near_px(p0.at(10, 25), 255, 0, 0, 255) && near_px(p0.at(90, 25), 0, 0, 255, 255) && near_px(p0.at(25, 5), 255, 0, 0, 255));
  measure("pdf-preview-100x50", c, dir, p0.t.decoded_bytes, before);
  Thumb p0b;
  st = rth_preview_from_fixed(c, doc, &pb, &r0, nullptr, &p0b.t, &err);
  check("preview: the second PDF request is a cache hit with identical pixels", st == RTH_OK && p0b.t.from_cache == 1 && p0b.px() == p0.px() && p0b.t.origin == RTH_ORIGIN_FIRST_PAGE_PREVIEW);
  rth_request r1 = req(100, 100, 1);
  Thumb p1;
  st = rth_preview_from_fixed(c, doc, &pb, &r1, nullptr, &p1.t, &err);
  check("preview: PDF page 2 is a separate 50x100 green entry", st == RTH_OK && !p1.t.from_cache && p1.t.width == 50 && p1.t.height == 100 && p1.t.pixels && near_px(p1.at(25, 50), 0, 255, 0, 255));
  rth_request r9 = req(100, 100, 9);
  Thumb bad;
  st = rth_preview_from_fixed(c, doc, &pb, &r9, nullptr, &bad.t, &err);
  check("preview: a page index outside the document is refused", st == RTH_ARGUMENT && !bad.t.pixels);
  rth_book epubbook = mk_book((int)EXR_EPUB, sha(pdf));
  st = rth_preview_from_fixed(c, doc, &epubbook, &r0, nullptr, &bad.t, &err);
  check("preview: a non-fixed book identity is refused", st == RTH_ARGUMENT);
  {  // same book identity, a cover and a preview never alias
    const Bytes& png = fx["grad16x8.png"];
    Thumb cv;
    cover(c, pb, png, 100, 100, cv);
    int found_prev = 0;
    Thumb b;
    rth_cache_find(c, &pb, RTH_ORIGIN_FIRST_PAGE_PREVIEW, &r0, &b.t, &found_prev, &err);
    Thumb again;
    cover(c, pb, png, 100, 100, again);
    check("origins: an author cover and a first-page preview of the same book are separate entries with separate labels",
          cv.t.origin == RTH_ORIGIN_AUTHOR_COVER && again.t.from_cache == 1 && again.t.origin == RTH_ORIGIN_AUTHOR_COVER &&
              found_prev == 1 && b.t.origin == RTH_ORIGIN_FIRST_PAGE_PREVIEW && again.px() != b.px());
  }
  {
    rth_request rbg = req(100, 100, 0, 0x000000ffu);
    Thumb x;
    st = rth_preview_from_fixed(c, doc, &pb, &rbg, nullptr, &x.t, &err);
    check("preview: a different render background is a different cache entry", st == RTH_OK && !x.t.from_cache && x.t.stored);
  }
  exr_fixed_free(doc);
  // The same PDF through the library-owned streaming reader.
  fs::path dir2 = fresh("preview-library");
  rth_cache* c2 = open_cache(dir2);
  exr_library* lib = open_library(dir2 / "library.db");
  int64_t id = import_memory(lib, EXR_PDF, pdf, "pdf");
  exr_fixed_document* ldoc = nullptr;
  exr_error se;
  std::memset(&se, 0, sizeof(se));
  if (exr_library_fixed_source(lib, id, nullptr, &ldoc, &se) != EXR_OK) fatal(std::string("fixed_source: ") + se.message);
  std::string snapshot = book_snapshot(lib);
  Bytes source_before = library_blob(lib, id, 0);
  Thumb lp;
  st = rth_preview_from_fixed(c2, ldoc, &pb, &r0, nullptr, &lp.t, &err);
  check("preview: the library-owned PDF reader gives the same pixels as the memory reader", st == RTH_OK && lp.px() == p0.px());
  check("unchanged: the stored original and the book rows are byte-identical after previews", library_blob(lib, id, 0) == source_before && source_before == pdf && book_snapshot(lib) == snapshot);
  exr_fixed_free(ldoc);
  exr_library_close(lib);
  rth_cache_close(c2);

  const Bytes& cbz = fx["pages2.cbz"];
  rth_book cb = mk_book((int)EXR_CBZ, sha(cbz));
  exr_fixed_document* cdoc = open_fixed(EXR_CBZ, cbz);
  rth_request rc = req(40, 40, 0);
  Thumb c0;
  before = thumb_current_rss();
  st = rth_preview_from_fixed(c, cdoc, &cb, &rc, nullptr, &c0.t, &err);
  bool ratio = c0.t.width && c0.t.height && std::abs((int)(c0.t.width * 3) - (int)(c0.t.height * 2)) <= 3;
  check("preview: CBZ page 1 keeps the 2:3 aspect inside 40x40", st == RTH_OK && c0.t.origin == RTH_ORIGIN_FIRST_PAGE_PREVIEW && std::max(c0.t.width, c0.t.height) == 40 && ratio,
        num(c0.t.width) + "x" + num(c0.t.height));
  check("preview: CBZ page 1 is the first image colour", c0.t.pixels && near_px(c0.at(c0.t.width / 2, c0.t.height / 2), 200, 30, 30, 255, 3));
  measure("cbz-preview-40", c, dir, c0.t.decoded_bytes, before);
  rth_request rc1 = req(40, 40, 1);
  Thumb c1;
  st = rth_preview_from_fixed(c, cdoc, &cb, &rc1, nullptr, &c1.t, &err);
  check("preview: CBZ page 2 is the second image colour", st == RTH_OK && c1.t.pixels && near_px(c1.at(c1.t.width / 2, c1.t.height / 2), 30, 30, 200, 255, 3));
  exr_fixed_free(cdoc);

  {  // repository PDF/CBZ corpus
    const Bytes& rp = repo["pdf-public.pdf"];
    exr_fixed_document* d = open_fixed(EXR_PDF, rp);
    rth_book b = mk_book((int)EXR_PDF, sha(rp));
    rth_request r = req(400, 400);
    Thumb x;
    st = rth_preview_from_fixed(c, d, &b, &r, nullptr, &x.t, &err);
    bool varied = false;
    for (uint32_t i = 4; x.t.pixels && i < (size_t)x.t.width * x.t.height * 4u && !varied; i += 4) varied = std::memcmp(x.t.pixels, x.t.pixels + i, 4) != 0;
    check("preview: the repository text PDF renders a non-blank first page inside 400x400",
          st == RTH_OK && x.t.origin == RTH_ORIGIN_FIRST_PAGE_PREVIEW && x.t.width <= 400 && x.t.height <= 400 && varied, err.message);
    exr_fixed_free(d);
    const Bytes& rc2 = repo["comic.cbz"];
    d = open_fixed(EXR_CBZ, rc2);
    b = mk_book((int)EXR_CBZ, sha(rc2));
    Thumb y;
    st = rth_preview_from_fixed(c, d, &b, &r, nullptr, &y.t, &err);
    check("preview: the repository CBZ renders a first-page preview inside 400x400", st == RTH_OK && y.t.origin == RTH_ORIGIN_FIRST_PAGE_PREVIEW && y.t.width >= 1 && y.t.width <= 400 && y.t.height >= 1 && y.t.height <= 400, err.message);
    exr_fixed_free(d);
  }
  rth_cache_close(c);
}

void test_limits() {
  fs::path dir = fresh("limits");
  rth_cache* c = open_cache(dir);
  rth_book b = mk_book((int)EXR_EPUB, std::string(64, 'b'));
  const Bytes& png = fx["grad16x8.png"];
  Thumb t;
  rth_error err;
  rth_request r = req(0, 0);
  check("limits: an empty output box is refused", rth_cover_from_encoded(c, &b, png.data(), png.size(), &r, nullptr, &t.t, &err) == RTH_ARGUMENT && !t.t.pixels);
  r = req(513, 8);
  check("limits: a box wider than max_edge is refused", rth_cover_from_encoded(c, &b, png.data(), png.size(), &r, nullptr, &t.t, &err) == RTH_LIMIT);
  r = req(0xffffffffu, 0xffffffffu);
  check("limits: a 4294967295x4294967295 box is refused without allocation", rth_cover_from_encoded(c, &b, png.data(), png.size(), &r, nullptr, &t.t, &err) == RTH_LIMIT && !t.t.pixels);
  check("limits: rejected requests are counted and nothing was stored", stats_of(c).rejected >= 2 && stats_of(c).entries == 0);
  r = req(8, 8);
  rth_book bad = b;
  bad.sha256[0] = 'A';
  check("limits: an uppercase SHA-256 is refused", rth_cover_from_encoded(c, &bad, png.data(), png.size(), &r, nullptr, &t.t, &err) == RTH_ARGUMENT);
  bad = b;
  bad.sha256[63] = 0;
  check("limits: a 63-digit SHA-256 is refused", rth_cover_from_encoded(c, &bad, png.data(), png.size(), &r, nullptr, &t.t, &err) == RTH_ARGUMENT);
  bad = b;
  bad.format = 0;
  check("limits: format 0 is refused", rth_cover_from_encoded(c, &bad, png.data(), png.size(), &r, nullptr, &t.t, &err) == RTH_ARGUMENT);
  bad.format = 10;
  check("limits: format 10 is refused", rth_cover_from_encoded(c, &bad, png.data(), png.size(), &r, nullptr, &t.t, &err) == RTH_ARGUMENT);
  check("limits: NULL book, request and output are refused",
        rth_cover_from_encoded(c, nullptr, png.data(), png.size(), &r, nullptr, &t.t, &err) == RTH_ARGUMENT &&
            rth_cover_from_encoded(c, &b, png.data(), png.size(), nullptr, nullptr, &t.t, &err) == RTH_ARGUMENT &&
            rth_cover_from_encoded(c, &b, png.data(), png.size(), &r, nullptr, nullptr, &err) == RTH_ARGUMENT);
  {
    Thumb x;
    rth_status st = cover(c, b, fx["huge-dims.png"], 8, 8, x, nullptr, &err);
    check("anomalous image: a PNG header declaring 30000x30000 over invalid data is refused before decoding (the SDK reports a damaged header)", (st == RTH_LIMIT || st == RTH_FORMAT) && !x.t.pixels && stats_of(c).peak_decoded_bytes == 0, err.message);
    st = cover(c, b, fx["wide9000x1.png"], 8, 8, x, nullptr, &err);
    check("limits: a valid 9000x1 PNG above the 8192 SDK edge limit is refused with a limit status before decoding", st == RTH_LIMIT && !x.t.pixels && stats_of(c).peak_decoded_bytes == 0, err.message);
    st = cover(c, b, fx["big4100x4100.png"], 8, 8, x, nullptr, &err);
    check("limits: a valid 4100x4100 PNG above 16,777,216 pixels is refused with a limit status before decoding", st == RTH_LIMIT && !x.t.pixels && stats_of(c).peak_decoded_bytes == 0, err.message);
    st = cover(c, b, fx["truncated.png"], 8, 8, x, nullptr, &err);
    check("anomalous image: a truncated PNG is refused as a format error", st == RTH_FORMAT && !x.t.pixels, err.message);
    st = cover(c, b, fx["badmagic.png"], 8, 8, x, nullptr, &err);
    check("anomalous image: bytes that are not an image are refused", (st == RTH_FORMAT || st == RTH_UNSUPPORTED) && !x.t.pixels, err.message);
    check("anomalous image: refusals stored nothing", stats_of(c).entries == 0 && stats_of(c).stores == 0);
  }
  rth_cache_close(c);

  {  // caps on decoded source pixels and encoded bytes
    fs::path d2 = fresh("limits-source");
    rth_limits lim = rth_limits_defaults();
    lim.max_source_pixels = 1000000;
    rth_cache* c2 = open_cache(d2, &lim);
    Thumb x;
    rth_status st = cover(c2, b, fx["mid3000x3000.png"], 64, 64, x, nullptr, &err);
    rth_stats s = stats_of(c2);
    check("limits: a 9,000,000-pixel image above max_source_pixels=1,000,000 is refused before any decode allocation",
          st == RTH_LIMIT && !x.t.pixels && s.peak_decoded_bytes == 0 && s.entries == 0, err.message);
    rth_cache_close(c2);
    lim = rth_limits_defaults();
    lim.max_encoded_bytes = 100;
    c2 = open_cache(d2, &lim);
    st = cover(c2, b, fx["mid3000x3000.png"], 64, 64, x, nullptr, &err);
    check("limits: an encoded cover above max_encoded_bytes is refused", st == RTH_LIMIT && !x.t.pixels);
    rth_cache_close(c2);
  }
  {  // decoded bytes versus cache bytes, recorded separately
    fs::path d3 = fresh("limits-decoded");
    rth_cache* c3 = open_cache(d3);
    Thumb x;
    uint64_t before = thumb_current_rss();
    rth_status st = cover(c3, b, fx["mid3000x3000.png"], 64, 64, x, nullptr, &err);
    rth_stats s = stats_of(c3);
    check("decoded bytes: a 3000x3000 cover reports 36,000,000 transient decoded bytes",
          st == RTH_OK && x.t.decoded_bytes == 36000000ull && s.peak_decoded_bytes == 36000000ull && x.t.source_width == 3000 && x.t.source_height == 3000);
    check("decoded bytes: cache bytes are a small separate figure and the decoded image is not part of them", s.bytes > 0 && s.bytes < 40000 && s.bytes == dir_bytes(d3));
    measure("cover-3000x3000-decode", c3, d3, x.t.decoded_bytes, before);
    rth_cache_close(c3);
  }

  rth_limits bad_limits = rth_limits_defaults();
  rth_cache* tmp = nullptr;
  fs::path d4 = fresh("limits-open");
  auto refuses = [&](rth_limits l, rth_status want) {
    tmp = nullptr;
    rth_status st = rth_cache_open(d4.u8string().c_str(), &l, &tmp, &err);
    bool good = st == want && tmp == nullptr;
    if (tmp) rth_cache_close(tmp);
    return good;
  };
  rth_limits l = bad_limits; l.max_edge = 0;
  check("limits: max_edge 0 is refused", refuses(l, RTH_LIMIT));
  l = bad_limits; l.max_edge = RTH_EDGE_HARD_MAX + 1;
  check("limits: max_edge above the hard maximum is refused", refuses(l, RTH_LIMIT));
  l = bad_limits; l.max_entries = RTH_ENTRIES_HARD_MAX + 1;
  check("limits: max_entries above the hard maximum is refused", refuses(l, RTH_LIMIT));
  l = bad_limits; l.max_total_bytes = RTH_TOTAL_BYTES_HARD_MAX + 1;
  check("limits: max_total_bytes above the hard maximum is refused", refuses(l, RTH_LIMIT));
  l = bad_limits; l.max_total_bytes = RTH_TOTAL_BYTES_MIN - 1;
  check("limits: max_total_bytes below the minimum is refused", refuses(l, RTH_LIMIT));
  l = bad_limits; l.max_source_pixels = RTH_SOURCE_PIXELS_HARD_MAX + 1;
  check("limits: max_source_pixels above the hard maximum is refused", refuses(l, RTH_LIMIT));
  l = bad_limits; l.max_encoded_bytes = RTH_ENCODED_HARD_MAX + 1;
  check("limits: max_encoded_bytes above the hard maximum is refused", refuses(l, RTH_LIMIT));
  tmp = nullptr;
  check("limits: a NULL directory is refused", rth_cache_open(nullptr, nullptr, &tmp, &err) == RTH_ARGUMENT && !tmp);
}

void test_lru() {
  fs::path dir = fresh("lru-count");
  rth_limits lim = rth_limits_defaults();
  lim.max_entries = 3;
  rth_cache* c = open_cache(dir, &lim);
  const Bytes& png = fx["grad16x8.png"];
  rth_book b = mk_book((int)EXR_EPUB, sha(png));
  uint32_t sizes[4] = {8, 6, 4, 3};
  for (int i = 0; i < 3; ++i) { Thumb t; cover(c, b, png, sizes[i], sizes[i], t); }
  { Thumb t; cover(c, b, png, sizes[0], sizes[0], t); }  // touch the oldest entry (a hit)
  { Thumb t; cover(c, b, png, sizes[3], sizes[3], t); }
  auto has = [&](uint32_t size) {
    Thumb u;
    rth_status st = cover(c, b, png, size, size, u);
    return st == RTH_OK && u.t.from_cache == 1;
  };
  rth_stats s = stats_of(c);
  check("lru: with max_entries=3 the fourth entry evicts exactly one", s.entries == 3 && s.evictions == 1 && files_with(dir, "rth-", ".rth").size() == 3);
  // Probe order matters: a miss re-inserts and would evict, so check the survivors first.
  bool a = has(8), cc = has(4), d = has(3);
  check("lru: the touched oldest entry and the two newest survive", a && cc && d);
  check("lru: the least recently used entry (6x6) was the one evicted", !has(6));
  rth_cache_close(c);

  fs::path d2 = fresh("lru-bytes");
  lim = rth_limits_defaults();
  lim.max_total_bytes = 4096;
  c = open_cache(d2, &lim);
  const Bytes& wide = fx["wide300x100.png"];
  rth_book wb = mk_book((int)EXR_EPUB, sha(wide));
  bool bounded = true, accounted = true, rejected_returned = true;
  for (uint32_t k = 5; k <= 16; ++k) {
    Thumb t;
    rth_status st = cover(c, wb, wide, k * 4, k * 4, t);
    uint64_t payload = (uint64_t)t.t.width * t.t.height * 4;
    if (st != RTH_OK || !t.t.pixels) rejected_returned = false;
    if (payload + 100 > 4096 && t.t.stored) rejected_returned = false;
    rth_stats cs = stats_of(c);
    bounded = bounded && cs.bytes <= 4096 && dir_bytes(d2) <= 4096;
    accounted = accounted && cs.bytes == dir_bytes(d2) && cs.entries == files_with(d2, "rth-", ".rth").size();
  }
  s = stats_of(c);
  check("lru: total cache bytes never exceed max_total_bytes=4096 after each of 12 insertions", bounded);
  check("lru: tracked bytes and entries equal the directory contents after each insertion", accounted);
  check("lru: byte pressure evicted entries and entries larger than the cap were returned but not stored", s.evictions > 0 && s.rejected > 0 && rejected_returned,
        "evictions " + num(s.evictions) + " rejected " + num(s.rejected));
  measure("lru-bytes-4096", c, d2, 0, thumb_current_rss());
  rth_cache_close(c);
}

void test_mishits() {
  fs::path dir = fresh("mishit");
  rth_cache* c = open_cache(dir);
  const Bytes& g = fx["grad16x8.png"];
  const Bytes& s = fx["swap16x8.png"];
  rth_book b1 = mk_book((int)EXR_EPUB, std::string(64, '1'));
  rth_book b2 = mk_book((int)EXR_EPUB, std::string(64, '2'));
  Thumb t1, t2, t1b, t2b;
  cover(c, b1, g, 8, 8, t1);
  cover(c, b2, s, 8, 8, t2);
  check("mishit: two books with the same request each get their own pixels", !t1.t.from_cache && !t2.t.from_cache && t1.px() != t2.px() && t1.px() == expect_of("grad16x8", 8, 8).px && t2.px() == expect_of("swap16x8", 8, 8).px);
  cover(c, b1, g, 8, 8, t1b);
  cover(c, b2, s, 8, 8, t2b);
  check("mishit: repeating both books hits each own entry", t1b.t.from_cache && t2b.t.from_cache && t1b.px() == t1.px() && t2b.px() == t2.px());
  rth_book b1cbz = mk_book((int)EXR_CBZ, std::string(64, '1'));
  Thumb x;
  cover(c, b1cbz, s, 8, 8, x);
  check("mishit: the same SHA with another format is a different book", !x.t.from_cache && x.px() == t2.px());
  Thumb y;
  cover(c, b1, g, 5, 5, y);
  check("mishit: the same book with another output size is a miss", !y.t.from_cache && y.px() == expect_of("grad16x8", 5, 5).px);
  Thumb z;
  cover(c, b1, s, 8, 8, z);
  check("mishit: different encoded cover bytes under one book identity are a miss", !z.t.from_cache && z.px() == t2.px());
  check("mishit: neither cover call changed the other's stored pixels", [&] { Thumb q; cover(c, b1, g, 8, 8, q); return q.t.from_cache == 1 && q.px() == t1.px(); }());
  {
    int found = 1;
    Thumb q;
    rth_error err;
    rth_request r = req(8, 8);
    rth_cache_find(c, &b1, RTH_ORIGIN_AUTHOR_COVER, &r, &q.t, &found, &err);
    check("mishit: a host-encoded cover is not served as the library cover of the same book", found == 0 && !q.t.pixels);
  }
  {
    const Bytes& pdf = fx["pages2.pdf"];
    rth_book pb = mk_book((int)EXR_PDF, sha(pdf));
    exr_fixed_document* doc = open_fixed(EXR_PDF, pdf);
    Thumb p0, p1, p0b;
    rth_error err;
    rth_request a = req(100, 100, 0), bpage = req(100, 100, 1), small = req(50, 50, 0);
    rth_preview_from_fixed(c, doc, &pb, &a, nullptr, &p0.t, &err);
    rth_preview_from_fixed(c, doc, &pb, &bpage, nullptr, &p1.t, &err);
    check("mishit: another page of the same book is a miss with different pixels", !p1.t.from_cache && p1.px() != p0.px());
    rth_preview_from_fixed(c, doc, &pb, &small, nullptr, &p0b.t, &err);
    check("mishit: another preview size is a miss", !p0b.t.from_cache && p0b.t.width == 50);
    exr_fixed_free(doc);
  }
  rth_cache_close(c);
}

void test_corruption() {
  const Bytes& png = fx["grad16x8.png"];
  rth_book b = mk_book((int)EXR_EPUB, sha(png));
  const Expect& want = expect_of("grad16x8", 8, 8);
  struct Mutation { const char* label; std::function<void(Bytes&)> apply; };
  std::vector<Mutation> mutations = {
      {"one payload byte flipped", [](Bytes& v) { v.back() ^= 0xff; }},
      {"file truncated by 10 bytes", [](Bytes& v) { v.resize(v.size() - 10); }},
      {"file zero-filled", [](Bytes& v) { std::fill(v.begin(), v.end(), 0); }},
      {"magic damaged", [](Bytes& v) { v[0] ^= 1; }},
      {"stored key altered", [](Bytes& v) { v[68 + 3] ^= 1; }},
      {"payload length field altered", [](Bytes& v) { v[28] ^= 1; }},
  };
  int index = 0;
  for (const Mutation& m : mutations) {
    for (int closed = 0; closed < 2; ++closed) {
      fs::path dir = fresh("corrupt-" + std::to_string(index++));
      rth_cache* c = open_cache(dir);
      { Thumb t; cover(c, b, png, 8, 8, t); }
      auto files = files_with(dir, "rth-", ".rth");
      if (files.size() != 1) fatal("expected one entry file");
      if (closed) { rth_cache_close(c); c = nullptr; }
      Bytes v = read_file(files[0]);
      m.apply(v);
      write_file(files[0], v);
      if (closed) c = open_cache(dir);
      Thumb t;
      rth_status st = cover(c, b, png, 8, 8, t);
      rth_stats s = stats_of(c);
      std::string label = std::string("corruption (") + m.label + (closed ? ", found at reopen" : ", found at lookup") + ")";
      check(label + ": the damaged entry is discarded and rebuilt from the source with the expected pixels",
            st == RTH_OK && !t.t.from_cache && t.t.stored && t.px() == want.px && s.corrupt_rebuilt == 1 && files_with(dir, "rth-", ".rth").size() == 1);
      Thumb again;
      cover(c, b, png, 8, 8, again);
      check(label + ": the rebuilt entry is then served from the cache", again.t.from_cache == 1 && again.px() == want.px);
      rth_cache_close(c);
    }
  }
  {  // index damage, stale temporaries and foreign files
    fs::path dir = fresh("corrupt-misc");
    rth_cache* c = open_cache(dir);
    { Thumb t; cover(c, b, png, 8, 8, t); }
    rth_cache_close(c);
    write_file(dir / "rth-index.txt", Bytes{0xff, 0x00, 'x', '\n', 0x01});
    Bytes junk{'t', 'm', 'p'};
    write_file(dir / "rth-tmp-77.tmp", junk);
    Bytes note{'u', 's', 'e', 'r', ' ', 'f', 'i', 'l', 'e'};
    write_file(dir / "notes.txt", note);
    write_file(dir / "other.tmp", note);
    write_file(dir / "rth-0123.rth.bak", note);
    write_file(dir / ("rth-" + std::string(32, 'a') + ".rth"), Bytes(200, 7));
    c = open_cache(dir);
    rth_stats s = stats_of(c);
    check("recovery: a garbage index is ignored and the valid entry is re-adopted from the directory", s.entries == 1);
    check("recovery: a stale temporary of the cache is removed", !fs::exists(dir / "rth-tmp-77.tmp"));
    check("recovery: a garbage entry file is dropped and counted", !fs::exists(dir / ("rth-" + std::string(32, 'a') + ".rth")) && s.corrupt_rebuilt == 1);
    check("recovery: foreign files in the directory are left byte-identical",
          read_file(dir / "notes.txt") == note && read_file(dir / "other.tmp") == note && read_file(dir / "rth-0123.rth.bak") == note);
    Thumb t;
    cover(c, b, png, 8, 8, t);
    check("recovery: the re-adopted entry is served as a hit", t.t.from_cache == 1 && t.px() == want.px);
    rth_cache_close(c);
    fs::remove(dir / "rth-index.txt");
    c = open_cache(dir);
    check("recovery: a missing index is rebuilt from the directory", stats_of(c).entries == 1);
    rth_cache_close(c);
  }
}

template <typename F>
void cancel_sweep(const std::string& label, const fs::path& dir, rth_cache* c, const Bytes& golden, F run) {
  size_t points = 0;
  bool clean = true, completed = false;
  for (int n = 1; n <= 600; ++n) {
    Canceller cc{n, 0};
    rth_control ctl{cancel_cb, &cc};
    Thumb t;
    rth_status st = run(&ctl, t);
    if (st == RTH_CANCELLED) {
      ++points;
      rth_stats s = stats_of(c);
      if (t.t.pixels || t.t.width || t.t.height || s.stores != 0 || s.entries != 0 || !files_with(dir, "rth-", ".rth").empty() || !files_with(dir, "rth-tmp-", ".tmp").empty())
        clean = false;
    } else {
      completed = st == RTH_OK && t.px() == golden && !t.t.from_cache;
      break;
    }
  }
  check(label + ": cancelling at each of " + num(points) + " poll points returns CANCELLED with no output and no cache entry", points >= 3 && clean);
  check(label + ": the first uncancelled retry equals the expected thumbnail and publishes the entry", completed && stats_of(c).stores == 1);
}

void test_cancel() {
  {
    fs::path dir = fresh("cancel-encoded");
    rth_cache* c = open_cache(dir);
    const Bytes& png = fx["grad16x8.png"];
    rth_book b = mk_book((int)EXR_EPUB, sha(png));
    cancel_sweep("cancel encoded cover", dir, c, expect_of("grad16x8", 8, 8).px, [&](const rth_control* ctl, Thumb& t) { return cover(c, b, png, 8, 8, t, ctl); });
    rth_cache_close(c);
  }
  {
    fs::path dir = fresh("cancel-library");
    rth_cache* c = open_cache(dir);
    exr_library* lib = open_library(dir / "library.db");
    const Bytes& epub = fx["cover-exact.epub"];
    int64_t id = import_memory(lib, EXR_EPUB, epub, "exact");
    rth_book b = mk_book((int)EXR_EPUB, sha(epub));
    rth_request r = req(4, 4);
    cancel_sweep("cancel library cover", dir, c, expect_of("alpha8x8", 4, 4).px, [&](const rth_control* ctl, Thumb& t) {
      rth_error e;
      return rth_cover_from_library(c, lib, id, &b, &r, ctl, &t.t, &e);
    });
    exr_library_close(lib);
    rth_cache_close(c);
  }
  struct Fixed { const char* label; const char* file; exr_format f; uint32_t box; };
  Fixed fixed[] = {{"cancel PDF preview", "pages2.pdf", EXR_PDF, 100}, {"cancel CBZ preview", "pages2.cbz", EXR_CBZ, 40}};
  for (const Fixed& fe : fixed) {
    const Bytes& bytes = fx[fe.file];
    rth_book b = mk_book((int)fe.f, sha(bytes));
    exr_fixed_document* doc = open_fixed(fe.f, bytes);
    rth_request r = req(fe.box, fe.box);
    fs::path gdir = fresh(std::string("cancel-golden-") + fe.file);
    rth_cache* gc = open_cache(gdir);
    Thumb golden;
    rth_error e;
    rth_preview_from_fixed(gc, doc, &b, &r, nullptr, &golden.t, &e);
    rth_cache_close(gc);
    fs::path dir = fresh(std::string("cancel-") + fe.file);
    rth_cache* c = open_cache(dir);
    cancel_sweep(fe.label, dir, c, golden.px(), [&](const rth_control* ctl, Thumb& t) {
      rth_error ee;
      return rth_preview_from_fixed(c, doc, &b, &r, ctl, &t.t, &ee);
    });
    // The borrowed document stays usable after cancelled renders.
    Thumb again;
    rth_cache_close(c);
    c = open_cache(fresh(std::string("cancel-after-") + fe.file));
    rth_status st = rth_preview_from_fixed(c, doc, &b, &r, nullptr, &again.t, &e);
    check(std::string(fe.label) + ": the borrowed document renders normally after the cancelled attempts", st == RTH_OK && again.px() == golden.px());
    rth_cache_close(c);
    exr_fixed_free(doc);
  }
}

void test_reopen() {
  fs::path dir = fresh("reopen");
  rth_cache* c = open_cache(dir);
  const Bytes& png = fx["grad16x8.png"];
  const Bytes& alt = fx["swap16x8.png"];
  rth_book b = mk_book((int)EXR_EPUB, sha(png));
  rth_book b2 = mk_book((int)EXR_EPUB, sha(alt));
  Thumb a, a2;
  cover(c, b, png, 8, 8, a);
  cover(c, b2, alt, 8, 8, a2);
  rth_stats before = stats_of(c);
  rth_cache_close(c);
  c = open_cache(dir);
  rth_stats after = stats_of(c);
  check("reopen: entries and bytes are restored from the directory", after.entries == before.entries && after.bytes == before.bytes && after.bytes == dir_bytes(dir));
  Thumb h;
  cover(c, b, png, 8, 8, h);
  check("reopen: a stored cover is served from the cache with identical pixels and no decode", h.t.from_cache == 1 && h.px() == a.px() && h.t.decoded_bytes == 0);
  int found = 0;
  Thumb f;
  rth_error err;
  rth_request r = req(8, 8);
  rth_cache_find(c, &b, RTH_ORIGIN_AUTHOR_COVER, &r, &f.t, &found, &err);
  check("reopen: a library-keyed lookup does not alias an encoded-cover entry", found == 0);
  rth_cache_close(c);

  fs::path d2 = fresh("reopen-lru");
  rth_limits lim = rth_limits_defaults();
  lim.max_entries = 3;
  c = open_cache(d2, &lim);
  uint32_t sizes[3] = {8, 6, 4};
  for (uint32_t s : sizes) { Thumb t; cover(c, b, png, s, s, t); }
  { Thumb t; cover(c, b, png, 8, 8, t); }  // touch the oldest
  rth_cache_close(c);
  c = open_cache(d2, &lim);
  { Thumb t; cover(c, b, png, 3, 3, t); }
  bool keep8 = false, miss6 = false;
  { Thumb t; cover(c, b, png, 8, 8, t); keep8 = t.t.from_cache == 1; }
  { Thumb t; cover(c, b, png, 6, 6, t); miss6 = t.t.from_cache == 0; }
  check("reopen: LRU recency survives close and reopen (the touched entry stays, the stale one is evicted)", keep8 && miss6);
  rth_cache_close(c);
  lim.max_entries = 1;
  c = open_cache(d2, &lim);
  rth_stats s = stats_of(c);
  check("reopen: reopening with smaller limits evicts down to the new bounds", s.entries == 1 && s.bytes <= lim.max_total_bytes && files_with(d2, "rth-", ".rth").size() == 1);
  rth_cache_close(c);

  fs::path d3 = fresh("reopen-library");
  c = open_cache(d3);
  exr_library* lib = open_library(d3 / "library.db");
  const Bytes& epub = fx["cover-exact.epub"];
  int64_t id = import_memory(lib, EXR_EPUB, epub, "exact");
  rth_book eb = mk_book((int)EXR_EPUB, sha(epub));
  rth_request r4 = req(4, 4);
  Thumb x;
  rth_cover_from_library(c, lib, id, &eb, &r4, nullptr, &x.t, &err);
  exr_library_close(lib);
  rth_cache_close(c);
  c = open_cache(d3);
  Thumb y;
  int fy = 0;
  rth_cache_find(c, &eb, RTH_ORIGIN_AUTHOR_COVER, &r4, &y.t, &fy, &err);
  check("reopen: a library cover is found again after reopen without the library or the book", fy == 1 && y.px() == x.px() && y.t.origin == RTH_ORIGIN_AUTHOR_COVER);
  check("reopen: clear removes only cache entries", [&] {
    write_file(d3 / "keep.txt", Bytes{'k'});
    bool ok = rth_cache_clear(c, &err) == RTH_OK && stats_of(c).entries == 0 && files_with(d3, "rth-", ".rth").empty();
    return ok && fs::exists(d3 / "keep.txt") && fs::exists(d3 / "library.db");
  }());
  rth_cache_close(c);
}

void test_owner() {
  fs::path dir = fresh("owner");
  rth_cache* c = open_cache(dir);
  const Bytes& png = fx["grad16x8.png"];
  rth_book b = mk_book((int)EXR_EPUB, sha(png));
  { Thumb t; cover(c, b, png, 8, 8, t); }
  uint64_t stores = stats_of(c).stores;
  rth_status st = RTH_OK, close_called = RTH_OK;
  bool pixels = true;
  std::thread worker([&] {
    Thumb t;
    st = cover(c, b, png, 4, 4, t);
    pixels = t.t.pixels != nullptr;
    rth_stats s;
    s.struct_size = sizeof(s);
    rth_error e;
    close_called = rth_cache_stats(c, &s, &e);
    rth_cache_close(c);  // refused: must not free the cache
  });
  worker.join();
  check("owner: a call from another thread is refused and changes nothing", st == RTH_ARGUMENT && !pixels && stats_of(c).stores == stores && close_called == RTH_ARGUMENT);
  Thumb t;
  check("owner: the cache still works for its owner after the foreign close attempt", cover(c, b, png, 8, 8, t) == RTH_OK && t.t.from_cache == 1);
  struct Reenter { rth_cache* c; const rth_book* b; const Bytes* png; rth_status inner; int calls; };
  Reenter re{c, &b, &png, RTH_OK, 0};
  auto cb = [](void* ctx) -> int {
    Reenter* r = static_cast<Reenter*>(ctx);
    if (r->calls++ == 0) {
      Thumb x;
      rth_request rq = req(3, 3);
      rth_error e;
      r->inner = rth_cover_from_encoded(r->c, r->b, r->png->data(), r->png->size(), &rq, nullptr, &x.t, &e);
    }
    return 0;
  };
  rth_control ctl{cb, &re};
  Thumb outer;
  rth_request r = req(5, 5);
  rth_error e;
  rth_status os = rth_cover_from_encoded(c, &b, png.data(), png.size(), &r, &ctl, &outer.t, &e);
  check("owner: re-entry from a control callback is refused while the outer call succeeds", re.inner == RTH_ARGUMENT && os == RTH_OK && outer.t.pixels);
  rth_cache_close(c);
}

// Blocks deletion of a cache entry the way another program on this platform can:
// on Windows by holding the file open without delete sharing, elsewhere by removing
// write permission from the directory that contains it.
struct Blocker {
  fs::path dir;
#ifdef _WIN32
  HANDLE handle = INVALID_HANDLE_VALUE;
#else
  bool changed = false;
#endif
  explicit Blocker(const fs::path& d) : dir(d) {
#ifdef _WIN32
    for (const auto& it : fs::directory_iterator(d)) {
      const std::string name = it.path().filename().string();
      if (name.size() == 40 && name.compare(0, 4, "rth-") == 0 && name.compare(36, 4, ".rth") == 0) {
        HANDLE h = ::CreateFileW(it.path().c_str(), GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr,
                                 OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
        if (h != INVALID_HANDLE_VALUE) handle = h;
        break;
      }
    }
#else
    changed = ::chmod(d.c_str(), 0500) == 0;
#endif
  }
  bool active() const {
#ifdef _WIN32
    return handle != INVALID_HANDLE_VALUE;
#else
    return changed;
#endif
  }
  void release() {
#ifdef _WIN32
    if (handle != INVALID_HANDLE_VALUE) {
      ::CloseHandle(handle);
      handle = INVALID_HANDLE_VALUE;
    }
#else
    if (changed) {
      ::chmod(dir.c_str(), 0700);
      changed = false;
    }
#endif
  }
  ~Blocker() { release(); }
  Blocker(const Blocker&) = delete;
  Blocker& operator=(const Blocker&) = delete;
};

// Pixel-level regression on a genuinely non-uniform source. The expected bytes come
// from make_fixtures.py, so a comparison here is a content comparison: sizes, a
// non-null pointer or a uniform fill cannot satisfy it.
void test_pixels() {
  fs::path dir = fresh("pixels");
  rth_cache* c = open_cache(dir);
  const Bytes& src = fx["noise64x48.png"];
  rth_book b = mk_book((int)EXR_EPUB, sha(src));
  const uint32_t boxes[4][2] = {{64, 48}, {16, 12}, {31, 9}, {7, 5}};
  bool all = true;
  size_t distinct = 0;
  std::string detail;
  for (const auto& box : boxes) {
    const Expect& e = expect_of("noise64x48", box[0], box[1]);
    Thumb t;
    const rth_status st = cover(c, b, src, box[0], box[1], t);
    const bool equal = st == RTH_OK && t.t.width == e.ow && t.t.height == e.oh && t.px() == e.px;
    for (size_t i = 0; i < e.px.size(); i += 4) {
      bool seen = false;
      for (size_t j = 0; j < i && !seen; j += 4) seen = std::memcmp(e.px.data() + j, e.px.data() + i, 4) == 0;
      if (!seen) ++distinct;
    }
    if (!equal) { all = false; detail = num(box[0]) + "x" + num(box[1]) + " differs"; }
  }
  check("pixels: a non-uniform 64x48 source matches its independent reference at 64x48, 16x12, 31x9 and 7x5",
        all && distinct >= 8, all ? "distinct reference texels " + num(distinct) : detail);
  {
    const Expect& e = expect_of("noise64x48", 7, 5);
    Thumb t;
    const rth_status st = cover(c, b, src, 7, 5, t);
    bool alpha_varied = false;
    for (size_t i = 4; i + 4 <= e.px.size() && !alpha_varied; i += 4) alpha_varied = e.px[i + 3] != e.px[3];
    check("pixels: the 7x5 downscale is compared byte for byte and its reference carries more than one alpha level",
          st == RTH_OK && t.px() == e.px && alpha_varied, "bytes " + num((uint64_t)e.px.size()));
  }
  rth_cache_close(c);
}

// An entry file that cannot be deleted is not free space: the store that needs its room
// is refused, the accounting keeps the old bytes, and an independent walk of the
// directory shows the hard caps still hold.
void test_delete_failure() {
  const Bytes& png = fx["grad16x8.png"];
  const Bytes& alt = fx["swap16x8.png"];
  rth_book b = mk_book((int)EXR_EPUB, sha(png));
  rth_book b2 = mk_book((int)EXR_EPUB, sha(alt));
  fs::path dir = fresh("delete-store");
  rth_limits lim = rth_limits_defaults();
  lim.max_entries = 1;
  rth_cache* c = open_cache(dir, &lim);
  { Thumb t; cover(c, b, png, 8, 8, t); }
  const rth_stats before = stats_of(c);
  uint64_t bytes_before = dir_bytes(dir);
  {
    Blocker blocker(dir);
    Thumb t;
    const rth_status st = cover(c, b2, alt, 8, 8, t);
    const rth_stats after = stats_of(c);
    size_t files = 0;
    uint64_t bytes = 0;
    for (const auto& it : fs::directory_iterator(dir)) {
      const std::string n = it.path().filename().string();
      if (n.size() == 40 && n.compare(0, 4, "rth-") == 0 && n.compare(36, 4, ".rth") == 0) {
        ++files;
        bytes += fs::file_size(it.path());
      }
    }
    check("disk budget: an entry that cannot be deleted is not counted as freed; the store is refused and the caps hold",
          blocker.active() && st == RTH_OK && t.t.pixels != nullptr && t.t.stored == 0 && after.delete_failures >= 1 &&
              after.entries == before.entries && after.bytes == before.bytes && files == before.entries && bytes == bytes_before &&
              files <= lim.max_entries && bytes <= lim.max_total_bytes,
          "stored " + num((uint64_t)t.t.stored) + " delete_failures " + num(after.delete_failures) + " entries " + num(after.entries) +
              " files " + num((uint64_t)files));
  }
  Thumb t2;
  const rth_status st2 = cover(c, b2, alt, 8, 8, t2);
  size_t files2 = 0;
  uint64_t bytes2 = 0;
  for (const auto& it : fs::directory_iterator(dir)) {
    const std::string n = it.path().filename().string();
    if (n.size() == 40 && n.compare(0, 4, "rth-") == 0 && n.compare(36, 4, ".rth") == 0) {
      ++files2;
      bytes2 += fs::file_size(it.path());
    }
  }
  check("disk budget: after the block is released the same store succeeds and evicts the old entry",
        st2 == RTH_OK && t2.t.stored == 1 && files2 == 1 && bytes2 <= lim.max_total_bytes, "files " + num((uint64_t)files2));
  rth_cache_close(c);
}

// open must not return a cache while an own file it has to delete is still there.
void test_open_delete_failure() {
  fs::path dir = fresh("delete-open");
  write_file(dir / "rth-owner.lock", Bytes());
  const std::string bogus = "rth-" + std::string(32, 'c') + ".rth";
  write_file(dir / bogus, Bytes(200, 0x21));
  bool blocked = false;
#ifdef _WIN32
  HANDLE h = ::CreateFileW((dir / bogus).c_str(), GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_EXISTING,
                           FILE_ATTRIBUTE_NORMAL, nullptr);
  blocked = h != INVALID_HANDLE_VALUE;
#else
  blocked = ::chmod(dir.c_str(), 0500) == 0;
#endif
  rth_cache* c = reinterpret_cast<rth_cache*>(static_cast<std::uintptr_t>(1));
  rth_error e;
  std::memset(&e, 0, sizeof(e));
  const rth_status st = rth_cache_open(dir.u8string().c_str(), nullptr, &c, &e);
  const bool still_there = fs::exists(dir / bogus);
  check("disk budget: open refuses to return a cache when a damaged entry cannot be deleted",
        blocked && st == RTH_IO && c == nullptr && still_there, "status " + num((uint64_t)st) + " " + e.message);
  if (st == RTH_OK && c) rth_cache_close(c);
#ifdef _WIN32
  if (blocked) ::CloseHandle(h);
#else
  if (blocked) ::chmod(dir.c_str(), 0700);
#endif
  c = open_cache(dir);
  rth_stats s = stats_of(c);
  check("disk budget: after the block is released the damaged entry is deleted and the cache opens",
        s.entries == 0 && s.corrupt_rebuilt == 1 && !fs::exists(dir / bogus), "entries " + num(s.entries));
  rth_cache_close(c);
}

// Bounded open: one pass, a candidate budget independent of the directory size, and
// entry-by-entry retention instead of collecting the whole directory first.
void test_bounded_open() {
  const Bytes& png = fx["grad16x8.png"];
  rth_book b = mk_book((int)EXR_EPUB, sha(png));
  {  // a tidy directory is scanned completely
    fs::path dir = fresh("bounded-small");
    rth_cache* c = open_cache(dir);
    { Thumb t; cover(c, b, png, 8, 8, t); }
    rth_cache_close(c);
    c = open_cache(dir);
    rth_stats s = stats_of(c);
    check("bounded open: a tidy directory is scanned completely, holds one entry and reports its work",
          s.entries == 1 && s.own_candidates == 1 && s.scan_deleted == 0 && s.peak_retained_entries <= 1 &&
              s.scanned_files >= 2 && s.scanned_files <= 8,
          "scanned " + num(s.scanned_files) + " own " + num(s.own_candidates) + " peak " + num(s.peak_retained_entries));
    rth_cache_close(c);
  }
  {  // 40 valid entries, reopened with max_entries=3
    fs::path dir = fresh("bounded-many");
    rth_limits lim = rth_limits_defaults();
    lim.max_entries = 64;
    rth_cache* c = open_cache(dir, &lim);
    for (uint32_t k = 4; k < 44; ++k) { Thumb t; cover(c, b, png, k, k, t); }
    const uint32_t stored = stats_of(c).entries;
    rth_cache_close(c);
    lim.max_entries = 3;
    c = open_cache(dir, &lim);
    rth_stats s = stats_of(c);
    check("bounded open: 40 entries were stored before the bounded reopen", stored == 40, "stored " + num(stored));
    check("bounded open: a reopen with max_entries=3 retains at most 3 while scanning, never 40",
          s.entries == 3 && s.peak_retained_entries <= 4 && s.scanned_files >= 41 && s.own_candidates == 40 && s.scan_deleted == 37,
          "entries " + num(s.entries) + " peak " + num(s.peak_retained_entries) + " scanned " + num(s.scanned_files) + " deleted " + num(s.scan_deleted));
    measure_scan("bounded-reopen-max-entries-3", c, dir, thumb_current_rss());
    rth_cache_close(c);
  }
  {  // 900 recognised candidates plus 400 unrelated files, max_entries=2
    fs::path dir = fresh("bounded-overflow");
    const uint32_t candidates = 900, unrelated = 400;
    std::vector<std::string> foreign;
    for (uint32_t i = 0; i < unrelated; ++i) {
      const std::string n = "note-" + num(i) + ".txt";
      foreign.push_back(n);
      write_file(dir / n, Bytes(3, (unsigned char)('a' + (i % 26))));
    }
    Bytes junk(200, 0x5a);
    for (uint32_t i = 0; i < candidates; ++i) {
      char name[64];
      std::snprintf(name, sizeof(name), "rth-%032x.rth", static_cast<unsigned>(i));
      write_file(dir / name, junk);
    }
    rth_limits lim = rth_limits_defaults();
    lim.max_entries = 2;
    uint64_t before = thumb_current_rss();
    rth_cache* c = open_cache(dir, &lim);
    rth_stats s = stats_of(c);
    size_t left = 0;
    for (const auto& it : fs::directory_iterator(dir)) {
      const std::string n = it.path().filename().string();
      if (n.size() == 40 && n.compare(0, 4, "rth-") == 0 && n.compare(36, 4, ".rth") == 0) ++left;
    }
    bool foreign_ok = true;
    for (size_t i = 0; i < foreign.size() && i < 25; ++i) foreign_ok = foreign_ok && fs::exists(dir / foreign[i]);
    check("bounded open: 1300 candidates are cleaned in one pass and the unrelated files are left untouched",
          s.entries == 0 && s.own_candidates == candidates && s.scan_deleted == candidates && left == 0 && foreign_ok,
          "own " + num(s.own_candidates) + " deleted " + num(s.scan_deleted) + " left " + num((uint64_t)left) + " unrelated kept " + num((uint64_t)foreign_ok));
    measure_scan("bounded-overflow-max-entries-2", c, dir, before);
    Thumb t, u;
    const bool stored = cover(c, b, png, 8, 8, t) == RTH_OK && t.t.stored;
    check("bounded open: the cache still stores and serves after a full cleanup", stored && cover(c, b, png, 8, 8, u) == RTH_OK && u.t.from_cache == 1);
    rth_cache_close(c);
  }
}

// The directory hard bound: whatever the directory held, an OK open leaves no more
// own entry files or bytes than max_entries / max_total_bytes, judged by an
// independent walk of the directory, and unrelated files survive untouched.
void test_disk_budget() {
  const Bytes& png = fx["grad16x8.png"];
  const Bytes& alt = fx["swap16x8.png"];
  rth_book b = mk_book((int)EXR_EPUB, sha(png));
  rth_book b2 = mk_book((int)EXR_EPUB, sha(alt));
  fs::path dir = fresh("disk-budget");
  rth_limits big = rth_limits_defaults();
  big.max_entries = 512;
  rth_cache* c = open_cache(dir, &big);
  for (uint32_t k = 4; k < 404; ++k) { Thumb t; cover(c, b, png, k, k, t); }
  const uint32_t grown = stats_of(c).entries;
  const uint64_t before = dir_bytes(dir);
  rth_cache_close(c);
  std::vector<std::string> foreign;
  for (int i = 0; i < 40; ++i) {
    const std::string n = "user-" + num((uint64_t)i) + ".txt";
    foreign.push_back(n);
    write_file(dir / n, Bytes(5, (unsigned char)('A' + (i % 26))));
  }
  rth_limits small = rth_limits_defaults();
  small.max_entries = 5;
  small.max_total_bytes = 4096;
  uint64_t rss = thumb_current_rss();
  c = open_cache(dir, &small);
  rth_stats s = stats_of(c);
  auto walk = [&dir](size_t& files, uint64_t& bytes) {
    files = 0;
    bytes = 0;
    for (const auto& it : fs::directory_iterator(dir)) {
      const std::string n = it.path().filename().string();
      if (n.size() == 40 && n.compare(0, 4, "rth-") == 0 && n.compare(36, 4, ".rth") == 0) {
        ++files;
        bytes += fs::file_size(it.path());
      }
    }
  };
  size_t files = 0;
  uint64_t bytes = 0;
  walk(files, bytes);
  bool foreign_ok = true;
  for (const std::string& n : foreign) foreign_ok = foreign_ok && fs::exists(dir / n);
  check("disk budget: 400 stored entries were on disk before the lower-cap reopen",
        grown == 400 && before > 4096, "entries " + num(grown) + " bytes " + num(before));
  check("disk budget: an OK open leaves every own entry file inside max_entries=5 and max_total_bytes=4096",
        files <= 5 && bytes <= 4096 && s.entries == files && s.bytes == bytes && s.peak_retained_entries <= 6 &&
            s.scan_deleted >= 395 && foreign_ok,
        "files " + num((uint64_t)files) + " bytes " + num(bytes) + " deleted " + num(s.scan_deleted) +
            " unrelated kept " + num((uint64_t)foreign_ok));
  measure_scan("disk-budget-reopen-5-4096", c, dir, rss);
  {
    Thumb t;
    cover(c, b2, alt, 8, 8, t);
  }
  size_t files2 = 0;
  uint64_t bytes2 = 0;
  walk(files2, bytes2);
  rth_stats s2 = stats_of(c);
  check("disk budget: a further store keeps the open directory inside the same caps",
        files2 <= 5 && bytes2 <= 4096 && s2.entries == files2 && s2.bytes == bytes2,
        "files " + num((uint64_t)files2) + " bytes " + num(bytes2));
  rth_cache_close(c);
}

// One cache per directory, in this process as well.
void test_owner_lock() {
  fs::path dir = fresh("owner-lock");
  rth_cache* a = open_cache(dir);
  rth_cache* b = reinterpret_cast<rth_cache*>(static_cast<std::uintptr_t>(1));
  rth_error e;
  std::memset(&e, 0, sizeof(e));
  const rth_status st = rth_cache_open(dir.u8string().c_str(), nullptr, &b, &e);
  check("owner lock: a second cache handle on the same directory is refused", st == RTH_BUSY && b == nullptr,
        "status " + num((uint64_t)st));
  rth_cache_close(a);
  b = nullptr;
  std::memset(&e, 0, sizeof(e));
  const rth_status st2 = rth_cache_open(dir.u8string().c_str(), nullptr, &b, &e);
  check("owner lock: closing the first handle lets a new cache own the directory", st2 == RTH_OK && b != nullptr,
        "status " + num((uint64_t)st2));
  if (b) rth_cache_close(b);
}

// A directory that holds more own entry files than the scan ceiling is refused
// instead of being adopted partially; unrelated files stay.
void test_scan_ceiling() {
  fs::path dir = fresh("scan-ceiling");
  const uint32_t junk = 4100;
  Bytes body(200, 0x7e);
  for (uint32_t i = 0; i < junk; ++i) {
    char name[64];
    std::snprintf(name, sizeof(name), "rth-%032x.rth", static_cast<unsigned>(i));
    write_file(dir / name, body);
  }
  for (int i = 0; i < 20; ++i) write_file(dir / ("keep-" + num((uint64_t)i) + ".txt"), Bytes(4, 'k'));
  rth_limits lim = rth_limits_defaults();
  lim.max_entries = 1;  // ceiling = max(4096, 1*64) = 4096
  rth_cache* c = reinterpret_cast<rth_cache*>(static_cast<std::uintptr_t>(1));
  rth_error e;
  std::memset(&e, 0, sizeof(e));
  const rth_status st = rth_cache_open(dir.u8string().c_str(), &lim, &c, &e);
  bool foreign_ok = true;
  for (int i = 0; i < 20; ++i) foreign_ok = foreign_ok && fs::exists(dir / ("keep-" + num((uint64_t)i) + ".txt"));
  check("disk budget: a directory above the scan ceiling is refused with RTH_LIMIT and no cache",
        st == RTH_LIMIT && c == nullptr && foreign_ok, "status " + num((uint64_t)st) + " msg " + e.message);
  if (st == RTH_OK && c) rth_cache_close(c);
}

// Atomic publish: no temporary survives, the index replace is reported when it fails,
// and a hard link at a temporary name can never be truncated through.
void test_publish() {
  const Bytes& png = fx["grad16x8.png"];
  rth_book b = mk_book((int)EXR_EPUB, sha(png));
  {
    fs::path dir = fresh("publish-clean");
    rth_cache* c = open_cache(dir);
    { Thumb t; cover(c, b, png, 8, 8, t); }
    rth_stats s = stats_of(c);
    rth_cache_close(c);
    check("publish: a successful session publishes no temporary file and records no index failure",
          s.index_failures == 0 && s.store_failures == 0 && files_with(dir, "rth-tmp-", ".tmp").empty() && s.entries == 1 &&
              files_with(dir, "rth-", ".rth").size() == 1,
          "index failures " + num(s.index_failures) + " store failures " + num(s.store_failures));
  }
  {
    fs::path dir = fresh("publish-blocked");
    fs::create_directory(dir / "rth-index.txt");
    rth_cache* c = reinterpret_cast<rth_cache*>(static_cast<std::uintptr_t>(1));
    rth_error e;
    std::memset(&e, 0, sizeof(e));
    rth_status st = rth_cache_open(dir.u8string().c_str(), nullptr, &c, &e);
    check("publish: an index that cannot be atomically replaced makes open fail with RTH_IO", st == RTH_IO && c == nullptr, e.message);
    if (st == RTH_OK && c) rth_cache_close(c);
  }
  {  // hard links at the pre-0.1.0 temporary names must never be truncated
    fs::path dir = fresh("publish-links");
    fs::path sentinel = dir.parent_path() / "publish-sentinel.bin";
    Bytes content(4096, 0);
    for (size_t i = 0; i < content.size(); ++i) content[i] = (unsigned char)(0x5a ^ (i * 7));
    write_file(sentinel, content);
    rth_cache* c = open_cache(dir);
    int seeded = 0;
    for (int i = 1; i <= 64; ++i) {
      std::error_code ec;
      fs::create_hard_link(sentinel, dir / ("rth-tmp-" + num((uint64_t)i) + ".tmp"), ec);
      if (!ec) ++seeded;
    }
    Thumb t;
    const rth_status st = cover(c, b, png, 8, 8, t);
    bool intact = read_file(sentinel) == content;
    for (int i = 1; i <= 64 && intact; ++i) intact = read_file(dir / ("rth-tmp-" + num((uint64_t)i) + ".tmp")) == content;
    check("publish: a hard link planted at a temporary name is neither followed nor truncated",
          st == RTH_OK && t.t.stored && seeded == 64 && intact, "seeded " + num((uint64_t)seeded));
    rth_cache_close(c);
    fs::remove(sentinel);
  }
}

// Re-entry: every cache entry point refuses a call from a control callback.
void test_reentry() {
  fs::path dir = fresh("reentry");
  rth_cache* c = open_cache(dir);
  const Bytes& png = fx["grad16x8.png"];
  rth_book b = mk_book((int)EXR_EPUB, sha(png));
  { Thumb t; cover(c, b, png, 8, 8, t); }
  struct Ctx {
    rth_cache* c;
    const rth_book* b;
    const Bytes* png;
    rth_status stats_st, clear_st, find_st, cover_st;
    int found;
    int calls;
  };
  Ctx ctx{c, &b, &png, RTH_OK, RTH_OK, RTH_OK, RTH_OK, -1, 0};
  auto cb = [](void* context) -> int {
    Ctx* x = static_cast<Ctx*>(context);
    if (x->calls++ == 0) {
      rth_stats s;
      std::memset(&s, 0, sizeof(s));
      s.struct_size = sizeof(s);
      rth_error e;
      std::memset(&e, 0, sizeof(e));
      x->stats_st = rth_cache_stats(x->c, &s, &e);
      x->clear_st = rth_cache_clear(x->c, &e);
      Thumb q;
      rth_request r = req(8, 8);
      x->find_st = rth_cache_find(x->c, x->b, RTH_ORIGIN_AUTHOR_COVER, &r, &q.t, &x->found, &e);
      rth_cache_close(x->c);
      x->cover_st = cover(x->c, *x->b, *x->png, 3, 3, q);
    }
    return 0;
  };
  rth_control ctl{cb, &ctx};
  Thumb outer;
  const rth_status os = cover(c, b, png, 5, 5, outer, &ctl);
  const rth_stats after = stats_of(c);
  check("re-entry: stats, clear, find and close are all refused inside a control callback",
        ctx.stats_st == RTH_ARGUMENT && ctx.clear_st == RTH_ARGUMENT && ctx.find_st == RTH_ARGUMENT && ctx.cover_st == RTH_ARGUMENT && ctx.found == 0,
        "stats " + num((uint64_t)ctx.stats_st) + " clear " + num((uint64_t)ctx.clear_st) + " find " + num((uint64_t)ctx.find_st) + " cover " + num((uint64_t)ctx.cover_st));
  check("re-entry: the outer call completes and the cache is still usable afterwards",
        os == RTH_OK && outer.t.pixels != nullptr && after.entries == 2, "entries " + num(after.entries));
  rth_cache_close(c);
}

}  // namespace

int main(int argc, char** argv) {
  fs::path fixtures, repo_fixtures, report;
  for (int i = 1; i + 1 < argc; i += 2) {
    std::string k = argv[i];
    if (k == "--fixtures") fixtures = argv[i + 1];
    else if (k == "--repo-fixtures") repo_fixtures = argv[i + 1];
    else if (k == "--work") work_root = argv[i + 1];
    else if (k == "--report") report = argv[i + 1];
  }
  if (fixtures.empty() || repo_fixtures.empty() || work_root.empty() || report.empty()) fatal("usage: --fixtures --repo-fixtures --work --report");
  fs::create_directories(work_root);
  std::map<std::string, std::string> hashes;
  for (const auto& it : fs::directory_iterator(fixtures)) {
    std::string name = it.path().filename().string();
    if (name == "manifest.json" || name == "expect.txt") continue;
    fx[name] = read_file(it.path());
    hashes[name] = sha(fx[name]);
  }
  for (const char* name : {"cover-import.epub", "cover-import-large.epub", "pdf-public.pdf", "comic.cbz"}) {
    repo[name] = read_file(repo_fixtures / name);
    hashes[std::string("repo/") + name] = sha(repo[name]);
  }
  {
    std::ifstream in(fixtures / "expect.txt");
    std::string line;
    while (std::getline(in, line)) {
      std::istringstream ss(line);
      Expect e;
      std::string hex;
      if (ss >> e.name >> e.bw >> e.bh >> e.ow >> e.oh >> hex) { e.px = from_hex(hex); expects.push_back(e); }
    }
  }
  if (expects.empty()) fatal("no expectations");
  check("version: RTH_VERSION is 0.1.0", std::string(RTH_VERSION) == "0.1.0");
  check("sha256: rth_sha256_hex of the empty string is the standard digest", [] {
    char out[65];
    rth_sha256_hex("", 0, out);
    return std::string(out) == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";
  }());
  check("sha256: rth_sha256_hex of a 1,000,000-byte buffer spans many blocks", [] {
    Bytes v(1000000, 'a');
    char out[65];
    rth_sha256_hex(v.data(), v.size(), out);
    return std::string(out) == "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0";
  }());
  int threads_before = thumb_thread_count();
  test_exact();
  test_missing();
  test_previews();
  test_limits();
  test_lru();
  test_mishits();
  test_corruption();
  test_cancel();
  test_reopen();
  test_pixels();
  test_bounded_open();
  test_disk_budget();
  test_delete_failure();
  test_open_delete_failure();
  test_owner_lock();
  test_scan_ceiling();
  test_publish();
  test_reentry();
  test_owner();
  int threads_after = thumb_thread_count();
  if (threads_before < 0) skipped.push_back("the module creates no thread (thread count is not measured on this platform)");
  else check("threads: the process thread count is unchanged by the module (no thread is created)", threads_before == threads_after,
             num((uint64_t)threads_before) + " -> " + num((uint64_t)threads_after));
  bool unchanged = true;
  for (const auto& it : fs::directory_iterator(fixtures)) {
    std::string name = it.path().filename().string();
    if (name == "manifest.json" || name == "expect.txt") continue;
    if (sha(read_file(it.path())) != hashes[name]) unchanged = false;
  }
  for (const char* name : {"cover-import.epub", "cover-import-large.epub", "pdf-public.pdf", "comic.cbz"})
    if (sha(read_file(repo_fixtures / name)) != hashes[std::string("repo/") + name]) unchanged = false;
  check("unchanged: every original fixture file is byte-identical after all operations", unchanged);

  size_t failures = 0;
  for (const Result& r : results) if (!r.pass) ++failures;
  auto esc = [](const std::string& s) {
    std::string o;
    for (unsigned char ch : s) {
      if (ch == '"' || ch == '\\') { o += '\\'; o += (char)ch; }
      else if (ch < 0x20) { char buf[8]; std::snprintf(buf, sizeof(buf), "\\u%04x", ch); o += buf; }
      else o += (char)ch;
    }
    return o;
  };
  std::ofstream out(report, std::ios::binary | std::ios::trunc);
  out << "{\n  \"failures\": " << failures << ",\n  \"expectations\": " << expects.size() << ",\n  \"checks\": [\n";
  for (size_t i = 0; i < results.size(); ++i)
    out << "    {\"name\": \"" << esc(results[i].name) << "\", \"pass\": " << (results[i].pass ? "true" : "false") << ", \"detail\": \"" << esc(results[i].detail) << "\"}" << (i + 1 < results.size() ? "," : "") << "\n";
  out << "  ],\n  \"skipped\": [";
  for (size_t i = 0; i < skipped.size(); ++i) out << (i ? ", " : "") << "\"" << esc(skipped[i]) << "\"";
  out << "],\n  \"fixture_sha256\": {";
  size_t n = 0;
  for (const auto& kv : hashes) out << (n++ ? ", " : "") << "\"" << esc(kv.first) << "\": \"" << kv.second << "\"";
  out << "},\n  \"threads\": {\"before\": " << threads_before << ", \"after\": " << threads_after << "},\n  \"measurements\": [\n";
  for (size_t i = 0; i < measures.size(); ++i) {
    const Measure& m = measures[i];
    out << "    {\"id\": \"" << esc(m.id) << "\", \"cache_entries\": " << m.cache_entries << ", \"cache_bytes\": " << m.cache_bytes << ", \"decoded_bytes\": " << m.decoded_bytes
        << ", \"rss_before\": " << m.rss_before << ", \"rss_after\": " << m.rss_after << ", \"process_peak_rss\": " << m.peak_rss
        << ", \"scanned_files\": " << m.scanned_files << ", \"peak_retained_entries\": " << m.peak_retained << "}" << (i + 1 < measures.size() ? "," : "") << "\n";
  }
  out << "  ]\n}\n";
  out.close();
  std::printf("checks=%zu failures=%zu\n", results.size(), failures);
  return failures == 0 ? 0 : 1;
}
