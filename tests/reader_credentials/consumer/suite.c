/* SPDX-License-Identifier: MIT */
#include "suite.h"
#include <stdio.h>
#include <string.h>

#define SENTINEL 0xA5
#define CAPACITY (EXR_CREDENTIALS_SECRET_MAX + 16)

typedef struct {
  suite_emit emit;
  void *context;
  int failed, total;
} runner;

static void report(runner *r, const char *id, int ok, const char *detail) {
  char line[256];
  snprintf(line, sizeof line, "check %s %s %s", id, ok ? "pass" : "fail", detail ? detail : "-");
  ++r->total;
  if (!ok) ++r->failed;
  r->emit(r->context, line);
}

static const char *name(exr_credentials_status s) { return exr_credentials_status_name(s); }

static int hex(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  return -1;
}

static const char *account_names = "abcdrp";
static const char *secret_names[SUITE_SECRETS] = {"primary", "update", "other", "ns2", "unicode", "binary", "max", "reopen"};

int suite_parse(const char *text, suite_input *input) {
  const char *line = text;
  memset(input, 0, sizeof *input);
  while (line && *line) {
    const char *end = strchr(line, '\n');
    size_t n = end ? (size_t)(end - line) : strlen(line);
    char key[16] = {0}, label[16] = {0};
    const char *value;
    size_t value_length;
    if (n && line[n - 1] == '\r') --n;
    if (sscanf(line, "%15s", key) == 1) {
      value = line + strlen(key);
      while (*value == ' ') ++value;
      if (!strcmp(key, "secret") || !strcmp(key, "account")) {
        if (sscanf(value, "%15s", label) != 1) return 1;
        value += strlen(label);
        while (*value == ' ') ++value;
      }
      value_length = n - (size_t)(value - line);
      if (!strcmp(key, "namespace") || !strcmp(key, "namespace2")) {
        char *out = key[9] ? input->ns2 : input->ns;
        if (value_length > EXR_CREDENTIALS_NAMESPACE_MAX) return 1;
        memcpy(out, value, value_length);
        out[value_length] = 0;
      } else if (!strcmp(key, "account")) {
        const char *slot = label[0] && !label[1] ? strchr(account_names, label[0]) : NULL;
        if (!slot || value_length != EXR_CREDENTIALS_ACCOUNT_ID_LENGTH) return 1;
        memcpy(input->account[slot - account_names], value, value_length);
      } else if (!strcmp(key, "secret")) {
        size_t i, k;
        for (k = 0; k < SUITE_SECRETS && strcmp(secret_names[k], label); ++k) {}
        if (k == SUITE_SECRETS || value_length % 2 || value_length / 2 > EXR_CREDENTIALS_SECRET_MAX) return 1;
        snprintf(input->secret[k].name, sizeof input->secret[k].name, "%s", label);
        for (i = 0; i < value_length / 2; ++i) {
          int hi = hex(value[2 * i]), lo = hex(value[2 * i + 1]);
          if (hi < 0 || lo < 0) return 1;
          input->secret[k].bytes[i] = (uint8_t)(hi * 16 + lo);
        }
        input->secret[k].length = value_length / 2;
      } else {
        return 1;
      }
    }
    line = end ? end + 1 : NULL;
  }
  return 0;
}

void suite_wipe(suite_input *input) { exr_credentials_wipe(input, sizeof *input); }

static const suite_secret *secret(const suite_input *in, const char *label) {
  int k;
  for (k = 0; k < SUITE_SECRETS; ++k)
    if (!strcmp(secret_names[k], label)) return in->secret[k].length ? &in->secret[k] : NULL;
  return NULL;
}

static int untouched(const uint8_t *buffer, size_t from, size_t to) {
  size_t i;
  for (i = from; i < to; ++i)
    if (buffer[i] != SENTINEL) return 0;
  return 1;
}

/* get and compare against expected (NULL expects the given non-OK status). */
static int expect_get(exr_credentials_store *store, const char *account, const suite_secret *expected,
                      exr_credentials_status want, char *detail, size_t detail_size) {
  static uint8_t buffer[CAPACITY];
  size_t length = 12345;
  exr_credentials_status status;
  int ok;
  memset(buffer, SENTINEL, sizeof buffer);
  status = exr_credentials_get(store, account, buffer, EXR_CREDENTIALS_SECRET_MAX, &length);
  if (expected) {
    ok = status == EXR_CRED_OK && length == expected->length &&
         !memcmp(buffer, expected->bytes, length) && untouched(buffer, length, sizeof buffer);
  } else {
    ok = status == want && length == 0 && untouched(buffer, 0, sizeof buffer);
  }
  snprintf(detail, detail_size, "get=%s", name(status));
  exr_credentials_wipe(buffer, sizeof buffer);
  return ok;
}

