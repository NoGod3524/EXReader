/* SPDX-License-Identifier: MIT */
#include "reader_book_information.h"
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#if defined(_MSC_VER)
#define READER_BI_THREAD __declspec(thread)
#else
#define READER_BI_THREAD _Thread_local
#endif

#define TEXT_CAP ((size_t)READER_BOOK_INFORMATION_MAX_TEXT_BYTES)
#define KEY_CAP ((size_t)READER_BOOK_INFORMATION_MAX_KEY_BYTES)
#define PROPS ((size_t)READER_BOOK_INFORMATION_MAX_PROPERTIES)
/* Worst kept payload: book_key, format, location_kind, title, author, parser
 * title and digest (3319 bytes) plus 32 key/value pairs (36928 bytes). */
#define ARENA_BYTES ((size_t)40960)

struct reader_book_information {
  reader_book_information_view view;
  reader_book_information_property props[READER_BOOK_INFORMATION_MAX_PROPERTIES];
  size_t used;
  char arena[ARENA_BYTES];
};

/* Guards this module's own reentrancy per thread; the catalog and the library
 * add their owner-thread and no-reentry rules on top. */
static READER_BI_THREAD int active_depth;

/* One bounded SHA-256 for the single requested original: the SDK has no public
 * digest, and the product key already carries the expected value. */
typedef struct { uint32_t h[8]; uint64_t bytes; unsigned char block[64]; size_t fill; } sha256_state;
static const uint32_t SHA_K[64] = {
  0x428a2f98u,0x71374491u,0xb5c0fbcfu,0xe9b5dba5u,0x3956c25bu,0x59f111f1u,0x923f82a4u,0xab1c5ed5u,
  0xd807aa98u,0x12835b01u,0x243185beu,0x550c7dc3u,0x72be5d74u,0x80deb1feu,0x9bdc06a7u,0xc19bf174u,
  0xe49b69c1u,0xefbe4786u,0x0fc19dc6u,0x240ca1ccu,0x2de92c6fu,0x4a7484aau,0x5cb0a9dcu,0x76f988dau,
  0x983e5152u,0xa831c66du,0xb00327c8u,0xbf597fc7u,0xc6e00bf3u,0xd5a79147u,0x06ca6351u,0x14292967u,
  0x27b70a85u,0x2e1b2138u,0x4d2c6dfcu,0x53380d13u,0x650a7354u,0x766a0abbu,0x81c2c92eu,0x92722c85u,
  0xa2bfe8a1u,0xa81a664bu,0xc24b8b70u,0xc76c51a3u,0xd192e819u,0xd6990624u,0xf40e3585u,0x106aa070u,
  0x19a4c116u,0x1e376c08u,0x2748774cu,0x34b0bcb5u,0x391c0cb3u,0x4ed8aa4au,0x5b9cca4fu,0x682e6ff3u,
  0x748f82eeu,0x78a5636fu,0x84c87814u,0x8cc70208u,0x90befffau,0xa4506cebu,0xbef9a3f7u,0xc67178f2u};
