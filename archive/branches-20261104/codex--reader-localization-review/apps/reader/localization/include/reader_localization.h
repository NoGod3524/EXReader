/* SPDX-License-Identifier: MIT */
#ifndef READER_LOCALIZATION_H
#define READER_LOCALIZATION_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define READER_LOCALIZATION_VERSION_STRING "0.1.0"
#define READER_LOCALIZATION_ABI_VERSION 1u
/* Canonical catalog serialization version mixed into the digest header. */
#define READER_LOCALIZATION_CATALOG_FORMAT_VERSION 1

/* Hard limits. They are part of the ABI contract, and each one has its own
   refusal: a message id longer than READER_LOCALIZATION_MAX_MESSAGE_ID is
   ARGUMENT, one string value longer than
   READER_LOCALIZATION_MAX_VALUE_BYTES is VALUE_TOO_LONG (checked before
   VALUE_INVALID, so a value that is both over-long and not well-formed UTF-8
   reports VALUE_TOO_LONG), a rendered text longer than
   READER_LOCALIZATION_MAX_OUTPUT_BYTES is LIMIT, and a catalog row that
   declares more than READER_LOCALIZATION_MAX_SLOTS slots is CATALOG, refused
   before any caller parameter is examined. The shipped catalog uses at most 3
   slots and 256 template bytes; the output limit is reachable with real values
   (two 1024-byte values plus a short template exceed it), so the refusal is
   exercised on every platform rather than left theoretical. */
#define READER_LOCALIZATION_MAX_MESSAGE_ID 96u
#define READER_LOCALIZATION_MAX_SLOTS 8u
#define READER_LOCALIZATION_MAX_VALUE_BYTES 1024u
#define READER_LOCALIZATION_MAX_OUTPUT_BYTES 2048u

#if defined(_WIN32) && defined(READER_LOCALIZATION_BUILD_SHARED)
#define READER_LOCALIZATION_API __declspec(dllexport)
#elif defined(_WIN32) && defined(READER_LOCALIZATION_USE_SHARED)
#define READER_LOCALIZATION_API __declspec(dllimport)
#else
#define READER_LOCALIZATION_API
#endif

/* Fixed zh-CN/en-US user-facing text and a strict renderer for it.

   This package owns a fixed, versioned message catalog with its own stable
   message ids (reader.shelf.*, reader.import.*, reader.organize.*,
   reader.reading.*, reader.sync.*, reader.error.*, reader.a11y.*). It does not
   read, replace or shadow any host string table, platform resource bundle or
   NSLocalizedString/Gettext/ICU catalog: the host keeps its own strings and
   may call this library for additional, newly created surfaces. No global
   locale is read or written (no setlocale, no locale category, no environment
   variable); the caller names the locale explicitly on every call.

   Book titles, author names, paths, notes and server-provided account labels
   are data. They are copied into the output byte for byte and are never
   parsed: a value containing "{0}", "%s", "%n", "$1", braces, quotes, control
   or bidirectional characters is emitted literally in a single pass, so it can
   neither re-trigger substitution nor inject markup. The library is not a
   formatter for arbitrary caller templates: only the shipped catalog provides
   templates, and only the shipped slot layout is accepted.

   Threading: the library has no mutable global state in a production build
   (the test-hook build deliberately does). Every entry point is reentrant and
   may run concurrently on any thread, provided each caller passes distinct
   output buffers. Catalog strings (message ids, groups, kinds, templates)
   point into static storage for the lifetime of the process and must not be
   freed or modified.

   Cancellation: there is no cancellation point. Every entry point is a pure,
   bounded, non-blocking computation over small buffers (at most 8 values of
   1024 bytes, two passes, no allocation, no I/O, no callbacks, no locks, no
   clock). Worst case work is fixed by READER_LOCALIZATION_MAX_* limits, so a
   caller can always run it to completion on the calling thread.

   Commit boundary: the library owns no durable state. It opens no file, uses
   no product schema table, no SDK table, no wire entity and no sidecar, and
   writes nothing outside the output buffer the caller supplies. A refused call
   writes nothing at all; a successful call writes exactly one NUL-terminated
   string. Nothing here is transactional with, or committed into, the product
   database. */
