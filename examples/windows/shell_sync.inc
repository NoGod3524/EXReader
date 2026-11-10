/* SPDX-License-Identifier: MIT */
/* WebDAV sync of reading progress, annotations and shelf metadata.

   Remote layout: <base>/<book SHA-256>/state.json, one file per book:
     {"format":"exreader-sync","version":1,"book_sha256":..,"revision":N,
      "updated_at":ms,"device_id":..,"progress":{at,ratio,anchor,fixed_page_id},
      "settings":{at,values},"annotations":[..],"deleted":[{key,at}]}
   Annotations are a set keyed by SHA-256 of their anchor; two devices that
   each added one annotation end up with both. A deletion is a tombstone that
   beats the annotation unless the annotation was edited after it. Progress
   and settings are last-writer-wins on their own "at" timestamp.

   Local files stay the single source of truth (annotations/<sha>.json,
   recent-books.json, shelf.json). The engine reads and writes only those files
   plus sync.json (non-secret config + draft queue), sync\<sha>.base.json (the
   last merged state, used to detect local edits and deletions) and sync.cred.
   sync.cred holds user name + password under Windows DPAPI (CryptProtectData,
   current user); no secret is ever written anywhere else.

   Threading: sy_net_* only reads files and talks to the server, so it runs on a
   worker. sy_apply_* mutates local files and runs on the UI thread. */
#include <winhttp.h>
#include <wincrypt.h>

enum { SY_OK=0,SY_AUTH,SY_NOTFOUND,SY_TIMEOUT,SY_OFFLINE,SY_SERVER,SY_CONFLICT,SY_LOCAL,SY_CONFIG,SY_TLS,SY_UNSUPPORTED };
#define SY_MAX_BYTES (32u*1024u*1024u)
#define SY_TOMBSTONE_MS (90ULL*86400000ULL)
#define WM_SY_DONE (WM_APP+0x5D)

typedef struct { char key[65]; uint64_t updated; char *raw; } sy_ann;
typedef struct { char key[65]; uint64_t at; } sy_del;
typedef struct {
  char sha[65],device[40];
  uint64_t revision,updated_at;
  int has_progress; uint64_t p_at; double p_ratio; char *p_anchor,*p_fixed;
  uint64_t s_at; char *settings;
  sy_ann *ann; int na;
  sy_del *del; int nd;
} sy_state;
typedef struct { char sha[65]; uint64_t queued; } sy_queued;
typedef struct { int code; char text[256]; } sy_status;
typedef struct { char sha[65]; sy_state merged; int pushed,pulled,failed; } sy_result;

/* configuration + paths (tests repoint these to simulate other devices) */
static char *sy_url,*sy_user,*sy_pass;
static char sy_device[40];
static wchar_t sy_annot_dir[HOST_PATH],sy_sync_dir[HOST_PATH],sy_shelf_file[HOST_PATH],sy_recent_file[HOST_PATH],
  sy_cfg_file[HOST_PATH],sy_cred_file[HOST_PATH];
static unsigned sy_timeout_ms=15000,sy_backoff_ms=300;
static uint64_t sy_last_ms,sy_clock_fixed;
static char sy_last_text[256];
static int sy_last_code;
static sy_queued *sy_queue; static int sy_queue_count;
static volatile LONG sy_busy;
static int sy_enabled_auto=1;

static uint64_t sy_now(void) {return sy_clock_fixed ? sy_clock_fixed:annot_time();}

/* ---- tiny helpers -------------------------------------------------- */
static char *sy_dup(const char *s) {return s ? host_strdup(s):NULL;}
static void sy_wipe(char **s) {if(*s){SecureZeroMemory(*s,strlen(*s));free(*s);*s=NULL;}}
static int sy_hex64(const char *s) {
  if(!s || strlen(s)!=64) return 0;
  for(int i=0;i<64;i++) if(!((s[i]>='0'&&s[i]<='9')||(s[i]>='a'&&s[i]<='f'))) return 0;
  return 1;
}
static void sy_sha(const void *bytes,size_t size,char out[65]) {shelf_hash(bytes,size,out);}
static char *sy_read(const wchar_t *path,size_t *size) {
  HANDLE f=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,NULL,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,NULL);
  if(f==INVALID_HANDLE_VALUE) return NULL;
  LARGE_INTEGER n;char *b=NULL;DWORD got=0;
  if(GetFileSizeEx(f,&n) && n.QuadPart>=0 && n.QuadPart<=SY_MAX_BYTES && (b=malloc((size_t)n.QuadPart+1))) {
    if(!ReadFile(f,b,(DWORD)n.QuadPart,&got,NULL) || got!=n.QuadPart){free(b);b=NULL;}
    else {b[got]=0;if(size)*size=got;}
  }
  CloseHandle(f);return b;
}
static int sy_write(const wchar_t *path,const void *bytes,size_t size) {
  wchar_t temp[HOST_PATH];swprintf(temp,HOST_PATH,L"%ls.tmp",path);
  HANDLE f=CreateFileW(temp,GENERIC_WRITE,0,NULL,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);
  DWORD wrote=0;int ok=0;
  if(f==INVALID_HANDLE_VALUE) return 0;
  ok=WriteFile(f,bytes,(DWORD)size,&wrote,NULL) && wrote==size && FlushFileBuffers(f);
  if(!CloseHandle(f)) ok=0;
  if(ok) ok=MoveFileExW(temp,path,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH)!=0;
  if(!ok) DeleteFileW(temp);
  return ok;
}
static void sy_status_set(sy_status *s,int code,const char *format,...) {
  va_list ap;va_start(ap,format);s->code=code;vsnprintf(s->text,sizeof(s->text),format,ap);va_end(ap);
}
static int sy_nul_free(const char *b,size_t n) { /* annot_parse's rule: SDK selectors are C strings */
  for(size_t i=0;i<n;i++) if(b[i]=='\\' && i+1<n){if(b[i+1]=='u' && i+5<n && !memcmp(b+i+2,"0000",4)) return 0;i++;}
  return 1;
}
static cv_json *sy_parse(const char *b,size_t n) {
  if(!sy_nul_free(b,n)) return NULL;
  char *e=NULL;cv_json *r=cv_json_parse(b,n,&e);free(e);return r;
}
static char *sy_copy_json(const cv_json *v) {
  cv_text t={0};style_json_copy(&t,v);
  if(t.failed){cv_text_free(&t);return NULL;}
  char *s=host_strdup(t.data ? t.data:"null");cv_text_free(&t);return s;
}

/* ---- state --------------------------------------------------------- */
static void sy_state_free(sy_state *s) {
  free(s->p_anchor);free(s->p_fixed);free(s->settings);
  for(int i=0;i<s->na;i++) free(s->ann[i].raw);
  free(s->ann);free(s->del);memset(s,0,sizeof(*s));
}
static int sy_ann_valid(const cv_json *o) {
  exr_content_anchor a={0};uint64_t color=9,c,u;char *text=NULL;
  const cv_json *anchor=cv_json_get(o,"anchor");
  int ok=o && o->type==CV_JSON_OBJECT && annot_uint(o,"color",&color) && color<3 && annot_uint(o,"created_ms",&c) &&
    annot_uint(o,"updated_ms",&u) && annot_string(o,"text",&text,0) && anchor && anchor->type==CV_JSON_OBJECT &&
    annot_endpoint_read(cv_json_get(anchor,"start"),&a.start) && annot_endpoint_read(cv_json_get(anchor,"end"),&a.end);
  free(text);exr_content_anchor_free(&a);return ok;
}
static int sy_ann_add(sy_state *s,const cv_json *o) {
  if(!sy_ann_valid(o)) return 0;
  char *anchor=sy_copy_json(cv_json_get(o,"anchor")),*raw=sy_copy_json(o);uint64_t u=0;
  if(!anchor || !raw){free(anchor);free(raw);return 0;}
  annot_uint(o,"updated_ms",&u);
  sy_ann *next=realloc(s->ann,((size_t)s->na+1)*sizeof(*next));
  if(!next){free(anchor);free(raw);return 0;}
  s->ann=next;sy_ann *a=&s->ann[s->na++];memset(a,0,sizeof(*a));
  sy_sha(anchor,strlen(anchor),a->key);a->updated=u;a->raw=raw;free(anchor);
  for(int i=0;i<s->na-1;i++) if(!strcmp(s->ann[i].key,a->key)) { /* duplicate inside one file: keep the newer */
    if(s->ann[i].updated<a->updated){free(s->ann[i].raw);s->ann[i]=*a;}else free(a->raw);
    s->na--;break;
  }
  return 1;
}
static int sy_del_add(sy_state *s,const char *key,uint64_t at) {
  for(int i=0;i<s->nd;i++) if(!strcmp(s->del[i].key,key)){if(s->del[i].at<at)s->del[i].at=at;return 1;}
  sy_del *next=realloc(s->del,((size_t)s->nd+1)*sizeof(*next));
  if(!next) return 0;
  s->del=next;strcpy(s->del[s->nd].key,key);s->del[s->nd++].at=at;return 1;
}
static int sy_cmp_ann(const void *a,const void *b) {return strcmp(((const sy_ann *)a)->key,((const sy_ann *)b)->key);}
static int sy_cmp_del(const void *a,const void *b) {return strcmp(((const sy_del *)a)->key,((const sy_del *)b)->key);}
/* Deterministic body without revision/updated_at/device: two states with the
   same content compare equal regardless of who wrote them. */