#define ROR(x,n) (((x)>>(n))|((x)<<(32-(n))))
static void sha_block(sha256_state *s, const unsigned char *p) {
  uint32_t w[64], a, b, c, d, e, f, g, h;
  int i;
  for (i = 0; i < 16; i++)
    w[i] = ((uint32_t)p[i*4] << 24) | ((uint32_t)p[i*4+1] << 16) | ((uint32_t)p[i*4+2] << 8) | (uint32_t)p[i*4+3];
  for (i = 16; i < 64; i++) {
    uint32_t s0 = ROR(w[i-15],7) ^ ROR(w[i-15],18) ^ (w[i-15] >> 3);
    uint32_t s1 = ROR(w[i-2],17) ^ ROR(w[i-2],19) ^ (w[i-2] >> 10);
    w[i] = w[i-16] + s0 + w[i-7] + s1;
  }
  a = s->h[0]; b = s->h[1]; c = s->h[2]; d = s->h[3]; e = s->h[4]; f = s->h[5]; g = s->h[6]; h = s->h[7];
  for (i = 0; i < 64; i++) {
    uint32_t t1 = h + (ROR(e,6) ^ ROR(e,11) ^ ROR(e,25)) + ((e & f) ^ (~e & g)) + SHA_K[i] + w[i];
    uint32_t t2 = (ROR(a,2) ^ ROR(a,13) ^ ROR(a,22)) + ((a & b) ^ (a & c) ^ (b & c));
    h = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
  }
  s->h[0] += a; s->h[1] += b; s->h[2] += c; s->h[3] += d;
  s->h[4] += e; s->h[5] += f; s->h[6] += g; s->h[7] += h;
}
static void sha_begin(sha256_state *s) {
  static const uint32_t init[8] = {0x6a09e667u,0xbb67ae85u,0x3c6ef372u,0xa54ff53au,
                                   0x510e527fu,0x9b05688cu,0x1f83d9abu,0x5be0cd19u};
  memcpy(s->h, init, sizeof(init)); s->bytes = 0; s->fill = 0;
}
static void sha_update(sha256_state *s, const unsigned char *p, size_t n) {
  s->bytes += n;
  while (n) {
    size_t take = 64 - s->fill;
    if (take > n) take = n;
    memcpy(s->block + s->fill, p, take); s->fill += take; p += take; n -= take;
    if (s->fill == 64) { sha_block(s, s->block); s->fill = 0; }
  }
}
static void sha_finish(sha256_state *s, char hex[65]) {
  static const char alphabet[] = "0123456789abcdef";
  uint64_t bits = s->bytes * 8u;
  unsigned char pad = 0x80, zero = 0, length[8];
  int i, j;
  sha_update(s, &pad, 1);
  while (s->fill != 56) sha_update(s, &zero, 1);
  for (i = 0; i < 8; i++) length[i] = (unsigned char)(bits >> (56 - 8*i));
  sha_update(s, length, 8);
  for (i = 0; i < 8; i++)
    for (j = 0; j < 4; j++) {
      unsigned char v = (unsigned char)(s->h[i] >> (24 - 8*j));
      hex[i*8 + j*2] = alphabet[v >> 4]; hex[i*8 + j*2 + 1] = alphabet[v & 15];
    }
  hex[64] = 0;
}

static reader_book_information_status fail(reader_book_information_error *e, reader_book_information_status code,
                                           int catalog, int sdk, const char *message) {
  if (e) {
    e->status = code; e->catalog_code = catalog; e->sdk_code = sdk;
    strncpy(e->message, message, sizeof(e->message) - 1);
    e->message[sizeof(e->message) - 1] = 0;
  }
  return code;
}

typedef struct { const reader_book_information_options *options; int cancelled_seen; } poll_state;
static int poll(poll_state *p) {
  if (p->options && p->options->cancelled && p->options->cancelled(p->options->context)) p->cancelled_seen = 1;
  return p->cancelled_seen;
}
static int sdk_poll(void *context) { return poll((poll_state *)context); }

/* Strict UTF-8 validation for values that came from outside this module. The
 * product catalog and the SDK already reject invalid UTF-8; this is defensive. */
static int utf8_valid(const char *s) {
  const unsigned char *p = (const unsigned char *)s;
  while (*p) {
    unsigned a = *p++, n, v, i;
    if (a < 0x80) continue;
    if (a >= 0xc2 && a <= 0xdf) { n = 1; v = a & 31u; }
    else if (a >= 0xe0 && a <= 0xef) { n = 2; v = a & 15u; }
    else if (a >= 0xf0 && a <= 0xf4) { n = 3; v = a & 7u; }
    else return 0;
    for (i = 0; i < n; i++) {
      if ((*p & 0xc0) != 0x80) return 0;
      v = (v << 6) | (*p++ & 0x3fu);
    }
    if ((n == 2 && v < 0x800) || (n == 3 && v < 0x10000) || v > 0x10ffff || (v >= 0xd800 && v <= 0xdfff)) return 0;
  }
  return 1;
}

