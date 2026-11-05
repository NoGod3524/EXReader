/* SPDX-License-Identifier: MIT */
/* Installed-package example: relay-tool inventory <root> <out.json>
                              relay-tool verify <root> <inventory.json>
   Exit 0 only on success; the status line on stdout is machine readable. */
#include <exr_relay.h>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <string>

static const char *name(exr_relay_status s) {
  static const char *n[] = {"OK", "ARGUMENT", "MEMORY", "IO", "LIMIT", "FORMAT", "CANCELLED", "UNSAFE", "MISMATCH"};
  return (unsigned)s < 9 ? n[s] : "UNKNOWN";
}

int main(int argc, char **argv) {
  if (argc != 4) { std::fprintf(stderr, "usage: relay-tool inventory|verify <root> <file>\n"); return 64; }
  std::string mode = argv[1];
  exr_relay_error error{};
  if (mode == "inventory") {
    char *json = nullptr;
    size_t bytes = 0;
    exr_relay_status st = exr_relay_inventory(argv[2], nullptr, nullptr, &json, &bytes, &error);
    if (st == EXR_RELAY_OK) {
      std::ofstream out(argv[3], std::ios::binary);
      out.write(json, (std::streamsize)bytes);
      if (!out) st = EXR_RELAY_IO;
    }
    exr_relay_free(json);
    std::printf("{\"mode\":\"inventory\",\"status\":\"%s\",\"bytes\":%zu}\n", name(st), bytes);
    if (st != EXR_RELAY_OK) std::fprintf(stderr, "%s\n", error.message);
    return st == EXR_RELAY_OK ? 0 : 1;
  }
  if (mode == "verify") {
    std::ifstream in(argv[3], std::ios::binary);
    std::string doc((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    exr_relay_status st = in ? exr_relay_verify(argv[2], doc.data(), doc.size(), nullptr, nullptr, &error) : EXR_RELAY_IO;
    std::printf("{\"mode\":\"verify\",\"status\":\"%s\"}\n", name(st));
    if (st != EXR_RELAY_OK) std::fprintf(stderr, "%s\n", error.message);
    return st == EXR_RELAY_OK ? 0 : 1;
  }
  return 64;
}
