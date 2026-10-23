/* SPDX-License-Identifier: MIT */
#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#define _FILE_OFFSET_BITS 64
#endif
#include "exr_sideload.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <sys/types.h>
#endif

static exr_status fail(exr_error *error, exr_status status, const char *message) {
  if (error) {
    error->code = status;
    snprintf(error->message, sizeof(error->message), "%s", message);
  }
  return status;
}

static exr_status arguments(exr_library *library, exr_format format,
    const exr_sideload_options *options, exr_sideload_result *result, exr_error *error) {
  if (!result || result->struct_size < sizeof(*result))
    return fail(error, EXR_ARGUMENT, "Set a complete sideload result struct_size");
  result->book_id = 0;
  result->created = 0;
  if (!library || (options && options->struct_size < sizeof(*options)))
    return fail(error, EXR_ARGUMENT, "Invalid library or sideload options struct_size");
  if (format < EXR_TXT || format > EXR_CBZ)
    return fail(error, EXR_UNSUPPORTED, "Unsupported sideload format");
  return EXR_OK;
}

static uint64_t limit_for(exr_format format, const exr_sideload_options *options) {
  uint64_t limit = format == EXR_EPUB || format == EXR_CBZ || format == EXR_PDF ?
      EXR_SIDELOAD_STREAM_LIMIT : EXR_SIDELOAD_MEMORY_LIMIT;
  if (options && options->max_input_bytes && options->max_input_bytes < limit)
    limit = options->max_input_bytes;
  return limit;
}

static exr_status poll(const exr_control *control, uint64_t done, uint64_t total, exr_error *error) {
  if (control->cancelled && control->cancelled(control->context))
    return fail(error, EXR_CANCELLED, "Sideload cancelled before committing");
  if (control->progress) control->progress(control->context, EXR_STAGE_READ, done, total);
  if (control->cancelled && control->cancelled(control->context))
    return fail(error, EXR_CANCELLED, "Sideload cancelled before committing");
  return EXR_OK;
}

exr_status exr_sideload_import_source(exr_library *library, exr_format format,
    const exr_source *input, const char *title, const exr_sideload_options *options,
    exr_sideload_result *result, exr_error *error) {
  exr_source source;
  exr_status status = arguments(library, format, options, result, error);
  unsigned char *bytes;
  size_t size, at = 0;
  if (status != EXR_OK) return status;
  if (!input || !input->read_at)
    return fail(error, EXR_ARGUMENT, "An immutable random-read source is required");
  if (format == EXR_PDF)
    return fail(error, EXR_UNSUPPORTED, "PDF sideload requires a stable app-owned file");
  if (!input->size) return fail(error, EXR_FORMAT, "Sideload input is empty");
  if (input->size > limit_for(format, options))
    return fail(error, EXR_LIMIT, "Sideload input exceeds its byte limit");
  source = *input;
  source.release = NULL;
  if (options && (options->control.cancelled || options->control.progress)) source.control = options->control;
  status = poll(&source.control, 0, source.size, error);
  if (status != EXR_OK) return status;
  if (format == EXR_EPUB || format == EXR_CBZ)
    return exr_library_import_source_unique(library, format, &source, title,
                                            &result->book_id, &result->created, error);
  size = (size_t)source.size;
  bytes = malloc(size);
  if (!bytes) return fail(error, EXR_MEMORY, "Cannot allocate bounded sideload input");
  while (at < size) {
    size_t wanted = size - at < 65536 ? size - at : 65536;
    size_t got;
    status = poll(&source.control, at, size, error);
    if (status != EXR_OK) break;
    got = source.read_at(source.context, at, bytes + at, wanted);
    if (!got || got > wanted) {
      status = fail(error, EXR_IO, "Sideload source returned an invalid or incomplete read");
      break;
    }
    at += got;
  }
  if (status == EXR_OK) status = poll(&source.control, size, size, error);
  if (status == EXR_OK)
    status = exr_library_import_unique(library, format, bytes, size, title,
                                       &result->book_id, &result->created, error);
  free(bytes);
  return status;
}

static FILE *open_file(const char *path, exr_status *status) {
#ifdef _WIN32
  int count = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1, NULL, 0);
  wchar_t *wide;
  FILE *file;
  if (!count) { *status = EXR_ENCODING; return NULL; }
  wide = malloc((size_t)count * sizeof(*wide));
  if (!wide) { *status = EXR_MEMORY; return NULL; }
  if (!MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1, wide, count)) {
    free(wide); *status = EXR_ENCODING; return NULL;
  }
  file = _wfopen(wide, L"rb");
  free(wide);
  return file;
#else
  (void)status;
  return fopen(path, "rb");
#endif
}

static size_t file_read(void *context, uint64_t offset, void *buffer, size_t size) {
  FILE *file = context;
  if (offset > INT64_MAX) return 0;
#ifdef _WIN32
  if (_fseeki64(file, (__int64)offset, SEEK_SET)) return 0;
#else
  if (fseeko(file, (off_t)offset, SEEK_SET)) return 0;
#endif
  return fread(buffer, 1, size, file);
}

exr_status exr_sideload_import_file(exr_library *library, exr_format format,
    const char *path, const char *title, const exr_sideload_options *options,
    exr_sideload_result *result, exr_error *error) {
  exr_status status = arguments(library, format, options, result, error);
  exr_source source = {0};
  FILE *file;
  int64_t size;
  if (status != EXR_OK) return status;
  if (!path || !path[0]) return fail(error, EXR_ARGUMENT, "A stable app-owned path is required");
  status = EXR_IO;
  file = open_file(path, &status);
  if (!file) return fail(error, status, "Cannot open sideload file");
#ifdef _WIN32
  size = _fseeki64(file, 0, SEEK_END) ? -1 : _ftelli64(file);
#else
  size = fseeko(file, 0, SEEK_END) ? -1 : (int64_t)ftello(file);
#endif
  if (size <= 0) status = fail(error, size < 0 ? EXR_IO : EXR_FORMAT, "Cannot size file or input is empty");
  else if ((uint64_t)size > limit_for(format, options))
    status = fail(error, EXR_LIMIT, "Sideload file exceeds its byte limit");
  else {
    source.size = (uint64_t)size;
    source.context = file;
    source.read_at = file_read;
    if (options) source.control = options->control;
    if (format == EXR_PDF) {
      status = poll(&source.control, 0, source.size, error);
      if (status == EXR_OK)
        status = exr_library_import_file_unique(library, format, path, title,
                                                &result->book_id, &result->created, error);
    } else status = exr_sideload_import_source(library, format, &source, title, options, result, error);
  }
  fclose(file);
  return status;
}
