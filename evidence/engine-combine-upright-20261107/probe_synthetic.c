/* SPDX-License-Identifier: MIT */
/* Render one vertical paragraph with the real reader font; write a PPM and per-glyph metrics.
   usage: probe_synthetic FONT CSS TEXT_FILE WIDTH HEIGHT OUT.ppm */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
int main(int argc,char **argv) {
  static char text[4096]; exr_error e; exr_font *font; exr_document *doc=NULL; exr_layout *l=NULL;
  exr_attribute id={"id","body"}; FILE *fp; size_t k,n,i; const exr_glyph *g; exr_bitmap bm; FILE *out;
  if(argc!=7) return 2;
  fp=fopen(argv[3],"rb"); k=fread(text,1,sizeof(text)-1,fp); text[k]=0; fclose(fp);
  { exr_node_input nodes[]={{EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0},{EXR_NODE_CHAPTER,0,NULL,NULL,NULL,0},
      {EXR_NODE_PARAGRAPH,1,"p",NULL,&id,1},{EXR_NODE_TEXT,2,NULL,text,NULL,0}};
    exr_chapter_input ch={"c","c.xhtml",1,1}; exr_document_input in={"c",nodes,4,&ch,1,NULL,0};
    if(exr_font_open(argv[1],&font,&e) || exr_document_create(&in,&doc,&e)) return 3; }
  { exr_layout_config c=exr_layout_config_defaults(); c.page.width=(float)atof(argv[4]); c.page.height=(float)atof(argv[5]);
    c.page.margin=28; c.page.font_size=28; c.page.line_height=1.6f; c.page.paragraph_spacing=0; c.user_css=argv[2];
    if(exr_layout_create_ex(doc,font,&c,&l,&e)) { fprintf(stderr,"%s\n",e.message); return 4; } }
  g=exr_layout_glyphs(l,&n);
  for(i=0;i<n;i++) printf("%zu cp=%x x=%.2f base=%.2f adv=%.2f size=%.2f ox=%.2f oy=%.2f fl=%u\n",i,g[i].codepoint,
    g[i].x,g[i].baseline,g[i].advance,g[i].size,g[i].offset_x,g[i].offset_y,g[i].flags);
  if(exr_render_page_color(l,font,0,&bm,&e)) return 5;
  out=fopen(argv[6],"wb"); fprintf(out,"P6\n%u %u\n255\n",bm.width,bm.height);
  for(i=0;i<(size_t)bm.width*bm.height;i++) fwrite(bm.pixels+(i/bm.width)*bm.stride+(i%bm.width)*4,1,3,out);
  fclose(out); return 0;
}
