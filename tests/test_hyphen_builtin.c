/* SPDX-License-Identifier: MIT */
/* Built-in hyph-en-us: rule correctness, language gating, CSS switches, logical text. */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks; static exr_font *font;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)

/* Breaks rendered as "hy-phen-ation". */
static void render(exr_hyphenator *h,const char *language,const char *word,char *out) {
  unsigned char bits[1025]={0}; size_t n=strlen(word),i,o=0;
  OK(exr_hyphenator_breaks(h,language,word,n,bits,NULL,&error));
  for(i=0;i<n;i++) { if(bits[i]) out[o++]='-'; out[o++]=word[i]; }
  out[o]=0;
}
static void rules(void) {
  exr_hyphenator *h=NULL,*loose=NULL; char out[128];
  OK(exr_hyphenator_create_builtin(0,0,0,NULL,&h,&error));
  render(h,"en-US","hyphenation",out); CHECK(!strcmp(out,"hy-phen-ation") || !strcmp(out,"hyphen-ation"));
  render(h,"en","algorithm",out);     CHECK(!strcmp(out,"al-go-rithm") || !strcmp(out,"algo-rithm"));
  render(h,"en","extraordinarily",out); CHECK(strchr(out,'-'));
  /* Default minimums are 3 graphemes on both sides: never a break within 3 of an edge. */
  { unsigned char bits[1025]={0}; const char *w="international"; size_t i,n=strlen(w);
    OK(exr_hyphenator_breaks(h,"en",w,n,bits,NULL,&error)); for(i=0;i<n;i++) if(bits[i]) CHECK(i>=3 && n-i>=3); }
  render(h,"en","cat",out); CHECK(!strcmp(out,"cat"));
  render(h,"en","table",out); CHECK(!strcmp(out,"table")); /* ta-ble leaves 2 letters on one side */
  /* No rules for other languages: no breaks at all, even for long English words. */
  render(h,"zh","hyphenation",out); CHECK(!strcmp(out,"hyphenation"));
  render(h,"de","hyphenation",out); CHECK(!strcmp(out,"hyphenation"));
  render(h,"","hyphenation",out);   CHECK(!strcmp(out,"hyphenation"));
  CHECK(exr_hyphenator_create_builtin(0,0,0,NULL,NULL,&error)==EXR_ARGUMENT);
  /* Configurable minimums. */
  OK(exr_hyphenator_create_builtin(2,2,0,NULL,&loose,&error));
  { unsigned char a[64]={0},b[64]={0}; size_t i,n=strlen("international"),ca=0,cb=0;
    OK(exr_hyphenator_breaks(h,"en","international",n,a,NULL,&error)); OK(exr_hyphenator_breaks(loose,"en","international",n,b,NULL,&error));
    for(i=0;i<=n;i++) { ca+=a[i]; cb+=b[i]; CHECK(!a[i] || b[i]); } CHECK(cb>=ca); }
  exr_hyphenator_free(h); exr_hyphenator_free(loose);
}

