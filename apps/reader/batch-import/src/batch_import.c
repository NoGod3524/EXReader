/* SPDX-License-Identifier: MIT */
#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#define _FILE_OFFSET_BITS 64
#endif
#include "reader_batch_import.h"
#include <ctype.h>
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifdef _WIN32
#include <windows.h>
#include <wchar.h>
#include <io.h>
#else
#include <dirent.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#endif

#define RB_COPY_CHUNK (64u * 1024u)
#define RB_TEMP_ATTEMPTS 128u

#ifndef O_CLOEXEC
#define O_CLOEXEC 0
#endif
#ifndef O_DIRECTORY
#define O_DIRECTORY 0
#endif
#ifndef O_NOFOLLOW
#define O_NOFOLLOW 0
#endif

#ifdef _WIN32
typedef HANDLE rb_file;
#define RB_BAD_FILE INVALID_HANDLE_VALUE
#else
typedef int rb_file;
#define RB_BAD_FILE (-1)
#endif

static reader_batch_status rb_fail(reader_batch_error *error,
    reader_batch_status code, exr_status status_code, const char *format, ...) {
  va_list args;
  if (error) {
    error->code = code;
    error->status_code = status_code;
    error->message[0] = 0;
    va_start(args, format);
    vsnprintf(error->message, sizeof(error->message), format, args);
    va_end(args);
  }
  return code;
}

static char *rb_strdup_n(const char *text, size_t bytes) {
  char *copy = malloc(bytes + 1);
  if (!copy) return NULL;
  if (bytes) memcpy(copy, text, bytes);
  copy[bytes] = 0;
  return copy;
}

static char *rb_strdup(const char *text) {
  return text ? rb_strdup_n(text, strlen(text)) : NULL;
}

static size_t rb_bounded_len(const char *text, size_t limit) {
  size_t i = 0;
  if (!text) return 0;
  while (i < limit && text[i]) i++;
  return i;
}

static int rb_utf8_valid(const char *text) {
  const unsigned char *s = (const unsigned char *)text;
  while (*s) {
    unsigned char c = *s++;
    if (c < 0x80) continue;
    if (c < 0xC2) return 0;
    if (c < 0xE0) {
      if ((*s & 0xC0) != 0x80) return 0;
      s++;
    } else if (c < 0xF0) {
      if ((s[0] & 0xC0) != 0x80 || (s[1] & 0xC0) != 0x80) return 0;
      if (c == 0xE0 && s[0] < 0xA0) return 0;
      if (c == 0xED && s[0] >= 0xA0) return 0;
      s += 2;
    } else if (c < 0xF5) {
      if ((s[0] & 0xC0) != 0x80 || (s[1] & 0xC0) != 0x80 || (s[2] & 0xC0) != 0x80)
        return 0;
      if (c == 0xF0 && s[0] < 0x90) return 0;
      if (c == 0xF4 && s[0] >= 0x90) return 0;
      s += 3;
    } else {
      return 0;
    }
  }
  return 1;
}

static int rb_is_sep(char c) {
#ifdef _WIN32
  return c == '/' || c == '\\';
#else
  return c == '/';
#endif
}

static char rb_sep(void) {
#ifdef _WIN32
  return '\\';
#else
  return '/';
#endif
}

static int rb_join(char *out, size_t capacity, const char *directory,
    const char *name) {
  size_t a = strlen(directory), b = strlen(name);
  int needs = !(a && rb_is_sep(directory[a - 1]));
  if (a + (size_t)needs + b + 1 > capacity) return 1;
  memcpy(out, directory, a);
  if (needs) out[a++] = rb_sep();
  memcpy(out + a, name, b + 1);
  return 0;
}

static int rb_cancelled(const exr_control *control) {
  return control && control->cancelled && control->cancelled(control->context);
}

static const char *rb_extension(const char *name) {
  const char *dot = NULL, *p = name;
  while (*p) {
    if (rb_is_sep(*p)) dot = NULL;
    else if (*p == '.') dot = p;
    p++;
  }
  return dot ? dot + 1 : NULL;
}

static int rb_extension_is(const char *extension, const char *wanted) {
  while (*extension && *wanted) {
    if (tolower((unsigned char)*extension) != tolower((unsigned char)*wanted))
      return 0;
    extension++;
    wanted++;
  }
  return *extension == 0 && *wanted == 0;
}

static exr_format rb_format_for_name(const char *name) {
  const char *ext = rb_extension(name);
  if (!ext) return EXR_CUSTOM;
  if (rb_extension_is(ext, "txt")) return EXR_TXT;
  if (rb_extension_is(ext, "html") || rb_extension_is(ext, "htm") ||
      rb_extension_is(ext, "xhtml")) return EXR_HTML;
  if (rb_extension_is(ext, "fb2")) return EXR_FB2;
  if (rb_extension_is(ext, "epub")) return EXR_EPUB;
  if (rb_extension_is(ext, "docx")) return EXR_DOCX;
  if (rb_extension_is(ext, "rtf")) return EXR_RTF;
  if (rb_extension_is(ext, "mobi") || rb_extension_is(ext, "prc") ||
      rb_extension_is(ext, "azw") || rb_extension_is(ext, "azw3") ||
      rb_extension_is(ext, "kf8")) return EXR_MOBI;
  if (rb_extension_is(ext, "pdf")) return EXR_PDF;
  if (rb_extension_is(ext, "cbz")) return EXR_CBZ;
  return EXR_CUSTOM;
}

static uint64_t rb_effective_limit(exr_format format, uint64_t requested) {
  uint64_t hard = (format == EXR_EPUB || format == EXR_CBZ || format == EXR_PDF)
      ? EXR_SIDELOAD_STREAM_LIMIT : EXR_SIDELOAD_MEMORY_LIMIT;
  if (requested && requested < hard) return requested;
  return hard;
}

#ifdef _WIN32
static wchar_t *rb_widen(const char *text, int *encoding) {
  int count;
  wchar_t *wide;
  if (encoding) *encoding = 0;
  count = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, text, -1, NULL, 0);
  if (count <= 0) {
    if (encoding) *encoding = 1;
    return NULL;
  }
  wide = malloc((size_t)count * sizeof(*wide));
  if (!wide) return NULL;
  if (!MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, text, -1, wide, count)) {
    free(wide);
    if (encoding) *encoding = 1;
    return NULL;
  }
  return wide;
}

static char *rb_narrow(const wchar_t *wide, int *encoding) {
  int count;
  char *text;
  if (encoding) *encoding = 0;
  count = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, wide, -1, NULL, 0,
      NULL, NULL);
  if (count <= 0) {
    if (encoding) *encoding = 1;
    return NULL;
  }
  text = malloc((size_t)count);
  if (!text) return NULL;
  if (!WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, wide, -1, text, count,
      NULL, NULL)) {
    free(text);
    if (encoding) *encoding = 1;
    return NULL;
  }
  return text;
}
#endif

