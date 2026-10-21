/* SPDX-License-Identifier: MIT */
#include "document_internal.h"

#define ANCHOR_QUOTE_LIMIT ((size_t)65536)
#define ANCHOR_CONTEXT_BYTES ((size_t)128)
#define ANCHOR_CONTEXT_SCALARS 32

static int text_boundary(const char *text,size_t size,size_t at) {
  return at<=size && (at==size || ((unsigned char)text[at]&0xc0)!=0x80);
}
static int boundary(const exr_document *d,size_t at) {
  return at<=d->size && (at==d->size || (exr_doc_byte(d,at)&0xc0)!=0x80);
}
static char *quote(const exr_document *d,size_t start,size_t size) {
  char *copy=malloc(size+1);
  if(!copy) return NULL;
  if(!exr_doc_copy(d,start,size,copy)) { free(copy);return NULL; }
  copy[size]=0;return copy;
}
static int equal(const exr_document *d,size_t at,const char *wanted,size_t size) {
  size_t done=0;
  while(done<size) {
    size_t available,chunk;const char *text=exr_doc_span(d,at+done,&available);
    if(!text || !available) return 0;
    chunk=size-done<available ? size-done : available;
    if(memcmp(text,wanted+done,chunk)) return 0;
    done+=chunk;
  }
  return 1;
}

static exr_status selector_string(const char *s, size_t limit, size_t scalars, exr_error *e) {
  size_t n = 0, at = 0, count = 0;
  uint32_t cp;
  if (!s)
    return EXR_OK;
  while (n <= limit && s[n])
    n++;
  if (n > limit)
    return exr_fail(e, EXR_LIMIT, "Anchor selector exceeds its size limit");
  while (at < n) {
    if (!exr_next(s, n, &at, &cp))
      return exr_fail(e, EXR_ENCODING, "Anchor selector is not valid UTF-8");
    if (++count > scalars)
      return exr_fail(e, EXR_LIMIT, "Anchor context exceeds 32 Unicode scalars");
  }
  return EXR_OK;
}

exr_status exr_anchor_validate(const exr_anchor *a, exr_error *e) {
  exr_status status;
  if (!a || a->start > a->end || ((a->start == SIZE_MAX) != (a->end == SIZE_MAX)))
    return exr_fail(e, EXR_ARGUMENT, "Invalid anchor range");
  if ((status = selector_string(a->exact, ANCHOR_QUOTE_LIMIT, SIZE_MAX, e)) != EXR_OK ||
      (status = selector_string(a->prefix, ANCHOR_CONTEXT_BYTES, ANCHOR_CONTEXT_SCALARS, e)) != EXR_OK ||
      (status = selector_string(a->suffix, ANCHOR_CONTEXT_BYTES, ANCHOR_CONTEXT_SCALARS, e)) != EXR_OK ||
      (status = selector_string(a->chapter, 2046, SIZE_MAX, e)) != EXR_OK)
    return status;
  if (a->exact && a->start != SIZE_MAX && a->end - a->start != strlen(a->exact))
    return exr_fail(e, EXR_ARGUMENT, "Anchor range and quote length disagree");
  return EXR_OK;
}

void exr_anchor_free(exr_anchor *a) {
  if (!a)
    return;
  free(a->exact);
  free(a->prefix);
  free(a->suffix);
  free(a->chapter);
  memset(a, 0, sizeof(*a));
}

static int chapter_range(const exr_document *d, size_t chapter, size_t *start, size_t *end) {
  const exr_chapter *c = &d->chapters[chapter];
  const exr_node *root;
  if (c->root >= d->node_count)
    return 0;
  root = (const exr_node[]){exr_doc_node(d,c->root)};
  if (root->start > root->end || root->end > d->size)
    return 0;
  *start = root->start;
  *end = root->end;
  return 1;
}

