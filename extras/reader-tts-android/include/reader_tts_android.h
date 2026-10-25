/* SPDX-License-Identifier: MIT */
#ifndef READER_TTS_ANDROID_H
#define READER_TTS_ANDROID_H
#include <jni.h>
#include <stdint.h>
#include "reader_tts.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Event kinds the Android library reports through reader_tts_android_deliver.
   They are the only vocabulary shared with org.exreader.tts.Backend and are
   stable for this backend; hosts never see them because reader_tts_poll
   translates them into reader_tts_event values. */
enum {
  READER_TTS_ANDROID_INIT_OK = 0,
  READER_TTS_ANDROID_INIT_FAILED = 1,
  READER_TTS_ANDROID_STARTED = 2,
  READER_TTS_ANDROID_RANGE = 3,
  READER_TTS_ANDROID_FINISHED = 4,
  READER_TTS_ANDROID_STOPPED = 5,
  READER_TTS_ANDROID_FAILED = 6,
  READER_TTS_ANDROID_RELEASED = 7
};

/* Binds the C ABI to org.exreader.tts.Backend of the Android library. Call
   once from a Java thread (for example the host's own JNI entry) with any
   Context; only the application context is retained. Until it succeeds,
   reader_tts_create returns READER_TTS_UNAVAILABLE. ARGUMENT for NULLs,
   UNAVAILABLE when the Java class is not packaged. Idempotent. */
reader_tts_status reader_tts_android_initialize(JNIEnv *env, jobject context);

/* Callback entry for the host's JNI glue. org.exreader.tts.Backend invokes a
   native method whose body forwards every engine callback here unchanged.
   cookie is the handle cookie handed to Backend.create, kind is one of the
   READER_TTS_ANDROID_* values, utterance is the decimal request id (NULL for
   INIT_OK/INIT_FAILED/RELEASED) and start/end are UTF-8 byte offsets for
   RANGE or the native status code for INIT_FAILED/FAILED. It only writes to
   the bounded per-handle queue: it never calls back into the host, never
   blocks on the engine and never retains the jstring. Unknown or already
   released cookies, malformed utterance ids and offsets outside the request
   text are ignored; the return value says whether the event was consumed. An
   utterance callback (STARTED, RANGE, FINISHED, STOPPED, FAILED) is consumed
   only while its id is the active accepted request: an id that was never
   accepted, that the host has not used yet or that already ended leaves the
   state untouched, so a late or fabricated callback can neither end a request
   that is still speaking nor advance the handle past it. The utterance id is
   the unsigned decimal form of the 64-bit request id, so ids at or above
   2^63 arrive as negative Java longs and are still recognised. */
int reader_tts_android_deliver(JNIEnv *env, int64_t cookie, int kind, jstring utterance,
  int start, int end);
#ifdef __cplusplus
}
#endif
#endif
