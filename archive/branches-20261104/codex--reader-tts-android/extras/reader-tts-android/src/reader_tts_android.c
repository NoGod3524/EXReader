/* SPDX-License-Identifier: MIT */
/* Android TextToSpeech backend for the frozen reader TTS C ABI (0.1.0).
 *
 * Structure: one native handle per reader_tts, one Java Backend per handle.
 * Every Java callback enters through reader_tts_android_deliver, writes at
 * most one value into the per-handle bounded ring and returns. Nothing in this
 * file calls the host, allocates in a callback or blocks on the engine.
 */
#include "reader_tts.h"
#include "reader_tts_android.h"

#include <jni.h>
#include <math.h>
#include <pthread.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define EXR_TTS_MAX_HANDLES 8u
/* Slots held back for STARTED plus one terminal event of an accepted request. */
#define EXR_TTS_RESERVED_SLOTS 3u

struct exr_queued_event {
  uint64_t request_id;
  reader_tts_event_kind kind;
  reader_tts_status status;
  size_t start;
  size_t end;
  int has_range;
};

struct reader_tts {
  pthread_mutex_t lock;
  pthread_t owner;
  uint64_t cookie;
  jobject backend;
  size_t max_utf8_bytes;
  reader_tts_state state;
  reader_tts_status last_status;
  uint64_t request_id;
  uint64_t last_request_id;
  unsigned capabilities;
  int engine_ready;
  int closing;
  int closed;
  int registered;
  size_t head;
  size_t count;
  struct exr_queued_event queue[READER_TTS_EVENT_CAPACITY];
};

static pthread_mutex_t g_registry_lock = PTHREAD_MUTEX_INITIALIZER;
static reader_tts *g_handles[EXR_TTS_MAX_HANDLES];
static uint64_t g_cookie_sequence;
static JavaVM *g_vm;
static jobject g_context;
static jclass g_backend_class;
static jmethodID g_method_create;
static jmethodID g_method_speak;
static jmethodID g_method_stop;
static jmethodID g_method_voices;
static jmethodID g_method_release;
static int g_bound;

static void report(reader_tts_error *error, reader_tts_status code, int native_code) {
  if (!error) return;
  error->code = code;
  error->native_code = native_code;
}

static JNIEnv *acquire_env(int *attached) {
  JNIEnv *env = NULL;
  jint result = JNI_OK;
  *attached = 0;
  if (!g_vm) return NULL;
  result = (*g_vm)->GetEnv(g_vm, (void **)&env, JNI_VERSION_1_6);
  if (result == JNI_OK) return env;
  if (result != JNI_EDETACHED) return NULL;
  if ((*g_vm)->AttachCurrentThread(g_vm, &env, NULL) != JNI_OK) return NULL;
  *attached = 1;
  return env;
}

static void release_env(int attached) {
  if (attached && g_vm) (*g_vm)->DetachCurrentThread(g_vm);
}

static int clear_exception(JNIEnv *env) {
  if (!env || !(*env)->ExceptionCheck(env)) return 0;
  (*env)->ExceptionClear(env);
  return 1;
}

/* Strict UTF-8: no overlong forms, no encoded surrogates, no code points past
   U+10FFFF, no incomplete sequence and no NUL. */
static int utf8_valid(const unsigned char *text, size_t bytes) {
  size_t index = 0;
  while (index < bytes) {
    unsigned char lead = text[index];
    size_t extra = 0;
    unsigned long code = 0;
    if (lead < 0x80) {
      if (lead == 0) return 0;
      index += 1;
      continue;
    }
    if ((lead & 0xE0) == 0xC0) { extra = 1; code = lead & 0x1Fu; }
    else if ((lead & 0xF0) == 0xE0) { extra = 2; code = lead & 0x0Fu; }
    else if ((lead & 0xF8) == 0xF0) { extra = 3; code = lead & 0x07u; }
    else return 0;
    if (index + extra >= bytes) return 0;
    for (size_t step = 1; step <= extra; step++) {
      unsigned char next = text[index + step];
      if ((next & 0xC0) != 0x80) return 0;
      code = (code << 6) | (next & 0x3Fu);
    }
    if (extra == 1 && code < 0x80) return 0;
    if (extra == 2 && (code < 0x800 || (code >= 0xD800 && code <= 0xDFFF))) return 0;
    if (extra == 3 && (code < 0x10000 || code > 0x10FFFF)) return 0;
    index += extra + 1;
  }
  return 1;
}

