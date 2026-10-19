/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static exr_text_region region(size_t start,size_t end,double x) {
  exr_text_region r={0}; r.start=start; r.end=end; r.quad[0]=r.quad[6]=x; r.quad[2]=r.quad[4]=x+1; r.quad[5]=r.quad[7]=2; return r;
}
static int cancel(void *context) { return *(int *)context; }
static int later(void *context) { unsigned *calls=context; return ++*calls>=3; }
static void snapshots(void) {
  char bytes[7]="A\xe4\xb8\xad\0B"; const char expected[6]={'A',(char)0xe4,(char)0xb8,(char)0xad,0,'B'};
  exr_text_region regions[4]={0}; exr_fixed_text *text=NULL; const exr_text_region *view; size_t size,count;
  regions[0]=region(0,1,0); regions[1]=region(1,4,2); regions[1].flags=EXR_REGION_VERTICAL;
  regions[2]=region(1,4,-5); regions[2].flags=EXR_REGION_INVISIBLE; regions[3]=region(5,6,8);
  OK(exr_fixed_text_create(bytes,6,regions,4,NULL,&text,&error)); memset(bytes,0,sizeof(bytes)); memset(regions,0,sizeof(regions));
  CHECK(!memcmp(exr_fixed_text_string(text,&size),expected,6) && size==6);
  view=exr_fixed_text_regions(text,&count); CHECK(count==4 && view[1].start==1 && view[1].end==4 && view[1].flags==EXR_REGION_VERTICAL && view[2].quad[0]==-5);
  CHECK(exr_fixed_text_memory_size(text)>=sizeof(*regions)*4+7); exr_fixed_text_free(text);
  regions[0]=region(1,4,0); regions[0].start=2;
  CHECK(exr_fixed_text_create(expected,6,regions,1,NULL,&text,&error)==EXR_ARGUMENT && !text);
  regions[0]=region(0,2,0); CHECK(exr_fixed_text_create(expected,6,regions,1,NULL,&text,&error)==EXR_ARGUMENT && !text);
  regions[0]=region(0,7,0); CHECK(exr_fixed_text_create(expected,6,regions,1,NULL,&text,&error)==EXR_ARGUMENT && !text);
  regions[0]=region(0,1,0); regions[0].quad[3]=NAN; CHECK(exr_fixed_text_create(expected,6,regions,1,NULL,&text,&error)==EXR_ARGUMENT && !text);
  regions[0]=region(0,1,0); regions[0].flags=4; CHECK(exr_fixed_text_create(expected,6,regions,1,NULL,&text,&error)==EXR_ARGUMENT && !text);
  CHECK(exr_fixed_text_create("\xc3",1,NULL,0,NULL,&text,&error)==EXR_ENCODING && !text);
  CHECK(exr_fixed_text_create("x",(size_t)64*1024*1024+1,NULL,0,NULL,&text,&error)==EXR_LIMIT && !text);
  CHECK(exr_fixed_text_create("x",1,regions,(size_t)2*1024*1024,NULL,&text,&error)==EXR_LIMIT && !text);
  { exr_control control={0}; int stopped=1; unsigned calls=0; control.cancelled=cancel; control.context=&stopped;
    CHECK(exr_fixed_text_create("x",1,NULL,0,&control,&text,&error)==EXR_CANCELLED && !text);
    control.cancelled=later; control.context=&calls; regions[0]=region(0,1,0);
    CHECK(exr_fixed_text_create("x",1,regions,1,&control,&text,&error)==EXR_CANCELLED && !text);
  }
  OK(exr_fixed_text_create(NULL,0,NULL,0,NULL,&text,&error)); CHECK(exr_fixed_text_string(text,&size) && !size && !exr_fixed_text_regions(text,&count) && !count); exr_fixed_text_free(text);
  CHECK(!exr_fixed_text_string(NULL,&size) && !size && !exr_fixed_text_regions(NULL,&count) && !count && !exr_fixed_text_memory_size(NULL)); exr_fixed_text_free(NULL);
}
typedef struct { exr_fixed_document *document; size_t calls,releases; int fail,missing; } provider;
static exr_status draw(void *context,size_t page,const double matrix[6],const exr_draw_sink *sink,const exr_control *control,exr_error *e) {
  (void)context; (void)page; (void)matrix; (void)sink; (void)control; (void)e; return EXR_OK;
}
static exr_status load_text(void *context,size_t page,const exr_control *control,exr_fixed_text **out,exr_error *e) {
  provider *p=context; exr_text_region r=region(0,2,0); exr_fixed_text *nested=NULL; exr_error local={0}; exr_status status; (void)page; p->calls++;
  CHECK(exr_fixed_load_text(p->document,0,NULL,&nested,&local)==EXR_ARGUMENT && !nested);
  if(p->missing) return EXR_OK;
  status=exr_fixed_text_create("AB",2,&r,1,control,out,e); return p->fail ? EXR_CANCELLED : status;
}
static void release(void *context) { ((provider *)context)->releases++; }
static void loaders(void) {
  provider p={0}; exr_fixed_page page={0}; exr_fixed_input input={0}; exr_fixed_document *d=NULL; exr_fixed_text *text=NULL; size_t size;
  page.geometry=(exr_page_geometry){{0,0,10,10},1,0,1}; input.struct_size=sizeof(input); input.pages=&page; input.page_count=1; input.draw=draw; input.text=load_text; input.release=release; input.context=&p;
  OK(exr_fixed_create(&input,&d,&error)); p.document=d; CHECK(!p.calls);
  p.fail=1; CHECK(exr_fixed_load_text(d,0,NULL,&text,&error)==EXR_CANCELLED && !text && error.code==EXR_CANCELLED); p.fail=0;
  p.missing=1; CHECK(exr_fixed_load_text(d,0,NULL,&text,&error)==EXR_FORMAT && !text); p.missing=0;
  OK(exr_fixed_load_text(d,0,NULL,&text,&error)); exr_fixed_free(d); CHECK(p.releases==1 && !strcmp(exr_fixed_text_string(text,&size),"AB") && size==2); exr_fixed_text_free(text);
  input.struct_size=offsetof(exr_fixed_input,text); OK(exr_fixed_create(&input,&d,&error)); p.document=d;
  CHECK(exr_fixed_load_text(d,0,NULL,&text,&error)==EXR_FORMAT && !text); exr_fixed_free(d); CHECK(p.releases==2); /* Old required prefix remains compatible. */
  input.struct_size=offsetof(exr_fixed_input,text)+1; ((unsigned char *)&input)[offsetof(exr_fixed_input,text)]=1;
  CHECK(exr_fixed_create(&input,&d,&error)==EXR_ARGUMENT && !d);
}
static void queries(void) {
  const char bytes[]="A\xe4\xb8\xad\0Bfi"; exr_fixed_text *t=NULL; exr_text_region r[6],*selected=NULL; size_t a,b,n,hit;
  exr_control control={0}; int stopped=1; unsigned calls=0;
  r[0]=region(0,1,0); r[1]=region(1,4,2); r[2]=region(1,4,-5); r[2].flags=EXR_REGION_INVISIBLE;
  r[3]=region(5,6,8); r[4]=region(6,8,10); r[5]=region(0,1,20); r[5].quad[2]=r[5].quad[4]=20;
  { const double diamond[8]={10,0,11,1,10,2,9,1}; memcpy(r[4].quad,diamond,sizeof(diamond)); }
  OK(exr_fixed_text_create(bytes,8,r,6,NULL,&t,&error));
  OK(exr_fixed_text_find(t,"Bfi",3,0,NULL,&a,&b,&error)); CHECK(a==5 && b==8);
  OK(exr_fixed_text_find(t,"\0B",2,0,NULL,&a,&b,&error)); CHECK(a==4 && b==6);
  OK(exr_fixed_text_find(t,bytes+1,3,2,NULL,&a,&b,&error)); CHECK(a==SIZE_MAX && b==SIZE_MAX);
  OK(exr_fixed_text_find(t,"i",1,8,NULL,&a,&b,&error)); CHECK(a==SIZE_MAX && b==SIZE_MAX);
  CHECK(exr_fixed_text_find(t,"\xc0",1,0,NULL,&a,&b,&error)==EXR_ENCODING && a==SIZE_MAX && b==SIZE_MAX);
  CHECK(exr_fixed_text_find(t,"x",(size_t)1024*1024+1,0,NULL,&a,&b,&error)==EXR_LIMIT && a==SIZE_MAX);
  CHECK(exr_fixed_text_find(t,"",0,0,NULL,&a,&b,&error)==EXR_ARGUMENT);
  CHECK(exr_fixed_text_find(t,"x",1,9,NULL,&a,&b,&error)==EXR_ARGUMENT);
  OK(exr_fixed_text_select(t,1,4,NULL,&selected,&n,&error)); CHECK(n==2 && selected[0].quad[0]==2 && selected[1].quad[0]==-5); exr_free(selected);
  OK(exr_fixed_text_select(t,6,7,NULL,&selected,&n,&error)); CHECK(n==1 && selected[0].start==6 && selected[0].end==8); exr_free(selected);
  OK(exr_fixed_text_select(t,4,4,NULL,&selected,&n,&error)); CHECK(!selected && !n);
  OK(exr_fixed_text_select(t,4,5,NULL,&selected,&n,&error)); CHECK(!selected && !n);
  CHECK(exr_fixed_text_select(t,2,4,NULL,&selected,&n,&error)==EXR_ARGUMENT && !selected && !n);
  CHECK(exr_fixed_text_select(t,0,9,NULL,&selected,&n,&error)==EXR_ARGUMENT && !selected && !n);
  OK(exr_fixed_text_hit(t,2,1,0,0,NULL,&hit,&error)); CHECK(hit==1);
  OK(exr_fixed_text_hit(t,-4.5,1,0,0,NULL,&hit,&error)); CHECK(hit==2);
  OK(exr_fixed_text_hit(t,-4.5,1,0,EXR_REGION_INVISIBLE,NULL,&hit,&error)); CHECK(hit==SIZE_MAX);
  OK(exr_fixed_text_hit(t,1.5,1,.5,0,NULL,&hit,&error)); CHECK(hit==0);
  OK(exr_fixed_text_hit(t,1.5,1,.49,0,NULL,&hit,&error)); CHECK(hit==SIZE_MAX);
  OK(exr_fixed_text_hit(t,9.1,.1,0,0,NULL,&hit,&error)); CHECK(hit==SIZE_MAX); /* Quad, not bounding box. */
  OK(exr_fixed_text_hit(t,9.5,.5,0,0,NULL,&hit,&error)); CHECK(hit==4);
  OK(exr_fixed_text_hit(t,20,1,0,0,NULL,&hit,&error)); CHECK(hit==5); /* Zero-area line cell. */
  CHECK(exr_fixed_text_hit(t,NAN,0,0,0,NULL,&hit,&error)==EXR_ARGUMENT && hit==SIZE_MAX);
  CHECK(exr_fixed_text_hit(t,0,0,-1,0,NULL,&hit,&error)==EXR_ARGUMENT);
  CHECK(exr_fixed_text_hit(t,0,0,0,4,NULL,&hit,&error)==EXR_ARGUMENT);
  control.cancelled=cancel; control.context=&stopped;
  CHECK(exr_fixed_text_find(t,"A",1,0,&control,&a,&b,&error)==EXR_CANCELLED && a==SIZE_MAX && b==SIZE_MAX);
  CHECK(exr_fixed_text_select(t,0,8,&control,&selected,&n,&error)==EXR_CANCELLED && !selected && !n);
  CHECK(exr_fixed_text_hit(t,0,0,1,0,&control,&hit,&error)==EXR_CANCELLED && hit==SIZE_MAX);
  control.cancelled=later; control.context=&calls;
  CHECK(exr_fixed_text_select(t,0,8,&control,&selected,&n,&error)==EXR_CANCELLED && !selected && !n); /* During copy pass. */
  exr_fixed_text_free(t);
  { size_t length=(size_t)1024*1024; char *large=malloc(length),*query=malloc(65536); CHECK(large && query);
    memset(large,'a',length); large[length-1]='b'; memset(query,'a',65536); query[65535]='b';
    OK(exr_fixed_text_create(large,length,NULL,0,NULL,&t,&error));
    OK(exr_fixed_text_find(t,query,65536,0,NULL,&a,&b,&error)); CHECK(a==length-65536 && b==length);
    query[65535]='c'; OK(exr_fixed_text_find(t,query,65536,0,NULL,&a,&b,&error)); CHECK(a==SIZE_MAX && b==SIZE_MAX);
    calls=0; CHECK(exr_fixed_text_find(t,query,65536,0,&control,&a,&b,&error)==EXR_CANCELLED && a==SIZE_MAX && b==SIZE_MAX);
    free(large); free(query); exr_fixed_text_free(t);
  }
  OK(exr_fixed_text_create(NULL,0,NULL,0,NULL,&t,&error));
  OK(exr_fixed_text_find(t,"x",1,0,NULL,&a,&b,&error)); CHECK(a==SIZE_MAX && b==SIZE_MAX);
  OK(exr_fixed_text_hit(t,0,0,0,0,NULL,&hit,&error)); CHECK(hit==SIZE_MAX); exr_fixed_text_free(t);
}
static exr_fixed_text *snapshot(const char *bytes,size_t size) {
  exr_fixed_text *t=NULL; OK(exr_fixed_text_create(bytes,size,NULL,0,NULL,&t,&error)); return t;
}
static void fixed_anchors(void) {
  const char source[]="prefix\0target\0suffix",moved[]="new prefix\0target\0suffix more";
  exr_fixed_text *t=snapshot(source,sizeof(source)-1),*next=snapshot(moved,sizeof(moved)-1);
  exr_fixed_anchor a={0},point={0},bad; exr_anchor_match match; exr_control control={0}; int stopped=1;
  OK(exr_fixed_anchor_create("page-1",t,6,14,&a,&error)); CHECK(a.exact_size==8 && a.exact[0]==0 && a.exact[7]==0 && a.prefix_size==6 && a.suffix_size==6);
  OK(exr_fixed_anchor_create("page-1",t,7,7,&point,&error)); CHECK(!point.exact_size && point.exact);
  exr_fixed_text_free(t); /* All selector bytes are owned. */
  OK(exr_fixed_anchor_resolve("page-1",next,&a,NULL,&match,&error)); CHECK(match.state==EXR_ANCHOR_FOUND && match.start==10 && match.end==18);
  OK(exr_fixed_anchor_resolve("page-1",next,&point,NULL,&match,&error)); CHECK(match.state==EXR_ANCHOR_FOUND && match.start==11 && match.end==11);
  OK(exr_fixed_anchor_resolve("page-2",next,&a,NULL,&match,&error)); CHECK(match.state==EXR_ANCHOR_MISSING && match.start==SIZE_MAX && match.end==SIZE_MAX);
  bad=a; bad.exact_size--; CHECK(exr_fixed_anchor_resolve("page-1",next,&bad,NULL,&match,&error)==EXR_ARGUMENT && match.start==SIZE_MAX);
  bad=a; bad.prefix_size=129; CHECK(exr_fixed_anchor_resolve("page-1",next,&bad,NULL,&match,&error)==EXR_LIMIT);
  bad=a; bad.prefix=NULL; CHECK(exr_fixed_anchor_resolve("page-1",next,&bad,NULL,&match,&error)==EXR_ARGUMENT);
  bad=a; bad.prefix="\xc0"; bad.prefix_size=1; CHECK(exr_fixed_anchor_resolve("page-1",next,&bad,NULL,&match,&error)==EXR_ENCODING);
  bad=a; bad.prefix="012345678901234567890123456789012"; bad.prefix_size=33; CHECK(exr_fixed_anchor_resolve("page-1",next,&bad,NULL,&match,&error)==EXR_LIMIT);
  control.cancelled=cancel; control.context=&stopped;
  CHECK(exr_fixed_anchor_resolve("page-1",next,&a,&control,&match,&error)==EXR_CANCELLED && match.start==SIZE_MAX);
  exr_fixed_anchor_free(&a); exr_fixed_anchor_free(&point); exr_fixed_text_free(next);
  { char original[81],twice[163]; unsigned calls=0;
    memset(original,'a',40); original[40]='q'; memset(original+41,'b',40);
    memcpy(twice,original,81); twice[81]='#'; memcpy(twice+82,original,81);
    t=snapshot(original,81); next=snapshot(twice,163); OK(exr_fixed_anchor_create("p",t,40,41,&a,&error));
    OK(exr_fixed_anchor_resolve("p",next,&a,NULL,&match,&error)); CHECK(match.state==EXR_ANCHOR_AMBIGUOUS && match.start==SIZE_MAX && match.end==SIZE_MAX);
    control.cancelled=later; control.context=&calls;
    /* Initial poll, then stream poll; cancellation can also be triggered on longer scans. */
    OK(exr_fixed_anchor_resolve("p",next,&a,&control,&match,&error)); CHECK(match.state==EXR_ANCHOR_AMBIGUOUS);
    exr_fixed_text_free(t); exr_fixed_text_free(next); exr_fixed_anchor_free(&a);
  }
  { char utf8[321]; size_t i;
    for(i=0;i<40;i++) { memcpy(utf8+4*i,"\xf0\x9f\x98\x80",4); memcpy(utf8+161+4*i,"\xf0\x9f\x98\x80",4); } utf8[160]='x';
    t=snapshot(utf8,sizeof(utf8)); OK(exr_fixed_anchor_create("p",t,160,161,&a,&error)); CHECK(a.prefix_size==128 && a.suffix_size==128);
    OK(exr_fixed_anchor_resolve("p",t,&a,NULL,&match,&error)); CHECK(match.state==EXR_ANCHOR_FOUND && match.start==160);
    CHECK(exr_fixed_anchor_create("p",t,1,4,&point,&error)==EXR_ARGUMENT && !point.exact);
    exr_fixed_anchor_free(&a); exr_fixed_text_free(t);
  }
  { char *large=malloc(65537); unsigned calls=0; CHECK(large); memset(large,'a',65537); t=snapshot(large,65537);
    CHECK(exr_fixed_anchor_create("p",t,0,65537,&point,&error)==EXR_LIMIT && !point.exact);
    OK(exr_fixed_anchor_create("p",t,0,65536,&a,&error)); control.cancelled=later; control.context=&calls;
    CHECK(exr_fixed_anchor_resolve("p",t,&a,&control,&match,&error)==EXR_CANCELLED && match.start==SIZE_MAX);
    exr_fixed_anchor_free(&a); exr_fixed_text_free(t); free(large);
  }
  t=snapshot(NULL,0); OK(exr_fixed_anchor_create("p",t,0,0,&a,&error));
  OK(exr_fixed_anchor_resolve("p",t,&a,NULL,&match,&error)); CHECK(match.state==EXR_ANCHOR_FOUND && !match.start && !match.end);
  CHECK(exr_fixed_anchor_create("",t,0,0,&point,&error)==EXR_ARGUMENT && !point.page_id);
  exr_fixed_anchor_free(&a); exr_fixed_text_free(t); exr_fixed_anchor_free(NULL);
}
int main(void) { snapshots(); loaders(); queries(); fixed_anchors(); printf("%u generic fixed text checks passed\n",checks); return 0; }
