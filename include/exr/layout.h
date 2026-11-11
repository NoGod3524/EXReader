/* SPDX-License-Identifier: MIT */
#ifndef EXR_LAYOUT_H
#define EXR_LAYOUT_H
#include "document.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {
  const char *title;
  const exr_part *parts;
  size_t part_count;
  exr_part_load_fn load;
  void *context;
  exr_context_release_fn release;
  const exr_navigation *navigation;
  size_t navigation_count;
} exr_publication_input;
typedef struct {
  size_t start, end, glyph_start, glyph_count;
  float y;
  size_t page;
  float x, width, height;
} exr_line;
typedef struct {
  size_t start, end, line_start, line_count;
  size_t box_start, box_count;
} exr_page;
/* Additive semantic output; exr_page/exr_line keep their original ABI.
   Chapter indices are one-based in this document/pager (0 when unknown).
   Source ranges are normalized UTF-8 offsets; line ranges index layout_lines().
   A block split across pages has one record per page. Ornaments remain text;
   a host may omit their line ranges when painting. Image-only chapter starts
   have a BODY record with line_count=0. Positioned input has no semantic records. */
typedef enum { EXR_BLOCK_BODY = 0, EXR_BLOCK_TITLE, EXR_BLOCK_ORNAMENT } exr_block_kind;
typedef struct {
  exr_block_kind kind;
  size_t node, start, end, page, line_start, line_count, chapter_index;
  int starts_chapter;
} exr_layout_block;
typedef struct {
  int starts_chapter, contains_title;
  size_t chapter_index, title_block_count;
} exr_page_structure;
EXR_API const exr_layout_block *exr_layout_blocks(const exr_layout *layout, size_t *count);
/* Invalid pages return a zero record. Borrowed blocks live until layout_free. */
EXR_API exr_page_structure exr_layout_page_structure(const exr_layout *layout, size_t page);
/* A pager over a pre-paginated EPUB part lays its content document out once at
   the native CSS viewport (content <meta name="viewport">, else the package
   rendition:viewport, else the first image's intrinsic size, else the requested
   page) and maps it into the requested page with one uniform scale, centred:
   page = native * scale + (x, y). It always yields exactly one page; CSS
   position:absolute with top/right/bottom/left is honoured on such pages.
   Reflow pages return a zero record. */
typedef enum {
  EXR_VIEWPORT_NONE = 0, EXR_VIEWPORT_CONTENT, EXR_VIEWPORT_PACKAGE, EXR_VIEWPORT_IMAGE, EXR_VIEWPORT_PAGE
} exr_viewport_source;
typedef struct {
  int fixed;
  exr_viewport_source source;
  float width, height, scale, x, y;
} exr_fixed_viewport;
EXR_API exr_fixed_viewport exr_layout_fixed_viewport(const exr_layout *layout);

typedef enum { EXR_BOX_BLOCK = 1, EXR_BOX_IMAGE, EXR_BOX_CELL } exr_box_kind;
/* Solid table-border rectangles, including collapsed grids and split cells.
   A contiguous run with one node is
   one border layer: overlapping rectangles replace within the layer, then the
   layer is composited once. This preserves translucent junction colors. */
#define EXR_BOX_BORDER 2u
/* Dashed and dotted border layers; the dash pattern scales with the border width. */
#define EXR_BOX_DASHED 4u
#define EXR_BOX_DOTTED 8u
/* Two parallel lines of half width, separated by the remaining half. */
#define EXR_BOX_DOUBLE 16u
typedef struct {
  exr_box_kind kind;
  size_t node, page, resource, start, end;
  float x, y, width, height, border_width;
  uint32_t background, border_color; /* 0xRRGGBBAA */
  unsigned flags; /* Image bit 1: placeholder. Block EXR_BOX_BORDER: border layer. */
} exr_box;
typedef enum { EXR_PAINT_GLYPH=1, EXR_PAINT_BOX=2 } exr_paint_kind;
typedef struct {
  exr_paint_kind kind;
  unsigned flags; /* Reserved; initialize to zero. */
  size_t index;   /* Index in the positioned glyph or box array. */
} exr_paint;
typedef struct {
  float width,height; /* Native coordinates: origin top left, y down. */
  exr_page content;
  size_t paint_start,paint_count;
} exr_positioned_page;
typedef struct {
  size_t struct_size; /* Set to sizeof(exr_positioned_input); zero-initialize all fields. */
  const exr_positioned_page *pages;
  size_t page_count;
  const exr_glyph *glyphs;
  size_t glyph_count;
  const exr_line *lines;
  size_t line_count;
  const exr_box *boxes;
  size_t box_count;
  const exr_paint *paints;
  size_t paint_count;
} exr_positioned_input;
typedef struct {
  float width, height, margin, font_size, line_height, paragraph_spacing;
} exr_layout_options;
typedef exr_status (*exr_image_decode_fn)(void *context, const exr_resource *resource,
                                          const void *encoded, size_t size, exr_bitmap *rgba,
                                          exr_error *error);
