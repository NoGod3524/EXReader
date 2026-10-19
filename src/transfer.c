/* SPDX-License-Identifier: MIT */
#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#endif
#include "base_internal.h"
#include <miniz.h>
#include <time.h>
exr_status exr_xml_text(const char *text, size_t size, const char *field, exr_error *e) {
  size_t at = 0;
  while (at < size) {
    size_t start = at;
    uint32_t cp;
    if (!exr_next(text, size, &at, &cp))
      return exr_fail(e, EXR_ENCODING, "Invalid UTF-8 in XML %s at byte %zu", field, start);
    if (cp != 9 && cp != 10 && cp != 13 &&
        !(cp >= 0x20 && cp <= 0xd7ff) && !(cp >= 0xe000 && cp <= 0xfffd) &&
        !(cp >= 0x10000 && cp <= 0x10ffff))
      return exr_fail(e, EXR_ENCODING, "XML 1.0 cannot represent U+%04lX in %s at byte %zu",
                      (unsigned long)cp, field, start);
  }
  return EXR_OK;
}
exr_status exr_export_time(char modified[32], exr_error *e) {
  time_t now = time(NULL);
  struct tm utc;
#ifdef _WIN32
  if (gmtime_s(&utc, &now))
    return exr_fail(e, EXR_IO, "Cannot read UTC time");
#else
  if (!gmtime_r(&now, &utc))
    return exr_fail(e, EXR_IO, "Cannot read UTC time");
#endif
  if (!strftime(modified, 32, "%Y-%m-%dT%H:%M:%SZ", &utc))
    return exr_fail(e, EXR_IO, "Cannot format UTC time");
  return EXR_OK;
}
static void big32(unsigned char *p, uint32_t n) {
  p[0] = (unsigned char)(n >> 24);
  p[1] = (unsigned char)(n >> 16);
  p[2] = (unsigned char)(n >> 8);
  p[3] = (unsigned char)n;
}
static int chunk(FILE *f, const char *type, const void *data, size_t n) {
  unsigned char prefix[8], crc[4];
  mz_ulong checksum;
  big32(prefix, (uint32_t)n);
  memcpy(prefix + 4, type, 4);
  checksum = mz_crc32(0, prefix + 4, 4);
  if (n)
    checksum = mz_crc32(checksum, data, n);
  big32(crc, (uint32_t)checksum);
  return fwrite(prefix, 1, 8, f) == 8 && (!n || fwrite(data, 1, n, f) == n) &&
         fwrite(crc, 1, 4, f) == 4;
}
exr_status exr_bitmap_write_png(const exr_bitmap *b, const char *path, exr_error *e) {
  unsigned char ihdr[13] = {0}, *raw, *compressed;
  size_t bytes, y, row;
  unsigned channels;
  unsigned long capacity;
  FILE *f;
  int ok;
  if (!b)
    return exr_fail(e, EXR_ARGUMENT, "Missing bitmap");
  channels = b->channels ? b->channels : 1;
  row = (size_t)b->width * channels;
  if (!path || !b->pixels || !b->width || !b->height || b->width > 16384 || b->height > 16384 ||
      (channels != 1 && channels != 4) || b->stride < row || row * b->height > 64 * 1024 * 1024)
    return exr_fail(e, EXR_ARGUMENT, "Invalid PNG bitmap");
  bytes = (row + 1) * b->height;
  capacity = mz_compressBound((mz_ulong)bytes);
  raw = malloc(bytes);
  compressed = malloc(capacity);
  if (!raw || !compressed) {
    free(raw);
    free(compressed);
    return exr_fail(e, EXR_MEMORY, "PNG allocation failed");
  }
  for (y = 0; y < b->height; y++) {
    raw[y * (row + 1)] = 0;
    memcpy(raw + y * (row + 1) + 1, b->pixels + y * b->stride, row);
  }
  if (mz_compress2(compressed, &capacity, raw, (mz_ulong)bytes, 1) != MZ_OK) {
    free(raw);
    free(compressed);
    return exr_fail(e, EXR_FORMAT, "PNG compression failed");
  }
  free(raw);
  big32(ihdr, b->width);
  big32(ihdr + 4, b->height);
  ihdr[8] = 8;
  ihdr[9] = channels == 4 ? 6 : 0;
  f = exr_fopen(path, "wb");
  if (!f) {
    free(compressed);
    return exr_fail(e, EXR_IO, "Cannot write PNG");
  }
  ok = fwrite("\x89PNG\r\n\x1a\n", 1, 8, f) == 8 && chunk(f, "IHDR", ihdr, 13) &&
       chunk(f, "IDAT", compressed, capacity) && chunk(f, "IEND", NULL, 0);
  if (fclose(f))
    ok = 0;
  free(compressed);
  return ok ? EXR_OK : exr_fail(e, EXR_IO, "PNG write failed");
}
