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
#include <sys/file.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>
#endif

#if defined(READER_ACCOUNT_PROFILES_TEST_HOOKS)
static void ap_test_pause(const char *variable) {
  const char *value = getenv(variable);
  const char *ready;
  unsigned milliseconds;
  FILE *marker;
  if (!value || value[0] == '\0') return;
  milliseconds = (unsigned)strtoul(value, NULL, 10);
  ready = getenv("EXR_ACCOUNT_PROFILES_TEST_READY_FILE");
  if (ready && ready[0] != '\0') {
    marker = fopen(ready, "wb");
    if (marker) {
      (void)fputs("ready", marker);
      (void)fclose(marker);
    }
  }
  ap_sleep_ms(milliseconds ? milliseconds : 30000u);
}

static int ap_test_fail_before_rename(void) {
  const char *value = getenv("EXR_ACCOUNT_PROFILES_TEST_FAIL_BEFORE_RENAME");
  return value && value[0] != '\0' && value[0] != '0';
}

static int ap_test_cancel_before_rename(void) {
  const char *value = getenv("EXR_ACCOUNT_PROFILES_TEST_CANCEL_BEFORE_RENAME");
  return value && value[0] != '\0' && value[0] != '0';
}
#endif

void ap_sleep_ms(unsigned milliseconds) {
#if defined(_WIN32)
  Sleep(milliseconds);
#else
  struct timespec request;
  request.tv_sec = (time_t)(milliseconds / 1000u);
  request.tv_nsec = (long)(milliseconds % 1000u) * 1000000L;
  while (nanosleep(&request, &request) != 0 && errno == EINTR) { }
#endif
}

#if defined(_WIN32)

static wchar_t *ap_win_path(const char *utf8, reader_account_profiles_error *error) {
  int needed;
  wchar_t *raw;
  wchar_t *full;
  DWORD length;
  size_t n;
  if (!utf8 || utf8[0] == '\0') {
    ap_error_set(error, READER_ACCOUNT_PROFILES_ARGUMENT, 0, 0, "empty path");
    return NULL;
  }
  needed = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, utf8, -1, NULL, 0);
  if (needed <= 0) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_ARGUMENT, 0, 0, "path is not valid UTF-8");
    return NULL;
  }
  raw = (wchar_t *)malloc((size_t)needed * sizeof(wchar_t));
  if (!raw) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_IO, ENOMEM, 0, "out of memory");
    return NULL;
  }
  if (MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, utf8, -1, raw, needed) != needed) {
    free(raw);
    ap_error_set(error, READER_ACCOUNT_PROFILES_ARGUMENT, 0, 0, "path is not valid UTF-8");
    return NULL;
  }
  length = GetFullPathNameW(raw, 0, NULL, NULL);
  if (length == 0) {
    DWORD code = GetLastError();
    free(raw);
    ap_error_set(error, READER_ACCOUNT_PROFILES_IO, (int)code, 0, "cannot resolve path");
    return NULL;
  }
  full = (wchar_t *)malloc(((size_t)length + 1u) * sizeof(wchar_t));
  if (!full) {
    free(raw);
    ap_error_set(error, READER_ACCOUNT_PROFILES_IO, ENOMEM, 0, "out of memory");
    return NULL;
  }
  if (GetFullPathNameW(raw, length + 1u, full, NULL) == 0) {
    DWORD code = GetLastError();
    free(raw);
    free(full);
    ap_error_set(error, READER_ACCOUNT_PROFILES_IO, (int)code, 0, "cannot resolve path");
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
      ap_error_set(error, READER_ACCOUNT_PROFILES_IO, ENOMEM, 0, "out of memory");
      return NULL;
    }
    memcpy(prefixed, prefix, prefix_length * sizeof(wchar_t));
    memcpy(prefixed + prefix_length, tail, (n + 1u) * sizeof(wchar_t));
    free(full);
    return prefixed;
  }
  return full;
}

static reader_account_profiles_status ap_win_inspect(const char *path, ap_entry_kind *kind,
                                                     uint64_t *size, uint32_t *link_count,
                                                     reader_account_profiles_error *error) {
  wchar_t *wide = ap_win_path(path, error);
  HANDLE handle;
  BY_HANDLE_FILE_INFORMATION info;
  DWORD code;
  if (!wide) return error && error->status != READER_ACCOUNT_PROFILES_OK
                          ? error->status : READER_ACCOUNT_PROFILES_ARGUMENT;
  handle = CreateFileW(wide, FILE_READ_ATTRIBUTES,
                       FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, NULL,
                       OPEN_EXISTING,
                       FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS, NULL);
  if (handle == INVALID_HANDLE_VALUE) {
    code = GetLastError();
    free(wide);
    if (code == ERROR_FILE_NOT_FOUND || code == ERROR_PATH_NOT_FOUND) {
      *kind = AP_ENTRY_MISSING;
      if (size) *size = 0;
      if (link_count) *link_count = 0;
      return READER_ACCOUNT_PROFILES_OK;
    }
    ap_error_set(error, READER_ACCOUNT_PROFILES_IO, (int)code, 0, "cannot inspect store entry");
    return READER_ACCOUNT_PROFILES_IO;
  }
  if (!GetFileInformationByHandle(handle, &info)) {
    code = GetLastError();
    CloseHandle(handle);
    free(wide);
    ap_error_set(error, READER_ACCOUNT_PROFILES_IO, (int)code, 0, "cannot inspect store entry");
    return READER_ACCOUNT_PROFILES_IO;
  }
  CloseHandle(handle);
  free(wide);
  if ((info.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT) != 0) *kind = AP_ENTRY_LINK;
  else if ((info.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) != 0) *kind = AP_ENTRY_DIRECTORY;
  else *kind = AP_ENTRY_FILE;
  if (size) *size = ((uint64_t)info.nFileSizeHigh << 32) | (uint64_t)info.nFileSizeLow;
  if (link_count) *link_count = (uint32_t)info.nNumberOfLinks;
  return READER_ACCOUNT_PROFILES_OK;
}

