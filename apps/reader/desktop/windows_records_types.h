/* SPDX-License-Identifier: MIT */
#include "windows_records_owner.h"
enum {IDC_RECORDS=210,IDC_RECORDS_ROWS,IDC_RECORDS_MESSAGE,IDC_RECORDS_BODY,
 IDC_RECORDS_PROGRESS,IDC_RECORDS_BOOKMARK,IDC_RECORDS_HIGHLIGHT,IDC_RECORDS_EDIT,
 IDC_RECORDS_DELETE,IDC_RECORDS_RESTORE,IDC_RECORDS_OPEN,IDC_RECORDS_PREVIOUS,
 IDC_RECORDS_NEXT,IDC_RECORDS_REFRESH,IDC_RECORDS_RETRY,IDC_RECORDS_DISCARD,
 IDC_RECORDS_CANCEL,IDC_RECORDS_CLOSE};
static struct {
 HWND button,dialog,rows,message,body,controls[14];
 winrecords_response result;
 int running,history,history_progress;
 unsigned long generation;
 int64_t book_id;
 char history_annotation[33],history_head[33],history_sha[65];
} records;
