/* SPDX-License-Identifier: MIT */
/*
 * reader_tts_windows.h - Windows-only extras of the EXReader TTS backend.
 *
 * reader_tts_windows_set_wav_output() redirects synthesis of later requests into a
 * WAV file through the same SAPI speak path, so a machine without an audio device can
 * still verify real synthesis. The debug_* functions exist for the package's own
 * acceptance tests (fault injection and accounting); hosts must not call them.
 * All functions here follow the owner-thread rule of reader_tts.h except the debug_*
 * ones, which are process-wide and may be called from any thread.
 */
#ifndef READER_TTS_WINDOWS_H
#define READER_TTS_WINDOWS_H
#include <stddef.h>
#include "reader_tts.h"
#ifdef __cplusplus
extern "C" {
#endif
/* path: UTF-16, NUL terminated, copied. NULL restores the default audio device.
 * Each later speak creates (overwrites) the file; the file is complete and closed
 * before that request's terminal event can be polled. Only while no request is active:
 * otherwise READER_TTS_BUSY. READER_TTS_UNAVAILABLE unless the state is READY. */
reader_tts_status reader_tts_windows_set_wav_output(reader_tts *, const wchar_t *path, reader_tts_error *);
/* The n-th allocation from now on (n>=1) fails once with READER_TTS_MEMORY; 0 disables. */
void reader_tts_windows_debug_fail_allocation_after(unsigned n);
/* Number of internal allocations not yet released (handles, voice lists, requests). */
long reader_tts_windows_debug_live_allocations(void);
/* Make the next created handles behave as if no speech service existed. */
void reader_tts_windows_debug_simulate_no_service(int enabled);
/* Delay the worker's initialisation of later handles so INITIALIZING is observable. */
void reader_tts_windows_debug_init_delay_ms(unsigned ms);
/* Last engine status the worker observed (test/diagnostic only; hosts must not call
   it). samples counts the status queries of the last and current request, so a
   report can prove the engine progress path really ran. */
typedef struct {
  int32_t hresult;
  uint32_t running_state;
  uint32_t word_position, word_length;
  uint32_t current_stream, last_queued;
  uint32_t samples;
} reader_tts_windows_engine_probe;
void reader_tts_windows_debug_engine_probe(reader_tts *, reader_tts_windows_engine_probe *);
#ifdef __cplusplus
}
#endif
#endif
