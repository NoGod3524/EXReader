/* SPDX-License-Identifier: MIT */
#ifndef OPDS_FS_H
#define OPDS_FS_H
#include <stdio.h>
FILE *opds_fopen_new(const char *path);   /* exclusive create, binary write */
FILE *opds_fopen_read(const char *path);
int opds_remove(const char *path);
/* 0 missing, 1 regular file, 2 directory, 3 link/other, -1 error */
int opds_path_kind(const char *path);
/* 0 published, 1 destination exists (replace=0), -1 error */
int opds_publish(const char *tmp, const char *dest, int replace);
int opds_sync(FILE *f);
#endif
