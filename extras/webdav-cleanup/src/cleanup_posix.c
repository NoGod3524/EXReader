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
#include <sys/types.h>
#include <sys/file.h>
#include <sys/random.h>
#include <sys/stat.h>
#include <unistd.h>

#ifdef EXR_WC_TEST_HOOKS
extern void exr_wc_test_hook(const char *phase, uint32_t slot, uint32_t state);
#define WC_HOOK(p, s, t) exr_wc_test_hook((p), (s), (t))
#else
#define WC_HOOK(p, s, t) ((void)(p), (void)(s), (void)(t))
#endif

enum { WC_SLOTS = 64, WC_HEAD = 64, WC_SLOT_SIZE = 64,
       WC_RECEIPT = WC_HEAD + WC_SLOTS * WC_SLOT_SIZE };

/* Receipt header: 0 magic[8], 8 version, 12 count, 16 generation,
 * 24 root inode, 32 uuid[16], 48 reserved[12], 60 crc32.
 * Slot: 0 state, 4 reserved, 8 bytes, 16 directory inode, 24 payload inode,
 * 32 transaction id[16], 48 reserved[16].  All integers little-endian. */
static const unsigned char wc_magic[8] = {'E', 'X', 'R', 'W', 'C', 'R', 'C', 'T'};
static const char wc_lock[] = ".lock";
static const char wc_receipt[] = ".receipt";
static const char wc_next[] = ".receipt.next";
static const char wc_payload[] = "payload";

typedef struct {
  uint32_t state;
  uint64_t bytes, dir_ino, payload_ino;
  unsigned char id[16];
} wc_slot;

typedef struct {
  uint64_t generation, root_ino;
  uint32_t count;
  unsigned char uuid[16];
  wc_slot slots[WC_SLOTS];
} wc_image;

struct exr_wc_root {
  int dirfd, lockfd, poisoned;
  dev_t dev;
  wc_image m;
  exr_wc_tx *active;
};

/* hold is a component-only read handle on the payload, open from begin until
 * the slot is cleaned or tx_close.  It keeps the payload inode allocated, so a
 * replaced payload can never reuse the recorded inode number meanwhile. */
struct exr_wc_tx {
  exr_wc_root *root;
  uint32_t slot;
  int dirfd, fd, hold;
};

enum { WC_DONE, WC_PENDING, WC_DENIED, WC_UNSURE };
enum { WC_READ_OK, WC_READ_MISSING, WC_READ_BAD, WC_READ_IO };

static void wc_put32(unsigned char *p, uint32_t v) {
  for (int i = 0; i < 4; i++) p[i] = (unsigned char)(v >> (8 * i));
}

static void wc_put64(unsigned char *p, uint64_t v) {
  for (int i = 0; i < 8; i++) p[i] = (unsigned char)(v >> (8 * i));
}

static uint32_t wc_get32(const unsigned char *p) {
  uint32_t v = 0;
  for (int i = 3; i >= 0; i--) v = (v << 8) | p[i];
  return v;
}

static uint64_t wc_get64(const unsigned char *p) {
  uint64_t v = 0;
  for (int i = 7; i >= 0; i--) v = (v << 8) | p[i];
  return v;
}

static int wc_zero(const unsigned char *p, size_t n) {
  for (size_t i = 0; i < n; i++)
    if (p[i]) return 0;
  return 1;
}

static uint32_t wc_crc(const unsigned char *p, size_t n) {
  uint32_t c = 0xffffffffu;
  for (size_t i = 0; i < n; i++) {
    c ^= p[i];
    for (int k = 0; k < 8; k++) c = (c >> 1) ^ (0xedb88320u & (0u - (c & 1u)));
  }
  return ~c;
}

