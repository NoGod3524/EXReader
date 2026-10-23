/* SPDX-License-Identifier: MIT */
/* OPDS 1.x Atom and OPDS 2 JSON feed models. See docs/WP15-OPDS.md for the frozen support table. */
#include "opds_internal.h"
#include <ctype.h>

typedef struct { void *p; size_t n, cap, sz; } vec;
static void *vec_push(vec *v) {
  if (v->n == v->cap) {
    size_t cap = v->cap ? v->cap * 2 : 8;
    void *p = realloc(v->p, cap * v->sz);
    if (!p) return NULL;
    v->p = p; v->cap = cap;
  }
  memset((char *)v->p + v->n * v->sz, 0, v->sz);
  return (char *)v->p + v->n++ * v->sz;
}
static void *vec_arena(vec *v, struct opds_arena *a) {
  void *p = arena_alloc(a, v->n * v->sz + 1);
  if (p && v->n) memcpy(p, v->p, v->n * v->sz);
  free(v->p); v->p = NULL; v->n = v->cap = 0;
  return p;
}

typedef struct facet_group {
  struct facet_group *next;
  const char *title;
  vec choices;
} facet_group;
typedef struct {
  struct opds_arena *a; const opds_limits *lim; const char *base; opds_error *err;
  facet_group *facets, *last_facet;
  size_t facet_count, choice_count;
} fctx;

static int streq_ci(const char *a, const char *b) { return opds_ascii_ieq(a, b); }

static int protected_type(const char *t) {
  char m[96];
  opds_media_type(t, m, sizeof m);
  return !strcmp(m, "application/vnd.adobe.adept+xml") ||
         !strcmp(m, "application/vnd.readium.lcp.license.v1.0+json") ||
         !strcmp(m, "application/vnd.readium.license.status.v1.0+json") ||
         !strcmp(m, "application/vnd.librarysimplified.axisnow+json") ||
         !strcmp(m, "application/vnd.librarysimplified.findaway.license+json") ||
         !strcmp(m, "application/vnd.adobe.adept.acsm+xml");
}

static void classify(opds_link *l) {
  const char *p = l->rel ? l->rel : "";
  l->kind = OPDS_REL_OTHER; l->acq = OPDS_ACQ_NONE;
  while (*p) {
    char tok[160];
    size_t n = 0;
    while (*p == ' ') p++;
    while (*p && *p != ' ' && n + 1 < sizeof tok) tok[n++] = *p++;
    tok[n] = 0;
    if (!n) break;
    if (!strncmp(tok, "http://opds-spec.org/acquisition", 32)) {
      const char *s = tok + 32;
      l->kind = OPDS_REL_ACQUISITION;
      l->acq = !strcmp(s, "/open-access") ? OPDS_ACQ_OPEN_ACCESS : !strcmp(s, "/borrow") ? OPDS_ACQ_BORROW :
               !strcmp(s, "/buy") ? OPDS_ACQ_BUY : !strcmp(s, "/sample") || !strcmp(s, "/preview") ? OPDS_ACQ_SAMPLE :
               !strcmp(s, "/subscribe") ? OPDS_ACQ_SUBSCRIBE : OPDS_ACQ_GENERIC;
      return;
    }
    if (!strcmp(tok, "http://opds-spec.org/image/thumbnail") || !strcmp(tok, "http://opds-spec.org/thumbnail")) { l->kind = OPDS_REL_THUMBNAIL; return; }
    if (!strcmp(tok, "http://opds-spec.org/image")) { l->kind = OPDS_REL_IMAGE; return; }
    if (!strcmp(tok, "self")) l->kind = OPDS_REL_SELF;
    else if (!strcmp(tok, "start")) l->kind = OPDS_REL_START;
    else if (!strcmp(tok, "up")) l->kind = OPDS_REL_UP;
    else if (!strcmp(tok, "next")) l->kind = OPDS_REL_NEXT;
    else if (!strcmp(tok, "previous") || !strcmp(tok, "prev")) l->kind = OPDS_REL_PREVIOUS;
    else if (!strcmp(tok, "first")) l->kind = OPDS_REL_FIRST;
    else if (!strcmp(tok, "last")) l->kind = OPDS_REL_LAST;
    else if (!strcmp(tok, "search")) l->kind = OPDS_REL_SEARCH;
    else if (!strcmp(tok, "subsection")) l->kind = OPDS_REL_SUBSECTION;
    if (l->kind != OPDS_REL_OTHER) return;
  }
}

