/* SPDX-License-Identifier: MIT */
/* Atomic publication of one report to a NEW path.

   The bytes are written to a same-directory temporary, flushed, and only then
   committed with a single primitive that fails when the target already exists
   (MoveFileExW without MOVEFILE_REPLACE_EXISTING on Windows, link(2) on POSIX).
   Every failure or cancel before that step removes the temporary, so an existing
   target is never opened, truncated or replaced. */
#if defined(_WIN32)
#define _CRT_SECURE_NO_WARNINGS 1
#include <windows.h>
#include <wchar.h>
#else
#include <errno.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#endif
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "internal.h"

#if defined(_WIN32)

/* UTF-8 path -> UTF-16. Invalid UTF-8 is ARGUMENT, not a silent substitution. */
static reader_diag_status rd_wide_path(const char *utf8, wchar_t **out) {
  int length;
  *out = NULL;
  length = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, utf8, -1, NULL, 0);
  if (length <= 0) return READER_DIAG_ARGUMENT;
  *out = (wchar_t *)calloc((size_t)length, sizeof(wchar_t));
  if (!*out) return READER_DIAG_MEMORY;
  if (MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, utf8, -1, *out, length) != length) {
    free(*out);
    *out = NULL;
    return READER_DIAG_ARGUMENT;
  }
  return READER_DIAG_OK;
}

/* "<target>.reader-diagnostic.tmp-<pid>-<attempt>" in UTF-16. */
static wchar_t *rd_temp_path(const wchar_t *target, unsigned attempt) {
  char tag[64];
  size_t target_length = wcslen(target);
  size_t tag_length;
  size_t index;
  wchar_t *path;
  int written = snprintf(tag, sizeof(tag), RD_TEMP_TAG "%lu-%u",
                         (unsigned long)GetCurrentProcessId(), attempt);
  if (written <= 0 || (size_t)written >= sizeof(tag)) return NULL;
  tag_length = (size_t)written;
  path = (wchar_t *)calloc(target_length + tag_length + 1u, sizeof(wchar_t));
  if (!path) return NULL;
  memcpy(path, target, target_length * sizeof(wchar_t));
  for (index = 0; index < tag_length; ++index)
    path[target_length + index] = (wchar_t)(unsigned char)tag[index];
  path[target_length + tag_length] = L'\0';
  return path;
}

/* True when the path itself exists (file, directory or dangling reparse point).
   Used only after a failed commit attempt to tell EXISTS from a real I/O error. */
static int rd_target_exists(const wchar_t *target) {
  return GetFileAttributesW(target) != INVALID_FILE_ATTRIBUTES;
}

static reader_diag_status rd_publish(const char *utf8_path, const void *data, size_t size,
                                    const reader_diag_control *control,
                                    reader_diag_error *error) {
  wchar_t *target = NULL;
  wchar_t *temp = NULL;
  HANDLE handle = INVALID_HANDLE_VALUE;
  DWORD last = 0;
  size_t offset = 0;
  unsigned attempt;
  reader_diag_status status = READER_DIAG_IO;

  status = rd_wide_path(utf8_path, &target);
  if (status != READER_DIAG_OK) {
    rd_error_set(error, status, 0,
                 status == READER_DIAG_MEMORY ? "out of memory" : "target path encoding");
    return status;
  }
  for (attempt = 0; attempt < RD_TEMP_ATTEMPTS; ++attempt) {
    temp = rd_temp_path(target, attempt);
    if (!temp) {
      free(target);
      rd_error_set(error, READER_DIAG_MEMORY, 0, "out of memory");
      return READER_DIAG_MEMORY;
    }
    handle = CreateFileW(temp, GENERIC_WRITE, 0, NULL, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, NULL);
    if (handle != INVALID_HANDLE_VALUE) break;
    last = GetLastError();
    free(temp);
    temp = NULL;
    if (last != ERROR_FILE_EXISTS && last != ERROR_ALREADY_EXISTS) {
      free(target);
      rd_error_set(error, READER_DIAG_IO, (int)last, "temporary file");
      return READER_DIAG_IO;
    }
  }
  if (handle == INVALID_HANDLE_VALUE) {
    free(target);
    rd_error_set(error, READER_DIAG_IO, (int)last, "temporary name");
    return READER_DIAG_IO;
  }
  while (offset < size) {
    DWORD chunk;
    DWORD done = 0;
    if (rd_cancel_requested(control)) {
      status = READER_DIAG_CANCELLED;
      goto fail;
    }
    chunk = (DWORD)((size - offset) < (size_t)RD_CHUNK_BYTES ? (size - offset)
                                                             : (size_t)RD_CHUNK_BYTES);
    if (!WriteFile(handle, (const char *)data + offset, chunk, &done, NULL) || done == 0) {
      last = GetLastError();
      status = READER_DIAG_IO;
      goto fail;
    }
    offset += (size_t)done;
  }
  if (!FlushFileBuffers(handle)) {
    last = GetLastError();
    status = READER_DIAG_IO;
    goto fail;
  }
  if (rd_cancel_requested(control)) {
    status = READER_DIAG_CANCELLED;
    goto fail;
  }
#ifdef READER_DIAGNOSTIC_TEST_HOOKS
  rd_test_pause_before_commit();
#endif
  CloseHandle(handle);
  handle = INVALID_HANDLE_VALUE;
  if (!MoveFileExW(temp, target, 0)) {
    last = GetLastError();
    if (last == ERROR_FILE_EXISTS || last == ERROR_ALREADY_EXISTS ||
        (last == ERROR_ACCESS_DENIED && rd_target_exists(target)))
      status = READER_DIAG_EXISTS;
    else
      status = READER_DIAG_IO;
    goto fail;
  }
  free(temp);
  free(target);
#ifdef READER_DIAGNOSTIC_TEST_HOOKS
  rd_test_pause_after_commit();
#endif
  if (error) reader_diag_error_clear(error);
  return READER_DIAG_OK;

fail:
  if (handle != INVALID_HANDLE_VALUE) CloseHandle(handle);
  DeleteFileW(temp);
  free(temp);
  free(target);
  rd_error_set(error, status, status == READER_DIAG_IO ? (int)last : 0,
               status == READER_DIAG_CANCELLED ? "write cancelled" : "publish");
  return status;
}

