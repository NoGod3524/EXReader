/* SPDX-License-Identifier: GPL-3.0-only */
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