static opds_status make_link(fctx *c, vec *links, const char *rel, const char *href, const char *base,
                             const char *type, const char *title, unsigned flags, const char *indirect) {
  char url[OPDS_URL_MAX];
  opds_link *l;
  int braces = strchr(href, '{') != NULL;
  opds_status st;
  if (links->n >= c->lim->max_links_per_entry * 64 + 64) return opds_fail(c->err, OPDS_LIMIT, "link budget exceeded");
  st = opds_url_resolve_ex(base, href, braces, url, sizeof url);
  if (st == OPDS_LIMIT) return opds_fail(c->err, OPDS_FORMAT, "link href too long");
  if (st) return st;
  l = (opds_link *)vec_push(links);
  if (!l) return OPDS_MEMORY;
  l->rel = arena_strdup(c->a, rel); l->href = arena_strdup(c->a, url); l->raw_href = arena_strdup(c->a, href);
  l->type = type ? arena_strdup(c->a, type) : NULL;
  l->title = title ? arena_strdup(c->a, title) : NULL;
  l->indirect_type = indirect ? arena_strdup(c->a, indirect) : NULL;
  if (!l->rel || !l->href || !l->raw_href) return OPDS_MEMORY;
  if (braces) flags |= OPDS_LINK_TEMPLATED;
  if (type && protected_type(type)) flags |= OPDS_LINK_PROTECTED;
  l->flags = flags;
  classify(l);
  if (l->kind != OPDS_REL_ACQUISITION) l->flags &= ~(unsigned)OPDS_LINK_PROTECTED;
  return OPDS_OK;
}

static int has_acquisition(const opds_link *l, size_t n) {
  for (size_t i = 0; i < n; i++) if (l[i].acq != OPDS_ACQ_NONE) return 1;
  return 0;
}

static int rel_token(const char *rel, const char *token) {
  size_t size = strlen(token);
  while (rel && *rel) {
    const char *start;
    while (isspace((unsigned char)*rel)) rel++;
    start = rel;
    while (*rel && !isspace((unsigned char)*rel)) rel++;
    if ((size_t)(rel - start) == size && !memcmp(start, token, size)) return 1;
  }
  return 0;
}

static opds_status facet_number(fctx *c, const char *text, int64_t *out) {
  uint64_t value = 0;
  *out = -1;
  if (!text) return OPDS_OK;
  if (!*text) return opds_fail(c->err, OPDS_FORMAT, "empty facet item count");
  for (; *text; text++) {
    unsigned digit = (unsigned char)*text - '0';
    if (digit > 9 || value > ((uint64_t)INT64_MAX - digit) / 10)
      return opds_fail(c->err, OPDS_FORMAT, "invalid facet item count");
    value = value * 10 + digit;
  }
  *out = (int64_t)value;
  return OPDS_OK;
}

static opds_status facet_new(fctx *c, const char *title, int merge, facet_group **out) {
  facet_group *group;
  for (group = c->facets; merge && group; group = group->next)
    if (!strcmp(group->title, title)) { *out = group; return OPDS_OK; }
  if (c->facet_count >= c->lim->max_entries)
    return opds_fail(c->err, OPDS_LIMIT, "facet group budget exceeded");
  group = (facet_group *)calloc(1, sizeof(*group));
  if (!group) return OPDS_MEMORY;
  group->title = arena_strdup(c->a, title);
  if (!group->title) { free(group); return OPDS_MEMORY; }
  group->choices.sz = sizeof(opds_facet_choice);
  if (c->last_facet) c->last_facet->next = group; else c->facets = group;
  c->last_facet = group;
  c->facet_count++;
  *out = group;
  return OPDS_OK;
}

static opds_status facet_choice(fctx *c, facet_group *group, const opds_link *link,
                               int active, int64_t count, int single_active) {
  opds_facet_choice *choice;
  if (group->choices.n >= c->lim->max_links_per_entry || c->choice_count >= c->lim->max_entries)
    return opds_fail(c->err, OPDS_LIMIT, "facet choice budget exceeded");
  if (active && single_active) {
    opds_facet_choice *old = (opds_facet_choice *)group->choices.p;
    for (size_t i = 0; i < group->choices.n; i++)
      if (old[i].active) return opds_fail(c->err, OPDS_FORMAT, "multiple active OPDS1 facets in a group");
  }
  choice = (opds_facet_choice *)vec_push(&group->choices);
  if (!choice) return OPDS_MEMORY;
  choice->link = *link; choice->active = active; choice->number_of_items = count;
  c->choice_count++;
  return OPDS_OK;
}

static opds_status facets_finish(fctx *c) {
  opds_facet *result;
  size_t i = 0;
  if (!c->facet_count) return OPDS_OK;
  if (c->facet_count > SIZE_MAX / sizeof(*result)) return OPDS_LIMIT;
  result = (opds_facet *)arena_alloc(c->a, c->facet_count * sizeof(*result));
  if (!result) return OPDS_MEMORY;
  for (facet_group *group = c->facets; group; group = group->next, i++) {
    result[i].title = group->title;
    result[i].choice_count = group->choices.n;
    result[i].choices = (const opds_facet_choice *)vec_arena(&group->choices, c->a);
    if (!result[i].choices) return OPDS_MEMORY;
  }
  c->a->facets = result; c->a->facet_count = c->facet_count;
  return OPDS_OK;
}