static reader_account_profiles_status ap_win_read(const char *path, size_t max_bytes,
                                                  unsigned char **data, size_t *size,
                                                  int *present,
                                                  const reader_account_profiles_control *control,
                                                  reader_account_profiles_error *error) {
  wchar_t *wide = ap_win_path(path, error);
  HANDLE handle;
  LARGE_INTEGER length;
  unsigned char *buffer;
  size_t total = 0;
  DWORD code;
  if (!wide) return error && error->status != READER_ACCOUNT_PROFILES_OK
                          ? error->status : READER_ACCOUNT_PROFILES_ARGUMENT;
  handle = CreateFileW(wide, GENERIC_READ,
                       FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, NULL,
                       OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
  if (handle == INVALID_HANDLE_VALUE) {
    code = GetLastError();
    free(wide);
    if (code == ERROR_FILE_NOT_FOUND || code == ERROR_PATH_NOT_FOUND) {
      *present = 0;
      *data = NULL;
      *size = 0;
      return READER_ACCOUNT_PROFILES_OK;
    }
    ap_error_set(error, READER_ACCOUNT_PROFILES_IO, (int)code, 0, "cannot open store document");
    return READER_ACCOUNT_PROFILES_IO;
  }
  if (!GetFileSizeEx(handle, &length) || length.QuadPart < 0) {
    code = GetLastError();
    CloseHandle(handle);
    free(wide);
    ap_error_set(error, READER_ACCOUNT_PROFILES_IO, (int)code, 0, "cannot size store document");
    return READER_ACCOUNT_PROFILES_IO;
  }
  if ((uint64_t)length.QuadPart > (uint64_t)max_bytes ||
      (uint64_t)length.QuadPart > (uint64_t)SIZE_MAX) {
    CloseHandle(handle);
    free(wide);
    ap_error_set(error, READER_ACCOUNT_PROFILES_LIMIT, 0, 0,
                 "document is %llu bytes, limit is %llu",
                 (unsigned long long)length.QuadPart, (unsigned long long)max_bytes);
    return READER_ACCOUNT_PROFILES_LIMIT;
  }
  *size = (size_t)length.QuadPart;
  buffer = (unsigned char *)malloc(*size ? *size : 1u);
  if (!buffer) {
    CloseHandle(handle);
    free(wide);
    ap_error_set(error, READER_ACCOUNT_PROFILES_IO, ENOMEM, 0, "out of memory");
    return READER_ACCOUNT_PROFILES_IO;
  }
  while (total < *size) {
    DWORD chunk = (DWORD)((*size - total) > 0x100000u ? 0x100000u : (*size - total));
    DWORD got = 0;
    if (ap_cancel_requested(control)) {
      CloseHandle(handle);
      free(wide);
      free(buffer);
      ap_error_set(error, READER_ACCOUNT_PROFILES_CANCELLED, 0, 0, "load cancelled while reading");
      return READER_ACCOUNT_PROFILES_CANCELLED;
    }
    if (!ReadFile(handle, buffer + total, chunk, &got, NULL) || got == 0) {
      code = GetLastError();
      CloseHandle(handle);
      free(wide);
      free(buffer);
      ap_error_set(error, READER_ACCOUNT_PROFILES_IO, (int)code, 0, "cannot read store document");
      return READER_ACCOUNT_PROFILES_IO;
    }
    total += got;
  }
  CloseHandle(handle);
  free(wide);
  *data = buffer;
  *present = 1;
  return READER_ACCOUNT_PROFILES_OK;
}

static reader_account_profiles_status ap_win_write(const char *path, const void *data, size_t size,
                                                   const reader_account_profiles_control *control,
                                                   reader_account_profiles_error *error) {
  wchar_t *target = ap_win_path(path, error);
  wchar_t *temporary = NULL;
  HANDLE handle = INVALID_HANDLE_VALUE;
  size_t total = 0;
  size_t length;
  DWORD code = 0;
  ap_entry_kind kind;
  if (!target) return error && error->status != READER_ACCOUNT_PROFILES_OK
                          ? error->status : READER_ACCOUNT_PROFILES_ARGUMENT;
  length = wcslen(target);
  temporary = (wchar_t *)malloc((length + 5u) * sizeof(wchar_t));
  if (!temporary) {
    free(target);
    ap_error_set(error, READER_ACCOUNT_PROFILES_IO, ENOMEM, 0, "out of memory");
    return READER_ACCOUNT_PROFILES_IO;
  }
  memcpy(temporary, target, length * sizeof(wchar_t));
  memcpy(temporary + length, L".tmp", 5u * sizeof(wchar_t));
  {
    char *utf8_temporary = (char *)malloc(strlen(path) + 5u);
    reader_account_profiles_status status;
    if (!utf8_temporary) {
      free(temporary);
      free(target);
      ap_error_set(error, READER_ACCOUNT_PROFILES_IO, ENOMEM, 0, "out of memory");
      return READER_ACCOUNT_PROFILES_IO;
    }
    memcpy(utf8_temporary, path, strlen(path));
    memcpy(utf8_temporary + strlen(path), ".tmp", 5u);
    status = ap_win_inspect(utf8_temporary, &kind, NULL, NULL, error);
    free(utf8_temporary);
    if (status != READER_ACCOUNT_PROFILES_OK) {
      free(temporary);
      free(target);
      return status;
    }
    if (kind == AP_ENTRY_LINK || kind == AP_ENTRY_DIRECTORY || kind == AP_ENTRY_OTHER) {
      free(temporary);
      free(target);
      ap_error_set(error, READER_ACCOUNT_PROFILES_UNSAFE_PATH, 0, 0,
                   "temporary document path is not a regular file");
      return READER_ACCOUNT_PROFILES_UNSAFE_PATH;
    }
    if (kind == AP_ENTRY_FILE && !DeleteFileW(temporary)) {
      code = GetLastError();
      free(temporary);
      free(target);
      ap_error_set(error, READER_ACCOUNT_PROFILES_IO, (int)code, 0,
                   "cannot remove a leftover temporary document");
      return READER_ACCOUNT_PROFILES_IO;
    }
  }
  handle = CreateFileW(temporary, GENERIC_WRITE, 0, NULL, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, NULL);
  if (handle == INVALID_HANDLE_VALUE) {
    code = GetLastError();
    free(temporary);
    free(target);
    ap_error_set(error, READER_ACCOUNT_PROFILES_IO, (int)code, 0, "cannot create temporary document");
    return READER_ACCOUNT_PROFILES_IO;
  }
  while (total < size) {
    DWORD chunk = (DWORD)((size - total) > 0x100000u ? 0x100000u : (size - total));
    DWORD wrote = 0;
    if (ap_cancel_requested(control)) {
      CloseHandle(handle);
      DeleteFileW(temporary);
      free(temporary);
      free(target);
      ap_error_set(error, READER_ACCOUNT_PROFILES_CANCELLED, 0, 0, "save cancelled while writing");
      return READER_ACCOUNT_PROFILES_CANCELLED;
    }
    if (!WriteFile(handle, (const unsigned char *)data + total, chunk, &wrote, NULL) || wrote == 0) {
      code = GetLastError();
      CloseHandle(handle);
      DeleteFileW(temporary);
      free(temporary);
      free(target);
      ap_error_set(error, READER_ACCOUNT_PROFILES_IO, (int)code, 0, "cannot write temporary document");
      return READER_ACCOUNT_PROFILES_IO;
    }
    total += wrote;
  }
  if (!FlushFileBuffers(handle)) {
    code = GetLastError();
    CloseHandle(handle);
    DeleteFileW(temporary);
    free(temporary);
    free(target);
    ap_error_set(error, READER_ACCOUNT_PROFILES_IO, (int)code, 0, "cannot flush temporary document");
    return READER_ACCOUNT_PROFILES_IO;
  }
  if (!CloseHandle(handle)) {
    code = GetLastError();
    DeleteFileW(temporary);
    free(temporary);
    free(target);
    ap_error_set(error, READER_ACCOUNT_PROFILES_IO, (int)code, 0, "cannot close temporary document");
    return READER_ACCOUNT_PROFILES_IO;
  }
#if defined(READER_ACCOUNT_PROFILES_TEST_HOOKS)
  if (ap_test_fail_before_rename()) {
    DeleteFileW(temporary);
    free(temporary);
    free(target);
    ap_error_set(error, READER_ACCOUNT_PROFILES_IO, 0, 0, "injected failure before replace");
    return READER_ACCOUNT_PROFILES_IO;
  }
  ap_test_pause("EXR_ACCOUNT_PROFILES_TEST_PAUSE_BEFORE_RENAME");
  if (ap_test_cancel_before_rename()) {
    DeleteFileW(temporary);
    free(temporary);
    free(target);
    ap_error_set(error, READER_ACCOUNT_PROFILES_CANCELLED, 0, 0,
                 "save cancelled immediately before replace");
    return READER_ACCOUNT_PROFILES_CANCELLED;
  }
#endif
  if (ap_cancel_requested(control)) {
    DeleteFileW(temporary);
    free(temporary);
    free(target);
    ap_error_set(error, READER_ACCOUNT_PROFILES_CANCELLED, 0, 0, "save cancelled before replace");
    return READER_ACCOUNT_PROFILES_CANCELLED;
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
      ap_sleep_ms(10u);
    }
    if (!replaced) {
      DeleteFileW(temporary);
      free(temporary);
      free(target);
      ap_error_set(error, READER_ACCOUNT_PROFILES_IO, (int)code, 0,
                   "cannot atomically replace the store document");
      return READER_ACCOUNT_PROFILES_IO;
    }
  }
  free(temporary);
  free(target);
#if defined(READER_ACCOUNT_PROFILES_TEST_HOOKS)
  ap_test_pause("EXR_ACCOUNT_PROFILES_TEST_PAUSE_AFTER_RENAME");
#endif
  return READER_ACCOUNT_PROFILES_OK;
}

