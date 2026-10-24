/* SPDX-License-Identifier: MIT */
#ifndef READER_SEARCH_H
#define READER_SEARCH_H
#include <stddef.h>
#include <stdint.h>
#include <exr/document.h>
#include <exr/layout.h>
#ifdef __cplusplus
extern "C" {
#endif
#define READER_SEARCH_VERSION "0.1.0"
#define READER_SEARCH_QUERY_MAX 4096u
#define READER_SEARCH_BATCH_MAX 100u

/* In-book search over three explicit sources of the frozen public SDK. Matching
   is a literal, case-sensitive comparison of well-formed UTF-8 bytes over the
   SDK's normalized text: no regex, no case folding, no OCR, no persisted index.
   A query is 1..4096 bytes, well-formed UTF-8 and contains no NUL; anything else
   is refused with READER_SEARCH_QUERY before any SDK call.

   Overlap: hits are leftmost and never overlap. After a hit the next scan starts
   at that hit's end, so "aa" in "aaaa" yields [0,2) and [2,4); hits never span
   units (an EPUB spine item or a fixed page). Order is document order: unit,
   then start offset.

   Owner rules: every handle passed to open is borrowed from the host owner and
   must outlive the search handle. The search handle, its calls, results' capture
   calls and close are used from that same owner; nothing here creates a thread.
   Concurrent use is a host error. A call made from inside an exr_control
   callback of the same search handle (reentry) returns READER_SEARCH_BUSY and
   changes nothing. The module never writes the SDK library, product history,
   notes, reading progress or the source bytes. It uses only public SDK calls.

   Batches and cursors: reader_search_next returns up to max_hits (1..100) hits
   and never stores a whole book's hits. The cursor says where the next batch
   starts. A batch that fails or is cancelled is discarded in full and the
   handle's committed cursor stays at the previous successful batch, so calling
   next again retries the same batch. Termination is the `complete` flag, set
   only when every unit was scanned to its end. A batch that happens to fill
   exactly at the last hit is not complete; the following call then returns
   count==0 with complete==1. count==0 is therefore returned only together with
   complete==1. */
typedef enum {
  READER_SEARCH_OK=0,
  READER_SEARCH_ARGUMENT,  /* NULL/size/limit error, or a cursor of another search or book */
  READER_SEARCH_QUERY,     /* empty, >4096 bytes, NUL, or not well-formed UTF-8 */
  READER_SEARCH_MEMORY,
  READER_SEARCH_SDK,       /* public SDK call failed; sdk_code is its exr_status */
  READER_SEARCH_CANCELLED, /* the caller's exr_control cancelled; the batch was discarded */
  READER_SEARCH_BUSY       /* reentrant use of a handle that is inside a call */
} reader_search_status;
typedef struct {
  reader_search_status code;
  int sdk_code;
  char message[160];
} reader_search_error;

typedef enum {
  READER_SEARCH_REFLOW=1, /* exr_document, global offsets (a reflowed EPUB keeps chapter scope) */
  READER_SEARCH_EPUB=2,   /* bounded publication: one spine item at a time via the public pager */
  READER_SEARCH_FIXED=3   /* exr_fixed_document: one page's text at a time */
} reader_search_mode;

/* Plain value, safe to store or copy. It is bound to the mode, the query bytes
   and the source's unit count (EPUB spine items, fixed pages, or the reflow text
   size), and any other search is refused with ARGUMENT. `unit` is the EPUB spine
   index or fixed page index (0 for reflow). `offset` is the byte offset inside
   the unit's text at which the next hit may start. */
typedef struct {
  uint32_t version;  /* 1 */
  uint32_t mode;
  uint64_t binding;
  uint64_t unit, offset;
  uint32_t complete; /* nonzero: nothing remains */
  uint32_t reserved; /* zero */
} reader_search_cursor;

typedef struct {
  size_t struct_size;             /* sizeof this struct */
  exr_control control;            /* copied; its context is borrowed until close */
  const reader_search_cursor *resume; /* NULL starts at the beginning */
} reader_search_options;

/* One hit. Offsets are normalized UTF-8 byte offsets in the text addressed by the
   route: the whole document (REFLOW), the spine item's chapter text (EPUB) or one
   page's text (FIXED). They are location hints only: after any failure to
   resolve, an offset is never used as a fallback.
   REFLOW: `anchor` is exr_anchor_create's capture, including any chapter scope the
     SDK attached. Navigate with exr_anchor_resolve_ex on an independent SDK
     instance; use reader_rs_capture{mode=REFLOW_GLOBAL, anchor}.
   EPUB: `unit` is the spine index and part_path the exr_part.path copied
     verbatim; a path repeated in the spine is told apart by `unit`. `anchor` is
     exr_pager_anchor_create's capture. Use reader_rs_capture{mode=EPUB_CHAPTER,
     anchor, part_path} and unit as the `part` argument of reader_rs_encode_v2.
   FIXED: `unit` is the zero-based page hint, page_id the page's exact ID (the
     route; the number is never used to guess a page), page_label may be NULL, and
     `fixed` is exr_fixed_anchor_create's capture. Use reader_rs_capture{mode=
     FIXED_PAGE, fixed, page=unit}. */
typedef struct {
  reader_search_mode mode;
  uint64_t unit;
  char *part_path, *page_id, *page_label;
  uint64_t start, end;
  exr_anchor anchor;
  exr_fixed_anchor fixed;
} reader_search_hit;
/* Owned by the module; release with reader_search_result_free exactly once. */
typedef struct {
  reader_search_hit *hits;
  size_t count;
  reader_search_cursor next; /* committed cursor after this batch */
  int complete;
} reader_search_result;

typedef struct reader_search reader_search;
/* Counters of this handle's own work, including discarded batches. */
typedef struct {
  uint64_t calls, failed_calls, hits_returned;
  uint64_t bytes_scanned, units_scanned;
  uint64_t peak_module_bytes;               /* module-accounted high-water mark, an estimate */
  uint64_t sdk_peak_parse_workspace_bytes;  /* the SDK's own figure, EPUB only */
  uint64_t sdk_max_projection_bytes;        /* largest chapter text scanned, EPUB only */
} reader_search_stats;

/* Open a search. The query is copied. Sources:
   reflow: a borrowed document.
   epub: a borrowed publication and font. layout and chapter may be NULL for the
     SDK defaults; if given they are copied, but pointers inside them (such as
     user_css, callbacks and their contexts) stay borrowed until close. Pagers are
     created and freed per spine item inside next(); auxiliary items outside the
     reading order are skipped.
   fixed: a borrowed document that provides page text; one without a text
     provider fails with READER_SEARCH_SDK (the SDK's FORMAT) rather than looking
     empty. *out is NULL on failure. */
reader_search_status reader_search_open_reflow(const exr_document *document,const char *query,size_t query_size,
  const reader_search_options *options,reader_search **out,reader_search_error *error);
reader_search_status reader_search_open_epub(exr_publication *publication,exr_font *font,
  const exr_layout_config *layout,const exr_chapter_options *chapter,const char *query,size_t query_size,
  const reader_search_options *options,reader_search **out,reader_search_error *error);
reader_search_status reader_search_open_fixed(exr_fixed_document *document,const char *query,size_t query_size,
  const reader_search_options *options,reader_search **out,reader_search_error *error);

/* Scan forward and return up to max_hits (1..100). *result is zeroed first.
   On OK the result must be released with reader_search_result_free and the
   committed cursor advanced; on any other status *result is empty and nothing
   advanced. Cancellation polls the control between units, finds and 32 KiB text
   blocks; a single reflow find has no finer granularity (public find has no control). */
reader_search_status reader_search_next(reader_search *search,size_t max_hits,
  reader_search_result *result,reader_search_error *error);
void reader_search_result_free(reader_search_result *result);
/* Committed cursor, i.e. the one after the last successful batch. */
reader_search_status reader_search_cursor_get(const reader_search *search,reader_search_cursor *cursor,reader_search_error *error);
reader_search_status reader_search_stats_get(const reader_search *search,reader_search_stats *stats,reader_search_error *error);
/* Frees the handle and sets *search to NULL. BUSY (handle kept) if called from
   inside one of its own callbacks. It does not touch borrowed SDK handles. */
reader_search_status reader_search_close(reader_search **search,reader_search_error *error);
#ifdef __cplusplus
}
#endif
#endif
