/* SPDX-License-Identifier: MIT */
#define _WIN32_WINNT 0x0601
#include <windows.h>
#include <commctrl.h>
#include <stdlib.h>
#include <string.h>
#include "common.h"
struct exr_display_lease {
  DWORD owner;
  HWND window;
  HANDLE request;
  WCHAR reason[257];
  uint32_t duration, error;
  uint64_t generation, deadline;
  exr_display_status state;
  int wanted, busy;
};
static volatile LONG count;
static exr_display_status enter(exr_display_lease *l) {
  if(!l) return EXR_DISPLAY_ARGUMENT;
  if(l->owner!=GetCurrentThreadId()) return EXR_DISPLAY_WRONG_THREAD;
  if(l->busy) return EXR_DISPLAY_REENTRANT;
  l->busy=1; return EXR_DISPLAY_OK;
}
static void release(exr_display_lease *l) {
  if(l->request) {
    if(!PowerClearRequest(l->request,PowerRequestDisplayRequired)) l->error=GetLastError();
    CloseHandle(l->request); l->request=NULL;
  }
}
static int eligible(exr_display_lease *l) {
  return l->window && IsWindow(l->window) && IsWindowVisible(l->window) &&
    !IsIconic(l->window) && GetForegroundWindow()==l->window;
}
static void revoke(exr_display_lease *l, exr_display_status s) {
  release(l); ++l->generation; l->state=s;
}
static void refresh(exr_display_lease *l) {
  REASON_CONTEXT r;
  if(!l->window) { if(l->state!=EXR_DISPLAY_WINDOW_GONE) revoke(l,EXR_DISPLAY_WINDOW_GONE); return; }
  if(!l->wanted) return;
  if(GetTickCount64()>=l->deadline) { l->wanted=0; revoke(l,EXR_DISPLAY_EXPIRED); return; }
  if(!eligible(l)) { if(l->request) revoke(l,EXR_DISPLAY_INACTIVE); return; }
  if(l->request || l->state==EXR_DISPLAY_UNAVAILABLE) return;
  ZeroMemory(&r,sizeof(r)); r.Version=POWER_REQUEST_CONTEXT_VERSION;
  r.Flags=POWER_REQUEST_CONTEXT_SIMPLE_STRING; r.Reason.SimpleReasonString=l->reason;
  l->request=PowerCreateRequest(&r);
  if(l->request==INVALID_HANDLE_VALUE) { l->request=NULL; l->error=GetLastError(); l->state=EXR_DISPLAY_UNAVAILABLE; return; }
  if(!PowerSetRequest(l->request,PowerRequestDisplayRequired)) {
    l->error=GetLastError(); CloseHandle(l->request); l->request=NULL; l->state=EXR_DISPLAY_UNAVAILABLE; return;
  }
  l->state=EXR_DISPLAY_OK; l->error=0;
}
static LRESULT CALLBACK dispatch(HWND w,UINT m,WPARAM a,LPARAM b,UINT_PTR id,DWORD_PTR data) {
  exr_display_lease *l=(exr_display_lease *)data;
  if(m==WM_DESTROY || m==WM_NCDESTROY) {
    revoke(l,EXR_DISPLAY_WINDOW_GONE); l->wanted=0;
    KillTimer(w,id); RemoveWindowSubclass(w,dispatch,id); l->window=NULL;
  } else if((m==WM_SHOWWINDOW && !a) || (m==WM_SIZE && a==SIZE_MINIMIZED) || (m==WM_ACTIVATE && LOWORD(a)==WA_INACTIVE)) {
    if(l->request) revoke(l,EXR_DISPLAY_INACTIVE);
  } else if(m==WM_TIMER && a==id && !l->busy) refresh(l);
  return DefSubclassProc(w,m,a,b);
}
exr_display_status exr_display_create(const exr_display_options *o,exr_display_lease **out) {
  exr_display_lease *l; DWORD tid;
  if(!out) return EXR_DISPLAY_ARGUMENT; *out=NULL;
  if(!exr_display_valid_options(o) || !IsWindow((HWND)o->native_window) || GetAncestor((HWND)o->native_window,GA_ROOT)!=(HWND)o->native_window) return EXR_DISPLAY_ARGUMENT;
  tid=GetWindowThreadProcessId((HWND)o->native_window,NULL);
  if(tid!=GetCurrentThreadId()) return EXR_DISPLAY_WRONG_THREAD;
  if(InterlockedIncrement(&count)>EXR_DISPLAY_MAX_LEASES) { InterlockedDecrement(&count); return EXR_DISPLAY_LIMIT; }
  l=(exr_display_lease *)calloc(1,sizeof(*l));
  if(!l) { InterlockedDecrement(&count); return EXR_DISPLAY_NO_MEMORY; }
  l->owner=tid; l->window=(HWND)o->native_window; l->duration=o->lease_ms; l->generation=1; l->state=EXR_DISPLAY_INACTIVE;
  MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,o->reason,-1,l->reason,257);
  if(!SetWindowSubclass(l->window,dispatch,(UINT_PTR)l,(DWORD_PTR)l) || !SetTimer(l->window,(UINT_PTR)l,50,NULL)) {
    RemoveWindowSubclass(l->window,dispatch,(UINT_PTR)l); free(l); InterlockedDecrement(&count); return EXR_DISPLAY_UNAVAILABLE;
  }
  *out=l; return EXR_DISPLAY_OK;
}
exr_display_status exr_display_set_active(exr_display_lease *l,int active) {
  exr_display_status s;
  if(active!=0 && active!=1) return EXR_DISPLAY_ARGUMENT;
  s=enter(l); if(s) return s;
  if(!l->window) { l->busy=0; return EXR_DISPLAY_WINDOW_GONE; }
  l->wanted=active; l->deadline=active?GetTickCount64()+l->duration:0;
  if(!active) revoke(l,EXR_DISPLAY_INACTIVE);
  else { if(l->state!=EXR_DISPLAY_OK) l->state=EXR_DISPLAY_INACTIVE; refresh(l); }
  s=l->state; l->busy=0; return s;
}
exr_display_status exr_display_cancel(exr_display_lease *l) {
  exr_display_status s=enter(l); if(s) return s;
  l->wanted=0; l->deadline=0; revoke(l,EXR_DISPLAY_CANCELLED); l->busy=0; return EXR_DISPLAY_OK;
}
exr_display_status exr_display_observe(exr_display_lease *l,exr_display_observation *o) {
  exr_display_status s;
  if(!o || o->struct_size!=sizeof(*o)) return EXR_DISPLAY_ARGUMENT;
  s=enter(l); if(s) return s; refresh(l);
  o->state=l->state; o->generation=l->generation; o->native_identity=(uint64_t)(uintptr_t)l->request;
  o->expires_at_ms=l->deadline; o->native_error=l->error; o->requested=l->wanted; o->pending=0; o->window_alive=l->window!=NULL;
  l->busy=0; return EXR_DISPLAY_OK;
}
exr_display_status exr_display_close(exr_display_lease *l) {
  exr_display_status s; if(!l) return EXR_DISPLAY_OK; s=enter(l); if(s) return s;
  release(l);
  if(l->window) { KillTimer(l->window,(UINT_PTR)l); RemoveWindowSubclass(l->window,dispatch,(UINT_PTR)l); }
  free(l); InterlockedDecrement(&count); return EXR_DISPLAY_OK;
}
