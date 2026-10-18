/* SPDX-License-Identifier: GPL-3.0-only */
#include "hyphen_internal.h"
#include "normalize_internal.h"
#include "hyphen_unicode_data.h"

#define NONE UINT32_MAX
#define EDGE UINT32_C(0x110000)
#define WORD_SCALARS 256
#define FOLDED_SCALARS (EXR_CANONICAL_FOLD_FACTOR*WORD_SCALARS+2)
#define PATTERN_SCALARS 128
#define NORMAL_SCALARS (EXR_CANONICAL_FOLD_FACTOR*WORD_SCALARS)
#define NORMAL_PATTERN (EXR_CANONICAL_FOLD_FACTOR*PATTERN_SCALARS)
#define WORK_LIMIT (64u*1024u*1024u)
typedef struct {
  uint32_t cp,child,next,values;
  unsigned short length;
} hy_node;
typedef struct {
  uint32_t next;
  size_t point,first,last;
  char *text;size_t before,after;
  unsigned kind; /* 0 ordinary, 1 replacement, 2 conflicting replacements. */
} hy_change;
typedef struct {
  hy_node *nodes; size_t count,capacity;
  unsigned char *values; size_t value_count,value_capacity;
  uint32_t *edges;
  uint32_t *heads;size_t head_capacity;
  hy_change *changes;size_t change_count,change_capacity;
} hy_trie;
typedef struct { uint32_t *items;size_t count; } hy_sequence;
typedef struct {
  hy_trie trie;
  unsigned left,right,compound_left,compound_right;
  hy_sequence *nohyphen;size_t nohyphen_count,nohyphen_capacity;
} hy_level;
typedef struct {
  char language[256];
  unsigned left_override,right_override;
  int explicit_levels;
  hy_level levels[2]; /* Compound rules, then ordinary rules. */
} hy_dictionary;
struct exr_hyphenator {
  size_t refs,bytes,budget;
  int busy,replacements;
  exr_hyphen_provider provider;
  exr_hyphen_discretionary_provider discretionary;
  hy_dictionary *dictionaries;
  size_t count;
};
typedef struct {
  exr_hyphenator *owner;
  const exr_control *control;
  exr_error *error;
  size_t work;
} hy_work;

struct exr_hyphenation {
  exr_hyphen_break *items;size_t count,capacity,bytes;
};
typedef struct {
  exr_hyphenation *result;
  const char *word;size_t size;
  const unsigned char *boundaries;
  unsigned char seen[1025],*bitmap;
  exr_status status;exr_error error;
} hy_emitter;
typedef struct { const hy_change *change;size_t first,last; } hy_choice;

static int changing(const exr_hyphen_break *item) {
  return item->start!=item->point || item->end!=item->point || item->before_size || item->after_size;
}
static exr_status replacement_text(const char *text,size_t size,size_t *scalars,exr_error *error) {
  size_t at=0;uint32_t cp;
  if(!text && size) return exr_fail(error,EXR_ARGUMENT,"Missing discretionary replacement text");
  if(size>512) return exr_fail(error,EXR_LIMIT,"Discretionary text exceeds 512 bytes");
  while(at<size) {
    if(!exr_next(text,size,&at,&cp)) return exr_fail(error,EXR_ENCODING,"Invalid discretionary UTF-8 text");
    if(cp<32 || (cp>=0x7f && cp<=0x9f) || cp==0x2028 || cp==0x2029)
      return exr_fail(error,EXR_FORMAT,"Control character in discretionary text");
    if(++*scalars>128) return exr_fail(error,EXR_LIMIT,"Discretionary text exceeds 128 scalars");
  }
  return EXR_OK;
}
static int source_edge(const hy_emitter *emit,size_t at) {
  return !at || at==emit->size || !!(emit->boundaries[at]&EXR_BOUNDARY_GRAPHEME);
}
static exr_status emit_break(void *context,const exr_hyphen_break *item,exr_error *error) {
  hy_emitter *emit=context;exr_status status=EXR_OK;size_t scalars=0;
  if(emit->status!=EXR_OK) { if(error) *error=emit->error;return emit->status; }
  if(!item || item->start>item->point || item->point>item->end || item->end>emit->size)
    status=exr_fail(error,EXR_FORMAT,"Invalid discretionary source range");
  else if(item->before_size>512 || item->after_size>512-item->before_size)
    status=exr_fail(error,EXR_LIMIT,"Discretionary text exceeds 512 bytes");
  else if(!source_edge(emit,item->start) || !source_edge(emit,item->end) ||
      (item->point<emit->size && ((unsigned char)emit->word[item->point]&0xc0)==0x80))
    status=exr_fail(error,EXR_FORMAT,"Discretionary range cuts an original grapheme");
  if(status==EXR_OK) status=replacement_text(item->before,item->before_size,&scalars,error);
  if(status==EXR_OK) status=replacement_text(item->after,item->after_size,&scalars,error);
  if(status==EXR_OK && emit->seen[item->point]) status=exr_fail(error,EXR_FORMAT,"Duplicate discretionary point");
  if(status==EXR_OK) {
    exr_hyphenation *result=emit->result;emit->seen[item->point]=1;
    if(!item->point || item->point==emit->size || !source_edge(emit,item->point) ||
       (emit->boundaries[item->point]&EXR_BOUNDARY_GLUE)) return EXR_OK;
    if(result) {
      size_t delta,bytes=item->before_size+item->after_size+2;char *text;
      if(result->count==result->capacity) {
        size_t capacity=result->capacity ? result->capacity*2 : 8;void *items;
        if(capacity>256) capacity=256;
        delta=(capacity-result->capacity)*sizeof(*result->items);
        items=realloc(result->items,capacity*sizeof(*result->items));
        if(!items) status=exr_fail(error,EXR_MEMORY,"Discretionary array allocation failed");
        else { result->items=items;result->capacity=capacity;result->bytes+=delta; }
      }
      if(status==EXR_OK && bytes>256*1024-result->bytes) status=exr_fail(error,EXR_LIMIT,"Discretionary result exceeds 256 KiB");
      if(status==EXR_OK) {
        text=malloc(bytes);
        if(!text) status=exr_fail(error,EXR_MEMORY,"Discretionary text allocation failed");
        else {
          exr_hyphen_break *copy=&result->items[result->count++];*copy=*item;
          if(item->before_size) memcpy(text,item->before,item->before_size);
          text[item->before_size]=0;
          if(item->after_size) memcpy(text+item->before_size+1,item->after,item->after_size);
          text[bytes-1]=0;
          copy->before=text;copy->after=text+item->before_size+1;result->bytes+=bytes;
        }
      }
    } else if(!changing(item)) emit->bitmap[item->point]=1;
  }
  if(status!=EXR_OK) {
    emit->status=status;if(error) emit->error=*error;else exr_fail(&emit->error,status,"Invalid discretionary result");
  }
  return status;
}