static int queue_push(reader_tts *tts, uint64_t request_id, reader_tts_event_kind kind,
  reader_tts_status status, size_t start, size_t end, int has_range) {
  struct exr_queued_event *slot = NULL;
  if (tts->count == READER_TTS_EVENT_CAPACITY) {
    /* STARTED and terminal events are never dropped: retire the oldest RANGE,
       which the contract allows because ranges are advisory and mergeable. */
    if (kind == READER_TTS_RANGE) {
      tts->last_status = READER_TTS_LIMIT;
      return 0;
    }
    for (size_t offset = 0; offset < tts->count; offset++) {
      size_t position = (tts->head + offset) % READER_TTS_EVENT_CAPACITY;
      if (tts->queue[position].kind == READER_TTS_RANGE) {
        for (size_t shift = offset; shift + 1 < tts->count; shift++) {
          size_t from = (tts->head + shift + 1) % READER_TTS_EVENT_CAPACITY;
          size_t to = (tts->head + shift) % READER_TTS_EVENT_CAPACITY;
          tts->queue[to] = tts->queue[from];
        }
        tts->count -= 1;
        break;
      }
    }
    if (tts->count == READER_TTS_EVENT_CAPACITY) {
      tts->last_status = READER_TTS_LIMIT;
      return 0;
    }
  }
  slot = &tts->queue[(tts->head + tts->count) % READER_TTS_EVENT_CAPACITY];
  slot->request_id = request_id;
  slot->kind = kind;
  slot->status = status;
  slot->start = start;
  slot->end = end;
  slot->has_range = has_range;
  tts->count += 1;
  return 1;
}

static reader_tts *lookup(uint64_t cookie) {
  reader_tts *found = NULL;
  pthread_mutex_lock(&g_registry_lock);
  for (size_t index = 0; index < EXR_TTS_MAX_HANDLES; index++) {
    if (g_handles[index] && g_handles[index]->cookie == cookie) {
      found = g_handles[index];
      break;
    }
  }
  pthread_mutex_unlock(&g_registry_lock);
  return found;
}

static void unregister_handle(reader_tts *tts) {
  pthread_mutex_lock(&g_registry_lock);
  for (size_t index = 0; index < EXR_TTS_MAX_HANDLES; index++) {
    if (g_handles[index] == tts) g_handles[index] = NULL;
  }
  tts->registered = 0;
  pthread_mutex_unlock(&g_registry_lock);
}

static void drop_backend(JNIEnv *env, reader_tts *tts) {
  jobject backend = NULL;
  pthread_mutex_lock(&tts->lock);
  backend = tts->backend;
  tts->backend = NULL;
  pthread_mutex_unlock(&tts->lock);
  if (backend && env) (*env)->DeleteGlobalRef(env, backend);
}

static void finish_close(JNIEnv *env, reader_tts *tts) {
  pthread_mutex_lock(&tts->lock);
  tts->closing = 1;
  tts->closed = 1;
  tts->request_id = 0;
  tts->state = READER_TTS_CLOSED;
  pthread_mutex_unlock(&tts->lock);
  unregister_handle(tts);
  drop_backend(env, tts);
}

static uint64_t parse_request_id(JNIEnv *env, jstring utterance, int *ok) {
  const char *text = NULL;
  uint64_t value = 0;
  size_t length = 0;
  *ok = 0;
  if (!utterance) return 0;
  text = (*env)->GetStringUTFChars(env, utterance, NULL);
  if (!text) {
    clear_exception(env);
    return 0;
  }
  length = strlen(text);
  if (length == 0 || length > 20) {
    (*env)->ReleaseStringUTFChars(env, utterance, text);
    return 0;
  }
  for (size_t index = 0; index < length; index++) {
    if (text[index] < '0' || text[index] > '9') {
      (*env)->ReleaseStringUTFChars(env, utterance, text);
      return 0;
    }
    value = value * 10u + (uint64_t)(text[index] - '0');
  }
  (*env)->ReleaseStringUTFChars(env, utterance, text);
  *ok = 1;
  return value;
}

