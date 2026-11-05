/* SPDX-License-Identifier: MIT */
#ifndef EXR_RELAY_H
#define EXR_RELAY_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

/* Bounded, read-only inventory of a relayed service directory.
 *
 * A relay carries the immutable bytes a native WebDAV service stored (original
 * books and revision wires) from the OS that produced them to the OS that
 * consumes them. The inventory pins every directory and file (length and
 * SHA-256) so the consumer can refuse a missing, extra, altered, truncated,
 * symlinked or oversized tree before it serves a single byte.
 *
 * Contract (applies to every call):
 *  - Input strings are UTF-8, NUL terminated and borrowed for the call only.
 *  - Output buffers are allocated by the library, returned only on EXR_RELAY_OK
 *    (on any failure the out parameter is NULL / untouched-zero) and released
 *    exactly once with exr_relay_free. NULL is a no-op for exr_relay_free.
 *  - Calls are stateless: any number of threads may call concurrently on
 *    different trees. The control callback runs on the calling thread, must not
 *    throw or longjmp, and may call back into this library (nothing is locked).
 *  - Nothing is created, modified or deleted under the root. There is no
 *    commit step: the result either describes the whole tree or is an error.
 *  - Cancellation is polled before each directory, before each file and after
 *    every 64 KiB read. A cancelled call returns EXR_RELAY_CANCELLED.
 *  - Hard ceilings (limits may only lower them, never raise them):
 *      EXR_RELAY_MAX_FILES, EXR_RELAY_MAX_DEPTH, EXR_RELAY_MAX_PATH_BYTES,
 *      EXR_RELAY_MAX_FILE_BYTES, EXR_RELAY_MAX_TOTAL_BYTES,
 *      EXR_RELAY_MAX_INVENTORY_BYTES.
 *    Exceeding any of them is EXR_RELAY_LIMIT, never a truncated result.
 */
#define EXR_RELAY_VERSION "0.1.0"
#define EXR_RELAY_MAX_FILES 4096u
#define EXR_RELAY_MAX_DEPTH 8u
#define EXR_RELAY_MAX_PATH_BYTES 512u
#define EXR_RELAY_MAX_FILE_BYTES ((uint64_t)128 * 1024 * 1024) /* WebDAV download ceiling */
#define EXR_RELAY_MAX_TOTAL_BYTES ((uint64_t)512 * 1024 * 1024)
#define EXR_RELAY_MAX_INVENTORY_BYTES ((size_t)2 * 1024 * 1024)

typedef enum {
  EXR_RELAY_OK = 0,
  EXR_RELAY_ARGUMENT,  /* NULL/short struct/limit above its ceiling */
  EXR_RELAY_MEMORY,
  EXR_RELAY_IO,        /* cannot read the tree, or it changed while being read */
  EXR_RELAY_LIMIT,     /* a hard ceiling was exceeded */
  EXR_RELAY_FORMAT,    /* inventory is not a well-formed exr-relay-inventory-1 document */
  EXR_RELAY_CANCELLED,
  EXR_RELAY_UNSAFE,    /* symlink/special file, non-UTF-8 or traversal-capable name */
  EXR_RELAY_MISMATCH   /* the tree differs from the inventory */
} exr_relay_status;

typedef struct { exr_relay_status code; char message[160]; } exr_relay_error;

typedef struct {
  size_t struct_size;       /* sizeof(exr_relay_limits) */
  uint32_t max_files;       /* 0 = EXR_RELAY_MAX_FILES */
  uint32_t max_depth;       /* 0 = EXR_RELAY_MAX_DEPTH */
  uint64_t max_file_bytes;  /* 0 = EXR_RELAY_MAX_FILE_BYTES */
  uint64_t max_total_bytes; /* 0 = EXR_RELAY_MAX_TOTAL_BYTES */
} exr_relay_limits;

typedef struct {
  int (*cancelled)(void *context); /* nonzero cancels; may be NULL */
  void *context;
} exr_relay_control;

/* Scan root and return the canonical inventory document (UTF-8, NUL terminated,
 * json_bytes excludes the NUL). Directory and file records are sorted bytewise
 * by their root-relative '/'-separated path and the document carries a SHA-256
 * digest over all records. Names must be valid UTF-8 without control characters,
 * quotes, backslashes, empty or dot components; no normalization is applied, so
 * NFC and NFD spellings are distinct names. Symlinks and special files are
 * refused with EXR_RELAY_UNSAFE. limits and control may be NULL. */
exr_relay_status exr_relay_inventory(const char *root_utf8, const exr_relay_limits *limits,
  const exr_relay_control *control, char **json, size_t *json_bytes, exr_relay_error *error);

/* Re-scan root and require its canonical inventory to equal the given document
 * byte for byte. The document must be an unmodified exr_relay_inventory output;
 * anything else is EXR_RELAY_MISMATCH (or EXR_RELAY_FORMAT when it does not even
 * carry the format header). The message names the first differing record. */
exr_relay_status exr_relay_verify(const char *root_utf8, const char *json, size_t json_bytes,
  const exr_relay_limits *limits, const exr_relay_control *control, exr_relay_error *error);

/* Streaming SHA-256 of one regular file, lowercase hex into out[65]. Refuses a
 * file larger than max_bytes (0 = EXR_RELAY_MAX_FILE_BYTES). */
exr_relay_status exr_relay_sha256_file(const char *path_utf8, uint64_t max_bytes,
  const exr_relay_control *control, char out_hex[65], uint64_t *bytes, exr_relay_error *error);

void exr_relay_free(void *);

#ifdef __cplusplus
}
#endif
#endif
