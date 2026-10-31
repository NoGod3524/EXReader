/* SPDX-License-Identifier: MIT */
/* Included after the host UTF-8 input helpers. All library owners use one
   fixed OS Context scope; migration packages cannot select this authority. */
#include <exr_pc02_sdk.h>
#include <errno.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#define ANDROID_C02_AUTHORITY "no_backup/c02-admission"
typedef struct {
  exr_library *library;
  pc02_lease *lease;
  size_t sources;
  int closed, events;
  pc02_identity target;
} android_library_owner;
typedef struct { exr_source source; android_library_owner *owner; } android_source_owner;

static void admission_error(JNIEnv *env, const char *message) {
  jclass type;
  if ((*env)->ExceptionCheck(env)) return;
  type = (*env)->FindClass(env, "org/exreader/host/NativeAdmission$Required");
  if (type) { (*env)->ThrowNew(env, type, message); (*env)->DeleteLocalRef(env, type); }
}

static int admission_context(int fd, jlong device, jlong inode) {
  struct stat st;
  return fd >= 0 && !fstat(fd, &st) && S_ISDIR(st.st_mode) &&
    st.st_uid == geteuid() && (uint64_t)st.st_dev == (uint64_t)device &&
    (uint64_t)st.st_ino == (uint64_t)inode;
}

static int admission_events(int context) {
#ifdef READER_C02_TEST
  struct stat st;
  int fd = openat(context, "c02-native-events.log",
                  O_WRONLY | O_APPEND | O_CREAT | O_CLOEXEC | O_NOFOLLOW, 0600);
  if (fd >= 0 && (fstat(fd, &st) || !S_ISREG(st.st_mode) ||
      st.st_uid != geteuid() || st.st_nlink != 1 || (st.st_mode & 0777) != 0600)) {
    close(fd); fd = -1;
  }
  return fd;
#else
  (void)context;
  return -1;
#endif
}

static void admission_event(int fd, const char *name, pc02_identity target) {
#ifdef READER_C02_TEST
  struct timespec now = {0};
  char line[256]; int n;
  if (fd < 0) return;
  clock_gettime(CLOCK_MONOTONIC, &now);
  n = snprintf(line, sizeof(line), "%lld.%09ld pid=%ld uid=%ld event=%s dev=%llu ino=%llu\n",
      (long long)now.tv_sec, now.tv_nsec, (long)getpid(), (long)geteuid(), name,
      (unsigned long long)target.device, (unsigned long long)target.inode);
  if (n > 0 && (size_t)n < sizeof(line)) {
    ssize_t wrote;
    do { wrote = write(fd, line, (size_t)n); } while (wrote < 0 && errno == EINTR);
    if (wrote == n) fsync(fd);
  }
#else
  (void)fd; (void)name; (void)target;
#endif
}

/* Only explicit enrollment may tighten verified app-owned directories. The
   system's /data ancestors are never opened for mutation. */
static int admission_private_directory(int fd) {
  struct stat st;
  if (fstat(fd, &st) || !S_ISDIR(st.st_mode) || st.st_uid != geteuid() ||
      (st.st_mode & 07000) || (st.st_mode & 0700) != 0700) return 0;
  if ((st.st_mode & 0022) && fchmod(fd, (st.st_mode & 0777) & ~0022)) return 0;
  return !fstat(fd, &st) && st.st_uid == geteuid() && !(st.st_mode & 0022);
}

