/* SPDX-License-Identifier: GPL-3.0-only */
#include "internal.h"
exr_status exr_fail(exr_error *e, exr_status code, const char *fmt, ...) {
  if (e) {
    va_list args;
    e->code = code;
    va_start(args, fmt);
    vsnprintf(e->message, sizeof(e->message), fmt, args);
    va_end(args);
  }
  return code;
}
exr_status exr_control_cancel(const exr_control *control, exr_error *e) {
  if (control && control->cancelled && control->cancelled(control->context))
    return exr_fail(e, EXR_CANCELLED, "Operation cancelled");
  return EXR_OK;
}
exr_status exr_control_poll(const exr_control *control, exr_stage stage,
                             uint64_t completed, uint64_t total, exr_error *e) {
  exr_status status = exr_control_cancel(control, e);
  if (status != EXR_OK) return status;
  if (control && control->progress) control->progress(control->context, stage, completed, total);
  return exr_control_cancel(control, e);
}
int exr_grow(void **p, size_t *cap, size_t n, size_t unit) {
  size_t next;
  void *q;
  if (n <= *cap)
    return 1;
  if (!unit || n > SIZE_MAX / unit)
    return 0;
  next = *cap ? *cap : 64;
  while (next < n) {
    if (next > SIZE_MAX / 2) {
      next = n;
      break;
    }
    next *= 2;
  }
  if (next > SIZE_MAX / unit)
    next = n;
  q = realloc(*p, next * unit);
  if (!q)
    return 0;
  *p = q;
  *cap = next;
  return 1;
}
char *exr_copy(const char *s, size_t n) {
  char *p;
  if (n == SIZE_MAX)
    return NULL;
  p = malloc(n + 1);
  if (!p)
    return NULL;
  if (n)
    memcpy(p, s, n);
  p[n] = 0;
  return p;
}
int exr_append(exr_buffer *b, const void *s, size_t n) {
  if (n > EXR_MAX_TEXT - b->size || !exr_grow((void **)&b->data, &b->capacity, b->size + n + 1, 1))
    return 0;
  if (n)
    memcpy(b->data + b->size, s, n);
  b->size += n;
  b->data[b->size] = 0;
  return 1;
}
int exr_codepoint(exr_buffer *b, uint32_t cp) {
  unsigned char s[4];
  size_t n;
  if (cp <= 0x7f) {
    s[0] = (unsigned char)cp;
    n = 1;
  } else if (cp <= 0x7ff) {
    s[0] = (unsigned char)(0xc0 | (cp >> 6));
    s[1] = (unsigned char)(0x80 | (cp & 63));
    n = 2;
  } else if (cp <= 0xffff && !(cp >= 0xd800 && cp <= 0xdfff)) {
    s[0] = (unsigned char)(0xe0 | (cp >> 12));
    s[1] = (unsigned char)(0x80 | ((cp >> 6) & 63));
    s[2] = (unsigned char)(0x80 | (cp & 63));
    n = 3;
  } else if (cp >= 0x10000 && cp <= 0x10ffff) {
    s[0] = (unsigned char)(0xf0 | (cp >> 18));
    s[1] = (unsigned char)(0x80 | ((cp >> 12) & 63));
    s[2] = (unsigned char)(0x80 | ((cp >> 6) & 63));
    s[3] = (unsigned char)(0x80 | (cp & 63));
    n = 4;
  } else
    return 0;
  return exr_append(b, s, n);
}
int exr_next(const char *s, size_t n, size_t *at, uint32_t *cp) {
  size_t i = *at, j, k;
  uint32_t c, min;
  if (i >= n)
    return 0;
  c = (unsigned char)s[i++];
  if (c < 0x80) {
    *cp = c;
    *at = i;
    return 1;
  }
  if (c >= 0xc2 && c <= 0xdf) {
    k = 1;
    min = 0x80;
    c &= 31;
  } else if (c >= 0xe0 && c <= 0xef) {
    k = 2;
    min = 0x800;
    c &= 15;
  } else if (c >= 0xf0 && c <= 0xf4) {
    k = 3;
    min = 0x10000;
    c &= 7;
  } else
    return 0;
  if (k > n - i)
    return 0;
  for (j = 0; j < k; j++) {
    unsigned char b = (unsigned char)s[i++];
    if ((b & 0xc0) != 0x80)
      return 0;
    c = (c << 6) | (b & 63);
  }
  if (c < min || c > 0x10ffff || (c >= 0xd800 && c <= 0xdfff))
    return 0;
  *cp = c;
  *at = i;
  return 1;
}
