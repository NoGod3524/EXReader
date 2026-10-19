/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static int near(float a,float b) { return fabsf(a-b)<0.01f; }
static exr_layout_config config(float width,float height) {
  exr_layout_config c=exr_layout_config_defaults(); c.page=(exr_layout_options){width,height,0,20,1.2f,0}; return c;
}
static void rejected(exr_document *doc,exr_font *font,const exr_positioned_input *input,exr_status expected) {
  exr_layout *layout=(exr_layout *)(uintptr_t)1; exr_layout_config c=config(180,100);
  CHECK(exr_layout_create_positioned(doc,font,input,&c,&layout,&error)==expected);
  CHECK(!layout && error.code==expected && error.message[0]);
}
static void text(const char *dir) {
  char path[4096]; exr_font *font=NULL; exr_document *doc=NULL; exr_layout *original=NULL,*fixed=NULL,*behind=NULL,*ahead=NULL,*scaled=NULL;
  exr_layout_config c=config(180,100); exr_positioned_input in={0}; exr_positioned_page page={0};
  exr_glyph *glyphs; exr_paint *paints; exr_box box={0}; exr_bitmap a={0},b={0};
  const exr_page *pages; const exr_line *lines; const exr_glyph *source; size_t ng,nl,np,i,n,difference=0; float x;
  snprintf(path,sizeof(path),"%s/fonts/primary.ttf",dir); OK(exr_font_open(path,&font,&error));
  OK(exr_document_open_memory(EXR_TXT,"AB",2,&doc,&error)); OK(exr_layout_create_ex(doc,font,&c,&original,&error));
  pages=exr_layout_pages(original,&np); CHECK(np==1); lines=exr_layout_lines(original,&nl); source=exr_layout_glyphs(original,&ng); CHECK(ng>=2);
  glyphs=malloc(ng*sizeof(*glyphs)); paints=malloc((ng+1)*sizeof(*paints)); CHECK(glyphs && paints); memcpy(glyphs,source,ng*sizeof(*glyphs));
  for(i=0;i<ng;i++) paints[i]=(exr_paint){EXR_PAINT_GLYPH,0,i};
  page.width=180; page.height=100; page.content=pages[0]; page.content.box_start=0; page.content.box_count=1; page.paint_count=ng;
  box.kind=EXR_BOX_BLOCK; box.node=box.resource=SIZE_MAX; box.end=2; box.width=180; box.height=100; box.background=0x0000ffff;
  in.struct_size=sizeof(in); in.pages=&page; in.page_count=1; in.glyphs=glyphs; in.glyph_count=ng;
  in.lines=lines; in.line_count=nl; in.boxes=&box; in.box_count=1; in.paints=paints; in.paint_count=ng;
  OK(exr_layout_create_positioned(doc,font,&in,&c,&fixed,&error));
  CHECK(exr_layout_paints(fixed,0,&n) && n==ng); CHECK(!exr_layout_paints(original,0,&n) && !n);
  { exr_layout_config viewport={0}; viewport.page.width=180; viewport.page.height=100;
    OK(exr_layout_create_positioned(doc,font,&in,&viewport,&scaled,&error)); exr_layout_free(scaled); scaled=NULL;
  }
  OK(exr_render_page_color(original,NULL,0,&a,&error)); OK(exr_render_page_color(fixed,NULL,0,&b,&error));
  CHECK(a.stride==b.stride && a.height==b.height && !memcmp(a.pixels,b.pixels,(size_t)a.stride*a.height));
  exr_bitmap_free(&a); exr_bitmap_free(&b);
  { exr_font_input input={0}; exr_font *raw=(exr_font *)(uintptr_t)1; exr_layout *native=NULL; FILE *file; long length; void *data;
    snprintf(path,sizeof(path),"%s/fonts/glyph-only.ttf",dir); file=fopen(path,"rb"); CHECK(file && !fseek(file,0,SEEK_END));
    length=ftell(file); CHECK(length>0); rewind(file); data=malloc((size_t)length);
    CHECK(data && fread(data,1,(size_t)length,file)==(size_t)length); fclose(file); input=(exr_font_input){data,(size_t)length,0};
    CHECK(exr_font_create(&input,1,&raw,&error)==EXR_FONT && !raw);
    OK(exr_font_create_glyphs(&input,1,&raw,&error)); CHECK(exr_font_count(raw)==1 && !exr_font_has_glyph(raw,0,'A'));
    free(data); OK(exr_layout_create_positioned(doc,raw,&in,&c,&native,&error)); exr_font_free(raw);
    OK(exr_render_page_color(original,NULL,0,&a,&error)); OK(exr_render_page_color(native,NULL,0,&b,&error));
    CHECK(a.stride==b.stride && a.height==b.height && !memcmp(a.pixels,b.pixels,(size_t)a.stride*a.height));
    exr_bitmap_free(&a); exr_bitmap_free(&b); exr_layout_free(native);
    CHECK(exr_font_create_glyphs(NULL,1,&raw,&error)==EXR_ARGUMENT && !raw);
  }
  c=config(360,200); OK(exr_layout_create_positioned(doc,font,&in,&c,&scaled,&error));
  source=exr_layout_glyphs(scaled,&n); CHECK(n==ng && near(source[0].x,glyphs[0].x*2) && near(source[0].size,glyphs[0].size*2));
  CHECK(exr_layout_hit_test(scaled,0,source[0].x+source[0].advance*0.25f,source[0].baseline)==source[0].cluster_start);
  exr_layout_free(scaled); scaled=NULL; c=config(180,100);
  paints[ng]=(exr_paint){EXR_PAINT_BOX,0,0}; in.paint_count=page.paint_count=ng+1;
  OK(exr_layout_create_positioned(doc,font,&in,&c,&ahead,&error));
  for(i=ng;i>0;i--) paints[i]=paints[i-1]; paints[0]=(exr_paint){EXR_PAINT_BOX,0,0};
  OK(exr_layout_create_positioned(doc,font,&in,&c,&behind,&error));
  { exr_font *large=NULL; exr_layout *oversize=NULL; exr_glyph *huge=malloc(ng*sizeof(*huge)); exr_positioned_input bigger=in;
    CHECK(huge); memcpy(huge,glyphs,ng*sizeof(*huge)); for(i=0;i<ng;i++) huge[i].size=256;
    snprintf(path,sizeof(path),"%s/fonts/oversize.ttf",dir); OK(exr_font_open(path,&large,&error)); bigger.glyphs=huge;
    OK(exr_layout_create_positioned(doc,large,&bigger,&c,&oversize,&error));
    CHECK(exr_render_page(oversize,NULL,0,&a,&error)==EXR_LIMIT && !a.pixels);
    exr_layout_free(oversize); exr_font_free(large); free(huge);
  }
  OK(exr_render_page_color(ahead,NULL,0,&a,&error)); OK(exr_render_page_color(behind,NULL,0,&b,&error));
  for(i=0;i<(size_t)a.width*a.height;i++) {
    CHECK(a.pixels[i*4]==0 && a.pixels[i*4+1]==0 && a.pixels[i*4+2]==255 && a.pixels[i*4+3]==255);
    if(memcmp(a.pixels+i*4,b.pixels+i*4,4)) difference++;
  }
  CHECK(difference>0); exr_bitmap_free(&a); exr_bitmap_free(&b);
  { exr_positioned_input bad=in; bad.struct_size--; rejected(doc,font,&bad,EXR_ARGUMENT); bad=in; bad.glyph_count=4194304; rejected(doc,font,&bad,EXR_LIMIT); }
  { struct { exr_positioned_input base; unsigned char extra[8]; } extended={0};
    extended.base=in; extended.base.struct_size=sizeof(extended); OK(exr_layout_create_positioned(doc,font,&extended.base,&c,&scaled,&error)); exr_layout_free(scaled); scaled=NULL;
    extended.extra[0]=1; rejected(doc,font,&extended.base,EXR_ARGUMENT);
  }
  x=glyphs[0].x; glyphs[0].x=NAN; rejected(doc,font,&in,EXR_ARGUMENT); glyphs[0].x=x;
  glyphs[0].font_index=99; rejected(doc,font,&in,EXR_ARGUMENT); glyphs[0].font_index=0;
  paints[0].flags=1; rejected(doc,font,&in,EXR_ARGUMENT); paints[0].flags=0;
  paints[0].index=99; rejected(doc,font,&in,EXR_ARGUMENT); paints[0].index=0;
  page.content.line_count=SIZE_MAX; rejected(doc,font,&in,EXR_ARGUMENT); page.content.line_count=nl;
  page.width=INFINITY; rejected(doc,font,&in,EXR_ARGUMENT); page.width=180;
  CHECK(exr_layout_memory_size(ahead)==exr_layout_memory_size(fixed)+sizeof(exr_paint));
  exr_layout_free(original); exr_document_free(doc); exr_font_free(font); free(glyphs); free(paints);
  OK(exr_render_page_color(fixed,NULL,0,&a,&error)); exr_bitmap_free(&a);
  CHECK(!exr_layout_paints(fixed,1,&n) && !n); exr_layout_free(fixed); exr_layout_free(ahead); exr_layout_free(behind);
}
typedef struct { unsigned decoded,released; int failure,cancel; } state;
static exr_status decode(void *context,const exr_resource *resource,const void *data,size_t size,exr_bitmap *bitmap,exr_error *e) {
  state *s=context; s->decoded++; CHECK(!strcmp(resource->media_type,"image/png"));
  return s->failure ? EXR_FORMAT : exr_image_decode(data,size,bitmap,e);
}
static void release(void *context,exr_bitmap *bitmap) { ((state *)context)->released++; exr_bitmap_free(bitmap); }
static int cancelled(void *context) { return ((state *)context)->cancel; }
static void images(const char *dir) {
  char path[4096]; exr_document *doc=NULL; exr_layout *layout=NULL; exr_layout_config c=config(128,64);
  exr_positioned_page page={0}; exr_positioned_input in={0}; exr_box box={0}; exr_paint paints[2]={{EXR_PAINT_BOX,0,0},{EXR_PAINT_BOX,0,0}};
  exr_bitmap bitmap={0}; size_t size; state s={0};
  snprintf(path,sizeof(path),"%s/rich.fb2",dir); OK(exr_document_open(path,&doc,&error)); exr_document_text(doc,&size);
  page.width=page.height=64; page.content.end=size; page.content.box_count=1; page.paint_count=2;
  box.kind=EXR_BOX_IMAGE; box.node=SIZE_MAX; box.resource=0; box.width=box.height=16;
  in.struct_size=sizeof(in); in.pages=&page; in.page_count=1; in.boxes=&box; in.box_count=1; in.paints=paints; in.paint_count=2;
  c.decode_image=decode; c.release_image=release; c.image_context=&s;
  OK(exr_layout_create_positioned(doc,NULL,&in,&c,&layout,&error)); CHECK(s.decoded==1 && s.released==1);
  CHECK(exr_layout_image(layout,0)); CHECK(near(exr_layout_boxes(layout,NULL)[0].x,32));
  exr_document_free(doc); OK(exr_render_page_color(layout,NULL,0,&bitmap,&error));
  CHECK(bitmap.pixels[0]==255 && bitmap.pixels[1]==255 && bitmap.pixels[2]==255);
  exr_bitmap_free(&bitmap);
  { exr_control control={cancelled,NULL,&s}; s.cancel=1;
    CHECK(exr_render_page_ex(layout,NULL,0,4,&control,&bitmap,&error)==EXR_CANCELLED && !bitmap.pixels);
  }
  exr_layout_free(layout); layout=NULL; OK(exr_document_open(path,&doc,&error));
  s.cancel=0; s.failure=1; CHECK(exr_layout_create_positioned(doc,NULL,&in,&c,&layout,&error)==EXR_FORMAT && !layout);
  CHECK(s.decoded==2 && s.released==2);
  s.failure=0; s.cancel=1; c.control=(exr_control){cancelled,NULL,&s};
  CHECK(exr_layout_create_positioned(doc,NULL,&in,&c,&layout,&error)==EXR_CANCELLED && !layout);
  CHECK(s.decoded==2); exr_document_free(doc);
}
static void pages(void) {
  exr_document *doc=NULL; exr_layout *layout=NULL; exr_layout_config c=config(200,200);
  exr_positioned_page p[2]={{0}}; exr_positioned_input in={0}; exr_bitmap bitmap={0};
  OK(exr_document_open_memory(EXR_TXT,"AB",2,&doc,&error));
  p[0].width=100; p[0].height=200; p[0].content.end=1;
  p[1].width=200; p[1].height=100; p[1].content.start=1; p[1].content.end=2;
  in.struct_size=sizeof(in); in.pages=p; in.page_count=2;
  OK(exr_layout_create_positioned(doc,NULL,&in,&c,&layout,&error)); CHECK(exr_layout_page_at(layout,1)==1);
  CHECK(exr_layout_hit_test(layout,1,0,0)==1); OK(exr_render_page(layout,NULL,1,&bitmap,&error));
  CHECK(bitmap.width==200 && bitmap.height==200 && bitmap.pixels[0]==255);
  exr_bitmap_free(&bitmap); exr_layout_free(layout); exr_document_free(doc);
  OK(exr_document_open_memory(EXR_TXT,"A\xe7\x94\xb2",4,&doc,&error)); p[0].content.end=2; in.page_count=1;
  rejected(doc,NULL,&in,EXR_ARGUMENT); exr_document_free(doc);
}
int main(int argc,char **argv) {
  CHECK(argc==2); text(argv[1]); images(argv[1]); pages(); printf("%u positioned layout checks passed\n",checks); return 0;
}