static void sy_content(const sy_state *s,cv_text *j) {
  sy_state t=*s;
  t.ann=s->na ? malloc((size_t)s->na*sizeof(*t.ann)):NULL;t.del=s->nd ? malloc((size_t)s->nd*sizeof(*t.del)):NULL;
  if((s->na && !t.ann) || (s->nd && !t.del)){free(t.ann);free(t.del);j->failed=1;return;}
  if(s->na) {memcpy(t.ann,s->ann,(size_t)s->na*sizeof(*t.ann));qsort(t.ann,(size_t)t.na,sizeof(*t.ann),sy_cmp_ann);}
  if(s->nd) {memcpy(t.del,s->del,(size_t)s->nd*sizeof(*t.del));qsort(t.del,(size_t)t.nd,sizeof(*t.del),sy_cmp_del);}
  cv_text_string(j,"\"progress\":");
  if(t.has_progress) {
    cv_text_format(j,"{\"at\":%llu,\"ratio\":%.6f,\"anchor\":%s,\"fixed_page_id\":",(unsigned long long)t.p_at,t.p_ratio,t.p_anchor ? t.p_anchor:"null");
    if(t.p_fixed) cv_text_json(j,t.p_fixed);else cv_text_string(j,"null");
    cv_text_string(j,"}");
  } else cv_text_string(j,"null");
  cv_text_format(j,",\"settings\":{\"at\":%llu,\"values\":%s},\"annotations\":[",(unsigned long long)t.s_at,t.settings ? t.settings:"{}");
  for(int i=0;i<t.na;i++){if(i)cv_text_string(j,",\n");cv_text_string(j,t.ann[i].raw);}
  cv_text_string(j,"],\"deleted\":[");
  for(int i=0;i<t.nd;i++){if(i)cv_text_string(j,",");cv_text_format(j,"{\"key\":\"%s\",\"at\":%llu}",t.del[i].key,(unsigned long long)t.del[i].at);}
  cv_text_string(j,"]");
  free(t.ann);free(t.del);
}
static void sy_serialize(const sy_state *s,cv_text *j) {
  cv_text_format(j,"{\"format\":\"exreader-sync\",\"version\":1,\"book_sha256\":\"%s\",\"revision\":%llu,\"updated_at\":%llu,\"device_id\":",
    s->sha,(unsigned long long)s->revision,(unsigned long long)s->updated_at);
  cv_text_json(j,s->device);cv_text_string(j,",");sy_content(s,j);cv_text_string(j,"}\n");
}
/* "same content" - used for dirty detection and to skip no-op uploads. */
static int sy_same(const sy_state *a,const sy_state *b) {
  cv_text x={0},y={0};sy_content(a,&x);sy_content(b,&y);
  int same=!x.failed && !y.failed && x.size==y.size && !memcmp(x.data,y.data,x.size);
  cv_text_free(&x);cv_text_free(&y);return same;
}
static int sy_state_parse(const char *bytes,size_t size,const char *sha,sy_state *out) {
  memset(out,0,sizeof(*out));
  cv_json *root=sy_parse(bytes,size);
  const cv_json *fmt=cv_json_get(root,"format"),*book=cv_json_get(root,"book_sha256"),*dev=cv_json_get(root,"device_id"),
    *pr=cv_json_get(root,"progress"),*st=cv_json_get(root,"settings"),*an=cv_json_get(root,"annotations"),*de=cv_json_get(root,"deleted");
  uint64_t version=0;
  int ok=root && root->type==CV_JSON_OBJECT && fmt && fmt->type==CV_JSON_STRING && !strcmp(fmt->string,"exreader-sync") &&
    annot_uint(root,"version",&version) && version==1 && book && book->type==CV_JSON_STRING && !strcmp(book->string,sha) &&
    annot_uint(root,"revision",&out->revision) && annot_uint(root,"updated_at",&out->updated_at) &&
    dev && dev->type==CV_JSON_STRING && strlen(dev->string)<sizeof(out->device) &&
    an && an->type==CV_JSON_ARRAY && an->count<=100000 && de && de->type==CV_JSON_ARRAY && de->count<=100000 &&
    st && st->type==CV_JSON_OBJECT;
  if(ok) {strcpy(out->sha,sha);strcpy(out->device,dev->string);}
  if(ok && pr && pr->type!=CV_JSON_NULL) {
    const cv_json *anchor=cv_json_get(pr,"anchor"),*ratio=cv_json_get(pr,"ratio"),*fixed=cv_json_get(pr,"fixed_page_id");
    ok=pr->type==CV_JSON_OBJECT && annot_uint(pr,"at",&out->p_at) && ratio && ratio->type==CV_JSON_NUMBER && ratio->number>=0 && ratio->number<=1 &&
      (!fixed || fixed->type==CV_JSON_NULL || fixed->type==CV_JSON_STRING);
    if(ok){out->has_progress=1;out->p_ratio=ratio->number;}
    if(ok && anchor && anchor->type!=CV_JSON_NULL) {
      exr_content_anchor a={0};
      ok=anchor->type==CV_JSON_OBJECT && annot_endpoint_read(cv_json_get(anchor,"start"),&a.start) && annot_endpoint_read(cv_json_get(anchor,"end"),&a.end);
      exr_content_anchor_free(&a);
      if(ok) ok=(out->p_anchor=sy_copy_json(anchor))!=NULL;
    }
    if(ok && fixed && fixed->type==CV_JSON_STRING) ok=(out->p_fixed=host_strdup(fixed->string))!=NULL;
  }
  if(ok) {
    const cv_json *values=cv_json_get(st,"values");
    ok=annot_uint(st,"at",&out->s_at) && values && values->type==CV_JSON_OBJECT && (out->settings=sy_copy_json(values))!=NULL;
  }
  for(size_t i=0;ok && i<an->count;i++) ok=sy_ann_add(out,an->items[i]);
  for(size_t i=0;ok && i<de->count;i++) {
    const cv_json *k=cv_json_get(de->items[i],"key");uint64_t at=0;
    ok=k && k->type==CV_JSON_STRING && sy_hex64(k->string) && annot_uint(de->items[i],"at",&at) && sy_del_add(out,k->string,at);
  }
  cv_json_free(root);
  if(!ok) sy_state_free(out);
  return ok;
}

/* ---- merge --------------------------------------------------------- */
static int sy_dup_state(sy_state *to,const sy_state *from) {
  *to=*from;to->p_anchor=sy_dup(from->p_anchor);to->p_fixed=sy_dup(from->p_fixed);to->settings=sy_dup(from->settings ? from->settings:"{}");
  to->ann=NULL;to->del=NULL;to->na=to->nd=0;
  int ok=(!from->p_anchor || to->p_anchor) && (!from->p_fixed || to->p_fixed) && to->settings;
  for(int i=0;ok && i<from->na;i++){
    sy_ann *n=realloc(to->ann,((size_t)to->na+1)*sizeof(*n));
    if(!n){ok=0;break;}
    to->ann=n;to->ann[to->na]=from->ann[i];to->ann[to->na].raw=host_strdup(from->ann[i].raw);
    if(!to->ann[to->na].raw){ok=0;break;}
    to->na++;
  }
  for(int i=0;ok && i<from->nd;i++) ok=sy_del_add(to,from->del[i].key,from->del[i].at);
  if(!ok) sy_state_free(to);
  return ok;
}
static int sy_tombstone(const sy_state *s,const char *key,uint64_t *at) {
  for(int i=0;i<s->nd;i++) if(!strcmp(s->del[i].key,key)){*at=s->del[i].at;return 1;}
  return 0;
}
/* out = union(a,b); never drops an annotation that has no newer tombstone. */
static int sy_merge(const sy_state *a,const sy_state *b,uint64_t now,sy_state *out) {
  memset(out,0,sizeof(*out));
  strcpy(out->sha,a->sha);strcpy(out->device,a->device);
  out->revision=(a->revision>b->revision ? a->revision:b->revision)+1;
  out->updated_at=a->updated_at>b->updated_at ? a->updated_at:b->updated_at;
  const sy_state *p=a;
  if(b->has_progress && (!a->has_progress || b->p_at>a->p_at || (b->p_at==a->p_at && b->p_ratio>a->p_ratio))) p=b;
  if((out->has_progress=p->has_progress)) {
    out->p_at=p->p_at;out->p_ratio=p->p_ratio;out->p_anchor=sy_dup(p->p_anchor);out->p_fixed=sy_dup(p->p_fixed);
    if((p->p_anchor && !out->p_anchor) || (p->p_fixed && !out->p_fixed)){sy_state_free(out);return 0;}
  }
  const sy_state *s=a->s_at>=b->s_at ? a:b;
  if(a->s_at==b->s_at && strcmp(a->settings ? a->settings:"{}",b->settings ? b->settings:"{}")<0) s=b; /* same winner on both devices */
  out->s_at=s->s_at;out->settings=sy_dup(s->settings ? s->settings:"{}");
  if(!out->settings){sy_state_free(out);return 0;}
  for(int pass=0;pass<2;pass++) {
    const sy_state *x=pass ? b:a,*y=pass ? a:b;
    for(int i=0;i<x->na;i++) {
      const sy_ann *pick=&x->ann[i],*other=NULL;
      int dup=0;
      for(int k=0;k<out->na;k++) if(!strcmp(out->ann[k].key,pick->key)){dup=1;break;}
      if(dup) continue;
      for(int j=0;j<y->na;j++) if(!strcmp(y->ann[j].key,pick->key)){other=&y->ann[j];break;}
      /* same annotation on both sides: newer edit wins; ties broken by content so every device picks the same one */
      if(other && (other->updated>pick->updated || (other->updated==pick->updated && strcmp(other->raw,pick->raw)>0))) pick=other;
      uint64_t t1=0,t2=0;int d1=sy_tombstone(a,pick->key,&t1),d2=sy_tombstone(b,pick->key,&t2);
      uint64_t t=d1 && (!d2 || t1>t2) ? t1:t2;
      if((d1||d2) && pick->updated<=t) continue; /* deleted after its last edit */
      sy_ann *n=realloc(out->ann,((size_t)out->na+1)*sizeof(*n));
      if(!n){sy_state_free(out);return 0;}
      out->ann=n;out->ann[out->na]=*pick;out->ann[out->na].raw=host_strdup(pick->raw);
      if(!out->ann[out->na].raw){sy_state_free(out);return 0;}
      out->na++;
    }
  }
  for(int pass=0;pass<2;pass++) {
    const sy_state *x=pass ? b:a;
    for(int i=0;i<x->nd;i++) {
      int alive=0;
      for(int k=0;k<out->na;k++) if(!strcmp(out->ann[k].key,x->del[i].key)){alive=1;break;}
      if(alive || (now>SY_TOMBSTONE_MS && x->del[i].at<now-SY_TOMBSTONE_MS)) continue;
      if(!sy_del_add(out,x->del[i].key,x->del[i].at)){sy_state_free(out);return 0;}
    }
  }
  return 1;
}

