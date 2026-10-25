/* SPDX-License-Identifier: MIT */
#include <exreader.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static exr_error error;
static unsigned checks, cases;
static FILE *frames;
#define CHECK(x) do { checks++;if(!(x)){fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message);exit(1);} } while(0)
#define OK(x) CHECK((x)==EXR_OK)

static int same(const exr_bitmap *a,const exr_bitmap *b) {
  return a->width==b->width && a->height==b->height && a->stride==b->stride && a->channels==b->channels &&
    !memcmp(a->pixels,b->pixels,(size_t)a->stride*a->height);
}
static void save_frame(const exr_bitmap *bitmap) {
  uint32_t header[4]={bitmap->width,bitmap->height,bitmap->stride,bitmap->channels};
  CHECK(fwrite(header,sizeof(header),1,frames)==1);
  CHECK(fwrite(bitmap->pixels,bitmap->stride,bitmap->height,frames)==bitmap->height);
}
#ifndef BACKGROUND_BASELINE
typedef struct { size_t count,stop; } cancel_state;
static int cancel(void *context) {
  cancel_state *state=context;state->count++;return state->stop && state->count>=state->stop;
}
static void corner(const exr_bitmap *b,uint32_t color) {
  CHECK(b->channels==4 && b->width && b->height);
  for(unsigned k=0;k<4;k++) CHECK(b->pixels[k]==(unsigned char)(color>>(24-8*k)));
}
static void color_at(const exr_bitmap *bitmap,unsigned x,unsigned y,uint32_t rgba) {
  const unsigned char *p=bitmap->pixels+(size_t)y*bitmap->stride+x*4;
  for(unsigned k=0;k<4;k++) CHECK(p[k]==(unsigned char)(rgba>>(24-8*k)));
}
/* Independent straight-alpha source-over oracle, allowing one rounding unit. */
static void over_at(const exr_bitmap *bitmap,unsigned x,unsigned y,uint32_t background,uint32_t source) {
  const unsigned char *p=bitmap->pixels+(size_t)y*bitmap->stride+x*4;
  double a=(source&255)/255.0,b=(background&255)/255.0,out=a+b*(1-a);
  CHECK(fabs(p[3]-255*out)<=1);
  for(unsigned k=0;k<3;k++) {
    double s=(source>>(24-8*k))&255,d=(background>>(24-8*k))&255;
    double expected=out ? (s*a+d*b*(1-a))/out : d;
    CHECK(fabs(p[k]-expected)<=1);
  }
}
#endif

