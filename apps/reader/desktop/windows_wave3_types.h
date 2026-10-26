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
#ifdef __cplusplus
extern "C" {
#endif
/* Thin C bridge: the retained v1/v2 raw encoder has C++ linkage in the installed
   reading-state archive (it is the command module's own boundary). */
reader_rs_status w3_encode_retained(reader_revisions *,const reader_rs_envelope *,const reader_rs_capture *,
  unsigned version,size_t part,char **wire,size_t *bytes,reader_rs_error *);
/* A full product snapshot: a missing raw revision store is an error, never an
   empty pending queue. Open, read and close stay on this caller's owner thread. */
reader_sync_view_status w3_sync_capture(reader_session *,const char *database_utf8,
  reader_sync_view_snapshot **out,reader_sync_view_error *);
#ifdef __cplusplus
}
#endif
typedef struct w3_job w3_job;
#endif
