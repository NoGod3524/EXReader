/* SPDX-License-Identifier: MIT */
#ifndef EXR_DESKTOP_DROP_H
#define EXR_DESKTOP_DROP_H
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Desktop file-input adapter, version 0.1.
 *
 * Turns what a native desktop drop, paste or clipboard read delivered into an
 * immutable, bounded exr_drop_request that owns every byte it exposes and
 * outlives the platform data object, the widget and the drop target. The host
 * then decides what to import: only EXR_DROP_ITEM_FILE entries are fit for
 * exr_sideload_import_file() (UTF-8 path, immutable until that call returns).
 * Nothing here opens, reads, copies, watches or recurses into a file; the only
 * filesystem access is one stat per local path to classify it.
 *
 * This module has no dependency on the EXReader SDK: it produces the input for
 * exr_sideload_import_file() and is installed as an independent CMake package
 * exporting a public C ABI. It starts no thread, allocates no global state and
 * builds no server.
 *
 * Hard limits (a request never exceeds them):
 *   EXR_DROP_MAX_ITEMS         256 items, rejected ones included
 *   EXR_DROP_MAX_PATH_BYTES    4096 UTF-8 bytes per local path
 *   EXR_DROP_MAX_SOURCE_BYTES  256 bytes of sanitized diagnostic text per item
 *   EXR_DROP_MAX_INPUT_BYTES   1 MiB of platform payload accepted per call
 * Larger payloads fail as a whole with EXR_DROP_TOO_LARGE; more than 256 items
 * keep the first 256 and set truncated / overflow_count; a single over-long
 * path becomes an EXR_DROP_ITEM_TOO_LONG item.
 *
 * Errors: every function returns an exr_drop_status. On any status other than
 * EXR_DROP_OK the output request pointer is set to NULL and nothing is leaked.
 * EXR_DROP_EMPTY means the payload held no entries at all (blank/comment-only
 * lists, empty HDROP, clipboard without a file-ish owner); a payload whose
 * entries were all rejected is OK and the request records why, item by item.
 *
 * Cancellation: a non-NULL control->cancelled is polled before each entry.
 * When it returns nonzero the call frees everything and returns
 * EXR_DROP_CANCELLED. A request is therefore all-or-nothing: the commit
 * boundary is the moment the function returns EXR_DROP_OK with a request.
 *
 * Memory and threads: a request is one heap block, immutable after return.
 * Any thread may read it; the last owner calls exr_drop_request_release()
 * exactly once after all readers are done (NULL is accepted). Parsing
 * functions are reentrant and thread-safe; they touch no global state. Paths
 * in a request are UTF-8 and point into the request. */
#define EXR_DROP_MAX_ITEMS 256u
#define EXR_DROP_MAX_PATH_BYTES 4096u
#define EXR_DROP_MAX_SOURCE_BYTES 256u
#define EXR_DROP_MAX_INPUT_BYTES (1024u * 1024u)

typedef enum {
  EXR_DROP_OK = 0,
  EXR_DROP_EMPTY,            /* no entries in the payload */
  EXR_DROP_ARGUMENT,         /* NULL/invalid argument or wrong struct_size */
  EXR_DROP_NO_MEMORY,
  EXR_DROP_TOO_LARGE,        /* payload above EXR_DROP_MAX_INPUT_BYTES */
  EXR_DROP_UNSUPPORTED,      /* the data object offers no file-like format */
  EXR_DROP_PLATFORM,         /* the platform API failed or was busy */
  EXR_DROP_CANCELLED,
  EXR_DROP_WRONG_THREAD      /* target used off the thread that created it */
} exr_drop_status;

typedef enum {
  EXR_DROP_ITEM_FILE = 1,    /* existing regular file; path set */
  EXR_DROP_ITEM_DIRECTORY,   /* existing directory, never recursed; path set */
  EXR_DROP_ITEM_REMOTE_URL,  /* non-file URL (http, ftp, smb, ...); source only */
  EXR_DROP_ITEM_REMOTE_HOST, /* file:// URI naming a host other than localhost */
  EXR_DROP_ITEM_VIRTUAL,     /* virtual file/promise/gio scheme; no local path */
  EXR_DROP_ITEM_INVALID,     /* bad URI syntax, escape, control byte, relative */
  EXR_DROP_ITEM_BAD_ENCODING,/* invalid UTF-8 / unpaired UTF-16 surrogate */
  EXR_DROP_ITEM_TOO_LONG,    /* path above EXR_DROP_MAX_PATH_BYTES */
  EXR_DROP_ITEM_MISSING,     /* path does not exist (path set) */
  EXR_DROP_ITEM_UNREADABLE,  /* stat failed for another reason (path set) */
  EXR_DROP_ITEM_NOT_REGULAR  /* device, pipe, socket, ... (path set) */
} exr_drop_item_status;

typedef enum {
  EXR_DROP_ORIGIN_DROP = 1,
  EXR_DROP_ORIGIN_CLIPBOARD,
  EXR_DROP_ORIGIN_TEXT       /* caller-supplied bytes (parsers called directly) */
} exr_drop_origin;

