// SPDX-License-Identifier: MIT
// Control: one legacy method per process on a direct DocumentRange handle; strict S_OK, raw value kept.
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
  const std::wstring variant=argv[3];
  if(variant!=L"compare"&&variant!=L"clone"&&variant!=L"expand"&&variant!=L"gettext")return 2;
  PROCESS_INFORMATION process={};WindowSearch windows={};
  ComPtr<IUIAutomation> automation;ComPtr<IUIAutomationElement> page;
  LegacyNode node;LegacyPattern pattern;
  bool initialized=false,passed=false,method_returned=false,method_ok=false,focus=false;
  HRESULT error=S_OK,method_hr=S_OK;
  try{
    check(CoInitializeEx(NULL,COINIT_MULTITHREADED));initialized=true;
    std::string mode="start legacy-direct-handle-control-client bitness=64 apartment=MTA no-selection-input variant=";
    mode.append(variant.begin(),variant.end());stage(mode.c_str());
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
    stage("direct-document-positive-control");require(before.size()>10);
    LegacyRange range;check(TextPattern_get_DocumentRange(pattern.Get(),range.Address()));require((bool)range);
    stage("direct-document-handle-obtained");
    char line[160];
    if(variant==L"compare"){
      LegacyRange doc;check(TextPattern_get_DocumentRange(pattern.Get(),doc.Address()));require((bool)doc);
      int start=1;stage("legacy-compare-endpoints-before");
      method_hr=TextRange_CompareEndpoints(range.Get(),TextPatternRangeEndpoint_Start,doc.Get(),TextPatternRangeEndpoint_Start,&start);
      method_returned=true;snprintf(line,sizeof(line),"legacy-compare-endpoints-after hr=0x%08lX value=%d",(unsigned long)method_hr,start);stage(line);
      method_ok=method_hr==S_OK&&start==0;
    }else if(variant==L"clone"){
      LegacyRange copy;stage("legacy-clone-before");
      method_hr=TextRange_Clone(range.Get(),copy.Address());
      method_returned=true;snprintf(line,sizeof(line),"legacy-clone-after hr=0x%08lX non_null=%d",(unsigned long)method_hr,copy?1:0);stage(line);
      method_ok=method_hr==S_OK&&(bool)copy;
    }else if(variant==L"expand"){
      stage("legacy-expand-document-before");
      method_hr=TextRange_ExpandToEnclosingUnit(range.Get(),TextUnit_Document);
      method_returned=true;snprintf(line,sizeof(line),"legacy-expand-document-after hr=0x%08lX",(unsigned long)method_hr);stage(line);
      method_ok=method_hr==S_OK;
    }else{
      BSTR value=NULL;stage("legacy-direct-get-text-before");
      method_hr=TextRange_GetText(range.Get(),-1,&value);
      size_t length=value?SysStringLen(value):0;bool same_text=value&&std::wstring(value,length)==before;
      if(value)SysFreeString(value);
      method_returned=true;snprintf(line,sizeof(line),"legacy-direct-get-text-after hr=0x%08lX length=%llu",(unsigned long)method_hr,(unsigned long long)length);stage(line);
      method_ok=method_hr==S_OK&&same_text;
    }
    require(method_ok);
    require(document(pattern.Get())==before);
    BOOL focused=FALSE;check(page->get_CurrentHasKeyboardFocus(&focused));focus=focused!=FALSE;require(focus);
    passed=true;stage("all-direct-handle-assertions-passed");
  }catch(const Failure &f){error=f.hr;stage("HRESULT/assertion-failure");}
  catch(const std::exception &){error=E_FAIL;stage("standard-exception");}
  // /EHsc intentionally does not catch a native access violation or manufacture success.
  pattern.Reset();node.Reset();page.Reset();automation.Reset();
  if(process.hProcess){
    if(WaitForSingleObject(process.hProcess,0)==WAIT_TIMEOUT){
      if(windows.main)PostMessageW(windows.main,WM_CLOSE,0,0);
      if(WaitForSingleObject(process.hProcess,15000)==WAIT_TIMEOUT){TerminateProcess(process.hProcess,1);WaitForSingleObject(process.hProcess,15000);}
    }CloseHandle(process.hProcess);
  }
  if(initialized)CoUninitialize();
  std::string name(variant.begin(),variant.end());
  std::ofstream report(output/L"report.json");
  report<<std::boolalpha<<"{\"passed\":"<<passed<<",\"consumer\":\"native-legacy-direct-handle-control\",\"variant\":\""<<name
    <<"\",\"error_hresult\":"<<(unsigned long)error<<",\"method_returned\":"<<method_returned
    <<",\"method_hresult\":"<<(unsigned long)method_hr<<",\"method_ok\":"<<method_ok
    <<",\"page_focus_preserved\":"<<focus<<",\"handle_source\":\"direct-document-range\",\"selection_input_sent\":false}";
  return passed?0:1;
}
