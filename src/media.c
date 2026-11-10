/* SPDX-License-Identifier: MIT */
/* Identifies embedded media in one loaded EPUB part and writes the visible
   placeholder. Nothing is decoded or played; durations come from container
   headers only (WAV, MP3, MP4/M4A/MOV) and stay unknown otherwise. */
#include "formats_internal.h"
#include "base_internal.h"
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MEDIA_READ_LIMIT ((size_t)32 << 20)
#define MEDIA_MAX_ITEMS 4096

static const char *local(const char *name) {
  const char *p = name ? strrchr(name, '|') : NULL;
  return p ? p + 1 : name ? name : "";
}
static int has_token(const char *s, const char *word) {
  size_t n = strlen(word);
  while (s && *s) {
    const char *e;
    while (isspace((unsigned char)*s)) s++;
    e = s;
    while (*e && !isspace((unsigned char)*e)) e++;
    if ((size_t)(e - s) == n && !strncmp(s, word, n)) return 1;
    s = e;
  }
  return 0;
}
static int ieq(const char *a, const char *b) {
  for (; *a && *b; a++, b++) if (tolower((unsigned char)*a) != tolower((unsigned char)*b)) return 0;
  return !*a && !*b;
}
static int type_is(const char *type, const char *prefix) {
  size_t n = strlen(prefix), i;
  for (i = 0; i < n; i++) if (tolower((unsigned char)type[i]) != prefix[i]) return 0;
  return 1;
}
/* Formats no mainstream reading system plays: reported, never decoded. */
static int legacy_type(const char *type) {
  static const char *const bad[] = {"video/x-flv", "video/x-ms-wmv", "video/x-ms-asf", "video/x-msvideo",
    "audio/x-ms-wma", "audio/x-realaudio", "audio/vnd.rn-realaudio", "application/vnd.rn-realmedia",
    "video/vnd.rn-realvideo", "audio/midi", "audio/x-midi", "audio/mid"};
  size_t i;
  for (i = 0; i < sizeof(bad) / sizeof(*bad); i++) if (ieq(type, bad[i])) return 1;
  return 0;
}
static int extension_type(const char *path, char out[64]) {
  static const struct { const char *ext, *type; } map[] = {
    {"mp3", "audio/mpeg"}, {"m4a", "audio/mp4"}, {"aac", "audio/aac"}, {"wav", "audio/wav"},
    {"ogg", "audio/ogg"}, {"oga", "audio/ogg"}, {"opus", "audio/opus"}, {"flac", "audio/flac"},
    {"mp4", "video/mp4"}, {"m4v", "video/mp4"}, {"webm", "video/webm"}, {"ogv", "video/ogg"},
    {"mov", "video/quicktime"}, {"flv", "video/x-flv"}, {"wmv", "video/x-ms-wmv"},
    {"wma", "audio/x-ms-wma"}, {"avi", "video/x-msvideo"}, {"swf", "application/x-shockwave-flash"},
    {"mid", "audio/midi"}, {"midi", "audio/midi"}, {"class", "application/java-vm"}, {"jar", "application/java-archive"}};
  const char *dot = strrchr(path, '.'), *slash = strrchr(path, '/');
  size_t i;
  if (!dot || (slash && dot < slash)) return 0;
  for (i = 0; i < sizeof(map) / sizeof(*map); i++)
    if (ieq(dot + 1, map[i].ext)) { snprintf(out, 64, "%s", map[i].type); return 1; }
  return 0;
}

