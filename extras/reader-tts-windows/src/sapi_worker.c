/* SPDX-License-Identifier: MIT */
/* SAPI 5 backend: one worker thread owns every COM object (ISpVoice, token
   enumeration, the optional WAV sink). It never calls the host, never allocates
   unbounded state and only publishes events into the bounded queue owned by
   reader_tts.c. Everything the host sees is a pure value taken with reader_tts_poll.

   Utterances are started with SPF_ASYNC so the worker stays responsive; pause,
   resume and stop are executed on the same thread, which is why a stopped request
   produces exactly one STOPPED event and no FINISHED for the old request. */
#include "internal.h"
#include <stdlib.h>
#include <string.h>
#if defined(_MSC_VER)
#pragma warning(push, 0)
#endif
#include <sapi.h>
#if defined(_MSC_VER)
#pragma warning(pop)
#endif

#define EXR_TTS_CAPS (READER_TTS_CAN_PAUSE | READER_TTS_CAN_REPORT_RANGE)
#define EXR_TTS_POLL_MS 20u

typedef struct {
  ISpVoice *voice;
  ISpStream *sink;         /* WAV output for the active request, else NULL */
  wchar_t *text;           /* owned until the terminal event */
  size_t text_units;
  size_t *unit_map;
  size_t text_bytes;
  uint64_t request_id;
  int speaking;
  int started;
} exr_tts_utterance;

/* ---- small helpers ---- */

static WAVEFORMATEX wave_format(void) {
  WAVEFORMATEX format;
  memset(&format, 0, sizeof format);
  format.wFormatTag = WAVE_FORMAT_PCM;
  format.nChannels = 1;
  format.nSamplesPerSec = 22050;
  format.wBitsPerSample = 16;
  format.nBlockAlign = (WORD)(format.nChannels * format.wBitsPerSample / 8);
  format.nAvgBytesPerSec = format.nSamplesPerSec * format.nBlockAlign;
  return format;
}

static char *utf16_to_utf8(const wchar_t *source) {
  size_t units = 0, i, out = 0;
  char *buffer;
  if (!source) return NULL;
  while (source[units]) units++;
  buffer = (char *)exr_tts_alloc(units * 4 + 1);
  if (!buffer) return NULL;
  for (i = 0; i < units; i++) {
    unsigned long code = (unsigned long)source[i];
    if (code >= 0xD800UL && code <= 0xDBFFUL && i + 1 < units) {
      unsigned long low = (unsigned long)source[i + 1];
      if (low >= 0xDC00UL && low <= 0xDFFFUL) {
        code = 0x10000UL + ((code - 0xD800UL) << 10) + (low - 0xDC00UL);
        i++;
      }
    }
    if (code < 0x80UL) {
      buffer[out++] = (char)code;
    } else if (code < 0x800UL) {
      buffer[out++] = (char)(0xC0UL | (code >> 6));
      buffer[out++] = (char)(0x80UL | (code & 0x3FUL));
    } else if (code < 0x10000UL) {
      buffer[out++] = (char)(0xE0UL | (code >> 12));
      buffer[out++] = (char)(0x80UL | ((code >> 6) & 0x3FUL));
      buffer[out++] = (char)(0x80UL | (code & 0x3FUL));
    } else {
      buffer[out++] = (char)(0xF0UL | (code >> 18));
      buffer[out++] = (char)(0x80UL | ((code >> 12) & 0x3FUL));
      buffer[out++] = (char)(0x80UL | ((code >> 6) & 0x3FUL));
      buffer[out++] = (char)(0x80UL | (code & 0x3FUL));
    }
  }
  buffer[out] = '\0';
  return buffer;
}

/* ---- voice category ---- */

static HRESULT open_voice_category(ISpObjectTokenCategory **category) {
  HRESULT hr = CoCreateInstance(&CLSID_SpObjectTokenCategory, NULL, CLSCTX_ALL, &IID_ISpObjectTokenCategory,
                                (void **)category);
  if (FAILED(hr)) return hr;
  hr = (*category)->lpVtbl->SetId(*category, SPCAT_VOICES, FALSE);
  if (FAILED(hr)) {
    (*category)->lpVtbl->Release(*category);
    *category = NULL;
  }
  return hr;
}

