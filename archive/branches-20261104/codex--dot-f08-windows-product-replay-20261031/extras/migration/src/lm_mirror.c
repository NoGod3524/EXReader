/* SPDX-License-Identifier: MIT */
#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#endif
#ifdef __APPLE__
#define _DARWIN_C_SOURCE
#endif
#include "lm_mirror.h"
#include <errno.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#include <io.h>
#include <fcntl.h>
#else
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#endif

#define INTENT_MAX 4096u
#define INTENT_FORMAT "exreader-mirror-intent"

static int mirror_error(lm_err *e, const char *code, const char *message) {
  lm_err_set(e, code, "%s", message);
  return 0;
}
static int hex_string(const char *p, size_t n) {
  size_t i;
  if (!p || strlen(p) != n) return 0;
  for (i = 0; i < n; i++)
    if (!((p[i] >= '0' && p[i] <= '9') || (p[i] >= 'a' && p[i] <= 'f'))) return 0;
  return 1;
}
static int valid_stage_token(const char *p) {
  size_t i, dash = 0, n = strlen(p);
  if (!n || n >= 24) return 0;
  for (i = 0; i < n; i++) {
    if (p[i] == '-') { if (!i || i + 1 == n || dash++) return 0; }
    else if (!((p[i] >= '0' && p[i] <= '9') || (p[i] >= 'a' && p[i] <= 'f'))) return 0;
  }
  return dash == 1;
}
#ifdef _WIN32
static wchar_t *mirror_widen(const char *p) {
  int n = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, p, -1, NULL, 0);
  wchar_t *w;
  if (n <= 0) return NULL;
  w = malloc((size_t)n * sizeof(*w));
  if (w && !MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, p, -1, w, n)) { free(w); return NULL; }
  return w;
}
#endif

/* No fopen on an unchecked special entry: a FIFO must never block migration.
   Identity checks detect many races, but do not replace the namespace lease. */
