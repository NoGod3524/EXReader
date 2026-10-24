/* SPDX-License-Identifier: MIT */
#if defined(_WIN32)
#define _CRT_SECURE_NO_WARNINGS 1
#endif
#include "internal.h"

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if defined(_WIN32)
#define WIN32_LEAN_AND_MEAN 1
#include <windows.h>
#include <wchar.h>
#else
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>
#endif

static unsigned rp_temp_counter;

#if defined(READER_PREFERENCES_TEST_HOOKS)
static void rp_sleep_ms(unsigned milliseconds) {
#if defined(_WIN32)
  Sleep(milliseconds);
#else
  struct timespec request;
  request.tv_sec = (time_t)(milliseconds / 1000u);
  request.tv_nsec = (long)(milliseconds % 1000u) * 1000000L;
  while (nanosleep(&request, &request) != 0 && errno == EINTR) { }
#endif
}

static void rp_test_pause(const char *variable) {
  const char *value = getenv(variable);
  const char *ready;
  unsigned milliseconds;
  FILE *marker;
  if (!value || value[0] == '\0') return;
  milliseconds = (unsigned)strtoul(value, NULL, 10);
  ready = getenv("EXR_PREFERENCES_TEST_READY_FILE");
  if (ready && ready[0] != '\0') {
    marker = fopen(ready, "wb");
    if (marker) {
      (void)fputs("ready", marker);
      (void)fclose(marker);
    }
  }
  rp_sleep_ms(milliseconds ? milliseconds : 30000u);
}

static int rp_test_fail_before_rename(void) {
  const char *value = getenv("EXR_PREFERENCES_TEST_FAIL_BEFORE_RENAME");
  return value && value[0] != '\0' && value[0] != '0';
}
#endif

#if defined(_WIN32)

static wchar_t *rp_win_path(const char *utf8, reader_preferences_error *error) {
  int needed;
  wchar_t *raw;
  wchar_t *full;
  DWORD length;
  size_t n;
  if (!utf8 || utf8[0] == '\0') {
    rp_error_set(error, READER_PREFERENCES_ARGUMENT, 0, 0, "empty path");
    return NULL;
  }
  needed = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, utf8, -1, NULL, 0);
  if (needed <= 0) {
    rp_error_set(error, READER_PREFERENCES_ARGUMENT, 0, 0, "path is not valid UTF-8");
    return NULL;
  }
  raw = (wchar_t *)malloc((size_t)needed * sizeof(wchar_t));
  if (!raw) {
    rp_error_set(error, READER_PREFERENCES_IO, ENOMEM, 0, "out of memory");
    return NULL;
  }
  if (MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, utf8, -1, raw, needed) != needed) {
    free(raw);
    rp_error_set(error, READER_PREFERENCES_ARGUMENT, 0, 0, "path is not valid UTF-8");
    return NULL;
  }
  length = GetFullPathNameW(raw, 0, NULL, NULL);
  if (length == 0) {
    DWORD code = GetLastError();
    free(raw);
    rp_error_set(error, READER_PREFERENCES_IO, (int)code, 0, "cannot resolve path");
    return NULL;
  }
  full = (wchar_t *)malloc(((size_t)length + 1u) * sizeof(wchar_t));
  if (!full) {
    free(raw);
    rp_error_set(error, READER_PREFERENCES_IO, ENOMEM, 0, "out of memory");
    return NULL;
  }
  if (GetFullPathNameW(raw, length + 1u, full, NULL) == 0) {
    DWORD code = GetLastError();
    free(raw); free(full);
    rp_error_set(error, READER_PREFERENCES_IO, (int)code, 0, "cannot resolve path");
    return NULL;
  }
  free(raw);
  if (wcsncmp(full, L"\\\\?\\", 4) == 0) return full;
  n = wcslen(full);
  if (n >= 248u) {
    wchar_t *prefixed;
    const wchar_t *tail = full;
    const wchar_t *prefix = L"\\\\?\\";
    size_t prefix_length = 4u;
    if (n >= 2u && full[0] == L'\\' && full[1] == L'\\') {
      tail = full + 2;
      prefix = L"\\\\?\\UNC\\";
      prefix_length = 8u;
      n -= 2u;
    }
    prefixed = (wchar_t *)malloc((prefix_length + n + 1u) * sizeof(wchar_t));
    if (!prefixed) {
      free(full);
      rp_error_set(error, READER_PREFERENCES_IO, ENOMEM, 0, "out of memory");
      return NULL;
    }
    memcpy(prefixed, prefix, prefix_length * sizeof(wchar_t));
    memcpy(prefixed + prefix_length, tail, (n + 1u) * sizeof(wchar_t));
    free(full);
    return prefixed;
  }
  return full;
}

