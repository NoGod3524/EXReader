/* SPDX-License-Identifier: MIT */
#ifndef READER_READING_STATE_H
#define READER_READING_STATE_H
#include <stddef.h>
#include <stdint.h>
#include <exr/layout.h>
#include <exr/library.h>
#include <reader_revisions.h>
#ifdef __cplusplus
extern "C" {
#endif
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
#define READER_READING_STATE_VERSION "0.2.0"
#else
#define READER_READING_STATE_VERSION "0.1.0"
#endif
/* Bridge between public SDK selectors and the unchanged product revision wire
   v1 envelope with explicit anchor versions 1/2. It never reads SDK tables, never writes the product
   catalog, and never rewrites retained revision bytes. All calls follow the
   owner rules of the SDK handle and revision store passed to them. */
typedef enum {
  READER_RS_OK=0, READER_RS_ARGUMENT, READER_RS_MEMORY,
  READER_RS_SDK,               /* public SDK call failed; sdk_code is set */
  READER_RS_REVISION,          /* revision module refused; revision_code is set */
  READER_RS_NOT_REPRESENTABLE, /* real capture has no lossless wire v1 form; see gap */
  READER_RS_UNRESOLVED,        /* public resolve was not FOUND; nothing persisted */
  READER_RS_IDENTITY           /* book/page/part route mismatch; no resolve attempted */
} reader_rs_status;
typedef enum {
  READER_RS_GAP_NONE=0,
  READER_RS_GAP_POINT,          /* empty exact (start==end): every SDK progress and bookmark */
  READER_RS_GAP_TEXTLESS_PAGE,  /* fixed page snapshot without text: only a point exists */
  READER_RS_GAP_CHAPTER_SCOPE,  /* reflow selector scoped to a chapter path; v1 has no field */
  READER_RS_GAP_NUL,            /* fixed selector bytes contain NUL; v1 refuses NUL */
  READER_RS_GAP_LEGACY,         /* exact==NULL offset-only selector */
  READER_RS_GAP_LIMIT,          /* SDK path/page ID longer than the v1 field limit */
  READER_RS_GAP_ROUTE           /* EPUB part path absent or repeated in the spine */
} reader_rs_gap;
typedef struct {
  reader_rs_status code; reader_rs_gap gap;
  int sdk_code, revision_code;
  char message[160];
} reader_rs_error;
typedef enum { READER_RS_REFLOW_GLOBAL=1, READER_RS_EPUB_CHAPTER=2, READER_RS_FIXED_PAGE=3 } reader_rs_mode;

/* Envelope of one new local revision. entity_kind is progress or annotation;
   annotation_id is required for annotation and ignored for progress.
   parents are the complete observed head set; note_text is the annotation body. */
typedef struct {
  const char *revision_id, *operation, *entity_kind, *book_key, *annotation_id;
  const char *const *parents; size_t parent_count;
  const char *note_text, *parser_version;
} reader_rs_envelope;
/* A selector exactly as returned by a public SDK capture call:
   reflow_global: exr_anchor_create; epub_chapter: exr_pager_anchor_create plus
   its exr_part.path; fixed_page: exr_fixed_anchor_create plus zero-based page.
   A delete still names the mode and leaves anchor/fixed NULL. */
typedef struct {
  reader_rs_mode mode;
  const exr_anchor *anchor;
  const char *part_path;
  const exr_fixed_anchor *fixed;
  size_t page;
} reader_rs_capture;

/* Pure classification of a capture against wire v1, without allocation. */
reader_rs_gap reader_rs_classify(const reader_rs_capture *);
/* Renders exact v1 bytes only for a lossless capture, then validates them with
   reader_revision_validate. Never inserts. NOT_REPRESENTABLE leaves wire NULL;
   no quote is invented, no offset rounded and no chapter scope dropped.
   Release output with reader_rs_free. */
reader_rs_status reader_rs_encode(reader_revisions *, const reader_rs_envelope *,
  const reader_rs_capture *, char **wire, size_t *bytes, reader_rs_error *);
/* Explicit anchor v2: accepts genuine point captures, preserves reflow chapter
   scope, and includes the supplied spine index for EPUB. Other modes ignore
   part. Encoding validates bytes but does not insert or choose history. */
reader_rs_status reader_rs_encode_v2(reader_revisions *, const reader_rs_envelope *,
  const reader_rs_capture *, size_t part, char **wire, size_t *bytes, reader_rs_error *);
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
/* Explicit candidate only: fixed_page anchor3; unchanged envelope/schema1.
   Pointer presence, byte lengths and NUL selectors are preserved. No insert. */
reader_rs_status reader_rs_encode_fixed_v3(reader_revisions *,const reader_rs_envelope *,
  const reader_rs_capture *,char **wire,size_t *bytes,reader_rs_error *);
#endif
void reader_rs_free(void *);

/* Decoded copy of one revalidated wire (anchor v1/v2). has_location is zero for delete. */
typedef struct {
  char entity_kind[16], operation[8], book_key[73], annotation_id[33], parser_version[65];
  reader_rs_mode mode;
  int has_location;
  uint64_t anchor_version, page, start, end;
  char *part_path, *page_id, *exact, *prefix, *suffix, *note_text;
  size_t exact_size, prefix_size, suffix_size;
  uint64_t part; /* Present for anchor v2 EPUB, checked against path on resolve. */
  char *chapter; /* Anchor v2 reflow scope; NULL is an explicit unscoped capture. */
} reader_rs_record;
reader_rs_status reader_rs_decode(reader_revisions *, const void *wire, size_t bytes,
  reader_rs_record *, reader_rs_error *);
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
/* Accepts retained v1/v2 unchanged and explicit fixed v3. Requires raw-v3 store.
   NULL differs from an allocated empty value; sizes exclude the safety terminator. */
reader_rs_status reader_rs_decode_raw_v3(reader_revisions *,const void *,size_t,
  reader_rs_record *,reader_rs_error *);
#endif
void reader_rs_record_free(reader_rs_record *);

/* Public SDK resolution only. OK means FOUND; MISSING/AMBIGUOUS/LEGACY return
   UNRESOLVED with the SDK match copied out. Old offsets never break ties. */
reader_rs_status reader_rs_resolve_reflow(const exr_document *, const reader_rs_record *,
  const exr_control *, exr_anchor_match *, reader_rs_error *);
/* Exactly one spine part must carry part_path; a repeated path is ROUTE. */
reader_rs_status reader_rs_epub_part(const exr_publication *, const char *part_path,
  size_t *part, reader_rs_error *);
reader_rs_status reader_rs_epub_record_part(const exr_publication *, const reader_rs_record *,
  size_t *part, reader_rs_error *);
reader_rs_status reader_rs_resolve_epub(const exr_publication *, exr_pager *, size_t part,
  const reader_rs_record *, const exr_control *, exr_anchor_match *, reader_rs_error *);
/* Selects the page by its exact page_id, never by the page-number hint. */
reader_rs_status reader_rs_fixed_page(exr_fixed_document *, const char *page_id,
  size_t *page, reader_rs_error *);
reader_rs_status reader_rs_resolve_fixed(exr_fixed_document *, const reader_rs_record *,
  const exr_control *, size_t *page, exr_anchor_match *, reader_rs_error *);
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
reader_rs_status reader_rs_resolve_fixed_v3(exr_fixed_document *,const reader_rs_record *,
  const exr_control *,size_t *page,exr_anchor_match *,reader_rs_error *);
#endif

/* Annotation persistence through public SDK note APIs, only after FOUND.
   existing_note_id is the receiver's own SDK note (0 creates). Product history
   is untouched; the SDK library and product catalog are separate commits. */
reader_rs_status reader_rs_store_reflow_note(exr_library *, int64_t book_id, const exr_document *,
  const reader_rs_record *, int64_t existing_note_id, int64_t *note_id, exr_anchor_match *, reader_rs_error *);
reader_rs_status reader_rs_store_epub_note(exr_library *, int64_t book_id, const exr_publication *,
  exr_pager *, size_t part, const reader_rs_record *, int64_t existing_note_id, int64_t *note_id,
  exr_anchor_match *, reader_rs_error *);
reader_rs_status reader_rs_store_fixed_note(exr_library *, int64_t book_id, exr_fixed_document *,
  const reader_rs_record *, int64_t existing_note_id, int64_t *note_id, exr_anchor_match *, reader_rs_error *);
#ifdef __cplusplus
}
#endif
#endif