int reader_tts_android_deliver(JNIEnv *env, int64_t cookie, int kind, jstring utterance,
  int start, int end) {
  reader_tts *tts = NULL;
  uint64_t request_id = 0;
  int valid = 0;
  if (cookie <= 0) return 0;
  tts = lookup((uint64_t)cookie);
  if (!tts) return 0;
  request_id = parse_request_id(env, utterance, &valid);
  if (utterance && !valid) return 0;
  pthread_mutex_lock(&tts->lock);
  if (tts->closed) {
    pthread_mutex_unlock(&tts->lock);
    return 0;
  }
  switch (kind) {
    case READER_TTS_ANDROID_INIT_OK:
      tts->engine_ready = 1;
      tts->last_status = READER_TTS_OK;
      if (tts->state == READER_TTS_INITIALIZING) tts->state = READER_TTS_READY;
      pthread_mutex_unlock(&tts->lock);
      return 1;
    case READER_TTS_ANDROID_INIT_FAILED:
      tts->engine_ready = 0;
      tts->request_id = 0;
      tts->last_status = READER_TTS_UNAVAILABLE;
      if (!tts->closing) tts->state = READER_TTS_SERVICE_UNAVAILABLE;
      pthread_mutex_unlock(&tts->lock);
      return 1;
    case READER_TTS_ANDROID_STARTED:
      queue_push(tts, request_id, READER_TTS_STARTED, READER_TTS_OK, 0, 0, 0);
      if (tts->request_id == request_id) tts->state = READER_TTS_SPEAKING;
      pthread_mutex_unlock(&tts->lock);
      return 1;
    case READER_TTS_ANDROID_RANGE:
      if (start < 0 || end < start) {
        pthread_mutex_unlock(&tts->lock);
        return 0;
      }
      tts->capabilities |= READER_TTS_CAN_REPORT_RANGE;
      queue_push(tts, request_id, READER_TTS_RANGE, READER_TTS_OK,
        (size_t)start, (size_t)end, 1);
      pthread_mutex_unlock(&tts->lock);
      return 1;
    case READER_TTS_ANDROID_FINISHED:
      queue_push(tts, request_id, READER_TTS_FINISHED, READER_TTS_OK, 0, 0, 0);
      if (tts->request_id == request_id) {
        tts->request_id = 0;
        tts->state = tts->engine_ready ? READER_TTS_READY : READER_TTS_SERVICE_UNAVAILABLE;
      }
      pthread_mutex_unlock(&tts->lock);
      return 1;
    case READER_TTS_ANDROID_STOPPED:
      queue_push(tts, request_id, READER_TTS_STOPPED, READER_TTS_OK, 0, 0, 0);
      if (tts->request_id == request_id) {
        tts->request_id = 0;
        tts->state = tts->engine_ready ? READER_TTS_READY : READER_TTS_SERVICE_UNAVAILABLE;
      }
      pthread_mutex_unlock(&tts->lock);
      return 1;
    case READER_TTS_ANDROID_FAILED:
      queue_push(tts, request_id, READER_TTS_FAILED, READER_TTS_IO, 0, 0, 0);
      if (tts->request_id == request_id) {
        tts->request_id = 0;
        tts->state = tts->engine_ready ? READER_TTS_READY : READER_TTS_SERVICE_UNAVAILABLE;
      }
      tts->last_status = READER_TTS_IO;
      pthread_mutex_unlock(&tts->lock);
      return 1;
    case READER_TTS_ANDROID_RELEASED:
      pthread_mutex_unlock(&tts->lock);
      finish_close(env, tts);
      return 1;
    default:
      pthread_mutex_unlock(&tts->lock);
      return 0;
  }
}

reader_tts_status reader_tts_android_initialize(JNIEnv *env, jobject context) {
  jclass local_class = NULL;
  jclass class_ref = NULL;
  jobject local_context = NULL;
  jobject context_ref = NULL;
  jmethodID create = NULL;
  jmethodID speak = NULL;
  jmethodID stop = NULL;
  jmethodID voices = NULL;
  jmethodID release = NULL;
  jmethodID app_context = NULL;
  if (!env || !context) return READER_TTS_ARGUMENT;
  pthread_mutex_lock(&g_registry_lock);
  if (g_bound) {
    pthread_mutex_unlock(&g_registry_lock);
    return READER_TTS_OK;
  }
  pthread_mutex_unlock(&g_registry_lock);
  local_class = (*env)->FindClass(env, "org/exreader/tts/Backend");
  if (!local_class) {
    clear_exception(env);
    return READER_TTS_UNAVAILABLE;
  }
  create = (*env)->GetStaticMethodID(env, local_class, "create",
    "(Landroid/content/Context;J)Lorg/exreader/tts/Backend;");
  speak = (*env)->GetStaticMethodID(env, local_class, "speak", "(JJ[B[BD)I");
  stop = (*env)->GetStaticMethodID(env, local_class, "stop", "(J)I");
  voices = (*env)->GetStaticMethodID(env, local_class, "voices", "(J)[B");
  release = (*env)->GetStaticMethodID(env, local_class, "release", "(J)I");
  if (clear_exception(env) || !create || !speak || !stop || !voices || !release) {
    return READER_TTS_UNAVAILABLE;
  }
  if ((*env)->GetJavaVM(env, &g_vm) != JNI_OK || !g_vm) return READER_TTS_UNAVAILABLE;
  local_context = context;
  app_context = (*env)->GetMethodID(env, (*env)->GetObjectClass(env, context),
    "getApplicationContext", "()Landroid/content/Context;");
  if (app_context && !clear_exception(env)) {
    jobject resolved = (*env)->CallObjectMethod(env, context, app_context);
    if (!clear_exception(env) && resolved) local_context = resolved;
  }
  class_ref = (jclass)(*env)->NewGlobalRef(env, local_class);
  context_ref = (*env)->NewGlobalRef(env, local_context);
  if (!class_ref || !context_ref) {
    if (class_ref) (*env)->DeleteGlobalRef(env, class_ref);
    if (context_ref) (*env)->DeleteGlobalRef(env, context_ref);
    return READER_TTS_MEMORY;
  }
  pthread_mutex_lock(&g_registry_lock);
  g_backend_class = class_ref;
  g_context = context_ref;
  g_method_create = create;
  g_method_speak = speak;
  g_method_stop = stop;
  g_method_voices = voices;
  g_method_release = release;
  g_bound = 1;
  pthread_mutex_unlock(&g_registry_lock);
  return READER_TTS_OK;
}