/* Copies at most cap bytes of a NUL-terminated string into the snapshot arena,
 * cutting only at a UTF-8 scalar boundary and flagging the cut. */
static const char *keep(reader_book_information *r, const char *s, size_t cap, int *truncated) {
  size_t n = 0;
  char *at;
  if (truncated) *truncated = 0;
  if (!s) return NULL;
  while (n <= cap && s[n]) n++;
  if (n > cap) {
    n = cap;
    if (truncated) *truncated = 1;
    while (n > 0 && ((unsigned char)s[n] & 0xc0) == 0x80) n--;
  }
  if (r->used + n + 1 > ARENA_BYTES) return NULL;
  at = r->arena + r->used;
  memcpy(at, s, n); at[n] = 0; r->used += n + 1;
  return at;
}

/* Splits "format:sha256" without touching either store. */
static int split_key(const char *key, char digest[65]) {
  const char *colon;
  size_t n, i, total;
  if (!key || !key[0]) return 0;
  total = strlen(key);
  if (total > KEY_CAP) return 0;
  colon = strchr(key, ':');
  if (!colon || colon == key) return 0;
  n = (size_t)(colon - key);
  if (n > 8) return 0;
  /* Product formats are lowercase tokens, and two of the nine formats carry a
   * digit: fb2 and the rest of the fixed vocabulary stay accepted here. */
  for (i = 0; i < n; i++)
    if (!((key[i] >= 'a' && key[i] <= 'z') || (key[i] >= '0' && key[i] <= '9'))) return 0;
  if (total != n + 1 + 64) return 0;
  for (i = 0; i < 64; i++) {
    char c = colon[1 + i];
    if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return 0;
  }
  memcpy(digest, colon + 1, 65);
  return 1;
}

/* Re-derives the identity from the stored product row: its keys and its format
 * column must agree before any local work starts. */
static int row_digest(const char *key, const char *format, char digest[65]) {
  size_t n = strlen(format), i;
  if (strncmp(key, format, n) != 0 || key[n] != ':' || strlen(key + n + 1) != 64) return 0;
  for (i = 0; i < 64; i++) {
    char c = key[n + 1 + i];
    if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return 0;
  }
  memcpy(digest, key + n + 1, 65);
  return 1;
}

typedef struct { reader_book_information *r; int ok; int64_t sdk_id; } product_fill;
static int fill_product(void *context, const reader_catalog_row *row) {
  product_fill *f = (product_fill *)context;
  reader_book_information *r = f->r;
  reader_book_information_view *v = &r->view;
  /* location_kind is NULL for a cloud-only row: it comes from the local mapping. */
  if (!row->book_key || !row->format || !row->title || !row->author) return 1;
  if (!utf8_valid(row->book_key) || !utf8_valid(row->format) || !utf8_valid(row->title) ||
      !utf8_valid(row->author) || (row->location_kind && !utf8_valid(row->location_kind))) return 1;
  v->book_key = keep(r, row->book_key, KEY_CAP, NULL);
  v->format = keep(r, row->format, 16, NULL);
  v->location_kind = row->location_kind ? keep(r, row->location_kind, 32, NULL) : "";
  v->title = keep(r, row->title, TEXT_CAP, &v->title_truncated);
  v->author = keep(r, row->author, TEXT_CAP, &v->author_truncated);
  v->author_known = row->author[0] != 0;
  v->favorite = row->favorite != 0;
  v->deleted = row->deleted != 0;
  v->product_source_bytes = row->source_bytes;
  f->sdk_id = row->sdk_book_id;
  f->ok = v->book_key && v->format && v->title && v->author;
  return 0;
}