static reader_account_profiles_status ap_win_lock(const char *store_dir, uint32_t timeout_ms,
                                                  const reader_account_profiles_control *control,
                                                  ap_lock *lock,
                                                  reader_account_profiles_error *error) {
  char *path = (char *)malloc(strlen(store_dir) + 8u);
  wchar_t *wide;
  ULONGLONG deadline;
  DWORD code = 0;
  if (!path) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_IO, ENOMEM, 0, "out of memory");
    return READER_ACCOUNT_PROFILES_IO;
  }
  (void)snprintf(path, strlen(store_dir) + 8u, "%s\\.lock", store_dir);
  wide = ap_win_path(path, error);
  free(path);
  if (!wide) return error && error->status != READER_ACCOUNT_PROFILES_OK
                          ? error->status : READER_ACCOUNT_PROFILES_ARGUMENT;
  deadline = GetTickCount64() + (ULONGLONG)timeout_ms;
  for (;;) {
    HANDLE handle = CreateFileW(wide, GENERIC_READ | GENERIC_WRITE, 0, NULL, OPEN_ALWAYS,
                                FILE_ATTRIBUTE_NORMAL, NULL);
    if (handle != INVALID_HANDLE_VALUE) {
      lock->handle = (void *)handle;
      lock->held = 1;
      free(wide);
#if defined(READER_ACCOUNT_PROFILES_TEST_HOOKS)
      ap_test_pause("EXR_ACCOUNT_PROFILES_TEST_PAUSE_AFTER_LOCK");
#endif
      return READER_ACCOUNT_PROFILES_OK;
    }
    code = GetLastError();
    if (code != ERROR_SHARING_VIOLATION && code != ERROR_LOCK_VIOLATION &&
        code != ERROR_ACCESS_DENIED) {
      free(wide);
      ap_error_set(error, READER_ACCOUNT_PROFILES_IO, (int)code, 0, "cannot open the writer lock");
      return READER_ACCOUNT_PROFILES_IO;
    }
    if (ap_cancel_requested(control)) {
      free(wide);
      ap_error_set(error, READER_ACCOUNT_PROFILES_CANCELLED, 0, 0, "cancelled while waiting for the lock");
      return READER_ACCOUNT_PROFILES_CANCELLED;
    }
    if (GetTickCount64() >= deadline) {
      free(wide);
      ap_error_set(error, READER_ACCOUNT_PROFILES_LOCKED, 0, 0,
                   "writer lock busy for %u ms", (unsigned)timeout_ms);
      return READER_ACCOUNT_PROFILES_LOCKED;
    }
    ap_sleep_ms(10u);
  }
}