static wchar_t *rp_win_temp_path(const wchar_t *target) {
  size_t length = wcslen(target);
  wchar_t *temporary = (wchar_t *)malloc((length + 64u) * sizeof(wchar_t));
  if (!temporary) return NULL;
  if (swprintf(temporary, length + 64u, L"%ls.tmp-%lu-%u", target,
               (unsigned long)GetCurrentProcessId(), ++rp_temp_counter) < 0) {
    free(temporary);
    return NULL;
  }
  return temporary;
}

static reader_preferences_status rp_win_read(const char *utf8_path, size_t max_bytes,
                                             const reader_preferences_control *control,
                                             unsigned char **data, size_t *size,
                                             reader_preferences_error *error) {
  wchar_t *path = rp_win_path(utf8_path, error);
  HANDLE handle;
  LARGE_INTEGER length;
  unsigned char *buffer;
  size_t total = 0;
  DWORD code;
  if (!path) return error && error->status != READER_PREFERENCES_OK ? error->status : READER_PREFERENCES_ARGUMENT;
  handle = CreateFileW(path, GENERIC_READ,
                       FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                       NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
  if (handle == INVALID_HANDLE_VALUE) {
    code = GetLastError();
    free(path);
    rp_error_set(error, READER_PREFERENCES_IO, (int)code, 0, "cannot open preferences file");
    return READER_PREFERENCES_IO;
  }
  if (!GetFileSizeEx(handle, &length) || length.QuadPart < 0) {
    code = GetLastError();
    CloseHandle(handle); free(path);
    rp_error_set(error, READER_PREFERENCES_IO, (int)code, 0, "cannot size preferences file");
    return READER_PREFERENCES_IO;
  }
  if ((uint64_t)length.QuadPart > (uint64_t)max_bytes ||
      (uint64_t)length.QuadPart > (uint64_t)SIZE_MAX) {
    CloseHandle(handle); free(path);
    rp_error_set(error, READER_PREFERENCES_LIMIT, 0, 0,
                 "file is %llu bytes, limit is %llu",
                 (unsigned long long)length.QuadPart, (unsigned long long)max_bytes);
    return READER_PREFERENCES_LIMIT;
  }
  *size = (size_t)length.QuadPart;
  buffer = (unsigned char *)malloc(*size ? *size : 1u);
  if (!buffer) {
    CloseHandle(handle); free(path);
    rp_error_set(error, READER_PREFERENCES_IO, ENOMEM, 0, "out of memory");
    return READER_PREFERENCES_IO;
  }
  while (total < *size) {
    DWORD chunk = (DWORD)((*size - total) > 0x100000u ? 0x100000u : (*size - total));
    DWORD got = 0;
    if (rp_cancel_requested(control)) {
      CloseHandle(handle); free(path); free(buffer);
      rp_error_set(error, READER_PREFERENCES_CANCELLED, 0, 0, "load cancelled while reading");
      return READER_PREFERENCES_CANCELLED;
    }
    if (!ReadFile(handle, buffer + total, chunk, &got, NULL) || got == 0) {
      code = GetLastError();
      CloseHandle(handle); free(path); free(buffer);
      rp_error_set(error, READER_PREFERENCES_IO, (int)code, 0, "cannot read preferences file");
      return READER_PREFERENCES_IO;
    }
    total += got;
  }
  CloseHandle(handle);
  free(path);
  *data = buffer;
  return READER_PREFERENCES_OK;
}

static reader_preferences_status rp_win_write(const char *utf8_path, const void *data,
                                              size_t size,
                                              const reader_preferences_control *control,
                                              reader_preferences_error *error) {
  wchar_t *target = rp_win_path(utf8_path, error);
  wchar_t *temporary = NULL;
  HANDLE handle = INVALID_HANDLE_VALUE;
  size_t total = 0;
  DWORD code = 0;
  int produced = 0;
  if (!target) return error && error->status != READER_PREFERENCES_OK ? error->status : READER_PREFERENCES_ARGUMENT;
  while (rp_temp_counter < 1000000u) {
    free(temporary);
    temporary = rp_win_temp_path(target);
    if (!temporary) {
      free(target);
      rp_error_set(error, READER_PREFERENCES_IO, ENOMEM, 0, "out of memory");
      return READER_PREFERENCES_IO;
    }
    handle = CreateFileW(temporary, GENERIC_WRITE, 0, NULL, CREATE_NEW,
                         FILE_ATTRIBUTE_NORMAL, NULL);
    if (handle != INVALID_HANDLE_VALUE) { produced = 1; break; }
    code = GetLastError();
    if (code != ERROR_FILE_EXISTS && code != ERROR_ALREADY_EXISTS) break;
  }
  if (!produced) {
    free(temporary); free(target);
    rp_error_set(error, READER_PREFERENCES_IO, (int)code, 0, "cannot create temporary file");
    return READER_PREFERENCES_IO;
  }
  while (total < size) {
    DWORD chunk = (DWORD)((size - total) > 0x100000u ? 0x100000u : (size - total));
    DWORD wrote = 0;
    if (rp_cancel_requested(control)) {
      CloseHandle(handle); DeleteFileW(temporary);
      free(temporary); free(target);
      rp_error_set(error, READER_PREFERENCES_CANCELLED, 0, 0, "save cancelled while writing");
      return READER_PREFERENCES_CANCELLED;
    }
    if (!WriteFile(handle, (const unsigned char *)data + total, chunk, &wrote, NULL) ||
        wrote == 0) {
      code = GetLastError();
      CloseHandle(handle); DeleteFileW(temporary);
      free(temporary); free(target);
      rp_error_set(error, READER_PREFERENCES_IO, (int)code, 0, "cannot write temporary file");
      return READER_PREFERENCES_IO;
    }
    total += wrote;
  }
  if (!FlushFileBuffers(handle)) {
    code = GetLastError();
    CloseHandle(handle); DeleteFileW(temporary);
    free(temporary); free(target);
    rp_error_set(error, READER_PREFERENCES_IO, (int)code, 0, "cannot flush temporary file");
    return READER_PREFERENCES_IO;
  }
  if (!CloseHandle(handle)) {
    code = GetLastError();
    DeleteFileW(temporary); free(temporary); free(target);
    rp_error_set(error, READER_PREFERENCES_IO, (int)code, 0, "cannot close temporary file");
    return READER_PREFERENCES_IO;
  }
#ifdef READER_PREFERENCES_TEST_HOOKS
  if (rp_test_fail_before_rename()) {
    DeleteFileW(temporary); free(temporary); free(target);
    rp_error_set(error, READER_PREFERENCES_IO, 0, 0, "injected failure before rename");
    return READER_PREFERENCES_IO;
  }
  rp_test_pause("EXR_PREFERENCES_TEST_PAUSE_BEFORE_RENAME");
#endif
  if (rp_cancel_requested(control)) {
    DeleteFileW(temporary); free(temporary); free(target);
    rp_error_set(error, READER_PREFERENCES_CANCELLED, 0, 0, "save cancelled before replace");
    return READER_PREFERENCES_CANCELLED;
  }
  {
    int attempt;
    int replaced = 0;
    for (attempt = 0; attempt < 50; ++attempt) {
      if (MoveFileExW(temporary, target, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)) {
        replaced = 1;
        break;
      }
      code = GetLastError();
      if (code != ERROR_SHARING_VIOLATION && code != ERROR_LOCK_VIOLATION &&
          code != ERROR_ACCESS_DENIED) break;
      Sleep(10);
    }
    if (!replaced) {
      DeleteFileW(temporary); free(temporary); free(target);
      rp_error_set(error, READER_PREFERENCES_IO, (int)code, 0, "cannot atomically replace preferences file");
      return READER_PREFERENCES_IO;
    }
  }
  free(temporary);
  free(target);
#ifdef READER_PREFERENCES_TEST_HOOKS
  rp_test_pause("EXR_PREFERENCES_TEST_PAUSE_AFTER_RENAME");
#endif
  return READER_PREFERENCES_OK;
}

#else

static char *rp_posix_temp_path(const char *target) {
  const char *slash = strrchr(target, '/');
  size_t directory_length;
  char *temporary;
  if (!slash) directory_length = 1u;
  else if (slash == target) directory_length = 1u;
  else directory_length = (size_t)(slash - target);
  temporary = (char *)malloc(directory_length + 64u);
  if (!temporary) return NULL;
  if (snprintf(temporary, directory_length + 64u, "%.*s/.reader-preferences.tmp-%ld-%u",
               (int)directory_length, target, (long)getpid(), ++rp_temp_counter) < 0) {
    free(temporary);
    return NULL;
  }
  return temporary;
}

static reader_preferences_status rp_posix_read(const char *path, size_t max_bytes,
                                               const reader_preferences_control *control,
                                               unsigned char **data, size_t *size,
                                               reader_preferences_error *error) {
  int descriptor;
  struct stat info;
  unsigned char *buffer;
  size_t total = 0;
  descriptor = open(path, O_RDONLY
#if defined(O_CLOEXEC)
                    | O_CLOEXEC
#endif
  );
  if (descriptor < 0) {
    int code = errno;
    rp_error_set(error, READER_PREFERENCES_IO, code, 0, "cannot open preferences file");
    return READER_PREFERENCES_IO;
  }
  if (fstat(descriptor, &info) != 0) {
    int code = errno;
    close(descriptor);
    rp_error_set(error, READER_PREFERENCES_IO, code, 0, "cannot size preferences file");
    return READER_PREFERENCES_IO;
  }
  if (!S_ISREG(info.st_mode)) {
    close(descriptor);
    rp_error_set(error, READER_PREFERENCES_IO, EISDIR, 0, "preferences path is not a regular file");
    return READER_PREFERENCES_IO;
  }
  if ((uintmax_t)info.st_size > (uintmax_t)max_bytes ||
      (uintmax_t)info.st_size > (uintmax_t)SIZE_MAX) {
    close(descriptor);
    rp_error_set(error, READER_PREFERENCES_LIMIT, 0, 0,
                 "file is %llu bytes, limit is %llu",
                 (unsigned long long)info.st_size, (unsigned long long)max_bytes);
    return READER_PREFERENCES_LIMIT;
  }
  *size = (size_t)info.st_size;
  buffer = (unsigned char *)malloc(*size ? *size : 1u);
  if (!buffer) {
    close(descriptor);
    rp_error_set(error, READER_PREFERENCES_IO, ENOMEM, 0, "out of memory");
    return READER_PREFERENCES_IO;
  }
  while (total < *size) {
    size_t remaining = *size - total;
    size_t chunk = remaining > 0x100000u ? 0x100000u : remaining;
    ssize_t got;
    if (rp_cancel_requested(control)) {
      close(descriptor); free(buffer);
      rp_error_set(error, READER_PREFERENCES_CANCELLED, 0, 0, "load cancelled while reading");
      return READER_PREFERENCES_CANCELLED;
    }
    got = read(descriptor, buffer + total, chunk);
    if (got < 0) {
      if (errno == EINTR) continue;
      {
        int code = errno;
        close(descriptor); free(buffer);
        rp_error_set(error, READER_PREFERENCES_IO, code, 0, "cannot read preferences file");
        return READER_PREFERENCES_IO;
      }
    }
    if (got == 0) {
      close(descriptor); free(buffer);
      rp_error_set(error, READER_PREFERENCES_IO, 0, 0, "preferences file ended early");
      return READER_PREFERENCES_IO;
    }
    total += (size_t)got;
  }
  close(descriptor);
  *data = buffer;
  return READER_PREFERENCES_OK;
}

static reader_preferences_status rp_posix_write(const char *path, const void *data,
                                                size_t size,
                                                const reader_preferences_control *control,
                                                reader_preferences_error *error) {
  char *temporary = NULL;
  int descriptor = -1;
  size_t total = 0;
  int code = 0;
  int attempts;
  for (attempts = 0; attempts < 16; ++attempts) {
    free(temporary);
    temporary = rp_posix_temp_path(path);
    if (!temporary) {
      rp_error_set(error, READER_PREFERENCES_IO, ENOMEM, 0, "out of memory");
      return READER_PREFERENCES_IO;
    }
    descriptor = open(temporary, O_WRONLY | O_CREAT | O_EXCL
#if defined(O_CLOEXEC)
                      | O_CLOEXEC
#endif
                      , 0600);
    if (descriptor >= 0) break;
    code = errno;
    if (code != EEXIST) break;
  }
  if (descriptor < 0) {
    free(temporary);
    rp_error_set(error, READER_PREFERENCES_IO, code, 0, "cannot create temporary file");
    return READER_PREFERENCES_IO;
  }
  while (total < size) {
    size_t remaining = size - total;
    size_t chunk = remaining > 0x100000u ? 0x100000u : remaining;
    ssize_t wrote;
    if (rp_cancel_requested(control)) {
      close(descriptor); unlink(temporary); free(temporary);
      rp_error_set(error, READER_PREFERENCES_CANCELLED, 0, 0, "save cancelled while writing");
      return READER_PREFERENCES_CANCELLED;
    }
    wrote = write(descriptor, (const unsigned char *)data + total, chunk);
    if (wrote < 0) {
      if (errno == EINTR) continue;
      code = errno;
      close(descriptor); unlink(temporary); free(temporary);
      rp_error_set(error, READER_PREFERENCES_IO, code, 0, "cannot write temporary file");
      return READER_PREFERENCES_IO;
    }
    if (wrote == 0) {
      close(descriptor); unlink(temporary); free(temporary);
      rp_error_set(error, READER_PREFERENCES_IO, 0, 0, "temporary file write stopped");
      return READER_PREFERENCES_IO;
    }
    total += (size_t)wrote;
  }
  if (fsync(descriptor) != 0) {
    code = errno;
    close(descriptor); unlink(temporary); free(temporary);
    rp_error_set(error, READER_PREFERENCES_IO, code, 0, "cannot flush temporary file");
    return READER_PREFERENCES_IO;
  }
  if (close(descriptor) != 0) {
    code = errno;
    unlink(temporary); free(temporary);
    rp_error_set(error, READER_PREFERENCES_IO, code, 0, "cannot close temporary file");
    return READER_PREFERENCES_IO;
  }
#ifdef READER_PREFERENCES_TEST_HOOKS
  if (rp_test_fail_before_rename()) {
    unlink(temporary); free(temporary);
    rp_error_set(error, READER_PREFERENCES_IO, 0, 0, "injected failure before rename");
    return READER_PREFERENCES_IO;
  }
  rp_test_pause("EXR_PREFERENCES_TEST_PAUSE_BEFORE_RENAME");
#endif
  if (rp_cancel_requested(control)) {
    unlink(temporary); free(temporary);
    rp_error_set(error, READER_PREFERENCES_CANCELLED, 0, 0, "save cancelled before replace");
    return READER_PREFERENCES_CANCELLED;
  }
  if (rename(temporary, path) != 0) {
    code = errno;
    unlink(temporary); free(temporary);
    rp_error_set(error, READER_PREFERENCES_IO, code, 0, "cannot atomically replace preferences file");
    return READER_PREFERENCES_IO;
  }
  free(temporary);
  {
    const char *slash = strrchr(path, '/');
    char directory[4096];
    int directory_descriptor = -1;
    if (!slash) {
      (void)snprintf(directory, sizeof(directory), ".");
      directory_descriptor = open(directory, O_RDONLY
#if defined(O_DIRECTORY)
                                  | O_DIRECTORY
#endif
      );
    } else {
      size_t length = slash == path ? 1u : (size_t)(slash - path);
      if (length + 1u < sizeof(directory)) {
        memcpy(directory, path, length);
        directory[length] = '\0';
        directory_descriptor = open(directory, O_RDONLY
#if defined(O_DIRECTORY)
                                    | O_DIRECTORY
#endif
        );
      }
    }
    if (directory_descriptor >= 0) {
      (void)fsync(directory_descriptor);
      (void)close(directory_descriptor);
    }
  }
#ifdef READER_PREFERENCES_TEST_HOOKS
  rp_test_pause("EXR_PREFERENCES_TEST_PAUSE_AFTER_RENAME");
#endif
  return READER_PREFERENCES_OK;
}

#endif

reader_preferences_status rp_read_file(const char *utf8_path, size_t max_bytes,
                                       const reader_preferences_control *control,
                                       unsigned char **data, size_t *size,
                                       reader_preferences_error *error) {
  if (data) *data = NULL;
  if (size) *size = 0;
#if defined(_WIN32)
  return rp_win_read(utf8_path, max_bytes, control, data, size, error);
#else
  return rp_posix_read(utf8_path, max_bytes, control, data, size, error);
#endif
}

reader_preferences_status rp_write_file_atomic(const char *utf8_path, const void *data,
                                               size_t size,
                                               const reader_preferences_control *control,
                                               reader_preferences_error *error) {
#if defined(_WIN32)
  return rp_win_write(utf8_path, data, size, control, error);
#else
  return rp_posix_write(utf8_path, data, size, control, error);
#endif
}
