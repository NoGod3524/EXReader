/* SPDX-License-Identifier: MIT */
/* JNI adapter: the Android Keystore is reachable only through Java, so the C
   ABI forwards to CredentialStore's bridge methods, which perform AES-GCM
   with a non-exportable AndroidKeyStore key. */
#include "backend.h"
#include "exr_credentials_android.h"
#include <pthread.h>
#include <string.h>

static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
static JavaVM *vm;
static jobject context_ref;
static jclass store_class;
static jmethodID put_method, get_method, delete_method;

exr_credentials_status exr_credentials_android_initialize(JNIEnv *env, jobject context) {
  jclass local;
  jmethodID application;
  jobject app;
  exr_credentials_status status = EXR_CRED_UNAVAILABLE;
  if (!env || !context) return EXR_CRED_ARGUMENT;
  pthread_mutex_lock(&lock);
  if (store_class) { pthread_mutex_unlock(&lock); return EXR_CRED_OK; }
  local = (*env)->FindClass(env, "org/exreader/credentials/CredentialStore");
  if (!local) goto done;
  put_method = (*env)->GetStaticMethodID(env, local, "bridgePut",
    "(Landroid/content/Context;Ljava/lang/String;Ljava/lang/String;[B)I");
  get_method = (*env)->GetStaticMethodID(env, local, "bridgeGet",
    "(Landroid/content/Context;Ljava/lang/String;Ljava/lang/String;[B[I)I");
  delete_method = (*env)->GetStaticMethodID(env, local, "bridgeDelete",
    "(Landroid/content/Context;Ljava/lang/String;Ljava/lang/String;)I");
  application = (*env)->GetMethodID(env, (*env)->GetObjectClass(env, context),
    "getApplicationContext", "()Landroid/content/Context;");
  if (!put_method || !get_method || !delete_method || !application) goto done;
  app = (*env)->CallObjectMethod(env, context, application);
  if ((*env)->ExceptionCheck(env)) goto done;
  if ((*env)->GetJavaVM(env, &vm) != JNI_OK) goto done;
  context_ref = (*env)->NewGlobalRef(env, app ? app : context);
  store_class = (jclass)(*env)->NewGlobalRef(env, local);
  if (context_ref && store_class) status = EXR_CRED_OK;
done:
  if ((*env)->ExceptionCheck(env)) (*env)->ExceptionClear(env);
  if (status != EXR_CRED_OK) {
    if (context_ref) (*env)->DeleteGlobalRef(env, context_ref);
    if (store_class) (*env)->DeleteGlobalRef(env, store_class);
    context_ref = NULL;
    store_class = NULL;
  }
  pthread_mutex_unlock(&lock);
  return status;
}

/* Attaches non-Java threads for the duration of one call. */
static JNIEnv *enter(int *attached) {
  JNIEnv *env = NULL;
  JavaVM *current;
  *attached = 0;
  pthread_mutex_lock(&lock);
  current = store_class ? vm : NULL;
  pthread_mutex_unlock(&lock);
  if (!current) return NULL;
  if ((*current)->GetEnv(current, (void **)&env, JNI_VERSION_1_6) == JNI_EDETACHED) {
    if ((*current)->AttachCurrentThread(current, &env, NULL) != JNI_OK) return NULL;
    *attached = 1;
  }
  return env;
}

static void leave(JNIEnv *env, int attached) {
  if ((*env)->ExceptionCheck(env)) (*env)->ExceptionClear(env);
  if (attached) (*vm)->DetachCurrentThread(vm);
}

static exr_credentials_status from_java(JNIEnv *env, jint value) {
  if ((*env)->ExceptionCheck(env)) return EXR_CRED_IO;
  return value >= EXR_CRED_OK && value <= EXR_CRED_IO ? (exr_credentials_status)value : EXR_CRED_IO;
}