typedef void (*exr_image_release_fn)(void *context, exr_bitmap *rgba);
typedef struct {
  exr_layout_options page;
  const char *user_css; /* Optional UTF-8 override stylesheet; borrowed for the create call. */
  int document_css;     /* Nonzero enables book stylesheets and inline styles. */
  exr_image_decode_fn decode_image;   /* Optional host decoder, returns RGBA. */
  exr_image_release_fn release_image; /* Required with decode_image; also called on failure. */
  void *image_context;
  exr_direction direction; /* Paragraph base direction; AUTO uses first strong scalar. */
  int embedded_fonts; /* Load used local @font-face resources; defaults to enabled. */
  exr_control control; /* Layout creation / pager work; context must outlive that work. */
} exr_layout_config;
/* Borrowed effective font set used by this layout, valid until layout_free.
   Includes book fonts. Glyph font_index indexes this set; do not free this view. */
EXR_API exr_font *exr_layout_font(const exr_layout *layout);
/* Metadata is copied. On success, release (if provided) runs once after the last
   publication/session reference is freed. Without release, keep context alive.
   Callbacks must not destroy/reenter the active publication or session. */
EXR_API exr_status exr_publication_create(const exr_publication_input *input,
                                          exr_publication **out, exr_error *error);
/* Built-in publications accept EPUB, MOBI/KF8 (including .azw3), and FB2/FB2 ZIP.
   EPUB and KF8 defer body parsing until load. KF8 decodes the records intersecting
   that section and its auxiliary flows; malformed records fail at load with a
   diagnostic. Legacy MOBI is split on pagebreaks; FB2 on section boundaries.
   open_source remains the ZIP/EPUB source API; use open_memory for typed bytes. */
EXR_API exr_status exr_publication_open(const char *path, exr_publication **out,
                                        exr_error *error);
EXR_API exr_status exr_publication_open_source(const exr_source *source,
                                               exr_publication **out, exr_error *error);
EXR_API exr_status exr_publication_open_memory(exr_format format, const void *data, size_t size,
                                               exr_publication **out, exr_error *error);
/* LCP Basic Profile read-only resource decoding; the host must validate license
   trust (this codec does not verify signatures or certificates).
   passphrase is borrowed UTF-8
   for this call only: NULL means missing; an empty string is a supplied value.
   No passphrase or decrypted EPUB is written to disk. Resources are decrypted
   on demand in memory (32 MiB each), with the key retained until the last
   publication/document/session reference closes. The original open functions
   are equivalent to these with NULL. See docs/DRM.md for profile/trust limits.
   Source ownership transfers only on success, as with open_source. */
EXR_API exr_status exr_publication_open_ex(const char *path, const char *passphrase,
                                           exr_publication **out, exr_error *error);
EXR_API exr_status exr_publication_open_source_ex(const exr_source *source, const char *passphrase,
                                                  exr_publication **out, exr_error *error);
EXR_API exr_status exr_publication_open_memory_ex(exr_format format, const void *data, size_t size,
                                                  const char *passphrase, exr_publication **out, exr_error *error);
EXR_API void exr_publication_free(exr_publication *publication);
EXR_API const char *exr_publication_title(const exr_publication *publication);
/* Same policy as document_page_progression; custom publications default LTR.
   Host left/right keys and spread placement should use this, never reverse the
   logical spine directory or pager_next order. NULL returns LTR. */
EXR_API exr_direction exr_publication_page_progression(const exr_publication *publication);
EXR_API const exr_part *exr_publication_parts(const exr_publication *publication, size_t *count);
/* EPUB 3 Fixed Layout (rendition: vocabulary). An itemref
   rendition:layout-pre-paginated/-reflowable overrides the package default, so
   one publication may mix fixed and reflowable parts. spread is the declared
   page-spread-left/right/center; viewport_* is the package rendition:viewport
   ("width=W, height=H"), zero when absent. Non-EPUB parts are reflowable. */
typedef enum { EXR_RENDITION_REFLOWABLE = 0, EXR_RENDITION_PRE_PAGINATED = 1 } exr_rendition_layout;
typedef enum { EXR_SPREAD_AUTO = 0, EXR_SPREAD_LEFT, EXR_SPREAD_RIGHT, EXR_SPREAD_CENTER } exr_spread_side;
typedef struct {
  exr_rendition_layout layout;
  exr_spread_side spread;
  float viewport_width, viewport_height;
} exr_part_rendition;
EXR_API exr_status exr_publication_rendition(const exr_publication *publication, size_t part,
                                             exr_part_rendition *out, exr_error *error);
/* Two-page screens in reading order. left/right are physical slots holding
   part indices, SIZE_MAX when empty. Pre-paginated parts pair by declared
   page-spread sides; an unspecified side alternates from the previous page
   and the first page is recto (right for ltr, left for rtl). Reflowable and
   page-spread-center parts, and every part under rendition:spread none, are
   single screens (EXR_SPREAD_SINGLE, part in left). Free with exr_free(). */
