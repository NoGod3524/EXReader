/* SPDX-License-Identifier: MIT */
/* Production ratio decisions, content-anchor JSON roundtrip, atomic failure and corruption. */
static void test_shelf(void) {
  for(int mode=0;mode<3;mode++) {
    g.frame.writing_mode=mode;
    for(int edge=20;edge<=25;edge+=5) {
      shell_tap_edge=edge;int reverse=mode==EXR_WRITING_VERTICAL_RL ? -1:1;
      assert(gesture_tap(0,1000)==-reverse);
      assert(gesture_tap(edge*10-1,1000)==-reverse);
      assert(gesture_tap(edge*10,1000)==0);
      assert(gesture_tap(1000-edge*10-1,1000)==0);
      assert(gesture_tap(1000-edge*10,1000)==reverse);
      assert(gesture_tap(999,1000)==reverse);
    }
  }
  wchar_t temp[HOST_PATH];GetTempPathW(HOST_PATH,temp);
  swprintf(g.data_dir,HOST_PATH,L"%lsexreader-shelf-%lu",temp,(unsigned long)GetCurrentProcessId());ensure_directory(g.data_dir);
  shelf_load();assert(shelf_loaded && shelf_writable && !shelf_count);
  shelf_count=1;shelf_book *b=&shelf_recent[0];b->id=1;b->path=host_strdup("C:\\图书\\a.epub");
  b->title=host_strdup("书架 \"书\" 😀");b->author=host_strdup("作者");b->progress=.25;b->opened=1;
  exr_text_position point={0,3};assert(exr_anchor_from_range(select_publication(),&(exr_text_range){point,point},NULL,&b->anchor,NULL)==EXR_OK);
  assert(shelf_save());shelf_destroy();shelf_load();assert(shelf_count==1 && shelf_writable);
  b=&shelf_recent[0];assert(!strcmp(b->path,"C:\\图书\\a.epub") && !strcmp(b->title,"书架 \"书\" 😀") && b->progress==.25);
  exr_text_range_match match={0};assert(exr_range_from_anchor(select_publication(),&b->anchor,NULL,&match,NULL)==EXR_OK && match.state==EXR_ANCHOR_FOUND && match.range.start.offset==3);
  wchar_t good[HOST_PATH];copy_wstring(good,HOST_PATH,shelf_json_path);copy_wstring(shelf_json_path,HOST_PATH,L"Z:\\absent-exreader-shelf\\recent.json");
  assert(!shelf_save());copy_wstring(shelf_json_path,HOST_PATH,good);
  shelf_destroy();shelf_load();assert(shelf_count==1 && shelf_recent[0].anchor.start.selector.start==3);
  shelf_destroy();FILE *f=_wfopen(good,L"wb");assert(f);fputs("{broken",f);fclose(f);
  shelf_load();assert(!shelf_writable && shelf_count==0);assert(!shelf_save());
  char bytes[16]={0};f=_wfopen(good,L"rb");assert(f);assert(fread(bytes,1,7,f)==7 && !memcmp(bytes,"{broken",7));fclose(f);
  DeleteFileW(good);RemoveDirectoryW(g.data_dir);shelf_loaded=0;shelf_writable=1;
  puts("SHELF ratios 36/36; UTF-8/content-anchor roundtrip; atomic failure preserves file; malformed file blocks overwrite");
}
