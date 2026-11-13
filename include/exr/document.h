/* SPDX-License-Identifier: MIT */
#ifndef EXR_DOCUMENT_H
#define EXR_DOCUMENT_H
#include "text.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {
  size_t start, end;
  unsigned heading;
} exr_block;
/* Indices and ranges use SIZE_MAX for absent/unprojected values. */
typedef enum {
  EXR_NODE_DOCUMENT = 1,
  EXR_NODE_CHAPTER,
  EXR_NODE_ELEMENT,
  EXR_NODE_TEXT,
  EXR_NODE_SECTION,
  EXR_NODE_PARAGRAPH,
  EXR_NODE_HEADING,
  EXR_NODE_LIST,
  EXR_NODE_LIST_ITEM,
  EXR_NODE_LINK,
  EXR_NODE_IMAGE,
  EXR_NODE_TABLE,
  EXR_NODE_ROW,
  EXR_NODE_CELL,
  EXR_NODE_BREAK,
  EXR_NODE_NOTE
} exr_node_kind;
typedef struct {
  const char *name, *value;
} exr_attribute;
typedef struct {
  exr_node_kind kind;
  size_t parent, first_child, next_sibling, chapter;
  size_t start, end;       /* Range in exr_document_text(), not source bytes. */
  const char *name, *text; /* XML expanded name; decoded, uncollapsed text. */
  const exr_attribute *attributes;
  size_t attribute_count;
} exr_node;
typedef struct {
  const char *id, *path;
  size_t root, resource;
  int in_spine, linear;
} exr_chapter;
typedef struct {
  const char *id, *path, *media_type, *properties;
} exr_resource;

/* Construction inputs: node indices refer to this input's preorder node array.
   Node 0 is DOCUMENT; each direct child is a CHAPTER listed exactly once below.
   The engine computes children, siblings, chapter membership and UTF-8 ranges. */
typedef struct {
  exr_node_kind kind;
  size_t parent;           /* SIZE_MAX for node 0; otherwise an earlier ancestor. */
  const char *name, *text; /* text is required only for TEXT nodes. */
  const exr_attribute *attributes;
  size_t attribute_count;
} exr_node_input;

typedef struct {
  const char *id, *path; /* path is a canonical, relative virtual path. */
  size_t root;
  int in_reading_order; /* Zero keeps an auxiliary chapter accessible by links. */
} exr_chapter_input;

typedef struct {
  exr_resource info;
  const void *data; /* NULL/0 declares metadata without encoded bytes. */
  size_t size;
} exr_resource_input;

typedef struct {
  const char *title;
  const exr_node_input *nodes;
  size_t node_count;
  const exr_chapter_input *chapters;
  size_t chapter_count;
  const exr_resource_input *resources;
  size_t resource_count;
} exr_document_input;

/* Portable text selectors. Offsets are UTF-8 bytes in normalized document text;
   exact/prefix/suffix/chapter are owned strings from create(), or host inputs.
   NULL exact denotes a legacy offset-only anchor. chapter is an optional path scope. */
typedef struct {
  size_t start, end;
  char *exact, *prefix, *suffix, *chapter;
} exr_anchor;
typedef enum {
  EXR_ANCHOR_MISSING = 0,
  EXR_ANCHOR_FOUND,
  EXR_ANCHOR_AMBIGUOUS,
  EXR_ANCHOR_LEGACY
} exr_anchor_state;
typedef struct {
  exr_anchor_state state;
  size_t start, end; /* SIZE_MAX unless FOUND. */
} exr_anchor_match;

/* A part may be a chapter, page, or a host-defined independently laid-out unit.
   Identifiers and paths are stable metadata, not whole-book text offsets. */
typedef struct {
  const char *id, *path, *title;
  int in_reading_order;
} exr_part;
/* A successful loader transfers an independent document to the engine. */
typedef exr_status (*exr_part_load_fn)(void *context, size_t part, exr_document **out,
                                       exr_error *error);
/* Flat navigation tree. Parent must precede its child; SIZE_MAX denotes a root
   or unresolved/ambiguous part. href is relative to base; arbitrary role labels
   permit host-defined navigation categories (e.g. toc, page-list, landmarks). */
typedef struct {
  size_t parent, part;
  const char *label, *href, *base, *role;
} exr_navigation;

