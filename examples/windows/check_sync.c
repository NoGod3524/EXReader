/* SPDX-License-Identifier: MIT */
/* Console-only entry: reuse the production sync and storage paths without
   entering WinMain, creating an HWND, or loading a font/publication. */
#define WinMain reader_WinMain
#include "../reader.c"
#undef WinMain
#include <assert.h>
#include "check_shell_sync.inc"
#include "check_shell_privacy.inc"

int main(int argc,char **argv) {
  setvbuf(stdout, NULL, _IONBF, 0);
  SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
  host_offscreen = 1;
  if(argc==3 && !strcmp(argv[1],"--privacy-crash")) {
    wchar_t *path=host_wide(argv[2],strlen(argv[2]));assert(path);
    HANDLE file=CreateFileW(path,GENERIC_WRITE,0,NULL,CREATE_ALWAYS,0,NULL);assert(file!=INVALID_HANDLE_VALUE);
    DWORD wrote=0;assert(WriteFile(file,"partial",7,&wrote,NULL) && wrote==7 && FlushFileBuffers(file));
    ExitProcess(77);
  }
  if(argc==2 && !strcmp(argv[1],"--privacy")) {test_privacy();return 0;}
  /* shelf_load refreshes covers under the same lock as the native host. */
  InitializeCriticalSection(&g.library_lock);
  test_sync();
  assert(!g.window && !g.page);
  DeleteCriticalSection(&g.library_lock);
  puts("PASS sync: 15 scenarios; HWNDs created=0");
  return 0;
}
