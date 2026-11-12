/* SPDX-License-Identifier: MIT */
/* Console-only acceptance of the actual host, not a second editor implementation. */
#define WinMain reader_WinMain
#define EXR_READER_TEST_DRIVERS 1
#include "../reader.c"
#undef WinMain
#include <assert.h>

static char *model_text(exr_edit_doc *doc) {
  cv_text out={0};
  for(size_t i=0;i<exr_edit_block_count(doc);i++) {
    const exr_edit_block *b=exr_edit_block_at(doc,i);
    cv_text_string(&out,"\n[block]");
    for(size_t j=0;j<b->run_count;j++) {
      const exr_edit_run *r=&b->runs[j];
      if(r->kind==EXR_EDIT_TEXT)cv_text_append(&out,r->text,r->text_size);
    }
  }
  cv_text_string(&out,"");return out.data;
}
static void same_text(const char *expected) {
  char *actual=model_text(de.doc);assert(!strcmp(expected,actual));free(actual);
}
static void file_text_equal(const char *path,const char *expected) {
  exr_edit_doc *readback=NULL;exr_error error={0};
  assert(exr_edit_docx_open(path,NULL,&readback,&error)==EXR_OK);
  char *actual=model_text(readback);assert(!strcmp(expected,actual));free(actual);exr_edit_doc_free(readback);
}
static void reset_caret(void) {
  de_pos p=de_start(0);
  while(exr_edit_block_at(de.doc,p.block)->kind!=EXR_EDIT_PARAGRAPH)p.block++;
  de_set_caret(p);de_set_anchor(p);
}
static uint32_t *paint_memory(int width,int height) {
  RECT area={0,0,width,height};BITMAPINFO info={0};void *pixels=NULL;
  info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);info.bmiHeader.biWidth=width;
  info.bmiHeader.biHeight=-height;info.bmiHeader.biPlanes=1;info.bmiHeader.biBitCount=32;
  HDC dc=CreateCompatibleDC(NULL);assert(dc);
  HBITMAP bitmap=CreateDIBSection(dc,&info,DIB_RGB_COLORS,&pixels,NULL,0);assert(bitmap);
  HGDIOBJ old=SelectObject(dc,bitmap);
  assert(de_paint_dc(dc,&area)==S_OK);GdiFlush();
  uint32_t *copy=malloc((size_t)width*height*4);assert(copy);memcpy(copy,pixels,(size_t)width*height*4);
  SelectObject(dc,old);DeleteObject(bitmap);DeleteDC(dc);return copy;
}
static void save_bitmap(const char *path,const uint32_t *pixels,int width,int height) {
  BITMAPFILEHEADER file={0};BITMAPINFOHEADER info={0};
  file.bfType=0x4d42;file.bfOffBits=sizeof(file)+sizeof(info);file.bfSize=file.bfOffBits+width*height*4;
  info.biSize=sizeof(info);info.biWidth=width;info.biHeight=-height;info.biPlanes=1;info.biBitCount=32;
  FILE *out=fopen(path,"wb");assert(out);
  assert(fwrite(&file,sizeof(file),1,out)==1 && fwrite(&info,sizeof(info),1,out)==1);
  assert(fwrite(pixels,4,(size_t)width*height,out)==(size_t)width*height);assert(!fclose(out));
}
static void seed_runs(void) {
  de_close();
  exr_edit_run runs[3]={{0}};runs[0].text="a\xc3\xa9";runs[0].text_size=3;
  runs[1].text="";runs[2].text="\xe4\xb8\xad\xf0\x9f\x99\x82";runs[2].text_size=7;
  runs[2].props.present=EXR_EDIT_BOLD;runs[2].props.bold=1;
  exr_edit_run tail={0};tail.text="tail";tail.text_size=4;
  exr_edit_block blocks[2]={{0}};blocks[0].runs=runs;blocks[0].run_count=3;
  blocks[1].runs=&tail;blocks[1].run_count=1;
  assert(exr_edit_doc_create(NULL,0,blocks,2,NULL,0,NULL,&de.doc)==EXR_OK);
  de.dirty=0;de.layout_dirty=1;de.scroll_y=0;de.blink=1;reset_caret();assert(de_measure(600,240));
}
int main(int argc,char **argv) {
  assert(argc==3);setvbuf(stdout,NULL,_IONBF,0);
  SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);
  assert(SUCCEEDED(CoInitializeEx(NULL,COINIT_APARTMENTTHREADED)));
  assert(SUCCEEDED(shell_d2d_create(NULL,&host_shell)));shell_dpi=96;
  wchar_t *directory=host_wide(argv[2],strlen(argv[2]));assert(directory);
  ensure_directory(directory);copy_wstring(g.data_dir,HOST_PATH,directory);free(directory);
  exr_error error={0};
  assert(host_open_body_font(L"C:\\Windows\\Fonts\\segoeui.ttf",L"",&error)==EXR_OK);
  char path[MAX_PATH],bmp[MAX_PATH];snprintf(path,sizeof(path),"%s/edited.docx",argv[2]);
  snprintf(bmp,sizeof(bmp),"%s/editor.bmp",argv[2]);
  wchar_t *source=host_wide(argv[1],strlen(argv[1])),*destination=host_wide(path,strlen(path));
  assert(source && destination && CopyFileW(source,destination,FALSE));free(source);free(destination);
  assert(de_open(path));assert(de_measure(600,240));
  size_t blocks=exr_edit_block_count(de.doc);char *original=model_text(de.doc);
  uint32_t *visible=paint_memory(600,240);save_bitmap(bmp,visible,600,240);
  de.blink=0;uint32_t *hidden=paint_memory(600,240);size_t caret_pixels=0,text_pixels=0;
  for(size_t i=0;i<600*240;i++) {caret_pixels+=visible[i]!=hidden[i];text_pixels+=(hidden[i]&0xffffff)!=(hidden[0]&0xffffff);}
  assert(caret_pixels>0 && text_pixels>0);free(visible);free(hidden);
  printf("1 PASS fixture=%s blocks=%zu text_pixels=%zu caret_pixels=%zu bitmap=%s\n",argv[1],blocks,text_pixels,caret_pixels,bmp);
  reset_caret();page_procedure(NULL,WM_CHAR,L'A',0);page_procedure(NULL,WM_CHAR,L'B',0);page_procedure(NULL,WM_CHAR,L'C',0);
  const exr_edit_block *first=exr_edit_block_at(de.doc,de.caret_block);
  assert(first->runs[0].text_size>=3 && !memcmp(first->runs[0].text,"ABC",3));
  printf("2 typed=ABC dirty=%d ",de.dirty);
  char *typed=model_text(de.doc);de_key('S',1,0);file_text_equal(path,typed);free(typed);
  for(int i=0;i<3;i++)de_key(VK_BACK,0,0);same_text(original);
  de_key('S',1,0);file_text_equal(path,original);
  puts("write/open ABC=1; backspace=3 write/open restored_original=1 PASS");
  reset_caret();de_key(VK_RETURN,0,0);assert(exr_edit_block_count(de.doc)==blocks+1);
  printf("3 Enter block_count=%zu -> %zu ",blocks,exr_edit_block_count(de.doc));
  de_key('Z',1,0);assert(exr_edit_block_count(de.doc)==blocks);same_text(original);
  printf("Ctrl+Z=%zu PASS\n",exr_edit_block_count(de.doc));free(original);
  seed_runs();
  size_t expected_run[]={0,0,2,2,0},expected_byte[]={1,3,3,7,0};
  for(int i=0;i<5;i++) {
    de_key(VK_RIGHT,0,0);assert(de.caret_run==expected_run[i] && de.caret_byte==expected_byte[i]);
    assert(de.caret_block==(i==4 ? 1u:0u));
  }
  de_key(VK_LEFT,0,0);assert(de.caret_block==0 && de.caret_run==2 && de.caret_byte==7);
  de_key(VK_LEFT,0,1);de_key(VK_LEFT,0,1);assert(de_selected());
  assert(de.caret_run==0 && de.caret_byte==3);
  de.blink=0;uint32_t *selection=paint_memory(600,240);de_set_anchor(de_caret());
  uint32_t *unselected=paint_memory(600,240);size_t selection_pixels=0;
  for(size_t i=0;i<600*240;i++)selection_pixels+=selection[i]!=unselected[i];
  assert(selection_pixels>0);free(selection);free(unselected);
  de_key(VK_RIGHT,0,1);de_key(VK_RIGHT,0,1);char *before=model_text(de.doc);
  de_character(L'X');de_key('Z',1,0);same_text(before);free(before);
  reset_caret();de_set_caret(de_end(0));de_set_anchor(de_caret());
  de_key(VK_DELETE,0,0);assert(exr_edit_block_count(de.doc)==1);
  de_key('Z',1,0);assert(exr_edit_block_count(de.doc)==2);
  de_set_caret(de_start(1));de_set_anchor(de_caret());de_key(VK_BACK,0,0);
  assert(exr_edit_block_count(de.doc)==1);de_key('Z',1,0);
  de_key('Y',1,0);assert(exr_edit_block_count(de.doc)==1);
  printf("4 PASS UTF-8: runs 0:1,0:3,2:3,2:7 -> block 1; Shift selects CJK+emoji; selection_pixels=%zu; replace undo; Delete/Backspace join; redo\n",selection_pixels);
  de_close();assert(de_open(path));reset_caret();de_character(L'A');de_character(L'B');de_character(L'C');
  de_key(VK_RETURN,0,0);de_character(0x4e2d);de_character(0xd83d);de_character(0xde42);
  char *expected=model_text(de.doc);assert(de.dirty==1);de_key('S',1,0);assert(de.dirty==0);
  file_text_equal(path,expected);
  printf("5 PASS Ctrl+S -> exr_edit_docx_open text_equal=1 bytes=%zu path=%s\n",strlen(expected),path);
  de_close();assert(de_open(path));same_text(expected);free(expected);
  de_character(L'!');assert(de.dirty==1);
  wchar_t title[600];de_title_text(title);assert(wcschr(title,L'*'));
  char saved_path[MAX_PATH];strcpy(saved_path,de.path);strcpy(de.path,"Z:/missing-dir/edited.docx");
  assert(!de_save() && de.dirty==1);strcpy(de.path,saved_path);
  assert(!de_exit_choice(IDCANCEL) && de.doc && de.dirty==1);
  assert(de_exit_choice(IDYES) && !de.doc);assert(de_open(path));
  assert(de.dirty==0);de_title_text(title);assert(!wcschr(title,L'*'));
  de_character(L'?');assert(de_exit_choice(IDNO) && !de.doc);
  puts("6 PASS edit dirty=1 title=*; save dirty=0 title=no*; reopen dirty=0; failed save dirty=1; exit Cancel/Save/Discard");
  seed_runs();
  for(int i=0;i<60;i++) {de_key(VK_END,1,0);de_key(VK_RETURN,0,0);de_character(L'x');}
  assert(de_measure(300,120));de_key(VK_NEXT,0,0);assert(de.scroll_y==120);
  de_key(VK_PRIOR,0,0);assert(de.scroll_y==0);
  de_key(VK_HOME,1,0);de_key(VK_DOWN,0,0);assert(de.caret_block>0);
  de_key(VK_UP,0,0);assert(de.caret_block==0);
  de_key('A',1,0);assert(de_selected());de_character(L'Q');assert(exr_edit_block_count(de.doc)==1);
  de_key('Z',1,0);assert(exr_edit_block_count(de.doc)==62);
  puts("extra PASS Home/End, Up/Down, PageUp/PageDown=viewport 120, Ctrl+A replace/undo, empty paragraph typing");
  g.has_current=1;g.session.active=1;g.current.format=EXR_DOCX;assert(de_eligible());
  g.current.format=EXR_TXT;assert(!de_eligible());g.has_current=g.session.active=0;
  seed_runs();
  /* Roll back earlier run changes if the selection reaches protected XML. */
  exr_edit_run protected_runs[3]={{0}};
  protected_runs[0].text="left";protected_runs[0].text_size=4;
  protected_runs[1].kind=EXR_EDIT_OPAQUE_RUN;protected_runs[1].opaque_xml="<w:bookmarkStart w:id=\"7\" w:name=\"keep\"/>";
  protected_runs[1].opaque_size=strlen(protected_runs[1].opaque_xml);
  protected_runs[2].text="right";protected_runs[2].text_size=5;
  exr_edit_id protected_id=0;assert(exr_edit_insert_paragraph(de.doc,0,protected_runs,3,NULL,&protected_id)==EXR_OK);
  de.dirty=0;de_set_anchor(de_start(0));de_set_caret(de_end(0));
  char *protected_before=model_text(de.doc);assert(!de_edit(DE_TYPE,"X",1));same_text(protected_before);
  assert(de.dirty==0);free(protected_before);
  puts("extra PASS DOCX enabled / TXT disabled; protected XML selection rolls back preceding text changes; dirty stays 0");
  exr_edit_block template={0};
  template.opaque_xml="<w:p><w:pPr><w:spacing w:before=\"120\"/></w:pPr></w:p>";
  template.opaque_size=strlen(template.opaque_xml);assert(de_rebuild_safe(&template));
  template.opaque_xml="<w:p><w:pPr><w:pStyle w:val=\"Heading1\"/></w:pPr></w:p>";
  template.opaque_size=strlen(template.opaque_xml);assert(!de_rebuild_safe(&template));
  puts("API boundary PASS rebuild preserves modeled properties; unmodeled paragraph templates protected (no engine changes)");
  de_close();shell_d2d_destroy(host_shell);host_shell=NULL;
  exr_font_free(g.font);exr_font_manager_free(g.font_manager);CoUninitialize();
  puts("M-E1 console acceptance PASS (no HWND / no SendInput)");return 0;
}
