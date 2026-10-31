/* SPDX-License-Identifier: MIT */
#if defined(__APPLE__)
#define _DARWIN_C_SOURCE
#else
#define _DEFAULT_SOURCE
#endif
#define _POSIX_C_SOURCE 200809L

#include "exr_webdav_cleanup.h"

#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

static const char data[] = "managed cleanup payload 20261031\n";
static const char any_uuid[] = "0123456789abcdef0123456789abcdef";
static const char *g_case = "";

#define CHECK(c)                                                                  \
  do {                                                                            \
    if (!(c)) {                                                                   \
      printf("FAIL %s line %d: %s errno=%d\n", g_case, __LINE__, #c, errno);      \
      fflush(stdout);                                                             \
      return 1;                                                                   \
    }                                                                             \
  } while (0)

#ifdef EXR_WC_TEST_HOOKS
static const char *g_phase;
static uint32_t g_state;

/* Synchronous notification only: holds the process at the requested phase
 * until the runner kills it. */
void exr_wc_test_hook(const char *phase, uint32_t slot, uint32_t state) {
  if (!g_phase || slot == UINT32_MAX || state != g_state || strcmp(phase, g_phase) != 0) return;
  printf("HELD %s %u %u\n", phase, (unsigned)slot, (unsigned)state);
  fflush(stdout);
  for (;;) pause();
}
#endif

static int open_dir(int base, const char *name) {
  return openat(base, name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
}

static int make_dir(int base, const char *name) {
  if (mkdirat(base, name, 0700) != 0) return -1;
  return open_dir(base, name);
}

static int write_all(int fd, const char *p, size_t n) {
  while (n) {
    ssize_t k = write(fd, p, n);
    if (k < 0) {
      if (errno == EINTR) continue;
      return -1;
    }
    p += k;
    n -= (size_t)k;
  }
  return 0;
}

static int write_file(int dir, const char *name, const char *text) {
  int fd = openat(dir, name, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
  int rc;
  if (fd < 0) return -1;
  rc = write_all(fd, text, strlen(text));
  return close(fd) != 0 ? -1 : rc;
}

static int read_file(int dir, const char *name, char *buf, size_t cap, size_t *len) {
  int fd = openat(dir, name, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
  *len = 0;
  if (fd < 0) return -1;
  for (;;) {
    ssize_t k = read(fd, buf + *len, cap - *len);
    if (k < 0 && errno == EINTR) continue;
    if (k <= 0 || *len + (size_t)k >= cap) {
      if (k > 0) *len += (size_t)k;
      break;
    }
    *len += (size_t)k;
  }
  close(fd);
  return *len < cap ? 0 : -1;
}

static int same_text(int dir, const char *name, const char *want) {
  char buf[256];
  size_t n;
  return read_file(dir, name, buf, sizeof buf, &n) == 0 && n == strlen(want) && memcmp(buf, want, n) == 0;
}

static int absent(int dir, const char *name) {
  struct stat st;
  return fstatat(dir, name, &st, AT_SYMLINK_NOFOLLOW) != 0 && errno == ENOENT;
}

static uint32_t state_of(exr_wc_root *r, uint32_t slot) {
  exr_wc_info i;
  return exr_wc_inspect(r, slot, &i) == EXR_WC_OK ? i.state : 0;
}

static int txname(exr_wc_root *r, uint32_t slot, char out[36]) {
  exr_wc_info i;
  if (exr_wc_inspect(r, slot, &i) != EXR_WC_OK || strlen(i.transaction_id) != 32) return -1;
  snprintf(out, 36, "tx-%s", i.transaction_id);
  return 0;
}

static int sealed_tx(exr_wc_root *r, exr_wc_tx **tx) {
  int fd = -2;
  CHECK(exr_wc_begin(r, tx, &fd) == EXR_WC_OK && *tx && fd >= 0);
  CHECK(write_all(fd, data, strlen(data)) == 0);
  CHECK(exr_wc_seal(*tx) == EXR_WC_OK);
  return 0;
}

static int published_tx(exr_wc_root *r, int dest, const char *leaf, exr_wc_tx **tx) {
  exr_wc_publish_result p;
  if (sealed_tx(r, tx)) return 1;
  CHECK(exr_wc_publish_at(*tx, dest, leaf, &p) == EXR_WC_OK && p.published == 1 &&
        p.cleanup_pending == 0 && p.receipt_uncertain == 0);
  return 0;
}

static int recovered(exr_wc_root *r, uint32_t start, uint32_t maximum, uint32_t inspected,
                     uint32_t cleaned, uint32_t pending, uint32_t next) {
  exr_wc_recovery_report rep;
  CHECK(exr_wc_recover(r, start, maximum, &rep) == EXR_WC_OK);
  CHECK(rep.inspected == inspected && rep.cleaned == cleaned && rep.pending == pending &&
        rep.refused == 0 && rep.next_slot == next && rep.receipt_uncertain == 0);
  return 0;
}

static int c01(int base) {
  exr_wc_root *r = NULL;
  exr_wc_tx *tx = NULL;
  exr_wc_cleanup_result c;
  char uuid[33], name[36];
  struct stat a, b;
  int dest, rd;
  CHECK(exr_wc_create_at(base, "root", &r, uuid) == EXR_WC_OK && r && strlen(uuid) == 32);
  CHECK((dest = make_dir(base, "dest")) >= 0);
  if (published_tx(r, dest, "book.epub", &tx)) return 1;
  CHECK(state_of(r, 0) == EXR_WC_PUBLISHED && txname(r, 0, name) == 0);
  CHECK(fstatat(dest, "book.epub", &a, AT_SYMLINK_NOFOLLOW) == 0 && a.st_nlink == 2);
  CHECK(same_text(dest, "book.epub", data));
  CHECK(exr_wc_cleanup(tx, 0, &c) == EXR_WC_OK && c.removed == 1 && c.pending == 0 && c.receipt_uncertain == 0);
  CHECK(fstatat(dest, "book.epub", &b, AT_SYMLINK_NOFOLLOW) == 0 && b.st_ino == a.st_ino &&
        b.st_dev == a.st_dev && b.st_nlink == 1 && same_text(dest, "book.epub", data));
  CHECK((rd = open_dir(base, "root")) >= 0 && absent(rd, name));
  CHECK(state_of(r, 0) == EXR_WC_CLEANED);
  CHECK(exr_wc_cleanup(tx, 0, &c) == EXR_WC_OK && c.removed == 0);
  CHECK(exr_wc_tx_close(&tx) == EXR_WC_OK && tx == NULL && exr_wc_tx_close(&tx) == EXR_WC_OK);
  CHECK(exr_wc_close(&r) == EXR_WC_OK && r == NULL && exr_wc_close(&r) == EXR_WC_OK &&
        exr_wc_close(NULL) == EXR_WC_OK);
  CHECK(exr_wc_open_at(base, "root", uuid, &r) == EXR_WC_OK);
  for (int k = 0; k < 2; k++)
    if (recovered(r, 0, 64, 1, 0, 0, 1)) return 1;
  CHECK(exr_wc_close(&r) == EXR_WC_OK);
  return 0;
}

static int abandon(int base, int seal) {
  exr_wc_root *r = NULL;
  exr_wc_tx *tx = NULL;
  exr_wc_cleanup_result c;
  char uuid[33], name[36];
  int fd, rd;
  CHECK(exr_wc_create_at(base, "root", &r, uuid) == EXR_WC_OK);
  CHECK(exr_wc_begin(r, &tx, &fd) == EXR_WC_OK && write_all(fd, data, strlen(data)) == 0);
  if (seal) CHECK(exr_wc_seal(tx) == EXR_WC_OK);
  CHECK(state_of(r, 0) == (uint32_t)(seal ? EXR_WC_SEALED : EXR_WC_OWNED) && txname(r, 0, name) == 0);
  CHECK((rd = open_dir(base, "root")) >= 0 && !absent(rd, name));
  CHECK(exr_wc_cleanup(tx, 1, &c) == EXR_WC_OK && c.removed == 1 && c.pending == 0);
  CHECK(state_of(r, 0) == EXR_WC_CLEANED && absent(rd, name));
  CHECK(exr_wc_tx_close(&tx) == EXR_WC_OK);
  for (int k = 0; k < 2; k++)
    if (recovered(r, 0, 64, 1, 0, 0, 1)) return 1;
  CHECK(exr_wc_close(&r) == EXR_WC_OK);
  return 0;
}

static int c02(int base) { return abandon(base, 0); }
static int c03(int base) { return abandon(base, 1); }

static int c04(int base) {
  exr_wc_root *r = NULL;
  exr_wc_tx *tx = NULL;
  exr_wc_cleanup_result c;
  char uuid[33], name[36];
  int fd, rd, td;
  CHECK(exr_wc_create_at(base, "root", &r, uuid) == EXR_WC_OK);
  CHECK(exr_wc_begin(r, &tx, &fd) == EXR_WC_OK && write_all(fd, data, strlen(data)) == 0);
  CHECK(txname(r, 0, name) == 0 && (rd = open_dir(base, "root")) >= 0 && (td = open_dir(rd, name)) >= 0);
  CHECK(exr_wc_cleanup(tx, 0, &c) == EXR_WC_REFUSED && c.removed == 0 && c.pending == 0);
  CHECK(state_of(r, 0) == EXR_WC_OWNED && !absent(td, "payload"));
  CHECK(exr_wc_seal(tx) == EXR_WC_OK);
  CHECK(exr_wc_cleanup(tx, 0, &c) == EXR_WC_REFUSED && c.removed == 0);
  CHECK(state_of(r, 0) == EXR_WC_SEALED && same_text(td, "payload", data));
  CHECK(exr_wc_cleanup(tx, 1, &c) == EXR_WC_OK && c.removed == 1);
  CHECK(exr_wc_tx_close(&tx) == EXR_WC_OK && exr_wc_close(&r) == EXR_WC_OK);
  return 0;
}

static int c05(int base) {
  exr_wc_root *r = NULL, *r2 = NULL;
  char uuid[33], u2[33];
  CHECK(exr_wc_create_at(base, "root", &r, uuid) == EXR_WC_OK);
  CHECK(exr_wc_open_at(base, "root", uuid, &r2) == EXR_WC_BUSY && r2 == NULL);
  CHECK(exr_wc_create_at(base, "root", &r2, u2) == EXR_WC_EXISTS && r2 == NULL);
  CHECK(exr_wc_close(&r) == EXR_WC_OK);
  CHECK(exr_wc_open_at(base, "root", uuid, &r2) == EXR_WC_OK && r2);
  CHECK(exr_wc_open_at(base, "root", uuid, &r) == EXR_WC_BUSY && r == NULL);
  CHECK(exr_wc_close(&r2) == EXR_WC_OK);
  return 0;
}

static int c07(int base) {
  exr_wc_root *r = NULL, *r2 = NULL;
  exr_wc_tx *tx = NULL, *t2 = NULL;
  exr_wc_recovery_report rep;
  char uuid[33];
  int fd, fd2 = 7;
  CHECK(exr_wc_create_at(base, "root", &r, uuid) == EXR_WC_OK);
  CHECK(exr_wc_begin(r, &tx, &fd) == EXR_WC_OK);
  CHECK(exr_wc_close(&r) == EXR_WC_BUSY && r != NULL);
  CHECK(exr_wc_begin(r, &t2, &fd2) == EXR_WC_BUSY && t2 == NULL && fd2 == -1);
  CHECK(exr_wc_recover(r, 0, 64, &rep) == EXR_WC_BUSY);
  CHECK(exr_wc_tx_close(&tx) == EXR_WC_OK && tx == NULL);
  CHECK(exr_wc_open_at(base, "root", uuid, &r2) == EXR_WC_BUSY && r2 == NULL);
  CHECK(state_of(r, 0) == EXR_WC_OWNED);
  if (recovered(r, 0, 64, 1, 0, 1, 1)) return 1;
  CHECK(exr_wc_close(&r) == EXR_WC_OK && r == NULL);
  return 0;
}

static int c08(int base) {
  exr_wc_root *r = NULL;
  exr_wc_tx *tx = NULL;
  exr_wc_publish_result p;
  exr_wc_cleanup_result c;
  struct stat a, b;
  char uuid[33];
  int dest;
  CHECK(exr_wc_create_at(base, "root", &r, uuid) == EXR_WC_OK);
  CHECK((dest = make_dir(base, "dest")) >= 0 && write_file(dest, "book.epub", "old\n") == 0);
  CHECK(fstatat(dest, "book.epub", &a, AT_SYMLINK_NOFOLLOW) == 0);
  if (sealed_tx(r, &tx)) return 1;
  CHECK(exr_wc_publish_at(tx, dest, "book.epub", &p) == EXR_WC_EXISTS && p.published == 0);
  CHECK(state_of(r, 0) == EXR_WC_SEALED);
  CHECK(fstatat(dest, "book.epub", &b, AT_SYMLINK_NOFOLLOW) == 0 && b.st_ino == a.st_ino &&
        b.st_nlink == 1 && same_text(dest, "book.epub", "old\n"));
  CHECK(exr_wc_cleanup(tx, 1, &c) == EXR_WC_OK && c.removed == 1);
  CHECK(same_text(dest, "book.epub", "old\n"));
  CHECK(exr_wc_tx_close(&tx) == EXR_WC_OK && exr_wc_close(&r) == EXR_WC_OK);
  return 0;
}

static int c09(int base) {
  exr_wc_root *r = NULL;
  exr_wc_tx *tx = NULL;
  exr_wc_publish_result p;
  exr_wc_cleanup_result c;
  char uuid[33], name[36];
  int rd, td;
  CHECK(exr_wc_create_at(base, "root", &r, uuid) == EXR_WC_OK);
  if (sealed_tx(r, &tx)) return 1;
  CHECK(txname(r, 0, name) == 0 && (rd = open_dir(base, "root")) >= 0 && (td = open_dir(rd, name)) >= 0);
  CHECK(exr_wc_publish_at(tx, rd, "book.epub", &p) == EXR_WC_REFUSED && p.published == 0 && absent(rd, "book.epub"));
  CHECK(exr_wc_publish_at(tx, td, "book.epub", &p) == EXR_WC_REFUSED && p.published == 0 && absent(td, "book.epub"));
  CHECK(state_of(r, 0) == EXR_WC_SEALED);
  CHECK(exr_wc_cleanup(tx, 1, &c) == EXR_WC_OK);
  CHECK(exr_wc_tx_close(&tx) == EXR_WC_OK && exr_wc_close(&r) == EXR_WC_OK);
  return 0;
}

static int replaced_payload(int base, int symlink_payload) {
  exr_wc_root *r = NULL;
  exr_wc_tx *tx = NULL;
  exr_wc_publish_result p;
  exr_wc_cleanup_result c;
  struct stat st;
  char uuid[33], name[36];
  int rd, td, dest;
  CHECK(exr_wc_create_at(base, "root", &r, uuid) == EXR_WC_OK);
  CHECK((dest = make_dir(base, "dest")) >= 0);
  if (sealed_tx(r, &tx)) return 1;
  CHECK(txname(r, 0, name) == 0 && (rd = open_dir(base, "root")) >= 0 && (td = open_dir(rd, name)) >= 0);
  CHECK(unlinkat(td, "payload", 0) == 0);
  if (symlink_payload)
    CHECK(symlinkat("../outside", td, "payload") == 0);
  else
    CHECK(write_file(td, "payload", data) == 0);
  CHECK(exr_wc_publish_at(tx, dest, "book.epub", &p) == EXR_WC_REFUSED && p.published == 0);
  CHECK(absent(dest, "book.epub") && state_of(r, 0) == EXR_WC_SEALED);
  CHECK(exr_wc_cleanup(tx, 1, &c) == EXR_WC_REFUSED && c.removed == 0);
  CHECK(fstatat(td, "payload", &st, AT_SYMLINK_NOFOLLOW) == 0);
  if (symlink_payload)
    CHECK(S_ISLNK(st.st_mode));
  else
    CHECK(S_ISREG(st.st_mode) && same_text(td, "payload", data));
  CHECK(exr_wc_tx_close(&tx) == EXR_WC_OK && exr_wc_close(&r) == EXR_WC_OK);
  return 0;
}

static int c10(int base) { return replaced_payload(base, 0); }
static int c11(int base) { return replaced_payload(base, 1); }

static int c12(int base) {
  exr_wc_root *r = NULL;
  exr_wc_tx *tx = NULL;
  exr_wc_cleanup_result c;
  struct stat st;
  char uuid[33], name[36];
  int rd, td, dest;
  CHECK(exr_wc_create_at(base, "root", &r, uuid) == EXR_WC_OK);
  CHECK((dest = make_dir(base, "dest")) >= 0);
  if (published_tx(r, dest, "book.epub", &tx)) return 1;
  CHECK(txname(r, 0, name) == 0 && (rd = open_dir(base, "root")) >= 0 && (td = open_dir(rd, name)) >= 0);
  CHECK(write_file(td, "unknown.txt", "owner\n") == 0);
  CHECK(exr_wc_cleanup(tx, 0, &c) == EXR_WC_IO && c.pending == 1 && c.removed == 0 &&
        (c.native_error == ENOTEMPTY || c.native_error == EEXIST));
  CHECK(state_of(r, 0) == EXR_WC_PUBLISHED && absent(td, "payload") && same_text(td, "unknown.txt", "owner\n"));
  CHECK(fstatat(dest, "book.epub", &st, AT_SYMLINK_NOFOLLOW) == 0 && st.st_nlink == 1 && same_text(dest, "book.epub", data));
  CHECK(exr_wc_tx_close(&tx) == EXR_WC_OK);
  if (recovered(r, 0, 64, 1, 0, 1, 1)) return 1;
  CHECK(same_text(td, "unknown.txt", "owner\n"));
  /* The fixture owner removes its own entry; recovery then completes. */
  CHECK(unlinkat(td, "unknown.txt", 0) == 0 && close(td) == 0);
  if (recovered(r, 0, 64, 1, 1, 0, 1)) return 1;
  CHECK(absent(rd, name) && state_of(r, 0) == EXR_WC_CLEANED);
  if (recovered(r, 0, 64, 1, 0, 0, 1)) return 1;
  CHECK(same_text(dest, "book.epub", data));
  CHECK(exr_wc_close(&r) == EXR_WC_OK);
  return 0;
}

/* Phase one of the real EACCES case; the runner recovers in a new process. */
static int c13(int base) {
  exr_wc_root *r = NULL;
  exr_wc_tx *tx = NULL;
  exr_wc_cleanup_result c;
  struct stat st;
  char uuid[33], name[36];
  int cd, rd, td, dest;
  CHECK(geteuid() != 0);
  CHECK((cd = make_dir(base, "canary")) >= 0 && write_file(cd, "c", "c\n") == 0);
  CHECK(fchmod(cd, 0500) == 0);
  errno = 0;
  CHECK(unlinkat(cd, "c", 0) != 0 && errno == EACCES);
  CHECK(fchmod(cd, 0700) == 0 && unlinkat(cd, "c", 0) == 0 && close(cd) == 0);
  CHECK(unlinkat(base, "canary", AT_REMOVEDIR) == 0);
  CHECK(exr_wc_create_at(base, "root", &r, uuid) == EXR_WC_OK);
  CHECK((dest = make_dir(base, "dest")) >= 0);
  if (published_tx(r, dest, "book.epub", &tx)) return 1;
  CHECK(txname(r, 0, name) == 0 && (rd = open_dir(base, "root")) >= 0 && (td = open_dir(rd, name)) >= 0);
  CHECK(fchmod(td, 0500) == 0);
  CHECK(exr_wc_cleanup(tx, 0, &c) == EXR_WC_IO && c.pending == 1 && c.removed == 0 && c.native_error == EACCES);
  CHECK(state_of(r, 0) == EXR_WC_PUBLISHED && !absent(td, "payload"));
  CHECK(fstatat(dest, "book.epub", &st, AT_SYMLINK_NOFOLLOW) == 0 && st.st_nlink == 2);
  CHECK(exr_wc_tx_close(&tx) == EXR_WC_OK && exr_wc_close(&r) == EXR_WC_OK);
  CHECK(fchmod(td, 0700) == 0);
  printf("UUID %s\n", uuid);
  return 0;
}

static int c14(int base) {
  exr_wc_root *r = NULL;
  exr_wc_tx *tx = NULL;
  exr_wc_recovery_report rep;
  struct stat st;
  char uuid[33], leaf[32];
  int dest;
  CHECK(exr_wc_create_at(base, "root", &r, uuid) == EXR_WC_OK);
  CHECK((dest = make_dir(base, "dest")) >= 0);
  for (int i = 0; i < 5; i++) {
    snprintf(leaf, sizeof leaf, "b%d.epub", i);
    if (published_tx(r, dest, leaf, &tx)) return 1;
    CHECK(exr_wc_tx_close(&tx) == EXR_WC_OK);
  }
  CHECK(exr_wc_recover(r, 0, 0, &rep) == EXR_WC_ARGUMENT);
  CHECK(exr_wc_recover(r, 0, 65, &rep) == EXR_WC_ARGUMENT);
  CHECK(exr_wc_recover(r, 6, 1, &rep) == EXR_WC_ARGUMENT);
  if (recovered(r, 0, 2, 2, 2, 0, 2) || recovered(r, 2, 2, 2, 2, 0, 4) ||
      recovered(r, 4, 2, 1, 1, 0, 5) || recovered(r, 5, 3, 0, 0, 0, 5) ||
      recovered(r, 0, 64, 5, 0, 0, 5) || recovered(r, 0, 64, 5, 0, 0, 5))
    return 1;
  CHECK(exr_wc_recover(r, 0, 64, &rep) == EXR_WC_OK && rep.total_slots == 5);
  for (int i = 0; i < 5; i++) {
    snprintf(leaf, sizeof leaf, "b%d.epub", i);
    CHECK(state_of(r, (uint32_t)i) == EXR_WC_CLEANED);
    CHECK(fstatat(dest, leaf, &st, AT_SYMLINK_NOFOLLOW) == 0 && st.st_nlink == 1 && same_text(dest, leaf, data));
  }
  CHECK(exr_wc_close(&r) == EXR_WC_OK);
  return 0;
}

static int c15(int base) {
  exr_wc_root *r = NULL;
  exr_wc_tx *tx = NULL;
  exr_wc_cleanup_result c;
  exr_wc_info info;
  char uuid[33];
  int fd;
  CHECK(exr_wc_create_at(base, "root", &r, uuid) == EXR_WC_OK);
  for (int i = 0; i < 64; i++) {
    CHECK(exr_wc_begin(r, &tx, &fd) == EXR_WC_OK);
    CHECK(exr_wc_cleanup(tx, 1, &c) == EXR_WC_OK && c.removed == 1);
    CHECK(exr_wc_tx_close(&tx) == EXR_WC_OK);
  }
  tx = (exr_wc_tx *)(void *)&r;
  fd = 123;
  CHECK(exr_wc_begin(r, &tx, &fd) == EXR_WC_LIMIT && tx == NULL && fd == -1);
  CHECK(exr_wc_inspect(r, 64, &info) == EXR_WC_ARGUMENT && state_of(r, 63) == EXR_WC_CLEANED);
  if (recovered(r, 0, 64, 64, 0, 0, 64) || recovered(r, 64, 1, 0, 0, 0, 64)) return 1;
  CHECK(exr_wc_close(&r) == EXR_WC_OK);
  CHECK(exr_wc_open_at(base, "root", uuid, &r) == EXR_WC_OK);
  fd = 123;
  CHECK(exr_wc_begin(r, &tx, &fd) == EXR_WC_LIMIT && tx == NULL && fd == -1);
  CHECK(exr_wc_close(&r) == EXR_WC_OK);
  return 0;
}

static int c16(int base) {
  exr_wc_root *r = NULL;
  char uuid[33], wrong[33];
  CHECK(exr_wc_create_at(base, "root", &r, uuid) == EXR_WC_OK && exr_wc_close(&r) == EXR_WC_OK);
  memcpy(wrong, uuid, sizeof wrong);
  wrong[0] = wrong[0] == '0' ? '1' : '0';
  CHECK(exr_wc_open_at(base, "root", wrong, &r) == EXR_WC_REFUSED && r == NULL);
  CHECK(exr_wc_open_at(base, "root", "0123456789ABCDEF0123456789ABCDEF", &r) == EXR_WC_ARGUMENT && r == NULL);
  CHECK(exr_wc_open_at(base, "root", "abc", &r) == EXR_WC_ARGUMENT && r == NULL);
  CHECK(exr_wc_open_at(base, "root", uuid, &r) == EXR_WC_OK && exr_wc_close(&r) == EXR_WC_OK);
  return 0;
}

static int c17(int base) {
  exr_wc_root *r = NULL;
  char uuid[33];
  int od;
  CHECK((od = make_dir(base, "legacy")) >= 0 && write_file(od, "payload-old", data) == 0);
  CHECK(exr_wc_open_at(base, "legacy", any_uuid, &r) == EXR_WC_REFUSED && r == NULL);
  CHECK(write_file(od, ".lock", "") == 0);
  CHECK(exr_wc_open_at(base, "legacy", any_uuid, &r) == EXR_WC_REFUSED && r == NULL);
  CHECK(exr_wc_create_at(base, "legacy", &r, uuid) == EXR_WC_EXISTS && r == NULL);
  CHECK(same_text(od, "payload-old", data) && absent(od, ".receipt") && absent(od, ".receipt.next"));
  return 0;
}

static int c18(int base) {
  exr_wc_root *r = NULL;
  char uuid[33], u2[33];
  CHECK(exr_wc_create_at(base, "real", &r, uuid) == EXR_WC_OK && exr_wc_close(&r) == EXR_WC_OK);
  CHECK(symlinkat("real", base, "alias") == 0);
  CHECK(exr_wc_open_at(base, "alias", uuid, &r) == EXR_WC_REFUSED && r == NULL);
  CHECK(exr_wc_create_at(base, "alias", &r, u2) == EXR_WC_EXISTS && r == NULL);
  CHECK(exr_wc_open_at(base, "real", uuid, &r) == EXR_WC_OK && exr_wc_close(&r) == EXR_WC_OK);
  return 0;
}

static int c19(int base) {
  exr_wc_root *r = NULL;
  char uuid[33];
  unsigned char byte;
  int rd, fd;
  CHECK(exr_wc_create_at(base, "root", &r, uuid) == EXR_WC_OK && exr_wc_close(&r) == EXR_WC_OK);
  CHECK((rd = open_dir(base, "root")) >= 0 && (fd = openat(rd, ".receipt", O_RDWR | O_NOFOLLOW)) >= 0);
  /* The generation field is structurally unconstrained, so only the CRC
   * can catch this flip. */
  CHECK(pread(fd, &byte, 1, 16) == 1);
  byte ^= 0x01;
  CHECK(pwrite(fd, &byte, 1, 16) == 1);
  CHECK(exr_wc_open_at(base, "root", uuid, &r) == EXR_WC_REFUSED && r == NULL);
  byte ^= 0x01;
  CHECK(pwrite(fd, &byte, 1, 16) == 1 && close(fd) == 0);
  CHECK(exr_wc_open_at(base, "root", uuid, &r) == EXR_WC_OK && exr_wc_close(&r) == EXR_WC_OK);
  return 0;
}

static int c20(int base) {
  exr_wc_root *r = NULL;
  char uuid[33], receipt[8192];
  size_t n;
  int rd, fd;
  CHECK(exr_wc_create_at(base, "root", &r, uuid) == EXR_WC_OK && exr_wc_close(&r) == EXR_WC_OK);
  CHECK((rd = open_dir(base, "root")) >= 0);
  CHECK(write_file(rd, ".receipt.next", "garbage\n") == 0);
  CHECK(exr_wc_open_at(base, "root", uuid, &r) == EXR_WC_REFUSED && r == NULL && !absent(rd, ".receipt.next"));
  CHECK(unlinkat(rd, ".receipt.next", 0) == 0);
  /* A valid copy of the current generation is not an uncommitted successor. */
  CHECK(read_file(rd, ".receipt", receipt, sizeof receipt, &n) == 0 && n == 4160);
  CHECK((fd = openat(rd, ".receipt.next", O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0600)) >= 0);
  CHECK(write_all(fd, receipt, n) == 0 && close(fd) == 0);
  CHECK(exr_wc_open_at(base, "root", uuid, &r) == EXR_WC_REFUSED && r == NULL && !absent(rd, ".receipt.next"));
  CHECK(unlinkat(rd, ".receipt.next", 0) == 0);
  CHECK(exr_wc_open_at(base, "root", uuid, &r) == EXR_WC_OK && exr_wc_close(&r) == EXR_WC_OK);
  return 0;
}

static int c21(int base) {
  exr_wc_root *r = NULL;
  exr_wc_tx *tx = NULL;
  exr_wc_publish_result p;
  exr_wc_cleanup_result c;
  char uuid[33], l120[121], l121[122];
  int dest;
  memset(l120, 'a', 120);
  l120[120] = 0;
  memset(l121, 'a', 121);
  l121[121] = 0;
  {
    const char *bad[] = {"", ".hidden", "a/b", "..", "bad leaf", "caf\xc3\xa9", l121};
    for (size_t i = 0; i < sizeof bad / sizeof bad[0]; i++) {
      r = (exr_wc_root *)(void *)&tx;
      CHECK(exr_wc_create_at(base, bad[i], &r, uuid) == EXR_WC_ARGUMENT && r == NULL);
      CHECK(exr_wc_open_at(base, bad[i], any_uuid, &r) == EXR_WC_ARGUMENT && r == NULL);
    }
    CHECK(absent(base, ".hidden") && absent(base, l121));
  }
  CHECK(exr_wc_create_at(base, NULL, &r, uuid) == EXR_WC_ARGUMENT && r == NULL);
  CHECK(exr_wc_create_at(base, l120, &r, uuid) == EXR_WC_OK && exr_wc_close(&r) == EXR_WC_OK);
  CHECK(exr_wc_create_at(base, "root", &r, uuid) == EXR_WC_OK);
  CHECK((dest = make_dir(base, "dest")) >= 0);
  if (sealed_tx(r, &tx)) return 1;
  CHECK(exr_wc_publish_at(tx, dest, "../x", &p) == EXR_WC_ARGUMENT && p.published == 0);
  CHECK(exr_wc_publish_at(tx, dest, ".x", &p) == EXR_WC_ARGUMENT && p.published == 0);
  CHECK(state_of(r, 0) == EXR_WC_SEALED);
  CHECK(exr_wc_cleanup(tx, 1, &c) == EXR_WC_OK);
  CHECK(exr_wc_tx_close(&tx) == EXR_WC_OK && exr_wc_close(&r) == EXR_WC_OK);
  return 0;
}

static const struct {
  const char *name;
  int (*run)(int);
} cases[] = {
    {"01-normal-publish-cleanup", c01},
    {"02-abandon-owned", c02},
    {"03-abandon-sealed", c03},
    {"04-unauthorized-abandon-refused", c04},
    {"05-same-process-lock", c05},
    {"07-active-tx-blocks-close", c07},
    {"08-existing-target-not-replaced", c08},
    {"09-root-or-txdir-destination-refused", c09},
    {"10-payload-inode-replacement-refused", c10},
    {"11-payload-symlink-refused", c11},
    {"12-unknown-entry-preserved", c12},
    {"13-real-eacces-recovered", c13},
    {"14-bounded-paging-idempotent", c14},
    {"15-lifetime-slot-limit", c15},
    {"16-wrong-uuid", c16},
    {"17-legacy-unreceipted-directory", c17},
    {"18-root-symlink", c18},
    {"19-receipt-checksum-corruption", c19},
    {"20-residual-receipt-next", c20},
    {"21-illegal-leaf", c21},
};

static int cmd_recover(int base, const char *uuid) {
  exr_wc_root *r = NULL;
  exr_wc_recovery_report rep;
  int s = exr_wc_open_at(base, "root", uuid, &r);
  printf("OPEN %d\n", s);
  if (s != EXR_WC_OK) return 0;
  for (int k = 0; k < 2; k++) {
    s = exr_wc_recover(r, 0, 64, &rep);
    printf("RECOVER {\"status\":%d,\"inspected\":%u,\"cleaned\":%u,\"pending\":%u,\"refused\":%u,"
           "\"next_slot\":%u,\"total_slots\":%u,\"receipt_uncertain\":%d,\"native_error\":%d,\"states\":[",
           s, (unsigned)rep.inspected, (unsigned)rep.cleaned, (unsigned)rep.pending, (unsigned)rep.refused,
           (unsigned)rep.next_slot, (unsigned)rep.total_slots, rep.receipt_uncertain, rep.native_error);
    for (uint32_t i = 0; i < rep.total_slots; i++) printf("%s%u", i ? "," : "", (unsigned)state_of(r, i));
    printf("]}\n");
  }
  return exr_wc_close(&r) == EXR_WC_OK ? 0 : 1;
}

#ifdef EXR_WC_TEST_HOOKS
static int cmd_kill_flow(int base, const char *phase, const char *state) {
  exr_wc_root *r = NULL;
  exr_wc_tx *tx = NULL;
  exr_wc_cleanup_result c;
  char uuid[33];
  int dest;
  g_case = phase;
  CHECK(exr_wc_create_at(base, "root", &r, uuid) == EXR_WC_OK);
  CHECK((dest = make_dir(base, "dest")) >= 0);
  printf("UUID %s\n", uuid);
  fflush(stdout);
  g_phase = phase;
  g_state = (uint32_t)strtoul(state, NULL, 10);
  if (published_tx(r, dest, "book.epub", &tx)) return 1;
  CHECK(exr_wc_cleanup(tx, 0, &c) == EXR_WC_OK);
  printf("NOHOLD\n");
  return 1;
}
#endif

int main(int argc, char **argv) {
  int base;
  if (argc < 3 || (base = open(argv[2], O_RDONLY | O_DIRECTORY | O_CLOEXEC)) < 0) {
    fprintf(stderr, "usage: worker COMMAND BASE [ARGS]\n");
    return 2;
  }
  if (strcmp(argv[1], "case") == 0 && argc == 4) {
    for (size_t i = 0; i < sizeof cases / sizeof cases[0]; i++) {
      if (strcmp(cases[i].name, argv[3]) != 0) continue;
      g_case = cases[i].name;
      if (cases[i].run(base)) return 1;
      printf("PASS %s\n", g_case);
      return 0;
    }
    return 2;
  }
  if (strcmp(argv[1], "prep") == 0) {
    exr_wc_root *r = NULL;
    char uuid[33];
    if (exr_wc_create_at(base, "root", &r, uuid) != EXR_WC_OK || exr_wc_close(&r) != EXR_WC_OK) return 1;
    printf("UUID %s\n", uuid);
    return 0;
  }
  if (strcmp(argv[1], "hold") == 0 && argc == 4) {
    exr_wc_root *r = NULL;
    char buf[64];
    int s = exr_wc_open_at(base, "root", argv[3], &r);
    printf("HELD %d\n", s);
    fflush(stdout);
    while (s == EXR_WC_OK && read(STDIN_FILENO, buf, sizeof buf) > 0) {
    }
    return s == EXR_WC_OK && exr_wc_close(&r) == EXR_WC_OK ? 0 : 1;
  }
  if (strcmp(argv[1], "try-open") == 0 && argc == 4) {
    exr_wc_root *r = NULL;
    int s = exr_wc_open_at(base, "root", argv[3], &r);
    printf("STATUS %d\n", s);
    return exr_wc_close(&r) == EXR_WC_OK ? 0 : 1;
  }
  if (strcmp(argv[1], "recover") == 0 && argc == 4) return cmd_recover(base, argv[3]);
#ifdef EXR_WC_TEST_HOOKS
  if (strcmp(argv[1], "kill-flow") == 0 && argc == 5) return cmd_kill_flow(base, argv[3], argv[4]);
#endif
  return 2;
}
