/* SPDX-License-Identifier: MIT */
/* Docked TOC: native owner-drawn fixed-height list supplies UIA and one Tab stop.
   Native list storage is prepared once per book; paint/layout only visit visible rows. */
static HWND shell_toc_panel,shell_toc_list,shell_toc_empty;
static WNDPROC shell_toc_list_base;
static int shell_toc_open,shell_toc_animating,shell_toc_current=-1,shell_toc_hot=-1;
static int shell_toc_pressed=-1,shell_toc_keyboard,shell_toc_drag,shell_toc_drag_y,shell_toc_drag_top;
static float shell_toc_value,shell_toc_from;
static double shell_toc_start,shell_toc_duration,shell_toc_elapsed;
static int64_t shell_toc_book;
static exr_navigation *shell_toc_owned;
static const exr_navigation *shell_toc_nav;
static size_t shell_toc_nav_count,*shell_toc_rows,shell_toc_count;
static size_t *shell_toc_offsets;
static wchar_t shell_toc_error[512];
static size_t shell_toc_last_part=SIZE_MAX;
static HWND shell_toc_test_focus;
static int shell_toc_scroll_hot;
static int shell_toc_drawing,shell_toc_close_pending;
static int shell_toc_scroll_y;
static int shell_toc_pending_row=-1;
static HDC shell_toc_buffer;
static HBITMAP shell_toc_bitmap;
static HGDIOBJ shell_toc_old_bitmap;
static int shell_toc_buffer_w,shell_toc_buffer_h;
static HDC shell_toc_backbuffer(HDC dc,int w,int h) {
  if(!shell_toc_buffer) shell_toc_buffer=CreateCompatibleDC(dc);
  if(shell_toc_buffer && (w!=shell_toc_buffer_w || h!=shell_toc_buffer_h)) {
    if(shell_toc_bitmap) {SelectObject(shell_toc_buffer,shell_toc_old_bitmap);DeleteObject(shell_toc_bitmap);shell_toc_bitmap=NULL;}
    BITMAPINFO info={0};void *bits=NULL;
    info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);info.bmiHeader.biWidth=w;info.bmiHeader.biHeight=-h;
    info.bmiHeader.biPlanes=1;info.bmiHeader.biBitCount=32;
    shell_toc_bitmap=CreateDIBSection(dc,&info,DIB_RGB_COLORS,&bits,NULL,0);
    if(shell_toc_bitmap) {shell_toc_old_bitmap=SelectObject(shell_toc_buffer,shell_toc_bitmap);shell_toc_buffer_w=w;shell_toc_buffer_h=h;}
  }
  return shell_toc_bitmap ? shell_toc_buffer:dc;
}
static int shell_toc_row_h(void) {return shell_px(34,shell_dpi);}
static int shell_toc_width(void) {
  RECT r;GetClientRect(g.window,&r);int w=r.right-shell_px(56,shell_dpi),max=shell_px(280,shell_dpi);
  return w<max ? (w>0 ? w:0):max;
}
static void shell_toc_fill(HDC dc,RECT r,uint32_t rgb) {
  HBRUSH brush=CreateSolidBrush(shell_colorref(rgb));FillRect(dc,&r,brush);DeleteObject(brush);
}
static int shell_toc_top(void) {int y=shell_toc_scroll_y-shell_px(8,shell_dpi);return y>0 ? y/shell_toc_row_h():0;}
static int shell_toc_visible(void) {
  RECT r;GetClientRect(shell_toc_list,&r);int n=(r.bottom/shell_toc_row_h());return n>0 ? n:1;
}
static void shell_toc_scroll_damage(void) {
  RECT strip;GetClientRect(shell_toc_panel,&strip);strip.left=strip.right-shell_px(12,shell_dpi);strip.top=shell_px(47,shell_dpi);
  InvalidateRect(shell_toc_panel,&strip,FALSE);
}
static int shell_toc_scroll_max(void) {
  RECT r;GetClientRect(shell_toc_list,&r);
  int max=shell_px(36,shell_dpi)+(int)shell_toc_count*shell_toc_row_h()-r.bottom;return max>0 ? max:0;
}
static void shell_toc_scroll_pixels(int y) {
  int max=shell_toc_scroll_max();if(y<0) y=0;if(y>max) y=max;shell_toc_scroll_y=y;
  SendMessageW(shell_toc_list,LB_SETTOPINDEX,shell_toc_top(),0);
  shell_toc_scroll_damage();InvalidateRect(shell_toc_list,NULL,FALSE);
}
static void shell_toc_scroll(int top) {shell_toc_scroll_pixels(top>0 ? shell_px(8,shell_dpi)+top*shell_toc_row_h():0);}
static void shell_toc_ensure(int row,int center) {
  RECT r;GetClientRect(shell_toc_list,&r);int y=shell_px(8,shell_dpi)+row*shell_toc_row_h();
  if(center) shell_toc_scroll_pixels(y-(r.bottom-shell_toc_row_h())/2);
  else if(y<shell_toc_scroll_y) shell_toc_scroll_pixels(y);
  else if(y+shell_toc_row_h()>shell_toc_scroll_y+r.bottom) shell_toc_scroll_pixels(y+shell_toc_row_h()-r.bottom);
}
static RECT shell_toc_thumb(void) {
  RECT r;GetClientRect(shell_toc_panel,&r);
  int top=shell_px(49,shell_dpi),track=r.bottom-top-shell_px(2,shell_dpi);
  int content=shell_px(36,shell_dpi)+(int)shell_toc_count*shell_toc_row_h();
  int view=r.bottom-shell_px(47,shell_dpi),len=content ? view*view/content:track;
  if(len<shell_px(32,shell_dpi)) len=shell_px(32,shell_dpi);
  if(len>track) len=track;
  int max=shell_toc_scroll_max();
  int y=top+(max>0 ? (track-len)*shell_toc_scroll_y/max:0);
  RECT thumb={r.right-shell_px(9,shell_dpi),y,r.right-shell_px(4,shell_dpi),y+len};return thumb;
}
static void shell_toc_layout(void) {
  if(!shell_toc_panel) return;
  RECT r;GetClientRect(g.window,&r);int w=shell_toc_width(),h=r.bottom-shell_px(56,shell_dpi);
  SetWindowPos(shell_toc_panel,HWND_TOP,(int)lroundf((shell_toc_value-1)*w),shell_px(56,shell_dpi),w,h>0 ? h:0,SWP_NOACTIVATE);
  int y=shell_px(47,shell_dpi);
  int hair=(int)(shell_dpi/96);if(hair<1) hair=1;
  MoveWindow(shell_toc_list,shell_px(10,shell_dpi),y,w-shell_px(20,shell_dpi)-hair,h-y>0 ? h-y:0,TRUE);
  SendMessageW(shell_toc_list,LB_SETITEMHEIGHT,0,shell_toc_row_h());
  MoveWindow(shell_toc_empty,shell_px(28,shell_dpi),shell_px(102,shell_dpi),w-shell_px(56,shell_dpi),shell_px(20,shell_dpi),TRUE);
}
static void shell_toc_set(int open,int keyboard) {
  double first=host_probe_ms();
  shell_toc_close_pending=0;
  BOOL animations=FALSE;SystemParametersInfoW(SPI_GETCLIENTAREAANIMATION,0,&animations,0);
  if(open && shell_panel_open) shell_toggle_settings();
  shell_toc_open=open;shell_toc_keyboard=keyboard;
  shell_toc_from=shell_toc_value;shell_toc_start=host_probe_ms();
  shell_toc_duration=180*fabsf((open ? 1.f:0.f)-shell_toc_from);
  host_probe_log("toc_start_ms",shell_toc_start);host_probe_log("toc_from",shell_toc_from);
  host_probe_log("toc_duration",shell_toc_duration);host_probe_log("toc_target",open ? 1:0);
  shell_toc_animating=animations && shell_toc_duration>0;
  if(open) {
    int focus=shell_toc_current>=0 ? shell_toc_current:0;
    SendMessageW(shell_toc_list,LB_SETCURSEL,focus,0);
    shell_toc_ensure(focus,1);
    ShowWindow(shell_toc_list,SW_SHOWNA);EnableWindow(shell_toc_list,shell_toc_count!=0);
    ShowWindow(shell_toc_empty,shell_toc_count ? SW_HIDE:SW_SHOWNA);
    ShowWindow(shell_toc_panel,SW_SHOWNOACTIVATE);
    SetFocus(shell_toc_count ? shell_toc_list:shell_toc_panel);
  }
  if(shell_toc_animating) SetTimer(g.window,0x5754,10,NULL);
  else {
    KillTimer(g.window,0x5754);shell_toc_value=open ? 1:0;shell_toc_elapsed=0;
    shell_toc_layout();if(!open) ShowWindow(shell_toc_panel,SW_HIDE);
  }
  InvalidateRect(shell_toc,NULL,FALSE);InvalidateRect(shell_toc_list,NULL,FALSE);
  host_probe_log("toc_toggle_ms",host_probe_ms()-first);
}
static void shell_toc_hide(void) {
  shell_toc_open=shell_toc_animating=shell_toc_close_pending=0;shell_toc_value=0;
  shell_toc_pending_row=-1;KillTimer(g.window,0x5755);
  KillTimer(g.window,0x5754);ShowWindow(shell_toc_panel,SW_HIDE);InvalidateRect(shell_toc,NULL,FALSE);
}
static void shell_toc_animate(void) {
  double elapsed=host_probe_ms()-shell_toc_start;
  float x=(float)(elapsed/shell_toc_duration);
  shell_toc_value=shell_toc_from+((shell_toc_open ? 1.f:0.f)-shell_toc_from)*shell_ease(fminf(x,1));
  if(x>=1) {
    shell_toc_value=shell_toc_open ? 1:0;shell_toc_animating=0;shell_toc_elapsed=elapsed;
    KillTimer(g.window,0x5754);host_probe_log("toc_animation_ms",elapsed);
  }
  host_probe_log("toc_offset",(shell_toc_value-1)*shell_toc_width());
  shell_toc_layout();if(!shell_toc_open && !shell_toc_animating) ShowWindow(shell_toc_panel,SW_HIDE);
  page_dirty(g.page,1);
}
static size_t shell_toc_offset(const exr_document *doc,size_t chapter,const exr_navigation *entry) {
  if(entry->href && !strncmp(entry->href,"exreader:toc:",13)) {
    size_t size=0;exr_document_text(doc,&size);size_t offset=(size_t)strtoull(entry->href+13,NULL,10);return offset<size ? offset:SIZE_MAX;
  }
  size_t count=0,n=0,resource=SIZE_MAX,node=SIZE_MAX;
  const exr_chapter *cs=exr_document_chapters(doc,&count);
  const exr_node *nodes=exr_document_nodes(doc,&n);
  if(chapter>=count) return SIZE_MAX;
  const char *hash=entry->href ? strchr(entry->href,'#'):NULL;
  if(hash && hash[1]) {
    exr_error error={0};
    if(exr_document_resolve(doc,chapter,hash,&resource,&node,&error)!=EXR_OK || node==SIZE_MAX || node>=n) return SIZE_MAX;
  } else node=cs[chapter].root;
  if(node>=n) return SIZE_MAX;
  return nodes[node].start==SIZE_MAX ? 0:nodes[node].start;
}
static void shell_toc_update_current(void) {
  if(shell_toc_last_part!=g.frame.part) {
    shell_toc_last_part=g.frame.part;
    exr_document *loaded=NULL;const exr_document *doc=g.session.document;exr_error error={0};
    if(g.session.bounded && exr_publication_load(g.session.publication,g.frame.part,&loaded,&error)==EXR_OK) doc=loaded;
    if(doc) for(size_t i=0;i<shell_toc_count;i++) {
      const exr_navigation *e=&shell_toc_nav[shell_toc_rows[i]];
      if(e->part==g.frame.part) shell_toc_offsets[i]=shell_toc_offset(doc,g.session.bounded ? 0:e->part,e);
    }
    exr_document_free(loaded);
  }
  /* Authored TOCs are in reading order; fixed row positions make this O(log N). */
  size_t lo=0,hi=shell_toc_count;
  while(lo<hi) {
    size_t mid=lo+(hi-lo)/2;const exr_navigation *e=&shell_toc_nav[shell_toc_rows[mid]];
    size_t offset=shell_toc_offsets[mid];
    int before=e->part<g.frame.part || (e->part==g.frame.part && offset!=SIZE_MAX && offset<=g.frame.range_start);
    if(before) lo=mid+1;else hi=mid;
  }
  int current=(int)lo-1;
  if(current!=shell_toc_current) {shell_toc_current=current;InvalidateRect(shell_toc_list,NULL,FALSE);}
}
/* Some Gutenberg novels supply only their license in NCX. Recover explicit,
   chapter headings from the book, never from a fixture or
   the filename. This work runs once on book acceptance, before TOC interaction. */
