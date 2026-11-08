/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

static exr_error error;
#define CHECK(x) do { if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message);exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static int same(exr_text_range a,exr_text_range b) {
  return a.start.part==b.start.part && a.start.offset==b.start.offset && a.end.part==b.end.part && a.end.offset==b.end.offset;
}
typedef struct { const char *body[2]; } source;
static exr_status load(void *ctx,size_t part,exr_document **out,exr_error *e) {
  source *s=ctx;return exr_document_open_memory(EXR_TXT,s->body[part],strlen(s->body[part]),out,e);
}
static exr_publication *publication(source *s,int reverse) {
  exr_publication *p=NULL;exr_publication_input input={0};
  exr_part parts[2]={{"first","first.txt","",1},{"second","second.txt","",1}};
  if(reverse) { exr_part tmp=parts[0];parts[0]=parts[1];parts[1]=tmp; }
  input.parts=parts;input.part_count=2;input.context=s;input.load=load;
  OK(exr_publication_create(&input,&p,&error));return p;
}
static char *body(unsigned part) {
  size_t i,at=0;char *s=calloc(1,40000);CHECK(s);
  for(i=0;i<150;i++) at+=(size_t)snprintf(s+at,40000-at,
    "Part %u paragraph %03u: alpha beta gamma. Unique item %03u has words, punctuation! 中文测试，锚点跟随文字。\n\n",
    part,(unsigned)i,(unsigned)i);
  CHECK(at<40000);return s;
}
static size_t *boundaries(const exr_document *d,size_t *count) {
  size_t size,i,n=0,*out;const char *text=exr_document_text(d,&size);
  out=malloc((size+1)*sizeof(*out));CHECK(out);
  for(i=0;i<=size;i++) if(i==size || ((unsigned char)text[i]&0xc0)!=0x80) out[n++]=i;
  *count=n;return out;
}
static unsigned rng=0x41ce2026;
static unsigned random_value(void) { rng=rng*1664525u+1013904223u;return rng; }
static void samples(exr_publication *p,exr_text_range *ranges,size_t count,size_t first,size_t second) {
  exr_document *d[2]={NULL,NULL};size_t *points[2],n[2],i;
  OK(exr_publication_load(p,first,&d[0],&error));OK(exr_publication_load(p,second,&d[1],&error));
  points[0]=boundaries(d[0],&n[0]);points[1]=boundaries(d[1],&n[1]);
  for(i=0;i<count;i++) {
    size_t a=random_value()%n[0],b;
    ranges[i].start.part=first;ranges[i].start.offset=points[0][a];
    if(i%10==0 && first!=second) { b=random_value()%n[1];ranges[i].end.part=second;ranges[i].end.offset=points[1][b]; }
    else {
      b=a+(i%13==0 ? 0 : 1+random_value()%100);if(b>=n[0]) b=n[0]-1;
      ranges[i].end.part=first;ranges[i].end.offset=points[0][b];
    }
  }
  for(i=0;i<2;i++) { free(points[i]);exr_document_free(d[i]); }
}
static void roundtrips(exr_publication *p,size_t first,size_t second) {
  exr_text_range ranges[200];size_t i,passed=0;
  samples(p,ranges,200,first,second);
  for(i=0;i<200;i++) {
    exr_content_anchor anchor={0};exr_text_range_match match;
    OK(exr_anchor_from_range(p,&ranges[i],NULL,&anchor,&error));
    OK(exr_range_from_anchor(p,&anchor,NULL,&match,&error));
    passed+=match.state==EXR_ANCHOR_FOUND && same(match.range,ranges[i]);
    exr_content_anchor_free(&anchor);
  }
  printf("same-layout: %u/200 = %.2f%% (seed 0x41ce2026; 20 cross-part)\n",(unsigned)passed,100.0*passed/200);
  CHECK(passed==200);
}
static void mapping(void) {
  char *a=body(0),*b=body(1);source s={{a,b}};exr_publication *p=publication(&s,0);
  roundtrips(p,0,1);
  /* Identical repeated context remains exact in an unchanged projection. */
  s.body[0]="repeat repeat repeat repeat repeat repeat repeat repeat repeat repeat repeat repeat repeat repeat repeat repeat";
  {
    exr_text_range r={{0,45},{0,52}};exr_content_anchor anchor={0};exr_text_range_match match;
    OK(exr_anchor_from_range(p,&r,NULL,&anchor,&error));
    OK(exr_range_from_anchor(p,&anchor,NULL,&match,&error));CHECK(match.state==EXR_ANCHOR_FOUND && same(r,match.range));
    exr_content_anchor_free(&anchor);
    r.start.offset=2;r.end.offset=1;CHECK(exr_anchor_from_range(p,&r,NULL,&anchor,&error)==EXR_ARGUMENT);
    CHECK(!anchor.start.part_id);
  }
  exr_publication_free(p);free(a);free(b);
}
static int cancel(void *ctx) { (void)ctx;return 1; }
static void relocation(void) {
  const char *original="abcdefghijklmnopqrstuvwxyzABCDEFtarget0123456789abcdefghijklmnopqrstuv";
  char changed[256];source s={{original,"other part"}},reversed;exr_publication *p=publication(&s,0),*q;
  exr_text_range r={{0,32},{0,38}};exr_content_anchor anchor={0};exr_text_range_match match;
  exr_control control={0};
  OK(exr_anchor_from_range(p,&r,NULL,&anchor,&error));
  snprintf(changed,sizeof(changed),"New frontmatter. %s",original);s.body[0]=changed;
  OK(exr_range_from_anchor(p,&anchor,NULL,&match,&error));
  CHECK(match.state==EXR_ANCHOR_FOUND && match.range.start.offset==49 && match.range.end.offset==55);
  reversed.body[0]=s.body[1];reversed.body[1]=s.body[0];q=publication(&reversed,1);
  OK(exr_range_from_anchor(q,&anchor,NULL,&match,&error));CHECK(match.state==EXR_ANCHOR_FOUND && match.range.start.part==1);
  exr_publication_free(q);
  snprintf(changed,sizeof(changed),"%s | %s",original,original);
  OK(exr_range_from_anchor(p,&anchor,NULL,&match,&error));CHECK(match.state==EXR_ANCHOR_AMBIGUOUS && match.range.start.part==SIZE_MAX);
  s.body[0]="deleted";OK(exr_range_from_anchor(p,&anchor,NULL,&match,&error));CHECK(match.state==EXR_ANCHOR_MISSING);
  control.cancelled=cancel;CHECK(exr_range_from_anchor(p,&anchor,&control,&match,&error)==EXR_CANCELLED);
  CHECK(match.range.start.offset==SIZE_MAX);
  exr_content_anchor_free(&anchor);exr_publication_free(p);
  /* No stable IDs: canonical path fallback. Duplicate identities reject capture. */
  {
    exr_part parts[2]={{"","one.txt","",1},{"","two.txt","",1}};exr_publication_input input={0};
    input.parts=parts;input.part_count=2;input.load=load;input.context=&s;
    s.body[0]=original;OK(exr_publication_create(&input,&p,&error));
    OK(exr_anchor_from_range(p,&r,NULL,&anchor,&error));
    OK(exr_range_from_anchor(p,&anchor,NULL,&match,&error));CHECK(match.state==EXR_ANCHOR_FOUND);
    exr_content_anchor_free(&anchor);exr_publication_free(p);
    parts[1].path="one.txt";OK(exr_publication_create(&input,&p,&error));
    CHECK(exr_anchor_from_range(p,&r,NULL,&anchor,&error)==EXR_ARGUMENT);CHECK(!anchor.start.part_path);
    exr_publication_free(p);
  }
  puts("relocation: insertion, part reorder, ambiguity, deletion, cancellation, identity passed");
}
static void expansion(void) {
  source s={{"Hello world. Next sentence!\n\nLast paragraph.","second chapter"}};
  exr_publication *p=publication(&s,0);exr_text_range r={{0,7},{0,7}},out;
  OK(exr_range_expand(p,&r,EXR_RANGE_WORD,NULL,&out,&error));CHECK(out.start.offset==6 && out.end.offset==11);
  r.start.offset=1;r.end.offset=2;OK(exr_range_expand(p,&r,EXR_RANGE_SENTENCE,NULL,&out,&error));CHECK(out.start.offset==0 && out.end.offset==12);
  r.start.offset=2;r.end.offset=3;OK(exr_range_expand(p,&r,EXR_RANGE_PARAGRAPH,NULL,&out,&error));CHECK(out.start.offset==0 && out.end.offset==27);
  r.start.offset=7;r.end.part=1;r.end.offset=3;
  OK(exr_range_expand(p,&r,EXR_RANGE_WORD,NULL,&out,&error));CHECK(out.start.offset==6 && out.end.part==1 && out.end.offset==6);
  r.start.part=0;r.end.part=0;r.start.offset=6;r.end.offset=11;
  OK(exr_range_expand(p,&r,EXR_RANGE_WORD,NULL,&r,&error));CHECK(r.start.offset==6 && r.end.offset==11);
  r.start.offset=7;r.end.part=1;r.end.offset=0;
  OK(exr_range_expand(p,&r,EXR_RANGE_WORD,NULL,&out,&error));CHECK(out.start.offset==6 && out.end.part==1 && out.end.offset==0);
  r.start.part=r.end.part=1;r.start.offset=r.end.offset=14;
  OK(exr_range_expand(p,&r,EXR_RANGE_CHAR,NULL,&out,&error));CHECK(same(out,r));
  s.body[0]="Ae\xcc\x81 👩‍💻 中文。";
  r.start.part=r.end.part=0;
  r.start.offset=r.end.offset=2;OK(exr_range_expand(p,&r,EXR_RANGE_CHAR,NULL,&out,&error));CHECK(out.start.offset==1 && out.end.offset==4);
  r.start.offset=r.end.offset=5;OK(exr_range_expand(p,&r,EXR_RANGE_CHAR,NULL,&out,&error));CHECK(out.start.offset==5 && out.end.offset==16);
  r.start.offset=r.end.offset=17;OK(exr_range_expand(p,&r,EXR_RANGE_WORD,NULL,&out,&error));CHECK(out.start.offset==17 && out.end.offset==20);
  r.start.offset=18;CHECK(exr_range_expand(p,&r,EXR_RANGE_CHAR,NULL,&out,&error)==EXR_ARGUMENT);CHECK(out.start.part==SIZE_MAX);
  exr_publication_free(p);puts("expansion: grapheme/emoji, word/CJK, sentence, paragraph, exclusive end and cross-part passed");
}

