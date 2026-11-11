/* SPDX-License-Identifier: MIT */
/* 书源 (OPDS catalogs): browse a remote library, download a book into the local
   shelf. Parsing is exr_opds_*; transport is opds_net.h (WinHTTP, HTTPS only,
   10 minute feed cache). All network work runs on one worker thread; results
   come back to the UI thread as a window message. A downloaded file goes
   through the normal import job, so metadata, cover and reading are the same
   as for a local book. */
#include <exr/opds.h>
#include "opds_net.h"
enum {
  OPDS_ID_BACK=300,OPDS_ID_NEXT,OPDS_ID_REFRESH,OPDS_ID_GO,OPDS_ID_SEARCH,OPDS_ID_ACTION,OPDS_ID_CANCEL,OPDS_ID_CLOSE,
  OPDS_ID_URL,OPDS_ID_QUERY,OPDS_ID_LIST,OPDS_ID_URL_LABEL,OPDS_ID_QUERY_LABEL,
  OPDS_MSG_DONE=WM_APP+0x210,OPDS_MSG_PROGRESS,OPDS_STACK=24
};
typedef enum { OPDS_OP_FEED=1,OPDS_OP_SEARCH,OPDS_OP_DOWNLOAD } opds_op;
typedef struct {
  opds_op kind;
  char url[2048],query[256],search_template[2048],search_description[2048];
  int use_cache,nav; /* nav: 1 push current page, -1 pop, 2 new source (reset history), 0 stay */
  char title[256],format[16];
  wchar_t dest[HOST_PATH];
  unsigned receive_ms;
  exr_opds_feed feed;int has_feed;
  char found_template[2048],feed_url[2048];
  onet_result result;
  char error[256];
} opds_job;
static void opds_back_to_shelf(void);
static HWND opds_view,opds_url_edit,opds_query_edit,opds_list;
static exr_opds_feed opds_feed;
static char opds_url[2048],opds_stack[OPDS_STACK][2048],opds_search_template[2048],opds_search_description[2048];
static int opds_depth,opds_visible;
static volatile LONG opds_cancel;
static volatile ULONGLONG opds_done_bytes,opds_total_bytes;
static ULONGLONG opds_last_progress_tick;
static wchar_t opds_status[512],opds_download_path[HOST_PATH],opds_download_title[256],opds_source_file[HOST_PATH];
static onet_result opds_last_result;
static unsigned opds_receive_override,opds_downloads_done,opds_downloads_cancelled,opds_downloads_failed,opds_imports_started,opds_feeds_loaded;
static int opds_last_op,opds_last_from_cache;
static HBRUSH opds_brush;
static WNDPROC opds_edit_base;

