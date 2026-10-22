/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include "../src/pdf_internal.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
static exr_error error;
static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"form check line %d failed: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static unsigned char pdf[262144],original[262144];
static size_t length,offset[256];
static void add(const char *text) { size_t n=strlen(text); CHECK(n<sizeof(pdf)-length); memcpy(pdf+length,text,n); length+=n; pdf[length]=0; }
static void fmt(const char *pattern,...) { char text[8192]; va_list args; int n; va_start(args,pattern); n=vsnprintf(text,sizeof(text),pattern,args); va_end(args); CHECK(n>=0 && (size_t)n<sizeof(text)); add(text); }
static void object(unsigned id,const char *body) { offset[id]=length; fmt("%u 0 obj\n%s\nendobj\n",id,body); }
/* Original generated corpus: 36 fields, inherited names/values/constraints,
   39 widgets, radio exports, pair options, multiple selection and two pages. */
static void source(unsigned mode) {
  unsigned i,page; char text[8192]; size_t at,xref; length=0; memset(offset,0,sizeof(offset)); add("%PDF-1.7\n");
  object(1,mode==9 ? "<< /Type /Catalog /Pages 2 0 R /AcroForm << /Fields [6 0 R 44 0 R 45 0 R 46 0 R 47 0 R 48 0 R 49 0 R 50 0 R 51 0 R 52 0 R 53 0 R 54 0 R 55 0 R] /NeedAppearances true >> >>" : "<< /Type /Catalog /Pages 2 0 R /AcroForm 5 0 R >>");
  object(2,"<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>");
  for(page=0;page<2;page++) {
    at=(size_t)snprintf(text,sizeof(text),"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 120 80] /Annots [");
    for(i=21;i<=55;i++) if(i!=48 && i!=49 && i%2==page) at+=(size_t)snprintf(text+at,sizeof(text)-at,"%u 0 R ",i);
    at+=(size_t)snprintf(text+at,sizeof(text)-at,"%u 0 R %u 0 R %u 0 R] >>",100+page,102+page,104+page); object(3+page,text);
  }
  snprintf(text,sizeof(text),"<< /Fields [6 0 R 44 0 R 45 0 R 46 0 R 47 0 R 48 0 R 49 0 R 50 0 R 51 0 R 52 0 R 53 0 R 54 0 R 55 0 R] /NeedAppearances true %s >>",mode==6 ? "/XFA (record only)" : ""); object(5,text);
  at=(size_t)snprintf(text,sizeof(text),"<< /T (person) /FT /Tx /Ff 0 /MaxLen 12 /V (inherited) /DV (default) /DA (/Helv 10 Tf 0 g) /Q 1 %s /Kids [",mode==7 ? "/AA << /K << /S /JavaScript /JS (never executed) >> >>" : "");
  for(i=20;i<44;i++) at+=(size_t)snprintf(text+at,sizeof(text)-at,"%u 0 R ",i);
  snprintf(text+at,sizeof(text)-at,"%s] >>",mode==2 ? "6 0 R" : ""); object(6,text);
  object(7,"<< /Type /XObject /Subtype /Form /BBox [0 0 100 20] /Length 0 >>\nstream\nendstream");
  for(i=20;i<44;i++) {
    snprintf(text,sizeof(text),"<< /Parent 6 0 R /T (text%02u) %s %s %s >>",i-20,
      i==20 ? "/Kids [100 0 R 101 0 R]" : "/Type /Annot /Subtype /Widget /Rect [10 10 110 30] /AP << /N 7 0 R >>",
      i==21 && mode==1 ? "/FT 42" : i==21 && mode==3 ? "/Ff 1" : i==21 && mode==4 ? "/Ff 2" : i==21 && mode==5 ? "/MaxLen 2" : "",
      i==21 && mode==8 ? "/MK << /R 90 >>" : ""); object(i,text);
  }
  for(i=44;i<48;i++) { snprintf(text,sizeof(text),"<< /FT /Btn /T (check%u) /Type /Annot /Subtype /Widget /Rect [10 35 30 55] /V /Off /AP << /N << /Off 7 0 R /Yes 7 0 R >> >> >>",i-44); object(i,text); }
  for(i=48;i<50;i++) { snprintf(text,sizeof(text),"<< /FT /Btn /Ff 32768 /T (radio%u) /Kids [%u 0 R %u 0 R] /V /Off >>",i-48,102+(i-48)*2,103+(i-48)*2); object(i,text); }
  for(i=50;i<54;i++) { snprintf(text,sizeof(text),"<< /FT /Ch /Ff %u /T (choice%u) /Type /Annot /Subtype /Widget /Rect [10 10 110 30] /Opt [(A) [(B) (V)]] /V (A) /AP << /N 7 0 R >> >>",i==52 ? 2097152u : i==53 ? 131072u : 0u,i-50); object(i,text); }
  object(54,"<< /FT /Sig /T (signature) /Type /Annot /Subtype /Widget /Rect [10 10 110 30] >>");
  object(55,"<< /FT /Btn /Ff 65536 /T (push) /Type /Annot /Subtype /Widget /Rect [10 10 110 30] >>");
  for(i=100;i<106;i++) {
    snprintf(text,sizeof(text),"<< /Type /Annot /Subtype /Widget /Parent %u 0 R /Rect [10 10 110 30] /AP << /N %s >> >>",i<102 ? 20 : i<104 ? 48 : 49,
      i<102 ? "7 0 R" : i%2 ? "<< /Off 7 0 R /Blue 7 0 R >>" : "<< /Off 7 0 R /Red 7 0 R >>"); object(i,text);
  }
  xref=length; add("xref\n0 106\n0000000000 65535 f \n");
  for(i=1;i<106;i++) if(offset[i]) fmt("%010zu 00000 n \n",offset[i]); else add("0000000000 00000 f \n");
  fmt("trailer\n<< /Size 106 /Root 1 0 R /ID [<1234> <5678>] >>\nstartxref\n%zu\n%%%%EOF\n",xref);
  memcpy(original,pdf,length);
}
static exr_pdf_form_field *read_fields(const void *data,size_t size,size_t *n) {
  exr_pdf_form_field *fields=NULL; OK(exr_pdf_form_read(data,size,NULL,&fields,n,&error)); return fields;
}
static const exr_pdf_form_field *named(const exr_pdf_form_field *f,size_t n,const char *name) {
  size_t i; for(i=0;i<n;i++) if(!strcmp(f[i].name,name)) return f+i; CHECK(0); return NULL;
}
static int cancelled(void *context) { return *(int *)context; }
static void final_cancel(void *context,exr_stage stage,uint64_t done,uint64_t total) { if(stage==EXR_STAGE_EXPORT && done==total) *(int *)context=1; }
static void failure(unsigned mode,const char *name,const char *value,exr_status expected) {
  const char *values[]={value}; exr_pdf_form_change c={name,values,1}; void *out=(void *)1; size_t n=99; source(mode);
  CHECK(exr_pdf_form_write(pdf,length,&c,1,NULL,&out,&n,&error)==expected); CHECK(!out && !n && !memcmp(pdf,original,length));
}
static uint32_t get(exr_pdf_file *file,uint32_t dict,const char *key) { uint32_t id; OK(exr_pdf_resolve(file,exr_pdf_get(file,dict,key),&id,&error)); return id; }
static int name_is(exr_pdf_file *file,uint32_t id,const char *name) { size_t n; const unsigned char *s=exr_pdf_bytes(file,id,&n); return s && n==strlen(name) && !memcmp(s,name,n); }
static void appearances(const void *data,size_t size) {
  exr_pdf_file *file=NULL; exr_pdf_page_info *pages=NULL; size_t count=0,i,seen=0; OK(exr_pdf_open(data,size,&file,&error)); OK(exr_pdf_pages(file,&pages,&count,&error)); CHECK(count==2);
  for(i=0;i<count;i++) {
    uint32_t annotations=get(file,pages[i].object,"Annots"),at=exr_pdf_value_at(file,annotations)->first;
    while(at!=EXR_PDF_NONE) {
      uint32_t next=exr_pdf_value_at(file,at)->next,widget,ap,normal; OK(exr_pdf_resolve(file,at,&widget,&error)); ap=get(file,widget,"AP");
      if(ap!=EXR_PDF_NONE) {
        const unsigned char *bytes; size_t n; normal=get(file,ap,"N");
        if(exr_pdf_value_at(file,normal)->kind==EXR_PDF_DICT) {
          uint32_t state=get(file,widget,"AS"); CHECK(state!=EXR_PDF_NONE); normal=get(file,normal,name_is(file,state,"Off") ? "Off" : name_is(file,state,"Yes") ? "Yes" : name_is(file,state,"Blue") ? "Blue" : "Red");
        }
        OK(exr_pdf_stream_data(file,normal,&bytes,&n,&error)); CHECK(n>0); seen++;
      }
      at=next;
    }
  }
  CHECK(seen==37); free(pages); exr_pdf_close(file);
}
static void render(const void *data,size_t size,exr_font *font) {
  exr_fixed_open_options options={0}; exr_fixed_document *doc=NULL; exr_bitmap bitmap={0}; size_t page,x,y,ink;
  options.struct_size=sizeof(options); options.fallback_font=font; OK(exr_fixed_open_memory(EXR_PDF,data,size,&options,&doc,&error));
  for(page=0;page<2;page++) { OK(exr_fixed_render(doc,page,1,NULL,&bitmap,&error)); ink=0;
    for(y=52;y<68;y++) for(x=15;x<105;x++) if(bitmap.pixels[y*bitmap.stride+x*bitmap.channels]<100) ink++;
    CHECK(ink>0); exr_bitmap_free(&bitmap);
  }
  exr_fixed_free(doc);
}
static void deep_source(void) {
  unsigned i; size_t xref; char text[256]; length=0; memset(offset,0,sizeof(offset)); add("%PDF-1.7\n");
  object(1,"<< /Type /Catalog /Pages 2 0 R /AcroForm << /Fields [10 0 R] >> >>"); object(2,"<< /Type /Pages /Count 1 /Kids [3 0 R] >>"); object(3,"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] >>");
  for(i=10;i<76;i++) { snprintf(text,sizeof(text),"<< /T (n) %s",i==10 ? "" : "/Parent "); offset[i]=length; fmt("%u 0 obj\n%s",i,text); if(i!=10) fmt("%u 0 R ",i-1); if(i<75) fmt("/Kids [%u 0 R] >>\nendobj\n",i+1); else add("/FT /Tx >>\nendobj\n"); }
  xref=length; add("xref\n0 76\n0000000000 65535 f \n"); for(i=1;i<76;i++) if(offset[i]) fmt("%010zu 00000 n \n",offset[i]); else add("0000000000 00000 f \n"); fmt("trailer\n<< /Root 1 0 R /Size 76 >>\nstartxref\n%zu\n%%%%EOF\n",xref);
}
int main(int argc,char **argv) {
  exr_pdf_form_field *fields=NULL; const exr_pdf_form_field *field; size_t n,i,output_size=0; void *output=NULL,*second=NULL; size_t second_size=0;
  exr_pdf_form_change changes[34]; char names[34][32]; const char *values[34][2]; exr_font *font=NULL; exr_pdf_form_write_options options=exr_pdf_form_write_defaults();
  CHECK(argc==2); OK(exr_font_open(argv[1],&font,&error)); source(0); fields=read_fields(pdf,length,&n); CHECK(n==36);
  field=named(fields,n,"person.text00"); CHECK(field->kind==EXR_PDF_FIELD_TEXT && field->widget_count==2 && field->max_length==12 && !strcmp(field->values[0],"inherited") && !strcmp(field->default_values[0],"default"));
  CHECK(field->widgets[0].page==0 && field->widgets[1].page==1); CHECK(named(fields,n,"signature")->issues&EXR_PDF_FORM_UNSUPPORTED); CHECK(named(fields,n,"push")->kind==EXR_PDF_FIELD_PUSHBUTTON);
  CHECK(named(fields,n,"choice0")->option_count==2 && !strcmp(named(fields,n,"choice0")->options[1].label,"V")); exr_pdf_form_free(fields,n);
  for(i=0;i<34;i++) {
    if(i<24) { snprintf(names[i],sizeof(names[i]),"person.text%02zu",i); values[i][0]="AVA"; }
    else if(i<28) { snprintf(names[i],sizeof(names[i]),"check%zu",i-24); values[i][0]="Yes"; }
    else if(i<30) { snprintf(names[i],sizeof(names[i]),"radio%zu",i-28); values[i][0]="Blue"; }
    else { snprintf(names[i],sizeof(names[i]),"choice%zu",i-30); values[i][0]="A"; }
    values[i][1]="B"; changes[i]=(exr_pdf_form_change){names[i],values[i],i==32 ? 2 : 1};
  }
  options.font=font; OK(exr_pdf_form_write(pdf,length,changes,34,&options,&output,&output_size,&error)); CHECK(output_size>length && !memcmp(output,pdf,length)); CHECK(!memcmp(pdf,original,length));
  fields=read_fields(output,output_size,&n); CHECK(n==36);
  for(i=0;i<34;i++) { field=named(fields,n,names[i]); CHECK(field->value_count==changes[i].value_count && !strcmp(field->values[0],values[i][0])); }
  exr_pdf_form_free(fields,n); appearances(output,output_size); render(output,output_size,font);
  values[0][0]="\xe7\x94\xb2\xe4\xb9\x99\xf0\x9f\x98\x80"; OK(exr_pdf_form_write(output,output_size,changes,1,&options,&second,&second_size,&error));
  fields=read_fields(second,second_size,&n); CHECK(!strcmp(named(fields,n,"person.text00")->values[0],values[0][0])); exr_pdf_form_free(fields,n); render(second,second_size,font); exr_free(second); exr_free(output); output=NULL;
  source(9); values[0][0]="AVA"; OK(exr_pdf_form_write(pdf,length,changes,1,NULL,&output,&output_size,&error)); fields=read_fields(output,output_size,&n); CHECK(!strcmp(fields[0].values[0],"AVA")); exr_pdf_form_free(fields,n); exr_free(output);
  source(0); OK(exr_pdf_form_write(pdf,length,NULL,0,NULL,&output,&output_size,&error)); CHECK(output_size==length && output!=pdf && !memcmp(output,pdf,length)); exr_free(output);
  failure(3,"person.text01","A",EXR_ARGUMENT); failure(4,"person.text01","",EXR_ARGUMENT); failure(5,"person.text01","AVA",EXR_ARGUMENT);
  failure(6,"person.text00","A",EXR_UNSUPPORTED); failure(7,"person.text00","A",EXR_UNSUPPORTED); failure(8,"person.text01","A",EXR_UNSUPPORTED);
  failure(0,"signature","A",EXR_UNSUPPORTED); failure(0,"push","A",EXR_UNSUPPORTED); failure(0,"missing","A",EXR_ARGUMENT);
  failure(0,"choice0","absent",EXR_ARGUMENT); failure(0,"check0","absent",EXR_ARGUMENT); failure(0,"person.text00","\xff",EXR_ENCODING);
  failure(0,"person.text00","\xe7\x94\xb2",EXR_UNSUPPORTED);
  for(i=1;i<=2;i++) { source((unsigned)i); fields=(exr_pdf_form_field *)1; n=99; CHECK(exr_pdf_form_read(pdf,length,NULL,&fields,&n,&error)==EXR_FORMAT && !fields && !n); }
  source(0);
  { exr_pdf_form_options limits=exr_pdf_form_defaults(); limits.max_fields=30; CHECK(exr_pdf_form_read(pdf,length,&limits,&fields,&n,&error)==EXR_LIMIT && !fields && !n); limits=exr_pdf_form_defaults(); limits.max_widgets=1; CHECK(exr_pdf_form_read(pdf,length,&limits,&fields,&n,&error)==EXR_LIMIT && !fields && !n); limits=exr_pdf_form_defaults(); limits.max_text_bytes=16; CHECK(exr_pdf_form_read(pdf,length,&limits,&fields,&n,&error)==EXR_LIMIT && !fields && !n); }
  { int stop=1; options=exr_pdf_form_write_defaults(); options.control.cancelled=cancelled; options.control.context=&stop; output=(void *)1; output_size=99;
    CHECK(exr_pdf_form_write(pdf,length,changes,1,&options,&output,&output_size,&error)==EXR_CANCELLED && !output && !output_size);
    stop=0; options.control.progress=final_cancel; CHECK(exr_pdf_form_write(pdf,length,changes,1,&options,&output,&output_size,&error)==EXR_CANCELLED && !output && !output_size && !memcmp(pdf,original,length));
  }
  deep_source(); CHECK(exr_pdf_form_read(pdf,length,NULL,&fields,&n,&error)==EXR_LIMIT && !fields && !n);
  exr_font_free(font); printf("AcroForm: %u checks; 36 fields, 39 widgets, 2 pages\n",checks); return 0;
}
