/* SPDX-License-Identifier: MIT */
#ifndef EXR_FONT_MANAGER_INTERNAL_H
#define EXR_FONT_MANAGER_INTERNAL_H
#include "base_internal.h"
#include "exr/font_manager.h"
#define EXR_FM_MAX_FACES ((size_t)65536)
#define EXR_FM_MAX_FILES ((size_t)200000)
#define EXR_FM_MAX_DEPTH 8
typedef struct {
  unsigned face_index, style, weight, scripts;
  char *family, *style_name;
  char *aliases; /* '\n'-separated localized family names, may be empty. */
  uint32_t *ranges; /* Inclusive [start,end] pairs, ascending. */
  size_t range_count, codepoints;
} exr_fm_face;
/* One discovered or cached font file. skip==0 means faces are valid. */
typedef struct {
  char *path;
  uint64_t size;
  int64_t mtime;
  size_t location;
  unsigned skip;
  char *detail;
  exr_fm_face *faces;
  size_t face_count;
} exr_fm_file;
typedef struct {
  exr_fm_file *items;
  size_t count, capacity;
} exr_fm_files;
typedef struct { size_t file, face; } exr_fm_ref;
typedef struct { char *path, *detail; unsigned reason; } exr_fm_skip;
struct exr_font_manager {
  exr_fm_files files;
  exr_fm_ref *faces; /* Flattened public face order. */
  size_t face_count;
  exr_fm_skip *skips;
  size_t skip_count, skip_capacity;
  char **fallback;
  size_t fallback_count;
  char *serif, *sans;
  exr_font_manager_summary summary;
};
/* Platform file system (font_scan.c). */
typedef struct { char *path; uint64_t size; int64_t mtime; } exr_fm_entry;
/* 1 = directory, 2 = regular file, 0 = missing, -1 = other/unreadable. */
int exr_fm_stat(const char *path, uint64_t *size, int64_t *mtime);
/* Recursive file listing in sorted, deterministic order. */
exr_status exr_fm_list(const char *directory, exr_fm_entry **out, size_t *count, exr_error *error);
void exr_fm_entries_free(exr_fm_entry *entries, size_t count);
/* Owned platform directories (user first, then system); NULL entries absent. */
size_t exr_fm_platform_directories(char *out[8]);
const char *exr_fm_default_serif(void);
const char *exr_fm_default_sans(void);
int exr_fm_rename(const char *from, const char *to);
void exr_fm_remove(const char *path);
double exr_fm_now_ms(void);
char *exr_fm_join(const char *directory, const char *name);
int exr_fm_absolute(const char *path);
/* Parses all faces of one file with FreeType. Never fails for bad fonts:
   it sets file->skip/detail instead. Returns EXR_MEMORY only. */
exr_status exr_fm_parse(void *library, exr_fm_file *file, exr_error *error);
void exr_fm_file_clear(exr_fm_file *file);
/* Cache (font_cache.c). */
exr_status exr_fm_cache_read(const char *path, exr_fm_files *out);
exr_status exr_fm_cache_write(const char *path, const exr_fm_files *files, exr_error *error);
#endif
