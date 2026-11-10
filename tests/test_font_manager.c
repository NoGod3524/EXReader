/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#include <sys/utime.h>
#else
#include <pthread.h>
#include <utime.h>
#endif

static exr_error error;
static unsigned checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n", \
  __LINE__, #x, (int)error.code, error.message); exit(1); } } while (0)
#define OK(x) CHECK((x) == EXR_OK)
static const char *fallback[] = {"EXR FM CJK Serif", "EXR FM CJK Sans"};
static char root[4096], fonts[4096], cache[4096];
static void path(char *out, const char *name) {
  CHECK(snprintf(out,4096,"%s/%s",root,name)>0);
}
static void write_file(const char *name, const char *value, const char *mode) {
  char p[4096]; FILE *f; path(p,name); f=fopen(p,mode); CHECK(f);
  CHECK(fwrite(value,1,strlen(value),f)==strlen(value)); CHECK(!fclose(f));
}
static void copy_file(const char *from, const char *to) {
  char a[4096],b[4096]; unsigned char bytes[4096]; size_t n; FILE *in,*out;
  path(a,from); path(b,to); in=fopen(a,"rb"); CHECK(in); out=fopen(b,"wb"); CHECK(out);
  while((n=fread(bytes,1,sizeof(bytes),in))) CHECK(fwrite(bytes,1,n,out)==n);
  CHECK(!ferror(in)); CHECK(!fclose(in)); CHECK(!fclose(out));
}
static void remove_file(const char *name) {
  char p[4096]; path(p,name); CHECK(!remove(p));
}
static exr_font_manager_options options(exr_font_location *location) {
  exr_font_manager_options o={0};
  *location=(exr_font_location){fonts,EXR_FONT_LOCATION_DIRECTORY,0};
  o.struct_size=sizeof(o); o.locations=location; o.location_count=1;
  o.fallback_families=fallback; o.fallback_count=2;
  o.serif_families="EXR FM Latin Serif"; o.sans_serif_families="EXR FM CJK Sans";
  return o;
}
static exr_font_manager_summary summary(exr_font_manager *m) {
  exr_font_manager_summary s={0}; s.struct_size=sizeof(s);
  OK(exr_font_manager_summary_get(m,&s,&error)); return s;
}
static exr_font_pick_result pick(exr_font_manager *m,const char *family,unsigned style,uint32_t cp) {
  exr_font_pick_result p={0}; p.struct_size=sizeof(p);
  OK(exr_font_manager_pick(m,family,style,cp,&p,&error)); return p;
}
static void picked(exr_font_manager *m,const char *family,unsigned style,uint32_t cp,
                   const char *expected,unsigned step) {
  exr_font_pick_result p=pick(m,family,style,cp); exr_font_face_info f={0};
  CHECK(p.face!=SIZE_MAX && p.step==step); f.struct_size=sizeof(f);
  OK(exr_font_manager_face(m,p.face,&f,&error)); CHECK(!strcmp(f.family,expected));
  CHECK(exr_font_manager_face_covers(m,p.face,cp));
}
static void discovery(void) {
  exr_font_location loc; exr_font_manager_options o=options(&loc);
  exr_font_manager *m=NULL; exr_font_manager_summary s; size_t i;
  OK(exr_font_manager_create(&o,&m,&error)); s=summary(m);
  CHECK(s.files==3 && s.faces==3 && s.families==3 && s.skipped==0 && s.parsed_files==3);
  for(i=0;i<3;i++) {
    exr_font_face_info f={0}; f.struct_size=sizeof(f);
    OK(exr_font_manager_face(m,i,&f,&error)); CHECK(f.style==EXR_FONT_STYLE_REGULAR && f.weight==400);
    CHECK(f.scripts==(!strcmp(f.family,"EXR FM Latin Serif") ? EXR_FONT_SCRIPT_LATIN : EXR_FONT_SCRIPT_CJK));
    CHECK(f.codepoints && f.location==0);
  }
  CHECK(exr_font_manager_has_family(m,"exr fm latin serif"));
  CHECK(exr_font_manager_has_family(m,"\xe6\xb5\x8b\xe8\xaf\x95\xe5\xae\x8b\xe4\xbd\x93"));
  exr_font_manager_free(m);
  write_file("fonts/broken.ttf","not a font","wb"); write_file("fonts/readme.txt","text","wb");
  OK(exr_font_manager_create(&o,&m,&error)); s=summary(m);
  CHECK(s.files==3 && s.skipped==2);
  {
    unsigned seen=0; exr_font_skip skip;
    for(i=0;exr_font_manager_skip(m,i,&skip);i++) {
      CHECK(skip.path && skip.detail && *skip.detail); seen|=1u<<skip.reason;
    }
    CHECK(seen==((1u<<EXR_FONT_SKIP_DAMAGED)|(1u<<EXR_FONT_SKIP_NOT_FONT)));
  }
  exr_font_manager_free(m);
  {
    char empty[4096]; path(empty,"empty"); loc.path=empty;
    CHECK(exr_font_manager_create(&o,&m,&error)==EXR_FONT && !m);
  }
  {
    char single[4096]; path(single,"fonts/latin-serif.ttf"); loc.path=single; loc.kind=EXR_FONT_LOCATION_FILE;
    OK(exr_font_manager_create(&o,&m,&error)); CHECK(summary(m).files==1); exr_font_manager_free(m);
    path(single,"extra/collection.ttc");
    OK(exr_font_manager_create(&o,&m,&error)); s=summary(m);
    CHECK(s.files==1 && s.faces==2 && s.families==2);
    for(i=0;i<2;i++) {
      exr_font_face_info f={0}; f.struct_size=sizeof(f);
      OK(exr_font_manager_face(m,i,&f,&error)); CHECK(f.face_index==i);
    }
    exr_font_manager_free(m);
  }
  loc.path="exr-font-directory-does-not-exist"; loc.kind=EXR_FONT_LOCATION_DIRECTORY;
  CHECK(exr_font_manager_create(&o,&m,&error)==EXR_IO && !m);
  CHECK(strstr(error.message,loc.path));
  {
    exr_font_location locations[2]={{fonts,0,0},{loc.path,0,EXR_FONT_LOCATION_OPTIONAL}};
    o.locations=locations; o.location_count=2;
    OK(exr_font_manager_create(&o,&m,&error)); CHECK(summary(m).skipped==3); exr_font_manager_free(m);
  }
}
static void selection(void) {
  exr_font_location locations[4]; exr_font_manager_options o=options(locations);
  exr_font_manager *m=NULL; char bold[4096],italic[4096],duplicates[4096]; exr_font_pick_result p;
  path(bold,"extra/cjk-serif-bold.ttf"); locations[1]=(exr_font_location){bold,1,0}; o.location_count=2;
  path(italic,"extra/cjk-serif-italic.ttf"); locations[2]=(exr_font_location){italic,1,0}; o.location_count=3;
  OK(exr_font_manager_create(&o,&m,&error)); CHECK(summary(m).files==5 && summary(m).families==3);
  picked(m,"EXR FM Latin Serif",0,'A',"EXR FM Latin Serif",EXR_FONT_STEP_REQUESTED);
  picked(m,"EXR FM Latin Serif",0,0x4e2d,"EXR FM CJK Serif",EXR_FONT_STEP_FALLBACK);
  picked(m,"EXR FM Latin Serif",0,0x6a13,"EXR FM CJK Sans",EXR_FONT_STEP_FALLBACK);
  picked(m,"nonexistent",0,0x4e2d,"EXR FM CJK Serif",EXR_FONT_STEP_FALLBACK);
  picked(m,"nonexistent",0,0x9f8d,"EXR FM CJK Serif",EXR_FONT_STEP_FALLBACK);
  picked(m,"EXR FM CJK Serif",0,0x9f8d,"EXR FM CJK Serif",EXR_FONT_STEP_FAMILY_STYLE);
  picked(m,"EXR FM CJK Serif",1,0x4e2d,"EXR FM CJK Serif",EXR_FONT_STEP_REQUESTED);
  p=pick(m,"EXR FM CJK Serif",EXR_FONT_STYLE_ITALIC,0x03b1);
  {
    exr_font_face_info f={0}; f.struct_size=sizeof(f);
    OK(exr_font_manager_face(m,p.face,&f,&error));
    CHECK(f.style==EXR_FONT_STYLE_ITALIC && (f.scripts&EXR_FONT_SCRIPT_OTHER));
  }
  picked(m,"serif",0,'A',"EXR FM Latin Serif",EXR_FONT_STEP_REQUESTED);
  picked(m,"sans-serif",0,0x6a13,"EXR FM CJK Sans",EXR_FONT_STEP_REQUESTED);
  p=pick(m,"EXR FM Latin Serif",0,0x10ffff); CHECK(p.face==SIZE_MAX && p.step==0 && p.chain_position==SIZE_MAX);
  CHECK(exr_font_manager_pick(m,"",0,0xd800,&p,&error)==EXR_ARGUMENT);
  exr_font_manager_free(m);
  o.fallback_count=0;
  OK(exr_font_manager_create(&o,&m,&error));
  picked(m,"missing",0,'A',"EXR FM Latin Serif",EXR_FONT_STEP_SERIF);
  picked(m,"missing",0,0x6a13,"EXR FM CJK Sans",EXR_FONT_STEP_SANS_SERIF);
  exr_font_manager_free(m);
  /* Generic family inside a defaults list must terminate, not recurse. */
  o.serif_families="serif, EXR FM Latin Serif";
  OK(exr_font_manager_create(&o,&m,&error));
  picked(m,"serif",0,'A',"EXR FM Latin Serif",EXR_FONT_STEP_REQUESTED); exr_font_manager_free(m);
  path(duplicates,"duplicates"); locations[3]=(exr_font_location){duplicates,0,0}; o.location_count=4;
  o.fallback_count=2;
  OK(exr_font_manager_create(&o,&m,&error)); CHECK(summary(m).files==45);
  picked(m,"EXR FM Latin Serif",0,0x6a13,"EXR FM CJK Sans",EXR_FONT_STEP_FALLBACK);
  {
    exr_font_chain_link *chain=NULL; size_t n=0;
    OK(exr_font_manager_chain(m,"EXR FM Latin Serif",0,&chain,&n,&error)); CHECK(n==5); exr_free(chain);
  }
  exr_font_manager_free(m);
  /* Real coverage, not one face per family/style: a later same-style install
     contributes supplementary Han, compatibility Han, Hangul, emoji and math. */
  {
    static const uint32_t scalars[]={0x20001,0xfa17,0xac00,0x1f600,0x0f40,0x2211};
    char supplement[4096]; exr_font *font=NULL; size_t *map=NULL,n=0,i,j;
    path(supplement,"extra");
    locations[3]=(exr_font_location){supplement,EXR_FONT_LOCATION_DIRECTORY,0};
    o.fallback_count=0; o.serif_families="EXR FM Latin Serif"; o.sans_serif_families="missing";
    o.cache_path=cache;
    OK(exr_font_manager_create(&o,&m,&error));
    OK(exr_font_manager_create_font(m,"EXR FM Latin Serif",0,&font,&map,&n,&error));
    CHECK(n && n<=EXR_FONT_CHAIN_MAX);
    for(i=0;i<sizeof(scalars)/sizeof(*scalars);i++) {
      p=pick(m,"EXR FM Latin Serif",0,scalars[i]);
      CHECK(p.face!=SIZE_MAX && p.step==EXR_FONT_STEP_DISCOVERED);
      for(j=0;j<n && map[j]!=p.face;j++) {}
      CHECK(j<n && exr_font_has_glyph(font,j,scalars[i]));
    }
    /* Ordinary requested-face priority is unchanged. */
    picked(m,"EXR FM Latin Serif",0,'A',"EXR FM Latin Serif",EXR_FONT_STEP_REQUESTED);
    picked(m,"EXR FM Latin Serif",0,0x1f600,"EXR FM Emoji",EXR_FONT_STEP_DISCOVERED);
    exr_font_free(font); exr_free(map); exr_font_manager_free(m);
    OK(exr_font_manager_create(&o,&m,&error));
    CHECK(summary(m).parsed_files==0);
    picked(m,"EXR FM Latin Serif",0,0x1f600,"EXR FM Emoji",EXR_FONT_STEP_DISCOVERED);
    exr_font_manager_free(m);
  }
}
static void compare(exr_font_manager *a,exr_font_manager *b) {
  size_t i; CHECK(exr_font_manager_face_count(a)==exr_font_manager_face_count(b));
  for(i=0;i<exr_font_manager_face_count(a);i++) {
    exr_font_face_info x={0},y={0}; x.struct_size=sizeof(x); y.struct_size=sizeof(y);
    OK(exr_font_manager_face(a,i,&x,&error)); OK(exr_font_manager_face(b,i,&y,&error));
    CHECK(!strcmp(x.path,y.path) && !strcmp(x.family,y.family) && !strcmp(x.style_name,y.style_name));
    CHECK(x.style==y.style && x.weight==y.weight && x.scripts==y.scripts && x.codepoints==y.codepoints);
  }
}
static void caching(void) {
  exr_font_location loc; exr_font_manager_options o=options(&loc);
  exr_font_manager *a=NULL,*b=NULL; exr_font_manager_summary s; o.cache_path=cache;
  OK(exr_font_manager_create(&o,&a,&error)); s=summary(a);
  CHECK(s.cache==EXR_FONT_CACHE_MISS && s.parsed_files==3 && s.cache_written);
  OK(exr_font_manager_create(&o,&b,&error)); s=summary(b);
  CHECK(s.cache==EXR_FONT_CACHE_HIT && s.parsed_files==0 && s.cached_files==3 && !s.cache_written);
  compare(a,b); exr_font_manager_free(b);
  {
    char name[4096]; path(name,"fonts/latin-serif.ttf");
#ifdef _WIN32
    struct _utimbuf times={1234567890,1234567890}; CHECK(!_utime(name,&times));
#else
    struct utimbuf times={1234567890,1234567890}; CHECK(!utime(name,&times));
#endif
    OK(exr_font_manager_create(&o,&b,&error)); s=summary(b);
    CHECK(s.cache==EXR_FONT_CACHE_PARTIAL && s.parsed_files==1 && s.cached_files==2);
    compare(a,b); exr_font_manager_free(b);
  }
  write_file("fonts/latin-serif.ttf","padding","ab");
  OK(exr_font_manager_create(&o,&b,&error)); s=summary(b);
  CHECK(s.cache==EXR_FONT_CACHE_PARTIAL && s.parsed_files==1 && s.cached_files==2 && s.cache_written);
  compare(a,b); exr_font_manager_free(b);
  write_file("index.cache","EXRFIDX","wb");
  OK(exr_font_manager_create(&o,&b,&error)); s=summary(b);
  CHECK(s.cache==EXR_FONT_CACHE_MISS && s.parsed_files==3 && s.cache_written); compare(a,b);
  exr_font_manager_free(b);
  {
    FILE *f=fopen(cache,"r+b"); CHECK(f); CHECK(!fseek(f,-1,SEEK_END)); CHECK(fputc(99,f)!=EOF); CHECK(!fclose(f));
  }
  OK(exr_font_manager_create(&o,&b,&error)); CHECK(summary(b).cache==EXR_FONT_CACHE_MISS);
  exr_font_manager_free(b);
  {
    FILE *f=fopen(cache,"r+b"); CHECK(f); CHECK(!fseek(f,8,SEEK_SET)); CHECK(fputc(99,f)!=EOF); CHECK(!fclose(f));
  }
  OK(exr_font_manager_create(&o,&b,&error)); CHECK(summary(b).cache==EXR_FONT_CACHE_MISS);
  exr_font_manager_free(b);
  /* A cache hit still enumerates the directory: additions and removals count. */
  copy_file("extra/cjk-serif-italic.ttf","fonts/new.ttf");
  OK(exr_font_manager_create(&o,&b,&error)); s=summary(b);
  CHECK(s.files==4 && s.faces==4 && s.cache==EXR_FONT_CACHE_PARTIAL);
  CHECK(s.parsed_files==1 && s.cached_files==3 && s.cache_written);
  exr_font_manager_free(b);
  remove_file("fonts/new.ttf");
  OK(exr_font_manager_create(&o,&b,&error)); s=summary(b);
  CHECK(s.files==3 && s.faces==3 && s.parsed_files==0 && s.cached_files==3 && s.cache_written);
  compare(a,b); exr_font_manager_free(b);
  remove_file("fonts/latin-serif.ttf");
  OK(exr_font_manager_create(&o,&b,&error)); s=summary(b);
  CHECK(s.files==2 && s.faces==2 && s.cached_files==2 && s.cache_written);
  CHECK(!exr_font_manager_has_family(b,"EXR FM Latin Serif")); exr_font_manager_free(b);
  copy_file("extra/collection.ttc","fonts/replacement.ttc");
  o.cache_path="exr-missing-cache-parent/index.cache";
  OK(exr_font_manager_create(&o,&b,&error)); CHECK(summary(b).cache_write_status==EXR_IO);
  exr_font_manager_free(b); exr_font_manager_free(a);
}
typedef struct { const exr_font_manager *m; int ok; } worker;
static void query_worker(worker *w) {
  size_t i; w->ok=1;
  for(i=0;i<2000;i++) {
    exr_font_pick_result p={0}; p.struct_size=sizeof(p);
    if(exr_font_manager_pick(w->m,"EXR FM Latin Serif",0,0x6a13,&p,NULL)!=EXR_OK || p.face==SIZE_MAX)
      w->ok=0;
  }
}
#ifdef _WIN32
static DWORD WINAPI query_thread(void *w) { query_worker(w); return 0; }
#else
static void *query_thread(void *w) { query_worker(w); return NULL; }
#endif
static void integration(void) {
  exr_font_manager *m=NULL; exr_font *font=NULL; size_t *map=NULL,n=0,i;
  exr_document *doc=NULL; exr_layout *layout=NULL; exr_pager *pager=NULL;
  exr_layout_config config=exr_layout_config_defaults(); char cfg[4096];
  const char *html="<p>A\xe4\xb8\xad\xe6\xa8\x93\xf4\x8f\xbf\xbf</p>";
  write_file("fonts.conf","version = 1\nfont_dir = fonts\nfallback = EXR FM CJK Serif\nfallback = EXR FM CJK Sans\nserif = EXR FM Latin Serif\nsans_serif = EXR FM CJK Sans\ncache = index.cache\n","wb");
  path(cfg,"fonts.conf"); OK(exr_font_manager_open(cfg,&m,&error));
  {
    worker w[4];
#ifdef _WIN32
    HANDLE threads[4];
    for(i=0;i<4;i++) { w[i]=(worker){m,0}; threads[i]=CreateThread(NULL,0,query_thread,&w[i],0,NULL); CHECK(threads[i]); }
    CHECK(WaitForMultipleObjects(4,threads,TRUE,INFINITE)==WAIT_OBJECT_0);
    for(i=0;i<4;i++) { CHECK(w[i].ok); CloseHandle(threads[i]); }
#else
    pthread_t threads[4];
    for(i=0;i<4;i++) { w[i]=(worker){m,0}; CHECK(!pthread_create(&threads[i],NULL,query_thread,&w[i])); }
    for(i=0;i<4;i++) { CHECK(!pthread_join(threads[i],NULL)); CHECK(w[i].ok); }
#endif
  }
  OK(exr_font_manager_create_font(m,"EXR FM Latin Serif",0,&font,&map,&n,&error)); CHECK(n==3);
  OK(exr_document_open_memory(EXR_HTML,html,strlen(html),&doc,&error));
  config.page=(exr_layout_options){180,100,8,20,1.2f,0}; config.embedded_fonts=0;
  config.user_css="*{font-family:'EXR FM CJK Sans'}";
  for(i=0;i<2;i++) {
    const exr_glyph *g; size_t count,j; exr_bitmap bitmap={0};
    if(i==0) OK(exr_layout_create_ex(doc,font,&config,&layout,&error));
    else { OK(exr_pager_create(doc,font,&config,&pager,&error)); OK(exr_pager_next(pager,&layout,&error)); }
    g=exr_layout_glyphs(layout,&count); CHECK(count==4);
    for(j=0;j<count;j++) {
      exr_font_pick_result p=pick(m,"EXR FM Latin Serif",0,g[j].codepoint);
      if(p.face==SIZE_MAX) CHECK(g[j].flags&EXR_GLYPH_MISSING);
      else CHECK(!(g[j].flags&EXR_GLYPH_MISSING) && g[j].font_index<n && map[g[j].font_index]==p.face);
    }
    OK(exr_render_page_color(layout,NULL,0,&bitmap,&error)); exr_bitmap_free(&bitmap);
    exr_layout_free(layout); exr_pager_free(pager); pager=NULL;
  }
  exr_document_free(doc); doc=NULL;
  /* Embedded CSS keeps priority while the host fallback still follows pick(). */
  {
    char book[4096]; const exr_glyph *g; size_t glyph_count;
    path(book,"embedded.epub"); OK(exr_document_open(book,&doc,&error));
    config.embedded_fonts=1; config.user_css=NULL;
    OK(exr_layout_create_ex(doc,font,&config,&layout,&error));
    CHECK(exr_font_count(exr_layout_font(layout))==n+1);
    g=exr_layout_glyphs(layout,&glyph_count); CHECK(glyph_count==2);
    CHECK(g[0].codepoint==0x9f8d && g[0].font_index==n && !(g[0].flags&EXR_GLYPH_MISSING));
    CHECK(g[1].codepoint==0x4e2d && g[1].font_index<n &&
          map[g[1].font_index]==pick(m,"EXR FM Latin Serif",0,0x4e2d).face);
    exr_layout_free(layout); layout=NULL;
  }
  exr_document_free(doc); exr_font_free(font); exr_free(map); exr_font_manager_free(m);
  /* A full automatic tail must leave room for a requested embedded face. */
  {
    char latin[4096], many[4096], book[4096]; exr_font_location locations[2];
    exr_font_manager_options o={0}; const exr_glyph *g; size_t glyph_count;
    path(latin,"fonts/latin-serif.ttf"); path(many,"extra/many-scripts.ttc");
    locations[0]=(exr_font_location){latin,EXR_FONT_LOCATION_FILE,0};
    locations[1]=(exr_font_location){many,EXR_FONT_LOCATION_FILE,0};
    o.struct_size=sizeof(o); o.locations=locations; o.location_count=2;
    o.serif_families="EXR FM Latin Serif"; o.sans_serif_families="missing";
    OK(exr_font_manager_create(&o,&m,&error));
    OK(exr_font_manager_create_font(m,"serif",0,&font,&map,&n,&error)); CHECK(n==32);
    path(book,"embedded.epub"); OK(exr_document_open(book,&doc,&error));
    OK(exr_layout_create_ex(doc,font,&config,&layout,&error));
    CHECK(exr_font_count(exr_layout_font(layout))==32);
    g=exr_layout_glyphs(layout,&glyph_count); CHECK(glyph_count==2);
    CHECK(g[0].codepoint==0x9f8d && g[0].font_index==31 && g[0].glyph && !(g[0].flags&EXR_GLYPH_MISSING));
    exr_layout_free(layout); layout=NULL; exr_document_free(doc); doc=NULL;
    exr_font_free(font); exr_free(map); exr_font_manager_free(m);
  }
  {
    exr_font_location loc; exr_font_manager_options o=options(&loc);
    exr_font_chain_link *empty=NULL;
    o.fallback_count=0; o.serif_families=""; o.sans_serif_families="";
    OK(exr_font_manager_create(&o,&m,&error));
    OK(exr_font_manager_chain(m,"missing",0,&empty,&n,&error)); CHECK(!empty && !n);
    write_file("fonts/latin-serif.ttf","padding","ab");
    CHECK(exr_font_manager_create_font(m,"EXR FM Latin Serif",0,&font,&map,&n,&error)==EXR_FONT);
    CHECK(!font && !map && !n); exr_font_manager_free(m);
  }
  {
    exr_font_location loc; exr_font_manager_options o=options(&loc);
    OK(exr_font_manager_create(&o,&m,&error));
    remove_file("fonts/latin-serif.ttf");
    OK(exr_font_manager_create_font(m,"EXR FM Latin Serif",0,&font,&map,&n,&error));
    CHECK(n==2 && exr_font_count(font)==2);
    for(i=0;i<n;i++) {
      exr_font_face_info f={0}; f.struct_size=sizeof(f);
      OK(exr_font_manager_face(m,map[i],&f,&error)); CHECK(strcmp(f.family,"EXR FM Latin Serif"));
    }
    exr_font_free(font); exr_free(map); exr_font_manager_free(m);
  }
  write_file("fonts.conf","version = 1\nfont_dir = missing-directory\n","wb");
  CHECK(exr_font_manager_open(cfg,&m,&error)==EXR_IO && !m && strstr(error.message,"missing-directory"));
  write_file("fonts.conf","version = 1\nunknown = value\n","wb");
  CHECK(exr_font_manager_open(cfg,&m,&error)==EXR_FORMAT && strstr(error.message,"line 2"));
  write_file("fonts.conf","font_dir = fonts\n","wb");
  CHECK(exr_font_manager_open(cfg,&m,&error)==EXR_FORMAT && !m && strstr(error.message,"line 1"));
  write_file("fonts.conf","version = 2\nfont_dir = fonts\n","wb");
  CHECK(exr_font_manager_open(cfg,&m,&error)==EXR_FORMAT && !m);
  write_file("fonts.conf","version = 1\nplatform_dirs = maybe\n","wb");
  CHECK(exr_font_manager_open(cfg,&m,&error)==EXR_FORMAT && !m && strstr(error.message,"line 2"));
}
int main(int argc,char **argv) {
  CHECK(argc==3); CHECK(strlen(argv[2])<sizeof(root)); strcpy(root,argv[2]);
  path(fonts,"fonts"); path(cache,"index.cache");
  if(!strcmp(argv[1],"discovery")) discovery();
  else if(!strcmp(argv[1],"selection")) selection();
  else if(!strcmp(argv[1],"cache")) caching();
  else if(!strcmp(argv[1],"integration")) integration();
  else CHECK(0);
  printf("font-manager %s: %u checks passed\n",argv[1],checks); return 0;
}
