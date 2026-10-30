/* SPDX-License-Identifier: MIT
 * Reference filesystem provider: real snapshot/import/verify/discard.
 * It never publishes, renames over, or deletes anything it did not create. */
#ifdef _WIN32
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0A00
#endif
#include <windows.h>
#include <winioctl.h>
#else
#define _POSIX_C_SOURCE 200809L
#include <dirent.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#include <errno.h>
#endif
#include "exr_wc_provider.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAXDEPTH 8
struct wc_fs {
  char source[1024], parent[1024], stage[1100];
  char staged_id[EXR_WC_ID_BYTES];
  char (*made)[EXR_WC_PATH_MAX + 1]; /* created paths relative to stage; "" = stage itself */
  unsigned char *made_dir; size_t made_n, made_cap;
  int created;
  wc_step (*d_admit)(void *, const wc_binding *, char *);
  wc_step (*d_publish)(void *, const char *, wc_pub *);
  wc_step (*d_recover)(void *, const char *, wc_pub *);
  wc_step (*d_release)(void *, const char *);
  void *d_ctx;
};

/* ---- portable primitives ---- */
#ifdef _WIN32
static int wide(const char *u, WCHAR *w, int cap) { return MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, u, -1, w, cap) > 0; }
static int identity_of(const char *path, int dir, char out[49]) {
  WCHAR w[2048]; HANDLE h; FILE_ID_INFO info; int i;
  if (!wide(path, w, 2048)) return 0;
  h = CreateFileW(w, 0, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, NULL, OPEN_EXISTING,
                  FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT, NULL);
  if (h == INVALID_HANDLE_VALUE) return 0;
  (void)dir;
  if (!GetFileInformationByHandleEx(h, FileIdInfo, &info, sizeof info)) { CloseHandle(h); return 0; }
  CloseHandle(h);
  sprintf(out, "%016llx", (unsigned long long)info.VolumeSerialNumber);
  for (i = 0; i < 16; i++) sprintf(out + 16 + 2*i, "%02x", info.FileId.Identifier[i]);
  return 1;
}
static FILE *fopen_u(const char *path, const char *mode) {
  WCHAR w[2048], m[8]; int i; if (!wide(path, w, 2048)) return NULL;
  for (i = 0; mode[i] && i < 7; i++) m[i] = (WCHAR)mode[i]; m[i] = 0; return _wfopen(w, m);
}
static int make_dir(const char *p) { WCHAR w[2048]; return wide(p, w, 2048) && CreateDirectoryW(w, NULL); }
static int rm_dir(const char *p) { WCHAR w[2048]; return wide(p, w, 2048) && RemoveDirectoryW(w); }
static int rm_file(const char *p) { WCHAR w[2048]; return wide(p, w, 2048) && DeleteFileW(w); }
/* callback(name, is_dir, is_regular): 0 continues */
static int list_dir(const char *dir, int (*cb)(void *, const char *, int, int), void *u) {
  WCHAR w[2100]; WIN32_FIND_DATAW d; HANDLE h; char name[1024];
  if (!wide(dir, w, 2048)) return 1;
  wcscat(w, L"\\*"); h = FindFirstFileW(w, &d); if (h == INVALID_HANDLE_VALUE) return 1;
  do {
    int isdir, reg;
    if (!wcscmp(d.cFileName, L".") || !wcscmp(d.cFileName, L"..")) continue;
    if (!WideCharToMultiByte(CP_UTF8, 0, d.cFileName, -1, name, sizeof name, NULL, NULL)) { FindClose(h); return 1; }
    isdir = (d.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) != 0;
    reg = !isdir && !(d.dwFileAttributes & (FILE_ATTRIBUTE_REPARSE_POINT | FILE_ATTRIBUTE_DEVICE));
    if (d.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT) { isdir = 0; reg = 0; }
    if (cb(u, name, isdir, reg)) { FindClose(h); return 1; }
  } while (FindNextFileW(h, &d));
  FindClose(h); return 0;
}
#define SEP "\\"
#else
static int identity_of(const char *path, int dir, char out[49]) {
  struct stat st; (void)dir;
  if (lstat(path, &st)) return 0;
  sprintf(out, "%016llx%032llx", (unsigned long long)st.st_dev, (unsigned long long)st.st_ino); return 1;
}
static FILE *fopen_u(const char *path, const char *mode) { return fopen(path, mode); }
static int make_dir(const char *p) { return mkdir(p, 0700) == 0; }
static int rm_dir(const char *p) { return rmdir(p) == 0; }
static int rm_file(const char *p) { return unlink(p) == 0; }
static int list_dir(const char *dir, int (*cb)(void *, const char *, int, int), void *u) {
  DIR *d = opendir(dir); struct dirent *e; char full[2200];
  if (!d) return 1;
  while ((e = readdir(d))) {
    struct stat st; int isdir, reg;
    if (!strcmp(e->d_name, ".") || !strcmp(e->d_name, "..")) continue;
    snprintf(full, sizeof full, "%s/%s", dir, e->d_name);
    if (lstat(full, &st)) { closedir(d); return 1; }
    isdir = S_ISDIR(st.st_mode); reg = S_ISREG(st.st_mode);
    if (cb(u, e->d_name, isdir, reg)) { closedir(d); return 1; }
  }
  closedir(d); return 0;
}
#define SEP "/"
#endif

