/* SPDX-License-Identifier: MIT */
/* Host render + Direct2D/GDI present frame + first interactive selection path. */
#include <psapi.h>
static int budget_compare(const void *a,const void *b) {
  double x=*(const double *)a,y=*(const double *)b;return (x>y)-(x<y);
}
static void budget_present_frame(void) {
  if(!host_shell) {
    assert(SUCCEEDED(shell_d2d_create(g.window,&host_shell)));
    shell_dpi=96;
    shell_apply_theme();
  }
  shell_active=1;
  compose_page_view(g.page);
  InvalidateRect(g.page,NULL,FALSE);
  paint_page_view(g.page);
  InvalidateRect(g.window,NULL,FALSE);
  shell_paint(g.window);
  GdiFlush();
}
static void budget_prepare_book(const char *book,double *out_setup_ms,double *out_interactive_ms) {
  LARGE_INTEGER frequency,t0,t_setup,t_interactive;
  assert(QueryPerformanceFrequency(&frequency));
  QueryPerformanceCounter(&t0);
  if(!book) {
    prepare_layout(0);
    QueryPerformanceCounter(&t_setup);
    budget_present_frame();
    select_origin=select_focus=(exr_text_position){g.session.part,g.frame.range_start};
    select_valid=0;
    select_drive_key(VK_RIGHT,1,0);assert(select_valid && g.selection.active);
    budget_present_frame();
    select_drive_key(VK_ESCAPE,0,0);assert(!g.selection.active);
    QueryPerformanceCounter(&t_interactive);
    *out_setup_ms=1000.0*(double)(t_setup.QuadPart-t0.QuadPart)/(double)frequency.QuadPart;
    *out_interactive_ms=1000.0*(double)(t_interactive.QuadPart-t0.QuadPart)/(double)frequency.QuadPart;
    puts("BUDGET load_path=fixture-document");
    return;
  }
  /* Match the production EPUB path. Whole-document open is a different API
     with a global document cap and previously rejected the fixed pg10 book. */
  const char *part_path=getenv("EXR_BUDGET_PART_PATH");assert(part_path && *part_path);
  frame_clear(&g.frame);session_clear(&g.session);
  ok(exr_library_open(":memory:",&g.library,NULL),NULL);
  host_job job={0};wchar_t *wide=host_wide(book,strlen(book));assert(wide);
  copy_wstring(job.path,HOST_PATH,wide);free(wide);
  int created=0;int64_t id=0;exr_error error={0};
  ok(import_bounded_epub(&job,&id,&created,&error),&error);assert(created);
  exr_library_epub_info info={sizeof(info),0,0};
  ok(exr_library_epub_info_get(g.library,id,&info,&error),&error);assert(info.bounded_storage);
  exr_source source={0};ok(exr_library_source(g.library,id,&source,&error),&error);
  assert(shell_epub_source(&source));
  exr_status status=exr_publication_open_source(&source,&g.session.publication,&error);
  if(status!=EXR_OK && source.release)source.release(source.context);
  ok(status,&error);
  size_t count=0;const exr_part *parts=exr_publication_parts(g.session.publication,&count);
  size_t part=0;while(part<count && strcmp(parts[part].path,part_path))part++;
  assert(part<count);
  g.session.active=g.session.bounded=1;g.session.book_id=id;g.session.part=part;
  g.session.config=exr_layout_config_defaults();
  g.session.config.page=(exr_layout_options){260,160,0,14,1.5f,0};
  g.session.config.user_css="p{margin:0;padding:0;hyphens:auto}";
  g.session.shell_geometry=(shell_geometry){1,260,160,0,96,14,{14,1.5f,0,0,0,0,0,0}};
  ok(bounded_pager(&g.session,part,&g.session.pager,&error),&error);
  load_frame(0);g.frame.part=part;
  QueryPerformanceCounter(&t_setup);
  uint64_t presents_before=shell_d2d_present_count(host_shell);
  budget_present_frame();
  select_origin=select_focus=(exr_text_position){part,g.frame.range_start};
  select_valid=0;
  select_drive_key(VK_RIGHT,1,0);assert(select_valid && g.selection.active);
  budget_present_frame();
  select_drive_key(VK_ESCAPE,0,0);assert(!g.selection.active);
  QueryPerformanceCounter(&t_interactive);
  assert(shell_d2d_present_count(host_shell)>=presents_before+2);
  *out_setup_ms=1000.0*(double)(t_setup.QuadPart-t0.QuadPart)/(double)frequency.QuadPart;
  *out_interactive_ms=1000.0*(double)(t_interactive.QuadPart-t0.QuadPart)/(double)frequency.QuadPart;
  printf("BUDGET load_path=production-bounded-epub part=%zu part_path=%s\n",part,parts[part].path);
}
static void test_render_budget(void) {
  const char *book=getenv("EXR_AUDIT_BOOK");
  LARGE_INTEGER frequency,start,end,pstart,pend;assert(QueryPerformanceFrequency(&frequency));
  double p95[2]={0},present_p95[2]={0},memory[2]={0};
  int cohorts=getenv("EXR_BUDGET_SINGLE_PROCESS") ? 1 : 2;
  for(int cohort=0;cohort<cohorts;cohort++) {
    double samples[64],present_samples[64],setup_ms=0,interactive_ms=0;
    budget_prepare_book(book,&setup_ms,&interactive_ms); /* same book, font, geometry and 0/1 page workload */
    printf("BUDGET setup_render_ready_ms=%.6f first_interactive_ms=%.6f d2d_present_count=%llu\n",
      setup_ms,interactive_ms,(unsigned long long)shell_d2d_present_count(host_shell));
    for(int i=0;i<8;i++) { load_frame((size_t)(i%2)); budget_present_frame(); }
    for(int i=0;i<64;i++) {
      uint64_t before_presents=shell_d2d_present_count(host_shell);
      QueryPerformanceCounter(&start);load_frame((size_t)(i%2));QueryPerformanceCounter(&end);
      samples[i]=1000.0*(double)(end.QuadPart-start.QuadPart)/(double)frequency.QuadPart;
      assert(g.frame.valid && g.frame.bitmap.pixels);
      QueryPerformanceCounter(&pstart);budget_present_frame();QueryPerformanceCounter(&pend);
      present_samples[i]=1000.0*(double)(pend.QuadPart-pstart.QuadPart)/(double)frequency.QuadPart;
      assert(shell_d2d_present_count(host_shell)>before_presents);
    }
    printf("BUDGET raw_render_ms=[");
    for(int i=0;i<64;i++)printf("%s%.6f",i ? "," : "",samples[i]);
    puts("]");
    printf("BUDGET raw_present_ms=[");
    for(int i=0;i<64;i++)printf("%s%.6f",i ? "," : "",present_samples[i]);
    puts("]");
    qsort(samples,64,sizeof(double),budget_compare);p95[cohort]=samples[60];
    qsort(present_samples,64,sizeof(double),budget_compare);present_p95[cohort]=present_samples[60];
    PROCESS_MEMORY_COUNTERS counters={0};counters.cb=sizeof(counters);
    assert(GetProcessMemoryInfo(GetCurrentProcess(),&counters,sizeof(counters)));
    memory[cohort]=(double)counters.PeakWorkingSetSize;
    printf("BUDGET cohort=%d n=64 render_p50_ms=%.6f render_p95_ms=%.6f present_p50_ms=%.6f present_p95_ms=%.6f d2d_last_present_ms=%.6f peak_working_set_bytes=%.0f\n",
      cohort,(samples[31]+samples[32])/2,p95[cohort],(present_samples[31]+present_samples[32])/2,present_p95[cohort],
      shell_d2d_last_present_ms(host_shell),memory[cohort]);
    if(book) { frame_clear(&g.frame);session_clear(&g.session);exr_library_close(g.library);g.library=NULL; }
  }
  assert(p95[0]>0 && present_p95[0]>0 && memory[0]>0);
  if(cohorts==1)return; /* Fresh-process comparisons are made by render_budget.py. */
  printf("BUDGET same_process_repeat_p95_ratio=%.6f present_repeat_p95_ratio=%.6f limit=2.5 peak_ratio=%.6f limit=1.25; present_frame=measured first_interactive=measured\n",
    p95[1]/p95[0],present_p95[1]/present_p95[0],memory[1]/memory[0]);
  assert(p95[1]/p95[0]<2.5 && present_p95[1]/present_p95[0]<2.5 && memory[1]/memory[0]<1.25);
}
