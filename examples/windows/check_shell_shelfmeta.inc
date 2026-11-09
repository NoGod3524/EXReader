/* SPDX-License-Identifier: MIT */
/* Shelf metadata: shelf.json roundtrip, failed-write rollback, series order,
   tag filters, idle rule and reading streak, all through production code. */
static void test_shelfmeta(void) {
  wchar_t temp[HOST_PATH],path[HOST_PATH];GetTempPathW(HOST_PATH,temp);
  swprintf(path,HOST_PATH,L"%lsexreader-shelf-check-%lu.json",temp,(unsigned long)GetCurrentProcessId());
  DeleteFileW(path);SetEnvironmentVariableW(L"EXREADER_SHELF_PATH",path);
  style_write(path,"{\"settings\":{\"theme\":\"dark\"},\"future\":{\"keep\":true}}");
  shell_style=exr_reader_style_defaults();shell_font=22;assert(shell_style_save());
  ok(exr_library_open(":memory:",&g.library,NULL),NULL);
  char body[6][160];
  for(int i=0;i<6;i++) {
    int64_t id=0;snprintf(body[i],160,"<html><body><p>Shelf book %d distinct body.</p></body></html>",i);
    char title[32];snprintf(title,32,"book-%d",i);
    ok(exr_library_import(g.library,EXR_HTML,body[i],strlen(body[i]),title,&id,NULL),NULL);
  }
  assert(reload_shelf()==EXR_OK && g.shelf_count==6);
  sm_load();assert(sm_writable);
  dict_init();assert(dict_writable && !wcscmp(dict_path,path));
  /* two series of three, inserted out of order, plus tags */
  const wchar_t *series[6]={L"甲",L"乙",L"甲",L"乙",L"甲",L"乙"},*index[6]={L"3",L"2",L"1",L"3",L"2",L"1"};
  const wchar_t *tags[6]={L"小说, 经典",L"小说",L"经典",L"",L"科幻",L"科幻,小说"};
  for(int i=0;i<6;i++) {
    wchar_t title[32];swprintf(title,32,L"标题 %d \"q\" \\ 😀",i);
    assert(sm_apply(i,title,L"作者",series[i],index[i],tags[i],NULL,0));
  }
  /* A dictionary loaded before metadata edits must preserve their latest values. */
  shell_font=24;assert(shell_style_save());dict_auto=1;assert(dict_config_save());
  assert(sm_save());shell_style_load();
  assert(shell_font==24);
  int valid;cv_json *shared=style_shelf_read(&valid);assert(valid && shared);
  assert(cv_json_get(shared,"books")->count==6);
  assert(cv_json_get(shared,"dictionary_auto_lookup")->boolean);
  assert(cv_json_get(cv_json_get(shared,"future"),"keep")->boolean);
  assert(!strcmp(cv_json_get(cv_json_get(shared,"settings"),"theme")->string,"dark"));
  cv_json_free(shared);
  int order[16],n=sm_order(order);assert(n==6);
  for(int i=0;i<6;i++) {
    int e=sm_book_entry((size_t)order[i]);
    assert(!strcmp(sm_entries[e].series,i<3 ? "乙":"甲") && sm_entries[e].series_index==(double)(i%3+1));
  }
  sm_collect_tags();assert(sm_tag_total==3);
  for(int t=0;t<3;t++){sm_filter=t;assert(sm_order(order)==(!strcmp(sm_tags[t],"小说") ? 3:2));}
  sm_filter=-2;assert(sm_order(order)==1);sm_filter=-1;
  /* failed write: in-memory edit rolled back, file unchanged */
  HANDLE f=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,0,NULL);assert(f!=INVALID_HANDLE_VALUE);
  char before[65536];DWORD got=0;ReadFile(f,before,sizeof(before),&got,NULL);CloseHandle(f);
  sm_fail_next=1;assert(!sm_apply(0,L"不应保存",NULL,NULL,NULL,NULL,NULL,0));
  assert(!strncmp(sm_title(0),"标题 0",8));
  f=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,0,NULL);char after[65536];DWORD got2=0;
  ReadFile(f,after,sizeof(after),&got2,NULL);CloseHandle(f);assert(got==got2 && !memcmp(before,after,got));
  /* library value is never stored as an override */
  {wchar_t lib[32];swprintf(lib,32,L"%hs",g.shelf[5].title);
   assert(sm_apply(5,lib,L"",L"",L"",L"",NULL,0));assert(!sm_entries[sm_book_entry(5)].title && !strcmp(sm_title(5),g.shelf[5].title));}
  /* idle rule with the virtual clock: 30 s grace, then nothing */
  sm_frozen_base=1762600000000ULL;sm_clock_offset=0;shell_active=1;sm_foreground=1;
  g.has_current=1;g.frame.valid=1;sm_reading_book=sm_book_entry(1);sm_last_tick=sm_now();
  uint64_t start=sm_entries[sm_reading_book].read_ms;
  sm_activity();for(int i=0;i<300;i++){sm_clock_offset+=1000;sm_tick();}
  assert(sm_entries[sm_reading_book].read_ms-start==SM_IDLE_MS);
  for(int i=0;i<12;i++){sm_activity();for(int k=0;k<10;k++){sm_clock_offset+=1000;sm_tick();}}
  assert(sm_entries[sm_reading_book].read_ms-start==SM_IDLE_MS+120000);
  sm_activity();shelf_exit_pending=1;sm_clock_offset+=1000;sm_tick();
  assert(sm_entries[sm_reading_book].read_ms-start==SM_IDLE_MS+120000);
  shelf_exit_pending=0;shelf_visible=1;sm_clock_offset+=1000;sm_tick();
  assert(sm_entries[sm_reading_book].read_ms-start==SM_IDLE_MS+120000);shelf_visible=0;
  sm_focus(0);sm_activity();for(int i=0;i<60;i++){sm_clock_offset+=1000;sm_tick();}
  assert(sm_entries[sm_reading_book].read_ms-start==SM_IDLE_MS+120000);
  /* streak: today, yesterday and the day before; a skipped day breaks it */
  assert(sm_streak()==1);
  sm_foreground=1;sm_clock_offset+=86400000;sm_activity();sm_clock_offset+=10000;sm_tick();assert(sm_streak()==2);
  sm_clock_offset+=86400000;sm_activity();sm_clock_offset+=10000;sm_tick();assert(sm_streak()==3);
  sm_clock_offset+=2*86400000ULL;sm_tick();assert(sm_streak()==0);
  assert(sm_save());
  /* roundtrip */
  cv_text saved={0};sm_serialize(&saved);assert(!saved.failed);
  sm_entry *items=sm_entries;int count=sm_count;sm_day *days=sm_days;int dc=sm_day_count;
  sm_entries=NULL;sm_count=0;sm_days=NULL;sm_day_count=0;
  assert(sm_parse(saved.data,saved.size) && sm_count==count && sm_day_count==dc);
  for(int i=0;i<count;i++) {
    assert(!strcmp(sm_entries[i].sha,items[i].sha) && sm_entries[i].read_ms==items[i].read_ms && sm_entries[i].tag_count==items[i].tag_count);
    assert(!sm_entries[i].title==!items[i].title && (!items[i].title || !strcmp(sm_entries[i].title,items[i].title)));
  }
  cv_text again={0};sm_serialize(&again);assert(again.size==saved.size && !memcmp(again.data,saved.data,saved.size));
  for(int i=0;i<sm_count;i++)sm_entry_free(&sm_entries[i]);
  free(sm_entries);free(sm_days);sm_entries=items;sm_count=count;sm_days=days;sm_day_count=dc;
  assert(!sm_parse("{\"version\":2,\"books\":[]}",24));assert(!sm_parse("{broken",7));
  cv_text_free(&saved);cv_text_free(&again);
  g.has_current=0;g.frame.valid=0;shelf_clear();exr_library_close(g.library);g.library=NULL;DeleteFileW(path);
  puts("SHELFMETA edits 6/6; series order 2x3; tag filters 4/4; rollback file-identical; idle 30 s cap; focus stop; streak 1/2/3/0; roundtrip byte-identical; version/malformed reject");
}
