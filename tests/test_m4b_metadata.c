/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef struct { unsigned char *p; size_t n; } buffer;
typedef struct { const buffer *first,*last; uint64_t tail,bytes; size_t calls; int released,short_reads,fail; } source_state;
static exr_error error;
static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
#define DC "http://purl.org/dc/terms/"
static void bytes(buffer *b,const void *p,size_t n) { b->p=realloc(b->p,b->n+n+1); CHECK(b->p); if(n) memcpy(b->p+b->n,p,n); b->n+=n; b->p[b->n]=0; }
static void integer(buffer *b,uint64_t v,unsigned n) { unsigned char p[8]; unsigned i; for(i=0;i<n;i++) p[n-1-i]=(unsigned char)(v>>(8*i)); bytes(b,p,n); }
static void box(buffer *b,const char type[4],const buffer *body) { integer(b,body->n+8,4); bytes(b,type,4); bytes(b,body->p,body->n); }
static void clear(buffer *b) { free(b->p); *b=(buffer){0}; }
static void item(buffer *items,const char type[4],unsigned encoding,const void *data,size_t n) {
  buffer payload={0},container={0}; integer(&payload,encoding,4); integer(&payload,0,4); bytes(&payload,data,n);
  box(&container,"data",&payload); box(items,type,&container); clear(&payload); clear(&container);
}
static buffer chapters(int version,int collision,int invalid_utf8) {
  buffer out={0}; integer(&out,(uint64_t)version<<24,4); if(version) integer(&out,0,4); integer(&out,2,1);
  integer(&out,0,8); integer(&out,3,1); bytes(&out,invalid_utf8 ? "\xff\x80\x80" : "One",3);
  integer(&out,collision ? 1 : UINT64_C(100000000),8); integer(&out,3,1); bytes(&out,"Two",3); return out;
}
static buffer movie(const buffer *items,const buffer *chpl,unsigned version,uint64_t duration,uint32_t scale) {
  buffer mvhd={0},udta={0},meta={0},content={0},movie={0};
  integer(&mvhd,(uint64_t)version<<24,4); integer(&mvhd,0,version ? 8 : 4); integer(&mvhd,0,version ? 8 : 4);
  integer(&mvhd,scale,4); integer(&mvhd,duration,version ? 8 : 4); box(&content,"mvhd",&mvhd);
  if(items) { integer(&meta,0,4); box(&meta,"ilst",items); box(&udta,"meta",&meta); }
  if(chpl) box(&udta,"chpl",chpl);
  box(&content,"udta",&udta); box(&movie,"moov",&content);
  clear(&mvhd); clear(&udta); clear(&meta); clear(&content); return movie;
}
static buffer book(const buffer *moov) {
  buffer b={0},ftyp={0}; bytes(&ftyp,"M4B \0\0\0\0",8); box(&b,"ftyp",&ftyp); bytes(&b,moov->p,moov->n); clear(&ftyp); return b;
}
static size_t read_at(void *context,uint64_t at,void *out,size_t n) {
  source_state *s=context; const buffer *b; uint64_t local;
  s->calls++; if(s->fail) return 0;
  if(s->short_reads && n>7) n=7;
  if(at<s->first->n) { b=s->first; local=at; }
  else if(s->last && at>=s->tail) { b=s->last; local=at-s->tail; }
  else return 0;
  if(local>=b->n) return 0;
  if(n>b->n-(size_t)local) n=b->n-(size_t)local;
  memcpy(out,b->p+(size_t)local,n); s->bytes+=n; return n;
}
static void release(void *context) { ((source_state *)context)->released++; }
static exr_source source(source_state *s) { exr_source out={0}; out.context=s; out.size=s->last ? s->tail+s->last->n : s->first->n; out.read_at=read_at; out.release=release; return out; }
static buffer fixture(const char *directory,const char *name) {
  char path[4096]; FILE *f; long length; buffer b={0}; snprintf(path,sizeof(path),"%s/%s",directory,name);
  f=fopen(path,"rb"); CHECK(f && !fseek(f,0,SEEK_END)); length=ftell(f); CHECK(length>0); rewind(f);
  b.p=malloc((size_t)length); CHECK(b.p && fread(b.p,1,(size_t)length,f)==(size_t)length); b.n=(size_t)length; CHECK(!fclose(f)); return b;
}
static int cancel(void *context) { (void)context; return 1; }
static void valid(const char *fixtures,const char *directory) {
  buffer items={0},cover=fixture(fixtures,"pdf-images/baseline.jpg"),chpl=chapters(1,0,0),moov,b; size_t count,size; const char *type; const exr_metadata_entry *metadata;
  const exr_audio_chapter *chapters_view; exr_m4b_inspection *m=NULL; exr_audio *audio=NULL; source_state state={0}; exr_source input;
  const unsigned char author[]={0x4e,0x2d,0xd8,0x3d,0xde,0x00};
  item(&items,"\xa9nam",1,"Book \xe4\xb8\xad\xf0\x9f\x98\x80",12); item(&items,"\xa9" "ART",2,author,sizeof(author)); item(&items,"\xa9" "ART",1,"Other",5);
  item(&items,"covr",13,cover.p,cover.n); moov=movie(&items,&chpl,0,20000,1000); b=book(&moov); state.first=&b; state.short_reads=1; input=source(&state);
  OK(exr_m4b_inspect_source(&input,&m,&error)); CHECK(!state.released && state.bytes<10000 && exr_m4b_inspection_duration(m)==20000);
  metadata=exr_m4b_inspection_metadata(m,&count); CHECK(count==3 && !strcmp(metadata[0].key,DC "title") && !strcmp(metadata[0].value,"Book \xe4\xb8\xad\xf0\x9f\x98\x80"));
  CHECK(!strcmp(metadata[1].value,"\xe4\xb8\xad\xf0\x9f\x98\x80") && !strcmp(metadata[2].value,"Other"));
  CHECK(exr_m4b_inspection_cover(m,&size,&type) && size==cover.n && !strcmp(type,"image/jpeg") && !memcmp(exr_m4b_inspection_cover(m,NULL,NULL),cover.p,size));
  chapters_view=exr_m4b_inspection_chapters(m,&count); CHECK(count==2 && chapters_view[0].parent==SIZE_MAX && chapters_view[0].start_ms==0 && chapters_view[0].end_ms==10000 && chapters_view[1].end_ms==20000 && !strcmp(chapters_view[0].title,"One"));
  { exr_audio_track track={"track","memory:book","audio/mp4",exr_m4b_inspection_duration(m)}; exr_audio_input a={0}; a.struct_size=sizeof(a); a.title=metadata[0].value; a.tracks=&track; a.track_count=1; a.chapters=chapters_view; a.chapter_count=count; OK(exr_audio_create(&a,NULL,&audio,&error)); }
  { char path[4096]; FILE *f; exr_m4b_inspection *disk=NULL; snprintf(path,sizeof(path),"%s/metadata-book.m4b",directory); f=fopen(path,"wb"); CHECK(f && fwrite(b.p,1,b.n,f)==b.n && !fclose(f)); OK(exr_m4b_inspect(path,NULL,&disk,&error)); CHECK(exr_m4b_inspection_duration(disk)==20000); exr_m4b_inspection_free(disk); }
  memset(b.p,0,b.n); exr_m4b_inspection_free(m); CHECK(!strcmp(exr_audio_title(audio),"Book \xe4\xb8\xad\xf0\x9f\x98\x80") && exr_audio_chapters(audio,&count) && count==2); exr_audio_free(audio);
  clear(&items); clear(&cover); clear(&chpl); clear(&moov); clear(&b);
}
static void invalids(void) {
  buffer items={0},chpl=chapters(0,0,0),moov=movie(NULL,&chpl,0,20000,1000),b=book(&moov); source_state state={0}; exr_source input; exr_m4b_inspection *m=NULL; size_t i;
  state.first=&b; input=source(&state);
  for(i=0;i<b.n;i++) { exr_status status; input.size=i; m=(void *)(uintptr_t)1; status=exr_m4b_inspect_source(&input,&m,&error); CHECK(status!=EXR_OK && !m && !state.released); }
  input.size=b.n; input.control.cancelled=cancel; CHECK(exr_m4b_inspect_source(&input,&m,&error)==EXR_CANCELLED && !m && !state.released); input.control.cancelled=NULL;
  state.fail=1; CHECK(exr_m4b_inspect_source(&input,&m,&error)==EXR_IO && !m); state.fail=0; clear(&b); clear(&moov);
  moov=movie(NULL,&chpl,0,UINT32_MAX,1000); b=book(&moov); state.first=&b; input=source(&state); OK(exr_m4b_inspect_source(&input,&m,&error)); CHECK(exr_m4b_inspection_duration(m)==UINT64_MAX && exr_m4b_inspection_chapters(m,&i)[1].end_ms==UINT64_MAX); exr_m4b_inspection_free(m); clear(&b); clear(&moov); clear(&chpl);
  chpl=chapters(1,1,0); moov=movie(NULL,&chpl,0,20000,1000); b=book(&moov); state.first=&b; input=source(&state); CHECK(exr_m4b_inspect_source(&input,&m,&error)==EXR_FORMAT && !m); clear(&b); clear(&moov); clear(&chpl);
  chpl=chapters(1,0,1); moov=movie(NULL,&chpl,0,20000,1000); b=book(&moov); state.first=&b; input=source(&state); CHECK(exr_m4b_inspect_source(&input,&m,&error)==EXR_ENCODING && !m); clear(&b); clear(&moov); clear(&chpl);
  item(&items,"\xa9nam",2,"\xd8\x00",2); moov=movie(&items,NULL,0,20,1000); b=book(&moov); state.first=&b; input=source(&state); CHECK(exr_m4b_inspect_source(&input,&m,&error)==EXR_ENCODING && !m); clear(&items); clear(&moov); clear(&b);
  for(i=0;i<257;i++) item(&items,"\xa9nam",1,"A",1);
  moov=movie(&items,NULL,0,20,1000); b=book(&moov); state.first=&b; input=source(&state); CHECK(exr_m4b_inspect_source(&input,&m,&error)==EXR_LIMIT && !m); clear(&items); clear(&moov); clear(&b);
  moov=movie(NULL,NULL,1,UINT64_MAX-1,1); b=book(&moov); state.first=&b; input=source(&state); CHECK(exr_m4b_inspect_source(&input,&m,&error)==EXR_LIMIT && !m); clear(&moov); clear(&b);
}
static void large(void) {
  buffer moov=movie(NULL,NULL,1,20000,1000),first={0},empty={0}; source_state state={0}; exr_source input; exr_m4b_inspection *m=NULL;
  uint64_t payload=UINT64_C(5)*1024*1024*1024; bytes(&empty,"M4B \0\0\0\0",8); box(&first,"ftyp",&empty);
  integer(&first,1,4); bytes(&first,"mdat",4); integer(&first,payload+16,8);
  state.first=&first; state.last=&moov; state.tail=16+16+payload; state.short_reads=1; input=source(&state);
  OK(exr_m4b_inspect_source(&input,&m,&error)); CHECK(exr_m4b_inspection_duration(m)==20000 && state.bytes<1000 && !state.released); exr_m4b_inspection_free(m);
  clear(&moov); clear(&first); clear(&empty);
}
static size_t type_at(const buffer *b,const char *type,unsigned occurrence) {
  size_t i; for(i=4;i+4<=b->n;i++) if(!memcmp(b->p+i,type,4) && !occurrence--) return i+4;
  CHECK(0); return 0;
}
static void put(buffer *b,size_t at,uint64_t value,unsigned width) { unsigned i; CHECK(at+width<=b->n); for(i=0;i<width;i++) b->p[at+width-1-i]=(unsigned char)(value>>(8*i)); }
/* Original text track: three samples, two chunks, two chunk-map runs. */
static buffer qt_book(unsigned compact,int wide,int edits) {
  buffer b={0},data={0},a={0},movie_data={0},owner={0},track={0},mdia={0},minf={0},stbl={0},outer={0},entry={0};
  uint64_t offsets[2]; unsigned sizes[3]={3,6,8},i;
  bytes(&a,"M4B \0\0\0\0",8); box(&b,"ftyp",&a); clear(&a);
  integer(&data,1,2); bytes(&data,"A",1);
  integer(&data,4,2); bytes(&data,"\xfe\xff\x4e\x2d",4);
  integer(&data,6,2); bytes(&data,"\xff\xfe\x3d\xd8\x00\xde",6);
  offsets[0]=b.n+8; offsets[1]=offsets[0]+sizes[0]+sizes[1]; box(&b,"mdat",&data); clear(&data);
  integer(&a,0,4); integer(&a,0,8); integer(&a,1000,4); integer(&a,edits ? 2500 : 3000,4); box(&movie_data,"mvhd",&a); clear(&a);
  integer(&a,edits==2 ? UINT64_C(1)<<24 : 0,4); integer(&a,0,edits==2 ? 8 : 4); integer(&a,0,edits==2 ? 8 : 4); integer(&a,1,4); box(&owner,"tkhd",&a); clear(&a);
  integer(&a,2,4); box(&outer,"chap",&a); clear(&a); box(&owner,"tref",&outer); clear(&outer); box(&movie_data,"trak",&owner); clear(&owner);
  integer(&a,edits==2 ? UINT64_C(1)<<24 : 0,4); integer(&a,0,edits==2 ? 8 : 4); integer(&a,0,edits==2 ? 8 : 4); integer(&a,2,4); box(&track,"tkhd",&a); clear(&a);
  if(edits) {
    integer(&a,edits==2 ? UINT64_C(1)<<24 : 0,4); integer(&a,2,4);
    integer(&a,500,edits==2 ? 8 : 4); integer(&a,edits==2 ? UINT64_MAX : UINT32_MAX,edits==2 ? 8 : 4); integer(&a,65536,4);
    integer(&a,2000,edits==2 ? 8 : 4); integer(&a,750,edits==2 ? 8 : 4); integer(&a,65536,4);
    box(&outer,"elst",&a); clear(&a); box(&track,"edts",&outer); clear(&outer);
  }
  integer(&a,edits==2 ? UINT64_C(1)<<24 : 0,4); integer(&a,0,edits==2 ? 8 : 4); integer(&a,0,edits==2 ? 8 : 4); integer(&a,1000,4); integer(&a,3000,edits==2 ? 8 : 4); box(&mdia,"mdhd",&a); clear(&a);
  integer(&a,0,8); bytes(&a,compact==16 ? "sbtl" : "text",4); box(&mdia,"hdlr",&a); clear(&a);
  integer(&entry,0,6); integer(&entry,1,2); for(i=0;i<(compact==16 ? 30u : 35u);i++) integer(&entry,0,1);
  integer(&a,0,4); integer(&a,1,4); box(&a,compact==16 ? "tx3g" : "text",&entry); clear(&entry); box(&stbl,"stsd",&a); clear(&a);
  integer(&a,0,4); integer(&a,3,4);
  for(i=0;i<3;i++) { integer(&a,1,4); integer(&a,i==0 ? 500 : i==1 ? 1000 : 1500,4); } box(&stbl,"stts",&a); clear(&a);
  integer(&a,0,4); integer(&a,2,4);
  for(i=0;i<2;i++) { integer(&a,i+1,4); integer(&a,i==0 ? 2 : 1,4); integer(&a,1,4); } box(&stbl,"stsc",&a); clear(&a);
  integer(&a,0,4); integer(&a,compact ? compact : 0,4); integer(&a,3,4);
  if(compact==4) { integer(&a,0x36,1); integer(&a,0x80,1); }
  else for(i=0;i<3;i++) integer(&a,sizes[i],compact ? compact/8 : 4);
  box(&stbl,compact ? "stz2" : "stsz",&a); clear(&a);
  integer(&a,0,4); integer(&a,2,4); for(i=0;i<2;i++) integer(&a,offsets[i],wide ? 8 : 4);
  box(&stbl,wide ? "co64" : "stco",&a); clear(&a);
  integer(&a,1,4); box(&entry,"url ",&a); clear(&a); integer(&a,0,4); integer(&a,1,4); bytes(&a,entry.p,entry.n); clear(&entry);
  box(&outer,"dref",&a); clear(&a); box(&minf,"dinf",&outer); clear(&outer);
  box(&minf,"stbl",&stbl); clear(&stbl); box(&mdia,"minf",&minf); clear(&minf);
  box(&track,"mdia",&mdia); clear(&mdia); box(&movie_data,"trak",&track); clear(&track);
  box(&b,"moov",&movie_data); clear(&movie_data); return b;
}
static void qt_result(buffer *b,int edited) {
  source_state state={0}; exr_source input; exr_m4b_inspection *m=NULL; exr_audio *audio=NULL; const exr_audio_chapter *view; size_t n;
  state.first=b; state.short_reads=1; input=source(&state); OK(exr_m4b_inspect_source(&input,&m,&error)); CHECK(!state.released);
  view=exr_m4b_inspection_chapters(m,&n); CHECK(n==(edited ? 2u : 3u));
  CHECK(!strcmp(view[0].title,edited ? "\xe4\xb8\xad" : "A")); CHECK(!strcmp(view[n-1].title,"\xf0\x9f\x98\x80"));
  CHECK(view[0].start_ms==(edited ? 500u : 0u) && view[0].parent==SIZE_MAX && !strncmp(view[0].id,"qt-00000002-",12));
  CHECK(view[n-1].start_ms==(edited ? 1250u : 1500u) && view[n-1].end_ms==(edited ? 2500u : 3000u));
  CHECK(view[0].end_ms==(edited ? 1250u : 500u));
  { exr_audio_track track={"track","memory:qt","audio/mp4",exr_m4b_inspection_duration(m)}; exr_audio_input a={0};
    a.struct_size=sizeof(a); a.title="qt"; a.tracks=&track; a.track_count=1; a.chapters=view; a.chapter_count=n; OK(exr_audio_create(&a,NULL,&audio,&error)); }
  exr_m4b_inspection_free(m); view=exr_audio_chapters(audio,&n);
  CHECK(n==(edited ? 2u : 3u) && !strcmp(view[n-1].title,"\xf0\x9f\x98\x80")); exr_audio_free(audio);
}
typedef struct { unsigned calls,after; } qt_cancel_state;
static int qt_cancel(void *context) { qt_cancel_state *c=context; return ++c->calls>c->after; }
static void qt_tests(const char *fixtures,const char *directory) {
  unsigned widths[]={0,4,8,16}; size_t i,j; buffer b; exr_m4b_inspection *m=NULL;
  for(i=0;i<4;i++) for(j=0;j<3;j++) { b=qt_book(widths[i],i&1,(int)j); qt_result(&b,(int)j); clear(&b); }
  b=qt_book(0,0,1);
  { source_state state={0}; exr_source input; const exr_audio_chapter *view; size_t n;
    put(&b,type_at(&b,"mvhd",0)+12,3000,4); put(&b,type_at(&b,"mdhd",0)+12,4000,4);
    state.first=&b; input=source(&state); OK(exr_m4b_inspect_source(&input,&m,&error)); view=exr_m4b_inspection_chapters(m,&n);
    CHECK(n==2 && view[0].start_ms==166 && view[1].start_ms==354 && view[1].end_ms==729); exr_m4b_inspection_free(m);
  }
  clear(&b);
  b=qt_book(0,1,0);
  { buffer head={0},tail={0}; source_state state={0}; exr_source input; uint64_t at=UINT64_C(5)*1024*1024*1024; size_t n;
    put(&b,type_at(&b,"co64",0)+8,at,8); put(&b,type_at(&b,"co64",0)+16,at+9,8);
    bytes(&head,b.p,16); integer(&head,1,4); bytes(&head,"mdat",4); integer(&head,at+17-16,8);
    bytes(&tail,b.p+24,17); n=type_at(&b,"moov",0)-8; bytes(&tail,b.p+n,b.n-n);
    state.first=&head; state.last=&tail; state.tail=at; state.short_reads=1; input=source(&state);
    OK(exr_m4b_inspect_source(&input,&m,&error)); CHECK(exr_m4b_inspection_chapters(m,&n) && n==3 && !state.released && state.bytes<20000);
    exr_m4b_inspection_free(m); clear(&head); clear(&tail);
  }
  clear(&b);
  b=qt_book(0,0,2);
  { source_state state={0}; exr_source input; state.first=&b; input=source(&state);
    put(&b,type_at(&b,"elst",0)+8,UINT64_MAX-500,8);
    CHECK(exr_m4b_inspect_source(&input,&m,&error)==EXR_LIMIT && !m && !state.released);
  }
  clear(&b);
  b=qt_book(0,0,0);
  { source_state state={0}; exr_source input; state.first=&b; input=source(&state);
    for(i=0;i<b.n;i++) { input.size=i; CHECK(exr_m4b_inspect_source(&input,&m,&error)!=EXR_OK && !m && !state.released); }
    input.size=b.n;
    for(i=0;i<120;i+=7) { qt_cancel_state c={0,(unsigned)i}; input.control.context=&c; input.control.cancelled=qt_cancel;
      CHECK(exr_m4b_inspect_source(&input,&m,&error)==EXR_CANCELLED && !m && !state.released); }
  }
  clear(&b);
  for(i=0;i<13;i++) {
    source_state state={0}; exr_source input; b=qt_book(0,0,0);
    switch(i) {
      case 0: put(&b,type_at(&b,"stco",0)+8,0,4); break;
      case 1: put(&b,type_at(&b,"stts",0)+12,0,4); break;
      case 2: put(&b,type_at(&b,"stts",0)+8,4,4); break;
      case 3: put(&b,type_at(&b,"chap",0),9,4); break;
      case 4: put(&b,type_at(&b,"tkhd",1)+12,1,4); break;
      case 5: put(&b,type_at(&b,"url ",0),0,4); break;
      case 6: put(&b,24,65535,2); break;
      case 7: put(&b,31,0xd800,2); break;
      case 8: put(&b,type_at(&b,"stts",0)+12,1,4); put(&b,type_at(&b,"mdhd",0)+12,1000000,4); put(&b,type_at(&b,"mdhd",0)+16,2501,4); break;
      case 9: put(&b,type_at(&b,"stsc",0)+16,2,4); break;
      case 10: put(&b,type_at(&b,"stsz",0)+4,3,4); put(&b,type_at(&b,"stsz",0)+8,4097,4); break;
      case 11: put(&b,type_at(&b,"stts",0)+4,65537,4); break;
      default: put(&b,type_at(&b,"mdhd",0)+16,1,4); break;
    }
    state.first=&b; input=source(&state);
    CHECK(exr_m4b_inspect_source(&input,&m,&error)==(i==7 ? EXR_ENCODING : i==10 || i==11 ? EXR_LIMIT : EXR_FORMAT) && !m && !state.released);
    clear(&b);
  }
  b=fixture(fixtures,"audio/metadata.m4b");
  { source_state state={0}; exr_source input; const exr_audio_chapter *view; size_t count; char path[4096]; FILE *f;
    state.first=&b; input=source(&state); OK(exr_m4b_inspect_source(&input,&m,&error));
    view=exr_m4b_inspection_chapters(m,&count); CHECK(count==2 && !strncmp(view[0].id,"chpl-",5)); exr_m4b_inspection_free(m);
    memcpy(b.p+type_at(&b,"chpl",0)-4,"free",4);
    OK(exr_m4b_inspect_source(&input,&m,&error)); view=exr_m4b_inspection_chapters(m,&count);
    CHECK(count==2 && view[0].start_ms==0 && view[0].end_ms==100 && view[1].start_ms==100 && view[1].end_ms==200);
    CHECK(!strcmp(view[0].title,"One") && !strcmp(view[1].title,"Two") && !strncmp(view[0].id,"qt-00000003-",12));
    exr_m4b_inspection_free(m); snprintf(path,sizeof(path),"%s/metadata-quicktime.m4b",directory); f=fopen(path,"wb"); CHECK(f && fwrite(b.p,1,b.n,f)==b.n && !fclose(f));
  }
  clear(&b);
}
static void key_entry(buffer *keys,const char *space,const char *name) { integer(keys,strlen(name)+8,4); bytes(keys,space,4); bytes(keys,name,strlen(name)); }
static void numbered_item(buffer *items,unsigned number,unsigned encoding,const void *value,size_t size) {
  char type[4]={(char)(number>>24),(char)(number>>16),(char)(number>>8),(char)number}; item(items,type,encoding,value,size);
}
static void freeform_item(buffer *items,const char *space,const char *name,const char *value) {
  buffer payload={0},field={0},data={0};
  if(space) { integer(&field,0,4); bytes(&field,space,strlen(space)); box(&payload,"mean",&field); clear(&field); }
  integer(&field,0,4); bytes(&field,name,strlen(name)); box(&payload,"name",&field); clear(&field);
  integer(&data,1,4); integer(&data,0,4); bytes(&data,value,strlen(value)); box(&payload,"data",&data); clear(&data);
  box(items,"----",&payload); clear(&payload);
}
static buffer named_book(const buffer *keys,const buffer *items) {
  buffer meta={0},content={0},moov={0},b; integer(&meta,0,4); if(keys) box(&meta,"keys",keys); box(&meta,"ilst",items);
  box(&content,"meta",&meta); box(&moov,"moov",&content); b=book(&moov); clear(&meta); clear(&content); clear(&moov); return b;
}
static void named_tests(void) {
  buffer keys={0},items={0},b; source_state state={0}; exr_source input; exr_m4b_inspection *m=NULL; const exr_metadata_entry *view; size_t n,i;
  integer(&keys,0,4); integer(&keys,4,4);
  key_entry(&keys,"mdta","com.apple.quicktime.title"); key_entry(&keys,"mdta","org.example.chapter");
  key_entry(&keys,"abcd","skip"); key_entry(&keys,"mdta","artist");
  numbered_item(&items,1,1,"Title",5); numbered_item(&items,1,1,"Other",5);
  numbered_item(&items,2,2,"\x4e\x2d\xd8\x3d\xde\x00",6); numbered_item(&items,3,1,"\xff",1);
  numbered_item(&items,4,21,"\0\0\0\x01",4); numbered_item(&items,4,1,"Author",6);
  freeform_item(&items,"com.apple.iTunes","TITLE","Book"); freeform_item(&items,"org:foo%","tag:name","Value"); freeform_item(&items,"org:foo%","tag:name","Second");
  b=named_book(&keys,&items); state.first=&b; state.short_reads=1; input=source(&state);
  for(i=0;i<b.n;i++) { input.size=i; CHECK(exr_m4b_inspect_source(&input,&m,&error)!=EXR_OK && !m && !state.released); }
  input.size=b.n;
  OK(exr_m4b_inspect_source(&input,&m,&error)); CHECK(!state.released); memset(b.p,0,b.n);
  view=exr_m4b_inspection_metadata(m,&n); CHECK(n==7);
  CHECK(!strcmp(view[0].key,DC "title") && !strcmp(view[1].key,DC "title") && !strcmp(view[1].value,"Other"));
  CHECK(!strcmp(view[2].key,"mdta:org.example.chapter") && !strcmp(view[2].value,"\xe4\xb8\xad\xf0\x9f\x98\x80"));
  CHECK(!strcmp(view[3].key,DC "creator") && !strcmp(view[3].value,"Author"));
  CHECK(!strcmp(view[4].key,DC "title") && !strcmp(view[4].value,"Book"));
  CHECK(!strcmp(view[5].key,"----:org%3Afoo%25:tag%3Aname") && !strcmp(view[6].key,view[5].key) && !strcmp(view[6].value,"Second"));
  exr_m4b_inspection_free(m); clear(&b); clear(&keys); clear(&items);
  item(&items,"T\0X:",1,"Custom",6); item(&items,"\xa9new",1,"Other",5); item(&items,"trkn",0,"\0\0\0\0",4); item(&items,"rate",21,"\0",1);
  b=named_book(NULL,&items); state.first=&b; input=source(&state); OK(exr_m4b_inspect_source(&input,&m,&error)); view=exr_m4b_inspection_metadata(m,&n);
  CHECK(n==2 && !strcmp(view[0].key,"ilst:T%00X%3A") && !strcmp(view[1].key,"ilst:%A9new")); exr_m4b_inspection_free(m); clear(&b); clear(&items);
  for(i=0;i<9;i++) {
    integer(&keys,0,4); integer(&keys,1,4); key_entry(&keys,"mdta","x"); numbered_item(&items,1,1,"v",1); b=named_book(&keys,&items);
    switch(i) {
      case 0: put(&b,type_at(&b,"keys",0),1,4); break;
      case 1: put(&b,type_at(&b,"keys",0)+4,257,4); break;
      case 2: put(&b,type_at(&b,"keys",0)+8,7,4); break;
      case 3: put(&b,type_at(&b,"keys",0)+8,65537,4); break;
      case 4: put(&b,type_at(&b,"keys",0)+16,0xff,1); break;
      case 5: put(&b,type_at(&b,"keys",0)+16,0,1); break;
      case 6: put(&b,type_at(&b,"ilst",0)+4,0,4); break;
      case 7: put(&b,type_at(&b,"ilst",0)+4,2,4); break;
      default: put(&b,type_at(&b,"data",0),UINT64_C(1)<<24,4); break;
    }
    state.first=&b; input=source(&state);
    CHECK(exr_m4b_inspect_source(&input,&m,&error)==(i==1 ? EXR_LIMIT : i==4 ? EXR_ENCODING : EXR_FORMAT) && !m && !state.released);
    clear(&b); clear(&keys); clear(&items);
  }
  for(i=0;i<3;i++) {
    freeform_item(&items,i==0 ? NULL : i==1 ? "" : "a","name","text"); b=named_book(NULL,&items);
    if(i==2) put(&b,type_at(&b,"name",0),1,4);
    state.first=&b; input=source(&state); CHECK(exr_m4b_inspect_source(&input,&m,&error)==EXR_FORMAT && !m && !state.released); clear(&b); clear(&items);
  }
  integer(&keys,0,4); integer(&keys,1,4);
  { char *long_name=malloc(65538); CHECK(long_name); memset(long_name,'a',65537); long_name[65537]=0; key_entry(&keys,"mdta",long_name); free(long_name); }
  numbered_item(&items,1,1,"v",1); b=named_book(&keys,&items); state.first=&b; input=source(&state);
  CHECK(exr_m4b_inspect_source(&input,&m,&error)==EXR_LIMIT && !m && !state.released); clear(&b); clear(&keys); clear(&items);
}
int main(int argc,char **argv) { CHECK(argc==3); valid(argv[1],argv[2]); invalids(); large(); qt_tests(argv[1],argv[2]); named_tests(); printf("%u ISO-BMFF metadata, chapters, ownership and large-source checks passed\n",checks); return 0; }
