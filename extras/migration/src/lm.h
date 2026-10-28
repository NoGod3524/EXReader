/* SPDX-License-Identifier: MIT */
#ifndef LM_H
#define LM_H
#include "exr/library.h"
#include <stdint.h>
#include <stdio.h>
#include <stddef.h>

#ifdef EXR_MIGRATION_TX_CANDIDATE
#define LM_TOOL_VERSION "0.2.0-tx-candidate"
#else
#define LM_TOOL_VERSION "0.1.0"
#endif
#define LM_PACK_FORMAT "exreader-legacy-pack"
#define LM_MAP_FORMAT "exreader-legacy-map"
#define LM_MANIFEST_MAX ((uint64_t)64 * 1024 * 1024)
#define LM_BOOK_MAX (100000u)
#define LM_NOTE_MAX (2000000u)
#define LM_BOOK_BYTES_MAX ((uint64_t)128 * 1024 * 1024)

/* Growable string; oom is sticky so call sites stay linear. */
typedef struct { char *p; size_t n, cap; int oom; } lm_sb;
void lm_sb_init(lm_sb *b);
void lm_sb_free(lm_sb *b);
void lm_sb_add(lm_sb *b, const char *s, size_t n);
void lm_sb_str(lm_sb *b, const char *s);
void lm_sb_fmt(lm_sb *b, const char *fmt, ...);
void lm_sb_json(lm_sb *b, const char *s, size_t n); /* quoted JSON string */

typedef struct { uint32_t h[8]; uint64_t len; unsigned char buf[64]; size_t fill; } lm_sha;
void lm_sha_init(lm_sha *s);
void lm_sha_add(lm_sha *s, const void *data, size_t n);
void lm_sha_hex(lm_sha *s, char out[65]);
void lm_sha_bytes(const void *data, size_t n, char out[65]);

int lm_utf8_valid(const char *s, size_t n);
int lm_b64_decode(const char *s, size_t n, unsigned char **out, size_t *outn, size_t max);

/* UTF-8 path helpers; every function returns 1 on success. */
FILE *lm_fopen(const char *path, const char *mode);
int lm_exists(const char *path);
int lm_remove(const char *path);
int lm_replace(const char *from, const char *to);
int lm_publish_new(const char *from, const char *to);
int lm_copy(const char *from, const char *to);
int lm_sha_file(const char *path, char out[65], uint64_t *size);
int lm_seek(FILE *f, uint64_t offset);
int lm_file_size(FILE *f, uint64_t *size);
int lm_sync(FILE *f);
uint64_t lm_peak_rss(void);
void lm_binary_stdout(void);

typedef enum { J_NULL, J_BOOL, J_NUM, J_STR, J_ARR, J_OBJ } jtype;
typedef struct jv jv;
struct jv { jtype t; double num; int b; char *s; size_t n; jv **items; char **keys; size_t cap; };
jv *lm_json_parse(const char *s, size_t n, char *err, size_t errcap);
void lm_json_free(jv *v);
const jv *lm_get(const jv *object, const char *key);
const char *lm_get_str(const jv *object, const char *key); /* NULL unless a string */
void lm_json_write(lm_sb *b, const jv *v);
int lm_json_uint(const jv *v, uint64_t *out); /* finite integer 0..2^53 */

typedef struct { char code[48]; char message[256]; } lm_err;
void lm_err_set(lm_err *e, const char *code, const char *fmt, ...);

typedef struct {
  FILE *f; uint64_t size, manifest_off, manifest_len;
  char sha[65]; jv *root; const jv *books, *notes;
} lm_pack;
typedef int (*lm_cancel_fn)(void *context);
int lm_pack_open(const char *path, lm_pack *p, lm_err *e);
int lm_pack_verify(lm_pack *p, lm_cancel_fn cancel, void *context, lm_err *e);
int lm_pack_read(lm_pack *p, uint64_t offset, void *buffer, size_t size);
void lm_pack_close(lm_pack *p);
#endif
