/* SPDX-License-Identifier: MIT */
#ifndef EXR_GLYPH_ATLAS_INTERNAL_H
#define EXR_GLYPH_ATLAS_INTERNAL_H
#include "vector_internal.h"
/* PDF font dictionary IDs are stable within their owning document. Host fonts
   use an operation-local scope, removed before their bytes may change.
   Exact affine coefficients/residual phases refine the F26Dot6/four-phase key:
   rounding an arbitrary PDF transform to quarter pixels changes coverage. */
typedef struct {
  size_t face;
  uintptr_t scope;
  uint32_t glyph,character;
  int64_t size;
  unsigned phase,flags;
  double matrix[6];
} exr_atlas_key;
typedef struct exr_atlas_entry {
  struct exr_atlas_entry *previous,*next,*hash_next;
  exr_atlas_key key;
  exr_bitmap mask;
  int left,top;
  size_t bytes,work;
  unsigned bucket;
} exr_atlas_entry;
typedef struct exr_glyph_atlas {
  exr_atlas_entry *buckets[1024],*first,*last;
  size_t bytes,count,byte_limit,entry_limit,hits,misses,evictions;
  unsigned initialized;
} exr_glyph_atlas;
static inline size_t exr_atlas_limit(const char *name,size_t fallback,size_t maximum) {
  const char *s=getenv(name); char *end; unsigned long long n;
  if(!s || !*s || *s<'0' || *s>'9') return fallback;
  n=strtoull(s,&end,10);
  return *end || n>maximum ? fallback : (size_t)n;
}
static inline size_t exr_atlas_budget(exr_glyph_atlas *a,size_t pixels) {
  size_t limit;
  if(!a->initialized) {
    a->entry_limit=exr_atlas_limit("EXR_GLYPH_ATLAS_ENTRIES",4096,1048576);
    a->byte_limit=exr_atlas_limit("EXR_GLYPH_ATLAS_BYTES",64u*1024u*1024u,64u*1024u*1024u);
    a->initialized=1;
  }
  /* Four page masks, a 1 MiB floor, and the configured ceiling, including the
     hash table and entry metadata. No allocation reserves the entire budget. */
  limit=pixels>16u*1024u*1024u ? 64u*1024u*1024u : pixels*4;
  if(limit<1024u*1024u) limit=1024u*1024u;
  if(limit>a->byte_limit) limit=a->byte_limit;
  return limit>sizeof(*a) ? limit-sizeof(*a) : 0;
}
static inline unsigned exr_atlas_bucket(const exr_atlas_key *key) {
  uint64_t h=UINT64_C(14695981039346656037);size_t i;
  h=(h^key->face)*UINT64_C(1099511628211);
  h=(h^key->scope)*UINT64_C(1099511628211);
  h=(h^key->character)*UINT64_C(1099511628211);
  h=(h^(uint64_t)key->size)*UINT64_C(1099511628211);
  h=(h^key->phase^key->flags)*UINT64_C(1099511628211);
  for(i=0;i<6;i++) {
    uint64_t bits;double v=key->matrix[i]==0 ? 0 : key->matrix[i];
    memcpy(&bits,&v,sizeof(bits));h=(h^bits)*UINT64_C(1099511628211);
  }
  return (unsigned)(h^(h>>32))&1023u;
}
static inline int exr_atlas_equal(const exr_atlas_key *a,const exr_atlas_key *b) {
  size_t i;
  /* A PDF font's character->GID mapping is immutable. A UINT32_MAX query can
     recover the resolved GID from the entry before consulting FreeType; raw
     CID CFF mapping would otherwise load an outline even on an atlas hit. */
  if(a->face!=b->face || a->scope!=b->scope || (b->glyph!=UINT32_MAX && a->glyph!=b->glyph) || a->character!=b->character ||
     a->size!=b->size || a->phase!=b->phase || a->flags!=b->flags) return 0;
  for(i=0;i<6;i++) if(a->matrix[i]!=b->matrix[i]) return 0;
  return 1;
}
static inline void exr_atlas_unlink(exr_glyph_atlas *a,exr_atlas_entry *e) {
  if(e->previous) e->previous->next=e->next;else a->first=e->next;
  if(e->next) e->next->previous=e->previous;else a->last=e->previous;
}
static inline void exr_atlas_front(exr_glyph_atlas *a,exr_atlas_entry *e) {
  e->previous=NULL;e->next=a->first;
  if(a->first) a->first->previous=e;else a->last=e;
  a->first=e;
}
static inline void exr_atlas_remove(exr_glyph_atlas *a,exr_atlas_entry *e) {
  exr_atlas_entry **link=&a->buckets[e->bucket];
  while(*link!=e) link=&(*link)->hash_next;
  *link=e->hash_next;exr_atlas_unlink(a,e);a->bytes-=e->bytes;a->count--;free(e);
}
static inline void exr_atlas_evict(exr_glyph_atlas *a) {
  exr_atlas_remove(a,a->last);a->evictions++;
}
static inline void exr_atlas_clear_scope(exr_glyph_atlas *a,uintptr_t scope) {
  exr_atlas_entry *e=a->first,*next;
  while(e) { next=e->next;if(e->key.scope==scope) exr_atlas_remove(a,e);e=next; }
}
static inline void exr_atlas_bound(exr_glyph_atlas *a,size_t pixels) {
  size_t limit=exr_atlas_budget(a,pixels);
  while(a->last && (a->bytes>limit || a->count>a->entry_limit)) exr_atlas_evict(a);
}
static inline exr_atlas_entry *exr_atlas_find(exr_glyph_atlas *a,const exr_atlas_key *key) {
  exr_atlas_entry *e;
  for(e=a->buckets[exr_atlas_bucket(key)];e;e=e->hash_next) if(exr_atlas_equal(&e->key,key)) {
    a->hits++;exr_atlas_unlink(a,e);exr_atlas_front(a,e);return e;
  }
  a->misses++;return NULL;
}
static inline exr_atlas_entry *exr_atlas_store(exr_glyph_atlas *a,const exr_atlas_key *key,
    const exr_bitmap *mask,int left,int top,size_t work,size_t pixels) {
  size_t payload=(size_t)mask->width*mask->height,bytes=sizeof(exr_atlas_entry)+payload;
  size_t limit=exr_atlas_budget(a,pixels);
  exr_atlas_entry *e;unsigned y;
  if(!a->entry_limit || bytes>limit) return NULL;
  /* Evict before allocating: even transient owned entries obey the ceiling. */
  while(a->last && (a->count>=a->entry_limit || a->bytes>limit-bytes)) exr_atlas_evict(a);
  e=calloc(1,bytes);if(!e) return NULL;
  e->key=*key;e->bytes=bytes;e->work=work;e->left=left;e->top=top;e->bucket=exr_atlas_bucket(key);
  e->mask=*mask;e->mask.stride=mask->width;e->mask.pixels=(unsigned char *)(e+1);
  for(y=0;y<mask->height;y++) memcpy(e->mask.pixels+(size_t)y*mask->width,mask->pixels+(size_t)y*mask->stride,mask->width);
  e->hash_next=a->buckets[e->bucket];a->buckets[e->bucket]=e;exr_atlas_front(a,e);
  a->bytes+=bytes;a->count++;return e;
}
static inline void exr_atlas_clear(exr_glyph_atlas *a) {
  while(a->last) exr_atlas_evict(a);
}
#endif