static void exercise(const exr_layout *layout,int pictures) {
  exr_bitmap plain={0},controlled={0},gray={0};
  OK(exr_render_page_color(layout,NULL,0,&plain,&error));save_frame(&plain);
  OK(exr_render_page_ex(layout,NULL,0,4,NULL,&controlled,&error));CHECK(same(&plain,&controlled));save_frame(&controlled);
  OK(exr_render_page(layout,NULL,0,&gray,&error));save_frame(&gray);
#ifndef BACKGROUND_BASELINE
  const uint32_t backgrounds[]={0xffffffffu,0xfdf4dcffu,0x141e46ffu,0x11223300u,0x33669980u};
  size_t memory=exr_layout_memory_size(layout);
  for(size_t i=0;i<sizeof(backgrounds)/sizeof(*backgrounds);i++) {
    exr_bitmap themed={0},one={0};uint32_t bg=backgrounds[i];
    OK(exr_render_page_background(layout,NULL,0,4,bg,NULL,&themed,&error));if(pictures) corner(&themed,bg);
    OK(exr_render_page_background(layout,NULL,0,1,bg,NULL,&one,&error));
    if(pictures) CHECK(one.pixels[0]==(unsigned char)((77*(bg>>24)+150*((bg>>16)&255)+29*((bg>>8)&255)+128)>>8));
    if(i==0) { CHECK(same(&plain,&themed));CHECK(same(&gray,&one)); }
    if(pictures) {
      color_at(&themed,32,32,0xffffffffu); /* An opaque white image is still white. */
      color_at(&themed,80,32,0x144678ffu);
      over_at(&themed,128,32,bg,0xff000080u);
      color_at(&themed,176,32,bg); /* Transparent image reveals actual canvas. */
      color_at(&themed,32,96,0xffffffffu); /* Author white background stays white. */
      over_at(&themed,80,96,bg,0x00ff0080u);
    }
    exr_bitmap_free(&one);exr_bitmap_free(&themed);
  }
  if(pictures) {
    for(unsigned channels=1;channels<=4;channels+=3) {
    cancel_state state={0};exr_control control={cancel,NULL,&state};exr_bitmap expected={0},out={0};
    OK(exr_render_page_background(layout,NULL,0,channels,0x141e46ffu,&control,&expected,&error));
    size_t polls=state.count;CHECK(polls>2 && polls<10000);
    for(size_t n=1;n<=polls;n++) {
      state=(cancel_state){0,n};
      CHECK(exr_render_page_background(layout,NULL,0,channels,0x141e46ffu,&control,&out,&error)==EXR_CANCELLED);
      CHECK(error.code==EXR_CANCELLED);
      CHECK(!out.pixels && !out.width && !out.height && !out.stride && !out.channels);
      state=(cancel_state){0};
      OK(exr_render_page_background(layout,NULL,0,channels,0x141e46ffu,&control,&out,&error));CHECK(same(&expected,&out));
      exr_bitmap_free(&out);
    }
    CHECK(exr_render_page_background(NULL,NULL,0,4,0,NULL,&out,&error)==EXR_ARGUMENT && !out.pixels);
    CHECK(exr_render_page_background(layout,NULL,SIZE_MAX,4,0,NULL,&out,&error)==EXR_ARGUMENT && !out.pixels);
    CHECK(exr_render_page_background(layout,NULL,0,3,0,NULL,&out,&error)==EXR_ARGUMENT && !out.pixels);
    exr_bitmap_free(&expected);
    }
  }
  CHECK(exr_layout_memory_size(layout)==memory);
  exr_bitmap_free(&controlled);OK(exr_render_page_ex(layout,NULL,0,4,NULL,&controlled,&error));CHECK(same(&plain,&controlled));
#else
  (void)pictures;
#endif
  exr_bitmap_free(&gray);exr_bitmap_free(&controlled);exr_bitmap_free(&plain);cases++;
}

static exr_status decode(void *context,const exr_resource *resource,const void *data,size_t size,exr_bitmap *bitmap,exr_error *e) {
  static const uint32_t colors[]={0xffffffffu,0x144678ffu,0xff000080u,0xabcdef00u};
  unsigned index=0;(void)context;(void)e;CHECK(size==1 && data);
  CHECK(sscanf(resource->id,"image%u",&index)==1 && index<4);
  *bitmap=(exr_bitmap){0};bitmap->width=bitmap->height=16;bitmap->stride=64;bitmap->channels=4;
  bitmap->pixels=malloc(1024);CHECK(bitmap->pixels);
  for(unsigned i=0;i<256;i++) for(unsigned k=0;k<4;k++) bitmap->pixels[4*i+k]=(unsigned char)(colors[index]>>(24-8*k));
  return EXR_OK;
}
static void release_image(void *context,exr_bitmap *bitmap) { (void)context;exr_bitmap_free(bitmap); }

