/* SPDX-License-Identifier: MIT */
#include "lm.h"
#include <stdlib.h>
#include <string.h>

/* Pack layout: "EXRLGP1\n" | original blobs | manifest JSON | trailer(56)
   trailer: "EXRLGPT1" | manifest_offset u64le | manifest_size u64le | sha256(manifest) */
#define MAGIC "EXRLGP1\n"
#define TRAILER_MAGIC "EXRLGPT1"
#define TRAILER_SIZE 56u

static uint64_t le64(const unsigned char *p) {
  uint64_t v = 0;
  int i;
  for (i = 7; i >= 0; i--) v = (v << 8) | p[i];
  return v;
}
int lm_pack_read(lm_pack *p, uint64_t offset, void *buffer, size_t size) {
  if (offset > p->size || size > p->size - offset) return 0;
  if (!lm_seek(p->f, offset)) return 0;
  return fread(buffer, 1, size, p->f) == size;
}
void lm_pack_close(lm_pack *p) {
  if (p->f) fclose(p->f);
  lm_json_free(p->root);
  memset(p, 0, sizeof(*p));
}
static int hex_digest(const char *s) {
  size_t i;
  if (!s || strlen(s) != 64) return 0;
  for (i = 0; i < 64; i++)
    if (!((s[i] >= '0' && s[i] <= '9') || (s[i] >= 'a' && s[i] <= 'f'))) return 0;
  return 1;
}
static int unique_ids(const jv *list, lm_err *e, const char *what) {
  size_t i, j;
  for (i = 0; i < list->n; i++) {
    const char *id = lm_get_str(list->items[i], "legacy_id");
    if (!id || !id[0] || !lm_get(list->items[i], "record") || lm_get(list->items[i], "record")->t != J_OBJ) {
      lm_err_set(e, "pack-schema", "%s entry %zu lacks legacy_id or record object", what, i);
      return 0;
    }
  }
  /* Quadratic only below 4096 entries; larger lists use a sorted copy. */
  if (list->n <= 4096) {
    for (i = 0; i < list->n; i++)
      for (j = i + 1; j < list->n; j++)
        if (!strcmp(lm_get_str(list->items[i], "legacy_id"), lm_get_str(list->items[j], "legacy_id"))) {
          lm_err_set(e, "pack-duplicate-id", "duplicate %s legacy_id %s", what, lm_get_str(list->items[i], "legacy_id"));
          return 0;
        }
  } else {
    const char **ids = malloc(list->n * sizeof(*ids));
    int ok = 1;
    if (!ids) { lm_err_set(e, "pack-limit", "out of memory checking identifiers"); return 0; }
    for (i = 0; i < list->n; i++) ids[i] = lm_get_str(list->items[i], "legacy_id");
    /* insertion into a hash set via open addressing */
    {
      size_t cap = 1;
      const char **table;
      while (cap < list->n * 2) cap <<= 1;
      table = calloc(cap, sizeof(*table));
      if (!table) { free(ids); lm_err_set(e, "pack-limit", "out of memory checking identifiers"); return 0; }
      for (i = 0; i < list->n && ok; i++) {
        uint32_t h = 2166136261u;
        size_t at;
        const char *c;
        for (c = ids[i]; *c; c++) h = (h ^ (unsigned char)*c) * 16777619u;
        at = h & (cap - 1);
        while (table[at]) {
          if (!strcmp(table[at], ids[i])) { lm_err_set(e, "pack-duplicate-id", "duplicate %s legacy_id %s", what, ids[i]); ok = 0; break; }
          at = (at + 1) & (cap - 1);
        }
        if (ok) table[at] = ids[i];
      }
      free(table);
    }
    free(ids);
    return ok;
  }
  return 1;
}
int lm_pack_open(const char *path, lm_pack *p, lm_err *e) {
  unsigned char head[8], trailer[TRAILER_SIZE], *manifest = NULL;
  char digest[65], json_error[160];
  uint64_t offset, length;
  const jv *format, *version;
  memset(p, 0, sizeof(*p));
  p->f = lm_fopen(path, "rb");
  if (!p->f) { lm_err_set(e, "pack-unreadable", "cannot open pack %s", path); return 0; }
  if (!lm_file_size(p->f, &p->size)) { lm_err_set(e, "pack-unreadable", "cannot size pack"); goto fail; }
  if (p->size < 8) { lm_err_set(e, "pack-truncated", "pack is shorter than its magic"); goto fail; }
  if (!lm_pack_read(p, 0, head, 8)) { lm_err_set(e, "pack-unreadable", "cannot read pack header"); goto fail; }
  if (memcmp(head, MAGIC, 8)) {
    if (!memcmp(head, "EXRLGP", 6)) lm_err_set(e, "pack-unknown-version", "pack container version %c is not supported", head[6]);
    else lm_err_set(e, "pack-bad-magic", "file is not an EXReader legacy migration pack");
    goto fail;
  }
  if (p->size < 8 + TRAILER_SIZE) { lm_err_set(e, "pack-truncated", "pack has no trailer"); goto fail; }
  if (!lm_pack_read(p, p->size - TRAILER_SIZE, trailer, TRAILER_SIZE)) { lm_err_set(e, "pack-unreadable", "cannot read trailer"); goto fail; }
  if (memcmp(trailer, TRAILER_MAGIC, 8)) { lm_err_set(e, "pack-truncated", "trailer magic missing; the pack is truncated or has trailing data"); goto fail; }
  offset = le64(trailer + 8);
  length = le64(trailer + 16);
  if (offset < 8 || !length || offset > p->size || length > p->size || offset + length != p->size - TRAILER_SIZE) {
    lm_err_set(e, "pack-truncated", "manifest bounds do not match the file size");
    goto fail;
  }
  if (length > LM_MANIFEST_MAX) { lm_err_set(e, "pack-limit", "manifest exceeds %llu bytes", (unsigned long long)LM_MANIFEST_MAX); goto fail; }
  manifest = malloc((size_t)length + 1);
  if (!manifest) { lm_err_set(e, "pack-limit", "cannot allocate manifest"); goto fail; }
  if (!lm_pack_read(p, offset, manifest, (size_t)length)) { lm_err_set(e, "pack-unreadable", "cannot read manifest"); goto fail; }
  manifest[length] = 0;
  lm_sha_bytes(manifest, (size_t)length, digest);
  {
    char expected[65];
    static const char hexd[] = "0123456789abcdef";
    int i;
    for (i = 0; i < 32; i++) { expected[i * 2] = hexd[trailer[24 + i] >> 4]; expected[i * 2 + 1] = hexd[trailer[24 + i] & 15]; }
    expected[64] = 0;
    if (strcmp(digest, expected)) { lm_err_set(e, "pack-manifest-hash", "manifest digest does not match the trailer"); goto fail; }
  }
  p->manifest_off = offset;
  p->manifest_len = length;
  p->root = lm_json_parse((const char *)manifest, (size_t)length, json_error, sizeof(json_error));
  free(manifest);
  manifest = NULL;
  if (!p->root || p->root->t != J_OBJ) { lm_err_set(e, "pack-manifest-json", "manifest is not valid JSON: %s", p->root ? "not an object" : json_error); goto fail; }
  format = lm_get(p->root, "format");
  version = lm_get(p->root, "version");
  if (!format || format->t != J_STR || strcmp(format->s, LM_PACK_FORMAT)) { lm_err_set(e, "pack-unknown-format", "manifest format is not %s", LM_PACK_FORMAT); goto fail; }
  if (!version || version->t != J_NUM || version->num != 1.0) { lm_err_set(e, "pack-unknown-version", "manifest version is not 1"); goto fail; }
  p->books = lm_get(p->root, "books");
  p->notes = lm_get(p->root, "notes");
  if (!p->books || p->books->t != J_ARR || !p->notes || p->notes->t != J_ARR) { lm_err_set(e, "pack-schema", "manifest lacks books/notes arrays"); goto fail; }
  if (p->books->n > LM_BOOK_MAX || p->notes->n > LM_NOTE_MAX) { lm_err_set(e, "pack-limit", "pack exceeds the book or note count limit"); goto fail; }
  if (!unique_ids(p->books, e, "book") || !unique_ids(p->notes, e, "note")) goto fail;
  if (!lm_sha_file(path, p->sha, NULL)) { lm_err_set(e, "pack-unreadable", "cannot hash pack"); goto fail; }
  return 1;
fail:
  free(manifest);
  {
    FILE *f = p->f;
    jv *root = p->root;
    p->f = NULL; p->root = NULL;
    if (f) fclose(f);
    lm_json_free(root);
  }
  return 0;
}
int lm_pack_verify(lm_pack *p, lm_cancel_fn cancel, void *context, lm_err *e) {
  size_t i;
  unsigned char *buffer = malloc(65536);
  if (!buffer) { lm_err_set(e, "pack-limit", "cannot allocate verification buffer"); return 0; }
  for (i = 0; i < p->books->n; i++) {
    const jv *book = p->books->items[i], *file = lm_get(book, "file"), *present = file ? lm_get(file, "present") : NULL;
    const char *id = lm_get_str(book, "legacy_id"), *want;
    uint64_t offset, size, done = 0;
    lm_sha sha;
    char got[65];
    if (!file || file->t != J_OBJ || !present || present->t != J_BOOL) { lm_err_set(e, "pack-schema", "book %s lacks file.present", id); free(buffer); return 0; }
    if (!present->b) continue;
    want = lm_get_str(file, "sha256");
    if (!lm_json_uint(lm_get(file, "offset"), &offset) || !lm_json_uint(lm_get(file, "size"), &size) || !hex_digest(want)) {
      lm_err_set(e, "pack-schema", "book %s has an invalid file offset, size or sha256", id); free(buffer); return 0;
    }
    if (offset < 8 || offset > p->manifest_off || size > p->manifest_off - offset) {
      lm_err_set(e, "pack-truncated", "book %s original lies outside the payload area", id); free(buffer); return 0;
    }
    if (!lm_seek(p->f, offset)) { lm_err_set(e, "pack-unreadable", "cannot seek to book %s", id); free(buffer); return 0; }
    lm_sha_init(&sha);
    while (done < size) {
      size_t take = size - done > 65536 ? 65536 : (size_t)(size - done);
      if (cancel && cancel(context)) { lm_err_set(e, "cancelled", "cancelled while verifying originals"); free(buffer); return 0; }
      if (fread(buffer, 1, take, p->f) != take) { lm_err_set(e, "pack-unreadable", "short read in book %s", id); free(buffer); return 0; }
      lm_sha_add(&sha, buffer, take);
      done += take;
    }
    lm_sha_hex(&sha, got);
    if (strcmp(got, want)) { lm_err_set(e, "pack-hash-mismatch", "book %s original does not match its recorded sha256", id); free(buffer); return 0; }
  }
  free(buffer);
  return 1;
}
