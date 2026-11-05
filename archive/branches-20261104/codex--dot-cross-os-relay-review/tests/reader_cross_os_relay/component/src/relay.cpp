/* SPDX-License-Identifier: MIT */
#include "exr_relay.h"
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <new>
#include <string>
#include <vector>

namespace fs = std::filesystem;

namespace {

struct failure {
  exr_relay_status code;
  std::string message;
};

/* ---------- SHA-256 (FIPS 180-4), no external crypto dependency ---------- */
struct sha256 {
  uint32_t h[8];
  uint64_t total = 0;
  unsigned char buf[64];
  size_t used = 0;
  sha256() {
    static const uint32_t init[8] = {0x6a09e667u, 0xbb67ae85u, 0x3c6ef372u, 0xa54ff53au,
                                     0x510e527fu, 0x9b05688cu, 0x1f83d9abu, 0x5be0cd19u};
    std::memcpy(h, init, sizeof h);
  }
  static uint32_t rotr(uint32_t x, unsigned n) { return (x >> n) | (x << (32u - n)); }
  void block(const unsigned char *p) {
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
    for (int i = 0; i < 16; i++)
      w[i] = ((uint32_t)p[4 * i] << 24) | ((uint32_t)p[4 * i + 1] << 16) | ((uint32_t)p[4 * i + 2] << 8) | (uint32_t)p[4 * i + 3];
    for (int i = 16; i < 64; i++) {
      uint32_t s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
      uint32_t s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
      w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    uint32_t a = h[0], b = h[1], c = h[2], d = h[3], e = h[4], f = h[5], g = h[6], hh = h[7];
    for (int i = 0; i < 64; i++) {
      uint32_t s1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
      uint32_t ch = (e & f) ^ (~e & g);
      uint32_t t1 = hh + s1 + ch + k[i] + w[i];
      uint32_t s0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
      uint32_t mj = (a & b) ^ (a & c) ^ (b & c);
      uint32_t t2 = s0 + mj;
      hh = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
    }
    h[0] += a; h[1] += b; h[2] += c; h[3] += d; h[4] += e; h[5] += f; h[6] += g; h[7] += hh;
  }
  void update(const void *data, size_t n) {
    const unsigned char *p = static_cast<const unsigned char *>(data);
    total += n;
    while (n) {
      size_t take = std::min(n, sizeof buf - used);
      std::memcpy(buf + used, p, take);
      used += take; p += take; n -= take;
      if (used == sizeof buf) { block(buf); used = 0; }
    }
  }
  std::string finish() {
    uint64_t bits = total * 8;
    unsigned char pad = 0x80;
    update(&pad, 1);
    unsigned char zero = 0;
    while (used != 56) update(&zero, 1);
    unsigned char length[8];
    for (int i = 0; i < 8; i++) length[i] = (unsigned char)(bits >> (56 - 8 * i));
    update(length, 8);
    static const char hex[] = "0123456789abcdef";
    std::string out;
    for (int i = 0; i < 8; i++)
      for (int shift = 28; shift >= 0; shift -= 4) out += hex[(h[i] >> shift) & 15u];
    return out;
  }
};

/* ---------- limits, control, errors ---------- */
struct effective_limits {
  uint32_t files = EXR_RELAY_MAX_FILES;
  uint32_t depth = EXR_RELAY_MAX_DEPTH;
  uint64_t file_bytes = EXR_RELAY_MAX_FILE_BYTES;
  uint64_t total_bytes = EXR_RELAY_MAX_TOTAL_BYTES;
};

effective_limits resolve_limits(const exr_relay_limits *l) {
  effective_limits out;
  if (!l) return out;
  if (l->struct_size < sizeof(exr_relay_limits)) throw failure{EXR_RELAY_ARGUMENT, "limits struct_size is too small"};
  if (l->max_files) {
    if (l->max_files > EXR_RELAY_MAX_FILES) throw failure{EXR_RELAY_ARGUMENT, "max_files above the hard ceiling"};
    out.files = l->max_files;
  }
  if (l->max_depth) {
    if (l->max_depth > EXR_RELAY_MAX_DEPTH) throw failure{EXR_RELAY_ARGUMENT, "max_depth above the hard ceiling"};
    out.depth = l->max_depth;
  }
  if (l->max_file_bytes) {
    if (l->max_file_bytes > EXR_RELAY_MAX_FILE_BYTES) throw failure{EXR_RELAY_ARGUMENT, "max_file_bytes above the hard ceiling"};
    out.file_bytes = l->max_file_bytes;
  }
  if (l->max_total_bytes) {
    if (l->max_total_bytes > EXR_RELAY_MAX_TOTAL_BYTES) throw failure{EXR_RELAY_ARGUMENT, "max_total_bytes above the hard ceiling"};
    out.total_bytes = l->max_total_bytes;
  }
  return out;
}

void poll(const exr_relay_control *control) {
  if (control && control->cancelled && control->cancelled(control->context))
    throw failure{EXR_RELAY_CANCELLED, "cancelled"};
}

void begin(exr_relay_error *error) {
  if (error) { error->code = EXR_RELAY_OK; error->message[0] = 0; }
}

void report(exr_relay_error *error, const failure &f) {
  if (!error) return;
  error->code = f.code;
  std::snprintf(error->message, sizeof error->message, "%s", f.message.c_str());
}

/* ---------- names ---------- */
bool valid_utf8(const std::string &s) {
  size_t i = 0, n = s.size();
  while (i < n) {
    unsigned char c = (unsigned char)s[i];
    if (c < 0x80) { i++; continue; }
    size_t extra;
    uint32_t cp;
    if (c >= 0xc2 && c <= 0xdf) { extra = 1; cp = c & 0x1fu; }
    else if (c >= 0xe0 && c <= 0xef) { extra = 2; cp = c & 0x0fu; }
    else if (c >= 0xf0 && c <= 0xf4) { extra = 3; cp = c & 0x07u; }
    else return false;
    if (i + extra >= n) return false;
    for (size_t k = 1; k <= extra; k++) {
      unsigned char cc = (unsigned char)s[i + k];
      if ((cc & 0xc0) != 0x80) return false;
      cp = (cp << 6) | (cc & 0x3fu);
    }
    if (extra == 2 && (cp < 0x800 || (cp >= 0xd800 && cp <= 0xdfff))) return false;
    if (extra == 3 && (cp < 0x10000 || cp > 0x10ffff)) return false;
    i += extra + 1;
  }
  return true;
}

void check_name(const std::string &name) {
  if (name.empty() || name == "." || name == "..") throw failure{EXR_RELAY_UNSAFE, "empty or dot path component"};
  if (!valid_utf8(name)) throw failure{EXR_RELAY_UNSAFE, "path component is not valid UTF-8"};
  for (unsigned char c : name)
    if (c < 0x20 || c == 0x7f || c == '"' || c == '\\' || c == '/') throw failure{EXR_RELAY_UNSAFE, "path component has a forbidden character"};
}

/* ---------- scan ---------- */
struct record {
  std::string path;
  bool dir = false;
  uint64_t bytes = 0;
  std::string sha;
};

struct scan {
  effective_limits limits;
  const exr_relay_control *control = nullptr;
  std::vector<record> records;
  uint32_t files = 0;
  uint64_t total = 0;
};

std::string hash_file(const fs::path &path, uint64_t max_bytes, const exr_relay_control *control, uint64_t &bytes) {
  std::error_code ec;
  uint64_t before = fs::file_size(path, ec);
  if (ec) throw failure{EXR_RELAY_IO, "cannot stat a file"};
  if (before > max_bytes) throw failure{EXR_RELAY_LIMIT, "file exceeds max_file_bytes"};
  std::ifstream in(path, std::ios::binary);
  if (!in) throw failure{EXR_RELAY_IO, "cannot open a file"};
  sha256 digest;
  std::vector<char> buffer(65536);
  uint64_t count = 0;
  for (;;) {
    poll(control);
    in.read(buffer.data(), (std::streamsize)buffer.size());
    std::streamsize got = in.gcount();
    if (got > 0) {
      count += (uint64_t)got;
      if (count > max_bytes) throw failure{EXR_RELAY_LIMIT, "file exceeds max_file_bytes"};
      digest.update(buffer.data(), (size_t)got);
    }
    if (!in) break;
  }
  if (in.bad()) throw failure{EXR_RELAY_IO, "read error"};
  uint64_t after = fs::file_size(path, ec);
  if (ec || after != before || count != before) throw failure{EXR_RELAY_IO, "file changed while it was read"};
  bytes = count;
  return digest.finish();
}

void walk(scan &ctx, const fs::path &dir, const std::string &relative, unsigned depth) {
  poll(ctx.control);
  std::error_code ec;
  std::vector<std::pair<std::string, fs::path>> children;
  fs::directory_iterator it(dir, ec), end;
  if (ec) throw failure{EXR_RELAY_IO, "cannot list a directory"};
  for (; it != end; it.increment(ec)) {
    if (ec) throw failure{EXR_RELAY_IO, "cannot list a directory"};
    children.emplace_back(it->path().filename().u8string(), it->path());
  }
  if (ec) throw failure{EXR_RELAY_IO, "cannot list a directory"};
  for (auto &child : children) {
    check_name(child.first);
    std::string path = relative.empty() ? child.first : relative + "/" + child.first;
    if (path.size() > EXR_RELAY_MAX_PATH_BYTES) throw failure{EXR_RELAY_LIMIT, "path exceeds the path byte ceiling"};
    fs::file_status status = fs::symlink_status(child.second, ec);
    if (ec) throw failure{EXR_RELAY_IO, "cannot stat an entry"};
    if (status.type() == fs::file_type::directory) {
      if (depth + 1 > ctx.limits.depth) throw failure{EXR_RELAY_LIMIT, "directory depth exceeds max_depth"};
      record r;
      r.path = path;
      r.dir = true;
      ctx.records.push_back(r);
      walk(ctx, child.second, path, depth + 1);
    } else if (status.type() == fs::file_type::regular) {
      if (depth + 1 > ctx.limits.depth) throw failure{EXR_RELAY_LIMIT, "file depth exceeds max_depth"};
      if (ctx.files + 1 > ctx.limits.files) throw failure{EXR_RELAY_LIMIT, "file count exceeds max_files"};
      record r;
      r.path = path;
      r.sha = hash_file(child.second, ctx.limits.file_bytes, ctx.control, r.bytes);
      if (ctx.total + r.bytes < ctx.total || ctx.total + r.bytes > ctx.limits.total_bytes)
        throw failure{EXR_RELAY_LIMIT, "tree exceeds max_total_bytes"};
      ctx.total += r.bytes;
      ctx.files++;
      ctx.records.push_back(r);
    } else {
      throw failure{EXR_RELAY_UNSAFE, "symlink or special file in the tree: " + path};
    }
  }
}

std::string canonical(const exr_relay_limits *limits, const exr_relay_control *control, const char *root_utf8) {
  if (!root_utf8 || !*root_utf8) throw failure{EXR_RELAY_ARGUMENT, "root is required"};
  scan ctx;
  ctx.limits = resolve_limits(limits);
  ctx.control = control;
  fs::path root = fs::u8path(root_utf8);
  std::error_code ec;
  fs::file_status status = fs::symlink_status(root, ec);
  if (ec || status.type() != fs::file_type::directory) throw failure{EXR_RELAY_IO, "root is not a readable directory"};
  walk(ctx, root, "", 0);
  std::sort(ctx.records.begin(), ctx.records.end(), [](const record &a, const record &b) { return a.path < b.path; });
  std::vector<const record *> dirs, files;
  for (const record &r : ctx.records) (r.dir ? dirs : files).push_back(&r);
  sha256 digest;
  auto feed = [&](const std::string &line) { digest.update(line.data(), line.size()); };
  for (const record *r : dirs) feed("D\t" + r->path + "\n");
  for (const record *r : files) feed("F\t" + std::to_string(r->bytes) + "\t" + r->sha + "\t" + r->path + "\n");
  std::string out = "{\"format\":\"exr-relay-inventory-1\",\n";
  out += "\"file_count\":" + std::to_string(files.size()) + ",\"dir_count\":" + std::to_string(dirs.size()) +
         ",\"total_bytes\":" + std::to_string(ctx.total) + ",\"digest\":\"" + digest.finish() + "\",\n";
  out += "\"dirs\":[\n";
  for (size_t i = 0; i < dirs.size(); i++) out += "\"" + dirs[i]->path + "\"" + (i + 1 < dirs.size() ? ",\n" : "\n");
  out += "],\n\"files\":[\n";
  for (size_t i = 0; i < files.size(); i++)
    out += "{\"path\":\"" + files[i]->path + "\",\"bytes\":" + std::to_string(files[i]->bytes) + ",\"sha256\":\"" + files[i]->sha +
           "\"}" + (i + 1 < files.size() ? ",\n" : "\n");
  out += "]}\n";
  if (out.size() > EXR_RELAY_MAX_INVENTORY_BYTES) throw failure{EXR_RELAY_LIMIT, "inventory exceeds the document ceiling"};
  return out;
}

std::string line_at(const std::string &s, size_t index, bool trim = true) {
  size_t start = 0;
  for (size_t i = 0; i < index; i++) {
    size_t at = s.find('\n', start);
    if (at == std::string::npos) return "<end of document>";
    start = at + 1;
  }
  size_t at = s.find('\n', start);
  std::string line = s.substr(start, at == std::string::npos ? std::string::npos : at - start);
  if (trim && line.size() > 60) line.resize(60);
  return line;
}

const char kHeader[] = "{\"format\":\"exr-relay-inventory-1\",\n";

}  // namespace

extern "C" {

exr_relay_status exr_relay_inventory(const char *root_utf8, const exr_relay_limits *limits, const exr_relay_control *control,
                                     char **json, size_t *json_bytes, exr_relay_error *error) {
  begin(error);
  if (json) *json = nullptr;
  if (json_bytes) *json_bytes = 0;
  try {
    if (!json || !json_bytes) throw failure{EXR_RELAY_ARGUMENT, "output pointers are required"};
    std::string doc = canonical(limits, control, root_utf8);
    char *memory = static_cast<char *>(std::malloc(doc.size() + 1));
    if (!memory) throw failure{EXR_RELAY_MEMORY, "out of memory"};
    std::memcpy(memory, doc.c_str(), doc.size() + 1);
    *json = memory;
    *json_bytes = doc.size();
    return EXR_RELAY_OK;
  } catch (const failure &f) {
    report(error, f);
    return f.code;
  } catch (const std::bad_alloc &) {
    report(error, failure{EXR_RELAY_MEMORY, "out of memory"});
    return EXR_RELAY_MEMORY;
  } catch (...) {
    report(error, failure{EXR_RELAY_IO, "unexpected failure"});
    return EXR_RELAY_IO;
  }
}

exr_relay_status exr_relay_verify(const char *root_utf8, const char *json, size_t json_bytes, const exr_relay_limits *limits,
                                  const exr_relay_control *control, exr_relay_error *error) {
  begin(error);
  try {
    if (!json) throw failure{EXR_RELAY_ARGUMENT, "inventory is required"};
    if (json_bytes > EXR_RELAY_MAX_INVENTORY_BYTES) throw failure{EXR_RELAY_LIMIT, "inventory exceeds the document ceiling"};
    std::string given(json, json_bytes);
    if (given.compare(0, sizeof kHeader - 1, kHeader) != 0) throw failure{EXR_RELAY_FORMAT, "not an exr-relay-inventory-1 document"};
    std::string actual = canonical(limits, control, root_utf8);
    if (actual == given) return EXR_RELAY_OK;
    size_t line = 0;
    while (line_at(actual, line, false) == line_at(given, line, false) && line_at(actual, line, false) != "<end of document>") line++;
    throw failure{EXR_RELAY_MISMATCH, "tree differs from the inventory at line " + std::to_string(line) + ": tree has [" + line_at(actual, line) +
                                          "] inventory has [" + line_at(given, line) + "]"};
  } catch (const failure &f) {
    report(error, f);
    return f.code;
  } catch (const std::bad_alloc &) {
    report(error, failure{EXR_RELAY_MEMORY, "out of memory"});
    return EXR_RELAY_MEMORY;
  } catch (...) {
    report(error, failure{EXR_RELAY_IO, "unexpected failure"});
    return EXR_RELAY_IO;
  }
}

exr_relay_status exr_relay_sha256_file(const char *path_utf8, uint64_t max_bytes, const exr_relay_control *control, char out_hex[65],
                                       uint64_t *bytes, exr_relay_error *error) {
  begin(error);
  if (out_hex) out_hex[0] = 0;
  if (bytes) *bytes = 0;
  try {
    if (!path_utf8 || !*path_utf8 || !out_hex || !bytes) throw failure{EXR_RELAY_ARGUMENT, "path and outputs are required"};
    if (max_bytes > EXR_RELAY_MAX_FILE_BYTES) throw failure{EXR_RELAY_ARGUMENT, "max_bytes above the hard ceiling"};
    fs::path path = fs::u8path(path_utf8);
    std::error_code ec;
    fs::file_status status = fs::symlink_status(path, ec);
    if (ec) throw failure{EXR_RELAY_IO, "cannot stat the file"};
    if (status.type() != fs::file_type::regular) throw failure{EXR_RELAY_UNSAFE, "not a regular file"};
    uint64_t count = 0;
    std::string hex = hash_file(path, max_bytes ? max_bytes : EXR_RELAY_MAX_FILE_BYTES, control, count);
    std::memcpy(out_hex, hex.c_str(), 65);
    *bytes = count;
    return EXR_RELAY_OK;
  } catch (const failure &f) {
    report(error, f);
    return f.code;
  } catch (const std::bad_alloc &) {
    report(error, failure{EXR_RELAY_MEMORY, "out of memory"});
    return EXR_RELAY_MEMORY;
  } catch (...) {
    report(error, failure{EXR_RELAY_IO, "unexpected failure"});
    return EXR_RELAY_IO;
  }
}

void exr_relay_free(void *memory) { std::free(memory); }

}  // extern "C"
