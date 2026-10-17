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

/* Shared prefix table for one-shot and incremental byte matching. */
exr_status exr_kmp_prefix(const char *q,size_t n,const exr_control *control,uint32_t **out,exr_error *e) {
  uint32_t *prefix; size_t i,j=0;
  if(!out) return exr_fail(e,EXR_ARGUMENT,"Missing search prefix output");
  *out=NULL;
  if(!q || !n) return exr_fail(e,EXR_ARGUMENT,"Missing search pattern");
  if(n>(size_t)1024*1024) return exr_fail(e,EXR_LIMIT,"Search query exceeds 1 MiB");
  prefix=malloc(n*sizeof(*prefix)); if(!prefix) return exr_fail(e,EXR_MEMORY,"Search prefix allocation failed");
  prefix[0]=0;
  for(i=1;i<n;i++) {
    exr_status status;
    if(!(i&4095) && (status=exr_control_cancel(control,e))!=EXR_OK) { free(prefix); return status; }
    while(j && q[i]!=q[j]) j=prefix[j-1];
    if(q[i]==q[j]) j++;
    prefix[i]=(uint32_t)j;
  }
  *out=prefix; return EXR_OK;
}
/* KMP keeps adversarial repeated-prefix searches linear, with <=4 MiB scratch. */
exr_status exr_find_bytes(const char *text,size_t size,const char *q,size_t n,size_t from,
                            const exr_control *control,size_t *start,size_t *end,exr_error *e) {
  uint32_t *prefix=NULL,cp; size_t at=0,i,j=0,steps=0; exr_status status;
  if(start) *start=SIZE_MAX;
  if(end) *end=SIZE_MAX;
  if((!text && size) || !q || !n || !start || !end || from>size) return exr_fail(e,EXR_ARGUMENT,"Invalid text search");
  if(n>(size_t)1024*1024) return exr_fail(e,EXR_LIMIT,"Search query exceeds 1 MiB");
  status=exr_control_cancel(control,e); if(status!=EXR_OK) return status;
  while(at<n) {
    if(!(steps++&1023) && exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
    if(!exr_next(q,n,&at,&cp)) return exr_fail(e,EXR_ENCODING,"Invalid query UTF-8");
  }
  while(from<size && ((unsigned char)text[from]&0xc0)==0x80) from++;
  if(n>size-from) return exr_fail(e,EXR_OK,"");
  status=exr_kmp_prefix(q,n,control,&prefix,e); if(status!=EXR_OK) return status;
  j=0;
  for(i=from;i<size;i++) {
    if(!((i-from)&4095) && exr_control_cancel(control,e)!=EXR_OK) { free(prefix); return EXR_CANCELLED; }
    while(j && text[i]!=q[j]) j=prefix[j-1];
    if(text[i]==q[j]) j++;
    if(j==n) { *end=i+1; *start=*end-n; break; }
  }
  free(prefix); return exr_fail(e,EXR_OK,"");
}
