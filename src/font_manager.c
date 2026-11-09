/* SPDX-License-Identifier: MIT */
/* Font manager: index assembly, cache reuse, fallback chain, pick and
   chain-ordered exr_font creation. Immutable after create(). */
#include "font_manager_internal.h"
#include "font_internal.h"
#include <ctype.h>

static int font_extension(const char *path) {
  const char *dot = strrchr(path, '.');
  char ext[5] = {0};
  size_t i;
  if (!dot || strlen(dot) != 4 || strchr(dot, '/') || strchr(dot, '\\')) return 0;
  for (i = 0; i < 4; i++) ext[i] = (char)tolower((unsigned char)dot[i]);
  return !strcmp(ext, ".ttf") || !strcmp(ext, ".otf") || !strcmp(ext, ".ttc") || !strcmp(ext, ".otc");
}
static char *copy(const char *s) { return s ? exr_copy(s, strlen(s)) : NULL; }
static void files_free(exr_fm_files *files) {
  size_t i;
  for (i = 0; i < files->count; i++) exr_fm_file_clear(&files->items[i]);
  free(files->items);
  memset(files, 0, sizeof(*files));
}
void exr_font_manager_free(exr_font_manager *m) {
  size_t i;
  if (!m) return;
  files_free(&m->files);
  free(m->faces);
  for (i = 0; i < m->skip_count; i++) { free(m->skips[i].path); free(m->skips[i].detail); }
  free(m->skips);
  for (i = 0; i < m->fallback_count; i++) free(m->fallback[i]);
  free(m->fallback);
  free(m->serif); free(m->sans);
  free(m);
}
static int add_skip(exr_font_manager *m, const char *path, unsigned reason, const char *detail) {
  exr_fm_skip *s;
  if (!exr_grow((void **)&m->skips, &m->skip_capacity, m->skip_count + 1, sizeof(*m->skips))) return 0;
  s = &m->skips[m->skip_count];
  s->path = copy(path); s->detail = copy(detail ? detail : ""); s->reason = reason;
  if (!s->path || !s->detail) { free(s->path); free(s->detail); return 0; }
  m->skip_count++;
  return 1;
}
typedef struct { exr_fm_entry entry; size_t location, order; } pending;
static int compare_pending(const void *a, const void *b) {
  const pending *x = a, *y = b;
  int c = strcmp(x->entry.path, y->entry.path);
  return c ? c : (x->order < y->order ? -1 : x->order > y->order);
}
static int compare_order(const void *a, const void *b) {
  const pending *x = a, *y = b;
  return x->order < y->order ? -1 : x->order > y->order;
}
static int compare_files(const void *a, const void *b) {
  return strcmp(((const exr_fm_file *)a)->path, ((const exr_fm_file *)b)->path);
}
static int compare_names(const void *a, const void *b) {
  const char *x = *(const char *const *)a, *y = *(const char *const *)b;
  for (; *x && tolower((unsigned char)*x) == tolower((unsigned char)*y); x++, y++) {}
  return tolower((unsigned char)*x) - tolower((unsigned char)*y);
}
static exr_status collect(exr_font_manager *m, const exr_font_location *location, size_t index,
                          pending **items, size_t *count, size_t *capacity, exr_error *e) {
  uint64_t size = 0;
  int64_t mtime = 0;
  int kind = exr_fm_stat(location->path, &size, &mtime);
  int want = location->kind == EXR_FONT_LOCATION_FILE ? 2 : 1;
  exr_fm_entry *entries = NULL;
  size_t n = 0, i;
  exr_status status;
  if (kind != want) {
    const char *what = want == 2 ? "Font file" : "Font directory";
    const char *why = kind == 0 ? "not found" : kind < 0 ? "unreadable" : want == 2 ? "is a directory" : "is not a directory";
    char detail[64];
    if (!(location->flags & EXR_FONT_LOCATION_OPTIONAL))
      return exr_fail(e, EXR_IO, "%s %s: %s", what, why, location->path);
    snprintf(detail, sizeof(detail), "optional %s %s", want == 2 ? "font file" : "font directory", why);
    return add_skip(m, location->path, EXR_FONT_SKIP_MISSING, detail) ? EXR_OK :
           exr_fail(e, EXR_MEMORY, "Font index allocation failed");
  }
  if (want == 2) {
    char *path = copy(location->path);
    if (!path) return exr_fail(e, EXR_MEMORY, "Font index allocation failed");
    entries = malloc(sizeof(*entries));
    if (!entries) { free(path); return exr_fail(e, EXR_MEMORY, "Font index allocation failed"); }
    entries[0] = (exr_fm_entry){path, size, mtime};
    n = 1;
  } else if ((status = exr_fm_list(location->path, &entries, &n, e)) != EXR_OK) {
    if (status == EXR_IO && (location->flags & EXR_FONT_LOCATION_OPTIONAL))
      return add_skip(m, location->path, EXR_FONT_SKIP_IO, "cannot read optional font directory") ? EXR_OK :
             exr_fail(e, EXR_MEMORY, "Font index allocation failed");
    return status;
  }
  if (*count + n > EXR_FM_MAX_FILES) {
    exr_fm_entries_free(entries, n);
    return exr_fail(e, EXR_LIMIT, "Font locations exceed %u files", (unsigned)EXR_FM_MAX_FILES);
  }
  if (!exr_grow((void **)items, capacity, *count + n, sizeof(**items))) {
    exr_fm_entries_free(entries, n);
    return exr_fail(e, EXR_MEMORY, "Font index allocation failed");
  }
  for (i = 0; i < n; i++) {
    (*items)[*count] = (pending){entries[i], index, *count};
    (*count)++;
  }
  free(entries); /* Paths moved into items. */
  return EXR_OK;
}
static exr_status finish(exr_font_manager *m, exr_error *e) {
  size_t i, j, n = 0;
  const char **names;
  for (i = 0; i < m->files.count; i++) {
    exr_fm_file *f = &m->files.items[i];
    if (f->skip && !add_skip(m, f->path, f->skip, f->detail)) return exr_fail(e, EXR_MEMORY, "Font index allocation failed");
    if (f->face_count) m->summary.files++;
    n += f->face_count;
  }
  if (n > EXR_FM_MAX_FACES) return exr_fail(e, EXR_LIMIT, "Font index exceeds 65536 faces");
  if (!n) return exr_fail(e, EXR_FONT, "No usable Unicode font face in the configured font locations");
  if (!(m->faces = malloc(n * sizeof(*m->faces))) || !(names = malloc(n * sizeof(*names))))
    return exr_fail(e, EXR_MEMORY, "Font index allocation failed");
  for (i = 0; i < m->files.count; i++)
    for (j = 0; j < m->files.items[i].face_count; j++) {
      names[m->face_count] = m->files.items[i].faces[j].family;
      m->faces[m->face_count++] = (exr_fm_ref){i, j};
    }
  qsort(names, n, sizeof(*names), compare_names);
  for (i = 0; i < n; i++) if (!i || compare_names(&names[i - 1], &names[i])) m->summary.families++;
  free((void *)names);
  m->summary.faces = n;
  m->summary.skipped = m->skip_count;
  return EXR_OK;
}
exr_status exr_font_manager_create(const exr_font_manager_options *o, exr_font_manager **out, exr_error *e) {
  double start = exr_fm_now_ms();
  exr_font_manager *m;
  exr_fm_files cached = {0};
  pending *items = NULL;
  size_t count = 0, capacity = 0, i, kept, used_cache = 0, cache_fonts = 0, indexed_faces = 0;
  char *platform[8] = {0};
  size_t platform_count = 0;
  int cache_valid = 0;
  FT_Library library = NULL;
  exr_status status = EXR_OK;
  if (!out) return exr_fail(e, EXR_ARGUMENT, "Missing font manager output");
  *out = NULL;
  if (!o || o->struct_size < sizeof(*o) || (o->location_count && !o->locations) ||
      (o->fallback_count && !o->fallback_families) || (o->flags & ~(unsigned)EXR_FONT_MANAGER_PLATFORM_DIRECTORIES))
    return exr_fail(e, EXR_ARGUMENT, "Invalid font manager options");
  for (i = 0; i < o->location_count; i++)
    if (!o->locations[i].path || !*o->locations[i].path || o->locations[i].kind > EXR_FONT_LOCATION_FILE ||
        (o->locations[i].flags & ~(unsigned)EXR_FONT_LOCATION_OPTIONAL))
      return exr_fail(e, EXR_ARGUMENT, "Invalid font location %u", (unsigned)i);
  for (i = 0; i < o->fallback_count; i++)
    if (!o->fallback_families[i] || !*o->fallback_families[i])
      return exr_fail(e, EXR_ARGUMENT, "Invalid fallback family %u", (unsigned)i);
  if (!(o->flags & EXR_FONT_MANAGER_PLATFORM_DIRECTORIES) && !o->location_count)
    return exr_fail(e, EXR_ARGUMENT, "Font manager needs at least one location");
  if (!(m = EXR_NEW(exr_font_manager))) return exr_fail(e, EXR_MEMORY, "Font manager allocation failed");
  m->summary.struct_size = sizeof(m->summary);
  m->serif = copy(o->serif_families ? o->serif_families : exr_fm_default_serif());
  m->sans = copy(o->sans_serif_families ? o->sans_serif_families : exr_fm_default_sans());
  if (o->fallback_count && !(m->fallback = calloc(o->fallback_count, sizeof(*m->fallback)))) goto memory;
  for (i = 0; i < o->fallback_count; i++) {
    if (!(m->fallback[i] = copy(o->fallback_families[i]))) goto memory;
    m->fallback_count++;
  }
  if (!m->serif || !m->sans) goto memory;
  /* 1. Discovery: list every location in order, then de-duplicate paths. */
  for (i = 0; i < o->location_count && status == EXR_OK; i++)
    status = collect(m, &o->locations[i], i, &items, &count, &capacity, e);
  if (status == EXR_OK && (o->flags & EXR_FONT_MANAGER_PLATFORM_DIRECTORIES)) {
    platform_count = exr_fm_platform_directories(platform);
    for (i = 0; i < platform_count && status == EXR_OK; i++) {
      exr_font_location location = {platform[i], EXR_FONT_LOCATION_DIRECTORY, EXR_FONT_LOCATION_OPTIONAL};
      status = collect(m, &location, o->location_count + i, &items, &count, &capacity, e);
    }
  }
  if (status != EXR_OK) goto fail;
  if (count) qsort(items, count, sizeof(*items), compare_pending);
  for (i = kept = 0; i < count; i++) {
    if (kept && !strcmp(items[kept - 1].entry.path, items[i].entry.path)) { free(items[i].entry.path); continue; }
    items[kept++] = items[i];
  }
  count = kept;
  if (count) qsort(items, count, sizeof(*items), compare_order);
  /* 2. Index: restore unchanged files from the cache, parse the rest. */
  if (o->cache_path) {
    cache_valid = exr_fm_cache_read(o->cache_path, &cached) == EXR_OK;
    if (cached.count) qsort(cached.items, cached.count, sizeof(*cached.items), compare_files);
  }
  if (count && !(m->files.items = calloc(count, sizeof(*m->files.items)))) goto memory;
  m->files.capacity = count;
  for (i = 0; i < count; i++) {
    exr_fm_file *file = &m->files.items[m->files.count++];
    exr_fm_file key, *hit;
    file->path = items[i].entry.path; items[i].entry.path = NULL;
    file->size = items[i].entry.size; file->mtime = items[i].entry.mtime;
    file->location = items[i].location;
    if (!font_extension(file->path)) {
      file->skip = EXR_FONT_SKIP_NOT_FONT;
      if (!(file->detail = copy("not a .ttf/.otf/.ttc/.otc file"))) goto memory;
      continue;
    }
    cache_fonts++;
    key.path = file->path;
    hit = cached.count ? bsearch(&key, cached.items, cached.count, sizeof(*cached.items), compare_files) : NULL;
    if (hit && hit->path && hit->size == file->size && hit->mtime == file->mtime) {
      file->skip = hit->skip; file->detail = hit->detail; file->faces = hit->faces; file->face_count = hit->face_count;
      hit->detail = NULL; hit->faces = NULL; hit->face_count = 0;
      m->summary.cached_files++;
      used_cache++;
    } else {
      if (!library && FT_Init_FreeType(&library)) { status = exr_fail(e, EXR_FONT, "FreeType initialization failed"); goto fail; }
      if ((status = exr_fm_parse(library, file, e)) != EXR_OK) goto fail;
      m->summary.parsed_files++;
    }
    if (file->face_count > EXR_FM_MAX_FACES - indexed_faces) {
      status = exr_fail(e, EXR_LIMIT, "Font index exceeds 65536 faces"); goto fail;
    }
    indexed_faces += file->face_count;
  }
  if ((status = finish(m, e)) != EXR_OK) goto fail;
  /* 3. Persist only when the index differs from what the cache described. */
  m->summary.cache_write_status = EXR_OK;
  if (o->cache_path) {
    m->summary.cache = !cache_valid || !used_cache ? EXR_FONT_CACHE_MISS :
                       m->summary.parsed_files ? EXR_FONT_CACHE_PARTIAL : EXR_FONT_CACHE_HIT;
    if (!cache_valid || m->summary.parsed_files || used_cache != cached.count || cache_fonts != used_cache) {
      exr_error ignored;
      m->summary.cache_write_status = exr_fm_cache_write(o->cache_path, &m->files, &ignored);
      m->summary.cache_written = m->summary.cache_write_status == EXR_OK;
    }
  }
  goto done;
memory:
  status = exr_fail(e, EXR_MEMORY, "Font manager allocation failed");
fail:
  exr_font_manager_free(m);
  m = NULL;
done:
  if (library) FT_Done_FreeType(library);
  for (i = 0; i < count; i++) free(items[i].entry.path);
  free(items);
  files_free(&cached);
  for (i = 0; i < platform_count; i++) free(platform[i]);
  if (m) {
    m->summary.elapsed_ms = exr_fm_now_ms() - start;
    *out = m;
    return exr_fail(e, EXR_OK, "");
  }
  return status;
}

