/* SPDX-License-Identifier: MIT */
/* Exercise the native outline and actual editor in a hidden window. */
#define WinMain reader_WinMain
#define EXR_READER_TEST_DRIVERS 1
#include "../reader.c"
#undef WinMain
#include <assert.h>

static void outline_seed(int headings) {
  de_close();memset(&de,0,sizeof(de));
  exr_edit_run runs[27][2]={0};exr_edit_block blocks[27]={0};
  char xml[27][128];
  const unsigned levels[]={1,2,3,4,6};
  const char *titles[]={"First","Second","Third ","Fourth","Sixth"};
  for(size_t i=0;i<27;i++) {
    runs[i][0].text="Body paragraph";runs[i][0].text_size=14;
    blocks[i].kind=EXR_EDIT_PARAGRAPH;blocks[i].runs=runs[i];blocks[i].run_count=1;
    if(headings && i%6==0) {
      size_t at=i/6;
      snprintf(xml[i],sizeof(xml[i]),"<w:p><w:pPr><w:pStyle w:val=\"Heading%u\"/></w:pPr></w:p>",levels[at]);
      blocks[i].opaque_xml=xml[i];blocks[i].opaque_size=strlen(xml[i]);
      runs[i][0].text=titles[at];runs[i][0].text_size=strlen(titles[at]);
      if(at==2) {
        runs[i][1].text="\xe4\xb8\xad\xf0\x9f\x99\x82";runs[i][1].text_size=7;
        runs[i][1].props.present=EXR_EDIT_BOLD;runs[i][1].props.bold=1;
        blocks[i].run_count=2;
      }
    }
  }
  if(headings) {
    const char *invalid="<w:p><w:pPr><w:pStyle w:val=\"Heading7\"/></w:pPr></w:p>";
    blocks[26].opaque_xml=invalid;blocks[26].opaque_size=strlen(invalid);
  }
  assert(exr_edit_doc_create(NULL,0,blocks,27,NULL,0,NULL,&de.doc)==EXR_OK);
  de_set_caret(de_start(0));de_set_anchor(de_caret_pos());de.layout_dirty=1;
  de_refresh(1);
}

static void outline_visible(void) {
  assert(de.caret.view<de.row_count);
  float box[4];shell_d2d_edit_row *row=&de.rows[de.caret.view];
  shell_d2d_edit_position(row->layout,de_offset(de_caret_pos()),box);
  float top=row->y+box[1]-de.scroll_y,bottom=top+box[3];
  assert(top>=de_toolbar_height()-.5f && bottom<=de.height+.5f);
}

static int outline_text_is(size_t index,const wchar_t *expected) {
  return index<deo.count && !wcscmp(deo.items[index].text,expected);
}

static void outline_wait_text(size_t index,const wchar_t *expected,ULONGLONG start) {
  while(!outline_text_is(index,expected) && GetTickCount64()-start<300) {
    MSG message;
    while(PeekMessageW(&message,NULL,0,0,PM_REMOVE)) {
      TranslateMessage(&message);DispatchMessageW(&message);
    }
    Sleep(1);
  }
  assert(outline_text_is(index,expected));
  assert(GetTickCount64()-start<=300);
}

