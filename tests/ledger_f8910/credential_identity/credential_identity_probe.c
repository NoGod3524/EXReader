/* SPDX-License-Identifier: MIT */
/* F10 Windows credential identity probe against the installed
   EXReaderCredentials package (the module windows_accounts.inc uses).

   unavailable   run inside a network logon session (WinRM as the probe
                 account). Credential Manager has no credential set there,
                 so put/get/delete must report EXR_CRED_UNAVAILABLE, and the
                 raw platform error must be ERROR_NO_SUCH_LOGON_SESSION.
   isolation     run as the runner account with EXR_F10_USER and
                 EXR_F10_PASSWORD naming a second local account. A record the
                 runner stores must be NOT_FOUND to that account, and a record
                 that account stores must be NOT_FOUND to the runner.
   Every check prints one "F10CHECK {json}" line; exit 0 only if all pass. */
#include <windows.h>
#include <wincred.h>
#include <objbase.h>
#include <ntsecapi.h>
#include <sddl.h>
#include <userenv.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "exr_credentials.h"

#define NS "org.exreader.ledger.f10"
static int checks, failed;

static void check(const char *name, int pass, const char *format, ...) {
  char detail[400];
  va_list list;
  va_start(list, format);
  vsnprintf(detail, sizeof detail, format, list);
  va_end(list);
  for (char *c = detail; *c; c++) if (*c == '"' || *c == '\\' || (unsigned char)*c < 0x20) *c = '\'';
  printf("F10CHECK {\"name\":\"%s\",\"pass\":%s,\"detail\":\"%s\"}\n", name, pass ? "true" : "false", detail);
  checks++;
  if (!pass) failed++;
}

static int finish(const char *mode) {
  printf("F10RESULT {\"mode\":\"%s\",\"checks\":%d,\"failed\":%d,\"accepted\":%s}\n", mode, checks, failed,
         checks && !failed ? "true" : "false");
  return checks && !failed ? 0 : 1;
}

static ULONG effective_logon(char sid_text[200]) {
  HANDLE token = NULL;
  ULONG type = 0;
  DWORD needed = 0;
  sid_text[0] = 0;
  if (!OpenThreadToken(GetCurrentThread(), TOKEN_QUERY, TRUE, &token) &&
      !OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &token)) return 0;
  TOKEN_STATISTICS stats;
  if (GetTokenInformation(token, TokenStatistics, &stats, sizeof stats, &needed)) {
    PSECURITY_LOGON_SESSION_DATA data = NULL;
    if (LsaGetLogonSessionData(&stats.AuthenticationId, &data) == 0 && data) {
      type = data->LogonType;
      LsaFreeReturnBuffer(data);
    }
  }
  BYTE buffer[256];
  LPSTR sid = NULL;
  if (GetTokenInformation(token, TokenUser, buffer, sizeof buffer, &needed) &&
      ConvertSidToStringSidA(((TOKEN_USER *)buffer)->User.Sid, &sid)) {
    snprintf(sid_text, 200, "%s", sid);
    LocalFree(sid);
  }
  CloseHandle(token);
  return type;
}

/* Lowercase canonical UUID from the runner's CSPRNG-backed GUID. */
static void account_id(char out[37]) {
  GUID g;
  CoCreateGuid(&g);
  snprintf(out, 37, "%08lx-%04x-%04x-%02x%02x-%02x%02x%02x%02x%02x%02x", (unsigned long)g.Data1, g.Data2, g.Data3,
           g.Data4[0], g.Data4[1], g.Data4[2], g.Data4[3], g.Data4[4], g.Data4[5], g.Data4[6], g.Data4[7]);
}

