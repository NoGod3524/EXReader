/* SPDX-License-Identifier: MIT */
#define _GNU_SOURCE
#include <errno.h>
#include <string.h>
#include <sys/syscall.h>
#include <unistd.h>

/* Inject an I/O failure only for the exporter temporary-file publication. */
int linkat(int fromfd, const char *from, int tofd, const char *to, int flags) {
  if (from && strncmp(from, ".roe-v1-", 8) == 0) {
    errno = EIO;
    return -1;
  }
  return (int)syscall(SYS_linkat, fromfd, from, tofd, to, flags);
}
