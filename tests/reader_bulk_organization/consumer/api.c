/* SPDX-License-Identifier: MIT */
/* Pure C consumer of the installed C ABI: seeds one book, favorites it through a
 * one-item batch, acknowledges the report and verifies the journal is gone. */
#include <reader_bulk.h>
#include <catalog.h>
#include <stdio.h>
#include <string.h>

int main(int argc, char **argv) {
  reader_catalog *catalog = NULL;
  reader_catalog_error ce;
  reader_catalog_book book = {"txt", "0000000000000000000000000000000000000000000000000000000000000001",
    "c-book", "c-author", "c-book", "reflow_global", 100, 1000, 0};
  reader_metadata_owner *owner = NULL;
  reader_metadata_error me;
  reader_metadata_snapshot *snapshot = NULL;
  reader_metadata_verified_source source = {"txt", "0000000000000000000000000000000000000000000000000000000000000001", 100};
  reader_metadata_result staged, done;
  reader_bulk *bulk = NULL;
  reader_bulk_error be;
  reader_bulk_item_result item;
  reader_bulk_summary summary;
  const char *keys[1] = {"txt:0000000000000000000000000000000000000000000000000000000000000001"};
  reader_bulk_request request;
  FILE *probe;
  if (argc < 4) return 2;
  memset(&ce, 0, sizeof ce); memset(&me, 0, sizeof me); memset(&be, 0, sizeof be);
  if (reader_catalog_open(argv[1], &catalog, &ce) || reader_catalog_attach(catalog, &book, &ce) ||
      reader_catalog_close(&catalog, &ce)) return 3;
  if (reader_metadata_open(argv[1], argv[2], &owner, &me) != READER_METADATA_OK) return 4;
  if (reader_metadata_prepare_book(owner, keys[0], &snapshot, &me) != READER_METADATA_NEEDS_BOOTSTRAP) return 5;
  if (reader_metadata_stage_bootstrap(owner, snapshot, &source, &staged, &me) != READER_METADATA_OK) return 6;
  reader_metadata_snapshot_free(snapshot);
  if (reader_metadata_finish_pending(owner, &done, &me) != READER_METADATA_OK) return 7;
  if (reader_bulk_open(owner, argv[1], argv[3], &bulk, &be) != READER_BULK_OK) return 8;
  memset(&request, 0, sizeof request);
  request.struct_size = sizeof request;
  request.action = READER_BULK_FAVORITE_SET;
  request.book_keys = keys;
  request.book_count = 1;
  if (reader_bulk_run(bulk, &request, &item, 1, &summary, &be) != READER_BULK_OK) return 9;
  if (!summary.complete || summary.committed != 1 || !item.committed || !item.created || item.head_count != 1) return 10;
  /* Journal survives until acknowledged, then disappears. */
  probe = fopen(argv[3], "rb");
  if (!probe) return 11;
  fclose(probe);
  if (reader_bulk_acknowledge(bulk, &be) != READER_BULK_OK) return 12;
  probe = fopen(argv[3], "rb");
  if (probe) { fclose(probe); return 13; }
  if (reader_bulk_run(bulk, &request, &item, 1, &summary, &be) != READER_BULK_OK || summary.unchanged != 1) return 14;
  if (reader_bulk_acknowledge(bulk, &be) != READER_BULK_OK) return 15;
  if (reader_bulk_close(&bulk, &be) != READER_BULK_OK || reader_metadata_close(&owner, &me) != READER_METADATA_OK) return 16;
  printf("c-abi-ok\n");
  return 0;
}
