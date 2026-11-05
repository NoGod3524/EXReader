/* SPDX-License-Identifier: MIT */
#define _WIN32_WINNT 0x0601
#include <windows.h>
#include <commctrl.h>
#include "probe.h"
static exr_display_lease *reenter;
static int reentered;
static LRESULT CALLBACK proc(HWND w,UINT m,WPARAM a,LPARAM b) {
  if(m==WM_APP+7 && reenter) { exr_display_observation o=snapshot(reenter); reentered=(o.state==EXR_DISPLAY_OK && exr_display_cancel(reenter)==EXR_DISPLAY_OK); }
  return DefWindowProcW(w,m,a,b);
}
static void pump(unsigned ms) {
  ULONGLONG stop=GetTickCount64()+ms; MSG m;
  do { while(PeekMessageW(&m,NULL,0,0,PM_REMOVE)) { TranslateMessage(&m); DispatchMessageW(&m); } Sleep(5); } while(GetTickCount64()<stop);
}
static HWND window(const wchar_t *title) { return CreateWindowW(L"DisplayProbe",title,WS_OVERLAPPEDWINDOW,100,100,480,320,NULL,NULL,GetModuleHandleW(NULL),NULL); }
static void focus(HWND w) { ShowWindow(w,SW_RESTORE); SetForegroundWindow(w); SetActiveWindow(w); pump(150); }
static DWORD WINAPI wrong_thread(void *p) {
  exr_display_lease *l=p; exr_display_observation o={0}; o.struct_size=sizeof(o);
  return exr_display_set_active(l,1)==EXR_DISPLAY_WRONG_THREAD && exr_display_cancel(l)==EXR_DISPLAY_WRONG_THREAD && exr_display_observe(l,&o)==EXR_DISPLAY_WRONG_THREAD && exr_display_close(l)==EXR_DISPLAY_WRONG_THREAD;
}
int main(int argc,char **argv) {
  WNDCLASSW c={0}; HWND w,w2; exr_display_lease *l=NULL,*b=NULL; exr_display_observation a,z;
  exr_display_options opt; HANDLE th; DWORD code,flags; int child=argc>1 && !strcmp(argv[1],"--child");
  c.lpfnWndProc=proc; c.lpszClassName=L"DisplayProbe"; c.hInstance=GetModuleHandleW(NULL); RegisterClassW(&c);
  w=window(L"Display-only lease"); focus(w);
  opt.struct_size=sizeof(opt); opt.native_window=w; opt.reason="EXReader display-only acceptance"; opt.lease_ms=10000;
  if(child) {
    if(exr_display_create(&opt,&l)!=EXR_DISPLAY_OK || exr_display_set_active(l,1)!=EXR_DISPLAY_OK) return 9;
    printf("READY %llu\n",(unsigned long long)snapshot(l).native_identity); fflush(stdout); Sleep(INFINITE); return 0;
  }
  boundaries(w);
  result("create_native_window",w && exr_display_create(&opt,&l)==EXR_DISPLAY_OK);
  if(!l) return 1;
  result("enable_display_request",exr_display_set_active(l,1)==EXR_DISPLAY_OK);
  a=snapshot(l); result("real_handle_identity",a.native_identity && GetHandleInformation((HANDLE)(uintptr_t)a.native_identity,&flags));
  th=CreateThread(NULL,0,wrong_thread,l,0,NULL); WaitForSingleObject(th,3000); GetExitCodeThread(th,&code); CloseHandle(th);
  result("wrong_thread_no_mutation",code==1 && snapshot(l).native_identity==a.native_identity);
  result("second_lease",exr_display_create(&opt,&b)==EXR_DISPLAY_OK && exr_display_set_active(b,1)==EXR_DISPLAY_OK && snapshot(b).native_identity!=a.native_identity);
  exr_display_cancel(l); result("cancel_own_handle_only",!GetHandleInformation((HANDLE)(uintptr_t)a.native_identity,&flags) && snapshot(b).native_identity!=0);
  exr_display_close(b); b=NULL;
  result("retry_after_cancel",exr_display_set_active(l,1)==EXR_DISPLAY_OK);
  a=snapshot(l); ShowWindow(w,SW_MINIMIZE); pump(150); z=snapshot(l);
  result("minimize_releases",z.native_identity==0 && !GetHandleInformation((HANDLE)(uintptr_t)a.native_identity,&flags));
  focus(w); result("restore_reacquires",snapshot(l).state==EXR_DISPLAY_OK);
  ShowWindow(w,SW_HIDE); pump(80); result("hidden_releases",snapshot(l).native_identity==0);
  focus(w); w2=window(L"Other reading window"); focus(w2);
  result("window_switch_releases",snapshot(l).native_identity==0);
  opt.native_window=w2; result("second_window_acquires",exr_display_create(&opt,&b)==EXR_DISPLAY_OK && exr_display_set_active(b,1)==EXR_DISPLAY_OK);
  DestroyWindow(w2); result("destroy_releases",snapshot(b).state==EXR_DISPLAY_WINDOW_GONE && !snapshot(b).native_identity); exr_display_close(b);
  focus(w); exr_display_set_active(l,1); reenter=l; SendMessageW(w,WM_APP+7,0,0); reenter=NULL;
  result("native_callback_reentry",reentered && snapshot(l).state==EXR_DISPLAY_CANCELLED);
  exr_display_close(l); opt.native_window=w; opt.lease_ms=100;
  exr_display_create(&opt,&l); exr_display_set_active(l,1); pump(200);
  result("bounded_expiry",snapshot(l).state==EXR_DISPLAY_EXPIRED && !snapshot(l).native_identity);
  exr_display_close(l); DestroyWindow(w);
  /* Real invalid HWND is rejected before any native request is created. */
  result("destroyed_native_rejected",exr_display_create(&opt,&l)==EXR_DISPLAY_ARGUMENT && !l);
  unavailable("physical_screen_energy","Hosted Windows handle success is not physical-screen or battery evidence");
  return failures?1:0;
}
