/* SPDX-License-Identifier: GPL-3.0-only */
#include "internal.h"
struct exr_fixed_text { char *text; size_t size,count,bytes; exr_text_region *regions; };
void exr_fixed_text_free(exr_fixed_text *text) { if(text) { free(text->text); free(text->regions); free(text); } }
const char *exr_fixed_text_string(const exr_fixed_text *text,size_t *size) { if(size) *size=text ? text->size : 0; return text ? text->text : NULL; }
const exr_text_region *exr_fixed_text_regions(const exr_fixed_text *text,size_t *count) { if(count) *count=text ? text->count : 0; return text ? text->regions : NULL; }
size_t exr_fixed_text_memory_size(const exr_fixed_text *text) { return text ? text->bytes : 0; }
exr_status exr_fixed_text_create(const char *utf8,size_t size,const exr_text_region *regions,size_t count,
                                  const exr_control *control,exr_fixed_text **out,exr_error *e) {
  exr_fixed_text *text; size_t at=0,examined=0,i,k,bytes=sizeof(*text); uint32_t cp; exr_status status;
  if(!out) return exr_fail(e,EXR_ARGUMENT,"Missing fixed text output");
  *out=NULL;
  if((!utf8 && size) || (!regions && count)) return exr_fail(e,EXR_ARGUMENT,"Missing fixed text input");
  if(size>EXR_MAX_TEXT || count>EXR_MAX_ITEMS || count>((size_t)128*1024*1024-bytes-size-1)/sizeof(*regions))
    return exr_fail(e,EXR_LIMIT,"Fixed text snapshot exceeds byte/count budget");
  if(!utf8) utf8="";
  status=exr_control_cancel(control,e); if(status!=EXR_OK) return status;
  while(at<size) {
    if(!(examined++&1023) && exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
    if(!exr_next(utf8,size,&at,&cp)) return exr_fail(e,EXR_ENCODING,"Fixed text is not UTF-8");
  }
  for(i=0;i<count;i++) {
    const exr_text_region *r=&regions[i];
    if(!(i&255) && exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
    if(r->start>r->end || r->end>size || (r->flags&~3u) ||
       (r->start<size && ((unsigned char)utf8[r->start]&0xc0)==0x80) ||
       (r->end<size && ((unsigned char)utf8[r->end]&0xc0)==0x80)) return exr_fail(e,EXR_ARGUMENT,"Invalid fixed text region range/flags");
    for(k=0;k<8;k++) if(!isfinite(r->quad[k]) || fabs(r->quad[k])>1e7) return exr_fail(e,EXR_ARGUMENT,"Invalid fixed text region quad");
  }
  text=calloc(1,sizeof(*text)); if(!text) return exr_fail(e,EXR_MEMORY,"Fixed text snapshot allocation failed");
  text->text=exr_copy(utf8,size); if(count) text->regions=malloc(count*sizeof(*regions));
  if(!text->text || (count && !text->regions)) { exr_fixed_text_free(text); return exr_fail(e,EXR_MEMORY,"Fixed text payload allocation failed"); }
  if(count) memcpy(text->regions,regions,count*sizeof(*regions));
  text->size=size; text->count=count; text->bytes=bytes+size+1+count*sizeof(*regions);
  status=exr_control_cancel(control,e); if(status!=EXR_OK) { exr_fixed_text_free(text); return status; }
  *out=text; return exr_fail(e,EXR_OK,"");
}
