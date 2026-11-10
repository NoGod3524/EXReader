/* SPDX-License-Identifier: MIT */
/* Console-only driver: reuse the host's sync API and acceptance assertions.
   reader_WinMain is compiled for linkage, but never called. No HWND is created. */
#define WinMain reader_WinMain
#include "../reader.c"
#undef WinMain
#include <assert.h>
#include "check_shell_sync.inc"

int main(void) {
  setvbuf(stdout, NULL, _IONBF, 0);
  SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
  host_offscreen = 1;
  InitializeCriticalSection(&g.library_lock);
  assert(!g.window && !g.page);
  test_sync();
  assert(!g.window && !g.page);
  DeleteCriticalSection(&g.library_lock);
  puts("PASS WebDAV 15 scenarios; windows_created=0");
  return 0;
}
