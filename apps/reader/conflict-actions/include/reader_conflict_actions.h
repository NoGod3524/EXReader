/* SPDX-License-Identifier: MIT */
#ifndef READER_CONFLICT_ACTIONS_H
#define READER_CONFLICT_ACTIONS_H
#include <reader_commands.h>
#ifdef __cplusplus
extern "C" {
#endif
#define READER_CONFLICT_ACTIONS_VERSION "0.1.0"
/* A merge revision can name at most READER_REVISION_MAX_PARENTS (32) parents,
   so a snapshot of more concurrent heads is refused rather than truncated. */
#define READER_CONFLICT_MAX_HEADS ((size_t)32)
/* Sum of the exact retained wire bytes copied into one snapshot. */
#define READER_CONFLICT_MAX_WIRE_BYTES ((size_t)8388608)

typedef struct reader_conflict_owner reader_conflict_owner;
typedef struct reader_conflict_snapshot reader_conflict_snapshot;

typedef enum {
  READER_CONFLICT_OK=0,
  READER_CONFLICT_ARGUMENT,         /* Missing/invalid input; nothing was read or written. */
  READER_CONFLICT_MEMORY,
  READER_CONFLICT_LIMIT,            /* More than 32 heads or more than 8 MiB of wire bytes. */
  READER_CONFLICT_CANCELLED,        /* Observed before the commit boundary; nothing was written. */
  READER_CONFLICT_OWNER,            /* Wrong thread, reentry, or closed owner. */
  READER_CONFLICT_NOT_FOUND,        /* The entity has no retained revision. */
  READER_CONFLICT_NOT_CONFLICT,     /* One complete safe head: use the ordinary edit path. */
  READER_CONFLICT_STALE,            /* The head set differs from the snapshot; prepare again. */
  READER_CONFLICT_INCOMPLETE,       /* A parent is missing/foreign; wait for it, then prepare again. */
  READER_CONFLICT_RESTORE_REQUIRED, /* A tombstone is observed; only an explicit restore can follow. */
  READER_CONFLICT_NOT_TOMBSTONED,   /* Restore needs a directly observed delete head. */
  READER_CONFLICT_READING_HOST,     /* Reading anchors are displayed only; the host resolves them. */
  READER_CONFLICT_NEEDS_BOOTSTRAP,  /* Membership needs retained book history first. */
  READER_CONFLICT_IDENTITY,         /* The typed command names a different entity. */
  READER_CONFLICT_REVISION,         /* Refused by the revision store; see revision error. */
  READER_CONFLICT_COMMAND           /* Refused by the typed command layer; see command error. */
} reader_conflict_status;

typedef enum {
  READER_CONFLICT_TARGET_BOOK=0,    /* book_key */
  READER_CONFLICT_TARGET_GROUP,     /* group_kind + group_id */
  READER_CONFLICT_TARGET_MEMBERSHIP,/* group_kind + group_id + book_key */
  READER_CONFLICT_TARGET_PROGRESS,  /* book_key; display only */
  READER_CONFLICT_TARGET_ANNOTATION /* book_key + annotation_id; display only */
} reader_conflict_target_kind;

typedef struct {
  reader_conflict_target_kind kind;
  reader_group_kind group_kind;
  const char *book_key, *group_id, *annotation_id;
} reader_conflict_target;

typedef enum {
  READER_CONFLICT_STATE_SAFE=0,     /* One complete, not blocked head. */
  READER_CONFLICT_STATE_CONCURRENT, /* Several complete heads. */
  READER_CONFLICT_STATE_TOMBSTONED, /* A delete head or a head blocked behind one. */
  READER_CONFLICT_STATE_INCOMPLETE  /* Missing or foreign parents (dominates the others). */
} reader_conflict_state;

typedef struct {
  char message[160];
  reader_revision_error revision;
  reader_command_error command;
} reader_conflict_error;

/* Optional. Polled only before the commit boundary: at the start, between head
   reads and immediately before the one typed command. Nonzero cancels. It must
   not call this module (reentry reports OWNER). Never polled after commit. */
typedef struct {
  int (*is_cancelled)(void *);
  void *context;
} reader_conflict_cancel;

typedef struct {
  reader_revision_head head;   /* ID, operation, SHA-256, complete, requires_restore. */
  reader_revision_info info;   /* From the revision store's validator, never re-parsed here. */
  const char *wire;            /* Exact retained UTF-8 bytes, NUL terminated for convenience. */
  size_t wire_bytes;
} reader_conflict_head;

typedef struct {
  reader_conflict_target_kind kind;
  const char *entity_kind, *entity_key; /* Typed global revision identity. */
  reader_conflict_state state;
  int resolvable;                       /* Explicit book/group/membership action is possible. */
  reader_revision_state graph;
  const reader_conflict_head *heads;    /* Sorted by revision ID; complete head set. */
  size_t head_count;
  const char *const *head_ids;          /* Same order; the parent set a resolution observes. */
  size_t wire_bytes;                    /* Sum of heads[n].wire_bytes. */
} reader_conflict_view;

typedef struct {
  reader_command_result command; /* IDs assigned before commit stay filled on failure. */
  int committed;                 /* 1 only after the native transaction committed. */
  size_t observed_heads;
} reader_conflict_result;

/* Opens its own handle to one existing product schema1 catalog (same provider as
   reader_revisions_open). Open, every other call except snapshot_free/view, and
   close must use the creating worker without callback reentry. */
reader_conflict_status reader_conflict_open(const char *utf8_product_path,reader_conflict_owner **,reader_conflict_error *);
reader_conflict_status reader_conflict_close(reader_conflict_owner **,reader_conflict_error *);

/* Copies the COMPLETE head set and each head's exact validated retained bytes
   from one stable read: the head set is read again after the wire copies and a
   change is retried three times, then reported STALE. A conflicting or
   incomplete state is returned successfully so a UI can show it; only a missing
   entity, invalid target or bound yields no snapshot. The snapshot is immutable
   and owned by the caller until reader_conflict_snapshot_free (any thread). */
reader_conflict_status reader_conflict_prepare(reader_conflict_owner *,const reader_conflict_target *,
  const reader_conflict_cancel *,reader_conflict_snapshot **,reader_conflict_error *);
const reader_conflict_view *reader_conflict_snapshot_view(const reader_conflict_snapshot *);
void reader_conflict_snapshot_free(reader_conflict_snapshot *);

/* Explicit resolution: exactly one new revision whose parents are ALL snapshot
   heads, carrying only the typed fields and operation the user supplied. No
   head is chosen by clock, order or content, and no head is discarded. Each
   entity (book, group, membership) is resolved separately; deleting or
   restoring a group never cascades to its memberships.
   revision_id is an optional 32-hex stable retry ID (NULL/empty allocates one;
   it is returned in result->command.revision_id even on failure). Repeating the
   same snapshot, ID and fields after the commit is an exact no-op with
   committed=1 and command.created=0; the same ID with different fields is a
   COMMAND/REVISION collision.
   Rules checked before any write: put needs no observed tombstone, restore
   needs a directly observed delete head, delete needs a live head, and an
   incomplete history is refused. The commit boundary is the single
   reader_command_apply_* call (its native transaction); the module has no
   other write. Cancellation is not polled after that call begins.
   A stale head set returns STALE with no partial write. */
reader_conflict_status reader_conflict_resolve_book(reader_conflict_owner *,const reader_conflict_snapshot *,
  const char *revision_id,const reader_book_command *,const reader_conflict_cancel *,
  reader_conflict_result *,reader_conflict_error *);
reader_conflict_status reader_conflict_resolve_group(reader_conflict_owner *,const reader_conflict_snapshot *,
  const char *revision_id,const reader_group_command *,const reader_conflict_cancel *,
  reader_conflict_result *,reader_conflict_error *);
reader_conflict_status reader_conflict_resolve_membership(reader_conflict_owner *,const reader_conflict_snapshot *,
  const char *revision_id,const reader_membership_command *,const reader_conflict_cancel *,
  reader_conflict_result *,reader_conflict_error *);
#ifdef __cplusplus
}
#endif
#endif