exr_status exr_anchor_create(const exr_document *d, size_t start, size_t end,
                             exr_anchor *out, exr_error *e) {
  exr_anchor a = {0};
  size_t lo = 0, hi, left, right, i;
  const char *chapter = NULL;
  uint32_t cp;
  unsigned count;
  if (!out)
    return exr_fail(e, EXR_ARGUMENT, "Missing anchor output");
  memset(out, 0, sizeof(*out));
  if (!d || start > end || !boundary(d, start) || !boundary(d, end))
    return exr_fail(e, EXR_ARGUMENT, "Selection must lie on UTF-8 boundaries inside the document");
  if (end - start > ANCHOR_QUOTE_LIMIT)
    return exr_fail(e, EXR_LIMIT, "Anchor quote exceeds 64 KiB");
  hi = d->size;
  for (i = 0; i < d->chapter_count; i++) {
    size_t begin, finish;
    if (chapter_range(d, i, &begin, &finish) && start >= begin && end <= finish &&
        (start < finish || (start == end && finish == d->size)) &&
        d->chapters[i].path && d->chapters[i].path[0]) {
      lo = begin;
      hi = finish;
      chapter = d->chapters[i].path;
      break;
    }
  }
  left = start;
  for (count = 0; count < ANCHOR_CONTEXT_SCALARS && left > lo; count++) {
    left--;
    while (left > lo && (exr_doc_byte(d,left) & 0xc0) == 0x80)
      left--;
  }
  right = end;
  for (count = 0; count < ANCHOR_CONTEXT_SCALARS && right < hi; count++)
    if (!exr_doc_next(d, hi, &right, &cp))
      return exr_fail(e, EXR_ENCODING, "Invalid document text");
  a.start = start;
  a.end = end;
  a.exact = quote(d, start, end - start);
  a.prefix = quote(d, left, start - left);
  a.suffix = quote(d, end, right - end);
  a.chapter = chapter ? exr_copy(chapter, strlen(chapter)) : NULL;
  if (!a.exact || !a.prefix || !a.suffix || (chapter && !a.chapter)) {
    exr_anchor_free(&a);
    return exr_fail(e, EXR_MEMORY, "Anchor allocation failed");
  }
  *out = a;
  return EXR_OK;
}

typedef struct {
  const exr_document *document;
  const char *exact,*prefix_text,*suffix_text;
  size_t size;
  const exr_control *control;
  size_t lo, hi, quote, prefix, suffix, best_start;
  unsigned best_score;
  int tied;
} anchor_search;

static void candidate(anchor_search *s, size_t at) {
  size_t end;
  unsigned score = 0;
  if (at < s->lo || at > s->hi || s->quote > s->hi - at)
    return;
  end = at + s->quote;
  if (!boundary(s->document,at) || !boundary(s->document,end))
    return;
  if (s->prefix ? s->prefix <= at - s->lo &&
                     equal(s->document,at-s->prefix,s->prefix_text,s->prefix)
                : at == s->lo)
    score++;
  if (s->suffix ? s->suffix <= s->hi - end &&
                     equal(s->document,end,s->suffix_text,s->suffix)
                : end == s->hi)
    score++;
  if (!score)
    return;
  if (score > s->best_score) {
    s->best_score = score;
    s->best_start = at;
    s->tied = 0;
  } else if (score == s->best_score && at != s->best_start)
    s->tied = 1;
}

static exr_status search(anchor_search *s, const char *pattern, size_t n, int after,
                           exr_error *e) {
  size_t i, j, *failure;
  if (n > s->hi - s->lo)
    return EXR_OK;
  failure = calloc(n, sizeof(*failure));
  if (!failure)
    return exr_fail(e, EXR_MEMORY, "Anchor search allocation failed");
  /* KMP keeps long/repetitive quote searches linear in the document size. */
  for (i = 1, j = 0; i < n; i++) {
    if(!(i&4095) && exr_control_cancel(s->control,e)!=EXR_OK) { free(failure); return EXR_CANCELLED; }
    while (j && pattern[i] != pattern[j])
      j = failure[j - 1];
    if (pattern[i] == pattern[j])
      j++;
    failure[i] = j;
  }
  for (i = s->lo, j = 0; i < s->hi; i++) {
    size_t available;const char *span=exr_doc_span(s->document,i,&available);char value;
    if(!span || !available) { free(failure);return exr_fail(e,EXR_FORMAT,"Anchor source is unavailable"); }
    value=*span;
    if(!((i-s->lo)&4095) && exr_control_cancel(s->control,e)!=EXR_OK) { free(failure); return EXR_CANCELLED; }
    while (j && value != pattern[j])
      j = failure[j - 1];
    if (value == pattern[j])
      j++;
    if (j == n) {
      candidate(s, after ? i + 1 : i + 1 - n);
      j = failure[j - 1];
    }
  }
  free(failure);
  return EXR_OK;
}

