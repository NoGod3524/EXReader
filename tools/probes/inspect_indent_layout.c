/* Read-only layout metadata; no rendering or text output. */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static const char *attribute(const exr_node *node,const char *name){for(size_t i=0;i<node->attribute_count;i++)if(!strcmp(node->attributes[i].name,name))return node->attributes[i].value;return "";}
static int example_main(int argc,char **argv){
  exr_font *font=NULL;exr_publication *publication=NULL;exr_document *doc=NULL;exr_pager *pager=NULL;exr_layout *page=NULL;exr_error error={0};
  exr_layout_config c=exr_layout_config_defaults();exr_status s=EXR_ARGUMENT;unsigned char *seen=NULL;size_t count=0;int result=1;
  if(argc!=3)return 2;
  c.page=(exr_layout_options){1280,800,36,18,1.5f,10};c.user_css="html,body{font-size:18px!important}";
  s=exr_font_open(argv[2],&font,&error);if(s)goto done;
  s=exr_publication_open(argv[1],&publication,&error);if(s)goto done;
  s=exr_publication_load(publication,64,&doc,&error);if(s)goto done;
  const exr_node *nodes=exr_document_nodes(doc,&count);seen=calloc(count,1);if(!seen)goto done;
  s=exr_pager_create(doc,font,&c,&pager,&error);if(s)goto done;
  for(size_t local=1;local<=8;local++){
    s=exr_pager_next(pager,&page,&error);if(s || !page)goto done;
    size_t nl=0,ng=0;const exr_line *lines=exr_layout_lines(page,&nl);const exr_glyph *glyphs=exr_layout_glyphs(page,&ng);
    for(size_t i=0;i<nl;i++){
      size_t j=lines[i].glyph_start;while(j<lines[i].glyph_start+lines[i].glyph_count && j<ng && ((glyphs[j].flags&EXR_GLYPH_HIDDEN) || !glyphs[j].advance))j++;
      if(j>=ng || j>=lines[i].glyph_start+lines[i].glyph_count)continue;
      size_t p=glyphs[j].node;
      while(p<count){const char *name=nodes[p].name,*local=name ? strrchr(name,'|'):NULL;local=local ? local+1:name;if(nodes[p].kind==EXR_NODE_PARAGRAPH || (local && (!strcmp(local,"p") || !strcmp(local,"div"))))break;p=nodes[p].parent;}
      if(p>=count){if(local<8)continue;fputs("No paragraph ancestor on measured page\n",stderr);goto done;}
      int first=!seen[p];seen[p]=1;
      if(local==8)printf("INDENT_LINE {\"line\":%zu,\"paragraph_node\":%zu,\"paragraph_class\":\"%s\",\"first_line_of_paragraph\":%s,\"layout_x\":%.6f,\"layout_y\":%.6f,\"first_glyph_x\":%.6f,\"font_size\":%.6f,\"glyph_count\":%zu}\n",i+1,p,attribute(nodes+p,"class"),first ? "true":"false",lines[i].x,lines[i].y,glyphs[j].x,glyphs[j].size,lines[i].glyph_count);
    }
    exr_layout_free(page);page=NULL;
  }
  result=0;
done:
  if(result && error.message[0])fprintf(stderr,"Error %d: %s\n",(int)s,error.message);
  free(seen);exr_layout_free(page);exr_pager_free(pager);exr_document_free(doc);exr_publication_free(publication);exr_font_free(font);return result;
}
#include "C:/Users/Oscar/Documents/Codex/EXReader-real-books-20261105/examples/entry.h"