static void pictures(void) {
  exr_node_input nodes[]={{EXR_NODE_DOCUMENT,SIZE_MAX,"document",NULL,NULL,0},
    {EXR_NODE_CHAPTER,0,"chapter",NULL,NULL,0},{EXR_NODE_TEXT,1,NULL,"AB",NULL,0}};
  exr_chapter_input chapter={"chapter","chapter.xhtml",1,1};
  exr_resource_input resources[4];exr_document_input input={0};
  char ids[4][16];unsigned char encoded=1;exr_document *doc=NULL;exr_layout *layout=NULL;
  exr_box boxes[6];exr_paint paints[6];exr_positioned_page page={0};exr_positioned_input positioned={0};
  exr_layout_config config=exr_layout_config_defaults();
  memset(resources,0,sizeof(resources));memset(boxes,0,sizeof(boxes));memset(paints,0,sizeof(paints));
  for(unsigned i=0;i<4;i++) {
    snprintf(ids[i],sizeof(ids[i]),"image%u",i);
    resources[i].info=(exr_resource){ids[i],ids[i],"image/png",""};resources[i].data=&encoded;resources[i].size=1;
  }
  input.nodes=nodes;input.node_count=3;input.chapters=&chapter;input.chapter_count=1;input.resources=resources;input.resource_count=4;
  OK(exr_document_create(&input,&doc,&error));
  for(unsigned i=0;i<6;i++) {
    boxes[i].kind=i<4 ? EXR_BOX_IMAGE:EXR_BOX_BLOCK;boxes[i].node=SIZE_MAX;boxes[i].resource=i<4 ? i:SIZE_MAX;
    boxes[i].end=2;boxes[i].x=16+(i<4 ? i:i-4)*48;boxes[i].y=i<4 ? 16:80;
    boxes[i].width=boxes[i].height=32;boxes[i].background=i==4 ? 0xffffffffu:i==5 ? 0x00ff0080u:0;
    paints[i]=(exr_paint){EXR_PAINT_BOX,0,i};
  }
  page.width=240;page.height=160;page.content.end=2;page.content.box_count=6;page.paint_count=6;
  positioned.struct_size=sizeof(positioned);positioned.pages=&page;positioned.page_count=1;
  positioned.boxes=boxes;positioned.box_count=6;positioned.paints=paints;positioned.paint_count=6;
  config.page=(exr_layout_options){240,160,0,18,1.2f,0};config.decode_image=decode;config.release_image=release_image;
  OK(exr_layout_create_positioned(doc,NULL,&positioned,&config,&layout,&error));
  const exr_bitmap *image=exr_layout_image(layout,0);CHECK(image && image->pixels[0]==255);
  unsigned char before[1024];memcpy(before,image->pixels,sizeof(before));
  exercise(layout,1);CHECK(!memcmp(before,image->pixels,sizeof(before)));
  exr_layout_free(layout);exr_document_free(doc);
}

static void book(const char *path,exr_font *font,int bounded) {
  exr_layout_config config=exr_layout_config_defaults();exr_document *doc=NULL;exr_layout *layout=NULL;
  config.page=(exr_layout_options){320,240,16,18,1.3f,8};
  if(bounded) {
    exr_publication *publication=NULL;exr_pager *pager=NULL;const exr_layout *view=NULL;
    exr_chapter_options options=exr_chapter_options_defaults();options.window_bytes=16384;
    OK(exr_publication_open(path,&publication,&error));
    OK(exr_publication_pager_create(publication,0,font,&config,&options,&pager,&error));
    OK(exr_pager_set_cache(pager,2,8*1024*1024,&error));
    OK(exr_pager_get(pager,0,&view,&error));exercise(view,0);
    OK(exr_pager_get(pager,95,&view,&error));exercise(view,0);
    CHECK(exr_pager_chapter_statistics(pager).explicit_snapshot_bytes==0);
    exr_pager_free(pager);exr_publication_free(publication);
  } else {
    OK(exr_document_open(path,&doc,&error));OK(exr_layout_create_ex(doc,font,&config,&layout,&error));
    exercise(layout,0);exr_layout_free(layout);exr_document_free(doc);
  }
}

int main(int argc,char **argv) {
  static const char *const names[]={"complex-text.html","block-border-double.epub","table-border-alpha.epub",
    "table-border-dashed.epub","table-border-dotted.epub","table-border-rtl.epub",
    "table-border-vertical.epub","float-vertical-rl.epub","color-fonts.epub"};
  exr_font *font=NULL;char path[4096];CHECK(argc==4);
  CHECK(!strcmp(exr_version(),EXR_VERSION) && exr_abi_version()==EXR_ABI_VERSION);
  frames=fopen(argv[2],"wb");CHECK(frames);
  snprintf(path,sizeof(path),"%s/fonts/primary.ttf",argv[1]);OK(exr_font_open(path,&font,&error));
  pictures();
  for(size_t i=0;i<sizeof(names)/sizeof(*names);i++) {
    snprintf(path,sizeof(path),"%s/%s",argv[1],names[i]);book(path,font,0);
  }
  book(argv[3],font,1);
  exr_font_free(font);CHECK(fclose(frames)==0);
  printf("{\"accepted\":true,\"cases\":%u,\"checks\":%u,\"sdk\":\"%s\",\"abi\":%u}\n",cases,checks,EXR_VERSION,EXR_ABI_VERSION);
  return 0;
}
