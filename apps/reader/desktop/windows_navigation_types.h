/* SPDX-License-Identifier: MIT */
#include <reader_navigation.h>
#define HOST_NAV_BATCH 32
enum { IDC_DIRECTORY=190, IDC_DIRECTORY_ROWS, IDC_DIRECTORY_OPEN,
  IDC_DIRECTORY_CHILDREN, IDC_DIRECTORY_UP, IDC_DIRECTORY_PREVIOUS,
  IDC_DIRECTORY_NEXT, IDC_DIRECTORY_CANCEL, IDC_DIRECTORY_CLOSE,
  IDC_DIRECTORY_MESSAGE };
typedef struct {
  reader_navigation_page page;
  reader_navigation_info info;
  reader_navigation_status code;
  uint64_t parent,first;
  uint64_t *candidates;
  size_t candidate_count;
} host_navigation_result;
static struct {
  HWND button,dialog,rows,open,children,up,previous,next,cancel,message;
  host_navigation_result result;
  uint64_t parents[READER_NAVIGATION_DEPTH_MAX],starts[READER_NAVIGATION_DEPTH_MAX];
  size_t depth,candidate_first;
  uint64_t pending_row;
  unsigned long generation;
  int64_t book_id;
  int running,accept_part;
} directory;
