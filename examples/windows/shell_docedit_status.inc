/* SPDX-License-Identifier: MIT */
/* Include after shell_docedit.inc. Host hooks: de_status_paint(dc,&area)
   after the editor paint; reserve de_status_height() at the viewport bottom;
   call de_status_refresh() from de_refresh/save. No separate timer is needed
   when every committed edit and caret move refreshes the editor. */
typedef struct { size_t words,characters,paragraphs; } de_status_counts;

static int de_status_space(uint32_t cp) {
  return cp==0x20 || (cp>=9 && cp<=13) || cp==0x85 || cp==0xa0 ||
    cp==0x1680 || (cp>=0x2000 && cp<=0x200a) || cp==0x2028 ||
    cp==0x2029 || cp==0x202f || cp==0x205f || cp==0x3000;
}
static void de_status_count_block(const exr_edit_block *block,de_status_counts *out) {
  if(!block)return;
  if(block->kind==EXR_EDIT_TABLE && block->table) {
    const exr_edit_table *table=block->table;
    for(size_t r=0;r<table->row_count;r++)
      for(size_t c=0;c<table->rows[r].cell_count;c++) {
        const exr_edit_cell *cell=&table->rows[r].cells[c];
        for(size_t b=0;b<cell->block_count;b++)de_status_count_block(&cell->blocks[b],out);
      }
    return;
  }
  if(block->kind!=EXR_EDIT_PARAGRAPH)return;
  out->paragraphs++;
  for(size_t r=0;r<block->run_count;r++) {
    const exr_edit_run *run=&block->runs[r];
    if(run->kind!=EXR_EDIT_TEXT)continue;
    /* The engine guarantees valid UTF-8. Decode scalars, never UTF-16 units
       or grapheme clusters: an emoji sequence may contain several scalars. */
    for(size_t i=0;i<run->text_size;) {
      const unsigned char *s=(const unsigned char *)run->text;
      uint32_t cp=s[i++];
      if(cp>=0xc0) {
        unsigned more=cp<0xe0 ? 1:cp<0xf0 ? 2:3;
        cp&=more==1 ? 0x1f:more==2 ? 0x0f:7;
        while(more-- && i<run->text_size)cp=(cp<<6)|(s[i++]&0x3f);
      }
      out->characters++;out->words+=!de_status_space(cp);
    }
  }
}

#ifndef DE_STATUS_COUNTS_ONLY
static de_status_counts de_status_count(void) {
  de_status_counts out={0};
  for(size_t i=0;i<exr_edit_block_count(de.doc);i++)
    de_status_count_block(exr_edit_block_at(de.doc,i),&out);
  return out;
}
static int de_status_height(void) {return shell_px(28,shell_dpi);}
static const wchar_t *de_status_saved(void) {return de.dirty ? L"已修改":L"已保存";}
static void de_status_refresh(void) {
  if(g.page)InvalidateRect(g.page,NULL,FALSE);
}
static void de_status_paint(HDC dc,const RECT *area) {
  RECT bar=*area;bar.top=bar.bottom-de_status_height();
  if(bar.top<area->top)bar.top=area->top;
  uint32_t color=shell_colors->layer_side;
  HBRUSH brush=CreateSolidBrush(RGB((color>>16)&255,(color>>8)&255,color&255));
  FillRect(dc,&bar,brush);DeleteObject(brush);
  int saved=SaveDC(dc);
  IntersectClipRect(dc,bar.left,bar.top,bar.right,bar.bottom);
  HFONT font=CreateFontW(-shell_px(12,shell_dpi),0,0,0,FW_NORMAL,FALSE,FALSE,FALSE,
    DEFAULT_CHARSET,OUT_DEFAULT_PRECIS,CLIP_DEFAULT_PRECIS,DEFAULT_QUALITY,
    DEFAULT_PITCH,L"Segoe UI");
  if(font)SelectObject(dc,font);
  SetBkMode(dc,TRANSPARENT);SetTextColor(dc,shell_is_dark() ? RGB(230,230,230):RGB(35,35,35));
  de_status_counts count=de_status_count();wchar_t summary[256];
  swprintf(summary,256,L"字数 %zu  字符数 %zu  段落数 %zu  当前块 %zu  %ls",
    count.words,count.characters,count.paragraphs,
    exr_edit_block_count(de.doc) ? de.caret_block+1:0,de_status_saved());
  RECT text=bar;text.left+=shell_px(8,shell_dpi);text.right-=shell_px(8,shell_dpi);
  SIZE extent={0};GetTextExtentPoint32W(dc,summary,(int)wcslen(summary),&extent);
  DrawTextW(dc,summary,-1,&text,DT_LEFT|DT_SINGLELINE|DT_VCENTER|DT_NOPREFIX);
  text.left+=extent.cx+shell_px(16,shell_dpi);
  wchar_t *path=host_wide(de.path,strlen(de.path));
  if(path && text.left<text.right)
    DrawTextW(dc,path,-1,&text,DT_LEFT|DT_SINGLELINE|DT_VCENTER|DT_PATH_ELLIPSIS|DT_NOPREFIX);
  free(path);RestoreDC(dc,saved);if(font)DeleteObject(font);
}
#endif