static void facets_release(fctx *c) {
  while (c->facets) {
    facet_group *next = c->facets->next;
    free(c->facets->choices.p); free(c->facets); c->facets = next;
  }
}

/* ---- Atom ---- */
static const opds_xnode *xchild(const opds_xnode *n, const char *ns, const char *name) {
  for (const opds_xnode *c = n->first; c; c = c->next) if (opds_xis(c, ns, name)) return c;
  return NULL;
}
static const char *xchild_text(const opds_xnode *n, const char *ns, const char *name) {
  const opds_xnode *c = xchild(n, ns, name);
  return c ? c->text : NULL;
}
static const char *xchild_text2(const opds_xnode *n, const char *name) {
  const char *t = xchild_text(n, NS_DC, name);
  return t ? t : xchild_text(n, NS_DCTERMS, name);
}

static opds_status xml_base(fctx *c, const opds_xnode *n, const char **out) {
  const opds_xnode *chain[260];
  size_t k = 0;
  char cur[OPDS_URL_MAX], next[OPDS_URL_MAX];
  int have = 0;
  for (const opds_xnode *p = n; p; p = p->parent) {
    if (k >= 256) return opds_fail(c->err, OPDS_LIMIT, "xml:base chain too deep");
    chain[k++] = p;
  }
  if (c->base) {
    if (strlen(c->base) >= sizeof cur) return opds_fail(c->err, OPDS_LIMIT, "base URL too long");
    strcpy(cur, c->base); have = 1;
  }
  while (k--) {
    const char *b = opds_xattr_get(chain[k], NS_XML, "base");
    if (!b) continue;
    opds_status st = opds_url_resolve(have ? cur : NULL, b, next, sizeof next);
    if (st) return opds_fail(c->err, OPDS_FORMAT, "bad xml:base");
    strcpy(cur, next); have = 1;
  }
  *out = have ? arena_strdup(c->a, cur) : NULL;
  return OPDS_OK;
}

static void scan_indirect(const opds_xnode *n, unsigned *flags, const char **first, int depth) {
  for (const opds_xnode *c = n->first; c; c = c->next) {
    if (opds_xis(c, NS_OPDS, "indirectAcquisition")) {
      const char *t = opds_xattr_get(c, "", "type");
      if (t) {
        if (!*first) *first = t;
        if (protected_type(t)) *flags |= OPDS_LINK_PROTECTED;
      }
      if (depth < 32) scan_indirect(c, flags, first, depth + 1);
    }
  }
}

static opds_status atom_link(fctx *c, const opds_xnode *ln, vec *links) {
  const char *href = opds_xattr_get(ln, "", "href"), *rel = opds_xattr_get(ln, "", "rel");
  const char *base, *indirect = NULL;
  unsigned flags = 0;
  opds_status st;
  if (!href || !*href) return opds_fail(c->err, OPDS_FORMAT, "Atom link without href");
  if ((st = xml_base(c, ln, &base)) != OPDS_OK) return st;
  if (xchild(ln, NS_OPDS, "price")) flags |= OPDS_LINK_PRICED;
  if (xchild(ln, NS_OPDS, "indirectAcquisition")) { flags |= OPDS_LINK_INDIRECT; scan_indirect(ln, &flags, &indirect, 0); }
  return make_link(c, links, rel && *rel ? rel : "alternate", href, base,
                   opds_xattr_get(ln, "", "type"), opds_xattr_get(ln, "", "title"), flags, indirect);
}

static int64_t to_int(const char *s) {
  char *e;
  long long v;
  if (!s || !*s) return -1;
  v = strtoll(s, &e, 10);
  return *e || v < 0 ? -1 : (int64_t)v;
}

