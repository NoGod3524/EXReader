/* SPDX-License-Identifier: MIT */
/* Independent installed-package consumer. One short-lived process per command,
   so every command reopens the SDK library and the product catalog. */
#define _CRT_SECURE_NO_WARNINGS
#include <reader_local_downloads.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <process.h>
#else
#include <unistd.h>
#endif

typedef struct {
  const char *kill_at, *cancel_at;
  int cancel, busy_all;
  int64_t hold_id;
  int held;
} probe_state;

/* Deterministic identity and reentrancy probes. */
static int cancel_calls;
static int swap_at;
static const char *swap_from;
static const char *swap_to;
static const char *reenter;
static int reenter_in_busy, reenter_done;
static const char *reenter_key, *reenter_path, *reenter_state;
static const reader_ld_options *reenter_options;

static const char *arg(int argc, char **argv, const char *name) {
  int i;
  for (i = 2; i + 1 < argc; i++) if (!strcmp(argv[i], name)) return argv[i + 1];
  return NULL;
}
static int flag(int argc, char **argv, const char *name) {
  int i;
  for (i = 2; i < argc; i++) if (!strcmp(argv[i], name)) return 1;
  return 0;
}
static int64_t arg_i64(int argc, char **argv, const char *name, int64_t fallback) {
  const char *v = arg(argc, argv, name);
  return v ? (int64_t)strtoll(v, NULL, 10) : fallback;
}

static int parse_format(const char *name, exr_format *format, const char **lower) {
  static const struct { const char *upper, *lower; exr_format format; } table[] = {
    {"TXT", "txt", EXR_TXT}, {"HTML", "html", EXR_HTML}, {"FB2", "fb2", EXR_FB2},
    {"EPUB", "epub", EXR_EPUB}, {"DOCX", "docx", EXR_DOCX}, {"RTF", "rtf", EXR_RTF},
    {"MOBI", "mobi", EXR_MOBI}, {"PDF", "pdf", EXR_PDF}, {"CBZ", "cbz", EXR_CBZ}};
  size_t i;
  for (i = 0; i < sizeof(table) / sizeof(table[0]); i++)
    if (name && !strcmp(name, table[i].upper)) { *format = table[i].format; *lower = table[i].lower; return 0; }
  return -1;
}
static const char *location_kind(exr_format f) {
  return f == EXR_EPUB ? "epub_chapter" : (f == EXR_PDF || f == EXR_CBZ) ? "fixed_page" : "reflow_global";
}

static char *read_all(const char *path, size_t *size) {
  FILE *f = fopen(path, "rb");
  char *data;
  long n;
  if (!f) return NULL;
  fseek(f, 0, SEEK_END); n = ftell(f); fseek(f, 0, SEEK_SET);
  if (n <= 0) { fclose(f); return NULL; }
  data = (char *)malloc((size_t)n);
  if (!data || fread(data, 1, (size_t)n, f) != (size_t)n) { free(data); fclose(f); return NULL; }
  fclose(f);
  *size = (size_t)n;
  return data;
}

static exr_library *open_library(const char *work) {
  char path[1024];
  exr_library *library = NULL;
  exr_error error;
  memset(&error, 0, sizeof(error));
  snprintf(path, sizeof(path), "%s/sdk.db", work);
  if (exr_library_open(path, &library, &error) != EXR_OK) {
    fprintf(stderr, "sdk open failed: %s\n", error.message);
    return NULL;
  }
  return library;
}
static reader_catalog *open_catalog(const char *work) {
  char path[1024];
  reader_catalog *catalog = NULL;
  reader_catalog_error error;
  memset(&error, 0, sizeof(error));
  snprintf(path, sizeof(path), "%s/catalog.db", work);
  if (reader_catalog_open(path, &catalog, &error) != 0) {
    fprintf(stderr, "catalog open failed: %s\n", error.message);
    return NULL;
  }
  return catalog;
}

