/* SPDX-License-Identifier: MIT */
#undef NDEBUG
#include "../src/pdf_raster_internal.h"
#include "../src/canvas_internal.h"
#include "../src/glyph_atlas_internal.h"
#include <assert.h>
#include <stdio.h>
static exr_error error;
static exr_glyph_atlas *evict_atlas;
static exr_status (*original_alpha)(void *,unsigned,exr_error *);
static exr_status evicting_alpha(void *context,unsigned flags,exr_error *e) {
  exr_atlas_entry *entry;
  /* Model nested mask painting evicting the parent's entry during sink setup.
     Poison payloads first so borrowing before this callback fails reliably. */
  for(entry=evict_atlas->first;entry;entry=entry->next)
    memset(entry->mask.pixels,0,(size_t)entry->mask.width*entry->mask.height);
  exr_atlas_clear(evict_atlas);
  return original_alpha(context,flags,e);
}
#define OK(x) do { exr_status s=(x);if(s!=EXR_OK) { fprintf(stderr,"line %d: %d %s\n",__LINE__,s,error.message);exit(1); } } while(0)
/* A forwarding host sink exercises the pre-atlas outline path on the same
   canvas implementation, without an environment-dependent reference image. */
static exr_status reference_path(void *c,const exr_path_segment *p,size_t n,
    const double m[6],const exr_draw_style *s,exr_error *e) {
  return exr_canvas_path(c,p,n,m,s,e);
}
static void render(exr_pdf_file *file,uint32_t resources,const char *content,
    unsigned variant,int reference,exr_bitmap *out) {
  exr_canvas_config config={0};exr_canvas *canvas=NULL;exr_draw_sink_ex sink={0};
  unsigned char soft[64*64];size_t i;
  exr_path_segment clip[5]={ {.verb=EXR_PATH_MOVE,.points={{4.25,3.5}}},
    {.verb=EXR_PATH_LINE,.points={{60.5,3.5}}}, {.verb=EXR_PATH_LINE,.points={{60.5,61.25}}},
    {.verb=EXR_PATH_LINE,.points={{4.25,61.25}}}, {.verb=EXR_PATH_CLOSE} };
  config.width=config.height=64;config.channels=variant&1 ? 1 : 4;
  config.background=variant&2 ? 0xadc8e480 : 0xffffffff;
  OK(exr_canvas_create(&config,&canvas,&error));
  if(variant&4) OK(exr_canvas_clip(canvas,clip,5,NULL,EXR_FILL_NONZERO,&error));
  if(variant&8) {
    for(i=0;i<sizeof(soft);i++) soft[i]=(unsigned char)(i*73);
    OK(exr_canvas_soft_mask(canvas,soft,64,64,&error));
  }
  sink.struct_size=sizeof(sink);OK(exr_canvas_get_sink_ex(canvas,&sink,&error));
  if(variant&16) {
    evict_atlas=exr_pdf_glyph_atlas(file);original_alpha=sink.alpha_source;sink.alpha_source=evicting_alpha;
  }
  if(reference) sink.base.path=reference_path;
  OK(exr_pdf_paint_content_ex(file,resources,content,strlen(content),NULL,&sink,NULL,NULL,
    &canvas->work,NULL,NULL,&error));
  OK(exr_canvas_take(canvas,out,&error));exr_canvas_free(canvas);
}
/* Optional fixture probe records actual atlas activity independently of render
   timings. The required timing/pixel oracle remains benchmark_pdf_rect.py. */
