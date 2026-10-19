/* SPDX-License-Identifier: MIT */
#include <exreader.h>
#include <stdio.h>
#include <string.h>
static int example_main(int argc,char **argv) {
  /* Original demonstration patterns, not a complete English dictionary. */
  const char patterns[]="hy1phen phen1ation";
  const char word[]="hyphenation";
  exr_hyphen_pattern_input input={sizeof(input),"en",patterns,sizeof(patterns)-1,2,2};
  exr_hyphenator *hyphenator=NULL; exr_error error={0}; unsigned char points[sizeof(word)]; size_t i;
  if(exr_hyphenator_create_patterns(&input,1,0,NULL,&hyphenator,&error)!=EXR_OK ||
     exr_hyphenator_breaks(hyphenator,"en-US",word,strlen(word),points,NULL,&error)!=EXR_OK) {
    fprintf(stderr,"%s\n",error.message); exr_hyphenator_free(hyphenator); return 1;
  }
  for(i=0;i<sizeof(word);i++) if(points[i]!=(i==2 || i==6)) { exr_hyphenator_free(hyphenator); return 1; }
  for(i=0;word[i];i++) { if(points[i]) putchar('-'); putchar(word[i]); }
  putchar('\n');
  {
    const char replacement[]=".aaaa1aaaa./aa=aaa,4,2";
    exr_hyphen_pattern_input alternative={sizeof(alternative),"xx",replacement,sizeof(replacement)-1,1,1};
    exr_hyphenator *rewrites=NULL;exr_hyphenation *result=NULL;size_t count;const exr_hyphen_break *items;
    if(exr_hyphenator_create_patterns(&alternative,1,0,NULL,&rewrites,&error)!=EXR_OK ||
       exr_hyphenator_query(rewrites,"xx","aaaaaaaa",8,NULL,&result,&error)!=EXR_OK) {
      fprintf(stderr,"%s\n",error.message);exr_hyphenator_free(rewrites);exr_hyphenator_free(hyphenator);return 1;
    }
    items=exr_hyphenation_breaks(result,&count);
    if(count!=1 || items[0].point!=4 || items[0].start!=3 || items[0].end!=5 ||
       strcmp(items[0].before,"aa") || strcmp(items[0].after,"aaa")) {
      exr_hyphenation_free(result);exr_hyphenator_free(rewrites);exr_hyphenator_free(hyphenator);return 1;
    }
    exr_hyphenation_free(result);exr_hyphenator_free(rewrites);result=NULL;rewrites=NULL;
    if(exr_hyphenator_create_patterns_ex(&alternative,1,0,EXR_HYPHEN_CASE_WORD,NULL,&rewrites,&error)!=EXR_OK ||
       exr_hyphenator_query(rewrites,"xx","AAAAAAAA",8,NULL,&result,&error)!=EXR_OK) {
      fprintf(stderr,"%s\n",error.message);exr_hyphenator_free(rewrites);exr_hyphenator_free(hyphenator);return 1;
    }
    items=exr_hyphenation_breaks(result,&count);
    if(count!=1 || strcmp(items[0].before,"AA") || strcmp(items[0].after,"AAA")) {
      exr_hyphenation_free(result);exr_hyphenator_free(rewrites);exr_hyphenator_free(hyphenator);return 1;
    }
    exr_hyphenation_free(result);exr_hyphenator_free(rewrites);
  }
  {
    const char rules[]="efg1hijk/gg=h,3,2\n.abcd1efgg.\nNEXTLEVEL\n.ab1cd.\n.hi1jk.";
    exr_hyphen_pattern_input input={sizeof(input),"xx",rules,sizeof(rules)-1,1,1};
    exr_hyphenator *compound=NULL;exr_hyphenation *result=NULL;const exr_hyphen_break *items;size_t count;
    exr_status status=exr_hyphenator_create_patterns(&input,1,0,NULL,&compound,&error);
    if(status==EXR_OK) status=exr_hyphenator_query(compound,"xx","abcdefghijk",11,NULL,&result,&error);
    items=exr_hyphenation_breaks(result,&count);
    if(status==EXR_OK && (count!=4 || items[0].point!=2 || items[1].point!=4 || items[2].point!=7 || items[3].point!=9 ||
       items[2].start!=6 || items[2].end!=8 || strcmp(items[2].before,"gg") || strcmp(items[2].after,"h"))) status=EXR_FORMAT;
    exr_hyphenation_free(result);exr_hyphenator_free(compound);
    if(status!=EXR_OK) { fprintf(stderr,"compound: %s\n",error.message);exr_hyphenator_free(hyphenator);return 1; }
  }
  if(argc==3) {
    exr_document *doc=NULL;exr_font *font=NULL;exr_layout *layout=NULL;exr_bitmap bitmap={0};exr_status status;
    exr_attribute attrs[]={{"lang","en"},{"style","hyphens:auto"}};
    exr_node_input nodes[]={{EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0},
      {EXR_NODE_CHAPTER,0,NULL,NULL,NULL,0},{EXR_NODE_PARAGRAPH,1,"p",NULL,attrs,2},
      {EXR_NODE_TEXT,2,NULL,"hyphenation hyphenation",NULL,0}};
    exr_chapter_input chapter={"Demo","demo.unit",1,1};
    exr_document_input source={"Hyphenation",nodes,4,&chapter,1,NULL,0};
    exr_layout_config config=exr_layout_config_defaults();size_t count,inserted=0;const exr_glyph *glyphs;
    config.page=(exr_layout_options){100,240,10,24,1.5f,0};
    status=exr_document_create(&source,&doc,&error);
    if(status==EXR_OK) status=exr_font_open(argv[1],&font,&error);
    if(status==EXR_OK) status=exr_layout_create_hyphenated(doc,font,&config,hyphenator,&layout,&error);
    if(status==EXR_OK) {
      glyphs=exr_layout_glyphs(layout,&count);
      for(i=0;i<count;i++) inserted+=!!(glyphs[i].flags&EXR_GLYPH_GENERATED);
      if(!inserted) status=EXR_FORMAT;
    }
    if(status==EXR_OK) status=exr_render_page_color(layout,NULL,0,&bitmap,&error);
    if(status==EXR_OK) status=exr_bitmap_write_png(&bitmap,argv[2],&error);
    if(status!=EXR_OK) fprintf(stderr,"%s\n",error.message);
    exr_bitmap_free(&bitmap);exr_layout_free(layout);exr_font_free(font);exr_document_free(doc);
    exr_hyphenator_free(hyphenator);return status==EXR_OK ? 0 : 1;
  }
  exr_hyphenator_free(hyphenator);return argc==1 ? 0 : 2;
}

#include "entry.h"
