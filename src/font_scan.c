/* SPDX-License-Identifier: MIT */
/* Font manager discovery: platform directories, file enumeration and
   per-file FreeType parsing into index records. */
#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#endif
#include "font_manager_internal.h"
#include "font_internal.h"
#include FT_TRUETYPE_TABLES_H
#include FT_SFNT_NAMES_H
#include FT_TRUETYPE_IDS_H
#ifdef _WIN32
#include <windows.h>
#else
#include <dirent.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#include <errno.h>
#endif

char *exr_fm_join(const char *directory, const char *name) {
  size_t a = strlen(directory), b = strlen(name);
  int slash = a && (directory[a - 1] == '/' || directory[a - 1] == '\\');
  char *out = malloc(a + b + 2);
  if (!out) return NULL;
  memcpy(out, directory, a);
  if (!slash) out[a++] = '/';
  memcpy(out + a, name, b + 1);
  return out;
}
int exr_fm_absolute(const char *p) {
  if (p[0] == '/' || p[0] == '\\') return 1;
#ifdef _WIN32
  if (((p[0] >= 'A' && p[0] <= 'Z') || (p[0] >= 'a' && p[0] <= 'z')) && p[1] == ':') return 1;
#endif
  return 0;
}

#ifdef _WIN32
static wchar_t *wide(const char *path) {
  int n = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1, NULL, 0);
  wchar_t *w;
  if (n <= 0 || !(w = malloc((size_t)n * sizeof(*w)))) return NULL;
  if (!MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1, w, n)) { free(w); return NULL; }
  return w;
}
static char *narrow(const wchar_t *w) {
  int n = WideCharToMultiByte(CP_UTF8, 0, w, -1, NULL, 0, NULL, NULL);
  char *s;
  if (n <= 0 || !(s = malloc((size_t)n))) return NULL;
  if (!WideCharToMultiByte(CP_UTF8, 0, w, -1, s, n, NULL, NULL)) { free(s); return NULL; }
  return s;
}
static int64_t filetime(FILETIME t) { return (int64_t)(((uint64_t)t.dwHighDateTime << 32) | t.dwLowDateTime); }
int exr_fm_stat(const char *path, uint64_t *size, int64_t *mtime) {
  WIN32_FILE_ATTRIBUTE_DATA data;
  wchar_t *w = wide(path);
  BOOL ok;
  if (!w) return -1;
  ok = GetFileAttributesExW(w, GetFileExInfoStandard, &data);
  free(w);
  if (!ok) {
    DWORD error = GetLastError();
    return error == ERROR_FILE_NOT_FOUND || error == ERROR_PATH_NOT_FOUND ? 0 : -1;
  }
  if (size) *size = ((uint64_t)data.nFileSizeHigh << 32) | data.nFileSizeLow;
  if (mtime) *mtime = filetime(data.ftLastWriteTime);
  return (data.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) ? 1 : 2;
}
int exr_fm_rename(const char *from, const char *to) {
  wchar_t *a = wide(from), *b = wide(to);
  int ok = a && b && MoveFileExW(a, b, MOVEFILE_REPLACE_EXISTING);
  free(a); free(b);
  return ok;
}
void exr_fm_remove(const char *path) {
  wchar_t *w = wide(path);
  if (w) _wremove(w);
  free(w);
}
double exr_fm_now_ms(void) {
  LARGE_INTEGER now, frequency;
  QueryPerformanceCounter(&now);
  QueryPerformanceFrequency(&frequency);
  return (double)now.QuadPart * 1000.0 / (double)frequency.QuadPart;
}
#else
int exr_fm_stat(const char *path, uint64_t *size, int64_t *mtime) {
  struct stat s;
  if (stat(path, &s)) return errno == ENOENT || errno == ENOTDIR ? 0 : -1;
  if (size) *size = (uint64_t)s.st_size;
#if defined(__APPLE__)
  if (mtime) *mtime = (int64_t)s.st_mtimespec.tv_sec * 1000000000 + s.st_mtimespec.tv_nsec;
#else
  if (mtime) *mtime = (int64_t)s.st_mtim.tv_sec * 1000000000 + s.st_mtim.tv_nsec;
#endif
  return S_ISDIR(s.st_mode) ? 1 : S_ISREG(s.st_mode) ? 2 : -1;
}
int exr_fm_rename(const char *from, const char *to) { return rename(from, to) == 0; }
void exr_fm_remove(const char *path) { remove(path); }
double exr_fm_now_ms(void) {
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return (double)t.tv_sec * 1000.0 + (double)t.tv_nsec / 1e6;
}
#endif

