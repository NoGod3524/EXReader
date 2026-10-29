/* SPDX-License-Identifier: MIT */
#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#endif
#ifdef __APPLE__
#define _DARWIN_C_SOURCE
#endif
#include "lm_ledger.h"
#ifdef EXR_MIGRATION_TX_CANDIDATE
#include "lm_mirror.h"
#endif
#ifdef EXR_MIGRATION_RECOVERY_CANDIDATE
#include "lm_recovery.h"
static lm_recovery *g_recovery;
#define LM_RECOVERY_VERSION "recovery-existing-v1"
#endif
#include <sqlite3.h>
#include <ctype.h>
#include <errno.h>
#include <math.h>
#include <signal.h>
#include <stdarg.h>
#include <time.h>
#ifdef _WIN32
#include <windows.h>
#include <process.h>
#else
#include <unistd.h>
#endif

typedef enum { O_NONE = 0, O_SUCCESS, O_REJECTED, O_FAILED, O_CANCELLED, O_BUSY, O_INCONSISTENT, O_DRYRUN } outcome;
static const char *const OUTCOME[] = {"unfinished", "success", "rejected", "failed", "cancelled", "busy", "inconsistent", "dry-run"};
static const int EXIT_CODE[] = {3, 0, 2, 3, 4, 5, 6, 0};
enum { S_INFO, S_WARNING, S_APPROX, S_UNLOCATED, S_DROPPED, S_UNSUPPORTED, S_CONFLICT, S_COUNT };
static const char *const SEVERITY[S_COUNT] = {"info", "warning", "approximate", "unlocated", "dropped", "unsupported", "conflict"};
#ifdef EXR_MIGRATION_TX_CANDIDATE
/* Process-local knowledge only: these values are not durable commit receipts. */
typedef enum { C_NOT_ATTEMPTED = 0, C_NOT_COMMITTED, C_COMMITTED, C_UNKNOWN } commit_knowledge;
static const char *const COMMIT_KNOWLEDGE[] = {"not-attempted", "not-committed", "committed", "unknown"};
#endif

static volatile sig_atomic_t g_cancel = 0;
static void on_signal(int sig) { (void)sig; g_cancel = 1; }

typedef struct {
  const char *cmd, *pack_path, *target, *report_path;
#ifdef EXR_MIGRATION_RECOVERY_CANDIDATE
  lm_recovery *recovery;
  const char *recovery_font;
  char *read_view;
  int recovery_retry, recovery_gate_ok;
#endif
  int allow_partial, dry_run, break_lock, cancel_at, inject_at;
  char inject[32];
  char run[24];
  char *stage, *lock, *sidecar, *pre, *sidecar_tmp;
  outcome out;
  char code[48], message[512];
  lm_pack pack;
  lm_ledger ledger;
  exr_library *lib;
  exr_error err;
  exr_control control;
  lm_sb entries, items, notes;
  size_t entry_n, item_n, note_n;
  unsigned sev[S_COUNT];
  unsigned books_expected, books_created, books_existing, books_merged, books_skipped, books_audio;
  unsigned notes_expected, notes_created, notes_existing, notes_unlocated, notes_skipped;
  unsigned imports, reads;
  uint64_t units, max_book_bytes, bytes_imported;
  char target_sha[65], sidecar_sha[65];
  int target_existed, sidecar_existed, rolled_back, lock_held, target_version;
#ifdef EXR_MIGRATION_TX_CANDIDATE
  commit_knowledge target_commit, private_stage_commit;
  lm_mirror_intent mirror_intent;
  lm_mirror_file mirror_before, owner_before, pending_snapshot, sidecar_tmp_file;
  char *pending;
  char *mirror_preimage;
  const char *mirror_state;
  int pending_retained, sidecar_tmp_owned, mirror_preimage_owned;
  lm_mirror_file lock_snapshot;
  int recovery_barrier, lock_retained, rollback_requested, rollback_status_valid;
  exr_status rollback_status;
#endif
  const char *pre_state, *stage_state;
  lm_hm pack_books;
  size_t *seen_a, *seen_b;
} ctx;

/* ---------- reporting ---------- */
static void fail(ctx *c, outcome o, const char *code, const char *fmt, ...) {
  va_list ap;
  if (c->out != O_NONE) return;
  c->out = o;
  snprintf(c->code, sizeof(c->code), "%s", code);
  va_start(ap, fmt);
  vsnprintf(c->message, sizeof(c->message), fmt, ap);
  va_end(ap);
}
static void entry(ctx *c, int sev, const char *code, const char *scope, const char *legacy, const char *fmt, ...) {
  char message[400];
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(message, sizeof(message), fmt, ap);
  va_end(ap);
  c->sev[sev]++;
  if (c->entry_n++) lm_sb_str(&c->entries, ",");
  lm_sb_fmt(&c->entries, "{\"severity\":\"%s\",\"code\":\"%s\",\"scope\":\"%s\",\"legacy_id\":", SEVERITY[sev], code, scope);
  if (legacy) lm_sb_json(&c->entries, legacy, strlen(legacy)); else lm_sb_str(&c->entries, "null");
  lm_sb_str(&c->entries, ",\"message\":");
  lm_sb_json(&c->entries, message, strlen(message));
  lm_sb_str(&c->entries, "}");
}
static int cancel_cb(void *context) {
  ctx *c = context;
  return g_cancel || (c->cancel_at >= 0 && c->units >= (uint64_t)c->cancel_at);
}
static int tick(ctx *c) {
  if (c->out != O_NONE) return 0;
  if (cancel_cb(c)) { fail(c, O_CANCELLED, "cancelled", "cancelled after %llu work units", (unsigned long long)c->units); return 0; }
  c->units++;
  return 1;
}
static int injected(ctx *c, const char *name, unsigned count) {
#ifdef EXR_MIGRATION_RECOVERY_CANDIDATE
  /* Recovery owns private, bounded rendezvous; old external marker hooks are
     unreachable, while actual importer data faults remain available. */
  if(strstr(name,"pause")) return 0;
#endif
  return c->inject[0] && !strcmp(c->inject, name) && (c->inject_at < 0 || (unsigned)c->inject_at == count);
}
static void sdk_fail(ctx *c, const char *what) {
  outcome o = c->err.code == EXR_CANCELLED ? O_CANCELLED : O_FAILED;
  fail(c, o, o == O_CANCELLED ? "cancelled" : "sdk-error", "%s: %s (status %d)", what, c->err.message, (int)c->err.code);
}

/* ---------- small helpers ---------- */
static void trim(const char *s, size_t n, const char **out, size_t *len) {
  size_t a = 0, b = n;
  while (a < b && (s[a] == ' ' || s[a] == '\t' || s[a] == '\n' || s[a] == '\r')) a++;
  while (b > a && (s[b - 1] == ' ' || s[b - 1] == '\t' || s[b - 1] == '\n' || s[b - 1] == '\r')) b--;
  *out = s + a;
  *len = b - a;
}
static char *path_join(const char *base, const char *suffix) {
  char *p = lm_xalloc(strlen(base) + strlen(suffix) + 1);
  strcpy(p, base);
  strcat(p, suffix);
  return p;
}
static int in_list(const char *name, const char *const *list) {
  for (; *list; list++)
    if (!strcmp(name, *list)) return 1;
  return 0;
}
static const char *const BOOK_FIELDS[] = {"id", "title", "author", "tags", "favorite", "status", "cover", "format", "filename", "size", "modified", "added", "progress", "cfi", "page", "seconds", "lastRead", "audio", NULL};
static const char *const NOTE_FIELDS[] = {"id", "bookId", "quote", "note", "value", "page", "seconds", "rects", "bookmark", "created", NULL};
static const char *const AUDIO_EXT[] = {"mp3", "m4a", "m4b", "ogg", "opus", "wav", "flac", "aac", NULL};
static void unknown_fields(ctx *c, const jv *record, const char *const *known, const char *scope, const char *legacy) {
  lm_sb names;
  size_t i;
  unsigned count = 0;
  lm_sb_init(&names);
  for (i = 0; i < record->n; i++)
    if (!in_list(record->keys[i], known)) {
      if (count++) lm_sb_str(&names, ",");
      lm_sb_str(&names, record->keys[i]);
    }
  if (count) entry(c, S_INFO, "unknown-field", scope, legacy, "unrecognised legacy fields kept verbatim in the ledger: %s", names.p ? names.p : "");
  lm_sb_free(&names);
}
static char *record_json(const jv *record, int skip_cover) {
  lm_sb b;
  size_t i;
  char *out;
  lm_sb_init(&b);
  if (!skip_cover) lm_json_write(&b, record);
  else {
    unsigned n = 0;
    lm_sb_str(&b, "{");
    for (i = 0; i < record->n; i++) {
      if (!strcmp(record->keys[i], "cover")) continue;
      if (n++) lm_sb_str(&b, ",");
      lm_sb_json(&b, record->keys[i], strlen(record->keys[i]));
      lm_sb_str(&b, ":");
      lm_json_write(&b, record->items[i]);
    }
    lm_sb_str(&b, "}");
  }
  out = lm_xdup(b.p ? b.p : "{}");
  lm_sb_free(&b);
  return out;
}

/* ---------- text location ---------- */
static size_t ws_at(const char *s, size_t n, size_t i) {
  unsigned char ch = (unsigned char)s[i];
  if (ch == ' ' || ch == '\t' || ch == '\n' || ch == '\r' || ch == '\f' || ch == '\v') return 1;
  if (ch == 0xc2 && i + 1 < n && (unsigned char)s[i + 1] == 0xa0) return 2;
  return 0;
}
/* Whitespace runs compare equal; returns the end offset or 0 on mismatch. */
static size_t match_at(const char *h, size_t hn, size_t i, const char *q, size_t qn) {
  size_t a = i, b = 0, w;
  while (b < qn) {
    if ((w = ws_at(q, qn, b)) != 0) {
      if (!ws_at(h, hn, a)) return 0;
      while (a < hn && (w = ws_at(h, hn, a)) != 0) a += w;
      while (b < qn && (w = ws_at(q, qn, b)) != 0) b += w;
      continue;
    }
    if (a >= hn || h[a] != q[b]) return 0;
    a++; b++;
  }
  return a;
}
#define MATCH_CAP 4096u
static size_t find_all(ctx *c, const char *h, size_t hn, const char *q, size_t qn) {
  size_t i, total = 0, end;
  if (!qn) return 0;
  for (i = 0; i < hn; i++) {
    if (h[i] != q[0]) continue;
    end = match_at(h, hn, i, q, qn);
    if (!end) continue;
    if (total < MATCH_CAP) { c->seen_a[total] = i; c->seen_b[total] = end; }
    total++;
  }
  return total;
}

/* ---------- CFI mapping ---------- */
typedef struct { int kind; size_t offset, rs, re; } cfi_loc; /* 0 none, 1 exact, 2 element start, 3 region only */
static int utf16_to_byte(const char *t, size_t n, size_t units, size_t *byte) {
  size_t i = 0, u = 0;
  while (u < units) {
    unsigned char ch;
    size_t len;
    if (i >= n) return 0;
    ch = (unsigned char)t[i];
    len = ch < 0x80 ? 1 : ch < 0xe0 ? 2 : ch < 0xf0 ? 3 : 4;
    u += len == 4 ? 2 : 1;
    i += len;
  }
  if (u != units) return 0;
  *byte = i;
  return 1;
}
static void point_loc(const exr_node *nodes, size_t count, const char *text, size_t text_size, const exr_cfi_point *pt, cfi_loc *loc) {
  const exr_node *node;
  memset(loc, 0, sizeof(*loc));
  if (pt->node >= count) return;
  node = &nodes[pt->node];
  if (node->start > node->end || node->end > text_size) return;
  loc->rs = node->start;
  loc->re = node->end;
  if (node->kind == EXR_NODE_TEXT && node->text && pt->offset != SIZE_MAX) {
    size_t length = strlen(node->text), byte;
    if (node->end - node->start == length && !memcmp(text + node->start, node->text, length) && utf16_to_byte(node->text, length, pt->offset, &byte)) {
      loc->kind = 1;
      loc->offset = node->start + byte;
    } else loc->kind = 3;
  } else if (pt->offset == SIZE_MAX) {
    loc->kind = 2;
    loc->offset = node->start;
  } else loc->kind = 3;
}
static int cfi_locate(const exr_document *doc, const char *cfi, const char *text, size_t text_size, cfi_loc *a, cfi_loc *b, int *is_range) {
  exr_error er;
  exr_cfi_range range;
  exr_cfi_point point;
  size_t chapter, count;
  const exr_node *nodes = exr_document_nodes(doc, &count);
  memset(a, 0, sizeof(*a));
  memset(b, 0, sizeof(*b));
  *is_range = 0;
  if (!cfi || strncmp(cfi, "epubcfi(", 8)) return 0;
  memset(&er, 0, sizeof(er));
  if (strchr(cfi, ',') && exr_document_cfi_range_resolve(doc, cfi, NULL, &range, &er) == EXR_OK) {
    point_loc(nodes, count, text, text_size, &range.start, a);
    point_loc(nodes, count, text, text_size, &range.end, b);
    *is_range = 1;
    return a->kind != 0;
  }
  if (exr_document_cfi_resolve(doc, cfi, NULL, &chapter, &point, &er) != EXR_OK) return 0;
  point_loc(nodes, count, text, text_size, &point, a);
  return a->kind != 0;
}

/* ---------- per-book state ---------- */
typedef struct { size_t start, end, page; char *text; int64_t id; } seen_note;
typedef struct {
  exr_document *doc;
  const char *text;
  size_t text_size;
  exr_fixed_document *fixed;
  size_t pages;
  seen_note *seen;
  size_t seen_n, seen_cap;
  exr_audio_bookmark *marks;
  size_t mark_n;
} bctx;
static void seen_add(bctx *b, size_t page, size_t start, size_t end, const char *text, int64_t id) {
  if (b->seen_n == b->seen_cap) {
    size_t cap = b->seen_cap ? b->seen_cap * 2 : 16;
    seen_note *grown = lm_xalloc(cap * sizeof(*grown));
    if (b->seen_n) memcpy(grown, b->seen, b->seen_n * sizeof(*grown));
    free(b->seen);
    b->seen = grown;
    b->seen_cap = cap;
  }
  b->seen[b->seen_n].page = page;
  b->seen[b->seen_n].start = start;
  b->seen[b->seen_n].end = end;
  b->seen[b->seen_n].text = lm_xdup(text);
  b->seen[b->seen_n].id = id;
  b->seen_n++;
}
static seen_note *seen_find(bctx *b, size_t page, size_t start, size_t end, const char *text) {
  size_t i;
  for (i = 0; i < b->seen_n; i++)
    if (b->seen[i].page == page && b->seen[i].start == start && b->seen[i].end == end && !strcmp(b->seen[i].text, text)) return &b->seen[i];
  return NULL;
}
static seen_note *seen_by_id(bctx *b, int64_t id) {
  size_t i;
  for (i = 0; i < b->seen_n; i++)
    if (b->seen[i].id == id) return &b->seen[i];
  return NULL;
}
static void bctx_free(bctx *b) {
  size_t i;
  exr_document_free(b->doc);
  exr_fixed_free(b->fixed);
  for (i = 0; i < b->seen_n; i++) free(b->seen[i].text);
  free(b->seen);
  exr_audio_bookmarks_free(b->marks, b->mark_n);
  memset(b, 0, sizeof(*b));
}
static int bctx_load(ctx *c, bctx *b, const lm_book *mb) {
  size_t i, n;
  if (mb->kind == K_REFLOW) {
    exr_note *notes = NULL;
    if (exr_library_document(c->lib, mb->book_id, &b->doc, &c->err) != EXR_OK) { sdk_fail(c, "opening stored document"); return 0; }
    b->text = exr_document_text(b->doc, &b->text_size);
    if (exr_library_notes(c->lib, mb->book_id, &notes, &n, &c->err) != EXR_OK) { sdk_fail(c, "listing notes"); return 0; }
    for (i = 0; i < n; i++) seen_add(b, 0, notes[i].start, notes[i].end, notes[i].text, notes[i].id);
    exr_notes_free(notes, n);
  } else if (mb->kind == K_FIXED) {
    exr_fixed_note *notes = NULL;
    const exr_fixed_page *pages;
    if (exr_library_fixed(c->lib, mb->book_id, NULL, &b->fixed, &c->err) != EXR_OK) { sdk_fail(c, "opening stored fixed document"); return 0; }
    pages = exr_fixed_pages(b->fixed, &b->pages);
    (void)pages;
    if (exr_library_fixed_notes(c->lib, mb->book_id, &notes, &n, &c->err) != EXR_OK) { sdk_fail(c, "listing fixed notes"); return 0; }
    for (i = 0; i < n; i++) seen_add(b, notes[i].page, notes[i].start, notes[i].end, notes[i].text, notes[i].id);
    exr_fixed_notes_free(notes, n);
  } else {
    if (exr_library_audio_bookmarks(c->lib, mb->audio_id, &b->marks, &b->mark_n, &c->err) != EXR_OK) { sdk_fail(c, "listing audio bookmarks"); return 0; }
  }
  return 1;
}

/* ---------- note migration ---------- */
static void note_item(ctx *c, const char *legacy, const char *book, const char *kind, const char *status, int64_t new_id, const char *method, const char *reason) {
  if (c->note_n++) lm_sb_str(&c->notes, ",");
  lm_sb_str(&c->notes, "{\"legacy_id\":");
  lm_sb_json(&c->notes, legacy, strlen(legacy));
  lm_sb_str(&c->notes, ",\"book\":");
  lm_sb_json(&c->notes, book, strlen(book));
  lm_sb_fmt(&c->notes, ",\"kind\":\"%s\",\"status\":\"%s\",\"new_id\":", kind, status);
  if (new_id > 0) lm_sb_fmt(&c->notes, "%lld", (long long)new_id); else lm_sb_str(&c->notes, "null");
  lm_sb_str(&c->notes, ",\"method\":");
  if (method) lm_sb_json(&c->notes, method, strlen(method)); else lm_sb_str(&c->notes, "null");
  lm_sb_str(&c->notes, ",\"reason\":");
  if (reason) lm_sb_json(&c->notes, reason, strlen(reason)); else lm_sb_str(&c->notes, "null");
  lm_sb_str(&c->notes, "}");
}
static void set_str(char **slot, const char *value) {
  free(*slot);
  *slot = value ? lm_xdup(value) : NULL;
}
static const char *kind_name(int kind) { return kind == K_REFLOW ? "reflow" : kind == K_FIXED ? "fixed" : "audio"; }

typedef struct { int located; size_t s, e; const char *method, *reason; } location;

static location locate_reflow(ctx *c, bctx *b, const char *legacy, const char *quote, size_t qn, const char *cfi, int bookmark) {
  location r = {0, 0, 0, NULL, NULL};
  cfi_loc a, e;
  int is_range = 0, have = cfi_locate(b->doc, cfi, b->text, b->text_size, &a, &e, &is_range);
  size_t total, i, inside = 0, pick = 0;
  if (cfi && !have) entry(c, S_WARNING, "cfi-unresolved", "note", legacy, "the CFI does not resolve in the migrated document; falling back to the quoted text");
  if (bookmark) {
    if (have && (a.kind == 1 || a.kind == 2)) {
      r.located = 1; r.s = r.e = a.offset;
      r.method = a.kind == 1 ? "cfi-offset" : "cfi-element-start";
    } else r.reason = cfi ? "bookmark-cfi-unresolved" : "bookmark-without-cfi";
    return r;
  }
  if (have && is_range && a.kind == 1 && e.kind == 1 && a.offset < e.offset) {
    if (!qn) { r.located = 1; r.s = a.offset; r.e = e.offset; r.method = "cfi-range"; return r; }
    if (match_at(b->text, b->text_size, a.offset, quote, qn) == e.offset) { r.located = 1; r.s = a.offset; r.e = e.offset; r.method = "cfi+quote"; return r; }
    entry(c, S_WARNING, "cfi-quote-mismatch", "note", legacy, "the CFI range does not contain the stored quote; using the quote alone");
  }
  if (!qn) { r.reason = "no-quote-and-no-resolvable-range"; return r; }
  total = find_all(c, b->text, b->text_size, quote, qn);
  if (total == 0) { r.reason = "quote-not-found"; return r; }
  if (total == 1) { r.located = 1; r.s = c->seen_a[0]; r.e = c->seen_b[0]; r.method = "quote-unique"; return r; }
  if (total > MATCH_CAP) { r.reason = "quote-ambiguous-too-many-matches"; return r; }
  if (have && a.rs < a.re) {
    for (i = 0; i < total; i++)
      if (c->seen_a[i] >= a.rs && c->seen_b[i] <= a.re) { inside++; pick = i; }
    if (inside == 1) { r.located = 1; r.s = c->seen_a[pick]; r.e = c->seen_b[pick]; r.method = "quote-in-cfi-node"; return r; }
  }
  r.reason = "quote-ambiguous";
  return r;
}
static location locate_fixed(ctx *c, const char *text, size_t tn, const char *quote, size_t qn) {
  location r = {0, 0, 0, NULL, NULL};
  size_t total;
  if (!qn) { r.reason = "no-quote"; return r; }
  total = find_all(c, text, tn, quote, qn);
  if (total == 0) r.reason = "quote-not-found";
  else if (total > 1) r.reason = "quote-ambiguous";
  else { r.located = 1; r.s = c->seen_a[0]; r.e = c->seen_b[0]; r.method = "quote-unique"; }
  return r;
}

