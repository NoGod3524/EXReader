#include <stdio.h>
/* Opt-in host-only measurement; no SDK behavior changes. */
static double host_probe_ms(void) { LARGE_INTEGER t,f; QueryPerformanceCounter(&t); QueryPerformanceFrequency(&f); return 1000.0*t.QuadPart/f.QuadPart; }
static void host_probe_log(const char *event,double value) {
  wchar_t path[4096]; static SRWLOCK lock=SRWLOCK_INIT;
  if(!GetEnvironmentVariableW(L"EXR_PAINT_TRACE",path,4096))return;
  AcquireSRWLockExclusive(&lock);
  FILE *f=_wfopen(path,L"ab"); if(f){fprintf(f,"%s,%.6f,%.6f\n",event,host_probe_ms(),value);fclose(f);}
  ReleaseSRWLockExclusive(&lock);
}
static exr_status host_probe_render(const exr_layout *layout, const exr_control *control, exr_bitmap *out, exr_error *error, uint32_t background) {
  static LONG measured; int count=1; exr_status status=EXR_OK;
  if(GetEnvironmentVariableW(L"EXR_PAINT_REPEAT",NULL,0) && InterlockedCompareExchange(&measured,1,0)==0)count=20;
  for(int i=0;i<count;i++) {
    double start=host_probe_ms();
    status=exr_render_page_background(layout,exr_layout_font(layout),0,4,background,control,out,error);
    host_probe_log(count==20?"repeat_render_ms":"render_ms",host_probe_ms()-start);
    if(status!=EXR_OK)break;
    if(i+1<count)exr_bitmap_free(out);
  }
  return status;
}
