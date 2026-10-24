// SPDX-License-Identifier: MIT
// Installed fault-injection consumer for EXReaderThumbnails. It replaces the global
// operator new/delete inside this binary only (no production hook, no public API
// change) so the n-th allocation throws std::bad_alloc, and it counts live
// allocations so a failed call can be shown to leak nothing: not the cache, not the
// borrowed SDK blob, not the thumbnail pixels, not a temporary file.
//
// Modes, one process each:
//   --mode open     DIR FIXTURES   every allocation point inside rth_cache_open
//   --mode store    DIR FIXTURES   every allocation point of a cover that reaches store
//   --mode library  DIR FIXTURES   every allocation point of the library-blob cover path
#include <reader_thumbnails.h>

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <new>
#include <string>
#include <vector>

namespace fs = std::filesystem;
using Bytes = std::vector<unsigned char>;

namespace {

bool g_armed = false;
long long g_countdown = 0;
long long g_live = 0;
bool g_tripped = false;

bool trip() {
  if (!g_armed) return false;
  if (g_countdown <= 0) {
    g_tripped = true;
    g_armed = false;
    return true;
  }
  --g_countdown;
  return false;
}

struct Result { std::string name; bool pass; std::string detail; };
std::vector<Result> results;

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
std::string num(long long v) { return std::to_string(v); }

Bytes read_file(const fs::path& p) {
  std::ifstream in(p, std::ios::binary);
  if (!in) fatal("cannot read " + p.string());
  return Bytes((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
}
std::string sha_of(const Bytes& b) {
  char out[65];
  rth_sha256_hex(b.data(), b.size(), out);
  return std::string(out);
}
rth_book mk_book(int format, const std::string& hex) {
  rth_book b;
  std::memset(&b, 0, sizeof(b));
  b.format = format;
  std::snprintf(b.sha256, sizeof(b.sha256), "%s", hex.c_str());
  return b;
}
struct Thumb {
  rth_thumbnail t;
  Thumb() { std::memset(&t, 0, sizeof(t)); }
  ~Thumb() { rth_thumbnail_free(&t); }
  Thumb(const Thumb&) = delete;
  Thumb& operator=(const Thumb&) = delete;
};
rth_cache* open_or_die(const std::string& dir) {
  rth_cache* c = nullptr;
  rth_error e;
  std::memset(&e, 0, sizeof(e));
  if (rth_cache_open(dir.c_str(), nullptr, &c, &e) != RTH_OK || !c) fatal("cache open: " + std::string(e.message));
  return c;
}
size_t count_entries(const fs::path& dir) {
  size_t n = 0;
  for (const auto& it : fs::directory_iterator(dir)) {
    const std::string name = it.path().filename().string();
    if (name.size() == 40 && name.compare(0, 4, "rth-") == 0 && name.compare(36, 4, ".rth") == 0) ++n;
  }
  return n;
}
size_t count_temps(const fs::path& dir) {
  size_t n = 0;
  for (const auto& it : fs::directory_iterator(dir)) {
    const std::string name = it.path().filename().string();
    if (name.rfind("rth-tmp-", 0) == 0 && name.size() > 4 && name.compare(name.size() - 4, 4, ".tmp") == 0) ++n;
  }
  return n;
}

// Every allocation point of one open: the call must report a status, return no
// cache, hold no lock, leak nothing, and the same directory must open on retry.
void sweep_open(const fs::path& root) {
  bool all_ok = true, covered = false;
  long long points = 0;
  std::string bad;
  for (long long n = 1; n <= 4096 && all_ok; ++n) {
    fs::path dir = root / ("open-" + std::to_string(n));
    fs::remove_all(dir);
    fs::create_directories(dir);
    const std::string text = dir.u8string();
    const long long live_before = g_live;
    g_countdown = n;
    g_tripped = false;
    g_armed = true;
    rth_cache* c = reinterpret_cast<rth_cache*>(static_cast<std::uintptr_t>(1));
    rth_error e;
    std::memset(&e, 0, sizeof(e));
    rth_status st = RTH_OK;
    bool escaped = false;
    try {
      st = rth_cache_open(text.c_str(), nullptr, &c, &e);
    } catch (...) {
      escaped = true;
    }
    const bool tripped = g_tripped;
    g_armed = false;
    if (!tripped) {
      covered = true;
      if (c) rth_cache_close(c);
      break;
    }
    ++points;
    const bool reported = !escaped && (st == RTH_MEMORY || st == RTH_IO) && c == nullptr;
    const bool no_leak = g_live == live_before;
    if (!reported || !no_leak) {
      all_ok = false;
      bad = "n=" + num(n) + " status=" + num((long long)st) + " escaped=" + num((long long)escaped) + " live " + num(live_before) + "->" + num(g_live) +
            " msg=" + e.message;
      if (c) rth_cache_close(c);
      break;
    }
    rth_cache* again = nullptr;
    if (rth_cache_open(text.c_str(), nullptr, &again, &e) != RTH_OK || !again) {
      all_ok = false;
      bad = "retry failed at n=" + num(n) + " msg=" + e.message;
      break;
    }
    rth_cache_close(again);
  }
  check("fault: an allocation failure inside open reports a status, clears the output and leaks nothing",
        all_ok && covered && points > 0, all_ok ? "points " + num(points) : bad);
}

// Every allocation point of a cover call that reaches the store path: the call must
// report a status with an empty output box (no pixels, no origin, no size), leave no
// entry file and no temporary, lose no memory, and the same cache must store and then
// serve the thumbnail on retry.
void sweep_store(const fs::path& root, const Bytes& png) {
  const rth_book b = mk_book((int)EXR_EPUB, sha_of(png));
  rth_request request = rth_request_defaults();
  request.width = 8;
  request.height = 8;
  bool all_ok = true, covered = false;
  long long points = 0;
  std::string bad;
  for (long long n = 1; n <= 8192 && all_ok; ++n) {
    fs::path dir = root / ("store-" + std::to_string(n));
    fs::remove_all(dir);
    rth_cache* c = open_or_die(dir.u8string());
    Thumb t;
    rth_error e;
    std::memset(&e, 0, sizeof(e));
    const long long live_before = g_live;
    g_countdown = n;
    g_tripped = false;
    g_armed = true;
    rth_status st = RTH_OK;
    bool escaped = false;
    try {
      st = rth_cover_from_encoded(c, &b, png.data(), png.size(), &request, nullptr, &t.t, &e);
    } catch (...) {
      escaped = true;
    }
    const bool tripped = g_tripped;
    g_armed = false;
    if (!tripped) {
      covered = true;
      rth_cache_close(c);
      break;
    }
    ++points;
    const bool reported = !escaped && (st == RTH_MEMORY || st == RTH_IO);
    const bool empty_output = t.t.pixels == nullptr && t.t.width == 0 && t.t.height == 0 && t.t.origin == RTH_ORIGIN_NONE && t.t.stride == 0;
    const bool no_leak = g_live == live_before;
    const bool clean_disk = count_entries(dir) == 0 && count_temps(dir) == 0;
    if (!reported || !empty_output || !no_leak || !clean_disk) {
      all_ok = false;
      bad = "n=" + num(n) + " status=" + num((long long)st) + " escaped=" + num((long long)escaped) + " live " + num(live_before) + "->" + num(g_live) +
            " entries=" + num((long long)count_entries(dir)) + " temps=" + num((long long)count_temps(dir)) + " msg=" + e.message;
      rth_cache_close(c);
      break;
    }
    Thumb retry;
    const rth_status st2 = rth_cover_from_encoded(c, &b, png.data(), png.size(), &request, nullptr, &retry.t, &e);
    Thumb again;
    const rth_status st3 = rth_cover_from_encoded(c, &b, png.data(), png.size(), &request, nullptr, &again.t, &e);
    if (st2 != RTH_OK || !retry.t.pixels || retry.t.stored != 1 || st3 != RTH_OK || again.t.from_cache != 1) {
      all_ok = false;
      bad = "retry failed at n=" + num(n) + " status " + num((long long)st2) + "/" + num((long long)st3);
      rth_cache_close(c);
      break;
    }
    rth_cache_close(c);
  }
  check("fault: an allocation failure after the thumbnail bytes exist reports a status with no output, loses no memory and the cache stores on retry",
        all_ok && covered && points > 0, all_ok ? "points " + num(points) : bad);
}

// Every allocation point of the borrowed-blob path: the blob and the decoded bitmap
// must be released, the output box empty and the cache/library usable afterwards.
void sweep_library(const fs::path& root, const Bytes& epub) {
  fs::path dir = root / "library";
  fs::remove_all(dir);
  rth_cache* c = open_or_die(dir.u8string());
  fs::path store = dir / "library.db";
  exr_library* lib = nullptr;
  exr_error e;
  std::memset(&e, 0, sizeof(e));
  if (exr_library_open(store.u8string().c_str(), &lib, &e) != EXR_OK || !lib) fatal(std::string("library open: ") + e.message);
  int64_t id = 0;
  if (exr_library_import(lib, EXR_EPUB, epub.data(), epub.size(), "cover", &id, &e) != EXR_OK) fatal(std::string("import: ") + e.message);
  const rth_book b = mk_book((int)EXR_EPUB, sha_of(epub));
  rth_request request = rth_request_defaults();
  request.width = 64;
  request.height = 64;
  bool all_ok = true, covered = false;
  long long points = 0;
  std::string bad;
  for (long long n = 1; n <= 8192 && all_ok; ++n) {
    Thumb t;
    std::memset(&e, 0, sizeof(e));
    const long long live_before = g_live;
    g_countdown = n;
    g_tripped = false;
    g_armed = true;
    rth_status st = RTH_OK;
    bool escaped = false;
    try {
      st = rth_cover_from_library(c, lib, id, &b, &request, nullptr, &t.t, &e);
    } catch (...) {
      escaped = true;
    }
    const bool tripped = g_tripped;
    g_armed = false;
    if (!tripped) {
      covered = true;
      break;
    }
    ++points;
    const bool reported = !escaped && (st == RTH_MEMORY || st == RTH_IO || st == RTH_SDK);
    const bool empty_output = t.t.pixels == nullptr && t.t.width == 0 && t.t.origin == RTH_ORIGIN_NONE;
    const bool no_leak = g_live == live_before;
    if (!reported || !empty_output || !no_leak) {
      all_ok = false;
      bad = "n=" + num(n) + " status=" + num((long long)st) + " escaped=" + num((long long)escaped) + " live " + num(live_before) + "->" + num(g_live) +
            " msg=" + e.message;
      break;
    }
  }
  Thumb usable;
  std::memset(&e, 0, sizeof(e));
  const rth_status st = rth_cover_from_library(c, lib, id, &b, &request, nullptr, &usable.t, &e);
  const bool still_usable = st == RTH_OK && usable.t.pixels != nullptr && usable.t.origin == RTH_ORIGIN_AUTHOR_COVER;
  check("fault: an allocation failure on the library cover path frees the borrowed blob and leaves the cache usable",
        all_ok && covered && points > 0 && still_usable, all_ok ? (still_usable ? "points " + num(points) : "library unusable afterwards") : bad);
  exr_library_close(lib);
  rth_cache_close(c);
}

}  // namespace

void* operator new(std::size_t size) {
  if (trip()) throw std::bad_alloc();
  void* p = std::malloc(size ? size : 1);
  if (!p) throw std::bad_alloc();
  ++g_live;
  return p;
}
void* operator new[](std::size_t size) { return ::operator new(size); }
void operator delete(void* p) noexcept {
  if (p) {
    --g_live;
    std::free(p);
  }
}
void operator delete(void* p, std::size_t) noexcept { ::operator delete(p); }
void operator delete[](void* p) noexcept { ::operator delete(p); }
void operator delete[](void* p, std::size_t) noexcept { ::operator delete(p); }
void* operator new(std::size_t size, const std::nothrow_t&) noexcept {
  try {
    return ::operator new(size);
  } catch (...) {
    return nullptr;
  }
}
void* operator new[](std::size_t size, const std::nothrow_t&) noexcept {
  try {
    return ::operator new(size);
  } catch (...) {
    return nullptr;
  }
}
void operator delete(void* p, const std::nothrow_t&) noexcept { ::operator delete(p); }
void operator delete[](void* p, const std::nothrow_t&) noexcept { ::operator delete(p); }

int main(int argc, char** argv) {
  std::string mode;
  fs::path work;
  fs::path fixtures;
  fs::path repo;
  for (int i = 1; i + 1 < argc; i += 2) {
    const std::string k = argv[i];
    if (k == "--mode") mode = argv[i + 1];
    else if (k == "--work") work = argv[i + 1];
    else if (k == "--fixtures") fixtures = argv[i + 1];
    else if (k == "--repo-fixtures") repo = argv[i + 1];
  }
  if (mode.empty() || work.empty() || fixtures.empty()) fatal("usage: --mode open|store|library --work DIR --fixtures DIR [--repo-fixtures DIR]");
  fs::create_directories(work);
  const Bytes png = read_file(fixtures / "grad16x8.png");
  if (mode == "open") {
    sweep_open(work);
  } else if (mode == "store") {
    sweep_store(work, png);
  } else if (mode == "library") {
    const Bytes epub = read_file(repo.empty() ? fixtures / "cover-import.epub" : repo / "cover-import.epub");
    sweep_library(work, epub);
  } else {
    fatal("unknown mode " + mode);
  }
  size_t failures = 0;
  for (const Result& r : results) if (!r.pass) ++failures;
  std::printf("checks=%zu failures=%zu mode=%s\n", results.size(), failures, mode.c_str());
  std::fflush(stdout);
  return failures == 0 ? 0 : 1;
}
