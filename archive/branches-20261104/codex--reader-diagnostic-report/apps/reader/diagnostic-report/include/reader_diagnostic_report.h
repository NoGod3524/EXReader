/* SPDX-License-Identifier: MIT */
#ifndef READER_DIAGNOSTIC_REPORT_H
#define READER_DIAGNOSTIC_REPORT_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define READER_DIAG_VERSION_STRING "0.1.0"
#define READER_DIAG_ABI_VERSION 1u
#define READER_DIAG_FORMAT_VERSION 1u

/* Hard limits. They are part of the contract and are never raised by options.
   A contract-valid input always produces a report: the maximal entry set is
   32 errors and 16 counters. */
#define READER_DIAG_MAX_ERROR_ENTRIES 32u
#define READER_DIAG_MAX_COUNTER_ENTRIES 16u
#define READER_DIAG_MAX_APP_VERSION_BYTES 32u
#define READER_DIAG_MAX_JSON_BYTES 8192u
#define READER_DIAG_MAX_SUMMARY_BYTES 4096u
#define READER_DIAG_MAX_COUNT 9007199254740991ull /* 2^53-1, exact in any JSON reader */
#define READER_DIAG_MAX_UNIX_TIME 4102444800ull   /* 2100-01-01T00:00:00Z */

/* This package installs a static C ABI library, like the other reader modules;
   there is no shared-library import/export branch. */
#define READER_DIAG_API

/* A user-triggered, bounded diagnostic report for import/sync/reading failures.

   Privacy contract. The report is assembled only from the closed set of fields
   below. The one text field, app_version, must match a strict grammar (see
   reader_diag_input.app_version) so that no free text can reach the output;
   every other value is an enumerator or a bounded integer. The library never
   reads a file, environment variable, clock, account, log or database, and never
   sends anything anywhere. Book and annotation text, titles, absolute paths,
   account URLs, credentials, server bodies, raw logs and private databases have
   no input field and therefore cannot appear. Rejected input is never echoed:
   error messages name the field, not its value.

   Ownership. Every pointer in reader_diag_input is borrowed for the duration of
   the single call and is not retained. reader_diag_report_build() allocates an
   opaque report; the caller releases it with reader_diag_report_free(). Strings
   returned by reader_diag_report_json()/summary() are owned by the report, are
   NUL-terminated ASCII, and stay valid until the report is freed. The size out
   parameters exclude the terminating NUL.

   Threads. There is no global mutable state. Distinct calls and distinct reports
   may be used concurrently from any threads. A report is immutable after build:
   any number of threads may read it concurrently, but it must not be freed while
   another call uses it. Cancel callbacks run synchronously on the calling
   thread; they may call the read-only accessors of the report being written but
   must not free it.

   Errors. Every entry point reports through a reader_diag_status return value and
   an optional reader_diag_error. error may be NULL and is always overwritten
   (cleared on success). status_name() never returns NULL. A NULL report is not
   an error for the read-only accessors: they return NULL and size 0. */
typedef enum {
  READER_DIAG_OK = 0,
  READER_DIAG_ARGUMENT = 1,  /* null/invalid struct, size, option or reserved word */
  READER_DIAG_FIELD = 2,     /* value outside its closed set, grammar or range */
  READER_DIAG_DUPLICATE = 3, /* repeated counter id or repeated (domain, kind) */
  READER_DIAG_LIMIT = 4,     /* too many entries or an output over its hard limit */
  READER_DIAG_IO = 5,        /* create/write/flush/link failed; nothing was published */
  READER_DIAG_EXISTS = 6,    /* target already exists; it was not touched */
  READER_DIAG_CANCELLED = 7, /* caller control asked to stop; nothing was published */
  READER_DIAG_MEMORY = 8
} reader_diag_status;

typedef enum {
  READER_DIAG_PLATFORM_WINDOWS = 1,
  READER_DIAG_PLATFORM_LINUX = 2,
  READER_DIAG_PLATFORM_MACOS = 3,
  READER_DIAG_PLATFORM_IOS = 4,
  READER_DIAG_PLATFORM_ANDROID = 5,
  READER_DIAG_PLATFORM_OTHER = 6
} reader_diag_platform;

/* What the user was doing when they asked for the report. */
typedef enum {
  READER_DIAG_OPERATION_IMPORT = 1,
  READER_DIAG_OPERATION_SYNC = 2,
  READER_DIAG_OPERATION_READING = 3,
  READER_DIAG_OPERATION_SEARCH = 4,
  READER_DIAG_OPERATION_OTHER = 5
} reader_diag_operation;

