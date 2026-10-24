// SPDX-License-Identifier: MIT
#include <reader_local_downloads.h>
#include <cstdio>
#include <cstring>

int main() {
  reader_ld_options options;
  reader_ld_result result;
  reader_ld_pending_info info;
  reader_ld_error error;
  reader_ld_options_init(&options);
  reader_ld_result_init(&result);
  std::memset(&info, 0, sizeof(info));
  info.struct_size = sizeof(info);
  // An unusable state directory must be rejected before any database is touched.
  options.state_dir = "";
  if (reader_ld_remove(&options, "txt:0000000000000000000000000000000000000000000000000000000000000000",
        &result, &error) != READER_LD_ARGUMENT)
    return 1;
  if (reader_ld_pending("", &info, &error) != READER_LD_ARGUMENT) return 1;
  if (std::strcmp(READER_LD_VERSION, "0.1.0") != 0) return 1;
  if (std::strcmp(reader_ld_status_name(READER_LD_LEGACY_DATA), "legacy_data") != 0) return 1;
  std::printf("CPP ok version=%s\n", READER_LD_VERSION);
  return 0;
}
