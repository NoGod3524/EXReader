/* SPDX-License-Identifier: MIT */
#ifndef EXR_BUFFER_POOL_INTERNAL_H
#define EXR_BUFFER_POOL_INTERNAL_H
#include <stdlib.h>
#include <string.h>

/* Exact-size scratch buffers; active callers own their allocations. Retain at
   most 16 idle buffers / 64 MiB, independent of the active layer/mask budgets. */
typedef struct {
  struct { void *data; size_t size; } slots[16];
  size_t bytes,allocations,reuses;
  unsigned disabled;
} exr_buffer_pool;
static inline void *exr_buffer_take(exr_buffer_pool *pool,size_t size,int clear) {
  void *data=NULL;size_t i;
  if(pool && !pool->disabled) for(i=0;i<16;i++) if(pool->slots[i].data && pool->slots[i].size==size) {
    data=pool->slots[i].data;pool->slots[i].data=NULL;pool->bytes-=size;pool->reuses++;break;
  }
  if(data) { if(clear) memset(data,0,size); }
  else { data=clear ? calloc(size,1) : malloc(size);if(data && pool) pool->allocations++; }
  return data;
}
static inline void exr_buffer_put(exr_buffer_pool *pool,void *data,size_t size) {
  size_t i;
  if(!data) return;
  if(pool && !pool->disabled && size<=(size_t)64*1024*1024-pool->bytes) for(i=0;i<16;i++) if(!pool->slots[i].data) {
    pool->slots[i].data=data;pool->slots[i].size=size;pool->bytes+=size;return;
  }
  free(data);
}
static inline void exr_buffer_pool_clear(exr_buffer_pool *pool) {
  size_t i;for(i=0;i<16;i++) { free(pool->slots[i].data);pool->slots[i].data=NULL; }pool->bytes=0;
}
#endif
