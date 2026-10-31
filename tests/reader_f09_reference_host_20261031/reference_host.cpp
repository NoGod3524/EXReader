// SPDX-License-Identifier: MIT
// Test-only reference host: a Microsoft RichEdit control as the page (control ID 123) with fixed
// non-book text, so the frozen consumers can drive a Microsoft text provider exactly like EXReader.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <richedit.h>
#include <string>
static LRESULT CALLBACK window_proc(HWND hwnd,UINT message,WPARAM wparam,LPARAM lparam){
  switch(message){
    case WM_SIZE:{HWND page=GetDlgItem(hwnd,123);if(page)MoveWindow(page,0,0,LOWORD(lparam),HIWORD(lparam),TRUE);return 0;}
    case WM_DESTROY:PostQuitMessage(0);return 0;
  }
  return DefWindowProcW(hwnd,message,wparam,lparam);
}
int WINAPI wWinMain(HINSTANCE instance,HINSTANCE,PWSTR,int){
  // The consumers pass --data and a book path; this host ignores its arguments.
  if(!LoadLibraryW(L"Msftedit.dll"))return 3;
  WNDCLASSW type={};type.lpfnWndProc=window_proc;type.hInstance=instance;
  type.lpszClassName=L"F09ReferenceHost";type.hCursor=LoadCursor(NULL,IDC_ARROW);
  if(!RegisterClassW(&type))return 4;
  HWND main=CreateWindowExW(0,type.lpszClassName,L"F09 reference RichEdit",WS_OVERLAPPEDWINDOW|WS_VISIBLE,
    0,0,1000,700,NULL,NULL,instance,NULL);
  if(!main)return 5;
  RECT client;GetClientRect(main,&client);
  HWND page=CreateWindowExW(0,MSFTEDIT_CLASS,L"",WS_CHILD|WS_VISIBLE|WS_TABSTOP|ES_MULTILINE|ES_READONLY,
    0,0,client.right,client.bottom,main,(HMENU)(INT_PTR)123,instance,NULL);
  if(!page)return 6;
  std::wstring text;
  for(int i=0;i<5;i++)text+=L"F09 reference RichEdit text for UI Automation comparison. ";
  if(!SetWindowTextW(page,text.c_str()))return 7;
  SetFocus(page);
  MSG message;
  while(GetMessageW(&message,NULL,0,0)>0){TranslateMessage(&message);DispatchMessageW(&message);}
  return 0;
}