static void process_note(ctx *c, bctx *b, lm_book *mb, const jv *jn) {
  const jv *rec = lm_get(jn, "record"), *v;
  const char *id = lm_get_str(jn, "legacy_id"), *quote_raw, *comment, *cfi;
  const char *quote;
  size_t qn;
  char fp[65];
  lm_note *ln;
  lm_sb fb;
  int bookmark = 0, existed;
  uint64_t page = 0;
  double seconds = -1;
  location loc = {0, 0, 0, NULL, NULL};
  size_t page0 = 0;
  const char *status = "created";
  int64_t new_id = 0;

  unknown_fields(c, rec, NOTE_FIELDS, "note", id);
  quote_raw = lm_get_str(rec, "quote");
  comment = lm_get_str(rec, "note");
  if (!quote_raw || (lm_get(rec, "note") && !comment)) {
    entry(c, S_UNSUPPORTED, "invalid-note-record", "note", id, "quote/note must be strings; the note cannot be interpreted");
    c->notes_skipped++;
    note_item(c, id, mb->legacy, kind_name(mb->kind), "skipped", 0, NULL, "invalid-note-record");
    return;
  }
  if (!comment) { comment = ""; entry(c, S_INFO, "missing-field", "note", id, "note text absent; empty comment used"); }
  v = lm_get(rec, "bookmark");
  if (v && v->t == J_BOOL) bookmark = v->b;
  else if (v) entry(c, S_WARNING, "wrong-type", "note", id, "bookmark is not boolean; treated as false");
  cfi = lm_get_str(rec, "value");
  v = lm_get(rec, "page");
  if (v && (!lm_json_uint(v, &page) || page < 1)) { entry(c, S_WARNING, "wrong-type", "note", id, "page is not a one-based integer; ignored"); page = 0; }
  v = lm_get(rec, "seconds");
  if (v && v->t == J_NUM && v->num >= 0 && isfinite(v->num)) seconds = v->num;
  else if (v) entry(c, S_WARNING, "wrong-type", "note", id, "seconds is not a non-negative number; ignored");
  trim(quote_raw, strlen(quote_raw), &quote, &qn);

  lm_sb_init(&fb);
  lm_json_write(&fb, rec);
  lm_sha_bytes(fb.p ? fb.p : "", fb.n, fp);
  lm_sb_free(&fb);
  existed = lm_ledger_note(&c->ledger, id, 0) != NULL;
  ln = lm_ledger_note(&c->ledger, id, 1);
  if (existed && strcmp(ln->fp, fp)) {
    entry(c, S_CONFLICT, "note-changed", "note", id, "legacy note id was migrated earlier with different content; the earlier result is kept (rule: same legacy id, changed content => conflict)");
    c->notes_skipped++;
    note_item(c, id, mb->legacy, kind_name(mb->kind), "skipped", ln->new_id, NULL, "note-changed");
    ln->touched = 1;
    return;
  }
  ln->touched = 1;
  if (existed && !ln->located) {
    c->notes_unlocated++;
    note_item(c, id, mb->legacy, kind_name(mb->kind), "unlocated", 0, ln->method, ln->reason);
    return;
  }
  if (existed && ln->new_id > 0) {
    int present = 1;
    if (mb->kind == K_REFLOW || mb->kind == K_FIXED) present = seen_by_id(b, ln->new_id) != NULL;
    if (present) {
      c->notes_existing++;
      note_item(c, id, mb->legacy, kind_name(mb->kind), "existing", ln->new_id, "ledger", NULL);
      return;
    }
    entry(c, S_INFO, "note-recreated", "note", id, "the ledger entry pointed at a note that no longer exists; recreating it");
  }
  strcpy(ln->fp, fp);
  set_str(&ln->book_legacy, mb->legacy);
  set_str(&ln->retained, NULL);
  ln->retained = record_json(rec, 0);
  ln->kind = mb->kind;
  ln->located = 0;
  ln->new_id = 0;
  {
    const jv *rects = lm_get(rec, "rects");
    if (rects && mb->kind != K_AUDIO) entry(c, S_DROPPED, "rects-not-converted", "note", id, "legacy normalised rectangles have no library slot; geometry is re-derived from text and the originals stay in the ledger");
  }

  if (mb->kind == K_AUDIO) {
    exr_audio_bookmark mark;
    size_t i;
    if (seconds < 0) {
      loc.reason = "audio-note-without-seconds";
    } else {
      if (seconds * 1000.0 + 0.5 >= 9223372036854775808.0) {
        fail(c, O_REJECTED, "audio-position-limit", "audio bookmark exceeds the stored checkpoint range"); return;
      }
      uint64_t ms = (uint64_t)floor(seconds * 1000.0 + 0.5);
      const char *label = comment[0] ? comment : quote;
      char *copy = lm_xdup(label);
      char *track = lm_xdup(mb->legacy);
      memset(&mark, 0, sizeof(mark));
      mark.label = copy;
      mark.position.track_id = track;
      mark.position.offset_ms = ms;
      mark.position.rate = 1.0;
      for (i = 0; i < b->mark_n; i++)
        if (b->marks[i].position.offset_ms == ms && !strcmp(b->marks[i].label, label) && !strcmp(b->marks[i].position.track_id, track)) { new_id = b->marks[i].id; status = "existing"; break; }
      if (!new_id) {
        if (exr_library_audio_bookmark(c->lib, mb->audio_id, &mark, &new_id, &c->err) != EXR_OK) { free(copy); free(track); sdk_fail(c, "writing audio bookmark"); return; }
        status = "created";
      }
      ln->start = (size_t)ms;
      loc.located = 1;
      loc.method = "audio-seconds";
      free(copy); free(track);
    }
  } else if (mb->kind == K_FIXED) {
    if (page < 1) loc.reason = "fixed-note-without-page";
    else if (page > b->pages) loc.reason = "page-out-of-range";
    else {
      page0 = (size_t)page - 1;
      if (bookmark || (!qn && !comment[0])) {
        loc.located = 1; loc.s = loc.e = 0; loc.method = "page-bookmark";
      } else {
        exr_fixed_text *ft = NULL;
        const char *pt;
        size_t pn;
        if (exr_fixed_load_text(b->fixed, page0, &c->control, &ft, &c->err) != EXR_OK) { sdk_fail(c, "loading page text"); return; }
        pt = exr_fixed_text_string(ft, &pn);
        loc = locate_fixed(c, pt, pn, quote, qn);
        exr_fixed_text_free(ft);
        if (!loc.located && !qn) { loc.located = 1; loc.s = loc.e = 0; loc.method = "page-bookmark"; loc.reason = NULL; }
      }
    }
    if (loc.located) {
      seen_note *dup = seen_find(b, page0, loc.s, loc.e, comment);
      if (dup) { new_id = dup->id; status = "existing"; }
      else {
        exr_fixed_note fn;
        memset(&fn, 0, sizeof(fn));
        fn.book_id = mb->book_id; fn.page = page0; fn.start = loc.s; fn.end = loc.e; fn.text = (char *)comment;
        if (exr_library_fixed_note(c->lib, &fn, &c->control, &new_id, &c->err) != EXR_OK) { sdk_fail(c, "writing fixed note"); return; }
        seen_add(b, page0, loc.s, loc.e, comment, new_id);
      }
      ln->page = page0;
    }
  } else {
    loc = locate_reflow(c, b, id, quote, qn, cfi, bookmark);
    if (loc.located) {
      const char *text = comment;
      seen_note *dup;
      if (bookmark && !comment[0]) text = quote_raw;
      dup = seen_find(b, 0, loc.s, loc.e, text);
      if (dup) { new_id = dup->id; status = "existing"; }
      else {
        exr_note n;
        memset(&n, 0, sizeof(n));
        n.book_id = mb->book_id; n.start = loc.s; n.end = loc.e; n.text = (char *)text;
        if (exr_library_note(c->lib, &n, &new_id, &c->err) != EXR_OK) { sdk_fail(c, "writing note"); return; }
        seen_add(b, 0, loc.s, loc.e, text, new_id);
      }
    }
  }
  ln->located = loc.located;
  ln->new_id = new_id;
  ln->start = loc.located && mb->kind != K_AUDIO ? loc.s : ln->start;
  ln->end = loc.located ? loc.e : 0;
  set_str(&ln->method, loc.method);
  set_str(&ln->reason, loc.reason);
  if (!loc.located) {
    c->notes_unlocated++;
    entry(c, S_UNLOCATED, loc.reason ? loc.reason : "unlocated", "note", id, "annotation preserved in the ledger but not placed in the library (no guessed highlight)");
    note_item(c, id, mb->legacy, kind_name(mb->kind), "unlocated", 0, NULL, loc.reason);
  } else if (!strcmp(status, "existing")) {
    c->notes_existing++;
    note_item(c, id, mb->legacy, kind_name(mb->kind), "existing", new_id, "content-match", NULL);
  } else {
    c->notes_created++;
    note_item(c, id, mb->legacy, kind_name(mb->kind), "created", new_id, loc.method, NULL);
  }
}

/* ---------- book migration ---------- */
static int map_format(const char *ext, exr_format *fmt, int *kind) {
  static const struct { const char *ext; exr_format fmt; int kind; } table[] = {
    {"txt", EXR_TXT, K_REFLOW}, {"html", EXR_HTML, K_REFLOW}, {"htm", EXR_HTML, K_REFLOW}, {"fb2", EXR_FB2, K_REFLOW},
    {"epub", EXR_EPUB, K_REFLOW}, {"docx", EXR_DOCX, K_REFLOW}, {"rtf", EXR_RTF, K_REFLOW}, {"mobi", EXR_MOBI, K_REFLOW},
    {"azw3", EXR_MOBI, K_REFLOW}, {"pdf", EXR_PDF, K_FIXED}, {"cbz", EXR_CBZ, K_FIXED}};
  size_t i;
  for (i = 0; i < sizeof(table) / sizeof(*table); i++)
    if (!strcmp(ext, table[i].ext)) { *fmt = table[i].fmt; *kind = table[i].kind; return 1; }
  return 0;
}
static const char *file_extension(const char *name, char *buffer, size_t size) {
  const char *dot = strrchr(name, '.');
  size_t i;
  if (!dot) return "";
  if (strlen(name) > 8 && !strcmp(name + strlen(name) - 8, ".fb2.zip")) return "fb2.zip";
  for (i = 0; dot[1 + i] && i + 1 < size; i++) buffer[i] = (char)tolower((unsigned char)dot[1 + i]);
  buffer[i] = 0;
  return buffer;
}
static void book_item(ctx *c, const char *legacy, const char *status, const char *kind, int64_t id, const char *sha, uint64_t size, const char *title) {
  if (c->item_n++) lm_sb_str(&c->items, ",");
  lm_sb_str(&c->items, "{\"legacy_id\":");
  lm_sb_json(&c->items, legacy, strlen(legacy));
  lm_sb_fmt(&c->items, ",\"status\":\"%s\",\"kind\":", status);
  if (kind) lm_sb_fmt(&c->items, "\"%s\"", kind); else lm_sb_str(&c->items, "null");
  lm_sb_str(&c->items, ",\"book_id\":");
  if (id > 0) lm_sb_fmt(&c->items, "%lld", (long long)id); else lm_sb_str(&c->items, "null");
  lm_sb_str(&c->items, ",\"sha256\":");
  if (sha && sha[0]) lm_sb_fmt(&c->items, "\"%s\"", sha); else lm_sb_str(&c->items, "null");
  lm_sb_fmt(&c->items, ",\"size\":%llu,\"title\":", (unsigned long long)size);
  if (title) lm_sb_json(&c->items, title, strlen(title)); else lm_sb_str(&c->items, "null");
  lm_sb_str(&c->items, "}");
}
static int import_item_error(ctx *c, const char *legacy) {
  /* Content the SDK refuses is an item-level rejection; infrastructure faults abort the run. */
  switch (c->err.code) {
    case EXR_FORMAT: case EXR_ENCODING: case EXR_UNSUPPORTED: case EXR_LIMIT: case EXR_PASSWORD: case EXR_ARGUMENT:
      entry(c, S_UNSUPPORTED, "sdk-rejected-original", "book", legacy, "the SDK refused the original: %s (status %d)", c->err.message, (int)c->err.code);
      return 1;
    default: sdk_fail(c, "importing original"); return 0;
  }
}
static void assign_ids(ctx *c, bctx *b, lm_book *mb, const jv *jb, const jv *notes_list, const size_t *order, size_t first, size_t last);

static void process_book(ctx *c, const jv *jb, const jv *pack_notes, const size_t *order, size_t first, size_t last) {
  const jv *rec = lm_get(jb, "record"), *file = lm_get(jb, "file"), *v;
  const char *id = lm_get_str(jb, "legacy_id"), *title_raw, *author, *filename, *format_field, *cover, *cfi, *status_text;
  char ext_buffer[32], *tags = NULL, *title = NULL;
  const char *ext, *tlen_ptr;
  size_t tl, i;
  int kind = K_REFLOW, audio_flag = 0, favorite = 0, status = 0, invalid = 0;
  exr_format fmt = EXR_TXT;
  uint64_t page = 0, offset = 0, size = 0;
  double progress = -1, seconds = -1;
  const char *file_sha;
  lm_book *mb;
  int existed;
  bctx bc;
  lm_sb joined;

  unknown_fields(c, rec, BOOK_FIELDS, "book", id);
  title_raw = lm_get_str(rec, "title");
  author = lm_get_str(rec, "author");
  filename = lm_get_str(rec, "filename");
  format_field = lm_get_str(rec, "format");
  cover = lm_get_str(rec, "cover");
  cfi = lm_get_str(rec, "cfi");
  status_text = lm_get_str(rec, "status");
  if ((lm_get(rec, "title") && !title_raw) || (lm_get(rec, "author") && !author) || (lm_get(rec, "tags") && lm_get(rec, "tags")->t != J_ARR) ||
      (lm_get(rec, "favorite") && lm_get(rec, "favorite")->t != J_BOOL)) invalid = 1;
  if (lm_get(rec, "tags") && lm_get(rec, "tags")->t == J_ARR)
    for (i = 0; i < lm_get(rec, "tags")->n; i++)
      if (lm_get(rec, "tags")->items[i]->t != J_STR) invalid = 1;
  if (invalid) {
    entry(c, S_UNSUPPORTED, "invalid-book-record", "book", id, "title/author/tags/favorite have the wrong JSON type");
    c->books_skipped++;
    book_item(c, id, "skipped", NULL, 0, NULL, 0, NULL);
    return;
  }
  if (!title_raw) entry(c, S_INFO, "missing-field", "book", id, "title absent; derived from the file name");
  if (!author) entry(c, S_INFO, "missing-field", "book", id, "author absent; empty author used");
  if (!lm_get(rec, "tags")) entry(c, S_INFO, "missing-field", "book", id, "tags absent; no tags");
  if (!lm_get(rec, "favorite")) entry(c, S_INFO, "missing-field", "book", id, "favorite absent; false");
  if (!status_text) entry(c, S_INFO, "missing-field", "book", id, "status absent; unread");
  favorite = lm_get(rec, "favorite") && lm_get(rec, "favorite")->b;
  if (status_text) {
    if (!strcmp(status_text, "reading")) status = 1;
    else if (!strcmp(status_text, "finished")) status = 2;
    else if (strcmp(status_text, "unread")) entry(c, S_WARNING, "unknown-status", "book", id, "status \"%s\" is not unread/reading/finished; unread used", status_text);
  }
  v = lm_get(rec, "progress");
  if (v && v->t == J_NUM && v->num >= 0 && v->num <= 1) progress = v->num;
  else if (v) entry(c, S_WARNING, "wrong-type", "book", id, "progress is not a fraction in [0,1]; ignored");
  v = lm_get(rec, "page");
  if (v && (!lm_json_uint(v, &page) || page < 1)) { entry(c, S_WARNING, "wrong-type", "book", id, "page is not a one-based integer; ignored"); page = 0; }
  v = lm_get(rec, "seconds");
  if (v && v->t == J_NUM && v->num >= 0 && isfinite(v->num)) seconds = v->num;
  else if (v) entry(c, S_WARNING, "wrong-type", "book", id, "seconds is not non-negative; ignored");
  v = lm_get(rec, "audio");
  audio_flag = v && v->t == J_BOOL && v->b;
  ext = format_field ? format_field : file_extension(filename ? filename : "", ext_buffer, sizeof(ext_buffer));
  if (in_list(ext, AUDIO_EXT)) audio_flag = 1;

  if (!lm_get(file, "present") || !lm_get(file, "present")->b) {
    entry(c, S_UNSUPPORTED, "missing-original", "book", id, "the export holds no original bytes for this record; nothing can be imported");
    c->books_skipped++;
    book_item(c, id, "skipped", NULL, 0, NULL, 0, title_raw);
    return;
  }
  file_sha = lm_get_str(file, "sha256");
  lm_json_uint(lm_get(file, "offset"), &offset);
  lm_json_uint(lm_get(file, "size"), &size);
  if (size > c->max_book_bytes) c->max_book_bytes = size;

  if (audio_flag) kind = K_AUDIO;
  else if (!map_format(ext, &fmt, &kind)) {
    entry(c, S_UNSUPPORTED, "unsupported-format", "book", id, "legacy format \"%s\" has no SDK format; the original stays in the pack", ext);
    c->books_skipped++;
    book_item(c, id, "skipped", NULL, 0, file_sha, size, title_raw);
    return;
  }

  /* Title: trimmed legacy title, else the file name stem. */
  if (title_raw) trim(title_raw, strlen(title_raw), &tlen_ptr, &tl); else { tlen_ptr = ""; tl = 0; }
  if (!tl && filename) {
    const char *dot = strrchr(filename, '.');
    tl = dot && dot != filename ? (size_t)(dot - filename) : strlen(filename);
    tlen_ptr = filename;
  }
  title = lm_xalloc(tl + 1);
  memcpy(title, tlen_ptr, tl);

  lm_sb_init(&joined);
  if (lm_get(rec, "tags"))
    for (i = 0; i < lm_get(rec, "tags")->n; i++) {
      const jv *t = lm_get(rec, "tags")->items[i];
      if (!t->n) continue;
      if (strchr(t->s, ',')) entry(c, S_INFO, "tag-separator", "book", id, "tag \"%s\" contains a comma; the library joins tags with \", \"", t->s);
      if (joined.n) lm_sb_str(&joined, ", ");
      lm_sb_str(&joined, t->s);
    }
  tags = lm_xdup(joined.p ? joined.p : "");
  lm_sb_free(&joined);

  existed = lm_ledger_book(&c->ledger, id, 0) != NULL;
  mb = lm_ledger_book(&c->ledger, id, 1);
  if (existed && mb->sha[0] && strcmp(mb->sha, file_sha)) {
    entry(c, S_CONFLICT, "id-content-changed", "book", id, "legacy id was migrated earlier with a different original (sha256 %.12s vs %.12s); rule: reject, keep the earlier book", mb->sha, file_sha);
    c->books_skipped++;
    book_item(c, id, "skipped", kind_name(mb->kind), mb->book_id, mb->sha, size, title);
    mb->touched = 1;
    free(title); free(tags);
    return;
  }
  strcpy(mb->sha, file_sha);
  mb->kind = kind;
  mb->touched = 1;
  free(mb->retained);
  mb->retained = record_json(rec, 1);
  memset(&bc, 0, sizeof(bc));
  c->seen_a = c->seen_a ? c->seen_a : lm_xalloc(MATCH_CAP * sizeof(size_t));
  c->seen_b = c->seen_b ? c->seen_b : lm_xalloc(MATCH_CAP * sizeof(size_t));

  if (kind == K_AUDIO) {
    exr_audio_checkpoint resume, current;
    int found = 0;
    free(mb->audio_id);
    {
      char *audio_id = lm_xalloc(strlen(id) + 24);
      sprintf(audio_id, "exreader-legacy:%s", id);
      mb->audio_id = audio_id;
    }
    entry(c, S_UNSUPPORTED, "audio-original-not-storable", "book", id, "the library has no audio original format; positions and bookmarks are migrated under audio_id, the file stays in the pack");
    memset(&current, 0, sizeof(current));
    if (exr_library_audio_resume_get(c->lib, mb->audio_id, &current, &found, &c->err) != EXR_OK) { sdk_fail(c, "reading audio resume"); goto done; }
    if (seconds >= 0 && !found) {
        if (seconds * 1000.0 + 0.5 >= 9223372036854775808.0) {
          exr_audio_checkpoint_free(&current);
          fail(c, O_REJECTED, "audio-position-limit", "audio position exceeds the stored checkpoint range"); goto done;
        }
        resume.track_id = (char *)id;
        resume.offset_ms = (uint64_t)floor(seconds * 1000.0 + 0.5);
        resume.rate = 1.0;
        if (exr_library_audio_resume(c->lib, mb->audio_id, &resume, &c->err) != EXR_OK) { sdk_fail(c, "writing audio resume"); goto done; }
        mb->audio_seconds = seconds;
        current.track_id = lm_xdup(id); current.offset_ms = resume.offset_ms; current.rate = resume.rate; found = 1;
    } else if (seconds >= 0 && found) {
      entry(c, S_INFO, "resume-exists", "book", id, "an audio resume point already exists; it is kept");
    }
    exr_audio_checkpoint_free(&mb->audio_expected);
    mb->audio_expectation_set = 1; mb->audio_resume_found = found;
    mb->audio_expected = current;
    c->books_audio++;
    if (!bctx_load(c, &bc, mb)) goto done;
    assign_ids(c, &bc, mb, jb, pack_notes, order, first, last);
    book_item(c, id, "audio-positions-only", "audio", 0, file_sha, size, title);
    goto done;
  }

  /* Reflow and fixed originals: import by exact bytes; unsupported content is an item-level rejection. */
  {
    unsigned char *bytes = NULL;
    int64_t book_id = 0;
    int created = 0;
    lm_book *claim;
    if (size == 0) {
      entry(c, S_UNSUPPORTED, "empty-original", "book", id, "the original is empty");
      c->books_skipped++; book_item(c, id, "skipped", kind_name(kind), 0, file_sha, size, title); goto done;
    }
    if (size > LM_BOOK_BYTES_MAX) {
      entry(c, S_UNSUPPORTED, "limit-exceeded", "book", id, "original is %llu bytes; the in-memory import bound is %llu and streaming migration is not implemented", (unsigned long long)size, (unsigned long long)LM_BOOK_BYTES_MAX);
      c->books_skipped++; book_item(c, id, "skipped", kind_name(kind), 0, file_sha, size, title); goto done;
    }
    if (injected(c, "read-fail", c->reads++)) { fail(c, O_FAILED, "pack-read-error", "injected read failure at book %u", c->reads - 1); goto done; }
    bytes = malloc((size_t)size);
    if (!bytes) { fail(c, O_FAILED, "out-of-memory", "cannot allocate %llu bytes for %s", (unsigned long long)size, id); goto done; }
    if (!lm_pack_read(&c->pack, offset, bytes, (size_t)size)) { free(bytes); fail(c, O_FAILED, "pack-read-error", "cannot read original of %s", id); goto done; }
    {
      char again[65];
      lm_sha_bytes(bytes, (size_t)size, again);
      if (strcmp(again, file_sha)) { free(bytes); fail(c, O_FAILED, "pack-changed", "original of %s no longer matches its digest", id); goto done; }
    }
    if (injected(c, "write-fail", c->imports++)) { free(bytes); fail(c, O_FAILED, "injected-write-fail", "injected library write failure at book %u", c->imports - 1); goto done; }
    if (exr_library_import_unique(c->lib, fmt, bytes, (size_t)size, tl ? title : NULL, &book_id, &created, &c->err) != EXR_OK) {
      free(bytes);
      if (import_item_error(c, id)) { c->books_skipped++; book_item(c, id, "skipped", kind_name(kind), 0, file_sha, size, title); }
      goto done;
    }
    free(bytes);
    c->bytes_imported += size;
    claim = lm_ledger_claim(&c->ledger, book_id);
    if (claim == mb) claim = NULL;
    lm_ledger_set_id(&c->ledger, mb, book_id);
    mb->created = created;
    if (claim) {
      entry(c, S_WARNING, "same-original-different-id", "book", id, "identical original already belongs to legacy id %s; rule: merge into that library book, keep its metadata and progress, merge annotations", claim->legacy);
      c->books_merged++;
    } else if (!created) {
      entry(c, S_INFO, existed ? "already-migrated" : "adopted-existing", "book", id, existed ? "legacy id was migrated earlier; nothing new to create" : "an identical original is already in the library; adopting it without touching its metadata");
      c->books_existing++;
    } else c->books_created++;

    if (created) {
      exr_book meta;
      size_t position = 0;
      int meta_done = 0;
      memset(&meta, 0, sizeof(meta));
      if (kind == K_FIXED) {
        size_t pages;
        exr_fixed_document *fd = NULL;
        if (exr_library_fixed(c->lib, book_id, NULL, &fd, &c->err) != EXR_OK) { sdk_fail(c, "opening fixed document"); goto done; }
        exr_fixed_pages(fd, &pages);
        exr_fixed_free(fd);
        if (page >= 1 && page <= pages) position = (size_t)page - 1;
        else if (page >= 1) entry(c, S_WARNING, "progress-out-of-range", "book", id, "legacy page %llu exceeds the %zu pages; position left at the first page", (unsigned long long)page, pages);
        else if (progress > 0 && pages > 1) {
          position = (size_t)floor(progress * (double)(pages - 1) + 0.5);
          entry(c, S_APPROX, "approximate-progress", "book", id, "only a book fraction was recorded; page %zu (zero-based) is a percentage estimate, not an exact page", position);
        }
        if (cfi && cfi[0]) entry(c, S_DROPPED, "cfi-not-applicable", "book", id, "an EPUB CFI cannot address a fixed-page book; kept in the ledger only");
      } else {
        exr_document *doc = NULL;
        const char *text;
        size_t text_size = 0;
        cfi_loc a, e;
        int is_range;
        if (exr_library_document(c->lib, book_id, &doc, &c->err) != EXR_OK) { sdk_fail(c, "opening stored document"); goto done; }
        text = exr_document_text(doc, &text_size);
        if (cfi && cfi[0] && cfi_locate(doc, cfi, text, text_size, &a, &e, &is_range) && (a.kind == 1 || a.kind == 2)) {
          position = a.offset;
          mb->anchored = 1;
        } else {
          if (cfi && cfi[0]) entry(c, S_WARNING, "cfi-unresolved", "book", id, "the reading-position CFI does not resolve exactly in the migrated document");
          if (progress > 0) {
            position = (size_t)floor(progress * (double)text_size);
            if (position > text_size) position = text_size;
            while (position > 0 && position < text_size && ((unsigned char)text[position] & 0xc0) == 0x80) position--;
            entry(c, S_APPROX, "approximate-progress", "book", id, "only a book fraction was usable; byte position %zu of %zu is a percentage estimate with no text selector", position, text_size);
          }
        }
        if (mb->anchored) {
          exr_anchor anchor;
          memset(&anchor, 0, sizeof(anchor));
          if (exr_anchor_create(doc, position, position, &anchor, &c->err) != EXR_OK) { exr_document_free(doc); sdk_fail(c, "creating progress anchor"); goto done; }
          meta.id = book_id; meta.title = title; meta.author = (char *)(author ? author : ""); meta.tags = tags; meta.favorite = favorite; meta.status = status; meta.position = position;
          if (exr_library_update(c->lib, &meta, &c->err) != EXR_OK || exr_library_progress(c->lib, book_id, &anchor, &c->err) != EXR_OK) { exr_anchor_free(&anchor); exr_document_free(doc); sdk_fail(c, "writing progress"); goto done; }
          exr_anchor_free(&anchor);
          meta_done = 1;
        }
        exr_document_free(doc);
      }
      if (!meta_done) {
        meta.id = book_id; meta.title = title; meta.author = (char *)(author ? author : ""); meta.tags = tags; meta.favorite = favorite; meta.status = status; meta.position = position;
        if (!tl) meta.title = (char *)"Untitled";
        if (exr_library_update(c->lib, &meta, &c->err) != EXR_OK) { sdk_fail(c, "writing metadata"); goto done; }
      }
      set_str(&mb->title, tl ? title : "Untitled");
      set_str(&mb->author, author ? author : "");
      set_str(&mb->tags, tags);
      mb->favorite = favorite; mb->status = status; mb->position = position;
      if (cover && cover[0]) {
        const char *comma = strchr(cover, ',');
        unsigned char *image = NULL;
        size_t image_size = 0;
        if (!strncmp(cover, "data:image/", 11) && comma && strstr(cover, ";base64,") && lm_b64_decode(comma + 1, strlen(comma + 1), &image, &image_size, 8u * 1024 * 1024) && image_size) {
          if (exr_library_cover(c->lib, book_id, image, image_size, &c->err) != EXR_OK) { free(image); sdk_fail(c, "writing cover"); goto done; }
          free(image);
        } else entry(c, S_DROPPED, "cover-invalid", "book", id, "the legacy cover is not a PNG/JPEG/WebP/GIF data URI within 8 MiB; dropped");
      }
    } else if (cover && cover[0]) entry(c, S_INFO, "cover-kept", "book", id, "existing library book keeps its own cover");
    entry(c, S_INFO, "retained-in-ledger", "book", id, "added/lastRead/modified/size/filename and the raw legacy record are retained in the ledger (no library fields exist for them)");
    if (!bctx_load(c, &bc, mb)) goto done;
    assign_ids(c, &bc, mb, jb, pack_notes, order, first, last);
    book_item(c, id, claim ? "merged" : created ? "created" : "existing", kind_name(kind), book_id, file_sha, size, title);
  }
done:
  bctx_free(&bc);
  free(title);
  free(tags);
}
/* Notes of this book are processed after its identity is fixed. */
static void assign_ids(ctx *c, bctx *b, lm_book *mb, const jv *jb, const jv *notes_list, const size_t *order, size_t first, size_t last) {
  size_t i;
  (void)jb;
  for (i = first; i < last && c->out == O_NONE; i++) {
    if (!tick(c)) return;
      process_note(c, b, mb, notes_list->items[order[i]]);
  }
}

