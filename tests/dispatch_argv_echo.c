/* SPDX-License-Identifier: MIT */
#include <stdio.h>
#include <wchar.h>
#include <stdlib.h>
#include <windows.h>
static void echo_args(FILE *out,int argc,wchar_t **argv) {
  int i; size_t j;
  fputc('[',out);
  for (i=1;i<argc;i++) {
    if (i>1) fputc(',',out);
    fputc('"',out);
    for (j=0;argv[i][j];j++) fprintf(out,"\\u%04x",(unsigned)(unsigned short)argv[i][j]);
    fputc('"',out);
  }
  fputs("]\n",out);
}
int wmain(int argc, wchar_t **argv) {
  const wchar_t *record=_wgetenv(L"EXR_ECHO_ARGV");
  const wchar_t *meta=_wgetenv(L"EXR_ECHO_METADATA");
  const wchar_t *code=_wgetenv(L"EXR_ECHO_EXIT");
  if (meta) {
    FILE *f; DWORD_PTR mask,system_mask; STARTUPINFOW startup={0};
    Sleep(500); GetStartupInfoW(&startup);
    GetProcessAffinityMask(GetCurrentProcess(),&mask,&system_mask);
    f=_wfopen(meta,L"w");
    if (!f) return 3;
    fprintf(f,"{\"priority\":%lu,\"affinity\":%llu,\"startup_flags\":%lu,\"show_window\":%u,\"jobs\":\"%s\"}\n",
      GetPriorityClass(GetCurrentProcess()),(unsigned long long)mask,startup.dwFlags,startup.wShowWindow,getenv("CMAKE_BUILD_PARALLEL_LEVEL"));
    fclose(f);
  }
  if (record) {
    FILE *f=_wfopen(record,L"w");
    if (!f) return 4;
    echo_args(f,argc,argv); fclose(f);
    fputs("echo stderr sentinel\n",stderr);
  }
  echo_args(stdout,argc,argv);
  return code ? _wtoi(code) : 0;
}
