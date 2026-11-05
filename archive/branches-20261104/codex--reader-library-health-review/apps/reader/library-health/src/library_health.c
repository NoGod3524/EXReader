/* SPDX-License-Identifier: MIT */
/* Read-only catalog/original health scan. The only writable state is the
   scanner and the caller's cursor; neither the product catalog nor the SDK
   library is ever modified. */
#include "reader_library_health.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#if defined(_WIN32)
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
typedef DWORD health_thread;
static health_thread health_current_thread(void) { return GetCurrentThreadId(); }
static int health_same_thread(health_thread t) { return t == GetCurrentThreadId(); }
#else
#include <pthread.h>
typedef pthread_t health_thread;
static health_thread health_current_thread(void) { return pthread_self(); }
static int health_same_thread(health_thread t) { return pthread_equal(t, pthread_self()) != 0; }
#endif

/* ---- SHA-256 (FIPS 180-4), streaming, no allocation ---- */
typedef struct {
  uint32_t state[8];
  uint64_t bits;
  unsigned char block[64];
  size_t used;
} health_sha256;
static const uint32_t health_sha_k[64] = {
  0x428a2f98u,0x71374491u,0xb5c0fbcfu,0xe9b5dba5u,0x3956c25bu,0x59f111f1u,0x923f82a4u,0xab1c5ed5u,
  0xd807aa98u,0x12835b01u,0x243185beu,0x550c7dc3u,0x72be5d74u,0x80deb1feu,0x9bdc06a7u,0xc19bf174u,
  0xe49b69c1u,0xefbe4786u,0x0fc19dc6u,0x240ca1ccu,0x2de92c6fu,0x4a7484aau,0x5cb0a9dcu,0x76f988dau,
  0x983e5152u,0xa831c66du,0xb00327c8u,0xbf597fc7u,0xc6e00bf3u,0xd5a79147u,0x06ca6351u,0x14292967u,
  0x27b70a85u,0x2e1b2138u,0x4d2c6dfcu,0x53380d13u,0x650a7354u,0x766a0abbu,0x81c2c92eu,0x92722c85u,
  0xa2bfe8a1u,0xa81a664bu,0xc24b8b70u,0xc76c51a3u,0xd192e819u,0xd6990624u,0xf40e3585u,0x106aa070u,
  0x19a4c116u,0x1e376c08u,0x2748774cu,0x34b0bcb5u,0x391c0cb3u,0x4ed8aa4au,0x5b9cca4fu,0x682e6ff3u,
  0x748f82eeu,0x78a5636fu,0x84c87814u,0x8cc70208u,0x90befffau,0xa4506cebu,0xbef9a3f7u,0xc67178f2u};
#define HEALTH_ROR(x, n) (((x) >> (n)) | ((x) << (32 - (n))))
static void health_sha_compress(health_sha256 *s, const unsigned char *p) {
  uint32_t w[64], a, b, c, d, e, f, g, h;
  size_t i;
  for (i = 0; i < 16; i++)
    w[i] = ((uint32_t)p[i * 4] << 24) | ((uint32_t)p[i * 4 + 1] << 16) |
           ((uint32_t)p[i * 4 + 2] << 8) | (uint32_t)p[i * 4 + 3];
  for (i = 16; i < 64; i++) {
    uint32_t s0 = HEALTH_ROR(w[i - 15], 7) ^ HEALTH_ROR(w[i - 15], 18) ^ (w[i - 15] >> 3);
    uint32_t s1 = HEALTH_ROR(w[i - 2], 17) ^ HEALTH_ROR(w[i - 2], 19) ^ (w[i - 2] >> 10);
    w[i] = w[i - 16] + s0 + w[i - 7] + s1;
  }
  a = s->state[0]; b = s->state[1]; c = s->state[2]; d = s->state[3];
  e = s->state[4]; f = s->state[5]; g = s->state[6]; h = s->state[7];
  for (i = 0; i < 64; i++) {
    uint32_t t1 = h + (HEALTH_ROR(e, 6) ^ HEALTH_ROR(e, 11) ^ HEALTH_ROR(e, 25)) +
                  ((e & f) ^ (~e & g)) + health_sha_k[i] + w[i];
    uint32_t t2 = (HEALTH_ROR(a, 2) ^ HEALTH_ROR(a, 13) ^ HEALTH_ROR(a, 22)) +
                  ((a & b) ^ (a & c) ^ (b & c));
    h = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
  }
  s->state[0] += a; s->state[1] += b; s->state[2] += c; s->state[3] += d;
  s->state[4] += e; s->state[5] += f; s->state[6] += g; s->state[7] += h;
}
static void health_sha_init(health_sha256 *s) {
  static const uint32_t init[8] = {0x6a09e667u,0xbb67ae85u,0x3c6ef372u,0xa54ff53au,
                                   0x510e527fu,0x9b05688cu,0x1f83d9abu,0x5be0cd19u};
  memcpy(s->state, init, sizeof(init));
  s->bits = 0;
  s->used = 0;
}
static void health_sha_update(health_sha256 *s, const unsigned char *data, size_t size) {
  s->bits += (uint64_t)size * 8u;
  while (size) {
    size_t take = 64 - s->used;
    if (take > size) take = size;
    memcpy(s->block + s->used, data, take);
    s->used += take; data += take; size -= take;
    if (s->used == 64) { health_sha_compress(s, s->block); s->used = 0; }
  }
}
static void health_sha_hex(health_sha256 *s, char out[65]) {
  static const char digits[] = "0123456789abcdef";
  unsigned char tail[72];
  uint64_t bits = s->bits;
  size_t pad = (s->used < 56 ? 56 : 120) - s->used, i;
  memset(tail, 0, sizeof(tail));
  tail[0] = 0x80;
  health_sha_update(s, tail, pad);
  for (i = 0; i < 8; i++) tail[i] = (unsigned char)(bits >> (56 - 8 * i));
  health_sha_update(s, tail, 8);
  for (i = 0; i < 32; i++) {
    unsigned char byte = (unsigned char)(s->state[i / 4] >> (24 - 8 * (i % 4)));
    out[i * 2] = digits[byte >> 4];
    out[i * 2 + 1] = digits[byte & 15];
  }
  out[64] = 0;
}

