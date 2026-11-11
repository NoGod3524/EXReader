/* SPDX-License-Identifier: MIT */
#include <exr/edit.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifdef _WIN32
#include <windows.h>
#include <psapi.h>
#else
#include <sys/time.h>
#endif

#define CHECK(x) do { if (!(x)) { fprintf(stderr,"%s:%d: %s\n",__FILE__,__LINE__,#x); exit(1); } } while (0)
#define OK(x) CHECK((x)==EXR_OK)
static exr_edit_doc *empty(const exr_edit_options *options) {
  exr_edit_doc *d=NULL;
  OK(exr_edit_doc_create(NULL,0,NULL,0,NULL,0,options,&d)); CHECK(d); return d;
}
static exr_edit_id insert(exr_edit_doc *d,exr_edit_id after,const char *text) {
  exr_edit_id id=0; exr_edit_run r={0}; r.text=text; r.text_size=strlen(text);
  OK(exr_edit_insert_paragraph(d,after,&r,1,NULL,&id)); CHECK(id); return id;
}
static int bytes_equal(const void *a,const void *b,size_t n) { return !n || !memcmp(a,b,n); }
static void same_block(const exr_edit_block *a,const exr_edit_block *b) {
  size_t i;
  CHECK(a && b); CHECK(a->id==b->id && a->section_id==b->section_id && a->kind==b->kind);
  CHECK(!memcmp(&a->props,&b->props,sizeof(a->props)));
  CHECK(a->opaque_size==b->opaque_size && bytes_equal(a->opaque_xml,b->opaque_xml,a->opaque_size));
  CHECK(a->run_count==b->run_count);
  for (i=0;i<a->run_count;i++) {
    const exr_edit_run *x=a->runs+i,*y=b->runs+i;
    CHECK(x->id==y->id && x->kind==y->kind && x->text_size==y->text_size);
    CHECK(bytes_equal(x->text,y->text,x->text_size));
    CHECK(!memcmp(&x->props,&y->props,sizeof(x->props)));
    CHECK(x->opaque_size==y->opaque_size && bytes_equal(x->opaque_xml,y->opaque_xml,x->opaque_size));
  }
}
static void same_doc(exr_edit_doc *a,exr_edit_doc *b) {
  size_t i,na,nb; const exr_edit_section *sa,*sb; const exr_edit_part *pa,*pb;
  CHECK(exr_edit_block_count(a)==exr_edit_block_count(b));
  for (i=0;i<exr_edit_block_count(a);i++) same_block(exr_edit_block_at(a,i),exr_edit_block_at(b,i));
  sa=exr_edit_sections(a,&na); sb=exr_edit_sections(b,&nb);
  CHECK(na==nb && bytes_equal(sa,sb,na*sizeof(*sa)));
  pa=exr_edit_parts(a,&na); pb=exr_edit_parts(b,&nb); CHECK(na==nb);
  for (i=0;i<na;i++) CHECK(pa[i].id==pb[i].id && !strcmp(pa[i].name,pb[i].name) &&
    pa[i].size==pb[i].size && bytes_equal(pa[i].data,pb[i].data,pa[i].size));
}
static exr_edit_doc *snapshot(exr_edit_doc *d) {
  size_t i,ns,np,n=exr_edit_block_count(d); exr_edit_doc *copy=NULL;
  const exr_edit_section *s=exr_edit_sections(d,&ns); const exr_edit_part *p=exr_edit_parts(d,&np);
  exr_edit_block *blocks=n ? calloc(n,sizeof(*blocks)) : NULL;
  CHECK(!n || blocks);
  for (i=0;i<n;i++) blocks[i]=*exr_edit_block_at(d,i);
  OK(exr_edit_doc_create(s,ns,blocks,n,p,np,NULL,&copy)); free(blocks); return copy;
}
static exr_edit_doc *seed(void) {
  exr_edit_doc *d=NULL; exr_edit_section s[2]={{0}}; exr_edit_block b[4]={{0}};
  exr_edit_run r[3]={{0}}; exr_edit_part p[3]={{0}};
  unsigned char image[]={137,80,78,71,0,13,10,255};
  char table[]="<w:tbl><w:tr><w:tc><w:p/></w:tc></w:tr></w:tbl>";
  char drawing[]="<w:r><w:drawing><a:blip r:embed=\"rIdImage\"/></w:drawing></w:r>";
  char unknown[]="<w:tabs><w:tab w:val=\"left\" w:pos=\"720\"/></w:tabs>";
  char rels[]="<Relationships><Relationship Id=\"rIdImage\" Target=\"media/image1.png\"/></Relationships>";
  s[0].id=10; s[0].page_width=12240; s[0].page_height=15840;
  s[0].margin_left=s[0].margin_right=s[0].margin_top=s[0].margin_bottom=1440;
  strcpy(s[0].header_refs[0],"rIdHeader"); strcpy(s[0].footer_refs[2],"rIdFooterEven");
  s[1]=s[0]; s[1].id=11; s[1].landscape=1; s[1].page_width=15840; s[1].page_height=12240;
  r[0].id=30; r[0].text="alpha"; r[0].text_size=5;
  r[0].props.present=EXR_EDIT_FONT|EXR_EDIT_SIZE|EXR_EDIT_BOLD;
  strcpy(r[0].props.font,"Aptos"); r[0].props.size_half_points=24; r[0].props.bold=1;
  r[1].id=31; r[1].kind=EXR_EDIT_OPAQUE_RUN; r[1].opaque_xml=drawing; r[1].opaque_size=strlen(drawing);
  r[2].id=32; r[2].text="omega"; r[2].text_size=5;
  b[0].id=20; b[0].section_id=10; b[0].runs=r; b[0].run_count=3;
  b[0].opaque_xml=unknown; b[0].opaque_size=strlen(unknown);
  b[1].id=21; b[1].section_id=10; b[1].kind=EXR_EDIT_TABLE;
  b[1].opaque_xml=table; b[1].opaque_size=strlen(table);
  b[2].id=22; b[2].section_id=11; b[2].kind=EXR_EDIT_PAGE_BREAK;
  b[3].id=23; b[3].section_id=11;
  p[0].id=40; p[0].name="word/media/image1.png"; p[0].data=image; p[0].size=sizeof(image);
  p[1].id=41; p[1].name="word/_rels/document.xml.rels"; p[1].data=rels; p[1].size=strlen(rels);
  p[2].id=42; p[2].name="word/header1.xml"; p[2].data="<w:hdr/>"; p[2].size=8;
  OK(exr_edit_doc_create(s,2,b,4,p,3,NULL,&d));
  memset(table,'!',strlen(table)); memset(drawing,'!',strlen(drawing)); memset(image,0,sizeof(image));
  CHECK(((const unsigned char *)exr_edit_parts(d,NULL)[0].data)[0]==137);
  CHECK(((const char *)exr_edit_block_at(d,1)->opaque_xml)[0]=='<'); return d;
}
static void test_insert(void) {
  exr_edit_doc *d=empty(NULL); exr_edit_id a,b,c; exr_edit_run r={0}; exr_edit_para_props p={0};
  char text[]="owned"; r.text=text; r.text_size=5; p.present=EXR_EDIT_ALIGN; p.alignment=EXR_EDIT_CENTER;
  OK(exr_edit_insert_paragraph(d,0,&r,1,&p,&a)); text[0]='X';
  CHECK(!strcmp(exr_edit_find_block(d,a)->runs[0].text,"owned"));
  b=insert(d,a,"second"); c=insert(d,0,"first");
  CHECK(exr_edit_block_count(d)==3 && exr_edit_block_at(d,1)->id==a && exr_edit_block_at(d,2)->id==b);
  CHECK(exr_edit_find_block(d,a)->props.alignment==EXR_EDIT_CENTER);
  CHECK(c!=a && b!=a && exr_edit_find_block(d,a)->runs[0].id!=a);
  OK(exr_edit_undo(d)); CHECK(!exr_edit_find_block(d,c)); OK(exr_edit_redo(d));
  CHECK(exr_edit_block_at(d,0)->id==c); exr_edit_doc_free(d);
}
static void test_split(void) {
  exr_edit_doc *d=seed(),*before=snapshot(d),*after; const exr_edit_block *a,*b;
  OK(exr_edit_split_paragraph(d,20,0,2));
  a=exr_edit_block_at(d,0); b=exr_edit_block_at(d,1);
  CHECK(a->id==20 && a->run_count==1 && !strcmp(a->runs[0].text,"al") && a->runs[0].id==30);
  CHECK(b->id!=20 && b->section_id==10 && b->run_count==3 && !strcmp(b->runs[0].text,"pha"));
  CHECK(b->runs[0].id!=30 && b->runs[1].id==31 && b->runs[2].id==32);
  CHECK(b->runs[0].props.bold==1 && !strcmp(b->runs[0].props.font,"Aptos"));
  same_block(exr_edit_block_at(d,2),exr_edit_block_at(before,1));
  after=snapshot(d); OK(exr_edit_undo(d)); same_doc(d,before); OK(exr_edit_redo(d)); same_doc(d,after);
  exr_edit_doc_free(after); exr_edit_doc_free(before); exr_edit_doc_free(d);
}
static void test_para_props(void) {
  exr_edit_doc *d=seed(),*before=snapshot(d); exr_edit_para_props p={0};
  p.present=127; p.alignment=EXR_EDIT_JUSTIFY; p.indent_left=720; p.indent_first_line=-360;
  p.space_before=120; p.space_after=240; p.line=360; p.keep_next=1; p.keep_lines=1;
  p.page_break_before=1; p.numbering_id=12; p.numbering_level=2;
  OK(exr_edit_set_paragraph_props(d,20,&p));
  CHECK(!memcmp(&exr_edit_find_block(d,20)->props,&p,sizeof(p)));
  CHECK(exr_edit_find_block(d,20)->runs[0].id==30);
  OK(exr_edit_undo(d)); same_doc(d,before); OK(exr_edit_redo(d));
  CHECK(exr_edit_find_block(d,20)->props.indent_first_line==-360);
  exr_edit_doc_free(before); exr_edit_doc_free(d);
}
static void test_run_props(void) {
  exr_edit_doc *d=seed(),*before=snapshot(d); exr_edit_run_props p={0};
  p.present=31; strcpy(p.font,"Noto Serif"); p.size_half_points=30; p.italic=1; p.color_rgb=0x123456;
  OK(exr_edit_set_run_props(d,20,0,&p));
  CHECK(!memcmp(&exr_edit_find_block(d,20)->runs[0].props,&p,sizeof(p)));
  CHECK(exr_edit_find_block(d,20)->runs[0].id==30 && exr_edit_find_block(d,20)->runs[1].id==31);
  OK(exr_edit_undo(d)); same_doc(d,before); OK(exr_edit_redo(d));
  CHECK(!exr_edit_find_block(d,20)->runs[0].props.bold);
  exr_edit_doc_free(before); exr_edit_doc_free(d);
}
static void test_delete(void) {
  exr_edit_doc *d=seed(),*before=snapshot(d);
  OK(exr_edit_delete_block(d,20)); CHECK(!exr_edit_find_block(d,20) && exr_edit_block_count(d)==3);
  CHECK(exr_edit_block_at(d,0)->id==21); OK(exr_edit_undo(d)); same_doc(d,before);
  OK(exr_edit_redo(d)); CHECK(!exr_edit_find_block(d,20));
  OK(exr_edit_delete_block(d,22)); CHECK(!exr_edit_find_block(d,22));
  CHECK(exr_edit_delete_block(d,21)==EXR_UNSUPPORTED);
  exr_edit_doc_free(before); exr_edit_doc_free(d);
}
static void test_transaction(void) {
  size_t i; exr_edit_doc *d=empty(NULL),*after; exr_edit_tx *t=exr_edit_begin(d); exr_edit_id id=0;
  CHECK(t && !exr_edit_begin(d)); CHECK(exr_edit_undo(d)==EXR_ARGUMENT);
  for (i=0;i<20;i++) id=insert(d,id,"transaction paragraph");
  OK(exr_edit_commit(t)); CHECK(exr_edit_block_count(d)==20); after=snapshot(d);
  OK(exr_edit_undo(d)); CHECK(exr_edit_block_count(d)==0 && exr_edit_undo(d)==EXR_ARGUMENT);
  OK(exr_edit_redo(d)); same_doc(d,after); CHECK(exr_edit_redo(d)==EXR_ARGUMENT);
  printf("transaction: 20 inserts -> 1 undo = 0 blocks -> 1 redo = 20 blocks\n");
  exr_edit_doc_free(after); exr_edit_doc_free(d);
}
static void test_rollback(void) {
  size_t i; exr_edit_doc *d=seed(),*before=snapshot(d); exr_edit_id id=20;
  exr_edit_tx *t=exr_edit_begin(d); exr_edit_para_props p={0};
  CHECK(t);
  for (i=0;i<9;i++) id=insert(d,id,"must disappear");
  CHECK(exr_edit_set_paragraph_props(d,UINT64_MAX,&p)==EXR_ARGUMENT); /* command 10 */
  CHECK(exr_edit_delete_block(d,20)==EXR_ARGUMENT); /* failure latched */
  OK(exr_edit_rollback(t)); same_doc(d,before); CHECK(exr_edit_undo(d)==EXR_ARGUMENT);
  t=exr_edit_begin(d); insert(d,20,"commit must roll back");
  CHECK(exr_edit_split_paragraph(d,20,0,100)==EXR_ARGUMENT);
  CHECK(exr_edit_commit(t)==EXR_ARGUMENT); same_doc(d,before);
  printf("rollback: command 10 failed; 9 inserts reverted; %zu blocks + all runs/sections/parts identical\n",
    exr_edit_block_count(d));
  exr_edit_doc_free(before); exr_edit_doc_free(d);
}
static void test_history(void) {
  size_t i; exr_edit_doc *d=empty(NULL); exr_edit_id id=0; exr_edit_options o={3};
  for (i=0;i<120;i++) id=insert(d,id,"history");
  for (i=0;i<100;i++) OK(exr_edit_undo(d));
  CHECK(exr_edit_block_count(d)==20 && exr_edit_undo(d)==EXR_ARGUMENT);
  for (i=0;i<100;i++) OK(exr_edit_redo(d));
  CHECK(exr_edit_block_count(d)==120 && exr_edit_redo(d)==EXR_ARGUMENT);
  OK(exr_edit_undo(d)); insert(d,0,"branch"); CHECK(exr_edit_redo(d)==EXR_ARGUMENT);
  printf("history: 120 edits, exactly 100 undo/redo; 20 blocks remain at oldest state\n");
  exr_edit_doc_free(d); d=empty(&o);
  for (i=0;i<5;i++) insert(d,0,"depth 3");
  for (i=0;i<3;i++) OK(exr_edit_undo(d));
  CHECK(exr_edit_undo(d)==EXR_ARGUMENT && exr_edit_block_count(d)==2); exr_edit_doc_free(d);
  o.undo_depth=0; d=empty(&o); insert(d,0,"no history"); CHECK(exr_edit_undo(d)==EXR_ARGUMENT);
  exr_edit_doc_free(d);
}
static void test_preservation(void) {
  size_t i; exr_edit_doc *d=seed(),*before=snapshot(d),*after; exr_edit_tx *t=exr_edit_begin(d);
  exr_edit_para_props p={0}; exr_edit_run_props rp={0}; exr_edit_id id;
  id=insert(d,21,"after table"); CHECK(exr_edit_find_block(d,id)->section_id==10);
  p.present=EXR_EDIT_KEEP_NEXT; p.keep_next=1; rp.present=EXR_EDIT_BOLD;
  OK(exr_edit_set_paragraph_props(d,20,&p)); OK(exr_edit_set_run_props(d,20,0,&rp));
  OK(exr_edit_split_paragraph(d,20,1,0)); OK(exr_edit_delete_block(d,id)); OK(exr_edit_commit(t));
  same_block(exr_edit_find_block(d,21),exr_edit_find_block(before,21));
  CHECK(exr_edit_block_at(d,1)->runs[0].id==31);
  CHECK(bytes_equal(exr_edit_block_at(d,1)->runs[0].opaque_xml,
    exr_edit_find_block(before,20)->runs[1].opaque_xml,exr_edit_block_at(d,1)->runs[0].opaque_size));
  after=snapshot(d);
  for (i=0;i<10;i++) { OK(exr_edit_undo(d)); same_doc(d,before); OK(exr_edit_redo(d)); same_doc(d,after); }
  exr_edit_doc_free(after); exr_edit_doc_free(before); exr_edit_doc_free(d);
}
static void test_boundaries(void) {
  exr_edit_doc *d=empty(NULL),*before; exr_edit_id id=insert(d,0,"A\xe4\xb8\xad\xf0\x9f\x98\x80Z");
  exr_edit_id rid=exr_edit_find_block(d,id)->runs[0].id,new_id=0; exr_edit_tx *t;
  CHECK(exr_edit_split_paragraph(d,id,0,2)==EXR_ARGUMENT);
  CHECK(exr_edit_split_paragraph(d,id,0,5)==EXR_ARGUMENT);
  OK(exr_edit_split_paragraph(d,id,0,4)); CHECK(!strcmp(exr_edit_block_at(d,0)->runs[0].text,"A\xe4\xb8\xad"));
  CHECK(!strcmp(exr_edit_block_at(d,1)->runs[0].text,"\xf0\x9f\x98\x80Z")); OK(exr_edit_undo(d));
  OK(exr_edit_split_paragraph(d,id,0,0)); CHECK(!exr_edit_block_at(d,0)->run_count);
  CHECK(exr_edit_block_at(d,1)->runs[0].id==rid); OK(exr_edit_undo(d));
  OK(exr_edit_split_paragraph(d,id,0,9)); CHECK(!exr_edit_block_at(d,1)->run_count); OK(exr_edit_undo(d));
  OK(exr_edit_split_paragraph(d,id,1,0)); CHECK(!exr_edit_block_at(d,1)->run_count); OK(exr_edit_undo(d));
  before=snapshot(d); t=exr_edit_begin(d); CHECK(t); OK(exr_edit_commit(t));
  OK(exr_edit_redo(d)); OK(exr_edit_undo(d)); same_doc(d,before);
  t=exr_edit_begin(d); insert(d,id,"rollback redo preserved"); OK(exr_edit_rollback(t)); OK(exr_edit_redo(d));
  OK(exr_edit_undo(d)); same_doc(d,before);
  { exr_edit_run bad={0}; bad.text="\xc0\xaf"; bad.text_size=2;
    CHECK(exr_edit_insert_paragraph(d,0,&bad,1,NULL,&new_id)==EXR_ARGUMENT && !new_id); }
  { exr_edit_block bad[2]={{0}}; exr_edit_doc *out=d; bad[0].id=bad[1].id=1;
    CHECK(exr_edit_doc_create(NULL,0,bad,2,NULL,0,NULL,&out)==EXR_ARGUMENT && !out); }
  t=exr_edit_begin(d); new_id=insert(d,0,"never reused"); OK(exr_edit_rollback(t));
  CHECK(insert(d,0,"fresh ID")>new_id);
  exr_edit_doc_free(before); exr_edit_doc_free(d);
  d=empty(NULL); OK(exr_edit_insert_paragraph(d,0,NULL,0,NULL,&id));
  OK(exr_edit_split_paragraph(d,id,0,0)); CHECK(exr_edit_block_count(d)==2); exr_edit_doc_free(d);
  CHECK(exr_edit_delete_block(NULL,1)==EXR_ARGUMENT && !exr_edit_begin(NULL));
}
static void test_mixed(void) {
  unsigned step,state=12345; exr_edit_doc *d=seed();
  for (step=0;step<300;step++) {
    exr_edit_doc *before=snapshot(d),*after; size_t n=exr_edit_block_count(d),index;
    const exr_edit_block *b; exr_edit_tx *t=exr_edit_begin(d); exr_edit_para_props p={0};
    exr_edit_run_props rp={0}; exr_edit_id id;
    state=state*1664525u+1013904223u; index=state%n; b=exr_edit_block_at(d,index); id=b->id;
    if (step%5==0 || b->kind!=EXR_EDIT_PARAGRAPH) insert(d,id,"random insert");
    else if (step%5==1) { p.present=EXR_EDIT_ALIGN; p.alignment=(exr_edit_alignment)(step%4); OK(exr_edit_set_paragraph_props(d,id,&p)); }
    else if (step%5==2 && b->run_count && b->runs[0].kind==EXR_EDIT_TEXT) {
      rp.present=EXR_EDIT_ITALIC; rp.italic=step%2; OK(exr_edit_set_run_props(d,id,0,&rp));
    } else if (step%5==3) OK(exr_edit_split_paragraph(d,id,b->run_count,0));
    else OK(exr_edit_delete_block(d,id));
    OK(exr_edit_commit(t)); after=snapshot(d);
    OK(exr_edit_undo(d)); same_doc(d,before); OK(exr_edit_redo(d)); same_doc(d,after);
    exr_edit_doc_free(before); exr_edit_doc_free(after);
  }
  exr_edit_doc_free(d);
}
static double seconds(void) {
#ifdef _WIN32
  LARGE_INTEGER value,frequency; QueryPerformanceCounter(&value); QueryPerformanceFrequency(&frequency);
  return (double)value.QuadPart/(double)frequency.QuadPart;
#else
  struct timeval value; gettimeofday(&value,NULL); return (double)value.tv_sec+(double)value.tv_usec/1e6;
#endif
}
static size_t resident(void) {
#ifdef _WIN32
  PROCESS_MEMORY_COUNTERS counters; memset(&counters,0,sizeof(counters)); counters.cb=sizeof(counters);
  CHECK(GetProcessMemoryInfo(GetCurrentProcess(),&counters,sizeof(counters)));
  return (size_t)counters.WorkingSetSize;
#else
  return 0; /* Portable model allocation count is reported on every platform. */
#endif
}
static int compare_times(const void *a,const void *b) {
  double x=*(const double *)a,y=*(const double *)b; return (x>y)-(x<y);
}
static void benchmark(void) {
  size_t i,page,index=0,n=2099,base_bytes,base_rss,final_rss; double times[200],start;
  exr_edit_doc *d=NULL; exr_edit_id id; exr_edit_block *b=calloc(n,sizeof(*b));
  exr_edit_run r={0}; char text[121]; CHECK(b); memset(text,'a',120); text[120]=0;
  r.text=text; r.text_size=120;
  /* 100 explicitly delimited logical pages, 20 paragraphs/page, 120 bytes/paragraph.
     Pagination/rendering belongs to the existing reader, not this model. */
  for (page=0;page<100;page++) {
    for (i=0;i<20;i++,index++) { b[index].runs=&r; b[index].run_count=1; }
    if (page<99) b[index++].kind=EXR_EDIT_PAGE_BREAK;
  }
  CHECK(index==n); OK(exr_edit_doc_create(NULL,0,b,n,NULL,0,NULL,&d)); free(b);
  base_bytes=exr_edit_memory_bytes(d); base_rss=resident();
  for (i=0;i<200;i++) {
    const exr_edit_block *anchor=exr_edit_block_at(d,exr_edit_block_count(d)/2);
    start=seconds(); OK(exr_edit_insert_paragraph(d,anchor->id,&r,1,NULL,&id)); times[i]=(seconds()-start)*1e6;
  }
  final_rss=resident(); qsort(times,200,sizeof(*times),compare_times);
  printf("{\"logical_pages\":100,\"base_paragraphs\":2000,\"page_breaks\":99,\"text_bytes_per_paragraph\":120,"
    "\"insertions\":200,\"history_depth\":100,\"p50_us\":%.6f,\"p95_us\":%.6f,"
    "\"model_bytes_before\":%zu,\"model_bytes_after\":%zu,\"model_delta_bytes\":%zu,"
    "\"rss_before\":%zu,\"rss_after\":%zu,\"rss_delta_bytes\":%lld}\n",
    times[99],times[189],base_bytes,exr_edit_memory_bytes(d),exr_edit_memory_bytes(d)-base_bytes,
    base_rss,final_rss,(long long)final_rss-(long long)base_rss);
  CHECK(exr_edit_block_count(d)==2299); exr_edit_doc_free(d);
}
int main(int argc,char **argv) {
  const char *group=argc>1 ? argv[1] : "";
  if (!strcmp(group,"insert")) test_insert();
  else if (!strcmp(group,"split")) test_split();
  else if (!strcmp(group,"para-props")) test_para_props();
  else if (!strcmp(group,"run-props")) test_run_props();
  else if (!strcmp(group,"delete")) test_delete();
  else if (!strcmp(group,"transaction")) test_transaction();
  else if (!strcmp(group,"rollback")) test_rollback();
  else if (!strcmp(group,"history")) test_history();
  else if (!strcmp(group,"preservation")) test_preservation();
  else if (!strcmp(group,"boundaries")) test_boundaries();
  else if (!strcmp(group,"mixed")) test_mixed();
  else if (!strcmp(group,"benchmark")) benchmark();
  else { fprintf(stderr,"unknown test group: %s\n",group); return 2; }
  printf("docx-edit-%s: passed\n",group); return 0;
}