static exr_credentials_status get_status(exr_credentials_store *store, const char *account, char *secret_out,
                                         size_t capacity) {
  uint8_t buffer[EXR_CREDENTIALS_SECRET_MAX];
  size_t length = 0;
  exr_credentials_status status = exr_credentials_get(store, account, buffer, sizeof buffer, &length);
  if (secret_out) {
    secret_out[0] = 0;
    if (status == EXR_CRED_OK && length < capacity) { memcpy(secret_out, buffer, length); secret_out[length] = 0; }
  }
  exr_credentials_wipe(buffer, sizeof buffer);
  return status;
}

static int run_unavailable(void) {
  char sid[200];
  ULONG type = effective_logon(sid);
  check("process_runs_in_network_logon_session", type == Network, "LogonType=%lu (3=Network) user=%s",
        (unsigned long)type, sid);
  char raw[] = "probe";
  CREDENTIALW probe;
  memset(&probe, 0, sizeof probe);
  probe.Type = CRED_TYPE_GENERIC;
  probe.TargetName = (LPWSTR)L"EXReaderCredentials/ledger-f10-raw-probe";
  probe.Persist = CRED_PERSIST_LOCAL_MACHINE;
  probe.CredentialBlob = (LPBYTE)raw;
  probe.CredentialBlobSize = 5;
  BOOL wrote = CredWriteW(&probe, 0);
  DWORD error = wrote ? 0 : GetLastError();
  if (wrote) CredDeleteW(probe.TargetName, CRED_TYPE_GENERIC, 0);
  check("platform_credwrite_refused", !wrote && error == ERROR_NO_SUCH_LOGON_SESSION,
        "CredWriteW=%d GetLastError=%lu (1312=ERROR_NO_SUCH_LOGON_SESSION)", (int)wrote, (unsigned long)error);
  exr_credentials_store *store = NULL;
  exr_credentials_status opened = exr_credentials_open(NS, &store);
  check("module_open", opened == EXR_CRED_OK && store, "open=%s", exr_credentials_status_name(opened));
  if (!store) return finish("unavailable");
  char account[37];
  account_id(account);
  const uint8_t secret[] = "network-session-secret";
  exr_credentials_status put = exr_credentials_put(store, account, secret, sizeof secret - 1);
  check("module_put_reports_unavailable", put == EXR_CRED_UNAVAILABLE, "put=%s", exr_credentials_status_name(put));
  exr_credentials_status got = get_status(store, account, NULL, 0);
  check("module_get_reports_unavailable", got == EXR_CRED_UNAVAILABLE, "get=%s", exr_credentials_status_name(got));
  exr_credentials_status deleted = exr_credentials_delete(store, account);
  check("module_delete_reports_unavailable", deleted == EXR_CRED_UNAVAILABLE, "delete=%s",
        exr_credentials_status_name(deleted));
  exr_credentials_close(store);
  return finish("unavailable");
}

