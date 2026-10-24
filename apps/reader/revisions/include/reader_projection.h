/* SPDX-License-Identifier: MIT */
#ifndef READER_PROJECTION_H
#define READER_PROJECTION_H
#include <reader_revisions.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef enum {READER_SELECTION_MISSING=0,READER_SELECTION_PENDING_PARENTS,
  READER_SELECTION_CONCURRENT,READER_SELECTION_BLOCKED_RESTORE,READER_SELECTION_SAFE} reader_selection_kind;
typedef struct {reader_selection_kind kind;reader_revision_state graph;} reader_revision_selection;
/* Only book/shelf/tag/series/membership change product metadata tables.
   expected_heads is an unordered set of 0..32 IDs observed by the host. It
   must match the current full head set, and the new wire parents must match it
   exactly, inside the same transaction as metadata+history+outbox.
   book_sort_title is the host's existing NFC title conversion, not wire data;
   required for non-delete book metadata, ignored for other entities.
   Same retained ID/exact bytes is a no-op before the stale-head check, with
   created=applied=0: it neither replays metadata nor requeues history. */
reader_revision_status reader_revision_local_project(reader_revisions *,const void *wire,size_t,
  const char *const *expected_heads,size_t expected_count,const char *book_sort_title,
  reader_revision_info *,int *created,int *applied,reader_revision_error *);
/* Product-owned progress/annotation history+outbox only, with the same complete
   expected-head check and exact-retry semantics. Requires retained verified
   book history. No metadata projection, SDK note copy or current-page write. */
reader_revision_status reader_revision_local_reading(reader_revisions *,const void *wire,size_t,
  const char *const *expected_heads,size_t expected_count,
  reader_revision_info *,int *created,reader_revision_error *);
/* Read current graph and apply only its complete, safe unique expected_head
   in one product transaction. No history/outbox/SDK write. Missing product
   dependencies remain pending; constraints never weaken or rewrite history.
   Entity deletion is soft; membership deletion changes only its derived join. */
reader_revision_status reader_revision_project(reader_revisions *,const char *entity_kind,
  const char *entity_key,const char *expected_head,const char *book_sort_title,
  reader_revision_info *,reader_revision_error *);
/* One snapshot, explicit MISSING/PENDING_PARENTS/CONCURRENT/BLOCKED_RESTORE/SAFE.
   Returns NOT_FOUND for missing, UNSAFE for the three blocked states, and only
   SAFE returns OK plus copied exact wire. Progress/annotation stay authoritative
   here: host resolves selectors with public SDK FOUND before user navigation.
   No SDK database write or automatic active-reading jump occurs. */
reader_revision_status reader_revision_selected(reader_revisions *,const char *entity_kind,
  const char *entity_key,char **wire,size_t *bytes,reader_revision_info *,
  reader_revision_selection *,reader_revision_error *);
#ifdef __cplusplus
}
#endif
#endif
