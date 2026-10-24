// SPDX-License-Identifier: MIT
// Installed fault-injection consumer for EXReaderThumbnails. It replaces the global
// operator new/delete inside its own binary only (no production hook, no public API
// change), makes the n-th allocation of one operation throw std::bad_alloc, and counts
// live allocations so a failed call can be shown to leak nothing: not the cache, not the
// borrowed SDK blob, not the thumbnail pixels, not a temporary file.
//
// Every allocation point runs in its own child process: the standard library declares
// parts of <filesystem> noexcept, so an injected failure there aborts instead of
// unwinding. A child that dies that way reports TERMINATE through its terminate handler;
// the driver counts those points separately and bounded, and every other point must
// pass its assertions.
//
//   --mode open|store|library  DIR FIXTURES [--repo-fixtures DIR]   driver
//   --mode ... --n K --report FILE                                  one point (child)
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

#ifndef _WIN32
#include <sys/wait.h>
#endif

namespace fs = std::filesystem;
using Bytes = std::vector<unsigned char>;

namespace {

bool g_armed = false;
long long g_countdown = 0;
long long g_live = 0;
bool g_tripped = false;
const char* g_step = "none";
long long g_last_n = 0;
FILE* g_report = nullptr;

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

void report(const std::string& text) {
  if (!g_report) return;
  std::fputs(text.c_str(), g_report);
  std::fputc('\n', g_report);
  std::fflush(g_report);
}

// A throw from a noexcept context aborts instead of unwinding: record it without
// allocating so the driver can tell that boundary from a real failure.
void on_terminate() {
  if (g_report) {
    std::fprintf(g_report, "TERMINATE step=%s n=%lld armed=%d countdown=%lld live=%lld tripped=%d\n", g_step, g_last_n,
                 (int)g_armed, g_countdown, g_live, (int)g_tripped);
    std::fflush(g_report);
  }
  std::_Exit(3);
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
rth_stats stats_now(rth_cache* c) {
  rth_stats s;
  std::memset(&s, 0, sizeof(s));
  s.struct_size = sizeof(s);
  rth_error e;
  std::memset(&e, 0, sizeof(e));
  rth_cache_stats(c, &s, &e);
  return s;
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

// ---- one allocation point per child ---------------------------------------
const char* kOpenCheck = "fault: an allocation failure inside open reports a status, clears the output and leaks nothing";
const char* kStoreCheck =
    "fault: an allocation failure after the thumbnail bytes exist reports a status with no output, loses no memory and the cache stores on retry";
const char* kLibraryCheck =
    "fault: an allocation failure on the library cover path frees the borrowed blob and leaves the cache usable";

int point_open(const fs::path& root, long long n) {
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
    if (c) rth_cache_close(c);
    report("NOFAIL");
    return 0;
  }
  const bool reported = !escaped && (st == RTH_MEMORY || st == RTH_IO) && c == nullptr;
  const bool no_leak = g_live == live_before;
  if (!reported || !no_leak) {
    report("FAIL n=" + num(n) + " status=" + num((long long)st) + " escaped=" + num((long long)escaped) + " live " + num(live_before) +
           "->" + num(g_live) + " msg=" + e.message);
    if (c) rth_cache_close(c);
    return 1;
  }
  rth_cache* again = nullptr;
  std::memset(&e, 0, sizeof(e));
  if (rth_cache_open(text.c_str(), nullptr, &again, &e) != RTH_OK || !again) {
    report("FAIL n=" + num(n) + " retry failed msg=" + e.message);
    return 1;
  }
  rth_cache_close(again);
  report("PASS n=" + num(n));
  return 0;
}

int point_store(const fs::path& root, const Bytes& png, long long n) {
  fs::path dir = root / ("store-" + std::to_string(n));
  fs::remove_all(dir);
  const rth_book b = mk_book((int)EXR_EPUB, sha_of(png));
  rth_request request = rth_request_defaults();
  request.width = 8;
  request.height = 8;
  const std::string text = dir.u8string();
  rth_cache* c = nullptr;
  rth_error e;
  std::memset(&e, 0, sizeof(e));
  if (rth_cache_open(text.c_str(), nullptr, &c, &e) != RTH_OK || !c) fatal("cache open: " + std::string(e.message));
  Thumb t;
  const rth_stats before_stats = stats_now(c);
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
    rth_cache_close(c);
    report("NOFAIL");
    return 0;
  }
  if (!escaped && st == RTH_OK) {
    // Only the best-effort index publication is reported instead of thrown: the entry
    // must still be published, complete and counted, and served from the file.
    const rth_stats after = stats_now(c);
    Thumb hit;
    const rth_status st3 = rth_cover_from_encoded(c, &b, png.data(), png.size(), &request, nullptr, &hit.t, &e);
    const bool index_only = t.t.pixels != nullptr && t.t.stored == 1 && t.t.origin == RTH_ORIGIN_AUTHOR_COVER &&
                            after.index_failures == before_stats.index_failures + 1 && count_entries(dir) == 1 &&
                            count_temps(dir) == 0 && st3 == RTH_OK && hit.t.from_cache == 1;
    rth_cache_close(c);
    if (!index_only) {
      report("FAIL n=" + num(n) + " index point: entry or index accounting differs");
      return 1;
    }
    report("PASS n=" + num(n) + " index");
    return 0;
  }
  const bool reported = !escaped && (st == RTH_MEMORY || st == RTH_IO);
  const bool empty_output =
      t.t.pixels == nullptr && t.t.width == 0 && t.t.height == 0 && t.t.origin == RTH_ORIGIN_NONE && t.t.stride == 0;
  const bool no_leak = g_live == live_before;
  const bool clean_disk = count_entries(dir) == 0 && count_temps(dir) == 0;
  if (!reported || !empty_output || !no_leak || !clean_disk) {
    const rth_stats now = stats_now(c);
    const std::string detail = "FAIL n=" + num(n) + " status=" + num((long long)st) + " escaped=" + num((long long)escaped) +
                               " live " + num(live_before) + "->" + num(g_live) + " entries=" + num((long long)count_entries(dir)) +
                               " temps=" + num((long long)count_temps(dir)) + " decoded=" + num((long long)now.last_decoded_bytes) +
                               " stores=" + num((long long)now.stores) + " store_failures=" + num((long long)now.store_failures) +
                               " index_failures=" + num((long long)now.index_failures) + " map_bytes=" + num((long long)now.bytes) +
                               " msg=" + e.message;
    rth_cache_close(c);
    report(detail);
    return 1;
  }
  Thumb retry;
  const rth_status st2 = rth_cover_from_encoded(c, &b, png.data(), png.size(), &request, nullptr, &retry.t, &e);
  Thumb again;
  const rth_status st3 = rth_cover_from_encoded(c, &b, png.data(), png.size(), &request, nullptr, &again.t, &e);
  const bool retried = st2 == RTH_OK && retry.t.pixels != nullptr && retry.t.stored == 1 && st3 == RTH_OK && again.t.from_cache == 1;
  rth_cache_close(c);
  if (!retried) {
    report("FAIL n=" + num(n) + " retry failed " + num((long long)st2) + "/" + num((long long)st3));
    return 1;
  }
  report("PASS n=" + num(n));
  return 0;
}

int point_library(const fs::path& root, const Bytes& epub, long long n) {
  fs::path dir = root / "library";
  fs::remove_all(dir);
  const std::string text = dir.u8string();
  rth_cache* c = nullptr;
  rth_error re;
  std::memset(&re, 0, sizeof(re));
  if (rth_cache_open(text.c_str(), nullptr, &c, &re) != RTH_OK || !c) fatal("cache open: " + std::string(re.message));
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
  rth_cache_clear(c, &re);  // every point starts from an empty cache so it reaches the store
  Thumb t;
  std::memset(&re, 0, sizeof(re));
  const rth_stats before_stats = stats_now(c);
  const long long live_before = g_live;
  g_countdown = n;
  g_tripped = false;
  g_armed = true;
  rth_status st = RTH_OK;
  bool escaped = false;
  try {
    st = rth_cover_from_library(c, lib, id, &b, &request, nullptr, &t.t, &re);
  } catch (...) {
    escaped = true;
  }
  const bool tripped = g_tripped;
  g_armed = false;
  if (!tripped) {
    exr_library_close(lib);
    rth_cache_close(c);
    report("NOFAIL");
    return 0;
  }
  if (!escaped && st == RTH_OK) {
    const rth_stats after = stats_now(c);
    const bool index_only = t.t.pixels != nullptr && t.t.origin == RTH_ORIGIN_AUTHOR_COVER && t.t.stored == 1 &&
                            after.index_failures == before_stats.index_failures + 1;
    exr_library_close(lib);
    rth_cache_close(c);
    if (!index_only) {
      report("FAIL n=" + num(n) + " index point: entry or index accounting differs");
      return 1;
    }
    report("PASS n=" + num(n) + " index");
    return 0;
  }
  const bool reported = !escaped && (st == RTH_MEMORY || st == RTH_IO || st == RTH_SDK);
  const bool empty_output = t.t.pixels == nullptr && t.t.width == 0 && t.t.origin == RTH_ORIGIN_NONE;
  const bool no_leak = g_live == live_before;
  exr_library_close(lib);
  rth_cache_close(c);
  if (!reported || !empty_output || !no_leak) {
    report("FAIL n=" + num(n) + " status=" + num((long long)st) + " escaped=" + num((long long)escaped) + " live " + num(live_before) +
           "->" + num(g_live) + " msg=" + re.message);
    return 1;
  }
  report("PASS n=" + num(n));
  return 0;
}

std::string quote(const std::string& s) { return "\"" + s + "\""; }

int exit_code(int status) {
#ifdef _WIN32
  return status;  // system() returns the child's exit code
#else
  if (status == -1) return -1;
  if (WIFEXITED(status)) return WEXITSTATUS(status);
  if (WIFSIGNALED(status)) return 128 + WTERMSIG(status);
  return -1;
#endif
}

int drive(const std::string& self, const std::string& mode, const fs::path& work, const fs::path& fixtures,
          const fs::path& repo) {
  long long points = 0, boundaries = 0, n = 0;
  bool finished = false;
  std::string bad;
  for (n = 1; n <= 4096 && bad.empty(); ++n) {
    const fs::path rep = work / ("point-" + std::to_string(n) + ".txt");
    std::error_code ec;
    fs::remove(rep, ec);
    std::string cmd = quote(self) + " --mode " + mode + " --n " + std::to_string(n) + " --work " + quote(work.u8string()) +
                      " --fixtures " + quote(fixtures.u8string());
    if (!repo.empty()) cmd += " --repo-fixtures " + quote(repo.u8string());
    cmd += " --report " + quote(rep.u8string());
    const int code = exit_code(std::system(cmd.c_str()));
    std::string text;
    {
      std::ifstream in(rep);
      std::string line;
      while (std::getline(in, line)) text += line + "\n";
    }
    if (text.rfind("NOFAIL", 0) == 0) {
      finished = true;
      break;
    }
    if (text.rfind("PASS", 0) == 0 && code == 0) {
      ++points;
      continue;
    }
    if (text.rfind("TERMINATE", 0) == 0 && (code == 3 || code == 134)) {
      ++boundaries;  // an allocation inside a noexcept <filesystem> shim, not our code
      continue;
    }
    bad = "n=" + std::to_string(n) + " exit=" + std::to_string(code) + " " + text.substr(0, 220);
  }
  const std::string detail = (bad.empty() ? "points " + std::to_string(points) + " noexcept boundaries " + std::to_string(boundaries)
                                          : bad);
  const bool ok = bad.empty() && finished && points > 0 && boundaries <= 12;
  const char* name = mode == "open" ? kOpenCheck : (mode == "store" ? kStoreCheck : kLibraryCheck);
  check(name, ok, detail);
  size_t failures = 0;
  for (const Result& r : results) if (!r.pass) ++failures;
  std::printf("checks=%zu failures=%zu mode=%s\n", results.size(), failures, mode.c_str());
  std::fflush(stdout);
  return failures == 0 ? 0 : 1;
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
  fs::path report_path;
  long long point = 0;
  for (int i = 1; i + 1 < argc; i += 2) {
    const std::string k = argv[i];
    if (k == "--mode") mode = argv[i + 1];
    else if (k == "--work") work = argv[i + 1];
    else if (k == "--fixtures") fixtures = argv[i + 1];
    else if (k == "--repo-fixtures") repo = argv[i + 1];
    else if (k == "--n") point = std::atoll(argv[i + 1]);
    else if (k == "--report") report_path = argv[i + 1];
  }
  if (mode.empty() || work.empty() || fixtures.empty()) fatal("usage: --mode open|store|library --work DIR --fixtures DIR [--n K --report FILE]");
  fs::create_directories(work);
  std::set_terminate(on_terminate);
  if (!report_path.empty()) {
    g_report = std::fopen(report_path.u8string().c_str(), "wb");
    if (!g_report) fatal("cannot open the report file");
  }
  if (point > 0) {
    g_step = mode.c_str();
    g_last_n = point;
    if (mode == "open") return point_open(work, point);
    const Bytes png = read_file(fixtures / "grad16x8.png");
    if (mode == "store") return point_store(work, png, point);
    if (mode == "library") {
      const Bytes epub = read_file((repo.empty() ? fixtures : repo) / "cover-import.epub");
      return point_library(work, epub, point);
    }
    fatal("unknown mode " + mode);
  }
  return drive(argv[0], mode, work, fixtures, repo);
}