#define EXR_SPREAD_SINGLE 1u
typedef struct {
  size_t left, right;
  unsigned flags;
} exr_spread;
EXR_API exr_status exr_publication_spreads(const exr_publication *publication, exr_spread **spreads,
                                           size_t *count, exr_error *error);
/* Borrowed until publication_free; EPUB navigation is decoded on first request.
   Custom publications copy navigation through exr_publication_input. */
EXR_API exr_status exr_publication_navigation(exr_publication *publication,
                                               const exr_navigation **entries, size_t *count,
                                               exr_error *error);
/* Own the returned document with document_free(); offsets/indices are part-local. */
EXR_API exr_status exr_publication_load(exr_publication *publication, size_t part,
                                        exr_document **out, exr_error *error);
/* Half-open ranges in normalized UTF-8 bytes, independent of pages. Parts are
   ordered by the publication directory; endpoints may name different parts. */
typedef struct { size_t part, offset; } exr_text_position;
typedef struct { exr_text_position start, end; } exr_text_range;

/* Speech cursor: offset uses the same normalized UTF-8 bytes as anchors. Set
   node=0 to seek; pass next unchanged to continue (node disambiguates images
   with zero text width). A cursor is valid only for the same document revision. */
typedef struct { size_t part, offset, node; } exr_ssml_position;
enum { EXR_SSML_HINT_NOTES=1, EXR_SSML_HINT_IMAGES=2, EXR_SSML_HINT_TABLES=4 };
typedef struct {
  exr_text_range range;
  size_t ssml_start, ssml_end; /* UTF-8 byte interval of sentence text in ssml. */
} exr_ssml_sentence;
typedef struct {
  char *ssml; /* Owned, NUL-terminated W3C SSML 1.0; no presentation styles. */
  size_t size, characters;
  exr_ssml_sentence *sentences;
  size_t sentence_count;
  exr_ssml_position next;
  int end; /* next.part == publication part_count */
} exr_ssml_chunk;
/* Emits at most max_chars Unicode scalars of spoken text, excluding markup and
   structural paragraph separators. 0 means 800; maximum 65536. With hints the
   minimum is 8. Flags default to 0: omit note references/bodies, images, tables.
   Hints replace each omitted subtree once with a short localized label.
   At most one linear part is emitted per call; empty/auxiliary parts advance.
   Sentences split after 。！？；.!? and at paragraph/language/omission boundaries;
   long sentences are split at the character budget. Element lang/xml:lang
   overrides publication language; untagged text defaults to zh-CN. zh/en map
   to zh-CN/en-US. Paragraphs are separated by a 300ms break, including across
   chunks. No layout or audio device is touched. Failure clears the output.
   Free each result before reuse. EOF returns an empty, valid speak document. */
EXR_API exr_status exr_document_ssml(exr_publication *publication,exr_ssml_position from_position,
  size_t max_chars,exr_ssml_chunk *out,unsigned flags,const exr_control *control,exr_error *error);
EXR_API void exr_ssml_chunk_free(exr_ssml_chunk *chunk);
enum { EXR_SEARCH_CASE_SENSITIVE=1, EXR_SEARCH_WHOLE_WORD=2 };
typedef struct { int found; size_t part, offset, length; } exr_search_result;
/* Return nonzero to continue, zero to stop (the delivered hit is counted).
   Callbacks must not reenter or destroy the publication. */
typedef int (*exr_search_fn)(void *context,const exr_search_result *result);
/* Search linear parts in directory order, from an inclusive part-local UTF-8
   position. Offsets/lengths address exr_document_text and existing anchors;
   use target={part,NULL,offset} with publication_locate. A match never bridges
   files. from.offset rounds forward to a codepoint boundary. No wraparound.
   Default folds A-Z and U+00C0..D6/D8..DE only (one-to-one, byte-length stable).
   No normalization, dictionary segmentation or visual-order transformation.
   Whole words use space/punctuation boundaries; CJK codepoints are units.
   Empty/invalid UTF-8 needles and unknown flags fail. Needle limit: 1 MiB.
   Text snapshots are cached lazily in a 16 MiB least-recently-searched cache
   until publication_free; evicted parts reload on demand, and a reload whose
   text differs from the first snapshot fails EXR_FORMAT. Reopen a mutable
   provider to search a new revision. Cancellation/failure clears result/count. */
EXR_API exr_status exr_publication_search(exr_publication *publication,exr_text_position from,
  const char *needle,unsigned flags,const exr_control *control,exr_search_result *result,exr_error *error);
/* Enumerates overlapping matches. NULL callback counts without collecting. */
EXR_API exr_status exr_publication_search_all(exr_publication *publication,const char *needle,
  unsigned flags,exr_search_fn callback,void *context,const exr_control *control,size_t *count,exr_error *error);
