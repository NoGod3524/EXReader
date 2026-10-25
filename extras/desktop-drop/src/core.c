/* SPDX-License-Identifier: MIT */
#include "internal.h"
#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <sys/stat.h>
#endif

struct exr_drop_request {
  exr_drop_request_info info;
  exr_drop_item *items;
};

static int ascii_alpha(unsigned c) { return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z'); }
static int ascii_alnum(unsigned c) { return ascii_alpha(c) || (c >= '0' && c <= '9'); }
static unsigned ascii_lower(unsigned c) { return c >= 'A' && c <= 'Z' ? c + 32u : c; }
static int ci_equal(const unsigned char *s, size_t n, const char *lit) {
  size_t i;
  if (strlen(lit) != n) return 0;
  for (i = 0; i < n; i++)
    if (ascii_lower(s[i]) != ascii_lower((unsigned char)lit[i])) return 0;
  return 1;
}
static int hex_value(unsigned c) {
  if (c >= '0' && c <= '9') return (int)(c - '0');
  if (c >= 'a' && c <= 'f') return (int)(c - 'a') + 10;
  if (c >= 'A' && c <= 'F') return (int)(c - 'A') + 10;
  return -1;
}

/* ---- strict UTF-8 / UTF-16 ------------------------------------------- */
static size_t utf8_seq(const unsigned char *s, size_t n) {
  unsigned char c = s[0];
  if (c < 0x80) return 1;
  if (c >= 0xC2 && c <= 0xDF) return n >= 2 && (s[1] & 0xC0) == 0x80 ? 2 : 0;
  if (c >= 0xE0 && c <= 0xEF) {
    if (n < 3 || (s[1] & 0xC0) != 0x80 || (s[2] & 0xC0) != 0x80) return 0;
    if (c == 0xE0 && s[1] < 0xA0) return 0;
    if (c == 0xED && s[1] >= 0xA0) return 0;
    return 3;
  }
  if (c >= 0xF0 && c <= 0xF4) {
    if (n < 4 || (s[1] & 0xC0) != 0x80 || (s[2] & 0xC0) != 0x80 || (s[3] & 0xC0) != 0x80) return 0;
    if (c == 0xF0 && s[1] < 0x90) return 0;
    if (c == 0xF4 && s[1] >= 0x90) return 0;
    return 4;
  }
  return 0;
}
static int utf8_valid(const unsigned char *s, size_t n) {
  size_t i = 0;
  while (i < n) {
    size_t length = utf8_seq(s + i, n - i);
    if (!length) return 0;
    i += length;
  }
  return 1;
}
/* Sanitized diagnostic copy: valid UTF-8 only, bad/control bytes become '?'. */
static size_t make_excerpt(const unsigned char *s, size_t n, char *out) {
  size_t o = 0, i = 0;
  while (i < n) {
    unsigned char c = s[i];
    size_t length = 1;
    int ok = 1;
    if (c < 0x20 || c == 0x7F) ok = 0;
    else if (c >= 0x80) {
      length = utf8_seq(s + i, n - i);
      if (!length) { ok = 0; length = 1; }
    }
    if (o + (ok ? length : 1) > EXR_DROP_MAX_SOURCE_BYTES) break;
    if (ok) { memcpy(out + o, s + i, length); o += length; }
    else out[o++] = '?';
    i += length;
  }
  out[o] = 0;
  return o;
}
/* out needs 3 * count + 1 bytes. Returns nonzero if any unit was unpaired
   (replaced by '?'). */
static int utf16_to_utf8(const uint16_t *u, size_t count, char *out, size_t *out_size) {
  size_t i = 0, o = 0;
  int bad = 0;
  while (i < count) {
    unsigned c = u[i++];
    if (c >= 0xD800 && c <= 0xDBFF && i < count && u[i] >= 0xDC00 && u[i] <= 0xDFFF) {
      unsigned long cp = 0x10000ul + (((unsigned long)c - 0xD800ul) << 10) + (unsigned long)(u[i++] - 0xDC00u);
      out[o++] = (char)(0xF0 | (cp >> 18));
      out[o++] = (char)(0x80 | ((cp >> 12) & 0x3F));
      out[o++] = (char)(0x80 | ((cp >> 6) & 0x3F));
      out[o++] = (char)(0x80 | (cp & 0x3F));
    } else if (c >= 0xD800 && c <= 0xDFFF) {
      out[o++] = '?'; bad = 1;
    } else if (c < 0x80) out[o++] = (char)c;
    else if (c < 0x800) {
      out[o++] = (char)(0xC0 | (c >> 6));
      out[o++] = (char)(0x80 | (c & 0x3F));
    } else {
      out[o++] = (char)(0xE0 | (c >> 12));
      out[o++] = (char)(0x80 | ((c >> 6) & 0x3F));
      out[o++] = (char)(0x80 | (c & 0x3F));
    }
  }
  out[o] = 0;
  *out_size = o;
  return bad;
}

/* ---- builder --------------------------------------------------------- */
void drop_builder_init(drop_builder *b, exr_drop_origin origin, const exr_drop_control *control) {
  memset(b, 0, sizeof(*b));
  b->origin = origin;
  if (control) b->control = *control;
}
int drop_builder_stopped(drop_builder *b) {
  if (b->failure != EXR_DROP_OK) return 1;
  if (b->control.cancelled && b->control.cancelled(b->control.context)) {
    b->failure = EXR_DROP_CANCELLED;
    return 1;
  }
  return 0;
}
void drop_builder_free(drop_builder *b) {
  size_t i;
  for (i = 0; i < b->count; i++) { free(b->items[i].path); free(b->items[i].source); }
  free(b->items);
  b->items = NULL;
  b->count = b->capacity = 0;
}
static char *copy_string(const char *s, size_t n) {
  char *p = malloc(n + 1);
  if (!p) return NULL;
  memcpy(p, s, n);
  p[n] = 0;
  return p;
}
/* path may be NULL. src is sanitized here. */
static void push_item(drop_builder *b, exr_drop_item_status status, const char *path, size_t path_size,
    const unsigned char *src, size_t src_size) {
  char excerpt[EXR_DROP_MAX_SOURCE_BYTES + 1];
  drop_tmp_item *item;
  size_t excerpt_size;
  if (b->failure != EXR_DROP_OK) return;
  if (b->count >= EXR_DROP_MAX_ITEMS) { b->overflow++; return; }
  if (b->count == b->capacity) {
    size_t capacity = b->capacity ? b->capacity * 2 : 8;
    drop_tmp_item *grown = realloc(b->items, capacity * sizeof(*grown));
    if (!grown) { b->failure = EXR_DROP_NO_MEMORY; return; }
    b->items = grown;
    b->capacity = capacity;
  }
  item = &b->items[b->count];
  item->status = status;
  item->path = path ? copy_string(path, path_size) : NULL;
  excerpt_size = make_excerpt(src, src_size, excerpt);
  item->source = copy_string(excerpt, excerpt_size);
  if ((path && !item->path) || !item->source) {
    free(item->path); free(item->source);
    b->failure = EXR_DROP_NO_MEMORY;
    return;
  }
  b->count++;
}

/* ---- local paths ----------------------------------------------------- */
static exr_drop_item_status classify(const char *path, size_t size) {
#ifdef _WIN32
  wchar_t wide[EXR_DROP_MAX_PATH_BYTES + 16];
  wchar_t *start = wide;
  int length, room;
  DWORD attributes;
  if (size >= 240) {
    if (path[0] == '\\' && path[1] == '\\') { wcscpy_s(wide, 16, L"\\\\?\\UNC\\"); start = wide + 8; path += 2; size -= 2; }
    else { wcscpy_s(wide, 16, L"\\\\?\\"); start = wide + 4; }
  }
  room = (int)(EXR_DROP_MAX_PATH_BYTES + 16) - (int)(start - wide);
  length = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, (int)size + 1, start, room);
  if (length <= 0) return EXR_DROP_ITEM_UNREADABLE;
  attributes = GetFileAttributesW(wide);
  if (attributes == INVALID_FILE_ATTRIBUTES) {
    DWORD error = GetLastError();
    return error == ERROR_FILE_NOT_FOUND || error == ERROR_PATH_NOT_FOUND || error == ERROR_INVALID_NAME
        ? EXR_DROP_ITEM_MISSING : EXR_DROP_ITEM_UNREADABLE;
  }
  if (attributes & FILE_ATTRIBUTE_DIRECTORY) return EXR_DROP_ITEM_DIRECTORY;
  if (attributes & FILE_ATTRIBUTE_DEVICE) return EXR_DROP_ITEM_NOT_REGULAR;
  return EXR_DROP_ITEM_FILE;
#else
  struct stat info;
  (void)size;
  if (stat(path, &info) != 0)
    return errno == ENOENT || errno == ENOTDIR ? EXR_DROP_ITEM_MISSING : EXR_DROP_ITEM_UNREADABLE;
  if (S_ISDIR(info.st_mode)) return EXR_DROP_ITEM_DIRECTORY;
  if (S_ISREG(info.st_mode)) return EXR_DROP_ITEM_FILE;
  return EXR_DROP_ITEM_NOT_REGULAR;
#endif
}
static int same_path(const char *a, const char *b) {
#ifdef _WIN32
  for (; *a && *b; a++, b++)
    if (ascii_lower((unsigned char)*a) != ascii_lower((unsigned char)*b)) return 0;
  return *a == *b;
#else
  return strcmp(a, b) == 0;
#endif
}
static int absolute_native(const char *p, size_t n) {
#ifdef _WIN32
  return (n >= 3 && ascii_alpha((unsigned char)p[0]) && p[1] == ':' && (p[2] == '\\' || p[2] == '/'))
      || (n >= 3 && p[0] == '\\' && p[1] == '\\');
#else
  return n >= 1 && p[0] == '/';
#endif
}
/* path is a writable buffer of at least size + 1 bytes. */
static void add_local(drop_builder *b, char *path, size_t size, const unsigned char *src, size_t src_size) {
  size_t i, floor_size;
  exr_drop_item_status status;
  if (b->failure != EXR_DROP_OK) return;
  for (i = 0; i < size; i++)
    if ((unsigned char)path[i] < 0x20 || (unsigned char)path[i] == 0x7F) {
      push_item(b, EXR_DROP_ITEM_INVALID, NULL, 0, src, src_size);
      return;
    }
  if (size > EXR_DROP_MAX_PATH_BYTES) { push_item(b, EXR_DROP_ITEM_TOO_LONG, NULL, 0, src, src_size); return; }
  if (!absolute_native(path, size)) { push_item(b, EXR_DROP_ITEM_INVALID, NULL, 0, src, src_size); return; }
#ifdef _WIN32
  for (i = 0; i < size; i++) if (path[i] == '/') path[i] = '\\';
  floor_size = path[0] == '\\' ? 2 : 3;
  while (size > floor_size && path[size - 1] == '\\') size--;
#else
  floor_size = 1;
  while (size > floor_size && path[size - 1] == '/') size--;
#endif
  path[size] = 0;
  for (i = 0; i < b->count; i++)
    if (b->items[i].path && same_path(b->items[i].path, path)) { b->duplicates++; return; }
  status = classify(path, size);
  push_item(b, status, path, size, src, src_size);
}

