/* SPDX-License-Identifier: GPL-3.0-only */
#ifndef EXR_PDF_INTERNAL_H
#define EXR_PDF_INTERNAL_H
#include "internal.h"
#define EXR_PDF_NONE UINT32_MAX
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
#endif
