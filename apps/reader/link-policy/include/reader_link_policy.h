/* SPDX-License-Identifier: MIT */
#ifndef READER_LINK_POLICY_H
#define READER_LINK_POLICY_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define READER_LINK_POLICY_VERSION_STRING "0.1.0"
#define READER_LINK_POLICY_ABI_VERSION 1u

/* Link-target policy for book content. Given the raw href/src string of a link
   it decides, without any side effect, whether the target is
     INTERNAL   - stays inside the book: hand the original string to the public
                  SDK (exr_document_resolve / exr_navigation / CFI handling);
     NEEDS_HOST - an allow-listed external target the HOST may open after its
                  own user confirmation;
     REJECT     - never act on it; show the display text only.
   The package never opens, fetches, launches, resolves DNS, touches the file
   system or starts a process, and keeps no global mutable state. It does not
   parse books or URLs beyond the checks documented in READER-EXTERNAL-LINK-POLICY.md
   and never guesses a chapter: a container path is validated, not mapped.

   Ownership
     - reader_link_policy is created and destroyed by the caller. It is immutable
       after creation.
     - Input text and base path are borrowed UTF-8 bytes for one call only.
     - reader_link_result is a caller-owned value; display is a library-allocated
       copy that stays valid until reader_link_result_free and does not depend on
       the input buffer or on the policy surviving. Free every result whose
       status was READER_LINK_OK exactly once; free is idempotent on zeroed values.
   Threads and reentry
     - reader_link_classify may be called concurrently from any threads on the
       same policy. The policy is not thread-affine. reader_link_policy_destroy
       needs exclusive access (no classify in flight).
     - The cancel callback runs synchronously on the calling thread. It may call
       reader_link_classify (also on the same policy) but must not destroy it.
   Errors, cancellation, commit
     - An error status (not OK) leaves *result zeroed: nothing is committed. The
       one exception is a result whose struct_size is not sizeof(reader_link_result):
       that struct is not ours to write and is left untouched, and the call
       returns ARGUMENT. A rejected link is NOT an error: status OK with action
       REJECT.
     - Cancellation is polled on entry and at least every 4096 input bytes.
   Hard limits
     - input <= READER_LINK_MAX_INPUT_BYTES (default 8192, option up to 65536);
       internal path and fragment each < 2048 bytes and <= 256 segments, matching
       the public SDK resolver; at most 8 extra allowed schemes. */

#define READER_LINK_DEFAULT_INPUT_BYTES 8192u
#define READER_LINK_MAX_INPUT_BYTES 65536u
#define READER_LINK_MAX_SCHEMES 8u
#define READER_LINK_SCHEME_BYTES 17u /* up to 16 characters + NUL */
#define READER_LINK_INTERNAL_PART_LIMIT 2048u
#define READER_LINK_MAX_SEGMENTS 256u

typedef enum {
  READER_LINK_OK = 0,
  READER_LINK_ARGUMENT = 1,  /* null/invalid struct, option or base path */
  READER_LINK_MEMORY = 2,    /* allocation failed; nothing committed */
  READER_LINK_CANCELLED = 3  /* caller control asked to stop; nothing committed */
} reader_link_status;

typedef enum {
  READER_LINK_ACTION_REJECT = 0,
  READER_LINK_ACTION_INTERNAL = 1,
  READER_LINK_ACTION_NEEDS_HOST = 2
} reader_link_action;

typedef enum {
  READER_LINK_REASON_NONE = 0,
  READER_LINK_REASON_EMPTY = 1,
  READER_LINK_REASON_TOO_LONG = 2,
  READER_LINK_REASON_INVALID_UTF8 = 3,
  READER_LINK_REASON_CONTROL = 4,         /* C0/C1/DEL, bidi, line separators, BOM */
  READER_LINK_REASON_SPACE = 5,           /* surrounding space, or space in external */
  READER_LINK_REASON_BACKSLASH = 6,
  READER_LINK_REASON_BAD_ESCAPE = 7,      /* malformed or non-UTF-8 percent escape */
  READER_LINK_REASON_ENCODED_CONTROL = 8, /* %00 anywhere; other controls in path/host */
  READER_LINK_REASON_ENCODED_SEPARATOR = 9,
  READER_LINK_REASON_ENCODED_DOT = 10,
  READER_LINK_REASON_DOUBLE_ESCAPE = 11,
  READER_LINK_REASON_FORBIDDEN_SCHEME = 12, /* javascript:, data:, file:, ms-*: ... */
  READER_LINK_REASON_UNKNOWN_SCHEME = 13,   /* valid syntax, not allow-listed */
  READER_LINK_REASON_BAD_SCHEME = 14,       /* colon without a valid scheme */
  READER_LINK_REASON_PROTOCOL_RELATIVE = 15,
  READER_LINK_REASON_ABSOLUTE_PATH = 16,
  READER_LINK_REASON_PATH_ESCAPE = 17,      /* leaves the container root */
  READER_LINK_REASON_BAD_AUTHORITY = 18,
  READER_LINK_REASON_USERINFO = 19,
  READER_LINK_REASON_BAD_PATH_CHAR = 20,    /* ':' or '?' inside an internal path */
  READER_LINK_REASON_MALFORMED = 21
} reader_link_reason;