/* ---------- ledger file ---------- */
static int read_whole(const char *path, char **out, size_t *size, size_t max) {
#ifdef EXR_MIGRATION_RECOVERY_CANDIDATE
  lm_err e={{0},{0}};return lr_read(g_recovery,path,out,size,max<LM_RECOVERY_LIMIT?max:LM_RECOVERY_LIMIT,&e);
#else
  FILE *f = lm_fopen(path, "rb");
  uint64_t n;
  char *p;
  if (!f) return 0;
  if (!lm_file_size(f, &n) || n > max) { fclose(f); return 0; }
  p = lm_xalloc((size_t)n + 1);
  if (fread(p, 1, (size_t)n, f) != (size_t)n) { fclose(f); free(p); return 0; }
  fclose(f);
  *out = p;
  *size = (size_t)n;
  return 1;
#endif
}
static int sidecar_parse(ctx *c, const char *data, size_t n) {
  char error[160];
  size_t i;
  jv *root;
  const jv *books, *notes, *packs;
  root = lm_json_parse(data, n, error, sizeof(error));
  if (!root || root->t != J_OBJ) { fail(c, O_REJECTED, "ledger-invalid", "existing ledger is not valid JSON: %s", root ? "not an object" : error); lm_json_free(root); return 0; }
  if (!lm_get_str(root, "format") || strcmp(lm_get_str(root, "format"), LM_MAP_FORMAT)) { fail(c, O_REJECTED, "ledger-invalid", "existing sidecar is not an %s file", LM_MAP_FORMAT); lm_json_free(root); return 0; }
  if (!lm_get(root, "version") || lm_get(root, "version")->num != 1.0) { fail(c, O_REJECTED, "ledger-unknown-version", "existing ledger has an unsupported version; refusing to overwrite it"); lm_json_free(root); return 0; }
  books = lm_get(root, "books"); notes = lm_get(root, "notes"); packs = lm_get(root, "packs");
  if (!books || books->t != J_ARR || !notes || notes->t != J_ARR) { fail(c, O_REJECTED, "ledger-invalid", "existing ledger lacks books/notes"); lm_json_free(root); return 0; }
  for (i = 0; i < books->n; i++) {
    const jv *e = books->items[i], *r = lm_get(e, "retained");
    const char *legacy = lm_get_str(e, "legacy_id"), *sha = lm_get_str(e, "sha256"), *kind = lm_get_str(e, "kind");
    uint64_t book_id = 0;
    lm_book *b;
    lm_sb raw;
    if (!legacy || !sha || strlen(sha) != 64 || !kind) { fail(c, O_REJECTED, "ledger-invalid", "ledger book %zu is malformed", i); lm_json_free(root); return 0; }
    b = lm_ledger_book(&c->ledger, legacy, 1);
    strcpy(b->sha, sha);
    b->kind = !strcmp(kind, "fixed") ? K_FIXED : !strcmp(kind, "audio") ? K_AUDIO : K_REFLOW;
    lm_json_uint(lm_get(e, "book_id"), &book_id);
    if (book_id > 0) lm_ledger_set_id(&c->ledger, b, (int64_t)book_id);
    if (lm_get_str(e, "audio_id")) b->audio_id = lm_xdup(lm_get_str(e, "audio_id"));
    if (b->kind == K_AUDIO && lm_get(e, "resume_expected")) {
      const jv *expected = lm_get(e, "resume_expected"), *present = lm_get(expected, "present"), *rate = lm_get(expected, "rate");
      const char *ms = lm_get_str(expected, "offset_ms"), *track = lm_get_str(expected, "track");
      char *end = NULL;
      unsigned long long offset_ms = 0;
      int valid = present && present->t == J_BOOL;
      if (valid && present->b) {
        errno = 0;
        if (ms && *ms && strspn(ms, "0123456789") == strlen(ms)) offset_ms = strtoull(ms, &end, 10);
        valid = ms && *ms && end && !*end && !errno && offset_ms <= INT64_MAX && track &&
                rate && rate->t == J_NUM && isfinite(rate->num) && rate->num > 0;
      }
      if (!valid) { fail(c, O_REJECTED, "ledger-invalid", "invalid expected audio checkpoint"); lm_json_free(root); return 0; }
      b->audio_expectation_set = 1; b->audio_resume_found = present->b;
      if (present->b) { b->audio_expected.track_id = lm_xdup(track); b->audio_expected.offset_ms = (uint64_t)offset_ms; b->audio_expected.rate = rate->num; }
    }
    lm_sb_init(&raw);
    if (r) lm_json_write(&raw, r); else lm_sb_str(&raw, "{}");
    b->retained = lm_xdup(raw.p);
    lm_sb_free(&raw);
  }
  for (i = 0; i < notes->n; i++) {
    const jv *e = notes->items[i], *r = lm_get(e, "retained");
    const char *legacy = lm_get_str(e, "legacy_id"), *fp = lm_get_str(e, "fingerprint"), *kind = lm_get_str(e, "kind");
    uint64_t id = 0, x = 0;
    lm_note *nn;
    lm_sb raw;
    if (!legacy || !fp || strlen(fp) != 64 || !kind) { fail(c, O_REJECTED, "ledger-invalid", "ledger note %zu is malformed", i); lm_json_free(root); return 0; }
    nn = lm_ledger_note(&c->ledger, legacy, 1);
    strcpy(nn->fp, fp);
    nn->kind = !strcmp(kind, "fixed") ? K_FIXED : !strcmp(kind, "audio") ? K_AUDIO : K_REFLOW;
    lm_json_uint(lm_get(e, "new_id"), &id);
    nn->new_id = (int64_t)id;
    nn->located = lm_get(e, "located") && lm_get(e, "located")->b;
    if (lm_get_str(e, "book_legacy_id")) nn->book_legacy = lm_xdup(lm_get_str(e, "book_legacy_id"));
    if (lm_get_str(e, "method")) nn->method = lm_xdup(lm_get_str(e, "method"));
    if (lm_get_str(e, "reason")) nn->reason = lm_xdup(lm_get_str(e, "reason"));
    if (lm_json_uint(lm_get(e, "start"), &x)) nn->start = (size_t)x;
    if (lm_json_uint(lm_get(e, "end"), &x)) nn->end = (size_t)x;
    if (lm_json_uint(lm_get(e, "page"), &x)) nn->page = (size_t)x;
    lm_sb_init(&raw);
    if (r) lm_json_write(&raw, r); else lm_sb_str(&raw, "{}");
    nn->retained = lm_xdup(raw.p);
    lm_sb_free(&raw);
  }
  if (packs && packs->t == J_ARR)
    for (i = 0; i < packs->n; i++)
      if (packs->items[i]->t == J_STR) {
        c->ledger.packs = realloc(c->ledger.packs, (c->ledger.pack_n + 1) * sizeof(char *));
        c->ledger.packs[c->ledger.pack_n++] = lm_xdup(packs->items[i]->s);
      }
  lm_json_free(root);
  return 1;
}
static int sidecar_load(ctx *c, const char *path) {
  char *data=NULL;size_t n;int ok;
  if (!read_whole(path,&data,&n,256u*1024*1024)) { fail(c,O_REJECTED,"ledger-unreadable","cannot read the existing migration ledger %s",path);return 0; }
  ok=sidecar_parse(c,data,n);free(data);return ok;
}
#ifdef EXR_MIGRATION_TX_CANDIDATE
/* A stale legacy sidecar can coexist with the transactional ledger, but an
   unreadable or unsupported sidecar must not be silently disregarded. */
static int sidecar_check_envelope(ctx *c, const char *path) {
  char *data=NULL, error[160];size_t size=0;const jv *version; jv *root;
  if(!read_whole(path,&data,&size,256u*1024*1024)) {
    fail(c,O_REJECTED,"ledger-unreadable","cannot read the existing migration ledger %s",path);return 0;
  }
  root=lm_json_parse(data,size,error,sizeof(error));free(data);
  if(!root || root->t!=J_OBJ || !lm_get_str(root,"format") || strcmp(lm_get_str(root,"format"),LM_MAP_FORMAT)) {
    lm_json_free(root);fail(c,O_REJECTED,"ledger-invalid","existing sidecar is not a valid migration ledger");return 0;
  }
  version=lm_get(root,"version");
  if(!version || version->t!=J_NUM || version->num!=1.0) {
    lm_json_free(root);fail(c,O_REJECTED,"ledger-unknown-version","existing ledger has an unsupported version; refusing to proceed");return 0;
  }
  if(!lm_get(root,"books") || lm_get(root,"books")->t!=J_ARR || !lm_get(root,"notes") || lm_get(root,"notes")->t!=J_ARR) {
    lm_json_free(root);fail(c,O_REJECTED,"ledger-invalid","existing ledger lacks books/notes");return 0;
  }
  lm_json_free(root);return 1;
}
#endif
static void sidecar_text(ctx *c, lm_sb *b) {
  size_t i;
  int known = 0;
  for (i = 0; i < c->ledger.pack_n; i++)
    if (!strcmp(c->ledger.packs[i], c->pack.sha)) known = 1;
  lm_sb_fmt(b, "{\"format\":\"%s\",\"version\":1,\"tool_version\":\"%s\",\"packs\":[", LM_MAP_FORMAT, LM_TOOL_VERSION);
  for (i = 0; i < c->ledger.pack_n; i++) { if (i) lm_sb_str(b, ","); lm_sb_fmt(b, "\"%s\"", c->ledger.packs[i]); }
  if (!known) lm_sb_fmt(b, "%s\"%s\"", c->ledger.pack_n ? "," : "", c->pack.sha);
  lm_sb_str(b, "],\"books\":[");
  for (i = 0; i < c->ledger.book_n; i++) {
    const lm_book *k = &c->ledger.books[i];
    if (i) lm_sb_str(b, ",");
    lm_sb_str(b, "{\"legacy_id\":");
    lm_sb_json(b, k->legacy, strlen(k->legacy));
    lm_sb_fmt(b, ",\"sha256\":\"%s\",\"kind\":\"%s\",\"book_id\":", k->sha, kind_name(k->kind));
    if (k->book_id > 0) lm_sb_fmt(b, "%lld", (long long)k->book_id); else lm_sb_str(b, "null");
    lm_sb_str(b, ",\"audio_id\":");
    if (k->audio_id) lm_sb_json(b, k->audio_id, strlen(k->audio_id)); else lm_sb_str(b, "null");
    if (k->kind == K_AUDIO && k->audio_expectation_set) {
      lm_sb_fmt(b, ",\"resume_expected\":{\"present\":%s", k->audio_resume_found ? "true" : "false");
      if (k->audio_resume_found) {
        lm_sb_str(b, ",\"track\":"); lm_sb_json(b, k->audio_expected.track_id, strlen(k->audio_expected.track_id));
        lm_sb_fmt(b, ",\"offset_ms\":\"%llu\",\"rate\":%.17g", (unsigned long long)k->audio_expected.offset_ms, k->audio_expected.rate);
      }
      lm_sb_str(b, "}");
    }
    lm_sb_str(b, ",\"retained\":");
    lm_sb_str(b, k->retained ? k->retained : "{}");
    lm_sb_str(b, "}");
  }
  lm_sb_str(b, "],\"notes\":[");
  for (i = 0; i < c->ledger.note_n; i++) {
    const lm_note *k = &c->ledger.notes[i];
    if (i) lm_sb_str(b, ",");
    lm_sb_str(b, "{\"legacy_id\":");
    lm_sb_json(b, k->legacy, strlen(k->legacy));
    lm_sb_str(b, ",\"book_legacy_id\":");
    if (k->book_legacy) lm_sb_json(b, k->book_legacy, strlen(k->book_legacy)); else lm_sb_str(b, "null");
    lm_sb_fmt(b, ",\"fingerprint\":\"%s\",\"kind\":\"%s\",\"new_id\":", k->fp, kind_name(k->kind));
    if (k->new_id > 0) lm_sb_fmt(b, "%lld", (long long)k->new_id); else lm_sb_str(b, "null");
    lm_sb_fmt(b, ",\"located\":%s,\"start\":%zu,\"end\":%zu,\"page\":%zu,\"method\":", k->located ? "true" : "false", k->start, k->end, k->page);
    if (k->method) lm_sb_json(b, k->method, strlen(k->method)); else lm_sb_str(b, "null");
    lm_sb_str(b, ",\"reason\":");
    if (k->reason) lm_sb_json(b, k->reason, strlen(k->reason)); else lm_sb_str(b, "null");
    lm_sb_str(b, ",\"retained\":");
    lm_sb_str(b, k->retained ? k->retained : "{}");
    lm_sb_str(b, "}");
  }
  lm_sb_str(b, "]}\n");
}
static int write_file(const char *path, const char *data, size_t n) {
#ifdef EXR_MIGRATION_RECOVERY_CANDIDATE
  lm_err e={{0},{0}};return lr_write_new(g_recovery,path,data,n,&e);
#else
  FILE *f = lm_fopen(path, "wb");
  int ok;
  if (!f) return 0;
  ok = fwrite(data, 1, n, f) == n && lm_sync(f);
  if (fclose(f)) ok = 0;
  if (!ok) lm_remove(path);
  return ok;
#endif
}
#ifdef EXR_MIGRATION_TX_CANDIDATE
static int export_new_file(const char *path,const void *data,size_t size) {
#ifdef EXR_MIGRATION_RECOVERY_CANDIDATE
  lm_err e={{0},{0}};return lr_write_new(g_recovery,path,data,size,&e);
#else
  char *temporary=lm_xalloc(strlen(path)+64);FILE *file;int ok;
  sprintf(temporary,"%s.tmp-%u",path,(unsigned)
#ifdef _WIN32
    _getpid()
#else
    getpid()
#endif
  );
  file=lm_fopen(temporary,"wbx");
  if(!file) { free(temporary);return 0; }
  ok=fwrite(data,1,size,file)==size && lm_sync(file);
  if(fclose(file)) ok=0;
  if(ok) ok=lm_publish_new(temporary,path);
  lm_remove(temporary);free(temporary);return ok;
#endif
}
#endif