/* ---- SHA256 over a stream ---- */
static int hash_file(const char *path, uint64_t *size, char sha[65], FILE *copy_to) {
  FILE *f = fopen_u(path, "rb"); unsigned char *buf; size_t n; uint64_t total = 0;
  /* whole content is hashed incrementally via chunked concatenation of partial digests is not
     possible; read into memory up to a bound and hash once. */
  size_t cap = 1u << 20, len = 0;
  if (!f) return 0;
  buf = malloc(cap); if (!buf) { fclose(f); return 0; }
  while ((n = fread(buf + len, 1, cap - len, f)) > 0) {
    len += n; total += n;
    if (len == cap) {
      unsigned char *nb; if (cap >= (256u << 20)) { free(buf); fclose(f); return 0; }
      cap *= 2; nb = realloc(buf, cap); if (!nb) { free(buf); fclose(f); return 0; } buf = nb;
    }
  }
  if (ferror(f)) { free(buf); fclose(f); return 0; }
  fclose(f);
  if (copy_to && len && fwrite(buf, 1, len, copy_to) != len) { free(buf); return 0; }
  wc_sha256_hex(buf, len, sha); free(buf); *size = total; return 1;
}

/* ---- snapshot walk ---- */
typedef struct { struct wc_fs *fs; wc_record *rows; size_t cap, n; char rel[EXR_WC_PATH_MAX]; int depth, failed; } walk;
static int cmp_names(const void *a, const void *b) { return strcmp((const char *)a, (const char *)b); }
typedef struct { char (*names)[256]; unsigned char *dirs; size_t n, cap; int bad; } names;
static int collect(void *u, const char *name, int isdir, int reg) {
  names *s = u;
  if ((!isdir && !reg) || strlen(name) >= 256) { s->bad = 1; return 1; }
  if (s->n == s->cap) {
    size_t nc = s->cap ? s->cap * 2 : 32; char (*a)[256] = realloc(s->names, nc * 256); unsigned char *d = realloc(s->dirs, nc);
    if (!a || !d) { if (a) s->names = a; s->bad = 1; return 1; }
    s->names = a; s->dirs = d; s->cap = nc;
  }
  strcpy(s->names[s->n], name); s->dirs[s->n++] = (unsigned char)isdir; return 0;
}
static int walk_dir(walk *w, const char *abs, size_t relen) {
  names s = {0}; size_t i, *order; int ok = 1;
  if (w->depth > MAXDEPTH) return 0;
  if (list_dir(abs, collect, &s) || s.bad) { free(s.names); free(s.dirs); return 0; }
  order = malloc((s.n + 1) * sizeof *order); if (!order) { free(s.names); free(s.dirs); return 0; }
  for (i = 0; i < s.n; i++) order[i] = i;
  /* sort by name (stable insertion sort; sets are small per directory) */
  for (i = 1; i < s.n; i++) { size_t j = i, v = order[i]; while (j && strcmp(s.names[order[j-1]], s.names[v]) > 0) { order[j] = order[j-1]; j--; } order[j] = v; }
  (void)cmp_names;
  for (i = 0; ok && i < s.n; i++) {
    const char *nm = s.names[order[i]]; char child[2200]; size_t nl = strlen(nm);
    if (relen + nl + 2 >= EXR_WC_PATH_MAX) { ok = 0; break; }
    snprintf(child, sizeof child, "%s" SEP "%s", abs, nm);
    memcpy(w->rel + relen, nm, nl + 1);
    if (s.dirs[order[i]]) {
      w->rel[relen + nl] = '/'; w->rel[relen + nl + 1] = 0; w->depth++;
      ok = walk_dir(w, child, relen + nl + 1); w->depth--;
      w->rel[relen] = 0;
    } else {
      wc_record *r;
      if (w->n >= w->cap) { ok = 0; break; }
      r = &w->rows[w->n];
      if (!identity_of(child, 0, r->id) || !hash_file(child, &r->size, r->sha, NULL)) { ok = 0; break; }
      strcpy(r->path, w->rel); w->n++;
      w->rel[relen] = 0;
    }
  }
  free(order); free(s.names); free(s.dirs); return ok;
}
static int cmp_rec(const void *a, const void *b) { return strcmp(((const wc_record *)a)->path, ((const wc_record *)b)->path); }