static reader_tts_status voice_count(ULONG *count, int *native) {
  ISpObjectTokenCategory *category = NULL;
  IEnumSpObjectTokens *tokens = NULL;
  HRESULT hr = open_voice_category(&category);
  *count = 0;
  if (SUCCEEDED(hr)) {
    hr = category->lpVtbl->EnumTokens(category, NULL, NULL, &tokens);
    category->lpVtbl->Release(category);
  }
  if (SUCCEEDED(hr) && tokens) {
    hr = tokens->lpVtbl->GetCount(tokens, count);
    tokens->lpVtbl->Release(tokens);
  }
  *native = (int)hr;
  if (FAILED(hr) || *count == 0) return READER_TTS_UNAVAILABLE;
  return READER_TTS_OK;
}

static reader_tts_status enumerate_voices(reader_tts_voice_list *list, int *native) {
  ISpObjectTokenCategory *category = NULL;
  IEnumSpObjectTokens *tokens = NULL;
  ULONG count = 0, index = 0;
  HRESULT hr;
  reader_tts_voice *voices;
  list->voices = NULL;
  list->count = 0;
  hr = open_voice_category(&category);
  if (SUCCEEDED(hr)) {
    hr = category->lpVtbl->EnumTokens(category, NULL, NULL, &tokens);
    category->lpVtbl->Release(category);
  }
  if (SUCCEEDED(hr) && tokens) {
    hr = tokens->lpVtbl->GetCount(tokens, &count);
    if (SUCCEEDED(hr) && count > 0) hr = tokens->lpVtbl->Reset(tokens);
  }
  if (FAILED(hr) || !tokens || count == 0) {
    if (tokens) tokens->lpVtbl->Release(tokens);
    *native = (int)hr;
    return READER_TTS_UNAVAILABLE;
  }
  voices = (reader_tts_voice *)exr_tts_alloc(count * sizeof *voices);
  if (!voices) {
    tokens->lpVtbl->Release(tokens);
    *native = 0;
    return READER_TTS_MEMORY;
  }
  {
    int out_of_memory = 0;
  for (;;) {
    ISpObjectToken *token = NULL;
    LPWSTR id = NULL, name = NULL, language = NULL;
    ULONG fetched = 0;
    hr = tokens->lpVtbl->Next(tokens, 1, &token, &fetched);
    if (FAILED(hr) || fetched == 0 || !token) break;
    if (index >= count) {
      token->lpVtbl->Release(token);
      break;
    }
    if (SUCCEEDED(token->lpVtbl->GetId(token, &id)) && id) {
      voices[index].id = utf16_to_utf8(id);
      CoTaskMemFree(id);
    }
    if (SUCCEEDED(((ISpDataKey *)token)->lpVtbl->GetStringValue((ISpDataKey *)token, L"Name", &name)) && name) {
      voices[index].name = utf16_to_utf8(name);
      CoTaskMemFree(name);
    }
    if (SUCCEEDED(((ISpDataKey *)token)->lpVtbl->GetStringValue((ISpDataKey *)token, L"Language", &language))
        && language) {
      wchar_t tag[64];
      size_t length = 0;
      int hex = 1;
      while (language[length] && length < 32) {
        wchar_t c = language[length];
        if (!((c >= L'0' && c <= L'9') || (c >= L'a' && c <= L'f') || (c >= L'A' && c <= L'F'))) hex = 0;
        length++;
      }
      if (hex && length > 0 && length <= 4) {
        LCID lcid = (LCID)wcstoul(language, NULL, 16);
        if (GetLocaleInfoW(MAKELCID(lcid, SORT_DEFAULT), LOCALE_SNAME, tag, 64) > 0) {
          voices[index].language = utf16_to_utf8(tag);
        }
      }
      if (!voices[index].language) voices[index].language = utf16_to_utf8(language);
      CoTaskMemFree(language);
    }
    token->lpVtbl->Release(token);
    if (!voices[index].id) {
      out_of_memory = 1;
      exr_tts_release(voices[index].name);
      exr_tts_release(voices[index].language);
      break;
    }
    index++;
    if (index == count) break;
  }
  tokens->lpVtbl->Release(tokens);
  if (index != count) {
    size_t i;
    for (i = 0; i < index; i++) {
      exr_tts_release(voices[i].id);
      exr_tts_release(voices[i].name);
      exr_tts_release(voices[i].language);
    }
    exr_tts_release(voices);
    *native = 0;
    return out_of_memory ? READER_TTS_MEMORY : READER_TTS_IO;
  }
  }
  list->voices = voices;
  list->count = count;
  *native = 0;
  return READER_TTS_OK;
}