typedef enum {
  READER_LOCALIZATION_OK = 0,
  READER_LOCALIZATION_ARGUMENT = 1,        /* null/invalid struct, id, value or capacity */
  READER_LOCALIZATION_UNKNOWN_MESSAGE = 2, /* id is well formed but not in the catalog */
  READER_LOCALIZATION_UNKNOWN_LOCALE = 3,  /* tag is not zh-CN or en-US */
  READER_LOCALIZATION_PARAMETER_COUNT = 4, /* param_count differs from the declared slots */
  READER_LOCALIZATION_PARAMETER_TYPE = 5,  /* kind differs from the declared slot kind */
  READER_LOCALIZATION_VALUE_INVALID = 6,   /* string value is not well-formed UTF-8 */
  READER_LOCALIZATION_VALUE_TOO_LONG = 7,  /* string value exceeds max value bytes */
  READER_LOCALIZATION_CAPACITY = 8,        /* output buffer too small; it was not written */
  READER_LOCALIZATION_LIMIT = 9,           /* rendered text exceeds max output bytes */
  READER_LOCALIZATION_CATALOG = 10         /* shipped catalog row is self-inconsistent */
} reader_localization_status;

typedef enum {
  READER_LOCALIZATION_LOCALE_ZH_CN = 1,
  READER_LOCALIZATION_LOCALE_EN_US = 2
} reader_localization_locale;

/* No shipped row declares a 'u' slot today: the kind is part of the ABI so a row
   can gain one without an ABI change, and it stays reachable while no row uses
   it, so its refusal and its rendering are exercised by the package's own
   hook-worker checks rather than claimed. */
typedef enum {
  READER_LOCALIZATION_PARAM_STRING = 1,   /* 's': borrowed UTF-8, copied verbatim */
  READER_LOCALIZATION_PARAM_INT = 2,      /* 'd': signed 64-bit decimal, ASCII, no grouping */
  READER_LOCALIZATION_PARAM_UNSIGNED = 3  /* 'u': unsigned 64-bit decimal, ASCII, no grouping */
} reader_localization_param_kind;

/* Caller-owned, immutable-by-convention locale selection. Build it with
   reader_localization_open (or set struct_size/locale and zero reserved).
   reserved must stay zero; unknown locale values are ARGUMENT. */
typedef struct {
  uint32_t struct_size;
  uint32_t locale; /* reader_localization_locale */
  uint32_t reserved[2];
} reader_localization_context;

/* One slot value. struct_size must be sizeof(reader_localization_param) and
   reserved-like padding is not read. Only the field selected by kind is
   examined; string must be NUL-terminated UTF-8 and stays borrowed for the
   duration of the call only. */
typedef struct {
  uint32_t struct_size;
  uint32_t kind; /* reader_localization_param_kind */
  const char *string;
  int64_t integer;
  uint64_t unsigned_integer;
} reader_localization_param;

/* Result of a successful measure, or the size a refused format would need.
   bytes includes the terminating NUL. slots is the declared layout. fallback
   is 1 when the requested locale has no row and en-US was used. */
typedef struct {
  uint32_t struct_size;
  size_t bytes;
  uint32_t slots;
  uint32_t fallback;
  uint32_t reserved;
} reader_localization_measurement;

/* One catalog message (locale independent): stable id, owning surface group
   and the slot layout, one kind character per slot, in slot order. */
typedef struct {
  uint32_t struct_size;
  const char *message_id;
  const char *group;
  const char *kinds;
  uint32_t slots;
  uint32_t reserved;
} reader_localization_message;

/* One resolved row. text is a borrowed catalog template (static storage, never
   freed); fallback is 1 only when text came from en-US because the requested
   locale row is absent. Callers must never treat text as a user string: it may
   contain {0}..{7} placeholders and literal braces beyond that are refused. */
typedef struct {
  uint32_t struct_size;
  const char *message_id;
  const char *locale;
  const char *text;
  uint32_t slots;
  uint32_t fallback;
  uint32_t reserved;
} reader_localization_template;

/* ABI and catalog identity. */
READER_LOCALIZATION_API uint32_t reader_localization_abi_version(void);
READER_LOCALIZATION_API int reader_localization_catalog_version(void);
/* Stable, non-localized ASCII code for logs and test reports. These names are
   never shown to a reader and contain no path, stack frame, errno text, server
   response, account or credential. */