static char *rb_canonical_root(const char *root, reader_batch_error *error) {
  char *result = NULL;
#ifdef _WIN32
  wchar_t *wide;
  DWORD attributes, length;
  wchar_t *full;
  wide = rb_widen(root, NULL);
  if (!wide) {
    rb_fail(error, READER_BATCH_ENCODING, EXR_ENCODING,
        "Root path is not valid UTF-8");
    return NULL;
  }
  attributes = GetFileAttributesW(wide);
  if (attributes == INVALID_FILE_ATTRIBUTES) {
    DWORD code = GetLastError();
    free(wide);
    rb_fail(error, READER_BATCH_IO, EXR_IO,
        "Cannot access root directory (Windows error %lu)", (unsigned long)code);
    return NULL;
  }
  if (attributes & FILE_ATTRIBUTE_REPARSE_POINT) {
    free(wide);
    rb_fail(error, READER_BATCH_ARGUMENT, EXR_ARGUMENT,
        "Root must not be a symbolic link or directory junction");
    return NULL;
  }
  if (!(attributes & FILE_ATTRIBUTE_DIRECTORY)) {
    free(wide);
    rb_fail(error, READER_BATCH_ARGUMENT, EXR_ARGUMENT,
        "Root is not a directory");
    return NULL;
  }
  length = GetFullPathNameW(wide, 0, NULL, NULL);
  if (!length) {
    free(wide);
    rb_fail(error, READER_BATCH_IO, EXR_IO,
        "Cannot canonicalize root directory");
    return NULL;
  }
  full = malloc(((size_t)length + 1) * sizeof(*full));
  if (!full) {
    free(wide);
    rb_fail(error, READER_BATCH_MEMORY, EXR_MEMORY,
        "Cannot allocate canonical root path");
    return NULL;
  }
  if (!GetFullPathNameW(wide, length, full, NULL)) {
    free(full);
    free(wide);
    rb_fail(error, READER_BATCH_IO, EXR_IO,
        "Cannot canonicalize root directory");
    return NULL;
  }
  free(wide);
  result = rb_narrow(full, NULL);
  free(full);
  if (!result) {
    rb_fail(error, READER_BATCH_ENCODING, EXR_ENCODING,
        "Canonical root path is not valid UTF-8");
    return NULL;
  }
#else
  struct stat status;
  if (lstat(root, &status) != 0) {
    rb_fail(error, READER_BATCH_IO, EXR_IO,
        "Cannot access root directory: %s", strerror(errno));
    return NULL;
  }
  if (S_ISLNK(status.st_mode)) {
    rb_fail(error, READER_BATCH_ARGUMENT, EXR_ARGUMENT,
        "Root must not be a symbolic link");
    return NULL;
  }
  if (!S_ISDIR(status.st_mode)) {
    rb_fail(error, READER_BATCH_ARGUMENT, EXR_ARGUMENT,
        "Root is not a directory");
    return NULL;
  }
  result = realpath(root, NULL);
  if (!result) {
    rb_fail(error, READER_BATCH_IO, EXR_IO,
        "Cannot canonicalize root directory: %s", strerror(errno));
    return NULL;
  }
#endif
  {
    size_t len = strlen(result);
    while (len > 1 && rb_is_sep(result[len - 1])) {
#ifdef _WIN32
      if (len == 3 && result[1] == ':') break;
#endif
      result[--len] = 0;
    }
  }
  return result;
}

typedef struct {
  char *path;
  size_t depth;
} rb_dir;

struct reader_batch_enumerator {
  reader_batch_scan_options options;
  char *root;
  size_t root_length;
  size_t batch_size;
  rb_dir *stack;
  size_t stack_count, stack_capacity;
  char *current;
  size_t current_depth;
  size_t retained_bytes;
  int current_open;
  int done;
  int truncated;
  size_t directories_seen;
  size_t candidates_seen;
#ifdef _WIN32
  HANDLE find;
  WIN32_FIND_DATAW find_data;
  int find_has;
#else
  DIR *dir;
#endif
};

static void rb_close_current(reader_batch_enumerator *enumerator) {
  if (!enumerator->current_open) return;
#ifdef _WIN32
  if (enumerator->find != INVALID_HANDLE_VALUE) FindClose(enumerator->find);
  enumerator->find = INVALID_HANDLE_VALUE;
  enumerator->find_has = 0;
#else
  if (enumerator->dir) closedir(enumerator->dir);
  enumerator->dir = NULL;
#endif
  if (enumerator->current) {
    enumerator->retained_bytes -= strlen(enumerator->current) + 1;
    free(enumerator->current);
    enumerator->current = NULL;
  }
  enumerator->current_open = 0;
  enumerator->current_depth = 0;
}

static reader_batch_status rb_open_current(reader_batch_enumerator *enumerator,
    char *path, size_t depth, reader_batch_error *error) {
  rb_close_current(enumerator);
#ifdef _WIN32
  {
    wchar_t *wide = rb_widen(path, NULL);
    DWORD attributes;
    wchar_t *pattern;
    size_t length, extra;
    HANDLE handle;
    if (!wide) {
      free(path);
      return rb_fail(error, READER_BATCH_ENCODING, EXR_ENCODING,
          "Directory path is not valid UTF-8");
    }
    attributes = GetFileAttributesW(wide);
    if (attributes == INVALID_FILE_ATTRIBUTES ||
        (attributes & FILE_ATTRIBUTE_REPARSE_POINT) ||
        !(attributes & FILE_ATTRIBUTE_DIRECTORY)) {
      free(wide);
      free(path);
      return rb_fail(error, READER_BATCH_IO, EXR_IO,
          "Directory disappeared or is no longer a real directory");
    }
    length = wcslen(wide);
    extra = (length && (wide[length - 1] == L'\\' || wide[length - 1] == L'/'))
        ? 2 : 3;
    pattern = malloc((length + extra) * sizeof(*pattern));
    if (!pattern) {
      free(wide);
      free(path);
      return rb_fail(error, READER_BATCH_MEMORY, EXR_MEMORY,
          "Cannot allocate directory search pattern");
    }
    memcpy(pattern, wide, (length + 1) * sizeof(*pattern));
    if (extra == 3) wcscat(pattern, L"\\");
    wcscat(pattern, L"*");
    handle = FindFirstFileW(pattern, &enumerator->find_data);
    free(pattern);
    free(wide);
    if (handle == INVALID_HANDLE_VALUE) {
      DWORD code = GetLastError();
      if (code == ERROR_FILE_NOT_FOUND) {
        enumerator->find = INVALID_HANDLE_VALUE;
        enumerator->find_has = 0;
      } else {
        free(path);
        return rb_fail(error, READER_BATCH_IO, EXR_IO,
            "Cannot enumerate directory (Windows error %lu)", (unsigned long)code);
      }
    } else {
      enumerator->find = handle;
      enumerator->find_has = 1;
    }
  }
#else
  {
    int fd;
    struct stat status;
    DIR *directory;
    fd = open(path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0) {
      free(path);
      return rb_fail(error, READER_BATCH_IO, EXR_IO,
          "Cannot open directory: %s", strerror(errno));
    }
    if (fstat(fd, &status) != 0 || !S_ISDIR(status.st_mode)) {
      close(fd);
      free(path);
      return rb_fail(error, READER_BATCH_IO, EXR_IO,
          "Directory disappeared or is not a real directory");
    }
    directory = fdopendir(fd);
    if (!directory) {
      close(fd);
      free(path);
      return rb_fail(error, READER_BATCH_IO, EXR_IO,
          "Cannot enumerate directory: %s", strerror(errno));
    }
    enumerator->dir = directory;
  }
#endif
  enumerator->current = path;
  enumerator->current_depth = depth;
  enumerator->current_open = 1;
  enumerator->retained_bytes += strlen(path) + 1;
  enumerator->directories_seen++;
  return READER_BATCH_OK;
}