typedef enum { HASH_SAME, HASH_DIFFERENT, HASH_CANCELLED, HASH_IO, HASH_MEMORY } hash_result;
/* Hashes exactly this one stored original, 64 KiB at a time, polling between
 * chunks; it never materializes the book and never touches another row. */
static hash_result hash_source(const exr_source *src, poll_state *p, const char *expect, char hex[65]) {
  unsigned char *buffer;
  sha256_state sha;
  uint64_t offset = 0;
  if (!src->read_at) return HASH_IO;
  buffer = (unsigned char *)malloc(READER_BOOK_INFORMATION_HASH_CHUNK);
  if (!buffer) return HASH_MEMORY;
  sha_begin(&sha);
  while (offset < src->size) {
    uint64_t left = src->size - offset;
    size_t want = left < (uint64_t)READER_BOOK_INFORMATION_HASH_CHUNK
                    ? (size_t)left : (size_t)READER_BOOK_INFORMATION_HASH_CHUNK;
    size_t got;
    if (poll(p)) { free(buffer); return HASH_CANCELLED; }
    got = src->read_at(src->context, offset, buffer, want);
    if (got == 0 || got > want) { free(buffer); return HASH_IO; }
    sha_update(&sha, buffer, got);
    offset += got;
  }
  free(buffer);
  if (poll(p)) return HASH_CANCELLED;
  sha_finish(&sha, hex);
  return strcmp(hex, expect) == 0 ? HASH_SAME : HASH_DIFFERENT;
}

/* Fills parser fields from public SDK calls only. Field states stay in the view;
 * the only failures returned here are cancellation and exhaustion. */
static reader_book_information_status read_parser(reader_book_information *r, exr_library *library,
                                                  int64_t sdk_id, poll_state *p) {
  reader_book_information_view *v = &r->view;
  exr_error err;
  memset(&err, 0, sizeof(err));
  if (!strcmp(v->format, "pdf") || !strcmp(v->format, "cbz")) {
    exr_fixed_open_options options;
    exr_fixed_document *doc = NULL;
    exr_metadata_entry *entries = NULL;
    const char *title;
    exr_status st;
    size_t count = 0, i;
    memset(&options, 0, sizeof(options));
    options.struct_size = sizeof(options);
    options.control.cancelled = sdk_poll;
    options.control.context = p;
    st = exr_library_fixed_source(library, sdk_id, &options, &doc, &err);
    if (st == EXR_CANCELLED) return READER_BOOK_INFORMATION_CANCELLED;
    if (st != EXR_OK) {
      v->parser_status = st == EXR_PASSWORD ? READER_BOOK_INFORMATION_PARSER_PASSWORD_REQUIRED
                                            : READER_BOOK_INFORMATION_PARSER_FAILED;
      return READER_BOOK_INFORMATION_OK;
    }
    (void)exr_fixed_pages(doc, &count);
    v->page_count_known = 1;
    v->page_count = (uint64_t)count;
    title = exr_fixed_title(doc);
    if (title && title[0]) {
      v->parser_title = keep(r, title, TEXT_CAP, &v->parser_title_truncated);
      if (!v->parser_title) { exr_fixed_free(doc); return READER_BOOK_INFORMATION_MEMORY; }
    }
    st = exr_fixed_load_metadata(doc, &options.control, &entries, &count, &err);
    if (st == EXR_CANCELLED) { exr_fixed_free(doc); return READER_BOOK_INFORMATION_CANCELLED; }
    if (st == EXR_OK) {
      for (i = 0; i < count; i++) {
        const char *key = entries[i].key, *value = entries[i].value;
        reader_book_information_property *q;
        if (v->property_count >= PROPS || !key || !value || !key[0] ||
            !utf8_valid(key) || !utf8_valid(value)) {
          v->properties_omitted++;
          continue;
        }
        q = &r->props[v->property_count];
        q->key = keep(r, key, KEY_CAP, &q->key_truncated);
        q->value = keep(r, value, TEXT_CAP, &q->value_truncated);
        if (!q->key || !q->value) {
          exr_metadata_free(entries, count);
          exr_fixed_free(doc);
          return READER_BOOK_INFORMATION_MEMORY;
        }
        v->property_count++;
      }
      exr_metadata_free(entries, count);
      v->parser_status = READER_BOOK_INFORMATION_PARSER_OK;
    } else {
      /* Page count and title above are still real values; only properties failed. */
      v->parser_status = READER_BOOK_INFORMATION_PARSER_FAILED;
    }
    exr_fixed_free(doc);
    return READER_BOOK_INFORMATION_OK;
  }
  if (!strcmp(v->format, "epub")) {
    exr_library_epub_info info;
    exr_status st;
    memset(&info, 0, sizeof(info));
    info.struct_size = sizeof(info);
    st = exr_library_epub_info_get(library, sdk_id, &info, &err);
    if (st == EXR_CANCELLED) return READER_BOOK_INFORMATION_CANCELLED;
    if (st == EXR_OK) {
      v->epub_mode_known = 1;
      v->epub_bounded_storage = info.bounded_storage != 0;
      v->epub_global_extent_known = info.global_extent_known != 0;
      v->parser_status = READER_BOOK_INFORMATION_PARSER_OK;
    } else {
      v->parser_status = READER_BOOK_INFORMATION_PARSER_FAILED;
    }
    return READER_BOOK_INFORMATION_OK;
  }
  v->parser_status = READER_BOOK_INFORMATION_PARSER_NO_PUBLIC_FIELDS;
  return READER_BOOK_INFORMATION_OK;
}