/* Configuration file. */
static char *trim(char *s) {
  char *end;
  while (*s == ' ' || *s == '\t') s++;
  end = s + strlen(s);
  while (end > s && (end[-1] == ' ' || end[-1] == '\t' || end[-1] == '\r')) *--end = 0;
  return s;
}
typedef struct { char **items; size_t count, capacity; } strings;
static int push(strings *list, char *s) {
  if (!s || !exr_grow((void **)&list->items, &list->capacity, list->count + 1, sizeof(*list->items))) { free(s); return 0; }
  list->items[list->count++] = s;
  return 1;
}
static char *resolve(const char *base, size_t base_size, const char *path) {
  char *dir, *out;
  if (exr_fm_absolute(path) || !base_size) return copy(path);
  if (!(dir = exr_copy(base, base_size))) return NULL;
  out = exr_fm_join(dir, path);
  free(dir);
  return out;
}
exr_status exr_font_manager_open(const char *config, exr_font_manager **out, exr_error *e) {
  unsigned char *data = NULL;
  size_t size = 0, base = 0, i, line_number = 0;
  char *line, *next, *serif = NULL, *sans = NULL, *cache = NULL;
  strings paths = {0}, families = {0};
  exr_font_location *locations = NULL;
  size_t location_capacity = 0, location_count = 0;
  unsigned flags = 0;
  int version = 0;
  exr_status status;
  if (!out) return exr_fail(e, EXR_ARGUMENT, "Missing font manager output");
  *out = NULL;
  if (!config) return exr_fail(e, EXR_ARGUMENT, "Missing font configuration path");
  if ((status = exr_read(config, &data, &size, e)) != EXR_OK)
    return exr_fail(e, status, "Cannot read font configuration: %s", config);
  for (i = 0; config[i]; i++) if (config[i] == '/' || config[i] == '\\') base = i + 1;
  line = (char *)data;
  if (size >= 3 && !memcmp(line, "\xEF\xBB\xBF", 3)) line += 3;
  if (memchr(data, 0, size)) { status = exr_fail(e, EXR_FORMAT, "Font configuration contains NUL"); goto done; }
  for (; line; line = next) {
    char *key, *value, *eq;
    next = strchr(line, '\n');
    if (next) *next++ = 0;
    line_number++;
    line = trim(line);
    if (!*line || *line == '#') continue;
    if (!(eq = strchr(line, '='))) { status = exr_fail(e, EXR_FORMAT, "Font configuration line %u: expected key = value", (unsigned)line_number); goto done; }
    *eq = 0;
    key = trim(line); value = trim(eq + 1);
    if (!version) {
      if (strcmp(key, "version") || strcmp(value, "1")) { status = exr_fail(e, EXR_FORMAT, "Font configuration line %u: first key must be version = 1", (unsigned)line_number); goto done; }
      version = 1;
      continue;
    }
    if (!*value) { status = exr_fail(e, EXR_FORMAT, "Font configuration line %u: empty value for %s", (unsigned)line_number, key); goto done; }
    if (!strcmp(key, "font_dir") || !strcmp(key, "font_dir?") || !strcmp(key, "font_file") || !strcmp(key, "font_file?")) {
      if (!push(&paths, resolve(config, base, value)) ||
          !exr_grow((void **)&locations, &location_capacity, location_count + 1, sizeof(*locations))) goto memory;
      locations[location_count].path = NULL;
      locations[location_count].kind = !strncmp(key, "font_file", 9) ? EXR_FONT_LOCATION_FILE : EXR_FONT_LOCATION_DIRECTORY;
      locations[location_count++].flags = key[strlen(key) - 1] == '?' ? EXR_FONT_LOCATION_OPTIONAL : 0u;
    } else if (!strcmp(key, "fallback")) {
      if (!push(&families, copy(value))) goto memory;
    } else if (!strcmp(key, "serif") || !strcmp(key, "sans_serif") || !strcmp(key, "cache")) {
      char **slot = key[0] == 'c' ? &cache : key[1] == 'e' ? &serif : &sans;
      free(*slot);
      if (!(*slot = key[0] == 'c' ? resolve(config, base, value) : copy(value))) goto memory;
    } else if (!strcmp(key, "platform_dirs")) {
      if (!strcmp(value, "yes")) flags |= EXR_FONT_MANAGER_PLATFORM_DIRECTORIES;
      else if (!strcmp(value, "no")) flags &= ~(unsigned)EXR_FONT_MANAGER_PLATFORM_DIRECTORIES;
      else { status = exr_fail(e, EXR_FORMAT, "Font configuration line %u: platform_dirs must be yes or no", (unsigned)line_number); goto done; }
    } else { status = exr_fail(e, EXR_FORMAT, "Font configuration line %u: unknown key %s", (unsigned)line_number, key); goto done; }
  }
  if (!version) { status = exr_fail(e, EXR_FORMAT, "Font configuration has no version"); goto done; }
  for (i = 0; i < location_count; i++) locations[i].path = paths.items[i];
  {
    exr_font_manager_options options;
    memset(&options, 0, sizeof(options));
    options.struct_size = sizeof(options);
    options.locations = locations; options.location_count = location_count;
    options.fallback_families = (const char *const *)families.items; options.fallback_count = families.count;
    options.serif_families = serif; options.sans_serif_families = sans;
    options.cache_path = cache; options.flags = flags;
    status = exr_font_manager_create(&options, out, e);
  }
  goto done;
memory:
  status = exr_fail(e, EXR_MEMORY, "Font configuration allocation failed");
done:
  for (i = 0; i < paths.count; i++) free(paths.items[i]);
  for (i = 0; i < families.count; i++) free(families.items[i]);
  free(paths.items); free(families.items); free(locations);
  free(serif); free(sans); free(cache); free(data);
  return status;
}