/* ---- URIs ------------------------------------------------------------ */
static size_t scheme_length(const unsigned char *s, size_t n) {
  size_t i = 0;
  if (!n || !ascii_alpha(s[0])) return 0;
  while (i < n && (ascii_alnum(s[i]) || s[i] == '+' || s[i] == '-' || s[i] == '.')) i++;
  return i < n && s[i] == ':' ? i : 0;
}
static int virtual_scheme(const unsigned char *s, size_t n) {
  static const char *const names[] = {"trash", "recent", "computer", "network", "x-nautilus-desktop",
      "burn", "favorites", "mtp", "gphoto2", "afc", "archive"};
  size_t i;
  for (i = 0; i < sizeof(names) / sizeof(*names); i++)
    if (ci_equal(s, n, names[i])) return 1;
  return 0;
}
static void add_uri(drop_builder *b, const unsigned char *s, size_t n) {
  size_t scheme = scheme_length(s, n), i, rest, host = 0, out = 0;
  const unsigned char *r;
  char *buffer;
  if (scheme < 2) { push_item(b, EXR_DROP_ITEM_INVALID, NULL, 0, s, n); return; }
  for (i = 0; i < n; i++)
    if (s[i] <= 0x20 || s[i] == 0x7F) { push_item(b, EXR_DROP_ITEM_INVALID, NULL, 0, s, n); return; }
  if (!ci_equal(s, scheme, "file")) {
    push_item(b, virtual_scheme(s, scheme) ? EXR_DROP_ITEM_VIRTUAL : EXR_DROP_ITEM_REMOTE_URL, NULL, 0, s, n);
    return;
  }
  r = s + scheme + 1;
  rest = n - scheme - 1;
  if (rest >= 2 && r[0] == '/' && r[1] == '/') {
    r += 2; rest -= 2;
    while (host < rest && r[host] != '/') host++;
    if (!(host == 0 || ci_equal(r, host, "localhost"))) { push_item(b, EXR_DROP_ITEM_REMOTE_HOST, NULL, 0, s, n); return; }
    r += host; rest -= host;
  }
  if (rest == 0 || r[0] != '/') { push_item(b, EXR_DROP_ITEM_INVALID, NULL, 0, s, n); return; }
  buffer = malloc(rest + 2);
  if (!buffer) { b->failure = EXR_DROP_NO_MEMORY; return; }
  for (i = 0; i < rest; i++) {
    unsigned c = r[i];
    if (c == '?' || c == '#') goto invalid;
    if (c == '%') {
      int hi, lo;
      if (i + 2 >= rest) goto invalid;
      hi = hex_value(r[i + 1]); lo = hex_value(r[i + 2]);
      if (hi < 0 || lo < 0 || (hi == 0 && lo == 0)) goto invalid;
      c = (unsigned)(hi * 16 + lo);
      i += 2;
    }
    buffer[out++] = (char)c;
  }
  if (!utf8_valid((const unsigned char *)buffer, out)) {
    free(buffer);
    push_item(b, EXR_DROP_ITEM_BAD_ENCODING, NULL, 0, s, n);
    return;
  }
#ifdef _WIN32
  for (i = 0; i < out; i++) if (buffer[i] == '\\') goto invalid;
  if (out >= 3 && ascii_alpha((unsigned char)buffer[1]) && buffer[2] == ':' && (out == 3 || buffer[3] == '/')) {
    memmove(buffer, buffer + 1, out - 1);
    out--;
    if (out == 2) buffer[out++] = '/';
  } else goto invalid;
#endif
  add_local(b, buffer, out, s, n);
  free(buffer);
  return;
invalid:
  free(buffer);
  push_item(b, EXR_DROP_ITEM_INVALID, NULL, 0, s, n);
}

