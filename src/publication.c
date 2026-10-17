/* SPDX-License-Identifier: GPL-3.0-only */
#include "layout_internal.h"

struct exr_publication {
  char *title;
  exr_part *parts;
  size_t count, refs;
  exr_part_load_fn load;
  void *context;
  exr_context_release_fn release;
  exr_navigation *navigation;
  size_t navigation_count, metadata_bytes;
  int navigation_ready, busy;
};
typedef struct {
  size_t part, bytes;
  exr_document *document;
  exr_layout *layout;
} cached_part;
struct exr_session {
  exr_publication *publication;
  exr_font *font;
  exr_layout_config config;
  cached_part *cache; /* Most recently used first, at most 64 entries. */
  size_t count, capacity, bytes, budget;
  int busy;
};

static exr_status copy_string(const char *source, size_t limit, size_t *total,
                               const char **out, exr_error *e) {
  size_t n = 0, at = 0;
  uint32_t cp;
  *out = NULL;
  if (!source)
    source = "";
  while (n <= limit && source[n])
    n++;
  if (n > limit || n >= EXR_MAX_TEXT - *total)
    return exr_fail(e, EXR_LIMIT, "Publication metadata or CSS exceeds limit");
  while (at < n)
    if (!exr_next(source, n, &at, &cp))
      return exr_fail(e, EXR_ENCODING, "Publication metadata or CSS is not UTF-8");
  *out = exr_copy(source, n);
  if (!*out)
    return exr_fail(e, EXR_MEMORY, "Publication string allocation failed");
  *total += n + 1;
  return EXR_OK;
}

void exr_publication_free(exr_publication *p) {
  size_t i;
  if (!p || --p->refs)
    return;
  if (p->release)
    p->release(p->context);
  for (i = 0; i < p->count; i++) {
    free((void *)p->parts[i].id);
    free((void *)p->parts[i].path);
    free((void *)p->parts[i].title);
  }
  free(p->parts);
  exr_navigation_free(p->navigation, p->navigation_count);
  free(p->title);
  free(p);
}

exr_status exr_publication_create(const exr_publication_input *input,
                                  exr_publication **out, exr_error *e) {
  exr_publication *p;
  exr_status status;
  const char *title;
  size_t i, total = 0;
  if (!out)
    return exr_fail(e, EXR_ARGUMENT, "Missing publication output");
  *out = NULL;
  if (!input || !input->load || !input->parts || !input->part_count)
    return exr_fail(e, EXR_ARGUMENT, "Missing publication directory or loader");
  if (input->navigation_count && !input->navigation)
    return exr_fail(e, EXR_ARGUMENT, "Missing publication navigation array");
  if (input->navigation_count > 10000)
    return exr_fail(e, EXR_LIMIT, "Navigation exceeds 10000 entries");
  if (input->part_count > 10000)
    return exr_fail(e, EXR_LIMIT, "Publication exceeds 10000 parts");
  p = calloc(1, sizeof(*p));
  if (!p)
    return exr_fail(e, EXR_MEMORY, "Publication allocation failed");
  p->refs = 1;
  p->parts = calloc(input->part_count, sizeof(*p->parts));
  if (!p->parts) {
    exr_publication_free(p);
    return exr_fail(e, EXR_MEMORY, "Publication directory allocation failed");
  }
  p->count = input->part_count;
  status = copy_string(input->title, 65536, &total, &title, e);
  p->title = (char *)title;
  for (i = 0; status == EXR_OK && i < p->count; i++) {
    exr_part *part = &p->parts[i];
    const exr_part *source = &input->parts[i];
    status = copy_string(source->id, 65536, &total, &part->id, e);
    if (status == EXR_OK)
      status = copy_string(source->path, 2046, &total, &part->path, e);
    if (status == EXR_OK)
      status = copy_string(source->title, 65536, &total, &part->title, e);
    part->in_reading_order = source->in_reading_order != 0;
  }
  if (status == EXR_OK && input->navigation_count) {
    p->navigation = calloc(input->navigation_count, sizeof(*p->navigation));
    if (!p->navigation) status = exr_fail(e, EXR_MEMORY, "Navigation allocation failed");
    else p->navigation_count = input->navigation_count;
  }
  for (i = 0; status == EXR_OK && i < p->navigation_count; i++) {
    const exr_navigation *source = &input->navigation[i];
    exr_navigation *v = &p->navigation[i];
    if ((source->parent != SIZE_MAX && source->parent >= i) ||
        (source->part != SIZE_MAX && source->part >= p->count)) {
      status = exr_fail(e, EXR_ARGUMENT, "Invalid navigation parent or part");
      break;
    }
    v->parent = source->parent; v->part = source->part;
    status = copy_string(source->label, 65536, &total, &v->label, e);
    if (status == EXR_OK) status = copy_string(source->href, 2046, &total, &v->href, e);
    if (status == EXR_OK) status = copy_string(source->base, 2046, &total, &v->base, e);
    if (status == EXR_OK) status = copy_string(source->role, 256, &total, &v->role, e);
  }
  if (status != EXR_OK) {
    exr_publication_free(p);
    return status;
  }
  p->load = input->load;
  p->context = input->context;
  p->release = input->release;
  p->metadata_bytes = total;
  p->navigation_ready = 1;
  *out = p;
  return exr_fail(e, EXR_OK, "");
}