static void ap_win_unlock(ap_lock *lock) {
  if (lock->held && lock->handle) CloseHandle((HANDLE)lock->handle);
  lock->handle = NULL;
  lock->held = 0;
}

static reader_account_profiles_status ap_win_ensure(const char *path,
                                                    reader_account_profiles_error *error) {
  wchar_t *wide = ap_win_path(path, error);
  ap_entry_kind kind;
  reader_account_profiles_status status;
  if (!wide) return error && error->status != READER_ACCOUNT_PROFILES_OK
                          ? error->status : READER_ACCOUNT_PROFILES_ARGUMENT;
  if (CreateDirectoryW(wide, NULL)) {
    free(wide);
    return READER_ACCOUNT_PROFILES_OK;
  }
  if (GetLastError() != ERROR_ALREADY_EXISTS) {
    DWORD code = GetLastError();
    free(wide);
    ap_error_set(error, READER_ACCOUNT_PROFILES_IO, (int)code, 0, "cannot create profile directory");
    return READER_ACCOUNT_PROFILES_IO;
  }
  free(wide);
  status = ap_win_inspect(path, &kind, NULL, NULL, error);
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  if (kind != AP_ENTRY_DIRECTORY) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_UNSAFE_PATH, 0, 0,
                 "profile directory path is not a real directory");
    return READER_ACCOUNT_PROFILES_UNSAFE_PATH;
  }
  return READER_ACCOUNT_PROFILES_OK;
}

#else

