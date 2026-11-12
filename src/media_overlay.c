/* SPDX-License-Identifier: MIT */
/* EPUB 3 Media Overlay (SMIL) reading: which text fragment belongs to which
   audio interval. The engine parses and maps; it never plays audio. */
#include "layout_internal.h"
#include "base_internal.h"
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char *local(const char *name) {
  const char *p = name ? strrchr(name, '|') : NULL;
  return p ? p + 1 : name ? name : "";
}
static char *dup(const char *s) { return exr_copy(s, strlen(s)); }

void exr_media_overlay_free(exr_media_overlay *o) {
  size_t i;
  if (!o) return;
  for (i = 0; i < o->clip_count; i++) {
    free((void *)o->clips[i].par_id); free((void *)o->clips[i].text_path);
    free((void *)o->clips[i].fragment); free((void *)o->clips[i].audio_path);
  }
  free(o->clips); free((void *)o->smil_path);
  free((void *)o->active_class); free((void *)o->playback_active_class);
  free(o);
}

/* SMIL clock value -> milliseconds, -1 when malformed. */
static long long clock_ms(const char *s) {
  char *end;
  double v;
  int colons = 0;
  const char *c;
  while (isspace((unsigned char)*s)) s++;
  if (!*s) return -1;
  for (c = s; *c; c++) colons += *c == ':';
  if (colons) {
    double total = 0;
    int parts = 0;
    if (colons > 2) return -1;
    for (;;) {
      v = strtod(s, &end);
      if (end == s || v < 0) return -1;
      total = total * 60 + v;
      parts++;
      if (*end == ':') { s = end + 1; continue; }
      s = end;
      break;
    }
    if (parts != colons + 1) return -1;
    while (isspace((unsigned char)*s)) s++;
    return *s ? -1 : (long long)(total * 1000 + 0.5);
  }
  v = strtod(s, &end);
  if (end == s || v < 0) return -1;
  while (isspace((unsigned char)*end)) end++;
  if (!*end || !strcmp(end, "s")) return (long long)(v * 1000 + 0.5);
  if (!strcmp(end, "ms")) return (long long)(v + 0.5);
  if (!strcmp(end, "min")) return (long long)(v * 60000 + 0.5);
  if (!strcmp(end, "h")) return (long long)(v * 3600000 + 0.5);
  return -1;
}

static const exr_node *child_named(const exr_document *d, const exr_node *n, const char *name) {
  size_t c;
  for (c = n->first_child; c != SIZE_MAX; c = d->nodes[c].next_sibling)
    if (!strcmp(local(d->nodes[c].name), name)) return &d->nodes[c];
  return NULL;
}
static const char *node_text(const exr_document *d, const exr_node *n) {
  size_t c;
  for (c = n->first_child; c != SIZE_MAX; c = d->nodes[c].next_sibling)
    if (d->nodes[c].kind == EXR_NODE_TEXT && d->nodes[c].text) return d->nodes[c].text;
  return "";
}
static const exr_node *tree_nodes(const exr_document *d, size_t *n) { return exr_document_nodes(d, n); }

typedef struct {
  exr_publication *p;
  const exr_document *index;
  const exr_part *parts;
  size_t part_count;
  size_t cached_part;
  exr_document *cached;
} context;

static const exr_node *find_id(const exr_document *d, const char *id) {
  size_t i, n;
  const exr_node *nodes = tree_nodes(d, &n);
  for (i = 0; i < n; i++) {
    const char *v = nodes[i].kind == EXR_NODE_TEXT ? NULL : exr_node_attribute(&nodes[i], "id");
    if (v && !strcmp(v, id)) return &nodes[i];
  }
  return NULL;
}
static int resource_present(const exr_document *index, const char *path) {
  size_t i, n;
  const exr_resource *r = exr_document_resources(index, &n);
  for (i = 0; i < n; i++) if (!strcmp(r[i].path, path)) return 1;
  return 0;
}

