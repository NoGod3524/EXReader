/* SPDX-License-Identifier: MIT */
/* Installed C++ consumer: named positive and negative cases for the relay
   component. Usage: relay-consumer <empty work dir> <report.json> */
#include <exr_relay.h>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

namespace fs = std::filesystem;
namespace {
struct result { std::string name, status, detail; };
std::vector<result> results;
void pass(const std::string &n) { results.push_back({n, "pass", ""}); }
void fail(const std::string &n, const std::string &d) { results.push_back({n, "fail", d}); std::fprintf(stderr, "FAIL %s %s\n", n.c_str(), d.c_str()); }
void skip(const std::string &n, const std::string &d) { results.push_back({n, "skip", d}); }
void check(bool ok, const std::string &n, const std::string &d = "") { if (ok) pass(n); else fail(n, d); }
const char *name(exr_relay_status s) {
  static const char *n[] = {"OK", "ARGUMENT", "MEMORY", "IO", "LIMIT", "FORMAT", "CANCELLED", "UNSAFE", "MISMATCH"};
  return (unsigned)s < 9 ? n[s] : "UNKNOWN";
}
void write(const fs::path &p, const std::string &data) {
  fs::create_directories(p.parent_path());
  std::ofstream out(p, std::ios::binary);
  out.write(data.data(), (std::streamsize)data.size());
}
std::string u8(const char *s) { return s; }
std::string esc(const std::string &s) {
  std::string o;
  for (unsigned char c : s) { if (c == '"' || c == '\\') { o += '\\'; o += (char)c; } else if (c < 0x20) o += ' '; else o += (char)c; }
  return o;
}
struct cancel_after { int polls; int seen = 0; };
int cancel_cb(void *p) { auto *c = static_cast<cancel_after *>(p); return ++c->seen > c->polls; }

exr_relay_status inventory(const fs::path &root, std::string &doc, exr_relay_error &e, const exr_relay_limits *limits = nullptr,
                           const exr_relay_control *control = nullptr) {
  char *json = nullptr;
  size_t n = 0;
  exr_relay_status st = exr_relay_inventory(root.u8string().c_str(), limits, control, &json, &n, &e);
  if (st == EXR_RELAY_OK) doc.assign(json, n); else if (json || n) fail("failure_leaves_outputs_empty", "output set on failure");
  exr_relay_free(json);
  return st;
}
exr_relay_status verify(const fs::path &root, const std::string &doc, exr_relay_error &e) {
  return exr_relay_verify(root.u8string().c_str(), doc.data(), doc.size(), nullptr, nullptr, &e);
}
}  // namespace

