/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

static exr_error error;
static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
#define DESCRIPTION "http://purl.org/dc/terms/description"
#define CREATOR "http://purl.org/dc/terms/creator"
#define SUBJECT "http://purl.org/dc/terms/subject"
#define CREATED "http://ns.adobe.com/xap/1.0/CreateDate"
#define MODIFIED "http://ns.adobe.com/xap/1.0/ModifyDate"
#define HUGE_REAL "1000000000000000000000000000000000000000000000000000000000000.0"

static unsigned char pdf[131072];
static size_t length,offset[16];
static unsigned generation[16];
static void raw(const void *data,size_t size) {
  CHECK(size<sizeof(pdf)-length); memcpy(pdf+length,data,size); length+=size; pdf[length]=0;
}
static void add(const char *text) { raw(text,strlen(text)); }
static void object(unsigned id,unsigned gen,const char *body) {
  char row[80]; offset[id]=length; generation[id]=gen;
  snprintf(row,sizeof(row),"%u %u obj\n",id,gen); add(row); add(body); add("\nendobj\n");
}
static void begin(void) { length=0; memset(offset,0,sizeof(offset)); memset(generation,0,sizeof(generation)); add("%PDF-1.7\n"); }
static void finish(unsigned objects,const char *trailer) {
  char row[512]; size_t xref=length; unsigned i;
  snprintf(row,sizeof(row),"xref\n0 %u\n0000000000 65535 f \n",objects); add(row);
  for(i=1;i<objects;i++) { snprintf(row,sizeof(row),"%010zu %05u n \n",offset[i],generation[i]); add(row); }
  snprintf(row,sizeof(row),"trailer\n<< /Size %u /Root 1 0 R %s >>\nstartxref\n%zu\n%%%%EOF\n",objects,trailer,xref); add(row);
}
static void classic(const char *annotations,const char *note,unsigned page_gen) {
  char row[2048]; begin();
  object(1,0,"<< /Type /Catalog /Pages 2 0 R /Custom (catalog untouched) >>");
  snprintf(row,sizeof(row),"<< /Type /Pages /Count 1 /Kids [3 %u R] >>",page_gen); object(2,0,row);
  snprintf(row,sizeof(row),"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 40 40] /Annots 4 2 R /Payload << /Annots (nested-value) /Tiny 0.00000000125 /Huge " HUGE_REAL " /Big 999999.25 /Weird /A#00B#23 >> >>"); object(3,page_gen,row);
  object(4,2,annotations);
  object(5,4,note);
  object(6,0,"<< /Title (Original title) /Author (Original author) >>");
  finish(7,"/Info 6 0 R /ID [<002380FF> <FEFF0041>]");
}
#define EXISTING "<< /Type /Annot /Subtype /Text /NM (keep) /Rect [30 30 38 38] /Contents (Existing) /Vendor << /Annots (annotation-nested) /Token <00FF23> >> >>"