typedef enum {
  READER_LINK_KIND_NONE = 0,
  READER_LINK_KIND_FRAGMENT = 1,       /* "#id": same document, fragment only */
  READER_LINK_KIND_CFI = 2,            /* fragment starts with epubcfi( */
  READER_LINK_KIND_CONTAINER_PATH = 3, /* relative container path, optional fragment */
  READER_LINK_KIND_EXTERNAL = 4
} reader_link_kind;

enum {
  READER_LINK_FLAG_DISPLAY_UNSAFE = 1u, /* display has invalid UTF-8 or controls: escape before drawing */
  READER_LINK_FLAG_NON_ASCII_HOST = 2u, /* external host is not ASCII: show punycode/warn */
  READER_LINK_FLAG_HAS_FRAGMENT = 4u
};

typedef struct {
  uint32_t struct_size;
  reader_link_status status;
  size_t offset;      /* input byte offset of the problem when known */
  char message[128];
} reader_link_error;

/* Return nonzero to cancel. Called synchronously on the calling thread. */
typedef int (*reader_link_cancel_fn)(void *context);
typedef struct {
  reader_link_cancel_fn cancelled;
  void *context;
} reader_link_control;

/* Zero-initialize and set struct_size. schemes are extra lower- or mixed-case
   scheme names added to the built-in allow list {http, https, mailto}; they are
   copied. A scheme that is syntactically invalid or on the hard deny list
   (javascript, vbscript, data, file, blob, filesystem, about, jar, view-source,
   shell, ms-*, search-ms, ...) makes creation fail with ARGUMENT. */
typedef struct {
  uint32_t struct_size;
  uint32_t max_input_bytes; /* 0 = default; > READER_LINK_MAX_INPUT_BYTES is ARGUMENT */
  const char *const *schemes;
  size_t scheme_count;
} reader_link_policy_options;

typedef struct reader_link_policy reader_link_policy;

typedef struct {
  uint32_t struct_size;
  reader_link_action action;
  reader_link_reason reason;
  reader_link_kind kind;
  uint32_t flags;
  char scheme[READER_LINK_SCHEME_BYTES]; /* lower-case, external only, else "" */
  size_t input_bytes;
  /* Original input bytes, NUL terminated, owned by the result. NULL (and
     display_len 0) when the input exceeded the byte limit. */
  char *display;
  size_t display_len;
  /* Internal targets, offsets into display: [0,path_len) is the container path
     (0 for a fragment-only link); fragment is the text after '#', unmodified. */
  size_t path_len;
  size_t fragment_offset;
  size_t fragment_len;
} reader_link_result;

/* Create an immutable policy. options may be NULL for the defaults. error is
   optional. On failure *out is NULL. */
reader_link_status reader_link_policy_create(const reader_link_policy_options *options,
                                             reader_link_policy **out, reader_link_error *error);
void reader_link_policy_destroy(reader_link_policy *policy); /* NULL is a no-op */

/* Classify text[0, size). The bytes need not be NUL terminated or valid UTF-8
   (that is reported as a REJECT). base_path is the container path of the
   document that contains the link (for example "OEBPS/text/ch1.xhtml", from
   exr_navigation.base or the chapter path); NULL means the container root.
   control and error are optional. result is required; on any non-OK status it
   is zeroed. */
reader_link_status reader_link_classify(const reader_link_policy *policy, const char *text,
                                        size_t size, const char *base_path,
                                        const reader_link_control *control,
                                        reader_link_result *result, reader_link_error *error);
void reader_link_result_free(reader_link_result *result);

const char *reader_link_reason_name(reader_link_reason reason);
const char *reader_link_action_name(reader_link_action action);

#ifdef __cplusplus
}
#endif

#endif
