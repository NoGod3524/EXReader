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

static LONG host_probe_layout_calls;
static int host_probe_burst_left;
#define HOST_PROBE_BURST_TIMER 0x7e91
static exr_status host_probe_pager_get(exr_pager *pager,size_t page,const exr_layout **layout,exr_error *error) {
  InterlockedIncrement(&host_probe_layout_calls);return exr_pager_get(pager,page,layout,error);
}
#define exr_pager_get host_probe_pager_get
/* Record completed GDI submission; do not wait for the compositor here,
   because doing so changes paint coalescing in the baseline being measured. */
static void host_probe_present(double generation) {
  if(GetEnvironmentVariableW(L"EXR_PAINT_TRACE",NULL,0)) {
    GdiFlush();host_probe_log("present_gen",generation);
  }
}

/* Opt-in visual stamp: synchronization byte, generation, and its complement.
   Decoder rejects torn stamps; normal product UI never enables this marker. */
static void host_probe_stamp(HDC dc,const RECT *area,unsigned long generation) {
  if(!GetEnvironmentVariableW(L"EXR_PAINT_MARKER",NULL,0))return;
  uint64_t g16=generation&0xffffu;
  uint64_t code=((uint64_t)0xa5<<32)|(g16<<16)|((~g16)&0xffffu);
  int left=area->right/2-80,top=area->bottom/2-4;
  RECT band={left,top,left+160,top+8};FillRect(dc,&band,(HBRUSH)GetStockObject(WHITE_BRUSH));
  for(int i=0;i<40;i++)if(code&((uint64_t)1<<(39-i))) {
    RECT bit={left+i*4,top,left+(i+1)*4,top+8};FillRect(dc,&bit,(HBRUSH)GetStockObject(BLACK_BRUSH));
  }
}
