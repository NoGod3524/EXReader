/* SPDX-License-Identifier: GPL-3.0-only */
#include "internal.h"
#include <miniz.h>
#include <ctype.h>

typedef struct {
  uint32_t label, fragments, start, length, file, sequence;
  unsigned present;
} entry;
typedef struct {
  uint32_t title,level,parent,first,last,fid,offset;
  unsigned present;
} nav_entry;
typedef union { entry book; nav_entry nav; } index_entry;
typedef struct { index_entry *items; size_t count, capacity; } index_table;
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
                         size_t controls,int kind,index_entry *output) {
  entry *out=&output->book; nav_entry *nav=&output->nav;
  size_t at,control=0,i,j; uint32_t counts[64]={0}; unsigned bytes[64]={0};
  unsigned seen[256]={0};
  if(!size || (size_t)s[0]+1>size) return 0;
  if(kind==1 && !decimal(s+1,s[0],&out->label)) return 0;
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
    if(kind==2) {
      if(tags[i].tag==6) {
        if(n!=2) return 0;
        nav->fid=values[0]; nav->offset=values[1]; nav->present|=32;
      } else {
        unsigned flag=0; uint32_t *field=NULL;
        switch(tags[i].tag) {
        case 3: field=&nav->title; flag=1; break;
        case 4: field=&nav->level; flag=2; break;
        case 21: field=&nav->parent; flag=4; break;
        case 22: field=&nav->first; flag=8; break;
        case 23: field=&nav->last; flag=16; break;
        default: break;
        }
        if(field) { if(n!=1) return 0; *field=values[0]; nav->present|=flag; }
      }
      continue;
    }
    switch(tags[i].tag) {
    case 1: if(kind==0) { if(n!=1) return 0; out->fragments=values[0]; out->present|=1; } break;
    case 3: if(kind==1) { if(n!=1) return 0; out->file=values[0]; out->present|=2; } break;
    case 4: if(kind==1) { if(n!=1) return 0; out->sequence=values[0]; out->present|=4; } break;
    case 6: if(n!=2) return 0; out->start=values[0]; out->length=values[1]; out->present|=8; break;
    default: break;
    }
  }
  while(at<size) if(s[at++]) return 0;
  if(kind==2) return (nav->present&35)==35;
  return (out->present&(kind==1 ? 14u : 9u))==(kind==1 ? 14u : 9u);
}
static exr_status index_read(const exr_mobi_record *records,size_t nr,size_t first,
                               int kind,index_table *out,exr_error *e) {
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
    if(n>(kind==2 ? 10000u : EXR_MAX_NODES)-out->count) return exr_fail(e,EXR_LIMIT,"KF8 index entry limit exceeded");
    if(!exr_grow((void **)&out->items,&out->capacity,out->count+n,sizeof(*out->items)))
      return exr_fail(e,EXR_MEMORY,"KF8 index allocation failed");
    for(j=0;j<n;j++) {
      size_t start=u16(s+table+4+j*2),end=j+1<n ? u16(s+table+6+j*2) : table;
      index_entry v; memset(&v,0,sizeof(v));
      if(kind==2) v.nav.parent=v.nav.first=v.nav.last=UINT32_MAX;
      if(start<previous || start>=end || end>table ||
         !decode_entry(s+start,end-start,tags,nt,controls,kind,&v)) goto bad;
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
typedef struct {
  exr_document *doc;
  const exr_mobi_record *records;
  const exr_mobi_record *shared;
  size_t count,first,flows,bytes,*mapped,shared_count;
  size_t queue[10000],queued,head;
  exr_error *error;
  exr_status status;
} assets;
static int asset_error(assets *a,exr_status status,const char *message) {
  a->status=exr_fail(a->error,status,"%s",message); return 0;
}
static int base32(const char *s,size_t size,size_t *at,uint32_t *out) {
  uint32_t value=0; size_t start=*at;
  while(*at<size) {
    unsigned c=(unsigned char)s[*at],digit;
    if(c>='0' && c<='9') digit=c-'0';
    else if(c>='A' && c<='V') digit=c-'A'+10;
    else if(c>='a' && c<='v') digit=c-'a'+10;
    else break;
    if(value>(UINT32_MAX-digit)/32) return 0;
    value=value*32+digit; (*at)++;
  }
  *out=value; return *at>start;
}
static const char *font_type(const unsigned char *s,size_t size) {
  if(size<4) return NULL;
  if(!memcmp(s,"\0\1\0\0",4) || !memcmp(s,"true",4)) return "font/ttf";
  if(!memcmp(s,"OTTO",4)) return "font/otf";
  if(!memcmp(s,"ttcf",4)) return "font/collection";
  if(!memcmp(s,"wOFF",4)) return "font/woff";
  if(!memcmp(s,"wOF2",4)) return "font/woff2";
  return NULL;
}
static int unpack_font(assets *a,const exr_mobi_record *r,unsigned char **data,
                         size_t *size,const char **type) {
  size_t length,offset,key_length,key_start,i; unsigned flags;
  unsigned char *packed=NULL,*out=NULL;
  if(r->size<24) goto bad;
  *size=u32(r->data+4); flags=u32(r->data+8); offset=u32(r->data+12);
  key_length=u32(r->data+16); key_start=u32(r->data+20);
  if(!*size || (flags&~3u) || offset<24 || offset>r->size) goto bad;
  length=r->size-offset;
  if(*size>32*1024*1024 || length>32*1024*1024 || *size>EXR_MAX_INPUT-a->bytes)
    return asset_error(a,EXR_LIMIT,"KF8 font or total asset byte budget exceeded");
  if((flags&2) && (!key_length || key_start<24 || key_start>offset || key_length>offset-key_start)) goto bad;
  packed=malloc(length ? length : 1); out=malloc(*size);
  if(!packed || !out) { free(packed); free(out); return asset_error(a,EXR_MEMORY,"KF8 font allocation failed"); }
  memcpy(packed,r->data+offset,length);
  if(flags&2) for(i=0;i<length && i<1040;i++) packed[i]^=r->data[key_start+i%key_length];
  if(flags&1) {
    mz_ulong output=(mz_ulong)*size,input=(mz_ulong)length;
    if(mz_uncompress2(out,&output,packed,&input)!=MZ_OK || output!=*size || input!=length) goto bad;
  } else {
    if(length!=*size) goto bad;
    memcpy(out,packed,length);
  }
  *type=font_type(out,*size); if(!*type) goto bad;
  free(packed); *data=out; return 1;
bad:
  free(packed); free(out); return asset_error(a,EXR_FORMAT,"Invalid or unsupported KF8 FONT record");
}
static int embed(assets *a,uint32_t number,size_t *index) {
  const exr_mobi_record *r; const unsigned char *s; const char *type=NULL;
  unsigned char *font=NULL; size_t size,record; char path[64];
  if(!number) return asset_error(a,EXR_FORMAT,"KF8 embedded resource index is zero");
  if(number<=a->shared_count) { record=number-1; r=&a->shared[record]; }
  else {
    size_t own=number-a->shared_count;
    if(a->first<=u16(a->records[0].data+8) || a->first>=a->count || own>a->count-a->first)
      return asset_error(a,EXR_FORMAT,"KF8 embedded resource index is out of range");
    record=a->shared_count+a->first+own-1; r=&a->records[a->first+own-1];
  }
  if(record>=a->count+a->shared_count)
    return asset_error(a,EXR_FORMAT,"KF8 embedded resource index is out of range");
  if(a->mapped[record]!=SIZE_MAX) { *index=a->mapped[record]; return 1; }
  s=r->data; size=r->size;
  if(size>=4 && !memcmp(s,"FONT",4)) {
    if(!unpack_font(a,r,&font,&size,&type)) return 0;
    s=font;
  } else if(size>=8 && !memcmp(s,"\x89PNG\r\n\x1a\n",8)) type="image/png";
  else if(size>=3 && s[0]==255 && s[1]==216 && s[2]==255) type="image/jpeg";
  else if(size>=6 && (!memcmp(s,"GIF87a",6) || !memcmp(s,"GIF89a",6))) type="image/gif";
  else if(size>=12 && !memcmp(s,"RIFF",4) && !memcmp(s+8,"WEBP",4)) type="image/webp";
  else type=font_type(s,size);
  if(!type) return asset_error(a,EXR_FORMAT,"Unknown KF8 embedded resource signature");
  if(size>32*1024*1024 || size>EXR_MAX_INPUT-a->bytes) {
    free(font); return asset_error(a,EXR_LIMIT,"KF8 asset byte budget exceeded");
  }
  snprintf(path,sizeof(path),"embed%05u.bin",number);
  a->status=resource(a->doc,path,type,s,size,index,a->error); free(font);
  if(a->status!=EXR_OK) return 0;
  a->mapped[record]=*index; a->bytes+=size; return 1;
}
/* Return a local path for an exact resource URI; an empty output means unchanged. */
static int asset_uri(assets *a,const char *s,size_t size,char path[2048]) {
  size_t at,index; uint32_t number; int flow; const char *mime=NULL;
  path[0]=0;
  if(size>=12 && !memcmp(s,"kindle:flow:",12)) { at=12; flow=1; }
  else if(size>=13 && !memcmp(s,"kindle:embed:",13)) { at=13; flow=0; }
  else return 1;
  if(!base32(s,size,&at,&number)) goto bad;
  if(at<size) {
    if(size-at<=6 || memcmp(s+at,"?mime=",6) || size-at-6>=128) goto bad;
    mime=s+at+6;
  }
  if(flow) {
    exr_resource *r; const char *type=NULL; size_t length=mime ? size-(size_t)(mime-s) : 0;
    if(!number || number>=a->flows) goto bad;
    if(length==8 && !memcmp(mime,"text/css",8)) type="text/css";
    else if(length==13 && !memcmp(mime,"image/svg+xml",13)) type="image/svg+xml";
    else goto bad;
    index=number-1; r=&a->doc->resources[index];
    if(!strcmp(r->media_type,"application/octet-stream")) {
      char *copy=exr_model_copy(a->doc,type,strlen(type));
      if(!copy) return asset_error(a,EXR_LIMIT,"KF8 resource metadata limit exceeded");
      free((void *)r->media_type); r->media_type=copy;
      if(!strcmp(type,"text/css")) a->queue[a->queued++]=index;
    } else if(strcmp(r->media_type,type)) goto bad;
  } else if(!embed(a,number,&index)) return 0;
  strcpy(path,a->doc->resources[index].path); return 1;
bad:
  return asset_error(a,EXR_FORMAT,"Invalid or unsupported KF8 resource URI");
}
static int css_space(unsigned c) { return c==' ' || c=='\t' || c=='\r' || c=='\n' || c=='\f'; }
static int css_rewrite(assets *a,const char *s,size_t size,exr_buffer *out) {
  size_t at=0,copy=0;
  while(at<size) {
    unsigned c=(unsigned char)s[at];
    if(c=='/' && at+1<size && s[at+1]=='*') {
      at+=2; while(at+1<size && (s[at]!='*' || s[at+1]!='/')) at++;
      at=at+1<size ? at+2 : size;
    } else if(c=='\'' || c=='"') {
      at++; while(at<size) { if(s[at]=='\\') { at+=at+1<size ? 2 : 1; continue; } if(s[at++]==(char)c) break; }
    } else if((c=='u' || c=='U') && size-at>=4 &&
                tolower((unsigned char)s[at+1])=='r' && tolower((unsigned char)s[at+2])=='l' &&
                s[at+3]=='(' && (!at || !(isalnum((unsigned char)s[at-1]) || s[at-1]=='_' || s[at-1]=='-'))) {
      size_t start,end,tail; unsigned quote=0; char path[2048];
      at+=4; while(at<size && css_space((unsigned char)s[at])) at++;
      if(at<size && (s[at]=='\'' || s[at]=='"')) quote=(unsigned char)s[at++];
      start=at;
      while(at<size && (quote ? (unsigned char)s[at]!=quote : s[at]!=')' && !css_space((unsigned char)s[at]))) {
        if(s[at]=='\\') at+=at+1<size ? 2 : 1; else at++;
      }
      end=at; tail=at;
      if(quote) { if(tail>=size || (unsigned char)s[tail]!=quote) continue; tail++; }
      while(tail<size && css_space((unsigned char)s[tail])) tail++;
      if(tail>=size || s[tail]!=')') continue;
      if(!asset_uri(a,s+start,end-start,path)) return 0;
      if(path[0]) {
        if(!exr_append(out,s+copy,start-copy) || !exr_append(out,path,strlen(path))) goto limit;
        copy=end;
      }
      at=tail+1;
    } else if(c=='\\') at+=at+1<size ? 2 : 1;
    else at++;
  }
  if(!exr_append(out,s+copy,size-copy)) goto limit;
  return 1;
limit:
  return asset_error(a,EXR_LIMIT,"KF8 rewritten CSS exceeds buffer limit");
}
static exr_status connect_assets(exr_document *d,const exr_mobi_record *records,size_t count,
                                   const exr_mobi_record *shared,size_t shared_count,size_t flows,exr_error *e) {
  assets a={0}; size_t i,j; exr_buffer css={0};
  a.doc=d; a.records=records; a.count=count; a.first=u32(records[0].data+108);
  a.shared=shared; a.shared_count=shared_count;
  a.flows=flows; a.error=e; a.status=EXR_OK;
  a.mapped=malloc((count+shared_count)*sizeof(*a.mapped)); if(!a.mapped) return exr_fail(e,EXR_MEMORY,"KF8 asset map allocation failed");
  for(i=0;i<count+shared_count;i++) a.mapped[i]=SIZE_MAX;
  for(i=0;i<d->resource_count;i++) a.bytes+=d->resource_data[i].size;
  if(a.bytes>EXR_MAX_INPUT) { asset_error(&a,EXR_LIMIT,"KF8 total resource byte budget exceeded"); goto done; }
  for(i=0;i<d->node_count;i++) {
    exr_node *v=&d->nodes[i];
    for(j=0;j<v->attribute_count;j++) {
      const char *key=v->attributes[j].name,*value=v->attributes[j].value,*local=strrchr(key,'|');
      char path[2048]; local=local ? local+1 : key;
      if(!strcmp(local,"src") || !strcmp(local,"href") || !strcmp(local,"poster") || !strcmp(local,"data")) {
        if(!asset_uri(&a,value,strlen(value),path)) goto done;
        if(path[0] && !exr_model_attribute(d,i,key,path)) goto limit;
      } else if(!strcmp(local,"style")) {
        css.size=0; if(!css_rewrite(&a,value,strlen(value),&css)) goto done;
        if(!exr_model_attribute(d,i,key,css.data)) goto limit;
      }
    }
    if(v->text && v->parent!=SIZE_MAX && !strcmp(exr_html_tag(d,&d->nodes[v->parent]),"style")) {
      char *copy;
      css.size=0; if(!css_rewrite(&a,v->text,strlen(v->text),&css)) goto done;
      if(!strcmp(css.data,v->text)) continue;
      copy=exr_model_copy(d,css.data,css.size); if(!copy) goto limit;
      free((void *)v->text); v->text=copy;
    }
  }
  while(a.head<a.queued) {
    size_t index=a.queue[a.head++],old=d->resource_data[index].size;
    css.size=0;
    if(!css_rewrite(&a,(const char *)d->resource_data[index].bytes,old,&css)) goto done;
    if(css.size>EXR_MAX_INPUT-(a.bytes-old)) goto limit;
    a.bytes=a.bytes-old+css.size;
    free(d->resource_data[index].bytes); d->resource_data[index].bytes=(unsigned char *)css.data;
    d->resource_data[index].size=css.size; memset(&css,0,sizeof(css));
  }
  goto done;
limit:
  asset_error(&a,EXR_LIMIT,"KF8 rewritten model or resource byte budget exceeded");
done:
  free(css.data); free(a.mapped); return a.status;
}
typedef struct { size_t offset,node,chapter; const char *id,*declared_id; } source_mark;
typedef struct { size_t start,length,first,count; } source_part;
typedef struct {
  exr_document *doc;
  source_mark *marks;
  size_t count,capacity;
  source_part *parts;
} source_map;
static exr_status source_position(void *context,size_t offset,size_t node) {
  source_map *map=context; exr_node *v=&map->doc->nodes[node];
  const char *id=exr_node_attribute(v,"id"),*tag_name=exr_html_tag(map->doc,v);
  int body=!strcmp(tag_name,"body");
  if(!id) id=exr_node_attribute(v,"http://www.w3.org/XML/1998/namespace|id");
  if(!id && !strcmp(tag_name,"a")) {
    id=exr_node_attribute(v,"name");
    if(id && *id && !exr_model_attribute(map->doc,node,"id",id)) return EXR_LIMIT;
    id=exr_node_attribute(v,"id");
  }
  if(!body && (!id || !*id)) return EXR_OK;
  if(!exr_grow((void **)&map->marks,&map->capacity,map->count+1,sizeof(*map->marks))) return EXR_MEMORY;
  map->marks[map->count++]=(source_mark){offset,body ? map->doc->chapters[v->chapter].root : node,
                                        v->chapter,body ? NULL : id,id};
  map->parts[v->chapter].count++; return EXR_OK;
}
static int mark_order(const void *left,const void *right) {
  const source_mark *a=left,*b=right;
  if(a->chapter!=b->chapter) return a->chapter<b->chapter ? -1 : 1;
  if(!a->declared_id || !b->declared_id) return (!a->declared_id)-(!b->declared_id);
  return strcmp(a->declared_id,b->declared_id);
}
static exr_status position_uri(const source_map *map,const index_table *fragments,
                                 const char *uri,char out[2048],exr_error *e) {
  size_t at=15,size=strlen(uri),part,offset,low,high; uint32_t fid,off;
  const entry *f; const source_part *p; const char *id=NULL; exr_buffer b={0};
  exr_status status=EXR_FORMAT;
  out[0]=0;
  if(size<11 || memcmp(uri,"kindle:pos:",11)) return EXR_OK;
  if(size<15 || memcmp(uri,"kindle:pos:fid:",15)) goto bad;
  if(!base32(uri,size,&at,&fid) || size-at<5 || memcmp(uri+at,":off:",5)) goto bad;
  at+=5;
  if(!base32(uri,size,&at,&off) || at!=size || fid>=fragments->count) goto bad;
  f=&fragments->items[fid].book; part=f->file;
  if(part>=map->doc->chapter_count || off>=f->length) goto bad;
  p=&map->parts[part];
  if(f->label<p->start || (size_t)(f->label-p->start)>p->length ||
     off>=p->length-(f->label-p->start)) goto bad;
  offset=(size_t)(f->label-p->start)+off; low=p->first; high=low+p->count;
  while(low<high) {
    size_t middle=low+(high-low)/2;
    if(map->marks[middle].offset<=offset) low=middle+1; else high=middle;
  }
  if(low>p->first) id=map->marks[low-1].id;
  if(!exr_append(&b,map->doc->chapters[part].path,strlen(map->doc->chapters[part].path)) ||
     (id && (!exr_append(&b,"#",1) || !exr_uri_path(&b,id)))) { status=EXR_LIMIT; goto bad; }
  if(b.size>=2048) { status=EXR_LIMIT; goto bad; }
  memcpy(out,b.data,b.size+1); free(b.data); return EXR_OK;
bad:
  free(b.data); return exr_fail(e,status,"Invalid or unsupported KF8 position URI");
}
static exr_status connect_positions(source_map *map,const index_table *fragments,exr_error *e) {
  source_mark *sorted=NULL; size_t i,j; exr_status status=EXR_OK;
  if(map->count) {
    sorted=malloc(map->count*sizeof(*sorted));
    if(!sorted) return exr_fail(e,EXR_MEMORY,"KF8 anchor index allocation failed");
    memcpy(sorted,map->marks,map->count*sizeof(*sorted));
    qsort(sorted,map->count,sizeof(*sorted),mark_order);
    for(i=1;i<map->count;i++) if(sorted[i].declared_id && sorted[i-1].declared_id && !mark_order(&sorted[i-1],&sorted[i])) {
      free(sorted); return exr_fail(e,EXR_FORMAT,"Duplicate KF8 anchor ID");
    }
    free(sorted);
  }
  for(i=0;i<map->doc->node_count;i++) {
    exr_node *v=&map->doc->nodes[i];
    for(j=0;j<v->attribute_count;j++) {
      const char *key=v->attributes[j].name,*local=strrchr(key,'|'); char uri[2048];
      local=local ? local+1 : key;
      if(strcmp(local,"href")) continue;
      status=position_uri(map,fragments,v->attributes[j].value,uri,e);
      if(status!=EXR_OK) return status;
      if(uri[0] && !exr_model_attribute(map->doc,i,key,uri)) return exr_fail(e,EXR_LIMIT,"KF8 link metadata limit exceeded");
    }
  }
  return EXR_OK;
}
typedef struct { uint32_t key; const char *text; size_t size; } cncx_string;
static exr_status cncx_read(const exr_mobi_record *records,size_t nr,size_t first,
                              cncx_string **out,size_t *count,exr_error *e) {
  size_t sections=u32(records[first].data+24),strings=u32(records[first].data+52);
  size_t i,capacity=0,bytes=0; exr_status status=EXR_OK;
  *out=NULL; *count=0;
  if(sections>nr-first-1 || strings>nr-first-1-sections) goto bad;
  for(i=0;i<strings;i++) {
    const exr_mobi_record *r=&records[first+1+sections+i]; size_t at=0;
    if(r->size>65536) goto bad;
    while(at<r->size) {
      size_t start=at; uint32_t length;
      if(!r->data[at]) {
        while(at<r->size) if(r->data[at++]) goto bad;
        break;
      }
      if(!vwi(r->data,r->size,&at,&length) || length>r->size-at) goto bad;
      if(*count>=EXR_MAX_NODES || length>EXR_MAX_TEXT-bytes) { status=EXR_LIMIT; goto bad; }
      status=exr_xml_text((const char *)r->data+at,length,"KF8 CNCX label",e);
      if(status!=EXR_OK) return status;
      if(!exr_grow((void **)out,&capacity,*count+1,sizeof(**out))) { status=EXR_MEMORY; goto bad; }
      (*out)[(*count)++]=(cncx_string){(uint32_t)(i*65536+start),(const char *)r->data+at,length};
      bytes+=length; at+=length;
    }
  }
  return EXR_OK;
bad:
  return exr_fail(e,status==EXR_OK ? EXR_FORMAT : status,"Invalid or oversized KF8 CNCX strings");
}
static const cncx_string *cncx_find(const cncx_string *strings,size_t count,uint32_t key) {
  size_t low=0,high=count;
  while(low<high) {
    size_t middle=low+(high-low)/2;
    if(strings[middle].key<key) low=middle+1; else high=middle;
  }
  return low<count && strings[low].key==key ? &strings[low] : NULL;
}
static int xml_escape(exr_buffer *out,const char *s,size_t size) {
  size_t i;
  for(i=0;i<size;i++) {
    const char *replacement=s[i]=='&' ? "&amp;" : s[i]=='<' ? "&lt;" : s[i]=='>' ? "&gt;" :
      s[i]=='"' ? "&quot;" : s[i]=='\r' ? "&#13;" : s[i]=='\n' ? "&#10;" : s[i]=='\t' ? "&#9;" : NULL;
    if(!exr_append(out,replacement ? replacement : s+i,replacement ? strlen(replacement) : 1)) return 0;
  }
  return 1;
}
static void to_base32(uint32_t value,char out[8]) {
  const char alphabet[]="0123456789ABCDEFGHIJKLMNOPQRSTUV"; char reversed[8]; size_t n=0,i;
  do { reversed[n++]=alphabet[value&31]; value>>=5; } while(value);
  for(i=0;i<n;i++) out[i]=reversed[n-1-i];
  out[n]=0;
}
static exr_status build_navigation(source_map *map,const index_table *fragments,
                                     const exr_mobi_record *records,size_t nr,size_t first,exr_error *e) {
  index_table table={0}; cncx_string *strings=NULL; size_t string_count=0,i,depth=0,index;
  size_t stack[252],*parents=NULL,*first_child=NULL,*last_child=NULL,*ends=NULL;
  exr_buffer xml={0}; exr_status status;
  if(first==UINT32_MAX) return EXR_OK;
  status=index_read(records,nr,first,2,&table,e); if(status!=EXR_OK) goto done;
  if(!table.count) { status=EXR_FORMAT; goto bad; }
  status=cncx_read(records,nr,first,&strings,&string_count,e); if(status!=EXR_OK) goto done;
  parents=malloc(table.count*sizeof(*parents)); first_child=malloc(table.count*sizeof(*first_child));
  last_child=malloc(table.count*sizeof(*last_child)); ends=malloc(table.count*sizeof(*ends));
  if(!parents || !first_child || !last_child || !ends) { status=EXR_MEMORY; goto bad; }
  for(i=0;i<table.count;i++) first_child[i]=last_child[i]=SIZE_MAX;
  for(i=0;i<table.count;i++) {
    const nav_entry *v=&table.items[i].nav;
    if(v->level>250 || v->level>depth) { status=EXR_FORMAT; goto bad; }
    while(depth>v->level) ends[stack[--depth]]=i;
    parents[i]=depth ? stack[depth-1] : SIZE_MAX;
    if((v->present&4) && (v->parent==UINT32_MAX ? SIZE_MAX : v->parent)!=parents[i]) { status=EXR_FORMAT; goto bad; }
    if(parents[i]!=SIZE_MAX) {
      if(first_child[parents[i]]==SIZE_MAX) first_child[parents[i]]=i;
      last_child[parents[i]]=i;
    }
    stack[depth++]=i;
  }
  while(depth) ends[stack[--depth]]=table.count;
  for(i=0;i<table.count;i++) {
    const nav_entry *v=&table.items[i].nav;
    if((v->present&24)==0) continue;
    if((v->present&24)!=24) { status=EXR_FORMAT; goto bad; }
    if(first_child[i]==SIZE_MAX) {
      if(v->first!=UINT32_MAX || v->last!=UINT32_MAX) { status=EXR_FORMAT; goto bad; }
    } else if(v->first!=first_child[i] || v->last<last_child[i] || v->last>=ends[i]) { status=EXR_FORMAT; goto bad; }
  }
#define PUT(s) do { if(!exr_append(&xml,s,strlen(s))) { status=EXR_LIMIT; goto bad; } } while(0)
  PUT("<ncx xmlns=\"http://www.daisy.org/z3986/2005/ncx/\" version=\"2005-1\"><head/><docTitle><text>Contents</text></docTitle><navMap>");
  for(i=0;i<table.count;i++) {
    const nav_entry *v=&table.items[i].nav; const cncx_string *label=cncx_find(strings,string_count,v->title);
    char uri[64],target[2048],fid[8],offset[8],value[80];
    if(!label) { status=EXR_FORMAT; goto bad; }
    while(depth>v->level) { PUT("</navPoint>"); depth--; }
    to_base32(v->fid,fid); to_base32(v->offset,offset);
    snprintf(uri,sizeof(uri),"kindle:pos:fid:%s:off:%s",fid,offset);
    status=position_uri(map,fragments,uri,target,e); if(status!=EXR_OK) goto done;
    snprintf(value,sizeof(value),"<navPoint id=\"n%u\" playOrder=\"%u\"><navLabel><text>",(unsigned)i,(unsigned)i+1);
    PUT(value);
    if(!xml_escape(&xml,label->text,label->size)) { status=EXR_LIMIT; goto bad; }
    PUT("</text></navLabel><content src=\"");
    if(!xml_escape(&xml,target,strlen(target))) { status=EXR_LIMIT; goto bad; }
    PUT("\"/>"); depth++;
  }
  while(depth) { PUT("</navPoint>"); depth--; }
  PUT("</navMap></ncx>");
#undef PUT
  status=resource(map->doc,"kf8-navigation.ncx","application/x-dtbncx+xml",xml.data,xml.size,&index,e);
  if(status==EXR_OK) { map->doc->has_ncx=1; map->doc->ncx_resource=index; }
  goto done;
bad:
  exr_fail(e,status,"Invalid or oversized KF8 navigation hierarchy or label");
done:
  free(table.items); free(strings); free(parents); free(first_child); free(last_child); free(ends); free(xml.data);
  return status;
}
exr_status exr_kf8(exr_document *d,const exr_mobi_record *records,size_t nr,
                    const exr_mobi_record *shared,size_t shared_count,const char *text,size_t size,exr_error *e) {
  const unsigned char *h=records[0].data; size_t flow_size=size,flows,fdst,i,frag=0,work=0;
  index_table skeletons={0},fragments={0}; exr_status status=EXR_FORMAT;
  size_t skel,frags; exr_buffer part={0};
  source_map map={0}; map.doc=d;
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
  map.parts=calloc(skeletons.count ? skeletons.count : 1,sizeof(*map.parts));
  if(!map.parts) { status=EXR_MEMORY; goto bad; }
  for(i=0;i<(skeletons.count ? skeletons.count : 1);i++) {
    size_t index,j,base; char path[64]; entry v={0};
    part.size=0;
    if(skeletons.count) v=skeletons.items[i].book; else v.length=(uint32_t)flow_size;
    if(v.start>flow_size || v.length>flow_size-v.start ||
       v.fragments>fragments.count-frag) goto bad;
    if(i) {
      entry before=skeletons.items[i-1].book; size_t previous=before.start+before.length;
      for(j=frag-before.fragments;j<frag;j++) previous+=fragments.items[j].book.length;
      if(v.start<previous) goto bad;
    }
    if(!exr_append(&part,text+v.start,v.length)) { status=EXR_LIMIT; goto bad; }
    base=(size_t)v.start+v.length;
    for(j=0;j<v.fragments;j++,frag++) {
      entry f=fragments.items[frag].book; size_t insert;
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
    map.parts[i]=(source_part){v.start,part.size,map.count,0};
    status=exr_xhtml_positions(d,part.data,part.size,index,source_position,&map,e);
    if(status!=EXR_OK) goto done;
  }
  if(frag!=fragments.count) goto bad;
  status=connect_positions(&map,&fragments,e); if(status!=EXR_OK) goto done;
  status=build_navigation(&map,&fragments,records,nr,u32(h+244),e); if(status!=EXR_OK) goto done;
  status=connect_assets(d,records,nr,shared,shared_count,flows,e); goto done;
bad:
  if(status==EXR_OK) status=EXR_FORMAT;
  exr_fail(e,status,"Invalid or unsupported KF8 reconstruction data");
done:
  free(map.marks); free(map.parts); free(part.data); free(skeletons.items); free(fragments.items); return status;
}
