/* SPDX-License-Identifier: GPL-3.0-only */
#include "pdf_raster_internal.h"
#include "pdf_face_internal.h"
typedef struct { exr_bitmap bitmap; size_t refs; } clip_mask;
typedef struct { const exr_pdf_font *key; exr_pdf_face *face; } raster_face;
typedef struct {
  exr_bitmap bitmap; FT_Library library; const exr_pdf_raster_config *config; const exr_control *control;
  clip_mask *clip,*saved[160],*text; size_t depth,mask_bytes,mask_budget,work,font_count,font_bytes;
  raster_face fonts[128];
} pdf_raster;
static void unref(pdf_raster *r,clip_mask *mask) {
  if(mask && !--mask->refs) { r->mask_bytes-=(size_t)mask->bitmap.stride*mask->bitmap.height; free(mask->bitmap.pixels); free(mask); }
}
static exr_status new_mask(pdf_raster *r,clip_mask **out,exr_error *e) {
  size_t bytes=(size_t)r->bitmap.width*r->bitmap.height; clip_mask *mask;
  *out=NULL;
  if(bytes>r->mask_budget-r->mask_bytes) return exr_fail(e,EXR_LIMIT,"PDF clip masks exceed byte budget");
  mask=calloc(1,sizeof(*mask)); if(!mask) return exr_fail(e,EXR_MEMORY,"PDF clip mask allocation failed");
  mask->bitmap=r->bitmap; mask->bitmap.channels=1; mask->bitmap.stride=r->bitmap.width; mask->bitmap.pixels=calloc(bytes,1);
  if(!mask->bitmap.pixels) { free(mask); return exr_fail(e,EXR_MEMORY,"PDF clip pixel allocation failed"); }
  mask->refs=1; r->mask_bytes+=bytes; *out=mask; return EXR_OK;
}
static uint32_t rgba(const exr_pdf_color *c) {
  unsigned r,g,b,a=(unsigned)floor(c->alpha*255+.5);
  if(c->space==EXR_PDF_DEVICE_GRAY) r=g=b=(unsigned)floor(c->values[0]*255+.5);
  else if(c->space==EXR_PDF_DEVICE_RGB) { r=(unsigned)floor(c->values[0]*255+.5); g=(unsigned)floor(c->values[1]*255+.5); b=(unsigned)floor(c->values[2]*255+.5); }
  else { r=(unsigned)floor((1-fmin(1,c->values[0]+c->values[3]))*255+.5); g=(unsigned)floor((1-fmin(1,c->values[1]+c->values[3]))*255+.5); b=(unsigned)floor((1-fmin(1,c->values[2]+c->values[3]))*255+.5); }
  return (r<<24)|(g<<16)|(b<<8)|a;
}
static int inverse(const double *m,double out[6]) {
  double d=m[0]*m[3]-m[1]*m[2]; size_t i;
  if(!d || !isfinite(d)) return 0;
  out[0]=m[3]/d; out[1]=-m[1]/d; out[2]=-m[2]/d; out[3]=m[0]/d;
  out[4]=-(out[0]*m[4]+out[2]*m[5]); out[5]=-(out[1]*m[4]+out[3]*m[5]);
  for(i=0;i<6;i++) if(!isfinite(out[i]) || fabs(out[i])>1e7) return 0;
  return 1;
}
static void multiply(const double a[6],const double b[6],double out[6]) {
  out[0]=a[0]*b[0]+a[2]*b[1]; out[1]=a[1]*b[0]+a[3]*b[1];
  out[2]=a[0]*b[2]+a[2]*b[3]; out[3]=a[1]*b[2]+a[3]*b[3];
  out[4]=a[0]*b[4]+a[2]*b[5]+a[4]; out[5]=a[1]*b[4]+a[3]*b[5]+a[5];
}
static exr_status fill(pdf_raster *r,const exr_vector_polyline *path,exr_vector_rule rule,uint32_t color,
                         exr_bitmap *target,const clip_mask *clip,exr_error *e) {
  exr_vector_edge *edges=NULL; size_t count=0; exr_status status=exr_vector_edges(path,1,&edges,&count,&r->work,r->control,e);
  if(status==EXR_OK) status=exr_vector_fill(target,edges,count,rule,color,clip ? &clip->bitmap : NULL,&r->work,r->control,e);
  free(edges); return status;
}
static exr_status geometry(pdf_raster *r,const exr_vector_segment *segments,size_t count,const double transform[6],
                             const exr_pdf_paint_state *paint,unsigned flags,exr_vector_rule rule,int text_clip,exr_error *e) {
  exr_vector_polyline flat={0},local={0},dashed={0},outline={0}; exr_status status=EXR_OK;
  if(flags&(EXR_PDF_FILL|EXR_PDF_CLIP)) status=exr_vector_flatten(segments,count,transform,.125,&flat,&r->work,r->control,e);
  if(status==EXR_OK && (flags&EXR_PDF_FILL)) status=fill(r,&flat,rule,rgba(&paint->fill),&r->bitmap,r->clip,e);
  if(status==EXR_OK && (flags&EXR_PDF_STROKE)) {
    double inv[6],matrix[6],scale=hypot(paint->matrix[0],paint->matrix[1])+hypot(paint->matrix[2],paint->matrix[3]);
    if(!inverse(paint->matrix,inv)) { status=exr_fail(e,EXR_FORMAT,"PDF stroke with singular CTM is unsupported"); goto done; }
    if(transform) multiply(inv,transform,matrix); else memcpy(matrix,inv,sizeof(matrix));
    status=exr_vector_flatten(segments,count,matrix,.125/fmax(1,scale),&local,&r->work,r->control,e);
    if(status==EXR_OK && paint->dash_count) status=exr_vector_dash(&local,paint->dashes,paint->dash_count,paint->dash_phase,&dashed,&r->work,r->control,e);
    if(status==EXR_OK) status=exr_vector_stroke(paint->dash_count ? &dashed : &local,&paint->line,paint->matrix,.125,&outline,&r->work,r->control,e);
    if(status==EXR_OK) status=fill(r,&outline,EXR_VECTOR_NONZERO,rgba(&paint->stroke),&r->bitmap,r->clip,e);
  }
  if(status==EXR_OK && (flags&EXR_PDF_CLIP)) {
    if(text_clip) {
      if(!r->text) status=new_mask(r,&r->text,e);
      if(status==EXR_OK) status=fill(r,&flat,rule,0xffffffff,&r->text->bitmap,NULL,e);
    } else {
      clip_mask *mask=NULL; status=new_mask(r,&mask,e);
      if(status==EXR_OK) status=fill(r,&flat,rule,0xffffffff,&mask->bitmap,r->clip,e);
      if(status==EXR_OK) { unref(r,r->clip); r->clip=mask; } else unref(r,mask);
    }
  }
done:
  exr_vector_polyline_free(&flat); exr_vector_polyline_free(&local); exr_vector_polyline_free(&dashed); exr_vector_polyline_free(&outline); return status;
}
static exr_status path_event(void *context,const exr_pdf_path_paint *p,exr_error *e) {
  return geometry(context,p->segments,p->count,NULL,&p->paint,p->flags,p->rule,0,e);
}
static exr_status state_event(void *context,exr_pdf_state_event event,exr_error *e) {
  pdf_raster *r=context;
  if(event==EXR_PDF_SAVE) {
    if(r->depth==160) return exr_fail(e,EXR_LIMIT,"PDF raster clip stack exceeds budget");
    r->saved[r->depth++]=r->clip; if(r->clip) r->clip->refs++;
  } else if(event==EXR_PDF_RESTORE) {
    if(!r->depth) return exr_fail(e,EXR_FORMAT,"PDF raster clip stack underflow");
    unref(r,r->clip); r->clip=r->saved[--r->depth]; r->saved[r->depth]=NULL;
  } else if(event==EXR_PDF_BEGIN_TEXT) {
    unref(r,r->text); r->text=NULL;
  } else if(event==EXR_PDF_END_TEXT && r->text) {
    if(r->clip) {
      uint32_t y,x;
      for(y=0;y<r->bitmap.height;y++) {
        if(!(y&63) && exr_control_cancel(r->control,e)!=EXR_OK) return EXR_CANCELLED;
        if(!exr_vector_work(&r->work,r->bitmap.width)) return exr_fail(e,EXR_LIMIT,"PDF text clip work budget exceeded");
        for(x=0;x<r->bitmap.width;x++) {
          unsigned char *p=r->text->bitmap.pixels+(size_t)y*r->text->bitmap.stride+x;
          *p=(unsigned char)(((unsigned)*p*r->clip->bitmap.pixels[(size_t)y*r->clip->bitmap.stride+x]+127)/255);
        }
      }
    }
    unref(r,r->clip); r->clip=r->text; r->text=NULL;
  }
  return EXR_OK;
}
static exr_status glyph_event(void *context,const exr_pdf_text_glyph *g,exr_error *e) {
  pdf_raster *r=context; size_t i,count=0; exr_status status; exr_vector_segment *segments=NULL; unsigned flags=0,mode=g->rendering_mode;
  if(mode==3) return EXR_OK;
  if(mode==0 || mode==2 || mode==4 || mode==6) flags|=EXR_PDF_FILL;
  if(mode==1 || mode==2 || mode==5 || mode==6) flags|=EXR_PDF_STROKE;
  if(mode>=4) flags|=EXR_PDF_CLIP;
  for(i=0;i<r->font_count;i++) if(r->fonts[i].key==g->font) break;
  if(i==r->font_count) {
    const exr_pdf_font_info *info=exr_pdf_font_description(g->font); const void *fallback=NULL; size_t size=0,bytes;
    if(i==128) return exr_fail(e,EXR_LIMIT,"PDF raster face cache exceeds 128 fonts");
    if(!info->program && r->config->program) { status=r->config->program(r->config->context,info,&fallback,&size,e); if(status!=EXR_OK) return status; }
    status=exr_pdf_face_open(r->library,g->font,fallback,size,&r->fonts[i].face,r->control,e); if(status!=EXR_OK) return status;
    r->fonts[i].key=g->font; r->font_count++; bytes=exr_pdf_face_memory(r->fonts[i].face);
    if(bytes>(size_t)32*1024*1024-r->font_bytes) return exr_fail(e,EXR_LIMIT,"PDF raster CID indexes exceed 32 MiB");
    r->font_bytes+=bytes;
  }
  status=exr_pdf_face_outline(r->fonts[i].face,&g->character,&segments,&count,&r->work,r->control,e);
  if(status==EXR_OK) status=geometry(r,segments,count,g->transform,&g->paint,flags,EXR_VECTOR_NONZERO,1,e);
  free(segments); return status;
}
static exr_status image_event(void *context,exr_pdf_file *file,uint32_t id,uint32_t resources,const exr_pdf_paint_state *paint,exr_error *e) {
  pdf_raster *r=context; exr_vector_texture *image=NULL; double matrix[6]; const double flip[6]={1,0,0,-1,0,1};
  exr_status status=exr_pdf_image_load(file,id,resources,rgba(&paint->fill),&image,&r->work,r->control,e);
  multiply(paint->matrix,flip,matrix);
  if(status==EXR_OK) status=exr_vector_texture_paint(&r->bitmap,image,matrix,paint->fill.alpha,r->clip ? &r->clip->bitmap : NULL,&r->work,r->control,e);
  exr_pdf_image_release(image); return status;
}
exr_status exr_pdf_raster_content(exr_pdf_file *file,uint32_t resources,const void *content,size_t size,
                                   const double initial[6],const exr_pdf_raster_config *config,
                                   const exr_control *control,exr_bitmap *out,exr_error *e) {
  pdf_raster r={0}; exr_pdf_draw_callbacks cb={glyph_event,path_event,state_event,image_event}; exr_status status; size_t bytes,i; unsigned c;
  if(out) memset(out,0,sizeof(*out));
  if(!out || !file || !config || (!content && size) || !config->width || !config->height || config->width>16384 || config->height>16384 ||
     (config->channels!=1 && config->channels!=4) || config->width>(size_t)64*1024*1024/config->channels/config->height)
    return exr_fail(e,EXR_ARGUMENT,"Invalid PDF raster output configuration");
  if(exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
  if(config->initial_clip) {
    const double *b=config->initial_clip;
    for(i=0;i<4;i++) if(!isfinite(b[i]) || fabs(b[i])>1e7) return exr_fail(e,EXR_ARGUMENT,"Invalid initial PDF raster clip");
    if(b[0]>b[2] || b[1]>b[3]) return exr_fail(e,EXR_ARGUMENT,"Inverted initial PDF raster clip");
  }
  r.config=config; r.control=control; r.mask_budget=config->mask_budget ? config->mask_budget : (size_t)64*1024*1024;
  r.bitmap.width=config->width; r.bitmap.height=config->height; r.bitmap.channels=config->channels; r.bitmap.stride=config->width*config->channels;
  bytes=(size_t)r.bitmap.stride*r.bitmap.height; r.bitmap.pixels=malloc(bytes);
  if(!r.bitmap.pixels) return exr_fail(e,EXR_MEMORY,"PDF page bitmap allocation failed");
  if(config->channels==1) {
    unsigned red=config->background>>24,green=(config->background>>16)&255,blue=(config->background>>8)&255;
    memset(r.bitmap.pixels,(int)((red*77+green*150+blue*29+128)>>8),bytes);
  }
  else for(i=0;i<bytes;i+=4) for(c=0;c<4;c++) r.bitmap.pixels[i+c]=(unsigned char)(config->background>>(24-8*c));
  if(config->initial_clip) {
    const double *b=config->initial_clip; exr_pdf_paint_state paint={0}; exr_vector_segment rect[5]={0};
    rect[0].verb=EXR_VECTOR_MOVE; rect[0].points[0]=(exr_vector_point){b[0],b[1]};
    rect[1].verb=EXR_VECTOR_LINE; rect[1].points[0]=(exr_vector_point){b[2],b[1]};
    rect[2].verb=EXR_VECTOR_LINE; rect[2].points[0]=(exr_vector_point){b[2],b[3]};
    rect[3].verb=EXR_VECTOR_LINE; rect[3].points[0]=(exr_vector_point){b[0],b[3]}; rect[4].verb=EXR_VECTOR_CLOSE;
    status=geometry(&r,rect,5,NULL,&paint,EXR_PDF_CLIP,EXR_VECTOR_NONZERO,0,e); if(status!=EXR_OK) goto done;
  }
  if(FT_Init_FreeType(&r.library)) { status=exr_fail(e,EXR_MEMORY,"PDF font library initialization failed"); goto done; }
  status=exr_pdf_draw_ops(file,resources,content,size,initial,&cb,&r,control,e);
  if(status==EXR_OK) { *out=r.bitmap; memset(&r.bitmap,0,sizeof(r.bitmap)); }
done:
  for(i=0;i<r.font_count;i++) exr_pdf_face_close(r.fonts[i].face);
  if(r.library) FT_Done_FreeType(r.library);
  unref(&r,r.clip); unref(&r,r.text); while(r.depth) unref(&r,r.saved[--r.depth]); free(r.bitmap.pixels); return status;
}