/* ---- local files --------------------------------------------------- */
static void sy_default_paths(void) {
  /* Same resolution as annot_sync(): environment override, else APPDATA/EXReader/annotations. */
  wchar_t base[HOST_PATH],root[HOST_PATH];
  DWORD n=GetEnvironmentVariableW(L"EXREADER_ANNOTATIONS_DIR",sy_annot_dir,HOST_PATH);
  if(!n || n>=HOST_PATH) {
    n=GetEnvironmentVariableW(L"APPDATA",root,HOST_PATH);
    if(n && n<HOST_PATH) {path_join(base,HOST_PATH,root,L"EXReader");path_join(sy_annot_dir,HOST_PATH,base,L"annotations");}
    else path_join(sy_annot_dir,HOST_PATH,g.data_dir,L"annotations");
  }
  shell_shelf_path(sy_shelf_file);
  path_join(sy_recent_file,HOST_PATH,g.data_dir,L"recent-books.json");
  path_join(sy_sync_dir,HOST_PATH,g.data_dir,L"sync");
  path_join(sy_cfg_file,HOST_PATH,g.data_dir,L"sync.json");
  path_join(sy_cred_file,HOST_PATH,g.data_dir,L"sync.cred");
}
static void sy_book_file(const wchar_t *dir,const char *sha,const wchar_t *suffix,wchar_t out[HOST_PATH]) {
  wchar_t name[160];swprintf(name,160,L"%hs%ls",sha,suffix);path_join(out,HOST_PATH,dir,name);
}
static int sy_read_state_file(const wchar_t *path,const char *sha,sy_state *s) {
  size_t n=0;char *b=sy_read(path,&n);
  if(!b){memset(s,0,sizeof(*s));strcpy(s->sha,sha);s->settings=host_strdup("{}");return s->settings!=NULL;}
  int ok=sy_state_parse(b,n,sha,s);free(b);return ok;
}
/* Settings values from a shelf.json book entry: only real overrides. */
static char *sy_settings_of(const cv_json *entry) {
  cv_text t={0};cv_text_string(&t,"{");int first=1;
  static const char *const keys[]={"title","author","series","series_index"};
  for(int i=0;i<4;i++) {
    const cv_json *v=cv_json_get(entry,keys[i]);
    if(!v || v->type==CV_JSON_NULL || (v->type==CV_JSON_STRING && !v->string[0])) continue;
    if(v->type!=CV_JSON_STRING && v->type!=CV_JSON_NUMBER) continue;
    if(!first) cv_text_string(&t,",");
    first=0;cv_text_json(&t,keys[i]);cv_text_string(&t,":");style_json_copy(&t,v);
  }
  const cv_json *tags=cv_json_get(entry,"tags");
  if(tags && tags->type==CV_JSON_ARRAY && tags->count) {
    if(!first) cv_text_string(&t,",");
    cv_text_string(&t,"\"tags\":");style_json_copy(&t,tags);
  }
  cv_text_string(&t,"}");
  char *out=t.failed ? NULL:host_strdup(t.data);cv_text_free(&t);return out;
}
/* Everything this device knows about one book, as a state. */
static int sy_local(const char *sha,const sy_state *base,sy_state *out) {
  memset(out,0,sizeof(*out));strcpy(out->sha,sha);snprintf(out->device,sizeof(out->device),"%s",sy_device);
  out->revision=base->revision;out->updated_at=base->updated_at;
  out->settings=host_strdup("{}");
  if(!out->settings) return 0;
  uint64_t now=sy_now();int ok=1;
  /* annotations */
  wchar_t path[HOST_PATH];sy_book_file(sy_annot_dir,sha,L".json",path);
  size_t n=0;char *b=sy_read(path,&n);
  if(b) {
    cv_json *root=sy_parse(b,n);const cv_json *list=cv_json_get(root,"annotations"),*h=cv_json_get(root,"book_sha256");
    ok=root && h && h->type==CV_JSON_STRING && !strcmp(h->string,sha) && list && list->type==CV_JSON_ARRAY && list->count<=100000;
    for(size_t i=0;ok && i<list->count;i++) ok=sy_ann_add(out,list->items[i]);
    cv_json_free(root);free(b);
  }
  if(!ok){sy_state_free(out);return 0;}
  /* progress: the shelf-flow entry for this book */
  b=sy_read(sy_recent_file,&n);
  if(b) {
    cv_json *root=sy_parse(b,n);const cv_json *books=cv_json_get(root,"books");
    for(size_t i=0;books && books->type==CV_JSON_ARRAY && i<books->count;i++) {
      const cv_json *o=books->items[i],*h=cv_json_get(o,"book_sha256"),*pr=cv_json_get(o,"progress"),*a=cv_json_get(o,"anchor"),*fx=cv_json_get(o,"fixed_page_id");
      if(!h || h->type!=CV_JSON_STRING || strcmp(h->string,sha) || !pr || pr->type!=CV_JSON_NUMBER) continue;
      uint64_t opened=0;annot_uint(o,"last_opened_ms",&opened);
      out->has_progress=1;out->p_ratio=pr->number;
      out->p_anchor=a && a->type==CV_JSON_OBJECT ? sy_copy_json(a):NULL;
      out->p_fixed=fx && fx->type==CV_JSON_STRING && fx->string[0] ? host_strdup(fx->string):NULL;
      out->p_at=opened;
      break;
    }
    cv_json_free(root);free(b);
    if(out->has_progress && base->has_progress && fabs(base->p_ratio-out->p_ratio)<5e-7 &&
       !strcmp(base->p_anchor ? base->p_anchor:"",out->p_anchor ? out->p_anchor:"") &&
       !strcmp(base->p_fixed ? base->p_fixed:"",out->p_fixed ? out->p_fixed:""))
      out->p_at=base->p_at; /* same place: not a new edit */
    if(!out->has_progress && base->has_progress) {out->has_progress=1;out->p_at=base->p_at;out->p_ratio=base->p_ratio;
      out->p_anchor=sy_dup(base->p_anchor);out->p_fixed=sy_dup(base->p_fixed);}
  }
  /* settings: the shelf.json entry */
  b=sy_read(sy_shelf_file,&n);
  if(b) {
    cv_json *root=sy_parse(b,n);const cv_json *books=cv_json_get(root,"books");
    for(size_t i=0;books && books->type==CV_JSON_ARRAY && i<books->count;i++) {
      const cv_json *h=cv_json_get(books->items[i],"sha256");
      if(!h || h->type!=CV_JSON_STRING || strcmp(h->string,sha)) continue;
      char *s=sy_settings_of(books->items[i]);
      if(s){free(out->settings);out->settings=s;}
      break;
    }
    cv_json_free(root);free(b);
  }
  out->s_at=base->s_at;
  if(strcmp(out->settings,base->settings ? base->settings:"{}")) out->s_at=now;
  /* deletions since the last merge become tombstones */
  for(int i=0;i<base->nd;i++) sy_del_add(out,base->del[i].key,base->del[i].at);
  for(int i=0;i<base->na;i++) {
    int still=0;for(int j=0;j<out->na;j++) if(!strcmp(out->ann[j].key,base->ann[i].key)){still=1;break;}
    if(!still && !sy_tombstone(out,base->ann[i].key,&(uint64_t){0})) sy_del_add(out,base->ann[i].key,now);
  }
  for(int i=0;i<out->na;i++) { /* re-created after a tombstone with a newer edit: alive again */
    uint64_t t;
    if(sy_tombstone(out,out->ann[i].key,&t) && out->ann[i].updated>t)
      for(int k=0;k<out->nd;k++) if(!strcmp(out->del[k].key,out->ann[i].key)){out->del[k]=out->del[--out->nd];break;}
  }
  sy_state probe=*out;probe.revision=base->revision;
  if(!sy_same(&probe,base)) out->updated_at=now;
  return 1;
}
static int sy_has_data(const sy_state *s) {return s->na || s->nd || s->has_progress || (s->settings && strcmp(s->settings,"{}"));}

/* Books this device knows: shelf, metadata and annotation files. */
static int sy_books(char (**out)[65]) {
  char (*list)[65]=NULL;int n=0,cap=0;
  #define SY_ADD(sha) do{ int dup_=0;for(int q_=0;q_<n;q_++) if(!strcmp(list[q_],(sha))){dup_=1;break;} \
    if(!dup_ && sy_hex64(sha)){ if(n==cap){cap=cap ? cap*2:32;char (*g_)[65]=realloc(list,(size_t)cap*65);if(!g_){free(list);return -1;}list=g_;} strcpy(list[n++],(sha)); } }while(0)
  size_t size=0;char *b=sy_read(sy_recent_file,&size);
  if(b){cv_json *r=sy_parse(b,size);const cv_json *bk=cv_json_get(r,"books");
    for(size_t i=0;bk && bk->type==CV_JSON_ARRAY && i<bk->count;i++){const cv_json *h=cv_json_get(bk->items[i],"book_sha256");if(h && h->type==CV_JSON_STRING)SY_ADD(h->string);}
    cv_json_free(r);free(b);}
  b=sy_read(sy_shelf_file,&size);
  if(b){cv_json *r=sy_parse(b,size);const cv_json *bk=cv_json_get(r,"books");
    for(size_t i=0;bk && bk->type==CV_JSON_ARRAY && i<bk->count;i++){const cv_json *h=cv_json_get(bk->items[i],"sha256");if(h && h->type==CV_JSON_STRING)SY_ADD(h->string);}
    cv_json_free(r);free(b);}
  wchar_t pattern[HOST_PATH];path_join(pattern,HOST_PATH,sy_annot_dir,L"*.json");
  WIN32_FIND_DATAW fd;HANDLE h=FindFirstFileW(pattern,&fd);
  if(h!=INVALID_HANDLE_VALUE){do{
    char name[300];WideCharToMultiByte(CP_UTF8,0,fd.cFileName,-1,name,sizeof(name),NULL,NULL);
    if(strlen(name)==69 && !strcmp(name+64,".json")){name[64]=0;SY_ADD(name);}
  }while(FindNextFileW(h,&fd));FindClose(h);}
  #undef SY_ADD
  *out=list;return n;
}

