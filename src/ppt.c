/* SPDX-License-Identifier: MIT */
#include "ppt_internal.h"

static unsigned u16(const unsigned char *p) { return p[0]|((unsigned)p[1]<<8); }
static uint32_t u32(const unsigned char *p) {
  return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
/* OLE property set: PIDSI_TITLE=2, VT_LPSTR=30, VT_LPWSTR=31.
   Optional malformed/unsupported properties leave the title empty. */
static char *summary_title(const unsigned char *p,size_t size) {
  size_t section,extent,count,i,title=0;unsigned codepage=1252,type;uint32_t n;
  exr_buffer text={0};
  if(!p || size<48 || u16(p)!=0xfffe || !u32(p+24)) return NULL;
  section=u32(p+44);
  if(section>size || size-section<8) return NULL;
  extent=u32(p+section);count=u32(p+section+4);
  if(extent<8 || extent>size-section || count>(extent-8)/8) return NULL;
  for(i=0;i<count;i++) {
    size_t entry=section+8+8*i,offset=u32(p+entry+4);unsigned id=u32(p+entry);
    if(offset<8+8*count || offset>extent || extent-offset<4) return NULL;
    if(id==2) title=offset;
    if(id==1 && extent-offset>=6 && u32(p+section+offset)==2) codepage=u16(p+section+offset+4);
  }
  if(!title || extent-title<8) return NULL;
  type=u32(p+section+title);n=u32(p+section+title+4);p+=section+title+8;extent-=title+8;
  if(type==31 || (type==30 && codepage==1200)) {
    if(type==30) n/=2;
    if(n>extent/2 || n>65536) return NULL;
    for(i=0;i<n;i++) {
      uint32_t cp=u16(p+2*i);
      if(!cp) break;
      if(cp>=0xd800 && cp<=0xdbff) {
        unsigned low;
        if(i+1>=n || (low=u16(p+2*(i+1)))<0xdc00 || low>0xdfff) goto invalid;
        cp=0x10000+((cp-0xd800)<<10)+(low-0xdc00);i++;
      } else if(cp>=0xdc00 && cp<=0xdfff) goto invalid;
      if(!exr_codepoint(&text,cp)) goto invalid;
    }
  } else if(type==30 && (codepage==1252 || codepage==65001)) {
    static const uint16_t cp1252[32]={0x20ac,0x81,0x201a,0x192,0x201e,0x2026,0x2020,0x2021,
      0x2c6,0x2030,0x160,0x2039,0x152,0x8d,0x17d,0x8f,0x90,0x2018,0x2019,0x201c,
      0x201d,0x2022,0x2013,0x2014,0x2dc,0x2122,0x161,0x203a,0x153,0x9d,0x17e,0x178};
    if(n>extent || n>65536) return NULL;
    for(i=0;i<n && p[i];i++) {
      if(codepage==65001) { if(!exr_append(&text,p+i,1)) goto invalid; }
      else if(!exr_codepoint(&text,p[i]>=128 && p[i]<160 ? cp1252[p[i]-128] : p[i])) goto invalid;
    }
    if(codepage==65001) {
      size_t at=0;uint32_t cp;
      while(at<text.size) if(!exr_next(text.data,text.size,&at,&cp)) goto invalid;
    }
  }
  if(text.size>65536) goto invalid;
  return text.data;
invalid:
  free(text.data);return NULL;
}
static exr_status draw(void *context,size_t page,const double matrix[6],const exr_draw_sink *sink,const exr_control *control,exr_error *e) {
  (void)context;(void)page;(void)matrix;(void)sink;
  return exr_control_cancel(control,e);
}
exr_status exr_ppt_open_memory(const void *data,size_t size,const exr_fixed_open_options *options,exr_fixed_document **out,exr_error *e) {
  exr_ppt_streams streams={0};exr_ppt_info info;exr_fixed_input input={0};
  exr_fixed_page *pages=NULL;char *title=NULL;size_t i;exr_status s;
  *out=NULL;
  s=exr_control_cancel(&options->control,e);if(s!=EXR_OK) return s;
  s=exr_ppt_cfb(data,size,&options->control,&streams,e);
  if(s==EXR_OK) s=exr_ppt_records(streams.document,streams.document_size,&options->control,&info,e);
  if(s!=EXR_OK) goto done;
  title=summary_title(streams.summary,streams.summary_size);
  if(info.pages) {
    pages=calloc(info.pages,sizeof(*pages));
    if(!pages) { s=exr_fail(e,EXR_MEMORY,"PPT page directory allocation failed");goto done; }
  }
  for(i=0;i<info.pages;i++) {
    pages[i].geometry.bounds[2]=info.width;pages[i].geometry.bounds[3]=info.height;
    pages[i].geometry.unit_scale=1;
  }
  input.struct_size=sizeof(input);input.title=title;input.pages=pages;input.page_count=info.pages;input.draw=draw;
  s=exr_control_poll(&options->control,EXR_STAGE_READ,info.pages,info.pages,e);
  if(s==EXR_OK) s=exr_fixed_create(&input,out,e);
  if(s==EXR_OK && info.mismatch) exr_fail(e,EXR_OK,"PPT warning: SlidePersistAtom count %zu differs from Slide container count %zu; using SlidePersistAtom",info.pages,info.slide_containers);
done:
  free(title);free(pages);exr_ppt_streams_free(&streams);return s;
}
exr_status exr_ppt_open_file(const char *path,const exr_fixed_open_options *options,exr_fixed_document **out,exr_error *e) {
  exr_mapping mapping={0};exr_status s=exr_map_file(path,&mapping,e);
  if(s==EXR_LIMIT) {
    exr_source source={0};
    /* Mapping rejects empty files as EXR_LIMIT; a PPT without a signature is
       a format error, just as it is through the memory entry point. */
    if(exr_file_source_limit(path,SIZE_MAX,&source,NULL)==EXR_OK) {
      int empty=!source.size;source.release(source.context);
      if(empty) return exr_ppt_open_memory(NULL,0,options,out,e);
    }
  }
  if(s!=EXR_OK) return s;
  s=exr_ppt_open_memory(mapping.address,mapping.size,options,out,e);
  exr_unmap(&mapping);return s;
}
