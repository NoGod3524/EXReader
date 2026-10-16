/* SPDX-License-Identifier: GPL-3.0-only */
#ifndef EXREADER_H
#define EXREADER_H
#include <stddef.h>
#include <stdint.h>
#if defined(_WIN32)
#if defined(EXR_BUILD)
#define EXR_API __declspec(dllexport)
#else
#define EXR_API __declspec(dllimport)
#endif
#else
#define EXR_API __attribute__((visibility("default")))
#endif
#ifdef __cplusplus
extern "C" {
#endif
#define EXR_VERSION "0.8.0"
typedef enum {
  EXR_OK = 0,
  EXR_ARGUMENT,
  EXR_MEMORY,
  EXR_IO,
  EXR_ENCODING,
  EXR_FORMAT,
  EXR_LIMIT,
  EXR_DATABASE,
  EXR_FONT
} exr_status;
typedef enum {
  EXR_CUSTOM = 0, /* Constructed through exr_document_create(), without a file decoder. */
  EXR_TXT = 1,
  EXR_HTML,
  EXR_FB2,
  EXR_EPUB,
  EXR_DOCX,
  EXR_RTF,
  EXR_MOBI,
  EXR_PDF
} exr_format;
typedef struct {
  exr_status code;
  char message[256];
} exr_error;
typedef struct exr_document exr_document;
typedef struct exr_font exr_font;
typedef struct exr_layout exr_layout;
typedef struct exr_library exr_library;
typedef struct exr_publication exr_publication;
typedef struct exr_session exr_session;
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
typedef void (*exr_context_release_fn)(void *context);
typedef struct {
  const char *title;
  const exr_part *parts;
  size_t part_count;
  exr_part_load_fn load;
  void *context;
  exr_context_release_fn release;
} exr_publication_input;
typedef struct {
  size_t start, end;
  uint32_t codepoint, glyph;
  float x, baseline, advance, size;
  size_t page;
  size_t node;
  uint32_t color; /* 0xRRGGBBAA */
  unsigned flags; /* 1: synthetic bold, 2: synthetic italic */
  float clip_left, clip_right;
  float line_height;
} exr_glyph;
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
typedef struct {
  exr_box_kind kind;
  size_t node, page, resource, start, end;
  float x, y, width, height, border_width;
  uint32_t background, border_color; /* 0xRRGGBBAA */
  unsigned flags;                    /* Image bit 1: missing/unsupported image placeholder. */
} exr_box;
typedef struct {
  float width, height, margin, font_size, line_height, paragraph_spacing;
} exr_layout_options;
typedef struct exr_bitmap exr_bitmap;
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
} exr_layout_config;
struct exr_bitmap {
  uint32_t width, height, stride;
  unsigned char *pixels;
  uint32_t channels; /* 1 (gray) or 4 (RGBA); zero accepted as gray on write. */
};
/* All input/output strings are UTF-8. Returned views belong to their owner. */
EXR_API const char *exr_version(void);
/* Copies every input string/attribute/blob during this call. Failure leaves *out NULL. */
EXR_API exr_status exr_document_create(const exr_document_input *input, exr_document **out,
                                       exr_error *error);
EXR_API exr_status exr_document_open(const char *path, exr_document **out, exr_error *error);
EXR_API exr_status exr_document_open_memory(exr_format format, const void *data, size_t size,
                                            exr_document **out, exr_error *error);
EXR_API void exr_document_free(exr_document *doc);
EXR_API const char *exr_document_text(const exr_document *doc, size_t *size);
EXR_API const char *exr_document_title(const exr_document *doc);
EXR_API const exr_block *exr_document_blocks(const exr_document *doc, size_t *count);
EXR_API const exr_node *exr_document_nodes(const exr_document *doc, size_t *count);
EXR_API const exr_chapter *exr_document_chapters(const exr_document *doc, size_t *count);
EXR_API const exr_resource *exr_document_resources(const exr_document *doc, size_t *count);
/* Borrowed views last until document_free. Attribute names use URI|local for namespaces. */
EXR_API const char *exr_node_attribute(const exr_node *node, const char *name);
/* Copies an embedded resource; free the returned bytes with exr_free(). No network access. */
EXR_API exr_status exr_document_resource(const exr_document *doc, size_t resource, void **data,
                                         size_t *size, exr_error *error);
/* Resolve a local chapter-relative URI to a resource and, if parsed, a node.
   Missing targets return EXR_OK with SIZE_MAX; external/unsafe URIs return EXR_ARGUMENT. */
EXR_API exr_status exr_document_resolve(const exr_document *doc, size_t chapter, const char *uri,
                                        size_t *resource, size_t *node, exr_error *error);
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
EXR_API exr_status exr_document_export(const exr_document *doc, exr_format format, void **data,
                                       size_t *size, exr_error *error);
/* Metadata is copied. On success, release (if provided) runs once after the last
   publication/session reference is freed. Without release, keep context alive.
   Callbacks must not destroy/reenter the active publication or session. */
EXR_API exr_status exr_publication_create(const exr_publication_input *input,
                                          exr_publication **out, exr_error *error);
/* Built-in indexed loading currently accepts EPUB. No XHTML is parsed at open. */
EXR_API exr_status exr_publication_open(const char *path, exr_publication **out,
                                        exr_error *error);
