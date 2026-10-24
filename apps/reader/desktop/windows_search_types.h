/* SPDX-License-Identifier: MIT */
#include <reader_search.h>
#define HOST_SEARCH_BATCH 32
enum { IDC_INBOOK = 170, IDC_INBOOK_QUERY, IDC_INBOOK_FIND, IDC_INBOOK_NEXT,
  IDC_INBOOK_HITS, IDC_INBOOK_OPEN, IDC_INBOOK_CANCEL, IDC_INBOOK_CLOSE,
  IDC_INBOOK_MESSAGE };
/* UI-owned copies: no borrowed SDK handles, provider text or module results. */
typedef struct {
  reader_search_mode mode;
  uint64_t unit;
  char *part_path, *page_id;
  exr_anchor anchor;
  exr_fixed_anchor fixed;
} host_search_hit;
typedef struct {
  host_search_hit hits[HOST_SEARCH_BATCH];
  size_t count;
  reader_search_cursor next;
  int complete;
} host_search_batch;
static struct {
  HWND button, dialog, query, find, next, rows, open, cancel, message;
  host_search_batch batch;
  unsigned long generation;
  int64_t book_id;
  int have_cursor, running;
} inbook;