READER_LOCALIZATION_API const char *reader_localization_status_name(reader_localization_status status);
/* "zh-CN"/"en-US" for a valid locale value, NULL otherwise. */
READER_LOCALIZATION_API const char *reader_localization_locale_tag(uint32_t locale);

/* Accepts, case-insensitively, "zh", "zh-CN", "zh_CN", "zh-Hans",
   "zh-Hans-CN", "zh_Hans", "zh_Hans_CN", "en", "en-US" and "en_US". Region
   suffixes are matched as whole subtags, so "zh-CN-x-bogus" and "de-DE" are
   UNKNOWN_LOCALE (no silent fallback to a default locale). */
READER_LOCALIZATION_API reader_localization_status
reader_localization_parse_locale(const char *tag, uint32_t *locale);

/* Fills a caller-owned context from a tag. out is untouched on failure. */
READER_LOCALIZATION_API reader_localization_status
reader_localization_open(const char *locale_tag, reader_localization_context *out);

/* Catalog enumeration, in shipped order. Both counts are constant. */
READER_LOCALIZATION_API size_t reader_localization_message_count(void);
READER_LOCALIZATION_API size_t reader_localization_template_count(void);
/* index >= count is ARGUMENT; out->struct_size must be set by the caller. */
READER_LOCALIZATION_API reader_localization_status
reader_localization_message_at(size_t index, reader_localization_message *out);
READER_LOCALIZATION_API reader_localization_status
reader_localization_template_at(size_t index, reader_localization_template *out);

/* Resolve one id for one locale, exposing the fallback flag. The requested row
   wins; a missing requested row falls back to en-US with fallback = 1; a
   missing en-US row is UNKNOWN_MESSAGE (never an empty string). */
READER_LOCALIZATION_API reader_localization_status
reader_localization_resolve(const reader_localization_context *context, const char *message_id,
                            reader_localization_template *out);

/* Required size without writing text. out may be NULL. */
READER_LOCALIZATION_API reader_localization_status
reader_localization_measure(const reader_localization_context *context, const char *message_id,
                            const reader_localization_param *params, size_t param_count,
                            reader_localization_measurement *out);

/* Renders message_id into out_text.

   Checked in this order, and the documented refusal leaves every caller buffer
   untouched: context (ARGUMENT), message id shape (ARGUMENT, then
   UNKNOWN_MESSAGE), row layout (CATALOG when the catalog row declares more
   slots than READER_LOCALIZATION_MAX_SLOTS), parameter count
   (PARAMETER_COUNT), parameter kind (PARAMETER_TYPE), string values
   (VALUE_TOO_LONG first for a value over the byte limit, then VALUE_INVALID for
   malformed UTF-8), template self-consistency (CATALOG), rendered length
   (LIMIT), capacity (CAPACITY).

   CAPACITY is the one failure that reports: out_measurement is filled with the
   required bytes so the caller can retry, while out_text keeps its previous
   bytes. On success the whole rendered string plus NUL is written,
   out_measurement (when non-NULL) is filled, and out_text bytes beyond the
   terminator are left as they were.

   A successful call never returns a partially written string: the length is
   computed and validated before the first output byte is stored. */
READER_LOCALIZATION_API reader_localization_status
reader_localization_format(const reader_localization_context *context, const char *message_id,
                           const reader_localization_param *params, size_t param_count,
                           char *out_text, size_t out_bytes,
                           reader_localization_measurement *out_measurement);

/* Lowercase hex SHA-256 (64 characters plus NUL) over the canonical catalog
   serialization of the shipped catalog:

     "reader-localization-catalog\t1\n"
     for each message in ascending byte order of message_id:
       "M\t" id "\t" group "\t" kinds "\n"
     then for each of those messages, for zh-CN first and en-US second:
       "T\t" id "\t" locale "\t" template "\n"   (absent rows are omitted)

   Templates never contain a tab or a line break. The digest covers message
   ids, groups, slot layouts and both shipped locales, so any edit of the
   resource pack changes it. It ignores test-hook overrides, allocation order
   and process state, and is identical on every platform. */
READER_LOCALIZATION_API void reader_localization_catalog_digest(char out_hex[65]);

#ifdef __cplusplus
}
#endif
#endif
