/* External read-only observer: numeric glyph coordinates, no document text. */
#include "exreader.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef struct {size_t i;float column,along;} item;
static int vertical=1;
static int space(uint32_t c){return c<=32 || c==0xa0 || c==0x3000 || c==0xfeff || c==0x200b;}
static int head_bad(uint32_t c){return c==0x3002||c==0x3001||c==0xff0c||c==0xff0e||c==0xff09||c==0x300d||c==0x300f||c==0xff01||c==0xff1f||c==0xff1a||c==0xff1b;}
static int tail_bad(uint32_t c){return c==0xff08||c==0x300c||c==0x300e;}
static int punct(uint32_t c){return head_bad(c)||tail_bad(c)||c==0x2026||c==0x2025||c==0x2014||c==0x2015;}
static int cjk(uint32_t c){return c>=0x4e00 && c<=0x9fff;}
static int ruby(const exr_node *nodes,size_t count,size_t node){
  for(size_t steps=0;node<count && steps<count;steps++){
    const char *s=nodes[node].name;
    if(s){const char *p=strrchr(s,'|');if(p)s=p+1;if(!strcmp(s,"rt")||!strcmp(s,"rp")||!strcmp(s,"rtc"))return 1;}
    size_t parent=nodes[node].parent;if(parent==node)break;node=parent;
  }
  return 0;
}
static int compare(const void *aa,const void *bb){
  const item *a=aa,*b=bb;
  if(fabsf(a->column-b->column)>0.02f)return vertical ? (a->column>b->column ? -1:1):(a->column<b->column ? -1:1);
  if(fabsf(a->along-b->along)>0.001f)return a->along<b->along ? -1:1;
  return a->i<b->i ? -1:a->i>b->i;
}
static int example_main(int argc,char **argv){
  exr_font *font=NULL;exr_publication *pub=NULL;exr_document *doc=NULL;exr_pager *pager=NULL;exr_layout *page=NULL;
  exr_error e={0};exr_status s=EXR_ARGUMENT;int rc=1;
  size_t parts=0,pages=0,columns=0,heads=0,tails=0,pairs=0,glyphs=0,annotations=0,wrong_mode=0;
  if(argc!=4)return 2;
  vertical=atoi(argv[3]);
  exr_layout_config config=exr_layout_config_defaults();config.page=(exr_layout_options){720,1040,36,28,1.5f,10};
  if(!vertical)config.user_css="html,body{writing-mode:horizontal-tb!important}";
  s=exr_font_open(argv[2],&font,&e);if(s)goto done;
  s=exr_publication_open(argv[1],&pub,&e);if(s)goto done;
  exr_publication_parts(pub,&parts);
  for(size_t part=0;part<parts;part++){
    s=exr_publication_load(pub,part,&doc,&e);if(s)goto done;
    size_t nn=0;const exr_node *nodes=exr_document_nodes(doc,&nn);
    s=exr_pager_create(doc,font,&config,&pager,&e);if(s)goto done;
    for(;;){
      s=exr_pager_next(pager,&page,&e);if(s)goto done;if(!page)break;
      pages++;wrong_mode+=exr_layout_writing_mode(page)!=(vertical ? EXR_WRITING_VERTICAL_RL:EXR_WRITING_HORIZONTAL_TB);
      size_t ng=0,nl=0,n=0;const exr_glyph *g=exr_layout_glyphs(page,&ng);const exr_line *lines=exr_layout_lines(page,&nl);
      glyphs+=ng;
      item *items=calloc(ng+1,sizeof(*items));unsigned char *seen=calloc(ng+1,1);
      if(!items||!seen){free(items);free(seen);s=EXR_MEMORY;goto done;}
      for(size_t l=0;l<nl;l++)for(size_t j=lines[l].glyph_start;j<ng && j<lines[l].glyph_start+lines[l].glyph_count;j++){
        if(seen[j])continue;
        seen[j]=1;
        if(g[j].flags&EXR_GLYPH_HIDDEN || space(g[j].codepoint))continue;
        if(ruby(nodes,nn,g[j].node)){annotations++;continue;}
        items[n++]=(item){j,vertical ? lines[l].x:lines[l].y,vertical ? g[j].baseline:g[j].x};
      }
      qsort(items,n,sizeof(*items),compare);
      for(size_t begin=0;begin<n;){
        size_t end=begin+1;while(end<n && fabsf(items[end].column-items[begin].column)<0.02f)end++;
        columns++;
        const exr_glyph *first=&g[items[begin].i],*last=&g[items[end-1].i];
        if(head_bad(first->codepoint)){
          heads++;printf("EDGE {\"page\":%zu,\"part\":%zu,\"edge\":\"head\",\"codepoint\":%u,\"column\":%.6f,\"along\":%.6f,\"source_start\":%zu}\n",pages,part,first->codepoint,items[begin].column,items[begin].along,first->start);
        }
        if(tail_bad(last->codepoint)){
          tails++;printf("EDGE {\"page\":%zu,\"part\":%zu,\"edge\":\"tail\",\"codepoint\":%u,\"column\":%.6f,\"along\":%.6f,\"source_start\":%zu}\n",pages,part,last->codepoint,items[begin].column,items[end-1].along,last->start);
        }
        for(size_t j=begin;j+1<end;j++){
          const exr_glyph *a=&g[items[j].i],*b=&g[items[j+1].i];
          if(!punct(a->codepoint)||!punct(b->codepoint)||a->cluster_end!=b->cluster_start||a->font_index!=b->font_index||fabsf(a->size-b->size)>0.01f)continue;
          float reference=0;
          for(size_t k=begin;k<end;k++){const exr_glyph *v=&g[items[k].i];if(cjk(v->codepoint)&&v->font_index==a->font_index&&fabsf(v->size-a->size)<0.01f&&v->advance>0){reference=v->advance;break;}}
          if(reference<=0)continue;
          pairs++;
          printf("PAIR {\"page\":%zu,\"part\":%zu,\"a\":%u,\"b\":%u,\"source_start\":%zu,\"size\":%.6f,\"advance_a\":%.6f,\"advance_b\":%.6f,\"position_a\":%.6f,\"position_b\":%.6f,\"sum\":%.6f,\"extent\":%.6f,\"reference\":%.6f}\n",pages,part,a->codepoint,b->codepoint,a->start,a->size,a->advance,b->advance,items[j].along,items[j+1].along,a->advance+b->advance,items[j+1].along+b->advance-items[j].along,reference);
        }
        begin=end;
      }
      free(items);free(seen);exr_layout_free(page);page=NULL;
    }
    exr_pager_free(pager);pager=NULL;exr_document_free(doc);doc=NULL;
  }
  rc=0;
done:
  printf("CJK_SUMMARY {\"vertical\":%s,\"parts\":%zu,\"pages\":%zu,\"columns\":%zu,\"head_violations\":%zu,\"tail_violations\":%zu,\"punctuation_pairs\":%zu,\"glyphs\":%zu,\"excluded_ruby_glyphs\":%zu,\"wrong_mode_pages\":%zu,\"status\":%d}\n",vertical ? "true":"false",parts,pages,columns,heads,tails,pairs,glyphs,annotations,wrong_mode,(int)s);
  if(rc)fprintf(stderr,"CJK error %d: %s\n",(int)s,e.message);
  exr_layout_free(page);exr_pager_free(pager);exr_document_free(doc);exr_publication_free(pub);exr_font_free(font);return rc;
}
#include "C:/Users/Oscar/Documents/Codex/EXReader-real-books-20261105/examples/entry.h"
