/* SPDX-License-Identifier: MIT */
#include "formats_internal.h"
#include "graphics_internal.h"

typedef struct { const char *path; size_t part; } nav_path;
typedef struct {
  const exr_document *index;
  const exr_control *control;
  exr_navigation *entries;
  size_t count, capacity, bytes, visited;
  nav_path *paths;
  exr_error *error;
} navigation;
static int ws(unsigned char c) { return c == ' ' || c == '\n' || c == '\r' || c == '\t'; }
static const char *name(const exr_node *n) {
  const char *p;
  if (!n->name) return "";
  p = strrchr(n->name, '|'); return p ? p + 1 : n->name;
}
static int token(const char *s, const char *wanted) {
  size_t n = strlen(wanted);
  while (s && *s) {
    const char *start;
    while (ws((unsigned char)*s)) s++;
    start = s;
    while (*s && !ws((unsigned char)*s)) s++;
    if ((size_t)(s - start) == n && !memcmp(start, wanted, n)) return 1;
  }
  return 0;
}
void exr_navigation_free(exr_navigation *entries, size_t count) {
  size_t i;
  for (i = 0; i < count; i++) {
    free((void *)entries[i].label); free((void *)entries[i].href);
    free((void *)entries[i].base); free((void *)entries[i].role);
  }
  free(entries);
}
static exr_status string(navigation *n, const char *value, size_t limit, const char **out) {
  size_t size;
  if (!value) value = "";
  size = strlen(value);
  if (size > limit || size >= EXR_MAX_TEXT - n->bytes)
    return exr_fail(n->error, EXR_LIMIT, "Navigation metadata exceeds limit");
  *out = exr_copy(value, size);
  if (!*out) return exr_fail(n->error, EXR_MEMORY, "Navigation allocation failed");
  n->bytes += size + 1;
  return EXR_OK;
}
static int path_compare(const void *a, const void *b) {
  return strcmp(((const nav_path *)a)->path, ((const nav_path *)b)->path);
}
static size_t target_part(const navigation *n, const char *base, const char *href) {
  char path[2048]; size_t low = 0, high = n->index->chapter_count;
  if (!href || !*href || !exr_resolve_path(base, href, path)) return SIZE_MAX;
  while (low < high) {
    size_t mid = low + (high - low)/2;
    if (strcmp(n->paths[mid].path, path) < 0) low = mid + 1;
    else high = mid;
  }
  if (low == n->index->chapter_count || strcmp(n->paths[low].path, path)) return SIZE_MAX;
  if (low + 1 < n->index->chapter_count && !strcmp(n->paths[low + 1].path, path)) return SIZE_MAX;
  return n->paths[low].part;
}
static exr_status push(navigation *n, size_t parent, const char *label, const char *href,
                         const char *base, const char *role, size_t *entry) {
  exr_navigation *v; exr_status status;
  if (n->count >= 10000) return exr_fail(n->error, EXR_LIMIT, "Navigation exceeds 10000 entries");
  if (!exr_grow((void **)&n->entries, &n->capacity, n->count + 1, sizeof(*n->entries)))
    return exr_fail(n->error, EXR_MEMORY, "Navigation allocation failed");
  *entry = n->count++;
  v = &n->entries[*entry]; memset(v, 0, sizeof(*v));
  v->parent = parent; v->part = target_part(n, base, href);
  status = string(n, label, 65536, &v->label);
  if (status == EXR_OK) status = string(n, href, 2046, &v->href);
  if (status == EXR_OK) status = string(n, base, 2046, &v->base);
  if (status == EXR_OK) status = string(n, role, 256, &v->role);
  return status;
}
static int excluded(const char *tag) {
  return !strcmp(tag, "ol") || !strcmp(tag, "ul") || !strcmp(tag, "li") ||
         !strcmp(tag, "navPoint") || !strcmp(tag, "pageTarget") || !strcmp(tag, "navTarget");
}
static size_t find(const exr_document *d, size_t node, const char *tag, unsigned depth) {
  size_t child, result;
  const char *current = name(&d->nodes[node]);
  if (depth > 260 || (depth && excluded(current))) return SIZE_MAX;
  if (!strcmp(current, tag)) return node;
  for (child = d->nodes[node].first_child; child != SIZE_MAX; child = d->nodes[child].next_sibling) {
    result = find(d, child, tag, depth + 1);
    if (result != SIZE_MAX) return result;
  }
  return SIZE_MAX;
}
static exr_status label_text(const exr_document *d, size_t node, exr_buffer *out,
                               int *space, unsigned depth, exr_error *e) {
  const exr_node *v = &d->nodes[node];
  const char *tag = name(v), *s;
  size_t child, i;
  if (depth > 260) return exr_fail(e, EXR_LIMIT, "Navigation nesting exceeds limit");
  if ((depth && excluded(tag)) || !strcmp(tag, "script") || !strcmp(tag, "style") ||
      exr_node_attribute(v, "hidden")) return EXR_OK;
  if (v->kind == EXR_NODE_TEXT)
    for (s = v->text, i = 0; s && s[i]; i++) {
      if (ws((unsigned char)s[i])) { if (out->size) *space = 1; continue; }
      if (out->size + (size_t)*space >= 65536)
        return exr_fail(e, EXR_LIMIT, "Navigation label exceeds 64 KiB");
      if ((*space && !exr_append(out, " ", 1)) || !exr_append(out, s + i, 1))
        return exr_fail(e, EXR_MEMORY, "Navigation label allocation failed");
      *space = 0;
    }
  for (child = v->first_child; child != SIZE_MAX; child = d->nodes[child].next_sibling) {
    exr_status status = label_text(d, child, out, space, depth + 1, e);
    if (status != EXR_OK) return status;
  }
  return EXR_OK;
}
static exr_status item(navigation *n, const exr_document *d, size_t node, size_t parent,
                         const char *base, const char *role, int ncx, size_t *entry) {
  size_t label, link;
  const char *href = NULL, *fallback;
  exr_buffer text = {0}; exr_status status; int space = 0;
  if (ncx) {
    label = find(d, node, "navLabel", 0);
    link = find(d, node, "content", 0);
    if (link != SIZE_MAX) href = exr_node_attribute(&d->nodes[link], "src");
  } else {
    link = find(d, node, "a", 0); label = link;
    if (label == SIZE_MAX) label = find(d, node, "span", 0);
    if (label == SIZE_MAX) label = node;
    if (link != SIZE_MAX) href = exr_node_attribute(&d->nodes[link], "href");
  }
  status = label == SIZE_MAX ? EXR_OK : label_text(d, label, &text, &space, 0, n->error);
  fallback = label == SIZE_MAX ? "" : exr_node_attribute(&d->nodes[label], "aria-label");
  if (status == EXR_OK)
    status = push(n, parent, text.size ? text.data : fallback, href, base, role, entry);
  free(text.data);
  return status;
}
static exr_status walk(navigation *n, const exr_document *d, size_t node, size_t parent,
                         const char *base, const char *role, int ncx, unsigned depth) {
  const char *tag = name(&d->nodes[node]);
  size_t child;
  exr_status status;
  if (depth > 260) return exr_fail(n->error, EXR_LIMIT, "Navigation nesting exceeds limit");
  if (!ncx && depth && !strcmp(tag, "nav")) return EXR_OK;
  if (!(n->visited++ & 255) && exr_control_cancel(n->control, n->error) != EXR_OK)
    return EXR_CANCELLED;
  if (ncx) {
    if (!strcmp(tag, "navMap")) role = "toc";
    else if (!strcmp(tag, "pageList")) role = "page-list";
    else if (!strcmp(tag, "navList")) {
      const char *type=exr_node_attribute(&d->nodes[node],"class");
      role=type && *type ? type : "nav-list";
    }
  }
  if ((!ncx && !strcmp(tag, "li")) || (ncx && (!strcmp(tag, "navPoint") ||
       !strcmp(tag, "pageTarget") || !strcmp(tag, "navTarget")))) {
    status = item(n, d, node, parent, base, role, ncx, &parent);
    if (status != EXR_OK) return status;
  }
  for (child = d->nodes[node].first_child; child != SIZE_MAX; child = d->nodes[child].next_sibling) {
    status = walk(n, d, child, parent, base, role, ncx, depth + 1);
    if (status != EXR_OK) return status;
  }
  return EXR_OK;
}
static exr_status resource(navigation *n, size_t index, int ncx) {
  exr_document *d = NULL;
  exr_status status = exr_xml_resource(n->index, index, ncx ? "ncx" : "html", &d, n->error);
  size_t i;
  const char *base = n->index->resources[index].path;
  if (status != EXR_OK) return status;
  if (ncx) status = walk(n, d, 0, SIZE_MAX, base, "toc", 1, 0);
  else for (i = 0; i < d->node_count && status == EXR_OK; i++) {
    const exr_node *v = &d->nodes[i];
    const char *role;
    if (strcmp(name(v), "nav")) continue;
    role = exr_node_attribute(v, "http://www.idpf.org/2007/ops|type");
    if (!role) {
      role = exr_node_attribute(v, "role");
      if (token(role, "doc-toc")) role = "toc";
      else if (token(role, "doc-pagelist")) role = "page-list";
      else if (!role) role = "toc";
    }
    status = walk(n, d, i, SIZE_MAX, base, role, 0, 0);
  }
  exr_document_free(d);
  return status;
}
exr_status exr_epub_navigation(const exr_document *index, size_t metadata_bytes,
                                exr_navigation **entries, size_t *count, exr_error *e) {
  navigation n = {0}; exr_status status = EXR_OK;
  size_t i, ncx = SIZE_MAX;
  *entries = NULL; *count = 0;
  n.index = index; n.error = e; n.bytes = metadata_bytes;
  if (index->shared_archive) n.control = &index->shared_archive->source.control;
  if (index->chapter_count) {
    n.paths = malloc(index->chapter_count*sizeof(*n.paths));
    if (!n.paths) return exr_fail(e, EXR_MEMORY, "Navigation path allocation failed");
    for (i = 0; i < index->chapter_count; i++)
      n.paths[i] = (nav_path){index->chapters[i].path, i};
    qsort(n.paths, index->chapter_count, sizeof(*n.paths), path_compare);
  }
  for (i = 0; i < index->resource_count && status == EXR_OK; i++) {
    if (token(index->resources[i].properties, "nav")) status = resource(&n, i, 0);
    if (ncx == SIZE_MAX && !strcmp(index->resources[i].media_type, "application/x-dtbncx+xml")) ncx = i;
  }
  if (status == EXR_OK && !n.count) {
    if (index->has_ncx) ncx = index->ncx_resource;
    if (index->has_ncx && ncx == SIZE_MAX)
      status = exr_fail(e, EXR_FORMAT, "Referenced NCX resource is missing");
    else if (ncx != SIZE_MAX) status = resource(&n, ncx, 1);
  }
  free(n.paths);
  if (status != EXR_OK) { exr_navigation_free(n.entries, n.count); return status; }
  *entries = n.entries; *count = n.count;
  return exr_fail(e, EXR_OK, "");
}
exr_status exr_document_navigation(const exr_document *doc,exr_navigation **entries,
                                    size_t *count,exr_error *e) {
  if(entries) *entries=NULL;
  if(count) *count=0;
  if(!doc || !entries || !count) return exr_fail(e,EXR_ARGUMENT,"Missing document or navigation outputs");
  return exr_epub_navigation(doc,0,entries,count,e);
}
