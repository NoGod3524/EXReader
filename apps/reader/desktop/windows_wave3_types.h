/* SPDX-License-Identifier: MIT
 * C09 native Windows adoption of the reviewed wave-3 optional packages.
 * Only the installed public headers are used. The explicit raw 0.2 family is
 * required: this host never mixes it with the legacy store family.
 */
#ifndef EXREADER_WINDOWS_WAVE3_TYPES_H
#define EXREADER_WINDOWS_WAVE3_TYPES_H
#if !defined(EXR_READER_WINDOWS_RAW3) || !defined(EXR_READER_WINDOWS_RECORDS) || !defined(EXR_READER_WINDOWS_ACCOUNT) || !defined(EXR_READER_WINDOWS_COMPACT)
#error "Wave-3 Windows features require the raw, records, account and compact host profile"
#endif
#include <reader_annotation_import_raw3.h>
#include <reader_annotation_export_raw3.h>
#include <reader_font_library.h>
#include <reader_original_export.h>
#include <reader_jump_history.h>
#include <reader_sync_view.h>
#include <reader_reading_state_capture_raw_candidate.h>
#ifdef __cplusplus
extern "C" {
#endif
/* A full product snapshot: a missing raw revision store is an error, never an
   empty pending queue. Open, read and close stay on this caller's owner thread. */
reader_sync_view_status w3_sync_capture(reader_session *,const char *database_utf8,
  reader_sync_view_snapshot **out,reader_sync_view_error *);
#ifdef __cplusplus
}
#endif
typedef struct w3_job w3_job;
#endif