static exr_status search_scope(anchor_search *s, exr_error *e) {
  exr_status status;
  if (s->quote)
    return search(s, s->exact, s->quote, 0, e);
  /* A point can be recovered from either adjacent context; equal candidates
     from the two searches are counted once. */
  if (s->prefix && (status = search(s, s->prefix_text, s->prefix, 1, e)) != EXR_OK)
    return status;
  if (s->suffix && (status = search(s, s->suffix_text, s->suffix, 0, e)) != EXR_OK)
    return status;
  if (!s->prefix && s->suffix)
    candidate(s, s->lo);
  if (!s->suffix && s->prefix)
    candidate(s, s->hi);
  if (!s->prefix && !s->suffix && s->lo == s->hi)
    candidate(s, s->lo);
  return EXR_OK;
}

exr_status exr_anchor_resolve_ex(const exr_document *d, const exr_anchor *a,const exr_control *control,
                                 exr_anchor_match *match, exr_error *e) {
  anchor_search s = {0};
  exr_status status;
  size_t i;
  if (!match)
    return exr_fail(e, EXR_ARGUMENT, "Missing anchor match output");
  match->state = EXR_ANCHOR_MISSING;
  match->start = match->end = SIZE_MAX;
  if (!d || !a)
    return exr_fail(e, EXR_ARGUMENT, "Missing document or anchor");
  if ((status = exr_anchor_validate(a, e)) != EXR_OK)
    return status;
  status=exr_control_cancel(control,e); if(status!=EXR_OK) return status;
  s.control=control;
  if (!a->exact) {
    match->state = EXR_ANCHOR_LEGACY;
    return exr_fail(e,EXR_OK,"");
  }
  s.document=d; s.size=d->size; s.exact=a->exact; s.prefix_text=a->prefix; s.suffix_text=a->suffix;
  s.hi = d->size;
  s.quote = strlen(a->exact);
  s.prefix = a->prefix ? strlen(a->prefix) : 0;
  s.suffix = a->suffix ? strlen(a->suffix) : 0;
  if (a->chapter && a->chapter[0]) {
    /* Repeated EPUB spine entries can share a path. Compare every occurrence,
       preserving the best score and ties across their independent text ranges. */
    for (i = 0; i < d->chapter_count; i++)
      if (d->chapters[i].path && !strcmp(d->chapters[i].path, a->chapter) &&
          chapter_range(d, i, &s.lo, &s.hi) &&
          (status = search_scope(&s, e)) != EXR_OK)
        return status;
  } else if ((status = search_scope(&s, e)) != EXR_OK)
    return status;
  if (s.best_score) {
    match->state = s.tied ? EXR_ANCHOR_AMBIGUOUS : EXR_ANCHOR_FOUND;
    if (!s.tied) {
      match->start = s.best_start;
      match->end = s.best_start + s.quote;
    }
  }
  return exr_fail(e,EXR_OK,"");
}

exr_status exr_anchor_resolve(const exr_document *d,const exr_anchor *a,exr_anchor_match *match,exr_error *e) {
  return exr_anchor_resolve_ex(d,a,NULL,match,e);
}