static reader_account_profiles_status ap_posix_read(const char *path, size_t max_bytes,
                                                    unsigned char **data, size_t *size,
                                                    int *present,
                                                    const reader_account_profiles_control *control,
                                                    reader_account_profiles_error *error) {
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
    if (code == ENOENT) {
      *present = 0;
      *data = NULL;
      *size = 0;
      return READER_ACCOUNT_PROFILES_OK;
    }
    ap_error_set(error, READER_ACCOUNT_PROFILES_IO, code, 0, "cannot open store document");
    return READER_ACCOUNT_PROFILES_IO;
  }
  if (fstat(descriptor, &info) != 0) {
    int code = errno;
    close(descriptor);
    ap_error_set(error, READER_ACCOUNT_PROFILES_IO, code, 0, "cannot size store document");
    return READER_ACCOUNT_PROFILES_IO;
  }
  if (!S_ISREG(info.st_mode)) {
    close(descriptor);
    ap_error_set(error, READER_ACCOUNT_PROFILES_UNSAFE_PATH, EINVAL, 0,
                 "store document is not a regular file");
    return READER_ACCOUNT_PROFILES_UNSAFE_PATH;
  }
  if ((uintmax_t)info.st_size > (uintmax_t)max_bytes ||
      (uintmax_t)info.st_size > (uintmax_t)SIZE_MAX) {
    close(descriptor);
    ap_error_set(error, READER_ACCOUNT_PROFILES_LIMIT, 0, 0,
                 "document is %llu bytes, limit is %llu",
                 (unsigned long long)info.st_size, (unsigned long long)max_bytes);
    return READER_ACCOUNT_PROFILES_LIMIT;
  }
  *size = (size_t)info.st_size;
  buffer = (unsigned char *)malloc(*size ? *size : 1u);
  if (!buffer) {
    close(descriptor);
    ap_error_set(error, READER_ACCOUNT_PROFILES_IO, ENOMEM, 0, "out of memory");
    return READER_ACCOUNT_PROFILES_IO;
  }
  while (total < *size) {
    size_t remaining = *size - total;
    size_t chunk = remaining > 0x100000u ? 0x100000u : remaining;
    ssize_t got;
    if (ap_cancel_requested(control)) {
      close(descriptor);
      free(buffer);
      ap_error_set(error, READER_ACCOUNT_PROFILES_CANCELLED, 0, 0, "load cancelled while reading");
      return READER_ACCOUNT_PROFILES_CANCELLED;
    }
    got = read(descriptor, buffer + total, chunk);
    if (got < 0) {
      if (errno == EINTR) continue;
      {
        int code = errno;
        close(descriptor);
        free(buffer);
        ap_error_set(error, READER_ACCOUNT_PROFILES_IO, code, 0, "cannot read store document");
        return READER_ACCOUNT_PROFILES_IO;
      }
    }
    if (got == 0) {
      close(descriptor);
      free(buffer);
      ap_error_set(error, READER_ACCOUNT_PROFILES_IO, 0, 0, "store document ended early");
      return READER_ACCOUNT_PROFILES_IO;
    }
    total += (size_t)got;
  }
  close(descriptor);
  *data = buffer;
  *present = 1;
  return READER_ACCOUNT_PROFILES_OK;
}

