/* SPDX-License-Identifier: MIT
   Installed integration sample: a JNI bridge for a host whose SDK owner is ONE dedicated thread.
   Compile it into the host's own shared library and call every function from that thread only. */
#include <exr_android_import_entry.h>
#include <jni.h>
#include <pthread.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
  exr_library *library;
  pthread_t owner;
  exr_error error;
} bridge;

static int on_owner(bridge *b) { return b && pthread_equal(b->owner, pthread_self()); }

JNIEXPORT jlong JNICALL Java_org_exreader_importentry_sample_NativeBridge_open(JNIEnv *env, jclass cls, jstring path) {
  const char *utf = (*env)->GetStringUTFChars(env, path, NULL);
  bridge *b = calloc(1, sizeof(*b));
  (void)cls;
  if (!utf || !b) { if (utf) (*env)->ReleaseStringUTFChars(env, path, utf); free(b); return 0; }
  b->owner = pthread_self();
  if (exr_library_open(utf, &b->library, &b->error) != EXR_OK) { free(b); b = NULL; }
  (*env)->ReleaseStringUTFChars(env, path, utf);
  return (jlong)(intptr_t)b;
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
  free(b);
}
