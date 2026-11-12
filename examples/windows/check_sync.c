/* SPDX-License-Identifier: MIT */
/* Console-only entry: production synchronous sync and disk loaders, no HWND. */
#define UNICODE
#define _UNICODE
#define WIN32_LEAN_AND_MEAN
#define _WIN32_WINNT 0x0602
#include <winsock2.h>
#include <windows.h>
#include <assert.h>
#include <stdlib.h>
/* A future accidental window creation fails the acceptance immediately. */
static inline HWND no_window(DWORD ex, LPCWSTR cls, LPCWSTR title, DWORD style,
    int x, int y, int w, int h, HWND parent, HMENU menu, HINSTANCE instance, LPVOID arg) {
  (void)ex; (void)cls; (void)title; (void)style; (void)x; (void)y; (void)w; (void)h;
  (void)parent; (void)menu; (void)instance; (void)arg;
  abort();
}
#define CreateWindowExW no_window
#define WinMain reader_WinMain
#include "../reader.c"
#undef WinMain
#include "check_shell_sync.inc"
int main(void) {
  SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
  setvbuf(stdout, NULL, _IONBF, 0);
  host_offscreen = 1;
  InitializeCriticalSection(&g.library_lock);
  test_sync();
  assert(!g.window && !g.page);
  DeleteCriticalSection(&g.library_lock);
  printf("PASS %d/15 WebDAV scenarios; HWND=0\n", syt_scenarios);
  return 0;
}