static void opds_set_status(const wchar_t *text) {
  wcsncpy(opds_status,text,511);opds_status[511]=0;
  if(opds_view)InvalidateRect(opds_view,NULL,FALSE);
}
static void opds_set_status_utf8(const char *prefix,const char *text) {
  wchar_t *a=host_wide(prefix,strlen(prefix)),*b=host_wide(text,strlen(text));
  wchar_t line[512];swprintf(line,512,L"%ls%ls",a ? a:L"",b ? b:L"");free(a);free(b);
  opds_set_status(line);
}
static void opds_controls_enable(void) {
  int busy=opds_busy!=0,selected=opds_list ? (int)SendMessageW(opds_list,LB_GETCURSEL,0,0):-1;
  EnableWindow(GetDlgItem(opds_view,OPDS_ID_GO),!busy);EnableWindow(GetDlgItem(opds_view,OPDS_ID_SEARCH),!busy);
  EnableWindow(GetDlgItem(opds_view,OPDS_ID_BACK),!busy && opds_depth>0);
  EnableWindow(GetDlgItem(opds_view,OPDS_ID_NEXT),!busy && opds_feed.next_url!=NULL);
  EnableWindow(GetDlgItem(opds_view,OPDS_ID_REFRESH),!busy && opds_url[0]);
  EnableWindow(GetDlgItem(opds_view,OPDS_ID_ACTION),!busy && selected>=0 && (size_t)selected<opds_feed.entry_count);
  EnableWindow(GetDlgItem(opds_view,OPDS_ID_CANCEL),busy);
  InvalidateRect(opds_view,NULL,FALSE);
}
static void opds_format_size(uint64_t bytes,wchar_t *out,size_t cap) {
  if(!bytes)out[0]=0;
  else if(bytes>=1048576)swprintf(out,cap,L"%.1f MB",bytes/1048576.0);
  else swprintf(out,cap,L"%llu KB",(unsigned long long)((bytes+1023)/1024));
}
static void opds_fill_list(void) {
  SendMessageW(opds_list,WM_SETREDRAW,FALSE,0);SendMessageW(opds_list,LB_RESETCONTENT,0,0);
  for(size_t i=0;i<opds_feed.entry_count;i++) {
    const exr_opds_entry *e=&opds_feed.entries[i];
    const char *title=e->title ? e->title:"(无标题)";
    const char *by=e->author ? e->author:e->summary ? e->summary:"";
    char line[1024];wchar_t tail[96]=L"",size[32];
    char first[256];size_t n=strcspn(by,"\r\n");if(n>255)n=255;memcpy(first,by,n);first[n]=0;
    snprintf(line,sizeof(line),"%s%s%s%s",e->download_url ? "↓  ":"›  ",title,first[0] ? "  —  ":"",first);
    if(e->download_url) {
      wchar_t *fmt=host_wide(e->format ? e->format:"",strlen(e->format ? e->format:""));
      opds_format_size(e->size,size,32);
      swprintf(tail,96,L"   [%ls%ls%ls]",fmt ? fmt:L"",size[0] ? L" ":L"",size);free(fmt);
      for(wchar_t *p=tail;*p;p++)*p=(wchar_t)towupper(*p);
    }
    wchar_t *wide=host_wide(line,strlen(line));wchar_t row[1200];
    swprintf(row,1200,L"%ls%ls",wide ? wide:L"",tail);free(wide);
    SendMessageW(opds_list,LB_ADDSTRING,0,(LPARAM)row);
  }
  if(opds_feed.entry_count)SendMessageW(opds_list,LB_SETCURSEL,0,0);
  SendMessageW(opds_list,WM_SETREDRAW,TRUE,0);InvalidateRect(opds_list,NULL,TRUE);
}
static void opds_save_source(const char *url) {
  FILE *f=_wfopen(opds_source_file,L"wb");
  if(f){fputs(url,f);fclose(f);}
}
static void opds_download_name(const char *title,const char *format,wchar_t *out) {
  wchar_t *name=host_wide(title && *title ? title:"book",strlen(title && *title ? title:"book"));
  wchar_t clean[96]=L"";size_t o=0;
  for(const wchar_t *p=name ? name:L"book";*p && o<80;p++) {
    if(*p<32 || wcschr(L"\\/:*?\"<>|",*p))clean[o++]=L'_';else clean[o++]=*p;
  }
  while(o && (clean[o-1]==L' ' || clean[o-1]==L'.'))o--;
  clean[o]=0;if(!o)wcscpy(clean,L"book");
  free(name);
  wchar_t folder[HOST_PATH],stem[HOST_PATH],extension[16];
  path_join(folder,HOST_PATH,g.data_dir,L"opds-downloads");ensure_directory(folder);
  wchar_t *f=host_wide(format && *format && strcmp(format,"other") ? format:"bin",strlen(format && *format && strcmp(format,"other") ? format:"bin"));
  swprintf(extension,16,L".%ls",f ? f:L"bin");free(f);
  swprintf(stem,HOST_PATH,L"%ls%ls",clean,extension);path_join(out,HOST_PATH,folder,stem);
  for(int n=2;GetFileAttributesW(out)!=INVALID_FILE_ATTRIBUTES && n<1000;n++) {
    swprintf(stem,HOST_PATH,L"%ls (%d)%ls",clean,n,extension);path_join(out,HOST_PATH,folder,stem);
  }
}

