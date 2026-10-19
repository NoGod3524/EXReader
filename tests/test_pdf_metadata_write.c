/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
#define TITLE "http://purl.org/dc/terms/title"
#define AUTHOR "http://purl.org/dc/terms/creator"
#define DESCRIPTION "http://purl.org/dc/terms/description"
#define KEYWORDS "http://ns.adobe.com/pdf/1.3/Keywords"
#define TOOL "http://ns.adobe.com/xap/1.0/CreatorTool"
#define PRODUCER "http://ns.adobe.com/pdf/1.3/Producer"
#define CREATED "http://ns.adobe.com/xap/1.0/CreateDate"
#define MODIFIED "http://ns.adobe.com/xap/1.0/ModifyDate"
#define RDF "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
#define DC "http://purl.org/dc/elements/1.1/"
static const char packet[]=
  "<?xpacket begin=\"\xef\xbb\xbf\" id=\"metadata-test\"?>"
  "<x:xmpmeta xmlns:x=\"adobe:ns:meta/\"><r:RDF xmlns:r=\"" RDF "\" xmlns:d=\"" DC "\" xmlns:t=\"http://purl.org/dc/terms/\" xmlns:v=\"urn:vendor:\" xmlns:q=\"urn:qualified:\">"
  "<!--keep-comment--><?vendor keep='yes'?>"
  "<r:Description r:about=\"\" d:title=\"old attribute title\" q:custom=\"A&#x9;B&#xA;C&#xD;D\">"
  "<d:title><r:Alt><r:li xml:lang=\"fr\">old French title</r:li><r:li xml:lang=\"x-default\">old XMP title</r:li></r:Alt></d:title>"
  "<t:title>old terms alias</t:title><d:creator><r:Seq><r:li>Original XMP author</r:li></r:Seq></d:creator>"
  "<d:description>Original XMP description</d:description>"
  "<v:complex r:parseType=\"Resource\"><v:child q:type=\"q:Class\">keep&lt;&amp;&#xD;tail</v:child></v:complex>"
  "<v:literal><![CDATA[A<B&C]]></v:literal><v:links><r:Bag><r:li r:resource=\"urn:item:1\"/></r:Bag></v:links>"
  "</r:Description></r:RDF></x:xmpmeta><?xpacket end='w'?>";