static void shell_toc_recover_chapters(void) {
  size_t authored=0;
  for(size_t i=0;i<shell_toc_nav_count;i++) if(shell_toc_nav[i].role && !strcmp(shell_toc_nav[i].role,"toc")) authored++;
  if(authored>1 || !g.session.bounded) return;
  size_t parts_count=0,count=0;exr_navigation *recovered=NULL;
  const exr_part *parts=exr_publication_parts(g.session.publication,&parts_count);
  for(size_t part=0;part<parts_count;part++) {
    if(!parts[part].in_reading_order) continue;
    exr_document *doc=NULL;exr_error error={0};
    if(exr_publication_load(g.session.publication,part,&doc,&error)!=EXR_OK) continue;
    size_t projection_size=0,node_count=0;const char *projection=exr_document_text(doc,&projection_size);
    const exr_node *nodes=exr_document_nodes(doc,&node_count);
    for(size_t node=0;node<node_count;node++) {
      if(nodes[node].kind!=EXR_NODE_TEXT || !nodes[node].text || nodes[node].start==SIZE_MAX) continue;
      int hidden=0;
      for(size_t ancestor=nodes[node].parent;ancestor<node_count;ancestor=nodes[ancestor].parent) {
        const char *classes=exr_node_attribute(&nodes[ancestor],"class");
        if(classes && strstr(classes,"exr-shell-hide")) {hidden=1;break;}
      }
      if(hidden) continue;
      const char *text=nodes[node].text;size_t size=strlen(text);
    for(size_t at=0;at<size;) {
      const char *start=text+at,*end=memchr(start,'\n',size-at);if(!end) end=text+size;
      at=(size_t)(end-text)+(end<text+size ? 1:0);
      while(start<end) {
        if((unsigned char)*start<=32) start++;
        else if(start+3<=end && !memcmp(start,"　",3)) start+=3;
        else break;
      }
      if(end-start<9 || memcmp(start,"第",3)) continue;
      const char *hui=NULL;
      for(const char *q=start+3;q+3<=end && q-start<40;q++) if(!memcmp(q,"回",3)) {hui=q;break;}
      if(!hui || (hui+3<end && (unsigned char)hui[3]>32 &&
         (hui+6>end || (memcmp(hui+3,"　",3) && memcmp(hui+3,"\xe2\x80\x83",3))))) continue;
      size_t offset=nodes[node].start,token=(size_t)(hui+3-start);
      while(offset+token<=projection_size && offset+token<=nodes[node].end && memcmp(projection+offset,start,token)) offset++;
      if(offset+token>projection_size || offset+token>nodes[node].end) continue;
      char label[513];size_t used=0;
      const char *label_end=end;
      if(hui+3==end || (hui+4==end && hui[3]=='\r')) {
        const char *next=end+1;
        while(next<text+size && ((unsigned char)*next<=32 || *next=='-' || (next+3<=text+size && !memcmp(next,"—",3))))
          next+=(next+3<=text+size && !memcmp(next,"—",3)) ? 3:1;
        const char *line=next<text+size ? memchr(next,'\n',(size_t)(text+size-next)):NULL;
        if(line && line-next<180) label_end=line;
      }
      for(const char *q=start;q<label_end && used<sizeof(label)-5;) {
        if((unsigned char)*q<=32 || *q=='-' || (q+3<=label_end && !memcmp(q,"—",3))) {
          if(used && label[used-1]!=' ') label[used++]=' ';
          q+=(q+3<=label_end && !memcmp(q,"—",3)) ? 3:1;
        } else {
          size_t bytes=(unsigned char)*q>=0xf0 ? 4:(unsigned char)*q>=0xe0 ? 3:(unsigned char)*q>=0xc0 ? 2:1;
          if(q+bytes>label_end || used+bytes>=sizeof(label)) break;
          memcpy(label+used,q,bytes);used+=bytes;q+=bytes;
        }
      }
      while(used && label[used-1]==' ') used--;
      label[used]=0;
      exr_navigation *grown=realloc(recovered,(count+1)*sizeof(*grown));if(!grown) continue;recovered=grown;
      exr_navigation entry={SIZE_MAX,part,NULL,NULL,NULL,NULL};
      entry.label=host_strdup(label);entry.role=host_strdup("toc");entry.base=host_strdup(parts[part].path);
      char href[64];snprintf(href,sizeof(href),"exreader:toc:%llu",(unsigned long long)offset);entry.href=host_strdup(href);
      if(!entry.label || !entry.role || !entry.base || !entry.href) {
        free((void *)entry.label);free((void *)entry.role);free((void *)entry.base);free((void *)entry.href);continue;
      }
      recovered[count++]=entry;
      /* EPUB split boundaries sometimes repeat the preceding chapter heading.
         Keep the later, body-bearing occurrence in reading order. */
      for(size_t previous=0;previous+1<count;previous++) if(!strncmp(recovered[previous].label,start,token)) {
        free((void *)recovered[previous].label);free((void *)recovered[previous].role);
        free((void *)recovered[previous].base);free((void *)recovered[previous].href);
        memmove(recovered+previous,recovered+previous+1,(count-previous-1)*sizeof(*recovered));count--;break;
      }
    }
    }
    exr_document_free(doc);
  }
  if(count>=5) {
    if(shell_toc_owned) exr_navigation_free(shell_toc_owned,shell_toc_nav_count);
    shell_toc_owned=recovered;shell_toc_nav=recovered;shell_toc_nav_count=count;
  } else if(recovered) exr_navigation_free(recovered,count);
}
/* Label of the TOC entry the page is in: whitespace runs (U+3000 included)
   folded to one space, cut with an ellipsis. 0 when the book has no entry here. */