static void probe(const char *path) {
  const unsigned widths[]={600,1200,2400};FILE *f=fopen(path,"rb");long size;unsigned char *data;
  assert(f && !fseek(f,0,SEEK_END));size=ftell(f);assert(size>0);rewind(f);
  data=malloc((size_t)size);assert(data && fread(data,1,(size_t)size,f)==(size_t)size);fclose(f);
  for(size_t w=0;w<3;w++) {
    exr_pdf_file *file=NULL;exr_pdf_page_info *pages=NULL;size_t count=0,first_hits=0,first_misses=0;
    exr_glyph_atlas *a;
    OK(exr_pdf_open(data,(size_t)size,&file,&error));OK(exr_pdf_pages(file,&pages,&count,&error));
    for(unsigned round=0;round<2;round++) for(size_t p=0;p<count;p++) {
      exr_viewport view;exr_bitmap bitmap={0};
      OK(exr_pdf_page_viewport(&pages[p],1,&view,&error));
      OK(exr_pdf_raster_page(file,&pages[p],widths[w]/view.width,NULL,NULL,&bitmap,&error));
      exr_bitmap_free(&bitmap);exr_pdf_operation_end(file);
      if(!round && p+1==count) { a=exr_pdf_glyph_atlas(file);first_hits=a->hits;first_misses=a->misses; }
    }
    a=exr_pdf_glyph_atlas(file);
    printf("{\"width\":%u,\"pages\":%zu,\"first_round_hits\":%zu,\"first_round_misses\":%zu,\"second_round_hits\":%zu,\"second_round_misses\":%zu,\"entries\":%zu,\"bytes_including_metadata\":%zu,\"evictions\":%zu}\n",
      widths[w],count,first_hits,first_misses,a->hits-first_hits,a->misses-first_misses,a->count,a->bytes+sizeof(*a),a->evictions);
    free(pages);exr_pdf_close(file);
  }
  free(data);
}
int main(int argc,char **argv) {
  char path[4096],content[32768];unsigned char *data;long size;FILE *f;
  exr_pdf_file *file=NULL;uint32_t resources;size_t compared=0;
  if(argc==3) { probe(argv[2]);return 0; }
  assert(argc==2);snprintf(path,sizeof(path),"%s/pdf-outlines.pdf",argv[1]);
  f=fopen(path,"rb");assert(f && !fseek(f,0,SEEK_END));size=ftell(f);assert(size>0);rewind(f);
  data=malloc((size_t)size);assert(data && fread(data,1,(size_t)size,f)==(size_t)size);fclose(f);
  OK(exr_pdf_open(data,(size_t)size,&file,&error));
  OK(exr_pdf_resolve(file,exr_pdf_get(file,exr_pdf_root(file),"Resources"),&resources,&error));
  for(unsigned transform=0;transform<5;transform++) {
    size_t at=0;
    for(unsigned i=0;i<64;i++) {
      double phase=(i%4)*.25+(transform==4 ? .001 : 0);
      double x=(int)(i%8)*8-5+phase,y=(int)(i/8)*8-5+(i%4)*.25;
      /* Every pair repeats a phase at a different integer position. Include
         negative origins, all page edges, non-F26Dot6 sizes, shear and rotation. */
      at+=(size_t)snprintf(content+at,sizeof(content)-at,
        "q .2 .4 .8 rg BT /%s %.9f Tf %.9f %.9f %.9f %.9f %.9f %.9f Tm (AAQQ ) Tj ET Q ",
        transform&1 ? "Cubic" : "Names",9.0+transform*.117,transform==2 ? -.9 : 1.0,transform==1 ? .2 : 0.0,
        transform==1 ? -.1 : 0.0,transform==3 ? -1.0 : 1.0,x,y);
      assert(at<sizeof(content));
    }
    for(unsigned variant=0;variant<16;variant++) {
      exr_bitmap cached={0},reference={0};
      render(file,resources,content,variant,0,&cached);
      if(!transform && !variant) {
        exr_glyph_atlas *a=exr_pdf_glyph_atlas(file);
        assert(a->hits && a->misses); /* Repeated characters hit within the very first page. */
      }
      render(file,resources,content,variant,1,&reference);
      assert(cached.stride==reference.stride && cached.height==reference.height);
      if(memcmp(cached.pixels,reference.pixels,(size_t)cached.stride*cached.height)) {
        fprintf(stderr,"coverage mismatch: transform %u variant %u\n",transform,variant);return 1;
      }
      compared+=(size_t)cached.width*cached.height;
      exr_bitmap_free(&cached);exr_bitmap_free(&reference);
      exr_pdf_operation_end(file); /* Cached coverage must survive decoded-font teardown. */
    }
  }
  for(unsigned variant=16;variant<=24;variant+=8) {
    exr_bitmap cached={0},reference={0};
    render(file,resources,content,variant,0,&cached);render(file,resources,content,variant,1,&reference);
    assert(!memcmp(cached.pixels,reference.pixels,(size_t)cached.stride*cached.height));
    compared+=(size_t)cached.width*cached.height;
    exr_bitmap_free(&cached);exr_bitmap_free(&reference);
  }
  {
    exr_glyph_atlas *a=exr_pdf_glyph_atlas(file);
    assert(a && a->hits && a->misses && a->count<=a->entry_limit && a->bytes+sizeof(*a)<=a->byte_limit);
    printf("{\"compared_pixels\":%zu,\"different_pixels\":0,\"hits\":%zu,\"misses\":%zu,\"entries\":%zu,\"bytes_including_metadata\":%zu}\n",
      compared,a->hits,a->misses,a->count,a->bytes+sizeof(*a));
  }
  exr_pdf_close(file);free(data);return 0;
}
