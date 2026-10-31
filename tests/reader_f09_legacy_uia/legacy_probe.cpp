// SPDX-License-Identifier: MIT
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <objbase.h>
#include <oleauto.h>
#include <initguid.h>
#include <UIAutomation.h>
#include <wrl/client.h>
#include <filesystem>
#include <fstream>
#include <string>
#include <functional>
#include <cstdio>
using Microsoft::WRL::ComPtr;
namespace fs=std::filesystem;
struct Failure { HRESULT hr; };
static fs::path output;
static void require(bool ok){if(!ok)throw Failure{E_FAIL};}
static void check(HRESULT hr){if(FAILED(hr))throw Failure{hr};}
static void stage(const char *name){
  SYSTEMTIME t;GetSystemTime(&t);
  char line[512];int n=snprintf(line,sizeof(line),"%04u-%02u-%02uT%02u:%02u:%02u.%03uZ pid=%lu %s\n",
    t.wYear,t.wMonth,t.wDay,t.wHour,t.wMinute,t.wSecond,t.wMilliseconds,GetCurrentProcessId(),name);
  if(n<=0||n>=(int)sizeof(line))return;
  HANDLE f=CreateFileW((output/L"stages.log").c_str(),FILE_APPEND_DATA,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);
  if(f!=INVALID_HANDLE_VALUE){DWORD written;WriteFile(f,line,(DWORD)n,&written,NULL);FlushFileBuffers(f);CloseHandle(f);}
  printf("F09-NATIVE %s",line);fflush(stdout);
}
static void wait(const std::function<bool()> &predicate,DWORD ms){
  ULONGLONG start=GetTickCount64();
  while(GetTickCount64()-start<ms){if(predicate())return;Sleep(25);}
  throw Failure{HRESULT_FROM_WIN32(WAIT_TIMEOUT)};
}
static void key(WORD vk,bool up){
  INPUT i={};i.type=INPUT_KEYBOARD;i.ki.wVk=vk;i.ki.dwFlags=up?KEYEVENTF_KEYUP:0;
  require(SendInput(1,&i,sizeof(i))==1);
}
static void select_all(){key(VK_CONTROL,false);try{key('A',false);key('A',true);}catch(...){key(VK_CONTROL,true);throw;}key(VK_CONTROL,true);}
class EventHandler final:public IUIAutomationEventHandler{
  LONG refs=1;
public:
  HANDLE event=CreateEventW(NULL,FALSE,FALSE,NULL);
  ~EventHandler(){if(event)CloseHandle(event);}
  HRESULT STDMETHODCALLTYPE QueryInterface(REFIID id,void **out) override {
    if(!out)return E_POINTER;*out=NULL;
    if(IsEqualIID(id,IID_IUnknown)||IsEqualIID(id,__uuidof(IUIAutomationEventHandler))){*out=static_cast<IUIAutomationEventHandler*>(this);AddRef();return S_OK;}
    return E_NOINTERFACE;
  }
  ULONG STDMETHODCALLTYPE AddRef() override{return (ULONG)InterlockedIncrement(&refs);}
  ULONG STDMETHODCALLTYPE Release() override{LONG left=InterlockedDecrement(&refs);if(!left)delete this;return (ULONG)left;}
  HRESULT STDMETHODCALLTYPE HandleAutomationEvent(IUIAutomationElement*,EVENTID id) override{
    if(id==UIA_Text_TextSelectionChangedEventId)SetEvent(event);return S_OK;
  }
};
template<class T, auto ReleaseFunction> class UiaHandle {
  T value=nullptr;
public:
  UiaHandle()=default;
  UiaHandle(const UiaHandle&)=delete;
  UiaHandle& operator=(const UiaHandle&)=delete;
  UiaHandle(UiaHandle&& other) noexcept:value(other.value){other.value=nullptr;}
  ~UiaHandle(){Reset();}
  void Reset(){if(value){ReleaseFunction(value);value=nullptr;}}
  T Get()const{return value;}
  T* Address(){Reset();return &value;}
  explicit operator bool()const{return value!=nullptr;}
};
using LegacyNode=UiaHandle<HUIANODE,UiaNodeRelease>;
using LegacyPattern=UiaHandle<HUIAPATTERNOBJECT,UiaPatternRelease>;
using LegacyRange=UiaHandle<HUIATEXTRANGE,UiaTextRangeRelease>;
struct ArrayOwner { SAFEARRAY *value=nullptr; ~ArrayOwner(){if(value)SafeArrayDestroy(value);} };
struct VariantOwner { VARIANT value; VariantOwner(){VariantInit(&value);} ~VariantOwner(){VariantClear(&value);} };
static std::wstring text(HUIATEXTRANGE range){
  stage("legacy-get-text-before");BSTR value=NULL;check(TextRange_GetText(range,-1,&value));
  std::wstring result;if(value){result.assign(value,SysStringLen(value));SysFreeString(value);}
  char line[96];snprintf(line,sizeof(line),"legacy-get-text-after length=%llu",(unsigned long long)result.size());stage(line);
  return result;
}
static std::wstring document(HUIAPATTERNOBJECT pattern){
  stage("legacy-document-range-before");LegacyRange range;
  check(TextPattern_get_DocumentRange(pattern,range.Address()));require((bool)range);
  stage("legacy-document-range-after");return text(range.Get());
}
static LegacyRange selection(HUIAPATTERNOBJECT pattern){
  stage("legacy-get-selection-before");ArrayOwner array;check(TextPattern_GetSelection(pattern,&array.value));require(array.value!=nullptr);
  VARTYPE type=VT_EMPTY;check(SafeArrayGetVartype(array.value,&type));
  UINT dim=SafeArrayGetDim(array.value);LONG low=0,high=-1;
  check(SafeArrayGetLBound(array.value,1,&low));check(SafeArrayGetUBound(array.value,1,&high));
  char line[128];snprintf(line,sizeof(line),"legacy-array vt=%u dim=%u low=%ld high=%ld",(unsigned)type,dim,low,high);stage(line);
  // This is the legacy client result, not the provider's VT_UNKNOWN array.
  require(type==VT_VARIANT&&dim==1);if(high-low+1!=1)return {};
  VariantOwner element;check(SafeArrayGetElement(array.value,&low,&element.value));
  snprintf(line,sizeof(line),"legacy-element vt=%u",(unsigned)element.value.vt);stage(line);
  LegacyRange range;stage("legacy-convert-before");
  check(UiaHTextRangeFromVariant(&element.value,range.Address()));require((bool)range);
  stage("legacy-convert-after");
  // VARIANT and SAFEARRAY are destroyed before the returned owning range is read.
  return range;
}
struct WindowSearch{DWORD pid;HWND main=NULL;HWND page=NULL;};
static BOOL CALLBACK find_window(HWND hwnd,LPARAM parameter){
  auto *s=reinterpret_cast<WindowSearch*>(parameter);DWORD pid=0;GetWindowThreadProcessId(hwnd,&pid);
  if(pid==s->pid&&IsWindowVisible(hwnd)&&GetWindow(hwnd,GW_OWNER)==NULL){
    HWND page=GetDlgItem(hwnd,123);if(page){s->main=hwnd;s->page=page;return FALSE;}
  }return TRUE;
}
int wmain(int argc,wchar_t **argv){
  if(argc!=4)return 2;
  output=fs::absolute(argv[2]);fs::create_directories(output);
  PROCESS_INFORMATION process={};WindowSearch windows={};
  ComPtr<IUIAutomation> automation;ComPtr<IUIAutomationElement> page;
  LegacyNode node;LegacyPattern pattern;ComPtr<EventHandler> handler;
  bool registered=false,initialized=false,passed=false,ctrl=false,nonempty=false,clear=false,event=false,same=false,focus=false;
  HRESULT error=S_OK;const bool expected=std::wstring(argv[3])==L"present";
  try{
    check(CoInitializeEx(NULL,COINIT_MULTITHREADED));initialized=true;
    stage("start legacy-C-API-client bitness=64 apartment=MTA");
    check(CoCreateInstance(CLSID_CUIAutomation,NULL,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&automation)));
    { wchar_t module[32768]={};DWORD n=GetModuleFileNameW(GetModuleHandleW(L"UIAutomationCore.dll"),module,32768);
      require(n>0&&n<32768);std::wofstream f(output/L"loaded-uia-module.txt");f<<module; }
    fs::path exe=fs::absolute(argv[1]);fs::create_directories(output/L"profile");
    std::wstring command=L"\""+exe.wstring()+L"\" --data \""+(output/L"profile").wstring()+L"\" \""+(exe.parent_path()/L"Sample.epub").wstring()+L"\"";
    require(SetEnvironmentVariableW(L"F09_PROVIDER_LOG",(output/L"provider.log").c_str())!=0);
    STARTUPINFOW startup={};startup.cb=sizeof(startup);stage("host-start-before");
    require(CreateProcessW(exe.c_str(),command.data(),NULL,NULL,FALSE,0,NULL,exe.parent_path().c_str(),&startup,&process)!=0);
    CloseHandle(process.hThread);process.hThread=NULL;windows.pid=process.dwProcessId;
    {std::ofstream file(output/L"host.pid");file<<process.dwProcessId;}
    stage("host-start-after");
    wait([&]{require(WaitForSingleObject(process.hProcess,0)==WAIT_TIMEOUT);EnumWindows(find_window,reinterpret_cast<LPARAM>(&windows));return windows.page!=NULL;},120000);
    SetForegroundWindow(windows.main);check(automation->ElementFromHandle(windows.page,&page));stage("automation-element-created");
    check(UiaNodeFromHandle(windows.page,node.Address()));require((bool)node);
    wait([&]{
      try{
        pattern.Reset();HRESULT hr=UiaGetPatternProvider(node.Get(),UIA_TextPatternId,pattern.Address());
        if(hr==UIA_E_NOTSUPPORTED)return false;check(hr);if(!pattern)return false;
        BOOL enabled=FALSE;std::wstring value=document(pattern.Get());check(page->get_CurrentIsEnabled(&enabled));return value.size()>10&&enabled;
      }catch(const Failure &f){if(f.hr==UIA_E_ELEMENTNOTAVAILABLE){stage("ready transient-element-unavailable");return false;}throw;}
    },120000);
    check(page->SetFocus());wait([&]{BOOL value=FALSE;check(page->get_CurrentHasKeyboardFocus(&value));return value!=FALSE;},10000);
    std::wstring before=document(pattern.Get());
    handler.Attach(new EventHandler);require(handler->event!=NULL);
    check(automation->AddAutomationEventHandler(UIA_Text_TextSelectionChangedEventId,page.Get(),TreeScope_Element,NULL,handler.Get()));registered=true;
    stage("ctrl-a-before");select_all();stage("ctrl-a-sent");require(WaitForSingleObject(handler->event,5000)==WAIT_OBJECT_0);ctrl=true;
    wait([&]{auto range=selection(pattern.Get());return range&&text(range.Get()).size()>0;},5000);nonempty=true;
    check(automation->RemoveAutomationEventHandler(UIA_Text_TextSelectionChangedEventId,page.Get(),handler.Get()));registered=false;handler.Reset();
    handler.Attach(new EventHandler);require(handler->event!=NULL);
    check(automation->AddAutomationEventHandler(UIA_Text_TextSelectionChangedEventId,page.Get(),TreeScope_Element,NULL,handler.Get()));registered=true;
    stage("escape-before");key(VK_ESCAPE,false);key(VK_ESCAPE,true);stage("escape-sent");
    wait([&]{
      auto range=selection(pattern.Get());if(!range)return false;
      int cmp=1;check(TextRange_CompareEndpoints(range.Get(),TextPatternRangeEndpoint_Start,range.Get(),TextPatternRangeEndpoint_End,&cmp));if(cmp!=0)return false;
      LegacyRange doc;check(TextPattern_get_DocumentRange(pattern.Get(),doc.Address()));
      check(TextRange_CompareEndpoints(range.Get(),TextPatternRangeEndpoint_Start,doc.Get(),TextPatternRangeEndpoint_Start,&cmp));return cmp==0;
    },5000);clear=true;
    DWORD observed=WaitForSingleObject(handler->event,5000);require(observed==WAIT_OBJECT_0||observed==WAIT_TIMEOUT);event=observed==WAIT_OBJECT_0;
    check(automation->RemoveAutomationEventHandler(UIA_Text_TextSelectionChangedEventId,page.Get(),handler.Get()));registered=false;
    same=document(pattern.Get())==before;require(same);BOOL focused=FALSE;check(page->get_CurrentHasKeyboardFocus(&focused));focus=focused!=FALSE;require(focus);
    require(event==expected);passed=true;stage("all-assertions-passed");
  }catch(const Failure &f){error=f.hr;stage("HRESULT/assertion-failure");}
  catch(const std::exception &){error=E_FAIL;stage("standard-exception");}
  // /EHsc intentionally does not catch a native access violation or manufacture success.
  if(registered&&automation&&page&&handler)automation->RemoveAutomationEventHandler(UIA_Text_TextSelectionChangedEventId,page.Get(),handler.Get());
  handler.Reset();pattern.Reset();node.Reset();page.Reset();automation.Reset();
  if(process.hProcess){
    if(WaitForSingleObject(process.hProcess,0)==WAIT_TIMEOUT){
      if(windows.main)PostMessageW(windows.main,WM_CLOSE,0,0);
      if(WaitForSingleObject(process.hProcess,15000)==WAIT_TIMEOUT){TerminateProcess(process.hProcess,1);WaitForSingleObject(process.hProcess,15000);}
    }CloseHandle(process.hProcess);
  }
  if(initialized)CoUninitialize();
  std::ofstream report(output/L"report.json");
  report<<std::boolalpha<<"{\"passed\":"<<passed<<",\"consumer\":\"native-legacy-C-API-text-with-COM-events\",\"error_hresult\":"<<(unsigned long)error
    <<",\"ctrl_a_event\":"<<ctrl<<",\"nonempty_selection\":"<<nonempty<<",\"escape_cleared_to_document_start\":"<<clear
    <<",\"escape_selection_event\":"<<event<<",\"same_page_text\":"<<same<<",\"page_focus_preserved\":"<<focus
    <<",\"expected_selection_event\":"<<expected<<",\"event_observation_ms\":5000}";
  return passed?0:1;
}