static const wchar_t *shell_toc_current_label(wchar_t *out, size_t capacity) {
  enum { LIMIT = 28 };
  if(shell_toc_current<0 || (size_t)shell_toc_current>=shell_toc_count || capacity<LIMIT+2) return NULL;
  const char *label=shell_toc_nav[shell_toc_rows[shell_toc_current]].label;
  wchar_t *wide=label ? host_wide(label,strlen(label)):NULL;size_t used=0;int gap=0;
  for(const wchar_t *p=wide;p && *p;p++) {
    if(*p==L' ' || *p==L'\t' || *p==L'\r' || *p==L'\n' || *p==0x3000 || *p==0x00a0) {gap=used!=0;continue;}
    if(used+gap>=LIMIT) {out[used++]=0x2026;break;}
    if(gap) out[used++]=L' ';
    out[used++]=*p;gap=0;
  }
  free(wide);out[used]=0;
  return used ? out:NULL;
}
static void shell_toc_load(void) {
  shell_toc_hide();SendMessageW(shell_toc_list,LB_RESETCONTENT,0,0);shell_d2d_toc_clear(host_shell);
  if(shell_toc_owned) exr_navigation_free(shell_toc_owned,shell_toc_nav_count);
  shell_toc_owned=NULL;shell_toc_nav=NULL;
  free(shell_toc_rows);free(shell_toc_offsets);shell_toc_rows=NULL;shell_toc_offsets=NULL;
  shell_toc_count=shell_toc_nav_count=0;shell_toc_current=-1;shell_toc_error[0]=0;
  shell_toc_scroll_y=0;
  shell_toc_book=g.session.book_id;shell_toc_last_part=SIZE_MAX;
  exr_error error={0};exr_status status=EXR_OK;
  if(g.session.bounded) status=exr_publication_navigation(g.session.publication,&shell_toc_nav,&shell_toc_nav_count,&error);
  else if(g.session.document) {
    status=exr_document_navigation(g.session.document,&shell_toc_owned,&shell_toc_nav_count,&error);shell_toc_nav=shell_toc_owned;
  }
  if(status!=EXR_OK) {describe_error(shell_toc_error,512,L"目录无法读取",status,&error);SetWindowTextW(shell_toc_empty,L"目录无法读取");return;}
  shell_toc_recover_chapters();
  shell_toc_rows=malloc(shell_toc_nav_count*sizeof(size_t));shell_toc_offsets=malloc(shell_toc_nav_count*sizeof(size_t));
  if(shell_toc_nav_count && (!shell_toc_rows || !shell_toc_offsets)) {wcscpy(shell_toc_error,L"内存不足");return;}
  SendMessageW(shell_toc_list,WM_SETREDRAW,FALSE,0);
  for(size_t i=0;i<shell_toc_nav_count;i++) {
    const exr_navigation *e=&shell_toc_nav[i];
    if(!e->role || strcmp(e->role,"toc") || e->part==SIZE_MAX) continue;
    wchar_t *label=host_wide(e->label ? e->label:"",strlen(e->label ? e->label:""));
    if(!label || SendMessageW(shell_toc_list,LB_ADDSTRING,0,(LPARAM)label)<0) {free(label);wcscpy(shell_toc_error,L"内存不足");break;}
    free(label);shell_toc_rows[shell_toc_count]=i;shell_toc_offsets[shell_toc_count++]=0;
  }
  SendMessageW(shell_toc_list,WM_SETREDRAW,TRUE,0);
  SetWindowTextW(shell_toc_empty,shell_toc_error[0] ? L"目录无法读取":L"这本书没有目录");
  shell_toc_update_current();
}
static void shell_toc_jump(int row) {
  if(row<0 || (size_t)row>=shell_toc_count) return;
  if(g.job || g.pending || shell_layout_waiting) {
    shell_toc_pending_row=row;SetTimer(g.window,0x5755,10,NULL);return;
  }
  const exr_navigation *e=&shell_toc_nav[shell_toc_rows[row]];
  exr_error error={0};exr_document *loaded=NULL;const exr_document *doc=g.session.document;
  if(g.session.bounded && exr_publication_load(g.session.publication,e->part,&loaded,&error)!=EXR_OK) {set_status(L"目录目标无法读取。");return;}
  if(loaded) doc=loaded;
  size_t offset=doc ? shell_toc_offset(doc,g.session.bounded ? 0:e->part,e):SIZE_MAX;
  host_job *job=offset!=SIZE_MAX ? job_new(JOB_GO):NULL;
  if(!job || exr_anchor_create(doc,offset,offset,&job->anchor,&error)!=EXR_OK) {
    if(job) job_release(job);
    exr_document_free(loaded);set_status(L"目录目标未找到，未跳转。");return;
  }
  shell_toc_offsets[row]=offset;job->book_id=g.session.book_id;job->use_offset=1;job->target_offset=offset;
  job->target_part=e->part;job->has_anchor=1;
  if(g.session.bounded) {
    size_t count;const exr_part *parts=exr_publication_parts(g.session.publication,&count);
    if(e->part>=count || !(job->part_path=host_strdup(parts[e->part].path))) {job_release(job);exr_document_free(loaded);return;}
  }
  exr_document_free(loaded);job->shell_toc_jump=1;job_submit(job);
}
static void shell_toc_pump(void) {
  if(!shell_toc_open) {shell_toc_pending_row=-1;KillTimer(g.window,0x5755);return;}
  if(g.job || g.pending || shell_layout_waiting) return;
  int row=shell_toc_pending_row;shell_toc_pending_row=-1;KillTimer(g.window,0x5755);
  if(row>=0) shell_toc_jump(row);
}
static int shell_toc_draw(const DRAWITEMSTRUCT *item) {
  if(item->hwndItem!=shell_toc_list) return 0;
  if(!shell_toc_drawing) return 1;
  if(item->itemID==(UINT)-1 || item->itemID>=shell_toc_count) return 1;
  unsigned state=0;int row=(int)item->itemID;
  if(row==shell_toc_hot) state|=1;
  if(row==shell_toc_pressed) state|=2;
  if(row==shell_toc_current) state|=8;
  if(shell_toc_keyboard && (GetFocus()==shell_toc_list || shell_toc_test_focus==shell_toc_list) &&
      row==(int)SendMessageW(shell_toc_list,LB_GETCURSEL,0,0)) state|=4;
  const exr_navigation *e=&shell_toc_nav[shell_toc_rows[row]];
  wchar_t *label=host_wide(e->label,strlen(e->label));
  if(label) shell_d2d_toc_row(host_shell,item->hDC,&item->rcItem,label,shell_is_dark(),state,row,14,400,0);
  free(label);return 1;
}
static int shell_toc_key(HWND focus,WPARAM key,int shift) {
  if(key==VK_TAB && shell_active && !shell_panel_open) {
    HWND stops[4]={shell_toc,shell_settings,shell_toc_open ? (shell_toc_count ? shell_toc_list:shell_toc_panel):g.page,g.page};
    int count=shell_toc_open ? 4:3,at=0;for(int i=0;i<count;i++) if(stops[i]==focus) at=i;
    HWND next=stops[(at+(shift ? count-1:1))%count];shell_toc_keyboard=1;SetFocus(next);
    if(host_offscreen) shell_toc_test_focus=next;
    SendMessageW(g.window,WM_CHANGEUISTATE,MAKEWPARAM(UIS_CLEAR,UISF_HIDEFOCUS),0);
    InvalidateRect(shell_toc_list,NULL,FALSE);return 1;
  }
  if(shell_toc_open && key==VK_ESCAPE) {shell_toc_set(0,1);SetFocus(shell_toc);if(host_offscreen) shell_toc_test_focus=shell_toc;return 1;}
  if(!shell_toc_open || (focus!=shell_toc_list && focus!=shell_toc_panel)) return 0;
  int row=(int)SendMessageW(shell_toc_list,LB_GETCURSEL,0,0),old=row;
  switch(key) {
    case VK_UP:row--;break;case VK_DOWN:row++;break;case VK_HOME:row=0;break;case VK_END:row=(int)shell_toc_count-1;break;
    case VK_PRIOR:row-=shell_toc_visible()-1;break;case VK_NEXT:row+=shell_toc_visible()-1;break;
    case VK_RETURN:case VK_SPACE:shell_toc_jump(row);return 1;default:return 0;
  }
  if(row<0) row=0;
  if(row>=(int)shell_toc_count) row=(int)shell_toc_count-1;
  shell_toc_keyboard=1;if(row!=old) SendMessageW(shell_toc_list,LB_SETCURSEL,row,0);
  shell_toc_ensure(row,0);
  InvalidateRect(shell_toc_list,NULL,FALSE);InvalidateRect(shell_toc_panel,NULL,FALSE);return 1;
}
static LRESULT CALLBACK shell_toc_list_proc(HWND window,UINT message,WPARAM wp,LPARAM lp) {
  switch(message) {
    case LB_GETITEMRECT: {
      RECT r;GetClientRect(window,&r);int y=shell_px(8,shell_dpi)+(int)wp*shell_toc_row_h()-shell_toc_scroll_y;
      if((size_t)wp>=shell_toc_count) return LB_ERR;
      *(RECT *)lp=(RECT){0,y,r.right,y+shell_toc_row_h()};return 0;
    }
    case LB_ITEMFROMPOINT: {
      RECT r;GetClientRect(window,&r);int y=(short)HIWORD(lp),x=(short)LOWORD(lp);
      int logical=y+shell_toc_scroll_y-shell_px(8,shell_dpi),row=logical>=0 ? logical/shell_toc_row_h():-1;
      int outside=x<0 || x>=r.right || y<0 || y>=r.bottom || row<0 || (size_t)row>=shell_toc_count;
      return MAKELRESULT(row>=0 ? row:0,outside);
    }
    case WM_PAINT:case WM_PRINTCLIENT: {
      PAINTSTRUCT paint;HDC output=message==WM_PAINT ? BeginPaint(window,&paint):(HDC)wp;
      RECT r;GetClientRect(window,&r);double start=host_probe_ms();
      HDC dc=shell_toc_backbuffer(output,r.right,r.bottom);
      double bound=start,laid=start,flushed=start;
      if(SUCCEEDED(shell_d2d_toc_begin(host_shell,dc,&r,shell_is_dark()))) {
        bound=host_probe_ms();
        shell_toc_drawing=1;
        int top=shell_toc_top(),height=shell_toc_row_h();
        int last=top+(r.bottom+height-1)/height+1;
        if(last>(int)shell_toc_count) last=(int)shell_toc_count;
        for(int row=top;row<last;row++) {
          DRAWITEMSTRUCT item={0};item.hwndItem=window;item.hDC=dc;item.itemID=row;
          int y=shell_px(8,shell_dpi)+row*height-shell_toc_scroll_y;
          item.rcItem=(RECT){0,y,r.right,y+height};shell_toc_draw(&item);
        }
        if(!shell_toc_count) {
          RECT hint={shell_px(18,shell_dpi),shell_px(85,shell_dpi),r.right-shell_px(18,shell_dpi),shell_px(135,shell_dpi)};
          shell_d2d_toc_row(host_shell,dc,&hint,shell_toc_error[0] ? shell_toc_error:L"可以用 PageDown 或滚轮继续翻页",shell_is_dark(),0,-4,14,400,2);
        }
        laid=host_probe_ms();shell_toc_drawing=0;shell_d2d_toc_end(host_shell);flushed=host_probe_ms();
      }
      if(dc!=output) BitBlt(output,0,0,r.right,r.bottom,dc,0,0,SRCCOPY);
      host_probe_log("toc_frame_ms",host_probe_ms()-start);
      host_probe_log("toc_bind_ms",bound-start);host_probe_log("toc_layout_ms",laid-bound);host_probe_log("toc_flush_ms",flushed-laid);
      if(message==WM_PAINT) EndPaint(window,&paint);
      return 0;
    }
    case WM_DESTROY:
      if(shell_toc_bitmap) {SelectObject(shell_toc_buffer,shell_toc_old_bitmap);DeleteObject(shell_toc_bitmap);shell_toc_bitmap=NULL;}
      if(shell_toc_buffer) {DeleteDC(shell_toc_buffer);shell_toc_buffer=NULL;}break;
    case WM_KEYDOWN:if(shell_toc_key(window,wp,GetKeyState(VK_SHIFT)<0)) return 0;break;
    case WM_CHAR:if(wp==VK_SPACE || wp==VK_RETURN || wp==VK_ESCAPE) return 0;break;
    case WM_GETDLGCODE:return DLGC_WANTARROWS|DLGC_WANTCHARS|DLGC_WANTTAB;
    case WM_ERASEBKGND: {RECT r;GetClientRect(window,&r);shell_toc_fill((HDC)wp,r,shell_colors->layer_side);return 1;}
    case WM_MOUSEMOVE: {
      LRESULT hit=SendMessageW(window,LB_ITEMFROMPOINT,0,lp);int row=HIWORD(hit) ? -1:LOWORD(hit);
      if(row!=shell_toc_hot) {shell_toc_hot=row;InvalidateRect(window,NULL,FALSE);}
      TRACKMOUSEEVENT track={sizeof(track),TME_LEAVE,window,0};TrackMouseEvent(&track);break;
    }
    case WM_MOUSELEAVE:shell_toc_hot=-1;InvalidateRect(window,NULL,FALSE);break;
    case WM_LBUTTONDOWN: {
      LRESULT hit=SendMessageW(window,LB_ITEMFROMPOINT,0,lp);shell_toc_keyboard=0;
      shell_toc_pressed=HIWORD(hit) ? -1:LOWORD(hit);
      if(shell_toc_pressed>=0) SendMessageW(window,LB_SETCURSEL,shell_toc_pressed,0);
      SetCapture(window);SetFocus(window);InvalidateRect(window,NULL,FALSE);return 0;
    }
    case WM_LBUTTONUP: {
      int row=shell_toc_pressed;shell_toc_pressed=-1;
      ReleaseCapture();
      LRESULT hit=SendMessageW(window,LB_ITEMFROMPOINT,0,lp);
      if(!HIWORD(hit) && LOWORD(hit)==row) shell_toc_jump(row);
      InvalidateRect(window,NULL,FALSE);return 0;
    }
    case WM_MOUSEWHEEL: {
      RECT panel;GetWindowRect(shell_toc_panel,&panel);POINT p={(short)LOWORD(lp),(short)HIWORD(lp)};
      if(!PtInRect(&panel,p)) return SendMessageW(g.page,message,wp,lp);
      UINT lines=3;SystemParametersInfoW(SPI_GETWHEELSCROLLLINES,0,&lines,0);
      shell_toc_scroll_pixels(shell_toc_scroll_y-(short)HIWORD(wp)/WHEEL_DELTA*(lines==WHEEL_PAGESCROLL ? shell_toc_visible():(int)lines)*shell_toc_row_h());return 0;
    }
    case WM_SETFOCUS:case WM_KILLFOCUS:InvalidateRect(window,NULL,FALSE);break;
  }
  return CallWindowProcW(shell_toc_list_base,window,message,wp,lp);
}
static LRESULT CALLBACK shell_toc_proc(HWND window,UINT message,WPARAM wp,LPARAM lp) {
  switch(message) {
    case WM_ERASEBKGND:return 1;
    case WM_DRAWITEM: {
      const DRAWITEMSTRUCT *item=(const DRAWITEMSTRUCT *)lp;
      if(item->hwndItem==shell_toc_empty) {
        shell_d2d_toc_row(host_shell,item->hDC,&item->rcItem,shell_toc_error[0] ? L"目录无法读取":L"这本书没有目录",shell_is_dark(),0,-3,16,650,2);return TRUE;
      }
      if(shell_toc_draw(item)) return TRUE;
      break;
    }
    case WM_CTLCOLORLISTBOX:SetBkColor((HDC)wp,shell_colorref(shell_colors->layer_side));return (LRESULT)GetStockObject(NULL_BRUSH);
    case WM_KEYDOWN:if(shell_toc_key(window,wp,GetKeyState(VK_SHIFT)<0)) return 0;break;
    case WM_MOUSEWHEEL:return SendMessageW(shell_toc_list,message,wp,lp);
    case WM_MOUSEMOVE: {
      RECT r,thumb=shell_toc_thumb();GetClientRect(window,&r);
      RECT hit={r.right-shell_px(12,shell_dpi),thumb.top,r.right-1,thumb.bottom};POINT p={(short)LOWORD(lp),(short)HIWORD(lp)};
      int hot=PtInRect(&hit,p);
      if(hot!=shell_toc_scroll_hot) {shell_toc_scroll_hot=hot;shell_toc_scroll_damage();}
      if(shell_toc_drag) {
        RECT thumb=shell_toc_thumb();int range=r.bottom-shell_px(51,shell_dpi)-(thumb.bottom-thumb.top);
        int max=shell_toc_scroll_max();
        if(range>0) shell_toc_scroll_pixels(shell_toc_drag_top+((short)HIWORD(lp)-shell_toc_drag_y)*max/range);
      }
      TRACKMOUSEEVENT track={sizeof(track),TME_LEAVE,window,0};TrackMouseEvent(&track);return 0;
    }
    case WM_MOUSELEAVE:shell_toc_scroll_hot=0;shell_toc_scroll_damage();return 0;
    case WM_LBUTTONDOWN: {
      RECT r;GetClientRect(window,&r);POINT p={(short)LOWORD(lp),(short)HIWORD(lp)};
      if((int)shell_toc_count>shell_toc_visible() && p.x>=r.right-shell_px(12,shell_dpi)) {
        RECT thumb=shell_toc_thumb();
        if(PtInRect(&thumb,p)) {shell_toc_drag=1;shell_toc_drag_y=p.y;shell_toc_drag_top=shell_toc_scroll_y;SetCapture(window);}
        else shell_toc_scroll(shell_toc_top()+(p.y<thumb.top ? -1:1)*shell_toc_visible());
      }return 0;
    }
    case WM_LBUTTONUP:shell_toc_drag=0;ReleaseCapture();return 0;
    case WM_CAPTURECHANGED:shell_toc_drag=0;return 0;
    case WM_PAINT:case WM_PRINTCLIENT: {
      PAINTSTRUCT paint;HDC dc=message==WM_PAINT ? BeginPaint(window,&paint):(HDC)wp;
      RECT r;GetClientRect(window,&r);shell_toc_fill(dc,r,shell_colors->layer_side);
      int hair=(int)(shell_dpi/96);if(hair<1) hair=1;
      uint32_t line=shell_is_dark() ? 0x2f2f32:0xededee;
      RECT edge={r.right-hair,0,r.right,r.bottom};shell_toc_fill(dc,edge,line);
      if(message==WM_PRINTCLIENT || paint.rcPaint.top<shell_px(47,shell_dpi)) {
      RECT title={shell_px(20,shell_dpi),0,r.right-shell_px(20,shell_dpi)-hair,shell_px(46,shell_dpi)};
      shell_d2d_toc_row(host_shell,dc,&title,L"目录",shell_is_dark(),0,-1,13,650,0);
      if(shell_toc_count) {
        wchar_t count[64];swprintf(count,64,L"%llu 项",(unsigned long long)shell_toc_count);
        title.left=r.right-shell_px(100,shell_dpi);shell_d2d_toc_row(host_shell,dc,&title,count,shell_is_dark(),0,-2,12,400,1);
      }
      edge=(RECT){0,shell_px(46,shell_dpi),r.right-hair,shell_px(46,shell_dpi)+hair};shell_toc_fill(dc,edge,line);
      }
      if((int)shell_toc_count>shell_toc_visible()) {
        RECT thumb=shell_toc_thumb();uint32_t color=shell_toc_scroll_hot || shell_toc_drag ? shell_colors->text_disabled:(shell_is_dark() ? 0x3b3b3e:0xe0e0e2);
        HBRUSH brush=CreateSolidBrush(shell_colorref(color));HPEN pen=CreatePen(PS_NULL,0,0);
        HGDIOBJ oldb=SelectObject(dc,brush),oldp=SelectObject(dc,pen);
        int width=thumb.right-thumb.left;RoundRect(dc,thumb.left,thumb.top,thumb.right+1,thumb.bottom+1,width,width);
        SelectObject(dc,oldb);SelectObject(dc,oldp);DeleteObject(brush);DeleteObject(pen);
      }
      if(message==WM_PAINT) EndPaint(window,&paint);
      return 0;
    }
  }
  return DefWindowProcW(window,message,wp,lp);
}
static void shell_toc_create(HWND parent) {
  WNDCLASSW type={0};type.lpfnWndProc=shell_toc_proc;type.hInstance=(HINSTANCE)GetWindowLongPtrW(parent,GWLP_HINSTANCE);
  type.lpszClassName=L"EXReaderTOC";type.hCursor=LoadCursor(NULL,IDC_ARROW);RegisterClassW(&type);
  shell_toc_panel=CreateWindowExW(0,type.lpszClassName,L"目录",WS_CHILD|WS_CLIPCHILDREN|WS_CLIPSIBLINGS,0,0,0,0,parent,NULL,type.hInstance,NULL);
  shell_toc_list=CreateWindowExW(0,L"LISTBOX",L"目录列表",WS_CHILD|WS_TABSTOP|LBS_OWNERDRAWFIXED|LBS_HASSTRINGS|LBS_NOTIFY|LBS_NOINTEGRALHEIGHT,
    0,0,0,0,shell_toc_panel,(HMENU)168,type.hInstance,NULL);
  shell_toc_list_base=(WNDPROC)SetWindowLongPtrW(shell_toc_list,GWLP_WNDPROC,(LONG_PTR)shell_toc_list_proc);
  shell_toc_empty=CreateWindowExW(0,L"STATIC",L"这本书没有目录",WS_CHILD|SS_OWNERDRAW,0,0,0,0,shell_toc_panel,(HMENU)169,type.hInstance,NULL);
}