static reader_batch_status rb_push_directory(reader_batch_enumerator *enumerator,
    char *path, size_t depth, reader_batch_error *error) {
  size_t length = strlen(path);
  if (enumerator->retained_bytes + length + 1 > enumerator->options.max_pending_bytes) {
    free(path);
    enumerator->truncated = 1;
    enumerator->done = 1;
    return READER_BATCH_OK;
  }
  if (enumerator->stack_count == enumerator->stack_capacity) {
    size_t capacity = enumerator->stack_capacity ? enumerator->stack_capacity * 2 : 8;
    rb_dir *stack = realloc(enumerator->stack, capacity * sizeof(*stack));
    if (!stack) {
      free(path);
      return rb_fail(error, READER_BATCH_MEMORY, EXR_MEMORY,
          "Cannot grow enumeration directory stack");
    }
    enumerator->stack = stack;
    enumerator->stack_capacity = capacity;
  }
  enumerator->stack[enumerator->stack_count].path = path;
  enumerator->stack[enumerator->stack_count].depth = depth;
  enumerator->stack_count++;
  enumerator->retained_bytes += length + 1;
  return READER_BATCH_OK;
}

static reader_batch_status rb_advance_directory(reader_batch_enumerator *enumerator,
    reader_batch_error *error, int *opened) {
  *opened = 0;
  rb_close_current(enumerator);
  while (enumerator->stack_count) {
    rb_dir item = enumerator->stack[--enumerator->stack_count];
    reader_batch_error local;
    reader_batch_status status;
    enumerator->retained_bytes -= strlen(item.path) + 1;
    memset(&local, 0, sizeof(local));
    status = rb_open_current(enumerator, item.path, item.depth, &local);
    if (status == READER_BATCH_OK) {
      *opened = 1;
      return READER_BATCH_OK;
    }
    if (status == READER_BATCH_MEMORY || status == READER_BATCH_ENCODING) {
      if (error) *error = local;
      return status;
    }
    enumerator->truncated = 1;
  }
  enumerator->done = 1;
  return READER_BATCH_OK;
}

typedef struct {
  char *name;
  char *full;
  int is_dir;
  int is_file;
  uint64_t size;
} rb_entry;

#ifdef _WIN32
static int rb_next_entry(reader_batch_enumerator *enumerator, rb_entry *entry,
    reader_batch_error *error) {
  for (;;) {
    DWORD attributes;
    const wchar_t *name;
    int encoding = 0;
    char *utf8;
    char *full;
    size_t capacity = enumerator->options.max_path_bytes + 1;
    if (!enumerator->current_open) return 0;
    if (enumerator->find == INVALID_HANDLE_VALUE) return 0;
    if (!enumerator->find_has) {
      if (!FindNextFileW(enumerator->find, &enumerator->find_data)) {
        DWORD code = GetLastError();
        if (code == ERROR_NO_MORE_FILES) return 0;
        rb_fail(error, READER_BATCH_IO, EXR_IO,
            "Cannot read directory (Windows error %lu)", (unsigned long)code);
        return -1;
      }
    } else {
      enumerator->find_has = 0;
    }
    attributes = enumerator->find_data.dwFileAttributes;
    name = enumerator->find_data.cFileName;
    if (name[0] == L'.' && (name[1] == 0 || (name[1] == L'.' && name[2] == 0)))
      continue;
    if (attributes & FILE_ATTRIBUTE_REPARSE_POINT) continue;
    if (attributes & FILE_ATTRIBUTE_DEVICE) continue;
    utf8 = rb_narrow(name, &encoding);
    if (!utf8) {
      if (encoding) enumerator->truncated = 1;
      continue;
    }
    full = malloc(capacity);
    if (!full) {
      free(utf8);
      rb_fail(error, READER_BATCH_MEMORY, EXR_MEMORY,
          "Cannot allocate candidate path");
      return -1;
    }
    if (rb_join(full, capacity, enumerator->current, utf8)) {
      free(full);
      free(utf8);
      enumerator->truncated = 1;
      enumerator->done = 1;
      return 0;
    }
    entry->name = utf8;
    entry->full = full;
    entry->is_dir = (attributes & FILE_ATTRIBUTE_DIRECTORY) != 0;
    entry->is_file = !entry->is_dir;
    entry->size = ((uint64_t)enumerator->find_data.nFileSizeHigh << 32) |
        (uint64_t)enumerator->find_data.nFileSizeLow;
    return 1;
  }
}
#else
static int rb_next_entry(reader_batch_enumerator *enumerator, rb_entry *entry,
    reader_batch_error *error) {
  for (;;) {
    struct dirent *item;
    struct stat status;
    char *full;
    size_t capacity = enumerator->options.max_path_bytes + 1;
    if (!enumerator->current_open || !enumerator->dir) return 0;
    errno = 0;
    item = readdir(enumerator->dir);
    if (!item) {
      if (errno) {
        rb_fail(error, READER_BATCH_IO, EXR_IO,
            "Cannot read directory: %s", strerror(errno));
        return -1;
      }
      return 0;
    }
    if (!strcmp(item->d_name, ".") || !strcmp(item->d_name, "..")) continue;
    if (!rb_utf8_valid(item->d_name)) {
      enumerator->truncated = 1;
      continue;
    }
    full = malloc(capacity);
    if (!full) {
      rb_fail(error, READER_BATCH_MEMORY, EXR_MEMORY,
          "Cannot allocate candidate path");
      return -1;
    }
    if (rb_join(full, capacity, enumerator->current, item->d_name)) {
      free(full);
      enumerator->truncated = 1;
      enumerator->done = 1;
      return 0;
    }
    if (lstat(full, &status) != 0) {
      free(full);
      if (errno != ENOENT && errno != ENOTDIR) enumerator->truncated = 1;
      continue;
    }
    if (S_ISLNK(status.st_mode)) {
      free(full);
      continue;
    }
    if (!S_ISDIR(status.st_mode) && !S_ISREG(status.st_mode)) {
      free(full);
      continue;
    }
    entry->name = rb_strdup(item->d_name);
    if (!entry->name) {
      free(full);
      rb_fail(error, READER_BATCH_MEMORY, EXR_MEMORY,
          "Cannot allocate candidate name");
      return -1;
    }
    entry->full = full;
    entry->is_dir = S_ISDIR(status.st_mode);
    entry->is_file = S_ISREG(status.st_mode);
    entry->size = (uint64_t)status.st_size;
    return 1;
  }
}
#endif

