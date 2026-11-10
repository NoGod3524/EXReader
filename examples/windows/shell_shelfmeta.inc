/* SPDX-License-Identifier: MIT */
/* Shelf organisation layer: metadata overrides, series, tags and reading
   statistics. UI-owned; books are keyed by content SHA-256 (the annotation
   identity) and every byte lives in %APPDATA%\EXReader\shelf.json.
   Organisation/statistics are child views of the recent-books shelf. The
   shelf flow owns leaving, opening, progress saving and anchor restoration.

   Reading-time rule (sm_tick):
   - a book counts as "being read" while it is open on the reading screen,
     the shelf overlay is hidden and the main window is the foreground window;
   - every page turn, wheel scroll or open is activity;
   - time is credited only up to SM_IDLE_MS (30 s) after the last activity,
     so a still window stops counting 30 s after its last page turn;
   - focus loss, opening the shelf, switching books and closing stop it. */
#define SM_VERSION 1
#define SM_IDLE_MS 30000ULL
#define SM_SAVE_MS 60000ULL
#define SM_MAX_TAGS 32
typedef struct {
  char sha[65];
  char *title,*author,*series,*cover;
  double series_index; int has_index;
  char *tags[SM_MAX_TAGS]; int tag_count;
  uint64_t read_ms,opens,last_ms,turns;
  uint64_t page,page_count,part,part_count;
  double progress;
} sm_entry;
typedef struct { char date[11]; uint64_t ms; } sm_day;
typedef struct { int64_t id; char sha[65]; } sm_ident;
static sm_entry *sm_entries; static int sm_count;
static sm_day *sm_days; static int sm_day_count;
static sm_ident *sm_ids; static int sm_id_count;
static wchar_t sm_path[HOST_PATH],sm_dir[HOST_PATH];
static int sm_loaded,sm_writable=1,sm_dirty,sm_fail_next,sm_saves,sm_save_failures;
static HWND sm_view,sm_edit_panel;
static int sm_requested=-1;
static int sm_mode; /* 0 shelf, 1 statistics */
static int sm_list,sm_filter=-1; /* -1 all, -2 untagged, n tag index */
static int sm_scroll,sm_content_h,sm_hot=-1;
static int64_t sm_clock_offset;
static uint64_t sm_last_tick,sm_last_activity,sm_last_save;
static int sm_foreground,sm_reading_book=-1;
static int sm_edit_book=-1,sm_edit_cover_clear;
static wchar_t sm_edit_cover[HOST_PATH];
static HBRUSH sm_edit_brush;
static void sm_hide(void);
static void sm_recent(void);
typedef struct { RECT r; int kind,arg; } sm_hit;
enum { SM_HIT_BOOK=1,SM_HIT_TAG,SM_HIT_GRID,SM_HIT_LIST,SM_HIT_STATS,SM_HIT_SHELF,SM_HIT_BACK,SM_HIT_IMPORT };
static sm_hit sm_hits[512]; static int sm_hit_count;
static char *sm_tags[256]; static int sm_tag_total;
typedef struct { int book; HBITMAP bitmap; int w,h; char *path; } sm_cover_cache;
static sm_cover_cache sm_covers[64]; static int sm_cover_count;
static HFONT sm_cover_font[2];

/* ---- clock --------------------------------------------------------- */
static uint64_t sm_frozen_base; /* acceptance only: a frozen base makes the clock purely virtual */
static uint64_t sm_now(void) { return (sm_frozen_base ? sm_frozen_base:annot_time())+(uint64_t)sm_clock_offset; }
static void sm_date(uint64_t ms,char out[11]) {
  ULARGE_INTEGER v;FILETIME utc,local;SYSTEMTIME st;
  v.QuadPart=ms*10000+116444736000000000ULL;utc.dwLowDateTime=v.LowPart;utc.dwHighDateTime=v.HighPart;
  FileTimeToLocalFileTime(&utc,&local);FileTimeToSystemTime(&local,&st);
  char tmp[32];snprintf(tmp,sizeof(tmp),"%04u-%02u-%02u",st.wYear%10000u,st.wMonth%100u,st.wDay%100u);memcpy(out,tmp,10);out[10]=0;
}
static int sm_day_index(const char *date) {
  /* days since 1970-01-01 for a civil YYYY-MM-DD (Howard Hinnant's algorithm) */
  int y=atoi(date),m=atoi(date+5),d=atoi(date+8);y-=m<=2;
  int era=(y>=0?y:y-399)/400;unsigned yoe=(unsigned)(y-era*400);
  unsigned doy=(153*(m+(m>2?-3:9))+2)/5+d-1,doe=yoe*365+yoe/4-yoe/100+doy;
  return era*146097+(int)doe-719468;
}

/* ---- entries ------------------------------------------------------- */
static void sm_entry_free(sm_entry *e) {
  free(e->title);free(e->author);free(e->series);free(e->cover);
  for(int i=0;i<e->tag_count;i++)free(e->tags[i]);
  memset(e,0,sizeof(*e));
}
static int sm_entry_copy(sm_entry *out,const sm_entry *in) {
  *out=*in;out->title=out->author=out->series=out->cover=NULL;out->tag_count=0;
  int ok=1;
#define SM_DUP(f) if(in->f && !(out->f=host_strdup(in->f)))ok=0;
  SM_DUP(title)SM_DUP(author)SM_DUP(series)SM_DUP(cover)
#undef SM_DUP
  for(int i=0;i<in->tag_count;i++) if((out->tags[i]=host_strdup(in->tags[i])))out->tag_count++;else ok=0;
  if(!ok)sm_entry_free(out);
  return ok;
}
static int sm_find(const char *sha) {
  for(int i=0;i<sm_count;i++) if(!strcmp(sm_entries[i].sha,sha))return i;
  return -1;
}
static int sm_get(const char *sha) {
  int i=sm_find(sha);if(i>=0)return i;
  sm_entry *next=realloc(sm_entries,((size_t)sm_count+1)*sizeof(*next));if(!next)return -1;
  sm_entries=next;memset(&sm_entries[sm_count],0,sizeof(sm_entry));
  snprintf(sm_entries[sm_count].sha,65,"%s",sha);return sm_count++;
}
static const char *sm_id_sha(int64_t id) {
  for(int i=0;i<sm_id_count;i++) if(sm_ids[i].id==id)return sm_ids[i].sha;
  char sha[65];if(id<=0 || !shell_content_identity(id,sha))return NULL;
  sm_ident *next=realloc(sm_ids,((size_t)sm_id_count+1)*sizeof(*next));if(!next)return NULL;
  sm_ids=next;sm_ids[sm_id_count].id=id;memcpy(sm_ids[sm_id_count].sha,sha,65);
  return sm_ids[sm_id_count++].sha;
}
static int sm_book_entry(size_t shelf) {
  if(shelf>=g.shelf_count)return -1;
  const char *sha=sm_id_sha(g.shelf[shelf].id);return sha ? sm_get(sha):-1;
}
static const char *sm_title(size_t shelf) {
  int e=sm_book_entry(shelf);
  if(e>=0 && sm_entries[e].title)return sm_entries[e].title;
  return g.shelf[shelf].title && g.shelf[shelf].title[0] ? g.shelf[shelf].title:"未命名";
}
static const char *sm_author(size_t shelf) {
  int e=sm_book_entry(shelf);
  if(e>=0 && sm_entries[e].author)return sm_entries[e].author;
  if(g.shelf[shelf].author && g.shelf[shelf].author[0])return g.shelf[shelf].author;
  shelf_book *b=shelf_find(g.shelf[shelf].id);
  return b && b->author && *b->author ? b->author:"未知作者";
}

