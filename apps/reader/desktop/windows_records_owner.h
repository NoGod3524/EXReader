/* SPDX-License-Identifier: MIT
 * App-private C boundary. G03/G04 and the installed product provider retain
 * their own public interfaces and versions. Every call owns its store/view
 * on this one worker invocation; only owned values cross the UI boundary.
 */
#ifndef EXREADER_WINDOWS_RECORDS_OWNER_H
#define EXREADER_WINDOWS_RECORDS_OWNER_H
#include <wchar.h>
#include <reader_reading_commands.h>
#include <reader_annotation_view.h>
#include <exr/base.h>
#ifdef __cplusplus
extern "C" {
#endif
enum { WINRECORDS_LIST=1,WINRECORDS_SAVE,WINRECORDS_RETRY,WINRECORDS_DISCARD,
  WINRECORDS_READ,WINRECORDS_HISTORY };
typedef struct {
  const char *database,*book_key;
  const wchar_t *pending_path;
  int64_t sdk_book;
  uint64_t source_bytes;
  int action,kind,operation,progress_target,direction;
  const char *annotation_id,*head,*sha256,*body,*version,*after,*pending_revision;
  void *context;
  int (*cancelled)(void *);
  /* A genuine public SDK capture of the current renderer. A historical input
     first requires independent FOUND and a fresh capture in that same renderer.
     The owner frees anchor/fixed exactly once after the callback returns. */
  exr_status (*capture)(void *,const reader_rs_record *historical,
    reader_rs_capture *,exr_anchor *,exr_fixed_anchor *,size_t *part);
  /* 1: before publication (cancellable); 2: durable original request (commit
     barrier); 3: RC commit returned, before deleting only this request. */
  void (*phase)(void *,int);
} winrecords_request;
typedef struct {
  reader_av_page page;
  reader_revision_selection progress;
  reader_revision_info progress_info;
  reader_rs_record record;
  char key[73],pending_key[73],pending_revision[33],saved_revision[33],saved_annotation[33];
  char versions[32][33];char *version_labels[32];size_t version_count;
  int history_complete,has_previous,has_next,pending,pending_corrupt,created,committed;
  int command_code;
  char message[192];
} winrecords_response;
exr_status winrecords_execute(const winrecords_request *,winrecords_response *);
void winrecords_response_free(winrecords_response *);
#ifdef __cplusplus
}
#endif
#endif