reader_tts_status reader_tts_create(const reader_tts_config *config, reader_tts **out,
  reader_tts_error *error) {
  reader_tts_config resolved = { sizeof(reader_tts_config), READER_TTS_DEFAULT_MAX_UTF8_BYTES };
  reader_tts *tts = NULL;
  jobject context = NULL;
  jobject backend = NULL;
  JNIEnv *env = NULL;
  int attached = 0;
  size_t slot = EXR_TTS_MAX_HANDLES;
  if (!out) {
    report(error, READER_TTS_ARGUMENT, 0);
    return READER_TTS_ARGUMENT;
  }
  *out = NULL;
  if (config) {
    if (config->struct_size != sizeof(reader_tts_config)) {
      report(error, READER_TTS_ARGUMENT, 0);
      return READER_TTS_ARGUMENT;
    }
    resolved = *config;
    if (resolved.max_utf8_bytes == 0) resolved.max_utf8_bytes = READER_TTS_DEFAULT_MAX_UTF8_BYTES;
    if (resolved.max_utf8_bytes > READER_TTS_DEFAULT_MAX_UTF8_BYTES) {
      report(error, READER_TTS_ARGUMENT, 0);
      return READER_TTS_ARGUMENT;
    }
  }
  tts = (reader_tts *)calloc(1, sizeof(reader_tts));
  if (!tts) {
    report(error, READER_TTS_MEMORY, 0);
    return READER_TTS_MEMORY;
  }
  if (pthread_mutex_init(&tts->lock, NULL) != 0) {
    free(tts);
    report(error, READER_TTS_MEMORY, 0);
    return READER_TTS_MEMORY;
  }
  tts->owner = pthread_self();
  tts->max_utf8_bytes = resolved.max_utf8_bytes;
  tts->state = READER_TTS_INITIALIZING;
  tts->last_status = READER_TTS_OK;
  pthread_mutex_lock(&g_registry_lock);
  if (!g_bound) {
    pthread_mutex_unlock(&g_registry_lock);
    pthread_mutex_destroy(&tts->lock);
    free(tts);
    report(error, READER_TTS_UNAVAILABLE, 0);
    return READER_TTS_UNAVAILABLE;
  }
  for (slot = 0; slot < EXR_TTS_MAX_HANDLES; slot++) {
    if (!g_handles[slot]) break;
  }
  if (slot == EXR_TTS_MAX_HANDLES) {
    pthread_mutex_unlock(&g_registry_lock);
    pthread_mutex_destroy(&tts->lock);
    free(tts);
    report(error, READER_TTS_LIMIT, EXR_TTS_MAX_HANDLES);
    return READER_TTS_LIMIT;
  }
  g_cookie_sequence += 1;
  if (g_cookie_sequence == 0) g_cookie_sequence = 1;
  tts->cookie = g_cookie_sequence;
  g_handles[slot] = tts;
  tts->registered = 1;
  context = g_context;
  pthread_mutex_unlock(&g_registry_lock);
  env = acquire_env(&attached);
  if (!env) {
    unregister_handle(tts);
    pthread_mutex_destroy(&tts->lock);
    free(tts);
    report(error, READER_TTS_UNAVAILABLE, 0);
    return READER_TTS_UNAVAILABLE;
  }
  backend = (*env)->CallStaticObjectMethod(env, g_backend_class, g_method_create,
    context, (jlong)tts->cookie);
  if (clear_exception(env) || !backend) {
    release_env(attached);
    unregister_handle(tts);
    pthread_mutex_destroy(&tts->lock);
    free(tts);
    report(error, READER_TTS_UNAVAILABLE, 0);
    return READER_TTS_UNAVAILABLE;
  }
  tts->backend = (*env)->NewGlobalRef(env, backend);
  release_env(attached);
  if (!tts->backend) {
    unregister_handle(tts);
    pthread_mutex_destroy(&tts->lock);
    free(tts);
    report(error, READER_TTS_MEMORY, 0);
    return READER_TTS_MEMORY;
  }
  *out = tts;
  report(error, READER_TTS_OK, 0);
  return READER_TTS_OK;
}