/* Queries. */
exr_status exr_font_manager_summary_get(const exr_font_manager *m, exr_font_manager_summary *out, exr_error *e) {
  if (!m || !out || out->struct_size < sizeof(*out)) return exr_fail(e, EXR_ARGUMENT, "Invalid font manager summary request");
  *out = m->summary;
  return exr_fail(e, EXR_OK, "");
}
int exr_font_manager_skip(const exr_font_manager *m, size_t index, exr_font_skip *out) {
  if (!m || !out || index >= m->skip_count) return 0;
  out->path = m->skips[index].path; out->reason = m->skips[index].reason; out->detail = m->skips[index].detail;
  return 1;
}
size_t exr_font_manager_face_count(const exr_font_manager *m) { return m ? m->face_count : 0; }
static const exr_fm_face *face_at(const exr_font_manager *m, size_t index) {
  return &m->files.items[m->faces[index].file].faces[m->faces[index].face];
}
exr_status exr_font_manager_face(const exr_font_manager *m, size_t index, exr_font_face_info *out, exr_error *e) {
  const exr_fm_face *f;
  const exr_fm_file *file;
  if (!m || !out || out->struct_size < sizeof(*out) || index >= m->face_count)
    return exr_fail(e, EXR_ARGUMENT, "Invalid font manager face request");
  f = face_at(m, index);
  file = &m->files.items[m->faces[index].file];
  out->family = f->family; out->style_name = f->style_name; out->path = file->path;
  out->face_index = f->face_index; out->style = f->style; out->weight = f->weight; out->scripts = f->scripts;
  out->location = file->location; out->codepoints = f->codepoints;
  return exr_fail(e, EXR_OK, "");
}
static int covers(const exr_fm_face *f, uint32_t cp) {
  size_t lo = 0, hi = f->range_count;
  while (lo < hi) {
    size_t mid = lo + (hi - lo) / 2;
    if (cp < f->ranges[2 * mid]) hi = mid;
    else if (cp > f->ranges[2 * mid + 1]) lo = mid + 1;
    else return 1;
  }
  return 0;
}
int exr_font_manager_face_covers(const exr_font_manager *m, size_t index, uint32_t cp) {
  return m && index < m->face_count && cp <= 0x10ffff && !(cp >= 0xd800 && cp <= 0xdfff) && covers(face_at(m, index), cp);
}
static int named(const exr_fm_face *f, const char *family) {
  const char *s = f->aliases;
  size_t n = strlen(family);
  if (exr_family_equal(family, f->family)) return 1;
  while (s && *s) {
    const char *end = strchr(s, '\n');
    size_t len = end ? (size_t)(end - s) : strlen(s);
    if (len == n) {
      size_t i;
      for (i = 0; i < n && tolower((unsigned char)s[i]) == tolower((unsigned char)family[i]); i++) {}
      if (i == n) return 1;
    }
    s = end ? end + 1 : NULL;
  }
  return 0;
}
int exr_font_manager_has_family(const exr_font_manager *m, const char *family) {
  size_t i;
  if (!m || !family || !*family) return 0;
  for (i = 0; i < m->face_count; i++) if (named(face_at(m, i), family)) return 1;
  return 0;
}