/* Resolves a voice id from the voices category and makes it the voice's voice. */
static reader_tts_status apply_voice(ISpVoice *voice, const wchar_t *wanted, int *native) {
  ISpObjectTokenCategory *category = NULL;
  IEnumSpObjectTokens *tokens = NULL;
  ISpObjectToken *match = NULL;
  HRESULT hr;
  reader_tts_status status = READER_TTS_ARGUMENT;
  hr = open_voice_category(&category);
  if (SUCCEEDED(hr)) {
    hr = category->lpVtbl->EnumTokens(category, NULL, NULL, &tokens);
    category->lpVtbl->Release(category);
  }
  if (SUCCEEDED(hr) && tokens && wanted) {
    for (;;) {
      ISpObjectToken *token = NULL;
      LPWSTR id = NULL;
      ULONG fetched = 0;
      hr = tokens->lpVtbl->Next(tokens, 1, &token, &fetched);
      if (FAILED(hr) || fetched == 0 || !token) break;
      if (SUCCEEDED(token->lpVtbl->GetId(token, &id)) && id) {
        if (wcscmp(id, wanted) == 0) match = token;
        CoTaskMemFree(id);
      }
      if (match != token) token->lpVtbl->Release(token);
      if (match) break;
    }
  }
  if (tokens) tokens->lpVtbl->Release(tokens);
  *native = 0;
  if (!match) return status;
  hr = voice->lpVtbl->SetVoice(voice, match);
  match->lpVtbl->Release(match);
  if (FAILED(hr)) {
    *native = (int)hr;
    return READER_TTS_IO;
  }
  return READER_TTS_OK;
}

/* ---- output sink ---- */

static HRESULT open_wav_sink(ISpVoice *voice, const wchar_t *path, ISpStream **sink) {
  WAVEFORMATEX format = wave_format();
  ISpStream *stream = NULL;
  HRESULT hr = CoCreateInstance(&CLSID_SpStream, NULL, CLSCTX_ALL, &IID_ISpStream, (void **)&stream);
  if (FAILED(hr)) return hr;
  hr = stream->lpVtbl->BindToFile(stream, path, SPFM_CREATE_ALWAYS, &SPDFID_WaveFormatEx, &format, 0);
  if (FAILED(hr)) {
    stream->lpVtbl->Release(stream);
    return hr;
  }
  hr = voice->lpVtbl->SetOutput(voice, (IUnknown *)stream, FALSE);
  if (FAILED(hr)) {
    stream->lpVtbl->Release(stream);
    return hr;
  }
  *sink = stream;
  return S_OK;
}

static void close_wav_sink(ISpVoice *voice, ISpStream **sink) {
  if (!*sink) return;
  voice->lpVtbl->SetOutput(voice, NULL, FALSE);
  (*sink)->lpVtbl->Close(*sink);
  (*sink)->lpVtbl->Release(*sink);
  *sink = NULL;
}

/* ---- request lifecycle ---- */

static void publish_ready(reader_tts *handle) {
  if (exr_tts_closing(handle)) return;
  exr_tts_publish(handle, READER_TTS_READY, READER_TTS_OK, EXR_TTS_CAPS, 0);
}