typedef enum { EXR_TOC_HOST, EXR_TOC_NAV, EXR_TOC_NCX, EXR_TOC_RECOVERED } exr_toc_source;
/* fragment is decoded UTF-8 (no leading #). offset is SIZE_MAX for URI targets,
   or a part-local normalized UTF-8 byte offset for recovered headings. */
typedef struct { size_t part; const char *fragment; size_t offset; } exr_target;
typedef struct {
  const char *title;
  size_t level;             /* One-based nesting depth. */
  exr_target target;
  exr_toc_source source;
  size_t play_order;        /* NCX playOrder, SIZE_MAX if absent/invalid. */
} exr_toc_entry;
typedef enum {
  EXR_LINK_FOUND, EXR_LINK_ANCHOR_MISSING, EXR_LINK_PART_MISSING
} exr_link_state;
typedef struct { size_t part, offset; exr_link_state state; } exr_location;
/* Resolves a decoded id/xml:id or legacy a@name in a single-part snapshot.
   Exact matches win, then unique Unicode uppercase-equivalent matches. Missing anchors
   return EXR_OK, offset 0 and ANCHOR_MISSING; empty fragment means part start. */
EXR_API exr_status exr_document_locate(const exr_document *document,const char *fragment,
                                      exr_location *location,exr_error *error);
typedef struct exr_fixed_document exr_fixed_document;
typedef struct exr_fixed_text exr_fixed_text;
enum { EXR_REGION_VERTICAL=1,EXR_REGION_INVISIBLE=2 };
typedef struct {
  size_t start,end; /* UTF-8 byte range; multiple regions may share a range. */
  double quad[8];  /* Four ordered corners in native page coordinates. */
  unsigned flags;
} exr_text_region;
/* Copies length-delimited UTF-8 and independent text quads, without imposing
   visual/reading order or one-glyph-per-character assumptions. */
EXR_API exr_status exr_fixed_text_create(const char *utf8,size_t size,const exr_text_region *regions,size_t count,
                                          const exr_control *control,exr_fixed_text **out,exr_error *error);
EXR_API void exr_fixed_text_free(exr_fixed_text *text);
EXR_API const char *exr_fixed_text_string(const exr_fixed_text *text,size_t *size);
EXR_API const exr_text_region *exr_fixed_text_regions(const exr_fixed_text *text,size_t *count);
EXR_API size_t exr_fixed_text_memory_size(const exr_fixed_text *text);
/* Exact, case-sensitive UTF-8 byte search, including embedded NUL. A miss sets
   start/end to SIZE_MAX. Queries are limited to 1 MiB; from rounds forward to UTF-8. */
EXR_API exr_status exr_fixed_text_find(const exr_fixed_text *text,const char *query,size_t query_size,size_t from,
                                        const exr_control *control,size_t *start,size_t *end,exr_error *error);
/* Copies whole overlapping regions in provider order; no ligature subdivision.
   UTF-8 range boundaries are required. Free returned regions with exr_free(). */
EXR_API exr_status exr_fixed_text_select(const exr_fixed_text *text,size_t start,size_t end,const exr_control *control,
                                          exr_text_region **regions,size_t *count,exr_error *error);
/* Nearest source-space quad within max_distance. Equal distances keep the first
   provider region. A miss returns SIZE_MAX; exclude_flags filters region flags. */
EXR_API exr_status exr_fixed_text_hit(const exr_fixed_text *text,double x,double y,double max_distance,unsigned exclude_flags,
                                       const exr_control *control,size_t *region,exr_error *error);

/* Owned from create, or explicit host inputs. Selector byte lengths preserve NUL;
   page_id is a nonempty UTF-8 string. Old offsets never override ambiguity. */
typedef struct {
  size_t start,end;
  char *page_id,*exact,*prefix,*suffix;
  size_t exact_size,prefix_size,suffix_size;
} exr_fixed_anchor;
EXR_API exr_status exr_fixed_anchor_create(const char *page_id,const exr_fixed_text *text,size_t start,size_t end,
                                            exr_fixed_anchor *out,exr_error *error);
EXR_API void exr_fixed_anchor_free(exr_fixed_anchor *anchor);
EXR_API exr_status exr_fixed_anchor_resolve(const char *page_id,const exr_fixed_text *text,const exr_fixed_anchor *anchor,
                                             const exr_control *control,exr_anchor_match *match,exr_error *error);