/* Fallback chain: the single ordering used by pick() and create_font(). */
typedef struct {
  exr_font_chain_link links[EXR_FONT_CHAIN_MAX];
  size_t count, bytes;
  uint32_t covered[0x110000 / 32];
} chain;
/* Count/merge actual indexed scalars, not just script flags. Removing a face
   that contributes nothing preserves every scalar's first matching face and
   leaves the bounded engine chain room for other writing systems. */
static size_t contribution(const exr_fm_face *f, chain *c, int merge) {
  size_t r, count = 0;
  for (r = 0; r < f->range_count; r++) {
    uint32_t start = f->ranges[2 * r], end = f->ranges[2 * r + 1], word;
    for (word = start / 32; word <= end / 32; word++) {
      uint32_t mask = UINT32_MAX, bits;
      if (word == start / 32) mask &= UINT32_MAX << (start % 32);
      if (word == end / 32) mask &= UINT32_MAX >> (31 - end % 32);
      bits = mask & ~c->covered[word];
      /* Portable population count (also used by MSVC builds). */
      bits -= (bits >> 1) & UINT32_C(0x55555555);
      bits = (bits & UINT32_C(0x33333333)) + ((bits >> 2) & UINT32_C(0x33333333));
      bits = (bits + (bits >> 4)) & UINT32_C(0x0f0f0f0f);
      count += (bits * UINT32_C(0x01010101)) >> 24;
      if (merge) c->covered[word] |= mask;
    }
  }
  return count;
}
static void append(const exr_font_manager *m, size_t face, unsigned step, chain *c) {
  c->links[c->count++] = (exr_font_chain_link){face, step};
  c->bytes += (size_t)m->files.items[m->faces[face].file].size;
  contribution(face_at(m, face), c, 1);
}
static unsigned long distance(const exr_fm_face *f, unsigned style) {
  unsigned target = (style & EXR_FONT_STYLE_BOLD) ? 700u : 400u;
  return (((f->style ^ style) & EXR_FONT_STYLE_ITALIC) ? 1000000ul : 0ul) +
         (((f->style ^ style) & EXR_FONT_STYLE_BOLD) ? 10000ul : 0ul) +
         (unsigned long)(f->weight > target ? f->weight - target : target - f->weight);
}
static int listed(const chain *c, size_t face) {
  size_t i;
  for (i = 0; i < c->count; i++) if (c->links[i].face == face) return 1;
  return 0;
}
static void add_family(const exr_font_manager *m, const char *family, unsigned style, unsigned step,
                       int all_styles, chain *c) {
  size_t i;
  unsigned styles_seen = 0;
  for (i = 0; i < c->count; i++) {
    const exr_fm_face *f = face_at(m, c->links[i].face);
    if (named(f, family)) styles_seen |= 1u << f->style;
  }
  for (;;) {
    size_t best = SIZE_MAX;
    unsigned long best_distance = 0;
    if (c->count >= EXR_FONT_CHAIN_MAX) return;
    for (i = 0; i < m->face_count; i++) {
      const exr_fm_face *f = face_at(m, i);
      unsigned long d;
      if (listed(c, i) || !named(f, family) || (styles_seen & (1u << f->style))) continue;
      d = distance(f, style);
      if (best == SIZE_MAX || d < best_distance) { best = i; best_distance = d; }
    }
    if (best == SIZE_MAX) return;
    if (!c->count || contribution(face_at(m, best), c, 0)) append(m, best, step, c);
    styles_seen |= 1u << face_at(m, best)->style;
    if (!all_styles) return;
    if (step == EXR_FONT_STEP_REQUESTED) step = EXR_FONT_STEP_FAMILY_STYLE;
  }
}
static void add_list(const exr_font_manager *m, const char *list, unsigned style, unsigned step, int all_styles, chain *c) {
  char family[128];
  size_t at = 0;
  int r;
  if (!list) return;
  while ((r = exr_family_next(list, &at, family)) == 1) {
    add_family(m, family, style, step, all_styles, c);
  }
  if (r < 0 && !at && strlen(list) < sizeof(family)) add_family(m, list, style, step, all_styles, c);
}
static void build(const exr_font_manager *m, const char *family, unsigned style, chain *c) {
  size_t i;
  memset(c, 0, sizeof(*c));
  style &= EXR_FONT_STYLE_BOLD_ITALIC;
  if (family && *family) {
    char name[128];
    size_t at = 0;
    while (exr_family_next(family, &at, name) == 1) {
      if (exr_family_equal(name, "serif")) add_list(m, m->serif, style, EXR_FONT_STEP_REQUESTED, 1, c);
      else if (exr_family_equal(name, "sans-serif")) add_list(m, m->sans, style, EXR_FONT_STEP_REQUESTED, 1, c);
      else add_family(m, name, style, EXR_FONT_STEP_REQUESTED, 1, c);
    }
  }
  for (i = 0; i < m->fallback_count; i++) add_family(m, m->fallback[i], style, EXR_FONT_STEP_FALLBACK, 1, c);
  add_list(m, m->serif, style, EXR_FONT_STEP_SERIF, 1, c);
  add_list(m, m->sans, style, EXR_FONT_STEP_SANS_SERIF, 1, c);
  /* Keep the five configured stages' priority. Fill remaining slots from the
     entire discovered inventory, maximizing new coverage per face. Explicitly
     empty system lists opt out, for callers requesting a closed font set. */
  while ((*m->serif || *m->sans) && c->count < EXR_FONT_CHAIN_MAX && c->bytes < EXR_FONT_MANAGER_MAX_BYTES) {
    size_t best = SIZE_MAX, most = 0;
    unsigned long nearest = ULONG_MAX;
    unsigned color = 0;
    for (i = 0; i < m->face_count; i++) {
      size_t added;
      unsigned long d;
      const exr_fm_face *f = face_at(m, i);
      if (listed(c, i) || m->files.items[m->faces[i].file].size > EXR_FONT_MANAGER_MAX_BYTES - c->bytes) continue;
      added = contribution(f, c, 0);
      d = distance(f, style);
      /* A monochrome symbol face can map every emoji scalar but lack its ZWJ
         ligatures. Prefer color-capable faces in the automatic tail. */
      if (added && (best == SIZE_MAX || f->color > color ||
          (f->color == color && (added > most || (added == most && d < nearest))))) {
        best = i; most = added; nearest = d; color = f->color;
      }
    }
    if (best == SIZE_MAX) break;
    append(m, best, EXR_FONT_STEP_DISCOVERED, c);
  }
}
exr_status exr_font_manager_chain(const exr_font_manager *m, const char *family, unsigned style,
                                  exr_font_chain_link **out, size_t *count, exr_error *e) {
  chain c;
  if (out) *out = NULL;
  if (count) *count = 0;
  if (!m || !out || !count) return exr_fail(e, EXR_ARGUMENT, "Invalid font chain request");
  build(m, family, style, &c);
  if (c.count) {
    if (!(*out = malloc(c.count * sizeof(**out)))) return exr_fail(e, EXR_MEMORY, "Font chain allocation failed");
    memcpy(*out, c.links, c.count * sizeof(**out));
    *count = c.count;
  }
  return exr_fail(e, EXR_OK, "");
}
exr_status exr_font_manager_pick(const exr_font_manager *m, const char *family, unsigned style, uint32_t cp,
                                 exr_font_pick_result *out, exr_error *e) {
  chain c;
  size_t i;
  if (!m || !out || out->struct_size < sizeof(*out) || cp > 0x10ffff || (cp >= 0xd800 && cp <= 0xdfff))
    return exr_fail(e, EXR_ARGUMENT, "Invalid font pick request");
  out->face = SIZE_MAX; out->step = EXR_FONT_STEP_NONE; out->chain_position = SIZE_MAX;
  build(m, family, style, &c);
  for (i = 0; i < c.count; i++)
    if (covers(face_at(m, c.links[i].face), cp)) {
      out->face = c.links[i].face; out->step = c.links[i].step; out->chain_position = i;
      break;
    }
  return exr_fail(e, EXR_OK, "");
}
exr_status exr_font_manager_create_font(const exr_font_manager *m, const char *family, unsigned style,
                                        exr_font **out, size_t **faces, size_t *count, exr_error *e) {
  chain c;
  exr_font_input inputs[EXR_FONT_CHAIN_MAX];
  unsigned char *loaded[EXR_FONT_CHAIN_MAX] = {0};
  size_t files[EXR_FONT_CHAIN_MAX], map[EXR_FONT_CHAIN_MAX], n = 0, required = 0, total = 0, i, j;
  exr_status status;
  if (out) *out = NULL;
  if (faces) *faces = NULL;
  if (count) *count = 0;
  if (!m || !out) return exr_fail(e, EXR_ARGUMENT, "Invalid font manager font request");
  build(m, family, style, &c);
  for (i = 0; i < c.count; i++) {
    size_t face = c.links[i].face, file_index = m->faces[face].file;
    const exr_fm_file *file = &m->files.items[file_index];
    unsigned char *bytes = NULL;
    size_t size = 0;
    for (j = 0; j < n; j++) if (files[j] == file_index) { bytes = (unsigned char *)inputs[j].data; size = inputs[j].size; break; }
    if (bytes) {
      if (size > EXR_FONT_MANAGER_MAX_BYTES - total) continue;
      total += size;
    } else {
      uint64_t now_size = 0;
      int64_t now_mtime = 0;
      if (exr_fm_stat(file->path, &now_size, &now_mtime) != 2 || now_size != file->size ||
          now_mtime != file->mtime || now_size > EXR_FONT_MANAGER_MAX_BYTES - total) continue;
      if (exr_read(file->path, &bytes, &size, NULL) != EXR_OK || size != now_size) { free(bytes); continue; }
      loaded[n] = bytes;
      total += size;
    }
    inputs[n] = (exr_font_input){bytes, size, face_at(m, face)->face_index};
    files[n] = file_index;
    map[n++] = face;
    if (c.links[i].step != EXR_FONT_STEP_DISCOVERED) required++;
  }
  if (!n) status = exr_fail(e, EXR_FONT, "No font in the fallback chain could be loaded");
  else status = exr_font_create_managed(inputs, n, out, e);
  for (i = 0; i < n; i++) free(loaded[i]);
  if (status != EXR_OK) return status;
  (*out)->manager_order = 1;
  (*out)->manager_required = required;
  if (faces) {
    if (!(*faces = malloc(n * sizeof(**faces)))) {
      exr_font_free(*out); *out = NULL;
      return exr_fail(e, EXR_MEMORY, "Font chain map allocation failed");
    }
    memcpy(*faces, map, n * sizeof(**faces));
  }
  if (count) *count = n;
  return exr_fail(e, EXR_OK, "");
}