static void xref_row(unsigned type,size_t first,unsigned second) {
  unsigned char row[7]; row[0]=(unsigned char)type;
  row[1]=(unsigned char)(first>>24); row[2]=(unsigned char)(first>>16);
  row[3]=(unsigned char)(first>>8); row[4]=(unsigned char)first;
  row[5]=(unsigned char)(second>>8); row[6]=(unsigned char)second; raw(row,sizeof(row));
}
static void compressed(void) {
  static const char *body[]={
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 40 40] /Annots [4 0 R] /Payload << /Annots (compressed-nested) >> >>"
  };
  char header[128],row[256]; size_t i,at=0,first,stream_size,xref;
  begin(); object(4,0,EXISTING);
  header[0]=0;
  for(i=0;i<3;i++) { size_t used=strlen(header); snprintf(header+used,sizeof(header)-used,"%u %zu ",(unsigned)i+1,at); at+=strlen(body[i])+1; }
  first=strlen(header); stream_size=first+at; offset[5]=length;
  snprintf(row,sizeof(row),"5 0 obj\n<< /Type /ObjStm /N 3 /First %zu /Length %zu >>\nstream\n",first,stream_size); add(row); add(header);
  for(i=0;i<3;i++) { add(body[i]); add("\n"); } add("\nendstream\nendobj\n");
  xref=length; offset[6]=xref;
  add("6 0 obj\n<< /Type /XRef /Size 7 /Root 1 0 R /Info << /Title (Compressed title) /Vendor /Info#23Name >> /ID [<002380FF> <FEFF0041>] /W [1 4 2] /Length 49 >>\nstream\n");
  xref_row(0,0,65535); for(i=0;i<3;i++) xref_row(2,5,(unsigned)i);
  for(i=4;i<7;i++) xref_row(1,offset[i],0);
  add("\nendstream\nendobj\n"); snprintf(row,sizeof(row),"startxref\n%zu\n%%%%EOF\n",xref); add(row);
}
static int contains(const void *data,size_t size,const char *text) {
  const unsigned char *bytes=data; size_t n=strlen(text),i;
  for(i=0;n<=size && i<=size-n;i++) if(!memcmp(bytes+i,text,n)) return 1;
  return 0;
}
static int cancelled(void *context) { return *(int *)context; }
static void final_stop(void *context,exr_stage stage,uint64_t done,uint64_t total) {
  (void)stage; if(done && done==total) *(int *)context=1;
}
static exr_page_annotation note(const char *id,const char *kind) {
  exr_page_annotation a={0}; a.id=id; a.kind=kind;
  a.bounds[0]=4; a.bounds[1]=4; a.bounds[2]=26; a.bounds[3]=18; return a;
}
static exr_page_annotation *annotations(const void *data,size_t size,size_t *count) {
  exr_fixed_document *document=NULL; exr_page_annotation *a=NULL;
  OK(exr_fixed_open_memory(EXR_PDF,data,size,NULL,&document,&error));
  OK(exr_fixed_load_annotations(document,0,NULL,&a,count,&error)); exr_fixed_free(document); return a;
}
static const exr_page_annotation *named(const exr_page_annotation *a,size_t n,const char *id) {
  size_t i; for(i=0;i<n;i++) if(a[i].id && !strcmp(a[i].id,id)) return a+i; return NULL;
}
static const char *property(const exr_page_annotation *a,const char *key) {
  size_t i; for(i=0;i<a->property_count;i++) if(!strcmp(a->properties[i].key,key)) return a->properties[i].value; return NULL;
}
static void title(const void *data,size_t size,const char *expected) {
  exr_fixed_document *document=NULL; exr_metadata_entry *entries=NULL; size_t n,i; int found=0;
  OK(exr_fixed_open_memory(EXR_PDF,data,size,NULL,&document,&error));
  OK(exr_fixed_load_metadata(document,NULL,&entries,&n,&error));
  for(i=0;i<n;i++) if(!strcmp(entries[i].key,"http://purl.org/dc/terms/title")) { CHECK(!strcmp(entries[i].value,expected)); found=1; }
  CHECK(found); exr_metadata_free(entries,n); exr_fixed_free(document);
}
static unsigned colored(const void *data,size_t size) {
  exr_fixed_document *document=NULL; exr_bitmap image={0}; unsigned found=0; size_t x,y;
  OK(exr_fixed_open_memory(EXR_PDF,data,size,NULL,&document,&error));
  OK(exr_fixed_render(document,0,1,NULL,&image,&error)); CHECK(image.width==40 && image.height==40 && image.channels==4);
  for(y=0;y<image.height;y++) for(x=0;x<image.width;x++) {
    const unsigned char *p=image.pixels+y*image.stride+x*4;
    if(p[0]!=255 || p[1]!=255 || p[2]!=255) found++;
  }
  exr_bitmap_free(&image); exr_fixed_free(document); return found;
}
static void prefix(const void *output,size_t size,const void *input,size_t input_size) {
  CHECK(output && size>input_size && !memcmp(output,input,input_size));
}
static void save(const char *directory,const char *name,const void *data,size_t size) {
  char path[4096]; FILE *f;
  if(!directory) return;
  snprintf(path,sizeof(path),"%s/%s",directory,name); f=fopen(path,"wb"); CHECK(f); CHECK(fwrite(data,1,size,f)==size); CHECK(!fclose(f));
}
static void roundtrip(const char *directory,int compressed_input) {
  static const double quad[]={4,18,26,18,4,4,26,4};
  static const exr_metadata_entry properties[]={
    {DESCRIPTION,"Chinese: \xe4\xb8\xad\xe6\x96\x87; emoji \xf0\x9f\x98\x80 (a) \\ \n"},
    {CREATOR,"Writer"},{SUBJECT,"Review"},{CREATED,"D:20261017090000Z"},{MODIFIED,"D:20261017100000Z"}
  };
  exr_page_annotation a=note("reader-highlight","Highlight"),*loaded; const exr_page_annotation *entry;
  exr_pdf_annotation_write_options options={0}; void *first=NULL,*second=NULL,*third=NULL,*removed=NULL;
  size_t first_size=0,second_size=0,third_size=0,removed_size=0,n; unsigned before;
  if(compressed_input) compressed(); else classic("[5 4 R]",EXISTING,7);
  before=colored(pdf,length); a.quads=quad; a.quad_count=1; a.properties=properties; a.property_count=5;
  options.struct_size=sizeof(options); options.color=0xff0000; options.opacity=.5;
  OK(exr_pdf_annotation_write(pdf,length,0,&a,&options,&first,&first_size,&error)); prefix(first,first_size,pdf,length);
  CHECK(colored(first,first_size)>before); loaded=annotations(first,first_size,&n); CHECK(n==2);
  entry=named(loaded,n,"reader-highlight"); CHECK(entry && !strcmp(entry->kind,"Highlight") && entry->quad_count==1);
  CHECK(!memcmp(entry->bounds,a.bounds,sizeof(a.bounds)) && !memcmp(entry->quads,quad,sizeof(quad)) && entry->property_count==5);
  CHECK(!strcmp(property(entry,DESCRIPTION),properties[0].value) && !strcmp(property(entry,CREATOR),"Writer") && !strcmp(property(entry,MODIFIED),properties[4].value));
  CHECK(named(loaded,n,"keep")); exr_page_annotations_free(loaded,n);
  title(first,first_size,compressed_input ? "Compressed title" : "Original title");
  CHECK(contains((const unsigned char *)first+length,first_size-length,"/ID") && contains((const unsigned char *)first+length,first_size-length,"002380FF"));
  CHECK(contains((const unsigned char *)first+length,first_size-length,compressed_input ? "636F6D707265737365642D6E6573746564" : "6E65737465642D76616C7565"));
  if(!compressed_input) CHECK(contains((const unsigned char *)first+length,first_size-length,"0.00000000125") && contains((const unsigned char *)first+length,first_size-length,HUGE_REAL) && contains((const unsigned char *)first+length,first_size-length,"/A#00B#23"));
  save(directory,compressed_input ? "pdf-write-compressed.pdf" : "pdf-write-classic.pdf",first,first_size);
  /* Updating an original indirect annotation must preserve its unknown keys. */
  a=note("keep","Text"); a.properties=properties; a.property_count=1;
  OK(exr_pdf_annotation_write(first,first_size,0,&a,NULL,&second,&second_size,&error)); prefix(second,second_size,first,first_size);
  loaded=annotations(second,second_size,&n); CHECK(n==2); entry=named(loaded,n,"keep");
  CHECK(entry && !strcmp(entry->kind,"Text") && !strcmp(property(entry,DESCRIPTION),properties[0].value)); exr_page_annotations_free(loaded,n);
  CHECK(contains((const unsigned char *)second+first_size,second_size-first_size,"/Vendor") && contains((const unsigned char *)second+first_size,second_size-first_size,"616E6E6F746174696F6E2D6E6573746564"));
  CHECK(colored(second,second_size)>0);
  /* Upsert keeps one NM record across an incremental chain. */
  a.bounds[0]=10; a.bounds[1]=10; a.bounds[2]=20; a.bounds[3]=24;
  OK(exr_pdf_annotation_write(second,second_size,0,&a,NULL,&third,&third_size,&error)); prefix(third,third_size,second,second_size);
  loaded=annotations(third,third_size,&n); CHECK(n==2); entry=named(loaded,n,"keep"); CHECK(entry && entry->bounds[0]==10 && entry->bounds[3]==24); exr_page_annotations_free(loaded,n);
  if(!compressed_input) CHECK(contains((const unsigned char *)third+second_size,third_size-second_size,"0.00000000125") && contains((const unsigned char *)third+second_size,third_size-second_size,HUGE_REAL));
  OK(exr_pdf_annotation_remove(third,third_size,0,"reader-highlight",NULL,&removed,&removed_size,&error)); prefix(removed,removed_size,third,third_size);
  loaded=annotations(removed,removed_size,&n); CHECK(n==1 && named(loaded,n,"keep")); exr_page_annotations_free(loaded,n);
  title(removed,removed_size,compressed_input ? "Compressed title" : "Original title"); save(directory,compressed_input ? "pdf-write-removed-compressed.pdf" : "pdf-write-removed.pdf",removed,removed_size);
  exr_free(first); exr_free(second); exr_free(third); exr_free(removed);
}