static void outline_style_acceptance(void) {
  de_close();memset(&de,0,sizeof(de));
  const char *styles="<w:styles xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\">"
    "<w:style w:type=\"paragraph\" w:styleId=\"CustomTitle\"><w:name w:val=\"heading 2\"/></w:style>"
    "<w:style w:type=\"paragraph\" w:styleId=\"Derived\"><w:basedOn w:val=\"CustomTitle\"/></w:style>"
    "<w:style w:type=\"paragraph\" w:styleId=\"CycleA\"><w:basedOn w:val=\"CycleB\"/></w:style>"
    "<w:style w:type=\"paragraph\" w:styleId=\"CycleB\"><w:basedOn w:val=\"CycleA\"/></w:style>"
    "<w:style w:type=\"character\" w:styleId=\"CharTitle\"><w:name w:val=\"Heading 3\"/></w:style>"
    "<w:style w:type=\"character\" w:styleId=\"Heading4\"><w:name w:val=\"Emphasis\"/></w:style>"
    "</w:styles>";
  const char *ids[]={"CustomTitle","Derived","CycleA","CharTitle","Heading4"};
  exr_edit_run runs[6]={0};exr_edit_block blocks[6]={0};char xml[6][160];
  for(size_t i=0;i<6;i++) {
    runs[i].text="Styled paragraph";runs[i].text_size=16;
    blocks[i].runs=&runs[i];blocks[i].run_count=1;
    if(i<5)snprintf(xml[i],sizeof(xml[i]),
      "<w:p><w:pPr><w:pStyle w:val=\"%s\"/></w:pPr></w:p>",ids[i]);
    else strcpy(xml[i],"<w:p><w:r><w:rPr><w:rStyle w:val=\"CharTitle\"/></w:rPr><w:t>body</w:t></w:r></w:p>");
    blocks[i].opaque_xml=xml[i];blocks[i].opaque_size=strlen(xml[i]);
  }
  exr_edit_part part={0};part.name="word/styles.xml";part.data=styles;part.size=strlen(styles);
  assert(exr_edit_doc_create(NULL,0,blocks,6,&part,1,NULL,&de.doc)==EXR_OK);
  de_set_caret(de_start(0));de_set_anchor(de_caret_pos());de.layout_dirty=1;de_refresh(1);
  assert(deo.count==2 && deo.items[0].level==2 && deo.items[1].level==2);
  assert(deo.items[0].view==0 && deo.items[1].view==1);
  for(size_t i=2;i<6;i++)assert(de_heading_level(de_block_at(de.doc,i))==0);
  puts("PASS custom Heading style names/basedOn; inheritance cycles, character styles and run styles excluded");
}

