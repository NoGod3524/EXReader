/* SPDX-License-Identifier: MIT */
/* Actions diagnostic consumer, not a substitute migration executable.
 * SDK transactions are real. SQLite's public logger only observes; it never
 * supplies a return, swaps a VFS, or accesses exr_library's private structure. */
#include <exreader.h>
#include <sqlite3.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char *phase = "setup";
static unsigned finish_io, finish_read, finish_delete;

static void json_string(FILE *f, const char *s) {
  const unsigned char *p = (const unsigned char *)(s ? s : "");
  fputc('"', f);
  for (; *p; ++p) {
    if (*p == '"' || *p == '\\') { fputc('\\', f); fputc(*p, f); }
    else if (*p < 32 || *p >= 127) fprintf(f, "\\u%04x", (unsigned)*p);
    else fputc(*p, f);
  }
  fputc('"', f);
}
static void error_log(void *unused, int code, const char *message) {
  (void)unused;
  if (!strcmp(phase, "sdk-finish")) {
    if ((code & 255) == SQLITE_IOERR) ++finish_io;
    if (code == SQLITE_IOERR_READ) ++finish_read;
    if (code == SQLITE_IOERR_DELETE) ++finish_delete;
  }
  fputs("{\"phase\":", stderr); json_string(stderr, phase);
  fprintf(stderr, ",\"sqlite_code\":%d,\"message\":", code);
  json_string(stderr, message); fputs("}\n", stderr); fflush(stderr);
}
static int failure(const char *where, const exr_error *e) {
  fprintf(stderr, "consumer setup/transport failure: %s: %s\n", where, e ? e->message : "");
  return 2;
}
static int marker(const char *path) {
  FILE *f = fopen(path, "wb");
  int ok;
  if (!f) return 0;
  ok = fputs("ready\n", f) >= 0;
  return fclose(f) == 0 && ok;
}
int main(int argc, char **argv) {
  exr_library *owner = NULL;
  exr_error error = {0};
  exr_status status;
  int64_t id = 0;
  FILE *report;
  char *temporary;
  static const char text[] = "Original diagnostic fixture text.\n";
  static const char ledger[] = "uncommitted diagnostic ledger, not a mirror receipt";
  if (!getenv("GITHUB_ACTIONS") || strcmp(getenv("GITHUB_ACTIONS"), "true"))
    return failure("Actions only", NULL);
  if (argc != 3 && argc != 5) return failure("arguments", NULL);
  if (sqlite3_config(SQLITE_CONFIG_LOG, error_log, NULL) != SQLITE_OK)
    return failure("logger registration", NULL);
  /* Byte-range refusal must target real ReadFile, not a mapped view. This is
   * an explicitly recorded public SQLite diagnostic configuration, not a
   * claim about every application configuration of the frozen SDK. */
  if (sqlite3_config(SQLITE_CONFIG_MMAP_SIZE, (sqlite3_int64)0, (sqlite3_int64)0) != SQLITE_OK)
    return failure("disable diagnostic mmap", NULL);
  fprintf(stderr, "linked SQLite %s source %s; diagnostic mmap disabled\n",
          sqlite3_libversion(), sqlite3_sourceid());
  if (SQLITE_VERSION_NUMBER != 3054000 || sqlite3_libversion_number() != 3054000 ||
      strcmp(SQLITE_SOURCE_ID, sqlite3_sourceid())) return failure("unexpected SQLite/header identity", NULL);
  if (!strcmp(argv[1], "seed") && argc == 3) {
    status = exr_library_open(argv[2], &owner, &error);
    if (status == EXR_OK)
      status = exr_library_import(owner, EXR_TXT, text, sizeof(text)-1,
                                  "Diagnostic baseline", &id, &error);
    if (owner) exr_library_close(owner);
    return status == EXR_OK ? 0 : failure("seed", &error);
  }
  if (!strcmp(argv[1], "recover") && argc == 3) {
    void *data = NULL;
    size_t size = 0;
    int found = 0;
    phase = "fresh-sdk-recovery";
    status = exr_library_migration_open(argv[2], &owner, &error);
    if (status == EXR_OK)
      status = exr_library_migration_ledger_get(owner, &data, &size, &found, &error);
    exr_free(data);
    if (status == EXR_OK && !found)
      status = exr_library_migration_finish(owner, 0, &error);
    if (owner) exr_library_close(owner);
    /* The diagnostic baseline deliberately had no internal ledger. */
    return status == EXR_OK && !found ? 0 : failure("fresh SDK recovery/baseline ledger", &error);
  }
  if (strcmp(argv[1], "observe") || argc != 5) return failure("mode", NULL);
  status = exr_library_migration_open(argv[2], &owner, &error);
  if (status != EXR_OK) return failure("migration open", &error);
  status = exr_library_migration_ledger_set(owner, ledger, sizeof(ledger)-1, &error);
  if (status != EXR_OK || !marker(argv[3])) {
    exr_library_close(owner); return failure("write/ready", &error);
  }
  if (fgetc(stdin) != 'R') { exr_library_close(owner); return failure("rollback acknowledgement", NULL); }
  phase = "sdk-finish";
  status = exr_library_migration_finish(owner, 0, &error);
  phase = "after-finish";
  temporary = malloc(strlen(argv[4]) + 5);
  if (!temporary) { exr_library_close(owner); return failure("result allocation", NULL); }
  sprintf(temporary, "%s.tmp", argv[4]);
  report = fopen(temporary, "wb");
  if (!report) { free(temporary); exr_library_close(owner); return failure("result file", NULL); }
  fprintf(report, "{\"sdk_status\":%d,\"sdk_ok\":%s,\"message\":", (int)status, status == EXR_OK ? "true" : "false");
  json_string(report, error.message);
  fprintf(report, ",\"finish_io_events\":%u,\"finish_read_events\":%u,\"finish_delete_events\":%u,\"read_error_code\":%d,\"delete_error_code\":%d,\"sqlite_version\":",
          finish_io, finish_read, finish_delete, SQLITE_IOERR_READ, SQLITE_IOERR_DELETE);
  json_string(report, sqlite3_libversion());
  fputs(",\"sqlite_source_id\":", report); json_string(report, sqlite3_sourceid());
  fputs(",\"diagnostic_mmap_disabled\":true}\n", report);
  if (fclose(report) || rename(temporary, argv[4])) {
    free(temporary); exr_library_close(owner); return failure("result flush/publication", NULL);
  }
  free(temporary);
  /* Controller releases the OS fault before this independent close phase.
   * Close-time errors must not be attributed to the finish phase above. */
  if (fgetc(stdin) != 'C') { exr_library_close(owner); return failure("close acknowledgement", NULL); }
  phase = "close-after-fault-release";
  exr_library_close(owner);
  return 0; /* Transport succeeded; the actual SDK status is in the report. */
}