/* ---- HTTP (WinHTTP) ------------------------------------------------ */
typedef struct { int status; DWORD werr; char *body; size_t size; char etag[160]; } sy_resp;
static void sy_resp_free(sy_resp *r) {free(r->body);memset(r,0,sizeof(*r));}
typedef struct { wchar_t host[256]; INTERNET_PORT port; int secure; char path[512]; } sy_target;
static int sy_target_parse(const char *url,sy_target *t) {
  memset(t,0,sizeof(*t));
  if(!url) return 0;
  const char *p;
  if(!_strnicmp(url,"https://",8)){t->secure=1;p=url+8;} else if(!_strnicmp(url,"http://",7)) p=url+7; else return 0;
  const char *slash=strchr(p,'/');size_t alen=slash ? (size_t)(slash-p):strlen(p);
  if(!alen || alen>=255 || memchr(p,'@',alen)) return 0; /* userinfo is refused: credentials live in sync.cred only */
  for(const char *c=url;*c;c++) if((unsigned char)*c<=' ' || *c=='?' || *c=='#') return 0;
  char auth[256];memcpy(auth,p,alen);auth[alen]=0;
  char *colon=strrchr(auth,':');long port=t->secure ? 443:80;
  if(colon && auth[0]!='[') {char *end;port=strtol(colon+1,&end,10);if(*end || port<1 || port>65535) return 0;*colon=0;}
  if(!auth[0]) return 0;
  MultiByteToWideChar(CP_UTF8,0,auth,-1,t->host,256);t->port=(INTERNET_PORT)port;
  snprintf(t->path,sizeof(t->path),"%s",slash ? slash:"/");
  size_t pl=strlen(t->path);if(t->path[pl-1]!='/'){if(pl+1>=sizeof(t->path)) return 0;t->path[pl]='/';t->path[pl+1]=0;}
  return 1;
}
static int sy_b64(const char *in,size_t n,char *out) {
  static const char t[]="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  size_t o=0;
  for(size_t i=0;i<n;i+=3) {
    unsigned v=(unsigned char)in[i]<<16|(i+1<n ? (unsigned char)in[i+1]<<8:0)|(i+2<n ? (unsigned char)in[i+2]:0);
    out[o++]=t[v>>18&63];out[o++]=t[v>>12&63];out[o++]=i+1<n ? t[v>>6&63]:'=';out[o++]=i+2<n ? t[v&63]:'=';
  }
  out[o]=0;return (int)o;
}
static int sy_loopback(const wchar_t *h) {return !_wcsicmp(h,L"localhost") || !wcscmp(h,L"127.0.0.1") || !wcscmp(h,L"::1") || !wcscmp(h,L"[::1]");}
/* One attempt. 0 = no HTTP response (see werr). */
static int sy_http_once(const sy_target *t,const wchar_t *method,const char *rel,const char *body,size_t n,const wchar_t *extra,sy_resp *r) {
  memset(r,0,sizeof(*r));
  wchar_t headers[1536];headers[0]=0;
  HINTERNET session=WinHttpOpen(L"EXReader-Sync/1",sy_loopback(t->host) ? WINHTTP_ACCESS_TYPE_NO_PROXY:WINHTTP_ACCESS_TYPE_AUTOMATIC_PROXY,
    WINHTTP_NO_PROXY_NAME,WINHTTP_NO_PROXY_BYPASS,0);
  HINTERNET conn=NULL,req=NULL;int ok=0;
  if(!session){r->werr=GetLastError();return 0;}
  WinHttpSetTimeouts(session,(int)sy_timeout_ms,(int)sy_timeout_ms,(int)sy_timeout_ms,(int)sy_timeout_ms);
  conn=WinHttpConnect(session,t->host,t->port,0);
  if(!conn){r->werr=GetLastError();goto done;}
  wchar_t object[1024];char full[1024];snprintf(full,sizeof(full),"%s%s",t->path,rel ? rel:"");
  if(!MultiByteToWideChar(CP_UTF8,0,full,-1,object,1024)){r->werr=ERROR_INVALID_PARAMETER;goto done;}
  req=WinHttpOpenRequest(conn,method,object,NULL,WINHTTP_NO_REFERER,WINHTTP_DEFAULT_ACCEPT_TYPES,t->secure ? WINHTTP_FLAG_SECURE:0);
  if(!req){r->werr=GetLastError();goto done;}
  DWORD feature=WINHTTP_DISABLE_REDIRECTS; /* never forward the password to another URL */
  WinHttpSetOption(req,WINHTTP_OPTION_DISABLE_FEATURE,&feature,sizeof(feature));
  if(sy_user && sy_pass) {
    char cred[512],enc[720];snprintf(cred,sizeof(cred),"%s:%s",sy_user,sy_pass);
    sy_b64(cred,strlen(cred),enc);SecureZeroMemory(cred,sizeof(cred));
    swprintf(headers,1536,L"Authorization: Basic %hs\r\n",enc);SecureZeroMemory(enc,sizeof(enc));
  }
  if(extra) wcsncat(headers,extra,1535-wcslen(headers));
  if(!WinHttpSendRequest(req,headers[0] ? headers:WINHTTP_NO_ADDITIONAL_HEADERS,headers[0] ? (DWORD)-1L:0,(LPVOID)body,(DWORD)n,(DWORD)n,0) ||
     !WinHttpReceiveResponse(req,NULL)){r->werr=GetLastError();goto done;}
  DWORD status=0,len=sizeof(status);
  if(!WinHttpQueryHeaders(req,WINHTTP_QUERY_STATUS_CODE|WINHTTP_QUERY_FLAG_NUMBER,WINHTTP_HEADER_NAME_BY_INDEX,&status,&len,WINHTTP_NO_HEADER_INDEX)){r->werr=GetLastError();goto done;}
  r->status=(int)status;
  wchar_t etag[160];len=sizeof(etag);
  if(WinHttpQueryHeaders(req,WINHTTP_QUERY_CUSTOM,L"ETag",etag,&len,WINHTTP_NO_HEADER_INDEX))
    WideCharToMultiByte(CP_UTF8,0,etag,-1,r->etag,sizeof(r->etag),NULL,NULL);
  size_t cap=0;
  for(;;) {
    DWORD avail=0;
    if(!WinHttpQueryDataAvailable(req,&avail)){r->werr=GetLastError();r->status=0;break;}
    if(!avail) break;
    if(r->size+avail>SY_MAX_BYTES){r->werr=ERROR_FILE_TOO_LARGE;r->status=0;break;}
    if(r->size+avail+1>cap){cap=(r->size+avail+1)*2;char *g=realloc(r->body,cap);if(!g){r->werr=ERROR_NOT_ENOUGH_MEMORY;r->status=0;break;}r->body=g;}
    DWORD got=0;
    if(!WinHttpReadData(req,r->body+r->size,avail,&got)){r->werr=GetLastError();r->status=0;break;}
    r->size+=got;
  }
  if(r->body) r->body[r->size]=0;
  ok=r->status!=0;
done:
  SecureZeroMemory(headers,sizeof(headers));
  if(req) WinHttpCloseHandle(req);
  if(conn) WinHttpCloseHandle(conn);
  WinHttpCloseHandle(session);
  return ok;
}
static int sy_transient(const sy_resp *r) {
  if(!r->status) return r->werr!=ERROR_FILE_TOO_LARGE && r->werr!=ERROR_INVALID_PARAMETER && r->werr!=ERROR_NOT_ENOUGH_MEMORY;
  return r->status==408 || r->status==429 || (r->status>=500 && r->status!=501 && r->status!=507);
}
/* Up to 3 attempts for network errors / 5xx / 408 / 429, 300 ms then 600 ms apart.
   A 401/404 etc. is a definite answer and returns at once. */
static int sy_http(const sy_target *t,const wchar_t *method,const char *rel,const char *body,size_t n,const wchar_t *extra,sy_resp *r) {
  int ok=0;
  for(int attempt=0;attempt<3;attempt++) {
    if(attempt) {sy_resp_free(r);Sleep(sy_backoff_ms<<(attempt-1));}
    ok=sy_http_once(t,method,rel,body,n,extra,r);
    if(!sy_transient(r)) break;
  }
  return ok;
}
/* Readable reason; fills s and returns the SY_* class. what = what we were doing. */
static int sy_explain(const sy_resp *r,const char *what,sy_status *s) {
  if(!r->status) {
    switch(r->werr) {
      case ERROR_WINHTTP_TIMEOUT: sy_status_set(s,SY_TIMEOUT,"%s失败：连接超时，服务器长时间没有响应。",what);return SY_TIMEOUT;
      case ERROR_WINHTTP_NAME_NOT_RESOLVED: sy_status_set(s,SY_OFFLINE,"%s失败：无法解析服务器域名（网络未连接或地址拼写错误）。",what);return SY_OFFLINE;
      case ERROR_WINHTTP_CANNOT_CONNECT: case ERROR_WINHTTP_CONNECTION_ERROR:
        sy_status_set(s,SY_OFFLINE,"%s失败：无法连接服务器（网络已断开，或服务器未运行）。",what);return SY_OFFLINE;
      case ERROR_WINHTTP_SECURE_FAILURE: case ERROR_WINHTTP_SECURE_INVALID_CA: case ERROR_WINHTTP_SECURE_CERT_CN_INVALID:
      case ERROR_WINHTTP_SECURE_CERT_DATE_INVALID: case ERROR_WINHTTP_SECURE_INVALID_CERT:
        sy_status_set(s,SY_TLS,"%s失败：HTTPS 证书无效或已过期。",what);return SY_TLS;
      case ERROR_FILE_TOO_LARGE: sy_status_set(s,SY_SERVER,"%s失败：服务器返回的数据过大。",what);return SY_SERVER;
      default: sy_status_set(s,SY_OFFLINE,"%s失败：网络错误（代码 %lu）。",what,(unsigned long)r->werr);return SY_OFFLINE;
    }
  }
  int c=r->status;
  if(c>=200 && c<300) {sy_status_set(s,SY_OK,"%s成功。",what);return SY_OK;}
  if(c==401) {sy_status_set(s,SY_AUTH,"%s失败：认证失败（HTTP 401），用户名或密码不正确。",what);return SY_AUTH;}
  if(c==403) {sy_status_set(s,SY_AUTH,"%s失败：拒绝访问（HTTP 403），该账号对此目录没有读写权限。",what);return SY_AUTH;}
  if(c==404) {sy_status_set(s,SY_NOTFOUND,"%s失败：找不到同步目录（HTTP 404），请检查服务器地址与路径。",what);return SY_NOTFOUND;}
  if(c==405 || c==501) {sy_status_set(s,SY_UNSUPPORTED,"%s失败：服务器不支持所需的 WebDAV 方法（HTTP %d）。",what,c);return SY_UNSUPPORTED;}
  if(c==409) {sy_status_set(s,SY_SERVER,"%s失败：上级目录不存在（HTTP 409）。",what);return SY_SERVER;}
  if(c==412) {sy_status_set(s,SY_CONFLICT,"%s失败：远端已被其他设备更新（HTTP 412）。",what);return SY_CONFLICT;}
  if(c==423) {sy_status_set(s,SY_SERVER,"%s失败：文件被服务器锁定（HTTP 423）。",what);return SY_SERVER;}
  if(c==507) {sy_status_set(s,SY_SERVER,"%s失败：服务器存储空间已满（HTTP 507）。",what);return SY_SERVER;}
  if(c>=300 && c<400) {sy_status_set(s,SY_CONFIG,"%s失败：服务器要求跳转（HTTP %d）。为保护密码不会自动跳转，请改用最终地址（常见原因：http 与 https 之分、缺少末尾 /）。",what,c);return SY_CONFIG;}
  if(c>=500) {sy_status_set(s,SY_SERVER,"%s失败：服务器内部错误（HTTP %d）。",what,c);return SY_SERVER;}
  sy_status_set(s,SY_SERVER,"%s失败：服务器返回意外状态 HTTP %d。",what,c);return SY_SERVER;
}
static int sy_offline_class(int code) {return code==SY_OFFLINE || code==SY_TIMEOUT || code==SY_SERVER;}