/* ---- worker ----------------------------------------------------------- */
static void opds_progress_cb(void *context,uint64_t done,uint64_t total) {
  (void)context;
  opds_done_bytes=done;opds_total_bytes=total;
  ULONGLONG now=GetTickCount64();
  if(now-opds_last_progress_tick>=80 || (total && done>=total)) {opds_last_progress_tick=now;PostMessageW(opds_view,OPDS_MSG_PROGRESS,0,0);}
}
static int opds_load_feed(const char *url,int use_cache,onet_options *o,opds_job *j) {
  onet_buffer body;exr_error error={0};char secure[2048];
  /* A typed source must pass the transport's HTTPS check unchanged. Catalog
     links may use legacy http URLs, which we request over HTTPS. */
  if(j->nav==2)snprintf(secure,sizeof(secure),"%s",url);
  else onet_secure(url,secure,sizeof(secure));
  if(!onet_fetch(secure,o,use_cache,&body,&j->result))return 0;
  snprintf(j->feed_url,sizeof(j->feed_url),"%s",j->result.from_cache ? secure:j->result.final_url);
  if(exr_opds_parse(body.data,body.size,j->feed_url,&j->feed,&error)!=EXR_OK) {
    onet_fail(&j->result,ONET_HTTP,"这个地址返回的不是 OPDS 书源目录（%s）。",error.message);
    free(body.data);return 0;
  }
  free(body.data);j->has_feed=1;return 1;
}
static int opds_valid_file(const wchar_t *path,const char *format) {
  FILE *f=_wfopen(path,L"rb");unsigned char head[8]={0};size_t n;
  if(!f)return 0;
  n=fread(head,1,sizeof(head),f);fclose(f);
  if(n<4)return 0;
  if(!strcmp(format,"epub") || !strcmp(format,"cbz") || !strcmp(format,"docx"))return head[0]=='P' && head[1]=='K';
  if(!strcmp(format,"pdf"))return !memcmp(head,"%PDF",4);
  return 1;
}
static DWORD WINAPI opds_worker(void *argument) {
  opds_job *j=argument;
  onet_options o={0};
  o.cancel=&opds_cancel;o.receive_ms=j->receive_ms;
  if(j->kind==OPDS_OP_FEED) {
    opds_load_feed(j->url,j->use_cache,&o,j);
  } else if(j->kind==OPDS_OP_SEARCH) {
    char tmpl[2048]="",*expanded=NULL;exr_error error={0};
    snprintf(tmpl,sizeof(tmpl),"%s",j->search_template);
    if(!tmpl[0] && j->search_description[0]) {
      onet_buffer body;char secure[2048];
      onet_secure(j->search_description,secure,sizeof(secure));
      if(onet_fetch(secure,&o,1,&body,&j->result)) {
        char *found=NULL;
        if(exr_opds_parse_search(body.data,body.size,secure,&found,&error)==EXR_OK){snprintf(tmpl,sizeof(tmpl),"%s",found);exr_free(found);}
        else onet_fail(&j->result,ONET_HTTP,"无法读取书源的搜索说明（%s）。",error.message);
        free(body.data);
      }
    }
    if(!tmpl[0]) {if(j->result.code==ONET_OK)onet_fail(&j->result,ONET_HTTP,"该书源没有提供搜索。");}
    else if(exr_opds_search_url(tmpl,j->query,&expanded,&error)!=EXR_OK) onet_fail(&j->result,ONET_HTTP,"搜索词无效：%s",error.message);
    else {
      snprintf(j->found_template,sizeof(j->found_template),"%s",tmpl);
      opds_load_feed(expanded,1,&o,j);exr_free(expanded);
    }
  } else {
    char url[2048];
    snprintf(url,sizeof(url),"%s",j->url);
    if(url[0]) {
      char secure[2048];
      onet_secure(url,secure,sizeof(secure));
      o.progress=opds_progress_cb;
      opds_done_bytes=0;opds_total_bytes=0;
      if(onet_download(secure,j->dest,&o,&j->result) && !opds_valid_file(j->dest,j->format)) {
        DeleteFileW(j->dest);
        onet_fail(&j->result,ONET_HTTP,"下载的内容不是有效的 %s 文件（可能是网页或错误页）。",j->format);
      }
    }
  }
  PostMessageW(opds_view,OPDS_MSG_DONE,0,(LPARAM)j);
  return 0;
}
static int opds_start(opds_job *j) {
  HANDLE thread;
  if(opds_busy){free(j);return 0;}
  j->receive_ms=opds_receive_override;
  opds_busy=1;opds_cancel=0;opds_last_op=(int)j->kind;
  thread=CreateThread(NULL,0,opds_worker,j,0,NULL);
  if(!thread){opds_busy=0;free(j);opds_set_status(L"无法启动网络任务。");return 0;}
  CloseHandle(thread);opds_controls_enable();
  return 1;
}

