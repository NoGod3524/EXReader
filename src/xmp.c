/* SPDX-License-Identifier: MIT */
#include "internal.h"
#include <expat.h>
#define RDF "http://www.w3.org/1999/02/22-rdf-syntax-ns#|"
#define XML_LANG "http://www.w3.org/XML/1998/namespace|lang"
typedef struct {
  XML_Parser parser; exr_error *error; exr_status status; exr_metadata_entry *entries;
  size_t count,capacity,bytes,property_start; unsigned depth,rdf,description,property,container,item,kind,skip,saw_rdf;
  char *key; exr_buffer text,alternative; unsigned preferred,current_preferred;
} xmp_reader;
static void fail(xmp_reader *r,exr_status status,const char *message) {
  if(r->status==EXR_OK) { r->status=exr_fail(r->error,status,"%s",message); XML_StopParser(r->parser,XML_FALSE); }
}
static const char *attribute(const char **attributes,const char *name) {
  while(*attributes) { if(!strcmp(attributes[0],name)) return attributes[1]; attributes+=2; }
  return NULL;
}
static char *key_name(xmp_reader *r,const char *name) {
  const char *split=strrchr(name,'|'); exr_buffer key={0}; const char *dc="http://purl.org/dc/elements/1.1/|";
  if(!split || split==name || !split[1]) { fail(r,EXR_FORMAT,"XMP properties must have a namespace"); return NULL; }
  if(strlen(name)>4096) { fail(r,EXR_LIMIT,"XMP property key exceeds 4096 bytes"); return NULL; }
  if(!strncmp(name,dc,strlen(dc))) {
    if(!exr_append(&key,"http://purl.org/dc/terms/",sizeof("http://purl.org/dc/terms/")-1) || !exr_append(&key,split+1,strlen(split+1))) goto memory;
  } else if(!exr_append(&key,name,(size_t)(split-name)) || !exr_append(&key,split+1,strlen(split+1))) goto memory;
  return key.data;
memory:
  free(key.data); fail(r,EXR_MEMORY,"XMP property key allocation failed"); return NULL;
}
static void entry(xmp_reader *r,const char *key,const char *text,size_t size) {
  char *key_copy,*value; size_t bytes=strlen(key)+size+2;
  if(r->status!=EXR_OK) return;
  if(bytes>(size_t)8*1024*1024-r->bytes) { fail(r,EXR_LIMIT,"XMP metadata exceeds 8 MiB"); return; }
  if(r->count==4096) { fail(r,EXR_LIMIT,"XMP exceeds 4096 literal values"); return; }
  if(!exr_grow((void **)&r->entries,&r->capacity,r->count+1,sizeof(*r->entries))) { fail(r,EXR_MEMORY,"XMP entries allocation failed"); return; }
  key_copy=exr_copy(key,strlen(key)); value=exr_copy(text,size);
  if(!key_copy || !value) { free(key_copy); free(value); fail(r,EXR_MEMORY,"XMP value allocation failed"); return; }
  r->entries[r->count++]=(exr_metadata_entry){key_copy,value}; r->bytes+=bytes;
}
static void XMLCALL start(void *context,const char *name,const char **attributes) {
  xmp_reader *r=context; const char *about; r->depth++;
  if(r->depth>64) { fail(r,EXR_LIMIT,"XMP nesting exceeds 64"); return; }
  if(!r->rdf) {
    if(!strcmp(name,RDF "RDF") && (r->depth==1 || r->depth==2)) { r->rdf=r->depth; r->saw_rdf=1; }
    else if(r->depth==1 && strcmp(name,"adobe:ns:meta/|xmpmeta")) fail(r,EXR_FORMAT,"Invalid XMP packet root");
    return;
  }
  if(!r->description) {
    if(r->depth!=r->rdf+1 || strcmp(name,RDF "Description")) return;
    about=attribute(attributes,RDF "about"); if(about && *about) { fail(r,EXR_FORMAT,"Named RDF subjects are not supported in XMP metadata"); return; }
    r->description=r->depth;
    while(*attributes && r->status==EXR_OK) {
      if(strncmp(attributes[0],RDF,strlen(RDF)) && strcmp(attributes[0],XML_LANG)) {
        char *key=key_name(r,attributes[0]); if(key) { size_t n=strlen(attributes[1]); if(n>65536) fail(r,EXR_LIMIT,"XMP literal exceeds 64 KiB"); else entry(r,key,attributes[1],n); free(key); }
      }
      attributes+=2;
    }
    return;
  }
  if(!r->property) {
    if(r->depth!=r->description+1) return;
    r->property=r->depth; r->property_start=r->count; r->key=key_name(r,name); r->skip=0; r->kind=r->container=r->item=0; r->preferred=0;
    if(attribute(attributes,RDF "resource") || attribute(attributes,RDF "parseType")) r->skip=1;
    return;
  }
  if(r->skip) return;
  if(r->depth==r->property+1 && !r->container) {
    if(!strcmp(name,RDF "Seq")) r->kind=1; else if(!strcmp(name,RDF "Bag")) r->kind=2; else if(!strcmp(name,RDF "Alt")) r->kind=3;
    if(!r->kind) { r->skip=1; return; }
    if(r->text.size && strspn(r->text.data," \t\r\n")!=r->text.size) { fail(r,EXR_FORMAT,"Mixed XMP container content"); return; }
    r->text.size=0; if(r->text.data) r->text.data[0]=0; r->container=r->depth; return;
  }
  if(r->container && r->depth==r->container+1 && !strcmp(name,RDF "li") && !r->item) {
    const char *lang=attribute(attributes,XML_LANG); r->item=r->depth; r->current_preferred=lang && !strcmp(lang,"x-default");
    if(attribute(attributes,RDF "resource") || attribute(attributes,RDF "parseType")) r->skip=1;
  } else r->skip=1;
}
static void XMLCALL characters(void *context,const char *text,int size) {
  xmp_reader *r=context;
  if(r->status!=EXR_OK || !r->property || r->skip) return;
  if(r->container && !r->item) { int i; for(i=0;i<size;i++) if(!strchr(" \t\r\n",text[i])) { fail(r,EXR_FORMAT,"Mixed XMP container content"); break; } return; }
  if((size_t)size>65536-r->text.size) { fail(r,EXR_LIMIT,"XMP literal exceeds 64 KiB"); return; }
  if(!exr_append(&r->text,text,(size_t)size)) fail(r,EXR_MEMORY,"XMP literal allocation failed");
}
static void XMLCALL end(void *context,const char *name) {
  xmp_reader *r=context; (void)name;
  if(r->item==r->depth) {
    if(!r->skip) {
      if(r->kind==3) {
        if(r->current_preferred && r->preferred==2) fail(r,EXR_FORMAT,"Duplicate XMP x-default alternative");
        else if(!r->preferred || r->current_preferred) {
          free(r->alternative.data); r->alternative=r->text; r->text=(exr_buffer){0}; r->preferred=r->current_preferred ? 2 : 1;
        }
      } else entry(r,r->key,r->text.data,r->text.size);
    }
    r->item=0; r->text.size=0; if(r->text.data) r->text.data[0]=0;
  }
  if(r->property==r->depth) {
    if(r->skip) while(r->count>r->property_start) { exr_metadata_entry *v=&r->entries[--r->count]; r->bytes-=strlen(v->key)+strlen(v->value)+2; free((void *)v->key); free((void *)v->value); }
    if(!r->skip && r->key) {
      if(!r->container) entry(r,r->key,r->text.data,r->text.size);
      else if(r->kind==3 && r->preferred) entry(r,r->key,r->alternative.data,r->alternative.size);
    }
    free(r->key); r->key=NULL; free(r->text.data); r->text=(exr_buffer){0}; free(r->alternative.data); r->alternative=(exr_buffer){0};
    r->property=r->container=r->item=r->skip=0;
  }
  if(r->description==r->depth) r->description=0;
  if(r->rdf==r->depth) r->rdf=0;
  r->depth--;
}
static void XMLCALL doctype(void *context,const char *name,const char *system,const char *public_id,int internal) {
  (void)name; (void)system; (void)public_id; (void)internal; fail(context,EXR_FORMAT,"XMP document types are not allowed");
}
exr_status exr_metadata_read_xmp(const void *data,size_t size,const exr_control *control,exr_metadata_entry **out,size_t *count,exr_error *e) {
  xmp_reader r={0}; size_t at=0; exr_status status;
  if(out) *out=NULL;
  if(count) *count=0;
  if(!data || !size || !out || !count) return exr_fail(e,EXR_ARGUMENT,"Missing XMP packet or output");
  if(size>1024*1024) return exr_fail(e,EXR_LIMIT,"XMP packet exceeds 1 MiB");
  r.error=e; r.parser=XML_ParserCreateNS(NULL,'|'); if(!r.parser) return exr_fail(e,EXR_MEMORY,"XMP parser allocation failed");
  XML_SetUserData(r.parser,&r); XML_SetElementHandler(r.parser,start,end); XML_SetCharacterDataHandler(r.parser,characters);
  XML_SetStartDoctypeDeclHandler(r.parser,doctype); XML_SetParamEntityParsing(r.parser,XML_PARAM_ENTITY_PARSING_NEVER);
  while(at<size && r.status==EXR_OK) {
    size_t n=size-at; if(n>4096) n=4096;
    r.status=exr_control_poll(control,EXR_STAGE_READ,at,size,e); if(r.status!=EXR_OK) break;
    if(XML_Parse(r.parser,(const char *)data+at,(int)n,at+n==size)==XML_STATUS_ERROR && r.status==EXR_OK) r.status=exr_fail(e,EXR_FORMAT,"Invalid XMP XML");
    at+=n;
  }
  if(r.status==EXR_OK && !r.saw_rdf) r.status=exr_fail(e,EXR_FORMAT,"XMP contains no RDF metadata");
  if(r.status==EXR_OK) r.status=exr_control_poll(control,EXR_STAGE_READ,size,size,e);
  status=r.status;
  if(status==EXR_OK) { *out=r.entries; *count=r.count; if(!r.count) { free(r.entries); *out=NULL; } }
  else exr_metadata_free(r.entries,r.count);
  XML_ParserFree(r.parser); free(r.key); free(r.text.data); free(r.alternative.data);
  return status==EXR_OK ? exr_fail(e,EXR_OK,"") : status;
}