static void run_reenter(void) {
  reader_ld_result result;
  reader_ld_error error;
  reader_ld_status status;
  if (!reenter || reenter_done) return;
  reenter_done = 1;
  reader_ld_result_init(&result);
  memset(&error, 0, sizeof(error));
  if (!strcmp(reenter, "pending")) {
    reader_ld_pending_info info;
    memset(&info, 0, sizeof(info)); info.struct_size = sizeof(info);
    status = reader_ld_pending(reenter_state, &info, &error);
    printf("REENTER op=pending status=%s pending=%d stage=%s\n",
      reader_ld_status_name(status), info.pending, reader_ld_stage_name(info.stage));
    fflush(stdout);
    return;
  }
  if (!strcmp(reenter, "recover")) status = reader_ld_recover(reenter_options, &result, &error);
  else if (!strcmp(reenter, "reimport"))
    status = reader_ld_reimport(reenter_options, reenter_key, reenter_path, &result, &error);
  else status = reader_ld_remove(reenter_options, reenter_key, &result, &error);
  printf("REENTER op=%s status=%s outcome=%s msg=%s\n", reenter,
    reader_ld_status_name(status), reader_ld_outcome_name(result.outcome),
    status == READER_LD_OK ? "" : error.message);
  fflush(stdout);
}

static void hook(void *context, reader_ld_stage stage) {
  probe_state *state = (probe_state *)context;
  printf("STAGE %s\n", reader_ld_stage_name(stage));
  if (!reenter_in_busy) run_reenter();
  fflush(stdout);
  if (state->kill_at && !strcmp(state->kill_at, reader_ld_stage_name(stage))) {
    printf("KILL %s\n", reader_ld_stage_name(stage));
    fflush(stdout);
    _exit(43); /* real process termination: no destructors, no flush, no cleanup */
  }
  if (state->cancel_at && !strcmp(state->cancel_at, reader_ld_stage_name(stage))) state->cancel = 1;
}
static int busy(void *context, const char *key, int64_t id) {
  probe_state *state = (probe_state *)context;
  (void)key;
  if (reenter_in_busy) run_reenter();
  return state->busy_all || (state->held && id == state->hold_id);
}
static int cancelled(void *context) {
  probe_state *state = (probe_state *)context;
  cancel_calls++;
  if (swap_at && cancel_calls == swap_at && swap_from && swap_to) {
    /* Replace the caller pathname while the module is between reading and
       importing. The bytes that were hashed must still be the bytes stored. */
    remove(swap_to);
    printf("SWAP %s\n", rename(swap_from, swap_to) == 0 ? "ok" : "failed");
    fflush(stdout);
    swap_at = 0;
  }
  return state->cancel;
}

static void print_result(reader_ld_status status, const reader_ld_result *r, const reader_ld_error *e) {
  printf("RESULT status=%s outcome=%s id=%lld removed=%u skipped=%u notes=%u progress=%u backup=%s msg=%s\n",
    reader_ld_status_name(status), reader_ld_outcome_name(r->outcome), (long long)r->sdk_book_id,
    (unsigned)r->copies_removed, (unsigned)r->copies_skipped, (unsigned)r->legacy_notes,
    (unsigned)r->legacy_progress, r->backup_path, status == READER_LD_OK ? "" : e->message);
}

static void make_options(reader_ld_options *o, exr_library *library, reader_catalog *catalog,
    const char *state_dir, probe_state *state, int argc, char **argv) {
  const char *policy = arg(argc, argv, "--policy");
  reader_ld_options_init(o);
  o->library = library; o->catalog = catalog; o->state_dir = state_dir;
  o->legacy_policy = policy && !strcmp(policy, "backup") ? READER_LD_LEGACY_BACKUP : READER_LD_LEGACY_REJECT;
  o->is_busy = busy; o->busy_context = state;
  o->after_stage = hook; o->stage_context = state;
  o->control.cancelled = cancelled; o->control.context = state;
}

static int cmd_init(const char *work) {
  exr_library *library = open_library(work);
  reader_catalog *catalog = open_catalog(work);
  reader_catalog_error ce;
  if (!library || !catalog) return 2;
  exr_library_close(library);
  memset(&ce, 0, sizeof(ce));
  if (reader_catalog_close(&catalog, &ce) != 0) return 2;
  puts("INIT ok");
  return 0;
}

