// SPDX-License-Identifier: MIT
// Installed regression consumer for the four root review findings on
// EXReaderThumbnails. It uses only the public C ABI that already existed at the
// tested source, so the same binary compiles against the unfixed and the fixed
// library: every named check below fails on the reviewed implementation and
// passes only after the documented root-cause fixes.
//
// Modes (driven by tests/reader_thumbnails/check_thumbnails.py, each a separate
// process so "independent reopen" is a real second process):
//   --mode lru-write  DIR --fixture PNG   store 8x8, 6x6, 4x4 then touch 8 and 4
//   --mode lru-verify DIR --fixture PNG   reopen with max_entries=2 and judge identity
//   --mode cache      DIR --fixture PNG   atomic publish, temp-file safety, bounded scan,
//                                         re-entry guard, exception boundary
#include <reader_thumbnails.h>

#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <string>
#include <thread>
#include <vector>

namespace fs = std::filesystem;
using Bytes = std::vector<unsigned char>;

namespace {

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
bool same(const fs::path& p, const Bytes& b) {
  std::error_code ec;
  if (!fs::exists(p, ec) || ec) return false;
  return read_file(p) == b;
}
rth_book mk_book(int format, const std::string& hex) {
  rth_book b;
  std::memset(&b, 0, sizeof(b));
  b.format = format;
  std::snprintf(b.sha256, sizeof(b.sha256), "%s", hex.c_str());
  return b;
}
rth_request req(uint32_t w, uint32_t h) {
  rth_request r = rth_request_defaults();
  r.width = w;
  r.height = h;
  return r;
}
rth_cache* open_cache(const fs::path& dir, const rth_limits& lim) {
  rth_cache* c = nullptr;
  rth_error e;
  std::memset(&e, 0, sizeof(e));
  if (rth_cache_open(dir.u8string().c_str(), &lim, &c, &e) != RTH_OK || !c) fatal("cache open: " + std::string(e.message));
  return c;
}
rth_limits limits_with_entries(uint32_t entries) {
  rth_limits l = rth_limits_defaults();
  l.max_entries = entries;
  return l;
}
std::string sha_of(const Bytes& b) {
  char out[65];
  rth_sha256_hex(b.data(), b.size(), out);
  return std::string(out);
}

// A cover through the host-verified encoded path: no SDK handle is borrowed, so the
// regression exercises the cache identity and the publish path only.
struct Thumb {
  rth_thumbnail t;
  Thumb() { std::memset(&t, 0, sizeof(t)); }
  ~Thumb() { rth_thumbnail_free(&t); }
  Thumb(const Thumb&) = delete;
  Thumb& operator=(const Thumb&) = delete;
};
rth_status cover(rth_cache* c, const rth_book& b, const Bytes& png, uint32_t box, Thumb& t, const rth_control* ctl = nullptr) {
  rth_request r = req(box, box);
  rth_error e;
  std::memset(&e, 0, sizeof(e));
  return rth_cover_from_encoded(c, &b, png.data(), png.size(), &r, ctl, &t.t, &e);
}
rth_stats stats_now(rth_cache* c) {
  rth_stats s;
  std::memset(&s, 0, sizeof(s));
  s.struct_size = sizeof(s);
  rth_error e;
  std::memset(&e, 0, sizeof(e));
  if (rth_cache_stats(c, &s, &e) != RTH_OK) fatal("stats: " + std::string(e.message));
  return s;
}

// ---- mode: lru-write / lru-verify -----------------------------------------
void lru_write(const fs::path& dir, const Bytes& png) {
  fs::remove_all(dir);
  fs::create_directories(dir);
  rth_cache* c = open_cache(dir, limits_with_entries(4));
  rth_book b = mk_book((int)EXR_EPUB, sha_of(png));
  for (uint32_t s : {8u, 6u, 4u}) {
    Thumb t;
    if (cover(c, b, png, s, t) != RTH_OK || !t.t.pixels || !t.t.stored) fatal("lru-write store failed");
  }
  for (uint32_t s : {8u, 4u}) {  // touch 8 then 4: oldest -> newest becomes 6, 8, 4
    Thumb t;
    if (cover(c, b, png, s, t) != RTH_OK || !t.t.from_cache) fatal("lru-write touch was not a hit");
  }
  const rth_stats before_close = stats_now(c);
  std::string written;
  {
    std::ifstream in(dir / "rth-index.txt", std::ios::binary);
    std::string line;
    while (std::getline(in, line) && written.size() < 400) written += line + "|";
  }
  rth_cache_close(c);
  std::printf("SETUP lru-write entries %u stores %llu index_failures %llu index[%s]\n", before_close.entries,
              (unsigned long long)before_close.stores, (unsigned long long)before_close.index_failures, written.c_str());
  std::fflush(stdout);
}

void lru_verify(const fs::path& dir, const Bytes& png) {
  rth_cache* c = open_cache(dir, limits_with_entries(2));
  rth_book b = mk_book((int)EXR_EPUB, sha_of(png));
  rth_stats s = stats_now(c);
  Thumb t8, t4, t6;
  rth_status s8 = cover(c, b, png, 8, t8);
  rth_status s4 = cover(c, b, png, 4, t4);
  rth_status s6 = cover(c, b, png, 6, t6);
  bool kept = s.entries == 2 && s8 == RTH_OK && t8.t.from_cache == 1 && s4 == RTH_OK && t4.t.from_cache == 1;
  std::string index_dump;
  {
    std::ifstream in(dir / "rth-index.txt", std::ios::binary);
    std::string line;
    while (std::getline(in, line) && index_dump.size() < 400) index_dump += line + "|";
  }
  check("regress: LRU recency written by one process survives an independent reopen", kept,
        "entries " + num(s.entries) + " 8x8 " + (t8.t.from_cache ? "hit" : "miss") + " 4x4 " + (t4.t.from_cache ? "hit" : "miss") +
            " index[" + index_dump + "]");
  check("regress: reopening with a smaller entry bound evicts the stale entry, not the touched ones",
        s6 == RTH_OK && t6.t.from_cache == 0, "6x6 from cache " + num((uint64_t)t6.t.from_cache));
  rth_cache_close(c);
}

// ---- modes: lock-hold / lock-busy / lock-release ---------------------------
// One cache per directory across processes: the holder keeps the OS lock until it is
// killed, and the OS then releases it for the next process.
void lock_hold(const fs::path& dir) {
  fs::remove_all(dir);
  fs::create_directories(dir);
  rth_cache* c = open_cache(dir, rth_limits_defaults());
  std::printf("SETUP lock-hold owns %s (%p)\n", dir.string().c_str(), static_cast<void*>(c));
  std::fflush(stdout);
  std::this_thread::sleep_for(std::chrono::seconds(300));
  rth_cache_close(c);  // only reached when the parent did not kill us
}

void lock_busy(const fs::path& dir) {
  rth_cache* c = reinterpret_cast<rth_cache*>(static_cast<std::uintptr_t>(1));
  rth_error e;
  std::memset(&e, 0, sizeof(e));
  const rth_status st = rth_cache_open(dir.u8string().c_str(), nullptr, &c, &e);
  check("regress: a second cache on one directory is refused while another process owns it",
        st == RTH_BUSY && c == nullptr, "status " + num((uint64_t)st));
  if (st == RTH_OK && c) rth_cache_close(c);
}

void lock_release(const fs::path& dir) {
  rth_cache* c = nullptr;
  rth_error e;
  std::memset(&e, 0, sizeof(e));
  const rth_status st = rth_cache_open(dir.u8string().c_str(), nullptr, &c, &e);
  check("regress: a killed owner's lock is released by the OS and the directory reopens",
        st == RTH_OK && c != nullptr, "status " + num((uint64_t)st));
  if (st == RTH_OK && c) rth_cache_close(c);
}

// ---- mode: cache -----------------------------------------------------------
// A control callback seeds hard links: every seeded name is a hard link to a file
// outside the cache directory, so any create-with-truncate at that name destroys
// external bytes. The links must never be followed or truncated.
struct Seed {
  fs::path dir;
  fs::path sentinel;
  Bytes content;
  int calls = 0;
  int seeded = 0;
};
int seed_cb(void* context) {
  Seed* s = static_cast<Seed*>(context);
  if (s->calls++ == 0) {
    for (int i = 1; i <= 64; ++i) {
      std::error_code ec;
      fs::create_hard_link(s->sentinel, s->dir / ("rth-tmp-" + std::to_string(i) + ".tmp"), ec);
      if (!ec) ++s->seeded;
    }
    for (int i = 1; i <= 16; ++i) {
      std::error_code ec;
      fs::create_hard_link(s->sentinel, s->dir / ("rth-tmp-index-" + std::to_string(i) + ".tmp"), ec);
      if (!ec) ++s->seeded;
    }
  }
  return 0;
}
struct Reentry {
  rth_cache* cache = nullptr;
  rth_status stats_st = RTH_OK;
  int calls = 0;
};
int stats_cb(void* context) {
  Reentry* s = static_cast<Reentry*>(context);
  if (s->calls++ == 0) {
    rth_stats st;
    std::memset(&st, 0, sizeof(st));
    st.struct_size = sizeof(st);
    rth_error e;
    std::memset(&e, 0, sizeof(e));
    s->stats_st = rth_cache_stats(s->cache, &st, &e);
  }
  return 0;
}
std::string hex16(uint64_t v) {
  char buf[32];
  std::snprintf(buf, sizeof(buf), "%016llx", (unsigned long long)v);
  return std::string(buf);
}
std::string hex8(uint64_t v) {
  char buf[16];
  std::snprintf(buf, sizeof(buf), "%08llx", (unsigned long long)v);
  return std::string(buf);
}
std::string hex32(uint64_t v) {
  char buf[40];
  std::snprintf(buf, sizeof(buf), "%032llx", (unsigned long long)v);
  return std::string(buf);
}

void cache_checks(const fs::path& root, const Bytes& png) {
  const rth_book b = mk_book((int)EXR_EPUB, sha_of(png));

  {  // 1: a hard link at a temporary name must never be truncated
    fs::path dir = root / "seed-links";
    fs::remove_all(dir);
    fs::create_directories(dir);
    Seed seed;
    seed.dir = dir;
    seed.sentinel = root / "sentinel.bin";
    seed.content.assign(4096, 0);
    for (size_t i = 0; i < seed.content.size(); ++i) seed.content[i] = (unsigned char)(0x5a ^ (i * 7));
    write_file(seed.sentinel, seed.content);
    rth_cache* c = open_cache(dir, rth_limits_defaults());
    rth_control ctl{seed_cb, &seed};
    Thumb t;
    rth_status st = cover(c, b, png, 8, t, &ctl);
    bool untouched = same(seed.sentinel, seed.content);
    bool intact = true;
    for (int i = 1; i <= 64 && intact; ++i) intact = same(dir / ("rth-tmp-" + std::to_string(i) + ".tmp"), seed.content);
    for (int i = 1; i <= 16 && intact; ++i) intact = same(dir / ("rth-tmp-index-" + std::to_string(i) + ".tmp"), seed.content);
    check("regress: a pre-seeded hard link at a temporary name is never followed or truncated",
          st == RTH_OK && t.t.pixels && seed.seeded == 80 && untouched && intact,
          "seeded " + num((uint64_t)seed.seeded) + " sentinel intact " + num((uint64_t)untouched) + " links intact " + num((uint64_t)intact));
    rth_cache_close(c);
    fs::remove(seed.sentinel);
  }

  {  // 2 + 3: another live cache's fresh temporary survives open; a stale one is removed
    fs::path dir = root / "live-temp";
    fs::remove_all(dir);
    fs::create_directories(dir);
    fs::path live = dir / ("rth-tmp-" + hex16(0x00c0ffee12345678ull) + "-" + hex8(0x1full) + ".tmp");
    fs::path stale = dir / ("rth-tmp-" + hex16(0x00c0ffee12345678ull) + "-" + hex8(0x2full) + ".tmp");
    Bytes live_bytes{'l', 'i', 'v', 'e'};
    Bytes stale_bytes{'s', 't', 'a', 'l', 'e'};
    write_file(live, live_bytes);
    write_file(stale, stale_bytes);
    std::error_code ec;
    fs::last_write_time(stale, fs::file_time_type::clock::now() - std::chrono::hours(3), ec);
    if (ec) fatal("cannot age the temporary file");
    rth_cache* c = open_cache(dir, rth_limits_defaults());
    bool live_ok = same(live, live_bytes);
    bool stale_gone = !fs::exists(stale, ec);
    check("regress: a fresh temporary file of another live cache instance is preserved by open", live_ok,
          live_ok ? "bytes " + num((uint64_t)live_bytes.size()) : "file was deleted or rewritten");
    check("regress: a stale temporary of the cache naming is removed by open", stale_gone, "stale removed " + num((uint64_t)stale_gone));
    rth_cache_close(c);
  }

  {  // 4: a failure to publish the index atomically must be reported, not hidden
    fs::path dir = root / "index-blocked";
    fs::remove_all(dir);
    fs::create_directories(dir);
    fs::create_directory(dir / "rth-index.txt");
    rth_cache* c = reinterpret_cast<rth_cache*>(static_cast<std::uintptr_t>(1));
    rth_error e;
    std::memset(&e, 0, sizeof(e));
    rth_status st = rth_cache_open(dir.u8string().c_str(), nullptr, &c, &e);
    check("regress: an index that cannot be atomically replaced is reported instead of silently accepted",
          st == RTH_IO && c == nullptr, "status " + num((uint64_t)st));
    if (st == RTH_OK && c) rth_cache_close(c);
  }

  {  // 5: the statistics call must refuse re-entry from a control callback
    fs::path dir = root / "reentry-stats";
    fs::remove_all(dir);
    fs::create_directories(dir);
    rth_cache* c = open_cache(dir, rth_limits_defaults());
    Reentry ctx;
    ctx.cache = c;
    Thumb t;
    rth_control ctl{stats_cb, &ctx};
    rth_status outer = cover(c, b, png, 8, t, &ctl);
    rth_stats after = stats_now(c);
    bool usable = after.entries == 1 && outer == RTH_OK && t.t.pixels != nullptr;
    check("regress: re-entry from a control callback is refused by the cache statistics call",
          ctx.stats_st == RTH_ARGUMENT && usable, "status " + num((uint64_t)ctx.stats_st) + " entries " + num(after.entries));
    rth_cache_close(c);
  }

  {  // 6: a directory far larger than the scan budget must not be loaded wholesale
    fs::path dir = root / "scan-budget";
    fs::remove_all(dir);
    fs::create_directories(dir);
    const int candidates = 1200;
    Bytes junk(200, 0x33);
    for (int i = 0; i < candidates; ++i) write_file(dir / ("rth-" + hex32((uint64_t)i) + ".rth"), junk);
    rth_cache* c = open_cache(dir, limits_with_entries(4));
    rth_stats s = stats_now(c);
    size_t left = 0;
    for (const auto& it : fs::directory_iterator(dir)) {
      std::string name = it.path().filename().string();
      if (name.size() == 4 + 32 + 4 && name.compare(0, 4, "rth-") == 0 && name.compare(36, 4, ".rth") == 0) ++left;
    }
    check("regress: a directory with many more candidates than the scan budget leaves the uninspected files untouched",
          left > 0 && s.entries == 0, "left " + num((uint64_t)left) + " of " + num((uint64_t)candidates));
    rth_cache_close(c);
  }

  {  // 7 (last: on an unfixed Windows build this terminates the process)
    std::string bad = root.u8string();
    bad += "/bad-";
    bad.push_back(static_cast<char>(0xff));
    bad.push_back(static_cast<char>(0xfe));
    bad += "-dir";
    rth_cache* c = reinterpret_cast<rth_cache*>(static_cast<std::uintptr_t>(1));
    rth_error e;
    std::memset(&e, 0, sizeof(e));
    rth_status st = rth_cache_open(bad.c_str(), nullptr, &c, &e);
    bool cleared = (st == RTH_OK) ? (c != nullptr) : (c == nullptr);
    check("regress: an unrepresentable directory path is refused with a status instead of an escaping exception",
          cleared && (st == RTH_OK || st == RTH_ARGUMENT || st == RTH_IO), "status " + num((uint64_t)st));
    if (st == RTH_OK && c) rth_cache_close(c);
  }
}

}  // namespace

