/* SPDX-License-Identifier: MIT */
#include <reader_cloud_import.h>
#include <cstdio>
#include <cstring>

/* Header-only contract check from a C++ translation unit (extern "C"). */
int main() {
  reader_cloud_request request;
  reader_cloud_import_options options;
  reader_cloud_request_init(&request);
  reader_cloud_import_options_init(&options);
  if (request.struct_size != sizeof(request) || options.struct_size != sizeof(options)) return 1;
  if (std::strcmp(reader_cloud_status_name(READER_CLOUD_CORRUPT), "corrupt") != 0) return 1;
  if (reader_cloud_format_from_name("书.PDF") != EXR_PDF) return 1;
  if (reader_cloud_format_from_name("书.exe") != EXR_CUSTOM) return 1;
  std::printf("cloud-import-cpp ok\n");
  return 0;
}
