/* SPDX-License-Identifier: GPL-3.0-only */
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
int main(void) { snapshots(); loaders(); printf("%u generic fixed text checks passed\n",checks); return 0; }