typedef enum {
  READER_DIAG_DOMAIN_LIBRARY = 1,
  READER_DIAG_DOMAIN_IMPORT = 2,
  READER_DIAG_DOMAIN_SYNC = 3,
  READER_DIAG_DOMAIN_READING = 4,
  READER_DIAG_DOMAIN_SEARCH = 5,
  READER_DIAG_DOMAIN_STORAGE = 6,
  READER_DIAG_DOMAIN_ACCOUNT = 7,
  READER_DIAG_DOMAIN_OTHER = 8
} reader_diag_domain;

/* Fixed error kinds. They mirror the status names already used by the reader
   packages (ARGUMENT, IO, FORMAT, VERSION, RANGE, CANCELLED, LIMIT, MEMORY, BUSY,
   NOT_FOUND, CONFLICT, INTERNAL); the host maps its own status to one of them and
   uses UNKNOWN when it cannot. */
typedef enum {
  READER_DIAG_KIND_ARGUMENT = 1,
  READER_DIAG_KIND_IO = 2,
  READER_DIAG_KIND_FORMAT = 3,
  READER_DIAG_KIND_VERSION = 4,
  READER_DIAG_KIND_RANGE = 5,
  READER_DIAG_KIND_CANCELLED = 6,
  READER_DIAG_KIND_LIMIT = 7,
  READER_DIAG_KIND_MEMORY = 8,
  READER_DIAG_KIND_BUSY = 9,
  READER_DIAG_KIND_NOT_FOUND = 10,
  READER_DIAG_KIND_CONFLICT = 11,
  READER_DIAG_KIND_INTERNAL = 12,
  READER_DIAG_KIND_UNKNOWN = 13
} reader_diag_kind;

typedef enum {
  READER_DIAG_COUNTER_BOOKS_TOTAL = 1,
  READER_DIAG_COUNTER_IMPORT_ATTEMPTS = 2,
  READER_DIAG_COUNTER_IMPORT_FAILURES = 3,
  READER_DIAG_COUNTER_SYNC_ATTEMPTS = 4,
  READER_DIAG_COUNTER_SYNC_FAILURES = 5,
  READER_DIAG_COUNTER_SYNC_CONFLICTS = 6,
  READER_DIAG_COUNTER_OPEN_FAILURES = 7,
  READER_DIAG_COUNTER_RENDER_FAILURES = 8,
  READER_DIAG_COUNTER_SEARCH_FAILURES = 9,
  READER_DIAG_COUNTER_PENDING_CHANGES = 10
} reader_diag_counter_id;

/* Tri-state host flags: 0 unknown, 1 no, 2 yes. */
enum { READER_DIAG_TRI_UNKNOWN = 0, READER_DIAG_TRI_NO = 1, READER_DIAG_TRI_YES = 2 };

typedef struct {
  uint32_t struct_size;
  reader_diag_status status;
  int system_error;  /* errno or GetLastError when status is IO, else 0 */
  char message[160]; /* static text naming a field; never contains caller values */
} reader_diag_error;

typedef int (*reader_diag_cancel_fn)(void *context);
typedef struct {
  reader_diag_cancel_fn cancelled; /* nonzero asks to stop */
  void *context;
} reader_diag_control;

typedef struct {
  uint32_t id;    /* reader_diag_counter_id */
  uint64_t value; /* 0..READER_DIAG_MAX_COUNT */
} reader_diag_counter;

typedef struct {
  uint32_t domain; /* reader_diag_domain */
  uint32_t kind;   /* reader_diag_kind */
  uint64_t count;  /* 1..READER_DIAG_MAX_COUNT occurrences */
} reader_diag_error_count;

