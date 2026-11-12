/* SPDX-License-Identifier: MIT */
/* Hybrid-reference (/XRefStm) merge, Prev-chain and bad-offset cases, built in memory. */
#include "exreader.h"
#include "../src/pdf_internal.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static const char *scenario;
#define CHECK(x) do { if(!(x)) { fprintf(stderr,"%s line %d: %s (%d: %s)\n",scenario,__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
typedef struct { unsigned char data[8192]; size_t size; } blob;
static void put(blob *b,const void *s,size_t n) { CHECK(b->size+n<=sizeof(b->data)); memcpy(b->data+b->size,s,n); b->size+=n; }
static void text(blob *b,const char *s) { put(b,s,strlen(s)); }
static size_t object(blob *b,unsigned number,const char *body) {
  char head[32]; size_t at=b->size; snprintf(head,sizeof(head),"%u 0 obj\n",number); text(b,head); text(b,body); text(b,"\nendobj\n"); return at;
}
static void classic_row(blob *b,size_t offset,const char *kind) { char row[32]; snprintf(row,sizeof(row),"%010zu 00000 %s \n",offset,kind); text(b,row); }
/* One uncompressed xref stream (W [1 4 2]) holding `count` type-1 rows for the listed object numbers. */
static size_t xref_stream(blob *b,unsigned number,unsigned size,const unsigned *numbers,const size_t *offsets,unsigned count) {
  char head[256],index[128]="",piece[32]; unsigned char rows[64]; size_t at=b->size,n=0; unsigned i;
  for(i=0;i<count;i++) {
    snprintf(piece,sizeof(piece),"%u 1 ",numbers[i]); strcat(index,piece);
    rows[n++]=1; rows[n++]=(unsigned char)(offsets[i]>>24); rows[n++]=(unsigned char)(offsets[i]>>16);
    rows[n++]=(unsigned char)(offsets[i]>>8); rows[n++]=(unsigned char)offsets[i]; rows[n++]=0; rows[n++]=0;
  }
  snprintf(head,sizeof(head),"%u 0 obj\n<</Type/XRef/Size %u/W[1 4 2]/Index[%s]/Length %zu>>\nstream\n",number,size,index,n);
  text(b,head); put(b,rows,n); text(b,"\nendstream\nendobj\n"); return at;
}
static void begin(blob *b) { b->size=0; text(b,"%PDF-1.5\n%\x80\x81\x82\x83\n"); }
static void finish(blob *b,size_t xref) { char tail[64]; snprintf(tail,sizeof(tail),"startxref\n%zu\n%%%%EOF\n",xref); text(b,tail); }
static void expect_string(exr_pdf_file *file,uint32_t root,const char *key,const char *expected) {
  uint32_t out; size_t n; const unsigned char *bytes;
  OK(exr_pdf_resolve(file,exr_pdf_get(file,root,key),&out,&error)); CHECK(out!=EXR_PDF_NONE);
  bytes=exr_pdf_bytes(file,out,&n); CHECK(bytes && n==strlen(expected) && !memcmp(bytes,expected,n));
}
static exr_pdf_file *open_blob(blob *b) {
  exr_pdf_file *file=NULL; OK(exr_pdf_open(b->data,b->size,&file,&error)); CHECK(file && exr_pdf_root(file)!=EXR_PDF_NONE); return file;
}
/* Objects 1-3 plus a catalog whose keys A/B/C point at objects 4/5/6. */
static size_t base_objects(blob *b,size_t *offsets,const char *tag) {
  char catalog[160];
  snprintf(catalog,sizeof(catalog),"<</Type/Catalog/Pages 2 0 R/Tag(%s)/A 4 0 R/B 5 0 R/C 6 0 R>>",tag);
  offsets[1]=object(b,1,catalog); offsets[2]=object(b,2,"<</Type/Pages/Count 1/Kids[3 0 R]>>");
  offsets[3]=object(b,3,"<</Type/Page/Parent 2 0 R/MediaBox[0 0 10 10]>>"); return 0;
}
static void classic_table(blob *b,size_t first,const size_t *offsets,unsigned count,size_t size,size_t previous,size_t stream) {
  char trailer[160]; unsigned i; char head[32];
  snprintf(head,sizeof(head),"xref\n%zu %u\n",first,count); text(b,head);
  for(i=0;i<count;i++) { if(!first && !i) text(b,"0000000000 65535 f \n"); else classic_row(b,offsets[first+i],"n"); }
  snprintf(trailer,sizeof(trailer),"trailer\n<</Size %zu/Root 1 0 R",size); text(b,trailer);
  if(previous) { snprintf(trailer,sizeof(trailer),"/Prev %zu",previous); text(b,trailer); }
  snprintf(trailer,sizeof(trailer),"/XRefStm %zu>>\n",stream); text(b,trailer);
}
/* Classic table owns 4 and 5; the xref stream re-points 4 and adds 6. The stream wins on 4,
   the classic table keeps 5, and 6 is only reachable through the stream. */