static reader_account_profiles_status ap_posix_write(const char *path, const void *data,
                                                     size_t size,
                                                     const reader_account_profiles_control *control,
                                                     reader_account_profiles_error *error) {
  size_t length = strlen(path);
  char *temporary = (char *)malloc(length + 5u);
  int descriptor = -1;
  size_t total = 0;
  int code = 0;
  struct stat leftover;
  if (!temporary) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_IO, ENOMEM, 0, "out of memory");
    return READER_ACCOUNT_PROFILES_IO;
  }
  memcpy(temporary, path, length);
  memcpy(temporary + length, ".tmp", 5u);
  if (lstat(temporary, &leftover) == 0) {
    if (S_ISLNK(leftover.st_mode) || !S_ISREG(leftover.st_mode)) {
      free(temporary);
      ap_error_set(error, READER_ACCOUNT_PROFILES_UNSAFE_PATH, 0, 0,
                   "temporary document path is not a regular file");
      return READER_ACCOUNT_PROFILES_UNSAFE_PATH;
    }
    if (unlink(temporary) != 0) {
      code = errno;
      free(temporary);
      ap_error_set(error, READER_ACCOUNT_PROFILES_IO, code, 0,
                   "cannot remove a leftover temporary document");
      return READER_ACCOUNT_PROFILES_IO;
    }
  } else if (errno != ENOENT) {
    code = errno;
    free(temporary);
    ap_error_set(error, READER_ACCOUNT_PROFILES_IO, code, 0,
                 "cannot inspect a leftover temporary document");
    return READER_ACCOUNT_PROFILES_IO;
  }
  descriptor = open(temporary, O_WRONLY | O_CREAT | O_EXCL
#if defined(O_CLOEXEC)
                    | O_CLOEXEC
#endif
#if defined(O_NOFOLLOW)
                    | O_NOFOLLOW
#endif
                    , 0600);
  if (descriptor < 0) {
    code = errno;
    free(temporary);
    ap_error_set(error, READER_ACCOUNT_PROFILES_IO, code, 0, "cannot create temporary document");
    return READER_ACCOUNT_PROFILES_IO;
  }
  while (total < size) {
    size_t remaining = size - total;
    size_t chunk = remaining > 0x100000u ? 0x100000u : remaining;
    ssize_t wrote;
    if (ap_cancel_requested(control)) {
      close(descriptor);
      unlink(temporary);
      free(temporary);
      ap_error_set(error, READER_ACCOUNT_PROFILES_CANCELLED, 0, 0, "save cancelled while writing");
      return READER_ACCOUNT_PROFILES_CANCELLED;
    }
    wrote = write(descriptor, (const unsigned char *)data + total, chunk);
    if (wrote < 0) {
      if (errno == EINTR) continue;
      code = errno;
      close(descriptor);
      unlink(temporary);
      free(temporary);
      ap_error_set(error, READER_ACCOUNT_PROFILES_IO, code, 0, "cannot write temporary document");
      return READER_ACCOUNT_PROFILES_IO;
    }
    if (wrote == 0) {
      close(descriptor);
      unlink(temporary);
      free(temporary);
      ap_error_set(error, READER_ACCOUNT_PROFILES_IO, 0, 0, "temporary document write stopped");
      return READER_ACCOUNT_PROFILES_IO;
    }
    total += (size_t)wrote;
  }
  if (fsync(descriptor) != 0) {
    code = errno;
    close(descriptor);
    unlink(temporary);
    free(temporary);
    ap_error_set(error, READER_ACCOUNT_PROFILES_IO, code, 0, "cannot flush temporary document");
    return READER_ACCOUNT_PROFILES_IO;
  }
  if (close(descriptor) != 0) {
    code = errno;
    unlink(temporary);
    free(temporary);
    ap_error_set(error, READER_ACCOUNT_PROFILES_IO, code, 0, "cannot close temporary document");
    return READER_ACCOUNT_PROFILES_IO;
  }
#if defined(READER_ACCOUNT_PROFILES_TEST_HOOKS)
  if (ap_test_fail_before_rename()) {
    unlink(temporary);
    free(temporary);
    ap_error_set(error, READER_ACCOUNT_PROFILES_IO, 0, 0, "injected failure before replace");
    return READER_ACCOUNT_PROFILES_IO;
  }
  ap_test_pause("EXR_ACCOUNT_PROFILES_TEST_PAUSE_BEFORE_RENAME");
  if (ap_test_cancel_before_rename()) {
    unlink(temporary);
    free(temporary);
    ap_error_set(error, READER_ACCOUNT_PROFILES_CANCELLED, 0, 0,
                 "save cancelled immediately before replace");
    return READER_ACCOUNT_PROFILES_CANCELLED;
  }
#endif
  if (ap_cancel_requested(control)) {
    unlink(temporary);
    free(temporary);
    ap_error_set(error, READER_ACCOUNT_PROFILES_CANCELLED, 0, 0, "save cancelled before replace");
    return READER_ACCOUNT_PROFILES_CANCELLED;
  }
  if (rename(temporary, path) != 0) {
    code = errno;
    unlink(temporary);
    free(temporary);
    ap_error_set(error, READER_ACCOUNT_PROFILES_IO, code, 0,
                 "cannot atomically replace the store document");
    return READER_ACCOUNT_PROFILES_IO;
  }
  free(temporary);
  {
    char directory[READER_ACCOUNT_PROFILES_MAX_PATH_BYTES + 1u];
    const char *slash = strrchr(path, '/');
    size_t used = slash ? (slash == path ? 1u : (size_t)(slash - path)) : 1u;
    int directory_descriptor;
    if (used >= sizeof(directory)) used = sizeof(directory) - 1u;
    if (slash) {
      memcpy(directory, path, used);
    } else {
      directory[0] = '.';
    }
    directory[used] = '\0';
    directory_descriptor = open(directory, O_RDONLY
#if defined(O_DIRECTORY)
                                | O_DIRECTORY
#endif
#if defined(O_CLOEXEC)
                                | O_CLOEXEC
#endif
    );
    if (directory_descriptor >= 0) {
      (void)fsync(directory_descriptor);
      (void)close(directory_descriptor);
    }
  }
#if defined(READER_ACCOUNT_PROFILES_TEST_HOOKS)
  ap_test_pause("EXR_ACCOUNT_PROFILES_TEST_PAUSE_AFTER_RENAME");
#endif
  return READER_ACCOUNT_PROFILES_OK;
}

