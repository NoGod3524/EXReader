/* SPDX-License-Identifier: MIT */
#ifndef READER_LOCAL_DOWNLOADS_H
#define READER_LOCAL_DOWNLOADS_H
#include <stddef.h>
#include <stdint.h>
#include <exr/library.h>
#include <exr_sideload.h>
#include <catalog.h>
#ifdef __cplusplus
extern "C" {
#endif

#define READER_LD_VERSION "0.1.0"
#define READER_LD_MAX_COPIES 8u
#define READER_LD_PATH_BYTES 1200u

/* Removes only the local original of a downloaded book and its local SDK
   mapping. The global product book, shelves/tags/series, revision history,
   outbox and every remote object are never read or written here, and no
   deletion tombstone is ever created.

   The SDK library and the product catalog have no shared transaction. Each
   removal therefore records a private durable intent (state_dir/intent.rdi,
   written by write-to-temp, flush and atomic replace) and advances it only
   after the previous step is verifiably complete:

     BEGUN     nothing destructive happened yet
     PREPARED  identity verified, a verified original export exists, duplicate
               byte-identical SDK rows and legacy data are known
     UNMAPPED  the local mapping is gone; the SDK rows still hold the bytes
     DELETED   the verified SDK rows are deleted
   (the export and then the intent are removed last)

   reader_ld_recover rolls BEGUN/PREPARED back (no mapping change was made)
   and rolls UNMAPPED/DELETED forward. Every step is idempotent.

   Calling contract: run on the thread that owns the exr_library and the
   catalog. Release every exr_source / reader opened on the affected SDK rows
   and stop network tasks touching the original BEFORE calling; report
   anything still in use through is_busy. Deleting a row permanently
   invalidates sources previously opened on it. A failed or rejected call
   leaves the rows, mapping and metadata readable, so already-open sources
   remain valid. No thread, watcher or network access is created. */

typedef enum {
  READER_LD_OK = 0,
  READER_LD_CANCELLED,
  READER_LD_ARGUMENT,
  READER_LD_MEMORY,
  READER_LD_IO,           /* private state directory / export / file failure */
  READER_LD_CATALOG,      /* product catalog (mapping) failure */
  READER_LD_SDK,          /* public SDK failure */
  READER_LD_NOT_FOUND,    /* unknown book key */
  READER_LD_BUSY,         /* caller reports the original is in use */
  READER_LD_IDENTITY,     /* stored bytes differ from format+SHA-256 identity */
  READER_LD_LEGACY_DATA,  /* SDK-only notes/progress and policy forbids loss */
  READER_LD_TOO_MANY_COPIES,
  READER_LD_PENDING,      /* another removal intent must be recovered first */
  READER_LD_CORRUPT_INTENT
} reader_ld_status;

typedef enum {
  READER_LD_LEGACY_REJECT = 0, /* refuse removal and report the counts */
  READER_LD_LEGACY_BACKUP = 1  /* keep an SDK backup, then remove */
} reader_ld_legacy_policy;

typedef enum {
  READER_LD_STAGE_NONE = 0,
  READER_LD_STAGE_BEGUN = 1,
  READER_LD_STAGE_PREPARED = 2,
  READER_LD_STAGE_UNMAPPED = 3,
  READER_LD_STAGE_DELETED = 4,
  READER_LD_STAGE_CLEANED = 5 /* hook only: files removed, intent still present */
} reader_ld_stage;

typedef enum {
  READER_LD_OUTCOME_NONE = 0,
  READER_LD_OUTCOME_REMOVED,        /* mapping and verified SDK rows removed */
  READER_LD_OUTCOME_ALREADY_CLOUD,  /* no local mapping: nothing to do */
  READER_LD_OUTCOME_ROLLED_BACK,    /* recover undid an unfinished preparation */
  READER_LD_OUTCOME_NOTHING_PENDING,
  READER_LD_OUTCOME_ATTACHED,       /* reimport attached a local original */
  READER_LD_OUTCOME_ALREADY_LOCAL,
  READER_LD_OUTCOME_RESTORED        /* a late conflict re-attached the mapping */
} reader_ld_outcome;

typedef struct {
  reader_ld_status code;
  exr_status sdk_status;
  int catalog_code;
  char message[224];
} reader_ld_error;

typedef struct {
  size_t struct_size;
  reader_ld_outcome outcome;
  int64_t sdk_book_id;      /* mapped SDK row that was removed / attached */
  size_t copies_removed;    /* SDK rows deleted, including identical copies */
  size_t copies_skipped;    /* rows in the intent that no longer matched and were kept */
  size_t legacy_notes;      /* SDK-only notes found on the removal set */
  size_t legacy_progress;   /* rows with SDK-only reading progress */
  char backup_path[READER_LD_PATH_BYTES]; /* legacy backup when one was made */
} reader_ld_result;

typedef struct {
  size_t struct_size;
  int pending;              /* 1 when a valid intent exists */
  reader_ld_stage stage;
  char book_key[160];
  int64_t sdk_book_id;
  size_t copies;
} reader_ld_pending_info;

/* Called after every durable stage write (and CLEANED). Hosts may use it for
   progress; tests terminate the process from it to prove real crash recovery. */
typedef void (*reader_ld_stage_fn)(void *context, reader_ld_stage stage);
/* Return nonzero when a source, reader or network task still touches this
   original. Called before any destructive step; BUSY changes nothing. */
typedef int (*reader_ld_busy_fn)(void *context, const char *book_key, int64_t sdk_book_id);

typedef struct {
  size_t struct_size;
  exr_library *library;
  reader_catalog *catalog;
  /* Existing app-private UTF-8 directory used only by this module. */
  const char *state_dir;
  reader_ld_legacy_policy legacy_policy;
  reader_ld_busy_fn is_busy;
  void *busy_context;
  reader_ld_stage_fn after_stage;
  void *stage_context;
  uint64_t max_input_bytes; /* zero selects the sideload ceiling */
  exr_control control;
} reader_ld_options;

void reader_ld_options_init(reader_ld_options *options);
void reader_ld_result_init(reader_ld_result *result);

/* Removes the local original for book_key (format ':' lowercase SHA-256).
   A cloud-only key succeeds with ALREADY_CLOUD; repeating a completed removal
   does the same. Refuses with PENDING while another intent exists. */
reader_ld_status reader_ld_remove(const reader_ld_options *options, const char *book_key,
  reader_ld_result *result, reader_ld_error *error);
/* Finishes or rolls back the pending intent, if any. Safe to repeat. */
reader_ld_status reader_ld_recover(const reader_ld_options *options,
  reader_ld_result *result, reader_ld_error *error);
/* Read-only inspection of the pending intent; touches neither database. */
reader_ld_status reader_ld_pending(const char *state_dir, reader_ld_pending_info *info,
  reader_ld_error *error);
/* Attaches a downloaded original again. The file must match the book's
   original format and SHA-256 identity; it is imported through the installed
   EXReaderSideload and mapped with the existing metadata. */
reader_ld_status reader_ld_reimport(const reader_ld_options *options, const char *book_key,
  const char *path, reader_ld_result *result, reader_ld_error *error);

const char *reader_ld_status_name(reader_ld_status status);
const char *reader_ld_stage_name(reader_ld_stage stage);
const char *reader_ld_outcome_name(reader_ld_outcome outcome);
#ifdef __cplusplus
}
#endif
#endif