static opds_status atom_feed(fctx *c, const opds_xnode *root, opds_feed *f) {
  vec entries = {0}, links = {0};
  const char *t;
  opds_status st = OPDS_OK;
  entries.sz = sizeof(opds_entry); links.sz = sizeof(opds_link);
  if (!opds_xis(root, NS_ATOM, "feed")) return opds_fail(c->err, OPDS_FORMAT, "root element is not an Atom feed");
  f->version = 1;
  if (!(t = xchild_text(root, NS_ATOM, "title")) || !*t) { st = opds_fail(c->err, OPDS_FORMAT, "Atom feed without title"); goto done; }
  f->title = arena_strdup(c->a, t);
  f->id = arena_strdup(c->a, (t = xchild_text(root, NS_ATOM, "id")) ? t : "");
  f->updated = arena_strdup(c->a, (t = xchild_text(root, NS_ATOM, "updated")) ? t : "");
  f->total_results = to_int(xchild_text(root, NS_OPENSEARCH, "totalResults"));
  f->items_per_page = to_int(xchild_text(root, NS_OPENSEARCH, "itemsPerPage"));
  f->start_index = to_int(xchild_text(root, NS_OPENSEARCH, "startIndex"));
  for (const opds_xnode *ch = root->first; ch; ch = ch->next) {
    if (opds_xis(ch, NS_ATOM, "link")) {
      if ((st = atom_link(c, ch, &links)) != OPDS_OK) goto done;
      const opds_link *link = (opds_link *)links.p + links.n - 1;
      if (rel_token(link->rel, "http://opds-spec.org/facet")) {
        const char *name = opds_xattr_get(ch, NS_OPDS, "facetGroup");
        const char *active = opds_xattr_get(ch, NS_OPDS, "activeFacet");
        int enabled = active && !strcmp(active, "true");
        int64_t count;
        facet_group *group;
        if (active && strcmp(active, "true") && strcmp(active, "false")) {
          st = opds_fail(c->err, OPDS_FORMAT, "invalid activeFacet value"); goto done;
        }
        if ((st = facet_number(c, opds_xattr_get(ch, "http://purl.org/syndication/thread/1.0", "count"), &count)) != OPDS_OK ||
            (st = facet_new(c, name ? name : "", 1, &group)) != OPDS_OK ||
            (st = facet_choice(c, group, link, enabled, count, 1)) != OPDS_OK) goto done;
      }
    } else if (opds_xis(ch, NS_ATOM, "entry")) {
      opds_entry *e;
      vec elinks = {0}, authors = {0};
      elinks.sz = sizeof(opds_link); authors.sz = sizeof(char *);
      if (entries.n >= c->lim->max_entries) { st = opds_fail(c->err, OPDS_LIMIT, "entry budget (%zu) exceeded", c->lim->max_entries); goto done; }
      if (!(t = xchild_text(ch, NS_ATOM, "title")) || !*t) { st = opds_fail(c->err, OPDS_FORMAT, "Atom entry without title"); goto done; }
      e = (opds_entry *)vec_push(&entries);
      if (!e) { st = OPDS_MEMORY; goto done; }
      e->title = arena_strdup(c->a, t);
      e->id = arena_strdup(c->a, (t = xchild_text(ch, NS_ATOM, "id")) ? t : "");
      e->updated = arena_strdup(c->a, (t = xchild_text(ch, NS_ATOM, "updated")) ? t : "");
      t = xchild_text(ch, NS_ATOM, "summary");
      if (!t) t = xchild_text(ch, NS_ATOM, "content");
      e->summary = t ? arena_strdup(c->a, t) : NULL;
      t = xchild_text2(ch, "identifier"); e->identifier = t ? arena_strdup(c->a, t) : NULL;
      t = xchild_text2(ch, "language"); e->language = t ? arena_strdup(c->a, t) : NULL;
      t = xchild_text2(ch, "publisher"); e->publisher = t ? arena_strdup(c->a, t) : NULL;
      for (const opds_xnode *x = ch->first; x; x = x->next) {
        if (opds_xis(x, NS_ATOM, "author")) {
          const char *nm = xchild_text(x, NS_ATOM, "name");
          if (nm && *nm) { const char **slot = (const char **)vec_push(&authors); if (!slot) { st = OPDS_MEMORY; goto done; } *slot = arena_strdup(c->a, nm); }
        } else if (opds_xis(x, NS_ATOM, "link")) {
          if (elinks.n >= c->lim->max_links_per_entry) { st = opds_fail(c->err, OPDS_LIMIT, "per-entry link budget exceeded"); free(elinks.p); free(authors.p); goto done; }
          if ((st = atom_link(c, x, &elinks)) != OPDS_OK) { free(elinks.p); free(authors.p); goto done; }
        }
      }
      e->author_count = authors.n; e->link_count = elinks.n;
      e->authors = (const char *const *)vec_arena(&authors, c->a);
      e->links = (const opds_link *)vec_arena(&elinks, c->a);
      if (!e->links || !e->authors) { st = OPDS_MEMORY; goto done; }
      e->is_publication = has_acquisition(e->links, e->link_count);
    }
  }
  f->entry_count = entries.n; f->link_count = links.n;
  f->entries = (const opds_entry *)vec_arena(&entries, c->a);
  f->links = (const opds_link *)vec_arena(&links, c->a);
  if (!f->entries || !f->links) return OPDS_MEMORY;
  return OPDS_OK;
done:
  free(entries.p); free(links.p);
  return st;
}