static int rb_relative_path(const reader_batch_enumerator *enumerator,
    const char *full, char **out, reader_batch_error *error) {
  const char *start;
  char *relative;
  size_t i, length;
  if (strncmp(full, enumerator->root, enumerator->root_length) != 0) {
    rb_fail(error, READER_BATCH_INTERNAL, EXR_IO,
        "Candidate escaped the selected root");
    return -1;
  }
  start = full + enumerator->root_length;
  while (*start && rb_is_sep(*start)) start++;
  length = strlen(start);
  relative = malloc(length + 1);
  if (!relative) {
    rb_fail(error, READER_BATCH_MEMORY, EXR_MEMORY,
        "Cannot allocate relative candidate path");
    return -1;
  }
  for (i = 0; i < length; i++)
    relative[i] = rb_is_sep(start[i]) ? '/' : start[i];
  relative[length] = 0;
  *out = relative;
  return 0;
}

void reader_batch_scan_options_init(reader_batch_scan_options *options) {
  if (!options) return;
  memset(options, 0, sizeof(*options));
  options->struct_size = sizeof(*options);
  options->recursive = 0;
  options->max_depth = 0;
  options->max_directories = READER_BATCH_DEFAULT_DIRECTORIES;
  options->max_candidates = READER_BATCH_DEFAULT_CANDIDATES;
  options->max_path_bytes = READER_BATCH_DEFAULT_PATH_BYTES;
  options->max_pending_bytes = READER_BATCH_DEFAULT_PENDING_BYTES;
  options->batch_size = READER_BATCH_DEFAULT_BATCH;
}

reader_batch_status reader_batch_enumerate_open(
    const reader_batch_scan_options *options, reader_batch_enumerator **out,
    reader_batch_error *error) {
  reader_batch_enumerator *enumerator;
  reader_batch_scan_options effective;
  char *root;
  size_t root_length;
  if (!out) return rb_fail(error, READER_BATCH_ARGUMENT, EXR_ARGUMENT,
      "Enumerator output is required");
  *out = NULL;
  if (!options || options->struct_size < sizeof(*options))
    return rb_fail(error, READER_BATCH_ARGUMENT, EXR_ARGUMENT,
        "Set a complete scan options struct_size");
  if (!options->root || !options->root[0])
    return rb_fail(error, READER_BATCH_ARGUMENT, EXR_ARGUMENT,
        "A UTF-8 root directory is required");
  if (options->batch_size > READER_BATCH_MAX_BATCH ||
      options->max_depth > READER_BATCH_MAX_DEPTH ||
      options->max_directories > READER_BATCH_MAX_DIRECTORIES ||
      options->max_candidates > READER_BATCH_MAX_CANDIDATES ||
      options->max_path_bytes > READER_BATCH_MAX_PATH_BYTES ||
      options->max_pending_bytes > READER_BATCH_MAX_PENDING_BYTES)
    return rb_fail(error, READER_BATCH_ARGUMENT, EXR_ARGUMENT,
        "Scan limits exceed the published hard maximum");
  effective = *options;
  if (!effective.recursive) effective.max_depth = 0;
  else if (!effective.max_depth) effective.max_depth = READER_BATCH_DEFAULT_DEPTH;
  if (!effective.max_directories) effective.max_directories = READER_BATCH_DEFAULT_DIRECTORIES;
  if (!effective.max_candidates) effective.max_candidates = READER_BATCH_DEFAULT_CANDIDATES;
  if (!effective.max_path_bytes) effective.max_path_bytes = READER_BATCH_DEFAULT_PATH_BYTES;
  if (!effective.max_pending_bytes) effective.max_pending_bytes = READER_BATCH_DEFAULT_PENDING_BYTES;
  if (!effective.batch_size) effective.batch_size = READER_BATCH_DEFAULT_BATCH;
  if (effective.max_path_bytes < 64)
    return rb_fail(error, READER_BATCH_ARGUMENT, EXR_ARGUMENT,
        "max_path_bytes is too small");
  root = rb_canonical_root(options->root, error);
  if (!root) return error ? error->code : READER_BATCH_IO;
  root_length = strlen(root);
  if (root_length > effective.max_path_bytes) {
    free(root);
    return rb_fail(error, READER_BATCH_ARGUMENT, EXR_ARGUMENT,
        "Root path exceeds max_path_bytes");
  }
  if (effective.max_pending_bytes < root_length + 1) {
    free(root);
    return rb_fail(error, READER_BATCH_ARGUMENT, EXR_ARGUMENT,
        "max_pending_bytes cannot hold the root path");
  }
  enumerator = calloc(1, sizeof(*enumerator));
  if (!enumerator) {
    free(root);
    return rb_fail(error, READER_BATCH_MEMORY, EXR_MEMORY,
        "Cannot allocate batch enumerator");
  }
  enumerator->options = effective;
  enumerator->root = root;
  enumerator->root_length = root_length;
  enumerator->batch_size = effective.batch_size;
#ifdef _WIN32
  enumerator->find = INVALID_HANDLE_VALUE;
#endif
  {
    char *root_copy = rb_strdup(root);
    reader_batch_status status;
    if (!root_copy) {
      reader_batch_enumerate_close(enumerator);
      return rb_fail(error, READER_BATCH_MEMORY, EXR_MEMORY,
          "Cannot allocate root directory path");
    }
    status = rb_open_current(enumerator, root_copy, 0, error);
    if (status != READER_BATCH_OK) {
      /* rb_open_current already freed its path. */
      reader_batch_enumerate_close(enumerator);
      return status;
    }
  }
  *out = enumerator;
  return READER_BATCH_OK;
}

