/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks;static exr_error error;
#define CHECK(x) do { checks++;if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message);exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static const char *directory;
static void rect(exr_path_segment p[5],double width,double height) {
  memset(p,0,5*sizeof(*p));p[0].verb=EXR_PATH_MOVE;p[1].verb=p[2].verb=p[3].verb=EXR_PATH_LINE;p[4].verb=EXR_PATH_CLOSE;
  p[1].points[0].x=width;p[2].points[0]=(exr_path_point){width,height};p[3].points[0].y=height;
}
static unsigned char *load(const char *name,size_t *size) {
  char path[4096];FILE *f;long n;unsigned char *data;
  snprintf(path,sizeof(path),"%s/%s",directory,name);f=fopen(path,"rb");CHECK(f && !fseek(f,0,SEEK_END));n=ftell(f);CHECK(n>0 && n<4*1024*1024);rewind(f);
  *size=(size_t)n;data=malloc(*size);CHECK(data && fread(data,1,*size,f)==*size);fclose(f);return data;
}
static exr_fixed_document *open_book(const char *name) {
  char path[4096];exr_fixed_document *d=NULL;snprintf(path,sizeof(path),"%s/%s.pdf",directory,name);OK(exr_fixed_open(path,NULL,&d,&error));CHECK(d);return d;
}
static exr_canvas *canvas(unsigned width,unsigned height,uint32_t background) {
  exr_canvas_config config={0};exr_canvas *c=NULL;config.width=width;config.height=height;config.background=background;OK(exr_canvas_create(&config,&c,&error));return c;
}
static void references(void) {
  const char *names[]={"flat","primitives","state","groups","compound","ap-groups","nonisolated","ap-nonisolated","knockout","knockout-nonisolated","knockout-shapes"};unsigned test,alpha;
  for(test=0;test<sizeof(names)/sizeof(*names);test++) {
    exr_fixed_document *d=open_book(names[test]);size_t page_count,mask_size;const exr_fixed_page *pages=exr_fixed_pages(d,&page_count);char name[64];unsigned char *mask;
    CHECK(page_count==1);snprintf(name,sizeof(name),"%s.mask",names[test]);mask=load(name,&mask_size);
    for(alpha=0;alpha<2;alpha++) {
      exr_fixed_render_options options={0};exr_bitmap result={0},replayed={0};exr_canvas *c;exr_draw_sink_ex sink={0};exr_viewport view;size_t size,i;unsigned char *expected;unsigned maximum=0;
      options.channels=4;options.background=alpha ? 0 : 0xffffffff;OK(exr_fixed_render(d,0,1,&options,&result,&error));CHECK(mask_size==(size_t)result.width*result.height);
      snprintf(name,sizeof(name),"%s-%s.rgba",names[test],alpha ? "alpha" : "white");expected=load(name,&size);CHECK(size==mask_size*4);
      for(i=0;i<mask_size;i++) if(mask[i]) {
        unsigned k;const unsigned char *p=result.pixels+(i/result.width)*result.stride+(i%result.width)*4;
        for(k=0;k<4;k++) {
          unsigned actual=alpha && k<3 ? (p[k]*p[3]+127)/255 : p[k];unsigned want=expected[4*i+k],diff=actual>want ? actual-want : want-actual;
          if(diff>maximum) maximum=diff;
          if(diff>3) fprintf(stderr,"%s alpha%u pixel %zu,%zu channel%u actual%u oracle%u\n",names[test],alpha,i%result.width,i/result.width,k,actual,want);
          CHECK(diff<=3);
        }
      }
      fprintf(stderr,"%s alpha%u maximum premultiplied difference %u\n",names[test],alpha,maximum);
      c=canvas(result.width,result.height,options.background);sink.struct_size=sizeof(sink);OK(exr_canvas_get_sink_ex(c,&sink,&error));OK(exr_viewport_create(&pages[0].geometry,1,&view,&error));
      OK(exr_fixed_draw_ex(d,0,view.matrix,&sink,NULL,&error));OK(exr_canvas_take(c,&replayed,&error));CHECK(result.stride==replayed.stride && !memcmp(result.pixels,replayed.pixels,(size_t)result.stride*result.height));
      exr_canvas_free(c);exr_bitmap_free(&replayed);
      if(!alpha) {
        exr_bitmap gray={0};options.channels=1;OK(exr_fixed_render(d,0,1,&options,&gray,&error));CHECK(gray.channels==1 && gray.width==result.width && gray.height==result.height);
        for(i=0;i<mask_size;i++) { const unsigned char *p=result.pixels+(i/result.width)*result.stride+(i%result.width)*4;CHECK(gray.pixels[i]==(77*p[0]+150*p[1]+29*p[2]+128)/256); }
        exr_bitmap_free(&gray);
      }
      exr_bitmap_free(&result);free(expected);
    }
    exr_fixed_free(d);free(mask);
  }
}
typedef struct {size_t paths,blends,begins,ends;unsigned modes[16];int fail;} inspect;
static exr_status path(void *context,const exr_path_segment *segments,size_t count,const double matrix[6],const exr_draw_style *style,exr_error *e) {
  inspect *i=context;(void)segments;(void)count;(void)matrix;(void)style;(void)e;i->paths++;return EXR_OK;
}
static exr_status blend(void *context,exr_blend_mode mode,exr_error *e) {
  inspect *i=context;CHECK(mode>=EXR_BLEND_NORMAL && mode<=EXR_BLEND_LUMINOSITY);i->blends++;i->modes[mode]++;
  if(i->fail) { e->code=EXR_CANCELLED;strcpy(e->message,"Blend consumer stopped"); }return EXR_OK;
}
static exr_status begin_layer(void *context,double opacity,exr_blend_mode mode,exr_error *e) {
  inspect *i=context;(void)opacity;(void)mode;(void)e;i->begins++;return EXR_OK;
}
static exr_status begin_group(void *context,double opacity,exr_blend_mode mode,unsigned flags,exr_error *e) {
  CHECK(!(flags&~EXR_GROUP_ISOLATED));return begin_layer(context,opacity,mode,e);
}
static exr_status end_layer(void *context,unsigned commit,exr_error *e) {
  inspect *i=context;(void)commit;(void)e;i->ends++;return EXR_OK;
}
static void consumers(void) {
  exr_fixed_document *d=open_book("flat");exr_draw_sink_ex sink={0};inspect state={0};exr_bitmap b={0};unsigned i;
  sink.struct_size=sizeof(sink);sink.base.path=path;sink.base.context=&state;sink.blend=blend;sink.begin_layer=begin_layer;sink.end_layer=end_layer;
  OK(exr_fixed_draw_ex(d,0,NULL,&sink,NULL,&error));CHECK(state.paths && state.blends==state.paths && state.begins==state.ends);
  for(i=0;i<16;i++) CHECK(state.modes[i]>0);
  CHECK(exr_fixed_draw(d,0,NULL,&sink.base,NULL,&error)==EXR_FORMAT);
  memset(&state,0,sizeof(state));state.fail=1;CHECK(exr_fixed_draw_ex(d,0,NULL,&sink,NULL,&error)==EXR_CANCELLED && !state.paths && error.code==EXR_CANCELLED);
  OK(exr_fixed_render(d,0,1,NULL,&b,&error));exr_bitmap_free(&b);
  { struct {exr_draw_sink_ex sink;unsigned char tail[8];} future={0};future.sink=sink;future.sink.struct_size=sizeof(future);future.tail[0]=1;
    CHECK(exr_fixed_draw_ex(d,0,NULL,&future.sink,NULL,&error)==EXR_ARGUMENT);
  }
  { union {exr_draw_sink_ex aligned;unsigned char bytes[sizeof(sink)];} storage={0};unsigned char *raw=storage.bytes;size_t offset=offsetof(exr_draw_sink_ex,blend);exr_draw_sink_ex *truncated=&storage.aligned;
    memcpy(raw,&sink,offset);truncated->struct_size=offset+1;raw[offset]=1;CHECK(exr_fixed_draw_ex(d,0,NULL,truncated,NULL,&error)==EXR_ARGUMENT);
  }
  { exr_draw_sink_ex missing=sink;missing.end_layer=NULL;CHECK(exr_fixed_draw_ex(d,0,NULL,&missing,NULL,&error)==EXR_ARGUMENT); }
  exr_fixed_free(d);
  d=open_book("nonisolated");memset(&state,0,sizeof(state));
  CHECK(exr_fixed_draw_ex(d,0,NULL,&sink,NULL,&error)==EXR_UNSUPPORTED);CHECK(state.begins==state.ends);exr_fixed_free(d);
  /* Knockout needs the size-tagged begin_group; a begin_layer-only consumer must refuse. */
  d=open_book("knockout");memset(&state,0,sizeof(state));
  CHECK(exr_fixed_draw_ex(d,0,NULL,&sink,NULL,&error)==EXR_UNSUPPORTED);CHECK(state.begins==state.ends);exr_fixed_free(d);
  memset(&state,0,sizeof(state));sink.begin_group=begin_group;sink.begin_layer=NULL;
  d=open_book("nonisolated");OK(exr_fixed_draw_ex(d,0,NULL,&sink,NULL,&error));CHECK(state.begins==state.ends && state.paths);exr_fixed_free(d);
  d=open_book("group-malformed");memset(&state,0,sizeof(state));
  CHECK(exr_fixed_draw_ex(d,0,NULL,&sink,NULL,&error)==EXR_FORMAT);CHECK(state.begins==2 && state.ends==2);exr_fixed_free(d);
}
static int cancelled(void *context) {return *(int *)context;}
static void direct(void) {
  unsigned mode;exr_path_segment p[5];rect(p,1,1);
  for(mode=0;mode<16;mode++) {
    exr_canvas *c=canvas(1,1,0xffffff00);exr_draw_style style=exr_draw_style_defaults();const unsigned char *pixel;
    style.fill=0x49a2ef80;OK(exr_canvas_blend(c,(exr_blend_mode)mode,&error));OK(exr_canvas_path(c,p,5,NULL,&style,&error));pixel=exr_canvas_bitmap(c)->pixels;
    CHECK(pixel[0]==0x49 && pixel[1]==0xa2 && pixel[2]==0xef && pixel[3]==128);exr_canvas_free(c);
  }
  { exr_canvas *c=canvas(1,1,0x808080ff);exr_draw_style style=exr_draw_style_defaults();exr_image_layer image={0};unsigned char px[]={128,128,128,128};const exr_bitmap *b;double m[]={1,0,0,1,0,0};
    OK(exr_canvas_blend(c,EXR_BLEND_MULTIPLY,&error));OK(exr_canvas_save(c,&error));OK(exr_canvas_blend(c,EXR_BLEND_SCREEN,&error));OK(exr_canvas_restore(c,&error));
    image.bitmap=(exr_bitmap){1,1,4,px,4};OK(exr_canvas_image(c,&image,m,1,&error));b=exr_canvas_bitmap(c);CHECK(b->pixels[0]==96 && b->pixels[1]==96 && b->pixels[2]==96);
    /* Clip construction uses coverage union, independent of current blend. */
    OK(exr_canvas_clip(c,p,5,NULL,EXR_FILL_NONZERO,&error));OK(exr_canvas_blend(c,EXR_BLEND_SCREEN,&error));style.fill=0xffffffff;OK(exr_canvas_path(c,p,5,NULL,&style,&error));CHECK(exr_canvas_bitmap(c)->pixels[0]==255);exr_canvas_free(c);
  }
  { typedef struct {size_t struct_size;exr_draw_sink base;} prefix;struct {prefix sink;unsigned char guard[16];} memory;
    exr_canvas *c=canvas(1,1,0xffffffff);size_t i;memset(&memory,0xa5,sizeof(memory));memory.sink.struct_size=sizeof(prefix);
    OK(exr_canvas_get_sink_ex(c,(exr_draw_sink_ex *)(void *)&memory.sink,&error));CHECK(memory.sink.struct_size==sizeof(prefix));
    for(i=0;i<sizeof(memory.guard);i++) CHECK(memory.guard[i]==0xa5);exr_canvas_free(c);
  }
  { typedef struct {size_t struct_size;exr_draw_sink base;exr_draw_blend_fn blend;exr_draw_layer_begin_fn begin_layer;exr_draw_layer_end_fn end_layer;} old_sink;
    struct {old_sink sink;unsigned char guard[16];} memory;exr_canvas *c=canvas(1,1,0);size_t i;
    memset(&memory,0xa5,sizeof(memory));memory.sink.struct_size=sizeof(memory.sink);OK(exr_canvas_get_sink_ex(c,(exr_draw_sink_ex *)(void *)&memory.sink,&error));
    CHECK(memory.sink.struct_size==sizeof(memory.sink) && memory.sink.begin_layer && memory.sink.end_layer);
    for(i=0;i<16;i++) CHECK(memory.guard[i]==0xa5);exr_canvas_free(c);
  }
  { exr_canvas *c=canvas(1,1,0);exr_bitmap output={0};CHECK(exr_canvas_blend(c,(exr_blend_mode)16,&error)==EXR_ARGUMENT);CHECK(!exr_canvas_bitmap(c));CHECK(exr_canvas_take(c,&output,&error)==EXR_ARGUMENT && !output.pixels);exr_canvas_free(c); }
  { int stop=0;exr_canvas_config cfg={0};exr_canvas *c=NULL;exr_bitmap output={0};cfg.width=cfg.height=1;cfg.control.cancelled=cancelled;cfg.control.context=&stop;
    OK(exr_canvas_create(&cfg,&c,&error));stop=1;CHECK(exr_canvas_blend(c,EXR_BLEND_MULTIPLY,&error)==EXR_CANCELLED);CHECK(exr_canvas_take(c,&output,&error)==EXR_CANCELLED && !output.pixels);exr_canvas_free(c);
  }
}
static void analytic(void) {
  exr_path_segment p[5];exr_draw_style style=exr_draw_style_defaults();rect(p,1,1);
  { const unsigned char expected[3][3]={{41,31,16},{214,148,163},{68,119,170}};
    const exr_blend_mode modes[]={EXR_BLEND_MULTIPLY,EXR_BLEND_SCREEN,EXR_BLEND_LUMINOSITY};unsigned i,k;
    for(i=0;i<3;i++) {
      exr_canvas *c=canvas(1,1,0x336699ff);style.fill=0xcc4d1aff;OK(exr_canvas_blend(c,modes[i],&error));OK(exr_canvas_path(c,p,5,NULL,&style,&error));
      for(k=0;k<3;k++) CHECK(exr_canvas_bitmap(c)->pixels[k]==expected[i][k]);exr_canvas_free(c);
    }
  }
  { exr_canvas *c=canvas(1,1,0x11ff7f80);const unsigned char *px;unsigned k;const unsigned expected[]={92,97,40};
    style.fill=0xf01f00c0;OK(exr_canvas_blend(c,EXR_BLEND_LUMINOSITY,&error));OK(exr_canvas_path(c,p,5,NULL,&style,&error));px=exr_canvas_bitmap(c)->pixels;
    CHECK(px[3]==224);for(k=0;k<3;k++) { unsigned v=(px[k]*px[3]+127)/255;CHECK(v+1>=expected[k] && v<=expected[k]+1); }exr_canvas_free(c);
  }
  { exr_canvas_config config={0};exr_canvas *c=NULL;exr_bitmap b={0};config.width=config.height=1;config.mask_budget=1;
    OK(exr_canvas_create(&config,&c,&error));style.flags=EXR_DRAW_FILL|EXR_DRAW_STROKE;
    CHECK(exr_canvas_path(c,p,5,NULL,&style,&error)==EXR_LIMIT);CHECK(exr_canvas_take(c,&b,&error)==EXR_LIMIT && !b.pixels);exr_canvas_free(c);
  }
}
static void layers(void) {
  exr_path_segment p[5];exr_draw_style style=exr_draw_style_defaults();rect(p,1,1);style.fill=0xff0000ff;
  { exr_canvas *c=canvas(1,1,0x0000ffff);size_t baseline=exr_canvas_memory_size(c);const unsigned char *px;
    OK(exr_canvas_blend(c,EXR_BLEND_MULTIPLY,&error));OK(exr_canvas_begin_layer(c,.5,EXR_BLEND_NORMAL,&error));
    CHECK(exr_canvas_memory_size(c)>baseline);OK(exr_canvas_path(c,p,5,NULL,&style,&error));OK(exr_canvas_path(c,p,5,NULL,&style,&error));
    OK(exr_canvas_begin_layer(c,1,EXR_BLEND_SCREEN,&error));style.fill=0x00ff00ff;OK(exr_canvas_path(c,p,5,NULL,&style,&error));OK(exr_canvas_end_layer(c,0,&error));
    OK(exr_canvas_end_layer(c,1,&error));px=exr_canvas_bitmap(c)->pixels;CHECK(px[0]==128 && px[1]==0 && px[2]==127 && px[3]==255);
    style.fill=0x00ff00ff;OK(exr_canvas_path(c,p,5,NULL,&style,&error));CHECK(exr_canvas_bitmap(c)->pixels[0]==0 && exr_canvas_bitmap(c)->pixels[1]==0);exr_canvas_free(c);
  }
  { exr_canvas *c=canvas(1,1,0);const unsigned char *px;
    rect(p,.5,1);OK(exr_canvas_clip(c,p,5,NULL,EXR_FILL_NONZERO,&error));rect(p,1,1);
    OK(exr_canvas_begin_layer(c,1,EXR_BLEND_NORMAL,&error));style.fill=0xff0000ff;OK(exr_canvas_path(c,p,5,NULL,&style,&error));
    OK(exr_canvas_begin_layer(c,1,EXR_BLEND_NORMAL,&error));OK(exr_canvas_path(c,p,5,NULL,&style,&error));OK(exr_canvas_end_layer(c,1,&error));OK(exr_canvas_end_layer(c,1,&error));
    px=exr_canvas_bitmap(c)->pixels;CHECK(px[0]==255 && px[3]>=126 && px[3]<=129);exr_canvas_free(c);
  }
  { exr_canvas *c=canvas(1,1,0);exr_draw_sink sink={0};const unsigned char *px;
    OK(exr_canvas_get_sink(c,&sink,&error));OK(sink.state(c,EXR_DRAW_BEGIN_CLIP,&error));rect(p,.5,1);OK(sink.clip(c,p,5,NULL,EXR_FILL_NONZERO,1,&error));
    OK(sink.state(c,EXR_DRAW_BEGIN_CLIP,&error));OK(sink.clip(c,p,5,NULL,EXR_FILL_NONZERO,1,&error));
    OK(exr_canvas_begin_layer(c,1,EXR_BLEND_NORMAL,&error));OK(sink.state(c,EXR_DRAW_BEGIN_CLIP,&error));OK(sink.clip(c,p,5,NULL,EXR_FILL_NONZERO,1,&error));
    OK(exr_canvas_save(c,&error));OK(exr_canvas_end_layer(c,0,&error));
    OK(sink.state(c,EXR_DRAW_END_CLIP,&error));OK(sink.state(c,EXR_DRAW_END_CLIP,&error));rect(p,1,1);OK(exr_canvas_path(c,p,5,NULL,&style,&error));
    px=exr_canvas_bitmap(c)->pixels;CHECK(px[0]==255 && px[3]>=62 && px[3]<=65);exr_canvas_free(c);
  }
  { exr_canvas *c=canvas(1,1,0);unsigned i;OK(exr_canvas_set_layer_budget(c,128,&error));
    for(i=0;i<32;i++) OK(exr_canvas_begin_layer(c,1,EXR_BLEND_NORMAL,&error));
    CHECK(exr_canvas_begin_layer(c,1,EXR_BLEND_NORMAL,&error)==EXR_LIMIT);
    for(i=0;i<32;i++) CHECK(exr_canvas_end_layer(c,0,&error)==EXR_LIMIT);exr_canvas_free(c);
  }
  { exr_canvas *c=canvas(2,2,0);OK(exr_canvas_set_layer_budget(c,15,&error));CHECK(exr_canvas_begin_layer(c,1,EXR_BLEND_NORMAL,&error)==EXR_LIMIT);exr_canvas_free(c); }
  { exr_canvas *c=canvas(1,1,0);exr_bitmap b={0};OK(exr_canvas_save(c,&error));OK(exr_canvas_begin_layer(c,1,EXR_BLEND_NORMAL,&error));
    CHECK(exr_canvas_restore(c,&error)==EXR_ARGUMENT);CHECK(exr_canvas_end_layer(c,0,&error)==EXR_ARGUMENT);CHECK(exr_canvas_take(c,&b,&error)==EXR_ARGUMENT && !b.pixels);exr_canvas_free(c);
  }
  { exr_canvas *c=canvas(1,1,0);OK(exr_canvas_begin_layer(c,1,EXR_BLEND_NORMAL,&error));OK(exr_canvas_save(c,&error));CHECK(exr_canvas_end_layer(c,1,&error)==EXR_ARGUMENT);exr_canvas_free(c); }
  { exr_canvas *c=canvas(1,1,0);exr_bitmap b={0};OK(exr_canvas_begin_layer(c,1,EXR_BLEND_NORMAL,&error));CHECK(exr_canvas_take(c,&b,&error)==EXR_ARGUMENT && !b.pixels);CHECK(exr_canvas_end_layer(c,0,&error)==EXR_ARGUMENT);exr_canvas_free(c); }
  { int stop=0;exr_canvas_config cfg={0};exr_canvas *c=NULL;cfg.width=cfg.height=1;cfg.control.cancelled=cancelled;cfg.control.context=&stop;
    OK(exr_canvas_create(&cfg,&c,&error));OK(exr_canvas_begin_layer(c,1,EXR_BLEND_NORMAL,&error));stop=1;CHECK(exr_canvas_end_layer(c,1,&error)==EXR_CANCELLED);exr_canvas_free(c);
  }
}
static int cancel_during_copy(void *context) { return ++*(int *)context>3; }
static void nonisolated(void) {
  const unsigned alphas[]={0,1,64,128,255};unsigned mode,row;exr_path_segment p[5];exr_draw_style style=exr_draw_style_defaults();rect(p,1,1);
  for(mode=0;mode<16;mode++) for(row=0;row<sizeof(alphas)/sizeof(*alphas);row++) {
    exr_canvas *direct=canvas(1,1,0x33669900|alphas[row]),*group=canvas(1,1,0x33669900|alphas[row]);unsigned i,k;
    OK(exr_canvas_begin_group(group,1,EXR_BLEND_NORMAL,0,&error));
    for(i=0;i<2;i++) {
      style.fill=i ? 0x1fc8a040 : 0xcc4d1a80;OK(exr_canvas_blend(direct,(exr_blend_mode)mode,&error));OK(exr_canvas_blend(group,(exr_blend_mode)mode,&error));
      OK(exr_canvas_path(direct,p,5,NULL,&style,&error));OK(exr_canvas_path(group,p,5,NULL,&style,&error));
    }
    OK(exr_canvas_end_layer(group,1,&error));
    for(k=0;k<4;k++) {
      const unsigned char *d=exr_canvas_bitmap(direct)->pixels,*g=exr_canvas_bitmap(group)->pixels;
      unsigned dv=k<3 ? (d[k]*d[3]+127)/255 : d[k],gv=k<3 ? (g[k]*g[3]+127)/255 : g[k];CHECK(dv+2>=gv && gv+2>=dv);
    }
    exr_canvas_free(direct);exr_canvas_free(group);
  }
  { exr_canvas *c=canvas(1,1,0x336699ff);const unsigned char *px;OK(exr_canvas_begin_group(c,.5,EXR_BLEND_NORMAL,0,&error));
    OK(exr_canvas_blend(c,EXR_BLEND_MULTIPLY,&error));style.fill=0xcc4d1a80;OK(exr_canvas_path(c,p,5,NULL,&style,&error));OK(exr_canvas_end_layer(c,1,&error));
    px=exr_canvas_bitmap(c)->pixels;CHECK(px[0]==48 && px[1]==84 && px[2]==119 && px[3]==255);exr_canvas_free(c);
  }
  { exr_canvas *c=canvas(1,1,0);unsigned i;OK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,0,&error));style.fill=0x0000ff01;
    for(i=0;i<1000;i++) OK(exr_canvas_path(c,p,5,NULL,&style,&error));OK(exr_canvas_end_layer(c,1,&error));
    CHECK(exr_canvas_bitmap(c)->pixels[2]==255 && exr_canvas_bitmap(c)->pixels[3]==250);exr_canvas_free(c);
  }
  { exr_canvas *c=canvas(1,1,0x33669980);size_t active,after;const unsigned char *px;
    OK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,0,&error));active=exr_canvas_memory_size(c);OK(exr_canvas_end_layer(c,1,&error));after=exr_canvas_memory_size(c);CHECK(active>=after+24);
    px=exr_canvas_bitmap(c)->pixels;CHECK(px[0]==51 && px[1]==102 && px[2]==153 && px[3]==128);
    OK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,0,&error));OK(exr_canvas_save(c,&error));style.fill=0xff0000ff;OK(exr_canvas_path(c,p,5,NULL,&style,&error));
    OK(exr_canvas_end_layer(c,0,&error));CHECK(exr_canvas_memory_size(c)==after);px=exr_canvas_bitmap(c)->pixels;CHECK(px[0]==51 && px[1]==102 && px[2]==153 && px[3]==128);exr_canvas_free(c);
  }
  { exr_canvas *c=canvas(1,1,0);OK(exr_canvas_set_layer_budget(c,27,&error));OK(exr_canvas_begin_layer(c,1,EXR_BLEND_NORMAL,&error));
    CHECK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,0,&error)==EXR_LIMIT);CHECK(exr_canvas_end_layer(c,0,&error)==EXR_LIMIT);exr_canvas_free(c);
  }
  { exr_canvas *c=canvas(1,1,0);unsigned i;style.fill=0x0000ff01;OK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,0,&error));
    for(i=0;i<1000;i++) { OK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,0,&error));OK(exr_canvas_path(c,p,5,NULL,&style,&error));OK(exr_canvas_end_layer(c,1,&error)); }
    OK(exr_canvas_end_layer(c,1,&error));CHECK(exr_canvas_bitmap(c)->pixels[2]==255 && exr_canvas_bitmap(c)->pixels[3]==250);exr_canvas_free(c);
  }
  { exr_canvas *c=canvas(1,1,0);unsigned i;for(i=0;i<32;i++) OK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,0,&error));
    style.fill=0xff000080;OK(exr_canvas_path(c,p,5,NULL,&style,&error));for(i=0;i<32;i++) OK(exr_canvas_end_layer(c,1,&error));
    CHECK(exr_canvas_bitmap(c)->pixels[0]==255 && exr_canvas_bitmap(c)->pixels[3]==128);exr_canvas_free(c);
  }
  { exr_canvas_config config={0};exr_canvas *c=NULL;int calls=0;config.width=config.height=2;config.control.cancelled=cancel_during_copy;config.control.context=&calls;
    OK(exr_canvas_create(&config,&c,&error));CHECK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,0,&error)==EXR_CANCELLED);CHECK(!exr_canvas_bitmap(c));exr_canvas_free(c);
  }
  { int stop=0;exr_canvas_config cfg={0};exr_canvas *c=NULL;cfg.width=cfg.height=1;cfg.control.cancelled=cancelled;cfg.control.context=&stop;
    OK(exr_canvas_create(&cfg,&c,&error));OK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,0,&error));stop=1;CHECK(exr_canvas_end_layer(c,1,&error)==EXR_CANCELLED);exr_canvas_free(c);
  }
  { exr_canvas *c=canvas(1,1,0x0000ffff);const unsigned char *px;rect(p,.5,1);OK(exr_canvas_clip(c,p,5,NULL,EXR_FILL_NONZERO,&error));rect(p,1,1);
    OK(exr_canvas_begin_group(c,.5,EXR_BLEND_NORMAL,0,&error));CHECK(exr_canvas_bitmap(c)->pixels[2]==255);style.fill=0xff0000ff;OK(exr_canvas_path(c,p,5,NULL,&style,&error));
    OK(exr_canvas_end_layer(c,1,&error));px=exr_canvas_bitmap(c)->pixels;CHECK(px[0]==64 && px[1]==0 && px[2]==191 && px[3]==255);exr_canvas_free(c);
  }
  { unsigned char pixels[]={204,77,26,255},mask_pixels[]={128,128,128,255};exr_image_layer image={0},mask={0};double m[]={1,0,0,1,0,0};unsigned k;
    exr_canvas *direct=canvas(1,1,0x336699c0),*group=canvas(1,1,0x336699c0);image.bitmap=(exr_bitmap){1,1,4,pixels,4};mask.bitmap=(exr_bitmap){1,1,4,mask_pixels,4};image.mask=&mask;image.mask_mode=EXR_MASK_GRAY;
    OK(exr_canvas_begin_group(group,1,EXR_BLEND_NORMAL,0,&error));OK(exr_canvas_blend(direct,EXR_BLEND_MULTIPLY,&error));OK(exr_canvas_blend(group,EXR_BLEND_MULTIPLY,&error));
    OK(exr_canvas_image(direct,&image,m,128./255,&error));OK(exr_canvas_image(group,&image,m,128./255,&error));OK(exr_canvas_end_layer(group,1,&error));
    for(k=0;k<4;k++) { const unsigned char *d=exr_canvas_bitmap(direct)->pixels,*g=exr_canvas_bitmap(group)->pixels;unsigned dv=k<3 ? (d[k]*d[3]+127)/255 : d[k],gv=k<3 ? (g[k]*g[3]+127)/255 : g[k];CHECK(dv+1>=gv && gv+1>=dv); }
    exr_canvas_free(direct);exr_canvas_free(group);
  }
  { exr_canvas *c=canvas(1,1,0);CHECK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,4,&error)==EXR_ARGUMENT);exr_canvas_free(c); }
  { exr_canvas *c=canvas(1,1,0);OK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,EXR_GROUP_KNOCKOUT,&error));OK(exr_canvas_end_layer(c,0,&error));exr_canvas_free(c); }
}