void drop_add_utf8_entry(drop_builder *b, const char *entry, size_t size) {
  const unsigned char *s = (const unsigned char *)entry;
  char *buffer;
  if (b->failure != EXR_DROP_OK) return;
  if (!utf8_valid(s, size)) { push_item(b, EXR_DROP_ITEM_BAD_ENCODING, NULL, 0, s, size); return; }
  if (scheme_length(s, size) >= 2) { add_uri(b, s, size); return; }
  buffer = malloc(size + 1);
  if (!buffer) { b->failure = EXR_DROP_NO_MEMORY; return; }
  memcpy(buffer, entry, size);
  add_local(b, buffer, size, s, size);
  free(buffer);
}
void drop_add_utf16_entry(drop_builder *b, const uint16_t *units, size_t count) {
  size_t size;
  char *buffer;
  if (b->failure != EXR_DROP_OK) return;
  buffer = malloc(count * 3 + 1);
  if (!buffer) { b->failure = EXR_DROP_NO_MEMORY; return; }
  if (utf16_to_utf8(units, count, buffer, &size)) push_item(b, EXR_DROP_ITEM_BAD_ENCODING, NULL, 0, (const unsigned char *)buffer, size);
  else drop_add_utf8_entry(b, buffer, size);
  free(buffer);
}
void drop_add_virtual(drop_builder *b, const uint16_t *units, size_t count) {
  size_t size;
  char *buffer;
  if (b->failure != EXR_DROP_OK) return;
  buffer = malloc(count * 3 + 1);
  if (!buffer) { b->failure = EXR_DROP_NO_MEMORY; return; }
  utf16_to_utf8(units, count, buffer, &size);
  push_item(b, EXR_DROP_ITEM_VIRTUAL, NULL, 0, (const unsigned char *)buffer, size);
  free(buffer);
}

