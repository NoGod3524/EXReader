/* SPDX-License-Identifier: MIT */
/* Reuse the real host's memory-DC driver and initialization helpers. */
#define main docedit_baseline_main
#include "check_shell_docedit.c"
#undef main

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
      de_set_caret(de_start(i));de_set_anchor(de_caret());return;
    }
  }
  assert(0);
}
int main(int argc,char **argv) {
  assert(argc==2);setvbuf(stdout,NULL,_IONBF,0);
  SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);
  assert(SUCCEEDED(CoInitializeEx(NULL,COINIT_APARTMENTTHREADED)));
  assert(SUCCEEDED(shell_d2d_create(NULL,&host_shell)));shell_dpi=96;shell_apply_theme();
  wchar_t *directory=host_wide(argv[1],strlen(argv[1]));assert(directory);
  ensure_directory(directory);copy_wstring(g.data_dir,HOST_PATH,directory);free(directory);
  exr_error error={0};assert(host_open_body_font(L"C:\\Windows\\Fonts\\segoeui.ttf",L"",&error)==EXR_OK);
  char path[MAX_PATH],bmp[MAX_PATH];snprintf(path,sizeof(path),"%s/table-ui.docx",argv[1]);
  table_fixture(path);assert(!de_cell_at(de.caret_block).table);
  assert(de_key(VK_TAB,0,0));de_cell active=de_cell_at(de.caret_block);assert(active.table && !active.row && !active.col);
  assert(de_measure(600,400));shell_d2d_edit_row *row=&de.rows[de.caret_block];float box[4];
  shell_d2d_edit_position(row->layout,de_offset(de_caret()),box);
  float cx=de.inset+row->x+box[0],cy=row->y+box[1];
  assert(cx>row->cell_box[0] && cx<row->cell_box[2] && cy>=row->cell_box[1] && cy+box[3]<row->cell_box[3]);
  assert(de_hit(cx+1,cy+box[3]/2).block==de.caret_block);
  uint32_t *visible=paint_memory(600,400);de.blink=0;uint32_t *hidden=paint_memory(600,400);
  size_t caret=0,border=0;int edge=(int)row->cell_box[0];
  for(int y=(int)row->cell_box[1]+2;y<(int)row->cell_box[3]-2;y++)
    for(int x=edge-1;x<=edge+1;x++)border+=(hidden[y*600+x]&0xffffff)!=(hidden[399*600]&0xffffff);
  for(size_t i=0;i<600*400;i++)caret+=visible[i]!=hidden[i];assert(border>0 && caret>0);
  snprintf(bmp,sizeof(bmp),"%s/table-ui.bmp",argv[1]);save_bitmap(bmp,visible,600,400);free(visible);free(hidden);
  printf("1 PASS open fixture -> Tab cell=(0,0); border_pixels=%zu caret_pixels=%zu caret=(%.1f,%.1f) inside cell; hit-test PASS\n",border,caret,cx,cy);
  de_key(VK_TAB,0,0);assert(de_cell_at(de.caret_block).col==1);
  de_key(VK_TAB,0,0);assert(de_cell_at(de.caret_block).row==1 && de_cell_at(de.caret_block).col==0);
  de_key(VK_TAB,0,1);assert(de_cell_at(de.caret_block).row==0 && de_cell_at(de.caret_block).col==1);
  de_key(VK_TAB,0,1);assert(de_cell_at(de.caret_block).col==0);
  de_key(VK_TAB,0,1);assert(!de_cell_at(de.caret_block).table);
  de_set_caret(de_end(0));de_set_anchor(de_caret());de_key(VK_RIGHT,0,0);assert(de_cell_at(de.caret_block).table);
  puts("1 extra PASS Tab row wrap / Shift+Tab / Right enters cell");
  de_character(L'A');de_character(L'B');check_cell(0,0,0,"AB");de_key('S',1,0);
  de_close();assert(de_open(path));focus_cell(0,0);check_cell(0,0,0,"AB");
  puts("2 PASS typed AB -> Ctrl+S -> reopened cell(0,0)=AB");
  de_set_caret(de_end(de.caret_block));de_set_anchor(de_caret());de_key(VK_RETURN,0,0);
  assert(table_view()->rows[0].cells[0].block_count==2);
  assert(de_block_at(de.doc,de.caret_block)->run_count==0);
  de_character(L'X');check_cell(0,0,0,"AB");check_cell(0,0,1,"X");check_cell(0,1,0,"keep");
  puts("3 PASS Enter paragraphs=1->2 zero-run=0; typed X -> [AB|X]; sibling cell=keep");
  de_key('Z',1,0);assert(table_view()->rows[0].cells[0].block_count==2);
  check_cell(0,0,0,"AB");check_cell(0,0,1,"");assert(de_block_at(de.doc,de.caret_block)->run_count==0);
  puts("4 PASS one Ctrl+Z -> [AB|empty], Enter retained, inserted run removed");
  de_key('Y',1,0);check_cell(0,0,1,"X");
  /* Use actual toolbar hit boxes, then prove one-step history for each row edit. */
  rich_click(DE_ADD_ROW);assert(table_view()->row_count==3);de_key('Z',1,0);assert(table_view()->row_count==2);
  de_key('Y',1,0);assert(table_view()->row_count==3);focus_cell(1,0);
  rich_click(DE_REMOVE_ROW);assert(table_view()->row_count==2);de_key('Z',1,0);assert(table_view()->row_count==3);
  de_key('Y',1,0);assert(table_view()->row_count==2);check_cell(0,0,0,"AB");check_cell(0,0,1,"X");focus_cell(0,0);
  puts("5 PASS toolbar +row 2->3; -row 3->2; each undo/redo is one transaction; text retained");
  assert(de_measure(600,400));row=&de.rows[de.caret_block];float w0=row->cell_box[2]-row->cell_box[0];
  rich_click(DE_WIDER);assert(de_measure(600,400));row=&de.rows[de.caret_block];float w1=row->cell_box[2]-row->cell_box[0];
  assert(w1>w0 && table_view()->column_widths[0]==2520);
  rich_click(DE_NARROWER);assert(de_measure(600,400));row=&de.rows[de.caret_block];float w2=row->cell_box[2]-row->cell_box[0];
  assert(w2<w1 && table_view()->column_widths[0]==2400);
  printf("6 PASS toolbar column +5%%/-5%% twips=2400->2520->2400 pixels=%.1f->%.1f->%.1f\n",w0,w1,w2);
  rich_click(DE_REMOVE_TABLE);assert(!table_view());assert(!de_cell_at(de.caret_block).table);
  assert(de_measure(600,400));for(size_t i=0;i<de.row_count;i++)assert(!de.rows[i].cell_border);
  puts("7 PASS toolbar delete table -> table block absent; border layouts=0; toolbar hidden");
  de_key('Z',1,0);assert(table_view());focus_cell(0,0);rich_click(DE_WIDER);
  char *expected=table_snapshot(de.doc);de_key('S',1,0);assert(!de.dirty);de_close();assert(de_open(path));
  char *actual=table_snapshot(de.doc);assert(!strcmp(expected,actual));free(expected);free(actual);
  assert(table_view()->row_count==2 && table_view()->column_widths[0]==2520);
  check_cell(0,0,0,"AB");check_cell(0,0,1,"X");check_cell(1,1,0,"keep");
  puts("8 PASS Ctrl+S -> reopen: rows=2 columns=2 widths=[2520,2400] all cell paragraphs/text equal [AB|X], keep");
  focus_cell(0,0);size_t first=de.caret_block;
  de_set_caret(de_end(first));de_set_anchor(de_caret());de_key(VK_DELETE,0,0);
  assert(table_view()->rows[0].cells[0].block_count==1);check_cell(0,0,0,"ABX");
  de_key('Z',1,0);assert(table_view()->rows[0].cells[0].block_count==2);
  de_set_caret(de_start(first+1));de_set_anchor(de_caret());de_key(VK_BACK,0,0);
  assert(table_view()->rows[0].cells[0].block_count==1);check_cell(0,0,0,"ABX");de_key('Z',1,0);
  de_set_caret(de_end(first+1));de_set_anchor(de_caret());
  assert(!de_edit(DE_DELETE,NULL,0));check_cell(0,0,1,"X");check_cell(0,1,0,"keep");
  assert(de_measure(600,400));visible=paint_memory(600,400);
  snprintf(bmp,sizeof(bmp),"%s/table-edited.bmp",argv[1]);save_bitmap(bmp,visible,600,400);free(visible);
  puts("extra PASS Delete/Backspace join within cell + undo; cross-cell deletion rolls back without text loss");
  de_close();shell_d2d_destroy(host_shell);exr_font_free(g.font);exr_font_manager_free(g.font_manager);CoUninitialize();
  puts("M-E2a table UI headless acceptance PASS (no HWND / no SendInput)");return 0;
}