/* Disk-backed positional index. Run build/search/load/save on a host worker,
   with exclusive access to this publication (use a separate one from the UI).
   No internal threads are created. A zero cursor starts a query; keep the same
   needle/flags when resuming. max_results=0 streams all hits; callbacks can stop
   earlier. next advances past the delivered start, preserving overlapping hits.
   Cancellation/errors leave the input cursor unchanged and clear count.
   The legacy search APIs and their flags are unchanged. */
enum { EXR_INDEX_IGNORE_DIACRITICS=4 }; /* Latin-1 accents and U+0300..036F. */
typedef struct { exr_text_position next; int done; } exr_index_cursor;
typedef struct {
  size_t text_bytes, memory_bytes, peak_memory_bytes, disk_bytes;
  size_t indexed_parts, total_parts;
  int complete;
} exr_index_stats;
/* max_parts=0 finishes; otherwise yields after that many directory entries.
   memory_limit=0 uses 30% of indexed UTF-8 bytes, with a 512-byte handle floor.
   The budget includes the index handle and its single build/query buffer.
   Provider document parsing, stdio handles, caller needles/results are separate.
   Payloads spill to a temporary file; no hits are omitted to meet the budget.
   Explicit budgets below 512 fail EXR_LIMIT. NULL stats is allowed. */
EXR_API exr_status exr_publication_index_build(exr_publication *publication,size_t memory_limit,
  size_t max_parts,const exr_control *control,exr_index_stats *stats,exr_error *error);
EXR_API exr_status exr_publication_index_search(exr_publication *publication,const char *needle,
  unsigned flags,exr_index_cursor *cursor,size_t max_results,exr_search_fn callback,void *context,
  const exr_control *control,size_t *count,exr_error *error);
EXR_API exr_status exr_publication_index_info(exr_publication *publication,exr_index_stats *stats,
  exr_error *error);
/* Save completed or partial indexes; load resumes without parsing saved parts.
   revision must be a nonempty immutable content identity, e.g. source SHA-256.
   The host must change it whenever source bytes/projection options change.
   Version, directory identity, checksum and record bounds are also checked.
   Save writes the requested file; use a fresh path then rename for atomic host
   replacement. Failed load leaves the previous index usable. */
EXR_API exr_status exr_publication_index_save(exr_publication *publication,const char *path,
  const char *revision,const exr_control *control,exr_error *error);
EXR_API exr_status exr_publication_index_load(exr_publication *publication,const char *path,
  const char *revision,size_t memory_limit,const exr_control *control,exr_index_stats *stats,exr_error *error);
/* Owned strings; zero-initialize outputs and release with content_anchor_free.
   Stable ID (path when ID is empty) routes each endpoint after part reordering.
   The FNV-1a text revision plus size permits exact offsets in unchanged text,
   including repeated passages. Edited text uses the existing quote resolver;
   ambiguous/missing context never falls back to an old offset. Each selector is
   a point with 32 Unicode scalars of context on either side. Host stores these
   fields itself; this API defines no storage or drawing format. */
typedef struct {
  char *part_id, *part_path;
  uint64_t text_revision;
  size_t text_size;
  exr_anchor selector;
} exr_content_endpoint;
typedef struct { exr_content_endpoint start, end; } exr_content_anchor;
typedef struct { exr_anchor_state state; exr_text_range range; } exr_text_range_match;
EXR_API exr_status exr_anchor_from_range(exr_publication *publication,const exr_text_range *range,
  const exr_control *control,exr_content_anchor *out,exr_error *error);
EXR_API exr_status exr_range_from_anchor(exr_publication *publication,const exr_content_anchor *anchor,
  const exr_control *control,exr_text_range_match *out,exr_error *error);
EXR_API void exr_content_anchor_free(exr_content_anchor *anchor);
/* EPUB content anchors / part-local text ranges <-> standard CFI. Requires
   the built-in EPUB provider. Both endpoints, including cross-part ranges,
   are mapped through the original package and raw XML DOM. A point CFI
   imports as a collapsed range. Missing/ambiguous anchors fail EXR_FORMAT.
   Round trips in an unchanged publication preserve range boundaries and all
   fields of anchors captured by anchor_from_range. Outputs are owned
   (exr_free/content_anchor_free). */
EXR_API exr_status exr_range_to_cfi(exr_publication *publication,const exr_text_range *range,
  const exr_control *control,char **out,exr_error *error);
EXR_API exr_status exr_range_from_cfi(exr_publication *publication,const char *cfi,
  const exr_control *control,exr_text_range *out,exr_error *error);
EXR_API exr_status exr_anchor_to_cfi(exr_publication *publication,const exr_content_anchor *anchor,
  const exr_control *control,char **out,exr_error *error);
EXR_API exr_status exr_anchor_from_cfi(exr_publication *publication,const char *cfi,
  const exr_control *control,exr_content_anchor *out,exr_error *error);
