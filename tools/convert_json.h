/* SPDX-License-Identifier: MIT */
#ifndef EXREADER_CONVERT_JSON_H
#define EXREADER_CONVERT_JSON_H
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {
  char *data;
  size_t size, capacity;
  int failed;
} cv_text;
void cv_text_init(cv_text *t);
void cv_text_free(cv_text *t);
int cv_text_append(cv_text *t, const void *data, size_t size);
int cv_text_string(cv_text *t, const char *s);
int cv_text_format(cv_text *t, const char *format, ...);
/* Escaped JSON string including surrounding quotes; invalid UTF-8 is replaced. */
int cv_text_json(cv_text *t, const char *s);

typedef enum { CV_JSON_NULL, CV_JSON_BOOL, CV_JSON_NUMBER, CV_JSON_STRING,
               CV_JSON_ARRAY, CV_JSON_OBJECT } cv_json_type;
typedef struct cv_json cv_json;
struct cv_json {
  cv_json_type type;
  int boolean;
  double number;
  int integral;
  long long integer;
  char *string;
  cv_json **items;
  char **keys;
  size_t count;
};
/* Strict RFC 8259 parser with a 64-level depth limit and duplicate-key
   rejection. Returns NULL and an owned message on failure. */
cv_json *cv_json_parse(const char *text, size_t size, char **error);
void cv_json_free(cv_json *value);
const cv_json *cv_json_get(const cv_json *object, const char *key);
#ifdef __cplusplus
}
#endif
#endif