static void finish_request(reader_tts *handle, exr_tts_utterance *utterance,
                           reader_tts_event_kind kind, reader_tts_status status) {
  exr_tts_queue_event event;
  close_wav_sink(utterance->voice, &utterance->sink);
  memset(&event, 0, sizeof event);
  event.request_id = utterance->request_id;
  event.kind = kind;
  event.status = status;
  exr_tts_push(handle, &event);
  exr_tts_release(utterance->text);
  exr_tts_release(utterance->unit_map);
  utterance->text = NULL;
  utterance->unit_map = NULL;
  utterance->text_units = 0;
  utterance->text_bytes = 0;
  utterance->request_id = 0;
  utterance->speaking = 0;
  utterance->started = 0;
  if (exr_tts_closing(handle)) return;
  if (status == READER_TTS_OK) publish_ready(handle);
  else exr_tts_publish(handle, READER_TTS_READY, status, EXR_TTS_CAPS, 0);
}

static void report_range(reader_tts *handle, exr_tts_utterance *utterance, const SPEVENTEX *source) {
  exr_tts_queue_event event;
  size_t start_units, length_units;
  if (source->lParam < 0 || source->wParam < 0) {
    finish_request(handle, utterance, READER_TTS_FAILED, READER_TTS_IO);
    return;
  }
  start_units = (size_t)source->lParam;
  length_units = (size_t)source->wParam;
  if (start_units > utterance->text_units || length_units > utterance->text_units - start_units) {
    /* SAPI reported a character position outside the text it was given. */
    finish_request(handle, utterance, READER_TTS_FAILED, READER_TTS_IO);
    return;
  }
  if (length_units == 0) return;
  memset(&event, 0, sizeof event);
  event.request_id = utterance->request_id;
  event.kind = READER_TTS_RANGE;
  event.status = READER_TTS_OK;
  event.start = utterance->unit_map[start_units];
  event.end = utterance->unit_map[start_units + length_units];
  event.has_range = 1;
  if (event.end <= event.start) return;
  if (exr_tts_push(handle, &event) != READER_TTS_OK) {
    finish_request(handle, utterance, READER_TTS_FAILED, READER_TTS_LIMIT);
  }
}

static void pump_events(reader_tts *handle, exr_tts_utterance *utterance) {
  ISpEventSource *source = (ISpEventSource *)utterance->voice;
  SPEVENTEX events[8];
  ULONG fetched = 0, index;
  if (FAILED(source->lpVtbl->GetEventsEx(source, 8, events, &fetched))) return;
  for (index = 0; index < fetched; index++) {
    switch (events[index].eEventId) {
      case SPEI_START_INPUT_STREAM:
        if (!utterance->started) {
          exr_tts_queue_event event;
          memset(&event, 0, sizeof event);
          event.request_id = utterance->request_id;
          event.kind = READER_TTS_STARTED;
          event.status = READER_TTS_OK;
          utterance->started = 1;
          if (exr_tts_push(handle, &event) != READER_TTS_OK) {
            finish_request(handle, utterance, READER_TTS_FAILED, READER_TTS_LIMIT);
            return;
          }
        }
        break;
      case SPEI_WORD_BOUNDARY:
        if (utterance->started && utterance->speaking) report_range(handle, utterance, &events[index]);
        break;
      case SPEI_END_INPUT_STREAM:
        /* Only the current utterance may finish; a stale end of a purged request is
           dropped so it can never terminate the request that replaced it. */
        if (utterance->speaking && utterance->started) {
          finish_request(handle, utterance, READER_TTS_FINISHED, READER_TTS_OK);
        }
        return;
      default:
        break;
    }
  }
}

static void purge(ISpVoice *voice) {
  if (voice) voice->lpVtbl->Speak(voice, NULL, SPF_PURGEBEFORESPEAK | SPF_ASYNC, NULL);
}

/* ---- command handling ---- */

static void set_ack(reader_tts *handle, reader_tts_status status, int native) {
  EnterCriticalSection(&handle->lock);
  handle->ack_result = status;
  handle->ack_native = native;
  LeaveCriticalSection(&handle->lock);
  SetEvent(handle->ack_event);
}

static int take_command(reader_tts *handle, exr_tts_command *out) {
  int taken = 0;
  EnterCriticalSection(&handle->lock);
  if (handle->cmd_pending) {
    *out = handle->cmd;
    memset(&handle->cmd, 0, sizeof handle->cmd);
    handle->cmd_pending = 0;
    taken = 1;
  }
  LeaveCriticalSection(&handle->lock);
  return taken;
}