typedef struct { exr_fm_entry *items; size_t count, capacity; } entry_list;
static int push_entry(entry_list *list, char *path, uint64_t size, int64_t mtime) {
  if (!path || list->count >= EXR_FM_MAX_FILES ||
      !exr_grow((void **)&list->items, &list->capacity, list->count + 1, sizeof(*list->items))) {
    free(path);
    return 0;
  }
  list->items[list->count++] = (exr_fm_entry){path, size, mtime};
  return 1;
}
static int compare_names(const void *a, const void *b) { return strcmp(*(char *const *)a, *(char *const *)b); }
/* Collects child names of one directory, sorted bytewise for determinism. */
static exr_status scan(const char *directory, int depth, entry_list *list, exr_error *e) {
  char **names = NULL;
  size_t count = 0, capacity = 0, i;
  int ok = 1;
  exr_status status = EXR_OK;
#ifdef _WIN32
  WIN32_FIND_DATAW data;
  HANDLE find;
  char *pattern = exr_fm_join(directory, "*");
  wchar_t *w = pattern ? wide(pattern) : NULL;
  free(pattern);
  if (!w) return exr_fail(e, EXR_MEMORY, "Font directory path allocation failed");
  find = FindFirstFileExW(w, FindExInfoBasic, &data, FindExSearchNameMatch, NULL, FIND_FIRST_EX_LARGE_FETCH);
  free(w);
  if (find == INVALID_HANDLE_VALUE) {
    if (GetLastError() == ERROR_FILE_NOT_FOUND) return EXR_OK; /* Empty directory. */
    return exr_fail(e, EXR_IO, "Cannot read font directory: %s", directory);
  }
  do {
    char *name, *path;
    int directory_flag = (data.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) != 0;
    if (!wcscmp(data.cFileName, L".") || !wcscmp(data.cFileName, L"..")) continue;
    if (directory_flag && (data.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT)) continue;
    name = narrow(data.cFileName);
    path = name ? exr_fm_join(directory, name) : NULL;
    free(name);
    if (!path) { ok = 0; break; }
    if (directory_flag) {
      if (!exr_grow((void **)&names, &capacity, count + 1, sizeof(*names))) { free(path); ok = 0; break; }
      names[count++] = path;
    } else if (!push_entry(list, path, ((uint64_t)data.nFileSizeHigh << 32) | data.nFileSizeLow,
                           filetime(data.ftLastWriteTime))) { ok = 0; break; }
  } while (FindNextFileW(find, &data));
  if (ok && GetLastError() != ERROR_NO_MORE_FILES)
    status = exr_fail(e, EXR_IO, "Cannot finish font directory: %s", directory);
  FindClose(find);
#else
  DIR *dir = opendir(directory);
  struct dirent *item;
  if (!dir) return exr_fail(e, EXR_IO, "Cannot read font directory: %s", directory);
  for (;;) {
    char *path;
    errno = 0;
    item = readdir(dir);
    if (!item) {
      if (errno) status = exr_fail(e, EXR_IO, "Cannot finish font directory: %s", directory);
      break;
    }
    if (!strcmp(item->d_name, ".") || !strcmp(item->d_name, "..")) continue;
    path = exr_fm_join(directory, item->d_name);
    if (!path || !exr_grow((void **)&names, &capacity, count + 1, sizeof(*names))) { free(path); ok = 0; break; }
    names[count++] = path;
  }
  closedir(dir);
  {
    size_t kept = 0;
    for (i = 0; i < count; i++) {
      uint64_t size = 0; int64_t mtime = 0;
      int kind = ok ? exr_fm_stat(names[i], &size, &mtime) : 0;
      if (kind == 2) { if (!push_entry(list, names[i], size, mtime)) ok = 0; }
      else if (kind == 1) names[kept++] = names[i];
      else free(names[i]);
    }
    count = kept;
  }
#endif
  if (ok && count) qsort(names, count, sizeof(*names), compare_names);
  for (i = 0; i < count; i++) {
    if (ok && status == EXR_OK && depth < EXR_FM_MAX_DEPTH) status = scan(names[i], depth + 1, list, e);
    free(names[i]);
  }
  free(names);
  if (!ok) return exr_fail(e, list->count >= EXR_FM_MAX_FILES ? EXR_LIMIT : EXR_MEMORY,
                           "Font directory listing failed: %s", directory);
  return status;
}
static int compare_entries(const void *a, const void *b) {
  return strcmp(((const exr_fm_entry *)a)->path, ((const exr_fm_entry *)b)->path);
}
exr_status exr_fm_list(const char *directory, exr_fm_entry **out, size_t *count, exr_error *e) {
  entry_list list = {0};
  exr_status status;
  *out = NULL; *count = 0;
  if ((status = scan(directory, 0, &list, e)) != EXR_OK) {
    exr_fm_entries_free(list.items, list.count);
    return status;
  }
  if (list.count) qsort(list.items, list.count, sizeof(*list.items), compare_entries);
  *out = list.items; *count = list.count;
  return EXR_OK;
}
void exr_fm_entries_free(exr_fm_entry *entries, size_t count) {
  size_t i;
  for (i = 0; i < count; i++) free(entries[i].path);
  free(entries);
}

