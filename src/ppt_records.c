/* SPDX-License-Identifier: MIT */
#include "ppt_internal.h"

/* MS-PPT 2.13.24: 0x0FD9 is HeadersFooters, 0x0FF5 is UserEditAtom.
   Atoms normally have recVer=0; only recVer=F universally denotes a container. */
#define RT_DOCUMENT 0x03e8
#define RT_DOCUMENT_ATOM 0x03e9
#define RT_SLIDE 0x03ee
#define RT_SLIDE_ATOM 0x03ef
#define RT_SLIDE_PERSIST 0x03f3
#define RT_SLIDE_LIST 0x0ff0
typedef struct {
  const unsigned char *data;
  const exr_control *control;
  size_t slides,persist,documents,records;
  double width,height;
  int list;
} records;
static unsigned u16(const unsigned char *p) { return p[0]|((unsigned)p[1]<<8); }
static uint32_t u32(const unsigned char *p) {
  return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static exr_status walk(records *r,size_t at,size_t end,unsigned depth,unsigned parent,int slide_list,exr_error *e) {
  if(depth>64) return exr_fail(e,EXR_LIMIT,"PPT record recursion depth exceeds 64 at offset %zu",at);
  while(at<end) {
    unsigned type,ver,instance;size_t length,next;int container;exr_status s;
    if(end-at<8) return exr_fail(e,EXR_FORMAT,"PPT truncated record header at offset %zu",at);
    ver=u16(r->data+at);instance=ver>>4;ver&=15;
    type=u16(r->data+at+2);length=u32(r->data+at+4);
    if(length>end-at-8) return exr_fail(e,EXR_FORMAT,"PPT record length exceeds stream/container at offset %zu",at);
    next=at+8+length;
    if((++r->records&1023)==1) {
      s=exr_control_cancel(r->control,e);if(s!=EXR_OK) return s;
    }
    container=ver==15 || ((ver==0) && (type==RT_DOCUMENT || type==RT_SLIDE || type==RT_SLIDE_LIST));
    if(type==RT_DOCUMENT && !depth) {
      if(!container) return exr_fail(e,EXR_FORMAT,"PPT invalid DocumentContainer at offset %zu",at);
      /* Incremental saves append replacement document snapshots. The last
         complete snapshot supplies the current slide list and dimensions. */
      r->documents++;r->persist=0;r->list=0;r->width=720;r->height=540;
    }
    if(type==RT_SLIDE && container) r->slides++;
    if(type==RT_SLIDE_LIST && container && parent==RT_DOCUMENT && instance==0) r->list=1;
    if(type==RT_SLIDE_PERSIST && slide_list && parent==RT_SLIDE_LIST) {
      if(container || length<20) return exr_fail(e,EXR_FORMAT,"PPT short SlidePersistAtom at offset %zu",at);
      /* persistIdRef is payload+0, slideId is payload+12, not recInstance. */
      r->persist++;
    }
    if(type==RT_DOCUMENT_ATOM && parent==RT_DOCUMENT && !container && length>=8) {
      uint32_t w=u32(r->data+at+8),h=u32(r->data+at+12);
      /* MS-PPT master units are 1/576 inch = 1/8 pt. Invalid/missing
         dimensions fall back to the standard 10 x 7.5 inch slide. */
      if(w>=576 && w<=32256 && h>=576 && h<=32256) { r->width=w/8.0;r->height=h/8.0; }
    }
    if(type==RT_SLIDE_ATOM && !container && length<24)
      return exr_fail(e,EXR_FORMAT,"PPT short SlideAtom at offset %zu",at);
    if(container) {
      int child_list=type==RT_SLIDE_LIST && parent==RT_DOCUMENT && instance==0;
      s=walk(r,at+8,next,depth+1,type,child_list,e);if(s!=EXR_OK) return s;
    }
    at=next;
  }
  return EXR_OK;
}
exr_status exr_ppt_records(const void *data,size_t size,const exr_control *control,exr_ppt_info *out,exr_error *e) {
  records r={0};exr_status s;
  memset(out,0,sizeof(*out));
  if(size>EXR_PPT_MAX_STREAM) return exr_fail(e,EXR_LIMIT,"PPT stream exceeds 256 MiB");
  if(!data || !size) return exr_fail(e,EXR_FORMAT,"PPT missing DocumentContainer at offset 0");
  r.data=data;r.control=control;r.width=720;r.height=540;
  s=walk(&r,0,size,0,0,0,e);if(s!=EXR_OK) return s;
  if(!r.documents) return exr_fail(e,EXR_FORMAT,"PPT missing DocumentContainer at offset 0");
  out->pages=r.list ? r.persist : r.slides;out->slide_containers=r.slides;
  out->width=r.width;out->height=r.height;out->mismatch=r.list && r.persist!=r.slides;
  if(out->pages>10000) return exr_fail(e,EXR_LIMIT,"PPT exceeds 10000 slides");
  return exr_fail(e,EXR_OK,"");
}
