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
exr_status exr_m4b_inspect_source(const exr_source *source,exr_m4b_inspection **out,exr_error *error) {
  exr_m4b_inspection *m; exr_error local={0}; exr_bmff_reader io; exr_bmff_box moov={0},box,mvhd,udta,child,chpl={0};
  uint64_t at=0,duration; uint32_t scale; int ftyp=0; unsigned char version; exr_status status=EXR_OK;
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