static exr_status work(hy_work *w,size_t count) {
  if(count>WORK_LIMIT-w->work) return exr_fail(w->error,EXR_LIMIT,"Hyphenation work limit exceeded");
  if(w->work/1024!=(w->work+count)/1024) {
    exr_status status=exr_control_cancel(w->control,w->error); if(status!=EXR_OK) return status;
  }
  w->work+=count; return EXR_OK;
}
int exr_hyphen_language(const char *language,char out[256]) {
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
/* NFC -> full fold -> NFC, retaining intervals in the original scalar stream.
   ASCII dictionaries/words need no normalization table searches. */
static exr_status canonical_non_ascii(hy_work *w,const char *language,const uint32_t *input,size_t count,
                                      exr_normal_scalar *out,size_t capacity,size_t *written) {
  exr_normal_scalar scratch[NORMAL_SCALARS];size_t i,n,used=0;exr_status status;
  for(i=0;i<count;i++) scratch[i]=(exr_normal_scalar){input[i],(unsigned)i,(unsigned)i+1};
  status=exr_normalize_nfc(scratch,count,out,capacity,&n,w->control,&w->work,w->error);if(status!=EXR_OK) return status;
  for(i=0;i<n;i++) {
    uint32_t values[3];unsigned j,len=fold(out[i].cp,language,values);
    if(len>capacity-used) return exr_fail(w->error,EXR_LIMIT,"Canonical folding scalar limit exceeded");
    for(j=0;j<len;j++) scratch[used++]=(exr_normal_scalar){values[j],out[i].first,out[i].last};
  }
  return exr_normalize_nfc(scratch,used,out,capacity,written,w->control,&w->work,w->error);
}
static exr_status canonical_fold(hy_work *w,const char *language,const uint32_t *input,size_t count,
                                  exr_normal_scalar *out,size_t capacity,size_t *written) {
  size_t i;exr_status status;
  for(i=0;i<count;i++) if(input[i]>=128) return canonical_non_ascii(w,language,input,count,out,capacity,written);
  for(i=0;i<count;i++) {
    uint32_t values[3];fold(input[i],language,values);out[i]=(exr_normal_scalar){values[0],(unsigned)i,(unsigned)i+1};
  }
  status=work(w,count);if(status==EXR_OK) *written=count;return status;
}
/* A boundary survives only if every output on each side came exclusively from
   that original side. This excludes fold/decomposition interiors and reordered
   or composed spans, without guessing an offset from normalized byte lengths. */
static void original_boundaries(const exr_normal_scalar *items,size_t count,size_t originals,size_t *map) {
  unsigned suffix[NORMAL_SCALARS+1],high=0;size_t i;
  for(i=0;i<=originals;i++) map[i]=SIZE_MAX;
  suffix[count]=(unsigned)originals;
  for(i=count;i;i--) suffix[i-1]=items[i-1].first<suffix[i] ? items[i-1].first : suffix[i];
  for(i=0;i<=count;i++) {
    if(high==suffix[i]) map[high]=i;
    if(i<count && items[i].last>high) high=items[i].last;
  }
}
unsigned exr_hyphen_word_kind(uint32_t cp) {
  if(cp==0x200c || cp==0x200d) return 2; /* Joining controls stay inside the word. */
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
  while(next<needed) next*=2; /* Item limits / 128 MiB payload cap bound doubling. */
  delta=(next-*capacity)*unit;
  if(delta>w->owner->budget-w->owner->bytes) return exr_fail(w->error,EXR_LIMIT,"Hyphenation dictionary byte budget exceeded");
  p=realloc(*out,next*unit); if(!p) return exr_fail(w->error,EXR_MEMORY,"Hyphenation dictionary allocation failed");
  *out=p; *capacity=next; w->owner->bytes+=delta; return EXR_OK;
}
static exr_status child(hy_work *w,hy_dictionary *owner,hy_trie *d,uint32_t parent,uint32_t cp,uint32_t *out) {
  uint32_t previous=NONE,current=d->nodes[parent].child; exr_status status;
  while(current!=NONE && d->nodes[current].cp<cp) {
    status=work(w,1); if(status!=EXR_OK) return status;
    previous=current; current=d->nodes[current].next;
  }
  if(current!=NONE && d->nodes[current].cp==cp) { *out=current; return EXR_OK; }
  if(owner->levels[0].trie.count+owner->levels[1].trie.count>=1024*1024) return exr_fail(w->error,EXR_LIMIT,"Hyphenation dictionary exceeds one million trie nodes");
  status=reserve(w,(void **)&d->nodes,&d->capacity,d->count+1,sizeof(*d->nodes)); if(status!=EXR_OK) return status;
  *out=(uint32_t)d->count++; d->nodes[*out]=(hy_node){cp,NONE,current,NONE,0};
  if(previous==NONE) d->nodes[parent].child=*out; else d->nodes[previous].next=*out;
  return EXR_OK;
}
static exr_status change_heads(hy_work *w,hy_trie *d) {
  size_t previous=d->head_capacity;exr_status status=reserve(w,(void **)&d->heads,&d->head_capacity,d->capacity,sizeof(*d->heads));
  if(status==EXR_OK && d->head_capacity>previous) memset(d->heads+previous,0xff,(d->head_capacity-previous)*sizeof(*d->heads));
  return status;
}
static void change_clear(hy_work *w,hy_change *change) {
  if(change->text) { w->owner->bytes-=change->before+change->after+2;free(change->text);change->text=NULL; }
  change->kind=0;
}
static int change_equal(const hy_change *a,const hy_change *b) {
  return a->first==b->first && a->last==b->last && a->before==b->before && a->after==b->after &&
    !memcmp(a->text,b->text,a->before+a->after+2);
}
static exr_status change_update(hy_work *w,hy_trie *d,uint32_t node,const unsigned char *scores,size_t count,const hy_change *replacement) {
  size_t i;exr_status status;
  if(!replacement && (!d->heads || node>=d->head_capacity || d->heads[node]==NONE)) return EXR_OK;
  if(d->heads || replacement) { status=change_heads(w,d);if(status!=EXR_OK) return status; }
  for(i=0;i<=count;i++) {
    uint32_t index=d->heads ? d->heads[node] : NONE;hy_change *existing=NULL;
    unsigned old=d->nodes[node].values==NONE ? 0 : d->values[d->nodes[node].values+i];
    int replacing=replacement && replacement->point==i;
    if(!scores[i] || scores[i]<old) continue;
    while(index!=NONE) {
      status=work(w,1);if(status!=EXR_OK) return status;
      if(d->changes[index].point==i) { existing=&d->changes[index];break; }
      index=d->changes[index].next;
    }
    /* A plain equal-weight rule wins. Different equal-weight rewrites suppress
       the ambiguous point; a strictly higher weight can resolve it again. */
    if(!replacing) { if(existing) change_clear(w,existing);continue; }
    if(scores[i]==old) {
      if(existing && existing->kind==1 && !change_equal(existing,replacement)) { change_clear(w,existing);existing->kind=2; }
      continue;
    }
    if(!existing) {
      status=reserve(w,(void **)&d->changes,&d->change_capacity,d->change_count+1,sizeof(*d->changes));if(status!=EXR_OK) return status;
      index=(uint32_t)d->change_count++;existing=&d->changes[index];
      *existing=(hy_change){0};existing->point=i;existing->next=d->heads[node];d->heads[node]=index;
    } else change_clear(w,existing);
    {
      size_t bytes=replacement->before+replacement->after+2;char *text;
      if(bytes>w->owner->budget-w->owner->bytes) return exr_fail(w->error,EXR_LIMIT,"Discretionary dictionary byte budget exceeded");
      text=malloc(bytes);if(!text) return exr_fail(w->error,EXR_MEMORY,"Discretionary dictionary allocation failed");
      memcpy(text,replacement->text,bytes);existing->text=text;existing->before=replacement->before;existing->after=replacement->after;
      existing->first=replacement->first;existing->last=replacement->last;existing->kind=1;w->owner->bytes+=bytes;
    }
  }
  return EXR_OK;
}
static exr_status change_parse(hy_work *w,const char *text,size_t size,const uint32_t *letters,
                               const unsigned char *weights,size_t count,hy_change *change,char buffer[514]) {
  size_t equal=SIZE_MAX,comma=size,i,base=count && letters[0]=='.',end=count-(count && letters[count-1]=='.'),start=1,cut=end-base;
  size_t scalars=0,point=SIZE_MAX;exr_status status;
  if(end<base) return exr_fail(w->error,EXR_FORMAT,"Discretionary pattern has no source letters");
  for(i=0;i<size;i++) {
    if(text[i]==',') { comma=i;break; }
    if(text[i]=='=') { if(equal!=SIZE_MAX) return exr_fail(w->error,EXR_FORMAT,"Multiple discretionary separators");equal=i; }
  }
  if(equal==SIZE_MAX) return exr_fail(w->error,EXR_FORMAT,"Missing discretionary separator");
  if(comma<size) {
    size_t values[2]={0,0};unsigned field=0,digits=0;
    for(i=comma+1;i<size;i++) {
      if(text[i]==',' && !field && digits) { field=1;digits=0;continue; }
      if(text[i]<'0' || text[i]>'9' || values[field]>128) return exr_fail(w->error,EXR_FORMAT,"Invalid discretionary range number");
      values[field]=values[field]*10+(unsigned)(text[i]-'0');digits++;
    }
    if(!field || !digits || !values[0] || values[0]>129 || values[1]>128) return exr_fail(w->error,EXR_FORMAT,"Invalid discretionary range");
    start=values[0];cut=values[1];
  }
  change->first=base+start-1;
  if(change->first>end || cut>end-change->first) return exr_fail(w->error,EXR_FORMAT,"Discretionary range outside pattern");
  change->last=change->first+cut;
  for(i=change->first;i<=change->last;i++) if(weights[i]&1) {
    if(point!=SIZE_MAX) return exr_fail(w->error,EXR_FORMAT,"Multiple odd weights in discretionary range");
    point=i;
  }
  if(point==SIZE_MAX) return exr_fail(w->error,EXR_FORMAT,"No odd weight in discretionary range");
  status=replacement_text(text,equal,&scalars,w->error);
  if(status==EXR_OK) status=replacement_text(text+equal+1,comma-equal-1,&scalars,w->error);
  if(status!=EXR_OK) return status;
  if(comma-1>512) return exr_fail(w->error,EXR_LIMIT,"Discretionary text exceeds 512 bytes");
  memcpy(buffer,text,equal);buffer[equal]=0;memcpy(buffer+equal+1,text+equal+1,comma-equal-1);buffer[comma]=0;
  change->point=point;change->before=equal;change->after=comma-equal-1;change->text=buffer;change->kind=1;return EXR_OK;
}
static exr_status pattern(hy_work *w,hy_dictionary *owner,hy_trie *d,const char *text,size_t size) {
  uint32_t letters[PATTERN_SCALARS],node=0;unsigned char original[PATTERN_SCALARS+1]={0},scores[NORMAL_PATTERN+1]={0};
  exr_normal_scalar normalized[NORMAL_PATTERN];size_t map[PATTERN_SCALARS+1];
  size_t at=0,count=0,n=0,i,slash=0;int digit=0;exr_status status;hy_change change={0};char replacement[514];
  while(slash<size && text[slash]!='/') slash++;
  while(at<slash) {
    uint32_t cp;
    if(!exr_next(text,slash,&at,&cp)) return exr_fail(w->error,EXR_ENCODING,"Invalid UTF-8 hyphenation pattern");
    if(cp>='0' && cp<='9') {
      if(digit) return exr_fail(w->error,EXR_FORMAT,"Adjacent hyphenation weights");
      original[count]=(unsigned char)(cp-'0');digit=1;continue;
    }
    digit=0;
    if(cp=='\\' || cp=='{' || cp=='}' || cp=='=') return exr_fail(w->error,EXR_UNSUPPORTED,"Raw TeX commands are unsupported");
    if(cp<0x20 || cp==0x7f || count==PATTERN_SCALARS) return exr_fail(w->error,EXR_LIMIT,"Invalid or overlong hyphenation pattern");
    letters[count++]=cp;
  }
  if(!count) return exr_fail(w->error,EXR_FORMAT,"Hyphenation pattern has no letters");
  if(slash<size) { status=change_parse(w,text+slash+1,size-slash-1,letters,original,count,&change,replacement);if(status!=EXR_OK) return status; }
  status=canonical_fold(w,owner->language,letters,count,normalized,NORMAL_PATTERN,&n);if(status!=EXR_OK) return status;
  if(!d->count) {
    if(owner->levels[0].trie.count+owner->levels[1].trie.count>=1024*1024) return exr_fail(w->error,EXR_LIMIT,"Hyphenation dictionary exceeds one million trie nodes");
    status=reserve(w,(void **)&d->nodes,&d->capacity,1,sizeof(*d->nodes));if(status!=EXR_OK) return status;
    d->count=1;d->nodes[0]=(hy_node){0,NONE,NONE,NONE,0};
  }
  original_boundaries(normalized,n,count,map);
  for(i=0;i<=count;i++) if(map[i]!=SIZE_MAX && original[i]>scores[map[i]]) scores[map[i]]=original[i];
  if(change.text) {
    if(map[change.point]==SIZE_MAX || map[change.first]==SIZE_MAX || map[change.last]==SIZE_MAX)
      return exr_fail(w->error,EXR_FORMAT,"Discretionary range cuts a canonical source span");
    change.point=map[change.point];change.first=map[change.first];change.last=map[change.last];
  }
  for(i=0;i<n;i++) { uint32_t cp=normalized[i].cp=='.' ? EDGE : normalized[i].cp;status=child(w,owner,d,node,cp,&node);if(status!=EXR_OK) return status; }
  status=change_update(w,d,node,scores,n,change.text ? &change : NULL);if(status!=EXR_OK) return status;
  if(d->nodes[node].values==NONE) {
    status=reserve(w,(void **)&d->values,&d->value_capacity,d->value_count+n+1,1);if(status!=EXR_OK) return status;
    d->nodes[node].values=(uint32_t)d->value_count;d->nodes[node].length=(unsigned short)(n+1);
    memcpy(d->values+d->value_count,scores,n+1);d->value_count+=n+1;
  } else for(i=0;i<=n;i++) {
    unsigned char *v=&d->values[d->nodes[node].values+i];if(scores[i]>*v) *v=scores[i];
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
static void nohyphen_clear(hy_work *w,hy_level *level) {
  size_t i;for(i=0;i<level->nohyphen_count;i++) {
    w->owner->bytes-=level->nohyphen[i].count*sizeof(uint32_t);free(level->nohyphen[i].items);
  }
  level->nohyphen_count=0;
}
static exr_status nohyphen(hy_work *w,hy_dictionary *d,hy_level *level,const char *text,size_t size) {
  size_t at=0;nohyphen_clear(w,level);
  while(at<size) {
    uint32_t scalars[PATTERN_SCALARS];exr_normal_scalar normalized[NORMAL_PATTERN];size_t count=0,n=0,i;hy_sequence *sequence;exr_status status;
    while(at<size && text[at]!=',') {
      uint32_t cp;if(!exr_next(text,size,&at,&cp)) return exr_fail(w->error,EXR_ENCODING,"Invalid NOHYPHEN UTF-8");
      if(cp<32 || cp==127) return exr_fail(w->error,EXR_FORMAT,"Control character in NOHYPHEN");
      if(count==PATTERN_SCALARS) return exr_fail(w->error,EXR_LIMIT,"NOHYPHEN sequence exceeds 128 scalars");
      scalars[count++]=cp;
    }
    if(!count || (at<size && ++at==size)) return exr_fail(w->error,EXR_FORMAT,"Empty NOHYPHEN sequence");
    if(level->nohyphen_count==64) return exr_fail(w->error,EXR_LIMIT,"NOHYPHEN exceeds 64 sequences");
    status=canonical_fold(w,d->language,scalars,count,normalized,NORMAL_PATTERN,&n);if(status!=EXR_OK) return status;
    status=reserve(w,(void **)&level->nohyphen,&level->nohyphen_capacity,level->nohyphen_count+1,sizeof(*level->nohyphen));if(status!=EXR_OK) return status;
    if(n*sizeof(uint32_t)>w->owner->budget-w->owner->bytes) return exr_fail(w->error,EXR_LIMIT,"NOHYPHEN byte budget exceeded");
    sequence=&level->nohyphen[level->nohyphen_count];sequence->items=malloc(n*sizeof(uint32_t));
    if(!sequence->items) return exr_fail(w->error,EXR_MEMORY,"NOHYPHEN allocation failed");
    sequence->count=n;for(i=0;i<n;i++) sequence->items[i]=normalized[i].cp;
    level->nohyphen_count++;w->owner->bytes+=n*sizeof(uint32_t);
  }
  return EXR_OK;
}
static exr_status pack(hy_work *w,hy_trie *d) {
  if(d->heads) { exr_status status=change_heads(w,d);if(status!=EXR_OK) return status; }
  if(d->count>1) {
    size_t bytes=(d->count-1)*sizeof(*d->edges),i,index=0;exr_status status;
    if(bytes>w->owner->budget-w->owner->bytes) return exr_fail(w->error,EXR_LIMIT,"Packed hyphenation trie exceeds byte budget");
    d->edges=malloc(bytes);if(!d->edges) return exr_fail(w->error,EXR_MEMORY,"Packed hyphenation trie allocation failed");
    w->owner->bytes+=bytes;
    for(i=0;i<d->count;i++) {
      uint32_t next=d->nodes[i].child;size_t start=index;
      while(next!=NONE) { d->edges[index++]=next;next=d->nodes[next].next; }
      d->nodes[i].child=(uint32_t)start;d->nodes[i].next=(uint32_t)(index-start);
      status=work(w,index-start+1);if(status!=EXR_OK) return status;
    }
  } else if(d->count) { d->nodes[0].child=0;d->nodes[0].next=0; }
  return EXR_OK;
}
static exr_status load(hy_work *w,hy_dictionary *d,const exr_hyphen_pattern_input *input) {
  const char *text=input->patterns;size_t at=0,first,end,patterns=0;unsigned level=0;int header=1;exr_status status;
  d->left_override=input->left_min;d->right_override=input->right_min;
  if(input->size>=3 && !memcmp(text,"\xef\xbb\xbf",3)) at=3;
  while(token(text,input->size,&at,&first,&end)) {
    hy_level *current=&d->levels[level];int field=-1;
    status=exr_control_poll(w->control,EXR_STAGE_READ,at,input->size,w->error);if(status!=EXR_OK) return status;
    if(header && matches(text,first,end,"UTF-8")) { header=0;continue; }
    if(header && ((end-first>=4 && !memcmp(text+first,"UTF-",4)) ||
       (end-first>=7 && !memcmp(text+first,"ISO8859",7)) || matches(text,first,end,"KOI8-R") || matches(text,first,end,"KOI8-U")))
      return exr_fail(w->error,EXR_UNSUPPORTED,"Only UTF-8 hyphenation dictionaries are supported");
    header=0;
    if(matches(text,first,end,"LEFTHYPHENMIN")) field=0;
    else if(matches(text,first,end,"RIGHTHYPHENMIN")) field=1;
    else if(matches(text,first,end,"COMPOUNDLEFTHYPHENMIN")) field=2;
    else if(matches(text,first,end,"COMPOUNDRIGHTHYPHENMIN")) field=3;
    if(field>=0) {
      unsigned number=0;size_t start;
      if(!token(text,input->size,&at,&first,&end) || end-first>2) return exr_fail(w->error,EXR_FORMAT,"Missing or invalid HYPHENMIN value");
      for(start=first;start<end;start++) { if(text[start]<'0' || text[start]>'9') return exr_fail(w->error,EXR_FORMAT,"Invalid HYPHENMIN number");number=number*10+(unsigned)(text[start]-'0'); }
      if(number>64) return exr_fail(w->error,EXR_LIMIT,"Hyphenation edge minimum exceeds 64");
      if(field==0) current->left=number;else if(field==1) current->right=number;
      else if(field==2) current->compound_left=number;else current->compound_right=number;
      continue;
    }
    if(matches(text,first,end,"NEXTLEVEL")) {
      if(level) return exr_fail(w->error,EXR_FORMAT,"Only two hyphenation levels are supported");
      level=1;continue;
    }
    if(matches(text,first,end,"NOHYPHEN")) {
      size_t next=at;while(next<input->size && (text[next]==' ' || text[next]=='\t')) next++;
      if(next==input->size || text[next]=='\r' || text[next]=='\n' || text[next]=='%' || text[next]=='#') {
        nohyphen_clear(w,current);continue;
      }
      token(text,input->size,&at,&first,&end);
      status=nohyphen(w,d,current,text+first,end-first);if(status!=EXR_OK) return status;
      continue;
    }
    if((end-first>=8 && !memcmp(text+first,"COMPOUND",8)) || matches(text,first,end,"NEXTWORD"))
      return exr_fail(w->error,EXR_UNSUPPORTED,"Unknown compound dictionary directive");
    if(++patterns>262144) return exr_fail(w->error,EXR_LIMIT,"More than 262144 hyphenation patterns");
    status=pattern(w,d,&current->trie,text+first,end-first);
    if(status!=EXR_OK) {
      if(w->error) {
        char reason[256];memcpy(reason,w->error->message,sizeof(reason));reason[255]=0;
        return exr_fail(w->error,status,"Pattern at byte %zu: %.200s",first,reason);
      }
      return status;
    }
  }
  d->explicit_levels=(int)level;
  if(!level) {
    static const char *separators[]={"1-1","1'1","1–1","1’1"};size_t i;
    d->levels[1]=d->levels[0];memset(&d->levels[0],0,sizeof(d->levels[0]));
    d->levels[0].left=d->levels[1].left;d->levels[0].right=d->levels[1].right;
    d->levels[0].compound_left=d->levels[1].compound_left ? d->levels[1].compound_left : d->levels[1].left ? d->levels[1].left : 3;
    d->levels[0].compound_right=d->levels[1].compound_right ? d->levels[1].compound_right : d->levels[1].right ? d->levels[1].right : 3;
    for(i=0;i<4;i++) { status=pattern(w,d,&d->levels[0].trie,separators[i],strlen(separators[i]));if(status!=EXR_OK) return status; }
    status=nohyphen(w,d,&d->levels[0],"-,',–,’",strlen("-,',–,’"));if(status!=EXR_OK) return status;
  }
  status=pack(w,&d->levels[0].trie);if(status==EXR_OK) status=pack(w,&d->levels[1].trie);return status;
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
/* Pattern scores for one part with virtual word-edge anchors. */
static exr_status overlay(hy_work *w,const hy_trie *d,const uint32_t *word,size_t first,size_t last,unsigned char *scores,hy_choice *choices) {
  size_t i,j,length=last-first;exr_status status;
  memset(scores,0,length+3);if(choices) memset(choices,0,(length+3)*sizeof(*choices));
  if(!d->count) return EXR_OK;
  for(i=0;i<length+2;i++) {
    uint32_t node=0;
    for(j=i;j<length+2;j++) {
      uint32_t cp=!j || j==length+1 ? EDGE : word[first+j-1];
      const hy_node *parent=&d->nodes[node];size_t lo=parent->child,hi=lo+parent->next,limit=hi;
      while(lo<hi) {
        size_t mid=lo+(hi-lo)/2;if(d->nodes[d->edges[mid]].cp<cp) lo=mid+1;else hi=mid;
        status=work(w,1);if(status!=EXR_OK) return status;
      }
      if(lo==limit || d->nodes[d->edges[lo]].cp!=cp) break;
      node=d->edges[lo];
      if(d->nodes[node].values!=NONE) {
        size_t k,n=d->nodes[node].length;const unsigned char *values=d->values+d->nodes[node].values;
        if(!choices) {
          for(k=0;k<n;k++) if(values[k]>scores[i+k]) scores[i+k]=values[k];
        } else for(k=0;k<n;k++) {
          unsigned value=values[k];hy_choice candidate={0};
          if(choices && (value&1) && value>=scores[i+k] && d->heads) {
            uint32_t index=d->heads[node];
            while(index!=NONE) {
              const hy_change *change=&d->changes[index];
              status=work(w,1);if(status!=EXR_OK) return status;
              if(change->point==k && change->kind) {
                /* Anchor-inclusive indices become part-relative word indices.
                   Replacement edges never include the virtual anchors. */
                if(i+change->first && i+change->last<=length+1)
                  candidate=(hy_choice){change,first+i+change->first-1,first+i+change->last-1};
                break;
              }
              index=change->next;
            }
          }
          if(value>scores[i+k]) { scores[i+k]=(unsigned char)value;if(choices) choices[i+k]=candidate; }
          else if(choices && (value&1) && value==scores[i+k]) {
            hy_choice *previous=&choices[i+k];
            if(!candidate.change || !previous->change) *previous=(hy_choice){0};
            else if(candidate.change->kind==2 || previous->change->kind==2 || candidate.first!=previous->first ||
                candidate.last!=previous->last || candidate.change->before!=previous->change->before ||
                candidate.change->after!=previous->change->after ||
                memcmp(candidate.change->text,previous->change->text,candidate.change->before+candidate.change->after+2)) {
              static const hy_change conflict={.kind=2};*previous=(hy_choice){&conflict,0,0};
            }
          }
        }
        status=work(w,n);if(status!=EXR_OK) return status;
      }
    }
  }
  return EXR_OK;
}
static exr_status native_match(hy_work *w,hy_dictionary *d,const uint32_t *scalars,
                                const size_t *offsets,size_t count,const unsigned char *boundaries,unsigned char *out,
                                hy_choice *choices,hy_choice *chosen,hy_emitter *emit) {
  typedef struct { size_t first,last; } part;
  hy_level *root;exr_status status;
  uint32_t word[NORMAL_SCALARS];exr_normal_scalar normalized[NORMAL_SCALARS];
  size_t folded_at[WORD_SCALARS+1],original_at[NORMAL_SCALARS+1],n=0,i,j,graphemes[WORD_SCALARS+1]={0};
  unsigned char scores[FOLDED_SCALARS+1]={0},selected[WORD_SCALARS+1]={0};part pending[WORD_SCALARS];size_t pending_count=0;
  unsigned left,right;int separator=0;
  root=&d->levels[0];left=d->left_override ? d->left_override : root->left ? root->left : 2;
  right=d->right_override ? d->right_override : root->right ? root->right : 2;
  status=canonical_fold(w,d->language,scalars,count,normalized,NORMAL_SCALARS,&n);if(status!=EXR_OK) return status;
  original_boundaries(normalized,n,count,folded_at);
  for(i=0;i<n;i++) {
    uint32_t cp=normalized[i].cp;word[i]=cp;separator|=cp=='-' || cp=='\'' || cp==0x2013 || cp==0x2019;
  }
  for(i=0;i<count;i++) graphemes[i+1]=graphemes[i]+!!(boundaries[offsets[i]]&EXR_BOUNDARY_GRAPHEME);
  /* Ordinary words cannot match the implicit separator layer. Keep their
     common query path to one overlay and the original-boundary map. */
  if((!d->explicit_levels && !separator) || (!root->trie.count && !root->nohyphen_count)) {
    status=overlay(w,&d->levels[1].trie,word,0,n,scores,choices);if(status!=EXR_OK) return status;
    for(i=1;i<count;i++) if(folded_at[i]!=SIZE_MAX && graphemes[i]>=left && graphemes[count]-graphemes[i]>=right)
      if(scores[folded_at[i]+1]&1) { selected[i]=1;if(chosen) chosen[i]=choices[folded_at[i]+1]; }
    goto publish;
  }
  for(i=0;i<=n;i++) original_at[i]=SIZE_MAX;
  /* Protected punctuation can still delimit structural parts. Only the final
     returned breaks are intersected with GLUE, so an apostrophe can establish
     compound minima without permitting a visible break beside it. */
  for(i=0;i<=count;i++) if(folded_at[i]!=SIZE_MAX && (boundaries[offsets[i]]&EXR_BOUNDARY_GRAPHEME)) original_at[folded_at[i]]=i;
  /* Endpoints are structural even when the text API has no final grapheme bit. */
  original_at[0]=0;original_at[n]=count;
  pending[pending_count++]=(part){0,n};
  while(pending_count) {
    part current=pending[--pending_count];size_t begin=current.first;int split=0;
    status=overlay(w,&root->trie,word,current.first,current.last,scores,choices);if(status!=EXR_OK) return status;
    for(i=current.first+1;i<current.last;i++) if(original_at[i]!=SIZE_MAX && (scores[i-current.first+1]&1)) {
      if(pending_count==WORD_SCALARS) return exr_fail(w->error,EXR_LIMIT,"Compound part work queue exceeded");
      selected[original_at[i]]=1;if(chosen) chosen[original_at[i]]=choices[i-current.first+1];
      pending[pending_count++]=(part){begin,i};begin=i;split=1;
    }
    if(split) {
      if(pending_count==WORD_SCALARS) return exr_fail(w->error,EXR_LIMIT,"Compound part work queue exceeded");
      pending[pending_count++]=(part){begin,current.last};continue;
    }
    status=overlay(w,&d->levels[1].trie,word,current.first,current.last,scores,choices);if(status!=EXR_OK) return status;
    for(i=current.first+1;i<current.last;i++) if(original_at[i]!=SIZE_MAX && (scores[i-current.first+1]&1)) {
      size_t original=original_at[i],first=original_at[current.first],last=original_at[current.last];
      if((!current.first || graphemes[original]-graphemes[first]>=root->compound_left) &&
         (current.last==n || graphemes[last]-graphemes[original]>=root->compound_right)) {
        selected[original]=1;if(chosen) chosen[original]=choices[i-current.first+1];
      }
    }
  }
  for(i=0;i<root->nohyphen_count;i++) {
    const hy_sequence *sequence=&root->nohyphen[i];if(sequence->count>n) continue;
    for(j=0;j<=n-sequence->count;j++) {
      size_t k;for(k=0;k<sequence->count && word[j+k]==sequence->items[k];k++) {}
      status=work(w,k+1);if(status!=EXR_OK) return status;
      if(k==sequence->count) {
        if(original_at[j]!=SIZE_MAX) selected[original_at[j]]=0;
        if(original_at[j+k]!=SIZE_MAX) selected[original_at[j+k]]=0;
      }
    }
  }
publish:
  for(i=1;i<count;i++) if(selected[i] && graphemes[i]>=left && graphemes[count]-graphemes[i]>=right) {
    const hy_choice *choice=chosen ? &chosen[i] : NULL;
    if(choice && choice->change) {
      size_t first=SIZE_MAX,last=SIZE_MAX;const hy_change *change=choice->change;exr_hyphen_break item;
      if(change->kind==2) continue;
      for(j=0;j<=count;j++) {
        if(folded_at[j]==choice->first) first=j;
        if(folded_at[j]==choice->last) last=j;
      }
      if(first==SIZE_MAX || last==SIZE_MAX || first>i || last<i ||
          (first && !(boundaries[offsets[first]]&EXR_BOUNDARY_GRAPHEME)) ||
          (last<count && !(boundaries[offsets[last]]&EXR_BOUNDARY_GRAPHEME))) continue;
      item=(exr_hyphen_break){offsets[i],offsets[first],offsets[last],change->text,change->text+change->before+1,change->before,change->after};
      if(emit) { status=emit_break(emit,&item,w->error);if(status!=EXR_OK) return status; }
      else if(!changing(&item)) out[offsets[i]]=1;
    } else out[offsets[i]]=1;
  }
  return EXR_OK;
}
static exr_status native_breaks(hy_work *w,const char *language,const uint32_t *scalars,
                                const size_t *offsets,size_t count,const unsigned char *boundaries,unsigned char *out,hy_emitter *emit) {
  hy_dictionary *d=dictionary(w->owner,language);hy_choice *choices=NULL;exr_status status;
  if(!d) return EXR_OK;
  if(d->levels[0].trie.change_count || d->levels[1].trie.change_count) {
    choices=calloc(NORMAL_SCALARS+3+WORD_SCALARS+1,sizeof(*choices));
    if(!choices) return exr_fail(w->error,EXR_MEMORY,"Discretionary matching scratch allocation failed");
  }
  status=native_match(w,d,scalars,offsets,count,boundaries,out,choices,choices ? choices+NORMAL_SCALARS+3 : NULL,emit);
  free(choices);return status;
}

exr_status exr_hyphenator_create(const exr_hyphen_provider *provider,exr_hyphenator **out,exr_error *e) {
  exr_hyphenator *h;
  if(!out) return exr_fail(e,EXR_ARGUMENT,"Missing hyphenator output");
  *out=NULL;
  if(!provider || provider->struct_size!=sizeof(*provider) || !provider->hyphenate) return exr_fail(e,EXR_ARGUMENT,"Invalid hyphenation provider");
  h=calloc(1,sizeof(*h)); if(!h) return exr_fail(e,EXR_MEMORY,"Hyphenator allocation failed");
  h->provider=*provider; h->refs=1; h->bytes=sizeof(*h); *out=h; return exr_fail(e,EXR_OK,"");
}
exr_status exr_hyphenator_create_discretionary(const exr_hyphen_discretionary_provider *provider,exr_hyphenator **out,exr_error *e) {
  exr_hyphenator *h;
  if(!out) return exr_fail(e,EXR_ARGUMENT,"Missing hyphenator output");
  *out=NULL;
  if(!provider || provider->struct_size!=sizeof(*provider) || !provider->hyphenate) return exr_fail(e,EXR_ARGUMENT,"Invalid discretionary provider");
  h=calloc(1,sizeof(*h));if(!h) return exr_fail(e,EXR_MEMORY,"Hyphenator allocation failed");
  h->discretionary=*provider;h->refs=1;h->bytes=sizeof(*h);*out=h;return exr_fail(e,EXR_OK,"");
}
exr_status exr_hyphenator_create_patterns(const exr_hyphen_pattern_input *inputs,size_t count,size_t budget,
                                          const exr_control *control,exr_hyphenator **out,exr_error *e) {
  exr_hyphenator *h; hy_work w={0}; size_t i,j,total=0; exr_status status=EXR_OK;
  if(!out) return exr_fail(e,EXR_ARGUMENT,"Missing hyphenator output");
  *out=NULL;
  if(!inputs || !count || count>64 || budget>EXR_MAX_INPUT) return exr_fail(e,EXR_ARGUMENT,"Invalid hyphenation dictionary registry");
  for(i=0;i<count;i++) {
    char key[256];
    if(inputs[i].struct_size!=sizeof(*inputs) || (!inputs[i].patterns && inputs[i].size) || !exr_hyphen_language(inputs[i].language,key)) return exr_fail(e,EXR_ARGUMENT,"Invalid hyphenation dictionary input");
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
    exr_hyphen_language(inputs[i].language,h->dictionaries[i].language);
    for(j=0;j<i;j++) if(!strcmp(h->dictionaries[j].language,h->dictionaries[i].language)) { status=exr_fail(e,EXR_ARGUMENT,"Duplicate hyphenation language key"); goto failed; }
    status=exr_control_poll(control,EXR_STAGE_READ,i,count,e); if(status!=EXR_OK) goto failed;
    status=load(&w,&h->dictionaries[i],&inputs[i]); if(status!=EXR_OK) goto failed;
    h->replacements|=h->dictionaries[i].levels[0].trie.change_count!=0 || h->dictionaries[i].levels[1].trie.change_count!=0;
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
static exr_status query(exr_hyphenator *h,const char *language,const char *text,size_t size,
                         unsigned char *out,exr_hyphenation *result,const exr_control *control,exr_error *e) {
  uint32_t scalars[WORD_SCALARS]; size_t offsets[WORD_SCALARS+1],count=0,at=0,i;
  unsigned char *boundaries=NULL;char key[256];exr_status status;hy_work w={h,control,e,0};hy_emitter emit,*destination=NULL;
  if(size>1024) return exr_fail(e,EXR_LIMIT,"Hyphenation word exceeds 1024 UTF-8 bytes");
  if(out) memset(out,0,size+1);
  if(!h || h->busy || !text || !out || !exr_hyphen_language(language,key)) return exr_fail(e,EXR_ARGUMENT,"Invalid or reentrant hyphenation query");
  if(e) memset(e,0,sizeof(*e));
  while(at<size) {
    uint32_t cp; size_t start=at;
    if(!exr_next(text,size,&at,&cp)) return exr_fail(e,EXR_ENCODING,"Invalid hyphenation word UTF-8");
    if(count==WORD_SCALARS) return exr_fail(e,EXR_LIMIT,"Hyphenation word exceeds 256 scalars");
    offsets[count]=start; scalars[count++]=cp;
  }
  offsets[count]=size;
  status=exr_text_analyze(text,size,&boundaries,e); if(status!=EXR_OK) return status;
  if(result || h->discretionary.hyphenate) {
    memset(&emit,0,sizeof(emit));emit.result=result;emit.word=text;emit.size=size;emit.boundaries=boundaries;emit.bitmap=out;destination=&emit;
  }
  h->busy=1;
  status=exr_control_poll(control,EXR_STAGE_LAYOUT,0,size,e);
  if(status==EXR_OK && size) {
    if(h->discretionary.hyphenate) status=h->discretionary.hyphenate(h->discretionary.context,key,text,size,emit_break,&emit,control,e);
    else if(h->provider.hyphenate) status=h->provider.hyphenate(h->provider.context,key,text,size,out,control,e);
    else status=native_breaks(&w,key,scalars,offsets,count,boundaries,out,destination);
  }
  if(destination && emit.status!=EXR_OK) { status=emit.status;if(e) *e=emit.error; }
  if(status<EXR_OK || status>EXR_UNSUPPORTED) status=exr_fail(e,EXR_FORMAT,"Hyphenation provider returned an invalid status");
  if(status==EXR_OK) {
    for(i=0;i<=size;i++) {
      if(out[i]>1 || (out[i] && i<size && ((unsigned char)text[i]&0xc0)==0x80)) { status=exr_fail(e,EXR_FORMAT,"Hyphenation provider returned invalid byte boundaries"); break; }
      if(!i || i==size || !(boundaries[i]&EXR_BOUNDARY_GRAPHEME) || (boundaries[i]&EXR_BOUNDARY_GLUE)) out[i]=0;
    }
    if(status==EXR_OK && result) for(i=1;i<size;i++) if(out[i]) {
      exr_hyphen_break item={i,i,i,NULL,NULL,0,0};
      status=emit_break(&emit,&item,e);if(status!=EXR_OK) break;
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
exr_status exr_hyphenator_breaks(exr_hyphenator *h,const char *language,const char *text,size_t size,
                                 unsigned char *out,const exr_control *control,exr_error *e) {
  return query(h,language,text,size,out,NULL,control,e);
}
static int point_compare(const void *left,const void *right) {
  size_t a=((const exr_hyphen_break *)left)->point,b=((const exr_hyphen_break *)right)->point;
  return a<b ? -1 : a>b;
}
exr_status exr_hyphenator_query(exr_hyphenator *h,const char *language,const char *text,size_t size,
                               const exr_control *control,exr_hyphenation **out,exr_error *e) {
  unsigned char bitmap[1025];exr_status status;exr_hyphenation *result;
  if(!out) return exr_fail(e,EXR_ARGUMENT,"Missing discretionary query output");
  *out=NULL;
  if(size>1024) return exr_fail(e,EXR_LIMIT,"Hyphenation word exceeds 1024 UTF-8 bytes");
  result=calloc(1,sizeof(*result));if(!result) return exr_fail(e,EXR_MEMORY,"Discretionary result allocation failed");
  result->bytes=sizeof(*result);
  status=query(h,language,text,size,bitmap,result,control,e);
  if(status!=EXR_OK) { exr_hyphenation_free(result);return status; }
  if(result->count>1) qsort(result->items,result->count,sizeof(*result->items),point_compare);
  *out=result;return EXR_OK;
}
const exr_hyphen_break *exr_hyphenation_breaks(const exr_hyphenation *result,size_t *count) {
  if(count) *count=result ? result->count : 0;
  return result ? result->items : NULL;
}
size_t exr_hyphenation_memory_size(const exr_hyphenation *result) { return result ? result->bytes : 0; }
void exr_hyphenation_free(exr_hyphenation *result) {
  size_t i;if(!result) return;
  for(i=0;i<result->count;i++) free((void *)result->items[i].before);
  free(result->items);free(result);
}
size_t exr_hyphenator_memory_size(const exr_hyphenator *h) { return h ? h->bytes : 0; }
int exr_hyphenator_replacements(const exr_hyphenator *h) {
  return h && (h->replacements || h->discretionary.hyphenate);
}
void exr_hyphenator_free(exr_hyphenator *h) {
  size_t i,j,k;
  if(!h || --h->refs) return;
  if(h->provider.release) h->provider.release(h->provider.context);
  if(h->discretionary.release) h->discretionary.release(h->discretionary.context);
  for(i=0;i<h->count;i++) for(j=0;j<2;j++) {
    hy_level *level=&h->dictionaries[i].levels[j];
    free(level->trie.nodes);free(level->trie.edges);free(level->trie.values);free(level->trie.heads);
    for(k=0;k<level->trie.change_count;k++) free(level->trie.changes[k].text);
    free(level->trie.changes);
    for(k=0;k<level->nohyphen_count;k++) free(level->nohyphen[k].items);
    free(level->nohyphen);
  }
  free(h->dictionaries); free(h);
}
