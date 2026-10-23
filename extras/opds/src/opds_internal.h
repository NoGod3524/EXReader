/* SPDX-License-Identifier: MIT */
#ifndef OPDS_INTERNAL_H
#define OPDS_INTERNAL_H
#include "opds.h"
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct opds_ablock { struct opds_ablock *next; size_t used, cap; } opds_ablock;
struct opds_arena {
  opds_ablock *head; size_t total;
  const opds_facet *facets; size_t facet_count;
};

struct opds_arena *arena_new(void);
void arena_free(struct opds_arena *arena);
void *arena_alloc(struct opds_arena *arena, size_t size);
char *arena_strndup(struct opds_arena *arena, const char *s, size_t n);
char *arena_strdup(struct opds_arena *arena, const char *s);

void opds_set_error(opds_error *error, opds_status code, const char *fmt, ...);
opds_status opds_fail(opds_error *error, opds_status code, const char *fmt, ...);

/* Growable byte buffer. */
typedef struct { unsigned char *data; size_t size, cap; } opds_buf;
int buf_append(opds_buf *b, const void *data, size_t n);
void buf_free(opds_buf *b);

typedef struct { uint32_t h[8]; uint64_t len; unsigned char buf[64]; size_t n; } opds_sha;
void opds_sha_init(opds_sha *c);
void opds_sha_update(opds_sha *c, const void *data, size_t size);
void opds_sha_final_hex(opds_sha *c, char out[65]);

/* Scheme://host:port in lower case with default ports kept explicit. */
int opds_url_origin(const char *url, char *out, size_t cap);
/* Resolution that optionally keeps {} for URI templates. */
opds_status opds_url_resolve_ex(const char *base, const char *ref, int keep_braces,
                                char *out, size_t cap);
int opds_ascii_ieq(const char *a, const char *b);
int opds_ascii_iprefix(const char *s, const char *prefix);

/* Mini XML DOM (namespace aware, DTD refused). Owned by an arena. */
typedef struct opds_xattr { const char *ns, *name, *value; } opds_xattr;
typedef struct opds_xnode {
  const char *ns, *name; /* resolved namespace URI ("" none), local name */
  opds_xattr *attrs; size_t attr_count;
  struct opds_xnode *first, *last, *next, *parent;
  const char *text; /* concatenated direct character data, trimmed */
  const char **ns_prefix, **ns_uri; size_t ns_count; /* declarations made on this element */
} opds_xnode;
opds_status opds_xml_parse(struct opds_arena *arena, const char *data, size_t size,
                           const opds_limits *limits, opds_xnode **root, opds_error *error);
const char *opds_xattr_get(const opds_xnode *n, const char *ns, const char *name);
int opds_xis(const opds_xnode *n, const char *ns, const char *name);

/* Mini JSON DOM. */
typedef enum { OJ_NULL, OJ_BOOL, OJ_NUM, OJ_STR, OJ_ARR, OJ_OBJ } opds_jtype;
typedef struct opds_jnode {
  opds_jtype type;
  const char *str;  /* string value or raw number text */
  double num; int boolean;
  const char *key;  /* when a member of an object */
  struct opds_jnode *first, *last, *next;
} opds_jnode;
opds_status opds_json_parse(struct opds_arena *arena, const char *data, size_t size,
                            const opds_limits *limits, opds_jnode **root, opds_error *error);
opds_jnode *opds_jget(const opds_jnode *obj, const char *key);
const char *opds_jstr(const opds_jnode *n);

#define NS_ATOM "http://www.w3.org/2005/Atom"
#define NS_OPDS "http://opds-spec.org/2010/catalog"
#define NS_OPENSEARCH "http://a9.com/-/spec/opensearch/1.1/"
#define NS_DC "http://purl.org/dc/elements/1.1/"
#define NS_DCTERMS "http://purl.org/dc/terms/"
#define NS_XML "http://www.w3.org/XML/1998/namespace"
#define OPDS_URL_MAX 4096
#endif
