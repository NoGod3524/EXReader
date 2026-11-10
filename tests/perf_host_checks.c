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

  assert(SetEnvironmentVariableW(L"EXREADER_SHELF_PATH",path));
  FILE *shelf=_wfopen(path,L"wb");assert(shelf);
  fputs("{\"sentinel\":\"keep\"}",shelf);assert(!fclose(shelf));
  shell_style=exr_reader_style_defaults();shell_font=shell_style.font_size;
  assert(shell_style_save());
  file=CreateFileW(path,GENERIC_READ|FILE_WRITE_ATTRIBUTES,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_EXISTING,0,NULL);
  assert(file!=INVALID_HANDLE_VALUE && SetFileTime(file,NULL,NULL,&stamp));
  assert(shell_style_save());
  assert(GetFileTime(file,NULL,NULL,&actual) && !CompareFileTime(&actual,&stamp));
  CloseHandle(file);
  shell_font+=1;assert(shell_style_save());
  int ok;exr_reader_style restored;cv_json *root=style_shelf_read(&ok);
  assert(ok && style_read(cv_json_get(cv_json_get(root,"settings"),"reader_style"),&restored));
  assert(restored.font_size==shell_font && !strcmp(cv_json_get(root,"sentinel")->string,"keep"));
  cv_json_free(root);assert(DeleteFileW(path));assert(SetEnvironmentVariableW(L"EXREADER_SHELF_PATH",NULL));

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

  host_frame frame={0};BITMAPINFO info={0};uint32_t source[257],*pixels=NULL;
  info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);info.bmiHeader.biWidth=257;info.bmiHeader.biHeight=-1;
  info.bmiHeader.biPlanes=1;info.bmiHeader.biBitCount=32;info.bmiHeader.biCompression=BI_RGB;
  frame.display_bitmap=CreateDIBSection(NULL,&info,DIB_RGB_COLORS,(void **)&pixels,NULL,0);assert(frame.display_bitmap && pixels);
  frame.valid=1;frame.shell_geometry.enabled=1;frame.bitmap.width=frame.display_width=257;
  frame.bitmap.height=frame.display_height=1;frame.dib=source;
  g.page=CreateWindowExW(0,L"STATIC",L"",0,0,0,257,1,HWND_MESSAGE,NULL,GetModuleHandleW(NULL),NULL);assert(g.page);
  for(int dark=0;dark<2;dark++) for(int paper=0;paper<2;paper++) {
    shell_theme_mode=dark;shell_colors=dark ? &shell_theme_dark : &shell_theme_light;
    for(unsigned i=0;i<256;i++) source[i]=paper ? 0xff876543 : 0xff000000|i|(i<<8)|(i<<16);
    source[256]=0xff123456;frame.display_shell_theme=0;
    shell_color_display(&frame);
    assert(frame.display_shell_paper==paper && pixels[256]==source[256]);
    for(unsigned i=0;i<256;i++) assert(pixels[i]==(paper ? source[i] : shell_blend(shell_colors->text,shell_colors->layer_page,i/255.f)));
  }
  DeleteObject(frame.display_bitmap);
  DestroyWindow(g.page);g.page=NULL;
  puts("Host perf regressions: INI/shelf persistence, unrelated keys, prepared DIB, all 256 shades/light/dark/colored paper passed");
  return 0;
}