/* ---------- verification and dump ---------- */
static int check_target_header(ctx *c);
static char *verified_note_text(const lm_note *note) {
  char error[160];
  jv *record = lm_json_parse(note->retained ? note->retained : "{}",
                           note->retained ? strlen(note->retained) : 2, error, sizeof(error));
  const char *comment = lm_get_str(record, "note"), *quote = lm_get_str(record, "quote");
  const jv *bookmark = lm_get(record, "bookmark");
  char *text;
  if (!record || record->t != J_OBJ) { lm_json_free(record); return NULL; }
  if (!comment) comment = "";
  if (note->kind == K_REFLOW && bookmark && bookmark->t == J_BOOL && bookmark->b && !*comment)
    comment = quote ? quote : "";
  text = lm_xdup(comment);
  lm_json_free(record);
  return text;
}
static int verify_library(ctx *c, exr_library *lib, int check_metadata) {
  size_t i, count = 0;
  exr_book *books = NULL;
  lm_hm by_id;
  unsigned bad = 0;
  size_t *head, *next, at;
  memset(&by_id, 0, sizeof(by_id));
  /* A damaged ledger must not silently turn a located annotation into a skip. */
  for (i = 0; i < c->ledger.note_n; i++) {
    lm_note *note = &c->ledger.notes[i];
    jv *record;
    lm_sb canonical;
    char error[160], fingerprint[65];
    size_t owner;
    if (!note->touched) continue;
    record = note->retained ? lm_json_parse(note->retained, strlen(note->retained), error, sizeof(error)) : NULL;
    if (!record || record->t != J_OBJ) { lm_json_free(record); fail(c, O_FAILED, "verify-failed", "retained annotation is not a record"); return 0; }
    if (note->located && (!note->book_legacy || !lm_get_str(record, "bookId") ||
                         strcmp(note->book_legacy, lm_get_str(record, "bookId")))) {
      lm_json_free(record); fail(c, O_FAILED, "verify-failed", "retained annotation owner differs from its mapping"); return 0;
    }
    lm_sb_init(&canonical);
    lm_json_write(&canonical, record);
    lm_sha_bytes(canonical.p ? canonical.p : "", canonical.n, fingerprint);
    lm_sb_free(&canonical); lm_json_free(record);
    if (strcmp(fingerprint, note->fp)) { fail(c, O_FAILED, "verify-failed", "retained annotation fingerprint differs from the ledger"); return 0; }
    if (note->located && (note->new_id <= 0 || !note->book_legacy ||
        !lm_hm_get(&c->ledger.book_index, note->book_legacy, &owner) ||
        c->ledger.books[owner].kind != note->kind ||
        (note->kind != K_AUDIO && c->ledger.books[owner].book_id <= 0))) {
      fail(c, O_FAILED, "verify-failed", "located annotation lacks a valid mapped owner or stored identity"); return 0;
    }
    if (note->located) c->ledger.books[owner].touched = 1;
  }
  if (exr_library_books(lib, "", &books, &count, &c->err) != EXR_OK) { sdk_fail(c, "listing library"); return 0; }
  for (i = 0; i < count; i++) {
    char *k = lm_xalloc(24);
    snprintf(k, 24, "%lld", (long long)books[i].id);
    lm_hm_put(&by_id, k, i);
  }
  head = lm_xalloc((c->ledger.book_n + 1) * sizeof(size_t));
  next = lm_xalloc((c->ledger.note_n + 1) * sizeof(size_t));
  for (i = 0; i <= c->ledger.book_n; i++) head[i] = SIZE_MAX;
  for (i = 0; i < c->ledger.note_n; i++) {
    lm_note *n = &c->ledger.notes[i];
    next[i] = SIZE_MAX;
    if (n->touched && n->book_legacy && lm_hm_get(&c->ledger.book_index, n->book_legacy, &at)) { next[i] = head[at]; head[at] = i; }
  }
  for (i = 0; i < c->ledger.book_n && c->out == O_NONE; i++) {
    lm_book *b = &c->ledger.books[i];
    size_t n;
    if (!b->touched || (b->kind != K_AUDIO && b->book_id <= 0)) continue;
    if (b->kind == K_AUDIO) {
      exr_audio_checkpoint p;
      int found = 0;
      memset(&p, 0, sizeof(p));
      if (!b->audio_id || !b->audio_expectation_set) { fail(c, O_FAILED, "verify-failed", "audio checkpoint expectation missing; rerun migration to register retained state"); break; }
      if (exr_library_audio_resume_get(lib, b->audio_id, &p, &found, &c->err) != EXR_OK) { sdk_fail(c, "verify audio"); break; }
      if (found != b->audio_resume_found || (found && (p.offset_ms != b->audio_expected.offset_ms ||
          p.rate != b->audio_expected.rate || !p.track_id || strcmp(p.track_id, b->audio_expected.track_id)))) {
        bad++; entry(c, S_CONFLICT, "verify-audio-resume", "verify", b->legacy, "stored audio checkpoint differs from registered retained state");
      }
      exr_audio_checkpoint_free(&p);
    } else {
      void *blob = NULL;
      size_t blob_size = 0;
      char digest[65];
      if (!lm_hm_get(&by_id, b->idkey, &n)) { bad++; entry(c, S_CONFLICT, "verify-book-missing", "verify", b->legacy, "mapped book %lld is not in the library", (long long)b->book_id); continue; }
      if (exr_library_blob(lib, b->book_id, 0, &blob, &blob_size, &c->err) != EXR_OK) { sdk_fail(c, "verify original"); break; }
      lm_sha_bytes(blob, blob_size, digest);
      exr_free(blob);
      if (strcmp(digest, b->sha)) { bad++; entry(c, S_CONFLICT, "verify-original-hash", "verify", b->legacy, "stored original differs from the pack digest"); }
      if (check_metadata && b->created) {
        const exr_book *lb = &books[n];
        if (strcmp(lb->title, b->title) || strcmp(lb->author, b->author) || strcmp(lb->tags, b->tags) || lb->favorite != b->favorite || lb->status != b->status || lb->position != b->position) {
          bad++; entry(c, S_CONFLICT, "verify-metadata", "verify", b->legacy, "stored metadata or position differs from the migrated values");
        }
        if (b->anchored && b->kind == K_REFLOW) {
          exr_anchor p;
          exr_anchor_state state;
          if (exr_library_progress_get(lib, b->book_id, &p, &state, &c->err) != EXR_OK) { sdk_fail(c, "verify progress"); break; }
          if (state != EXR_ANCHOR_FOUND || p.start != b->position) { bad++; entry(c, S_CONFLICT, "verify-progress", "verify", b->legacy, "stored reading-position selector differs"); }
          exr_anchor_free(&p);
        }
      }
    }
    if (c->out != O_NONE) break;
    for (at = head[i]; at != SIZE_MAX; at = next[at]) {
      lm_note *nn = &c->ledger.notes[at];
      if (!nn->located || nn->new_id <= 0) continue;
      if (b->kind == K_AUDIO) {
        exr_audio_bookmark *marks = NULL;
        size_t count = 0, j;
        int found = 0;
        char *expected_text = verified_note_text(nn);
        if (!expected_text) { fail(c, O_FAILED, "verify-failed", "invalid retained audio bookmark"); break; }
        if (!*expected_text) {
          char error[160];
          jv *record = lm_json_parse(nn->retained, strlen(nn->retained), error, sizeof(error));
          const char *quote = lm_get_str(record, "quote"), *trimmed;
          size_t length;
          if (quote) { trim(quote, strlen(quote), &trimmed, &length); free(expected_text); expected_text = lm_xdup(trimmed); }
          lm_json_free(record);
        }
        if (exr_library_audio_bookmarks(lib, b->audio_id, &marks, &count, &c->err) != EXR_OK) { free(expected_text); sdk_fail(c, "verify audio bookmarks"); break; }
        for (j = 0; j < count; j++) if (marks[j].id == nn->new_id && marks[j].position.offset_ms == nn->start &&
            marks[j].position.track_id && !strcmp(marks[j].position.track_id, b->legacy) &&
            !strcmp(marks[j].label, expected_text)) found = 1;
        free(expected_text); exr_audio_bookmarks_free(marks, count);
        if (!found) { bad++; entry(c, S_CONFLICT, "verify-note", "verify", nn->legacy, "stored audio bookmark differs from its mapping"); }
        continue;
      }
      if (b->kind == K_REFLOW) {
        exr_note *notes = NULL;
        size_t m, j;
        int found = 0;
        char *expected_text = verified_note_text(nn);
        if (!expected_text) { fail(c, O_FAILED, "verify-failed", "invalid retained annotation record"); break; }
        if (exr_library_notes(lib, b->book_id, &notes, &m, &c->err) != EXR_OK) { free(expected_text); sdk_fail(c, "verify notes"); break; }
        for (j = 0; j < m; j++) if (notes[j].id == nn->new_id && notes[j].start == nn->start && notes[j].end == nn->end && !strcmp(notes[j].text, expected_text)) found = 1;
        free(expected_text);
        exr_notes_free(notes, m);
        if (!found) { bad++; entry(c, S_CONFLICT, "verify-note", "verify", nn->legacy, "migrated note %lld missing or moved after reopen", (long long)nn->new_id); }
      } else {
        exr_fixed_note *notes = NULL;
        size_t m, j;
        int found = 0;
        char *expected_text = verified_note_text(nn);
        if (!expected_text) { fail(c, O_FAILED, "verify-failed", "invalid retained annotation record"); break; }
        if (exr_library_fixed_notes(lib, b->book_id, &notes, &m, &c->err) != EXR_OK) { free(expected_text); sdk_fail(c, "verify fixed notes"); break; }
        for (j = 0; j < m; j++) if (notes[j].id == nn->new_id && notes[j].page == nn->page && notes[j].start == nn->start && notes[j].end == nn->end && !strcmp(notes[j].text, expected_text)) found = 1;
        free(expected_text);
        exr_fixed_notes_free(notes, m);
        if (!found) { bad++; entry(c, S_CONFLICT, "verify-note", "verify", nn->legacy, "migrated fixed note %lld missing after reopen", (long long)nn->new_id); }
      }
    }
  }
  exr_books_free(books, count);
  free(head); free(next);
  if (c->out == O_NONE && (bad || injected(c, "verify-fail", 0))) fail(c, O_FAILED, "verify-failed", "%u verification mismatches after reopening the library", bad ? bad : 1);
  return c->out == O_NONE;
}

static void dump_library(ctx *c) {
  lm_sb b;
  exr_book *books = NULL;
  size_t count, i, j;
  lm_sb_init(&b);
  if (!check_target_header(c)) return;
  if (exr_library_open(c->target, &c->lib, &c->err) != EXR_OK) { fail(c, O_FAILED, "open-failed", "cannot open %s: %s", c->target, c->err.message); return; }
  if (exr_library_books(c->lib, "", &books, &count, &c->err) != EXR_OK) { sdk_fail(c, "listing library"); return; }
  lm_sb_str(&b, "{\"books\":[");
  for (i = count; i > 0; i--) {
    const exr_book *k = &books[i - 1];
    void *blob = NULL;
    size_t blob_size = 0, cover_size = 0;
    void *cover = NULL;
    char digest[65];
    if (i != count) lm_sb_str(&b, ",");
    if (exr_library_blob(c->lib, k->id, 0, &blob, &blob_size, &c->err) != EXR_OK) { sdk_fail(c, "reading original"); return; }
    lm_sha_bytes(blob ? blob : "", blob_size, digest);
    exr_free(blob);
    if (exr_library_blob(c->lib, k->id, 1, &cover, &cover_size, &c->err) != EXR_OK) { sdk_fail(c, "reading cover"); return; }
    exr_free(cover);
    lm_sb_fmt(&b, "{\"id\":%lld,\"format\":%d,\"title\":", (long long)k->id, (int)k->format);
    lm_sb_json(&b, k->title, strlen(k->title));
    lm_sb_str(&b, ",\"author\":");
    lm_sb_json(&b, k->author, strlen(k->author));
    lm_sb_str(&b, ",\"tags\":");
    lm_sb_json(&b, k->tags, strlen(k->tags));
    lm_sb_fmt(&b, ",\"favorite\":%d,\"status\":%d,\"position\":%zu,\"source_sha256\":\"%s\",\"source_bytes\":%zu,\"cover_bytes\":%zu", k->favorite, k->status, k->position, digest, blob_size, cover_size);
    if (k->format == EXR_PDF || k->format == EXR_CBZ) {
      exr_fixed_note *notes = NULL;
      size_t n;
      if (exr_library_fixed_notes(c->lib, k->id, &notes, &n, &c->err) != EXR_OK) { sdk_fail(c, "listing fixed notes"); return; }
      lm_sb_str(&b, ",\"notes\":[");
      for (j = 0; j < n; j++) {
        if (j) lm_sb_str(&b, ",");
        lm_sb_fmt(&b, "{\"id\":%lld,\"page\":%zu,\"start\":%zu,\"end\":%zu,\"text\":", (long long)notes[j].id, notes[j].page, notes[j].start, notes[j].end);
        lm_sb_json(&b, notes[j].text, strlen(notes[j].text));
        lm_sb_str(&b, ",\"exact\":");
        lm_sb_json(&b, notes[j].anchor.exact ? notes[j].anchor.exact : "", notes[j].anchor.exact_size);
        lm_sb_str(&b, "}");
      }
      lm_sb_str(&b, "]");
      exr_fixed_notes_free(notes, n);
    } else {
      exr_note *notes = NULL;
      exr_anchor progress;
      exr_anchor_state state;
      size_t n;
      if (exr_library_notes(c->lib, k->id, &notes, &n, &c->err) != EXR_OK) { sdk_fail(c, "listing notes"); return; }
      lm_sb_str(&b, ",\"notes\":[");
      for (j = 0; j < n; j++) {
        if (j) lm_sb_str(&b, ",");
        lm_sb_fmt(&b, "{\"id\":%lld,\"start\":%zu,\"end\":%zu,\"text\":", (long long)notes[j].id, notes[j].start == SIZE_MAX ? (size_t)0 : notes[j].start, notes[j].end == SIZE_MAX ? (size_t)0 : notes[j].end);
        lm_sb_json(&b, notes[j].text, strlen(notes[j].text));
        lm_sb_fmt(&b, ",\"located\":%s,\"exact\":", notes[j].start == SIZE_MAX ? "false" : "true");
        lm_sb_json(&b, notes[j].anchor.exact ? notes[j].anchor.exact : "", notes[j].anchor.exact ? strlen(notes[j].anchor.exact) : 0);
        lm_sb_str(&b, "}");
      }
      lm_sb_str(&b, "]");
      exr_notes_free(notes, n);
      if (exr_library_progress_get(c->lib, k->id, &progress, &state, &c->err) != EXR_OK) { sdk_fail(c, "reading progress"); return; }
      lm_sb_fmt(&b, ",\"progress_state\":%d,\"progress_start\":%zu", (int)state, progress.start);
      exr_anchor_free(&progress);
    }
    lm_sb_str(&b, "}");
  }
  exr_books_free(books, count);
  lm_sb_str(&b, "],\"audio\":[");
  {
    unsigned n = 0;
    for (i = 0; i < c->ledger.book_n; i++) {
      lm_book *k = &c->ledger.books[i];
      exr_audio_checkpoint p;
      exr_audio_bookmark *marks = NULL;
      size_t m;
      int found = 0;
      if (k->kind != K_AUDIO || !k->audio_id) continue;
      memset(&p, 0, sizeof(p));
      if (exr_library_audio_resume_get(c->lib, k->audio_id, &p, &found, &c->err) != EXR_OK || exr_library_audio_bookmarks(c->lib, k->audio_id, &marks, &m, &c->err) != EXR_OK) { sdk_fail(c, "reading audio"); return; }
      if (n++) lm_sb_str(&b, ",");
      lm_sb_str(&b, "{\"audio_id\":");
      lm_sb_json(&b, k->audio_id, strlen(k->audio_id));
      lm_sb_fmt(&b, ",\"resume_found\":%s,\"resume_ms\":%llu,\"bookmarks\":[", found ? "true" : "false", (unsigned long long)p.offset_ms);
      for (j = 0; j < m; j++) {
        if (j) lm_sb_str(&b, ",");
        lm_sb_fmt(&b, "{\"id\":%lld,\"offset_ms\":%llu,\"label\":", (long long)marks[j].id, (unsigned long long)marks[j].position.offset_ms);
        lm_sb_json(&b, marks[j].label, strlen(marks[j].label));
        lm_sb_str(&b, "}");
      }
      lm_sb_str(&b, "]}");
      exr_audio_checkpoint_free(&p);
      exr_audio_bookmarks_free(marks, m);
    }
  }
  lm_sb_str(&b, "]}\n");
  fwrite(b.p, 1, b.n, stdout);
  lm_sb_free(&b);
}

/* ---------- target lifecycle ---------- */
static int check_target_header(ctx *c) {
#ifdef EXR_MIGRATION_TX_CANDIDATE
  sqlite3 *db=NULL;sqlite3_stmt *stmt=NULL;int rc,app=-1,version=-1;
  lm_mirror_file target;lm_err path_error={{0},{0}};
  if(!lm_mirror_snapshot(c->target,0,0,&target,NULL,NULL,&path_error) || !target.present) {
    fail(c,O_REJECTED,"target-not-library","target must be a readable regular existing library");return 0;
  }
  /* Read commands must not report a recognized v3 policy as lifted, including
     schema-6 reads which will be refused below before any SDK upgrade. */
  {
    lm_mirror_intent policy;lm_mirror_file pending;
    if(!c->pending) c->pending=path_join(c->target,".migration-pending.json");
    if(!lm_mirror_intent_read(c->pending,&policy,&pending,&path_error)) {
      c->pending_retained=1;c->recovery_barrier=1;
      fail(c,O_FAILED,path_error.code,"%s",path_error.message);return 0;
    }
    if(pending.present && policy.version==3) {
      c->pending_retained=1;c->recovery_barrier=1;c->mirror_state="recovery-unverified";
    }
  }
  rc=sqlite3_open_v2(c->target,&db,SQLITE_OPEN_READONLY | SQLITE_OPEN_FULLMUTEX,NULL);
  if(rc==SQLITE_OK) rc=sqlite3_prepare_v2(db,"PRAGMA application_id",-1,&stmt,NULL);
  if(rc==SQLITE_OK && sqlite3_step(stmt)==SQLITE_ROW) app=sqlite3_column_int(stmt,0);
  else if(rc==SQLITE_OK) rc=sqlite3_errcode(db);
  sqlite3_finalize(stmt);stmt=NULL;
  if(rc==SQLITE_OK) rc=sqlite3_prepare_v2(db,"PRAGMA user_version",-1,&stmt,NULL);
  if(rc==SQLITE_OK && sqlite3_step(stmt)==SQLITE_ROW) version=sqlite3_column_int(stmt,0);
  else if(rc==SQLITE_OK) rc=sqlite3_errcode(db);
  sqlite3_finalize(stmt);if(db) sqlite3_close(db);
  if(rc!=SQLITE_OK) { fail(c,O_REJECTED,"target-not-library","cannot read the target SQLite library");return 0; }
  if(app!=1163416131 || version!=7) {
    fail(c,O_REJECTED,"target-schema","read commands require a schema 7 EXReader library");return 0;
  }
  c->target_version=version;return 1;
#else
  unsigned char h[100];
  FILE *f = lm_fopen(c->target, "rb");
  uint32_t user_version, app_id;
  if (!f) { fail(c, O_FAILED, "target-unreadable", "cannot read existing target %s", c->target); return 0; }
  if (fread(h, 1, sizeof(h), f) != sizeof(h) || memcmp(h, "SQLite format 3", 16)) { fclose(f); fail(c, O_REJECTED, "target-not-library", "%s is not an SQLite library; refusing to touch it", c->target); return 0; }
  fclose(f);
  user_version = (uint32_t)h[60] << 24 | (uint32_t)h[61] << 16 | (uint32_t)h[62] << 8 | h[63];
  app_id = (uint32_t)h[68] << 24 | (uint32_t)h[69] << 16 | (uint32_t)h[70] << 8 | h[71];
  if (app_id != 1163416131u || (user_version != 6u && user_version != 7u)) {
    fail(c, O_REJECTED, "target-schema", "target library is schema %u (application id %u); supported target schemas are 6 and 7", user_version, app_id);
    return 0;
  }
  c->target_version = (int)user_version;
  if (user_version == 6u && strcmp(c->cmd, "migrate")) {
    fail(c, O_REJECTED, "target-schema", "schema 6 requires migration before this command; the original is not upgraded in place");
    return 0;
  }
  return 1;
#endif
}

/* A raw-file preimage is only valid if no SQLite sidecar holds committed data.
   Require a closed, checkpointed old library and recheck before publication. */
static int old_target_quiescent(ctx *c) {
  static const char *suffixes[] = {"-wal", "-shm", "-journal"};
  size_t i;
  for (i = 0; i < sizeof(suffixes)/sizeof(suffixes[0]); i++) {
    char *name = path_join(c->target, suffixes[i]);
    int exists = lm_exists(name);
    free(name);
    if (exists) { fail(c, O_BUSY, "target-busy", "close and checkpoint the old library before migration"); return 0; }
  }
  return 1;
}

#ifndef EXR_MIGRATION_TX_CANDIDATE
/* A transactional ledger cannot safely be maintained by the file-replacement
   migrator, which only reads and writes the external legacy sidecar. */
static int reject_transactional_ledger(ctx *c) {
  sqlite3 *db = NULL;
  sqlite3_stmt *stmt = NULL;
  int rc = sqlite3_open_v2(c->target, &db, SQLITE_OPEN_READONLY | SQLITE_OPEN_FULLMUTEX, NULL);
  if (rc == SQLITE_OK)
    rc = sqlite3_prepare_v2(db, "SELECT 1 FROM sqlite_master WHERE type='table' AND name='exr_migration_ledger'", -1, &stmt, NULL);
  if (rc == SQLITE_OK) rc = sqlite3_step(stmt);
  sqlite3_finalize(stmt);
  if (db) sqlite3_close(db);
  if (rc == SQLITE_ROW) {
    fail(c, O_REJECTED, "transactional-ledger", "this library has a transactional migration ledger; use the transaction migrator");
    return 0;
  }
  if (rc != SQLITE_DONE) {
    fail(c, O_BUSY, "target-busy", "cannot inspect the target ledger safely; close other handles and retry");
    return 0;
  }
  return 1;
}
#endif

