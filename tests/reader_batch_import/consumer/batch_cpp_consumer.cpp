/* SPDX-License-Identifier: MIT */
#include <reader_batch_import.h>
#include <cstdio>
#include <cstring>

int main(int argc, char **argv) {
  reader_batch_scan_options scan;
  reader_batch_import_options import;
  reader_batch_scan_options_init(&scan);
  reader_batch_import_options_init(&import);
  if (scan.struct_size != sizeof(scan) || import.struct_size != sizeof(import))
    return 1;
  if (scan.batch_size < 1 || scan.batch_size > READER_BATCH_MAX_BATCH)
    return 1;
  if (std::strcmp(reader_batch_status_name(READER_BATCH_OK), "OK") != 0)
    return 1;
  if (std::strcmp(reader_batch_item_status_name(READER_BATCH_ITEM_DUPLICATE),
                  "DUPLICATE") != 0)
    return 1;
  if (std::strcmp(reader_batch_format_name(EXR_EPUB), "EPUB") != 0)
    return 1;
  if (argc > 1 && std::strcmp(argv[1], "--selftest") == 0) {
    std::printf("batch-import-cpp-selftest ok\n");
    return 0;
  }
  return 0;
}