int main(int argc, char **argv) {
  if (argc != 3) return 64;
  fs::path work = fs::u8path(argv[1]);
  exr_relay_error e{};
  /* Known SHA-256 vectors, independent of the inventory format. */
  write(work / "v" / "empty", "");
  write(work / "v" / "abc", "abc");
  write(work / "v" / "million", std::string(1000000, 'a'));
  struct { const char *file, *hex; uint64_t bytes; } vectors[] = {
    {"empty", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", 0},
    {"abc", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", 3},
    {"million", "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0", 1000000}};
  for (auto &v : vectors) {
    char hex[65];
    uint64_t bytes = 0;
    exr_relay_status st = exr_relay_sha256_file((work / "v" / v.file).u8string().c_str(), 0, nullptr, hex, &bytes, &e);
    check(st == EXR_RELAY_OK && !std::strcmp(hex, v.hex) && bytes == v.bytes, std::string("sha256_vector_") + v.file, std::string(name(st)) + " " + hex);
  }

  /* A tree shaped like a native WebDAV service plus every text class the product must keep. */
  fs::path tree = work / "tree";
  std::string nfc = u8("caf\xc3\xa9-nfc.txt"), nfd = u8("cafe\xcc\x81-nfd.txt"), ru = u8("\xd0\x92\xd0\xbe\xd0\xb9\xd0\xbd\xd0\xb0.txt"), em = u8("\xf0\x9f\x99\x82 emoji.txt");
  write(tree / "exreader-sync-v1" / "objects" / "ab" / "ab.txt", "original bytes");
  write(tree / "exreader-sync-v1" / "revisions" / "cd" / "cd.json", "{\"version\":1}");
  for (const std::string &n : {nfc, nfd, ru, em}) write(tree / "names" / fs::u8path(n), n);
  fs::create_directories(tree / "empty-dir");
  std::string doc;
  exr_relay_status st = inventory(tree, doc, e);
  check(st == EXR_RELAY_OK && doc.find("\"file_count\":6") != std::string::npos && doc.find("\"dir_count\":7") != std::string::npos, "inventory_counts_files_and_directories", name(st));
  std::string again;
  check(inventory(tree, again, e) == EXR_RELAY_OK && again == doc, "inventory_is_deterministic");
  {
    /* Apple file systems may report a different normalization form than the one created; both are valid exact names. */
    bool nfc_ok = doc.find(nfc) != std::string::npos || doc.find(nfd) != std::string::npos;
    check(nfc_ok && doc.find(ru) != std::string::npos && doc.find(em) != std::string::npos, "inventory_keeps_nfc_nfd_russian_emoji_names_unmodified");
  }
  check(verify(tree, doc, e) == EXR_RELAY_OK, "verify_accepts_the_unmodified_tree");

  /* Negative cases, each against a freshly copied tree. */
  auto fresh = [&](const char *label) { fs::path p = work / label; fs::copy(tree, p, fs::copy_options::recursive); return p; };
  { fs::path t = fresh("altered"); write(t / "exreader-sync-v1" / "objects" / "ab" / "ab.txt", "original byteS");
    st = verify(t, doc, e); check(st == EXR_RELAY_MISMATCH && std::string(e.message).find("line") != std::string::npos, "verify_rejects_altered_byte_same_length", name(st)); }
  { fs::path t = fresh("truncated"); write(t / "exreader-sync-v1" / "objects" / "ab" / "ab.txt", "original");
    st = verify(t, doc, e); check(st == EXR_RELAY_MISMATCH, "verify_rejects_truncated_file", name(st)); }
  { fs::path t = fresh("extra"); write(t / "exreader-sync-v1" / "objects" / "ab" / "extra.txt", "x");
    st = verify(t, doc, e); check(st == EXR_RELAY_MISMATCH, "verify_rejects_extra_file", name(st)); }
  { fs::path t = fresh("missing"); fs::remove(t / "exreader-sync-v1" / "revisions" / "cd" / "cd.json");
    st = verify(t, doc, e); check(st == EXR_RELAY_MISMATCH, "verify_rejects_missing_file", name(st)); }
  { fs::path t = fresh("emptydir"); fs::remove(t / "empty-dir");
    st = verify(t, doc, e); check(st == EXR_RELAY_MISMATCH, "verify_rejects_missing_directory", name(st)); }
  { fs::path t = fresh("renamed"); fs::rename(t / "names" / fs::u8path(ru), t / "names" / "renamed.txt");
    st = verify(t, doc, e); check(st == EXR_RELAY_MISMATCH, "verify_rejects_renamed_file", name(st)); }
  { std::string cut = doc.substr(0, doc.size() / 2);
    st = verify(tree, cut, e); check(st == EXR_RELAY_MISMATCH, "verify_rejects_truncated_inventory", name(st)); }
  { std::string spaced = doc; spaced.insert(spaced.find("\"files\""), " ");
    st = verify(tree, spaced, e); check(st == EXR_RELAY_MISMATCH, "verify_rejects_noncanonical_inventory", name(st)); }
  { std::string other = "{\"format\":\"other\"}\n";
    st = verify(tree, other, e); check(st == EXR_RELAY_FORMAT, "verify_rejects_foreign_document", name(st)); }
  { std::string forged = doc; size_t at = forged.find("\"digest\":\"") + 10; forged[at] = forged[at] == '0' ? '1' : '0';
    st = verify(tree, forged, e); check(st == EXR_RELAY_MISMATCH, "verify_rejects_forged_digest", name(st)); }

  /* Symlinks are refused; creating one can need privileges on Windows. */
  { fs::path t = fresh("symlink"); std::error_code ec; fs::create_symlink(t / "names" / "x", t / "link", ec);
    if (ec) skip("inventory_refuses_symlink", "symlink creation not permitted: " + ec.message());
    else { std::string d; st = inventory(t, d, e); check(st == EXR_RELAY_UNSAFE, "inventory_refuses_symlink", name(st)); } }
  { fs::path t = fresh("badname"); std::error_code ec; bool made = false;
    std::ofstream out(t / "bad\"quote.txt", std::ios::binary); made = (bool)out; out.close();
    if (!made) skip("inventory_refuses_quote_in_name", "file system refuses the name");
    else { std::string d; st = inventory(t, d, e); check(st == EXR_RELAY_UNSAFE, "inventory_refuses_quote_in_name", name(st)); } }

  /* Limits may only lower the ceilings. */
  { exr_relay_limits l{}; l.struct_size = sizeof l; l.max_files = 2; std::string d; st = inventory(tree, d, e, &l);
    check(st == EXR_RELAY_LIMIT && d.empty(), "limit_max_files_rejects_whole_tree_not_truncates", name(st)); }
  { exr_relay_limits l{}; l.struct_size = sizeof l; l.max_depth = 2; std::string d; st = inventory(tree, d, e, &l); check(st == EXR_RELAY_LIMIT, "limit_max_depth", name(st)); }
  { exr_relay_limits l{}; l.struct_size = sizeof l; l.max_file_bytes = 10; std::string d; st = inventory(tree, d, e, &l); check(st == EXR_RELAY_LIMIT, "limit_max_file_bytes", name(st)); }
  { exr_relay_limits l{}; l.struct_size = sizeof l; l.max_total_bytes = 20; std::string d; st = inventory(tree, d, e, &l); check(st == EXR_RELAY_LIMIT, "limit_max_total_bytes", name(st)); }
  { exr_relay_limits l{}; l.struct_size = sizeof l; l.max_files = EXR_RELAY_MAX_FILES + 1; std::string d; st = inventory(tree, d, e, &l); check(st == EXR_RELAY_ARGUMENT, "limit_above_ceiling_refused", name(st)); }
  { exr_relay_limits l{}; l.struct_size = 4; std::string d; st = inventory(tree, d, e, &l); check(st == EXR_RELAY_ARGUMENT, "limit_struct_too_short_refused", name(st)); }
  { char hex[65]; uint64_t b = 0; st = exr_relay_sha256_file((work / "v" / "million").u8string().c_str(), 10, nullptr, hex, &b, &e);
    check(st == EXR_RELAY_LIMIT && !hex[0], "sha256_file_limit", name(st)); }

  /* Cancellation: before any work and in the middle of a multi-chunk file. */
  { cancel_after c{0}; exr_relay_control ctl{cancel_cb, &c}; std::string d; st = inventory(tree, d, e, nullptr, &ctl);
    check(st == EXR_RELAY_CANCELLED && d.empty(), "cancel_before_first_directory", name(st)); }
  { cancel_after c{3}; exr_relay_control ctl{cancel_cb, &c}; char hex[65]; uint64_t b = 0;
    st = exr_relay_sha256_file((work / "v" / "million").u8string().c_str(), 0, &ctl, hex, &b, &e);
    check(st == EXR_RELAY_CANCELLED && !hex[0] && b == 0, "cancel_in_the_middle_of_a_file", name(st)); }

  /* Argument, I/O and ownership rules. */
  { char *j = (char *)1; size_t n = 1; st = exr_relay_inventory(nullptr, nullptr, nullptr, &j, &n, &e); check(st == EXR_RELAY_ARGUMENT && !j && !n, "null_root_refused", name(st)); }
  { std::string d; st = inventory(work / "does-not-exist", d, e); check(st == EXR_RELAY_IO, "missing_root_is_io", name(st)); }
  { std::string d; st = inventory(work / "v" / "abc", d, e); check(st == EXR_RELAY_IO, "file_root_is_io", name(st)); }
  { exr_relay_free(nullptr); pass("free_null_is_noop"); }
  check(!std::strcmp(EXR_RELAY_VERSION, "0.1.0"), "version_constant");

  size_t failures = 0, skips = 0;
  std::string out = "{\"component\":\"exr_relay\",\"version\":\"" EXR_RELAY_VERSION "\",\"checks\":[";
  for (size_t i = 0; i < results.size(); i++) {
    failures += results[i].status == "fail";
    skips += results[i].status == "skip";
    out += std::string(i ? "," : "") + "{\"name\":\"" + results[i].name + "\",\"status\":\"" + results[i].status + "\",\"detail\":\"" + esc(results[i].detail) + "\"}";
  }
  out += "],\"failures\":" + std::to_string(failures) + ",\"skips\":" + std::to_string(skips) + "}\n";
  std::ofstream(argv[2], std::ios::binary) << out;
  std::fputs(out.c_str(), stdout);
  return failures ? 1 : 0;
}
