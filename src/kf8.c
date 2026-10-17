/* SPDX-License-Identifier: GPL-3.0-only */
#include "internal.h"

typedef struct {
  uint32_t label, fragments, start, length, file, sequence;
  unsigned present;
} entry;
typedef struct { entry *items; size_t count, capacity; } index_table;
typedef struct { unsigned tag, width, mask, end; } tag;
static uint16_t u16(const unsigned char *p) { return (uint16_t)((p[0]<<8)|p[1]); }
static uint32_t u32(const unsigned char *p) {
  return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];
}
static int vwi(const unsigned char *s,size_t end,size_t *at,uint32_t *out) {
  uint32_t value=0; unsigned n;
  for(n=0;n<5 && *at<end;n++) {
    unsigned b=s[(*at)++];
    if(value>(UINT32_MAX>>7)) return 0;
    value=(value<<7)|(b&127);
    if(b&128) { *out=value; return 1; }
  }
  return 0;
}
static int header(const exr_mobi_record *r) {
  return r->size>=192 && !memcmp(r->data,"INDX",4) && u32(r->data+4)>=192 &&
    u32(r->data+4)<=r->size && u32(r->data+28)!=65002 &&
    !u32(r->data+164) && !u32(r->data+168);
}
static int decimal(const unsigned char *s,size_t size,uint32_t *out) {
  size_t i; uint32_t value=0;
  if(!size) return 0;
  for(i=0;i<size;i++) {
    if(s[i]<'0' || s[i]>'9' || value>(UINT32_MAX-(s[i]-'0'))/10) return 0;
    value=value*10+(s[i]-'0');
  }
  *out=value; return 1;
}
static int decode_entry(const unsigned char *s,size_t size,const tag *tags,size_t nt,
                         size_t controls,int fragment,entry *out) {
  size_t at,control=0,i,j; uint32_t counts[64]={0}; unsigned bytes[64]={0};
  unsigned seen[256]={0};
  if(!size || (size_t)s[0]+1>size) return 0;
  if(fragment && !decimal(s+1,s[0],&out->label)) return 0;
  at=(size_t)s[0]+1;
  if(controls>size-at) return 0;
  /* Byte-length prefixes precede ALL value payloads, even for later tags. */
  for(i=0,j=at+controls;i<nt;i++) {
    unsigned value,mask=tags[i].mask;
    if(tags[i].end) { control++; continue; }
    if(control>=controls) return 0;
    value=s[at+control]&mask;
    if(!value) continue;
    if(seen[tags[i].tag]++) return 0;
    if(value==mask && (mask&(mask-1))) {
      bytes[i]=1;
      if(!vwi(s,size,&j,&counts[i])) return 0;
    } else {
      while(!(mask&1)) { mask>>=1; value>>=1; }
      counts[i]=value*tags[i].width;
    }
  }
  at=j;
  for(i=0;i<nt;i++) if(counts[i]) {
    size_t end=size,n=0; uint32_t values[2]={0};
    if(bytes[i]) { if(counts[i]>size-at) return 0; end=at+counts[i]; }
    while(bytes[i] ? at<end : n<counts[i]) {
      uint32_t value;
      if(!vwi(s,end,&at,&value)) return 0;
      if(n<2) values[n]=value;
      n++;
    }
    if(n%tags[i].width) return 0;
    switch(tags[i].tag) {
    case 1: if(!fragment) { if(n!=1) return 0; out->fragments=values[0]; out->present|=1; } break;
    case 3: if(fragment) { if(n!=1) return 0; out->file=values[0]; out->present|=2; } break;
    case 4: if(fragment) { if(n!=1) return 0; out->sequence=values[0]; out->present|=4; } break;
    case 6: if(n!=2) return 0; out->start=values[0]; out->length=values[1]; out->present|=8; break;
    default: break;
    }
  }
  while(at<size) if(s[at++]) return 0;
  return (out->present&(fragment ? 14u : 9u))==(fragment ? 14u : 9u);
}
static exr_status index_read(const exr_mobi_record *records,size_t nr,size_t first,
                               int fragment,index_table *out,exr_error *e) {
  const exr_mobi_record *r; const unsigned char *s; tag tags[64];
  size_t pos,len,nt,controls,sections,i,j,total=0; unsigned masks[32]={0};
  if(first>=nr || !header(&records[first])) goto bad;
  r=&records[first]; s=r->data; pos=u32(s+4); sections=u32(s+24);
  if(!sections || sections>nr-first-1 || u32(s+52)>nr-first-1-sections ||
     pos>r->size || r->size-pos<12 || memcmp(s+pos,"TAGX",4)) goto bad;
  len=u32(s+pos+4); controls=u32(s+pos+8);
  if(len<12 || len>r->size-pos || (len-12)%4 || (nt=(len-12)/4)>64 ||
     !controls || controls>32) goto bad;
  for(i=0,j=0;i<nt;i++) {
    const unsigned char *t=s+pos+12+i*4; unsigned shifted=t[2];
    tags[i]=(tag){t[0],t[1],t[2],t[3]};
    if(t[3]==1) { if(++j>controls) goto bad; continue; }
    if(t[3] || !t[1] || !shifted || j>=controls || (masks[j]&shifted)) goto bad;
    masks[j]|=shifted;
    while(!(shifted&1)) shifted>>=1;
    if(shifted&(shifted+1)) goto bad;
  }
  for(i=0;i<sections;i++) {
    size_t n,table,previous;
    r=&records[first+1+i]; s=r->data;
    if(!header(r)) goto bad;
    n=u32(s+24); table=u32(s+20); previous=u32(s+4);
    if(table<previous || table>r->size || r->size-table<4 ||
       memcmp(s+table,"IDXT",4) || n>(r->size-table-4)/2) goto bad;
    if(n>EXR_MAX_NODES-out->count) return exr_fail(e,EXR_LIMIT,"KF8 index entry limit exceeded");
    if(!exr_grow((void **)&out->items,&out->capacity,out->count+n,sizeof(*out->items)))
      return exr_fail(e,EXR_MEMORY,"KF8 index allocation failed");
    for(j=0;j<n;j++) {
      size_t start=u16(s+table+4+j*2),end=j+1<n ? u16(s+table+6+j*2) : table;
      entry v={0};
      if(start<previous || start>=end || end>table ||
         !decode_entry(s+start,end-start,tags,nt,controls,fragment,&v)) goto bad;
      out->items[out->count++]=v; previous=end;
    }
    total+=n;
  }
  if(total!=u32(records[first].data+36)) goto bad;
  return EXR_OK;
bad:
  return exr_fail(e,EXR_FORMAT,"Invalid or unsupported KF8 INDX/TAGX table");
}
static exr_status resource(exr_document *d,const char *path,const char *type,
                             const void *data,size_t size,size_t *index,exr_error *e) {
  exr_resource *r; exr_resource_data *bytes;
  if(d->resource_count>=10000) return exr_fail(e,EXR_LIMIT,"KF8 resource limit exceeded");
  if(!exr_grow((void **)&d->resources,&d->resource_capacity,d->resource_count+1,sizeof(*r))) goto memory;
  bytes=realloc(d->resource_data,(d->resource_count+1)*sizeof(*bytes));
  if(!bytes) goto memory;
  d->resource_data=bytes; *index=d->resource_count++;
  r=&d->resources[*index]; memset(r,0,sizeof(*r)); memset(&bytes[*index],0,sizeof(*bytes));
  r->id=exr_model_copy(d,path,strlen(path)); r->path=exr_model_copy(d,path,strlen(path));
  r->media_type=exr_model_copy(d,type,strlen(type)); r->properties=exr_model_copy(d,"",0);
  if(!r->id || !r->path || !r->media_type || !r->properties) return exr_fail(e,EXR_LIMIT,"KF8 metadata limit exceeded");
  bytes[*index].bytes=malloc(size ? size : 1);
  if(!bytes[*index].bytes) goto memory;
  if(size) memcpy(bytes[*index].bytes,data,size);
  bytes[*index].size=size; return EXR_OK;
memory:
  return exr_fail(e,EXR_MEMORY,"KF8 resource allocation failed");
}
exr_status exr_kf8(exr_document *d,const exr_mobi_record *records,size_t nr,
                    const char *text,size_t size,exr_error *e) {
  const unsigned char *h=records[0].data; size_t flow_size=size,flows,fdst,i,frag=0,work=0;
  index_table skeletons={0},fragments={0}; exr_status status=EXR_FORMAT;
  size_t skel,frags; exr_buffer part={0};
  if(u32(h+20)<248) goto bad;
  skel=u32(h+252); frags=u32(h+248); flows=u32(h+196); fdst=u32(h+192);
  if(flows>10000) { status=EXR_LIMIT; goto bad; }
  if(flows>1) {
    const exr_mobi_record *r; size_t end=0;
    if(fdst>=nr) goto bad;
    r=&records[fdst];
    if(r->size<12 || memcmp(r->data,"FDST",4) || u32(r->data+4)!=12 ||
       u32(r->data+8)!=flows || flows>(r->size-12)/8) goto bad;
    for(i=0;i<flows;i++) {
      size_t start=u32(r->data+12+i*8),stop=u32(r->data+16+i*8),index;
      char path[64];
      if(start!=end || start>stop || stop>size) goto bad;
      if(!i) flow_size=stop;
      else {
        snprintf(path,sizeof(path),"flow%04u.bin",(unsigned)i);
        status=resource(d,path,"application/octet-stream",text+start,stop-start,&index,e);
        if(status!=EXR_OK) goto done;
      }
      end=stop;
    }
    if(end!=size) goto bad;
  }
  if(skel!=UINT32_MAX) {
    status=index_read(records,nr,skel,0,&skeletons,e); if(status!=EXR_OK) goto done;
    if(frags!=UINT32_MAX) { status=index_read(records,nr,frags,1,&fragments,e); if(status!=EXR_OK) goto done; }
    if(!skeletons.count || skeletons.count>10000) goto bad;
  } else if(frags!=UINT32_MAX) goto bad;
  for(i=0;i<(skeletons.count ? skeletons.count : 1);i++) {
    size_t index,j,base; char path[64]; entry v={0};
    part.size=0;
    if(skeletons.count) v=skeletons.items[i]; else v.length=(uint32_t)flow_size;
    if(v.start>flow_size || v.length>flow_size-v.start ||
       v.fragments>fragments.count-frag) goto bad;
    if(i) {
      entry before=skeletons.items[i-1]; size_t previous=before.start+before.length;
      for(j=frag-before.fragments;j<frag;j++) previous+=fragments.items[j].length;
      if(v.start<previous) goto bad;
    }
    if(!exr_append(&part,text+v.start,v.length)) { status=EXR_LIMIT; goto bad; }
    base=(size_t)v.start+v.length;
    for(j=0;j<v.fragments;j++,frag++) {
      entry f=fragments.items[frag]; size_t insert;
      if(f.file!=i || f.label<v.start || (insert=f.label-v.start)>part.size ||
         base>flow_size || f.length>flow_size-base) goto bad;
      if(part.size>EXR_MAX_TEXT-f.length || part.size-insert>EXR_MAX_INPUT*2-work) { status=EXR_LIMIT; goto bad; }
      work+=part.size-insert;
      /* Reserve through the shared bounded buffer, then open the insertion gap. */
      if(!exr_append(&part,text+base,f.length)) { status=EXR_LIMIT; goto bad; }
      memmove(part.data+insert+f.length,part.data+insert,part.size-f.length-insert);
      memcpy(part.data+insert,text+base,f.length); base+=f.length;
    }
    snprintf(path,sizeof(path),"part%04u.xhtml",(unsigned)i);
    status=resource(d,path,"application/xhtml+xml",part.data,part.size,&index,e);
    if(status!=EXR_OK) goto done;
    status=exr_xhtml(d,part.data,part.size,index,1,1,e); if(status!=EXR_OK) goto done;
  }
  if(frag!=fragments.count) goto bad;
  status=EXR_OK; goto done;
bad:
  if(status==EXR_OK) status=EXR_FORMAT;
  exr_fail(e,status,"Invalid or unsupported KF8 reconstruction data");
done:
  free(part.data); free(skeletons.items); free(fragments.items); return status;
}
