/* SPDX-License-Identifier: MIT */
/* F08 fixed-scale shelf workload: 2202 originals in an on-disk library (the
   GTK corpus scale), the production shelf load (reload_shelf -> sm_refresh),
   the first painted custom-drawn shelf view and a real keyboard move, then
   one repaint per keyboard move through the books in grid and list mode.
   Budgets are the fixed product budgets of render-corpus.json. Each sample
   is QPC around SendMessage(WM_KEYDOWN) -> sm_key_move -> sm_key_reveal ->
   UpdateWindow (a complete GDI repaint of the view) + GdiFlush. */
#include <psapi.h>
#define SHELF_BUDGET_BOOKS 2202
static double shelf_budget_ms(LARGE_INTEGER a,LARGE_INTEGER b,LARGE_INTEGER f) {
  return 1000.0*(double)(b.QuadPart-a.QuadPart)/(double)f.QuadPart;
}
static int shelf_budget_cmp(const void *a,const void *b) {
  double x=*(const double *)a,y=*(const double *)b;return (x>y)-(x<y);
}
static void shelf_budget_key(WPARAM key,int shift) {
  BYTE keys[256];GetKeyboardState(keys);keys[VK_SHIFT]=shift ? 0x80:0;SetKeyboardState(keys);
  SendMessageW(sm_view,WM_KEYDOWN,key,0);GdiFlush();
  keys[VK_SHIFT]=0;SetKeyboardState(keys);
}
static void shelf_budget_series(const char *name,double *samples,int count) {
  printf("SHELF-BUDGET raw_%s_ms=[",name);
  for(int i=0;i<count;i++) printf("%s%.6f",i ? ",":"",samples[i]);
  puts("]");
}
static void test_shelf_budget(void) {
  LARGE_INTEGER f,t0,t1,t2,t3,a,b;assert(QueryPerformanceFrequency(&f));
  wchar_t temp[HOST_PATH],database_w[HOST_PATH],shelf_json[HOST_PATH];GetTempPathW(HOST_PATH,temp);
  swprintf(database_w,HOST_PATH,L"%lsexreader-shelf-budget-%lu.sqlite",temp,(unsigned long)GetCurrentProcessId());
  swprintf(shelf_json,HOST_PATH,L"%lsexreader-shelf-budget-%lu.json",temp,(unsigned long)GetCurrentProcessId());
  DeleteFileW(database_w);DeleteFileW(shelf_json);SetEnvironmentVariableW(L"EXREADER_SHELF_PATH",shelf_json);
  char *database=host_utf8(database_w);assert(database);
  /* Fixed corpus, written once through the public SDK (not timed). */
  ok(exr_library_open(database,&g.library,NULL),NULL);
  QueryPerformanceCounter(&a);
  for(int i=0;i<SHELF_BUDGET_BOOKS;i++) {
    char title[32],body[200];int64_t id=0;
    snprintf(title,sizeof(title),"Shelf %04d",i);
    snprintf(body,sizeof(body),"Shelf original %04d. A fixed-scale shelf book; read it and return to the same shelf position.\n",i);
    ok(exr_library_import(g.library,EXR_TXT,body,strlen(body),title,&id,NULL),NULL);
  }
  QueryPerformanceCounter(&b);
  exr_library_close(g.library);g.library=NULL;
  printf("SHELF-BUDGET corpus books=%d import_setup_ms=%.3f (not budgeted)\n",SHELF_BUDGET_BOOKS,shelf_budget_ms(a,b,f));
  /* Cold product path: open the on-disk library and load the shelf. */
  QueryPerformanceCounter(&t0);
  ok(exr_library_open(database,&g.library,NULL),NULL);
  assert(reload_shelf()==EXR_OK && g.shelf_count==SHELF_BUDGET_BOOKS);
  QueryPerformanceCounter(&t1);
  WNDCLASSW type={0};type.lpfnWndProc=sm_view_procedure;type.hInstance=GetModuleHandleW(NULL);
  type.lpszClassName=L"EXReaderShelfMetaBudget";RegisterClassW(&type);
  HWND host=CreateWindowExW(WS_EX_NOACTIVATE,L"STATIC",L"",WS_POPUP|WS_VISIBLE,-32000,-32000,1280,800,NULL,NULL,NULL,NULL);assert(host);
  sm_view=CreateWindowExW(0,type.lpszClassName,L"系列、标签与阅读统计",WS_CHILD|WS_VISIBLE|WS_TABSTOP|WS_VSCROLL,0,0,1280,800,host,NULL,NULL,NULL);
  assert(sm_view);sm_mode=0;sm_list=0;sm_filter=-1;sm_scroll=0;sm_key_kind=sm_key_arg=0;
  RedrawWindow(sm_view,NULL,NULL,RDW_INVALIDATE|RDW_UPDATENOW);GdiFlush();
  QueryPerformanceCounter(&t2);
  shelf_budget_key(VK_TAB,0);assert(sm_key_index()>=0);
  QueryPerformanceCounter(&t3);
  int books=0;for(int i=0;i<sm_hit_count;i++) books+=sm_hits[i].kind==SM_HIT_BOOK;
  assert(books==SHELF_BUDGET_BOOKS); /* every book is a hit/keyboard stop, not just the first 512 targets */
  double load_ms=shelf_budget_ms(t0,t1,f),paint_ms=shelf_budget_ms(t1,t2,f),interactive_ms=shelf_budget_ms(t0,t3,f);
  printf("SHELF-BUDGET shelf_load_ms=%.3f first_paint_ms=%.3f first_interactive_ms=%.3f hits=%d books=%d\n",
         load_ms,paint_ms,interactive_ms,sm_hit_count,books);
  /* The last book is reachable: Shift+Tab from the first stop wraps to it
     (before the 512-target cap was removed it could not be reached at all). */
  while(sm_key_kind!=SM_HIT_GRID) shelf_budget_key(VK_TAB,0);
  shelf_budget_key(VK_TAB,1);
  wchar_t label[320];sm_key_label(&sm_hits[sm_key_index()],label,320);
  {char *shown=host_utf8(label);printf("SHELF-BUDGET shift_tab_from_first_stop kind=%d label=%s\n",sm_key_kind,shown ? shown:"");free(shown);}
  /* The shelf is newest first, so the last stop is the bottom-most book. */
  long bottom=LONG_MIN;for(int k=0;k<sm_hit_count;k++) if(sm_hits[k].kind==SM_HIT_BOOK && sm_hits[k].r.top>bottom) bottom=sm_hits[k].r.top;
  assert(sm_key_kind==SM_HIT_BOOK && sm_hits[sm_key_index()].r.top==bottom && !wcscmp(label,L"书籍：Shelf 0000"));
  printf("SHELF-BUDGET last_book_reachable=1 scroll=%d content_h=%d\n",sm_scroll,sm_content_h);
  /* Back to the top, then Tab from the first stop to the first book. */
  sm_scroll_to(0);sm_key_kind=sm_key_arg=0;RedrawWindow(sm_view,NULL,NULL,RDW_INVALIDATE|RDW_UPDATENOW);
  do shelf_budget_key(VK_TAB,0); while(sm_key_kind!=SM_HIT_BOOK);
  static double grid[256],list[128];
  for(int i=0;i<8;i++) shelf_budget_key(VK_RIGHT,0); /* warm */
  for(int i=0;i<256;i++) {QueryPerformanceCounter(&a);shelf_budget_key(VK_RIGHT,0);QueryPerformanceCounter(&b);grid[i]=shelf_budget_ms(a,b,f);}
  int grid_scroll=sm_scroll;
  sm_list=1;sm_scroll=0;RedrawWindow(sm_view,NULL,NULL,RDW_INVALIDATE|RDW_UPDATENOW);
  for(int i=0;i<8;i++) shelf_budget_key(VK_DOWN,0);
  for(int i=0;i<128;i++) {QueryPerformanceCounter(&a);shelf_budget_key(VK_DOWN,0);QueryPerformanceCounter(&b);list[i]=shelf_budget_ms(a,b,f);}
  int list_scroll=sm_scroll;
  shelf_budget_series("grid_move",grid,256);shelf_budget_series("list_move",list,128);
  qsort(grid,256,sizeof(double),shelf_budget_cmp);qsort(list,128,sizeof(double),shelf_budget_cmp);
  double grid_p50=(grid[127]+grid[128])/2,grid_p95=grid[243],list_p50=(list[63]+list[64])/2,list_p95=list[121];
  PROCESS_MEMORY_COUNTERS counters={0};counters.cb=sizeof(counters);
  assert(GetProcessMemoryInfo(GetCurrentProcess(),&counters,sizeof(counters)));
  double peak=(double)counters.PeakWorkingSetSize;
  printf("SHELF-BUDGET grid_move n=256 p50_ms=%.6f p95_ms=%.6f max_ms=%.6f scrolled_to=%d\n",grid_p50,grid_p95,grid[255],grid_scroll);
  printf("SHELF-BUDGET list_move n=128 p50_ms=%.6f p95_ms=%.6f max_ms=%.6f scrolled_to=%d\n",list_p50,list_p95,list[127],list_scroll);
  printf("SHELF-BUDGET peak_working_set_bytes=%.0f\n",peak);
  int pass=interactive_ms<=2500.0 && grid_p50<=50.0 && grid_p95<=100.0 && list_p50<=50.0 && list_p95<=100.0 && peak<=268435456.0;
  printf("SHELF-BUDGET budgets first_interactive_ms<=2500 move_p50_ms<=50 move_p95_ms<=100 peak<=268435456 passed=%s\n",pass ? "true":"false");
  assert(grid_scroll>0 && list_scroll>0); /* the samples include real scrolling repaints */
  assert(pass);
  DestroyWindow(sm_view);sm_view=NULL;DestroyWindow(host);
  shelf_clear();exr_library_close(g.library);g.library=NULL;
  DeleteFileW(database_w);DeleteFileW(shelf_json);free(database);
}
