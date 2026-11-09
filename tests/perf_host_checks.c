/* SPDX-License-Identifier: MIT */
/* Console regression of the real host's unchanged-setting and prepared-DIB paths. */
#define WinMain reader_WinMain
#include "../examples/reader.c"
#undef WinMain
#include <assert.h>
int main(void) {
  wchar_t directory[MAX_PATH],path[MAX_PATH],value[32];
  FILETIME stamp={123456789,123456},actual;
  HANDLE file; MSG message; host_job job={0};
  assert(GetTempPathW(MAX_PATH,directory) && GetTempFileNameW(directory,L"exr",0,path));
  settings_write(L"Host",L"FontPercent",L"100",path);
  file=CreateFileW(path,GENERIC_READ|FILE_WRITE_ATTRIBUTES,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_EXISTING,0,NULL);
  assert(file!=INVALID_HANDLE_VALUE && SetFileTime(file,NULL,NULL,&stamp));
  settings_write(L"Host",L"FontPercent",L"100",path);
  assert(GetFileTime(file,NULL,NULL,&actual) && !CompareFileTime(&actual,&stamp));
  CloseHandle(file);
  settings_write(L"Host",L"FontPercent",L"110",path);
  assert(GetPrivateProfileStringW(L"Host",L"FontPercent",L"",value,32,path)==3 && !wcscmp(value,L"110"));
  settings_write(L"Host",L"Empty",L"",path);
  assert(GetPrivateProfileStringW(L"Host",L"Empty",L"missing",value,32,path)==0);
  assert(DeleteFileW(path));

  g.window=CreateWindowExW(0,L"STATIC",L"",0,0,0,0,0,HWND_MESSAGE,NULL,GetModuleHandleW(NULL),NULL);
  assert(g.window);
  job.kind=JOB_GO;job.status=EXR_OK;job.frame.valid=1;job.frame.shell_geometry.enabled=1;
  job.frame.bitmap.width=job.frame.bitmap.height=2;
  job.frame.display_width=job.frame.display_height=2;
  job.frame.display_bitmap=CreateBitmap(2,2,1,32,NULL);assert(job.frame.display_bitmap);
  job_launch_pixels(&job);
  assert(!job.thread && PeekMessageW(&message,g.window,WM_HOST_COMPLETE,WM_HOST_COMPLETE,PM_REMOVE));
  assert((host_job *)message.lParam==&job);
  DeleteObject(job.frame.display_bitmap);DestroyWindow(g.window);g.window=NULL;
  puts("Host perf regressions: unchanged INI, changed INI, empty key, prepared DIB passed");
  return 0;
}
