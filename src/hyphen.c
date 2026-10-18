/* SPDX-License-Identifier: GPL-3.0-only */
#include "hyphen_internal.h"
#include "hyphen_unicode_data.h"

#define NONE UINT32_MAX
#define EDGE UINT32_C(0x110000)
#define WORD_SCALARS 256
#define FOLDED_SCALARS (3*WORD_SCALARS+2)
#define PATTERN_SCALARS 128
#define WORK_LIMIT (64u*1024u*1024u)
typedef struct {
  uint32_t cp,child,next,values;
  unsigned short length;
} hy_node;
typedef struct {
  char language[256];
  unsigned left,right;
  hy_node *nodes; size_t count,capacity;
  unsigned char *values; size_t value_count,value_capacity;
  uint32_t *edges;
} hy_dictionary;
struct exr_hyphenator {
  size_t refs,bytes,budget;
  int busy;
  exr_hyphen_provider provider;
  hy_dictionary *dictionaries;
  size_t count;
};
typedef struct {
  exr_hyphenator *owner;
  const exr_control *control;
  exr_error *error;
  size_t work;
} hy_work;

static exr_status work(hy_work *w,size_t count) {
  if(count>WORK_LIMIT-w->work) return exr_fail(w->error,EXR_LIMIT,"Hyphenation work limit exceeded");
  if(w->work/1024!=(w->work+count)/1024) {
    exr_status status=exr_control_cancel(w->control,w->error); if(status!=EXR_OK) return status;
  }
  w->work+=count; return EXR_OK;
}
static int canonical(const char *language,char out[256]) {
  size_t n=0,component=0; int primary=1;
  if(!language) language="";
  for(;language[n];n++) {
    unsigned c=(unsigned char)language[n];
    if(n==255) return 0;
    if(c=='-') { if(!component) return 0; component=0; primary=0; }
    else {
      if(!((c>='a' && c<='z') || (c>='A' && c<='Z') || (!primary && c>='0' && c<='9'))) return 0;
      component++;
    }
    out[n]=(char)(c>='A' && c<='Z' ? c+32 : c);
  }
  if(n && !component) return 0;
  out[n]=0; return 1;
}
static unsigned fold(uint32_t cp,const char *language,uint32_t values[3]) {
  size_t lo=0,hi=sizeof(exr_case_folds)/sizeof(*exr_case_folds);
  int turkic=(!strncmp(language,"tr",2) || !strncmp(language,"az",2)) && (!language[2] || language[2]=='-');
  if(turkic && (cp==0x49 || cp==0x130)) { values[0]=cp==0x49 ? 0x131 : 0x69; return 1; }
  while(lo<hi) { size_t mid=lo+(hi-lo)/2; if(exr_case_folds[mid].cp<cp) lo=mid+1; else hi=mid; }
  if(lo<sizeof(exr_case_folds)/sizeof(*exr_case_folds) && exr_case_folds[lo].cp==cp) {
    memcpy(values,exr_case_folds[lo].values,sizeof(exr_case_folds[lo].values)); return exr_case_folds[lo].count;
  }
  values[0]=cp; return 1;
}
unsigned exr_hyphen_word_kind(uint32_t cp) {
  size_t lo=0,hi=sizeof(exr_word_ranges)/sizeof(*exr_word_ranges);
  while(lo<hi) {
    size_t mid=lo+(hi-lo)/2;
    if(cp<exr_word_ranges[mid].first) hi=mid;
    else if(cp>exr_word_ranges[mid].last) lo=mid+1;
    else return exr_word_ranges[mid].kind;
  }
  return 0;
}
static exr_status reserve(hy_work *w,void **out,size_t *capacity,size_t needed,size_t unit) {
  size_t next=*capacity ? *capacity : 64,delta; void *p;
  if(needed<=*capacity) return EXR_OK;
  while(next<needed) next*=2; /* Counts below 4 Mi items; no size_t overflow. */
  delta=(next-*capacity)*unit;
  if(delta>w->owner->budget-w->owner->bytes) return exr_fail(w->error,EXR_LIMIT,"Hyphenation dictionary byte budget exceeded");
  p=realloc(*out,next*unit); if(!p) return exr_fail(w->error,EXR_MEMORY,"Hyphenation dictionary allocation failed");
  *out=p; *capacity=next; w->owner->bytes+=delta; return EXR_OK;
}
static exr_status child(hy_work *w,hy_dictionary *d,uint32_t parent,uint32_t cp,uint32_t *out) {
  uint32_t previous=NONE,current=d->nodes[parent].child; exr_status status;
  while(current!=NONE && d->nodes[current].cp<cp) {
    status=work(w,1); if(status!=EXR_OK) return status;
    previous=current; current=d->nodes[current].next;
  }
  if(current!=NONE && d->nodes[current].cp==cp) { *out=current; return EXR_OK; }
  if(d->count>=1024*1024) return exr_fail(w->error,EXR_LIMIT,"Hyphenation trie exceeds one million nodes");
  status=reserve(w,(void **)&d->nodes,&d->capacity,d->count+1,sizeof(*d->nodes)); if(status!=EXR_OK) return status;
  *out=(uint32_t)d->count++; d->nodes[*out]=(hy_node){cp,NONE,current,NONE,0};
  if(previous==NONE) d->nodes[parent].child=*out; else d->nodes[previous].next=*out;
  return EXR_OK;
}
static exr_status pattern(hy_work *w,hy_dictionary *d,const char *text,size_t size) {
  uint32_t letters[3*PATTERN_SCALARS],node=0; unsigned char scores[3*PATTERN_SCALARS+1]={0};
  size_t at=0,n=0,scalars=0,i; int digit=0; exr_status status;
  while(at<size) {
    uint32_t cp,values[3]; unsigned count,j;
    if(!exr_next(text,size,&at,&cp)) return exr_fail(w->error,EXR_ENCODING,"Invalid UTF-8 hyphenation pattern");
    if(cp>='0' && cp<='9') {
      if(digit) return exr_fail(w->error,EXR_FORMAT,"Adjacent hyphenation weights");
      scores[n]=(unsigned char)(cp-'0'); digit=1; continue;
    }
    digit=0;
    if(cp=='/' || cp=='\\' || cp=='{' || cp=='}' || cp=='=') return exr_fail(w->error,EXR_UNSUPPORTED,"Hyphenation spelling replacements or TeX commands require a provider");
    if(cp<0x20 || cp==0x7f || ++scalars>PATTERN_SCALARS) return exr_fail(w->error,EXR_LIMIT,"Invalid or overlong hyphenation pattern");
    if(cp=='.') { values[0]=EDGE; count=1; } else count=fold(cp,d->language,values);
    for(j=0;j<count;j++) letters[n++]=values[j];
  }
  if(!n) return exr_fail(w->error,EXR_FORMAT,"Hyphenation pattern has no letters");
  for(i=0;i<n;i++) { status=child(w,d,node,letters[i],&node); if(status!=EXR_OK) return status; }
  if(d->nodes[node].values==NONE) {
    status=reserve(w,(void **)&d->values,&d->value_capacity,d->value_count+n+1,1); if(status!=EXR_OK) return status;
    d->nodes[node].values=(uint32_t)d->value_count; d->nodes[node].length=(unsigned short)(n+1);
    memcpy(d->values+d->value_count,scores,n+1); d->value_count+=n+1;
  } else for(i=0;i<=n;i++) {
    unsigned char *v=&d->values[d->nodes[node].values+i]; if(scores[i]>*v) *v=scores[i];
  }
  return work(w,n+1);
}
static int space(unsigned c) { return c==' ' || c=='\t' || c=='\r' || c=='\n'; }
static int token(const char *text,size_t size,size_t *at,size_t *first,size_t *end) {
  while(*at<size) {
    unsigned c=(unsigned char)text[*at];
    if(space(c)) { (*at)++; continue; }
    if(c=='%' || c=='#') { while(*at<size && text[*at]!='\n') (*at)++; continue; }
    break;
  }
  if(*at==size) return 0;
  *first=*at;
  while(*at<size && !space((unsigned char)text[*at]) && text[*at]!='%' && text[*at]!='#') (*at)++;
  *end=*at; return 1;
}
static int matches(const char *text,size_t first,size_t end,const char *key) { return end-first==strlen(key) && !memcmp(text+first,key,end-first); }
static exr_status load(hy_work *w,hy_dictionary *d,const exr_hyphen_pattern_input *input) {
  const char *text=input->patterns; size_t at=0,first,end,patterns=0; exr_status status;
  d->left=input->left_min ? input->left_min : 2; d->right=input->right_min ? input->right_min : 2;
  status=reserve(w,(void **)&d->nodes,&d->capacity,1,sizeof(*d->nodes)); if(status!=EXR_OK) return status;
  d->count=1; d->nodes[0]=(hy_node){0,NONE,NONE,NONE,0};
  if(input->size>=3 && !memcmp(text,"\xef\xbb\xbf",3)) at=3;
  while(token(text,input->size,&at,&first,&end)) {
    status=exr_control_poll(w->control,EXR_STAGE_READ,at,input->size,w->error); if(status!=EXR_OK) return status;
    if(!patterns && matches(text,first,end,"UTF-8")) continue;
    if(matches(text,first,end,"LEFTHYPHENMIN") || matches(text,first,end,"RIGHTHYPHENMIN")) {
      unsigned number=0; int left=matches(text,first,end,"LEFTHYPHENMIN"); size_t start;
      if(!token(text,input->size,&at,&first,&end) || end-first>2) return exr_fail(w->error,EXR_FORMAT,"Missing or invalid HYPHENMIN value");
      for(start=first;start<end;start++) { if(text[start]<'0' || text[start]>'9') return exr_fail(w->error,EXR_FORMAT,"Invalid HYPHENMIN number"); number=number*10+(unsigned)(text[start]-'0'); }
      if(number>64) return exr_fail(w->error,EXR_LIMIT,"Hyphenation edge minimum exceeds 64");
      if(left && !input->left_min) d->left=number;
      if(!left && !input->right_min) d->right=number;
      continue;
    }
    if(matches(text,first,end,"NEXTLEVEL") || (end-first>=8 && !memcmp(text+first,"COMPOUND",8)))
      return exr_fail(w->error,EXR_UNSUPPORTED,"Compound hyphenation dictionaries require a provider");
    if(++patterns>262144) return exr_fail(w->error,EXR_LIMIT,"More than 262144 hyphenation patterns");
    status=pattern(w,d,text+first,end-first); if(status!=EXR_OK) return status;
  }
  if(d->count>1) {
    size_t bytes=(d->count-1)*sizeof(*d->edges),i,index=0;
    if(bytes>w->owner->budget-w->owner->bytes) return exr_fail(w->error,EXR_LIMIT,"Packed hyphenation trie exceeds byte budget");
    d->edges=malloc(bytes); if(!d->edges) return exr_fail(w->error,EXR_MEMORY,"Packed hyphenation trie allocation failed");
    w->owner->bytes+=bytes;
    for(i=0;i<d->count;i++) {
      uint32_t next=d->nodes[i].child; size_t start=index;
      while(next!=NONE) { d->edges[index++]=next; next=d->nodes[next].next; }
      d->nodes[i].child=(uint32_t)start; d->nodes[i].next=(uint32_t)(index-start);
      status=work(w,index-start+1); if(status!=EXR_OK) return status;
    }
  } else { d->nodes[0].child=0; d->nodes[0].next=0; }
  return EXR_OK;
}
static hy_dictionary *dictionary(exr_hyphenator *h,const char *language) {
  char key[256]; size_t i,n=strlen(language); memcpy(key,language,n+1);
  for(;;) {
    for(i=0;i<h->count;i++) if(!strcmp(key,h->dictionaries[i].language)) return &h->dictionaries[i];
    if(!n) return NULL;
    while(n && key[n-1]!='-') n--;
    if(!n) return NULL;
    key[--n]=0;
    /* RFC 4647 lookup removes a trailing extension singleton with its subtag. */
    if(n==1 || (n>=2 && key[n-2]=='-')) {
      if(n==1) return NULL;
      key[n-=2]=0;
    }
  }
}
static exr_status native_breaks(hy_work *w,const char *language,const uint32_t *scalars,
                                const size_t *offsets,size_t count,const unsigned char *boundaries,unsigned char *out) {
  hy_dictionary *d=dictionary(w->owner,language);
  uint32_t word[FOLDED_SCALARS]; size_t folded_at[WORD_SCALARS+1],n=1,i,j,graphemes[WORD_SCALARS+1]={0};
  unsigned char scores[FOLDED_SCALARS+1]={0}; exr_status status;
  if(!d) return EXR_OK;
  word[0]=EDGE;
  for(i=0;i<count;i++) {
    uint32_t values[3]; unsigned k,len=fold(scalars[i],d->language,values);
    folded_at[i]=n; for(k=0;k<len;k++) word[n++]=values[k];
    graphemes[i+1]=graphemes[i]+!!(boundaries[offsets[i]]&EXR_BOUNDARY_GRAPHEME);
  }
  folded_at[count]=n; word[n++]=EDGE;
  for(i=0;i<n;i++) {
    uint32_t node=0;
    for(j=i;j<n;j++) {
      const hy_node *parent=&d->nodes[node]; size_t lo=parent->child,hi=lo+parent->next,limit=hi;
      while(lo<hi) {
        size_t mid=lo+(hi-lo)/2; if(d->nodes[d->edges[mid]].cp<word[j]) lo=mid+1; else hi=mid;
        status=work(w,1); if(status!=EXR_OK) return status;
      }
      if(lo==limit || d->nodes[d->edges[lo]].cp!=word[j]) break;
      node=d->edges[lo];
      if(d->nodes[node].values!=NONE) {
        size_t k,length=d->nodes[node].length; const unsigned char *values=d->values+d->nodes[node].values;
        for(k=0;k<length;k++) if(values[k]>scores[i+k]) scores[i+k]=values[k];
        status=work(w,length); if(status!=EXR_OK) return status;
      }
    }
  }
  for(i=1;i<count;i++) if(graphemes[i]>=d->left && graphemes[count]-graphemes[i]>=d->right &&
      (boundaries[offsets[i]]&EXR_BOUNDARY_GRAPHEME)) out[offsets[i]]=(unsigned char)(scores[folded_at[i]]&1);
  return EXR_OK;
}

