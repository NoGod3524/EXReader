/* SPDX-License-Identifier: MIT
   Installed integration sample: a JNI bridge for a host whose SDK owner is ONE dedicated thread.
   Compile it into the host's own shared library and call every function from that thread only. */
#include <exr_android_import_entry.h>
#include <exr_pc02_sdk.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#include <jni.h>
#include <pthread.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
  exr_library *library;
  pc02_lease *admission;
  pthread_t owner;
  exr_error error;
} bridge;

static int on_owner(bridge *b) {
  return b && b->library && pthread_equal(b->owner, pthread_self()) && pc02_check(b->admission);
}

#define SAMPLE_LIBRARY "files/library.db"
#define SAMPLE_AUTHORITY "no_backup/c02-admission"
static pc02_scope *context_scope(int fd, jlong device, jlong inode) {
  struct stat st; pc02_scope *scope = NULL;
  pc02_identity expected = {(uint64_t)device, (uint64_t)inode};
  if (fd < 0 || fstat(fd, &st) || !S_ISDIR(st.st_mode) || st.st_uid != geteuid() ||
      expected.device != (uint64_t)st.st_dev || expected.inode != (uint64_t)st.st_ino) return NULL;
  return pc02_scope_create(fd, &expected, &scope) ? scope : NULL;
}
/* Explicit action only. OS Context creates these app-owned directories; no
   system ancestor, package path, authority tail or unknown root is repaired. */
static int private_directory(int fd) {
  struct stat st;
  if (fd < 0 || fstat(fd, &st) || !S_ISDIR(st.st_mode) || st.st_uid != geteuid() ||
      (st.st_mode & 07000) || (st.st_mode & 0700) != 0700) return 0;
  return !(st.st_mode & 0022) || !fchmod(fd, (st.st_mode & 0777) & ~0022);
}
JNIEXPORT jboolean JNICALL Java_org_exreader_importentry_sample_NativeBridge_nativeInitialize(
    JNIEnv *env, jclass cls, jint fd, jlong device, jlong inode, jint operation) {
  pc02_scope *scope = NULL; pc02_sdk_proof proof = {0}; struct stat st;
  int files = -1, backup = -1, ok = 0; (void)env; (void)cls;
  if (operation < 1 || operation > 3 || fstat(fd, &st) ||
      (uint64_t)st.st_dev != (uint64_t)device || (uint64_t)st.st_ino != (uint64_t)inode) goto done;
  if (operation != 3) {
    if (!private_directory(fd)) goto done;
    files = openat(fd, "files", O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    backup = openat(fd, "no_backup", O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (!private_directory(files) || !private_directory(backup)) goto done;
  }
  if (!(scope = context_scope(fd, device, inode))) goto done;
  if (operation == 3) ok = pc02_sdk_recover_enrollment_in(scope, SAMPLE_AUTHORITY, SAMPLE_LIBRARY, &proof);
  else ok = pc02_sdk_enroll_in(scope, SAMPLE_AUTHORITY, SAMPLE_LIBRARY, operation == 1, &proof);
done:
  if (scope) pc02_scope_close(scope);
  if (files >= 0) close(files);
  if (backup >= 0) close(backup);
  return ok ? JNI_TRUE : JNI_FALSE;
}




JNIEXPORT jlong JNICALL Java_org_exreader_importentry_sample_NativeBridge_nativeOpen(
    JNIEnv *env, jclass cls, jint fd, jlong device, jlong inode) {
  pc02_scope *scope = context_scope(fd, device, inode);
  bridge *b = calloc(1, sizeof(*b)); const char *actual = NULL;
  (void)env; (void)cls;
  if (!scope || !b) goto fail;
  b->owner = pthread_self();
  if (!pc02_open_in(scope, SAMPLE_AUTHORITY, SAMPLE_LIBRARY, PC02_SHARED, NULL, NULL, &b->admission) ||
      !(actual = pc02_library_path(b->admission)) ||
      exr_library_open(actual, &b->library, &b->error) != EXR_OK || !pc02_check(b->admission)) goto fail;
  pc02_scope_close(scope);
  return (jlong)(intptr_t)b;
fail:
  if (b) {
    exr_library_close(b->library);
    if (b->admission) pc02_close(b->admission);
    free(b);
  }
  if (scope) pc02_scope_close(scope);
  return 0;
}

/* Returns {status, bookId, created}. status is an exr_status; a call from a non-owner thread is refused. */
JNIEXPORT jlongArray JNICALL Java_org_exreader_importentry_sample_NativeBridge_commit(JNIEnv *env, jclass cls,
    jlong handle, jstring path, jint format, jstring title, jlong size) {
  bridge *b = (bridge *)(intptr_t)handle;
  jlong out[3] = {EXR_ARGUMENT, 0, 0};
  jlongArray array = (*env)->NewLongArray(env, 3);
  (void)cls;
  if (!array) return NULL;
  if (on_owner(b) && path && size > 0) {
    const char *p = (*env)->GetStringUTFChars(env, path, NULL);
    const char *t = title ? (*env)->GetStringUTFChars(env, title, NULL) : NULL;
    exr_android_import_request request;
    exr_sideload_result result;
    memset(&request, 0, sizeof(request));
    request.struct_size = sizeof(request);
    request.path = p;
    request.format = (exr_format)format;
    request.title = t;
    request.size = (uint64_t)size;
    if (p) {
      out[0] = exr_android_import_commit(b->library, &request, &result, &b->error);
      if (out[0] == EXR_OK) { out[1] = result.book_id; out[2] = result.created; }
    }
    if (p) (*env)->ReleaseStringUTFChars(env, path, p);
    if (t) (*env)->ReleaseStringUTFChars(env, title, t);
  }
  (*env)->SetLongArrayRegion(env, array, 0, 3, out);
  return array;
}

JNIEXPORT jstring JNICALL Java_org_exreader_importentry_sample_NativeBridge_lastError(JNIEnv *env, jclass cls, jlong handle) {
  bridge *b = (bridge *)(intptr_t)handle;
  (void)cls;
  return (*env)->NewStringUTF(env, on_owner(b) ? b->error.message : "");
}

JNIEXPORT void JNICALL Java_org_exreader_importentry_sample_NativeBridge_close(JNIEnv *env, jclass cls, jlong handle) {
  bridge *b = (bridge *)(intptr_t)handle;
  (void)env; (void)cls;
  if (!on_owner(b)) return; /* wrong thread: leave it for the owner to close */
  exr_library_close(b->library);
  b->library = NULL;
  /* A failed close keeps the admission pinned until process death. */
  if (pc02_close(b->admission)) free(b);
}