void exr_fixed_anchor_free(exr_fixed_anchor *a) {
  if(a) { free(a->page_id); free(a->exact); free(a->prefix); free(a->suffix); memset(a,0,sizeof(*a)); }
}
static exr_status fixed_selector(const char *text,size_t size,size_t limit,size_t maximum,exr_error *e) {
  size_t at=0,count=0; uint32_t cp;
  if((!text && size) || size>limit) return exr_fail(e,size>limit ? EXR_LIMIT : EXR_ARGUMENT,"Invalid fixed anchor selector size");
  while(at<size) {
    if(!exr_next(text,size,&at,&cp)) return exr_fail(e,EXR_ENCODING,"Invalid fixed anchor UTF-8");
    if(++count>maximum) return exr_fail(e,EXR_LIMIT,"Fixed anchor context exceeds 32 Unicode scalars");
  }
  return EXR_OK;
}
static exr_status fixed_page_id(const char *id,exr_error *e) {
  if(!id || !*id) return exr_fail(e,EXR_ARGUMENT,"Missing fixed anchor page ID");
  return selector_string(id,65536,SIZE_MAX,e);
}
exr_status exr_fixed_anchor_create(const char *page_id,const exr_fixed_text *snapshot,size_t start,size_t end,
                                    exr_fixed_anchor *out,exr_error *e) {
  exr_fixed_anchor a={0}; const char *text; size_t size,left,right; unsigned count; uint32_t cp; exr_status status;
  if(!out) return exr_fail(e,EXR_ARGUMENT,"Missing fixed anchor output");
  memset(out,0,sizeof(*out)); text=exr_fixed_text_string(snapshot,&size);
  if(!text || start>end || !text_boundary(text,size,start) || !text_boundary(text,size,end)) return exr_fail(e,EXR_ARGUMENT,"Invalid fixed anchor range");
  if(end-start>ANCHOR_QUOTE_LIMIT) return exr_fail(e,EXR_LIMIT,"Fixed anchor quote exceeds 64 KiB");
  status=fixed_page_id(page_id,e); if(status!=EXR_OK) return status;
  left=start; right=end;
  for(count=0;count<ANCHOR_CONTEXT_SCALARS && left;count++) { left--; while(left && ((unsigned char)text[left]&0xc0)==0x80) left--; }
  for(count=0;count<ANCHOR_CONTEXT_SCALARS && right<size;count++) exr_next(text,size,&right,&cp);
  a.start=start; a.end=end; a.exact_size=end-start; a.prefix_size=start-left; a.suffix_size=right-end;
  a.page_id=exr_copy(page_id,strlen(page_id)); a.exact=exr_copy(text+start,a.exact_size);
  a.prefix=exr_copy(text+left,a.prefix_size); a.suffix=exr_copy(text+end,a.suffix_size);
  if(!a.page_id || !a.exact || !a.prefix || !a.suffix) { exr_fixed_anchor_free(&a); return exr_fail(e,EXR_MEMORY,"Fixed anchor allocation failed"); }
  *out=a; return exr_fail(e,EXR_OK,"");
}
exr_status exr_fixed_anchor_validate(const exr_fixed_anchor *a,exr_error *e) {
  exr_status status;
  if(!a || !a->exact || a->start>a->end || ((a->start==SIZE_MAX)!=(a->end==SIZE_MAX)) ||
     (a->start!=SIZE_MAX && a->end-a->start!=a->exact_size)) return exr_fail(e,EXR_ARGUMENT,"Invalid fixed anchor selector");
  if((status=fixed_page_id(a->page_id,e))!=EXR_OK ||
     (status=fixed_selector(a->exact,a->exact_size,ANCHOR_QUOTE_LIMIT,SIZE_MAX,e))!=EXR_OK ||
     (status=fixed_selector(a->prefix,a->prefix_size,ANCHOR_CONTEXT_BYTES,ANCHOR_CONTEXT_SCALARS,e))!=EXR_OK ||
     (status=fixed_selector(a->suffix,a->suffix_size,ANCHOR_CONTEXT_BYTES,ANCHOR_CONTEXT_SCALARS,e))!=EXR_OK) return status;
  return exr_fail(e,EXR_OK,"");
}
exr_status exr_fixed_anchor_resolve(const char *page_id,const exr_fixed_text *snapshot,const exr_fixed_anchor *a,
                                     const exr_control *control,exr_anchor_match *match,exr_error *e) {
  anchor_search s={0}; exr_document view={0}; exr_status status;
  if(!match) return exr_fail(e,EXR_ARGUMENT,"Missing fixed anchor match output");
  match->state=EXR_ANCHOR_MISSING; match->start=match->end=SIZE_MAX;
  if(!snapshot) return exr_fail(e,EXR_ARGUMENT,"Missing fixed text snapshot");
  if((status=fixed_page_id(page_id,e))!=EXR_OK || (status=exr_fixed_anchor_validate(a,e))!=EXR_OK) return status;
  status=exr_control_cancel(control,e); if(status!=EXR_OK) return status;
  if(strcmp(page_id,a->page_id)) return exr_fail(e,EXR_OK,"");
  view.text=(char *)exr_fixed_text_string(snapshot,&s.size);view.size=s.size;
  s.document=&view;s.hi=s.size;s.control=control;
  s.exact=a->exact; s.prefix_text=a->prefix; s.suffix_text=a->suffix;
  s.quote=a->exact_size; s.prefix=a->prefix_size; s.suffix=a->suffix_size;
  status=search_scope(&s,e); if(status!=EXR_OK) return status;
  if(s.best_score) {
    match->state=s.tied ? EXR_ANCHOR_AMBIGUOUS : EXR_ANCHOR_FOUND;
    if(!s.tied) { match->start=s.best_start; match->end=s.best_start+s.quote; }
  }
  return exr_fail(e,EXR_OK,"");
}