static int cmd_add(const char *work, int argc, char **argv) {
  const char *file = arg(argc, argv, "--file"), *title = arg(argc, argv, "--title"), *sha = arg(argc, argv, "--sha");
  const char *lower = NULL;
  exr_format format;
  int copies = (int)arg_i64(argc, argv, "--copies", 1), i;
  int64_t ids[16];
  exr_library *library;
  exr_error error;
  size_t size = 0;
  char *data = NULL;
  if (!file || !title || !sha || copies < 1 || copies > 16 || parse_format(arg(argc, argv, "--fmt"), &format, &lower)) return 2;
  library = open_library(work);
  if (!library) return 2;
  memset(&error, 0, sizeof(error));
  data = read_all(file, &size);
  if (!data) { exr_library_close(library); return 2; }
  for (i = 0; i < copies; i++) {
    exr_status status;
    if (format == EXR_EPUB || format == EXR_CBZ || format == EXR_PDF)
      status = exr_library_import_file(library, format, file, title, &ids[i], &error);
    else
      status = exr_library_import(library, format, data, size, title, &ids[i], &error);
    if (status != EXR_OK) { fprintf(stderr, "import failed: %s\n", error.message); free(data); exr_library_close(library); return 2; }
  }
  free(data);
  exr_library_close(library);
  if (!flag(argc, argv, "--no-attach")) {
    reader_catalog *catalog = open_catalog(work);
    reader_catalog_error ce;
    reader_catalog_book book;
    char sort_title[256];
    size_t t;
    if (!catalog) return 2;
    memset(&ce, 0, sizeof(ce)); memset(&book, 0, sizeof(book));
    snprintf(sort_title, sizeof(sort_title), "%s", title);
    for (t = 0; sort_title[t]; t++) if (sort_title[t] >= 'A' && sort_title[t] <= 'Z') sort_title[t] = (char)(sort_title[t] + 32);
    book.format = lower; book.sha256 = sha; book.title = title; book.author = "";
    book.sort_title = sort_title; book.location_kind = location_kind(format);
    book.source_bytes = size; book.sdk_book_id = ids[0];
    if (reader_catalog_attach(catalog, &book, &ce) != 0) { fprintf(stderr, "attach failed: %s\n", ce.message); return 2; }
    reader_catalog_close(&catalog, &ce);
  }
  printf("ADD key=%s:%s ids=", lower, sha);
  for (i = 0; i < copies; i++) printf("%s%lld", i ? "," : "", (long long)ids[i]);
  printf("\n");
  return 0;
}

static int cmd_legacy(const char *work, int argc, char **argv) {
  int64_t id = arg_i64(argc, argv, "--id", 0), notes = arg_i64(argc, argv, "--notes", 0), position = arg_i64(argc, argv, "--position", 0), i;
  exr_library *library = open_library(work);
  exr_error error;
  memset(&error, 0, sizeof(error));
  if (!library || id <= 0) return 2;
  for (i = 0; i < notes; i++) {
    exr_note note;
    int64_t note_id = 0;
    memset(&note, 0, sizeof(note));
    note.book_id = id; note.start = 0; note.end = 16; note.text = (char *)"legacy sdk-only note";
    if (exr_library_note(library, &note, &note_id, &error) != EXR_OK) { fprintf(stderr, "note failed: %s\n", error.message); return 2; }
  }
  if (position > 0) {
    exr_book *books = NULL;
    size_t count = 0, n;
    if (exr_library_books(library, NULL, &books, &count, &error) != EXR_OK) return 2;
    for (n = 0; n < count; n++) if (books[n].id == id) {
      books[n].position = (size_t)position;
      if (exr_library_update(library, &books[n], &error) != EXR_OK) { fprintf(stderr, "update failed: %s\n", error.message); return 2; }
    }
    exr_books_free(books, count);
  }
  exr_library_close(library);
  puts("LEGACY ok");
  return 0;
}

static int print_books(exr_library *library, const char *prefix) {
  exr_book *books = NULL;
  size_t count = 0, i;
  exr_error error;
  memset(&error, 0, sizeof(error));
  if (exr_library_books(library, NULL, &books, &count, &error) != EXR_OK) return 2;
  for (i = 0; i < count; i++) {
    exr_note *notes = NULL;
    size_t note_count = 0;
    exr_source source;
    unsigned long long size = 0;
    memset(&source, 0, sizeof(source));
    if (exr_library_source(library, books[i].id, &source, &error) == EXR_OK) {
      size = source.size;
      if (source.release) source.release(source.context);
    }
    if (books[i].format != EXR_PDF && books[i].format != EXR_CBZ && books[i].format != EXR_EPUB &&
        exr_library_notes(library, books[i].id, &notes, &note_count, &error) == EXR_OK) exr_notes_free(notes, note_count);
    printf("%s id=%lld format=%d size=%llu notes=%u position=%u\n", prefix, (long long)books[i].id,
      (int)books[i].format, size, (unsigned)note_count, (unsigned)books[i].position);
  }
  exr_books_free(books, count);
  return 0;
}

