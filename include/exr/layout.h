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
/* Built-in indexed loading currently accepts EPUB. No XHTML is parsed at open. */
EXR_API exr_status exr_publication_open(const char *path, exr_publication **out,
                                        exr_error *error);
EXR_API exr_status exr_publication_open_source(const exr_source *source,
                                               exr_publication **out, exr_error *error);
EXR_API exr_status exr_publication_open_memory(exr_format format, const void *data, size_t size,
                                               exr_publication **out, exr_error *error);
EXR_API void exr_publication_free(exr_publication *publication);
EXR_API const char *exr_publication_title(const exr_publication *publication);
EXR_API const exr_part *exr_publication_parts(const exr_publication *publication, size_t *count);
/* Borrowed until publication_free; EPUB navigation is decoded on first request.
   Custom publications copy navigation through exr_publication_input. */
EXR_API exr_status exr_publication_navigation(exr_publication *publication,
                                               const exr_navigation **entries, size_t *count,
                                               exr_error *error);
/* Own the returned document with document_free(); offsets/indices are part-local. */
EXR_API exr_status exr_publication_load(exr_publication *publication, size_t part,
                                        exr_document **out, exr_error *error);
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
#ifdef __cplusplus
}
#endif
#endif