static void drop_payload(exr_tts_command *command) {
  exr_tts_release(command->text);
  exr_tts_release(command->unit_map);
  exr_tts_release(command->voice_id);
  exr_tts_release(command->wav_path);
  command->text = NULL;
  command->unit_map = NULL;
  command->voice_id = NULL;
  command->wav_path = NULL;
}

static reader_tts_status start_speak(reader_tts *handle, exr_tts_utterance *utterance,
                                     ISpVoice *voice, exr_tts_command *command, int *native) {
  wchar_t *wav = NULL;
  HRESULT hr;
  *native = 0;
  if (!voice) return READER_TTS_UNAVAILABLE;
  if (utterance->speaking) return READER_TTS_BUSY;
  if (command->voice_id) {
    reader_tts_status applied = apply_voice(voice, command->voice_id, native);
    if (applied != READER_TTS_OK) return applied;
  }
  wav = exr_tts_copy_wav_path(handle);
  if (wav) {
    hr = open_wav_sink(voice, wav, &utterance->sink);
    exr_tts_release(wav);
    if (FAILED(hr)) {
      *native = (int)hr;
      return READER_TTS_IO;
    }
  }
  utterance->text = command->text;
  utterance->unit_map = command->unit_map;
  utterance->text_units = command->text_units;
  utterance->text_bytes = command->text_bytes;
  utterance->request_id = command->request_id;
  command->text = NULL;
  command->unit_map = NULL;
  hr = voice->lpVtbl->Speak(voice, utterance->text, SPF_ASYNC | SPF_PURGEBEFORESPEAK, NULL);
  if (FAILED(hr)) {
    *native = (int)hr;
    close_wav_sink(voice, &utterance->sink);
    exr_tts_release(utterance->text);
    exr_tts_release(utterance->unit_map);
    utterance->text = NULL;
    utterance->unit_map = NULL;
    utterance->request_id = 0;
    return READER_TTS_IO;
  }
  utterance->speaking = 1;
  utterance->started = 0;
  exr_tts_publish(handle, READER_TTS_SPEAKING, READER_TTS_OK, EXR_TTS_CAPS, command->request_id);
  return READER_TTS_OK;
}

/* Returns 1 when the command was CLOSE. */
static int handle_command(reader_tts *handle, exr_tts_utterance *utterance, ISpVoice **voice,
                          HANDLE *notify, exr_tts_command *command) {
  int native = 0;
  reader_tts_status status = READER_TTS_OK;
  switch (command->kind) {
    case EXR_TTS_CMD_SPEAK:
      status = start_speak(handle, utterance, *voice, command, &native);
      break;
    case EXR_TTS_CMD_PAUSE:
      if (!*voice || !utterance->speaking) {
        status = READER_TTS_ARGUMENT;
        break;
      }
      if (FAILED((*voice)->lpVtbl->Pause(*voice))) {
        status = READER_TTS_IO;
        break;
      }
      exr_tts_publish(handle, READER_TTS_PAUSED, READER_TTS_OK, EXR_TTS_CAPS, utterance->request_id);
      break;
    case EXR_TTS_CMD_RESUME:
      if (!*voice || !utterance->speaking) {
        status = READER_TTS_ARGUMENT;
        break;
      }
      if (FAILED((*voice)->lpVtbl->Resume(*voice))) {
        status = READER_TTS_IO;
        break;
      }
      exr_tts_publish(handle, READER_TTS_SPEAKING, READER_TTS_OK, EXR_TTS_CAPS, utterance->request_id);
      break;
    case EXR_TTS_CMD_STOP:
      if (!utterance->speaking) {
        status = READER_TTS_ARGUMENT;
        break;
      }
      purge(*voice);
      finish_request(handle, utterance, READER_TTS_STOPPED, READER_TTS_OK);
      break;
    case EXR_TTS_CMD_VOICES: {
      reader_tts_voice_list voices;
      voices.voices = NULL;
      voices.count = 0;
      status = enumerate_voices(&voices, &native);
      EnterCriticalSection(&handle->lock);
      handle->ack_voices = voices;
      LeaveCriticalSection(&handle->lock);
      break;
    }
    case EXR_TTS_CMD_SET_WAV: {
      wchar_t *previous;
      EnterCriticalSection(&handle->lock);
      previous = handle->wav_path;
      handle->wav_path = command->wav_path;
      command->wav_path = NULL;
      LeaveCriticalSection(&handle->lock);
      exr_tts_release(previous);
      break;
    }
    case EXR_TTS_CMD_CLOSE:
      if (utterance->speaking) {
        purge(*voice);
        finish_request(handle, utterance, READER_TTS_STOPPED, READER_TTS_OK);
      }
      if (*voice) {
        (*voice)->lpVtbl->Release(*voice);
        *voice = NULL;
      }
      *notify = NULL;
      set_ack(handle, READER_TTS_OK, 0);
      return 1;
    default:
      status = READER_TTS_ARGUMENT;
      break;
  }
  drop_payload(command);
  set_ack(handle, status, native);
  return 0;
}

