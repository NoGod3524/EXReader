// SPDX-License-Identifier: MIT
// EXReaderThumbnails: bounded cover / first-page thumbnails and their LRU cache.
// Single-owner, synchronous, no threads. Only the public SDK API is used.
//
// Cache files are created with exclusive-create semantics and opened without
// following links or reparse points; publication is a same-directory platform
// atomic replace that reports failure. The cache directory is scanned once with a
// bounded candidate budget instead of being collected wholesale.
#include "reader_thumbnails.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <filesystem>
#include <map>
#include <new>
#include <string>
#include <system_error>
#include <thread>
#include <vector>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#else
#include <cerrno>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#endif

namespace fs = std::filesystem;

namespace {

// ---- SHA-256 -------------------------------------------------------------
struct Sha256 {
  uint32_t h[8];
  uint64_t length;
  unsigned char buffer[64];
  size_t fill;
  static uint32_t rotr(uint32_t x, unsigned n) { return (x >> n) | (x << (32u - n)); }
  void init() {
    static const uint32_t iv[8] = {0x6a09e667u, 0xbb67ae85u, 0x3c6ef372u, 0xa54ff53au,
                                   0x510e527fu, 0x9b05688cu, 0x1f83d9abu, 0x5be0cd19u};
    std::memcpy(h, iv, sizeof(h));
    length = 0;
    fill = 0;
  }
  void block(const unsigned char* p) {
    static const uint32_t k[64] = {
        0x428a2f98u, 0x71374491u, 0xb5c0fbcfu, 0xe9b5dba5u, 0x3956c25bu, 0x59f111f1u, 0x923f82a4u, 0xab1c5ed5u,
        0xd807aa98u, 0x12835b01u, 0x243185beu, 0x550c7dc3u, 0x72be5d74u, 0x80deb1feu, 0x9bdc06a7u, 0xc19bf174u,
        0xe49b69c1u, 0xefbe4786u, 0x0fc19dc6u, 0x240ca1ccu, 0x2de92c6fu, 0x4a7484aau, 0x5cb0a9dcu, 0x76f988dau,
        0x983e5152u, 0xa831c66du, 0xb00327c8u, 0xbf597fc7u, 0xc6e00bf3u, 0xd5a79147u, 0x06ca6351u, 0x14292967u,
        0x27b70a85u, 0x2e1b2138u, 0x4d2c6dfcu, 0x53380d13u, 0x650a7354u, 0x766a0abbu, 0x81c2c92eu, 0x92722c85u,
        0xa2bfe8a1u, 0xa81a664bu, 0xc24b8b70u, 0xc76c51a3u, 0xd192e819u, 0xd6990624u, 0xf40e3585u, 0x106aa070u,
        0x19a4c116u, 0x1e376c08u, 0x2748774cu, 0x34b0bcb5u, 0x391c0cb3u, 0x4ed8aa4au, 0x5b9cca4fu, 0x682e6ff3u,
        0x748f82eeu, 0x78a5636fu, 0x84c87814u, 0x8cc70208u, 0x90befffau, 0xa4506cebu, 0xbef9a3f7u, 0xc67178f2u};
    uint32_t w[64];
    for (unsigned i = 0; i < 16; ++i)
      w[i] = (uint32_t)p[i * 4] << 24 | (uint32_t)p[i * 4 + 1] << 16 | (uint32_t)p[i * 4 + 2] << 8 | (uint32_t)p[i * 4 + 3];
    for (unsigned i = 16; i < 64; ++i) {
      uint32_t s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
      uint32_t s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
      w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    uint32_t a = h[0], b = h[1], c = h[2], d = h[3], e = h[4], f = h[5], g = h[6], hh = h[7];
    for (unsigned i = 0; i < 64; ++i) {
      uint32_t s1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
      uint32_t ch = (e & f) ^ (~e & g);
      uint32_t t1 = hh + s1 + ch + k[i] + w[i];
      uint32_t s0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
      uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
      uint32_t t2 = s0 + maj;
      hh = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
    }
    h[0] += a; h[1] += b; h[2] += c; h[3] += d; h[4] += e; h[5] += f; h[6] += g; h[7] += hh;
  }
  void update(const void* data, size_t size) {
    const unsigned char* p = static_cast<const unsigned char*>(data);
    length += size;
    while (size) {
      size_t take = std::min<size_t>(64 - fill, size);
      std::memcpy(buffer + fill, p, take);
      fill += take; p += take; size -= take;
      if (fill == 64) { block(buffer); fill = 0; }
    }
  }
  void finish(unsigned char out[32]) {
    uint64_t bits = length * 8u;
    unsigned char pad = 0x80;
    update(&pad, 1);
    pad = 0;
    while (fill != 56) update(&pad, 1);
    unsigned char tail[8];
    for (unsigned i = 0; i < 8; ++i) tail[i] = (unsigned char)(bits >> (56 - 8 * i));
    update(tail, 8);
    for (unsigned i = 0; i < 8; ++i) {
      out[i * 4] = (unsigned char)(h[i] >> 24); out[i * 4 + 1] = (unsigned char)(h[i] >> 16);
      out[i * 4 + 2] = (unsigned char)(h[i] >> 8); out[i * 4 + 3] = (unsigned char)h[i];
    }
  }
};

std::string hex(const unsigned char* p, size_t n) {
  static const char digits[] = "0123456789abcdef";
  std::string s;
  s.reserve(n * 2);
  for (size_t i = 0; i < n; ++i) { s += digits[p[i] >> 4]; s += digits[p[i] & 15]; }
  return s;
}
std::string sha_hex(const void* data, size_t size) {
  Sha256 s; unsigned char d[32];
  s.init(); s.update(data, size); s.finish(d);
  return hex(d, 32);
}

// ---- errors and status mapping --------------------------------------------
rth_status fail(rth_error* e, rth_status code, int sdk, const char* message) {
  if (e) {
    e->code = code;
    e->sdk_code = sdk;
    std::snprintf(e->message, sizeof(e->message), "%s", message);
  }
  return code;
}
rth_status ok(rth_error* e) { return fail(e, RTH_OK, -1, ""); }
rth_status map_sdk(rth_error* e, exr_status s, const exr_error& sdk, const char* what) {
  rth_status code;
  switch (s) {
    case EXR_OK: return ok(e);
    case EXR_ARGUMENT: code = RTH_ARGUMENT; break;
    case EXR_MEMORY: code = RTH_MEMORY; break;
    case EXR_IO: code = RTH_IO; break;
    case EXR_ENCODING: case EXR_FORMAT: code = RTH_FORMAT; break;
    case EXR_LIMIT: code = RTH_LIMIT; break;
    case EXR_CANCELLED: code = RTH_CANCELLED; break;
    case EXR_PASSWORD: case EXR_UNSUPPORTED: code = RTH_UNSUPPORTED; break;
    default: code = RTH_SDK; break;
  }
  char text[256];
  std::snprintf(text, sizeof(text), "%s: %.180s", what, sdk.message);
  return fail(e, code, (int)s, text);
}

// No exception may cross the C ABI: every public entry point is wrapped.
template <typename Body>
rth_status guarded(rth_error* e, Body&& body) {
  try {
    return body();
  } catch (const std::bad_alloc&) {
    return fail(e, RTH_MEMORY, -1, "Out of memory");
  } catch (const std::exception& ex) {
    return fail(e, RTH_IO, -1, ex.what());
  } catch (...) {
    return fail(e, RTH_IO, -1, "Unexpected failure");
  }
}

struct Poll {
  const rth_control* control;
  bool cancelled;
  bool check() {
    if (!cancelled && control && control->cancelled && control->cancelled(control->context)) cancelled = true;
    return cancelled;
  }
};
int poll_callback(void* context) { return static_cast<Poll*>(context)->check() ? 1 : 0; }

// ---- little-endian helpers --------------------------------------------------
void put32(std::vector<unsigned char>& v, uint32_t x) { for (unsigned i = 0; i < 4; ++i) v.push_back((unsigned char)(x >> (8 * i))); }
void put64(std::vector<unsigned char>& v, uint64_t x) { for (unsigned i = 0; i < 8; ++i) v.push_back((unsigned char)(x >> (8 * i))); }
uint32_t get32(const unsigned char* p) { return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24; }
uint64_t get64(const unsigned char* p) { return (uint64_t)get32(p) | (uint64_t)get32(p + 4) << 32; }

const unsigned char kMagic[8] = {'E', 'X', 'R', 'T', 'H', 'M', 'B', '1'};
const size_t kFixedHeader = 68;  // magic8 hdr4 key4 w4 h4 origin4 payload8 sha32
const size_t kKeyMax = 512;
const char kIndexName[] = "rth-index.txt";
const char kIndexMagic[] = "RTHIDX1";

// Temporary files younger than this grace period are left alone by open: another
// process may be publishing one at that very moment.
const uint64_t kStaleTempSeconds = 600;
// Candidate budget of one bounded directory scan: independent of the directory size.
const uint64_t kScanMinCandidates = 256;
const uint64_t kScanPerEntry = 8;
const uint64_t kScanMaxCandidates = 65536;

struct Header {
  std::string key;
  uint32_t width = 0, height = 0, origin = 0;
  uint64_t payload = 0;
  unsigned char digest[32] = {0};
  size_t body = 0;  // payload offset
};

uint64_t splitmix64(uint64_t x) {
  x += 0x9e3779b97f4a7c15ull;
  x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ull;
  x = (x ^ (x >> 27)) * 0x94d049bb133111ebull;
  return x ^ (x >> 31);
}
uint64_t process_token() {
#ifdef _WIN32
  const uint64_t pid = (uint64_t)::GetCurrentProcessId();
#else
  const uint64_t pid = (uint64_t)::getpid();
#endif
  const uint64_t clock = (uint64_t)std::chrono::steady_clock::now().time_since_epoch().count();
  const uint64_t wall = (uint64_t)std::chrono::system_clock::now().time_since_epoch().count();
  uint64_t stack = 0;
  const uint64_t address = static_cast<uint64_t>(reinterpret_cast<std::uintptr_t>(&stack));
  return splitmix64(pid ^ splitmix64(clock ^ splitmix64(wall ^ splitmix64(address))));
}

// ---- exclusive-create / no-follow file layer -------------------------------
// kind: 0 fine, 1 the name already exists, 2 error.
class WriteHandle {
 public:
  WriteHandle() = default;
  ~WriteHandle() { close(); }
  WriteHandle(const WriteHandle&) = delete;
  WriteHandle& operator=(const WriteHandle&) = delete;
  int open_exclusive(const fs::path& path, std::error_code& ec);
  bool write(const void* data, size_t size, std::error_code& ec);
  bool sync(std::error_code& ec);
  void close();

