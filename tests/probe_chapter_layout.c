/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
static exr_error error;
#define OK(x) do { if((x)!=EXR_OK) { fprintf(stderr,"%s\n",error.message);exit(1); } } while(0)
int main(int argc,char **argv) {
  exr_font *font=NULL;exr_publication *pub=NULL;size_t parts,global=0,previous_lines=0,previous_end=0;
  float previous_bottom=0;
  exr_layout_config c=exr_layout_config_defaults();
  if(argc<3) return 2;
  c.page=(exr_layout_options){1552,928,0,18,1.6f,14.4f};
  if(argc>4) { c.page.width=(float)atof(argv[3]);c.page.height=(float)atof(argv[4]); }
  OK(exr_font_open(argv[2],&font,&error));OK(exr_publication_open(argv[1],&pub,&error));exr_publication_parts(pub,&parts);
  { exr_shape_options options=exr_shape_defaults();exr_shaped_glyph *g=NULL;size_t n;
    options.font_size=18;OK(exr_shape(font,0,"殘紅",6,&options,&g,&n,&error));
    if(n!=2) return 3;
    printf("{\"kind\":\"font_default\",\"size_px\":18,\"advances_px\":[%.6f,%.6f]}\n",g[0].advance_x,g[1].advance_x);exr_free(g);
  }
  for(size_t part=0;part<parts;part++) {
    exr_document *doc=NULL;exr_pager *pager=NULL;size_t length;
    OK(exr_publication_load(pub,part,&doc,&error));const char *text=exr_document_text(doc,&length);
    const char *indent=strstr(text,"紫鵑雪雁素日知道");size_t indent_at=indent ? (size_t)(indent-text):SIZE_MAX;
    if(getenv("BOUNDED")) { exr_chapter_options o=exr_chapter_options_defaults();OK(exr_publication_pager_create(pub,part,font,&c,&o,&pager,&error)); }
    else OK(exr_pager_create(doc,font,&c,&pager,&error));
    for(size_t local=0;;local++) {
      exr_layout *page=NULL;size_t nb,nl;OK(exr_pager_next(pager,&page,&error));if(!page) break;
      const exr_layout_block *b=exr_layout_blocks(page,&nb);const exr_line *lines=exr_layout_lines(page,&nl);
      const exr_glyph *g=exr_layout_glyphs(page,NULL);exr_page_structure info=exr_layout_page_structure(page,0);
      for(size_t i=0;i<nb;i++) if(b[i].kind==EXR_BLOCK_TITLE) {
        float deviation=0,min=1e9f,max=0;size_t gaps=0;
        for(size_t j=b[i].line_start;j<b[i].line_start+b[i].line_count;j++) {
          const exr_line *line=lines+j;
          for(size_t k=line->glyph_start;k+1<line->glyph_start+line->glyph_count;k++) {
            float dx=g[k+1].x-g[k].x,difference=fabsf(dx-g[k].advance);
            if(difference>deviation) deviation=difference;
            if(dx<min) min=dx;
            if(dx>max) max=dx;
            gaps++;
          }
        }
        size_t bytes=b[i].end-b[i].start;if(bytes>160) bytes=160;
        if(bytes>=15 && !memcmp(text+b[i].start,"第二十七回",15))
          printf("{\"kind\":\"previous_chapter_end\",\"book_page\":%zu,\"part_page\":%zu,\"line_count\":%zu,\"source_end\":%zu,\"last_line_bottom\":%.6f,\"blank_px\":%.6f}\n",global,local,previous_lines,previous_end,previous_bottom,c.page.height-c.page.margin-previous_bottom);
        printf("{\"kind\":\"title\",\"part\":%zu,\"part_page\":%zu,\"book_page\":%zu,\"chapter_index\":%zu,\"starts_chapter\":%d,\"contains_title\":%d,\"line_start\":%zu,\"line_count\":%zu,\"source_start\":%zu,\"source_end\":%zu,\"gaps\":%zu,\"min_dx\":%.6f,\"max_dx\":%.6f,\"max_deviation_px\":%.6f,\"title\":\"%.*s\"}\n",
          part,local+1,global+1,b[i].chapter_index,info.starts_chapter,info.contains_title,b[i].line_start,b[i].line_count,b[i].start,b[i].end,gaps,min,max,deviation,(int)bytes,text+b[i].start);
      }
      for(size_t i=0;i<nl;i++) {
        const exr_line *line=lines+i;
        if(line->start<=indent_at && indent_at<line->end && i+1<nl) {
          for(size_t k=line->glyph_start;k<line->glyph_start+line->glyph_count;k++) if(g[k].start==indent_at) {
            float continued=g[lines[i+1].glyph_start].x;
            printf("{\"kind\":\"indent\",\"part\":%zu,\"part_page\":%zu,\"book_page\":%zu,\"line\":%zu,\"first_ink_x\":%.6f,\"continuation_x\":%.6f,\"indent_px\":%.6f}\n",part,local+1,global+1,i,g[k].x,continued,g[k].x-continued);
          }
        }
      }
      previous_lines=nl;previous_end=exr_layout_pages(page,NULL)->end;
      previous_bottom=nl ? lines[nl-1].y+lines[nl-1].height:0;
      global++;exr_layout_free(page);
    }
    exr_pager_free(pager);exr_document_free(doc);
  }
  printf("{\"kind\":\"summary\",\"pages\":%zu}\n",global);
  exr_publication_free(pub);exr_font_free(font);return 0;
}
