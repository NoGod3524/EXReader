/* SPDX-License-Identifier: GPL-3.0-only */
#include "pdf_internal.h"
typedef struct { uint32_t first,last; unsigned bytes; size_t offset,length; } cmap_range;
struct exr_pdf_cmap {
  cmap_range *spaces,*mappings; size_t space_count,space_capacity,count,capacity;
  exr_buffer strings;
};
typedef struct { exr_pdf_cmap *map; unsigned block,begun,ended,type; size_t expected; } cmap_reader;
static int compare_range(const void *a,const void *b) {
  const cmap_range *x=a,*y=b;
  if(x->bytes!=y->bytes) return x->bytes<y->bytes ? -1 : 1;
  return x->first<y->first ? -1 : x->first>y->first;
}
static const cmap_range *find_range(const cmap_range *ranges,size_t count,uint32_t code,unsigned bytes) {
  size_t low=0,high=count;
  while(low<high) {
    size_t middle=low+(high-low)/2;
    if(ranges[middle].bytes<bytes || (ranges[middle].bytes==bytes && ranges[middle].first<=code)) low=middle+1;
    else high=middle;
  }
  if(low && ranges[low-1].bytes==bytes && code<=ranges[low-1].last) return &ranges[low-1];
  return NULL;
}
static int source(exr_pdf_file *arena,uint32_t id,uint32_t *code,unsigned *bytes) {
  const exr_pdf_value *v=exr_pdf_value_at(arena,id); size_t size,i; const unsigned char *data=exr_pdf_bytes(arena,id,&size);
  if(!v || v->kind!=EXR_PDF_STRING || !data || !size || size>4) return 0;
  *code=0; *bytes=(unsigned)size; for(i=0;i<size;i++) *code=(*code<<8)|data[i]; return 1;
}
static int utf16(const unsigned char *data,size_t size,char out[256],size_t *length) {
  size_t at=0,n=0;
  if(size%2 || size>128) return 0;
  while(at<size) {
    uint32_t cp=((uint32_t)data[at]<<8)|data[at+1]; at+=2;
    if(cp>=0xd800 && cp<=0xdbff) {
      uint32_t low;
      if(size-at<2) return 0;
      low=((uint32_t)data[at]<<8)|data[at+1]; at+=2;
      if(low<0xdc00 || low>0xdfff) return 0;
      cp=0x10000+((cp-0xd800)<<10)+low-0xdc00;
    } else if(cp>=0xdc00 && cp<=0xdfff) return 0;
    if(cp<0x80) out[n++]=(char)cp;
    else if(cp<0x800) { out[n++]=(char)(0xc0|(cp>>6)); out[n++]=(char)(0x80|(cp&63)); }
    else if(cp<0x10000) { out[n++]=(char)(0xe0|(cp>>12)); out[n++]=(char)(0x80|((cp>>6)&63)); out[n++]=(char)(0x80|(cp&63)); }
    else { out[n++]=(char)(0xf0|(cp>>18)); out[n++]=(char)(0x80|((cp>>12)&63)); out[n++]=(char)(0x80|((cp>>6)&63)); out[n++]=(char)(0x80|(cp&63)); }
  }
  out[n]=0; *length=n; return 1;
}
static int target_increment(const unsigned char *base,size_t size,uint32_t delta,unsigned char out[128]) {
  size_t i=size;
  if(size) memcpy(out,base,size);
  while(i && delta) { uint32_t value=out[--i]+(delta&255); out[i]=(unsigned char)value; delta=(delta>>8)+(value>>8); }
  return !delta;
}
static exr_status add_mapping(exr_pdf_cmap *map,cmap_range range,exr_pdf_file *arena,uint32_t target,exr_error *error) {
  const exr_pdf_value *v=exr_pdf_value_at(arena,target); size_t size,n; const unsigned char *data=exr_pdf_bytes(arena,target,&size);
  char text[256]; unsigned char last[128];
  if(!v || v->kind!=EXR_PDF_STRING || !data || !utf16(data,size,text,&n) ||
     !target_increment(data,size,range.last-range.first,last) || !utf16(last,size,text,&n))
    return exr_fail(error,EXR_FORMAT,"Invalid PDF ToUnicode UTF-16 target or range overflow");
  if(map->count==262144 || size>(size_t)32*1024*1024-map->strings.size) return exr_fail(error,EXR_LIMIT,"PDF ToUnicode mapping budget exceeded");
  range.offset=map->strings.size; range.length=size;
  if(!exr_append(&map->strings,data,size) || !exr_grow((void **)&map->mappings,&map->capacity,map->count+1,sizeof(*map->mappings)))
    return exr_fail(error,EXR_MEMORY,"PDF ToUnicode mapping allocation failed");
  map->mappings[map->count++]=range; return EXR_OK;
}
static exr_status cmap_operation(void *context,exr_pdf_file *arena,const char *name,const uint32_t *values,size_t count,exr_error *error) {
  cmap_reader *r=context; exr_pdf_cmap *map=r->map; unsigned block=0; size_t i;
  if(!strcmp(name,"usecmap")) return exr_fail(error,EXR_FORMAT,"Inherited PDF ToUnicode CMaps are not implemented yet");
  if(!strcmp(name,"begincmap")) { if(count || r->begun) goto invalid; r->begun=1; return EXR_OK; }
  if(!strcmp(name,"endcmap")) { if(count || !r->begun || r->ended || r->block) goto invalid; r->ended=1; return EXR_OK; }
  if(!strcmp(name,"begincodespacerange")) block=1;
  else if(!strcmp(name,"beginbfchar")) block=2;
  else if(!strcmp(name,"beginbfrange")) block=3;
  if(block) {
    const exr_pdf_value *v=count==1 ? exr_pdf_value_at(arena,values[0]) : NULL;
    if(!r->begun || r->ended || r->block || !v || v->kind!=EXR_PDF_INT || v->u.integer<0 || v->u.integer>100) goto invalid;
    r->block=block; r->expected=(size_t)v->u.integer; return EXR_OK;
  }
  if(!strcmp(name,"endcodespacerange")) block=1;
  else if(!strcmp(name,"endbfchar")) block=2;
  else if(!strcmp(name,"endbfrange")) block=3;
  if(block) {
    size_t stride=block==3 ? 3 : 2;
    if(block!=r->block || count!=r->expected*stride) goto invalid;
    for(i=0;i<count;i+=stride) {
      cmap_range range={0}; unsigned bytes; exr_status status;
      if(!source(arena,values[i],&range.first,&range.bytes)) goto invalid;
      range.last=range.first;
      if(block!=2 && (!source(arena,values[i+1],&range.last,&bytes) || bytes!=range.bytes || range.first>range.last)) goto invalid;
      if(block==1) {
        if(map->space_count==256) return exr_fail(error,EXR_LIMIT,"PDF ToUnicode codespace budget exceeded");
        if(!exr_grow((void **)&map->spaces,&map->space_capacity,map->space_count+1,sizeof(*map->spaces))) return exr_fail(error,EXR_MEMORY,"PDF codespace allocation failed");
        map->spaces[map->space_count++]=range;
      } else {
        uint32_t target=values[i+(block==3 ? 2 : 1)]; const exr_pdf_value *v=exr_pdf_value_at(arena,target);
        if(block==3 && v && v->kind==EXR_PDF_ARRAY) {
          uint32_t at=v->first; uint64_t code=range.first;
          while(at!=EXR_PDF_NONE) {
            uint32_t next=exr_pdf_value_at(arena,at)->next; cmap_range single=range;
            if(code>range.last) goto invalid;
            single.first=single.last=(uint32_t)code++;
            status=add_mapping(map,single,arena,at,error); if(status!=EXR_OK) return status;
            at=next;
          }
          if(code!=(uint64_t)range.last+1) goto invalid;
        } else { status=add_mapping(map,range,arena,target,error); if(status!=EXR_OK) return status; }
      }
    }
    r->block=0; return EXR_OK;
  }
  if(r->block) goto invalid;
  if(!strcmp(name,"def") && count && exr_pdf_value_at(arena,values[0])->kind==EXR_PDF_NAME) {
    size_t n; const unsigned char *key=exr_pdf_bytes(arena,values[0],&n);
    if(n==8 && !memcmp(key,"CMapType",8)) {
      const exr_pdf_value *v=count==2 ? exr_pdf_value_at(arena,values[1]) : NULL;
      if(!v || v->kind!=EXR_PDF_INT || v->u.integer!=2) goto invalid;
      r->type=2;
    }
  }
  if(strstr(name,"cidchar") || strstr(name,"cidrange") || strstr(name,"notdef")) goto invalid;
  return EXR_OK;
invalid:
  return exr_fail(error,EXR_FORMAT,"Invalid PDF ToUnicode CMap block or operands");
}
void exr_pdf_cmap_free(exr_pdf_cmap *map) { if(map) { free(map->spaces); free(map->mappings); free(map->strings.data); free(map); } }
exr_status exr_pdf_cmap_parse(const void *data,size_t size,const exr_control *control,exr_pdf_cmap **out,exr_error *error) {
  cmap_reader r={0}; exr_pdf_cmap *map; size_t i,j; exr_status status;
  if(!out) return exr_fail(error,EXR_ARGUMENT,"Missing PDF ToUnicode CMap output");
  *out=NULL; map=calloc(1,sizeof(*map)); if(!map) return exr_fail(error,EXR_MEMORY,"PDF CMap allocation failed");
  r.map=map; status=exr_pdf_syntax_ops(data,size,cmap_operation,&r,1024,control,error);
  if(status!=EXR_OK) goto done;
  if(!r.begun || !r.ended || r.block || r.type!=2 || !map->space_count) goto invalid;
  qsort(map->spaces,map->space_count,sizeof(*map->spaces),compare_range);
  if(map->count) qsort(map->mappings,map->count,sizeof(*map->mappings),compare_range);
  for(i=0;i<map->space_count;i++) for(j=0;j<i;j++) {
    const cmap_range *a=&map->spaces[j],*b=&map->spaces[i]; unsigned shift=8*(b->bytes-a->bytes);
    if(a->last>=(b->first>>shift) && a->first<=(b->last>>shift)) goto invalid;
  }
  { size_t merged=0;
    for(i=0;i<map->space_count;i++) {
      if(merged && map->spaces[merged-1].bytes==map->spaces[i].bytes && (uint64_t)map->spaces[merged-1].last+1==map->spaces[i].first)
        map->spaces[merged-1].last=map->spaces[i].last;
      else map->spaces[merged++]=map->spaces[i];
    }
    map->space_count=merged;
  }
  for(i=0;i<map->count;i++) {
    const cmap_range *range=&map->mappings[i],*space;
    if(!(i&1023)) { status=exr_control_poll(control,EXR_STAGE_READ,i,map->count,error); if(status!=EXR_OK) goto done; }
    if(i && range->bytes==map->mappings[i-1].bytes && range->first<=map->mappings[i-1].last) goto invalid;
    space=find_range(map->spaces,map->space_count,range->first,range->bytes);
    if(!space || space->last<range->last) goto invalid;
  }
  *out=map; return EXR_OK;
invalid:
  status=exr_fail(error,EXR_FORMAT,"Missing, overlapping or ambiguous PDF ToUnicode codespaces/mappings");
done:
  exr_pdf_cmap_free(map); return status;
}
exr_status exr_pdf_cmap_next(const exr_pdf_cmap *map,const unsigned char *data,size_t size,size_t *at,exr_pdf_mapping *out,exr_error *error) {
  uint32_t code=0; unsigned bytes; const cmap_range *range; unsigned char target[128];
  if(out) memset(out,0,sizeof(*out));
  if(!map || !data || !at || *at>=size || !out) return exr_fail(error,EXR_ARGUMENT,"Missing PDF CMap character input/output");
  for(bytes=1;bytes<=4 && bytes<=size-*at;bytes++) {
    code=(code<<8)|data[*at+bytes-1];
    if(find_range(map->spaces,map->space_count,code,bytes)) break;
  }
  if(bytes>4 || bytes>size-*at) return exr_fail(error,EXR_FORMAT,"PDF character code is outside ToUnicode codespaces");
  range=find_range(map->mappings,map->count,code,bytes);
  if(!range) { memcpy(out->utf8,"\xef\xbf\xbd",4); out->size=3; }
  else if(!target_increment((const unsigned char *)map->strings.data+range->offset,range->length,code-range->first,target) || !utf16(target,range->length,out->utf8,&out->size))
    return exr_fail(error,EXR_FORMAT,"PDF ToUnicode range produces invalid UTF-16");
  out->code=code; out->code_bytes=bytes; *at+=bytes;
  if(error) memset(error,0,sizeof(*error));
  return EXR_OK;
}
