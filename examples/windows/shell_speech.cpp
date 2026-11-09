/* SPDX-License-Identifier: MIT */
#include "shell_speech.h"
#include <initguid.h>
#include <sapi.h>
#include <string>
#include <vector>
#include <new>

struct shell_speech {
  ISpVoice *voice=nullptr;
  std::vector<ISpObjectToken *> tokens;
  std::vector<std::wstring> names;
  bool uninitialize=false,paused=false;
};
void shell_speech_free(shell_speech *s) {
  if(!s) return;
  if(s->voice) {shell_speech_stop(s);s->voice->Release();}
  for(auto *token:s->tokens) token->Release();
  bool uninitialize=s->uninitialize;delete s;
  if(uninitialize) CoUninitialize();
}
HRESULT shell_speech_create(shell_speech **out) {
  if(!out) return E_POINTER;
  *out=nullptr;
  auto *s=new(std::nothrow) shell_speech;
  if(!s) return E_OUTOFMEMORY;
  HRESULT hr=CoInitializeEx(nullptr,COINIT_APARTMENTTHREADED);
  s->uninitialize=SUCCEEDED(hr);
  if(FAILED(hr) && hr!=RPC_E_CHANGED_MODE) {delete s;return hr;}
  ISpObjectTokenCategory *category=nullptr;IEnumSpObjectTokens *enumerator=nullptr;
  hr=CoCreateInstance(CLSID_SpObjectTokenCategory,nullptr,CLSCTX_INPROC_SERVER,IID_ISpObjectTokenCategory,(void **)&category);
  if(SUCCEEDED(hr)) hr=category->SetId(SPCAT_VOICES,FALSE);
  if(SUCCEEDED(hr)) hr=category->EnumTokens(nullptr,nullptr,&enumerator);
  if(SUCCEEDED(hr)) {
    ISpObjectToken *token=nullptr;
    while(enumerator->Next(1,&token,nullptr)==S_OK) {
      LPWSTR local=nullptr,english=nullptr,id=nullptr;
      wchar_t language[16];swprintf(language,16,L"%x",(unsigned)GetUserDefaultUILanguage());
      if(FAILED(token->GetStringValue(language,&local))) token->GetStringValue(nullptr,&local);
      token->GetStringValue(L"409",&english);token->GetId(&id);
      std::wstring name=local ? local : id ? id : L"System voice";
      if(english && name!=english) {name+=L" / ";name+=english;}
      CoTaskMemFree(local);CoTaskMemFree(english);CoTaskMemFree(id);
      s->tokens.push_back(token);s->names.push_back(name);
    }
  }
  if(enumerator) enumerator->Release();
  if(category) category->Release();
  if(SUCCEEDED(hr) && !s->tokens.empty())
    hr=CoCreateInstance(CLSID_SpVoice,nullptr,CLSCTX_INPROC_SERVER,IID_ISpVoice,(void **)&s->voice);
  if(SUCCEEDED(hr) && s->voice) {
    ULONGLONG interest=SPFEI(SPEI_START_INPUT_STREAM)|SPFEI(SPEI_END_INPUT_STREAM)|SPFEI(SPEI_WORD_BOUNDARY)|SPFEI(SPEI_SENTENCE_BOUNDARY);
    hr=s->voice->SetInterest(interest,interest);
    if(SUCCEEDED(hr)) hr=s->voice->SetVoice(s->tokens[0]);
  }
  if(FAILED(hr)) {shell_speech_free(s);return hr;}
  *out=s;return S_OK;
}
size_t shell_speech_count(const shell_speech *s) {return s ? s->tokens.size():0;}
const wchar_t *shell_speech_name(const shell_speech *s,size_t i) {return s && i<s->names.size() ? s->names[i].c_str():L"";}
HRESULT shell_speech_voice(shell_speech *s,size_t i) {
  return s && s->voice && i<s->tokens.size() ? s->voice->SetVoice(s->tokens[i]):E_INVALIDARG;
}
HRESULT shell_speech_rate(shell_speech *s,int i) {
  static const long rates[]={-2,0,2,4};
  return s && s->voice && i>=0 && i<4 ? s->voice->SetRate(rates[i]):E_INVALIDARG;
}
HRESULT shell_speech_get_rate(shell_speech *s,long *rate) {return s && s->voice ? s->voice->GetRate(rate):E_UNEXPECTED;}
HRESULT shell_speech_speak(shell_speech *s,const char *ssml,unsigned long *stream) {
  if(!s || !s->voice || !ssml || !stream) return E_INVALIDARG;
  int n=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,ssml,-1,nullptr,0);
  if(!n) return E_INVALIDARG;
  std::wstring xml((size_t)n,L'\0');
  MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,ssml,-1,&xml[0],n);
  return s->voice->Speak(xml.c_str(),SPF_ASYNC|SPF_IS_XML|SPF_PARSE_SSML,stream);
}
HRESULT shell_speech_pause(shell_speech *s,int pause) {
  if(!s || !s->voice) return E_UNEXPECTED;
  if(s->paused==(pause!=0)) return S_OK;
  HRESULT hr=pause ? s->voice->Pause():s->voice->Resume();
  if(SUCCEEDED(hr)) s->paused=pause!=0;
  return hr;
}
HRESULT shell_speech_stop(shell_speech *s) {
  if(!s || !s->voice) return S_OK;
  HRESULT hr=s->voice->Speak(nullptr,SPF_PURGEBEFORESPEAK,nullptr);
  if(s->paused) {HRESULT resume=shell_speech_pause(s,0);if(SUCCEEDED(hr)) hr=resume;}
  SPEVENT e;ULONG count;
  while(s->voice->GetEvents(1,&e,&count)==S_OK && count) {
    if(e.elParamType==SPET_LPARAM_IS_STRING || e.elParamType==SPET_LPARAM_IS_POINTER) CoTaskMemFree((void *)e.lParam);
    else if(e.elParamType==SPET_LPARAM_IS_TOKEN || e.elParamType==SPET_LPARAM_IS_OBJECT) ((IUnknown *)e.lParam)->Release();
  }
  return hr;
}
int shell_speech_event(shell_speech *s,int *type,unsigned long *stream,size_t *offset) {
  SPEVENT e;ULONG count;
  if(!s || !s->voice || s->voice->GetEvents(1,&e,&count)!=S_OK || !count) return 0;
  *stream=e.ulStreamNum;*offset=(size_t)e.lParam;
  *type=e.eEventId==SPEI_START_INPUT_STREAM ? 1:e.eEventId==SPEI_END_INPUT_STREAM ? 3:2;
  return 1;
}
HRESULT shell_speech_status(shell_speech *s,unsigned long *state,unsigned long *stream,size_t *offset) {
  SPVOICESTATUS status={};
  if(!s || !s->voice) return E_UNEXPECTED;
  HRESULT hr=s->voice->GetStatus(&status,nullptr);
  if(SUCCEEDED(hr)) {*state=status.dwRunningState;*stream=status.ulCurrentStream;*offset=status.ulInputWordPos;}
  if(SUCCEEDED(hr) && FAILED(status.hrLastResult)) return status.hrLastResult;
  return hr;
}
