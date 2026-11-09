/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static exr_error error;
static unsigned checks;
#define CHECK(x) do {checks++;if(!(x)){fprintf(stderr,"%d: %s (%s)\n",__LINE__,#x,error.message);exit(1);}}while(0)
#define OK(x) CHECK((x)==EXR_OK)
static exr_publication *open_book(const char *root,const char *kind) {
  char path[4096];exr_publication *p=NULL;
  snprintf(path,sizeof(path),"%s/style-footnotes/style-%s.epub",root,kind);
  OK(exr_publication_open(path,&p,&error));return p;
}
static void footnotes(const char *root) {
  const char *kinds[]={"chapter","end","none","vertical"};size_t k;
  for(k=0;k<4;k++) {
    exr_publication *p=open_book(root,kinds[k]);const exr_footnote *notes,*again;const exr_footnote_reference *refs;
    size_t n,r,i,nn,rr;OK(exr_publication_footnotes(p,&notes,&n,&refs,&r,&error));
    CHECK(n==(k==2?0:10));CHECK(r==(k==2?0:10));
    for(i=0;i<r;i++) {
      exr_document *d=NULL;size_t size;const char *text;char wanted[64],label[16];
      CHECK(refs[i].footnote<n);const exr_footnote *f=&notes[refs[i].footnote];
      snprintf(wanted,sizeof(wanted),"Footnote %zu correct content.",i+1);snprintf(label,sizeof(label),"[%zu]",i+1);
      CHECK(strstr(f->text,wanted));CHECK(!strcmp(f->label,label));
      /* Book-end notes live in their own non-linear document (part 2 after nav). */
      CHECK(k==1 ? f->target_part!=refs[i].part : f->target_part==refs[i].part);
      CHECK(refs[i].part==0 && refs[i].end-refs[i].start==strlen(label));
      OK(exr_publication_load(p,f->target_part,&d,&error));text=exr_document_text(d,&size);
      CHECK(f->target_offset<size && !strncmp(text+f->target_offset,f->text,strlen(f->text)));
      exr_document_free(d);
    }
    OK(exr_publication_footnotes(p,&again,&nn,&refs,&rr,&error));CHECK(again==notes && nn==n && rr==r);
    printf("%s notes=%zu references=%zu\n",kinds[k],n,r);exr_publication_free(p);
  }
}
static float *value(exr_reader_style *s,int i) {
  switch(i){case 0:return &s->font_size;case 1:return &s->line_height;case 2:return &s->paragraph_spacing;
    case 3:return &s->left;case 4:return &s->right;default:return &s->letter_spacing;}
}
static void styles(const char *root,exr_font *font) {
  exr_publication *p=open_book(root,"chapter");exr_document *d=NULL;
  const float steps[6][3]={{12,24,32},{1.2f,1.75f,2.2f},{0,.5f,1.5f},{0,48,120},{0,48,120},{-.02f,0,.06f}};
  int i,j;OK(exr_publication_load(p,0,&d,&error));
  for(i=0;i<6;i++)for(j=0;j<3;j++) {
    exr_reader_style s=exr_reader_style_defaults();exr_layout_config c=exr_layout_config_defaults();exr_layout *l=NULL;char css[1024];size_t n;
    *value(&s,i)=steps[i][j];OK(exr_reader_style_config(&s,800,700,1,&c,css,&error));
    OK(exr_layout_create_ex(d,font,&c,&l,&error));exr_layout_pages(l,&n);CHECK(n>0);exr_layout_free(l);
  }
  {
    exr_reader_style s=exr_reader_style_defaults();exr_layout_config a=exr_layout_config_defaults(),b=a;char ca[1024],cb[1024];
    OK(exr_reader_style_config(&s,800,700,1,&a,ca,&error));s.left=120;
    OK(exr_reader_style_config(&s,800,700,1,&b,cb,&error));CHECK(a.page.width+48==b.page.width+120);CHECK(b.page.height==a.page.height);
    s.top=120;s.bottom=0;s.right=0;OK(exr_reader_style_config(&s,800,700,1,&b,cb,&error));CHECK(b.page.width==680 && b.page.height==580);
    s.font_size=NAN;CHECK(exr_reader_style_config(&s,800,700,1,&b,cb,&error)==EXR_ARGUMENT);
    s=exr_reader_style_defaults();CHECK(exr_reader_style_config(&s,150,100,1,&b,cb,&error)==EXR_ARGUMENT);
  }
  printf("runtime style layouts=18/18; independent physical edges=4/4\n");
  exr_document_free(d);exr_publication_free(p);
}
static void anchors(const char *root,exr_font *font) {
  exr_publication *p=open_book(root,"chapter");exr_document *d=NULL;exr_content_anchor anchors[3]={{0}};
  exr_text_range ranges[3]={{{0,20},{0,25}},{{0,40},{0,45}},{{0,60},{0,65}}};int i,j;
  OK(exr_publication_load(p,0,&d,&error));
  for(i=0;i<3;i++)OK(exr_anchor_from_range(p,&ranges[i],NULL,&anchors[i],&error));
  for(j=0;j<3;j++) {
    exr_reader_style s=exr_reader_style_defaults();exr_layout_config c=exr_layout_config_defaults();exr_layout *l=NULL;char css[1024];
    s.font_size=j==1?24:18;OK(exr_reader_style_config(&s,800,700,1,&c,css,&error));OK(exr_layout_create_ex(d,font,&c,&l,&error));
    for(i=0;i<3;i++) {
      exr_text_range_match m;OK(exr_range_from_anchor(p,&anchors[i],NULL,&m,&error));CHECK(m.state==EXR_ANCHOR_FOUND);
      CHECK(m.range.start.part==0 && m.range.start.offset==ranges[i].start.offset && m.range.end.offset==ranges[i].end.offset);
    }
    exr_layout_free(l);
  }
  for(i=0;i<3;i++)exr_content_anchor_free(&anchors[i]);
  printf("#74 content anchors 18->24->18=9/9\n");exr_document_free(d);exr_publication_free(p);
}
/* Every visible glyph of every page stays inside the configured content box. */
static size_t inside(const exr_layout *l,const exr_layout_config *c) {
  size_t pages,lines,glyphs,p,i,k,seen=0;const exr_page *page=exr_layout_pages(l,&pages);
  const exr_line *line=exr_layout_lines(l,&lines);const exr_glyph *glyph=exr_layout_glyphs(l,&glyphs);
  CHECK(pages>0);
  for(p=0;p<pages;p++)for(i=page[p].line_start;i<page[p].line_start+page[p].line_count;i++)
    for(k=line[i].glyph_start;k<line[i].glyph_start+line[i].glyph_count;k++) {
      const exr_glyph *g=&glyph[k];if(g->flags&EXR_GLYPH_HIDDEN)continue;
      CHECK(g->x>=-.5f && g->x+g->advance<=c->page.width+.5f);
      CHECK(g->baseline>0 && g->baseline<=c->page.height+.5f);seen++;
    }
  CHECK(seen>0);return pages;
}
static void toc(const char *root,exr_font *font) {
  char path[4096];exr_publication *p=NULL;exr_document *d=NULL;const exr_toc_entry *entries;size_t n,i;
  struct {const char *name;exr_reader_style s;} cases[7];
  for(i=0;i<7;i++)cases[i].s=exr_reader_style_defaults();
  cases[0].name="default";cases[1].name="font12";cases[1].s.font_size=12;
  cases[2].name="font32";cases[2].s.font_size=32;
  cases[3].name="margins0";cases[3].s.top=cases[3].s.right=cases[3].s.bottom=cases[3].s.left=0;
  cases[4].name="margins120";cases[4].s.top=cases[4].s.right=cases[4].s.bottom=cases[4].s.left=120;
  cases[5].name="left120";cases[5].s.left=120;cases[5].s.right=0;
  cases[6].name="font32-margins120-line2.2-letter.06";cases[6].s=cases[4].s;cases[6].s.font_size=32;
  cases[6].s.line_height=2.2f;cases[6].s.letter_spacing=.06f;cases[6].s.paragraph_spacing=1.5f;
  snprintf(path,sizeof(path),"%s/toc-pages.epub",root);OK(exr_publication_open(path,&p,&error));
  OK(exr_publication_toc(p,&entries,&n,&error));CHECK(n==70);OK(exr_publication_load(p,1,&d,&error));
  for(i=0;i<7;i++) {
    exr_layout_config c=exr_layout_config_defaults();char css[1024];exr_layout *t=NULL,*body=NULL;
    exr_toc_page_options o;size_t pages,page,first,count,total=0;memset(&o,0,sizeof(o));o.struct_size=sizeof(o);
    OK(exr_reader_style_config(&cases[i].s,1280,800,1,&c,css,&error));
    OK(exr_toc_pages_create(p,font,&c,&o,&t,&error));CHECK(t);pages=inside(t,&c);
    for(page=0;page<pages;page++){OK(exr_toc_pages_entries(t,page,&first,&count));CHECK(first==total);total+=count;}
    CHECK(total==n);
    OK(exr_layout_create_ex(d,font,&c,&body,&error));
    printf("%s content=%.0fx%.0f toc_pages=%zu entries=%zu body_pages=%zu glyphs_inside=yes\n",cases[i].name,
      (double)c.page.width,(double)c.page.height,pages,total,inside(body,&c));
    exr_layout_free(t);exr_layout_free(body);
  }
  exr_document_free(d);exr_publication_free(p);
}
int main(int argc,char **argv) {
  exr_font *font=NULL;char path[4096];CHECK(argc==3);
  snprintf(path,sizeof(path),"%s/fonts/primary.ttf",argv[1]);OK(exr_font_open(path,&font,&error));
  if(!strcmp(argv[2],"footnotes"))footnotes(argv[1]);
  else if(!strcmp(argv[2],"styles"))styles(argv[1],font);
  else if(!strcmp(argv[2],"toc"))toc(argv[1],font);
  else anchors(argv[1],font);
  exr_font_free(font);printf("checks=%u\n",checks);return 0;
}
