/* SPDX-License-Identifier: GPL-3.0-only */
#ifndef EXR_PDF_INTERNAL_H
#define EXR_PDF_INTERNAL_H
#include "internal.h"
#define EXR_PDF_NONE UINT32_MAX
#define EXR_PDF_MAX_VALUES 1048576u
typedef enum {
  EXR_PDF_NULL,EXR_PDF_BOOL,EXR_PDF_INT,EXR_PDF_REAL,EXR_PDF_NAME,
  EXR_PDF_STRING,EXR_PDF_ARRAY,EXR_PDF_DICT,EXR_PDF_REF,EXR_PDF_STREAM
} exr_pdf_kind;
typedef struct {
  exr_pdf_kind kind;
  uint32_t next,first;
  union { double number; int64_t integer; struct { uint32_t offset,length; } bytes; struct { uint32_t object,generation; } ref; } u;
} exr_pdf_value;
typedef struct exr_pdf_file exr_pdf_file;
/* The input is borrowed until close. IDs remain stable; value pointers may move
   when another indirect object is resolved. No PDF API is exported yet. */
exr_status exr_pdf_open(const void *data,size_t size,exr_pdf_file **out,exr_error *error);
void exr_pdf_close(exr_pdf_file *file);
uint32_t exr_pdf_root(const exr_pdf_file *file);
const exr_pdf_value *exr_pdf_value_at(const exr_pdf_file *file,uint32_t value);
const unsigned char *exr_pdf_bytes(const exr_pdf_file *file,uint32_t value,size_t *size);
uint32_t exr_pdf_get(exr_pdf_file *file,uint32_t dict,const char *key);
exr_status exr_pdf_resolve(exr_pdf_file *file,uint32_t value,uint32_t *out,exr_error *error);
exr_status exr_pdf_stream_data(exr_pdf_file *file,uint32_t stream,const unsigned char **data,
                                 size_t *size,exr_error *error);
typedef struct {
  uint32_t object,resources,contents,annotations;
  double media[4],crop[4],user_unit;
  unsigned rotation;
} exr_pdf_page_info;
/* Caller frees the page snapshot and content buffer. Object IDs borrow file. */
exr_status exr_pdf_pages(exr_pdf_file *file,exr_pdf_page_info **pages,size_t *count,exr_error *error);
exr_status exr_pdf_content(exr_pdf_file *file,uint32_t contents,exr_buffer *out,exr_error *error);
/* Operand arena and its IDs/bytes are borrowed only for the callback. */
typedef exr_status (*exr_pdf_operator_fn)(void *context,exr_pdf_file *operands,const char *operator_name,
                                         const uint32_t *values,size_t count,exr_error *error);
exr_status exr_pdf_content_ops(const void *data,size_t size,exr_pdf_operator_fn operation,void *context,
                               const exr_control *control,exr_error *error);
exr_status exr_pdf_syntax_ops(const void *data,size_t size,exr_pdf_operator_fn operation,void *context,
                              size_t maximum_operands,const exr_control *control,exr_error *error);
typedef struct exr_pdf_cmap exr_pdf_cmap;
typedef struct { uint32_t code; unsigned code_bytes; char utf8[256]; size_t size; } exr_pdf_mapping;
exr_status exr_pdf_cmap_parse(const void *data,size_t size,const exr_control *control,exr_pdf_cmap **out,exr_error *error);
void exr_pdf_cmap_free(exr_pdf_cmap *map);
exr_status exr_pdf_cmap_next(const exr_pdf_cmap *map,const unsigned char *data,size_t size,size_t *at,
                            exr_pdf_mapping *out,exr_error *error);
#endif
