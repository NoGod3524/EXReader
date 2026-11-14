/* SPDX-License-Identifier: MIT */
/* Exercise the real editor with a memory DC and hidden outline; no SendInput. */
#define main docedit_baseline_main
#include "check_shell_docedit.c"
#undef main

extern void XML_SetCharacterDataHandler(void *,void (*)(void *,const char *,int));

typedef struct { int depth,section_depth,paragraph_depth,run_depth,text_depth,title,even,page,date; cv_text text; } hf_xml;
static void hf_xml_start(void *context,const char *name,const char **attrs) {
  hf_xml *x=context;const char *local=de_local(name);x->depth++;
  if(!strcmp(local,"sectPr"))x->section_depth=x->depth;
  if(!strcmp(local,"p") && x->depth==2)x->paragraph_depth=x->depth;
  if(!strcmp(local,"r") && x->paragraph_depth && x->depth==x->paragraph_depth+1)x->run_depth=x->depth;
  if(!strcmp(local,"t") && x->run_depth && x->depth==x->run_depth+1)x->text_depth=x->depth;
  if(!strcmp(local,"fldSimple")) {
    const char *instruction=de_attribute(attrs,"instr");
    if(strstr(instruction," PAGE "))x->page++;
    if(strstr(instruction," DATE "))x->date++;
  }
  const char *val=de_attribute(attrs,"val");
  int enabled=strcmp(val,"0") && strcmp(val,"false") && strcmp(val,"off");
  if(!strcmp(local,"titlePg") && x->section_depth && enabled)x->title++;
  if(!strcmp(local,"evenAndOddHeaders") && enabled)x->even++;
}
static void hf_xml_end(void *context,const char *name) {
  hf_xml *x=context;(void)name;
  if(x->text_depth==x->depth)x->text_depth=0;
  if(x->run_depth==x->depth)x->run_depth=0;
  if(x->paragraph_depth==x->depth)x->paragraph_depth=0;
  if(x->section_depth==x->depth)x->section_depth=0;
  x->depth--;
}
static void hf_xml_text(void *context,const char *text,int n) {
  hf_xml *x=context;if(x->text_depth)cv_text_append(&x->text,text,(size_t)n);
}
static hf_xml hf_parse_part(exr_edit_doc *doc,const char *name) {
  size_t count=0;const exr_edit_part *parts=exr_edit_parts(doc,&count),*part=NULL;
  for(size_t i=0;i<count;i++)if(!strcmp(parts[i].name,name)) {part=&parts[i];break;}
  assert(part && part->size<=INT_MAX);
  void *parser=XML_ParserCreate(NULL);assert(parser);hf_xml x={0};
  XML_SetUserData(parser,&x);XML_SetElementHandler(parser,hf_xml_start,hf_xml_end);
  XML_SetCharacterDataHandler(parser,hf_xml_text);
  assert(XML_Parse(parser,part->data,(int)part->size,1)==1);XML_ParserFree(parser);
  cv_text_string(&x.text,"");assert(!x.text.failed);return x;
}
static exr_edit_id hf_section(void) {
  size_t count=0;const exr_edit_section *sections=exr_edit_sections(de.doc,&count);
  assert(count==1);return sections[0].id;
}
static void hf_expect(unsigned footer,unsigned variant,const char *expected) {
  char *text=NULL;size_t size=0;
  assert(exr_edit_header_footer_text(de.doc,hf_section(),footer,variant,&text,&size)==EXR_OK);
  assert(size==strlen(expected) && !memcmp(text,expected,size));exr_free(text);
}
static void hf_double(RECT box) {
  assert(de_message(NULL,WM_LBUTTONDBLCLK,0,MAKELPARAM((box.left+box.right)/2,(box.top+box.bottom)/2)));
}
static RECT hf_body_box(void) {
  assert(de_measure(800,600));assert(de.row_count);
  shell_d2d_edit_row *row=&de.rows[0];
  RECT box={(LONG)de.inset,(LONG)(row->y-de.scroll_y),(LONG)(800-de.inset),
    (LONG)(row->y+row->height-de.scroll_y)};return box;
}
static unsigned hf_body_contrast(uint32_t *pixels,RECT box) {
  uint32_t background=pixels[599*800];unsigned maximum=0;
  for(int y=box.top;y<box.bottom && y<600;y++)for(int x=box.left;x<box.right && x<800;x++) {
    assert(y>=0 && x>=0);uint32_t p=pixels[y*800+x];unsigned distance=0;
    for(unsigned channel=0;channel<24;channel+=8)
      distance+=(unsigned)abs((int)((p>>channel)&255)-(int)((background>>channel)&255));
    if(distance>maximum)maximum=distance;
  }
  return maximum;
}
static void hf_save_reopen(const char *path) {
  assert(de_key('S',1,0) && !de.dirty);de_close();assert(de_open(path));assert(de_measure(800,600));
}
static void hf_lane_union_acceptance(void) {
  de_close();memset(&de,0,sizeof(de));
  exr_edit_run runs[2]={{0}};exr_edit_block blocks[2]={{0}};
  runs[0].text="Heading";runs[0].text_size=7;runs[1].text="Body";runs[1].text_size=4;
  for(size_t i=0;i<2;i++) {blocks[i].runs=&runs[i];blocks[i].run_count=1;}
  const char *heading="<w:p><w:pPr><w:pStyle w:val=\"Heading1\"/></w:pPr></w:p>";
  blocks[0].opaque_xml=heading;blocks[0].opaque_size=strlen(heading);
  /* Retained paragraph templates require their original OPC main part. */
  const char *main="<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\"><w:body>"
    "<w:p><w:pPr><w:pStyle w:val=\"Heading1\"/></w:pPr></w:p>"
    "<w:p><w:r><w:t>Body</w:t></w:r></w:p><w:sectPr/></w:body></w:document>";
  const char *rels="<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
    "<Relationship Id=\"main\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" "
    "Target=\"word/document.xml\"/></Relationships>";
  const char *types="<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
    "<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>"
    "<Default Extension=\"xml\" ContentType=\"application/xml\"/>"
    "<Override PartName=\"/word/document.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml\"/></Types>";
  const char *names[]={"word/document.xml","_rels/.rels","[Content_Types].xml"},*values[]={main,rels,types};
  exr_edit_part parts[3]={{0}};
  for(size_t i=0;i<3;i++) {parts[i].name=names[i];parts[i].data=values[i];parts[i].size=strlen(values[i]);}
  assert(exr_edit_doc_create(NULL,0,blocks,2,parts,3,NULL,&de.doc)==EXR_OK);
  exr_edit_id heading_id=de_block_at(de.doc,0)->id,note_id=0;
  assert(exr_edit_footnote_insert(de.doc,de_block_at(de.doc,1)->id,0,4,"Note",4,&note_id)==EXR_OK);
  assert(exr_edit_set_header_footer_text(de.doc,hf_section(),0,0,"Header",6)==EXR_OK);
  assert(exr_edit_set_header_footer_text(de.doc,hf_section(),1,0,"Footer",6)==EXR_OK);
  assert(!g.page && !g.window);
  g.page=CreateWindowW(L"STATIC",L"Three lane acceptance",WS_POPUP,
    0,0,800,600,NULL,NULL,GetModuleHandleW(NULL),NULL);assert(g.page);
  de_set_caret(de_start(1));de_set_anchor(de_caret_pos());de.layout_dirty=1;
  assert(de_measure(800,600) && deo.count==1 && de.footnote_row_count==2);
  float margin=(float)shell_px(24,shell_dpi);assert(de.inset==margin+240);
  shell_d2d_edit_row *header=&de.hf_rows[0],*body=&de.rows[1],
    *note=&de.rows[de.row_count+de.footnote_row_count-1],*footer=&de.hf_rows[1];
  assert(header->y+header->height<=de.rows[0].y);
  assert(body->y+body->height<note->y && note->y+note->height<footer->y);
  assert(header->y>=de_toolbar_height() && footer->y+footer->height<=600);
  de.blink=0;uint32_t *pixels=paint_memory(800,600);
  shell_d2d_edit_row *rows[]={header,body,note,footer};
  for(size_t i=0;i<sizeof(rows)/sizeof(*rows);i++) {
    RECT box={(LONG)de.inset,(LONG)(rows[i]->y-de.scroll_y),800-(LONG)margin,
      (LONG)(rows[i]->y+rows[i]->height-de.scroll_y)};
    assert(hf_body_contrast(pixels,box)>0);
  }
  free(pixels);
  rich_click(DE_HEADER);assert(de.hf_mode==1);
  assert(de_key(VK_ESCAPE,0,0) && !de.hf_mode);
  assert(de_key('O',1,1) && GetFocus()==deo.tree);
  assert(TreeView_SelectItem(deo.tree,NULL));
  assert(TreeView_SelectItem(deo.tree,deo.items[0].node));
  assert(de_block_at(de.doc,de.caret.view)->id==heading_id && !de_selected());
  de_set_caret(de_start(1));de_set_anchor(de_caret_pos());
  rich_click(DE_HEADER);assert(de.hf_mode==1);
  assert(!de_command(DE_INSERT_FOOTNOTE,0) && de.hf_mode==1 && exr_edit_footnote_count(de.doc)==1);
  assert(de_key('O',1,1) && !de.hf_mode && GetFocus()==deo.tree);
  rich_click(DE_HEADER);assert(de.hf_mode==1);
  assert(TreeView_SelectItem(deo.tree,NULL) && de.hf_mode==1);
  assert(TreeView_SelectItem(deo.tree,deo.items[0].node));
  assert(!de.hf_mode && de_block_at(de.doc,de.caret.view)->id==heading_id && !de_selected());
  hf_expect(0,0,"Header");hf_expect(1,0,"Footer");assert(exr_edit_footnote_count(de.doc)==1);
  de_close();DestroyWindow(g.page);g.page=NULL;
  puts("L13/L14/L15 PASS outline/body/footnote/header/footer layout and pixels; header Esc/shortcut/tree return to body; note insertion blocked in header");
}

