/* SPDX-License-Identifier: MIT */
#ifndef EXR_SHELL_SPEECH_H
#define EXR_SHELL_SPEECH_H
#include <windows.h>
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct shell_speech shell_speech;
/* All calls belong to the UI COM apartment. Names borrow the adapter lifetime. */
HRESULT shell_speech_create(shell_speech **out);
void shell_speech_free(shell_speech *speech);
size_t shell_speech_count(const shell_speech *speech);
const wchar_t *shell_speech_name(const shell_speech *speech,size_t index);
HRESULT shell_speech_voice(shell_speech *speech,size_t index);
HRESULT shell_speech_rate(shell_speech *speech,int index);
HRESULT shell_speech_get_rate(shell_speech *speech,long *rate);
HRESULT shell_speech_speak(shell_speech *speech,const char *ssml,unsigned long *stream);
HRESULT shell_speech_pause(shell_speech *speech,int pause);
HRESULT shell_speech_stop(shell_speech *speech);
/* type: 1=start, 2=word/sentence boundary (UTF-16 XML offset), 3=end. */
int shell_speech_event(shell_speech *speech,int *type,unsigned long *stream,size_t *offset);
HRESULT shell_speech_status(shell_speech *speech,unsigned long *state,unsigned long *stream,size_t *offset);
#ifdef __cplusplus
}
#endif
#endif
