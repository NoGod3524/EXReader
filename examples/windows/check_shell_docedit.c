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
static void rich_seed(const char *text,const char *path) {
  de_close();memset(&de,0,sizeof(de));
  exr_edit_run run={0};run.text=text;run.text_size=strlen(text);
  run.props.present=EXR_EDIT_SIZE|EXR_EDIT_FONT|EXR_EDIT_BOLD;
  run.props.size_half_points=24;strcpy(run.props.font,"Segoe UI");
  exr_edit_block block={0};block.runs=&run;block.run_count=1;
  assert(exr_edit_doc_create(NULL,0,&block,1,NULL,0,NULL,&de.doc)==EXR_OK);
  strcpy(de.path,path);de.layout_dirty=1;reset_caret();assert(de_measure(600,240));
}
static const exr_edit_run *rich_run(size_t run) {return &exr_edit_block_at(de.doc,0)->runs[run];}
static void rich_readback(unsigned bold) {
  de_key('S',1,0);exr_edit_doc *doc=NULL;exr_error error={0};
  assert(exr_edit_docx_open(de.path,NULL,&doc,&error)==EXR_OK);
  const exr_edit_run_props *props=&exr_edit_block_at(doc,0)->runs[0].props;
  assert((props->present&EXR_EDIT_BOLD) && props->bold==bold);exr_edit_doc_free(doc);
}
static int rich_ink_height(void) {
  de_set_anchor(de_caret_pos());de.blink=0;
  uint32_t *pixels=paint_memory(600,240);int first=240,last=-1;
  uint32_t background=pixels[239*600];
  for(int y=(int)de_toolbar_height();y<240;y++)for(int x=0;x<600;x++)
    if((pixels[y*600+x]&0xffffff)!=(background&0xffffff)) {
      if(y<first)first=y;if(y>last)last=y;
    }
  free(pixels);return last>=first ? last-first+1:0;
}
static void rich_click(int command) {
  RECT box=de_toolbar_box(command);
  assert(de_toolbar_click((box.left+box.right)/2.f,(box.top+box.bottom)/2.f));
}
static void rich_acceptance(const char *directory) {
  char path[MAX_PATH],bmp[MAX_PATH];snprintf(path,sizeof(path),"%s/rich-edited.docx",directory);
  rich_seed("甲乙丙丁戊ABCDE",path);
  for(int i=0;i<5;i++)de_key(VK_RIGHT,0,1);
  assert(de.caret.byte==15 && de_selected());assert(de_key('B',1,0));
  assert(rich_run(0)->props.bold==1);rich_readback(1);
  puts("E2c 1 PASS select=5 Ctrl+B write/open present.BOLD=1 bold=1 (partial selection -> whole run)");
  assert(de_key('B',1,0));assert(rich_run(0)->props.bold==0);rich_readback(0);
  puts("E2c 2 PASS Ctrl+B again write/open present.BOLD=1 bold=0 (explicit override)");
  int before=rich_ink_height();de_set_anchor(de_start(0));de_set_caret(de_end(0));
  assert(de_key(VK_OEM_PERIOD,1,1));assert(rich_run(0)->props.size_half_points==26);
  int after=rich_ink_height();assert(before!=after);
  printf("E2c 3 PASS Ctrl+Shift+. size_half_points=24->26 points=12->13 ink_height=%d->%d px\n",before,after);
  de_set_anchor(de_start(0));de_set_caret(de_end(0));rich_click(DE_COLOR);assert(de.color_panel);
  RECT red=de_color_box(2);assert(de_toolbar_click((red.left+red.right)/2.f,(red.top+red.bottom)/2.f));
  assert(!de.color_panel && rich_run(0)->props.color_rgb==0xff0000);
  de_set_anchor(de_caret_pos());de.blink=0;uint32_t *pixels=paint_memory(600,240);size_t red_pixels=0;
  for(int y=(int)de_toolbar_height();y<240;y++)for(int x=0;x<600;x++) {
    uint32_t rgb=pixels[y*600+x];red_pixels+=((rgb>>16)&255)>180 && ((rgb>>8)&255)<100 && (rgb&255)<100;
  }
  assert(red_pixels>0);snprintf(bmp,sizeof(bmp),"%s/rich-red.bmp",directory);save_bitmap(bmp,pixels,600,240);free(pixels);
  printf("E2c 4 PASS toolbar palette red=FF0000 text_red_pixels=%zu bitmap=%s\n",red_pixels,bmp);
  rich_seed("prefix",path);de_set_caret(de_end(0));de_set_anchor(de_caret_pos());
  de_key('B',1,0);assert(de.pending_props.bold && !de.dirty && !rich_run(0)->props.bold);
  de_character(L'A');de_character(L'B');
  assert(!strcmp(rich_run(0)->text,"prefix") && !rich_run(0)->props.bold);
  assert(!strcmp(rich_run(1)->text,"AB") && rich_run(1)->props.bold && (rich_run(1)->props.present&EXR_EDIT_BOLD));
  de_key('S',1,0);exr_edit_doc *read=NULL;exr_error error={0};
  assert(exr_edit_docx_open(path,NULL,&read,&error)==EXR_OK);
  const exr_edit_block *readblock=exr_edit_block_at(read,0);
  assert(!readblock->runs[0].props.bold && readblock->runs[1].props.bold);
  exr_edit_doc_free(read);
  puts("E2c 5 PASS no selection Ctrl+B then AB: prefix.bold=0 AB.bold=1; write/open retained");
  float x[3];const WPARAM keys[]={'L','E','R'};
  for(int i=0;i<3;i++) {
    de_key(keys[i],1,0);assert(de_measure(600,240));float box[4];
    shell_d2d_edit_position(de.rows[0].layout,0,box);x[i]=de.inset+box[0];
    de_pos hit=de_hit(x[i]+1,de.rows[0].y+box[1]+box[3]*.5f-de.scroll_y);
    assert(hit.block==0 && hit.byte==0);
    pixels=paint_memory(600,240);free(pixels);
  }
  assert(x[0]<x[1] && x[1]<x[2]);de_key('J',1,0);
  assert(exr_edit_block_at(de.doc,0)->props.alignment==EXR_EDIT_JUSTIFY);
  printf("E2c 6 PASS Ctrl+L/E/R line_start_x=%.2f/%.2f/%.2f px; hit-test roundtrip; Ctrl+J=JUSTIFY\n",x[0],x[1],x[2]);
  rich_seed("leftRIGHT",path);de_pos middle={0,0,4};de_set_caret(middle);de_set_anchor(middle);
  de_key('I',1,0);de_character(L'X');
  assert(!strcmp(rich_run(0)->text,"left") && !rich_run(0)->props.italic);
  assert(!strcmp(rich_run(1)->text,"X") && rich_run(1)->props.italic);
  assert(!strcmp(rich_run(2)->text,"RIGHT") && !rich_run(2)->props.italic);
  de_key('Z',1,0);assert(!strcmp(rich_run(0)->text,"leftRIGHT"));
  de_key('Y',1,0);assert(rich_run(1)->props.italic);
  de_key(VK_LEFT,0,0);assert(!de.pending_props.present);
  de_key('A',1,0);rich_click(DE_BOLD);
  for(size_t i=0;i<exr_edit_block_at(de.doc,0)->run_count;i++)assert(rich_run(i)->props.bold);
  rich_click(DE_SMALLER);assert(rich_run(0)->props.size_half_points==22);
  rich_click(DE_LARGER);assert(rich_run(0)->props.size_half_points==24);
  rich_click(DE_ITALIC);assert(rich_run(1)->props.italic);
  rich_click(DE_ITALIC);assert(!rich_run(1)->props.italic);
  puts("E2c extra PASS middle insertion isolates both neighbors; undo/redo; move clears pending; toolbar B/I/size; multi-run selection");
  de_close();memset(&de,0,sizeof(de));
  const char *styles="<w:styles><w:docDefaults><w:rPrDefault><w:rPr><w:sz w:val=\"24\"/>"
    "<w:rFonts w:ascii=\"Segoe UI\"/></w:rPr></w:rPrDefault></w:docDefaults>"
    "<w:style w:styleId=\"Base\"><w:rPr><w:b/></w:rPr></w:style>"
    "<w:style w:type=\"paragraph\" w:styleId=\"Body\" w:default=\"1\">"
    "<w:basedOn w:val=\"Base\"/><w:rPr><w:sz w:val=\"28\"/></w:rPr></w:style>"
    "<w:style w:styleId=\"Em\"><w:rPr><w:i/></w:rPr></w:style></w:styles>";
  exr_edit_part part={0};part.name="word/styles.xml";part.data=styles;part.size=strlen(styles);
  exr_edit_run styled={0};styled.text="styled";styled.text_size=6;
  styled.opaque_xml="<w:r><w:rPr><w:rStyle w:val=\"Em\"/></w:rPr><w:t>styled</w:t></w:r>";
  styled.opaque_size=strlen(styled.opaque_xml);
  exr_edit_block styled_block={0};styled_block.runs=&styled;styled_block.run_count=1;
  styled_block.opaque_xml="<w:p><w:pPr><w:pStyle w:val=\"Body\"/></w:pPr></w:p>";
  styled_block.opaque_size=strlen(styled_block.opaque_xml);
  assert(exr_edit_doc_create(NULL,0,&styled_block,1,&part,1,NULL,&de.doc)==EXR_OK);
  de.layout_dirty=1;reset_caret();exr_edit_run_props effective=de_current_props();
  assert(effective.bold && effective.italic && effective.size_half_points==28 && !strcmp(effective.font,"Segoe UI"));
  de_set_caret(de_end(0));de_set_anchor(de_caret_pos());de_key('B',1,0);assert(!de.pending_props.bold && (de.pending_props.present&EXR_EDIT_BOLD));
  assert(!de_edit(DE_TYPE,"X",1) && !strcmp(rich_run(0)->text,"styled") && !de.dirty);
  assert(de.pending_props.present&EXR_EDIT_BOLD); /* Protected templates keep the pending edit. */
  de_set_anchor(de_start(0));de_key('B',1,0);assert(rich_run(0)->props.bold);
  de_key('B',1,0);assert(!rich_run(0)->props.bold && (rich_run(0)->props.present&EXR_EDIT_BOLD));
  pixels=paint_memory(600,240);free(pixels);
  puts("E2c extra PASS docDefaults / paragraph basedOn / character style inheritance; explicit bold=0; protected pending insertion rolls back");
  rich_seed("fallback",path);de.blink=0;uint32_t *default_pixels=paint_memory(600,240);
  exr_edit_run_props props=rich_run(0)->props;
  strcpy(props.font,"EXReader Missing Font E2c");
  assert(exr_edit_set_run_props(de.doc,exr_edit_block_at(de.doc,0)->id,0,&props)==EXR_OK);
  de.layout_dirty=1;pixels=paint_memory(600,240);
  assert(!memcmp(default_pixels,pixels,600*240*4));free(default_pixels);free(pixels);
  puts("E2c fonts fallback list: EXReader Missing Font E2c -> current default (Segoe UI)");
  puts("M-E2c console acceptance PASS (no HWND / no SendInput)");
}
static void footnote_acceptance(const char *directory) {
  char path[MAX_PATH];snprintf(path,sizeof(path),"%s/footnotes-edited.docx",directory);
  rich_seed("leftRIGHT",path);de_pos middle={0,0,4};de_set_caret(middle);de_set_anchor(middle);
  rich_click(DE_INSERT_FOOTNOTE);
  exr_edit_footnote first={0},second={0};assert(exr_edit_footnote_count(de.doc)==1);
  assert(exr_edit_footnote_at(de.doc,0,&first)==EXR_OK && first.number==1);
  assert(de_footnote_update(first.id,"note1",5));
  wchar_t *body=de_paragraph_text(de_block_at(de.doc,0));
  assert(body && !wcscmp(body,L"left¹RIGHT"));free(body);
  assert(de_measure(600,240) && de.footnote_row_count==2);
  uint32_t *pixels=paint_memory(600,240);char bitmap[MAX_PATH];
  snprintf(bitmap,sizeof(bitmap),"%s/footnotes-editor.bmp",directory);save_bitmap(bitmap,pixels,600,240);free(pixels);
  /* A hidden page creates the real outline; g.window stays NULL to avoid a modal note editor. */
  assert(!g.page && !g.window);
  g.page=CreateWindowW(L"STATIC",L"Footnote outline acceptance",WS_POPUP,
    0,0,600,240,NULL,NULL,GetModuleHandleW(NULL),NULL);assert(g.page);
  de.layout_dirty=1;assert(de_measure(600,240) && de_outline_width(600)==200);
  float margin=(float)shell_px(24,shell_dpi);
  shell_d2d_edit_row *last=&de.rows[de.row_count-1],*title=&de.rows[de.row_count],
    *note=&de.rows[de.row_count+1];
  float gap=title->y-last->y-last->height-shell_px(8,shell_dpi);
  assert(gap>margin-.5f && gap<margin+.5f);
  assert(de_footnote_click(600-margin-1,note->y+note->height*.5f-de.scroll_y));
  de_outline_close();DestroyWindow(g.page);g.page=NULL;
  de.layout_dirty=1;assert(de_measure(600,240));
  puts("L14 PASS outline preserves footnote vertical margin and right-edge editing");
  rich_click(DE_INSERT_FOOTNOTE);assert(exr_edit_footnote_count(de.doc)==2);
  assert(exr_edit_footnote_at(de.doc,1,&second)==EXR_OK && second.number==2);
  assert(de_footnote_update(second.id,"note2",5));assert(de_save());
  de_close();assert(de_open(path));assert(exr_edit_footnote_count(de.doc)==2);
  assert(exr_edit_footnote_at(de.doc,0,&first)==EXR_OK && first.text_size==5 && !memcmp(first.text,"note1",5));
  assert(de_footnote_remove(first.id));assert(exr_edit_footnote_count(de.doc)==1);
  assert(exr_edit_footnote_at(de.doc,0,&second)==EXR_OK && second.number==1 && !strcmp(second.text,"note2"));
  assert(de_history(0)==EXR_OK && exr_edit_footnote_count(de.doc)==2);
  assert(de_history(1)==EXR_OK && exr_edit_footnote_count(de.doc)==1);
  assert(de_save());de_close();assert(de_open(path));
  assert(exr_edit_footnote_at(de.doc,0,&second)==EXR_OK && second.number==1 && !strcmp(second.text,"note2"));
  reset_caret();body=de_paragraph_text(de_block_at(de.doc,de.caret.view));
  assert(body && !wcscmp(body,L"left¹RIGHT"));free(body);
  /* References are one atomic caret step and can be deleted from the body. */
  de_pos before={de.caret.view,0,4};de_set_caret(before);de_set_anchor(before);
  assert(de_key(VK_DELETE,0,0) && exr_edit_footnote_count(de.doc)==0);
  assert(de_history(0)==EXR_OK && exr_edit_footnote_count(de.doc)==1);
  puts("L14 PASS toolbar at cursor; superscript body; footer note1; save/reopen; delete/renumber=1; undo/redo; body Delete");
}
int main(int argc,char **argv) {
  assert(argc==3);setvbuf(stdout,NULL,_IONBF,0);
  SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);
  assert(SUCCEEDED(CoInitializeEx(NULL,COINIT_APARTMENTTHREADED)));
  assert(SUCCEEDED(shell_d2d_create(NULL,&host_shell)));shell_dpi=96;shell_apply_theme();
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
  const exr_edit_block *first=exr_edit_block_at(de.doc,de.caret.view);
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
    de_key(VK_RIGHT,0,0);assert(de.caret.run==expected_run[i] && de.caret.byte==expected_byte[i]);
    assert(de.caret.view==(i==4 ? 1u:0u));
  }
  de_key(VK_LEFT,0,0);assert(de.caret.view==0 && de.caret.run==2 && de.caret.byte==7);
  de_key(VK_LEFT,0,1);de_key(VK_LEFT,0,1);assert(de_selected());
  assert(de.caret.run==0 && de.caret.byte==3);
  de.blink=0;uint32_t *selection=paint_memory(600,240);de_set_anchor(de_caret_pos());
  uint32_t *unselected=paint_memory(600,240);size_t selection_pixels=0;
  for(size_t i=0;i<600*240;i++)selection_pixels+=selection[i]!=unselected[i];
  assert(selection_pixels>0);free(selection);free(unselected);
  de_key(VK_RIGHT,0,1);de_key(VK_RIGHT,0,1);char *before=model_text(de.doc);
  de_character(L'X');de_key('Z',1,0);same_text(before);free(before);
  reset_caret();de_set_caret(de_end(0));de_set_anchor(de_caret_pos());
  de_key(VK_DELETE,0,0);assert(exr_edit_block_count(de.doc)==1);
  de_key('Z',1,0);assert(exr_edit_block_count(de.doc)==2);
  de_set_caret(de_start(1));de_set_anchor(de_caret_pos());de_key(VK_BACK,0,0);
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
  de_key(VK_HOME,1,0);de_key(VK_DOWN,0,0);assert(de.caret.view>0);
  de_key(VK_UP,0,0);assert(de.caret.view==0);
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
  rich_acceptance(argv[2]);
  footnote_acceptance(argv[2]);
  de_close();shell_d2d_destroy(host_shell);host_shell=NULL;
  exr_font_free(g.font);exr_font_manager_free(g.font_manager);CoUninitialize();
  puts("M-E1 console acceptance PASS (no HWND / no SendInput)");return 0;
}