 private:
#ifdef _WIN32
  HANDLE handle_ = INVALID_HANDLE_VALUE;
#else
  int fd_ = -1;
#endif
};

class ReadHandle {
 public:
  ReadHandle() = default;
  ~ReadHandle() { close(); }
  ReadHandle(const ReadHandle&) = delete;
  ReadHandle& operator=(const ReadHandle&) = delete;
  bool open_regular(const fs::path& path, uint64_t& size, std::error_code& ec);
  bool read(void* data, size_t size, size_t& got, std::error_code& ec);
  void close();

 private:
#ifdef _WIN32
  HANDLE handle_ = INVALID_HANDLE_VALUE;
#else
  int fd_ = -1;
#endif
};

bool atomic_replace(const fs::path& from, const fs::path& to, std::error_code& ec) {
  ec.clear();
#ifdef _WIN32
  if (!::MoveFileExW(from.c_str(), to.c_str(), MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)) {
    ec = std::error_code(static_cast<int>(::GetLastError()), std::system_category());
    return false;
  }
  return true;
#else
  if (::rename(from.c_str(), to.c_str()) != 0) {
    const int code = errno;
    ec = std::error_code(code, std::system_category());
    return false;
  }
  return true;
#endif
}

}  // namespace

struct rth_cache {
  struct Entry { std::string key; uint32_t width, height; uint64_t bytes, tick; };
  fs::path dir;
  rth_limits limits;
  std::map<std::string, Entry> entries;  // by file name
  uint64_t total = 0, clock = 0, temp_counter = 0, temp_token = 0;
  rth_stats stats;
  std::thread::id owner;
  bool busy = false;
};

namespace {

// ---- handle implementations ------------------------------------------------
int WriteHandle::open_exclusive(const fs::path& path, std::error_code& ec) {
  ec.clear();
#ifdef _WIN32
  HANDLE h = ::CreateFileW(path.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_NEW,
                           FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OPEN_REPARSE_POINT, nullptr);
  if (h == INVALID_HANDLE_VALUE) {
    const DWORD error = ::GetLastError();
    ec = std::error_code(static_cast<int>(error), std::system_category());
    return (error == ERROR_FILE_EXISTS || error == ERROR_ALREADY_EXISTS) ? 1 : 2;
  }
  handle_ = h;
  return 0;
#else
  const int fd = ::open(path.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
  if (fd < 0) {
    const int error = errno;
    ec = std::error_code(error, std::system_category());
    return error == EEXIST ? 1 : 2;
  }
  fd_ = fd;
  return 0;
#endif
}

bool WriteHandle::write(const void* data, size_t size, std::error_code& ec) {
  const unsigned char* p = static_cast<const unsigned char*>(data);
  size_t done = 0;
  while (done < size) {
#ifdef _WIN32
    const DWORD want = static_cast<DWORD>(std::min<size_t>(size - done, static_cast<size_t>(1) << 20));
    DWORD wrote = 0;
    if (!::WriteFile(handle_, p + done, want, &wrote, nullptr)) {
      ec = std::error_code(static_cast<int>(::GetLastError()), std::system_category());
      return false;
    }
    if (wrote == 0) {
      ec = std::make_error_code(std::errc::io_error);
      return false;
    }
    done += static_cast<size_t>(wrote);
#else
    const ssize_t n = ::write(fd_, p + done, size - done);
    if (n < 0) {
      if (errno == EINTR) continue;
      ec = std::error_code(errno, std::system_category());
      return false;
    }
    if (n == 0) {
      ec = std::make_error_code(std::errc::io_error);
      return false;
    }
    done += static_cast<size_t>(n);
#endif
  }
  return true;
}

bool WriteHandle::sync(std::error_code& ec) {
#ifdef _WIN32
  if (!::FlushFileBuffers(handle_)) {
    ec = std::error_code(static_cast<int>(::GetLastError()), std::system_category());
    return false;
  }
  return true;
#else
  if (::fsync(fd_) != 0) {
    ec = std::error_code(errno, std::system_category());
    return false;
  }
  return true;
#endif
}

void WriteHandle::close() {
#ifdef _WIN32
  if (handle_ != INVALID_HANDLE_VALUE) {
    ::CloseHandle(handle_);
    handle_ = INVALID_HANDLE_VALUE;
  }
#else
  if (fd_ >= 0) {
    ::close(fd_);
    fd_ = -1;
  }
#endif
}

bool ReadHandle::open_regular(const fs::path& path, uint64_t& size, std::error_code& ec) {
  ec.clear();
  size = 0;
#ifdef _WIN32
  HANDLE h = ::CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, nullptr,
                           OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_SEQUENTIAL_SCAN, nullptr);
  if (h == INVALID_HANDLE_VALUE) {
    ec = std::error_code(static_cast<int>(::GetLastError()), std::system_category());
    return false;
  }
  BY_HANDLE_FILE_INFORMATION info;
  if (!::GetFileInformationByHandle(h, &info) ||
      (info.dwFileAttributes & (FILE_ATTRIBUTE_REPARSE_POINT | FILE_ATTRIBUTE_DIRECTORY)) != 0) {
    ::CloseHandle(h);
    ec = std::make_error_code(std::errc::invalid_argument);
    return false;
  }
  handle_ = h;
  size = (static_cast<uint64_t>(info.nFileSizeHigh) << 32) | static_cast<uint64_t>(info.nFileSizeLow);
  return true;
#else
  const int fd = ::open(path.c_str(), O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
  if (fd < 0) {
    ec = std::error_code(errno, std::system_category());
    return false;
  }
  struct stat info;
  if (::fstat(fd, &info) != 0 || !S_ISREG(info.st_mode)) {
    ::close(fd);
    ec = std::make_error_code(std::errc::invalid_argument);
    return false;
  }
  fd_ = fd;
  size = static_cast<uint64_t>(info.st_size);
  return true;
#endif
}

bool ReadHandle::read(void* data, size_t size, size_t& got, std::error_code& ec) {
  unsigned char* p = static_cast<unsigned char*>(data);
  got = 0;
  while (got < size) {
#ifdef _WIN32
    const DWORD want = static_cast<DWORD>(std::min<size_t>(size - got, static_cast<size_t>(1) << 20));
    DWORD have = 0;
    if (!::ReadFile(handle_, p + got, want, &have, nullptr)) {
      ec = std::error_code(static_cast<int>(::GetLastError()), std::system_category());
      return false;
    }
    if (have == 0) break;
    got += static_cast<size_t>(have);
#else
    const ssize_t n = ::read(fd_, p + got, size - got);
    if (n < 0) {
      if (errno == EINTR) continue;
      ec = std::error_code(errno, std::system_category());
      return false;
    }
    if (n == 0) break;
    got += static_cast<size_t>(n);
#endif
  }
  return true;
}

void ReadHandle::close() {
#ifdef _WIN32
  if (handle_ != INVALID_HANDLE_VALUE) {
    ::CloseHandle(handle_);
    handle_ = INVALID_HANDLE_VALUE;
  }
#else
  if (fd_ >= 0) {
    ::close(fd_);
    fd_ = -1;
  }
#endif
}

struct Enter {
  rth_cache* cache;
  bool entered = false;
  Enter(rth_cache* c, rth_error* e) : cache(c) {
    if (!c) { fail(e, RTH_ARGUMENT, -1, "Missing cache"); return; }
    if (c->owner != std::this_thread::get_id()) { fail(e, RTH_ARGUMENT, -1, "Cache used from a thread other than its owner"); return; }
    if (c->busy) { fail(e, RTH_ARGUMENT, -1, "Cache is busy (re-entrant call)"); return; }
    c->busy = true; entered = true;
  }
  ~Enter() { if (entered) cache->busy = false; }
};

std::string entry_name(const std::string& key) { return "rth-" + sha_hex(key.data(), key.size()).substr(0, 32) + ".rth"; }

bool recognised_entry(const std::string& n) {
  if (n.size() != 4 + 32 + 4 || n.compare(0, 4, "rth-") != 0 || n.compare(36, 4, ".rth") != 0) return false;
  for (size_t i = 4; i < 36; ++i) if (!((n[i] >= '0' && n[i] <= '9') || (n[i] >= 'a' && n[i] <= 'f'))) return false;
  return true;
}

bool lower_hex(const std::string& n, size_t begin, size_t end) {
  if (begin >= end) return false;
  for (size_t i = begin; i < end; ++i) if (!((n[i] >= '0' && n[i] <= '9') || (n[i] >= 'a' && n[i] <= 'f'))) return false;
  return true;
}
bool digits(const std::string& n, size_t begin, size_t end) {
  if (begin >= end) return false;
  for (size_t i = begin; i < end; ++i) if (n[i] < '0' || n[i] > '9') return false;
  return true;
}

// Names written by earlier versions of this module: "rth-tmp-<n>.tmp" and
// "rth-tmp-index-<n>.tmp". No live session of this version uses them, so open may
// remove them (removing a link never touches the file it points at).
bool legacy_temp_name(const std::string& n) {
  if (n.size() < 12 || n.compare(n.size() - 4, 4, ".tmp") != 0) return false;
  const size_t body = n.size() - 4;
  if (n.compare(0, 8, "rth-tmp-") == 0 && digits(n, 8, body)) return true;
  if (n.size() > 18 && n.compare(0, 14, "rth-tmp-index-") == 0 && digits(n, 14, body)) return true;
  return false;
}

// "rth-tmp-<16 hex session>-<8 hex sequence>.tmp": unpredictable per open, so a
// hard link or symbolic link cannot be aimed at it from outside.
bool session_temp_name(const std::string& n) {
  if (n.size() != 37 || n.compare(0, 8, "rth-tmp-") != 0 || n[24] != '-' || n.compare(33, 4, ".tmp") != 0) return false;
  return lower_hex(n, 8, 24) && lower_hex(n, 25, 33);
}

uint64_t scan_budget(const rth_limits& l) {
  const uint64_t budget = kScanMinCandidates + static_cast<uint64_t>(l.max_entries) * kScanPerEntry;
  return std::min(budget, kScanMaxCandidates);
}

std::string next_temp_name(rth_cache* c) {
  const uint64_t seq = ++c->temp_counter;
  char buf[64];
  std::snprintf(buf, sizeof(buf), "rth-tmp-%016llx-%08llx.tmp", (unsigned long long)c->temp_token,
                (unsigned long long)(seq & 0xffffffffull));
  return std::string(buf);
}

bool temp_is_stale(const fs::path& p) {
  std::error_code ec;
  const fs::file_time_type written = fs::last_write_time(p, ec);
  if (ec) return false;
  const fs::file_time_type now = fs::file_time_type::clock::now();
  if (written >= now) return false;
  return (now - written) > std::chrono::seconds(kStaleTempSeconds);
}

// Creates the bytes under a fresh exclusive name in the cache directory, then
// publishes them with a platform atomic replace. A name that already exists
// (including one that is a hard link) is never opened, so nothing outside the
// cache can be truncated through it.
bool publish_file(rth_cache* c, const fs::path& target, const void* data, size_t size, std::error_code& ec) {
  for (int attempt = 0; attempt < 8; ++attempt) {
    const fs::path temp = c->dir / next_temp_name(c);
    WriteHandle out;
    const int opened = out.open_exclusive(temp, ec);
    if (opened == 1) continue;
    if (opened != 0) return false;
    bool good = out.write(data, size, ec);
    if (good) good = out.sync(ec);
    out.close();
    if (!good) {
      std::error_code ignored;
      fs::remove(temp, ignored);
      return false;
    }
    if (atomic_replace(temp, target, ec)) return true;
    std::error_code ignored;
    fs::remove(temp, ignored);
    return false;
  }
  ec = std::make_error_code(std::errc::file_exists);
  return false;
}

bool write_index(rth_cache* c) {
  std::string text = std::string(kIndexMagic) + "\n";
  for (const auto& kv : c->entries) text += kv.first + " " + std::to_string(kv.second.tick) + "\n";
  std::error_code ec;
  if (!publish_file(c, c->dir / kIndexName, text.data(), text.size(), ec)) {
    ++c->stats.index_failures;
    return false;
  }
  return true;
}

// Parses and structurally validates the header of an in-memory prefix; file_size is
// the real size of the file.
bool parse_header(const unsigned char* p, size_t have, uint64_t file_size, const rth_limits& lim, Header& h) {
  if (have < kFixedHeader || std::memcmp(p, kMagic, 8) != 0) return false;
  uint32_t header_len = get32(p + 8), key_len = get32(p + 12);
  h.width = get32(p + 16); h.height = get32(p + 20); h.origin = get32(p + 24);
  h.payload = get64(p + 28);
  std::memcpy(h.digest, p + 36, 32);
  if (key_len == 0 || key_len > kKeyMax || header_len != kFixedHeader + key_len) return false;
  if (have < header_len) return false;
  if (h.width == 0 || h.height == 0 || h.width > lim.max_edge || h.height > lim.max_edge) return false;
  if (h.origin != RTH_ORIGIN_AUTHOR_COVER && h.origin != RTH_ORIGIN_FIRST_PAGE_PREVIEW) return false;
  if (h.payload != (uint64_t)h.width * h.height * 4u) return false;
  if (file_size != (uint64_t)header_len + h.payload) return false;
  h.key.assign(reinterpret_cast<const char*>(p + kFixedHeader), key_len);
  h.body = header_len;
  return true;
}

bool read_header_only(const fs::path& p, const rth_limits& lim, Header& h, uint64_t& size) {
  std::error_code ec;
  ReadHandle in;
  if (!in.open_regular(p, size, ec)) return false;
  unsigned char buf[kFixedHeader + kKeyMax];
  size_t got = 0;
  if (!in.read(buf, sizeof(buf), got, ec)) return false;
  return parse_header(buf, got, size, lim, h);
}

void drop_entry(rth_cache* c, const std::string& name) {
  auto it = c->entries.find(name);
  if (it != c->entries.end()) { c->total -= it->second.bytes; c->entries.erase(it); }
  std::error_code ec;
  fs::remove(c->dir / name, ec);
}

void evict_lru(rth_cache* c) {
  auto victim = c->entries.begin();
  for (auto it = c->entries.begin(); it != c->entries.end(); ++it)
    if (it->second.tick < victim->second.tick) victim = it;
  std::string name = victim->first;
  drop_entry(c, name);
  ++c->stats.evictions;
}

void make_room(rth_cache* c, uint64_t need) {
  while (!c->entries.empty() && (c->entries.size() + 1 > c->limits.max_entries || c->total + need > c->limits.max_total_bytes))
    evict_lru(c);
}

// ---- argument validation ----------------------------------------------------
bool hex64(const char* s) {
  for (size_t i = 0; i < 64; ++i) if (!((s[i] >= '0' && s[i] <= '9') || (s[i] >= 'a' && s[i] <= 'f'))) return false;
  return s[64] == 0;
}
rth_status check_book(const rth_book* b, bool fixed_only, rth_error* e) {
  if (!b) return fail(e, RTH_ARGUMENT, -1, "Missing book identity");
  if (b->format < (int)EXR_TXT || b->format > (int)EXR_CBZ) return fail(e, RTH_ARGUMENT, -1, "Unknown book format");
  if (fixed_only && b->format != (int)EXR_PDF && b->format != (int)EXR_CBZ) return fail(e, RTH_ARGUMENT, -1, "Preview needs a PDF or CBZ identity");
  if (!hex64(b->sha256)) return fail(e, RTH_ARGUMENT, -1, "Book SHA-256 must be 64 lowercase hex digits");
  return ok(e);
}
rth_status check_request(const rth_cache* c, const rth_request* r, rth_error* e) {
  if (!r || r->struct_size < sizeof(rth_request)) return fail(e, RTH_ARGUMENT, -1, "Invalid request");
  if (r->width == 0 || r->height == 0) return fail(e, RTH_ARGUMENT, -1, "Empty output box");
  if (r->width > c->limits.max_edge || r->height > c->limits.max_edge)  // the caller counts the rejection
    return fail(e, RTH_LIMIT, -1, "Output box exceeds the cache edge limit");
  return ok(e);
}

std::string make_key(const rth_book& b, rth_origin origin, const std::string& source, const rth_request& r) {
  bool preview = origin == RTH_ORIGIN_FIRST_PAGE_PREVIEW;
  char text[kKeyMax];
  std::snprintf(text, sizeof(text), "rth1|f=%d|s=%s|o=%d|src=%s|box=%ux%u|pg=%u|bg=%08x|alg=box1", b.format, b.sha256,
                (int)origin, source.c_str(), (unsigned)r.width, (unsigned)r.height, preview ? (unsigned)r.page : 0u,
                preview ? (unsigned)r.background : 0u);
  return text;
}

// ---- lookup / store ---------------------------------------------------------
void clear_out(rth_thumbnail* t) { if (t) std::memset(t, 0, sizeof(*t)); }

bool lookup(rth_cache* c, const std::string& key, rth_thumbnail* out) {
  const std::string name = entry_name(key);
  auto it = c->entries.find(name);
  if (it == c->entries.end()) { ++c->stats.misses; return false; }
  const uint64_t max_entry = kFixedHeader + kKeyMax + (uint64_t)c->limits.max_edge * c->limits.max_edge * 4ull;
  std::error_code ec;
  ReadHandle in;
  uint64_t size = 0;
  std::vector<unsigned char> bytes;
  Header h;
  bool good = false;
  if (in.open_regular(c->dir / name, size, ec) && size >= kFixedHeader && size <= max_entry) {
    bytes.resize((size_t)size);
    size_t got = 0;
    if (in.read(bytes.data(), bytes.size(), got, ec) && got == bytes.size())
      good = parse_header(bytes.data(), bytes.size(), size, c->limits, h) && h.key == key;
  }
  in.close();
  if (good) {
    unsigned char digest[32];
    Sha256 s; s.init(); s.update(bytes.data() + h.body, (size_t)h.payload); s.finish(digest);
    good = std::memcmp(digest, h.digest, 32) == 0;
  }
  if (!good) {
    drop_entry(c, name);
    ++c->stats.corrupt_rebuilt;
    ++c->stats.misses;
    return false;
  }
  unsigned char* pixels = static_cast<unsigned char*>(std::malloc((size_t)h.payload));
  if (!pixels) { ++c->stats.misses; return false; }
  std::memcpy(pixels, bytes.data() + h.body, (size_t)h.payload);
  it->second.tick = ++c->clock;
  ++c->stats.hits;
  out->origin = (rth_origin)h.origin; out->width = h.width; out->height = h.height; out->stride = h.width * 4u;
  out->pixels = pixels; out->from_cache = 1; out->stored = 0;
  return true;
}

bool store(rth_cache* c, const std::string& key, rth_origin origin, const rth_thumbnail& t) {
  const std::string name = entry_name(key);
  std::vector<unsigned char> file;
  const uint64_t payload = (uint64_t)t.width * t.height * 4u;
  file.reserve(kFixedHeader + key.size() + (size_t)payload);
  file.insert(file.end(), kMagic, kMagic + 8);
  put32(file, (uint32_t)(kFixedHeader + key.size())); put32(file, (uint32_t)key.size());
  put32(file, t.width); put32(file, t.height); put32(file, (uint32_t)origin); put64(file, payload);
  unsigned char digest[32];
  Sha256 s; s.init(); s.update(t.pixels, (size_t)payload); s.finish(digest);
  file.insert(file.end(), digest, digest + 32);
  file.insert(file.end(), key.begin(), key.end());
  file.insert(file.end(), t.pixels, t.pixels + payload);
  const uint64_t need = file.size();
  if (need > c->limits.max_total_bytes) { ++c->stats.rejected; return false; }
  if (c->entries.count(name)) drop_entry(c, name);
  make_room(c, need);
  std::error_code ec;
  if (!publish_file(c, c->dir / name, file.data(), file.size(), ec)) {
    ++c->stats.store_failures;
    return false;
  }
  c->entries[name] = rth_cache::Entry{key, t.width, t.height, need, ++c->clock};
  c->total += need;
  ++c->stats.stores;
  write_index(c);
  return true;
}

// ---- geometry and resampling -------------------------------------------------
void fit(uint64_t sw, uint64_t sh, uint64_t bw, uint64_t bh, uint32_t* ow, uint32_t* oh) {
  if (sw <= bw && sh <= bh) { *ow = (uint32_t)sw; *oh = (uint32_t)sh; return; }
  if (sw * bh >= sh * bw) {
    *ow = (uint32_t)bw;
    uint64_t h = (sh * bw + sw / 2) / sw;
    *oh = (uint32_t)std::max<uint64_t>(1, std::min<uint64_t>(h, bh));
  } else {
    *oh = (uint32_t)bh;
    uint64_t w = (sw * bh + sh / 2) / sh;
    *ow = (uint32_t)std::max<uint64_t>(1, std::min<uint64_t>(w, bw));
  }
}

// Integer box filter on alpha-weighted (premultiplied) samples; fully transparent
// output texels carry RGB 0. Source straight RGBA8.
bool resample(const unsigned char* src, uint32_t sw, uint32_t sh, size_t stride, uint32_t ow, uint32_t oh,
              unsigned char* dst, Poll& poll) {
  for (uint32_t oy = 0; oy < oh; ++oy) {
    if (poll.check()) return false;
    uint64_t y0 = (uint64_t)oy * sh / oh, y1 = ((uint64_t)(oy + 1) * sh + oh - 1) / oh;
    if (y1 <= y0) y1 = y0 + 1;
    for (uint32_t ox = 0; ox < ow; ++ox) {
      uint64_t x0 = (uint64_t)ox * sw / ow, x1 = ((uint64_t)(ox + 1) * sw + ow - 1) / ow;
      if (x1 <= x0) x1 = x0 + 1;
      uint64_t sa = 0, sr = 0, sg = 0, sb = 0;
      for (uint64_t y = y0; y < y1; ++y) {
        const unsigned char* p = src + (size_t)y * stride + (size_t)x0 * 4u;
        for (uint64_t x = x0; x < x1; ++x, p += 4) {
          uint64_t a = p[3];
          sa += a; sr += p[0] * a; sg += p[1] * a; sb += p[2] * a;
        }
      }
      uint64_t n = (x1 - x0) * (y1 - y0);
      unsigned char* q = dst + ((size_t)oy * ow + ox) * 4u;
      q[3] = (unsigned char)((sa + n / 2) / n);
      if (sa == 0) { q[0] = q[1] = q[2] = 0; }
      else {
        q[0] = (unsigned char)((sr + sa / 2) / sa);
        q[1] = (unsigned char)((sg + sa / 2) / sa);
        q[2] = (unsigned char)((sb + sa / 2) / sa);
      }
    }
  }
  return true;
}

struct Bitmap {
  exr_bitmap b;
  Bitmap() { std::memset(&b, 0, sizeof(b)); }
  ~Bitmap() { exr_bitmap_free(&b); }
};

// Shared tail: scale a decoded/rendered RGBA bitmap into the request box, publish.
rth_status finish(rth_cache* c, const std::string& key, rth_origin origin, const exr_bitmap& bmp,
                  const rth_request& rq, Poll& poll, rth_thumbnail* out, rth_error* err) {
  if (!bmp.pixels || bmp.channels != 4 || bmp.width == 0 || bmp.height == 0 || bmp.stride < (uint64_t)bmp.width * 4u)
    return fail(err, RTH_FORMAT, -1, "Source image is not RGBA");
  uint64_t pixels = (uint64_t)bmp.width * bmp.height;
  if (pixels > c->limits.max_source_pixels) return fail(err, RTH_LIMIT, -1, "Source image exceeds the pixel limit");
  uint64_t decoded = (uint64_t)bmp.stride * bmp.height;
  c->stats.last_decoded_bytes = decoded;
  c->stats.peak_decoded_bytes = std::max(c->stats.peak_decoded_bytes, decoded);
  if (poll.check()) return fail(err, RTH_CANCELLED, -1, "Cancelled");
  uint32_t ow, oh;
  fit(bmp.width, bmp.height, rq.width, rq.height, &ow, &oh);
  uint64_t bytes = (uint64_t)ow * oh * 4u;  // <= 1024*1024*4, cannot overflow
  unsigned char* dst = static_cast<unsigned char*>(std::malloc((size_t)bytes));
  if (!dst) return fail(err, RTH_MEMORY, -1, "Thumbnail allocation failed");
  if (!resample(bmp.pixels, bmp.width, bmp.height, bmp.stride, ow, oh, dst, poll)) {
    std::free(dst);
    return fail(err, RTH_CANCELLED, -1, "Cancelled");
  }
  if (poll.check()) { std::free(dst); return fail(err, RTH_CANCELLED, -1, "Cancelled"); }
  out->origin = origin; out->width = ow; out->height = oh; out->stride = ow * 4u; out->pixels = dst;
  out->from_cache = 0; out->source_width = bmp.width; out->source_height = bmp.height; out->decoded_bytes = decoded;
  out->stored = store(c, key, origin, *out) ? 1 : 0;
  return ok(err);
}

rth_status decode_cover(rth_cache* c, const std::string& key, const void* data, size_t size, const rth_request& rq,
                        Poll& poll, rth_thumbnail* out, rth_error* err) {
  if (size > c->limits.max_encoded_bytes) return fail(err, RTH_LIMIT, -1, "Encoded cover exceeds the byte limit");
  uint32_t w = 0, h = 0;
  exr_error se;
  std::memset(&se, 0, sizeof(se));
  exr_status st = exr_image_page_dimensions(data, size, 0, &w, &h, &se);
  if (st != EXR_OK) return map_sdk(err, st, se, "Cover header");
  if (w == 0 || h == 0) return fail(err, RTH_FORMAT, -1, "Cover has no pixels");
  if ((uint64_t)w * h > c->limits.max_source_pixels) return fail(err, RTH_LIMIT, -1, "Cover exceeds the source pixel limit");
  if (poll.check()) return fail(err, RTH_CANCELLED, -1, "Cancelled");
  Bitmap bmp;
  st = exr_image_decode(data, size, &bmp.b, &se);
  if (st != EXR_OK) return map_sdk(err, st, se, "Cover decode");
  return finish(c, key, RTH_ORIGIN_AUTHOR_COVER, bmp.b, rq, poll, out, err);
}

}  // namespace

// ---- public API -------------------------------------------------------------
extern "C" {

rth_limits rth_limits_defaults(void) {
  rth_limits l;
  std::memset(&l, 0, sizeof(l));
  l.struct_size = sizeof(l);
  l.max_edge = 512;
  l.max_entries = 256;
  l.max_total_bytes = 64ull * 1024ull * 1024ull;
  l.max_source_pixels = RTH_SOURCE_PIXELS_HARD_MAX;
  l.max_encoded_bytes = 8u * 1024u * 1024u;
  return l;
}

rth_request rth_request_defaults(void) {
  rth_request r;
  std::memset(&r, 0, sizeof(r));
  r.struct_size = sizeof(r);
  r.width = 256; r.height = 256; r.page = 0; r.background = 0xffffffffu;
  return r;
}

void rth_thumbnail_free(rth_thumbnail* t) {
  if (!t) return;
  std::free(t->pixels);
  std::memset(t, 0, sizeof(*t));
}

void rth_sha256_hex(const void* data, size_t size, char out[65]) {
  if (!out) return;
  try {
    std::string s = sha_hex(data, size);
    std::memcpy(out, s.c_str(), 65);
  } catch (...) {
    std::memset(out, 0, 65);
  }
}

rth_status rth_cache_open(const char* directory, const rth_limits* limits, rth_cache** out, rth_error* error) {
  if (out) *out = nullptr;
  if (!directory || !*directory || !out) return fail(error, RTH_ARGUMENT, -1, "Missing cache directory or output");
  rth_limits lim = limits ? *limits : rth_limits_defaults();
  if (lim.struct_size < sizeof(rth_limits)) return fail(error, RTH_ARGUMENT, -1, "Invalid limits");
  if (lim.max_edge == 0 || lim.max_edge > RTH_EDGE_HARD_MAX) return fail(error, RTH_LIMIT, -1, "max_edge outside 1..hard maximum");
  if (lim.max_entries == 0 || lim.max_entries > RTH_ENTRIES_HARD_MAX) return fail(error, RTH_LIMIT, -1, "max_entries outside 1..hard maximum");
  if (lim.max_total_bytes < RTH_TOTAL_BYTES_MIN || lim.max_total_bytes > RTH_TOTAL_BYTES_HARD_MAX)
    return fail(error, RTH_LIMIT, -1, "max_total_bytes outside the permitted range");
  if (lim.max_source_pixels == 0 || lim.max_source_pixels > RTH_SOURCE_PIXELS_HARD_MAX) return fail(error, RTH_LIMIT, -1, "max_source_pixels outside 1..hard maximum");
  if (lim.max_encoded_bytes == 0 || lim.max_encoded_bytes > RTH_ENCODED_HARD_MAX) return fail(error, RTH_LIMIT, -1, "max_encoded_bytes outside 1..hard maximum");
  return guarded(error, [&]() -> rth_status {
    rth_cache* c = new (std::nothrow) rth_cache();
    if (!c) return fail(error, RTH_MEMORY, -1, "Cache allocation failed");
    c->dir = fs::u8path(directory);
    c->limits = lim;
    std::memset(&c->stats, 0, sizeof(c->stats));
    c->stats.struct_size = sizeof(c->stats);
    c->owner = std::this_thread::get_id();
    c->temp_token = process_token();
    std::error_code ec;
    fs::create_directories(c->dir, ec);
    if (ec || !fs::is_directory(c->dir, ec)) {
      delete c;
      return fail(error, RTH_IO, -1, "Cannot create the cache directory");
    }
    // LRU ticks of the last close. The index is read once and its line count is
    // bounded by the same candidate budget as the directory scan.
    const uint64_t budget = scan_budget(c->limits);
    std::map<std::string, uint64_t> ticks;
    {
      ReadHandle in;
      uint64_t size = 0;
      if (in.open_regular(c->dir / kIndexName, size, ec) && size <= 4ull * 1024ull * 1024ull) {
        std::vector<char> text((size_t)size);
        size_t got = 0;
        if (size == 0 || (in.read(text.data(), text.size(), got, ec) && got == text.size())) {
          size_t pos = 0, lines = 0;
          auto next_line = [&](std::string& line) {
            if (pos >= text.size()) return false;
            const size_t end = [&] {
              size_t at = pos;
              while (at < text.size() && text[at] != '\n') ++at;
              return at;
            }();
            line.assign(text.data() + pos, end - pos);
            pos = end < text.size() ? end + 1 : end;
            return true;
          };
          std::string line;
          if (next_line(line) && line == kIndexMagic) {
            while (lines < budget && next_line(line)) {
              ++lines;
              const size_t space = line.find(' ');
              if (space != std::string::npos) ticks[line.substr(0, space)] = std::strtoull(line.c_str() + space + 1, nullptr, 10);
            }
          }
        }
      }
    }
    // One bounded pass: retain and evict entry by entry, never holding the
    // directory contents. Beyond the budget the rest is left untouched and
    // scan_truncated reports that the adoption is partial.
    uint64_t inspected = 0;
    std::error_code it_ec;
    for (fs::directory_iterator it(c->dir, it_ec), end; !it_ec && it != end; it.increment(it_ec)) {
      if (inspected >= budget) { c->stats.scan_truncated = 1; break; }
      ++inspected;
      std::error_code fe;
      const fs::file_status status = it->symlink_status(fe);  // never follows a link
      if (fe || !fs::is_regular_file(status)) continue;
      std::string name;
      try {
        name = it->path().filename().u8string();
      } catch (...) {
        continue;  // a name this platform cannot represent is left untouched
      }
      if (legacy_temp_name(name)) { fs::remove(it->path(), fe); continue; }
      if (session_temp_name(name)) {
        if (temp_is_stale(it->path())) fs::remove(it->path(), fe);
        continue;
      }
      if (!recognised_entry(name)) continue;
      Header h;
      uint64_t size = 0;
      if (!read_header_only(it->path(), c->limits, h, size) || entry_name(h.key) != name) {
        fs::remove(it->path(), fe);
        ++c->stats.corrupt_rebuilt;
        continue;
      }
      const uint64_t tick = ticks.count(name) ? ticks[name] : 0;
      c->entries[name] = rth_cache::Entry{h.key, h.width, h.height, size, tick};
      c->total += size;
      c->clock = std::max(c->clock, tick);
      while (!c->entries.empty() && (c->entries.size() > c->limits.max_entries || c->total > c->limits.max_total_bytes))
        evict_lru(c);
      // The retained set, not the transient insertion, is what the scan holds.
      c->stats.peak_retained_entries =
          std::max<uint64_t>(c->stats.peak_retained_entries, static_cast<uint64_t>(c->entries.size()));
    }
    c->stats.scanned_files = inspected;
    if (!write_index(c)) {
      delete c;
      return fail(error, RTH_IO, -1, "Cannot publish the cache index (atomic replace failed)");
    }
    *out = c;
    return ok(error);
  });
}

void rth_cache_close(rth_cache* c) {
  if (!c || c->owner != std::this_thread::get_id() || c->busy) return;
  try {
    write_index(c);
  } catch (...) {
  }
  delete c;
}

rth_status rth_cache_clear(rth_cache* c, rth_error* error) {
  Enter guard(c, error);
  if (!guard.entered) return RTH_ARGUMENT;
  return guarded(error, [&]() -> rth_status {
    std::vector<std::string> names;
    names.reserve(c->entries.size());
    for (const auto& kv : c->entries) names.push_back(kv.first);
    for (const std::string& n : names) drop_entry(c, n);
    if (!write_index(c)) return fail(error, RTH_IO, -1, "Cannot publish the cache index (atomic replace failed)");
    return ok(error);
  });
}

rth_status rth_cache_stats(const rth_cache* cc, rth_stats* stats, rth_error* error) {
  rth_cache* c = const_cast<rth_cache*>(cc);
  if (!c || !stats) return fail(error, RTH_ARGUMENT, -1, "Missing cache or output");
  Enter guard(c, error);
  if (!guard.entered) return RTH_ARGUMENT;
  return guarded(error, [&]() -> rth_status {
    *stats = c->stats;
    stats->struct_size = sizeof(*stats);
    stats->entries = (uint32_t)c->entries.size();
    stats->bytes = c->total;
    return ok(error);
  });
}

rth_status rth_cache_find(rth_cache* c, const rth_book* book, rth_origin origin, const rth_request* request,
                          rth_thumbnail* out, int* found, rth_error* error) {
  if (found) *found = 0;
  clear_out(out);
  Enter guard(c, error);
  if (!guard.entered) return RTH_ARGUMENT;
  return guarded(error, [&]() -> rth_status {
    if (!out || !found) return fail(error, RTH_ARGUMENT, -1, "Missing output");
    if (origin != RTH_ORIGIN_AUTHOR_COVER && origin != RTH_ORIGIN_FIRST_PAGE_PREVIEW) return fail(error, RTH_ARGUMENT, -1, "Unknown origin");
    rth_status st = check_book(book, origin == RTH_ORIGIN_FIRST_PAGE_PREVIEW, error);
    if (st != RTH_OK) return st;
    st = check_request(c, request, error);
    if (st != RTH_OK) { if (st == RTH_LIMIT) ++c->stats.rejected; return st; }
    const std::string key = make_key(*book, origin, origin == RTH_ORIGIN_AUTHOR_COVER ? "lib" : "fix", *request);
    *found = lookup(c, key, out) ? 1 : 0;
    if (*found) write_index(c);
    return ok(error);
  });
}

rth_status rth_cover_from_library(rth_cache* c, exr_library* library, int64_t book_id, const rth_book* book,
                                  const rth_request* request, const rth_control* control, rth_thumbnail* out,
                                  rth_error* error) {
  clear_out(out);
  Enter guard(c, error);
  if (!guard.entered) return RTH_ARGUMENT;
  return guarded(error, [&]() -> rth_status {
    if (!out || !library || book_id <= 0) return fail(error, RTH_ARGUMENT, -1, "Missing library, book id or output");
    rth_status st = check_book(book, false, error);
    if (st != RTH_OK) return st;
    st = check_request(c, request, error);
    if (st != RTH_OK) { if (st == RTH_LIMIT) ++c->stats.rejected; return st; }
    Poll poll{control, false};
    if (poll.check()) return fail(error, RTH_CANCELLED, -1, "Cancelled");
    const std::string key = make_key(*book, RTH_ORIGIN_AUTHOR_COVER, "lib", *request);
    if (lookup(c, key, out)) { write_index(c); return ok(error); }
    void* data = nullptr;
    size_t size = 0;
    exr_error se;
    std::memset(&se, 0, sizeof(se));
    exr_status es = exr_library_blob(library, book_id, 1, &data, &size, &se);
    if (es != EXR_OK) return map_sdk(error, es, se, "Cover blob");
    if (!data || !size) { exr_free(data); return ok(error); }  // normal placeholder
    st = decode_cover(c, key, data, size, *request, poll, out, error);
    exr_free(data);
    if (st != RTH_OK) clear_out(out);
    return st;
  });
}

rth_status rth_cover_from_encoded(rth_cache* c, const rth_book* book, const void* data, size_t size,
                                  const rth_request* request, const rth_control* control, rth_thumbnail* out,
                                  rth_error* error) {
  clear_out(out);
  Enter guard(c, error);
  if (!guard.entered) return RTH_ARGUMENT;
  return guarded(error, [&]() -> rth_status {
    if (!out) return fail(error, RTH_ARGUMENT, -1, "Missing output");
    rth_status st = check_book(book, false, error);
    if (st != RTH_OK) return st;
    st = check_request(c, request, error);
    if (st != RTH_OK) { if (st == RTH_LIMIT) ++c->stats.rejected; return st; }
    Poll poll{control, false};
    if (poll.check()) return fail(error, RTH_CANCELLED, -1, "Cancelled");
    if (!data || !size) return ok(error);  // no cover: placeholder
    if (size > c->limits.max_encoded_bytes) { ++c->stats.rejected; return fail(error, RTH_LIMIT, -1, "Encoded cover exceeds the byte limit"); }
    const std::string key = make_key(*book, RTH_ORIGIN_AUTHOR_COVER, "enc:" + sha_hex(data, size), *request);
    if (lookup(c, key, out)) { write_index(c); return ok(error); }
    st = decode_cover(c, key, data, size, *request, poll, out, error);
    if (st != RTH_OK) clear_out(out);
    return st;
  });
}

rth_status rth_preview_from_fixed(rth_cache* c, exr_fixed_document* document, const rth_book* book,
                                  const rth_request* request, const rth_control* control, rth_thumbnail* out,
                                  rth_error* error) {
  clear_out(out);
  Enter guard(c, error);
  if (!guard.entered) return RTH_ARGUMENT;
  return guarded(error, [&]() -> rth_status {
    if (!out || !document) return fail(error, RTH_ARGUMENT, -1, "Missing document or output");
    rth_status st = check_book(book, true, error);
    if (st != RTH_OK) return st;
    st = check_request(c, request, error);
    if (st != RTH_OK) { if (st == RTH_LIMIT) ++c->stats.rejected; return st; }
    Poll poll{control, false};
    if (poll.check()) return fail(error, RTH_CANCELLED, -1, "Cancelled");
    const std::string key = make_key(*book, RTH_ORIGIN_FIRST_PAGE_PREVIEW, "fix", *request);
    if (lookup(c, key, out)) { write_index(c); return ok(error); }
    size_t count = 0;
    const exr_fixed_page* pages = exr_fixed_pages(document, &count);
    if (!pages || request->page >= count) return fail(error, RTH_ARGUMENT, -1, "Page index outside the document");
    exr_error se;
    std::memset(&se, 0, sizeof(se));
    exr_viewport vp;
    std::memset(&vp, 0, sizeof(vp));
    exr_status es = exr_viewport_create(&pages[request->page].geometry, 1.0, &vp, &se);
    if (es != EXR_OK) return map_sdk(error, es, se, "Page geometry");
    double vw = vp.width, vh = vp.height;
    if (!(std::isfinite(vw) && std::isfinite(vh) && vw > 0.0 && vh > 0.0 && vw < 1e7 && vh < 1e7))
      return fail(error, RTH_FORMAT, -1, "Page has no usable size");
    double scale = std::min(1.0, std::min((double)request->width / vw, (double)request->height / vh));
    if (vw * scale < 1.0 || vh * scale < 1.0) scale = 1.0 / std::min(vw, vh);
    double estimate = std::ceil(vw * scale) * std::ceil(vh * scale);
    if (!(estimate <= (double)c->limits.max_source_pixels)) {
      ++c->stats.rejected;
      return fail(error, RTH_LIMIT, -1, "Rendered page would exceed the source pixel limit");
    }
    exr_fixed_render_options options;
    std::memset(&options, 0, sizeof(options));
    options.channels = 4;
    options.background = request->background;
    options.control.cancelled = poll_callback;
    options.control.context = &poll;
    Bitmap bmp;
    es = exr_fixed_render(document, request->page, scale, &options, &bmp.b, &se);
    if (poll.cancelled) return fail(error, RTH_CANCELLED, -1, "Cancelled");
    if (es != EXR_OK) return map_sdk(error, es, se, "Page render");
    st = finish(c, key, RTH_ORIGIN_FIRST_PAGE_PREVIEW, bmp.b, *request, poll, out, error);
    if (st != RTH_OK) clear_out(out);
    return st;
  });
}

}  // extern "C"
