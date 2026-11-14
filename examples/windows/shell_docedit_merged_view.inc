/* SPDX-License-Identifier: MIT */
/* Include after de_paragraph_text. The same owner rectangles drive paint/hit. */
#include "shell_docedit_merged_cells.h"
typedef struct {
  size_t block,row,cell,column,columns,rows;
  RECT box;
  wchar_t *text;
} de_merge_view;
static de_merge_view *de_mv;
static size_t de_mv_count;
static size_t de_merge_selected_block=SIZE_MAX,de_merge_selected_row,de_merge_selected_cell;
static void de_merge_release(void) {
  for(size_t i=0;i<de_mv_count;i++)free(de_mv[i].text);
  free(de_mv);de_mv=NULL;de_mv_count=0;
}
static HFONT de_merge_font(void) {
  return CreateFontW(-shell_px(16,shell_dpi),0,0,0,FW_NORMAL,FALSE,FALSE,FALSE,
    DEFAULT_CHARSET,OUT_DEFAULT_PRECIS,CLIP_DEFAULT_PRECIS,CLEARTYPE_QUALITY,
    DEFAULT_PITCH,g.font_family[0] ? g.font_family:L"Segoe UI");
}
static wchar_t *de_merge_text(const exr_edit_cell *cell) {
  wchar_t *text=calloc(1,sizeof(*text));size_t used=0;
  if(!text)return NULL;
  for(size_t i=0;i<cell->block_count;i++) {
    wchar_t *part=de_paragraph_text(cell->blocks+i);
    if(!part) {free(text);return NULL;}
    size_t n=wcslen(part);
    if(n>SIZE_MAX/sizeof(*text)-used-2) {free(part);free(text);return NULL;}
    wchar_t *grown=realloc(text,(used+n+2)*sizeof(*text));
    if(!grown) {free(part);free(text);return NULL;}text=grown;
    if(i)text[used++]=L'\n';
    memcpy(text+used,part,(n+1)*sizeof(*text));used+=n;free(part);
  }
  return text;
}
static int de_merge_measure(size_t block,float top,float available,float *height) {
  const exr_edit_table *t=exr_edit_block_at(de.doc,block)->table;
  de_merged_cell *grid=NULL;size_t count=0,start=de_mv_count;
  if(!t || !t->row_count || !t->column_count || !de_merge_grid(t,&grid,&count))return 0;
  float *x=calloc(t->column_count+1,sizeof(*x)),*y=calloc(t->row_count+1,sizeof(*y));
  if(!x || !y || count>SIZE_MAX/sizeof(*de_mv)-start) {free(x);free(y);free(grid);return 0;}
  de_merge_view *grown=realloc(de_mv,(start+count)*sizeof(*de_mv));
  if(!grown && count) {free(x);free(y);free(grid);return 0;}de_mv=grown;
  double total=0;
  for(size_t c=0;c<t->column_count;c++)total+=t->column_widths && t->column_widths[c]>0 ? t->column_widths[c]:1;
  x[0]=de.inset;
  for(size_t c=0;c<t->column_count;c++)x[c+1]=x[c]+available*(float)(
    (t->column_widths && t->column_widths[c]>0 ? t->column_widths[c]:1)/total);
  int pad=shell_px(6,shell_dpi),minimum=shell_px(30,shell_dpi);
  HDC dc=CreateCompatibleDC(NULL);HFONT font=de_merge_font();
  if(!dc || !font) {if(dc)DeleteDC(dc);if(font)DeleteObject(font);free(x);free(y);free(grid);return 0;}
  HGDIOBJ old=SelectObject(dc,font);int ok=1;
  for(size_t r=0;r<t->row_count;r++)y[r+1]=(float)minimum;
  for(size_t i=0;i<count;i++)if(grid[i].owner==i) {
    const de_merged_cell *m=grid+i;de_merge_view *v=de_mv+de_mv_count++;
    memset(v,0,sizeof(*v));v->block=block;v->row=m->row;v->cell=m->cell;
    v->column=m->column;v->columns=m->columns;v->rows=m->rows;
    v->text=de_merge_text(t->rows[m->row].cells+m->cell);
    if(!v->text) {ok=0;break;}
    v->box.left=(LONG)x[m->column];v->box.right=(LONG)x[m->column+m->columns];
    RECT text={0,0,v->box.right-v->box.left-2*pad,0};if(text.right<1)text.right=1;
    DrawTextW(dc,v->text,-1,&text,DT_CALCRECT|DT_WORDBREAK|DT_NOPREFIX|DT_EDITCONTROL);
    float current=0;for(size_t r=m->row;r<m->row+m->rows;r++)current+=y[r+1];
    float needed=(float)(text.bottom+2*pad);
    if(needed>current)y[m->row+m->rows]+=needed-current;
  }
  SelectObject(dc,old);DeleteObject(font);DeleteDC(dc);
  y[0]=top;for(size_t r=0;r<t->row_count;r++)y[r+1]+=y[r];
  for(size_t i=start;i<de_mv_count;i++) {
    de_mv[i].box.top=(LONG)y[de_mv[i].row];
    de_mv[i].box.bottom=(LONG)y[de_mv[i].row+de_mv[i].rows];
  }
  *height=y[t->row_count]-top;free(x);free(y);free(grid);return ok;
}
static const de_merge_view *de_merge_hit(float x,float y) {
  POINT p={(LONG)x,(LONG)(y+de.scroll_y)};
  for(size_t i=0;i<de_mv_count;i++)if(PtInRect(&de_mv[i].box,p))return de_mv+i;
  return NULL;
}
static void de_merge_paint(HDC dc,const RECT *area) {
  int saved=SaveDC(dc),pad=shell_px(6,shell_dpi);
  IntersectClipRect(dc,area->left,(int)de_toolbar_height(),area->right,area->bottom);
  HFONT font=de_merge_font();HPEN pen=CreatePen(PS_SOLID,1,shell_is_dark() ? RGB(180,180,180):RGB(80,80,80));
  SelectObject(dc,font);SelectObject(dc,pen);SelectObject(dc,GetStockObject(NULL_BRUSH));
  SetBkMode(dc,TRANSPARENT);SetTextColor(dc,shell_is_dark() ? RGB(240,240,240):RGB(24,24,24));
  for(size_t i=0;i<de_mv_count;i++) {
    RECT box=de_mv[i].box;OffsetRect(&box,0,-(int)de.scroll_y);
    Rectangle(dc,box.left,box.top,box.right+1,box.bottom+1);
    InflateRect(&box,-pad,-pad);
    DrawTextW(dc,de_mv[i].text,-1,&box,DT_WORDBREAK|DT_NOPREFIX|DT_EDITCONTROL);
  }
  RestoreDC(dc,saved);DeleteObject(font);DeleteObject(pen);
}