/* Independent positioned fixture: known glyph cells and expected caret offsets. */
static void hits(const char *font_path) {
  exr_document *d=NULL;exr_font *font=NULL;exr_layout *l=NULL;
  exr_glyph g[10]={{0}};exr_line line={0};exr_box image={0};exr_positioned_page page={0};
  exr_positioned_input input={0};exr_layout_config config=exr_layout_config_defaults();
  exr_text_position hit;size_t i,passed=0;
  OK(exr_document_open_memory(EXR_TXT,"abcdefgh.!",10,&d,&error));OK(exr_font_open(font_path,&font,&error));
  for(i=0;i<10;i++) {
    g[i].codepoint=(uint32_t)(i<8 ? 'a'+i : i==8 ? '.' : '!');
    g[i].glyph=1;g[i].x=20+(float)i*10;g[i].baseline=40;g[i].advance=10;g[i].size=20;
    g[i].start=g[i].cluster_start=i;g[i].end=g[i].cluster_end=i+1;g[i].line_height=20;
  }
  line.start=0;line.end=10;line.glyph_count=10;line.x=20;line.y=20;line.width=100;line.height=20;
  image.kind=EXR_BOX_IMAGE;image.page=0;image.node=SIZE_MAX;image.resource=SIZE_MAX;
  image.start=image.end=10;image.x=150;image.y=20;image.width=30;image.height=30;image.flags=1;
  page.width=200;page.height=100;page.content.start=0;page.content.end=10;page.content.line_count=1;page.content.box_count=1;
  input.struct_size=sizeof(input);input.pages=&page;input.page_count=1;input.glyphs=g;input.glyph_count=10;
  input.lines=&line;input.line_count=1;input.boxes=&image;input.box_count=1;
  config.page.width=200;config.page.height=100;config.page.margin=0;
  OK(exr_layout_create_positioned(d,font,&input,&config,&l,&error));
  for(i=0;i<50;i++) {
    float x,y=30;size_t want;
    if(i<10) { x=31+(float)i*0.8f;want=i<5 ? 1 : 2; }
    else if(i<20) { x=100+(float)(i-10);want=i<15 ? 8 : 9; } /* punctuation */
    else if(i<30) { x=150+(float)(i-20);want=SIZE_MAX; } /* image */
    else if(i<40) { x=120;y=21+(float)(i-30);want=10; } /* exact line end */
    else { x=20;y=21+(float)(i-40);want=0; } /* exact line start */
    OK(exr_hit_test(l,3,0,x,y,&hit,&error));
    if(hit.offset==want && hit.part==(want==SIZE_MAX ? SIZE_MAX : 3)) passed++;
    else fprintf(stderr,"hit %u: (%g,%g) got %u expected %u\n",(unsigned)i,x,y,(unsigned)hit.offset,(unsigned)want);
  }
  printf("hit-test: %u/50 = %.2f%%\n",(unsigned)passed,2.0*passed);CHECK(passed==50);
  CHECK(exr_hit_test(l,0,1,20,30,&hit,&error)==EXR_ARGUMENT && hit.part==SIZE_MAX);
  CHECK(exr_hit_test(l,0,0,NAN,30,&hit,&error)==EXR_ARGUMENT);
  OK(exr_hit_test(l,0,0,10,30,&hit,&error));CHECK(hit.part==SIZE_MAX);
  exr_layout_free(l);
  image.x=110;OK(exr_layout_create_positioned(d,font,&input,&config,&l,&error));
  OK(exr_hit_test(l,0,0,115,30,&hit,&error));CHECK(hit.offset==SIZE_MAX);exr_layout_free(l);
  image.x=150;for(i=0;i<10;i++) g[i].bidi_level=1;
  OK(exr_layout_create_positioned(d,font,&input,&config,&l,&error));
  OK(exr_hit_test(l,0,0,21,30,&hit,&error));CHECK(hit.offset==1);exr_layout_free(l);
  for(i=0;i<10;i++) { g[i].bidi_level=0;g[i].flags=EXR_GLYPH_VERTICAL;g[i].x=20;g[i].baseline=20+(float)i*10; }
  line.width=20;line.height=100;page.height=160;config.page.height=160;
  OK(exr_layout_create_positioned(d,font,&input,&config,&l,&error));
  OK(exr_hit_test(l,0,0,30,21,&hit,&error));CHECK(hit.offset==0);
  OK(exr_hit_test(l,0,0,30,119,&hit,&error));CHECK(hit.offset==10);
  exr_layout_free(l);exr_font_free(font);exr_document_free(d);
}