static int run_isolation(void) {
  const char *user_a = getenv("EXR_F10_USER"), *password_a = getenv("EXR_F10_PASSWORD");
  if (!user_a || !*user_a || !password_a || !*password_a) { fputs("EXR_F10_USER/EXR_F10_PASSWORD required\n", stderr); return 2; }
  wchar_t user[128], password[256];
  MultiByteToWideChar(CP_UTF8, 0, user_a, -1, user, 128);
  MultiByteToWideChar(CP_UTF8, 0, password_a, -1, password, 256);
  char runner_sid[200], other_sid[200];
  effective_logon(runner_sid);
  exr_credentials_store *store = NULL;
  exr_credentials_status opened = exr_credentials_open(NS, &store);
  check("module_open", opened == EXR_CRED_OK && store, "open=%s", exr_credentials_status_name(opened));
  if (!store) return finish("isolation");
  char runner_account[37], other_account[37], secret[64];
  account_id(runner_account);
  account_id(other_account);
  const uint8_t runner_secret[] = "runner-account-secret";
  exr_credentials_status put = exr_credentials_put(store, runner_account, runner_secret, sizeof runner_secret - 1);
  exr_credentials_status got = get_status(store, runner_account, secret, sizeof secret);
  check("runner_round_trip", put == EXR_CRED_OK && got == EXR_CRED_OK && !strcmp(secret, (const char *)runner_secret),
        "put=%s get=%s", exr_credentials_status_name(put), exr_credentials_status_name(got));
  static const DWORD types[] = {LOGON32_LOGON_INTERACTIVE, LOGON32_LOGON_BATCH, LOGON32_LOGON_NETWORK_CLEARTEXT};
  static const char *names[] = {"interactive", "batch", "network_cleartext"};
  HANDLE token = NULL;
  int used = -1;
  DWORD errors[3] = {0};
  for (int i = 0; i < 3 && !token; i++) {
    if (LogonUserW(user, L".", password, types[i], LOGON32_PROVIDER_DEFAULT, &token)) used = i;
    else { errors[i] = GetLastError(); token = NULL; }
  }
  SecureZeroMemory(password, sizeof password);
  check("second_local_account_logon", token != NULL, "logon=%s errors=%lu/%lu/%lu", used >= 0 ? names[used] : "none",
        (unsigned long)errors[0], (unsigned long)errors[1], (unsigned long)errors[2]);
  if (token) {
    PROFILEINFOW profile;
    memset(&profile, 0, sizeof profile);
    profile.dwSize = sizeof profile;
    profile.lpUserName = user;
    int profile_loaded = LoadUserProfileW(token, &profile) != 0;
    ImpersonateLoggedOnUser(token);
    effective_logon(other_sid);
    check("impersonating_a_different_account", strcmp(runner_sid, other_sid) != 0, "runner=%s other=%s profile=%d",
          runner_sid, other_sid, profile_loaded);
    exr_credentials_status foreign = get_status(store, runner_account, NULL, 0);
    check("runner_record_not_found_for_other_account", foreign == EXR_CRED_NOT_FOUND, "get=%s",
          exr_credentials_status_name(foreign));
    const uint8_t other_secret[] = "other-account-secret";
    exr_credentials_status other_put = exr_credentials_put(store, other_account, other_secret, sizeof other_secret - 1);
    exr_credentials_status other_get = get_status(store, other_account, secret, sizeof secret);
    check("other_account_round_trip_in_its_own_vault",
          other_put == EXR_CRED_OK && other_get == EXR_CRED_OK && !strcmp(secret, (const char *)other_secret),
          "put=%s get=%s", exr_credentials_status_name(other_put), exr_credentials_status_name(other_get));
    RevertToSelf();
    exr_credentials_status back = get_status(store, other_account, NULL, 0);
    check("other_account_record_not_found_for_runner", back == EXR_CRED_NOT_FOUND, "get=%s",
          exr_credentials_status_name(back));
    exr_credentials_status mine = get_status(store, runner_account, secret, sizeof secret);
    check("runner_record_intact", mine == EXR_CRED_OK && !strcmp(secret, (const char *)runner_secret), "get=%s",
          exr_credentials_status_name(mine));
    ImpersonateLoggedOnUser(token);
    exr_credentials_delete(store, other_account);
    RevertToSelf();
    if (profile_loaded) UnloadUserProfile(token, profile.hProfile);
    CloseHandle(token);
  }
  exr_credentials_delete(store, runner_account);
  exr_credentials_status gone = get_status(store, runner_account, NULL, 0);
  check("runner_cleanup", gone == EXR_CRED_NOT_FOUND, "get after delete=%s", exr_credentials_status_name(gone));
  exr_credentials_close(store);
  SecureZeroMemory(secret, sizeof secret);
  return finish("isolation");
}

int main(int argc, char **argv) {
  setvbuf(stdout, NULL, _IONBF, 0);
  if (argc == 2 && !strcmp(argv[1], "unavailable")) return run_unavailable();
  if (argc == 2 && !strcmp(argv[1], "isolation")) return run_isolation();
  fputs("usage: credential-identity-probe unavailable|isolation\n", stderr);
  return 2;
}