typedef enum { EXR_RANGE_CHAR, EXR_RANGE_WORD, EXR_RANGE_SENTENCE, EXR_RANGE_PARAGRAPH } exr_range_unit;
/* CHAR is a Unicode grapheme. WORD groups non-space, non-punctuation graphemes;
   CJK ideographs/kana and punctuation are individual units (no dictionary).
   SENTENCE ends at . ! ? or their CJK equivalents, or a paragraph break;
   this deterministic rule does not infer abbreviations. PARAGRAPH uses blocks.
   A collapsed range selects the unit to its right; EOF stays collapsed.
   Nonempty ranges expand outward, with an exclusive end. Only endpoint parts
   are loaded; the returned range represents all intervening parts as well. */
EXR_API exr_status exr_range_expand(exr_publication *publication,const exr_text_range *range,
  exr_range_unit unit,const exr_control *control,exr_text_range *out,exr_error *error);
/* Lazy borrowed TOC, valid until publication_free. Priority: nav toc, NCX
   navMap, then body recovery when no linked TOC exists or all linked TOC labels
   are license notices. Recovery scans linear parts for h1..h6 and standalone
   Chinese chapter-title lines (第 + numeral + 回/章/卷/节/節). */
EXR_API exr_status exr_publication_toc(exr_publication *publication,
  const exr_toc_entry **entries,size_t *count,exr_error *error);
/* Resolve a relative internal href against a content/resource path. The caller
   supplies fragment[2048]; target.fragment borrows it. Missing/ambiguous parts
   have target.part=SIZE_MAX. External/invalid URIs return EXR_ARGUMENT. */
EXR_API exr_status exr_publication_resolve_href(const exr_publication *publication,
  const char *base,const char *href,char fragment[2048],exr_target *target,exr_error *error);
/* Part-local normalized UTF-8 offset. Missing anchors fall back to part start
   with a distinct state and are retained in missing_targets (deduplicated). */
EXR_API exr_status exr_publication_locate(exr_publication *publication,
  const exr_target *target,exr_location *location,exr_error *error);
typedef struct {
  uint64_t total_entries,resolved_exact,resolved_part_start,missing_part,missing_anchor;
} exr_locate_report;
/* Per-publication call counters, including internal calls from target_at.
   total_entries counts every locate call with a non-NULL publication, including
   errors. Outcome counters count successful calls only. Exact includes an
   explicitly requested part start; missing anchors increment both missing_anchor
   and resolved_part_start. Missing parts increment missing_part only. Repeated
   calls count again. NULL reports zero; reset does not clear missing_targets or
   invalidate cached TOC locations. Like locate, not safe for concurrent access. */
EXR_API exr_locate_report exr_publication_locate_report(const exr_publication *publication);
EXR_API void exr_publication_locate_report_reset(exr_publication *publication);
/* Borrowed until the next locate/target_at request or publication_free. */
EXR_API const exr_target *exr_publication_missing_targets(const exr_publication *publication,size_t *count);
/* Last TOC target at/before (part,offset) in reading order; deeper entries win
   ties. SIZE_MAX means before the first resolved target. Invalid offsets fail.
   Resolved TOC positions are cached; returned index addresses publication_toc. */
EXR_API exr_status exr_publication_target_at(exr_publication *publication,
  size_t part,size_t offset,size_t *entry,exr_error *error);
/* Full point CFI for the built-in indexed EPUB provider. Create accepts a
   single-chapter snapshot from this publication, with snapshot-local node IDs.
   Resolve parses only the addressed chapter and returns an independent owned
   document (document_free), plus a point local to it. Auxiliary parts fail. */
EXR_API exr_status exr_publication_cfi_create(exr_publication *publication,size_t part,const exr_document *document,
                                              const exr_cfi_point *point,const exr_control *control,char **cfi,exr_error *error);
EXR_API exr_status exr_publication_cfi_create_quoted(exr_publication *publication,size_t part,const exr_document *document,
                                                     const exr_cfi_point *point,size_t context_scalars,const exr_control *control,char **cfi,exr_error *error);
EXR_API exr_status exr_publication_cfi_resolve(exr_publication *publication,const char *cfi,const exr_control *control,
                                               size_t *part,exr_document **document,exr_cfi_point *point,exr_error *error);
EXR_API exr_layout_options exr_layout_defaults(void);
EXR_API exr_layout_config exr_layout_config_defaults(void);
/* Reader preferences. Margins are physical top/right/bottom/left CSS pixels;
   paragraph_spacing and letter_spacing are ems. The returned config describes
   the content rectangle; paint/hit-test it at (left,top)*scale. This keeps old
   config/layout ABI and defaults intact, including positioned TOC composition.
   css[1024] must outlive config use; append book-specific overrides afterwards. */
