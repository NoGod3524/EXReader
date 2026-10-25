/* SPDX-License-Identifier: MIT */
#ifndef READER_COMMANDS_H
#define READER_COMMANDS_H
#include <reader_projection.h>
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
#define READER_COMMANDS_VERSION "0.2.0"
#else
#define READER_COMMANDS_VERSION "0.1.0"
#endif
#ifdef __cplusplus
extern "C" {
#endif

typedef enum {READER_COMMAND_OK=0,READER_COMMAND_ARGUMENT,
  READER_COMMAND_NEEDS_BOOK_BOOTSTRAP,READER_COMMAND_REVISION} reader_command_status;
typedef enum {READER_COMMAND_PUT=0,READER_COMMAND_DELETE,READER_COMMAND_RESTORE} reader_command_operation;
typedef enum {READER_GROUP_SHELF=0,READER_GROUP_TAG,READER_GROUP_SERIES} reader_group_kind;

typedef struct {
  reader_revisions *store;
  /* Optional stable ID for retries; NULL/empty allocates one. Never a clock. */
  const char *revision_id;
  /* The complete head set observed by the UI, never selected by this producer. */
  const char *const *expected_heads;
  size_t expected_count;
} reader_command_context;
typedef struct {
  reader_command_status code;
  reader_revision_error revision;
  char message[160];
} reader_command_error;
typedef struct {
  /* Assigned before committing, retained on a later failure for exact retry.
     Reuse BOTH identifiers when a create response is uncertain. */
  char entity_key[257],revision_id[33];
  reader_revision_info revision;
  int created,applied;
} reader_command_result;

typedef struct {
  reader_command_operation operation;
  const char *book_key;
  /* Required for put/restore. Host verifies the exact original through the
     public SDK before calling; no SDK-local ID enters this module or wire. */
  const char *format,*source_sha256,*title,*author,*sort_title;
  uint64_t source_bytes;
  int favorite;
} reader_book_command;
typedef struct {
  reader_command_operation operation;
  reader_group_kind kind;
  /* Empty creates only with put and no observed heads; return assigned key. */
  const char *id,*name,*parent_id;
  uint64_t ordinal;
} reader_group_command;
typedef struct {
  reader_command_operation operation;
  reader_group_kind kind;
  const char *group_id,*book_key;
  uint64_t ordinal;
} reader_membership_command;

/* JNI/Windows boundary: counted UTF-16 -> strict UTF-8, never modified UTF-8.
   At most 16384 input units/output bytes; capacity includes the terminator.
   Rejects NUL and lone surrogates. No normalization; bytes excludes terminator.
   On failure bytes=0 and output[0]=0 when output/capacity are provided. */
reader_command_status reader_command_utf16(const uint16_t *,size_t units,
  char *output,size_t capacity,size_t *bytes,reader_command_error *);

/* No stored/remote wire is rewritten. These functions encode only new typed
   local commands, sort the new parent set, then call local_project once.
   Metadata/history/outbox are that native transaction; a surrounding Java or
   Swift connection transaction cannot extend it. Use the store's owner queue.
   Delete/restore require at least one observed head; bootstrap legacy state
   explicitly first. Names use the existing 256-scalar/1024-byte contract.
   Non-shelf groups have no parent/order; tag memberships require ordinal zero.
   SDK import ordering: verify original -> book command -> local map attach.
   Keep committed SDK originals when later product work fails. */
reader_command_status reader_command_apply_book(const reader_command_context *,const reader_book_command *,
  reader_command_result *,reader_command_error *);
reader_command_status reader_command_apply_group(const reader_command_context *,const reader_group_command *,
  reader_command_result *,reader_command_error *);
/* Requires verified retained book history before any join/history/outbox write;
   returns NEEDS_BOOK_BOOTSTRAP otherwise, including existing catalog-only books. */
reader_command_status reader_command_apply_membership(const reader_command_context *,const reader_membership_command *,
  reader_command_result *,reader_command_error *);
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
/* Explicit raw-store metadata commands; unchanged wire/schema and one transaction. */
reader_command_status reader_command_apply_book_raw_v3(const reader_command_context *context,const reader_book_command *input,
    reader_command_result *result,reader_command_error *error);
reader_command_status reader_command_apply_group_raw_v3(const reader_command_context *context,const reader_group_command *input,
    reader_command_result *result,reader_command_error *error);
reader_command_status reader_command_apply_membership_raw_v3(const reader_command_context *context,const reader_membership_command *input,
    reader_command_result *result,reader_command_error *error);
#endif
#ifdef __cplusplus
}
#endif
#endif