/* ---- OPDS 2 ---- */
static const char *j_text(fctx *c, const opds_jnode *n) {
  if (!n) return NULL;
  if (n->type == OJ_STR) return n->str;
  if (n->type == OJ_NUM) return n->str;
  if (n->type == OJ_ARR && n->first) return j_text(c, n->first);
  if (n->type == OJ_OBJ) { for (opds_jnode *m = n->first; m; m = m->next) if (m->type == OJ_STR) return m->str; }
  return NULL;
}
static const char *j_name(fctx *c, const opds_jnode *n) {
  if (n && n->type == OJ_OBJ) { const char *s = j_text(c, opds_jget(n, "name")); return s; }
  return j_text(c, n);
}
static void j_scan_indirect(const opds_jnode *arr, unsigned *flags, const char **first, int depth) {
  if (!arr || arr->type != OJ_ARR) return;
  for (opds_jnode *m = arr->first; m; m = m->next) {
    const char *t = opds_jstr(opds_jget(m, "type"));
    if (t) { if (!*first) *first = t; if (protected_type(t)) *flags |= OPDS_LINK_PROTECTED; }
    if (depth < 32) j_scan_indirect(opds_jget(m, "child"), flags, first, depth + 1);
  }
}
static opds_status j_link(fctx *c, const opds_jnode *o, vec *links, const char *default_rel) {
  const char *href, *type, *title;
  const opds_jnode *relv, *props;
  char rel[256];
  unsigned flags = 0;
  const char *indirect = NULL;
  if (o->type != OJ_OBJ) return opds_fail(c->err, OPDS_FORMAT, "OPDS2 link is not an object");
  href = opds_jstr(opds_jget(o, "href"));
  if (!href || !*href) return opds_fail(c->err, OPDS_FORMAT, "OPDS2 link without href");
  relv = opds_jget(o, "rel"); rel[0] = 0;
  if (relv && relv->type == OJ_STR) snprintf(rel, sizeof rel, "%s", relv->str);
  else if (relv && relv->type == OJ_ARR) {
    size_t used = 0;
    for (opds_jnode *m = relv->first; m; m = m->next) {
      int w;
      if (m->type != OJ_STR) continue;
      w = snprintf(rel + used, sizeof rel - used, "%s%s", used ? " " : "", m->str);
      if (w < 0 || (size_t)w >= sizeof rel - used) break;
      used += (size_t)w;
    }
  }
  if (!rel[0]) snprintf(rel, sizeof rel, "%s", default_rel);
  type = opds_jstr(opds_jget(o, "type")); title = opds_jstr(opds_jget(o, "title"));
  { opds_jnode *t = opds_jget(o, "templated"); if (t && t->type == OJ_BOOL && t->boolean) flags |= OPDS_LINK_TEMPLATED; }
  props = opds_jget(o, "properties");
  if (props && props->type == OJ_OBJ) {
    const opds_jnode *ia = opds_jget(props, "indirectAcquisition");
    if (ia && ia->type == OJ_ARR && ia->first) { flags |= OPDS_LINK_INDIRECT; j_scan_indirect(ia, &flags, &indirect, 0); }
    if (opds_jget(props, "price")) flags |= OPDS_LINK_PRICED;
  }
  return make_link(c, links, rel, href, c->base, type, title, flags, indirect);
}

static opds_status j_links(fctx *c, const opds_jnode *arr, vec *links, const char *default_rel) {
  if (!arr) return OPDS_OK;
  if (arr->type != OJ_ARR) return opds_fail(c->err, OPDS_FORMAT, "OPDS2 links is not an array");
  for (opds_jnode *m = arr->first; m; m = m->next) {
    opds_status st = j_link(c, m, links, default_rel);
    if (st) return st;
  }
  return OPDS_OK;
}

static opds_status j_facets(fctx *c, const opds_jnode *facets) {
  if (!facets) return OPDS_OK;
  if (facets->type != OJ_ARR) return opds_fail(c->err, OPDS_FORMAT, "OPDS2 facets is not an array");
  for (const opds_jnode *item = facets->first; item; item = item->next) {
    const opds_jnode *metadata = opds_jget(item, "metadata"), *links;
    const opds_jnode *name = opds_jget(metadata, "title");
    const char *title = j_text(c, name);
    facet_group *group;
    opds_status status;
    if (item->type != OJ_OBJ || !metadata || metadata->type != OJ_OBJ || !name ||
        (name->type != OJ_STR && name->type != OJ_OBJ) || !title || !*title)
      return opds_fail(c->err, OPDS_FORMAT, "OPDS2 facet group without title");
    links = opds_jget(item, "links");
    if (!links || links->type != OJ_ARR || !links->first)
      return opds_fail(c->err, OPDS_FORMAT, "OPDS2 facet group without links");
    if ((status = facet_new(c, title, 0, &group)) != OPDS_OK) return status;
    for (const opds_jnode *item_link = links->first; item_link; item_link = item_link->next) {
      vec one = {0}; int64_t count;
      const opds_jnode *properties, *number;
      one.sz = sizeof(opds_link);
      status = j_link(c, item_link, &one, "");
      if (status != OPDS_OK) { free(one.p); return status; }
      properties = opds_jget(item_link, "properties");
      if (properties && properties->type != OJ_OBJ) {
        free(one.p); return opds_fail(c->err, OPDS_FORMAT, "facet properties is not an object");
      }
      number = opds_jget(properties, "numberOfItems");
      if (number && number->type != OJ_NUM) { free(one.p); return opds_fail(c->err, OPDS_FORMAT, "facet count is not an integer"); }
      status = facet_number(c, number ? number->str : NULL, &count);
      if (status == OPDS_OK) {
        const opds_link *link = (const opds_link *)one.p;
        status = facet_choice(c, group, link, rel_token(link->rel, "self"), count, 0);
      }
      free(one.p);
      if (status != OPDS_OK) return status;
    }
  }
  return OPDS_OK;
}

