/* SPDX-License-Identifier: MIT */
#ifndef LM_MIRROR_H
#define LM_MIRROR_H
#include "lm.h"
#define LM_MIRROR_LEDGER_MAX ((uint64_t)256 * 1024 * 1024)

/* Tools-only, immutable mirror intent. It is NOT a commit receipt. All callers
   must hold the common migration lock plus the documented stable-path lease. */
typedef struct {
  int present;
  char identity[33];                 /* platform volume/device + file number */
  char sha[65];                      /* empty when content was not requested */
  uint64_t size;
} lm_mirror_file;

typedef struct {
  int version;
  int target_was_present;
  char target_identity[33];          /* target inode, or private-stage inode */
  char stage_token[24];              /* safe run token; empty for existing target */
  int before_found;
  char before_sha[65], after_sha[65]; /* equal hashes do not identify COMMIT */
  lm_mirror_file mirror_before;
  char artifact_token[24];           /* v2 existing-target precommit artifacts */
  lm_mirror_file mirror_after, mirror_preimage;
} lm_mirror_intent;

typedef enum {
  LM_MIRROR_CONFLICT = 0,
  LM_MIRROR_ALREADY_EQUAL,
  LM_MIRROR_EXPORT_CURRENT,
  LM_MIRROR_NO_LEDGER,
  LM_MIRROR_ABANDONED_NEW,
  LM_MIRROR_RESTORE_BEFORE
} lm_mirror_action;

/* Tri-state snapshot: absent is a successful result with present=0; an unknown,
   unreadable, symlink/reparse, or non-regular path is an error, never absence.
   hash_content=0 obtains identity without reading the database. Optional data
   is malloc-owned, NUL-terminated, and bounded by max_bytes. */
int lm_mirror_snapshot(const char *path, int hash_content, uint64_t max_bytes,
                       lm_mirror_file *out, char **data, size_t *size, lm_err *e);
int lm_mirror_same_file(const lm_mirror_file *a, const lm_mirror_file *b);
int lm_mirror_same_bytes(const lm_mirror_file *a, const lm_mirror_file *b);
int lm_mirror_copy_new(const char *source, const lm_mirror_file *expected,
                       const char *destination, lm_mirror_file *written,
                       int *owned, lm_err *e);
int lm_mirror_planned_file(const lm_mirror_intent *intent, const lm_mirror_file *file);
int lm_mirror_original_file(const lm_mirror_intent *intent, const lm_mirror_file *file);
/* Capture the pre-migration relationship. An existing internal ledger permits
   an absent mirror or an exact byte mirror, not an arbitrary valid envelope. */
int lm_mirror_begin(lm_mirror_intent *intent, int target_was_present,
                    const char *stage_token,
                    const lm_mirror_file *owner, int before_found,
                    const void *before, size_t before_size,
                    const lm_mirror_file *mirror, lm_err *e);
void lm_mirror_set_after(lm_mirror_intent *intent, const void *data, size_t size);
/* The fixed sibling journal is exclusive-created. Failure never deletes a
   possibly partial intent; later callers fail closed. No arbitrary paths are
   accepted from journal content. Strict format is bounded to 4096 bytes. */
int lm_mirror_intent_write(const char *path, const lm_mirror_intent *intent,
                           lm_mirror_file *written, lm_err *e);
int lm_mirror_intent_read(const char *path, lm_mirror_intent *intent,
                          lm_mirror_file *snapshot, lm_err *e);
/* Only removes the exact journal snapshot that was read/written. There is no
   recursive cleanup and no removal of crashed private stages/export temps. */
int lm_mirror_intent_remove(const char *path, const lm_mirror_file *expected, lm_err *e);
/* Pure recovery classifier. Caller supplies ledger_get bytes from the fresh
   migration owner. It never infers historical commit from ledger hashes. */
lm_mirror_action lm_mirror_plan(const lm_mirror_intent *intent,
                                const lm_mirror_file *target,
                                const lm_mirror_file *unpublished_stage,
                                int current_found, const void *current, size_t current_size,
                                const lm_mirror_file *mirror, lm_err *e);
#endif
