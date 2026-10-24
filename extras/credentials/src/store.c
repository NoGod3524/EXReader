/* SPDX-License-Identifier: MIT */
#include "backend.h"
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#endif

struct exr_credentials_store { char service_namespace[EXR_CREDENTIALS_NAMESPACE_MAX + 1]; };

const char *exr_credentials_status_name(exr_credentials_status status) {
  switch (status) {
    case EXR_CRED_OK: return "OK";
    case EXR_CRED_NOT_FOUND: return "NOT_FOUND";
    case EXR_CRED_UNAVAILABLE: return "UNAVAILABLE";
    case EXR_CRED_ARGUMENT: return "ARGUMENT";
    case EXR_CRED_IO: return "IO";
  }
  return "UNKNOWN";
}

static int lower_alnum(char c) { return (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9'); }

static int valid_namespace(const char *value) {
  size_t n = 0;
  if (!value || !lower_alnum(value[0])) return 0;
  for (; value[n]; ++n) {
    if (n >= EXR_CREDENTIALS_NAMESPACE_MAX) return 0;
    if (!lower_alnum(value[n]) && value[n] != '.' && value[n] != '-') return 0;
  }
  return 1;
}

static int valid_account(const char *value) {
  size_t n;
  if (!value) return 0;
  for (n = 0; n < EXR_CREDENTIALS_ACCOUNT_ID_LENGTH; ++n) {
    char c = value[n];
    if (n == 8 || n == 13 || n == 18 || n == 23) {
      if (c != '-') return 0;
    } else if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) {
      return 0;
    }
  }
  return value[n] == '\0';
}

void exr_credentials_wipe(void *buffer, size_t length) {
  if (!buffer || !length) return;
#ifdef _WIN32
  SecureZeroMemory(buffer, length);
#else
  {
    volatile unsigned char *p = (volatile unsigned char *)buffer;
    while (length--) *p++ = 0;
  }
#endif
}

exr_credentials_status exr_cred_copy_out(const void *record, size_t record_length,
                                         uint8_t *buffer, size_t capacity, size_t *out_length) {
  if (record_length == 0 || record_length > EXR_CREDENTIALS_SECRET_MAX) return EXR_CRED_IO;
  *out_length = record_length;
  if (record_length > capacity) return EXR_CRED_ARGUMENT;
  memcpy(buffer, record, record_length);
  return EXR_CRED_OK;
}

exr_credentials_status exr_credentials_open(const char *service_namespace,
                                            exr_credentials_store **out_store) {
  exr_credentials_store *store;
  if (!out_store) return EXR_CRED_ARGUMENT;
  *out_store = NULL;
  if (!valid_namespace(service_namespace)) return EXR_CRED_ARGUMENT;
  store = (exr_credentials_store *)calloc(1, sizeof *store);
  if (!store) return EXR_CRED_IO;
  memcpy(store->service_namespace, service_namespace, strlen(service_namespace) + 1);
  *out_store = store;
  return EXR_CRED_OK;
}

void exr_credentials_close(exr_credentials_store *store) { free(store); }

exr_credentials_status exr_credentials_put(exr_credentials_store *store, const char *account_id,
                                           const uint8_t *secret, size_t secret_length) {
  if (!store || !valid_account(account_id) || !secret || secret_length == 0 ||
      secret_length > EXR_CREDENTIALS_SECRET_MAX)
    return EXR_CRED_ARGUMENT;
  return exr_cred_backend_put(store->service_namespace, account_id, secret, secret_length);
}

exr_credentials_status exr_credentials_get(exr_credentials_store *store, const char *account_id,
                                           uint8_t *buffer, size_t capacity, size_t *out_length) {
  exr_credentials_status status;
  if (!out_length) return EXR_CRED_ARGUMENT;
  *out_length = 0;
  if (!store || !valid_account(account_id) || !buffer) return EXR_CRED_ARGUMENT;
  status = exr_cred_backend_get(store->service_namespace, account_id, buffer, capacity, out_length);
  if (status != EXR_CRED_OK && status != EXR_CRED_ARGUMENT) *out_length = 0;
  return status;
}

exr_credentials_status exr_credentials_delete(exr_credentials_store *store, const char *account_id) {
  if (!store || !valid_account(account_id)) return EXR_CRED_ARGUMENT;
  return exr_cred_backend_delete(store->service_namespace, account_id);
}