/* ---- duration probes -------------------------------------------------- */
static unsigned long long be(const unsigned char *p, int n) {
  unsigned long long v = 0;
  while (n--) v = v << 8 | *p++;
  return v;
}
static unsigned long long le(const unsigned char *p, int n) {
  unsigned long long v = 0;
  while (n--) v = v << 8 | p[n];
  return v;
}
static long long wav_ms(const unsigned char *b, size_t n) {
  size_t at = 12;
  unsigned long long rate = 0;
  if (n < 12 || memcmp(b, "RIFF", 4) || memcmp(b + 8, "WAVE", 4)) return -1;
  while (at + 8 <= n) {
    unsigned long long size = le(b + at + 4, 4);
    if (!memcmp(b + at, "fmt ", 4) && size >= 16 && at + 8 + 16 <= n) rate = le(b + at + 16, 4);
    else if (!memcmp(b + at, "data", 4)) {
      if (!rate || size > n - at - 8) size = n - at - 8;
      return rate ? (long long)(size * 1000 / rate) : -1;
    }
    at += 8 + (size_t)size + (size & 1);
  }
  return -1;
}
static long long mp4_box(const unsigned char *b, size_t n, size_t depth) {
  size_t at = 0;
  while (at + 8 <= n) {
    unsigned long long size = be(b + at, 4);
    size_t head = 8;
    if (size == 1) { if (at + 16 > n) return -1; size = be(b + at + 8, 8); head = 16; }
    else if (!size) size = n - at;
    if (size < head || size > n - at) return -1;
    if (!memcmp(b + at + 4, "mvhd", 4)) {
      const unsigned char *p = b + at + head;
      size_t room = (size_t)size - head;
      unsigned long long scale, length;
      if (room >= 20 && !p[0]) { scale = be(p + 12, 4); length = be(p + 16, 4); }
      else if (room >= 32 && p[0] == 1) { scale = be(p + 20, 4); length = be(p + 24, 8); }
      else return -1;
      return scale ? (long long)(length * 1000 / scale) : -1;
    }
    if (depth < 3 && !memcmp(b + at + 4, "moov", 4)) {
      long long v = mp4_box(b + at + head, (size_t)size - head, depth + 1);
      if (v >= 0) return v;
    }
    at += (size_t)size;
  }
  return -1;
}
static long long mp3_ms(const unsigned char *b, size_t n, int *estimated) {
  static const int v1[] = {0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0};
  static const int v2[] = {0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0};
  static const int sr1[] = {44100, 48000, 32000, 0};
  size_t at = 0, end;
  if (n > 10 && !memcmp(b, "ID3", 3))
    at = 10 + ((size_t)(b[6] & 127) << 21 | (size_t)(b[7] & 127) << 14 | (size_t)(b[8] & 127) << 7 | (b[9] & 127));
  for (end = n < at + 65536 ? n : at + 65536; at + 4 <= end; at++) {
    unsigned h = (unsigned)be(b + at, 4);
    int version = (h >> 19) & 3, layer = (h >> 17) & 3, bi = (h >> 12) & 15, si = (h >> 10) & 3, mono = ((h >> 6) & 3) == 3;
    int bitrate, rate, frame_samples;
    size_t xing;
    if ((h & 0xFFE00000u) != 0xFFE00000u || version == 1 || layer != 1 || bi == 0 || bi == 15 || si == 3) continue;
    bitrate = (version == 3 ? v1 : v2)[bi] * 1000;
    rate = sr1[si] >> (version == 3 ? 0 : version == 2 ? 1 : 2);
    frame_samples = version == 3 ? 1152 : 576;
    xing = at + 4 + (version == 3 ? (mono ? 17 : 32) : (mono ? 9 : 17));
    if (xing + 12 <= n && (!memcmp(b + xing, "Xing", 4) || !memcmp(b + xing, "Info", 4)) && (b[xing + 7] & 1) && be(b + xing + 8, 4))
      return (long long)(be(b + xing + 8, 4) * (unsigned long long)frame_samples * 1000 / (unsigned)rate);
    *estimated = 1;
    return (long long)((unsigned long long)(n - at) * 8000 / (unsigned)bitrate);
  }
  return -1;
}
static void *limited_allocate(void *context, size_t size) { (void)context; return size <= MEDIA_READ_LIMIT ? malloc(size ? size : 1) : NULL; }
static void *limited_reallocate(void *context, void *data, size_t size) { (void)context; return size <= MEDIA_READ_LIMIT ? realloc(data, size ? size : 1) : NULL; }
static void limited_release(void *context, void *data) { (void)context; free(data); }
static long long probe_duration(const exr_document *d, size_t resource, const char *type, unsigned *flags) {
  exr_resource_allocator a = {NULL, limited_allocate, limited_reallocate, limited_release};
  void *bytes = NULL;
  size_t size = 0;
  long long ms = -1;
  int estimated = 0;
  if (exr_document_resource_bounded(d, resource, &a, NULL, &bytes, &size, NULL) != EXR_OK) return -1;
  if (ieq(type, "audio/wav") || ieq(type, "audio/x-wav") || ieq(type, "audio/wave")) ms = wav_ms(bytes, size);
  else if (ieq(type, "audio/mpeg") || ieq(type, "audio/mp3")) ms = mp3_ms(bytes, size, &estimated);
  else if (ieq(type, "audio/mp4") || ieq(type, "audio/x-m4a") || ieq(type, "video/mp4") || ieq(type, "video/quicktime") || ieq(type, "audio/aac")) ms = mp4_box(bytes, size, 0);
  if (estimated && ms >= 0) *flags |= EXR_MEDIA_DURATION_ESTIMATED;
  a.release(NULL, bytes);
  return ms;
}

