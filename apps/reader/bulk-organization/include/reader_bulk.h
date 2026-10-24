/* SPDX-License-Identifier: MIT */
#ifndef READER_BULK_H
#define READER_BULK_H
#include <reader_metadata.h>
#ifdef __cplusplus
extern "C" {
#endif

#define READER_BULK_VERSION "0.1.0"
#define READER_BULK_MAX_BATCH 100u
#define READER_BULK_MAX_HEADS 32u            /* == READER_REVISION_MAX_PARENTS */
#define READER_BULK_JOURNAL_MAX_BYTES ((size_t)524288)

/* One explicit organization action is applied to at most 100 selected books.
 * Every book is its own product transaction through the installed metadata
 * owner (prepare -> stage -> apply -> finish). A batch is NEVER atomic: a
 * conflict, a deleted dependency, a failure or a cancellation leaves every
 * earlier committed item committed and no later item is rolled back or hidden.
 * The component starts no thread and keeps no global state.
 *
 * THREADS/REENTRY: reader_bulk_open, every call and close must run on the one
 * worker that created the borrowed reader_metadata_owner and this handle. A
 * progress or control callback runs on that worker inside the call; it must not
 * call this handle or the metadata owner (reentry is refused with OWNER) and
 * must not close either. Only one bulk handle may use an owner at a time.
 * CALLER-OWNED MEMORY: all inputs are borrowed for the call. Results are
 * written into a caller array; nothing is allocated for the caller to free.
 *
 * COMMIT BOUNDARY: an item is committed exactly when the metadata owner's
 * apply returns OK. Cancellation is polled only BEFORE an item is prepared,
 * never between stage and finish, so cancel cannot split one item.
 *
 * DURABILITY: before the first item a private sidecar journal (journal_path,
 * <= 512 KiB, flushed temp file + atomic rename) records the request and each
 * item. It is rewritten after each item is staged (observed heads + stable
 * retry revision ID) and after each item completes. It is NOT the product
 * database, adds no schema, wire entity or sync traffic, and holds no secret.
 * After process death call reader_bulk_resume with the same journal_path: a
 * staged item is replayed with its ORIGINAL revision ID and observed heads
 * (metadata owner sidecar), never rebuilt from current rows. A finished batch
 * keeps its journal until reader_bulk_acknowledge so the report survives a
 * crash between the last commit and delivery to the host. */
typedef struct reader_bulk reader_bulk;

typedef enum {
  READER_BULK_OK = 0,
  READER_BULK_CANCELLED,      /* control stopped the batch; resumable, nothing rolled back */
  READER_BULK_ARGUMENT,
  READER_BULK_OWNER,          /* wrong thread, reentry, or second handle */
  READER_BULK_IO,             /* journal read/write failure */
  READER_BULK_CORRUPT,        /* journal checksum/shape invalid or bound to another product DB */
  READER_BULK_JOURNAL_ACTIVE, /* a journal already exists: resume, acknowledge or abandon it */
  READER_BULK_NO_JOURNAL,
  READER_BULK_FOREIGN_PENDING,/* metadata owner holds an intent not belonging to this batch */
  READER_BULK_METADATA,       /* owner/revision failure stopped the batch; journal kept, resumable */
  READER_BULK_CAPACITY        /* results array smaller than the batch */
} reader_bulk_status;

typedef struct {
  reader_bulk_status code;
  reader_metadata_status metadata; /* READER_METADATA_OK unless code is METADATA/FOREIGN_PENDING */
  char message[160];
} reader_bulk_error;

typedef enum {
  READER_BULK_FAVORITE_SET = 0, READER_BULK_FAVORITE_CLEAR,
  READER_BULK_SHELF_ADD, READER_BULK_SHELF_REMOVE,
  READER_BULK_TAG_ADD, READER_BULK_TAG_REMOVE,
  READER_BULK_SERIES_ADD, READER_BULK_SERIES_REMOVE
} reader_bulk_action;

typedef enum {
  READER_BULK_ITEM_NOT_RUN = 0,   /* cancelled or interrupted before this item */
  READER_BULK_ITEM_COMMITTED,     /* a typed revision for this book is retained */
  READER_BULK_ITEM_UNCHANGED,     /* already in the requested state; no transaction, no revision */
  READER_BULK_ITEM_CONFLICT,      /* concurrent heads / missing or foreign parents / restore needed */
  READER_BULK_ITEM_MISSING,       /* book absent or deleted */
  READER_BULK_ITEM_DEPENDENCY_DELETED, /* target group (or book) deleted */
  READER_BULK_ITEM_NEEDS_BOOTSTRAP,    /* legacy book: explicit verified bootstrap first */
  READER_BULK_ITEM_FAILED         /* refused by the metadata owner for another reason */
} reader_bulk_item_outcome;

typedef struct {
  size_t struct_size;             /* sizeof(reader_bulk_item_result) */
  size_t index;                   /* position in the request */
  char book_key[73];
  reader_bulk_item_outcome outcome;
  int committed;                  /* 1 iff outcome is COMMITTED */
  /* 1 iff THIS run's apply created the revision. A replay after process death
   * of an intent that had already committed reports committed=1, created=0,
   * replayed=1; the revision ID below identifies it either way. */
  int created;
  int replayed;
  int conflict;                   /* 1 for CONFLICT and DEPENDENCY_DELETED */
  reader_metadata_status metadata;/* owner status for FAILED/CONFLICT/NEEDS_BOOTSTRAP */
  char entity_key[257];
  char revision_id[33];           /* stable retry ID; empty for UNCHANGED or never staged */
  /* COMPLETE head set observed by prepare; reuse is the expected-head input of
   * the staged revision. heads_known is 0 only for the single narrow window
   * "metadata intent staged but journal not yet rewritten" after a kill. */
  int heads_known;
  size_t head_count;
  char heads[READER_BULK_MAX_HEADS][33];
  char message[160];
} reader_bulk_item_result;

typedef struct {
  char batch_id[33];
  reader_bulk_action action;
  size_t total, committed, created, unchanged, conflicts, failed, not_run;
  int complete;                   /* every item has a final outcome */
  int cancelled;                  /* last run stopped on control */
} reader_bulk_summary;

typedef enum {
  READER_BULK_EVENT_STAGED = 0,   /* durable intent + retry ID exist; not yet committed */
  READER_BULK_EVENT_COMMITTED,    /* apply returned OK; sidecars not yet cleaned */
  /* The item has its final outcome. A COMMITTED outcome is already durable in
   * the journal; other outcomes are in memory and are safely re-evaluated if
   * the process dies before the next journal write. */
  READER_BULK_EVENT_ITEM_DONE
} reader_bulk_event;
typedef void (*reader_bulk_progress_fn)(void *context, reader_bulk_event event,
  size_t index, const reader_bulk_item_result *item);
/* Return nonzero to stop before the next item. Polled once per item, before
 * preparing it. Never called between stage and finish. */
typedef int (*reader_bulk_cancel_fn)(void *context);
typedef struct {
  void *context;
  reader_bulk_cancel_fn cancelled;       /* may be NULL */
  reader_bulk_progress_fn progress;      /* may be NULL */
} reader_bulk_control;

typedef struct {
  size_t struct_size;             /* sizeof(reader_bulk_request) */
  reader_bulk_action action;
  /* 32 lowercase hex group ID for shelf/tag/series actions; NULL for favorite. */
  const char *group_id;
  /* Shelf/series add: item i receives ordinal_base+i (<= INT64_MAX-100).
   * Tag add and every remove/favorite action ignore it (tags use zero;
   * removals reuse the observed ordinal). */
  uint64_t ordinal_base;
  const char *const *book_keys;   /* 1..READER_BULK_MAX_BATCH distinct keys */
  size_t book_count;
  reader_bulk_control control;
} reader_bulk_request;

/* product_path is the same product schema1 database opened by `owner`;
 * journal_path is a private file in the host profile directory, different from
 * the product database and the metadata pending file. The handle borrows
 * `owner`, which must outlive it. Nothing is read or created yet. */
reader_bulk_status reader_bulk_open(reader_metadata_owner *owner, const char *product_path,
  const char *journal_path, reader_bulk **out, reader_bulk_error *);
reader_bulk_status reader_bulk_close(reader_bulk **, reader_bulk_error *);

/* Start a batch. Refuses JOURNAL_ACTIVE when an earlier journal exists and
 * FOREIGN_PENDING when the metadata owner holds any pending intent. results
 * must have room for book_count entries (CAPACITY otherwise). On OK, CANCELLED
 * or METADATA the results/summary describe the journal's current state. */
reader_bulk_status reader_bulk_run(reader_bulk *, const reader_bulk_request *,
  reader_bulk_item_result *results, size_t capacity, reader_bulk_summary *, reader_bulk_error *);
/* Continue the journal's unfinished items after cancellation or process death.
 * control is the new run's callbacks (the request's are not persisted). A
 * completed journal just reports its results. */
reader_bulk_status reader_bulk_resume(reader_bulk *, const reader_bulk_control *,
  reader_bulk_item_result *results, size_t capacity, reader_bulk_summary *, reader_bulk_error *);
/* Read the journal without doing work. */
reader_bulk_status reader_bulk_inspect(reader_bulk *, reader_bulk_item_result *results,
  size_t capacity, reader_bulk_summary *, reader_bulk_error *);
/* Delete a COMPLETE journal after the host has the report. */
reader_bulk_status reader_bulk_acknowledge(reader_bulk *, reader_bulk_error *);
/* Give up an unfinished batch: removes the journal. Refused with
 * FOREIGN_PENDING while the metadata owner holds an intent (resume it
 * instead). Committed items stay committed; unrun items stay unrun. */
reader_bulk_status reader_bulk_abandon(reader_bulk *, reader_bulk_error *);

#ifdef __cplusplus
}
#endif
#endif