/* ---- navigation ------------------------------------------------------- */
static opds_job *opds_new_job(opds_op kind) {
  opds_job *j=calloc(1,sizeof(*j));if(j)j->kind=kind;return j;
}
static void opds_load_url(const char *url,int use_cache,int push) {
  opds_job *j=opds_new_job(OPDS_OP_FEED);
  if(!j)return;
  snprintf(j->url,sizeof(j->url),"%s",url);j->use_cache=use_cache;
  /* History changes are applied on success so a failed load leaves it untouched. */
  j->nav=push;
  opds_set_status(L"正在加载书源目录…");
  opds_start(j);
}
static void opds_go(void) {
  wchar_t wide[2048];char *utf8;char url[2048];
  if(opds_busy)return;
  GetWindowTextW(opds_url_edit,wide,2048);
  utf8=host_utf8(wide);
  if(!utf8 || !utf8[0]){free(utf8);opds_set_status(L"请先填写书源地址（OPDS 目录 URL）。");return;}
  char trimmed[2048];snprintf(trimmed,sizeof(trimmed),"%s",utf8);free(utf8);
  char *s=trimmed;while(*s==' ')s++;
  size_t n=strlen(s);while(n && s[n-1]==' ')s[--n]=0;
  if(!_strnicmp(s,"http://",7) || !_strnicmp(s,"https://",8))snprintf(url,sizeof(url),"%s",s);
  else snprintf(url,sizeof(url),"https://%s",s);
  opds_load_url(url,1,2);
}
static void opds_search(void) {
  wchar_t wide[256];char *utf8;
  if(opds_busy)return;
  GetWindowTextW(opds_query_edit,wide,256);utf8=host_utf8(wide);
  if(!utf8 || !utf8[0]){free(utf8);opds_set_status(L"请输入要搜索的书名或作者。");return;}
  if(!opds_search_template[0] && !opds_search_description[0]){free(utf8);opds_set_status(L"请先打开一个书源；该书源是否支持搜索取决于它的目录。");return;}
  opds_job *j=opds_new_job(OPDS_OP_SEARCH);
  if(!j){free(utf8);return;}
  snprintf(j->query,sizeof(j->query),"%s",utf8);free(utf8);
  snprintf(j->search_template,sizeof(j->search_template),"%s",opds_search_template);
  snprintf(j->search_description,sizeof(j->search_description),"%s",opds_search_description);
  j->nav=1;
  opds_set_status(L"正在搜索…");
  opds_start(j);
}
static void opds_activate(int index) {
  if(opds_busy || index<0 || (size_t)index>=opds_feed.entry_count)return;
  const exr_opds_entry *e=&opds_feed.entries[index];
  if(e->download_url) {
    opds_job *j=opds_new_job(OPDS_OP_DOWNLOAD);
    if(!j)return;
    snprintf(j->url,sizeof(j->url),"%s",e->download_url);
    snprintf(j->title,sizeof(j->title),"%s",e->title ? e->title:"book");
    snprintf(j->format,sizeof(j->format),"%s",e->format ? e->format:"epub");
    opds_download_name(j->title,j->format,j->dest);
    wcscpy(opds_download_path,j->dest);
    { wchar_t *t=host_wide(j->title,strlen(j->title));wcsncpy(opds_download_title,t ? t:L"",255);free(t); }
    opds_done_bytes=0;opds_total_bytes=e->size;
    opds_set_status(L"正在下载…");
    opds_start(j);
  } else if(e->detail_url) {
    opds_load_url(e->detail_url,1,1);
  }
}
static void opds_back(void) {
  if(opds_busy || opds_depth<=0)return;
  opds_load_url(opds_stack[opds_depth-1],1,-1);
}
static void opds_next(void) {
  if(opds_busy || !opds_feed.next_url)return;
  opds_load_url(opds_feed.next_url,1,1);
}
static void opds_refresh(void) {
  if(opds_busy || !opds_url[0])return;
  opds_load_url(opds_url,0,0);
}
static void opds_finish(opds_job *j) {
  int mode=j->nav;
  onet_result r=j->result;
  if(j->kind==OPDS_OP_DOWNLOAD) {
    opds_last_result=r;
    if(r.code==ONET_OK) {
      opds_downloads_done++;
      wchar_t line[HOST_PATH+64];swprintf(line,HOST_PATH+64,L"下载完成，正在导入：%ls",opds_download_title);
      opds_set_status(line);
      opds_busy=0;
      /* Same path as the shelf's open-book button, so import adds metadata and
         cover and then opens the book. */
      g.auto_open_imported=1;opds_imports_started++;
      if(opds_visible){ShowWindow(opds_view,SW_HIDE);opds_visible=0;opds_back_to_shelf();}
      import_path(opds_download_path,0);
    } else {
      if(r.code==ONET_CANCELLED)opds_downloads_cancelled++;else opds_downloads_failed++;
      opds_busy=0;
      opds_set_status_utf8(r.code==ONET_CANCELLED ? "已取消下载。":"下载失败：",r.code==ONET_CANCELLED ? "":r.message);
    }
  } else {
    if(j->has_feed && r.code==ONET_OK) {
      opds_last_result=r;opds_last_from_cache=r.from_cache;opds_feeds_loaded++;
      if(mode==2)opds_depth=0;
      else if(mode==1 && opds_url[0] && opds_depth<OPDS_STACK)snprintf(opds_stack[opds_depth++],2048,"%s",opds_url);
      else if(mode<0 && opds_depth>0)opds_depth--;
      exr_opds_feed_free(&opds_feed);opds_feed=j->feed;memset(&j->feed,0,sizeof(j->feed));
      snprintf(opds_url,sizeof(opds_url),"%s",j->feed_url);
      if(opds_feed.search_template)snprintf(opds_search_template,sizeof(opds_search_template),"%s",opds_feed.search_template);
      if(opds_feed.search_description_url){snprintf(opds_search_description,sizeof(opds_search_description),"%s",opds_feed.search_description_url);
        if(!opds_feed.search_template)opds_search_template[0]=0;}
      if(j->found_template[0])snprintf(opds_search_template,sizeof(opds_search_template),"%s",j->found_template);
      opds_busy=0;opds_fill_list();
      { wchar_t *u=host_wide(opds_url,strlen(opds_url));SetWindowTextW(opds_url_edit,u ? u:L"");free(u); }
      if(mode==2)opds_save_source(opds_url);
      wchar_t line[256];swprintf(line,256,L"共 %zu 项%ls%ls",opds_feed.entry_count,opds_feed.next_url ? L"，可翻到下一页":L"",r.from_cache ? L"（缓存，10 分钟内不重复请求）":L"");
      opds_set_status(line);
    } else {
      opds_last_result=r;opds_busy=0;
      opds_set_status_utf8("",r.message[0] ? r.message:"加载失败。");
    }
  }
  exr_opds_feed_free(&j->feed);free(j);
  opds_busy=0;opds_controls_enable();
}

