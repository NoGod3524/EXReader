/* SPDX-License-Identifier: MIT */
/* text-combine-upright (CSS Writing Modes 3): 2-4 digits, or a short run under
   `all`, become one em-wide horizontal block in vertical text. */
#include "exreader.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error;
static unsigned checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr,"line %d: %s (%d %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static int near(float a,float b) { return fabsf(a-b)<.02f; }
static const char VERTICAL[]="writing-mode:vertical-rl;";
static exr_document *document(const char *text) {
  exr_document *doc=NULL; exr_attribute id={"id","body"};
  exr_node_input nodes[]={{EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0},
    {EXR_NODE_CHAPTER,0,NULL,NULL,NULL,0},{EXR_NODE_PARAGRAPH,1,"p",NULL,&id,1},
    {EXR_NODE_TEXT,2,NULL,text,NULL,0}};
  exr_chapter_input chapter={"combine","combine.xhtml",1,1};
  exr_document_input input={"combine",nodes,4,&chapter,1,NULL,0};
  OK(exr_document_create(&input,&doc,&error)); return doc;
}
static exr_layout *layout(exr_font *font,const char *text,const char *css,float height) {
  char all[400]; exr_document *doc=document(text); exr_layout *l=NULL; exr_layout_config c=exr_layout_config_defaults();
  c.page.width=100; c.page.height=height; c.page.margin=10;
  c.page.font_size=20; c.page.line_height=1.2f; c.page.paragraph_spacing=0;
  snprintf(all,sizeof(all),"#body{text-indent:0}%s",css); c.user_css=all; /* no default CJK first-line indent */
  OK(exr_layout_create_ex(doc,font,&c,&l,&error)); exr_document_free(doc); return l;
}
static unsigned combined(const exr_glyph *g,size_t n) {
  unsigned count=0; size_t i;
  for(i=0;i<n;i++) count+=!!(g[i].flags&EXR_GLYPH_COMBINED);
  return count;
}
/* Ink of the test digits spans y 0..700 of 1000 units above the baseline. */
static float ink_centre(const exr_glyph *g) { return g->baseline-g->offset_y-.35f*g->size; }
static void block_width_and_centre(exr_font *font) {
  /* U+7532 12 U+7532: the block advances exactly 1em, is scaled 20/24 and is centred on its em. */
  exr_layout *l=layout(font,"\xe7\x94\xb2" "12\xe7\x94\xb2","#body{" "writing-mode:vertical-rl;text-combine-upright:digits}",140);
  size_t n; const exr_glyph *g=exr_layout_glyphs(l,&n);
  float scale=20.f/24.f,cell;
  CHECK(n==4 && combined(g,n)==2);
  CHECK(!(g[0].flags&EXR_GLYPH_COMBINED) && !(g[3].flags&EXR_GLYPH_COMBINED));
  CHECK((g[1].flags&EXR_GLYPH_VERTICAL) && !(g[1].flags&EXR_GLYPH_SIDEWAYS));
  CHECK(near(g[1].advance,0) && near(g[2].advance,20));                   /* width = 1em */
  CHECK(near(g[3].baseline-g[0].baseline,40));                             /* one em between the ideographs' cells */
  CHECK(near(g[1].baseline,g[0].baseline+20) && near(g[2].baseline,g[1].baseline));
  CHECK(near(g[1].size,20*scale) && near(g[2].size,20*scale));             /* internal scale */
  CHECK(near(g[1].x,g[0].x) && near(g[2].x,g[0].x));                       /* same column */
  /* Horizontal extent: first digit starts at -10 from the column centre, the second ends at +10. */
  CHECK(near(g[1].offset_x,-10) && near(g[2].offset_x,-10+12*scale));
  CHECK(near(g[2].offset_x+.55f*g[2].size,10-.05f*g[2].size));
  /* Vertical centring on the em box: ink centre sits half an em below the cell start. */
  cell=g[1].baseline;
  CHECK(near(ink_centre(&g[1]),cell+10) && near(ink_centre(&g[2]),cell+10));
  CHECK(near(g[1].offset_y,g[2].offset_y));
  exr_layout_free(l);
}
static void four_digits_fit(exr_font *font) {
  exr_layout *l=layout(font,"2026","#body{writing-mode:vertical-rl;text-combine-upright:digits 4}",140);
  size_t n,i; const exr_glyph *g=exr_layout_glyphs(l,&n);
  float scale=20.f/48.f;
  CHECK(n==4 && combined(g,n)==4);
  for(i=0;i<4;i++) {
    float left=g[i].x+g[i].offset_x+.05f*g[i].size,right=g[i].x+g[i].offset_x+.55f*g[i].size;
    CHECK(near(g[i].size,20*scale) && near(g[i].advance,i==3 ? 20 : 0));
    CHECK(left>=g[0].x-10-.02f && right<=g[0].x+10+.02f);
    if(i) CHECK(near(g[i].offset_x-g[i-1].offset_x,12*scale));             /* adjacent digits stay readable */
  }
  CHECK(near(g[0].offset_x,-10) && near(g[3].offset_x+.55f*g[3].size,10-.05f*g[3].size));
  CHECK(near(ink_centre(&g[2]),g[0].baseline+10));
  exr_layout_free(l);
}
static void modes_and_rejections(exr_font *font) {
  struct { const char *text,*css; unsigned expect; } cases[]={
    {"12","text-combine-upright:none",0},            /* default and explicit none */
    {"12","",0},
    {"12345","text-combine-upright:digits 4",0},     /* run longer than N */
    {"12345","text-combine-upright:digits",0},
    {"123","text-combine-upright:digits",0},         /* default N is 2 */
    {"1","text-combine-upright:digits",0},           /* a lone digit is not a block */
    {"1.2","text-combine-upright:digits 4",0},       /* digits never swallow punctuation */
    {"1.2","text-combine-upright:all",3},            /* all takes punctuation */
    {"12345","text-combine-upright:all",0},          /* more than four characters */
    {"12","text-combine-upright:digits 5",0},        /* invalid value ignored */
    {"12","-epub-text-combine:horizontal",2},        /* legacy EPUB alias for all */
    {"12","-webkit-text-combine:horizontal",2},
    {"12","text-combine-upright:all;text-combine-upright:none",0}, /* later declaration overrides */
    {"\xe7\x94\xb2" "12","text-combine-upright:all",0}, /* ideograph + 2 digits is a 3-character run, not a lone digit pair */
  };
  size_t i;
  cases[sizeof(cases)/sizeof(*cases)-1].expect=3;
  for(i=0;i<sizeof(cases)/sizeof(*cases);i++) {
    char css[300]; size_t n; exr_layout *l; const exr_glyph *g;
    snprintf(css,sizeof(css),"#body{%s%s}",VERTICAL,cases[i].css);
    l=layout(font,cases[i].text,css,140); g=exr_layout_glyphs(l,&n);
    if(combined(g,n)!=cases[i].expect) fprintf(stderr,"case %zu: %u combined, expected %u\n",i,combined(g,n),cases[i].expect);
    CHECK(combined(g,n)==cases[i].expect);
    exr_layout_free(l);
  }
  puts("14 mode and rejection cases passed");
}
static void horizontal_untouched(exr_font *font) {
  const char *text="\xe7\x94\xb2" "12 2026\xe7\x94\xb2";
  exr_layout *plain=layout(font,text,"#body{writing-mode:horizontal-tb}",140);
  exr_layout *asked=layout(font,text,"#body{writing-mode:horizontal-tb;text-combine-upright:all}",140);
  size_t a,b,i; const exr_glyph *ga=exr_layout_glyphs(plain,&a),*gb=exr_layout_glyphs(asked,&b);
  CHECK(a==b && a && combined(gb,b)==0);
  for(i=0;i<a;i++) CHECK(ga[i].glyph==gb[i].glyph && ga[i].flags==gb[i].flags && near(ga[i].x,gb[i].x) &&
                         near(ga[i].baseline,gb[i].baseline) && near(ga[i].advance,gb[i].advance) && near(ga[i].size,gb[i].size));
  exr_layout_free(asked); exr_layout_free(plain);
}
static void unbreakable(exr_font *font) {
  /* A 130px page leaves 110px = 5.5em per column. Five ideographs leave half an em: the 1em block
     must move to the next column whole instead of being split or overflowing. */
  exr_layout *l=layout(font,"\xe7\x94\xb2\xe7\x94\xb2\xe7\x94\xb2\xe7\x94\xb2\xe7\x94\xb2" "12\xe7\x94\xb2",
                       "#body{writing-mode:vertical-rl;text-combine-upright:digits}",130);
  size_t n; const exr_glyph *g=exr_layout_glyphs(l,&n);
  CHECK(n==8 && combined(g,n)==2);
  CHECK(near(g[4].baseline+20,g[0].baseline+110));  /* the half-em tail is spread over the four gaps, not given to the block */
  CHECK(g[5].x<g[4].x-1);                       /* next column, to the left in vertical-rl */
  CHECK(near(g[5].x,g[6].x));                   /* both digits stay together */
  CHECK(near(g[5].baseline,g[0].baseline) && near(g[6].baseline,g[0].baseline));
  CHECK(near(g[7].baseline,g[0].baseline+20) && near(g[7].x,g[5].x));
  exr_layout_free(l);
  /* The same text without combining splits nothing special: digits lie sideways on the half-em tail. */
  l=layout(font,"\xe7\x94\xb2\xe7\x94\xb2\xe7\x94\xb2\xe7\x94\xb2\xe7\x94\xb2" "12\xe7\x94\xb2",
           "#body{writing-mode:vertical-rl}",130);
  g=exr_layout_glyphs(l,&n);
  CHECK(n==8 && combined(g,n)==0 && (g[5].flags&EXR_GLYPH_SIDEWAYS));
  exr_layout_free(l);
}
static void matrix_and_pages(exr_font *font) {
  /* Public transform: an unrotated, scaled horizontal glyph at the stored offsets. */
  exr_layout *l=layout(font,"12","#body{writing-mode:vertical-rl;text-combine-upright:digits}",140);
  size_t n; const exr_glyph *g=exr_layout_glyphs(l,&n);
  double m[6];
  CHECK(n==2);
  OK(exr_glyph_matrix(&g[0],m,&error));
  CHECK(near((float)m[0],g[0].size/1000) && near((float)m[3],-g[0].size/1000) && !m[1] && !m[2]);
  CHECK(near((float)m[4],g[0].x+g[0].offset_x) && near((float)m[5],g[0].baseline-g[0].offset_y));
  exr_layout_free(l);
}
int main(int argc,char **argv) {
  char path[4096]; exr_font *font=NULL; const char *group;
  CHECK(argc==3); group=argv[2];
  snprintf(path,sizeof(path),"%s/combine.ttf",argv[1]);
  OK(exr_font_open(path,&font,&error));
  if(!strcmp(group,"geometry")) { block_width_and_centre(font); four_digits_fit(font); matrix_and_pages(font); }
  else if(!strcmp(group,"modes")) { modes_and_rejections(font); horizontal_untouched(font); }
  else if(!strcmp(group,"wrap")) unbreakable(font);
  else CHECK(0);
  exr_font_free(font);
  printf("%u text-combine-upright %s checks passed\n",checks,group); return 0;
}