int main(void) {
  setvbuf(stdout,NULL,_IONBF,0);
  SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);
  assert(SUCCEEDED(CoInitializeEx(NULL,COINIT_APARTMENTTHREADED)));
  assert(SUCCEEDED(shell_d2d_create(NULL,&host_shell)));
  shell_dpi=96;shell_apply_theme();host_offscreen=1;
  WNDCLASSW klass={0};klass.lpfnWndProc=page_procedure;
  klass.hInstance=GetModuleHandleW(NULL);klass.lpszClassName=L"L15OutlineHeadlessPage";
  assert(RegisterClassW(&klass));
  g.page=CreateWindowExW(0,klass.lpszClassName,L"L15 headless",WS_OVERLAPPEDWINDOW,
    0,0,900,300,NULL,NULL,klass.hInstance,NULL);
  assert(g.page);

  outline_seed(1);
  assert(deo.pane && deo.tree && deo.levels && deo.count==5);
  const unsigned expected[]={1,2,3,4,6};
  for(size_t i=0;i<5;i++) {
    assert(deo.items[i].level==expected[i] && deo.items[i].view==i*6);
    assert(TreeView_GetParent(deo.tree,deo.items[i].node)==(i ? deo.items[i-1].node:NULL));
  }
  assert(TreeView_GetCount(deo.tree)==5);
  assert(outline_text_is(2,L"Third \x4e2d\xd83d\xde42"));
  assert(de_outline_width(900)==240 && de_outline_width(300)==100);
  puts("PASS five Heading 1/2/3/4/6 entries, hierarchy, skipped level, multi-run Unicode; body/H7 excluded");

  de_outline_level(6);
  exr_edit_id third=deo.items[2].id;
  assert(TreeView_SelectItem(deo.tree,deo.items[2].node));
  assert(de.caret.block==12 && de.caret.view==12);
  assert(!de_selected() && de.scroll_y>0);outline_visible();
  assert(de_outline_jump(third));outline_visible();
  printf("PASS native tree selection -> caret block=%zu, scroll=%.1f, caret visible\n",de.caret.block,de.scroll_y);

  ULONGLONG start=GetTickCount64();
  de_character(L'!');outline_wait_text(2,L"!Third \x4e2d\xd83d\xde42",start);
  printf("PASS typed heading updates within %llu ms\n",(unsigned long long)(GetTickCount64()-start));
  assert(de_key('Z',1,0));assert(outline_text_is(2,L"Third \x4e2d\xd83d\xde42"));
  assert(de_key('Y',1,0));assert(outline_text_is(2,L"!Third \x4e2d\xd83d\xde42"));
  puts("PASS outline follows editor undo/redo");

  de_outline_level(1);
  assert(de.caret.block==12);
  assert(!(TreeView_GetItemState(deo.tree,deo.items[0].node,TVIS_EXPANDED)&TVIS_EXPANDED));
  SendMessageW(deo.levels,CB_SETCURSEL,2,0);
  SendMessageW(deo.pane,WM_COMMAND,MAKEWPARAM(0,CBN_SELCHANGE),(LPARAM)deo.levels);
  assert(deo.max_level==3);
  assert(TreeView_GetItemState(deo.tree,deo.items[0].node,TVIS_EXPANDED)&TVIS_EXPANDED);
  assert(TreeView_GetItemState(deo.tree,deo.items[1].node,TVIS_EXPANDED)&TVIS_EXPANDED);
  assert(!(TreeView_GetItemState(deo.tree,deo.items[2].node,TVIS_EXPANDED)&TVIS_EXPANDED));
  de_character(L'?');assert(deo.max_level==3);
  assert(!(TreeView_GetItemState(deo.tree,deo.items[2].node,TVIS_EXPANDED)&TVIS_EXPANDED));
  de_outline_level(6);
  assert(TreeView_GetItemState(deo.tree,deo.items[3].node,TVIS_EXPANDED)&TVIS_EXPANDED);
  assert(de_key('O',1,1));
  assert(!SendMessageW(deo.tree,WM_KEYDOWN,VK_RETURN,0));
  assert(!SendMessageW(deo.tree,WM_KEYDOWN,VK_ESCAPE,0));
  puts("PASS collapse/expand at levels 1/3/6, level retained during typing");

  assert(de_outline_jump(third));
  de_set_caret(de_end(de.caret.view));de_set_anchor(de_caret_pos());
  assert(de_key(VK_RETURN,0,0));assert(deo.count==6);
  assert(deo.items[2].id==third && deo.items[3].level==3);
  assert(de_key('Z',1,0));assert(deo.count==5);
  exr_edit_run body={0};body.text="Inserted body";body.text_size=13;
  exr_edit_id inserted=0;
  assert(exr_edit_insert_paragraph(de.doc,0,&body,1,NULL,&inserted)==EXR_OK);
  de.layout_dirty=1;de_refresh(0);
  assert(de_outline_jump(third));assert(de.caret.block==13);outline_visible();
  assert(!de_outline_jump(UINT64_MAX));
  puts("PASS split/undo refresh and stable heading ID after block indices shift");

  outline_style_acceptance();
  outline_seed(0);assert(deo.count==0 && TreeView_GetCount(deo.tree)==0);
  wchar_t empty[32]={0};assert(GetWindowTextW(deo.empty,empty,32));
  assert(!wcscmp(empty,L"\x65e0\x6807\x9898"));
  assert(GetWindowLongPtrW(deo.empty,GWL_STYLE)&WS_VISIBLE);
  puts("PASS no headings displays the native empty entry: 无标题");
  de_close();assert(!deo.pane && !deo.tree && !deo.count);
  DestroyWindow(g.page);g.page=NULL;
  UnregisterClassW(klass.lpszClassName,klass.hInstance);
  shell_d2d_destroy(host_shell);host_shell=NULL;
  exr_font_free(g.font);exr_font_manager_free(g.font_manager);CoUninitialize();
  puts("L15 outline headless acceptance PASS");return 0;
}
