/* SPDX-License-Identifier: MIT */
/* Independent C11 consumer of the installed public header. It opens a product
   catalog written by the C++ probe, lists one book through the whole ownership
   cycle (view, pages, strings, free, close) and prints the observed totals.
   usage: annotation-view-c-consumer DB BOOK_KEY EXPECTED_COUNT */
#include <reader_annotation_view.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv) {
  reader_revisions *store = NULL;
  reader_revision_error revision_error;
  reader_av_view *view = NULL;
  reader_av_error error;
  reader_av_cursor cursor;
  size_t total = 0, safe = 0, unavailable = 0, tombstones = 0, bytes = 0, pages = 0;
  unsigned long expected;
  int failed = 0;
  if (argc != 4) { fprintf(stderr, "usage: db book count\n"); return 2; }
  expected = strtoul(argv[3], NULL, 10);
  memset(&revision_error, 0, sizeof(revision_error));
  if (reader_revisions_open(argv[1], &store, &revision_error) != READER_REV_OK) { fprintf(stderr, "open: %s\n", revision_error.message); return 2; }
  if (reader_av_open(store, argv[2], NULL, &view, &error) != READER_AV_OK) { fprintf(stderr, "view: %s\n", error.message); return 2; }
  if (reader_av_cursor_start(view, 1, &cursor, &error) != READER_AV_OK) { fprintf(stderr, "cursor: %s\n", error.message); return 2; }
  for (;;) {
    reader_av_page page;
    size_t i;
    int done;
    if (reader_av_page_get(view, &cursor, READER_AV_BATCH_MAX, &page, &error) != READER_AV_OK) { fprintf(stderr, "page: %s\n", error.message); failed = 1; break; }
    pages++;
    for (i = 0; i < page.count; i++) {
      const reader_av_item *item = &page.items[i];
      total++;
      if (item->state == READER_AV_STATE_SAFE) safe++; else unavailable++;
      if (item->kind == READER_AV_KIND_TOMBSTONE) tombstones++;
      if (item->content_available) bytes += item->exact_size + item->note_size;
      if (item->state != READER_AV_STATE_SAFE && (item->exact || item->note_text || item->revision_id[0])) failed = 1;
      if (item->resolution != READER_AV_RESOLUTION_NOT_ATTEMPTED) failed = 1;
    }
    done = page.complete;
    cursor = page.next;
    reader_av_page_free(&page);
    if (done) break;
  }
  if (reader_av_close(&view, &error) != READER_AV_OK || view != NULL) failed = 1;
  if (reader_revisions_close(&store, &revision_error) != READER_REV_OK) failed = 1;
  if (total != expected) failed = 1;
  printf("%s total=%zu safe=%zu unavailable=%zu tombstones=%zu pages=%zu bytes=%zu failed=%d\n", READER_ANNOTATION_VIEW_VERSION, total, safe, unavailable,
         tombstones, pages, bytes, failed);
  return failed;
}
