/* SPDX-License-Identifier: MIT */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <commdlg.h>
#include <shellapi.h>
#include <exreader.h>
#include <math.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

typedef struct {
  exr_document *document;
  exr_fixed_document *fixed;
  exr_pager *pager;
  wchar_t file[4096];
} reader_book;
typedef struct {
  exr_bitmap bitmap;
  uint32_t *dib;
  wchar_t *text;
  size_t page;
} reader_frame;
typedef struct {
  reader_book *book;
  reader_frame frame;
  wchar_t file[4096];
  size_t page;
  int opening;
  exr_status status;
} request;

static exr_font *font;
static reader_book *book;
static reader_frame frame;
static HWND window, buttons[4], position;
static int busy, closing;
static wchar_t settings[4096];
enum { OPEN=101, PREVIOUS, NEXT, SELECT_TEXT, COMPLETE=WM_APP+1 };

static char *utf8(const wchar_t *value) {
  int size=WideCharToMultiByte(CP_UTF8,0,value,-1,NULL,0,NULL,NULL);
  char *out=size>0 ? malloc((size_t)size) : NULL;
  if(out && !WideCharToMultiByte(CP_UTF8,0,value,-1,out,size,NULL,NULL)) { free(out);out=NULL; }
  return out;
}
static wchar_t *wide(const char *value,size_t size) {
  int n;
  wchar_t *out;
  if(size>INT_MAX) return NULL;
  n=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,value,(int)size,NULL,0);
  if(!n && size) return NULL;
  out=calloc((size_t)n+1,sizeof(*out));
  if(out && n && !MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,value,(int)size,out,n)) {
    free(out);return NULL;
  }
  return out;
}
static void close_book(reader_book *value) {
  if(!value) return;
  exr_pager_free(value->pager);exr_fixed_free(value->fixed);
  exr_document_free(value->document);free(value);
}
static void close_frame(reader_frame *value) {
  exr_bitmap_free(&value->bitmap);free(value->dib);free(value->text);
  memset(value,0,sizeof(*value));
}
static exr_status open_book(const wchar_t *path,reader_book **out) {
  WIN32_FILE_ATTRIBUTE_DATA attributes;
  reader_book *value=NULL;
  exr_fixed_open_options fixed={0};
  exr_layout_config config=exr_layout_config_defaults();
  exr_error error={0};exr_status status;
  char *name=NULL;const wchar_t *extension=wcsrchr(path,L'.');
  *out=NULL;
  if(wcslen(path)>=4096) return EXR_LIMIT;
  if(!GetFileAttributesExW(path,GetFileExInfoStandard,&attributes)) return EXR_IO;
  if(attributes.nFileSizeHigh || !attributes.nFileSizeLow || attributes.nFileSizeLow>32u*1024u*1024u) return EXR_LIMIT;
  name=utf8(path);value=calloc(1,sizeof(*value));
  if(!name || !value) { status=EXR_MEMORY;goto done; }
  wcscpy(value->file,path);
  if(extension && (!_wcsicmp(extension,L".pdf") || !_wcsicmp(extension,L".cbz"))) {
    fixed.struct_size=sizeof(fixed);fixed.fallback_font=font;
    status=exr_fixed_open(name,&fixed,&value->fixed,&error);
  } else {
    status=exr_document_open(name,&value->document,&error);
    config.page=(exr_layout_options){720,1040,36,28,1.5f,10};
    if(status==EXR_OK) status=exr_pager_create(value->document,font,&config,&value->pager,&error);
  }
done:
  free(name);
  if(status!=EXR_OK) close_book(value);
  else *out=value;
  return status;
}
static exr_status render(reader_book *value,size_t index,reader_frame *out) {
  exr_error error={0};exr_status status;
  exr_fixed_text *text=NULL;
  const char *bytes="";size_t size=0;
  memset(out,0,sizeof(*out));out->page=index;
  if(value->fixed) {
    size_t count=0;
    const exr_fixed_page *pages=exr_fixed_pages(value->fixed,&count);
    double width,height,scale;
    if(index>=count) return EXR_ARGUMENT;
    width=(pages[index].geometry.bounds[2]-pages[index].geometry.bounds[0])*pages[index].geometry.unit_scale;
    height=(pages[index].geometry.bounds[3]-pages[index].geometry.bounds[1])*pages[index].geometry.unit_scale;
    if(!(width>0) || !(height>0) || !isfinite(width) || !isfinite(height)) return EXR_FORMAT;
    scale=fmin(1,1440/fmax(width,height));
    status=exr_fixed_render(value->fixed,index,scale,NULL,&out->bitmap,&error);
    if(status==EXR_OK && exr_fixed_load_text(value->fixed,index,NULL,&text,&error)==EXR_OK)
      bytes=exr_fixed_text_string(text,&size);
  } else {
    const exr_layout *layout=NULL;
    status=exr_pager_get(value->pager,index,&layout,&error);
    if(status==EXR_OK) {
      const exr_page *page=exr_layout_pages(layout,NULL);
      const char *all=exr_document_text(value->document,&size);
      if(!page || page->start>page->end || page->end>size) status=EXR_FORMAT;
      else {
        bytes=all+page->start;size=page->end-page->start;
        status=exr_render_page_color(layout,exr_layout_font(layout),0,&out->bitmap,&error);
      }
    }
  }
  if(status==EXR_OK) {
    size_t count=(size_t)out->bitmap.width*out->bitmap.height;
    if(out->bitmap.channels!=4 || count>SIZE_MAX/sizeof(*out->dib)) status=EXR_FORMAT;
    else {
      out->text=wide(bytes ? bytes : "",size);
      out->dib=malloc(count*sizeof(*out->dib));
      if(!out->text || !out->dib) status=EXR_MEMORY;
      else for(size_t y=0;y<out->bitmap.height;y++) for(size_t x=0;x<out->bitmap.width;x++) {
        const unsigned char *p=out->bitmap.pixels+y*out->bitmap.stride+x*4;
        unsigned a=p[3],r=(p[0]*a+255*(255-a)+127)/255;
        unsigned g=(p[1]*a+255*(255-a)+127)/255,b=(p[2]*a+255*(255-a)+127)/255;
        out->dib[y*out->bitmap.width+x]=(r<<16)|(g<<8)|b;
      }
    }
  }
  exr_fixed_text_free(text);
  if(status!=EXR_OK) close_frame(out);
  return status;
}
static void bookmark_key(const wchar_t *path,wchar_t out[32]) {
  uint64_t hash=UINT64_C(14695981039346656037);
  while(*path) { hash^=(uint16_t)*path++;hash*=UINT64_C(1099511628211); }
  swprintf(out,32,L"%016llx",(unsigned long long)hash);
}
static void save_position(void) {
  wchar_t key[32],number[32];
  if(!book || !settings[0]) return;
  bookmark_key(book->file,key);
  swprintf(number,32,L"%llu",(unsigned long long)frame.page);
  WritePrivateProfileStringW(L"Positions",key,number,settings);
}
static DWORD WINAPI work(void *context) {
  request *r=context;
  reader_book *target=r->book;
  if(r->opening) r->status=open_book(r->file,&target);
  else r->status=EXR_OK;
  if(r->status==EXR_OK) {
    r->status=render(target,r->page,&r->frame);
    if(r->opening && r->status==EXR_ARGUMENT) r->status=render(target,0,&r->frame);
  }
  if(r->opening) {
    if(r->status==EXR_OK) r->book=target;
    else { close_book(target);r->book=NULL; }
  }
  if(!PostMessageW(window,COMPLETE,0,(LPARAM)r)) {
    close_frame(&r->frame);if(r->opening) close_book(r->book);free(r);
  }
  return 0;
}
static void load(const wchar_t *path,size_t page,int opening) {
  request *r;HANDLE thread;
  if(busy || (!opening && !book)) return;
  r=calloc(1,sizeof(*r));if(!r) return;
  r->opening=opening;r->book=book;r->page=page;
  if(path) {
    wchar_t key[32];
    if(wcslen(path)>=4096) { free(r);return; }
    wcscpy(r->file,path);bookmark_key(path,key);
    r->page=(size_t)GetPrivateProfileIntW(L"Positions",key,0,settings);
  }
  busy=1;
  for(int i=0;i<4;i++) EnableWindow(buttons[i],FALSE);
  SetWindowTextW(position,L"正在打开…");
  thread=CreateThread(NULL,0,work,r,0,NULL);
  if(thread) CloseHandle(thread);
  else { busy=0;free(r);for(int i=0;i<4;i++) EnableWindow(buttons[i],TRUE); }
}
static void select_text(void) {
  HWND dialog,edit;
  if(!frame.text || !frame.text[0]) { MessageBoxW(window,L"本页没有可选文字。",L"EXReader",MB_OK);return; }
  dialog=CreateWindowExW(WS_EX_DLGMODALFRAME,L"STATIC",L"本页文字 — 可选择复制",
    WS_OVERLAPPEDWINDOW|WS_VISIBLE,120,120,600,460,window,NULL,GetModuleHandleW(NULL),NULL);
  edit=CreateWindowExW(WS_EX_CLIENTEDGE,L"EDIT",frame.text,WS_CHILD|WS_VISIBLE|WS_VSCROLL|
    ES_MULTILINE|ES_AUTOVSCROLL|ES_READONLY,8,8,565,400,dialog,NULL,GetModuleHandleW(NULL),NULL);
  SendMessageW(edit,WM_SETFONT,(WPARAM)GetStockObject(DEFAULT_GUI_FONT),TRUE);
  SetFocus(edit);
}
static LRESULT CALLBACK procedure(HWND hwnd,UINT message,WPARAM wparam,LPARAM lparam) {
  switch(message) {
    case WM_CREATE:
      window=hwnd;
      buttons[0]=CreateWindowW(L"BUTTON",L"打开文件",WS_CHILD|WS_VISIBLE,10,10,95,30,hwnd,(HMENU)(INT_PTR)OPEN,NULL,NULL);
      buttons[1]=CreateWindowW(L"BUTTON",L"上一页",WS_CHILD|WS_VISIBLE,115,10,95,30,hwnd,(HMENU)(INT_PTR)PREVIOUS,NULL,NULL);
      buttons[2]=CreateWindowW(L"BUTTON",L"下一页",WS_CHILD|WS_VISIBLE,220,10,95,30,hwnd,(HMENU)(INT_PTR)NEXT,NULL,NULL);
      buttons[3]=CreateWindowW(L"BUTTON",L"选文",WS_CHILD|WS_VISIBLE,325,10,95,30,hwnd,(HMENU)(INT_PTR)SELECT_TEXT,NULL,NULL);
      position=CreateWindowW(L"STATIC",L"打开一本书开始阅读",WS_CHILD|WS_VISIBLE,10,46,600,24,hwnd,NULL,NULL,NULL);
      return 0;
    case WM_COMMAND:
      if(LOWORD(wparam)==OPEN) {
        wchar_t path[4096]=L"";OPENFILENAMEW file={0};
        file.lStructSize=sizeof(file);file.hwndOwner=hwnd;file.lpstrFile=path;file.nMaxFile=4096;
        file.lpstrFilter=L"电子书\0*.epub;*.pdf;*.cbz;*.txt;*.fb2;*.html;*.rtf;*.docx;*.mobi;*.azw3\0所有文件\0*.*\0";
        file.Flags=OFN_FILEMUSTEXIST|OFN_NOCHANGEDIR;
        if(GetOpenFileNameW(&file)) { save_position();load(path,0,1); }
      } else if(LOWORD(wparam)==PREVIOUS && frame.page) load(NULL,frame.page-1,0);
      else if(LOWORD(wparam)==NEXT) load(NULL,frame.page+1,0);
      else if(LOWORD(wparam)==SELECT_TEXT) select_text();
      return 0;
    case COMPLETE: {
      request *r=(request *)lparam;wchar_t label[80];
      if(r->status==EXR_OK) {
        if(r->opening) { close_book(book);book=r->book;SetWindowTextW(hwnd,book->file); }
        close_frame(&frame);frame=r->frame;save_position();InvalidateRect(hwnd,NULL,TRUE);
      } else MessageBoxW(hwnd,r->status==EXR_ARGUMENT ? L"已到最后一页。" : L"无法打开或显示该文件，请检查文件格式。",L"EXReader",MB_OK);
      free(r);busy=0;
      for(int i=0;i<4;i++) EnableWindow(buttons[i],TRUE);
      swprintf(label,80,L"第 %llu 页",(unsigned long long)frame.page+1);SetWindowTextW(position,label);
      if(closing) DestroyWindow(hwnd);
      return 0;
    }
    case WM_PAINT: {
      PAINTSTRUCT paint;HDC dc=BeginPaint(hwnd,&paint);RECT area;GetClientRect(hwnd,&area);
      FillRect(dc,&area,(HBRUSH)GetStockObject(WHITE_BRUSH));
      if(frame.dib) {
        BITMAPINFO info={0};double scale=fmin((area.right-20)/(double)frame.bitmap.width,(area.bottom-88)/(double)frame.bitmap.height);
        if(scale>0) {
          int width=(int)(frame.bitmap.width*scale),height=(int)(frame.bitmap.height*scale);
          info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);info.bmiHeader.biWidth=(LONG)frame.bitmap.width;
          info.bmiHeader.biHeight=-(LONG)frame.bitmap.height;info.bmiHeader.biPlanes=1;info.bmiHeader.biBitCount=32;info.bmiHeader.biCompression=BI_RGB;
          SetStretchBltMode(dc,HALFTONE);
          StretchDIBits(dc,(area.right-width)/2,78,width,height,0,0,(int)frame.bitmap.width,(int)frame.bitmap.height,frame.dib,&info,DIB_RGB_COLORS,SRCCOPY);
        }
      }
      EndPaint(hwnd,&paint);return 0;
    }
    case WM_SIZE: InvalidateRect(hwnd,NULL,TRUE);return 0;
    case WM_CLOSE: if(busy) closing=1;else DestroyWindow(hwnd);return 0;
    case WM_DESTROY: save_position();PostQuitMessage(0);return 0;
  }
  return DefWindowProcW(hwnd,message,wparam,lparam);
}
static int selftest(wchar_t **argv,int argc) {
  reader_book *r=NULL;reader_frame a={0},b={0},again={0};exr_error error={0};
  char *name=NULL,*output=NULL;FILE *report=NULL;unsigned checks=0;int result=1;
#define CHECK(value) do { if(!(value)) goto done;checks++; } while(0)
  if(argc!=7) return 2;
  name=utf8(argv[2]);CHECK(name);CHECK(exr_font_open(name,&font,&error)==EXR_OK);free(name);name=NULL;
  CHECK(open_book(argv[3],&r)==EXR_OK);CHECK(r && r->pager);
  CHECK(render(r,0,&a)==EXR_OK);CHECK(a.bitmap.width==720);CHECK(a.bitmap.height==1040);
  CHECK(a.bitmap.channels==4);CHECK(a.dib && a.text && a.text[0]);CHECK(a.bitmap.stride>=a.bitmap.width*4);
  output=utf8(argv[6]);CHECK(output);CHECK(exr_bitmap_write_png(&a.bitmap,output,&error)==EXR_OK);
  CHECK(render(r,1,&b)==EXR_OK);CHECK(b.page==1);close_frame(&b);
  CHECK(render(r,0,&again)==EXR_OK);CHECK(a.bitmap.stride==again.bitmap.stride);
  CHECK(!memcmp(a.bitmap.pixels,again.bitmap.pixels,(size_t)a.bitmap.stride*a.bitmap.height));
  CHECK(!wcscmp(a.text,again.text));close_frame(&again);
  close_book(r);r=NULL;
  CHECK(a.bitmap.pixels && a.text[0]);close_frame(&a);
  CHECK(open_book(argv[4],&r)==EXR_OK);CHECK(r && r->fixed);
  CHECK(render(r,0,&a)==EXR_OK);CHECK(a.bitmap.width>0 && a.bitmap.height>0);
  CHECK(a.bitmap.width<=1440 && a.bitmap.height<=1440);CHECK(a.bitmap.channels==4 && a.dib);
  report=_wfopen(argv[5],L"wb");CHECK(report);
  fprintf(report,"{\n  \"schema\": 1, \"passed\": true, \"platform\": \"Windows\", \"checks\": %u, \"engine_version\": \"%s\"\n}\n",checks,exr_version());
  { int closed=fclose(report);report=NULL;CHECK(!closed); }result=0;
done:
  if(report) fclose(report);
  close_frame(&a);close_frame(&b);close_frame(&again);close_book(r);exr_font_free(font);font=NULL;
  free(name);free(output);return result;
#undef CHECK
}
int WINAPI WinMain(HINSTANCE instance,HINSTANCE previous,LPSTR command,int show) {
  int argc=0,result=1;wchar_t **argv=CommandLineToArgvW(GetCommandLineW(),&argc);
  wchar_t font_path[4096],sample[4096],*separator;WNDCLASSW type={0};MSG message;exr_error error={0};char *path;
  (void)previous;(void)command;
  if(!argv) return 2;
  if(argc>1 && !wcscmp(argv[1],L"--self-test")) { result=selftest(argv,argc);LocalFree(argv);return result; }
  if(!GetModuleFileNameW(NULL,font_path,4000)) goto done;
  separator=wcsrchr(font_path,L'\\');if(!separator) goto done;separator[1]=0;
  wcscpy(sample,font_path);wcscat(sample,L"Sample.epub");wcscat(font_path,L"Reader.otf");
  path=utf8(argc>2 ? argv[2] : font_path);if(!path) goto done;
  result=exr_font_open(path,&font,&error);free(path);
  if(result!=EXR_OK) { MessageBoxW(NULL,L"找不到阅读字体，请保留安装包内的 Reader.otf 文件。",L"EXReader",MB_OK);goto done; }
  result=1;
  if(GetEnvironmentVariableW(L"LOCALAPPDATA",settings,3900)) {
    wcscat(settings,L"\\EXReaderHost");CreateDirectoryW(settings,NULL);wcscat(settings,L"\\reader.ini");
  }
  type.lpfnWndProc=procedure;type.hInstance=instance;type.lpszClassName=L"EXReaderHost";
  type.hCursor=LoadCursor(NULL,IDC_ARROW);type.hbrBackground=(HBRUSH)GetStockObject(WHITE_BRUSH);
  if(!RegisterClassW(&type)) goto done;
  window=CreateWindowW(type.lpszClassName,L"EXReader",WS_OVERLAPPEDWINDOW,CW_USEDEFAULT,CW_USEDEFAULT,800,1000,NULL,NULL,instance,NULL);
  if(!window) goto done;
  ShowWindow(window,show);UpdateWindow(window);load(argc>1 ? argv[1] : sample,0,1);
  while(GetMessageW(&message,NULL,0,0)>0) { TranslateMessage(&message);DispatchMessageW(&message); }
  result=0;
done:
  close_frame(&frame);close_book(book);exr_font_free(font);LocalFree(argv);return result;
}