static exr_status epub_load(void *context, size_t part, exr_document **out, exr_error *e) {
  return exr_epub_load(context, part, out, e);
}
static void epub_release(void *context) { exr_document_free(context); }

static exr_status publication_index(exr_document *index, exr_publication **out, exr_error *e) {
  exr_part *parts;
  exr_publication_input input = {0};
  exr_status status;
  size_t i;
  parts = calloc(index->chapter_count, sizeof(*parts));
  if (!parts) {
    exr_document_free(index);
    return exr_fail(e, EXR_MEMORY, "Publication directory allocation failed");
  }
  for (i = 0; i < index->chapter_count; i++) {
    parts[i].id = index->chapters[i].id;
    parts[i].path = index->chapters[i].path;
    parts[i].in_reading_order = index->chapters[i].in_spine && index->chapters[i].linear;
  }
  input.title = exr_document_title(index);
  input.parts = parts;
  input.part_count = index->chapter_count;
  input.load = epub_load;
  input.context = index;
  input.release = epub_release;
  status = exr_publication_create(&input, out, e);
  if (status == EXR_OK) (*out)->navigation_ready = 0;
  free(parts);
  if (status != EXR_OK)
    exr_document_free(index);
  return status;
}
exr_status exr_publication_open_memory(exr_format format, const void *data, size_t size,
                                       exr_publication **out, exr_error *e) {
  exr_document *index = NULL;
  exr_status status;
  if (!out) return exr_fail(e, EXR_ARGUMENT, "Missing publication output");
  *out = NULL;
  if (format != EXR_EPUB)
    return exr_fail(e, EXR_FORMAT, "Built-in indexed loading currently accepts EPUB");
  status = exr_epub_index(data, size, &index, e);
  return status == EXR_OK ? publication_index(index, out, e) : status;
}
exr_status exr_publication_open_source(const exr_source *source, exr_publication **out, exr_error *e) {
  exr_document *index = NULL;
  exr_status status;
  if (!out) return exr_fail(e, EXR_ARGUMENT, "Missing publication output");
  *out = NULL;
  status = exr_epub_index_source(source, &index, e);
  if (status != EXR_OK) return status;
  status = publication_index(index, out, e);
  if (status == EXR_OK) index->shared_archive->source.release = source->release;
  return status;
}

exr_status exr_publication_open(const char *path, exr_publication **out, exr_error *e) {
  exr_source source = {0};
  exr_status status;
  if (!out)
    return exr_fail(e, EXR_ARGUMENT, "Missing publication output");
  *out = NULL;
  if (!path)
    return exr_fail(e, EXR_ARGUMENT, "Missing publication path");
  status = exr_file_source(path, &source, e);
  if (status != EXR_OK) return status;
  status = exr_publication_open_source(&source, out, e);
  if (status != EXR_OK) source.release(source.context);
  return status;
}
const char *exr_publication_title(const exr_publication *p) { return p ? p->title : ""; }
const exr_part *exr_publication_parts(const exr_publication *p, size_t *count) {
  if (count)
    *count = p ? p->count : 0;
  return p ? p->parts : NULL;
}
exr_status exr_publication_navigation(exr_publication *p, const exr_navigation **out,
                                       size_t *count, exr_error *e) {
  exr_status status;
  if (out) *out = NULL;
  if (count) *count = 0;
  if (!p || !out || !count || p->busy)
    return exr_fail(e, EXR_ARGUMENT, "Invalid or reentrant navigation request");
  if (!p->navigation_ready) {
    exr_navigation *entries = NULL;
    size_t n = 0;
    p->busy = 1;
    status = exr_epub_navigation(p->context, p->metadata_bytes, &entries, &n, e);
    p->busy = 0;
    if (status != EXR_OK) return status;
    p->navigation = entries; p->navigation_count = n; p->navigation_ready = 1;
  }
  *out = p->navigation; *count = p->navigation_count;
  return exr_fail(e, EXR_OK, "");
}
exr_status exr_publication_load(exr_publication *p, size_t part, exr_document **out, exr_error *e) {
  exr_document *doc = NULL;
  exr_status status;
  if (!out)
    return exr_fail(e, EXR_ARGUMENT, "Missing part document output");
  *out = NULL;
  if (!p || part >= p->count || p->busy)
    return exr_fail(e, EXR_ARGUMENT, "Part is outside the publication");
  p->busy = 1;
  status = p->load(p->context, part, &doc, e);
  if (status == EXR_OK && !doc)
    status = exr_fail(e, EXR_FORMAT, "Part loader returned no document");
  if (status != EXR_OK) {
    exr_document_free(doc);
    p->busy = 0;
    return status;
  }
  p->busy = 0;
  *out = doc;
  return exr_fail(e, EXR_OK, "");
}