static reader_account_profiles_status ap_posix_lock(const char *store_dir, uint32_t timeout_ms,
                                                    const reader_account_profiles_control *control,
                                                    ap_lock *lock,
                                                    reader_account_profiles_error *error) {
  size_t length = strlen(store_dir);
  char *path = (char *)malloc(length + 8u);
  struct timespec start;
  int descriptor;
  if (!path) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_IO, ENOMEM, 0, "out of memory");
    return READER_ACCOUNT_PROFILES_IO;
  }
  (void)snprintf(path, length + 8u, "%s/.lock", store_dir);
  descriptor = open(path, O_RDWR | O_CREAT
#if defined(O_CLOEXEC)
                    | O_CLOEXEC
#endif
                    , 0600);
  free(path);
  if (descriptor < 0) {
    int code = errno;
    ap_error_set(error, READER_ACCOUNT_PROFILES_IO, code, 0, "cannot open the writer lock");
    return READER_ACCOUNT_PROFILES_IO;
  }
  (void)clock_gettime(CLOCK_MONOTONIC, &start);
  for (;;) {
    if (flock(descriptor, LOCK_EX | LOCK_NB) == 0) {
      lock->descriptor = descriptor;
      lock->held = 1;
#if defined(READER_ACCOUNT_PROFILES_TEST_HOOKS)
      ap_test_pause("EXR_ACCOUNT_PROFILES_TEST_PAUSE_AFTER_LOCK");
#endif
      return READER_ACCOUNT_PROFILES_OK;
    }
    if (errno != EWOULDBLOCK && errno != EINTR) {
      int code = errno;
      close(descriptor);
      ap_error_set(error, READER_ACCOUNT_PROFILES_IO, code, 0, "cannot take the writer lock");
      return READER_ACCOUNT_PROFILES_IO;
    }
    if (ap_cancel_requested(control)) {
      close(descriptor);
      ap_error_set(error, READER_ACCOUNT_PROFILES_CANCELLED, 0, 0,
                   "cancelled while waiting for the lock");
      return READER_ACCOUNT_PROFILES_CANCELLED;
    }
    {
      struct timespec now;
      uint64_t elapsed;
      (void)clock_gettime(CLOCK_MONOTONIC, &now);
      elapsed = (uint64_t)(now.tv_sec - start.tv_sec) * 1000u;
      elapsed += (uint64_t)((now.tv_nsec - start.tv_nsec) / 1000000L);
      if (elapsed >= (uint64_t)timeout_ms) {
        close(descriptor);
        ap_error_set(error, READER_ACCOUNT_PROFILES_LOCKED, 0, 0,
                     "writer lock busy for %u ms", (unsigned)timeout_ms);
        return READER_ACCOUNT_PROFILES_LOCKED;
      }
    }
    ap_sleep_ms(10u);
  }
}

static void ap_posix_unlock(ap_lock *lock) {
  if (lock->held && lock->descriptor >= 0) {
    (void)flock(lock->descriptor, LOCK_UN);
    (void)close(lock->descriptor);
  }
  lock->descriptor = -1;
  lock->held = 0;
}

static reader_account_profiles_status ap_posix_ensure(const char *path,
                                                      reader_account_profiles_error *error) {
  ap_entry_kind kind;
  reader_account_profiles_status status;
  if (mkdir(path, 0700) == 0) return READER_ACCOUNT_PROFILES_OK;
  if (errno != EEXIST) {
    int code = errno;
    ap_error_set(error, READER_ACCOUNT_PROFILES_IO, code, 0, "cannot create profile directory");
    return READER_ACCOUNT_PROFILES_IO;
  }
  status = ap_inspect_entry(path, &kind, NULL, NULL, error);
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  if (kind != AP_ENTRY_DIRECTORY) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_UNSAFE_PATH, 0, 0,
                 "profile directory path is not a real directory");
    return READER_ACCOUNT_PROFILES_UNSAFE_PATH;
  }
  return READER_ACCOUNT_PROFILES_OK;
}

static reader_account_profiles_status ap_posix_inspect(const char *path, ap_entry_kind *kind,
                                                       uint64_t *size, uint32_t *link_count,
                                                       reader_account_profiles_error *error) {
  struct stat info;
  if (lstat(path, &info) != 0) {
    int code = errno;
    if (code == ENOENT) {
      *kind = AP_ENTRY_MISSING;
      if (size) *size = 0;
      if (link_count) *link_count = 0;
      return READER_ACCOUNT_PROFILES_OK;
    }
    ap_error_set(error, READER_ACCOUNT_PROFILES_IO, code, 0, "cannot inspect store entry");
    return READER_ACCOUNT_PROFILES_IO;
  }
  if (S_ISLNK(info.st_mode)) *kind = AP_ENTRY_LINK;
  else if (S_ISDIR(info.st_mode)) *kind = AP_ENTRY_DIRECTORY;
  else if (S_ISREG(info.st_mode)) *kind = AP_ENTRY_FILE;
  else *kind = AP_ENTRY_OTHER;
  if (size) *size = (uint64_t)info.st_size;
  if (link_count) *link_count = (uint32_t)info.st_nlink;
  return READER_ACCOUNT_PROFILES_OK;
}

#endif

reader_account_profiles_status ap_read_file(const char *path, size_t max_bytes,
                                            unsigned char **data, size_t *size, int *present,
                                            const reader_account_profiles_control *control,
                                            reader_account_profiles_error *error) {
  *data = NULL;
  *size = 0;
  *present = 0;
#if defined(_WIN32)
  return ap_win_read(path, max_bytes, data, size, present, control, error);
#else
  return ap_posix_read(path, max_bytes, data, size, present, control, error);
#endif
}