static wc_step fs_snapshot(void *ctx, wc_record *rows, size_t cap, size_t *count) {
  struct wc_fs *fs = ctx; walk w; memset(&w, 0, sizeof w); w.fs = fs; w.rows = rows; w.cap = cap;
  memset(rows, 0, cap * sizeof *rows);
  if (!walk_dir(&w, fs->source, 0) || !w.n) return WC_STEP_FAILED;
  qsort(rows, w.n, sizeof *rows, cmp_rec); *count = w.n; return WC_STEP_OK;
}

/* ---- staging ---- */
static int note(struct wc_fs *fs, const char *rel, int isdir) {
  if (fs->made_n == fs->made_cap) {
    size_t nc = fs->made_cap ? fs->made_cap * 2 : 64; void *a = realloc(fs->made, nc * sizeof *fs->made); void *d;
    if (!a) return 0; fs->made = a; d = realloc(fs->made_dir, nc); if (!d) return 0; fs->made_dir = d; fs->made_cap = nc;
  }
  snprintf(fs->made[fs->made_n], EXR_WC_PATH_MAX + 1, "%s", rel); fs->made_dir[fs->made_n++] = (unsigned char)isdir; return 1;
}
static void abs_in_stage(struct wc_fs *fs, const char *rel, char *out, size_t cap) {
  char tmp[EXR_WC_PATH_MAX + 1]; size_t i;
  snprintf(tmp, sizeof tmp, "%s", rel);
#ifdef _WIN32
  for (i = 0; tmp[i]; i++) if (tmp[i] == '/') tmp[i] = '\\';
#else
  (void)i;
#endif
  snprintf(out, cap, "%s%s%s", fs->stage, *tmp ? SEP : "", tmp);
}
static wc_step fs_import(void *ctx, const wc_binding *b, const wc_record *rows, size_t n, char staged[49]) {
  struct wc_fs *fs = ctx; size_t i; char srcp[2200], dst[2300];
  snprintf(fs->stage, sizeof fs->stage, "%s" SEP ".exwc-%s-%s", fs->parent, b->run, b->attempt);
  if (!make_dir(fs->stage)) return WC_STEP_FAILED;           /* exclusive: existing stage is never adopted */
  fs->created = 1; if (!note(fs, "", 1)) return WC_STEP_UNCERTAIN;
  if (!identity_of(fs->stage, 1, fs->staged_id)) return WC_STEP_UNCERTAIN;
  memcpy(staged, fs->staged_id, 49);
  for (i = 0; i < n; i++) {
    const char *rel = rows[i].path; const char *slash; char dirrel[EXR_WC_PATH_MAX + 1]; FILE *out; uint64_t size; char sha[65], dirabs[2300];
    for (slash = strchr(rel, '/'); slash; slash = strchr(slash + 1, '/')) {
      size_t len = (size_t)(slash - rel); memcpy(dirrel, rel, len); dirrel[len] = 0;
      abs_in_stage(fs, dirrel, dirabs, sizeof dirabs);
      { size_t k; int seen = 0; for (k = 0; k < fs->made_n; k++) if (fs->made_dir[k] && !strcmp(fs->made[k], dirrel)) { seen = 1; break; }
        if (!seen) { if (!make_dir(dirabs)) return WC_STEP_FAILED; if (!note(fs, dirrel, 1)) return WC_STEP_FAILED; } }
    }
    snprintf(srcp, sizeof srcp, "%s" SEP "%s", fs->source, rel);
#ifdef _WIN32
    { char *c; for (c = srcp + strlen(fs->source); *c; c++) if (*c == '/') *c = '\\'; }
#endif
    abs_in_stage(fs, rel, dst, sizeof dst);
    out = fopen_u(dst, "wbx");                                /* exclusive create */
    if (!out) return WC_STEP_FAILED;
    if (!note(fs, rel, 0)) { fclose(out); return WC_STEP_FAILED; }
    if (!hash_file(srcp, &size, sha, out)) { fclose(out); return WC_STEP_FAILED; }
    if (fclose(out) != 0) return WC_STEP_FAILED;
    if (size != rows[i].size || strcmp(sha, rows[i].sha)) return WC_STEP_FAILED;   /* source changed mid-snapshot */
  }
  return WC_STEP_OK;
}
static wc_step fs_verify(void *ctx, const char staged[49], const wc_record *rows, size_t n) {
  struct wc_fs *fs = ctx; char id[49]; walk w; wc_record *got; size_t i; wc_step res = WC_STEP_FAILED;
  if (!fs->created || strcmp(staged, fs->staged_id) || !identity_of(fs->stage, 1, id) || strcmp(id, fs->staged_id)) return WC_STEP_FAILED;
  got = calloc(n + 1, sizeof *got); if (!got) return WC_STEP_UNCERTAIN;
  memset(&w, 0, sizeof w); w.fs = fs; w.rows = got; w.cap = n;
  if (walk_dir(&w, fs->stage, 0) && w.n == n) {
    qsort(got, w.n, sizeof *got, cmp_rec); res = WC_STEP_OK;
    for (i = 0; i < n; i++) if (strcmp(got[i].path, rows[i].path) || got[i].size != rows[i].size || strcmp(got[i].sha, rows[i].sha)) { res = WC_STEP_FAILED; break; }
  }
  free(got); return res;
}
static wc_step fs_discard(void *ctx, const char *staged) {
  struct wc_fs *fs = ctx; size_t i; char id[49], p[2300]; int ok = 1;
  if (!fs->created || strcmp(staged, fs->staged_id) || !identity_of(fs->stage, 1, id) || strcmp(id, fs->staged_id)) return WC_STEP_UNCERTAIN;
  for (i = fs->made_n; i-- > 0;) {                            /* only what this provider created, in reverse */
    if (fs->made_dir[i] == 2) continue;                       /* already removed */
    abs_in_stage(fs, fs->made[i], p, sizeof p);
    if (fs->made_dir[i] ? !rm_dir(p) : !rm_file(p)) ok = 0; else fs->made_dir[i] = 2;
  }
  if (!ok) return WC_STEP_UNCERTAIN;
  fs->made_n = 0; fs->created = 0; return WC_STEP_OK;
}