#else /* POSIX */

/* "<target>.reader-diagnostic.tmp-<pid>-<attempt>" as bytes; the target path is
   passed through unchanged, so no encoding assumption is made on POSIX. */
static char *rd_temp_path(const char *target, unsigned attempt) {
  char tag[64];
  size_t target_length = strlen(target);
  size_t tag_length;
  char *path;
  int written = snprintf(tag, sizeof(tag), RD_TEMP_TAG "%lu-%u", (unsigned long)getpid(),
                         attempt);
  if (written <= 0 || (size_t)written >= sizeof(tag)) return NULL;
  tag_length = (size_t)written;
  path = (char *)malloc(target_length + tag_length + 1u);
  if (!path) return NULL;
  memcpy(path, target, target_length);
  memcpy(path + target_length, tag, tag_length + 1u);
  return path;
}

/* lstat() succeeds for a dangling link and for a directory. Used only after a
   failed commit attempt to tell EXISTS from a real I/O error. */
static int rd_target_exists(const char *path) {
  struct stat information;
  return lstat(path, &information) == 0;
}

static reader_diag_status rd_publish(const char *utf8_path, const void *data, size_t size,
                                    const reader_diag_control *control,
                                    reader_diag_error *error) {
  char *temp = NULL;
  int descriptor = -1;
  int last = 0;
  size_t offset = 0;
  unsigned attempt;
  reader_diag_status status = READER_DIAG_IO;

  for (attempt = 0; attempt < RD_TEMP_ATTEMPTS; ++attempt) {
    temp = rd_temp_path(utf8_path, attempt);
    if (!temp) {
      rd_error_set(error, READER_DIAG_MEMORY, 0, "out of memory");
      return READER_DIAG_MEMORY;
    }
    descriptor = open(temp, O_WRONLY | O_CREAT | O_EXCL, 0666);
    if (descriptor >= 0) break;
    last = errno;
    free(temp);
    temp = NULL;
    if (last != EEXIST) {
      rd_error_set(error, READER_DIAG_IO, last, "temporary file");
      return READER_DIAG_IO;
    }
  }
  if (descriptor < 0) {
    rd_error_set(error, READER_DIAG_IO, last, "temporary name");
    return READER_DIAG_IO;
  }
  while (offset < size) {
    ssize_t done;
    size_t chunk = (size - offset) < (size_t)RD_CHUNK_BYTES ? (size - offset)
                                                            : (size_t)RD_CHUNK_BYTES;
    if (rd_cancel_requested(control)) {
      status = READER_DIAG_CANCELLED;
      goto fail;
    }
    done = write(descriptor, (const char *)data + offset, chunk);
    if (done < 0) {
      if (errno == EINTR) continue;
      last = errno;
      status = READER_DIAG_IO;
      goto fail;
    }
    if (done == 0) {
      last = EIO;
      status = READER_DIAG_IO;
      goto fail;
    }
    offset += (size_t)done;
  }
  if (fsync(descriptor) != 0) {
    last = errno;
    status = READER_DIAG_IO;
    goto fail;
  }
  if (close(descriptor) != 0) {
    last = errno;
    descriptor = -1;
    status = READER_DIAG_IO;
    goto fail;
  }
  descriptor = -1;
  if (rd_cancel_requested(control)) {
    status = READER_DIAG_CANCELLED;
    goto fail;
  }
#ifdef READER_DIAGNOSTIC_TEST_HOOKS
  rd_test_pause_before_commit();
#endif
  if (link(temp, utf8_path) != 0) {
    last = errno;
    status = (last == EEXIST || (last == EPERM && rd_target_exists(utf8_path)))
                 ? READER_DIAG_EXISTS
                 : READER_DIAG_IO;
    goto fail;
  }
  (void)unlink(temp);
  free(temp);
#ifdef READER_DIAGNOSTIC_TEST_HOOKS
  rd_test_pause_after_commit();
#endif
  if (error) reader_diag_error_clear(error);
  return READER_DIAG_OK;

fail:
  if (descriptor >= 0) (void)close(descriptor);
  (void)unlink(temp);
  free(temp);
  rd_error_set(error, status, status == READER_DIAG_IO ? last : 0,
               status == READER_DIAG_CANCELLED ? "write cancelled" : "publish");
  return status;
}

#endif

reader_diag_status rd_write_new_file(const char *utf8_path, const void *data, size_t size,
                                     const reader_diag_control *control,
                                     reader_diag_error *error) {
  if (!utf8_path || utf8_path[0] == '\0') {
    rd_error_set(error, READER_DIAG_ARGUMENT, 0, "target path");
    return READER_DIAG_ARGUMENT;
  }
  if (!data && size != 0u) {
    rd_error_set(error, READER_DIAG_ARGUMENT, 0, "report bytes");
    return READER_DIAG_ARGUMENT;
  }
  if (rd_cancel_requested(control)) {
    rd_error_set(error, READER_DIAG_CANCELLED, 0, "write cancelled");
    return READER_DIAG_CANCELLED;
  }
  return rd_publish(utf8_path, data, size, control, error);
}