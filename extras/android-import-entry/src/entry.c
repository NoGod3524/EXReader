/* SPDX-License-Identifier: MIT */
#include <exr_android_import_entry.h>
#include <string.h>
#include <sys/stat.h>

static exr_status refuse(exr_error *error, exr_status code, const char *message) {
  if (error) {
    error->code = code;
    strncpy(error->message, message, sizeof(error->message) - 1);
    error->message[sizeof(error->message) - 1] = 0;
  }
  return code;
}

static uint64_t ceiling(exr_format format) {
  return format == EXR_EPUB || format == EXR_CBZ || format == EXR_PDF ? EXR_SIDELOAD_STREAM_LIMIT
                                                                       : EXR_SIDELOAD_MEMORY_LIMIT;
}

exr_status exr_android_import_commit(exr_library *library, const exr_android_import_request *request,
    exr_sideload_result *result, exr_error *error) {
  struct stat st;
  exr_sideload_options options;
  if (result) memset(result, 0, sizeof(*result));
  if (!library || !request || !result || request->struct_size < sizeof(*request))
    return refuse(error, EXR_ARGUMENT, "Invalid import request");
  if (request->format < EXR_TXT || request->format > EXR_CBZ)
    return refuse(error, EXR_ARGUMENT, "Unsupported format code");
  if (!request->path || request->path[0] != '/') return refuse(error, EXR_ARGUMENT, "A staged absolute path is required");
  if (request->size == 0 || request->size > ceiling(request->format))
    return refuse(error, EXR_LIMIT, "Staged size is outside the format ceiling");
  if (lstat(request->path, &st) != 0 || !S_ISREG(st.st_mode)) return refuse(error, EXR_IO, "Staged file is not a regular file");
  if ((uint64_t)st.st_size != request->size) return refuse(error, EXR_IO, "Staged file size changed");
  memset(&options, 0, sizeof(options));
  options.struct_size = sizeof(options);
  options.control = request->control;
  result->struct_size = sizeof(*result);
  return exr_sideload_import_file(library, request->format, request->path, request->title, &options, result, error);
}
