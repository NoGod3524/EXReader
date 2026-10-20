/* SPDX-License-Identifier: MIT */
#if !defined(_WIN32) && !defined(_POSIX_C_SOURCE)
#define _POSIX_C_SOURCE 200809L
#endif
#include "exreader.h"
#if EXR_FUZZ_PIPELINE < 1 || EXR_FUZZ_PIPELINE > 3
#error EXR_FUZZ_PIPELINE must select font, layout or render
#endif
static exr_status exercise(exr_format,const unsigned char *,size_t);
static const char *record_name(exr_format);
static exr_format record_format(const char *);
/* Share the exact mutation and persistence loop with the parser driver. */
#define EXR_FUZZ_PROCESS exercise
#define EXR_FUZZ_RECORD_NAME record_name
#define EXR_FUZZ_RECORD_PARSE record_format
#define EXR_FUZZ_RESULT_LABEL "completed the selected pipeline"
#define main pipeline_runner
#include "fuzz_parse.c"
#undef main
#include <math.h>

static exr_font *host_font;
static const char *stage(void) { return EXR_FUZZ_PIPELINE==1 ? "font" : EXR_FUZZ_PIPELINE==2 ? "layout" : "render"; }
static const char *record_name(exr_format format) {
  static char name[32];
  if(EXR_FUZZ_PIPELINE==1) return "font";
  snprintf(name,sizeof(name),"%s:%s",stage(),format_name(format));return name;
}
static exr_format record_format(const char *name) {
  size_t n=strlen(stage());
  if(EXR_FUZZ_PIPELINE==1) return !strcmp(name,"font") ? EXR_TXT : EXR_CUSTOM;
  return !strncmp(name,stage(),n) && name[n]==':' ? named_format(name+n+1) : EXR_CUSTOM;
}
static void require(int condition,const char *message) {
  if(!condition) { fprintf(stderr,"%s invariant: %s\n",stage(),message);abort(); }
}
static int cancelled(void *context) { unsigned *polls=context;return ++*polls>4096; }
static void bitmap_check(exr_status status,const exr_bitmap *b,unsigned channels) {
  if(status!=EXR_OK) { require(!b->pixels,"failed render retained pixels");return; }
  require(b->pixels && b->width && b->height && b->channels==channels,"invalid bitmap");
  require(b->width<=256 && b->height<=256 && b->stride>=(size_t)b->width*channels,"bitmap exceeds test viewport");
  volatile unsigned char sample=b->pixels[(size_t)(b->height-1)*b->stride+(size_t)(b->width-1)*channels];(void)sample;
}
static exr_status font_exercise(const unsigned char *data,size_t size,exr_control control) {
  const char text[]="ABC AV ffi a\xcc\x81 \xd8\xa8\xd9\x84\xd8\xa7 \xe0\xa4\x95\xe0\xa4\xbf \xe0\xb8\x81 \xe7\x94\xb2 \xf0\x9f\x98\x80";
  exr_font *font=NULL;exr_font_input input={data,size,0};exr_error error={0};exr_status status;
  exr_font_axis *axes=NULL;size_t axes_count=0;
  status=exr_font_create_glyphs(&input,1,&font,&error);require((status==EXR_OK)==!!font,"font open ownership");
  if(status!=EXR_OK) return status;
  status=exr_font_axes(font,0,&axes,&axes_count,&error);
  if(status==EXR_OK) for(size_t i=0;i<axes_count;i++) require(isfinite(axes[i].value) && axes[i].minimum<=axes[i].value && axes[i].value<=axes[i].maximum,"invalid font axis");
  exr_free(axes);
  for(unsigned mode=0;mode<3 && status==EXR_OK;mode++) {
    exr_shape_options options=exr_shape_defaults();exr_shaped_glyph *glyphs=NULL;size_t count=0;
    options.font_size=16;options.direction=mode==1 ? EXR_DIRECTION_RTL : EXR_DIRECTION_LTR;options.control=control;
    status=mode==2 ? exr_shape_vertical(font,0,text,sizeof(text)-1,&options,&glyphs,&count,&error) : exr_shape(font,0,text,sizeof(text)-1,&options,&glyphs,&count,&error);
    if(status!=EXR_OK) require(!glyphs && !count,"failed shaping retained output");
    else {
      require(!count || glyphs,"missing shaped glyphs");
      for(size_t i=0;i<count && status==EXR_OK;i++) {
        exr_path_segment *outline=NULL;size_t segments=0;exr_glyph_image image={0};exr_font_color_layer *layers=NULL;size_t layer_count=0;
        const exr_shaped_glyph *g=glyphs+i;
        exr_font_color_info color={0};color.struct_size=sizeof(color);
        require(g->start<=g->end && g->end<sizeof(text),"shaping source range");
        require(isfinite(g->advance_x) && isfinite(g->advance_y) && isfinite(g->offset_x) && isfinite(g->offset_y),"non-finite shaped glyph");
        status=exr_font_color_info_get(font,0,g->glyph,&color,&control,&error);
        if(status==EXR_OK) status=exr_font_glyph_outline(font,0,g->glyph,&outline,&segments,&control,&error);
        if(status==EXR_OK) for(size_t j=0;j<segments;j++) {
          require(outline[j].verb>=EXR_PATH_MOVE && outline[j].verb<=EXR_PATH_CLOSE,"outline verb");
          unsigned points=outline[j].verb==EXR_PATH_CUBIC ? 3 : outline[j].verb==EXR_PATH_QUAD ? 2 : outline[j].verb==EXR_PATH_CLOSE ? 0 : 1;
          for(unsigned k=0;k<points;k++) require(isfinite(outline[j].points[k].x) && isfinite(outline[j].points[k].y),"non-finite outline");
        }
        exr_free(outline);
        if(status==EXR_OK) status=exr_font_glyph_image(font,0,g->glyph,16,&image,&control,&error);
        if(status==EXR_OK && image.bitmap.pixels) require(image.bitmap.channels==4 && image.bitmap.stride>=(size_t)image.bitmap.width*4,"glyph image storage");
        exr_bitmap_free(&image.bitmap);
        if(status==EXR_OK) status=exr_font_color_layers(font,0,g->glyph,0,0xffffffff,&layers,&layer_count,&control,&error);
        if(status==EXR_OK) require(layer_count<=256 && (!layer_count || layers),"colour glyph layers");
        exr_free(layers);
      }
    }
    exr_free(glyphs);
  }
  if(status==EXR_OK) {
    exr_document *doc=NULL;exr_layout *layout=NULL;exr_bitmap bitmap={0};
    exr_layout_config config=exr_layout_config_defaults();config.page=(exr_layout_options){192,256,8,16,1.25f,0};config.control=control;
    status=exr_document_open_memory(EXR_TXT,text,sizeof(text)-1,&doc,&error);
    if(status==EXR_OK) status=exr_layout_create_ex(doc,font,&config,&layout,&error);
    require((status==EXR_OK)==!!layout,"font render layout ownership");
    if(status==EXR_OK) { status=exr_render_page_ex(layout,font,0,4,&control,&bitmap,&error);bitmap_check(status,&bitmap,4); }
    exr_bitmap_free(&bitmap);exr_layout_free(layout);exr_document_free(doc);
  }
  exr_font_free(font);return status;
}
static void layout_check(const exr_layout *layout,size_t source_size) {
  size_t count=0;const exr_page *pages=exr_layout_pages(layout,&count);require(count==1 && pages,"pager page count");
  require(pages[0].start<=pages[0].end && pages[0].end<=source_size,"page source range");
  const exr_glyph *glyphs=exr_layout_glyphs(layout,&count);require(!count || glyphs,"missing page glyphs");
  for(size_t i=0;i<count;i++) {
    const exr_glyph *g=glyphs+i;
    require(g->start<=g->end && g->end<=source_size,"glyph source range");
    require(isfinite(g->x) && isfinite(g->baseline) && isfinite(g->advance) && isfinite(g->size),"non-finite layout glyph");
  }
  const exr_box *boxes=exr_layout_boxes(layout,&count);require(!count || boxes,"missing page boxes");
  for(size_t i=0;i<count;i++) require(isfinite(boxes[i].x) && isfinite(boxes[i].y) && isfinite(boxes[i].width) && isfinite(boxes[i].height),"non-finite layout box");
}
static exr_status reflow_exercise(exr_format format,const unsigned char *data,size_t size,exr_control control) {
  exr_document *doc=NULL;exr_pager *pager=NULL;exr_layout *page=NULL;exr_error error={0};exr_status status;size_t source_size;
  exr_layout_config config=exr_layout_config_defaults();config.page=(exr_layout_options){192,256,8,16,1.25f,0};config.control=control;
  status=exr_document_open_memory(format,data,size,&doc,&error);require((status==EXR_OK)==!!doc,"document open ownership");
  if(status!=EXR_OK) return status;
  (void)exr_document_text(doc,&source_size);
  status=exr_pager_create(doc,host_font,&config,&pager,&error);require((status==EXR_OK)==!!pager,"pager ownership");
  for(unsigned i=0;i<4 && status==EXR_OK;i++) {
    status=exr_pager_next(pager,&page,&error);
    if(status!=EXR_OK) { require(!page,"failed pager retained output");break; }
    if(!page) break;
    layout_check(page,source_size);
    if(EXR_FUZZ_PIPELINE==3) for(unsigned channels=1;channels<=4 && status==EXR_OK;channels+=3) {
      exr_bitmap b={0};status=exr_render_page_ex(page,exr_layout_font(page),0,channels,&control,&b,&error);bitmap_check(status,&b,channels);exr_bitmap_free(&b);
    }
    exr_layout_free(page);page=NULL;
  }
  exr_layout_free(page);exr_pager_free(pager);exr_document_free(doc);return status;
}
static exr_status fixed_exercise(exr_format format,const unsigned char *data,size_t size,exr_control control) {
  exr_fixed_document *doc=NULL;exr_fixed_open_options open={0};exr_fixed_render_options options={0};exr_error error={0};size_t count=0;exr_status status;
  open.struct_size=sizeof(open);open.control=control;open.fallback_font=host_font;options.control=control;
  status=exr_fixed_open_memory(format,data,size,&open,&doc,&error);require((status==EXR_OK)==!!doc,"fixed open ownership");
  if(status!=EXR_OK) return status;
  const exr_fixed_page *pages=exr_fixed_pages(doc,&count);require(!count || pages,"missing fixed pages");
  for(size_t i=0;i<count && i<4 && status==EXR_OK;i++) {
    double width=(pages[i].geometry.bounds[2]-pages[i].geometry.bounds[0])*pages[i].geometry.unit_scale;
    double height=(pages[i].geometry.bounds[3]-pages[i].geometry.bounds[1])*pages[i].geometry.unit_scale;
    double scale=fmin(1,fmin(255/width,255/height));
    if(!(width>0) || !(height>0) || !isfinite(scale) || !(scale>0)) { status=EXR_FORMAT;break; }
    for(unsigned channels=1;channels<=4 && status==EXR_OK;channels+=3) {
      exr_bitmap b={0};options.channels=channels;status=exr_fixed_render(doc,i,scale,&options,&b,&error);bitmap_check(status,&b,channels);exr_bitmap_free(&b);
    }
  }
  exr_fixed_free(doc);return status;
}
static exr_status exercise(exr_format format,const unsigned char *data,size_t size) {
  unsigned polls=0;exr_control control={cancelled,NULL,&polls};
  if(EXR_FUZZ_PIPELINE==1) return font_exercise(data,size,control);
  if(format==EXR_PDF || format==EXR_CBZ) return EXR_FUZZ_PIPELINE==3 ? fixed_exercise(format,data,size,control) : EXR_UNSUPPORTED;
  return reflow_exercise(format,data,size,control);
}
int main(int argc,char **argv) {
  int count=1,result;const char *font_path=NULL;exr_error error={0};
  for(int i=1;i<argc;i++) {
    if(!strcmp(argv[i],"--font") && i+1<argc) font_path=argv[++i];
    else argv[count++]=argv[i];
  }
  if(EXR_FUZZ_PIPELINE!=1) {
    if(!font_path || exr_font_open(font_path,&host_font,&error)!=EXR_OK) { fprintf(stderr,"%s requires a valid --font: %s\n",stage(),error.message);return 2; }
  }
  result=pipeline_runner(count,argv);exr_font_free(host_font);return result;
}