static void failure(exr_status expected,const exr_page_annotation *a,const exr_pdf_annotation_write_options *options,size_t page) {
  void *out=(void *)(uintptr_t)1; size_t size=123; exr_status status=exr_pdf_annotation_write(pdf,length,page,a,options,&out,&size,&error);
  CHECK(status==expected && error.code==expected && !out && !size && error.message[0]);
}
static void invalid(void) {
  static const double quad[]={4,18,26,18,4,4,26,4};
  double invalid_quad[8];
  char oversized[32769];
  exr_page_annotation a=note("new","Text"); exr_metadata_entry p={"unknown:property","value"};
  exr_pdf_annotation_write_options options={0}; void *out; size_t size; int stop=1;
  exr_control control={cancelled,NULL,&stop};
  classic("[5 4 R]",EXISTING,0);
  out=(void *)(uintptr_t)1; size=123;
  CHECK(exr_pdf_annotation_write(NULL,length,0,&a,NULL,&out,&size,&error)==EXR_ARGUMENT && !out && !size);
  out=(void *)(uintptr_t)1; size=123;
  CHECK(exr_pdf_annotation_write(pdf,0,0,&a,NULL,&out,&size,&error)==EXR_ARGUMENT && !out && !size);
  size=123; CHECK(exr_pdf_annotation_write(pdf,length,0,&a,NULL,NULL,&size,&error)==EXR_ARGUMENT && !size);
  out=(void *)(uintptr_t)1; CHECK(exr_pdf_annotation_write(pdf,length,0,&a,NULL,&out,NULL,&error)==EXR_ARGUMENT && !out);
  failure(EXR_ARGUMENT,NULL,NULL,0); failure(EXR_ARGUMENT,&a,NULL,1);
  a.id=""; failure(EXR_ARGUMENT,&a,NULL,0); a.id=NULL; failure(EXR_ARGUMENT,&a,NULL,0); a.id="new";
  a.kind="Ink"; failure(EXR_ARGUMENT,&a,NULL,0); a.kind="Text";
  a.id="\xff"; failure(EXR_ENCODING,&a,NULL,0); a.id="new";
  a.bounds[0]=NAN; failure(EXR_ARGUMENT,&a,NULL,0); a.bounds[0]=4;
  a.bounds[2]=a.bounds[0]; failure(EXR_ARGUMENT,&a,NULL,0); a.bounds[2]=26;
  a.bounds[0]=1e8; failure(EXR_ARGUMENT,&a,NULL,0); a.bounds[0]=4;
  a.bounds[0]=-1e7; a.bounds[2]=1e7; failure(EXR_ARGUMENT,&a,NULL,0); a.bounds[0]=4; a.bounds[2]=26;
  a.quads=quad; a.quad_count=1; failure(EXR_ARGUMENT,&a,NULL,0); a.quads=NULL; a.quad_count=0;
  a.kind="Highlight"; failure(EXR_ARGUMENT,&a,NULL,0); a.quad_count=1; failure(EXR_ARGUMENT,&a,NULL,0); a.quad_count=0; a.kind="Text";
  a.kind="Highlight"; a.quads=quad; a.quad_count=32769; failure(EXR_LIMIT,&a,NULL,0); a.quads=NULL; a.quad_count=0;
  a.kind="Highlight"; a.quads=invalid_quad; a.quad_count=1; memcpy(invalid_quad,quad,sizeof(quad));
  invalid_quad[0]=NAN; failure(EXR_ARGUMENT,&a,NULL,0); invalid_quad[0]=3; failure(EXR_ARGUMENT,&a,NULL,0);
  memcpy(invalid_quad,quad,sizeof(quad)); invalid_quad[6]=4; invalid_quad[7]=4; failure(EXR_ARGUMENT,&a,NULL,0);
  a.kind="Text"; a.quads=NULL; a.quad_count=0;
  a.properties=&p; a.property_count=1; failure(EXR_ARGUMENT,&a,NULL,0);
  p.key=DESCRIPTION; p.value="\xff"; failure(EXR_ENCODING,&a,NULL,0); a.properties=NULL; a.property_count=0;
  memset(oversized,'A',sizeof(oversized)-1); oversized[sizeof(oversized)-1]=0;
  a.properties=&p; a.property_count=1; p.value=oversized; failure(EXR_LIMIT,&a,NULL,0); a.properties=NULL; a.property_count=0;
  a.id=oversized; failure(EXR_LIMIT,&a,NULL,0); a.id="new";
  { exr_metadata_entry duplicate[]={{DESCRIPTION,"first"},{DESCRIPTION,"second"}};
    a.properties=duplicate; a.property_count=2; failure(EXR_ARGUMENT,&a,NULL,0); a.properties=NULL; a.property_count=0;
  }
  options.struct_size=1; failure(EXR_ARGUMENT,&a,&options,0); options.struct_size=sizeof(options);
  options.opacity=NAN; failure(EXR_ARGUMENT,&a,&options,0); options.opacity=-.1; failure(EXR_ARGUMENT,&a,&options,0); options.opacity=1.1; failure(EXR_ARGUMENT,&a,&options,0);
  options.opacity=.5; options.color=0xff000000; failure(EXR_ARGUMENT,&a,&options,0); options.color=0xffff00; options.control=control; failure(EXR_CANCELLED,&a,&options,0);
  stop=0; options.control.progress=final_stop; failure(EXR_CANCELLED,&a,&options,0);
  out=(void *)(uintptr_t)1; size=123; CHECK(exr_pdf_annotation_remove(pdf,length,0,"keep",&control,&out,&size,&error)==EXR_CANCELLED && !out && !size);
  out=(void *)(uintptr_t)1; size=123; CHECK(exr_pdf_annotation_remove(pdf,length,0,"",NULL,&out,&size,&error)==EXR_ARGUMENT && !out && !size);
  /* A duplicate NM is ambiguous; the editor must not silently choose one. */
  classic("[5 4 R << /Subtype /Text /NM (keep) /Rect [1 1 3 3] >>]",EXISTING,0); a.id="keep";
  failure(EXR_FORMAT,&a,NULL,0); out=(void *)(uintptr_t)1; size=123;
  CHECK(exr_pdf_annotation_remove(pdf,length,0,"keep",NULL,&out,&size,&error)==EXR_FORMAT && !out && !size);
}
static void edgecases(void) {
  exr_page_annotation a=note("direct","Text"),*loaded; void *out=NULL,*removed=NULL; size_t size=0,removed_size=0,n;
  exr_pdf_annotation_write_options defaults=exr_pdf_annotation_write_defaults();
  struct { exr_pdf_annotation_write_options base; unsigned char extra[8]; } extended;
  CHECK(defaults.struct_size==sizeof(defaults) && defaults.color==0xffff00 && defaults.opacity==.35 && !defaults.control.cancelled && !defaults.control.progress && !defaults.control.context);
  classic("[<< /Subtype /Text /NM (direct) /Rect [1 1 3 3] /Vendor (direct-preserved) >>]",EXISTING,0);
  memset(&extended,0,sizeof(extended)); extended.base=defaults; extended.base.struct_size=sizeof(extended); extended.extra[7]=1;
  failure(EXR_ARGUMENT,&a,&extended.base,0); extended.extra[7]=0;
  OK(exr_pdf_annotation_write(pdf,length,0,&a,&extended.base,&out,&size,&error)); exr_free(out); out=NULL;
  extended.base.struct_size=4097; failure(EXR_ARGUMENT,&a,&extended.base,0);
  pdf[7]='3'; failure(EXR_FORMAT,&a,NULL,0);
  OK(exr_pdf_annotation_remove(pdf,length,0,"direct",NULL,&out,&size,&error)); loaded=annotations(out,size,&n); CHECK(!loaded && !n); exr_free(out); out=NULL; pdf[7]='7';
  OK(exr_pdf_annotation_remove(pdf,length,0,"absent",NULL,&out,&size,&error));
  CHECK(out && out!=pdf && size==length && !memcmp(out,pdf,length)); exr_free(out); out=NULL;
  OK(exr_pdf_annotation_write(pdf,length,0,&a,NULL,&out,&size,&error));
  loaded=annotations(out,size,&n); CHECK(n==1 && !strcmp(loaded[0].id,"direct") && loaded[0].bounds[0]==4); exr_page_annotations_free(loaded,n);
  CHECK(contains((const unsigned char *)out+length,size-length,"6469726563742D707265736572766564"));
  OK(exr_pdf_annotation_remove(out,size,0,"direct",NULL,&removed,&removed_size,&error));
  loaded=annotations(removed,removed_size,&n); CHECK(!loaded && !n && !colored(removed,removed_size)); exr_free(out); exr_free(removed); out=removed=NULL;
  classic("null",EXISTING,0);
  OK(exr_pdf_annotation_write(pdf,length,0,&a,NULL,&out,&size,&error)); loaded=annotations(out,size,&n);
  CHECK(n==1 && !strcmp(loaded[0].id,"direct")); exr_page_annotations_free(loaded,n); exr_free(out); out=NULL;
  classic("[5 4 R << /Subtype /Popup /NM (popup) /Rect [1 1 3 3] /Parent 5 4 R >> << /Subtype /Text /NM (other) /Rect [1 1 3 3] >>]",EXISTING,0);
  OK(exr_pdf_annotation_remove(pdf,length,0,"keep",NULL,&out,&size,&error)); loaded=annotations(out,size,&n);
  CHECK(n==1 && !strcmp(loaded[0].id,"other")); exr_page_annotations_free(loaded,n); exr_free(out);
  /* An invalid Popup pointer must not delete an unrelated Text annotation. */
  begin(); object(1,0,"<< /Type /Catalog /Pages 2 0 R >>"); object(2,0,"<< /Type /Pages /Count 1 /Kids [3 0 R] >>");
  object(3,0,"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 40 40] /Annots 4 0 R >>"); object(4,0,"[5 0 R 6 0 R]");
  object(5,0,"<< /Subtype /Text /NM (keep) /Rect [1 1 3 3] /Popup 6 0 R >>"); object(6,0,"<< /Subtype /Text /NM (other) /Rect [1 1 3 3] >>"); finish(7,"");
  OK(exr_pdf_annotation_remove(pdf,length,0,"keep",NULL,&out,&size,&error)); loaded=annotations(out,size,&n);
  CHECK(n==1 && !strcmp(loaded[0].id,"other")); exr_page_annotations_free(loaded,n); exr_free(out);
}
static void boundaries(void) {
  char maximum[32768]; exr_page_annotation a=note("keep","Text"),*loaded; exr_metadata_entry p={DESCRIPTION,maximum};
  void *out=NULL; size_t size=0,n;
  memset(maximum,'A',sizeof(maximum)-1); maximum[sizeof(maximum)-1]=0; classic("null",EXISTING,0);
  a.id=maximum; a.properties=&p; a.property_count=1;
  OK(exr_pdf_annotation_write(pdf,length,0,&a,NULL,&out,&size,&error)); loaded=annotations(out,size,&n);
  CHECK(n==1 && strlen(loaded[0].id)==32767 && !strcmp(loaded[0].id,maximum) && !strcmp(property(loaded,DESCRIPTION),maximum));
  exr_page_annotations_free(loaded,n); exr_free(out); out=NULL; a=note("keep","Text");
  begin(); object(1,0,"<< /Type /Catalog /Pages 2 0 R /Perms << /DocMDP 6 0 R >> >>"); object(2,0,"<< /Type /Pages /Count 1 /Kids [3 0 R] >>");
  object(3,0,"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 40 40] /Annots 4 0 R >>"); object(4,0,"[5 0 R]");
  object(5,0,"<< /Subtype /Text /NM (keep) /Rect [1 1 3 3] >>"); object(6,0,"<< /Type /Sig >>"); finish(7,"");
  failure(EXR_FORMAT,&a,NULL,0); out=(void *)(uintptr_t)1; size=123;
  CHECK(exr_pdf_annotation_remove(pdf,length,0,"keep",NULL,&out,&size,&error)==EXR_FORMAT && !out && !size);
  OK(exr_pdf_annotation_remove(pdf,length,0,"absent",NULL,&out,&size,&error)); CHECK(out && out!=pdf && size==length && !memcmp(out,pdf,length)); exr_free(out);
}
static void overlap(const char *directory) {
  static const double quads[]={4,18,26,18,4,4,26,4,10,22,32,22,10,6,32,6};
  exr_page_annotation a=note("overlap","Highlight"); exr_pdf_annotation_write_options options=exr_pdf_annotation_write_defaults();
  exr_fixed_document *document=NULL; exr_bitmap bitmap={0}; void *out=NULL; size_t size=0; const unsigned char *single,*double_covered;
  classic("null",EXISTING,0); a.quads=quads; a.quad_count=2; a.bounds[2]=32; a.bounds[3]=22; options.color=0xff0000; options.opacity=.5;
  OK(exr_pdf_annotation_write(pdf,length,0,&a,&options,&out,&size,&error));
  OK(exr_fixed_open_memory(EXR_PDF,out,size,NULL,&document,&error)); OK(exr_fixed_render(document,0,1,NULL,&bitmap,&error));
  single=bitmap.pixels+30*bitmap.stride+6*4; double_covered=bitmap.pixels+28*bitmap.stride+15*4;
  CHECK(single[0]==255 && single[1]>=126 && single[1]<=129 && single[2]==single[1]);
  CHECK(!memcmp(single,double_covered,4));
  save(directory,"pdf-write-overlap.pdf",out,size); exr_bitmap_free(&bitmap); exr_fixed_free(document); exr_free(out);
}
int main(int argc,char **argv) {
  const char *directory=argc==2 ? argv[1] : NULL;
  CHECK(argc<=2); roundtrip(directory,0); roundtrip(directory,1); invalid(); edgecases(); boundaries(); overlap(directory);
  printf("PDF annotation writing passed (%u checks)\n",checks); return 0;
}
