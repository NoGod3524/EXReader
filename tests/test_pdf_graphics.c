/* SPDX-License-Identifier: GPL-3.0-only */
#include "../src/pdf_internal.h"
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
typedef struct {
  exr_bitmap image,clip; unsigned char saved[160][64]; size_t depth,saves,restores,texts,paths,clips,glyphs,images,work;
  exr_pdf_path_paint last; exr_vector_segment segments[64]; double dashes[1024];
  exr_pdf_text_glyph glyph; exr_pdf_paint_state image_paint;
} raster;
static exr_bitmap bitmap(unsigned channels,unsigned value) {
  exr_bitmap out={0}; out.width=out.height=8; out.channels=channels; out.stride=8*channels; out.pixels=malloc((size_t)out.stride*8);
  CHECK(out.pixels); memset(out.pixels,value,(size_t)out.stride*8); return out;
}
static uint32_t color(const exr_pdf_color *c) {
  unsigned r,g,b,a=(unsigned)floor(c->alpha*255+.5);
  if(c->space==EXR_PDF_DEVICE_GRAY) r=g=b=(unsigned)floor(c->values[0]*255+.5);
  else if(c->space==EXR_PDF_DEVICE_RGB) { r=(unsigned)floor(c->values[0]*255+.5); g=(unsigned)floor(c->values[1]*255+.5); b=(unsigned)floor(c->values[2]*255+.5); }
  else { r=(unsigned)floor((1-fmin(1,c->values[0]+c->values[3]))*255+.5); g=(unsigned)floor((1-fmin(1,c->values[1]+c->values[3]))*255+.5); b=(unsigned)floor((1-fmin(1,c->values[2]+c->values[3]))*255+.5); }
  return (r<<24)|(g<<16)|(b<<8)|a;
}
static exr_status fill(raster *r,const exr_vector_polyline *path,int close,exr_vector_rule rule,uint32_t rgba,exr_bitmap *target,exr_error *e) {
  exr_vector_edge *edges=NULL; size_t count; exr_status status=exr_vector_edges(path,close,&edges,&count,&r->work,NULL,e);
  if(status==EXR_OK) status=exr_vector_fill(target,edges,count,rule,rgba,&r->clip,&r->work,NULL,e);
  free(edges); return status;
}
static int inverse(const double *m,double out[6]) {
  double d=m[0]*m[3]-m[1]*m[2]; if(!d) return 0;
  out[0]=m[3]/d; out[1]=-m[1]/d; out[2]=-m[2]/d; out[3]=m[0]/d;
  out[4]=-(out[0]*m[4]+out[2]*m[5]); out[5]=-(out[1]*m[4]+out[3]*m[5]); return 1;
}
static exr_status path_event(void *context,const exr_pdf_path_paint *paint,exr_error *e) {
  raster *r=context; exr_vector_polyline flat={0},dashed={0},outline={0}; exr_status status;
  CHECK(paint->count<=64 && paint->paint.dash_count<=1024); r->last=*paint;
  if(paint->count) memcpy(r->segments,paint->segments,paint->count*sizeof(*r->segments)); r->last.segments=r->segments;
  if(paint->paint.dash_count) memcpy(r->dashes,paint->paint.dashes,paint->paint.dash_count*sizeof(double)); r->last.paint.dashes=r->dashes;
  status=exr_vector_flatten(paint->segments,paint->count,NULL,.01,&flat,&r->work,NULL,e); if(status!=EXR_OK) return status;
  if(paint->flags&EXR_PDF_FILL) { r->paths++; status=fill(r,&flat,1,paint->rule,color(&paint->paint.fill),&r->image,e); }
  if(status==EXR_OK && (paint->flags&EXR_PDF_STROKE)) {
    exr_vector_segment local[64]; double inv[6],scale; size_t i,j;
    r->paths++; CHECK(inverse(paint->paint.matrix,inv));
    if(paint->count) memcpy(local,paint->segments,paint->count*sizeof(*local));
    for(i=0;i<paint->count;i++) for(j=0;j<(local[i].verb==EXR_VECTOR_CLOSE ? 0u : local[i].verb==EXR_VECTOR_CUBIC ? 3u : 1u);j++) {
      exr_vector_point p=local[i].points[j]; local[i].points[j]=(exr_vector_point){inv[0]*p.x+inv[2]*p.y+inv[4],inv[1]*p.x+inv[3]*p.y+inv[5]};
    }
    exr_vector_polyline_free(&flat); scale=hypot(paint->paint.matrix[0],paint->paint.matrix[1])+hypot(paint->paint.matrix[2],paint->paint.matrix[3]);
    status=exr_vector_flatten(local,paint->count,NULL,.01/fmax(1,scale),&flat,&r->work,NULL,e);
    if(status==EXR_OK && paint->paint.dash_count) status=exr_vector_dash(&flat,paint->paint.dashes,paint->paint.dash_count,paint->paint.dash_phase,&dashed,&r->work,NULL,e);
    if(status==EXR_OK) status=exr_vector_stroke(paint->paint.dash_count ? &dashed : &flat,&paint->paint.line,paint->paint.matrix,.01,&outline,&r->work,NULL,e);
    if(status==EXR_OK) status=fill(r,&outline,0,EXR_VECTOR_NONZERO,color(&paint->paint.stroke),&r->image,e);
  }
  if(status==EXR_OK && (paint->flags&EXR_PDF_CLIP)) {
    exr_bitmap mask=bitmap(1,0); r->clips++;
    status=fill(r,&flat,1,paint->rule,0xffffffff,&mask,e);
    if(status==EXR_OK) { free(r->clip.pixels); r->clip=mask; } else free(mask.pixels);
  }
  exr_vector_polyline_free(&flat); exr_vector_polyline_free(&dashed); exr_vector_polyline_free(&outline); return status;
}
static exr_status state_event(void *context,exr_pdf_state_event event,exr_error *e) {
  raster *r=context; (void)e;
  if(event==EXR_PDF_SAVE) { CHECK(r->depth<160); memcpy(r->saved[r->depth++],r->clip.pixels,64); r->saves++; }
  else if(event==EXR_PDF_RESTORE) { CHECK(r->depth); memcpy(r->clip.pixels,r->saved[--r->depth],64); r->restores++; }
  else r->texts++;
  return EXR_OK;
}
static exr_status glyph_event(void *context,const exr_pdf_text_glyph *glyph,exr_error *e) { raster *r=context; (void)e; r->glyph=*glyph; r->glyphs++; return EXR_OK; }
static exr_status image_event(void *context,exr_pdf_file *file,uint32_t image,exr_pdf_file *resource_file,uint32_t resources,const exr_pdf_paint_state *paint,exr_error *e) {
  (void)resource_file;
  raster *r=context; (void)e; (void)resources; CHECK(exr_pdf_value_at(file,image)->kind==EXR_PDF_STREAM); r->image_paint=*paint; r->images++; return EXR_OK;
}
static exr_status stop_path(void *context,const exr_pdf_path_paint *path,exr_error *e) { (void)context; (void)path; (void)e; return EXR_CANCELLED; }
static exr_pdf_draw_callbacks callbacks(void) { exr_pdf_draw_callbacks cb={glyph_event,path_event,state_event,image_event}; return cb; }
static void reset(raster *r) { memset(r,0,sizeof(*r)); r->image=bitmap(4,255); r->clip=bitmap(1,255); }
static void release(raster *r) { free(r->image.pixels); free(r->clip.pixels); }
static void run(exr_pdf_file *file,uint32_t resources,const char *content,const double *matrix,raster *r) {
  exr_pdf_draw_callbacks cb=callbacks(); reset(r); OK(exr_pdf_draw_ops(file,resources,content,strlen(content),matrix,&cb,r,NULL,&error)); CHECK(!r->depth);
}
static void pixel(const raster *r,unsigned x,unsigned y,unsigned red,unsigned green,unsigned blue) {
  const unsigned char *p=r->image.pixels+(size_t)y*r->image.stride+x*4; CHECK(p[0]==red && p[1]==green && p[2]==blue && p[3]==255);
}
int main(int argc,char **argv) {
  char path[4096]; FILE *input; unsigned char *data; long length; exr_pdf_file *file=NULL; exr_pdf_page_info *pages=NULL; size_t count,i; uint32_t resources; raster r;
  const char *invalid[]={"1 1 l S","h","1 2 3 re f","0 0 m","BT 1 1 m ET","3 J",".5 M","-1 w","[0 0] 0 d","[1 2] -1 d","1 0 0 g","/Unsupported cs","/Blend gs","/Soft gs","/Shade sh"};
  CHECK(argc==2); snprintf(path,sizeof(path),"%s/pdf-graphics.pdf",argv[1]); input=fopen(path,"rb"); CHECK(input && !fseek(input,0,SEEK_END)); length=ftell(input); CHECK(length>0); rewind(input); data=malloc((size_t)length);
  CHECK(data && fread(data,1,(size_t)length,input)==(size_t)length); fclose(input); OK(exr_pdf_open(data,(size_t)length,&file,&error));
  OK(exr_pdf_pages(file,&pages,&count,&error)); CHECK(count==1); resources=pages[0].resources;
  { exr_buffer content={0}; exr_pdf_draw_callbacks cb=callbacks(); reset(&r); OK(exr_pdf_content(file,pages[0].contents,&content,&error)); OK(exr_pdf_draw_ops(file,resources,content.data,content.size,NULL,&cb,&r,NULL,&error)); free(content.data);
    pixel(&r,0,0,255,255,255); pixel(&r,1,1,255,0,0); pixel(&r,2,2,0,0,255); pixel(&r,5,5,255,0,0); release(&r);
  }
  run(file,resources,"q 1 1 2 2 re W n 1 0 0 rg 0 0 8 8 re f Q 0 0 1 rg 6 6 1 1 re f",NULL,&r);
  CHECK(r.saves==1 && r.restores==1 && r.clips==1); pixel(&r,1,1,255,0,0); pixel(&r,0,0,255,255,255); pixel(&r,6,6,0,0,255); release(&r);
  run(file,resources,"0 G 2 w 2 2 4 4 re W S 0 0 1 rg 0 0 8 8 re f",NULL,&r);
  pixel(&r,1,2,0,0,0); pixel(&r,2,2,0,0,255); pixel(&r,0,0,255,255,255); release(&r);
  run(file,resources,"0 0 8 8 re 2 2 4 4 re W* n 0 g 0 0 8 8 re f",NULL,&r); pixel(&r,0,0,0,0,0); pixel(&r,3,3,255,255,255); release(&r);
  run(file,resources,"W n 0 g 0 0 8 8 re f",NULL,&r); pixel(&r,4,4,255,255,255); CHECK(r.clips==1); release(&r);
  run(file,resources,"1 1 m q 2 0 0 2 0 0 cm 3 1 l Q 1 3 l h f",NULL,&r);
  CHECK(r.last.count==4 && r.segments[1].points[0].x==6 && r.segments[1].points[0].y==2 && r.last.paint.matrix[0]==1); release(&r);
  run(file,resources,"1 1 m 2 3 4 5 v 6 7 2 1 y S",NULL,&r);
  CHECK(r.last.count==3 && r.segments[1].points[0].x==1 && r.segments[1].points[1].x==2 && r.segments[1].points[2].x==4 && r.segments[2].points[1].x==2); release(&r);
  run(file,resources,"1 1 m 5 1 l 3 5 l b*",NULL,&r); CHECK(r.last.flags==(EXR_PDF_FILL|EXR_PDF_STROKE) && r.last.rule==EXR_VECTOR_EVENODD && r.segments[3].verb==EXR_VECTOR_CLOSE); release(&r);
  run(file,resources,"/A gs /RgbAlias cs 1 0 0 sc 1 1 2 2 re f",NULL,&r);
  pixel(&r,1,1,255,127,127); CHECK(r.last.paint.line.width==2 && r.last.paint.line.cap==EXR_VECTOR_SQUARE && r.last.paint.line.join==EXR_VECTOR_BEVEL && r.last.paint.line.miter_limit==3 && r.last.paint.dash_count==2 && r.dashes[0]==2 && r.dashes[1]==1 && r.last.paint.stroke.alpha==.25); release(&r);
  run(file,resources,"0 1 0 0 k 1 1 2 2 re f",NULL,&r); pixel(&r,1,1,255,0,255); CHECK(r.last.paint.fill.space==EXR_PDF_DEVICE_CMYK && r.last.paint.fill.values[1]==1); release(&r);
  run(file,resources,"/DeviceRGB CS 0 1 0 SCN 1 4 m 7 4 l S",NULL,&r); CHECK(r.last.paint.stroke.space==EXR_PDF_DEVICE_RGB && r.last.paint.stroke.values[1]==1); release(&r);
  run(file,resources,"1 0 0 rg q 0 0 1 rg Q BT /Simple 10 Tf (A) Tj ET",NULL,&r); CHECK(r.glyphs==1 && r.texts==2 && r.glyph.paint.fill.space==EXR_PDF_DEVICE_RGB && r.glyph.paint.fill.values[0]==1 && r.glyph.paint.fill.values[2]==0); release(&r);
  run(file,resources,"0 1 0 rg /Filled Do 0 0 1 1 re f",NULL,&r);
  CHECK(r.saves==1 && r.restores==1 && r.clips==1); pixel(&r,2,3,255,0,0); pixel(&r,0,0,0,255,0); pixel(&r,4,4,255,255,255); release(&r);
  run(file,resources,"1 1 m 2 1 l /Filled Do 1 2 l h f",NULL,&r); CHECK(r.last.count==4 && r.segments[0].points[0].x==1 && r.segments[1].points[0].x==2); release(&r);
  run(file,resources,"q 2 0 0 3 1 2 cm /Image Do Q",NULL,&r); CHECK(r.images==1 && r.image_paint.matrix[0]==2 && r.image_paint.matrix[3]==3 && r.image_paint.matrix[4]==1); release(&r);
  { const double matrix[6]={2,0,0,2,0,0}; run(file,resources,"1 w 1 2 m 3 2 l S",matrix,&r); pixel(&r,3,3,0,0,0); pixel(&r,3,2,255,255,255); CHECK(r.last.paint.matrix[0]==2); release(&r); }
  { const double matrix[6]={1,0,0,-1,0,8}; run(file,resources,"1 0 0 rg 0 0 1 2 re f",matrix,&r); pixel(&r,0,7,255,0,0); pixel(&r,0,0,255,255,255); release(&r); }
  for(i=0;i<sizeof(invalid)/sizeof(*invalid);i++) { exr_pdf_draw_callbacks cb=callbacks(); reset(&r); CHECK(exr_pdf_draw_ops(file,resources,invalid[i],strlen(invalid[i]),NULL,&cb,&r,NULL,&error)==EXR_FORMAT); release(&r); }
  { const char content[]="1 1 2 2 re f"; exr_pdf_draw_callbacks cb=callbacks(); cb.path=stop_path; reset(&r); CHECK(exr_pdf_draw_ops(file,resources,content,sizeof(content)-1,NULL,&cb,&r,NULL,&error)==EXR_CANCELLED); release(&r); }
  free(pages); exr_pdf_close(file); free(data); printf("%u native PDF graphics checks passed\n",checks); return 0;
}
