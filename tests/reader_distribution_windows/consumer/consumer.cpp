// SPDX-License-Identifier: MIT
// Installed-distribution C++ consumer: proves the shipped headers are usable as
// C++ translation units and that the C ABI links from a relocated prefix.
#include <cstdio>
#include <cstring>
#include <string>
#include <exreader.h>

namespace {

std::string escape(const char* value) {
  std::string result;
  for (const unsigned char* cursor = reinterpret_cast<const unsigned char*>(value); *cursor; ++cursor) {
    if (*cursor == '\\' || *cursor == '"') {
      result.push_back('\\');
      result.push_back(static_cast<char>(*cursor));
    } else if (*cursor < 0x20) {
      char buffer[8];
      std::snprintf(buffer, sizeof(buffer), "\\u%04x", *cursor);
      result += buffer;
    } else {
      result.push_back(static_cast<char>(*cursor));
    }
  }
  return result;
}

}  // namespace

int main(int argc, char** argv) {
  if (argc != 2) {
    std::fprintf(stderr, "usage: consumer-cpp <output.json>\n");
    return 2;
  }
  const exr_layout_config config = exr_layout_config_defaults();
  const std::string version{exr_version()};
  const unsigned abi = static_cast<unsigned>(exr_abi_version());
  const bool layout_valid = config.page.width > 0 && config.page.height > 0;
  const bool passed = !version.empty() && abi == EXR_ABI_VERSION && layout_valid &&
                      std::strcmp(EXR_VERSION, exr_version()) == 0;
  std::FILE* stream = std::fopen(argv[1], "wb");
  if (!stream) {
    return 3;
  }
  std::fprintf(stream,
               "{\"schema\":\"reader-distribution-windows-consumer-v1\",\"consumer\":\"cpp17\","
               "\"sdk_version\":\"%s\",\"abi\":%u,\"page_width\":%.1f,\"page_height\":%.1f,"
               "\"passed\":%s}\n",
               escape(version.c_str()).c_str(), abi, config.page.width, config.page.height,
               passed ? "true" : "false");
  std::fclose(stream);
  return passed ? 0 : 1;
}
