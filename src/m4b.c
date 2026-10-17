/* SPDX-License-Identifier: GPL-3.0-only */
#include "internal.h"
#if defined(EXR_ENABLE_AAC) && EXR_ENABLE_AAC
#include <neaacdec.h>
#define M4B_TYPE(a,b,c,d) ((uint32_t)(a)<<24|(uint32_t)(b)<<16|(uint32_t)(c)<<8|(uint32_t)(d))
#define M4B_TABLE_LIMIT 65536u
#define M4B_WORK_SAMPLES UINT64_C(16777216)
typedef struct { uint64_t data,end; uint32_t type; } m4b_box;
typedef struct { uint64_t at; uint32_t count,constant; unsigned width; } m4b_table;
typedef struct { uint64_t offset; uint32_t packet,chunk,within,per_chunk,sc; } m4b_cursor;
typedef struct { const exr_source *source; const exr_control *control; exr_error *error; uint64_t bytes,limit; unsigned boxes; } m4b_io;
struct exr_m4b {
  exr_source source;
  exr_m4b_info info;
  NeAACDecHandle decoder;
  m4b_box media[256]; size_t media_count;
  m4b_table sizes,chunks,sc,times;
  uint32_t media_scale,movie_scale,block;
  uint64_t media_duration,raw_frames,trim,leading;
  uint64_t edit_start,edit_duration,empty_duration;
  int have_edit;
  unsigned char asc[4096]; size_t asc_size;
  unsigned char *packet; size_t packet_capacity;
  float *cache; size_t cache_capacity,cache_frames;
  uint64_t cache_first,position;
  m4b_cursor cursor;
  int busy,dirty;
};
static uint32_t m4b_be16(const unsigned char *p) { return (uint32_t)p[0]<<8|p[1]; }
static uint32_t m4b_be32(const unsigned char *p) { return m4b_be16(p)<<16|m4b_be16(p+2); }
static uint64_t m4b_be64(const unsigned char *p) { return (uint64_t)m4b_be32(p)<<32|m4b_be32(p+4); }
static exr_status m4b_fail(m4b_io *io,const char *message) { return exr_fail(io->error,EXR_FORMAT,"%s",message); }
static exr_status m4b_read_bytes(m4b_io *io,uint64_t at,void *out,size_t size) {
  size_t done=0;
  if(at>io->source->size || size>io->source->size-at) return m4b_fail(io,"ISO-BMFF field exceeds source");
  if(size>io->limit-io->bytes) return exr_fail(io->error,EXR_LIMIT,"ISO-BMFF operation exceeds read budget");
  io->bytes+=size;
  while(done<size) {
    size_t got; exr_status status=exr_control_cancel(io->control,io->error); if(status!=EXR_OK) return status;
    got=io->source->read_at(io->source->context,at+done,(unsigned char *)out+done,size-done);
    if(!got || got>size-done) return exr_fail(io->error,EXR_IO,"Invalid or short ISO-BMFF source read");
    done+=got;
  }
  return EXR_OK;
}
static exr_status m4b_box_at(m4b_io *io,uint64_t at,uint64_t end,m4b_box *box) {
  unsigned char bytes[16]; uint64_t size; unsigned header=8; exr_status status;
  if(++io->boxes>65536) return exr_fail(io->error,EXR_LIMIT,"ISO-BMFF box count exceeds 65536");
  if(at>end || end-at<8) return m4b_fail(io,"Truncated ISO-BMFF box header");
  status=m4b_read_bytes(io,at,bytes,8); if(status!=EXR_OK) return status;
  size=m4b_be32(bytes); box->type=m4b_be32(bytes+4);
  if(size==1) { if(end-at<16) return m4b_fail(io,"Truncated ISO-BMFF extended box"); status=m4b_read_bytes(io,at+8,bytes+8,8); if(status!=EXR_OK) return status; size=m4b_be64(bytes+8); header=16; }
  else if(!size) size=end-at;
  if(box->type==M4B_TYPE('u','u','i','d')) header+=16;
  if(size<header || size>end-at) return m4b_fail(io,"Invalid ISO-BMFF box size");
  box->data=at+header; box->end=at+size; return EXR_OK;
}
static exr_status m4b_child(m4b_io *io,const m4b_box *parent,uint32_t type,int required,m4b_box *out) {
  uint64_t at=parent->data; memset(out,0,sizeof(*out));
  while(at<parent->end) {
    m4b_box child; exr_status status=m4b_box_at(io,at,parent->end,&child); if(status!=EXR_OK) return status;
    if(child.type==type) { if(out->end) return m4b_fail(io,"Duplicate ISO-BMFF structural box"); *out=child; }
    at=child.end;
  }
  return required && !out->end ? m4b_fail(io,"Missing ISO-BMFF structural box") : EXR_OK;
}
static exr_status m4b_header(m4b_io *io,const m4b_box *box,void *bytes,size_t size) {
  if(size>box->end-box->data) return m4b_fail(io,"Truncated ISO-BMFF box fields");
  return m4b_read_bytes(io,box->data,bytes,size);
}
static exr_status m4b_time_header(m4b_io *io,const m4b_box *box,uint32_t *scale,uint64_t *duration) {
  unsigned char b[32]; exr_status status=m4b_header(io,box,b,4); if(status!=EXR_OK) return status;
  if(b[1] || b[2] || b[3] || b[0]>1) return m4b_fail(io,"Unsupported ISO-BMFF time header version/flags");
  status=m4b_header(io,box,b,b[0] ? 32 : 20); if(status!=EXR_OK) return status;
  if(b[0]) { *scale=m4b_be32(b+20); *duration=m4b_be64(b+24); } else { *scale=m4b_be32(b+12); *duration=m4b_be32(b+16); }
  return *scale ? EXR_OK : m4b_fail(io,"Zero ISO-BMFF timescale");
}
static exr_status m4b_table_box(m4b_io *io,const m4b_box *box,m4b_table *table,unsigned width,int bounded) {
  unsigned char b[8]; uint64_t bytes; exr_status status=m4b_header(io,box,b,8); if(status!=EXR_OK) return status;
  if(m4b_be32(b)) return m4b_fail(io,"Unsupported ISO-BMFF table version/flags");
  table->count=m4b_be32(b+4); table->at=box->data+8; table->width=width;
  if(!table->count) return m4b_fail(io,"Empty ISO-BMFF audio table");
  if(bounded && table->count>M4B_TABLE_LIMIT) return exr_fail(io->error,EXR_LIMIT,"ISO-BMFF table exceeds 65536 runs");
  bytes=(uint64_t)table->count*width;
  return bytes<=box->end-table->at ? EXR_OK : m4b_fail(io,"Truncated ISO-BMFF table entries");
}
static exr_status m4b_size_box(m4b_io *io,const m4b_box *box,m4b_table *table) {
  unsigned char b[12]; uint64_t n; exr_status status=m4b_header(io,box,b,12); if(status!=EXR_OK) return status;
  if(m4b_be32(b)) return m4b_fail(io,"Unsupported ISO-BMFF sample-size version/flags");
  table->count=m4b_be32(b+8); table->at=box->data+12;
  if(box->type==M4B_TYPE('s','t','s','z')) { table->constant=m4b_be32(b+4); table->width=32; }
  else {
    if(b[4] || b[5] || b[6] || (b[7]!=4 && b[7]!=8 && b[7]!=16)) return m4b_fail(io,"Invalid compact ISO-BMFF sample sizes");
    table->width=b[7];
  }
  if(!table->count || table->constant>65536) return m4b_fail(io,"Empty/oversized ISO-BMFF audio samples");
  n=table->constant ? 0 : ((uint64_t)table->count*table->width+7)/8;
  return n<=box->end-table->at ? EXR_OK : m4b_fail(io,"Truncated ISO-BMFF sample-size table");
}
static exr_status m4b_sample_size(m4b_io *io,const exr_m4b *m,uint32_t sample,uint32_t *size) {
  unsigned char b[4]; exr_status status;
  if(sample>=m->sizes.count) return m4b_fail(io,"ISO-BMFF sample index exceeds table");
  if(m->sizes.constant) *size=m->sizes.constant;
  else {
    unsigned width=m->sizes.width; size_t bytes=width==4 ? 1 : width/8;
    status=m4b_read_bytes(io,m->sizes.at+(uint64_t)sample*width/8,b,bytes); if(status!=EXR_OK) return status;
    *size=width==4 ? ((sample&1) ? b[0]&15 : b[0]>>4) : width==8 ? b[0] : width==16 ? m4b_be16(b) : m4b_be32(b);
  }
  return *size && *size<=65536 ? EXR_OK : m4b_fail(io,"ISO-BMFF AAC packet exceeds 64 KiB or is empty");
}
static exr_status m4b_sc_entry(m4b_io *io,const exr_m4b *m,uint32_t index,uint32_t values[3]) {
  unsigned char b[12]; exr_status status;
  if(index>=m->sc.count) return m4b_fail(io,"ISO-BMFF sample-to-chunk index exceeds table");
  status=m4b_read_bytes(io,m->sc.at+(uint64_t)index*12,b,12); if(status!=EXR_OK) return status;
  values[0]=m4b_be32(b); values[1]=m4b_be32(b+4); values[2]=m4b_be32(b+8);
  return EXR_OK;
}
static exr_status m4b_validate_sc(m4b_io *io,const exr_m4b *m) {
  uint32_t i,current[3]={0},next[3]={0}; uint64_t samples=0; exr_status status=m4b_sc_entry(io,m,0,current); if(status!=EXR_OK) return status;
  if(current[0]!=1) return m4b_fail(io,"ISO-BMFF first sample-to-chunk entry must start at chunk 1");
  for(i=0;i<m->sc.count;i++) {
    uint64_t end=(uint64_t)m->chunks.count+1,count;
    if(i+1<m->sc.count) { status=m4b_sc_entry(io,m,i+1,next); if(status!=EXR_OK) return status; end=next[0]; }
    if(!current[0] || current[0]>m->chunks.count || end<=current[0] || end>(uint64_t)m->chunks.count+1 || !current[1] || current[2]!=1) return m4b_fail(io,"Invalid ISO-BMFF sample-to-chunk run");
    count=(end-current[0])*current[1];
    if(count>m->sizes.count-samples) return m4b_fail(io,"ISO-BMFF chunk sample counts exceed size table");
    samples+=count; if(i+1<m->sc.count) memcpy(current,next,sizeof(current));
  }
  return samples==m->sizes.count ? EXR_OK : m4b_fail(io,"ISO-BMFF sample-to-chunk coverage is incomplete");
}
static exr_status m4b_chunk_offset(m4b_io *io,const exr_m4b *m,uint32_t chunk,uint64_t *offset) {
  unsigned char b[8]; exr_status status;
  if(chunk>=m->chunks.count) return m4b_fail(io,"ISO-BMFF chunk index exceeds offset table");
  status=m4b_read_bytes(io,m->chunks.at+(uint64_t)chunk*m->chunks.width,b,m->chunks.width); if(status!=EXR_OK) return status;
  *offset=m->chunks.width==8 ? m4b_be64(b) : m4b_be32(b); return EXR_OK;
}
static exr_status m4b_initial_cursor(m4b_io *io,const exr_m4b *m,m4b_cursor *cursor) {
  uint32_t sc[3]={0}; exr_status status=m4b_sc_entry(io,m,0,sc); if(status!=EXR_OK) return status;
  memset(cursor,0,sizeof(*cursor)); cursor->per_chunk=sc[1]; return m4b_chunk_offset(io,m,0,&cursor->offset);
}
static exr_status m4b_packet(m4b_io *io,exr_m4b *m,const m4b_cursor *cursor,m4b_cursor *next,uint32_t *size) {
  size_t i; exr_status status=m4b_sample_size(io,m,cursor->packet,size); if(status!=EXR_OK) return status;
  for(i=0;i<m->media_count;i++) if(cursor->offset>=m->media[i].data && cursor->offset<=m->media[i].end && *size<=m->media[i].end-cursor->offset) break;
  if(i==m->media_count) return m4b_fail(io,"ISO-BMFF audio packet lies outside mdat payload");
  if(!exr_grow((void **)&m->packet,&m->packet_capacity,*size,1)) return exr_fail(io->error,EXR_MEMORY,"ISO-BMFF AAC packet allocation failed");
  status=m4b_read_bytes(io,cursor->offset,m->packet,*size); if(status!=EXR_OK) return status;
  *next=*cursor; next->packet++; next->within++; next->offset+=*size;
  if(next->packet<m->sizes.count && next->within==next->per_chunk) {
    uint32_t sc[3]={0}; next->chunk++; next->within=0;
    if(next->sc+1<m->sc.count) { status=m4b_sc_entry(io,m,next->sc+1,sc); if(status!=EXR_OK) return status; if(sc[0]==next->chunk+1) { next->sc++; next->per_chunk=sc[1]; } }
    status=m4b_chunk_offset(io,m,next->chunk,&next->offset); if(status!=EXR_OK) return status;
  }
  return EXR_OK;
}
static exr_status m4b_descriptor(exr_m4b *m,const unsigned char *data,size_t size,unsigned depth,int *codec,exr_error *e) {
  size_t at=0;
  if(depth>8) return exr_fail(e,EXR_LIMIT,"ISO-BMFF descriptor depth exceeds 8");
  while(at<size) {
    unsigned tag=data[at++],k; size_t n=0,start; exr_status status;
    for(k=0;k<4;k++) { unsigned b; if(at==size) return exr_fail(e,EXR_FORMAT,"Truncated ISO-BMFF descriptor length"); b=data[at++]; n=(n<<7)|(b&127); if(!(b&128)) break; }
    if(k==4 || n>size-at) return exr_fail(e,EXR_FORMAT,"ISO-BMFF descriptor exceeds box");
    start=at; at+=n;
    if(tag==3) {
      unsigned flags; size_t skip=3;
      if(n<3) return exr_fail(e,EXR_FORMAT,"Truncated ISO-BMFF ES descriptor");
      flags=data[start+2]; if(flags&128) skip+=2;
      if(flags&64) { if(skip>=n) return exr_fail(e,EXR_FORMAT,"Truncated ISO-BMFF ES URL"); skip+=1+data[start+skip]; }
      if(flags&32) skip+=2;
      if(skip>n) return exr_fail(e,EXR_FORMAT,"ISO-BMFF ES flags exceed descriptor");
      status=m4b_descriptor(m,data+start+skip,n-skip,depth+1,codec,e); if(status!=EXR_OK) return status;
    } else if(tag==4) {
      if(n<13 || (data[start]!=0x40 && (data[start]<0x66 || data[start]>0x68)) || (data[start+1]>>2)!=5) return exr_fail(e,EXR_FORMAT,"ISO-BMFF decoder is not supported AAC audio");
      if((*codec)++) return exr_fail(e,EXR_FORMAT,"Duplicate ISO-BMFF decoder descriptor");
      status=m4b_descriptor(m,data+start+13,n-13,depth+1,codec,e); if(status!=EXR_OK) return status;
    } else if(tag==5) {
      if(!*codec || !n || n>sizeof(m->asc) || m->asc_size) return exr_fail(e,EXR_FORMAT,"Invalid/duplicate AAC AudioSpecificConfig");
      memcpy(m->asc,data+start,n); m->asc_size=n;
    }
  }
  return EXR_OK;
}
static exr_status m4b_sample_description(m4b_io *io,exr_m4b *m,const m4b_box *stsd) {
  unsigned char b[28],*descriptors; m4b_box entry,children,esds,wave,sinf; exr_status status; size_t size; int codec=0;
  status=m4b_header(io,stsd,b,8); if(status!=EXR_OK) return status;
  if(m4b_be32(b) || m4b_be32(b+4)!=1) return m4b_fail(io,"ISO-BMFF requires one AAC sample description");
  status=m4b_box_at(io,stsd->data+8,stsd->end,&entry); if(status!=EXR_OK) return status;
  if(entry.type!=M4B_TYPE('m','p','4','a') || entry.end!=stsd->end) return m4b_fail(io,"ISO-BMFF audio is encrypted or not mp4a AAC");
  status=m4b_header(io,&entry,b,28); if(status!=EXR_OK) return status;
  if(m4b_be16(b+6)!=1 || m4b_be16(b+8)) return m4b_fail(io,"External or versioned QuickTime AAC sample entries are unsupported");
  children=entry; children.data+=28;
  status=m4b_child(io,&children,M4B_TYPE('s','i','n','f'),0,&sinf); if(status!=EXR_OK) return status;
  if(sinf.end) return m4b_fail(io,"Encrypted ISO-BMFF AAC is unsupported");
  status=m4b_child(io,&children,M4B_TYPE('e','s','d','s'),0,&esds); if(status!=EXR_OK) return status;
  if(!esds.end) { status=m4b_child(io,&children,M4B_TYPE('w','a','v','e'),1,&wave); if(status!=EXR_OK) return status; status=m4b_child(io,&wave,M4B_TYPE('e','s','d','s'),1,&esds); if(status!=EXR_OK) return status; }
  size=(size_t)(esds.end-esds.data);
  if(size<4 || esds.end-esds.data>65536) return exr_fail(io->error,EXR_LIMIT,"ISO-BMFF AAC descriptors exceed 64 KiB");
  descriptors=malloc(size); if(!descriptors) return exr_fail(io->error,EXR_MEMORY,"ISO-BMFF descriptor allocation failed");
  status=m4b_read_bytes(io,esds.data,descriptors,size);
  if(status==EXR_OK && m4b_be32(descriptors)) status=m4b_fail(io,"Unsupported ISO-BMFF esds version/flags");
  if(status==EXR_OK) status=m4b_descriptor(m,descriptors+4,size-4,0,&codec,io->error);
  free(descriptors);
  return status!=EXR_OK ? status : (!m->asc_size || codec!=1) ? m4b_fail(io,"Missing AAC decoder configuration") : EXR_OK;
}
static exr_status m4b_edits(m4b_io *io,exr_m4b *m,const m4b_box *trak) {
  m4b_box edts,elst; unsigned char b[20]; uint32_t i,count; unsigned width; int audio=0; exr_status status=m4b_child(io,trak,M4B_TYPE('e','d','t','s'),0,&edts); if(status!=EXR_OK || !edts.end) return status;
  status=m4b_child(io,&edts,M4B_TYPE('e','l','s','t'),1,&elst); if(status!=EXR_OK) return status;
  status=m4b_header(io,&elst,b,8); if(status!=EXR_OK) return status;
  if(b[0]>1 || b[1] || b[2] || b[3]) return m4b_fail(io,"Unsupported ISO-BMFF edit-list version/flags");
  width=b[0] ? 20u : 12u; count=m4b_be32(b+4);
  if(!count || count>64 || (uint64_t)count*width>elst.end-elst.data-8) return m4b_fail(io,"Invalid/oversized ISO-BMFF edit list");
  for(i=0;i<count;i++) {
    uint64_t duration,time; uint32_t rate;
    status=m4b_read_bytes(io,elst.data+8+(uint64_t)i*width,b,width); if(status!=EXR_OK) return status;
    duration=width==20 ? m4b_be64(b) : m4b_be32(b); time=width==20 ? m4b_be64(b+8) : m4b_be32(b+4); rate=m4b_be32(b+(width==20 ? 16 : 8));
    if(rate!=65536) return m4b_fail(io,"ISO-BMFF edit rates other than 1 are unsupported");
    if(time==(width==20 ? UINT64_MAX : UINT32_MAX)) {
      if(audio || duration>UINT64_MAX-m->empty_duration) return m4b_fail(io,"Only leading ISO-BMFF empty edits are supported");
      m->empty_duration+=duration;
    } else {
      if(audio || time>(width==20 ? INT64_MAX : INT32_MAX)) return m4b_fail(io,"Only one forward ISO-BMFF audio edit is supported");
      audio=1; m->edit_start=time; m->edit_duration=duration;
    }
  }
  if(!audio) return m4b_fail(io,"ISO-BMFF edit list contains no audio segment");
  m->have_edit=1; return EXR_OK;
}
static exr_status m4b_composition(m4b_io *io,const exr_m4b *m,const m4b_box *stbl) {
  m4b_box box; unsigned char b[8]; uint32_t count,i; uint64_t covered=0;
  exr_status status=m4b_child(io,stbl,M4B_TYPE('c','t','t','s'),0,&box); if(status!=EXR_OK || !box.end) return status;
  status=m4b_header(io,&box,b,8); if(status!=EXR_OK) return status;
  if(b[0]>1 || b[1] || b[2] || b[3]) return m4b_fail(io,"Unsupported ISO-BMFF composition-time version/flags");
  count=m4b_be32(b+4);
  if(!count || count>M4B_TABLE_LIMIT || (uint64_t)count*8>box.end-box.data-8) return m4b_fail(io,"Invalid ISO-BMFF composition-time table");
  for(i=0;i<count;i++) {
    uint32_t packets;
    status=m4b_read_bytes(io,box.data+8+(uint64_t)i*8,b,8); if(status!=EXR_OK) return status;
    packets=m4b_be32(b);
    if(!packets || packets>m->sizes.count-covered || m4b_be32(b+4)) return m4b_fail(io,"Nonzero ISO-BMFF AAC composition offsets are unsupported");
    covered+=packets;
  }
  return covered==m->sizes.count ? EXR_OK : m4b_fail(io,"Incomplete ISO-BMFF composition-time coverage");
}
static exr_status m4b_track(m4b_io *io,exr_m4b *m,const m4b_box *trak,int *audio) {
  m4b_box mdia,hdlr,mdhd,minf,stbl,box,alternative,stsd,dinf,dref; unsigned char b[12]; exr_status status;
  *audio=0;
  status=m4b_child(io,trak,M4B_TYPE('m','d','i','a'),1,&mdia); if(status!=EXR_OK) return status;
  status=m4b_child(io,&mdia,M4B_TYPE('h','d','l','r'),1,&hdlr); if(status!=EXR_OK) return status;
  status=m4b_header(io,&hdlr,b,12); if(status!=EXR_OK) return status;
  if(m4b_be32(b+8)!=M4B_TYPE('s','o','u','n')) return EXR_OK;
  *audio=1;
  status=m4b_child(io,&mdia,M4B_TYPE('m','d','h','d'),1,&mdhd); if(status!=EXR_OK) return status;
  status=m4b_time_header(io,&mdhd,&m->media_scale,&m->media_duration); if(status!=EXR_OK) return status;
  status=m4b_child(io,&mdia,M4B_TYPE('m','i','n','f'),1,&minf); if(status!=EXR_OK) return status;
  status=m4b_child(io,&minf,M4B_TYPE('d','i','n','f'),1,&dinf); if(status!=EXR_OK) return status;
  status=m4b_child(io,&dinf,M4B_TYPE('d','r','e','f'),1,&dref); if(status!=EXR_OK) return status;
  status=m4b_header(io,&dref,b,8); if(status!=EXR_OK) return status;
  if(m4b_be32(b) || !m4b_be32(b+4)) return m4b_fail(io,"Invalid ISO-BMFF data-reference table");
  status=m4b_box_at(io,dref.data+8,dref.end,&box); if(status!=EXR_OK) return status;
  status=m4b_header(io,&box,b,4); if(status!=EXR_OK) return status;
  if(box.type!=M4B_TYPE('u','r','l',' ') || m4b_be32(b)!=1) return m4b_fail(io,"External ISO-BMFF audio data references are unsupported");
  status=m4b_child(io,&minf,M4B_TYPE('s','t','b','l'),1,&stbl); if(status!=EXR_OK) return status;
  status=m4b_child(io,&stbl,M4B_TYPE('s','t','s','d'),1,&stsd); if(status!=EXR_OK) return status;
  status=m4b_sample_description(io,m,&stsd); if(status!=EXR_OK) return status;
  status=m4b_child(io,&stbl,M4B_TYPE('s','t','t','s'),1,&box); if(status!=EXR_OK) return status;
  status=m4b_table_box(io,&box,&m->times,8,1); if(status!=EXR_OK) return status;
  status=m4b_child(io,&stbl,M4B_TYPE('s','t','s','c'),1,&box); if(status!=EXR_OK) return status;
  status=m4b_table_box(io,&box,&m->sc,12,1); if(status!=EXR_OK) return status;
  status=m4b_child(io,&stbl,M4B_TYPE('s','t','s','z'),0,&box); if(status!=EXR_OK) return status;
  status=m4b_child(io,&stbl,M4B_TYPE('s','t','z','2'),0,&alternative); if(status!=EXR_OK) return status;
  if((box.end!=0)==(alternative.end!=0)) return m4b_fail(io,"ISO-BMFF requires exactly one sample-size table");
  if(!box.end) box=alternative;
  status=m4b_size_box(io,&box,&m->sizes); if(status!=EXR_OK) return status;
  status=m4b_composition(io,m,&stbl); if(status!=EXR_OK) return status;
  status=m4b_child(io,&stbl,M4B_TYPE('s','t','c','o'),0,&box); if(status!=EXR_OK) return status;
  status=m4b_child(io,&stbl,M4B_TYPE('c','o','6','4'),0,&alternative); if(status!=EXR_OK) return status;
  if((box.end!=0)==(alternative.end!=0)) return m4b_fail(io,"ISO-BMFF requires exactly one chunk-offset table");
  if(!box.end) box=alternative;
  status=m4b_table_box(io,&box,&m->chunks,box.type==M4B_TYPE('c','o','6','4') ? 8 : 4,0); if(status!=EXR_OK) return status;
  status=m4b_validate_sc(io,m); if(status!=EXR_OK) return status;
  return m4b_edits(io,m,trak);
}
static exr_status m4b_top(m4b_io *io,exr_m4b *m) {
  uint64_t at=0; m4b_box moov={0},mvhd,fragment,child; int ftyp=0,found=0; exr_status status;
  while(at<io->source->size) {
    status=m4b_box_at(io,at,io->source->size,&child); if(status!=EXR_OK) return status;
    if(child.type==M4B_TYPE('f','t','y','p')) { if(ftyp++ || child.end-child.data<8) return m4b_fail(io,"Invalid/duplicate ISO-BMFF ftyp"); }
    else if(child.type==M4B_TYPE('m','o','o','v')) { if(moov.end) return m4b_fail(io,"Duplicate ISO-BMFF moov"); moov=child; }
    else if(child.type==M4B_TYPE('m','d','a','t')) { if(m->media_count==256) return exr_fail(io->error,EXR_LIMIT,"ISO-BMFF exceeds 256 mdat extents"); m->media[m->media_count++]=child; }
    else if(child.type==M4B_TYPE('m','o','o','f')) return m4b_fail(io,"Fragmented ISO-BMFF audio is unsupported");
    at=child.end;
  }
  if(!ftyp || !moov.end || !m->media_count) return m4b_fail(io,"ISO-BMFF requires ftyp, moov and mdat");
  status=m4b_child(io,&moov,M4B_TYPE('m','v','e','x'),0,&fragment); if(status!=EXR_OK) return status;
  if(fragment.end) return m4b_fail(io,"Fragmented ISO-BMFF audio is unsupported");
  status=m4b_child(io,&moov,M4B_TYPE('m','v','h','d'),1,&mvhd); if(status!=EXR_OK) return status;
  { uint64_t duration; status=m4b_time_header(io,&mvhd,&m->movie_scale,&duration); if(status!=EXR_OK) return status; }
  for(at=moov.data;at<moov.end;at=child.end) {
    int audio; status=m4b_box_at(io,at,moov.end,&child); if(status!=EXR_OK) return status;
    if(child.type!=M4B_TYPE('t','r','a','k')) continue;
    status=m4b_track(io,m,&child,&audio); if(status!=EXR_OK) return status;
    if(audio) { found=1; break; }
  }
  return found ? EXR_OK : m4b_fail(io,"ISO-BMFF contains no supported AAC audio track");
}
static exr_status m4b_scaled(m4b_io *io,uint64_t time,uint32_t scale,uint32_t rate,int exact,int ceiling,uint64_t *frames) {
  uint64_t quotient=time/scale,remainder=time%scale,small=remainder*rate;
  if(quotient>UINT64_MAX/rate) return exr_fail(io->error,EXR_LIMIT,"ISO-BMFF duration exceeds PCM frame range");
  if(exact && small%scale) return m4b_fail(io,"ISO-BMFF media time does not map to an exact PCM boundary");
  small=small/scale+((ceiling && small%scale) ? 1 : 0);
  if(small>UINT64_MAX-quotient*rate) return exr_fail(io->error,EXR_LIMIT,"ISO-BMFF duration exceeds PCM frame range");
  *frames=quotient*rate+small; return EXR_OK;
}
static exr_status m4b_timeline(m4b_io *io,exr_m4b *m) {
  uint64_t packets=0,units=0,frames=0,play; uint32_t i; exr_status status;
  for(i=0;i<m->times.count;i++) {
    unsigned char b[8]; uint32_t count,delta; uint64_t duration=0;
    status=m4b_read_bytes(io,m->times.at+(uint64_t)i*8,b,8); if(status!=EXR_OK) return status;
    count=m4b_be32(b); delta=m4b_be32(b+4);
    if(!count || !delta || count>m->sizes.count-packets) return m4b_fail(io,"Invalid ISO-BMFF time-to-sample run");
    status=m4b_scaled(io,delta,m->media_scale,m->info.sample_rate,1,0,&duration); if(status!=EXR_OK) return status;
    if(!duration || duration>m->block || ((packets+count<m->sizes.count || count>1) && duration!=m->block)) return m4b_fail(io,"ISO-BMFF AAC duration differs from its decoded block");
    if((uint64_t)count*delta>UINT64_MAX-units || (uint64_t)count*duration>UINT64_MAX-frames) return exr_fail(io->error,EXR_LIMIT,"ISO-BMFF time-to-sample duration overflows");
    packets+=count; units+=(uint64_t)count*delta; frames+=(uint64_t)count*duration;
  }
  if(packets!=m->sizes.count || (m->media_duration && m->media_duration!=UINT64_MAX && m->media_duration!=UINT32_MAX && m->media_duration!=units)) return m4b_fail(io,"ISO-BMFF sample and media durations disagree");
  m->raw_frames=frames; play=frames;
  if(m->have_edit) {
    status=m4b_scaled(io,m->edit_start,m->media_scale,m->info.sample_rate,1,0,&m->trim); if(status!=EXR_OK) return status;
    if(m->trim>frames) return m4b_fail(io,"ISO-BMFF edit starts past audio duration");
    status=m4b_scaled(io,m->edit_duration,m->movie_scale,m->info.sample_rate,0,1,&play); if(status!=EXR_OK) return status;
    if(play>frames-m->trim) play=frames-m->trim;
    status=m4b_scaled(io,m->empty_duration,m->movie_scale,m->info.sample_rate,0,1,&m->leading); if(status!=EXR_OK) return status;
  }
  if(play>UINT64_MAX-m->leading) return exr_fail(io->error,EXR_LIMIT,"ISO-BMFF edited timeline overflows");
  m->info.frames=m->leading+play; return EXR_OK;
}
static exr_status m4b_decode(exr_m4b *m,NeAACDecHandle decoder,uint32_t size,NeAACDecFrameInfo *frame,const float **pcm,exr_error *e) {
  size_t i; *pcm=NeAACDecDecode(decoder,frame,m->packet,size);
  if(frame->error) return exr_fail(e,EXR_FORMAT,"ISO-BMFF AAC decoder: %s",NeAACDecGetErrorMessage(frame->error));
  if(!*pcm || !frame->bytesconsumed || frame->bytesconsumed>size || !frame->channels || frame->channels>8 || !frame->samples || frame->samples%frame->channels || frame->samples/frame->channels>2048 || !frame->samplerate || frame->samplerate>192000)
    return exr_fail(e,EXR_FORMAT,"Unsupported/invalid ISO-BMFF AAC output frame");
  if(m->info.sample_rate && (frame->samplerate!=m->info.sample_rate || frame->channels!=m->info.channels || frame->samples/frame->channels!=m->block)) return exr_fail(e,EXR_FORMAT,"ISO-BMFF AAC output format changes");
  for(i=0;i<frame->samples;i++) if(!isfinite((*pcm)[i])) return exr_fail(e,EXR_FORMAT,"ISO-BMFF AAC decoder produced nonfinite audio");
  return EXR_OK;
}
static exr_status m4b_restart(m4b_io *io,exr_m4b *m) {
  m4b_cursor first,next; uint32_t size=0; NeAACDecHandle decoder; NeAACDecConfigurationPtr config; unsigned long rate; unsigned char channels;
  NeAACDecFrameInfo frame={0}; const float *pcm; exr_status status=m4b_initial_cursor(io,m,&first); if(status!=EXR_OK) return status;
  status=m4b_packet(io,m,&first,&next,&size); if(status!=EXR_OK) return status;
  decoder=NeAACDecOpen(); if(!decoder) return exr_fail(io->error,EXR_MEMORY,"ISO-BMFF AAC decoder allocation failed");
  config=NeAACDecGetCurrentConfiguration(decoder);
  if(!config) { status=m4b_fail(io,"ISO-BMFF AAC configuration unavailable"); goto fail; }
  config->outputFormat=FAAD_FMT_FLOAT; config->downMatrix=0; config->dontUpSampleImplicitSBR=1;
  if(!NeAACDecSetConfiguration(decoder,config) || NeAACDecInit2(decoder,m->asc,(unsigned long)m->asc_size,&rate,&channels)) { status=m4b_fail(io,"ISO-BMFF AAC AudioSpecificConfig rejected"); goto fail; }
  NeAACDecPostSeekReset(decoder,1);
  status=m4b_decode(m,decoder,size,&frame,&pcm,io->error); if(status!=EXR_OK) goto fail;
  if(!exr_grow((void **)&m->cache,&m->cache_capacity,frame.samples,sizeof(*m->cache))) { status=exr_fail(io->error,EXR_MEMORY,"ISO-BMFF PCM cache allocation failed"); goto fail; }
  status=exr_control_cancel(io->control,io->error); if(status!=EXR_OK) goto fail;
  memcpy(m->cache,pcm,frame.samples*sizeof(*pcm));
  if(m->decoder) NeAACDecClose(m->decoder);
  m->decoder=decoder; m->info.sample_rate=(uint32_t)frame.samplerate; m->info.channels=frame.channels; m->block=(uint32_t)(frame.samples/frame.channels);
  m->cache_first=0; m->cache_frames=m->block; m->position=m->block; m->cursor=next; m->dirty=0; return EXR_OK;
fail:
  NeAACDecClose(decoder); return status;
}
int exr_m4b_available(void) { return 1; }
void exr_m4b_free(exr_m4b *m) { if(m) { if(m->decoder) NeAACDecClose(m->decoder); if(m->source.release) m->source.release(m->source.context); free(m->packet); free(m->cache); free(m); } }
const exr_m4b_info *exr_m4b_format(const exr_m4b *m) { return m ? &m->info : NULL; }
exr_status exr_m4b_open_source(const exr_source *source,exr_m4b **out,exr_error *e) {
  exr_m4b *m; m4b_io io; exr_status status;
  if(out) *out=NULL;
  if(!source || !out || !source->read_at || source->size<8) return exr_fail(e,EXR_ARGUMENT,"Invalid ISO-BMFF source");
  m=calloc(1,sizeof(*m)); if(!m) return exr_fail(e,EXR_MEMORY,"ISO-BMFF reader allocation failed");
  io=(m4b_io){source,&source->control,e,0,UINT64_C(67108864),0};
  status=m4b_top(&io,m); if(status!=EXR_OK) goto fail;
  status=m4b_restart(&io,m); if(status!=EXR_OK) goto fail;
  status=m4b_timeline(&io,m); if(status!=EXR_OK) goto fail;
  status=exr_control_poll(&source->control,EXR_STAGE_READ,io.bytes,source->size,e); if(status!=EXR_OK) goto fail;
  m->source=*source; memset(&m->source.control,0,sizeof(m->source.control)); *out=m; return exr_fail(e,EXR_OK,"");
fail:
  if(m->decoder) NeAACDecClose(m->decoder);
  free(m->packet); free(m->cache); free(m); return status;
}
exr_status exr_m4b_open(const char *path,const exr_control *control,exr_m4b **out,exr_error *e) {
  exr_source source; exr_status status;
  if(out) *out=NULL;
  if(!path || !out) return exr_fail(e,EXR_ARGUMENT,"Invalid ISO-BMFF file input");
  status=exr_file_source_limit(path,INT64_MAX,&source,e); if(status!=EXR_OK) return status;
  if(control) source.control=*control;
  status=exr_m4b_open_source(&source,out,e); if(status!=EXR_OK) source.release(source.context); return status;
}
exr_status exr_m4b_read(exr_m4b *m,uint64_t first,size_t requested,float *out,size_t *read,const exr_control *control,exr_error *e) {
  m4b_io io; size_t done=0; uint64_t work=0,target,play_end; exr_status status;
  if(read) *read=0;
  if(!m || !read || (requested && !out) || m->busy || first>m->info.frames) return exr_fail(e,EXR_ARGUMENT,"Invalid or reentrant ISO-BMFF audio read");
  if(requested>65536) return exr_fail(e,EXR_LIMIT,"ISO-BMFF audio read exceeds 65536 sample frames");
  if(requested) memset(out,0,requested*m->info.channels*sizeof(*out));
  m->busy=1; io=(m4b_io){&m->source,control,e,0,UINT64_C(268435456),0}; status=exr_control_cancel(control,e); if(status!=EXR_OK) goto finish;
  if(!requested || first==m->info.frames) goto complete;
  if(first<m->leading) { uint64_t silent=m->leading-first; done=silent<requested ? (size_t)silent : requested; }
  if(done==requested) goto complete;
  target=m->trim+(first+done-m->leading); play_end=m->trim+(m->info.frames-m->leading);
  if(m->dirty || target<m->cache_first) { status=m4b_restart(&io,m); if(status!=EXR_OK) goto finish; }
  while(done<requested && target<play_end) {
    if(target>=m->cache_first && target<m->position) {
      uint64_t end=m->position<play_end ? m->position : play_end; size_t begin=(size_t)(target-m->cache_first),count=(size_t)(end-target);
      if(count>requested-done) count=requested-done;
      memcpy(out+done*m->info.channels,m->cache+begin*m->info.channels,count*m->info.channels*sizeof(*out)); done+=count; target+=count;
      if(done==requested || target==play_end) break;
    }
    if(m->cursor.packet==m->sizes.count) { status=m4b_fail(&io,"ISO-BMFF AAC packets end before the presentation timeline"); goto finish; }
    if(work>=M4B_WORK_SAMPLES) { status=exr_fail(e,EXR_LIMIT,"ISO-BMFF accurate replay budget exhausted; retry retains decoder progress"); goto finish; }
    status=exr_control_poll(control,EXR_STAGE_READ,done,requested,e); if(status!=EXR_OK) goto finish;
    {
      m4b_cursor next; uint32_t size=0; NeAACDecFrameInfo frame={0}; const float *pcm;
      status=m4b_packet(&io,m,&m->cursor,&next,&size); if(status!=EXR_OK) goto finish;
      status=m4b_decode(m,m->decoder,size,&frame,&pcm,e); if(status!=EXR_OK) { m->dirty=1; goto finish; }
      if(m->position>UINT64_MAX-m->block) { m->dirty=1; status=exr_fail(e,EXR_LIMIT,"ISO-BMFF decoded sample timeline overflows"); goto finish; }
      memcpy(m->cache,pcm,frame.samples*sizeof(*pcm)); m->cache_first=m->position; m->position+=m->block; m->cache_frames=m->block; m->cursor=next; work+=m->block;
    }
  }
complete:
  status=exr_control_poll(control,EXR_STAGE_READ,done,done,e);
finish:
  m->busy=0;
  if(status!=EXR_OK) { if(requested) memset(out,0,requested*m->info.channels*sizeof(*out)); return status; }
  *read=done; return exr_fail(e,EXR_OK,"");
}
#else
struct exr_m4b { int unused; };
int exr_m4b_available(void) { return 0; }
void exr_m4b_free(exr_m4b *m) { free(m); }
const exr_m4b_info *exr_m4b_format(const exr_m4b *m) { (void)m; return NULL; }
exr_status exr_m4b_open_source(const exr_source *source,exr_m4b **out,exr_error *e) {
  if(out) *out=NULL;
  if(!source || !out || !source->read_at) return exr_fail(e,EXR_ARGUMENT,"Invalid ISO-BMFF source");
  return exr_fail(e,EXR_FORMAT,"AAC codec was disabled at build time");
}
exr_status exr_m4b_open(const char *path,const exr_control *control,exr_m4b **out,exr_error *e) {
  (void)control; if(out) *out=NULL;
  return exr_fail(e,path && out ? EXR_FORMAT : EXR_ARGUMENT,"AAC codec was disabled or input is invalid");
}
exr_status exr_m4b_read(exr_m4b *m,uint64_t first,size_t frames,float *output,size_t *read,const exr_control *control,exr_error *e) {
  (void)m; (void)first; (void)frames; (void)output; (void)control; if(read) *read=0;
  return exr_fail(e,EXR_ARGUMENT,"No ISO-BMFF AAC decoder handle");
}
#endif