reader_batch_status reader_batch_enumerate_next(
    reader_batch_enumerator *enumerator, reader_batch_candidate **items,
    size_t *count, int *complete, int *truncated, reader_batch_error *error) {
  reader_batch_candidate *batch;
  size_t produced = 0;
  reader_batch_status status = READER_BATCH_OK;
  if (!enumerator || !items || !count || !complete || !truncated)
    return rb_fail(error, READER_BATCH_ARGUMENT, EXR_ARGUMENT,
        "Enumerator, items, count, complete and truncated are required");
  *items = NULL;
  *count = 0;
  *complete = 0;
  *truncated = 0;
  if (enumerator->done) {
    *truncated = enumerator->truncated;
    *complete = !enumerator->truncated;
    return READER_BATCH_OK;
  }
  batch = calloc(enumerator->batch_size, sizeof(*batch));
  if (!batch)
    return rb_fail(error, READER_BATCH_MEMORY, EXR_MEMORY,
        "Cannot allocate candidate batch");
  while (produced < enumerator->batch_size) {
    rb_entry entry;
    exr_format format;
    char *relative = NULL;
    if (rb_cancelled(&enumerator->options.control)) {
      status = rb_fail(error, READER_BATCH_CANCELLED, EXR_CANCELLED,
          "Enumeration cancelled");
      break;
    }
    if (!enumerator->current_open) {
      int opened = 0;
      status = rb_advance_directory(enumerator, error, &opened);
      if (status != READER_BATCH_OK) break;
      if (!opened) break;
    }
    memset(&entry, 0, sizeof(entry));
    {
      int got = rb_next_entry(enumerator, &entry, error);
      if (got < 0) {
        status = error ? error->code : READER_BATCH_IO;
        break;
      }
      if (got == 0) {
        rb_close_current(enumerator);
        if (enumerator->done) break;
        continue;
      }
    }
    if (entry.is_dir) {
      reader_batch_status pushed;
      if (!enumerator->options.recursive) {
        free(entry.name);
        free(entry.full);
        continue;
      }
      if (enumerator->current_depth >= enumerator->options.max_depth ||
          enumerator->directories_seen >= enumerator->options.max_directories) {
        free(entry.name);
        free(entry.full);
        enumerator->truncated = 1;
        enumerator->done = 1;
        break;
      }
      pushed = rb_push_directory(enumerator, entry.full, enumerator->current_depth + 1,
          error);
      free(entry.name);
      if (pushed != READER_BATCH_OK) {
        status = pushed;
        break;
      }
      if (enumerator->done) break;
      continue;
    }
    if (!entry.is_file) {
      free(entry.name);
      free(entry.full);
      continue;
    }
    format = rb_format_for_name(entry.name);
    if (format == EXR_CUSTOM) {
      free(entry.name);
      free(entry.full);
      continue;
    }
    if (enumerator->candidates_seen >= enumerator->options.max_candidates) {
      free(entry.name);
      free(entry.full);
      enumerator->truncated = 1;
      enumerator->done = 1;
      break;
    }
    if (rb_relative_path(enumerator, entry.full, &relative, error) != 0) {
      free(entry.name);
      free(entry.full);
      status = error ? error->code : READER_BATCH_INTERNAL;
      break;
    }
    if (strlen(relative) > enumerator->options.max_path_bytes) {
      free(relative);
      free(entry.name);
      free(entry.full);
      enumerator->truncated = 1;
      enumerator->done = 1;
      break;
    }
    batch[produced].struct_size = sizeof(batch[produced]);
    batch[produced].path = entry.full;
    batch[produced].path_bytes = strlen(entry.full);
    batch[produced].relative_path = relative;
    batch[produced].relative_bytes = strlen(relative);
    batch[produced].format = format;
    batch[produced].size_hint = entry.size;
    produced++;
    enumerator->candidates_seen++;
    free(entry.name);
  }
  if (status != READER_BATCH_OK) {
    size_t i;
    for (i = 0; i < produced; i++) {
      free(batch[i].path);
      free(batch[i].relative_path);
    }
    free(batch);
    return status;
  }
  if (!produced) {
    free(batch);
    batch = NULL;
  }
  *items = batch;
  *count = produced;
  *truncated = enumerator->truncated;
  *complete = enumerator->done && !enumerator->truncated;
  return READER_BATCH_OK;
}

void reader_batch_enumerate_close(reader_batch_enumerator *enumerator) {
  size_t i;
  if (!enumerator) return;
  rb_close_current(enumerator);
  for (i = 0; i < enumerator->stack_count; i++) free(enumerator->stack[i].path);
  free(enumerator->stack);
  free(enumerator->root);
  free(enumerator);
}

void reader_batch_candidates_free(reader_batch_candidate *items, size_t count) {
  size_t i;
  if (!items) return;
  for (i = 0; i < count; i++) {
    free(items[i].path);
    free(items[i].relative_path);
  }
  free(items);
}

typedef struct {
  uint64_t size;
  int64_t seconds;
  int64_t nanoseconds;
} rb_stamp;

typedef struct {
#ifdef _WIN32
  HANDLE handle;
#else
  int fd;
#endif
  int open;
} rb_source;

