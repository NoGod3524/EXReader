/* SPDX-License-Identifier: MIT */
#ifndef EXR_BASE_INTERNAL_H
#define EXR_BASE_INTERNAL_H
#include "exr/base.h"
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
/* MSVC's C headers do not provide max_align_t. These allocator payloads hold
   ordinary scalar/aggregate C objects; the union preserves their alignment. */
typedef union { long double number; void *pointer; int64_t integer; } exr_allocation_alignment;
typedef struct {
  char *data;
  size_t size, capacity;
} exr_buffer;
exr_status exr_fail(exr_error *error, exr_status status, const char *fmt, ...);
exr_status exr_control_cancel(const exr_control *control, exr_error *error);
exr_status exr_control_poll(const exr_control *control, exr_stage stage,
                             uint64_t completed, uint64_t total, exr_error *error);
exr_status exr_kmp_prefix(const char *query,size_t size,const exr_control *control,uint32_t **out,exr_error *error);
exr_status exr_find_bytes(const char *text,size_t size,const char *query,size_t query_size,size_t from,
                            const exr_control *control,size_t *start,size_t *end,exr_error *error);
int exr_grow(void **data, size_t *capacity, size_t count, size_t element);
char *exr_copy(const char *text, size_t size);
exr_status exr_export_time(char modified[32], exr_error *error);
exr_status exr_xml_text(const char *text, size_t size, const char *field, exr_error *error);
int exr_append(exr_buffer *buf, const void *data, size_t size);
exr_status exr_number_text(exr_buffer *out,int value,const char *format,exr_error *error);
int exr_codepoint(exr_buffer *buf, uint32_t cp);
int exr_next(const char *text, size_t size, size_t *offset, uint32_t *cp);
FILE *exr_fopen(const char *path, const char *mode);
exr_status exr_read(const char *path, unsigned char **data, size_t *size, exr_error *error);
exr_status exr_decode(const void *data, size_t size, exr_buffer *buf, exr_error *error);
int exr_uri_path(exr_buffer *buffer, const char *path);
int exr_uri_decode(const char *text, size_t size, char out[2048]);
int exr_resolve_path(const char *base, const char *href, char out[2048]);

exr_status exr_file_source_limit(const char *path,uint64_t maximum,exr_source *source,exr_error *error);
exr_status exr_file_source(const char *path,exr_source *source,exr_error *error);

/* Read-only file mapping and pagefile-backed anonymous mapping. Mapping bytes
   are file/pagefile backed, not an SDK heap buffer. exr_unmap releases both. */
typedef struct { void *address; size_t size; void *file; void *mapping; } exr_mapping;
exr_status exr_map_file(const char *path,exr_mapping *mapping,exr_error *error);
exr_status exr_map_anonymous(size_t size,exr_mapping *mapping,exr_error *error);
void exr_unmap(exr_mapping *mapping);

#endif
