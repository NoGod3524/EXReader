/* SPDX-License-Identifier: MIT */
#include "exr/formats.h"
#include "lzma_internal.h"
#include <miniz.h>

#define SEVENZ_ITEMS 10000
#define SEVENZ_CODERS 4
typedef struct { const unsigned char *data; size_t size,at; exr_status status; } reader;
typedef struct { uint32_t value; int defined; } digest;
typedef struct {
  uint64_t method,size;
  unsigned char properties[5]; size_t property_size;
  unsigned next;
} coder;
typedef struct {
  coder coders[SEVENZ_CODERS]; unsigned count,first,last;
  size_t sub_count;
} folder;
typedef struct { size_t folder; uint64_t offset,size; digest crc; } substream;
typedef struct {
  uint64_t position,*packed;
  digest *pack_crc,*folder_crc;
  folder *folders; size_t count;
  substream *subs; size_t sub_count;
} streams;
struct exr_sevenz {
  exr_source source;
  exr_sevenz_options options;
  streams main;
  exr_sevenz_entry *entries; size_t *sub_index,count;
};

static const unsigned char *take(reader *r,size_t n) {
  const unsigned char *p;
  if(r->status!=EXR_OK) return NULL;
  if(n>r->size-r->at) { r->status=EXR_FORMAT; return NULL; }
  p=r->data+r->at; r->at+=n; return p;
}
static unsigned octet(reader *r) { const unsigned char *p=take(r,1); return p ? *p : 0; }
static uint64_t number(reader *r) {
  unsigned first=octet(r),mask=128,i; uint64_t value=0;
  for(i=0;i<8;i++,mask>>=1) {
    if(!(first&mask)) return value|((uint64_t)(first&(mask-1))<<(8*i));
    value|=(uint64_t)octet(r)<<(8*i);
  }
  return value;
}
static uint64_t little(const unsigned char *p,unsigned n) {
  uint64_t v=0; unsigned i;
  for(i=0;i<n;i++) v|=(uint64_t)p[i]<<(8*i);
  return v;
}
static size_t item_count(reader *r) {
  uint64_t n=number(r);
  if(n>SEVENZ_ITEMS) r->status=EXR_LIMIT;
  return r->status==EXR_OK ? (size_t)n : 0;
}
static int expect(reader *r,unsigned value) {
  if(octet(r)!=value && r->status==EXR_OK) r->status=EXR_FORMAT;
  return r->status==EXR_OK;
}
static uint32_t crc(const void *data,size_t size) { return (uint32_t)mz_crc32(MZ_CRC32_INIT,data,size); }
static int flag(const unsigned char *bits,size_t i) { return bits && (bits[i/8]&(128u>>(i%8))); }
static digest *digests(reader *r,size_t count) {
  digest *d; const unsigned char *bits=NULL; size_t i; unsigned all=octet(r);
  if(all>1) r->status=EXR_FORMAT;
  if(!all) bits=take(r,(count+7)/8);
  if(r->status!=EXR_OK) return NULL;
  d=calloc(count ? count : 1,sizeof(*d));
  if(!d) { r->status=EXR_MEMORY; return NULL; }
  for(i=0;i<count && r->status==EXR_OK;i++) {
    d[i].defined=all || flag(bits,i);
    if(d[i].defined) { const unsigned char *p=take(r,4); if(p) d[i].value=(uint32_t)little(p,4); }
  }
  return d;
}
static void streams_free(streams *s) {
  free(s->packed); free(s->pack_crc); free(s->folder_crc); free(s->folders); free(s->subs);
  memset(s,0,sizeof(*s));
}
static void read_folder(reader *r,folder *f) {
  size_t count=item_count(r); unsigned i,j,used=0,inputs=0,outputs=0;
  if(!count || count>SEVENZ_CODERS) { if(r->status==EXR_OK) r->status=EXR_UNSUPPORTED; return; }
  f->count=(unsigned)count; f->sub_count=1;
  for(i=0;i<f->count && r->status==EXR_OK;i++) {
    coder *c=&f->coders[i]; unsigned info=octet(r),len=info&15;
    uint64_t props=0;
    c->next=SEVENZ_CODERS;
    if(!len || len>8 || (info&0xc0)) { r->status=EXR_FORMAT; return; }
    for(j=0;j<len;j++) c->method=(c->method<<8)|octet(r);
    if(info&16) {
      uint64_t in=number(r),out=number(r);
      if(in!=1 || out!=1) { r->status=EXR_UNSUPPORTED; return; }
    }
    if(info&32) props=number(r);
    if(c->method!=0 && c->method!=0x030101 && c->method!=0x21 && c->method!=3) {
      r->status=EXR_UNSUPPORTED; return;
    }
    if(props!=(c->method==0x030101 ? 5u : (c->method ? 1u : 0u))) { r->status=EXR_FORMAT; return; }
    c->property_size=(size_t)props;
    for(j=0;j<props;j++) c->properties[j]=(unsigned char)octet(r);
    if((c->method==0x030101 && c->properties[0]>=225) ||
       (c->method==0x21 && c->properties[0]>40)) r->status=EXR_FORMAT;
  }
  for(i=1;i<f->count && r->status==EXR_OK;i++) {
    uint64_t in=number(r),out=number(r);
    if(in>=f->count || out>=f->count || in==out ||
       (inputs&(1u<<(unsigned)in)) || (outputs&(1u<<(unsigned)out))) { r->status=EXR_FORMAT; return; }
    inputs|=1u<<(unsigned)in; outputs|=1u<<(unsigned)out;
    f->coders[out].next=(unsigned)in;
  }
  for(i=0;i<f->count;i++) {
    if(!(inputs&(1u<<i))) f->first=i;
    if(!(outputs&(1u<<i))) f->last=i;
  }
  for(i=f->first;i<SEVENZ_CODERS;i=f->coders[i].next) {
    if(used&(1u<<i)) { r->status=EXR_FORMAT; return; }
    used|=1u<<i;
  }
  if(used!=(1u<<f->count)-1) r->status=EXR_FORMAT;
}
static uint64_t folder_size(const folder *f) { return f->coders[f->last].size; }
static void read_substreams(reader *r,streams *s,unsigned id) {
  size_t i,j,k=0,digest_count=0; int has_subs=id==8,has_sizes=0;
  if(has_subs) {
    id=octet(r);
    if(id==13) {
      for(i=0;i<s->count && r->status==EXR_OK;i++) s->folders[i].sub_count=item_count(r);
      id=octet(r);
    }
    if(id==9) has_sizes=1;
  }
  for(i=0;i<s->count;i++) {
    size_t n=s->folders[i].sub_count;
    if(n>SEVENZ_ITEMS-s->sub_count) { r->status=EXR_LIMIT; return; }
    s->sub_count+=n;
  }
  s->subs=calloc(s->sub_count ? s->sub_count : 1,sizeof(*s->subs));
  if(!s->subs) { r->status=EXR_MEMORY; return; }
  for(i=0;i<s->count && r->status==EXR_OK;i++) {
    folder *f=&s->folders[i]; uint64_t offset=0,total=folder_size(f);
    if((f->sub_count>1 && !has_sizes) || (!f->sub_count && total)) { r->status=EXR_FORMAT; break; }
    for(j=0;j<f->sub_count;j++,k++) {
      substream *sub=&s->subs[k]; uint64_t n=j+1==f->sub_count ? total-offset : number(r);
      if(n>total-offset) { r->status=EXR_FORMAT; break; }
      sub->folder=i; sub->size=n; sub->offset=offset; offset+=n;
      if(f->sub_count==1 && s->folder_crc && s->folder_crc[i].defined) sub->crc=s->folder_crc[i];
      else digest_count++;
    }
  }
  if(has_sizes) id=octet(r);
  if(has_subs && id==10 && r->status==EXR_OK) {
    digest *d=digests(r,digest_count); size_t at=0;
    if(d) for(i=0;i<s->sub_count;i++) if(!s->subs[i].crc.defined) s->subs[i].crc=d[at++];
    free(d); id=octet(r);
  }
  if(has_subs) { if(id!=0) r->status=EXR_FORMAT; expect(r,0); }
  else if(id!=0) r->status=EXR_FORMAT;
}
static void read_streams(reader *r,streams *s,uint64_t data_end) {
  unsigned id=octet(r); size_t i,j,count; uint64_t remaining;
  if(!id) return;
  if(id!=6) { r->status=EXR_FORMAT; return; }
  s->position=number(r); count=item_count(r);
  if(!count || !expect(r,9)) { if(r->status==EXR_OK) r->status=EXR_FORMAT; return; }
  s->packed=calloc(count,sizeof(*s->packed));
  if(!s->packed) { r->status=EXR_MEMORY; return; }
  if(s->position>data_end) { r->status=EXR_FORMAT; return; }
  remaining=data_end-s->position;
  for(i=0;i<count && r->status==EXR_OK;i++) {
    s->packed[i]=number(r);
    if(s->packed[i]>remaining) r->status=EXR_FORMAT;
    else remaining-=s->packed[i];
  }
  id=octet(r);
  if(id==10) { s->pack_crc=digests(r,count); id=octet(r); }
  if(id!=0 || !expect(r,7) || !expect(r,11)) { if(r->status==EXR_OK) r->status=EXR_FORMAT; return; }
  s->count=item_count(r);
  if(s->count!=count) { r->status=EXR_FORMAT; return; }
  if(octet(r)) { r->status=EXR_UNSUPPORTED; return; }
  s->folders=calloc(count,sizeof(*s->folders));
  if(!s->folders) { r->status=EXR_MEMORY; return; }
  for(i=0;i<count && r->status==EXR_OK;i++) read_folder(r,&s->folders[i]);
  if(!expect(r,12)) return;
  for(i=0;i<count && r->status==EXR_OK;i++) for(j=0;j<s->folders[i].count;j++)
    s->folders[i].coders[j].size=number(r);
  id=octet(r);
  if(id==10) { s->folder_crc=digests(r,count); id=octet(r); }
  if(id!=0) { r->status=EXR_FORMAT; return; }
  read_substreams(r,s,octet(r));
}
static exr_status read_at(exr_sevenz *z,uint64_t offset,void *buffer,size_t size,exr_error *e) {
  size_t done=0;
  if(offset>z->source.size || size>z->source.size-offset) return exr_fail(e,EXR_FORMAT,"7Z stream outside source");
  while(done<size) {
    size_t want=size-done,n; exr_status status=exr_control_cancel(&z->source.control,e);
    if(status!=EXR_OK) return status;
    if(want>65536) want=65536;
    n=z->source.read_at(z->source.context,offset+done,(unsigned char *)buffer+done,want);
    if(!n || n>want) return exr_fail(e,EXR_IO,"Short or invalid 7Z source read");
    done+=n;
  }
  return EXR_OK;
}
static exr_status decode_folder(exr_sevenz *z,const streams *s,size_t index,size_t limit,
  unsigned char **out,size_t *size,exr_error *e) {
  const folder *f=&s->folders[index]; uint64_t offset=32+s->position;
  unsigned char *data=NULL,*next; size_t i,n; unsigned c; exr_status status;
  *out=NULL; *size=0;
  if(s->packed[index]>limit) return exr_fail(e,EXR_LIMIT,"7Z packed block exceeds limit");
  for(c=0;c<f->count;c++) if(f->coders[c].size>limit)
    return exr_fail(e,EXR_LIMIT,"7Z unpacked block exceeds limit");
  for(i=0;i<index;i++) offset+=s->packed[i];
  n=(size_t)s->packed[index]; data=malloc(n ? n : 1);
  if(!data) return exr_fail(e,EXR_MEMORY,"7Z packed block allocation failed");
  status=read_at(z,offset,data,n,e);
  if(status==EXR_OK && s->pack_crc && s->pack_crc[index].defined && s->pack_crc[index].value!=crc(data,n))
    status=exr_fail(e,EXR_FORMAT,"7Z packed CRC mismatch");
  for(c=f->first;c<SEVENZ_CODERS && status==EXR_OK;c=f->coders[c].next) {
    const coder *codec=&f->coders[c]; size_t unpack=(size_t)codec->size;
    if(codec->method==0 || codec->method==3) {
      if(n!=unpack) { status=exr_fail(e,EXR_FORMAT,"7Z filter size mismatch"); break; }
      if(codec->method==3) {
        size_t distance=(size_t)codec->properties[0]+1;
        for(i=distance;i<n;i++) {
          if((i&65535)==0 && (status=exr_control_cancel(&z->source.control,e))!=EXR_OK) break;
          data[i]=(unsigned char)(data[i]+data[i-distance]);
        }
      }
    } else {
      next=malloc(unpack ? unpack : 1);
      if(!next) { status=exr_fail(e,EXR_MEMORY,"7Z output allocation failed"); break; }
      status=exr_lzma_decode(codec->method==0x21,codec->properties,codec->property_size,
        data,n,next,unpack,&z->source.control,e);
      free(data); data=next; n=unpack;
    }
  }
  if(status==EXR_OK && s->folder_crc && s->folder_crc[index].defined && s->folder_crc[index].value!=crc(data,n))
    status=exr_fail(e,EXR_FORMAT,"7Z folder CRC mismatch");
  if(status==EXR_OK) status=exr_control_cancel(&z->source.control,e);
  if(status!=EXR_OK) { free(data); return status; }
  *out=data; *size=n; return EXR_OK;
}
static int safe_path(char *path) {
  char *at=path,*start=path;
  if(!*path || *path=='/' || *path=='\\') return 0;
  for(;;at++) {
    if(*at=='\\') *at='/';
    if(*at==':' || ((unsigned char)*at<32 && *at)) return 0;
    if(!*at || *at=='/') {
      size_t n=(size_t)(at-start);
      if((n==1 && start[0]=='.') || (n==2 && start[0]=='.' && start[1]=='.')) return 0;
      if(!n && *at) return 0;
      if(!*at) return 1;
      start=at+1;
    }
  }
}
static void names(reader *r,exr_sevenz *z) {
  size_t i;
  if(octet(r)) { r->status=EXR_UNSUPPORTED; return; }
  for(i=0;i<z->count && r->status==EXR_OK;i++) {
    exr_buffer name={0};
    for(;;) {
      const unsigned char *p=take(r,2); uint32_t cp;
      if(!p) break;
      cp=(uint32_t)little(p,2);
      if(!cp) break;
      if(cp>=0xd800 && cp<=0xdbff) {
        uint32_t low; p=take(r,2); if(!p) break; low=(uint32_t)little(p,2);
        if(low<0xdc00 || low>0xdfff) { r->status=EXR_ENCODING; break; }
        cp=0x10000+((cp-0xd800)<<10)+low-0xdc00;
      } else if(cp>=0xdc00 && cp<=0xdfff) { r->status=EXR_ENCODING; break; }
      if(name.size>=2048) { r->status=EXR_LIMIT; break; }
      if(!exr_codepoint(&name,cp)) { r->status=EXR_MEMORY; break; }
    }
    if(r->status==EXR_OK && !exr_append(&name,"",1)) r->status=EXR_MEMORY;
    if(r->status==EXR_OK && !safe_path(name.data)) r->status=EXR_FORMAT;
    if(r->status!=EXR_OK) free(name.data);
    else z->entries[i].path=name.data;
  }
}
static void read_files(reader *r,exr_sevenz *z) {
  const unsigned char *empty=NULL,*empty_file=NULL;
  size_t empties=0,i,k=0,sub=0; unsigned seen=0,id;
  z->count=item_count(r);
  if(r->status!=EXR_OK) return;
  z->entries=calloc(z->count ? z->count : 1,sizeof(*z->entries));
  z->sub_index=calloc(z->count ? z->count : 1,sizeof(*z->sub_index));
  if(!z->entries || !z->sub_index) { r->status=EXR_MEMORY; return; }
  while(r->status==EXR_OK && (id=octet(r))!=0) {
    uint64_t n=number(r); const unsigned char *p; reader property;
    if(n>r->size-r->at) { r->status=EXR_FORMAT; break; }
    p=take(r,(size_t)n); if(!p) break;
    property=(reader){p,(size_t)n,0,EXR_OK};
    if(id>=14 && id<=17) {
      unsigned bit=1u<<(id-14);
      if(seen&bit) { r->status=EXR_FORMAT; break; }
      seen|=bit;
    }
    if(id==17) names(&property,z);
    else if(id==14) {
      empty=take(&property,(z->count+7)/8);
      for(i=0;i<z->count;i++) if(flag(empty,i)) empties++;
    } else if(id==15 || id==16) {
      const unsigned char *bits=take(&property,(empties+7)/8);
      if(!(seen&1)) property.status=EXR_FORMAT;
      if(id==15) empty_file=bits;
      else for(i=0;i<empties;i++) if(flag(bits,i)) property.status=EXR_UNSUPPORTED;
    } else property.at=property.size; /* Timestamp/attributes/comment/padding. */
    if(property.status!=EXR_OK) r->status=property.status;
    else if(property.at!=property.size) r->status=EXR_FORMAT;
  }
  if(r->status!=EXR_OK) return;
  if(z->count && !(seen&8)) { r->status=EXR_FORMAT; return; }
  for(i=0;i<z->count;i++) {
    z->sub_index[i]=SIZE_MAX;
    if(flag(empty,i)) z->entries[i].is_directory=!flag(empty_file,k++);
    else {
      if(sub==z->main.sub_count) { r->status=EXR_FORMAT; return; }
      z->sub_index[i]=sub; z->entries[i].size=z->main.subs[sub++].size;
    }
  }
  if(sub!=z->main.sub_count) r->status=EXR_FORMAT;
}
static void skip_properties(reader *r) {
  while(r->status==EXR_OK && octet(r)) {
    uint64_t n=number(r);
    if(n>r->size-r->at) r->status=EXR_FORMAT;
    else take(r,(size_t)n);
  }
}
void exr_sevenz_free(exr_sevenz *z) {
  size_t i;
  if(!z) return;
  if(z->source.release) z->source.release(z->source.context);
  streams_free(&z->main);
  if(z->entries) for(i=0;i<z->count;i++) free((void *)z->entries[i].path);
  free(z->entries); free(z->sub_index); free(z);
}
exr_sevenz_options exr_sevenz_options_defaults(void) {
  exr_sevenz_options options={sizeof(options),128u*1024*1024,16u*1024*1024}; return options;
}
exr_status exr_sevenz_open_source(const exr_source *source,const exr_sevenz_options *options,
  exr_sevenz **out,exr_error *e) {
  exr_sevenz *z; exr_status status; unsigned char signature[32],*header=NULL;
  uint64_t offset,n; reader r; unsigned id; streams encoded={0};
  if(out) *out=NULL;
  if(!out || !source || !source->read_at ||
     (options && (options->struct_size<sizeof(*options) || !options->max_unpack_size || !options->max_header_size)))
    return exr_fail(e,EXR_ARGUMENT,"Invalid 7Z open request");
  if(source->size<32) return exr_fail(e,EXR_FORMAT,"Truncated 7Z signature");
  z=calloc(1,sizeof(*z));
  if(!z) return exr_fail(e,EXR_MEMORY,"7Z container allocation failed");
  z->source=*source; z->source.release=NULL;
  z->options=options ? *options : exr_sevenz_options_defaults();
  status=read_at(z,0,signature,sizeof(signature),e);
  if(status!=EXR_OK) goto done;
  if(memcmp(signature,"7z\xbc\xaf\x27\x1c",6) || crc(signature+12,20)!=(uint32_t)little(signature+8,4)) {
    status=exr_fail(e,EXR_FORMAT,"Invalid 7Z signature or start-header CRC"); goto done;
  }
  if(signature[6]!=0) { status=exr_fail(e,EXR_UNSUPPORTED,"Unsupported 7Z major version"); goto done; }
  offset=little(signature+12,8); n=little(signature+20,8);
  if(offset>source->size-32 || n>source->size-32-offset) {
    status=exr_fail(e,EXR_FORMAT,"7Z next header outside source"); goto done;
  }
  if(n>z->options.max_header_size) { status=exr_fail(e,EXR_LIMIT,"7Z header exceeds limit"); goto done; }
  header=malloc(n ? (size_t)n : 1);
  if(!header) { status=exr_fail(e,EXR_MEMORY,"7Z header allocation failed"); goto done; }
  status=read_at(z,32+offset,header,(size_t)n,e);
  if(status!=EXR_OK) goto done;
  if(crc(header,(size_t)n)!=(uint32_t)little(signature+28,4)) {
    status=exr_fail(e,EXR_FORMAT,"7Z next-header CRC mismatch"); goto done;
  }
  if(!n) goto done;
  r=(reader){header,(size_t)n,0,EXR_OK}; id=octet(&r);
  if(id==23) {
    unsigned char *decoded=NULL; size_t decoded_size=0;
    read_streams(&r,&encoded,offset);
    if(r.status==EXR_OK && (r.at!=r.size || encoded.count!=1 || encoded.sub_count!=1)) r.status=EXR_FORMAT;
    if(r.status!=EXR_OK) { status=exr_fail(e,r.status,"Invalid or unsupported 7Z encoded header"); goto done; }
    status=decode_folder(z,&encoded,0,z->options.max_header_size,&decoded,&decoded_size,e);
    if(status!=EXR_OK) goto done;
    free(header); header=decoded;
    if(encoded.subs[0].crc.defined && encoded.subs[0].crc.value!=crc(header,decoded_size)) {
      status=exr_fail(e,EXR_FORMAT,"7Z decoded-header CRC mismatch"); goto done;
    }
    r=(reader){header,decoded_size,0,EXR_OK}; id=octet(&r);
  }
  if(id!=1) { status=exr_fail(e,EXR_FORMAT,"Missing 7Z header"); goto done; }
  id=octet(&r);
  if(id==2) { skip_properties(&r); id=octet(&r); }
  if(id==3) { status=exr_fail(e,EXR_UNSUPPORTED,"External 7Z metadata is unsupported"); goto done; }
  if(id==4) { read_streams(&r,&z->main,offset); id=octet(&r); }
  if(id==5 && r.status==EXR_OK) { read_files(&r,z); id=octet(&r); }
  if(r.status==EXR_OK && (id!=0 || r.at!=r.size || (!z->entries && z->main.sub_count))) r.status=EXR_FORMAT;
  status=exr_fail(e,r.status,r.status==EXR_OK ? "" : "Invalid, unsafe or unsupported 7Z directory");
done:
  streams_free(&encoded); free(header);
  if(status==EXR_OK) status=exr_control_cancel(&z->source.control,e);
  if(status!=EXR_OK) exr_sevenz_free(z);
  else { z->source.release=source->release; *out=z; }
  return status;
}
exr_status exr_sevenz_open(const char *path,const exr_sevenz_options *options,exr_sevenz **out,exr_error *e) {
  exr_source source; exr_status status;
  if(out) *out=NULL;
  if(!path || !out) return exr_fail(e,EXR_ARGUMENT,"Missing 7Z path or output");
  status=exr_file_source_limit(path,INT64_MAX,&source,e);
  if(status!=EXR_OK) return status;
  status=exr_sevenz_open_source(&source,options,out,e);
  if(status!=EXR_OK) source.release(source.context);
  return status;
}
const exr_sevenz_entry *exr_sevenz_entries(const exr_sevenz *z,size_t *count) {
  if(count) *count=z ? z->count : 0;
  return z ? z->entries : NULL;
}
exr_status exr_sevenz_extract(exr_sevenz *z,size_t index,void **out,size_t *size,exr_error *e) {
  unsigned char *data=NULL; size_t n=0; const substream *sub; exr_status status;
  if(out) *out=NULL;
  if(size) *size=0;
  if(!z || !out || !size || index>=z->count || z->entries[index].is_directory)
    return exr_fail(e,EXR_ARGUMENT,"Invalid 7Z file index or output");
  status=exr_control_cancel(&z->source.control,e);
  if(status!=EXR_OK) return status;
  if(z->sub_index[index]==SIZE_MAX) {
    data=malloc(1);
    if(!data) return exr_fail(e,EXR_MEMORY,"7Z empty file allocation failed");
    *out=data; return exr_fail(e,EXR_OK,"");
  }
  sub=&z->main.subs[z->sub_index[index]];
  status=decode_folder(z,&z->main,sub->folder,z->options.max_unpack_size,&data,&n,e);
  if(status!=EXR_OK) return status;
  if(sub->offset>n || sub->size>n-sub->offset ||
     (sub->crc.defined && sub->crc.value!=crc(data+(size_t)sub->offset,(size_t)sub->size))) {
    free(data); return exr_fail(e,EXR_FORMAT,"7Z member size or CRC mismatch");
  }
  memmove(data,data+(size_t)sub->offset,(size_t)sub->size);
  *out=data; *size=(size_t)sub->size; return exr_fail(e,EXR_OK,"");
}
