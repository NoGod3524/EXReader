/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include "../src/pdf_raster_internal.h"
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static unsigned char *load(const char *dir,const char *name,size_t *size) {
  char path[4096]; FILE *f; long n; unsigned char *data;
  snprintf(path,sizeof(path),"%s/%s",dir,name); f=fopen(path,"rb"); CHECK(f && !fseek(f,0,SEEK_END)); n=ftell(f); CHECK(n>0); rewind(f);
  *size=(size_t)n; data=malloc(*size); CHECK(data && fread(data,1,*size,f)==*size); fclose(f); return data;
}
static exr_bitmap render(exr_pdf_file *file,uint32_t resources,const char *content,unsigned channels,size_t budget) {
  exr_bitmap out={0}; exr_pdf_raster_config config={0}; config.width=config.height=12; config.channels=channels; config.background=0xffffffff; config.mask_budget=budget;
  OK(exr_pdf_raster_content(file,resources,content,strlen(content),NULL,&config,NULL,&out,&error)); CHECK(out.width==12 && out.height==12 && out.channels==channels); return out;
}
static void pixel(const exr_bitmap *b,unsigned x,unsigned y,unsigned r,unsigned g,unsigned blue) {
  const unsigned char *p=b->pixels+(size_t)y*b->stride+x*b->channels;
  if(b->channels==1) CHECK(*p==r && r==g && r==blue); else CHECK(p[0]==r && p[1]==g && p[2]==blue && p[3]==255);
}
static void text_cases(exr_pdf_file *file,uint32_t resources) {
  exr_bitmap b;
  b=render(file,resources,"1 0 0 rg 0 0 2 2 re f 0 0 1 rg BT /Names 10 Tf (A) Tj ET",4,0);
  pixel(&b,0,0,255,0,0); pixel(&b,6,1,0,0,255); pixel(&b,3,1,255,255,255); free(b.pixels);
  b=render(file,resources,"BT /Names 10 Tf 3 Tr (A) Tj ET",1,0); pixel(&b,6,1,255,255,255); free(b.pixels);
  b=render(file,resources,"BT /Names 10 Tf 7 Tr (A) Tj ET 0 g 0 0 12 12 re f",1,0);
  pixel(&b,6,1,0,0,0); pixel(&b,1,1,255,255,255); pixel(&b,6,8,255,255,255); free(b.pixels);
  b=render(file,resources,"BT /Names 10 Tf 7 Tr (AA) Tj ET 0 g 0 0 12 12 re f",1,0);
  pixel(&b,6,1,0,0,0); pixel(&b,11,1,0,0,0); pixel(&b,3,1,255,255,255); free(b.pixels);
  b=render(file,resources,"q BT /Names 10 Tf 7 Tr (A) Tj ET Q 0 g 0 0 12 12 re f",1,0); pixel(&b,1,1,0,0,0); free(b.pixels);
  b=render(file,resources,"0 0 4 12 re W n BT /Names 10 Tf 7 Tr (A) Tj ET 0 g 0 0 12 12 re f",1,0); pixel(&b,6,1,255,255,255); pixel(&b,1,1,255,255,255); free(b.pixels);
  b=render(file,resources,"BT /Names 10 Tf 7 Tr ( ) Tj ET 0 g 0 0 12 12 re f",1,0); pixel(&b,6,1,255,255,255); free(b.pixels);
  b=render(file,resources,"0 0 1 RG .4 w BT /Names 10 Tf 1 Tr (A) Tj ET",4,0);
  pixel(&b,6,1,255,255,255); CHECK(b.pixels[5*4+2]==255 && b.pixels[5*4]<255); free(b.pixels);
  b=render(file,resources,"0 0 1 rg 1 0 0 RG .4 w BT /Names 10 Tf 2 Tr (A) Tj ET",4,0); pixel(&b,6,1,0,0,255); free(b.pixels);
}
static void clip_cases(exr_pdf_file *file,uint32_t resources) {
  exr_bitmap b; exr_pdf_raster_config config={0}; char content[2048]; size_t at=0,i;
  b=render(file,resources,"q 1 1 2 2 re W n 1 0 0 rg 0 0 12 12 re f Q 0 0 1 rg 6 6 1 1 re f",4,0);
  pixel(&b,1,1,255,0,0); pixel(&b,0,0,255,255,255); pixel(&b,6,6,0,0,255); free(b.pixels);
  b=render(file,resources,"0 G 2 w 2 2 4 4 re W S 0 0 1 rg 0 0 12 12 re f",4,0); pixel(&b,1,2,0,0,0); pixel(&b,2,2,0,0,255); free(b.pixels);
  b=render(file,resources,"0 0 12 12 re 2 2 4 4 re W* n 0 g 0 0 12 12 re f",1,0); pixel(&b,0,0,0,0,0); pixel(&b,3,3,255,255,255); free(b.pixels);
  b=render(file,resources,"W n 0 g 0 0 12 12 re f",1,0); pixel(&b,4,4,255,255,255); free(b.pixels);
  at+=(size_t)snprintf(content+at,sizeof(content)-at,"0 0 12 12 re W n ");
  for(i=0;i<120;i++) at+=(size_t)snprintf(content+at,sizeof(content)-at,"q ");
  at+=(size_t)snprintf(content+at,sizeof(content)-at,"0 g 0 0 12 12 re f ");
  for(i=0;i<120;i++) at+=(size_t)snprintf(content+at,sizeof(content)-at,"Q ");
  b=render(file,resources,content,1,144); pixel(&b,1,1,0,0,0); free(b.pixels); /* 120 saves share one 144-byte mask. */
  config.width=config.height=12; config.channels=1; config.background=0xffffffff; config.mask_budget=144;
  { const char *s="0 0 12 12 re W n q 0 0 6 6 re W n Q"; CHECK(exr_pdf_raster_content(file,resources,s,strlen(s),NULL,&config,NULL,&b,&error)==EXR_LIMIT && !b.pixels && !b.width); }
}
static int cancelled(void *ctx) { (void)ctx; return 1; }
typedef struct { size_t paths,clips,states,images; int stop; } inspection;
static exr_status inspect_path(void *ctx,const exr_path_segment *segments,size_t count,const double matrix[6],const exr_draw_style *style,exr_error *e) {
  inspection *i=ctx; (void)e; CHECK(count>=4 && segments && style->flags==EXR_DRAW_FILL);
  if(matrix) CHECK(segments[0].points[0].x==500 && matrix[0]==.01);
  i->paths++; return i->stop ? EXR_CANCELLED : EXR_OK;
}
static exr_status inspect_clip(void *ctx,const exr_path_segment *segments,size_t count,const double matrix[6],exr_fill_rule rule,unsigned accumulate,exr_error *e) {
  inspection *i=ctx; (void)e; CHECK(segments && count>=4 && matrix && rule==EXR_FILL_NONZERO && accumulate==1); i->clips++; return EXR_OK;
}
static exr_status inspect_state(void *ctx,exr_draw_state state,exr_error *e) {
  inspection *i=ctx; (void)e; CHECK(state==EXR_DRAW_BEGIN_CLIP || state==EXR_DRAW_END_CLIP); i->states++; return EXR_OK;
}
static void drawing_inspection(exr_pdf_file *file,uint32_t resources) {
  inspection i={0}; exr_draw_sink sink={inspect_path,NULL,inspect_clip,inspect_state,&i}; const char *content="1 1 2 2 re f BT /Names 10 Tf (A) Tj ET";
  OK(exr_pdf_paint_content(file,resources,content,strlen(content),NULL,&sink,NULL,NULL,NULL,NULL,&error)); CHECK(i.paths==2 && !i.clips && i.states==2);
  memset(&i,0,sizeof(i)); content="BT /Names 10 Tf 7 Tr (A) Tj ET";
  OK(exr_pdf_paint_content(file,resources,content,strlen(content),NULL,&sink,NULL,NULL,NULL,NULL,&error)); CHECK(!i.paths && i.clips==1 && i.states==2);
  sink.clip=NULL; content="BT /Fallback 10 Tf 7 Tr (A) Tj ET";
  OK(exr_pdf_paint_content(file,resources,content,strlen(content),NULL,&sink,NULL,NULL,NULL,NULL,&error)); /* Ignored clips need no host fallback font. */
  i.stop=1; content="BT /Names 10 Tf (A) Tj ET"; CHECK(exr_pdf_paint_content(file,resources,content,strlen(content),NULL,&sink,NULL,NULL,NULL,NULL,&error)==EXR_CANCELLED);
}
typedef struct { const void *bytes; size_t size,calls; int fail; } fallback_context;
static exr_status program(void *context,const exr_pdf_font_info *info,exr_font_input *source,exr_error *e) {
  fallback_context *c=context; (void)e; CHECK(!info->program && !strcmp(info->base_name,"Helvetica")); c->calls++;
  if(c->fail) return EXR_CANCELLED;
  source->data=c->bytes; source->size=c->size; source->face_index=0; return EXR_OK;
}
static void fallback_cases(const char *dir,exr_pdf_file *file,uint32_t resources) {
  fallback_context context={0}; exr_pdf_raster_config config={0}; exr_bitmap b; unsigned char *data; const char *content="BT /Fallback 10 Tf (AA) Tj ET";
  data=load(dir,"fonts/pdf-names.ttf",&context.size); context.bytes=data;
  config.width=config.height=12; config.channels=1; config.background=0xffffffff; config.program=program; config.context=&context;
  OK(exr_pdf_raster_content(file,resources,content,strlen(content),NULL,&config,NULL,&b,&error)); CHECK(context.calls==1); pixel(&b,1,1,0,0,0); free(b.pixels);
  context.fail=1; CHECK(exr_pdf_raster_content(file,resources,content,strlen(content),NULL,&config,NULL,&b,&error)==EXR_CANCELLED && !b.pixels && context.calls==2);
  content="BT /BadEmbedded 10 Tf (A) Tj ET"; CHECK(exr_pdf_raster_content(file,resources,content,strlen(content),NULL,&config,NULL,&b,&error)==EXR_FORMAT && !b.pixels && context.calls==2);
  content="BT /Fallback 10 Tf 3 Tr (A) Tj ET"; OK(exr_pdf_raster_content(file,resources,content,strlen(content),NULL,&config,NULL,&b,&error)); CHECK(context.calls==2); free(b.pixels);
  config.background=0xff0000ff; OK(exr_pdf_raster_content(file,resources,"",0,NULL,&config,NULL,&b,&error)); pixel(&b,1,1,77,77,77); free(b.pixels);
  free(data);
}
static void page_cases(const char *dir) {
  unsigned char *data; size_t size,count,i; exr_pdf_file *file=NULL; exr_pdf_page_info *pages=NULL; exr_viewport view; exr_bitmap b;
  const unsigned colors[4][4][3]={{{0,0,255},{255,255,0},{255,0,0},{0,255,0}},{{255,0,0},{0,0,255},{0,255,0},{255,255,0}},
    {{0,255,0},{255,0,0},{255,255,0},{0,0,255}},{{255,255,0},{0,255,0},{0,0,255},{255,0,0}}};
  data=load(dir,"pdf-page-view.pdf",&size); OK(exr_pdf_open(data,size,&file,&error)); OK(exr_pdf_pages(file,&pages,&count,&error)); CHECK(count==7);
  for(i=0;i<4;i++) {
    size_t corner; OK(exr_pdf_page_viewport(&pages[i],1,&view,&error)); CHECK(view.width==(i%2 ? 4 : 8) && view.height==(i%2 ? 8 : 4));
    OK(exr_pdf_raster_page(file,&pages[i],1,NULL,NULL,&b,&error)); CHECK(b.width==view.width && b.height==view.height);
    for(corner=0;corner<4;corner++) pixel(&b,corner%2 ? b.width-1 : 0,corner/2 ? b.height-1 : 0,colors[i][corner][0],colors[i][corner][1],colors[i][corner][2]);
    free(b.pixels);
  }
  OK(exr_pdf_page_viewport(&pages[4],1,&view,&error)); CHECK(view.width==4 && view.height==3);
  OK(exr_pdf_raster_page(file,&pages[5],1,NULL,NULL,&b,&error)); CHECK(b.width==4 && b.height==2); pixel(&b,3,1,191,191,191); pixel(&b,0,0,0,0,0); free(b.pixels);
  CHECK(exr_pdf_raster_page(file,&pages[6],1,NULL,NULL,&b,&error)==EXR_FORMAT && !b.pixels && !b.width);
  CHECK(exr_pdf_raster_page(file,&pages[0],100000,NULL,NULL,&b,&error)==EXR_LIMIT && !b.pixels);
  free(pages); exr_pdf_close(file); free(data);
}
static void mask_controls(const char *dir) {
  exr_pdf_file *file=NULL;exr_pdf_page_info *pages=NULL;size_t count,size,work=0;uint32_t mask,states,id;
  unsigned char *data=load(dir,"pdf-blend/mask-function-alpha-calculator-128.pdf",&size),*pixels=NULL;
  exr_control control={0};double matrix[6]={1,0,0,1,0,0};
  OK(exr_pdf_open(data,size,&file,&error));OK(exr_pdf_pages(file,&pages,&count,&error));CHECK(count==1);
  OK(exr_pdf_resolve(file,exr_pdf_get(file,pages[0].resources,"ExtGState"),&states,&error));
  OK(exr_pdf_resolve(file,exr_pdf_get(file,states,"M"),&id,&error));
  OK(exr_pdf_resolve(file,exr_pdf_get(file,id,"SMask"),&mask,&error));
  OK(exr_pdf_soft_mask_build(file,mask,matrix,16,16,&pixels,&work,NULL,NULL,&error));CHECK(work>256);free(pixels);pixels=NULL;
  { size_t used=256u*1024u*1024u-work+1;
    CHECK(exr_pdf_soft_mask_build(file,mask,matrix,16,16,&pixels,&used,NULL,NULL,&error)==EXR_LIMIT && !pixels);
    CHECK(strstr(error.message,"soft mask samples exceed work budget"));
  }
  work=256u*1024u*1024u;CHECK(exr_pdf_soft_mask_build(file,mask,matrix,16,16,&pixels,&work,NULL,NULL,&error)==EXR_LIMIT && !pixels);
  control.cancelled=cancelled;work=0;
  CHECK(exr_pdf_soft_mask_build(file,mask,matrix,16,16,&pixels,&work,NULL,&control,&error)==EXR_CANCELLED && !pixels);
  free(pages);exr_pdf_close(file);free(data);
}
static void mask_recursion_budget(const char *dir) {
  exr_pdf_file *file=NULL;exr_pdf_page_info *pages=NULL;size_t count,size;uint32_t states,id,mask;
  unsigned char *data=load(dir,"render-audit/mask-cycle.pdf",&size),*pixels=NULL;double matrix[6]={1,0,0,1,0,0};
  const size_t held[]={60u*1024u*1024u,64u*1024u*1024u,64u*1024u*1024u+1};unsigned i;
  OK(exr_pdf_open(data,size,&file,&error));OK(exr_pdf_pages(file,&pages,&count,&error));CHECK(count==1);
  OK(exr_pdf_resolve(file,exr_pdf_get(file,pages[0].resources,"ExtGState"),&states,&error));
  OK(exr_pdf_resolve(file,exr_pdf_get(file,states,"GS"),&id,&error));
  OK(exr_pdf_resolve(file,exr_pdf_get(file,id,"SMask"),&mask,&error));
  for(i=0;i<3;i++) {
    size_t active=held[i],work=0;
    CHECK(exr_pdf_soft_mask_build(file,mask,matrix,1024,1024,&pixels,&work,&active,NULL,&error)==EXR_LIMIT && !pixels);
    CHECK(strstr(error.message,"active soft masks exceed 64 MiB"));CHECK(active==held[i]);
  }
  free(pages);exr_pdf_close(file);free(data);
}
static exr_status shading_count(void *ctx,const exr_bitmap *bitmap,const exr_bitmap *inks,const double matrix[6],const exr_pdf_paint_state *paint,exr_error *e) {
  unsigned *count=ctx;(void)inks;(void)matrix;(void)paint;(void)e;
  CHECK(bitmap && bitmap->pixels);(*count)++;return EXR_OK;
}
static void shading_budget(const char *dir,const char *name) {
  exr_pdf_file *file=NULL;exr_pdf_page_info *pages=NULL;size_t count,size,work=0;uint32_t shadings,id;
  unsigned emits=0;exr_pdf_paint_state paint={0};exr_control control={0};double matrix[6]={1,0,0,1,0,0};
  unsigned char *data=load(dir,name,&size);
  OK(exr_pdf_open(data,size,&file,&error));OK(exr_pdf_pages(file,&pages,&count,&error));CHECK(count==1);
  OK(exr_pdf_resolve(file,exr_pdf_get(file,pages[0].resources,"Shading"),&shadings,&error));
  OK(exr_pdf_resolve(file,exr_pdf_get(file,shadings,"Sh"),&id,&error));
  OK(exr_pdf_shading_draw(file,file,pages[0].resources,id,matrix,&paint,&work,shading_count,&emits,0,NULL,&error));CHECK(emits==1 && work>512);
  { size_t near_limit=256u*1024u*1024u-work/2;emits=0;
    CHECK(exr_pdf_shading_draw(file,file,pages[0].resources,id,matrix,&paint,&near_limit,shading_count,&emits,0,NULL,&error)==EXR_LIMIT);
    CHECK(!emits && strstr(error.message,"shading samples exceed work budget"));
  }
  work=256u*1024u*1024u;emits=0;
  CHECK(exr_pdf_shading_draw(file,file,pages[0].resources,id,matrix,&paint,&work,shading_count,&emits,0,NULL,&error)==EXR_LIMIT && !emits);
  control.cancelled=cancelled;work=0;
  CHECK(exr_pdf_shading_draw(file,file,pages[0].resources,id,matrix,&paint,&work,shading_count,&emits,0,&control,&error)==EXR_CANCELLED && !emits);
  { exr_pdf_raster_config config={0};exr_bitmap b={0};const char *content="/Sh sh";size_t total=0;
    config.width=config.height=16;config.channels=4;config.work=&total;
    OK(exr_pdf_raster_content(file,pages[0].resources,content,strlen(content),NULL,&config,NULL,&b,&error));
    CHECK(total>512);free(b.pixels);
    total=256u*1024u*1024u-1;
    CHECK(exr_pdf_raster_content(file,pages[0].resources,content,strlen(content),NULL,&config,NULL,&b,&error)==EXR_LIMIT && !b.pixels);
    CHECK(strstr(error.message,"shading samples exceed work budget"));
  }
  free(pages);exr_pdf_close(file);free(data);
}
typedef struct { unsigned depth,saves,restores,clips,shadings,fail; } shading_scope;
static exr_status shading_native_inks(void *ctx,const exr_bitmap *bitmap,const exr_bitmap *inks,const double matrix[6],const exr_pdf_paint_state *paint,exr_error *e) {
  const unsigned char expected[4]={64,128,191,32};unsigned *emits=ctx;(void)matrix;(void)paint;(void)e;
  CHECK(bitmap && inks && inks->pixels && bitmap->width==inks->width && bitmap->height==inks->height && inks->channels==4);
  for(unsigned y=0;y<inks->height;y++) for(unsigned x=0;x<inks->width;x++) CHECK(!memcmp(inks->pixels+(size_t)y*inks->stride+x*4,expected,4));
  (*emits)++;return EXR_OK;
}
static void function_inks(const char *dir) {
  exr_pdf_file *file=NULL;exr_pdf_page_info *pages=NULL;size_t size,count,work=0;uint32_t shadings,id;unsigned emits=0;
  exr_pdf_paint_state paint={0};double matrix[6]={1,0,0,1,0,0};unsigned char *data=load(dir,"pdf-color/shading-function-inks.pdf",&size);
  OK(exr_pdf_open(data,size,&file,&error));OK(exr_pdf_pages(file,&pages,&count,&error));
  OK(exr_pdf_resolve(file,exr_pdf_get(file,pages[0].resources,"Shading"),&shadings,&error));
  OK(exr_pdf_resolve(file,exr_pdf_get(file,shadings,"Sh"),&id,&error));
  OK(exr_pdf_shading_draw(file,file,pages[0].resources,id,matrix,&paint,&work,shading_native_inks,&emits,1,NULL,&error));CHECK(emits==1);
  free(pages);exr_pdf_close(file);free(data);
}
static exr_status scope_state(void *ctx,exr_draw_state state,exr_error *e) {
  shading_scope *s=ctx;(void)e;
  if(state==EXR_DRAW_SAVE) { s->saves++;s->depth++; }
  else if(state==EXR_DRAW_RESTORE) { CHECK(s->depth);s->restores++;s->depth--; }
  return EXR_OK;
}
static exr_status scope_clip(void *ctx,const exr_path_segment *p,size_t n,const double m[6],exr_fill_rule rule,unsigned accumulate,exr_error *e) {
  shading_scope *s=ctx;(void)m;(void)e;CHECK(p && n==5 && rule==EXR_FILL_NONZERO && !accumulate && s->depth==1);s->clips++;
  return s->fail==1 ? EXR_CANCELLED : EXR_OK;
}
static exr_status scope_shading(void *ctx,const exr_bitmap *b,const double m[6],exr_error *e) {
  shading_scope *s=ctx;(void)m;(void)e;CHECK(b && b->pixels && s->depth==1);s->shadings++;
  return s->fail==2 ? EXR_CANCELLED : EXR_OK;
}
static void shading_cleanup(const char *dir) {
  exr_pdf_file *file=NULL;exr_pdf_page_info *pages=NULL;size_t size,count;
  unsigned char *data=load(dir,"pdf-color/shading-geometry-8.pdf",&size);exr_draw_sink_ex sink={0};
  OK(exr_pdf_open(data,size,&file,&error));OK(exr_pdf_pages(file,&pages,&count,&error));
  sink.struct_size=sizeof(sink);sink.base.state=scope_state;sink.base.clip=scope_clip;sink.shading=scope_shading;
  for(unsigned fail=0;fail<3;fail++) {
    shading_scope s={0};s.fail=fail;sink.base.context=&s;
    CHECK(exr_pdf_paint_content_ex(file,pages[0].resources,"/Sh sh",6,NULL,&sink,NULL,NULL,NULL,NULL,NULL,&error)==(fail ? EXR_CANCELLED : EXR_OK));
    CHECK(s.saves==1 && s.restores==1 && !s.depth && s.clips==1 && s.shadings==(fail!=1));
  }
  free(pages);exr_pdf_close(file);free(data);
}
int main(int argc,char **argv) {
  unsigned char *data; size_t size; exr_pdf_file *file=NULL; uint32_t resources; exr_bitmap b; exr_pdf_raster_config config={0}; exr_control control={0};
  CHECK(argc==2); page_cases(argv[1]);mask_controls(argv[1]);mask_recursion_budget(argv[1]);
  shading_budget(argv[1],"pdf-color/shading-domain-0.pdf");shading_budget(argv[1],"pdf-color/shading-function-0.pdf");
  shading_budget(argv[1],"pdf-color/shading-function-4.pdf");shading_budget(argv[1],"pdf-color/shading-function-7.pdf");
  shading_cleanup(argv[1]);function_inks(argv[1]); data=load(argv[1],"pdf-outlines.pdf",&size); OK(exr_pdf_open(data,size,&file,&error)); OK(exr_pdf_resolve(file,exr_pdf_get(file,exr_pdf_root(file),"Resources"),&resources,&error));
  text_cases(file,resources); clip_cases(file,resources); fallback_cases(argv[1],file,resources); drawing_inspection(file,resources);
  config.width=config.height=12; config.channels=4; config.background=0;
  { const char *s="1 0 0 rg 1 1 2 2 re f"; OK(exr_pdf_raster_content(file,resources,s,strlen(s),NULL,&config,NULL,&b,&error)); CHECK(b.pixels[13*4]==255 && b.pixels[13*4+3]==255 && !b.pixels[3]); free(b.pixels); }
  { size_t aggregate=256u*1024u*1024u;const char *s="0 0 12 12 re f";config.work=&aggregate;
    CHECK(exr_pdf_raster_content(file,resources,s,strlen(s),NULL,&config,NULL,&b,&error)==EXR_LIMIT && !b.pixels);
    CHECK(aggregate>=256u*1024u*1024u);config.work=NULL;
  }
  config.width=0; CHECK(exr_pdf_raster_content(file,resources,"",0,NULL,&config,NULL,&b,&error)==EXR_ARGUMENT && !b.pixels);
  config.width=12; control.cancelled=cancelled; CHECK(exr_pdf_raster_content(file,resources,"",0,NULL,&config,&control,&b,&error)==EXR_CANCELLED && !b.pixels);
  { double clip[4]={0,0,12,12}; config.initial_clip=clip;
    clip[0]=NAN; CHECK(exr_pdf_raster_content(file,resources,"",0,NULL,&config,NULL,&b,&error)==EXR_ARGUMENT && !b.pixels);
    clip[0]=13; CHECK(exr_pdf_raster_content(file,resources,"",0,NULL,&config,NULL,&b,&error)==EXR_ARGUMENT && !b.pixels);
    clip[0]=0; config.mask_budget=143; CHECK(exr_pdf_raster_content(file,resources,"",0,NULL,&config,NULL,&b,&error)==EXR_LIMIT && !b.pixels);
    config.initial_clip=NULL; config.mask_budget=0;
  }
  exr_pdf_close(file); free(data);
  data=load(argv[1],"pdf-graphics.pdf",&size); OK(exr_pdf_open(data,size,&file,&error)); OK(exr_pdf_resolve(file,exr_pdf_get(file,exr_pdf_root(file),"Pages"),&resources,&error));
  { uint32_t kids,page; OK(exr_pdf_resolve(file,exr_pdf_get(file,resources,"Kids"),&kids,&error)); OK(exr_pdf_resolve(file,exr_pdf_value_at(file,kids)->first,&page,&error)); OK(exr_pdf_resolve(file,exr_pdf_get(file,page,"Resources"),&resources,&error)); }
  b=render(file,resources,"0 1 0 rg /Filled Do 0 0 1 1 re f",4,0); pixel(&b,2,3,255,0,0); pixel(&b,0,0,0,255,0); pixel(&b,4,4,255,255,255); free(b.pixels);
  { const char *s="/Image Do"; OK(exr_pdf_raster_content(file,resources,s,strlen(s),NULL,&config,NULL,&b,&error)); pixel(&b,0,0,0,0,0); free(b.pixels); }
  exr_pdf_close(file); free(data); printf("%u native PDF raster checks passed\n",checks); return 0;
}
