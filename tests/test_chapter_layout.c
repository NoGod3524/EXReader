/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
static exr_error error;
static unsigned checks;
static exr_font *font;
#define CHECK(x) do { checks++;if(!(x)) { fprintf(stderr,"line %d: %s (%s)\n",__LINE__,#x,error.message);exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static int near(float a,float b) { return fabsf(a-b)<.01f; }
static exr_document *book(const char *text,const char *name,exr_node_kind kind,const exr_attribute *attrs,size_t count,const char *css) {
  char tag[128];
  exr_node_input nodes[]={
    {EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0},
    {EXR_NODE_CHAPTER,0,"http://www.w3.org/1999/xhtml|section",NULL,NULL,0},
    {EXR_NODE_PARAGRAPH,1,"http://www.w3.org/1999/xhtml|p",NULL,NULL,0},
    {EXR_NODE_TEXT,2,NULL,"Previous chapter ends here.",NULL,0},
    {kind,1,name,NULL,attrs,count},
    {EXR_NODE_TEXT,4,NULL,text,NULL,0},
    {EXR_NODE_ELEMENT,1,"http://www.w3.org/1999/xhtml|style",NULL,NULL,0},
    {EXR_NODE_TEXT,6,NULL,css ? css : "",NULL,0}};
  exr_chapter_input chapter={"chapter","chapter.xhtml",1,1};
  exr_document_input input={"test",nodes,8,&chapter,1,NULL,0};exr_document *doc=NULL;
  snprintf(tag,sizeof(tag),"http://www.w3.org/1999/xhtml|%s",name);nodes[4].name=tag;
  OK(exr_document_create(&input,&doc,&error));return doc;
}
static exr_layout_config config(void) {
  exr_layout_config c=exr_layout_config_defaults();
  c.page=(exr_layout_options){200,400,10,18,1.5f,0};return c;
}
static void chapter(void) {
  exr_attribute attrs[]={{"class","body chapter-title extra"}};
  exr_document *doc=book("Chapter two","p",EXR_NODE_PARAGRAPH,attrs,1,NULL);
  exr_layout_config c=config();exr_layout *l=NULL,*page=NULL;exr_pager *pager=NULL;
  size_t np,n,i;const exr_page *pages;const exr_layout_block *blocks;
  OK(exr_layout_create_ex(doc,font,&c,&l,&error));pages=exr_layout_pages(l,&np);CHECK(np==2);
  CHECK(pages[0].line_count>0 && pages[1].line_count>0);
  { const exr_line *lines=exr_layout_lines(l,NULL);
    CHECK(lines[pages[0].line_start+pages[0].line_count-1].y+27<200); }
  CHECK(exr_layout_page_structure(l,1).starts_chapter && exr_layout_page_structure(l,1).contains_title);
  blocks=exr_layout_blocks(l,&n);CHECK(n==2 && blocks[1].kind==EXR_BLOCK_TITLE && blocks[1].line_start==pages[1].line_start);
  OK(exr_pager_create(doc,font,&c,&pager,&error));
  for(i=0;i<2;i++) { OK(exr_pager_next(pager,&page,&error));CHECK(page);CHECK(exr_layout_page_structure(page,0).chapter_index==i+1);exr_layout_free(page); }
  OK(exr_pager_next(pager,&page,&error));CHECK(!page);exr_pager_free(pager);exr_layout_free(l);exr_document_free(doc);
  doc=book("甲甲甲。\n第二十七回　甲甲甲甲\n__________\n　　甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲", "p",EXR_NODE_PARAGRAPH,NULL,0,NULL);
  OK(exr_layout_create_ex(doc,font,&c,&l,&error));pages=exr_layout_pages(l,&np);CHECK(np>=2);
  blocks=exr_layout_blocks(l,&n);
  for(i=0;i<n && blocks[i].kind!=EXR_BLOCK_TITLE;i++);CHECK(i<n);
  CHECK(blocks[i].starts_chapter && blocks[i].line_start==pages[blocks[i].page].line_start);
  CHECK(i+1<n && blocks[i+1].kind==EXR_BLOCK_ORNAMENT);
  { const exr_line *lines=exr_layout_lines(l,NULL);
    const exr_glyph *g=exr_layout_glyphs(l,NULL);
    for(size_t block=i;block<=i+1;block++)
      for(size_t line=blocks[block].line_start;line<blocks[block].line_start+blocks[block].line_count;line++)
        for(size_t k=lines[line].glyph_start+1;k<lines[line].glyph_start+lines[line].glyph_count;k++)
          CHECK(near(g[k].x-g[k-1].x,g[k-1].advance));
  }
  OK(exr_pager_create(doc,font,&c,&pager,&error));
  OK(exr_pager_set_cache(pager,1,0,&error));
  { const exr_layout *cached=NULL;
    OK(exr_pager_get(pager,1,&cached,&error));CHECK(exr_layout_page_structure(cached,0).contains_title);
    OK(exr_pager_get(pager,0,&cached,&error));CHECK(!exr_layout_page_structure(cached,0).contains_title);
    OK(exr_pager_get(pager,1,&cached,&error));CHECK(exr_layout_page_structure(cached,0).chapter_index==2);
  }
  exr_pager_free(pager);
  exr_layout_free(l);exr_document_free(doc);
  doc=book("第二十七回　甲甲\r\n\r\n甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲", "p",EXR_NODE_PARAGRAPH,NULL,0,NULL);
  OK(exr_layout_create_ex(doc,font,&c,&l,&error));blocks=exr_layout_blocks(l,&n);
  CHECK(n==3 && blocks[1].kind==EXR_BLOCK_TITLE && blocks[1].line_count==1);
  CHECK(blocks[2].kind==EXR_BLOCK_BODY && !blocks[2].starts_chapter);
  exr_layout_free(l);exr_document_free(doc);
}
static void title(void) {
  const char *names[]={"h1","h2","h3","h4","h5","h6","p","div","p","p","p"};size_t j,i,k,n;
  for(j=0;j<11;j++) {
    exr_attribute attrs[]={{j==7 ? "role" : "class",j==7 ? "heading" : j==6 ? "title" : j==9 ? "chapter_title" : j==10 ? "chaptertitle" : "chapter-title"},
      {"style","text-align:justify;font-size:18px"}};
    exr_document *doc=book("甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲 甲甲甲甲甲甲甲甲",names[j],j<6 ? EXR_NODE_HEADING:EXR_NODE_PARAGRAPH,j<6 ? attrs+1 : attrs,j<6 ? 1 : 2,NULL);
    exr_layout *l=NULL;exr_layout_config c=config();const exr_layout_block *b;const exr_line *lines;const exr_glyph *g;
    OK(exr_layout_create_ex(doc,font,&c,&l,&error));b=exr_layout_blocks(l,&n);lines=exr_layout_lines(l,NULL);g=exr_layout_glyphs(l,NULL);
    CHECK(n==2 && b[1].kind==EXR_BLOCK_TITLE && b[1].line_count>=2);
    for(i=b[1].line_start;i<b[1].line_start+b[1].line_count;i++) {
      const exr_line *line=&lines[i];
      for(k=line->glyph_start+1;k<line->glyph_start+line->glyph_count;k++) CHECK(near(g[k].x-g[k-1].x,g[k-1].advance));
    }
    exr_layout_free(l);exr_document_free(doc);
  }
  { exr_attribute attrs[]={{"class","subtitle chapter-title-extra"}};
    exr_document *doc=book("Not a chapter title","p",EXR_NODE_PARAGRAPH,attrs,1,NULL);
    exr_layout *l=NULL;exr_layout_config c=config();
    OK(exr_layout_create_ex(doc,font,&c,&l,&error));exr_layout_pages(l,&n);CHECK(n==1);
    CHECK(!exr_layout_page_structure(l,0).contains_title);
    exr_layout_free(l);exr_document_free(doc);
  }
}
static void indent(void) {
  const char *css[]={"", "p {text-indent:0}","p {text-indent:1em}","section {text-indent:0}","p {text-indent:2em;font-size:20px}"};
  const float expected[]={36,0,18,0,40};size_t j,i,n;
  for(j=0;j<5;j++) {
    exr_document *doc=book("甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲", "p",EXR_NODE_PARAGRAPH,NULL,0,css[j]);
    exr_layout *l=NULL;exr_layout_config c=config();const exr_line *lines;
    OK(exr_layout_create_ex(doc,font,&c,&l,&error));lines=exr_layout_lines(l,&n);
    for(i=0;i<n && lines[i].start<27;i++);CHECK(i+1<n);CHECK(near(lines[i].x-lines[i+1].x,expected[j]));
    exr_layout_free(l);
    c.user_css="p {text-indent:0}";OK(exr_layout_create_ex(doc,font,&c,&l,&error));lines=exr_layout_lines(l,&n);
    for(i=0;i<n && lines[i].start<27;i++);CHECK(i+1<n);CHECK(near(lines[i].x,lines[i+1].x));
    exr_layout_free(l);exr_document_free(doc);
  }
  { exr_document *doc=book("　　甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲", "p",EXR_NODE_PARAGRAPH,NULL,0,NULL);
    exr_layout *l=NULL;exr_layout_config c=config();const exr_line *lines;const exr_glyph *g;
    OK(exr_layout_create_ex(doc,font,&c,&l,&error));lines=exr_layout_lines(l,&n);g=exr_layout_glyphs(l,NULL);
    for(i=0;i<n && lines[i].start<27;i++);CHECK(i+1<n);
    CHECK(near(g[lines[i].glyph_start].x-g[lines[i+1].glyph_start].x,36));
    exr_layout_free(l);exr_document_free(doc);
  }
}
int main(int argc,char **argv) {
  char path[4096];CHECK(argc==3);snprintf(path,sizeof(path),"%s/fonts/cjk-punctuation.ttf",argv[1]);
  OK(exr_font_open(path,&font,&error));
  if(!strcmp(argv[2],"chapter")) chapter();else if(!strcmp(argv[2],"title")) title();else indent();
  exr_font_free(font);printf("%u chapter layout checks passed\n",checks);return 0;
}
