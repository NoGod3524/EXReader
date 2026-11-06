/* Public-API geometry observer. Emits numeric measurements, no book text. */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
static int han(unsigned c){return (c>=0x3400&&c<=0x9fff)||(c>=0xf900&&c<=0xfaff)||(c>=0x20000&&c<=0x3347f);}
static int punct(unsigned c){return (c>=0x2014&&c<=0x201d)||c==0x2026||(c>=0x3001&&c<=0x303f)||(c>=0xff01&&c<=0xff65);}
static int opening(unsigned c){return c==0x2018||c==0x201c||c==0x300c||c==0x300e||c==0xff08||c==0x3008||c==0x300a||c==0x3010;}
static int cjk(unsigned c){return han(c)||punct(c);}
int main(int argc,char **argv){
 if(argc!=4)return 2;
 exr_font *font=NULL;exr_publication *pub=NULL;exr_document *doc=NULL;exr_pager *pager=NULL;exr_layout *page=NULL;
 exr_error e={0};exr_status s;size_t parts=0,pages=0,colon=0,fullstop=0;
 exr_layout_config config=exr_layout_config_defaults();
 config.page=(exr_layout_options){612,624,0,18,1.6f,14.4f};
 config.user_css="html,body{writing-mode:horizontal-tb!important}";
 if((s=exr_font_open(argv[2],&font,&e)))goto done;
 if((s=exr_publication_open(argv[1],&pub,&e)))goto done;
 exr_publication_parts(pub,&parts);
 for(size_t part=0;part<parts;part++){
  if((s=exr_publication_load(pub,part,&doc,&e)))goto done;
  size_t bytes=0,nn=0;const char *text=exr_document_text(doc,&bytes);const exr_node *nodes=exr_document_nodes(doc,&nn);
  for(size_t i=0;i+3<bytes;i++){
   if(!memcmp(text+i,"\xef\xbc\x9a",3)||!memcmp(text+i,"\xe3\x80\x82",3)){
    size_t j=i+3;while(j<bytes&&text[j]==' ')j++;
    if(j>i+3&&j+3<=bytes){colon+=!memcmp(text+i,"\xef\xbc\x9a",3)&&!memcmp(text+j,"\xe2\x80\x9c",3);fullstop+=!memcmp(text+i,"\xe3\x80\x82",3)&&!memcmp(text+j,"\xe2\x80\x9d",3);}
   }
  }
  if((s=exr_pager_create(doc,font,&config,&pager,&e)))goto done;
  for(size_t local=0;;local++){
   if((s=exr_pager_next(pager,&page,&e)))goto done;
   if(!page)break;
   pages++;
   size_t ng=0,nl=0;const exr_glyph *g=exr_layout_glyphs(page,&ng);const exr_line *lines=exr_layout_lines(page,&nl);
   for(size_t l=0;l<nl;l++){
    const exr_line *line=lines+l;size_t a=line->glyph_start,b=a+line->glyph_count;
    while(a<b&&(g[a].flags&EXR_GLYPH_HIDDEN))a++;
    while(b>a&&(g[b-1].flags&EXR_GLYPH_HIDDEN))b--;
    if(a==b)continue;
    size_t block=g[a].node;int heading=0;
    for(size_t node=block;node<nn;node=nodes[node].parent){heading|=nodes[node].kind==EXR_NODE_HEADING;if(nodes[node].kind==EXR_NODE_PARAGRAPH){block=node;break;}if(nodes[node].parent==node)break;}
    size_t end=block<nn?nodes[block].end:line->end;
    int final=line->end>=end;size_t gaps=0,chars=0,tail=b;float raw=0,maxgap=0,maxem=0;
    for(size_t i=a;i<b;i++){
     chars+=han(g[i].codepoint);raw+=g[i].advance;
     if(i+1<b&&cjk(g[i].codepoint)&&cjk(g[i+1].codepoint)&&!(punct(g[i].codepoint)&&punct(g[i+1].codepoint))&&g[i].cluster_start!=g[i+1].cluster_start){
      float delta=g[i+1].x-g[i].x-g[i].advance;gaps++;maxgap=fmaxf(maxgap,delta);maxem=fmaxf(maxem,delta/fminf(g[i].size,g[i+1].size));
     }
    }
    float actual=g[b-1].x+g[b-1].advance-g[a].x;
    while(tail>a&&punct(g[tail-1].codepoint))tail--;
    float tailadvance=0;for(size_t i=tail;i<b;i++)tailadvance+=g[i].advance;
    printf("LINE {\"part\":%zu,\"page\":%zu,\"line\":%zu,\"start\":%zu,\"end\":%zu,\"block\":%zu,\"final\":%d,\"heading\":%d,\"han\":%zu,\"raw\":%.6f,\"actual\":%.6f,\"right\":%.6f,\"gaps\":%zu,\"increment\":%.6f,\"max_increment\":%.6f,\"max_em\":%.6f,\"head_cp\":%u,\"head_advance\":%.6f,\"head_em\":%.6f,\"opening\":%d,\"tail_count\":%zu,\"tail_a\":%u,\"tail_b\":%u,\"tail_advance\":%.6f,\"tail_em\":%.6f}\n",part,local,l,line->start,line->end,block,final,heading,chars,raw,actual,g[a].clip_right-g[b-1].x-g[b-1].advance,gaps,gaps?(actual-raw)/gaps:0,maxgap,maxem,g[a].codepoint,g[a].advance,g[a].advance/g[a].size,opening(g[a].codepoint),b-tail,tail<b?g[tail].codepoint:0,g[b-1].codepoint,tailadvance,tailadvance/g[b-1].size);
   }
   if(part==15&&local==0&&strcmp(argv[3],"-")){
    exr_bitmap bm={0};if((s=exr_render_page_color(page,exr_layout_font(page),0,&bm,&e)))goto done;
    s=exr_bitmap_write_png(&bm,argv[3],&e);exr_bitmap_free(&bm);if(s)goto done;
   }
   exr_layout_free(page);page=NULL;
  }
  exr_pager_free(pager);pager=NULL;exr_document_free(doc);doc=NULL;
 }
 s=EXR_OK;
 done:
 printf("SUMMARY {\"pages\":%zu,\"colon_quote_spaces\":%zu,\"fullstop_quote_spaces\":%zu,\"status\":%d}\n",pages,colon,fullstop,(int)s);
 if(s)fprintf(stderr,"%s\n",e.message);
 exr_layout_free(page);exr_pager_free(pager);exr_document_free(doc);exr_publication_free(pub);exr_font_free(font);return s?1:0;
}
