/* SPDX-License-Identifier: GPL-3.0-only */
#include "internal.h"
#ifdef _WIN32
#include <windows.h>
#endif
const char *exr_version(void) { return EXR_VERSION; }
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
FILE *exr_fopen(const char *path, const char *mode) {
#ifdef _WIN32
  int n;
  wchar_t *wpath, wm[8];
  size_t i;
  FILE *f;
  n = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1, NULL, 0);
  if (!n)
    return NULL;
  wpath = malloc((size_t)n * sizeof(*wpath));
  if (!wpath)
    return NULL;
  if (!MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1, wpath, n)) {
    free(wpath);
    return NULL;
  }
  for (i = 0; mode[i] && i < 7; i++)
    wm[i] = (wchar_t)mode[i];
  wm[i] = 0;
  f = _wfopen(wpath, wm);
  free(wpath);
  return f;
#else
  return fopen(path, mode);
#endif
}
exr_status exr_read(const char *path, unsigned char **data, size_t *size, exr_error *e) {
  FILE *f;
  long n;
  unsigned char *p;
  if (!path || !data || !size)
    return exr_fail(e, EXR_ARGUMENT, "Invalid file arguments");
  *data = NULL;
  *size = 0;
  f = exr_fopen(path, "rb");
  if (!f)
    return exr_fail(e, EXR_IO, "Cannot open file");
  if (fseek(f, 0, SEEK_END) || ((n = ftell(f)) < 0) || fseek(f, 0, SEEK_SET)) {
    fclose(f);
    return exr_fail(e, EXR_IO, "Cannot size file");
  }
  if ((size_t)n > EXR_MAX_INPUT) {
    fclose(f);
    return exr_fail(e, EXR_LIMIT, "Input exceeds 128 MiB");
  }
  p = malloc((size_t)n + 1);
  if (!p) {
    fclose(f);
    return exr_fail(e, EXR_MEMORY, "Allocation failed");
  }
  if (fread(p, 1, (size_t)n, f) != (size_t)n) {
    free(p);
    fclose(f);
    return exr_fail(e, EXR_IO, "Cannot read file");
  }
  fclose(f);
  p[n] = 0;
  *data = p;
  *size = (size_t)n;
  return EXR_OK;
}
exr_status exr_decode(const void *data, size_t n, exr_buffer *out, exr_error *e) {
  const unsigned char *s = data;
  size_t i = 0;
  int endian = 0, cr = 0;
  uint32_t cp;
  if (n >= 2 && s[0] == 0xff && s[1] == 0xfe) {
    endian = 1;
    i = 2;
  } else if (n >= 2 && s[0] == 0xfe && s[1] == 0xff) {
    endian = 2;
    i = 2;
  } else if (n >= 3 && s[0] == 0xef && s[1] == 0xbb && s[2] == 0xbf)
    i = 3;
  while (i < n) {
    if (endian) {
      if (n - i < 2)
        return exr_fail(e, EXR_ENCODING, "Truncated UTF-16");
      cp = endian == 1 ? (uint32_t)(s[i] | (s[i + 1] << 8)) : (uint32_t)((s[i] << 8) | s[i + 1]);
      i += 2;
      if (cp >= 0xd800 && cp <= 0xdbff) {
        uint32_t lo;
        if (n - i < 2)
          return exr_fail(e, EXR_ENCODING, "Unpaired UTF-16 surrogate");
        lo = endian == 1 ? (uint32_t)(s[i] | (s[i + 1] << 8)) : (uint32_t)((s[i] << 8) | s[i + 1]);
        i += 2;
        if (lo < 0xdc00 || lo > 0xdfff)
          return exr_fail(e, EXR_ENCODING, "Unpaired UTF-16 surrogate");
        cp = 0x10000 + ((cp - 0xd800) << 10) + (lo - 0xdc00);
      } else if (cp >= 0xdc00 && cp <= 0xdfff)
        return exr_fail(e, EXR_ENCODING, "Unpaired UTF-16 surrogate");
    } else if (!exr_next((const char *)s, n, &i, &cp))
      return exr_fail(e, EXR_ENCODING, "Invalid UTF-8; use UTF-8 or BOM-marked UTF-16");
    if (cp == 0)
      return exr_fail(e, EXR_ENCODING, "NUL is not text");
    if (cp == '\n' && cr) {
      cr = 0;
      continue;
    }
    cr = cp == '\r';
    if (cr)
      cp = '\n';
    if (!exr_codepoint(out, cp))
      return exr_fail(e, EXR_LIMIT, "Decoded text exceeds limit");
  }
  return EXR_OK;
}
int exr_add_block(exr_document *d, const char *text, size_t n, unsigned heading) {
  exr_block *b;
  while (n && (text[0] == ' ' || text[0] == '\t' || text[0] == '\n' || text[0] == '\r')) {
    text++;
    n--;
  }
  while (n &&
         (text[n - 1] == ' ' || text[n - 1] == '\t' || text[n - 1] == '\n' || text[n - 1] == '\r'))
    n--;
  if (!n)
    return 1;
  if (d->count >= EXR_MAX_ITEMS || n > EXR_MAX_TEXT - d->size - 1)
    return 0;
  if (!exr_grow((void **)&d->text, &d->text_capacity, d->size + n + 2, 1) ||
      !exr_grow((void **)&d->blocks, &d->capacity, d->count + 1, sizeof(*d->blocks)))
    return 0;
  if (d->size)
    d->text[d->size++] = '\n';
  b = &d->blocks[d->count++];
  b->start = d->size;
  b->end = d->size + n;
  b->heading = heading;
  memcpy(d->text + d->size, text, n);
  d->size += n;
  d->text[d->size] = 0;
  return 1;
}
void exr_document_free(exr_document *d) {
  if (d) {
    free(d->text);
    free(d->title);
    free(d->blocks);
    exr_model_free(d);
    free(d);
  }
}
exr_status exr_document_open_memory(exr_format f, const void *data, size_t n, exr_document **out,
                                    exr_error *e) {
  exr_document *d;
  exr_status status;
  if (!out)
    return exr_fail(e, EXR_ARGUMENT, "Missing output");
  *out = NULL;
  if (e)
    memset(e, 0, sizeof(*e));
  if (!data || !n || n > EXR_MAX_INPUT)
    return exr_fail(e, n > EXR_MAX_INPUT ? EXR_LIMIT : EXR_ARGUMENT, "Invalid document bytes");
  d = calloc(1, sizeof(*d));
  if (!d)
    return exr_fail(e, EXR_MEMORY, "Allocation failed");
  d->format = f;
  status = exr_parse(d, data, n, e);
  if (status == EXR_OK)
    status = exr_model_finish(d, e);
  if (status != EXR_OK) {
    if (e) {
      e->code = status;
      if (!e->message[0])
        snprintf(e->message, sizeof(e->message), "Native parser failed (%d)", (int)status);
    }
    exr_document_free(d);
    return status;
  }
  if (!d->count && !d->chapter_count) {
    exr_document_free(d);
    return exr_fail(e, EXR_FORMAT, "Document has no supported text content");
  }
  *out = d;
  return exr_fail(e, EXR_OK, "");
}
exr_status exr_document_open(const char *path, exr_document **out, exr_error *e) {
  const char *ext;
  unsigned char *data;
  size_t n;
  exr_status s;
  exr_format f = 0;
  char lower[16];
  size_t i;
  if (!path || !out)
    return exr_fail(e, EXR_ARGUMENT, "Invalid path or output");
  *out = NULL;
  ext = strrchr(path, '.');
  if (!ext)
    return exr_fail(e, EXR_FORMAT, "File has no format extension");
  ext++;
  for (i = 0; ext[i] && i < sizeof(lower) - 1; i++)
    lower[i] = (char)((ext[i] >= 'A' && ext[i] <= 'Z') ? ext[i] + 32 : ext[i]);
  lower[i] = 0;
  if (!strcmp(lower, "txt"))
    f = EXR_TXT;
  else if (!strcmp(lower, "html") || !strcmp(lower, "htm"))
    f = EXR_HTML;
  else if (!strcmp(lower, "epub"))
    f = EXR_EPUB;
  else if (!strcmp(lower, "fb2"))
    f = EXR_FB2;
  else if (!strcmp(lower, "docx"))
    f = EXR_DOCX;
  else if (!strcmp(lower, "rtf"))
    f = EXR_RTF;
  else if (!strcmp(lower, "mobi") || !strcmp(lower, "azw3"))
    f = EXR_MOBI;
  else if (!strcmp(lower, "pdf"))
    f = EXR_PDF;
  if (!f)
    return exr_fail(e, EXR_FORMAT, "Unsupported format");
  s = exr_read(path, &data, &n, e);
  if (s != EXR_OK)
    return s;
  s = exr_document_open_memory(f, data, n, out, e);
  free(data);
  return s;
}
const char *exr_document_text(const exr_document *d, size_t *n) {
  if (n)
    *n = d ? d->size : 0;
  return d ? d->text : NULL;
}
const char *exr_document_title(const exr_document *d) { return d && d->title ? d->title : ""; }
const exr_block *exr_document_blocks(const exr_document *d, size_t *n) {
  if (n)
    *n = d ? d->count : 0;
  return d ? d->blocks : NULL;
}
exr_format exr_document_format(const exr_document *d) { return d ? d->format : 0; }
exr_status exr_document_find(const exr_document *d, const char *q, size_t from, size_t *start,
                             size_t *end, exr_error *e) {
  size_t n, at = 0;
  uint32_t cp;
  const char *p;
  if (!d || !q || !start || !end || from > d->size || !q[0])
    return exr_fail(e, EXR_ARGUMENT, "Invalid search");
  n = strlen(q);
  while (at < n)
    if (!exr_next(q, n, &at, &cp))
      return exr_fail(e, EXR_ENCODING, "Invalid query UTF-8");
  while (from < d->size && ((unsigned char)d->text[from] & 0xc0) == 0x80)
    from++;
  p = strstr(d->text + from, q);
  if (!p) {
    *start = *end = SIZE_MAX;
    return EXR_OK;
  }
  *start = (size_t)(p - d->text);
  *end = *start + n;
  return EXR_OK;
}
void exr_bitmap_free(exr_bitmap *b) {
  if (b) {
    free(b->pixels);
    memset(b, 0, sizeof(*b));
  }
}
static void le32(unsigned char *p, uint32_t v) {
  p[0] = (unsigned char)v;
  p[1] = (unsigned char)(v >> 8);
  p[2] = (unsigned char)(v >> 16);
  p[3] = (unsigned char)(v >> 24);
}
exr_status exr_bitmap_write_bmp(const exr_bitmap *b, const char *path, exr_error *e) {
  unsigned char head[54] = {0}, *row;
  uint32_t stride, y, x;
  unsigned channels;
  FILE *f;
  int ok = 1;
  if (!b)
    return exr_fail(e, EXR_ARGUMENT, "Missing bitmap");
  channels = b->channels ? b->channels : 1;
  if (!b->pixels || !path || !b->width || !b->height || b->width > 16384 || b->height > 16384 ||
      (channels != 1 && channels != 4) || b->stride < b->width * channels)
    return exr_fail(e, EXR_ARGUMENT, "Invalid bitmap");
  stride = (b->width * 3 + 3) & ~3u;
  row = calloc(stride, 1);
  if (!row)
    return exr_fail(e, EXR_MEMORY, "Allocation failed");
  head[0] = 'B';
  head[1] = 'M';
  le32(head + 2, 54 + stride * b->height);
  le32(head + 10, 54);
  le32(head + 14, 40);
  le32(head + 18, b->width);
  le32(head + 22, b->height);
  head[26] = 1;
  head[28] = 24;
  f = exr_fopen(path, "wb");
  if (!f) {
    free(row);
    return exr_fail(e, EXR_IO, "Cannot write bitmap");
  }
  if (fwrite(head, 1, 54, f) != 54)
    ok = 0;
  for (y = b->height; y > 0 && ok; y--) {
    for (x = 0; x < b->width; x++) {
      const unsigned char *p = b->pixels + (size_t)(y - 1) * b->stride + x * channels;
      if (channels == 1)
        row[x * 3] = row[x * 3 + 1] = row[x * 3 + 2] = *p;
      else {
        row[x * 3] = (unsigned char)((p[2] * p[3] + 255 * (255 - p[3])) / 255);
        row[x * 3 + 1] = (unsigned char)((p[1] * p[3] + 255 * (255 - p[3])) / 255);
        row[x * 3 + 2] = (unsigned char)((p[0] * p[3] + 255 * (255 - p[3])) / 255);
      }
    }
    if (fwrite(row, 1, stride, f) != stride)
      ok = 0;
  }
  if (fclose(f))
    ok = 0;
  free(row);
  return ok ? EXR_OK : exr_fail(e, EXR_IO, "Bitmap write failed");
}
