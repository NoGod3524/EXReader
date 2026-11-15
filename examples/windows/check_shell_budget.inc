/* SPDX-License-Identifier: MIT */
/* Host render path only: no display-present or first-interactive claim. */
#include <psapi.h>
static int budget_compare(const void *a,const void *b) {
  double x=*(const double *)a,y=*(const double *)b;return (x>y)-(x<y);
}
static void test_render_budget(void) {
  const char *book=getenv("EXR_AUDIT_BOOK");
  if(book) snprintf(fixture_path,sizeof(fixture_path),"%s",book);
  LARGE_INTEGER frequency,start,end;assert(QueryPerformanceFrequency(&frequency));
  double p95[2],memory[2];
  for(int cohort=0;cohort<2;cohort++) {
    double samples[64];
    prepare_layout(0); /* same book, font, geometry and 0/1 page workload */
    for(int i=0;i<8;i++) load_frame((size_t)(i%2));
    for(int i=0;i<64;i++) {
      QueryPerformanceCounter(&start);load_frame((size_t)(i%2));QueryPerformanceCounter(&end);
      samples[i]=1000.0*(double)(end.QuadPart-start.QuadPart)/(double)frequency.QuadPart;
      assert(g.frame.valid && g.frame.bitmap.pixels);
    }
    qsort(samples,64,sizeof(double),budget_compare);p95[cohort]=samples[60];
    PROCESS_MEMORY_COUNTERS counters={0};counters.cb=sizeof(counters);
    assert(GetProcessMemoryInfo(GetCurrentProcess(),&counters,sizeof(counters)));
    memory[cohort]=(double)counters.PeakWorkingSetSize;
    printf("BUDGET cohort=%d n=64 render_p50_ms=%.6f render_p95_ms=%.6f peak_working_set_bytes=%.0f\n",
      cohort,(samples[31]+samples[32])/2,p95[cohort],memory[cohort]);
  }
  assert(p95[0]>0 && memory[0]>0);
  printf("BUDGET same_process_repeat_p95_ratio=%.6f limit=2.5 peak_ratio=%.6f limit=1.25; present_frame=missing first_interactive=missing\n",
    p95[1]/p95[0],memory[1]/memory[0]);
  assert(p95[1]/p95[0]<2.5 && memory[1]/memory[0]<1.25);
}
