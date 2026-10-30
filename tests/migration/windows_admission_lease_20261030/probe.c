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
static void report(lm_wl_status s, const lm_wl_error *e, unsigned long long gen) {
  printf("{\"status\":%d,\"native\":%lu,\"generation\":%llu,\"pid\":%lu,\"source\":\"%s\"}\n", (int)s, (unsigned long)e->native, gen, (unsigned long)GetCurrentProcessId(), SOURCE_SHA);
  fflush(stdout);
}
int main(int argc, char **argv) {
  lm_wl_lease *l = NULL; lm_wl_error e = {0, ""}; lm_wl_mode m; WCHAR *dir; lm_wl_status s; char line[64];
  if (argc < 4 || !(dir = wide(argv[2]))) return 64;
  if (!strcmp(argv[1], "hold") && argc == 5 && parse_mode(argv[4], &m)) {
    s = lm_wl_acquire(dir, argv[3], m, 0, &l, &e);
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
    report(s, &e, l ? lm_wl_generation(l) : 0);
    if (l) lm_wl_release(l);
    return s == LM_WL_OK ? 0 : 1;
  }
  if (!strcmp(argv[1], "bump") && argc == 4) {
    unsigned long long g = 0;
    s = lm_wl_acquire(dir, argv[3], LM_WL_EXCLUSIVE, 0, &l, &e);
    if (s == LM_WL_OK) { uint64_t n = 0; s = lm_wl_exclusive_bump(l, &n, &e); g = n; lm_wl_release(l); }
    report(s, &e, g);
    return s == LM_WL_OK ? 0 : 1;
  }
  if (!strcmp(argv[1], "expect") && argc == 5) {
    s = lm_wl_acquire(dir, argv[3], LM_WL_SHARED, 0, &l, &e);
    if (s == LM_WL_OK) { s = lm_wl_require_generation(l, _strtoui64(argv[4], NULL, 10)); report(s, &e, lm_wl_generation(l)); lm_wl_release(l); }
    else report(s, &e, 0);
    return s == LM_WL_OK ? 0 : 1;
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
