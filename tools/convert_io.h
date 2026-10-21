/* SPDX-License-Identifier: MIT */
#ifndef EXREADER_CONVERT_IO_H
#define EXREADER_CONVERT_IO_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* UTF-8 path helpers for the conversion tool. Windows uses the wide APIs, so
   non-ASCII argv and paths reach CreateFileW/MoveFileExW, not the ANSI CRT. */
typedef struct {
  int exists, is_dir, is_file;
  uint64_t volume, index;
} cv_file_id;
int cv_read_prefix(const char *path, void *buffer, size_t capacity, size_t *read,
                   char **error);
/* Reads a complete file. The returned buffer is owned by the caller and has a
   trailing NUL for convenience; size excludes it. */
int cv_read_file(const char *path, unsigned char **data, size_t *size, char **error);
int cv_sha256_file(const char *path, char hex[65], char **error);
int cv_file_size(const char *path, uint64_t *size, char **error);
int cv_identity(const char *path, cv_file_id *id, char **error);
/* Nonzero when both names denote the same existing file or, for a missing
   target, its resolved parent directory plus basename equals the source. */
int cv_same_file(const char *a, const char *b, int *same, char **error);
char *cv_absolute(const char *path, char **error);
/* Path spelling comparison: case-insensitive on Windows, byte-exact elsewhere.
   Use cv_same_file for existing-file identity. */
int cv_path_equal(const char *a, const char *b);
char *cv_join(const char *base, const char *path);
char *cv_dirname(const char *path);
char *cv_basename(const char *path);
const char *cv_extension(const char *path);
char *cv_replace_extension(const char *path, const char *extension);
int cv_mkdir(const char *path, char **error);
/* Same-directory, exclusively created temporary file. The returned path is
   UTF-8 and owned by the caller. Data is flushed before close. */
int cv_write_temp(const char *target, const void *data, size_t size, char **temp,
                  char **error);
/* Atomic publication. Without overwrite an existing target is preserved and
   publication fails; with overwrite the previous bytes remain on failure. */
int cv_publish(const char *temp, const char *target, int overwrite, char **error);
void cv_remove(const char *path);
int cv_is_absolute(const char *path);
size_t cv_peak_rss(void);
void cv_release_unused_memory(void);
void cv_memory_diag(const char *label, size_t index);
uint64_t cv_now_ms(void);
void cv_sha256_hex(const void *data, size_t size, char hex[65]);
#ifdef __cplusplus
}
#endif
#endif
