/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error;static unsigned checks,maximum;static const char *directory;
#define CHECK(x) do { checks++;if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message);exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static exr_fixed_document *open_scene(const char *name) {
  char path[4096];exr_fixed_document *d=NULL;snprintf(path,sizeof(path),"%s/pdf-blend/%s",directory,name);
  OK(exr_fixed_open(path,NULL,&d,&error));return d;
}
static void scenes(void) {
  const char *kinds[]={"retain","null","clear","restore","ordinary","group","inner-alpha","nested"};
  const unsigned masks[]={64,128,192};unsigned i,j,w,k;char path[4096];unsigned char expected[27][8];FILE *f;
  snprintf(path,sizeof(path),"%s/pdf-blend/mask-scope-oracle.bin",directory);f=fopen(path,"rb");CHECK(f);
  CHECK(fread(expected,1,sizeof(expected),f)==sizeof(expected));CHECK(fgetc(f)==EOF);fclose(f);
  for(i=0;i<8;i++) for(j=0;j<3;j++) {
    exr_fixed_document *d;snprintf(path,sizeof(path),"mask-scope-%s-%u.pdf",kinds[i],masks[j]);d=open_scene(path);
    for(w=0;w<2;w++) {
      exr_bitmap b={0};exr_fixed_render_options options={0};const unsigned char *p;
      options.channels=4;options.background=w ? 0xffffffff : 0;
      OK(exr_fixed_render(d,0,1,&options,&b,&error));p=b.pixels+8*b.stride+8*4;
      for(k=0;k<4;k++) {
        unsigned got=w || k==3 ? p[k] : (p[k]*p[3]+127)/255;
        unsigned diff=(unsigned)abs((int)got-(int)expected[i*3+j][w*4+k]);
        if(diff>maximum) maximum=diff;
        if(diff>2) fprintf(stderr,"%s white %u channel %u got %u want %u\n",path,w,k,got,expected[i*3+j][w*4+k]);
        CHECK(diff<=2);
      }
      exr_bitmap_free(&b);
    }
    exr_fixed_free(d);
  }
  { const char *names[]={"mask-scope-shape-iso.pdf","mask-scope-shape-noniso.pdf","mask-scope-shape-nested.pdf"};
    for(i=0;i<3;i++) {
      exr_fixed_document *d=open_scene(names[i]);
      for(w=0;w<2;w++) {
        exr_bitmap b={0};exr_fixed_render_options options={0};const unsigned char *p;options.channels=4;options.background=w ? 0xffffffff : 0;
        OK(exr_fixed_render(d,0,1,&options,&b,&error));p=b.pixels+8*b.stride+8*4;
        for(k=0;k<4;k++) { unsigned got=w || k==3 ? p[k] : (p[k]*p[3]+127)/255;
          CHECK(abs((int)got-(int)expected[24+i][w*4+k])<=2); }
        exr_bitmap_free(&b);
      }
      exr_fixed_free(d);
    }
  }
  { const char *bad[]={"mask-scope-bad-mask.pdf","mask-scope-bad-content.pdf"};
    for(i=0;i<2;i++) { exr_fixed_document *d=open_scene(bad[i]);exr_bitmap b={0};
      CHECK(exr_fixed_render(d,0,1,NULL,&b,&error)==EXR_FORMAT);CHECK(!b.pixels);exr_fixed_free(d); }
  }
}
static void group_failure(void) {
  exr_fixed_document *d=open_scene("mask-scope-group-128.pdf");exr_canvas_config config={0};exr_canvas *c=NULL;
  exr_draw_sink_ex sink={0};exr_bitmap b={0};config.width=config.height=16;
  OK(exr_canvas_create(&config,&c,&error));OK(exr_canvas_set_layer_budget(c,1024,&error));
  sink.struct_size=sizeof(sink);OK(exr_canvas_get_sink_ex(c,&sink,&error));
  CHECK(exr_fixed_draw_ex(d,0,NULL,&sink,NULL,&error)==EXR_LIMIT);
  CHECK(exr_canvas_take(c,&b,&error)==EXR_LIMIT && !b.pixels);
  exr_canvas_free(c);exr_fixed_free(d);
}
typedef struct { unsigned begins,ends; } inspection;
static exr_status inspect_path(void *ctx,const exr_path_segment *p,size_t n,const double m[6],const exr_draw_style *style,exr_error *e) {
  (void)ctx;(void)p;(void)n;(void)m;(void)style;(void)e;return EXR_OK;
}
static exr_status inspect_begin(void *ctx,double opacity,exr_blend_mode mode,unsigned flags,exr_error *e) {
  inspection *s=ctx;(void)opacity;(void)mode;(void)flags;(void)e;s->begins++;return EXR_OK;
}
static exr_status inspect_end(void *ctx,unsigned commit,exr_error *e) {
  inspection *s=ctx;(void)commit;(void)e;s->ends++;return EXR_OK;
}
static exr_status inspect_mask(void *ctx,const unsigned char *mask,size_t w,size_t h,exr_error *e) {
  (void)ctx;(void)mask;(void)w;(void)h;(void)e;return EXR_OK;
}
static exr_status inspect_extent(void *ctx,unsigned *w,unsigned *h,exr_error *e) {
  (void)ctx;(void)e;*w=*h=2048;return EXR_OK;
}
static void aggregate_budget(void) {
  exr_fixed_document *d=open_scene("mask-scope-budget.pdf");inspection state={0};exr_draw_sink_ex sink={0};
  sink.struct_size=sizeof(sink);sink.base.path=inspect_path;sink.base.context=&state;
  sink.begin_group=inspect_begin;sink.end_layer=inspect_end;sink.soft_mask=inspect_mask;sink.extent=inspect_extent;
  CHECK(exr_fixed_draw_ex(d,0,NULL,&sink,NULL,&error)==EXR_LIMIT);
  CHECK(strstr(error.message,"active soft masks exceed 64 MiB"));CHECK(state.begins==state.ends && state.begins==17);
  exr_fixed_free(d);
}
int main(int argc,char **argv) {
  CHECK(argc==2);directory=argv[1];scenes();group_failure();aggregate_budget();
  printf("%u mask scope checks; maximum analytic probe difference %u/255\n",checks,maximum);return 0;
}
