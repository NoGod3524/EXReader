/* SPDX-License-Identifier: MIT */
#ifndef LM_LEDGER_H
#define LM_LEDGER_H
#include "lm.h"
#include <stdlib.h>
#include <string.h>

/* String-keyed index; keys are borrowed and must outlive the table. */
typedef struct { const char **keys; size_t *vals; size_t cap, n; } lm_hm;
static void *lm_xalloc(size_t n) {
  void *p = calloc(1, n ? n : 1);
  if (!p) { fputs("{\"result\":\"failed\",\"code\":\"out-of-memory\"}\n", stderr); exit(3); }
  return p;
}
static char *lm_xdup(const char *s) {
  size_t n = strlen(s);
  char *p = lm_xalloc(n + 1);
  memcpy(p, s, n);
  return p;
}
static uint32_t lm_hash(const char *s) {
  uint32_t h = 2166136261u;
  for (; *s; s++) h = (h ^ (unsigned char)*s) * 16777619u;
  return h;
}
static void lm_hm_put(lm_hm *m, const char *key, size_t val);
static void lm_hm_grow(lm_hm *m) {
  lm_hm old = *m;
  size_t i;
  m->cap = old.cap ? old.cap * 2 : 64;
  m->keys = lm_xalloc(m->cap * sizeof(*m->keys));
  m->vals = lm_xalloc(m->cap * sizeof(*m->vals));
  m->n = 0;
  for (i = 0; i < old.cap; i++)
    if (old.keys[i]) lm_hm_put(m, old.keys[i], old.vals[i]);
  free(old.keys);
  free(old.vals);
}
static void lm_hm_put(lm_hm *m, const char *key, size_t val) {
  size_t at;
  if (!m->cap || (m->n + 1) * 2 > m->cap) lm_hm_grow(m);
  at = lm_hash(key) & (m->cap - 1);
  while (m->keys[at]) {
    if (!strcmp(m->keys[at], key)) { m->vals[at] = val; return; }
    at = (at + 1) & (m->cap - 1);
  }
  m->keys[at] = key;
  m->vals[at] = val;
  m->n++;
}
static int lm_hm_get(const lm_hm *m, const char *key, size_t *val) {
  size_t at;
  if (!m->cap) return 0;
  at = lm_hash(key) & (m->cap - 1);
  while (m->keys[at]) {
    if (!strcmp(m->keys[at], key)) { *val = m->vals[at]; return 1; }
    at = (at + 1) & (m->cap - 1);
  }
  return 0;
}

enum { K_REFLOW = 0, K_FIXED = 1, K_AUDIO = 2 };
/* One migrated (or previously migrated) legacy book. Fields after `created`
   are expectations for the books this run inserted; they drive stage verification. */
typedef struct {
  char *legacy, *audio_id, *retained;
  char sha[65], idkey[24];
  int64_t book_id;
  int kind;
  int touched, created;
  char *title, *author, *tags;
  int favorite, status;
  size_t position;
  int anchored;
  double audio_seconds;
} lm_book;
typedef struct {
  char *legacy, *book_legacy, *method, *reason, *retained;
  char fp[65];
  int64_t new_id;
  int kind, located, touched;
  size_t start, end, page;
  char *text;
} lm_note;
typedef struct {
  lm_book *books; size_t book_n, book_cap;
  lm_note *notes; size_t note_n, note_cap;
  lm_hm book_index, note_index, id_index;
  char **packs; size_t pack_n;
} lm_ledger;

static lm_book *lm_ledger_book(lm_ledger *l, const char *legacy, int create) {
  size_t at;
  if (lm_hm_get(&l->book_index, legacy, &at)) return &l->books[at];
  if (!create) return NULL;
  if (l->book_n == l->book_cap) {
    size_t cap = l->book_cap ? l->book_cap * 2 : 32;
    lm_book *grown = lm_xalloc(cap * sizeof(*grown));
    if (l->book_n) memcpy(grown, l->books, l->book_n * sizeof(*grown));
    free(l->books);
    l->books = grown;
    l->book_cap = cap;
    /* Keys point at the heap-owned legacy strings, so only values move. */
    memset(&l->book_index, 0, sizeof(l->book_index));
    memset(&l->id_index, 0, sizeof(l->id_index));
    for (at = 0; at < l->book_n; at++) {
      lm_hm_put(&l->book_index, l->books[at].legacy, at);
      if (l->books[at].book_id > 0) lm_hm_put(&l->id_index, l->books[at].idkey, at);
    }
  }
  memset(&l->books[l->book_n], 0, sizeof(lm_book));
  l->books[l->book_n].legacy = lm_xdup(legacy);
  lm_hm_put(&l->book_index, l->books[l->book_n].legacy, l->book_n);
  return &l->books[l->book_n++];
}
static lm_note *lm_ledger_note(lm_ledger *l, const char *legacy, int create) {
  size_t at;
  if (lm_hm_get(&l->note_index, legacy, &at)) return &l->notes[at];
  if (!create) return NULL;
  if (l->note_n == l->note_cap) {
    size_t cap = l->note_cap ? l->note_cap * 2 : 64;
    lm_note *grown = lm_xalloc(cap * sizeof(*grown));
    if (l->note_n) memcpy(grown, l->notes, l->note_n * sizeof(*grown));
    free(l->notes);
    l->notes = grown;
    l->note_cap = cap;
    memset(&l->note_index, 0, sizeof(l->note_index));
    for (at = 0; at < l->note_n; at++) lm_hm_put(&l->note_index, l->notes[at].legacy, at);
  }
  memset(&l->notes[l->note_n], 0, sizeof(lm_note));
  l->notes[l->note_n].legacy = lm_xdup(legacy);
  lm_hm_put(&l->note_index, l->notes[l->note_n].legacy, l->note_n);
  return &l->notes[l->note_n++];
}
/* Re-key a book's SDK identity; the id index lets us find an earlier claimant. */
static void lm_ledger_set_id(lm_ledger *l, lm_book *b, int64_t id) {
  b->book_id = id;
  snprintf(b->idkey, sizeof(b->idkey), "%lld", (long long)id);
  lm_hm_put(&l->id_index, b->idkey, (size_t)(b - l->books));
}
static lm_book *lm_ledger_claim(lm_ledger *l, int64_t id) {
  char key[24];
  size_t at;
  snprintf(key, sizeof(key), "%lld", (long long)id);
  if (!lm_hm_get(&l->id_index, key, &at) || l->books[at].book_id != id) return NULL;
  return &l->books[at];
}
#endif
