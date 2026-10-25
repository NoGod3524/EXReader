/* SPDX-License-Identifier: MIT */
#ifndef READER_BOOK_INFORMATION_H
#define READER_BOOK_INFORMATION_H
#include <stddef.h>
#include <stdint.h>
#include <catalog.h>
#include <exr/library.h>
#ifdef __cplusplus
extern "C" {
#endif

#define READER_BOOK_INFORMATION_VERSION "0.1.0"
/* Hard caps. Text is cut at a UTF-8 scalar boundary and flagged; a cut value is
 * never presented as complete. One snapshot, including its view and property
 * array, occupies less than 48 KiB. */
#define READER_BOOK_INFORMATION_MAX_TEXT_BYTES 1024
#define READER_BOOK_INFORMATION_MAX_KEY_BYTES 128
#define READER_BOOK_INFORMATION_MAX_PROPERTIES 32
#define READER_BOOK_INFORMATION_HASH_CHUNK 65536

typedef struct reader_book_information reader_book_information;

typedef enum {
  READER_BOOK_INFORMATION_OK = 0,
  READER_BOOK_INFORMATION_ARGUMENT,   /* Malformed call or book_key. */
  READER_BOOK_INFORMATION_NOT_FOUND,  /* No product row for book_key. */
  READER_BOOK_INFORMATION_CANCELLED,
  READER_BOOK_INFORMATION_REENTRANT,  /* Called again from this module's cancel callback. */
  READER_BOOK_INFORMATION_CATALOG,
  READER_BOOK_INFORMATION_SDK,        /* Hard SDK failure that cannot be a field state. */
  READER_BOOK_INFORMATION_MEMORY
} reader_book_information_status;

typedef struct {
  reader_book_information_status status;
  int catalog_code; /* Nonzero catalog/SQLite code behind CATALOG. */
  int sdk_code;     /* exr_status behind SDK, or the recorded field-state code. */
  char message[160];
} reader_book_information_error;

/* Where the original is. Never a cross-device identity: the product book_key is
 * the only identity in this view. */
typedef enum {
  READER_BOOK_INFORMATION_CLOUD_ONLY = 0,  /* Product metadata only; no local mapping. */
  READER_BOOK_INFORMATION_LOCAL_UNCHECKED, /* Mapping exists; no SDK handle was supplied. */
  READER_BOOK_INFORMATION_LOCAL_PRESENT,   /* Public SDK source exists and passed identity. */
  READER_BOOK_INFORMATION_LOCAL_MISSING,   /* Mapping exists but the SDK cannot supply the original. */
  READER_BOOK_INFORMATION_LOCAL_MISMATCH   /* SDK bytes are not this product book. */
} reader_book_information_availability;

typedef enum {
  READER_BOOK_INFORMATION_IDENTITY_NOT_CHECKED = 0,
  READER_BOOK_INFORMATION_IDENTITY_SIZE_ONLY, /* Stored size equals the product size. */
  READER_BOOK_INFORMATION_IDENTITY_SHA256,    /* Size and SHA-256 equal the book_key digest. */
  READER_BOOK_INFORMATION_IDENTITY_MISMATCH
} reader_book_information_identity;

/* Parser fields come only from public SDK calls on a source that passed
 * identity; they are never copied from, or merged into, product fields. */
typedef enum {
  READER_BOOK_INFORMATION_PARSER_UNAVAILABLE = 0, /* No usable source, or parsing not requested. */
  READER_BOOK_INFORMATION_PARSER_NO_PUBLIC_FIELDS,/* Format exposes no cheap public attributes. */
  READER_BOOK_INFORMATION_PARSER_OK,
  READER_BOOK_INFORMATION_PARSER_PASSWORD_REQUIRED,
  READER_BOOK_INFORMATION_PARSER_FAILED
} reader_book_information_parser_status;

typedef struct { const char *key, *value; int key_truncated, value_truncated; } reader_book_information_property;

typedef struct {
  size_t struct_size;
  /* Product fields, copied from the product catalog. Strings are NUL-terminated
   * UTF-8 owned by the snapshot. */
  const char *book_key, *format, *location_kind, *title, *author;
  int author_known; /* Zero when the product author is empty: do not display a guess. */
  int title_truncated, author_truncated, favorite, deleted;
  uint64_t product_source_bytes;
  /* Local state. The SDK book ID is deliberately absent from this view. */
  reader_book_information_availability availability;
  reader_book_information_identity identity;
  uint64_t verified_bytes;       /* Nonzero only when the stored size matched. */
  const char *verified_sha256;   /* 64 lowercase hex, only for IDENTITY_SHA256. */
  /* Parser fields. Unknown values stay zero/NULL; nothing is inferred. */
  reader_book_information_parser_status parser_status;
  int page_count_known; uint64_t page_count; /* Fixed-page formats only. */
  const char *parser_title;      /* NULL when the format exposes no title. */
  int parser_title_truncated;
  int epub_mode_known, epub_bounded_storage, epub_global_extent_known;
  const reader_book_information_property *properties;
  size_t property_count;
  size_t properties_omitted;     /* Beyond the 32 cap, empty, or not valid UTF-8. */
} reader_book_information_view;

typedef struct {
  size_t struct_size;          /* sizeof(reader_book_information_options) */
  int verify_source;           /* Nonzero: hash this ONE original, 64 KiB at a time. */
  int read_parser_fields;      /* Nonzero: open the public fixed/EPUB info readers. */
  int (*cancelled)(void *context); /* Optional; nonzero cancels. Same thread. */
  void *context;               /* Borrowed for the call. */
} reader_book_information_options;

/* Read-only snapshot of one product book.
 *
 * Inputs: catalog and optional library are borrowed and must be used on their
 * creating owner thread. library may be NULL, in which case no SDK call is made.
 * book_key is "format:sha256" (the product key, at most 128 UTF-8 bytes). The
 * product row is read through reader_catalog_metadata; original bytes through
 * exr_library_source and, when requested, exr_library_fixed_source (PDF/CBZ) or
 * exr_library_epub_info_get (EPUB). Neither store is written, no SDK SQL is read,
 * nothing is imported, attached, edited or re-hashed for any other book.
 * Output: *out is a deep copy owned by the caller until reader_book_information_free.
 * It stays valid after the catalog, library, source and fixed document are closed;
 * the view is immutable and may be read from any thread. *out is NULL on failure.
 * Missing local files, a different book, passwords and unreadable parsers are field
 * states (availability/identity/parser_status), not failures. error is cleared on
 * every call, including success; its status equals the returned status on
 * failure, including cancellation inside a public parser call. Returns zero
 * (OK) on success.
 * Reentrancy: the cancel callback may not call this function (REENTRANT) and may not
 * use the catalog or library handles. Cancellation is polled before each stage and
 * between hash chunks; the module never commits, so a cancelled call leaves both
 * stores and every borrowed handle exactly as it found them. */
reader_book_information_status reader_book_information_read(reader_catalog *catalog, exr_library *library,
  const char *book_key, const reader_book_information_options *options,
  reader_book_information **out, reader_book_information_error *error);
/* Borrowed immutable view of a snapshot, or NULL. Valid until free. */
const reader_book_information_view *reader_book_information_get(const reader_book_information *snapshot);
/* Releases one snapshot. NULL is accepted and ignored. */
void reader_book_information_free(reader_book_information *snapshot);

#ifdef __cplusplus
}
#endif
#endif
