/* SPDX-License-Identifier: MIT */
#include "ppt_internal.h"
#include "graphics_internal.h"

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
  const exr_ppt_streams *streams;
  size_t shapes,records;
  int patriarch;
  uint32_t colors[8];
  unsigned color_mask;
} drawing_reader;
typedef struct {
  unsigned type,flags,fill_type,fill_flags,line_flags,rotation;
  uint32_t fill,back,line,pib,fill_blip,stops[2];
  double width,anchor[4],children[4];
  int has_anchor,has_children,has_fsp,valid;
  int has_fill_blip,has_fill,has_back,has_stops,bad_stops;
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
/* Keep every BSE slot, including unsupported records, so pib stays one-based. */
static exr_status read_bstore(drawing_reader *r,const art_record *store,exr_error *e) {
  size_t at=store->payload;art_record a;exr_ppt_drawing *d=r->drawing;
  while(art_next(r,&at,store->end,&a)) {
    const unsigned char *bytes=r->data;size_t offset,end=a.end,skip;unsigned instance;exr_ppt_blip *b;
    exr_status status=exr_control_cancel(r->control,e);if(status!=EXR_OK) return status;
    if(a.type!=0xf007) { d->malformed++;continue; }
    if(d->blip_count>=65535) return exr_fail(e,EXR_LIMIT,"PPT exceeds 65535 blips");
    if(!exr_grow((void **)&d->blips,&d->blip_capacity,d->blip_count+1,sizeof(*d->blips)))
      return exr_fail(e,EXR_MEMORY,"PPT blip directory allocation failed");
    b=&d->blips[d->blip_count++];memset(b,0,sizeof(*b));b->state=2;
    if(a.end-a.payload<36) { d->malformed++;continue; }
    offset=a.payload+36+bytes[a.payload+33];
    if(offset>end) { d->malformed++;continue; }
    if(offset==end) {
      offset=u32(bytes+a.payload+28);bytes=r->streams->pictures;end=r->streams->pictures_size;
      if(!bytes || offset>end) continue;
    }
    if(end-offset<8 || u32(bytes+offset+4)>end-offset-8) { d->malformed++;continue; }
    b->type=u16(bytes+offset+2);instance=u16(bytes+offset)>>4;
    if(b->type==0xf01d || b->type==0xf02a) {
      if(instance!=0x46a && instance!=0x46b && instance!=0x6e2 && instance!=0x6e3) continue;
      skip=(instance==0x46b || instance==0x6e3) ? 33 : 17;
    } else if(b->type==0xf01e || b->type==0xf02b) {
      if(instance!=0x6e0 && instance!=0x6e1) continue;
      skip=instance==0x6e1 ? 33 : 17;
    } else { b->state=3;continue; }
    b->size=u32(bytes+offset+4);
    if(b->size<skip) continue;
    b->encoded=bytes+offset+8+skip;b->size-=skip;b->state=0;
  }
  return EXR_OK;
}
static exr_status read_resources(drawing_reader *r,size_t at,size_t end,unsigned depth,exr_error *e) {
  art_record a;
  if(depth>16) { r->drawing->depth++;return EXR_OK; }
  while(art_next(r,&at,end,&a)) {
    exr_status status=exr_control_cancel(r->control,e);if(status!=EXR_OK) return status;
    if(a.type==0xf001 && a.ver==15) status=read_bstore(r,&a,e);
    else if(a.ver==15 && (a.type==0x040b || a.type==0xf000))
      status=read_resources(r,a.payload,a.end,depth+1,e);
    if(status!=EXR_OK) return status;
  }
  return EXR_OK;
}
/* MS-PPT SlideSchemeColorSchemeAtom is 8 COLORREFs, recInstance=1.
   Read actual slots: newer PowerPoint may map modern accents differently. */
static void read_scheme(drawing_reader *r,const art_record *container) {
  size_t at=container->payload,i;art_record a;
  while(art_next(r,&at,container->end,&a)) if(a.type==0x07f0 && a.instance==1) {
    if(a.end-a.payload!=32) { r->drawing->malformed++;continue; }
    for(i=0;i<8;i++) r->colors[i]=u32(r->data+a.payload+4*i);
    r->color_mask=255;
  }
}
/* Complex lengths are validated even for properties we do not consume. */
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
      if(pid==0x0197) {
        const unsigned char *p=r->data+complex;unsigned count=value>=6 ? u16(p) : 0;
        size_t j;uint32_t low=UINT32_MAX,high=0;
        s->has_stops=0;s->bad_stops=1;
        if(count>=2 && u16(p+2)>=count && u16(p+4)==8 && count<=(value-6)/8 && value==6+8*count) {
          for(j=0;j<count;j++) {
            uint32_t pos=u32(p+10+8*j),color=u32(p+6+8*j);
            if(pos>65536) break;
            if(pos<low) { low=pos;s->stops[0]=color; }
            if(pos>=high) { high=pos;s->stops[1]=color; }
          }
          if(j==count && low<high) { s->has_stops=1;s->bad_stops=0; }
        }
      }
      complex+=value;continue;
    }
    switch(pid) {
      case 0x0004:s->rotation=value;break;
      case 0x0104:s->pib=value;break;
      case 0x0186:s->fill_blip=value;s->has_fill_blip=1;break;
      case 0x0180:s->fill_type=value;break;
      case 0x0181:s->fill=value;s->has_fill=1;break;
      case 0x0183:s->back=value;s->has_back=1;break;
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
static int colorref(drawing_reader *r,uint32_t value,uint32_t *out) {
  if((value&0xffffff00u)==0x08000000u) {
    unsigned index=value&255;
    if(index>=8 || !(r->color_mask&(1u<<index))) { r->drawing->scheme++;return 0; }
    value=r->colors[index];
  }
  if((value&0xff000000u)==0xff000000u || (value&0xf9000000u)) return 0;
  *out=((value&255)<<24)|((value&0xff00)<<8)|((value>>16&255)<<8)|255;
  return 1;
}
static exr_status image_fill(drawing_reader *r,uint32_t pib,exr_ppt_shape *shape,int *skip,exr_error *e) {
  exr_ppt_drawing *d=r->drawing;exr_ppt_blip *b;exr_status status;uint32_t w,h;
  shape->style.fill=0xccccccff;shape->style.flags|=EXR_DRAW_FILL;
  if(!pib || pib>d->blip_count) { d->bad_pib++;return EXR_OK; }
  b=&d->blips[pib-1];
  if(b->state==3) { d->unknown_blip++;*skip=1;return EXR_OK; }
  if(!b->state) {
    b->state=2;
    status=exr_image_dimensions(b->encoded,b->size,&w,&h,NULL);
    if(status==EXR_OK && (size_t)w*h<=((size_t)128*1024*1024-d->image_bytes)/4) {
      status=exr_image_decode_control(b->encoded,b->size,r->control,&b->bitmap,e);
      if(status==EXR_CANCELLED) return status;
      if(status==EXR_OK) { b->state=1;d->image_bytes+=b->bitmap.stride*b->bitmap.height; }
      else exr_bitmap_free(&b->bitmap);
    }
    status=exr_control_cancel(r->control,e);if(status!=EXR_OK) return status;
  }
  if(b->state==1) { shape->blip=pib;shape->style.flags&=~EXR_DRAW_FILL; }
  else d->image_decode++;
  return EXR_OK;
}
static exr_status emit_shape(drawing_reader *r,const art_shape *s,const transform *t,exr_error *e) {
  exr_ppt_drawing *d=r->drawing;exr_ppt_shape shape={0};size_t i;int line=s->type==20 || s->type==32;
  if(!s->valid || (s->flags&8)) return EXR_OK;
  if(!s->has_anchor) { d->missing_anchor++;return EXR_OK; }
  if(!s->has_fsp || (s->type!=1 && s->type!=3 && s->type!=75 && !line) || s->rotation) { d->unsupported++;return EXR_OK; }
  shape.type=s->type;shape.style=exr_draw_style_defaults();shape.style.flags=0;
  if(!line && (s->type==75 || (s->fill_type==3 && !((s->fill_flags&0x100000) && !(s->fill_flags&0x10))))) {
    uint32_t pib=s->type==75 || !s->has_fill_blip ? s->pib : s->fill_blip;
    int skip=0;exr_status status=image_fill(r,pib,&shape,&skip,e);
    if(status!=EXR_OK || skip) return status;
  } else if(!line && !((s->fill_flags&0x100000) && !(s->fill_flags&0x10))) {
    /* An explicitly unfilled shape is omitted, including its outline (M2). */
    if(!s->fill_type && colorref(r,s->fill,&shape.style.fill)) shape.style.flags|=EXR_DRAW_FILL;
    else if(s->fill_type>=4 && s->fill_type<=8) {
      int first=colorref(r,s->has_stops ? s->stops[0] : s->fill,&shape.style.fill);
      if(first) shape.style.flags|=EXR_DRAW_FILL;
      if(first && !s->bad_stops && (s->has_stops || (s->has_fill && s->has_back)) &&
         colorref(r,s->has_stops ? s->stops[1] : s->back,&shape.gradient[1])) {
        shape.gradient[0]=shape.style.fill;shape.has_gradient=1;d->gradient_horizontal++;
      } else { d->gradient_missing++;if(!first) { shape.style.fill=0xccccccff;shape.style.flags|=EXR_DRAW_FILL; } }
    }
    else d->unsupported++;
  } else if(!line) return EXR_OK;
  if(!((s->line_flags&0x80000) && !(s->line_flags&8))) {
    if(colorref(r,s->line,&shape.style.stroke)) shape.style.flags|=EXR_DRAW_STROKE;
    else d->unsupported++;
  }
  if(!shape.style.flags && !shape.blip) return EXR_OK;
  for(i=0;i<4;i++) {
    shape.bounds[i]=s->anchor[i]*(i&1 ? t->sy : t->sx)+(i&1 ? t->ty : t->tx);
    if(!isfinite(shape.bounds[i]) || fabs(shape.bounds[i])>1e7) { d->malformed++;return EXR_OK; }
  }
  if(line || shape.blip || shape.has_gradient) {
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
  size_t i;for(i=0;i<d->blip_count;i++) exr_bitmap_free(&d->blips[i].bitmap);
  free(d->blips);
  free(d->shapes);free(d->slides);memset(d,0,sizeof(*d));
}
exr_status exr_ppt_read_drawing(const exr_ppt_streams *streams,const exr_ppt_info *info,const exr_control *control,exr_ppt_drawing *out,exr_error *e) {
  size_t size=streams->document_size;
  drawing_reader r={0};art_record a;size_t at=0,doc=0,doc_end=0,master=0,n=0,i;
  size_t *physical=NULL;uint32_t *refs=NULL,*persist=NULL;exr_status status=EXR_OK;
  memset(out,0,sizeof(*out));r.data=streams->document;r.streams=streams;r.control=control;r.drawing=out;out->pages=info->pages;
  if(!out->pages) return EXR_OK;
  out->slides=calloc(out->pages,sizeof(*out->slides));physical=calloc(out->pages*2,sizeof(*physical));refs=calloc(out->pages,sizeof(*refs));
  if(!out->slides || !physical || !refs) { status=exr_fail(e,EXR_MEMORY,"PPT drawing directory allocation failed");goto done; }
  /* Scan the already validated top-level record stream. Persist directories
     overwrite older mappings, and the final Document supplies slide order. */
  while(art_next(&r,&at,size,&a)) {
    status=exr_control_cancel(control,e);if(status!=EXR_OK) goto done;
    if(a.type==RT_DOCUMENT) {
      doc=a.payload;doc_end=a.end;n=0;master=0;memset(physical,0,out->pages*2*sizeof(*physical));
    }
    else if(a.type==RT_SLIDE && n<out->pages) { physical[n]=a.payload-8;physical[out->pages+n++]=master; }
    else if(a.type==0x03f8) master=a.payload-8;
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
  status=read_resources(&r,doc,doc_end,0,e);if(status!=EXR_OK) goto done;
  at=doc;n=0;
  while(art_next(&r,&at,doc_end,&a)) if(a.type==RT_SLIDE_LIST && a.instance==0) {
    size_t entry=a.payload;art_record ref;
    while(art_next(&r,&entry,a.end,&ref)) if(ref.type==RT_SLIDE_PERSIST && ref.end-ref.payload>=20 && n<out->pages)
      refs[n++]=u32(r.data+ref.payload);
  }
  for(i=0;i<out->pages;i++) {
    size_t offset=physical[i],cursor,master_offset=physical[out->pages+i];art_record slide,child;unsigned flags=0;
    uint32_t master_id=0;
    out->slides[i].first=out->count;r.shapes=0;r.patriarch=0;
    if(persist && refs[i] && refs[i]<(1u<<20)) {
      uint32_t mapped=persist[refs[i]];
      if(mapped && mapped<size && size-mapped>=8 && u16(r.data+mapped+2)==RT_SLIDE) offset=mapped;
    }
    if(!offset || offset>=size) continue;
    cursor=offset;
    if(!art_next(&r,&cursor,size,&slide) || slide.type!=RT_SLIDE) continue;
    cursor=slide.payload;
    while(art_next(&r,&cursor,slide.end,&child)) if(child.type==RT_SLIDE_ATOM && child.end-child.payload>=24) {
      master_id=u32(r.data+child.payload+12);flags=u16(r.data+child.payload+20);
    }
    /* MasterPersistAtom uses the same layout as SlidePersistAtom; the list's
       instance=1 selects masters, and masterId matches SlideAtom.masterIdRef. */
    cursor=doc;
    while(master_id && persist && art_next(&r,&cursor,doc_end,&child)) if(child.type==RT_SLIDE_LIST && child.instance==1) {
      size_t entry=child.payload;art_record ref;
      while(art_next(&r,&entry,child.end,&ref)) if(ref.type==RT_SLIDE_PERSIST && ref.end-ref.payload>=20 && u32(r.data+ref.payload+12)==master_id) {
        uint32_t id=u32(r.data+ref.payload);
        if(id<(1u<<20) && persist[id]) master_offset=persist[id];
      }
    }
    r.color_mask=0;
    if(master_offset && master_offset<size) {
      art_record m;size_t entry=master_offset;
      if(art_next(&r,&entry,size,&m) && m.type==0x03f8) read_scheme(&r,&m);
    }
    if(!(flags&2)) read_scheme(&r,&slide);
    cursor=slide.payload;
    while(art_next(&r,&cursor,slide.end,&child)) if(child.type==0x040c) {
      transform t={.125,.125,0,0};
      status=art_walk(&r,child.payload,child.end,0,0,t,e);if(status!=EXR_OK) goto done;
    }
    out->slides[i].count=out->count-out->slides[i].first;
  }
done:
  for(i=0;i<out->blip_count;i++) out->blips[i].encoded=NULL;
  free(physical);free(refs);free(persist);
  if(status!=EXR_OK) exr_ppt_drawing_free(out);
  return status;
}