/* ---- server operations --------------------------------------------- */
/* PROPFIND the base collection: proves URL + credentials and lists which books exist remotely. */
static int sy_remote_list(const sy_target *t,char (**shas)[65],int *count,int *unsupported,sy_status *s) {
  static const char body[]="<?xml version=\"1.0\"?><propfind xmlns=\"DAV:\"><prop><resourcetype/></prop></propfind>";
  sy_resp r;*shas=NULL;*count=0;*unsupported=0;
  sy_http(t,L"PROPFIND","",body,sizeof(body)-1,L"Depth: 1\r\nContent-Type: application/xml\r\n",&r);
  int code=r.status==207 || r.status==200 ? SY_OK:sy_explain(&r,"连接服务器",s);
  if(code==SY_UNSUPPORTED){*unsupported=1;sy_resp_free(&r);return SY_OK;}
  if(code==SY_OK && r.body) {
    int cap=0;
    for(size_t i=0;i+64<=r.size;i++) {
      if(i>0 && r.body[i-1]!='/' && r.body[i-1]!='>') continue;
      if(i+64>=r.size || (r.body[i+64]!='/' && r.body[i+64]!='<')) continue;
      char sha[65];memcpy(sha,r.body+i,64);sha[64]=0;
      if(!sy_hex64(sha)) continue;
      int dup=0;for(int k=0;k<*count;k++) if(!strcmp((*shas)[k],sha)){dup=1;break;}
      if(dup) continue;
      if(*count==cap){cap=cap ? cap*2:32;char (*g)[65]=realloc(*shas,(size_t)cap*65);if(!g){code=SY_LOCAL;break;}*shas=g;}
      strcpy((*shas)[(*count)++],sha);i+=63;
    }
  }
  if(code==SY_OK) sy_status_set(s,SY_OK,"已连接服务器。");
  sy_resp_free(&r);return code;
}
static int sy_remote_get(const sy_target *t,const char *sha,sy_state *out,char etag[160],int *found,sy_status *s) {
  char rel[160];snprintf(rel,sizeof(rel),"%s/state.json",sha);sy_resp r;
  *found=0;etag[0]=0;memset(out,0,sizeof(*out));
  sy_http(t,L"GET",rel,NULL,0,NULL,&r);
  if(r.status==404){sy_resp_free(&r);return SY_OK;}
  int code=sy_explain(&r,"读取远端状态",s);
  if(code==SY_OK) {
    if(!r.body || !sy_state_parse(r.body,r.size,sha,out)) {
      sy_status_set(s,SY_LOCAL,"远端状态文件损坏或版本不受支持（%.8s…），已跳过这本书，未覆盖远端。",sha);code=SY_LOCAL;
    } else {*found=1;snprintf(etag,160,"%s",r.etag);}
  }
  sy_resp_free(&r);return code;
}
/* conditional: etag -> If-Match; no etag + create -> If-None-Match: *. */
static int sy_remote_put(const sy_target *t,const char *sha,const char *json,size_t n,const char *etag,int create,sy_status *s) {
  char rel[160];snprintf(rel,sizeof(rel),"%s/state.json",sha);sy_resp r;wchar_t extra[400];
  swprintf(extra,400,L"Content-Type: application/json\r\n");
  if(etag && etag[0] && strncmp(etag,"W/",2)) swprintf(extra+wcslen(extra),400-wcslen(extra),L"If-Match: %hs\r\n",etag);
  else if(create) wcscat(extra,L"If-None-Match: *\r\n");
  sy_http(t,L"PUT",rel,json,n,extra,&r);
  int code=sy_explain(&r,"上传",s);
  sy_resp_free(&r);return code;
}
static int sy_remote_mkcol(const sy_target *t,const char *sha,sy_status *s) {
  char rel[160];snprintf(rel,sizeof(rel),"%s/",sha);sy_resp r;
  sy_http(t,L"MKCOL",rel,NULL,0,NULL,&r);
  int code=r.status==405 ? SY_OK:sy_explain(&r,"创建远端目录",s); /* 405 = already exists */
  sy_resp_free(&r);return code;
}

/* ---- per-book network phase (worker-safe) --------------------------- */
static int sy_net_book(const sy_target *t,const char *sha,int remote_known,int remote_exists,sy_result *res,sy_status *s) {
  sy_state base={0},local={0},remote={0},merged={0};
  wchar_t bf[HOST_PATH];char etag[160];int found=0,code=SY_OK;
  sy_book_file(sy_sync_dir,sha,L".base.json",bf);
  memset(res,0,sizeof(*res));strcpy(res->sha,sha);
  if(!sy_read_state_file(bf,sha,&base)){sy_status_set(s,SY_LOCAL,"本地同步基线损坏（%.8s…），已跳过。",sha);return SY_LOCAL;}
  if(!sy_local(sha,&base,&local)){sy_status_set(s,SY_LOCAL,"本地标注或阅读记录无法解析（%.8s…），已跳过这本书，未覆盖任何数据。",sha);sy_state_free(&base);return SY_LOCAL;}
  int dirty=!sy_same(&local,&base);
  if(remote_known && !remote_exists) {found=0;etag[0]=0;}
  else {code=sy_remote_get(t,sha,&remote,etag,&found,s);if(code!=SY_OK) goto done;}
  /* A device that has never synced this book and merely opened it (page 1, "just now") must not
     reset the real reading position stored in the cloud: on a first sync the furthest position wins. */
  if(found && !base.has_progress && local.has_progress && remote.has_progress && local.p_ratio<remote.p_ratio) local.p_at=0;
  if(!found && !sy_has_data(&local)) goto done;     /* nothing anywhere */
  if(found && !dirty && remote.revision==base.revision && sy_same(&remote,&base)) goto done; /* up to date */
  for(int round=0;round<4;round++) {
    if(found){if(!sy_merge(&local,&remote,sy_now(),&merged)){sy_status_set(s,SY_LOCAL,"内存不足，无法合并。");code=SY_LOCAL;goto done;}}
    else {if(!sy_dup_state(&merged,&local)){sy_status_set(s,SY_LOCAL,"内存不足，无法合并。");code=SY_LOCAL;goto done;}merged.revision=base.revision+1;}
    if(found && sy_same(&merged,&remote)) { /* remote already has everything: adopt, no upload */
      merged.revision=remote.revision;strcpy(merged.device,remote.device);merged.updated_at=remote.updated_at;res->pulled=!sy_same(&local,&merged);break;
    }
    if(!merged.updated_at) merged.updated_at=sy_now();
    cv_text j={0};sy_serialize(&merged,&j);
    if(j.failed || j.size>SY_MAX_BYTES){cv_text_free(&j);sy_status_set(s,SY_LOCAL,"状态文件过大。");code=SY_LOCAL;goto done;}
    if(!found) {code=sy_remote_mkcol(t,sha,s);if(code!=SY_OK){cv_text_free(&j);goto done;}}
    code=sy_remote_put(t,sha,j.data,j.size,found ? etag:NULL,!found,s);
    cv_text_free(&j);
    if(code==SY_CONFLICT) { /* another device wrote between our GET and PUT: merge again on top of theirs */
      sy_state_free(&merged);sy_state_free(&remote);
      code=sy_remote_get(t,sha,&remote,etag,&found,s);if(code!=SY_OK) goto done;
      continue;
    }
    if(code!=SY_OK) goto done;
    res->pushed=1;res->pulled=!sy_same(&local,&merged);break;
  }
  if(code==SY_CONFLICT) sy_status_set(s,SY_CONFLICT,"多台设备同时在写，已放弃本轮，稍后自动重试。");
  if(code==SY_OK && merged.sha[0]) {res->merged=merged;memset(&merged,0,sizeof(merged));}
done:
  sy_state_free(&base);sy_state_free(&local);sy_state_free(&remote);sy_state_free(&merged);
  if(code!=SY_OK) res->failed=1;
  return code;
}

