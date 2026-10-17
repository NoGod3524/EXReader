/* SPDX-License-Identifier: GPL-3.0-only */
#ifndef _WIN32
#ifndef _POSIX_C_SOURCE
#define _POSIX_C_SOURCE 200809L
#endif
#ifndef _FILE_OFFSET_BITS
#define _FILE_OFFSET_BITS 64
#endif
#endif
#include "internal.h"

static size_t file_read(void *context, uint64_t offset, void *buffer, size_t size) {
  FILE *file = context;
  if(offset>INT64_MAX) return 0;
#ifdef _WIN32
  if(_fseeki64(file,(int64_t)offset,SEEK_SET)) return 0;
#else
  if(fseeko(file,(off_t)offset,SEEK_SET)) return 0;
#endif
  return fread(buffer, 1, size, file);
}
static void file_release(void *context) { fclose(context); }
exr_status exr_file_source_limit(const char *path,uint64_t maximum,exr_source *source,exr_error *e) {
  FILE *file;
  int64_t size;
  memset(source, 0, sizeof(*source));
  file = exr_fopen(path, "rb");
  if (!file) return exr_fail(e, EXR_IO, "Cannot open publication file");
#ifdef _WIN32
  size = _fseeki64(file, 0, SEEK_END) ? -1 : _ftelli64(file);
#else
  size = fseeko(file, 0, SEEK_END) ? -1 : (int64_t)ftello(file);
#endif
  if (size < 0 || (uint64_t)size > maximum) {
    fclose(file);
    return exr_fail(e, size < 0 ? EXR_IO : EXR_LIMIT, "Cannot size file or input exceeds byte limit");
  }
  *source = (exr_source){(uint64_t)size, file_read, file_release, file, {0}};
  return EXR_OK;
}

exr_status exr_file_source(const char *path,exr_source *source,exr_error *e) { return exr_file_source_limit(path,EXR_MAX_INPUT,source,e); }
