/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
#define WGHT EXR_TAG('w','g','h','t')
#define WDTH EXR_TAG('w','d','t','h')
static exr_font_input load(const char *directory,const char *name) {
  char path[4096]; FILE *f; long size; exr_font_input input={0};
  snprintf(path,sizeof(path),"%s/%s",directory,name); f=fopen(path,"rb"); CHECK(f && !fseek(f,0,SEEK_END)); size=ftell(f); CHECK(size>0); rewind(f);
  input.size=(size_t)size; input.data=malloc(input.size); CHECK(input.data && fread((void *)input.data,1,input.size,f)==input.size && !fclose(f)); return input;
}
static void close_to(double a,double b) { CHECK(fabs(a-b)<0.03); }
static exr_font *create(const exr_font_input *inputs,size_t count,const exr_font_coordinate *coordinates,size_t n) {
  exr_font *font=NULL; OK(exr_font_create_variable(inputs,count,coordinates,n,&font,&error)); CHECK(font && exr_font_count(font)==count); return font;
}
static exr_font_axis *snapshot(exr_font *font,size_t index,size_t expected) {
  exr_font_axis *axes=NULL; size_t count=99; OK(exr_font_axes(font,index,&axes,&count,&error)); CHECK(count==expected && (expected ? axes!=NULL : axes==NULL)); return axes;
}
static exr_shaped_glyph *shape(exr_font *font,const char *text,int vertical,size_t expected) {
  exr_shape_options options=exr_shape_defaults(); exr_shaped_glyph *out=NULL; size_t n=0; options.font_size=100;
  OK(vertical ? exr_shape_vertical(font,0,text,strlen(text),&options,&out,&n,&error) : exr_shape(font,0,text,strlen(text),&options,&out,&n,&error)); CHECK(n==expected); return out;
}
static double top(exr_font *font,uint32_t glyph) {
  exr_path_segment *segments=NULL; size_t n,i,j; double result=-1e20; OK(exr_font_glyph_outline(font,0,glyph,&segments,&n,NULL,&error)); CHECK(n>0);
  for(i=0;i<n;i++) { size_t points=segments[i].verb==EXR_PATH_CUBIC ? 3 : segments[i].verb==EXR_PATH_QUAD ? 2 : segments[i].verb==EXR_PATH_CLOSE ? 0 : 1;
    for(j=0;j<points;j++) if(segments[i].points[j].y>result) result=segments[i].points[j].y;
  }
  exr_free(segments); return result;
}
static void rejection(const exr_font_input *inputs,exr_font_coordinate *coordinates,size_t count,exr_status status) {
  exr_font *font=(exr_font *)(uintptr_t)1; CHECK(exr_font_create_variable(inputs,2,coordinates,count,&font,&error)==status && !font);
}
static void axes_and_shaping(const char *directory) {
  exr_font_input inputs[2]={load(directory,"variable.ttf"),load(directory,"primary.ttf")};
  exr_font_coordinate coordinates[2]={{0,WGHT,900},{0,WDTH,150}}; exr_font_axis *axes; exr_shaped_glyph *g; exr_font *base=create(inputs,2,NULL,0),*wide=create(inputs,2,coordinates,2),*mapped,*named;
  axes=snapshot(base,0,2); CHECK(axes[0].tag==WGHT && axes[1].tag==WDTH && !(axes[0].flags&EXR_FONT_AXIS_HIDDEN) && (axes[1].flags&EXR_FONT_AXIS_HIDDEN));
  close_to(axes[0].minimum,100); close_to(axes[0].initial,400); close_to(axes[0].maximum,900); close_to(axes[0].value,400); exr_free(axes); CHECK(!snapshot(base,1,0));
  axes=snapshot(wide,0,2); close_to(axes[0].value,900); close_to(axes[1].value,150); exr_free(axes);
  g=shape(base,"AV",0,2); CHECK(g[0].glyph==2 && g[1].glyph==3); close_to(g[0].advance_x,45); close_to(g[1].advance_x,50); exr_free(g);
  g=shape(wide,"AV",0,2); CHECK(g[0].glyph==4); close_to(g[0].advance_x,69.5); close_to(g[1].advance_x,80); exr_free(g);
  close_to(top(base,2),700); close_to(top(wide,2),750); close_to(top(wide,4),600);
  g=shape(base,"A\xcc\x81",0,2); CHECK(!g[1].advance_x); close_to(g[1].offset_y,70); exr_free(g);
  g=shape(wide,"A\xcc\x81",0,2); CHECK(g[0].glyph==4 && !g[1].advance_x); close_to(g[1].offset_y,60); exr_free(g);
  g=shape(wide,"V",1,1); close_to(g[0].advance_y,-105); exr_free(g);
  coordinates[0].value=650; mapped=create(inputs,2,coordinates,1); g=shape(mapped,"AV",0,2); CHECK(g[0].glyph==4); close_to(g[0].advance_x,45); close_to(g[1].advance_x,53); exr_free(g); exr_font_free(mapped);
  inputs[0].face_index=1u<<16; named=create(inputs,1,NULL,0); axes=snapshot(named,0,2); close_to(axes[0].value,900); close_to(axes[1].value,100); exr_free(axes); g=shape(named,"AV",0,2); CHECK(g[0].glyph==4); close_to(g[0].advance_x,45); close_to(g[1].advance_x,55); exr_free(g); exr_font_free(named); inputs[0].face_index=0;
  coordinates[0].value=100; coordinates[1].value=50; mapped=create(inputs,2,coordinates,2); g=shape(mapped,"AV",0,2); CHECK(g[0].glyph==2); close_to(g[0].advance_x,20.5); close_to(g[1].advance_x,22); exr_free(g); exr_font_free(mapped);
  axes=snapshot(base,0,2); close_to(axes[0].value,400); exr_font_free(base); close_to(axes[0].value,400); exr_free(axes);
  { exr_font_axis *out=(exr_font_axis *)(uintptr_t)1; size_t n=99; CHECK(exr_font_axes(wide,2,&out,&n,&error)==EXR_ARGUMENT && !out && !n); }
  coordinates[0]=(exr_font_coordinate){0,WGHT,99}; rejection(inputs,coordinates,1,EXR_ARGUMENT); coordinates[0].value=901; rejection(inputs,coordinates,1,EXR_ARGUMENT);
  coordinates[0].value=NAN; rejection(inputs,coordinates,1,EXR_ARGUMENT); coordinates[0].value=INFINITY; rejection(inputs,coordinates,1,EXR_ARGUMENT);
  coordinates[0]=(exr_font_coordinate){0,EXR_TAG('n','o','n','e'),100}; rejection(inputs,coordinates,1,EXR_ARGUMENT);
  coordinates[0]=(exr_font_coordinate){1,WGHT,100}; rejection(inputs,coordinates,1,EXR_ARGUMENT);
  coordinates[0]=(exr_font_coordinate){2,WGHT,100}; rejection(inputs,coordinates,1,EXR_ARGUMENT);
  coordinates[0]=(exr_font_coordinate){0,WGHT,100}; coordinates[1]=coordinates[0]; rejection(inputs,coordinates,2,EXR_ARGUMENT); rejection(inputs,coordinates,2049,EXR_LIMIT);
  exr_font_free(wide); free((void *)inputs[0].data); free((void *)inputs[1].data);
}
static void effective_font(const char *directory) {
  exr_font_input input=load(directory,"variable.ttf"),inner=load(directory,"primary.ttf"); exr_font_coordinate point={0,WGHT,900}; exr_font *font=create(&input,1,&point,1),*effective;
  exr_attribute first={"style","font-family:Inner"},second={"style","font-family:'EXR Variable Test'"};
  exr_node_input nodes[]={{EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0},{EXR_NODE_CHAPTER,0,NULL,NULL,NULL,0},
    {EXR_NODE_PARAGRAPH,1,NULL,NULL,&first,1},{EXR_NODE_TEXT,2,NULL,"A",NULL,0},{EXR_NODE_PARAGRAPH,1,NULL,NULL,&second,1},{EXR_NODE_TEXT,4,NULL,"AV",NULL,0}};
  exr_chapter_input chapter={"font","font.unit",1,1}; exr_resource_input resource={{"inner","inner.ttf","font/ttf",""},inner.data,inner.size};
  exr_document_input model={"Variable inheritance",nodes,6,&chapter,1,&resource,1}; exr_document *doc=NULL; exr_layout *layout=NULL; exr_layout_config config=exr_layout_config_defaults(); exr_font_axis *axes;
  config.user_css="@font-face{font-family:Inner;src:url('inner.ttf')}"; config.page=(exr_layout_options){240,240,12,24,1.2f,4};
  OK(exr_document_create(&model,&doc,&error)); OK(exr_layout_create_ex(doc,font,&config,&layout,&error)); effective=exr_layout_font(layout); CHECK(effective && exr_font_count(effective)==2);
  axes=snapshot(effective,0,2); close_to(axes[0].value,900); exr_free(axes);
  { size_t count,i; const exr_glyph *g=exr_layout_glyphs(layout,&count); int found=0; for(i=0;i<count;i++) if(g[i].node==5 && g[i].codepoint=='A') { CHECK(g[i].font_index==0 && g[i].glyph==4); found=1; } CHECK(found); }
  exr_font_free(font); { exr_bitmap image={0}; OK(exr_render_page(layout,effective,0,&image,&error)); CHECK(image.width==240 && image.height==240); exr_bitmap_free(&image); }
  exr_layout_free(layout); exr_document_free(doc); free((void *)input.data); free((void *)inner.data);
}
int main(int argc,char **argv) { CHECK(argc==2); axes_and_shaping(argv[1]); effective_font(argv[1]); printf("%u variable font axes, shaping, outlines and inheritance checks passed\n",checks); return 0; }
