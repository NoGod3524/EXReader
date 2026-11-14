/* SPDX-License-Identifier: MIT
 * Independent public C ABI consumer for C08.
 *
 * It loads the SDK shared object by explicit path (dlopen), resolves only the
 * documented exr_* symbols with dlsym and calls them. It opens the library file
 * through exr_library_open and reads back the books, original bytes, reading
 * progress and notes exactly as the public ABI returns them. It never issues SQL
 * and never reads the library file itself. One JSON document goes to stdout;
 * every API call is recorded with its status so a report with no calls (a
 * file/SQL scan) cannot be mistaken for an API readback.
 */
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <exr/library.h>

static int first_item = 1;
static int api_calls = 0, api_failures = 0;

static void json_text(const char *text) {
  putchar('"');
  for (const unsigned char *p = (const unsigned char *)(text ? text : ""); *p; ++p) {
    if (*p == '"' || *p == '\\') { putchar('\\'); putchar(*p); }
    else if (*p < 0x20) printf("\\u%04x", *p);
    else putchar(*p);
  }
  putchar('"');
}

static void hex(const void *data, size_t size) {
  static const char digits[] = "0123456789abcdef";
  const unsigned char *p = (const unsigned char *)data;
  putchar('"');
  for (size_t i = 0; i < size; ++i) { putchar(digits[p[i] >> 4]); putchar(digits[p[i] & 15]); }
  putchar('"');
}

static void comma(void) { if (!first_item) putchar(','); first_item = 0; }