typedef struct {
  const char *id,*label;
  exr_page_geometry geometry;
} exr_fixed_page;
typedef exr_status (*exr_fixed_draw_fn)(void *context,size_t page,const double matrix[6],
                                         const exr_draw_sink *sink,const exr_control *control,exr_error *error);
typedef exr_status (*exr_fixed_draw_ex_fn)(void *context,size_t page,const double matrix[6],
  const exr_draw_sink_ex *sink,const exr_control *control,exr_error *error);
typedef exr_status (*exr_fixed_text_fn)(void *context,size_t page,const exr_control *control,
                                         exr_fixed_text **out,exr_error *error);
typedef exr_status (*exr_fixed_metadata_fn)(void *context,const exr_control *control,
  const exr_metadata_entry **entries,size_t *count,exr_error *error);
/* Page-source coordinates; quad components preserve the provider's declared
   order. Properties keep format-specific text without a fixed annotation enum. */
typedef struct {
  const char *id,*kind; double bounds[4];
  const double *quads; size_t quad_count;
  const exr_metadata_entry *properties; size_t property_count;
} exr_page_annotation;
typedef exr_status (*exr_fixed_annotations_fn)(void *context,size_t page,const exr_control *control,
  const exr_page_annotation **annotations,size_t *count,exr_error *error);
typedef struct {
  size_t struct_size;
  const char *title;
  const exr_fixed_page *pages; size_t page_count;
  exr_fixed_draw_fn draw;
  void *context;
  exr_context_release_fn release;
  exr_fixed_text_fn text; /* Optional; appended after the original required prefix. */
  exr_fixed_metadata_fn metadata; /* Optional, lazy document metadata. */
  exr_fixed_annotations_fn annotations; /* Optional, lazy page annotation data. */
  exr_fixed_draw_ex_fn draw_ex; /* Optional versioned drawing provider; draw remains required. */
} exr_fixed_input;
typedef struct {
  uint32_t channels,background; /* channels 0 -> RGBA */
  size_t mask_budget;
  exr_control control;
} exr_fixed_render_options;
/* Metadata is copied. Provider context ownership transfers only on success.
     Empty IDs become page-1, page-2, ...; effective IDs must be unique.
     A zero page_count is valid; pages may then be NULL. draw is required. */
EXR_API exr_status exr_fixed_create(const exr_fixed_input *input,exr_fixed_document **out,exr_error *error);
EXR_API void exr_fixed_free(exr_fixed_document *document);
EXR_API exr_status exr_fixed_load_metadata(exr_fixed_document *document,const exr_control *control,
  exr_metadata_entry **entries,size_t *count,exr_error *error);
EXR_API exr_status exr_fixed_load_annotations(exr_fixed_document *document,size_t page,const exr_control *control,
  exr_page_annotation **annotations,size_t *count,exr_error *error);
EXR_API void exr_page_annotations_free(exr_page_annotation *annotations,size_t count);
EXR_API const char *exr_fixed_title(const exr_fixed_document *document);
EXR_API const exr_fixed_page *exr_fixed_pages(const exr_fixed_document *document,size_t *count);
/* Owned directory/metadata bytes, excluding the provider's own payload. */
EXR_API size_t exr_fixed_memory_size(const exr_fixed_document *document);
/* Loads an independent owned text snapshot only when requested. The same
   nonconcurrent/nonreentrant provider rule as draw applies. */
EXR_API exr_status exr_fixed_load_text(exr_fixed_document *document,size_t page,const exr_control *control,
                                        exr_fixed_text **out,exr_error *error);
/* Strict text load: EXR_NO_TEXT_LAYER and *out=NULL for an empty page. The
   original load_text keeps its empty-snapshot behavior for existing callers.
   Missing text providers return EXR_UNSUPPORTED. No OCR is performed. */
EXR_API exr_status exr_fixed_page_text(exr_fixed_document *document,size_t page,const exr_control *control,
                                      exr_fixed_text **out,exr_error *error);
typedef struct {
  size_t start,end; /* Global UTF-8 byte offsets, end exclusive. */
  size_t start_page,start_offset,end_page,end_offset; /* Zero-based page + byte. */
} exr_search_match;
/* Exact case-sensitive UTF-8 search from offset, inclusive, across fixed pages.
   Text follows provider order, concatenated WITHOUT added page separators.
   Empty pages contribute zero bytes. Miss: OK with every match field SIZE_MAX;
   entirely textless document: EXR_NO_TEXT_LAYER. Query: NUL-terminated, 1..1 MiB.
   An interior UTF-8 offset rounds forward. Loads at most one page at a time;
   query preprocessing is linear and bounded. Failure clears the match. */