void exr_session_clear(exr_session *s) {
  size_t i;
  if (!s)
    return;
  for (i = 0; i < s->count; i++) {
    exr_layout_free(s->cache[i].layout);
    exr_document_free(s->cache[i].document);
  }
  s->count = 0;
  s->bytes = 0;
}
void exr_session_free(exr_session *s) {
  if (!s)
    return;
  exr_session_clear(s);
  free(s->cache);
  free((void *)s->config.user_css);
  exr_publication_free(s->publication);
  free(s);
}
size_t exr_session_cached(const exr_session *s) { return s ? s->count : 0; }
size_t exr_session_cached_bytes(const exr_session *s) { return s ? s->bytes : 0; }

static void evict_last(exr_session *s) {
  cached_part *entry = &s->cache[--s->count];
  s->bytes -= entry->bytes;
  exr_layout_free(entry->layout);
  exr_document_free(entry->document);
}
exr_status exr_session_set_budget(exr_session *s, size_t bytes, exr_error *e) {
  if (!s || s->busy)
    return exr_fail(e, EXR_ARGUMENT, "Invalid or reentrant session access");
  s->budget = bytes;
  while (s->budget && s->bytes > s->budget)
    evict_last(s);
  return exr_fail(e, EXR_OK, "");
}

exr_status exr_session_create(exr_publication *p, exr_font *font,
                              const exr_layout_config *config, size_t capacity,
                              exr_session **out, exr_error *e) {
  exr_layout_config defaults = exr_layout_config_defaults();
  exr_status status;
  exr_session *s;
  size_t total = 0;
  if (!out)
    return exr_fail(e, EXR_ARGUMENT, "Missing session output");
  *out = NULL;
  if (!p || !font || !capacity || capacity > 64)
    return exr_fail(e, EXR_ARGUMENT, "Session requires a publication, font and capacity 1..64");
  if (!config)
    config = &defaults;
  status = exr_layout_validate(config, e);
  if (status != EXR_OK)
    return status;
  if (p->refs == SIZE_MAX)
    return exr_fail(e, EXR_LIMIT, "Too many publication references");
  s = calloc(1, sizeof(*s));
  if (!s)
    return exr_fail(e, EXR_MEMORY, "Session allocation failed");
  s->config = *config;
  s->config.user_css = NULL;
  if (config->user_css) {
    status = copy_string(config->user_css, 1024 * 1024, &total, &s->config.user_css, e);
    if (status != EXR_OK) {
      exr_session_free(s);
      return status;
    }
  }
  s->cache = calloc(capacity, sizeof(*s->cache));
  if (!s->cache) {
    exr_session_free(s);
    return exr_fail(e, EXR_MEMORY, "Session cache allocation failed");
  }
  s->capacity = capacity;
  s->font = font;
  s->publication = p;
  p->refs++;
  *out = s;
  return exr_fail(e, EXR_OK, "");
}

exr_status exr_session_get(exr_session *s, size_t part, const exr_document **document,
                           const exr_layout **layout, exr_error *e) {
  cached_part entry = {0};
  exr_status status;
  size_t i, document_bytes, layout_bytes;
  if (document)
    *document = NULL;
  if (layout)
    *layout = NULL;
  if (!s || !document || !layout || part >= s->publication->count || s->busy)
    return exr_fail(e, EXR_ARGUMENT, "Invalid or reentrant session access");
  for (i = 0; i < s->count; i++)
    if (s->cache[i].part == part) {
      entry = s->cache[i];
      memmove(s->cache + 1, s->cache, i * sizeof(*s->cache));
      s->cache[0] = entry;
      *document = entry.document;
      *layout = entry.layout;
      return exr_fail(e, EXR_OK, "");
    }
  s->busy = 1;
  status = exr_publication_load(s->publication, part, &entry.document, e);
  if (status == EXR_OK)
    status = exr_layout_create_ex(entry.document, s->font, &s->config, &entry.layout, e);
  s->busy = 0;
  if (status != EXR_OK) {
    exr_document_free(entry.document);
    exr_layout_free(entry.layout);
    return status;
  }
  document_bytes = exr_document_memory_size(entry.document);
  layout_bytes = exr_layout_memory_size(entry.layout);
  if (document_bytes == SIZE_MAX || layout_bytes >= SIZE_MAX - document_bytes ||
      (s->budget && (document_bytes > s->budget || layout_bytes > s->budget - document_bytes))) {
    exr_document_free(entry.document);
    exr_layout_free(entry.layout);
    return exr_fail(e, EXR_LIMIT, "Part exceeds the session cache byte budget");
  }
  entry.bytes = document_bytes + layout_bytes;
  /* Finish loading and measuring before changing the resident cache. Failures
     leave all previous borrowed pointers and their LRU order intact. */
  while (s->count && (s->count == s->capacity || entry.bytes > SIZE_MAX - s->bytes ||
                      (s->budget && entry.bytes > s->budget - s->bytes)))
    evict_last(s);
  s->count++;
  memmove(s->cache + 1, s->cache, (s->count - 1) * sizeof(*s->cache));
  entry.part = part;
  s->cache[0] = entry;
  s->bytes += entry.bytes;
  *document = entry.document;
  *layout = entry.layout;
  return exr_fail(e, EXR_OK, "");
}
