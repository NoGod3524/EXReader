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
typedef struct {
  const char *annotation_id; /* Borrowed lowercase 32-hex ID, cursor within book. */
  reader_revision_selection selection;
  reader_revision_info info; /* Zero unless SAFE, including safe tombstones. */
  const char *wire; /* Exact retained bytes only for SAFE; otherwise NULL. */
} reader_revision_annotation_row;
typedef int (*reader_revision_annotation_fn)(void *,const reader_revision_annotation_row *);
/* One read snapshot, distinct global annotation IDs in bytewise keyset order.
   book_key is required; after_id NULL starts at the appropriate end. direction
   is +1/-1 and limit is 1..100. Includes tombstones and unresolved entities;
   only SAFE supplies info/wire, and navigation still requires SDK FOUND.
   Callback data is borrowed until return. Nonzero stops successfully. Calls
   use the creating worker without reentry. Discard the page on any error.
   Uses the schema1 entity index, with no OFFSET, migration or SDK write. */
reader_revision_status reader_revision_annotations_page(reader_revisions *,const char *book_key,
  const char *after_id,int direction,size_t limit,reader_revision_annotation_fn,void *,
  reader_revision_error *);

typedef struct {
  const char *entity_key; /* Borrowed typed global key; cursor within entity_kind. */
  reader_revision_selection selection;
  reader_revision_info info; /* Zero unless SAFE, including a safe tombstone. */
  const char *wire; /* Exact original bytes only for SAFE. */
} reader_revision_entity_row;
typedef int (*reader_revision_entity_fn)(void *,const reader_revision_entity_row *);
/* Enumerate one explicit kind in one read snapshot. after_key NULL starts at
   either end; direction +/-1, limit 1..100. Includes unresolved/deleted entities
   so the host can report conflicts or schedule safe metadata projection.
   Copy callback data before applying: reentry is refused. Nonzero stops. On
   error discard the page. Uses schema1's index; no writes/SDK work/OFFSET.
   A later project call still checks its expected safe head transactionally. */
reader_revision_status reader_revision_entities_page(reader_revisions *,const char *entity_kind,
  const char *after_key,int direction,size_t limit,reader_revision_entity_fn,void *,
  reader_revision_error *);
/* Copy the exact title from one retained non-delete book revision for the
   host's existing NFC sort conversion. Does not select a head or normalize.
   project(expected_head) remains the authority before writing metadata.
   Release the output with reader_revision_bytes_free; failure leaves NULL. */
reader_revision_status reader_revision_book_title(reader_revisions *,const char *revision_id,
  char **title,reader_revision_error *);
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
/* Explicit candidate APIs: store capability is immutable; legacy APIs refuse raw stores. */
reader_revision_status reader_revisions_open_raw_v3(const char *path,reader_revisions **out,reader_revision_error *error);
reader_revision_status reader_revision_validate_raw_v3(reader_revisions *store,const void *bytes,size_t count,const char *expected,reader_revision_info *out,reader_revision_error *error);
reader_revision_status reader_revision_local_raw_v3(reader_revisions *store,const void *bytes,size_t count,reader_revision_info *out,int *created,reader_revision_error *error);
reader_revision_status reader_revision_receive_raw_v3(reader_revisions *store,const void *bytes,size_t count,const char *expected,reader_revision_info *out,int *created,reader_revision_error *error);
reader_revision_status reader_revision_get_raw_v3(reader_revisions *store,const char *id,char **wire,size_t *bytes,reader_revision_info *out,reader_revision_error *error);
reader_revision_status reader_revision_heads_raw_v3(reader_revisions *store,const char *entity_kind,const char *entity_key,reader_revision_head_fn visit,void *context,reader_revision_state *out,reader_revision_error *error);
reader_revision_status reader_revision_book_identity_raw_v3(reader_revisions *store,const char *key,uint64_t *bytes,reader_revision_error *error);
reader_revision_status reader_revision_local_project_raw_v3(reader_revisions *store,const void *bytes,size_t count,const char *const *expected,size_t expected_count,const char *sort_title,reader_revision_info *out,int *created,int *applied,reader_revision_error *error);
reader_revision_status reader_revision_local_reading_raw_v3(reader_revisions *store,const void *bytes,size_t count,const char *const *expected,size_t expected_count,reader_revision_info *out,int *created,reader_revision_error *error);
reader_revision_status reader_revision_project_raw_v3(reader_revisions *store,const char *entity_kind,const char *entity_key,const char *expected,const char *sort_title,reader_revision_info *out,reader_revision_error *error);
reader_revision_status reader_revision_selected_raw_v3(reader_revisions *store,const char *entity_kind,const char *entity_key,char **wire,size_t *bytes,reader_revision_info *out,reader_revision_selection *selection,reader_revision_error *error);
reader_revision_status reader_revision_annotations_page_raw_v3(reader_revisions *store,const char *book_key,const char *after_id,int direction,size_t limit,reader_revision_annotation_fn visit,void *context,reader_revision_error *error);
reader_revision_status reader_revision_entities_page_raw_v3(reader_revisions *store,const char *type,const char *after_key,int direction,size_t limit,reader_revision_entity_fn visit,void *context,reader_revision_error *error);
reader_revision_status reader_revision_book_title_raw_v3(reader_revisions *store,const char *id,char **title,reader_revision_error *error);
reader_revision_status reader_revision_outbox_raw_v3(reader_revisions *store,size_t limit,reader_revision_outbox_fn visit,void *context,reader_revision_error *error);
reader_revision_status reader_revision_retry_raw_v3(reader_revisions *store,const char *id,reader_revision_status reason,reader_revision_error *error);
reader_revision_status reader_revision_ack_raw_v3(reader_revisions *store,const char *id,const char *expected,reader_revision_error *error);
#endif
#ifdef __cplusplus
}
#endif
#endif