static int cmd_list(const char *work) {
  exr_library *library = open_library(work);
  int rc;
  if (!library) return 2;
  rc = print_books(library, "BOOK");
  exr_library_close(library);
  return rc;
}

static int cmd_backup_open(const char *path) {
  exr_library *library = NULL;
  exr_error error;
  int rc;
  memset(&error, 0, sizeof(error));
  if (exr_library_open(path, &library, &error) != EXR_OK) return 2;
  rc = print_books(library, "BACKUP");
  exr_library_close(library);
  return rc;
}

static int cmd_dump(const char *work, int argc, char **argv) {
  int64_t id = arg_i64(argc, argv, "--id", 0);
  const char *out = arg(argc, argv, "--out");
  exr_library *library = open_library(work);
  exr_source source;
  exr_error error;
  FILE *f;
  unsigned char *buffer;
  uint64_t offset = 0;
  memset(&error, 0, sizeof(error)); memset(&source, 0, sizeof(source));
  if (!library || id <= 0 || !out) return 2;
  if (exr_library_source(library, id, &source, &error) != EXR_OK) {
    printf("DUMP id=%lld status=missing\n", (long long)id);
    exr_library_close(library);
    return 0;
  }
  f = fopen(out, "wb");
  buffer = (unsigned char *)malloc(65536);
  if (!f || !buffer) return 2;
  while (offset < source.size) {
    size_t want = source.size - offset > 65536 ? 65536 : (size_t)(source.size - offset);
    size_t got = source.read_at(source.context, offset, buffer, want);
    if (!got) { printf("DUMP id=%lld status=short\n", (long long)id); return 1; }
    fwrite(buffer, 1, got, f);
    offset += got;
  }
  fclose(f); free(buffer);
  if (source.release) source.release(source.context);
  exr_library_close(library);
  printf("DUMP id=%lld status=ok bytes=%llu\n", (long long)id, (unsigned long long)offset);
  return 0;
}

typedef struct { int64_t id; int deleted; int found; } meta_out;
static int meta_visit(void *context, const reader_catalog_row *row) {
  meta_out *m = (meta_out *)context;
  m->id = row->sdk_book_id; m->deleted = row->deleted; m->found = 1;
  return 0;
}
static int cmd_catalog(const char *work, int argc, char **argv) {
  const char *key = arg(argc, argv, "--key");
  reader_catalog *catalog = open_catalog(work);
  reader_catalog_error ce;
  meta_out m;
  int found = 0, present = 0;
  memset(&m, 0, sizeof(m)); memset(&ce, 0, sizeof(ce));
  if (!catalog || !key) return 2;
  if (reader_catalog_metadata(catalog, key, meta_visit, &m, &found, &ce) != 0) return 2;
  if (found && m.id > 0 && reader_catalog_has_local(catalog, m.id, &present, &ce) != 0) return 2;
  printf("CATALOG found=%d local=%lld mapped=%d deleted=%d\n", found, (long long)(found ? m.id : 0), present, m.deleted);
  reader_catalog_close(&catalog, &ce);
  return 0;
}

static int cmd_pending(const char *work) {
  char state_dir[1024];
  reader_ld_pending_info info;
  reader_ld_error error;
  reader_ld_status status;
  memset(&info, 0, sizeof(info)); info.struct_size = sizeof(info);
  snprintf(state_dir, sizeof(state_dir), "%s/state", work);
  status = reader_ld_pending(state_dir, &info, &error);
  printf("PENDING status=%s pending=%d stage=%s key=%s id=%lld copies=%u\n", reader_ld_status_name(status),
    info.pending, reader_ld_stage_name(info.stage), info.book_key, (long long)info.sdk_book_id, (unsigned)info.copies);
  return 0;
}