exr_status exr_hyphenator_create(const exr_hyphen_provider *provider,exr_hyphenator **out,exr_error *e) {
  exr_hyphenator *h;
  if(!out) return exr_fail(e,EXR_ARGUMENT,"Missing hyphenator output");
  *out=NULL;
  if(!provider || provider->struct_size!=sizeof(*provider) || !provider->hyphenate) return exr_fail(e,EXR_ARGUMENT,"Invalid hyphenation provider");
  h=calloc(1,sizeof(*h)); if(!h) return exr_fail(e,EXR_MEMORY,"Hyphenator allocation failed");
  h->provider=*provider; h->refs=1; h->bytes=sizeof(*h); *out=h; return exr_fail(e,EXR_OK,"");
}
exr_status exr_hyphenator_create_patterns(const exr_hyphen_pattern_input *inputs,size_t count,size_t budget,
                                          const exr_control *control,exr_hyphenator **out,exr_error *e) {
  exr_hyphenator *h; hy_work w={0}; size_t i,j,total=0; exr_status status=EXR_OK;
  if(!out) return exr_fail(e,EXR_ARGUMENT,"Missing hyphenator output");
  *out=NULL;
  if(!inputs || !count || count>64 || budget>EXR_MAX_INPUT) return exr_fail(e,EXR_ARGUMENT,"Invalid hyphenation dictionary registry");
  for(i=0;i<count;i++) {
    char key[256];
    if(inputs[i].struct_size!=sizeof(*inputs) || (!inputs[i].patterns && inputs[i].size) || !canonical(inputs[i].language,key)) return exr_fail(e,EXR_ARGUMENT,"Invalid hyphenation dictionary input");
    if(inputs[i].left_min>64 || inputs[i].right_min>64 || inputs[i].size>8*1024*1024 || inputs[i].size>32*1024*1024-total)
      return exr_fail(e,EXR_LIMIT,"Hyphenation dictionary input limit exceeded");
    total+=inputs[i].size;
  }
  h=calloc(1,sizeof(*h)); if(!h) return exr_fail(e,EXR_MEMORY,"Hyphenator allocation failed");
  h->refs=1; h->bytes=sizeof(*h); h->budget=budget ? budget : 32*1024*1024;
  if(h->bytes>h->budget || count*sizeof(*h->dictionaries)>h->budget-h->bytes) { status=exr_fail(e,EXR_LIMIT,"Hyphenation registry byte budget exceeded"); goto failed; }
  h->dictionaries=calloc(count,sizeof(*h->dictionaries));
  if(!h->dictionaries) { status=exr_fail(e,EXR_MEMORY,"Hyphenation registry allocation failed"); goto failed; }
  h->count=count; h->bytes+=count*sizeof(*h->dictionaries); w.owner=h; w.control=control; w.error=e;
  for(i=0;i<count;i++) {
    canonical(inputs[i].language,h->dictionaries[i].language);
    for(j=0;j<i;j++) if(!strcmp(h->dictionaries[j].language,h->dictionaries[i].language)) { status=exr_fail(e,EXR_ARGUMENT,"Duplicate hyphenation language key"); goto failed; }
    status=exr_control_poll(control,EXR_STAGE_READ,i,count,e); if(status!=EXR_OK) goto failed;
    status=load(&w,&h->dictionaries[i],&inputs[i]); if(status!=EXR_OK) goto failed;
  }
  status=exr_control_poll(control,EXR_STAGE_READ,count,count,e); if(status!=EXR_OK) goto failed;
  *out=h; return exr_fail(e,EXR_OK,"");
failed:
  exr_hyphenator_free(h); return status;
}
exr_status exr_hyphenator_ref(exr_hyphenator *h,exr_error *e) {
  if(!h || h->refs==SIZE_MAX) return exr_fail(e,EXR_LIMIT,"Invalid hyphenator reference count");
  h->refs++; return EXR_OK;
}
exr_status exr_hyphenator_breaks(exr_hyphenator *h,const char *language,const char *text,size_t size,
                                 unsigned char *out,const exr_control *control,exr_error *e) {
  uint32_t scalars[WORD_SCALARS]; size_t offsets[WORD_SCALARS+1],count=0,at=0,i;
  unsigned char *boundaries=NULL; char key[256]; exr_status status; hy_work w={h,control,e,0};
  if(size>1024) return exr_fail(e,EXR_LIMIT,"Hyphenation word exceeds 1024 UTF-8 bytes");
  if(out) memset(out,0,size+1);
  if(!h || h->busy || !text || !out || !canonical(language,key)) return exr_fail(e,EXR_ARGUMENT,"Invalid or reentrant hyphenation query");
  if(e) memset(e,0,sizeof(*e));
  while(at<size) {
    uint32_t cp; size_t start=at;
    if(!exr_next(text,size,&at,&cp)) return exr_fail(e,EXR_ENCODING,"Invalid hyphenation word UTF-8");
    if(count==WORD_SCALARS) return exr_fail(e,EXR_LIMIT,"Hyphenation word exceeds 256 scalars");
    offsets[count]=start; scalars[count++]=cp;
  }
  offsets[count]=size;
  status=exr_text_analyze(text,size,&boundaries,e); if(status!=EXR_OK) return status;
  h->busy=1;
  status=exr_control_poll(control,EXR_STAGE_LAYOUT,0,size,e);
  if(status==EXR_OK && size) status=h->provider.hyphenate ? h->provider.hyphenate(h->provider.context,key,text,size,out,control,e) :
    native_breaks(&w,key,scalars,offsets,count,boundaries,out);
  if(status<EXR_OK || status>EXR_UNSUPPORTED) status=exr_fail(e,EXR_FORMAT,"Hyphenation provider returned an invalid status");
  if(status==EXR_OK) {
    for(i=0;i<=size;i++) {
      if(out[i]>1 || (out[i] && i<size && ((unsigned char)text[i]&0xc0)==0x80)) { status=exr_fail(e,EXR_FORMAT,"Hyphenation provider returned invalid byte boundaries"); break; }
      if(!i || i==size || !(boundaries[i]&EXR_BOUNDARY_GRAPHEME) || (boundaries[i]&EXR_BOUNDARY_GLUE)) out[i]=0;
    }
    if(status==EXR_OK) status=exr_control_poll(control,EXR_STAGE_LAYOUT,size,size,e);
  }
  h->busy=0; free(boundaries);
  if(status!=EXR_OK) {
    memset(out,0,size+1);
    if(!e || !e->message[0]) return exr_fail(e,status,"Hyphenation provider failed");
    e->code=status; return status;
  }
  return exr_fail(e,EXR_OK,"");
}
size_t exr_hyphenator_memory_size(const exr_hyphenator *h) { return h ? h->bytes : 0; }
void exr_hyphenator_free(exr_hyphenator *h) {
  size_t i;
  if(!h || --h->refs) return;
  if(h->provider.release) h->provider.release(h->provider.context);
  for(i=0;i<h->count;i++) { free(h->dictionaries[i].nodes); free(h->dictionaries[i].edges); free(h->dictionaries[i].values); }
  free(h->dictionaries); free(h);
}