static exr_document *constructed(const char *text,const char *lang,const char *style) {
  exr_document *d=NULL; exr_attribute attrs[]={{"lang",lang},{"style",style}};
  exr_node_input nodes[]={ {EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0}, {EXR_NODE_CHAPTER,0,NULL,NULL,NULL,0},
    {EXR_NODE_PARAGRAPH,1,"p",NULL,attrs,2}, {EXR_NODE_TEXT,2,NULL,text,NULL,0}};
  exr_chapter_input chapter={"hyphen","hyphen.unit",1,1}; exr_document_input input={"Hyphens",nodes,4,&chapter,1,NULL,0};
  OK(exr_document_create(&input,&d,&error)); return d;
}
static exr_layout *lay(exr_document *d,exr_hyphenator *h) {
  exr_layout_config c=exr_layout_config_defaults(); exr_layout *l=NULL;
  c.page=(exr_layout_options){90,200,10,14,20.f/14,0};
  c.user_css="html,body,p{margin:0;padding:0;font-size:14px;line-height:20px}";
  OK(exr_layout_create_hyphenated(d,font,&c,h,&l,&error)); return l;
}
static size_t hyphens(const exr_layout *l) {
  size_t i,n,count=0; const exr_glyph *g=exr_layout_glyphs(l,&n);
  for(i=0;i<n;i++) count+=(g[i].flags&EXR_GLYPH_GENERATED) && g[i].codepoint==0x2010;
  return count;
}
/* Logical text copied out of the pages: every source byte once, generated glyphs skipped. */
static size_t logical(const exr_layout *l,const char *text,size_t size,char *out) {
  size_t i,n,emitted=0,o=0; const exr_glyph *g=exr_layout_glyphs(l,&n);
  for(i=0;i<n;i++) {
    size_t from;
    if(g[i].flags&EXR_GLYPH_GENERATED) { CHECK(g[i].start==g[i].end); continue; }
    if(g[i].end>size) continue;
    from=g[i].start>emitted ? g[i].start : emitted;
    for(;from<g[i].end;from++) if(text[from]!=' ') out[o++]=text[from];
    if(g[i].end>emitted) emitted=g[i].end;
  }
  out[o]=0; return o;
}
static void switches(void) {
  const char *word="extraordinarily internationalization unbelievable characteristically misunderstanding ";
  exr_hyphenator *manual=NULL,*automatic=NULL; size_t k;
  OK(exr_hyphenator_create_builtin(0,0,0,NULL,&manual,&error));
  OK(exr_hyphenator_create_builtin(0,0,1,NULL,&automatic,&error));
  { /* default CSS (manual): only an explicit hyphens:auto breaks words; none/manual never do. */
    struct { const char *lang,*style; exr_hyphenator *h; int expect; } cases[]={
      {"en","",manual,0}, {"en","hyphens:auto",manual,1}, {"en","hyphens:auto",automatic,1},
      {"en","",automatic,1}, {"en-US","",automatic,1}, {"en","hyphens:none",automatic,0}, {"en","hyphens:manual",automatic,0},
      {"zh","",automatic,0}, {"zh-CN","",automatic,0}, {"","",automatic,0}, {"de","",automatic,0}, {"zh","hyphens:auto",automatic,0}};
    for(k=0;k<sizeof(cases)/sizeof(*cases);k++) {
      exr_document *d=constructed(word,cases[k].lang,cases[k].style); exr_layout *l=lay(d,cases[k].h);
      size_t size=0,n; const char *text=exr_document_text(d,&size); char *copy=malloc(size+1),*base=malloc(size+1);
      exr_layout *plain=lay(d,NULL); CHECK(copy && base);
      if(!(cases[k].expect ? hyphens(l)>0 : hyphens(l)==0)) { size_t gn; exr_layout_glyphs(l,&gn); fprintf(stderr,"case %zu (%s/%s) hyphens=%zu glyphs=%zu lines=%zu\n",k,cases[k].lang,cases[k].style,hyphens(l),gn,exr_layout_lines(l,&gn)?gn:0); }
      CHECK(cases[k].expect ? hyphens(l)>0 : hyphens(l)==0);
      /* Logical text is identical with and without hyphenation. */
      n=logical(l,text,size,copy); CHECK(n==logical(plain,text,size,base) && !memcmp(copy,base,n));
      free(copy); free(base); exr_layout_free(l); exr_layout_free(plain); exr_document_free(d);
    }
  }
  exr_hyphenator_free(manual); exr_hyphenator_free(automatic);
}
static void joiners(void) {
  /* Hyphenation points never touch an apostrophe or hyphen-minus neighbour. */
  const char *text="well-known understand's co-operation-extraordinarily internationalization's ";
  exr_hyphenator *h=NULL; exr_document *d=constructed(text,"en","hyphens:auto"); exr_layout *l;
  size_t i,n; const exr_glyph *g; OK(exr_hyphenator_create_builtin(0,0,0,NULL,&h,&error));
  l=lay(d,h); g=exr_layout_glyphs(l,&n); CHECK(hyphens(l)>0);
  for(i=0;i<n;i++) if((g[i].flags&EXR_GLYPH_GENERATED) && g[i].codepoint==0x2010) {
    char before=g[i].start ? text[g[i].start-1] : 0, after=text[g[i].start];
    CHECK(before!='-' && before!='\'' && after!='-' && after!='\'' && after!=' ');
  }
  exr_layout_free(l); exr_document_free(d); exr_hyphenator_free(h);
}
int main(int argc,char **argv) {
  char path[4096]; CHECK(argc==2 || argc==3); snprintf(path,sizeof(path),"%s/fonts/latin-hyphen.ttf",argv[1]); OK(exr_font_open(path,&font,&error));
  if(argc==2 || !strcmp(argv[2],"rules")) rules();
  if(argc==2 || !strcmp(argv[2],"switches")) switches();
  if(argc==2 || !strcmp(argv[2],"joiners")) joiners();
  exr_font_free(font); printf("%u built-in hyphenation checks passed\n",checks); return 0;
}
