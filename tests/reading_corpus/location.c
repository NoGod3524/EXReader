/* SPDX-License-Identifier: MIT */
/* Real-document selectors must resolve after independent reopen; no private API. */
#include <exr/core.h>
#include <exr/pdf.h>
#include <stdio.h>
#include <string.h>

static size_t start_at(const char *text,size_t n) {
  size_t at=n/2;
  while(at<n && ((unsigned char)text[at]&0xc0)==0x80) at++;
  return at;
}
static size_t end_at(const char *text,size_t n,size_t start) {
  size_t end=n-start>64?start+64:n;
  while(end<n && ((unsigned char)text[end]&0xc0)==0x80) end++;
  return end;
}
static int same(const char *a,const char *b) { return a && b && !strcmp(a,b); }

int main(int argc,char **argv) {
  exr_font *font=NULL;exr_error error={0};exr_status status=EXR_ARGUMENT;
  exr_fixed_document *fixed=NULL,*again=NULL;
  exr_publication *publication=NULL,*reopened=NULL;
  size_t units=0,checked=0,empty=0;int complete=0;
  const char *stage="arguments";
  if(argc!=3) return 2;
  stage="font";status=exr_font_open(argv[2],&font,&error);if(status) goto done;
  stage="open";
  if(strstr(argv[1],".pdf")) {
    exr_fixed_open_options options={0};size_t other=0;
    options.struct_size=sizeof(options);options.fallback_font=font;
    status=exr_fixed_open(argv[1],&options,&fixed,&error);if(status) goto done;
    status=exr_fixed_open(argv[1],&options,&again,&error);if(status) goto done;
    const exr_fixed_page *pages=exr_fixed_pages(fixed,&units),*pages2=exr_fixed_pages(again,&other);
    if(!units || units!=other || !pages || !pages2) {status=EXR_FORMAT;goto done;}
    for(size_t i=0;i<units;i++) {
      exr_fixed_text *text=NULL,*text2=NULL;exr_fixed_anchor anchor={0};exr_anchor_match match={0};
      size_t n=0,n2=0,start=0,end=0;const char *value=NULL,*value2=NULL;
      stage="text";
      status=exr_fixed_load_text(fixed,i,NULL,&text,&error);if(status) goto pdf_unit;
      status=exr_fixed_load_text(again,i,NULL,&text2,&error);if(status) goto pdf_unit;
      value=exr_fixed_text_string(text,&n);value2=exr_fixed_text_string(text2,&n2);
      if(n!=n2 || (n && (!value || !value2 || memcmp(value,value2,n)))) {status=EXR_FORMAT;goto pdf_unit;}
      if(!same(pages[i].id,pages2[i].id)) {status=EXR_FORMAT;goto pdf_unit;}
      if(!n) {empty++;goto pdf_unit;}
      start=start_at(value,n);end=end_at(value,n,start);stage="capture";
      status=exr_fixed_anchor_create(pages[i].id,text,start,end,&anchor,&error);if(status) goto pdf_unit;
      stage="resolve";
      status=exr_fixed_anchor_resolve(pages2[i].id,text2,&anchor,NULL,&match,&error);if(status) goto pdf_unit;
      if(match.state!=EXR_ANCHOR_FOUND || match.start!=start || match.end!=end) {status=EXR_FORMAT;goto pdf_unit;}
      checked++;
pdf_unit:
      printf("{\"unit\":%zu,\"status\":%d,\"stage\":\"%s\",\"text_bytes\":%zu,\"selector_state\":%d}\n",i,(int)status,stage,n,(int)match.state);
      exr_fixed_anchor_free(&anchor);exr_fixed_text_free(text);exr_fixed_text_free(text2);
      if(status) goto done;
    }
  } else {
    size_t other=0;
    status=exr_publication_open(argv[1],&publication,&error);if(status) goto done;
    status=exr_publication_open(argv[1],&reopened,&error);if(status) goto done;
    const exr_part *parts=exr_publication_parts(publication,&units),*parts2=exr_publication_parts(reopened,&other);
    if(!units || units!=other || !parts || !parts2) {status=EXR_FORMAT;goto done;}
    for(size_t i=0;i<units;i++) {
      exr_document *doc=NULL,*doc2=NULL;exr_anchor anchor={0};exr_anchor_match match={0};
      size_t n=0,n2=0,start=0,end=0;const char *value=NULL,*value2=NULL;
      stage="load";
      status=exr_publication_load(publication,i,&doc,&error);if(status) goto epub_unit;
      status=exr_publication_load(reopened,i,&doc2,&error);if(status) goto epub_unit;
      value=exr_document_text(doc,&n);value2=exr_document_text(doc2,&n2);
      if(n!=n2 || (n && (!value || !value2 || memcmp(value,value2,n)))) {status=EXR_FORMAT;goto epub_unit;}
      if(!same(parts[i].path,parts2[i].path)) {status=EXR_FORMAT;goto epub_unit;}
      if(!n) {empty++;goto epub_unit;}
      start=start_at(value,n);end=end_at(value,n,start);stage="capture";
      status=exr_anchor_create(doc,start,end,&anchor,&error);if(status) goto epub_unit;
      stage="resolve";status=exr_anchor_resolve(doc2,&anchor,&match,&error);if(status) goto epub_unit;
      if(match.state!=EXR_ANCHOR_FOUND || match.start!=start || match.end!=end) {status=EXR_FORMAT;goto epub_unit;}
      checked++;
epub_unit:
      printf("{\"unit\":%zu,\"status\":%d,\"stage\":\"%s\",\"text_bytes\":%zu,\"selector_state\":%d}\n",i,(int)status,stage,n,(int)match.state);
      exr_anchor_free(&anchor);exr_document_free(doc);exr_document_free(doc2);
      if(status) goto done;
    }
  }
  complete=checked>0 && checked+empty==units;
done:
  fprintf(stderr,"stage=%s status=%d units=%zu checked=%zu empty=%zu\n",stage,(int)status,units,checked,empty);
  printf("{\"schema\":1,\"status\":%d,\"complete\":%s,\"units\":%zu,\"checked\":%zu,\"empty\":%zu,\"engine_version\":\"%s\"}\n",(int)status,complete?"true":"false",units,checked,empty,exr_version());
  exr_fixed_free(fixed);exr_fixed_free(again);exr_publication_free(publication);exr_publication_free(reopened);exr_font_free(font);
  return status==EXR_OK && complete?0:1;
}