reader_tts_status reader_tts_voices(reader_tts *tts, reader_tts_voice_list *list,
  reader_tts_error *error) {
  JNIEnv *env = NULL;
  jbyteArray blob = NULL;
  jsize bytes = 0;
  jbyte *raw = NULL;
  unsigned char *copy = NULL;
  reader_tts_voice *voices = NULL;
  size_t fields = 0;
  size_t count = 0;
  size_t total = 0;
  size_t scan = 0;
  int attached = 0;
  reader_tts_status status = READER_TTS_OK;
  if (!list) {
    report(error, READER_TTS_ARGUMENT, 0);
    return READER_TTS_ARGUMENT;
  }
  list->voices = NULL;
  list->count = 0;
  if (!tts) {
    report(error, READER_TTS_ARGUMENT, 0);
    return READER_TTS_ARGUMENT;
  }
  if (!pthread_equal(pthread_self(), tts->owner)) {
    report(error, READER_TTS_OWNER, 0);
    return READER_TTS_OWNER;
  }
  pthread_mutex_lock(&tts->lock);
  if (tts->closed || tts->closing) {
    pthread_mutex_unlock(&tts->lock);
    report(error, READER_TTS_UNAVAILABLE, 0);
    return READER_TTS_UNAVAILABLE;
  }
  if (tts->state == READER_TTS_INITIALIZING) {
    pthread_mutex_unlock(&tts->lock);
    report(error, READER_TTS_BUSY, 0);
    return READER_TTS_BUSY;
  }
  if (tts->state == READER_TTS_SERVICE_UNAVAILABLE) {
    pthread_mutex_unlock(&tts->lock);
    report(error, READER_TTS_UNAVAILABLE, 0);
    return READER_TTS_UNAVAILABLE;
  }
  pthread_mutex_unlock(&tts->lock);
  env = acquire_env(&attached);
  if (!env) {
    report(error, READER_TTS_UNAVAILABLE, 0);
    return READER_TTS_UNAVAILABLE;
  }
  blob = (jbyteArray)(*env)->CallStaticObjectMethod(env, g_backend_class, g_method_voices,
    (jlong)tts->cookie);
  if (clear_exception(env) || !blob) {
    release_env(attached);
    report(error, READER_TTS_UNAVAILABLE, 0);
    return READER_TTS_UNAVAILABLE;
  }
  bytes = (*env)->GetArrayLength(env, blob);
  if (bytes < 0) {
    release_env(attached);
    report(error, READER_TTS_IO, bytes);
    return READER_TTS_IO;
  }
  if (bytes == 0) {
    release_env(attached);
    report(error, READER_TTS_OK, 0);
    return READER_TTS_OK;
  }
  raw = (*env)->GetByteArrayElements(env, blob, NULL);
  if (!raw) {
    clear_exception(env);
    release_env(attached);
    report(error, READER_TTS_MEMORY, 0);
    return READER_TTS_MEMORY;
  }
  copy = (unsigned char *)malloc((size_t)bytes);
  if (!copy) {
    (*env)->ReleaseByteArrayElements(env, blob, raw, JNI_ABORT);
    release_env(attached);
    report(error, READER_TTS_MEMORY, 0);
    return READER_TTS_MEMORY;
  }
  memcpy(copy, raw, (size_t)bytes);
  (*env)->ReleaseByteArrayElements(env, blob, raw, JNI_ABORT);
  release_env(attached);
  if (copy[(size_t)bytes - 1] != 0) {
    free(copy);
    report(error, READER_TTS_IO, 0);
    return READER_TTS_IO;
  }
  for (scan = 0; scan < (size_t)bytes; scan++) {
    if (copy[scan] == 0) fields += 1;
  }
  if (fields == 0 || fields % 3 != 0) {
    free(copy);
    report(error, READER_TTS_IO, 0);
    return READER_TTS_IO;
  }
  count = fields / 3;
  if (count > READER_TTS_MAX_VOICES) {
    free(copy);
    report(error, READER_TTS_LIMIT, (int)READER_TTS_MAX_VOICES);
    return READER_TTS_LIMIT;
  }
  scan = 0;
  for (size_t index = 0; index < count; index++) {
    for (size_t field = 0; field < 3; field++) {
      size_t length = 0;
      while (scan + length < (size_t)bytes && copy[scan + length] != 0) length += 1;
      if (length == 0 || length > READER_TTS_MAX_VOICE_FIELD_BYTES ||
          !utf8_valid(copy + scan, length)) {
        free(copy);
        report(error, READER_TTS_LIMIT, (int)length);
        return READER_TTS_LIMIT;
      }
      scan += length + 1;
    }
  }
  total = (size_t)bytes;
  voices = (reader_tts_voice *)malloc(count * sizeof(reader_tts_voice) + total + 1);
  if (!voices) {
    free(copy);
    report(error, READER_TTS_MEMORY, 0);
    return READER_TTS_MEMORY;
  }
  {
    unsigned char *text = (unsigned char *)(voices + count);
    size_t source = 0;
    for (size_t index = 0; index < count; index++) {
      size_t length = 0;
      char *target = (char *)text;
      while (copy[source + length] != 0) length += 1;
      memcpy(text, copy + source, length);
      text[length] = 0;
      voices[index].id = target;
      text += length + 1;
      source += length + 1;
      length = 0;
      while (copy[source + length] != 0) length += 1;
      memcpy(text, copy + source, length);
      text[length] = 0;
      voices[index].name = (char *)text;
      text += length + 1;
      source += length + 1;
      length = 0;
      while (copy[source + length] != 0) length += 1;
      memcpy(text, copy + source, length);
      text[length] = 0;
      voices[index].language = (char *)text;
      text += length + 1;
      source += length + 1;
    }
  }
  free(copy);
  list->voices = voices;
  list->count = count;
  report(error, status, 0);
  return status;
}