int lm_mirror_snapshot(const char *path, int hash_content, uint64_t max_bytes,
                       lm_mirror_file *out, char **data, size_t *size, lm_err *e) {
  FILE *f = NULL;
  unsigned char buffer[16384];
  size_t n;
  uint64_t total = 0;
  lm_sha sha;
  lm_sb bytes;
#ifdef _WIN32
  wchar_t *w = mirror_widen(path);
  HANDLE h;
  BY_HANDLE_FILE_INFORMATION first, last;
  DWORD error;
  int fd;
#else
  int fd;
  struct stat first, last;
#endif
  memset(out, 0, sizeof(*out));
  if (data) *data = NULL;
  if (size) *size = 0;
  lm_sb_init(&bytes);
#ifdef _WIN32
  if (!w) return mirror_error(e, "mirror-path", "invalid UTF-8 path");
  /* Do not request backup semantics: privileged runner/host tokens must not
     bypass a mirror or preimage's read ACL. Directories fail closed at open. */
  h = CreateFileW(w, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                  NULL, OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT, NULL);
  error = h == INVALID_HANDLE_VALUE ? GetLastError() : ERROR_SUCCESS;
  free(w);
  if (h == INVALID_HANDLE_VALUE) {
    if (error == ERROR_FILE_NOT_FOUND) return 1;
    return mirror_error(e, "mirror-unreadable", "cannot inspect path; it is not known absent");
  }
  if (GetFileType(h) != FILE_TYPE_DISK || !GetFileInformationByHandle(h, &first) ||
      (first.dwFileAttributes & (FILE_ATTRIBUTE_DIRECTORY | FILE_ATTRIBUTE_REPARSE_POINT))) {
    CloseHandle(h); return mirror_error(e, "mirror-special", "path is not a regular non-reparse file");
  }
  snprintf(out->identity, sizeof(out->identity), "%016llx%016llx",
           (unsigned long long)first.dwVolumeSerialNumber,
           ((unsigned long long)first.nFileIndexHigh << 32) | first.nFileIndexLow);
  out->size = ((uint64_t)first.nFileSizeHigh << 32) | first.nFileSizeLow;
  if (!hash_content) { out->present = 1; CloseHandle(h); return 1; }
  fd = _open_osfhandle((intptr_t)h, _O_RDONLY | _O_BINARY);
  if (fd < 0) { CloseHandle(h); return mirror_error(e, "mirror-unreadable", "cannot read regular file"); }
  f = _fdopen(fd, "rb");
  if (!f) { _close(fd); return mirror_error(e, "mirror-unreadable", "cannot read regular file"); }
#else
  if (!hash_content) {
    /* SQLite's POSIX locks belong to the process, not one descriptor. Opening
       and then closing the target here would silently drop its active SQLite
       owner locks. Identity-only inspection must not open the database at all.
       lstat preserves final-component no-symlink validation; SDK open still
       enforces access rights under the existing stable-namespace contract. */
    if (lstat(path, &first)) {
      if (errno == ENOENT) return 1;
      return mirror_error(e, "mirror-unreadable", "cannot inspect path; it is not known absent");
    }
    if (!S_ISREG(first.st_mode) || first.st_size < 0)
      return mirror_error(e, "mirror-special", "path is not a regular non-symlink file");
    snprintf(out->identity, sizeof(out->identity), "%016llx%016llx",
             (unsigned long long)first.st_dev, (unsigned long long)first.st_ino);
    out->size = (uint64_t)first.st_size;
    out->present = 1;
    return 1;
  }
  fd = open(path, O_RDONLY | O_NOFOLLOW | O_NONBLOCK);
  if (fd < 0) {
    if (errno == ENOENT) return 1;
    return mirror_error(e, "mirror-unreadable", "cannot inspect path; it is not known absent");
  }
  if (fstat(fd, &first) || !S_ISREG(first.st_mode) || first.st_size < 0) {
    close(fd); return mirror_error(e, "mirror-special", "path is not a regular non-symlink file");
  }
  snprintf(out->identity, sizeof(out->identity), "%016llx%016llx",
           (unsigned long long)first.st_dev, (unsigned long long)first.st_ino);
  out->size = (uint64_t)first.st_size;
  f = fdopen(fd, "rb");
  if (!f) { close(fd); return mirror_error(e, "mirror-unreadable", "cannot read regular file"); }
#endif
  if (out->size > max_bytes) {
    fclose(f); return mirror_error(e, "mirror-size", "file exceeds the bounded mirror/journal read");
  }
  lm_sha_init(&sha);
  while ((n = fread(buffer, 1, sizeof(buffer), f)) != 0) {
    if (total > max_bytes || n > max_bytes - total) {
      fclose(f); lm_sb_free(&bytes); return mirror_error(e, "mirror-size", "file grew beyond the read bound");
    }
    lm_sha_add(&sha, buffer, n);
    if (data) lm_sb_add(&bytes, (const char *)buffer, n);
    total += n;
  }
  if (ferror(f) || bytes.oom) {
    fclose(f); lm_sb_free(&bytes); return mirror_error(e, "mirror-unreadable", "cannot read a complete mirror/journal");
  }
#ifdef _WIN32
  if (!GetFileInformationByHandle((HANDLE)_get_osfhandle(_fileno(f)), &last) ||
      first.nFileSizeHigh != last.nFileSizeHigh || first.nFileSizeLow != last.nFileSizeLow ||
      first.ftLastWriteTime.dwHighDateTime != last.ftLastWriteTime.dwHighDateTime ||
      first.ftLastWriteTime.dwLowDateTime != last.ftLastWriteTime.dwLowDateTime || total != out->size) {
#else
  if (fstat(fileno(f), &last) || first.st_size != last.st_size ||
      first.st_mtime != last.st_mtime || total != out->size) {
#endif
    fclose(f); lm_sb_free(&bytes); return mirror_error(e, "mirror-changed", "file changed while being read");
  }
  if (fclose(f)) { lm_sb_free(&bytes); return mirror_error(e, "mirror-unreadable", "cannot close mirror/journal reader"); }
  if (data && !bytes.p) {
    bytes.p = calloc(1, 1);
    if (!bytes.p) return mirror_error(e, "mirror-memory", "cannot allocate empty file snapshot");
  }
  lm_sha_hex(&sha, out->sha);
  out->present = 1;
  if (size) *size = (size_t)total;
  if (data) *data = bytes.p;
  else lm_sb_free(&bytes);
  return 1;
}

int lm_mirror_same_file(const lm_mirror_file *a, const lm_mirror_file *b) {
  return a->present == b->present && (!a->present ||
         (a->identity[0] && b->identity[0] && !strcmp(a->identity, b->identity)));
}
int lm_mirror_same_bytes(const lm_mirror_file *a, const lm_mirror_file *b) {
  return a->present == b->present && (!a->present ||
         (a->sha[0] && b->sha[0] && a->size == b->size && !strcmp(a->sha, b->sha)));
}
static int same_baseline(const lm_mirror_file *a, const lm_mirror_file *b) {
  return lm_mirror_same_file(a, b) && lm_mirror_same_bytes(a, b);
}
int lm_mirror_copy_new(const char *source, const lm_mirror_file *expected,
                       const char *destination, lm_mirror_file *written,
                       int *owned, lm_err *e) {
  lm_mirror_file observed;
#ifdef _WIN32
  wchar_t *from=NULL,*to=NULL;HANDLE copy;int ok;
#else
  char *data = NULL;size_t size = 0;
  FILE *f;int ok;
#endif
  *owned = 0;
#ifdef _WIN32
  if(!lm_mirror_snapshot(source,1,LM_MIRROR_LEDGER_MAX,&observed,NULL,NULL,e)) return 0;
  if(!observed.present || !same_baseline(expected,&observed))
    return mirror_error(e,"mirror-changed","external mirror changed before its byte preimage was captured");
  from=mirror_widen(source);to=mirror_widen(destination);
  ok=from && to && CopyFileW(from,to,TRUE);
  free(from);
  if(!ok) { free(to);return mirror_error(e,"mirror-preimage","cannot exclusively copy external mirror and its security attributes"); }
  *owned=1;
  copy=CreateFileW(to,GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_DELETE,NULL,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,NULL);
  free(to);
  if(copy==INVALID_HANDLE_VALUE) return mirror_error(e,"mirror-preimage","cannot open owned mirror preimage for flush");
  ok=FlushFileBuffers(copy)!=0;CloseHandle(copy);
  if(!ok) return mirror_error(e,"mirror-preimage","cannot flush complete external mirror preimage");
#else
  if(!lm_mirror_snapshot(source,1,LM_MIRROR_LEDGER_MAX,&observed,&data,&size,e)) return 0;
  if(!observed.present || !same_baseline(expected,&observed)) {
    free(data);return mirror_error(e,"mirror-changed","external mirror changed before its byte preimage was captured");
  }
  f=lm_fopen(destination,"wbx");
  if(!f) { free(data);return mirror_error(e,"mirror-preimage","cannot exclusively create external mirror preimage"); }
  *owned=1;
  /* A retained byte preimage must not expose a formerly private mirror. */
  ok=fchmod(fileno(f),S_IRUSR|S_IWUSR)==0 && fwrite(data,1,size,f)==size && lm_sync(f);
  if(fclose(f)) ok=0;
  free(data);
  if(!ok) return mirror_error(e,"mirror-preimage","cannot flush complete external mirror preimage");
#endif
  if(!lm_mirror_snapshot(destination,1,LM_MIRROR_LEDGER_MAX,written,NULL,NULL,e)) return 0;
  if(!lm_mirror_same_bytes(expected,written)) return mirror_error(e,"mirror-preimage","external mirror preimage bytes do not match baseline");
  return 1;
}
int lm_mirror_planned_file(const lm_mirror_intent *p, const lm_mirror_file *file) {
  return (p->version==2 || p->version==3) && same_baseline(file,&p->mirror_after);
}
int lm_mirror_original_file(const lm_mirror_intent *p, const lm_mirror_file *file) {
  return same_baseline(file,&p->mirror_before) ||
         ((p->version==2 || p->version==3) && p->mirror_preimage.present && same_baseline(file,&p->mirror_preimage));
}
int lm_mirror_begin(lm_mirror_intent *intent, int target_was_present,
                    const char *stage_token,
                    const lm_mirror_file *owner, int before_found,
                    const void *before, size_t before_size,
                    const lm_mirror_file *mirror, lm_err *e) {
  memset(intent, 0, sizeof(*intent));
  intent->version=1;
  if (!owner->present || !hex_string(owner->identity, 32))
    return mirror_error(e, "mirror-owner", "cannot bind mirror intent to a regular library owner");
  if (!target_was_present && (!stage_token || !valid_stage_token(stage_token)))
    return mirror_error(e, "mirror-stage", "new-target intent requires a safe private-stage token");
  if (before_found) lm_sha_bytes(before, before_size, intent->before_sha);
  if (before_found && mirror->present &&
      (mirror->size != before_size || strcmp(mirror->sha, intent->before_sha)))
    return mirror_error(e, "mirror-diverged", "external mirror differs from the authoritative internal ledger");
  intent->target_was_present = target_was_present != 0;
  strcpy(intent->target_identity, owner->identity);
  if (!target_was_present) strcpy(intent->stage_token, stage_token);
  intent->before_found = before_found != 0;
  intent->mirror_before = *mirror;
  return 1;
}
void lm_mirror_set_after(lm_mirror_intent *intent, const void *data, size_t size) {
  lm_sha_bytes(data, size, intent->after_sha);
}

static int intent_valid(const lm_mirror_intent *p) {
  int common=hex_string(p->target_identity, 32) && hex_string(p->after_sha, 64) &&
         (p->target_was_present ? !p->stage_token[0] : valid_stage_token(p->stage_token)) &&
         (p->before_found ? hex_string(p->before_sha, 64) : !p->before_sha[0]) &&
         (p->mirror_before.present ?
          (hex_string(p->mirror_before.identity, 32) && hex_string(p->mirror_before.sha, 64) &&
           p->mirror_before.size <= LM_MIRROR_LEDGER_MAX) :
          (!p->mirror_before.identity[0] && !p->mirror_before.sha[0] && !p->mirror_before.size));
  if(!common) return 0;
  if(p->version==1) return !p->artifact_token[0] && !p->mirror_after.present && !p->mirror_preimage.present;
  return (p->version==2 || p->version==3) && p->target_was_present && valid_stage_token(p->artifact_token) &&
         p->mirror_after.present && hex_string(p->mirror_after.identity,32) &&
         !strcmp(p->mirror_after.sha,p->after_sha) && p->mirror_after.size<=LM_MIRROR_LEDGER_MAX &&
         p->mirror_preimage.present==p->mirror_before.present &&
         (p->mirror_preimage.present ?
          (hex_string(p->mirror_preimage.identity,32) && lm_mirror_same_bytes(&p->mirror_preimage,&p->mirror_before)) :
          (!p->mirror_preimage.identity[0] && !p->mirror_preimage.sha[0] && !p->mirror_preimage.size));
}
int lm_mirror_intent_write(const char *path, const lm_mirror_intent *p,
                           lm_mirror_file *written, lm_err *e) {
  lm_sb b;
  FILE *f;
  int ok;
  if (!intent_valid(p)) return mirror_error(e, "mirror-intent", "cannot persist an invalid mirror intent");
  lm_sb_init(&b);
  lm_sb_fmt(&b, "{\"format\":\"%s\",\"version\":%d,\"target_was_present\":%s,"
            "\"target_identity\":\"%s\",\"stage_token\":\"%s\",\"before_found\":%s,\"before_sha\":\"%s\","
            "\"after_sha\":\"%s\",\"mirror_present\":%s,\"mirror_identity\":\"%s\","
            "\"mirror_sha\":\"%s\",\"mirror_size\":%llu", INTENT_FORMAT,p->version,
            p->target_was_present ? "true" : "false", p->target_identity, p->stage_token,
            p->before_found ? "true" : "false", p->before_sha, p->after_sha,
            p->mirror_before.present ? "true" : "false", p->mirror_before.identity,
            p->mirror_before.sha, (unsigned long long)p->mirror_before.size);
  if(p->version==2 || p->version==3) lm_sb_fmt(&b,",\"artifact_token\":\"%s\",\"published_identity\":\"%s\",\"published_size\":%llu,\"preimage_identity\":\"%s\"",
      p->artifact_token,p->mirror_after.identity,(unsigned long long)p->mirror_after.size,p->mirror_preimage.identity);
  lm_sb_str(&b,"}\n");
  if (b.oom || b.n > INTENT_MAX) { lm_sb_free(&b); return mirror_error(e, "mirror-intent", "cannot encode bounded mirror intent"); }
  f = lm_fopen(path, "wbx");
  if (!f) { lm_sb_free(&b); return mirror_error(e, "mirror-pending", "pending path already exists or cannot be created"); }
  ok = fwrite(b.p, 1, b.n, f) == b.n && lm_sync(f);
  if (fclose(f)) ok = 0;
  lm_sb_free(&b);
  if (!ok) return mirror_error(e, "mirror-intent-write", "intent write failed; partial file retained, do not commit");
  return lm_mirror_snapshot(path, 1, INTENT_MAX, written, NULL, NULL, e);
}

static int get_bool(const jv *v, const char *key, int *out) {
  const jv *p = lm_get(v, key);
  if (!p || p->t != J_BOOL) return 0;
  *out = p->b;
  return 1;
}
static int get_hex(const jv *v, const char *key, char *out, size_t len, int allow_empty) {
  const jv *p = lm_get(v, key);
  if (!p || p->t != J_STR || p->n != strlen(p->s)) return 0;
  if (allow_empty && !p->n) { out[0] = 0; return 1; }
  if (!hex_string(p->s, len)) return 0;
  memcpy(out, p->s, len + 1);
  return 1;
}
int lm_mirror_intent_read(const char *path, lm_mirror_intent *p,
                          lm_mirror_file *snapshot, lm_err *e) {
  char *data = NULL, parse_error[128] = {0};
  size_t size = 0;
  uint64_t version;
  jv *root;
  const jv *format;
  const jv *stage;
  int ok;
  memset(p, 0, sizeof(*p));
  if (!lm_mirror_snapshot(path, 1, INTENT_MAX, snapshot, &data, &size, e)) return 0;
  if (!snapshot->present) return 1;
  root = lm_json_parse(data, size, parse_error, sizeof(parse_error));
  free(data);
  format = lm_get(root, "format");
  stage = lm_get(root, "stage_token");
  if (stage && stage->t == J_STR && stage->n < sizeof(p->stage_token) && stage->n == strlen(stage->s))
    memcpy(p->stage_token, stage->s, stage->n + 1);
  ok = root && root->t == J_OBJ && format && format->t == J_STR &&
       stage && stage->t == J_STR && stage->n < sizeof(p->stage_token) && stage->n == strlen(stage->s) &&
       format->n == strlen(INTENT_FORMAT) && !memcmp(format->s, INTENT_FORMAT, format->n) &&
       lm_json_uint(lm_get(root, "version"), &version) && (version == 1 || version == 2 || version == 3) &&
       root->n==(version==1?12u:16u) &&
       get_bool(root, "target_was_present", &p->target_was_present) &&
       get_hex(root, "target_identity", p->target_identity, 32, 0) &&
       get_bool(root, "before_found", &p->before_found) &&
       get_hex(root, "before_sha", p->before_sha, 64, !p->before_found) &&
       get_hex(root, "after_sha", p->after_sha, 64, 0) &&
       get_bool(root, "mirror_present", &p->mirror_before.present) &&
       get_hex(root, "mirror_identity", p->mirror_before.identity, 32, !p->mirror_before.present) &&
       get_hex(root, "mirror_sha", p->mirror_before.sha, 64, !p->mirror_before.present) &&
       lm_json_uint(lm_get(root, "mirror_size"), &p->mirror_before.size);
  if(ok) {
    p->version=(int)version;
    if(version==2 || version==3) {
      const jv *token=lm_get(root,"artifact_token");
      ok=token && token->t==J_STR && token->n<sizeof(p->artifact_token) && token->n==strlen(token->s) && valid_stage_token(token->s) &&
         get_hex(root,"published_identity",p->mirror_after.identity,32,0) &&
         lm_json_uint(lm_get(root,"published_size"),&p->mirror_after.size) &&
         get_hex(root,"preimage_identity",p->mirror_preimage.identity,32,!p->mirror_before.present);
      if(ok) {
        strcpy(p->artifact_token,token->s);p->mirror_after.present=1;strcpy(p->mirror_after.sha,p->after_sha);
        p->mirror_preimage.present=p->mirror_before.present;p->mirror_preimage.size=p->mirror_before.size;
        strcpy(p->mirror_preimage.sha,p->mirror_before.sha);
      }
    }
    if(ok) ok=intent_valid(p);
  }
  lm_json_free(root);
  if (!ok) return mirror_error(e, "mirror-intent-invalid", "pending intent is malformed, unsupported, or incomplete; retained");
  return 1;
}
int lm_mirror_intent_remove(const char *path, const lm_mirror_file *expected, lm_err *e) {
  lm_mirror_file now;
  if (!expected->present || !lm_mirror_snapshot(path, 1, INTENT_MAX, &now, NULL, NULL, e)) return 0;
  if (!same_baseline(expected, &now)) return mirror_error(e, "mirror-intent-changed", "pending intent changed; retained");
  if (!lm_remove(path)) return mirror_error(e, "mirror-pending", "mirror converged but pending intent could not be removed");
  return 1;
}

lm_mirror_action lm_mirror_plan(const lm_mirror_intent *p,
                                const lm_mirror_file *target,
                                const lm_mirror_file *unpublished_stage,
                                int current_found, const void *current, size_t current_size,
                                const lm_mirror_file *mirror, lm_err *e) {
  char digest[65];
  /* v3 restart recovery has no complete baseline verifier. Never let the
     legacy ledger-only classifier accidentally authorize its retirement. */
  if (!intent_valid(p) || p->version==3) goto conflict;
  if (!target->present) {
    if (!p->target_was_present && !current_found && unpublished_stage && unpublished_stage->present &&
        !strcmp(unpublished_stage->identity, p->target_identity) && same_baseline(mirror, &p->mirror_before))
      return LM_MIRROR_ABANDONED_NEW; /* retain stage; never publish it */
    goto conflict;
  }
  if (strcmp(target->identity, p->target_identity)) goto conflict;
  if (!current_found) {
    if (p->target_was_present && !p->before_found) {
      if(lm_mirror_original_file(p,mirror)) return LM_MIRROR_NO_LEDGER;
      if(p->version==2 && (!mirror->present || lm_mirror_planned_file(p,mirror))) return LM_MIRROR_RESTORE_BEFORE;
    }
    goto conflict;
  }
  lm_sha_bytes(current, current_size, digest);
  if (strcmp(digest, p->after_sha) && (!p->before_found || strcmp(digest, p->before_sha))) goto conflict;
  if (mirror->present && mirror->size == current_size && !strcmp(mirror->sha, digest))
    return LM_MIRROR_ALREADY_EQUAL;
  /* The original observed mirror is the only replacement authority. A missing
     mirror may also be rebuilt. Third-state or replaced-identical files fail. */
  if (!mirror->present || lm_mirror_original_file(p,mirror) || lm_mirror_planned_file(p,mirror)) return LM_MIRROR_EXPORT_CURRENT;
conflict:
  mirror_error(e, "mirror-recovery-conflict", "target, ledger, or external mirror is outside the pending intent; retained");
  return LM_MIRROR_CONFLICT;
}
