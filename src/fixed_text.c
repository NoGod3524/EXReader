/* SPDX-License-Identifier: MIT */
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

exr_status exr_fixed_text_find(const exr_fixed_text *text,const char *query,size_t query_size,size_t from,
                                const exr_control *control,size_t *start,size_t *end,exr_error *e) {
  if(!text) { if(start) *start=SIZE_MAX; if(end) *end=SIZE_MAX; return exr_fail(e,EXR_ARGUMENT,"Missing fixed text snapshot"); }
  return exr_find_bytes(text->text,text->size,query,query_size,from,control,start,end,e);
}
exr_status exr_fixed_text_select(const exr_fixed_text *text,size_t start,size_t end,const exr_control *control,
                                  exr_text_region **out,size_t *count,exr_error *e) {
  size_t i,n=0; exr_text_region *regions=NULL; exr_status status;
  if(out) *out=NULL;
  if(count) *count=0;
  if(!text || !out || !count || start>end || end>text->size ||
     (start<text->size && ((unsigned char)text->text[start]&0xc0)==0x80) ||
     (end<text->size && ((unsigned char)text->text[end]&0xc0)==0x80)) return exr_fail(e,EXR_ARGUMENT,"Invalid fixed text selection");
  status=exr_control_cancel(control,e); if(status!=EXR_OK) return status;
  if(start==end) return exr_fail(e,EXR_OK,"");
  for(i=0;i<text->count;i++) {
    const exr_text_region *r=&text->regions[i];
    if(!(i&255) && exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
    if(r->start<r->end && r->start<end && start<r->end) n++;
  }
  if(n) {
    regions=malloc(n*sizeof(*regions)); if(!regions) return exr_fail(e,EXR_MEMORY,"Fixed selection allocation failed");
    n=0;
    for(i=0;i<text->count;i++) {
      const exr_text_region *r=&text->regions[i];
      if(!(i&255) && exr_control_cancel(control,e)!=EXR_OK) { free(regions); return EXR_CANCELLED; }
      if(r->start<r->end && r->start<end && start<r->end) regions[n++]=*r;
    }
  }
  *out=regions; *count=n; return exr_fail(e,EXR_OK,"");
}
static double quad_distance(const double q[8],double x,double y) {
  size_t i,j; int inside=0; double best=HUGE_VAL;
  for(i=0,j=3;i<4;j=i++) {
    double ax=q[j*2],ay=q[j*2+1],bx=q[i*2],by=q[i*2+1],dx=bx-ax,dy=by-ay;
    double length=dx*dx+dy*dy,t=length ? ((x-ax)*dx+(y-ay)*dy)/length : 0,ex,ey,d;
    if(t<0) t=0; else if(t>1) t=1;
    ex=x-(ax+t*dx); ey=y-(ay+t*dy); d=ex*ex+ey*ey; if(d<best) best=d;
    if((ay>y)!=(by>y) && x<ax+(y-ay)*(bx-ax)/(by-ay)) inside=!inside;
  }
  return inside ? 0 : best;
}
exr_status exr_fixed_text_hit(const exr_fixed_text *text,double x,double y,double maximum,unsigned exclude,
                               const exr_control *control,size_t *region,exr_error *e) {
  size_t i,found=SIZE_MAX; double best; exr_status status;
  if(region) *region=SIZE_MAX;
  if(!text || !region || !isfinite(x) || !isfinite(y) || fabs(x)>1e7 || fabs(y)>1e7 ||
     !isfinite(maximum) || maximum<0 || maximum>1e7 || (exclude&~3u)) return exr_fail(e,EXR_ARGUMENT,"Invalid fixed text hit request");
  status=exr_control_cancel(control,e); if(status!=EXR_OK) return status;
  best=maximum*maximum;
  for(i=0;i<text->count;i++) {
    double distance;
    if(!(i&255) && exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
    if(text->regions[i].flags&exclude) continue;
    distance=quad_distance(text->regions[i].quad,x,y);
    if(distance<=best && (found==SIZE_MAX || distance<best)) { found=i; best=distance; }
  }
  *region=found; return exr_fail(e,EXR_OK,"");
}