DWORD WINAPI exr_tts_worker_main(LPVOID parameter) {
  reader_tts *handle = (reader_tts *)parameter;
  exr_tts_utterance utterance;
  ISpVoice *voice = NULL;
  HANDLE notify = NULL;
  int com = 0;
  HRESULT hr;
  memset(&utterance, 0, sizeof utterance);
  {
    LONG delay = exr_tts_debug_init_delay();
    if (delay > 0) Sleep((DWORD)delay);
  }
  hr = CoInitializeEx(NULL, COINIT_MULTITHREADED);
  if (hr == RPC_E_CHANGED_MODE) hr = CoInitializeEx(NULL, COINIT_APARTMENTTHREADED);
  if (SUCCEEDED(hr)) com = 1;
  if (com && !exr_tts_debug_no_service()) {
    hr = CoCreateInstance(&CLSID_SpVoice, NULL, CLSCTX_ALL, &IID_ISpVoice, (void **)&voice);
    if (SUCCEEDED(hr)) {
      ULONG count = 0;
      int native = 0;
      if (voice_count(&count, &native) != READER_TTS_OK) {
        voice->lpVtbl->Release(voice);
        voice = NULL;
      }
    }
    if (voice) {
      ULONGLONG interest = SPFEI(SPEI_START_INPUT_STREAM) | SPFEI(SPEI_END_INPUT_STREAM)
                         | SPFEI(SPEI_WORD_BOUNDARY);
      ISpNotifySource *source = (ISpNotifySource *)voice;
      ISpEventSource *events = (ISpEventSource *)voice;
      if (FAILED(source->lpVtbl->SetNotifyWin32Event(source))
          || FAILED(events->lpVtbl->SetInterest(events, interest, interest))) {
        voice->lpVtbl->Release(voice);
        voice = NULL;
      } else {
        notify = source->lpVtbl->GetNotifyEventHandle(source);
      }
    }
  }
  if (!exr_tts_closing(handle)) {
    if (voice) {
      exr_tts_publish(handle, READER_TTS_READY, READER_TTS_OK, EXR_TTS_CAPS, 0);
    } else {
      exr_tts_publish(handle, READER_TTS_SERVICE_UNAVAILABLE, READER_TTS_UNAVAILABLE, 0, 0);
    }
  }
  for (;;) {
    exr_tts_command command;
    HANDLE waits[2];
    DWORD count = 1, timeout = INFINITE, result;
    if (take_command(handle, &command)) {
      if (handle_command(handle, &utterance, &voice, &notify, &command)) break;
      continue;
    }
    if (utterance.speaking) pump_events(handle, &utterance);
    if (exr_tts_closing(handle) && !utterance.speaking) break;
    waits[0] = handle->cmd_event;
    if (utterance.speaking) {
      if (notify) {
        waits[count++] = notify;
      } else {
        timeout = EXR_TTS_POLL_MS;
      }
    }
    result = WaitForMultipleObjects(count, waits, FALSE, timeout);
    if (result == WAIT_FAILED) break;
  }
  if (utterance.speaking) {
    purge(voice);
    close_wav_sink(voice, &utterance.sink);
    exr_tts_release(utterance.text);
    exr_tts_release(utterance.unit_map);
  }
  if (voice) voice->lpVtbl->Release(voice);
  if (com) CoUninitialize();
  return 0;
}