static opds_status j_entries(fctx *c, const opds_jnode *nav, const opds_jnode *pubs, const char *group, vec *entries) {
  if (nav) {
    if (nav->type != OJ_ARR) return opds_fail(c->err, OPDS_FORMAT, "OPDS2 navigation is not an array");
    for (opds_jnode *m = nav->first; m; m = m->next) {
      opds_entry *e; vec l = {0}; opds_status st;
      l.sz = sizeof(opds_link);
      if (entries->n >= c->lim->max_entries) return opds_fail(c->err, OPDS_LIMIT, "entry budget (%zu) exceeded", c->lim->max_entries);
      if ((st = j_link(c, m, &l, "subsection")) != OPDS_OK) { free(l.p); return st; }
      e = (opds_entry *)vec_push(entries);
      if (!e) { free(l.p); return OPDS_MEMORY; }
      e->title = ((opds_link *)l.p)->title ? ((opds_link *)l.p)->title : "";
      e->id = ""; e->updated = ""; e->group = group; e->authors = NULL;
      e->link_count = l.n; e->links = (const opds_link *)vec_arena(&l, c->a);
      if (!e->links) return OPDS_MEMORY;
      e->is_publication = has_acquisition(e->links, e->link_count);
    }
  }
  if (pubs) {
    if (pubs->type != OJ_ARR) return opds_fail(c->err, OPDS_FORMAT, "OPDS2 publications is not an array");
    for (opds_jnode *m = pubs->first; m; m = m->next) {
      const opds_jnode *md = opds_jget(m, "metadata"), *au;
      opds_entry *e; vec l = {0}, authors = {0}; opds_status st; const char *t;
      l.sz = sizeof(opds_link); authors.sz = sizeof(char *);
      if (entries->n >= c->lim->max_entries) return opds_fail(c->err, OPDS_LIMIT, "entry budget (%zu) exceeded", c->lim->max_entries);
      if (m->type != OJ_OBJ || !md || md->type != OJ_OBJ) return opds_fail(c->err, OPDS_FORMAT, "publication without metadata");
      if (!(t = j_text(c, opds_jget(md, "title"))) || !*t) return opds_fail(c->err, OPDS_FORMAT, "publication without title");
      e = (opds_entry *)vec_push(entries);
      if (!e) return OPDS_MEMORY;
      e->title = arena_strdup(c->a, t);
      t = opds_jstr(opds_jget(md, "identifier")); if (!t) t = opds_jstr(opds_jget(md, "@id"));
      e->id = arena_strdup(c->a, t ? t : "");
      t = opds_jstr(opds_jget(md, "modified")); e->updated = arena_strdup(c->a, t ? t : "");
      t = j_text(c, opds_jget(md, "description")); e->summary = t ? arena_strdup(c->a, t) : NULL;
      e->identifier = e->id[0] ? e->id : NULL;
      t = j_text(c, opds_jget(md, "language")); e->language = t ? arena_strdup(c->a, t) : NULL;
      t = j_name(c, opds_jget(md, "publisher")); e->publisher = t ? arena_strdup(c->a, t) : NULL;
      e->group = group;
      au = opds_jget(md, "author");
      if (au && au->type == OJ_ARR) {
        for (opds_jnode *a = au->first; a; a = a->next) {
          const char *nm = j_name(c, a);
          if (nm && *nm) { const char **s = (const char **)vec_push(&authors); if (!s) return OPDS_MEMORY; *s = arena_strdup(c->a, nm); }
        }
      } else if (au) {
        const char *nm = j_name(c, au);
        if (nm && *nm) { const char **s = (const char **)vec_push(&authors); if (!s) return OPDS_MEMORY; *s = arena_strdup(c->a, nm); }
      }
      if ((st = j_links(c, opds_jget(m, "links"), &l, "")) != OPDS_OK) { free(l.p); free(authors.p); return st; }
      if (l.n > c->lim->max_links_per_entry) { free(l.p); free(authors.p); return opds_fail(c->err, OPDS_LIMIT, "per-entry link budget exceeded"); }
      if ((st = j_links(c, opds_jget(m, "images"), &l, "http://opds-spec.org/image")) != OPDS_OK) { free(l.p); free(authors.p); return st; }
      e->author_count = authors.n; e->link_count = l.n;
      e->authors = (const char *const *)vec_arena(&authors, c->a);
      e->links = (const opds_link *)vec_arena(&l, c->a);
      if (!e->links || !e->authors) return OPDS_MEMORY;
      e->is_publication = has_acquisition(e->links, e->link_count);
    }
  }
  return OPDS_OK;
}

