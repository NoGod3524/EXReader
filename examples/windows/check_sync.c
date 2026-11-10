/* SPDX-License-Identifier: MIT */
/* Console-only entry: reuse the production sync and storage paths without
   entering WinMain, creating an HWND, or loading a font/publication. */
#define WinMain reader_WinMain
#include "../reader.c"
#undef WinMain
#include <assert.h>
#include "check_shell_sync.inc"

int main(void) {
  setvbuf(stdout, NULL, _IONBF, 0);
  SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
  host_offscreen = 1;
  test_sync();
  assert(!g.window && !g.page);
  puts("PASS sync: 15 scenarios; HWNDs created=0");
  return 0;
}
