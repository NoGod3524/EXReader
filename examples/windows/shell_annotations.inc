/* SPDX-License-Identifier: MIT */
/* UI-owned sidecar. Engine anchors are the only persisted location. */
#include <wincrypt.h>
#ifdef __GNUC__
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-variable"
#endif
#include "../../tools/convert_json.c"
#ifdef __GNUC__
#pragma GCC diagnostic pop
#endif
typedef struct {
  exr_content_anchor anchor;
  char *text;
  uint64_t created,updated;
  int color;
  exr_text_range range; /* resolved session cache; never serialized */
  int found;
} shell_annotation;
static void sy_note(const char *sha);static void sy_boot(void);
static shell_annotation *annotations;
static int annot_editing=-1,annot_writable;
static int64_t annot_book;
static char annot_hash[65];
static wchar_t annot_path[HOST_PATH];
static HWND annot_panel,annot_edit;
static HBRUSH annot_brush;
static void annot_close(void) { if(annot_panel) ShowWindow(annot_panel,SW_HIDE); SetFocus(g.page); }
static void annot_free(shell_annotation *a) {exr_content_anchor_free(&a->anchor);free(a->text);memset(a,0,sizeof(*a));}
static void annot_clear(void) {
  if(annot_panel) ShowWindow(annot_panel,SW_HIDE);
  for(int i=0;i<annot_count;i++) annot_free(&annotations[i]);
  free(annotations);annotations=NULL;annot_count=0;annot_selected=-1;annot_writable=0;
}
static uint64_t annot_time(void) {
  FILETIME ft;ULARGE_INTEGER value;GetSystemTimeAsFileTime(&ft);value.LowPart=ft.dwLowDateTime;value.HighPart=ft.dwHighDateTime;
  return (value.QuadPart-116444736000000000ULL)/10000;
}
static void annot_error(const wchar_t *text) {
  set_status(text);
  if(!host_offscreen) MessageBoxW(g.window,text,L"标注",MB_OK|MB_ICONERROR);
}
static int shell_content_identity(int64_t book_id,char out[65]) {
  exr_source source={0};HCRYPTPROV provider=0;HCRYPTHASH hash=0;BYTE digest[32];DWORD size=32;
  int ok=0;BYTE bytes[65536];
  EnterCriticalSection(&g.library_lock);
  if(exr_library_source(g.library,book_id,&source,NULL)!=EXR_OK) goto done;
  if(!CryptAcquireContextW(&provider,NULL,NULL,PROV_RSA_AES,CRYPT_VERIFYCONTEXT) ||
     !CryptCreateHash(provider,CALG_SHA_256,0,0,&hash)) goto done;
  for(uint64_t at=0;at<source.size;) {
    size_t count=source.read_at(source.context,at,bytes,(size_t)min(sizeof(bytes),source.size-at));
    if(!count || !CryptHashData(hash,bytes,(DWORD)count,0)) goto done;
    at+=count;
  }
  if(!CryptGetHashParam(hash,HP_HASHVAL,digest,&size,0)) goto done;
  for(int i=0;i<32;i++) sprintf(out+2*i,"%02x",digest[i]);
  ok=1;
done:
  if(source.release) source.release(source.context);
  LeaveCriticalSection(&g.library_lock);
  if(hash) CryptDestroyHash(hash);
  if(provider) CryptReleaseContext(provider,0);
  return ok;
}
static int annot_identity(char out[65]) {return shell_content_identity(g.frame.book_id,out);}
static void annot_json_string(cv_text *j,const char *key,const char *value) {
  cv_text_json(j,key);cv_text_string(j,":");
  if(value) cv_text_json(j,value);else cv_text_string(j,"null");
}
static void annot_endpoint_write(cv_text *j,const exr_content_endpoint *e) {
  cv_text_string(j,"{");annot_json_string(j,"part_id",e->part_id);cv_text_string(j,",");
  annot_json_string(j,"part_path",e->part_path);
  cv_text_format(j,",\"text_revision\":\"%016llx\",\"text_size\":%llu,\"selector\":{\"start\":%llu,\"end\":%llu,",
    (unsigned long long)e->text_revision,(unsigned long long)e->text_size,(unsigned long long)e->selector.start,(unsigned long long)e->selector.end);
  annot_json_string(j,"exact",e->selector.exact);cv_text_string(j,",");
  annot_json_string(j,"prefix",e->selector.prefix);cv_text_string(j,",");
  annot_json_string(j,"suffix",e->selector.suffix);cv_text_string(j,",");
  annot_json_string(j,"chapter",e->selector.chapter);cv_text_string(j,"}}");
}
static void annot_serialize(cv_text *j) {
  cv_text_string(j,"{\"version\":1,\"book_sha256\":");cv_text_json(j,annot_hash);cv_text_string(j,",\"annotations\":[\n");
  for(int i=0;i<annot_count;i++) {
    shell_annotation *a=&annotations[i];if(i)cv_text_string(j,",\n");
    cv_text_format(j,"{\"color\":%d,\"created_ms\":%llu,\"updated_ms\":%llu,",a->color,(unsigned long long)a->created,(unsigned long long)a->updated);
    annot_json_string(j,"text",a->text);cv_text_string(j,",\"anchor\":{\"start\":");
    annot_endpoint_write(j,&a->anchor.start);cv_text_string(j,",\"end\":");annot_endpoint_write(j,&a->anchor.end);cv_text_string(j,"}}");
  }
  cv_text_string(j,"\n]}\n");
}
static int annot_save(void) {
  if(!annot_writable) {annot_error(L"标注存储不可用；原文件已保留。");return 0;}
  cv_text json={0};annot_serialize(&json);wchar_t temp[HOST_PATH];
  swprintf(temp,HOST_PATH,L"%ls.tmp",annot_path);
  HANDLE file=INVALID_HANDLE_VALUE;int ok=0;DWORD written=0;
  if(json.failed || json.size>32*1024*1024) goto done;
  file=CreateFileW(temp,GENERIC_WRITE,0,NULL,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);
  if(file==INVALID_HANDLE_VALUE) goto done;
  ok=WriteFile(file,json.data,(DWORD)json.size,&written,NULL) && written==json.size && FlushFileBuffers(file);
  if(!CloseHandle(file))ok=0;
  file=INVALID_HANDLE_VALUE;
  if(ok)ok=MoveFileExW(temp,annot_path,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH)!=0;
done:
  if(file!=INVALID_HANDLE_VALUE)CloseHandle(file);
  if(!ok) {DeleteFileW(temp);annot_error(L"标注保存失败；更改未保存，请重试。");}
  else sy_note(annot_hash);
  cv_text_free(&json);return ok;
}
static int annot_uint(const cv_json *o,const char *key,uint64_t *out) {
  const cv_json *v=cv_json_get(o,key);
  if(!v || v->type!=CV_JSON_NUMBER || !v->integral || v->integer<0) return 0;
  *out=(uint64_t)v->integer;return 1;
}
static int annot_string(const cv_json *o,const char *key,char **out,int nullable) {
  const cv_json *v=cv_json_get(o,key);
  if(!v)return 0;
  if(nullable && v->type==CV_JSON_NULL){*out=NULL;return 1;}
  if(v->type!=CV_JSON_STRING || strlen(v->string)>1024*1024)return 0;
  *out=host_strdup(v->string);return *out!=NULL;
}
static int annot_endpoint_read(const cv_json *o,exr_content_endpoint *e) {
  char *revision=NULL;uint64_t size,start,end;
  const cv_json *s=cv_json_get(o,"selector");
  if(!annot_string(o,"part_id",&e->part_id,0) || !annot_string(o,"part_path",&e->part_path,0) ||
     !annot_string(o,"text_revision",&revision,0))return 0;
  int valid=strlen(revision)==16;
  for(size_t i=0;valid && i<16;i++)valid=isxdigit((unsigned char)revision[i]);
  if(valid)e->text_revision=strtoull(revision,NULL,16);
  free(revision);
  if(!valid || !annot_uint(o,"text_size",&size) || size>SIZE_MAX ||
     !annot_uint(s,"start",&start) || !annot_uint(s,"end",&end) || start!=end || end>size)return 0;
  e->text_size=(size_t)size;e->selector.start=(size_t)start;e->selector.end=(size_t)end;
  return annot_string(s,"exact",&e->selector.exact,0) && !e->selector.exact[0] &&
    annot_string(s,"prefix",&e->selector.prefix,1) && annot_string(s,"suffix",&e->selector.suffix,1) &&
    annot_string(s,"chapter",&e->selector.chapter,1);
}
static int annot_parse(const char *bytes,size_t size) {
  /* SDK selectors are C strings: reject an embedded NUL, preserving literal
     backslash-u text and the original file on failure. */
  for(size_t i=0;i<size;i++) if(bytes[i]=='\\' && i+1<size) {
    if(bytes[i+1]=='u' && i+5<size && !memcmp(bytes+i+2,"0000",4))return 0;
    i++;
  }
  char *error=NULL;cv_json *root=cv_json_parse(bytes,size,&error);free(error);
  const cv_json *list=cv_json_get(root,"annotations"),*hash=cv_json_get(root,"book_sha256");uint64_t version;
  int ok=root && annot_uint(root,"version",&version) && version==1 && hash && hash->type==CV_JSON_STRING &&
    !strcmp(hash->string,annot_hash) && list && list->type==CV_JSON_ARRAY && list->count<=100000;
  shell_annotation *items=NULL;size_t count=ok ? list->count:0;
  if(ok && count) {items=calloc(count,sizeof(*items));if(!items)ok=0;}
  for(size_t i=0;ok && i<count;i++) {
    shell_annotation *a=&items[i];const cv_json *o=list->items[i],*anchor=cv_json_get(o,"anchor");uint64_t color=0;
    ok=annot_uint(o,"color",&color) && color<3 && annot_uint(o,"created_ms",&a->created) &&
      annot_uint(o,"updated_ms",&a->updated) && annot_string(o,"text",&a->text,0) &&
      annot_endpoint_read(cv_json_get(anchor,"start"),&a->anchor.start) &&
      annot_endpoint_read(cv_json_get(anchor,"end"),&a->anchor.end);
    a->color=(int)color;
  }
  cv_json_free(root);
  if(!ok) {if(items){for(size_t i=0;i<count;i++)annot_free(&items[i]);free(items);}return 0;}
  annotations=items;annot_count=(int)count;return 1;
}
static void annot_resolve(void) {
  exr_publication *publication=select_publication();if(!publication)return;
  for(int i=0;i<annot_count;i++) {
    exr_text_range_match match={0};shell_annotation *a=&annotations[i];
    a->found=exr_range_from_anchor(publication,&a->anchor,NULL,&match,NULL)==EXR_OK && match.state==EXR_ANCHOR_FOUND;
    if(a->found)a->range=match.range;
  }
}
static void annot_sync(void) {
  if(!g.frame.valid || g.frame.fixed || !g.session.active || g.job || g.pending)return;
  if(annot_book==g.frame.book_id)return;
  annot_clear();annot_book=g.frame.book_id;annot_hash[0]=0;
  if(!annot_identity(annot_hash)) {annot_error(L"无法读取书籍内容身份，标注不可用。");return;}
  wchar_t directory[HOST_PATH],name[80];
  DWORD n=GetEnvironmentVariableW(L"EXREADER_ANNOTATIONS_DIR",directory,HOST_PATH);
  if(!n) {
    n=GetEnvironmentVariableW(L"APPDATA",directory,HOST_PATH);
    if(!n || n>=HOST_PATH)return;
    wchar_t base[HOST_PATH];path_join(base,HOST_PATH,directory,L"EXReader");path_join(directory,HOST_PATH,base,L"annotations");
  } else if(n>=HOST_PATH)return;
  if(wcslen(directory)+80>=HOST_PATH){annot_error(L"标注目录路径过长。");return;}
  if(!ensure_directory(directory)) {annot_error(L"无法创建标注目录。");return;}
  swprintf(name,80,L"%hs.json",annot_hash);path_join(annot_path,HOST_PATH,directory,name);
  HANDLE file=CreateFileW(annot_path,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,NULL);
  if(file==INVALID_HANDLE_VALUE) {
    annot_writable=GetLastError()==ERROR_FILE_NOT_FOUND;
    if(!annot_writable)annot_error(L"无法打开标注文件；原文件已保留。");
    return;
  }
  LARGE_INTEGER size;DWORD got=0;char *bytes=NULL;
  if(GetFileSizeEx(file,&size) && size.QuadPart>0 && size.QuadPart<=32*1024*1024) {
    bytes=malloc((size_t)size.QuadPart+1);
    if(bytes && ReadFile(file,bytes,(DWORD)size.QuadPart,&got,NULL) && got==size.QuadPart) {
      bytes[got]=0;annot_writable=annot_parse(bytes,got);
    }
  }
  free(bytes);CloseHandle(file);
  if(!annot_writable)annot_error(L"标注JSON格式错误或版本不支持；原文件已保留，暂停写入。");
  annot_resolve();page_dirty(g.page,0);
}
static uint32_t annot_rgb(int color) {if(shell_contrast)return shell_colors->accent;return shell_is_dark() ? SHELL_ANNOT_DARK_RGB[color]:SHELL_ANNOT_RGB[color];}
static HRGN annot_region(const shell_annotation *a) {
  if(!a->found || g.frame.part<a->range.start.part || g.frame.part>a->range.end.part)return CreateRectRgn(0,0,0,0);
  return select_region_for(g.frame.part==a->range.start.part ? a->range.start.offset:0,
    g.frame.part==a->range.end.part ? a->range.end.offset:SIZE_MAX);
}
static void annot_pixels(uint32_t *pixels,int width,int height) {
  if(annot_book!=g.frame.book_id)return;
  for(int i=0;i<annot_count;i++) {
    HRGN region=annot_region(&annotations[i]);RECT bounds;GetRgnBox(region,&bounds);
    uint32_t rgb=annot_rgb(annotations[i].color);float alpha=shell_is_dark() ? SHELL_ANNOT_DARK_ALPHA:SHELL_ANNOT_ALPHA;
    for(int y=max(0,bounds.top);y<min(height,bounds.bottom);y++) for(int x=max(0,bounds.left);x<min(width,bounds.right);x++) if(PtInRegion(region,x,y)) {
      size_t at=(size_t)y*width+x;uint32_t q=g.frame.dib[at];unsigned r=(q>>16)&255,b=q&255,green=(q>>8)&255;
      if(!g.frame.display_shell_paper && r==b && b==green)
        pixels[at]=shell_blend(shell_colors->text,shell_blend(shell_colors->layer_page,rgb,alpha),r/255.f);
      else pixels[at]=shell_blend(q,rgb,(float)max(r,max(b,green))/255.f*alpha);
    }
    DeleteObject(region);
  }
}
static int annot_marker(const shell_annotation *a,POINT *point) {
  if(!a->found || !a->text[0] || a->range.end.part!=g.frame.part)return 0;
  for(size_t i=0;i<g.frame.shell_line_count;i++) {
    const exr_line *line=&g.frame.shell_lines[i];
    for(size_t j=line->glyph_start;j<line->glyph_start+line->glyph_count;j++) {
      const exr_glyph *glyph=&g.frame.glyphs[j];
      if(glyph->flags&EXR_GLYPH_HIDDEN || glyph->cluster_start>=a->range.end.offset || glyph->cluster_end<a->range.end.offset)continue;
      float x=line->x+line->width+6,y=line->y+line->height*.5f;
      if(glyph->flags&EXR_GLYPH_VERTICAL) {x=line->x+line->width*.5f;y=line->y+line->height+6;}
      point->x=g.view.dx+(int)lroundf(min(x,g.frame.bitmap.width-4)*g.view.scale);
      point->y=g.view.dy+(int)lroundf(min(y,g.frame.bitmap.height-4)*g.view.scale);return 1;
    }
  }
  return 0;
}
static void annot_marks(HDC dc) {
  if(annot_book!=g.frame.book_id)return;
  for(int i=0;i<annot_count;i++) {
    if(i==annot_selected) {
      HRGN region=annot_region(&annotations[i]);OffsetRgn(region,g.view.dx,g.view.dy);
      HBRUSH brush=CreateSolidBrush(shell_colorref(annot_rgb(annotations[i].color)));FrameRgn(dc,region,brush,1,1);DeleteObject(brush);DeleteObject(region);
    }
    POINT p;if(!annot_marker(&annotations[i],&p))continue;
    int radius=shell_px(3,shell_dpi);HBRUSH brush=CreateSolidBrush(shell_colorref(annot_rgb(annotations[i].color)));
    HGDIOBJ old=SelectObject(dc,brush),pen=SelectObject(dc,GetStockObject(NULL_PEN));
    Ellipse(dc,p.x-radius,p.y-radius,p.x+radius,p.y+radius);SelectObject(dc,old);SelectObject(dc,pen);DeleteObject(brush);
  }
}
static int annot_commit(const char *text,int color) {
  annot_sync();if(!annot_writable || color<0 || color>2)return 0;
  if(annot_selected>=0 && annot_selected<annot_count) {
    shell_annotation *a=&annotations[annot_selected];char *copy=host_strdup(text);if(!copy)return 0;
    char *old=a->text;uint64_t time=a->updated;int oldcolor=a->color;
    a->text=copy;a->updated=annot_time();a->color=color;
    if(!annot_save()){a->text=old;a->updated=time;a->color=oldcolor;free(copy);return 0;}free(old);
  } else {
    if(!select_valid || !select_before(select_range.start,select_range.end))return 0;
    shell_annotation a={0};a.text=host_strdup(text);a.color=color;a.created=a.updated=annot_time();
    if(!a.text || exr_anchor_from_range(select_publication(),&select_range,NULL,&a.anchor,NULL)!=EXR_OK){annot_free(&a);return 0;}
    shell_annotation *next=realloc(annotations,((size_t)annot_count+1)*sizeof(*next));
    if(!next){annot_free(&a);return 0;}annotations=next;annotations[annot_count++]=a;
    if(!annot_save()){annot_free(&annotations[--annot_count]);return 0;}
    annot_selected=annot_count-1;
  }
  annot_resolve();selection_clear();page_dirty(g.page,0);return 1;
}
static int annot_delete(void) {
  if(annot_selected<0 || annot_selected>=annot_count)return 0;
  int at=annot_selected;shell_annotation saved=annotations[at];
  memmove(annotations+at,annotations+at+1,(size_t)(annot_count-at-1)*sizeof(*annotations));annot_count--;
  if(!annot_save()) {
    memmove(annotations+at+1,annotations+at,(size_t)(annot_count-at)*sizeof(*annotations));annotations[at]=saved;annot_count++;return 0;
  }
  annot_free(&saved);annot_selected=-1;annot_close();selection_clear();page_dirty(g.page,0);return 1;
}
static LRESULT CALLBACK annot_procedure(HWND window,UINT message,WPARAM wp,LPARAM lp) {
  switch(message) {
    case WM_ERASEBKGND:return 1;
    case WM_CTLCOLORSTATIC:case WM_CTLCOLOREDIT: {
      SetTextColor((HDC)wp,shell_colorref(shell_colors->text));SetBkColor((HDC)wp,shell_colorref(shell_colors->layer_float));
      if(annot_brush)DeleteObject(annot_brush);
      annot_brush=CreateSolidBrush(shell_colorref(shell_colors->layer_float));return (LRESULT)annot_brush;
    }
    case WM_COMMAND:
      if(LOWORD(wp)==1) {
        wchar_t text[8193];GetWindowTextW(annot_edit,text,8193);char *utf8=host_utf8(text);
        int color=0;for(int i=0;i<3;i++)if(SendDlgItemMessageW(window,10+i,BM_GETCHECK,0,0)==BST_CHECKED)color=i;
        annot_selected=annot_editing;
        if(utf8 && annot_commit(utf8,color))annot_close();
        free(utf8);return 0;
      }
      if(LOWORD(wp)==2){annot_close();return 0;}
      if(LOWORD(wp)==3){annot_selected=annot_editing;annot_delete();return 0;}
      break;
    case WM_DRAWITEM: {
      const DRAWITEMSTRUCT *item=(const DRAWITEMSTRUCT *)lp;
      shell_draw_control(item,item->CtlID==1 ? L"保存":item->CtlID==2 ? L"取消":L"删除",
        item->CtlID==1 ? SHELL_CONTROL_PRIMARY:SHELL_CONTROL_STANDARD,shell_colors->layer_float);return TRUE;
    }
    case WM_PAINT:case WM_PRINTCLIENT: {
      PAINTSTRUCT paint;RECT box;GetClientRect(window,&box);HDC dc=message==WM_PAINT ? BeginPaint(window,&paint):(HDC)wp;
      shell_card_paint(window,dc,&box,L"笔记");
      if(message==WM_PAINT)EndPaint(window,&paint);
      return 0;
    }
  }
  return DefWindowProcW(window,message,wp,lp);
}
static void annot_open(void) {
  if(!select_valid && annot_selected<0)return;
  if(!annot_writable){annot_error(L"标注存储不可用；原文件已保留。");return;}
  annot_editing=annot_selected;
  if(!annot_panel) {
    WNDCLASSW type={0};type.lpfnWndProc=annot_procedure;type.hInstance=GetModuleHandleW(NULL);type.hCursor=LoadCursor(NULL,IDC_ARROW);type.lpszClassName=L"EXReaderAnnotation";RegisterClassW(&type);
    annot_panel=CreateWindowExW(WS_EX_CONTROLPARENT,type.lpszClassName,L"笔记",WS_CHILD|WS_CLIPSIBLINGS,0,0,0,0,g.window,NULL,type.hInstance,NULL);
    annot_edit=CreateWindowExW(0,L"EDIT",L"",WS_CHILD|WS_VISIBLE|WS_TABSTOP|ES_MULTILINE|ES_AUTOVSCROLL|ES_WANTRETURN|WS_VSCROLL,0,0,0,0,annot_panel,(HMENU)20,NULL,NULL);
    SendMessageW(annot_edit,EM_SETLIMITTEXT,8192,0);
    const wchar_t *labels[6]={L"保存",L"取消",L"删除",L"黄色",L"绿色",L"蓝色"};
    int ids[6]={1,2,3,10,11,12};
    for(int i=0;i<6;i++)CreateWindowExW(0,L"BUTTON",labels[i],WS_CHILD|WS_VISIBLE|WS_TABSTOP|(i<3 ? BS_OWNERDRAW:BS_AUTORADIOBUTTON)|(i==3 ? WS_GROUP:0),0,0,0,0,annot_panel,(HMENU)(INT_PTR)ids[i],NULL,NULL);
  }
  RECT client;GetClientRect(g.window,&client);int pad=shell_px(SHELL_SHADOW_PAD,shell_dpi),top=shell_px(SHELL_SHADOW_TOP,shell_dpi);
  int w=shell_px(320,shell_dpi)+2*pad,h=shell_px(236,shell_dpi)+top+pad;
  SetWindowPos(annot_panel,HWND_TOP,max(-pad,(client.right-w)/2),max(0,(client.bottom-h)/2),w,h,SWP_NOACTIVATE);
  int x=pad+shell_px(16,shell_dpi),y=top+shell_px(44,shell_dpi);
  MoveWindow(annot_edit,x,y,shell_px(288,shell_dpi),shell_px(100,shell_dpi),TRUE);
  for(int i=0;i<3;i++) {
    MoveWindow(GetDlgItem(annot_panel,10+i),x+shell_px(96*i,shell_dpi),top+shell_px(154,shell_dpi),shell_px(90,shell_dpi),shell_px(26,shell_dpi),TRUE);
    MoveWindow(GetDlgItem(annot_panel,i+1),x+shell_px(96*i,shell_dpi),top+shell_px(190,shell_dpi),shell_px(88,shell_dpi),shell_px(34,shell_dpi),TRUE);
  }
  EnableWindow(GetDlgItem(annot_panel,3),annot_editing>=0);
  int color=annot_editing>=0 ? annotations[annot_editing].color:0;
  CheckRadioButton(annot_panel,10,12,10+color);
  wchar_t *text=host_wide(annot_editing>=0 ? annotations[annot_editing].text:"",annot_editing>=0 ? strlen(annotations[annot_editing].text):0);
  SetWindowTextW(annot_edit,text ? text:L"");free(text);
  HFONT font=(HFONT)GetStockObject(DEFAULT_GUI_FONT);
  for(HWND child=GetWindow(annot_panel,GW_CHILD);child;child=GetWindow(child,GW_HWNDNEXT))SendMessageW(child,WM_SETFONT,(WPARAM)font,TRUE);
  ShowWindow(annot_panel,SW_SHOWNOACTIVATE);SetFocus(annot_edit);InvalidateRect(annot_panel,NULL,TRUE);
}
static int annot_command(int command) {
  if(command>=3 && command<=5) {
    const char *text=annot_selected>=0 ? annotations[annot_selected].text:"";
    return annot_commit(text,command-3);
  }
  if(command==6){annot_open();return 1;}
  if(command==7)return annot_delete();
  return 0;
}
static int annot_click(int x,int y) {
  if(annot_book!=g.frame.book_id)return 0;
  for(int i=annot_count-1;i>=0;i--) {
    POINT p;int marker=annot_marker(&annotations[i],&p) && abs(x-p.x)<=shell_px(8,shell_dpi) && abs(y-p.y)<=shell_px(8,shell_dpi);
    HRGN region=annot_region(&annotations[i]);int hit=PtInRegion(region,x-g.view.dx,y-g.view.dy);DeleteObject(region);
    if(marker || hit) {
      selection_clear();annot_selected=i;page_dirty(g.page,0);
      if(marker)annot_open();
      return 1;
    }
  }
  annot_selected=-1;return 0;
}
static int annot_translate(const MSG *message) {
  if(!annot_panel || !IsWindowVisible(annot_panel))return 0;
  if(message->message==WM_KEYDOWN && message->wParam==VK_ESCAPE){annot_close();return 1;}
  if(message->message==WM_KEYDOWN && message->wParam==VK_RETURN && (GetKeyState(VK_CONTROL)&0x8000)) {
    SendMessageW(annot_panel,WM_COMMAND,1,0);return 1;
  }
  if(message->message==WM_LBUTTONDOWN && message->hwnd==g.page){annot_close();return 1;}
  return IsDialogMessageW(annot_panel,(MSG *)message);
}