/* ---- scanner state ---- */
typedef struct {
  char key[READER_HEALTH_KEY_CAPACITY];
  char format[16];
  char *sort_title;
  uint64_t bytes;
  int64_t sdk_id;
} health_page_row;

struct reader_health_scanner {
  reader_catalog *catalog;
  exr_library *library;
  reader_health_options options;
  health_thread owner;
  int active;
  unsigned char *buffer;
  health_page_row rows[READER_HEALTH_MAX_ROWS_PER_STEP];
  size_t count;
};

static reader_health_status health_fail(reader_health_error *e, reader_health_status code,
                                        int detail, const char *message) {
  if (e) {
    size_t length = 0;
    e->code = code;
    e->detail_code = detail;
    if (message) {
      while (message[length] && length + 1 < sizeof(e->message)) length++;
      memcpy(e->message, message, length);
    }
    e->message[length] = 0;
  }
  return code;
}
static void health_clear_error(reader_health_error *e) {
  if (e) memset(e, 0, sizeof(*e));
}

const char *reader_health_verdict_name(reader_health_verdict v) {
  switch (v) {
    case READER_HEALTH_VERIFIED: return "verified";
    case READER_HEALTH_CLOUD_ONLY: return "cloud_only";
    case READER_HEALTH_MAPPING_MISSING: return "mapping_missing";
    case READER_HEALTH_SOURCE_UNAVAILABLE: return "source_unavailable";
    case READER_HEALTH_SIZE_MISMATCH: return "size_mismatch";
    case READER_HEALTH_READ_FAILED: return "read_failed";
    case READER_HEALTH_HASH_MISMATCH: return "hash_mismatch";
    case READER_HEALTH_LIMIT_SKIPPED: return "limit_skipped";
  }
  return "unknown";
}
const char *reader_health_status_name(reader_health_status s) {
  switch (s) {
    case READER_HEALTH_OK: return "ok";
    case READER_HEALTH_CANCELLED: return "cancelled";
    case READER_HEALTH_ARGUMENT: return "argument";
    case READER_HEALTH_MEMORY: return "memory";
    case READER_HEALTH_CATALOG: return "catalog";
    case READER_HEALTH_THREAD: return "thread";
    case READER_HEALTH_REENTRY: return "reentry";
    case READER_HEALTH_INTERNAL: return "internal";
  }
  return "unknown";
}

void reader_health_options_init(reader_health_options *o) {
  if (!o) return;
  memset(o, 0, sizeof(*o));
  o->struct_size = sizeof(*o);
  o->rows_per_step = READER_HEALTH_DEFAULT_ROWS_PER_STEP;
  o->buffer_bytes = READER_HEALTH_DEFAULT_BUFFER_BYTES;
  o->max_step_bytes = READER_HEALTH_DEFAULT_STEP_BYTES;
  o->max_book_bytes = READER_HEALTH_DEFAULT_BOOK_BYTES;
  o->max_total_rows = READER_HEALTH_DEFAULT_TOTAL_ROWS;
}
void reader_health_cursor_init(reader_health_cursor *c) {
  if (!c) return;
  memset(c, 0, sizeof(*c));
  c->struct_size = sizeof(*c);
  c->magic = READER_HEALTH_CURSOR_MAGIC;
}