/* ---- delegates (C01 admission, native publisher) ---- */
static wc_step w_admit(void *c, const wc_binding *b, char l[49]) { struct wc_fs *f = c; return f->d_admit(f->d_ctx, b, l); }
static wc_step w_publish(void *c, const char *s, wc_pub *o) { struct wc_fs *f = c; return f->d_publish(f->d_ctx, s, o); }
static wc_step w_recover(void *c, const char *s, wc_pub *o) { struct wc_fs *f = c; return f->d_recover(f->d_ctx, s, o); }
static wc_step w_release(void *c, const char *l) { struct wc_fs *f = c; return f->d_release(f->d_ctx, l); }

int wc_fs_open(const char *source_dir, const char *parent, const char *identity_sha, wc_fs **out, wc_provider *p) {
  struct wc_fs *fs;
  if (!source_dir || !parent || !identity_sha || !out || !p || strlen(source_dir) >= 1024 || strlen(parent) >= 1024) return 0;
  fs = calloc(1, sizeof *fs); if (!fs) return 0;
  strcpy(fs->source, source_dir); strcpy(fs->parent, parent);
  memset(p, 0, sizeof *p);
  p->abi = EXR_WC_ABI; p->identity_sha = identity_sha; p->context = fs;
  p->snapshot = fs_snapshot; p->import = fs_import; p->verify = fs_verify; p->discard = fs_discard;
  *out = fs; return 1;
}
void wc_fs_attach(wc_provider *p, wc_step (*admit)(void *, const wc_binding *, char *),
                  wc_step (*publish)(void *, const char *, wc_pub *), wc_step (*recover)(void *, const char *, wc_pub *),
                  wc_step (*release)(void *, const char *), void *context) {
  struct wc_fs *fs = p->context; fs->d_admit = admit; fs->d_publish = publish; fs->d_recover = recover; fs->d_release = release; fs->d_ctx = context;
  p->admit = admit ? w_admit : NULL; p->publish = publish ? w_publish : NULL;
  p->recover = recover ? w_recover : NULL; p->release = release ? w_release : NULL;
}
const char *wc_fs_staging_path(const wc_fs *fs) { return fs && fs->created ? fs->stage : NULL; }
void wc_fs_close(wc_fs *fs) { if (fs) { free(fs->made); free(fs->made_dir); free(fs); } }
