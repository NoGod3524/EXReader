/* SPDX-License-Identifier: MIT */
/* Host-owned recent books. SQLite retains original bytes; JSON owns content points. */
enum { SHELF_LIMIT=64, SHELF_LIST=190, SHELF_IMPORT, SHELF_TIMER=0x5348 };
typedef struct {
  int64_t id;
  char *path,*title,*author;
  char cover_hash[65],book_hash[65];
  exr_content_anchor anchor;
  char *fixed_id; /* Provider's stable page identity, never a page index. */
  uint64_t opened;
  double progress;
  uint32_t *cover;
  int cover_w,cover_h;
} shelf_book;
static shelf_book shelf_recent[SHELF_LIMIT];
static int shelf_count,shelf_loaded,shelf_writable=1;
static HWND shelf_panel,shelf_list,shelf_add,shelf_children[128];
static int shelf_child_count;
static wchar_t shelf_json_path[HOST_PATH];
static WNDPROC shelf_list_base;
extern int shell_epub_shelf(const exr_source *,char **,void **,size_t *);

static void shelf_free_book(shelf_book *b) {
  free(b->path);free(b->title);free(b->author);free(b->cover);free(b->fixed_id);
  exr_content_anchor_free(&b->anchor);memset(b,0,sizeof(*b));
}
static shelf_book *shelf_find(int64_t id) {
  for(int i=0;i<shelf_count;i++) if(shelf_recent[i].id==id) return &shelf_recent[i];
  return NULL;
}
static void shelf_hash(const void *bytes,size_t size,char out[65]) {
  HCRYPTPROV p=0;HCRYPTHASH h=0;BYTE digest[32];DWORD n=32;
  out[0]=0;
  if(size<=MAXDWORD && CryptAcquireContextW(&p,NULL,NULL,PROV_RSA_AES,CRYPT_VERIFYCONTEXT) &&
    CryptCreateHash(p,CALG_SHA_256,0,0,&h) && CryptHashData(h,bytes,(DWORD)size,0) &&
    CryptGetHashParam(h,HP_HASHVAL,digest,&n,0))
    for(int i=0;i<32;i++) sprintf(out+i*2,"%02x",digest[i]);
  if(h) CryptDestroyHash(h);
  if(p) CryptReleaseContext(p,0);
}
static int shelf_save(void) {
  if(!shelf_loaded) return 1;
  if(!shelf_writable) {annot_error(L"最近阅读记录损坏或不可写，原文件保留。");return 0;}
  cv_text j={0};cv_text_string(&j,"{\"version\":1,\"books\":[");
  for(int i=0;i<shelf_count;i++) {
    shelf_book *b=&shelf_recent[i];if(i)cv_text_string(&j,",");
    cv_text_format(&j,"{\"id\":%lld,\"last_opened_ms\":%llu,\"progress\":%.6f,",(long long)b->id,(unsigned long long)b->opened,b->progress);
    annot_json_string(&j,"path",b->path);cv_text_string(&j,",");
    annot_json_string(&j,"title",b->title);cv_text_string(&j,",");
    annot_json_string(&j,"author",b->author);cv_text_string(&j,",");
    annot_json_string(&j,"book_sha256",b->book_hash);cv_text_string(&j,",");
    annot_json_string(&j,"cover_hash",b->cover_hash);cv_text_string(&j,",");
    annot_json_string(&j,"fixed_page_id",b->fixed_id);cv_text_string(&j,",\"anchor\":");
    if(b->anchor.start.part_id) {
      cv_text_string(&j,"{\"start\":");annot_endpoint_write(&j,&b->anchor.start);
      cv_text_string(&j,",\"end\":");annot_endpoint_write(&j,&b->anchor.end);cv_text_string(&j,"}");
    } else cv_text_string(&j,"null");
    cv_text_string(&j,"}");
  }
  cv_text_string(&j,"]}\n");
  wchar_t temp[HOST_PATH];swprintf(temp,HOST_PATH,L"%ls.tmp",shelf_json_path);
  HANDLE file=INVALID_HANDLE_VALUE;DWORD written=0;int ok=0;
  if(!j.failed && j.size<=8*1024*1024) file=CreateFileW(temp,GENERIC_WRITE,0,NULL,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);
  if(file!=INVALID_HANDLE_VALUE) {
    ok=WriteFile(file,j.data,(DWORD)j.size,&written,NULL) && written==j.size && FlushFileBuffers(file);
    if(!CloseHandle(file))ok=0;
    if(ok)ok=MoveFileExW(temp,shelf_json_path,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH)!=0;
  }
  if(!ok) {DeleteFileW(temp);annot_error(L"最近阅读位置保存失败，请重试。");}
  cv_text_free(&j);return ok;
}
static void shelf_cover(shelf_book *b) {
  if(b->cover)return;
  void *encoded=NULL;size_t bytes=0;exr_bitmap image={0};
  EnterCriticalSection(&g.library_lock);
  exr_library_blob(g.library,b->id,1,&encoded,&bytes,NULL);
  if(!bytes) {
    exr_source source={0};char *author=NULL;
    exr_free(encoded);encoded=NULL;
    if(exr_library_source(g.library,b->id,&source,NULL)==EXR_OK) {
      shell_epub_shelf(&source,&author,&encoded,&bytes);
      if(source.release)source.release(source.context);
    }
    if(author && *author && (!b->author || !*b->author)) {free(b->author);b->author=author;author=NULL;}
    free(author);
    if(bytes)exr_library_cover(g.library,b->id,encoded,bytes,NULL);
  }
  LeaveCriticalSection(&g.library_lock);
  if(bytes && exr_image_decode(encoded,bytes,&image,NULL)==EXR_OK && image.width && image.height) {
    b->cover_w=168;b->cover_h=max(1,min(224,(int)(168.0*image.height/image.width)));
    if(image.height>image.width) {b->cover_h=224;b->cover_w=max(1,(int)(224.0*image.width/image.height));}
    b->cover=malloc((size_t)b->cover_w*b->cover_h*4);
    if(b->cover) for(int y=0;y<b->cover_h;y++) for(int x=0;x<b->cover_w;x++) {
      const unsigned char *p=image.pixels+(size_t)(y*(uint64_t)image.height/b->cover_h)*image.stride+(x*(uint64_t)image.width/b->cover_w)*4;
      unsigned a=p[3];b->cover[y*b->cover_w+x]=(((p[0]*a+255*(255-a))/255)<<16)|(((p[1]*a+255*(255-a))/255)<<8)|((p[2]*a+255*(255-a))/255);
    }
    shelf_hash(encoded,bytes,b->cover_hash);
  }
  exr_bitmap_free(&image);exr_free(encoded);
}
static void shelf_refresh(void) {
  if(!shelf_list)return;
  SendMessageW(shelf_list,WM_SETREDRAW,FALSE,0);SendMessageW(shelf_list,LB_RESETCONTENT,0,0);
  for(int i=0;i<shelf_count;i++) {
    shelf_book *b=&shelf_recent[i];wchar_t *title=host_wide(b->title ? b->title:"",b->title ? strlen(b->title):0);
    shelf_cover(b);SendMessageW(shelf_list,LB_ADDSTRING,0,(LPARAM)(title ? title:L"Untitled"));free(title);
  }
  SendMessageW(shelf_list,LB_SETITEMHEIGHT,0,shell_px(148,shell_dpi));
  if(shelf_count)SendMessageW(shelf_list,LB_SETCURSEL,0,0);
  SendMessageW(shelf_list,WM_SETREDRAW,TRUE,0);InvalidateRect(shelf_list,NULL,TRUE);
  InvalidateRect(shelf_panel,NULL,TRUE);
}
static void shelf_imported(int64_t id,const wchar_t *path) {
  if(!shelf_loaded || !shelf_writable)return;
  int index=shelf_index(id);if(index<0)return;
  shelf_book *b=shelf_find(id);
  if(!b) {
    if(shelf_count==SHELF_LIMIT) {shelf_free_book(&shelf_recent[--shelf_count]);}
    b=&shelf_recent[shelf_count++];memset(b,0,sizeof(*b));b->id=id;
  }
  wchar_t absolute[HOST_PATH];
  if(path && *path && GetFullPathNameW(path,HOST_PATH,absolute,NULL)) {free(b->path);b->path=host_utf8(absolute);}
  free(b->title);b->title=host_strdup(g.shelf[index].title ? g.shelf[index].title:"Untitled");
  if(!b->author)b->author=host_strdup(g.shelf[index].author ? g.shelf[index].author:"");
  shelf_cover(b);shelf_save();shelf_refresh();
}
static void shelf_opened(void) {
  if(!shelf_loaded || !g.has_current)return;
  if(!shelf_find(g.current.id))shelf_imported(g.current.id,NULL);
  shelf_book *b=shelf_find(g.current.id);if(!b)return;
  b->opened=annot_time();
  int index=(int)(b-shelf_recent);shelf_book front=*b;
  memmove(shelf_recent+1,shelf_recent,(size_t)index*sizeof(*b));shelf_recent[0]=front;
  shelf_save();
}
static void shelf_resume(size_t offset) {
  /* Startup may open before the final DPI/viewport is known. Carry the resolved
     content point into that reflow, instead of capturing the containing page. */
  shelf_book *b=shelf_find(g.current.id);
  exr_anchor_free(&shell_anchor);shell_anchor_valid=0;
  if(!b || !host_anchor_copy(&shell_anchor,&b->anchor.start.selector))return;
  shell_anchor.start=shell_anchor.end=offset;
  shell_anchor_offset=offset;shell_anchor_part=g.frame.part;
  shell_anchor_book=g.frame.book_id;shell_anchor_valid=1;
}
static int shelf_capture(void) {
  if(!shelf_loaded || !g.has_current || !g.frame.valid || !g.session.active || (g.job && g.job->kind!=JOB_PREFETCH) || g.pending)return 1;
  shelf_book *b=shelf_find(g.current.id);if(!b)return 1;
  if(g.frame.fixed) {
    size_t n=0;const exr_fixed_page *pages=exr_fixed_pages(g.session.fixed_document,&n);
    if(g.frame.page>=n)return 0;
    char *id=host_strdup(pages[g.frame.page].id);if(!id)return 0;
    free(b->fixed_id);b->fixed_id=id;b->progress=n>1 ? (double)g.frame.page/(n-1):0;
  } else {
    exr_content_anchor point={0};exr_publication *pub=select_publication();
    exr_text_position pos={g.frame.part,g.frame.range_start};
    if(!pub || exr_anchor_from_range(pub,&(exr_text_range){pos,pos},NULL,&point,NULL)!=EXR_OK) {
      annot_error(L"无法捕获阅读锚点，尚未退出本书。");return 0;
    }
    exr_content_anchor_free(&b->anchor);b->anchor=point;
    size_t count=0;exr_publication_parts(pub,&count);
    b->progress=count ? (pos.part+(point.start.text_size ? (double)pos.offset/point.start.text_size:0))/count:0;
  }
  b->progress=fmin(1,fmax(0,b->progress));
  if(!b->book_hash[0]) annot_identity(b->book_hash);
  return shelf_save();
}
static exr_status shelf_restore(host_session *s,const exr_control *control,size_t *page,size_t *offset,int *found,exr_error *error) {
  *found=0;shelf_book *b=shelf_find(s->book_id);
  if(!b || !b->anchor.start.part_id)return EXR_OK;
  if(!s->publication) {
    if(!s->document)return EXR_OK;
    exr_anchor_match point={0};
    exr_status result=exr_anchor_resolve_ex(s->document,&b->anchor.start.selector,control,&point,error);
    if(result!=EXR_OK)return result;
    if(point.state!=EXR_ANCHOR_FOUND)return EXR_FORMAT;
    *offset=point.start;result=page_for_offset(s,*offset,control,page,NULL,NULL,error);
    if(result==EXR_OK)*found=1;
    return result;
  }
  exr_text_range_match match={0};
  exr_status status=exr_range_from_anchor(s->publication,&b->anchor,control,&match,error);
  if(status!=EXR_OK)return status;
  if(match.state!=EXR_ANCHOR_FOUND)return EXR_FORMAT;
  s->part=match.range.start.part;*offset=match.range.start.offset;
  status=bounded_pager(s,s->part,&s->pager,error);
  if(status==EXR_OK)status=page_for_offset(s,*offset,control,page,NULL,NULL,error);
  if(status==EXR_OK)*found=1;
  return status;
}
static void shelf_fixed_page(int64_t id,const exr_fixed_page *pages,size_t count,size_t *target) {
  shelf_book *b=shelf_find(id);if(!b || !b->fixed_id)return;
  for(size_t i=0;i<count;i++)if(pages[i].id && !strcmp(pages[i].id,b->fixed_id)) {*target=i;return;}
}
static int shelf_before_exit(void) {
  if(annot_panel && IsWindowVisible(annot_panel)) {
    SendMessageW(annot_panel,WM_COMMAND,1,0);
    if(IsWindowVisible(annot_panel))return 0;
  }
  return 1;
}
static void shelf_return(void) {
  if(!shell_active || shelf_requested)return;
  if(!shelf_before_exit())return;
  shelf_exit_pending=1;shelf_pump();
  if(shelf_exit_pending)SetTimer(g.window,SHELF_TIMER,30,NULL);
}
static void shelf_pump(void) {
  if(!shelf_exit_pending || g.job || g.pending || g.closing)return;
  if(shelf_exit_pending==1) {
    if(!shelf_capture() || !save_progress()) {shelf_exit_pending=0;KillTimer(g.window,SHELF_TIMER);return;}
    shelf_exit_pending=2; /* Await this save once; a failed disk write stays in the book. */
    if(g.job || g.pending)return;
  }
  if(g.progress_failed) {shelf_exit_pending=0;KillTimer(g.window,SHELF_TIMER);return;}
  shelf_exit_pending=0;shelf_requested=1;g.active_book_id=0;
  shell_selection_reset();memset(&g.selection,0,sizeof(g.selection));
  KillTimer(g.page,PAGE_WHEEL_TIMER);wheel_delta=0;
  KillTimer(g.window,SHELF_TIMER);settings_save();shell_sync();shelf_refresh();
}
static void shelf_open_index(int index) {
  if(index<0 || index>=shelf_count || (g.job && g.job->kind!=JOB_PREFETCH) || g.pending)return;
  shelf_book *b=&shelf_recent[index];int row=shelf_index(b->id);if(row<0)return;
  if(!shelf_before_exit() || !shelf_capture())return;
  if(g.has_current && b->id==g.current.id && g.frame.valid) {
    shelf_requested=0;shell_bar_hidden=0;g.active_book_id=b->id;shelf_opened();shell_sync();
    shell_request_layout();SetFocus(g.page);return;
  }
  SendMessageW(g.books,LB_SETCURSEL,(WPARAM)row,0);open_selected_book();
}
static void shelf_text(HDC dc,const wchar_t *text,RECT r,int size,int weight,uint32_t color,UINT flags) {
  HFONT f=CreateFontW(-shell_px((float)size,shell_dpi),0,0,0,weight,0,0,0,DEFAULT_CHARSET,0,0,CLEARTYPE_QUALITY,0,L"Microsoft YaHei UI");
  HGDIOBJ old=SelectObject(dc,f);SetTextColor(dc,shell_colorref(color));SetBkMode(dc,TRANSPARENT);
  DrawTextW(dc,text,-1,&r,flags|DT_SINGLELINE|DT_VCENTER|DT_END_ELLIPSIS|DT_NOPREFIX);SelectObject(dc,old);DeleteObject(f);
}
static void shelf_draw(const DRAWITEMSTRUCT *d) {
  RECT r=d->rcItem;HDC dc=d->hDC;
  uint32_t bg=d->itemState&ODS_SELECTED ? shell_colors->surface2:shell_colors->layer_page;
  HBRUSH brush=CreateSolidBrush(shell_colorref(bg));FillRect(dc,&r,brush);DeleteObject(brush);
  if(d->itemID>=(UINT)shelf_count)return;
  shelf_book *b=&shelf_recent[d->itemID];int x=r.left+shell_px(24,shell_dpi),y=r.top+shell_px(16,shell_dpi);
  int cw=shell_px(84,shell_dpi),ch=shell_px(112,shell_dpi);RECT cover={x,y,x+cw,y+ch};
  if(b->cover) {
    BITMAPINFO info={0};info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);info.bmiHeader.biWidth=b->cover_w;
    info.bmiHeader.biHeight=-b->cover_h;info.bmiHeader.biPlanes=1;info.bmiHeader.biBitCount=32;
    double scale=fmin((double)cw/b->cover_w,(double)ch/b->cover_h);
    int w=(int)(b->cover_w*scale),h=(int)(b->cover_h*scale);SetStretchBltMode(dc,HALFTONE);
    StretchDIBits(dc,x+(cw-w)/2,y+(ch-h)/2,w,h,0,0,b->cover_w,b->cover_h,b->cover,&info,DIB_RGB_COLORS,SRCCOPY);
  } else {
    brush=CreateSolidBrush(shell_colorref(shell_colors->surface3));FillRect(dc,&cover,brush);DeleteObject(brush);
    wchar_t *title=host_wide(b->title,strlen(b->title));shelf_text(dc,title ? title:L"书",cover,13,600,shell_colors->text,DT_CENTER);free(title);
  }
  x+=cw+shell_px(28,shell_dpi);r.left=x;r.right-=shell_px(32,shell_dpi);r.top=y;r.bottom=y+shell_px(32,shell_dpi);
  wchar_t *title=host_wide(b->title ? b->title:"Untitled",strlen(b->title ? b->title:"Untitled"));
  shelf_text(dc,title ? title:L"Untitled",r,18,600,shell_colors->text,DT_LEFT);free(title);
  r.top+=shell_px(34,shell_dpi);r.bottom+=shell_px(34,shell_dpi);
  wchar_t *author=host_wide(b->author ? b->author:"",strlen(b->author ? b->author:""));
  shelf_text(dc,author && *author ? author:L"作者未提供",r,13,400,shell_colors->text_secondary,DT_LEFT);free(author);
  r.top+=shell_px(34,shell_dpi);r.bottom+=shell_px(34,shell_dpi);wchar_t label[80];
  swprintf(label,80,L"已读 %.0f%%",b->progress*100);shelf_text(dc,label,r,12,400,shell_colors->text_secondary,DT_LEFT);
  RECT bar={x,r.bottom+shell_px(3,shell_dpi),min(x+shell_px(260,shell_dpi),r.right),r.bottom+shell_px(6,shell_dpi)};
  brush=CreateSolidBrush(shell_colorref(shell_colors->surface3));FillRect(dc,&bar,brush);DeleteObject(brush);
  bar.right=bar.left+(int)((bar.right-bar.left)*b->progress);
  brush=CreateSolidBrush(shell_colorref(shell_colors->accent));FillRect(dc,&bar,brush);DeleteObject(brush);
  if((d->itemState&ODS_FOCUS) && !(d->itemState&ODS_NOFOCUSRECT))DrawFocusRect(dc,&d->rcItem);
}
static LRESULT CALLBACK shelf_list_proc(HWND w,UINT m,WPARAM wp,LPARAM lp) {
  if(m==WM_ERASEBKGND) {RECT r;GetClientRect(w,&r);HBRUSH b=CreateSolidBrush(shell_colorref(shell_colors->layer_page));FillRect((HDC)wp,&r,b);DeleteObject(b);return 1;}
  if(m==WM_LBUTTONUP) {LRESULT result=CallWindowProcW(shelf_list_base,w,m,wp,lp);DWORD item=(DWORD)SendMessageW(w,LB_ITEMFROMPOINT,0,lp);if(!HIWORD(item))shelf_open_index(LOWORD(item));return result;}
  if(m==WM_KEYDOWN && wp==VK_RETURN) {shelf_open_index((int)SendMessageW(w,LB_GETCURSEL,0,0));return 0;}
  return CallWindowProcW(shelf_list_base,w,m,wp,lp);
}
static LRESULT CALLBACK shelf_proc(HWND w,UINT m,WPARAM wp,LPARAM lp) {
  switch(m) {
    case WM_ERASEBKGND:return 1;
    case WM_SIZE:shelf_layout();return 0;
    case WM_COMMAND:if(LOWORD(wp)==SHELF_IMPORT) {g.auto_open_imported=1;import_path(NULL,1);return 0;}break;
    case WM_DRAWITEM: {
      const DRAWITEMSTRUCT *d=(const DRAWITEMSTRUCT *)lp;
      if(d->hwndItem==shelf_list)shelf_draw(d);
      else shell_d2d_control(host_shell,d->hDC,&d->rcItem,L"＋ 打开书籍",shell_is_dark(),1,(d->itemState&ODS_SELECTED ? 2:0)|(d->itemState&ODS_FOCUS ? 4:0));
      return TRUE;
    }
    case WM_CTLCOLORLISTBOX:SetBkColor((HDC)wp,shell_colorref(shell_colors->layer_page));return (LRESULT)GetStockObject(NULL_BRUSH);
    case WM_PAINT:case WM_PRINTCLIENT: {
      PAINTSTRUCT p;HDC dc=m==WM_PAINT ? BeginPaint(w,&p):(HDC)wp;RECT r;GetClientRect(w,&r);
      HBRUSH bg=CreateSolidBrush(shell_colorref(shell_colors->layer_page));FillRect(dc,&r,bg);DeleteObject(bg);
      r.left=shell_px(48,shell_dpi);r.top=shell_px(24,shell_dpi);r.bottom=shell_px(68,shell_dpi);
      shelf_text(dc,L"书架",r,28,600,shell_colors->text,DT_LEFT);
      r.top=shell_px(76,shell_dpi);r.bottom=shell_px(104,shell_dpi);wchar_t label[96];
      swprintf(label,96,L"最近阅读  ·  %d 本书",shelf_count);shelf_text(dc,label,r,13,400,shell_colors->text_secondary,DT_LEFT);
      if(!shelf_count) {GetClientRect(w,&r);shelf_text(dc,L"打开一本书，开始阅读",r,18,400,shell_colors->text_secondary,DT_CENTER);}
      if(m==WM_PAINT)EndPaint(w,&p);
      return 0;
    }
  }
  return DefWindowProcW(w,m,wp,lp);
}
static int shelf_layout(void) {
  if(!shelf_visible || !shelf_panel)return 0;
  RECT r;GetClientRect(g.window,&r);SetWindowPos(shelf_panel,HWND_TOP,0,0,r.right,r.bottom,SWP_NOACTIVATE);
  int pad=shell_px(24,shell_dpi),top=shell_px(124,shell_dpi);
  MoveWindow(shelf_list,pad,top,max(0,r.right-2*pad),max(0,r.bottom-top-pad),TRUE);
  MoveWindow(shelf_add,r.right-shell_px(188,shell_dpi),shell_px(35,shell_dpi),shell_px(140,shell_dpi),shell_px(40,shell_dpi),TRUE);
  return 1;
}
static void shelf_show(int show) {
  if(!shelf_panel || shelf_visible==show)return;
  shelf_visible=show;
  if(show) {
    shelf_child_count=0;
    for(HWND child=GetWindow(g.window,GW_CHILD);child;child=GetWindow(child,GW_HWNDNEXT))
      if(child!=shelf_panel && IsWindowVisible(child) && shelf_child_count<128) {shelf_children[shelf_child_count++]=child;ShowWindow(child,SW_HIDE);}
    shelf_layout();shelf_refresh();ShowWindow(shelf_panel,SW_SHOWNA);SetFocus(shelf_list);
  } else {
    ShowWindow(shelf_panel,SW_HIDE);
    for(int i=0;i<shelf_child_count;i++)ShowWindow(shelf_children[i],SW_SHOWNA);
    shelf_child_count=0;
  }
}
static void shelf_create(HWND parent) {
  WNDCLASSW c={0};c.lpfnWndProc=shelf_proc;c.hInstance=GetModuleHandleW(NULL);c.lpszClassName=L"EXReaderShelf";c.hCursor=LoadCursor(NULL,IDC_ARROW);RegisterClassW(&c);
  shelf_panel=CreateWindowExW(WS_EX_CONTROLPARENT,c.lpszClassName,L"书架",WS_CHILD|WS_CLIPCHILDREN,0,0,0,0,parent,NULL,c.hInstance,NULL);
  shelf_list=CreateWindowExW(0,L"LISTBOX",L"最近阅读",WS_CHILD|WS_VISIBLE|WS_TABSTOP|WS_VSCROLL|LBS_OWNERDRAWFIXED|LBS_HASSTRINGS|LBS_NOINTEGRALHEIGHT|LBS_NOTIFY,
    0,0,0,0,shelf_panel,(HMENU)SHELF_LIST,NULL,NULL);
  shelf_list_base=(WNDPROC)SetWindowLongPtrW(shelf_list,GWLP_WNDPROC,(LONG_PTR)shelf_list_proc);
  shelf_add=CreateWindowExW(0,L"BUTTON",L"打开书籍",WS_CHILD|WS_VISIBLE|WS_TABSTOP|BS_OWNERDRAW,0,0,0,0,shelf_panel,(HMENU)SHELF_IMPORT,NULL,NULL);
}
static void shelf_load(void) {
  path_join(shelf_json_path,HOST_PATH,g.data_dir,L"recent-books.json");shelf_loaded=1;
  FILE *f=_wfopen(shelf_json_path,L"rb");if(!f) {shelf_writable=GetLastError()==ERROR_FILE_NOT_FOUND || GetFileAttributesW(shelf_json_path)==INVALID_FILE_ATTRIBUTES;return;}
  fseek(f,0,SEEK_END);long size=ftell(f);rewind(f);char *data=size>=0 && size<=8*1024*1024 ? calloc((size_t)size+1,1):NULL;
  int ok=data && fread(data,1,(size_t)size,f)==(size_t)size;fclose(f);
  for(long i=0;ok && i<size;i++) {
    if(!data[i])ok=0;
    if(data[i]=='\\' && i+1<size) {
      if(data[i+1]=='u' && i+5<size && !memcmp(data+i+2,"0000",4))ok=0;
      i++;
    }
  }
  char *error=NULL;cv_json *root=ok ? cv_json_parse(data,(size_t)size,&error):NULL;free(error);free(data);
  const cv_json *books=cv_json_get(root,"books");uint64_t version=0;
  ok=root && annot_uint(root,"version",&version) && version==1 && books && books->type==CV_JSON_ARRAY && books->count<=SHELF_LIMIT;
  for(size_t i=0;ok && i<books->count;i++) {
    const cv_json *o=books->items[i],*progress=cv_json_get(o,"progress"),*a=cv_json_get(o,"anchor");
    shelf_book *b=&shelf_recent[shelf_count++];uint64_t id=0;char *hash=NULL,*cover=NULL;
    ok=annot_uint(o,"id",&id) && id>0 && id<=INT64_MAX && annot_uint(o,"last_opened_ms",&b->opened) &&
      annot_string(o,"path",&b->path,1) && annot_string(o,"title",&b->title,0) && annot_string(o,"author",&b->author,0) &&
      annot_string(o,"book_sha256",&hash,0) && (strlen(hash)==0 || strlen(hash)==64) &&
      annot_string(o,"cover_hash",&cover,0) && (strlen(cover)==0 || strlen(cover)==64) &&
      annot_string(o,"fixed_page_id",&b->fixed_id,1) && progress && progress->type==CV_JSON_NUMBER && progress->number>=0 && progress->number<=1;
    if(ok) {b->id=(int64_t)id;b->progress=progress->number;strcpy(b->book_hash,hash);strcpy(b->cover_hash,cover);}
    free(hash);free(cover);
    if(ok && a && a->type!=CV_JSON_NULL) ok=annot_endpoint_read(cv_json_get(a,"start"),&b->anchor.start) && annot_endpoint_read(cv_json_get(a,"end"),&b->anchor.end);
    if(ok && !a)ok=0;
    for(int j=0;ok && j<shelf_count-1;j++)if(shelf_recent[j].id==b->id)ok=0;
  }
  cv_json_free(root);
  if(!ok) {for(int i=0;i<shelf_count;i++)shelf_free_book(&shelf_recent[i]);shelf_count=0;shelf_writable=0;annot_error(L"最近阅读记录损坏，原文件保留。");}
  shelf_refresh();
}
static void shelf_destroy(void) {
  for(int i=0;i<shelf_count;i++)shelf_free_book(&shelf_recent[i]);
  shelf_count=0;
}