typedef struct {
  float font_size, line_height, paragraph_spacing;
  float top, right, bottom, left, letter_spacing;
} exr_reader_style;
EXR_API exr_reader_style exr_reader_style_defaults(void);
EXR_API exr_status exr_reader_style_config(const exr_reader_style *style,
  float width,float height,float scale,exr_layout_config *config,char css[1024],exr_error *error);

typedef struct {
  const char *id, *label;
  size_t target_part, target_offset;
  const char *text;
} exr_footnote;
typedef struct { size_t part, start, end, footnote; } exr_footnote_reference;
/* Lazy, publication-owned metadata; stable until publication_free. Does not
   alter reading order, source offsets, layout or navigation. References index
   footnotes (zero-based). Missing/external targets produce no reference. */
EXR_API exr_status exr_publication_footnotes(exr_publication *publication,
  const exr_footnote **footnotes,size_t *count,
  const exr_footnote_reference **references,size_t *reference_count,exr_error *error);
/* Optional dictionaries are retained. Automatic opportunities require CSS
   hyphens:auto; the CSS default remains manual. Replacement strings are literal
   and retain protected original selection ranges. Committed after text wraps
   at display grapheme/line boundaries and can be re-queried for further edits.
   Fresh points must advance display positions and respect original graphemes;
   several display points may share one source offset. The before candidate
   plus hyphen must fit the selected left line. Config record/ABI is unchanged. */
EXR_API exr_status exr_layout_create_hyphenated(const exr_document *doc,exr_font *font,
  const exr_layout_config *config,exr_hyphenator *hyphenator,exr_layout **out,exr_error *error);
EXR_API exr_status exr_layout_create(const exr_document *doc, exr_font *font,
                                     const exr_layout_options *options, exr_layout **out,
                                     exr_error *error);
EXR_API exr_status exr_layout_create_ex(const exr_document *doc, exr_font *font,
                                        const exr_layout_config *config, exr_layout **out,
                                        exr_error *error);
/* Copies pre-positioned arrays and fits each page inside the configured viewport.
   Glyph IDs/advances are supplied by the host; this path performs no shaping/reflow.
   Font may be NULL only for inputs with no glyphs. */
EXR_API exr_status exr_layout_create_positioned(const exr_document *doc, exr_font *font,
                                                const exr_positioned_input *input,
                                                const exr_layout_config *config,
                                                exr_layout **out, exr_error *error);
/* Resumable page layout. The document/font/callback context must outlive the pager.
   Config/CSS are copied. next() transfers one independent single-page layout,
   or returns EXR_OK with NULL at EOF. Pages share immutable images; serialize
   their lifetime changes with other pages from the same pager.
   After a next() error, recreate the pager. */
EXR_API exr_status exr_pager_create(const exr_document *doc, exr_font *font,
                                     const exr_layout_config *config, exr_pager **out,
                                     exr_error *error);
/* Opt-in TXT pager. On success the pager owns source->context and calls
   source->release exactly once when destroyed; on failure ownership remains
   with the caller. The source must remain byte-for-byte immutable and seekable
   until release; font and control contexts follow the ordinary pager contract.
   Paragraphs are limited to 64 KiB decoded, user CSS is unsupported, and
   pager CFI/anchor/text queries are not provided by this adapter. The source
   identity and durable storage are the caller's responsibility. */
EXR_API exr_status exr_txt_pager_create(const exr_source *source,exr_font *font,
  const exr_layout_config *config,exr_pager **out,exr_error *error);
/* Independent bounded EPUB reading path; complete-document snapshot limits and
   borrowed arrays retain their existing contract. The publication is retained.
   The caller's font and callback contexts follow the ordinary pager lifetime. */
/* workspace_budget bounds the chapter index, XML/window and CSS allocations.
   Source ZIP work reserves at most 1 MiB within it. window_bytes is a preferred
   source span: indivisible paragraphs/tables/ruby/floats still require room.
   Fonts/images, page payloads and replay checkpoints retain separate budgets. */
typedef struct {
  size_t size, workspace_budget, window_bytes;
} exr_chapter_options;
/* Live sizes include owned capacities; parse workspace also includes the pager's
   live continuation state. Its peak is a conservative upper bound including
   XML/CSS/source scratch and projection array growth overlap. Shared fonts and
   the compressed source payload are separate; book_bytes is its logical size. */
typedef struct {
  size_t book_bytes, index_bytes, parse_workspace_bytes, peak_parse_workspace_bytes;
  size_t node_count, projection_bytes;
  size_t page_cache_bytes, checkpoint_bytes, explicit_snapshot_bytes;
  size_t windows_loaded, windows_evicted;
} exr_chapter_stats;
EXR_API exr_chapter_options exr_chapter_options_defaults(void);
/* Synthetic front-matter pages. A table-of-contents layout is a separate
   exr_layout (never part of a publication part), so publication text search,
   anchors and export cannot reach it; hosts that mix it into one page list must
   consult exr_layout_page_kind() and skip EXR_PAGE_TOC pages when searching or
   copying. Ordinary layouts report EXR_PAGE_BODY for every page. */