/* ---- persistence --------------------------------------------------- */
static void sm_json_str(cv_text *j,const char *key,const char *v) { annot_json_string(j,key,v); }
static void sm_serialize(cv_text *j) {
  cv_text_format(j,"{\"version\":%d,\"books\":[\n",SM_VERSION);
  for(int i=0;i<sm_count;i++) {
    sm_entry *e=&sm_entries[i];if(i)cv_text_string(j,",\n");
    cv_text_string(j,"{\"sha256\":");cv_text_json(j,e->sha);cv_text_string(j,",");
    sm_json_str(j,"title",e->title);cv_text_string(j,",");sm_json_str(j,"author",e->author);cv_text_string(j,",");
    sm_json_str(j,"series",e->series);cv_text_string(j,",\"series_index\":");
    if(e->has_index)cv_text_format(j,"%.6g",e->series_index);else cv_text_string(j,"null");
    cv_text_string(j,",\"tags\":[");
    for(int t=0;t<e->tag_count;t++){if(t)cv_text_string(j,",");cv_text_json(j,e->tags[t]);}
    cv_text_string(j,"],");sm_json_str(j,"cover",e->cover);
    cv_text_format(j,",\"stats\":{\"read_ms\":%llu,\"opens\":%llu,\"last_read_ms\":%llu,\"page_turns\":%llu,"
      "\"page\":%llu,\"page_count\":%llu,\"part\":%llu,\"part_count\":%llu,\"progress\":%.4f}}",
      (unsigned long long)e->read_ms,(unsigned long long)e->opens,(unsigned long long)e->last_ms,(unsigned long long)e->turns,
      (unsigned long long)e->page,(unsigned long long)e->page_count,(unsigned long long)e->part,(unsigned long long)e->part_count,e->progress);
  }
  cv_text_string(j,"\n],\"days\":[");
  for(int i=0;i<sm_day_count;i++) {
    if(i)cv_text_string(j,",");
    cv_text_string(j,"{\"date\":");cv_text_json(j,sm_days[i].date);cv_text_format(j,",\"read_ms\":%llu}",(unsigned long long)sm_days[i].ms);
  }
  cv_text_format(j,"],\"view\":\"%s\"",sm_list ? "list":"grid");
  /* Read on every write: style/dictionary settings may have changed since load. */
  int valid;cv_json *root=style_shelf_read(&valid);
  if(!valid)j->failed=1;
  if(root)for(size_t i=0;i<root->count;i++) {
    const char *key=root->keys[i];
    if(!strcmp(key,"version") || !strcmp(key,"books") || !strcmp(key,"days") || !strcmp(key,"view"))continue;
    cv_text_string(j,",");cv_text_json(j,key);cv_text_string(j,":");style_json_copy(j,root->items[i]);
  }
  cv_json_free(root);cv_text_string(j,"}\n");
}
static int sm_save(void) {
  if(!sm_writable)return 0;
  cv_text json={0};sm_serialize(&json);wchar_t temp[HOST_PATH];
  swprintf(temp,HOST_PATH,L"%ls.tmp",sm_path);
  HANDLE file=INVALID_HANDLE_VALUE;int ok=0;DWORD written=0;
  if(sm_fail_next){sm_fail_next=0;goto done;}
  if(json.failed || json.size>32*1024*1024)goto done;
  file=CreateFileW(temp,GENERIC_WRITE,0,NULL,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);
  if(file==INVALID_HANDLE_VALUE)goto done;
  ok=WriteFile(file,json.data,(DWORD)json.size,&written,NULL) && written==json.size && FlushFileBuffers(file);
  if(!CloseHandle(file))ok=0;
  file=INVALID_HANDLE_VALUE;
  if(ok)ok=MoveFileExW(temp,sm_path,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH)!=0;
done:
  if(file!=INVALID_HANDLE_VALUE)CloseHandle(file);
  if(!ok){DeleteFileW(temp);sm_save_failures++;}else{sm_saves++;sm_dirty=0;sm_last_save=sm_now();}
  cv_text_free(&json);return ok;
}
static int sm_jstr(const cv_json *o,const char *key,char **out) {
  const cv_json *v=cv_json_get(o,key);*out=NULL;
  if(!v || v->type==CV_JSON_NULL)return 1;
  if(v->type!=CV_JSON_STRING || strlen(v->string)>65536)return 0;
  return (*out=host_strdup(v->string))!=NULL;
}
static int sm_juint(const cv_json *o,const char *key,uint64_t *out) {
  const cv_json *v=cv_json_get(o,key);*out=0;
  if(!v)return 1;
  if(v->type!=CV_JSON_NUMBER || !v->integral || v->integer<0)return 0;
  *out=(uint64_t)v->integer;return 1;
}
static int sm_parse(const char *bytes,size_t size) {
  char *error=NULL;cv_json *root=cv_json_parse(bytes,size,&error);free(error);
  const cv_json *version=cv_json_get(root,"version"),*books=cv_json_get(root,"books"),*days=cv_json_get(root,"days"),*view=cv_json_get(root,"view");
  int ok=root && root->type==CV_JSON_OBJECT &&
    (!version || (version->type==CV_JSON_NUMBER && version->integral && version->integer>=1 && version->integer<=SM_VERSION)) &&
    (!books || (books->type==CV_JSON_ARRAY && books->count<=100000)) &&
    (!days || (days->type==CV_JSON_ARRAY && days->count<=100000));
  sm_entry *items=ok && books && books->count ? calloc(books->count,sizeof(*items)):NULL;
  size_t count=ok && books ? books->count:0;
  if(count && !items)ok=0;
  for(size_t i=0;ok && i<count;i++) {
    const cv_json *o=books->items[i],*sha=cv_json_get(o,"sha256"),*idx=cv_json_get(o,"series_index"),*tags=cv_json_get(o,"tags"),
      *st=cv_json_get(o,"stats"),*pr=cv_json_get(st,"progress");
    sm_entry *e=&items[i];
    ok=o && o->type==CV_JSON_OBJECT && sha && sha->type==CV_JSON_STRING && strlen(sha->string)==64 &&
      sm_jstr(o,"title",&e->title) && sm_jstr(o,"author",&e->author) && sm_jstr(o,"series",&e->series) && sm_jstr(o,"cover",&e->cover) &&
      (!tags || (tags->type==CV_JSON_ARRAY && tags->count<=SM_MAX_TAGS));
    if(!ok)break;
    memcpy(e->sha,sha->string,65);
    if(idx && idx->type==CV_JSON_NUMBER){e->has_index=1;e->series_index=idx->number;}
    for(size_t t=0;ok && tags && t<tags->count;t++) {
      ok=tags->items[t]->type==CV_JSON_STRING && (e->tags[t]=host_strdup(tags->items[t]->string))!=NULL;
      if(ok)e->tag_count++;
    }
    if(ok && st)ok=sm_juint(st,"read_ms",&e->read_ms) && sm_juint(st,"opens",&e->opens) && sm_juint(st,"last_read_ms",&e->last_ms) &&
      sm_juint(st,"page_turns",&e->turns) && sm_juint(st,"page",&e->page) && sm_juint(st,"page_count",&e->page_count) &&
      sm_juint(st,"part",&e->part) && sm_juint(st,"part_count",&e->part_count);
    if(ok && pr && pr->type==CV_JSON_NUMBER)e->progress=pr->number;
  }
  sm_day *dl=ok && days && days->count ? calloc(days->count,sizeof(*dl)):NULL;
  size_t dc=ok && days ? days->count:0;
  if(dc && !dl)ok=0;
  for(size_t i=0;ok && i<dc;i++) {
    const cv_json *date=cv_json_get(days->items[i],"date");
    ok=date && date->type==CV_JSON_STRING && strlen(date->string)==10 && sm_juint(days->items[i],"read_ms",&dl[i].ms);
    if(ok)memcpy(dl[i].date,date->string,11);
  }
  if(ok && view && view->type==CV_JSON_STRING)sm_list=!strcmp(view->string,"list");
  cv_json_free(root);
  if(!ok){for(size_t i=0;i<count;i++)sm_entry_free(&items[i]);free(items);free(dl);return 0;}
  sm_entries=items;sm_count=(int)count;sm_days=dl;sm_day_count=(int)dc;return 1;
}
static void sm_load(void) {
  if(sm_loaded)return;
  sm_loaded=1;
  shell_shelf_path(sm_path);
  wcscpy(sm_dir,sm_path);wchar_t *slash=wcsrchr(sm_dir,L'\\');if(slash)*slash=0;
  if(!ensure_directory(sm_dir)){sm_writable=0;return;}
  HANDLE file=CreateFileW(sm_path,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,NULL);
  if(file==INVALID_HANDLE_VALUE){sm_writable=GetLastError()==ERROR_FILE_NOT_FOUND;return;}
  LARGE_INTEGER size;DWORD got=0;char *bytes=NULL;sm_writable=0;
  if(GetFileSizeEx(file,&size) && size.QuadPart>0 && size.QuadPart<=32*1024*1024) {
    bytes=malloc((size_t)size.QuadPart+1);
    if(bytes && ReadFile(file,bytes,(DWORD)size.QuadPart,&got,NULL) && got==size.QuadPart){bytes[got]=0;sm_writable=sm_parse(bytes,got);}
  }
  free(bytes);CloseHandle(file);
  if(!sm_writable)set_status(L"shelf.json 无法解析或版本不支持；原文件已保留，书架信息暂停写入。");
}

