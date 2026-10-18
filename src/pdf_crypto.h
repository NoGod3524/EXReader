/* SPDX-License-Identifier: GPL-3.0-only */
#ifndef EXR_PDF_CRYPTO_H
#define EXR_PDF_CRYPTO_H
#include "pdf_internal.h"
typedef enum { EXR_CRYPT_IDENTITY,EXR_CRYPT_RC4,EXR_CRYPT_AES128,EXR_CRYPT_AES256 } exr_crypt_method;
typedef struct {
  unsigned char key[32];
  unsigned length,revision,version,owner,metadata;
  uint32_t permissions;
  exr_crypt_method strings,streams,embedded;
} exr_pdf_crypt;
void exr_pdf_secret_clear(void *data,size_t size);
exr_status exr_pdf_crypt_init(exr_pdf_file *file,uint32_t dict,uint32_t id,
  const void *password,size_t password_size,const exr_pdf_crypt *saved,
  const exr_control *control,exr_pdf_crypt *out,exr_error *error);
exr_status exr_pdf_crypt_filter(exr_pdf_file *file,uint32_t dict,uint32_t name,
  const exr_pdf_crypt *crypt,exr_crypt_method *method,exr_error *error);
/* In-place; AES consumes the IV and validates/removes PKCS#7 padding. */
exr_status exr_pdf_crypt_bytes(const exr_pdf_crypt *crypt,exr_crypt_method method,
  uint32_t object,unsigned generation,unsigned char *data,size_t *size,
  const exr_control *control,exr_error *error);
/* Only the immutable PDF adapter may reuse this key, against the same bytes. */
exr_status exr_pdf_open_password(const void *data,size_t size,const void *password,size_t password_size,
  const exr_pdf_crypt *saved,const exr_control *control,exr_pdf_file **out,exr_error *error);
void exr_pdf_crypt_snapshot(const exr_pdf_file *file,exr_pdf_crypt *out);
#endif
