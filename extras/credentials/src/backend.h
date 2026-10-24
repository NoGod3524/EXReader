/* SPDX-License-Identifier: MIT */
#ifndef EXR_CREDENTIALS_BACKEND_H
#define EXR_CREDENTIALS_BACKEND_H
#include "exr_credentials.h"
/* Arguments are already validated: namespace and account are well-formed
   NUL-terminated ASCII, secret_length is 1..EXR_CREDENTIALS_SECRET_MAX and
   buffer/out_length are non-NULL. get must copy only when the stored record
   fits, returning ARGUMENT with *out_length set otherwise, and IO for a stored
   record longer than EXR_CREDENTIALS_SECRET_MAX. Backends wipe their copies. */
exr_credentials_status exr_cred_backend_put(const char *service_namespace, const char *account_id,
  const uint8_t *secret, size_t secret_length);
exr_credentials_status exr_cred_backend_get(const char *service_namespace, const char *account_id,
  uint8_t *buffer, size_t capacity, size_t *out_length);
exr_credentials_status exr_cred_backend_delete(const char *service_namespace, const char *account_id);
/* Shared by backends that receive the record from platform memory. */
exr_credentials_status exr_cred_copy_out(const void *record, size_t record_length,
  uint8_t *buffer, size_t capacity, size_t *out_length);
#endif
