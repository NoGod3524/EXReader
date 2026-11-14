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
    /* Drawing records have their own recoverable bounds/depth checks. */
    if(container && type!=0x040b && type!=0x040c) {
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

/* MS-PPT DrawingContainer=040C; OfficeArt Spgr/Sp/FSPGR/FSP/FOPT are
   F003/F004/F009/F00A/F00B. ClientAnchor F010 uses PPT master units;
   ChildAnchor F00F and FSPGR use the group's local (normally EMU) space. */
typedef struct { size_t payload,end; unsigned type,ver,instance; } art_record;
typedef struct { double sx,sy,tx,ty; } transform;
typedef struct {
  const unsigned char *data;
  const exr_control *control;
  exr_ppt_drawing *drawing;
  size_t shapes,records;
  int patriarch;
} drawing_reader;
typedef struct {
  unsigned type,flags,fill_type,fill_flags,line_flags,rotation;
  uint32_t fill,line;
  double width,anchor[4],children[4];
  int has_anchor,has_children,has_fsp,valid;
} art_shape;
static double i32(const unsigned char *p) {
  uint32_t n=u32(p);
  return n<=INT32_MAX ? (double)n : (double)n-4294967296.0;
}
static double i16(const unsigned char *p) {
  unsigned n=u16(p);
  return n<=INT16_MAX ? (double)n : (double)n-65536.0;
}
static int art_next(drawing_reader *r,size_t *at,size_t end,art_record *a) {
  size_t length;
  if(*at==end) return 0;
  if(end-*at<8 || (length=u32(r->data+*at+4))>end-*at-8) {
    r->drawing->malformed++;*at=end;return 0;
  }
  a->ver=u16(r->data+*at)&15;a->instance=u16(r->data+*at)>>4;
  a->type=u16(r->data+*at+2);a->payload=*at+8;a->end=a->payload+length;
  *at=a->end;return 1;
}
/* Complex lengths are validated even for properties M2 does not consume.
   Only literal RGB COLORREFs are painted; indexed colours need M3 styles. */
static unsigned merge_flags(unsigned previous,uint32_t value) {
  unsigned used=value>>16;
  return (previous&~used)|(value&used)|(value&0xffff0000u);
}
static int properties(drawing_reader *r,const art_record *a,art_shape *s) {
  size_t at=a->payload,complex,i;
  if(a->instance>(a->end-at)/6) return 0;
  complex=at+6*a->instance;
  for(i=0;i<a->instance;i++,at+=6) {
    unsigned op=u16(r->data+at),pid=op&0x3fff;uint32_t value=u32(r->data+at+2);
    if(op&0x8000) {
      if(value>a->end-complex) return 0;
      complex+=value;continue;
    }
    switch(pid) {
      case 0x0004:s->rotation=value;break;
      case 0x0180:s->fill_type=value;break;
      case 0x0181:s->fill=value;break;
      case 0x01bf:s->fill_flags=merge_flags(s->fill_flags,value);break;
      case 0x01c0:s->line=value;break;
      case 0x01cb:
        if(value>0x0132f540) return 0;
        s->width=value/12700.0;break;
      case 0x01ff:s->line_flags=merge_flags(s->line_flags,value);break;
      default:break;
    }
  }
  return complex==a->end;
}
static exr_status read_shape(drawing_reader *r,const art_record *container,art_shape *s,exr_error *e) {
  size_t at=container->payload;art_record a;
  memset(s,0,sizeof(*s));s->fill=0xffffff;s->width=.75;s->valid=1;
  while(at<container->end) {
    size_t n;const unsigned char *p;
    if((++r->records&255)==1) {
      exr_status status=exr_control_cancel(r->control,e);if(status!=EXR_OK) return status;
    }
    if(!art_next(r,&at,container->end,&a)) { s->valid=0;break; }
    n=a.end-a.payload;p=r->data+a.payload;
    if(a.type==0xf00a) {
      if(n!=8) goto malformed;
      s->type=a.instance;s->flags=u32(p+4);s->has_fsp=1;
    } else if(a.type==0xf009) {
      size_t i;
      if(n!=16) goto malformed;
      for(i=0;i<4;i++) s->children[i]=i32(p+4*i);
      s->has_children=1;
    } else if(a.type==0xf00f || a.type==0xf010) {
      double v[4];size_t i;
      if(n!=16 && !(a.type==0xf010 && n==8)) goto malformed;
      for(i=0;i<4;i++) v[i]=n==8 ? i16(p+2*i) : i32(p+4*i);
      /* PPT ClientAnchor: top,left,right,bottom. ChildAnchor: x0,y0,x1,y1. */
      s->anchor[0]=v[a.type==0xf010 ? 1 : 0];
      s->anchor[1]=v[a.type==0xf010 ? 0 : 1];
      s->anchor[2]=v[2];s->anchor[3]=v[3];s->has_anchor=1;
    } else if(a.type==0xf00b || a.type==0xf121 || a.type==0xf122) {
      if(!properties(r,&a,s)) goto malformed;
    }
  }
  return EXR_OK;
malformed:
  r->drawing->malformed++;s->valid=0;return EXR_OK;
}
static int colorref(uint32_t value,uint32_t *out) {
  if((value&0xff000000u)==0xff000000u || (value&0xf9000000u)) return 0;
  *out=((value&255)<<24)|((value&0xff00)<<8)|((value>>16&255)<<8)|255;
  return 1;
}
static exr_status emit_shape(drawing_reader *r,const art_shape *s,const transform *t,exr_error *e) {
  exr_ppt_drawing *d=r->drawing;exr_ppt_shape shape={0};size_t i;int line=s->type==20 || s->type==32;
  if(!s->valid || (s->flags&8)) return EXR_OK;
  if(!s->has_anchor) { d->missing_anchor++;return EXR_OK; }
  if(!s->has_fsp || (s->type!=1 && s->type!=3 && !line) || s->rotation) { d->unsupported++;return EXR_OK; }
  shape.type=s->type;shape.style=exr_draw_style_defaults();shape.style.flags=0;
  if(!line && !((s->fill_flags&0x100000) && !(s->fill_flags&0x10))) {
    /* An explicitly unfilled shape is omitted, including its outline (M2). */
    if(!s->fill_type && colorref(s->fill,&shape.style.fill)) shape.style.flags|=EXR_DRAW_FILL;
    else d->unsupported++;
  } else if(!line) return EXR_OK;
  if(!((s->line_flags&0x80000) && !(s->line_flags&8))) {
    if(colorref(s->line,&shape.style.stroke)) shape.style.flags|=EXR_DRAW_STROKE;
    else d->unsupported++;
  }
  if(!shape.style.flags) return EXR_OK;
  for(i=0;i<4;i++) {
    shape.bounds[i]=s->anchor[i]*(i&1 ? t->sy : t->sx)+(i&1 ? t->ty : t->tx);
    if(!isfinite(shape.bounds[i]) || fabs(shape.bounds[i])>1e7) { d->malformed++;return EXR_OK; }
  }
  if(line) {
    if(s->flags&0x40) { double v=shape.bounds[0];shape.bounds[0]=shape.bounds[2];shape.bounds[2]=v; }
    if(s->flags&0x80) { double v=shape.bounds[1];shape.bounds[1]=shape.bounds[3];shape.bounds[3]=v; }
  }
  /* Line widths are EMUs independently of anchor/group coordinate systems. */
  shape.style.line.width=s->width;
  /* exr_grow doubles capacity, so reserve room for its next power of two. */
  if(d->count>=EXR_MAX_INPUT/(2*sizeof(*d->shapes)))
    return exr_fail(e,EXR_LIMIT,"PPT shapes exceed 128 MiB budget");
  if(!exr_grow((void **)&d->shapes,&d->capacity,d->count+1,sizeof(*d->shapes)))
    return exr_fail(e,EXR_MEMORY,"PPT shape allocation failed");
  d->shapes[d->count++]=shape;return EXR_OK;
}
static exr_status art_walk(drawing_reader *r,size_t at,size_t end,unsigned depth,int in_group,transform t,exr_error *e) {
  art_record a;int group_header=1;
  if(depth>16) { r->drawing->depth++;return EXR_OK; }
  while(art_next(r,&at,end,&a)) {
    exr_status status;
    if((++r->records&255)==1) { status=exr_control_cancel(r->control,e);if(status!=EXR_OK) return status; }
    if(a.type==0xf004 && a.ver==15) {
      art_shape s;
      status=read_shape(r,&a,&s,e);if(status!=EXR_OK) return status;
      if(group_header && in_group && s.has_fsp && (s.flags&5)==5 && !r->patriarch) r->patriarch=1;
      else if(++r->shapes>5000)
        return exr_fail(e,EXR_LIMIT,"PPT slide exceeds 5000 shapes");
      if(group_header && in_group) {
        group_header=0;
        if(!s.valid || (s.flags&8)) return EXR_OK;
        if(!s.has_fsp || !(s.flags&1)) { r->drawing->malformed++;return EXR_OK; }
        if(s.rotation) { r->drawing->unsupported++;return EXR_OK; }
        /* The root patriarch has no anchor and introduces no transform. */
        if(!s.has_anchor && (s.flags&4)) continue;
        if(!s.has_anchor) { r->drawing->missing_anchor++;return EXR_OK; }
        if(!s.has_children) { r->drawing->malformed++;return EXR_OK; }
        {
          double dx=s.children[2]-s.children[0],dy=s.children[3]-s.children[1];
          double sx=dx ? (s.anchor[2]-s.anchor[0])/dx : 1;
          double sy=dy ? (s.anchor[3]-s.anchor[1])/dy : 1;
          if(!dx || !dy) r->drawing->zero_extent++;
          if(s.flags&0x40) sx=-sx;
          if(s.flags&0x80) sy=-sy;
          t.tx+=t.sx*((s.flags&0x40 ? s.anchor[2] : s.anchor[0])-s.children[0]*sx);
          t.ty+=t.sy*((s.flags&0x80 ? s.anchor[3] : s.anchor[1])-s.children[1]*sy);
          t.sx*=sx;t.sy*=sy;
        }
      } else {
        group_header=0;
        status=emit_shape(r,&s,&t,e);if(status!=EXR_OK) return status;
      }
    } else if(a.ver==15 && (a.type==0xf002 || a.type==0xf003)) {
      status=art_walk(r,a.payload,a.end,depth+1,a.type==0xf003,t,e);if(status!=EXR_OK) return status;
    } else if(a.ver==15 && a.type>=0xf000 && a.type<=0xf121) {
      /* Unknown OfficeArt containers retain bounds and depth protection. */
      status=art_walk(r,a.payload,a.end,depth+1,0,t,e);if(status!=EXR_OK) return status;
    }
  }
  return EXR_OK;
}
void exr_ppt_drawing_free(exr_ppt_drawing *d) {
  free(d->shapes);free(d->slides);memset(d,0,sizeof(*d));
}
exr_status exr_ppt_read_drawing(const void *data,size_t size,const exr_ppt_info *info,const exr_control *control,exr_ppt_drawing *out,exr_error *e) {
  drawing_reader r={0};art_record a;size_t at=0,doc=0,doc_end=0,n=0,i;
  size_t *physical=NULL;uint32_t *refs=NULL,*persist=NULL;exr_status status=EXR_OK;
  memset(out,0,sizeof(*out));r.data=data;r.control=control;r.drawing=out;out->pages=info->pages;
  if(!out->pages) return EXR_OK;
  out->slides=calloc(out->pages,sizeof(*out->slides));physical=calloc(out->pages,sizeof(*physical));refs=calloc(out->pages,sizeof(*refs));
  if(!out->slides || !physical || !refs) { status=exr_fail(e,EXR_MEMORY,"PPT drawing directory allocation failed");goto done; }
  /* Scan the already validated top-level record stream. Persist directories
     overwrite older mappings, and the final Document supplies slide order. */
  while(art_next(&r,&at,size,&a)) {
    status=exr_control_cancel(control,e);if(status!=EXR_OK) goto done;
    if(a.type==RT_DOCUMENT) {
      doc=a.payload;doc_end=a.end;n=0;memset(physical,0,out->pages*sizeof(*physical));
    }
    else if(a.type==RT_SLIDE && n<out->pages) physical[n++]=a.payload-8;
    else if(a.type==0x1772 || a.type==0x1771) {
      size_t entry=a.payload;
      if(!persist) persist=calloc(1u<<20,sizeof(*persist));
      if(!persist) { status=exr_fail(e,EXR_MEMORY,"PPT persist directory allocation failed");goto done; }
      while(entry<a.end) {
        uint32_t packed,start,count,j;
        if(a.end-entry<4) { out->malformed++;break; }
        packed=u32(r.data+entry);entry+=4;start=packed&0xfffff;count=packed>>20;
        if(!count || count>(a.end-entry)/4 || count>(1u<<20)-start) { out->malformed++;break; }
        for(j=0;j<count;j++,entry+=4) persist[start+j]=u32(r.data+entry);
      }
    }
  }
  at=doc;n=0;
  while(art_next(&r,&at,doc_end,&a)) if(a.type==RT_SLIDE_LIST && a.instance==0) {
    size_t entry=a.payload;art_record ref;
    while(art_next(&r,&entry,a.end,&ref)) if(ref.type==RT_SLIDE_PERSIST && ref.end-ref.payload>=20 && n<out->pages)
      refs[n++]=u32(r.data+ref.payload);
  }
  for(i=0;i<out->pages;i++) {
    size_t offset=physical[i],cursor;art_record slide,child;
    out->slides[i].first=out->count;r.shapes=0;r.patriarch=0;
    if(persist && refs[i] && refs[i]<(1u<<20)) {
      uint32_t mapped=persist[refs[i]];
      if(mapped && mapped<size && size-mapped>=8 && u16(r.data+mapped+2)==RT_SLIDE) offset=mapped;
    }
    if(!offset || offset>=size) continue;
    cursor=offset;
    if(!art_next(&r,&cursor,size,&slide) || slide.type!=RT_SLIDE) continue;
    cursor=slide.payload;
    while(art_next(&r,&cursor,slide.end,&child)) if(child.type==0x040c) {
      transform t={.125,.125,0,0};
      status=art_walk(&r,child.payload,child.end,0,0,t,e);if(status!=EXR_OK) goto done;
    }
    out->slides[i].count=out->count-out->slides[i].first;
  }
done:
  free(physical);free(refs);free(persist);
  if(status!=EXR_OK) exr_ppt_drawing_free(out);
  return status;
}
