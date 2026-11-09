/* SPDX-License-Identifier: MIT */
#include "document_internal.h"

#define CFI_MAX 65536u
/* The immutable parsed representation retains validated lexemes, so unknown
   extension parameters and assertion order survive serialization exactly. */
struct exr_cfi { char *data; size_t size,comma[2]; int range; };
typedef struct {
  const char *s; size_t at,end,steps; exr_cfi_diagnostic diagnostic;
  int side,offset;
} lexer;
static int reject(lexer *l,exr_cfi_error_code code) {
  if(!l->diagnostic.code) l->diagnostic=(exr_cfi_diagnostic){code,l->at};
  return 0;
}
static char peek(const lexer *l) { return l->at<l->end ? l->s[l->at] : 0; }
static int digit(char c) { return c>='0' && c<='9'; }
static int number(lexer *l,int decimal) {
  size_t begin=l->at,value=0;int fraction=0;
  if(!digit(peek(l))) return reject(l,EXR_CFI_NUMBER);
  do {
    unsigned d=(unsigned)(peek(l)-'0');
    if(value>(SIZE_MAX-d)/10) return reject(l,EXR_CFI_NUMBER);
    value=value*10+d; l->at++;
  } while(digit(peek(l)));
  if(l->at-begin>1 && l->s[begin]=='0') return reject(l,EXR_CFI_NUMBER);
  if(decimal && peek(l)=='.') {
    fraction=1;
    l->at++; begin=l->at;
    while(digit(peek(l))) l->at++;
    if(begin==l->at || l->s[l->at-1]=='0') return reject(l,EXR_CFI_NUMBER);
  }
  if(decimal==2 && (value>100 || (value==100 && fraction))) return reject(l,EXR_CFI_NUMBER);
  return 1;
}
/* assertion value state: escapes consume exactly one reserved character. */
static int value(lexer *l,int key) {
  size_t begin=l->at;
  while(peek(l) && peek(l)!=']' && peek(l)!=',' && peek(l)!=';' && peek(l)!='=') {
    char c=peek(l);
    if(c=='^') {
      l->at++;
      if(!peek(l) || !strchr("^[](),;=",peek(l))) return reject(l,EXR_CFI_ESCAPE);
    } else if(c=='[' || c=='(' || c==')' || (key && c==' ')) return reject(l,EXR_CFI_ASSERTION);
    l->at++;
  }
  return l->at>begin ? 1 : reject(l,EXR_CFI_ASSERTION);
}
static int assertion(lexer *l,int text) {
  int has=0,seen_side=0;
  if(peek(l)!='[') return 1;
  l->at++;
  if(peek(l)!=';' && peek(l)!=',') { if(!value(l,0)) return 0; has=1; }
  if(peek(l)==',') {
    if(!text) return reject(l,EXR_CFI_ASSERTION);
    l->at++; if(!value(l,0)) return 0; has=1;
  }
  while(peek(l)==';') {
    size_t key,end,begin;
    l->at++; key=l->at;
    if(!value(l,1)) return 0;
    end=l->at;
    if(peek(l)!='=') return reject(l,EXR_CFI_ASSERTION);
    l->at++; begin=l->at;
    if(!value(l,0)) return 0;
    if(end-key==1 && l->s[key]=='s') {
      if(seen_side || l->at-begin!=1 || (l->s[begin]!='a' && l->s[begin]!='b')) return reject(l,EXR_CFI_ASSERTION);
      l->side=seen_side=1;
    } else {
      while(peek(l)==',') { l->at++; if(!value(l,0)) return 0; }
    }
    has=1;
  }
  if(!has || peek(l)!=']') return reject(l,EXR_CFI_ASSERTION);
  l->at++; return 1;
}
/* path state: steps -> indirection/steps -> one terminal offset. */
static int path(lexer *l,int required) {
  size_t begin=l->at; int need_step=required,terminal=0;
  l->offset=l->side=0;
  for(;;) {
    char c=peek(l);
    if(c=='/') {
      if(terminal || l->side) return reject(l,EXR_CFI_SYNTAX);
      if(++l->steps>768) return reject(l,EXR_CFI_LIMIT);
      l->at++; if(!number(l,0) || !assertion(l,0)) return 0;
      need_step=0;
    } else if(c=='!') {
      if(terminal || l->side || need_step || (required && l->at==begin)) return reject(l,EXR_CFI_SYNTAX);
      l->at++;
      if(peek(l)!='/' && peek(l)!=':' && peek(l)!='@' && peek(l)!='~') return reject(l,EXR_CFI_SYNTAX);
    } else if(c==':' || c=='~' || c=='@') {
      int spatial=0;
      if(terminal || l->side || need_step) return reject(l,EXR_CFI_SYNTAX);
      l->at++;
      if(!number(l,c=='@' ? 2 : c!=':')) return 0;
      if(c=='@') {
        spatial=1;
        if(peek(l)!=':') return reject(l,EXR_CFI_SYNTAX);
        l->at++; if(!number(l,2)) return 0;
      } else if(c=='~' && peek(l)=='@') {
        spatial=1; l->at++; if(!number(l,2)) return 0;
        if(peek(l)!=':') return reject(l,EXR_CFI_SYNTAX);
        l->at++; if(!number(l,2)) return 0;
      }
      if(!assertion(l,c==':')) return 0;
      if(spatial && l->side) return reject(l,EXR_CFI_ASSERTION);
      l->offset=terminal=1;
    } else break;
  }
  if(need_step) return reject(l,EXR_CFI_SYNTAX);
  return 1;
}
exr_status exr_cfi_parse(const char *s,exr_cfi **out,exr_cfi_diagnostic *diagnostic,exr_error *e) {
  lexer l={0}; exr_cfi *result=NULL; size_t n=0,begin=0,at=0,commas[2]={0,0}; uint32_t cp; int range=0;
  if(out) *out=NULL;
  if(diagnostic) *diagnostic=(exr_cfi_diagnostic){EXR_CFI_VALID,0};
  if(!s || !out) return exr_fail(e,EXR_ARGUMENT,"Missing CFI input/output");
  while(n<=CFI_MAX && s[n]) n++;
  l.s=s; l.end=n;
  if(n>CFI_MAX) { l.at=CFI_MAX;reject(&l,EXR_CFI_LIMIT);goto bad; }
  while(at<n) {
    l.at=at;
    if(!exr_next(s,n,&at,&cp) || (cp<32 && cp!=9 && cp!=10 && cp!=13) || cp==0xfffe || cp==0xffff) {
      reject(&l,EXR_CFI_ENCODING); goto bad;
    }
  }
  if(n>=8 && !memcmp(s,"epubcfi(",8)) {
    begin=8;
    if(n<10 || s[n-1]!=')') { l.at=n;reject(&l,EXR_CFI_SYNTAX);goto bad; }
    l.end=n-1;
  }
  l.at=begin;
  if(!path(&l,1)) goto bad;
  if(peek(&l)==',') {
    int side=l.side;
    if(l.offset) { reject(&l,EXR_CFI_RANGE);goto bad; }
    range=1; commas[0]=l.at-begin; l.at++;
    if(!path(&l,0)) goto bad;
    side|=l.side;
    if(peek(&l)!=',') { reject(&l,EXR_CFI_RANGE);goto bad; }
    commas[1]=l.at-begin; l.at++;
    if(!path(&l,0)) goto bad;
    if(side || l.side) { reject(&l,EXR_CFI_RANGE);goto bad; }
  }
  if(l.at!=l.end) { reject(&l,EXR_CFI_SYNTAX);goto bad; }
  if(l.end-begin>CFI_MAX-9) { reject(&l,EXR_CFI_LIMIT);goto bad; }
  result=EXR_NEW(exr_cfi);
  if(!result) return exr_fail(e,EXR_MEMORY,"CFI allocation failed");
  result->size=l.end-begin; result->data=exr_copy(s+begin,result->size);
  if(!result->data) { free(result);return exr_fail(e,EXR_MEMORY,"CFI allocation failed"); }
  result->range=range;result->comma[0]=commas[0];result->comma[1]=commas[1];*out=result;
  return exr_fail(e,EXR_OK,"");
bad:
  if(diagnostic) *diagnostic=l.diagnostic;
  return exr_fail(e,l.diagnostic.code==EXR_CFI_ENCODING ? EXR_ENCODING : l.diagnostic.code==EXR_CFI_LIMIT ? EXR_LIMIT : EXR_FORMAT,
    "CFI error %u at byte %zu",(unsigned)l.diagnostic.code,l.diagnostic.byte);
}
static exr_status wrapped(const char *base,size_t nb,const char *tail,size_t nt,char **out,exr_error *e) {
  exr_buffer b={0};
  if(!exr_append(&b,"epubcfi(",8) || !exr_append(&b,base,nb) || !exr_append(&b,tail,nt) || !exr_append(&b,")",1)) {
    free(b.data);return exr_fail(e,EXR_MEMORY,"CFI serialization allocation failed");
  }
  *out=b.data;return exr_fail(e,EXR_OK,"");
}
exr_status exr_cfi_serialize(const exr_cfi *c,char **out,exr_error *e) {
  if(out) *out=NULL;
  if(!c || !out) return exr_fail(e,EXR_ARGUMENT,"Missing parsed CFI/output");
  return wrapped(c->data,c->size,"",0,out,e);
}
int exr_cfi_is_range(const exr_cfi *c) { return c && c->range; }
exr_status exr_cfi_endpoints(const exr_cfi *c,char **a,char **b,exr_error *e) {
  exr_status status;
  if(a) *a=NULL;
  if(b) *b=NULL;
  if(!c || !a || !b || a==b) return exr_fail(e,EXR_ARGUMENT,"Missing/distinct CFI endpoint outputs required");
  if(!c->range) {
    status=exr_cfi_serialize(c,a,e);
    if(status==EXR_OK) status=exr_cfi_serialize(c,b,e);
  } else {
    status=wrapped(c->data,c->comma[0],c->data+c->comma[0]+1,c->comma[1]-c->comma[0]-1,a,e);
    if(status==EXR_OK) status=wrapped(c->data,c->comma[0],c->data+c->comma[1]+1,c->size-c->comma[1]-1,b,e);
  }
  if(status!=EXR_OK) { free(*a);free(*b);*a=*b=NULL; }
  return status;
}
void exr_cfi_free(exr_cfi *c) { if(c) { free(c->data);free(c); } }
