/* SPDX-License-Identifier: MIT */
#ifndef EXR_FORMATS_INTERNAL_H
#define EXR_FORMATS_INTERNAL_H
#include "document_internal.h"
#include "exr/formats.h"
typedef struct {
  void *context;
  void *(*allocate)(void *context,size_t size);
  void *(*reallocate)(void *context,void *data,size_t size);
  void (*release)(void *context,void *data);
} exr_resource_allocator;
/* The supplied allocator rejects every archive/output allocation before it
   exceeds its caller's budget; member metadata is checked before extraction. */
exr_status exr_document_resource_bounded(const exr_document *doc,size_t resource,
  const exr_resource_allocator *allocator,const exr_control *control,void **out,size_t *size,exr_error *error);
typedef exr_status (*exr_chapter_feed_fn)(void *context,const void *data,size_t size,int final,exr_error *error);
exr_status exr_epub_chapter_feed(const exr_document *index,size_t part,
  exr_chapter_feed_fn feed,void *context,const exr_control *control,exr_error *error);
/* Every central-directory, source-read and inflate allocation uses allocator.
   The caller can charge a shared live budget in these callbacks. */
exr_status exr_epub_chapter_feed_bounded(const exr_document *index,size_t part,
  exr_chapter_feed_fn feed,void *context,const exr_resource_allocator *allocator,
  const exr_control *control,exr_error *error);
exr_status exr_parse(exr_document *doc, const void *data, size_t size, exr_error *error);
exr_status exr_epub_index(const void *data, size_t size, exr_document **out, exr_error *error);
exr_status exr_epub_index_source(const exr_source *source, exr_document **out, exr_error *error);
exr_status exr_epub_index_ex(const void *data, size_t size, const char *passphrase, exr_document **out, exr_error *error);
exr_status exr_epub_index_source_ex(const exr_source *source, const char *passphrase, exr_document **out, exr_error *error);
exr_status exr_file_source_limit(const char *path,uint64_t maximum,exr_source *source,exr_error *error);
exr_status exr_file_source(const char *path, exr_source *source, exr_error *error);
exr_status exr_xml_resource(const exr_document *doc, size_t resource, const char *root_name,
                             exr_document **out, exr_error *error);
exr_status exr_epub_navigation(const exr_document *index, size_t metadata_bytes,
                                exr_navigation **entries, size_t *count, exr_error *error);
exr_status exr_epub_navigation_details(const exr_document *index,size_t metadata_bytes,
  exr_navigation **entries,size_t *count,size_t **orders,exr_toc_source *source,exr_error *error);
exr_status exr_epub_package_tree(const exr_document *doc,const exr_control *control,exr_document **out,exr_error *error);
exr_status exr_epub_export_check(const exr_document *doc, exr_error *error);
exr_status exr_epub_load(const exr_document *index, size_t part, exr_document **out,
                        exr_error *error);
exr_status exr_xml_serialize(const exr_document *doc, size_t root,
                               exr_buffer *out, exr_error *error);
typedef exr_status (*exr_member_read_fn)(void *context, const char *path, int optional,
                                          void **data, size_t *size, exr_error *error);
exr_status exr_docx(exr_document *doc, exr_member_read_fn read, void *context, exr_error *error);
typedef struct { const unsigned char *data; size_t size; } exr_mobi_record;
exr_status exr_mobi_palmdoc(const exr_mobi_record *record,exr_buffer *out,exr_error *error);
typedef struct {
  exr_document *index;
  exr_navigation *navigation;
  size_t navigation_count, memory;
  void *context;
  exr_status (*load)(void *,size_t,exr_document **,exr_error *);
  void (*release)(void *);
} exr_format_book;
exr_status exr_book_open(exr_format format,const void *data,size_t size,exr_format_book **out,exr_error *error);
void exr_book_free(void *book);
exr_status exr_book_load(void *book,size_t part,exr_document **out,exr_error *error);
exr_status exr_book_slice(void *document,size_t part,exr_document **out,exr_error *error);
exr_status exr_book_resource(exr_document *doc,const char *path,const char *type,const void *data,size_t size,size_t *index,exr_error *error);
exr_status exr_book_chapter(exr_document *doc,size_t *body,exr_error *error);
exr_status exr_mobi_navigation(exr_document *doc,const exr_mobi_record *records,size_t count,const size_t *positions,const size_t *nodes,size_t marks,exr_error *error);
exr_status exr_mobi_html(exr_document *doc,const exr_mobi_record *records,size_t count,const char *text,size_t size,unsigned encoding,exr_error *error);
exr_status exr_mobi_book(const void *data,size_t size,exr_format_book *book,exr_error *error);
typedef exr_status (*exr_mobi_read_fn)(void *,size_t,size_t,exr_buffer *,exr_error *);
exr_status exr_kf8_book(const exr_mobi_record *records,size_t count,const exr_mobi_record *shared,size_t shared_count,
  exr_mobi_read_fn read,void *context,void (*release)(void *),exr_format_book *book,exr_error *error);
exr_status exr_kf8(exr_document *doc, const exr_mobi_record *records, size_t count,
                    const exr_mobi_record *shared, size_t shared_count,
                    const char *text, size_t size, exr_error *error);
exr_status exr_mobi_cover(exr_document *doc, const exr_mobi_record *records, size_t count,
                           const exr_mobi_record *shared, size_t shared_count,
                           uint32_t cover, exr_error *error);
typedef struct exr_mobi_huff exr_mobi_huff;
exr_status exr_mobi_huff_open(const exr_mobi_record *records, size_t count,
                               exr_mobi_huff **out, exr_error *error);
/* Records are independent; the output may be appended, reused or discarded. */
exr_status exr_mobi_huff_decode(exr_mobi_huff *huff, const void *data, size_t size,
                                 exr_buffer *out, exr_error *error);
/* Scan codes and memoize phrase lengths without allocating expanded text. */
exr_status exr_mobi_huff_size(exr_mobi_huff *huff,const void *data,size_t size,size_t *out,exr_error *error);
void exr_mobi_huff_free(exr_mobi_huff *huff);
uint32_t exr_windows1252(unsigned char byte);
exr_status exr_rtf(exr_document *doc, const void *data, size_t size, exr_error *error);
exr_status exr_fb2(exr_document *doc, const void *data, size_t size, exr_error *error);
exr_status exr_zip_format(const void *data,size_t size,exr_format *format,exr_error *error);
static inline int exr_format_is_fixed(exr_format format) { return format==EXR_PDF || format==EXR_CBZ || format==EXR_PPTX; }
#endif