static void reflow(exr_publication *p,size_t first,size_t second,const char *font1,const char *font2) {
  exr_text_range ranges[100];exr_content_anchor anchors[100]={0};exr_font *fonts[2]={NULL,NULL};
  size_t i,stage,group,passed[3]={0},changed[3]={0},initial[100];
  const float sizes[]={17,18,24,17,17,17,17,17};
  const float widths[]={1280,1280,1280,1280,1280,1280,1552,1280};
  const float heights[]={800,800,800,800,800,800,928,800};
  samples(p,ranges,100,first,second);
  OK(exr_font_open(font1,&fonts[0],&error));OK(exr_font_open(font2,&fonts[1],&error));
  for(i=0;i<100;i++) OK(exr_anchor_from_range(p,&ranges[i],NULL,&anchors[i],&error));
  for(stage=0;stage<8;stage++) {
    exr_document *d=NULL;exr_layout *l=NULL;exr_layout_config cfg=exr_layout_config_defaults();size_t pages;
    cfg.page.width=widths[stage];cfg.page.height=heights[stage];cfg.page.font_size=sizes[stage];
    cfg.document_css=0;cfg.embedded_fonts=0;
    OK(exr_publication_load(p,first,&d,&error));
    OK(exr_layout_create_ex(d,fonts[stage==4 ? 1 : 0],&cfg,&l,&error));
    exr_layout_pages(l,&pages);CHECK(pages>0);
    for(i=0;i<100;i++) {
      exr_text_range_match m;size_t page=exr_layout_page_at(l,ranges[i].start.offset);
      CHECK(page<pages);
      if(!stage) initial[i]=page;
      else if(stage==1 || stage==2 || stage==4 || stage==6) changed[stage<3 ? 0 : stage==4 ? 1 : 2]+=page!=initial[i];
      OK(exr_range_from_anchor(p,&anchors[i],NULL,&m,&error));
      if(stage==3 || stage==5 || stage==7) {
        group=stage==3 ? 0 : stage==5 ? 1 : 2;
        if(m.state==EXR_ANCHOR_FOUND && same(m.range,ranges[i])) passed[group]++;
        else fprintf(stderr,"group %u range %u mismatch state %d: (%u,%u)-(%u,%u)\n",(unsigned)group,(unsigned)i,m.state,
          (unsigned)m.range.start.part,(unsigned)m.range.start.offset,(unsigned)m.range.end.part,(unsigned)m.range.end.offset);
      } else CHECK(m.state==EXR_ANCHOR_FOUND && same(m.range,ranges[i]));
    }
    printf("stage %u: %.0fx%.0f %.0fpx font%u: %u pages\n",(unsigned)stage,cfg.page.width,cfg.page.height,cfg.page.font_size,stage==4 ? 2u : 1u,(unsigned)pages);
    exr_layout_free(l);exr_document_free(d);
  }
  for(i=0;i<3;i++) {
    printf("%s: %u/100 = %.2f%%; page movements=%u; mismatches=%u\n",i==0 ? "size-17-18-24-17" : i==1 ? "font-roundtrip" : "window-roundtrip",
      (unsigned)passed[i],(double)passed[i],(unsigned)changed[i],(unsigned)(100-passed[i]));CHECK(passed[i]==100);
  }
  for(i=0;i<100;i++) exr_content_anchor_free(&anchors[i]);
  exr_font_free(fonts[0]);exr_font_free(fonts[1]);
}
int main(int argc,char **argv) {
  CHECK(argc>=2);
  if(!strcmp(argv[1],"mapping")) mapping();
  else if(!strcmp(argv[1],"relocation")) relocation();
  else if(!strcmp(argv[1],"expansion")) expansion();
  else if(!strcmp(argv[1],"hits")) { CHECK(argc==3);hits(argv[2]); }
  else if(!strcmp(argv[1],"reflow")) {
    source s;exr_publication *p;CHECK(argc==4);s.body[0]=body(0);s.body[1]=body(1);p=publication(&s,0);
    reflow(p,0,1,argv[2],argv[3]);exr_publication_free(p);free((void *)s.body[0]);free((void *)s.body[1]);
  } else if(!strcmp(argv[1],"measure")) {
    exr_publication *p=NULL;size_t n,i,first=SIZE_MAX,second=SIZE_MAX;CHECK(argc==5);
    OK(exr_publication_open(argv[2],&p,&error));exr_publication_parts(p,&n);
    for(i=0;i<n && second==SIZE_MAX;i++) {
      exr_document *d=NULL;size_t size;OK(exr_publication_load(p,i,&d,&error));exr_document_text(d,&size);exr_document_free(d);
      if(size>10000) { if(first==SIZE_MAX) first=i;else second=i; }
    }
    CHECK(first!=SIZE_MAX && second!=SIZE_MAX);printf("real book endpoint parts: %u, %u\n",(unsigned)first,(unsigned)second);
    roundtrips(p,first,second);reflow(p,first,second,argv[3],argv[4]);exr_publication_free(p);
  } else CHECK(0);
  return 0;
}