EXR_API exr_status exr_publication_open_memory(exr_format format, const void *data, size_t size,
                                               exr_publication **out, exr_error *error);
EXR_API void exr_publication_free(exr_publication *publication);
EXR_API const char *exr_publication_title(const exr_publication *publication);
EXR_API const exr_part *exr_publication_parts(const exr_publication *publication, size_t *count);
/* Own the returned document with document_free(); offsets/indices are part-local. */
EXR_API exr_status exr_publication_load(exr_publication *publication, size_t part,
                                        exr_document **out, exr_error *error);
EXR_API exr_status exr_font_open(const char *path, exr_font **out, exr_error *error);
EXR_API void exr_font_free(exr_font *font);
EXR_API exr_layout_options exr_layout_defaults(void);
EXR_API exr_layout_config exr_layout_config_defaults(void);
EXR_API exr_status exr_layout_create(const exr_document *doc, exr_font *font,
                                     const exr_layout_options *options, exr_layout **out,
                                     exr_error *error);
EXR_API exr_status exr_layout_create_ex(const exr_document *doc, exr_font *font,
                                        const exr_layout_config *config, exr_layout **out,
                                        exr_error *error);
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
EXR_API void exr_session_clear(exr_session *session);
EXR_API void exr_session_free(exr_session *session);
EXR_API void exr_layout_free(exr_layout *layout);
EXR_API const exr_page *exr_layout_pages(const exr_layout *layout, size_t *count);
EXR_API const exr_line *exr_layout_lines(const exr_layout *layout, size_t *count);
EXR_API const exr_glyph *exr_layout_glyphs(const exr_layout *layout, size_t *count);
EXR_API const exr_box *exr_layout_boxes(const exr_layout *layout, size_t *count);
/* Borrowed decoded RGBA pixels, valid until layout_free; NULL for unavailable resources. */
EXR_API const exr_bitmap *exr_layout_image(const exr_layout *layout, size_t resource);
EXR_API size_t exr_layout_page_at(const exr_layout *layout, size_t utf8_offset);
EXR_API size_t exr_layout_hit_test(const exr_layout *layout, size_t page, float x, float y);
EXR_API exr_status exr_render_page(const exr_layout *layout, exr_font *font, size_t page,
                                   exr_bitmap *bitmap, exr_error *error);
EXR_API exr_status exr_render_page_color(const exr_layout *layout, exr_font *font, size_t page,
                                         exr_bitmap *bitmap, exr_error *error);
/* Built-in PNG/JPEG decoder; owns its output pixels, freed with exr_bitmap_free(). */
EXR_API exr_status exr_image_decode(const void *data, size_t size, exr_bitmap *rgba,
                                    exr_error *error);
EXR_API exr_status exr_bitmap_write_png(const exr_bitmap *bitmap, const char *path,
                                        exr_error *error);
EXR_API void exr_bitmap_free(exr_bitmap *bitmap);
EXR_API exr_status exr_bitmap_write_bmp(const exr_bitmap *bitmap, const char *path,
                                        exr_error *error);
/* SQLite owns the original bytes and covers; there is no filesystem sidecar. */
typedef struct {
  int64_t id;
  exr_format format;
  char *title, *author, *tags;
  int favorite, status;
  size_t position;
} exr_book;
typedef struct {
  int64_t id, book_id;
  size_t start, end;
  char *text;
  exr_anchor anchor; /* Owned in query results; zero-initialize input notes. */
} exr_note;
EXR_API exr_status exr_library_open(const char *path, exr_library **out, exr_error *error);
EXR_API void exr_library_close(exr_library *library);
EXR_API exr_status exr_library_import(exr_library *library, exr_format format, const void *data,
                                      size_t size, const char *title, int64_t *id,
                                      exr_error *error);
EXR_API exr_status exr_library_books(exr_library *library, const char *query, exr_book **books,
                                     size_t *count, exr_error *error);
EXR_API void exr_books_free(exr_book *books, size_t count);
EXR_API exr_status exr_library_update(exr_library *library, const exr_book *book, exr_error *error);
EXR_API exr_status exr_library_document(exr_library *library, int64_t id, exr_document **doc,
                                        exr_error *error);
EXR_API exr_status exr_library_cover(exr_library *library, int64_t id, const void *data,
                                     size_t size, exr_error *error);
/* New/reranged notes capture a selector from the stored book. Updating only text
   preserves the old selector (including legacy). A non-NULL anchor.exact explicitly
   supplies a replacement selector, whose start/end must equal the note range. */
EXR_API exr_status exr_library_note(exr_library *library, const exr_note *note, int64_t *id,
                                    exr_error *error);
EXR_API exr_status exr_library_notes(exr_library *library, int64_t book_id, exr_note **notes,
                                     size_t *count, exr_error *error);
EXR_API void exr_notes_free(exr_note *notes, size_t count);
EXR_API void exr_free(void *memory);
EXR_API exr_status exr_library_blob(exr_library *library, int64_t id, int cover, void **data,
                                    size_t *size, exr_error *error);
EXR_API exr_status exr_library_remove_note(exr_library *library, int64_t id, exr_error *error);
EXR_API exr_status exr_library_backup(exr_library *library, const char *path, exr_error *error);
EXR_API exr_status exr_library_delete(exr_library *library, int64_t id, exr_error *error);
#ifdef __cplusplus
}
#endif
#endif