static reader_batch_status rb_source_open(const char *path, rb_source *source,
    rb_stamp *stamp, reader_batch_error *error) {
  memset(source, 0, sizeof(*source));
#ifdef _WIN32
  {
    int encoding = 0;
    wchar_t *wide = rb_widen(path, &encoding);
    BY_HANDLE_FILE_INFORMATION information;
    DWORD type;
    if (!wide)
      return rb_fail(error, READER_BATCH_ENCODING, EXR_ENCODING,
          "Path is not valid UTF-8");
    source->handle = CreateFileW(wide, GENERIC_READ,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, NULL,
        OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_SEQUENTIAL_SCAN,
        NULL);
    free(wide);
    if (source->handle == INVALID_HANDLE_VALUE)
      return rb_fail(error, READER_BATCH_IO, EXR_IO,
          "Cannot open candidate (Windows error %lu)",
          (unsigned long)GetLastError());
    type = GetFileType(source->handle);
    if (type != FILE_TYPE_DISK)
      goto not_regular;
    if (!GetFileInformationByHandle(source->handle, &information))
      goto io_failure;
    if ((information.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT) ||
        (information.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY))
      goto not_regular;
    stamp->size = ((uint64_t)information.nFileSizeHigh << 32) |
        information.nFileSizeLow;
    {
      ULARGE_INTEGER ticks;
      ticks.LowPart = information.ftLastWriteTime.dwLowDateTime;
      ticks.HighPart = information.ftLastWriteTime.dwHighDateTime;
      stamp->seconds = (int64_t)(ticks.QuadPart / UINT64_C(10000000));
      stamp->nanoseconds = (int64_t)((ticks.QuadPart % UINT64_C(10000000)) * 100);
    }
    source->open = 1;
    return READER_BATCH_OK;
  }
io_failure:
  CloseHandle(source->handle);
  source->handle = INVALID_HANDLE_VALUE;
  return rb_fail(error, READER_BATCH_IO, EXR_IO,
      "Cannot inspect candidate (Windows error %lu)",
      (unsigned long)GetLastError());
not_regular:
  CloseHandle(source->handle);
  source->handle = INVALID_HANDLE_VALUE;
  return rb_fail(error, READER_BATCH_ARGUMENT, EXR_FORMAT,
      "Candidate is not a regular file");
#else
  {
    struct stat status;
    source->fd = open(path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (source->fd < 0) {
      if (errno == ELOOP)
        return rb_fail(error, READER_BATCH_ARGUMENT, EXR_FORMAT,
            "Candidate is a symbolic link");
      return rb_fail(error, READER_BATCH_IO, EXR_IO,
          "Cannot open candidate: %s", strerror(errno));
    }
    if (fstat(source->fd, &status) != 0) {
      close(source->fd);
      source->fd = -1;
      return rb_fail(error, READER_BATCH_IO, EXR_IO,
          "Cannot inspect candidate: %s", strerror(errno));
    }
    if (!S_ISREG(status.st_mode)) {
      close(source->fd);
      source->fd = -1;
      return rb_fail(error, READER_BATCH_ARGUMENT, EXR_FORMAT,
          "Candidate is not a regular file");
    }
    stamp->size = (uint64_t)status.st_size;
    stamp->seconds = (int64_t)status.st_mtime;
#ifdef __APPLE__
    /* _POSIX_C_SOURCE hides st_mtimespec on current macOS SDKs. */
    stamp->nanoseconds = 0;
#else
    stamp->nanoseconds = (int64_t)status.st_mtim.tv_nsec;
#endif
    source->open = 1;
    return READER_BATCH_OK;
  }
#endif
}

static void rb_source_close(rb_source *source) {
  if (!source->open) return;
#ifdef _WIN32
  CloseHandle(source->handle);
  source->handle = INVALID_HANDLE_VALUE;
#else
  close(source->fd);
  source->fd = -1;
#endif
  source->open = 0;
}

static reader_batch_status rb_source_read(rb_source *source, void *buffer,
    size_t wanted, size_t *got, reader_batch_error *error) {
  *got = 0;
#ifdef _WIN32
  {
    DWORD read = 0;
    if (!ReadFile(source->handle, buffer, (DWORD)wanted, &read, NULL))
      return rb_fail(error, READER_BATCH_IO, EXR_IO,
          "Cannot read candidate (Windows error %lu)",
          (unsigned long)GetLastError());
    *got = (size_t)read;
    return READER_BATCH_OK;
  }
#else
  {
    ssize_t nread;
    do {
      nread = read(source->fd, buffer, wanted);
    } while (nread < 0 && errno == EINTR);
    if (nread < 0)
      return rb_fail(error, READER_BATCH_IO, EXR_IO,
          "Cannot read candidate: %s", strerror(errno));
    *got = (size_t)nread;
    return READER_BATCH_OK;
  }
#endif
}

static reader_batch_status rb_source_stamp(rb_source *source, rb_stamp *stamp,
    reader_batch_error *error) {
#ifdef _WIN32
  {
    BY_HANDLE_FILE_INFORMATION information;
    if (!GetFileInformationByHandle(source->handle, &information))
      return rb_fail(error, READER_BATCH_IO, EXR_IO,
          "Cannot re-inspect candidate (Windows error %lu)",
          (unsigned long)GetLastError());
    stamp->size = ((uint64_t)information.nFileSizeHigh << 32) |
        information.nFileSizeLow;
    {
      ULARGE_INTEGER ticks;
      ticks.LowPart = information.ftLastWriteTime.dwLowDateTime;
      ticks.HighPart = information.ftLastWriteTime.dwHighDateTime;
      stamp->seconds = (int64_t)(ticks.QuadPart / UINT64_C(10000000));
      stamp->nanoseconds = (int64_t)((ticks.QuadPart % UINT64_C(10000000)) * 100);
    }
    return READER_BATCH_OK;
  }
#else
  {
    struct stat status;
    if (fstat(source->fd, &status) != 0)
      return rb_fail(error, READER_BATCH_IO, EXR_IO,
          "Cannot re-inspect candidate: %s", strerror(errno));
    stamp->size = (uint64_t)status.st_size;
    stamp->seconds = (int64_t)status.st_mtime;
#ifdef __APPLE__
    /* _POSIX_C_SOURCE hides st_mtimespec on current macOS SDKs. */
    stamp->nanoseconds = 0;
#else
    stamp->nanoseconds = (int64_t)status.st_mtim.tv_nsec;
#endif
    return READER_BATCH_OK;
  }
#endif
}

static int rb_stamp_equal(const rb_stamp *a, const rb_stamp *b) {
  return a->size == b->size && a->seconds == b->seconds &&
      a->nanoseconds == b->nanoseconds;
}

static reader_batch_status rb_create_temp(const char *directory, char *path,
    size_t capacity, rb_file *file, reader_batch_error *error) {
  static unsigned long counter;
  unsigned long attempt;
  time_t now = time(NULL);
#ifdef _WIN32
  unsigned long process = (unsigned long)GetCurrentProcessId();
#else
  unsigned long process = (unsigned long)getpid();
#endif
  for (attempt = 0; attempt < RB_TEMP_ATTEMPTS; attempt++) {
    int written = snprintf(path, capacity, "%s%creader-batch-%ld-%lu-%lu-%lu.tmp",
        directory, rb_sep(), (long)now, process, counter++, attempt);
    if (written < 0 || (size_t)written >= capacity)
      return rb_fail(error, READER_BATCH_ARGUMENT, EXR_LIMIT,
          "Staging path exceeds the path limit");
#ifdef _WIN32
    {
      wchar_t *wide = rb_widen(path, NULL);
      if (!wide)
        return rb_fail(error, READER_BATCH_ENCODING, EXR_ENCODING,
            "Staging path is not valid UTF-8");
      *file = CreateFileW(wide, GENERIC_WRITE, 0, NULL, CREATE_NEW,
          FILE_ATTRIBUTE_TEMPORARY, NULL);
      free(wide);
      if (*file != INVALID_HANDLE_VALUE) return READER_BATCH_OK;
      {
        DWORD code = GetLastError();
        if (code == ERROR_FILE_EXISTS || code == ERROR_ALREADY_EXISTS) continue;
        return rb_fail(error, READER_BATCH_IO, EXR_IO,
            "Cannot create staging file (Windows error %lu)", (unsigned long)code);
      }
    }
#else
    *file = open(path, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
    if (*file >= 0) return READER_BATCH_OK;
    if (errno == EEXIST) continue;
    return rb_fail(error, READER_BATCH_IO, EXR_IO,
        "Cannot create staging file: %s", strerror(errno));
#endif
  }
  return rb_fail(error, READER_BATCH_IO, EXR_IO,
      "Cannot allocate a unique staging file");
}

static reader_batch_status rb_write_all(rb_file file, const void *buffer,
    size_t bytes, reader_batch_error *error) {
  const unsigned char *cursor = buffer;
  size_t done = 0;
  while (done < bytes) {
#ifdef _WIN32
    DWORD written = 0;
    DWORD wanted = (DWORD)(bytes - done > 0x7FFFFFFFu ? 0x7FFFFFFFu : bytes - done);
    if (!WriteFile(file, cursor + done, wanted, &written, NULL))
      return rb_fail(error, READER_BATCH_IO, EXR_IO,
          "Cannot write staging file (Windows error %lu)",
          (unsigned long)GetLastError());
    if (!written)
      return rb_fail(error, READER_BATCH_IO, EXR_IO,
          "Staging write made no progress");
    done += (size_t)written;
#else
    ssize_t written;
    do {
      written = write(file, cursor + done, bytes - done);
    } while (written < 0 && errno == EINTR);
    if (written <= 0)
      return rb_fail(error, READER_BATCH_IO, EXR_IO,
          "Cannot write staging file: %s", strerror(errno));
    done += (size_t)written;
#endif
  }
  return READER_BATCH_OK;
}

static void rb_close_file(rb_file file) {
#ifdef _WIN32
  if (file != INVALID_HANDLE_VALUE) CloseHandle(file);
#else
  if (file >= 0) close(file);
#endif
}

static void rb_delete_temp(const char *path) {
#ifdef _WIN32
  wchar_t *wide = rb_widen(path, NULL);
  if (wide) {
    DeleteFileW(wide);
    free(wide);
  }
#else
  unlink(path);
#endif
}

static reader_batch_status rb_stage_file(const char *path, uint64_t limit,
    const char *staging_dir, const exr_control *control, char *temp_path,
    size_t temp_capacity, uint64_t *bytes, reader_batch_error *error) {
  rb_source source;
  rb_stamp before = {0, 0, 0}, after = {0, 0, 0};
  rb_file file = RB_BAD_FILE;
  unsigned char *buffer = NULL;
  reader_batch_status status;
  uint64_t size, done = 0;
  status = rb_source_open(path, &source, &before, error);
  if (status != READER_BATCH_OK) return status;
  size = before.size;
  if (!size) {
    rb_source_close(&source);
    return rb_fail(error, READER_BATCH_ARGUMENT, EXR_FORMAT,
        "Candidate is empty");
  }
  if (size > limit) {
    rb_source_close(&source);
    return rb_fail(error, READER_BATCH_ARGUMENT, EXR_LIMIT,
        "Candidate exceeds its %llu-byte format limit",
        (unsigned long long)limit);
  }
  status = rb_create_temp(staging_dir, temp_path, temp_capacity, &file, error);
  if (status != READER_BATCH_OK) {
    rb_source_close(&source);
    return status;
  }
  buffer = malloc(RB_COPY_CHUNK);
  if (!buffer) {
    status = rb_fail(error, READER_BATCH_MEMORY, EXR_MEMORY,
        "Cannot allocate staging buffer");
    goto finish;
  }
  while (done < size) {
    size_t wanted = (size - done) > RB_COPY_CHUNK ? RB_COPY_CHUNK : (size_t)(size - done);
    size_t got = 0;
    if (rb_cancelled(control)) {
      status = rb_fail(error, READER_BATCH_CANCELLED, EXR_CANCELLED,
          "Import cancelled while staging");
      goto finish;
    }
    status = rb_source_read(&source, buffer, wanted, &got, error);
    if (status != READER_BATCH_OK) goto finish;
    if (!got) {
      status = rb_fail(error, READER_BATCH_IO, EXR_IO,
          "Candidate ended before its observed size");
      goto finish;
    }
    status = rb_write_all(file, buffer, got, error);
    if (status != READER_BATCH_OK) goto finish;
    done += got;
    if (control && control->progress)
      control->progress(control->context, EXR_STAGE_READ, done, size);
    if (rb_cancelled(control)) {
      status = rb_fail(error, READER_BATCH_CANCELLED, EXR_CANCELLED,
          "Import cancelled while staging");
      goto finish;
    }
  }
  status = rb_source_stamp(&source, &after, error);
  if (status != READER_BATCH_OK) goto finish;
  if (!rb_stamp_equal(&before, &after)) {
    status = rb_fail(error, READER_BATCH_IO, EXR_IO,
        "Candidate changed while it was being staged");
    goto finish;
  }
  *bytes = size;
  status = READER_BATCH_OK;
finish:
  free(buffer);
  rb_source_close(&source);
  rb_close_file(file);
  if (status != READER_BATCH_OK) rb_delete_temp(temp_path);
  return status;
}

static void rb_set_failed(reader_batch_result *result, reader_batch_status code,
    exr_status status_code, const char *message) {
  result->status = (code == READER_BATCH_CANCELLED)
      ? READER_BATCH_ITEM_CANCELLED : READER_BATCH_ITEM_FAILED;
  result->status_code = status_code;
  result->committed = 0;
  result->created = 0;
  result->book_id = 0;
  result->message[0] = 0;
  if (message)
    snprintf(result->message, sizeof(result->message), "%.*s",
        (int)sizeof(result->message) - 1, message);
}

static void rb_import_item(exr_library *library, const reader_batch_item *item,
    const reader_batch_import_options *options, uint64_t limit,
    reader_batch_result *result) {
  char *temp = NULL;
  uint64_t bytes = 0;
  reader_batch_error staging;
  reader_batch_status status;
  exr_sideload_options sideload;
  exr_sideload_result imported;
  exr_error sdk_error;
  exr_status sdk_status;
  size_t path_length;
  result->path = item->path;
  result->format = item->format;
  result->status = READER_BATCH_ITEM_NOT_ATTEMPTED;
  result->committed = 0;
  result->created = 0;
  result->book_id = 0;
  result->status_code = EXR_OK;
  result->message[0] = 0;
  if (!item->path || !item->path[0]) {
    rb_set_failed(result, READER_BATCH_ARGUMENT, EXR_ARGUMENT,
        "A candidate path is required");
    return;
  }
  path_length = rb_bounded_len(item->path, READER_BATCH_MAX_PATH_BYTES + 1);
  if (path_length > READER_BATCH_MAX_PATH_BYTES) {
    rb_set_failed(result, READER_BATCH_ARGUMENT, EXR_ARGUMENT,
        "Candidate path exceeds the published path limit");
    return;
  }
  if (!rb_utf8_valid(item->path)) {
    rb_set_failed(result, READER_BATCH_ENCODING, EXR_ENCODING,
        "Candidate path is not valid UTF-8");
    return;
  }
  if (item->format < EXR_TXT || item->format > EXR_CBZ) {
    rb_set_failed(result, READER_BATCH_ARGUMENT, EXR_UNSUPPORTED,
        "Unsupported candidate format");
    return;
  }
  if (rb_cancelled(&options->control)) {
    rb_set_failed(result, READER_BATCH_CANCELLED, EXR_CANCELLED,
        "Import cancelled before staging");
    return;
  }
  temp = malloc(READER_BATCH_MAX_PATH_BYTES + 1);
  if (!temp) {
    rb_set_failed(result, READER_BATCH_MEMORY, EXR_MEMORY,
        "Cannot allocate staging path");
    return;
  }
  memset(&staging, 0, sizeof(staging));
  status = rb_stage_file(item->path, limit, options->staging_dir,
      &options->control, temp, READER_BATCH_MAX_PATH_BYTES + 1, &bytes, &staging);
  if (status != READER_BATCH_OK) {
    rb_set_failed(result, status, staging.status_code,
        staging.message[0] ? staging.message : "Cannot stage candidate");
    free(temp);
    return;
  }
  (void)bytes;
  if (rb_cancelled(&options->control)) {
    rb_delete_temp(temp);
    free(temp);
    rb_set_failed(result, READER_BATCH_CANCELLED, EXR_CANCELLED,
        "Import cancelled after staging");
    return;
  }
  memset(&sideload, 0, sizeof(sideload));
  sideload.struct_size = sizeof(sideload);
  sideload.max_input_bytes = limit;
  sideload.control = options->control;
  memset(&imported, 0, sizeof(imported));
  imported.struct_size = sizeof(imported);
  memset(&sdk_error, 0, sizeof(sdk_error));
  sdk_status = exr_sideload_import_file(library, item->format, temp, item->title,
      &sideload, &imported, &sdk_error);
  rb_delete_temp(temp);
  free(temp);
  if (sdk_status == EXR_OK) {
    if (imported.book_id <= 0) {
      rb_set_failed(result, READER_BATCH_INTERNAL, EXR_IO,
          "SDK reported success without a book id");
      return;
    }
    result->committed = 1;
    result->created = imported.created ? 1 : 0;
    result->book_id = imported.book_id;
    result->status_code = EXR_OK;
    result->status = imported.created ? READER_BATCH_ITEM_IMPORTED
                                      : READER_BATCH_ITEM_DUPLICATE;
    snprintf(result->message, sizeof(result->message), "%s",
        imported.created ? "SDK commit created a new book"
                         : "SDK commit matched an exact duplicate");
    return;
  }
  rb_set_failed(result,
      sdk_status == EXR_CANCELLED ? READER_BATCH_CANCELLED : READER_BATCH_IO,
      sdk_status,
      sdk_error.message[0] ? sdk_error.message : "Sideload import failed");
}

void reader_batch_import_options_init(reader_batch_import_options *options) {
  if (!options) return;
  memset(options, 0, sizeof(*options));
  options->struct_size = sizeof(*options);
}

static reader_batch_status rb_validate_staging_dir(const char *path,
    reader_batch_error *error) {
  size_t length = rb_bounded_len(path, READER_BATCH_MAX_PATH_BYTES + 1);
  if (!path || !path[0])
    return rb_fail(error, READER_BATCH_ARGUMENT, EXR_ARGUMENT,
        "A private staging directory is required");
  if (length > READER_BATCH_MAX_PATH_BYTES)
    return rb_fail(error, READER_BATCH_ARGUMENT, EXR_ARGUMENT,
        "Staging directory path exceeds the published path limit");
  if (!rb_utf8_valid(path))
    return rb_fail(error, READER_BATCH_ENCODING, EXR_ENCODING,
        "Staging directory is not valid UTF-8");
#ifdef _WIN32
  {
    wchar_t *wide = rb_widen(path, NULL);
    DWORD attributes;
    if (!wide)
      return rb_fail(error, READER_BATCH_ENCODING, EXR_ENCODING,
          "Staging directory is not valid UTF-8");
    attributes = GetFileAttributesW(wide);
    free(wide);
    if (attributes == INVALID_FILE_ATTRIBUTES)
      return rb_fail(error, READER_BATCH_IO, EXR_IO,
          "Cannot access staging directory");
    if (attributes & FILE_ATTRIBUTE_REPARSE_POINT)
      return rb_fail(error, READER_BATCH_ARGUMENT, EXR_ARGUMENT,
          "Staging directory must not be a link or junction");
    if (!(attributes & FILE_ATTRIBUTE_DIRECTORY))
      return rb_fail(error, READER_BATCH_ARGUMENT, EXR_ARGUMENT,
          "Staging path is not a directory");
  }
#else
  {
    struct stat status;
    if (lstat(path, &status) != 0)
      return rb_fail(error, READER_BATCH_IO, EXR_IO,
          "Cannot access staging directory: %s", strerror(errno));
    if (S_ISLNK(status.st_mode))
      return rb_fail(error, READER_BATCH_ARGUMENT, EXR_ARGUMENT,
          "Staging directory must not be a symbolic link");
    if (!S_ISDIR(status.st_mode))
      return rb_fail(error, READER_BATCH_ARGUMENT, EXR_ARGUMENT,
          "Staging path is not a directory");
  }
#endif
  return READER_BATCH_OK;
}

reader_batch_status reader_batch_import(exr_library *library,
    const reader_batch_item *items, size_t count,
    const reader_batch_import_options *options, reader_batch_result **results,
    size_t *result_count, reader_batch_error *error) {
  reader_batch_result *output;
  size_t i;
  int stopped = 0;
  if (!results || !result_count)
    return rb_fail(error, READER_BATCH_ARGUMENT, EXR_ARGUMENT,
        "Results and result count are required");
  *results = NULL;
  *result_count = 0;
  if (!library || !items)
    return rb_fail(error, READER_BATCH_ARGUMENT, EXR_ARGUMENT,
        "Library and items are required");
  if (!count || count > READER_BATCH_MAX_BATCH)
    return rb_fail(error, READER_BATCH_ARGUMENT, EXR_ARGUMENT,
        "Import count must be 1..%u", READER_BATCH_MAX_BATCH);
  if (!options || options->struct_size < sizeof(*options))
    return rb_fail(error, READER_BATCH_ARGUMENT, EXR_ARGUMENT,
        "Set a complete import options struct_size");
  for (i = 0; i < count; i++) {
    if (items[i].struct_size < sizeof(items[i]))
      return rb_fail(error, READER_BATCH_ARGUMENT, EXR_ARGUMENT,
          "Set a complete item struct_size at index %llu",
          (unsigned long long)i);
  }
  {
    reader_batch_status status = rb_validate_staging_dir(options->staging_dir, error);
    if (status != READER_BATCH_OK) return status;
  }
  output = calloc(count, sizeof(*output));
  if (!output)
    return rb_fail(error, READER_BATCH_MEMORY, EXR_MEMORY,
        "Cannot allocate import results");
  for (i = 0; i < count; i++) {
    output[i].struct_size = sizeof(output[i]);
    output[i].status = READER_BATCH_ITEM_NOT_ATTEMPTED;
    output[i].path = items[i].path;
    output[i].format = items[i].format;
    output[i].status_code = EXR_OK;
  }
  for (i = 0; i < count; i++) {
    size_t j;
    if (rb_cancelled(&options->control)) {
      for (j = i; j < count; j++) {
        output[j].status = READER_BATCH_ITEM_CANCELLED;
        output[j].status_code = EXR_CANCELLED;
        snprintf(output[j].message, sizeof(output[j].message), "%s",
            "Batch cancelled before this item started");
      }
      stopped = 1;
      break;
    }
    rb_import_item(library, &items[i], options,
        rb_effective_limit(items[i].format, options->max_input_bytes), &output[i]);
    if (options->on_result)
      options->on_result(options->on_result_context, i, &output[i]);
    if (output[i].status == READER_BATCH_ITEM_CANCELLED) {
      for (j = i + 1; j < count; j++) {
        output[j].status = READER_BATCH_ITEM_CANCELLED;
        output[j].status_code = EXR_CANCELLED;
        snprintf(output[j].message, sizeof(output[j].message), "%s",
            "Batch cancelled after an earlier item");
      }
      stopped = 1;
      break;
    }
  }
  *results = output;
  *result_count = count;
  return stopped ? READER_BATCH_CANCELLED : READER_BATCH_OK;
}

void reader_batch_results_free(reader_batch_result *results, size_t count) {
  (void)count;
  free(results);
}

const char *reader_batch_status_name(reader_batch_status status) {
  switch (status) {
    case READER_BATCH_OK: return "OK";
    case READER_BATCH_CANCELLED: return "CANCELLED";
    case READER_BATCH_ARGUMENT: return "ARGUMENT";
    case READER_BATCH_MEMORY: return "MEMORY";
    case READER_BATCH_IO: return "IO";
    case READER_BATCH_ENCODING: return "ENCODING";
    case READER_BATCH_INTERNAL: return "INTERNAL";
    default: return "UNKNOWN";
  }
}

const char *reader_batch_item_status_name(reader_batch_item_status status) {
  switch (status) {
    case READER_BATCH_ITEM_NOT_ATTEMPTED: return "NOT_ATTEMPTED";
    case READER_BATCH_ITEM_IMPORTED: return "IMPORTED";
    case READER_BATCH_ITEM_DUPLICATE: return "DUPLICATE";
    case READER_BATCH_ITEM_FAILED: return "FAILED";
    case READER_BATCH_ITEM_CANCELLED: return "CANCELLED";
    default: return "UNKNOWN";
  }
}

const char *reader_batch_format_name(exr_format format) {
  switch (format) {
    case EXR_TXT: return "TXT";
    case EXR_HTML: return "HTML";
    case EXR_FB2: return "FB2";
    case EXR_EPUB: return "EPUB";
    case EXR_DOCX: return "DOCX";
    case EXR_RTF: return "RTF";
    case EXR_MOBI: return "MOBI";
    case EXR_PDF: return "PDF";
    case EXR_CBZ: return "CBZ";
    case EXR_CUSTOM: return "CUSTOM";
    default: return "UNKNOWN";
  }
}