void reader_tts_voice_list_free(reader_tts_voice_list *list) {
  if (!list) return;
  free(list->voices);
  list->voices = NULL;
  list->count = 0;
}

reader_tts_status reader_tts_speak(reader_tts *tts, uint64_t request_id, const char *utf8,
  size_t bytes, const char *voice_id, double rate, reader_tts_error *error) {
  jbyteArray text_array = NULL;
  jbyteArray voice_array = NULL;
  JNIEnv *env = NULL;
  jint outcome = 0;
  uint64_t previous_last = 0;
  size_t voice_bytes = 0;
  int attached = 0;
  if (!tts) {
    report(error, READER_TTS_ARGUMENT, 0);
    return READER_TTS_ARGUMENT;
  }
  if (!pthread_equal(pthread_self(), tts->owner)) {
    report(error, READER_TTS_OWNER, 0);
    return READER_TTS_OWNER;
  }
  if (request_id == 0 || !utf8 || bytes == 0) {
    report(error, READER_TTS_ARGUMENT, 0);
    return READER_TTS_ARGUMENT;
  }
  /* NaN fails both comparisons, so no separate NaN test is needed. */
  if (!(rate >= 0.5) || !(rate <= 2.0)) {
    report(error, READER_TTS_ARGUMENT, 0);
    return READER_TTS_ARGUMENT;
  }
  if (voice_id) voice_bytes = strlen(voice_id);
  if (voice_bytes > READER_TTS_MAX_VOICE_FIELD_BYTES) {
    report(error, READER_TTS_ARGUMENT, (int)voice_bytes);
    return READER_TTS_ARGUMENT;
  }
  if (bytes > tts->max_utf8_bytes) {
    report(error, READER_TTS_LIMIT, (int)tts->max_utf8_bytes);
    return READER_TTS_LIMIT;
  }
  if (!utf8_valid((const unsigned char *)utf8, bytes)) {
    report(error, READER_TTS_ARGUMENT, 0);
    return READER_TTS_ARGUMENT;
  }
  pthread_mutex_lock(&tts->lock);
  if (tts->state == READER_TTS_INITIALIZING) {
    pthread_mutex_unlock(&tts->lock);
    report(error, READER_TTS_BUSY, 0);
    return READER_TTS_BUSY;
  }
  if (tts->closed || tts->closing || tts->state == READER_TTS_SERVICE_UNAVAILABLE) {
    pthread_mutex_unlock(&tts->lock);
    report(error, READER_TTS_UNAVAILABLE, 0);
    return READER_TTS_UNAVAILABLE;
  }
  if (tts->request_id != 0) {
    pthread_mutex_unlock(&tts->lock);
    report(error, READER_TTS_BUSY, 0);
    return READER_TTS_BUSY;
  }
  if (request_id <= tts->last_request_id) {
    pthread_mutex_unlock(&tts->lock);
    report(error, READER_TTS_ARGUMENT, 0);
    return READER_TTS_ARGUMENT;
  }
  if (tts->count + EXR_TTS_RESERVED_SLOTS > READER_TTS_EVENT_CAPACITY) {
    pthread_mutex_unlock(&tts->lock);
    report(error, READER_TTS_LIMIT, (int)(READER_TTS_EVENT_CAPACITY - tts->count));
    return READER_TTS_LIMIT;
  }
  previous_last = tts->last_request_id;
  tts->last_request_id = request_id;
  tts->request_id = request_id;
  tts->state = READER_TTS_SPEAKING;
  tts->last_status = READER_TTS_OK;
  pthread_mutex_unlock(&tts->lock);
  env = acquire_env(&attached);
  if (!env) {
    pthread_mutex_lock(&tts->lock);
    tts->request_id = 0;
    tts->last_request_id = previous_last;
    tts->state = tts->engine_ready ? READER_TTS_READY : READER_TTS_SERVICE_UNAVAILABLE;
    pthread_mutex_unlock(&tts->lock);
    report(error, READER_TTS_UNAVAILABLE, 0);
    return READER_TTS_UNAVAILABLE;
  }
  text_array = (*env)->NewByteArray(env, (jsize)bytes);
  if (text_array) {
    (*env)->SetByteArrayRegion(env, text_array, 0, (jsize)bytes, (const jbyte *)utf8);
  }
  if (voice_bytes > 0) {
    voice_array = (*env)->NewByteArray(env, (jsize)voice_bytes);
    if (voice_array) {
      (*env)->SetByteArrayRegion(env, voice_array, 0, (jsize)voice_bytes, (const jbyte *)voice_id);
    }
  }
  if (clear_exception(env) || !text_array || (voice_bytes > 0 && !voice_array)) {
    release_env(attached);
    pthread_mutex_lock(&tts->lock);
    tts->request_id = 0;
    tts->last_request_id = previous_last;
    tts->state = tts->engine_ready ? READER_TTS_READY : READER_TTS_SERVICE_UNAVAILABLE;
    pthread_mutex_unlock(&tts->lock);
    report(error, READER_TTS_MEMORY, 0);
    return READER_TTS_MEMORY;
  }
  outcome = (*env)->CallStaticIntMethod(env, g_backend_class, g_method_speak,
    (jlong)tts->cookie, (jlong)request_id, text_array, voice_array, (jdouble)rate);
  if (clear_exception(env)) outcome = 5;
  release_env(attached);
  if (outcome != 0) {
    reader_tts_status mapped = READER_TTS_IO;
    if (outcome == 1) mapped = READER_TTS_ARGUMENT;
    else if (outcome == 3) mapped = READER_TTS_BUSY;
    else if (outcome == 4) mapped = READER_TTS_LIMIT;
    else if (outcome == 5) mapped = READER_TTS_UNAVAILABLE;
    pthread_mutex_lock(&tts->lock);
    tts->request_id = 0;
    tts->last_request_id = previous_last;
    tts->state = tts->engine_ready ? READER_TTS_READY : READER_TTS_SERVICE_UNAVAILABLE;
    tts->last_status = mapped;
    pthread_mutex_unlock(&tts->lock);
    report(error, mapped, (int)outcome);
    return mapped;
  }
  report(error, READER_TTS_OK, 0);
  return READER_TTS_OK;
}