static int valid_input(const suite_input *in, int need_ns2) {
  int i;
  if (!in->ns[0] || (need_ns2 && !in->ns2[0])) return 0;
  for (i = 0; i < SUITE_ACCOUNTS; ++i)
    if (!in->account[i][0]) return 0;
  for (i = 0; i < SUITE_SECRETS; ++i)
    if (!in->secret[i].length) return 0;
  return 1;
}

static void run_suite(runner *r, const suite_input *in) {
  const char *a = in->account[0], *b = in->account[1], *c = in->account[2], *d = in->account[3];
  const suite_secret *primary = secret(in, "primary"), *update = secret(in, "update"),
    *other = secret(in, "other"), *ns2secret = secret(in, "ns2"), *unicode = secret(in, "unicode"),
    *binary = secret(in, "binary"), *max = secret(in, "max"), *reopen = secret(in, "reopen");
  exr_credentials_store *store = NULL, *store2 = NULL, *probe = NULL;
  exr_credentials_status s, t, u;
  char detail[160], more[160];
  static uint8_t buffer[CAPACITY], oversize[EXR_CREDENTIALS_SECRET_MAX + 1];
  size_t length;
  int ok, i;

  ok = !strcmp(EXR_CREDENTIALS_VERSION, "0.1.0") && EXR_CREDENTIALS_SECRET_MAX == 2048u &&
       !strcmp(name(EXR_CRED_OK), "OK") && !strcmp(name(EXR_CRED_NOT_FOUND), "NOT_FOUND") &&
       !strcmp(name(EXR_CRED_UNAVAILABLE), "UNAVAILABLE") && !strcmp(name(EXR_CRED_ARGUMENT), "ARGUMENT") &&
       !strcmp(name(EXR_CRED_IO), "IO") && !strcmp(name((exr_credentials_status)99), "UNKNOWN") &&
       EXR_CRED_OK == 0 && EXR_CRED_NOT_FOUND == 1 && EXR_CRED_UNAVAILABLE == 2 &&
       EXR_CRED_ARGUMENT == 3 && EXR_CRED_IO == 4;
  report(r, "contract-version-and-status-names", ok, EXR_CREDENTIALS_VERSION);

  {
    static const char *bad[] = {"", "Upper.case", ".lead", "-lead", "a/b", "a b", "a_b", "a\\b",
      "\xe5\x90\x8d", "0123456789012345678901234567890123456789012345678901234567890123x"};
    ok = 1;
    for (i = 0; i < (int)(sizeof bad / sizeof bad[0]); ++i) {
      probe = (exr_credentials_store *)&ok;
      s = exr_credentials_open(bad[i], &probe);
      if (s != EXR_CRED_ARGUMENT || probe) ok = 0;
    }
    probe = (exr_credentials_store *)&ok;
    if (exr_credentials_open(NULL, &probe) != EXR_CRED_ARGUMENT || probe) ok = 0;
    if (exr_credentials_open(in->ns, NULL) != EXR_CRED_ARGUMENT) ok = 0;
    report(r, "open-rejects-invalid-namespace", ok, "ARGUMENT");
  }
  probe = NULL;
  s = exr_credentials_open("0123456789012345678901234567890123456789012345678901234567890123", &probe);
  t = exr_credentials_open(in->ns, &store);
  u = exr_credentials_open(in->ns2, &store2);
  snprintf(detail, sizeof detail, "max=%s ns=%s ns2=%s", name(s), name(t), name(u));
  report(r, "open-accepts-namespaces", s == EXR_CRED_OK && probe && t == EXR_CRED_OK && store &&
         u == EXR_CRED_OK && store2, detail);
  exr_credentials_close(probe);
  if (!store || !store2) {
    exr_credentials_close(store);
    exr_credentials_close(store2);
    return;
  }

  report(r, "empty-get-not-found", expect_get(store, a, NULL, EXR_CRED_NOT_FOUND, detail, sizeof detail), detail);
  s = exr_credentials_delete(store, a);
  snprintf(detail, sizeof detail, "delete=%s", name(s));
  report(r, "empty-delete-not-found", s == EXR_CRED_NOT_FOUND, detail);

  s = exr_credentials_put(store, a, primary->bytes, primary->length);
  ok = s == EXR_CRED_OK && expect_get(store, a, primary, EXR_CRED_OK, more, sizeof more);
  snprintf(detail, sizeof detail, "put=%s %s", name(s), more);
  report(r, "write-read-back", ok, detail);

  s = exr_credentials_put(store, a, update->bytes, update->length);
  ok = s == EXR_CRED_OK && update->length < primary->length &&
       expect_get(store, a, update, EXR_CRED_OK, more, sizeof more);
  snprintf(detail, sizeof detail, "put=%s %s shorter=%d", name(s), more, update->length < primary->length);
  report(r, "exact-update-no-stale-bytes", ok, detail);

  ok = expect_get(store, b, NULL, EXR_CRED_NOT_FOUND, more, sizeof more);
  s = exr_credentials_put(store, b, other->bytes, other->length);
  ok = ok && s == EXR_CRED_OK && expect_get(store, a, update, EXR_CRED_OK, detail, sizeof detail) &&
       expect_get(store, b, other, EXR_CRED_OK, detail, sizeof detail);
  snprintf(detail, sizeof detail, "before=%s put=%s", more, name(s));
  report(r, "account-isolation", ok, detail);

  ok = expect_get(store2, a, NULL, EXR_CRED_NOT_FOUND, more, sizeof more);
  s = exr_credentials_put(store2, a, ns2secret->bytes, ns2secret->length);
  ok = ok && s == EXR_CRED_OK && expect_get(store, a, update, EXR_CRED_OK, detail, sizeof detail) &&
       expect_get(store2, a, ns2secret, EXR_CRED_OK, detail, sizeof detail);
  t = exr_credentials_delete(store2, a);
  ok = ok && t == EXR_CRED_OK && expect_get(store2, a, NULL, EXR_CRED_NOT_FOUND, detail, sizeof detail) &&
       expect_get(store, a, update, EXR_CRED_OK, detail, sizeof detail);
  snprintf(detail, sizeof detail, "before=%s put=%s delete=%s", more, name(s), name(t));
  report(r, "namespace-isolation", ok, detail);

  s = exr_credentials_put(store, c, unicode->bytes, unicode->length);
  ok = s == EXR_CRED_OK && expect_get(store, c, unicode, EXR_CRED_OK, more, sizeof more);
  snprintf(detail, sizeof detail, "put=%s %s", name(s), more);
  report(r, "unicode-secret-exact", ok, detail);

  ok = memchr(binary->bytes, 0, binary->length) != NULL;
  s = exr_credentials_put(store, c, binary->bytes, binary->length);
  ok = ok && s == EXR_CRED_OK && expect_get(store, c, binary, EXR_CRED_OK, more, sizeof more);
  snprintf(detail, sizeof detail, "put=%s %s", name(s), more);
  report(r, "opaque-binary-with-nul-exact", ok, detail);

  s = exr_credentials_put(store, d, max->bytes, max->length);
  ok = max->length == EXR_CREDENTIALS_SECRET_MAX && s == EXR_CRED_OK &&
       expect_get(store, d, max, EXR_CRED_OK, more, sizeof more);
  snprintf(detail, sizeof detail, "put=%s %s bytes=%u", name(s), more, (unsigned)max->length);
  report(r, "maximum-secret-exact", ok, detail);

  memcpy(oversize, max->bytes, max->length);
  oversize[EXR_CREDENTIALS_SECRET_MAX] = 0x5a;
  s = exr_credentials_put(store, d, oversize, sizeof oversize);
  t = exr_credentials_put(store, d, max->bytes, 0);
  u = exr_credentials_put(store, d, NULL, 5);
  exr_credentials_wipe(oversize, sizeof oversize);
  ok = s == EXR_CRED_ARGUMENT && t == EXR_CRED_ARGUMENT && u == EXR_CRED_ARGUMENT &&
       expect_get(store, d, max, EXR_CRED_OK, more, sizeof more);
  snprintf(detail, sizeof detail, "oversize=%s empty=%s null=%s %s", name(s), name(t), name(u), more);
  report(r, "out-of-bounds-secret-refused-record-kept", ok, detail);

  memset(buffer, SENTINEL, sizeof buffer);
  length = 0;
  s = exr_credentials_get(store, d, buffer, EXR_CREDENTIALS_SECRET_MAX - 1, &length);
  ok = s == EXR_CRED_ARGUMENT && length == EXR_CREDENTIALS_SECRET_MAX && untouched(buffer, 0, sizeof buffer);
  length = 0;
  t = exr_credentials_get(store, d, buffer, 0, &length);
  ok = ok && t == EXR_CRED_ARGUMENT && length == EXR_CREDENTIALS_SECRET_MAX && untouched(buffer, 0, sizeof buffer);
  snprintf(detail, sizeof detail, "short=%s zero=%s required=%u", name(s), name(t), (unsigned)length);
  report(r, "small-buffer-reports-length-untouched", ok, detail);

  {
    char upper[EXR_CREDENTIALS_ACCOUNT_ID_LENGTH + 1], braces[48], bare[40], shorter[40], longer[48],
      nonhex[EXR_CREDENTIALS_ACCOUNT_ID_LENGTH + 1], newline[48];
    const char *bad[8];
    size_t k, j = 0;
    for (k = 0; k <= EXR_CREDENTIALS_ACCOUNT_ID_LENGTH; ++k)
      upper[k] = (a[k] >= 'a' && a[k] <= 'f') ? (char)(a[k] - 32) : a[k];
    if (!strcmp(upper, a)) upper[0] = 'A'; /* digits-only first group */
    snprintf(braces, sizeof braces, "{%s}", a);
    for (k = 0; a[k]; ++k)
      if (a[k] != '-') bare[j++] = a[k];
    bare[j] = 0;
    snprintf(shorter, sizeof shorter, "%.35s", a);
    snprintf(longer, sizeof longer, "%s0", a);
    memcpy(nonhex, a, sizeof nonhex);
    nonhex[0] = 'g';
    snprintf(newline, sizeof newline, "%s\n", a);
    bad[0] = upper; bad[1] = braces; bad[2] = bare; bad[3] = shorter;
    bad[4] = longer; bad[5] = nonhex; bad[6] = newline; bad[7] = "";
    ok = 1;
    for (k = 0; k < 8; ++k) {
      memset(buffer, SENTINEL, sizeof buffer);
      length = 7;
      if (exr_credentials_put(store, bad[k], other->bytes, other->length) != EXR_CRED_ARGUMENT ||
          exr_credentials_get(store, bad[k], buffer, EXR_CREDENTIALS_SECRET_MAX, &length) != EXR_CRED_ARGUMENT ||
          length != 0 || !untouched(buffer, 0, sizeof buffer) ||
          exr_credentials_delete(store, bad[k]) != EXR_CRED_ARGUMENT)
        ok = 0;
    }
    if (exr_credentials_put(store, NULL, other->bytes, other->length) != EXR_CRED_ARGUMENT ||
        exr_credentials_delete(store, NULL) != EXR_CRED_ARGUMENT)
      ok = 0;
    ok = ok && expect_get(store, a, update, EXR_CRED_OK, more, sizeof more);
    report(r, "invalid-account-ids-refused", ok, "ARGUMENT");
  }

  ok = exr_credentials_put(NULL, a, other->bytes, other->length) == EXR_CRED_ARGUMENT &&
       exr_credentials_delete(NULL, a) == EXR_CRED_ARGUMENT;
  length = 9;
  ok = ok && exr_credentials_get(NULL, a, buffer, sizeof buffer, &length) == EXR_CRED_ARGUMENT && length == 0;
  length = 9;
  ok = ok && exr_credentials_get(store, a, NULL, sizeof buffer, &length) == EXR_CRED_ARGUMENT && length == 0;
  ok = ok && exr_credentials_get(store, a, buffer, sizeof buffer, NULL) == EXR_CRED_ARGUMENT;
  exr_credentials_wipe(buffer, sizeof buffer);
  exr_credentials_close(NULL);
  report(r, "null-arguments-refused", ok, "ARGUMENT");

  s = exr_credentials_delete(store, b);
  ok = s == EXR_CRED_OK && expect_get(store, b, NULL, EXR_CRED_NOT_FOUND, more, sizeof more);
  t = exr_credentials_delete(store, b);
  ok = ok && t == EXR_CRED_NOT_FOUND && expect_get(store, a, update, EXR_CRED_OK, detail, sizeof detail);
  snprintf(detail, sizeof detail, "delete=%s %s again=%s", name(s), more, name(t));
  report(r, "delete-and-repeat-delete", ok, detail);

  exr_credentials_close(store);
  store = NULL;
  s = exr_credentials_open(in->ns, &store);
  ok = s == EXR_CRED_OK && store && expect_get(store, a, update, EXR_CRED_OK, more, sizeof more);
  snprintf(detail, sizeof detail, "open=%s %s", name(s), more);
  report(r, "handle-reopen-reads-record", ok, detail);
  if (!store) {
    exr_credentials_close(store2);
    return;
  }

  memset(buffer, SENTINEL, sizeof buffer);
  exr_credentials_wipe(buffer, sizeof buffer);
  exr_credentials_wipe(NULL, 4);
  for (ok = 1, i = 0; i < (int)sizeof buffer; ++i)
    if (buffer[i]) ok = 0;
  report(r, "wipe-zeroes-buffer", ok, "-");

  s = exr_credentials_delete(store, a);
  t = exr_credentials_delete(store, c);
  u = exr_credentials_delete(store, d);
  ok = s == EXR_CRED_OK && t == EXR_CRED_OK && u == EXR_CRED_OK;
  s = exr_credentials_put(store, in->account[4], reopen->bytes, reopen->length);
  ok = ok && s == EXR_CRED_OK;
  snprintf(detail, sizeof detail, "cleanup=%s reopen-put=%s", ok ? "OK" : "FAILED", name(s));
  report(r, "own-records-removed-reopen-record-written", ok, detail);
  exr_credentials_close(store);
  exr_credentials_close(store2);
}

