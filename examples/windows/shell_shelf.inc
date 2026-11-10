/* SPDX-License-Identifier: MIT */
/* Sole bookshelf renderer: grid/list, series, tags and empty state. */
static int shelf_draw_book_cover(HDC dc,RECT r,int64_t id) {
  shelf_book *b=shelf_find(id);if(!b)return 0;
  shelf_cover(b);if(!b->cover)return 0;
  BITMAPINFO info={0};info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);info.bmiHeader.biWidth=b->cover_w;
  info.bmiHeader.biHeight=-b->cover_h;info.bmiHeader.biPlanes=1;info.bmiHeader.biBitCount=32;
  double scale=fmin((double)(r.right-r.left)/b->cover_w,(double)(r.bottom-r.top)/b->cover_h);
  int w=(int)(b->cover_w*scale),h=(int)(b->cover_h*scale);SetStretchBltMode(dc,HALFTONE);
  StretchDIBits(dc,r.left+(r.right-r.left-w)/2,r.top+(r.bottom-r.top-h)/2,w,h,0,0,b->cover_w,b->cover_h,b->cover,&info,DIB_RGB_COLORS,SRCCOPY);
  return 1;
}
static uint32_t sm_hash_rgb(const char *sha) {
  static const uint32_t palette[6]={0x5b6ee1,0x2f8f6b,0xb4572e,0x8a4fb8,0x3b7ea1,0xa8862b};
  return palette[(sha ? (unsigned char)sha[0]+(unsigned char)sha[1]:0)%6];
}
static void sm_draw_cover(HDC dc,RECT r,int s,int e) {
  sm_cover_cache *c=sm_cover(e);
  if(c) {
    HDC src=CreateCompatibleDC(dc);HGDIOBJ old=SelectObject(src,c->bitmap);
    SetStretchBltMode(dc,HALFTONE);SetBrushOrgEx(dc,0,0,NULL);
    StretchBlt(dc,r.left,r.top,r.right-r.left,r.bottom-r.top,src,0,0,c->w,c->h,SRCCOPY);
    SelectObject(src,old);DeleteDC(src);return;
  }
  if(shelf_draw_book_cover(dc,r,g.shelf[s].id))return;
  /* default cover: colour from the content hash, title typeset on it */
  sm_fill(dc,&r,sm_hash_rgb(e>=0 ? sm_entries[e].sha:NULL));
  RECT band={r.left,r.top+(r.bottom-r.top)/6,r.right,r.top+(r.bottom-r.top)/6+shell_px(2,shell_dpi)};sm_fill(dc,&band,0xffffff);
  SetTextColor(dc,RGB(255,255,255));
  if(r.right-r.left<shell_px(64,shell_dpi)) { /* thumbnail: first character only */
    const char *t=sm_title((size_t)s);size_t n=1;while(t[n] && ((unsigned char)t[n]&0xc0)==0x80)n++;
    char first[8]={0};memcpy(first,t,min(n,(size_t)7));HGDIOBJ old=SelectObject(dc,sm_cover_font[1]);
    RECT text=r;text.top+=(r.bottom-r.top)/6;sm_text(dc,first,&text,DT_CENTER|DT_VCENTER|DT_SINGLELINE);SelectObject(dc,old);return;
  }
  RECT text={r.left+shell_px(10,shell_dpi),r.top+(r.bottom-r.top)/4,r.right-shell_px(10,shell_dpi),r.bottom-shell_px(10,shell_dpi)};
  HGDIOBJ old=SelectObject(dc,sm_cover_font[0]);sm_text(dc,sm_title((size_t)s),&text,DT_WORDBREAK|DT_EDITCONTROL|DT_END_ELLIPSIS);SelectObject(dc,old);
}
static void sm_paint_shelf(HDC dc,RECT client,HFONT ui,HFONT small_font,HFONT bold) {
  int pad=shell_px(24,shell_dpi),y=shell_px(60,shell_dpi);
  sm_collect_tags();
  /* tag filter bar */
  SelectObject(dc,ui);int x=pad,total=0,untagged=0;
  int *order=malloc((g.shelf_count+1)*sizeof(int));if(!order)return;
  for(size_t s=0;s<g.shelf_count;s++) if(g.shelf[s].id>0){int e=sm_book_entry(s);total++;untagged+=e<0 || !sm_entries[e].tag_count;}
  wchar_t label[160];swprintf(label,160,L"全部 %d",total);x=sm_chip(dc,x,y,label,sm_filter==-1,SM_HIT_TAG,-1);
  for(int t=0;t<sm_tag_total;t++) {
    int n=0;for(size_t s=0;s<g.shelf_count;s++) n+=g.shelf[s].id>0 && sm_has_tag(sm_book_entry(s),sm_tags[t]);
    wchar_t *w=host_wide(sm_tags[t],strlen(sm_tags[t]));swprintf(label,160,L"%ls %d",w ? w:L"",n);free(w);
    x=sm_chip(dc,x,y,label,sm_filter==t,SM_HIT_TAG,t);
  }
  swprintf(label,160,L"未分类 %d",untagged);sm_chip(dc,x,y,label,sm_filter==-2,SM_HIT_TAG,-2);
  int top=y+shell_px(44,shell_dpi);
  HRGN clip=CreateRectRgn(0,top,client.right,client.bottom);SelectClipRgn(dc,clip);
  int n=sm_order(order);y=top+shell_px(8,shell_dpi)-sm_scroll;
  int card=shell_px(128,shell_dpi),cover_h=shell_px(180,shell_dpi),gap=shell_px(20,shell_dpi);
  int columns=max(1,(client.right-2*pad+gap)/(card+gap)),col=0;
  const char *group=(const char *)-1;
  for(int i=0;i<n;i++) {
    int s=order[i],e=sm_book_entry((size_t)s);const char *series=sm_series_of(s);
    if(group==(const char *)-1 || (!series != !group) || (series && strcmp(series,group))) {
      if(col){y+=cover_h+shell_px(64,shell_dpi);col=0;}
      int members=0;for(int k=i;k<n;k++){const char *o=sm_series_of(order[k]);if(series ? (o && !strcmp(o,series)):!o)members++;}
      wchar_t *w=series ? host_wide(series,strlen(series)):NULL;
      if(series)swprintf(label,160,L"系列 · %ls（%d 本）",w ? w:L"",members);else swprintf(label,160,L"未分组（%d 本）",members);free(w);
      SelectObject(dc,bold);SetTextColor(dc,shell_colorref(shell_colors->text_secondary));
      RECT h={pad,y,client.right-pad,y+shell_px(28,shell_dpi)};DrawTextW(dc,label,-1,&h,DT_VCENTER|DT_SINGLELINE);
      y+=shell_px(32,shell_dpi);group=series;
    }
    if(!sm_list) {
      int cx=pad+col*(card+gap);RECT cover={cx,y,cx+card,y+cover_h};
      RECT frame=cover;InflateRect(&frame,shell_px(4,shell_dpi),shell_px(4,shell_dpi));
      if(sm_hot==s)sm_round(dc,&frame,shell_colors->surface2,shell_colors->accent,shell_px(9,shell_dpi));
      sm_draw_cover(dc,cover,s,e);
      SelectObject(dc,ui);SetTextColor(dc,shell_colorref(shell_colors->text));
      RECT t={cx,cover.bottom+shell_px(6,shell_dpi),cx+card,cover.bottom+shell_px(26,shell_dpi)};
      char line[512];
      if(series && e>=0 && sm_entries[e].has_index)snprintf(line,512,"%g · %s",sm_entries[e].series_index,sm_title((size_t)s));
      else snprintf(line,512,"%s",sm_title((size_t)s));
      sm_text(dc,line,&t,DT_SINGLELINE|DT_END_ELLIPSIS);
      SelectObject(dc,small_font);SetTextColor(dc,shell_colorref(shell_colors->text_secondary));
      OffsetRect(&t,0,shell_px(20,shell_dpi));sm_text(dc,sm_author((size_t)s),&t,DT_SINGLELINE|DT_END_ELLIPSIS);
      RECT hit={cx,y,cx+card,t.bottom};sm_add_hit(hit,SM_HIT_BOOK,s);
      if(++col==columns){col=0;y+=cover_h+shell_px(64,shell_dpi);}
    } else {
      int row=shell_px(64,shell_dpi);RECT r={pad,y,client.right-pad,y+row-shell_px(6,shell_dpi)};
      sm_round(dc,&r,sm_hot==s ? shell_colors->surface2:shell_colors->layer_float,shell_colors->surface3,shell_px(9,shell_dpi));
      RECT cover={r.left+shell_px(10,shell_dpi),r.top+shell_px(5,shell_dpi),r.left+shell_px(46,shell_dpi),r.bottom-shell_px(5,shell_dpi)};
      sm_draw_cover(dc,cover,s,e);
      int c1=cover.right+shell_px(14,shell_dpi),w=r.right-c1;
      RECT t={c1,r.top+shell_px(8,shell_dpi),c1+w*34/100,r.top+shell_px(30,shell_dpi)};
      char line[512];
      if(series && e>=0 && sm_entries[e].has_index)snprintf(line,512,"%g · %s",sm_entries[e].series_index,sm_title((size_t)s));
      else snprintf(line,512,"%s",sm_title((size_t)s));
      SelectObject(dc,ui);SetTextColor(dc,shell_colorref(shell_colors->text));sm_text(dc,line,&t,DT_SINGLELINE|DT_END_ELLIPSIS);
      SelectObject(dc,small_font);SetTextColor(dc,shell_colorref(shell_colors->text_secondary));
      OffsetRect(&t,0,shell_px(22,shell_dpi));sm_text(dc,sm_author((size_t)s),&t,DT_SINGLELINE|DT_END_ELLIPSIS);
      wchar_t info[256];sm_entry *x=e>=0 ? &sm_entries[e]:NULL;
      int started=x && (x->read_ms || x->opens);
      if(started && x->part_count)swprintf(info,256,L"进度 %.1f%% · 已读 %llu 页 · 第 %llu/%llu 章",x->progress*100,(unsigned long long)x->turns,(unsigned long long)(x->part+1),(unsigned long long)x->part_count);
      else if(started && x->page_count)swprintf(info,256,L"进度 %.1f%% · 第 %llu/%llu 页",x->progress*100,(unsigned long long)(x->page+1),(unsigned long long)x->page_count);
      else if(started)swprintf(info,256,L"进度 %.1f%% · 已读 %llu 页",x->progress*100,(unsigned long long)x->turns);
      else swprintf(info,256,L"未读");
      RECT p={c1+w*36/100,r.top+shell_px(8,shell_dpi),c1+w*72/100,r.top+shell_px(30,shell_dpi)};
      SelectObject(dc,ui);SetTextColor(dc,shell_colorref(shell_colors->text));DrawTextW(dc,info,-1,&p,DT_SINGLELINE|DT_END_ELLIPSIS);
      if(started) {
        RECT bar={p.left,p.bottom+shell_px(8,shell_dpi),p.right-shell_px(20,shell_dpi),p.bottom+shell_px(12,shell_dpi)};sm_fill(dc,&bar,shell_colors->surface3);
        bar.right=bar.left+(int)((bar.right-bar.left)*x->progress);sm_fill(dc,&bar,shell_colors->accent);
      }
      wchar_t tags[512];sm_tags_line(e,tags,512);
      RECT q={c1+w*72/100,r.top+shell_px(8,shell_dpi),r.right-shell_px(12,shell_dpi),r.bottom-shell_px(8,shell_dpi)};
      SelectObject(dc,small_font);SetTextColor(dc,shell_colorref(shell_colors->accent));DrawTextW(dc,tags[0] ? tags:L"未分类",-1,&q,DT_WORDBREAK|DT_END_ELLIPSIS|DT_NOPREFIX);
      sm_add_hit(r,SM_HIT_BOOK,s);y+=row;
    }
  }
  if(col)y+=cover_h+shell_px(64,shell_dpi);
  if(!n){SelectObject(dc,ui);SetTextColor(dc,shell_colorref(shell_colors->text_secondary));RECT r={pad,y,client.right-pad,y+shell_px(40,shell_dpi)};DrawTextW(dc,g.shelf_count ? L"没有符合筛选的书。":L"书架为空：拖入或导入书籍。",-1,&r,DT_SINGLELINE);}
  sm_content_h=y+sm_scroll-top+shell_px(24,shell_dpi);
  SelectClipRgn(dc,NULL);DeleteObject(clip);free(order);
}
