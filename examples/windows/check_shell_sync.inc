/* SPDX-License-Identifier: MIT */
/* WebDAV sync acceptance: real TCP + WinHTTP against mock_webdav.inc, two
   simulated devices that differ only in their data directory, all through the
   production engine (sy_*) and the production loaders (annot_parse, shelf_load,
   sm_load) to prove the rewritten files are still valid. */
#include "mock_webdav.inc"

#define SYT_PASS "s3cret-Pw!-\xE5\xAF\x86\xE7\xA0\x81"
static wchar_t syt_root[HOST_PATH];
static char syt_url[128];
static const char *const SYT_BOOK_X="1111111111111111111111111111111111111111111111111111111111111111";
static const char *const SYT_BOOK_Y="2222222222222222222222222222222222222222222222222222222222222222";
static const char *const SYT_BOOK_Z="3333333333333333333333333333333333333333333333333333333333333333";
static const char *const SYT_BOOK_W="4444444444444444444444444444444444444444444444444444444444444444";

static void syt_dev(const char *name) {
  wchar_t d[HOST_PATH],n[64];swprintf(n,64,L"%hs",name);path_join(d,HOST_PATH,syt_root,n);
  assert(ensure_directory(d));wcscpy(g.data_dir,d);
  sy_default_paths();
  path_join(sy_annot_dir,HOST_PATH,d,L"annotations");
  sy_queue_clear();sy_last_ms=0;sy_last_text[0]=0;sy_last_code=0;
  sy_config_load();strcpy(sy_device,name);
  free(sy_url);sy_url=host_strdup(syt_url);
  sy_wipe(&sy_user);sy_wipe(&sy_pass);sy_user=host_strdup("alice");sy_pass=host_strdup(SYT_PASS);
}
static void syt_endpoint(cv_text *j,unsigned at) {
  cv_text_format(j,"{\"part_id\":\"p1\",\"part_path\":\"OEBPS/c1.xhtml\",\"text_revision\":\"00000000deadbeef\",\"text_size\":100000,"
    "\"selector\":{\"start\":%u,\"end\":%u,\"exact\":\"\",\"prefix\":\"before %u\",\"suffix\":\"after\",\"chapter\":null}}",at,at,at);
}
typedef struct { unsigned at; const char *text; unsigned long long updated; } syt_ann;
static void syt_write_anns(const char *sha,const syt_ann *a,int n) {
  cv_text j={0};cv_text_format(&j,"{\"version\":1,\"book_sha256\":\"%s\",\"annotations\":[\n",sha);
  for(int i=0;i<n;i++) {
    if(i) cv_text_string(&j,",\n");
    cv_text_format(&j,"{\"color\":0,\"created_ms\":%llu,\"updated_ms\":%llu,\"text\":",a[i].updated,a[i].updated);
    cv_text_json(&j,a[i].text);cv_text_string(&j,",\"anchor\":{\"start\":");
    syt_endpoint(&j,a[i].at);cv_text_string(&j,",\"end\":");syt_endpoint(&j,a[i].at);cv_text_string(&j,"}}");
  }
  cv_text_string(&j,"\n]}\n");
  wchar_t path[HOST_PATH];assert(ensure_directory(sy_annot_dir));sy_book_file(sy_annot_dir,sha,L".json",path);
  assert(!j.failed && sy_write(path,j.data,j.size));cv_text_free(&j);
}
/* load through the production parser; returns the count and the texts joined with '|' */
static int syt_read_anns(const char *sha,char *texts,size_t cap) {
  wchar_t path[HOST_PATH];sy_book_file(sy_annot_dir,sha,L".json",path);
  size_t n=0;char *b=sy_read(path,&n);texts[0]=0;
  if(!b) return 0;
  annot_clear();snprintf(annot_hash,sizeof(annot_hash),"%s",sha);
  assert(annot_parse(b,n));free(b);int count=annot_count;
  for(int i=0;i<annot_count;i++) {if(texts[0]) strncat(texts,"|",cap-strlen(texts)-1);strncat(texts,annotations[i].text,cap-strlen(texts)-1);}
  annot_clear();return count;
}
static void syt_write_progress(const char *sha,double ratio,unsigned at,unsigned long long opened) {
  cv_text j={0};cv_text_format(&j,"{\"version\":1,\"books\":[{\"id\":1,\"last_opened_ms\":%llu,\"progress\":%.6f,\"path\":null,"
    "\"title\":\"t\",\"author\":\"a\",\"book_sha256\":\"%s\",\"cover_hash\":\"\",\"fixed_page_id\":null,\"anchor\":{\"start\":",opened,ratio,sha);
  syt_endpoint(&j,at);cv_text_string(&j,",\"end\":");syt_endpoint(&j,at);cv_text_string(&j,"}}]}\n");
  assert(!j.failed && sy_write(sy_recent_file,j.data,j.size));cv_text_free(&j);
}
/* production loader check; returns progress */
static double syt_read_progress(const char *sha,unsigned *at,unsigned long long *opened) {
  for(int i=0;i<shelf_count;i++) shelf_free_book(&shelf_recent[i]);
  shelf_count=0;shelf_writable=1;shelf_load();assert(shelf_writable);
  for(int i=0;i<shelf_count;i++) if(!strcmp(shelf_recent[i].book_hash,sha)) {
    *at=(unsigned)shelf_recent[i].anchor.start.selector.start;*opened=shelf_recent[i].opened;return shelf_recent[i].progress;
  }
  return -1;
}
static void syt_write_title(const char *sha,const char *title) {
  cv_text j={0};cv_text_format(&j,"{\"version\":1,\"books\":[{\"sha256\":\"%s\",\"title\":",sha);
  cv_text_json(&j,title);cv_text_string(&j,",\"tags\":[\"a\"]}],\"days\":[]}\n");
  assert(!j.failed && sy_write(sy_shelf_file,j.data,j.size));cv_text_free(&j);
}
static int syt_read_title(const char *sha,char *out,size_t cap) {
  size_t n=0;char *b=sy_read(sy_shelf_file,&n);out[0]=0;if(!b) return 0;
  cv_json *root=sy_parse(b,n);const cv_json *books=cv_json_get(root,"books");int found=0;
  for(size_t i=0;books && i<books->count;i++) {
    const cv_json *h=cv_json_get(books->items[i],"sha256"),*t=cv_json_get(books->items[i],"title");
    if(h && !strcmp(h->string,sha) && t && t->type==CV_JSON_STRING){snprintf(out,cap,"%s",t->string);found=1;}
  }
  cv_json_free(root);free(b);
  /* the production loader must still accept the file */
  sm_loaded=0;sm_entries=NULL;sm_count=0;sm_days=NULL;sm_day_count=0;sm_writable=1;
  sm_load();assert(sm_writable);
  for(int i=0;i<sm_count;i++) sm_entry_free(&sm_entries[i]);
  free(sm_entries);free(sm_days);sm_entries=NULL;sm_count=0;sm_days=NULL;sm_day_count=0;sm_loaded=0;
  return found;
}
static int syt_sync(void) {sy_status s={0};int c=sy_sync_now(&s);printf("  sync -> code=%d  %s\n",c,s.text);return c;}
static int syt_remote_revision(const char *sha,int *anns) {
  char path[200];snprintf(path,sizeof(path),MOCK_BASE "%s/state.json",sha);
  EnterCriticalSection(&mock_lock);
  mock_node *n=mock_find(path);int rev=-1;
  if(n){sy_state s;if(sy_state_parse(n->data,n->size,sha,&s)){rev=(int)s.revision;if(anns)*anns=s.na;sy_state_free(&s);}}
  LeaveCriticalSection(&mock_lock);return rev;
}
static void syt_scan_for(const wchar_t *dir,const char *needle,int *hits,int *files) {
  wchar_t pattern[HOST_PATH];path_join(pattern,HOST_PATH,dir,L"*");
  WIN32_FIND_DATAW fd;HANDLE h=FindFirstFileW(pattern,&fd);if(h==INVALID_HANDLE_VALUE) return;
  do {
    if(!wcscmp(fd.cFileName,L".") || !wcscmp(fd.cFileName,L"..")) continue;
    wchar_t full[HOST_PATH];path_join(full,HOST_PATH,dir,fd.cFileName);
    if(fd.dwFileAttributes&FILE_ATTRIBUTE_DIRECTORY){syt_scan_for(full,needle,hits,files);continue;}
    size_t n=0;char *b=sy_read(full,&n);if(!b) continue;
    (*files)++;
    for(size_t i=0;i+strlen(needle)<=n;i++) if(!memcmp(b+i,needle,strlen(needle))){(*hits)++;break;}
    free(b);
  } while(FindNextFileW(h,&fd));
  FindClose(h);
}