/* ---- apply (UI thread) ---------------------------------------------- */
/* Rebuild a top-level array file with one entry replaced (or appended). */
static int sy_json_member(cv_text *j,const cv_json *o,const char *const *skip,int nskip) {
  int first=1;cv_text_string(j,"{");
  for(size_t i=0;i<o->count;i++) {
    int drop=0;for(int k=0;k<nskip;k++) if(!strcmp(o->keys[i],skip[k])) drop=1;
    if(drop) continue;
    if(!first) cv_text_string(j,",");
    first=0;cv_text_json(j,o->keys[i]);cv_text_string(j,":");style_json_copy(j,o->items[i]);
  }
  return !first;
}
static int sy_apply_progress(const sy_state *m,int *wrote) {
  if(!m->has_progress) return 1;
  size_t n=0;char *b=sy_read(sy_recent_file,&n);if(!b) return 1; /* book not on this device's shelf */
  cv_json *root=sy_parse(b,n);const cv_json *books=cv_json_get(root,"books");int ok=1,hit=-1;
  for(size_t i=0;books && books->type==CV_JSON_ARRAY && i<books->count;i++) {
    const cv_json *h=cv_json_get(books->items[i],"book_sha256");
    if(h && h->type==CV_JSON_STRING && !strcmp(h->string,m->sha)) hit=(int)i;
  }
  if(hit<0){cv_json_free(root);free(b);return 1;}
  sy_state cur={0};
  {sy_state none={0};strcpy(none.sha,m->sha);none.settings=host_strdup("{}");
   int got=sy_local(m->sha,&none,&cur);free(none.settings);if(!got){cv_json_free(root);free(b);return 0;}}
  int newer=m->p_at>cur.p_at || !cur.has_progress;
  int same=cur.has_progress && fabs(cur.p_ratio-m->p_ratio)<5e-7 && !strcmp(cur.p_anchor ? cur.p_anchor:"",m->p_anchor ? m->p_anchor:"") &&
    !strcmp(cur.p_fixed ? cur.p_fixed:"",m->p_fixed ? m->p_fixed:"");
  sy_state_free(&cur);
  if(!newer || same){cv_json_free(root);free(b);return 1;}
  cv_text j={0};static const char *const skip[]={"progress","anchor","fixed_page_id","last_opened_ms"};
  cv_text_string(&j,"{");int first=1;
  for(size_t i=0;i<root->count;i++) {
    if(!first) cv_text_string(&j,",");
    first=0;cv_text_json(&j,root->keys[i]);cv_text_string(&j,":");
    if(strcmp(root->keys[i],"books")){style_json_copy(&j,root->items[i]);continue;}
    cv_text_string(&j,"[");
    for(size_t k=0;k<books->count;k++) {
      if(k) cv_text_string(&j,",");
      if((int)k!=hit){style_json_copy(&j,books->items[k]);continue;}
      sy_json_member(&j,books->items[k],skip,4);
      cv_text_format(&j,",\"last_opened_ms\":%llu,\"progress\":%.6f,\"fixed_page_id\":",(unsigned long long)m->p_at,m->p_ratio);
      if(m->p_fixed) cv_text_json(&j,m->p_fixed);else cv_text_string(&j,"null");
      cv_text_format(&j,",\"anchor\":%s}",m->p_anchor ? m->p_anchor:"null");
    }
    cv_text_string(&j,"]");
  }
  cv_text_string(&j,"}\n");
  ok=!j.failed && sy_write(sy_recent_file,j.data,j.size);
  if(ok) *wrote=1;
  cv_text_free(&j);cv_json_free(root);free(b);return ok;
}
static int sy_apply_settings(const sy_state *m,int *wrote) {
  size_t n=0;char *b=sy_read(sy_shelf_file,&n);
  cv_json *root=b ? sy_parse(b,n):NULL;
  if(b && !root){free(b);return 0;} /* unparsable shelf.json is never rewritten */
  cv_json *vals=sy_parse(m->settings ? m->settings:"{}",strlen(m->settings ? m->settings:"{}"));
  if(!vals){cv_json_free(root);free(b);return 0;}
  const cv_json *books=cv_json_get(root,"books");int hit=-1;
  for(size_t i=0;books && books->type==CV_JSON_ARRAY && i<books->count;i++) {
    const cv_json *h=cv_json_get(books->items[i],"sha256");
    if(h && h->type==CV_JSON_STRING && !strcmp(h->string,m->sha)) hit=(int)i;
  }
  int empty=!vals->count;
  if(hit<0 && empty){cv_json_free(vals);cv_json_free(root);free(b);return 1;}
  char *cur=hit>=0 ? sy_settings_of(books->items[hit]):host_strdup("{}");
  char *want=sy_copy_json(vals);
  int same=cur && want && !strcmp(cur,want);
  free(cur);free(want);
  if(same){cv_json_free(vals);cv_json_free(root);free(b);return 1;}
  static const char *const skip[]={"title","author","series","series_index","tags"};
  cv_text j={0};cv_text_string(&j,"{");int first=1,wrote_books=0;
  for(size_t i=0;root && i<root->count;i++) {
    if(!first) cv_text_string(&j,",");
    first=0;cv_text_json(&j,root->keys[i]);cv_text_string(&j,":");
    if(strcmp(root->keys[i],"books")){style_json_copy(&j,root->items[i]);continue;}
    wrote_books=1;cv_text_string(&j,"[");
    for(size_t k=0;k<books->count;k++) {
      if(k) cv_text_string(&j,",");
      if((int)k!=hit){style_json_copy(&j,books->items[k]);continue;}
      sy_json_member(&j,books->items[k],skip,5);
      for(size_t v=0;v<vals->count;v++){cv_text_string(&j,",");cv_text_json(&j,vals->keys[v]);cv_text_string(&j,":");style_json_copy(&j,vals->items[v]);}
      cv_text_string(&j,"}");
    }
    cv_text_string(&j,"]");
  }
  if(!wrote_books) { /* no list yet (or no shelf.json): add a minimal entry */
    if(!first) cv_text_string(&j,",");
    cv_text_format(&j,"\"version\":%d,\"books\":[{\"sha256\":\"%s\"",SM_VERSION,m->sha);
    for(size_t v=0;v<vals->count;v++){cv_text_string(&j,",");cv_text_json(&j,vals->keys[v]);cv_text_string(&j,":");style_json_copy(&j,vals->items[v]);}
    cv_text_string(&j,"}]");
  }
  cv_text_string(&j,"}\n");
  int ok=!j.failed && j.size<SY_MAX_BYTES && sy_write(sy_shelf_file,j.data,j.size);
  if(ok) *wrote=1;
  cv_text_free(&j);cv_json_free(vals);cv_json_free(root);free(b);return ok;
}
static int sy_apply_annotations(const sy_state *m,int *changed) {
  sy_state none={0},cur={0};strcpy(none.sha,m->sha);none.settings=host_strdup("{}");
  int ok=sy_local(m->sha,&none,&cur);free(none.settings);
  if(!ok) return 0;
  /* union with whatever the user added while the network phase ran */
  cv_text j={0};
  sy_state out={0};
  if(!sy_merge(&cur,m,sy_now(),&out)){sy_state_free(&cur);return 0;}
  /* sy_merge bumped the revision; the file itself carries none. Compare only annotations. */
  int differs=out.na!=cur.na;
  for(int i=0;!differs && i<out.na;i++) {
    int match=0;for(int k=0;k<cur.na;k++) if(!strcmp(cur.ann[k].key,out.ann[i].key) && !strcmp(cur.ann[k].raw,out.ann[i].raw)) match=1;
    if(!match) differs=1;
  }
  if(differs) {
    cv_text_format(&j,"{\"version\":1,\"book_sha256\":\"%s\",\"annotations\":[\n",m->sha);
    for(int i=0;i<out.na;i++){if(i)cv_text_string(&j,",\n");cv_text_string(&j,out.ann[i].raw);}
    cv_text_string(&j,"\n]}\n");
    wchar_t path[HOST_PATH];sy_book_file(sy_annot_dir,m->sha,L".json",path);
    ok=ensure_directory(sy_annot_dir) && !j.failed && sy_write(path,j.data,j.size);
    if(ok) *changed=1;
  }
  cv_text_free(&j);sy_state_free(&out);sy_state_free(&cur);return ok;
}
/* Make this device match the merged state and record it as the new baseline. */
enum { SY_CHANGED_ANNOTATIONS=1,SY_CHANGED_PROGRESS=2,SY_CHANGED_SETTINGS=4 };
static int sy_apply(const sy_state *m,int *ui_changed) {
  int ann=0,prog=0,set=0;
  if(!sy_apply_annotations(m,&ann)) return 0;
  if(!sy_apply_progress(m,&prog) || !sy_apply_settings(m,&set)) return 0;
  wchar_t bf[HOST_PATH];cv_text j={0};
  if(!ensure_directory(sy_sync_dir)) return 0;
  sy_serialize(m,&j);sy_book_file(sy_sync_dir,m->sha,L".base.json",bf);
  int ok=!j.failed && sy_write(bf,j.data,j.size);cv_text_free(&j);
  if(ok && ui_changed) *ui_changed|=(ann ? SY_CHANGED_ANNOTATIONS:0)|(prog ? SY_CHANGED_PROGRESS:0)|(set ? SY_CHANGED_SETTINGS:0);
  return ok;
}