/* ---- request --------------------------------------------------------- */
exr_drop_status drop_builder_finish(drop_builder *b, exr_drop_request **out) {
  exr_drop_status status = b->failure;
  exr_drop_request *request;
  size_t i, bytes, strings = 0;
  char *cursor;
  *out = NULL;
  if (status == EXR_DROP_OK && b->count == 0) status = EXR_DROP_EMPTY;
  if (status != EXR_DROP_OK) { drop_builder_free(b); return status; }
  for (i = 0; i < b->count; i++)
    strings += (b->items[i].path ? strlen(b->items[i].path) + 1 : 0) + strlen(b->items[i].source) + 1;
  bytes = sizeof(*request) + b->count * sizeof(exr_drop_item) + strings;
  request = calloc(1, bytes);
  if (!request) { drop_builder_free(b); return EXR_DROP_NO_MEMORY; }
  request->items = (exr_drop_item *)(request + 1);
  cursor = (char *)(request->items + b->count);
  request->info.struct_size = sizeof(request->info);
  request->info.origin = b->origin;
  request->info.item_count = b->count;
  request->info.duplicate_count = b->duplicates;
  request->info.overflow_count = b->overflow;
  request->info.truncated = b->overflow != 0;
  for (i = 0; i < b->count; i++) {
    exr_drop_item *item = &request->items[i];
    size_t n;
    item->struct_size = sizeof(*item);
    item->status = b->items[i].status;
    if (item->status == EXR_DROP_ITEM_FILE) request->info.file_count++;
    if (item->status == EXR_DROP_ITEM_DIRECTORY) request->info.directory_count++;
    if (b->items[i].path) {
      n = strlen(b->items[i].path) + 1;
      memcpy(cursor, b->items[i].path, n);
      item->path = cursor;
      cursor += n;
    }
    n = strlen(b->items[i].source) + 1;
    memcpy(cursor, b->items[i].source, n);
    item->source = cursor;
    cursor += n;
  }
  drop_builder_free(b);
  *out = request;
  return EXR_DROP_OK;
}
exr_drop_status exr_drop_request_get_info(const exr_drop_request *request, exr_drop_request_info *info) {
  if (!request || !info || info->struct_size != sizeof(*info)) return EXR_DROP_ARGUMENT;
  *info = request->info;
  return EXR_DROP_OK;
}
exr_drop_status exr_drop_request_get_item(const exr_drop_request *request, size_t index, exr_drop_item *item) {
  if (!request || !item || item->struct_size != sizeof(*item) || index >= request->info.item_count) return EXR_DROP_ARGUMENT;
  *item = request->items[index];
  return EXR_DROP_OK;
}
void exr_drop_request_release(exr_drop_request *request) { free(request); }