static int admission_directories(int anchor, const char *relative, int parents_only) {
  char *copy = copy_string(relative), *part, *slash;
  int fd = fcntl(anchor, F_DUPFD_CLOEXEC, 0), next = -1, ok = 0;
  if (!copy || fd < 0 || !relative[0] || relative[0] == '/') goto done;
  part = copy;
  for (;;) {
    slash = strchr(part, '/');
    if (slash) *slash = 0;
    if (!part[0] || !strcmp(part, ".") || !strcmp(part, "..")) goto done;
    if (!slash && parents_only) { ok = 1; break; }
    next = openat(fd, part, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (next < 0 && errno == ENOENT) {
      if (mkdirat(fd, part, 0700) && errno != EEXIST) goto done;
      next = openat(fd, part, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    }
    if (next < 0 || !admission_private_directory(next)) goto done;
    close(fd); fd = next; next = -1;
    if (!slash) { ok = 1; break; }
    part = slash + 1;
  }
done:
  if (next >= 0) close(next);
  if (fd >= 0) close(fd);
  free(copy);
  return ok;
}

static pc02_scope *admission_scope(JNIEnv *env, jint fd, jlong device, jlong inode) {
  pc02_scope *scope = NULL;
  pc02_identity expected = {(uint64_t)device, (uint64_t)inode};
  if (!admission_context(fd, device, inode) || !pc02_scope_create(fd, &expected, &scope))
    admission_error(env, "Application storage is unsafe or changed");
  return scope;
}

static void admission_owner_release(android_library_owner *owner) {
  if (!owner || !owner->closed || owner->sources) return;
  /* Failure retains the owner and lock; close must never manufacture CLEAN. */
  if (!pc02_close(owner->lease)) return;
  admission_event(owner->events, "lease_close", owner->target);
  if (owner->events >= 0) close(owner->events);
  free(owner);
}

JNIEXPORT jlong JNICALL Java_org_exreader_host_NativeAdmission_nativeOpen(
    JNIEnv *env, jclass type, jint fd, jlong device, jlong inode, jstring relative) {
  pc02_scope *scope = NULL;
  android_library_owner *owner = NULL;
  char *path = input_string(env, relative);
  const char *actual;
  exr_error error = {0}; exr_status status;
  struct stat st;
  int target = -1;
  (void)type;
  if (!path || !(scope = admission_scope(env, fd, device, inode))) goto fail;
  owner = calloc(1, sizeof(*owner));
  if (!owner) { throw_status(env, EXR_MEMORY, NULL, "Cannot allocate library owner"); goto fail; }
  owner->events = admission_events(fd);
  if (!pc02_open_in(scope, ANDROID_C02_AUTHORITY, path, PC02_SHARED, NULL, NULL, &owner->lease) ||
      !(actual = pc02_library_path(owner->lease))) {
    admission_event(owner->events, "admission_refused", owner->target);
    admission_error(env, "Library requires explicit creation, verification, or recovery");
    goto fail;
  }
  target = open(actual, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
  if (target < 0 || fstat(target, &st)) { admission_error(env, "Library identity is unavailable"); goto fail; }
  owner->target.device = (uint64_t)st.st_dev; owner->target.inode = (uint64_t)st.st_ino;
  close(target); target = -1;
  admission_event(owner->events, "shared_acquired", owner->target);
  admission_event(owner->events, "sdk_open", owner->target);
  status = exr_library_open(actual, &owner->library, &error);
  if (status != EXR_OK || !pc02_check(owner->lease)) {
    if (status != EXR_OK) throw_status(env, status, &error, "Cannot open the library");
    else admission_error(env, "Library identity changed during SDK open");
    goto fail;
  }
  pc02_scope_close(scope); free(path);
  return (jlong)(intptr_t)owner;
fail:
  if (target >= 0) close(target);
  if (owner) {
    exr_library_close(owner->library);
    if (owner->lease) pc02_close(owner->lease);
    if (owner->events >= 0) close(owner->events);
    free(owner);
  }
  if (scope) pc02_scope_close(scope);
  free(path);
  return 0;
}

JNIEXPORT void JNICALL Java_org_exreader_host_NativeAdmission_nativeEnroll(
    JNIEnv *env, jclass type, jint fd, jlong device, jlong inode,
    jstring relative, jint operation) {
  pc02_scope *scope = NULL;
  pc02_sdk_proof proof = {0};
  char *path = input_string(env, relative);
  int ok = 0;
  (void)type;
  if (!path || operation < 1 || operation > 3) goto done;
  if (!admission_context(fd, device, inode)) goto done;
  if (operation != 3 && (!admission_private_directory(fd) ||
      !admission_directories(fd, "no_backup", 0) ||
      !admission_directories(fd, path, 1))) goto done;
  scope = admission_scope(env, fd, device, inode);
  if (!scope) goto done;
  if (operation == 3) ok = pc02_sdk_recover_enrollment_in(scope, ANDROID_C02_AUTHORITY, path, &proof);
  else ok = pc02_sdk_enroll_in(scope, ANDROID_C02_AUTHORITY, path, operation == 1, &proof);
done:
  if (scope) pc02_scope_close(scope);
  free(path);
  if (!ok) admission_error(env, "Library verification failed; retained recovery evidence was preserved");
}

JNIEXPORT void JNICALL Java_org_exreader_host_NativeAdmission_nativeEvent(
    JNIEnv *env, jclass type, jint context, jstring event) {
  char *name = input_string(env, event);
  int fd = admission_events(context);
  pc02_identity empty = {0, 0};
  (void)type;
  if (name && strlen(name) < 48 && strspn(name, "abcdefghijklmnopqrstuvwxyz_") == strlen(name))
    admission_event(fd, name, empty);
  if (fd >= 0) close(fd);
  free(name);
}
