/* SPDX-License-Identifier: GPL-3.0-only */
#include "pdf_internal.h"
#include <expat.h>
#define NS '\x1f'
#define RDF "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
#define DC "http://purl.org/dc/elements/1.1/"
#define DCT "http://purl.org/dc/terms/"
#define XMP "http://ns.adobe.com/xap/1.0/"
#define PDF "http://ns.adobe.com/pdf/1.3/"
typedef struct {
  XML_Parser parser; exr_error *error; exr_status status; exr_buffer output,declarations;
  const exr_metadata_entry *changes; size_t count;
  unsigned depth,rdf,description,skip,saw_rdf;
} xmp_writer;
static void fail(xmp_writer *w,exr_status status,const char *message) {
  if(w->status==EXR_OK) { w->status=exr_fail(w->error,status,"%s",message); XML_StopParser(w->parser,XML_FALSE); }
}
static void append(xmp_writer *w,exr_buffer *b,const char *text,size_t size) {
  if(w->status!=EXR_OK) return;
  if(size>1024*1024-b->size) fail(w,EXR_LIMIT,"Written XMP packet exceeds 1 MiB");
  else if(!exr_append(b,text,size)) fail(w,EXR_MEMORY,"XMP writing allocation failed");
}
static void put(xmp_writer *w,exr_buffer *b,const char *text) { append(w,b,text,strlen(text)); }
static void escaped(xmp_writer *w,exr_buffer *b,const char *text,size_t n,int attribute) {
  size_t i,start=0;
  for(i=0;i<n && w->status==EXR_OK;i++) {
    const char *replacement=NULL;
    switch(text[i]) {
      case '&': replacement="&amp;"; break; case '<': replacement="&lt;"; break;
      case '>': replacement="&gt;"; break; case '"': replacement="&quot;"; break;
      case '\r': replacement="&#xD;"; break;
      case '\n': if(attribute) replacement="&#xA;"; break;
      case '\t': if(attribute) replacement="&#x9;"; break;
    }
    if(replacement) { append(w,b,text+start,i-start); put(w,b,replacement); start=i+1; }
  }
  append(w,b,text+start,n-start);
}
static int named(const char *name,const char *uri,const char *local) {
  size_t n=strlen(uri),m=strlen(local);
  return !strncmp(name,uri,n) && name[n]==NS && !strncmp(name+n+1,local,m) && (name[n+1+m]==0 || name[n+1+m]==NS);
}
static void qname(xmp_writer *w,exr_buffer *b,const char *name) {
  const char *first=strchr(name,NS),*last=first ? strchr(first+1,NS) : NULL;
  if(!first) put(w,b,name);
  else {
    if(last && last[1]) { put(w,b,last+1); put(w,b,":"); }
    append(w,b,first+1,last ? (size_t)(last-first-1) : strlen(first+1));
  }
}
static size_t changed(const xmp_writer *w,const char *name) {
  const char *split=strchr(name,NS),*local,*end; size_t uri,n,i;
  if(!split) return SIZE_MAX;
  uri=(size_t)(split-name); local=split+1; end=strchr(local,NS); n=end ? (size_t)(end-local) : strlen(local);
  for(i=0;i<w->count;i++) {
    const char *key=w->changes[i].key; size_t k=strlen(key);
    if(uri==strlen(DC) && !memcmp(name,DC,uri)) {
      size_t prefix=strlen(DCT); if(k==prefix+n && !memcmp(key,DCT,prefix) && !memcmp(key+prefix,local,n)) return i;
    } else if(k==uri+n && !memcmp(key,name,uri) && !memcmp(key+uri,local,n)) return i;
  }
  return SIZE_MAX;
}
static void XMLCALL namespace_start(void *context,const char *prefix,const char *uri) {
  xmp_writer *w=context;
  put(w,&w->declarations," xmlns"); if(prefix) { put(w,&w->declarations,":"); put(w,&w->declarations,prefix); }
  put(w,&w->declarations,"=\""); if(uri) escaped(w,&w->declarations,uri,strlen(uri),1); put(w,&w->declarations,"\"");
}
static void XMLCALL start(void *context,const char *name,const char **attributes) {
  xmp_writer *w=context; const char **at; int document_subject=1;
  if(++w->depth>64) { fail(w,EXR_LIMIT,"XMP nesting exceeds 64"); return; }
  if(w->depth==1 && !named(name,RDF,"RDF") && !named(name,"adobe:ns:meta/","xmpmeta")) {
    fail(w,EXR_FORMAT,"Invalid XMP packet root"); return;
  }
  if(!w->rdf && named(name,RDF,"RDF") && (w->depth==1 || w->depth==2)) {
    if(w->saw_rdf) { fail(w,EXR_FORMAT,"Multiple XMP RDF roots are unsupported for writing"); return; }
    w->rdf=w->depth; w->saw_rdf=1;
  }
  for(at=attributes;*at;at+=2)
    if((named(at[0],RDF,"about") && *at[1]) || named(at[0],RDF,"ID") || named(at[0],RDF,"nodeID")) document_subject=0;
  if(!w->skip && w->rdf && w->depth==w->rdf+1 && named(name,RDF,"Description")) {
    if(!document_subject) { fail(w,EXR_FORMAT,"Named RDF subjects are unsupported for PDF metadata writing"); return; }
    w->description=w->depth;
  }
  if(!w->skip && w->description && w->depth==w->description+1 && changed(w,name)!=SIZE_MAX) w->skip=w->depth;
  if(!w->skip) {
    put(w,&w->output,"<"); qname(w,&w->output,name); append(w,&w->output,w->declarations.data,w->declarations.size);
    for(at=attributes;*at;at+=2) {
      if(w->description==w->depth && changed(w,at[0])!=SIZE_MAX) continue;
      put(w,&w->output," "); qname(w,&w->output,at[0]); put(w,&w->output,"=\"");
      escaped(w,&w->output,at[1],strlen(at[1]),1); put(w,&w->output,"\"");
    }
    put(w,&w->output,">");
  }
  w->declarations.size=0;
}
static void replacements(xmp_writer *w) {
  size_t i;
  put(w,&w->output,"<rdf:Description xmlns:rdf=\"" RDF "\" xmlns:dc=\"" DC "\" xmlns:xmp=\"" XMP "\" xmlns:pdf=\"" PDF "\" rdf:about=\"\">");
  for(i=0;i<w->count && w->status==EXR_OK;i++) {
    const exr_metadata_entry *entry=&w->changes[i]; const char *tag,*prefix,*value=entry->value; int kind=0;
    if(!value) continue;
    if(!strncmp(entry->key,DCT,strlen(DCT))) { tag=entry->key+strlen(DCT); prefix="dc:"; kind=!strcmp(tag,"creator") ? 1 : 2; }
    else if(!strncmp(entry->key,XMP,strlen(XMP))) { tag=entry->key+strlen(XMP); prefix="xmp:"; }
    else { tag=entry->key+strlen(PDF); prefix="pdf:"; }
    put(w,&w->output,"<"); put(w,&w->output,prefix); put(w,&w->output,tag); put(w,&w->output,">");
    if(kind==1) put(w,&w->output,"<rdf:Seq><rdf:li>");
    else if(kind==2) put(w,&w->output,"<rdf:Alt><rdf:li xml:lang=\"x-default\">");
    escaped(w,&w->output,value,strlen(value),0);
    if(kind==1) put(w,&w->output,"</rdf:li></rdf:Seq>"); else if(kind==2) put(w,&w->output,"</rdf:li></rdf:Alt>");
    put(w,&w->output,"</"); put(w,&w->output,prefix); put(w,&w->output,tag); put(w,&w->output,">");
  }
  put(w,&w->output,"</rdf:Description>");
}
static void XMLCALL end(void *context,const char *name) {
  xmp_writer *w=context;
  if(!w->skip) {
    if(w->rdf==w->depth) replacements(w);
    put(w,&w->output,"</"); qname(w,&w->output,name); put(w,&w->output,">");
  }
  if(w->skip==w->depth) w->skip=0;
  if(w->description==w->depth) w->description=0;
  if(w->rdf==w->depth) w->rdf=0;
  w->depth--;
}
static void XMLCALL characters(void *context,const char *text,int size) {
  xmp_writer *w=context; if(!w->skip) escaped(w,&w->output,text,(size_t)size,0);
}
static void XMLCALL comment(void *context,const char *text) {
  xmp_writer *w=context; if(!w->skip) { put(w,&w->output,"<!--"); put(w,&w->output,text); put(w,&w->output,"-->"); }
}
static void XMLCALL instruction(void *context,const char *target,const char *data) {
  xmp_writer *w=context; if(!w->skip) { put(w,&w->output,"<?"); put(w,&w->output,target); if(data && *data) { put(w,&w->output," "); put(w,&w->output,data); } put(w,&w->output,"?>"); }
}
static void XMLCALL doctype(void *context,const char *name,const char *system,const char *public_id,int internal) {
  (void)name; (void)system; (void)public_id; (void)internal; fail(context,EXR_FORMAT,"XMP document types are not allowed");
}
exr_status exr_pdf_xmp_write(const void *data,size_t size,const exr_metadata_entry *changes,size_t count,
  const exr_control *control,exr_buffer *out,exr_error *e) {
  xmp_writer w={0}; size_t at=0,i; exr_status status;
  if(!data || !size || !out || !changes || !count) return exr_fail(e,EXR_ARGUMENT,"Missing XMP writing input");
  if(size>1024*1024) return exr_fail(e,EXR_LIMIT,"XMP packet exceeds 1 MiB");
  for(i=0;i<count;i++) if(changes[i].value) { status=exr_xml_text(changes[i].value,strlen(changes[i].value),"PDF XMP metadata",e); if(status!=EXR_OK) return status; }
  w.changes=changes; w.count=count; w.error=e; w.parser=XML_ParserCreateNS(NULL,NS);
  if(!w.parser) return exr_fail(e,EXR_MEMORY,"XMP writer parser allocation failed");
  XML_SetUserData(w.parser,&w); XML_SetReturnNSTriplet(w.parser,1);
  XML_SetElementHandler(w.parser,start,end); XML_SetCharacterDataHandler(w.parser,characters);
  XML_SetNamespaceDeclHandler(w.parser,namespace_start,NULL); XML_SetCommentHandler(w.parser,comment); XML_SetProcessingInstructionHandler(w.parser,instruction);
  XML_SetStartDoctypeDeclHandler(w.parser,doctype); XML_SetParamEntityParsing(w.parser,XML_PARAM_ENTITY_PARSING_NEVER);
  put(&w,&w.output,"<?xml version=\"1.0\" encoding=\"UTF-8\"?>");
  while(at<size && w.status==EXR_OK) {
    size_t n=size-at; if(n>4096) n=4096;
    w.status=exr_control_poll(control,EXR_STAGE_READ,at,size,e); if(w.status!=EXR_OK) break;
    if(XML_Parse(w.parser,(const char *)data+at,(int)n,at+n==size)==XML_STATUS_ERROR && w.status==EXR_OK) w.status=exr_fail(e,EXR_FORMAT,"Invalid XMP XML");
    at+=n;
  }
  if(w.status==EXR_OK && !w.saw_rdf) w.status=exr_fail(e,EXR_FORMAT,"XMP contains no RDF metadata");
  if(w.status==EXR_OK) w.status=exr_control_poll(control,EXR_STAGE_READ,size,size,e);
  status=w.status; if(status==EXR_OK) { *out=w.output; w.output=(exr_buffer){0}; }
  free(w.output.data); free(w.declarations.data); XML_ParserFree(w.parser); return status;
}
