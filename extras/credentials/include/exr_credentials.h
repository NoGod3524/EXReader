/* SPDX-License-Identifier: MIT */
#ifndef EXR_CREDENTIALS_H
#define EXR_CREDENTIALS_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define EXR_CREDENTIALS_VERSION "0.1.0"
/* Secrets are opaque bytes (username/password, token, ...): 1..2048 bytes.
   The ceiling fits every backend, including the 2560-byte Windows blob. */
#define EXR_CREDENTIALS_SECRET_MAX 2048u
/* Namespace: 1..64 bytes of [a-z0-9.-], starting with [a-z0-9]. One namespace
   per application/service, e.g. "org.exreader.reader.webdav". */
#define EXR_CREDENTIALS_NAMESPACE_MAX 64u
/* Account ID: the caller's stable lowercase canonical UUID, exactly
   xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx with [0-9a-f]. The module never
   derives it from a URL or user name. */
#define EXR_CREDENTIALS_ACCOUNT_ID_LENGTH 36u
typedef enum {
  EXR_CRED_OK = 0,
  EXR_CRED_NOT_FOUND = 1,   /* No record for this namespace/account. */
  EXR_CRED_UNAVAILABLE = 2, /* Secure storage absent, locked or refused. Nothing
                               was written in plain text; the host may keep the
                               secret for the current session only. */
  EXR_CRED_ARGUMENT = 3,    /* Invalid namespace, account, length, pointer or a
                               too-small output buffer. Storage untouched. */
  EXR_CRED_IO = 4           /* Platform storage failed or a record is corrupt. */
} exr_credentials_status;
typedef struct exr_credentials_store exr_credentials_store;
/* Static, secret-free name such as "UNAVAILABLE". Never NULL. Statuses carry
   no messages, so no failure path can echo secret bytes. */
const char *exr_credentials_status_name(exr_credentials_status);
/* Validates the namespace and allocates a handle; contacts no service. Every
   record is scoped to (namespace, account). The module never enumerates
   records and keeps no process-wide credential. One handle may be shared by
   threads; operations on the same account are last-writer-wins. */
exr_credentials_status exr_credentials_open(const char *service_namespace,
  exr_credentials_store **out_store);
void exr_credentials_close(exr_credentials_store *);
/* Creates or exactly replaces the record. secret is borrowed for the call. */
exr_credentials_status exr_credentials_put(exr_credentials_store *, const char *account_id,
  const uint8_t *secret, size_t secret_length);
/* Copies the record into the caller-owned buffer; the module never allocates
   output for the caller. *out_length is always written: the stored length on
   OK or when capacity is too small (ARGUMENT, buffer untouched), otherwise 0.
   A buffer of EXR_CREDENTIALS_SECRET_MAX bytes always suffices. The caller
   should clear the buffer with exr_credentials_wipe when done. */
exr_credentials_status exr_credentials_get(exr_credentials_store *, const char *account_id,
  uint8_t *buffer, size_t capacity, size_t *out_length);
/* Removes the record; NOT_FOUND when it is already absent. */
exr_credentials_status exr_credentials_delete(exr_credentials_store *, const char *account_id);
/* Zeroes memory in a way the compiler may not elide. */
void exr_credentials_wipe(void *buffer, size_t length);
#ifdef __cplusplus
}
#endif
#endif
