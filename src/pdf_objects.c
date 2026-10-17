/* SPDX-License-Identifier: GPL-3.0-only */
#include "pdf_internal.h"
#include <miniz.h>
#include <inttypes.h>
#define PDF_MAX_OBJECTS 1048576u
#define PDF_MAX_VALUES EXR_PDF_MAX_VALUES
#define PDF_MAX_STRINGS ((size_t)32*1024*1024)
typedef struct { size_t offset; uint32_t value,revision; unsigned generation,type,state,seen; uint32_t compressed_index; } pdf_xref;
typedef struct { size_t offset,size; unsigned char *decoded; size_t decoded_size; uint32_t dict; int ready; uint32_t *objects,*offsets; size_t object_count,first; exr_pdf_stream_codec codec; uint32_t parameters; } pdf_stream;
struct exr_pdf_file {
  const unsigned char *data; size_t size,work,decoded_bytes,decode_work,declared_size,index_bytes;
  exr_pdf_value *values; size_t value_count,value_capacity;
  exr_buffer strings;
  pdf_xref *xref; size_t xref_count,xref_capacity;
  pdf_stream *streams; size_t stream_count,stream_capacity;
  uint32_t root,info,revision,raw_root,trailer_id; size_t startxref;
  unsigned resolving,loading_xref;
  exr_error error;
};
typedef struct { exr_pdf_file *file; const unsigned char *data; size_t size,at; } parser;
static int failed(exr_pdf_file *f,exr_status status,const char *message) {
  if(f->error.code==EXR_OK) exr_fail(&f->error,status,"%s",message);
  return 0;
}
static int whitespace(unsigned c) { return !c || c==9 || c==10 || c==12 || c==13 || c==32; }
static int delimiter(unsigned c) { return whitespace(c) || strchr("()<>[]{}/%",(int)c)!=NULL; }
static int skip(parser *p) {
  size_t first=p->at;
  if(p->file->error.code!=EXR_OK) return 0;
  while(p->at<p->size) {
    unsigned c=p->data[p->at];
    if(whitespace(c)) p->at++;
    else if(c=='%') { while(p->at<p->size && p->data[p->at]!=10 && p->data[p->at]!=13) p->at++; }
    else break;
  }
  if(p->at-first>(size_t)256*1024*1024-p->file->work) return failed(p->file,EXR_LIMIT,"PDF parsing work budget exceeded");
  p->file->work+=p->at-first; return p->file->error.code==EXR_OK;
}
static int word(parser *p,const char *text) {
  size_t n=strlen(text);
  if(!skip(p) || n>p->size-p->at || memcmp(p->data+p->at,text,n) ||
     (p->at+n<p->size && !delimiter(p->data[p->at+n]))) return 0;
  p->at+=n; return 1;
}
static int integer_token(parser *p,uint64_t *out) {
  size_t first; uint64_t value=0;
  if(!skip(p)) return 0;
  first=p->at;
  while(p->at<p->size && p->data[p->at]>='0' && p->data[p->at]<='9') {
    unsigned digit=p->data[p->at++]-'0';
    if(value>(UINT64_MAX-digit)/10) return failed(p->file,EXR_LIMIT,"PDF integer overflow");
    value=value*10+digit;
  }
  if(p->at==first || (p->at<p->size && !delimiter(p->data[p->at]))) return 0;
  *out=value; return 1;
}
static uint32_t value_new(exr_pdf_file *f,exr_pdf_kind kind) {
  uint32_t id; exr_pdf_value *v;
  if(f->value_count>=PDF_MAX_VALUES) { failed(f,EXR_LIMIT,"PDF value limit exceeded"); return EXR_PDF_NONE; }
  if(!exr_grow((void **)&f->values,&f->value_capacity,f->value_count+1,sizeof(*f->values))) {
    failed(f,EXR_MEMORY,"PDF value allocation failed"); return EXR_PDF_NONE;
  }
  id=(uint32_t)f->value_count++; v=&f->values[id]; memset(v,0,sizeof(*v));
  v->kind=kind; v->first=v->next=EXR_PDF_NONE; return id;
}
static int append(exr_pdf_file *f,exr_buffer *b,const void *data,size_t size) {
  if(size>PDF_MAX_STRINGS-b->size) return failed(f,EXR_LIMIT,"PDF string payload exceeds 32 MiB");
  return exr_append(b,data,size) || failed(f,EXR_MEMORY,"PDF string allocation failed");
}
static uint32_t string_new(exr_pdf_file *f,exr_pdf_kind kind,const void *data,size_t size) {
  uint32_t id; size_t offset=f->strings.size;
  if(!append(f,&f->strings,data,size)) return EXR_PDF_NONE;
  id=value_new(f,kind); if(id==EXR_PDF_NONE) return id;
  f->values[id].u.bytes.offset=(uint32_t)offset; f->values[id].u.bytes.length=(uint32_t)size; return id;
}
static int hex(unsigned c) {
  return c>='0' && c<='9' ? (int)c-'0' : c>='A' && c<='F' ? (int)c-'A'+10 : c>='a' && c<='f' ? (int)c-'a'+10 : -1;
}
static uint32_t parse_string(parser *p,int name,int hexadecimal) {
  exr_buffer b={0}; exr_pdf_file *f=p->file; unsigned depth=1; uint32_t id=EXR_PDF_NONE; int high=-1,closed=name;
  p->at++;
  while(p->at<p->size) {
    unsigned char c=p->data[p->at++];
    if(name) {
      if(delimiter(c)) { p->at--; break; }
      if(c=='#' && p->size-p->at>=2 && hex(p->data[p->at])>=0 && hex(p->data[p->at+1])>=0) {
        c=(unsigned char)((hex(p->data[p->at])<<4)|hex(p->data[p->at+1])); p->at+=2;
      }
    } else if(hexadecimal) {
      int digit;
      if(c=='>') { closed=1; break; }
      if(whitespace(c)) continue;
      digit=hex(c); if(digit<0) { failed(f,EXR_FORMAT,"Invalid PDF hex string"); goto done; }
      if(high<0) { high=digit; continue; }
      c=(unsigned char)((high<<4)|digit); high=-1;
    } else if(c=='\\') {
      unsigned k;
      if(p->at==p->size) break;
      c=p->data[p->at++];
      if(c==10 || c==13) { if(c==13 && p->at<p->size && p->data[p->at]==10) p->at++; continue; }
      if(c>='0' && c<='7') {
        unsigned octal=c-'0';
        for(k=1;k<3 && p->at<p->size && p->data[p->at]>='0' && p->data[p->at]<='7';k++) octal=(octal<<3)|(p->data[p->at++]-'0');
        c=(unsigned char)octal;
      } else if(c=='n') c=10; else if(c=='r') c=13; else if(c=='t') c=9; else if(c=='b') c=8; else if(c=='f') c=12;
    } else if(c=='(') {
      if(++depth>128) { failed(f,EXR_LIMIT,"PDF literal string nesting exceeds 128"); goto done; }
    } else if(c==')') { if(!--depth) { closed=1; break; } }
    else if(c==13) { c=10; if(p->at<p->size && p->data[p->at]==10) p->at++; }
    if(!append(f,&b,&c,1)) goto done;
  }
  if(!closed) { failed(f,EXR_FORMAT,"Unterminated PDF string"); goto done; }
  if(hexadecimal && high>=0) { unsigned char c=(unsigned char)(high<<4); if(!append(f,&b,&c,1)) goto done; }
  id=string_new(f,name ? EXR_PDF_NAME : EXR_PDF_STRING,b.data,b.size);
done:
  free(b.data); return id;
}
static uint32_t parse_value(parser *p,unsigned depth);
static uint32_t parse_collection(parser *p,int dict,unsigned depth) {
  exr_pdf_file *f=p->file; uint32_t id=value_new(f,dict ? EXR_PDF_DICT : EXR_PDF_ARRAY),previous=EXR_PDF_NONE;
  size_t count=0;
  if(id==EXR_PDF_NONE) return id;
  p->at+=dict ? 2 : 1;
  while(skip(p) && p->at<p->size) {
    uint32_t key=EXR_PDF_NONE,item;
    if(dict ? p->size-p->at>=2 && p->data[p->at]=='>' && p->data[p->at+1]=='>' : p->data[p->at]==']') {
      p->at+=dict ? 2 : 1; return id;
    }
    if(++count>262144) { failed(f,EXR_LIMIT,"PDF collection exceeds item limit"); break; }
    if(dict) {
      if(p->data[p->at]!='/') { failed(f,EXR_FORMAT,"PDF dictionary key is not a name"); break; }
      key=parse_string(p,1,0); if(key==EXR_PDF_NONE) break;
    }
    item=parse_value(p,depth+1); if(item==EXR_PDF_NONE) break;
    if(dict) f->values[key].next=item;
    if(previous==EXR_PDF_NONE) f->values[id].first=dict ? key : item;
    else f->values[previous].next=dict ? key : item;
    previous=item;
  }
  failed(f,EXR_FORMAT,"Unterminated PDF array or dictionary"); return EXR_PDF_NONE;
}
static uint32_t parse_value(parser *p,unsigned depth) {
  exr_pdf_file *f=p->file; uint32_t id; size_t first,end; int negative=0,real=0,digits=0; double n=0,fraction=0.1;
  if(depth>128) { failed(f,EXR_LIMIT,"PDF value nesting exceeds 128"); return EXR_PDF_NONE; }
  if(!skip(p) || p->at==p->size) goto bad;
  if(++f->work>(size_t)256*1024*1024) { failed(f,EXR_LIMIT,"PDF parsing work budget exceeded"); return EXR_PDF_NONE; }
  if(p->data[p->at]=='/') return parse_string(p,1,0);
  if(p->data[p->at]=='(') return parse_string(p,0,0);
  if(p->data[p->at]=='[') return parse_collection(p,0,depth);
  if(p->data[p->at]=='<') {
    if(p->size-p->at>=2 && p->data[p->at+1]=='<') return parse_collection(p,1,depth);
    return parse_string(p,0,1);
  }
  if(word(p,"null")) return value_new(f,EXR_PDF_NULL);
  if(word(p,"true")) { id=value_new(f,EXR_PDF_BOOL); if(id!=EXR_PDF_NONE) f->values[id].u.number=1; return id; }
  if(word(p,"false")) return value_new(f,EXR_PDF_BOOL);
  first=p->at;
  if(p->data[p->at]=='-' || p->data[p->at]=='+') negative=p->data[p->at++]=='-';
  while(p->at<p->size) {
    unsigned c=p->data[p->at];
    if(c=='.' && !real) { real=1; p->at++; continue; }
    if(c<'0' || c>'9') break;
    if(real) { n+=(c-'0')*fraction; fraction*=0.1; } else n=n*10+(c-'0');
    digits++; p->at++;
    if(p->at-first>384 || !isfinite(n)) { failed(f,EXR_LIMIT,"PDF number exceeds precision limit"); return EXR_PDF_NONE; }
  }
  if(!digits || (p->at<p->size && !delimiter(p->data[p->at]))) goto bad;
  end=p->at;
  if(!real && !negative && n<=PDF_MAX_OBJECTS) {
    uint64_t generation;
    if(integer_token(p,&generation) && generation<=65535 && word(p,"R")) {
      id=value_new(f,EXR_PDF_REF);
      if(id!=EXR_PDF_NONE) { f->values[id].u.ref.object=(uint32_t)n; f->values[id].u.ref.generation=(uint32_t)generation; }
      return id;
    }
    p->at=end;
  }
  id=value_new(f,real ? EXR_PDF_REAL : EXR_PDF_INT);
  if(id!=EXR_PDF_NONE) {
    if(real) {
      unsigned char length[2]={(unsigned char)(end-first),(unsigned char)((end-first)>>8)};
      f->values[id].u.number=negative ? -n : n;
      /* Retain the spelling: serializing the decoded double alone can change
         unknown dictionary numbers after repeated incremental edits. */
      f->values[id].first=(uint32_t)f->strings.size;
      if(!append(f,&f->strings,length,2) || !append(f,&f->strings,p->data+first,end-first)) return EXR_PDF_NONE;
    }
    else {
      uint64_t whole=0,maximum=negative ? (UINT64_C(1)<<63) : INT64_MAX; size_t at=first;
      if(p->data[at]=='+' || p->data[at]=='-') at++;
      for(;at<end;at++) {
        unsigned digit=p->data[at]-'0';
        if(whole>(maximum-digit)/10) { failed(f,EXR_LIMIT,"PDF integer exceeds signed 64-bit range"); return EXR_PDF_NONE; }
        whole=whole*10+digit;
      }
      f->values[id].u.integer=negative ? whole==(UINT64_C(1)<<63) ? INT64_MIN : -(int64_t)whole : (int64_t)whole;
    }
  }
  return id;
bad:
  failed(f,EXR_FORMAT,"Invalid PDF value token"); return EXR_PDF_NONE;
}
const exr_pdf_value *exr_pdf_value_at(const exr_pdf_file *f,uint32_t id) { return f && id<f->value_count ? &f->values[id] : NULL; }
const unsigned char *exr_pdf_bytes(const exr_pdf_file *f,uint32_t id,size_t *size) {
  const exr_pdf_value *v=exr_pdf_value_at(f,id); if(size) *size=0;
  if(!v || (v->kind!=EXR_PDF_NAME && v->kind!=EXR_PDF_STRING)) return NULL;
  if(size) *size=v->u.bytes.length;
  return v->u.bytes.length ? (const unsigned char *)f->strings.data+v->u.bytes.offset : (const unsigned char *)"";
}
uint32_t exr_pdf_get(exr_pdf_file *f,uint32_t dict,const char *key) {
  const exr_pdf_value *d=exr_pdf_value_at(f,dict); uint32_t at,result=EXR_PDF_NONE; size_t length=strlen(key);
  if(!d || (d->kind!=EXR_PDF_DICT && d->kind!=EXR_PDF_STREAM)) return result;
  for(at=d->first;at!=EXR_PDF_NONE;) {
    const exr_pdf_value *k=&f->values[at]; uint32_t value=k->next;
    if(++f->work>(size_t)256*1024*1024) { failed(f,EXR_LIMIT,"PDF lookup work budget exceeded"); return EXR_PDF_NONE; }
    if(k->u.bytes.length==length && !memcmp(f->strings.data+k->u.bytes.offset,key,length)) result=value;
    at=f->values[value].next;
  }
  return result;
}
static int direct_integer(exr_pdf_file *f,uint32_t id,uint64_t maximum,uint64_t *out) {
  const exr_pdf_value *v=exr_pdf_value_at(f,id);
  if(!v || v->kind!=EXR_PDF_INT || v->u.integer<0 || (uint64_t)v->u.integer>maximum) return 0;
  *out=(uint64_t)v->u.integer; return 1;
}
static uint32_t indirect(parser *p,uint32_t object,unsigned generation);
static uint32_t compressed_object(exr_pdf_file *f,uint32_t object);
static uint32_t resolve(exr_pdf_file *f,uint32_t id) {
  uint32_t seen[64]; size_t count=0,i;
  while(id!=EXR_PDF_NONE && f->error.code==EXR_OK) {
    const exr_pdf_value *v=exr_pdf_value_at(f,id); uint32_t object; unsigned generation;
    if(!v) { failed(f,EXR_FORMAT,"Invalid PDF value index"); return EXR_PDF_NONE; }
    if(v->kind!=EXR_PDF_REF) return id;
    object=v->u.ref.object; generation=v->u.ref.generation;
    if(f->loading_xref) { failed(f,EXR_FORMAT,"Indirect value in PDF cross-reference stream"); return EXR_PDF_NONE; }
    if(object>=f->xref_count || !f->xref[object].seen || !f->xref[object].type || f->xref[object].generation!=generation) return EXR_PDF_NONE;
    for(i=0;i<count;i++) if(seen[i]==object) { failed(f,EXR_FORMAT,"Cyclic PDF reference chain"); return EXR_PDF_NONE; }
    if(count==64 || f->resolving>=64) { failed(f,EXR_LIMIT,"PDF object nesting exceeds 64"); return EXR_PDF_NONE; }
    seen[count++]=object;
    if(f->xref[object].state==1) { failed(f,EXR_FORMAT,"Cyclic PDF object loading"); return EXR_PDF_NONE; }
    if(!f->xref[object].state) {
      parser p={f,f->data,f->size,f->xref[object].offset}; uint32_t loaded;
      f->xref[object].state=1; f->resolving++;
      loaded=f->xref[object].type==2 ? compressed_object(f,object) : indirect(&p,object,generation); f->resolving--;
      if(loaded==EXR_PDF_NONE) return loaded;
      f->xref[object].value=loaded; f->xref[object].state=2;
    }
    id=f->xref[object].value;
  }
  return EXR_PDF_NONE;
}
static uint32_t indirect(parser *p,uint32_t object,unsigned generation) {
  exr_pdf_file *f=p->file; uint64_t number,gen,length; uint32_t id;
  if(!integer_token(p,&number) || !integer_token(p,&gen) || number!=object || gen!=generation || !word(p,"obj")) goto bad;
  id=parse_value(p,0); if(id==EXR_PDF_NONE) return id;
  if(f->values[id].kind==EXR_PDF_DICT && word(p,"stream")) {
    uint32_t length_value=resolve(f,exr_pdf_get(f,id,"Length")); size_t start,index;
    if(!direct_integer(f,length_value,EXR_MAX_INPUT,&length)) goto bad;
    while(p->at<p->size && (p->data[p->at]==' ' || p->data[p->at]==9)) p->at++;
    if(p->at==p->size || (p->data[p->at]!=10 && p->data[p->at]!=13)) goto bad;
    if(p->data[p->at++]==13 && p->at<p->size && p->data[p->at]==10) p->at++;
    start=p->at; if(length>p->size-start) goto bad;
    p->at+=(size_t)length; if(!word(p,"endstream")) goto bad;
    if(f->stream_count>=PDF_MAX_OBJECTS) { failed(f,EXR_LIMIT,"PDF stream count limit exceeded"); return EXR_PDF_NONE; }
    if(!exr_grow((void **)&f->streams,&f->stream_capacity,f->stream_count+1,sizeof(*f->streams))) {
      failed(f,EXR_MEMORY,"PDF stream allocation failed"); return EXR_PDF_NONE;
    }
    index=f->stream_count++; f->streams[index]=(pdf_stream){.offset=start,.size=(size_t)length,.dict=id,.parameters=EXR_PDF_NONE};
    f->values[id].kind=EXR_PDF_STREAM; f->values[id].u.ref.object=(uint32_t)index;
  }
  if(!word(p,"endobj")) goto bad;
  return id;
bad:
  failed(f,EXR_FORMAT,"Invalid PDF indirect object or stream bounds"); return EXR_PDF_NONE;
}
static int xref_room(exr_pdf_file *f,size_t count) {
  size_t previous=f->xref_capacity;
  if(count>PDF_MAX_OBJECTS) return failed(f,EXR_LIMIT,"PDF object number limit exceeded");
  if(!exr_grow((void **)&f->xref,&f->xref_capacity,count,sizeof(*f->xref))) return failed(f,EXR_MEMORY,"PDF xref allocation failed");
  if(f->xref_capacity>previous) memset(f->xref+previous,0,(f->xref_capacity-previous)*sizeof(*f->xref));
  if(count>f->xref_count) f->xref_count=count;
  return 1;
}
static int name_is(exr_pdf_file *f,uint32_t id,const char *expected) {
  size_t n; const unsigned char *bytes=exr_pdf_bytes(f,id,&n);
  return bytes && f->values[id].kind==EXR_PDF_NAME && n==strlen(expected) && !memcmp(bytes,expected,n);
}
static int array_integers(exr_pdf_file *f,uint32_t id,uint64_t *values,size_t capacity,size_t *count) {
  const exr_pdf_value *v=exr_pdf_value_at(f,id); uint32_t at;
  *count=0; if(!v || v->kind!=EXR_PDF_ARRAY) return 0;
  for(at=v->first;at!=EXR_PDF_NONE;at=f->values[at].next) {
    if(*count==capacity || !direct_integer(f,at,UINT32_MAX,&values[*count])) return 0;
    (*count)++;
  }
  return 1;
}
static int stream_xref(parser *p,size_t *previous,uint32_t *root,uint32_t *info,int hybrid) {
  exr_pdf_file *f=p->file; parser start=*p; uint64_t object,generation,size,widths[3],range[2],fields[3];
  uint32_t dict,id,at; const unsigned char *data; size_t length,n,row=0,pos=0,i,k,ranges=0;
  unsigned char *seen=NULL; int ok=0;
  if(!integer_token(p,&object) || !object || object>=PDF_MAX_OBJECTS || !integer_token(p,&generation) || generation) goto bad;
  f->loading_xref=1; dict=indirect(&start,(uint32_t)object,0);
  if(dict==EXR_PDF_NONE || f->values[dict].kind!=EXR_PDF_STREAM || !name_is(f,exr_pdf_get(f,dict,"Type"),"XRef") ||
     !direct_integer(f,exr_pdf_get(f,dict,"Size"),PDF_MAX_OBJECTS,&size) || !size || object>=size ||
     !array_integers(f,exr_pdf_get(f,dict,"W"),widths,3,&n) || n!=3 || !xref_room(f,(size_t)size)) goto bad;
  for(i=0;i<3;i++) { if(widths[i]>8) goto bad; row+=(size_t)widths[i]; }
  if(!row) goto bad;
  id=exr_pdf_get(f,dict,"Encrypt");
  if(id!=EXR_PDF_NONE && f->values[id].kind!=EXR_PDF_NULL) goto bad;
  if(exr_pdf_get(f,dict,"XRefStm")!=EXR_PDF_NONE) goto bad;
  *info=exr_pdf_get(f,dict,"Info");
  *root=exr_pdf_get(f,dict,"Root");
  if(*root!=EXR_PDF_NONE && f->values[*root].kind!=EXR_PDF_REF) goto bad;
  *previous=SIZE_MAX; id=exr_pdf_get(f,dict,"Prev");
  if(id!=EXR_PDF_NONE) { uint64_t offset; if(!direct_integer(f,id,f->size-1,&offset)) goto bad; *previous=(size_t)offset; }
  if(exr_pdf_stream_data(f,dict,&data,&length,NULL)!=EXR_OK) goto bad;
  seen=calloc((size_t)(size+7)/8,1); if(!seen) { failed(f,EXR_MEMORY,"PDF xref validation allocation failed"); goto done; }
  id=exr_pdf_get(f,dict,"Index");
  if(id!=EXR_PDF_NONE && f->values[id].kind!=EXR_PDF_ARRAY) goto bad;
  at=id==EXR_PDF_NONE ? EXR_PDF_NONE : f->values[id].first;
  do {
    if(id==EXR_PDF_NONE) { range[0]=0; range[1]=size; }
    else {
      if(at==EXR_PDF_NONE || !direct_integer(f,at,size,&range[0])) goto bad;
      at=f->values[at].next;
      if(at==EXR_PDF_NONE || !direct_integer(f,at,size-range[0],&range[1])) goto bad;
      at=f->values[at].next;
    }
    if(range[1]>size-range[0] || range[1]>(length-pos)/row || ++ranges>262144) goto bad;
    for(i=0;i<(size_t)range[1];i++) {
      size_t number=(size_t)range[0]+i; pdf_xref *x=&f->xref[number];
      if(seen[number/8]&(1u<<(number%8))) goto bad;
      seen[number/8]|=(unsigned char)(1u<<(number%8));
      fields[0]=widths[0] ? 0 : 1; fields[1]=fields[2]=0;
      for(k=0;k<3;k++) { size_t b; for(b=0;b<(size_t)widths[k];b++) fields[k]=(fields[k]<<8)|data[pos++]; }
      if(fields[0]==1 ? fields[1]>=f->size || fields[2]>65535 :
         fields[0]==2 ? !fields[1] || fields[1]>=size || fields[2]>=PDF_MAX_OBJECTS :
         fields[0]==0 ? fields[1]>=PDF_MAX_OBJECTS || fields[2]>65535 : 0) goto bad;
      if(x->seen && x->revision==f->revision && !hybrid) goto bad;
      if(!x->seen || (hybrid && x->revision==f->revision)) {
        *x=(pdf_xref){(size_t)fields[1],EXR_PDF_NONE,f->revision,fields[0]==2 ? 0 : (unsigned)fields[2],
                     fields[0]<=2 ? (unsigned)fields[0] : 0,0,1,(uint32_t)fields[2]};
      }
    }
  } while(id!=EXR_PDF_NONE && at!=EXR_PDF_NONE);
  if(pos!=length || (id!=EXR_PDF_NONE && !ranges)) goto bad;
  if(f->revision==1 && !hybrid) f->declared_size=(size_t)size;
  if(!hybrid && f->trailer_id==EXR_PDF_NONE) f->trailer_id=exr_pdf_get(f,dict,"ID");
  ok=1; goto done;
bad:
  failed(f,EXR_FORMAT,"Invalid PDF cross-reference stream");
done:
  f->loading_xref=0; free(seen); return ok;
}
static uint32_t compressed_object(exr_pdf_file *f,uint32_t object) {
  pdf_xref entry=f->xref[object]; uint32_t ref=value_new(f,EXR_PDF_REF),dict,id,result;
  size_t index,n,i; const unsigned char *data; uint64_t count,first; parser p;
  if(ref==EXR_PDF_NONE) return ref;
  if(entry.offset>=f->xref_count || f->xref[entry.offset].type!=1) goto bad;
  f->values[ref].u.ref.object=(uint32_t)entry.offset;
  dict=resolve(f,ref);
  if(dict==EXR_PDF_NONE || f->values[dict].kind!=EXR_PDF_STREAM || !name_is(f,exr_pdf_get(f,dict,"Type"),"ObjStm")) goto bad;
  index=f->values[dict].u.ref.object;
  if(exr_pdf_get(f,dict,"Extends")!=EXR_PDF_NONE) { failed(f,EXR_FORMAT,"PDF object stream Extends is not implemented yet"); return EXR_PDF_NONE; }
  if(exr_pdf_stream_data(f,dict,&data,&n,NULL)!=EXR_OK) return EXR_PDF_NONE;
  if(!f->streams[index].objects) {
    uint32_t *numbers=NULL,*offsets=NULL; unsigned char *seen=NULL;
    if(!direct_integer(f,resolve(f,exr_pdf_get(f,dict,"N")),PDF_MAX_OBJECTS,&count) || !count ||
       !direct_integer(f,resolve(f,exr_pdf_get(f,dict,"First")),n,&first) || count>first/3) goto bad;
    if(count*sizeof(uint32_t)*2>PDF_MAX_STRINGS-f->index_bytes) { failed(f,EXR_LIMIT,"PDF object stream index budget exceeded"); return EXR_PDF_NONE; }
    numbers=calloc((size_t)count,sizeof(*numbers)); offsets=calloc((size_t)count,sizeof(*offsets)); seen=calloc(PDF_MAX_OBJECTS/8,1);
    if(!numbers || !offsets || !seen) { free(numbers); free(offsets); free(seen); failed(f,EXR_MEMORY,"PDF object stream index allocation failed"); return EXR_PDF_NONE; }
    p=(parser){f,data,(size_t)first,0};
    for(i=0;i<(size_t)count;i++) {
      uint64_t number,offset;
      if(!integer_token(&p,&number) || !number || number>=PDF_MAX_OBJECTS || !integer_token(&p,&offset) || offset>=n-first ||
         (i && offset<=offsets[i-1]) || (seen[number/8]&(1u<<(number%8)))) break;
      seen[number/8]|=(unsigned char)(1u<<(number%8)); numbers[i]=(uint32_t)number; offsets[i]=(uint32_t)offset;
    }
    free(seen);
    if(i!=(size_t)count || !skip(&p) || p.at!=p.size) { free(numbers); free(offsets); goto bad; }
    f->streams[index].objects=numbers; f->streams[index].offsets=offsets;
    f->index_bytes+=(size_t)count*sizeof(uint32_t)*2;
    f->streams[index].object_count=(size_t)count; f->streams[index].first=(size_t)first;
  }
  i=entry.compressed_index;
  if(i>=f->streams[index].object_count || f->streams[index].objects[i]!=object) goto bad;
  p=(parser){f,data,n,f->streams[index].first+f->streams[index].offsets[i]};
  if(i+1<f->streams[index].object_count) p.size=f->streams[index].first+f->streams[index].offsets[i+1];
  result=parse_value(&p,0); if(result==EXR_PDF_NONE) return result;
  id=result;
  if(f->values[id].kind==EXR_PDF_REF || !skip(&p) || p.at!=p.size) goto bad;
  return result;
bad:
  failed(f,EXR_FORMAT,"Invalid compressed PDF object or object stream index"); return EXR_PDF_NONE;
}
static int classic_xref(parser *p,size_t *previous,uint32_t *root,uint32_t *info) {
  exr_pdf_file *f=p->file; uint64_t first,count,i,size; uint32_t trailer,id;
  size_t maximum=0;
  for(;;) {
    if(word(p,"trailer")) break;
    if(!integer_token(p,&first) || !integer_token(p,&count) || first>PDF_MAX_OBJECTS || count>PDF_MAX_OBJECTS-first ||
       !xref_room(f,(size_t)(first+count))) goto bad;
    if(first+count>maximum) maximum=(size_t)(first+count);
    for(i=0;i<count;i++) {
      uint64_t offset,generation; unsigned type; pdf_xref *x;
      if(!integer_token(p,&offset) || !integer_token(p,&generation) || generation>65535 || !skip(p) || p->at==p->size) goto bad;
      if(p->data[p->at]=='n') type=1; else if(p->data[p->at]=='f') type=0; else goto bad;
      p->at++; if(p->at<p->size && !delimiter(p->data[p->at])) goto bad;
      if(type ? offset>=f->size : offset>=PDF_MAX_OBJECTS) goto bad;
      x=&f->xref[first+i];
      if(x->seen && x->revision==f->revision) goto bad;
      if(!x->seen) *x=(pdf_xref){(size_t)offset,EXR_PDF_NONE,f->revision,(unsigned)generation,type,0,1,0};
    }
  }
  trailer=parse_value(p,0);
  if(trailer==EXR_PDF_NONE || f->values[trailer].kind!=EXR_PDF_DICT ||
     !direct_integer(f,exr_pdf_get(f,trailer,"Size"),PDF_MAX_OBJECTS,&size) || size<maximum || !xref_room(f,(size_t)size)) goto bad;
  if(f->revision==1) f->declared_size=(size_t)size;
  id=exr_pdf_get(f,trailer,"Encrypt");
  if(id!=EXR_PDF_NONE && f->values[id].kind!=EXR_PDF_NULL) { failed(f,EXR_FORMAT,"Encrypted PDF is not supported"); return 0; }
  id=exr_pdf_get(f,trailer,"XRefStm");
  if(id!=EXR_PDF_NONE) {
    parser other; size_t ignored_previous; uint32_t ignored_root,ignored_info;
    if(!direct_integer(f,id,f->size-1,&size)) goto bad;
    other=(parser){f,f->data,f->size,(size_t)size};
    if(!stream_xref(&other,&ignored_previous,&ignored_root,&ignored_info,1)) return 0;
  }
  *info=exr_pdf_get(f,trailer,"Info");
  *root=exr_pdf_get(f,trailer,"Root");
  if(*root!=EXR_PDF_NONE && f->values[*root].kind!=EXR_PDF_REF) goto bad;
  id=exr_pdf_get(f,trailer,"Prev"); *previous=SIZE_MAX;
  if(id!=EXR_PDF_NONE) { if(!direct_integer(f,id,f->size-1,&size)) goto bad; *previous=(size_t)size; }
  if(f->trailer_id==EXR_PDF_NONE) f->trailer_id=exr_pdf_get(f,trailer,"ID");
  return 1;
bad:
  return failed(f,EXR_FORMAT,"Invalid PDF cross-reference table or trailer");
}
void exr_pdf_close(exr_pdf_file *f) {
  size_t i; if(!f) return;
  for(i=0;i<f->stream_count;i++) { free(f->streams[i].decoded); free(f->streams[i].objects); free(f->streams[i].offsets); }
  free(f->streams); free(f->xref); free(f->values); free(f->strings.data); free(f);
}
uint32_t exr_pdf_info(const exr_pdf_file *f) { return f ? f->info : EXR_PDF_NONE; }
uint32_t exr_pdf_root(const exr_pdf_file *f) { return f ? f->root : EXR_PDF_NONE; }
void exr_pdf_revision(const exr_pdf_file *f,exr_pdf_revision_info *out) {
  if(out) *out=f ? (exr_pdf_revision_info){f->startxref,f->declared_size,f->raw_root,f->info,f->trailer_id} :
                  (exr_pdf_revision_info){0,0,EXR_PDF_NONE,EXR_PDF_NONE,EXR_PDF_NONE};
}
exr_status exr_pdf_object_identity(const exr_pdf_file *f,uint32_t value,
  uint32_t *object,uint32_t *generation,exr_error *e) {
  size_t i; const exr_pdf_value *v=exr_pdf_value_at(f,value);
  if(object) *object=EXR_PDF_NONE;
  if(generation) *generation=0;
  if(!f || !v || !object || !generation) return exr_fail(e,EXR_ARGUMENT,"Missing PDF object identity input/output");
  if(v->kind==EXR_PDF_REF) {
    i=v->u.ref.object;
    if(i<f->xref_count && f->xref[i].seen && f->xref[i].type && f->xref[i].generation==v->u.ref.generation) {
      *object=(uint32_t)i; *generation=v->u.ref.generation; return exr_fail(e,EXR_OK,"");
    }
  } else for(i=0;i<f->xref_count;i++) if(f->xref[i].seen && f->xref[i].type &&
      f->xref[i].state==2 && f->xref[i].value==value) {
    *object=(uint32_t)i; *generation=f->xref[i].generation; return exr_fail(e,EXR_OK,"");
  }
  return exr_fail(e,EXR_FORMAT,"PDF value has no active indirect object identity");
}
exr_status exr_pdf_real(exr_buffer *out,double value,exr_error *e) {
  char formatted[64],digits[32],text[384]; size_t count=0,point=SIZE_MAX,at=0,i=0;
  int n,negative,exponent=0,place; const char *p;
  if(!out || !isfinite(value)) return exr_fail(e,EXR_ARGUMENT,"PDF real must be finite");
  n=snprintf(formatted,sizeof(formatted),"%.17g",value);
  if(n<0 || (size_t)n>=sizeof(formatted)) return exr_fail(e,EXR_FORMAT,"PDF real formatting failed");
  p=formatted; negative=*p=='-'; if(*p=='-' || *p=='+') p++;
  while(*p && *p!='e' && *p!='E') {
    if(*p>='0' && *p<='9') {
      if(count==sizeof(digits)) return exr_fail(e,EXR_FORMAT,"PDF real precision exceeds output bounds");
      digits[count++]=*p;
    } else if(point==SIZE_MAX) point=count; /* The locale decimal separator may be multibyte. */
    p++;
  }
  if(*p) exponent=(int)strtol(p+1,NULL,10);
  if(!count || exponent < -350 || exponent > 350) return exr_fail(e,EXR_FORMAT,"Invalid formatted PDF real");
  if(point==SIZE_MAX) point=count;
  place=(int)point+exponent;
  if(negative) text[at++]='-';
  if(place<=0) {
    text[at++]='0'; text[at++]='.';
    while(place++<0) text[at++]='0';
    memcpy(text+at,digits,count); at+=count;
  } else {
    for(i=0;i<(size_t)place;i++) text[at++]=i<count ? digits[i] : '0';
    text[at++]='.';
    if(i<count) { memcpy(text+at,digits+i,count-i); at+=count-i; }
    else text[at++]='0';
  }
  if(out->size>EXR_MAX_TEXT || at>EXR_MAX_TEXT-out->size) return exr_fail(e,EXR_LIMIT,"PDF output exceeds 64 MiB");
  if(!exr_append(out,text,at)) return exr_fail(e,EXR_MEMORY,"PDF real output allocation failed");
  return exr_fail(e,EXR_OK,"");
}
typedef struct {
  const exr_pdf_file *file; exr_buffer *out; const exr_control *control; exr_error *error;
  const char *const *skip_keys; size_t skip_count,nodes;
} pdf_serializer;
static exr_status serialized(pdf_serializer *s,const void *data,size_t size) {
  exr_status status=exr_control_cancel(s->control,s->error); if(status!=EXR_OK) return status;
  if(s->out->size>EXR_MAX_TEXT || size>EXR_MAX_TEXT-s->out->size)
    return exr_fail(s->error,EXR_LIMIT,"PDF serialized values exceed 64 MiB");
  return exr_append(s->out,data,size) ? EXR_OK : exr_fail(s->error,EXR_MEMORY,"PDF value output allocation failed");
}
static exr_status serialize_bytes(pdf_serializer *s,uint32_t id,int name) {
  static const char hex_digits[]="0123456789ABCDEF";
  char chunk[1024]; size_t size,i,used=0; const unsigned char *bytes=exr_pdf_bytes(s->file,id,&size);
  exr_status status=serialized(s,name ? "/" : "<",1); if(status!=EXR_OK) return status;
  if(!bytes) return exr_fail(s->error,EXR_FORMAT,"Invalid PDF serialized string");
  for(i=0;i<size;i++) {
    unsigned c=bytes[i];
    if(used+3>sizeof(chunk)) { status=serialized(s,chunk,used); if(status!=EXR_OK) return status; used=0; }
    if(name && c>32 && c<127 && c!='#' && !delimiter(c)) chunk[used++]=(char)c;
    else {
      if(name) chunk[used++]='#';
      chunk[used++]=hex_digits[c>>4]; chunk[used++]=hex_digits[c&15];
    }
  }
  status=serialized(s,chunk,used); if(status!=EXR_OK || name) return status;
  return serialized(s,">",1);
}
static int serialize_skip(const pdf_serializer *s,uint32_t key) {
  const unsigned char *bytes; size_t size,i;
  bytes=exr_pdf_bytes(s->file,key,&size);
  for(i=0;bytes && i<s->skip_count;i++) if(strlen(s->skip_keys[i])==size && !memcmp(bytes,s->skip_keys[i],size)) return 1;
  return 0;
}
static exr_status serialize_value(pdf_serializer *s,uint32_t id,unsigned depth) {
  const exr_pdf_value *v=exr_pdf_value_at(s->file,id); exr_status status;
  char number[64]; int length; uint32_t at;
  if(!v) return exr_fail(s->error,EXR_FORMAT,"Invalid PDF serialized value");
  if(depth>128 || ++s->nodes>EXR_PDF_MAX_VALUES) return exr_fail(s->error,EXR_LIMIT,"PDF serialization traversal exceeds limits");
  switch(v->kind) {
    case EXR_PDF_NULL: return serialized(s,"null",4);
    case EXR_PDF_BOOL: return serialized(s,v->u.number ? "true" : "false",v->u.number ? 4 : 5);
    case EXR_PDF_INT:
      length=snprintf(number,sizeof(number),"%" PRId64,v->u.integer); break;
    case EXR_PDF_REAL:
      status=exr_control_cancel(s->control,s->error); if(status!=EXR_OK) return status;
      if(v->first!=EXR_PDF_NONE) {
        size_t size; const unsigned char *raw;
        if(v->first>s->file->strings.size || s->file->strings.size-v->first<2)
          return exr_fail(s->error,EXR_FORMAT,"Invalid retained PDF number");
        raw=(const unsigned char *)s->file->strings.data+v->first; size=raw[0]+((size_t)raw[1]<<8);
        if(size>s->file->strings.size-v->first-2) return exr_fail(s->error,EXR_FORMAT,"Invalid retained PDF number length");
        return serialized(s,raw+2,size);
      }
      return exr_pdf_real(s->out,v->u.number,s->error);
    case EXR_PDF_REF:
      length=snprintf(number,sizeof(number),"%" PRIu32 " %" PRIu32 " R",v->u.ref.object,v->u.ref.generation); break;
    case EXR_PDF_NAME: return serialize_bytes(s,id,1);
    case EXR_PDF_STRING: return serialize_bytes(s,id,0);
    case EXR_PDF_ARRAY:
      status=serialized(s,"[",1); if(status!=EXR_OK) return status;
      for(at=v->first;at!=EXR_PDF_NONE;) {
        const exr_pdf_value *child=exr_pdf_value_at(s->file,at);
        if(!child) return exr_fail(s->error,EXR_FORMAT,"Invalid PDF array member");
        status=serialize_value(s,at,depth+1); if(status!=EXR_OK) return status;
        at=child->next; if(at!=EXR_PDF_NONE && (status=serialized(s," ",1))!=EXR_OK) return status;
      }
      return serialized(s,"]",1);
    case EXR_PDF_DICT:
      status=serialized(s,"<<",2); if(status!=EXR_OK) return status;
      for(at=v->first;at!=EXR_PDF_NONE;) {
        const exr_pdf_value *key=exr_pdf_value_at(s->file,at),*child;
        if(!(s->nodes&1023) && (status=exr_control_cancel(s->control,s->error))!=EXR_OK) return status;
        if(!key || key->kind!=EXR_PDF_NAME || !(child=exr_pdf_value_at(s->file,key->next)))
          return exr_fail(s->error,EXR_FORMAT,"Invalid PDF dictionary member");
        if(!depth && serialize_skip(s,at)) {
          if(++s->nodes>EXR_PDF_MAX_VALUES) return exr_fail(s->error,EXR_LIMIT,"PDF serialization traversal exceeds limits");
        } else {
          status=serialized(s," ",1); if(status!=EXR_OK) return status;
          status=serialize_value(s,at,depth+1); if(status!=EXR_OK) return status;
          status=serialized(s," ",1); if(status!=EXR_OK) return status;
          status=serialize_value(s,key->next,depth+1); if(status!=EXR_OK) return status;
        }
        at=child->next;
      }
      return serialized(s," >>",3);
    case EXR_PDF_STREAM: return exr_fail(s->error,EXR_FORMAT,"PDF streams cannot be serialized as ordinary values");
    default: return exr_fail(s->error,EXR_FORMAT,"Unknown PDF serialized value kind");
  }
  if(length<0 || (size_t)length>=sizeof(number)) return exr_fail(s->error,EXR_FORMAT,"PDF integer formatting failed");
  return serialized(s,number,(size_t)length);
}
exr_status exr_pdf_serialize(const exr_pdf_file *f,uint32_t value,const char *const *skip_keys,size_t skip_count,
  exr_buffer *out,const exr_control *control,exr_error *e) {
  pdf_serializer s={f,out,control,e,skip_keys,skip_count,0}; exr_status status; size_t original,i;
  if(!f || !out || (skip_count && !skip_keys)) return exr_fail(e,EXR_ARGUMENT,"Missing PDF serialization input/output");
  if(skip_count>64) return exr_fail(e,EXR_LIMIT,"PDF serialization filter exceeds 64 keys");
  if(out->size>EXR_MAX_TEXT) return exr_fail(e,EXR_LIMIT,"PDF output exceeds 64 MiB");
  for(i=0;i<skip_count;i++) if(!skip_keys[i]) return exr_fail(e,EXR_ARGUMENT,"Missing PDF dictionary filter key");
  original=out->size; status=exr_control_cancel(control,e);
  if(status==EXR_OK) status=serialize_value(&s,value,0);
  if(status==EXR_OK) status=exr_control_cancel(control,e);
  if(status!=EXR_OK) { out->size=original; if(out->data) out->data[original]=0; return status; }
  return exr_fail(e,EXR_OK,"");
}
static exr_status result(exr_pdf_file *f,exr_error *e) { if(e) *e=f->error; return f->error.code; }
exr_status exr_pdf_resolve(exr_pdf_file *f,uint32_t id,uint32_t *out,exr_error *e) {
  if(out) *out=EXR_PDF_NONE;
  if(!f || !out) return exr_fail(e,EXR_ARGUMENT,"Missing PDF resolution input/output");
  *out=resolve(f,id); return result(f,e);
}
exr_status exr_pdf_open(const void *data,size_t size,exr_pdf_file **out,exr_error *e) {
  const unsigned char *bytes=data; exr_pdf_file *f; parser p; size_t end=size,at,visited[10000],count=0,i; uint64_t offset;
  uint32_t root=EXR_PDF_NONE;
  if(!out) return exr_fail(e,EXR_ARGUMENT,"Missing PDF output");
  *out=NULL;
  if(!data || size<8 || size>EXR_MAX_INPUT) return exr_fail(e,size>EXR_MAX_INPUT ? EXR_LIMIT : EXR_ARGUMENT,"Invalid PDF input bytes");
  if(memcmp(bytes,"%PDF-",5) || !((bytes[5]=='1' && bytes[6]=='.' && bytes[7]>='0' && bytes[7]<='7') ||
     (bytes[5]=='2' && bytes[6]=='.' && bytes[7]=='0'))) return exr_fail(e,EXR_FORMAT,"Invalid PDF header version");
  f=calloc(1,sizeof(*f)); if(!f) return exr_fail(e,EXR_MEMORY,"PDF file allocation failed");
  f->data=bytes; f->size=size; f->root=f->info=f->raw_root=f->trailer_id=EXR_PDF_NONE;
  while(end && whitespace(bytes[end-1])) end--;
  if(end<5 || memcmp(bytes+end-5,"%%EOF",5)) goto bad;
  at=end-5;
  while(at && end-at<65536) {
    at--;
    if(end-at>=9 && !memcmp(bytes+at,"startxref",9) && (!at || whitespace(bytes[at-1]))) break;
  }
  if(end-at<9 || end-at>=65536 || memcmp(bytes+at,"startxref",9)) goto bad;
  p=(parser){f,bytes,end-5,at+9};
  if(!integer_token(&p,&offset) || offset>=size) goto bad;
  while(p.at<p.size && whitespace(bytes[p.at])) p.at++;
  if(p.at!=p.size) goto bad;
  at=f->startxref=(size_t)offset;
  while(at!=SIZE_MAX) {
    uint32_t candidate,info; size_t previous;
    for(i=0;i<count;i++) if(visited[i]==at) { failed(f,EXR_FORMAT,"Cyclic PDF Prev chain"); goto done; }
    if(count==10000) { failed(f,EXR_LIMIT,"PDF revision limit exceeded"); goto done; }
    visited[count++]=at; f->revision=(uint32_t)count;
    p=(parser){f,bytes,size,at};
    if(word(&p,"xref")) { if(!classic_xref(&p,&previous,&candidate,&info)) goto done; }
    else if(!stream_xref(&p,&previous,&candidate,&info,0)) goto done;
    if(root==EXR_PDF_NONE) root=candidate;
    if(f->info==EXR_PDF_NONE) f->info=info;
    at=previous;
  }
  if(root==EXR_PDF_NONE || f->declared_size<f->xref_count) goto bad;
  f->raw_root=root;
  f->root=resolve(f,root);
  if(f->root==EXR_PDF_NONE || f->values[f->root].kind!=EXR_PDF_DICT) goto bad;
  root=resolve(f,exr_pdf_get(f,f->root,"Type"));
  { size_t length; const unsigned char *name=exr_pdf_bytes(f,root,&length);
    if(!name || f->values[root].kind!=EXR_PDF_NAME || length!=7 || memcmp(name,"Catalog",7)) goto bad;
  }
  if(f->error.code==EXR_OK) { *out=f; return result(f,e); }
  goto done;
bad:
  failed(f,EXR_FORMAT,"Invalid PDF header, EOF, startxref or catalog");
done:
  { exr_status status=result(f,e); exr_pdf_close(f); return status; }
}
typedef struct { unsigned char *data; size_t size,capacity; } pdf_output;
static int decode_work(exr_pdf_file *f,size_t amount) {
  if(amount>(size_t)256*1024*1024-f->decode_work) return failed(f,EXR_LIMIT,"PDF decompression work budget exceeded");
  f->decode_work+=amount; return 1;
}
static int output_room(exr_pdf_file *f,pdf_output *out,size_t extra,size_t temporary) {
  size_t capacity; unsigned char *data;
  if(extra>EXR_MAX_TEXT-out->size) return failed(f,EXR_LIMIT,"PDF decoded stream exceeds 64 MiB");
  if(out->size+extra<=out->capacity) return 1;
  capacity=out->capacity ? out->capacity : 4096;
  while(capacity<out->size+extra) capacity*=2;
  if(temporary>EXR_MAX_INPUT-f->decoded_bytes || capacity>EXR_MAX_INPUT-f->decoded_bytes-temporary)
    return failed(f,EXR_LIMIT,"PDF decoded stream cache budget exceeded");
  data=realloc(out->data,capacity);
  if(!data) return failed(f,EXR_MEMORY,"PDF stream buffer allocation failed");
  out->data=data; out->capacity=capacity; return 1;
}
static int output_bytes(exr_pdf_file *f,pdf_output *out,const void *data,size_t size,size_t temporary) {
  if(!decode_work(f,size) || !output_room(f,out,size,temporary)) return 0;
  if(size) memcpy(out->data+out->size,data,size);
  out->size+=size; return 1;
}
static int tail_whitespace(const unsigned char *data,size_t size,size_t at) {
  while(at<size && whitespace(data[at])) at++;
  return at==size;
}
static int decode_flate(exr_pdf_file *f,const unsigned char *data,size_t size,pdf_output *out,size_t temporary) {
  size_t capacity;
  for(capacity=4096;capacity<=EXR_MAX_TEXT;capacity*=2) {
    mz_ulong produced=(mz_ulong)capacity,consumed=(mz_ulong)size; int status;
    if(!output_room(f,out,capacity,temporary) || !decode_work(f,capacity)) return 0;
    status=mz_uncompress2(out->data,&produced,data,&consumed);
    if(status==MZ_OK) {
      if(!tail_whitespace(data,size,(size_t)consumed)) return failed(f,EXR_FORMAT,"Trailing bytes in PDF Flate stream");
      out->size=(size_t)produced; return 1;
    }
    if(status!=MZ_BUF_ERROR) return failed(f,EXR_FORMAT,"Invalid PDF Flate stream");
  }
  return failed(f,EXR_LIMIT,"PDF decoded stream exceeds 64 MiB");
}
static int decode_hex(exr_pdf_file *f,const unsigned char *data,size_t size,pdf_output *out,size_t temporary) {
  size_t at; int high=-1;
  for(at=0;at<size;at++) {
    unsigned char byte; int digit;
    if(whitespace(data[at])) continue;
    if(data[at]=='>') {
      if(high>=0) { byte=(unsigned char)(high<<4); if(!output_bytes(f,out,&byte,1,temporary)) return 0; }
      if(tail_whitespace(data,size,at+1)) return 1;
      break;
    }
    digit=hex(data[at]); if(digit<0) break;
    if(high<0) high=digit;
    else { byte=(unsigned char)((high<<4)|digit); high=-1; if(!output_bytes(f,out,&byte,1,temporary)) return 0; }
  }
  return failed(f,EXR_FORMAT,"Invalid PDF ASCIIHex stream");
}
static int decode_ascii85(exr_pdf_file *f,const unsigned char *data,size_t size,pdf_output *out,size_t temporary) {
  size_t at; uint64_t tuple=0; unsigned count=0;
  for(at=0;at<size;at++) {
    unsigned char bytes[4]; unsigned k;
    if(whitespace(data[at])) continue;
    if(data[at]=='~') {
      if(at+1==size || data[at+1]!='>' || !tail_whitespace(data,size,at+2) || count==1) break;
      if(!count) return 1;
      for(k=count;k<5;k++) tuple=tuple*85+84;
      if(tuple>UINT32_MAX) break;
      for(k=0;k<4;k++) bytes[k]=(unsigned char)(tuple>>(24-8*k));
      return output_bytes(f,out,bytes,count-1,temporary);
    }
    if(data[at]=='z') {
      if(count) break;
      memset(bytes,0,sizeof(bytes)); if(!output_bytes(f,out,bytes,4,temporary)) return 0;
    } else {
      if(data[at]<'!' || data[at]>'u') break;
      tuple=tuple*85+data[at]-'!';
      if(++count==5) {
        if(tuple>UINT32_MAX) break;
        for(k=0;k<4;k++) bytes[k]=(unsigned char)(tuple>>(24-8*k));
        if(!output_bytes(f,out,bytes,4,temporary)) return 0;
        count=0; tuple=0;
      }
    }
  }
  return failed(f,EXR_FORMAT,"Invalid PDF ASCII85 stream");
}
static int decode_runlength(exr_pdf_file *f,const unsigned char *data,size_t size,pdf_output *out,size_t temporary) {
  size_t at=0;
  while(at<size) {
    unsigned run=data[at++]; size_t n;
    if(run==128) {
      if(tail_whitespace(data,size,at)) return 1;
      break;
    }
    n=run<128 ? run+1 : 257-run;
    if(run<128) {
      if(n>size-at) break;
      if(!output_bytes(f,out,data+at,n,temporary)) return 0;
      at+=n;
    } else {
      if(at==size) break;
      if(!decode_work(f,n) || !output_room(f,out,n,temporary)) return 0;
      memset(out->data+out->size,data[at++],n); out->size+=n;
    }
  }
  return failed(f,EXR_FORMAT,"Invalid PDF RunLength stream");
}
static int parameter(exr_pdf_file *f,uint32_t dict,const char *key,uint64_t maximum,uint64_t fallback,uint64_t *out) {
  uint32_t id=exr_pdf_get(f,dict,key); *out=fallback;
  return id==EXR_PDF_NONE || direct_integer(f,resolve(f,id),maximum,out);
}
static int decode_lzw(exr_pdf_file *f,const unsigned char *data,size_t size,pdf_output *out,size_t temporary,unsigned early) {
  uint16_t prefix[4096]; unsigned char suffix[4096],stack[4096];
  size_t bit=0; unsigned width=9,next=258,previous=UINT_MAX; int started=0;
  while(size*8-bit>=width) {
    unsigned code=0,current,k,first; size_t count=0; int special;
    for(k=0;k<width;k++,bit++) code=(code<<1)|((data[bit/8]>>(7-bit%8))&1);
    if(!started && code!=256) break;
    started=1;
    if(code==256) { width=9; next=258; previous=UINT_MAX; continue; }
    if(code==257) {
      if(tail_whitespace(data,size,(bit+7)/8)) return 1;
      break;
    }
    special=code==next && previous!=UINT_MAX;
    if(code>next || (code==next && !special)) break;
    current=special ? previous : code;
    while(current>=258) {
      if(current>=next || count==sizeof(stack)-1) goto bad;
      stack[count++]=suffix[current]; current=prefix[current];
    }
    if(current>=256) break;
    first=current; stack[count++]=(unsigned char)first;
    if(!decode_work(f,count+(size_t)special) || !output_room(f,out,count+(size_t)special,temporary)) return 0;
    for(k=0;k<count;k++) out->data[out->size++]=stack[count-1-k];
    if(special) out->data[out->size++]=(unsigned char)first;
    if(previous!=UINT_MAX && next<4096) {
      prefix[next]=(uint16_t)previous; suffix[next++]=(unsigned char)first;
      if(width<12 && next+early==(1u<<width)) width++;
    }
    previous=code;
  }
bad:
  return failed(f,EXR_FORMAT,"Invalid PDF LZW codes or terminator");
}
static unsigned sample_get(const unsigned char *data,size_t bit,unsigned bits) {
  unsigned value=0,i;
  for(i=0;i<bits;i++) value=(value<<1)|((data[(bit+i)/8]>>(7-(bit+i)%8))&1);
  return value;
}
static void sample_set(unsigned char *data,size_t bit,unsigned bits,unsigned value) {
  unsigned i;
  for(i=0;i<bits;i++) { unsigned char mask=(unsigned char)(1u<<(7-(bit+i)%8));
    data[(bit+i)/8]=(unsigned char)((data[(bit+i)/8]&~mask)|((value>>(bits-1-i))&1 ? mask : 0));
  }
}
static int undo_predictor(exr_pdf_file *f,uint32_t parameters,pdf_output *out) {
  uint64_t predictor,colors,bits,columns; size_t row,rows,at,y,x,pixel;
  if(parameters==EXR_PDF_NONE || f->values[parameters].kind==EXR_PDF_NULL) return 1;
  if(f->values[parameters].kind!=EXR_PDF_DICT || !parameter(f,parameters,"Predictor",15,1,&predictor)) goto bad;
  if(predictor==1) return 1;
  if((predictor!=2 && predictor<10) || !parameter(f,parameters,"Colors",32,1,&colors) || !colors ||
     !parameter(f,parameters,"BitsPerComponent",16,8,&bits) || (bits!=1 && bits!=2 && bits!=4 && bits!=8 && bits!=16) ||
     !parameter(f,parameters,"Columns",1048576,1,&columns) || !columns) goto bad;
  row=(size_t)((colors*bits*columns+7)/8); pixel=(size_t)((colors*bits+7)/8);
  if(predictor==2) {
    if(out->size%row || !decode_work(f,(out->size/row)*(size_t)(columns*colors))) goto bad;
    for(at=0;at<out->size;at+=row) for(x=(size_t)colors;x<(size_t)(columns*colors);x++) {
      unsigned value=sample_get(out->data+at,x*(size_t)bits,(unsigned)bits)+sample_get(out->data+at,(x-(size_t)colors)*(size_t)bits,(unsigned)bits);
      sample_set(out->data+at,x*(size_t)bits,(unsigned)bits,value);
    }
    return 1;
  }
  if(out->size%(row+1) || !decode_work(f,out->size)) goto bad;
  rows=out->size/(row+1);
  for(y=0;y<rows;y++) {
    unsigned filter=out->data[y*(row+1)];
    if(filter>4) goto bad;
    for(x=0;x<row;x++) {
      unsigned left=x>=pixel ? out->data[y*row+x-pixel] : 0,up=y ? out->data[(y-1)*row+x] : 0;
      unsigned upper_left=y && x>=pixel ? out->data[(y-1)*row+x-pixel] : 0,add=0;
      if(filter==1) add=left;
      else if(filter==2) add=up;
      else if(filter==3) add=(left+up)/2;
      else if(filter==4) {
        int p=(int)left+(int)up-(int)upper_left,a=abs(p-(int)left),b=abs(p-(int)up),c=abs(p-(int)upper_left);
        add=a<=b && a<=c ? left : b<=c ? up : upper_left;
      }
      out->data[y*row+x]=(unsigned char)(out->data[y*(row+1)+1+x]+add);
    }
  }
  out->size=rows*row; return 1;
bad:
  return failed(f,EXR_FORMAT,"Invalid PDF predictor or row parameters");
}
static exr_status stream_payload(exr_pdf_file *f,uint32_t id,const unsigned char **data,size_t *size,
                                   int allow_image,exr_pdf_stream_codec *codec,uint32_t *tail_parameters,exr_error *e) {
  uint32_t filter,parameters,filters[16],parms[16],at; size_t index,count=0,n=0,i; pdf_stream source;
  exr_pdf_stream_codec terminal=EXR_PDF_STREAM_RAW; uint32_t terminal_parameters=EXR_PDF_NONE;
  const unsigned char *input; size_t input_size; pdf_output current={0};
  if(data) *data=NULL;
  if(size) *size=0;
  if(codec) *codec=EXR_PDF_STREAM_RAW;
  if(tail_parameters) *tail_parameters=EXR_PDF_NONE;
  if(!f || !data || !size) return exr_fail(e,EXR_ARGUMENT,"Missing PDF stream inputs/outputs");
  id=resolve(f,id);
  if(id==EXR_PDF_NONE || f->values[id].kind!=EXR_PDF_STREAM) { failed(f,EXR_FORMAT,"PDF value is not a stream"); return result(f,e); }
  index=f->values[id].u.ref.object; source=f->streams[index];
  if(source.ready) {
    if(source.codec!=EXR_PDF_STREAM_RAW && !allow_image) goto unsupported;
    *data=source.decoded ? source.decoded : f->data+source.offset; *size=source.decoded_size;
    if(codec) *codec=source.codec;
    if(tail_parameters) *tail_parameters=source.parameters;
    return result(f,e);
  }
  filter=resolve(f,exr_pdf_get(f,id,"Filter")); parameters=resolve(f,exr_pdf_get(f,id,"DecodeParms"));
  for(i=0;i<16;i++) parms[i]=EXR_PDF_NONE;
  if(filter!=EXR_PDF_NONE && f->values[filter].kind!=EXR_PDF_NULL) {
    if(f->values[filter].kind==EXR_PDF_ARRAY) {
      at=f->values[filter].first;
      while(at!=EXR_PDF_NONE) {
        uint32_t next=f->values[at].next;
        if(count==16) goto unsupported;
        filters[count++]=resolve(f,at); at=next;
      }
      if(parameters!=EXR_PDF_NONE && f->values[parameters].kind!=EXR_PDF_NULL) {
        if(f->values[parameters].kind!=EXR_PDF_ARRAY) goto unsupported;
        at=f->values[parameters].first;
        while(at!=EXR_PDF_NONE) {
          uint32_t next=f->values[at].next;
          if(n==count) goto unsupported;
          parms[n++]=resolve(f,at); at=next;
        }
        if(n!=count) goto unsupported;
      }
    } else { filters[count++]=filter; parms[0]=parameters; }
  }
  if(f->error.code!=EXR_OK) goto done;
  input=f->data+source.offset; input_size=source.size;
  for(i=0;i<count;i++) {
    pdf_output output={0}; int ok=0,is_flate=name_is(f,filters[i],"FlateDecode") || name_is(f,filters[i],"Fl");
    int is_lzw=name_is(f,filters[i],"LZWDecode") || name_is(f,filters[i],"LZW");
    if(parms[i]!=EXR_PDF_NONE && f->values[parms[i]].kind!=EXR_PDF_NULL && f->values[parms[i]].kind!=EXR_PDF_DICT) goto unsupported;
    if(allow_image && (name_is(f,filters[i],"DCTDecode") || name_is(f,filters[i],"DCT"))) {
      if(i+1!=count) goto unsupported;
      terminal=EXR_PDF_STREAM_JPEG; terminal_parameters=parms[i]; break;
    }
    if(!decode_work(f,input_size)) goto done;
    if(is_flate) ok=decode_flate(f,input,input_size,&output,current.capacity);
    else if(is_lzw) {
      uint64_t early;
      if(!parameter(f,parms[i],"EarlyChange",1,1,&early)) { failed(f,EXR_FORMAT,"Invalid PDF LZW EarlyChange"); goto done; }
      ok=decode_lzw(f,input,input_size,&output,current.capacity,(unsigned)early);
    }
    else if(name_is(f,filters[i],"ASCIIHexDecode") || name_is(f,filters[i],"AHx")) ok=decode_hex(f,input,input_size,&output,current.capacity);
    else if(name_is(f,filters[i],"ASCII85Decode") || name_is(f,filters[i],"A85")) ok=decode_ascii85(f,input,input_size,&output,current.capacity);
    else if(name_is(f,filters[i],"RunLengthDecode") || name_is(f,filters[i],"RL")) ok=decode_runlength(f,input,input_size,&output,current.capacity);
    else { free(output.data); goto unsupported; }
    if(ok && (is_flate || is_lzw)) ok=undo_predictor(f,parms[i],&output);
    if(!ok) { free(output.data); goto done; }
    free(current.data); current=output; input=current.data; input_size=current.size;
  }
  if(f->error.code!=EXR_OK) goto done;
  if(current.capacity>EXR_MAX_INPUT-f->decoded_bytes) { failed(f,EXR_LIMIT,"PDF decoded stream cache budget exceeded"); goto done; }
  f->streams[index].decoded=current.data; f->streams[index].decoded_size=input_size; f->streams[index].ready=1;
  f->streams[index].codec=terminal; f->streams[index].parameters=terminal_parameters;
  f->decoded_bytes+=current.capacity; *data=current.data ? current.data : f->data+source.offset; *size=input_size;
  if(codec) *codec=terminal;
  if(tail_parameters) *tail_parameters=terminal_parameters;
  return result(f,e);
unsupported:
  failed(f,EXR_FORMAT,"PDF stream filter or parameter shape is not implemented");
done:
  free(current.data); return result(f,e);
}
exr_status exr_pdf_stream_data(exr_pdf_file *f,uint32_t id,const unsigned char **data,size_t *size,exr_error *e) {
  return stream_payload(f,id,data,size,0,NULL,NULL,e);
}
exr_status exr_pdf_image_payload(exr_pdf_file *f,uint32_t id,const unsigned char **data,size_t *size,
                                  exr_pdf_stream_codec *codec,uint32_t *parameters,exr_error *e) {
  if(!codec || !parameters) {
    if(data) *data=NULL;
    if(size) *size=0;
    if(codec) *codec=EXR_PDF_STREAM_RAW;
    if(parameters) *parameters=EXR_PDF_NONE;
    return exr_fail(e,EXR_ARGUMENT,"Missing PDF image payload codec/parameters");
  }
  return stream_payload(f,id,data,size,1,codec,parameters,e);
}
/* Content operands reuse the object lexer in a short-lived arena. */
exr_status exr_pdf_syntax_ops(const void *data,size_t size,exr_pdf_operator_fn operation,void *context,
                              size_t maximum_operands,const exr_control *control,exr_error *error) {
  exr_pdf_file *arena; parser p; uint32_t operands[1024]; size_t count=0,operations=0; exr_status status;
  if((!data && size) || !operation || !maximum_operands || maximum_operands>1024) return exr_fail(error,EXR_ARGUMENT,"Missing PDF content bytes or callback");
  if(size>EXR_MAX_TEXT) return exr_fail(error,EXR_LIMIT,"PDF content exceeds 64 MiB");
  arena=calloc(1,sizeof(*arena)); if(!arena) return exr_fail(error,EXR_MEMORY,"PDF operand arena allocation failed");
  arena->data=data; arena->size=size; arena->root=EXR_PDF_NONE; p=(parser){arena,data,size,0};
  status=exr_control_poll(control,EXR_STAGE_READ,0,size,&arena->error);
  while(status==EXR_OK && skip(&p) && p.at<p.size) {
    unsigned c=p.data[p.at]; parser probe=p;
    if(c=='/' || c=='(' || c=='<' || c=='[' || c=='+' || c=='-' || c=='.' || (c>='0' && c<='9') ||
       word(&probe,"true") || word(&probe,"false") || word(&probe,"null")) {
      uint32_t id;
      if(count==maximum_operands) { failed(arena,EXR_LIMIT,"PDF operand stack exceeds its limit"); break; }
      id=parse_value(&p,0); if(id==EXR_PDF_NONE) break;
      operands[count++]=id;
    } else {
      char name[128]; size_t start=p.at,i;
      while(p.at<p.size && !delimiter(p.data[p.at])) {
        if(p.at-start==sizeof(name)-1) { failed(arena,EXR_LIMIT,"PDF content operator name exceeds 127 bytes"); break; }
        p.at++;
      }
      if(arena->error.code!=EXR_OK) break;
      if(p.at==start) { failed(arena,EXR_FORMAT,"Unexpected PDF content delimiter"); break; }
      memcpy(name,p.data+start,p.at-start); name[p.at-start]=0;
      if(++operations>1048576) { failed(arena,EXR_LIMIT,"PDF content operation budget exceeded"); break; }
      for(i=0;i<arena->value_count;i++) if(arena->values[i].kind==EXR_PDF_REF) { failed(arena,EXR_FORMAT,"Indirect reference in PDF content operands"); break; }
      if(arena->error.code!=EXR_OK) break;
      if(!strcmp(name,"BI")) { failed(arena,EXR_FORMAT,"Inline PDF images are not implemented yet"); break; }
      status=operation(context,arena,name,operands,count,&arena->error);
      if(status!=EXR_OK && arena->error.code==EXR_OK) failed(arena,status,"PDF content callback failed");
      if(status!=EXR_OK || arena->error.code!=EXR_OK) break;
      count=0; arena->value_count=0; arena->strings.size=0;
      if(!(operations&255)) status=exr_control_poll(control,EXR_STAGE_READ,p.at,size,&arena->error);
    }
  }
  if(arena->error.code==EXR_OK && count) failed(arena,EXR_FORMAT,"PDF content ends with operands but no operator");
  if(arena->error.code==EXR_OK) exr_control_poll(control,EXR_STAGE_READ,size,size,&arena->error);
  status=result(arena,error); exr_pdf_close(arena); return status;
}

exr_status exr_pdf_content_ops(const void *data,size_t size,exr_pdf_operator_fn operation,void *context,
                               const exr_control *control,exr_error *error) {
  return exr_pdf_syntax_ops(data,size,operation,context,64,control,error);
}
