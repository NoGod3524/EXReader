/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static char pdf[262144]; static size_t size,offset[7];
static void add(const char *s) { size_t n=strlen(s); CHECK(n<sizeof(pdf)-size); memcpy(pdf+size,s,n); size+=n; pdf[size]=0; }
static void object(unsigned id,const char *body) { char head[40]; offset[id]=size; snprintf(head,sizeof(head),"%u 0 obj\n",id); add(head); add(body); add("\nendobj\n"); }
static void build(const char *annotations,const char *note,const char *text) {
  char row[128]; size_t xref; unsigned i; size=0; add("%PDF-1.7\n");
  object(1,"<< /Type /Catalog /Pages 2 0 R >>"); object(2,"<< /Type /Pages /Count 1 /Kids [3 0 R] >>"); object(3,"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 20 20] /Annots 4 0 R >>"); object(4,annotations); object(5,note); object(6,text);
  xref=size; add("xref\n0 7\n0000000000 65535 f \n"); for(i=1;i<=6;i++) { snprintf(row,sizeof(row),"%010zu 00000 n \n",offset[i]); add(row); }
  snprintf(row,sizeof(row),"trailer\n<< /Size 7 /Root 1 0 R >>\nstartxref\n%zu\n%%%%EOF\n",xref); add(row);
}
#define NOTE "<< /Type /Annot /Subtype /Highlight /NM (note-1) /Rect [12 8 1 2] /QuadPoints [1 8 12 8 1 2 12 2] /Contents 6 0 R /T (Author) /Subj (Subject) /CreationDate (D:20261017) /M (D:20261018) >>"
#define UNICODE "<FEFF4E2DD83DDE00>"
static int cancel(void *context) { return *(int *)context; }
static void stop(void *context,exr_stage stage,uint64_t done,uint64_t total) { (void)stage; if(done && done==total) *(int *)context=1; }
static void native(void) {
  exr_fixed_document *d=NULL; exr_page_annotation *a=NULL; size_t n,i; exr_bitmap bitmap; int stopped=0; exr_control control={cancel,stop,&stopped};
  build("[5 0 R null 99 0 R << /Subtype /Text /Rect [0 0 1 1] >>]",NOTE,UNICODE);
  OK(exr_fixed_open_memory(EXR_PDF,pdf,size,NULL,&d,&error)); OK(exr_fixed_load_annotations(d,0,NULL,&a,&n,&error)); CHECK(n==2);
  CHECK(!strcmp(a[0].id,"note-1") && !strcmp(a[0].kind,"Highlight") && a[0].bounds[0]==1 && a[0].bounds[2]==12 && a[0].quad_count==1 && a[0].quads[6]==12 && a[0].property_count==5);
  CHECK(!strcmp(a[0].properties[0].key,"http://purl.org/dc/terms/description") && !strcmp(a[0].properties[0].value,"\xe4\xb8\xad\xf0\x9f\x98\x80"));
  CHECK(!strcmp(a[1].id,"") && !strcmp(a[1].kind,"Text") && !a[1].quad_count && !a[1].property_count);
  { exr_page_annotation *other=NULL; size_t count; CHECK(exr_fixed_load_annotations(d,0,&control,&other,&count,&error)==EXR_CANCELLED && !other && !count); }
  exr_fixed_free(d); CHECK(!strcmp(a[0].properties[1].value,"Author") && a[0].quads[1]==8); exr_page_annotations_free(a,n);
  { const char *invalid[]={"<< /Rect [0 0 1 1] >>","<< /Subtype 1 /Rect [0 0 1 1] >>","<< /Subtype /Text /Rect [0 0 1] >>","<< /Subtype /Text /Rect [0 0 1 /bad] >>","<< /Subtype /Text /Rect [0 0 1 100000000.0] >>","<< /Subtype /Text /Rect [0 0 1 1] /QuadPoints [0 0] >>","<< /Subtype /Text /Rect [0 0 1 1] /Contents 4 >>"};
    for(i=0;i<sizeof(invalid)/sizeof(*invalid);i++) { build("[5 0 R]",invalid[i],UNICODE); OK(exr_fixed_open_memory(EXR_PDF,pdf,size,NULL,&d,&error)); CHECK(exr_fixed_load_annotations(d,0,NULL,&a,&n,&error)==EXR_FORMAT && !a && !n); OK(exr_fixed_render(d,0,1,NULL,&bitmap,&error)); exr_bitmap_free(&bitmap); CHECK(exr_fixed_load_annotations(d,0,NULL,&a,&n,&error)==EXR_FORMAT && !a); exr_fixed_free(d); }
  }
  /* PDF numbers have no exponent syntax. The malformed object cannot be read
     even to decide whether it contains an appearance stream. */
  build("[5 0 R]","<< /Subtype /Text /Rect [0 0 1 1e20] >>",UNICODE); OK(exr_fixed_open_memory(EXR_PDF,pdf,size,NULL,&d,&error));
  CHECK(exr_fixed_load_annotations(d,0,NULL,&a,&n,&error)==EXR_FORMAT && !a && !n);
  CHECK(exr_fixed_render(d,0,1,NULL,&bitmap,&error)==EXR_FORMAT && !bitmap.pixels && !bitmap.width && !bitmap.height); exr_fixed_free(d);
  build("[5 0 R]",NOTE,UNICODE); OK(exr_fixed_open_memory(EXR_PDF,pdf,size,NULL,&d,&error)); OK(exr_fixed_render(d,0,1,NULL,&bitmap,&error)); exr_bitmap_free(&bitmap); exr_fixed_free(d);
  build("42",NOTE,UNICODE); OK(exr_fixed_open_memory(EXR_PDF,pdf,size,NULL,&d,&error)); CHECK(exr_fixed_load_annotations(d,0,NULL,&a,&n,&error)==EXR_FORMAT && !a); exr_fixed_free(d);
  build("null",NOTE,UNICODE); OK(exr_fixed_open_memory(EXR_PDF,pdf,size,NULL,&d,&error)); OK(exr_fixed_load_annotations(d,0,NULL,&a,&n,&error)); CHECK(!a && !n); CHECK(exr_fixed_load_annotations(d,1,NULL,&a,&n,&error)==EXR_ARGUMENT && !a); exr_fixed_free(d);
  { char many[26000],*large=malloc(65539); size_t at=0; CHECK(large); many[at++]='['; for(i=0;i<4097;i++) { memcpy(many+at,"5 0 R ",6); at+=6; } strcpy(many+at,"]"); build(many,NOTE,UNICODE); OK(exr_fixed_open_memory(EXR_PDF,pdf,size,NULL,&d,&error)); CHECK(exr_fixed_load_annotations(d,0,NULL,&a,&n,&error)==EXR_LIMIT && !a); exr_fixed_free(d);
    large[0]='('; memset(large+1,'A',65536); strcpy(large+65537,")"); many[0]='['; at=1; for(i=0;i<130;i++) { memcpy(many+at,"5 0 R ",6); at+=6; } strcpy(many+at,"]"); build(many,NOTE,large); free(large); OK(exr_fixed_open_memory(EXR_PDF,pdf,size,NULL,&d,&error)); CHECK(exr_fixed_load_annotations(d,0,NULL,&a,&n,&error)==EXR_LIMIT && !a); exr_fixed_free(d);
  }
}
typedef struct { exr_fixed_document *d; exr_page_annotation entry; exr_metadata_entry property; double quad[8]; size_t count; int detail; } host;
static exr_status draw(void *context,size_t page,const double matrix[6],const exr_draw_sink *sink,const exr_control *control,exr_error *e) { (void)context;(void)page;(void)matrix;(void)sink;(void)control;(void)e;return EXR_OK; }
static exr_status provider(void *context,size_t page,const exr_control *control,const exr_page_annotation **out,size_t *count,exr_error *e) {
  host *h=context; exr_page_annotation *other=NULL; size_t n; (void)page;(void)control;
  CHECK(exr_fixed_load_annotations(h->d,0,NULL,&other,&n,e)==EXR_ARGUMENT && !other && !n); memset(e,0,sizeof(*e)); if(h->detail) { e->code=EXR_IO; strcpy(e->message,"host annotations failed"); }
  *out=&h->entry; *count=h->count; return EXR_OK;
}
static void generic(void) {
  host h={0}; exr_fixed_input input={0}; exr_fixed_page page={0}; exr_page_annotation *a=NULL; size_t n; int stopped=1; exr_control control={cancel,NULL,&stopped};
  page.geometry.bounds[2]=page.geometry.bounds[3]=10; page.geometry.unit_scale=1; input.struct_size=sizeof(input); input.pages=&page; input.page_count=1; input.draw=draw; input.annotations=provider; input.context=&h;
  h.count=1; h.entry.kind="host:custom"; h.entry.bounds[2]=h.entry.bounds[3]=1; h.entry.quads=h.quad; h.entry.quad_count=1; h.entry.properties=&h.property; h.entry.property_count=1; h.property=(exr_metadata_entry){"custom:key","Value"};
  OK(exr_fixed_create(&input,&h.d,&error)); CHECK(exr_fixed_load_annotations(h.d,0,&control,&a,&n,&error)==EXR_CANCELLED && !a && !n);
  OK(exr_fixed_load_annotations(h.d,0,NULL,&a,&n,&error)); h.quad[0]=5; h.property.value="Changed"; exr_fixed_free(h.d); CHECK(n==1 && a[0].quads[0]==0 && !strcmp(a[0].properties[0].value,"Value")); exr_page_annotations_free(a,n);
  OK(exr_fixed_create(&input,&h.d,&error)); h.entry.quad_count=SIZE_MAX; CHECK(exr_fixed_load_annotations(h.d,0,NULL,&a,&n,&error)==EXR_LIMIT && !a); h.entry.quad_count=1;
  h.quad[0]=NAN; CHECK(exr_fixed_load_annotations(h.d,0,NULL,&a,&n,&error)==EXR_FORMAT && !a); h.quad[0]=0;
  h.property.value="\xff"; CHECK(exr_fixed_load_annotations(h.d,0,NULL,&a,&n,&error)==EXR_ENCODING && !a); h.property.value="valid";
  h.detail=1; CHECK(exr_fixed_load_annotations(h.d,0,NULL,&a,&n,&error)==EXR_IO && !a && !strcmp(error.message,"host annotations failed")); h.detail=0;
  h.count=4097; CHECK(exr_fixed_load_annotations(h.d,0,NULL,&a,&n,&error)==EXR_LIMIT && !a); h.count=0; OK(exr_fixed_load_annotations(h.d,0,NULL,&a,&n,&error)); CHECK(!a && !n); exr_fixed_free(h.d);
  input.struct_size=offsetof(exr_fixed_input,annotations)+1; ((unsigned char *)&input)[offsetof(exr_fixed_input,annotations)]=1;
  CHECK(exr_fixed_create(&input,&h.d,&error)==EXR_ARGUMENT && !h.d); input.annotations=provider;
  input.struct_size=offsetof(exr_fixed_input,annotations); OK(exr_fixed_create(&input,&h.d,&error)); CHECK(exr_fixed_load_annotations(h.d,0,NULL,&a,&n,&error)==EXR_FORMAT && !a); exr_fixed_free(h.d);
}
int main(void) { native(); generic(); puts("Page annotation snapshots passed"); return 0; }