static opds_status json_feed(fctx *c, const opds_jnode *root, opds_feed *f) {
  vec entries = {0}, links = {0};
  const opds_jnode *md = opds_jget(root, "metadata"), *g;
  const char *t;
  opds_status st;
  entries.sz = sizeof(opds_entry); links.sz = sizeof(opds_link);
  if (root->type != OJ_OBJ || !md || md->type != OJ_OBJ) return opds_fail(c->err, OPDS_FORMAT, "OPDS2 feed without metadata");
  if (!opds_jget(root, "links") && !opds_jget(root, "navigation") && !opds_jget(root, "publications") && !opds_jget(root, "groups") && !opds_jget(root, "facets"))
    return opds_fail(c->err, OPDS_FORMAT, "JSON document is not an OPDS2 feed");
  f->version = 2;
  if (!(t = j_text(c, opds_jget(md, "title"))) || !*t) return opds_fail(c->err, OPDS_FORMAT, "OPDS2 feed without title");
  f->title = arena_strdup(c->a, t);
  t = opds_jstr(opds_jget(md, "identifier")); if (!t) t = opds_jstr(opds_jget(md, "@id"));
  f->id = arena_strdup(c->a, t ? t : "");
  t = opds_jstr(opds_jget(md, "modified")); f->updated = arena_strdup(c->a, t ? t : "");
  { opds_jnode *v;
    v = opds_jget(md, "numberOfItems"); if (v && v->type == OJ_NUM && v->num >= 0) f->total_results = (int64_t)v->num;
    v = opds_jget(md, "itemsPerPage"); if (v && v->type == OJ_NUM && v->num >= 0) f->items_per_page = (int64_t)v->num;
    v = opds_jget(md, "currentPage"); if (v && v->type == OJ_NUM && v->num >= 0) f->current_page = (int64_t)v->num;
  }
  if ((st = j_links(c, opds_jget(root, "links"), &links, "")) != OPDS_OK) goto done;
  if ((st = j_entries(c, opds_jget(root, "navigation"), opds_jget(root, "publications"), NULL, &entries)) != OPDS_OK) goto done;
  g = opds_jget(root, "groups");
  if (g) {
    if (g->type != OJ_ARR) { st = opds_fail(c->err, OPDS_FORMAT, "OPDS2 groups is not an array"); goto done; }
    for (opds_jnode *m = g->first; m; m = m->next) {
      const char *gt = j_text(c, opds_jget(opds_jget(m, "metadata"), "title"));
      if ((st = j_entries(c, opds_jget(m, "navigation"), opds_jget(m, "publications"), gt ? arena_strdup(c->a, gt) : NULL, &entries)) != OPDS_OK) goto done;
    }
  }
  if ((st = j_facets(c, opds_jget(root, "facets"))) != OPDS_OK) goto done;
  f->entry_count = entries.n; f->link_count = links.n;
  f->entries = (const opds_entry *)vec_arena(&entries, c->a);
  f->links = (const opds_link *)vec_arena(&links, c->a);
  return f->entries && f->links ? OPDS_OK : OPDS_MEMORY;
done:
  free(entries.p); free(links.p);
  return st;
}

/* ---- public ---- */
void opds_feed_free(opds_feed *f) {
  if (!f) return;
  arena_free(f->arena);
  memset(f, 0, sizeof *f);
}

