/* SPDX-License-Identifier: GPL-3.0-only */
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
static buffer file(const char *directory) {
  char path[4096]; FILE *f; long length; buffer b={0}; snprintf(path,sizeof(path),"%s/pdf-images/baseline.jpg",directory);
  f=fopen(path,"rb"); CHECK(f && !fseek(f,0,SEEK_END)); length=ftell(f); CHECK(length>0); rewind(f);
  b.p=malloc((size_t)length); CHECK(b.p && fread(b.p,1,(size_t)length,f)==(size_t)length); b.n=(size_t)length; CHECK(!fclose(f)); return b;
}
static int cancel(void *context) { (void)context; return 1; }
static void valid(const char *fixtures,const char *directory) {
  buffer items={0},cover=file(fixtures),chpl=chapters(1,0,0),moov,b; size_t count,size; const char *type; const exr_metadata_entry *metadata;
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
int main(int argc,char **argv) { CHECK(argc==3); valid(argv[1],argv[2]); invalids(); large(); printf("%u ISO-BMFF metadata, chapters, ownership and large-source checks passed\n",checks); return 0; }
