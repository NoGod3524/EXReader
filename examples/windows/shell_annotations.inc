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
static shell_annotation *annotations;
static int annot_editing=-1,annot_writable;
static int64_t annot_book;
static char annot_hash[65];
static wchar_t annot_path[HOST_PATH];
static HWND annot_panel,annot_edit;
static HBRUSH annot_brush;
static shell_save_state annot_storage;
static HANDLE annot_lock;
static cv_text annot_before_edit;
static int annot_applying,annot_draft_changed;
static int annot_test_answer,annot_prompt_count;
static const wchar_t *annot_last_prompt=L"";
static wchar_t annot_last_error[256];
static void annot_title(void) {
  if(!g.window)return;
  wchar_t title[512];wchar_t *name=host_wide(g.has_current && g.current.title ? g.current.title:"",g.has_current && g.current.title ? strlen(g.current.title):0);
  swprintf(title,512,L"%lsEXReader%ls%.400ls",annot_storage.dirty ? L"* ":L"",name && name[0] ? L" - ":L"",name ? name:L"");
  SetWindowTextW(g.window,title);free(name);
}
static void annot_dirty(void) {
  int was_dirty=annot_storage.dirty;annot_storage.dirty=1;annot_storage.revision++;
  if(!was_dirty && g.window)SetTimer(g.window,SHELL_SAVE_TIMER,shell_autosave_seconds*1000,NULL);
  annot_title();
}
static int annot_question(const wchar_t *text,UINT flags) {
  annot_last_prompt=text;annot_prompt_count++;
  if(g.drive_mode && annot_test_answer) {int answer=annot_test_answer;annot_test_answer=0;return answer;}
  if(host_offscreen)return IDCANCEL;
  return MessageBoxW(g.window,text,L"EXReader",flags|MB_ICONQUESTION);
}
static void annot_close(void) {
  if(annot_panel) ShowWindow(annot_panel,SW_HIDE);
  cv_text_free(&annot_before_edit);annot_draft_changed=0;SetFocus(g.page);
}
static void annot_free(shell_annotation *a) {exr_content_anchor_free(&a->anchor);free(a->text);memset(a,0,sizeof(*a));}
static void annot_clear(void) {
  if(annot_panel) ShowWindow(annot_panel,SW_HIDE);
  for(int i=0;i<annot_count;i++) annot_free(&annotations[i]);
  free(annotations);annotations=NULL;annot_count=0;annot_selected=-1;annot_writable=0;
  cv_text_free(&annot_before_edit);annot_draft_changed=0;
  memset(&annot_storage,0,sizeof(annot_storage));
  if(g.window)KillTimer(g.window,SHELL_SAVE_TIMER);
  if(annot_lock && annot_lock!=INVALID_HANDLE_VALUE)CloseHandle(annot_lock);
  annot_lock=NULL;annot_title();
}
static uint64_t annot_time(void) {
  FILETIME ft;ULARGE_INTEGER value;GetSystemTimeAsFileTime(&ft);value.LowPart=ft.dwLowDateTime;value.HighPart=ft.dwHighDateTime;
  return (value.QuadPart-116444736000000000ULL)/10000;
}
static void annot_error(const wchar_t *text) {
  copy_wstring(annot_last_error,256,text);
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
static int annot_decode(const char *bytes,size_t size,shell_annotation **out,int *out_count) {
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
  *out=items;*out_count=(int)count;return 1;
}
static int annot_validate(const char *bytes,size_t size,void *context) {
  shell_annotation *items=NULL;int count=0;(void)context;
  int ok=annot_decode(bytes,size,&items,&count);
  for(int i=0;i<count;i++)annot_free(&items[i]);
  free(items);return ok;
}
static int annot_parse(const char *bytes,size_t size) {
  shell_annotation *items=NULL;int count=0;
  if(!annot_decode(bytes,size,&items,&count))return 0;
  for(int i=0;i<annot_count;i++)annot_free(&annotations[i]);
  free(annotations);annotations=items;annot_count=count;annot_selected=-1;return 1;
}
static int annot_save(void) {
  if(!annot_writable) {annot_error(L"标注存储不可用；原文件已保留。");return 0;}
  cv_text json={0};annot_serialize(&json);
  int result=json.failed ? 0:shell_save_replace(annot_path,json.data,json.size,annot_validate,NULL,NULL);
  cv_text_free(&json);
  if(result!=1) {
    annot_error(result<0 ? L"保存校验失败且回滚失败；保存前的完整版本保留在 .bak，请勿覆盖。":L"标注保存失败；原文件已保留，更改仍未保存，请重试。");return 0;
  }
  /* Remove before clearing dirty: a failed cleanup must not resurrect discarded work. */
  if(!shell_save_discard(annot_path)) {annot_error(L"文件已保存，但无法删除恢复副本；请重试保存。");return 0;}
  memset(&annot_storage,0,sizeof(annot_storage));
  if(g.window)KillTimer(g.window,SHELL_SAVE_TIMER);
  annot_title();set_status(L"已保存并校验。");return 1;
}
static void annot_autosave(void) {
  if(!annot_writable || !annot_storage.dirty || annot_storage.autosaved==annot_storage.revision)return;
  cv_text json={0};annot_serialize(&json);
  int result=json.failed ? 0:shell_save_autosave(annot_path,json.data,json.size,annot_validate,NULL);
  cv_text_free(&json);
  if(result==1) {annot_storage.autosaved=annot_storage.revision;set_status(L"已自动保存恢复副本。");}
  else set_status(L"自动保存失败；更改仍在内存中，请重试或显式保存。");
}
static int annot_before_leave(void) {
  if(!annot_storage.dirty)return 1;
  int answer=annot_question(L"有未保存的修改，是否保存？\n是：保存；否：放弃；取消：继续编辑。",MB_YESNOCANCEL|MB_DEFBUTTON3);
  if(answer==IDYES)return annot_save();
  if(answer!=IDNO)return 0;
  if(!shell_save_discard(annot_path)) {annot_error(L"无法删除恢复副本；仍保留当前修改，请重试。");return 0;}
  char *bytes=NULL;size_t size=0;int found=shell_save_read(annot_path,&bytes,&size);
  if(found<0 || (found==1 && !annot_parse(bytes,size))) {free(bytes);annot_error(L"无法重新载入保存前的文件；仍保留当前修改。");return 0;}
  free(bytes);
  if(!found) {for(int i=0;i<annot_count;i++)annot_free(&annotations[i]);free(annotations);annotations=NULL;annot_count=0;}
  memset(&annot_storage,0,sizeof(annot_storage));if(g.window)KillTimer(g.window,SHELL_SAVE_TIMER);
  annot_close();annot_title();return 1;
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
  wchar_t lockpath[HOST_PATH];
  if(!shell_save_suffix(lockpath,HOST_PATH,annot_path,L".lock"))return;
  annot_lock=CreateFileW(lockpath,GENERIC_READ|GENERIC_WRITE,0,NULL,OPEN_ALWAYS,FILE_ATTRIBUTE_HIDDEN|FILE_FLAG_DELETE_ON_CLOSE,NULL);
  if(annot_lock==INVALID_HANDLE_VALUE) {annot_error(L"此文档的笔记已在另一个窗口打开，或无法取得写入权限。");return;}
  char *bytes=NULL;size_t size=0;int found=shell_save_read(annot_path,&bytes,&size);
  annot_writable=found==0 || (found==1 && annot_parse(bytes,size));free(bytes);bytes=NULL;
  int recovery=shell_save_recovery(annot_path,&bytes,&size,annot_validate,NULL);
  if(recovery<0)annot_error(L"副本损坏，无法恢复");
  if(recovery==1) {
    int answer=annot_question(L"有未保存的修改，是否恢复？",MB_YESNO|MB_DEFBUTTON1);
    if(answer==IDYES && annot_parse(bytes,size)) {
      annot_writable=1;annot_dirty();annot_storage.autosaved=annot_storage.revision;
    }
    else if(answer==IDNO) {
      if(!shell_save_discard(annot_path)) {annot_writable=0;annot_error(L"无法删除恢复副本，请重试。");}
    } else {annot_writable=0;set_status(L"恢复尚未确认；恢复副本已保留。");}
  }
  free(bytes);
  if(!annot_writable && recovery!=1)annot_error(L"标注JSON格式错误或版本不支持；原文件已保留，暂停写入。");
  annot_title();annot_resolve();page_dirty(g.page,0);
}
static uint32_t annot_rgb(int color) {return shell_is_dark() ? SHELL_ANNOT_DARK_RGB[color]:SHELL_ANNOT_RGB[color];}
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
    char *old=a->text;
    a->text=copy;a->updated=annot_time();a->color=color;
    free(old);
  } else {
    if(!select_valid || !select_before(select_range.start,select_range.end))return 0;
    shell_annotation a={0};a.text=host_strdup(text);a.color=color;a.created=a.updated=annot_time();
    if(!a.text || exr_anchor_from_range(select_publication(),&select_range,NULL,&a.anchor,NULL)!=EXR_OK){annot_free(&a);return 0;}
    shell_annotation *next=realloc(annotations,((size_t)annot_count+1)*sizeof(*next));
    if(!next){annot_free(&a);return 0;}annotations=next;annotations[annot_count++]=a;
    annot_selected=annot_count-1;
  }
  annot_dirty();annot_resolve();selection_clear();page_dirty(g.page,0);return 1;
}
static int annot_delete(void) {
  if(!annot_writable || annot_selected<0 || annot_selected>=annot_count)return 0;
  int at=annot_selected;shell_annotation saved=annotations[at];
  memmove(annotations+at,annotations+at+1,(size_t)(annot_count-at-1)*sizeof(*annotations));annot_count--;
  annot_dirty();annot_free(&saved);annot_selected=-1;annot_close();selection_clear();page_dirty(g.page,0);return 1;
}
static int annot_editor_changed(void) {
  if(annot_applying || !annot_panel || !IsWindowVisible(annot_panel))return 1;
  wchar_t text[8193];GetWindowTextW(annot_edit,text,8193);char *utf8=host_utf8(text);
  int color=0;for(int i=0;i<3;i++)if(SendDlgItemMessageW(annot_panel,10+i,BM_GETCHECK,0,0)==BST_CHECKED)color=i;
  if(utf8 && annot_editing>=0 && annot_editing<annot_count && !strcmp(utf8,annotations[annot_editing].text) && color==annotations[annot_editing].color) {free(utf8);return 1;}
  annot_selected=annot_editing;int ok=utf8 && annot_commit(utf8,color);free(utf8);
  if(ok) {annot_editing=annot_selected;annot_draft_changed=1;}
  else annot_error(L"无法记录笔记草稿，请重试。");
  return ok;
}
static void annot_cancel_edit(void) {
  if(annot_draft_changed && annot_before_edit.data) {
    if(!annot_parse(annot_before_edit.data,annot_before_edit.size)) {annot_error(L"无法撤销草稿；当前文字已保留。");return;}
    annot_dirty();annot_resolve();page_dirty(g.page,0);
  }
  annot_close();
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
      if(!annot_applying && ((LOWORD(wp)==20 && HIWORD(wp)==EN_CHANGE) ||
         (LOWORD(wp)>=10 && LOWORD(wp)<=12 && HIWORD(wp)==BN_CLICKED))) {annot_editor_changed();return 0;}
      if(LOWORD(wp)==1) {
        if(annot_editor_changed() && annot_save())annot_close();return 0;
      }
      if(LOWORD(wp)==2){annot_cancel_edit();return 0;}
      if(LOWORD(wp)==3){annot_selected=annot_editing;annot_delete();return 0;}
      break;
    case WM_DRAWITEM: {
      const DRAWITEMSTRUCT *item=(const DRAWITEMSTRUCT *)lp;
      shell_d2d_control(host_shell,item->hDC,&item->rcItem,item->CtlID==1 ? L"保存":item->CtlID==2 ? L"取消":L"删除",
        shell_is_dark(),item->CtlID==1 ? 1:2,(item->itemState&ODS_SELECTED ? 2:0)|(item->itemState&ODS_FOCUS ? 4:0));return TRUE;
    }
    case WM_PAINT:case WM_PRINTCLIENT: {
      PAINTSTRUCT paint;RECT box;GetClientRect(window,&box);HDC dc=message==WM_PAINT ? BeginPaint(window,&paint):(HDC)wp;
      BITMAPINFO info={0};void *bits=NULL;
      info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);info.bmiHeader.biWidth=box.right;
      info.bmiHeader.biHeight=-box.bottom;info.bmiHeader.biPlanes=1;info.bmiHeader.biBitCount=32;
      HDC underlay=CreateCompatibleDC(dc);HBITMAP bitmap=CreateDIBSection(dc,&info,DIB_RGB_COLORS,&bits,NULL,0);
      if(underlay && bitmap) {
        HGDIOBJ old=SelectObject(underlay,bitmap);RECT place;GetWindowRect(window,&place);MapWindowPoints(NULL,g.page,(POINT *)&place,2);
        HBRUSH bg=CreateSolidBrush(shell_colorref(shell_colors->layer_page));FillRect(underlay,&box,bg);DeleteObject(bg);
        if(page_buffer_dc)BitBlt(underlay,0,0,box.right,box.bottom,page_buffer_dc,place.left,place.top,SRCCOPY);
        GdiFlush();shell_d2d_note(host_shell,dc,&box,shell_is_dark(),bits);SelectObject(underlay,old);
      } else shell_d2d_note(host_shell,dc,&box,shell_is_dark(),NULL);
      if(bitmap)DeleteObject(bitmap);
      if(underlay)DeleteDC(underlay);
      if(message==WM_PAINT)EndPaint(window,&paint);
      return 0;
    }
  }
  return DefWindowProcW(window,message,wp,lp);
}
static void annot_open(void) {
  if(!select_valid && annot_selected<0)return;
  if(!annot_writable){annot_error(L"标注存储不可用；原文件已保留。");return;}
  annot_close();annot_serialize(&annot_before_edit);annot_draft_changed=0;
  if(annot_before_edit.failed) {annot_error(L"内存不足，无法打开笔记编辑器。");return;}
  annot_editing=annot_selected;
  annot_applying=1;
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
  annot_applying=0;ShowWindow(annot_panel,SW_SHOWNOACTIVATE);SetFocus(annot_edit);InvalidateRect(annot_panel,NULL,TRUE);
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
  if(message->message==WM_KEYDOWN && message->wParam=='S' && (GetKeyState(VK_CONTROL)&0x8000) && !(GetKeyState(VK_SHIFT)&0x8000)) {
    if(annot_editor_changed() && annot_save())annot_close();return 1;
  }
  if(!annot_panel || !IsWindowVisible(annot_panel))return 0;
  if(message->message==WM_KEYDOWN && message->wParam==VK_ESCAPE){annot_cancel_edit();return 1;}
  if(message->message==WM_KEYDOWN && message->wParam==VK_RETURN && (GetKeyState(VK_CONTROL)&0x8000)) {
    SendMessageW(annot_panel,WM_COMMAND,1,0);return 1;
  }
  if(message->message==WM_LBUTTONDOWN && message->hwnd==g.page){annot_close();return 1;}
  return IsDialogMessageW(annot_panel,(MSG *)message);
}
