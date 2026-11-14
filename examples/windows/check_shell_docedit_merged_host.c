/* SPDX-License-Identifier: MIT */
#define WinMain reader_WinMain
#define EXR_READER_TEST_DRIVERS 1
#ifndef L10_READER_SOURCE
#define L10_READER_SOURCE "../reader.c"
#endif
#include L10_READER_SOURCE
#undef WinMain
#include <assert.h>

static size_t first_table(void) {
  for(size_t i=0;i<exr_edit_block_count(de.doc);i++)if(exr_edit_block_at(de.doc,i)->table)return i;
  assert(0);return 0;
}
static void raster(const char *path) {
  RECT area={0,0,640,480};BITMAPINFO info={0};void *pixels=NULL;
  info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);info.bmiHeader.biWidth=640;
  info.bmiHeader.biHeight=-480;info.bmiHeader.biPlanes=1;info.bmiHeader.biBitCount=32;
  HDC dc=CreateCompatibleDC(NULL);assert(dc);
  HBITMAP bitmap=CreateDIBSection(dc,&info,DIB_RGB_COLORS,&pixels,NULL,0);assert(bitmap);
  HGDIOBJ old=SelectObject(dc,bitmap);assert(de_paint_dc(dc,&area)==S_OK);GdiFlush();
  assert(de_mv_count);const de_merge_view *v=de_mv;
  uint32_t *p=pixels,border=shell_is_dark() ? 0xb4b4b4:0x505050;
  int x=(v->box.left+v->box.right)/2,y=v->box.top;
  assert((p[y*640+x]&0xffffff)==border);
  /* Merged cell interiors have no grid line at the covered column/row seam. */
  if(v->columns>1)assert((p[(v->box.bottom-3)*640+x]&0xffffff)!=border);
  if(v->rows>1)assert((p[((v->box.top+v->box.bottom)/2)*640+v->box.right-3]&0xffffff)!=border);
  BITMAPFILEHEADER file={0};file.bfType=0x4d42;
  file.bfOffBits=sizeof(file)+sizeof(info.bmiHeader);file.bfSize=file.bfOffBits+640*480*4;
  FILE *out=fopen(path,"wb");assert(out);
  assert(fwrite(&file,sizeof(file),1,out)==1);
  assert(fwrite(&info.bmiHeader,sizeof(info.bmiHeader),1,out)==1);
  assert(fwrite(pixels,4,640*480,out)==640*480);assert(!fclose(out));
  SelectObject(dc,old);DeleteObject(bitmap);DeleteDC(dc);
}
int main(int argc,char **argv) {
  assert(argc==3);setvbuf(stdout,NULL,_IONBF,0);
  assert(SUCCEEDED(CoInitializeEx(NULL,COINIT_APARTMENTTHREADED)));
  assert(SUCCEEDED(shell_d2d_create(NULL,&host_shell)));shell_dpi=96;shell_apply_theme();
  const char *fixtures[]={"codex/01-table-horizontal.docx","codex/02-table-vertical.docx",
    "argon/02-table-merged-hmerge-vmerge.docx"};
  for(size_t f=0;f<3;f++) {
    char path[1024],output[1024];snprintf(path,sizeof(path),"%s/tests/fixtures/docx-real/%s",argv[1],fixtures[f]);
    assert(de_open(path));size_t block=first_table();assert(de_measure(640,480));
    const exr_edit_block *b=exr_edit_block_at(de.doc,block);exr_edit_id id=b->id;
    assert(de_mv_count && de_mv[0].row==0 && de_mv[0].cell==0);
    de_merge_view v=de_mv[0];
    for(int y=v.box.top+2;y<v.box.bottom;y+=7)for(int x=v.box.left+2;x<v.box.right;x+=17) {
      de_pos p=de_hit((float)x,(float)y);assert(p.block==block);
      assert(de_merge_selected_block==block && !de_merge_selected_row && !de_merge_selected_cell);
    }
    snprintf(output,sizeof(output),"%s/merged-%zu.bmp",argv[2],f);raster(output);
    printf("PASS %s: real host paint spans=%zux%zu; all covered hits select owner; bitmap=%s\n",
      fixtures[f],v.columns,v.rows,output);
    size_t row=0,col=0;int merged=0;
    assert(de_merge_resolve(b->table,&row,&col,1,&merged));assert(row || col);
    assert(de_merge_resolve(b->table,&row,&col,-1,&merged) && !row && !col && merged);
    memset(&de_tp,0,sizeof(de_tp));de_tp.table=id;
    for(int command=DE_TADD;command<=DE_TWIDE;command++) {
      size_t rows=b->table->row_count;int dirty=de.dirty;
      de_table_action(command);b=exr_edit_find_block(de.doc,id);
      assert(b->table->row_count==rows && de.dirty==dirty);
      assert(!wcscmp(g.status_text,DE_MERGE_STRUCTURE_MESSAGE));
    }
    puts("PASS navigation skips continuation cells; +row/delete/width rejected with exact visible status text");
    const char *text="\xe5\x90\x88\xe5\xb9\xb6 edited\nsecond line\n";
    assert(de_table_text(de.doc,id,0,0,text,strlen(text))==EXR_OK);
    b=exr_edit_find_block(de.doc,id);
    assert(b->table->rows[0].cells[0].block_count==3);
    assert(exr_edit_undo(de.doc)==EXR_OK);assert(exr_edit_redo(de.doc)==EXR_OK);
    if(v.rows>1)assert(exr_edit_table_insert_row(de.doc,id,0)==EXR_UNSUPPORTED);
    void *bytes=NULL;size_t size=0;exr_error error={0};
    assert(exr_edit_docx_write(de.doc,&bytes,&size,&error)==EXR_OK);
    snprintf(output,sizeof(output),"%s/merged-%zu.docx",argv[2],f);
    FILE *out=fopen(output,"wb");assert(out && fwrite(bytes,1,size,out)==size);assert(!fclose(out));exr_free(bytes);
    exr_edit_doc *read=NULL;assert(exr_edit_docx_open(output,NULL,&read,&error)==EXR_OK);
    const exr_edit_table *t=exr_edit_find_block(read,id) ? exr_edit_find_block(read,id)->table:NULL;
    if(!t)for(size_t i=0;i<exr_edit_block_count(read);i++)if(exr_edit_block_at(read,i)->table) {t=exr_edit_block_at(read,i)->table;break;}
    assert(t && t->rows[0].cells[0].block_count==3);
    de_merged_cell *grid=NULL;size_t count=0;assert(de_merge_grid(t,&grid,&count));
    assert(grid[0].columns==v.columns && grid[0].rows==v.rows);free(grid);
    const exr_edit_block *paragraph=t->rows[0].cells[0].blocks;
    assert(paragraph->run_count && paragraph->runs[0].text_size==13);
    assert(!memcmp(paragraph->runs[0].text,text,13));
    exr_edit_doc_free(read);de.layout_dirty=1;assert(de_measure(640,480));
    de.scroll_y=20;const de_merge_view *hit=de_merge_hit((float)v.box.left+2,(float)v.box.bottom-22);
    assert(hit && !hit->row && !hit->cell);de.scroll_y=0;
    shell_dpi=144;de.layout_dirty=1;assert(de_measure(640,480));shell_dpi=96;
    puts("PASS whole-cell UTF-8/multiline typing, undo/redo, write/reopen retains merges; scroll and DPI rebuild");
    de_close();
  }
  shell_d2d_destroy(host_shell);host_shell=NULL;CoUninitialize();
  puts("L10 merged host acceptance PASS (memory DC; no windows / no SendInput)");return 0;
}
