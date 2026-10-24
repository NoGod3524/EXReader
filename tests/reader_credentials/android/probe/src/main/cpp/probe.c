/* SPDX-License-Identifier: MIT */
/* Runs the shared C suite through the installed C ABI on the emulator. */
#include <jni.h>
#include <stdlib.h>
#include <string.h>
#include "exr_credentials_android.h"
#include "suite.h"

typedef struct { char *text; size_t length, capacity; } lines;

static void emit(void *context, const char *line) {
  lines *out = (lines *)context;
  size_t n = strlen(line);
  if (out->length + n + 2 > out->capacity) {
    size_t capacity = (out->capacity + n + 2) * 2;
    char *grown = (char *)realloc(out->text, capacity);
    if (!grown) return;
    out->text = grown;
    out->capacity = capacity;
  }
  memcpy(out->text + out->length, line, n);
  out->length += n;
  out->text[out->length++] = '\n';
  out->text[out->length] = 0;
}

JNIEXPORT jstring JNICALL
Java_org_exreader_credentials_probe_CredentialsProbe_runNative(JNIEnv *env, jclass type, jobject context,
                                                              jstring phase, jstring text, jboolean bind) {
  lines out = {NULL, 0, 0};
  suite_input *input = (suite_input *)calloc(1, sizeof *input);
  const char *phase_chars = (*env)->GetStringUTFChars(env, phase, NULL);
  const char *text_chars = (*env)->GetStringUTFChars(env, text, NULL);
  jstring result;
  (void)type;
  emit(&out, "");
  out.length = 0;
  if (bind) {
    exr_credentials_status status = exr_credentials_android_initialize(env, context);
    emit(&out, status == EXR_CRED_OK ? "check jni-bind-keystore-store pass OK"
                                     : "check jni-bind-keystore-store fail not-bound");
  }
  if (!input || !phase_chars || !text_chars || suite_parse(text_chars, input))
    emit(&out, "check harness-input fail malformed");
  else if (suite_run(phase_chars, input, emit, &out) < 0)
    emit(&out, "check harness-phase fail unknown");
  if (input) {
    suite_wipe(input);
    free(input);
  }
  if (text_chars) (*env)->ReleaseStringUTFChars(env, text, text_chars);
  if (phase_chars) (*env)->ReleaseStringUTFChars(env, phase, phase_chars);
  result = (*env)->NewStringUTF(env, out.text ? out.text : "");
  free(out.text);
  return result;
}