/* ---- config, credentials, queue ------------------------------------- */
static int sy_cred_save(const char *user,const char *pass) {
  char blob[1100];int n=snprintf(blob,sizeof(blob),"EXRS1\n%s\n%s",user,pass);
  if(n<=0 || n>=(int)sizeof(blob)) return 0;
  DATA_BLOB in={(DWORD)n,(BYTE *)blob},entropy={14,(BYTE *)"EXReader-sync1"},out={0};
  int ok=CryptProtectData(&in,L"EXReader WebDAV",&entropy,NULL,NULL,CRYPTPROTECT_UI_FORBIDDEN,&out)!=0;
  if(ok) {ok=ensure_directory(g.data_dir) && sy_write(sy_cred_file,out.pbData,out.cbData);LocalFree(out.pbData);}
  SecureZeroMemory(blob,sizeof(blob));return ok;
}
static int sy_cred_load(void) {
  size_t n=0;char *b=sy_read(sy_cred_file,&n);if(!b) return 0;
  DATA_BLOB in={(DWORD)n,(BYTE *)b},entropy={14,(BYTE *)"EXReader-sync1"},out={0};
  int ok=CryptUnprotectData(&in,NULL,&entropy,NULL,NULL,CRYPTPROTECT_UI_FORBIDDEN,&out)!=0;
  free(b);
  if(!ok) return 0;
  char *text=malloc(out.cbData+1);
  if(text) {
    memcpy(text,out.pbData,out.cbData);text[out.cbData]=0;
    char *u=strchr(text,'\n'),*p=u ? strchr(u+1,'\n'):NULL;
    if(!strncmp(text,"EXRS1\n",6) && u && p) {
      *p=0;sy_wipe(&sy_user);sy_wipe(&sy_pass);sy_user=host_strdup(u+1);sy_pass=host_strdup(p+1);ok=sy_user && sy_pass;
    } else ok=0;
    SecureZeroMemory(text,out.cbData);free(text);
  } else ok=0;
  SecureZeroMemory(out.pbData,out.cbData);LocalFree(out.pbData);return ok;
}
static void sy_cred_delete(void) {DeleteFileW(sy_cred_file);sy_wipe(&sy_user);sy_wipe(&sy_pass);}
static void sy_new_device(void) {
  BYTE r[8];HCRYPTPROV p=0;
  if(CryptAcquireContextW(&p,NULL,NULL,PROV_RSA_AES,CRYPT_VERIFYCONTEXT)){CryptGenRandom(p,8,r);CryptReleaseContext(p,0);}
  else memset(r,0x5a,8);
  snprintf(sy_device,sizeof(sy_device),"win-%02x%02x%02x%02x%02x%02x%02x%02x",r[0],r[1],r[2],r[3],r[4],r[5],r[6],r[7]);
}
/* sync.json: nothing secret - URL, device id, last result, draft queue. */
static int sy_config_save(void) {
  cv_text j={0};cv_text_string(&j,"{\"version\":1,\"url\":");
  if(sy_url) cv_text_json(&j,sy_url);else cv_text_string(&j,"null");
  cv_text_string(&j,",\"device_id\":");cv_text_json(&j,sy_device);
  cv_text_format(&j,",\"auto\":%s,\"last_sync_ms\":%llu,\"last_code\":%d,\"last_text\":",sy_enabled_auto ? "true":"false",(unsigned long long)sy_last_ms,sy_last_code);
  cv_text_json(&j,sy_last_text);cv_text_string(&j,",\"queue\":[");
  for(int i=0;i<sy_queue_count;i++){if(i)cv_text_string(&j,",");cv_text_format(&j,"{\"sha256\":\"%s\",\"queued_ms\":%llu}",sy_queue[i].sha,(unsigned long long)sy_queue[i].queued);}
  cv_text_string(&j,"]}\n");
  int ok=!j.failed && ensure_directory(g.data_dir) && sy_write(sy_cfg_file,j.data,j.size);
  cv_text_free(&j);return ok;
}
static void sy_queue_clear(void) {free(sy_queue);sy_queue=NULL;sy_queue_count=0;}
static void sy_queue_add(const char *sha) {
  if(!sy_hex64(sha)) return;
  for(int i=0;i<sy_queue_count;i++) if(!strcmp(sy_queue[i].sha,sha)) return;
  sy_queued *n=realloc(sy_queue,((size_t)sy_queue_count+1)*sizeof(*n));
  if(!n) return;
  sy_queue=n;strcpy(sy_queue[sy_queue_count].sha,sha);sy_queue[sy_queue_count++].queued=sy_now();
}
static void sy_queue_remove(const char *sha) {
  for(int i=0;i<sy_queue_count;i++) if(!strcmp(sy_queue[i].sha,sha)){sy_queue[i]=sy_queue[--sy_queue_count];return;}
}
static void sy_config_load(void) {
  sy_new_device();
  size_t n=0;char *b=sy_read(sy_cfg_file,&n);if(!b) return;
  cv_json *root=sy_parse(b,n);free(b);
  if(!root || root->type!=CV_JSON_OBJECT){cv_json_free(root);return;}
  const cv_json *url=cv_json_get(root,"url"),*dev=cv_json_get(root,"device_id"),*auto_=cv_json_get(root,"auto"),*text=cv_json_get(root,"last_text"),*q=cv_json_get(root,"queue");
  uint64_t v=0;
  free(sy_url);sy_url=url && url->type==CV_JSON_STRING && url->string[0] ? host_strdup(url->string):NULL;
  if(dev && dev->type==CV_JSON_STRING && strlen(dev->string)<sizeof(sy_device)) strcpy(sy_device,dev->string);
  if(auto_ && auto_->type==CV_JSON_BOOL) sy_enabled_auto=auto_->boolean;
  if(annot_uint(root,"last_sync_ms",&v)) sy_last_ms=v;
  if(annot_uint(root,"last_code",&v)) sy_last_code=(int)v;
  if(text && text->type==CV_JSON_STRING) snprintf(sy_last_text,sizeof(sy_last_text),"%s",text->string);
  sy_queue_clear();
  for(size_t i=0;q && q->type==CV_JSON_ARRAY && i<q->count;i++) {
    const cv_json *h=cv_json_get(q->items[i],"sha256");
    if(h && h->type==CV_JSON_STRING){sy_queue_add(h->string);if(sy_queue_count && annot_uint(q->items[i],"queued_ms",&v))sy_queue[sy_queue_count-1].queued=v;}
  }
  cv_json_free(root);
}

/* ---- one full run --------------------------------------------------- */
typedef struct { sy_result *items; int count,pushed,pulled,failed,books,queued; sy_status status; } sy_run;
static void sy_run_free(sy_run *r) {for(int i=0;i<r->count;i++) sy_state_free(&r->items[i].merged);free(r->items);memset(r,0,sizeof(*r));}
/* Network + merge for every local book. Touches no local file except by reading. */
static void sy_run_net(sy_run *run) {
  memset(run,0,sizeof(*run));
  sy_target t;
  if(!sy_url || !sy_target_parse(sy_url,&t)){sy_status_set(&run->status,SY_CONFIG,"请先填写正确的服务器地址（以 http:// 或 https:// 开头，不要在地址里写用户名密码）。");return;}
  if(!sy_user || !sy_pass || !sy_user[0]){sy_status_set(&run->status,SY_CONFIG,"请填写用户名和密码。");return;}
  char (*remote)[65]=NULL;int remote_count=0,unsupported=0;
  int code=sy_remote_list(&t,&remote,&remote_count,&unsupported,&run->status);
  char (*books)[65]=NULL;int n=0;
  if(code==SY_OK) {
    n=sy_books(&books);
    if(n<0){sy_status_set(&run->status,SY_LOCAL,"内存不足。");code=SY_LOCAL;n=0;}
  }
  run->books=n;
  for(int i=0;code==SY_OK && i<n;i++) {
    int exists=0;for(int k=0;k<remote_count;k++) if(!strcmp(remote[k],books[i])){exists=1;break;}
    sy_result res;sy_status s={0};
    int c=sy_net_book(&t,books[i],!unsupported,exists,&res,&s);
    if(c==SY_OK) {
      if(res.merged.sha[0]) {
        sy_result *g=realloc(run->items,((size_t)run->count+1)*sizeof(*g));
        if(g){run->items=g;run->items[run->count++]=res;run->pushed+=res.pushed;run->pulled+=res.pulled;}
        else sy_state_free(&res.merged);
      }
      continue;
    }
    run->failed++;run->status=s;
    if(c==SY_AUTH || c==SY_NOTFOUND || c==SY_CONFIG || c==SY_TLS || c==SY_UNSUPPORTED || sy_offline_class(c)) {code=c;break;} /* every book would fail the same way */
  }
  if(code==SY_OK && run->failed) code=run->status.code;
  if(code==SY_OK) sy_status_set(&run->status,SY_OK,"同步完成：上传 %d 本，从云端更新 %d 本，共 %d 本书。",run->pushed,run->pulled,n);
  run->status.code=code;
  /* books that could not be synced stay in the draft queue */
  if(code!=SY_OK) run->queued=1;
  free(remote);free(books);
}
/* Apply on the UI thread (or inline in tests): local files, baselines, queue, status. */
static int sy_run_apply(sy_run *run,int *ui_changed) {
  int ok=1;
  for(int i=0;i<run->count;i++) {
    if(sy_apply(&run->items[i].merged,ui_changed)) sy_queue_remove(run->items[i].sha);
    else {ok=0;sy_queue_add(run->items[i].sha);}
  }
  if(run->status.code==SY_OK && ok) {sy_last_ms=sy_now();sy_queue_clear();}
  if(run->status.code!=SY_OK) {
    /* offline or failing: everything that differs from its baseline is a draft */
    char (*books)[65]=NULL;int n=sy_books(&books);
    for(int i=0;i<n;i++) {
      sy_state base={0},local={0};wchar_t bf[HOST_PATH];sy_book_file(sy_sync_dir,books[i],L".base.json",bf);
      if(sy_read_state_file(bf,books[i],&base) && sy_local(books[i],&base,&local)) {
        if(!sy_same(&local,&base) && sy_has_data(&local)) sy_queue_add(books[i]);
      }
      sy_state_free(&base);sy_state_free(&local);
    }
    free(books);
  }
  sy_last_code=run->status.code;snprintf(sy_last_text,sizeof(sy_last_text),"%s",run->status.text);
  if(run->status.code!=SY_OK && sy_queue_count && sy_offline_class(run->status.code))
    snprintf(sy_last_text+strlen(sy_last_text),sizeof(sy_last_text)-strlen(sy_last_text)," 已保存 %d 本书的离线草稿，联网后自动推送。",sy_queue_count);
  sy_config_save();
  return ok;
}
/* Synchronous convenience for tests and the command line. */
static inline int sy_sync_now(sy_status *out) {
  sy_run run;sy_run_net(&run);int changed=0;sy_run_apply(&run,&changed);
  if(out) *out=run.status;
  int code=run.status.code;sy_run_free(&run);return code;
}
static void sy_init(void) {
  sy_default_paths();sy_config_load();sy_cred_load();
}

/* ---- worker + UI ---------------------------------------------------- */
static sy_run sy_async_run;
static unsigned __stdcall sy_worker(void *arg) {
  (void)arg;
  sy_run_net(&sy_async_run);
  PostMessageW(g.window,WM_SY_DONE,0,0);
  return 0;
}
/* Called on the UI thread. Flushes in-memory shelf data to disk first so the
   worker reads what the user sees. */
static int sy_start_async(void) {
  if(InterlockedCompareExchange(&sy_busy,1,0)) return 0;
  if(sm_loaded && sm_writable) sm_save();
  shelf_save();
  uintptr_t t=_beginthreadex(NULL,0,sy_worker,NULL,0,NULL);
  if(!t){sy_busy=0;return 0;}
  CloseHandle((HANDLE)t);return 1;
}
/* Local files were rewritten under the running app: re-read what it caches. */
static void sy_reload_ui(int changed) {
  if(changed&SY_CHANGED_ANNOTATIONS) {
    annot_book=0; /* annot_sync() re-reads annotations/<sha>.json for the open book */
    if(annot_panel) ShowWindow(annot_panel,SW_HIDE);
  }
  if(changed&SY_CHANGED_PROGRESS) {
    for(int i=0;i<shelf_count;i++) shelf_free_book(&shelf_recent[i]);
    shelf_count=0;shelf_writable=1;shelf_load();
  }
  if(changed&SY_CHANGED_SETTINGS) {
    for(int i=0;i<sm_count;i++) sm_entry_free(&sm_entries[i]);
    free(sm_entries);sm_entries=NULL;sm_count=0;free(sm_days);sm_days=NULL;sm_day_count=0;
    sm_loaded=0;sm_reading_book=-1;sm_load();
  }
  if(changed && g.page) page_dirty(g.page,0);
}
static int sy_ready(void) {return sy_url && sy_user && sy_pass;}
/* annot_save() calls this: remember the book as an offline draft and sync soon. */
static void sy_note(const char *sha) {
  if(!sy_ready()) return;
  sy_queue_add(sha);sy_config_save();
  if(sy_enabled_auto && g.window && !host_offscreen) SetTimer(g.window,0x5C01,5000,NULL);
}

