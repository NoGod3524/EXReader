/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static char pdf[400000]; static size_t length,offsets[10],previous;
static void add(const char *text) { size_t n=strlen(text); CHECK(n<sizeof(pdf)-length); memcpy(pdf+length,text,n); length+=n; pdf[length]=0; }
static void object(unsigned id,const char *text) { char head[48]; offsets[id]=length; snprintf(head,sizeof(head),"%u 0 obj\n",id); add(head); add(text); add("\nendobj\n"); }
static void build(const char *info) {
  unsigned i; char row[120]; length=0; add("%PDF-2.0\n");
  object(1,"<< /Type /Catalog /Pages 2 0 R >>"); object(2,"<< /Type /Pages /Count 1 /Kids [3 0 R] >>"); object(3,"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 10 10] >>");
  object(4,info); object(5,"(An author)"); object(6,"<FEFF4E2DD83DDE00>");
  previous=length; add("xref\n0 7\n0000000000 65535 f \n");
  for(i=1;i<7;i++) { snprintf(row,sizeof(row),"%010zu 00000 n \n",offsets[i]); add(row); }
  snprintf(row,sizeof(row),"trailer\n<< /Size 7 /Root 1 0 R /Info 4 0 R >>\nstartxref\n%zu\n%%%%EOF\n",previous); add(row);
}
static void incremental(const char *info) {
  char row[256]; size_t xref; object(7,"<< /Title (New title) >>"); xref=length;
  snprintf(row,sizeof(row),"xref\n7 1\n%010zu 00000 n \ntrailer\n<< /Size 8 /Prev %zu %s >>\nstartxref\n%zu\n%%%%EOF\n",offsets[7],previous,info,xref); add(row);
}
static void stream_xref(void) {
  unsigned i,j; char head[256]; size_t xref;
  build("<< /Title (Stream title) >>"); length=previous; xref=length; offsets[7]=xref;
  snprintf(head,sizeof(head),"7 0 obj\n<< /Type /XRef /Size 8 /W [1 4 2] /Root 1 0 R /Info 4 0 R /Length 56 >>\nstream\n"); add(head);
  for(i=0;i<8;i++) { unsigned char row[7]={0}; row[0]=i ? 1 : 0; for(j=0;j<4;j++) row[1+j]=(unsigned char)((i ? offsets[i] : 0)>>(24-8*j)); if(!i) row[5]=row[6]=255; memcpy(pdf+length,row,7); length+=7; }
  add("\nendstream\nendobj\n"); snprintf(head,sizeof(head),"startxref\n%zu\n%%%%EOF\n",xref); add(head);
}
static const char *value(exr_metadata_entry *entries,size_t count,const char *key) { size_t i; for(i=0;i<count;i++) if(!strcmp(entries[i].key,key)) return entries[i].value; return NULL; }
#define TITLE "http://purl.org/dc/terms/title"
#define AUTHOR "http://purl.org/dc/terms/creator"
static void title(const char *expected) {
  exr_fixed_document *d=NULL; exr_metadata_entry *entries=NULL; size_t count;
  OK(exr_fixed_open_memory(EXR_PDF,pdf,length,NULL,&d,&error)); OK(exr_fixed_load_metadata(d,NULL,&entries,&count,&error)); exr_fixed_free(d);
  if(expected) CHECK(value(entries,count,TITLE) && !strcmp(value(entries,count,TITLE),expected)); else CHECK(!count);
  exr_metadata_free(entries,count);
}
static int cancel(void *context) { return *(int *)context; }
static void stop(void *context,exr_stage stage,uint64_t done,uint64_t total) { (void)stage; if(done && done==total) *(int *)context=1; }
static void pdf_metadata(void) {
  exr_fixed_document *d=NULL; exr_metadata_entry *entries=NULL; size_t count; exr_bitmap bitmap; int stopped=1; exr_control control={cancel,NULL,&stopped};
  const char *invalid[]={"<< /Title <FEFF00> >>","<< /Title <FEFFD800> >>","<< /Title <FEFFDC00> >>","<< /Title <FEFFD8000041> >>","<< /Title <EFBBBFFF> >>","<< /Title <7F> >>","<< /Title <9F> >>","<< /Title <AD> >>","<< /Title <00> >>","<< /Title 5 >>","5"}; size_t i;
  build("<< /Title 6 0 R /Author 5 0 R /Subject (Description) /Keywords <8018A0> /Creator () /Producer (Tool) /CreationDate (D:20261017120000Z) /ModDate null >>");
  OK(exr_fixed_open_memory(EXR_PDF,pdf,length,NULL,&d,&error));
  CHECK(exr_fixed_load_metadata(d,&control,&entries,&count,&error)==EXR_CANCELLED && !entries && !count); stopped=0;
  OK(exr_fixed_load_metadata(d,NULL,&entries,&count,&error)); CHECK(count==7 && !strcmp(value(entries,count,TITLE),"\xe4\xb8\xad\xf0\x9f\x98\x80") && !strcmp(value(entries,count,AUTHOR),"An author"));
  CHECK(!strcmp(value(entries,count,"http://ns.adobe.com/pdf/1.3/Keywords"),"\xe2\x80\xa2\xcb\x98\xe2\x82\xac"));
  { exr_metadata_entry *other=NULL; size_t n=0; control.progress=stop; CHECK(exr_fixed_load_metadata(d,&control,&other,&n,&error)==EXR_CANCELLED && !other && !n); }
  exr_fixed_free(d); CHECK(!strcmp(value(entries,count,AUTHOR),"An author")); exr_metadata_free(entries,count);
  build("<< /Title <EFBBBFE4B8ADF09F9880> >>"); title("\xe4\xb8\xad\xf0\x9f\x98\x80");
  build("<< /Title (Original) >>"); incremental(""); title("Original");
  build("<< /Title (Original) >>"); incremental("/Info 7 0 R"); title("New title");
  build("<< /Title (Original) >>"); incremental("/Info null"); title(NULL);
  stream_xref(); title("Stream title");
  build("<< /Title 99 0 R >>"); title(NULL); /* Undefined references are PDF null. */
  for(i=0;i<sizeof(invalid)/sizeof(*invalid);i++) {
    build(invalid[i]); OK(exr_fixed_open_memory(EXR_PDF,pdf,length,NULL,&d,&error));
    CHECK(exr_fixed_load_metadata(d,NULL,&entries,&count,&error)==EXR_FORMAT && !entries && !count);
    OK(exr_fixed_render(d,0,1,NULL,&bitmap,&error)); exr_bitmap_free(&bitmap);
    CHECK(exr_fixed_load_metadata(d,NULL,&entries,&count,&error)==EXR_FORMAT && !entries); exr_fixed_free(d);
  }
  { char *large=malloc(70050); CHECK(large); strcpy(large,"<< /Title ("); memset(large+11,'A',70000); strcpy(large+70011,") >>"); build(large); free(large); OK(exr_fixed_open_memory(EXR_PDF,pdf,length,NULL,&d,&error)); CHECK(exr_fixed_load_metadata(d,NULL,&entries,&count,&error)==EXR_LIMIT && !entries); exr_fixed_free(d); }
}
typedef struct { exr_fixed_document *d; exr_metadata_entry entries[130]; size_t count; int null,detail; } provider;
static exr_status draw(void *context,size_t page,const double matrix[6],const exr_draw_sink *sink,const exr_control *control,exr_error *e) { (void)context; (void)page; (void)matrix; (void)sink; (void)control; (void)e; return EXR_OK; }
static exr_status metadata(void *context,const exr_control *control,const exr_metadata_entry **out,size_t *count,exr_error *e) {
  provider *p=context; exr_metadata_entry *entries=NULL; size_t n; (void)control;
  CHECK(exr_fixed_load_metadata(p->d,NULL,&entries,&n,e)==EXR_ARGUMENT && !entries && !n);
  memset(e,0,sizeof(*e)); if(p->detail) { e->code=EXR_IO; strcpy(e->message,"provider detail"); }
  *out=p->null ? NULL : p->entries; *count=p->count; return EXR_OK;
}
static void generic(void) {
  provider p={0}; exr_fixed_input input={0}; exr_fixed_page page={0}; exr_metadata_entry *entries=NULL; size_t n;
  page.geometry.bounds[2]=page.geometry.bounds[3]=10; page.geometry.unit_scale=1;
  input.struct_size=sizeof(input); input.pages=&page; input.page_count=1; input.draw=draw; input.metadata=metadata; input.context=&p;
  p.entries[0]=(exr_metadata_entry){"custom:key","A value"}; p.entries[1]=(exr_metadata_entry){"custom:key","Another value"}; p.count=2;
  OK(exr_fixed_create(&input,&p.d,&error)); OK(exr_fixed_load_metadata(p.d,NULL,&entries,&n,&error)); CHECK(n==2);
  p.entries[0].value="Replaced"; exr_fixed_free(p.d); CHECK(!strcmp(entries[0].value,"A value") && !strcmp(entries[1].key,"custom:key")); exr_metadata_free(entries,n);
  OK(exr_fixed_create(&input,&p.d,&error)); p.null=1; CHECK(exr_fixed_load_metadata(p.d,NULL,&entries,&n,&error)==EXR_FORMAT && !entries && !n); p.null=0;
  p.count=4097; CHECK(exr_fixed_load_metadata(p.d,NULL,&entries,&n,&error)==EXR_LIMIT && !entries); p.count=2;
  p.entries[0].key=""; CHECK(exr_fixed_load_metadata(p.d,NULL,&entries,&n,&error)==EXR_FORMAT && !entries); p.entries[0].key="custom:key";
  p.entries[0].value="\xff"; CHECK(exr_fixed_load_metadata(p.d,NULL,&entries,&n,&error)==EXR_ENCODING && !entries); p.entries[0].value="Valid";
  p.detail=1; CHECK(exr_fixed_load_metadata(p.d,NULL,&entries,&n,&error)==EXR_IO && !strcmp(error.message,"provider detail")); p.detail=0;
  { char *large=malloc(65537); size_t i; CHECK(large); memset(large,'A',65536); large[65536]=0;
    for(i=0;i<130;i++) p.entries[i]=(exr_metadata_entry){"key",large}; p.count=130;
    CHECK(exr_fixed_load_metadata(p.d,NULL,&entries,&n,&error)==EXR_LIMIT && !entries && !n); free(large);
  }
  p.count=0; OK(exr_fixed_load_metadata(p.d,NULL,&entries,&n,&error)); CHECK(!entries && !n); exr_fixed_free(p.d);
  input.struct_size=offsetof(exr_fixed_input,metadata)+1; ((unsigned char *)&input)[offsetof(exr_fixed_input,metadata)]=1;
  CHECK(exr_fixed_create(&input,&p.d,&error)==EXR_ARGUMENT && !p.d); input.metadata=metadata;
  input.struct_size=offsetof(exr_fixed_input,metadata); OK(exr_fixed_create(&input,&p.d,&error)); CHECK(exr_fixed_load_metadata(p.d,NULL,&entries,&n,&error)==EXR_FORMAT && !entries); exr_fixed_free(p.d);
}
static void library(const char *path) {
  exr_library *l=NULL; int64_t id; exr_book *books=NULL; size_t count; remove(path);
  build("<< /Title (PDF title) /Author 5 0 R >>"); OK(exr_library_open(path,&l,&error)); OK(exr_library_import(l,EXR_PDF,pdf,length,NULL,&id,&error)); OK(exr_library_books(l,NULL,&books,&count,&error)); CHECK(count==1 && !strcmp(books[0].title,"PDF title") && !strcmp(books[0].author,"An author")); exr_books_free(books,count);
  OK(exr_library_import(l,EXR_PDF,pdf,length,"Host title",&id,&error)); OK(exr_library_books(l,"Host title",&books,&count,&error)); CHECK(count==1 && !strcmp(books[0].title,"Host title") && !strcmp(books[0].author,"An author")); exr_books_free(books,count);
  build("<< /Title 3 >>"); CHECK(exr_library_import(l,EXR_PDF,pdf,length,NULL,&id,&error)==EXR_FORMAT && !id); OK(exr_library_books(l,NULL,&books,&count,&error)); CHECK(count==2); exr_books_free(books,count); exr_library_close(l); remove(path);
}
int main(int argc,char **argv) { char path[4096]; CHECK(argc==2); snprintf(path,sizeof(path),"%s/metadata-library.sqlite",argv[1]); pdf_metadata(); generic(); library(path); printf("%u metadata checks passed\n",checks); return 0; }
