/* SPDX-License-Identifier: MIT */
#ifndef READER_LIBRARY_HEALTH_H
#define READER_LIBRARY_HEALTH_H
#include <stddef.h>
#include <stdint.h>
#include <exr/library.h>
#include <catalog.h>
#ifdef __cplusplus
extern "C" {
#endif

#define READER_LIBRARY_HEALTH_VERSION "1.0.0"
#define READER_HEALTH_VERSION READER_LIBRARY_HEALTH_VERSION

/* Hard bounds. reader_health_options_init() selects the defaults; a caller may
   only lower a maximum (and must keep the read buffer at or above its minimum).
   Anything outside these bounds is READER_HEALTH_ARGUMENT. */
#define READER_HEALTH_MAX_ROWS_PER_STEP 200u            /* equals the catalog page limit */
#define READER_HEALTH_DEFAULT_ROWS_PER_STEP 32u
#define READER_HEALTH_MIN_BUFFER_BYTES 4096u
#define READER_HEALTH_MAX_BUFFER_BYTES (1024u * 1024u)
#define READER_HEALTH_DEFAULT_BUFFER_BYTES (64u * 1024u)
#define READER_HEALTH_MAX_STEP_BYTES (1ull << 30)       /* hashed per step */
#define READER_HEALTH_DEFAULT_STEP_BYTES (64ull << 20)
#define READER_HEALTH_MAX_BOOK_BYTES 2147483647ull      /* public SDK source ceiling */
#define READER_HEALTH_DEFAULT_BOOK_BYTES (512ull << 20)
#define READER_HEALTH_MAX_TOTAL_ROWS 1000000ull         /* per cursor */
#define READER_HEALTH_DEFAULT_TOTAL_ROWS 100000ull
#define READER_HEALTH_SORT_TITLE_CAPACITY 16385u        /* 4096 characters * 4 + NUL */
#define READER_HEALTH_KEY_CAPACITY 72u                  /* "pdf:" + sha256 + NUL */
#define READER_HEALTH_ERROR_MESSAGE_CAPACITY 192u
#define READER_HEALTH_CURSOR_MAGIC 0x4c484352u          /* "LHCR" */

/* Read-only health scan of one product catalog against one SDK library.
 *
 * Input: one open reader_catalog and one open exr_library, both borrowed and
 *   never closed by the scanner.
 * Output: exactly one verdict per delivered active catalog row, in catalog
 *   keyset order (sort_title, book_key). Soft-deleted catalog rows are not
 *   scanned because reader_catalog_page never returns them.
 *
 * The scanner never repairs, deletes, downloads, imports or writes anything:
 * the catalog is read only through reader_catalog_page, and the SDK only
 * through the public exr_library_source, read in a fixed buffer of
 * buffer_bytes. No whole book is loaded, no SDK private table or header is
 * touched, and no new thread or server is created.
 *
 * Threads: a scanner is bound to the thread that created it. That thread must
 *   be the catalog's owning worker and, serially with every other user, the
 *   exr_library owner. Another thread receives READER_HEALTH_THREAD before any
 *   state is touched. A call made from inside the visit or progress callback
 *   receives READER_HEALTH_REENTRY. The creating thread must outlive the
 *   scanner; binding is by operating-system thread identity.
 *
 * Commit boundary: a row is delivered only after its verdict is final. The
 *   cursor advances exactly past delivered rows and never past a row whose
 *   observation was cancelled or failed with a status. Cancellation and an
 *   unobservable source are never reported as healthy.
 *
 * Cost: one step materializes at most rows_per_step catalog rows (their sort
 *   titles are copied) and hashes at most max_step_bytes of original bytes
 *   with one buffer. A row is started only while the step budget is unspent,
 *   so a single row may exceed max_step_bytes by at most max_book_bytes.
 */
typedef enum {
  READER_HEALTH_OK = 0,
  READER_HEALTH_CANCELLED,   /* control.cancelled; the cursor keeps delivered rows only */
  READER_HEALTH_ARGUMENT,
  READER_HEALTH_MEMORY,
  READER_HEALTH_CATALOG,     /* catalog read failed or returned a malformed row */
  READER_HEALTH_THREAD,      /* wrong thread; scanner untouched */
  READER_HEALTH_REENTRY,     /* called from a callback; scanner untouched */
  READER_HEALTH_INTERNAL
} reader_health_status;

typedef struct {
  reader_health_status code;
  int detail_code;           /* catalog return code when code==CATALOG, else 0 */
  char message[READER_HEALTH_ERROR_MESSAGE_CAPACITY];
} reader_health_error;

/* Exactly one verdict per delivered row. Only VERIFIED means healthy. */
typedef enum {
  READER_HEALTH_VERIFIED = 1,       /* mapped, size equal, SHA-256 equal, both ends re-read equal */
  READER_HEALTH_CLOUD_ONLY,         /* catalog metadata with no local SDK mapping */
  READER_HEALTH_MAPPING_MISSING,    /* mapped SDK ID has no retained original (EXR_ARGUMENT) */
  READER_HEALTH_SOURCE_UNAVAILABLE, /* SDK refused to open the source for another reason */
  READER_HEALTH_SIZE_MISMATCH,      /* retained size differs from the catalog's source_bytes */
  READER_HEALTH_READ_FAILED,        /* short/failed read, or the source was invalidated mid-read */
  READER_HEALTH_HASH_MISMATCH,      /* full read completed, SHA-256 differs */
  READER_HEALTH_LIMIT_SKIPPED       /* larger than max_book_bytes; not read, not healthy */
} reader_health_verdict;

const char *reader_health_verdict_name(reader_health_verdict verdict);
const char *reader_health_status_name(reader_health_status status);

/* Strings are borrowed for the duration of one visit call; copy them to keep
   them. expected_sha256 is the identity recorded by the catalog, observed_sha256
   is what the retained original actually hashed to. */
typedef struct {
  size_t struct_size;
  const char *book_key;           /* "format:sha256", the catalog identity */
  const char *format;             /* catalog protocol format name */
  const char *sort_title;         /* catalog binary ordering key */
  int64_t sdk_book_id;            /* 0 for CLOUD_ONLY */
  reader_health_verdict verdict;
  exr_status sdk_status;          /* failing SDK status, EXR_OK otherwise */
  uint64_t expected_bytes;        /* catalog source_bytes */
  uint64_t retained_bytes;        /* SDK-reported size; 0 if the source was not opened */
  uint64_t bytes_read;            /* bytes hashed for this row */
  int hashed;                     /* 1 when observed_sha256 covers the full original */
  char expected_sha256[65];       /* lowercase hex taken from book_key */
  char observed_sha256[65];       /* lowercase hex when hashed, else empty */
} reader_health_row;

/* Return nonzero to stop after this row (the row counts as delivered). The
   callback runs on the scanner thread; it must not call the scanner, close the
   catalog or library, or free the scanner. */
typedef int (*reader_health_visit)(void *context, const reader_health_row *row);

typedef struct {
  size_t struct_size;
  size_t rows_per_step;           /* 1..READER_HEALTH_MAX_ROWS_PER_STEP */
  size_t buffer_bytes;            /* read buffer owned by the scanner */
  uint64_t max_step_bytes;        /* a new row is not started once this was hashed */
  uint64_t max_book_bytes;        /* larger originals are LIMIT_SKIPPED */
  uint64_t max_total_rows;        /* per cursor; reaching it reports limit_reached */
  /* Cancellation is polled before a step, between rows and between buffers.
     Progress reports (EXR_STAGE_READ, bytes read of this book, retained size).
     Both run synchronously on the scanner thread and must not destroy or
     reenter the scanner or close its catalog/library. */
  exr_control control;
} reader_health_options;

/* Plain data. Zero-fill with reader_health_cursor_init and copy by value.
   A cursor is valid only for the catalog its scanner was created with; using
   it with another catalog's scanner is READER_HEALTH_ARGUMENT. */
typedef struct {
  size_t struct_size;
  uint32_t magic;                 /* READER_HEALTH_CURSOR_MAGIC once initialized */
  int started;
  uint64_t rows_done;
  const reader_catalog *catalog;   /* scanner catalog that produced the cursor */
  char sort_title[READER_HEALTH_SORT_TITLE_CAPACITY];
  char book_key[READER_HEALTH_KEY_CAPACITY];
} reader_health_cursor;

typedef struct {
  size_t struct_size;
  size_t rows_delivered;
  size_t steps;                   /* always 1 for a successful call */
  uint64_t bytes_hashed;
  int done;                       /* catalog exhausted after the cursor */
  int stopped;                    /* the visitor asked to stop */
  int budget_reached;             /* max_step_bytes ended the step early */
  int limit_reached;              /* max_total_rows ended the scan; raise it to continue */
} reader_health_step_info;

typedef struct reader_health_scanner reader_health_scanner;

void reader_health_options_init(reader_health_options *options);
void reader_health_cursor_init(reader_health_cursor *cursor);

/* Binds to the calling thread. catalog and library must outlive the scanner.
   On failure *scanner is NULL. */
reader_health_status reader_health_create(reader_catalog *catalog, exr_library *library,
                                          const reader_health_options *options,
                                          reader_health_scanner **scanner,
                                          reader_health_error *error);

/* Processes at most rows_per_step catalog rows from cursor. Returns OK when the
   step finished, with info->done set if the catalog is exhausted. On any
   non-OK return the cursor reflects exactly the delivered rows. info is fully
   overwritten by the call. */
reader_health_status reader_health_step(reader_health_scanner *scanner,
                                        reader_health_cursor *cursor,
                                        reader_health_visit visit, void *context,
                                        reader_health_step_info *info,
                                        reader_health_error *error);

/* Frees the scanner (not the catalog or library) and clears *scanner. Must run
   on the creating thread, outside a callback. A NULL scanner pointer is
   READER_HEALTH_ARGUMENT; *scanner==NULL is a successful no-op. */
reader_health_status reader_health_destroy(reader_health_scanner **scanner,
                                           reader_health_error *error);

#ifdef __cplusplus
}
#endif
#endif