EXR_API exr_status exr_document_search(exr_fixed_document *document,size_t offset,const char *needle,
                                       const exr_control *control,exr_search_match *match,exr_error *error);
/* Exact containment in native page coordinates (use inverse viewport matrix
   for screen input). Invisible text is excluded. A hit copies the source quad
   and UTF-8 range; character is its first Unicode scalar. A ligature's complete
   mapping retains one quad/range, without invented per-letter geometry.
   NO_TEXT_LAYER differs from NO_TEXT_AT_POINT; failure clears both outputs. */
EXR_API exr_status exr_fixed_character_at(exr_fixed_document *document,size_t page,double x,double y,
                                          const exr_control *control,exr_text_region *region,
                                          uint32_t *character,exr_error *error);
/* Streams one page in source coordinates through matrix (NULL -> identity).
   No implicit clip/state changes. The provider must skip absent callbacks.
   One document cannot be drawn concurrently or reentered from a callback. */
EXR_API exr_status exr_fixed_draw(exr_fixed_document *document,size_t page,const double matrix[6],
                                   const exr_draw_sink *sink,const exr_control *control,exr_error *error);
/* Uses draw_ex when supplied, otherwise the original provider with sink.base. */
EXR_API exr_status exr_fixed_draw_ex(exr_fixed_document *document,size_t page,const double matrix[6],
  const exr_draw_sink_ex *sink,const exr_control *control,exr_error *error);
/* Creates a natural-size viewport, clips to it, then paints just this page.
   NULL options default to white RGBA. Failure returns no partial bitmap. */
EXR_API exr_status exr_fixed_render(exr_fixed_document *document,size_t page,double scale,
                                     const exr_fixed_render_options *options,exr_bitmap *out,exr_error *error);
/* Copies every input string/attribute/blob during this call. Failure leaves *out NULL. */
EXR_API exr_status exr_document_create(const exr_document_input *input, exr_document **out,
                                       exr_error *error);
EXR_API void exr_document_free(exr_document *doc);
/* Owned allocation payload, excluding shared source archives and allocator overhead. */
EXR_API size_t exr_document_memory_size(const exr_document *doc);
EXR_API const char *exr_document_text(const exr_document *doc, size_t *size);
EXR_API const char *exr_document_title(const exr_document *doc);
/* Physical book progression, independent of paragraph bidi. Explicit OPF spine
   ltr/rtl wins; default/absent uses ar/he/iw/fa/ur/yi/ps/sd/dv primary language
   subtags, otherwise LTR (also for NULL). RTL means next page is on the left. */
EXR_API exr_direction exr_document_page_progression(const exr_document *doc);
EXR_API const exr_block *exr_document_blocks(const exr_document *doc, size_t *count);
EXR_API const exr_node *exr_document_nodes(const exr_document *doc, size_t *count);
EXR_API const exr_chapter *exr_document_chapters(const exr_document *doc, size_t *count);
EXR_API const exr_resource *exr_document_resources(const exr_document *doc, size_t *count);
/* Borrowed views last until document_free. Attribute names use URI|local for namespaces. */
EXR_API const char *exr_node_attribute(const exr_node *node, const char *name);

/* Embedded media recognised in a loaded EPUB part. The engine never decodes or
   plays media; it identifies each <audio>, <video>, <object> and <embed>, checks
   the container, and lays out a short visible placeholder (TEXT node) instead of
   leaving the element blank. Hosts that can play media use path/media_type and
   read bytes with exr_document_resource. */
