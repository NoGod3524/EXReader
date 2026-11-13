/* SPDX-License-Identifier: MIT */
/* Reuse the real host's memory-DC driver and initialization helpers. */
#define WIN32_LEAN_AND_MEAN
#define UNICODE
#define _UNICODE
#define _WIN32_WINNT 0x0602
#include <windows.h>
static int WINAPI table_confirm(HWND window,LPCWSTR text,LPCWSTR title,UINT flags);
#define MessageBoxW table_confirm
#define main docedit_baseline_main
#include "check_shell_docedit.c"
#undef main
#undef MessageBoxW
static int confirm_choice=IDNO,confirm_count;
static int WINAPI table_confirm(HWND window,LPCWSTR text,LPCWSTR title,UINT flags) {
  assert(!window && !wcscmp(title,L"删除表格") && wcsstr(text,L"删除整个表格"));
  assert((flags&MB_YESNO) && (flags&MB_DEFBUTTON2));
  confirm_count++;return confirm_choice;
}

static const exr_edit_table *table_view(void) {
  for(size_t i=0;i<exr_edit_block_count(de.doc);i++) {
    const exr_edit_block *b=exr_edit_block_at(de.doc,i);if(b->table)return b->table;
  }
  return NULL;
}
static char *table_snapshot(exr_edit_doc *doc) {
  cv_text out={0};char number[96];
  for(size_t i=0;i<exr_edit_block_count(doc);i++) {
    const exr_edit_block *b=exr_edit_block_at(doc,i);
    snprintf(number,sizeof(number),"B%d;",b->kind);cv_text_string(&out,number);
    if(!b->table)continue;
    const exr_edit_table *t=b->table;
    snprintf(number,sizeof(number),"%zu,%zu,%d;",t->row_count,t->column_count,t->width_twips);cv_text_string(&out,number);
    for(size_t c=0;c<t->column_count;c++) {
      snprintf(number,sizeof(number),"W%d;",t->column_widths ? t->column_widths[c]:t->width_twips/(int32_t)t->column_count);
      cv_text_string(&out,number);
    }
    for(size_t r=0;r<t->row_count;r++) {
      snprintf(number,sizeof(number),"R%zu;",t->rows[r].cell_count);cv_text_string(&out,number);
      for(size_t c=0;c<t->rows[r].cell_count;c++) {
        const exr_edit_cell *cell=&t->rows[r].cells[c];
        snprintf(number,sizeof(number),"C%zu;",cell->block_count);cv_text_string(&out,number);
        for(size_t p=0;p<cell->block_count;p++) {
          const exr_edit_block *para=&cell->blocks[p];cv_text_string(&out,"P[");
          for(size_t j=0;j<para->run_count;j++)if(para->runs[j].kind==EXR_EDIT_TEXT)
            cv_text_append(&out,para->runs[j].text,para->runs[j].text_size);
          cv_text_string(&out,"]");
        }
      }
    }
  }
  cv_text_string(&out,"");return out.data;
}
static void check_cell(size_t row,size_t col,size_t paragraph,const char *expected) {
  const exr_edit_block *p=&table_view()->rows[row].cells[col].blocks[paragraph];cv_text out={0};
  for(size_t i=0;i<p->run_count;i++)if(p->runs[i].kind==EXR_EDIT_TEXT)cv_text_append(&out,p->runs[i].text,p->runs[i].text_size);
  cv_text_string(&out,"");assert(!strcmp(out.data,expected));free(out.data);
}
static void table_fixture(const char *path) {
  exr_edit_run before={0},other={0};before.text="before";before.text_size=6;other.text="keep";other.text_size=4;
  exr_edit_block paras[4]={{0}};for(int i=1;i<4;i++) {paras[i].runs=&other;paras[i].run_count=1;}
  exr_edit_cell cells[4]={{0}};for(int i=0;i<4;i++) {cells[i].blocks=&paras[i];cells[i].block_count=1;}
  exr_edit_row rows[2]={{0}};for(int i=0;i<2;i++) {rows[i].cells=&cells[i*2];rows[i].cell_count=2;}
  int32_t widths[2]={2400,2400};exr_edit_table table={0};table.rows=rows;table.row_count=table.column_count=2;
  table.width_twips=4800;table.column_widths=widths;table.borders=EXR_EDIT_BORDER_SINGLE;
  exr_edit_block blocks[3]={{0}};blocks[0].runs=blocks[2].runs=&before;blocks[0].run_count=blocks[2].run_count=1;
  blocks[1].kind=EXR_EDIT_TABLE;blocks[1].table=&table;
  assert(exr_edit_doc_create(NULL,0,blocks,3,NULL,0,NULL,&de.doc)==EXR_OK);
  strcpy(de.path,path);assert(de_save());de_close();assert(de_open(path));
}
static void focus_cell(size_t r,size_t c) {
  for(size_t i=0;i<de_block_count(de.doc);i++) {
    de_cell cell=de_cell_at(i);if(cell.table && cell.row==r && cell.col==c) {
      de_set_caret(de_start(i));de_set_anchor(de_caret_pos());return;
    }
  }
  assert(0);
}
static void existing_table_fixture(const char *path) {
  assert(de_open(path));assert(table_view());
  assert(de_key(VK_TAB,0,0) && de.caret_in_table && de.caret.row==0 && de.caret.column==0);
  assert(de_measure(600,400));shell_d2d_edit_row *row=&de.rows[de.caret.view];
  de.scroll_y=row->cell_box[1]-de_toolbar_height()-8;de.blink=0;
  uint32_t *pixels=paint_memory(600,400);size_t border=0;
  int top=(int)(row->cell_box[1]-de.scroll_y),bottom=(int)(row->cell_box[3]-de.scroll_y);
  int left=(int)row->cell_box[0];
  for(int y=top+2;y<bottom-2 && y<400;y++)for(int x=left-1;x<=left+1;x++)
    border+=(pixels[y*600+x]&0xffffff)!=(pixels[399*600]&0xffffff);
  assert(border>0);free(pixels);
  char *before=table_snapshot(de.doc);int was_dirty=de.dirty;
  assert(!de_edit(DE_TYPE,"X",1));char *after=table_snapshot(de.doc);
  assert(!strcmp(before,after) && de.dirty==was_dirty);free(before);free(after);
  printf("1 PASS existing rich.docx (Content/main.xml) -> Tab cell=(0,0); border_pixels=%zu; merged-cell edit rolls back\n",border);
  de_close();
}
int main(int argc,char **argv) {
  assert(argc==3);setvbuf(stdout,NULL,_IONBF,0);
  SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);
  assert(SUCCEEDED(CoInitializeEx(NULL,COINIT_APARTMENTTHREADED)));
  assert(SUCCEEDED(shell_d2d_create(NULL,&host_shell)));shell_dpi=96;shell_apply_theme();
  wchar_t *directory=host_wide(argv[1],strlen(argv[1]));assert(directory);
  ensure_directory(directory);copy_wstring(g.data_dir,HOST_PATH,directory);free(directory);
  exr_error error={0};assert(host_open_body_font(L"C:\\Windows\\Fonts\\segoeui.ttf",L"",&error)==EXR_OK);
  existing_table_fixture(argv[2]);
  char path[MAX_PATH],bmp[MAX_PATH];snprintf(path,sizeof(path),"%s/table-ui.docx",argv[1]);
  table_fixture(path);assert(!de_cell_at(de.caret.view).table);
  assert(de_key(VK_TAB,0,0));de_cell active=de_cell_at(de.caret.view);assert(active.table && !active.row && !active.col);
  assert(de.caret_in_table && de.caret.block==1 && de.caret.row==0 && de.caret.column==0);
  assert(de_table_at(de.caret.block)==table_view() && de.anchor.block==de.caret.block);
  assert(de_measure(600,400));shell_d2d_edit_row *row=&de.rows[de.caret.view];float box[4];
  shell_d2d_edit_position(row->layout,de_offset(de_caret_pos()),box);
  float cx=de.inset+row->x+box[0],cy=row->y+box[1];
  assert(cx>row->cell_box[0] && cx<row->cell_box[2] && cy>=row->cell_box[1] && cy+box[3]<row->cell_box[3]);
  assert(de_hit(cx+1,cy+box[3]/2).block==de.caret.view);
  uint32_t *visible=paint_memory(600,400);de.blink=0;uint32_t *hidden=paint_memory(600,400);
  size_t caret=0,border=0;int edge=(int)row->cell_box[0];
  for(int y=(int)row->cell_box[1]+2;y<(int)row->cell_box[3]-2;y++)
    for(int x=edge-1;x<=edge+1;x++)border+=(hidden[y*600+x]&0xffffff)!=(hidden[399*600]&0xffffff);
  for(size_t i=0;i<600*400;i++)caret+=visible[i]!=hidden[i];assert(border>0 && caret>0);
  snprintf(bmp,sizeof(bmp),"%s/table-ui.bmp",argv[1]);save_bitmap(bmp,visible,600,400);free(visible);free(hidden);
  printf("extra PASS generated 2x2 fixture -> Tab cell=(0,0); border_pixels=%zu caret_pixels=%zu caret=(%.1f,%.1f) inside cell; hit-test PASS\n",border,caret,cx,cy);
  de_character(L'X');de_character(L'1');check_cell(0,0,0,"X1");de_key('S',1,0);
  de_close();assert(de_open(path));focus_cell(0,0);check_cell(0,0,0,"X1");
  puts("2 PASS typed X1 -> Ctrl+S -> reopened cell(0,0)=X1");
  de_key(VK_TAB,0,0);assert(de_cell_at(de.caret.view).col==1);
  assert(de.caret.row==0 && de.caret.column==1);
  de_key(VK_TAB,0,0);assert(de_cell_at(de.caret.view).row==1 && de_cell_at(de.caret.view).col==0);
  assert(de.caret.row==1 && de.caret.column==0);
  de_key(VK_TAB,0,0);assert(de.caret.row==1 && de.caret.column==1);
  de_key(VK_TAB,0,1);assert(de.caret.row==1 && de.caret.column==0);
  de_key(VK_TAB,0,1);assert(de_cell_at(de.caret.view).row==0 && de_cell_at(de.caret.view).col==1);
  de_key(VK_TAB,0,1);assert(de_cell_at(de.caret.view).col==0);
  de_key(VK_TAB,0,1);assert(!de_cell_at(de.caret.view).table);
  de_set_caret(de_end(0));de_set_anchor(de_caret_pos());de_key(VK_RIGHT,0,0);assert(de_cell_at(de.caret.view).table);
  puts("3 PASS Tab (0,0)->(0,1)->(1,0)->(1,1); Shift+Tab reverses; Right enters cell");
  de_set_caret(de_end(de.caret.view));de_set_anchor(de_caret_pos());de_key(VK_RETURN,0,0);
  assert(table_view()->rows[0].cells[0].block_count==2);
  assert(de_block_at(de.doc,de.caret.view)->run_count==0);
  de_character(L'X');check_cell(0,0,0,"X1");check_cell(0,0,1,"X");check_cell(0,1,0,"keep");
  puts("extra PASS Enter paragraphs=1->2 zero-run=0; typed X -> [X1|X]; sibling cell=keep");
  de_key('Z',1,0);assert(table_view()->rows[0].cells[0].block_count==2);
  check_cell(0,0,0,"X1");check_cell(0,0,1,"");assert(de_block_at(de.doc,de.caret.view)->run_count==0);
  puts("extra PASS one Ctrl+Z -> [X1|empty], Enter retained, inserted run removed");
  de_key('Y',1,0);check_cell(0,0,1,"X");
  /* Use actual toolbar hit boxes, then prove one-step history for each row edit. */
  rich_click(DE_ADD_ROW);assert(table_view()->row_count==3);
  check_cell(0,0,0,"");check_cell(1,0,0,"X1");assert(de.caret.row==1);
  de_key('Z',1,0);assert(table_view()->row_count==2);
  de_key('Y',1,0);assert(table_view()->row_count==3);focus_cell(0,0);
  rich_click(DE_REMOVE_ROW);assert(table_view()->row_count==2);de_key('Z',1,0);assert(table_view()->row_count==3);
  de_key('Y',1,0);assert(table_view()->row_count==2);check_cell(0,0,0,"X1");check_cell(0,0,1,"X");focus_cell(0,0);
  puts("4 PASS toolbar +row ABOVE 2->3; -row 3->2; each undo/redo is one transaction; text retained");
  assert(de_measure(600,400));row=&de.rows[de.caret.view];float w0=row->cell_box[2]-row->cell_box[0];
  rich_click(DE_WIDER);assert(de_measure(600,400));row=&de.rows[de.caret.view];float w1=row->cell_box[2]-row->cell_box[0];
  assert(w1>w0 && table_view()->column_widths[0]==2520);
  rich_click(DE_NARROWER);assert(de_measure(600,400));row=&de.rows[de.caret.view];float w2=row->cell_box[2]-row->cell_box[0];
  assert(w2<w1 && table_view()->column_widths[0]==2394);
  printf("5 PASS toolbar column +5%%/-5%% twips=2400->2520->2394 pixels=%.1f->%.1f->%.1f\n",w0,w1,w2);
  size_t blocks_before=exr_edit_block_count(de.doc);
  char *before_delete=table_snapshot(de.doc);int was_dirty=de.dirty;
  rich_click(DE_REMOVE_TABLE);assert(confirm_count==1 && de.dirty==was_dirty);
  char *cancelled=table_snapshot(de.doc);assert(!strcmp(before_delete,cancelled));free(before_delete);free(cancelled);
  confirm_choice=IDYES;rich_click(DE_REMOVE_TABLE);assert(confirm_count==2);
  assert(!table_view() && exr_edit_block_count(de.doc)==blocks_before-1);assert(!de.caret_in_table);
  assert(de_measure(600,400));for(size_t i=0;i<de.row_count;i++)assert(!de.rows[i].cell_border);
  puts("6 PASS toolbar delete confirmation No unchanged / Yes deletes; block_count 3->2; border layouts=0; toolbar hidden");
  de_key('Z',1,0);assert(table_view());focus_cell(0,0);rich_click(DE_WIDER);
  char *expected=table_snapshot(de.doc);de_key('S',1,0);assert(!de.dirty);de_close();assert(de_open(path));
  char *actual=table_snapshot(de.doc);assert(!strcmp(expected,actual));free(expected);free(actual);
  assert(table_view()->row_count==2 && table_view()->column_widths[0]==2514);
  check_cell(0,0,0,"X1");check_cell(0,0,1,"X");check_cell(1,1,0,"keep");
  puts("extra PASS Ctrl+S -> reopen: rows=2 columns=2 widths=[2514,2400] all cell paragraphs/text equal [X1|X], keep");
  focus_cell(0,0);size_t first=de.caret.view;
  de_set_caret(de_end(first));de_set_anchor(de_caret_pos());de_key(VK_DELETE,0,0);
  assert(table_view()->rows[0].cells[0].block_count==1);check_cell(0,0,0,"X1X");
  de_key('Z',1,0);assert(table_view()->rows[0].cells[0].block_count==2);
  de_set_caret(de_start(first+1));de_set_anchor(de_caret_pos());de_key(VK_BACK,0,0);
  assert(table_view()->rows[0].cells[0].block_count==1);check_cell(0,0,0,"X1X");de_key('Z',1,0);
  de_set_caret(de_end(first+1));de_set_anchor(de_caret_pos());
  assert(!de_edit(DE_DELETE,NULL,0));check_cell(0,0,1,"X");check_cell(0,1,0,"keep");
  assert(de_measure(600,400));visible=paint_memory(600,400);
  snprintf(bmp,sizeof(bmp),"%s/table-edited.bmp",argv[1]);save_bitmap(bmp,visible,600,400);free(visible);
  puts("extra PASS Delete/Backspace join within cell + undo; cross-cell deletion rolls back without text loss");
  focus_cell(0,1);assert(de_measure(600,400));
  de_key(VK_DOWN,0,0);assert(de.caret.row==1 && de.caret.column==1);
  de_key(VK_UP,0,0);assert(de.caret.row==0 && de.caret.column==1);
  focus_cell(0,0);de_key(VK_DOWN,0,0);assert(de.caret.row==0 && de.caret.paragraph==1);
  de_key(VK_DOWN,0,0);assert(de.caret.row==1 && de.caret.column==0);
  de_key(VK_UP,0,0);assert(de.caret.row==0 && de.caret.paragraph==1);
  de_key(VK_UP,0,0);assert(de.caret.row==0 && de.caret.paragraph==0);
  de_set_caret(de_end(de.caret.view));de_set_anchor(de_caret_pos());
  de_key(VK_RIGHT,0,0);assert(de.caret.paragraph==1);
  de_set_caret(de_end(de.caret.view));de_set_anchor(de_caret_pos());
  de_key(VK_RIGHT,0,0);assert(de.caret.row==0 && de.caret.column==1);
  de_key(VK_LEFT,0,0);assert(de.caret.column==0 && de.caret.paragraph==1);
  puts("extra PASS Left/Right cross cells; Up/Down stay in column across unequal cell heights and cell paragraphs");
  focus_cell(1,1);de_set_anchor(de_start(de.caret.view));de_set_caret(de_end(de.caret.view));
  assert(de_edit(DE_TYPE,"wrapped text wrapped text wrapped text wrapped text wrapped text wrapped text",77));
  assert(de_measure(600,400));de_set_caret(de_start(de.caret.view));de_set_anchor(de_caret_pos());
  row=&de.rows[de.caret.view];shell_d2d_edit_position(row->layout,0,box);
  float first_line=box[1];size_t wrapped_view=de.caret.view;
  de_key(VK_DOWN,0,0);assert(de.caret.view==wrapped_view && de_offset(de_caret_pos())>0);
  shell_d2d_edit_position(row->layout,de_offset(de_caret_pos()),box);assert(box[1]>first_line);
  de_key(VK_UP,0,0);assert(de.caret.view==wrapped_view);
  shell_d2d_edit_position(row->layout,de_offset(de_caret_pos()),box);assert(box[1]==first_line);
  de_key('Z',1,0);check_cell(1,1,0,"keep");
  puts("extra PASS wrapped cell Up/Down moves between visual lines before crossing cells");
  focus_cell(1,1);de_set_anchor(de_start(de.caret.view));de_set_caret(de_end(de.caret.view));
  assert(de_edit(DE_TYPE,"",0));
  de_character(0x4e2d);de_character(0xd83d);de_character(0xde42);check_cell(1,1,0,"\xe4\xb8\xad\xf0\x9f\x99\x82");
  de_key(VK_BACK,0,0);check_cell(1,1,0,"\xe4\xb8\xad");
  de_set_caret(de_start(de.caret.view));de_set_anchor(de_caret_pos());de_key(VK_DELETE,0,0);check_cell(1,1,0,"");
  for(int i=0;i<5;i++)de_key('Z',1,0);check_cell(1,1,0,"keep");
  puts("extra PASS cell UTF-8 CJK/surrogate input, Backspace/Delete scalar boundaries, five undos restore keep");
  focus_cell(0,0);blocks_before=exr_edit_block_count(de.doc);
  assert(de_key_modifiers(VK_RETURN,1,0,1));
  assert(!de.caret_in_table && de.caret.block==2 && exr_edit_block_count(de.doc)==blocks_before+1);
  assert(exr_edit_block_at(de.doc,2)->kind==EXR_EDIT_PARAGRAPH && !exr_edit_block_at(de.doc,2)->run_count);
  de_character(L'Q');assert(de_block_at(de.doc,de.caret.view)->runs[0].text[0]=='Q');
  de_key('Z',1,0);assert(exr_edit_block_count(de.doc)==blocks_before+1);
  de_key('Z',1,0);assert(exr_edit_block_count(de.doc)==blocks_before);check_cell(0,0,0,"X1");
  puts("extra PASS Ctrl+Alt+Enter inserts empty paragraph immediately below table; typing and insertion undo separately");
  de_close();memset(&de,0,sizeof(de));
  exr_edit_block empty={0};exr_edit_cell no_width_cells[2]={{0}};
  for(int i=0;i<2;i++) {no_width_cells[i].blocks=&empty;no_width_cells[i].block_count=1;}
  exr_edit_row no_width_row={0};no_width_row.cells=no_width_cells;no_width_row.cell_count=2;
  exr_edit_table no_width={0};no_width.rows=&no_width_row;no_width.row_count=1;no_width.column_count=2;
  exr_edit_block no_width_block={0};no_width_block.kind=EXR_EDIT_TABLE;no_width_block.table=&no_width;
  assert(exr_edit_doc_create(NULL,0,&no_width_block,1,NULL,0,NULL,&de.doc)==EXR_OK);
  de.layout_dirty=1;focus_cell(0,0);assert(de_measure(600,400));
  float fallback0=de.rows[0].cell_box[2]-de.rows[0].cell_box[0];
  float fallback1=de.rows[1].cell_box[2]-de.rows[1].cell_box[0];
  assert(fabsf(fallback0-276)<.1f && fabsf(fallback1-276)<.1f);
  assert(fabsf(de.rows[1].cell_box[2]-(600-de.inset))<.1f);
  printf("extra PASS missing engine widths -> available 552px equally split %.1f/%.1fpx\n",fallback0,fallback1);
  de_close();shell_d2d_destroy(host_shell);exr_font_free(g.font);exr_font_manager_free(g.font_manager);CoUninitialize();
  puts("M-E2a table UI headless acceptance PASS (no HWND / no SendInput)");return 0;
}