/* ---- references -------------------------------------------------------- */
typedef struct {
  char src[2048], path[2048], type[96];
  size_t resource;
  exr_media_state state;
} candidate;

static size_t find_resource(const exr_document *d, const char *path) {
  size_t i;
  for (i = 0; i < d->resource_count; i++) if (!strcmp(d->resources[i].path, path)) return i;
  return SIZE_MAX;
}
static int has_scheme(const char *s) {
  size_t i = 0;
  if (!isalpha((unsigned char)s[0])) return 0;
  while (isalnum((unsigned char)s[i]) || s[i] == '+' || s[i] == '-' || s[i] == '.') i++;
  return s[i] == ':';
}
/* Fills one candidate from a reference and optional declared type. */
static void classify(const exr_document *d, const char *base, const char *ref, const char *type,
                     int want_media, candidate *c) {
  char guess[64];
  memset(c, 0, sizeof(*c));
  c->resource = SIZE_MAX;
  snprintf(c->src, sizeof(c->src), "%s", ref);
  if (type) snprintf(c->type, sizeof(c->type), "%s", type);
  if (!ref[0]) { c->state = EXR_MEDIA_NO_SOURCE; return; }
  if (has_scheme(ref) || !strncmp(ref, "//", 2)) {
    c->state = EXR_MEDIA_REMOTE;
    if (!c->type[0] && extension_type(ref, guess)) snprintf(c->type, sizeof(c->type), "%s", guess);
    return;
  }
  if (!exr_resolve_path(base, ref, c->path)) { c->path[0] = 0; c->state = EXR_MEDIA_MISSING; return; }
  c->resource = find_resource(d, c->path);
  if (c->resource != SIZE_MAX && d->resources[c->resource].media_type && d->resources[c->resource].media_type[0])
    snprintf(c->type, sizeof(c->type), "%s", d->resources[c->resource].media_type);
  else if (!c->type[0] && extension_type(c->path, guess)) snprintf(c->type, sizeof(c->type), "%s", guess);
  if (c->resource == SIZE_MAX) { c->state = EXR_MEDIA_MISSING; return; }
  if (c->type[0] && (legacy_type(c->type) || (want_media && !type_is(c->type, "audio/") && !type_is(c->type, "video/"))))
    c->state = EXR_MEDIA_UNSUPPORTED;
  else c->state = want_media || type_is(c->type, "audio/") || type_is(c->type, "video/") ? EXR_MEDIA_AVAILABLE : EXR_MEDIA_UNSUPPORTED;
}
static void format_time(long long ms, char out[32]) {
  long long s = (ms + 500) / 1000;
  if (s >= 3600) snprintf(out, 32, "%lld:%02lld:%02lld", s / 3600, s / 60 % 60, s % 60);
  else snprintf(out, 32, "%lld:%02lld", s / 60, s % 60);
}
static const char *base_name(const char *path) {
  const char *s = strrchr(path, '/');
  return s ? s + 1 : path;
}
static char *dup(const char *s) { return exr_copy(s, strlen(s)); }