reader_health_status reader_health_create(reader_catalog *catalog, exr_library *library,
                                          const reader_health_options *options,
                                          reader_health_scanner **out, reader_health_error *e) {
  reader_health_scanner *s;
  health_clear_error(e);
  if (out) *out = NULL;
  if (!catalog || !library || !options || !out)
    return health_fail(e, READER_HEALTH_ARGUMENT, 0, "Missing scanner owner, options or output");
  if (options->struct_size != sizeof(*options))
    return health_fail(e, READER_HEALTH_ARGUMENT, 0, "Options struct_size differs from this build");
  if (options->rows_per_step < 1 || options->rows_per_step > READER_HEALTH_MAX_ROWS_PER_STEP ||
      options->buffer_bytes < READER_HEALTH_MIN_BUFFER_BYTES ||
      options->buffer_bytes > READER_HEALTH_MAX_BUFFER_BYTES ||
      options->max_step_bytes < 1 || options->max_step_bytes > READER_HEALTH_MAX_STEP_BYTES ||
      options->max_book_bytes < 1 || options->max_book_bytes > READER_HEALTH_MAX_BOOK_BYTES ||
      options->max_total_rows < 1 || options->max_total_rows > READER_HEALTH_MAX_TOTAL_ROWS)
    return health_fail(e, READER_HEALTH_ARGUMENT, 0, "Option outside the published bounds");
  s = calloc(1, sizeof(*s));
  if (!s) return health_fail(e, READER_HEALTH_MEMORY, 0, "Scanner allocation failed");
  s->buffer = malloc(options->buffer_bytes);
  if (!s->buffer) {
    free(s);
    return health_fail(e, READER_HEALTH_MEMORY, 0, "Read buffer allocation failed");
  }
  s->catalog = catalog;
  s->library = library;
  s->options = *options;
  s->owner = health_current_thread();
  *out = s;
  return READER_HEALTH_OK;
}

static void health_release_page(reader_health_scanner *s) {
  size_t i;
  for (i = 0; i < s->count; i++) {
    free(s->rows[i].sort_title);
    s->rows[i].sort_title = NULL;
  }
  s->count = 0;
}

reader_health_status reader_health_destroy(reader_health_scanner **out, reader_health_error *e) {
  reader_health_scanner *s;
  health_clear_error(e);
  if (!out) return health_fail(e, READER_HEALTH_ARGUMENT, 0, "Missing scanner handle");
  s = *out;
  if (!s) return READER_HEALTH_OK;
  if (!health_same_thread(s->owner))
    return health_fail(e, READER_HEALTH_THREAD, 0, "Scanner belongs to another thread");
  if (s->active)
    return health_fail(e, READER_HEALTH_REENTRY, 0, "Scanner is inside a callback");
  health_release_page(s);
  free(s->buffer);
  free(s);
  *out = NULL;
  return READER_HEALTH_OK;
}

static int health_hex64(const char *p) {
  size_t i;
  for (i = 0; i < 64; i++)
    if (!((p[i] >= '0' && p[i] <= '9') || (p[i] >= 'a' && p[i] <= 'f'))) return 0;
  return p[64] == 0;
}

typedef struct {
  reader_health_scanner *scanner;
  size_t limit;
  int failure; /* 0 ok, 1 malformed, 2 out of memory */
  char message[96];
} health_collector;

static int health_collect(void *context, const reader_catalog_row *row) {
  health_collector *c = context;
  reader_health_scanner *s = c->scanner;
  health_page_row *r;
  size_t key_bytes, format_bytes, title_bytes;
  if (s->count >= c->limit) {
    c->failure = 1;
    snprintf(c->message, sizeof(c->message), "Catalog exceeded the requested page limit");
    return 1;
  }
  if (!row || !row->book_key || !row->format || !row->sort_title) {
    c->failure = 1;
    snprintf(c->message, sizeof(c->message), "Catalog row lacks required text");
    return 1;
  }
  key_bytes = strlen(row->book_key);
  format_bytes = strlen(row->format);
  title_bytes = strlen(row->sort_title);
  if (format_bytes == 0 || format_bytes >= sizeof(s->rows[0].format) ||
      key_bytes != format_bytes + 65 || key_bytes >= READER_HEALTH_KEY_CAPACITY ||
      title_bytes >= READER_HEALTH_SORT_TITLE_CAPACITY ||
      memcmp(row->book_key, row->format, format_bytes) != 0 ||
      row->book_key[format_bytes] != ':' || !health_hex64(row->book_key + format_bytes + 1) ||
      row->source_bytes == 0 || row->sdk_book_id < 0) {
    c->failure = 1;
    snprintf(c->message, sizeof(c->message), "Catalog row identity is malformed");
    return 1;
  }
  r = &s->rows[s->count];
  memcpy(r->key, row->book_key, key_bytes + 1);
  memcpy(r->format, row->format, format_bytes + 1);
  r->bytes = row->source_bytes;
  r->sdk_id = row->sdk_book_id;
  r->sort_title = malloc(title_bytes + 1);
  if (!r->sort_title) {
    c->failure = 2;
    snprintf(c->message, sizeof(c->message), "Sort title allocation failed");
    return 1;
  }
  memcpy(r->sort_title, row->sort_title, title_bytes + 1);
  s->count++;
  return 0;
}