#define CANCEL() do { result = fail(error, READER_BOOK_INFORMATION_CANCELLED, 0, 0, "Cancelled"); goto done; } while (0)

reader_book_information_status reader_book_information_read(reader_catalog *catalog, exr_library *library,
    const char *book_key, const reader_book_information_options *options,
    reader_book_information **out, reader_book_information_error *error) {
  reader_book_information_status result = READER_BOOK_INFORMATION_OK;
  reader_book_information *r = NULL;
  reader_book_information_view *v;
  poll_state p;
  product_fill fill;
  reader_catalog_error ce;
  char digest[65];
  int found = 0, rc;
  if (error) memset(error, 0, sizeof(*error));
  if (out) *out = NULL;
  if (!out || !catalog) return fail(error, READER_BOOK_INFORMATION_ARGUMENT, 0, 0, "Missing catalog or output");
  if (!split_key(book_key, digest))
    return fail(error, READER_BOOK_INFORMATION_ARGUMENT, 0, 0, "book_key is not format:sha256");
  if (options && options->struct_size < sizeof(*options))
    return fail(error, READER_BOOK_INFORMATION_ARGUMENT, 0, 0, "Options record is too small");
  if (active_depth)
    return fail(error, READER_BOOK_INFORMATION_REENTRANT, 0, 0, "Book information read is not reentrant");
  active_depth++;
  p.options = options; p.cancelled_seen = 0;
  memset(&fill, 0, sizeof(fill)); memset(&ce, 0, sizeof(ce));
  r = (reader_book_information *)calloc(1, sizeof(*r));
  if (!r) {
    result = fail(error, READER_BOOK_INFORMATION_MEMORY, 0, 0, "Snapshot allocation failed");
    goto done;
  }
  v = &r->view; v->struct_size = sizeof(*v); fill.r = r;
  if (poll(&p)) CANCEL();
  rc = reader_catalog_metadata(catalog, book_key, fill_product, &fill, &found, &ce);
  if (rc != 0) {
    result = fail(error, READER_BOOK_INFORMATION_CATALOG, rc, 0, ce.message);
    goto done;
  }
  if (!found) {
    result = fail(error, READER_BOOK_INFORMATION_NOT_FOUND, 0, 0, "No product book for this key");
    goto done;
  }
  if (!fill.ok) {
    result = fail(error, READER_BOOK_INFORMATION_CATALOG, 0, 0, "Product row is malformed");
    goto done;
  }
  if (!row_digest(v->book_key, v->format, digest)) {
    result = fail(error, READER_BOOK_INFORMATION_CATALOG, 0, 0, "Product key is not format:sha256");
    goto done;
  }
  if (poll(&p)) CANCEL();
  if (fill.sdk_id <= 0) { v->availability = READER_BOOK_INFORMATION_CLOUD_ONLY; goto finish; }
  if (!library) { v->availability = READER_BOOK_INFORMATION_LOCAL_UNCHECKED; goto finish; }
  {
    exr_source source;
    exr_error err;
    exr_status st;
    int mismatch = 0;
    memset(&source, 0, sizeof(source)); memset(&err, 0, sizeof(err));
    st = exr_library_source(library, fill.sdk_id, &source, &err);
    if (st == EXR_CANCELLED) CANCEL();
    if (st == EXR_MEMORY) {
      result = fail(error, READER_BOOK_INFORMATION_MEMORY, 0, (int)st, err.message);
      goto done;
    }
    if (st != EXR_OK) { v->availability = READER_BOOK_INFORMATION_LOCAL_MISSING; goto finish; }
    if (source.size != v->product_source_bytes) mismatch = 1;
    else if (options && options->verify_source && source.read_at) {
      char hex[65];
      int truncated = 0;
      hash_result h = hash_source(&source, &p, digest, hex);
      if (h == HASH_CANCELLED || h == HASH_MEMORY) {
        if (source.release) source.release(source.context);
        if (h == HASH_CANCELLED) CANCEL();
        result = fail(error, READER_BOOK_INFORMATION_MEMORY, 0, 0, "Hash buffer allocation failed");
        goto done;
      }
      if (h == HASH_IO) {
        if (source.release) source.release(source.context);
        v->availability = READER_BOOK_INFORMATION_LOCAL_MISSING;
        goto finish;
      }
      if (h == HASH_DIFFERENT) mismatch = 1;
      else {
        v->identity = READER_BOOK_INFORMATION_IDENTITY_SHA256;
        v->verified_bytes = source.size;
        v->verified_sha256 = keep(r, hex, 64, &truncated);
        if (!v->verified_sha256) {
          if (source.release) source.release(source.context);
          result = fail(error, READER_BOOK_INFORMATION_MEMORY, 0, 0, "Snapshot arena exhausted");
          goto done;
        }
      }
    } else {
      v->identity = READER_BOOK_INFORMATION_IDENTITY_SIZE_ONLY;
      v->verified_bytes = source.size;
    }
    if (source.release) source.release(source.context);
    if (mismatch) {
      v->identity = READER_BOOK_INFORMATION_IDENTITY_MISMATCH;
      v->verified_bytes = 0;
      v->verified_sha256 = NULL;
      v->availability = READER_BOOK_INFORMATION_LOCAL_MISMATCH;
      goto finish;
    }
    v->availability = READER_BOOK_INFORMATION_LOCAL_PRESENT;
    if (options && options->read_parser_fields) {
      if (poll(&p)) CANCEL();
      result = read_parser(r, library, fill.sdk_id, &p);
      if (result != READER_BOOK_INFORMATION_OK) goto done;
      if (p.cancelled_seen) CANCEL();
    }
  }
finish:
  v->properties = r->props;
  if (poll(&p)) CANCEL();
  *out = r;
  r = NULL;
done:
  free(r);
  active_depth--;
  return result;
}

const reader_book_information_view *reader_book_information_get(const reader_book_information *snapshot) {
  return snapshot ? &snapshot->view : NULL;
}

void reader_book_information_free(reader_book_information *snapshot) { free(snapshot); }