/* ---- window ----------------------------------------------------------- */
static void opds_rect_text(HDC dc,const wchar_t *text,RECT r,int size,int weight,uint32_t color,UINT flags) {
  HFONT f=sm_font(size,weight);HGDIOBJ old=SelectObject(dc,f);
  SetTextColor(dc,shell_colorref(color));SetBkMode(dc,TRANSPARENT);
  DrawTextW(dc,text,-1,&r,flags|DT_VCENTER|DT_NOPREFIX|DT_END_ELLIPSIS);SelectObject(dc,old);DeleteObject(f);
}
static void opds_paint(HDC dc) {
  RECT c;GetClientRect(opds_view,&c);
  sm_fill(dc,&c,shell_colors->layer_page);
  int pad=shell_px(24,shell_dpi);
  RECT t={pad,shell_px(14,shell_dpi),c.right/2,shell_px(54,shell_dpi)};
  opds_rect_text(dc,L"书源",t,28,600,shell_colors->text,DT_LEFT|DT_SINGLELINE);
  int bottom=c.bottom-pad;
  RECT bar_text={pad,bottom-shell_px(116,shell_dpi),c.right-pad,bottom-shell_px(94,shell_dpi)};
  RECT bar={pad,bottom-shell_px(88,shell_dpi),c.right-pad,bottom-shell_px(80,shell_dpi)};
  RECT line={pad,bottom-shell_px(72,shell_dpi),c.right-pad,bottom-shell_px(52,shell_dpi)};
  RECT head={pad,shell_px(192,shell_dpi),c.right-pad,shell_px(214,shell_dpi)};
  wchar_t text[600];
  if(opds_feed.title){wchar_t *w=host_wide(opds_feed.title,strlen(opds_feed.title));swprintf(text,600,L"当前目录：%ls",w ? w:L"");free(w);}
  else wcscpy(text,L"当前目录：（尚未打开书源）");
  opds_rect_text(dc,text,head,13,400,shell_colors->text_secondary,DT_LEFT|DT_SINGLELINE);
  if(opds_busy && opds_last_op==OPDS_OP_DOWNLOAD) {
    ULONGLONG done=opds_done_bytes,total=opds_total_bytes;
    wchar_t a[32],b[32];opds_format_size(done,a,32);opds_format_size(total,b,32);
    if(!a[0])wcscpy(a,L"0 KB");
    if(total)swprintf(text,600,L"下载中：%ls / %ls（%u%%）",a,b,(unsigned)(done>=total ? 100:done*100/total));
    else swprintf(text,600,L"下载中：%ls",a);
    opds_rect_text(dc,text,bar_text,13,400,shell_colors->text,DT_LEFT|DT_SINGLELINE);
    sm_fill(dc,&bar,shell_colors->surface3);
    if(total){RECT fill=bar;fill.right=bar.left+(LONG)((bar.right-bar.left)*(done>=total ? 1.0:(double)done/total));sm_fill(dc,&fill,shell_colors->accent);}
    else {RECT fill=bar;fill.left=bar.left+(LONG)((GetTickCount()/8)%(bar.right-bar.left));fill.right=min(bar.right,fill.left+shell_px(80,shell_dpi));sm_fill(dc,&fill,shell_colors->accent);}
  }
  opds_rect_text(dc,opds_status,line,13,400,shell_colors->text_secondary,DT_LEFT|DT_SINGLELINE);
}
static void opds_back_to_shelf(void) {
  if(sm_view){ShowWindow(sm_view,SW_SHOWNA);sm_layout();SetFocus(sm_view);}
}
static void opds_layout(void) {
  if(!opds_view || !opds_visible)return;
  RECT c;GetClientRect(shelf_panel,&c);
  SetWindowPos(opds_view,HWND_TOP,0,0,c.right,c.bottom,SWP_NOACTIVATE);
  GetClientRect(opds_view,&c);
  int pad=shell_px(24,shell_dpi),bw=shell_px(104,shell_dpi),bh=shell_px(34,shell_dpi),gap=shell_px(8,shell_dpi),bottom=c.bottom-pad;
  MoveWindow(GetDlgItem(opds_view,OPDS_ID_CLOSE),c.right-pad-shell_px(124,shell_dpi),shell_px(18,shell_dpi),shell_px(124,shell_dpi),bh,TRUE);
  MoveWindow(GetDlgItem(opds_view,OPDS_ID_URL_LABEL),pad,shell_px(60,shell_dpi),c.right-2*pad,shell_px(20,shell_dpi),TRUE);
  MoveWindow(opds_url_edit,pad,shell_px(82,shell_dpi),c.right-2*pad-bw-gap,shell_px(30,shell_dpi),TRUE);
  MoveWindow(GetDlgItem(opds_view,OPDS_ID_GO),c.right-pad-bw,shell_px(80,shell_dpi),bw,shell_px(34,shell_dpi),TRUE);
  MoveWindow(GetDlgItem(opds_view,OPDS_ID_QUERY_LABEL),pad,shell_px(120,shell_dpi),c.right-2*pad,shell_px(20,shell_dpi),TRUE);
  MoveWindow(opds_query_edit,pad,shell_px(142,shell_dpi),c.right-2*pad-bw-gap,shell_px(30,shell_dpi),TRUE);
  MoveWindow(GetDlgItem(opds_view,OPDS_ID_SEARCH),c.right-pad-bw,shell_px(140,shell_dpi),bw,shell_px(34,shell_dpi),TRUE);
  int list_top=shell_px(220,shell_dpi),list_bottom=bottom-shell_px(124,shell_dpi);
  MoveWindow(opds_list,pad,list_top,c.right-2*pad,max(shell_px(60,shell_dpi),list_bottom-list_top),TRUE);
  int y=bottom-bh;
  MoveWindow(GetDlgItem(opds_view,OPDS_ID_BACK),pad,y,bw,bh,TRUE);
  MoveWindow(GetDlgItem(opds_view,OPDS_ID_NEXT),pad+bw+gap,y,bw,bh,TRUE);
  MoveWindow(GetDlgItem(opds_view,OPDS_ID_REFRESH),pad+2*(bw+gap),y,bw,bh,TRUE);
  MoveWindow(GetDlgItem(opds_view,OPDS_ID_CANCEL),c.right-pad-bw,y,bw,bh,TRUE);
  MoveWindow(GetDlgItem(opds_view,OPDS_ID_ACTION),c.right-pad-2*bw-gap,y,bw,bh,TRUE);
}
static void opds_hide(void) {
  if(!opds_view || !opds_visible)return;
  if(opds_busy)InterlockedExchange(&opds_cancel,1);
  ShowWindow(opds_view,SW_HIDE);opds_visible=0;opds_back_to_shelf();
}
static void opds_show(void) {
  if(!opds_view || !shelf_visible)return;
  if(sm_view)ShowWindow(sm_view,SW_HIDE);
  opds_visible=1;opds_layout();ShowWindow(opds_view,SW_SHOW);opds_controls_enable();
  SetFocus(opds_url_edit);
}
static LRESULT CALLBACK opds_edit_proc(HWND w,UINT m,WPARAM wp,LPARAM lp) {
  int id=GetDlgCtrlID(w);
  if(m==WM_KEYDOWN && wp==VK_RETURN) {
    SendMessageW(opds_view,WM_COMMAND,MAKEWPARAM(id==OPDS_ID_URL ? OPDS_ID_GO:id==OPDS_ID_QUERY ? OPDS_ID_SEARCH:OPDS_ID_ACTION,BN_CLICKED),0);return 0;
  }
  if(m==WM_KEYDOWN && wp==VK_ESCAPE){opds_hide();return 0;}
  if(m==WM_CHAR && (wp=='\r' || wp==27))return 0;
  return CallWindowProcW(opds_edit_base,w,m,wp,lp);
}
static LRESULT CALLBACK opds_view_proc(HWND w,UINT m,WPARAM wp,LPARAM lp) {
  switch(m) {
    case WM_ERASEBKGND:return 1;
    case WM_PAINT:{PAINTSTRUCT ps;HDC dc=BeginPaint(w,&ps);opds_paint(dc);EndPaint(w,&ps);return 0;}
    case WM_PRINTCLIENT:opds_paint((HDC)wp);return 0;
    case WM_CTLCOLORSTATIC:case WM_CTLCOLOREDIT:case WM_CTLCOLORLISTBOX:
      SetTextColor((HDC)wp,shell_colorref(shell_colors->text));SetBkColor((HDC)wp,shell_colorref(m==WM_CTLCOLORSTATIC ? shell_colors->layer_page:shell_colors->layer_float));
      if(opds_brush)DeleteObject(opds_brush);
      opds_brush=CreateSolidBrush(shell_colorref(m==WM_CTLCOLORSTATIC ? shell_colors->layer_page:shell_colors->layer_float));return (LRESULT)opds_brush;
    case WM_DRAWITEM: {
      const DRAWITEMSTRUCT *d=(const DRAWITEMSTRUCT *)lp;wchar_t label[32];
      GetWindowTextW(d->hwndItem,label,32);
      shell_d2d_control(host_shell,d->hDC,&d->rcItem,label,shell_is_dark(),d->CtlID==OPDS_ID_ACTION ? 1:2,
        (d->itemState&ODS_SELECTED ? 2:0)|(d->itemState&ODS_FOCUS ? 4:0)|(d->itemState&ODS_DISABLED ? 8:0));
      return TRUE;
    }
    case WM_COMMAND:
      switch(LOWORD(wp)) {
        case OPDS_ID_GO:opds_go();return 0;
        case OPDS_ID_SEARCH:opds_search();return 0;
        case OPDS_ID_BACK:opds_back();return 0;
        case OPDS_ID_NEXT:opds_next();return 0;
        case OPDS_ID_REFRESH:opds_refresh();return 0;
        case OPDS_ID_ACTION:opds_activate((int)SendMessageW(opds_list,LB_GETCURSEL,0,0));return 0;
        case OPDS_ID_CANCEL:
          if(opds_busy){InterlockedExchange(&opds_cancel,1);opds_set_status(L"正在取消…");}
          return 0;
        case OPDS_ID_CLOSE:opds_hide();return 0;
        case OPDS_ID_LIST:
          if(HIWORD(wp)==LBN_DBLCLK)opds_activate((int)SendMessageW(opds_list,LB_GETCURSEL,0,0));
          else if(HIWORD(wp)==LBN_SELCHANGE)opds_controls_enable();
          return 0;
      }
      break;
    case OPDS_MSG_PROGRESS:InvalidateRect(w,NULL,FALSE);return 0;
    case OPDS_MSG_DONE:opds_finish((opds_job *)lp);return 0;
  }
  return DefWindowProcW(w,m,wp,lp);
}
static void opds_create(HWND parent) {
  HINSTANCE instance=GetModuleHandleW(NULL);WNDCLASSW type={0};
  (void)parent;
  type.lpfnWndProc=opds_view_proc;type.hInstance=instance;type.hCursor=LoadCursor(NULL,IDC_ARROW);type.lpszClassName=L"EXReaderOpds";RegisterClassW(&type);
  opds_view=CreateWindowExW(WS_EX_CONTROLPARENT,type.lpszClassName,L"书源",WS_CHILD|WS_CLIPSIBLINGS|WS_CLIPCHILDREN,0,0,0,0,shelf_panel,NULL,instance,NULL);
  CreateWindowExW(0,L"STATIC",L"书源地址（OPDS 目录，需要 https://）",WS_CHILD|WS_VISIBLE,0,0,0,0,opds_view,(HMENU)OPDS_ID_URL_LABEL,instance,NULL);
  opds_url_edit=CreateWindowExW(WS_EX_CLIENTEDGE,L"EDIT",L"",WS_CHILD|WS_VISIBLE|WS_TABSTOP|ES_AUTOHSCROLL,0,0,0,0,opds_view,(HMENU)OPDS_ID_URL,instance,NULL);
  CreateWindowExW(0,L"BUTTON",L"打开",WS_CHILD|WS_VISIBLE|WS_TABSTOP|BS_OWNERDRAW,0,0,0,0,opds_view,(HMENU)OPDS_ID_GO,instance,NULL);
  CreateWindowExW(0,L"STATIC",L"在书源中搜索（书名或作者）",WS_CHILD|WS_VISIBLE,0,0,0,0,opds_view,(HMENU)OPDS_ID_QUERY_LABEL,instance,NULL);
  opds_query_edit=CreateWindowExW(WS_EX_CLIENTEDGE,L"EDIT",L"",WS_CHILD|WS_VISIBLE|WS_TABSTOP|ES_AUTOHSCROLL,0,0,0,0,opds_view,(HMENU)OPDS_ID_QUERY,instance,NULL);
  CreateWindowExW(0,L"BUTTON",L"搜索",WS_CHILD|WS_VISIBLE|WS_TABSTOP|BS_OWNERDRAW,0,0,0,0,opds_view,(HMENU)OPDS_ID_SEARCH,instance,NULL);
  opds_list=CreateWindowExW(WS_EX_CLIENTEDGE,L"LISTBOX",L"书源条目",WS_CHILD|WS_VISIBLE|WS_TABSTOP|WS_VSCROLL|LBS_NOTIFY|LBS_NOINTEGRALHEIGHT|LBS_HASSTRINGS,0,0,0,0,opds_view,(HMENU)OPDS_ID_LIST,instance,NULL);
  const struct {int id;const wchar_t *label;} buttons[]={{OPDS_ID_BACK,L"返回上级"},{OPDS_ID_NEXT,L"下一页"},{OPDS_ID_REFRESH,L"刷新"},
    {OPDS_ID_ACTION,L"下载 / 打开"},{OPDS_ID_CANCEL,L"取消"},{OPDS_ID_CLOSE,L"返回书架"}};
  for(size_t i=0;i<sizeof(buttons)/sizeof(*buttons);i++)
    CreateWindowExW(0,L"BUTTON",buttons[i].label,WS_CHILD|WS_VISIBLE|WS_TABSTOP|BS_OWNERDRAW,0,0,0,0,opds_view,(HMENU)(INT_PTR)buttons[i].id,instance,NULL);
  HFONT font=sm_font(14,400);
  for(HWND child=GetWindow(opds_view,GW_CHILD);child;child=GetWindow(child,GW_HWNDNEXT))SendMessageW(child,WM_SETFONT,(WPARAM)font,TRUE);
  opds_edit_base=(WNDPROC)SetWindowLongPtrW(opds_url_edit,GWLP_WNDPROC,(LONG_PTR)opds_edit_proc);
  SetWindowLongPtrW(opds_query_edit,GWLP_WNDPROC,(LONG_PTR)opds_edit_proc);
  path_join(opds_source_file,HOST_PATH,g.data_dir,L"opds-source.txt");
  { FILE *f=_wfopen(opds_source_file,L"rb");char line[2048]={0};
    if(f){size_t n=fread(line,1,sizeof(line)-1,f);fclose(f);line[n]=0;}
    if(!line[0])snprintf(line,sizeof(line),"https://www.gutenberg.org/ebooks.opds/");
    { wchar_t *w=host_wide(line,strlen(line));SetWindowTextW(opds_url_edit,w ? w:L"");free(w); }
  }
  opds_set_status(L"填写书源地址后点“打开”。支持 OPDS 1.x（Atom）目录，例如 Project Gutenberg。");
}