static int health_cancelled(const reader_health_options *o) {
  return o->control.cancelled && o->control.cancelled(o->control.context) != 0;
}

/* Hashes one retained original through the public SDK source. Returns 1 when
   the observation was cancelled and the row must not be delivered. */
static int health_observe(reader_health_scanner *s, const health_page_row *r,
                          reader_health_row *out) {
  exr_source source;
  exr_error error;
  exr_status status;
  health_sha256 hash;
  uint64_t offset = 0;
  unsigned char first = 0, last = 0;
  int cancelled = 0;
  out->sdk_book_id = r->sdk_id;
  out->expected_bytes = r->bytes;
  if (r->sdk_id == 0) {
    out->verdict = READER_HEALTH_CLOUD_ONLY;
    return 0;
  }
  memset(&source, 0, sizeof(source));
  memset(&error, 0, sizeof(error));
  status = exr_library_source(s->library, r->sdk_id, &source, &error);
  if (status != EXR_OK) {
    out->sdk_status = status;
    out->verdict = status == EXR_ARGUMENT ? READER_HEALTH_MAPPING_MISSING
                                          : READER_HEALTH_SOURCE_UNAVAILABLE;
    return 0;
  }
  out->retained_bytes = source.size;
  if (source.size != r->bytes) {
    out->verdict = READER_HEALTH_SIZE_MISMATCH;
    goto release;
  }
  if (source.size > s->options.max_book_bytes) {
    out->verdict = READER_HEALTH_LIMIT_SKIPPED;
    goto release;
  }
  if (!source.read_at || source.size == 0) {
    out->verdict = READER_HEALTH_READ_FAILED;
    goto release;
  }
  health_sha_init(&hash);
  out->verdict = READER_HEALTH_READ_FAILED;
  while (offset < source.size) {
    uint64_t left = source.size - offset;
    size_t want = left < (uint64_t)s->options.buffer_bytes ? (size_t)left : s->options.buffer_bytes;
    size_t got;
    if (health_cancelled(&s->options)) { cancelled = 1; goto release; }
    got = source.read_at(source.context, offset, s->buffer, want);
    if (got == 0 || got > want) {
      out->bytes_read = offset;
      goto release;
    }
    if (offset == 0) first = s->buffer[0];
    health_sha_update(&hash, s->buffer, got);
    offset += got;
    last = s->buffer[got - 1];
    out->bytes_read = offset;
    if (s->options.control.progress)
      s->options.control.progress(s->options.control.context, EXR_STAGE_READ, offset, source.size);
  }
  /* Re-observe both ends: a source invalidated or changed after the hash must
     never be reported healthy. */
  {
    unsigned char again = 0;
    if (source.read_at(source.context, source.size - 1, &again, 1) != 1 || again != last ||
        source.read_at(source.context, 0, &again, 1) != 1 || again != first) {
      out->verdict = READER_HEALTH_READ_FAILED;
      goto release;
    }
  }
  health_sha_hex(&hash, out->observed_sha256);
  out->hashed = 1;
  out->verdict = strcmp(out->observed_sha256, out->expected_sha256) == 0
                     ? READER_HEALTH_VERIFIED
                     : READER_HEALTH_HASH_MISMATCH;
release:
  if (source.release) source.release(source.context);
  return cancelled;
}

