/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static char pdf[300000]; static size_t size,offset[12];
static void add(const char *s) { size_t n=strlen(s); CHECK(n<sizeof(pdf)-size); memcpy(pdf+size,s,n); size+=n; pdf[size]=0; }
static void object(unsigned id,const char *body) { char head[40]; offset[id]=size; snprintf(head,sizeof(head),"%u 0 obj\n",id); add(head); add(body); add("\nendobj\n"); }
static void stream(unsigned id,const char *dictionary,const char *content) {
  char head[1024]; snprintf(head,sizeof(head),"<< %s /Length %zu >>\nstream\n",dictionary,strlen(content));
  offset[id]=size; { char begin[40]; snprintf(begin,sizeof(begin),"%u 0 obj\n",id); add(begin); } add(head); add(content); add("\nendstream\nendobj\n");
}
#define FORM "/Type /XObject /Subtype /Form /BBox [0 0 10 10]"
#define RED "1 0 0 rg -20 -20 50 50 re f"
#define FIRST "<< /Subtype /Square /Rect [10 10 20 20] /AP << /N 7 0 R >> >>"
#define SECOND "<< /Subtype /Square /Rect [25 25 35 35] /AP << /N 9 0 R >> >>"
static void build(const char *annots,const char *first,const char *second,const char *page_content,const char *form,const char *appearance) {
  char row[160]; size_t xref; unsigned i; size=0; add("%PDF-1.7\n");
  object(1,"<< /Type /Catalog /Pages 2 0 R >>"); object(2,"<< /Type /Pages /Count 2 /Kids [3 0 R 4 0 R] >>");
  snprintf(row,sizeof(row),"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 40 40] /Contents 5 0 R /Annots %s /Resources << /XObject << /Nested 11 0 R >> >> >>",annots); object(3,row);
  object(4,"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 40 40] /Contents 10 0 R >>");
  stream(5,"",page_content); object(6,first); stream(7,form,appearance); object(8,second);
  stream(9,FORM,"0 1 0 rg 0 0 10 10 re f"); stream(10,"","0 0 1 rg 0 0 40 40 re f"); stream(11,FORM,"0 0 1 rg 0 0 10 10 re f");
  xref=size; add("xref\n0 12\n0000000000 65535 f \n"); for(i=1;i<12;i++) { snprintf(row,sizeof(row),"%010zu 00000 n \n",offset[i]); add(row); }
  snprintf(row,sizeof(row),"trailer\n<< /Size 12 /Root 1 0 R >>\nstartxref\n%zu\n%%%%EOF\n",xref); add(row);
}
static unsigned color(const exr_bitmap *b,unsigned x,unsigned y) {
  const unsigned char *p=b->pixels+(b->height-1-y)*b->stride+x*4; return ((unsigned)p[0]<<16)|((unsigned)p[1]<<8)|p[2];
}
static exr_fixed_document *open_pdf(void) { exr_fixed_document *d=NULL; OK(exr_fixed_open_memory(EXR_PDF,pdf,size,NULL,&d,&error)); return d; }
static void render(exr_fixed_document *d,exr_bitmap *b) { OK(exr_fixed_render(d,0,1,NULL,b,&error)); CHECK(b->width==40 && b->height==40 && b->channels==4); }
static void geometry_and_isolation(void) {
  exr_fixed_document *d; exr_bitmap b;
  build("[6 0 R 8 0 R null 99 0 R]",FIRST,SECOND,"0 0 2 2 re W n",FORM,RED); d=open_pdf(); render(d,&b);
  CHECK(color(&b,15,15)==0xff0000 && color(&b,30,30)==0x00ff00 && color(&b,5,5)==0xffffff && color(&b,21,15)==0xffffff); exr_bitmap_free(&b); exr_fixed_free(d);
  build("[6 0 R 8 0 R]",FIRST,SECOND,"",FORM,"q 0 0 1 1 re W n 1 0 0 rg 0 0 10 10 re f Q"); d=open_pdf(); render(d,&b);
  CHECK(color(&b,10,10)==0xff0000 && color(&b,15,15)==0xffffff && color(&b,30,30)==0x00ff00); exr_bitmap_free(&b); exr_fixed_free(d);
  build("[6 0 R]","<< /Rect [30 28 10 8] /AP << /N 7 0 R >> >>","null","","/Subtype /Form /BBox [2 3 12 13] /Matrix [0 2 -1 0 30 -10]","1 0 0 rg 2 3 5 10 re f"); d=open_pdf(); render(d,&b);
  CHECK(color(&b,20,13)==0xff0000 && color(&b,20,23)==0xffffff && color(&b,31,13)==0xffffff); exr_bitmap_free(&b); exr_fixed_free(d);
  build("[6 0 R]","<< /Rect [10 10 30 30] /AP << /N 7 0 R >> >>","null","","/BBox [0 0 10 10] /Matrix [1 0 1 1 0 0]",RED); d=open_pdf(); render(d,&b);
  CHECK(color(&b,20,20)==0xff0000 && color(&b,12,28)==0xffffff && color(&b,28,12)==0xffffff); exr_bitmap_free(&b); exr_fixed_free(d);
  build("[6 0 R]",FIRST,"null","",FORM,"/Nested Do"); d=open_pdf(); render(d,&b); CHECK(color(&b,15,15)==0x0000ff); exr_bitmap_free(&b); exr_fixed_free(d);
  build("[6 0 R]",FIRST,"null","","/BBox [0 0 10 10] /Resources << /XObject << /Own 11 0 R >> >>","/Own Do"); d=open_pdf(); render(d,&b); CHECK(color(&b,15,15)==0x0000ff); exr_bitmap_free(&b); exr_fixed_free(d);
}
static void states_and_flags(void) {
  const char *notes[]={
    "<< /Rect [10 10 20 20] /AP << /N << /Off 9 0 R /On 7 0 R >> >> /AS /On >>",
    "<< /Rect [10 10 20 20] /AP << /N << /Off 9 0 R /On 7 0 R >> >> /AS /Off >>",
    "<< /Rect [10 10 20 20] /AP << /N << /Off 9 0 R /On 7 0 R >> >> >>",
    "<< /Rect [10 10 20 20] /AP << /N << /Off 9 0 R >> >> /AS /Missing >>",
    "<< /F 1 /Rect /invalid /AP /invalid >>","<< /F 2 /Rect /invalid /AP /invalid >>","<< /F 32 /Rect /invalid /AP /invalid >>",
    "<< /Rect /invalid /Contents 42 >>","<< /Rect [10 10 20 20] /AP << /N null >> >>",
    "<< /Rect [10 10 20 20] /AP << /N << /A#00B 7 0 R >> >> /AS /A#00B >>"};
  size_t i; for(i=0;i<sizeof(notes)/sizeof(*notes);i++) {
    exr_fixed_document *d; exr_bitmap b; unsigned expected=i==0 || i==9 ? 0xff0000 : i==1 ? 0x00ff00 : 0xffffff;
    build("[6 0 R]",notes[i],"null","",FORM,RED); d=open_pdf(); render(d,&b); CHECK(color(&b,15,15)==expected); exr_bitmap_free(&b); exr_fixed_free(d);
  }
}
typedef struct { unsigned depth,text,paths,saves,restores; double first[2]; } observer;
static exr_status state(void *context,exr_draw_state event,exr_error *e) {
  observer *o=context; (void)e;
  if(event==EXR_DRAW_SAVE) { o->depth++; o->saves++; }
  else if(event==EXR_DRAW_RESTORE) { CHECK(o->depth); o->depth--; o->restores++; }
  else if(event==EXR_DRAW_BEGIN_CLIP) { CHECK(!o->text); o->text=1; }
  else { CHECK(o->text); o->text=0; }
  return EXR_OK;
}
static exr_status path(void *context,const exr_path_segment *segments,size_t n,const double matrix[6],const exr_draw_style *style,exr_error *e) {
  observer *o=context; (void)matrix;(void)style;(void)e; CHECK(n);
  if(!o->paths) { o->first[0]=segments[0].points[0].x; o->first[1]=segments[0].points[0].y; }
  o->paths++; return EXR_OK;
}
static int cancelled(void *context) { return *(int *)context; }
static void stop(void *context,exr_stage stage,uint64_t done,uint64_t total) { if(stage==EXR_STAGE_RENDER && done && !total) *(int *)context=1; }
static exr_status state_detail(void *context,exr_draw_state event,exr_error *e) {
  if(event==*(exr_draw_state *)context) { e->code=EXR_IO; strcpy(e->message,"consumer state failure"); }
  return EXR_OK;
}
static exr_status clip_detail(void *context,const exr_path_segment *segments,size_t n,const double matrix[6],exr_fill_rule rule,unsigned accumulate,exr_error *e) {
  (void)context;(void)segments;(void)n;(void)matrix;(void)rule;(void)accumulate;
  e->code=EXR_IO; strcpy(e->message,"consumer clip failure"); return EXR_OK;
}
static void failures(void) {
  const char *forms[]={"/BBox [0 0 0 10]","/BBox [0 0 10]","/BBox [0 0 10 10] /Matrix [1 0 0 1 0]","/BBox [0 0 10 10] /Resources 42","/BBox [0 0 10 10] /Group << /S /Transparency >>","/Subtype /Image /BBox [0 0 10 10]","/BBox [0 0 10 10] /FormType 2"};
  size_t i; exr_fixed_document *d; exr_bitmap b;
  for(i=0;i<sizeof(forms)/sizeof(*forms);i++) {
    build("[6 0 R]",FIRST,"null","",forms[i],RED); d=open_pdf(); CHECK(exr_fixed_render(d,0,1,NULL,&b,&error)==EXR_FORMAT && !b.pixels && !b.width);
    OK(exr_fixed_render(d,1,1,NULL,&b,&error)); CHECK(color(&b,15,15)==0x0000ff); exr_bitmap_free(&b);
    CHECK(exr_fixed_render(d,0,1,NULL,&b,&error)==EXR_FORMAT && !b.pixels); exr_fixed_free(d);
  }
  build("[6 0 R]",FIRST,"null","",FORM,"q BT"); d=open_pdf();
  { observer o={0}; exr_draw_sink sink={0}; sink.state=state; sink.path=path; sink.context=&o;
    CHECK(exr_fixed_draw(d,0,NULL,&sink,NULL,&error)==EXR_FORMAT && !o.depth && !o.text && o.saves==o.restores);
  }
  CHECK(exr_fixed_render(d,0,1,NULL,&b,&error)==EXR_FORMAT && !b.pixels); OK(exr_fixed_render(d,1,1,NULL,&b,&error)); exr_bitmap_free(&b); exr_fixed_free(d);
  build("[6 0 R]",FIRST,"null","",FORM,RED); d=open_pdf();
  { int stopped=0; exr_fixed_render_options options={0}; options.channels=4; options.background=0xffffffff; options.control=(exr_control){cancelled,stop,&stopped};
    CHECK(exr_fixed_render(d,0,1,&options,&b,&error)==EXR_CANCELLED && !b.pixels); render(d,&b); CHECK(color(&b,15,15)==0xff0000); exr_bitmap_free(&b);
  }
  exr_fixed_free(d);
  build("[6 0 R]",FIRST,"null","",FORM,RED); d=open_pdf();
  { exr_draw_sink sink={0}; exr_draw_state failure=EXR_DRAW_SAVE; sink.state=state_detail; sink.context=&failure;
    CHECK(exr_fixed_draw(d,0,NULL,&sink,NULL,&error)==EXR_IO && !strcmp(error.message,"consumer state failure"));
    failure=EXR_DRAW_RESTORE; CHECK(exr_fixed_draw(d,0,NULL,&sink,NULL,&error)==EXR_IO && !strcmp(error.message,"consumer state failure"));
    sink.state=NULL; sink.clip=clip_detail; CHECK(exr_fixed_draw(d,0,NULL,&sink,NULL,&error)==EXR_IO && !strcmp(error.message,"consumer clip failure"));
  }
  exr_fixed_free(d);
  build("[6 0 R]",FIRST,"null","",FORM,"1 0 0 rg 0 0 10 10 re f"); d=open_pdf();
  { observer o={0}; exr_draw_sink sink={0}; const double matrix[6]={2,0,0,-3,5,100}; sink.state=state; sink.path=path; sink.context=&o;
    OK(exr_fixed_draw(d,0,matrix,&sink,NULL,&error)); CHECK(o.paths==1 && !o.depth && !o.text && o.first[0]==25 && o.first[1]==70);
  }
  exr_fixed_free(d);
  { char many[26000]; size_t at=0; many[at++]='['; for(i=0;i<4097;i++) { memcpy(many+at,"6 0 R ",6); at+=6; } strcpy(many+at,"]");
    build("null",FIRST,"null","",FORM,RED);
    /* The large array is an indirect object, keeping the page dictionary small. */
    size=0; add("%PDF-1.7\n"); object(1,"<< /Type /Catalog /Pages 2 0 R >>"); object(2,"<< /Type /Pages /Count 1 /Kids [3 0 R] >>"); object(3,"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 40 40] /Annots 4 0 R >>"); object(4,many);
    object(5,"null"); object(6,"<< >>"); stream(7,FORM,RED); object(8,"null"); object(9,"null"); object(10,"null"); object(11,"null");
    { char row[160]; size_t xref=size; add("xref\n0 12\n0000000000 65535 f \n"); for(i=1;i<12;i++) { snprintf(row,sizeof(row),"%010zu 00000 n \n",offset[i]); add(row); } snprintf(row,sizeof(row),"trailer\n<< /Size 12 /Root 1 0 R >>\nstartxref\n%zu\n%%%%EOF\n",xref); add(row); }
    d=open_pdf(); CHECK(exr_fixed_render(d,0,1,NULL,&b,&error)==EXR_LIMIT && !b.pixels); exr_fixed_free(d);
  }
}
int main(void) { geometry_and_isolation(); states_and_flags(); failures(); printf("%u PDF appearance checks passed\n",checks); return 0; }
