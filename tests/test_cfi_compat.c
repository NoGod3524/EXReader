/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <miniz.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static exr_error error;static unsigned checks;
#define CHECK(x) do { checks++;if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message);exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static int cancel(void *ctx) { (void)ctx;return 1; }
static int same(exr_text_range a,exr_text_range b) {
  return a.start.part==b.start.part && a.start.offset==b.start.offset && a.end.part==b.end.part && a.end.offset==b.end.offset;
}
static int equal_string(const char *a,const char *b) { return a && b ? !strcmp(a,b) : a==b; }
static void equal_endpoint(const exr_content_endpoint *a,const exr_content_endpoint *b) {
  CHECK(equal_string(a->part_id,b->part_id) && equal_string(a->part_path,b->part_path));
  CHECK(a->text_revision==b->text_revision && a->text_size==b->text_size);
  CHECK(a->selector.start==b->selector.start && a->selector.end==b->selector.end);
  CHECK(equal_string(a->selector.chapter,b->selector.chapter) && equal_string(a->selector.exact,b->selector.exact));
  CHECK(equal_string(a->selector.prefix,b->selector.prefix) && equal_string(a->selector.suffix,b->selector.suffix));
}
static void vectors(const char *path,int invalid) {
  FILE *f=fopen(path,"rb");char line[4096];unsigned count=0;CHECK(f);
  while(fgets(line,sizeof(line),f)) {
    exr_cfi *parsed=NULL,*again=NULL;exr_cfi_diagnostic diag;exr_status status;char *tab,*s,*serialized=NULL,*copy=NULL,*a=NULL,*b=NULL;
    unsigned code;size_t n;
    if(line[0]=='#') continue;
    tab=strchr(line,'\t');CHECK(tab);*tab=0;code=(unsigned)strtoul(line,NULL,10);s=tab+1;
    n=strlen(s);while(n && (s[n-1]=='\n' || s[n-1]=='\r')) s[--n]=0;
    if((code!=0)!=invalid) continue;
    status=exr_cfi_parse(s,&parsed,&diag,&error);count++;
    if(code) {
      if(status!=EXR_FORMAT || diag.code!=(exr_cfi_error_code)code) fprintf(stderr,"vector: %s expected %u got %u\n",s,code,(unsigned)diag.code);
      CHECK(status==EXR_FORMAT && !parsed && diag.code==(exr_cfi_error_code)code && diag.byte<=n);
      continue;
    }
    OK(status);CHECK(parsed && !diag.code);
    OK(exr_cfi_serialize(parsed,&serialized,&error));
    if(!strncmp(s,"epubcfi(",8)) CHECK(!strcmp(s,serialized));
    else CHECK(!strncmp(serialized,"epubcfi(",8) && !memcmp(serialized+8,s,n) && !strcmp(serialized+8+n,")"));
    OK(exr_cfi_parse(serialized,&again,NULL,&error));OK(exr_cfi_serialize(again,&copy,&error));CHECK(!strcmp(serialized,copy));
    OK(exr_cfi_endpoints(parsed,&a,&b,&error));
    { exr_cfi *p=NULL;OK(exr_cfi_parse(a,&p,NULL,&error));CHECK(!exr_cfi_is_range(p));exr_cfi_free(p);
      OK(exr_cfi_parse(b,&p,NULL,&error));CHECK(!exr_cfi_is_range(p));exr_cfi_free(p); }
    { size_t k;char prefix[4096];
      memcpy(prefix,s,n+1);
      for(k=0;k<n;k++) {
        exr_cfi *p=NULL;char saved=prefix[k];exr_cfi_diagnostic diagnostic;
        prefix[k]=0;status=exr_cfi_parse(prefix,&p,&diagnostic,&error);prefix[k]=saved;
        CHECK((status==EXR_OK && p && diagnostic.code==EXR_CFI_VALID) ||
          (status!=EXR_OK && !p && diagnostic.code!=EXR_CFI_VALID && diagnostic.byte<=k));
        exr_cfi_free(p);
      }
    }
    exr_cfi_free(parsed);exr_cfi_free(again);exr_free(serialized);exr_free(copy);exr_free(a);exr_free(b);
  }
  CHECK(!ferror(f));fclose(f);CHECK(count>=20);printf("%s vectors: %u/%u\n",invalid ? "invalid" : "valid",count,count);
}
static exr_publication *fixture(void) {
  const char *names[]={"mimetype","META-INF/container.xml","book.opf","a.xhtml","b.xhtml","empty.xhtml"};
  const char *values[]={"application/epub+zip","<container><rootfiles><rootfile full-path='book.opf'/></rootfiles></container>",
    "<package><metadata/><manifest><item id='a' href='a.xhtml' media-type='application/xhtml+xml'/><item id='b' href='b.xhtml' media-type='application/xhtml+xml'/><item id='empty' href='empty.xhtml' media-type='application/xhtml+xml'/></manifest><spine><itemref id='ref=a' idref='a'/><itemref idref='b'/><itemref idref='empty'/></spine></package>",
    "<html><head><title>Hidden</title><style>hidden</style></head><body id='body=a'><p id='p'>  Alpha\t beta <em>中😀文</em> tail  </p><p>\n A<em> </em>B  C\nD　文  字</p><div hidden='hidden'>invisible</div><p>repeat repeat repeat</p><p><br/></p><p>last😀</p></body></html>",
    "<html><head/><body><p>Second part. 标注😀  more.</p><p>Last line.</p></body></html>",
    "<html><head/><body><p> </p></body></html>"};
  mz_zip_archive zip={0};void *bytes;size_t n,i;exr_publication *p=NULL;
  CHECK(mz_zip_writer_init_heap(&zip,0,0));
  for(i=0;i<6;i++) CHECK(mz_zip_writer_add_mem(&zip,names[i],values[i],strlen(values[i]),i ? MZ_BEST_SPEED : 0));
  CHECK(mz_zip_writer_finalize_heap_archive(&zip,&bytes,&n));CHECK(mz_zip_writer_end(&zip));
  OK(exr_publication_open_memory(EXR_EPUB,bytes,n,&p,&error));free(bytes);return p;
}
static size_t *boundaries(exr_publication *p,size_t part,size_t *count) {
  exr_document *d=NULL;size_t size,i,n=0,*out;const char *s;
  OK(exr_publication_load(p,part,&d,&error));s=exr_document_text(d,&size);out=malloc((size+1)*sizeof(*out));CHECK(out);
  for(i=0;i<=size;i++) if(i==size || ((unsigned char)s[i]&0xc0)!=0x80) out[n++]=i;
  exr_document_free(d);*count=n;return out;
}
static void adjacent_text(void) {
  exr_node_input nodes[]={
    {EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0},{EXR_NODE_CHAPTER,0,NULL,NULL,NULL,0},
    {EXR_NODE_ELEMENT,1,"html",NULL,NULL,0},{EXR_NODE_ELEMENT,2,"head",NULL,NULL,0},
    {EXR_NODE_ELEMENT,2,"body",NULL,NULL,0},{EXR_NODE_PARAGRAPH,4,"p",NULL,NULL,0},
    {EXR_NODE_TEXT,5,NULL,"A ",NULL,0},{EXR_NODE_TEXT,5,NULL,"B",NULL,0},
    {EXR_NODE_TEXT,5,NULL,"  ",NULL,0},{EXR_NODE_TEXT,5,NULL,"C",NULL,0}};
  exr_chapter_input chapter={"a","a.xhtml",1,1};
  exr_document_input input={"Adjacent text",nodes,10,&chapter,1,NULL,0};exr_document *d=NULL;size_t i,size;
  OK(exr_document_create(&input,&d,&error));CHECK(!strcmp(exr_document_text(d,&size),"A B C") && size==5);
  for(i=0;i<=size;i++) {
    exr_cfi_point point,resolved;char *path=NULL;size_t offset;
    OK(exr_document_cfi_point_at(d,0,i,NULL,&point,&error));
    OK(exr_document_cfi_path_create(d,0,&point,NULL,&path,&error));
    OK(exr_document_cfi_path_resolve(d,0,path,NULL,&resolved,&error));
    OK(exr_document_cfi_point_offset(d,0,&resolved,NULL,&offset,&error));CHECK(offset==i);exr_free(path);
  }
  exr_document_free(d);
}
static void mapping(void) {
  exr_publication *p=fixture();exr_document *d=NULL;size_t *offsets,n,i,j,count;const exr_node *nodes;
  OK(exr_publication_load(p,0,&d,&error));offsets=boundaries(p,0,&n);nodes=exr_document_nodes(d,&count);
  for(i=0;i<n;i++) {
    exr_cfi_point point,copy;size_t offset;char *path=NULL;
    OK(exr_document_cfi_point_at(d,0,offsets[i],NULL,&point,&error));
    OK(exr_document_cfi_path_create(d,0,&point,NULL,&path,&error));
    OK(exr_document_cfi_path_resolve(d,0,path,NULL,&copy,&error));
    OK(exr_document_cfi_point_offset(d,0,&copy,NULL,&offset,&error));CHECK(offset==offsets[i]);exr_free(path);
  }
  for(j=0;j<count;j++) if(nodes[j].kind==EXR_NODE_TEXT && nodes[j].text && !strcmp(nodes[j].text,"中😀文")) break;
  CHECK(j<count);
  { char *path=NULL;exr_cfi_point point={j,1,0},resolved;
    OK(exr_document_cfi_path_create(d,0,&point,NULL,&path,&error));
    CHECK(!strcmp(path,"/4[body^=a]/2[p]/2/1:1"));exr_free(path);
    OK(exr_document_cfi_path_resolve(d,0,"/4/2/2/1:1[;vnd.exr=x,y;s=a]",NULL,&resolved,&error));
    CHECK(resolved.node==j && resolved.offset==1 && resolved.side==2);
    CHECK(exr_document_cfi_path_resolve(d,0,"/4/2/2/1:1[中,]",NULL,&resolved,&error)==EXR_FORMAT); }
  { size_t offset;exr_cfi_point point={j,2,0};
    CHECK(exr_document_cfi_point_offset(d,0,&point,NULL,&offset,&error)==EXR_ARGUMENT && offset==SIZE_MAX);
    point.offset=3;OK(exr_document_cfi_point_offset(d,0,&point,NULL,&offset,&error));
    CHECK(exr_document_cfi_point_at(d,0,offset-1,NULL,&point,&error)==EXR_ARGUMENT && point.node==SIZE_MAX); }
  for(j=0;j<count;j++) if(nodes[j].kind==EXR_NODE_TEXT && nodes[j].text && !strcmp(nodes[j].text,"last😀")) break;
  CHECK(j<count);
  { char *quoted=NULL;exr_cfi *parsed=NULL;exr_cfi_point point={j,6,0};
    OK(exr_document_cfi_path_create_quoted(d,0,&point,2,NULL,&quoted,&error));
    CHECK(strstr(quoted,"[t😀]") && !strstr(quoted,",]"));
    OK(exr_cfi_parse(quoted,&parsed,NULL,&error));exr_cfi_free(parsed);exr_free(quoted); }
  printf("projection boundaries: %zu/%zu (raw UTF-16/normalized UTF-8)\n",n,n);
  free(offsets);exr_document_free(d);exr_publication_free(p);adjacent_text();
}
static void roundtrip(exr_publication *p,exr_text_range range,unsigned index,int print) {
  exr_content_anchor original={0},copy={0};exr_text_range_match match;exr_text_range restored;char *cfi=NULL,*again=NULL;
  OK(exr_anchor_from_range(p,&range,NULL,&original,&error));OK(exr_anchor_to_cfi(p,&original,NULL,&cfi,&error));
  OK(exr_anchor_from_cfi(p,cfi,NULL,&copy,&error));equal_endpoint(&original.start,&copy.start);equal_endpoint(&original.end,&copy.end);
  OK(exr_range_from_anchor(p,&copy,NULL,&match,&error));CHECK(match.state==EXR_ANCHOR_FOUND && same(range,match.range));
  OK(exr_range_from_cfi(p,cfi,NULL,&restored,&error));CHECK(same(range,restored));
  OK(exr_anchor_to_cfi(p,&copy,NULL,&again,&error));CHECK(!strcmp(cfi,again));
  if(print) printf("sample %u: %zu:%zu -> %zu:%zu %s\n",index,range.start.part,range.start.offset,range.end.part,range.end.offset,cfi);
  exr_free(cfi);exr_free(again);exr_content_anchor_free(&original);exr_content_anchor_free(&copy);
}
static void ranges(int cross) {
  exr_publication *p=fixture();size_t *a,*b,na,nb,i;unsigned total=cross ? 10 : 100;uint32_t seed=0x41ce2026;
  a=boundaries(p,0,&na);b=boundaries(p,cross ? 1 : 0,&nb);
  for(i=0;i<total;i++) {
    size_t start,end;exr_text_range r;
    seed=seed*1664525u+1013904223u;start=seed%na;seed=seed*1664525u+1013904223u;end=seed%nb;
    if(!cross && start>end) { size_t swap=start;start=end;end=swap; }
    r=(exr_text_range){{0,a[start]},{cross ? 1 : 0,b[end]}};roundtrip(p,r,(unsigned)i,1);
  }
  /* Entire part, collapsed start/end, and an empty chapter. */
  roundtrip(p,(exr_text_range){{0,0},{0,a[na-1]}},total,0);
  roundtrip(p,(exr_text_range){{0,0},{0,0}},total+1,0);
  roundtrip(p,(exr_text_range){{0,a[na-1]},{0,a[na-1]}},total+2,0);
  roundtrip(p,(exr_text_range){{2,0},{2,0}},total+3,0);
  printf("%s ranges: %u/%u = 100%%; anchor fields and both endpoints equal; 4 boundary cases\n",cross ? "cross-part" : "same-part",total,total);
  free(a);free(b);exr_publication_free(p);
}
static void contracts(void) {
  exr_publication *p=fixture();exr_text_range range;exr_content_anchor anchor={0};char *cfi=NULL;exr_control control={0};
  exr_cfi *parsed=NULL;exr_cfi_diagnostic diag;size_t n=65537;char *huge=malloc(n+1);CHECK(huge);memset(huge,'/',n);huge[n]=0;
  CHECK(exr_cfi_parse(huge,&parsed,&diag,&error)==EXR_LIMIT && diag.code==EXR_CFI_LIMIT && !parsed);free(huge);
  CHECK(exr_cfi_parse("/2[\xff]",&parsed,&diag,&error)==EXR_ENCODING && diag.code==EXR_CFI_ENCODING && diag.byte==3);
  CHECK(exr_cfi_parse("/2[\x01]",&parsed,&diag,&error)==EXR_ENCODING && !parsed);
  CHECK(exr_cfi_parse(NULL,&parsed,&diag,&error)==EXR_ARGUMENT && !parsed);
  { char *a=NULL,*b=NULL;
    OK(exr_cfi_parse("/6/4!/2,/2,/4",&parsed,NULL,&error));CHECK(exr_cfi_is_range(parsed));
    OK(exr_cfi_endpoints(parsed,&a,&b,&error));
    CHECK(!strcmp(a,"epubcfi(/6/4!/2/2)") && !strcmp(b,"epubcfi(/6/4!/2/4)"));
    exr_free(a);exr_free(b);exr_cfi_free(parsed);parsed=NULL; }
  CHECK(exr_range_from_cfi(p,"/6,/4!/4/2/1:3,/2!/4/2/1:0",NULL,&range,&error)==EXR_FORMAT && range.start.part==SIZE_MAX);
  CHECK(exr_range_from_cfi(p,"/6/99!/4",NULL,&range,&error)==EXR_FORMAT && range.end.part==SIZE_MAX);
  OK(exr_range_from_cfi(p,"/6/2!/4/2/1:2[;vnd.exr=x,y]",NULL,&range,&error));CHECK(same(range,(exr_text_range){{0,0},{0,0}}));
  OK(exr_range_from_cfi(p,"/6/2!/4/2/2/1:3",NULL,&range,&error));
  CHECK(range.start.offset==strlen("Alpha beta 中😀") && same(range,(exr_text_range){range.start,range.start}));
  OK(exr_range_from_cfi(p,"/6/2!/4/2/2/1:0[中😀,文]",NULL,&range,&error));
  CHECK(range.start.offset==strlen("Alpha beta 中😀"));
  control.cancelled=cancel;
  CHECK(exr_range_from_cfi(p,"/6/2!/4",&control,&range,&error)==EXR_CANCELLED && range.start.part==SIZE_MAX);
  range=(exr_text_range){{0,0},{1,1}};
  CHECK(exr_range_to_cfi(p,&range,&control,&cfi,&error)==EXR_CANCELLED && !cfi);
  CHECK(exr_anchor_from_cfi(p,"/6/2!/4",&control,&anchor,&error)==EXR_CANCELLED && !anchor.start.part_id);
  range=(exr_text_range){{1,1},{0,0}};CHECK(exr_range_to_cfi(p,&range,NULL,&cfi,&error)==EXR_ARGUMENT && !cfi);
  exr_publication_free(p);
}
static void real(const char *path) {
  exr_publication *p=NULL;size_t *a,*b,na,nb,i,count;const exr_part *parts;
  OK(exr_publication_open(path,&p,&error));
  parts=exr_publication_parts(p,&count);CHECK(parts && count>2);
  for(i=0;i<20;i++) {
    size_t part=1+i*(count-2)/20;
    a=boundaries(p,part,&na);b=boundaries(p,part,&nb);CHECK(na==nb);
    roundtrip(p,(exr_text_range){{part,a[(na-1)*(i+1)/21]},{part,b[(na-1)*(i+1)/21]}},(unsigned)i,1);free(a);free(b);
  }
  printf("real-book positions: 20/20 = 100%%\n");exr_publication_free(p);
}
int main(int argc,char **argv) {
  CHECK(argc>=2);
  if(!strcmp(argv[1],"parse")) { CHECK(argc==3);vectors(argv[2],0); }
  else if(!strcmp(argv[1],"invalid")) { CHECK(argc==3);vectors(argv[2],1); }
  else if(!strcmp(argv[1],"mapping")) mapping();
  else if(!strcmp(argv[1],"roundtrip")) ranges(0);
  else if(!strcmp(argv[1],"cross")) ranges(1);
  else if(!strcmp(argv[1],"contracts")) contracts();
  else if(!strcmp(argv[1],"real")) { CHECK(argc==3);real(argv[2]); }
  else CHECK(0);
  printf("%u checks passed\n",checks);return 0;
}