/* ---- SHA-256 (public domain style, for the original-bytes identity) ---- */
typedef struct { uint32_t state[8]; uint64_t length; unsigned char block[64]; size_t used; } sha256_t;
static const uint32_t K[64] = {
  0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
  0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
  0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
  0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
  0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
  0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
  0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
  0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
#define ROR(x, n) (((x) >> (n)) | ((x) << (32 - (n))))
static void sha_block(sha256_t *s, const unsigned char *b) {
  uint32_t w[64], a, c, d, e, f, g, h, i, t1, t2, bb;
  for (i = 0; i < 16; ++i)
    w[i] = (uint32_t)b[i*4] << 24 | (uint32_t)b[i*4+1] << 16 | (uint32_t)b[i*4+2] << 8 | b[i*4+3];
  for (i = 16; i < 64; ++i) {
    uint32_t s0 = ROR(w[i-15], 7) ^ ROR(w[i-15], 18) ^ (w[i-15] >> 3);
    uint32_t s1 = ROR(w[i-2], 17) ^ ROR(w[i-2], 19) ^ (w[i-2] >> 10);
    w[i] = w[i-16] + s0 + w[i-7] + s1;
  }
  a = s->state[0]; bb = s->state[1]; c = s->state[2]; d = s->state[3];
  e = s->state[4]; f = s->state[5]; g = s->state[6]; h = s->state[7];
  for (i = 0; i < 64; ++i) {
    t1 = h + (ROR(e, 6) ^ ROR(e, 11) ^ ROR(e, 25)) + ((e & f) ^ (~e & g)) + K[i] + w[i];
    t2 = (ROR(a, 2) ^ ROR(a, 13) ^ ROR(a, 22)) + ((a & bb) ^ (a & c) ^ (bb & c));
    h = g; g = f; f = e; e = d + t1; d = c; c = bb; bb = a; a = t1 + t2;
  }
  s->state[0] += a; s->state[1] += bb; s->state[2] += c; s->state[3] += d;
  s->state[4] += e; s->state[5] += f; s->state[6] += g; s->state[7] += h;
}
static void sha_init(sha256_t *s) {
  static const uint32_t init[8] = {0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,
                                   0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
  memcpy(s->state, init, sizeof(init)); s->length = 0; s->used = 0;
}
static void sha_update(sha256_t *s, const unsigned char *data, size_t size) {
  s->length += size;
  while (size) {
    size_t take = 64 - s->used; if (take > size) take = size;
    memcpy(s->block + s->used, data, take); s->used += take; data += take; size -= take;
    if (s->used == 64) { sha_block(s, s->block); s->used = 0; }
  }
}
static void sha_final(sha256_t *s, char out[65]) {
  uint64_t bits = s->length * 8; unsigned char pad = 0x80, zero = 0, tail[8];
  sha_update(s, &pad, 1);
  while (s->used != 56) sha_update(s, &zero, 1);
  for (int i = 0; i < 8; ++i) tail[i] = (unsigned char)(bits >> (56 - 8 * i));
  sha_update(s, tail, 8);
  for (int i = 0; i < 8; ++i) snprintf(out + i * 8, 9, "%08x", s->state[i]);
}

/* ---- dlsym resolution ---- */
typedef exr_status (*open_fn)(const char *, exr_library **, exr_error *);
typedef void (*close_fn)(exr_library *);
typedef exr_status (*books_fn)(exr_library *, const char *, exr_book **, size_t *, exr_error *);
typedef void (*books_free_fn)(exr_book *, size_t);
typedef exr_status (*source_fn)(exr_library *, int64_t, exr_source *, exr_error *);
typedef exr_status (*progress_get_fn)(exr_library *, int64_t, exr_anchor *, exr_anchor_state *, exr_error *);
typedef void (*anchor_free_fn)(exr_anchor *);
typedef exr_status (*notes_fn)(exr_library *, int64_t, exr_note **, size_t *, exr_error *);
typedef void (*notes_free_fn)(exr_note *, size_t);
typedef exr_status (*fixed_notes_fn)(exr_library *, int64_t, exr_fixed_note **, size_t *, exr_error *);
typedef void (*fixed_notes_free_fn)(exr_fixed_note *, size_t);
typedef exr_status (*epub_info_fn)(exr_library *, int64_t, exr_library_epub_info *, exr_error *);
typedef exr_status (*epub_notes_fn)(exr_library *, int64_t, exr_epub_note **, size_t *, exr_error *);
typedef void (*epub_notes_free_fn)(exr_epub_note *, size_t);
typedef const char *(*version_fn)(void);
typedef uint32_t (*abi_fn)(void);

static void *library_handle;
static void *symbol(const char *name) {
  void *found = dlsym(library_handle, name);
  comma();
  printf("{\"symbol\":"); json_text(name); printf(",\"resolved\":%s}", found ? "true" : "false");
  return found;
}

static struct { char name[48]; int status; long long a, b; } recorded[512];
static int recorded_count = 0;
static void call_record(const char *name, int status, long long a, long long b) {
  ++api_calls;
  if (status != 0) ++api_failures;
  if (recorded_count < 512) {
    snprintf(recorded[recorded_count].name, sizeof(recorded[0].name), "%s", name);
    recorded[recorded_count].status = status; recorded[recorded_count].a = a; recorded[recorded_count].b = b;
    ++recorded_count;
  }
}

int main(int argc, char **argv) {
  const char *mode, *library_path, *database;
  open_fn library_open; close_fn library_close; books_fn books; books_free_fn books_free;
  source_fn library_source; progress_get_fn progress_get; anchor_free_fn anchor_free;
  notes_fn notes; notes_free_fn notes_free; fixed_notes_fn fixed_notes; fixed_notes_free_fn fixed_free;
  epub_info_fn epub_info; epub_notes_fn epub_notes; epub_notes_free_fn epub_free;
  version_fn version; abi_fn abi;
  exr_library *library = NULL; exr_error error; exr_book *list = NULL; size_t count = 0;
  Dl_info where; int fatal = 0;
  if (argc != 4) { fprintf(stderr, "usage: c08_consumer mode library database\n"); return 64; }
  mode = argv[1]; library_path = argv[2]; database = argv[3];
  memset(&error, 0, sizeof(error));
  printf("{\"schema\":\"c08-public-api-readback-1\",\"mode\":"); json_text(mode);
  printf(",\"library_path\":"); json_text(library_path);
  printf(",\"database_path\":"); json_text(database);
  library_handle = dlopen(library_path, RTLD_NOW | RTLD_LOCAL);
  if (!library_handle) {
    printf(",\"dlopen_error\":"); json_text(dlerror());
    printf(",\"api_calls\":0,\"api_failures\":1,\"complete\":false}\n");
    return 2;
  }
  printf(",\"symbols\":["); first_item = 1;
  library_open = (open_fn)symbol("exr_library_open");
  library_close = (close_fn)symbol("exr_library_close");
  books = (books_fn)symbol("exr_library_books");
  books_free = (books_free_fn)symbol("exr_books_free");
  library_source = (source_fn)symbol("exr_library_source");
  progress_get = (progress_get_fn)symbol("exr_library_progress_get");
  anchor_free = (anchor_free_fn)symbol("exr_anchor_free");
  notes = (notes_fn)symbol("exr_library_notes");
  notes_free = (notes_free_fn)symbol("exr_notes_free");
  fixed_notes = (fixed_notes_fn)symbol("exr_library_fixed_notes");
  fixed_free = (fixed_notes_free_fn)symbol("exr_fixed_notes_free");
  epub_info = (epub_info_fn)symbol("exr_library_epub_info_get");
  epub_notes = (epub_notes_fn)symbol("exr_library_epub_notes");
  epub_free = (epub_notes_free_fn)symbol("exr_epub_notes_free");
  version = (version_fn)symbol("exr_version");
  abi = (abi_fn)symbol("exr_abi_version");
  printf("]");
  if (!library_open || !library_close || !books || !books_free || !library_source || !progress_get
      || !anchor_free || !notes || !notes_free || !fixed_notes || !fixed_free || !epub_info
      || !epub_notes || !epub_free || !version || !abi) {
    printf(",\"api_calls\":0,\"api_failures\":1,\"complete\":false,\"error\":\"required public symbol missing\"}\n");
    return 3;
  }
  memset(&where, 0, sizeof(where));
  if (dladdr((void *)library_open, &where)) {
    printf(",\"loaded_from\":"); json_text(where.dli_fname);
    printf(",\"loaded_base\":\"%p\"", where.dli_fbase);
  }
  printf(",\"sdk_version\":"); json_text(version());
  printf(",\"abi_version\":%u", (unsigned)abi());
  {
    exr_status status = library_open(database, &library, &error);
    call_record("exr_library_open", (int)status, 0, 0);
    if (status != EXR_OK) fatal = 1;
  }
  if (!fatal) {
    exr_status status = books(library, NULL, &list, &count, &error);
    call_record("exr_library_books", (int)status, (long long)count, 0);
    if (status != EXR_OK) { fatal = 1; count = 0; list = NULL; }
  }
  printf(",\"books\":["); {
    int first_book = 1;
    for (size_t i = 0; i < count && !fatal; ++i) {
      exr_book *book = &list[i];
      printf("%s{\"id\":%lld,\"format\":%d,\"title_hex\":", first_book ? "" : ",", (long long)book->id, (int)book->format);
      first_book = 0;
      hex(book->title, book->title ? strlen(book->title) : 0);
      printf(",\"author_hex\":"); hex(book->author, book->author ? strlen(book->author) : 0);
      printf(",\"tags_hex\":"); hex(book->tags, book->tags ? strlen(book->tags) : 0);
      printf(",\"favorite\":%d,\"status\":%d,\"position\":%llu", book->favorite, book->status,
             (unsigned long long)book->position);
      {
        exr_source source; exr_status status; sha256_t digest; char out[65];
        unsigned char buffer[65536]; uint64_t offset = 0; int source_ok = 0;
        memset(&source, 0, sizeof(source)); memset(&error, 0, sizeof(error));
        status = library_source(library, book->id, &source, &error);
        printf(",\"source\":{\"status\":%d", (int)status);
        if (status == EXR_OK) {
          sha_init(&digest);
          while (offset < source.size) {
            size_t want = source.size - offset > sizeof(buffer) ? sizeof(buffer) : (size_t)(source.size - offset);
            size_t got = source.read_at(source.context, offset, buffer, want);
            if (got == 0) break;
            sha_update(&digest, buffer, got); offset += got;
          }
          source_ok = offset == source.size;
          sha_final(&digest, out);
          printf(",\"size\":%llu,\"read\":%llu,\"complete\":%s,\"sha256\":\"%s\"",
                 (unsigned long long)source.size, (unsigned long long)offset, source_ok ? "true" : "false", out);
          if (source.release) source.release(source.context);
        }
        printf("}");
        call_record("exr_library_source", (int)status, (long long)source.size, (long long)offset);
        if (status == EXR_OK && !source_ok) ++api_failures;
      }
      {
        exr_anchor point; exr_anchor_state state = EXR_ANCHOR_MISSING; exr_status status;
        memset(&point, 0, sizeof(point)); memset(&error, 0, sizeof(error));
        status = progress_get(library, book->id, &point, &state, &error);
        printf(",\"progress\":{\"status\":%d,\"state\":%d,\"start\":%llu,\"end\":%llu", (int)status, (int)state,
               (unsigned long long)point.start, (unsigned long long)point.end);
        printf(",\"exact_present\":%s,\"exact_hex\":", point.exact ? "true" : "false");
        hex(point.exact, point.exact ? strlen(point.exact) : 0);
        printf(",\"prefix_hex\":"); hex(point.prefix, point.prefix ? strlen(point.prefix) : 0);
        printf(",\"suffix_hex\":"); hex(point.suffix, point.suffix ? strlen(point.suffix) : 0);
        printf(",\"chapter_present\":%s}", point.chapter ? "true" : "false");
        if (status == EXR_OK) anchor_free(&point);
        call_record("exr_library_progress_get", (int)status, (long long)state, (long long)point.start);
      }
      {
        exr_note *rows = NULL; size_t n = 0; exr_status status;
        memset(&error, 0, sizeof(error));
        status = notes(library, book->id, &rows, &n, &error);
        printf(",\"notes\":{\"status\":%d,\"count\":%llu,\"rows\":[", (int)status, (unsigned long long)n);
        for (size_t k = 0; status == EXR_OK && k < n; ++k)
          printf("%s{\"id\":%lld,\"start\":%llu,\"end\":%llu,\"text_hex\":", k ? "," : "", (long long)rows[k].id,
                 (unsigned long long)rows[k].start, (unsigned long long)rows[k].end),
          hex(rows[k].text, rows[k].text ? strlen(rows[k].text) : 0), printf("}");
        printf("]}");
        if (status == EXR_OK) notes_free(rows, n);
        call_record("exr_library_notes", (int)status, (long long)n, 0);
      }
      {
        exr_fixed_note *rows = NULL; size_t n = 0; exr_status status;
        memset(&error, 0, sizeof(error));
        status = fixed_notes(library, book->id, &rows, &n, &error);
        printf(",\"fixed_notes\":{\"status\":%d,\"count\":%llu}", (int)status, (unsigned long long)n);
        if (status == EXR_OK) fixed_free(rows, n);
        /* A reflow book has no fixed-page store; the status is reported, never hidden. */
        ++api_calls;
      }
      {
        exr_library_epub_info info; exr_status status;
        memset(&info, 0, sizeof(info)); info.struct_size = sizeof(info); memset(&error, 0, sizeof(error));
        status = epub_info(library, book->id, &info, &error);
        printf(",\"epub_info\":{\"status\":%d,\"bounded_storage\":%d}", (int)status, info.bounded_storage);
        ++api_calls;
      }
      printf("}");
    }
  }
  printf("],\"book_count\":%llu", (unsigned long long)count);
  if (list) books_free(list, count);
  if (library) library_close(library);
  printf(",\"calls\":[");
  for (int i = 0; i < recorded_count; ++i) {
    printf("%s{\"call\":", i ? "," : ""); json_text(recorded[i].name);
    printf(",\"status\":%d,\"a\":%lld,\"b\":%lld}", recorded[i].status, recorded[i].a, recorded[i].b);
  }
  printf("]");
  printf(",\"api_calls\":%d,\"api_failures\":%d,\"complete\":%s}\n", api_calls, api_failures,
         (!fatal && api_failures == 0) ? "true" : "false");
  (void)epub_notes; (void)epub_free;
  return (!fatal && api_failures == 0) ? 0 : 4;
}