static int snapshot_old_target(ctx *c) {
  sqlite3 *source = NULL, *dest = NULL;
  sqlite3_backup *backup = NULL;
  int rc, finished = SQLITE_ERROR;
  if (!old_target_quiescent(c)) return 0;
  rc = sqlite3_open_v2(c->target, &source, SQLITE_OPEN_READONLY | SQLITE_OPEN_FULLMUTEX, NULL);
  if (rc == SQLITE_OK) rc = sqlite3_open_v2(c->stage, &dest, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE | SQLITE_OPEN_FULLMUTEX, NULL);
  if (rc == SQLITE_OK) {
    backup = sqlite3_backup_init(dest, "main", source, "main");
    if (backup) { rc = sqlite3_backup_step(backup, -1); finished = sqlite3_backup_finish(backup); }
    else rc = sqlite3_errcode(dest);
  }
  if (dest) sqlite3_close(dest);
  if (source) sqlite3_close(source);
  if (rc != SQLITE_DONE || finished != SQLITE_OK) {
    fail(c, O_BUSY, "target-busy", "cannot snapshot the old library (SQLite %d); close all handles and retry", rc);
    return 0;
  }
  return 1;
}
#ifdef EXR_MIGRATION_TX_CANDIDATE
static int mirror_fail(ctx *c, const lm_err *e) {
  fail(c, O_FAILED, e->code, "%s", e->message);
  return 0;
}
static int mirror_sidecar_snapshot(ctx *c, lm_mirror_file *out) {
  lm_err e = {{0}, {0}};
#ifdef EXR_MIGRATION_RECOVERY_CANDIDATE
  if(lr_snapshot(c->recovery,c->sidecar,1,LM_RECOVERY_LIMIT,out,NULL,NULL,&e)) return 1;
#else
  if (lm_mirror_snapshot(c->sidecar, 1, LM_MIRROR_LEDGER_MAX, out, NULL, NULL, &e)) return 1;
#endif
  fail(c, (!strcmp(c->cmd, "verify") || !strcmp(c->cmd, "dump")) ? O_REJECTED : O_FAILED,
       "ledger-unreadable", "%s", e.message);
  return 0;
}
static void mirror_run_id(ctx *c) {
  snprintf(c->run, sizeof(c->run), "%llx-%x", (unsigned long long)time(NULL), (unsigned)
#ifdef _WIN32
    _getpid()
#else
    getpid()
#endif
  );
}
static int mirror_owner_unchanged(ctx *c, const char *path, const lm_mirror_file *expected) {
  lm_mirror_file now;
  lm_err e = {{0}, {0}};
  if (!lm_mirror_snapshot(path, 0, 0, &now, NULL, NULL, &e)) return mirror_fail(c, &e);
  if (!now.present || !lm_mirror_same_file(expected, &now)) {
    fail(c, O_FAILED, "target-changed", "library owner pathname changed; pending evidence is retained"); return 0;
  }
  return 1;
}
static int mirror_write_stage(ctx *c, const char *path, const void *data, size_t size, int *owned) {
  FILE *f = lm_fopen(path, "wbx");
  int ok;
  *owned = 0;
  if (!f) { fail(c, O_FAILED, "mirror-stage", "cannot exclusively create the mirror export stage"); return 0; }
  *owned = 1;
  ok = fwrite(data, 1, size, f) == size && lm_sync(f);
  if (fclose(f)) ok = 0;
  if (!ok) { fail(c, O_FAILED, "mirror-stage", "mirror export stage write failed"); return 0; }
  return 1;
}
static int mirror_pause(ctx *c, const char *hook, const char *suffix) {
  char *ready, *resume;
  unsigned wait;int resumed=0;
  if(!injected(c,hook,0)) return 1;
  ready=path_join(c->target,suffix);
  resume=path_join(ready,".resume");
  if(!write_file(ready,"ready",5)) { free(ready);free(resume);fail(c,O_FAILED,"review-hook-failed","cannot create mirror synchronization marker");return 0; }
  for(wait=0;wait<400 && !cancel_cb(c);wait++) {
    if(lm_exists(resume)) { resumed=1;break; }
#ifdef _WIN32
    Sleep(50);
#else
    struct timespec delay={0,50000000};nanosleep(&delay,NULL);
#endif
  }
  lm_remove(ready);lm_remove(resume);free(ready);free(resume);
  if(!resumed) { fail(c,cancel_cb(c)?O_CANCELLED:O_FAILED,cancel_cb(c)?"cancelled":"review-hook-timeout","mirror synchronization interrupted; pending retained");return 0; }
  return 1;
}
static char *mirror_artifact_path(ctx *c, const char *kind, const char *token) {
  char *path=lm_xalloc(strlen(c->sidecar)+strlen(kind)+strlen(token)+2);
  sprintf(path,"%s%s%s",c->sidecar,kind,token);return path;
}
/* The caller has already verified mirror disposition and released its recovery
   owner. Missing retired artifacts are idempotent; foreign artifacts are not. */
static int mirror_remove_artifact(const char *path,const lm_mirror_file *expected,lm_err *e) {
  lm_mirror_file now;
  if(!lm_mirror_snapshot(path,1,LM_MIRROR_LEDGER_MAX,&now,NULL,NULL,e)) return 0;
  if(!now.present) return 1;
  if(!expected->present || !lm_mirror_same_file(expected,&now) || !lm_mirror_same_bytes(expected,&now)) {
    lm_err_set(e,"mirror-artifact-changed","refusing to delete an artifact not owned by the pending intent");return 0;
  }
  if(!lm_remove(path)) { lm_err_set(e,"mirror-cleanup-pending","cannot remove an owned mirror artifact");return 0; }
  return 1;
}
static int mirror_retire_artifacts(ctx *c,const lm_mirror_intent *intent,lm_err *e) {
  char *before,*planned;int ok;
  if(intent->version!=2 && intent->version!=3) return 1;
  before=mirror_artifact_path(c,".before-",intent->artifact_token);
  planned=mirror_artifact_path(c,".staged-",intent->artifact_token);
  ok=mirror_remove_artifact(before,&intent->mirror_preimage,e) &&
     mirror_remove_artifact(planned,&intent->mirror_after,e);
  free(before);free(planned);return ok;
}
/* Restore external bytes/absence only. No database file is ever restored here.
   A copied preimage may become the mirror by rename; v2 recognizes that file ID
   on retry even if the old preimage pathname no longer exists. */
static int mirror_restore_original(ctx *c,const lm_mirror_intent *intent) {
  lm_mirror_file now,preimage,after;lm_err e={{0},{0}};
  char *path=NULL;int ok=0;
  if(intent->version!=2 || !intent->target_was_present) {
    fail(c,O_FAILED,"mirror-restore-contract","only an existing-target v2 intent can restore an external mirror baseline");return 0;
  }
  if(!mirror_sidecar_snapshot(c,&now)) return 0;
  if(lm_mirror_same_bytes(&now,&intent->mirror_before)) return 1; /* no overwrite */
  if(now.present && !lm_mirror_planned_file(intent,&now)) {
    fail(c,O_FAILED,"mirror-recovery-conflict","external mirror is neither baseline bytes nor the owned planned file");return 0;
  }
  if(intent->mirror_before.present) {
    path=mirror_artifact_path(c,".before-",intent->artifact_token);
    if(!lm_mirror_snapshot(path,1,LM_MIRROR_LEDGER_MAX,&preimage,NULL,NULL,&e)) { mirror_fail(c,&e);goto done; }
    if(!preimage.present || !lm_mirror_same_file(&preimage,&intent->mirror_preimage) ||
       !lm_mirror_same_bytes(&preimage,&intent->mirror_before)) {
      fail(c,O_FAILED,"mirror-preimage-unavailable","exact owned external mirror preimage is unavailable; intent retained");goto done;
    }
    if(!(now.present?lm_replace(path,c->sidecar):lm_publish_new(path,c->sidecar))) {
      fail(c,O_FAILED,"mirror-restore-failed","cannot publish the exact external mirror preimage; intent retained");goto done;
    }
  } else if(now.present && !lm_remove(c->sidecar)) {
    fail(c,O_FAILED,"mirror-restore-failed","cannot remove the owned planned mirror to restore original absence");goto done;
  }
  if(!mirror_sidecar_snapshot(c,&after)) goto done;
  if(!lm_mirror_same_bytes(&after,&intent->mirror_before)) {
    fail(c,O_FAILED,"mirror-restore-failed","external mirror baseline was not restored exactly");goto done;
  }
  ok=1;
done:
  free(path);return ok;
}
static int mirror_prepare_existing(ctx *c) {
  lm_err e={{0},{0}};lm_mirror_intent *intent=&c->mirror_intent;
  if(!c->target_existed) return 1;
  if(!lm_mirror_snapshot(c->sidecar_tmp,1,LM_MIRROR_LEDGER_MAX,&intent->mirror_after,NULL,NULL,&e)) return mirror_fail(c,&e);
  if(!intent->mirror_after.present || strcmp(intent->mirror_after.sha,intent->after_sha) ||
     !lm_mirror_same_file(&intent->mirror_after,&c->sidecar_tmp_file)) {
    fail(c,O_FAILED,"mirror-stage-changed","planned mirror stage differs from transactional ledger bytes");return 0;
  }
  if(c->mirror_before.present) {
    c->mirror_preimage=mirror_artifact_path(c,".before-",c->run);
    if(!lm_mirror_copy_new(c->sidecar,&c->mirror_before,c->mirror_preimage,&intent->mirror_preimage,&c->mirror_preimage_owned,&e)) return mirror_fail(c,&e);
  }
  strcpy(intent->artifact_token,c->run);intent->version=3;return 1;
}
static int mirror_publish_precommit(ctx *c) {
  lm_mirror_file now,planned,after;lm_err e={{0},{0}};
  if(!mirror_sidecar_snapshot(c,&now)) return 0;
  if(!lm_mirror_same_file(&now,&c->mirror_before) || !lm_mirror_same_bytes(&now,&c->mirror_before)) {
    fail(c,O_FAILED,"ledger-changed","external mirror changed before pre-COMMIT publication");return 0;
  }
  if(!lm_mirror_snapshot(c->sidecar_tmp,1,LM_MIRROR_LEDGER_MAX,&planned,NULL,NULL,&e)) return mirror_fail(c,&e);
  if(!lm_mirror_planned_file(&c->mirror_intent,&planned)) {
    fail(c,O_FAILED,"mirror-stage-changed","planned mirror stage identity or bytes changed");return 0;
  }
  if(!mirror_pause(c,"precommit-publish-pause",".precommit-publish-ready") || cancel_cb(c)) {
    fail(c,O_CANCELLED,"cancelled","cancelled before pre-COMMIT mirror publication");return 0;
  }
  /* Recheck after the explicit rendezvous, not just before it. This closes the
     deterministic hook window; it is still not a filesystem compare-and-swap. */
  if(!mirror_owner_unchanged(c,c->target,&c->owner_before) || !mirror_sidecar_snapshot(c,&now)) return 0;
  if(!lm_mirror_same_file(&now,&c->mirror_before) || !lm_mirror_same_bytes(&now,&c->mirror_before)) {
    fail(c,O_FAILED,"ledger-changed","external mirror changed at the pre-COMMIT publication boundary");return 0;
  }
  if(!lm_mirror_snapshot(c->sidecar_tmp,1,LM_MIRROR_LEDGER_MAX,&planned,NULL,NULL,&e)) return mirror_fail(c,&e);
  if(!lm_mirror_planned_file(&c->mirror_intent,&planned)) {
    fail(c,O_FAILED,"mirror-stage-changed","planned mirror stage changed at the publication boundary");return 0;
  }
  if(cancel_cb(c)) { fail(c,O_CANCELLED,"cancelled","cancelled immediately before external mirror publication");return 0; }
  if(!lm_mirror_same_bytes(&now,&planned)) {
    /* Real publication site. Failure precedes SDK COMMIT; rollback is attempted
       by the caller, never inferred from unchanged ledger hashes. */
    if(injected(c,"sidecar-fail",0) || injected(c,"rollback-fail",0) ||
       !(now.present?lm_replace(c->sidecar_tmp,c->sidecar):lm_publish_new(c->sidecar_tmp,c->sidecar))) {
      fail(c,O_FAILED,"ledger-publish-failed","external mirror publication failed before database COMMIT");return 0;
    }
    if(!mirror_sidecar_snapshot(c,&after)) return 0;
    if(!lm_mirror_planned_file(&c->mirror_intent,&after)) {
      fail(c,O_FAILED,"mirror-publication-unknown","published mirror identity or bytes are not confirmed; intent retained");return 0;
    }
  }
  c->mirror_state="published-before-commit";
  if(injected(c,"precommit-cancel",0)) g_cancel=1;
  if(!mirror_pause(c,"precommit-mirror-pause",".precommit-mirror-ready") || cancel_cb(c)) {
    fail(c,O_CANCELLED,"cancelled","cancelled after mirror publication but before database COMMIT");return 0;
  }
  return 1;
}
static int mirror_abort_precommit(ctx *c) {
  lm_err e={{0},{0}};
  exr_status status;
  /* This function is only reached before any COMMIT attempt in this process. */
  c->rollback_requested=1;
  status=exr_library_migration_finish(c->lib,0,&c->err);
  c->rollback_status=status;c->rollback_status_valid=1;
  if(status!=EXR_OK) {
    c->out=O_NONE;
    fail(c,O_INCONSISTENT,"rollback-failed","pre-COMMIT rollback was not confirmed: %s; mirror intent and byte preimage retained",c->err.message);return 0;
  }
  c->target_commit=C_NOT_COMMITTED;c->rolled_back=1;
  if(c->mirror_intent.version==3) {
    /* Literal SDK acknowledgement is not independent whole-library proof.
       Keep the immutable, already durable policy and every owned mirror byte.
       In particular do not consume the sole preimage by a restoring rename. */
    c->recovery_barrier=1;c->mirror_state="recovery-unverified";
    entry(c,S_WARNING,"recovery-unverified","mirror",NULL,
          "SDK acknowledged rollback; full recovery is unverified; intent, mirror evidence and migration barrier retained");
    return 0;
  }
  if(!mirror_restore_original(c,&c->mirror_intent)) {
    c->out=O_NONE;
    fail(c,O_INCONSISTENT,"mirror-restore-failed","database transaction rolled back, but external mirror baseline could not be restored; intent and evidence retained");return 0;
  }
  c->mirror_state="baseline-restored";
  if(!mirror_retire_artifacts(c,&c->mirror_intent,&e) ||
     !lm_mirror_intent_remove(c->pending,&c->pending_snapshot,&e)) {
    c->mirror_state="cleanup-pending";
    entry(c,S_WARNING,"mirror-cleanup-pending","mirror",NULL,"%s",e.message);return 0;
  }
  c->pending_retained=0;
  return 0; /* the requested operation still failed/cancelled, despite cleanup */
}

/* Only a COMMIT actually acknowledged in this invocation can use this path.
   v3 already published the external mirror before COMMIT. Do not open another
   SDK migration owner merely to roll it back and call that recovery proof. */
static int mirror_complete_committed_v3(ctx *c) {
  lm_mirror_intent intent,observed_intent;
  lm_mirror_file pending,now,observed_pending;
  lm_err e={{0},{0}};
  if(c->target_commit!=C_COMMITTED || !c->target_existed || c->mirror_intent.version!=3 ||
     !c->pending_snapshot.present || strcmp(c->mirror_intent.artifact_token,c->run)) {
    fail(c,O_FAILED,"mirror-commit-context","same-process COMMIT context is unavailable; evidence retained");return 0;
  }
  if(!lm_mirror_intent_read(c->pending,&intent,&pending,&e)) return mirror_fail(c,&e);
  if(intent.version!=3 || strcmp(intent.artifact_token,c->run) ||
     !lm_mirror_same_file(&pending,&c->pending_snapshot) ||
     !lm_mirror_same_bytes(&pending,&c->pending_snapshot)) {
    fail(c,O_FAILED,"mirror-intent-changed","COMMIT intent identity or bytes changed; evidence retained");return 0;
  }
  if(!mirror_owner_unchanged(c,c->target,&c->owner_before) || !mirror_sidecar_snapshot(c,&now)) return 0;
  if(!lm_mirror_same_bytes(&now,&intent.mirror_after) ||
     !(lm_mirror_planned_file(&intent,&now) ||
       (lm_mirror_same_file(&now,&c->mirror_before) && lm_mirror_same_bytes(&now,&c->mirror_before)))) {
    fail(c,O_FAILED,"mirror-not-converged","committed mirror identity or bytes changed; evidence retained");return 0;
  }
  c->mirror_state="commit-planned-mirror-matched";
  if(cancel_cb(c) || !mirror_pause(c,"mirror-pause",".mirror-ready")) {
    fail(c,O_CANCELLED,"cancelled","COMMIT was acknowledged; interrupted cleanup retains evidence");return 0;
  }
  if(!lm_mirror_intent_read(c->pending,&observed_intent,&observed_pending,&e)) return mirror_fail(c,&e);
  if(!lm_mirror_same_file(&observed_pending,&pending) || !lm_mirror_same_bytes(&observed_pending,&pending)) {
    fail(c,O_FAILED,"mirror-intent-changed","intent changed before committed artifact cleanup; evidence retained");return 0;
  }
  if(!mirror_owner_unchanged(c,c->target,&c->owner_before) || !mirror_sidecar_snapshot(c,&now)) return 0;
  if(!lm_mirror_same_bytes(&now,&intent.mirror_after) ||
     !(lm_mirror_planned_file(&intent,&now) ||
       (lm_mirror_same_file(&now,&c->mirror_before) && lm_mirror_same_bytes(&now,&c->mirror_before)))) {
    fail(c,O_FAILED,"mirror-not-converged","mirror changed at committed cleanup boundary; evidence retained");return 0;
  }
  /* Original SDK owner is closed before entry: an ordinary writer may proceed.
     No old DB bytes are restored, including after artifact-cleanup failures. */
  if(!mirror_retire_artifacts(c,&intent,&e)) {
    if(strcmp(e.code,"mirror-cleanup-pending")) return mirror_fail(c,&e);
    c->mirror_state="cleanup-pending";
    entry(c,S_WARNING,"mirror-cleanup-pending","mirror",NULL,"%s",e.message);return 2;
  }
  if(!mirror_pause(c,"mirror-retire-pause",".mirror-retire-ready") || cancel_cb(c)) {
    fail(c,O_CANCELLED,"cancelled","COMMIT acknowledged; intent retirement interrupted");return 0;
  }
  if(!lm_mirror_intent_read(c->pending,&observed_intent,&observed_pending,&e)) return mirror_fail(c,&e);
  if(!lm_mirror_same_file(&observed_pending,&pending) || !lm_mirror_same_bytes(&observed_pending,&pending)) {
    fail(c,O_FAILED,"mirror-intent-changed","intent changed at final retirement; foreign intent retained");return 0;
  }
  if(!mirror_owner_unchanged(c,c->target,&c->owner_before) || !mirror_sidecar_snapshot(c,&now)) return 0;
  if(!lm_mirror_same_bytes(&now,&intent.mirror_after) ||
     !(lm_mirror_planned_file(&intent,&now) ||
       (lm_mirror_same_file(&now,&c->mirror_before) && lm_mirror_same_bytes(&now,&c->mirror_before)))) {
    fail(c,O_FAILED,"mirror-not-converged","mirror changed at final intent retirement; intent retained");return 0;
  }
  /* intent_remove independently checks the exact original file and bytes at
     this final boundary; it never removes a replacement/foreign intent. */
  if(!lm_mirror_intent_remove(c->pending,&pending,&e)) {
    /* Only a real unlink refusal of our exact owned intent is benign pending
       cleanup. A race-time identity/byte mismatch must remain a refusal. */
    if(strcmp(e.code,"mirror-pending")) return mirror_fail(c,&e);
    c->mirror_state="cleanup-pending";
    entry(c,S_WARNING,"mirror-cleanup-pending","mirror",NULL,"%s",e.message);return 2;
  }
  c->pending_retained=0;c->recovery_barrier=0;return 1;
}

/* Returns 1 when no pending remains; 2 for bytes-converged/cleanup-pending;
   0 for a conflict/error. Never opens a missing target through the CREATE API. */
