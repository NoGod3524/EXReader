/* SPDX-License-Identifier: MIT */
/* C08 privacy-failure probe. Logs a throw-away local user on with a chosen logon type, impersonates
   that logon in this thread and drives the installed credential module (real Windows Credential
   Manager) with a synthetic secret from C08_SECRET_HEX. User/password come from C08_USER and
   C08_PASS (run-time generated, never real). Output carries status names and error numbers only,
   never secret bytes. Usage: c08-probe <network|network-cleartext|batch|service|interactive> */
#include <windows.h>
#include <wincred.h>
#include <exr_credentials.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char *NS = "org.exreader.c08.privacy";
static const char *ACCOUNT = "3c08c0de-0000-4000-8000-000000000a01";
static const wchar_t *DIRECT_TARGET = L"C08Diag/org.exreader.c08.privacy/direct";

static int nibble(int c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  return -1;
}

static int decode(const char *hex, uint8_t *out, size_t capacity, size_t *length) {
  size_t n = hex ? strlen(hex) : 0, i;
  if (!n || n % 2 || n / 2 > capacity) return 0;
  for (i = 0; i < n / 2; i++) {
    int hi = nibble(hex[2 * i]), lo = nibble(hex[2 * i + 1]);
    if (hi < 0 || lo < 0) return 0;
    out[i] = (uint8_t)(hi * 16 + lo);
  }
  *length = n / 2;
  return 1;
}

static void say(const char *what, exr_credentials_status s) {
  printf("RESULT %s %s\n", what, exr_credentials_status_name(s));
  fflush(stdout);
}

static int logon_type(const char *name, DWORD *type) {
  if (!strcmp(name, "network")) *type = LOGON32_LOGON_NETWORK;
  else if (!strcmp(name, "network-cleartext")) *type = LOGON32_LOGON_NETWORK_CLEARTEXT;
  else if (!strcmp(name, "batch")) *type = LOGON32_LOGON_BATCH;
  else if (!strcmp(name, "service")) *type = LOGON32_LOGON_SERVICE;
  else if (!strcmp(name, "interactive")) *type = LOGON32_LOGON_INTERACTIVE;
  else return 0;
  return 1;
}

int main(int argc, char **argv) {
  static uint8_t secret[EXR_CREDENTIALS_SECRET_MAX], buffer[EXR_CREDENTIALS_SECRET_MAX];
  wchar_t user[128], pass[256], who[256];
  DWORD type = 0, who_len = (DWORD)(sizeof who / sizeof who[0]);
  size_t secret_length = 0, got = 0;
  HANDLE token = NULL;
  exr_credentials_store *store = NULL;
  exr_credentials_status sp, sg;
  CREDENTIALW direct;
  int ok = 0;
  if (argc != 2 || !logon_type(argv[1], &type)) {
    fprintf(stderr, "usage: c08-probe <network|network-cleartext|batch|service|interactive>\n");
    return 2;
  }
  if (!decode(getenv("C08_SECRET_HEX"), secret, sizeof secret, &secret_length)) {
    fprintf(stderr, "C08_SECRET_HEX missing or invalid\n");
    return 2;
  }
  if (!GetEnvironmentVariableW(L"C08_USER", user, 128) || !GetEnvironmentVariableW(L"C08_PASS", pass, 256)) {
    fprintf(stderr, "C08_USER/C08_PASS missing\n");
    return 2;
  }
  if (!LogonUserW(user, L".", pass, type, LOGON32_PROVIDER_DEFAULT, &token)) {
    printf("LOGON %s error %lu\nOUTCOME logon-failed\n", argv[1], GetLastError());
    return 3;
  }
  SecureZeroMemory(pass, sizeof pass);
  printf("LOGON %s ok\n", argv[1]);
  if (!ImpersonateLoggedOnUser(token)) {
    printf("IMPERSONATE error %lu\nOUTCOME impersonate-failed\n", GetLastError());
    CloseHandle(token);
    return 3;
  }
  if (GetUserNameW(who, &who_len)) printf("IDENTITY %ls\n", who);
  fflush(stdout);

  sp = exr_credentials_open(NS, &store);
  if (sp != EXR_CRED_OK || !store) {
    say("open", sp);
    RevertToSelf();
    CloseHandle(token);
    return 1;
  }
  sp = exr_credentials_put(store, ACCOUNT, secret, secret_length);
  say("put", sp);
  sg = exr_credentials_get(store, ACCOUNT, buffer, sizeof buffer, &got);
  say("get", sg);

  /* diagnostic only: the raw Win32 error behind the refusal, same persistence as the module */
  memset(&direct, 0, sizeof direct);
  direct.Type = CRED_TYPE_GENERIC;
  direct.TargetName = (LPWSTR)DIRECT_TARGET;
  direct.CredentialBlobSize = (DWORD)secret_length;
  direct.CredentialBlob = secret;
  direct.Persist = CRED_PERSIST_LOCAL_MACHINE;
  if (CredWriteW(&direct, 0)) {
    printf("DIRECT CredWriteW ok\n");
    CredDeleteW(DIRECT_TARGET, CRED_TYPE_GENERIC, 0);
  } else {
    printf("DIRECT CredWriteW error %lu\n", GetLastError());
  }

  if (sp == EXR_CRED_OK) {
    int match = sg == EXR_CRED_OK && got == secret_length && !memcmp(buffer, secret, got);
    exr_credentials_status sd = exr_credentials_delete(store, ACCOUNT);
    say("delete", sd);
    printf("OUTCOME stored match=%d cleaned=%d\n", match, sd == EXR_CRED_OK);
    ok = match && sd == EXR_CRED_OK;
  } else if (sp == EXR_CRED_UNAVAILABLE || sp == EXR_CRED_IO) {
    ok = sg != EXR_CRED_OK && got == 0;
    printf("OUTCOME refused get-also-failed=%d\n", ok);
  } else {
    printf("OUTCOME other-%s\n", exr_credentials_status_name(sp));
  }
  fflush(stdout);
  exr_credentials_wipe(buffer, sizeof buffer);
  exr_credentials_wipe(secret, sizeof secret);
  exr_credentials_close(store);
  RevertToSelf();
  CloseHandle(token);
  return ok ? 0 : 1;
}