static int contains_word(const char *s, const char *word) {
  size_t i, n = strlen(word), len = strlen(s);
  for (i = 0; i + n <= len; i++) {
    size_t k;
    for (k = 0; k < n && tolower((unsigned char)s[i + k]) == word[k]; k++) {}
    if (k == n) return 1;
  }
  return 0;
}
static int cover_context(const exr_document *d, const exr_node *n) {
  if (d->chapter_count && contains_word(d->chapters[0].path, "cover")) return 1;
  for (; n; n = n->parent == SIZE_MAX ? NULL : &d->nodes[n->parent])
    if (has_token(exr_node_attribute(n, "http://www.idpf.org/2007/ops|type"), "cover") ||
        has_token(exr_node_attribute(n, "role"), "doc-cover")) return 1;
  return 0;
}
static int boolean_attribute(const exr_node *n, const char *name) {
  const char *v = exr_node_attribute(n, name);
  return v != NULL && strcmp(v, "false") != 0;
}
static const char *tag_of(const exr_document *d, size_t i) { return local(d->nodes[i].name); }
static void release_item(exr_media_item *m) {
  free((void *)m->src); free((void *)m->path); free((void *)m->media_type);
  free((void *)m->poster); free((void *)m->label);
}

static void make_label(const exr_media_item *m, char out[1200]) {
  const char *kind = m->kind == EXR_MEDIA_AUDIO ? "Audio" : m->kind == EXR_MEDIA_VIDEO ? "Video" : "Embedded media";
  const char *name = m->path ? base_name(m->path) : m->src;
  char time[32];
  switch (m->state) {
  case EXR_MEDIA_AVAILABLE:
    if (m->duration_ms >= 0) {
      format_time(m->duration_ms, time);
      snprintf(out, 1200, "[%s: %s, %s%s]", kind, name, m->flags & EXR_MEDIA_DURATION_ESTIMATED ? "about " : "", time);
    } else snprintf(out, 1200, "[%s: %s, duration unknown]", kind, name);
    break;
  case EXR_MEDIA_MISSING:
    snprintf(out, 1200, "[%s unavailable: %.200s is missing from this book]", kind, m->src);
    break;
  case EXR_MEDIA_UNSUPPORTED:
    snprintf(out, 1200, "[%s not supported: %.200s%s%.80s%s]", kind, name, m->media_type[0] ? " (" : "", m->media_type, m->media_type[0] ? ")" : "");
    break;
  case EXR_MEDIA_REMOTE:
    snprintf(out, 1200, "[%s is online: %.300s - not loaded]", kind, m->src);
    break;
  default:
    snprintf(out, 1200, "[%s: no source given]", kind);
  }
}
/* Chooses the first usable candidate, else the first candidate seen. */
static void pick(const exr_document *d, const char *base, const exr_node *n, int want_media,
                 candidate *best, size_t *count) {
  candidate c;
  const char *ref;
  size_t child;
  *count = 0;
  best->state = EXR_MEDIA_NO_SOURCE;
  best->src[0] = best->path[0] = best->type[0] = 0;
  best->resource = SIZE_MAX;
  ref = exr_node_attribute(n, "src");
  if (!ref) ref = exr_node_attribute(n, "data");
  if (ref && ref[0]) {
    classify(d, base, ref, exr_node_attribute(n, "type"), want_media, best);
    (*count)++;
  }
  for (child = n->first_child; child != SIZE_MAX; child = d->nodes[child].next_sibling) {
    const char *tag = tag_of(d, child);
    const exr_node *k = &d->nodes[child];
    if (!strcmp(tag, "source") && exr_node_attribute(k, "src")) {
      classify(d, base, exr_node_attribute(k, "src"), exr_node_attribute(k, "type"), want_media, &c);
    } else if (!strcmp(tag, "param") && exr_node_attribute(k, "name") && exr_node_attribute(k, "value") &&
               (ieq(exr_node_attribute(k, "name"), "movie") || ieq(exr_node_attribute(k, "name"), "src") ||
                ieq(exr_node_attribute(k, "name"), "url") || ieq(exr_node_attribute(k, "name"), "filename"))) {
      classify(d, base, exr_node_attribute(k, "value"), exr_node_attribute(n, "type"), want_media, &c);
    } else continue;
    if (!*count || (best->state != EXR_MEDIA_AVAILABLE && c.state == EXR_MEDIA_AVAILABLE)) *best = c;
    (*count)++;
  }
}

