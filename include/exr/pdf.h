/* SPDX-License-Identifier: MIT */
#ifndef EXR_PDF_H
#define EXR_PDF_H
#include "document.h"
#define EXR_PDF_VERSION "3.34.2"
#ifdef __cplusplus
extern "C" {
#endif
/* Standard-security PDF permission bits from ISO 32000, /P (one-based bits).
   Query these before offering operations in an application. Owner authentication
   grants all operations. The SDK does not treat these flags as a security boundary. */
#define EXR_PDF_PERMIT_PRINT (1u<<2)
#define EXR_PDF_PERMIT_MODIFY (1u<<3)
#define EXR_PDF_PERMIT_COPY (1u<<4)
#define EXR_PDF_PERMIT_ANNOTATE (1u<<5)
#define EXR_PDF_PERMIT_FILL_FORMS (1u<<8)
#define EXR_PDF_PERMIT_ACCESSIBILITY (1u<<9)
#define EXR_PDF_PERMIT_ASSEMBLE (1u<<10)
#define EXR_PDF_PERMIT_PRINT_HIGH_QUALITY (1u<<11)
typedef struct {
  size_t struct_size;
  unsigned encrypted,revision,key_bits,owner_authenticated;
  uint32_t permissions; /* Raw /P; UINT32_MAX for an unencrypted document. */
  unsigned metadata_encrypted;
} exr_pdf_security_info;
typedef struct {
  size_t struct_size;
  exr_font *fallback_font; /* Optional ordered font set, retained until fixed_free. */
  exr_control control; /* Used only while opening. */
  const void *pdf_password; /* Borrowed for this call only; NULL tries empty password. */
  size_t pdf_password_size; /* Explicit bytes; R2-4 PDFDocEncoding, R5-6 UTF-8. */
  exr_pdf_security_info *pdf_security; /* Optional, initialize struct_size; written on success. */
} exr_fixed_open_options;
EXR_API int exr_pdf_crypto_available(void);
/* Built-in fixed-format readers (PDF and CBZ). Memory input is copied;
   file input uses UTF-8 paths. No system font lookup or eager page painting. */
EXR_API exr_status exr_fixed_open_memory(exr_format format,const void *data,size_t size,
                                          const exr_fixed_open_options *options,
                                          exr_fixed_document **out,exr_error *error);
EXR_API exr_status exr_fixed_open(const char *path,const exr_fixed_open_options *options,
                                   exr_fixed_document **out,exr_error *error);
#ifdef __cplusplus
}
#endif
#endif