static void knockout(void) {
  exr_path_segment p[5];exr_draw_style style=exr_draw_style_defaults();unsigned char *px;exr_canvas *c,*plain;
  /* A single knockout element must equal plain painting: no "clear the backdrop" shortcut. */
  c=canvas(4,4,0xffffffff);plain=canvas(4,4,0xffffffff);rect(p,4,4);style.fill=0x00ff0080;
  OK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,EXR_GROUP_KNOCKOUT,&error));
  OK(exr_canvas_path(c,p,5,NULL,&style,&error));OK(exr_canvas_end_layer(c,1,&error));
  OK(exr_canvas_path(plain,p,5,NULL,&style,&error));
  px=exr_canvas_bitmap(c)->pixels;
  { const unsigned char *q=exr_canvas_bitmap(plain)->pixels;unsigned k;for(k=0;k<4;k++) CHECK(px[k]+1>=q[k] && q[k]+1>=px[k]); }
  exr_canvas_free(c);exr_canvas_free(plain);
  /* Overlapping elements: knockout keeps the newest element over the initial backdrop. */
  c=canvas(4,4,0xffffffff);rect(p,4,4);
  OK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,EXR_GROUP_KNOCKOUT,&error));
  style.fill=0xff0000ff;OK(exr_canvas_path(c,p,5,NULL,&style,&error));
  style.fill=0x00ff0080;OK(exr_canvas_path(c,p,5,NULL,&style,&error));
  OK(exr_canvas_end_layer(c,1,&error));px=exr_canvas_bitmap(c)->pixels;
  CHECK(px[0]>=125 && px[0]<=130 && px[1]>=253 && px[2]>=125 && px[2]<=130);
  exr_canvas_free(c);
  /* The same sequence without knockout accumulates over the red element instead. */
  c=canvas(4,4,0xffffffff);rect(p,4,4);
  OK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,0,&error));
  style.fill=0xff0000ff;OK(exr_canvas_path(c,p,5,NULL,&style,&error));
  style.fill=0x00ff0080;OK(exr_canvas_path(c,p,5,NULL,&style,&error));
  OK(exr_canvas_end_layer(c,1,&error));px=exr_canvas_bitmap(c)->pixels;
  CHECK(px[0]>=125 && px[0]<=130 && px[1]>=125 && px[1]<=130 && px[2]<=3);
  exr_canvas_free(c);
  /* Zero-coverage elements never knock the group back to its backdrop. */
  c=canvas(4,4,0xffffffff);rect(p,4,4);
  OK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,EXR_GROUP_KNOCKOUT,&error));
  style.fill=0x00ff0080;OK(exr_canvas_path(c,p,5,NULL,&style,&error));
  style.fill=0x0000ff00;OK(exr_canvas_path(c,p,5,NULL,&style,&error));
  OK(exr_canvas_end_layer(c,1,&error));px=exr_canvas_bitmap(c)->pixels;
  CHECK(px[1]>=253 && px[0]>=125 && px[0]<=130);
  exr_canvas_free(c);
  /* A transparent backdrop exposes coverage replacement: a later element replaces
     both the colour and the alpha, so background removal keeps 50% coverage. */
  c=canvas(4,4,0x00000000);rect(p,4,4);
  OK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,EXR_GROUP_KNOCKOUT,&error));
  style.fill=0xff0000ff;OK(exr_canvas_path(c,p,5,NULL,&style,&error));
  style.fill=0x00ff0080;OK(exr_canvas_path(c,p,5,NULL,&style,&error));
  OK(exr_canvas_end_layer(c,1,&error));px=exr_canvas_bitmap(c)->pixels;
  CHECK(px[1]>=253 && px[3]>=126 && px[3]<=130);
  exr_canvas_free(c);
  /* Budget: a knockout group costs the same 24 bytes/pixel as a non-isolated one. */
  { exr_canvas *b=canvas(1,1,0);OK(exr_canvas_set_layer_budget(b,23,&error));
    CHECK(exr_canvas_begin_group(b,1,EXR_BLEND_NORMAL,EXR_GROUP_KNOCKOUT,&error)==EXR_LIMIT);exr_canvas_free(b);
  }
  { exr_canvas *b=canvas(1,1,0);OK(exr_canvas_set_layer_budget(b,24,&error));
    OK(exr_canvas_begin_group(b,1,EXR_BLEND_NORMAL,EXR_GROUP_KNOCKOUT,&error));OK(exr_canvas_end_layer(b,0,&error));exr_canvas_free(b);
  }
  /* Cancellation aborts a knockout group without producing a partial commit. */
  { int stop=0;exr_canvas_config cfg={0};exr_canvas *b=NULL;cfg.width=cfg.height=1;cfg.control.cancelled=cancelled;cfg.control.context=&stop;
    OK(exr_canvas_create(&cfg,&b,&error));rect(p,1,1);style.fill=0x00ff0080;
    OK(exr_canvas_begin_group(b,1,EXR_BLEND_NORMAL,EXR_GROUP_KNOCKOUT,&error));
    OK(exr_canvas_path(b,p,5,NULL,&style,&error));stop=1;
    CHECK(exr_canvas_end_layer(b,1,&error)==EXR_CANCELLED);exr_canvas_free(b);
  }
  /* Isolated knockout starts transparent. */
  c=canvas(4,4,0xffffffff);rect(p,4,4);style.fill=0x00ff0080;
  OK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,EXR_GROUP_ISOLATED|EXR_GROUP_KNOCKOUT,&error));
  OK(exr_canvas_path(c,p,5,NULL,&style,&error));OK(exr_canvas_end_layer(c,1,&error));
  px=exr_canvas_bitmap(c)->pixels;CHECK(px[0]>=125 && px[0]<=130 && px[1]>=253 && px[2]>=125 && px[2]<=130);
  exr_canvas_free(c);
}
static void invalid(void) {
  { exr_fixed_document *d=open_book("group-malformed");exr_bitmap b={0};unsigned i;for(i=0;i<5;i++) CHECK(exr_fixed_render(d,0,1,NULL,&b,&error)==EXR_FORMAT && !b.pixels);exr_fixed_free(d); }
  { unsigned i;for(i=1;i<6;i++) {char name[24];exr_fixed_document *d;exr_bitmap b={0};exr_status got;snprintf(name,sizeof(name),"group-bad-%u",i);d=open_book(name);got=exr_fixed_render(d,0,1,NULL,&b,&error);
      /* K=true is a plain group (11.4.5 default); K=false is knockout and now renders. */
      if(i==1) { CHECK(got==EXR_OK && b.pixels); exr_bitmap_free(&b); }
      else CHECK(got==(i==2 ? EXR_UNSUPPORTED : EXR_FORMAT) && !b.pixels);
      exr_fixed_free(d);} }
  unsigned i;for(i=0;i<3;i++) {char name[16];exr_fixed_document *d;exr_bitmap b={0};snprintf(name,sizeof(name),"bad-%u",i);d=open_book(name);CHECK(exr_fixed_render(d,0,1,NULL,&b,&error)==EXR_FORMAT && !b.pixels);exr_fixed_free(d);}
}
int main(int argc,char **argv) {CHECK(argc==2);directory=argv[1];direct();analytic();layers();nonisolated();references();consumers();knockout();invalid();printf("%u RGB blend checks passed\n",checks);return 0;}