reader_account_profiles_status ap_write_file_atomic(const char *directory, const char *path,
                                                    const void *data, size_t size,
                                                    const reader_account_profiles_control *control,
                                                    reader_account_profiles_error *error) {
  (void)directory;
#if defined(_WIN32)
  return ap_win_write(path, data, size, control, error);
#else
  return ap_posix_write(path, data, size, control, error);
#endif
}

reader_account_profiles_status ap_lock_acquire(const char *store_dir, uint32_t timeout_ms,
                                               const reader_account_profiles_control *control,
                                               ap_lock *lock,
                                               reader_account_profiles_error *error) {
  lock->held = 0;
#if defined(_WIN32)
  lock->handle = NULL;
  return ap_win_lock(store_dir, timeout_ms, control, lock, error);
#else
  lock->descriptor = -1;
  return ap_posix_lock(store_dir, timeout_ms, control, lock, error);
#endif
}

void ap_lock_release(ap_lock *lock) {
#if defined(_WIN32)
  ap_win_unlock(lock);
#else
  ap_posix_unlock(lock);
#endif
}

reader_account_profiles_status ap_inspect_entry(const char *path, ap_entry_kind *kind,
                                                uint64_t *size, uint32_t *link_count,
                                                reader_account_profiles_error *error) {
#if defined(_WIN32)
  return ap_win_inspect(path, kind, size, link_count, error);
#else
  return ap_posix_inspect(path, kind, size, link_count, error);
#endif
}

reader_account_profiles_status ap_ensure_directory(const char *path,
                                                   reader_account_profiles_error *error) {
#if defined(_WIN32)
  return ap_win_ensure(path, error);
#else
  return ap_posix_ensure(path, error);
#endif
}

reader_account_profiles_status ap_verify_directory_chain(const char *path,
                                                         reader_account_profiles_error *error) {
  char buffer[READER_ACCOUNT_PROFILES_MAX_PATH_BYTES + 1u];
  size_t length = strlen(path);
  size_t root;
  size_t index;
  if (length == 0 || length >= sizeof(buffer)) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_ARGUMENT, 0, 0, "store path length is unsupported");
    return READER_ACCOUNT_PROFILES_ARGUMENT;
  }
  memcpy(buffer, path, length + 1u);
#if defined(_WIN32)
  if (length >= 3u && buffer[1] == ':' &&
      (buffer[2] == '\\' || buffer[2] == '/') &&
      ((buffer[0] >= 'A' && buffer[0] <= 'Z') || (buffer[0] >= 'a' && buffer[0] <= 'z'))) {
    root = 3u;
  } else if (length >= 2u && buffer[0] == '\\' && buffer[1] == '\\') {
    size_t seen = 0;
    root = 2u;
    while (root < length) {
      if (buffer[root] == '\\' || buffer[root] == '/') {
        seen += 1u;
        if (seen == 2u) { root += 1u; break; }
      }
      root += 1u;
    }
  } else {
    ap_error_set(error, READER_ACCOUNT_PROFILES_ARGUMENT, 0, 0, "store path is not absolute");
    return READER_ACCOUNT_PROFILES_ARGUMENT;
  }
#else
  if (buffer[0] != '/') {
    ap_error_set(error, READER_ACCOUNT_PROFILES_ARGUMENT, 0, 0, "store path is not absolute");
    return READER_ACCOUNT_PROFILES_ARGUMENT;
  }
  root = 1u;
#endif
  for (index = root; index <= length; ++index) {
    if (index == length || buffer[index] == '/' || buffer[index] == '\\') {
      char saved = buffer[index];
      buffer[index] = '\0';
      if (index > root) {
        ap_entry_kind kind;
        reader_account_profiles_status status =
            ap_inspect_entry(buffer, &kind, NULL, NULL, error);
        if (status != READER_ACCOUNT_PROFILES_OK) {
          buffer[index] = saved;
          return status;
        }
        if (kind == AP_ENTRY_MISSING) {
          buffer[index] = saved;
          ap_error_set(error, READER_ACCOUNT_PROFILES_IO, ENOENT, 0,
                       "a store directory component does not exist");
          return READER_ACCOUNT_PROFILES_IO;
        }
        if (kind == AP_ENTRY_LINK) {
          buffer[index] = saved;
          ap_error_set(error, READER_ACCOUNT_PROFILES_UNSAFE_PATH, 0, 0,
                       "a store directory component is a link or junction");
          return READER_ACCOUNT_PROFILES_UNSAFE_PATH;
        }
        if (kind != AP_ENTRY_DIRECTORY) {
          buffer[index] = saved;
          ap_error_set(error, READER_ACCOUNT_PROFILES_UNSAFE_PATH, 0, 0,
                       "a store directory component is not a directory");
          return READER_ACCOUNT_PROFILES_UNSAFE_PATH;
        }
      }
      buffer[index] = saved;
    }
  }
  return READER_ACCOUNT_PROFILES_OK;
}
