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
#define EXR_MAX_NODES ((size_t)262144)
typedef struct {
  unsigned char *bytes;
  size_t size;
} exr_resource_data;
typedef struct {
  unsigned char *bytes;
  size_t size, refs;
} exr_archive_store;
struct exr_document {
  char *text, *title;
  size_t size, text_capacity;
  exr_block *blocks;
  size_t count, capacity;
  exr_format format;
  exr_node *nodes;
  size_t node_count, node_capacity, model_bytes;
  size_t *last_children;
  size_t last_capacity;
  exr_chapter *chapters;
  size_t chapter_count, chapter_capacity;
  exr_resource *resources;
  size_t resource_count, resource_capacity;
  exr_resource_data *resource_data; /* Copied resources from public construction inputs. */
  int owns_chapter_strings;
  unsigned char *archive;
  size_t archive_size;
  exr_archive_store *shared_archive;
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
exr_status exr_read(const char *path, unsigned char **data, size_t *size, exr_error *error);
exr_status exr_decode(const void *data, size_t size, exr_buffer *buf, exr_error *error);
exr_status exr_anchor_validate(const exr_anchor *anchor, exr_error *error);
exr_status exr_parse(exr_document *doc, const void *data, size_t size, exr_error *error);
exr_status exr_epub_index(const void *data, size_t size, exr_document **out, exr_error *error);
exr_status exr_epub_load(const exr_document *index, size_t part, exr_document **out,
                        exr_error *error);
int exr_add_block(exr_document *doc, const char *text, size_t size, unsigned heading);
char *exr_model_copy(exr_document *doc, const char *text, size_t size);
const char *exr_html_tag(const exr_document *doc, const exr_node *node);
size_t exr_model_node(exr_document *doc, size_t parent, size_t chapter, exr_node_kind kind,
                      const char *name, const char *text, size_t length);
exr_status exr_xhtml(exr_document *doc, const void *data, size_t size, size_t resource,
                     int in_spine, int linear, exr_error *error);
exr_status exr_model_finish(exr_document *doc, exr_error *error);
void exr_model_free(exr_document *doc);
int exr_resolve_path(const char *base, const char *href, char out[2048]);
typedef struct {
  float value;
  int percent;
} exr_length; /* value < 0 means auto */
enum { EXR_CSS_NONE, EXR_CSS_INLINE, EXR_CSS_BLOCK, EXR_CSS_TABLE, EXR_CSS_ROW, EXR_CSS_CELL };
typedef struct {
  char family[128], source[2048], base[2048];
  size_t chapter;
  unsigned flags;
} exr_font_rule;
typedef struct {
  float font_size, leading, indent, border_width;
  const char *family;
  int family_owned;
  int leading_relative, align, display, before, after, border_style;
  unsigned flags;
  exr_direction direction;
  uint32_t color, background, border_color;
  exr_length width, height, max_width, margin[4], padding[4];
} exr_style;
exr_status exr_compute_styles(const exr_document *doc, const exr_layout_config *config,
                              exr_style **styles, exr_font_rule **fonts, size_t *font_count,
                              exr_error *error);
void exr_styles_free(exr_style *styles, size_t count);
int exr_family_next(const char *value, size_t *offset, char out[128]);
int exr_family_equal(const char *a, const char *b);
int exr_parse_font_rule(const char *body, size_t size, const char *base,
                         size_t chapter, exr_font_rule *rule);
size_t exr_css_delimiter(const char *text, size_t size, char delimiter);
#endif