/* ---- settings page "云同步" ----------------------------------------- */
static int sy_inited;
static void sy_ensure(void) {if(!sy_inited){sy_inited=1;sy_init();}}
static void sy_time_text(uint64_t ms,char *out,size_t cap) {
  if(!ms){snprintf(out,cap,"从未");return;}
  FILETIME ft,local;SYSTEMTIME st;ULARGE_INTEGER v;v.QuadPart=(ms*10000ULL)+116444736000000000ULL;ft.dwLowDateTime=v.LowPart;ft.dwHighDateTime=v.HighPart;
  FileTimeToLocalFileTime(&ft,&local);FileTimeToSystemTime(&local,&st);
  snprintf(out,cap,"%04d-%02d-%02d %02d:%02d:%02d",st.wYear,st.wMonth,st.wDay,st.wHour,st.wMinute,st.wSecond);
}
static void sy_refresh(void) {
  if(!sy_panel) return;
  char when[40];sy_time_text(sy_last_ms,when,sizeof(when));
  cv_text t={0};
  cv_text_format(&t,"上次成功同步：%s\r\n",when);
  if(sy_busy) cv_text_string(&t,"状态：正在同步……\r\n");
  else if(sy_last_text[0]) cv_text_format(&t,"状态：%s\r\n",sy_last_text);
  else cv_text_string(&t,"状态：尚未同步。\r\n");
  cv_text_format(&t,"待推送的离线草稿：%d 本书\r\n",sy_queue_count);
  if(sy_url && !_strnicmp(sy_url,"http://",7) && !strstr(sy_url,"//127.0.0.1") && !strstr(sy_url,"//localhost"))
    cv_text_string(&t,"提示：http:// 为明文传输，密码可能被同一网络中的人截获，建议使用 https://。\r\n");
  if(sy_user && sy_pass) cv_text_string(&t,"凭证：已加密保存在本机（Windows DPAPI，仅当前用户可解密）。");
  else cv_text_string(&t,"凭证：未保存。");
  dict_set_text(GetDlgItem(sy_panel,SY_ID_STATUS),t.data ? t.data:"");cv_text_free(&t);
  CheckDlgButton(sy_panel,SY_ID_AUTO,sy_enabled_auto ? BST_CHECKED:BST_UNCHECKED);
  EnableWindow(GetDlgItem(sy_panel,SY_ID_NOW),!sy_busy);
}
static char *sy_edit_utf8(int id) {
  wchar_t text[1024];GetWindowTextW(GetDlgItem(sy_panel,id),text,1024);return host_utf8(text);
}
static void sy_fail(const char *text) {sy_last_code=SY_CONFIG;snprintf(sy_last_text,sizeof(sy_last_text),"%s",text);}
/* Returns 1 when the form is valid and stored; otherwise sy_last_text says why. */
static int sy_save_form(void) {
  char *url=sy_edit_utf8(SY_ID_URL),*user=sy_edit_utf8(SY_ID_USER),*pass=sy_edit_utf8(SY_ID_PASS);
  sy_target t;int ok=0;
  if(!url || !user || !pass) {sy_fail("内存不足。");goto done;}
  if(sy_busy) {sy_fail("正在同步，请稍后再保存设置。");goto done;} /* the worker reads url/user/password */
  if(!sy_target_parse(url,&t)) {sy_fail("服务器地址无效：请以 http:// 或 https:// 开头，且不要在地址里写用户名密码。");goto done;}
  if(!user[0]) {sy_fail("请填写用户名。");goto done;}
  if(!pass[0] && !(sy_pass && sy_user)) {sy_fail("请填写密码。");goto done;}
  if(pass[0] || strcmp(user,sy_user ? sy_user:"")) {
    const char *use=pass[0] ? pass:sy_pass;
    if(!sy_cred_save(user,use)) {sy_fail("无法加密保存凭证（DPAPI 不可用）；未写入任何明文。");goto done;}
    char *new_pass=host_strdup(use);
    sy_wipe(&sy_user);sy_wipe(&sy_pass);sy_user=host_strdup(user);sy_pass=new_pass;
  }
  free(sy_url);sy_url=host_strdup(url);
  sy_enabled_auto=IsDlgButtonChecked(sy_panel,SY_ID_AUTO)==BST_CHECKED;
  ok=sy_config_save();
  if(!ok) sy_fail("无法保存同步设置。");else sy_last_code=SY_OK;
done:
  if(pass){SecureZeroMemory(pass,strlen(pass));free(pass);}
  free(url);free(user);
  SetWindowTextW(GetDlgItem(sy_panel,SY_ID_PASS),L""); /* the password never stays in a control */
  return ok;
}
static void sy_open(void) {
  sy_ensure();dict_init();dict_hide();if(dict_manager)ShowWindow(dict_manager,SW_HIDE);
  if(!sy_panel) {
    sy_panel=dict_card_create(L"云同步（WebDAV）");
    dict_control(sy_panel,L"STATIC",L"服务器地址（例：https://dav.example.com/exreader/）",SY_ID_L1,0);
    dict_control(sy_panel,L"EDIT",L"",SY_ID_URL,ES_AUTOHSCROLL|WS_BORDER);
    dict_control(sy_panel,L"STATIC",L"用户名",SY_ID_L2,0);
    dict_control(sy_panel,L"EDIT",L"",SY_ID_USER,ES_AUTOHSCROLL|WS_BORDER);
    dict_control(sy_panel,L"STATIC",L"密码",SY_ID_L3,0);
    dict_control(sy_panel,L"EDIT",L"",SY_ID_PASS,ES_AUTOHSCROLL|ES_PASSWORD|WS_BORDER);
    dict_control(sy_panel,L"BUTTON",L"保存设置",SY_ID_SAVE,BS_OWNERDRAW);
    dict_control(sy_panel,L"BUTTON",L"立即同步",SY_ID_NOW,BS_OWNERDRAW);
    dict_control(sy_panel,L"BUTTON",L"清除凭证",SY_ID_CLEAR,BS_OWNERDRAW);
    dict_control(sy_panel,L"BUTTON",L"关闭",SY_ID_CLOSE,BS_OWNERDRAW);
    dict_control(sy_panel,L"BUTTON",L"有改动时自动同步",SY_ID_AUTO,BS_AUTOCHECKBOX);
    dict_control(sy_panel,L"EDIT",L"",SY_ID_STATUS,ES_MULTILINE|ES_READONLY|ES_AUTOVSCROLL|WS_VSCROLL);
  }
  dict_card_position(sy_panel,520,420);
  dict_place(sy_panel,SY_ID_L1,80,66,488,20);dict_place(sy_panel,SY_ID_URL,80,88,488,28);
  dict_place(sy_panel,SY_ID_L2,80,124,230,20);dict_place(sy_panel,SY_ID_L3,338,124,230,20);
  dict_place(sy_panel,SY_ID_USER,80,146,230,28);dict_place(sy_panel,SY_ID_PASS,338,146,230,28);
  dict_place(sy_panel,SY_ID_SAVE,80,186,110,34);dict_place(sy_panel,SY_ID_NOW,198,186,130,34);
  dict_place(sy_panel,SY_ID_CLEAR,336,186,110,34);dict_place(sy_panel,SY_ID_CLOSE,454,186,114,34);
  dict_place(sy_panel,SY_ID_AUTO,80,228,300,26);dict_place(sy_panel,SY_ID_STATUS,80,262,488,138);
  dict_set_text(GetDlgItem(sy_panel,SY_ID_URL),sy_url ? sy_url:"");
  dict_set_text(GetDlgItem(sy_panel,SY_ID_USER),sy_user ? sy_user:"");
  SetWindowTextW(GetDlgItem(sy_panel,SY_ID_PASS),L"");
  SendDlgItemMessageW(sy_panel,SY_ID_PASS,EM_SETCUEBANNER,TRUE,(LPARAM)(sy_pass ? L"已保存（留空则不修改）":L"密码"));
  sy_refresh();ShowWindow(sy_panel,SW_SHOWNOACTIVATE);SetFocus(GetDlgItem(sy_panel,SY_ID_URL));
}
static int sy_command(HWND window,int id,int notify) {
  (void)notify;
  if(!sy_panel || window!=sy_panel) return 0;
  if(id==SY_ID_CLOSE){ShowWindow(sy_panel,SW_HIDE);SetFocus(g.page);return 1;}
  if(id==SY_ID_SAVE){sy_save_form();sy_refresh();return 1;}
  if(id==SY_ID_AUTO){sy_enabled_auto=IsDlgButtonChecked(sy_panel,SY_ID_AUTO)==BST_CHECKED;sy_config_save();return 1;}
  if(id==SY_ID_CLEAR) {
    sy_cred_delete();SetWindowTextW(GetDlgItem(sy_panel,SY_ID_USER),L"");SetWindowTextW(GetDlgItem(sy_panel,SY_ID_PASS),L"");
    sy_last_code=SY_OK;snprintf(sy_last_text,sizeof(sy_last_text),"已清除保存的用户名和密码。");sy_config_save();sy_refresh();return 1;
  }
  if(id==SY_ID_NOW) {
    if(!sy_save_form()){sy_refresh();return 1;}
    if(!sy_start_async()) snprintf(sy_last_text,sizeof(sy_last_text),"已有同步正在进行。");
    sy_refresh();return 1;
  }
  return 0;
}
/* main window: the worker finished (WM_SY_DONE) */
static void sy_done(void) {
  int changed=0;
  sy_run_apply(&sy_async_run,&changed);sy_run_free(&sy_async_run);
  InterlockedExchange(&sy_busy,0);
  sy_reload_ui(changed);sy_refresh();
  if(sy_last_code!=SY_OK) set_status(L"云同步未完成，详见 设置 → 云同步。");else set_status(L"云同步完成。");
}
/* 60 s timer: retry the draft queue at once, otherwise pull every 5 minutes. 0x5C01 = debounced push after an edit. */
static void sy_timer(WPARAM id) {
  static int ticks;
  if(id==0x5C01){KillTimer(g.window,0x5C01);if(sy_ready() && sy_enabled_auto) sy_start_async();return;}
  if(!sy_ready() || !sy_enabled_auto) return;
  if(sy_queue_count || ++ticks>=5){ticks=0;sy_start_async();}
}
static void sy_boot(void) {
  sy_ensure();
  if(g.window && !host_offscreen && sy_ready() && sy_enabled_auto) {
    SetTimer(g.window,0x5C02,60000,NULL);
    SetTimer(g.window,0x5C01,3000,NULL); /* one pull shortly after start */
  }
}