exr_credentials_status exr_cred_backend_put(const char *ns, const char *account,
                                            const uint8_t *secret, size_t secret_length) {
  int attached;
  JNIEnv *env = enter(&attached);
  jstring jns, jaccount;
  jbyteArray bytes;
  exr_credentials_status status = EXR_CRED_IO;
  if (!env) return EXR_CRED_UNAVAILABLE;
  jns = (*env)->NewStringUTF(env, ns);
  jaccount = (*env)->NewStringUTF(env, account);
  bytes = (*env)->NewByteArray(env, (jsize)secret_length);
  if (jns && jaccount && bytes) {
    jbyte zero[64];
    jsize i;
    (*env)->SetByteArrayRegion(env, bytes, 0, (jsize)secret_length, (const jbyte *)secret);
    status = from_java(env, (*env)->CallStaticIntMethod(env, store_class, put_method,
                                                        context_ref, jns, jaccount, bytes));
    memset(zero, 0, sizeof zero);
    for (i = 0; i < (jsize)secret_length; i += (jsize)sizeof zero) {
      jsize n = (jsize)secret_length - i < (jsize)sizeof zero ? (jsize)secret_length - i : (jsize)sizeof zero;
      (*env)->SetByteArrayRegion(env, bytes, i, n, zero);
    }
  }
  if (bytes) (*env)->DeleteLocalRef(env, bytes);
  if (jaccount) (*env)->DeleteLocalRef(env, jaccount);
  if (jns) (*env)->DeleteLocalRef(env, jns);
  leave(env, attached);
  return status;
}

exr_credentials_status exr_cred_backend_get(const char *ns, const char *account,
                                            uint8_t *buffer, size_t capacity, size_t *out_length) {
  int attached;
  JNIEnv *env = enter(&attached);
  jstring jns, jaccount;
  jbyteArray bytes;
  jintArray length;
  exr_credentials_status status = EXR_CRED_IO;
  if (!env) return EXR_CRED_UNAVAILABLE;
  jns = (*env)->NewStringUTF(env, ns);
  jaccount = (*env)->NewStringUTF(env, account);
  bytes = (*env)->NewByteArray(env, (jsize)EXR_CREDENTIALS_SECRET_MAX);
  length = (*env)->NewIntArray(env, 1);
  if (jns && jaccount && bytes && length) {
    status = from_java(env, (*env)->CallStaticIntMethod(env, store_class, get_method,
                                                        context_ref, jns, jaccount, bytes, length));
    if (status == EXR_CRED_OK) {
      jint n = 0;
      jbyte zero[64];
      jsize i;
      (*env)->GetIntArrayRegion(env, length, 0, 1, &n);
      if (n <= 0 || (size_t)n > EXR_CREDENTIALS_SECRET_MAX) {
        status = EXR_CRED_IO;
      } else {
        *out_length = (size_t)n;
        if ((size_t)n > capacity) status = EXR_CRED_ARGUMENT;
        else (*env)->GetByteArrayRegion(env, bytes, 0, n, (jbyte *)buffer);
      }
      memset(zero, 0, sizeof zero);
      for (i = 0; i < (jsize)EXR_CREDENTIALS_SECRET_MAX; i += (jsize)sizeof zero)
        (*env)->SetByteArrayRegion(env, bytes, i, (jsize)sizeof zero, zero);
    }
  }
  if (length) (*env)->DeleteLocalRef(env, length);
  if (bytes) (*env)->DeleteLocalRef(env, bytes);
  if (jaccount) (*env)->DeleteLocalRef(env, jaccount);
  if (jns) (*env)->DeleteLocalRef(env, jns);
  leave(env, attached);
  return status;
}

exr_credentials_status exr_cred_backend_delete(const char *ns, const char *account) {
  int attached;
  JNIEnv *env = enter(&attached);
  jstring jns, jaccount;
  exr_credentials_status status = EXR_CRED_IO;
  if (!env) return EXR_CRED_UNAVAILABLE;
  jns = (*env)->NewStringUTF(env, ns);
  jaccount = (*env)->NewStringUTF(env, account);
  if (jns && jaccount)
    status = from_java(env, (*env)->CallStaticIntMethod(env, store_class, delete_method,
                                                        context_ref, jns, jaccount));
  if (jaccount) (*env)->DeleteLocalRef(env, jaccount);
  if (jns) (*env)->DeleteLocalRef(env, jns);
  leave(env, attached);
  return status;
}
