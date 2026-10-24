/* SPDX-License-Identifier: MIT */
#ifndef READER_NAVIGATION_H
#define READER_NAVIGATION_H
#include <stddef.h>
#include <stdint.h>
#include <exr/document.h>
#include <exr/layout.h>
#ifdef __cplusplus
extern "C" {
#endif
#define READER_NAVIGATION_VERSION "0.1.0"
#define READER_NAVIGATION_PAGE_MAX 100u          /* rows per page query: 1..100 */
#define READER_NAVIGATION_NODES_MAX 10000u       /* total rows in one snapshot */
#define READER_NAVIGATION_DEPTH_MAX 64u          /* levels: roots are depth 0, the deepest allowed is 63 */
#define READER_NAVIGATION_TEXT_MAX 4194304u      /* total copied string bytes, terminators included */
#define READER_NAVIGATION_CFI_MAX 4096u
#define READER_NAVIGATION_NONE UINT64_MAX        /* an absent/unresolved index; the SDK's SIZE_MAX */

/* Table-of-contents snapshots and navigation targets over the frozen public SDK.
   This module parses no EPUB, NCX, XHTML or PDF itself: the author's navigation
   comes from exr_publication_navigation / exr_document_navigation, a local target
   is located with exr_publication_load / exr_document_resolve, and a CFI with
   exr_publication_cfi_resolve. It never opens the network, a browser or a
   credential store, never executes label text, and never writes the SDK library,
   product history, reading position, progress, annotations or sync records. The
   host (root) performs the visible navigation itself after the user's click.

   Snapshot: open copies every row once. Order, parent, label, href, base, role and
   part are kept exactly as the SDK reported them; nothing is sorted, merged,
   deduplicated or renamed, so two rows with the same title or the same href stay
   two rows. Labels are plain text: no HTML is interpreted. A part that the SDK left
   at SIZE_MAX (unknown path, a path repeated in the spine, an external or empty
   target) stays READER_NAVIGATION_NONE here; it is never guessed to be a chapter.
   The snapshot holds no SDK pointer, so it stays valid after the publication or
   document it came from is freed; queries return their own copies as well, and a
   page outlives the snapshot handle. Limits are checked and exceeded limits are
   refused with READER_NAVIGATION_LIMIT; rows are never silently dropped or cut.

   Books without authored navigation give an empty snapshot (node_count 0). Fixed
   documents (PDF, CBZ) have no authored outline in the frozen SDK; open_pages gives
   a separate, clearly flagged by-page list that is never an author outline.

   Owner rules: a snapshot handle, its queries and close are used from the owner that
   opened it. Every SDK handle passed in is borrowed: open and resolve use it only
   during the call, resolve additionally needs the live handle of the same book. Nothing
   here creates a thread. A call made from inside an exr_control callback of the same
   snapshot returns READER_NAVIGATION_BUSY and changes nothing; the SDK handle's own
   no-reentry rule also applies. Outputs of a failed call are empty and need no free. */
typedef enum {
  READER_NAVIGATION_OK=0,
  READER_NAVIGATION_ARGUMENT,   /* NULL, size, limit option or index misuse */
  READER_NAVIGATION_MEMORY,
  READER_NAVIGATION_SDK,        /* public SDK call failed; sdk_code is its exr_status */
  READER_NAVIGATION_CANCELLED,  /* the caller's exr_control cancelled; nothing was produced */
  READER_NAVIGATION_BUSY,       /* reentrant use of a snapshot that is inside a call */
  READER_NAVIGATION_LIMIT,      /* more rows, levels or text than the checked limit */
  READER_NAVIGATION_RANGE,      /* row/part/page index outside, or a target that leaves the
                                   book container (".." above the root, absolute, backslash) */
  READER_NAVIGATION_CORRUPT,    /* the SDK refused the data as damaged (FORMAT/ENCODING), an
                                   invalid fragment escape, or a CFI it cannot resolve */
  READER_NAVIGATION_UNRESOLVED, /* local target without any matching part, or without a target */
  READER_NAVIGATION_AMBIGUOUS,  /* several parts share the target path; candidates are listed */
  READER_NAVIGATION_MISMATCH,   /* the live SDK handle is not the book of the snapshot, or an
                                   explicit identity does not match the target */
  READER_NAVIGATION_NEEDS_HOST, /* external target (a URI scheme or "//"): the host decides;
                                   this module does not fetch, launch or authenticate */
  READER_NAVIGATION_PART_ONLY   /* the part is certain but its fragment id is absent: the
                                   target holds the part and no node; the host may open the
                                   part's start explicitly, nothing is guessed */
} reader_navigation_status;
typedef struct {
  reader_navigation_status code;
  int sdk_code;
  char message[160];
} reader_navigation_error;

typedef enum {
  READER_NAVIGATION_AUTHORED=1, /* the book's own navigation (possibly empty) */
  READER_NAVIGATION_PAGES=2     /* a by-page entry list; NOT an author outline */
} reader_navigation_kind;
typedef enum {
  READER_NAVIGATION_FROM_PUBLICATION=1, /* exr_publication: parts are spine items */
  READER_NAVIGATION_FROM_DOCUMENT=2,    /* exr_document: parts are chapter indices */
  READER_NAVIGATION_FROM_FIXED=3        /* exr_fixed_document: parts are page indices */
} reader_navigation_source;
typedef enum {
  READER_NAVIGATION_TARGET_NONE=0,      /* the row has no href */
  READER_NAVIGATION_TARGET_LOCAL=1,     /* relative path and/or fragment inside the book */
  READER_NAVIGATION_TARGET_EXTERNAL=2,  /* URI scheme or network-path reference */
  READER_NAVIGATION_TARGET_PAGE=3       /* a by-page entry */
} reader_navigation_target_class;

typedef struct {
  size_t struct_size;      /* sizeof this struct */
  exr_control control;     /* copied; cancellation is polled while the call runs and its
                              context is borrowed only until the call returns */
  uint32_t max_nodes;      /* 0: 10000; may only lower the maximum */
  uint32_t max_depth;      /* 0: 64; may only lower the maximum */
  uint64_t max_text_bytes; /* 0: 4194304; may only lower the maximum */
} reader_navigation_options;

typedef struct reader_navigation reader_navigation;
typedef struct {
  reader_navigation_kind kind;
  reader_navigation_source source;
  uint32_t author_outline;   /* 1 only for AUTHORED with at least one row; 0 for PAGES and empty books */
  uint32_t reserved;
  uint64_t node_count, root_count, depth_levels, text_bytes;
  uint64_t part_count;       /* spine items / chapters / pages of the book at snapshot time */
} reader_navigation_info;

/* Snapshots. *out is NULL on failure. The book's navigation is read once; the SDK
   handle is not needed afterwards for queries, only for resolve.
   publication: parts are spine items, a repeated path is a different part each time.
   document: parts are the document's chapter indices.
   pages: one row per page (role "page", label = the page label or else its id). */
reader_navigation_status reader_navigation_open_publication(exr_publication *publication,
  const reader_navigation_options *options,reader_navigation **out,reader_navigation_error *error);
reader_navigation_status reader_navigation_open_document(const exr_document *document,
  const reader_navigation_options *options,reader_navigation **out,reader_navigation_error *error);
reader_navigation_status reader_navigation_open_pages(exr_fixed_document *document,
  const reader_navigation_options *options,reader_navigation **out,reader_navigation_error *error);
reader_navigation_status reader_navigation_info_get(reader_navigation *navigation,
  reader_navigation_info *info,reader_navigation_error *error);
/* Frees the snapshot and sets *navigation to NULL. BUSY (kept) from inside its own
   callback. A NULL *navigation is accepted. Pages and targets are not affected. */
reader_navigation_status reader_navigation_close(reader_navigation **navigation,reader_navigation_error *error);

/* One copied row. Strings are never NULL ("" when empty) and owned by the page. */
typedef struct {
  uint64_t index;       /* position in the SDK's order */
  uint64_t parent;      /* original parent row, NONE for a root */
  uint64_t part;        /* SDK part (spine item / chapter / page), NONE when unresolved */
  uint32_t depth;       /* 0 for roots */
  uint32_t child_count;
  uint32_t target_class;/* reader_navigation_target_class */
  uint32_t reserved;
  char *label, *href, *base, *role;
  char *part_path;      /* identity of `part` at snapshot time (exr_part.path); "" if none */
  char *part_id;        /* exr_part.id, chapter id or page id; "" if none */
} reader_navigation_row;
/* Owned copies; release with reader_navigation_page_free exactly once. */
typedef struct {
  reader_navigation_row *rows;
  size_t count;
  uint64_t total;       /* rows in the queried sequence (all rows, or all children of the parent) */
  uint64_t next;        /* `first` for the next call, NONE when the sequence is exhausted */
} reader_navigation_page;
/* 1..100 rows from sequence position `first`. count==0 only when first==total.
   first > total is RANGE. *page is zeroed first. */
reader_navigation_status reader_navigation_rows(reader_navigation *navigation,uint64_t first,size_t max_rows,
  reader_navigation_page *page,reader_navigation_error *error);
/* Children of one row, in the SDK's order; parent NONE lists the roots. */
reader_navigation_status reader_navigation_children(reader_navigation *navigation,uint64_t parent,uint64_t first,
  size_t max_rows,reader_navigation_page *page,reader_navigation_error *error);
void reader_navigation_page_free(reader_navigation_page *page);

typedef enum {
  READER_NAVIGATION_RESULT_SPINE=1,   /* publication part, optionally with a node */
  READER_NAVIGATION_RESULT_CHAPTER=2, /* document chapter, optionally with a node */
  READER_NAVIGATION_RESULT_CFI=3,     /* publication part plus a CFI point */
  READER_NAVIGATION_RESULT_PAGE=4     /* fixed page */
} reader_navigation_result_kind;
/* The verified native target. On success or PART_ONLY the identity is the live SDK
   handle's: `part` is the spine/chapter/page index, `part_path` the exr_part.path
   copied verbatim (NULL for a page) and `part_id` the exr_part.id (page id for a
   page). A repeated spine path is told apart by `part` alone.
   node: SPINE = node index in the document exr_publication_load(part) returns (it
   is deterministic and meaningful on a second, independent SDK object); CHAPTER =
   node index in the document; NONE when the target has no fragment, or after
   PART_ONLY. fragment is the text after the first '#' as written (still
   percent-encoded), NULL when there is none. CFI: cfi is a copy of the input and
   cfi_node/cfi_offset/cfi_side the exr_cfi_point of the chapter document (UTF-16
   offsets per the SDK); the chapter-local node ids are valid in a fresh load of
   `part`. AMBIGUOUS: part is NONE and candidates lists every part index with the
   same path, ascending. Release with reader_navigation_target_free exactly once. */
typedef struct {
  uint32_t kind;        /* reader_navigation_result_kind, 0 when empty */
  uint32_t reserved;
  uint64_t row;         /* source row, NONE for a CFI */
  uint64_t part;
  char *part_path, *part_id, *fragment;
  uint64_t node;
  char *cfi;
  uint64_t cfi_node, cfi_offset;
  uint32_t cfi_side;
  uint32_t reserved2;
  uint64_t *candidates;
  size_t candidate_count;
} reader_navigation_target;
typedef struct {
  size_t struct_size;   /* sizeof this struct */
  exr_control control;  /* copied; cancellation is polled before and after each SDK call */
  uint64_t explicit_part; /* NONE, or the spine/chapter index the host chose among the
                             listed candidates for a repeated path; it must match the
                             row's own path (and the SDK part when the SDK gave one) */
} reader_navigation_resolve_options;

/* Verify one row against the live book and report its native target. *target is
   cleared first. The snapshot's book identity (part count and the part's path and id)
   must equal the live handle's, otherwise MISMATCH. EXTERNAL rows give NEEDS_HOST;
   rows without href or without any matching part give UNRESOLVED; a path shared by
   several parts gives AMBIGUOUS unless explicit_part names one of them; the first
   match is never taken. Only publications and documents resolve local targets. */
reader_navigation_status reader_navigation_resolve_publication(reader_navigation *navigation,uint64_t row,
  exr_publication *publication,const reader_navigation_resolve_options *options,
  reader_navigation_target *target,reader_navigation_error *error);
reader_navigation_status reader_navigation_resolve_document(reader_navigation *navigation,uint64_t row,
  const exr_document *document,const reader_navigation_resolve_options *options,
  reader_navigation_target *target,reader_navigation_error *error);
reader_navigation_status reader_navigation_resolve_page(reader_navigation *navigation,uint64_t row,
  exr_fixed_document *document,const reader_navigation_resolve_options *options,
  reader_navigation_target *target,reader_navigation_error *error);
/* Resolve a stored full EPUB CFI (1..4096 bytes) with exr_publication_cfi_resolve. The
   snapshot (opened from the same publication) only provides the book identity check
   and the owner/busy guard. Publications without the built-in EPUB provider are CORRUPT
   here (SDK FORMAT), never a guess. */
reader_navigation_status reader_navigation_resolve_cfi(reader_navigation *navigation,exr_publication *publication,
  const char *cfi,const reader_navigation_resolve_options *options,reader_navigation_target *target,
  reader_navigation_error *error);
void reader_navigation_target_free(reader_navigation_target *target);
#ifdef __cplusplus
}
#endif
#endif
