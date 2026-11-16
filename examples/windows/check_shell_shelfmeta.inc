/* SPDX-License-Identifier: MIT */
/* Shelf metadata: shelf.json roundtrip, failed-write rollback, series order,
   tag filters, idle rule and reading streak, all through production code. */
static void shelfmeta_expect_name(HWND control,const wchar_t *expected) {
  HMODULE module=LoadLibraryW(L"oleacc.dll");assert(module);
  typedef HRESULT (WINAPI *accessible_from_window)(HWND,DWORD,REFIID,void **);
  accessible_from_window load=(accessible_from_window)(void (*)(void))GetProcAddress(module,"AccessibleObjectFromWindow");assert(load);
  IAccessible *object=NULL;BSTR name=NULL;VARIANT child;VariantInit(&child);child.vt=VT_I4;child.lVal=CHILDID_SELF;
  assert(SUCCEEDED(load(control,OBJID_CLIENT,&IID_IAccessible,(void **)&object)) && object);
  assert(SUCCEEDED(object->lpVtbl->get_accName(object,child,&name)) && name && !wcscmp(name,expected));
  SysFreeString(name);object->lpVtbl->Release(object);FreeLibrary(module);
}
/* F09: every stop is its own MSAA child (UIA element through the MSAA bridge). */
static void shelfmeta_expect_children(int stops,const wchar_t *focused_label) {
  HMODULE module=LoadLibraryW(L"oleacc.dll");assert(module);
  typedef HRESULT (WINAPI *accessible_from_window)(HWND,DWORD,REFIID,void **);
  accessible_from_window load=(accessible_from_window)(void (*)(void))GetProcAddress(module,"AccessibleObjectFromWindow");assert(load);
  IAccessible *object=NULL;assert(SUCCEEDED(load(sm_view,OBJID_CLIENT,&IID_IAccessible,(void **)&object)) && object);
  long count=0;assert(SUCCEEDED(object->lpVtbl->get_accChildCount(object,&count)) && count==stops);
  int order[512],n=sm_key_order(order);assert(n==stops);
  int books=0;
  for(long id=1;id<=count;id++) {
    VARIANT child;VariantInit(&child);child.vt=VT_I4;child.lVal=id;
    BSTR name=NULL;VARIANT role,state;VariantInit(&role);VariantInit(&state);IDispatch *dispatch=(IDispatch *)1;
    assert(object->lpVtbl->get_accChild(object,child,&dispatch)==S_FALSE && !dispatch); /* simple element */
    assert(SUCCEEDED(object->lpVtbl->get_accName(object,child,&name)) && name && name[0]);
    wchar_t expected[320];sm_key_label(&sm_hits[order[id-1]],expected,320);assert(!wcscmp(name,expected));
    assert(SUCCEEDED(object->lpVtbl->get_accRole(object,child,&role)) && role.vt==VT_I4);
    int kind=sm_hits[order[id-1]].kind;
    assert(role.lVal==(kind==SM_HIT_BOOK ? ROLE_SYSTEM_LISTITEM:kind==SM_HIT_TAG ? ROLE_SYSTEM_RADIOBUTTON:ROLE_SYSTEM_PUSHBUTTON));
    books+=role.lVal==ROLE_SYSTEM_LISTITEM;
    assert(SUCCEEDED(object->lpVtbl->get_accState(object,child,&state)) && state.vt==VT_I4 && (state.lVal&STATE_SYSTEM_FOCUSABLE));
    long x=0,y=0,w=0,h=0;assert(SUCCEEDED(object->lpVtbl->accLocation(object,&x,&y,&w,&h,child)) && w>0 && h>0);
    VARIANT hit;VariantInit(&hit);
    assert(SUCCEEDED(object->lpVtbl->accHitTest(object,x+w/2,y+h/2,&hit)) && hit.vt==VT_I4 && hit.lVal==id);
    SysFreeString(name);
  }
  VARIANT self,first,next;VariantInit(&self);VariantInit(&first);VariantInit(&next);self.vt=VT_I4;self.lVal=CHILDID_SELF;
  assert(object->lpVtbl->accNavigate(object,NAVDIR_FIRSTCHILD,self,&first)==S_OK && first.vt==VT_I4 && first.lVal==1);
  assert(object->lpVtbl->accNavigate(object,NAVDIR_NEXT,first,&next)==S_OK && next.vt==VT_I4 && next.lVal==2);
  VARIANT selected;VariantInit(&selected);BSTR name=NULL;
  assert(object->lpVtbl->get_accSelection(object,&selected)==S_OK && selected.vt==VT_I4 && selected.lVal>0);
  assert(SUCCEEDED(object->lpVtbl->get_accName(object,selected,&name)) && !wcscmp(name,focused_label));
  SysFreeString(name);object->lpVtbl->Release(object);FreeLibrary(module);
  printf("SHELFMETA MSAA children: %ld simple elements (%d list items) with names, roles, focusable state, bounds, hit test, navigation and the focused stop as selection PASS\n",count,books);
}
static void shelfmeta_tab(int shift) {
  BYTE keys[256];GetKeyboardState(keys);keys[VK_SHIFT]=shift ? 0x80:0;SetKeyboardState(keys);
  SendMessageW(sm_view,WM_KEYDOWN,VK_TAB,0);
  keys[VK_SHIFT]=0;SetKeyboardState(keys);
}
/* F09: the custom-drawn shelf exposed one Tab stop and no keyboard activation. */
static void shelfmeta_keyboard(void) {
  WNDCLASSW type={0};type.lpfnWndProc=sm_view_procedure;type.hInstance=GetModuleHandleW(NULL);
  type.lpszClassName=L"EXReaderShelfMetaKeyboardTest";RegisterClassW(&type);
  HWND host=CreateWindowExW(WS_EX_NOACTIVATE,L"STATIC",L"",WS_POPUP|WS_VISIBLE,-32000,-32000,900,700,NULL,NULL,NULL,NULL);assert(host);
  sm_view=CreateWindowExW(0,type.lpszClassName,L"系列、标签与阅读统计",WS_CHILD|WS_VISIBLE|WS_TABSTOP|WS_VSCROLL,0,0,900,700,host,NULL,NULL,NULL);
  assert(sm_view);sm_mode=0;sm_list=0;sm_filter=-1;sm_scroll=0;sm_key_kind=sm_key_arg=0;
  RedrawWindow(sm_view,NULL,NULL,RDW_INVALIDATE|RDW_UPDATENOW);
  int stops=sm_hit_count;assert(stops>=6+6+2);
  assert(SendMessageW(sm_view,WM_GETDLGCODE,VK_TAB,0)&DLGC_WANTTAB);
  int kinds[512],args[512],books=0,toolbar=0,tags=0;
  for(int i=0;i<stops;i++) {
    shelfmeta_tab(0);int at=sm_key_index();assert(at>=0);kinds[i]=sm_hits[at].kind;args[i]=sm_hits[at].arg;
    for(int j=0;j<i;j++) assert(kinds[j]!=kinds[i] || args[j]!=args[i]);
    books+=kinds[i]==SM_HIT_BOOK;tags+=kinds[i]==SM_HIT_TAG;toolbar+=kinds[i]>=SM_HIT_GRID;
  }
  assert(books==6 && toolbar==6 && tags>=2 && books+toolbar+tags==stops);
  shelfmeta_tab(0);assert(sm_key_kind==kinds[0] && sm_key_arg==args[0]); /* wraps */
  shelfmeta_tab(1);assert(sm_key_kind==kinds[stops-1] && sm_key_arg==args[stops-1]); /* Shift+Tab */
  while(!(sm_key_kind==SM_HIT_TAG && sm_key_arg==-2)) shelfmeta_tab(0);
  shelfmeta_expect_name(sm_view,L"标签筛选：未分类");
  SendMessageW(sm_view,WM_KEYDOWN,VK_RETURN,0);assert(sm_filter==-2);
  shelfmeta_expect_name(sm_view,L"标签筛选：未分类（已选）");
  while(!(sm_key_kind==SM_HIT_TAG && sm_key_arg==-1)) shelfmeta_tab(0);
  SendMessageW(sm_view,WM_KEYDOWN,VK_SPACE,0);assert(sm_filter==-1);
  while(sm_key_kind!=SM_HIT_LIST) shelfmeta_tab(0);
  shelfmeta_expect_name(sm_view,L"列表视图");
  SendMessageW(sm_view,WM_KEYDOWN,VK_RETURN,0);assert(sm_list==1);
  RedrawWindow(sm_view,NULL,NULL,RDW_INVALIDATE|RDW_UPDATENOW);assert(sm_key_index()>=0 && sm_key_kind==SM_HIT_LIST);
  while(sm_key_kind!=SM_HIT_BOOK) shelfmeta_tab(0);
  wchar_t expected[320];sm_key_label(&sm_hits[sm_key_index()],expected,320);assert(!wcsncmp(expected,L"书籍：",3));
  shelfmeta_expect_name(sm_view,expected);
  RedrawWindow(sm_view,NULL,NULL,RDW_INVALIDATE|RDW_UPDATENOW);shelfmeta_expect_children(sm_hit_count,expected);
  while(sm_key_kind!=SM_HIT_GRID) shelfmeta_tab(0);
  SendMessageW(sm_view,WM_KEYDOWN,VK_RETURN,0);assert(sm_list==0);
  printf("SHELFMETA keyboard: %d stops (6 books, 6 toolbar, %d tag filters) in Tab order, wrap and Shift+Tab, Enter/Space activate filter/list/grid, IAccessible name follows focus PASS\n",stops,tags);
  DestroyWindow(sm_view);sm_view=NULL;DestroyWindow(host);
}
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
  shelfmeta_keyboard();
  g.has_current=0;g.frame.valid=0;shelf_clear();exr_library_close(g.library);g.library=NULL;DeleteFileW(path);
  puts("SHELFMETA edits 6/6; series order 2x3; tag filters 4/4; rollback file-identical; idle 30 s cap; focus stop; streak 1/2/3/0; roundtrip byte-identical; version/malformed reject");
}
