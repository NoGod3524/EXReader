/* SPDX-License-Identifier: MIT */
/* DirectWrite supplies wrapping, caret geometry and hit testing from one layout. */
static unsigned de_units(const char *text,size_t n) {
  return n ? (unsigned)MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,text,(int)n,NULL,0):0;
}
static unsigned de_run_units(const exr_edit_run *r) {
  return r->kind==EXR_EDIT_TEXT ? de_units(r->text,r->text_size):de_run_trivia(r) ? 0:1;
}
static unsigned de_offset(de_pos p) {
  const exr_edit_block *b=exr_edit_block_at(de.doc,p.block);unsigned offset=0;
  if(!b)return 0;
  for(size_t i=0;i<p.run && i<b->run_count;i++)offset+=de_run_units(&b->runs[i]);
  if(p.run<b->run_count && b->runs[p.run].kind==EXR_EDIT_TEXT)
    offset+=de_units(b->runs[p.run].text,p.byte);
  return offset;
}
static de_pos de_from_offset(size_t block,unsigned offset) {
  const exr_edit_block *b=exr_edit_block_at(de.doc,block);de_pos p=de_start(block);
  if(!b)return p;
  for(size_t i=0;i<b->run_count;i++) {
    const exr_edit_run *r=&b->runs[i];unsigned units=de_run_units(r);
    if(offset<=units) {
      p.run=i;
      if(r->kind==EXR_EDIT_TEXT) {
        unsigned at=0;
        while(p.byte<r->text_size) {
          size_t next=de_next_byte(r->text,r->text_size,p.byte);
          unsigned step=de_units(r->text+p.byte,next-p.byte);
          if(at+step>offset)break;
          at+=step;p.byte=next;
        }
      } else if(offset)p.run++;
      return de_normalize(p);
    }
    offset-=units;
  }
  return de_end(block);
}
static wchar_t *de_paragraph_text(const exr_edit_block *b) {
  if(b->kind!=EXR_EDIT_PARAGRAPH) {
    const wchar_t *label=de_block_trivia(b) ? L"":b->kind==EXR_EDIT_TABLE ? L"[表格]":
      b->kind==EXR_EDIT_IMAGE ? L"[图片]":L"[保留的文档内容]";
    size_t bytes=(wcslen(label)+1)*sizeof(wchar_t);wchar_t *text=malloc(bytes);
    if(text)memcpy(text,label,bytes);return text;
  }
  size_t count=0;
  for(size_t i=0;i<b->run_count;i++)count+=de_run_units(&b->runs[i]);
  if(count>INT_MAX)return NULL;
  wchar_t *text=calloc(count+1,sizeof(wchar_t));if(!text)return NULL;
  size_t at=0;
  for(size_t i=0;i<b->run_count;i++) {
    const exr_edit_run *r=&b->runs[i];
    if(de_run_trivia(r))continue;
    if(r->kind!=EXR_EDIT_TEXT)text[at++]=0xfffc;
    else if(r->text_size)at+=(size_t)MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,
      r->text,(int)r->text_size,text+at,(int)(count-at));
  }
  return text;
}
static void de_drop_layout(void) {
  for(size_t i=0;i<de.row_count;i++)shell_d2d_edit_release(de.rows[i].layout);
  free(de.rows);de.rows=NULL;de.row_count=0;de.extent=0;
}
static int de_measure(int width,int height) {
  /* ponytail: rebuild all paragraph views on edits; cache changed paragraphs if
     editing large documents becomes a measured bottleneck. */
  if(!de.doc || !host_shell)return 0;
  if(!de.layout_dirty && de.width==width && de.height==height && de.dpi==shell_dpi)return 1;
  de_drop_layout();de.width=width;de.height=height;de.dpi=shell_dpi;
  de.inset=(float)shell_px(24,shell_dpi);
  size_t count=exr_edit_block_count(de.doc);
  de.rows=calloc(count ? count:1,sizeof(*de.rows));if(!de.rows)return 0;
  float y=de.inset;
  for(size_t i=0;i<count;i++) {
    wchar_t *text=de_paragraph_text(exr_edit_block_at(de.doc,i));
    if(!text) {de_drop_layout();return 0;}
    shell_d2d_edit_row *row=&de.rows[i];
    HRESULT hr=shell_d2d_edit_layout(host_shell,text,g.font_family[0] ? g.font_family:L"Segoe UI",
      17.f*shell_dpi/96.f,(float)width-2*de.inset,&row->layout,&row->height);
    free(text);
    if(FAILED(hr)) {de_drop_layout();return 0;}
    de.row_count++;row->y=y;
    if(de_block_trivia(exr_edit_block_at(de.doc,i)))row->height=0;
    else y+=row->height+(float)shell_px(8,shell_dpi);
  }
  de.extent=y+de.inset;de.layout_dirty=0;return 1;
}
static void de_scroll(float delta) {
  float limit=de.extent-de.height;if(limit<0)limit=0;
  de.scroll_y+=delta;if(de.scroll_y<0)de.scroll_y=0;
  if(de.scroll_y>limit)de.scroll_y=limit;
  if(g.page)InvalidateRect(g.page,NULL,FALSE);
}
static void de_refresh(int reveal) {
  de.blink=1;
  if(!g.page)return;
  RECT area;GetClientRect(g.page,&area);
  if(de_measure(area.right,area.bottom) && reveal && de.caret_block<de.row_count) {
    float box[4];shell_d2d_edit_row *row=&de.rows[de.caret_block];
    shell_d2d_edit_position(row->layout,de_offset(de_caret()),box);
    float top=row->y+box[1],bottom=top+box[3];
    if(top<de.scroll_y)de.scroll_y=top;
    if(bottom>de.scroll_y+de.height)de.scroll_y=bottom-de.height;
  }
  de_scroll(0);de_title();
}
static de_pos de_hit(float x,float y) {
  if(!de.row_count)return de_caret();
  y+=de.scroll_y;
  size_t block=de.row_count-1;
  for(size_t i=0;i<de.row_count;i++)if(y<de.rows[i].y+de.rows[i].height) {block=i;break;}
  if(exr_edit_block_at(de.doc,block)->kind!=EXR_EDIT_PARAGRAPH) {
    for(size_t distance=1;distance<de.row_count;distance++) {
      if(block+distance<de.row_count && exr_edit_block_at(de.doc,block+distance)->kind==EXR_EDIT_PARAGRAPH)
        return de_start(block+distance);
      if(block>=distance && exr_edit_block_at(de.doc,block-distance)->kind==EXR_EDIT_PARAGRAPH)
        return de_end(block-distance);
    }
    return de_caret();
  }
  return de_from_offset(block,shell_d2d_edit_hit(de.rows[block].layout,x-de.inset,y-de.rows[block].y));
}
static HRESULT de_paint_dc(HDC dc,const RECT *area) {
  if(!de_measure(area->right-area->left,area->bottom-area->top))return E_FAIL;
  de_pos a=de_normalize(de_anchor()),b=de_normalize(de_caret());
  if(de_compare(a,b)>0) {de_pos temp=a;a=b;b=temp;}
  int selected=de_compare(a,b)!=0;
  for(size_t i=0;i<de.row_count;i++) {
    shell_d2d_edit_row *row=&de.rows[i];
    row->start=row->length=0;row->selected_break=0;
    if(selected && i>=a.block && i<=b.block) {
      row->start=i==a.block ? de_offset(a):0;
      unsigned end=de_offset(i==b.block ? b:de_end(i));
      row->length=end>=row->start ? end-row->start:0;
      row->selected_break=i<b.block;
    }
    row->caret=i==de.caret_block ? de_offset(de_caret()):0;
    row->show_caret=i==de.caret_block && de.blink && (!g.page || GetFocus()==g.page || host_offscreen);
  }
  return shell_d2d_edit_paint(host_shell,dc,area,shell_is_dark(),de.rows,de.row_count,de.inset,de.scroll_y);
}
static void de_paint(HWND window) {
  PAINTSTRUCT paint;RECT area;HDC dc=BeginPaint(window,&paint);GetClientRect(window,&area);
  HRESULT hr=de_paint_dc(dc,&area);EndPaint(window,&paint);
  if(hr==S_FALSE)InvalidateRect(window,NULL,FALSE);
}
static void de_vertical(int direction) {
  if(de.caret_block>=de.row_count)return;
  shell_d2d_edit_row *row=&de.rows[de.caret_block];float box[4];
  shell_d2d_edit_position(row->layout,de_offset(de_caret()),box);
  float y=row->y+box[1]+(direction<0 ? -box[3]*.5f:box[3]*1.5f);
  de_set_caret(de_hit(de.inset+box[0],y-de.scroll_y));
}
static void de_line_edge(int end) {
  if(de.caret_block>=de.row_count)return;
  shell_d2d_edit_row *row=&de.rows[de.caret_block];float box[4];
  shell_d2d_edit_position(row->layout,de_offset(de_caret()),box);
  de_set_caret(de_from_offset(de.caret_block,shell_d2d_edit_hit(row->layout,
    end ? (float)de.width:0,box[1]+box[3]*.5f)));
}
