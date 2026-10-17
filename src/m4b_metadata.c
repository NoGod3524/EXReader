/* SPDX-License-Identifier: GPL-3.0-only */
#include "bmff_internal.h"
#define BOX EXR_BMFF_TYPE
#define DC "http://purl.org/dc/terms/"
struct exr_m4b_inspection {
  exr_metadata_entry *entries; size_t count,capacity,text_bytes;
  exr_audio_chapter *chapters; size_t chapter_count;
  unsigned char *cover; size_t cover_size; const char *cover_type;
  uint64_t duration;
};
void exr_m4b_inspection_free(exr_m4b_inspection *m) {
  size_t i; if(!m) return;
  exr_metadata_free(m->entries,m->count);
  for(i=0;i<m->chapter_count;i++) { free((void *)m->chapters[i].id); free((void *)m->chapters[i].title); }
  free(m->chapters); free(m->cover); free(m);
}
uint64_t exr_m4b_inspection_duration(const exr_m4b_inspection *m) { return m ? m->duration : UINT64_MAX; }
const exr_metadata_entry *exr_m4b_inspection_metadata(const exr_m4b_inspection *m,size_t *count) { if(count) *count=m ? m->count : 0; return m ? m->entries : NULL; }
const exr_audio_chapter *exr_m4b_inspection_chapters(const exr_m4b_inspection *m,size_t *count) { if(count) *count=m ? m->chapter_count : 0; return m ? m->chapters : NULL; }
const void *exr_m4b_inspection_cover(const exr_m4b_inspection *m,size_t *size,const char **type) { if(size) *size=m ? m->cover_size : 0; if(type) *type=m ? m->cover_type : NULL; return m ? m->cover : NULL; }
static exr_status string_value(exr_bmff_reader *io,const unsigned char *data,size_t size,unsigned type,char **out) {
  exr_buffer text={0}; size_t at=0; uint32_t cp; *out=NULL;
  if(type!=0 && type!=1 && type!=2) return exr_bmff_fail(io,"Unsupported ISO-BMFF text data type");
  if(size>65536) return exr_fail(io->error,EXR_LIMIT,"ISO-BMFF text exceeds 64 KiB");
  if(type==2) {
    if(size&1) return exr_bmff_fail(io,"Odd UTF-16BE metadata length");
    if(size>=2 && data[0]==0xfe && data[1]==0xff) at=2;
    if(size>=2 && !data[size-1] && !data[size-2]) size-=2;
    while(at<size) {
      cp=exr_bmff_be16(data+at); at+=2;
      if(cp>=0xd800 && cp<=0xdbff) {
        uint32_t low;
        if(size-at<2) goto encoding;
        low=exr_bmff_be16(data+at); at+=2;
        if(low<0xdc00 || low>0xdfff) goto encoding;
        cp=0x10000+((cp-0xd800)<<10)+(low-0xdc00);
      } else if(cp>=0xdc00 && cp<=0xdfff) goto encoding;
      if(!cp) goto encoding;
      if(!exr_codepoint(&text,cp)) goto memory;
    }
  } else {
    if(size && !data[size-1]) size--;
    while(at<size) if(!exr_next((const char *)data,size,&at,&cp) || !cp) goto encoding;
    if(!exr_append(&text,(const char *)data,size)) goto memory;
  }
  if(text.size>65536) { free(text.data); return exr_fail(io->error,EXR_LIMIT,"Decoded ISO-BMFF text exceeds 64 KiB"); }
  if(!text.data && !exr_append(&text,"",0)) goto memory;
  *out=text.data; return EXR_OK;
encoding:
  free(text.data); return exr_fail(io->error,EXR_ENCODING,"Invalid ISO-BMFF UTF text");
memory:
  free(text.data); return exr_fail(io->error,EXR_MEMORY,"ISO-BMFF text allocation failed");
}
static const char *key(uint32_t type) {
  switch(type) {
    case BOX(0xa9,'n','a','m'): return DC "title";
    case BOX(0xa9,'A','R','T'): case BOX('a','A','R','T'): return DC "creator";
    case BOX(0xa9,'w','r','t'): return DC "contributor";
    case BOX(0xa9,'d','a','y'): return DC "date";
    case BOX(0xa9,'c','m','t'): case BOX('d','e','s','c'): return DC "description";
    case BOX('c','p','r','t'): return DC "rights";
    case BOX(0xa9,'g','e','n'): return "http://ns.adobe.com/xmp/1.0/DynamicMedia/genre";
    case BOX(0xa9,'a','l','b'): return "http://ns.adobe.com/xmp/1.0/DynamicMedia/album";
    default: return NULL;
  }
}
static exr_status metadata_value(exr_bmff_reader *io,exr_m4b_inspection *m,const exr_bmff_box *box,const char *name,int cover) {
  unsigned char header[8],*bytes; uint64_t length; uint32_t type; exr_status status; char *text=NULL,*owned_key=NULL;
  status=exr_bmff_header(io,box,header,8); if(status!=EXR_OK) return status;
  if(header[0]) return exr_bmff_fail(io,"Unsupported ISO-BMFF data version");
  type=exr_bmff_be32(header)&0xffffff; length=box->end-box->data-8;
  if(cover && (m->cover || (type!=13 && type!=14))) return EXR_OK;
  if(length>(uint64_t)(cover ? 16*1024*1024 : 65536)) return exr_fail(io->error,EXR_LIMIT,"ISO-BMFF metadata payload exceeds budget");
  bytes=malloc((size_t)length+1); if(!bytes) return exr_fail(io->error,EXR_MEMORY,"ISO-BMFF metadata allocation failed");
  status=exr_bmff_read(io,box->data+8,bytes,(size_t)length); if(status!=EXR_OK) { free(bytes); return status; }
  if(cover) {
    if((type==13 && (length<3 || memcmp(bytes,"\xff\xd8\xff",3))) ||
       (type==14 && (length<8 || memcmp(bytes,"\x89PNG\r\n\x1a\n",8)))) {
      free(bytes); return exr_bmff_fail(io,"ISO-BMFF cover signature differs from data type");
    }
    m->cover=bytes; m->cover_size=(size_t)length; m->cover_type=type==13 ? "image/jpeg" : "image/png"; return EXR_OK;
  }
  status=string_value(io,bytes,(size_t)length,type,&text); free(bytes); if(status!=EXR_OK) return status;
  if(m->count==256 || strlen(text)+strlen(name)+2>(size_t)1024*1024-m->text_bytes) { free(text); return exr_fail(io->error,EXR_LIMIT,"ISO-BMFF metadata exceeds 256 values or 1 MiB text"); }
  owned_key=exr_copy(name,strlen(name));
  if(!owned_key || !exr_grow((void **)&m->entries,&m->capacity,m->count+1,sizeof(*m->entries))) { free(owned_key); free(text); return exr_fail(io->error,EXR_MEMORY,"ISO-BMFF metadata entry allocation failed"); }
  m->text_bytes+=strlen(text)+strlen(name)+2; m->entries[m->count++]=(exr_metadata_entry){owned_key,text}; return EXR_OK;
}
static exr_status meta(exr_bmff_reader *io,exr_m4b_inspection *m,const exr_bmff_box *box) {
  exr_bmff_box children=*box,items,item,data; unsigned char header[4]; uint64_t at,next; exr_status status=exr_bmff_header(io,box,header,4);
  if(status!=EXR_OK) return status;
  if(exr_bmff_be32(header)) return exr_bmff_fail(io,"Unsupported ISO-BMFF meta version/flags");
  children.data+=4; status=exr_bmff_child(io,&children,BOX('i','l','s','t'),0,&items); if(status!=EXR_OK || !items.end) return status;
  for(at=items.data;at<items.end;at=item.end) {
    const char *name; int cover;
    status=exr_bmff_at(io,at,items.end,&item); if(status!=EXR_OK) return status;
    name=key(item.type); cover=item.type==BOX('c','o','v','r'); if(!name && !cover) continue;
    for(next=item.data;next<item.end;next=data.end) {
      status=exr_bmff_at(io,next,item.end,&data); if(status!=EXR_OK) return status;
      if(data.type!=BOX('d','a','t','a')) continue;
      status=metadata_value(io,m,&data,name,cover); if(status!=EXR_OK) return status;
    }
  }
  return EXR_OK;
}
static exr_status chapter_list(exr_bmff_reader *io,exr_m4b_inspection *m,const exr_bmff_box *box) {
  unsigned char header[9]; uint64_t at; unsigned i,count; exr_status status=exr_bmff_header(io,box,header,5);
  if(status!=EXR_OK) return status;
  if(header[0]>1 || header[1] || header[2] || header[3]) return exr_bmff_fail(io,"Unsupported Nero chapter version/flags");
  at=box->data+4;
  if(header[0]) { status=exr_bmff_header(io,box,header,9); if(status!=EXR_OK) return status; at+=4; }
  count=header[header[0] ? 8 : 4]; at++;
  m->chapters=count ? calloc(count,sizeof(*m->chapters)) : NULL;
  if(count && !m->chapters) return exr_fail(io->error,EXR_MEMORY,"ISO-BMFF chapter allocation failed");
  for(i=0;i<count;i++) {
    unsigned char value[255]; uint64_t timestamp; unsigned length; char id[48],*title=NULL; exr_audio_chapter *chapter=&m->chapters[i];
    if(box->end-at<9) return exr_bmff_fail(io,"Truncated Nero chapter entry");
    status=exr_bmff_read(io,at,header,9); if(status!=EXR_OK) return status; at+=9;
    timestamp=exr_bmff_be64(header); length=header[8];
    if(length>box->end-at) return exr_bmff_fail(io,"Truncated Nero chapter title");
    status=exr_bmff_read(io,at,value,length); if(status!=EXR_OK) return status; at+=length;
    status=string_value(io,value,length,1,&title); if(status!=EXR_OK) return status;
    snprintf(id,sizeof(id),"chpl-%016llx",(unsigned long long)timestamp);
    chapter->id=exr_copy(id,strlen(id)); chapter->title=title; chapter->parent=SIZE_MAX;
    chapter->start_ms=timestamp/10000; chapter->end_ms=m->duration; m->chapter_count++;
    if(!chapter->id) return exr_fail(io->error,EXR_MEMORY,"ISO-BMFF chapter ID allocation failed");
    if((i && chapter->start_ms<=m->chapters[i-1].start_ms) || (m->duration!=UINT64_MAX && chapter->start_ms>=m->duration)) return exr_bmff_fail(io,"Nero chapter times must increase within millisecond duration");
    if(i) m->chapters[i-1].end_ms=chapter->start_ms;
  }
  return at==box->end ? EXR_OK : exr_bmff_fail(io,"Trailing Nero chapter data");
}
static exr_status milliseconds(exr_bmff_reader *io,uint64_t time,uint32_t scale,uint64_t *out) {
  uint64_t whole=time/scale,fraction=time%scale;
  if(whole>UINT64_MAX/1000 || fraction*1000/scale>UINT64_MAX-whole*1000) return exr_fail(io->error,EXR_LIMIT,"ISO-BMFF millisecond time overflows");
  *out=whole*1000+fraction*1000/scale; return EXR_OK;
}
/* Floor once after adding rational times from two different clocks. */
static exr_status chapter_time(exr_bmff_reader *io,uint64_t leading,uint32_t movie_scale,uint64_t delta,uint32_t media_scale,uint64_t *out) {
  uint64_t a=0,b=0,ra=(leading%movie_scale*1000)%movie_scale,rb=(delta%media_scale*1000)%media_scale;
  unsigned carry=ra*media_scale>=((uint64_t)media_scale-rb)*movie_scale; exr_status status;
  status=milliseconds(io,leading,movie_scale,&a); if(status!=EXR_OK) return status;
  status=milliseconds(io,delta,media_scale,&b); if(status!=EXR_OK) return status;
  if(b>UINT64_MAX-a || carry>UINT64_MAX-a-b) return exr_fail(io->error,EXR_LIMIT,"QuickTime chapter time overflows");
  *out=a+b+carry; return EXR_OK;
}
typedef struct { uint64_t start,leading,duration; int present; } chapter_edit;
static exr_status chapter_edits(exr_bmff_reader *io,const exr_bmff_box *track,chapter_edit *edit) {
  exr_bmff_box edts,list; unsigned char b[20]; uint32_t count,i; unsigned width; exr_status status;
  status=exr_bmff_child(io,track,BOX('e','d','t','s'),0,&edts); if(status!=EXR_OK || !edts.end) return status;
  status=exr_bmff_child(io,&edts,BOX('e','l','s','t'),1,&list); if(status!=EXR_OK) return status;
  status=exr_bmff_header(io,&list,b,8); if(status!=EXR_OK) return status;
  if(b[0]>1 || b[1] || b[2] || b[3]) return exr_bmff_fail(io,"Unsupported chapter edit-list version/flags");
  width=b[0] ? 20 : 12; count=exr_bmff_be32(b+4);
  if(count>64) return exr_fail(io->error,EXR_LIMIT,"Chapter edit list exceeds 64 entries");
  if(!count || (uint64_t)count*width!=list.end-list.data-8) return exr_bmff_fail(io,"Invalid chapter edit list");
  for(i=0;i<count;i++) {
    uint64_t duration,time;
    status=exr_bmff_read(io,list.data+8+(uint64_t)i*width,b,width); if(status!=EXR_OK) return status;
    duration=width==20 ? exr_bmff_be64(b) : exr_bmff_be32(b); time=width==20 ? exr_bmff_be64(b+8) : exr_bmff_be32(b+4);
    if(exr_bmff_be32(b+(width==20 ? 16 : 8))!=65536) return exr_bmff_fail(io,"Chapter edit rate must be one");
    if(time==(width==20 ? UINT64_MAX : UINT32_MAX)) {
      if(edit->present || duration>UINT64_MAX-edit->leading) return exr_bmff_fail(io,"Only leading empty chapter edits are supported");
      edit->leading+=duration;
    } else {
      if(edit->present || time>(width==20 ? INT64_MAX : INT32_MAX)) return exr_bmff_fail(io,"Only one forward chapter edit is supported");
      edit->present=1; edit->start=time; edit->duration=duration;
    }
  }
  return edit->present ? EXR_OK : exr_bmff_fail(io,"Chapter edit list has no media segment");
}
static exr_status chapter_table(exr_bmff_reader *io,const exr_bmff_box *stbl,uint32_t type,unsigned width,exr_bmff_table *table) {
  exr_bmff_box box; exr_status status=exr_bmff_child(io,stbl,type,1,&box);
  return status!=EXR_OK ? status : exr_bmff_table_box(io,&box,table,width,1);
}
static exr_status chapter_track(exr_bmff_reader *io,exr_m4b_inspection *m,const exr_bmff_box *track,uint32_t id,
                                 const exr_bmff_box *media,size_t media_count,uint32_t movie_scale) {
  exr_bmff_box mdia,box,minf,stbl,entry,other,dref; exr_bmff_table sizes={0},chunks={0},sc={0},times={0};
  unsigned char b[32],*sample=NULL; uint32_t scale,i,j,sc_index=0,chunk_index=0,in_chunk=0,current[3]={0},next[3]={0};
  uint64_t duration,*starts=NULL,total=0,offset=0,window=UINT64_MAX,final_end; unsigned version; chapter_edit edit={0}; exr_status status;
#define TRY(x) do { status=(x); if(status!=EXR_OK) goto done; } while(0)
  TRY(exr_bmff_child(io,track,BOX('m','d','i','a'),1,&mdia));
  TRY(exr_bmff_child(io,&mdia,BOX('h','d','l','r'),1,&box)); TRY(exr_bmff_header(io,&box,b,12));
  if(exr_bmff_be32(b) || (exr_bmff_be32(b+8)!=BOX('t','e','x','t') && exr_bmff_be32(b+8)!=BOX('s','b','t','l'))) goto bad;
  TRY(exr_bmff_child(io,&mdia,BOX('m','d','h','d'),1,&box)); TRY(exr_bmff_time(io,&box,&scale,&duration));
  TRY(exr_bmff_header(io,&box,b,1)); version=b[0];
  TRY(exr_bmff_child(io,&mdia,BOX('m','i','n','f'),1,&minf));
  TRY(exr_bmff_child(io,&minf,BOX('d','i','n','f'),1,&box)); TRY(exr_bmff_child(io,&box,BOX('d','r','e','f'),1,&dref));
  TRY(exr_bmff_header(io,&dref,b,8)); if(exr_bmff_be32(b) || exr_bmff_be32(b+4)!=1) goto bad;
  TRY(exr_bmff_at(io,dref.data+8,dref.end,&entry)); TRY(exr_bmff_header(io,&entry,b,4));
  if(entry.type!=BOX('u','r','l',' ') || entry.end!=dref.end || exr_bmff_be32(b)!=1) goto bad;
  TRY(exr_bmff_child(io,&minf,BOX('s','t','b','l'),1,&stbl));
  TRY(exr_bmff_child(io,&stbl,BOX('s','t','s','d'),1,&box)); TRY(exr_bmff_header(io,&box,b,8));
  if(exr_bmff_be32(b) || exr_bmff_be32(b+4)!=1) goto bad;
  TRY(exr_bmff_at(io,box.data+8,box.end,&entry));
  if(entry.end!=box.end || (entry.type!=BOX('t','e','x','t') && entry.type!=BOX('t','x','3','g'))) goto bad;
  TRY(exr_bmff_header(io,&entry,b,8));
  if(memcmp(b,"\0\0\0\0\0\0",6) || exr_bmff_be16(b+6)!=1 || entry.end-entry.data<(entry.type==BOX('t','e','x','t') ? 43u : 38u)) goto bad;
  TRY(chapter_table(io,&stbl,BOX('s','t','t','s'),8,&times));
  TRY(chapter_table(io,&stbl,BOX('s','t','s','c'),12,&sc));
  TRY(exr_bmff_child(io,&stbl,BOX('s','t','s','z'),0,&box)); TRY(exr_bmff_child(io,&stbl,BOX('s','t','z','2'),0,&other));
  if((box.end!=0)==(other.end!=0)) goto bad;
  TRY(exr_bmff_size_box(io,box.end ? &box : &other,&sizes));
  if(sizes.count>4096) { status=exr_fail(io->error,EXR_LIMIT,"QuickTime chapters exceed 4096 samples"); goto done; }
  TRY(exr_bmff_child(io,&stbl,BOX('s','t','c','o'),0,&box)); TRY(exr_bmff_child(io,&stbl,BOX('c','o','6','4'),0,&other));
  if((box.end!=0)==(other.end!=0)) goto bad;
  TRY(exr_bmff_table_box(io,box.end ? &box : &other,&chunks,box.end ? 4 : 8,1));
  TRY(exr_bmff_validate_sc(io,&sizes,&chunks,&sc));
  /* Text chapters use decode times; reordered composition is unsupported. */
  TRY(exr_bmff_child(io,&stbl,BOX('c','t','t','s'),0,&box)); if(box.end) goto bad;
  TRY(chapter_edits(io,track,&edit));
  if(edit.present) {
    if(!movie_scale) goto bad;
    if(edit.duration>UINT64_MAX-edit.leading) { status=exr_fail(io->error,EXR_LIMIT,"QuickTime chapter edit time overflows"); goto done; }
    TRY(milliseconds(io,edit.leading+edit.duration,movie_scale,&window));
  }
  starts=calloc((size_t)sizes.count+1,sizeof(*starts)); sample=malloc(65536);
  m->chapters=calloc(sizes.count,sizeof(*m->chapters));
  if(!starts || !sample || !m->chapters) { status=exr_fail(io->error,EXR_MEMORY,"QuickTime chapter allocation failed"); goto done; }
  j=0;
  for(i=0;i<times.count;i++) {
    uint32_t count,delta;
    TRY(exr_bmff_read(io,times.at+(uint64_t)i*8,b,8)); count=exr_bmff_be32(b); delta=exr_bmff_be32(b+4);
    if(!count || !delta || count>sizes.count-j) goto bad;
    while(count--) { starts[j++]=total; total+=delta; }
  }
  starts[j]=total;
  if(j!=sizes.count || (duration!=(version ? UINT64_MAX : UINT32_MAX) && duration!=total)) goto bad;
  if(edit.present && edit.start>=total) goto bad;
  TRY(chapter_time(io,edit.leading,edit.present ? movie_scale : 1,total-edit.start,scale,&final_end));
  if(edit.present && final_end>window) final_end=window;
  if(m->duration<final_end) final_end=m->duration;
  TRY(exr_bmff_sc_entry(io,&sc,0,current));
  if(sc.count>1) TRY(exr_bmff_sc_entry(io,&sc,1,next));
  TRY(exr_bmff_chunk_offset(io,&chunks,0,&offset));
  for(i=0;i<sizes.count;i++) {
    uint32_t size,length; uint64_t time,tail; size_t k; char *title=NULL,id_text[64];
    TRY(exr_bmff_sample_size(io,&sizes,i,&size));
    for(k=0;k<media_count;k++) if(offset>=media[k].data && offset<=media[k].end && size<=media[k].end-offset) break;
    if(k==media_count || size<2) goto bad;
    tail=offset+size;
    if(starts[i+1]>edit.start) {
      TRY(chapter_time(io,edit.leading,edit.present ? movie_scale : 1,starts[i]>edit.start ? starts[i]-edit.start : 0,scale,&time));
      if(time<final_end) {
        TRY(exr_bmff_read(io,offset,sample,size)); length=exr_bmff_be16(sample); if(length>size-2) goto bad;
        /* Modifiers remain uninterpreted, but cannot escape the sample. */
        for(uint64_t at=offset+2+length;at<tail;at=box.end) TRY(exr_bmff_at(io,at,tail,&box));
        if(length>=2 && sample[2]==0xff && sample[3]==0xfe) {
          if(length&1) { status=exr_fail(io->error,EXR_ENCODING,"Odd UTF-16LE chapter text"); goto done; }
          for(k=2;k<2+length;k+=2) { unsigned char c=sample[k]; sample[k]=sample[k+1]; sample[k+1]=c; }
        }
        status=string_value(io,sample+2,length,length>=2 && sample[2]==0xfe && sample[3]==0xff ? 2 : 1,&title); if(status!=EXR_OK) goto done;
        if(strlen(title)+1>(size_t)1024*1024-m->text_bytes) { free(title); status=exr_fail(io->error,EXR_LIMIT,"QuickTime chapter text exceeds 1 MiB"); goto done; }
        m->text_bytes+=strlen(title)+1;
        if(m->chapter_count && time<=m->chapters[m->chapter_count-1].start_ms) { free(title); goto bad; }
        snprintf(id_text,sizeof(id_text),"qt-%08x-%016llx",id,(unsigned long long)starts[i]);
        m->chapters[m->chapter_count]=(exr_audio_chapter){exr_copy(id_text,strlen(id_text)),title,SIZE_MAX,time,final_end};
        if(m->chapter_count) m->chapters[m->chapter_count-1].end_ms=time;
        m->chapter_count++; if(!m->chapters[m->chapter_count-1].id) { status=exr_fail(io->error,EXR_MEMORY,"QuickTime chapter ID allocation failed"); goto done; }
      }
    }
    offset=tail; in_chunk++;
    if(i+1<sizes.count && in_chunk==current[1]) {
      in_chunk=0; chunk_index++;
      if(sc_index+1<sc.count && next[0]==chunk_index+1) { sc_index++; memcpy(current,next,sizeof(current)); if(sc_index+1<sc.count) TRY(exr_bmff_sc_entry(io,&sc,sc_index+1,next)); }
      TRY(exr_bmff_chunk_offset(io,&chunks,chunk_index,&offset));
    }
  }
  status=EXR_OK; goto done;
bad:
  status=exr_bmff_fail(io,"Invalid or unsupported QuickTime chapter track");
done:
  free(starts); free(sample); return status;
#undef TRY
}
static exr_status quicktime_chapters(exr_bmff_reader *io,exr_m4b_inspection *m,const exr_bmff_box *moov,
                                      const exr_bmff_box *media,size_t media_count,uint32_t movie_scale) {
  exr_bmff_box tracks[256],box,tref,chap,tkhd; uint32_t ids[256],references[256]; size_t count=0,refs=0,i,j; uint64_t at; unsigned char b[24]; exr_status status;
  for(at=moov->data;at<moov->end;at=box.end) {
    status=exr_bmff_at(io,at,moov->end,&box); if(status!=EXR_OK) return status;
    if(box.type!=BOX('t','r','a','k')) continue;
    if(count==256) return exr_fail(io->error,EXR_LIMIT,"QuickTime inspection exceeds 256 tracks");
    tracks[count++]=box;
    status=exr_bmff_child(io,&box,BOX('t','r','e','f'),0,&tref); if(status!=EXR_OK) return status;
    if(!tref.end) continue;
    status=exr_bmff_child(io,&tref,BOX('c','h','a','p'),0,&chap); if(status!=EXR_OK) return status;
    if(!chap.end) continue;
    if((chap.end-chap.data)%4) return exr_bmff_fail(io,"Invalid QuickTime chapter references");
    if((chap.end-chap.data)/4>256-refs) return exr_fail(io->error,EXR_LIMIT,"QuickTime inspection exceeds 256 chapter references");
    for(uint64_t next=chap.data;next<chap.end;next+=4) {
      status=exr_bmff_read(io,next,b,4); if(status!=EXR_OK) return status; references[refs++]=exr_bmff_be32(b);
    }
  }
  if(!refs) return EXR_OK;
  for(i=0;i<count;i++) {
    status=exr_bmff_child(io,tracks+i,BOX('t','k','h','d'),1,&tkhd); if(status!=EXR_OK) return status;
    status=exr_bmff_header(io,&tkhd,b,4); if(status!=EXR_OK) return status;
    if(b[0]>1) return exr_bmff_fail(io,"Unsupported QuickTime track header");
    unsigned index=b[0] ? 20 : 12;
    status=exr_bmff_header(io,&tkhd,b,index+4); if(status!=EXR_OK) return status; ids[i]=exr_bmff_be32(b+index);
    if(!ids[i]) return exr_bmff_fail(io,"Zero QuickTime track ID");
    for(j=0;j<i;j++) if(ids[i]==ids[j]) return exr_bmff_fail(io,"Duplicate QuickTime track ID");
  }
  for(i=0;i<count;i++) if(ids[i]==references[0]) return chapter_track(io,m,tracks+i,ids[i],media,media_count,movie_scale);
  return exr_bmff_fail(io,"Missing referenced QuickTime chapter track");
}
exr_status exr_m4b_inspect_source(const exr_source *source,exr_m4b_inspection **out,exr_error *error) {
  exr_m4b_inspection *m; exr_error local={0}; exr_bmff_reader io; exr_bmff_box moov={0},box,mvhd,udta,child,chpl={0};
  exr_bmff_box media[256]; size_t media_count=0;
  uint64_t at=0,duration; uint32_t scale=0; int ftyp=0; unsigned char version; exr_status status=EXR_OK;
  if(out) *out=NULL;
  if(!source || !source->read_at || source->size<8 || !out) return exr_fail(error,EXR_ARGUMENT,"Invalid ISO-BMFF inspection source");
  if(!error) error=&local;
  memset(error,0,sizeof(*error));
  io=(exr_bmff_reader){source,&source->control,error,0,UINT64_C(33554432),0};
  m=calloc(1,sizeof(*m)); if(!m) return exr_fail(error,EXR_MEMORY,"ISO-BMFF inspection allocation failed"); m->duration=UINT64_MAX;
  while(at<source->size) {
    status=exr_bmff_at(&io,at,source->size,&box); if(status!=EXR_OK) goto done;
    if(box.type==BOX('f','t','y','p')) { if(ftyp++ || box.end-box.data<8) { status=exr_bmff_fail(&io,"Invalid ISO-BMFF file type"); goto done; } }
    if(box.type==BOX('m','o','o','v')) { if(moov.end) { status=exr_bmff_fail(&io,"Duplicate ISO-BMFF movie"); goto done; } moov=box; }
    if(box.type==BOX('m','d','a','t')) {
      if(media_count==256) { status=exr_fail(error,EXR_LIMIT,"ISO-BMFF inspection exceeds 256 media boxes"); goto done; }
      media[media_count++]=box;
    }
    at=box.end;
  }
  if(!ftyp || !moov.end) { status=exr_bmff_fail(&io,"ISO-BMFF metadata requires ftyp and moov"); goto done; }
  status=exr_bmff_child(&io,&moov,BOX('m','v','h','d'),0,&mvhd); if(status!=EXR_OK) goto done;
  if(mvhd.end) {
    status=exr_bmff_time(&io,&mvhd,&scale,&duration); if(status!=EXR_OK) goto done;
    status=exr_bmff_read(&io,mvhd.data,&version,1); if(status!=EXR_OK) goto done;
    if(duration!=(version ? UINT64_MAX : UINT32_MAX)) {
      uint64_t whole=duration/scale,fraction=duration%scale;
      if(whole>UINT64_MAX/1000 || fraction*1000/scale>UINT64_MAX-whole*1000) { status=exr_fail(error,EXR_LIMIT,"ISO-BMFF millisecond duration overflows"); goto done; }
      m->duration=whole*1000+fraction*1000/scale;
    }
  }
  status=exr_bmff_child(&io,&moov,BOX('m','e','t','a'),0,&child); if(status!=EXR_OK) goto done;
  if(child.end) { status=meta(&io,m,&child); if(status!=EXR_OK) goto done; }
  status=exr_bmff_child(&io,&moov,BOX('u','d','t','a'),0,&udta); if(status!=EXR_OK) goto done;
  if(udta.end) {
    status=exr_bmff_child(&io,&udta,BOX('m','e','t','a'),0,&child); if(status!=EXR_OK) goto done;
    if(child.end) { status=meta(&io,m,&child); if(status!=EXR_OK) goto done; }
    status=exr_bmff_child(&io,&udta,BOX('c','h','p','l'),0,&chpl); if(status!=EXR_OK) goto done;
  }
  if(chpl.end) { status=chapter_list(&io,m,&chpl); if(status!=EXR_OK) goto done; }
  if(!m->chapter_count) {
    free(m->chapters); m->chapters=NULL;
    status=quicktime_chapters(&io,m,&moov,media,media_count,scale); if(status!=EXR_OK) goto done;
  }
  status=exr_control_poll(&source->control,EXR_STAGE_READ,io.bytes,source->size,error);
done:
  if(status==EXR_OK) { *out=m; return exr_fail(error,EXR_OK,""); }
  exr_m4b_inspection_free(m); return status;
}
exr_status exr_m4b_inspect(const char *path,const exr_control *control,exr_m4b_inspection **out,exr_error *error) {
  exr_source source; exr_status status; if(out) *out=NULL;
  if(!path || !out) return exr_fail(error,EXR_ARGUMENT,"Invalid ISO-BMFF inspection file");
  status=exr_file_source_limit(path,INT64_MAX,&source,error); if(status!=EXR_OK) return status;
  if(control) source.control=*control;
  status=exr_m4b_inspect_source(&source,out,error); source.release(source.context); return status;
}
