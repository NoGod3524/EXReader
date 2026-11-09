/* SPDX-License-Identifier: MIT */
/* Persistent font index. Little-endian binary:
     "EXRFIDX\0", u32 format, u32 FreeType version, u32 file count,
     u64 FNV-1a of the payload, payload.
   Payload per file: str path, u64 size, i64 mtime, u32 skip, str detail,
   u32 faces; per face: u32 index/style/weight/scripts/color, str family/style/aliases,
   u64 codepoints, u32 ranges, ranges*2 u32. str = u32 length + bytes.
   Any mismatch (format, FreeType version, checksum, bounds) discards the whole
   cache; individual entries are revalidated by path + size + mtime. */
#include "font_manager_internal.h"
#include "font_internal.h"
#ifdef _WIN32
#include <process.h>
#define exr_getpid _getpid
#else
#include <unistd.h>
#define exr_getpid getpid
#endif
#define FORMAT 2u
static const unsigned char magic[8] = {'E', 'X', 'R', 'F', 'I', 'D', 'X', 0};
static uint32_t ft_version(void) {
  return ((uint32_t)FREETYPE_MAJOR << 16) | ((uint32_t)FREETYPE_MINOR << 8) | (uint32_t)FREETYPE_PATCH;
}
static uint64_t fnv(const unsigned char *p, size_t n) {
  uint64_t h = UINT64_C(14695981039346656037);
  size_t i;
  for (i = 0; i < n; i++) { h ^= p[i]; h *= UINT64_C(1099511628211); }
  return h;
}
typedef struct { const unsigned char *p; size_t at, size; int bad; } reader;
static uint64_t take(reader *r, unsigned bytes) {
  uint64_t v = 0;
  unsigned i;
  if (r->bad || r->size - r->at < bytes) { r->bad = 1; return 0; }
  for (i = 0; i < bytes; i++) v |= (uint64_t)r->p[r->at + i] << (8 * i);
  r->at += bytes;
  return v;
}
static char *take_text(reader *r) {
  uint64_t n = take(r, 4);
  char *s;
  if (r->bad || n > r->size - r->at || n > 65536) { r->bad = 1; return NULL; }
  s = exr_copy((const char *)r->p + r->at, (size_t)n);
  if (!s || memchr(s, 0, (size_t)n)) { free(s); r->bad = 1; return NULL; }
  r->at += (size_t)n;
  return s;
}
static void files_free(exr_fm_files *files) {
  size_t i;
  for (i = 0; i < files->count; i++) exr_fm_file_clear(&files->items[i]);
  free(files->items);
  memset(files, 0, sizeof(*files));
}
exr_status exr_fm_cache_read(const char *path, exr_fm_files *out) {
  unsigned char *data = NULL;
  size_t size = 0, i, j, face_total = 0;
  reader r;
  uint64_t count, sum;
  memset(out, 0, sizeof(*out));
  if (exr_read(path, &data, &size, NULL) != EXR_OK) return EXR_IO;
  r = (reader){data, 0, size, 0};
  if (size < 28 || memcmp(data, magic, 8)) goto bad;
  r.at = 8;
  if (take(&r, 4) != FORMAT || take(&r, 4) != ft_version()) goto bad;
  count = take(&r, 4);
  sum = take(&r, 8);
  if (r.bad || count > EXR_FM_MAX_FILES || count > (size - r.at) / 36 ||
      fnv(data + r.at, size - r.at) != sum) goto bad;
  if (count && !(out->items = calloc((size_t)count, sizeof(*out->items)))) goto bad;
  out->capacity = (size_t)count;
  for (i = 0; i < count && !r.bad; i++) {
    exr_fm_file *file = &out->items[i];
    uint64_t faces;
    out->count++;
    file->path = take_text(&r);
    file->size = take(&r, 8);
    file->mtime = (int64_t)take(&r, 8);
    file->skip = (unsigned)take(&r, 4);
    file->detail = take_text(&r);
    faces = take(&r, 4);
    if (r.bad || faces > 4096 || faces > EXR_FM_MAX_FACES - face_total || faces > (r.size - r.at) / 52 ||
        (file->skip && faces) || (!file->skip && !faces)) { r.bad = 1; break; }
    if (faces && !(file->faces = calloc((size_t)faces, sizeof(*file->faces)))) { r.bad = 1; break; }
    face_total += (size_t)faces;
    for (j = 0; j < faces && !r.bad; j++) {
      exr_fm_face *face = &file->faces[j];
      uint64_t ranges, k;
      file->face_count++;
      face->face_index = (unsigned)take(&r, 4);
      face->style = (unsigned)take(&r, 4) & 3u;
      face->weight = (unsigned)take(&r, 4);
      face->scripts = (unsigned)take(&r, 4) & 7u;
      face->color = (unsigned)take(&r, 4) & 1u;
      face->family = take_text(&r);
      face->style_name = take_text(&r);
      face->aliases = take_text(&r);
      face->codepoints = (size_t)take(&r, 8);
      ranges = take(&r, 4);
      if (r.bad || !ranges || ranges > 0x110000 || ranges * 8 > r.size - r.at) { r.bad = 1; break; }
      if (!(face->ranges = malloc((size_t)ranges * 2 * sizeof(*face->ranges)))) { r.bad = 1; break; }
      face->range_count = (size_t)ranges;
      for (k = 0; k < 2 * ranges; k++) face->ranges[k] = (uint32_t)take(&r, 4);
      for (k = 0; k < ranges && !r.bad; k++)
        if (face->ranges[2 * k] > face->ranges[2 * k + 1] || face->ranges[2 * k + 1] > 0x10ffff ||
            (k && face->ranges[2 * k] <= face->ranges[2 * k - 1])) r.bad = 1;
    }
  }
  if (r.bad || r.at != size) goto bad;
  free(data);
  return EXR_OK;
bad:
  free(data);
  files_free(out);
  return EXR_FORMAT;
}
static int put(exr_buffer *b, uint64_t v, unsigned bytes) {
  unsigned char s[8];
  unsigned i;
  for (i = 0; i < bytes; i++) s[i] = (unsigned char)(v >> (8 * i));
  return exr_append(b, s, bytes);
}
static int put_text(exr_buffer *b, const char *s) {
  size_t n = s ? strlen(s) : 0;
  return put(b, n, 4) && exr_append(b, s ? s : "", n);
}
exr_status exr_fm_cache_write(const char *path, const exr_fm_files *files, exr_error *e) {
  exr_buffer b = {0};
  size_t i, j, k, count = 0, n;
  char *temporary;
  FILE *f;
  int ok = 1;
  for (i = 0; i < files->count; i++) if (files->items[i].skip != EXR_FONT_SKIP_NOT_FONT &&
                                         files->items[i].skip != EXR_FONT_SKIP_IO) count++;
  ok = exr_append(&b, magic, 8) && put(&b, FORMAT, 4) && put(&b, ft_version(), 4) && put(&b, count, 4) && put(&b, 0, 8);
  for (i = 0; ok && i < files->count; i++) {
    const exr_fm_file *file = &files->items[i];
    if (file->skip == EXR_FONT_SKIP_NOT_FONT || file->skip == EXR_FONT_SKIP_IO) continue;
    ok = put_text(&b, file->path) && put(&b, file->size, 8) && put(&b, (uint64_t)file->mtime, 8) &&
         put(&b, file->skip, 4) && put_text(&b, file->detail) && put(&b, file->face_count, 4);
    for (j = 0; ok && j < file->face_count; j++) {
      const exr_fm_face *face = &file->faces[j];
      ok = put(&b, face->face_index, 4) && put(&b, face->style, 4) && put(&b, face->weight, 4) &&
           put(&b, face->scripts, 4) && put(&b, face->color, 4) && put_text(&b, face->family) && put_text(&b, face->style_name) &&
           put_text(&b, face->aliases) && put(&b, face->codepoints, 8) && put(&b, face->range_count, 4);
      for (k = 0; ok && k < 2 * face->range_count; k++) ok = put(&b, face->ranges[k], 4);
    }
  }
  if (!ok) { free(b.data); return exr_fail(e, EXR_MEMORY, "Font cache serialization failed"); }
  {
    uint64_t sum = fnv((unsigned char *)b.data + 28, b.size - 28);
    for (i = 0; i < 8; i++) b.data[20 + i] = (char)(unsigned char)(sum >> (8 * i));
  }
  n = strlen(path) + 48;
  temporary = malloc(n);
  if (!temporary) { free(b.data); return exr_fail(e, EXR_MEMORY, "Font cache path allocation failed"); }
  /* pid + live buffer address: unique among concurrent writers without shared state. */
  snprintf(temporary, n, "%s.%lu.%p.tmp", path, (unsigned long)exr_getpid(), (void *)b.data);
  f = exr_fopen(temporary, "wb");
  if (!f) { free(b.data); free(temporary); return exr_fail(e, EXR_IO, "Cannot create font cache: %s", path); }
  ok = fwrite(b.data, 1, b.size, f) == b.size;
  ok = fclose(f) == 0 && ok;
  free(b.data);
  if (!ok || !exr_fm_rename(temporary, path)) {
    exr_fm_remove(temporary);
    free(temporary);
    return exr_fail(e, EXR_IO, "Cannot write font cache: %s", path);
  }
  free(temporary);
  return EXR_OK;
}
