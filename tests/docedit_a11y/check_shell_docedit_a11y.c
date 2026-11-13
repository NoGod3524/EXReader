/* SPDX-License-Identifier: MIT */
/* Actual host keyboard handlers, without windows, input injection or automation. */
#define WinMain reader_WinMain
#define EXR_READER_TEST_DRIVERS 1
#include "../reader.c"
#undef WinMain
#include <assert.h>

static const exr_edit_run *cell_run(exr_edit_doc *doc,exr_edit_id id,size_t row,size_t col) {
  const exr_edit_block *p=exr_edit_table_cell_paragraph(doc,id,row,col,0);
  assert(p && p->run_count);return &p->runs[0];
}
static void describe(const char *step) {
  assert(da.description[0]);
  char bytes[2400];assert(WideCharToMultiByte(CP_UTF8,0,da.description,-1,bytes,sizeof(bytes),NULL,NULL));
  printf("PASS %s description=%s\n",step,bytes);
}
static void press_command(int action,WPARAM key) {
  int focus=DA_TEXT;
  for(int i=0;i<DA_COUNT && focus!=action;i++)focus=da_next_control(focus,0);
  assert(focus==action && da_enabled(focus));
  assert(da_control_key(focus,key,0,0));
  char label[128];assert(WideCharToMultiByte(CP_UTF8,0,da_labels[action],-1,label,sizeof(label),NULL,NULL));
  printf("PASS keyboard-command=%s\n",label);
}
static void seed(const char *path) {
  const char *xml="<w:tbl xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\">"
    "<w:tblPr><w:tblW w:w=\"6000\" w:type=\"dxa\"/></w:tblPr>"
    "<w:tblGrid><w:gridCol w:w=\"3000\"/><w:gridCol w:w=\"3000\"/></w:tblGrid>"
    "<w:tr><w:tc><w:p><w:r><w:rPr><w:b/></w:rPr><w:t>alpha</w:t></w:r>"
    "<w:r><w:t>keep</w:t></w:r></w:p><w:p><w:r><w:t>second</w:t></w:r></w:p></w:tc>"
    "<w:tc><w:p><w:r><w:t>beta</w:t></w:r></w:p></w:tc></w:tr>"
    "<w:tr><w:tc><w:p/><w:p><w:r><w:t>gamma</w:t></w:r></w:p></w:tc>"
    "<w:tc><w:p><w:r><w:t>delta</w:t></w:r></w:p></w:tc></w:tr></w:tbl>";
  exr_edit_run run={0};run.text="body";run.text_size=4;
  exr_edit_block blocks[2]={{0}};blocks[0].runs=&run;blocks[0].run_count=1;
  blocks[1].kind=EXR_EDIT_TABLE;blocks[1].opaque_xml=xml;blocks[1].opaque_size=strlen(xml);
  assert(exr_edit_doc_create(NULL,0,blocks,2,NULL,0,NULL,&de.doc)==EXR_OK);
  strcpy(de.path,path);assert(de_save());de_close();
}
int main(int argc,char **argv) {
  assert(argc==3);setvbuf(stdout,NULL,_IONBF,0);
  SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);
  assert(SUCCEEDED(CoInitializeEx(NULL,COINIT_APARTMENTTHREADED)));
  shell_dpi=96;
  for(int i=0;i<DA_COUNT;i++)assert(da_labels[i][0] && da_help[i][0]);
  puts("PASS Chinese labels and descriptions for all 19 controls");
  /* File chooser completion supplies a path; all subsequent edits are keys. */
  seed(argv[2]);assert(de_open(argv[2]));describe("open-docx");
  assert(de_key('T',1,0) && da.table);describe("Ctrl+T-enter-table");
  int focus=DA_TEXT;
  for(int i=1;i<DA_COUNT;i++) {focus=da_next_control(focus,0);assert(focus==i);}
  assert(da_next_control(focus,0)==DA_TEXT);
  assert(da_next_control(DA_TEXT,1)==DA_BODY);
  assert(!da_control_key(DA_TEXT,VK_SPACE,0,0));
  puts("PASS Tab and Shift+Tab order, wrapping and editable Space");
  exr_edit_id id=da.table;assert(!strcmp(cell_run(de.doc,id,0,0)->text,"alpha"));
  da.row=1;da_update();page_procedure(NULL,WM_CHAR,L'E',0);
  assert(!strcmp(cell_run(de.doc,id,1,0)->text,"E"));
  assert(!strcmp(exr_edit_table_cell_paragraph(de.doc,id,1,0,1)->runs[0].text,"gamma"));
  de_key('Z',1,0);assert(!exr_edit_table_cell_paragraph(de.doc,id,1,0,0)->run_count);
  de_key('Y',1,0);assert(!strcmp(cell_run(de.doc,id,1,0)->text,"E"));
  da.row=da.col=da.para=da.run=da.byte=da.anchor=0;da_update();
  puts("PASS typing empty paragraph retains sibling paragraph and undo/redo");
  page_procedure(NULL,WM_CHAR,0x4e2d,0);page_procedure(NULL,WM_CHAR,0xd83d,0);page_procedure(NULL,WM_CHAR,0xde42,0);
  assert(!strcmp(cell_run(de.doc,id,0,0)->text,"\xe4\xb8\xad\xf0\x9f\x99\x82" "alpha"));
  assert(cell_run(de.doc,id,0,0)->props.bold);describe("keyboard-type-CJK-emoji");
  assert(de_key('S',1,0) && !de.dirty);describe("Ctrl+S-save");
  exr_edit_doc *read=NULL;exr_error error={0};
  assert(exr_edit_docx_open(argv[2],NULL,&read,&error)==EXR_OK);
  assert(!strcmp(cell_run(read,id,0,0)->text,cell_run(de.doc,id,0,0)->text));
  const exr_edit_block *p=exr_edit_table_cell_paragraph(read,id,0,0,0);
  assert(p->run_count==2 && !strcmp(p->runs[1].text,"keep"));
  assert(!strcmp(exr_edit_table_cell_paragraph(read,id,0,0,1)->runs[0].text,"second"));
  assert(!strcmp(cell_run(read,id,1,0)->text,"E"));
  assert(!strcmp(exr_edit_table_cell_paragraph(read,id,1,0,1)->runs[0].text,"gamma"));
  exr_edit_doc_free(read);puts("PASS saved-file-reopen text, formatting, sibling run and paragraph retained");
  de_key('A',1,0);page_procedure(NULL,WM_CHAR,L'X',0);
  assert(!strcmp(cell_run(de.doc,id,0,0)->text,"X"));
  de_key('Z',1,0);assert(strstr(cell_run(de.doc,id,0,0)->text,"alpha"));
  de_key('Y',1,0);assert(!strcmp(cell_run(de.doc,id,0,0)->text,"X"));
  de_key(VK_END,0,0);de_key(VK_LEFT,0,1);page_procedure(NULL,WM_CHAR,0x4e2d,0);
  assert(!strcmp(cell_run(de.doc,id,0,0)->text,"\xe4\xb8\xad"));
  de_key(VK_BACK,0,0);assert(!cell_run(de.doc,id,0,0)->text_size);
  puts("PASS select-replace undo redo UTF-8-selection backspace");
  press_command(DA_RUN,VK_RETURN);assert(da.run==1);page_procedure(NULL,WM_CHAR,L'!',0);
  assert(!strcmp(da_run()->text,"!keep"));
  press_command(DA_RUN,VK_SPACE);assert(da.para==1 && !strcmp(da_run()->text,"second"));
  press_command(DA_NEXT,VK_RETURN);assert(da.row==0 && da.col==1);
  press_command(DA_NEXT,VK_SPACE);assert(da.row==1 && da.col==0);
  press_command(DA_PREV,VK_RETURN);assert(da.row==0 && da.col==1);
  press_command(DA_ADD,VK_RETURN);assert(da_table()->table->row_count==3);
  press_command(DA_REMOVE,VK_SPACE);assert(da_table()->table->row_count==2);
  de_key('Z',1,0);assert(da_table()->table->row_count==3);
  de_key('Y',1,0);assert(da_table()->table->row_count==2);
  puts("PASS next-run next-paragraph next/previous-cell insert/delete-row undo redo");
  /* Empty new row remains typeable. */
  da.row=0;da.col=da.para=da.run=da.byte=da.anchor=0;da_update();
  page_procedure(NULL,WM_CHAR,L'N',0);assert(da_run() && !strcmp(da_run()->text,"N"));
  int bold=de_resolve_props(da_paragraph(),da_run()).bold;
  de_key('B',1,0);assert(de_resolve_props(da_paragraph(),da_run()).bold!=bold);
  press_command(DA_BOLD,VK_SPACE);assert(de_resolve_props(da_paragraph(),da_run()).bold==bold);
  int italic=de_resolve_props(da_paragraph(),da_run()).italic;
  press_command(DA_ITALIC,VK_RETURN);assert(de_resolve_props(da_paragraph(),da_run()).italic!=italic);
  unsigned size=de_resolve_props(da_paragraph(),da_run()).size_half_points;
  press_command(DA_SMALL,VK_SPACE);assert(da_run()->props.size_half_points==size-2);
  press_command(DA_LARGE,VK_RETURN);assert(da_run()->props.size_half_points==size);
  press_command(DA_COLOR,VK_SPACE);assert(da_run()->props.color_rgb==de_colors[da.color]);
  press_command(DA_LEFT,VK_RETURN);assert(da_paragraph()->props.alignment==EXR_EDIT_LEFT);
  press_command(DA_RIGHT,VK_SPACE);assert(da_paragraph()->props.alignment==EXR_EDIT_RIGHT);
  press_command(DA_JUSTIFY,VK_RETURN);assert(da_paragraph()->props.alignment==EXR_EDIT_JUSTIFY);
  press_command(DA_CENTER,VK_RETURN);assert(da_paragraph()->props.alignment==EXR_EDIT_CENTER);
  press_command(DA_SAVE,VK_RETURN);assert(!de.dirty);
  assert(exr_edit_docx_open(argv[2],NULL,&read,&error)==EXR_OK);
  assert(cell_run(read,id,0,0)->props.color_rgb==de_colors[da.color]);
  assert(cell_run(read,id,0,0)->props.size_half_points==size);
  assert(exr_edit_table_cell_paragraph(read,id,0,0,0)->props.alignment==EXR_EDIT_CENTER);
  assert(!strcmp(exr_edit_table_cell_paragraph(read,id,1,0,1)->runs[0].text,"gamma"));
  exr_edit_doc_free(read);puts("PASS table formatting commands persist without replacing sibling paragraphs");
  de_key('S',1,0);assert(!de.dirty);describe("save-after-table-commands");
  /* The image command's file-dialog completion calls this exact IO function. */
  static const unsigned char png[]={137,80,78,71,13,10,26,10,0,0,0,13,73,72,68,82,0,0,0,1,0,0,0,1,8,6,0,0,0,31,21,196,137,
    0,0,0,11,73,68,65,84,120,156,99,96,0,2,0,0,5,0,1,165,246,69,64,0,0,0,0,73,69,78,68,174,66,96,130};
  char image[MAX_PATH];snprintf(image,sizeof(image),"%s.png",argv[2]);FILE *file=fopen(image,"wb");assert(file);
  assert(fwrite(png,1,sizeof(png),file)==sizeof(png));fclose(file);
  wchar_t *wide=host_wide(image,strlen(image));assert(wide);
  assert(da_insert_image_path(wide)==EXR_OK);free(wide);
  size_t images=0;for(size_t i=0;i<exr_edit_block_count(de.doc);i++)images+=exr_edit_block_at(de.doc,i)->kind==EXR_EDIT_IMAGE;
  assert(images==1);puts("PASS image-file-picker-completion inserts real image");
  press_command(DA_BODY,VK_RETURN);assert(!da.table);
  assert(da_next_control(DA_BODY,0)==DA_TABLE);
  assert(da_next_control(DA_TABLE,1)==DA_BODY);
  puts("PASS body Tab skips unavailable table controls");
  de_key('S',1,0);de_close();
  /* Real fixture regression: editor still accepts ordinary body input. */
  assert(de_open(argv[1]));page_procedure(NULL,WM_CHAR,L'Q',0);assert(de.dirty);de_close();
  CoUninitialize();puts("L07 headless acceptance PASS (no HWND / no SendInput)");return 0;
}