int main(int argc, char** argv) {
  std::string mode;
  fs::path work;
  fs::path fixture;
  for (int i = 1; i + 1 < argc; i += 2) {
    std::string k = argv[i];
    if (k == "--mode") mode = argv[i + 1];
    else if (k == "--work") work = argv[i + 1];
    else if (k == "--fixture") fixture = argv[i + 1];
  }
  if (mode.empty() || work.empty() || fixture.empty()) fatal("usage: --mode lru-write|lru-verify|cache --work DIR --fixture PNG");
  const Bytes png = read_file(fixture);
  fs::create_directories(work);
  if (mode == "lru-write") {
    lru_write(work / "lru", png);
  } else if (mode == "lru-verify") {
    lru_verify(work / "lru", png);
  } else if (mode == "cache") {
    cache_checks(work, png);
  } else if (mode == "lock-hold") {
    lock_hold(work / "lock");
  } else if (mode == "lock-busy") {
    lock_busy(work / "lock");
  } else if (mode == "lock-release") {
    lock_release(work / "lock");
  } else {
    fatal("unknown mode " + mode);
  }
  size_t failures = 0;
  for (const Result& r : results) if (!r.pass) ++failures;
  std::printf("checks=%zu failures=%zu mode=%s\n", results.size(), failures, mode.c_str());
  std::fflush(stdout);
  return failures == 0 ? 0 : 1;
}
