/* SPDX-License-Identifier: MIT */
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
int main(int argc,char **argv) {
  unsigned char *data; size_t size; exr_pdf_file *file=NULL; uint32_t resources; exr_bitmap b; exr_pdf_raster_config config={0}; exr_control control={0};
  CHECK(argc==2); page_cases(argv[1]); data=load(argv[1],"pdf-outlines.pdf",&size); OK(exr_pdf_open(data,size,&file,&error)); OK(exr_pdf_resolve(file,exr_pdf_get(file,exr_pdf_root(file),"Resources"),&resources,&error));
  text_cases(file,resources); clip_cases(file,resources); fallback_cases(argv[1],file,resources); drawing_inspection(file,resources);
  config.width=config.height=12; config.channels=4; config.background=0;
  { const char *s="1 0 0 rg 1 1 2 2 re f"; OK(exr_pdf_raster_content(file,resources,s,strlen(s),NULL,&config,NULL,&b,&error)); CHECK(b.pixels[13*4]==255 && b.pixels[13*4+3]==255 && !b.pixels[3]); free(b.pixels); }
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
