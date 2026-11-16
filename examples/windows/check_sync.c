/* SPDX-License-Identifier: MIT */
/* Console-only entry: reuse the production sync and storage paths without
   entering WinMain, creating an HWND, or loading a font/publication. */
#define WinMain reader_WinMain
#define EXR_READER_SYNC_TEST_DRIVERS 1
#include "../reader.c"
#undef WinMain
#include <assert.h>
#include "check_shell_sync.inc"
#include "check_shell_privacy.inc"
#include "check_shell_f10_identity.inc"

int main(int argc,char **argv) {
  setvbuf(stdout, NULL, _IONBF, 0);
  SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
  host_offscreen = 1;
  if(argc==4 && !strcmp(argv[1],"--privacy-credential-crash")) {
    wchar_t *root=host_wide(argv[2],strlen(argv[2])),*event=host_wide(argv[3],strlen(argv[3]));assert(root && event);
    wcscpy(g.data_dir,root);sy_default_paths();
    sy_test_after_flush_event=OpenEventW(EVENT_MODIFY_STATE,FALSE,event);assert(sy_test_after_flush_event);
    /* The parent force-terminates after the production writer flushes. */
    assert(sy_cred_save("interrupted-user","interrupted-password"));return 1;
  }
  if(argc==3 && !strcmp(argv[1],"--privacy-crash")) {
    wchar_t *path=host_wide(argv[2],strlen(argv[2]));assert(path);
    HANDLE file=CreateFileW(path,GENERIC_WRITE,0,NULL,CREATE_ALWAYS,0,NULL);assert(file!=INVALID_HANDLE_VALUE);
    DWORD wrote=0;assert(WriteFile(file,"partial",7,&wrote,NULL) && wrote==7 && FlushFileBuffers(file));
    ExitProcess(77);
  }
  if(argc==2 && !strcmp(argv[1],"--privacy")) {test_privacy();return 0;}
  if(argc==3 && !strcmp(argv[1],"--f10-unavailable")) return test_f10_unavailable(argv[2]);
  if(argc==2 && !strcmp(argv[1],"--f10-cross-user")) return test_f10_cross_user();
  if(argc==2 && !strcmp(argv[1],"--f10-public-tls")) return test_f10_public_tls();
  if(argc>2 && !strcmp(argv[1],"--f10-tls")) return test_f10_tls(argc-2,argv+2);
  /* shelf_load refreshes covers under the same lock as the native host. */
  InitializeCriticalSection(&g.library_lock);
  test_sync();
  assert(!g.window && !g.page);
  DeleteCriticalSection(&g.library_lock);
  puts("PASS sync: 15 scenarios; HWNDs created=0");
  return 0;
}