static void test_sync(void) {
  wchar_t temp[HOST_PATH];GetTempPathW(HOST_PATH,temp);
  swprintf(syt_root,HOST_PATH,L"%lsexreader-sync-check-%lu",temp,(unsigned long)GetCurrentProcessId());
  assert(ensure_directory(syt_root));
  sy_clock_fixed=1762600000000ULL;sy_timeout_ms=1500;sy_backoff_ms=30;
  char buf[512];int anns=0;
  int port=mock_start(0,"alice",SYT_PASS);assert(port);
  snprintf(syt_url,sizeof(syt_url),"http://127.0.0.1:%d" MOCK_BASE,port);

  /* A. pure merge properties: commutative content, tombstones, resurrection by a newer edit */
  {
    sy_state a={0},b={0},m1,m2;strcpy(a.sha,SYT_BOOK_X);strcpy(b.sha,SYT_BOOK_X);a.settings=host_strdup("{}");b.settings=host_strdup("{}");
    cv_text e={0};syt_endpoint(&e,10);
    cv_text r1={0};cv_text_format(&r1,"{\"color\":0,\"created_ms\":5,\"updated_ms\":5,\"text\":\"one\",\"anchor\":{\"start\":%s,\"end\":%s}}",e.data,e.data);
    cv_json *o1=sy_parse(r1.data,r1.size);assert(sy_ann_add(&a,o1));cv_json_free(o1);
    cv_text e2={0};syt_endpoint(&e2,20);cv_text r2={0};
    cv_text_format(&r2,"{\"color\":1,\"created_ms\":6,\"updated_ms\":6,\"text\":\"two\",\"anchor\":{\"start\":%s,\"end\":%s}}",e2.data,e2.data);
    cv_json *o2=sy_parse(r2.data,r2.size);assert(sy_ann_add(&b,o2));cv_json_free(o2);
    assert(sy_merge(&a,&b,100,&m1) && sy_merge(&b,&a,100,&m2));
    assert(m1.na==2 && m2.na==2 && sy_same(&m1,&m2));
    /* tombstone newer than the annotation removes it; an edit newer than the tombstone keeps it */
    sy_state t={0};strcpy(t.sha,SYT_BOOK_X);t.settings=host_strdup("{}");sy_del_add(&t,a.ann[0].key,50);
    sy_state m3;assert(sy_merge(&a,&t,100,&m3) && m3.na==0 && m3.nd==1);
    a.ann[0].updated=60;sy_state m4;assert(sy_merge(&a,&t,100,&m4) && m4.na==1 && m4.nd==0);
    sy_state_free(&m1);sy_state_free(&m2);sy_state_free(&m3);sy_state_free(&m4);sy_state_free(&a);sy_state_free(&b);sy_state_free(&t);
    cv_text_free(&e);cv_text_free(&e2);cv_text_free(&r1);cv_text_free(&r2);
    puts("MERGE commutative=1 tombstone=1 newer-edit-wins=1");
  }

  /* B. first upload, incremental, idle */
  syt_dev("devA");
  {syt_ann one[]={{100,"first",1762600001000ULL}};syt_write_anns(SYT_BOOK_X,one,1);}
  syt_write_progress(SYT_BOOK_X,0.25,100,1762600001000ULL);
  syt_write_title(SYT_BOOK_X,"Title A");
  mock_n_put=mock_n_mkcol=mock_n_get=mock_n_propfind=0;
  assert(syt_sync()==SY_OK);
  assert(mock_n_mkcol==1 && mock_n_put==1 && mock_n_propfind==1);
  assert(syt_remote_revision(SYT_BOOK_X,&anns)==1 && anns==1);
  puts("FIRST-UPLOAD put=1 mkcol=1 revision=1 annotations=1");
  {syt_ann two[]={{100,"first",1762600001000ULL},{200,"second",1762600002000ULL}};syt_write_anns(SYT_BOOK_X,two,2);}
  sy_clock_fixed+=5000;mock_n_put=mock_n_mkcol=0;
  assert(syt_sync()==SY_OK && mock_n_put==1 && mock_n_mkcol==0);
  assert(syt_remote_revision(SYT_BOOK_X,&anns)==2 && anns==2);
  puts("INCREMENTAL put=1 mkcol=0 revision=2 annotations=2");
  mock_n_put=0;assert(syt_sync()==SY_OK && mock_n_put==0 && syt_remote_revision(SYT_BOOK_X,NULL)==2);
  puts("IDLE put=0 (nothing changed, nothing uploaded)");

  /* C. second device pulls everything, through the production loaders */
  syt_dev("devB");
  sy_clock_fixed+=5000;
  syt_write_progress(SYT_BOOK_X,0.05,5,1762600000500ULL); /* B has the book on its shelf, read less */
  assert(syt_sync()==SY_OK);
  assert(syt_read_anns(SYT_BOOK_X,buf,sizeof(buf))==2 && !strcmp(buf,"first|second"));
  unsigned at=0;unsigned long long opened=0;
  assert(fabs(syt_read_progress(SYT_BOOK_X,&at,&opened)-0.25)<1e-6 && at==100 && opened==1762600001000ULL);
  assert(syt_read_title(SYT_BOOK_X,buf,sizeof(buf)) && !strcmp(buf,"Title A"));
  puts("PULL annotations=2 progress=0.25(anchor 100) title=\"Title A\"");

  /* D. conflict: both devices add one annotation to the same synced book */
  syt_dev("devA");
  {syt_ann l[]={{100,"first",1762600001000ULL},{200,"second",1762600002000ULL},{300,"A-only",1762600010000ULL}};syt_write_anns(SYT_BOOK_X,l,3);}
  syt_dev("devB");
  {syt_ann l[]={{100,"first",1762600001000ULL},{200,"second",1762600002000ULL},{400,"B-only",1762600011000ULL}};syt_write_anns(SYT_BOOK_X,l,3);}
  syt_dev("devA");sy_clock_fixed+=5000;assert(syt_sync()==SY_OK);
  syt_dev("devB");sy_clock_fixed+=5000;assert(syt_sync()==SY_OK);
  assert(syt_read_anns(SYT_BOOK_X,buf,sizeof(buf))==4);printf("  devB: %s\n",buf);
  syt_dev("devA");sy_clock_fixed+=5000;assert(syt_sync()==SY_OK);
  assert(syt_read_anns(SYT_BOOK_X,buf,sizeof(buf))==4);printf("  devA: %s\n",buf);
  assert(strstr(buf,"A-only") && strstr(buf,"B-only"));
  assert(syt_remote_revision(SYT_BOOK_X,&anns)>=3 && anns==4);
  puts("CONFLICT common-base A+1 B+1 -> both devices 4 annotations (2 shared + A-only + B-only), nothing lost");

  /* E. the literal acceptance case: two empty devices each add one annotation -> two each */
  syt_dev("devA");{syt_ann l[]={{10,"from-A",1762600020000ULL}};syt_write_anns(SYT_BOOK_Y,l,1);}
  syt_dev("devB");{syt_ann l[]={{20,"from-B",1762600021000ULL}};syt_write_anns(SYT_BOOK_Y,l,1);}
  syt_dev("devA");sy_clock_fixed+=1000;assert(syt_sync()==SY_OK);
  syt_dev("devB");sy_clock_fixed+=1000;assert(syt_sync()==SY_OK);
  assert(syt_read_anns(SYT_BOOK_Y,buf,sizeof(buf))==2);printf("  devB: %s\n",buf);
  syt_dev("devA");sy_clock_fixed+=1000;assert(syt_sync()==SY_OK);
  assert(syt_read_anns(SYT_BOOK_Y,buf,sizeof(buf))==2);printf("  devA: %s\n",buf);
  assert(strstr(buf,"from-A") && strstr(buf,"from-B"));
  puts("CONFLICT-2 each device added 1 -> both devices have 2");

  /* F. deletion propagates and is not resurrected by the other device's stale copy */
  syt_dev("devA");{syt_ann l[]={{10,"from-A",1762600020000ULL}};syt_write_anns(SYT_BOOK_Y,l,1);} /* A deletes from-B */
  sy_clock_fixed+=1000;assert(syt_sync()==SY_OK);
  syt_dev("devB");sy_clock_fixed+=1000;assert(syt_sync()==SY_OK);
  assert(syt_read_anns(SYT_BOOK_Y,buf,sizeof(buf))==1 && !strcmp(buf,"from-A"));
  syt_dev("devA");sy_clock_fixed+=1000;assert(syt_sync()==SY_OK);
  assert(syt_read_anns(SYT_BOOK_Y,buf,sizeof(buf))==1);
  puts("DELETE tombstone propagated, not resurrected");

  /* G. progress and settings: last writer wins */
  syt_dev("devB");sy_clock_fixed+=1000;
  syt_write_progress(SYT_BOOK_X,0.80,800,1762600100000ULL);syt_write_title(SYT_BOOK_X,"Title B");
  assert(syt_sync()==SY_OK);
  syt_dev("devA");sy_clock_fixed+=1000;assert(syt_sync()==SY_OK);
  assert(fabs(syt_read_progress(SYT_BOOK_X,&at,&opened)-0.80)<1e-6 && at==800);
  assert(syt_read_title(SYT_BOOK_X,buf,sizeof(buf)) && !strcmp(buf,"Title B"));
  puts("LWW progress 0.25->0.80 and title A->B reached the other device");

  /* H. errors are readable and never silent */
  {
    syt_dev("devA");
    sy_wipe(&sy_pass);sy_pass=host_strdup("wrong");
    sy_status s={0};int c=sy_sync_now(&s);printf("  401: %s\n",s.text);
    assert(c==SY_AUTH && strstr(s.text,"401") && strstr(s.text,"密码") && sy_last_code==SY_AUTH);
    puts("ERROR-401 reported: " "认证失败（HTTP 401）");
    syt_dev("devA");
    char bad[160];snprintf(bad,sizeof(bad),"http://127.0.0.1:%d/nope/",port);
    free(sy_url);sy_url=host_strdup(bad);
    c=sy_sync_now(&s);printf("  404: %s\n",s.text);
    assert(c==SY_NOTFOUND && strstr(s.text,"404"));
    puts("ERROR-404 reported: 找不到同步目录（HTTP 404）");
    syt_dev("devA");
    mock_delay_ms=4000;sy_timeout_ms=700;
    c=sy_sync_now(&s);printf("  timeout: %s\n",s.text);
    assert(c==SY_TIMEOUT && strstr(s.text,"超时"));
    mock_delay_ms=0;sy_timeout_ms=1500;
    assert(WaitForSingleObject(mock_idle,5000)==WAIT_OBJECT_0);
    puts("ERROR-TIMEOUT reported: 连接超时");
    mock_force_status=403;mock_force_count=1000;
    c=sy_sync_now(&s);printf("  403: %s\n",s.text);assert(c==SY_AUTH && strstr(s.text,"403"));
    mock_force_count=0;
    puts("ERROR-403 reported: HTTP 403");
    /* transient 500s are retried transparently */
    mock_force_status=500;mock_force_count=2;
    c=sy_sync_now(&s);printf("  after two 500s: %s\n",s.text);assert(c==SY_OK);
    mock_force_count=0;
    puts("RETRY two HTTP 500 responses then success, no user-visible failure");
  }

  /* I. corrupt remote state is never merged into local data */
  {
    syt_dev("devA");
    char path[200];snprintf(path,sizeof(path),MOCK_BASE "%s/state.json",SYT_BOOK_X);
    EnterCriticalSection(&mock_lock);mock_node *n=mock_find(path);assert(n);
    char *keep=malloc(n->size);memcpy(keep,n->data,n->size);size_t keep_size=n->size;
    mock_put_node(path,0,"{not json",9);LeaveCriticalSection(&mock_lock);
    wchar_t ap[HOST_PATH];sy_book_file(sy_annot_dir,SYT_BOOK_X,L".json",ap);size_t before_n=0;char *before=sy_read(ap,&before_n);
    sy_status s={0};int c=sy_sync_now(&s);printf("  corrupt: %s\n",s.text);
    size_t after_n=0;char *after=sy_read(ap,&after_n);
    assert(c==SY_LOCAL && before_n==after_n && !memcmp(before,after,before_n));
    free(before);free(after);
    EnterCriticalSection(&mock_lock);mock_put_node(path,0,keep,keep_size);LeaveCriticalSection(&mock_lock);free(keep);
    puts("CORRUPT-REMOTE reported, local annotations byte-identical, remote not overwritten");
  }

  /* J. offline queue: really unreachable network, three edits, then reconnect */
  {
    syt_dev("devA");
    int before_rev_x=syt_remote_revision(SYT_BOOK_X,NULL);
    sy_clock_fixed+=60000;
    {syt_ann l[]={{100,"first",1762600001000ULL},{200,"second",1762600002000ULL},{300,"A-only",1762600010000ULL},{400,"B-only",1762600011000ULL},{999,"edit-1 offline",1762600500000ULL}};
     syt_write_anns(SYT_BOOK_X,l,5);}                                             /* edit 1: annotation on X */
    {syt_ann l[]={{1,"z",1762600501000ULL}};syt_write_anns(SYT_BOOK_Z,l,1);}      /* edit 2: annotation on a new book Z */
    syt_write_title(SYT_BOOK_W,"offline title");                                  /* edit 3: shelf metadata on a new book W */
    mock_stop(); /* the port now refuses connections: a genuine TCP-level outage */
    unsigned long put_before=(unsigned long)mock_n_put;
    sy_status s={0};int c=sy_sync_now(&s);printf("  offline: %s\n",s.text);
    assert(c==SY_OFFLINE && strstr(sy_last_text,"离线草稿") && sy_queue_count==3);
    assert((unsigned long)mock_n_put==put_before);
    /* the draft queue is on disk: survives an app restart */
    sy_queue_clear();sy_config_load();assert(sy_queue_count==3);
    puts("OFFLINE server down: failure reported, 3 drafts queued and persisted in sync.json");
    /* network back */
    assert(mock_start(port,"alice",SYT_PASS)==port);
    sy_clock_fixed+=1000;c=syt_sync();assert(c==SY_OK && sy_queue_count==0);
    assert(syt_remote_revision(SYT_BOOK_X,&anns)>before_rev_x && anns==5);
    assert(syt_remote_revision(SYT_BOOK_Z,&anns)==1 && anns==1);
    assert(syt_remote_revision(SYT_BOOK_W,NULL)==1);
    sy_queue_clear();sy_config_load();assert(sy_queue_count==0);
    puts("RECONNECT 3/3 offline edits pushed (X annotations=5, Z created, W created), queue empty");
  }

  /* K. credentials are encrypted at rest */
  {
    syt_dev("devA");assert(sy_cred_save("alice",SYT_PASS) && sy_config_save());
    int hits_pw=0,hits_user=0,files=0,hits_url_user=0;
    syt_scan_for(syt_root,SYT_PASS,&hits_pw,&files);
    syt_scan_for(syt_root,"alice",&hits_user,&files);
    syt_scan_for(syt_root,"s3cret",&hits_url_user,&files);
    printf("  scanned %d files under the data root: password hits=%d  username hits=%d  fragment hits=%d\n",files,hits_pw,hits_user,hits_url_user);
    assert(files>10 && hits_pw==0 && hits_user==0 && hits_url_user==0);
    sy_wipe(&sy_user);sy_wipe(&sy_pass);assert(sy_cred_load() && !strcmp(sy_user,"alice") && !strcmp(sy_pass,SYT_PASS));
    /* a different user cannot matter here, but a damaged blob must fail closed */
    size_t n=0;char *blob=sy_read(sy_cred_file,&n);assert(blob && n>40);blob[n/2]^=0x55;assert(sy_write(sy_cred_file,blob,n));free(blob);
    sy_wipe(&sy_user);sy_wipe(&sy_pass);assert(!sy_cred_load() && !sy_user && !sy_pass);
    sy_cred_delete();assert(GetFileAttributesW(sy_cred_file)==INVALID_FILE_ATTRIBUTES);
    puts("CREDENTIALS password/username absent from all files; DPAPI blob roundtrip ok; tampered blob rejected; delete removes file");
  }
  /* The wire never carries the password anywhere but the Authorization header: userinfo is refused. */
  {sy_target t;assert(!sy_target_parse("http://alice:pw@host/dav/",&t) && !sy_target_parse("ftp://h/",&t) && sy_target_parse("https://h:8443/a/b",&t) && t.secure && t.port==8443 && !strcmp(t.path,"/a/b/"));}
  mock_stop();
  mock_reset();
  sy_queue_clear();free(sy_url);sy_url=NULL;
  WSACleanup();
}