reader_tts_status reader_tts_pause(reader_tts *tts, uint64_t request_id, reader_tts_error *error) {
  if (!tts) {
    report(error, READER_TTS_ARGUMENT, 0);
    return READER_TTS_ARGUMENT;
  }
  if (!pthread_equal(pthread_self(), tts->owner)) {
    report(error, READER_TTS_OWNER, 0);
    return READER_TTS_OWNER;
  }
  (void)request_id;
  report(error, READER_TTS_UNSUPPORTED, 0);
  return READER_TTS_UNSUPPORTED;
}

reader_tts_status reader_tts_resume(reader_tts *tts, uint64_t request_id, reader_tts_error *error) {
  if (!tts) {
    report(error, READER_TTS_ARGUMENT, 0);
    return READER_TTS_ARGUMENT;
  }
  if (!pthread_equal(pthread_self(), tts->owner)) {
    report(error, READER_TTS_OWNER, 0);
    return READER_TTS_OWNER;
  }
  (void)request_id;
  report(error, READER_TTS_UNSUPPORTED, 0);
  return READER_TTS_UNSUPPORTED;
}

reader_tts_status reader_tts_stop(reader_tts *tts, uint64_t request_id, reader_tts_error *error) {
  JNIEnv *env = NULL;
  jint outcome = 0;
  int attached = 0;
  int call = 0;
  if (!tts) {
    report(error, READER_TTS_ARGUMENT, 0);
    return READER_TTS_ARGUMENT;
  }
  if (!pthread_equal(pthread_self(), tts->owner)) {
    report(error, READER_TTS_OWNER, 0);
    return READER_TTS_OWNER;
  }
  if (request_id == 0) {
    report(error, READER_TTS_ARGUMENT, 0);
    return READER_TTS_ARGUMENT;
  }
  pthread_mutex_lock(&tts->lock);
  if (tts->closed || tts->closing) {
    pthread_mutex_unlock(&tts->lock);
    report(error, READER_TTS_UNAVAILABLE, 0);
    return READER_TTS_UNAVAILABLE;
  }
  if (tts->request_id == request_id) {
    tts->state = READER_TTS_STOPPING;
    call = 1;
  } else if (request_id > tts->last_request_id) {
    pthread_mutex_unlock(&tts->lock);
    report(error, READER_TTS_ARGUMENT, 0);
    return READER_TTS_ARGUMENT;
  }
  pthread_mutex_unlock(&tts->lock);
  if (call) {
    env = acquire_env(&attached);
    if (env) outcome = (*env)->CallStaticIntMethod(env, g_backend_class, g_method_stop,
      (jlong)tts->cookie);
    if (clear_exception(env)) outcome = 1;
    release_env(attached);
    if (outcome != 0) {
      pthread_mutex_lock(&tts->lock);
      tts->state = tts->engine_ready ? READER_TTS_SPEAKING : READER_TTS_SERVICE_UNAVAILABLE;
      pthread_mutex_unlock(&tts->lock);
      report(error, READER_TTS_IO, (int)outcome);
      return READER_TTS_IO;
    }
  }
  report(error, READER_TTS_OK, 0);
  return READER_TTS_OK;
}