int suite_run(const char *phase, const suite_input *in, suite_emit emit, void *context) {
  runner r = {emit, context, 0, 0};
  char line[96], detail[160];
  exr_credentials_store *store = NULL, *store2 = NULL;
  exr_credentials_status s, t, u;
  int ok, i;
  if (!valid_input(in, 1)) {
    report(&r, "harness-input", 0, "missing namespace, account or secret");
  } else if (!strcmp(phase, "suite")) {
    run_suite(&r, in);
  } else if (!strcmp(phase, "reopen")) {
    s = exr_credentials_open(in->ns, &store);
    ok = s == EXR_CRED_OK && expect_get(store, in->account[4], secret(in, "reopen"), EXR_CRED_OK, detail, sizeof detail);
    report(&r, "new-process-reads-persisted-record", ok, detail);
    t = exr_credentials_delete(store, in->account[4]);
    ok = t == EXR_CRED_OK && expect_get(store, in->account[4], NULL, EXR_CRED_NOT_FOUND, detail, sizeof detail);
    report(&r, "new-process-deletes-record", ok, name(t));
    exr_credentials_close(store);
  } else if (!strcmp(phase, "seed")) {
    const suite_secret *primary = secret(in, "primary");
    s = exr_credentials_open(in->ns, &store);
    t = s == EXR_CRED_OK ? exr_credentials_put(store, in->account[5], primary->bytes, primary->length) : s;
    ok = t == EXR_CRED_OK && expect_get(store, in->account[5], primary, EXR_CRED_OK, detail, sizeof detail);
    report(&r, "seed-probe-record", ok, name(t));
    exr_credentials_close(store);
  } else if (!strcmp(phase, "unavailable")) {
    const suite_secret *other = secret(in, "other");
    s = exr_credentials_open(in->ns, &store);
    report(&r, "open-needs-no-service", s == EXR_CRED_OK, name(s));
    if (store) {
      ok = expect_get(store, in->account[5], NULL, EXR_CRED_UNAVAILABLE, detail, sizeof detail);
      report(&r, "unavailable-get-existing", ok, detail);
      ok = expect_get(store, in->account[0], NULL, EXR_CRED_UNAVAILABLE, detail, sizeof detail);
      report(&r, "unavailable-get-absent", ok, detail);
      t = exr_credentials_put(store, in->account[5], other->bytes, other->length);
      report(&r, "unavailable-put", t == EXR_CRED_UNAVAILABLE, name(t));
      u = exr_credentials_delete(store, in->account[5]);
      report(&r, "unavailable-delete", u == EXR_CRED_UNAVAILABLE, name(u));
      exr_credentials_close(store);
    }
  } else if (!strcmp(phase, "cleanup")) {
    s = exr_credentials_open(in->ns, &store);
    t = exr_credentials_open(in->ns2, &store2);
    ok = s == EXR_CRED_OK && t == EXR_CRED_OK;
    for (i = 0; ok && i < SUITE_ACCOUNTS; ++i) {
      u = exr_credentials_delete(store, in->account[i]);
      if (u != EXR_CRED_OK && u != EXR_CRED_NOT_FOUND) ok = 0;
      if (!expect_get(store, in->account[i], NULL, EXR_CRED_NOT_FOUND, detail, sizeof detail)) ok = 0;
    }
    if (ok) {
      u = exr_credentials_delete(store2, in->account[0]);
      if ((u != EXR_CRED_OK && u != EXR_CRED_NOT_FOUND) ||
          !expect_get(store2, in->account[0], NULL, EXR_CRED_NOT_FOUND, detail, sizeof detail))
        ok = 0;
    }
    report(&r, "cleanup-only-own-records", ok, ok ? "NOT_FOUND" : "residual");
    exr_credentials_close(store);
    exr_credentials_close(store2);
  } else {
    return -1;
  }
  snprintf(line, sizeof line, "phase %s %d/%d", phase, r.total - r.failed, r.total);
  emit(context, line);
  return r.failed;
}