opds_status opds_feed_parse(const void *data, size_t size, const char *content_type, const char *base_url,
                            const opds_limits *limits, opds_feed *out, opds_error *error) {
  opds_limits lim;
  const char *d = (const char *)data;
  size_t i = 0;
  struct opds_arena *a;
  fctx c = {0};
  opds_status st;
  if (!out) return opds_fail(error, OPDS_ARGUMENT, "feed output required");
  memset(out, 0, sizeof *out);
  if (!data) return opds_fail(error, OPDS_ARGUMENT, "feed data required");
  if (limits) lim = *limits; else opds_limits_defaults(&lim);
  if (size > lim.max_feed_bytes) return opds_fail(error, OPDS_LIMIT, "feed larger than %zu bytes", lim.max_feed_bytes);
  if (size >= 3 && !memcmp(d, "\xEF\xBB\xBF", 3)) i = 3;
  while (i < size && (d[i] == ' ' || d[i] == '\t' || d[i] == '\r' || d[i] == '\n')) i++;
  if (i >= size || (d[i] != '<' && d[i] != '{')) return opds_fail(error, OPDS_FORMAT, "document is neither XML nor JSON");
  a = arena_new();
  if (!a) return opds_fail(error, OPDS_MEMORY, "out of memory");
  out->arena = a;
  out->total_results = out->items_per_page = out->start_index = out->current_page = -1;
  out->base_url = base_url ? arena_strdup(a, base_url) : NULL;
  c.a = a; c.lim = &lim; c.base = base_url; c.err = error;
  if (content_type) {
    char m[96];
    opds_media_type(content_type, m, sizeof m);
    if (strstr(m, "json")) out->declared_type_mismatch = d[i] != '{';
    else if (strstr(m, "xml")) out->declared_type_mismatch = d[i] != '<';
  }
  if (d[i] == '<') {
    opds_xnode *root;
    st = opds_xml_parse(a, d, size, &lim, &root, error);
    if (st == OPDS_OK) st = atom_feed(&c, root, out);
  } else {
    opds_jnode *root;
    st = opds_json_parse(a, d, size, &lim, &root, error);
    if (st == OPDS_OK) st = json_feed(&c, root, out);
  }
  if (st == OPDS_OK) st = facets_finish(&c);
  facets_release(&c);
  if (st != OPDS_OK) { if (error && error->code == OPDS_OK) error->code = st; opds_feed_free(out); }
  return st;
}

const opds_facet *opds_feed_facets(const opds_feed *feed, size_t *count) {
  size_t size = feed && feed->arena ? feed->arena->facet_count : 0;
  if (count) *count = size;
  return size ? feed->arena->facets : NULL;
}

const opds_link *opds_feed_find(const opds_feed *f, opds_rel_kind kind) {
  for (size_t i = 0; i < f->link_count; i++) if (f->links[i].kind == kind) return &f->links[i];
  return NULL;
}

const opds_link *opds_entry_acquisition(const opds_entry *e, const char *media_type) {
  char want[96], got[96];
  if (media_type) opds_media_type(media_type, want, sizeof want);
  for (size_t i = 0; i < e->link_count; i++) {
    const opds_link *l = &e->links[i];
    if (l->acq == OPDS_ACQ_NONE) continue;
    if (media_type) {
      if (!l->type) continue;
      opds_media_type(l->type, got, sizeof got);
      if (!streq_ci(got, want)) continue;
      return l;
    }
    if (l->acq == OPDS_ACQ_SAMPLE) continue;
    return l;
  }
  return NULL;
}

opds_status opds_link_acquirable(const opds_link *l, opds_error *error) {
  if (l->acq == OPDS_ACQ_BORROW || l->acq == OPDS_ACQ_BUY || l->acq == OPDS_ACQ_SUBSCRIBE)
    return opds_fail(error, OPDS_NEEDS_HOST, "borrow/purchase/subscription flows need a host capability");
  if (l->flags & OPDS_LINK_PRICED) return opds_fail(error, OPDS_NEEDS_HOST, "priced acquisition needs a host payment capability");
  if (l->flags & OPDS_LINK_PROTECTED) return opds_fail(error, OPDS_NEEDS_HOST, "DRM/license acquisition needs a host capability");
  return OPDS_OK;
}

opds_status opds_opensearch_template(const void *data, size_t size, const opds_limits *limits,
                                     char *out, size_t cap, opds_error *error) {
  opds_limits lim;
  struct opds_arena *a = arena_new();
  opds_xnode *root;
  opds_status st;
  const char *best = NULL;
  if (limits) lim = *limits; else opds_limits_defaults(&lim);
  if (!a) return opds_fail(error, OPDS_MEMORY, "out of memory");
  if (size > lim.max_feed_bytes) { arena_free(a); return opds_fail(error, OPDS_LIMIT, "description too large"); }
  st = opds_xml_parse(a, (const char *)data, size, &lim, &root, error);
  if (st) { arena_free(a); return st; }
  if (strcmp(root->name, "OpenSearchDescription")) { arena_free(a); return opds_fail(error, OPDS_FORMAT, "not an OpenSearch description"); }
  for (const opds_xnode *u = root->first; u; u = u->next) {
    const char *type, *tmpl;
    char m[96];
    if (strcmp(u->name, "Url")) continue;
    type = opds_xattr_get(u, "", "type"); tmpl = opds_xattr_get(u, "", "template");
    if (!type || !tmpl) continue;
    opds_media_type(type, m, sizeof m);
    if (strstr(m, "atom+xml") || strstr(m, "opds+json")) { best = tmpl; break; }
  }
  if (!best) { arena_free(a); return opds_fail(error, OPDS_UNSUPPORTED, "description offers no Atom/OPDS Url template"); }
  if (strlen(best) >= cap) { arena_free(a); return opds_fail(error, OPDS_LIMIT, "template too long"); }
  strcpy(out, best);
  arena_free(a);
  return OPDS_OK;
}