int main(int argc,char **argv) {
  assert(argc==2);setvbuf(stdout,NULL,_IONBF,0);
  SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);
  assert(SUCCEEDED(CoInitializeEx(NULL,COINIT_APARTMENTTHREADED)));
  assert(SUCCEEDED(shell_d2d_create(NULL,&host_shell)));shell_dpi=96;shell_apply_theme();
  wchar_t *directory=host_wide(argv[1],strlen(argv[1]));assert(directory);
  ensure_directory(directory);copy_wstring(g.data_dir,HOST_PATH,directory);free(directory);
  exr_error error={0};assert(host_open_body_font(L"C:\\Windows\\Fonts\\segoeui.ttf",L"",&error)==EXR_OK);
  char path[MAX_PATH],bitmap[MAX_PATH];snprintf(path,sizeof(path),"%s/header-footer-ui.docx",argv[1]);
  rich_seed("body retained",path);assert(de_save());de_close();assert(de_open(path));assert(de_measure(800,600));
  char *body=model_text(de.doc);de.blink=0;uint32_t *normal=paint_memory(800,600);
  unsigned normal_contrast=hf_body_contrast(normal,hf_body_box());free(normal);
  RECT drag_body=hf_body_box(),drag_header=de_hf_box(0);
  assert(de_message(NULL,WM_LBUTTONDOWN,0,MAKELPARAM(drag_body.left+2,drag_body.top+2)) && de.mouse_down);
  assert(de_message(NULL,WM_MOUSEMOVE,0,MAKELPARAM(drag_header.left+2,drag_header.top+2)));
  assert(de_message(NULL,WM_LBUTTONUP,0,MAKELPARAM(drag_header.left+2,drag_header.top+2)) && !de.mouse_down);
  reset_caret();
  hf_double(de_hf_box(0));assert(de.hf_mode==1 && de.doc);
  drag_header=de_hf_box(0);
  assert(de_message(NULL,WM_LBUTTONDOWN,0,MAKELPARAM(drag_header.left+2,drag_header.top+22)) && de.mouse_down);
  assert(de_message(NULL,WM_MOUSEMOVE,0,MAKELPARAM(10,8)));
  assert(de_message(NULL,WM_LBUTTONUP,0,MAKELPARAM(10,8)) && !de.mouse_down && de.hf_mode==1);
  hf_double(de_hf_box(0));
  assert(de_measure(800,600));RECT body_box=hf_body_box();de_caret original_caret=de.caret;
  assert(de_message(NULL,WM_LBUTTONDOWN,0,MAKELPARAM(body_box.right-2,body_box.top+2)));
  assert(de_message(NULL,WM_LBUTTONUP,0,0));
  assert(de.hf_mode==1 && !memcmp(&original_caret,&de.caret,sizeof(de.caret)));
  de_character(L'H');de_character(L'D');de_character(L'R');hf_expect(0,0,"HDR");same_text(body);
  de.blink=0;uint32_t *dimmed=paint_memory(800,600);
  assert(de.rows[0].dimmed);unsigned dim_contrast=hf_body_contrast(dimmed,hf_body_box());
  assert(dim_contrast>0 && dim_contrast<normal_contrast);
  snprintf(bitmap,sizeof(bitmap),"%s/header-mode.bmp",argv[1]);save_bitmap(bitmap,dimmed,800,600);free(dimmed);
  hf_save_reopen(path);hf_expect(0,0,"HDR");same_text(body);
  hf_xml header=hf_parse_part(de.doc,"word/header1.xml");
  assert(!strcmp(header.text.data,"HDR") && header.page==1 && header.date==1);cv_text_free(&header.text);
  printf("1 PASS double-click header -> type HDR -> save/reopen; header1.xml text=HDR; body locked, contrast=%u->%u\n",normal_contrast,dim_contrast);

  hf_double(de_hf_box(1));assert(de.hf_mode==2);
  de_character(L'F');de_character(L'T');de_character(L'R');hf_expect(1,0,"FTR");same_text(body);
  hf_save_reopen(path);hf_expect(0,0,"HDR");hf_expect(1,0,"FTR");
  hf_xml footer=hf_parse_part(de.doc,"word/footer1.xml");assert(!strcmp(footer.text.data,"FTR"));cv_text_free(&footer.text);
  puts("2 PASS double-click footer -> type FTR -> save/reopen; footer1.xml text=FTR; header=HDR retained");

  rich_click(DE_DIFFERENT_FIRST);hf_save_reopen(path);
  hf_xml document=hf_parse_part(de.doc,"word/document.xml");assert(document.title==1);cv_text_free(&document.text);
  unsigned first=0,even=0;assert(exr_edit_header_footer_flags(de.doc,hf_section(),&first,&even)==EXR_OK && first==1);
  rich_click(DE_DIFFERENT_FIRST);hf_save_reopen(path);
  document=hf_parse_part(de.doc,"word/document.xml");assert(document.title==0);cv_text_free(&document.text);
  assert(exr_edit_header_footer_flags(de.doc,hf_section(),&first,&even)==EXR_OK && first==0);
  rich_click(DE_DIFFERENT_EVEN);hf_save_reopen(path);
  hf_xml settings=hf_parse_part(de.doc,"word/settings.xml");assert(settings.even==1);cv_text_free(&settings.text);
  rich_click(DE_DIFFERENT_EVEN);hf_save_reopen(path);
  settings=hf_parse_part(de.doc,"word/settings.xml");assert(settings.even==0);cv_text_free(&settings.text);
  puts("3 PASS toolbar different-first: sectPr/titlePg 0->1->0; different-even: settings/evenAndOddHeaders 0->1->0; save/reopen each");

  rich_click(DE_HEADER);assert(de.hf_mode==1);assert(de_key(VK_ESCAPE,0,0));assert(!de.hf_mode && de.doc);
  de_character(L'A');assert(de.dirty);char *edited=model_text(de.doc);assert(strcmp(edited,body));free(edited);
  assert(de_key('Z',1,0));same_text(body);
  rich_click(DE_FOOTER);assert(de.hf_mode==2);hf_double(hf_body_box());assert(!de.hf_mode && de.doc);
  de_character(L'B');edited=model_text(de.doc);assert(strcmp(edited,body));free(edited);
  hf_expect(0,0,"HDR");hf_expect(1,0,"FTR");hf_save_reopen(path);hf_expect(0,0,"HDR");hf_expect(1,0,"FTR");
  edited=model_text(de.doc);assert(strcmp(edited,body));free(edited);free(body);
  puts("4 PASS Esc and double-click body leave header/footer without closing editor; body typing/undo/save/reopen work; HDR/FTR unchanged");

  rich_click(DE_HEADER);assert(de_key('A',1,0));
  de_character(0x4e2d);de_character(0xd83d);de_character(0xde42);hf_expect(0,0,"\xe4\xb8\xad\xf0\x9f\x99\x82");
  assert(de_key(VK_BACK,0,0));hf_expect(0,0,"\xe4\xb8\xad");
  assert(de_key('Z',1,0));hf_expect(0,0,"\xe4\xb8\xad\xf0\x9f\x99\x82");
  assert(de_key('Y',1,0));hf_expect(0,0,"\xe4\xb8\xad");
  assert(de_key('A',1,0));assert(de_key(VK_RETURN,0,0));
  de_character(L'H');de_character(L'D');de_character(L'R');
  assert(de_key(VK_RETURN,0,0));assert(de_key(VK_RETURN,0,0));hf_expect(0,0,"\nHDR\n\n");
  hf_save_reopen(path);hf_expect(0,0,"\nHDR\n\n");rich_click(DE_HEADER);
  assert(de_key('A',1,0));de_character(L'H');de_character(L'D');de_character(L'R');
  rich_click(DE_DIFFERENT_FIRST);rich_click(DE_VARIANT);assert(de.hf_variant==1);
  assert(de_key('Z',1,0) && !de.hf_variant);
  assert(de_key('Y',1,0));rich_click(DE_VARIANT);assert(de.hf_variant==1);
  de_character(L'F');de_character(L'I');de_character(L'R');de_character(L'S');de_character(L'T');hf_expect(0,1,"FIRST");
  rich_click(DE_DIFFERENT_EVEN);rich_click(DE_VARIANT);assert(de.hf_variant==2);
  de_character(L'E');de_character(L'V');de_character(L'E');de_character(L'N');hf_expect(0,2,"EVEN");
  rich_click(DE_VARIANT);assert(!de.hf_variant);hf_expect(0,0,"HDR");hf_expect(1,0,"FTR");
  hf_save_reopen(path);hf_expect(0,0,"HDR");hf_expect(0,1,"FIRST");hf_expect(0,2,"EVEN");hf_expect(1,0,"FTR");
  rich_click(DE_DIFFERENT_FIRST);rich_click(DE_DIFFERENT_EVEN);hf_save_reopen(path);
  puts("extra PASS header Ctrl+A, CJK/surrogate typing, scalar Backspace, undo/redo, leading/trailing empty paragraphs; toolbar default/first/even stories stay independent after reopen");
  puts("extra PASS drag release over header/toolbar clears mouse state; undoing first-page flag returns variant to default");
  assert(de.doc && !de.hf_mode);reset_caret();rich_click(DE_INSERT_FOOTNOTE);
  exr_edit_footnote note={0};assert(exr_edit_footnote_count(de.doc)==1);
  assert(exr_edit_footnote_at(de.doc,0,&note)==EXR_OK && de_footnote_update(note.id,"note1",5));
  assert(!g.page && !g.window);
  g.page=CreateWindowW(L"STATIC",L"Header footer outline acceptance",WS_POPUP,
    0,0,800,600,NULL,NULL,GetModuleHandleW(NULL),NULL);assert(g.page);
  de.layout_dirty=1;de.scroll_y=0;
  assert(de_measure(800,600) && deo.tree && de.footnote_row_count==2);
  float margin=(float)shell_px(24,shell_dpi);assert(de.inset==margin+de_outline_width(800));
  assert(de_outline_width(800)==shell_px(240,shell_dpi));
  shell_d2d_edit_row *regions[]={&de.hf_rows[0],&de.rows[0],&de.rows[de.row_count+1],&de.hf_rows[1]};
  uint32_t *combined=paint_memory(800,600);
  for(unsigned i=0;i<4;i++) {
    shell_d2d_edit_row *row=regions[i];
    RECT box={(LONG)de.inset,(LONG)row->y,(LONG)(800-margin),(LONG)(row->y+row->height)};
    assert(hf_body_contrast(combined,box)>0);
    if(i)assert(regions[i-1]->y+regions[i-1]->height<row->y);
  }
  free(combined);
  for(unsigned i=0;i<2;i++) {
    shell_d2d_edit_row *row=&de.hf_rows[i];
    assert(de_message(NULL,WM_LBUTTONDBLCLK,0,
      MAKELPARAM((int)(800-margin-1),(int)(row->y+row->height*.5f-de.scroll_y))));
    assert(de.hf_mode==i+1);
  }
  rich_click(DE_HEADER);SetFocus(g.page);
  rich_click(DE_INSERT_FOOTNOTE);assert(exr_edit_footnote_count(de.doc)==1 && de.hf_mode==1);
  assert(de_key('O',1,1) && GetFocus()==deo.tree && !de.hf_mode);
  assert(de.doc && !de.hf_mode);de.mouse_down=0;
  shell_d2d_edit_row *note_row=&de.rows[de.row_count+1];
  assert(de_message(NULL,WM_LBUTTONDOWN,0,
    MAKELPARAM((int)(800-margin-1),(int)(note_row->y+note_row->height*.5f-de.scroll_y))));
  assert(!de.hf_mode && !de.mouse_down);
  de_outline_close();DestroyWindow(g.page);g.page=NULL;
  puts("merge PASS outline/header/body/footnote/footer paint together; right-edge margin editing, header outline shortcut and footnote isolation");
  hf_lane_union_acceptance();
  de_close();shell_d2d_destroy(host_shell);host_shell=NULL;
  exr_font_free(g.font);exr_font_manager_free(g.font_manager);CoUninitialize();
  puts("L13 real-editor headless acceptance PASS (no SendInput)");return 0;
}