reader_tts_status reader_tts_observe(reader_tts *tts, reader_tts_snapshot *snapshot,
  reader_tts_error *error) {
  if (!tts || !snapshot) {
    report(error, READER_TTS_ARGUMENT, 0);
    return READER_TTS_ARGUMENT;
  }
  if (!pthread_equal(pthread_self(), tts->owner)) {
    report(error, READER_TTS_OWNER, 0);
    return READER_TTS_OWNER;
  }
  pthread_mutex_lock(&tts->lock);
  snapshot->state = tts->state;
  snapshot->last_status = tts->last_status;
  snapshot->request_id = tts->request_id;
  snapshot->capabilities = tts->capabilities;
  pthread_mutex_unlock(&tts->lock);
  report(error, READER_TTS_OK, 0);
  return READER_TTS_OK;
}

reader_tts_status reader_tts_poll(reader_tts *tts, reader_tts_event *event, int *available,
  reader_tts_error *error) {
  if (!tts || !event || !available) {
    report(error, READER_TTS_ARGUMENT, 0);
    return READER_TTS_ARGUMENT;
  }
  if (!pthread_equal(pthread_self(), tts->owner)) {
    report(error, READER_TTS_OWNER, 0);
    return READER_TTS_OWNER;
  }
  memset(event, 0, sizeof(*event));
  pthread_mutex_lock(&tts->lock);
  if (tts->count == 0) {
    *available = 0;
    pthread_mutex_unlock(&tts->lock);
    report(error, READER_TTS_OK, 0);
    return READER_TTS_OK;
  }
  {
    struct exr_queued_event *slot = &tts->queue[tts->head];
    event->request_id = slot->request_id;
    event->kind = slot->kind;
    event->status = slot->status;
    event->start = slot->start;
    event->end = slot->end;
    event->has_range = slot->has_range;
    tts->head = (tts->head + 1) % READER_TTS_EVENT_CAPACITY;
    tts->count -= 1;
  }
  *available = 1;
  pthread_mutex_unlock(&tts->lock);
  report(error, READER_TTS_OK, 0);
  return READER_TTS_OK;
}

reader_tts_status reader_tts_request_close(reader_tts *tts, reader_tts_error *error) {
  JNIEnv *env = NULL;
  jint outcome = 0;
  int attached = 0;
  int already = 0;
  if (!tts) {
    report(error, READER_TTS_ARGUMENT, 0);
    return READER_TTS_ARGUMENT;
  }
  if (!pthread_equal(pthread_self(), tts->owner)) {
    report(error, READER_TTS_OWNER, 0);
    return READER_TTS_OWNER;
  }
  pthread_mutex_lock(&tts->lock);
  already = tts->closing || tts->closed;
  if (!already) {
    tts->closing = 1;
    if (tts->state != READER_TTS_CLOSED) tts->state = READER_TTS_CLOSING;
  }
  pthread_mutex_unlock(&tts->lock);
  if (already) {
    report(error, READER_TTS_OK, 0);
    return READER_TTS_OK;
  }
  env = acquire_env(&attached);
  if (env) outcome = (*env)->CallStaticIntMethod(env, g_backend_class, g_method_release,
    (jlong)tts->cookie);
  if (clear_exception(env)) outcome = 1;
  if (outcome != 0) {
    finish_close(env, tts);
    release_env(attached);
    report(error, READER_TTS_IO, (int)outcome);
    return READER_TTS_IO;
  }
  release_env(attached);
  report(error, READER_TTS_OK, 0);
  return READER_TTS_OK;
}

reader_tts_status reader_tts_destroy(reader_tts **handle, reader_tts_error *error) {
  reader_tts *tts = NULL;
  if (!handle) {
    report(error, READER_TTS_ARGUMENT, 0);
    return READER_TTS_ARGUMENT;
  }
  tts = *handle;
  if (!tts) {
    report(error, READER_TTS_ARGUMENT, 0);
    return READER_TTS_ARGUMENT;
  }
  if (!pthread_equal(pthread_self(), tts->owner)) {
    report(error, READER_TTS_OWNER, 0);
    return READER_TTS_OWNER;
  }
  pthread_mutex_lock(&tts->lock);
  if (!tts->closed) {
    pthread_mutex_unlock(&tts->lock);
    report(error, READER_TTS_BUSY, 0);
    return READER_TTS_BUSY;
  }
  pthread_mutex_unlock(&tts->lock);
  unregister_handle(tts);
  drop_backend(NULL, tts);
  pthread_mutex_destroy(&tts->lock);
  free(tts);
  *handle = NULL;
  report(error, READER_TTS_OK, 0);
  return READER_TTS_OK;
}
