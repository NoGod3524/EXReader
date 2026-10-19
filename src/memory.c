/* SPDX-License-Identifier: MIT */
#include "base_internal.h"
#include "memory_internal.h"

void exr_free(void *p) { free(p); }

/* Requested allocation payload, excluding allocator overhead and shared or borrowed
   objects. Saturation keeps accounting safe even when a sum cannot fit size_t. */
size_t exr_memory_add(size_t total, size_t bytes) {
  return bytes > SIZE_MAX - total ? SIZE_MAX : total + bytes;
}
size_t exr_memory_array(size_t total, const void *data, size_t count, size_t element) {
  if (!data)
    return total;
  if (element && count > SIZE_MAX / element)
    return SIZE_MAX;
  return exr_memory_add(total, count * element);
}

void exr_metadata_free(exr_metadata_entry *entries,size_t count) {
  size_t i; if(!entries) return;
  for(i=0;i<count;i++) { free((void *)entries[i].key); free((void *)entries[i].value); }
  free(entries);
}
