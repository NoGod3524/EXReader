/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include "../src/bidi_internal.h"
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
static const char *rematch_rules=
  ".abcd1efghijklmnopqr./d=xy,4,2 "
  ".xyfg1hijklmnopqr. .xyfghijk1lmnopqr./k=zz,8,2 .zzm1nopqr.";
static const char *boundary_rules=".aaaa1aaaa./\u0301=\u0600,4,2";
static const char *boundary_canonical=".éaaa1aaaa./\u0301=\u0600,4,2";
static const char *boundary_ri=".aaaa1a./=🇺,1,5";
static const char *boundary_emoji=".aaaa1a./=👩‍,1,5";
static const char *bidi_rules=".aaaa1aaaaaaaa./ا1中=12ا,4,2";
static const char *bidi_isolate=".aaaa1aaaaaaaa./\u2067א1\u2069=ا2中,4,2";
static const char *bidi_override=".aaaa1aaaaaaaa./\u202e12\u202c=אב,4,2";
static const char *future_neutral=".aaaa1aaaaaaaa./א1中=12א,1,5";
static const char *future_bracket=".aaaa1aaaaaaaa./א)=12א,1,5";
static const char *future_isolate=".aaaa1aaaaaaaa./\u2069א=12א,1,5";
static const char *bidi_auto=".aaaa1aaaaaaaa./=אב1,1,5";
static const char *insertion_rules=".aaaa1aaaa./=abcdefghijklmnop,5,0 .abcd1efghijklmnopaaaa./d=xy,4,2 .xyfg1hijklmnopaaaa./g=zz,4,2 .zzij1klmnopaaaa.";
static const char *insertion_mixed=".aaaa1aaaa./=中ا1中אב12中ا1中אב12,5,0";
static exr_hyphenator *dictionary(void) {
  const char *patterns="aa1aaaa aaaa1aa f1if1if1if1i"; const char *arabic="ل1ال1ال1ا"; const char *french="é1té";const char *compound="aaaa1aaaa .aa1aa. NEXTLEVEL .a1a.";const char *rewrite=".aaaa1aaaa./aa=aaa,4,2";const char *canonical_rewrite=".é1té./é=t,1,2";const char *canonical_rematch=".ébcd1efghijklmnopqr./d=xy,4,2 .xyfg1hijklmnopqr. .xyfghijk1lmnopqr./k=zz,8,2 .zzm1nopqr.";
  exr_hyphen_pattern_input i[]={{sizeof(*i),"en",patterns,strlen(patterns),1,1},{sizeof(*i),"ar",arabic,strlen(arabic),1,1},{sizeof(*i),"fr",french,strlen(french),1,1},{sizeof(*i),"xx",compound,strlen(compound),1,1},{sizeof(*i),"zz",rewrite,strlen(rewrite),1,1},{sizeof(*i),"zr",canonical_rewrite,strlen(canonical_rewrite),1,1},{sizeof(*i),"zm",rematch_rules,strlen(rematch_rules),1,1},{sizeof(*i),"zn",canonical_rematch,strlen(canonical_rematch),1,1},{sizeof(*i),"zp",boundary_rules,strlen(boundary_rules),1,1},{sizeof(*i),"zu",boundary_canonical,strlen(boundary_canonical),1,1},{sizeof(*i),"zv",boundary_ri,strlen(boundary_ri),1,1},{sizeof(*i),"zw",boundary_emoji,strlen(boundary_emoji),1,1},{sizeof(*i),"zb",bidi_rules,strlen(bidi_rules),1,1},{sizeof(*i),"zc",bidi_isolate,strlen(bidi_isolate),1,1},{sizeof(*i),"zd",bidi_override,strlen(bidi_override),1,1},{sizeof(*i),"ze",bidi_auto,strlen(bidi_auto),1,1},{sizeof(*i),"zf",future_neutral,strlen(future_neutral),1,1},{sizeof(*i),"zg",future_bracket,strlen(future_bracket),1,1},{sizeof(*i),"zh",future_isolate,strlen(future_isolate),1,1},{sizeof(*i),"zi",insertion_rules,strlen(insertion_rules),1,1},{sizeof(*i),"zj",insertion_mixed,strlen(insertion_mixed),1,1}}; exr_hyphenator *h=NULL;
  OK(exr_hyphenator_create_patterns(i,sizeof(i)/sizeof(*i),0,NULL,&h,&error)); return h;
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
static exr_layout *layout(exr_document *d,exr_font *f,exr_hyphenator *h,const exr_layout_config *c) { exr_layout *l=NULL; exr_status status=exr_layout_create_hyphenated(d,f,c,h,&l,&error);if(status!=EXR_OK) { size_t size;const char *text=exr_document_text(d,&size);fprintf(stderr,"layout failure %s size %zu prefix %.100s width %.1f: %s\n",exr_document_title(d),size,text,c->page.width,error.message); } OK(status); return l; }
static void source(exr_document *d,const exr_layout *l) {
  size_t size,n,np,i,j; const char *text=exr_document_text(d,&size); const exr_glyph *g=exr_layout_glyphs(l,&n); const exr_page *p=exr_layout_pages(l,&np); unsigned char *covered=calloc(size+1,1); CHECK(covered);
  for(i=0;i<n;i++) {
    double matrix[6]; CHECK(!(g[i].flags&~2559u));CHECK(g[i].page<np && g[i].start>=p[g[i].page].start && g[i].end<=p[g[i].page].end && !(g[i].boundaries&~15u));
    OK(exr_glyph_matrix(g+i,matrix,&error));
    for(j=g[i].start;j<g[i].end;j++) covered[j]=1;
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
static exr_hyphenator *replacement_dictionary(const char *rules) {
  exr_hyphen_pattern_input i={sizeof(i),"zz",rules,strlen(rules),1,1};exr_hyphenator *h=NULL;
  OK(exr_hyphenator_create_patterns(&i,1,0,NULL,&h,&error));return h;
}
static const char *case_german=".aaaa1aaaa./ß=ﬃ,4,2 .bbbb1bbbb./=abcdefghijklmnop,5,0 .abcd1efghijklmnopbbbb./d=ß,4,2 .ssfg1hijklmnopbbbb./g=ß,4,2 .ssij1klmnopbbbb.";
static exr_hyphenator *case_dictionary(void) {
  const char *english=".aaaa1aaaa./ß=ﬃ,1,5 .cccc1cccc./=,1,5",*turkish=".ıııı1ıııı./i=ı,4,2",*lithuanian=".aaaa1aaaa./Í=J,4,2",*greek=".αααα1αααα./Σ=,4,5",*french=".éaaa1aaaa./é=ß,1,5";
  exr_hyphen_pattern_input inputs[]={{sizeof(*inputs),"de",case_german,strlen(case_german),1,1},
    {sizeof(*inputs),"en",english,strlen(english),1,1},{sizeof(*inputs),"tr",turkish,strlen(turkish),1,1},
    {sizeof(*inputs),"lt",lithuanian,strlen(lithuanian),1,1},{sizeof(*inputs),"el",greek,strlen(greek),1,1},
    {sizeof(*inputs),"fr",french,strlen(french),1,1}};
  exr_hyphenator *h=NULL;OK(exr_hyphenator_create_patterns_ex(inputs,sizeof(inputs)/sizeof(*inputs),0,EXR_HYPHEN_CASE_WORD,NULL,&h,&error));return h;
}
static const char *stem_rules=".abcdefg1hijk./gg=h,7,2\n.abcd1efgg.\n.abcdéfg1hijk./gg=h,7,2\n.abcd1éfgg.\nNEXTLEVEL\n.ab1cd.\n.hi1jk.";
static exr_hyphenator *stem_dictionary(int word_case) {
  exr_hyphen_pattern_input input={sizeof(input),"zk",stem_rules,strlen(stem_rules),1,1};exr_hyphenator *h=NULL;
  OK(exr_hyphenator_create_patterns_ex(&input,1,0,word_case ? EXR_HYPHEN_CASE_WORD : EXR_HYPHEN_CASE_LITERAL,NULL,&h,&error));return h;
}
static void conditional_stems(void) {
  exr_hyphenator *h=stem_dictionary(0);exr_document *d=constructed("abcdefghijk","zk","hyphens:auto");exr_layout_config c=config();exr_layout *l;
  const exr_line *lines;const exr_glyph *g;size_t n,k,at=0;char visible[32]={0};
  c.page.width=55;l=layout(d,font,h,&c);lines=exr_layout_lines(l,&n);g=exr_layout_glyphs(l,NULL);
  CHECK(n>=2 && lines[0].glyph_count==5 && near(lines[0].width,35));
  CHECK(g[4].start==4 && g[4].end==4 && (g[4].flags&EXR_GLYPH_GENERATED));
  g=exr_layout_glyphs(l,&n);
  for(k=0;k<n;k++) if(g[k].codepoint!='-' && g[k].codepoint!=0x2010) { CHECK(at<sizeof(visible)-1);visible[at++]=(char)g[k].codepoint; }
  CHECK(!strcmp(visible,"abcdefgghijk"));
  source(d,l);positioned(d,l,&c);exr_layout_free(l);c.page.width=83;at=0;memset(visible,0,sizeof(visible));l=layout(d,font,h,&c);
  g=exr_layout_glyphs(l,&n);for(k=0;k<n;k++) if(g[k].codepoint!='-' && g[k].codepoint!=0x2010) { CHECK(at<sizeof(visible)-1);visible[at++]=(char)g[k].codepoint; }
  CHECK(!strcmp(visible,"abcdefgghijk"));source(d,l);positioned(d,l,&c);
  exr_layout_free(l);exr_document_free(d);at=0;memset(visible,0,sizeof(visible));
  { exr_attribute floating={"style","display:block;float:left;width:28px;height:20px"};
    exr_attribute reading[]={{"lang","zk"},{"style","hyphens:auto"}};
    exr_node_input nodes[]={{EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0},{EXR_NODE_CHAPTER,0,NULL,NULL,NULL,0},
      {EXR_NODE_ELEMENT,1,"http://www.w3.org/1999/xhtml|div",NULL,&floating,1},{EXR_NODE_TEXT,2,NULL,"X",NULL,0},
      {EXR_NODE_PARAGRAPH,1,"http://www.w3.org/1999/xhtml|p",NULL,reading,2},{EXR_NODE_TEXT,4,NULL,"abcdefghijk",NULL,0}};
    exr_chapter_input chapter={"Untaken stem boundary","stem.unit",1,1};exr_document_input input={"Stem",nodes,6,&chapter,1,NULL,0};
    OK(exr_document_create(&input,&d,&error));
  }
  l=layout(d,font,h,&c);g=exr_layout_glyphs(l,&n);
  for(k=0;k<n;k++) if(g[k].codepoint!='X' && g[k].codepoint!='-' && g[k].codepoint!=0x2010) { CHECK(at<sizeof(visible)-1);visible[at++]=(char)g[k].codepoint; }
  CHECK(!strcmp(visible,"abcdefghijk")); /* Later boundary fits and is never taken. */
  { int earlier=0,wrapped=0;size_t point=exr_document_nodes(d,NULL)[5].start+4;
    for(k=0;k<n;k++) {
      if((g[k].flags&EXR_GLYPH_GENERATED) && g[k].start==point && g[k].end==point) earlier=1;
      if(g[k].node==5 && g[k].codepoint=='a' && near(g[k].x,c.page.margin+28)) wrapped=1;
    }
    CHECK(earlier && wrapped);
  }
  source(d,l);positioned(d,l,&c);exr_layout_free(l);exr_document_free(d);exr_hyphenator_free(h);
}
static void replacements(void) {
  const char *rules[]={".aaaa1aaaa./aa=aaa,4,2", ".aaaa1aaaa./=,4,2", ".aaaa1aaaa./aa=a,5,0", ".aaaa1aaaa./=a,1,8", "l·1l/=,2,1"};
  float widths[]={62,55,69,41,41};size_t r;
  for(r=0;r<5;r++) {
    exr_hyphenator *h=replacement_dictionary(rules[r]);exr_document *d=constructed(r==4 ? "al·la" : "aaaaaaaa","zz","hyphens:auto");
    exr_layout_config c=config();exr_layout *l;size_t n,nl,j;const exr_glyph *g;const exr_line *lines;int mapped=0;
    c.page.width=widths[r];l=layout(d,font,h,&c);g=exr_layout_glyphs(l,&n);lines=exr_layout_lines(l,&nl);
    CHECK(generated(l)>0 && nl==2);source(d,l);positioned(d,l,&c);
    for(j=0;j<n;j++) if((g[j].flags&EXR_GLYPH_GENERATED) && g[j].start<g[j].end) mapped=1;
    CHECK(mapped || r==2);
    if(r==0) {
      CHECK(lines[0].glyph_count==6 && lines[1].glyph_count==6 && near(lines[0].width,42) && near(lines[1].width,42));
      CHECK(g[3].start==3 && g[3].end==4 && g[3].codepoint=='a' && g[4].start==3 && g[4].end==4);
      CHECK(g[6].start==4 && g[6].end==5 && g[8].start==4 && g[8].end==5);
      CHECK(exr_layout_hit_test(l,0,g[3].x+.1f,g[3].baseline-2)==3);
      CHECK(exr_layout_hit_test(l,0,g[4].x+g[4].advance-.1f,g[4].baseline-2)==4);
    }
    if(r==1) CHECK((g[lines[1].glyph_start].flags&EXR_GLYPH_HIDDEN) && g[lines[1].glyph_start].start==4 && g[lines[1].glyph_start].end==5);
    if(r==2) {
      const exr_glyph *original=&g[lines[1].glyph_start+1];
      CHECK(exr_layout_hit_test(l,0,original->x+original->advance-.1f,original->baseline-2)==5);
    }
    if(r==3) CHECK(lines[0].glyph_count==1 && g[0].start==0 && g[0].end==4 && near(lines[0].width,7));
    exr_layout_free(l);c.page.width=300;l=layout(d,font,h,&c);CHECK(!generated(l));exr_layout_free(l);exr_document_free(d);
    d=constructed(r==4 ? "al·la" : "aaaaaaaa","zz","hyphens:manual");c.page.width=widths[r];l=layout(d,font,h,&c);CHECK(!generated(l));exr_layout_free(l);exr_document_free(d);exr_hyphenator_free(h);
  }
}
/* Anchored rules make every later opportunity depend on changed display text.
   The second rewrite survives a normal break before it is selected. */
static void display_lines(const exr_layout *l,const char *expected) {
  size_t nl,i,j,at=0;const exr_line *lines=exr_layout_lines(l,&nl);const exr_glyph *g=exr_layout_glyphs(l,NULL);
  char text[512];
  for(i=0;i<nl;i++) {
    for(j=lines[i].glyph_start;j<lines[i].glyph_start+lines[i].glyph_count;j++) {
      uint32_t cp=g[j].codepoint;
      if(g[j].flags&EXR_GLYPH_HIDDEN) continue;
      CHECK(at+2<sizeof(text) && (cp<128 || cp==0x2010));text[at++]=cp==0x2010 ? '-' : (char)cp;
    }
    text[at++]='|';
  }
  text[at]=0;
  if(strcmp(text,expected)) fprintf(stderr,"display: %s, expected: %s\n",text,expected);
  CHECK(!strcmp(text,expected));
}
static void rematching(void) {
  const char *rules[]={rematch_rules,
    ".abcd1efghijklmnopqr./d=xyz,4,2 .xyzf1ghijklmnopqr./w=v,2,4 .vhij1klmnopqr.",
    ".abcd1efghijklmnopqr./d=xyz,4,2 .xyzf1ghijklmnopqr./w=v,2,4 .vhij1klmnopqr. .vhijklm1nopqr./XXXXXXXXXX=R,2,7",
    ".abcd1efghijklmnopqr./=xy,5,0 .xy1efghijklmnopqr. .xyef1ghijklmnopqr./f=zz,4,2 .zzh1ijklmnopqr."};
  const char *expected[]={"abcd-|xyfg-|hijk-|zzm-|nopqr|", "abcd-|xw-|vhij-|klmnop|qr|", "abcd-|xw-|vhij-|klmnop|qr|", "abcd-|xyef-|zzh-|ijklmn|opqr|"};
  size_t k;
  for(k=0;k<sizeof(rules)/sizeof(*rules);k++) {
    exr_hyphenator *h=replacement_dictionary(rules[k]);exr_document *d=constructed("abcdefghijklmnopqr","zz","hyphens:auto");
    exr_layout_config c=config();exr_layout *l; c.page.width=62;l=layout(d,font,h,&c);
    display_lines(l,expected[k]);source(d,l);positioned(d,l,&c);
    exr_layout_free(l);exr_document_free(d);exr_hyphenator_free(h);
  }
}
static void replacement_boundaries(void) {
  const char *rules[]={".aaaa1aaaa./\u0301=a,4,2", ".aaaa1aaaa./a=\u0600,4,2",
    ".aaaa1aaaa./\u034f=a,4,2", ".aaaa1aaaa./a=aaa\u2060,4,2",
    ".aaaa1bककक./a=क्,4,2", ".aaaa1a./=🇺,1,5", ".aaaa1a./=👩‍,1,5", ".aaaa1aaaa./a\ufe0f=a,4,2", ".aaaa1aaaa./a=aaa\u200b,4,2"};
  const char *words[]={"aaaaaaaa","aaaaaaaa","aaaaaaaa","aaaaaaaa","aaaabककक","aaaaa🇸🇨","aaaaa👩‍💻","aaaaaaaa","aaaaaaaa"};
  size_t k;
  for(k=0;k<sizeof(rules)/sizeof(*rules);k++) {
    exr_hyphenator *h=replacement_dictionary(rules[k]);exr_document *d=constructed(words[k],"zz","hyphens:auto");
    exr_layout_config c=config();exr_layout *l;size_t i,n;const exr_glyph *g;int seen=0;
    c.page.width=(k==5 || k==6) ? 48 : 62;l=layout(d,font,h,&c);g=exr_layout_glyphs(l,&n);CHECK(generated(l)>0);
    for(i=0;i<n;i++) {
      if(k==0 && g[i].codepoint==0x301) { CHECK(g[i].cluster_start==2 && g[i].cluster_end==4 && !g[i].boundaries);CHECK(exr_layout_hit_test(l,g[i].page,g[i].x+g[i].advance-.1f,g[i].baseline-2)==4);seen=1; }
      if(k==1 && g[i].start==5) { CHECK(g[i].cluster_start==4 && g[i].cluster_end==6 && !g[i].boundaries);seen=1; }
      if(k==2 && g[i].codepoint==0x34f) { CHECK((g[i].flags&EXR_GLYPH_HIDDEN) && near(g[i].advance,0));seen=1; }
      if(k==3 && g[i].start==5) { CHECK((g[i].boundaries&EXR_BOUNDARY_GLUE) && (g[i].boundaries&EXR_BOUNDARY_GRAPHEME));seen=1; }
      if(k==4 && g[i].start==5) { CHECK(g[i].cluster_start==4 && g[i].cluster_end==8 && !g[i].boundaries);seen=1; }
      if(k==5 && g[i].codepoint==0x1f1f8) { CHECK(g[i].cluster_start==4 && g[i].cluster_end==9 && !g[i].boundaries);seen=1; }
      if(k==5 && g[i].codepoint==0x1f1e8) CHECK(g[i].cluster_start==9 && g[i].cluster_end==13 && (g[i].boundaries&EXR_BOUNDARY_GRAPHEME));
      if(k==6 && g[i].codepoint==0x1f4bb) { CHECK(g[i].cluster_start==4 && g[i].cluster_end==16 && !g[i].boundaries);seen=1; }
      if(k==7 && g[i].codepoint==0xfe0f) { CHECK((g[i].flags&EXR_GLYPH_HIDDEN) && near(g[i].advance,0) && g[i].cluster_start==3 && g[i].cluster_end==4);seen=1; }
      if(k==8 && g[i].start==5) { CHECK((g[i].boundaries&EXR_BOUNDARY_LINE) && (g[i].boundaries&EXR_BOUNDARY_GRAPHEME));seen=1; }
      if((g[i].flags&EXR_GLYPH_GENERATED) && (g[i].codepoint==0x200d || g[i].codepoint==0x2060)) CHECK((g[i].flags&EXR_GLYPH_HIDDEN) && near(g[i].advance,0));
    }
    CHECK(seen);source(d,l);positioned(d,l,&c);exr_layout_free(l);exr_document_free(d);exr_hyphenator_free(h);
  }
}
static int bidi_format(uint32_t cp) { return (cp>=0x202a && cp<=0x202e) || (cp>=0x2066 && cp<=0x2069); }
static void bidi_case(size_t case_index,const char *before,const char *after,const char *prefix,int erase_first,exr_direction direction) {
  size_t shift=strlen(prefix),prefix_count=0,left=erase_first ? 0 : 3;
  char rules[256],original[1024],display[2048];exr_hyphenator *h;exr_document *d;exr_layout_config c=config();exr_layout *l;
  exr_bidi *reference=NULL,*counted=NULL;const exr_bidi_scalar *scalars;const exr_glyph *g;const exr_line *lines;
  size_t i,j,n,nl,ns,first=0,*starts,*ends,nb=0,na=0;const char *hyphen="-";
  snprintf(rules,sizeof(rules),".aaaa1aaaaaaaa./%s=%s,%u,%u",before,after,erase_first ? 1 : 4,erase_first ? 5 : 2);
  snprintf(original,sizeof(original),"%saaaaaaaaaaaa",prefix);h=replacement_dictionary(rules);
  d=constructed(original,"zz",direction==EXR_DIRECTION_RTL ? "hyphens:auto;direction:rtl" : "hyphens:auto");c.page.width=76;l=layout(d,font,h,&c);
  g=exr_layout_glyphs(l,&n);lines=exr_layout_lines(l,&nl);CHECK(generated(l)>0);
  for(i=0;i<n;i++) if((g[i].flags&EXR_GLYPH_GENERATED) && g[i].codepoint==0x2010) hyphen="‐";
  OK(exr_bidi_analyze(before,strlen(before),EXR_DIRECTION_LTR,&counted,&error));exr_bidi_scalars(counted,&nb);exr_bidi_free(counted);
  OK(exr_bidi_analyze(after,strlen(after),EXR_DIRECTION_LTR,&counted,&error));exr_bidi_scalars(counted,&na);exr_bidi_free(counted);
  OK(exr_bidi_analyze(prefix,strlen(prefix),EXR_DIRECTION_LTR,&counted,&error));exr_bidi_scalars(counted,&prefix_count);exr_bidi_free(counted);
  snprintf(display,sizeof(display),"%s%.*s%s%s%saaaaaaa",prefix,(int)left,"aaa",before,hyphen,after);
  OK(exr_bidi_analyze(display,strlen(display),direction,&reference,&error));scalars=exr_bidi_scalars(reference,&ns);
  CHECK(n==ns);starts=calloc(ns,sizeof(*starts));ends=calloc(ns,sizeof(*ends));CHECK(starts && ends);
  for(i=0;i<ns;i++) {
    if(i<prefix_count) { starts[i]=scalars[i].start;ends[i]=scalars[i].end; }
    else if(i<prefix_count+left) { starts[i]=shift+i-prefix_count;ends[i]=starts[i]+1; }
    else if(i<prefix_count+left+nb) { starts[i]=shift+(erase_first ? 0 : 3);ends[i]=shift+4; }
    else if(i==prefix_count+left+nb) { starts[i]=shift+(!nb ? (erase_first ? 0 : 3) : 4);ends[i]=shift+4; }
    else if(i<prefix_count+left+nb+1+na) { starts[i]=shift+4;ends[i]=shift+5; }
    else { starts[i]=shift+5+i-(prefix_count+left+nb+1+na);ends[i]=starts[i]+1; }
  }
  for(i=0;i<nl;i++) {
    size_t last=first,*order=NULL,count=0,at=lines[i].glyph_start,limit=at+lines[i].glyph_count;
    last=first+lines[i].glyph_count;CHECK(last<=ns);
    CHECK(last>first);OK(exr_bidi_reorder(reference,first,last-first,&order,&count,&error));
    for(j=0;j<count;j++) {
      size_t k=order[j],last_content=last;unsigned expected_level=scalars[k].level;
      while(last_content>first && (scalars[last_content-1].codepoint==32 || bidi_format(scalars[last_content-1].codepoint))) last_content--;
      if(k>=last_content) expected_level=exr_bidi_base_level(reference,k);
      if(bidi_format(scalars[k].codepoint) || scalars[k].codepoint==0x2029) continue;
      while(at<limit && (g[at].flags&EXR_GLYPH_HIDDEN)) at++;
      CHECK(at<limit);
      if(g[at].codepoint!=scalars[k].codepoint || g[at].bidi_level!=expected_level)
        fprintf(stderr,"bidi case %zu line %zu: actual U+%x level %u, expected U+%x level %u\n",case_index,i,g[at].codepoint,g[at].bidi_level,scalars[k].codepoint,expected_level);
      CHECK(g[at].codepoint==scalars[k].codepoint && g[at].bidi_level==expected_level);
      CHECK(g[at].start==starts[k] && g[at].end==ends[k]);at++;
    }
    while(at<limit && (g[at].flags&EXR_GLYPH_HIDDEN)) at++;
    CHECK(at==limit);exr_free(order);first=last;
    for(at=lines[i].glyph_start;at<limit;) {
      size_t end=at+1,k;float lo=g[at].x,hi=lo+g[at].advance;int visible=!(g[at].flags&EXR_GLYPH_HIDDEN);
      while(end<limit && g[end].cluster_start==g[at].cluster_start && g[end].bidi_level==g[at].bidi_level) end++;
      for(k=at+1;k<end;k++) { lo=fminf(lo,g[k].x);hi=fmaxf(hi,g[k].x+g[k].advance);visible|=!(g[k].flags&EXR_GLYPH_HIDDEN); }
      if(visible && hi-lo>.2f) {
        CHECK(exr_layout_hit_test(l,g[at].page,lo+.1f,g[at].baseline-2)==((g[at].bidi_level&1) ? g[at].cluster_end : g[at].cluster_start));
        CHECK(exr_layout_hit_test(l,g[at].page,hi-.1f,g[at].baseline-2)==((g[at].bidi_level&1) ? g[at].cluster_start : g[at].cluster_end));
      }
      at=end;
    }
  }
  CHECK(first==ns);free(starts);free(ends);exr_bidi_free(reference);
  source(d,l);positioned(d,l,&c);exr_layout_free(l);exr_document_free(d);exr_hyphenator_free(h);
}
static void replacement_bidi(void) {
  const char *before[]={"ا1中","(א1)","\u2067א1\u2069","\u202e12\u202c","","中ا1","ا1中","ا1)","a中A"};
  const char *after[]={"12ا","中א","ا2中","אב","אב1","א2","12ا","中אב","A中a"};size_t q,j;
  const char *alphabet[]={"A","中","א","ا","1","2","١","٢","+","-",".","!"};
  const char *prefixes[]={"","אב ","ا1 ","1 אב ","אב 12 ","abc "};uint32_t seed=180405;
  for(q=0;q<sizeof(before)/sizeof(*before);q++) bidi_case(q,before[q],after[q],q==6 || q==8 ? "אב " : q==7 ? "(" : "",q==4 || q==7,q==5 ? EXR_DIRECTION_RTL : EXR_DIRECTION_AUTO);
  bidi_case(598,"א1中","12א","אב 1111111111111111\u2029a אב +++++ ",1,EXR_DIRECTION_AUTO);
  bidi_case(269,"א1中","12א","a אב +++++++++++++ ",1,EXR_DIRECTION_AUTO);
  bidi_case(270,"א)","12א","a אב (111111111111 ",1,EXR_DIRECTION_AUTO);
  bidi_case(271,"א]","12א","a אב [111111111111 ",1,EXR_DIRECTION_AUTO);
  bidi_case(272,"L1中","12L","אב a +++++++++++++ ",1,EXR_DIRECTION_AUTO);
  bidi_case(273,"\u2069א","12א","a אב \u2067abc 11111111 ",1,EXR_DIRECTION_AUTO);
  bidi_case(274,"\u202cא","12א","a אב \u202e1111111111 ",1,EXR_DIRECTION_AUTO);
  { size_t k;const char *tails[]={"א1中","L1中","א)","\u2069א","\u202cא"};
    for(k=0;k<64;k++) {
      char prefix[96]="a אב ";size_t at=strlen(prefix),n=6+k%19;
      memset(prefix+at,k%2 ? '+' : '1',n);prefix[at+n]=' ';prefix[at+n+1]=0;
      bidi_case(275+k,tails[k%5],"12א",prefix,1,k%3 ? EXR_DIRECTION_AUTO : EXR_DIRECTION_RTL);
    }
  }
  bidi_case(265,"ا1中","12ا","1111111111111111 ",1,EXR_DIRECTION_AUTO);
  bidi_case(266,"ا1中","12ا","\u2067אב\u2069 11111111 ",1,EXR_DIRECTION_AUTO);
  bidi_case(267,"ا1中","12ا","\u2067abc\u2069 11111111 ",1,EXR_DIRECTION_AUTO);
  bidi_case(268,"ا1中","12ا","1111\u202911111111 ",1,EXR_DIRECTION_AUTO);
  {
    const char *punct[]={"+",",",".","$","!","?","1","١","٢"," "};size_t k;
    for(k=0;k<256;k++) {
      char prefix[96];size_t at,j,count=1+k%24;
      strcpy(prefix,k%2 ? "a אב " : "אב a ");at=strlen(prefix);
      for(j=0;j<count;j++) {
        unsigned pick;seed=seed*1664525u+1013904223u;pick=(seed>>16)%10;
        if(pick==9 && prefix[at-1]==' ') pick=0;
        strcpy(prefix+at,punct[pick]);at+=strlen(punct[pick]);
      }
      if(prefix[at-1]!=' ') prefix[at++]=' ';prefix[at]=0;
      bidi_case(339+k,k%3 ? "א1中" : "L1中","12א",prefix,1,k%7 ? EXR_DIRECTION_AUTO : EXR_DIRECTION_RTL);
    }
    { char prefix[400];size_t at;
      strcpy(prefix,"a אב ");at=strlen(prefix);memset(prefix+at,'+',300);strcpy(prefix+at+300," ");
      bidi_case(595,"א1中","12א",prefix,1,EXR_DIRECTION_AUTO);
      strcpy(prefix,"אב a ");at=strlen(prefix);memset(prefix+at,'+',300);strcpy(prefix+at+300," ");
      bidi_case(596,"א1中","12א",prefix,1,EXR_DIRECTION_AUTO);
      strcpy(prefix,"a ا ");at=strlen(prefix);memset(prefix+at,'1',300);strcpy(prefix+at+300,",,$$$+ ");
      bidi_case(597,"א1中","12א",prefix,1,EXR_DIRECTION_AUTO);
    }
  }
  for(q=0;q<256;q++) {
    char a[32]={0},b[32]={0};
    for(j=0;j<3;j++) { seed=seed*1664525u+1013904223u;strcat(a,alphabet[(seed>>16)%12]);seed=seed*1664525u+1013904223u;strcat(b,alphabet[(seed>>16)%12]); }
    bidi_case(q+9,a,b,prefixes[q%6],q%11==0,q%3==0 ? EXR_DIRECTION_RTL : EXR_DIRECTION_AUTO);
  }
}
static void bidi_mark_tail(void) {
  exr_hyphenator *h=replacement_dictionary(".aaaa1aaaaaaaa./L1中=12L,1,5");size_t width;
  for(width=42;width<=100;width+=2) {
    exr_document *d=constructed("אב a \u0301aaaaaaaaaaaa","zz","hyphens:auto");exr_layout_config c=config();exr_layout *l;
    size_t i,n,seen=0;const exr_glyph *g;c.page.width=(float)width;l=layout(d,font,h,&c);g=exr_layout_glyphs(l,&n);
    for(i=0;i<n;i++) if(g[i].codepoint==0x301) { CHECK(g[i].start==7 && g[i].bidi_level==2);seen++; }
    CHECK(seen==1);source(d,l);exr_layout_free(l);exr_document_free(d);
  }
  exr_hyphenator_free(h);
}
static void long_insertion(void) {
  char rules[200]=".aaaa1aaaa./=";size_t n=strlen(rules),i,np;
  exr_hyphenator *h;exr_document *d;exr_layout_config c=config();exr_layout *l;
  memset(rules+n,'a',128);strcpy(rules+n+128,",5,0");h=replacement_dictionary(rules);
  d=constructed("aaaaaaaa","zz","hyphens:auto");c.page.width=55;l=layout(d,font,h,&c);
  CHECK(generated(l)==129);exr_layout_pages(l,&np);CHECK(np>1);source(d,l);positioned(d,l,&c);
  { size_t count;const exr_glyph *g=exr_layout_glyphs(l,&count);int original=0;
    for(i=0;i<count;i++) if(g[i].codepoint=='a' && g[i].start==4 && g[i].end==4) CHECK(g[i].cluster_end==5);
    for(i=0;i<count;i++) original|=g[i].start==7 && g[i].end==8;
    CHECK(original);
  }
  exr_layout_free(l);exr_document_free(d);exr_hyphenator_free(h);
}
static void generated_hyphenation(void) {
  const char *rules[]={
    ".aaaa1aaaa./=abcdefghijklmnop,5,0 .abcd1efghijklmnopaaaa. .abcdefgh1ijklmnopaaaa.",
    ".aaaa1aaaa./=abcdefghijklmnop,5,0 .abcd1efghijklmnopaaaa./d=xy,4,2 .xyfg1hijklmnopaaaa./g=zz,4,2 .zzij1klmnopaaaa."};
  const char *expected[]={"aaaa-|abcd-|efgh-|ijklm|nopaa|aa|", "aaaa-|abcd-|xyfg-|zzij-|klmno|paaaa|"};size_t k;
  for(k=0;k<sizeof(rules)/sizeof(*rules);k++) {
    exr_hyphenator *h=replacement_dictionary(rules[k]);exr_document *d=constructed("aaaaaaaa","zz","hyphens:auto");
    exr_layout_config c=config();exr_layout *l;size_t n,i,extra=0;c.page.width=55;l=layout(d,font,h,&c);
    { const exr_glyph *g=exr_layout_glyphs(l,&n);
      for(i=0;i<n;i++) if((g[i].flags&EXR_GLYPH_GENERATED) && (g[i].codepoint=='-' || g[i].codepoint==0x2010)) extra++;
    }
    CHECK(extra>=3);display_lines(l,expected[k]);source(d,l);positioned(d,l,&c);exr_layout_free(l);exr_document_free(d);exr_hyphenator_free(h);
  }
}
static exr_status insertion_provider(void *context,const char *language,const char *word,size_t size,
  exr_hyphen_emit_fn emit,void *sink,const exr_control *control,exr_error *e) {
  const char *text=context;exr_hyphen_break item={4,4,4,NULL,text,0,strlen(text)};
  (void)language;(void)control;
  return size==8 && !memcmp(word,"aaaaaaaa",8) ? emit(sink,&item,e) : EXR_OK;
}
static void generated_boundaries(void) {
  const char *payloads[]={"ab cd ef gh ij kl mn op qr st uv wx yz", "中文中文中文中文中文中文中文中文中文中文",
    "áááááááááááááááá", "🇺🇸🇨🇳🇺🇸🇨🇳🇺🇸🇨🇳🇺🇸🇨🇳",
    "👩‍💻👩‍💻👩‍💻👩‍💻👩‍💻👩‍💻👩‍💻👩‍💻", "ab\u00a0cd ef\u2060gh ij\u00a0kl mn\u2060op qr"};
  size_t k,w;
  for(k=0;k<sizeof(payloads)/sizeof(*payloads);k++) for(w=55;w<=69;w+=7) {
    exr_hyphen_discretionary_provider provider={sizeof(provider),insertion_provider,NULL,(void *)payloads[k]};
    exr_hyphenator *h=NULL;exr_document *d=constructed("aaaaaaaa","zz","hyphens:auto");exr_layout_config c=config();
    exr_layout *l;size_t n,nl,i,j,at=0;const exr_glyph *g;const exr_line *lines;char display[512];unsigned char *boundaries=NULL;exr_bidi *reference=NULL;const exr_bidi_scalar *scalars;size_t ns;
    OK(exr_hyphenator_create_discretionary(&provider,&h,&error));c.page.width=(float)w;l=layout(d,font,h,&c);
    g=exr_layout_glyphs(l,&n);lines=exr_layout_lines(l,&nl);CHECK(generated(l)>0 && nl>2);
    snprintf(display,sizeof(display),"aaaa%s%saaaa",g[lines[0].glyph_count-1].codepoint==0x2010 ? "‐" : "-",payloads[k]);
    OK(exr_text_analyze(display,strlen(display),&boundaries,&error));
    OK(exr_bidi_analyze(display,strlen(display),EXR_DIRECTION_LTR,&reference,&error));scalars=exr_bidi_scalars(reference,&ns);CHECK(n==ns);
    for(i=0;i<nl;i++) {
      size_t last=at+lines[i].glyph_count,next=at;unsigned char matched[256]={0};CHECK(last<=ns && ns<=sizeof(matched));
      if(i>1) CHECK((boundaries[scalars[at].start]&EXR_BOUNDARY_GRAPHEME) && !(boundaries[scalars[at].start]&EXR_BOUNDARY_GLUE));
      for(j=lines[i].glyph_start;j<lines[i].glyph_start+lines[i].glyph_count;j++) {
        size_t found=at;
        while(found<last && (matched[found] || scalars[found].codepoint!=g[j].codepoint)) found++;
        CHECK(found<last);matched[found]=1;
        if(!(g[j].flags&EXR_GLYPH_HIDDEN)) {
          while(next<last && (scalars[next].codepoint==0x200d || scalars[next].codepoint==0x2060)) next++;
          CHECK(next<last && g[j].codepoint==scalars[next++].codepoint);
        }
        if(g[j].flags&EXR_GLYPH_GENERATED) CHECK(g[j].cluster_start<=4 && g[j].cluster_end>=4);
      }
      at=last;
    }
    CHECK(at==ns);source(d,l);positioned(d,l,&c);
    exr_bidi_free(reference);exr_free(boundaries);exr_layout_free(l);exr_document_free(d);exr_hyphenator_free(h);
  }
}
static void generated_shaping(void) {
  const char *payloads[]={"fifififififififififififififififi", "لالالالالالالالالالالالالالالالا"};size_t k;
  exr_font *f=NULL;char path[4096];snprintf(path,sizeof(path),"%s/shaping/hyphen.ttf",directory);OK(exr_font_open(path,&f,&error));
  for(k=0;k<2;k++) {
    exr_hyphen_discretionary_provider provider={sizeof(provider),insertion_provider,NULL,(void *)payloads[k]};
    exr_hyphenator *h=NULL;exr_document *d=constructed("aaaaaaaa","zz",k ? "hyphens:auto;direction:rtl" : "hyphens:auto");
    exr_layout_config c=config();exr_layout *l;const exr_glyph *g;const exr_line *lines;size_t n,nl,i,shaped=0;
    OK(exr_hyphenator_create_discretionary(&provider,&h,&error));c.page.width=55;l=layout(d,f,h,&c);
    g=exr_layout_glyphs(l,&n);lines=exr_layout_lines(l,&nl);CHECK(nl>2 && generated(l)>10);
    for(i=0;i<n;i++) if((g[i].flags&EXR_GLYPH_GENERATED) && g[i].codepoint!='-' && g[i].codepoint!=0x2010) {
      CHECK((g[i].flags&EXR_GLYPH_SHAPED) && !(g[i].flags&EXR_GLYPH_MISSING));
      CHECK(g[i].cluster_start==4 && g[i].cluster_end==5);shaped++;
    }
    CHECK(shaped>8);for(i=0;i<nl;i++) CHECK(lines[i].width<=35.01f);
    source(d,l);positioned(d,l,&c);exr_layout_free(l);exr_document_free(d);exr_hyphenator_free(h);
  }
  exr_font_free(f);
}
static exr_status insertion_recovery_provider(void *context,const char *language,const char *word,size_t size,
  exr_hyphen_emit_fn emit,void *sink,const exr_control *control,exr_error *e) {
  if(size==20 && !memcmp(word,"abcdefghijklmnopaaaa",20)) {
    exr_hyphen_break item={4,3,5,"d","xy",1,2};int mode=*(int *)context;
    if(mode==1) return EXR_IO;
    if(mode==2) return EXR_CANCELLED;
    return emit(sink,&item,e);
  }
  return insertion_provider("abcdefghijklmnop",language,word,size,emit,sink,control,e);
}
static void generated_recovery(void) {
  int mode=0;exr_hyphen_discretionary_provider provider={sizeof(provider),insertion_recovery_provider,NULL,&mode};
  exr_hyphenator *h=NULL;exr_document *d=book("insertion-long");exr_layout_config c=config();exr_pager *p=NULL;
  const exr_layout *page=NULL;exr_bitmap first={0},again={0};
  OK(exr_hyphenator_create_discretionary(&provider,&h,&error));OK(exr_pager_create(d,font,&c,&p,&error));OK(exr_pager_set_hyphenator(p,h,&error));exr_hyphenator_free(h);
  OK(exr_pager_set_cache(p,1,262144,&error));OK(exr_pager_set_checkpoints(p,16,262144,1,&error));
  OK(exr_pager_get(p,0,&page,&error));OK(exr_render_page_color(page,NULL,0,&first,&error));
  mode=1;CHECK(exr_pager_get(p,4,&page,&error)==EXR_IO && !page && exr_pager_cached_count(p)==1);
  mode=2;CHECK(exr_pager_get(p,4,&page,&error)==EXR_CANCELLED && !page && exr_pager_cached_count(p)==1);
  OK(exr_pager_get(p,0,&page,&error));OK(exr_render_page_color(page,NULL,0,&again,&error));
  CHECK(first.stride==again.stride && first.height==again.height && !memcmp(first.pixels,again.pixels,(size_t)first.stride*first.height));
  mode=0;OK(exr_pager_get(p,4,&page,&error));CHECK(generated(page)>0);
  exr_bitmap_free(&first);exr_bitmap_free(&again);exr_pager_free(p);exr_document_free(d);
}
static void insertion_large_context(void) {
  const char *word="abcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyz";
  const size_t bytes=1024*1024;char *text=malloc(bytes+1),insert[129],rules[400];size_t i,k;
  CHECK(text);for(i=0;i<bytes;i++) text[i]=i%79==78 ? ' ' : word[i%79];text[bytes-1]='\n';text[bytes]=0;
  for(i=0;i<128;i++) insert[i]="abcdefghijklmnop"[i%16];insert[128]=0;
  for(k=0;k<2;k++) {
    exr_hyphenator *h;exr_document *d=constructed(text,"zz","hyphens:auto");exr_layout_config c=config();exr_pager *p=NULL;
    const exr_layout *page;const exr_glyph *g;size_t n,inserted=0;
    snprintf(rules,sizeof(rules),".%.40s1%s./=%s,41,0 %s",word,word+40,insert,k ? "abcd1efgh" : "");h=replacement_dictionary(rules);
    c.page.width=k ? 230 : 380;c.page.height=800;
    OK(exr_pager_create(d,font,&c,&p,&error));OK(exr_pager_set_hyphenator(p,h,&error));
    OK(exr_pager_get(p,0,&page,&error));CHECK(generated(page)>0);g=exr_layout_glyphs(page,&n);
    for(i=0;i<n;i++) {
      CHECK(!(g[i].boundaries&~15u));
      if((g[i].flags&EXR_GLYPH_GENERATED) && g[i].start==40 && g[i].codepoint>='a' && g[i].codepoint<='z') inserted++;
    }
    CHECK(k ? inserted==0 : inserted==128);
    OK(exr_pager_get(p,1,&page,&error));CHECK(generated(page)>0);
    exr_pager_free(p);exr_document_free(d);exr_hyphenator_free(h);
  }
  free(text);
}
static void case_large_context(void) {
  const char *word="abcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyz";
  const size_t bytes=1024*1024;char *text=malloc(bytes+1),rules[256];size_t i,n;exr_hyphenator *h=NULL;
  exr_hyphen_pattern_input input={sizeof(input),"lt",rules,0,1,1};exr_document *d;exr_layout_config c=config();exr_pager *p=NULL;
  const exr_layout *page;exr_bitmap first={0},again={0};const exr_glyph *g;
  CHECK(text);for(i=0;i<bytes;i++) text[i]=i%79==78 ? ' ' : word[i%79];text[bytes]=0;
  snprintf(rules,sizeof(rules),".%.20s1%s./Í=J,20,2",word,word+20);input.size=strlen(rules);
  d=constructed(text,"lt-LT","hyphens:auto");free(text);c.page.width=300;c.page.height=800;
  OK(exr_hyphenator_create_patterns_ex(&input,1,0,EXR_HYPHEN_CASE_WORD,NULL,&h,&error));
  OK(exr_pager_create(d,font,&c,&p,&error));OK(exr_pager_set_hyphenator(p,h,&error));exr_hyphenator_free(h);
  OK(exr_pager_set_cache(p,1,1024*1024,&error));OK(exr_pager_set_checkpoints(p,16,1024*1024,1,&error));
  OK(exr_pager_get(p,0,&page,&error));CHECK(generated(page)>0);OK(exr_render_page_color(page,NULL,0,&first,&error));
  OK(exr_pager_get(p,8,&page,&error));CHECK(generated(page)>0);g=exr_layout_glyphs(page,&n);
  for(i=0;i<n;i++) CHECK(!(g[i].boundaries&~15u));
  OK(exr_pager_get(p,0,&page,&error));OK(exr_render_page_color(page,NULL,0,&again,&error));
  CHECK(first.stride==again.stride && first.height==again.height && !memcmp(first.pixels,again.pixels,(size_t)first.stride*first.height));
  OK(exr_pager_get(p,8,&page,&error));CHECK(generated(page)>0 && exr_pager_statistics(p).restored_checkpoints>0);
  exr_bitmap_free(&first);exr_bitmap_free(&again);exr_pager_free(p);exr_document_free(d);
}
static void replacement_intrinsics(void) {
  const char *rules[]={".aaaa1aaaa./aaaaaaaaaaaaaaaa=a,1,8", ".aaaa1aaaa./a=aaaaaaaaaaaaaaaa,1,8"};size_t k;
  exr_attribute attrs[]={{"lang","zz"},{"style","hyphens:auto"}};
  exr_node_input nodes[]={{EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0},{EXR_NODE_CHAPTER,0,NULL,NULL,NULL,0},
    {EXR_NODE_TABLE,1,"table",NULL,attrs,2},{EXR_NODE_ROW,2,"tr",NULL,NULL,0},{EXR_NODE_CELL,3,"td",NULL,NULL,0},{EXR_NODE_TEXT,4,NULL,"aaaaaaaa",NULL,0}};
  exr_chapter_input chapter={"Intrinsic","intrinsic.unit",1,1};exr_document_input input={"Intrinsic",nodes,6,&chapter,1,NULL,0};
  for(k=0;k<2;k++) {
    exr_document *d=NULL;exr_hyphenator *h=replacement_dictionary(rules[k]);exr_layout_config c=config();exr_layout *l;size_t i,n;const exr_box *boxes;
    OK(exr_document_create(&input,&d,&error));l=layout(d,font,h,&c);boxes=exr_layout_boxes(l,&n);
    { size_t cells=0;for(i=0;i<n;i++) if(boxes[i].kind==EXR_BOX_CELL) { cells++;CHECK(boxes[i].width<=60.01f); }CHECK(cells==1); }
    CHECK(!generated(l));exr_layout_free(l);exr_document_free(d);exr_hyphenator_free(h);
  }
}
static exr_status replacement_provider(void *context,const char *language,const char *word,size_t size,
  exr_hyphen_emit_fn emit,void *sink,const exr_control *control,exr_error *e) {
  exr_hyphen_break item={4,3,5,"aa","aaa",2,3};exr_status status;(void)control;
  CHECK(!strcmp(language,"zz"));
  if(context && *(int *)context==1) return EXR_IO;
  status=size==8 && !memcmp(word,"aaaaaaaa",8) ? emit(sink,&item,e) : EXR_OK;
  return status==EXR_OK && context && *(int *)context==2 ? EXR_CANCELLED : status;
}
static void replacement_shaping(void) {
  const char *rules[]={".fi1fifi./f=fi,2,2", ".لا1لالا./لا=ل,1,3"};
  const char *words[]={"fififi","لالالا"};const char *styles[]={"hyphens:auto;width:11px", "hyphens:auto;width:20px;direction:rtl"};
  size_t k;char path[4096];exr_font *f=NULL;snprintf(path,sizeof(path),"%s/shaping/hyphen.ttf",directory);OK(exr_font_open(path,&f,&error));
  for(k=0;k<2;k++) {
    exr_hyphenator *h=replacement_dictionary(rules[k]);exr_document *d=constructed(words[k],"zz",styles[k]);exr_layout_config c=config();exr_layout *l=layout(d,f,h,&c);
    size_t n,j;const exr_glyph *g=exr_layout_glyphs(l,&n);int mapped=0;CHECK(generated(l)>0);source(d,l);positioned(d,l,&c);
    for(j=0;j<n;j++) mapped|=(g[j].flags&EXR_GLYPH_GENERATED) && g[j].start<g[j].end;
    CHECK(mapped);
    if(!k) { const exr_line *lines=exr_layout_lines(l,NULL);CHECK(near(lines[0].width,10.88f)); }
    else CHECK((g[0].flags&EXR_GLYPH_GENERATED) && g[0].start==4 && g[0].end==4 && (g[0].bidi_level&1));
    exr_layout_free(l);exr_document_free(d);exr_hyphenator_free(h);
  }
  {
    exr_hyphenator *h=replacement_dictionary(".aaaa1aaaaaaaa./لا=fiلا,4,2");exr_document *d=constructed("aaaaaaaaaaaa","zz","hyphens:auto");
    exr_layout_config c=config();exr_layout *l;const exr_glyph *g;exr_shaped_glyph *expected=NULL;exr_shape_options options=exr_shape_defaults();size_t n,j,count;int seen=0;
    c.page.width=76;l=layout(d,f,h,&c);g=exr_layout_glyphs(l,&n);
    options.font_size=14;options.direction=EXR_DIRECTION_RTL;options.script=0x61726162;
    OK(exr_shape(f,0,"لا",strlen("لا"),&options,&expected,&count,&error));CHECK(count==1);
    for(j=0;j<n;j++) if((g[j].flags&EXR_GLYPH_GENERATED) && g[j].start==3 && g[j].end==4 && g[j].glyph==expected[0].glyph) {
      CHECK((g[j].bidi_level&1) && (g[j].flags&EXR_GLYPH_SHAPED) && near(g[j].advance,expected[0].advance_x));seen=1;
    }
    CHECK(seen);exr_free(expected);source(d,l);positioned(d,l,&c);
    exr_layout_free(l);exr_document_free(d);exr_hyphenator_free(h);
  }
  exr_font_free(f);
  { exr_hyphen_discretionary_provider p={sizeof(p),replacement_provider,NULL,NULL};exr_hyphenator *h=NULL;
    exr_document *d=constructed("aaaaaaaa aaaaaaaa","zz","hyphens:auto");exr_layout_config c=config();exr_layout *l;
    c.page.width=62;OK(exr_hyphenator_create_discretionary(&p,&h,&error));l=layout(d,font,h,&c);CHECK(generated(l)>0);source(d,l);positioned(d,l,&c);
    exr_layout_free(l);exr_document_free(d);exr_hyphenator_free(h);
  }
}
static void replacement_recovery(void) {
  int mode=0;exr_hyphen_discretionary_provider provider={sizeof(provider),replacement_provider,NULL,&mode};exr_hyphenator *h=NULL;
  exr_document *d=book("rewrite-long");exr_layout_config c=config();exr_pager *p=NULL;const exr_layout *page=NULL;exr_bitmap first={0},again={0};
  OK(exr_hyphenator_create_discretionary(&provider,&h,&error));OK(exr_pager_create(d,font,&c,&p,&error));OK(exr_pager_set_hyphenator(p,h,&error));exr_hyphenator_free(h);
  OK(exr_pager_set_cache(p,1,262144,&error));OK(exr_pager_set_checkpoints(p,16,262144,1,&error));
  OK(exr_pager_get(p,0,&page,&error));OK(exr_render_page_color(page,NULL,0,&first,&error));
  mode=1;CHECK(exr_pager_get(p,1,&page,&error)==EXR_IO && !page && exr_pager_cached_count(p)==1);
  mode=2;CHECK(exr_pager_get(p,1,&page,&error)==EXR_CANCELLED && !page);
  OK(exr_pager_get(p,0,&page,&error));OK(exr_render_page_color(page,NULL,0,&again,&error));
  CHECK(first.stride==again.stride && first.height==again.height && !memcmp(first.pixels,again.pixels,(size_t)first.stride*first.height));
  mode=0;OK(exr_pager_get(p,1,&page,&error));CHECK(generated(page)>0);
  exr_bitmap_free(&first);exr_bitmap_free(&again);exr_pager_free(p);exr_document_free(d);
}
typedef struct { unsigned original,changed,last;int mode; } rematch_host;
static exr_status rematch_provider(void *context,const char *language,const char *word,size_t size,
  exr_hyphen_emit_fn emit,void *sink,const exr_control *control,exr_error *e) {
  rematch_host *host=context;exr_status status=EXR_OK;(void)control;CHECK(!strcmp(language,"zm"));
  if(size==18 && !memcmp(word,"abcdefghijklmnopqr",18)) {
    exr_hyphen_break item={4,3,5,"d","xy",1,2};host->original++;return emit(sink,&item,e);
  }
  if(size==15 && !memcmp(word,"xyfghijklmnopqr",15)) {
    exr_hyphen_break normal={4,4,4,NULL,NULL,0,0},edit={8,7,9,"k","zz",1,2};host->changed++;
    if(host->mode==1) return EXR_IO;
    if(host->mode==2) return EXR_CANCELLED;
    status=emit(sink,&normal,e);if(status==EXR_OK) status=emit(sink,&edit,e);
  } else if(size==8 && !memcmp(word,"zzmnopqr",8)) {
    exr_hyphen_break item={3,3,3,NULL,NULL,0,0};host->last++;status=emit(sink,&item,e);
  }
  return status;
}
static void rematch_provider_recovery(void) {
  rematch_host host={0};exr_hyphen_discretionary_provider provider={sizeof(provider),rematch_provider,NULL,&host};exr_hyphenator *h=NULL;
  exr_document *d=book("rematch-long");exr_layout_config c=config();exr_pager *p=NULL;const exr_layout *page=NULL;exr_bitmap first={0},again={0};
  OK(exr_hyphenator_create_discretionary(&provider,&h,&error));OK(exr_pager_create(d,font,&c,&p,&error));OK(exr_pager_set_hyphenator(p,h,&error));exr_hyphenator_free(h);
  OK(exr_pager_set_cache(p,1,262144,&error));OK(exr_pager_set_checkpoints(p,16,262144,1,&error));
  OK(exr_pager_get(p,0,&page,&error));OK(exr_render_page_color(page,NULL,0,&first,&error));CHECK(host.original && host.changed);
  host.mode=1;CHECK(exr_pager_get(p,2,&page,&error)==EXR_IO && !page && exr_pager_cached_count(p)==1);
  host.mode=2;CHECK(exr_pager_get(p,2,&page,&error)==EXR_CANCELLED && !page);
  OK(exr_pager_get(p,0,&page,&error));OK(exr_render_page_color(page,NULL,0,&again,&error));
  CHECK(first.stride==again.stride && first.height==again.height && !memcmp(first.pixels,again.pixels,(size_t)first.stride*first.height));
  host.mode=0;OK(exr_pager_get(p,2,&page,&error));CHECK(host.last && generated(page)>0);
  exr_bitmap_free(&first);exr_bitmap_free(&again);exr_pager_free(p);exr_document_free(d);
}
static exr_status bidi_provider(void *context,const char *language,const char *word,size_t size,
  exr_hyphen_emit_fn emit,void *sink,const exr_control *control,exr_error *e) {
  exr_hyphen_break item={4,3,5,"ا1中","12ا",0,0};(void)control;CHECK(!strcmp(language,"zb"));
  if(*(int *)context==1) return EXR_IO;
  if(*(int *)context==2) return EXR_CANCELLED;
  item.before_size=strlen(item.before);item.after_size=strlen(item.after);
  return size==12 && !memcmp(word,"aaaaaaaaaaaa",12) ? emit(sink,&item,e) : EXR_OK;
}
static void bidi_provider_recovery(void) {
  int mode=0;exr_hyphen_discretionary_provider provider={sizeof(provider),bidi_provider,NULL,&mode};exr_hyphenator *h=NULL;
  exr_document *d=book("bidi-long");exr_layout_config c=config();exr_pager *p=NULL;const exr_layout *page=NULL;exr_bitmap first={0},again={0};
  OK(exr_hyphenator_create_discretionary(&provider,&h,&error));OK(exr_pager_create(d,font,&c,&p,&error));OK(exr_pager_set_hyphenator(p,h,&error));exr_hyphenator_free(h);
  OK(exr_pager_set_cache(p,1,262144,&error));OK(exr_pager_set_checkpoints(p,16,262144,1,&error));
  OK(exr_pager_get(p,0,&page,&error));OK(exr_render_page_color(page,NULL,0,&first,&error));
  mode=1;CHECK(exr_pager_get(p,2,&page,&error)==EXR_IO && !page && exr_pager_cached_count(p)==1);
  mode=2;CHECK(exr_pager_get(p,2,&page,&error)==EXR_CANCELLED && !page);
  OK(exr_pager_get(p,0,&page,&error));OK(exr_render_page_color(page,NULL,0,&again,&error));
  CHECK(first.stride==again.stride && first.height==again.height && !memcmp(first.pixels,again.pixels,(size_t)first.stride*first.height));
  mode=0;OK(exr_pager_get(p,2,&page,&error));CHECK(generated(page)>0);
  exr_bitmap_free(&first);exr_bitmap_free(&again);exr_pager_free(p);exr_document_free(d);
}
typedef struct { int mode;size_t calls; } changing_host;
static exr_status changing_breaks(void *context,const char *lang,const char *word,size_t size,
  exr_hyphen_emit_fn emit,void *sink,const exr_control *control,exr_error *e) {
  changing_host *s=context;exr_hyphen_break item={4,0,5,NULL,"12א",0,strlen("12א")};
  (void)lang;(void)control;
  if(size!=12 || memcmp(word,"aaaaaaaaaaaa",12)) return EXR_OK;
  s->calls++;
  item.before=s->mode==1 && (s->calls&1) ? "א1中" : s->mode==2 && s->calls>=3 ? "L1中" : "ا1中";
  item.before_size=strlen(item.before);return emit(sink,&item,e);
}
static void plan_provider_recovery(void) {
  changing_host state={1,0};exr_hyphen_discretionary_provider provider={sizeof(provider),changing_breaks,NULL,&state};
  exr_hyphenator *h=NULL;exr_document *d=constructed("aaaaaaaaaaaa","zz","hyphens:auto");exr_layout_config c=config();
  exr_pager *p=NULL;const exr_layout *page=NULL;c.page.width=76;
  OK(exr_hyphenator_create_discretionary(&provider,&h,&error));OK(exr_pager_create(d,font,&c,&p,&error));OK(exr_pager_set_hyphenator(p,h,&error));
  CHECK(exr_pager_get(p,0,&page,&error)==EXR_LIMIT && !page && !exr_pager_cached_count(p));CHECK(state.calls>=8);
  state.mode=2;state.calls=0;CHECK(exr_pager_get(p,0,&page,&error)==EXR_FORMAT && !page && !exr_pager_cached_count(p));
  state.mode=0;state.calls=0;OK(exr_pager_get(p,0,&page,&error));CHECK(page && generated(page)>0);
  exr_pager_free(p);exr_document_free(d);exr_hyphenator_free(h);
}
static void tall_row_limit(void) {
  exr_document *d=book("bidi-future-tall-row");exr_hyphenator *h=dictionary();exr_layout_config c=config();exr_layout *l=NULL;
  OK(exr_layout_create_hyphenated(d,font,&c,h,&l,&error));source(d,l);positioned(d,l,&c);exr_layout_free(l);
  exr_document_free(d);exr_hyphenator_free(h);
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
  exr_document *d=book(name); exr_hyphenator *h=!strncmp(name,"stem-",5) ? stem_dictionary(!strncmp(name,"stem-case",9)) : !strncmp(name,"case-",5) ? case_dictionary() : dictionary(); exr_layout_config c=config(); exr_layout *all;
  exr_pager *fast=NULL,*slow=NULL; const exr_layout *a,*b; size_t np,i,targets[]={20,15,2,11,0,20,4};
  if(!strcmp(name,"rematch-table") || !strcmp(name,"bidi-future-table") || !strcmp(name,"insertion-table") || !strcmp(name,"case-table") || !strcmp(name,"stem-table")) c.page.height=160;
  c.page.width=(!strncmp(name,"compound",8) || !strncmp(name,"rewrite",7) || !strncmp(name,"rematch",7) || !strncmp(name,"boundary",8) || !strncmp(name,"bidi",4) || !strncmp(name,"insertion",9) || !strncmp(name,"case-",5) || !strncmp(name,"stem-",5)) ? 80 : 55; all=layout(d,font,h,&c); exr_layout_pages(all,&np); if(np<=20 || !generated(all)) fprintf(stderr,"replay %s: %zu pages, %zu generated\n",name,np,generated(all));CHECK(np>20 && generated(all)>0); source(d,all);
  if(!strcmp(name,"case-long") || !strcmp(name,"case-insertion")) {
    size_t n,k,letters=0;const exr_glyph *g=exr_layout_glyphs(all,&n);
    for(k=0;k<n;k++) if((g[k].flags&EXR_GLYPH_GENERATED) && g[k].codepoint!='-' && g[k].codepoint!=0x2010) {
      CHECK(g[k].codepoint>='A' && g[k].codepoint<='Z');letters++;
    }
    CHECK(letters>400);
  }
  if(!strcmp(name,"bidi-auto")) { const exr_glyph *glyphs=exr_layout_glyphs(all,NULL);CHECK((glyphs[0].flags&EXR_GLYPH_GENERATED) && glyphs[0].start==0 && glyphs[0].end==4 && (glyphs[0].bidi_level&1)); }
  if(!strcmp(name,"bidi-leading") || !strcmp(name,"bidi-paragraphs")) {
    const exr_glyph *glyphs=exr_layout_glyphs(all,NULL);size_t k=0;
    if(!strcmp(name,"bidi-paragraphs")) { for(;k<4;k++) CHECK(glyphs[k].codepoint=='1' && glyphs[k].bidi_level==0);k++; }
    for(;k<10;k++) CHECK(glyphs[k].codepoint=='1' && glyphs[k].bidi_level==2);
  }
  if(!strcmp(name,"bidi-leading-ruby")) {
    size_t bytes,count,k,seen=0;const char *text=exr_document_text(d,&bytes),*digits=strstr(text,"1111111111");
    const exr_glyph *glyphs=exr_layout_glyphs(all,&count);CHECK(digits);
    for(k=0;k<count;k++) if(glyphs[k].start>=(size_t)(digits-text) && glyphs[k].start<(size_t)(digits-text)+64) {
      CHECK(glyphs[k].codepoint=='1' && glyphs[k].bidi_level==2);seen++;
    }
    CHECK(seen==64);
  }
  if(!strcmp(name,"bidi-future-neutral")) {
    size_t count,k,seen=0;const exr_glyph *glyphs=exr_layout_glyphs(all,&count);
    for(k=0;k<count && !glyphs[k].page;k++) if(glyphs[k].codepoint=='+') { CHECK(glyphs[k].bidi_level==1);seen++; }
    CHECK(seen>0);
  }
  if(!strcmp(name,"canonical")) {
    size_t count,j,bytes;const exr_glyph *glyphs=exr_layout_glyphs(all,&count);const char *text=exr_document_text(d,&bytes);
    CHECK(bytes==6399 && !memcmp(text,"ÉTÉ ",8));
    for(j=0;j<count;j++) if(glyphs[j].flags&EXR_GLYPH_GENERATED) CHECK(glyphs[j].start==glyphs[j].end && glyphs[j].start%8==3);
  }
  if(!strncmp(name,"compound",8)) {
    size_t count,j;const exr_glyph *glyphs=exr_layout_glyphs(all,&count);
    if(!strcmp(name,"compound")) {
      const exr_line *lines=exr_layout_lines(all,NULL);
      CHECK(lines[0].glyph_count==6 && (glyphs[5].flags&EXR_GLYPH_GENERATED) && glyphs[5].start==5 && near(lines[0].width,42));
    }
    for(j=0;j<count;j++) if(glyphs[j].flags&EXR_GLYPH_GENERATED) {
      if(!strcmp(name,"compound")) CHECK(glyphs[j].start%9>=1 && glyphs[j].start%9<=7);
      else CHECK(glyphs[j].start%16==2 || glyphs[j].start%16==13);
    }
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
  char path[4096]; CHECK(argc==2 || argc==3);directory=argv[1];snprintf(path,sizeof(path),"%s/fonts/primary.ttf",directory); OK(exr_font_open(path,&font,&error)); if(argc==3) { if(!strcmp(argv[2],"bidi")) { replacement_bidi();bidi_mark_tail();plan_provider_recovery(); } else if(!strcmp(argv[2],"case-large")) { case_large_context(); } else if(!strcmp(argv[2],"insertion")) { long_insertion();generated_hyphenation();generated_boundaries();generated_shaping();generated_recovery();insertion_large_context();case_large_context(); } else replay(argv[2]);exr_font_free(font);printf("%u display bidi checks passed\n",checks);return 0; } ordinary();conditional_stems();replacements();rematching();replacement_boundaries();replacement_bidi();bidi_mark_tail();long_insertion();generated_hyphenation();generated_boundaries();generated_shaping();generated_recovery();insertion_large_context();case_large_context();replacement_intrinsics();replacement_shaping();replacement_recovery();rematch_provider_recovery();bidi_provider_recovery();plan_provider_recovery();tall_row_limit();fixtures();cascade();joining();word_boundaries();provider_recovery();sessions();replay("long");replay("rtl");replay("vertical");replay("float");replay("orthogonal");replay("canonical");replay("compound");replay("compound-joiner");replay("rewrite-long");replay("rewrite-rtl");replay("rewrite-vertical");replay("rewrite-float");replay("rewrite-orthogonal");replay("rewrite-table");replay("rewrite-inline");replay("rewrite-gap");replay("rewrite-canonical");replay("rematch-long");replay("rematch-rtl");replay("rematch-vertical");replay("rematch-float");replay("rematch-orthogonal");replay("rematch-table");replay("rematch-inline");replay("rematch-gap");replay("rematch-canonical");replay("boundary-long");replay("boundary-rtl");replay("boundary-vertical");replay("boundary-float");replay("boundary-orthogonal");replay("boundary-table");replay("boundary-inline");replay("boundary-gap");replay("boundary-canonical");replay("boundary-ri");replay("boundary-emoji");replay("bidi-long");replay("bidi-rtl");replay("bidi-vertical");replay("bidi-float");replay("bidi-orthogonal");replay("bidi-table");replay("bidi-inline");replay("bidi-bracket");replay("bidi-isolate");replay("bidi-override");replay("bidi-auto");replay("bidi-leading");replay("bidi-leading-float");replay("bidi-paragraphs");replay("bidi-leading-ruby");replay("bidi-future-neutral");replay("bidi-future-bracket");replay("bidi-future-isolate");replay("bidi-future-numbers");replay("bidi-future-float");replay("bidi-future-vertical");replay("bidi-future-table");replay("bidi-future-tall-row");replay("insertion-long");replay("insertion-rtl");replay("insertion-vertical");replay("insertion-float");replay("insertion-orthogonal");replay("insertion-inline");replay("insertion-table");replay("insertion-mixed");replay("case-long");replay("case-title");replay("case-rtl");replay("case-vertical");replay("case-float");replay("case-table");replay("case-tr");replay("case-lt");replay("case-el");replay("case-canonical");replay("case-insertion");replay("case-title-delete");replay("case-mixed");replay("case-orthogonal");replay("case-inline");replay("stem-long");replay("stem-rtl");replay("stem-vertical");replay("stem-float");replay("stem-orthogonal");replay("stem-table");replay("stem-inline");replay("stem-canonical");replay("stem-case"); exr_font_free(font); printf("%u automatic hyphen layout checks passed\n",checks); return 0;
}
