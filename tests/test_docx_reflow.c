/* SPDX-License-Identifier: MIT */
#include "exr/reflow.h"
#include "exr/render.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifdef _WIN32
#include <windows.h>
#endif
static exr_error error;
static exr_font *font;
#define CHECK(x) do { if(!(x)) { fprintf(stderr,"line %d: %s (%d %s)\n",__LINE__,#x,error.code,error.message);exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static exr_layout_config config(void) {
  exr_layout_config c=exr_layout_config_defaults();
  c.page=(exr_layout_options){400,232,16,16,1.25f,0};return c;
}
/* Stable seed identities also let a decoder publish a revised snapshot before
   X1 exposes a text-replacement command. Never write to X1 borrowed views. */
static exr_edit_doc *model(size_t count,int change_last) {
  exr_edit_doc *doc=NULL;exr_edit_block *blocks=calloc(count,sizeof(*blocks));
  exr_edit_run *runs=calloc(count,sizeof(*runs));char (*text)[64]=calloc(count,64);size_t i;
  CHECK(blocks && runs && text);
  for(i=0;i<count;i++) {
    snprintf(text[i],64,"Block %06zu sample text%c",i,change_last && i==count-1 ? '!' : '.');
    runs[i].id=100000+i;runs[i].text=text[i];runs[i].text_size=strlen(text[i]);
    blocks[i].id=1000+i;blocks[i].runs=&runs[i];blocks[i].run_count=1;
  }
  OK(exr_edit_doc_create(NULL,0,blocks,count,NULL,0,NULL,&doc));
  free(blocks);free(runs);free(text);return doc;
}
static exr_pager *pager(exr_edit_doc *doc) {
  exr_pager *p=NULL;exr_layout_config c=config();OK(exr_edit_pager_create(doc,font,&c,&p,&error));
  OK(exr_pager_set_cache(p,64,8*1024*1024,&error));return p;
}
static void compare(exr_pager *a,exr_edit_doc *doc) {
  exr_pager *b=pager(doc);size_t i,j,n=exr_edit_reflow_statistics(a).page_count;
  CHECK(n==exr_edit_reflow_statistics(b).page_count);
  for(i=0;i<n;i++) {
    const exr_layout *x,*y;size_t nx,ny;const exr_glyph *gx,*gy;const exr_line *lx,*ly;
    OK(exr_pager_get(a,i,&x,&error));OK(exr_pager_get(b,i,&y,&error));
    gx=exr_layout_glyphs(x,&nx);gy=exr_layout_glyphs(y,&ny);CHECK(nx==ny);
    for(j=0;j<nx;j++) CHECK(gx[j].start==gy[j].start && gx[j].end==gy[j].end && gx[j].node==gy[j].node &&
      gx[j].x==gy[j].x && gx[j].baseline==gy[j].baseline && gx[j].glyph==gy[j].glyph && gx[j].flags==gy[j].flags);
    lx=exr_layout_lines(x,&nx);ly=exr_layout_lines(y,&ny);CHECK(nx==ny);
    for(j=0;j<nx;j++) CHECK(lx[j].start==ly[j].start && lx[j].end==ly[j].end && lx[j].y==ly[j].y);
    if(i==0 || i==n/2 || i==n-1) {
      exr_bitmap bx={0},by={0};OK(exr_render_page_color(x,font,0,&bx,&error));OK(exr_render_page_color(y,font,0,&by,&error));
      CHECK(bx.stride==by.stride && bx.height==by.height && !memcmp(bx.pixels,by.pixels,(size_t)bx.stride*bx.height));
      exr_bitmap_free(&bx);exr_bitmap_free(&by);
    }
  }
  exr_pager_free(b);
}
static exr_edit_id insert(exr_edit_doc *doc,exr_edit_id after,const char *text) {
  exr_edit_run run={0};exr_edit_id id;run.text=text;run.text_size=strlen(text);
  OK(exr_edit_insert_paragraph(doc,after,&run,1,NULL,&id));return id;
}
static void basic(void) {
  exr_edit_doc *doc=model(1000,0),*revised;exr_pager *p=pager(doc);size_t n;const exr_layout *page,*cached;
  exr_edit_reflow_stats s;exr_edit_view_anchor before,after;
  CHECK(exr_edit_reflow_statistics(p).page_count==100);
  OK(exr_pager_get(p,0,&cached,&error));OK(exr_pager_get(p,99,&page,&error));
  OK(exr_edit_anchor_capture(p,50,1500,6,&before,&error));
  revised=model(1000,1);OK(exr_edit_layout_after(revised,p,1999,&n,&error));
  CHECK(n==1);s=exr_edit_reflow_statistics(p);CHECK(s.dirty.first_page==99 && s.cache_invalidated==1);
  OK(exr_pager_get(p,0,&page,&error));CHECK(page==cached);
  CHECK(exr_pager_cache_statistics(p).hits==1);
  OK(exr_edit_anchor_restore(p,&before,&after,&error));CHECK(after.page_index==50 && after.byte_offset==6);
  compare(p,revised);
  OK(exr_edit_layout_after(revised,p,0,&n,&error));CHECK(n==0);
  exr_pager_free(p);exr_edit_doc_free(revised);exr_edit_doc_free(doc);
}
static void insertions(void) {
  int k;for(k=0;k<3;k++) {
    exr_edit_doc *doc=model(1000,0);exr_pager *p=pager(doc);size_t n,i;exr_edit_view_anchor a,b;
    OK(exr_edit_anchor_capture(p,50,1500,6,&a,&error));
    if(k<2) insert(doc,k ? 1499 : 0,"An inserted paragraph.");
    else { exr_edit_tx *tx=exr_edit_begin(doc);exr_edit_id id=1999;CHECK(tx);
      for(i=0;i<50;i++) id=insert(doc,id,"AI appended paragraph.");OK(exr_edit_commit(tx)); }
    OK(exr_edit_layout_after(doc,p,0,&n,&error));
    CHECK(k==0 ? n==101 : k==1 ? n==51 : n==5);
    CHECK(exr_edit_reflow_statistics(p).page_count==(k==2 ? 105 : 101));
    OK(exr_edit_anchor_restore(p,&a,&b,&error));CHECK(b.block_id==a.block_id && b.byte_offset==a.byte_offset);
    compare(p,doc);exr_pager_free(p);exr_edit_doc_free(doc);
  }
}
static void convergence(void) {
  exr_edit_doc *doc=model(100,0);exr_pager *p=pager(doc);size_t n;exr_edit_para_props props={0};
  const exr_layout *old,*now;exr_edit_view_anchor a,b;
  props.present=EXR_EDIT_PAGE_BEFORE;props.page_break_before=1;
  OK(exr_edit_set_paragraph_props(doc,1050,&props));OK(exr_edit_layout_after(doc,p,1050,&n,&error));
  OK(exr_pager_get(p,8,&old,&error));OK(exr_edit_anchor_capture(p,8,1080,8,&a,&error));
  insert(doc,1004,"A new paragraph.");OK(exr_edit_layout_after(doc,p,0,&n,&error));
  CHECK(n==6);CHECK(exr_edit_reflow_statistics(p).pages_reused==5);
  OK(exr_pager_get(p,9,&now,&error));CHECK(old==now);
  OK(exr_edit_anchor_restore(p,&a,&b,&error));CHECK(b.page_index==9 && b.byte_offset==8);
  printf("anchor: page %zu offset %zu -> page %zu offset %zu, block %llu byte %zu\n",a.page_index,a.page_offset,b.page_index,b.page_offset,(unsigned long long)b.block_id,b.byte_offset);
  compare(p,doc);exr_pager_free(p);exr_edit_doc_free(doc);
}
static void history(void) {
  exr_edit_doc *doc=model(100,0);exr_pager *p=pager(doc);size_t n;exr_edit_id id=insert(doc,1040,"Undo text.");
  OK(exr_edit_layout_after(doc,p,id,&n,&error));compare(p,doc);
  OK(exr_edit_undo(doc));OK(exr_edit_layout_after(doc,p,id,&n,&error));compare(p,doc);
  OK(exr_edit_redo(doc));OK(exr_edit_layout_after(doc,p,id,&n,&error));compare(p,doc);
  OK(exr_edit_delete_block(doc,id));OK(exr_edit_layout_after(doc,p,id,&n,&error));compare(p,doc);
  { exr_edit_tx *t=exr_edit_begin(doc);CHECK(t);insert(doc,0,"Rolled back.");OK(exr_edit_rollback(t)); }
  OK(exr_edit_layout_after(doc,p,0,&n,&error));CHECK(n==0);
  exr_pager_free(p);exr_edit_doc_free(doc);
}
static void anchors(void) {
  exr_edit_doc *doc=model(100,0);exr_pager *p=pager(doc);exr_edit_view_anchor a,b;size_t n;
  OK(exr_edit_anchor_capture(p,5,1050,12,&a,&error));
  OK(exr_edit_split_paragraph(doc,1050,0,6));OK(exr_edit_layout_after(doc,p,1050,&n,&error));
  OK(exr_edit_anchor_restore(p,&a,&b,&error));CHECK(b.block_id!=a.block_id && b.byte_offset==6);
  printf("anchor split: page %zu offset %zu -> page %zu offset %zu, byte %zu -> %zu\n",a.page_index,a.page_offset,b.page_index,b.page_offset,a.byte_offset,b.byte_offset);
  a=b;OK(exr_edit_delete_block(doc,b.block_id));OK(exr_edit_layout_after(doc,p,b.block_id,&n,&error));
  OK(exr_edit_anchor_restore(p,&a,&b,&error));CHECK(b.block_id==1051 && b.byte_offset==0);
  compare(p,doc);exr_pager_free(p);exr_edit_doc_free(doc);
}
static int cancel(void *context) { return *(int *)context; }
static void failures(void) {
  exr_edit_doc *doc=model(100,0);exr_pager *p=pager(doc);size_t n,revision=exr_edit_reflow_statistics(p).revision;
  int stop=1;exr_control control={cancel,NULL,&stop};const exr_layout *old,*now;
  OK(exr_pager_get(p,0,&old,&error));insert(doc,0,"Cancel me.");OK(exr_pager_set_control(p,&control,&error));
  CHECK(exr_edit_layout_after(doc,p,0,&n,&error)==EXR_CANCELLED && n==0);
  CHECK(exr_edit_reflow_statistics(p).revision==revision);OK(exr_pager_get(p,0,&now,&error));CHECK(now==old);
  stop=0;OK(exr_edit_layout_after(doc,p,0,&n,&error));compare(p,doc);
  OK(exr_pager_set_cache(p,1,1,&error));CHECK(exr_pager_get(p,0,&now,&error)==EXR_LIMIT);
  OK(exr_pager_set_cache(p,2,1024*1024,&error));OK(exr_pager_get(p,0,&now,&error));
  exr_pager_free(p);exr_edit_doc_free(doc);
}
static void formatting(void) {
  exr_edit_doc *doc=model(100,0);exr_pager *p=pager(doc);size_t n;exr_edit_run_props style={0};
  exr_edit_para_props para={0};
  style.present=EXR_EDIT_BOLD|EXR_EDIT_SIZE|EXR_EDIT_COLOR;style.bold=1;style.size_half_points=30;style.color_rgb=0x336699;
  OK(exr_edit_set_run_props(doc,1049,0,&style));
  para.present=EXR_EDIT_ALIGN|EXR_EDIT_INDENT|EXR_EDIT_SPACING;para.alignment=EXR_EDIT_RIGHT;
  para.indent_left=120;para.indent_right=240;para.indent_first_line=90;para.space_after=100;
  OK(exr_edit_set_paragraph_props(doc,1048,&para));OK(exr_edit_layout_after(doc,p,1049,&n,&error));
  CHECK(exr_edit_reflow_statistics(p).dirty.old_first==48);compare(p,doc);
  exr_pager_free(p);exr_edit_doc_free(doc);
}
static void unicode(void) {
  const char *text="A\xe4\xb8\xad\xe6\x96\x87 text";exr_edit_doc *doc=model(30,0);exr_edit_id id=insert(doc,1009,text);
  exr_pager *p=pager(doc);size_t n;exr_edit_view_anchor a,b;
  CHECK(exr_edit_anchor_capture(p,1,id,2,&a,&error)==EXR_ARGUMENT);
  OK(exr_edit_anchor_capture(p,1,id,4,&a,&error));insert(doc,0,"Before UTF8.");
  OK(exr_edit_layout_after(doc,p,0,&n,&error));OK(exr_edit_anchor_restore(p,&a,&b,&error));
  CHECK(b.block_id==id && b.byte_offset==4);
  printf("anchor UTF8: page %zu offset %zu -> page %zu offset %zu, block %llu byte %zu\n",a.page_index,a.page_offset,b.page_index,b.page_offset,(unsigned long long)id,b.byte_offset);
  compare(p,doc);exr_pager_free(p);exr_edit_doc_free(doc);
}
static exr_edit_doc *single(const char *text) {
  exr_edit_doc *doc=NULL;exr_edit_run run={0};exr_edit_block block={0};
  run.id=100000;run.text=text;run.text_size=strlen(text);block.id=1000;block.runs=&run;block.run_count=1;
  OK(exr_edit_doc_create(NULL,0,&block,1,NULL,0,NULL,&doc));return doc;
}
static void long_paragraph(void) {
  char *text=malloc(40002);exr_edit_doc *doc,*revised;exr_pager *p;size_t n,i,pages;
  CHECK(text);for(i=0;i<40000;i++) text[i]=i%5==4 ? ' ' : 'A';text[40000]='.';text[40001]=0;
  doc=single(text);p=pager(doc);pages=exr_edit_reflow_statistics(p).page_count;CHECK(pages>50);
  text[40000]='!';revised=single(text);OK(exr_edit_layout_after(revised,p,1000,&n,&error));
  CHECK(n==1);CHECK(exr_edit_reflow_statistics(p).dirty.first_page==pages-1);compare(p,revised);
  exr_pager_free(p);exr_edit_doc_free(doc);exr_edit_doc_free(revised);free(text);
}
static void anchor_revisions(void) {
  exr_edit_doc *doc=single("prefix original target suffix"),*revised=single("prefix INSERT original target suffix");
  exr_pager *p=pager(doc);exr_edit_view_anchor a,b;size_t n;
  OK(exr_edit_anchor_capture(p,0,1000,16,&a,&error));
  OK(exr_edit_layout_after(revised,p,1000,&n,&error));OK(exr_edit_anchor_restore(p,&a,&b,&error));
  CHECK(b.block_id==1000 && b.byte_offset==23);
  CHECK(!memcmp(exr_edit_block_at(revised,0)->runs[0].text+b.byte_offset,"target",6));
  printf("anchor replacement: page %zu offset %zu -> page %zu offset %zu, text target\n",a.page_index,a.page_offset,b.page_index,b.page_offset);
  insert(revised,0,"another revision");OK(exr_edit_layout_after(revised,p,0,&n,&error));
  CHECK(exr_edit_anchor_restore(p,&a,&b,&error)==EXR_ARGUMENT);
  exr_pager_free(p);exr_edit_doc_free(doc);exr_edit_doc_free(revised);
}
static void empty(void) {
  exr_edit_doc *doc=NULL;exr_pager *p;size_t n;exr_edit_id id;const exr_layout *page;
  OK(exr_edit_doc_create(NULL,0,NULL,0,NULL,0,NULL,&doc));p=pager(doc);
  CHECK(exr_edit_reflow_statistics(p).page_count==1);OK(exr_pager_get(p,0,&page,&error));
  id=insert(doc,0,"");OK(exr_edit_layout_after(doc,p,id,&n,&error));CHECK(n==1);compare(p,doc);
  OK(exr_edit_delete_block(doc,id));OK(exr_edit_layout_after(doc,p,id,&n,&error));CHECK(n==1);compare(p,doc);
  exr_pager_free(p);exr_edit_doc_free(doc);
}
static void disjoint(void) {
  exr_edit_doc *doc=model(100,0);exr_pager *p=pager(doc);exr_edit_para_props prop={0};
  exr_edit_run_props run={0};size_t n;exr_edit_tx *tx;
  prop.present=EXR_EDIT_PAGE_BEFORE;prop.page_break_before=1;
  OK(exr_edit_set_paragraph_props(doc,1050,&prop));OK(exr_edit_layout_after(doc,p,0,&n,&error));
  tx=exr_edit_begin(doc);CHECK(tx);insert(doc,1000,"first dirty island");
  run.present=EXR_EDIT_COLOR;run.color_rgb=0xff0000;OK(exr_edit_set_run_props(doc,1090,0,&run));OK(exr_edit_commit(tx));
  OK(exr_edit_layout_after(doc,p,1000,&n,&error));CHECK(exr_edit_reflow_statistics(p).dirty.old_end==91);
  CHECK(n>=10);compare(p,doc);exr_pager_free(p);exr_edit_doc_free(doc);
}
static double now(void) {
#ifdef _WIN32
  LARGE_INTEGER t,f;QueryPerformanceCounter(&t);QueryPerformanceFrequency(&f);return (double)t.QuadPart/f.QuadPart;
#else
  struct timespec t;timespec_get(&t,TIME_UTC);return t.tv_sec+t.tv_nsec/1e9;
#endif
}
static int double_order(const void *a,const void *b) { double x=*(const double *)a,y=*(const double *)b;return (x>y)-(x<y); }
static void benchmark(void) {
  int scenario,trial;const char *names[]={"head_insert","middle_insert","last_character","append_50"};
  puts("scenario,trials,pages_before,pages_after,repaginated,p50_ms,p95_ms,cache_hits,cache_misses,cache_invalidated,cache_hit_rate,cold_frame_p50_ms,cold_frame_p95_ms,reflow_and_frame_p50_ms,reflow_and_frame_p95_ms,full_rebuild_p50_ms,full_rebuild_p95_ms");
  for(scenario=0;scenario<4;scenario++) {
    double times[31],frames[31],totals[31],full[31];size_t n=0,hits=0,misses=0,invalidated=0,pages=0;
    for(trial=0;trial<31;trial++) {
      exr_edit_doc *doc=model(1000,0),*replacement=NULL;exr_pager *p=pager(doc);const exr_layout *page;
      const size_t probes[]={0,10,49,50,98,99};size_t j;exr_pager_cache_stats before,after;double start;
      CHECK(exr_edit_reflow_statistics(p).page_count==100);
      for(j=0;j<6;j++) OK(exr_pager_get(p,probes[j],&page,&error));
      before=exr_pager_cache_statistics(p);
      if(scenario<2) insert(doc,scenario ? 1499 : 0,"An inserted paragraph.");
      else if(scenario==2) replacement=model(1000,1);
      else { exr_edit_tx *tx=exr_edit_begin(doc);exr_edit_id id=1999;CHECK(tx);for(j=0;j<50;j++) id=insert(doc,id,"AI appended paragraph.");OK(exr_edit_commit(tx)); }
      start=now();OK(exr_edit_layout_after(replacement ? replacement : doc,p,0,&n,&error));times[trial]=(now()-start)*1000;
      invalidated+=exr_edit_reflow_statistics(p).cache_invalidated;pages=exr_edit_reflow_statistics(p).page_count;
      for(j=0;j<6;j++) OK(exr_pager_get(p,probes[j],&page,&error));
      after=exr_pager_cache_statistics(p);hits+=after.hits-before.hits;misses+=after.misses-before.misses;
      /* Report a cold visible frame separately, without warming the cache probe.
         LRU eviction and full-reference creation are outside the reflow timer. */
      OK(exr_pager_set_cache(p,1,1,&error));OK(exr_pager_set_cache(p,64,8*1024*1024,&error));
      start=now();
      OK(exr_pager_get(p,exr_edit_reflow_statistics(p).dirty.first_page,&page,&error));
      { exr_bitmap bitmap={0};OK(exr_render_page_color(page,font,0,&bitmap,&error));exr_bitmap_free(&bitmap); }
      frames[trial]=(now()-start)*1000;totals[trial]=times[trial]+frames[trial];
      start=now();{ exr_pager *reference=pager(replacement ? replacement : doc);exr_pager_free(reference); }
      full[trial]=(now()-start)*1000;
      CHECK(scenario!=2 || n==1);CHECK(scenario!=3 || n==5);
      exr_pager_free(p);exr_edit_doc_free(replacement);exr_edit_doc_free(doc);
    }
    qsort(times,31,sizeof(*times),double_order);
    qsort(frames,31,sizeof(*frames),double_order);qsort(totals,31,sizeof(*totals),double_order);qsort(full,31,sizeof(*full),double_order);
    printf("%s,31,100,%zu,%zu,%.4f,%.4f,%zu,%zu,%zu,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f\n",
      names[scenario],pages,n,times[15],times[29],hits,misses,invalidated,(double)hits/(hits+misses),
      frames[15],frames[29],totals[15],totals[29],full[15],full[29]);
  }
}
int main(int argc,char **argv) {
  CHECK(argc==3);OK(exr_font_open(argv[1],&font,&error));
  if(!strcmp(argv[2],"basic")) basic();else if(!strcmp(argv[2],"insertions")) insertions();
  else if(!strcmp(argv[2],"convergence")) convergence();else if(!strcmp(argv[2],"history")) history();
  else if(!strcmp(argv[2],"anchors")) anchors();else if(!strcmp(argv[2],"failures")) failures();
  else if(!strcmp(argv[2],"formatting")) formatting();else if(!strcmp(argv[2],"unicode")) unicode();
  else if(!strcmp(argv[2],"long")) long_paragraph();else if(!strcmp(argv[2],"revision")) anchor_revisions();
  else if(!strcmp(argv[2],"empty")) empty();else if(!strcmp(argv[2],"disjoint")) disjoint();
  else if(!strcmp(argv[2],"benchmark")) benchmark();else CHECK(0);
  exr_font_free(font);return 0;
}