static int cmd_remove(const char *work, int argc, char **argv, int recover, int reimport) {
  char state_dir[1024];
  probe_state state;
  reader_ld_options options;
  reader_ld_result result;
  reader_ld_error error;
  reader_ld_status status;
  exr_library *library;
  reader_catalog *catalog;
  exr_source held;
  const char *key = arg(argc, argv, "--key");
  int64_t hold = arg_i64(argc, argv, "--hold", 0);
  reader_catalog_error ce;
  memset(&state, 0, sizeof(state)); memset(&held, 0, sizeof(held)); memset(&ce, 0, sizeof(ce));
  state.kill_at = arg(argc, argv, "--kill-at");
  state.cancel_at = arg(argc, argv, "--cancel-at");
  state.busy_all = flag(argc, argv, "--busy-all");
  {
    const char *at = arg(argc, argv, "--swap-at");
    swap_at = at ? atoi(at) : 0;
    swap_from = arg(argc, argv, "--swap-from");
    swap_to = arg(argc, argv, "--swap-to");
    cancel_calls = 0;
    reenter = arg(argc, argv, "--reenter");
    reenter_in_busy = flag(argc, argv, "--reenter-in-busy");
    reenter_done = 0;
    reenter_key = key;
    reenter_path = arg(argc, argv, "--file");
  }
  snprintf(state_dir, sizeof(state_dir), "%s/state", work);
  library = open_library(work);
  catalog = open_catalog(work);
  if (!library || !catalog) return 2;
  make_options(&options, library, catalog, state_dir, &state, argc, argv);
  reenter_options = &options;
  reenter_state = state_dir;
  reader_ld_result_init(&result);
  memset(&error, 0, sizeof(error));
  if (hold > 0) {
    exr_error se;
    memset(&se, 0, sizeof(se));
    if (exr_library_source(library, hold, &held, &se) != EXR_OK) return 2;
    state.hold_id = hold; state.held = 1;
  }
  if (recover) status = reader_ld_recover(&options, &result, &error);
  else if (reimport) status = reader_ld_reimport(&options, key, arg(argc, argv, "--file"), &result, &error);
  else status = reader_ld_remove(&options, key, &result, &error);
  print_result(status, &result, &error);
  if (hold > 0) {
    unsigned char probe_bytes[16];
    size_t want = held.size < sizeof(probe_bytes) ? (size_t)held.size : sizeof(probe_bytes);
    size_t got = want ? held.read_at(held.context, 0, probe_bytes, want) : 0;
    printf("HELD readable=%d size=%llu\n", got == want && want > 0, (unsigned long long)held.size);
    /* Contract: release the source on the SDK owner, then ask again. */
    if (held.release) held.release(held.context);
    state.held = 0;
    reader_ld_result_init(&result);
    memset(&error, 0, sizeof(error));
    status = reader_ld_remove(&options, key, &result, &error);
    printf("AFTER_RELEASE ");
    print_result(status, &result, &error);
  }
  exr_library_close(library);
  reader_catalog_close(&catalog, &ce);
  return 0;
}

int main(int argc, char **argv) {
  const char *work;
  if (argc < 3) return 2;
  work = arg(argc, argv, "--work");
  if (!strcmp(argv[1], "backup-open")) return cmd_backup_open(arg(argc, argv, "--path"));
  if (!work) return 2;
  if (!strcmp(argv[1], "init")) return cmd_init(work);
  if (!strcmp(argv[1], "add")) return cmd_add(work, argc, argv);
  if (!strcmp(argv[1], "legacy")) return cmd_legacy(work, argc, argv);
  if (!strcmp(argv[1], "list")) return cmd_list(work);
  if (!strcmp(argv[1], "dump")) return cmd_dump(work, argc, argv);
  if (!strcmp(argv[1], "catalog")) return cmd_catalog(work, argc, argv);
  if (!strcmp(argv[1], "pending")) return cmd_pending(work);
  if (!strcmp(argv[1], "remove")) return cmd_remove(work, argc, argv, 0, 0);
  if (!strcmp(argv[1], "recover")) return cmd_remove(work, argc, argv, 1, 0);
  if (!strcmp(argv[1], "reimport")) return cmd_remove(work, argc, argv, 0, 1);
  return 2;
}
