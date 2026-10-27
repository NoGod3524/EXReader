/* SPDX-License-Identifier: MIT */
#ifndef READER_TXT_PROGRESS_H
#define READER_TXT_PROGRESS_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define READER_TXT_PROGRESS_VERSION "0.1.0"
/* The bounded context is the real captured normalized text at the saved point.
   It is carried as the wire v2 prefix/suffix window, whose limits are 32 scalars
   and 128 bytes, and is re-checked on restore so a silently changed projection
   is reported instead of navigating to a wrong place. */
#define READER_TXP_CONTEXT_BYTES ((size_t)128)
#define READER_TXP_CONTEXT_SCALARS ((size_t)32)
#define READER_TXP_BOOK_KEY_BYTES ((size_t)72)

typedef enum {
  READER_TXP_OK = 0,
  READER_TXP_ARGUMENT,  /* caller input outside the documented bounds */
  READER_TXP_MEMORY,    /* bounded allocation failed */
  READER_TXP_STORE,     /* the product revision store could not be opened/closed */
  READER_TXP_REVISION,  /* revision/command module refused; codes are reported */
  READER_TXP_MISSING,   /* no progress history exists for this product identity */
  READER_TXP_BOOTSTRAP, /* verified book history is absent; progress cannot exist */
  READER_TXP_CONFLICT,  /* several concurrent heads: nothing is selected or written */
  READER_TXP_PENDING,   /* a head has missing parents; history is not projectable */
  READER_TXP_BLOCKED,   /* a delete needs an explicit restore; history is not safe */
  READER_TXP_UNSAFE,    /* the observed head set changed under the caller */
  READER_TXP_LEGACY,    /* the selected head is not an anchor v2 point selector */
  READER_TXP_IDENTITY,  /* retained content identity differs from the supplied one */
  READER_TXP_LIMIT      /* this entity reached the revision history limit */
} reader_txp_status;
typedef struct {
  reader_txp_status code;
  int revision_code;   /* reader_revision_status or 0 */
  int command_code;    /* reader_command_status / reader_rc_status or 0 */
  int selection_kind;  /* reader_selection_kind observed for the entity */
  char message[160];   /* fixed text; never a path, URL or secret */
} reader_txp_error;

/* A canonical text position in the SDK's whole-document normalized UTF-8
   projection of the immutable original. The offset is not a page number: it is
   the byte position the pager itself reports for the top of the accepted page. */
typedef struct {
  uint64_t offset;
  size_t context_bytes; /* 0 only when the captured window was empty */
  char context[READER_TXP_CONTEXT_BYTES + 1];
} reader_txp_position;

/* Product content identity and the metadata needed to bootstrap its retained
   book revision. The host supplies values it verified; this module never reads
   the SDK library, never invents an SDK book ID and never rewrites history. */
typedef struct {
  const char *book_key;    /* exactly format:sha256, lowercase */
  const char *title;
  const char *author;
  const char *sort_title;  /* host NFC sort key, as the product catalog stores it */
  uint64_t source_bytes;
  int favorite;
} reader_txp_book;

typedef struct {
  char book_key[READER_TXP_BOOK_KEY_BYTES + 1];
  char revision_id[33];
  char sha256[65];
  size_t bytes;           /* exact retained revision bytes */
  int created;            /* 1 only for the call that committed the write */
  int unchanged;          /* 1 when the selected head already equals this position */
} reader_txp_result;

/* One schema1 product database; the module owns the connection and requires its
   creating worker. raw_capability selects the explicit raw-v3 store family and
   must match the build (the legacy build refuses it). */
typedef struct reader_txt_progress reader_txt_progress;
reader_txp_status reader_txp_open(const char *utf8_path, int raw_capability,
  reader_txt_progress **out, reader_txp_error *error);
void reader_txp_close(reader_txt_progress **store);

/* Bounds a captured window to 32 scalars / 128 bytes on a UTF-8 boundary.
   NUL and malformed UTF-8 are refused, never escaped or truncated silently. */
reader_txp_status reader_txp_capture(reader_txp_position *position, uint64_t offset,
  const char *bytes, size_t size, reader_txp_error *error);

/* Idempotent retained book identity. An existing identity is never rewritten and
   its recorded original length must equal source_bytes. */
reader_txp_status reader_txp_ensure_book(reader_txt_progress *store,
  const reader_txp_book *book, reader_txp_result *result, reader_txp_error *error);

/* Writes one anchor v2 point progress revision whose parents are the complete
   observed head set. A concurrent/pending/blocked graph, a stale observed head,
   a legacy selector or an exhausted history writes nothing and keeps every
   retained record. */
reader_txp_status reader_txp_save(reader_txt_progress *store, const char *book_key,
  const char *parser_version, const reader_txp_position *position,
  reader_txp_result *result, reader_txp_error *error);

/* Reads the single complete safe head. MISSING/CONFLICT/PENDING/BLOCKED/LEGACY
   are reported without choosing a winner and without writing anything. */
reader_txp_status reader_txp_load(reader_txt_progress *store, const char *book_key,
  reader_txp_position *position, reader_txp_result *result, reader_txp_error *error);

/* Compares a saved position with one projected window [window_offset,
   window_offset+window_bytes). A window that does not cover the point is
   ARGUMENT, never a silent match. */
reader_txp_status reader_txp_match(const reader_txp_position *position,
  const char *window, uint64_t window_offset, size_t window_bytes, int *matches,
  reader_txp_error *error);
#ifdef __cplusplus
}
#endif
#endif