static exr_status add_clip(context *c, exr_media_overlay *o, const char *smil_path, const exr_node *par,
                           const exr_document *smil, exr_error *e) {
  const exr_node *text = child_named(smil, par, "text"), *audio = child_named(smil, par, "audio");
  exr_overlay_clip clip, *grown;
  char path[2048], decoded[2048];
  const char *src, *hash, *value;
  size_t i;
  if (!text || !audio) return EXR_OK;
  memset(&clip, 0, sizeof(clip));
  clip.text_part = clip.text_start = clip.text_end = SIZE_MAX;
  clip.clip_end_ms = -1;
  value = exr_node_attribute(par, "id");
  clip.par_id = dup(value ? value : "");
  src = exr_node_attribute(text, "src");
  hash = src ? strchr(src, '#') : NULL;
  clip.fragment = dup("");
  if (hash) {
    free((void *)clip.fragment);
    if (!exr_uri_decode(hash + 1, strlen(hash + 1), decoded)) snprintf(decoded, sizeof(decoded), "%s", hash + 1);
    clip.fragment = dup(decoded);
  }
  clip.text_path = dup(src && exr_resolve_path(smil_path, src, path) ? path : "");
  value = exr_node_attribute(audio, "src");
  clip.audio_path = dup(value && exr_resolve_path(smil_path, value, path) ? path : "");
  value = exr_node_attribute(audio, "clipBegin");
  clip.clip_begin_ms = value && clock_ms(value) >= 0 ? clock_ms(value) : 0;
  value = exr_node_attribute(audio, "clipEnd");
  clip.clip_end_ms = value ? clock_ms(value) : -1;
  if (!clip.par_id || !clip.fragment || !clip.text_path || !clip.audio_path) {
    free((void *)clip.par_id); free((void *)clip.fragment); free((void *)clip.text_path); free((void *)clip.audio_path);
    return exr_fail(e, EXR_MEMORY, "Overlay clip allocation failed");
  }
  clip.audio_present = clip.audio_path[0] && resource_present(c->index, clip.audio_path);
  if (!clip.audio_present) o->missing_audio++;
  for (i = 0; clip.text_path[0] && i < c->part_count; i++)
    if (c->parts[i].path && !strcmp(c->parts[i].path, clip.text_path)) { clip.text_part = i; break; }
  if (clip.text_part != SIZE_MAX) {
    const exr_node *target = NULL;
    size_t length = 0;
    if (c->cached_part != clip.text_part) {
      exr_document_free(c->cached);
      c->cached = NULL;
      c->cached_part = SIZE_MAX;
      if (exr_publication_load(c->p, clip.text_part, &c->cached, NULL) == EXR_OK) c->cached_part = clip.text_part;
    }
    if (c->cached) {
      if (clip.fragment[0]) target = find_id(c->cached, clip.fragment);
      else { exr_document_text(c->cached, &length); clip.text_start = 0; clip.text_end = length; }
      if (target && target->start != SIZE_MAX) { clip.text_start = target->start; clip.text_end = target->end; }
    }
  }
  if (clip.text_start == SIZE_MAX) o->unresolved_text++;
  grown = realloc(o->clips, (o->clip_count + 1) * sizeof(*o->clips));
  if (!grown) {
    free((void *)clip.par_id); free((void *)clip.fragment); free((void *)clip.text_path); free((void *)clip.audio_path);
    return exr_fail(e, EXR_MEMORY, "Overlay clip allocation failed");
  }
  o->clips = grown;
  o->clips[o->clip_count++] = clip;
  return EXR_OK;
}

static exr_status walk(context *c, exr_media_overlay *o, const char *smil_path, const exr_document *smil,
                       size_t node, unsigned depth, exr_error *e) {
  size_t child;
  exr_status status;
  if (depth > 64) return exr_fail(e, EXR_LIMIT, "SMIL nesting exceeds 64 levels");
  for (child = smil->nodes[node].first_child; child != SIZE_MAX; child = smil->nodes[child].next_sibling) {
    const char *tag;
    if (smil->nodes[child].kind == EXR_NODE_TEXT) continue;
    tag = local(smil->nodes[child].name);
    if (!strcmp(tag, "par")) status = add_clip(c, o, smil_path, &smil->nodes[child], smil, e);
    else status = walk(c, o, smil_path, smil, child, depth + 1, e);
    if (status != EXR_OK) return status;
  }
  return EXR_OK;
}