/* Start from reader_diag_input_defaults(). */
typedef struct {
  uint32_t struct_size;
  uint32_t abi_version; /* READER_DIAG_ABI_VERSION */
  /* NUL-terminated ASCII, at most READER_DIAG_MAX_APP_VERSION_BYTES bytes:
     MAJOR.MINOR.PATCH with decimal parts of 1..6 digits and no leading zeros,
     optionally followed by "-alpha", "-beta" or "-rc" and optionally ".N"
     (1..3 digits). Anything else, including build metadata, is FIELD. */
  const char *app_version;
  uint32_t platform;  /* reader_diag_platform */
  uint32_t operation; /* reader_diag_operation */
  uint32_t sdk_abi;   /* 0..65535 */
  uint32_t sdk_major, sdk_minor, sdk_patch; /* each 0..9999 */
  uint32_t schema_version; /* product schema, 0..65535 */
  uint32_t wire_version;   /* wire format, 0..65535 */
  uint64_t generated_at_unix; /* host supplied; 0 = unknown, else <= READER_DIAG_MAX_UNIX_TIME */
  uint8_t account_configured, sync_enabled, offline_mode; /* READER_DIAG_TRI_* */
  uint8_t flag_reserved[5]; /* must be zero */
  const reader_diag_counter *counters; /* counter_count entries; ids unique */
  size_t counter_count;                /* <= READER_DIAG_MAX_COUNTER_ENTRIES */
  const reader_diag_error_count *errors; /* (domain, kind) unique */
  size_t error_count;                    /* <= READER_DIAG_MAX_ERROR_ENTRIES */
  uint32_t reserved[8];                  /* must be zero */
} reader_diag_input;

typedef struct {
  uint32_t struct_size;
  reader_diag_control control;
} reader_diag_build_options;

typedef enum {
  READER_DIAG_FORMAT_JSON = 1,
  READER_DIAG_FORMAT_SUMMARY = 2
} reader_diag_write_format;

typedef struct {
  uint32_t struct_size;
  uint32_t format; /* reader_diag_write_format; 0 = JSON */
  reader_diag_control control;
} reader_diag_write_options;

typedef struct reader_diag_report reader_diag_report;

READER_DIAG_API uint32_t reader_diag_abi_version(void);
READER_DIAG_API const char *reader_diag_status_name(reader_diag_status status);
READER_DIAG_API void reader_diag_error_clear(reader_diag_error *error);
READER_DIAG_API reader_diag_input reader_diag_input_defaults(void);

/* Validate the whole input, then build an immutable report. On any failure
   *out is NULL and nothing is allocated. options and error may be NULL. The
   build performs no I/O. Entry order in the input does not matter: the output is
   canonical (errors by domain then kind, counters by id), so equal content gives
   equal bytes. */
READER_DIAG_API reader_diag_status
reader_diag_report_build(const reader_diag_input *input,
                         const reader_diag_build_options *options,
                         reader_diag_report **out, reader_diag_error *error);

/* Readable, pretty-printed JSON (ASCII, '\n' line ends, trailing newline) with
   format "exreader-diagnostic-report" and format_version 1, and a short plain
   text summary. size may be NULL. Both are NULL when report is NULL. */
READER_DIAG_API const char *reader_diag_report_json(const reader_diag_report *report,
                                                    size_t *size);
READER_DIAG_API const char *reader_diag_report_summary(const reader_diag_report *report,
                                                       size_t *size);
READER_DIAG_API void reader_diag_report_free(reader_diag_report *report);

/* Publish JSON (default) or the summary to a NEW file at utf8_path (borrowed
   UTF-8, not retained; the parent directory must already exist).

   Commit boundary: the bytes are written to a same-directory temporary file and
   flushed; the temporary is then linked/renamed to utf8_path only if the path
   does not exist. That single step is the commit. Before it, every failure or
   cancel removes the temporary and leaves the filesystem as it was. If the target
   exists (file, directory or dangling link) the result is EXISTS and the existing
   data is not modified, opened for write or removed. After the commit OK is
   returned even if the caller cancels late. Concurrent writers to one path:
   exactly one gets OK, the rest EXISTS. A process killed at any point leaves
   either no target or the whole report, plus at most one orphan temporary named
   "<target>.reader-diagnostic.tmp-*". The library never uploads or reads the file.

   Platform notes: Windows addresses the path as UTF-8 and converts it to UTF-16
   (invalid UTF-8 is ARGUMENT) and publishes with MoveFileExW without
   MOVEFILE_REPLACE_EXISTING; POSIX publishes with link(2) and removes the
   temporary, so the target appears atomically and never replaces existing data.
   Neither backend follows a link and neither backend truncates a target. */
READER_DIAG_API reader_diag_status
reader_diag_report_write(const reader_diag_report *report, const char *utf8_path,
                         const reader_diag_write_options *options,
                         reader_diag_error *error);

#ifdef __cplusplus
}
#endif
#endif