static void wc_encode(const wc_image *m, unsigned char *b) {
  memset(b, 0, WC_RECEIPT);
  memcpy(b, wc_magic, 8);
  wc_put32(b + 8, 1);
  wc_put32(b + 12, m->count);
  wc_put64(b + 16, m->generation);
  wc_put64(b + 24, m->root_ino);
  memcpy(b + 32, m->uuid, 16);
  for (uint32_t i = 0; i < m->count; i++) {
    unsigned char *s = b + WC_HEAD + i * WC_SLOT_SIZE;
    wc_put32(s, m->slots[i].state);
    wc_put64(s + 8, m->slots[i].bytes);
    wc_put64(s + 16, m->slots[i].dir_ino);
    wc_put64(s + 24, m->slots[i].payload_ino);
    memcpy(s + 32, m->slots[i].id, 16);
  }
  wc_put32(b + 60, wc_crc(b, WC_RECEIPT));
}

static int wc_decode(const unsigned char *b, wc_image *m) {
  unsigned char t[WC_RECEIPT];
  memcpy(t, b, WC_RECEIPT);
  memset(t + 60, 0, 4);
  if (memcmp(b, wc_magic, 8) != 0 || wc_get32(b + 8) != 1 ||
      !wc_zero(b + 48, 12) || wc_get32(b + 60) != wc_crc(t, WC_RECEIPT))
    return -1;
  memset(m, 0, sizeof *m);
  m->count = wc_get32(b + 12);
  m->generation = wc_get64(b + 16);
  m->root_ino = wc_get64(b + 24);
  memcpy(m->uuid, b + 32, 16);
  if (m->count > WC_SLOTS || m->generation == 0 || m->root_ino == 0) return -1;
  for (uint32_t i = 0; i < WC_SLOTS; i++) {
    const unsigned char *s = b + WC_HEAD + i * WC_SLOT_SIZE;
    wc_slot *v = &m->slots[i];
    if (i >= m->count) {
      if (!wc_zero(s, WC_SLOT_SIZE)) return -1;
      continue;
    }
    v->state = wc_get32(s);
    v->bytes = wc_get64(s + 8);
    v->dir_ino = wc_get64(s + 16);
    v->payload_ino = wc_get64(s + 24);
    memcpy(v->id, s + 32, 16);
    if (v->state < EXR_WC_RESERVED || v->state > EXR_WC_CLEANED ||
        !wc_zero(s + 4, 4) || !wc_zero(s + 48, 16))
      return -1;
    if (v->state == EXR_WC_RESERVED
            ? (v->bytes || v->dir_ino || v->payload_ino)
            : (!v->dir_ino || !v->payload_ino))
      return -1;
  }
  return 0;
}

static int wc_sync(int fd) {
#ifdef F_FULLFSYNC
  if (fcntl(fd, F_FULLFSYNC) == 0) return 0;
#endif
  return fsync(fd);
}