/* ---- statistics ---------------------------------------------------- */
static void sm_credit(int e,uint64_t ms,uint64_t at) {
  if(e<0 || !ms)return;
  sm_entries[e].read_ms+=ms;sm_entries[e].last_ms=at;sm_dirty=1;
  char date[11];sm_date(at,date);
  for(int i=0;i<sm_day_count;i++) if(!strcmp(sm_days[i].date,date)){sm_days[i].ms+=ms;return;}
  sm_day *next=realloc(sm_days,((size_t)sm_day_count+1)*sizeof(*next));if(!next)return;
  sm_days=next;memcpy(sm_days[sm_day_count].date,date,11);sm_days[sm_day_count++].ms=ms;
}
static int sm_is_reading(void) {
  return sm_reading_book>=0 && g.has_current && g.frame.valid && sm_foreground && shell_active &&
    !shelf_visible && !shelf_exit_pending && !shelf_requested &&
    !(sm_view && IsWindowVisible(sm_view));
}
static void sm_tick(void) {
  uint64_t now=sm_now();
  if(sm_is_reading() && sm_last_tick) {
    uint64_t end=min(now,sm_last_activity+SM_IDLE_MS);
    if(end>sm_last_tick)sm_credit(sm_reading_book,end-sm_last_tick,end);
  }
  sm_last_tick=now;
  if(sm_dirty && now-sm_last_save>=SM_SAVE_MS)sm_save();
}
static void sm_activity(void) { sm_tick();sm_last_activity=sm_now(); }
static void sm_focus(int active) { sm_tick();sm_foreground=active; if(!active && sm_dirty)sm_save(); }
static uint64_t sm_streak(void) {
  char today[11];sm_date(sm_now(),today);int t=sm_day_index(today),run=0;
  for(int day=t;;day--) {
    int found=0;
    for(int i=0;i<sm_day_count;i++) if(sm_days[i].ms && sm_day_index(sm_days[i].date)==day){found=1;break;}
    if(!found){ if(day==t)continue; break; }  /* today may still be empty */
    run++;
  }
  return run;
}
static void sm_landed(int opened) {
  if(!g.has_current || !g.frame.valid)return;
  sm_load();sm_tick();
  int shelf=shelf_index(g.current.id);
  int e=shelf>=0 ? sm_book_entry((size_t)shelf):-1;
  if(opened>0 || e!=sm_reading_book) {
    if(sm_dirty)sm_save();
    sm_reading_book=e;
    if(e>=0 && opened>0){sm_entries[e].opens++;sm_entries[e].last_ms=sm_now();sm_dirty=1;}
  } else if(e>=0 && opened==0) sm_entries[e].turns++;
  /* Reflow refreshes progress without counting as a turn or resetting idle. */
  if(opened>=0)sm_last_activity=sm_now();
  if(e<0)return;
  sm_entry *x=&sm_entries[e];size_t parts=0;
  exr_publication *publication=g.session.fixed || g.session.txt ? NULL:select_publication();
  if(publication)exr_publication_parts(publication,&parts);
  x->page=g.frame.page;x->page_count=g.frame.page_count;x->part=g.frame.part;x->part_count=parts;
  double in_part=g.frame.page_count ? (double)(g.frame.page+1)/g.frame.page_count:0;
  x->progress=parts ? ((double)g.frame.part+in_part)/parts:in_part;
  if(x->progress>1)x->progress=1;
  sm_dirty=1;
  if(opened>0)sm_save();
}

/* ---- covers -------------------------------------------------------- */
typedef struct { UINT32 version; void *callback; BOOL no_thread,no_codecs; } sm_gdip_input;
static HBITMAP sm_decode(const wchar_t *path,int *w,int *h) {
  static HMODULE gdip;static ULONG_PTR token;
  static int (WINAPI *start)(ULONG_PTR *,const sm_gdip_input *,void *);
  static int (WINAPI *from_file)(const WCHAR *,void **);
  static int (WINAPI *to_hbitmap)(void *,HBITMAP *,DWORD);
  static int (WINAPI *dispose)(void *);
  if(!gdip) {
    gdip=LoadLibraryW(L"gdiplus.dll");if(!gdip)return NULL;
    start=(void *)GetProcAddress(gdip,"GdiplusStartup");from_file=(void *)GetProcAddress(gdip,"GdipCreateBitmapFromFile");
    to_hbitmap=(void *)GetProcAddress(gdip,"GdipCreateHBITMAPFromBitmap");dispose=(void *)GetProcAddress(gdip,"GdipDisposeImage");
    sm_gdip_input input={1,NULL,FALSE,FALSE};
    if(!start || !from_file || !to_hbitmap || !dispose || start(&token,&input,NULL)){FreeLibrary(gdip);gdip=NULL;return NULL;}
  }
  void *image=NULL;HBITMAP bitmap=NULL;
  if(from_file(path,&image) || !image)return NULL;
  if(to_hbitmap(image,&bitmap,0xffffffff))bitmap=NULL;
  dispose(image);
  BITMAP info;if(bitmap && GetObjectW(bitmap,sizeof(info),&info)){*w=info.bmWidth;*h=info.bmHeight;}
  return bitmap;
}
static void sm_cover_path(const char *relative,wchar_t *out) {
  wchar_t *wide=host_wide(relative,strlen(relative));out[0]=0;if(!wide)return;
  for(wchar_t *p=wide;*p;p++) if(*p==L'/')*p=L'\\';
  path_join(out,HOST_PATH,sm_dir,wide);free(wide);
}
static sm_cover_cache *sm_cover(int e) {
  if(e<0 || !sm_entries[e].cover)return NULL;
  for(int i=0;i<sm_cover_count;i++) if(sm_covers[i].book==e) {
    if(sm_covers[i].path && !strcmp(sm_covers[i].path,sm_entries[e].cover))return sm_covers[i].bitmap ? &sm_covers[i]:NULL;
    if(sm_covers[i].bitmap)DeleteObject(sm_covers[i].bitmap);
    free(sm_covers[i].path);sm_covers[i]=sm_covers[--sm_cover_count];break;
  }
  if(sm_cover_count==64)return NULL;
  sm_cover_cache *c=&sm_covers[sm_cover_count++];memset(c,0,sizeof(*c));c->book=e;c->path=host_strdup(sm_entries[e].cover);
  wchar_t path[HOST_PATH];sm_cover_path(sm_entries[e].cover,path);
  c->bitmap=sm_decode(path,&c->w,&c->h);
  return c->bitmap ? c:NULL;
}
/* ---- view model ---------------------------------------------------- */
static int sm_has_tag(int e,const char *tag) {
  if(e<0)return 0;
  for(int i=0;i<sm_entries[e].tag_count;i++) if(!strcmp(sm_entries[e].tags[i],tag))return 1;
  return 0;
}
static void sm_collect_tags(void) {
  sm_tag_total=0;
  for(size_t s=0;s<g.shelf_count;s++) {
    int e=sm_book_entry(s);if(e<0)continue;
    for(int t=0;t<sm_entries[e].tag_count;t++) {
      int seen=0;for(int k=0;k<sm_tag_total;k++) if(!strcmp(sm_tags[k],sm_entries[e].tags[t]))seen=1;
      if(!seen && sm_tag_total<256)sm_tags[sm_tag_total++]=sm_entries[e].tags[t];
    }
  }
  for(int i=1;i<sm_tag_total;i++) for(int k=i;k>0 && strcmp(sm_tags[k-1],sm_tags[k])>0;k--){char *t=sm_tags[k];sm_tags[k]=sm_tags[k-1];sm_tags[k-1]=t;}
  if(sm_filter>=sm_tag_total)sm_filter=-1;
}
static int sm_visible(size_t s) {
  int e=sm_book_entry(s);
  if(sm_filter==-1)return 1;
  if(sm_filter==-2)return e<0 || !sm_entries[e].tag_count;
  return sm_has_tag(e,sm_tags[sm_filter]);
}
static int sm_order_cmp(const void *a,const void *b) {
  int x=*(const int *)a,y=*(const int *)b,ex=sm_book_entry((size_t)x),ey=sm_book_entry((size_t)y);
  const char *sx=ex>=0 ? sm_entries[ex].series:NULL,*sy=ey>=0 ? sm_entries[ey].series:NULL;
  if(!sx != !sy)return sx ? -1:1;
  if(sx) {
    int c=strcmp(sx,sy);if(c)return c;
    double ix=sm_entries[ex].has_index ? sm_entries[ex].series_index:1e300,iy=sm_entries[ey].has_index ? sm_entries[ey].series_index:1e300;
    if(ix!=iy)return ix<iy ? -1:1;
  }
  return x-y; /* library order (most recent first) */
}
/* Visible shelf indices: series groups (by name, then index) followed by ungrouped books. */
static int sm_order(int *out) {
  int n=0;
  for(size_t s=0;s<g.shelf_count;s++) if(g.shelf[s].id>0 && sm_visible(s))out[n++]=(int)s;
  qsort(out,(size_t)n,sizeof(int),sm_order_cmp);return n;
}
static const char *sm_series_of(int s) { int e=sm_book_entry((size_t)s);return e>=0 ? sm_entries[e].series:NULL; }

