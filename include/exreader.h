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
#define EXR_VERSION "0.3.0"
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
typedef struct {
  size_t start, end;
  unsigned heading;
} exr_block;
typedef struct {
  size_t start, end;
  uint32_t codepoint, glyph;
  float x, baseline, advance, size;
  size_t page;
} exr_glyph;
typedef struct {
  size_t start, end, glyph_start, glyph_count;
  float y;
  size_t page;
} exr_line;
typedef struct {
  size_t start, end, line_start, line_count;
} exr_page;
typedef struct {
  float width, height, margin, font_size, line_height, paragraph_spacing;
} exr_layout_options;
typedef struct {
  uint32_t width, height, stride;
  unsigned char *pixels;
} exr_bitmap;
/* All input/output strings are UTF-8. Returned views belong to their owner. */
EXR_API const char *exr_version(void);
EXR_API exr_status exr_document_open(const char *path, exr_document **out, exr_error *error);
EXR_API exr_status exr_document_open_memory(exr_format format, const void *data, size_t size,
                                            exr_document **out, exr_error *error);
EXR_API void exr_document_free(exr_document *doc);
EXR_API const char *exr_document_text(const exr_document *doc, size_t *size);
EXR_API const char *exr_document_title(const exr_document *doc);
EXR_API const exr_block *exr_document_blocks(const exr_document *doc, size_t *count);
EXR_API exr_format exr_document_format(const exr_document *doc);
EXR_API exr_status exr_document_find(const exr_document *doc, const char *query, size_t from,
                                     size_t *start, size_t *end, exr_error *error);
EXR_API exr_status exr_document_export(const exr_document *doc, exr_format format, void **data,
                                       size_t *size, exr_error *error);
EXR_API exr_status exr_font_open(const char *path, exr_font **out, exr_error *error);
EXR_API void exr_font_free(exr_font *font);
EXR_API exr_layout_options exr_layout_defaults(void);
EXR_API exr_status exr_layout_create(const exr_document *doc, exr_font *font,
                                     const exr_layout_options *options, exr_layout **out,
                                     exr_error *error);
EXR_API void exr_layout_free(exr_layout *layout);
EXR_API const exr_page *exr_layout_pages(const exr_layout *layout, size_t *count);
EXR_API const exr_line *exr_layout_lines(const exr_layout *layout, size_t *count);
EXR_API const exr_glyph *exr_layout_glyphs(const exr_layout *layout, size_t *count);
EXR_API size_t exr_layout_page_at(const exr_layout *layout, size_t utf8_offset);
EXR_API size_t exr_layout_hit_test(const exr_layout *layout, size_t page, float x, float y);
EXR_API exr_status exr_render_page(const exr_layout *layout, exr_font *font, size_t page,
                                   exr_bitmap *bitmap, exr_error *error);
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