static int wc_write_all(int fd, const unsigned char *p, size_t n) {
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

static int wc_private(const struct stat *st, mode_t type) {
  return (st->st_mode & S_IFMT) == type && st->st_uid == geteuid() &&
         (st->st_mode & 077) == 0;
}

static int wc_read_receipt(int dirfd, const char *name, unsigned char *b) {
  struct stat st;
  size_t got = 0;
  unsigned char extra;
  int result = WC_READ_OK;
  int fd = openat(dirfd, name, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
  if (fd < 0) return errno == ENOENT ? WC_READ_MISSING : errno == ELOOP ? WC_READ_BAD : WC_READ_IO;
  if (fstat(fd, &st) != 0) {
    result = WC_READ_IO;
  } else if (!wc_private(&st, S_IFREG) || st.st_nlink != 1 || st.st_size != WC_RECEIPT) {
    result = WC_READ_BAD;
  } else {
    while (got < WC_RECEIPT) {
      ssize_t k = read(fd, b + got, WC_RECEIPT - got);
      if (k < 0 && errno == EINTR) continue;
      if (k <= 0) break;
      got += (size_t)k;
    }
    if (got != WC_RECEIPT || read(fd, &extra, 1) != 0) result = WC_READ_IO;
  }
  close(fd);
  return result;
}

static exr_wc_status wc_write_receipt(int dirfd, const unsigned char *b,
                                      uint32_t slot, uint32_t state) {
  int e, fd = openat(dirfd, wc_next, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
  if (fd < 0) return EXR_WC_IO;
  if (wc_write_all(fd, b, WC_RECEIPT) != 0 || wc_sync(fd) != 0) {
    e = errno;
    close(fd);
    unlinkat(dirfd, wc_next, 0);
    errno = e;
    return EXR_WC_IO;
  }
  if (close(fd) != 0) {
    e = errno;
    unlinkat(dirfd, wc_next, 0);
    errno = e;
    return EXR_WC_IO;
  }
  WC_HOOK("receipt_next_synced", slot, state);
  if (renameat(dirfd, wc_next, dirfd, wc_receipt) != 0) {
    e = errno;
    unlinkat(dirfd, wc_next, 0);
    errno = e;
    return EXR_WC_IO;
  }
  WC_HOOK("receipt_renamed", slot, state);
  if (wc_sync(dirfd) != 0) return EXR_WC_UNCERTAIN;
  WC_HOOK("receipt_committed", slot, state);
  return EXR_WC_OK;
}

/* Any failed receipt write stops further mutation of the root. */
static exr_wc_status wc_commit(exr_wc_root *r, uint32_t slot, const wc_slot *value) {
  unsigned char b[WC_RECEIPT];
  wc_image next = r->m;
  exr_wc_status s;
  if (r->poisoned) return EXR_WC_UNCERTAIN;
  if (value) {
    next.slots[slot] = *value;
    if (slot == next.count) next.count++;
  }
  next.generation++;
  wc_encode(&next, b);
  s = wc_write_receipt(r->dirfd, b, value ? slot : UINT32_MAX, value ? value->state : 0);
  if (s != EXR_WC_OK) r->poisoned = 1;
  if (s != EXR_WC_IO) r->m = next;
  return s;
}

static int wc_leaf(const char *s) {
  size_t i;
  if (!s) return 0;
  for (i = 0; s[i]; i++) {
    unsigned char c = (unsigned char)s[i];
    int ok = (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
             (c >= '0' && c <= '9') || c == '_' || c == '-' || (i > 0 && c == '.');
    if (!ok || i >= 120) return 0;
  }
  return i >= 1;
}

static void wc_hex(const unsigned char *id, char out[33]) {
  static const char d[] = "0123456789abcdef";
  for (int i = 0; i < 16; i++) {
    out[2 * i] = d[id[i] >> 4];
    out[2 * i + 1] = d[id[i] & 15];
  }
  out[32] = 0;
}

static int wc_unhex(const char *s, unsigned char id[16]) {
  for (int i = 0; i < 32; i++) {
    char c = s[i];
    int v = c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : -1;
    if (v < 0) return -1;
    if (i % 2) id[i / 2] = (unsigned char)(id[i / 2] | v);
    else id[i / 2] = (unsigned char)(v << 4);
  }
  return s[32] ? -1 : 0;
}

static void wc_txname(const unsigned char *id, char out[36]) {
  memcpy(out, "tx-", 3);
  wc_hex(id, out + 3);
}

static int wc_open_dir(int parent, const char *name) {
  return openat(parent, name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
}

static exr_wc_root *wc_new_root(void) {
  exr_wc_root *r = calloc(1, sizeof *r);
  if (r) r->dirfd = r->lockfd = -1;
  return r;
}

static void wc_free_root(exr_wc_root *r) {
  if (!r) return;
  if (r->lockfd >= 0) close(r->lockfd);
  if (r->dirfd >= 0) close(r->dirfd);
  free(r);
}

static int wc_registered_dir(const exr_wc_root *r, uint64_t ino) {
  if (ino == r->m.root_ino) return 1;
  for (uint32_t i = 0; i < r->m.count; i++) {
    const wc_slot *v = &r->m.slots[i];
    if (v->state != EXR_WC_RESERVED && v->state != EXR_WC_CLEANED && v->dir_ino == ino) return 1;
  }
  return 0;
}

/* A link failure with one of these errors is known not to have created the
 * destination name, so the slot can safely return to SEALED. */
static int wc_link_definitely_failed(int e) {
  return e == EEXIST || e == EXDEV || e == ENOENT || e == EACCES || e == EPERM ||
         e == EMLINK || e == ENOSPC || e == EDQUOT || e == EROFS ||
         e == ENAMETOOLONG || e == ENOTDIR || e == ELOOP;
}

/* fstatat followed by unlinkat is not an atomic remove-by-inode; safety
 * relies on the root lock and the cooperative namespace contract. */
static int wc_clean_slot(exr_wc_root *r, uint32_t slot, int *err) {
  wc_slot v = r->m.slots[slot];
  char name[36];
  struct stat st;
  int fd;
  *err = 0;
  wc_txname(v.id, name);
  fd = wc_open_dir(r->dirfd, name);
  if (fd < 0) {
    *err = errno;
    if (errno == ELOOP || errno == ENOTDIR) return WC_DENIED;
    if (errno != ENOENT) return WC_PENDING;
    *err = 0;
  } else {
    if (fstat(fd, &st) != 0) {
      *err = errno;
      close(fd);
      return WC_PENDING;
    }
    if (!wc_private(&st, S_IFDIR) || st.st_dev != r->dev || (uint64_t)st.st_ino != v.dir_ino) {
      close(fd);
      return WC_DENIED;
    }
    if (fstatat(fd, wc_payload, &st, AT_SYMLINK_NOFOLLOW) == 0) {
      if (!S_ISREG(st.st_mode) || st.st_dev != r->dev || (uint64_t)st.st_ino != v.payload_ino) {
        close(fd);
        return WC_DENIED;
      }
      if (unlinkat(fd, wc_payload, 0) != 0) {
        *err = errno;
        close(fd);
        return WC_PENDING;
      }
      WC_HOOK("alias_unlinked", slot, v.state);
      if (wc_sync(fd) != 0) {
        *err = errno;
        close(fd);
        return WC_PENDING;
      }
      WC_HOOK("alias_directory_synced", slot, v.state);
    } else if (errno != ENOENT) {
      *err = errno;
      close(fd);
      return WC_PENDING;
    }
    close(fd);
    if (unlinkat(r->dirfd, name, AT_REMOVEDIR) != 0) {
      *err = errno;
      return WC_PENDING;
    }
    WC_HOOK("transaction_removed", slot, v.state);
  }
  if (wc_sync(r->dirfd) != 0) {
    *err = errno;
    return WC_PENDING;
  }
  WC_HOOK("transaction_parent_synced", slot, v.state);
  v.state = EXR_WC_CLEANED;
  if (wc_commit(r, slot, &v) != EXR_WC_OK) {
    *err = errno;
    return WC_UNSURE;
  }
  WC_HOOK("cleaned", slot, EXR_WC_CLEANED);
  return WC_DONE;
}

exr_wc_status exr_wc_create_at(int parent_fd, const char *leaf,
                               exr_wc_root **out, char root_uuid[33]) {
  exr_wc_root *r;
  struct stat st;
  exr_wc_status s = EXR_WC_IO;
  if (out) *out = NULL;
  if (root_uuid) root_uuid[0] = 0;
  if (!out || !root_uuid || parent_fd < 0 || !wc_leaf(leaf)) return EXR_WC_ARGUMENT;
  if (mkdirat(parent_fd, leaf, 0700) != 0) return errno == EEXIST ? EXR_WC_EXISTS : EXR_WC_IO;
  /* A failure after mkdir leaves a directory without a receipt, which
   * open_at refuses; it is never adopted. */
  if (!(r = wc_new_root())) return EXR_WC_IO;
  r->dirfd = wc_open_dir(parent_fd, leaf);
  if (r->dirfd < 0 || fstat(r->dirfd, &st) != 0) goto fail;
  if (!wc_private(&st, S_IFDIR)) {
    s = EXR_WC_REFUSED;
    goto fail;
  }
  r->dev = st.st_dev;
  r->m.root_ino = (uint64_t)st.st_ino;
  r->lockfd = openat(r->dirfd, wc_lock, O_RDWR | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
  if (r->lockfd < 0 || flock(r->lockfd, LOCK_EX | LOCK_NB) != 0) goto fail;
  if (getentropy(r->m.uuid, sizeof r->m.uuid) != 0) goto fail;
  if ((s = wc_commit(r, UINT32_MAX, NULL)) != EXR_WC_OK) goto fail;
  if (wc_sync(parent_fd) != 0) {
    s = EXR_WC_IO;
    goto fail;
  }
  wc_hex(r->m.uuid, root_uuid);
  *out = r;
  return EXR_WC_OK;
fail:
  wc_free_root(r);
  return s;
}

exr_wc_status exr_wc_open_at(int parent_fd, const char *leaf,
                             const char *expected_uuid, exr_wc_root **out) {
  unsigned char want[16], b[WC_RECEIPT];
  wc_image next;
  struct stat st, ls;
  exr_wc_root *r;
  exr_wc_status s = EXR_WC_REFUSED;
  int rc;
  if (out) *out = NULL;
  if (!out || parent_fd < 0 || !wc_leaf(leaf) || !expected_uuid || wc_unhex(expected_uuid, want) != 0)
    return EXR_WC_ARGUMENT;
  if (!(r = wc_new_root())) return EXR_WC_IO;
  r->dirfd = wc_open_dir(parent_fd, leaf);
  if (r->dirfd < 0) {
    s = errno == ELOOP || errno == ENOTDIR ? EXR_WC_REFUSED : EXR_WC_IO;
    goto fail;
  }
  if (fstat(r->dirfd, &st) != 0) {
    s = EXR_WC_IO;
    goto fail;
  }
  if (!wc_private(&st, S_IFDIR)) goto fail;
  r->dev = st.st_dev;
  r->lockfd = openat(r->dirfd, wc_lock, O_RDWR | O_NOFOLLOW | O_CLOEXEC);
  if (r->lockfd < 0) {
    s = errno == ENOENT || errno == ELOOP ? EXR_WC_REFUSED : EXR_WC_IO;
    goto fail;
  }
  if (fstat(r->lockfd, &ls) != 0 || !wc_private(&ls, S_IFREG)) goto fail;
  if (flock(r->lockfd, LOCK_EX | LOCK_NB) != 0) {
    s = errno == EWOULDBLOCK || errno == EAGAIN ? EXR_WC_BUSY : EXR_WC_IO;
    goto fail;
  }
  rc = wc_read_receipt(r->dirfd, wc_receipt, b);
  if (rc != WC_READ_OK) {
    s = rc == WC_READ_IO ? EXR_WC_IO : EXR_WC_REFUSED;
    goto fail;
  }
  if (wc_decode(b, &r->m) != 0 || r->m.root_ino != (uint64_t)st.st_ino ||
      memcmp(r->m.uuid, want, 16) != 0)
    goto fail;
  rc = wc_read_receipt(r->dirfd, wc_next, b);
  if (rc == WC_READ_IO) {
    s = EXR_WC_IO;
    goto fail;
  }
  if (rc != WC_READ_MISSING) {
    /* An uncommitted successor of the valid receipt: its rename never
     * happened, so no later step ran.  Anything else fails closed. */
    if (rc != WC_READ_OK || wc_decode(b, &next) != 0 || next.root_ino != r->m.root_ino ||
        memcmp(next.uuid, r->m.uuid, 16) != 0 || next.generation != r->m.generation + 1)
      goto fail;
    if (unlinkat(r->dirfd, wc_next, 0) != 0 || wc_sync(r->dirfd) != 0) {
      s = EXR_WC_IO;
      goto fail;
    }
  }
  *out = r;
  return EXR_WC_OK;
fail:
  wc_free_root(r);
  return s;
}

exr_wc_status exr_wc_begin(exr_wc_root *r, exr_wc_tx **out, int *borrowed_fd) {
  wc_slot v;
  char name[36];
  struct stat ds, ps, hs;
  exr_wc_tx *tx;
  exr_wc_status s;
  uint32_t slot;
  if (out) *out = NULL;
  if (borrowed_fd) *borrowed_fd = -1;
  if (!r || !out || !borrowed_fd) return EXR_WC_ARGUMENT;
  if (r->poisoned) return EXR_WC_UNCERTAIN;
  if (r->active) return EXR_WC_BUSY;
  if (r->m.count >= WC_SLOTS) return EXR_WC_LIMIT;
  slot = r->m.count;
  memset(&v, 0, sizeof v);
  memset(&ds, 0, sizeof ds);
  memset(&ps, 0, sizeof ps);
  v.state = EXR_WC_RESERVED;
  if (getentropy(v.id, sizeof v.id) != 0) return EXR_WC_IO;
  if ((s = wc_commit(r, slot, &v)) != EXR_WC_OK) return s;
  wc_txname(v.id, name);
  if (mkdirat(r->dirfd, name, 0700) != 0) return EXR_WC_IO;
  WC_HOOK("directory_created", slot, EXR_WC_RESERVED);
  if (!(tx = calloc(1, sizeof *tx))) return EXR_WC_IO;
  tx->root = r;
  tx->slot = slot;
  tx->fd = tx->hold = -1;
  s = EXR_WC_IO;
  tx->dirfd = wc_open_dir(r->dirfd, name);
  if (tx->dirfd < 0 || fstat(tx->dirfd, &ds) != 0 || !wc_private(&ds, S_IFDIR) || ds.st_dev != r->dev)
    goto fail;
  tx->fd = openat(tx->dirfd, wc_payload, O_RDWR | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
  if (tx->fd < 0) goto fail;
  WC_HOOK("payload_created", slot, EXR_WC_RESERVED);
  if (fstat(tx->fd, &ps) != 0 || !wc_private(&ps, S_IFREG) || wc_sync(tx->dirfd) != 0 ||
      wc_sync(r->dirfd) != 0)
    goto fail;
  tx->hold = openat(tx->dirfd, wc_payload, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
  if (tx->hold < 0 || fstat(tx->hold, &hs) != 0 || hs.st_dev != ps.st_dev || hs.st_ino != ps.st_ino)
    goto fail;
  v.state = EXR_WC_OWNED;
  v.dir_ino = (uint64_t)ds.st_ino;
  v.payload_ino = (uint64_t)ps.st_ino;
  if ((s = wc_commit(r, slot, &v)) != EXR_WC_OK) goto fail;
  WC_HOOK("owned", slot, EXR_WC_OWNED);
  r->active = tx;
  *out = tx;
  *borrowed_fd = tx->fd;
  return EXR_WC_OK;
fail:
  if (tx->hold >= 0) close(tx->hold);
  if (tx->fd >= 0) close(tx->fd);
  if (tx->dirfd >= 0) close(tx->dirfd);
  free(tx);
  return s;
}

exr_wc_status exr_wc_seal(exr_wc_tx *tx) {
  struct stat st;
  wc_slot v;
  exr_wc_status s;
  int bad;
  if (!tx) return EXR_WC_ARGUMENT;
  memset(&st, 0, sizeof st);
  v = tx->root->m.slots[tx->slot];
  if (tx->root->poisoned) return EXR_WC_UNCERTAIN;
  if (v.state != EXR_WC_OWNED || tx->fd < 0) return EXR_WC_REFUSED;
  bad = wc_sync(tx->fd) != 0;
  if (!bad) WC_HOOK("payload_synced", tx->slot, EXR_WC_OWNED);
  bad = bad || fstat(tx->fd, &st) != 0 || !wc_private(&st, S_IFREG) || st.st_dev != tx->root->dev ||
        (uint64_t)st.st_ino != v.payload_ino || st.st_nlink != 1;
  /* The borrowed fd is closed whatever the outcome; a failed seal leaves the
   * slot OWNED, which only an explicit abandon can clean. */
  if (close(tx->fd) != 0) bad = 1;
  tx->fd = -1;
  if (bad) return EXR_WC_IO;
  v.state = EXR_WC_SEALED;
  v.bytes = (uint64_t)st.st_size;
  if ((s = wc_commit(tx->root, tx->slot, &v)) != EXR_WC_OK) return s;
  WC_HOOK("sealed", tx->slot, EXR_WC_SEALED);
  return EXR_WC_OK;
}

exr_wc_status exr_wc_publish_at(exr_wc_tx *tx, int destination_fd,
                                const char *leaf, exr_wc_publish_result *res) {
  exr_wc_root *r;
  struct stat ds, ps, ts;
  char name[36];
  wc_slot v;
  exr_wc_status s;
  int e;
  if (res) memset(res, 0, sizeof *res);
  if (!tx || !res || destination_fd < 0 || !wc_leaf(leaf)) return EXR_WC_ARGUMENT;
  r = tx->root;
  v = r->m.slots[tx->slot];
  if (r->poisoned) return EXR_WC_UNCERTAIN;
  if (v.state != EXR_WC_SEALED) return EXR_WC_REFUSED;
  if (fstat(destination_fd, &ds) != 0) {
    res->native_error = errno;
    return EXR_WC_IO;
  }
  if (!S_ISDIR(ds.st_mode)) return EXR_WC_ARGUMENT;
  if (ds.st_dev == r->dev && wc_registered_dir(r, (uint64_t)ds.st_ino)) return EXR_WC_REFUSED;
  if (ds.st_dev != r->dev) {
    res->native_error = EXDEV;
    return EXR_WC_IO;
  }
  wc_txname(v.id, name);
  if (fstat(tx->dirfd, &ts) != 0 || (uint64_t)ts.st_ino != v.dir_ino ||
      fstatat(r->dirfd, name, &ts, AT_SYMLINK_NOFOLLOW) != 0 || !wc_private(&ts, S_IFDIR) ||
      ts.st_dev != r->dev || (uint64_t)ts.st_ino != v.dir_ino)
    return EXR_WC_REFUSED;
  if (fstatat(tx->dirfd, wc_payload, &ps, AT_SYMLINK_NOFOLLOW) != 0) {
    res->native_error = errno;
    return errno == ENOENT ? EXR_WC_REFUSED : EXR_WC_IO;
  }
  if (!wc_private(&ps, S_IFREG) || ps.st_dev != r->dev || (uint64_t)ps.st_ino != v.payload_ino ||
      ps.st_nlink != 1 || (uint64_t)ps.st_size != v.bytes)
    return EXR_WC_REFUSED;
  if (fstatat(destination_fd, leaf, &ts, AT_SYMLINK_NOFOLLOW) == 0) return EXR_WC_EXISTS;
  if (errno != ENOENT) {
    res->native_error = errno;
    return EXR_WC_IO;
  }
  v.state = EXR_WC_PUBLISH_INTENT;
  if ((s = wc_commit(r, tx->slot, &v)) != EXR_WC_OK) {
    res->receipt_uncertain = s == EXR_WC_UNCERTAIN;
    return s;
  }
  WC_HOOK("publish_intent", tx->slot, EXR_WC_PUBLISH_INTENT);
  if (linkat(tx->dirfd, wc_payload, destination_fd, leaf, 0) != 0) {
    e = res->native_error = errno;
    if (!wc_link_definitely_failed(e)) {
      r->poisoned = 1;
      res->cleanup_pending = 1;
      return EXR_WC_UNCERTAIN;
    }
    v.state = EXR_WC_SEALED;
    if (wc_commit(r, tx->slot, &v) != EXR_WC_OK) {
      res->receipt_uncertain = res->cleanup_pending = 1;
      return EXR_WC_UNCERTAIN;
    }
    return e == EEXIST ? EXR_WC_EXISTS : EXR_WC_IO;
  }
  WC_HOOK("linked", tx->slot, EXR_WC_PUBLISH_INTENT);
  res->published = 1;
  if (wc_sync(destination_fd) != 0) {
    res->native_error = errno;
    res->receipt_uncertain = res->cleanup_pending = 1;
    r->poisoned = 1;
    return EXR_WC_OK;
  }
  WC_HOOK("destination_synced", tx->slot, EXR_WC_PUBLISH_INTENT);
  v.state = EXR_WC_PUBLISHED;
  if (wc_commit(r, tx->slot, &v) != EXR_WC_OK) {
    res->native_error = errno;
    res->receipt_uncertain = res->cleanup_pending = 1;
    return EXR_WC_OK;
  }
  WC_HOOK("published", tx->slot, EXR_WC_PUBLISHED);
  return EXR_WC_OK;
}

exr_wc_status exr_wc_cleanup(exr_wc_tx *tx, int abandon_unpublished,
                             exr_wc_cleanup_result *res) {
  uint32_t state;
  int e;
  if (res) memset(res, 0, sizeof *res);
  if (!tx || !res) return EXR_WC_ARGUMENT;
  state = tx->root->m.slots[tx->slot].state;
  if (tx->root->poisoned) {
    res->receipt_uncertain = 1;
    return EXR_WC_UNCERTAIN;
  }
  if (state == EXR_WC_CLEANED) return EXR_WC_OK;
  if (state != EXR_WC_PUBLISHED &&
      !(abandon_unpublished && (state == EXR_WC_OWNED || state == EXR_WC_SEALED)))
    return EXR_WC_REFUSED;
  if (tx->fd >= 0) close(tx->fd);
  if (tx->dirfd >= 0) close(tx->dirfd);
  tx->fd = tx->dirfd = -1;
  switch (wc_clean_slot(tx->root, tx->slot, &e)) {
  case WC_DONE:
    if (tx->hold >= 0) close(tx->hold);
    tx->hold = -1;
    res->removed = 1;
    return EXR_WC_OK;
  case WC_PENDING:
    res->pending = 1;
    res->native_error = e;
    return EXR_WC_IO;
  case WC_DENIED:
    res->native_error = e;
    return EXR_WC_REFUSED;
  default:
    res->removed = res->receipt_uncertain = 1;
    res->native_error = e;
    return EXR_WC_UNCERTAIN;
  }
}

exr_wc_status exr_wc_inspect(exr_wc_root *r, uint32_t slot, exr_wc_info *info) {
  const wc_slot *v;
  if (info) memset(info, 0, sizeof *info);
  if (!r || !info || slot >= r->m.count) return EXR_WC_ARGUMENT;
  v = &r->m.slots[slot];
  info->slot = slot;
  info->state = v->state;
  info->bytes = v->bytes;
  if (v->state != EXR_WC_RESERVED) {
    info->directory_device = info->payload_device = (uint64_t)r->dev;
    info->directory_inode = v->dir_ino;
    info->payload_inode = v->payload_ino;
  }
  wc_hex(v->id, info->transaction_id);
  return EXR_WC_OK;
}

exr_wc_status exr_wc_recover(exr_wc_root *r, uint32_t start, uint32_t maximum,
                             exr_wc_recovery_report *rep) {
  uint32_t end;
  int e;
  if (rep) memset(rep, 0, sizeof *rep);
  if (!r || !rep || maximum < 1 || maximum > WC_SLOTS || start > r->m.count) return EXR_WC_ARGUMENT;
  rep->total_slots = r->m.count;
  rep->next_slot = start;
  if (r->active) return EXR_WC_BUSY;
  if (r->poisoned) {
    rep->receipt_uncertain = 1;
    return EXR_WC_UNCERTAIN;
  }
  end = start + maximum > r->m.count ? r->m.count : start + maximum;
  for (uint32_t i = start; i < end; i++) {
    uint32_t state = r->m.slots[i].state;
    rep->inspected++;
    rep->next_slot = i + 1;
    if (state == EXR_WC_CLEANED) continue;
    if (state != EXR_WC_PUBLISHED) {
      rep->pending++;
      continue;
    }
    switch (wc_clean_slot(r, i, &e)) {
    case WC_DONE:
      rep->cleaned++;
      break;
    case WC_PENDING:
      rep->pending++;
      rep->native_error = e;
      break;
    case WC_DENIED:
      rep->refused++;
      if (e) rep->native_error = e;
      break;
    default:
      rep->receipt_uncertain = 1;
      rep->native_error = e;
      return EXR_WC_UNCERTAIN;
    }
  }
  return EXR_WC_OK;
}

exr_wc_status exr_wc_tx_close(exr_wc_tx **p) {
  exr_wc_tx *tx;
  if (!p || !*p) return EXR_WC_OK;
  tx = *p;
  if (tx->hold >= 0) close(tx->hold);
  if (tx->fd >= 0) close(tx->fd);
  if (tx->dirfd >= 0) close(tx->dirfd);
  if (tx->root->active == tx) tx->root->active = NULL;
  free(tx);
  *p = NULL;
  return EXR_WC_OK;
}

exr_wc_status exr_wc_close(exr_wc_root **p) {
  if (!p || !*p) return EXR_WC_OK;
  if ((*p)->active) return EXR_WC_BUSY;
  wc_free_root(*p);
  *p = NULL;
  return EXR_WC_OK;
}
