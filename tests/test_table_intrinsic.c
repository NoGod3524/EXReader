/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks; static const char *directory;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static int near(float a,float b) { return fabsf(a-b)<.03f; }
static exr_document *book(const char *name) { char path[4096]; exr_document *d=NULL; snprintf(path,sizeof(path),"%s/%s.epub",directory,name); OK(exr_document_open(path,&d,&error)); return d; }
static const exr_box *named(const exr_document *d,const exr_layout *l,const char *name) {
  size_t n,count,i,j; const exr_node *nodes=exr_document_nodes(d,&n); const exr_box *b=exr_layout_boxes(l,&count);
  for(i=0;i<n;i++) for(j=0;j<nodes[i].attribute_count;j++) if(!strcmp(nodes[i].attributes[j].name,"id") && !strcmp(nodes[i].attributes[j].value,name)) {
    for(j=0;j<count;j++) if(b[j].node==i) return b+j;
    CHECK(0);
  }
  CHECK(0); return NULL;
}
static exr_layout_config config(void) { exr_layout_config c=exr_layout_config_defaults(); c.page=(exr_layout_options){420,160,10,14,1.2f,0}; return c; }
typedef struct { unsigned calls; int stop; } cancellation;
static int cancelled(void *context) { return ((cancellation *)context)->stop; }
static void progress(void *context,exr_stage stage,uint64_t completed,uint64_t total) {
  cancellation *c=context; (void)completed; (void)total;
  if(stage==EXR_STAGE_LAYOUT && ++c->calls==8) c->stop=1;
}
static exr_font *font(const char *name) { char path[4096]; exr_font *f=NULL; snprintf(path,sizeof(path),"%s/%s",directory,name); OK(exr_font_open(path,&f,&error)); return f; }
static void widths(const char *name,exr_font *f,float a,float b,float c) {
  exr_document *d=book(name); exr_layout_config cfg=config(); exr_layout *l=NULL; const exr_box *x,*y;
  exr_status status=exr_layout_create_ex(d,f,&cfg,&l,&error); if(status!=EXR_OK) fprintf(stderr,"fixture %s\n",name); CHECK(status==EXR_OK);
  x=named(d,l,"a"); y=named(d,l,"b");
  if(!near(x->width,a) || !near(y->width,b)) fprintf(stderr,"%s actual %.6f %.6f expected %.6f %.6f\n",name,x->width,y->width,a,b);
  CHECK(near(x->width,a) && near(y->width,b)); CHECK(near(x->x+x->width,y->x));
  if(c) CHECK(near(named(d,l,"c")->width,c));
  if(!strcmp(name,"table-auto-centered")) CHECK(near(x->x,196));
  exr_layout_free(l); exr_document_free(d);
}
static void streaming(exr_font *f) {
  exr_document *d=book("table-auto-streaming"); exr_layout_config cfg=config(); exr_layout *l=NULL; size_t count,n,i,characters=0; const exr_glyph *g;
  cfg.page.height=12000;
  OK(exr_layout_create_ex(d,f,&cfg,&l,&error)); CHECK(near(named(d,l,"b")->width,21));
  exr_layout_pages(l,&count); CHECK(count==1);
  g=exr_layout_glyphs(l,&n); for(i=0;i<n;i++) if(g[i].codepoint=='A') characters++;
  CHECK(characters==8195); exr_layout_free(l); exr_document_free(d);
}
static void pages(exr_font *f) {
  exr_document *d=book("table-auto-pages"); exr_layout_config cfg=config(); exr_layout *whole=NULL;
  exr_pager *fast=NULL,*slow=NULL; const exr_layout *a,*b; size_t i,targets[]={15,12,2,8,0,15,4};
  cfg.page.height=120; OK(exr_layout_create_ex(d,f,&cfg,&whole,&error));
  OK(exr_pager_create(d,f,&cfg,&fast,&error)); OK(exr_pager_create(d,f,&cfg,&slow,&error));
  OK(exr_pager_set_cache(fast,1,65536,&error)); OK(exr_pager_set_checkpoints(fast,32,1024*1024,1,&error)); OK(exr_pager_set_checkpoints(slow,0,0,0,&error));
  for(i=0;i<sizeof(targets)/sizeof(*targets);i++) {
    exr_bitmap x={0},y={0},z={0}; size_t n,m,j; const exr_glyph *ag,*bg;
    OK(exr_pager_get(fast,targets[i],&a,&error)); OK(exr_pager_get(slow,targets[i],&b,&error)); CHECK(a && b);
    ag=exr_layout_glyphs(a,&n); bg=exr_layout_glyphs(b,&m); CHECK(n==m);
    for(j=0;j<n;j++) {
      CHECK(ag[j].start==bg[j].start && ag[j].end==bg[j].end && ag[j].glyph==bg[j].glyph && near(ag[j].x,bg[j].x) && near(ag[j].baseline,bg[j].baseline));
      CHECK(exr_layout_hit_test(a,0,ag[j].x+.1f,ag[j].baseline-2)==exr_layout_hit_test(whole,targets[i],ag[j].x+.1f,ag[j].baseline-2));
    }
    OK(exr_render_page_color(a,NULL,0,&x,&error)); OK(exr_render_page_color(b,NULL,0,&y,&error)); OK(exr_render_page_color(whole,NULL,targets[i],&z,&error));
    CHECK(x.stride==y.stride && x.stride==z.stride && x.height==y.height && x.height==z.height);
    CHECK(!memcmp(x.pixels,y.pixels,(size_t)x.stride*x.height) && !memcmp(x.pixels,z.pixels,(size_t)x.stride*x.height));
    exr_bitmap_free(&x); exr_bitmap_free(&y); exr_bitmap_free(&z);
  }
  CHECK(exr_pager_statistics(fast).restored_checkpoints>0);
  exr_pager_free(fast); exr_pager_free(slow); exr_layout_free(whole); exr_document_free(d);
}
static void cancel_measurement(exr_font *f) {
  exr_document *d=book("table-auto-pages"); exr_layout_config cfg=config(); exr_layout *l=(exr_layout *)(uintptr_t)1; cancellation c={0};
  cfg.control=(exr_control){cancelled,progress,&c};
  CHECK(exr_layout_create_ex(d,f,&cfg,&l,&error)==EXR_CANCELLED && !l && c.stop);
  memset(&cfg.control,0,sizeof(cfg.control)); OK(exr_layout_create_ex(d,f,&cfg,&l,&error)); CHECK(l); exr_layout_free(l); exr_document_free(d);
}
static uint32_t random_value(uint32_t *state) { *state=*state*1664525u+1013904223u; return *state; }
static void generated(exr_font *f) {
  uint32_t seed=180314u; unsigned iteration;
  for(iteration=0;iteration<500;iteration++) {
    exr_node_input nodes[128]={{0}}; exr_attribute attrs[128][2]; char styles[128][128],texts[128][32];
    exr_chapter_input chapter={"generated","generated.unit",1,1}; exr_document_input input={"Generated tables",nodes,0,&chapter,1,NULL,0};
    exr_document *d=NULL; exr_layout *l=NULL; exr_layout_config cfg=config(); size_t used=3,row,columns=2+random_value(&seed)%5,i,n,expected=0,actual=0;
    const exr_box *boxes; const exr_glyph *g; const char *source;
    cfg.page.width=84+(float)(random_value(&seed)%337); cfg.page.height=2048;
    nodes[0]=(exr_node_input){EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0}; nodes[1]=(exr_node_input){EXR_NODE_CHAPTER,0,NULL,NULL,NULL,0};
    snprintf(styles[2],sizeof(styles[2]),"%swidth:%upx",iteration%3==0 ? "table-layout:fixed;" : "",35+random_value(&seed)%250);
    attrs[2][0]=(exr_attribute){"style",styles[2]}; nodes[2]=(exr_node_input){EXR_NODE_TABLE,1,"table",NULL,attrs[2],iteration%4==0 ? 0u : 1u};
    for(row=0;row<3;row++) {
      size_t parent=used++,column=0; nodes[parent]=(exr_node_input){EXR_NODE_ROW,2,"tr",NULL,NULL,0};
      while(column<columns) {
        size_t cell=used++,text=used++,span=(row==0 && column+1<columns && random_value(&seed)%3==0) ? 2 : 1;
        unsigned which=random_value(&seed)%4,letters=1+random_value(&seed)%9,k; size_t length=0;
        snprintf(styles[cell],sizeof(styles[cell]),"width:%u%s;direction:%s",1+random_value(&seed)%200,which==0 ? "%" : "px",iteration%2 ? "rtl" : "ltr");
        if(which==3) strcpy(styles[cell],"width:.01px");
        { const char *align[]={"baseline","top","middle","bottom"}; size_t used_style=strlen(styles[cell]);
          snprintf(styles[cell]+used_style,sizeof(styles[cell])-used_style,";vertical-align:%s;font-size:%upx;height:%upx",align[random_value(&seed)%4],14+7*(random_value(&seed)%3),10+random_value(&seed)%71);
        }
        attrs[cell][0]=(exr_attribute){"style",styles[cell]}; attrs[cell][1]=(exr_attribute){"colspan","2"};
        nodes[cell]=(exr_node_input){EXR_NODE_CELL,parent,"td",NULL,attrs[cell],span==2 ? 2u : 1u};
        for(k=0;k<letters;k++) { texts[text][length++]='A'; if(k+1<letters && iteration%2) texts[text][length++]=' '; } texts[text][length]=0;
        nodes[text]=(exr_node_input){EXR_NODE_TEXT,cell,NULL,texts[text],NULL,0}; column+=span;
      }
    }
    input.node_count=used; OK(exr_document_create(&input,&d,&error));
    { exr_status status=exr_layout_create_ex(d,f,&cfg,&l,&error);
      if(status!=EXR_OK) {
        fprintf(stderr,"generated case %u viewport %.3f table %s\n",iteration,cfg.page.width,nodes[2].attribute_count ? styles[2] : "auto");
        for(i=0;i<used;i++) if(nodes[i].kind==EXR_NODE_CELL) fprintf(stderr,"cell %zu span %zu %s text %s\n",i,nodes[i].attribute_count,styles[i],texts[i+1]);
      }
      CHECK(status==EXR_OK);
    }
    source=exr_document_text(d,&n); for(i=0;i<n;i++) expected+=source[i]=='A';
    g=exr_layout_glyphs(l,&n); for(i=0;i<n;i++) actual+=g[i].codepoint=='A'; CHECK(actual==expected);
    boxes=exr_layout_boxes(l,&n); for(i=0;i<n;i++) CHECK(isfinite(boxes[i].x) && isfinite(boxes[i].width) && isfinite(boxes[i].y) && isfinite(boxes[i].height) && boxes[i].x>=9.99f && boxes[i].y>=9.99f && boxes[i].width>0 && boxes[i].x+boxes[i].width<=cfg.page.width-9.99f && boxes[i].y+boxes[i].height<=cfg.page.height-9.99f);
    exr_layout_free(l); exr_document_free(d);
  }
}
int main(int argc,char **argv) {
  exr_font *primary,*shaping,*fallback=NULL; exr_font_input sources[2]={{0}}; unsigned char *bytes[2]={0}; size_t i;
  CHECK(argc==2); directory=argv[1]; primary=font("fonts/primary.ttf"); shaping=font("shaping/shaping.ttf");
  widths("table-auto-content",primary,7,21,0);
  widths("table-auto-range",primary,7,21,0);
  widths("table-auto-extra",primary,70.0f/6,70.0f*5/6,0);
  widths("table-auto-centered",primary,7,21,0);
  widths("table-auto-later-row",primary,42,7,0);
  widths("table-fixed-later-row",primary,35,35,0);
  widths("table-auto-span",primary,24.5f,24.5f,21);
  widths("table-auto-soft",primary,21,7,0);
  widths("table-auto-nested",primary,28,7,0);
  widths("table-auto-multi-block",primary,21,7,0);
  widths("table-auto-image",primary,80,7,0);
  widths("table-auto-fixed-image",primary,40,7,0);
  widths("table-auto-fixed-block",primary,40,7,0);
  widths("table-auto-percent-block",primary,21,7,0);
  widths("table-auto-mixed-size",primary,21,7,0);
  widths("table-auto-insets",primary,19,7,0);
  widths("table-auto-break",primary,21,7,0);
  widths("table-auto-script",shaping,10,24,0); /* 700-unit lam-alef ligature, integer FT advances. */
  { exr_document *d=book("table-column-float-floor"); exr_layout_config cfg=config(); exr_layout *l=NULL; const exr_box *boxes; size_t n,j;
    OK(exr_layout_create_ex(d,primary,&cfg,&l,&error)); boxes=exr_layout_boxes(l,&n);
    for(j=0;j<n;j++) if(boxes[j].kind==EXR_BOX_CELL) CHECK(boxes[j].width>=1);
    exr_layout_free(l); exr_document_free(d);
  }
  for(i=0;i<2;i++) {
    char path[4096]; FILE *file; long n; snprintf(path,sizeof(path),"%s/fonts/%s.ttf",directory,i ? "fallback" : "primary");
    file=fopen(path,"rb"); CHECK(file && !fseek(file,0,SEEK_END)); n=ftell(file); CHECK(n>0); rewind(file); bytes[i]=malloc((size_t)n); CHECK(bytes[i] && fread(bytes[i],1,(size_t)n,file)==(size_t)n); fclose(file);
    sources[i].data=bytes[i]; sources[i].size=(size_t)n;
  }
  OK(exr_font_create(sources,2,&fallback,&error)); for(i=0;i<2;i++) free(bytes[i]);
  widths("table-auto-grapheme",fallback,13,21,0);
  widths("table-auto-cjk",fallback,25,7,0);
  { exr_document *d=book("table-auto-vertical"); exr_layout_config cfg=config(); exr_layout *l=NULL;
    OK(exr_layout_create_ex(d,primary,&cfg,&l,&error)); CHECK(near(named(d,l,"a")->height,7) && near(named(d,l,"b")->height,21)); exr_layout_free(l); exr_document_free(d);
  }
  generated(primary); cancel_measurement(primary); pages(primary); streaming(primary); exr_font_free(fallback); exr_font_free(primary); exr_font_free(shaping);
  printf("%u intrinsic table checks passed\n",checks); return 0;
}
