/* SPDX-License-Identifier: GPL-3.0-only */
#ifndef EXR_INTERNAL_H
#define EXR_INTERNAL_H
#include "exreader.h"
#include <limits.h>
#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define EXR_MAX_INPUT ((size_t)128 * 1024 * 1024)
#define EXR_MAX_TEXT ((size_t)64 * 1024 * 1024)
#define EXR_MAX_ITEMS ((size_t)4 * 1024 * 1024)
struct exr_document {
  char *text, *title;
  size_t size, text_capacity;
  exr_block *blocks;
  size_t count, capacity;
  exr_format format;
};
typedef struct {
  char *data;
  size_t size, capacity;
} exr_buffer;
exr_status exr_fail(exr_error *error, exr_status status, const char *fmt, ...);
int exr_grow(void **data, size_t *capacity, size_t count, size_t element);
char *exr_copy(const char *text, size_t size);
int exr_append(exr_buffer *buf, const void *data, size_t size);
int exr_codepoint(exr_buffer *buf, uint32_t cp);
int exr_next(const char *text, size_t size, size_t *offset, uint32_t *cp);
FILE *exr_fopen(const char *path, const char *mode);
exr_status exr_read(const char *path, unsigned char **data, size_t *size,
                    exr_error *error);
exr_status exr_decode(const void *data, size_t size, exr_buffer *buf,
                      exr_error *error);
exr_status exr_parse(exr_document *doc, const void *data, size_t size,
                     exr_error *error);
int exr_add_block(exr_document *doc, const char *text, size_t size,
                  unsigned heading);
#endif