#if !defined(__ANDROID__) || defined(_WIN32)
static char *env_copy(const char *name) {
#ifdef _WIN32
  wchar_t wname[64], *value;
  size_t i;
  for (i = 0; name[i] && i < 63; i++) wname[i] = (wchar_t)name[i];
  wname[i] = 0;
  value = _wgetenv(wname);
  return value && *value ? narrow(value) : NULL;
#else
  const char *value = getenv(name);
  return value && *value ? exr_copy(value, strlen(value)) : NULL;
#endif
}
#endif
static size_t add_dir(char *out[8], size_t n, const char *base, const char *suffix) {
  if (n < 8 && base) out[n] = suffix ? exr_fm_join(base, suffix) : exr_copy(base, strlen(base));
  return n < 8 && base && out[n] ? n + 1 : n;
}
size_t exr_fm_platform_directories(char *out[8]) {
  size_t n = 0;
  memset(out, 0, 8 * sizeof(*out));
#if defined(_WIN32)
  {
    char *local = env_copy("LOCALAPPDATA"), *windows = env_copy("WINDIR");
    n = add_dir(out, n, local, "Microsoft/Windows/Fonts");
    n = add_dir(out, n, windows ? windows : "C:/Windows", "Fonts");
    free(local); free(windows);
  }
#elif defined(__ANDROID__)
  n = add_dir(out, n, "/system/fonts", NULL);
  n = add_dir(out, n, "/product/fonts", NULL);
#elif defined(__APPLE__)
  {
    char *home = env_copy("HOME");
    n = add_dir(out, n, home, "Library/Fonts");
    n = add_dir(out, n, "/Library/Fonts", NULL);
    n = add_dir(out, n, "/System/Library/Fonts", NULL);
    free(home);
  }
#else
  {
    char *home = env_copy("HOME"), *data = env_copy("XDG_DATA_HOME");
    if (data) n = add_dir(out, n, data, "fonts");
    else n = add_dir(out, n, home, ".local/share/fonts");
    n = add_dir(out, n, home, ".fonts");
    n = add_dir(out, n, "/usr/local/share/fonts", NULL);
    n = add_dir(out, n, "/usr/share/fonts", NULL);
    free(home); free(data);
  }
#endif
  return n;
}
const char *exr_fm_default_serif(void) {
#if defined(_WIN32)
  return "Times New Roman, Noto Serif SC, SimSun, Georgia";
#elif defined(__ANDROID__)
  return "Noto Serif, Noto Serif CJK SC";
#elif defined(__APPLE__)
  return "Times New Roman, Times, Songti SC, STSong";
#else
  return "DejaVu Serif, Liberation Serif, Noto Serif, Noto Serif CJK SC, Noto Serif SC, AR PL UMing CN";
#endif
}
const char *exr_fm_default_sans(void) {
#if defined(_WIN32)
  return "Segoe UI, Arial, Noto Sans SC, Microsoft YaHei, SimHei";
#elif defined(__ANDROID__)
  return "Roboto, Noto Sans CJK SC";
#elif defined(__APPLE__)
  return "Helvetica Neue, Helvetica, PingFang SC, Hiragino Sans GB";
#else
  return "DejaVu Sans, Liberation Sans, Noto Sans, Noto Sans CJK SC, Noto Sans SC, WenQuanYi Micro Hei";
#endif
}