static int mirror_reconcile(ctx *c) {
  lm_mirror_intent intent;
  lm_mirror_file pending, target, mirror, stage, after;
  lm_err e = {{0}, {0}};
  exr_library *owner = NULL;
  void *data = NULL;
  size_t size = 0;
  int found = 0, result = 0, owner_finished = 0, temp_owned = 0;
  char *temp = NULL, *stage_path = NULL, digest[65];
  lm_mirror_action action;
  memset(&stage, 0, sizeof(stage));
  if (!lm_mirror_intent_read(c->pending, &intent, &pending, &e)) { c->pending_retained = 1; return mirror_fail(c, &e); }
  if (!pending.present) return 1;
  c->pending_retained = 1;
  c->mirror_state = "pending";
  if(intent.version==3) {
    c->recovery_barrier=1;c->mirror_state="recovery-unverified";
    fail(c,O_BUSY,"recovery-unverified","pending v3 requires independent full recovery verification; no database or mirror changed; evidence and migration barrier retained");
    return 0;
  }
  if (!lm_mirror_snapshot(c->target, 0, 0, &target, NULL, NULL, &e)) {
    mirror_fail(c, &e); goto done;
  }
  if (!strcmp(c->cmd,"recover-mirror")) c->target_existed = target.present;
  if (!mirror_sidecar_snapshot(c, &mirror)) goto done;
  if (!target.present) {
    if (!intent.target_was_present) {
      stage_path = lm_xalloc(strlen(c->target) + 64);
      sprintf(stage_path, "%s.migrating-%s", c->target, intent.stage_token);
      if (!lm_mirror_snapshot(stage_path, 0, 0, &stage, NULL, NULL, &e)) { mirror_fail(c, &e); goto done; }
    }
  } else {
    if (strcmp(target.identity, intent.target_identity)) {
      fail(c, O_FAILED, "mirror-recovery-conflict", "pending intent belongs to a different target file"); goto done;
    }
    if (exr_library_migration_open(c->target, &owner, &c->err) != EXR_OK) {
      fail(c, O_BUSY, "target-busy", "cannot acquire a fresh recovery owner: %s", c->err.message); goto done;
    }
    if (!mirror_owner_unchanged(c, c->target, &target)) goto done;
    if (exr_library_migration_ledger_get(owner, &data, &size, &found, &c->err) != EXR_OK) {
      sdk_fail(c, "reading current ledger for mirror recovery"); goto done;
    }
  }
  action = lm_mirror_plan(&intent, &target, &stage, found, data, size, &mirror, &e);
  if (action == LM_MIRROR_CONFLICT) { mirror_fail(c, &e); goto done; }
  if (cancel_cb(c)) { fail(c, O_CANCELLED, "cancelled", "mirror recovery cancelled; pending intent retained"); goto done; }
  if(action==LM_MIRROR_RESTORE_BEFORE && !mirror_restore_original(c,&intent)) goto done;
  if (action == LM_MIRROR_EXPORT_CURRENT) {
    temp = lm_xalloc(strlen(c->sidecar) + 64);
    sprintf(temp, "%s.recover-%s", c->sidecar, c->run);
    if (!mirror_write_stage(c, temp, data, size, &temp_owned)) goto done;
    if (!mirror_owner_unchanged(c, c->target, &target)) goto done;
    if (!mirror_sidecar_snapshot(c, &after)) goto done;
    if (!lm_mirror_same_file(&mirror, &after) || !lm_mirror_same_bytes(&mirror, &after)) {
      fail(c, O_FAILED, "ledger-changed", "external mirror changed before publication; intent retained"); goto done;
    }
    if(!mirror_pause(c,"mirror-prepublish-pause",".mirror-prepublish-ready") || cancel_cb(c)) {
      fail(c,O_CANCELLED,"cancelled","mirror publication cancelled; pending intent retained; no database restoration attempted");goto done;
    }
    /* This hook now exercises the real mirror-publication site. It cannot
       truthfully promise that the already committed database was rolled back. */
    if (injected(c, "sidecar-fail", 0) || injected(c, "rollback-fail", 0) ||
        !(mirror.present ? lm_replace(temp, c->sidecar) : lm_publish_new(temp, c->sidecar))) {
      fail(c, O_FAILED, "ledger-publish-failed", "database outcome is separate; external mirror publication failed and recovery is pending"); goto done;
    }
  }
  if (found) {
    if (!mirror_sidecar_snapshot(c, &after)) goto done;
    lm_sha_bytes(data, size, digest);
    if (!after.present || after.size != size || strcmp(after.sha, digest)) {
      fail(c, O_FAILED, "mirror-not-converged", "external mirror does not match the current internal ledger; intent retained"); goto done;
    }
    c->mirror_state = "bytes-converged";
  } else c->mirror_state = action == LM_MIRROR_ABANDONED_NEW ? "no-authoritative-target" : "no-internal-ledger";
  if(cancel_cb(c)) { fail(c,O_CANCELLED,"cancelled","mirror disposition observed; cancellation leaves pending intent retained");goto done; }
  if(!mirror_pause(c,"mirror-pause",".mirror-ready")) goto done;
  if (owner) {
    if (exr_library_migration_finish(owner, 0, &c->err) != EXR_OK) { sdk_fail(c, "releasing recovery owner"); goto done; }
    owner_finished = 1;
  }
  if(cancel_cb(c)) { fail(c,O_CANCELLED,"cancelled","recovery owner released; cancellation leaves pending intent retained");goto done; }
  /* Only after explicit recovery ROLLBACK succeeds may the intent be retired. */
  if (!mirror_retire_artifacts(c,&intent,&e)) {
    c->mirror_state = "cleanup-pending";
    entry(c, S_WARNING, "mirror-cleanup-pending", "mirror", NULL, "%s", e.message);
    result = 2; goto done;
  }
  if(!mirror_pause(c,"mirror-retire-pause",".mirror-retire-ready")) goto done;
  if (!lm_mirror_intent_remove(c->pending, &pending, &e)) {
    c->mirror_state = "cleanup-pending";
    entry(c, S_WARNING, "mirror-cleanup-pending", "mirror", NULL, "%s", e.message);
    result = 2; goto done;
  }
  c->pending_retained = 0;
  result = 1;
done:
  if (owner && !owner_finished) {
    exr_error release_error;
    /* A failed cleanup cannot erase the earlier failure or upgrade knowledge. */
    (void)exr_library_migration_finish(owner, 0, &release_error);
  }
  if (owner) exr_library_close(owner);
  exr_free(data);
  if (result && temp_owned) lm_remove(temp); /* this invocation's owned temp only */
  free(temp); free(stage_path);
  return result;
}
/* Read-only commands remain usable with a valid pending intent and stale lock.
   This checks mirror provenance only; normal pack/touched verification follows. */
static int mirror_check_read(ctx *c, const void *data, size_t size) {
  lm_mirror_file target, mirror, pending;
  lm_mirror_intent intent;
  lm_err e = {{0}, {0}};
  char digest[65];
  int explained;
  if (!c->pending) c->pending = path_join(c->target, ".migration-pending.json");
  if (!mirror_sidecar_snapshot(c, &mirror)) return 0;
  if (!lm_mirror_snapshot(c->target, 0, 0, &target, NULL, NULL, &e) ||
      !lm_mirror_intent_read(c->pending, &intent, &pending, &e)) return mirror_fail(c, &e);
  lm_sha_bytes(data, size, digest);
  if (pending.present) {
    c->pending_retained = 1;
    if(intent.version==3) c->recovery_barrier=1;
    c->mirror_state = intent.version==3?"recovery-unverified":"pending";
    if (!target.present || strcmp(target.identity, intent.target_identity) ||
        (strcmp(digest, intent.after_sha) && (!intent.before_found || strcmp(digest, intent.before_sha)))) {
      fail(c, O_FAILED, "mirror-recovery-conflict", "pending intent does not explain the current target/ledger"); return 0;
    }
  }
  if (mirror.present && mirror.size == size && !strcmp(mirror.sha, digest)) {
    if (!pending.present) c->mirror_state = "bytes-equal";
    return 1;
  }
  if (!mirror.present) { if (!pending.present) c->mirror_state = "missing"; return 1; }
  explained = pending.present && (lm_mirror_original_file(&intent,&mirror) || !strcmp(mirror.sha, intent.after_sha));
  if (explained) return 1;
  entry(c, S_CONFLICT, "mirror-diverged", "mirror", NULL, "external mirror differs from the current ledger without a valid explanation");
  fail(c, O_FAILED, !strcmp(c->cmd,"verify")?"verify-failed":"mirror-diverged",
       "external mirror is not explained by the current ledger or pending intent"); return 0;
}
#endif

#ifdef EXR_MIGRATION_TX_CANDIDATE
/* The stable-path contract still applies: these are identity rechecks, not a
   filesystem compare-and-swap. Never unlink a foreign/replaced lock in cleanup. */
static int mirror_lock_release(ctx *c) {
  lm_mirror_file now;lm_err e={{0},{0}};
  if(!c->lock_held) return 1;
  if(!c->lock_snapshot.present || !lm_mirror_snapshot(c->lock,1,128,&now,NULL,NULL,&e) ||
     !lm_mirror_same_file(&now,&c->lock_snapshot) || !lm_mirror_same_bytes(&now,&c->lock_snapshot)) {
    entry(c,S_WARNING,"migration-lock-changed","lock",NULL,"lock identity or nonce changed; not removed");
    c->lock_held=0;return 0;
  }
  if(!lm_remove(c->lock)) {
    entry(c,S_WARNING,"migration-lock-cleanup-pending","lock",NULL,"owned lock could not be removed");
    c->lock_held=0;c->lock_retained=1;return 0;
  }
  c->lock_held=0;return 1;
}
static int mirror_lock_acquire(ctx *c) {
  lm_mirror_intent prior;lm_mirror_file pending;lm_err e={{0},{0}};
  FILE *lock;int ok;char expected[32];char *bytes=NULL;size_t size=0;
  if(!lm_mirror_intent_read(c->pending,&prior,&pending,&e)) {
    c->pending_retained=1;c->recovery_barrier=1;return mirror_fail(c,&e);
  }
  if(pending.present && prior.version==3) {
    c->pending_retained=1;c->recovery_barrier=1;c->mirror_state="recovery-unverified";
    /* --break-lock is not permission to erase this versioned recovery policy.
       Leave an existing lock untouched; if absent, reserve the default old-tool
       barrier below before reporting the retained recovery requirement. */
    if(lm_path_state(c->lock)!=0) {
      fail(c,O_BUSY,"recovery-unverified","v3 recovery remains unverified; existing migration barrier and evidence retained");return 0;
    }
  } else if(c->break_lock) {
    /* Existing v1/v2 explicit stale-lock contract, unchanged. New v3 never
       reaches this path, and normal cleanup only removes its exact own lock. */
    lm_remove(c->lock);
  }
  /* The nonce is verified as raw bytes. Avoid CRT LF-to-CRLF translation while
     retaining exclusive creation and the exact identity/content checks below. */
  lock=lm_fopen(c->lock,"wbx");
  if(!lock) {
    fail(c,lm_exists(c->lock)?O_BUSY:O_FAILED,"target-busy","cannot acquire the shared migration lock");return 0;
  }
  snprintf(expected,sizeof(expected),"%s\n",c->run);
  ok=fwrite(expected,1,strlen(expected),lock)==strlen(expected) && lm_sync(lock);
  if(fclose(lock)) ok=0;
  if(!ok || !lm_mirror_snapshot(c->lock,1,128,&c->lock_snapshot,&bytes,&size,&e) ||
     size!=strlen(expected) || memcmp(bytes,expected,size)) {
    free(bytes);fail(c,O_FAILED,"lock-failed","shared lock nonce could not be confirmed; lock left untouched");return 0;
  }
  free(bytes);c->lock_held=1;
  if(c->recovery_barrier) {
    fail(c,O_BUSY,"recovery-unverified","v3 recovery remains unverified; migration barrier reserved and evidence retained");return 0;
  }
  return 1;
}
#endif

static void cleanup(ctx *c) {
#ifdef EXR_MIGRATION_RECOVERY_CANDIDATE
  if(c->lib) {
    if(c->target_commit!=C_COMMITTED && lr_open_attempted(c->recovery)) {
      exr_status status=exr_library_migration_finish(c->lib,0,&c->err);
      lr_rollback(c->recovery,status);
      if(status!=EXR_OK) entry(c,S_WARNING,"rollback-sdk-error","recovery",NULL,"rollback request returned status %d; evidence retained",(int)status);
    }
    exr_library_close(c->lib);c->lib=NULL;lr_owner_closed(c->recovery);
  }
  /* No mirror/database/intent/lease deletion. A literal finish(0) result is
     not whole-state proof; retries require an explicit guarded R operation. */
  return;
#else
  char journal[4096];
  if (c->lib) { exr_library_close(c->lib); c->lib = NULL; }
#ifdef EXR_MIGRATION_TX_CANDIDATE
  if (c->pending_retained) {
    /* A valid or partial intent may still refer to this stage. Never delete
       crash/recovery evidence or call it a database pre-image. */
    if (c->stage && lm_path_state(c->stage) != 0) c->stage_state = "retained-pending";
    if(c->recovery_barrier && c->lock_held) {
      lm_mirror_file now;lm_err lock_error={{0},{0}};
      if(lm_mirror_snapshot(c->lock,1,128,&now,NULL,NULL,&lock_error) &&
         lm_mirror_same_file(&now,&c->lock_snapshot) && lm_mirror_same_bytes(&now,&c->lock_snapshot))
        c->lock_retained=1;
      else entry(c,S_WARNING,"migration-lock-changed","lock",NULL,"pending evidence retained but shared lock ownership is no longer confirmed; foreign lock not removed");
      c->lock_held=0;
    } else (void)mirror_lock_release(c);
    return;
  }
#endif
  if (c->stage) {
    if (lm_exists(c->stage)) { lm_remove(c->stage); c->stage_state = "removed"; } else if (!c->stage_state) c->stage_state = "not-created";
    snprintf(journal, sizeof(journal), "%s-journal", c->stage);
    lm_remove(journal);
  }
#ifdef EXR_MIGRATION_TX_CANDIDATE
  {
    lm_err cleanup_error={{0},{0}};
    if(c->sidecar_tmp && c->sidecar_tmp_owned)
      (void)mirror_remove_artifact(c->sidecar_tmp,&c->sidecar_tmp_file,&cleanup_error);
    if(c->mirror_preimage && c->mirror_preimage_owned)
      (void)mirror_remove_artifact(c->mirror_preimage,&c->mirror_intent.mirror_preimage,&cleanup_error);
  }
#else
  if(c->sidecar_tmp) lm_remove(c->sidecar_tmp);
#endif
  if (c->pre && c->out != O_INCONSISTENT) {
    if (lm_exists(c->pre)) { lm_remove(c->pre); c->pre_state = "removed"; } else if (!c->pre_state) c->pre_state = "not-created";
  } else if (c->pre) c->pre_state = "retained";
#ifdef EXR_MIGRATION_TX_CANDIDATE
  (void)mirror_lock_release(c);
#else
  if (c->lock_held && c->lock) { lm_remove(c->lock); c->lock_held = 0; }
#endif
#endif
}

static int publish(ctx *c) {
  lm_sb text;
  char digest[65];
  uint64_t size;
  lm_sb_init(&text);
  sidecar_text(c, &text);
  if (text.oom || !write_file(c->sidecar_tmp, text.p, text.n)) { lm_sb_free(&text); fail(c, O_FAILED, "ledger-write-failed", "cannot write the migration ledger next to the target"); return 0; }
  lm_sb_free(&text);
  if (injected(c, "publish-cancel", 0)) g_cancel = 1;
  if (injected(c, "publish-pause", 0)) {
    char *ready = path_join(c->target, ".review-ready"), *resume = path_join(c->target, ".review-resume");
    unsigned wait;
    int resumed = 0;
    if (!write_file(ready, "ready", 5)) { free(ready); free(resume); fail(c, O_FAILED, "review-hook-failed", "cannot create review synchronization marker"); return 0; }
    for (wait = 0; wait < 400 && !cancel_cb(c); wait++) {
      if (lm_exists(resume)) { resumed = 1; break; }
#ifdef _WIN32
      Sleep(50);
#else
      struct timespec delay = {0, 50000000};
      nanosleep(&delay, NULL);
#endif
    }
    lm_remove(ready); lm_remove(resume); free(ready); free(resume);
    if (!resumed && !cancel_cb(c)) { fail(c, O_FAILED, "review-hook-timeout", "review synchronization timed out"); return 0; }
  }
  if (injected(c, "publish-fail", 0)) { fail(c, O_FAILED, "injected-publish-fail", "injected failure before the library was replaced"); return 0; }
  if (cancel_cb(c)) { fail(c, O_CANCELLED, "cancelled", "cancelled before publication"); return 0; }
  if (lm_exists(c->target) != c->target_existed) { fail(c, O_FAILED, "target-changed", "target existence changed during migration"); return 0; }
  if (lm_exists(c->sidecar) != c->sidecar_existed ||
      (c->sidecar_existed && (!lm_sha_file(c->sidecar, digest, NULL) || strcmp(digest, c->sidecar_sha)))) {
    fail(c, O_FAILED, "ledger-changed", "the migration ledger changed; nothing was published"); return 0;
  }
  if (c->target_existed) {
    if (c->target_version == 6 && !old_target_quiescent(c)) return 0;
    if (!lm_sha_file(c->target, digest, &size) || strcmp(digest, c->target_sha)) { fail(c, O_FAILED, "target-changed", "the target changed while it was being migrated; nothing was published"); return 0; }
    if (!lm_copy(c->target, c->pre)) { fail(c, O_FAILED, "pre-image-failed", "cannot keep a pre-image of the target for rollback"); return 0; }
    c->pre_state = "kept-until-commit";
  }
  /* Test-only ordinary-writer rendezvous after the last identity checks. */
  if (injected(c, "writer-pause", 0)) {
    char *ready = path_join(c->target, ".writer-ready"), *resume = path_join(c->target, ".writer-resume");
    unsigned wait;
    int resumed = 0;
    if (!write_file(ready, "ready", 5)) { free(ready); free(resume); fail(c, O_FAILED, "review-hook-failed", "cannot create writer synchronization marker"); return 0; }
    for (wait = 0; wait < 400 && !cancel_cb(c); wait++) {
      if (lm_exists(resume)) { resumed = 1; break; }
#ifdef _WIN32
      Sleep(50);
#else
      struct timespec delay = {0, 50000000};
      nanosleep(&delay, NULL);
#endif
    }
    lm_remove(ready); lm_remove(resume); free(ready); free(resume);
    if (!resumed && !cancel_cb(c)) { fail(c, O_FAILED, "review-hook-timeout", "writer synchronization timed out"); return 0; }
  }
  if (cancel_cb(c)) { fail(c, O_CANCELLED, "cancelled", "cancelled before publication"); return 0; }
  if (!(c->target_existed ? lm_replace(c->stage, c->target) : lm_publish_new(c->stage, c->target))) { fail(c, O_FAILED, "publish-failed", "cannot publish the target library; the original is unchanged"); return 0; }
  c->stage_state = "published";
  if (injected(c, "sidecar-fail", 0) || injected(c, "rollback-fail", 0) ||
      !(c->sidecar_existed ? lm_replace(c->sidecar_tmp, c->sidecar) : lm_publish_new(c->sidecar_tmp, c->sidecar))) {
    int restored = 0;
    if (!injected(c, "rollback-fail", 0)) restored = c->target_existed ? lm_replace(c->pre, c->target) : lm_remove(c->target);
    if (restored) { c->rolled_back = 1; fail(c, O_FAILED, "ledger-publish-failed", "the ledger could not be published; the library was rolled back to its previous state"); }
    else fail(c, O_INCONSISTENT, "rollback-failed", "the ledger could not be published and the rollback failed; the pre-image is kept at %s", c->target_existed ? c->pre : "(none, target was new)");
    return 0;
  }
  return 1;
}