exr_status exr_publication_media_overlay(exr_publication *p, size_t part, exr_media_overlay **out, exr_error *e) {
  const exr_document *index = NULL;
  exr_document *package = NULL, *smil = NULL;
  const exr_resource *res;
  const exr_chapter *chapters;
  exr_media_overlay *o = NULL;
  const char *overlay_id = NULL;
  void *bytes = NULL;
  size_t count, i, smil_resource = SIZE_MAX, size = 0, pn;
  context c;
  exr_status status;
  if (!out) return exr_fail(e, EXR_ARGUMENT, "Missing media overlay output");
  *out = NULL;
  memset(&c, 0, sizeof(c));
  c.cached_part = SIZE_MAX;
  if (!p) return exr_fail(e, EXR_ARGUMENT, "Missing publication");
  status = exr_publication_retain_epub(p, &index, e);
  if (status != EXR_OK) return status;
  chapters = exr_document_chapters(index, &count);
  res = exr_document_resources(index, &pn);
  if (part >= count) { status = exr_fail(e, EXR_ARGUMENT, "Part is outside the publication"); goto done; }
  status = exr_document_package_tree(index, NULL, &package, e);
  if (status != EXR_OK) goto done;
  {
    size_t n, k;
    const exr_node *nodes = tree_nodes(package, &n);
    const char *id = res[chapters[part].resource].id;
    for (k = 0; k < n; k++) {
      const char *v;
      if (nodes[k].kind == EXR_NODE_TEXT || strcmp(local(nodes[k].name), "item")) continue;
      v = exr_node_attribute(&nodes[k], "id");
      if (v && !strcmp(v, id)) { overlay_id = exr_node_attribute(&nodes[k], "media-overlay"); break; }
    }
  }
  if (!overlay_id) { status = exr_fail(e, EXR_OK, ""); goto done; }
  for (i = 0; i < pn; i++) if (!strcmp(res[i].id, overlay_id)) { smil_resource = i; break; }
  if (smil_resource == SIZE_MAX) {
    status = exr_fail(e, EXR_FORMAT, "media-overlay refers to an item that is not in the manifest");
    goto done;
  }
  o = calloc(1, sizeof(*o));
  if (!o) { status = exr_fail(e, EXR_MEMORY, "Overlay allocation failed"); goto done; }
  o->smil_path = dup(res[smil_resource].path);
  o->duration_ms = -1;
  o->active_class = dup("");
  o->playback_active_class = dup("");
  if (!o->smil_path || !o->active_class || !o->playback_active_class) {
    status = exr_fail(e, EXR_MEMORY, "Overlay allocation failed"); goto done;
  }
  {
    size_t n, k;
    const exr_node *nodes = tree_nodes(package, &n);
    for (k = 0; k < n; k++) {
      const char *prop, *refines, *text;
      if (nodes[k].kind == EXR_NODE_TEXT || strcmp(local(nodes[k].name), "meta")) continue;
      prop = exr_node_attribute(&nodes[k], "property");
      if (!prop) continue;
      refines = exr_node_attribute(&nodes[k], "refines");
      text = node_text(package, &nodes[k]);
      if (!strcmp(prop, "media:duration") && refines && refines[0] == '#' && !strcmp(refines + 1, overlay_id))
        o->duration_ms = clock_ms(text);
      else if (!refines && (!strcmp(prop, "media:active-class") || !strcmp(prop, "media:playback-active-class"))) {
        char **slot = (char **)(prop[6] == 'a' ? &o->active_class : &o->playback_active_class);
        free(*slot);
        *slot = dup(text);
        if (!*slot) { status = exr_fail(e, EXR_MEMORY, "Overlay allocation failed"); goto done; }
      }
    }
  }
  status = exr_document_resource(index, smil_resource, &bytes, &size, e);
  if (status != EXR_OK) {
    status = exr_fail(e, EXR_FORMAT, "Media overlay file is missing or unreadable");
    goto done;
  }
  status = exr_xml_memory_tree(bytes, size, "smil", &smil, e);
  if (status != EXR_OK) {
    status = exr_fail(e, EXR_FORMAT, "Media overlay is not well-formed SMIL");
    goto done;
  }
  c.p = p; c.index = index;
  c.parts = exr_publication_parts(p, &c.part_count);
  status = walk(&c, o, o->smil_path, smil, 0, 0, e);
done:
  free(bytes);
  exr_document_free(smil);
  exr_document_free(package);
  exr_document_free(c.cached);
  if (status == EXR_OK && o) { *out = o; o = NULL; }
  exr_media_overlay_free(o);
  exr_publication_free(p);
  return status;
}
