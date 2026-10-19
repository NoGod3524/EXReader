/* SPDX-License-Identifier: MIT */
#include "document_internal.h"

/* Construction is atomic: the document remains private until every input is copied and projected.
 */
static exr_status copy_string(exr_document *d, const char *source, const char **out, exr_error *e) {
  size_t n = 0, at = 0, room = EXR_MAX_TEXT - d->model_bytes;
  uint32_t cp;
  if (!source)
    source = "";
  while (n < room && source[n])
    n++;
  if (n == room)
    return exr_fail(e, EXR_LIMIT, "Constructed model strings exceed 64 MiB");
  while (at < n)
    if (!exr_next(source, n, &at, &cp))
      return exr_fail(e, EXR_ENCODING, "Construction strings must be UTF-8");
  *out = exr_model_copy(d, source, n);
  return *out ? EXR_OK : exr_fail(e, EXR_MEMORY, "Construction string allocation failed");
}
/* Paths are raw names, not URIs. Literal %, # and ? are linked using percent-encoded URIs. */
int exr_canonical_path(const char *s) {
  size_t start = 0, i, depth = 0, n;
  if (!s || !(n = strlen(s)) || n > 2046)
    return 0;
  for (i = 0; i <= n; i++) {
    unsigned char c = (unsigned char)s[i];
    if (c && (c < 32 || c == 127 || c == ':' || c == '\\'))
      return 0;
    if (!c || c == '/') {
      size_t length = i - start;
      if (!length || (length == 1 && s[start] == '.') ||
          (length == 2 && s[start] == '.' && s[start + 1] == '.') || ++depth > 256)
        return 0;
      start = i + 1;
    }
  }
  return 1;
}
static int string_order(const void *a, const void *b) {
  return strcmp(*(const char *const *)a, *(const char *const *)b);
}
static int unique(const char **names, size_t count, int skip_empty) {
  size_t i;
  if (count < 2)
    return 1;
  qsort(names, count, sizeof(*names), string_order);
  for (i = 1; i < count; i++)
    if ((!skip_empty || names[i][0]) && !strcmp(names[i - 1], names[i]))
      return 0;
  return 1;
}
static int resource_order(const void *a, const void *b) {
  const exr_resource *x = *(const exr_resource *const *)a, *y = *(const exr_resource *const *)b;
  return strcmp(x->path, y->path);
}
static size_t resource_at(const exr_document *d, const exr_resource *const *sorted,
                          const char *path) {
  size_t low = 0, high = d->resource_count;
  while (low < high) {
    size_t middle = low + (high - low) / 2;
    int order = strcmp(sorted[middle]->path, path);
    if (!order)
      return (size_t)(sorted[middle] - d->resources);
    if (order < 0)
      low = middle + 1;
    else
      high = middle;
  }
  return SIZE_MAX;
}
static exr_status attributes(exr_document *d, exr_node *node, const exr_node_input *input,
                             exr_error *e) {
  const char *names[256];
  exr_attribute *a;
  size_t i;
  exr_status status;
  if (input->attribute_count > 256)
    return exr_fail(e, EXR_LIMIT, "More than 256 node attributes");
  if (!input->attribute_count)
    return EXR_OK;
  if (!input->attributes)
    return exr_fail(e, EXR_ARGUMENT, "Missing attribute array");
  a = calloc(input->attribute_count, sizeof(*a));
  if (!a)
    return exr_fail(e, EXR_MEMORY, "Attribute allocation failed");
  node->attributes = a;
  node->attribute_count = input->attribute_count;
  for (i = 0; i < input->attribute_count; i++) {
    if (!input->attributes[i].name || !input->attributes[i].name[0] || !input->attributes[i].value)
      return exr_fail(e, EXR_ARGUMENT, "Attributes require a name and value");
    status = copy_string(d, input->attributes[i].name, &a[i].name, e);
    if (status != EXR_OK)
      return status;
    status = copy_string(d, input->attributes[i].value, &a[i].value, e);
    if (status != EXR_OK)
      return status;
    names[i] = a[i].name;
  }
  if (!unique(names, input->attribute_count, 0))
    return exr_fail(e, EXR_ARGUMENT, "Duplicate attribute name");
  return EXR_OK;
}
exr_status exr_document_create(const exr_document_input *input, exr_document **out, exr_error *e) {
  exr_document *d = NULL;
  const exr_resource **sorted = NULL;
  const char **names = NULL, *title;
  size_t *chapter_map = NULL, stack[256], depth = 0, i, bytes = 0, name_capacity;
  exr_status status = EXR_MEMORY;
  if (!out)
    return exr_fail(e, EXR_ARGUMENT, "Missing document output");
  *out = NULL;
  if (e)
    memset(e, 0, sizeof(*e));
  if (!input)
    return exr_fail(e, EXR_ARGUMENT, "Missing construction input");
  if (input->node_count > EXR_MAX_NODES || input->chapter_count > 10000 ||
      input->resource_count > 10000)
    return exr_fail(e, EXR_LIMIT, "Construction node/chapter/resource limit exceeded");
  if (input->node_count < 2 || !input->nodes || !input->chapter_count || !input->chapters ||
      (input->resource_count && !input->resources))
    return exr_fail(e, EXR_ARGUMENT, "Construction requires a document tree and chapters");
  d = calloc(1, sizeof(*d));
  if (!d)
    goto bad;
  d->format = EXR_CUSTOM;
  d->owns_chapter_strings = 1;
  status = copy_string(d, input->title, &title, e);
  if (status != EXR_OK)
    goto bad;
  d->title = (char *)title;
  chapter_map = malloc(input->node_count * sizeof(*chapter_map));
  name_capacity =
      input->chapter_count > input->resource_count ? input->chapter_count : input->resource_count;
  names = malloc(name_capacity * sizeof(*names));
  d->chapters = calloc(input->chapter_count, sizeof(*d->chapters));
  status = EXR_MEMORY;
  if (!chapter_map || !names || !d->chapters)
    goto bad;
  memset(chapter_map, 255, input->node_count * sizeof(*chapter_map));
  d->chapter_count = d->chapter_capacity = input->chapter_count;
  if (input->resource_count) {
    d->resources = calloc(input->resource_count, sizeof(*d->resources));
    d->resource_data = calloc(input->resource_count, sizeof(*d->resource_data));
    sorted = malloc(input->resource_count * sizeof(*sorted));
    if (!d->resources || !d->resource_data || !sorted)
      goto bad;
    d->resource_count = d->resource_capacity = input->resource_count;
  }
  for (i = 0; i < d->resource_count; i++) {
    const exr_resource_input *from = &input->resources[i];
    exr_resource *to = &d->resources[i];
    if (!from->info.path || !from->info.path[0] || (!from->data && from->size)) {
      status = exr_fail(e, EXR_ARGUMENT, "Invalid resource path or bytes");
      goto bad;
    }
    if (from->size > 32 * 1024 * 1024 || from->size > EXR_MAX_INPUT - bytes) {
      status = exr_fail(e, EXR_LIMIT, "Resource exceeds 32 MiB or total resources exceed 128 MiB");
      goto bad;
    }
    status = copy_string(d, from->info.id, &to->id, e);
    if (status != EXR_OK)
      goto bad;
    status = copy_string(d, from->info.path, &to->path, e);
    if (status != EXR_OK)
      goto bad;
    status = copy_string(d, from->info.media_type, &to->media_type, e);
    if (status != EXR_OK)
      goto bad;
    status = copy_string(d, from->info.properties, &to->properties, e);
    if (status != EXR_OK)
      goto bad;
    if (!exr_canonical_path(to->path)) {
      status = exr_fail(e, EXR_ARGUMENT, "Resource path must be canonical and relative");
      goto bad;
    }
    names[i] = to->id;
    sorted[i] = to;
    if (from->data) {
      d->resource_data[i].bytes = malloc(from->size ? from->size : 1);
      if (!d->resource_data[i].bytes) {
        status = EXR_MEMORY;
        goto bad;
      }
      if (from->size)
        memcpy(d->resource_data[i].bytes, from->data, from->size);
      d->resource_data[i].size = from->size;
    }
    bytes += from->size;
  }
  if (!unique(names, d->resource_count, 1)) {
    status = exr_fail(e, EXR_ARGUMENT, "Duplicate resource ID");
    goto bad;
  }
  if (d->resource_count > 1)
    qsort(sorted, d->resource_count, sizeof(*sorted), resource_order);
  for (i = 1; i < d->resource_count; i++)
    if (!strcmp(sorted[i - 1]->path, sorted[i]->path)) {
      status = exr_fail(e, EXR_ARGUMENT, "Duplicate resource path");
      goto bad;
    }
  for (i = 0; i < d->chapter_count; i++) {
    const exr_chapter_input *from = &input->chapters[i];
    exr_chapter *to = &d->chapters[i];
    if (!from->path || !from->path[0] || !from->root || from->root >= input->node_count ||
        chapter_map[from->root] != SIZE_MAX || input->nodes[from->root].kind != EXR_NODE_CHAPTER ||
        input->nodes[from->root].parent != 0) {
      status = exr_fail(e, EXR_ARGUMENT, "Invalid or repeated chapter root/path");
      goto bad;
    }
    status = copy_string(d, from->id, &to->id, e);
    if (status != EXR_OK)
      goto bad;
    status = copy_string(d, from->path, &to->path, e);
    if (status != EXR_OK)
      goto bad;
    if (!exr_canonical_path(to->path)) {
      status = exr_fail(e, EXR_ARGUMENT, "Chapter path must be canonical and relative");
      goto bad;
    }
    to->root = from->root;
    to->resource = resource_at(d, sorted, to->path);
    to->in_spine = to->linear = from->in_reading_order != 0;
    chapter_map[from->root] = i;
    names[i] = to->path;
  }
  if (!unique(names, d->chapter_count, 0)) {
    status = exr_fail(e, EXR_ARGUMENT, "Duplicate chapter path");
    goto bad;
  }
  for (i = 0; i < d->chapter_count; i++)
    names[i] = d->chapters[i].id;
  if (!unique(names, d->chapter_count, 1)) {
    status = exr_fail(e, EXR_ARGUMENT, "Duplicate chapter ID");
    goto bad;
  }
  for (i = 0; i < input->node_count; i++) {
    const exr_node_input *from = &input->nodes[i];
    exr_node *to;
    size_t chapter = SIZE_MAX;
    if (from->kind < EXR_NODE_DOCUMENT || from->kind > EXR_NODE_NOTE ||
        (from->kind == EXR_NODE_TEXT ? !from->text : from->text != NULL)) {
      status = exr_fail(e, EXR_ARGUMENT, "Invalid node kind or text payload");
      goto bad;
    }
    if (!i) {
      if (from->kind != EXR_NODE_DOCUMENT || from->parent != SIZE_MAX) {
        status = exr_fail(e, EXR_ARGUMENT, "Node zero must be the document root");
        goto bad;
      }
    } else {
      if (from->parent >= i || from->kind == EXR_NODE_DOCUMENT) {
        status = exr_fail(e, EXR_ARGUMENT, "Parent must precede its child");
        goto bad;
      }
      while (depth && stack[depth - 1] != from->parent)
        depth--;
      if (!depth) {
        status = exr_fail(e, EXR_ARGUMENT, "Node array must use preorder");
        goto bad;
      }
      if (depth == 256) {
        status = exr_fail(e, EXR_LIMIT, "Constructed tree exceeds depth 256");
        goto bad;
      }
      if (d->nodes[from->parent].kind == EXR_NODE_TEXT ||
          d->nodes[from->parent].kind == EXR_NODE_BREAK ||
          d->nodes[from->parent].kind == EXR_NODE_IMAGE) {
        status = exr_fail(e, EXR_ARGUMENT, "Text, break and image nodes cannot have children");
        goto bad;
      }
      if (!from->parent) {
        if (from->kind != EXR_NODE_CHAPTER || chapter_map[i] == SIZE_MAX) {
          status = exr_fail(e, EXR_ARGUMENT, "Every root child must be a listed chapter");
          goto bad;
        }
        chapter = chapter_map[i];
      } else {
        if (from->kind == EXR_NODE_CHAPTER) {
          status = exr_fail(e, EXR_ARGUMENT, "Chapters must be root children");
          goto bad;
        }
        chapter = d->nodes[from->parent].chapter;
      }
    }
    if (exr_model_node(d, from->parent, chapter, from->kind, NULL, NULL, 0) == SIZE_MAX) {
      status = EXR_MEMORY;
      goto bad;
    }
    to = &d->nodes[i];
    if (from->name) {
      status = copy_string(d, from->name, &to->name, e);
      if (status != EXR_OK)
        goto bad;
    }
    if (from->text) {
      status = copy_string(d, from->text, &to->text, e);
      if (status != EXR_OK)
        goto bad;
    }
    status = attributes(d, to, from, e);
    if (status != EXR_OK)
      goto bad;
    stack[depth++] = i;
  }
  status = exr_model_finish(d, e);
  if (status != EXR_OK)
    goto bad;
  free(sorted);
  free(names);
  free(chapter_map);
  *out = d;
  return EXR_OK;
bad:
  free(sorted);
  free(names);
  free(chapter_map);
  exr_document_free(d);
  if (!e || !e->message[0])
    exr_fail(e, status, "Document construction failed");
  return status;
}