const char *exr_drop_status_name(exr_drop_status status) {
  switch (status) {
    case EXR_DROP_OK: return "ok";
    case EXR_DROP_EMPTY: return "empty";
    case EXR_DROP_ARGUMENT: return "argument";
    case EXR_DROP_NO_MEMORY: return "no_memory";
    case EXR_DROP_TOO_LARGE: return "too_large";
    case EXR_DROP_UNSUPPORTED: return "unsupported";
    case EXR_DROP_PLATFORM: return "platform";
    case EXR_DROP_CANCELLED: return "cancelled";
    case EXR_DROP_WRONG_THREAD: return "wrong_thread";
  }
  return "unknown";
}
const char *exr_drop_item_status_name(exr_drop_item_status status) {
  switch (status) {
    case EXR_DROP_ITEM_FILE: return "file";
    case EXR_DROP_ITEM_DIRECTORY: return "directory";
    case EXR_DROP_ITEM_REMOTE_URL: return "remote_url";
    case EXR_DROP_ITEM_REMOTE_HOST: return "remote_host";
    case EXR_DROP_ITEM_VIRTUAL: return "virtual";
    case EXR_DROP_ITEM_INVALID: return "invalid";
    case EXR_DROP_ITEM_BAD_ENCODING: return "bad_encoding";
    case EXR_DROP_ITEM_TOO_LONG: return "too_long";
    case EXR_DROP_ITEM_MISSING: return "missing";
    case EXR_DROP_ITEM_UNREADABLE: return "unreadable";
    case EXR_DROP_ITEM_NOT_REGULAR: return "not_regular";
  }
  return "unknown";
}