static int run_migrate(ctx *c) {
  lm_err e;
  size_t i, *order = NULL, *first_of, *count_of, *note_book;
  unsigned long long stamp = (unsigned long long)time(NULL);
#ifndef EXR_MIGRATION_TX_CANDIDATE
  FILE *lock;
#endif
  memset(&e, 0, sizeof(e));
  snprintf(c->run, sizeof(c->run), "%llx-%x", stamp, (unsigned)
#ifdef _WIN32
    _getpid()
#else
    getpid()
#endif
  );
  c->control.cancelled = cancel_cb;
  c->control.context = c;
  if (!lm_pack_open(c->pack_path, &c->pack, &e)) { fail(c, O_REJECTED, e.code, "%s", e.message); return 0; }
  c->books_expected = (unsigned)c->pack.books->n;
  c->notes_expected = (unsigned)c->pack.notes->n;
  if (!lm_pack_verify(&c->pack, cancel_cb, c, &e)) { fail(c, !strcmp(e.code, "cancelled") ? O_CANCELLED : O_REJECTED, e.code, "%s", e.message); return 0; }
  if (!c->target) return 1; /* inspect */

  c->sidecar = path_join(c->target, ".legacy-map.json");
#ifdef EXR_MIGRATION_RECOVERY_CANDIDATE
  {
    void *data=NULL;size_t size=0;int found=0;
    if(!lr_prepare(c->recovery,&c->pack,c->recovery_retry,&e)||!lr_opening(c->recovery,&e)) {
      fail(c,!strcmp(e.code,"cancelled")?O_CANCELLED:O_BUSY,e.code,"%s; recovery evidence retained",e.message);return 0;
    }
    lr_owner_attempted(c->recovery);
    if(exr_library_migration_open(c->target,&c->lib,&c->err)!=EXR_OK) {
      fail(c,O_BUSY,"recovery-sdk-open-failed","%s; explicit recovery remains required",c->err.message);return 0;
    }
    lr_owner_started(c->recovery);c->target_existed=1;
    if(!lr_compare_restore(c->recovery,c->lib,&e)||!lr_snapshot(c->recovery,c->target,0,0,&c->owner_before,NULL,NULL,&e)||!mirror_sidecar_snapshot(c,&c->mirror_before)) {
      fail(c,!strcmp(e.code,"cancelled")?O_CANCELLED:O_BUSY,e.code,"%s; evidence retained",e.message);return 0;
    }
    c->sidecar_existed=c->mirror_before.present;
    if(exr_library_migration_ledger_get(c->lib,&data,&size,&found,&c->err)!=EXR_OK){sdk_fail(c,"reading transactional ledger");return 0;}
    if(found){
      if((c->sidecar_existed&&!sidecar_check_envelope(c,c->sidecar))||!sidecar_parse(c,(const char*)data,size)){exr_free(data);return 0;}
    } else if(c->sidecar_existed&&!sidecar_load(c,c->sidecar)){exr_free(data);return 0;}
    exr_free(data);
  }
  goto process_pack;
#endif
  /* Both migration executables must hold the same lock while touching a target. */
  c->lock = path_join(c->target, ".migrate-lock");
#ifdef EXR_MIGRATION_TX_CANDIDATE
  c->pending=path_join(c->target,".migration-pending.json");
  if(!mirror_lock_acquire(c)) return 0;
#else
  if (c->break_lock) lm_remove(c->lock);
  lock = lm_fopen(c->lock, "wx");
  if (!lock) {
    if (lm_exists(c->lock)) fail(c, O_BUSY, "target-busy", "another migration holds %s (use --break-lock only if no migration is running)", c->lock);
    else fail(c, O_FAILED, "lock-failed", "cannot create the lock file %s", c->lock);
    return 0;
  }
  fprintf(lock, "%s\n", c->run);
  fclose(lock);
  c->lock_held = 1;
#endif
#ifdef EXR_MIGRATION_TX_CANDIDATE
  {
    void *data=NULL;size_t size=0;int found=0;const char *open_path;
    int recovered;
    if(c->dry_run) {
      lm_mirror_intent prior;lm_mirror_file prior_file;
      if(!lm_mirror_intent_read(c->pending,&prior,&prior_file,&e)) { c->pending_retained=1;return mirror_fail(c,&e); }
      if(prior_file.present) {
        c->pending_retained=1;c->mirror_state="pending";
        fail(c,O_BUSY,"mirror-recovery-required","dry-run cannot publish or retire a pending mirror intent; recover separately");return 0;
      }
      recovered=1;
    } else recovered=mirror_reconcile(c);
    if(!recovered) return 0;
    if(recovered==2) { fail(c,O_BUSY,"mirror-cleanup-pending","prior mirror converged but pending cleanup must finish before another migration");return 0; }
    if(!lm_mirror_snapshot(c->target,0,0,&c->owner_before,NULL,NULL,&e)) return mirror_fail(c,&e);
    c->target_existed=c->owner_before.present;
    if(!mirror_sidecar_snapshot(c,&c->mirror_before)) return 0;
    c->sidecar_existed=c->mirror_before.present;
    strcpy(c->sidecar_sha,c->mirror_before.sha);
    if(!c->target_existed && c->sidecar_existed) {
      fail(c,O_REJECTED,"orphan-ledger","a legacy ledger exists without its library");return 0;
    }
    open_path=c->target;
    if(!c->target_existed) {
      FILE *reserved;
      c->stage=lm_xalloc(strlen(c->target)+64);
      sprintf(c->stage,"%s.migrating-%s",c->target,c->run);
      reserved=lm_fopen(c->stage,"wbx");
      if(!reserved) { free(c->stage);c->stage=NULL;fail(c,O_FAILED,"stage-failed","cannot reserve private new-library stage");return 0; }
      if(fclose(reserved)) { fail(c,O_FAILED,"stage-failed","cannot close private new-library stage");return 0; }
      open_path=c->stage;c->stage_state="created";
      if(!lm_mirror_snapshot(open_path,0,0,&c->owner_before,NULL,NULL,&e)) return mirror_fail(c,&e);
    }
    if(exr_library_migration_open(open_path,&c->lib,&c->err)!=EXR_OK) {
      if(strstr(c->err.message,"Migration requires schema")) { fail(c,O_REJECTED,"target-schema","%s",c->err.message);return 0; }
      if(strstr(c->err.message,"not a database")) { fail(c,O_REJECTED,"target-not-library","%s",c->err.message);return 0; }
      fail(c,O_BUSY,"target-busy","cannot acquire the library write transaction: %s",c->err.message);return 0;
    }
    if(!mirror_owner_unchanged(c,open_path,&c->owner_before)) return 0;
    if(exr_library_migration_ledger_get(c->lib,&data,&size,&found,&c->err)!=EXR_OK) {
      sdk_fail(c,"reading transactional ledger");return 0;
    }
    if(found) {
      if(c->sidecar_existed && !sidecar_check_envelope(c,c->sidecar)) { exr_free(data);return 0; }
      if(!sidecar_parse(c,(const char *)data,size)) { exr_free(data);return 0; }
    } else if(c->sidecar_existed && !sidecar_load(c,c->sidecar)) { exr_free(data);return 0; }
    if(!lm_mirror_begin(&c->mirror_intent,c->target_existed,c->run,&c->owner_before,
                        found,data,size,&c->mirror_before,&e)) { exr_free(data);return mirror_fail(c,&e); }
    exr_free(data);
  }
  goto process_pack;
#endif
  c->stage = lm_xalloc(strlen(c->target) + 64);
  sprintf(c->stage, "%s.migrating-%s", c->target, c->run);
  c->pre = lm_xalloc(strlen(c->target) + 64);
  sprintf(c->pre, "%s.pre-%s", c->target, c->run);
  c->sidecar_tmp = lm_xalloc(strlen(c->sidecar) + 64);
  sprintf(c->sidecar_tmp, "%s.tmp-%s", c->sidecar, c->run);

  c->target_existed = lm_exists(c->target);
  c->sidecar_existed = lm_exists(c->sidecar);
  if (c->target_existed) {
    exr_library *source = NULL;
    if (!check_target_header(c)) return 0;
#ifndef EXR_MIGRATION_TX_CANDIDATE
    /* Do not open SQLite before rejecting a schema-6 WAL/journal: opening an
       occupied database can itself create a shared-memory sidecar. */
    if (c->target_version == 6 && !old_target_quiescent(c)) return 0;
    if (!reject_transactional_ledger(c)) return 0;
#endif
    if (!lm_sha_file(c->target, c->target_sha, NULL)) { fail(c, O_FAILED, "target-unreadable", "cannot hash the target"); return 0; }
    if (c->target_version == 6) {
      if (!snapshot_old_target(c)) return 0;
    } else {
      if (exr_library_open(c->target, &source, &c->err) != EXR_OK) { fail(c, O_BUSY, "target-busy", "cannot open the target (%s); close every other handle and retry", c->err.message); return 0; }
      if (exr_library_backup(source, c->stage, &c->err) != EXR_OK) { exr_library_close(source); fail(c, O_FAILED, "stage-failed", "cannot build the stage with the backup API: %s", c->err.message); return 0; }
      exr_library_close(source);
    }
    c->stage_state = "built-from-backup";
  } else if (c->sidecar_existed) {
    fail(c, O_REJECTED, "orphan-ledger", "a ledger exists without its library (%s); remove or restore one of them first", c->sidecar);
    return 0;
  }
  if (c->sidecar_existed) {
    if (!lm_sha_file(c->sidecar, c->sidecar_sha, NULL)) { fail(c, O_FAILED, "ledger-unreadable", "cannot hash the existing ledger"); return 0; }
    if (!sidecar_load(c, c->sidecar)) return 0;
  }
  if (exr_library_open(c->stage, &c->lib, &c->err) != EXR_OK) { sdk_fail(c, "opening the stage library"); return 0; }
  if (!c->stage_state) c->stage_state = "created";

#ifdef EXR_MIGRATION_TX_CANDIDATE
process_pack:
#endif
  /* Group annotations by book without copying them. */
  note_book = lm_xalloc((c->pack.notes->n + 1) * sizeof(size_t));
  first_of = lm_xalloc((c->pack.books->n + 2) * sizeof(size_t));
  count_of = lm_xalloc((c->pack.books->n + 2) * sizeof(size_t));
  order = lm_xalloc((c->pack.notes->n + 1) * sizeof(size_t));
  for (i = 0; i < c->pack.books->n; i++) lm_hm_put(&c->pack_books, lm_get_str(c->pack.books->items[i], "legacy_id"), i);
  for (i = 0; i < c->pack.notes->n; i++) {
    const char *owner = lm_get_str(lm_get(c->pack.notes->items[i], "record"), "bookId");
    size_t at;
    note_book[i] = owner && lm_hm_get(&c->pack_books, owner, &at) ? at : SIZE_MAX;
    if (note_book[i] != SIZE_MAX) count_of[note_book[i]]++;
  }
  {
    size_t sum = 0;
    for (i = 0; i < c->pack.books->n; i++) { first_of[i] = sum; sum += count_of[i]; count_of[i] = 0; }
    for (i = 0; i < c->pack.notes->n; i++)
      if (note_book[i] != SIZE_MAX) order[first_of[note_book[i]] + count_of[note_book[i]]++] = i;
  }
  for (i = 0; i < c->pack.books->n && c->out == O_NONE; i++) {
    if (!tick(c)) break;
    process_book(c, c->pack.books->items[i], c->pack.notes, order, first_of[i], first_of[i] + count_of[i]);
  }
  for (i = 0; i < c->pack.notes->n && c->out == O_NONE; i++) {
    const jv *jn = c->pack.notes->items[i];
    const char *id = lm_get_str(jn, "legacy_id");
    lm_note *ln;
    lm_sb canonical;
    char fingerprint[65];
    if (note_book[i] != SIZE_MAX) continue;
    if (!tick(c)) break;
    lm_sb_init(&canonical);
    lm_json_write(&canonical, lm_get(jn, "record"));
    lm_sha_bytes(canonical.p ? canonical.p : "", canonical.n, fingerprint);
    lm_sb_free(&canonical);
    ln = lm_ledger_note(&c->ledger, id, 0);
    if (ln) {
      ln->touched = 1;
      if (strcmp(ln->fp, fingerprint)) {
        entry(c, S_CONFLICT, "note-changed", "note", id, "existing legacy annotation differs; earlier result retained");
        c->notes_skipped++;
        note_item(c, id, ln->book_legacy ? ln->book_legacy : "", kind_name(ln->kind), "skipped", ln->new_id, NULL, "note-changed");
      } else if (ln->located) {
        c->notes_existing++;
        note_item(c, id, ln->book_legacy ? ln->book_legacy : "", kind_name(ln->kind), "existing", ln->new_id, "ledger", NULL);
      } else {
        c->notes_unlocated++;
        note_item(c, id, "", kind_name(ln->kind), "unlocated", 0, ln->method, ln->reason);
      }
      continue;
    }
    ln = lm_ledger_note(&c->ledger, id, 1);
    ln->touched = 1;
    set_str(&ln->reason, "orphan-note");
    free(ln->retained);
    ln->retained = record_json(lm_get(jn, "record"), 0);
    strcpy(ln->fp, fingerprint);
    entry(c, S_UNLOCATED, "orphan-note", "note", id, "the annotation refers to a book that is not in the export; preserved in the ledger only");
    c->notes_unlocated++;
    note_item(c, id, "", "reflow", "unlocated", 0, NULL, "orphan-note");
  }
  free(note_book); free(first_of); free(count_of); free(order);
  if (c->out != O_NONE) return 0;
  /* Books processed through the ledger count as expected-accounted. */
  if (!c->allow_partial && (c->sev[S_UNSUPPORTED] || c->sev[S_CONFLICT])) {
#ifdef EXR_MIGRATION_TX_CANDIDATE
    fail(c, O_REJECTED, "policy-strict", "%u unsupported and %u conflicting items; requested migration changes were not committed (rerun with --allow-partial to commit the convertible part)", c->sev[S_UNSUPPORTED], c->sev[S_CONFLICT]);
#else
    fail(c, O_REJECTED, "policy-strict", "%u unsupported and %u conflicting items; nothing was published (rerun with --allow-partial to publish the convertible part)", c->sev[S_UNSUPPORTED], c->sev[S_CONFLICT]);
#endif
    return 0;
  }
  if (c->out == O_NONE) {
#ifdef EXR_MIGRATION_RECOVERY_CANDIDATE
    lm_sb text;exr_status status;
    if(!verify_library(c,c->lib,1))return 0;
    if(c->dry_run){fail(c,O_BUSY,"dry-run-recovery-required","preview completed under the real owner; rollback will be requested, then explicit recover-migration is required");return 0;}
    if(cancel_cb(c)||injected(c,"publish-fail",0)){fail(c,cancel_cb(c)?O_CANCELLED:O_FAILED,cancel_cb(c)?"cancelled":"injected-publish-fail","no COMMIT requested; retained evidence requires explicit recovery");return 0;}
    lm_sb_init(&text);sidecar_text(c,&text);
    if(text.oom||text.n>LM_RECOVERY_LIMIT){lm_sb_free(&text);fail(c,O_FAILED,"recovery-ledger-bound","bounded ledger serialization refused");return 0;}
    if(exr_library_migration_ledger_set(c->lib,text.p,text.n,&c->err)!=EXR_OK){lm_sb_free(&text);sdk_fail(c,"writing transactional ledger");return 0;}
    if(!lr_publish(c->recovery,text.p,text.n,&e)){lm_sb_free(&text);fail(c,!strcmp(e.code,"cancelled")?O_CANCELLED:O_BUSY,e.code,"%s; evidence retained",e.message);return 0;}lm_sb_free(&text);
    if(cancel_cb(c)){fail(c,O_CANCELLED,"cancelled","cancelled before COMMIT; explicit recovery required");return 0;}
    c->target_commit=C_UNKNOWN;status=exr_library_migration_finish(c->lib,1,&c->err);
    if(status==EXR_OK)c->target_commit=C_COMMITTED;
    if(!lr_ack(c->recovery,status,&e)){fail(c,O_BUSY,e.code,"%s; COMMIT observation and evidence retained without whole-state recovery claim",e.message);return 0;}
    exr_library_close(c->lib);c->lib=NULL;lr_owner_closed(c->recovery);
    if(!lr_complete(c->recovery,&e)){fail(c,O_BUSY,e.code,"%s; committed evidence remains retained",e.message);return 0;}
    c->out=O_SUCCESS;snprintf(c->code,sizeof(c->code),"ok");snprintf(c->message,sizeof(c->message),"real importer COMMIT acknowledged; exact mirror and permanent recovery evidence retained");return 1;
#elif defined(EXR_MIGRATION_TX_CANDIDATE)
    lm_sb text;
    if(!verify_library(c,c->lib,1)) return 0;
    lm_sb_init(&text);sidecar_text(c,&text);
    if(text.oom || exr_library_migration_ledger_set(c->lib,text.p,text.n,&c->err)!=EXR_OK) {
      lm_sb_free(&text);sdk_fail(c,"writing transactional ledger");return 0;
    }
    lm_mirror_set_after(&c->mirror_intent,text.p,text.n);
    c->sidecar_tmp=lm_xalloc(strlen(c->sidecar)+64);
    sprintf(c->sidecar_tmp,"%s.staged-%s",c->sidecar,c->run);
    if(!mirror_write_stage(c,c->sidecar_tmp,text.p,text.n,&c->sidecar_tmp_owned)) { lm_sb_free(&text);return 0; }
    if(!lm_mirror_snapshot(c->sidecar_tmp,1,LM_MIRROR_LEDGER_MAX,&c->sidecar_tmp_file,NULL,NULL,&e)) {
      lm_sb_free(&text);return mirror_fail(c,&e);
    }
    c->mirror_state="staged";
    lm_sb_free(&text);
    if(injected(c,"writer-pause",0)) {
      char *ready=path_join(c->target,".writer-ready"),*resume=path_join(c->target,".writer-resume");
      unsigned wait;int resumed=0;
      if(!write_file(ready,"ready",5)) { free(ready);free(resume);fail(c,O_FAILED,"review-hook-failed","cannot create writer marker");return 0; }
      for(wait=0;wait<400 && !cancel_cb(c);wait++) {
        if(lm_exists(resume)) { resumed=1;break; }
#ifdef _WIN32
        Sleep(50);
#else
        struct timespec delay={0,50000000};nanosleep(&delay,NULL);
#endif
      }
      lm_remove(ready);lm_remove(resume);free(ready);free(resume);
      if(!resumed && !cancel_cb(c)) { fail(c,O_FAILED,"review-hook-timeout","writer synchronization timed out");return 0; }
    }
    /* Preserve the legacy publication rendezvous for external-ledger checks. */
    if(injected(c,"publish-pause",0)) {
      char *ready=path_join(c->target,".review-ready"),*resume=path_join(c->target,".review-resume");
      unsigned wait;int resumed=0;
      if(!write_file(ready,"ready",5)) { free(ready);free(resume);fail(c,O_FAILED,"review-hook-failed","cannot create review marker");return 0; }
      for(wait=0;wait<400 && !cancel_cb(c);wait++) {
        if(lm_exists(resume)) { resumed=1;break; }
#ifdef _WIN32
        Sleep(50);
#else
        struct timespec delay={0,50000000};nanosleep(&delay,NULL);
#endif
      }
      lm_remove(ready);lm_remove(resume);free(ready);free(resume);
      if(!resumed && !cancel_cb(c)) { fail(c,O_FAILED,"review-hook-timeout","review synchronization timed out");return 0; }
    }
    {
      lm_mirror_file now;
      if(!mirror_sidecar_snapshot(c,&now)) return 0;
      if(!lm_mirror_same_file(&now,&c->mirror_before) || !lm_mirror_same_bytes(&now,&c->mirror_before)) {
        fail(c,O_FAILED,"ledger-changed","the migration ledger changed before COMMIT");return 0;
      }
    }
    /* Preserve the legacy late-cancellation hook at the transaction boundary. */
    if(injected(c,"publish-cancel",0)) g_cancel=1;
    if(c->dry_run || cancel_cb(c) || injected(c,"publish-fail",0)) {
      if(exr_library_migration_finish(c->lib,0,&c->err)!=EXR_OK) { sdk_fail(c,"rolling back migration");return 0; }
      if(c->target_existed) c->target_commit=C_NOT_COMMITTED;
      else c->private_stage_commit=C_NOT_COMMITTED;
      if(c->dry_run) { c->out=O_DRYRUN;snprintf(c->code,sizeof(c->code),"dry-run");snprintf(c->message,sizeof(c->message),"transaction rolled back; nothing was published");return 1; }
      fail(c,cancel_cb(c)?O_CANCELLED:O_FAILED,cancel_cb(c)?"cancelled":"injected-publish-fail","transaction rolled back");return 0;
    }
    if(!mirror_owner_unchanged(c,c->target_existed?c->target:c->stage,&c->owner_before)) return 0;
    if(!c->target_existed) {
      lm_mirror_file destination;
      if(!lm_mirror_snapshot(c->target,0,0,&destination,NULL,NULL,&e)) return mirror_fail(c,&e);
      if(destination.present) {
        fail(c,O_FAILED,"target-changed","a target appeared before COMMIT; the uncommitted private stage will be removed");return 0;
      }
    }
    if(!mirror_prepare_existing(c)) return 0;
    if(!lm_mirror_intent_write(c->pending,&c->mirror_intent,&c->pending_snapshot,&e)) {
      c->pending_retained=lm_path_state(c->pending)!=0;
      c->recovery_barrier=c->pending_retained && c->mirror_intent.version==3;
      return mirror_fail(c,&e);
    }
    c->pending_retained=1;c->mirror_state="pending";
    c->recovery_barrier=c->mirror_intent.version==3;
    {
      int resumed=mirror_pause(c,"intent-pause",".intent-ready");
      /* Intent I/O may block. Cancellation received during its write/fsync must
         be observed before entering COMMIT, not turned into a committed cancel. */
      if(!resumed || cancel_cb(c)) {
        if(c->mirror_intent.version==2 || c->mirror_intent.version==3) {
          fail(c,O_CANCELLED,"cancelled","prepared migration cancelled before COMMIT");return mirror_abort_precommit(c);
        }
        if(exr_library_migration_finish(c->lib,0,&c->err)!=EXR_OK) { sdk_fail(c,"rolling back prepared migration");return 0; }
        if(c->target_existed) c->target_commit=C_NOT_COMMITTED;
        else c->private_stage_commit=C_NOT_COMMITTED;
        fail(c,O_CANCELLED,"cancelled","prepared migration rolled back; mirror intent retained for reconciliation");return 0;
      }
    }
    if((c->mirror_intent.version==2 || c->mirror_intent.version==3) && !mirror_publish_precommit(c)) return mirror_abort_precommit(c);
    if(cancel_cb(c)) {
      fail(c,O_CANCELLED,"cancelled","cancelled immediately before COMMIT");
      if(c->mirror_intent.version==2 || c->mirror_intent.version==3) return mirror_abort_precommit(c);
      return 0;
    }
    /* A commit error is not proof of rollback. Closing the owner below must not
       turn an unconfirmed commit into a claimed cancellation or rollback. */
    if(c->target_existed) c->target_commit=C_UNKNOWN;
    else c->private_stage_commit=C_UNKNOWN;
    if(exr_library_migration_finish(c->lib,1,&c->err)!=EXR_OK) { sdk_fail(c,"committing migration");return 0; }
    if(c->target_existed) c->target_commit=C_COMMITTED;
    else c->private_stage_commit=C_COMMITTED;
    if(!c->target_existed) {
      exr_library_close(c->lib);c->lib=NULL;
      /* A committed private stage is not yet a committed target. */
      c->target_commit=C_UNKNOWN;
      if(!lm_publish_new(c->stage,c->target)) { fail(c,O_FAILED,"publish-failed","cannot publish the new library without replacing an existing path");return 0; }
      c->target_commit=C_COMMITTED;
      c->stage_state="published";
    }
    if(injected(c,"commit-pause",0)) {
      char *ready=path_join(c->target,".commit-ready"),*resume=path_join(c->target,".commit-resume");
      unsigned wait;int resumed=0;
      if(!write_file(ready,"ready",5)) { free(ready);free(resume);fail(c,O_FAILED,"review-hook-failed","cannot create commit marker");return 0; }
      for(wait=0;wait<400 && !cancel_cb(c);wait++) {
        if(lm_exists(resume)) { resumed=1;break; }
#ifdef _WIN32
        Sleep(50);
#else
        struct timespec delay={0,50000000};nanosleep(&delay,NULL);
#endif
      }
      lm_remove(ready);lm_remove(resume);free(ready);free(resume);
      if(!resumed) { fail(c,O_FAILED,"review-hook-timeout","commit synchronization timed out");return 0; }
    }
    if(c->lib) { exr_library_close(c->lib);c->lib=NULL; }
    {
      int mirrored=c->mirror_intent.version==3?mirror_complete_committed_v3(c):mirror_reconcile(c);
      if(!mirrored) return 0;
      c->out=O_SUCCESS;
      snprintf(c->code,sizeof(c->code),"%s",mirrored==2?"mirror-cleanup-pending":"ok");
      snprintf(c->message,sizeof(c->message),"%s",mirrored==2?
        "transaction committed; mirror bytes converged; intent cleanup pending":
        "transaction committed; mirror bytes converged");
      return 1;
    }
#else
    exr_library_close(c->lib);
    c->lib = NULL;
    if (exr_library_open(c->stage, &c->lib, &c->err) != EXR_OK) { sdk_fail(c, "reopening the stage library"); return 0; }
    if (!verify_library(c, c->lib, 1)) return 0;
    exr_library_close(c->lib);
    c->lib = NULL;
#endif
  }
#ifndef EXR_MIGRATION_TX_CANDIDATE
  if (c->dry_run) { c->out = O_DRYRUN; snprintf(c->code, sizeof(c->code), "dry-run"); snprintf(c->message, sizeof(c->message), "stage built and verified; nothing was published"); return 1; }
  if (!publish(c)) return 0;
  c->out = O_SUCCESS;
  snprintf(c->code, sizeof(c->code), "ok");
  snprintf(c->message, sizeof(c->message), "published and verified");
  return 1;
#endif
  return 0;
}

