/* SPDX-License-Identifier: MIT */
/* Windows Credential Manager: one CRED_TYPE_GENERIC record per account. */
#include "backend.h"
#include <windows.h>
#include <wincred.h>
#include <string.h>

/* "EXReaderCredentials/<namespace>/<account>" fits CRED_MAX_GENERIC_TARGET_NAME_LENGTH. */
#define TARGET_PREFIX L"EXReaderCredentials/"
#define TARGET_CAPACITY 160

static void target_name(const char *ns, const char *account, wchar_t *out) {
  size_t n = wcslen(TARGET_PREFIX);
  memcpy(out, TARGET_PREFIX, n * sizeof(wchar_t));
  while (*ns) out[n++] = (wchar_t)*ns++; /* validated ASCII */
  out[n++] = L'/';
  while (*account) out[n++] = (wchar_t)*account++;
  out[n] = 0;
}

static exr_credentials_status map_error(DWORD error) {
  switch (error) {
    case ERROR_NOT_FOUND: return EXR_CRED_NOT_FOUND;
    /* No credential-capable logon session (service, S4U task, ...), or
       Credential Manager disabled by policy. */
    case ERROR_NO_SUCH_LOGON_SESSION:
    case ERROR_ACCESS_DENIED:
    case ERROR_NOT_SUPPORTED:
    case ERROR_SERVICE_NOT_ACTIVE:
    case ERROR_SERVICE_DISABLED:
      return EXR_CRED_UNAVAILABLE;
    default: return EXR_CRED_IO;
  }
}

exr_credentials_status exr_cred_backend_put(const char *ns, const char *account,
                                            const uint8_t *secret, size_t secret_length) {
  wchar_t target[TARGET_CAPACITY], user[EXR_CREDENTIALS_ACCOUNT_ID_LENGTH + 1];
  CREDENTIALW credential;
  size_t i;
  target_name(ns, account, target);
  for (i = 0; i <= EXR_CREDENTIALS_ACCOUNT_ID_LENGTH; ++i) user[i] = (wchar_t)account[i];
  memset(&credential, 0, sizeof credential);
  credential.Type = CRED_TYPE_GENERIC;
  credential.TargetName = target;
  credential.UserName = user;
  credential.CredentialBlobSize = (DWORD)secret_length;
  credential.CredentialBlob = (LPBYTE)secret;
  credential.Persist = CRED_PERSIST_LOCAL_MACHINE;
  /* CredWriteW replaces an existing record with the same target and type. */
  return CredWriteW(&credential, 0) ? EXR_CRED_OK : map_error(GetLastError());
}

exr_credentials_status exr_cred_backend_get(const char *ns, const char *account,
                                            uint8_t *buffer, size_t capacity, size_t *out_length) {
  wchar_t target[TARGET_CAPACITY];
  PCREDENTIALW credential = NULL;
  exr_credentials_status status;
  target_name(ns, account, target);
  if (!CredReadW(target, CRED_TYPE_GENERIC, 0, &credential)) return map_error(GetLastError());
  status = exr_cred_copy_out(credential->CredentialBlob, credential->CredentialBlobSize,
                             buffer, capacity, out_length);
  if (credential->CredentialBlob) SecureZeroMemory(credential->CredentialBlob, credential->CredentialBlobSize);
  CredFree(credential);
  return status;
}

exr_credentials_status exr_cred_backend_delete(const char *ns, const char *account) {
  wchar_t target[TARGET_CAPACITY];
  target_name(ns, account, target);
  return CredDeleteW(target, CRED_TYPE_GENERIC, 0) ? EXR_CRED_OK : map_error(GetLastError());
}
