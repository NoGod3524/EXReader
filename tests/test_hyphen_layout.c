/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
static exr_error error; static unsigned checks; static exr_font *font;
static const char *directory;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static int near(float a,float b) { return fabsf(a-b)<.03f; }
static exr_layout_config config(void) { exr_layout_config c=exr_layout_config_defaults(); c.page=(exr_layout_options){80,100,10,14,20.f/14,0}; c.user_css="html,body,p{margin:0;padding:0;font-size:14px;line-height:20px}"; return c; }
static exr_hyphenator *dictionary(void) {
  const char *patterns="aa1aaaa aaaa1aa f1if1if1if1i"; const char *arabic="ل1ال1ال1ا"; const char *french="é1té";
  exr_hyphen_pattern_input i[]={{sizeof(*i),"en",patterns,strlen(patterns),1,1},{sizeof(*i),"ar",arabic,strlen(arabic),1,1},{sizeof(*i),"fr",french,strlen(french),1,1}}; exr_hyphenator *h=NULL;
  OK(exr_hyphenator_create_patterns(i,3,0,NULL,&h,&error)); return h;
}
static exr_document *constructed(const char *text,const char *lang,const char *style) {
  exr_document *d=NULL; exr_attribute attrs[]={{"lang",lang},{"style",style}};
  exr_node_input nodes[]={ {EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0}, {EXR_NODE_CHAPTER,0,NULL,NULL,NULL,0},
    {EXR_NODE_PARAGRAPH,1,"p",NULL,attrs,2}, {EXR_NODE_TEXT,2,NULL,text,NULL,0}};
  exr_chapter_input chapter={"hyphen","hyphen.unit",1,1}; exr_document_input input={"Hyphens",nodes,4,&chapter,1,NULL,0};
  OK(exr_document_create(&input,&d,&error)); return d;
}
static size_t generated(const exr_layout *l) { size_t i,n,count=0; const exr_glyph *g=exr_layout_glyphs(l,&n); for(i=0;i<n;i++) count+=!!(g[i].flags&EXR_GLYPH_GENERATED); return count; }
static exr_document *book(const char *name) { char path[4096]; exr_document *d=NULL; snprintf(path,sizeof(path),"%s/hyphen-%s.epub",directory,name); OK(exr_document_open(path,&d,&error)); return d; }
static exr_layout *layout(exr_document *d,exr_font *f,exr_hyphenator *h,const exr_layout_config *c) { exr_layout *l=NULL; OK(exr_layout_create_hyphenated(d,f,c,h,&l,&error)); return l; }
static void source(exr_document *d,const exr_layout *l) {
  size_t size,n,np,i,j; const char *text=exr_document_text(d,&size); const exr_glyph *g=exr_layout_glyphs(l,&n); const exr_page *p=exr_layout_pages(l,&np); unsigned char *covered=calloc(size+1,1); CHECK(covered);
  for(i=0;i<n;i++) {
    double matrix[6]; CHECK(g[i].page<np && g[i].start>=p[g[i].page].start && g[i].end<=p[g[i].page].end && !(g[i].boundaries&~15u));
    OK(exr_glyph_matrix(g+i,matrix,&error));
    if(g[i].flags&EXR_GLYPH_GENERATED) CHECK(g[i].start==g[i].end);
    else for(j=g[i].start;j<g[i].end;j++) covered[j]=1;
  }
  for(i=0;i<size;i++) if((unsigned char)text[i]>32 && text[i]!=(char)0xc2 && text[i]!=(char)0xad) CHECK(covered[i]);
  free(covered);
}
static void positioned(exr_document *d,const exr_layout *l,const exr_layout_config *c) {
  size_t np,nl,ng,nb,i,j,at=0; const exr_page *p=exr_layout_pages(l,&np); const exr_line *lines=exr_layout_lines(l,&nl);
  const exr_glyph *g=exr_layout_glyphs(l,&ng); const exr_box *boxes=exr_layout_boxes(l,&nb);
  exr_positioned_page *pages=calloc(np,sizeof(*pages)); exr_paint *paints=calloc(ng+nb,sizeof(*paints));
  exr_positioned_input input={0}; exr_layout *copy=NULL; exr_layout_config cc=*c; CHECK(pages && paints);
  for(i=0;i<np;i++) {
    pages[i].width=c->page.width; pages[i].height=c->page.height; pages[i].content=p[i]; pages[i].paint_start=at;
    for(j=p[i].box_start;j<p[i].box_start+p[i].box_count;j++) paints[at++]=(exr_paint){EXR_PAINT_BOX,0,j};
    for(j=p[i].line_start;j<p[i].line_start+p[i].line_count;j++) { size_t k; for(k=lines[j].glyph_start;k<lines[j].glyph_start+lines[j].glyph_count;k++) paints[at++]=(exr_paint){EXR_PAINT_GLYPH,0,k}; }
    pages[i].paint_count=at-pages[i].paint_start;
  }
  input.struct_size=sizeof(input);input.pages=pages;input.page_count=np;input.lines=lines;input.line_count=nl;input.glyphs=g;input.glyph_count=ng;input.boxes=boxes;input.box_count=nb;input.paints=paints;input.paint_count=at;
  cc.page.margin=0; OK(exr_layout_create_positioned(d,exr_layout_font(l),&input,&cc,&copy,&error));
  for(i=0;i<np;i++) { exr_bitmap a={0},b={0}; OK(exr_render_page_color(l,NULL,i,&a,&error)); OK(exr_render_page_color(copy,NULL,i,&b,&error)); CHECK(a.height==b.height && a.stride==b.stride && !memcmp(a.pixels,b.pixels,(size_t)a.stride*a.height)); exr_bitmap_free(&a);exr_bitmap_free(&b); }
  exr_layout_free(copy);free(pages);free(paints);
}
static void ordinary(void) {
  exr_hyphenator *h=dictionary(); exr_layout_config c=config(); exr_layout *a=NULL,*b=NULL; exr_document *d=constructed("AAAAAA AAAAAA","en","hyphens:auto"); size_t n,i,count=0; const exr_glyph *g;
  c.page.width=55; OK(exr_layout_create_hyphenated(d,font,&c,h,&a,&error)); OK(exr_layout_create_ex(d,font,&c,&b,&error));
  CHECK(generated(a)>0 && !generated(b)); g=exr_layout_glyphs(a,&n);
  for(i=0;i<n;i++) {
    if(g[i].flags&EXR_GLYPH_GENERATED) { CHECK(g[i].start==g[i].end && g[i].cluster_start==g[i].cluster_end); CHECK(g[i].codepoint=='-' || g[i].codepoint==0x2010); }
    else if(g[i].codepoint=='A') count++;
    CHECK(!(g[i].boundaries&~15u));
  }
  CHECK(count==12); exr_layout_free(a); exr_layout_free(b); exr_document_free(d); exr_hyphenator_free(h);
}
static void fixtures(void) {
  const char *names[]={"opf","xml-lang","unknown","empty-lang","manual","none","soft","inline","table","ruby"}; size_t i,j,n;
  exr_hyphenator *h=dictionary(); exr_layout_config c=config(); c.page.width=55;
  for(i=0;i<sizeof(names)/sizeof(*names);i++) {
    exr_document *d=book(names[i]); exr_layout *l=layout(d,font,h,&c); const exr_glyph *g=exr_layout_glyphs(l,&n);
    if(i==0 || i==1 || i==7 || i==9) { if(!generated(l)) fprintf(stderr,"missing hyphen %s\n",names[i]); CHECK(generated(l)>0); }
    if(i>=2 && i<=6) CHECK(!generated(l));
    if(i==5) for(j=0;j<n;j++) if(g[j].codepoint==0xad) CHECK(g[j].flags&EXR_GLYPH_HIDDEN);
    if(i==6) { int visible=0; for(j=0;j<n;j++) visible|=g[j].codepoint==0xad && !(g[j].flags&EXR_GLYPH_HIDDEN); CHECK(visible); }
    source(d,l);positioned(d,l,&c);exr_layout_free(l);exr_document_free(d);
  }
  exr_hyphenator_free(h);
}
static void cascade(void) {
  const char *names[]={"inherit","invalid-css","invalid-lang","inline-optin","inline-none","gap"};
  exr_hyphenator *h=dictionary();exr_layout_config c=config();size_t i;c.page.width=55;
  for(i=0;i<sizeof(names)/sizeof(*names);i++) {
    exr_document *d=book(names[i]);exr_layout *l=layout(d,font,h,&c);
    CHECK(!!generated(l)==(i!=2 && i!=4));source(d,l);positioned(d,l,&c);
    exr_layout_free(l);exr_document_free(d);
  }
  exr_hyphenator_free(h);
}
static void replay(const char *name) {
  exr_document *d=book(name); exr_hyphenator *h=dictionary(); exr_layout_config c=config(); exr_layout *all;
  exr_pager *fast=NULL,*slow=NULL; const exr_layout *a,*b; size_t np,i,targets[]={20,15,2,11,0,20,4};
  c.page.width=55; all=layout(d,font,h,&c); exr_layout_pages(all,&np); CHECK(np>20 && generated(all)>0); source(d,all);
  if(!strcmp(name,"canonical")) {
    size_t count,j,bytes;const exr_glyph *glyphs=exr_layout_glyphs(all,&count);const char *text=exr_document_text(d,&bytes);
    CHECK(bytes==6399 && !memcmp(text,"ÉTÉ ",8));
    for(j=0;j<count;j++) if(glyphs[j].flags&EXR_GLYPH_GENERATED) CHECK(glyphs[j].start==glyphs[j].end && glyphs[j].start%8==3);
  }
  OK(exr_pager_create(d,font,&c,&fast,&error));OK(exr_pager_create(d,font,&c,&slow,&error));
  OK(exr_pager_set_hyphenator(fast,h,&error));OK(exr_pager_set_hyphenator(slow,h,&error));exr_hyphenator_free(h);
  OK(exr_pager_set_cache(fast,1,262144,&error));OK(exr_pager_set_checkpoints(fast,32,1024*1024,1,&error));OK(exr_pager_set_checkpoints(slow,0,0,0,&error));
  for(i=0;i<sizeof(targets)/sizeof(*targets);i++) {
    size_t j,n,m; const exr_glyph *g,*k; exr_bitmap x={0},y={0},z={0};
    OK(exr_pager_get(fast,targets[i],&a,&error));OK(exr_pager_get(slow,targets[i],&b,&error));
    g=exr_layout_glyphs(a,&n);k=exr_layout_glyphs(b,&m);CHECK(n==m);
    for(j=0;j<n;j++) { CHECK(g[j].start==k[j].start && g[j].end==k[j].end && g[j].flags==k[j].flags && near(g[j].x,k[j].x) && near(g[j].baseline,k[j].baseline)); CHECK(exr_layout_hit_test(a,0,g[j].x+.1f,g[j].baseline-2)==exr_layout_hit_test(all,targets[i],g[j].x+.1f,g[j].baseline-2)); }
    OK(exr_render_page_color(a,NULL,0,&x,&error));OK(exr_render_page_color(b,NULL,0,&y,&error));OK(exr_render_page_color(all,NULL,targets[i],&z,&error));
    CHECK(x.height==y.height && x.height==z.height && x.stride==y.stride && x.stride==z.stride && !memcmp(x.pixels,y.pixels,(size_t)x.stride*x.height) && !memcmp(x.pixels,z.pixels,(size_t)x.stride*x.height));
    exr_bitmap_free(&x);exr_bitmap_free(&y);exr_bitmap_free(&z);
  }
  CHECK(exr_pager_statistics(fast).restored_checkpoints>0);CHECK(exr_pager_statistics(fast).checkpoint_bytes<=1024*1024);
  CHECK(exr_pager_set_hyphenator(fast,NULL,&error)==EXR_ARGUMENT);exr_pager_free(fast);exr_pager_free(slow);exr_layout_free(all);exr_document_free(d);
}
static void joining(void) {
  char path[4096]; exr_font *f=NULL; exr_hyphenator *h=dictionary(); exr_layout_config c=config(); exr_document *d; exr_layout *l; const exr_glyph *g; const exr_line *lines; size_t n,i;
  snprintf(path,sizeof(path),"%s/shaping/hyphen.ttf",directory);OK(exr_font_open(path,&f,&error));
  d=book("fi-wide");l=layout(d,f,h,&c);g=exr_layout_glyphs(l,&n);CHECK(n==4 && !generated(l));for(i=0;i<n;i++) CHECK(g[i].glyph==7);exr_layout_free(l);exr_document_free(d);
  d=book("fi");l=layout(d,f,h,&c);source(d,l);CHECK(generated(l)>0);g=exr_layout_glyphs(l,&n);lines=exr_layout_lines(l,NULL);
  CHECK(lines[0].glyph_count==2 && g[0].glyph==4 && (g[1].flags&EXR_GLYPH_GENERATED));
  /* FreeType hinted widths at 14px are 4px each; GPOS subtracts 80*14/1000. */
  CHECK(near(g[0].advance,2.88f) && near(g[1].advance,4) && near(lines[0].width,6.88f));
  CHECK(g[1].start==1 && g[lines[1].glyph_start].start==1 && g[lines[1].glyph_start].glyph==5);
  positioned(d,l,&c);exr_layout_free(l);exr_document_free(d);
  d=book("arabic");l=layout(d,f,h,&c);CHECK(generated(l)>0);g=exr_layout_glyphs(l,&n);lines=exr_layout_lines(l,NULL);
  CHECK(lines[0].glyph_count==2 && (g[0].flags&EXR_GLYPH_GENERATED) && g[0].start==2 && g[1].glyph==24 && g[1].start==0);
  source(d,l);positioned(d,l,&c);exr_layout_free(l);exr_document_free(d);
  exr_hyphenator_free(h);exr_font_free(f);
}

