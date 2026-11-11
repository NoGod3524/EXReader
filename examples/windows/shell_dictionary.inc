/* SPDX-License-Identifier: MIT */
/* UI-owned dictionary configuration and vocabulary; no dictionary bytes copied. */
#include <exr/dictionary.h>
#include <shlobj.h>
enum { DICT_ADD=810,DICT_REMOVE,DICT_AUTO,DICT_VOCAB,DICT_SAVE,DICT_CLOSE,DICT_EXPORT,
       DICT_FILTER,DICT_LIST,DICT_PATHS,DICT_QUERY,DICT_STATUS,DICT_GROUP=900 };
enum { SY_ID_URL=840,SY_ID_USER,SY_ID_PASS,SY_ID_SAVE,SY_ID_NOW,SY_ID_CLEAR,SY_ID_CLOSE,SY_ID_AUTO,SY_ID_STATUS,SY_ID_L1,SY_ID_L2,SY_ID_L3 };
static HWND sy_panel;static int sy_command(HWND window,int id,int notify);
static exr_dictionary *dicts[64];
static size_t dict_count,dict_dir_count,dict_result_count;
static wchar_t *dict_dirs[64];
static int dict_ready,dict_writable,dict_auto,dict_scroll,dict_content_height;
static cv_json *dict_shelf;
static wchar_t dict_path[HOST_PATH],vocab_path[HOST_PATH];
static char *dict_word,*dict_problem;
static exr_dictionary_result *dict_results;
static exr_content_anchor dict_anchor;
static int64_t dict_book;
static char *dict_book_title;
static HWND dict_popup,dict_view,dict_manager,vocab_panel;
static HWND dict_headers[64],dict_bodies[64];
static int dict_collapsed[64];
static HBRUSH dict_brush;
static HFONT dict_font;
typedef struct {
  char *word,*summary,*book,*sentence;
  int64_t book_id;
  uint64_t time;
  exr_content_anchor anchor;
} shell_vocab;
static shell_vocab *vocab;
static size_t vocab_count;
static int vocab_ready,vocab_writable;
static void dict_manager_open(void);
static void vocab_open(void);
static void dict_groups_layout(void);
static void vocab_list_refresh(void);

