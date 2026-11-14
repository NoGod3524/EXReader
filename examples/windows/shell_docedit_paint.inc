/* SPDX-License-Identifier: MIT */
/* DirectWrite supplies wrapping, caret geometry and hit testing from one layout. */
static unsigned de_units(const char *text,size_t n) {
  return n ? (unsigned)MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,text,(int)n,NULL,0):0;
}
static unsigned de_footnote_label(exr_edit_id id,wchar_t label[32]) {
  exr_edit_footnote note={0};size_t number=0;
  /* ponytail: scan references for labels; cache ordinals if note-heavy documents need it. */
  size_t count=exr_edit_footnote_count(de.doc);
  for(size_t i=0;i<count;i++)
    if(exr_edit_footnote_at(de.doc,i,&note)==EXR_OK && note.id==id) {number=note.number;break;}
  wchar_t digits[32];swprintf(digits,32,L"%zu",number);
  const wchar_t superscript[]=L"⁰¹²³⁴⁵⁶⁷⁸⁹";
  unsigned n=0;for(;digits[n] && n<31;n++)label[n]=superscript[digits[n]-L'0'];
  label[n]=0;return n;
}
static unsigned de_run_units(const exr_edit_run *r) {
  if(r->kind==EXR_EDIT_FOOTNOTE) {wchar_t label[32];return de_footnote_label(r->id,label);}
  return r->kind==EXR_EDIT_TEXT ? de_units(r->text,r->text_size):de_run_trivia(r) ? 0:1;
}
static unsigned de_offset(de_pos p) {
  const exr_edit_block *b=de_block_at(de.doc,p.block);unsigned offset=0;
  if(!b)return 0;
  for(size_t i=0;i<p.run && i<b->run_count;i++)offset+=de_run_units(&b->runs[i]);
  if(p.run<b->run_count && b->runs[p.run].kind==EXR_EDIT_TEXT)
    offset+=de_units(b->runs[p.run].text,p.byte);
  return offset;
}
static de_pos de_from_offset(size_t block,unsigned offset) {
  const exr_edit_block *b=de_block_at(de.doc,block);de_pos p=de_start(block);
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
    if(r->kind==EXR_EDIT_FOOTNOTE) {wchar_t label[32];unsigned n=de_footnote_label(r->id,label);memcpy(text+at,label,n*sizeof(wchar_t));at+=n;}
    else if(r->kind!=EXR_EDIT_TEXT)text[at++]=0xfffc;
    else if(r->text_size)at+=(size_t)MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,
      r->text,(int)r->text_size,text+at,(int)(count-at));
  }
  return text;
}
static void de_drop_layout(void) {
  for(size_t i=0;i<de.row_count+de.footnote_row_count;i++)shell_d2d_edit_release(de.rows[i].layout);
  free(de.rows);de.rows=NULL;de.row_count=de.footnote_row_count=0;de.extent=0;
}
static int de_measure(int width,int height) {
  /* ponytail: rebuild all paragraph views on edits; cache changed paragraphs if
     editing large documents becomes a measured bottleneck. */
  if(!de.doc || !host_shell)return 0;
  if(!de.layout_dirty && de.width==width && de.height==height && de.dpi==shell_dpi)return 1;
  de_drop_layout();de.width=width;de.height=height;de.dpi=shell_dpi;
  de.inset=(float)shell_px(24,shell_dpi);
  size_t count=de_block_count(de.doc),notes=exr_edit_footnote_count(de.doc);
  size_t total=count+(notes ? notes+1:0);
  de.rows=calloc(total ? total:1,sizeof(*de.rows));if(!de.rows)return 0;
  float y=de_toolbar_height()+de.inset;
  float table_top=y,pad=(float)shell_px(6,shell_dpi);size_t table_start=0;
  for(size_t i=0;i<count;i++) {
    const exr_edit_block *block=de_block_at(de.doc,i);
    wchar_t *text=de_paragraph_text(block);
    if(!text) {de_drop_layout();return 0;}
    shell_d2d_edit_row *row=&de.rows[i];
    de_cell cell=de_cell_at(i);float available=(float)width-2*de.inset;
    if(cell.table) {
      const exr_edit_table *t=exr_edit_find_block(de.doc,cell.table)->table;
      de_cell previous=i ? de_cell_at(i-1):(de_cell){0};
      if(previous.table!=cell.table || previous.row!=cell.row) {table_top=y;table_start=i;}
      float unit=shell_dpi/1440.f,left=de.inset;
      for(size_t c=0;c<cell.col;c++)left+=de_column_twips(t,c)*unit;
      float cw=de_column_twips(t,cell.col)*unit;
      if(cw<2*pad+16)cw=2*pad+16;
      row->x=left-de.inset+pad;available=cw-2*pad;
      row->y=cell.paragraph ? de.rows[i-1].y+de.rows[i-1].height+8:table_top+pad;
      row->cell_border=cell.paragraph==0;
      row->cell_box[0]=left;row->cell_box[1]=table_top;row->cell_box[2]=left+cw;
    } else row->y=y;
    HRESULT hr=shell_d2d_edit_layout(host_shell,text,g.font_family[0] ? g.font_family:L"Segoe UI",
      16.f*shell_dpi/96.f,available,&row->layout,&row->height);
    free(text);
    unsigned start=0;
    for(size_t j=0;SUCCEEDED(hr) && j<block->run_count;j++) {
      const exr_edit_run *r=&block->runs[j];unsigned length=de_run_units(r);
      if(length && r->kind==EXR_EDIT_TEXT) {
        exr_edit_run_props resolved=de_resolve_props(block,r);
        const exr_edit_run_props *props=&resolved;
        wchar_t *font=props->font[0] ? host_wide(props->font,strlen(props->font)):NULL;
        if(props->font[0] && !font) {hr=E_OUTOFMEMORY;break;}
        int missing=0;
        hr=shell_d2d_edit_style(host_shell,row->layout,start,length,font,
          (props->size_half_points ? props->size_half_points:24)*shell_dpi/144.f,
          props->bold,props->italic,(props->present&EXR_EDIT_COLOR)!=0,props->color_rgb,&missing);
        if(missing)fprintf(stderr,"font fallback: %s -> default\n",props->font);
        free(font);
      }
      start+=length;
    }
    if(SUCCEEDED(hr))hr=shell_d2d_edit_align(row->layout,
      (block->props.present&EXR_EDIT_ALIGN) ? block->props.alignment:EXR_EDIT_LEFT,&row->height);
    if(FAILED(hr)) {shell_d2d_edit_release(row->layout);row->layout=NULL;de_drop_layout();return 0;}
    de.row_count++;
    if(de_block_trivia(de_block_at(de.doc,i)))row->height=0;
    else if(cell.table) {
      float bottom=row->y+row->height+pad;if(bottom>y)y=bottom;
      de_cell next=de_cell_at(i+1);
      if(next.table!=cell.table || next.row!=cell.row) {
        for(size_t j=table_start;j<=i;j++)de.rows[j].cell_box[3]=y;
      }
    } else y+=row->height+(float)shell_px(8,shell_dpi);
  }
  if(notes) {
    y+=de.inset;
    for(size_t i=0;i<=notes;i++) {
      wchar_t *text=NULL;
      if(!i)text=host_wide("──────── 脚注（单击编辑） ────────",strlen("──────── 脚注（单击编辑） ────────"));
      else {
        exr_edit_footnote note={0};if(exr_edit_footnote_at(de.doc,i-1,&note)!=EXR_OK) {de_drop_layout();return 0;}
        wchar_t *body=host_wide(note.text ? note.text:"",note.text_size);
        if(body) {
          size_t length=wcslen(body)+40;text=calloc(length,sizeof(*text));
          if(text)swprintf(text,length,L"%zu  %ls",note.number,body);free(body);
        }
      }
      if(!text) {de_drop_layout();return 0;}
      shell_d2d_edit_row *row=&de.rows[count+i];row->y=y;
      HRESULT hr=shell_d2d_edit_layout(host_shell,text,g.font_family[0] ? g.font_family:L"Segoe UI",
        14.f*shell_dpi/96.f,(float)width-2*de.inset,&row->layout,&row->height);
      free(text);
      if(FAILED(hr)) {shell_d2d_edit_release(row->layout);row->layout=NULL;de_drop_layout();return 0;}
      de.footnote_row_count++;y+=row->height+(float)shell_px(8,shell_dpi);
    }
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
  if(de_measure(area.right,area.bottom) && reveal && de.caret.view<de.row_count) {
    float box[4];shell_d2d_edit_row *row=&de.rows[de.caret.view];
    shell_d2d_edit_position(row->layout,de_offset(de_caret_pos()),box);
    float top=row->y+box[1],bottom=top+box[3];
    if(top<de.scroll_y+de_toolbar_height())de.scroll_y=top-de_toolbar_height();
    if(bottom>de.scroll_y+de.height)de.scroll_y=bottom-de.height;
  }
  de_scroll(0);de_title();
}
static de_pos de_hit(float x,float y) {
  if(!de.row_count)return de_caret_pos();
  y+=de.scroll_y;
  size_t block=de.row_count-1;
  for(size_t i=0;i<de.row_count;i++) {
    shell_d2d_edit_row *row=&de.rows[i];de_cell cell=de_cell_at(i);
    if(cell.table && x>=row->cell_box[0] && x<=row->cell_box[2] &&
      y>=row->cell_box[1] && y<=row->cell_box[3]) {
      block=i;
      while(block+1<de.row_count && de_same_cell(i,block+1) && y>=de.rows[block+1].y)block++;
      return de_from_offset(block,shell_d2d_edit_hit(de.rows[block].layout,
        x-de.inset-de.rows[block].x,y-de.rows[block].y));
    }
  }
  for(size_t i=0;i<de.row_count;i++)if(y<de.rows[i].y+de.rows[i].height) {block=i;break;}
  if(de_block_at(de.doc,block)->kind!=EXR_EDIT_PARAGRAPH) {
    for(size_t distance=1;distance<de.row_count;distance++) {
      if(block+distance<de.row_count && de_block_at(de.doc,block+distance)->kind==EXR_EDIT_PARAGRAPH)
        return de_start(block+distance);
      if(block>=distance && de_block_at(de.doc,block-distance)->kind==EXR_EDIT_PARAGRAPH)
        return de_end(block-distance);
    }
    return de_caret_pos();
  }
  return de_from_offset(block,shell_d2d_edit_hit(de.rows[block].layout,x-de.inset-de.rows[block].x,y-de.rows[block].y));
}
static HRESULT de_paint_dc(HDC dc,const RECT *area) {
  if(!de_measure(area->right-area->left,area->bottom-area->top))return E_FAIL;
  de_pos a=de_normalize(de_anchor()),b=de_normalize(de_caret_pos());
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
    row->caret=i==de.caret.view ? de_offset(de_caret_pos()):0;
    row->show_caret=i==de.caret.view && de.blink && (!g.page || GetFocus()==g.page || host_offscreen);
  }
  HRESULT hr=shell_d2d_edit_paint(host_shell,dc,area,shell_is_dark(),de.rows,de.row_count+de.footnote_row_count,
    de.inset,de.scroll_y,de_toolbar_height());
  return hr==S_OK ? de_toolbar_paint(dc):hr;
}
static void de_paint(HWND window) {
  PAINTSTRUCT paint;RECT area;HDC dc=BeginPaint(window,&paint);GetClientRect(window,&area);
  HRESULT hr=de_paint_dc(dc,&area);EndPaint(window,&paint);
  if(hr==S_FALSE)InvalidateRect(window,NULL,FALSE);
}
static void de_vertical(int direction) {
  if(!de_measure(de.width,de.height) || de.caret.view>=de.row_count)return;
  shell_d2d_edit_row *row=&de.rows[de.caret.view];float box[4];
  shell_d2d_edit_position(row->layout,de_offset(de_caret_pos()),box);
  float x=de.inset+row->x+box[0];
  float local_y=box[1]+(direction<0 ? -box[3]*.5f:box[3]*1.5f);
  if(de.caret_in_table && (local_y<0 || local_y>=row->height)) {
    de_cell cell=de_cell_at(de.caret.view);
    size_t target=SIZE_MAX,count=de_block_count(de.doc);
    /* Continue within this cell, then the same physical column of the next row.
       Padding and taller siblings must not trap the caret. */
    size_t neighbour=direction<0 ? de.caret.view-1:de.caret.view+1;
    if(neighbour<count && de_same_cell(de.caret.view,neighbour))target=neighbour;
    else {
      for(size_t i=0;i<count;i++) {
        de_cell next=de_cell_at(i);
        if(next.table==cell.table && next.col==cell.col &&
          (direction<0 ? cell.row>0 && next.row==cell.row-1:next.row==cell.row+1) &&
          de_block_at(de.doc,i)->kind==EXR_EDIT_PARAGRAPH) {
          target=i;if(direction>0)break;
        }
      }
      if(target==SIZE_MAX) {
        size_t i=de.caret.view;
        while(direction<0 ? i>0:i+1<count) {
          i=direction<0 ? i-1:i+1;
          if(de_cell_at(i).table!=cell.table && de_block_at(de.doc,i)->kind==EXR_EDIT_PARAGRAPH) {target=i;break;}
        }
      }
    }
    if(target!=SIZE_MAX) {
      row=&de.rows[target];
      de_set_caret(de_from_offset(target,shell_d2d_edit_hit(row->layout,
        x-de.inset-row->x,direction<0 ? row->height-1:0)));
    }
    return;
  }
  de_set_caret(de_hit(x,row->y+local_y-de.scroll_y));
}
static void de_line_edge(int end) {
  if(de.caret.view>=de.row_count)return;
  shell_d2d_edit_row *row=&de.rows[de.caret.view];float box[4];
  shell_d2d_edit_position(row->layout,de_offset(de_caret_pos()),box);
  de_set_caret(de_from_offset(de.caret.view,shell_d2d_edit_hit(row->layout,
    end ? (float)de.width:0,box[1]+box[3]*.5f)));
}