typedef enum { EXR_MEDIA_AUDIO = 1, EXR_MEDIA_VIDEO, EXR_MEDIA_EMBEDDED } exr_media_kind;
typedef enum {
  EXR_MEDIA_AVAILABLE = 0, /* local, present, an audio or video type */
  EXR_MEDIA_MISSING,       /* local reference absent from the container */
  EXR_MEDIA_UNSUPPORTED,   /* plugin/legacy type (Flash, Java, ...) or non-media */
  EXR_MEDIA_REMOTE,        /* absolute URI outside the book; never fetched */
  EXR_MEDIA_NO_SOURCE      /* no src/data and no <source> child */
} exr_media_state;
enum {
  EXR_MEDIA_AUTOPLAY = 1, EXR_MEDIA_LOOP = 2, EXR_MEDIA_CONTROLS = 4, EXR_MEDIA_MUTED = 8,
  EXR_MEDIA_HIDDEN = 16,     /* hidden attribute: no placeholder is laid out */
  EXR_MEDIA_COVER = 32,      /* inside epub:type/role cover, or a cover-named part */
  EXR_MEDIA_BACKGROUND = 64, /* audio with autoplay+loop and no controls */
  EXR_MEDIA_DURATION_ESTIMATED = 128 /* constant-bitrate MP3 size estimate */
};
typedef struct {
  exr_media_kind kind;
  exr_media_state state;
  unsigned flags;
  size_t element;     /* node index of the media element */
  size_t placeholder; /* TEXT node holding label, SIZE_MAX when none */
  const char *tag;    /* local element name */
  const char *src;    /* chosen reference as written ("" when none) */
  const char *path;   /* resolved container path, NULL when remote/absent */
  const char *media_type; /* manifest type, else type attribute, else "" */
  const char *poster; /* resolved video poster path or NULL */
  long long duration_ms; /* -1 unknown; WAV, MP3, MP4/M4A/MOV headers only */
  size_t source_count;   /* candidate references considered (src + <source>) */
  const char *label;     /* the visible placeholder text */
} exr_media_item;
/* Borrowed until document_free; parts without media return NULL and 0. */
EXR_API const exr_media_item *exr_document_media(const exr_document *doc, size_t *count);
EXR_API exr_format exr_document_format(const exr_document *doc);
EXR_API exr_status exr_document_find(const exr_document *doc, const char *query, size_t from,
                                     size_t *start, size_t *end, exr_error *error);
/* Capture up to 64 KiB of selected text and 32 Unicode scalars of context per side.
   Empty ranges capture point bookmarks. Output must be empty; failure clears it. */
EXR_API exr_status exr_anchor_create(const exr_document *doc, size_t start, size_t end,
                                     exr_anchor *out, exr_error *error);
EXR_API void exr_anchor_free(exr_anchor *anchor);
/* Read-only resolution; never falls back to the nearest old offset. EXR_OK may
   report MISSING/AMBIGUOUS/LEGACY; only FOUND supplies a usable range. */
EXR_API exr_status exr_anchor_resolve(const exr_document *doc, const exr_anchor *anchor,
                                      exr_anchor_match *match, exr_error *error);
/* DOM location for a chapter-local EPUB CFI path component. TEXT offsets count
   UTF-16 code units in raw, uncollapsed node text (including surrogate interiors).
   Element offset=SIZE_MAX denotes the element; other offsets are child-node
   boundaries. side: 0 unspecified, 1 before, 2 after. No normalized text offsets. */
typedef struct { size_t node,offset; unsigned side; } exr_cfi_point;
/* Document-independent CFI grammar (W3C EPUB CFI 1.1). Accepts epubcfi(...)
   or its bare scheme data. Serialization adds the wrapper and otherwise
   preserves every assertion, escape and parameter in its original order.
   No URI/percent decoding. diagnostics.byte is an input UTF-8 byte index.
   Syntax failures return EXR_FORMAT plus the specific diagnostic code;
   encoding/size failures return EXR_ENCODING/EXR_LIMIT. Owned outputs use
   exr_free; parsed values use exr_cfi_free. Failure clears owned outputs. */
typedef struct exr_cfi exr_cfi;
typedef enum {
  EXR_CFI_VALID=0, EXR_CFI_SYNTAX, EXR_CFI_NUMBER, EXR_CFI_ESCAPE,
  EXR_CFI_ASSERTION, EXR_CFI_RANGE, EXR_CFI_ENCODING, EXR_CFI_LIMIT
} exr_cfi_error_code;
typedef struct { exr_cfi_error_code code; size_t byte; } exr_cfi_diagnostic;
EXR_API exr_status exr_cfi_parse(const char *text,exr_cfi **out,
  exr_cfi_diagnostic *diagnostic,exr_error *error);