typedef enum { EXR_PAGE_BODY = 0, EXR_PAGE_TOC = 1 } exr_page_kind;
EXR_API exr_page_kind exr_layout_page_kind(const exr_layout *layout, size_t page);
/* Reading-order part before which the TOC pages belong: right after a leading
   cover part (id/path containing "cover", or an image-only first part), else
   before the first reading-order part. SIZE_MAX when there is no reading part. */
EXR_API exr_status exr_publication_toc_insert_before(exr_publication *publication,
  size_t *part, exr_error *error);
typedef struct {
  size_t struct_size;          /* sizeof(exr_toc_page_options); zero-initialize the rest. */
  const char *const *labels;   /* One right-hand label per exr_publication_toc entry; NULL/"" omits it. */
  size_t label_count;          /* Must equal the TOC entry count when labels is set. */
  const char *title;           /* NULL: "目录" for CJK titles, else "Contents". */
  const char *continued_title; /* NULL: "目录（续）" / "Contents (continued)". */
} exr_toc_page_options;
/* Lays the publication's TOC (exr_publication_toc) out through the ordinary
   layout stack: same font, viewport and user CSS as config, single line spacing,
   no first-line indent, one em of indent per level beyond the first, and the
   label right-aligned after a continuous run of leader dots. Entries overflow to
   further pages, each repeating the continued title. *out is NULL with EXR_OK
   when the book has no TOC. Pages are not part of the body page numbering; each
   has a roman-numeral label. Pages are always horizontal; leaders and labels
   assume left-to-right rows. */
EXR_API exr_status exr_toc_pages_create(exr_publication *publication, exr_font *font,
  const exr_layout_config *config, const exr_toc_page_options *options,
  exr_layout **out, exr_error *error);
EXR_API const char *exr_toc_pages_label(const exr_layout *layout, size_t page);
/* Entries are laid out in order: page holds entries [first, first+count). */
EXR_API exr_status exr_toc_pages_entries(const exr_layout *layout, size_t page,
  size_t *first, size_t *count);
/* Row hit test in page-local coordinates (any x on the row counts). *entry is
   SIZE_MAX on the heading or empty space. The index addresses exr_publication_toc
   and the target goes to exr_publication_locate / exr_document_locate. */
EXR_API exr_status exr_toc_pages_entry_at(const exr_layout *layout, size_t page,
  float x, float y, size_t *entry);
/* Maps a normalized text offset returned by exr_layout_hit_test (or the
   position of exr_hit_test) on a TOC layout to its entry; SIZE_MAX if none. */
EXR_API size_t exr_toc_pages_entry_for_offset(const exr_layout *layout, size_t offset);
EXR_API exr_status exr_publication_pager_create(exr_publication *publication,size_t part,
  exr_font *font,const exr_layout_config *config,const exr_chapter_options *options,
  exr_pager **out,exr_error *error);
EXR_API exr_chapter_stats exr_pager_chapter_statistics(const exr_pager *pager);
/* Bounded-pager queries use stable chapter-local node IDs / normalized UTF-8
   offsets. They may evict the active window without changing page traversal.
   Full CFIs retain the publication's original spine route; context is 0..32.
   Query calls and sink callbacks must not reenter or destroy this pager. */
EXR_API exr_status exr_pager_cfi_create(exr_pager *pager,const exr_cfi_point *point,
  size_t context_scalars,const exr_control *control,char **cfi,exr_error *error);
EXR_API exr_status exr_pager_cfi_resolve(exr_pager *pager,const char *cfi,
  const exr_control *control,exr_cfi_point *point,exr_error *error);
EXR_API exr_status exr_pager_anchor_create(exr_pager *pager,size_t start,size_t end,
  const exr_control *control,exr_anchor *anchor,exr_error *error);
EXR_API exr_status exr_pager_anchor_resolve(exr_pager *pager,const exr_anchor *anchor,
  const exr_control *control,exr_anchor_match *match,exr_error *error);
/* Streams normalized selected text (whole chapter: 0..projection_bytes), in
   complete UTF-8 chunks up to 32 KiB, borrowed only during sink. On error the
   sink may have received a prefix; atomic file publication belongs to the host. */
typedef exr_status (*exr_text_sink_fn)(void *context,const char *utf8,size_t size,exr_error *error);
EXR_API exr_status exr_pager_read_text(exr_pager *pager,size_t start,size_t end,
  exr_text_sink_fn sink,void *context,const exr_control *control,exr_error *error);
EXR_API exr_status exr_pager_next(exr_pager *pager, exr_layout **out, exr_error *error);
EXR_API exr_status exr_pager_set_control(exr_pager *pager, const exr_control *control,
                                         exr_error *error);