static void merge(void) {
  blob b; size_t off[16]={0},xs,xref; unsigned numbers[2]={4,6}; size_t at[2]; exr_pdf_file *file;
  scenario="merge"; begin(&b); base_objects(&b,off,"merge");
  off[4]=object(&b,4,"(classic4)"); off[5]=object(&b,5,"(classic5)");
  at[0]=object(&b,4,"(stream4)"); at[1]=object(&b,6,"(stream6)");
  xs=xref_stream(&b,7,8,numbers,at,2); xref=b.size; classic_table(&b,0,off,6,8,0,xs); finish(&b,xref);
  file=open_blob(&b); {
    uint32_t root=exr_pdf_root(file);
    expect_string(file,root,"A","stream4"); expect_string(file,root,"B","classic5"); expect_string(file,root,"C","stream6");
  }
  exr_pdf_close(file);
}
/* The xref stream object number equals /Size, as Office writes it. */
static void size_quirk(void) {
  blob b; size_t off[16]={0},xs,xref; unsigned numbers[1]={4}; size_t at[1]; exr_pdf_file *file;
  scenario="size"; begin(&b); base_objects(&b,off,"size"); off[5]=object(&b,5,"(c5)"); at[0]=object(&b,4,"(s4)");
  xs=xref_stream(&b,6,6,numbers,at,1); xref=b.size; classic_table(&b,0,off,6,7,0,xs); finish(&b,xref);
  file=open_blob(&b); expect_string(file,exr_pdf_root(file),"A","s4"); exr_pdf_close(file);
}
/* Revision 2 is itself hybrid and chains to a classic revision 1 through /Prev. */
static void chain(void) {
  blob b; size_t off[16]={0},first,xs,xref,at[1]; unsigned numbers[1]={5}; exr_pdf_file *file;
  scenario="chain"; begin(&b); base_objects(&b,off,"rev1"); off[4]=object(&b,4,"(old4)");
  first=b.size; { unsigned i; text(&b,"xref\n0 5\n0000000000 65535 f \n"); for(i=1;i<5;i++) classic_row(&b,off[i],"n");
    text(&b,"trailer\n<</Size 7/Root 1 0 R>>\n"); }
  finish(&b,first);
  off[1]=object(&b,1,"<</Type/Catalog/Pages 2 0 R/Tag(rev2)/A 4 0 R/C 5 0 R>>"); at[0]=object(&b,5,"(stream5)");
  xs=xref_stream(&b,6,7,numbers,at,1); xref=b.size;
  { char row[64]; text(&b,"xref\n1 1\n"); classic_row(&b,off[1],"n");
    snprintf(row,sizeof(row),"trailer\n<</Size 7/Root 1 0 R/Prev %zu/XRefStm %zu>>\n",first,xs); text(&b,row); }
  finish(&b,xref);
  file=open_blob(&b); { uint32_t root=exr_pdf_root(file);
    expect_string(file,root,"Tag","rev2"); expect_string(file,root,"A","old4"); expect_string(file,root,"C","stream5"); }
  exr_pdf_close(file);
}
static void bad_offset(void) {
  size_t starts[]={5,0,64,SIZE_MAX}; unsigned i;
  scenario="bad-offset";
  for(i=0;i<sizeof(starts)/sizeof(*starts);i++) {
    blob b; size_t off[16]={0},xref; exr_pdf_file *file=(exr_pdf_file *)(uintptr_t)1; exr_status status;
    begin(&b); base_objects(&b,off,"bad"); off[4]=object(&b,4,"(x)"); off[5]=object(&b,5,"(x)"); xref=b.size;
    classic_table(&b,0,off,6,7,0,starts[i]==SIZE_MAX ? b.size+1000 : starts[i]); finish(&b,xref);
    status=exr_pdf_open(b.data,b.size,&file,&error);
    CHECK(status==EXR_FORMAT && !file && error.code==EXR_FORMAT && error.message[0]);
  }
}
int main(int argc,char **argv) {
  const char *name=argc>1 ? argv[1] : "";
  if(!strcmp(name,"merge")) { merge(); size_quirk(); }
  else if(!strcmp(name,"chain")) chain();
  else if(!strcmp(name,"bad-offset")) bad_offset();
  else return 2;
  puts("ok"); return 0;
}