typedef struct {
  size_t struct_size;        /* set to sizeof(exr_drop_item) */
  exr_drop_item_status status;
  /* UTF-8, NUL-terminated, absolute, trailing separators removed. Non-NULL
     only for FILE, DIRECTORY, MISSING, UNREADABLE and NOT_REGULAR. */
  const char *path;
  /* Sanitized diagnostic copy of the original entry (at most 256 bytes, valid
     UTF-8, control and invalid bytes replaced by '?'). Never NULL. */
  const char *source;
} exr_drop_item;

typedef struct {
  size_t struct_size;        /* set to sizeof(exr_drop_request_info) */
  exr_drop_origin origin;
  size_t item_count;         /* items kept, 0..EXR_DROP_MAX_ITEMS */
  size_t file_count;         /* of those: EXR_DROP_ITEM_FILE */
  size_t directory_count;    /* of those: EXR_DROP_ITEM_DIRECTORY */
  size_t duplicate_count;    /* entries merged into an earlier identical one */
  size_t overflow_count;     /* distinct entries dropped beyond the item cap */
  int truncated;             /* overflow_count != 0 */
} exr_drop_request_info;

typedef struct exr_drop_request exr_drop_request;

typedef struct {
  size_t struct_size;        /* set to sizeof(exr_drop_control) */
  int (*cancelled)(void *context); /* nonzero cancels; may be NULL */
  void *context;
} exr_drop_control;

/* text/uri-list (RFC 2483): LF, CRLF or lone CR separate entries, blank lines
   and '#' comments are skipped, an initial UTF-8 BOM is skipped. Each entry
   must be a URI without spaces; file URIs are decoded strictly: %XX hex only,
   decoded bytes must be well-formed UTF-8 without control bytes, '?' and '#'
   are invalid in a file path, file://localhost and file:/// are local, any
   other host is REMOTE_HOST, other schemes REMOTE_URL (or VIRTUAL for trash:,
   recent:, mtp:, ...). On Windows only file:///X:/dir/name maps to X:\dir\name.
   Duplicates are merged on the decoded path (byte-exact; ASCII case-folded on
   Windows). control may be NULL. */
exr_drop_status exr_drop_request_from_uri_list(const char *bytes, size_t size,
    exr_drop_origin origin, const exr_drop_control *control, exr_drop_request **out);
/* x-special/gnome-copied-files: like uri-list with an optional first line
   "copy" or "cut" (ignored). */
exr_drop_status exr_drop_request_from_gnome_files(const char *bytes, size_t size,
    exr_drop_origin origin, const exr_drop_control *control, exr_drop_request **out);

typedef enum {
  EXR_DROP_UTF16_NUL_LIST = 1, /* path\0path\0\0 (CF_HDROP); stops at an empty entry */
  EXR_DROP_UTF16_LINES         /* CF_UNICODETEXT: URIs or paths, CR/LF/CRLF separated */
} exr_drop_utf16_layout;
/* units is strictly validated UTF-16 (unpaired surrogates -> BAD_ENCODING for
   that entry only). Entries are native absolute paths or URIs. At most 512 Ki
   units (1 MiB of UTF-16) are accepted; more fails with EXR_DROP_TOO_LARGE. */
exr_drop_status exr_drop_request_from_utf16(const uint16_t *units, size_t count,
    exr_drop_utf16_layout layout, exr_drop_origin origin,
    const exr_drop_control *control, exr_drop_request **out);

/* An array of native UTF-8 paths or URIs (macOS pasteboard URLs, tests). The
   summed entry bytes are bounded by EXR_DROP_MAX_INPUT_BYTES. A NULL entry is
   an argument error. */
exr_drop_status exr_drop_request_from_utf8_list(const char *const *entries, size_t count,
    exr_drop_origin origin, const exr_drop_control *control, exr_drop_request **out);

exr_drop_status exr_drop_request_get_info(const exr_drop_request *request,
    exr_drop_request_info *info);
exr_drop_status exr_drop_request_get_item(const exr_drop_request *request,
    size_t index, exr_drop_item *item);
void exr_drop_request_release(exr_drop_request *request);

const char *exr_drop_status_name(exr_drop_status status);
const char *exr_drop_item_status_name(exr_drop_item_status status);

/* Platform delivery. A drop target is created for one native control on the
   thread that owns that control (Windows: STA with OLE initialised; GTK and
   AppKit: the main thread). The callback runs on that thread only, once per
   completed drop/paste, never after exr_drop_target_destroy() returned and
   never during creation. status is EXR_DROP_OK with a request whose ownership
   moves to the callback, or an error with request == NULL. The callback may
   call exr_drop_target_destroy() on its own target (destruction is then
   completed after it returns) but must not block on other threads' use of the
   target. If the control is destroyed first the target silently becomes inert
   and destroy only frees memory. exr_drop_target_destroy() from another thread
   returns EXR_DROP_WRONG_THREAD and changes nothing. */
typedef struct exr_drop_target exr_drop_target;
typedef struct {
  size_t struct_size;        /* set to sizeof(exr_drop_target_options) */
  void (*on_drop)(void *context, exr_drop_status status, exr_drop_request *request);
  void *context;
  const exr_drop_control *control; /* copied; may be NULL */
} exr_drop_target_options;
exr_drop_status exr_drop_target_destroy(exr_drop_target *target);

#ifdef __cplusplus
}
#endif
#endif
