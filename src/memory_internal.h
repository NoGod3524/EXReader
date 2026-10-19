/* SPDX-License-Identifier: MIT */
#ifndef EXR_MEMORY_INTERNAL_H
#define EXR_MEMORY_INTERNAL_H
#include <stddef.h>
size_t exr_memory_add(size_t total,size_t bytes);
size_t exr_memory_array(size_t total,const void *data,size_t count,size_t element);
#endif