reader_health_status reader_health_step(reader_health_scanner *s, reader_health_cursor *cursor,
                                        reader_health_visit visit, void *context,
                                        reader_health_step_info *info, reader_health_error *e) {
  reader_catalog_error catalog_error;
  health_collector gather;
  reader_health_status result = READER_HEALTH_OK;
  size_t limit, i, page_count;
  uint64_t remaining;
  int status;
  health_clear_error(e);
  if (!s) return health_fail(e, READER_HEALTH_ARGUMENT, 0, "Missing scanner");
  if (!health_same_thread(s->owner))
    return health_fail(e, READER_HEALTH_THREAD, 0, "Scanner belongs to another thread");
  if (s->active) return health_fail(e, READER_HEALTH_REENTRY, 0, "Scanner is already running a step");
  if (!cursor || !visit || !info)
    return health_fail(e, READER_HEALTH_ARGUMENT, 0, "Invalid step arguments");
  memset(info, 0, sizeof(*info));
  info->struct_size = sizeof(*info);
  info->steps = 1;
  if (cursor->struct_size != sizeof(*cursor) || cursor->magic != READER_HEALTH_CURSOR_MAGIC)
    return health_fail(e, READER_HEALTH_ARGUMENT, 0, "Cursor was not initialized by this build");
  if (cursor->catalog != NULL && cursor->catalog != s->catalog)
    return health_fail(e, READER_HEALTH_ARGUMENT, 0, "Cursor belongs to another catalog");
  if (cursor->started &&
      (cursor->book_key[0] == 0 ||
       memchr(cursor->sort_title, 0, sizeof(cursor->sort_title)) == NULL ||
       memchr(cursor->book_key, 0, sizeof(cursor->book_key)) == NULL))
    return health_fail(e, READER_HEALTH_ARGUMENT, 0, "Cursor strings are not terminated");
  if (cursor->rows_done >= s->options.max_total_rows) {
    info->limit_reached = 1;
    return READER_HEALTH_OK;
  }
  remaining = s->options.max_total_rows - cursor->rows_done;
  limit = s->options.rows_per_step;
  if ((uint64_t)limit > remaining) limit = (size_t)remaining;
  s->active = 1;
  s->count = 0;
  if (health_cancelled(&s->options)) {
    result = health_fail(e, READER_HEALTH_CANCELLED, 0, "Cancelled before the step");
    goto finish;
  }
  memset(&gather, 0, sizeof(gather));
  gather.scanner = s;
  gather.limit = limit;
  memset(&catalog_error, 0, sizeof(catalog_error));
  status = reader_catalog_page(s->catalog, cursor->started ? cursor->sort_title : NULL,
                               cursor->started ? cursor->book_key : NULL, limit, health_collect,
                               &gather, &catalog_error);
  if (gather.failure == 2) {
    result = health_fail(e, READER_HEALTH_MEMORY, 0, gather.message);
    goto finish;
  }
  if (gather.failure) {
    result = health_fail(e, READER_HEALTH_CATALOG, 0, gather.message);
    goto finish;
  }
  if (status != 0) {
    result = health_fail(e, READER_HEALTH_CATALOG, status, catalog_error.message);
    goto finish;
  }
  page_count = s->count;
  for (i = 0; i < page_count; i++) {
    health_page_row *r = &s->rows[i];
    reader_health_row row;
    size_t format_bytes = strlen(r->format);
    int stopped;
    if (i > 0 && info->bytes_hashed >= s->options.max_step_bytes) {
      info->budget_reached = 1;
      goto finish;
    }
    if (health_cancelled(&s->options)) {
      result = health_fail(e, READER_HEALTH_CANCELLED, 0, "Cancelled between rows");
      goto finish;
    }
    memset(&row, 0, sizeof(row));
    row.struct_size = sizeof(row);
    row.book_key = r->key;
    row.format = r->format;
    row.sort_title = r->sort_title;
    row.expected_bytes = r->bytes;
    memcpy(row.expected_sha256, r->key + format_bytes + 1, 64);
    row.expected_sha256[64] = 0;
    if (health_observe(s, r, &row) || health_cancelled(&s->options)) {
      result = health_fail(e, READER_HEALTH_CANCELLED, 0, "Cancelled while reading an original");
      goto finish;
    }
    info->bytes_hashed += row.bytes_read;
    /* Commit the cursor before delivery so a stop request cannot lose the row. */
    memcpy(cursor->sort_title, r->sort_title, strlen(r->sort_title) + 1);
    memcpy(cursor->book_key, r->key, strlen(r->key) + 1);
    cursor->started = 1;
    cursor->catalog = s->catalog;
    cursor->rows_done++;
    info->rows_delivered++;
    stopped = visit(context, &row);
    if (stopped) {
      info->stopped = 1;
      goto finish;
    }
  }
  if (page_count < limit) info->done = 1;
  else if (cursor->rows_done >= s->options.max_total_rows) info->limit_reached = 1;
finish:
  health_release_page(s);
  s->active = 0;
  return result;
}
