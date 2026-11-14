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
  exr_ppt_text_style style;
  uint32_t cf_mask,color;
  unsigned font,ea,bullet_flags,bullet_font,bullet_size;
  uint32_t bullet_color;
} text_props;
typedef struct {
  const unsigned char *data;
  const exr_control *control;
  exr_ppt_drawing *drawing;
  const exr_ppt_streams *streams;
  size_t shapes,records;
  int patriarch;
  uint32_t colors[8];
  unsigned color_mask;
  text_props environment[9][5],master_text[9][5];
  size_t outline_begin,outline_end;
  int in_table;
} drawing_reader;
typedef struct {
  unsigned type,flags,fill_type,fill_flags,line_flags,rotation;
  uint32_t fill,back,line,pib,fill_blip,stops[2];
  double width,anchor[4],children[4];
  int has_anchor,has_children,has_fsp,valid;
  int has_fill_blip,has_fill,has_back,has_stops,bad_stops;
  art_record textbox;
  double inset[4];
  int wrap,anchor_text,placeholder;
  unsigned table,table_rows;
  int table_bad;
  art_record table_heights;
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
      if(value>a->end-complex) {
        if(pid!=0x03a0) return 0;
        s->table_bad=1;value=(uint32_t)(a->end-complex);
      }
      if(pid==0x03a0) {
        const unsigned char *p=r->data+complex;
        s->table_heights=(art_record){complex,complex+value,0,0,0};
        s->table_rows=value>=2 ? u16(p) : 0;
        if(value<6 || u16(p+2)<s->table_rows || u16(p+4)!=4 || value!=6+4*s->table_rows)
          s->table_bad=1;
      } else if(pid==0x0197) {
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
      case 0x0081:case 0x0082:case 0x0083:case 0x0084:
        if(value>0x0132f540) return 0;
        s->inset[pid==0x81 ? 3 : pid==0x82 ? 0 : pid==0x83 ? 1 : 2]=value/12700.0;break;
      case 0x0085:s->wrap=value!=2;break;
      case 0x0087:s->anchor_text=value==1 || value==4 ? 1 : value==2 || value==5 ? 2 : 0;break;
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
      case 0x039f:s->table=value&1;break;
      default:break;
    }
  }
  return complex==a->end;
}
static exr_status read_shape(drawing_reader *r,const art_record *container,art_shape *s,exr_error *e) {
  size_t at=container->payload;art_record a;
  memset(s,0,sizeof(*s));s->fill=0xffffff;s->width=.75;s->valid=1;
  s->inset[0]=s->inset[2]=3.6;s->inset[1]=s->inset[3]=7.2;s->wrap=1;
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
    } else if(a.type==0xf00d) s->textbox=a;
    else if(a.type==0xf011) {
      size_t entry=a.payload;art_record client;
      while(art_next(r,&entry,a.end,&client)) if(client.type==0x0bc3) s->placeholder=1;
    } else if(a.type==0xf00b || a.type==0xf121 || a.type==0xf122) {
      if(!properties(r,&a,s)) {
        if(s->table) s->table_bad=1;
        else goto malformed;
      }
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
/* MS-PPT 2.9: counts are UTF-16 units including an implicit final CR.
   StyleTextPropAtom has separate PF and CF arrays, without block lengths. */
static int text_u16(drawing_reader *r,size_t *at,size_t end,unsigned *out) {
  if(*at>end || end-*at<2) return 0;
  *out=u16(r->data+*at);*at+=2;return 1;
}
static int text_u32(drawing_reader *r,size_t *at,size_t end,uint32_t *out) {
  if(*at>end || end-*at<4) return 0;
  *out=u32(r->data+*at);*at+=4;return 1;
}
static double text_signed(unsigned n) { return n<32768 ? (double)n : (double)n-65536; }
static int text_pf(drawing_reader *r,size_t *at,size_t end,text_props *p) {
  uint32_t mask,color;unsigned n,flags,i;
  if(!text_u32(r,at,end,&mask)) return 0;
  if(mask&15) {
    if(!text_u16(r,at,end,&flags)) return 0;
    p->bullet_flags=(p->bullet_flags&~(mask&15))|(flags&mask&15);
  }
  if(mask&0x80) { if(!text_u16(r,at,end,&n)) return 0;p->style.bullet=n; }
  if(mask&0x10) { if(!text_u16(r,at,end,&n)) return 0;p->bullet_font=n; }
  if(mask&0x40) { if(!text_u16(r,at,end,&n)) return 0;p->bullet_size=n; }
  if(mask&0x20) { if(!text_u32(r,at,end,&color)) return 0;p->bullet_color=color; }
  if(mask&0x800) {
    if(!text_u16(r,at,end,&n)) return 0;
    p->style.align=n==1 ? 1 : n==2 ? 2 : n==3 ? 3 : 0;
  }
  for(i=0;i<3;i++) if(mask&(0x1000u<<i)) {
    double v;int pct;
    if(!text_u16(r,at,end,&n)) return 0;
    v=text_signed(n);pct=v>=0;v=pct ? v/100 : -v/8;
    if(!i) { p->style.line=v;p->style.line_pct=pct; }
    else if(i==1) { p->style.before=v;p->style.before_pct=pct; }
    else { p->style.after=v;p->style.after_pct=pct; }
  }
  if(mask&0x100) { if(!text_u16(r,at,end,&n)) return 0;p->style.margin=text_signed(n)/8; }
  if(mask&0x400) { if(!text_u16(r,at,end,&n)) return 0;p->style.indent=text_signed(n)/8; }
  if((mask&0x8000) && !text_u16(r,at,end,&n)) return 0;
  if(mask&0x100000) {
    if(!text_u16(r,at,end,&n) || n>(end-*at)/4) return 0;
    *at+=4*n;
  }
  if((mask&0x10000) && !text_u16(r,at,end,&n)) return 0;
  if((mask&0xe0000) && !text_u16(r,at,end,&n)) return 0;
  if((mask&0x200000) && !text_u16(r,at,end,&n)) return 0;
  return 1;
}
static int text_cf(drawing_reader *r,size_t *at,size_t end,text_props *p) {
  uint32_t mask;unsigned n;
  if(!text_u32(r,at,end,&mask)) return 0;
  p->cf_mask=mask;
  if(mask&0x3eb7) {
    if(!text_u16(r,at,end,&n)) return 0;
    p->style.flags=(p->style.flags&~(mask&7))|(n&mask&7);
  }
  if(mask&0x10000) { if(!text_u16(r,at,end,&n)) return 0;p->font=n; }
  if(mask&0x200000) { if(!text_u16(r,at,end,&n)) return 0;p->ea=n; }
  if(mask&0x400000) { if(!text_u16(r,at,end,&n)) return 0;if(!(mask&0x10000)) p->font=n; }
  if((mask&0x800000) && !text_u16(r,at,end,&n)) return 0;
  if(mask&0x20000) {
    if(!text_u16(r,at,end,&n)) return 0;
    p->style.size=n>0 && n<=4000 ? n : 18;
  }
  if((mask&0x40000) && !text_u32(r,at,end,&p->color)) return 0;
  if((mask&0x80000) && !text_u16(r,at,end,&n)) return 0;
  return 1;
}
static void text_cf_overlay(text_props *p,const text_props *v) {
  uint32_t m=v->cf_mask;
  p->style.flags=(p->style.flags&~(m&7))|(v->style.flags&m&7);
  if(m&0x410000) p->font=v->font;
  if(m&0x200000) p->ea=v->ea;
  if(m&0x20000) p->style.size=v->style.size;
  if(m&0x40000) p->color=v->color;
}
static void text_defaults(text_props styles[9][5]) {
  size_t i,j;
  for(i=0;i<9;i++) for(j=0;j<5;j++) {
    text_props *p=&styles[i][j];memset(p,0,sizeof(*p));
    p->style.size=18;p->style.line=1;p->style.line_pct=1;
    p->style.bullet=0x2022;p->ea=0xffff;p->color=0xfe000000;
    p->bullet_size=100;p->bullet_color=0xfe000000;
  }
}
static void text_master(drawing_reader *r,const art_record *a,text_props styles[9][5]) {
  size_t at=a->payload,i;unsigned count,level;unsigned kind=a->instance;
  if(kind>=9 || !text_u16(r,&at,a->end,&count) || count>5) { r->drawing->text_malformed++;return; }
  for(i=0;i<count;i++) {
    text_props p=styles[kind][i ? i-1 : 0];level=(unsigned)i;
    if((kind>=5 && !text_u16(r,&at,a->end,&level)) || level>=5 ||
       !text_pf(r,&at,a->end,&p) || !text_cf(r,&at,a->end,&p)) { r->drawing->text_malformed++;return; }
    styles[kind][level]=p;
  }
}
static exr_status text_resources(drawing_reader *r,size_t at,size_t end,unsigned depth,exr_error *e) {
  art_record a;exr_ppt_drawing *d=r->drawing;
  if(depth>16) { d->depth++;return EXR_OK; }
  while(art_next(r,&at,end,&a)) {
    if(a.type==0x0fb7) {
      exr_buffer name={0};size_t j;
      if(a.end-a.payload!=68) d->text_malformed++;
      for(j=0;a.end-a.payload==68 && j<32;j++) {
        unsigned cp=u16(r->data+a.payload+2*j);if(!cp) break;
        if(cp>=0xd800 && cp<=0xdfff) { cp=0xfffd;d->text_unicode++; }
        if(!exr_codepoint(&name,cp)) { free(name.data);return exr_fail(e,EXR_MEMORY,"PPT font name allocation failed"); }
      }
      if(d->font_count==1024) { free(name.data);return exr_fail(e,EXR_LIMIT,"PPT exceeds 1024 font entries"); }
      if(!exr_grow((void **)&d->fonts,&d->font_capacity,d->font_count+1,sizeof(*d->fonts))) {
        free(name.data);return exr_fail(e,EXR_MEMORY,"PPT font table allocation failed");
      }
      if(!name.data) name.data=exr_copy("sans-serif",10);
      if(!name.data) return exr_fail(e,EXR_MEMORY,"PPT font name allocation failed");
      d->fonts[d->font_count++]=name.data;
    } else if(a.type==0x0fa3) text_master(r,&a,r->environment);
    else if(a.ver==15 && (a.type==0x03f2 || a.type==0x07d5)) {
      exr_status status=text_resources(r,a.payload,a.end,depth+1,e);if(status!=EXR_OK) return status;
    }
  }
  return EXR_OK;
}
static void text_ruler(drawing_reader *r,const art_record *a,text_props levels[5]) {
  size_t at=a->payload,i;uint32_t mask;unsigned n;
  if(!text_u32(r,&at,a->end,&mask)) goto bad;
  if((mask&2) && !text_u16(r,&at,a->end,&n)) goto bad;
  if((mask&1) && !text_u16(r,&at,a->end,&n)) goto bad;
  if(mask&4) { if(!text_u16(r,&at,a->end,&n) || n>(a->end-at)/4) goto bad;at+=4*n; }
  for(i=0;i<5;i++) {
    if(mask&(8u<<i)) { if(!text_u16(r,&at,a->end,&n)) goto bad;levels[i].style.margin=text_signed(n)/8; }
    if(mask&(256u<<i)) { if(!text_u16(r,&at,a->end,&n)) goto bad;levels[i].style.indent=text_signed(n)/8; }
  }
  return;
bad:r->drawing->text_malformed++;
}
static uint32_t text_color(drawing_reader *r,uint32_t value) {
  unsigned index=value>>24;uint32_t color=0;
  if(index==0xfe) color=value&0xffffff;
  else if(index<8 && (r->color_mask&(1u<<index))) color=r->colors[index];
  else r->drawing->text_color_index++;
  return ((color&255)<<24)|((color&0xff00)<<8)|((color>>16&255)<<8)|255;
}
static const char *text_family(drawing_reader *r,unsigned index) {
  if(index<r->drawing->font_count) return r->drawing->fonts[index];
  r->drawing->text_font_index++;return "sans-serif";
}
static exr_ppt_text_style text_resolve(drawing_reader *r,text_props p) {
  exr_ppt_drawing *d=r->drawing;
  p.style.family="sans-serif";
  if(p.font<d->font_count) p.style.family=d->fonts[p.font];else d->text_font_index++;
  p.style.ea=p.style.family;
  if(p.ea!=0xffff) {
    if(p.ea<d->font_count) p.style.ea=d->fonts[p.ea];else { p.style.ea="sans-serif";d->text_font_index++; }
  }
  p.style.color=text_color(r,p.color);
  if(!(p.bullet_flags&1)) p.style.bullet=0;
  else {
    if(p.bullet_flags&2) p.style.bullet_family=text_family(r,p.bullet_font);
    if(p.bullet_flags&4) p.style.bullet_color=text_color(r,p.bullet_color);
    if(p.bullet_flags&8) p.style.bullet_size=p.bullet_size<=32767 ? -(double)p.bullet_size/100 : -text_signed(p.bullet_size);
  }
  p.style.indent-=p.style.margin;return p.style;
}
typedef struct { size_t start,end; text_props props; } text_span;
static int text_span_add(text_span **spans,size_t *count,size_t *capacity,size_t start,size_t end,text_props props) {
  if(*count>=65536 || !exr_grow((void **)spans,capacity,*count+1,sizeof(**spans))) return 0;
  (*spans)[*count]=(text_span){start,end,props};(*count)++;return 1;
}
static exr_status read_text(drawing_reader *r,const art_shape *s,exr_ppt_text **out,exr_error *e) {
  art_record atom,chars={0},bytes={0},style={0},ruler={0},levels_atom={0};
  size_t begin=s->textbox.payload,end=s->textbox.end,at=begin,units,i,kind=4,*map=NULL;
  size_t pc=0,cc=0,pcap=0,ccap=0,start=0,total=0,j=0,k=0,rcap=0,para_cap=0;
  text_span *pf=NULL,*cf=NULL;exr_ppt_text *text=NULL;exr_buffer value={0};
  text_props levels[5];exr_status status=EXR_OK;int bad=0;
  *out=NULL;if(!end) return EXR_OK;
  while(art_next(r,&at,end,&atom)) if(atom.type==0x0f9e && atom.end-atom.payload>=4) {
    unsigned ref=u32(r->data+atom.payload),n=0;size_t cursor=r->outline_begin;art_record a;
    begin=end=0;
    while(art_next(r,&cursor,r->outline_end,&a)) if(a.type==0x0f9f) {
      if(n++==ref) { begin=a.payload-8;end=r->outline_end; }
      else if(begin) { end=a.payload-8;break; }
    }
    if(!begin) r->drawing->text_index++;
    break;
  }
  at=begin;
  while(art_next(r,&at,end,&atom)) {
    if(atom.type==0x0f9f && atom.end-atom.payload>=4) kind=u32(r->data+atom.payload);
    else if(atom.type==0x0fa0) chars=atom;
    else if(atom.type==0x0fa8) bytes=atom;
    else if(atom.type==0x0fa1) style=atom;
    else if(atom.type==0x0fa2) levels_atom=atom;
    else if(atom.type==0x0fa6) ruler=atom;
  }
  if(!chars.end && !bytes.end) return EXR_OK;
  if(kind>8) { kind=4;r->drawing->text_malformed++; }
  memcpy(levels,s->placeholder ? r->master_text[kind] : r->environment[kind],sizeof(levels));
  if(ruler.end) text_ruler(r,&ruler,levels);
  atom=chars.end ? chars : bytes;units=atom.end-atom.payload;
  if(chars.end) { if(units&1) r->drawing->text_unicode++;units/=2; }
  else {
    /* ASCII TextBytesAtom is the normal PowerPoint table encoding. */
    for(i=0;r->in_table && i<units && r->data[atom.payload+i]<128;i++) { }
    if(!r->in_table || i<units) r->drawing->text_bytes_fallback++;
  }
  if(units>EXR_MAX_TEXT/8) return exr_fail(e,EXR_LIMIT,"PPT textbox exceeds text budget");
  map=calloc(units+2,sizeof(*map));text=calloc(1,sizeof(*text));
  if(!map || !text) goto memory;
  for(i=0;i<units;i++) {
    uint32_t cp=chars.end ? u16(r->data+atom.payload+2*i) : r->data[atom.payload+i];
    map[i]=value.size;
    if(!(i&1023) && (status=exr_control_cancel(r->control,e))!=EXR_OK) goto done;
    if(cp>=0xd800 && cp<=0xdbff) {
      unsigned low=i+1<units ? u16(r->data+atom.payload+2*(i+1)) : 0;
      if(low>=0xdc00 && low<=0xdfff) { map[++i]=value.size;cp=0x10000+((cp-0xd800)<<10)+low-0xdc00; }
      else { cp=0xfffd;r->drawing->text_unicode++; }
    } else if(cp>=0xdc00 && cp<=0xdfff) { cp=0xfffd;r->drawing->text_unicode++; }
    if(!cp) { cp=0xfffd;r->drawing->text_unicode++; }
    if(!exr_codepoint(&value,cp)) goto memory;
  }
  map[units]=map[units+1]=value.size;
  text->value=value.data;value.data=NULL;text->length=map[units];
  if(!text->value) { text->value=exr_copy("",0);if(!text->value) goto memory; }
  memcpy(text->inset,s->inset,sizeof(text->inset));text->anchor=s->anchor_text;text->wrap=s->wrap;
  at=style.payload;
  while(style.end && at<style.end && total<units+1) {
    uint32_t count;unsigned level;text_props p;
    if((status=exr_control_cancel(r->control,e))!=EXR_OK) goto done;
    if(!text_u32(r,&at,style.end,&count) || !text_u16(r,&at,style.end,&level) || !count) { bad=1;break; }
    if(level>4) { level=4;r->drawing->text_malformed++; }
    p=levels[level];
    if(!text_pf(r,&at,style.end,&p)) { bad=1;break; }
    start=total;total+=count;if(total>units+1) r->drawing->text_runs++;
    if(!text_span_add(&pf,&pc,&pcap,start,total>units+1 ? units+1 : total,p)) goto memory;
  }
  if(style.end && total<units+1) { r->drawing->text_runs++;bad=1; }
  total=0;
  while(!bad && style.end && at<style.end && total<units+1) {
    uint32_t count;text_props p={0};
    if((status=exr_control_cancel(r->control,e))!=EXR_OK) goto done;
    if(!text_u32(r,&at,style.end,&count) || !count || !text_cf(r,&at,style.end,&p)) { bad=1;break; }
    start=total;total+=count;if(total>units+1) r->drawing->text_runs++;
    if(!text_span_add(&cf,&cc,&ccap,start,total>units+1 ? units+1 : total,p)) goto memory;
  }
  if(style.end && (total!=units+1 || at!=style.end)) r->drawing->text_runs++;
  if(bad) { r->drawing->text_malformed++;r->drawing->text_runs++;pc=cc=0; }
  /* A malformed/short final run inherits the last usable style. Paragraphs
     follow the actual CRs, independent of corrupt style run boundaries. */
  start=0;
  for(i=0;i<=units;i++) if(i==units || (chars.end ? u16(r->data+atom.payload+2*i) : r->data[atom.payload+i])==13) {
    text_props p=levels[0];size_t a=start;
    if((status=exr_control_cancel(r->control,e))!=EXR_OK) goto done;
    while(j+1<pc && start>=pf[j].end) j++;
    if(pc) p=pf[j].props;
    else if(levels_atom.end) {
      size_t cursor=levels_atom.payload,pos=0;uint32_t count;unsigned level;
      while(text_u32(r,&cursor,levels_atom.end,&count) && text_u16(r,&cursor,levels_atom.end,&level)) {
        if(count>units+1-pos) count=(uint32_t)(units+1-pos);
        pos+=count;if(start<pos) { p=levels[level<5 ? level : 4];break; }
        if(pos==units+1) break;
      }
    }
    if(text->paragraph_count>=65536) { status=exr_fail(e,EXR_LIMIT,"PPT textbox exceeds 65536 paragraphs");goto done; }
    if(!exr_grow((void **)&text->paragraphs,&para_cap,text->paragraph_count+1,sizeof(*text->paragraphs))) goto memory;
    text->paragraphs[text->paragraph_count++]=(exr_ppt_text_paragraph){map[start],map[i],text_resolve(r,p),NULL};
    while(a<i) {
      size_t b=i;text_props v=p;
      while(k+1<cc && a>=cf[k].end) k++;
      if(cc) { text_cf_overlay(&v,&cf[k].props);if(cf[k].end>a && cf[k].end<b) b=cf[k].end; }
      if(text->run_count>=65536) { status=exr_fail(e,EXR_LIMIT,"PPT textbox exceeds 65536 text runs");goto done; }
      if(!exr_grow((void **)&text->runs,&rcap,text->run_count+1,sizeof(*text->runs))) goto memory;
      text->runs[text->run_count++]=(exr_ppt_text_run){map[a],map[b],text_resolve(r,v)};a=b;
    }
    start=i+1;
  }
  total=text->length+2*text->run_count*sizeof(*text->runs)+2*text->paragraph_count*sizeof(*text->paragraphs);
  if(total>EXR_MAX_TEXT-r->drawing->text_bytes) { status=exr_fail(e,EXR_LIMIT,"PPT text exceeds 64 MiB");goto done; }
  r->drawing->text_bytes+=total;
  *out=text;text=NULL;goto done;
memory:status=exr_fail(e,EXR_MEMORY,"PPT text allocation failed");
done:
  if(text) { free(text->value);free(text->runs);free(text->paragraphs);free(text); }
  free(value.data);free(map);free(pf);free(cf);return status;
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
  if(!s->has_fsp || (s->type!=1 && s->type!=3 && s->type!=75 && !line && !s->textbox.end) || s->rotation) { d->unsupported++;return EXR_OK; }
  shape.type=s->type;shape.style=exr_draw_style_defaults();shape.style.flags=0;
  shape.clip_text=r->in_table;
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
  } else if(!line && !s->textbox.end) return EXR_OK;
  if(!((s->line_flags&0x80000) && !(s->line_flags&8))) {
    if(colorref(r,s->line,&shape.style.stroke)) shape.style.flags|=EXR_DRAW_STROKE;
    else d->unsupported++;
  }
  /* Preserve M2's noFill geometry omission while retaining the textbox. */
  if(!line && s->type!=75 && (s->fill_flags&0x100000) && !(s->fill_flags&0x10)) shape.style.flags=0;
  if(s->textbox.end && s->type!=1 && s->type!=3 && s->type!=75 && s->type!=202 && !line) {
    shape.style.flags=0;shape.blip=0;shape.has_gradient=0;d->unsupported++;
  }
  if(!shape.style.flags && !shape.blip && !s->textbox.end) return EXR_OK;
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
  if(s->textbox.end) {
    exr_status status=read_text(r,s,&shape.text,e);if(status!=EXR_OK) return status;
  }
  d->shapes[d->count++]=shape;return EXR_OK;
}
/* MS-ODRAW tableProperties (039F) marks a Spgr, not ClientData. Cells are
   ordinary rectangles/textboxes; borders are independent line shapes. A merge
   is a spanning rectangle with no covered cell shapes. Keep that representation
   and send its geometry/text through the same M2/M4 emit/layout paths. */