/* ---------- report ---------- */
static void emit(ctx *c) {
  lm_sb b;
  unsigned long long peak = lm_peak_rss();
  size_t i;
  lm_sb_init(&b);
  lm_sb_fmt(&b, "{\"tool\":\"exreader-legacy-migrate\",\"tool_version\":\"%s\",\"sdk_version\":\"%s\",\"abi\":%u,\"command\":\"%s\",\"result\":\"%s\",\"code\":", 
#ifdef EXR_MIGRATION_RECOVERY_CANDIDATE
    LM_RECOVERY_VERSION,
#else
    LM_TOOL_VERSION,
#endif
    exr_version(), exr_abi_version(), c->cmd, OUTCOME[c->out]);
  lm_sb_json(&b, c->code, strlen(c->code));
  lm_sb_str(&b, ",\"message\":");
  lm_sb_json(&b, c->message, strlen(c->message));
  lm_sb_str(&b, ",\"pack\":{\"path\":");
  lm_sb_json(&b, c->pack_path ? c->pack_path : "", c->pack_path ? strlen(c->pack_path) : 0);
  lm_sb_fmt(&b, ",\"sha256\":\"%s\",\"bytes\":%llu}", c->pack.sha, (unsigned long long)c->pack.size);
  lm_sb_str(&b, ",\"target\":{\"path\":");
#ifdef EXR_MIGRATION_RECOVERY_CANDIDATE
  {const char *original=lr_original_target(c->recovery);if(!original||!*original)original=c->target;lm_sb_json(&b,original?original:"",original?strlen(original):0);}
#else
  lm_sb_json(&b, c->target ? c->target : "", c->target ? strlen(c->target) : 0);
#endif
  lm_sb_fmt(&b, ",\"existed\":%s,\"sha256_before\":%s%s%s,\"ledger\":", c->target_existed ? "true" : "false", c->target_sha[0] ? "\"" : "", c->target_sha[0] ? c->target_sha : "null", c->target_sha[0] ? "\"" : "");
  if (c->sidecar) lm_sb_json(&b, c->sidecar, strlen(c->sidecar)); else lm_sb_str(&b, "null");
  lm_sb_str(&b, "}");
  lm_sb_fmt(&b, ",\"counts\":{\"books_expected\":%u,\"books_created\":%u,\"books_existing\":%u,\"books_merged\":%u,\"books_skipped\":%u,\"books_audio_positions_only\":%u,", c->books_expected, c->books_created, c->books_existing, c->books_merged, c->books_skipped, c->books_audio);
  lm_sb_fmt(&b, "\"books_accounted\":%u,\"notes_expected\":%u,\"notes_created\":%u,\"notes_existing\":%u,\"notes_unlocated\":%u,\"notes_skipped\":%u,\"notes_accounted\":%u,", c->books_created + c->books_existing + c->books_merged + c->books_skipped + c->books_audio, c->notes_expected, c->notes_created, c->notes_existing, c->notes_unlocated, c->notes_skipped, c->notes_created + c->notes_existing + c->notes_unlocated + c->notes_skipped);
  lm_sb_str(&b, "\"entries\":{");
  for (i = 0; i < S_COUNT; i++) lm_sb_fmt(&b, "%s\"%s\":%u", i ? "," : "", SEVERITY[i], c->sev[i]);
  lm_sb_str(&b, "}}");
  lm_sb_fmt(&b, ",\"memory\":{\"peak_rss_bytes\":%llu,\"max_original_bytes\":%llu,\"imported_bytes\":%llu,\"manifest_bytes\":%llu},", peak, (unsigned long long)c->max_book_bytes, (unsigned long long)c->bytes_imported, (unsigned long long)c->pack.manifest_len);
  lm_sb_fmt(&b, "\"atomicity\":{\"rolled_back\":%s,\"stage\":\"%s\",\"pre_image\":\"%s\",\"inject\":", 
#ifdef EXR_MIGRATION_RECOVERY_CANDIDATE
    "null",
#else
    c->rolled_back ? "true" : "false",
#endif
    c->stage_state ? c->stage_state : "none", c->pre_state ? c->pre_state : "none");
  if (c->inject[0]) lm_sb_json(&b, c->inject, strlen(c->inject)); else lm_sb_str(&b, "null");
#ifdef EXR_MIGRATION_TX_CANDIDATE
  lm_sb_fmt(&b, ",\"transaction\":{\"target_commit\":\"%s\",\"private_stage_commit\":\"%s\"}",
    COMMIT_KNOWLEDGE[c->target_commit], COMMIT_KNOWLEDGE[c->private_stage_commit]);
#ifdef EXR_MIGRATION_RECOVERY_CANDIDATE
  lm_sb_str(&b,",\"mirror\":{\"state\":\"see-recovery-protocol\",\"pending\":null}");
#else
  lm_sb_fmt(&b, ",\"mirror\":{\"state\":\"%s\",\"pending\":%s}",
    c->mirror_state?c->mirror_state:"not-inspected",c->pending_retained?"true":"false");
#endif
#ifdef EXR_MIGRATION_RECOVERY_CANDIDATE
  lm_sb_str(&b,",\"recovery\":");lr_report(c->recovery,&b);
#else
  lm_sb_fmt(&b, ",\"recovery\":{\"scope\":\"existing-target-post-intent-v3\",\"rollback_requested\":%s,\"sdk_status\":",
    c->rollback_requested?"true":"null");
  if(c->rollback_status_valid) lm_sb_fmt(&b,"%d",(int)c->rollback_status);else lm_sb_str(&b,"null");
  lm_sb_fmt(&b,",\"logical_state\":\"%s\",\"io_observation\":\"not-installed\",\"physical_cleanup\":\"not-independently-verified\",\"automatic_retirement_blocked\":%s,\"full_recovery_accepted\":false}",
    c->recovery_barrier?"unverified":"not-assessed",c->recovery_barrier?"true":"false");
#endif
#endif
#ifdef EXR_MIGRATION_TX_CANDIDATE
#ifdef EXR_MIGRATION_RECOVERY_CANDIDATE
  lm_sb_str(&b,",\"lock\":\"protocol-owned-retained-or-not-acquired\"},");
#else
  lm_sb_fmt(&b, ",\"lock\":\"%s\"},",c->lock_retained?"retained-pending":(c->lock_held?"held":"released-or-not-acquired"));
#endif
#else
  lm_sb_fmt(&b, ",\"lock\":\"%s\"},", c->lock_held ? "held" : "released");
#endif
  lm_sb_str(&b, "\"items\":[");
  if (c->items.p) lm_sb_str(&b, c->items.p);
  lm_sb_str(&b, "],\"notes\":[");
  if (c->notes.p) lm_sb_str(&b, c->notes.p);
  lm_sb_str(&b, "],\"entries\":[");
  if (c->entries.p) lm_sb_str(&b, c->entries.p);
  lm_sb_str(&b, "]}\n");
  fwrite(b.p, 1, b.n, stdout);
  fflush(stdout);
  if (c->report_path
#ifdef EXR_MIGRATION_RECOVERY_CANDIDATE
      && c->recovery_gate_ok
#endif
      && !write_file(c->report_path, b.p, b.n)) fprintf(stderr, "warning: cannot write the report file %s\n", c->report_path);
  lm_sb_free(&b);
}

/* ---------- inspect ---------- */
static void run_inspect(ctx *c) {
  size_t i;
  lm_sb b;
  for (i = 0; i < c->pack.books->n; i++) {
    const jv *jb = c->pack.books->items[i], *rec = lm_get(jb, "record"), *file = lm_get(jb, "file");
    char buf[32];
    const char *ext = lm_get_str(rec, "format"), *name = lm_get_str(rec, "filename");
    exr_format fmt;
    int kind = 0;
    const char *state;
    uint64_t size = 0;
    if (!ext) ext = file_extension(name ? name : "", buf, sizeof(buf));
    lm_json_uint(lm_get(file, "size"), &size);
    if (!lm_get(file, "present") || !lm_get(file, "present")->b) state = "missing-original";
    else if (in_list(ext, AUDIO_EXT)) state = "audio-positions-only";
    else if (map_format(ext, &fmt, &kind)) state = "convertible";
    else state = "unsupported-format";
    if (c->item_n++) lm_sb_str(&c->items, ",");
    lm_sb_str(&c->items, "{\"legacy_id\":");
    lm_sb_json(&c->items, lm_get_str(jb, "legacy_id"), strlen(lm_get_str(jb, "legacy_id")));
    lm_sb_str(&c->items, ",\"format\":");
    lm_sb_json(&c->items, ext, strlen(ext));
    lm_sb_fmt(&c->items, ",\"state\":\"%s\",\"size\":%llu}", state, (unsigned long long)size);
  }
  lm_sb_init(&b);
  c->out = O_SUCCESS;
  snprintf(c->code, sizeof(c->code), "ok");
  snprintf(c->message, sizeof(c->message), "pack is well-formed and every original matches its digest");
}

/* ---------- verify command ---------- */
static void run_verify(ctx *c) {
  size_t i, at;
  c->sidecar = path_join(c->target, ".legacy-map.json");
#ifdef EXR_MIGRATION_TX_CANDIDATE
  {
    void *data=NULL;size_t size=0;int found=0;
    if (!check_target_header(c)) return;
    if(exr_library_open(c->target,&c->lib,&c->err)!=EXR_OK) { sdk_fail(c,"opening library");return; }
    if(exr_library_migration_ledger_get(c->lib,&data,&size,&found,&c->err)!=EXR_OK) { sdk_fail(c,"reading transactional ledger");return; }
    if(!found) { fail(c,O_REJECTED,"ledger-missing","no transactional ledger in library");return; }
    {
      lm_mirror_file mirror;
      if(!mirror_sidecar_snapshot(c,&mirror)) { exr_free(data);return; }
      if(mirror.present && !sidecar_check_envelope(c,c->sidecar)) { exr_free(data);return; }
    }
    if(!mirror_check_read(c,data,size)) { exr_free(data);return; }
    if(!sidecar_parse(c,(const char *)data,size)) { exr_free(data);return; }
    exr_free(data);
  }
#else
  if (!lm_exists(c->sidecar)) { fail(c, O_REJECTED, "ledger-missing", "no migration ledger next to %s", c->target); return; }
  if (!sidecar_load(c, c->sidecar)) return;
  if (!check_target_header(c)) return;
  if (exr_library_open(c->target, &c->lib, &c->err) != EXR_OK) { fail(c, O_FAILED, "open-failed", "cannot open %s: %s", c->target, c->err.message); return; }
#endif
  for (i = 0; i < c->pack.books->n; i++) {
    const char *id = lm_get_str(c->pack.books->items[i], "legacy_id");
    const jv *file = lm_get(c->pack.books->items[i], "file");
    lm_book *b = lm_ledger_book(&c->ledger, id, 0);
    if (!file || !lm_get(file, "present") || !lm_get(file, "present")->b) continue;
    if (!b) { entry(c, S_CONFLICT, "verify-unmapped-book", "verify", id, "pack book has no ledger entry"); c->books_skipped++; continue; }
    if (strcmp(b->sha, lm_get_str(file, "sha256"))) { entry(c, S_CONFLICT, "verify-sha", "verify", id, "ledger digest differs from the pack"); c->books_skipped++; continue; }
    b->touched = 1;
    c->books_existing++;
  }
  for (i = 0; i < c->pack.notes->n; i++) {
    const char *id = lm_get_str(c->pack.notes->items[i], "legacy_id");
    lm_note *n = lm_ledger_note(&c->ledger, id, 0);
    lm_sb record;
    char fingerprint[65];
    if (!n) { entry(c, S_CONFLICT, "verify-unmapped-note", "verify", id, "pack note has no ledger entry"); c->notes_skipped++; continue; }
    lm_sb_init(&record);
    lm_json_write(&record, lm_get(c->pack.notes->items[i], "record"));
    lm_sha_bytes(record.p ? record.p : "", record.n, fingerprint);
    lm_sb_free(&record);
    if (strcmp(n->fp, fingerprint)) { entry(c, S_CONFLICT, "verify-note-content", "verify", id, "pack annotation differs from the migrated ledger record"); c->notes_skipped++; continue; }
    n->touched = 1;
    if (n->located) c->notes_existing++; else c->notes_unlocated++;
  }
  (void)at;
  if (c->sev[S_CONFLICT]) { fail(c, O_FAILED, "verify-failed", "%u pack items are not reflected in the library ledger", c->sev[S_CONFLICT]); return; }
  if (!verify_library(c, c->lib, 0)) return;
  c->out = O_SUCCESS;
  snprintf(c->code, sizeof(c->code), "ok");
  snprintf(c->message, sizeof(c->message), "library and ledger agree with the pack");
}

/* ---------- command line ---------- */
static void usage(void) {
  fputs("usage: exreader-legacy-migrate <command> [options]\n"
        "  inspect --pack PACK\n"
        "  migrate --pack PACK --target LIBRARY [--report FILE] [--allow-partial] [--dry-run] [--break-lock]\n"
        "  verify  --pack PACK --target LIBRARY\n"
        "  dump    --target LIBRARY\n"
#ifdef EXR_MIGRATION_TX_CANDIDATE
        "  recover-mirror --target LIBRARY [--break-lock] [--report FILE]\n"
#endif
#ifdef EXR_MIGRATION_RECOVERY_CANDIDATE
        "  recover-migration --pack PACK --target LIBRARY [--recovery-font FONT]\n"
        "  Existing native POSIX targets only. Dry-run/cancel after opening requires explicit recovery.\n"
#endif
        "  --version\n"
        "Exit: 0 success/dry-run, 1 usage, 2 rejected, 3 failed, 4 cancelled, 5 busy, 6 inconsistent\n", stderr);
}
static int real_main(int argc, char **argv) {
  ctx *c = lm_xalloc(sizeof(*c));
  int i;
#ifdef EXR_MIGRATION_TX_CANDIDATE
  const char *export_path=NULL;
#endif
  c->cancel_at = -1;
  c->inject_at = -1;
  if (argc >= 2 && !strcmp(argv[1], "--version")) { printf("exreader-legacy-migrate %s (EXReader SDK %s)\n", 
#ifdef EXR_MIGRATION_RECOVERY_CANDIDATE
    LM_RECOVERY_VERSION,
#else
    LM_TOOL_VERSION,
#endif
    exr_version()); return 0; }
  if (argc < 2) { usage(); return 1; }
  c->cmd = argv[1];
  for (i = 2; i < argc; i++) {
    const char *a = argv[i];
    if (!strcmp(a, "--pack") && i + 1 < argc) c->pack_path = argv[++i];
    else if (!strcmp(a, "--target") && i + 1 < argc) c->target = argv[++i];
    else if (!strcmp(a, "--report") && i + 1 < argc) c->report_path = argv[++i];
#ifdef EXR_MIGRATION_TX_CANDIDATE
    else if (!strcmp(a, "--output") && i + 1 < argc) export_path = argv[++i];
#endif
#ifdef EXR_MIGRATION_RECOVERY_CANDIDATE
    else if (!strcmp(a,"--recovery-font") && i+1<argc) c->recovery_font=argv[++i];
#endif
    else if (!strcmp(a, "--allow-partial")) c->allow_partial = 1;
    else if (!strcmp(a, "--dry-run")) c->dry_run = 1;
    else if (!strcmp(a, "--break-lock")) c->break_lock = 1;
    else if (!strcmp(a, "--inject") && i + 1 < argc) {
      const char *spec = argv[++i], *at = strchr(spec, '@');
      size_t n = at ? (size_t)(at - spec) : strlen(spec);
      const char *enabled = getenv("EXR_MIGRATE_TEST_FAULTS");
      if (!enabled || strcmp(enabled, "1") || n >= sizeof(c->inject)) { fputs("--inject is a test hook and needs EXR_MIGRATE_TEST_FAULTS=1\n", stderr); return 1; }
      memcpy(c->inject, spec, n);
      c->inject[n] = 0;
      if (at) c->inject_at = atoi(at + 1);
      if (!strcmp(c->inject, "cancel") && at) c->cancel_at = c->inject_at;
    } else { usage(); return 1; }
  }
  lm_binary_stdout();
  signal(SIGINT, on_signal);
  signal(SIGTERM, on_signal);
#ifdef EXR_MIGRATION_RECOVERY_CANDIDATE
  if(strcmp(c->cmd,"inspect")||c->target) {
    lm_err gate_error={{0},{0}};
    if(!lr_gate(&c->recovery,argv[0],c->cmd,c->target,c->pack_path,c->recovery_font,c->break_lock,cancel_cb,c,&gate_error)) {
      g_recovery=c->recovery;fail(c,O_REJECTED,gate_error.code,"%s; no target SDK open",gate_error.message);emit(c);return EXIT_CODE[c->out];
    }
    g_recovery=c->recovery;c->recovery_gate_ok=1;c->target=lr_original_target(c->recovery);
    if(!strcmp(c->cmd,"recover-migration"))c->recovery_retry=1;
    if(!strcmp(c->cmd,"dump")||!strcmp(c->cmd,"verify")||!strcmp(c->cmd,"export-ledger")) {
      if(!lr_read_view(c->recovery,&c->read_view,&gate_error)){fail(c,O_BUSY,gate_error.code,"%s; no target SDK open",gate_error.message);emit(c);return EXIT_CODE[c->out];}
      c->target=c->read_view;
    }
  }
#endif

#ifdef EXR_MIGRATION_TX_CANDIDATE
  if(!strcmp(c->cmd,"recover-mirror")) {
    int reconciled=0;
    if(!c->target || c->pack_path || c->dry_run) { usage();return 1; }
    mirror_run_id(c);
    c->sidecar=path_join(c->target,".legacy-map.json");
    c->pending=path_join(c->target,".migration-pending.json");
    c->lock=path_join(c->target,".migrate-lock");
    if(mirror_lock_acquire(c)) {
      reconciled=mirror_reconcile(c);
      if(reconciled) {
        c->out=O_SUCCESS;
        snprintf(c->code,sizeof(c->code),"%s",reconciled==2?"mirror-cleanup-pending":"ok");
        snprintf(c->message,sizeof(c->message),"%s",c->mirror_state?c->mirror_state:"no pending intent; no database or mirror changed");
      }
    }
    cleanup(c);emit(c);return EXIT_CODE[c->out];
  }
  if(!strcmp(c->cmd,"export-ledger")) {
    void *data=NULL;size_t size=0;int found=0;
    if(!c->target || !export_path || lm_exists(export_path)) { fputs("export-ledger requires --target and a new --output file\n",stderr);return 1; }
    if(check_target_header(c) && exr_library_open(c->target,&c->lib,&c->err)==EXR_OK &&
       exr_library_migration_ledger_get(c->lib,&data,&size,&found,&c->err)==EXR_OK && found &&
       export_new_file(export_path,data,size)) {
      exr_free(data);exr_library_close(c->lib);puts("ledger exported");return 0;
    }
    exr_free(data);if(c->lib) exr_library_close(c->lib);
    fputs("cannot export ledger\n",stderr);return 3;
  }
#endif
  if (!strcmp(c->cmd, "dump")) {
    if (!c->target) { usage(); return 1; }
    c->sidecar = path_join(c->target, ".legacy-map.json");
#ifdef EXR_MIGRATION_TX_CANDIDATE
    if(check_target_header(c)) {
      exr_library *reader=NULL;void *data=NULL;size_t size=0;int found=0;
      if(exr_library_open(c->target,&reader,&c->err)!=EXR_OK) sdk_fail(c,"opening library");
      else {
        if(exr_library_migration_ledger_get(reader,&data,&size,&found,&c->err)!=EXR_OK) sdk_fail(c,"reading transactional ledger");
        else if(found) {
          lm_mirror_file mirror;
          if(mirror_sidecar_snapshot(c,&mirror) && (!mirror.present || sidecar_check_envelope(c,c->sidecar)) &&
             mirror_check_read(c,data,size)) sidecar_parse(c,(const char *)data,size);
        }
        else {
          lm_mirror_file mirror, target, pending;lm_mirror_intent intent;
          lm_err e={{0},{0}};
          c->pending=path_join(c->target,".migration-pending.json");
          if(mirror_sidecar_snapshot(c,&mirror)) {
            if(!lm_mirror_snapshot(c->target,0,0,&target,NULL,NULL,&e) ||
               !lm_mirror_intent_read(c->pending,&intent,&pending,&e)) mirror_fail(c,&e);
            else if(pending.present) {
              c->pending_retained=1;
              if(intent.version==3) c->recovery_barrier=1;
              c->mirror_state=intent.version==3?"recovery-unverified":"pending";
              if(!target.present || !intent.target_was_present || intent.before_found ||
                 strcmp(target.identity,intent.target_identity) ||
                 !lm_mirror_original_file(&intent,&mirror))
                fail(c,O_FAILED,"mirror-recovery-conflict","pending intent does not explain a target without an internal ledger");
            }
            if(c->out==O_NONE && mirror.present) sidecar_load(c,c->sidecar);
          }
        }
        exr_free(data);exr_library_close(reader);
      }
    }
#else
    if (lm_exists(c->sidecar)) sidecar_load(c, c->sidecar);
#endif
#ifdef EXR_MIGRATION_TX_CANDIDATE
    if (c->out == O_NONE && c->pending_retained)
      fputs("mirror pending: dump uses the current library and validated ledger provenance; no historical commit claim\n",stderr);
#endif
    if (c->out == O_NONE) dump_library(c);
    if (c->out != O_NONE) { emit(c); }
    if (c->lib) exr_library_close(c->lib);
    return c->out == O_NONE ? 0 : EXIT_CODE[c->out];
  }
  if (!c->pack_path) { usage(); return 1; }
  if (!strcmp(c->cmd, "inspect")) {
    lm_err e;
    memset(&e, 0, sizeof(e));
    if (!lm_pack_open(c->pack_path, &c->pack, &e)) fail(c, O_REJECTED, e.code, "%s", e.message);
    else if (!lm_pack_verify(&c->pack, cancel_cb, c, &e)) fail(c, O_REJECTED, e.code, "%s", e.message);
    else { c->books_expected = (unsigned)c->pack.books->n; c->notes_expected = (unsigned)c->pack.notes->n; run_inspect(c); }
  } else if (!strcmp(c->cmd, "migrate")
#ifdef EXR_MIGRATION_RECOVERY_CANDIDATE
             || !strcmp(c->cmd,"recover-migration")
#endif
             ) {
    if (!c->target) { usage(); return 1; }
    run_migrate(c);
    if (c->out == O_NONE) fail(c, O_FAILED, "internal", "migration ended without an outcome");
    cleanup(c);
  } else if (!strcmp(c->cmd, "verify")) {
    lm_err e;
    memset(&e, 0, sizeof(e));
    if (!c->target) { usage(); return 1; }
    if (!lm_pack_open(c->pack_path, &c->pack, &e)) fail(c, O_REJECTED, e.code, "%s", e.message);
    else if (!lm_pack_verify(&c->pack, cancel_cb, c, &e)) fail(c, O_REJECTED, e.code, "%s", e.message);
    else run_verify(c);
    if (c->lib) { exr_library_close(c->lib); c->lib = NULL; }
  } else { usage(); return 1; }
  emit(c);
  return EXIT_CODE[c->out];
}

#ifdef _WIN32
int wmain(int argc, wchar_t **wargv) {
  char **argv = lm_xalloc(((size_t)argc + 1) * sizeof(*argv));
  int i;
  for (i = 0; i < argc; i++) {
    int n = WideCharToMultiByte(CP_UTF8, 0, wargv[i], -1, NULL, 0, NULL, NULL);
    argv[i] = lm_xalloc((size_t)n + 1);
    WideCharToMultiByte(CP_UTF8, 0, wargv[i], -1, argv[i], n, NULL, NULL);
  }
  return real_main(argc, argv);
}
#else
int main(int argc, char **argv) { return real_main(argc, argv); }
#endif
