/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
typedef struct { exr_fixed_document *document; size_t calls,releases,reentries; int fail,reenter; } provider;
static exr_status draw(void *context,size_t page,const double matrix[6],const exr_draw_sink *sink,const exr_control *control,exr_error *e) {
  provider *p=context; exr_path_segment rect[5]={0}; exr_draw_style style=exr_draw_style_defaults(); exr_status status=EXR_OK;
  double x=page ? 0 : -2,y=page ? 0 : -1,w=page ? 3 : 4,h=2; (void)control; p->calls++;
  if(p->reenter) { exr_error nested={0}; CHECK(exr_fixed_draw(p->document,page,matrix,sink,NULL,&nested)==EXR_ARGUMENT); p->reentries++; }
  rect[0].verb=EXR_PATH_MOVE; rect[0].points[0]=(exr_path_point){x,y}; rect[1].verb=EXR_PATH_LINE; rect[1].points[0]=(exr_path_point){x+w,y};
  rect[2].verb=EXR_PATH_LINE; rect[2].points[0]=(exr_path_point){x+w,y+h}; rect[3].verb=EXR_PATH_LINE; rect[3].points[0]=(exr_path_point){x,y+h}; rect[4].verb=EXR_PATH_CLOSE;
  style.fill=page ? 0x0000ffff : 0xff0000ff;
  if(sink->path) status=sink->path(sink->context,rect,5,matrix,&style,e);
  return p->fail ? EXR_CANCELLED : status;
}
static void release(void *context) { ((provider *)context)->releases++; }
static exr_status inspect(void *context,const exr_path_segment *segments,size_t count,const double matrix[6],const exr_draw_style *style,exr_error *e) {
  size_t *calls=context; (void)e; CHECK(count==5 && segments[0].points[0].x==-2 && matrix[4]==10 && matrix[5]==20 && style->fill==0xff0000ff); (*calls)++; return EXR_OK;
}
static int cancel(void *context) { return *(int *)context; }
static exr_fixed_input input_for(provider *p,exr_fixed_page pages[2]) {
  exr_fixed_input input={0}; memset(pages,0,2*sizeof(*pages));
  pages[0].id="first"; pages[0].label="i"; pages[0].geometry=(exr_page_geometry){{-2,-1,2,1},2,0,0};
  pages[1].id="second"; pages[1].label="1"; pages[1].geometry=(exr_page_geometry){{0,0,3,2},1,90,1};
  input.struct_size=sizeof(input); input.title="A fixed document"; input.pages=pages; input.page_count=2; input.draw=draw; input.context=p; input.release=release; return input;
}
static void metadata_and_render(void) {
  provider p={0}; exr_fixed_page pages[2]; exr_fixed_input input=input_for(&p,pages); exr_fixed_document *d=NULL; const exr_fixed_page *snapshot; size_t count,calls=0;
  char title[32]="Original title",id[32]="persistent-id"; exr_bitmap image; exr_draw_sink sink={0}; double matrix[6]={1,0,0,1,10,20}; exr_fixed_render_options options={0}; int stopped=0;
  input.title=title; pages[0].id=id; OK(exr_fixed_create(&input,&d,&error)); p.document=d;
  memset(title,'X',sizeof(title)); memset(id,'X',sizeof(id)); memset(pages,0,sizeof(pages));
  snapshot=exr_fixed_pages(d,&count); CHECK(count==2 && !strcmp(exr_fixed_title(d),"Original title") && !strcmp(snapshot[0].id,"persistent-id") && !strcmp(snapshot[1].label,"1"));
  CHECK(!p.calls && exr_fixed_memory_size(d)>2*sizeof(exr_fixed_page));
  OK(exr_fixed_render(d,0,1,NULL,&image,&error)); CHECK(image.width==8 && image.height==4 && image.channels==4 && image.pixels[0]==255 && image.pixels[1]==0); exr_bitmap_free(&image);
  p.reenter=1; OK(exr_fixed_render(d,1,1,NULL,&image,&error)); CHECK(p.reentries==1 && image.width==2 && image.height==3 && image.pixels[0]==0 && image.pixels[2]==255); exr_bitmap_free(&image); p.reenter=0;
  sink.path=inspect; sink.context=&calls; OK(exr_fixed_draw(d,0,matrix,&sink,NULL,&error)); CHECK(calls==1 && p.calls==3);
  matrix[0]=NAN; CHECK(exr_fixed_draw(d,0,matrix,&sink,NULL,&error)==EXR_ARGUMENT && p.calls==3); matrix[0]=1;
  p.fail=1; CHECK(exr_fixed_render(d,0,1,NULL,&image,&error)==EXR_CANCELLED && !image.pixels && !image.width && error.code==EXR_CANCELLED && error.message[0]); p.fail=0;
  OK(exr_fixed_render(d,0,1,NULL,&image,&error)); exr_bitmap_free(&image);
  stopped=1; options.control.cancelled=cancel; options.control.context=&stopped;
  count=p.calls; CHECK(exr_fixed_render(d,0,1,&options,&image,&error)==EXR_CANCELLED && !image.pixels && p.calls==count);
  stopped=0; options.channels=2; CHECK(exr_fixed_render(d,0,1,&options,&image,&error)==EXR_ARGUMENT && !image.pixels && p.calls==count);
  CHECK(exr_fixed_render(d,0,100000,NULL,&image,&error)==EXR_LIMIT && !image.pixels && p.calls==count);
  CHECK(exr_fixed_render(d,2,1,NULL,&image,&error)==EXR_ARGUMENT && !image.pixels);
  exr_fixed_free(d); CHECK(p.releases==1);
}
static void construction_failures(void) {
  provider p={0}; exr_fixed_page pages[2]; exr_fixed_input input=input_for(&p,pages); exr_fixed_document *d=NULL; size_t count;
  pages[1].id=pages[0].id; CHECK(exr_fixed_create(&input,&d,&error)==EXR_ARGUMENT && !d && !p.releases);
  input=input_for(&p,pages); input.title="\xff"; CHECK(exr_fixed_create(&input,&d,&error)==EXR_ENCODING && !d && !p.releases);
  input=input_for(&p,pages); pages[0].geometry.unit_scale=0; CHECK(exr_fixed_create(&input,&d,&error)==EXR_ARGUMENT && !d);
  input=input_for(&p,pages); input.page_count=10001; CHECK(exr_fixed_create(&input,&d,&error)==EXR_LIMIT && !d);
  input=input_for(&p,pages); input.struct_size=offsetof(exr_fixed_input,release)+sizeof(input.release)-1; CHECK(exr_fixed_create(&input,&d,&error)==EXR_ARGUMENT && !d);
  input=input_for(&p,pages);
  { struct { exr_fixed_input input; unsigned char extension[8]; } extended={0}; extended.input=input; extended.input.struct_size=sizeof(extended); extended.extension[0]=1;
    CHECK(exr_fixed_create(&extended.input,&d,&error)==EXR_ARGUMENT && !d && !p.releases); extended.extension[0]=0;
    OK(exr_fixed_create(&extended.input,&d,&error)); exr_fixed_free(d); CHECK(p.releases==1);
  }
  input=input_for(&p,pages); pages[0].id=pages[1].id=NULL; OK(exr_fixed_create(&input,&d,&error));
  CHECK(!strcmp(exr_fixed_pages(d,&count)[0].id,"page-1") && !strcmp(exr_fixed_pages(d,&count)[1].id,"page-2")); exr_fixed_free(d); CHECK(p.releases==2);
  input=input_for(&p,pages); pages[0].geometry=(exr_page_geometry){{0,0,1000,1000},75000,0,0}; OK(exr_fixed_create(&input,&d,&error)); exr_fixed_free(d);
  input=input_for(&p,pages); pages[0].geometry.unit_scale=1e-10; OK(exr_fixed_create(&input,&d,&error)); exr_fixed_free(d);
  { char *large=malloc(65538); CHECK(large); memset(large,'x',65537); large[65537]=0; input=input_for(&p,pages); input.title=large;
    CHECK(exr_fixed_create(&input,&d,&error)==EXR_LIMIT && !d); free(large);
  }
  CHECK(!exr_fixed_pages(NULL,&count) && !count && !exr_fixed_memory_size(NULL) && !strcmp(exr_fixed_title(NULL),"")); exr_fixed_free(NULL);
}
int main(void) { metadata_and_render(); construction_failures(); printf("%u native generic fixed document checks passed\n",checks); return 0; }
