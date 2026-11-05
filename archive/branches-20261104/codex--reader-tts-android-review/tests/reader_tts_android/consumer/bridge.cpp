/* SPDX-License-Identifier: MIT */
/* JNI glue between the probe app and the installed C consumer.
 *
 * This file belongs to the probe app, not to the installed package: it only
 * forwards the two Android-specific entry points (Context binding and the
 * engine callback) into reader_tts_android_* and exposes the named case table.
 * The saved JNIEnv is valid because the probe runs every case on one thread.
 */
#include "reader_tts.h"
#include "reader_tts_android.h"

#include "consumer.h"

#include <jni.h>

namespace {
JNIEnv *g_env;
jobject g_context;
jlong g_last_cookie;
}  // namespace

extern "C" JNIEXPORT void JNICALL
Java_org_exreader_tts_Backend_nativeEvent(JNIEnv *env, jclass, jlong cookie, jint kind,
  jstring utterance, jint start, jint end) {
  g_last_cookie = cookie;
  reader_tts_android_deliver(env, (int64_t)cookie, (int)kind, utterance, (int)start, (int)end);
}

long exr_tts_platform_last_cookie(void) {
  return (long)g_last_cookie;
}

/* Fabricates one engine callback for a handle the probe itself drives, through
   the same entry the AAR uses. The saved JNIEnv belongs to the probe thread,
   so this must be called from it (the case table is single threaded). */
int exr_tts_platform_deliver(long cookie, int kind, const char *utterance) {
  jstring text = nullptr;
  int consumed = 0;
  if (g_env == nullptr) return 0;
  if (utterance != nullptr) {
    text = g_env->NewStringUTF(utterance);
    if (text == nullptr) return 0;
  }
  consumed = reader_tts_android_deliver(g_env, (int64_t)cookie, (int)kind, text, 0, 0);
  if (text != nullptr) g_env->DeleteLocalRef(text);
  return consumed;
}

extern "C" JNIEXPORT void JNICALL
Java_org_exreader_tts_probe_NativeTts_setContext(JNIEnv *env, jclass, jobject context) {
  if (g_context) env->DeleteGlobalRef(g_context);
  g_env = env;
  g_context = env->NewGlobalRef(context);
}

int exr_tts_platform_bind_null(void) {
  return (int)reader_tts_android_initialize(nullptr, nullptr);
}

int exr_tts_platform_bind(void) {
  return (int)reader_tts_android_initialize(g_env, g_context);
}

extern "C" JNIEXPORT void JNICALL
Java_org_exreader_tts_probe_NativeTts_setMode(JNIEnv *, jclass, jint engine_expected) {
  exr_tts_consumer_set_mode((int)engine_expected);
}

extern "C" JNIEXPORT jint JNICALL
Java_org_exreader_tts_probe_NativeTts_caseCount(JNIEnv *, jclass) {
  return (jint)exr_tts_consumer_case_count();
}

extern "C" JNIEXPORT jstring JNICALL
Java_org_exreader_tts_probe_NativeTts_caseName(JNIEnv *env, jclass, jint id) {
  return env->NewStringUTF(exr_tts_consumer_case_name((int)id));
}

extern "C" JNIEXPORT jint JNICALL
Java_org_exreader_tts_probe_NativeTts_runCase(JNIEnv *, jclass, jint id) {
  return (jint)exr_tts_consumer_case((int)id);
}

extern "C" JNIEXPORT jstring JNICALL
Java_org_exreader_tts_probe_NativeTts_caseDetail(JNIEnv *env, jclass) {
  return env->NewStringUTF(exr_tts_consumer_detail());
}

extern "C" JNIEXPORT jstring JNICALL
Java_org_exreader_tts_probe_NativeTts_voiceLines(JNIEnv *env, jclass) {
  return env->NewStringUTF(exr_tts_consumer_voice_lines());
}

extern "C" JNIEXPORT jint JNICALL
Java_org_exreader_tts_probe_NativeTts_rotationBegin(JNIEnv *, jclass) {
  return (jint)exr_tts_consumer_rotation_begin();
}

extern "C" JNIEXPORT jint JNICALL
Java_org_exreader_tts_probe_NativeTts_rotationFinish(JNIEnv *, jclass) {
  return (jint)exr_tts_consumer_rotation_finish();
}

extern "C" JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *, void *) {
  return JNI_VERSION_1_6;
}
