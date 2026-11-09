/* SPDX-License-Identifier: MIT */
#ifndef EXR_LIFETIME_INTERNAL_H
#define EXR_LIFETIME_INTERNAL_H
#include "exr/base.h"
#include <stdlib.h>

#if !defined(NDEBUG) && defined(EXR_LIFETIME_IMPLEMENTATION)
void *exr_lifetime_new(size_t size, const char *type);
void *exr_lifetime_malloc(size_t size);
void *exr_lifetime_calloc(size_t count, size_t size);
void *exr_lifetime_realloc(void *data, size_t size);
void exr_lifetime_own(void *data, size_t size);
void exr_lifetime_release_public(const void *object);
void exr_lifetime_loan(const void *owner, const void *object);
void exr_lifetime_view(const void *owner, const void *object);
void exr_lifetime_expect(const void *object, const char *type);
void exr_lifetime_delete(void *object);
void exr_lifetime_depend(const void *object, unsigned slot, const void *parent);
void exr_lifetime_borrow(const void *owner, const void *data, size_t size);
/* begin/end surround only public calls; internal SDK calls use the renamed
   implementation symbols. Hence a nested public call is a host reentry. */
typedef struct {
  void *records[64], *buffers[64];
  size_t count, buffer_count;
  void *previous;
} exr_lifetime_scope;
int exr_lifetime_begin(exr_lifetime_scope *scope, const void *const *objects,
                       size_t count, int mode);
void exr_lifetime_end(exr_lifetime_scope *scope);
#define EXR_NEW(type) ((type *)exr_lifetime_new(sizeof(type), #type))
#define EXR_DELETE(object) exr_lifetime_delete(object)
#define EXR_DEPEND(object, slot, parent) exr_lifetime_depend(object, slot, parent)
/* SDK frees inspect the registry before touching a handle. Foreign and ordinary
   buffers continue to use their original C allocator. */
#if !defined(EXR_LIFETIME_WRAPPER)
#define malloc(size) exr_lifetime_malloc(size)
#define calloc(count, size) exr_lifetime_calloc(count, size)
#define realloc(data, size) exr_lifetime_realloc(data, size)
#define free(object) exr_lifetime_delete(object)
/* miniz's default heap is the C heap. LCP decoding can replace its buffers
   with SDK allocations before they pass through this release entry point. */
#define mz_free exr_lifetime_delete
#endif
#else
#define EXR_NEW(type) ((type *)calloc(1, sizeof(type)))
#define EXR_DELETE(object) free(object)
#define EXR_DEPEND(object, slot, parent) ((void)0)
#endif
#endif
