/* SPDX-License-Identifier: MIT */
#include "lm_win_lease.h"
#include <stdio.h>
#include <stdlib.h>
#include <wchar.h>
#include <string.h>
#define LEASE_LOCK 4096ull
#define INIT_LOCK 4097ull
#define HDR_MAGIC "EXRLEASE1\n"
#define HDR_ID 10
#define GEN_OFFSET 64
#define PENDING_OFFSET 72
#define LEASE_SIZE 80
#define PATH_MAX_W 3000
struct lm_wl_lease {
  HANDLE dir, file;
  lm_wl_mode mode;
  uint64_t generation, pending;
  DWORD volume, index_high, index_low;
  unsigned char header[GEN_OFFSET];
};
static lm_wl_status fail(lm_wl_error *e, lm_wl_status s, DWORD native, const char *reason) {
  if (e) { e->native = native; e->reason = reason; }
  return s;
}
static int valid_identity(const char *id) {
  size_t i;
  if (!id) return 0;
  for (i = 0; i < 48; i++) if (!((id[i] >= '0' && id[i] <= '9') || (id[i] >= 'a' && id[i] <= 'f'))) return 0;
  return id[48] == 0;
}
static int lock_range(HANDLE h, ULONGLONG off, int exclusive, DWORD timeout, DWORD *native) {
  ULONGLONG start = GetTickCount64();
  for (;;) {
    OVERLAPPED o; memset(&o, 0, sizeof o);
    o.Offset = (DWORD)off; o.OffsetHigh = (DWORD)(off >> 32);
    if (LockFileEx(h, LOCKFILE_FAIL_IMMEDIATELY | (exclusive ? LOCKFILE_EXCLUSIVE_LOCK : 0), 0, 1, 0, &o)) return 1;
    *native = GetLastError();
    if (*native != ERROR_LOCK_VIOLATION) return 0;
    if (GetTickCount64() - start >= timeout) return 0;
    Sleep(5);
  }
}
static void unlock_range(HANDLE h, ULONGLONG off) {
  OVERLAPPED o; memset(&o, 0, sizeof o);
  o.Offset = (DWORD)off; o.OffsetHigh = (DWORD)(off >> 32);
  UnlockFileEx(h, 0, 1, 0, &o);
}
static int pread_exact(HANDLE h, DWORD off, void *buf, DWORD n) {
  OVERLAPPED o; DWORD got = 0; memset(&o, 0, sizeof o); o.Offset = off;
  return ReadFile(h, buf, n, &got, &o) && got == n;
}
static int pwrite_exact(HANDLE h, DWORD off, const void *buf, DWORD n) {
  OVERLAPPED o; DWORD got = 0; memset(&o, 0, sizeof o); o.Offset = off;
  return WriteFile(h, buf, n, &got, &o) && got == n;
}
static int final_path(HANDLE h, WCHAR *out, DWORD cap) {
  DWORD n = GetFinalPathNameByHandleW(h, out, cap, FILE_NAME_NORMALIZED | VOLUME_NAME_DOS);
  return n > 0 && n < cap;
}
/* Fail closed unless the handle is one regular, singly-linked, non-reparse file. */
static lm_wl_status file_state(HANDLE h, BY_HANDLE_FILE_INFORMATION *i, lm_wl_error *e) {
  if (GetFileType(h) != FILE_TYPE_DISK) return fail(e, LM_WL_REFUSED, 0, "lease is not a disk file");
  if (!GetFileInformationByHandle(h, i)) return fail(e, LM_WL_NATIVE, GetLastError(), "GetFileInformationByHandle");
  if (i->dwFileAttributes & (FILE_ATTRIBUTE_DIRECTORY | FILE_ATTRIBUTE_REPARSE_POINT)) return fail(e, LM_WL_REFUSED, 0, "lease is directory or reparse point");
  if (i->nNumberOfLinks != 1) return fail(e, LM_WL_REFUSED, 0, "lease has extra hard links");
  if (i->nFileSizeHigh != 0 || i->nFileSizeLow != LEASE_SIZE) return fail(e, LM_WL_REFUSED, 0, "lease size mismatch");
  return LM_WL_OK;
}
lm_wl_status lm_wl_acquire(const WCHAR *dirpath, const char identity[49], lm_wl_mode mode,
                           DWORD timeout_ms, lm_wl_lease **out, lm_wl_error *e) {
  lm_wl_lease *l; WCHAR dirfinal[PATH_MAX_W], filefinal[PATH_MAX_W], path[PATH_MAX_W + 64], leaf[64];
  BY_HANDLE_FILE_INFORMATION dinfo, finfo; LARGE_INTEGER size; DWORD native = 0; size_t n, i; lm_wl_status s;
  unsigned char hdr[LEASE_SIZE], got[LEASE_SIZE];
  if (out) *out = NULL;
  if (!out || !dirpath || (mode != LM_WL_SHARED && mode != LM_WL_EXCLUSIVE)) return fail(e, LM_WL_INVALID, 0, "bad argument");
  if (!valid_identity(identity)) return fail(e, LM_WL_INVALID, 0, "identity must be 48 lowercase hex");
  n = wcslen(dirpath);
  if (n == 0 || n >= PATH_MAX_W) return fail(e, LM_WL_INVALID, 0, "bad lease directory");
  l = (lm_wl_lease *)calloc(1, sizeof *l);
  if (!l) return fail(e, LM_WL_NATIVE, ERROR_OUTOFMEMORY, "allocation");
  l->mode = mode; l->dir = l->file = INVALID_HANDLE_VALUE;
  l->dir = CreateFileW(dirpath, FILE_READ_ATTRIBUTES | SYNCHRONIZE, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL,
                       OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT, NULL);
  if (l->dir == INVALID_HANDLE_VALUE) { s = fail(e, LM_WL_NATIVE, GetLastError(), "open lease directory"); goto bad; }
  if (!GetFileInformationByHandle(l->dir, &dinfo)) { s = fail(e, LM_WL_NATIVE, GetLastError(), "directory info"); goto bad; }
  if (!(dinfo.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) || (dinfo.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT)) { s = fail(e, LM_WL_REFUSED, 0, "lease directory is reparse or not a directory"); goto bad; }
  if (!final_path(l->dir, dirfinal, PATH_MAX_W)) { s = fail(e, LM_WL_NATIVE, GetLastError(), "directory final path"); goto bad; }
  for (i = 0; i < 48; i++) leaf[i] = (WCHAR)identity[i];
  memcpy(leaf + 48, L".lease", 7 * sizeof(WCHAR));
  if (swprintf_s(path, PATH_MAX_W + 64, L"%ls\\%ls", dirpath, leaf) < 0) { s = fail(e, LM_WL_INVALID, 0, "path"); goto bad; }
  l->file = CreateFileW(path, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL,
                        OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OPEN_REPARSE_POINT, NULL);
  if (l->file == INVALID_HANDLE_VALUE) { s = fail(e, LM_WL_NATIVE, GetLastError(), "open lease file"); goto bad; }
  /* Opened handle must live directly in the pinned directory. */
  if (!final_path(l->file, filefinal, PATH_MAX_W)) { s = fail(e, LM_WL_NATIVE, GetLastError(), "file final path"); goto bad; }
  n = wcslen(dirfinal);
  if (_wcsnicmp(filefinal, dirfinal, n) != 0 || filefinal[n] != L'\\' || _wcsicmp(filefinal + n + 1, leaf) != 0) { s = fail(e, LM_WL_REFUSED, 0, "lease file escaped pinned directory"); goto bad; }
  memcpy(hdr, HDR_MAGIC, HDR_ID); memcpy(hdr + HDR_ID, identity, 48); hdr[HDR_ID + 48] = '\n';
  memset(hdr + HDR_ID + 49, 0, LEASE_SIZE - (HDR_ID + 49));
  memcpy(l->header, hdr, sizeof l->header); /* whole 64-byte region, padding included */
  /* Serialise first-time initialisation of the file against other processes. */
  if (!lock_range(l->file, INIT_LOCK, 1, timeout_ms ? timeout_ms : 1000, &native)) { s = fail(e, native == ERROR_LOCK_VIOLATION ? LM_WL_BUSY : LM_WL_NATIVE, native, "init lock"); goto bad; }
  if (!GetFileSizeEx(l->file, &size)) { native = GetLastError(); unlock_range(l->file, INIT_LOCK); s = fail(e, LM_WL_NATIVE, native, "size"); goto bad; }
  if (size.QuadPart == 0 && !pwrite_exact(l->file, 0, hdr, LEASE_SIZE)) { native = GetLastError(); unlock_range(l->file, INIT_LOCK); s = fail(e, LM_WL_NATIVE, native, "init write"); goto bad; }
  if (size.QuadPart == 0 && !FlushFileBuffers(l->file)) { native = GetLastError(); unlock_range(l->file, INIT_LOCK); s = fail(e, LM_WL_NATIVE, native, "init flush"); goto bad; }
  unlock_range(l->file, INIT_LOCK);
  if ((s = file_state(l->file, &finfo, e)) != LM_WL_OK) goto bad;
  if (!pread_exact(l->file, 0, got, LEASE_SIZE)) { s = fail(e, LM_WL_NATIVE, GetLastError(), "read header"); goto bad; }
  if (memcmp(got, hdr, GEN_OFFSET) != 0) { s = fail(e, LM_WL_REFUSED, 0, "lease header is not bound to this identity"); goto bad; }
  l->volume = finfo.dwVolumeSerialNumber; l->index_high = finfo.nFileIndexHigh; l->index_low = finfo.nFileIndexLow;
  if (!lock_range(l->file, LEASE_LOCK, mode == LM_WL_EXCLUSIVE, timeout_ms, &native)) { s = fail(e, native == ERROR_LOCK_VIOLATION ? LM_WL_BUSY : LM_WL_NATIVE, native, "lease lock"); goto bad; }
  if (!pread_exact(l->file, GEN_OFFSET, &l->generation, sizeof l->generation) ||
      !pread_exact(l->file, PENDING_OFFSET, &l->pending, sizeof l->pending)) { native = GetLastError(); unlock_range(l->file, LEASE_LOCK); s = fail(e, LM_WL_NATIVE, native, "read generation"); goto bad; }
  if (l->pending > 1) { unlock_range(l->file, LEASE_LOCK); s = fail(e, LM_WL_REFUSED, 0, "corrupt pending marker"); goto bad; }
  if (l->pending && mode == LM_WL_SHARED) { unlock_range(l->file, LEASE_LOCK); s = fail(e, LM_WL_STALE, 0, "unacknowledged publication intent"); goto bad; }
  *out = l;
  return LM_WL_OK;
bad:
  if (l->file != INVALID_HANDLE_VALUE) CloseHandle(l->file);
  if (l->dir != INVALID_HANDLE_VALUE) CloseHandle(l->dir);
  free(l);
  return s;
}
lm_wl_status lm_wl_check(lm_wl_lease *l, lm_wl_error *e) {
  BY_HANDLE_FILE_INFORMATION i; unsigned char got[LEASE_SIZE]; lm_wl_status s;
  if (!l) return fail(e, LM_WL_INVALID, 0, "null lease");
  if ((s = file_state(l->file, &i, e)) != LM_WL_OK) return s == LM_WL_NATIVE ? LM_WL_LOST : s;
  if (i.dwVolumeSerialNumber != l->volume || i.nFileIndexHigh != l->index_high || i.nFileIndexLow != l->index_low) return fail(e, LM_WL_LOST, 0, "lease file identity changed");
  if (!pread_exact(l->file, 0, got, LEASE_SIZE)) return fail(e, LM_WL_LOST, GetLastError(), "read header");
  if (memcmp(got, l->header, sizeof l->header) != 0) return fail(e, LM_WL_REFUSED, 0, "header changed");
  return LM_WL_OK;
}
uint64_t lm_wl_generation(const lm_wl_lease *l) { return l ? l->generation : 0; }
lm_wl_status lm_wl_require_generation(const lm_wl_lease *l, uint64_t admitted) {
  return l && l->generation == admitted ? LM_WL_OK : LM_WL_STALE;
}
static lm_wl_status persist(lm_wl_lease *l, DWORD off, uint64_t v, lm_wl_error *e) {
  if (!pwrite_exact(l->file, off, &v, sizeof v) || !FlushFileBuffers(l->file)) return fail(e, LM_WL_NATIVE, GetLastError(), "persist");
  return LM_WL_OK;
}
int lm_wl_pending(const lm_wl_lease *l) { return l && l->pending != 0; }
lm_wl_status lm_wl_exclusive_begin(lm_wl_lease *l, lm_wl_error *e) {
  lm_wl_status s;
  if (!l || l->mode != LM_WL_EXCLUSIVE) return fail(e, LM_WL_INVALID, 0, "exclusive lease required");
  if ((s = lm_wl_check(l, e)) != LM_WL_OK) return s;
  if (l->pending) return fail(e, LM_WL_REFUSED, 0, "intent already pending; commit after re-qualification");
  if ((s = persist(l, PENDING_OFFSET, 1, e)) != LM_WL_OK) return s;
  l->pending = 1;
  return LM_WL_OK;
}
lm_wl_status lm_wl_exclusive_commit(lm_wl_lease *l, uint64_t *g, lm_wl_error *e) {
  lm_wl_status s;
  if (!l || l->mode != LM_WL_EXCLUSIVE) return fail(e, LM_WL_INVALID, 0, "exclusive lease required");
  if ((s = lm_wl_check(l, e)) != LM_WL_OK) return s;
  if (!l->pending) return fail(e, LM_WL_REFUSED, 0, "no pending intent");
  if (l->generation == UINT64_MAX) return fail(e, LM_WL_REFUSED, 0, "generation exhausted");
  if ((s = persist(l, GEN_OFFSET, l->generation + 1, e)) != LM_WL_OK) return s;
  l->generation++;
  if ((s = persist(l, PENDING_OFFSET, 0, e)) != LM_WL_OK) return s;
  l->pending = 0;
  if (g) *g = l->generation;
  return LM_WL_OK;
}void lm_wl_release(lm_wl_lease *l) {
  if (!l) return;
  unlock_range(l->file, LEASE_LOCK);
  CloseHandle(l->file); CloseHandle(l->dir); free(l);
}