static unsigned char input[32768]; static size_t length,offsets[8];
static void raw(const void *bytes,size_t size) { CHECK(size<sizeof(input)-length); memcpy(input+length,bytes,size); length+=size; input[length]=0; }
static void add(const char *text) { raw(text,strlen(text)); }
static void object(unsigned id,const char *body) {
  char row[128]; offsets[id]=length; snprintf(row,sizeof(row),"%u 0 obj\n",id); add(row); add(body); add("\nendobj\n");
}
static void source(const void *xmp,size_t xmp_size,int hex,const char *catalog,const char *info) {
  char row[512]; size_t i,xref; unsigned objects=xmp ? 6 : 5;
  length=0; memset(offsets,0,sizeof(offsets)); add("%PDF-1.7\n");
  snprintf(row,sizeof(row),"<< /Type /Catalog /Pages 2 0 R /VendorRoot << /Keep (catalog untouched) >> %s %s >>",xmp ? "/Metadata 5 0 R" : "",catalog ? catalog : ""); object(1,row);
  object(2,"<< /Type /Pages /Count 1 /Kids [3 0 R] >>");
  object(3,"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 64 64] >>");
  object(4,info ? info : "<< /Title (Original Info title) /Author (Original Info author) /Subject (Original Info description) /Keywords (one,two) /Creator (Original tool) /Producer (Original producer) /CreationDate (D:20261017) /ModDate (D:20261018) /Vendor << /Flag true /Token <00FF> /Tiny .00000000025 >> >>");
  if(xmp) {
    const unsigned char *bytes=xmp; static const char digits[]="0123456789ABCDEF"; offsets[5]=length;
    snprintf(row,sizeof(row),"5 0 obj\n<< /Type /Metadata /Subtype /XML %s /Length %zu >>\nstream\n",hex ? "/Filter /ASCIIHexDecode" : "",hex ? xmp_size*2+1 : xmp_size); add(row);
    if(hex) { for(i=0;i<xmp_size;i++) { char encoded[2]={digits[bytes[i]>>4],digits[bytes[i]&15]}; raw(encoded,2); } add(">"); }
    else raw(xmp,xmp_size);
    add("\nendstream\nendobj\n");
  }
  xref=length; snprintf(row,sizeof(row),"xref\n0 %u\n0000000000 65535 f \n",objects); add(row);
  for(i=1;i<objects;i++) { snprintf(row,sizeof(row),"%010zu 00000 n \n",offsets[i]); add(row); }
  snprintf(row,sizeof(row),"trailer\n<< /Size %u /Root 1 0 R /Info 4 0 R /ID [<0123FF> <ABCDEF>] >>\nstartxref\n%zu\n%%%%EOF\n",objects,xref); add(row);
}
static int contains(const void *bytes,size_t size,const char *text) {
  const unsigned char *p=bytes; size_t n=strlen(text),i;
  for(i=0;n<=size && i<=size-n;i++) if(!memcmp(p+i,text,n)) return 1;
  return 0;
}
static void prefix(const void *bytes,size_t size,const void *old,size_t old_size) { CHECK(bytes && size>old_size && !memcmp(bytes,old,old_size)); }
static exr_metadata_entry *metadata(const void *bytes,size_t size,size_t *count) {
  exr_fixed_document *document=NULL; exr_metadata_entry *entries=NULL;
  OK(exr_fixed_open_memory(EXR_PDF,bytes,size,NULL,&document,&error));
  OK(exr_fixed_load_metadata(document,NULL,&entries,count,&error)); exr_fixed_free(document); return entries;
}
static const char *value(const exr_metadata_entry *entries,size_t count,const char *key) {
  size_t i; const char *result=NULL; for(i=0;i<count;i++) if(!strcmp(entries[i].key,key)) { CHECK(!result); result=entries[i].value; } return result;
}
static void save(const char *directory,const char *name,const void *bytes,size_t size) {
  char path[4096]; FILE *f; if(!directory) return; snprintf(path,sizeof(path),"%s/%s",directory,name); f=fopen(path,"wb"); CHECK(f);
  CHECK(fwrite(bytes,1,size,f)==size); CHECK(!fclose(f));
}
static void roundtrip(const char *directory,int with_xmp,int hex) {
  static const exr_metadata_entry changes[]={
    {TITLE,"New \xe4\xb8\xad\xe6\x96\x87 \xf0\x9f\x98\x80 < & \" title"},{AUTHOR,"New author"},{DESCRIPTION,NULL},{KEYWORDS,""}
  };
  exr_metadata_entry *entries; void *first=NULL,*second=NULL,*third=NULL; size_t size=0,second_size=0,third_size=0,count;
  source(with_xmp ? packet : NULL,sizeof(packet)-1,hex,NULL,NULL);
  OK(exr_pdf_metadata_write(input,length,changes,4,NULL,&first,&size,&error)); prefix(first,size,input,length);
  entries=metadata(first,size,&count);
  CHECK(!strcmp(value(entries,count,TITLE),changes[0].value)); CHECK(!strcmp(value(entries,count,AUTHOR),changes[1].value));
  CHECK(!value(entries,count,DESCRIPTION) && value(entries,count,KEYWORDS) && !*value(entries,count,KEYWORDS));
  CHECK(!strcmp(value(entries,count,TOOL),"Original tool") && !strcmp(value(entries,count,PRODUCER),"Original producer"));
  CHECK(!strcmp(value(entries,count,CREATED),"D:20261017") && !strcmp(value(entries,count,MODIFIED),"D:20261018"));
  if(with_xmp) CHECK(!strcmp(value(entries,count,"urn:qualified:custom"),"A\tB\nC\rD") && !strcmp(value(entries,count,"urn:vendor:literal"),"A<B&C"));
  exr_metadata_free(entries,count);
  CHECK(contains((const unsigned char *)first+length,size-length,"/Vendor"));
  CHECK(contains((const unsigned char *)first+length,size-length,"/Tiny .00000000025"));
  CHECK(contains((const unsigned char *)first+length,size-length,"0123FF"));
  if(with_xmp) {
    const unsigned char *revision=(const unsigned char *)first+length; size_t revision_size=size-length;
    CHECK(contains(revision,revision_size,"/VendorRoot") && contains(revision,revision_size,"<!--keep-comment-->") && contains(revision,revision_size,"<?vendor keep='yes'?>"));
    CHECK(contains(revision,revision_size,"<v:complex r:parseType=\"Resource\"><v:child q:type=\"q:Class\">keep&lt;&amp;&#xD;tail</v:child></v:complex>"));
    CHECK(contains(revision,revision_size,"<r:li r:resource=\"urn:item:1\"></r:li>") && contains(revision,revision_size,"xmlns:q=\"urn:qualified:\""));
    CHECK(!contains(revision,revision_size,"old French title") && !contains(revision,revision_size,"old terms alias") && !contains(revision,revision_size,"old attribute title"));
  }
  save(directory,with_xmp ? (hex ? "pdf-metadata-xmp-hex.pdf" : "pdf-metadata-xmp.pdf") : "pdf-metadata-info.pdf",first,size);
  { exr_metadata_entry patch={TITLE,NULL}; OK(exr_pdf_metadata_write(first,size,&patch,1,NULL,&second,&second_size,&error)); }
  prefix(second,second_size,first,size); entries=metadata(second,second_size,&count);
  CHECK(!value(entries,count,TITLE) && !strcmp(value(entries,count,AUTHOR),"New author")); exr_metadata_free(entries,count);
  { exr_metadata_entry patch={TITLE,""}; OK(exr_pdf_metadata_write(second,second_size,&patch,1,NULL,&third,&third_size,&error)); }
  entries=metadata(third,third_size,&count); CHECK(value(entries,count,TITLE) && !*value(entries,count,TITLE)); exr_metadata_free(entries,count);
  save(directory,with_xmp ? "pdf-metadata-xmp-chain.pdf" : "pdf-metadata-info-chain.pdf",third,third_size);
  exr_free(first); exr_free(second); exr_free(third);
}
static int cancelled(void *context) { return *(int *)context; }
static void final_stop(void *context,exr_stage stage,uint64_t done,uint64_t total) { if(stage==EXR_STAGE_EXPORT && done==total && done) *(int *)context=1; }
static void fail(exr_status expected,const exr_metadata_entry *changes,size_t count,const exr_control *control) {
  void *bytes=(void *)(uintptr_t)1; size_t size=123;
  CHECK(exr_pdf_metadata_write(input,length,changes,count,control,&bytes,&size,&error)==expected && !bytes && !size && error.message[0]);
}
static void invalid(void) {
  exr_metadata_entry change={TITLE,"new"}; void *bytes=(void *)(uintptr_t)1; size_t size=123; int stop=1; exr_control control={cancelled,NULL,&stop};
  source(NULL,0,0,NULL,NULL);
  CHECK(exr_pdf_metadata_write(input,length,&change,1,NULL,NULL,&size,&error)==EXR_ARGUMENT && !size);
  CHECK(exr_pdf_metadata_write(input,length,&change,1,NULL,&bytes,NULL,&error)==EXR_ARGUMENT && !bytes);
  fail(EXR_ARGUMENT,NULL,1,NULL); fail(EXR_ARGUMENT,&change,9,NULL);
  change.key=NULL; fail(EXR_ARGUMENT,&change,1,NULL); change.key="unknown:field"; fail(EXR_ARGUMENT,&change,1,NULL); change.key=TITLE;
  { exr_metadata_entry duplicates[]={{TITLE,"a"},{TITLE,NULL}}; fail(EXR_ARGUMENT,duplicates,2,NULL); }
  change.value="\xff"; fail(EXR_ENCODING,&change,1,NULL); change.value="new"; fail(EXR_CANCELLED,&change,1,&control);
  stop=0; control.progress=final_stop; fail(EXR_CANCELLED,&change,1,&control);
  { char large[32769]; memset(large,'A',sizeof(large)-1); large[sizeof(large)-1]=0; change.value=large; fail(EXR_LIMIT,&change,1,NULL); } change.value="new";
  source(NULL,0,0,"/Perms << /DocMDP 1 0 R >>",NULL); fail(EXR_FORMAT,&change,1,NULL);
  source(NULL,0,0,"/AcroForm << /XFA (unsupported) >>",NULL); fail(EXR_FORMAT,&change,1,NULL);
  source(NULL,0,0,NULL,"[]"); fail(EXR_FORMAT,&change,1,NULL);
  source(NULL,0,0,"/Metadata << >>",NULL); fail(EXR_FORMAT,&change,1,NULL);
  source("not XML",7,0,NULL,NULL); fail(EXR_FORMAT,&change,1,NULL);
  { const char *xml="<!DOCTYPE x [<!ENTITY test 'no'>]><r:RDF xmlns:r=\"" RDF "\"><r:Description/></r:RDF>";
    source(xml,strlen(xml),0,NULL,NULL); fail(EXR_FORMAT,&change,1,NULL);
  }
  source(packet,sizeof(packet)-1,0,NULL,NULL); change.value="bad\1XML"; fail(EXR_ENCODING,&change,1,NULL);
}
static void edgecases(const char *directory) {
  exr_metadata_entry change={TITLE,"unicode \xe4\xb8\xad"},*entries; void *bytes=NULL; size_t size=0,count;
  source(NULL,0,0,"/Perms << >>",NULL);
  OK(exr_pdf_metadata_write(input,length,NULL,0,NULL,&bytes,&size,&error)); CHECK(bytes && bytes!=input && size==length && !memcmp(bytes,input,length)); exr_free(bytes); bytes=NULL;
  source(NULL,0,0,NULL,NULL); input[7]='3';
  OK(exr_pdf_metadata_write(input,length,&change,1,NULL,&bytes,&size,&error)); entries=metadata(bytes,size,&count);
  CHECK(!strcmp(value(entries,count,TITLE),change.value)); exr_metadata_free(entries,count); save(directory,"pdf-metadata-pdf13.pdf",bytes,size); exr_free(bytes); bytes=NULL;
  /* UTF-16 input XML is parsed and serialized as UTF-8 with declarations and
     qualified names preserved semantically. */
  { const char *xml="<RDF xmlns=\"" RDF "\" xmlns:dc=\"" DC "\"><Description><dc:title>UTF16 old</dc:title><dc:creator>UTF16 author</dc:creator></Description></RDF>";
    unsigned char utf16[4096]; size_t i,n=strlen(xml); CHECK(2+2*n<sizeof(utf16)); utf16[0]=0xfe; utf16[1]=0xff;
    for(i=0;i<n;i++) { utf16[2+i*2]=0; utf16[3+i*2]=(unsigned char)xml[i]; }
    source(utf16,2+2*n,0,NULL,NULL); OK(exr_pdf_metadata_write(input,length,&change,1,NULL,&bytes,&size,&error)); entries=metadata(bytes,size,&count);
    CHECK(!strcmp(value(entries,count,TITLE),change.value) && !strcmp(value(entries,count,AUTHOR),"UTF16 author")); exr_metadata_free(entries,count);
    save(directory,"pdf-metadata-xmp-utf16.pdf",bytes,size); exr_free(bytes); bytes=NULL;
  }
  { const char *xml="<r:RDF xmlns:r=\"" RDF "\" xmlns:dc=\"" DC "\"><r:Description r:about=\"urn:other\"><dc:title>other subject title</dc:title></r:Description></r:RDF>";
    source(xml,strlen(xml),0,NULL,NULL); fail(EXR_FORMAT,&change,1,NULL);
  }
}
static void dates(const char *directory) {
  static const struct { const char *input,*pdf,*xmp; } valid[]={
    {"D:2026","D:2026","2026"},
    {"2024-02","D:202402","2024-02"},
    {"D:20240229","D:20240229","2024-02-29"},
    {"D:202610171234-0400","D:202610171234-04'00'","2026-10-17T12:34-04:00"},
    {"2026-10-17T12:34:56","D:20261017123456","2026-10-17T12:34:56"},
    {"2026-10-17T12:34:56.000+05:30","D:20261017123456+05'30'","2026-10-17T12:34:56+05:30"},
    {"D:20261017123456Z","D:20261017123456Z","2026-10-17T12:34:56Z"}
  };
  static const char *const invalid_dates[]={"","2026-02-29","1900-02-29","2024-13-01","2024-00-01","2024-01-00","2024-04-31",
    "0000","D:2026101712","2026-10-17T12","2026-10-17T12:34:60Z","2026-10-17T24:00:00Z","2026-10-17T12:34:00+24:00",
    "2026-10-17T12:34:00+00:60","2026-10-17T12:34:56.001Z","2026-10-17T12:34:56.Z","D:20261017123456-04'x0'","2026-10Z","not a date"};
  size_t i,j,count,size; void *bytes=NULL; exr_metadata_entry *entries;
  for(i=0;i<sizeof(valid)/sizeof(*valid);i++) for(j=0;j<2;j++) {
    exr_metadata_entry change={CREATED,valid[i].input}; source(j ? packet : NULL,sizeof(packet)-1,0,NULL,NULL);
    OK(exr_pdf_metadata_write(input,length,&change,1,NULL,&bytes,&size,&error)); entries=metadata(bytes,size,&count);
    CHECK(!strcmp(value(entries,count,CREATED),j ? valid[i].xmp : valid[i].pdf));
    CHECK(!strcmp(value(entries,count,MODIFIED),"D:20261018"));
    exr_metadata_free(entries,count); exr_free(bytes); bytes=NULL;
  }
  source(packet,sizeof(packet)-1,0,NULL,NULL);
  for(i=0;i<sizeof(invalid_dates)/sizeof(*invalid_dates);i++) { exr_metadata_entry change={CREATED,invalid_dates[i]}; fail(EXR_ARGUMENT,&change,1,NULL); }
  { exr_metadata_entry changes[]={{CREATED,"D:20261017123456-04'00'"},{MODIFIED,"2026-10-17T16:34:56Z"}};
    OK(exr_pdf_metadata_write(input,length,changes,2,NULL,&bytes,&size,&error)); save(directory,"pdf-metadata-dates.pdf",bytes,size); exr_free(bytes); bytes=NULL;
  }
  { exr_metadata_entry changes[]={{TITLE,"all eight"},{AUTHOR,"author"},{DESCRIPTION,"description"},{KEYWORDS,"keywords"},{TOOL,"tool"},{PRODUCER,"producer"},
      {CREATED,"2000-02-29T00:00:00Z"},{MODIFIED,"D:20261017123456+05'30'"}};
    source(NULL,0,0,NULL,NULL); OK(exr_pdf_metadata_write(input,length,changes,8,NULL,&bytes,&size,&error)); entries=metadata(bytes,size,&count);
    CHECK(count==8); for(i=0;i<6;i++) CHECK(!strcmp(value(entries,count,changes[i].key),changes[i].value));
    CHECK(!strcmp(value(entries,count,CREATED),"D:20000229000000Z") && !strcmp(value(entries,count,MODIFIED),"D:20261017123456+05'30'"));
    exr_metadata_free(entries,count); exr_free(bytes);
  }
}
int main(int argc,char **argv) {
  const char *directory=argc==2 ? argv[1] : NULL; CHECK(argc<=2);
  roundtrip(directory,0,0); roundtrip(directory,1,0); roundtrip(directory,1,1); invalid(); edgecases(directory); dates(directory);
  printf("PDF metadata writing passed (%u checks)\n",checks); return 0;
}