/* ---- painting ------------------------------------------------------ */
static HFONT sm_font(int size,int weight) {
  return CreateFontW(-shell_px(size,shell_dpi),0,0,0,weight,0,0,0,DEFAULT_CHARSET,0,0,CLEARTYPE_QUALITY,0,L"Microsoft YaHei UI");
}
static void sm_text(HDC dc,const char *utf8,RECT *r,UINT flags) {
  wchar_t *w=host_wide(utf8,strlen(utf8));DrawTextW(dc,w ? w:L"",-1,r,flags|DT_NOPREFIX);free(w);
}
static void sm_fill(HDC dc,const RECT *r,uint32_t rgb) { HBRUSH b=CreateSolidBrush(shell_colorref(rgb));FillRect(dc,r,b);DeleteObject(b); }
static void sm_round(HDC dc,const RECT *r,uint32_t fill,uint32_t line,int radius) {
  HBRUSH b=CreateSolidBrush(shell_colorref(fill));HPEN p=CreatePen(PS_SOLID,1,shell_colorref(line));
  HGDIOBJ ob=SelectObject(dc,b),op=SelectObject(dc,p);RoundRect(dc,r->left,r->top,r->right,r->bottom,radius,radius);
  SelectObject(dc,ob);SelectObject(dc,op);DeleteObject(b);DeleteObject(p);
}
static void sm_add_hit(RECT r,int kind,int arg) { if(sm_hit_count<512)sm_hits[sm_hit_count++]=(sm_hit){r,kind,arg}; }
static int sm_chip(HDC dc,int x,int y,const wchar_t *label,int on,int kind,int arg) {
  SIZE size;GetTextExtentPoint32W(dc,label,(int)wcslen(label),&size);
  RECT r={x,y,x+size.cx+shell_px(24,shell_dpi),y+shell_px(30,shell_dpi)};
  sm_round(dc,&r,on ? shell_colors->accent:shell_colors->surface2,on ? shell_colors->accent:shell_colors->surface3,shell_px(15,shell_dpi));
  SetTextColor(dc,shell_colorref(on ? shell_colors->on_accent:shell_colors->text));
  DrawTextW(dc,label,-1,&r,DT_CENTER|DT_VCENTER|DT_SINGLELINE|DT_NOPREFIX);
  sm_add_hit(r,kind,arg);return r.right+shell_px(8,shell_dpi);
}
static void sm_fmt_duration(uint64_t ms,wchar_t *out,size_t cap) {
  uint64_t s=ms/1000;
  if(s>=3600)swprintf(out,cap,L"%llu 小时 %llu 分",(unsigned long long)(s/3600),(unsigned long long)(s%3600/60));
  else if(s>=60)swprintf(out,cap,L"%llu 分 %llu 秒",(unsigned long long)(s/60),(unsigned long long)(s%60));
  else swprintf(out,cap,L"%llu 秒",(unsigned long long)s);
}
static void sm_tags_line(int e,wchar_t *out,size_t cap) {
  out[0]=0;if(e<0)return;
  for(int t=0;t<sm_entries[e].tag_count;t++) {
    wchar_t *w=host_wide(sm_entries[e].tags[t],strlen(sm_entries[e].tags[t]));
    size_t n=wcslen(out);swprintf(out+n,cap-n,L"%ls#%ls",n ? L" ":L"",w ? w:L"");free(w);
  }
}
static int sm_header(HDC dc,RECT client,HFONT title,HFONT ui) {
  SelectObject(dc,title);SetTextColor(dc,shell_colorref(shell_colors->text));
  RECT t={shell_px(24,shell_dpi),0,client.right/2,shell_px(56,shell_dpi)};
  DrawTextW(dc,sm_mode ? L"阅读统计":L"书架",-1,&t,DT_VCENTER|DT_SINGLELINE);
  SelectObject(dc,ui);
  const wchar_t *labels[5]={L"网格",L"列表",L"统计",L"返回阅读",L"打开书籍"};
  int kinds[5]={SM_HIT_GRID,SM_HIT_LIST,SM_HIT_STATS,SM_HIT_BACK,SM_HIT_IMPORT};
  if(sm_mode){labels[0]=L"书架";kinds[0]=SM_HIT_SHELF;}
  int x=client.right-shell_px(24,shell_dpi);
  for(int i=4;i>=0;i--) {
    if(sm_mode && (i==1 || i==2))continue;
    SIZE size;GetTextExtentPoint32W(dc,labels[i],(int)wcslen(labels[i]),&size);
    int w=size.cx+shell_px(24,shell_dpi);x-=w;
    int on=!sm_mode && ((i==0 && !sm_list) || (i==1 && sm_list));
    RECT r={x,shell_px(12,shell_dpi),x+w,shell_px(44,shell_dpi)};
    sm_round(dc,&r,on ? shell_colors->accent:shell_colors->layer_float,on ? shell_colors->accent:shell_colors->surface3,shell_px(9,shell_dpi));
    SetTextColor(dc,shell_colorref(on ? shell_colors->on_accent:shell_colors->text));
    DrawTextW(dc,labels[i],-1,&r,DT_CENTER|DT_VCENTER|DT_SINGLELINE);sm_add_hit(r,kinds[i],0);
    x-=shell_px(8,shell_dpi);
  }
  return shell_px(56,shell_dpi);
}
#include "shell_shelf.inc"

