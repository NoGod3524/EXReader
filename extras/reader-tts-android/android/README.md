# EXReaderTTSAndroid

Optional Android `TextToSpeech` backend implementing the frozen reader TTS C ABI
(`reader_tts.h`, `READER_TTS_VERSION "0.1.0"`). Two pieces ship together:

| Piece | Path | Installed by |
| --- | --- | --- |
| C static archive + headers | `extras/reader-tts-android` | CMake, target `EXReaderTTSAndroid::reader_tts` |
| Android library `org.exreader.tts` | `extras/reader-tts-android/android/tts` | Gradle `com.android.library` |

The default reader build includes neither piece.

## Host wiring

1. Add the Android library project (or its AAR) to the host app.
2. Build and install the C package for the app ABI and link it into the host
   process from the host's own JNI glue:

```c
JNIEXPORT void JNICALL Java_com_example_Host_initializeTts(JNIEnv *env, jclass, jobject context) {
  if (reader_tts_android_initialize(env, context) != READER_TTS_OK) return;  /* class not packaged */
}
```

3. Implement the callback entry the library calls and forward it unchanged:

```c
JNIEXPORT void JNICALL Java_org_exreader_tts_Backend_nativeEvent(
    JNIEnv *env, jclass, jlong cookie, jint kind, jstring utterance, jint start, jint end) {
  reader_tts_android_deliver(env, (int64_t)cookie, (int)kind, utterance, (int)start, (int)end);
}
```

4. Use the C ABI: `reader_tts_create` returns `INITIALIZING` (readiness arrives later
   as READY or SERVICE_UNAVAILABLE), `reader_tts_voices` lists installed voices,
   `reader_tts_speak` copies the text and `reader_tts_poll` drains the bounded
   event queue on the creating thread.

`tests/reader_tts_android/consumer` is a complete working example: it is compiled
against the installed prefix only (`find_package(EXReaderTTSAndroid CONFIG
REQUIRED)`) and is the exact program the cloud acceptance runs.

## Threading and memory

* Every call except `reader_tts_voice_list_free` belongs to the thread that called
  `reader_tts_create`; other threads get `READER_TTS_OWNER`.
* The owner thread needs no `Looper`. Engine creation, the init handshake and
  shutdown run on the library's internal `HandlerThread`; the framework delivers
  the engine init callback on the process main thread (so a blocked main thread
  blocks readiness) and every utterance callback on an engine binder thread. The
  request calls (`speak`, `stop`, `voices`, `synthesizeToFile`) are synchronous
  engine calls on the owner thread and copy nothing into a callback.
* `speak` copies the input. Voice strings live in one block owned by the list and
  stay readable after the handle is destroyed until `reader_tts_voice_list_free`.
  Each voice carries the engine identifier (`id`), the localized display name
  (`name`) and a BCP 47 language tag; an empty `voice_id` re-selects the engine
  default voice instead of keeping the voice of an earlier request.
* Engine callbacks only write one value into the bounded 128-event ring; the host
  never sees a callback and no request text or engine error string is copied into
  the queue.

## Audio files

`Backend.synthesizeToFile(byte[] utf8, String voiceId, double rate, String path,
long timeoutMs)` is an Android-only helper for hosts that want a rendered artifact
instead of playback. It is not part of the C ABI.
