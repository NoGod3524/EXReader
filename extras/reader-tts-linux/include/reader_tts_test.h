/* SPDX-License-Identifier: MIT */
/* Fault-injection surface of the Linux reader TTS backend.
   Built and installed only when READER_TTS_BUILD_TEST_HOOKS=ON; never part of
   the shipped ABI. Every hook is owner-thread only and changes no behaviour
   unless it is explicitly armed. */
#ifndef READER_TTS_TEST_H
#define READER_TTS_TEST_H
#include "reader_tts.h"
#ifdef __cplusplus
extern "C" {
#endif

/* Fail the nth library allocation counting from this call: 0 = the next one,
   1 = the one after it, -1 = stop failing. */
void reader_tts_test_fail_alloc(int nth);
/* Feed one synthetic daemon callback through the real event path: kind 0=begin,
   1=end, 2=cancel. Used to prove early-callback buffering and late-callback
   filtering without depending on daemon timing. */
void reader_tts_test_inject(reader_tts *, long msg_id, int kind);
/* Record this id as the daemon's message id for the next speak instead of the
   value the daemon returns (the daemon still speaks). */
void reader_tts_test_force_msg_id(long msg_id);
/* Deliver one synthetic begin/end/cancel callback inside the next speak, while
   the library is between "submitted" and "message id known" (kind as above). */
void reader_tts_test_early_callback(int kind);
/* Message id the library currently associates with the active request. */
long reader_tts_test_msg_id(reader_tts *);
/* Push n synthetic terminal events to exercise the queue ceiling. */
void reader_tts_test_fill_queue(reader_tts *, size_t n);
/* Events currently queued. */
size_t reader_tts_test_queue_depth(reader_tts *);
/* Number of voices the connected daemon lists (SIZE_MAX when it cannot answer).
   Measures the real list length so the public ceiling has evidence behind it. */
size_t reader_tts_test_daemon_voice_count(reader_tts *);
#ifdef __cplusplus
}
#endif
#endif