static int sm_rank_cmp(const void *a,const void *b) {
  uint64_t x=sm_entries[*(const int *)a].read_ms,y=sm_entries[*(const int *)b].read_ms;return x<y ? 1:x>y ? -1:0;
}
static void sm_paint_stats(HDC dc,RECT client,HFONT ui,HFONT small_font,HFONT bold,HFONT big) {
  int pad=shell_px(24,shell_dpi),y=shell_px(68,shell_dpi);
  uint64_t total=0;int books=0,read=0;
  for(size_t s=0;s<g.shelf_count;s++) if(g.shelf[s].id>0){int e=sm_book_entry(s);books++;if(e>=0 && sm_entries[e].read_ms){total+=sm_entries[e].read_ms;read++;}}
  char today[11];sm_date(sm_now(),today);uint64_t today_ms=0;
  for(int i=0;i<sm_day_count;i++) if(!strcmp(sm_days[i].date,today))today_ms=sm_days[i].ms;
  wchar_t values[4][64];const wchar_t *names[4]={L"累计阅读时长",L"书架 / 已读本数",L"连续阅读天数",L"今日阅读"};
  sm_fmt_duration(total,values[0],64);swprintf(values[1],64,L"%d / %d 本",books,read);
  swprintf(values[2],64,L"%llu 天",(unsigned long long)sm_streak());sm_fmt_duration(today_ms,values[3],64);
  int w=(client.right-2*pad-3*shell_px(16,shell_dpi))/4;
  for(int i=0;i<4;i++) {
    RECT r={pad+i*(w+shell_px(16,shell_dpi)),y,pad+i*(w+shell_px(16,shell_dpi))+w,y+shell_px(96,shell_dpi)};
    sm_round(dc,&r,shell_colors->layer_float,shell_colors->surface3,shell_px(14,shell_dpi));
    RECT t={r.left+shell_px(16,shell_dpi),r.top+shell_px(12,shell_dpi),r.right-shell_px(8,shell_dpi),r.top+shell_px(34,shell_dpi)};
    SelectObject(dc,small_font);SetTextColor(dc,shell_colorref(shell_colors->text_secondary));DrawTextW(dc,names[i],-1,&t,DT_SINGLELINE);
    t.top=t.bottom+shell_px(6,shell_dpi);t.bottom=r.bottom-shell_px(10,shell_dpi);
    SelectObject(dc,big);SetTextColor(dc,shell_colorref(shell_colors->text));DrawTextW(dc,values[i],-1,&t,DT_SINGLELINE|DT_END_ELLIPSIS);
  }
  y+=shell_px(120,shell_dpi);
  SelectObject(dc,bold);SetTextColor(dc,shell_colorref(shell_colors->text_secondary));
  RECT h={pad,y,client.right-pad,y+shell_px(28,shell_dpi)};DrawTextW(dc,L"单册排行（按阅读时长）",-1,&h,DT_SINGLELINE|DT_VCENTER);
  y+=shell_px(34,shell_dpi);
  int cols[7]={0,5,40,56,67,78,88};const wchar_t *heads[7]={L"#",L"书名",L"阅读时长",L"打开次数",L"已读页数",L"进度",L"最后阅读"};
  int tw=client.right-2*pad;SelectObject(dc,small_font);
  for(int c=0;c<7;c++){RECT r={pad+tw*cols[c]/100,y,pad+tw*(c<6 ? cols[c+1]:100)/100,y+shell_px(22,shell_dpi)};DrawTextW(dc,heads[c],-1,&r,DT_SINGLELINE);}
  y+=shell_px(26,shell_dpi);
  int rank[512],n=0;
  for(size_t s=0;s<g.shelf_count && n<512;s++) if(g.shelf[s].id>0){int e=sm_book_entry(s);if(e>=0 && sm_entries[e].read_ms){int dup=0;for(int k=0;k<n;k++)dup|=rank[k]==e;if(!dup)rank[n++]=e;}}
  qsort(rank,(size_t)n,sizeof(int),sm_rank_cmp);
  for(int i=0;i<n && y<client.bottom;i++) {
    sm_entry *x=&sm_entries[rank[i]];size_t s=0;
    for(size_t k=0;k<g.shelf_count;k++){const char *sha=sm_id_sha(g.shelf[k].id);if(sha && !strcmp(sha,x->sha)){s=k;break;}}
    RECT row={pad,y,client.right-pad,y+shell_px(36,shell_dpi)};
    if(i%2==0)sm_round(dc,&row,shell_colors->surface2,shell_colors->surface2,shell_px(6,shell_dpi));
    wchar_t cell[7][128];swprintf(cell[0],128,L"%d",i+1);
    wchar_t *title=host_wide(sm_title(s),strlen(sm_title(s)));swprintf(cell[1],128,L"%ls",title ? title:L"");free(title);
    sm_fmt_duration(x->read_ms,cell[2],128);swprintf(cell[3],128,L"%llu",(unsigned long long)x->opens);
    swprintf(cell[4],128,L"%llu",(unsigned long long)x->turns);swprintf(cell[5],128,L"%.1f%%",x->progress*100);
    char date[11];sm_date(x->last_ms,date);swprintf(cell[6],128,L"%hs",date);
    SelectObject(dc,ui);SetTextColor(dc,shell_colorref(shell_colors->text));
    for(int c=0;c<7;c++){RECT r={pad+tw*cols[c]/100+shell_px(8,shell_dpi),y,pad+tw*(c<6 ? cols[c+1]:100)/100,y+shell_px(36,shell_dpi)};DrawTextW(dc,cell[c],-1,&r,DT_SINGLELINE|DT_VCENTER|DT_END_ELLIPSIS|DT_NOPREFIX);}
    y+=shell_px(38,shell_dpi);
  }
  if(!n){SelectObject(dc,ui);RECT r={pad,y,client.right-pad,y+shell_px(30,shell_dpi)};DrawTextW(dc,L"还没有阅读记录。",-1,&r,DT_SINGLELINE);}
  sm_content_h=0;
}
static void sm_paint(HWND window,HDC target) {
  RECT client;GetClientRect(window,&client);
  HDC dc=CreateCompatibleDC(target);HBITMAP bitmap=CreateCompatibleBitmap(target,client.right,client.bottom);
  HGDIOBJ old=SelectObject(dc,bitmap);
  sm_fill(dc,&client,shell_colors->layer_page);SetBkMode(dc,TRANSPARENT);sm_hit_count=0;
  HFONT title=sm_font(20,650),ui=sm_font(14,400),small_font=sm_font(12,400),bold=sm_font(14,650),big=sm_font(22,650);
  sm_cover_font[0]=sm_font(15,650);sm_cover_font[1]=sm_font(16,650);
  RECT bar={0,0,client.right,shell_px(56,shell_dpi)};sm_fill(dc,&bar,shell_colors->layer_side);
  RECT line={0,bar.bottom-1,client.right,bar.bottom};sm_fill(dc,&line,shell_colors->surface3);
  sm_header(dc,client,title,ui);
  if(sm_mode)sm_paint_stats(dc,client,ui,small_font,bold,big);else sm_paint_shelf(dc,client,ui,small_font,bold);
  int page=max(1,client.bottom-shell_px(104,shell_dpi));
  int pos=max(0,min(sm_scroll,max(0,sm_content_h-page)));
  SCROLLINFO scroll={sizeof(scroll),SIF_RANGE|SIF_PAGE|SIF_POS,0,max(0,sm_content_h-1),(UINT)page,pos,0};
  SetScrollInfo(window,SB_VERT,&scroll,TRUE);
  if(sm_scroll!=pos){sm_scroll=pos;InvalidateRect(window,NULL,FALSE);}
  BitBlt(target,0,0,client.right,client.bottom,dc,0,0,SRCCOPY);
  SelectObject(dc,old);DeleteObject(bitmap);DeleteDC(dc);
  DeleteObject(title);DeleteObject(ui);DeleteObject(small_font);DeleteObject(bold);DeleteObject(big);DeleteObject(sm_cover_font[0]);DeleteObject(sm_cover_font[1]);
}

