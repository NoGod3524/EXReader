/* SPDX-License-Identifier: MIT */
#include "document_internal.h"
#define JSON_LIMIT ((size_t)1024*1024)
#define CONTEXT "http://www.w3.org/ns/anno.jsonld"
typedef struct { const char *data; size_t size,at; exr_status status; } json_reader;
static int put(exr_buffer *b,const char *s,size_t n) { return n<=JSON_LIMIT-b->size && exr_append(b,s,n); }
static int literal(exr_buffer *b,const char *s) { return put(b,s,strlen(s)); }
static int string_ok(const char *s,size_t maximum,int required) {
  size_t n=0,at=0; uint32_t cp;
  if(!s) return !required;
  while(n<=maximum && s[n]) n++;
  if(n>maximum || (required && !n)) return 0;
  while(at<n) if(!exr_next(s,n,&at,&cp)) return 0;
  return 1;
}
static int quote(exr_buffer *b,const char *s) {
  const unsigned char *p=(const unsigned char *)s; char escape[7];
  if(!literal(b,"\"")) return 0;
  while(*p) {
    if(*p=='"' || *p=='\\') { char pair[2]={'\\',(char)*p++}; if(!put(b,pair,2)) return 0; }
    else if(*p<32) { snprintf(escape,sizeof(escape),"\\u%04x",(unsigned)*p++); if(!literal(b,escape)) return 0; }
    else { if(!put(b,(const char *)p,1)) return 0; p++; }
  }
  return literal(b,"\"");
}
void exr_text_annotation_free(exr_text_annotation *a) {
  if(a) { free(a->id); free(a->source); free(a->text); exr_anchor_free(&a->anchor); memset(a,0,sizeof(*a)); }
}
exr_status exr_text_annotation_export(const exr_text_annotation *a,char **out,size_t *size,exr_error *e) {
  exr_buffer b={0}; exr_status status;
  if(out) *out=NULL;
  if(size) *size=0;
  if(!a || !out || !size || !a->text || !a->anchor.exact ||
     !string_ok(a->id,4096,0) || !string_ok(a->source,4096,1) || !string_ok(a->text,JSON_LIMIT,0))
    return exr_fail(e,EXR_ARGUMENT,"Invalid text annotation or UTF-8 metadata");
  status=exr_anchor_validate(&a->anchor,e); if(status!=EXR_OK) return status;
  if(!literal(&b,"{\"@context\":\"" CONTEXT "\",\"type\":\"Annotation\"")) goto failed;
  if(a->id && (!literal(&b,",\"id\":") || !quote(&b,a->id))) goto failed;
  if(!literal(&b,",\"body\":{\"type\":\"TextualBody\",\"format\":\"text/plain\",\"value\":") || !quote(&b,a->text) ||
     !literal(&b,"},\"target\":{\"type\":\"SpecificResource\",\"source\":") || !quote(&b,a->source) ||
     !literal(&b,",\"selector\":{\"type\":\"TextQuoteSelector\",\"exact\":") || !quote(&b,a->anchor.exact)) goto failed;
  if(a->anchor.prefix && (!literal(&b,",\"prefix\":") || !quote(&b,a->anchor.prefix))) goto failed;
  if(a->anchor.suffix && (!literal(&b,",\"suffix\":") || !quote(&b,a->anchor.suffix))) goto failed;
  if(!literal(&b,"}}}")) goto failed;
  *out=b.data; *size=b.size; return exr_fail(e,EXR_OK,"");
failed:
  free(b.data); return exr_fail(e,EXR_LIMIT,"Annotation JSON exceeds 1 MiB or allocation failed");
}
static void space(json_reader *r) { while(r->at<r->size && strchr(" \t\r\n",r->data[r->at])) r->at++; }
static int take(json_reader *r,char c) { space(r); if(r->at==r->size || r->data[r->at]!=c) return 0; r->at++; return 1; }
static int hex4(json_reader *r,uint32_t *out) {
  unsigned i; uint32_t cp=0;
  for(i=0;i<4;i++) { unsigned char c; unsigned digit; if(r->at==r->size) return 0; c=(unsigned char)r->data[r->at++];
    if(c>='0' && c<='9') digit=c-'0'; else if(c>='a' && c<='f') digit=c-'a'+10; else if(c>='A' && c<='F') digit=c-'A'+10; else return 0;
    cp=cp*16+digit;
  }
  *out=cp; return 1;
}
static char *string(json_reader *r) {
  exr_buffer b={0}; int closed=0;
  if(!take(r,'"')) return NULL;
  while(r->at<r->size) {
    unsigned char c=(unsigned char)r->data[r->at++];
    if(c=='"') { closed=1; break; }
    if(c<32) goto failed;
    if(c=='\\') {
      const char *escapes="\"\\/bfnrt",*mapped="\"\\/\b\f\n\r\t",*found; uint32_t cp,low;
      if(r->at==r->size) goto failed;
      c=(unsigned char)r->data[r->at++];
      if(c=='u') {
        if(!hex4(r,&cp)) goto failed;
        if(cp>=0xd800 && cp<=0xdbff) {
          if(r->size-r->at<2 || r->data[r->at++]!='\\' || r->data[r->at++]!='u' || !hex4(r,&low) || low<0xdc00 || low>0xdfff) goto failed;
          cp=0x10000+((cp-0xd800)<<10)+(low-0xdc00);
        }
        if(!cp || (cp>=0xdc00 && cp<=0xdfff)) goto failed;
        if(!exr_codepoint(&b,cp)) { r->status=EXR_MEMORY; goto failed; }
        continue;
      }
      found=strchr(escapes,c); if(!found) goto failed; c=(unsigned char)mapped[found-escapes];
    }
    if(!exr_append(&b,&c,1)) { r->status=EXR_MEMORY; goto failed; }
  }
  if(!closed) goto failed;
  if(!b.data) { b.data=exr_copy("",0); if(!b.data) { r->status=EXR_MEMORY; goto failed; } }
  if(!string_ok(b.data,JSON_LIMIT,0)) goto failed;
  return b.data;
failed:
  free(b.data); return NULL;
}
static int skip(json_reader *r,unsigned depth) {
  char c; space(r); if(depth>32 || r->at==r->size) return 0; c=r->data[r->at];
  if(c=='"') { char *value=string(r); if(!value) return 0; free(value); return 1; }
  if(c=='{' || c=='[') {
    char close=c=='{' ? '}' : ']'; r->at++; if(take(r,close)) return 1;
    do {
      if(c=='{') { char *key=string(r); if(!key) return 0; free(key); if(!take(r,':')) return 0; }
      if(!skip(r,depth+1)) return 0;
      if(take(r,close)) return 1;
    } while(take(r,','));
    return 0;
  }
  if(c=='t' || c=='f' || c=='n') {
    const char *word=c=='t' ? "true" : c=='f' ? "false" : "null"; size_t n=strlen(word);
    if(r->size-r->at<n || memcmp(r->data+r->at,word,n)) return 0;
    r->at+=n; return 1;
  }
  /* Validate JSON number grammar without losing precision through a float. */
  if(c=='-') r->at++;
  if(r->at==r->size) return 0;
  c=r->data[r->at++]; if(c!='0') { if(c<'1' || c>'9') return 0; while(r->at<r->size && r->data[r->at]>='0' && r->data[r->at]<='9') r->at++; }
  if(r->at<r->size && r->data[r->at]=='.') { size_t start=++r->at; while(r->at<r->size && r->data[r->at]>='0' && r->data[r->at]<='9') r->at++; if(start==r->at) return 0; }
  if(r->at<r->size && (r->data[r->at]=='e' || r->data[r->at]=='E')) { size_t start; r->at++; if(r->at<r->size && (r->data[r->at]=='+' || r->data[r->at]=='-')) r->at++; start=r->at; while(r->at<r->size && r->data[r->at]>='0' && r->data[r->at]<='9') r->at++; if(start==r->at) return 0; }
  return 1;
}
/* Each supported object has fixed known fields; unknown metadata is validated
   and skipped, rather than allocated as an unbounded JSON DOM. */
