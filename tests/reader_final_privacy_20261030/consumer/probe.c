/* SPDX-License-Identifier: MIT */
/* F10 privacy probe: drives the installed credential module with a synthetic secret
   taken from F10_SECRET_HEX. Output carries status names and pass/fail bits only,
   never secret bytes. Usage: f10-probe <put|verify|absent|delete|unavailable|args> */
#include <exr_credentials.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char *NS = "org.exreader.f10.privacy";
static const char *ACCOUNT = "3f10c0de-0000-4000-8000-000000000a01";

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

static int check(const char *name, int ok) {
  printf("CHECK %s %d\n", name, ok ? 1 : 0);
  fflush(stdout);
  return ok;
}

static int argument_checks(exr_credentials_store *store, const uint8_t *secret, size_t secret_length) {
  static uint8_t big[EXR_CREDENTIALS_SECRET_MAX + 1], buffer[64];
  exr_credentials_store *probe = NULL;
  size_t got = 7, i;
  int ok = 1;
  memset(big, 'x', sizeof big);
  ok &= check("open-bad-namespace", exr_credentials_open("Bad_NS", &probe) == EXR_CRED_ARGUMENT && !probe);
  ok &= check("put-bad-account", exr_credentials_put(store, "NOT-A-UUID", secret, secret_length) == EXR_CRED_ARGUMENT);
  ok &= check("put-empty", exr_credentials_put(store, ACCOUNT, secret, 0) == EXR_CRED_ARGUMENT);
  ok &= check("put-oversize", exr_credentials_put(store, ACCOUNT, big, sizeof big) == EXR_CRED_ARGUMENT);
  ok &= check("get-bad-account", exr_credentials_get(store, "NOT-A-UUID", buffer, sizeof buffer, &got) == EXR_CRED_ARGUMENT && got == 0);
  ok &= check("storage-untouched", exr_credentials_get(store, ACCOUNT, buffer, sizeof buffer, &got) == EXR_CRED_NOT_FOUND);
  memset(buffer, 0xA5, sizeof buffer);
  exr_credentials_wipe(buffer, sizeof buffer);
  for (i = 0; i < sizeof buffer; i++) if (buffer[i]) ok = 0;
  return check("wipe-zeroes", ok);
}

int main(int argc, char **argv) {
  static uint8_t secret[EXR_CREDENTIALS_SECRET_MAX], buffer[EXR_CREDENTIALS_SECRET_MAX];
  size_t secret_length = 0, got = 0;
  exr_credentials_store *store = NULL;
  exr_credentials_status s;
  const char *mode = argc == 2 ? argv[1] : "";
  int ok = 0;
  if (!*mode) {
    fprintf(stderr, "usage: f10-probe <put|verify|absent|delete|unavailable|args>\n");
    return 2;
  }
  if (strcmp(mode, "absent") && strcmp(mode, "delete") && strcmp(mode, "args") &&
      !decode(getenv("F10_SECRET_HEX"), secret, sizeof secret, &secret_length)) {
    fprintf(stderr, "F10_SECRET_HEX missing or invalid\n");
    return 2;
  }
  if (!strcmp(mode, "args")) memcpy(secret, "synthetic-not-stored", secret_length = 20);
  s = exr_credentials_open(NS, &store);
  if (s != EXR_CRED_OK || !store) {
    say("open", s);
    return 1;
  }
  if (!strcmp(mode, "put")) {
    s = exr_credentials_put(store, ACCOUNT, secret, secret_length);
    say("put", s);
    ok = s == EXR_CRED_OK;
  } else if (!strcmp(mode, "verify")) {
    s = exr_credentials_get(store, ACCOUNT, buffer, sizeof buffer, &got);
    say("get", s);
    ok = check("match", s == EXR_CRED_OK && got == secret_length && !memcmp(buffer, secret, got));
  } else if (!strcmp(mode, "absent")) {
    s = exr_credentials_get(store, ACCOUNT, buffer, sizeof buffer, &got);
    say("get", s);
    ok = s == EXR_CRED_NOT_FOUND && got == 0;
  } else if (!strcmp(mode, "delete")) {
    s = exr_credentials_delete(store, ACCOUNT);
    say("delete", s);
    ok = s == EXR_CRED_OK;
  } else if (!strcmp(mode, "unavailable")) {
    s = exr_credentials_put(store, ACCOUNT, secret, secret_length);
    say("put", s);
    ok = s == EXR_CRED_UNAVAILABLE || s == EXR_CRED_IO;
    s = exr_credentials_get(store, ACCOUNT, buffer, sizeof buffer, &got);
    say("get", s);
    ok &= s != EXR_CRED_OK && got == 0;
  } else if (!strcmp(mode, "args")) {
    ok = argument_checks(store, secret, secret_length);
  } else {
    fprintf(stderr, "unknown mode\n");
  }
  exr_credentials_wipe(buffer, sizeof buffer);
  exr_credentials_wipe(secret, sizeof secret);
  exr_credentials_close(store);
  return ok ? 0 : 1;
}