/* ---- metadata editing ---------------------------------------------- */
static char *sm_trimmed(const wchar_t *text) {
  if(!text)return NULL;
  while(*text==L' ' || *text==L'\t')text++;
  size_t n=wcslen(text);while(n && (text[n-1]==L' ' || text[n-1]==L'\t'))n--;
  if(!n)return NULL;
  wchar_t *copy=malloc((n+1)*sizeof(wchar_t));if(!copy)return NULL;
  memcpy(copy,text,n*sizeof(wchar_t));copy[n]=0;char *utf8=host_utf8(copy);free(copy);return utf8;
}
/* Applies one edit; fields equal to the library value are stored as null. */
static int sm_apply(int shelf,const wchar_t *title,const wchar_t *author,const wchar_t *series,const wchar_t *index,
                    const wchar_t *tags,const wchar_t *cover_file,int cover_clear) {
  int e=sm_book_entry((size_t)shelf);if(e<0 || !sm_writable)return 0;
  sm_entry backup;if(!sm_entry_copy(&backup,&sm_entries[e]))return 0;
  sm_entry *x=&sm_entries[e];
  char *t=sm_trimmed(title),*a=sm_trimmed(author),*s=sm_trimmed(series);
  const char *lt=g.shelf[shelf].title ? g.shelf[shelf].title:"",*la=g.shelf[shelf].author ? g.shelf[shelf].author:"";
  if(t && !strcmp(t,lt)){free(t);t=NULL;}
  if(a && !strcmp(a,la)){free(a);a=NULL;}
  free(x->title);free(x->author);free(x->series);x->title=t;x->author=a;x->series=s;
  wchar_t *end=NULL;double v=index && index[0] ? wcstod(index,&end):0;
  x->has_index=index && index[0] && end && !*end;x->series_index=x->has_index ? v:0;
  for(int i=0;i<x->tag_count;i++)free(x->tags[i]);
  x->tag_count=0;
  if(tags) {
    wchar_t buffer[2048];wcsncpy(buffer,tags,2047);buffer[2047]=0;wchar_t *context=NULL;
    for(wchar_t *part=wcstok(buffer,L",，;；",&context);part && x->tag_count<SM_MAX_TAGS;part=wcstok(NULL,L",，;；",&context)) {
      char *tag=sm_trimmed(part);if(!tag)continue;
      int dup=0;for(int i=0;i<x->tag_count;i++)dup|=!strcmp(x->tags[i],tag);
      if(dup)free(tag);else x->tags[x->tag_count++]=tag;
    }
  }
  wchar_t new_cover[HOST_PATH]=L"";char *old_cover=x->cover ? host_strdup(x->cover):NULL;
  if(cover_file && cover_file[0]) {
    int w=0,h=0;HBITMAP probe=sm_decode(cover_file,&w,&h);
    if(!probe){sm_entry_free(x);*x=backup;free(old_cover);set_status(L"无法读取封面图片；未做更改。");return 0;}
    DeleteObject(probe);
    wchar_t covers[HOST_PATH],name[128];path_join(covers,HOST_PATH,sm_dir,L"covers");ensure_directory(covers);
    const wchar_t *ext=wcsrchr(cover_file,L'.');
    swprintf(name,128,L"%hs-%llu%ls",x->sha,(unsigned long long)sm_now(),ext && wcslen(ext)<8 ? ext:L".img");
    path_join(new_cover,HOST_PATH,covers,name);
    if(!CopyFileW(cover_file,new_cover,FALSE)){sm_entry_free(x);*x=backup;free(old_cover);set_status(L"复制封面失败；未做更改。");return 0;}
    char *utf8=host_utf8(name);free(x->cover);x->cover=NULL;
    if(utf8){size_t n=strlen(utf8)+8;x->cover=malloc(n);if(x->cover)snprintf(x->cover,n,"covers/%s",utf8);free(utf8);}
  } else if(cover_clear){free(x->cover);x->cover=NULL;}
  if(!sm_save()) {
    sm_entry_free(x);*x=backup;if(new_cover[0])DeleteFileW(new_cover);free(old_cover);
    set_status(L"shelf.json 保存失败；已回滚，原文件未改动。");if(sm_view)InvalidateRect(sm_view,NULL,FALSE);return 0;
  }
  if(old_cover && (!x->cover || strcmp(old_cover,x->cover))){wchar_t path[HOST_PATH];sm_cover_path(old_cover,path);DeleteFileW(path);}
  free(old_cover);sm_entry_free(&backup);
  set_status(L"书籍信息已保存到 shelf.json。");
  shelf_refresh();InvalidateRect(g.window,NULL,FALSE);
  if(sm_view)InvalidateRect(sm_view,NULL,FALSE);
  return 1;
}
enum { SM_ID_TITLE=30,SM_ID_AUTHOR,SM_ID_SERIES,SM_ID_INDEX,SM_ID_TAGS,SM_ID_TAGLIST,SM_ID_COVER,SM_ID_NOCOVER,SM_ID_SAVE,SM_ID_CANCEL,SM_ID_COVERSTATE };
static void sm_edit_close(void) { if(sm_edit_panel)ShowWindow(sm_edit_panel,SW_HIDE);sm_edit_book=-1;SetFocus(sm_view); }
static void sm_edit_cover_state(void) {
  int e=sm_book_entry((size_t)sm_edit_book);wchar_t text[HOST_PATH+32];
  if(sm_edit_cover[0]){const wchar_t *n=wcsrchr(sm_edit_cover,L'\\');swprintf(text,HOST_PATH+32,L"封面：将替换为 %ls",n ? n+1:sm_edit_cover);}
  else if(sm_edit_cover_clear || e<0 || !sm_entries[e].cover)swprintf(text,HOST_PATH+32,L"封面：默认");
  else swprintf(text,HOST_PATH+32,L"封面：自定义");
  SetDlgItemTextW(sm_edit_panel,SM_ID_COVERSTATE,text);
}
static void sm_edit_toggle_tag(void) {
  /* clicking a known tag in the list adds/removes it from the tags field */
  int i=(int)SendDlgItemMessageW(sm_edit_panel,SM_ID_TAGLIST,LB_GETCURSEL,0,0);if(i<0)return;
  wchar_t tag[256],field[2048],out[2048]=L"";SendDlgItemMessageW(sm_edit_panel,SM_ID_TAGLIST,LB_GETTEXT,i,(LPARAM)tag);
  GetDlgItemTextW(sm_edit_panel,SM_ID_TAGS,field,2048);int found=0;wchar_t *context=NULL;
  for(wchar_t *p=wcstok(field,L",，",&context);p;p=wcstok(NULL,L",，",&context)) {
    while(*p==L' ')p++;
    if(!wcscmp(p,tag)){found=1;continue;}
    if(*p){if(out[0])wcscat(out,L", ");wcsncat(out,p,2000-wcslen(out));}
  }
  if(!found){if(out[0])wcscat(out,L", ");wcsncat(out,tag,2000-wcslen(out));}
  SetDlgItemTextW(sm_edit_panel,SM_ID_TAGS,out);
}
static int sm_edit_commit(void) {
  wchar_t f[5][2048];for(int i=0;i<5;i++)GetDlgItemTextW(sm_edit_panel,SM_ID_TITLE+i,f[i],2048);
  int ok=sm_apply(sm_edit_book,f[0],f[1],f[2],f[3],f[4],sm_edit_cover,sm_edit_cover_clear);
  if(ok)sm_edit_close();
  return ok;
}
static LRESULT CALLBACK sm_edit_procedure(HWND window,UINT message,WPARAM wp,LPARAM lp) {
  switch(message) {
    case WM_ERASEBKGND:{RECT r;GetClientRect(window,&r);sm_fill((HDC)wp,&r,shell_colors->layer_float);
      HBRUSH b=CreateSolidBrush(shell_colorref(shell_colors->surface3));FrameRect((HDC)wp,&r,b);DeleteObject(b);return 1;}
    case WM_CTLCOLORSTATIC:case WM_CTLCOLOREDIT:case WM_CTLCOLORLISTBOX:
      SetTextColor((HDC)wp,shell_colorref(shell_colors->text));SetBkColor((HDC)wp,shell_colorref(shell_colors->layer_float));
      if(sm_edit_brush)DeleteObject(sm_edit_brush);
      sm_edit_brush=CreateSolidBrush(shell_colorref(shell_colors->layer_float));return (LRESULT)sm_edit_brush;
    case WM_COMMAND:
      switch(LOWORD(wp)) {
        case SM_ID_SAVE:sm_edit_commit();return 0;
        case SM_ID_CANCEL:sm_edit_close();return 0;
        case SM_ID_NOCOVER:sm_edit_cover[0]=0;sm_edit_cover_clear=1;sm_edit_cover_state();return 0;
        case SM_ID_COVER: {
          OPENFILENAMEW ofn={0};wchar_t file[HOST_PATH]=L"";ofn.lStructSize=sizeof(ofn);ofn.hwndOwner=g.window;
          ofn.lpstrFilter=L"图片 (*.png;*.jpg;*.jpeg;*.bmp;*.gif)\0*.png;*.jpg;*.jpeg;*.bmp;*.gif\0";ofn.lpstrFile=file;ofn.nMaxFile=HOST_PATH;
          ofn.Flags=OFN_FILEMUSTEXIST|OFN_PATHMUSTEXIST|OFN_NOCHANGEDIR;
          if(GetOpenFileNameW(&ofn)){wcscpy(sm_edit_cover,file);sm_edit_cover_clear=0;sm_edit_cover_state();}
          return 0;
        }
        case SM_ID_TAGLIST: if(HIWORD(wp)==LBN_SELCHANGE)sm_edit_toggle_tag();return 0;
      }
      break;
    case WM_DRAWITEM: {
      const DRAWITEMSTRUCT *item=(const DRAWITEMSTRUCT *)lp;wchar_t text[64];GetWindowTextW(item->hwndItem,text,64);
      shell_draw_control(item,text,item->CtlID==SM_ID_SAVE ? SHELL_CONTROL_PRIMARY:SHELL_CONTROL_STANDARD,shell_colors->layer_float);return TRUE;
    }
  }
  return DefWindowProcW(window,message,wp,lp);
}
static void sm_edit_open(int shelf) {
  if(shelf<0 || (size_t)shelf>=g.shelf_count || sm_book_entry((size_t)shelf)<0)return;
  if(!sm_writable){set_status(L"shelf.json 不可写；书籍信息编辑已暂停。");return;}
  HINSTANCE instance=GetModuleHandleW(NULL);
  if(!sm_edit_panel) {
    WNDCLASSW type={0};type.lpfnWndProc=sm_edit_procedure;type.hInstance=instance;type.hCursor=LoadCursor(NULL,IDC_ARROW);type.lpszClassName=L"EXReaderShelfEdit";RegisterClassW(&type);
    sm_edit_panel=CreateWindowExW(WS_EX_CONTROLPARENT,type.lpszClassName,L"编辑信息",WS_CHILD|WS_CLIPSIBLINGS,0,0,0,0,g.window,NULL,instance,NULL);
    const wchar_t *labels[6]={L"编辑信息",L"标题",L"作者",L"系列名",L"系列序号",L"标签（逗号分隔，点下方已有标签可增删）"};
    for(int i=0;i<6;i++)CreateWindowExW(0,L"STATIC",labels[i],WS_CHILD|WS_VISIBLE,0,0,0,0,sm_edit_panel,(HMENU)(INT_PTR)(10+i),instance,NULL);
    for(int i=0;i<5;i++)CreateWindowExW(WS_EX_CLIENTEDGE,L"EDIT",L"",WS_CHILD|WS_VISIBLE|WS_TABSTOP|ES_AUTOHSCROLL,0,0,0,0,sm_edit_panel,(HMENU)(INT_PTR)(SM_ID_TITLE+i),instance,NULL);
    CreateWindowExW(WS_EX_CLIENTEDGE,L"LISTBOX",L"",WS_CHILD|WS_VISIBLE|WS_TABSTOP|WS_VSCROLL|LBS_NOTIFY|LBS_MULTICOLUMN,0,0,0,0,sm_edit_panel,(HMENU)SM_ID_TAGLIST,instance,NULL);
    CreateWindowExW(0,L"STATIC",L"",WS_CHILD|WS_VISIBLE,0,0,0,0,sm_edit_panel,(HMENU)SM_ID_COVERSTATE,instance,NULL);
    const wchar_t *buttons[4]={L"更换封面…",L"移除封面",L"保存",L"取消"};
    for(int i=0;i<4;i++)CreateWindowExW(0,L"BUTTON",buttons[i],WS_CHILD|WS_VISIBLE|WS_TABSTOP|BS_OWNERDRAW,0,0,0,0,sm_edit_panel,(HMENU)(INT_PTR)(SM_ID_COVER+i),instance,NULL);
  }
  sm_edit_book=shelf;sm_edit_cover[0]=0;sm_edit_cover_clear=0;
  RECT client;GetClientRect(g.window,&client);
  int w=shell_px(440,shell_dpi),h=shell_px(500,shell_dpi),x0=shell_px(20,shell_dpi),fw=w-2*x0;
  SetWindowPos(sm_edit_panel,HWND_TOP,max(0,(client.right-w)/2),max(0,(client.bottom-h)/2),w,h,SWP_NOACTIVATE);
  HFONT font=sm_font(13,400),head=sm_font(18,650);static HFONT owned[2];
  if(owned[0]){DeleteObject(owned[0]);DeleteObject(owned[1]);}
  owned[0]=font;owned[1]=head;
  for(HWND child=GetWindow(sm_edit_panel,GW_CHILD);child;child=GetWindow(child,GW_HWNDNEXT))SendMessageW(child,WM_SETFONT,(WPARAM)font,TRUE);
  SendDlgItemMessageW(sm_edit_panel,10,WM_SETFONT,(WPARAM)head,TRUE);
  int y=shell_px(16,shell_dpi);
  MoveWindow(GetDlgItem(sm_edit_panel,10),x0,y,fw,shell_px(28,shell_dpi),TRUE);y+=shell_px(38,shell_dpi);
  for(int i=0;i<5;i++) {
    MoveWindow(GetDlgItem(sm_edit_panel,11+i),x0,y,fw,shell_px(18,shell_dpi),TRUE);y+=shell_px(20,shell_dpi);
    if(i==3){MoveWindow(GetDlgItem(sm_edit_panel,SM_ID_TITLE+i),x0,y,shell_px(120,shell_dpi),shell_px(26,shell_dpi),TRUE);}
    else MoveWindow(GetDlgItem(sm_edit_panel,SM_ID_TITLE+i),x0,y,fw,shell_px(26,shell_dpi),TRUE);
    y+=shell_px(34,shell_dpi);
  }
  MoveWindow(GetDlgItem(sm_edit_panel,SM_ID_TAGLIST),x0,y-shell_px(4,shell_dpi),fw,shell_px(56,shell_dpi),TRUE);y+=shell_px(60,shell_dpi);
  MoveWindow(GetDlgItem(sm_edit_panel,SM_ID_COVERSTATE),x0,y,fw,shell_px(20,shell_dpi),TRUE);y+=shell_px(24,shell_dpi);
  MoveWindow(GetDlgItem(sm_edit_panel,SM_ID_COVER),x0,y,shell_px(120,shell_dpi),shell_px(32,shell_dpi),TRUE);
  MoveWindow(GetDlgItem(sm_edit_panel,SM_ID_NOCOVER),x0+shell_px(128,shell_dpi),y,shell_px(100,shell_dpi),shell_px(32,shell_dpi),TRUE);
  y=h-shell_px(50,shell_dpi);
  MoveWindow(GetDlgItem(sm_edit_panel,SM_ID_SAVE),w-x0-shell_px(196,shell_dpi),y,shell_px(92,shell_dpi),shell_px(34,shell_dpi),TRUE);
  MoveWindow(GetDlgItem(sm_edit_panel,SM_ID_CANCEL),w-x0-shell_px(96,shell_dpi),y,shell_px(92,shell_dpi),shell_px(34,shell_dpi),TRUE);
  int e=sm_book_entry((size_t)shelf);
  const char *values[3]={sm_title((size_t)shelf),sm_author((size_t)shelf),sm_entries[e].series ? sm_entries[e].series:""};
  for(int i=0;i<3;i++){wchar_t *wv=host_wide(values[i],strlen(values[i]));SetDlgItemTextW(sm_edit_panel,SM_ID_TITLE+i,wv ? wv:L"");free(wv);}
  wchar_t index[32]=L"";if(sm_entries[e].has_index)swprintf(index,32,L"%g",sm_entries[e].series_index);
  SetDlgItemTextW(sm_edit_panel,SM_ID_INDEX,index);
  wchar_t tags[2048]=L"";
  for(int t=0;t<sm_entries[e].tag_count;t++){wchar_t *wt=host_wide(sm_entries[e].tags[t],strlen(sm_entries[e].tags[t]));if(t)wcscat(tags,L", ");wcsncat(tags,wt ? wt:L"",2000-wcslen(tags));free(wt);}
  SetDlgItemTextW(sm_edit_panel,SM_ID_TAGS,tags);
  sm_collect_tags();SendDlgItemMessageW(sm_edit_panel,SM_ID_TAGLIST,LB_RESETCONTENT,0,0);
  SendDlgItemMessageW(sm_edit_panel,SM_ID_TAGLIST,LB_SETCOLUMNWIDTH,shell_px(100,shell_dpi),0);
  for(int t=0;t<sm_tag_total;t++){wchar_t *wt=host_wide(sm_tags[t],strlen(sm_tags[t]));SendDlgItemMessageW(sm_edit_panel,SM_ID_TAGLIST,LB_ADDSTRING,0,(LPARAM)(wt ? wt:L""));free(wt);}
  sm_edit_cover_state();
  ShowWindow(sm_edit_panel,SW_SHOW);SetFocus(GetDlgItem(sm_edit_panel,SM_ID_TITLE));InvalidateRect(sm_edit_panel,NULL,TRUE);
}