exr_status exr_media_scan(exr_document *d, exr_error *e) {
  const char *base = d->chapter_count ? d->chapters[0].path : "";
  size_t i;
  for (i = 0; i < d->node_count; i++) {
    exr_media_item item;
    exr_node *n = &d->nodes[i];
    const char *tag = tag_of(d, i), *type;
    candidate c;
    char label[1200], poster[2048];
    size_t count, ph;
    int is_object;
    if (n->kind == EXR_NODE_TEXT || !exr_media_element(tag)) continue;
    is_object = !strcmp(tag, "object");
    ph = n->first_child;
    if (ph == SIZE_MAX || d->nodes[ph].kind != EXR_NODE_TEXT || (d->nodes[ph].text && d->nodes[ph].text[0])) ph = SIZE_MAX;
    memset(&item, 0, sizeof(item));
    pick(d, base, n, !is_object && strcmp(tag, "embed"), &c, &count);
    type = exr_node_attribute(n, "type");
    if (is_object && c.state != EXR_MEDIA_NO_SOURCE) {
      /* Images, SVG and XHTML objects are ordinary content, not media. */
      const char *t = c.type[0] ? c.type : type ? type : "";
      if (type_is(t, "image/") || type_is(t, "text/") || type_is(t, "application/xhtml")) continue;
    }
    item.kind = !strcmp(tag, "audio") ? EXR_MEDIA_AUDIO : !strcmp(tag, "video") ? EXR_MEDIA_VIDEO :
                type_is(c.type, "audio/") ? EXR_MEDIA_AUDIO : type_is(c.type, "video/") ? EXR_MEDIA_VIDEO : EXR_MEDIA_EMBEDDED;
    item.state = c.state;
    item.element = i;
    item.placeholder = ph;
    item.tag = tag;
    item.source_count = count;
    item.duration_ms = -1;
    if (boolean_attribute(n, "autoplay")) item.flags |= EXR_MEDIA_AUTOPLAY;
    if (boolean_attribute(n, "loop")) item.flags |= EXR_MEDIA_LOOP;
    if (boolean_attribute(n, "controls")) item.flags |= EXR_MEDIA_CONTROLS;
    if (boolean_attribute(n, "muted")) item.flags |= EXR_MEDIA_MUTED;
    if (boolean_attribute(n, "hidden")) item.flags |= EXR_MEDIA_HIDDEN;
    if (cover_context(d, n)) item.flags |= EXR_MEDIA_COVER;
    if (item.kind == EXR_MEDIA_AUDIO && (item.flags & EXR_MEDIA_AUTOPLAY) && (item.flags & EXR_MEDIA_LOOP) && !(item.flags & EXR_MEDIA_CONTROLS))
      item.flags |= EXR_MEDIA_BACKGROUND;
    if (item.state == EXR_MEDIA_AVAILABLE && c.resource != SIZE_MAX)
      item.duration_ms = probe_duration(d, c.resource, c.type, &item.flags);
    item.src = dup(c.src);
    item.path = c.path[0] ? dup(c.path) : NULL;
    item.media_type = dup(c.type);
    poster[0] = 0;
    if (item.kind == EXR_MEDIA_VIDEO && exr_node_attribute(n, "poster") && !has_scheme(exr_node_attribute(n, "poster")) &&
        exr_resolve_path(base, exr_node_attribute(n, "poster"), poster)) item.poster = dup(poster);
    make_label(&item, label);
    item.label = dup(label);
    if (!item.src || !item.media_type || !item.label || (c.path[0] && !item.path)) { release_item(&item); return exr_fail(e, EXR_MEMORY, "Media table allocation failed"); }
    if (d->media_count >= MEDIA_MAX_ITEMS) { release_item(&item); continue; }
    if (!exr_grow((void **)&d->media, &d->media_capacity, d->media_count + 1, sizeof(*d->media))) { release_item(&item); return exr_fail(e, EXR_MEMORY, "Media table allocation failed"); }
    if (ph != SIZE_MAX && !(item.flags & EXR_MEDIA_HIDDEN)) {
      char *text = exr_model_copy(d, label, strlen(label));
      if (!text) { release_item(&item); return exr_fail(e, EXR_LIMIT, "Media placeholder exceeds text limit"); }
      free((void *)d->nodes[ph].text);
      d->nodes[ph].text = text;
    } else item.placeholder = SIZE_MAX;
    d->media[d->media_count++] = item;
  }
  return EXR_OK;
}
