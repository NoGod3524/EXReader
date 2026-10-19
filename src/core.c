/* SPDX-License-Identifier: MIT */
#include "internal.h"
#ifdef _WIN32
#include <windows.h>
#endif
const char *exr_version(void) { return EXR_VERSION; }
uint32_t exr_abi_version(void) { return EXR_ABI_VERSION; }
int exr_pdf_crypto_available(void) {
#ifdef EXR_ENABLE_PDF_CRYPTO
  return 1;
#else
  return 0;
#endif
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
