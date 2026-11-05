/* SPDX-License-Identifier: MIT */
/* Driver contract between the installed C consumer and the Android probe app.
 * The consumer owns the named case table so the case names and the exercised
 * behaviour cannot drift apart; the app only installs the JNI bridge. */
#ifndef EXR_TTS_ANDROID_CONSUMER_H
#define EXR_TTS_ANDROID_CONSUMER_H
#ifdef __cplusplus
extern "C" {
#endif
/* engine_expected: 1 when a real TTS engine is installed, 0 when the run
 * deliberately removed every engine. Every case compares the observed state
 * against that expectation instead of accepting either. */
void exr_tts_consumer_set_mode(int engine_expected);
int exr_tts_consumer_case_count(void);
const char *exr_tts_consumer_case_name(int id);
/* 0 pass, 1 fail, 2 skipped because the observed capability is absent. */
int exr_tts_consumer_case(int id);
/* Human readable detail of the last case; never contains request text. */
const char *exr_tts_consumer_detail(void);

/* Rotation pair driven by the probe app: begin starts one long request on a
   dedicated handle, finish observes the surviving state and the single terminal
   event after the Activity was really recreated. 0 pass, 1 fail, 2 skip. */
int exr_tts_consumer_rotation_begin(void);
int exr_tts_consumer_rotation_finish(void);

/* Tab-separated "id<TAB>name<TAB>language" lines for every voice the installed
   C ABI reports; empty when no engine is present. The probe app compares them
   with the engine's own voice objects. */
const char *exr_tts_consumer_voice_lines(void);

/* Implemented by the host bridge (bridge.cpp). */
int exr_tts_platform_bind_null(void);
int exr_tts_platform_bind(void);
/* Cookie of the last real engine callback the bridge forwarded, or 0. */
long exr_tts_platform_last_cookie(void);
/* Forwards one fabricated engine callback for the given cookie through
   reader_tts_android_deliver, exactly as the AAR would. 1 consumed, 0 refused. */
int exr_tts_platform_deliver(long cookie, int kind, const char *utterance);
#ifdef __cplusplus
}
#endif
#endif