EXR_API exr_status exr_cfi_serialize(const exr_cfi *cfi,char **out,exr_error *error);
EXR_API int exr_cfi_is_range(const exr_cfi *cfi);
/* Expand P,S,E into full wrapped PS and PE. A point produces two equal paths. */
EXR_API exr_status exr_cfi_endpoints(const exr_cfi *cfi,char **start,char **end,exr_error *error);
EXR_API void exr_cfi_free(exr_cfi *cfi);
/* Exact mapping between normalized UTF-8 byte boundaries and raw XML UTF-16
   text points, using the retained DOM projection. Synthetic paragraph breaks
   map to the text boundaries on their respective sides. Collapsed whitespace
   and element points import at the corresponding normalized boundary.
   Hidden/unprojected nodes and surrogate/UTF-8 interiors are rejected. */
EXR_API exr_status exr_document_cfi_point_at(const exr_document *doc,size_t chapter,size_t offset,
  const exr_control *control,exr_cfi_point *out,exr_error *error);
EXR_API exr_status exr_document_cfi_point_offset(const exr_document *doc,size_t chapter,const exr_cfi_point *point,
  const exr_control *control,size_t *offset,exr_error *error);
/* These APIs produce/consume the content-document component, e.g. /4/2[id]/1:3,
   not the package spine prefix or epubcfi(...) wrapper. chapter must have one
   XML document element. Owned path uses exr_free; failure clears output. */
EXR_API exr_status exr_document_cfi_path_create(const exr_document *doc,size_t chapter,const exr_cfi_point *point,
                                                const exr_control *control,char **path,exr_error *error);
EXR_API exr_status exr_document_cfi_path_resolve(const exr_document *doc,size_t chapter,const char *path,
                                                 const exr_control *control,exr_cfi_point *point,exr_error *error);
/* Full point CFI through the original package spine. Requires a complete EPUB
   document retaining its archive; auxiliary non-spine chapters are rejected.
   Raw epubcfi(...) strings only; no URI percent decoding. Range input resolves
   to its start; use range_resolve to validate/obtain both ends. Failure clears output. */
EXR_API exr_status exr_document_cfi_create(const exr_document *doc,size_t chapter,const exr_cfi_point *point,
                                           const exr_control *control,char **cfi,exr_error *error);
EXR_API exr_status exr_document_cfi_resolve(const exr_document *doc,const char *cfi,const exr_control *control,
                                            size_t *chapter,exr_cfi_point *point,exr_error *error);
/* Context-bearing text CFIs capture 1..32 Unicode scalars per side from raw
   XML text with collapsed XML whitespace. Text assertions can correct stale
   offsets when their context is unique. Scalar-interior offsets are rejected. */
EXR_API exr_status exr_document_cfi_path_create_quoted(const exr_document *doc,size_t chapter,const exr_cfi_point *point,
                                                       size_t context_scalars,const exr_control *control,char **path,exr_error *error);
EXR_API exr_status exr_document_cfi_create_quoted(const exr_document *doc,size_t chapter,const exr_cfi_point *point,
                                                  size_t context_scalars,const exr_control *control,char **cfi,exr_error *error);
/* EPUB CFI simple range across one or more spine chapters. Endpoint side bias
   must be unspecified; the standard implies after-start/before-end attachment. */
typedef struct { size_t start_chapter,end_chapter; exr_cfi_point start,end; } exr_cfi_range;
EXR_API exr_status exr_document_cfi_range_create(const exr_document *doc,const exr_cfi_range *range,
                                                 const exr_control *control,char **cfi,exr_error *error);
EXR_API exr_status exr_document_cfi_range_resolve(const exr_document *doc,const char *cfi,const exr_control *control,
                                                  exr_cfi_range *range,exr_error *error);
EXR_API exr_status exr_anchor_resolve_ex(const exr_document *doc,const exr_anchor *anchor,const exr_control *control,
                                         exr_anchor_match *match,exr_error *error);
/* Compact W3C Web Annotation JSON profile: one plain-text body and one
   TextQuoteSelector. source identifies the exact target resource (host mapping).
   JSON does not carry SDK byte offsets or chapter paths; imported anchor ranges
   are SIZE_MAX and must be resolved in the host-selected document/part. */
typedef struct { char *id,*source,*text; exr_anchor anchor; } exr_text_annotation;
EXR_API exr_status exr_text_annotation_export(const exr_text_annotation *annotation,char **json,size_t *size,exr_error *error);
EXR_API exr_status exr_text_annotation_import(const void *json,size_t size,exr_text_annotation *annotation,exr_error *error);
EXR_API void exr_text_annotation_free(exr_text_annotation *annotation);
#ifdef __cplusplus
}
#endif
#endif