/* Set/clear before set_cache(), get() or next(). Retains the dictionary. */
EXR_API exr_status exr_pager_set_hyphenator(exr_pager *pager,exr_hyphenator *hyphenator,exr_error *error);
/* Alternative borrowed-page mode; cannot be mixed with next(). Cache defaults to
   one page/no byte limit. Evicted pages resume from a retained checkpoint when
   available, otherwise from the beginning.
   New oversize pages return EXR_LIMIT without evicting existing cached pages. */
EXR_API exr_status exr_pager_set_cache(exr_pager *pager, size_t capacity, size_t byte_budget,
                                       exr_error *error);
EXR_API exr_status exr_pager_get(exr_pager *pager, size_t page, const exr_layout **out,
                                 exr_error *error);
EXR_API size_t exr_pager_cached_count(const exr_pager *pager);
EXR_API size_t exr_pager_cached_bytes(const exr_pager *pager);
typedef struct { size_t hits,misses; } exr_pager_cache_stats;
EXR_API exr_pager_cache_stats exr_pager_cache_statistics(const exr_pager *pager);
/* Bounded in-memory replay checkpoints, separate from the page payload cache.
   Defaults: 4 entries / 2 MiB / every 16 pages in get() mode. Capacity zero disables.
   Capacity <=64, nonzero budget/interval required when enabled; not serialized. */
EXR_API exr_status exr_pager_set_checkpoints(exr_pager *pager, size_t capacity,
                                             size_t byte_budget, size_t interval,
                                             exr_error *error);
typedef struct {
  size_t generated_pages, checkpoint_count, checkpoint_bytes, restored_checkpoints;
} exr_pager_stats;
EXR_API exr_pager_stats exr_pager_statistics(const exr_pager *pager);
/* Scanned UTF-8 source position, possibly ahead of the last page due to lookahead;
   this is progress information, not a serializable resume token. */
EXR_API size_t exr_pager_position(const exr_pager *pager);
EXR_API void exr_pager_free(exr_pager *pager);
/* Font and image callback context must outlive the session. Config/user CSS are
   copied; the publication is retained. Cache capacity is 1..64 resident parts. */
EXR_API exr_status exr_session_create(exr_publication *publication, exr_font *font,
                                      const exr_layout_config *config, size_t capacity,
                                      exr_session **out, exr_error *error);
/* Loads/layouts only this part. Borrowed views last until the next get/clear/free.
   Cache hits reuse layout; failure keeps existing cached entries. */
EXR_API exr_status exr_session_get(exr_session *session, size_t part,
                                   const exr_document **document, const exr_layout **layout,
                                   exr_error *error);
EXR_API size_t exr_session_cached(const exr_session *session);
/* Resident cache payload budget; zero is unlimited. Lowering evicts LRU entries.
   A new entry larger than the budget returns EXR_LIMIT and preserves the old cache.
   Shared sources, fonts, temporary loads and renderer bitmaps are outside this budget. */
EXR_API exr_status exr_session_set_budget(exr_session *session, size_t bytes, exr_error *error);
/* Retains the new dictionary and clears cached layouts when changed. */
EXR_API exr_status exr_session_set_hyphenator(exr_session *session,exr_hyphenator *hyphenator,exr_error *error);
EXR_API size_t exr_session_cached_bytes(const exr_session *session);
EXR_API void exr_session_clear(exr_session *session);
EXR_API void exr_session_free(exr_session *session);
EXR_API void exr_layout_free(exr_layout *layout);
EXR_API size_t exr_layout_memory_size(const exr_layout *layout);
EXR_API exr_writing_mode exr_layout_writing_mode(const exr_layout *layout);
EXR_API const exr_page *exr_layout_pages(const exr_layout *layout, size_t *count);
EXR_API const exr_line *exr_layout_lines(const exr_layout *layout, size_t *count);
EXR_API const exr_glyph *exr_layout_glyphs(const exr_layout *layout, size_t *count);
EXR_API const exr_box *exr_layout_boxes(const exr_layout *layout, size_t *count);
/* Borrowed ordered paint commands for one positioned page; NULL for reflow layouts. */
EXR_API const exr_paint *exr_layout_paints(const exr_layout *layout, size_t page, size_t *count);
/* Borrowed decoded RGBA pixels, valid until layout_free; NULL for unavailable resources. */
EXR_API const exr_bitmap *exr_layout_image(const exr_layout *layout, size_t resource);
EXR_API size_t exr_layout_page_at(const exr_layout *layout, size_t utf8_offset);
EXR_API size_t exr_layout_hit_test(const exr_layout *layout, size_t page, float x, float y);
/* Page-local layout coordinates, origin top left. Caret at the nearest cluster
   edge (bidi/vertical-aware); ligature interiors are not subdivided. Unlike the
   legacy nearest-line API, images and points outside text lines miss, returning
   {SIZE_MAX,SIZE_MAX}. part is the caller's publication directory index. */
EXR_API exr_status exr_hit_test(const exr_layout *layout,size_t part,size_t page,float x,float y,
  exr_text_position *out,exr_error *error);
#ifdef __cplusplus
}
#endif
#endif