static void dict_error(const wchar_t *text) {
  set_status(text);
  if(!host_offscreen)MessageBoxW(g.window,text,L"词典与生词本",MB_OK|MB_ICONERROR);
}
static int dict_atomic(const wchar_t *path,const cv_text *text) {
  wchar_t temp[HOST_PATH];DWORD written=0;
  if(text->failed || text->size>32*1024*1024 || wcslen(path)+5>=HOST_PATH)return 0;
  swprintf(temp,HOST_PATH,L"%ls.tmp",path);
  HANDLE file=CreateFileW(temp,GENERIC_WRITE,0,NULL,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);
  if(file==INVALID_HANDLE_VALUE)return 0;
  int ok=WriteFile(file,text->data,(DWORD)text->size,&written,NULL) && written==text->size && FlushFileBuffers(file);
  if(!CloseHandle(file))ok=0;
  if(ok)ok=MoveFileExW(temp,path,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH)!=0;
  if(!ok)DeleteFileW(temp);
  return ok;
}
static cv_json *dict_json_load(const wchar_t *path,const char *empty) {
  FILE *file=_wfopen(path,L"rb");char *data=NULL,*error=NULL;size_t size=0;
  if(!file) {
    if(GetFileAttributesW(path)!=INVALID_FILE_ATTRIBUTES || GetLastError()!=ERROR_FILE_NOT_FOUND)return NULL;
    return cv_json_parse(empty,strlen(empty),NULL);
  }
  if(!fseek(file,0,SEEK_END)) {
    long n=ftell(file);
    if(n>=0 && n<=32*1024*1024 && !fseek(file,0,SEEK_SET)) {
      data=malloc((size_t)n+1);if(data && fread(data,1,(size_t)n,file)==(size_t)n){size=(size_t)n;data[size]=0;}
    }
  }
  fclose(file);
  /* C-string consumers must not silently truncate persisted values. */
  for(size_t i=0;i<size;i++)if(data[i]=='\\' && i+1<size) {
    if(data[i+1]=='u' && i+5<size && !memcmp(data+i+2,"0000",4)){free(data);return NULL;}i++;
  }
  cv_json *root=data ? cv_json_parse(data,size,&error):NULL;free(data);free(error);return root;
}
static void dict_json_write(cv_text *text,const cv_json *v) {
  if(!v){cv_text_string(text,"null");return;}
  switch(v->type) {
    case CV_JSON_NULL:cv_text_string(text,"null");break;
    case CV_JSON_BOOL:cv_text_string(text,v->boolean ? "true":"false");break;
    case CV_JSON_NUMBER:
      if(v->integral)cv_text_format(text,"%lld",v->integer);else cv_text_format(text,"%.17g",v->number);break;
    case CV_JSON_STRING:cv_text_json(text,v->string);break;
    case CV_JSON_OBJECT:case CV_JSON_ARRAY:
      cv_text_string(text,v->type==CV_JSON_OBJECT ? "{":"[");
      for(size_t i=0;i<v->count;i++) {
        if(i)cv_text_string(text,",");
        if(v->type==CV_JSON_OBJECT){cv_text_json(text,v->keys[i]);cv_text_string(text,":");}
        dict_json_write(text,v->items[i]);
      }
      cv_text_string(text,v->type==CV_JSON_OBJECT ? "}":"]");break;
  }
}
static int dict_config_save(void) {
  if(!dict_writable){dict_error(L"shelf.json 无法读取，未写入更改。");return 0;}
  cv_json *current=dict_json_load(dict_path,"{}");
  if(!current || current->type!=CV_JSON_OBJECT) {
    cv_json_free(current);dict_error(L"shelf.json 无法读取，未写入更改。");return 0;
  }
  cv_json_free(dict_shelf);dict_shelf=current;
  cv_text j={0};cv_text_string(&j,"{");
  for(size_t i=0;i<dict_shelf->count;i++) {
    if(!strcmp(dict_shelf->keys[i],"dictionary_directories") || !strcmp(dict_shelf->keys[i],"dictionary_auto_lookup"))continue;
    cv_text_json(&j,dict_shelf->keys[i]);cv_text_string(&j,":");dict_json_write(&j,dict_shelf->items[i]);cv_text_string(&j,",");
  }
  cv_text_format(&j,"\"dictionary_auto_lookup\":%s,\"dictionary_directories\":[",dict_auto ? "true":"false");
  for(size_t i=0;i<dict_dir_count;i++) {
    char *path=host_utf8(dict_dirs[i]);if(!path){j.failed=1;break;}
    if(i)cv_text_string(&j,",");
    cv_text_json(&j,path);free(path);
  }
  cv_text_string(&j,"]}\n");int ok=dict_atomic(dict_path,&j);cv_text_free(&j);
  if(!ok)dict_error(L"词典设置保存失败，更改未保存。");
  return ok;
}
static void dict_problem_add(const wchar_t *path,const char *reason) {
  char *utf8=host_utf8(path);cv_text text={0};
  if(dict_problem)cv_text_string(&text,dict_problem);
  cv_text_format(&text,"%s: %s\n",utf8 ? utf8:"",reason);free(utf8);free(dict_problem);dict_problem=text.data;
}
static int dict_compare_path(const void *a,const void *b) {return wcscmp(*(wchar_t *const *)a,*(wchar_t *const *)b);}
static void dict_scan(const wchar_t *directory,unsigned depth) {
  if(depth>8 || wcslen(directory)+4>=HOST_PATH){dict_problem_add(directory,"目录层级或路径过长");return;}
  wchar_t pattern[HOST_PATH];path_join(pattern,HOST_PATH,directory,L"*");
  WIN32_FIND_DATAW data;HANDLE find=FindFirstFileW(pattern,&data);
  if(find==INVALID_HANDLE_VALUE){dict_problem_add(directory,"无法读取目录");return;}
  wchar_t **paths=NULL;size_t count=0;
  do {
    if(data.cFileName[0]==L'.' || (data.dwFileAttributes&FILE_ATTRIBUTE_REPARSE_POINT))continue;
    const wchar_t *ext=wcsrchr(data.cFileName,L'.');
    if(!(data.dwFileAttributes&FILE_ATTRIBUTE_DIRECTORY) && (!ext || (wcscmp(ext,L".ifo")&&wcscmp(ext,L".index"))))continue;
    if(count>=4096 || wcslen(directory)+wcslen(data.cFileName)+2>=HOST_PATH){dict_problem_add(directory,"目录项目过多或路径过长");break;}
    wchar_t **next=realloc(paths,(count+1)*sizeof(*paths));if(!next)break;paths=next;
    paths[count]=calloc(HOST_PATH,sizeof(wchar_t));if(!paths[count])break;
    path_join(paths[count++],HOST_PATH,directory,data.cFileName);
  } while(FindNextFileW(find,&data));
  FindClose(find);if(count)qsort(paths,count,sizeof(*paths),dict_compare_path);
  for(size_t i=0;i<count;i++) {
    if(GetFileAttributesW(paths[i])&FILE_ATTRIBUTE_DIRECTORY)dict_scan(paths[i],depth+1);
    else if(dict_count>=64)dict_problem_add(paths[i],"最多同时加载 64 本词典");
    else {
      char *path=host_utf8(paths[i]);exr_error error={0};
      if(path && exr_dictionary_open(path,&dicts[dict_count],&error)==EXR_OK)dict_count++;
      else dict_problem_add(paths[i],error.message[0] ? error.message:"无法打开词典");
      free(path);
    }
    free(paths[i]);
  }
  free(paths);
}
static void dict_reload(void) {
  for(size_t i=0;i<dict_count;i++)exr_dictionary_free(dicts[i]);
  dict_count=0;
  free(dict_problem);dict_problem=NULL;
  for(size_t i=0;i<dict_dir_count;i++)dict_scan(dict_dirs[i],0);
  if(dict_popup)ShowWindow(dict_popup,SW_HIDE);
}
static void dict_init(void) {
  if(dict_ready)return;
  dict_ready=1;
  shell_shelf_path(dict_path);path_join(vocab_path,HOST_PATH,g.data_dir,L"vocab.json");
  dict_shelf=dict_json_load(dict_path,"{}");
  if(!dict_shelf || dict_shelf->type!=CV_JSON_OBJECT){dict_error(L"shelf.json 格式错误或不可读，暂停修改词典设置。");return;}
  const cv_json *dirs=cv_json_get(dict_shelf,"dictionary_directories"),*auto_lookup=cv_json_get(dict_shelf,"dictionary_auto_lookup");
  if((dirs && (dirs->type!=CV_JSON_ARRAY || dirs->count>64)) || (auto_lookup && auto_lookup->type!=CV_JSON_BOOL))return;
  if(dirs)for(size_t i=0;i<dirs->count;i++) {
    if(dirs->items[i]->type!=CV_JSON_STRING || strlen(dirs->items[i]->string)>=HOST_PATH*3)return;
    wchar_t *wide=host_wide(dirs->items[i]->string,strlen(dirs->items[i]->string));if(!wide)return;
    dict_dirs[dict_dir_count++]=wide;
  }
  dict_auto=auto_lookup && auto_lookup->boolean;dict_writable=1;dict_reload();
}
static int dict_directory_add(const wchar_t *directory) {
  dict_init();wchar_t full[HOST_PATH];DWORD n=GetFullPathNameW(directory,HOST_PATH,full,NULL);
  DWORD attr=GetFileAttributesW(directory);
  if(!n || n>=HOST_PATH || attr==INVALID_FILE_ATTRIBUTES || !(attr&FILE_ATTRIBUTE_DIRECTORY) || dict_dir_count==64)return 0;
  for(size_t i=0;i<dict_dir_count;i++)if(!_wcsicmp(dict_dirs[i],full))return 1;
  wchar_t *copy=malloc((wcslen(full)+1)*sizeof(wchar_t));if(!copy)return 0;wcscpy(copy,full);
  dict_dirs[dict_dir_count++]=copy;
  if(!dict_config_save()){free(dict_dirs[--dict_dir_count]);return 0;}
  dict_reload();return 1;
}
static int dict_directory_remove(size_t index) {
  if(index>=dict_dir_count)return 0;
  wchar_t *saved=dict_dirs[index];
  memmove(dict_dirs+index,dict_dirs+index+1,(dict_dir_count-index-1)*sizeof(*dict_dirs));dict_dir_count--;
  if(!dict_config_save()) {
    memmove(dict_dirs+index+1,dict_dirs+index,(dict_dir_count-index)*sizeof(*dict_dirs));dict_dirs[index]=saved;dict_dir_count++;return 0;
  }
  free(saved);dict_reload();return 1;
}
static void vocab_free(shell_vocab *v) {
  free(v->word);free(v->summary);free(v->book);free(v->sentence);exr_content_anchor_free(&v->anchor);memset(v,0,sizeof(*v));
}
static void vocab_load(void) {
  dict_init();if(vocab_ready)return;vocab_ready=1;
  cv_json *root=dict_json_load(vocab_path,"{\"version\":1,\"words\":[]}");
  const cv_json *words=cv_json_get(root,"words");uint64_t version=0;
  int ok=annot_uint(root,"version",&version) && version==1 && words && words->type==CV_JSON_ARRAY && words->count<=100000;
  if(ok && words->count) {vocab=calloc(words->count,sizeof(*vocab));if(!vocab)ok=0;}
  if(ok)for(size_t i=0;i<words->count;i++) {
    shell_vocab *v=&vocab[vocab_count++];const cv_json *item=words->items[i],*anchor=cv_json_get(item,"anchor");uint64_t book;
    ok=annot_string(item,"word",&v->word,0) && annot_string(item,"summary",&v->summary,0) &&
      annot_string(item,"book",&v->book,0) && annot_string(item,"sentence",&v->sentence,0) &&
      annot_uint(item,"book_id",&book) && book<=INT64_MAX && annot_uint(item,"time_ms",&v->time) &&
      annot_endpoint_read(cv_json_get(anchor,"start"),&v->anchor.start) && annot_endpoint_read(cv_json_get(anchor,"end"),&v->anchor.end);
    if(!ok)break;
    v->book_id=(int64_t)book;
  }
  cv_json_free(root);vocab_writable=ok;
  if(!ok) {
    for(size_t i=0;i<vocab_count;i++)vocab_free(&vocab[i]);
    free(vocab);vocab=NULL;vocab_count=0;
    dict_error(L"vocab.json 格式错误或不可读，暂停写入生词本。");
  }
}
static int vocab_save(void) {
  if(!vocab_writable)return 0;
  cv_text j={0};cv_text_string(&j,"{\"version\":1,\"words\":[\n");
  for(size_t i=0;i<vocab_count;i++) {
    shell_vocab *v=&vocab[i];if(i)cv_text_string(&j,",\n");cv_text_string(&j,"{");
    annot_json_string(&j,"word",v->word);cv_text_string(&j,",");annot_json_string(&j,"summary",v->summary);cv_text_string(&j,",");
    annot_json_string(&j,"book",v->book);cv_text_string(&j,",");annot_json_string(&j,"sentence",v->sentence);
    cv_text_format(&j,",\"book_id\":%lld,\"time_ms\":%llu,\"anchor\":{\"start\":",(long long)v->book_id,(unsigned long long)v->time);
    annot_endpoint_write(&j,&v->anchor.start);cv_text_string(&j,",\"end\":");annot_endpoint_write(&j,&v->anchor.end);cv_text_string(&j,"}}");
  }
  cv_text_string(&j,"\n]}\n");int ok=dict_atomic(vocab_path,&j);cv_text_free(&j);return ok;
}
static char *dict_sentence(const exr_content_anchor *anchor) {
  exr_publication *pub=select_publication();exr_text_range_match match={0};exr_text_range sentence;
  if(!pub || exr_range_from_anchor(pub,anchor,NULL,&match,NULL)!=EXR_OK || match.state!=EXR_ANCHOR_FOUND ||
     exr_range_expand(pub,&match.range,EXR_RANGE_SENTENCE,NULL,&sentence,NULL)!=EXR_OK)return NULL;
  cv_text text={0};
  for(size_t part=sentence.start.part;part<=sentence.end.part;part++) {
    exr_document *doc=NULL;size_t size=0;
    if(exr_publication_load(pub,part,&doc,NULL)!=EXR_OK){text.failed=1;break;}
    const char *source=exr_document_text(doc,&size);size_t first=part==sentence.start.part ? sentence.start.offset:0;
    size_t last=part==sentence.end.part ? sentence.end.offset:size;
    if(!source || first>last || last>size || text.size+last-first>1024*1024)text.failed=1;
    else cv_text_append(&text,source+first,last-first);
    exr_document_free(doc);if(text.failed)break;
  }
  if(text.failed){cv_text_free(&text);return NULL;}return text.data;
}
static int vocab_add(void) {
  vocab_load();
  if(!vocab_writable || !dict_word || !dict_result_count || dict_book!=g.frame.book_id || vocab_count>=100000)return 0;
  shell_vocab v={0};exr_text_range_match match={0};
  if(exr_range_from_anchor(select_publication(),&dict_anchor,NULL,&match,NULL)!=EXR_OK || match.state!=EXR_ANCHOR_FOUND ||
     exr_anchor_from_range(select_publication(),&match.range,NULL,&v.anchor,NULL)!=EXR_OK)return 0;
  v.word=host_strdup(dict_word);v.book=host_strdup(dict_book_title);v.book_id=dict_book;v.time=annot_time();v.sentence=dict_sentence(&dict_anchor);
  cv_text summary={0};
  for(size_t i=0;i<dict_result_count;i++) {
    exr_dictionary_result *r=&dict_results[i];size_t n=strlen(r->definition);if(n>512){n=512;while(n && ((unsigned char)r->definition[n]&0xc0)==0x80)n--;}
    if(i)cv_text_string(&summary,"\n");
    cv_text_format(&summary,"[%s] %s: ",r->dictionary,r->word);cv_text_append(&summary,r->definition,n);
  }
  v.summary=summary.data;
  if(!v.word || !v.book || !v.sentence || !v.summary || summary.failed){vocab_free(&v);return 0;}
  shell_vocab *next=realloc(vocab,(vocab_count+1)*sizeof(*vocab));if(!next){vocab_free(&v);return 0;}
  vocab=next;vocab[vocab_count++]=v;
  if(!vocab_save()){vocab_free(&vocab[--vocab_count]);dict_error(L"生词保存失败，请重试。");return 0;}
  SetWindowTextW(GetDlgItem(dict_popup,DICT_SAVE),L"已加入生词本");EnableWindow(GetDlgItem(dict_popup,DICT_SAVE),FALSE);
  if(vocab_panel && IsWindowVisible(vocab_panel))vocab_list_refresh();
  return 1;
}
static int64_t vocab_filter(void) {
  if(!vocab_panel)return 0;
  LRESULT index=SendDlgItemMessageW(vocab_panel,DICT_FILTER,CB_GETCURSEL,0,0);
  return index<=0 ? 0:(int64_t)SendDlgItemMessageW(vocab_panel,DICT_FILTER,CB_GETITEMDATA,(WPARAM)index,0);
}
static void vocab_csv_cell(cv_text *out,const char *value) {
  cv_text_string(out,"\"");
  /* Quoting alone does not prevent spreadsheet formula interpretation. */
  const char *first=value;while(*first==' '||*first=='\r'||*first=='\n')first++;
  if(*first && strchr("=+-@\t",*first))cv_text_string(out,"'");
  for(const char *p=value;*p;p++){if(*p=='"')cv_text_string(out,"\"");cv_text_append(out,p,1);}cv_text_string(out,"\"");
}
static int vocab_export(const wchar_t *path) {
  vocab_load();if(!vocab_writable)return 0;cv_text csv={0};int64_t filter=vocab_filter();
  cv_text_string(&csv,"\xef\xbb\xbf词,释义摘要,书名,锚点,时间,例句\r\n");
  for(size_t i=0;i<vocab_count;i++) {
    shell_vocab *v=&vocab[i];if(filter && v->book_id!=filter)continue;
    cv_text anchor={0};cv_text_string(&anchor,"{\"start\":");annot_endpoint_write(&anchor,&v->anchor.start);
    cv_text_string(&anchor,",\"end\":");annot_endpoint_write(&anchor,&v->anchor.end);cv_text_string(&anchor,"}");
    char time[32];snprintf(time,sizeof(time),"%llu",(unsigned long long)v->time);
    const char *cells[]={v->word,v->summary,v->book,anchor.data,time,v->sentence};
    for(size_t j=0;j<6;j++){if(j)cv_text_string(&csv,",");vocab_csv_cell(&csv,cells[j] ? cells[j]:"");}
    cv_text_string(&csv,"\r\n");if(anchor.failed)csv.failed=1;cv_text_free(&anchor);
  }
  int ok=dict_atomic(path,&csv);cv_text_free(&csv);return ok;
}
static void dict_set_text(HWND window,const char *text) {
  cv_text crlf={0};
  for(const char *p=text;*p;p++){if(*p=='\n' && (p==text || p[-1]!='\r'))cv_text_string(&crlf,"\r");cv_text_append(&crlf,p,1);}
  wchar_t *wide=host_wide(crlf.data ? crlf.data:"",crlf.size);SetWindowTextW(window,wide ? wide:L"");free(wide);cv_text_free(&crlf);
}
static HWND dict_control(HWND parent,const wchar_t *type,const wchar_t *label,int id,DWORD style) {
  HWND control=CreateWindowExW(0,type,label,WS_CHILD|WS_VISIBLE|WS_TABSTOP|style,0,0,0,0,parent,(HMENU)(INT_PTR)id,NULL,NULL);
  SendMessageW(control,WM_SETFONT,(WPARAM)dict_font,TRUE);return control;
}
static void dict_place(HWND parent,int id,int x,int y,int width,int height) {
  MoveWindow(GetDlgItem(parent,id),shell_px(x,shell_dpi),shell_px(y,shell_dpi),shell_px(width,shell_dpi),shell_px(height,shell_dpi),TRUE);
}
static void dict_card_paint(HWND window,HDC dc) {
  RECT box;GetClientRect(window,&box);
  shell_card_paint(window,dc,&box,window==dict_popup ? L"查词":window==dict_manager ? L"词典设置":window==sy_panel ? L"云同步（WebDAV）":L"生词本");
}
static LRESULT CALLBACK dict_procedure(HWND window,UINT message,WPARAM wp,LPARAM lp);
static HWND dict_card_create(const wchar_t *title) {
  if(!dict_font)dict_font=CreateFontW(-shell_px(14,shell_dpi),0,0,0,FW_NORMAL,FALSE,FALSE,FALSE,DEFAULT_CHARSET,
    OUT_DEFAULT_PRECIS,CLIP_DEFAULT_PRECIS,CLEARTYPE_QUALITY,DEFAULT_PITCH,L"Microsoft YaHei UI");
  WNDCLASSW type={0};type.lpfnWndProc=dict_procedure;type.hInstance=GetModuleHandleW(NULL);type.hCursor=LoadCursor(NULL,IDC_ARROW);type.lpszClassName=L"EXReaderDictionary";RegisterClassW(&type);
  return CreateWindowExW(WS_EX_CONTROLPARENT,type.lpszClassName,title,WS_CHILD|WS_CLIPCHILDREN|WS_CLIPSIBLINGS,
    0,0,0,0,g.window,NULL,type.hInstance,NULL);
}
static void dict_card_position(HWND window,int width,int height) {
  RECT client;GetClientRect(g.window,&client);
  int w=shell_px(width+2*SHELL_SHADOW_PAD,shell_dpi),h=shell_px(height+SHELL_SHADOW_PAD+SHELL_SHADOW_TOP,shell_dpi);
  SetWindowPos(window,HWND_TOP,(client.right-w)/2,max(0,(client.bottom-h)/2),w,h,SWP_NOACTIVATE);
}
static void dict_groups_layout(void) {
  if(!dict_view)return;
  RECT box;GetClientRect(dict_view,&box);int y=0;
  for(size_t i=0;i<dict_count;i++)if(dict_headers[i]) {
    y+=shell_px(54,shell_dpi);
    if(!dict_collapsed[i])y+=shell_px(144,shell_dpi);
  }
  dict_content_height=y;dict_scroll=max(0,min(dict_scroll,y-box.bottom));
  SCROLLINFO si={sizeof(si),SIF_RANGE|SIF_PAGE|SIF_POS,0,max(0,y-1),(UINT)box.bottom,dict_scroll,0};SetScrollInfo(dict_view,SB_VERT,&si,TRUE);
  GetClientRect(dict_view,&box); /* The scrollbar may just have changed client width. */
  y=-dict_scroll;
  for(size_t i=0;i<dict_count;i++)if(dict_headers[i]) {
    MoveWindow(dict_headers[i],0,y,box.right,shell_px(50,shell_dpi),TRUE);y+=shell_px(54,shell_dpi);
    ShowWindow(dict_bodies[i],dict_collapsed[i] ? SW_HIDE:SW_SHOWNOACTIVATE);
    if(!dict_collapsed[i]){MoveWindow(dict_bodies[i],shell_px(6,shell_dpi),y,box.right-shell_px(12,shell_dpi),shell_px(136,shell_dpi),TRUE);y+=shell_px(144,shell_dpi);}
    const exr_dictionary_info *info=exr_dictionary_get_info(dicts[i]);cv_text label={0};
    cv_text_format(&label,"%s %s",dict_collapsed[i] ? "▸":"▾",info->bookname);dict_set_text(dict_headers[i],label.data);cv_text_free(&label);
  }
  InvalidateRect(dict_view,NULL,TRUE);
}
static void dict_hide(void) {if(dict_popup)ShowWindow(dict_popup,SW_HIDE);}
static void dict_close_all(void) {
  HWND panels[]={dict_popup,dict_manager,vocab_panel,sy_panel};
  for(size_t i=0;i<4;i++)if(panels[i])ShowWindow(panels[i],SW_HIDE);
}
static void dict_lookup(void) {
  dict_init();char *word=NULL;size_t size=shell_selection_bytes(&word);
  if(!size){free(word);return;}
  if(size>4096){free(word);dict_error(L"选中文字过长，请选择词语或短语。");return;}
  exr_content_anchor anchor={0};
  if(exr_anchor_from_range(select_publication(),&select_range,NULL,&anchor,NULL)!=EXR_OK){free(word);return;}
  exr_content_anchor_free(&dict_anchor);dict_anchor=anchor;dict_book=g.frame.book_id;
  int row=shelf_index(g.frame.book_id);
  free(dict_book_title);dict_book_title=row>=0 ? host_strdup(sm_title((size_t)row)):host_utf8(g.frame.title);
  free(dict_word);dict_word=word;
  exr_dictionary_results_free(dict_results,dict_result_count);dict_results=NULL;dict_result_count=0;
  char *query=host_strdup(word);if(!query)return;
  size_t n=strlen(query);while(n && isspace((unsigned char)query[n-1]))query[--n]=0;
  char *start=query;while(isspace((unsigned char)*start))start++;
  exr_error error={0};exr_status status=exr_dictionary_query(dicts,dict_count,start,8,&dict_results,&dict_result_count,&error);free(query);
  if(!dict_popup) {
    dict_popup=dict_card_create(L"查词");
    dict_control(dict_popup,L"EDIT",L"",DICT_QUERY,ES_READONLY|ES_AUTOHSCROLL);
    dict_control(dict_popup,L"EDIT",L"",DICT_STATUS,ES_READONLY|ES_MULTILINE|ES_AUTOVSCROLL|WS_VSCROLL);
    dict_view=CreateWindowExW(WS_EX_CONTROLPARENT,L"EXReaderDictionary",L"词典释义分组",WS_CHILD|WS_VISIBLE|WS_CLIPCHILDREN|WS_VSCROLL,
      0,0,0,0,dict_popup,NULL,GetModuleHandleW(NULL),NULL);
    dict_control(dict_popup,L"BUTTON",L"加入生词本",DICT_SAVE,BS_OWNERDRAW);
    dict_control(dict_popup,L"BUTTON",L"生词本",DICT_VOCAB,BS_OWNERDRAW);
    dict_control(dict_popup,L"BUTTON",L"关闭",DICT_CLOSE,BS_OWNERDRAW);
  }
  for(size_t i=0;i<64;i++){if(dict_headers[i])DestroyWindow(dict_headers[i]);if(dict_bodies[i])DestroyWindow(dict_bodies[i]);dict_headers[i]=dict_bodies[i]=NULL;dict_collapsed[i]=0;}
  for(size_t i=0;i<dict_count;i++) {
    cv_text body={0};
    for(size_t j=0;j<dict_result_count;j++)if(dict_results[j].dictionary_index==i) {
      exr_dictionary_result *r=&dict_results[j];
      if(body.size)cv_text_string(&body,"\n\n");
      cv_text_format(&body,"%s%s%s\n%s",r->word,*r->part_of_speech ? " · ":"",r->part_of_speech,r->definition);
    }
    if(body.size) {
      dict_headers[i]=dict_control(dict_view,L"BUTTON",L"",DICT_GROUP+(int)i,BS_OWNERDRAW);
      dict_bodies[i]=dict_control(dict_view,L"EDIT",L"",1000+(int)i,ES_MULTILINE|ES_READONLY|ES_AUTOVSCROLL|WS_VSCROLL);
      SendMessageW(dict_bodies[i],EM_SETLIMITTEXT,16*1024*1024,0);dict_set_text(dict_bodies[i],body.data);
    }
    cv_text_free(&body);
  }
  const char *state=status!=EXR_OK ? "查询失败：词典释义损坏或无法读取。" : !dict_result_count ? "未收录 · 可选择并复制上方词条原文":"";
  if(!dict_count && !dict_problem)state="未收录 · 请在设置中添加词典目录；上方词条可复制。";
  cv_text message={0};cv_text_string(&message,state);if(dict_problem){cv_text_string(&message,"\n部分词典不可用：\n");cv_text_string(&message,dict_problem);}
  dict_set_text(GetDlgItem(dict_popup,DICT_QUERY),dict_word);dict_set_text(GetDlgItem(dict_popup,DICT_STATUS),message.data ? message.data:"");cv_text_free(&message);
  SetWindowTextW(GetDlgItem(dict_popup,DICT_SAVE),L"加入生词本");EnableWindow(GetDlgItem(dict_popup,DICT_SAVE),dict_result_count>0 && dict_book_title!=NULL);
  dict_card_position(dict_popup,360,dict_result_count ? 420:196);
  dict_place(dict_popup,DICT_QUERY,80,68,328,28);dict_place(dict_popup,DICT_STATUS,80,100,328,44);
  int show_status=*state || dict_problem;
  ShowWindow(GetDlgItem(dict_popup,DICT_STATUS),show_status ? SW_SHOWNOACTIVATE:SW_HIDE);
  ShowScrollBar(GetDlgItem(dict_popup,DICT_STATUS),SB_VERT,dict_problem!=NULL);
  ShowWindow(dict_view,dict_result_count ? SW_SHOWNOACTIVATE:SW_HIDE);
  MoveWindow(dict_view,shell_px(80,shell_dpi),shell_px(show_status ? 148:108,shell_dpi),shell_px(328,shell_dpi),shell_px(show_status ? 238:278,shell_dpi),TRUE);
  int footer=dict_result_count ? 398:174;
  dict_place(dict_popup,DICT_SAVE,80,footer,144,34);dict_place(dict_popup,DICT_VOCAB,230,footer,84,34);dict_place(dict_popup,DICT_CLOSE,320,footer,88,34);
  dict_scroll=0;dict_groups_layout();ShowWindow(dict_popup,SW_SHOWNOACTIVATE);SetFocus(GetDlgItem(dict_popup,DICT_QUERY));InvalidateRect(dict_popup,NULL,TRUE);
}
static void dict_auto_lookup(void) {dict_init();if(dict_auto && select_valid && !select_drag && g.selection.active)dict_lookup();}
static void dict_manager_refresh(void) {
  HWND list=GetDlgItem(dict_manager,DICT_PATHS);SendMessageW(list,LB_RESETCONTENT,0,0);
  HDC dc=GetDC(list);HGDIOBJ old=SelectObject(dc,dict_font);int extent=0;
  for(size_t i=0;i<dict_dir_count;i++) {
    SendMessageW(list,LB_ADDSTRING,0,(LPARAM)dict_dirs[i]);SIZE size={0};GetTextExtentPoint32W(dc,dict_dirs[i],(int)wcslen(dict_dirs[i]),&size);extent=max(extent,size.cx);
  }
  SelectObject(dc,old);ReleaseDC(list,dc);SendMessageW(list,LB_SETHORIZONTALEXTENT,(WPARAM)(extent+16),0);
  CheckDlgButton(dict_manager,DICT_AUTO,dict_auto ? BST_CHECKED:BST_UNCHECKED);
  cv_text status={0};cv_text_format(&status,"已加载 %zu 本词典，按目录顺序查询。\n",dict_count);
  if(dict_problem)cv_text_string(&status,dict_problem);
  if(!dict_writable)cv_text_string(&status,"shelf.json 不可写，请检查文件格式与访问权限。");
  dict_set_text(GetDlgItem(dict_manager,DICT_STATUS),status.data);cv_text_free(&status);
}
static void dict_manager_open(void) {
  dict_init();dict_hide();
  if(!dict_manager) {
    dict_manager=dict_card_create(L"词典设置");
    dict_control(dict_manager,L"LISTBOX",L"词典目录（查询顺序）",DICT_PATHS,LBS_NOTIFY|WS_VSCROLL|WS_HSCROLL);
    dict_control(dict_manager,L"BUTTON",L"添加目录",DICT_ADD,BS_OWNERDRAW);
    dict_control(dict_manager,L"BUTTON",L"移除目录",DICT_REMOVE,BS_OWNERDRAW);
    dict_control(dict_manager,L"BUTTON",L"选中即查",DICT_AUTO,BS_AUTOCHECKBOX);
    dict_control(dict_manager,L"EDIT",L"",DICT_STATUS,ES_MULTILINE|ES_READONLY|WS_VSCROLL);
    dict_control(dict_manager,L"BUTTON",L"生词本",DICT_VOCAB,BS_OWNERDRAW);
    dict_control(dict_manager,L"BUTTON",L"关闭",DICT_CLOSE,BS_OWNERDRAW);
  }
  dict_card_position(dict_manager,520,420);
  dict_place(dict_manager,DICT_PATHS,80,70,488,138);dict_place(dict_manager,DICT_ADD,80,218,124,34);
  dict_place(dict_manager,DICT_REMOVE,212,218,124,34);dict_place(dict_manager,DICT_AUTO,360,218,180,34);
  dict_place(dict_manager,DICT_STATUS,80,264,488,116);dict_place(dict_manager,DICT_VOCAB,80,398,140,34);dict_place(dict_manager,DICT_CLOSE,428,398,140,34);
  dict_manager_refresh();ShowWindow(dict_manager,SW_SHOWNOACTIVATE);SetFocus(GetDlgItem(dict_manager,DICT_PATHS));
}
static void vocab_list_refresh(void) {
  HWND list=GetDlgItem(vocab_panel,DICT_LIST);SendMessageW(list,LB_RESETCONTENT,0,0);int64_t filter=vocab_filter();
  for(size_t i=0;i<vocab_count;i++) {
    shell_vocab *v=&vocab[i];if(filter && v->book_id!=filter)continue;
    cv_text row={0};cv_text_format(&row,"%s — %s",v->word,v->book);wchar_t *wide=host_wide(row.data,row.size);
    LRESULT index=SendMessageW(list,LB_ADDSTRING,0,(LPARAM)(wide ? wide:L""));SendMessageW(list,LB_SETITEMDATA,(WPARAM)index,(LPARAM)i);free(wide);cv_text_free(&row);
  }
  SetWindowTextW(GetDlgItem(vocab_panel,DICT_STATUS),vocab_count ? L"选择词条查看释义与例句。":L"生词本为空；划词查询后可加入。");
}
static void vocab_open(void) {
  vocab_load();dict_hide();if(dict_manager)ShowWindow(dict_manager,SW_HIDE);
  if(!vocab_panel) {
    vocab_panel=dict_card_create(L"生词本");
    dict_control(vocab_panel,L"COMBOBOX",L"按书筛选",DICT_FILTER,CBS_DROPDOWNLIST|WS_VSCROLL);
    dict_control(vocab_panel,L"LISTBOX",L"生词列表",DICT_LIST,LBS_NOTIFY|WS_VSCROLL);
    dict_control(vocab_panel,L"EDIT",L"",DICT_STATUS,ES_MULTILINE|ES_READONLY|ES_AUTOVSCROLL|WS_VSCROLL);
    dict_control(vocab_panel,L"BUTTON",L"导出 CSV",DICT_EXPORT,BS_OWNERDRAW);
    dict_control(vocab_panel,L"BUTTON",L"关闭",DICT_CLOSE,BS_OWNERDRAW);
  }
  dict_card_position(vocab_panel,520,440);
  dict_place(vocab_panel,DICT_FILTER,80,70,488,220);dict_place(vocab_panel,DICT_LIST,80,110,488,128);
  dict_place(vocab_panel,DICT_STATUS,80,250,488,150);dict_place(vocab_panel,DICT_EXPORT,80,418,160,34);dict_place(vocab_panel,DICT_CLOSE,428,418,140,34);
  HWND filter=GetDlgItem(vocab_panel,DICT_FILTER);SendMessageW(filter,CB_RESETCONTENT,0,0);SendMessageW(filter,CB_ADDSTRING,0,(LPARAM)L"全部书籍");
  for(size_t i=0;i<vocab_count;i++) {
    int seen=0;for(size_t j=0;j<i;j++)if(vocab[j].book_id==vocab[i].book_id)seen=1;if(seen)continue;
    wchar_t *wide=host_wide(vocab[i].book,strlen(vocab[i].book));LRESULT index=SendMessageW(filter,CB_ADDSTRING,0,(LPARAM)(wide ? wide:L""));free(wide);
    SendMessageW(filter,CB_SETITEMDATA,(WPARAM)index,(LPARAM)vocab[i].book_id);
  }
  SendMessageW(filter,CB_SETCURSEL,0,0);vocab_list_refresh();ShowWindow(vocab_panel,SW_SHOWNOACTIVATE);SetFocus(filter);
}
static LRESULT CALLBACK dict_procedure(HWND window,UINT message,WPARAM wp,LPARAM lp) {
  switch(message) {
    case WM_ERASEBKGND:return 1;
    case WM_CTLCOLORSTATIC:case WM_CTLCOLOREDIT:case WM_CTLCOLORLISTBOX:case WM_CTLCOLORBTN:
      SetTextColor((HDC)wp,shell_colorref(shell_colors->text));SetBkColor((HDC)wp,shell_colorref(shell_colors->layer_float));
      if(dict_brush)DeleteObject(dict_brush);
      dict_brush=CreateSolidBrush(shell_colorref(shell_colors->layer_float));return (LRESULT)dict_brush;
    case WM_MOUSEWHEEL:
      if(window==dict_view){dict_scroll-=GET_WHEEL_DELTA_WPARAM(wp)/WHEEL_DELTA*shell_px(48,shell_dpi);dict_groups_layout();return 0;}break;
    case WM_VSCROLL:
      if(window==dict_view) {
        SCROLLINFO si={sizeof(si),SIF_ALL,0,0,0,0,0};GetScrollInfo(window,SB_VERT,&si);
        switch(LOWORD(wp)) {
          case SB_LINEUP:dict_scroll-=shell_px(24,shell_dpi);break;case SB_LINEDOWN:dict_scroll+=shell_px(24,shell_dpi);break;
          case SB_PAGEUP:dict_scroll-=(int)si.nPage;break;case SB_PAGEDOWN:dict_scroll+=(int)si.nPage;break;
          case SB_THUMBTRACK:case SB_THUMBPOSITION:dict_scroll=si.nTrackPos;break;
        }
        dict_groups_layout();return 0;
      }break;
    case WM_COMMAND: {
      int id=LOWORD(wp);
      if(sy_command(window,id,HIWORD(wp)))return 0;
      if(id>=DICT_GROUP && id<DICT_GROUP+64){dict_collapsed[id-DICT_GROUP]=!dict_collapsed[id-DICT_GROUP];dict_groups_layout();return 0;}
      if(id==DICT_CLOSE){ShowWindow(window,SW_HIDE);SetFocus(g.page);return 0;}
      if(id==DICT_SAVE){vocab_add();return 0;}
      if(id==DICT_VOCAB){vocab_open();return 0;}
      if(id==DICT_ADD) {
        HRESULT initialized=CoInitializeEx(NULL,COINIT_APARTMENTTHREADED);
        BROWSEINFOW browse={0};wchar_t path[HOST_PATH];browse.hwndOwner=g.window;browse.lpszTitle=L"选择 StarDict / dictd 词典目录";browse.ulFlags=BIF_RETURNONLYFSDIRS|BIF_NEWDIALOGSTYLE;
        if(initialized==RPC_E_CHANGED_MODE)browse.ulFlags=BIF_RETURNONLYFSDIRS;
        PIDLIST_ABSOLUTE item=SHBrowseForFolderW(&browse);
        if(item){if(SHGetPathFromIDListW(item,path) && !dict_directory_add(path))dict_error(L"无法添加词典目录。");CoTaskMemFree(item);}
        if(SUCCEEDED(initialized))CoUninitialize();
        dict_manager_refresh();return 0;
      }
      if(id==DICT_REMOVE){LRESULT i=SendDlgItemMessageW(window,DICT_PATHS,LB_GETCURSEL,0,0);if(i>=0)dict_directory_remove((size_t)i);dict_manager_refresh();return 0;}
      if(id==DICT_AUTO){int previous=dict_auto;dict_auto=IsDlgButtonChecked(window,DICT_AUTO)==BST_CHECKED;if(!dict_config_save())dict_auto=previous;dict_manager_refresh();return 0;}
      if(id==DICT_FILTER && HIWORD(wp)==CBN_SELCHANGE){vocab_list_refresh();return 0;}
      if(id==DICT_LIST && HIWORD(wp)==LBN_SELCHANGE) {
        LRESULT index=SendDlgItemMessageW(window,DICT_LIST,LB_GETCURSEL,0,0);
        if(index>=0){size_t i=(size_t)SendDlgItemMessageW(window,DICT_LIST,LB_GETITEMDATA,(WPARAM)index,0);if(i<vocab_count){cv_text text={0};cv_text_format(&text,"%s\n\n%s\n\n例句：%s",vocab[i].word,vocab[i].summary,vocab[i].sentence);dict_set_text(GetDlgItem(window,DICT_STATUS),text.data);cv_text_free(&text);}}return 0;
      }
      if(id==DICT_EXPORT) {
        wchar_t path[HOST_PATH]=L"vocabulary.csv";OPENFILENAMEW dialog={0};dialog.lStructSize=sizeof(dialog);dialog.hwndOwner=g.window;dialog.lpstrFile=path;dialog.nMaxFile=HOST_PATH;
        dialog.lpstrFilter=L"CSV (*.csv)\0*.csv\0\0";dialog.lpstrDefExt=L"csv";dialog.Flags=OFN_OVERWRITEPROMPT|OFN_PATHMUSTEXIST;
        if(GetSaveFileNameW(&dialog)){if(vocab_export(path))set_status(L"生词 CSV 已导出（含例句）。");else dict_error(L"CSV 导出失败。");}return 0;
      }
      break;
    }
    case WM_DRAWITEM: {
      const DRAWITEMSTRUCT *item=(const DRAWITEMSTRUCT *)lp;wchar_t text[512];GetWindowTextW(item->hwndItem,text,512);
      if(item->CtlID>=DICT_GROUP && item->CtlID<DICT_GROUP+64) {
        RECT box=item->rcItem;HBRUSH brush=CreateSolidBrush(shell_colorref(shell_colors->surface2));FillRect(item->hDC,&box,brush);DeleteObject(brush);
        HGDIOBJ old=SelectObject(item->hDC,dict_font);SetTextColor(item->hDC,shell_colorref(shell_colors->text_secondary));SetBkMode(item->hDC,TRANSPARENT);
        InflateRect(&box,-shell_px(6,shell_dpi),-shell_px(3,shell_dpi));DrawTextW(item->hDC,text,-1,&box,DT_WORDBREAK|DT_NOPREFIX);
        SelectObject(item->hDC,old);if(item->itemState&ODS_FOCUS)DrawFocusRect(item->hDC,&item->rcItem);return TRUE;
      }
      shell_draw_control(item,text,item->CtlID==DICT_SAVE || item->CtlID==SY_ID_NOW ? SHELL_CONTROL_PRIMARY:SHELL_CONTROL_STANDARD,shell_colors->layer_float);return TRUE;
    }
    case WM_PAINT:case WM_PRINTCLIENT: {
      PAINTSTRUCT paint;HDC dc=message==WM_PAINT ? BeginPaint(window,&paint):(HDC)wp;
      if(window==dict_view){RECT box;GetClientRect(window,&box);HBRUSH brush=CreateSolidBrush(shell_colorref(shell_colors->layer_float));FillRect(dc,&box,brush);DeleteObject(brush);}
      else dict_card_paint(window,dc);
      if(message==WM_PAINT)EndPaint(window,&paint);
      return 0;
    }
  }
  return DefWindowProcW(window,message,wp,lp);
}
static int dict_translate(const MSG *message) {
  HWND panels[]={dict_popup,dict_manager,vocab_panel,sy_panel};
  for(size_t i=0;i<4;i++)if(panels[i] && IsWindowVisible(panels[i])) {
    if(message->message==WM_KEYDOWN && message->wParam==VK_ESCAPE){ShowWindow(panels[i],SW_HIDE);SetFocus(g.page);return 1;}
    if((message->message==WM_LBUTTONDOWN || message->message==WM_POINTERDOWN) && message->hwnd==g.page) {
      dict_close_all();SetFocus(g.page);return 1;
    }
    if(IsDialogMessageW(panels[i],(MSG *)message))return 1;
  }
  return 0;
}
static void dict_shutdown(void) {
  for(size_t i=0;i<dict_count;i++)exr_dictionary_free(dicts[i]);
  dict_count=0;
  for(size_t i=0;i<dict_dir_count;i++)free(dict_dirs[i]);
  dict_dir_count=0;
  for(size_t i=0;i<vocab_count;i++)vocab_free(&vocab[i]);
  free(vocab);vocab=NULL;vocab_count=0;
  cv_json_free(dict_shelf);dict_shelf=NULL;free(dict_word);dict_word=NULL;free(dict_problem);dict_problem=NULL;
  free(dict_book_title);dict_book_title=NULL;exr_content_anchor_free(&dict_anchor);
  exr_dictionary_results_free(dict_results,dict_result_count);dict_results=NULL;dict_result_count=0;
  if(dict_brush)DeleteObject(dict_brush);
  dict_brush=NULL;
  if(dict_font)DeleteObject(dict_font);
  dict_font=NULL;
  dict_ready=vocab_ready=dict_writable=vocab_writable=0;
}
