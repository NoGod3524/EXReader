/* SPDX-License-Identifier: MIT */
/* One production-path check: serialization, failed write rollback, geometry, deletion. */
static void test_annotations(void) {
  wchar_t directory[HOST_PATH],temp[HOST_PATH];GetTempPathW(HOST_PATH,temp);
  swprintf(directory,HOST_PATH,L"%lsexreader-annotation-check-%lu",temp,(unsigned long)GetCurrentProcessId());
  SetEnvironmentVariableW(L"EXREADER_ANNOTATIONS_DIR",directory);
  ok(exr_library_open(":memory:",&g.library,NULL),NULL);int64_t id=0;
  ok(exr_library_import(g.library,EXR_HTML,fixture,strlen(fixture),"annotations",&id,NULL),NULL);
  prepare_layout(0);annot_sync();assert(annot_writable && strlen(annot_hash)==64);
  for(int i=0;i<8;i++) {
    annot_selected=-1;assert(select_set((exr_text_position){0,(size_t)i*3},(exr_text_position){0,(size_t)i*3+3},-1,1));
    assert(annot_commit(i>=5 ? "笔记\n\"quote\"\\😀":"",i%3));
  }
  assert(annot_count==8);cv_text saved={0};annot_serialize(&saved);assert(!saved.failed);
  annot_clear();assert(annot_parse(saved.data,saved.size));annot_resolve();annot_writable=1;
  for(int i=0;i<8;i++)assert(annotations[i].found && annotations[i].range.start.offset==(size_t)i*3 && annotations[i].color==i%3);
  annot_selected=7;select_all_part();assert(annot_selected==-1);
  assert(!strcmp(annotations[7].text,"笔记\n\"quote\"\\😀"));
  wchar_t good[HOST_PATH];copy_wstring(good,HOST_PATH,annot_path);copy_wstring(annot_path,HOST_PATH,L"Z:\\missing-exreader-folder\\file.json");
  annot_selected=7;assert(!annot_commit("unsaved",0));assert(!strcmp(annotations[7].text,"笔记\n\"quote\"\\😀"));
  assert(!annot_delete());assert(annot_count==8);copy_wstring(annot_path,HOST_PATH,good);
  for(int vertical=0;vertical<2;vertical++) {
    prepare_layout(vertical);size_t pixels=(size_t)g.frame.bitmap.width*g.frame.bitmap.height;
    uint32_t *copy=malloc(pixels*4);assert(copy);memcpy(copy,g.frame.dib,pixels*4);
    uint32_t *painted=malloc(pixels*4);assert(painted);memcpy(painted,copy,pixels*4);
    annot_pixels(painted,g.frame.bitmap.width,g.frame.bitmap.height);
    assert(!memcmp(copy,g.frame.dib,pixels*4));assert(memcmp(painted,copy,pixels*4));free(painted);free(copy);
    HRGN region=annot_region(&annotations[1]);RECT bounds;assert(GetRgnBox(region,&bounds)!=NULLREGION);DeleteObject(region);
  }
  annot_selected=7;assert(annot_commit("edited",2));assert(annotations[7].color==2 && !strcmp(annotations[7].text,"edited"));
  assert(annot_delete());assert(annot_count==7);
  shell_annotation *items=annotations;int count=annot_count;annotations=NULL;annot_count=0;
  assert(!annot_parse("{\"version\":2}",13));assert(!annot_parse("{broken",7));
  const char *nul="{\"version\":1,\"text\":\"\\u0000\"}";assert(!annot_parse(nul,strlen(nul)));
  annotations=items;annot_count=count;annot_clear();cv_text_free(&saved);exr_library_close(g.library);g.library=NULL;
  DeleteFileW(good);RemoveDirectoryW(directory);
  puts("ANNOTATIONS restore 8/8; UTF-8 escaping; colors 3/3; rollback 2/2; horizontal/vertical ink unchanged; edit/delete; malformed/version reject");
}
