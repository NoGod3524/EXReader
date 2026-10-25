/* SPDX-License-Identifier: MIT
 * Named-case reporting shared by every acceptance program: one JSON object per
 * line so the checker can bind each case name to a platform and a status.
 */
#ifndef EXR_DROP_REPORT_H
#define EXR_DROP_REPORT_H
#include <stdio.h>
#include <string.h>

static int report_total, report_passed, report_failed, report_skipped;

static void report_text(char *out, size_t room, const char *text) {
  size_t used = 0;
  if (!room) return;
  while (text && *text && used + 7 < room) {
    unsigned char c = (unsigned char)*text++;
    if (c == '"' || c == '\\') { out[used++] = '\\'; out[used++] = (char)c; }
    else if (c == '\n') { out[used++] = '\\'; out[used++] = 'n'; }
    else if (c == '\r') { out[used++] = '\\'; out[used++] = 'r'; }
    else if (c < 0x20 || c == 0x7F) { out[used++] = '?'; }
    else out[used++] = (char)c;
  }
  out[used] = 0;
}

static void report_emit(const char *name, const char *status, const char *detail) {
  char name_buf[192], detail_buf[512];
  report_text(name_buf, sizeof(name_buf), name);
  report_text(detail_buf, sizeof(detail_buf), detail);
  printf("{\"case\":\"%s\",\"status\":\"%s\",\"detail\":\"%s\"}\n", name_buf, status, detail_buf);
  fflush(stdout);
  report_total++;
  if (strcmp(status, "pass") == 0) report_passed++;
  else if (strcmp(status, "skip") == 0) report_skipped++;
  else report_failed++;
}

static void report_pass(const char *name, const char *detail) { report_emit(name, "pass", detail); }
static void report_skip(const char *name, const char *detail) { report_emit(name, "skip", detail); }
static void report_fail(const char *name, const char *detail) { report_emit(name, "fail", detail); }

static void report_expect(const char *name, int ok, const char *detail) {
  if (ok) report_pass(name, detail);
  else report_fail(name, detail);
}

static int report_summary(const char *platform) {
  printf("{\"case\":\"__summary\",\"platform\":\"%s\",\"total\":%d,\"passed\":%d,\"failed\":%d,\"skipped\":%d}\n",
      platform, report_total, report_passed, report_failed, report_skipped);
  fflush(stdout);
  return report_failed ? 1 : 0;
}
#endif