static int object(json_reader *r,unsigned kind,exr_text_annotation *a) {
  static const char *keys[][8]={
    {"@context","type","id","body","target",NULL},
    {"type","format","value",NULL},
    {"type","source","selector",NULL},
    {"type","exact","prefix","suffix",NULL}
  };
  unsigned seen=0;
  if(!take(r,'{') || take(r,'}')) return 0;
  do {
    char *key=string(r),*value=NULL; unsigned k=0; char **destination=NULL; int valid=1;
    if(!key) return 0;
    while(keys[kind][k] && strcmp(key,keys[kind][k])) k++;
    if((key[0]=='@' && !(kind==0 && !strcmp(key,"@context"))) ||
       (kind==2 && (!strcmp(key,"scope") || !strcmp(key,"state"))) ||
       (kind==3 && !strcmp(key,"refinedBy"))) { free(key); return 0; }
    free(key); if(!take(r,':')) return 0;
    if(!keys[kind][k]) { if(!skip(r,1)) return 0; }
    else {
      if(seen&(1u<<k)) return 0;
      seen|=1u<<k;
      if(kind==0 && (k==3 || k==4)) { if(!object(r,k==3 ? 1 : 2,a)) return 0; }
      else if(kind==2 && k==2) { if(!object(r,3,a)) return 0; }
      else {
        value=string(r); if(!value) return 0;
        if(kind==0) { if(k==0) valid=!strcmp(value,CONTEXT); else if(k==1) valid=!strcmp(value,"Annotation"); else destination=&a->id; }
        else if(kind==1) { if(k==0) valid=!strcmp(value,"TextualBody"); else if(k==1) valid=!strcmp(value,"text/plain"); else destination=&a->text; }
        else if(kind==2) { if(k==0) valid=!strcmp(value,"SpecificResource"); else destination=&a->source; }
        else { if(k==0) valid=!strcmp(value,"TextQuoteSelector"); else if(k==1) destination=&a->anchor.exact; else if(k==2) destination=&a->anchor.prefix; else destination=&a->anchor.suffix; }
        if(destination) *destination=value; else free(value);
        if(!valid) return 0;
      }
    }
    if(take(r,'}')) {
      unsigned required=kind==0 ? 27u : kind==1 ? 5u : kind==2 ? 6u : 3u;
      return (seen&required)==required;
    }
  } while(take(r,','));
  return 0;
}
exr_status exr_text_annotation_import(const void *json,size_t size,exr_text_annotation *out,exr_error *e) {
  exr_text_annotation a={0}; json_reader r={(const char *)json,size,0,EXR_FORMAT}; exr_status status;
  if(out) memset(out,0,sizeof(*out));
  if(!json || !out || !size) return exr_fail(e,EXR_ARGUMENT,"Missing annotation JSON or output");
  if(size>JSON_LIMIT) return exr_fail(e,EXR_LIMIT,"Annotation JSON exceeds 1 MiB");
  a.anchor.start=a.anchor.end=SIZE_MAX;
  if(memchr(json,0,size) || !object(&r,0,&a)) goto invalid;
  space(&r); if(r.at!=size || !string_ok(a.id,4096,0) || !string_ok(a.source,4096,1)) goto invalid;
  status=exr_anchor_validate(&a.anchor,e); if(status!=EXR_OK) { exr_text_annotation_free(&a); return status; }
  *out=a; return exr_fail(e,EXR_OK,"");
invalid:
  exr_text_annotation_free(&a); return exr_fail(e,r.status,"Invalid or unsupported text annotation JSON profile");
}
