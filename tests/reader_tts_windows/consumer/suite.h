/* SPDX-License-Identifier: MIT */
/* Acceptance suite for the installed EXReaderTTSWindows package. The consumer
   links only EXReaderTTSWindows::reader_tts from the installed prefix and drives
   the real Windows SAPI backend; nothing is mocked. Output format:
     check <id> <pass|fail> <detail>
     phase <name> <passed> <total>
     wavfile <absolute path> <minimum duration in ms>
     info <key> <value>
   The Actions harness verifies the emitted WAV containers and requires every
   check id of a phase to be present exactly once. */
#ifndef EXR_TTS_SUITE_H
#define EXR_TTS_SUITE_H

#include <stddef.h>

typedef struct suite suite;

/* The WAV directory must exist. Returns NULL on allocation failure. */
suite *suite_create(const char *wav_dir);
void suite_destroy(suite *state);
/* Runs one phase; returns 0 when every check of the phase passed. */
int suite_run(suite *state, const char *phase);

#endif