/* ---- public parsers -------------------------------------------------- */
static exr_drop_status check_call(size_t size, exr_drop_origin origin, const exr_drop_control *control,
    exr_drop_request **out, int has_data) {
  if (!out) return EXR_DROP_ARGUMENT;
  *out = NULL;
  if (!has_data || origin < EXR_DROP_ORIGIN_DROP || origin > EXR_DROP_ORIGIN_TEXT) return EXR_DROP_ARGUMENT;
  if (control && control->struct_size != sizeof(*control)) return EXR_DROP_ARGUMENT;
  return size > EXR_DROP_MAX_INPUT_BYTES ? EXR_DROP_TOO_LARGE : EXR_DROP_OK;
}
static exr_drop_status uri_list(const char *bytes, size_t size, int gnome, exr_drop_origin origin,
    const exr_drop_control *control, exr_drop_request **out) {
  drop_builder b;
  const unsigned char *p = (const unsigned char *)bytes;
  size_t i = 0;
  int first = 1;
  exr_drop_status status = check_call(size, origin, control, out, bytes != NULL || size == 0);
  if (status != EXR_DROP_OK) return status;
  drop_builder_init(&b, origin, control);
  if (size >= 3 && p[0] == 0xEF && p[1] == 0xBB && p[2] == 0xBF) i = 3;
  while (i < size && !drop_builder_stopped(&b)) {
    size_t start = i, end;
    while (i < size && p[i] != '\n' && p[i] != '\r') i++;
    end = i;
    if (i < size) i += (p[i] == '\r' && i + 1 < size && p[i + 1] == '\n') ? 2 : 1;
    while (start < end && (p[start] == ' ' || p[start] == '\t')) start++;
    while (end > start && (p[end - 1] == ' ' || p[end - 1] == '\t')) end--;
    if (gnome && first) {
      first = 0;
      if (ci_equal(p + start, end - start, "copy") || ci_equal(p + start, end - start, "cut")) continue;
    }
    first = 0;
    if (end == start || p[start] == '#') continue;
    add_uri(&b, p + start, end - start);
  }
  return drop_builder_finish(&b, out);
}
exr_drop_status exr_drop_request_from_uri_list(const char *bytes, size_t size, exr_drop_origin origin,
    const exr_drop_control *control, exr_drop_request **out) {
  return uri_list(bytes, size, 0, origin, control, out);
}
exr_drop_status exr_drop_request_from_gnome_files(const char *bytes, size_t size, exr_drop_origin origin,
    const exr_drop_control *control, exr_drop_request **out) {
  return uri_list(bytes, size, 1, origin, control, out);
}

