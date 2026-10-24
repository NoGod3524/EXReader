/* SPDX-License-Identifier: MIT */
#ifndef READER_ANNOTATION_EXPORT_H
#define READER_ANNOTATION_EXPORT_H
#include <stddef.h>
#include <stdint.h>
#include <reader_revisions.h>
#include <reader_reading_state.h>
#ifdef __cplusplus
extern "C" {
#endif
#define READER_ANNOTATION_EXPORT_VERSION "0.1.0"
#define READER_ANNOTATION_EXPORT_FORMAT_VERSION 1u
#define READER_ANNOTATION_EXPORT_PATH_MAX 4096u        /* UTF-8 bytes of one output path */
#define READER_ANNOTATION_EXPORT_TITLE_MAX 16384u      /* UTF-8 bytes of a supplied book title */
#define READER_ANNOTATION_EXPORT_DEFAULT_MAX_BYTES ((uint64_t)64u<<20)  /* per output file */
#define READER_ANNOTATION_EXPORT_HARD_MAX_BYTES ((uint64_t)1u<<30)      /* largest accepted budget */

/* Read-only export of one book's product annotations to a JSONL file (lossless,
   machine readable) and/or a Markdown file (plain text for sharing).

   Sources: reader_revision_annotations_page (keyset, 100 per page, one read
   snapshot per page), reader_revision_heads / reader_revision_get for every
   entity without one safe head, and reader_rs_decode for the Markdown text.
   One entity is always described by one valid public snapshot: a safe page row
   keeps its own immutable head and page graph, and any other entity is read once
   through reader_revision_heads, with selection, tombstone, graph, head list,
   statistics and Markdown all classified from that same returned graph by the
   public rule of reader_projection.h. A writer that completes a parent, merges,
   deletes or restores between the page and the heads read therefore cannot
   produce a mixed record. Different entities may still come from different
   moments. The module never writes the product catalog, the revision store, the
   SDK library, notes or reading progress, resolves no anchor, opens no book, uses
   no network and never interprets HTML. It does not import and does not resolve
   conflicts: every concurrent head is exported as it is.

   Streaming: only one page of 100 small rows, one entity's head list and one
   revision at a time are in memory, never a whole book's annotations.

   Outputs: jsonl_path and markdown_path must resolve to distinct final targets.
   An alias of one target (dot segments, repeated separators, parent segments, a
   case-folded Windows path, a symlinked directory, or an existing file reached
   twice) is refused with ARGUMENT before any temporary file exists, so two
   outputs can never be published over each other.

   JSONL (UTF-8, LF, one JSON object per line; see docs/READER-ANNOTATION-EXPORT.md):
   a header line, one "annotation" line per global annotation ID in ascending
   bytewise order, then a footer line whose presence proves completeness. Every
   head carries the exact retained wire bytes as the JSON string value "wire"
   (standard JSON string escaping of well-formed UTF-8; any JSON reader restores
   the exact bytes) together with its SHA-256 and byte count.

   Markdown: fixed Chinese labels; the book title and identifiers are
   backslash-escaped, quote/prefix/suffix/note text sit in fenced code blocks
   whose fence is longer than any backtick run inside, so nothing renders as
   HTML or markup. In Markdown only, CR/CRLF become LF and other C0 controls and
   DEL become the U+2400 control pictures.

   Publication: each output is written to a fresh temporary file next to its
   target, flushed, synced, and only then renamed over the target (atomic on one
   file system). Failure, cancellation or a budget breach removes the temporary
   file and leaves any previous valid export untouched. With two outputs both
   are completed before the first is published; a failure while publishing the
   second leaves the first published (stats say which). Budgets: each output is
   limited to max_output_bytes (0 = 64 MiB, hard maximum 1 GiB; exceeding it is
   READER_ANNOTATION_EXPORT_LIMIT) and each path to 4096 UTF-8 bytes.

   Calls follow the owner rules of the borrowed reader_revisions handle: run from
   the creating worker, without reentry. The cancel callback runs on that thread,
   so a call from that callback is a reentry: it is refused with ARGUMENT and a
   fixed message before any path, store or budget is examined, the caller's stats
   is left untouched, and the outer run continues unchanged. */
typedef enum {
  READER_ANNOTATION_EXPORT_OK=0,
  READER_ANNOTATION_EXPORT_ARGUMENT,   /* bad options, identity, path or title */
  READER_ANNOTATION_EXPORT_MEMORY,
  READER_ANNOTATION_EXPORT_REVISION,   /* revision store refused; revision_code is set */
  READER_ANNOTATION_EXPORT_DECODE,     /* a retained wire could not be decoded; rs_code is set */
  READER_ANNOTATION_EXPORT_IO,         /* create/write/sync/publish failed; os_error is set */
  READER_ANNOTATION_EXPORT_LIMIT,      /* output budget exceeded */
  READER_ANNOTATION_EXPORT_CANCELLED   /* the cancel callback returned nonzero */
} reader_annotation_export_status;
typedef struct {
  reader_annotation_export_status code;
  int revision_code, rs_code, os_error;
  char message[160];
} reader_annotation_export_error;
/* Nonzero cancels. Polled before every page, entity and head and whenever an
   output buffer is flushed. */
typedef int (*reader_annotation_export_cancel_fn)(void *);
typedef struct {
  size_t struct_size;                 /* sizeof this struct */
  reader_revisions *revisions;        /* borrowed product revision store */
  const char *book_key;               /* global original identity, format:sha256 */
  const char *book_title;             /* optional UTF-8; NULL derives it from a safe book head if any */
  const char *jsonl_path;             /* optional UTF-8 output path */
  const char *markdown_path;          /* optional UTF-8 output path; at least one output is required */
  uint64_t max_output_bytes;          /* per output file, 0 = default */
  reader_annotation_export_cancel_fn cancel;
  void *cancel_context;
} reader_annotation_export_options;
typedef struct {
  uint64_t annotations;       /* global annotation IDs exported */
  uint64_t current;           /* one safe non-delete head */
  uint64_t tombstones;        /* one safe delete head */
  uint64_t pending_parents;   /* missing or foreign parents: no unique current annotation */
  uint64_t concurrent;        /* more than one head */
  uint64_t blocked_restore;   /* implicit resurrection blocked */
  uint64_t head_wires;        /* exact wires written, one per head */
  uint64_t jsonl_bytes, markdown_bytes;
  int jsonl_published, markdown_published;
} reader_annotation_export_stats;

/* Run one export. stats and error may be NULL; stats is zeroed first (a refused
   reentrant call leaves it untouched) and is only meaningful for outputs reported
   published. */
reader_annotation_export_status reader_annotation_export_run(const reader_annotation_export_options *,
  reader_annotation_export_stats *,reader_annotation_export_error *);
#ifdef __cplusplus
}
#endif
#endif