typedef struct { art_shape shape; unsigned row,col,rows,cols; int skip; } table_cell;
static int table_edge(double edges[201],unsigned *count,double value) {
  unsigned i=0;
  while(i<*count && edges[i]<value) i++;
  if(i<*count && edges[i]==value) return 1;
  if(*count==201) return 0;
  memmove(edges+i+1,edges+i,(*count-i)*sizeof(*edges));edges[i]=value;(*count)++;return 1;
}
static unsigned table_index(const double *edges,unsigned count,double value) {
  unsigned i=0;while(i+1<count && edges[i]<value) i++;return i;
}
static exr_status table_frame(drawing_reader *r,const art_shape *group,const transform *t,exr_error *e) {
  art_shape frame=*group;size_t first=r->drawing->count;exr_status status;
  r->drawing->table_missing++;
  frame.type=1;frame.flags&=~1u;frame.has_fsp=1;frame.textbox.end=0;
  frame.line_flags=0x80008;
  /* emit_shape preserves M2's noFill omission; retain only this outline. */
  frame.fill_type=0;frame.fill=0xffffff;frame.fill_flags=0x100010;
  status=emit_shape(r,&frame,t,e);
  if(r->drawing->count>first) r->drawing->shapes[first].style.flags&=~EXR_DRAW_FILL;
  return status;
}
static exr_status table_border(drawing_reader *r,const art_shape *line,const transform *t,
  const double *xs,unsigned nx,const double *ys,unsigned ny,const unsigned *owners,exr_error *e) {
  unsigned axis,n,edge,i;const double *grid;double low,high;
  if(line->anchor[0]==line->anchor[2]) { axis=0;grid=ys;n=ny;edge=table_index(xs,nx,line->anchor[0]); }
  else if(line->anchor[1]==line->anchor[3]) { axis=1;grid=xs;n=nx;edge=table_index(ys,ny,line->anchor[1]); }
  else return emit_shape(r,line,t,e);
  if(!edge || edge>=(axis ? ny : nx)-1 || (axis ? ys : xs)[edge]!=line->anchor[axis])
    return emit_shape(r,line,t,e);
  low=fmin(line->anchor[1-axis],line->anchor[3-axis]);high=fmax(line->anchor[1-axis],line->anchor[3-axis]);
  for(i=0;i+1<n;i++) {
    size_t a=axis ? (edge-1)*(nx-1)+i : i*(nx-1)+edge-1;
    size_t b=axis ? edge*(nx-1)+i : a+1;
    art_shape part=*line;exr_status status;
    if(owners[a] && owners[a]==owners[b]) continue;
    part.anchor[1-axis]=fmax(low,grid[i]);part.anchor[3-axis]=fmin(high,grid[i+1]);
    if(part.anchor[1-axis]>=part.anchor[3-axis]) continue;
    status=emit_shape(r,&part,t,e);if(status!=EXR_OK) return status;
  }
  return EXR_OK;
}
static exr_status read_table(drawing_reader *r,size_t at,size_t end,const art_shape *group,
  const transform *parent,const transform *t,exr_error *e) {
  table_cell *cells=NULL;size_t count=0,capacity=0,i,j,k,rectangles=0;
  unsigned nx=0,ny=0,*owners=NULL;double xs[201],ys[201];art_record a;
  exr_ppt_drawing *d=r->drawing;exr_ppt_table table={0};exr_status status=EXR_OK;
  int previous=r->in_table,bad=group->table_bad;r->in_table=1;
  if(group->table_rows>200) { status=exr_fail(e,EXR_LIMIT,"PPT table exceeds 200 rows");goto done; }
  if(group->table_heights.end-group->table_heights.payload>=6) {
    size_t available=(group->table_heights.end-group->table_heights.payload-6)/4;
    for(i=0;i<group->table_rows && i<available;i++)
      if(i32(r->data+group->table_heights.payload+6+4*i)<=0) bad=1;
  }
  if(bad) d->table_malformed++;
  if(!table_edge(xs,&nx,group->children[0]) || !table_edge(xs,&nx,group->children[2]) ||
     !table_edge(ys,&ny,group->children[1]) || !table_edge(ys,&ny,group->children[3])) goto limit;
  while(art_next(r,&at,end,&a)) {
    art_shape s;
    status=exr_control_cancel(r->control,e);if(status!=EXR_OK) goto done;
    if(a.type!=0xf004 || a.ver!=15) { d->table_malformed++;continue; }
    status=read_shape(r,&a,&s,e);if(status!=EXR_OK) goto done;
    if(!s.valid || (s.flags&8)) continue;
    if(!s.has_anchor || !s.has_fsp || (s.type!=1 && s.type!=20 && s.type!=32)) { d->table_malformed++;continue; }
    if(count>=EXR_MAX_INPUT/(2*sizeof(*cells))) goto limit;
    if(!exr_grow((void **)&cells,&capacity,count+1,sizeof(*cells))) {
      status=exr_fail(e,EXR_MEMORY,"PPT table cell allocation failed");goto done;
    }
    cells[count++]=(table_cell){s,0,0,0,0,0};
    if(s.type!=1) continue;
    if(s.anchor[0]<group->children[0] || s.anchor[1]<group->children[1] ||
       s.anchor[2]>group->children[2] || s.anchor[3]>group->children[3] ||
       s.anchor[0]>=s.anchor[2] || s.anchor[1]>=s.anchor[3]) {
      cells[count-1].skip=1;d->table_malformed++;continue;
    }
    if(++rectangles>40000 || !table_edge(xs,&nx,s.anchor[0]) || !table_edge(xs,&nx,s.anchor[2]) ||
       !table_edge(ys,&ny,s.anchor[1]) || !table_edge(ys,&ny,s.anchor[3])) goto limit;
  }
  if(!rectangles || nx<2 || ny<2) { status=table_frame(r,group,parent,e);goto done; }
  if(!group->table_heights.end) d->table_missing++;
  /* ponytail: invisible row boundaries use minimum-height ratios. Exact hidden
     boundaries need extra preserved metadata (e.g. metroBlob); visible cell
     anchors always take precedence. */
  if(ny==2 && group->table_rows>1 && !bad) {
    double sum=0,pos=ys[0],height=ys[1]-ys[0];unsigned row;
    for(row=0;row<group->table_rows;row++) sum+=u32(r->data+group->table_heights.payload+6+4*row);
    if(sum>0) for(row=0;row+1<group->table_rows;row++) {
      pos+=height*u32(r->data+group->table_heights.payload+6+4*row)/sum;
      if(!table_edge(ys,&ny,pos)) goto limit;
    }
  }
  if(ny-1!=group->table_rows) d->table_malformed++;
  owners=calloc((nx-1)*(ny-1),sizeof(*owners));
  if(!owners) { status=exr_fail(e,EXR_MEMORY,"PPT table grid allocation failed");goto done; }
  table.first=d->count;table.rows=ny-1;table.columns=nx-1;
  for(i=0;i<count;i++) {
    table_cell *c=&cells[i];art_shape *s=&c->shape;int conflict=0;
    status=exr_control_cancel(r->control,e);if(status!=EXR_OK) goto done;
    if(c->skip || s->type!=1) continue;
    c->col=table_index(xs,nx,s->anchor[0]);c->row=table_index(ys,ny,s->anchor[1]);
    c->cols=table_index(xs,nx,s->anchor[2])-c->col;c->rows=table_index(ys,ny,s->anchor[3])-c->row;
    for(j=c->row;j<c->row+c->rows && !conflict;j++) for(k=c->col;k<c->col+c->cols;k++)
      if(owners[j*(nx-1)+k]) { conflict=1;break; }
    if(conflict) { c->skip=1;d->table_merge++;continue; }
    for(j=c->row;j<c->row+c->rows;j++) for(k=c->col;k<c->col+c->cols;k++) owners[j*(nx-1)+k]=(unsigned)i+1;
    table.cells++;if(c->cols>1 || c->rows>1) table.merged++;
  }
  for(i=0;i<(nx-1)*(ny-1);i++) if(!owners[i]) { d->table_malformed++;break; }
  /* Draw all cells before all borders so a later fill never erases a border. */
  for(i=0;i<count;i++) if(!cells[i].skip && cells[i].shape.type==1) {
    status=exr_control_cancel(r->control,e);if(status!=EXR_OK) goto done;
    status=emit_shape(r,&cells[i].shape,t,e);if(status!=EXR_OK) goto done;
  }
  for(i=0;i<count;i++) if(!cells[i].skip && cells[i].shape.type!=1) {
    status=exr_control_cancel(r->control,e);if(status!=EXR_OK) goto done;
    status=table_border(r,&cells[i].shape,t,xs,nx,ys,ny,owners,e);if(status!=EXR_OK) goto done;
  }
  table.count=d->count-table.first;
  if(!exr_grow((void **)&d->tables,&d->table_capacity,d->table_count+1,sizeof(table))) {
    status=exr_fail(e,EXR_MEMORY,"PPT table directory allocation failed");goto done;
  }
  d->tables[d->table_count++]=table;goto done;
limit:status=exr_fail(e,EXR_LIMIT,"PPT table exceeds 200x200 or cell storage budget");
done:r->in_table=previous;free(cells);free(owners);return status;
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
        transform parent=t;
        group_header=0;
        if(!s.valid || (s.flags&8)) return EXR_OK;
        if(!s.has_fsp || !(s.flags&1)) { r->drawing->malformed++;return EXR_OK; }
        if(s.rotation) { r->drawing->unsupported++;return EXR_OK; }
        /* The root patriarch has no anchor and introduces no transform. */
        if(!s.has_anchor && (s.flags&4)) continue;
        if(!s.has_anchor) { r->drawing->missing_anchor++;return EXR_OK; }
        if(!s.has_children) {
          if(s.table) {
            if(s.table_rows>200) return exr_fail(e,EXR_LIMIT,"PPT table exceeds 200 rows");
            return table_frame(r,&s,&t,e);
          }
          r->drawing->malformed++;return EXR_OK;
        }
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
        if(s.table) return read_table(r,at,end,&s,&parent,&t,e);
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
  exr_ppt_text_free(d);
  for(i=0;i<d->font_count;i++) free(d->fonts[i]);
  free(d->fonts);
  free(d->tables);
  free(d->blips);
  free(d->shapes);free(d->slides);memset(d,0,sizeof(*d));
}
exr_status exr_ppt_read_drawing(const exr_ppt_streams *streams,const exr_ppt_info *info,const exr_control *control,exr_ppt_drawing *out,exr_error *e) {
  size_t size=streams->document_size;
  drawing_reader r={0};art_record a;size_t at=0,doc=0,doc_end=0,master=0,n=0,i;
  size_t *physical=NULL,*outline=NULL;uint32_t *refs=NULL,*persist=NULL;exr_status status=EXR_OK;
  memset(out,0,sizeof(*out));r.data=streams->document;r.streams=streams;r.control=control;r.drawing=out;out->pages=info->pages;
  if(!out->pages) return EXR_OK;
  out->slides=calloc(out->pages,sizeof(*out->slides));physical=calloc(out->pages*2,sizeof(*physical));refs=calloc(out->pages,sizeof(*refs));
  outline=calloc(out->pages*2,sizeof(*outline));
  if(!out->slides || !physical || !refs || !outline) { status=exr_fail(e,EXR_MEMORY,"PPT drawing directory allocation failed");goto done; }
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
  text_defaults(r.environment);
  status=text_resources(&r,doc,doc_end,0,e);if(status!=EXR_OK) goto done;
  for(i=0;i<9;i++) if(i!=4) memcpy(r.environment[i],r.environment[4],sizeof(r.environment[i]));
  at=doc;n=0;
  while(art_next(&r,&at,doc_end,&a)) if(a.type==RT_SLIDE_LIST && a.instance==0) {
    size_t entry=a.payload;art_record ref;
    while(art_next(&r,&entry,a.end,&ref)) if(ref.type==RT_SLIDE_PERSIST && ref.end-ref.payload>=20 && n<out->pages) {
      if(n) outline[out->pages+n-1]=ref.payload-8;
      refs[n]=u32(r.data+ref.payload);outline[n]=ref.end;outline[out->pages+n]=a.end;n++;
    }
  }
  for(i=0;i<out->pages;i++) {
    size_t offset=physical[i],cursor,master_offset=physical[out->pages+i];art_record slide,child;unsigned flags=0;
    uint32_t master_id=0;
    out->slides[i].first=out->count;r.shapes=0;r.patriarch=0;
    r.outline_begin=outline[i];r.outline_end=outline[out->pages+i];
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
    memcpy(r.master_text,r.environment,sizeof(r.master_text));
    if(master_offset && master_offset<size) {
      art_record m;size_t entry=master_offset;
      if(art_next(&r,&entry,size,&m) && m.type==0x03f8) {
        size_t cursor=m.payload;art_record text;
        read_scheme(&r,&m);
        while(art_next(&r,&cursor,m.end,&text)) if(text.type==0x0fa3) text_master(&r,&text,r.master_text);
      }
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
  free(physical);free(refs);free(persist);free(outline);
  if(status!=EXR_OK) exr_ppt_drawing_free(out);
  return status;
}