/* ---- shelf window ---------------------------------------------------- */
static void sm_open_book(int shelf) {
  if(shelf<0 || (size_t)shelf>=g.shelf_count || (g.job && g.job->kind!=JOB_PREFETCH) || g.pending)return;
  int64_t id=g.shelf[shelf].id;
  if(!shelf_find(id))shelf_imported(id,NULL);
  for(int i=0;i<shelf_count;i++)if(shelf_recent[i].id==id) {
    sm_recent();shelf_open_index(i);return;
  }
}
static int sm_hit_at(int x,int y) {
  POINT p={x,y};for(int i=sm_hit_count-1;i>=0;i--) if(PtInRect(&sm_hits[i].r,p))return i;
  return -1;
}
static void sm_context(int shelf,int command) {
  if(command==1)sm_open_book(shelf);
  else if(command==2)sm_edit_open(shelf);
}
static void sm_recent(void) {
  sm_requested=-1;sm_edit_close();sm_last_tick=sm_now();
  if(sm_view)ShowWindow(sm_view,SW_HIDE);
}
static void sm_hide(void) {
  if(g.has_current)sm_open_book(shelf_index(g.current.id));
  else {sm_mode=0;sm_filter=-1;sm_scroll=0;sm_refresh();}
}
static void sm_click(int index,int right,int x,int y) {
  if(index<0)return;
  sm_hit h=sm_hits[index];
  switch(h.kind) {
    case SM_HIT_BOOK:
      if(!right){sm_open_book(h.arg);return;}
      {
        HMENU menu=CreatePopupMenu();AppendMenuW(menu,MF_STRING,1,L"打开");AppendMenuW(menu,MF_STRING,2,L"编辑信息…");
        POINT p={x,y};ClientToScreen(sm_view,&p);
        int command=TrackPopupMenu(menu,TPM_RETURNCMD|TPM_RIGHTBUTTON,p.x,p.y,0,sm_view,NULL);DestroyMenu(menu);
        sm_context(h.arg,command);
      }
      return;
    case SM_HIT_TAG:sm_filter=h.arg;sm_scroll=0;break;
    case SM_HIT_GRID:case SM_HIT_LIST:
      sm_list=h.kind==SM_HIT_LIST;sm_dirty=1;sm_save();break;
    case SM_HIT_STATS:sm_show(1);break;
    case SM_HIT_SHELF:sm_show(0);break;
    case SM_HIT_BACK:sm_hide();return;
    case SM_HIT_IMPORT:g.auto_open_imported=1;import_path(NULL,1);return;
  }
  InvalidateRect(sm_view,NULL,FALSE);
}
static void sm_scroll_to(int position) {
  RECT r;GetClientRect(sm_view,&r);
  int range=max(0,sm_content_h-(r.bottom-shell_px(104,shell_dpi)));
  sm_scroll=max(0,min(range,position));
  SetScrollPos(sm_view,SB_VERT,sm_scroll,TRUE);InvalidateRect(sm_view,NULL,FALSE);
}
static LRESULT CALLBACK sm_view_procedure(HWND window,UINT message,WPARAM wp,LPARAM lp) {
  switch(message) {
    case WM_ERASEBKGND:return 1;
    case WM_PAINT:{PAINTSTRUCT ps;HDC dc=BeginPaint(window,&ps);sm_paint(window,dc);EndPaint(window,&ps);return 0;}
    case WM_PRINTCLIENT:sm_paint(window,(HDC)wp);return 0;
    case WM_LBUTTONDOWN:SetFocus(window);return 0;
    case WM_LBUTTONUP:sm_click(sm_hit_at((short)LOWORD(lp),(short)HIWORD(lp)),0,0,0);return 0;
    case WM_RBUTTONUP:sm_click(sm_hit_at((short)LOWORD(lp),(short)HIWORD(lp)),1,(short)LOWORD(lp),(short)HIWORD(lp));return 0;
    case WM_MOUSEMOVE: {
      int i=sm_hit_at((short)LOWORD(lp),(short)HIWORD(lp)),hot=i>=0 && sm_hits[i].kind==SM_HIT_BOOK ? sm_hits[i].arg:-1;
      if(hot!=sm_hot){sm_hot=hot;InvalidateRect(window,NULL,FALSE);}
      return 0;
    }
    case WM_MOUSEWHEEL:
      sm_scroll_to(sm_scroll-(short)HIWORD(wp)*shell_px(60,shell_dpi)/WHEEL_DELTA);return 0;
    case WM_VSCROLL: {
      SCROLLINFO info={.cbSize=sizeof(info),.fMask=SIF_ALL};GetScrollInfo(window,SB_VERT,&info);
      int pos=sm_scroll;
      switch(LOWORD(wp)) {
        case SB_LINEUP:pos-=shell_px(60,shell_dpi);break;
        case SB_LINEDOWN:pos+=shell_px(60,shell_dpi);break;
        case SB_PAGEUP:pos-=(int)info.nPage;break;
        case SB_PAGEDOWN:pos+=(int)info.nPage;break;
        case SB_THUMBTRACK:case SB_THUMBPOSITION:pos=info.nTrackPos;break;
        case SB_TOP:pos=0;break;case SB_BOTTOM:pos=info.nMax;break;
      }
      sm_scroll_to(pos);return 0;
    }
    case WM_KEYDOWN:
      if(wp==VK_ESCAPE && g.has_current){sm_hide();return 0;}
      break;
  }
  return DefWindowProcW(window,message,wp,lp);
}
static void sm_layout(void) {
  RECT client;GetClientRect(shelf_panel,&client);
  if(sm_view && IsWindowVisible(sm_view))SetWindowPos(sm_view,HWND_TOP,0,0,client.right,client.bottom,SWP_NOACTIVATE);
}
static void sm_create(HWND parent) {
  HINSTANCE instance=GetModuleHandleW(NULL);WNDCLASSW type={0};
  type.lpfnWndProc=sm_view_procedure;type.hInstance=instance;type.hCursor=LoadCursor(NULL,IDC_ARROW);type.lpszClassName=L"EXReaderShelfMeta";RegisterClassW(&type);
  sm_view=CreateWindowExW(0,type.lpszClassName,L"系列、标签与阅读统计",WS_CHILD|WS_CLIPSIBLINGS|WS_TABSTOP|WS_VSCROLL,0,0,0,0,shelf_panel,NULL,instance,NULL);
  sm_foreground=GetForegroundWindow()==parent;sm_load();
  SetTimer(parent,0x5760,1000,NULL);
}
static void sm_refresh(void) {
  if(!sm_view)return;
  sm_load();sm_layout();
  if(IsWindowVisible(sm_view))InvalidateRect(sm_view,NULL,FALSE);
}
static void sm_shelf_visibility(int show) {
  if(!show){sm_recent();return;}
  if(sm_requested>=0){sm_mode=sm_requested;sm_requested=-1;}
  if(sm_view){ShowWindow(sm_view,SW_SHOWNA);sm_layout();SetFocus(sm_view);}
  sm_refresh();
}
static void sm_show(int mode) {
  if(!sm_view)return;
  sm_load();sm_tick();if(sm_dirty)sm_save();
  sm_requested=mode;sm_scroll=0;
  if(shell_active)shelf_return();
  else if(!shelf_visible){shelf_requested=1;shell_sync();}
  if(shelf_visible)sm_shelf_visibility(1);
  else if(!shelf_exit_pending)sm_requested=-1;
}
static int sm_flush(void) {
  sm_tick();
  if(sm_dirty && !sm_save())set_status(L"阅读统计保存失败；shelf.json 原文件保留。");
  return 1; /* never block closing on statistics */
}