exr_drop_status drop_utf16_split(const uint16_t *u, size_t count, exr_drop_utf16_layout layout, drop_builder *b) {
  size_t i = 0;
  if (layout == EXR_DROP_UTF16_NUL_LIST) {
    while (i < count && !drop_builder_stopped(b)) {
      size_t start = i;
      while (i < count && u[i]) i++;
      if (i == start) break;
      drop_add_utf16_entry(b, u + start, i - start);
      if (i < count) i++;
    }
  } else {
    if (count && u[0] == 0xFEFF) i = 1;
    while (i < count && !drop_builder_stopped(b)) {
      size_t start = i, end;
      while (i < count && u[i] != '\n' && u[i] != '\r') i++;
      end = i;
      if (i < count) i += (u[i] == '\r' && i + 1 < count && u[i + 1] == '\n') ? 2 : 1;
      while (start < end && (u[start] == ' ' || u[start] == '\t')) start++;
      while (end > start && (u[end - 1] == ' ' || u[end - 1] == '\t')) end--;
      if (end > start) drop_add_utf16_entry(b, u + start, end - start);
    }
  }
  return b->failure;
}
exr_drop_status exr_drop_request_from_utf16(const uint16_t *units, size_t count, exr_drop_utf16_layout layout,
    exr_drop_origin origin, const exr_drop_control *control, exr_drop_request **out) {
  drop_builder b;
  exr_drop_status status = check_call(count > EXR_DROP_MAX_INPUT_BYTES / 2 ? EXR_DROP_MAX_INPUT_BYTES + 1u : count * 2,
      origin, control, out, units != NULL || count == 0);
  if (status != EXR_DROP_OK) return status;
  if (layout != EXR_DROP_UTF16_NUL_LIST && layout != EXR_DROP_UTF16_LINES) return EXR_DROP_ARGUMENT;
  drop_builder_init(&b, origin, control);
  drop_utf16_split(units, count, layout, &b);
  return drop_builder_finish(&b, out);
}
exr_drop_status exr_drop_request_from_utf8_list(const char *const *entries, size_t count, exr_drop_origin origin,
    const exr_drop_control *control, exr_drop_request **out) {
  drop_builder b;
  size_t i, total = 0;
  exr_drop_status status = check_call(0, origin, control, out, entries != NULL || count == 0);
  if (status != EXR_DROP_OK) return status;
  drop_builder_init(&b, origin, control);
  for (i = 0; i < count && !drop_builder_stopped(&b); i++) {
    size_t n;
    if (!entries[i]) { b.failure = EXR_DROP_ARGUMENT; break; }
    n = strnlen(entries[i], EXR_DROP_MAX_INPUT_BYTES + 1);
    total += n;
    if (n > EXR_DROP_MAX_INPUT_BYTES || total > EXR_DROP_MAX_INPUT_BYTES) { b.failure = EXR_DROP_TOO_LARGE; break; }
    if (n) drop_add_utf8_entry(&b, entries[i], n);
  }
  return drop_builder_finish(&b, out);
}

/* ---- targets --------------------------------------------------------- */
int drop_target_options_valid(const exr_drop_target_options *o) {
  return o && o->struct_size == sizeof(*o) && o->on_drop && (!o->control || o->control->struct_size == sizeof(*o->control));
}
void drop_target_init(struct exr_drop_target *t, const exr_drop_target_options *o,
    int (*owner_thread)(const struct exr_drop_target *), void (*release)(struct exr_drop_target *)) {
  memset(&t->control, 0, sizeof(t->control));
  t->control.struct_size = sizeof(t->control);
  t->on_drop = o->on_drop;
  t->context = o->context;
  if (o->control) t->control = *o->control;
  t->dead = t->in_callback = t->destroy_pending = 0;
  t->owner_thread = owner_thread;
  t->release = release;
}
const exr_drop_control *drop_target_control(const struct exr_drop_target *t) { return &t->control; }
void drop_target_deliver(struct exr_drop_target *t, exr_drop_status status, exr_drop_request *request) {
  if (t->dead) { exr_drop_request_release(request); return; }
  t->in_callback = 1;
  t->on_drop(t->context, status, request);
  t->in_callback = 0;
  if (t->destroy_pending) { t->destroy_pending = 0; t->release(t); }
}
exr_drop_status exr_drop_target_destroy(exr_drop_target *t) {
  if (!t) return EXR_DROP_ARGUMENT;
  if (!t->owner_thread(t)) return EXR_DROP_WRONG_THREAD;
  if (t->in_callback) {
    t->dead = 1;
    t->destroy_pending = 1;
    return EXR_DROP_OK;
  }
  t->dead = 1;
  t->release(t);
  return EXR_DROP_OK;
}
