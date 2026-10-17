/* SPDX-License-Identifier: GPL-3.0-only */
#include "internal.h"
typedef union {
  size_t size;
#ifdef _MSC_VER
  /* MSVC's C headers omit max_align_t; preserve its 16-byte malloc alignment. */
  __declspec(align(16)) unsigned char alignment[16];
#else
  max_align_t alignment;
#endif
} allocation;
#ifdef _MSC_VER
#define IMAGE_TLS __declspec(thread)
#else
#define IMAGE_TLS _Thread_local
#endif
static IMAGE_TLS size_t working_bytes;
static IMAGE_TLS int allocation_limited;
static IMAGE_TLS int allocation_failed;
static void *image_allocate(size_t n) {
  allocation *p;
  if (n > 128 * 1024 * 1024 - working_bytes) {
    allocation_limited = 1;
    return NULL;
  }
  p = malloc(sizeof(*p) + n);
  if (!p) {
    allocation_failed = 1;
    return NULL;
  }
  p->size = n;
  working_bytes += n;
  return p + 1;
}
static void image_free(void *memory) {
  allocation *p;
  if (!memory)
    return;
  p = (allocation *)memory - 1;
  working_bytes -= p->size;
  free(p);
}
static void *image_reallocate(void *memory, size_t n) {
  allocation *p, *next;
  size_t old;
  if (!memory)
    return image_allocate(n);
  p = (allocation *)memory - 1;
  old = p->size;
  if (n > 128 * 1024 * 1024 - (working_bytes - old)) {
    allocation_limited = 1;
    return NULL;
  }
  next = realloc(p, sizeof(*p) + n);
  if (!next) {
    allocation_failed = 1;
    return NULL;
  }
  next->size = n;
  working_bytes = working_bytes - old + n;
  return next + 1;
}
#define STBI_MALLOC image_allocate
#define STBI_REALLOC image_reallocate
#define STBI_FREE image_free
#define STB_IMAGE_IMPLEMENTATION
#define STB_IMAGE_STATIC
#define STBI_ONLY_PNG
#define STBI_ONLY_JPEG
#define STBI_NO_GIF
#define STBI_NO_STDIO
#define STBI_MAX_DIMENSIONS INT_MAX /* Dimensions are checked after reading the header. */
#include <stb_image.h>
exr_status exr_image_decode(const void *data, size_t n, exr_bitmap *out, exr_error *e) {
  int w, h, channels;
  unsigned char *pixels;
  if (!out)
    return exr_fail(e, EXR_ARGUMENT, "Missing image output");
  memset(out, 0, sizeof(*out));
  if (!data || !n)
    return exr_fail(e, EXR_ARGUMENT, "Missing encoded image bytes");
  if (n > 32 * 1024 * 1024)
    return exr_fail(e, EXR_LIMIT, "Encoded image exceeds 32 MiB");
  allocation_limited = 0;
  allocation_failed = 0;
  if (!stbi_info_from_memory(data, (int)n, &w, &h, &channels))
    return exr_fail(e, allocation_failed ? EXR_MEMORY : EXR_FORMAT,
                    "Unsupported or damaged PNG/JPEG image");
  if (w <= 0 || h <= 0 || w > 8192 || h > 8192 || (size_t)w * (size_t)h > 16 * 1024 * 1024)
    return exr_fail(e, EXR_LIMIT, "Image exceeds 16 million pixels");
  pixels = stbi_load_from_memory(data, (int)n, &w, &h, &channels, 4);
  if (!pixels)
    return exr_fail(e,
                    allocation_limited  ? EXR_LIMIT
                    : allocation_failed ? EXR_MEMORY
                                        : EXR_FORMAT,
                    "PNG/JPEG decoding failed");
  out->pixels = malloc((size_t)w * (size_t)h * 4);
  if (!out->pixels) {
    stbi_image_free(pixels);
    return exr_fail(e, EXR_MEMORY, "Image pixel allocation failed");
  }
  memcpy(out->pixels, pixels, (size_t)w * (size_t)h * 4);
  stbi_image_free(pixels);
  out->width = (uint32_t)w;
  out->height = (uint32_t)h;
  out->stride = (uint32_t)w * 4;
  out->channels = 4;
  return EXR_OK;
}