/* FreeType stream over a UTF-8 path (FreeType's own stdio opener is ANSI on Windows). */
static unsigned long stream_read(FT_Stream stream, unsigned long offset, unsigned char *buffer, unsigned long count) {
  FILE *f = stream->descriptor.pointer;
  if (fseek(f, (long)offset, SEEK_SET)) return count ? 0 : 1;
  return count ? (unsigned long)fread(buffer, 1, count, f) : 0;
}
static void stream_close(FT_Stream stream) { (void)stream; }
static int script_of(uint32_t c) {
  if ((c >= 0x3000 && c <= 0x30ff) || (c >= 0x3100 && c <= 0x312f) || (c >= 0x3131 && c <= 0x318f) ||
      (c >= 0x31a0 && c <= 0x31ff) || (c >= 0x3400 && c <= 0x4dbf) || (c >= 0x4e00 && c <= 0x9fff) ||
      (c >= 0xac00 && c <= 0xd7af) || (c >= 0xf900 && c <= 0xfaff) || (c >= 0x20000 && c <= 0x3134f))
    return EXR_FONT_SCRIPT_CJK;
  if ((c >= 0x0370 && c <= 0x1dff) || (c >= 0x1f00 && c <= 0x1fff) || (c >= 0x2c80 && c <= 0x2dff) ||
      (c >= 0xa4d0 && c <= 0xabff) || (c >= 0xfb1d && c <= 0xfdff) || (c >= 0xfe70 && c <= 0xfefc) ||
      (c >= 0x10000 && c <= 0x1efff))
    return EXR_FONT_SCRIPT_OTHER;
  return 0;
}
static int coverage(FT_Face face, exr_fm_face *out) {
  FT_UInt glyph;
  FT_ULong c = FT_Get_First_Char(face, &glyph);
  size_t capacity = 0, latin = 0;
  while (glyph) {
    uint32_t cp = (uint32_t)c;
    if (cp <= 0x10ffff && !(cp >= 0xd800 && cp <= 0xdfff)) {
      if (out->range_count && out->ranges[2 * out->range_count - 1] + 1 == cp)
        out->ranges[2 * out->range_count - 1] = cp;
      else if (!out->range_count || out->ranges[2 * out->range_count - 1] < cp) {
        if (!exr_grow((void **)&out->ranges, &capacity, 2 * out->range_count + 2, sizeof(*out->ranges))) return 0;
        out->ranges[2 * out->range_count] = out->ranges[2 * out->range_count + 1] = cp;
        out->range_count++;
      } else { c = FT_Get_Next_Char(face, c, &glyph); continue; } /* Non-ascending cmap entry. */
      out->codepoints++;
      if ((cp >= 'A' && cp <= 'Z') || (cp >= 'a' && cp <= 'z')) latin++;
      out->scripts |= (unsigned)script_of(cp);
    }
    c = FT_Get_Next_Char(face, c, &glyph);
  }
  if (latin >= 40) out->scripts |= EXR_FONT_SCRIPT_LATIN;
  return 1;
}
/* UTF-16BE (Windows/Unicode platform) name to UTF-8; NULL for other encodings. */
static char *name_text(const FT_SfntName *name) {
  exr_buffer b = {0};
  FT_UInt i;
  int unicode = name->platform_id == TT_PLATFORM_MICROSOFT ?
                (name->encoding_id == TT_MS_ID_UNICODE_CS || name->encoding_id == TT_MS_ID_UCS_4) :
                name->platform_id == TT_PLATFORM_APPLE_UNICODE;
  if (!unicode || name->string_len < 2 || (name->string_len & 1)) return NULL;
  for (i = 0; i + 1 < name->string_len; i += 2) {
    uint32_t cp = ((uint32_t)name->string[i] << 8) | name->string[i + 1];
    if (cp >= 0xd800 && cp <= 0xdbff && i + 3 < name->string_len) {
      uint32_t low = ((uint32_t)name->string[i + 2] << 8) | name->string[i + 3];
      if (low >= 0xdc00 && low <= 0xdfff) { cp = 0x10000 + ((cp - 0xd800) << 10) + (low - 0xdc00); i += 2; }
    }
    if (cp < 0x20 || (cp >= 0xd800 && cp <= 0xdfff)) continue;
    if (!exr_codepoint(&b, cp)) { free(b.data); return NULL; }
  }
  return b.data;
}
static int contains_line(const char *list, const char *name) {
  size_t n = strlen(name);
  while (list && *list) {
    const char *end = strchr(list, '\n');
    size_t len = end ? (size_t)(end - list) : strlen(list);
    if (len == n && !memcmp(list, name, n)) return 1;
    list = end ? end + 1 : NULL;
  }
  return 0;
}
static int names(FT_Face face, exr_fm_face *out) {
  FT_UInt i, count = FT_Get_Sfnt_Name_Count(face);
  char *typographic = NULL, *subfamily = NULL;
  exr_buffer aliases = {0};
  for (i = 0; i < count; i++) {
    FT_SfntName name;
    char *text;
    if (FT_Get_Sfnt_Name(face, i, &name)) continue;
    if (name.name_id != TT_NAME_ID_FONT_FAMILY && name.name_id != TT_NAME_ID_TYPOGRAPHIC_FAMILY &&
        name.name_id != TT_NAME_ID_TYPOGRAPHIC_SUBFAMILY) continue;
    if (!(text = name_text(&name))) continue;
    if (!*text) { free(text); continue; }
    if (name.platform_id == TT_PLATFORM_MICROSOFT && name.language_id == TT_MS_LANGID_ENGLISH_UNITED_STATES) {
      if (name.name_id == TT_NAME_ID_TYPOGRAPHIC_FAMILY && !typographic) { typographic = text; continue; }
      if (name.name_id == TT_NAME_ID_TYPOGRAPHIC_SUBFAMILY && !subfamily) { subfamily = text; continue; }
    }
    if (name.name_id != TT_NAME_ID_TYPOGRAPHIC_SUBFAMILY && !contains_line(aliases.data, text) &&
        ((aliases.size && !exr_append(&aliases, "\n", 1)) || !exr_append(&aliases, text, strlen(text)))) {
      free(text); free(typographic); free(subfamily); free(aliases.data);
      return 0;
    }
    free(text);
  }
  if (typographic) out->family = typographic;
  else {
    const char *family = face->family_name ? face->family_name : "";
    out->family = exr_copy(family, strlen(family));
  }
  if (subfamily) out->style_name = subfamily;
  else {
    const char *style = face->style_name ? face->style_name : "";
    out->style_name = exr_copy(style, strlen(style));
  }
  out->aliases = aliases.data ? aliases.data : exr_copy("", 0);
  return out->family && out->style_name && out->aliases;
}
static void face_clear(exr_fm_face *face) {
  free(face->family); free(face->style_name); free(face->aliases); free(face->ranges);
  memset(face, 0, sizeof(*face));
}
void exr_fm_file_clear(exr_fm_file *file) {
  size_t i;
  for (i = 0; i < file->face_count; i++) face_clear(&file->faces[i]);
  free(file->faces); free(file->path); free(file->detail);
  memset(file, 0, sizeof(*file));
}
static exr_status skip(exr_fm_file *file, unsigned reason, const char *detail, exr_error *e) {
  size_t i;
  for (i = 0; i < file->face_count; i++) face_clear(&file->faces[i]);
  free(file->faces); file->faces = NULL; file->face_count = 0;
  file->skip = reason;
  free(file->detail);
  file->detail = exr_copy(detail, strlen(detail));
  return file->detail ? EXR_OK : exr_fail(e, EXR_MEMORY, "Font index allocation failed");
}
exr_status exr_fm_parse(void *library_handle, exr_fm_file *file, exr_error *e) {
  FT_Library library = library_handle;
  FT_StreamRec stream;
  FT_Open_Args args;
  FT_Face face = NULL;
  FILE *f = exr_fopen(file->path, "rb");
  FT_Long faces, i;
  FT_Error error;
  char detail[96];
  exr_status status = EXR_OK;
  if (!f) return skip(file, EXR_FONT_SKIP_IO, "cannot open file", e);
  if (file->size > (uint64_t)LONG_MAX) { fclose(f); return skip(file, EXR_FONT_SKIP_UNSUPPORTED, "file too large", e); }
  memset(&stream, 0, sizeof(stream));
  stream.size = (unsigned long)file->size;
  stream.descriptor.pointer = f;
  stream.read = stream_read;
  stream.close = stream_close;
  memset(&args, 0, sizeof(args));
  args.flags = FT_OPEN_STREAM;
  args.stream = &stream;
  error = FT_Open_Face(library, &args, -1, &face);
  if (error || !face) {
    fclose(f);
    snprintf(detail, sizeof(detail), "FreeType cannot open font (error 0x%02x)", (unsigned)error);
    return skip(file, EXR_FONT_SKIP_DAMAGED, detail, e);
  }
  faces = face->num_faces;
  FT_Done_Face(face);
  if (faces < 1 || faces > 4096) { fclose(f); return skip(file, EXR_FONT_SKIP_DAMAGED, "invalid face count", e); }
  file->faces = calloc((size_t)faces, sizeof(*file->faces));
  if (!file->faces) { fclose(f); return exr_fail(e, EXR_MEMORY, "Font index allocation failed"); }
  detail[0] = 0;
  for (i = 0; i < faces; i++) {
    exr_fm_face *out = &file->faces[file->face_count];
    TT_OS2 *os2;
    face = NULL;
    error = FT_Open_Face(library, &args, i, &face);
    if (error || !face) { snprintf(detail, sizeof(detail), "FreeType cannot open face %ld (error 0x%02x)", (long)i, (unsigned)error); continue; }
    if (!exr_font_face_supported(face) || FT_Select_Charmap(face, FT_ENCODING_UNICODE)) {
      snprintf(detail, sizeof(detail), "face %ld has no supported Unicode charmap", (long)i);
      FT_Done_Face(face);
      continue;
    }
    out->face_index = (unsigned)i;
    os2 = FT_Get_Sfnt_Table(face, FT_SFNT_OS2);
    out->weight = os2 && os2->version != 0xffff && os2->usWeightClass ? os2->usWeightClass : 400;
    out->style = ((face->style_flags & FT_STYLE_FLAG_BOLD) || out->weight >= 600 ? EXR_FONT_STYLE_BOLD : 0u) |
                 ((face->style_flags & FT_STYLE_FLAG_ITALIC) ||
                  (os2 && os2->version != 0xffff && (os2->fsSelection & 0x201)) ? EXR_FONT_STYLE_ITALIC : 0u);
    if (!names(face, out) || !coverage(face, out)) {
      FT_Done_Face(face);
      face_clear(out);
      status = exr_fail(e, EXR_MEMORY, "Font index allocation failed");
      break;
    }
    FT_Done_Face(face);
    if (!out->codepoints) { face_clear(out); snprintf(detail, sizeof(detail), "face %ld maps no Unicode scalar", (long)i); continue; }
    file->face_count++;
  }
  fclose(f);
  if (status != EXR_OK) return status;
  if (!file->face_count)
    return skip(file, strstr(detail, "FreeType") ? EXR_FONT_SKIP_DAMAGED : EXR_FONT_SKIP_UNSUPPORTED,
                detail[0] ? detail : "no usable face", e);
  file->skip = 0;
  return EXR_OK;
}
