/* SPDX-License-Identifier: MIT */
#ifndef WINDOWS_IMPORT_ORGANIZE_TYPES_H
#define WINDOWS_IMPORT_ORGANIZE_TYPES_H
#include <reader_cloud_import.h>
#include <reader_bulk.h>
/* IDs do not move any retained host controls. */
enum { IDC_CLOUD_IMPORT=240, IDC_BULK_ORGANIZE, IDC_IO_ROWS, IDC_IO_MESSAGE,
  IDC_IO_GO, IDC_IO_CANCEL, IDC_IO_CLOSE, IDC_IO_ROOT, IDC_IO_UP,
  IDC_IO_ACTION, IDC_IO_GROUPS, IDC_IO_MORE, IDC_IO_RESUME, IDC_IO_ACK,
  IDC_IO_CLEANUP, IDC_IO_REPORT, IDC_IO_NAME, IDC_IO_CREATE_GROUP, IDC_IO_RECOVER_EDIT, IDC_IO_ABANDON_EDIT };
enum { WINIO_CLOUD=1, WINIO_BULK };
enum { WINIO_LIST=1, WINIO_DOWNLOAD, WINIO_IMPORT, WINIO_CLEAN,
  WINIO_GROUPS, WINIO_RUN, WINIO_RESUME, WINIO_INSPECT, WINIO_ACK,
  WINIO_CREATE_GROUP, WINIO_RECOVER_EDIT, WINIO_ABANDON_EDIT };
typedef struct { char id[33],parent[33];uint64_t ordinal;wchar_t name[512]; } winio_group;
typedef struct {
  int operation,mode,action,group_kind,more;
  unsigned long generation;
  char account[37],resource[4097],name[1025],group[33],parent[33],after[33];
  uint64_t bytes,after_ordinal;
  char keys[READER_BULK_MAX_BATCH][73];int64_t ids[READER_BULK_MAX_BATCH];size_t count;
  exr_webdav_listing listing;
  exr_webdav_error dav_error;
  reader_cloud_staged *staged;
  reader_cloud_error cloud_error;
  reader_cloud_import_result imported;
  reader_cloud_status cloud_status;
  reader_bulk_status bulk_status;
  reader_bulk_error bulk_error;
  reader_bulk_summary summary;
  reader_bulk_item_result results[READER_BULK_MAX_BATCH];
  char superseded_bootstrap[33];
  winio_group groups[200];size_t group_count;
  int mapped,receipt_saved,prepared,bootstrap_pending,edit_committed,edit_pending;
} winio_job;
static void winio_job_free(winio_job *value);
static int winio_modal_blocked(void);
#endif
