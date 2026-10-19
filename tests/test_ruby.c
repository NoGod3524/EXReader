/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <miniz.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error;
static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static int near(float a,float b) { return fabsf(a-b)<.02f; }
static exr_document *document(const char *body) {
  const char *a="<html xmlns='http://www.w3.org/1999/xhtml'><body>",*b="</body></html>";
  const char *container="<container><rootfiles><rootfile full-path='book.opf'/></rootfiles></container>";
  const char *package="<package><manifest><item id='main' href='main.xhtml' media-type='application/xhtml+xml'/></manifest><spine><itemref idref='main'/></spine></package>";
  size_t n=strlen(a)+strlen(body)+strlen(b)+1,zip_size=0; char *text=malloc(n); void *bytes=NULL;
  mz_zip_archive zip={0}; exr_document *doc=NULL;
  CHECK(text); snprintf(text,n,"%s%s%s",a,body,b);
  CHECK(mz_zip_writer_init_heap(&zip,0,0));
  CHECK(mz_zip_writer_add_mem(&zip,"META-INF/container.xml",container,strlen(container),0));
  CHECK(mz_zip_writer_add_mem(&zip,"book.opf",package,strlen(package),0));
  CHECK(mz_zip_writer_add_mem(&zip,"main.xhtml",text,strlen(text),0));
  CHECK(mz_zip_writer_finalize_heap_archive(&zip,&bytes,&zip_size)); CHECK(mz_zip_writer_end(&zip));
  OK(exr_document_open_memory(EXR_EPUB,bytes,zip_size,&doc,&error)); free(bytes); free(text); return doc;
}
static exr_layout_config config(unsigned mode,int under) {
  static char css[3][2][256]; const char *names[]={"horizontal-tb","vertical-rl","vertical-lr"};
  exr_layout_config c=exr_layout_config_defaults();
  snprintf(css[mode][under],sizeof(css[mode][under]),"body{writing-mode:%s} p{margin:0} ruby{ruby-position:%s}",names[mode],under ? "under" : "over");
  c.page.width=100;c.page.height=140;c.page.margin=10;c.page.font_size=20;c.page.line_height=1.2f;c.page.paragraph_spacing=0;c.user_css=css[mode][under];
  return c;
}
static const char *local(const char *name) { const char *p=name ? strrchr(name,'|') : NULL; return p ? p+1 : name ? name : ""; }
static int annotation(const exr_document *doc,size_t node) {
  const exr_node *nodes=exr_document_nodes(doc,NULL);
  for(;node!=SIZE_MAX;node=nodes[node].parent) if(!strcmp(local(nodes[node].name),"rt") || !strcmp(local(nodes[node].name),"rtc")) return 1;
  return 0;
}
static void geometry(exr_document *doc,exr_font *font,const exr_layout *layout) {
  size_t ng,nl,i,j,size,np; const exr_glyph *g=exr_layout_glyphs(layout,&ng);
  const exr_line *lines=exr_layout_lines(layout,&nl); const char *text=exr_document_text(doc,&size);
  exr_layout_pages(layout,&np); CHECK(ng && nl && np);
  for(i=0;i<ng;i++) {
    CHECK(!(g[i].flags&~511u) && g[i].codepoint!=0xfffc && g[i].codepoint!='(' && g[i].codepoint!=')');
    CHECK(g[i].start<g[i].end && g[i].end<=size && g[i].cluster_start<=g[i].start && g[i].cluster_end>=g[i].end);
    CHECK(g[i].codepoint=='A' ? text[g[i].start]=='A' : (unsigned char)text[g[i].start]>=128);
  }
  for(i=0;i<nl;i++) {
    const exr_line *line=&lines[i];
    CHECK(line->x>=9.98f && line->y>=9.98f && line->x+line->width<=90.02f && line->y+line->height<=130.02f);
    for(j=line->glyph_start;j<line->glyph_start+line->glyph_count;j++) {
      float x=(g[j].flags&EXR_GLYPH_VERTICAL) ? line->x+line->width/2 : g[j].x+g[j].advance/4;
      float y=(g[j].flags&EXR_GLYPH_VERTICAL) ? g[j].baseline+g[j].advance/4 : line->y+line->height/2;
      CHECK(exr_layout_hit_test(layout,line->page,x,y)==g[j].cluster_start);
    }
  }
  for(i=0;i<np;i++) { exr_bitmap bitmap={0}; size_t ink=0;
    OK(exr_render_page(layout,font,i,&bitmap,&error));
    for(j=0;j<(size_t)bitmap.stride*bitmap.height;j++) ink+=bitmap.pixels[j]<255;
    CHECK(ink); exr_bitmap_free(&bitmap);
  }
}
static void roundtrip(exr_document *doc,exr_font *font,const exr_layout *layout) {
  size_t ng,nl,np,i,j,at=0; const exr_glyph *g=exr_layout_glyphs(layout,&ng);
  const exr_line *lines=exr_layout_lines(layout,&nl); const exr_page *p=exr_layout_pages(layout,&np);
  exr_positioned_page *pages=calloc(np,sizeof(*pages)); exr_paint *paints=calloc(ng,sizeof(*paints));
  exr_positioned_input input={0}; exr_layout_config c=config(0,0); exr_layout *copy=NULL;
  CHECK(pages && paints);
  for(i=0;i<np;i++) {
    pages[i].width=100;pages[i].height=140;pages[i].content=p[i];pages[i].paint_start=at;
    for(j=p[i].line_start;j<p[i].line_start+p[i].line_count;j++) {
      size_t k;for(k=lines[j].glyph_start;k<lines[j].glyph_start+lines[j].glyph_count;k++) paints[at++]=(exr_paint){EXR_PAINT_GLYPH,0,k};
    }
    pages[i].paint_count=at-pages[i].paint_start;
  }
  CHECK(at==ng);input.struct_size=sizeof(input);input.pages=pages;input.page_count=np;input.glyphs=g;input.glyph_count=ng;
  input.lines=lines;input.line_count=nl;input.paints=paints;input.paint_count=ng;c.page.margin=0;
  OK(exr_layout_create_positioned(doc,font,&input,&c,&copy,&error));
  for(i=0;i<np;i++) { exr_bitmap a={0},b={0};
    OK(exr_render_page(layout,font,i,&a,&error));OK(exr_render_page(copy,font,i,&b,&error));
    CHECK(a.stride==b.stride && a.height==b.height && !memcmp(a.pixels,b.pixels,(size_t)a.stride*a.height));
    exr_bitmap_free(&a);exr_bitmap_free(&b);
  }
  exr_layout_free(copy);free(pages);free(paints);
}
static void simple(exr_font *font) {
  unsigned mode,under;
  for(mode=0;mode<3;mode++) for(under=0;under<2;under++) {
    exr_document *doc=document("<p>A<ruby>\xe7\x94\xb2<rp>(</rp><rt>AA</rt><rp>)</rp></ruby>A</p>");
    exr_layout_config c=config(mode,(int)under); exr_layout *layout=NULL; const exr_glyph *g; size_t n,i;
    const exr_line *lines;size_t nl;float base=-1,note=-1;
    OK(exr_layout_create_ex(doc,font,&c,&layout,&error));g=exr_layout_glyphs(layout,&n);CHECK(n==5);
    for(i=0;i<n;i++) CHECK(near(g[i].size,annotation(doc,g[i].node) ? 10 : 20));
    lines=exr_layout_lines(layout,&nl);
    for(i=0;i<nl;i++) {
      if(annotation(doc,g[lines[i].glyph_start].node)) note=mode ? lines[i].x : lines[i].y;
      else if(g[lines[i].glyph_start].codepoint==0x7532) base=mode ? lines[i].x : lines[i].y;
    }
    CHECK(base>=0 && note>=0 && (mode ? (under ? note<base : note>base) : (under ? note>base : note<base)));
    geometry(doc,font,layout);roundtrip(doc,font,layout);
    for(i=0;i<n;i++) if(annotation(doc,g[i].node)) { exr_anchor anchor={0};exr_anchor_match match={0};
      OK(exr_anchor_create(doc,g[i].start,g[i].end,&anchor,&error));OK(exr_anchor_resolve(doc,&anchor,&match,&error));
      CHECK(match.state==EXR_ANCHOR_FOUND && match.start==g[i].start && match.end==g[i].end);exr_anchor_free(&anchor);break;
    }
    exr_layout_free(layout);exr_document_free(doc);
  }
}
static void equal_page(const exr_layout *all,size_t index,const exr_layout *part) {
  const exr_page *a=exr_layout_pages(all,NULL)+index,*b=exr_layout_pages(part,NULL);size_t i,j,n;
  const exr_line *la=exr_layout_lines(all,NULL),*lb=exr_layout_lines(part,NULL);
  const exr_glyph *ga=exr_layout_glyphs(all,NULL),*gb=exr_layout_glyphs(part,NULL);
  exr_layout_pages(part,&n);CHECK(n==1 && a->start==b->start && a->end==b->end && a->line_count==b->line_count);
  for(i=0;i<b->line_count;i++) {const exr_line *x=&la[a->line_start+i],*y=&lb[b->line_start+i];
    CHECK(x->start==y->start && x->end==y->end && x->glyph_count==y->glyph_count && near(x->x,y->x) && near(x->y,y->y) && near(x->width,y->width) && near(x->height,y->height));
    for(j=0;j<x->glyph_count;j++) {const exr_glyph *u=&ga[x->glyph_start+j],*v=&gb[y->glyph_start+j];
      CHECK(u->start==v->start && u->end==v->end && u->glyph==v->glyph && u->flags==v->flags && near(u->x,v->x) && near(u->baseline,v->baseline) && near(u->advance,v->advance));
    }
  }
}
static void pagination(exr_font *font) {
  char body[12000];size_t i,at=0,np;unsigned mode;
  at+=(size_t)snprintf(body+at,sizeof(body)-at,"<p><ruby>");
  for(i=0;i<120;i++) at+=(size_t)snprintf(body+at,sizeof(body)-at,"\xe7\x94\xb2<rt>AA</rt>");
  snprintf(body+at,sizeof(body)-at,"</ruby></p>");
  for(mode=0;mode<3;mode++) {
    exr_document *doc=document(body);exr_layout_config c=config(mode,0);exr_layout *all=NULL,*one=NULL;
    exr_pager *pager=NULL;const exr_layout *cached=NULL;
    OK(exr_layout_create_ex(doc,font,&c,&all,&error));exr_layout_pages(all,&np);CHECK(np>3);
    geometry(doc,font,all);roundtrip(doc,font,all);OK(exr_pager_create(doc,font,&c,&pager,&error));
    for(i=0;i<np;i++) {OK(exr_pager_next(pager,&one,&error));CHECK(one);equal_page(all,i,one);exr_layout_free(one);one=NULL;}
    OK(exr_pager_next(pager,&one,&error));CHECK(!one);exr_pager_free(pager);pager=NULL;
    OK(exr_pager_create(doc,font,&c,&pager,&error));OK(exr_pager_set_cache(pager,1,128*1024,&error));
    OK(exr_pager_set_checkpoints(pager,8,512*1024,1,&error));
    for(i=np;i;i--) {OK(exr_pager_get(pager,i-1,&cached,&error));equal_page(all,i-1,cached);}
    CHECK(exr_pager_statistics(pager).restored_checkpoints>0);
    exr_pager_free(pager);exr_layout_free(all);exr_document_free(doc);
  }
}
static void complex(exr_font *font) {
  unsigned mode;
  for(mode=0;mode<3;mode++) {
    exr_document *doc=document("<p><ruby><rb>\xe7\x94\xb2</rb><rb>\xe7\x94\xb2</rb><rtc><rt rbspan='2'>AAAAAAAA</rt></rtc><rtc style='ruby-position:under'><rt>A</rt><rt>AA</rt></rtc></ruby></p>");
    exr_layout_config c=config(mode,0);exr_layout *layout=NULL;size_t n;
    OK(exr_layout_create_ex(doc,font,&c,&layout,&error));exr_layout_glyphs(layout,&n);CHECK(n==13);
    geometry(doc,font,layout);roundtrip(doc,font,layout);exr_layout_free(layout);exr_document_free(doc);
  }
  {exr_document *doc=document("<p><ruby><rb>\xe7\x94\xb2</rb><rtc><rt>AAAAAAAAAAAAAAAAAAAAAAAA</rt></rtc></ruby></p>");
    exr_layout_config c=config(0,0);exr_layout *layout=NULL;
    CHECK(exr_layout_create_ex(doc,font,&c,&layout,&error)==EXR_LIMIT && !layout);exr_document_free(doc);
  }
}
int main(int argc,char **argv) {
  char path[4096];exr_font *font=NULL;CHECK(argc==2);snprintf(path,sizeof(path),"%s/vertical-vrt2.ttf",argv[1]);
  OK(exr_font_open(path,&font,&error));simple(font);pagination(font);complex(font);exr_font_free(font);
  printf("%u ruby layout, source, hit, pagination and checkpoint checks passed\n",checks);return 0;
}