typedef struct {
  unsigned calls,releases,apostrophes,marks,joined;
  int mode,stop;
  exr_pager *pager;
  exr_session *session;
} host;
static exr_status host_breaks(void *context,const char *lang,const char *word,size_t size,unsigned char *out,const exr_control *control,exr_error *e) {
  host *s=context; size_t i; (void)control; (void)e; CHECK(!strcmp(lang,"en")); s->calls++;
  CHECK(size<=256 && !memchr(word,'1',size));
  s->apostrophes+=!!memchr(word,'\'',size); s->marks+=size>=3 && !!memchr(word,0xcc,size); s->joined+=size>=3 && !!memchr(word,0xe2,size);
  if(s->mode==1) return EXR_IO;
  if(s->mode==2) s->stop=1;
  if(s->mode==3) {
    exr_error inner={0};
    if(s->pager) CHECK(exr_pager_set_hyphenator(s->pager,NULL,&inner)==EXR_ARGUMENT);
    if(s->session) CHECK(exr_session_set_hyphenator(s->session,NULL,&inner)==EXR_ARGUMENT);
  }
  for(i=1;i<size;i++) if(((unsigned char)word[i]&0xc0)!=0x80) out[i]=1;
  return EXR_OK;
}
static void host_release(void *context) { ((host *)context)->releases++; }
static int host_cancelled(void *context) { return ((host *)context)->stop; }
static exr_hyphenator *host_dictionary(host *s) {
  exr_hyphen_provider p={sizeof(p),host_breaks,host_release,s}; exr_hyphenator *h=NULL;
  OK(exr_hyphenator_create(&p,&h,&error)); return h;
}
static void word_boundaries(void) {
  char text[512]; host state={0}; exr_hyphenator *h=host_dictionary(&state); exr_layout_config c=config(); exr_document *d; exr_layout *l;
  const char *prefix="AAAA'AA AA1AAA A\xcc\x81" "AAAA A\xe2\x80\x8d" "AAAA "; size_t at=strlen(prefix),i,n; const exr_glyph *g;
  memcpy(text,prefix,at);memset(text+at,'A',300);strcpy(text+at+300," AAAAAA"); c.page.width=55;
  d=constructed(text,"en","hyphens:auto"); l=layout(d,font,h,&c); g=exr_layout_glyphs(l,&n);
  CHECK(state.apostrophes==1 && state.marks==1 && state.joined==1 && state.calls==4 && generated(l)>0);
  for(i=0;i<n;i++) if(g[i].flags&EXR_GLYPH_GENERATED) {
    CHECK(g[i].start!=16 && g[i].start!=17 && g[i].start!=23 && g[i].start!=24 && g[i].start!=25 && g[i].start!=26);
  }
  source(d,l);exr_layout_free(l);exr_document_free(d);exr_hyphenator_free(h);CHECK(state.releases==1);
}
static void provider_recovery(void) {
  host state={0}; exr_hyphenator *h=host_dictionary(&state); exr_document *d=book("long"); exr_layout_config c=config(); exr_pager *p=NULL;
  const exr_layout *page=NULL; exr_control control={host_cancelled,NULL,&state};
  c.page.width=55; c.control=control; OK(exr_pager_create(d,font,&c,&p,&error)); state.pager=p;
  OK(exr_pager_set_hyphenator(p,h,&error));exr_hyphenator_free(h);CHECK(!state.releases);
  state.mode=1; CHECK(exr_pager_get(p,0,&page,&error)==EXR_IO && !page && !exr_pager_cached_count(p));
  state.mode=2; CHECK(exr_pager_get(p,0,&page,&error)==EXR_CANCELLED && !page && !exr_pager_cached_count(p));
  state.mode=3; state.stop=0; OK(exr_pager_get(p,0,&page,&error));CHECK(generated(page)>0);
  OK(exr_pager_set_cache(p,1,1,&error)); CHECK(exr_pager_get(p,1,&page,&error)==EXR_LIMIT && !page);
  OK(exr_pager_set_cache(p,1,262144,&error));OK(exr_pager_get(p,0,&page,&error));CHECK(generated(page)>0);
  exr_pager_free(p);CHECK(state.releases==1);exr_document_free(d);
}
static void sessions(void) {
  char path[4096]; host state={0}; exr_hyphenator *h=host_dictionary(&state);exr_publication *pub=NULL;exr_session *session=NULL;
  const exr_document *d;const exr_layout *l;exr_layout_config c=config(); unsigned calls;size_t bytes;
  snprintf(path,sizeof(path),"%s/hyphen-long.epub",directory);OK(exr_publication_open(path,&pub,&error));c.page.width=55;
  OK(exr_session_create(pub,font,&c,1,&session,&error));exr_publication_free(pub);state.session=session;
  OK(exr_session_get(session,0,&d,&l,&error));CHECK(!generated(l) && exr_session_cached(session)==1);
  OK(exr_session_set_hyphenator(session,h,&error));exr_hyphenator_free(h);CHECK(!state.releases && !exr_session_cached(session));
  state.mode=3; OK(exr_session_get(session,0,&d,&l,&error));CHECK(generated(l)>0);calls=state.calls;bytes=exr_session_cached_bytes(session);
  OK(exr_session_get(session,0,&d,&l,&error));CHECK(state.calls==calls);
  OK(exr_session_set_budget(session,bytes-1,&error));CHECK(!exr_session_cached(session));
  CHECK(exr_session_get(session,0,&d,&l,&error)==EXR_LIMIT && !d && !l && !exr_session_cached(session));
  OK(exr_session_set_budget(session,0,&error));OK(exr_session_get(session,0,&d,&l,&error));CHECK(generated(l)>0);
  OK(exr_session_set_hyphenator(session,NULL,&error));CHECK(state.releases==1 && !exr_session_cached(session));
  OK(exr_session_get(session,0,&d,&l,&error));CHECK(!generated(l));exr_session_free(session);
}
int main(int argc,char **argv) {
  char path[4096]; CHECK(argc==2);directory=argv[1];snprintf(path,sizeof(path),"%s/fonts/primary.ttf",directory); OK(exr_font_open(path,&font,&error)); ordinary();fixtures();cascade();joining();word_boundaries();provider_recovery();sessions();replay("long");replay("rtl");replay("vertical");replay("float");replay("orthogonal");replay("canonical"); exr_font_free(font); printf("%u automatic hyphen layout checks passed\n",checks); return 0;
}
