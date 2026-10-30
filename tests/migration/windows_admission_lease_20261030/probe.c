/* SPDX-License-Identifier: MIT
 * Installed consumer of the admission lease. Driven by run.py across processes. */
#include "lm_win_lease.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
static WCHAR *wide(const char *s) {
  int n = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, s, -1, NULL, 0);
  WCHAR *w = n > 0 ? (WCHAR *)malloc((size_t)n * sizeof(WCHAR)) : NULL;
  if (w && !MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, s, -1, w, n)) { free(w); w = NULL; }
  return w;
}
static int parse_mode(const char *s, lm_wl_mode *m) {
  if (!strcmp(s, "shared")) *m = LM_WL_SHARED; else if (!strcmp(s, "exclusive")) *m = LM_WL_EXCLUSIVE; else return 0;
  return 1;
}
static int g_pending;
static void report(lm_wl_status s, const lm_wl_error *e, unsigned long long gen) {
  printf("{\"status\":%d,\"native\":%lu,\"generation\":%llu,\"pending\":%d,\"pid\":%lu,\"source\":\"%s\"}\n", (int)s, (unsigned long)e->native, gen, g_pending, (unsigned long)GetCurrentProcessId(), SOURCE_SHA);
  fflush(stdout);
}
int main(int argc, char **argv) {
  lm_wl_lease *l = NULL; lm_wl_error e = {0, ""}; lm_wl_mode m; WCHAR *dir; lm_wl_status s; char line[64];
  if (argc < 4 || !(dir = wide(argv[2]))) return 64;
  if (!strcmp(argv[1], "hold") && argc == 5 && parse_mode(argv[4], &m)) {
    s = lm_wl_acquire(dir, argv[3], m, 0, &l, &e);
    g_pending = lm_wl_pending(l);
    report(s, &e, l ? lm_wl_generation(l) : 0);
    if (s != LM_WL_OK) return 2;
    /* Hold until told to release; parent may instead terminate this process. */
    while (fgets(line, sizeof line, stdin)) {
      if (!strncmp(line, "check", 5)) { s = lm_wl_check(l, &e); report(s, &e, lm_wl_generation(l)); }
      else if (!strncmp(line, "release", 7)) break;
    }
    lm_wl_release(l);
    return 0;
  }
  if (!strcmp(argv[1], "try") && argc == 6 && parse_mode(argv[4], &m)) {
    s = lm_wl_acquire(dir, argv[3], m, (DWORD)strtoul(argv[5], NULL, 10), &l, &e);
    g_pending = lm_wl_pending(l);
    report(s, &e, l ? lm_wl_generation(l) : 0);
    if (l) lm_wl_release(l);
    return s == LM_WL_OK ? 0 : 1;
  }
  /* publish <dir> <id> <cut>: begin; (cut after-begin) ; commit; (cut after-commit).
   * The parent hard-kills the process at the announced point. */
  if (!strcmp(argv[1], "publish") && argc == 5) {
    uint64_t n = 0;
    s = lm_wl_acquire(dir, argv[3], LM_WL_EXCLUSIVE, 0, &l, &e);
    if (s != LM_WL_OK) { report(s, &e, 0); return 1; }
    if (!strcmp(argv[4], "before-begin")) { report(s, &e, lm_wl_generation(l)); Sleep(INFINITE); }
    s = lm_wl_exclusive_begin(l, &e); g_pending = lm_wl_pending(l);
    if (s != LM_WL_OK || !strcmp(argv[4], "after-begin")) { report(s, &e, lm_wl_generation(l)); if (s != LM_WL_OK) return 1; Sleep(INFINITE); }
    s = lm_wl_exclusive_commit(l, &n, &e); g_pending = lm_wl_pending(l);
    report(s, &e, lm_wl_generation(l));
    if (s != LM_WL_OK) return 1;
    if (!strcmp(argv[4], "after-commit")) Sleep(INFINITE);
    lm_wl_release(l);
    return 0;
  }
  /* resolve <dir> <id>: exclusive re-qualification path; commit a left-over intent. */
  if (!strcmp(argv[1], "resolve") && argc == 4) {
    uint64_t n = 0;
    s = lm_wl_acquire(dir, argv[3], LM_WL_EXCLUSIVE, 0, &l, &e);
    if (s == LM_WL_OK) { g_pending = lm_wl_pending(l); if (g_pending) s = lm_wl_exclusive_commit(l, &n, &e); report(s, &e, lm_wl_generation(l)); lm_wl_release(l); }
    else report(s, &e, 0);
    return s == LM_WL_OK ? 0 : 1;
  }
  /* misuse: commit without begin, begin twice, begin from shared. */
  if (!strcmp(argv[1], "misuse") && argc == 4) {
    lm_wl_lease *sh = NULL; int ok = 1; uint64_t n = 0;
    ok &= lm_wl_acquire(dir, argv[3], LM_WL_EXCLUSIVE, 0, &l, &e) == LM_WL_OK;
    ok &= lm_wl_exclusive_commit(l, &n, &e) == LM_WL_REFUSED;
    ok &= lm_wl_exclusive_begin(l, &e) == LM_WL_OK;
    ok &= lm_wl_exclusive_begin(l, &e) == LM_WL_REFUSED;
    ok &= lm_wl_exclusive_commit(l, &n, &e) == LM_WL_OK && n == 1;
    lm_wl_release(l);
    ok &= lm_wl_acquire(dir, argv[3], LM_WL_SHARED, 0, &sh, &e) == LM_WL_OK;
    ok &= lm_wl_exclusive_begin(sh, &e) == LM_WL_INVALID && lm_wl_exclusive_commit(sh, &n, &e) == LM_WL_INVALID;
    lm_wl_release(sh);
    printf("{\"misuse\":%d,\"source\":\"%s\"}\n", ok, SOURCE_SHA);
    return ok ? 0 : 1;
  }  if (!strcmp(argv[1], "expect") && argc == 5) {
    s = lm_wl_acquire(dir, argv[3], LM_WL_SHARED, 0, &l, &e);
    if (s == LM_WL_OK) { s = lm_wl_require_generation(l, _strtoui64(argv[4], NULL, 10)); report(s, &e, lm_wl_generation(l)); lm_wl_release(l); }
    else report(s, &e, 0);
    return s == LM_WL_OK ? 0 : 1;
  }
  /* loop <dir> <id>: endless begin/commit; each acknowledged generation is printed after commit returns. */
  if (!strcmp(argv[1], "loop") && argc == 4) {
    s = lm_wl_acquire(dir, argv[3], LM_WL_EXCLUSIVE, 0, &l, &e);
    if (s != LM_WL_OK) { report(s, &e, 0); return 1; }
    for (;;) {
      uint64_t n = 0;
      if (lm_wl_exclusive_begin(l, &e) != LM_WL_OK || lm_wl_exclusive_commit(l, &n, &e) != LM_WL_OK) { report(LM_WL_NATIVE, &e, 0); return 1; }
      printf("%llu\n", (unsigned long long)n);
      fflush(stdout);
    }
  }
  /* race <dir> <id> <count>: contend for exclusive custody, begin+commit under it. */
  if (!strcmp(argv[1], "race") && argc == 5) {
    unsigned ok = 0, busy = 0, bad = 0, i, count = (unsigned)strtoul(argv[4], NULL, 10);
    for (i = 0; i < count; i++) {
      uint64_t n = 0;
      s = lm_wl_acquire(dir, argv[3], LM_WL_EXCLUSIVE, 2000, &l, &e);
      if (s == LM_WL_OK) {
        if (lm_wl_exclusive_begin(l, &e) == LM_WL_OK && lm_wl_exclusive_commit(l, &n, &e) == LM_WL_OK) ok++; else bad++;
        lm_wl_release(l);
      } else if (s == LM_WL_BUSY) busy++; else bad++;
    }
    printf("{\"ok\":%u,\"busy\":%u,\"bad\":%u,\"pid\":%lu}\n", ok, busy, bad, (unsigned long)GetCurrentProcessId());
    return bad ? 1 : 0;
  }
  /* readers <dir> <id> <ms>: shared admissions must never see pending, generation never regresses. */
  if (!strcmp(argv[1], "readers") && argc == 5) {
    unsigned ok = 0, stale = 0, busy = 0, bad = 0; unsigned long long last = 0;
    ULONGLONG end = GetTickCount64() + strtoul(argv[4], NULL, 10);
    while (GetTickCount64() < end) {
      s = lm_wl_acquire(dir, argv[3], LM_WL_SHARED, 200, &l, &e);
      if (s == LM_WL_OK) {
        unsigned long long g = lm_wl_generation(l);
        if (lm_wl_pending(l) || g < last || lm_wl_check(l, &e) != LM_WL_OK) bad++;
        last = g; ok++; lm_wl_release(l);
      } else if (s == LM_WL_STALE) stale++; else if (s == LM_WL_BUSY) busy++; else bad++;
    }
    printf("{\"ok\":%u,\"stale\":%u,\"busy\":%u,\"bad\":%u,\"last\":%llu}\n", ok, stale, busy, bad, last);
    return bad ? 1 : 0;
  }
  /* In-process: a second handle in the same process must still conflict. */
  if (!strcmp(argv[1], "selfconflict") && argc == 4) {
    lm_wl_lease *a = NULL, *b = NULL; int ok = 1;
    ok &= lm_wl_acquire(dir, argv[3], LM_WL_SHARED, 0, &a, &e) == LM_WL_OK;
    ok &= lm_wl_acquire(dir, argv[3], LM_WL_SHARED, 0, &b, &e) == LM_WL_OK;
    if (b) { lm_wl_release(b); b = NULL; }
    ok &= lm_wl_acquire(dir, argv[3], LM_WL_EXCLUSIVE, 0, &b, &e) == LM_WL_BUSY && b == NULL;
    lm_wl_release(a); a = NULL;
    ok &= lm_wl_acquire(dir, argv[3], LM_WL_EXCLUSIVE, 0, &a, &e) == LM_WL_OK;
    ok &= lm_wl_acquire(dir, argv[3], LM_WL_SHARED, 0, &b, &e) == LM_WL_BUSY && b == NULL;
    ok &= lm_wl_check(a, &e) == LM_WL_OK;
    lm_wl_release(a);
    printf("{\"selfconflict\":%d,\"source\":\"%s\"}\n", ok, SOURCE_SHA);
    return ok ? 0 : 1;
  }
  return 64;
}
