/* SPDX-License-Identifier: MIT */
#include "exr/dictionary.h"
#include "base_internal.h"
#include "hyphen_unicode_data.h" /* Existing Unicode 17 full case-fold table. */
#include <ctype.h>
#include <miniz.h>

#define DICT_ENTRY_MAX (16u * 1024u * 1024u)
typedef struct { char *word; uint64_t offset; uint32_t size; } dict_entry;
typedef struct { char *key; size_t entry; } dict_key;
struct exr_dictionary {
  exr_dictionary_info info;
  exr_source source;
  dict_entry *entries;
  dict_key *keys, *folded, *synonyms, *synfolded;
  uint64_t *chunks;
  exr_dictionary_io io;
  char *ifo, *index, *syn;
  int dictd;
};
static uint32_t be32(const unsigned char *p) {
  return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];
}
static unsigned le16(const unsigned char *p) { return p[0]|((unsigned)p[1]<<8); }
static uint32_t le32(const unsigned char *p) { return le16(p)|((uint32_t)le16(p+2)<<16); }
static exr_status read_at(exr_source *s, uint64_t at, void *p, size_t n, exr_error *e) {
  if(at>s->size || n>s->size-at) return exr_fail(e,EXR_FORMAT,"Dictionary range outside file");
  for(size_t done=0;done<n;) {
    size_t got=s->read_at(s->context,at+done,(char *)p+done,n-done);
    if(!got || got>n-done) return exr_fail(e,EXR_IO,"Cannot read dictionary");
    done+=got;
  }
  return EXR_OK;
}
/* Read only gzip metadata. Unknown extra subfields are legal. */
static exr_status gzip_header(exr_source *s, uint64_t *data, exr_dictionary *d, exr_error *e) {
  unsigned char h[12], *extra=NULL, trailer[8];
  uint64_t at=10; exr_status status=read_at(s,0,h,10,e);
  if(status!=EXR_OK) return status;
  if(h[0]!=31 || h[1]!=139 || h[2]!=8 || (h[3]&0xe0))
    return exr_fail(e,EXR_FORMAT,"Invalid gzip header");
  if(h[3]&4) {
    status=read_at(s,10,h+10,2,e); if(status!=EXR_OK) return status;
    size_t n=le16(h+10); at=12+n; extra=malloc(n?n:1);
    if(!extra) return EXR_MEMORY;
    status=read_at(s,12,extra,n,e);
    for(size_t i=0;status==EXR_OK && i<n;) {
      if(n-i<4 || le16(extra+i+2)>n-i-4) { status=EXR_FORMAT; break; }
      size_t len=le16(extra+i+2);
      if(d && extra[i]=='R' && extra[i+1]=='A') {
        const unsigned char *ra=extra+i+4;
        if(d->chunks || len<6 || le16(ra)!=1 || !le16(ra+2) || !le16(ra+4) ||
           len!=6+2*le16(ra+4)) { status=EXR_FORMAT; break; }
        d->info.chunk_length=le16(ra+2); d->info.chunk_count=le16(ra+4);
        d->chunks=calloc((size_t)d->info.chunk_count+1,sizeof(*d->chunks));
        if(!d->chunks) { status=EXR_MEMORY; break; }
        for(unsigned j=0;j<d->info.chunk_count;j++) {
          unsigned size=le16(ra+6+2*j);
          if(!size) { status=EXR_FORMAT; break; }
          d->chunks[j+1]=d->chunks[j]+size;
        }
      }
      i+=4+len;
    }
    free(extra); if(status!=EXR_OK) return exr_fail(e,status,"Invalid dictzip extra table");
  }
  for(unsigned flag=8;flag<=16;flag<<=1) if(h[3]&flag) {
    unsigned char ch; size_t n=0;
    do {
      if(++n>65536) return exr_fail(e,EXR_LIMIT,"Gzip header string too long");
      status=read_at(s,at++,&ch,1,e); if(status!=EXR_OK) return status;
    } while(ch);
  }
  if(h[3]&2) {
    unsigned char *header=malloc((size_t)at+2);
    if(!header) return EXR_MEMORY;
    status=read_at(s,0,header,(size_t)at+2,e);
    if(status==EXR_OK && (mz_crc32(0,header,(size_t)at)&0xffff)!=le16(header+at)) status=EXR_FORMAT;
    free(header); if(status!=EXR_OK) return exr_fail(e,status,"Invalid gzip header checksum");
    at+=2;
  }
  if(s->size<8 || at>s->size-8) return exr_fail(e,EXR_FORMAT,"Truncated gzip");
  status=read_at(s,s->size-8,trailer,8,e); if(status!=EXR_OK) return status;
  if(d) {
    if(!d->chunks) return exr_fail(e,EXR_UNSUPPORTED,".dict.dz requires a dictzip RA table");
    uint64_t n=d->info.chunk_count, len=d->info.chunk_length;
    d->info.data_size=le32(trailer+4);
    if(d->chunks[n]>s->size-at-8 || d->info.data_size>(n*len) || d->info.data_size<=(n-1)*len)
      return exr_fail(e,EXR_FORMAT,"Dictzip chunk table disagrees with file size");
    for(size_t j=0;j<=n;j++) d->chunks[j]+=at;
  }
  *data=at; return EXR_OK;
}
static exr_status load_index(const char *path, size_t expected, char **out, exr_error *e) {
  unsigned char *bytes=NULL; size_t n=0;
  exr_status status=exr_read(path,&bytes,&n,e);
  if(status==EXR_OK) {
    if(n!=expected) { free(bytes); return exr_fail(e,EXR_FORMAT,"idxfilesize mismatch"); }
    *out=(char *)bytes; return EXR_OK;
  }
  if(status!=EXR_IO) return status;
  size_t len=strlen(path); char *gzip=malloc(len+4);
  if(!gzip) return EXR_MEMORY;
  memcpy(gzip,path,len);memcpy(gzip+len,".gz",4);
  exr_source source={0}; status=exr_file_source(gzip,&source,e);free(gzip);
  if(status!=EXR_OK) return status;
  uint64_t start=0;status=gzip_header(&source,&start,NULL,e);
  unsigned char *compressed=NULL,*plain=NULL;
  if(status==EXR_OK) {
    size_t amount=(size_t)(source.size-start);
    compressed=malloc(amount);plain=malloc(expected+1);
    if(!compressed || !plain) status=EXR_MEMORY;
    else if((status=read_at(&source,start,compressed,amount,e))==EXR_OK) {
      size_t got=tinfl_decompress_mem_to_mem(plain,expected,compressed,amount-8,TINFL_FLAG_USING_NON_WRAPPING_OUTPUT_BUF);
      if(got!=expected || le32(compressed+amount-4)!=expected ||
         le32(compressed+amount-8)!=mz_crc32(0,plain,expected)) status=EXR_FORMAT;
      else { plain[expected]=0;*out=(char *)plain;plain=NULL; }
    }
  }
  free(compressed);free(plain);source.release(source.context);
  return status==EXR_OK ? status : exr_fail(e,status,"Invalid compressed index");
}
static char *fold_word(const char *word) {
  exr_buffer out={0};size_t n=strlen(word),at=0;uint32_t cp;
  while(at<n) {
    if(!exr_next(word,n,&at,&cp) || !cp) { free(out.data);return NULL; }
    size_t lo=0,hi=sizeof(exr_case_folds)/sizeof(*exr_case_folds);
    while(lo<hi) {size_t mid=lo+(hi-lo)/2;if(exr_case_folds[mid].cp<cp)lo=mid+1;else hi=mid;}
    if(lo<sizeof(exr_case_folds)/sizeof(*exr_case_folds) && exr_case_folds[lo].cp==cp) {
      for(unsigned j=0;j<exr_case_folds[lo].count;j++)
        if(!exr_codepoint(&out,exr_case_folds[lo].values[j])) {free(out.data);return NULL;}
    } else if(!exr_codepoint(&out,cp)) {free(out.data);return NULL;}
  }
  if(!exr_append(&out,"",1)) {free(out.data);return NULL;} return out.data;
}
static int compare_key(const void *a,const void *b) {
  const dict_key *x=a,*y=b;int cmp=strcmp(x->key,y->key);
  return cmp ? cmp : x->entry<y->entry ? -1 : x->entry>y->entry;
}
static int decimal(const char *s,uint64_t *out) {
  uint64_t n=0;if(!*s)return 0;
  for(;*s;s++) {if(*s<'0'||*s>'9'||n>(UINT64_MAX-(unsigned)(*s-'0'))/10)return 0;n=n*10+(unsigned)(*s-'0');}
  *out=n;return 1;
}
static exr_status parse_ifo(exr_dictionary *d,exr_error *e) {
  char *line=d->ifo;unsigned required=0;d->info.idxoffsetbits=32;d->info.sametypesequence="";
  char *end=strchr(line,'\n'); if(!end)return EXR_FORMAT;
  *end=0;if(end>line && end[-1]=='\r')end[-1]=0;
  if(strcmp(line,"StarDict's dict ifo file"))return exr_fail(e,EXR_FORMAT,"Invalid StarDict magic");
  line=end+1;
  while(*line) {
    end=strchr(line,'\n');if(end)*end=0;
    size_t len=strlen(line);if(len && line[len-1]=='\r')line[len-1]=0;
    char *value=strchr(line,'=');
    if(value) {
      *value++=0;uint64_t n=0;unsigned bit=0;
      if(!strcmp(line,"bookname")) {d->info.bookname=value;bit=1;if(!*value)return EXR_FORMAT;}
      else if(!strcmp(line,"version")) {d->info.version=value;bit=2;}
      else if(!strcmp(line,"sametypesequence")) {
        if(strlen(value)>32)return EXR_LIMIT;
        for(char *p=value;*p;p++)if(!((*p>='a'&&*p<='z')||(*p>='A'&&*p<='Z')))return EXR_FORMAT;
        d->info.sametypesequence=value;bit=64;
      } else if(!strcmp(line,"wordcount") || !strcmp(line,"idxfilesize") ||
                !strcmp(line,"synwordcount") || !strcmp(line,"idxoffsetbits")) {
        if(!decimal(value,&n))return exr_fail(e,EXR_FORMAT,"Invalid StarDict number");
        if(!strcmp(line,"wordcount")) {d->info.wordcount=n;bit=4;}
        else if(!strcmp(line,"idxfilesize")) {d->info.idxfilesize=n;bit=8;}
        else if(!strcmp(line,"synwordcount")) {d->info.synwordcount=n;bit=16;}
        else {if(n!=32&&n!=64)return EXR_FORMAT;d->info.idxoffsetbits=(unsigned)n;bit=32;}
      }
      if(bit && (required&bit))return exr_fail(e,EXR_FORMAT,"Duplicate StarDict metadata");
      required|=bit;
    }
    if(!end)break;
    line=end+1;
  }
  if((required&15)!=15 || (strcmp(d->info.version,"2.4.2") && strcmp(d->info.version,"3.0.0")) ||
     (d->info.idxoffsetbits==64 && strcmp(d->info.version,"3.0.0")))
    return exr_fail(e,EXR_FORMAT,"Missing or unsupported StarDict metadata");
  if(!d->info.wordcount || d->info.wordcount>EXR_MAX_ITEMS || d->info.synwordcount>EXR_MAX_ITEMS ||
     d->info.idxfilesize>EXR_MAX_INPUT) return exr_fail(e,EXR_LIMIT,"StarDict index limit exceeded");
  return EXR_OK;
}
static exr_status build_keys(exr_dictionary *d,exr_error *e) {
  size_t n=(size_t)d->info.wordcount,s=(size_t)d->info.synwordcount;
  d->keys=calloc(n,sizeof(*d->keys));d->folded=calloc(n,sizeof(*d->folded));
  d->synfolded=calloc(s?s:1,sizeof(*d->synfolded));
  if(!d->keys || !d->folded || !d->synfolded)return EXR_MEMORY;
  for(size_t i=0;i<n;i++) {
    dict_entry *entry=&d->entries[i];
    if(entry->offset>d->info.data_size || entry->size>d->info.data_size-entry->offset)
      return exr_fail(e,EXR_FORMAT,"Entry outside dictionary data");
    if(entry->size>DICT_ENTRY_MAX)return exr_fail(e,EXR_LIMIT,"Dictionary entry too large");
    d->keys[i]=(dict_key){entry->word,i};d->folded[i]=(dict_key){fold_word(entry->word),i};
    if(!d->folded[i].key)return exr_fail(e,EXR_ENCODING,"Invalid UTF-8 dictionary word");
  }
  for(size_t i=0;i<s;i++) {
    d->synfolded[i]=(dict_key){fold_word(d->synonyms[i].key),d->synonyms[i].entry};
    if(!d->synfolded[i].key)return EXR_ENCODING;
  }
  qsort(d->keys,n,sizeof(*d->keys),compare_key);qsort(d->folded,n,sizeof(*d->folded),compare_key);
  if(s) {qsort(d->synonyms,s,sizeof(*d->synonyms),compare_key);qsort(d->synfolded,s,sizeof(*d->synfolded),compare_key);}
  return EXR_OK;
}
static exr_status parse_idx(exr_dictionary *d,exr_error *e) {
  size_t n=(size_t)d->info.wordcount,size=(size_t)d->info.idxfilesize,at=0,width=d->info.idxoffsetbits/8;
  d->entries=calloc(n,sizeof(*d->entries));if(!d->entries)return EXR_MEMORY;
  for(size_t i=0;i<n;i++) {
    const char *zero=memchr(d->index+at,0,size-at);
    if(!zero || zero==d->index+at || zero-(d->index+at)>=256) return exr_fail(e,EXR_FORMAT,"Invalid idx word");
    dict_entry *entry=&d->entries[i];entry->word=d->index+at;at=(size_t)(zero-d->index)+1;
    if(size-at<width+4)return exr_fail(e,EXR_FORMAT,"Truncated idx record");
    const unsigned char *p=(unsigned char *)d->index+at;
    entry->offset=width==8 ? ((uint64_t)be32(p)<<32)|be32(p+4) : be32(p);
    entry->size=be32(p+width);at+=width+4;
  }
  return at==size ? EXR_OK : exr_fail(e,EXR_FORMAT,"wordcount disagrees with idx");
}
static int base64_number(const char *s,uint64_t *value) {
  const char *alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  uint64_t n=0;if(!*s)return 0;
  for(;*s;s++) {const char *p=strchr(alphabet,*s);if(!p || n>(UINT64_MAX-(uint64_t)(p-alphabet))/64)return 0;n=n*64+(uint64_t)(p-alphabet);}
  *value=n;return 1;
}
static exr_status parse_dictd(exr_dictionary *d,size_t size,exr_error *e) {
  size_t count=0,capacity=0;char *line=d->index,*end;
  while((size_t)(line-d->index)<size && *line) {
    end=strchr(line,'\n');if(end)*end=0;
    size_t len=strlen(line);if(len && line[len-1]=='\r')line[len-1]=0;
    char *a=strchr(line,'\t'),*b=a ? strchr(a+1,'\t'):NULL;uint64_t offset,length;
    if(!a || !b || a==line || a-line>=256)return exr_fail(e,EXR_FORMAT,"Invalid dictd index");
    *a++=0;*b++=0;
    if(!base64_number(a,&offset) || !base64_number(b,&length) || length>DICT_ENTRY_MAX)return EXR_FORMAT;
    if(count>=EXR_MAX_ITEMS)return EXR_LIMIT;
    if(!exr_grow((void **)&d->entries,&capacity,count+1,sizeof(*d->entries)))return EXR_MEMORY;
    d->entries[count++]=(dict_entry){line,offset,(uint32_t)length};
    if(!end)break;
    line=end+1;
  }
  d->info.wordcount=count;return count ? EXR_OK : EXR_FORMAT;
}
exr_status exr_dictionary_open(const char *path,exr_dictionary **out,exr_error *e) {
  if(out)*out=NULL;
  if(!path || !out)return exr_fail(e,EXR_ARGUMENT,"Missing dictionary path/output");
  size_t len=strlen(path);const char *ext=strrchr(path,'.');
  if(len>32700 || !ext || (strcmp(ext,".ifo") && strcmp(ext,".index")))return exr_fail(e,EXR_ARGUMENT,"Expected .ifo or .index");
  exr_dictionary *d=EXR_NEW(exr_dictionary);char *name=malloc(len+16);exr_status status=EXR_MEMORY;
  if(!d || !name)goto fail;
  size_t base=(size_t)(ext-path),size=0;memcpy(name,path,base);d->dictd=!strcmp(ext,".index");
  if(d->dictd) {
    status=exr_read(path,(unsigned char **)&d->index,&size,e);if(status!=EXR_OK)goto fail;
    d->ifo=exr_copy(path,base);if(!d->ifo)goto fail;
    const char *slash=strrchr(d->ifo,'/'),*back=strrchr(d->ifo,'\\');
    if(back && (!slash || back>slash))slash=back;
    d->info.bookname=slash ? slash+1:d->ifo;d->info.version="dictd";d->info.sametypesequence="m";
    d->info.idxfilesize=size;d->info.idxoffsetbits=64;
    status=parse_dictd(d,size,e);if(status!=EXR_OK)goto fail;
  } else {
    status=exr_read(path,(unsigned char **)&d->ifo,&size,e);if(status!=EXR_OK)goto fail;
    if(size>1024*1024 || memchr(d->ifo,0,size)) {status=EXR_FORMAT;goto fail;}
    status=parse_ifo(d,e);if(status!=EXR_OK)goto fail;
    strcpy(name+base,".idx");status=load_index(name,(size_t)d->info.idxfilesize,&d->index,e);if(status!=EXR_OK)goto fail;
    status=parse_idx(d,e);if(status!=EXR_OK)goto fail;
    strcpy(name+base,".syn");
    status=exr_read(name,(unsigned char **)&d->syn,&size,e);
    if(status!=EXR_OK && (status!=EXR_IO || d->info.synwordcount))goto fail;
    if(status==EXR_OK) {
      size_t at=0,n=(size_t)d->info.synwordcount;
      d->synonyms=calloc(n?n:1,sizeof(*d->synonyms));if(!d->synonyms){status=EXR_MEMORY;goto fail;}
      for(size_t i=0;i<n;i++) {
        char *zero=memchr(d->syn+at,0,size-at);status=EXR_FORMAT;
        /* Modern Wiktionary exports also use long fragment/link aliases. */
        if(!zero || zero==d->syn+at || zero-(d->syn+at)>4096)goto fail;
        d->synonyms[i].key=d->syn+at;at=(size_t)(zero-d->syn)+1;
        if(size-at<4)goto fail;
        d->synonyms[i].entry=be32((unsigned char *)d->syn+at);at+=4;
        if(d->synonyms[i].entry>=d->info.wordcount)goto fail;
      }
      if(at!=size){status=EXR_FORMAT;goto fail;}
    }
  }
  strcpy(name+base,".dict.dz");status=exr_file_source_limit(name,INT64_MAX,&d->source,e);
  if(status==EXR_OK) {uint64_t start;status=gzip_header(&d->source,&start,d,e);}
  else if(status==EXR_IO) {
    strcpy(name+base,".dict");status=exr_file_source_limit(name,INT64_MAX,&d->source,e);d->info.data_size=d->source.size;
  }
  if(status!=EXR_OK)goto fail;
  status=build_keys(d,e);if(status!=EXR_OK)goto fail;
  free(name);*out=d;if(e)memset(e,0,sizeof(*e));return EXR_OK;
fail:
  free(name);exr_dictionary_free(d);
  if(e && e->code==status && e->message[0])return status;
  return exr_fail(e,status==EXR_OK ? EXR_MEMORY:status,"Cannot open dictionary: invalid, missing or oversized companion");
}
void exr_dictionary_free(exr_dictionary *d) {
  if(!d)return;
  if(d->source.release)d->source.release(d->source.context);
  if(d->folded)for(size_t i=0;i<d->info.wordcount;i++)free(d->folded[i].key);
  if(d->synfolded)for(size_t i=0;i<d->info.synwordcount;i++)free(d->synfolded[i].key);
  free(d->keys);free(d->folded);free(d->synonyms);free(d->synfolded);free(d->entries);
  free(d->ifo);free(d->index);free(d->syn);free(d->chunks);free(d);
}
const exr_dictionary_info *exr_dictionary_get_info(const exr_dictionary *d) {return d ? &d->info:NULL;}
exr_dictionary_io exr_dictionary_get_io(const exr_dictionary *d) {return d ? d->io:(exr_dictionary_io){0};}
static exr_status read_entry(exr_dictionary *d,const dict_entry *entry,unsigned char **out,exr_error *e) {
  *out=malloc((size_t)entry->size+1);if(!*out)return EXR_MEMORY;
  (*out)[entry->size]=0;
  if(!d->chunks)return read_at(&d->source,entry->offset,*out,entry->size,e);
  if(!entry->size)return EXR_OK;
  size_t len=d->info.chunk_length,first=(size_t)(entry->offset/len),last=(size_t)((entry->offset+entry->size-1)/len);
  unsigned char *plain=malloc(len+1),*compressed=malloc(65535+5);tinfl_decompressor *decoder=malloc(sizeof(*decoder));
  exr_status status=EXR_MEMORY;size_t written=0;
  if(!plain || !compressed || !decoder)goto done;
  for(size_t i=first;i<=last;i++) {
    size_t amount=(size_t)(d->chunks[i+1]-d->chunks[i]);
    status=read_at(&d->source,d->chunks[i],compressed,amount,e);if(status!=EXR_OK)goto done;
    d->io.compressed_bytes_read+=amount;
    /* Each dictzip chunk ends at Z_FULL_FLUSH. Supply an empty final block so
       miniz can validate the entire raw stream, including the flush boundary. */
    memcpy(compressed+amount,"\x01\x00\x00\xff\xff",5);
    size_t input=amount+5,output=len+1;tinfl_init(decoder);
    tinfl_status rc=tinfl_decompress(decoder,compressed,&input,plain,plain,&output,TINFL_FLAG_USING_NON_WRAPPING_OUTPUT_BUF);
    uint64_t remaining=d->info.data_size-i*len;
    size_t expected=remaining<len ? (size_t)remaining:len;
    if(rc!=TINFL_STATUS_DONE || output!=expected || input<amount) {status=exr_fail(e,EXR_FORMAT,"Invalid dictzip chunk");goto done;}
    d->io.blocks_inflated++;d->io.bytes_inflated+=output;
    size_t skip=i==first ? (size_t)(entry->offset%len):0,take=entry->size-written;
    if(take>output-skip)take=output-skip;
    memcpy(*out+written,plain+skip,take);written+=take;
  }
  status=EXR_OK;
done:free(plain);free(compressed);free(decoder);return status;
}
static int line_break(exr_buffer *out) {return !out->size || out->data[out->size-1]=='\n' || exr_append(out,"\n",1);}
/* Markup is flattened, never interpreted as UI or links. Paragraphs, bullets,
   indentation and phonetic text survive. Unknown entities remain literal. */
static int text_field(exr_buffer *out,const unsigned char *p,size_t n,int markup) {
  for(size_t i=0;i<n;) {
    if(markup && p[i]=='<') {
      const unsigned char *end=memchr(p+i,'>',n-i);
      if(end) {
        size_t j=i+1;if(j<n&&p[j]=='/')j++;
        char tag[32];size_t k=0;while(j<n && isalpha(p[j]) && k<31)tag[k++]=(char)tolower(p[j++]);tag[k]=0;
        if(!strcmp(tag,"br")||!strcmp(tag,"p")||!strcmp(tag,"div")||!strcmp(tag,"li")||!strcmp(tag,"def")||!strcmp(tag,"tr"))
          if(!line_break(out))return 0;
        if(!strcmp(tag,"li") && p[i+1]!='/' && !exr_append(out,"• ",4))return 0;
        i=(size_t)(end-p)+1;continue;
      }
    }
    if(markup && p[i]=='&') {
      const unsigned char *end=memchr(p+i,';',n-i<16 ? n-i:16);
      if(end) {
        size_t len=(size_t)(end-(p+i))+1;uint32_t cp=0;
        if(len==4&&!memcmp(p+i,"&lt;",4))cp='<';
        else if(len==4&&!memcmp(p+i,"&gt;",4))cp='>';
        else if(len==5&&!memcmp(p+i,"&amp;",5))cp='&';
        else if(len==6&&!memcmp(p+i,"&quot;",6))cp='"';
        else if(len==6&&!memcmp(p+i,"&apos;",6))cp='\'';
        else if(len==6&&!memcmp(p+i,"&nbsp;",6))cp=' ';
        else if(p[i+1]=='#') {
          size_t j=i+2;unsigned base=10;if(p[j]=='x'||p[j]=='X'){base=16;j++;}
          for(;p+j<end;j++) {
            unsigned digit=p[j]>='0'&&p[j]<='9' ? (unsigned)(p[j]-'0') : (unsigned)(tolower(p[j])-'a'+10);
            if(digit>=base || cp>0x10ffff/base){cp=0;break;}cp=cp*base+digit;
          }
        }
        if(cp && cp<=0x10ffff && !(cp>=0xd800 && cp<=0xdfff)) {if(!exr_codepoint(out,cp))return 0;i+=len;continue;}
      }
    }
    if(p[i]=='\r') {if(!exr_append(out,"\n",1))return 0;i++;if(i<n&&p[i]=='\n')i++;continue;}
    if(!p[i])return 0;
    if(!exr_append(out,p+i,1))return 0;
    i++;
  }
  return 1;
}
static char *speech(const char *text) {
  static const char *const labels[]={"n.","v.","vt.","vi.","adj.","adv.","prep.","pron.","conj.","interj.","noun","verb","adjective","adverb"};
  for(const char *p=text;*p;p++) if(p==text || isspace((unsigned char)p[-1]) || p[-1]=='[' || p[-1]=='(') {
    for(size_t i=0;i<sizeof(labels)/sizeof(*labels);i++) {
      size_t n=strlen(labels[i]);
      if(!strncmp(p,labels[i],n) && (!p[n] || isspace((unsigned char)p[n]) || strchr(")],:",p[n])))return exr_copy(p,n);
    }
  }
  return exr_copy("",0);
}
static exr_status definition(exr_dictionary *d,const dict_entry *entry,char **out,char **pos,exr_error *e) {
  unsigned char *bytes=NULL;exr_buffer text={0};exr_status status=read_entry(d,entry,&bytes,e);
  if(status!=EXR_OK){free(bytes);return status;}
  size_t at=0,seq=0,n=entry->size;const char *types=d->info.sametypesequence;
  while(at<n) {
    unsigned char type=d->dictd ? 'm':*types ? (unsigned char)types[seq++]:bytes[at++];
    int binary=type>='A'&&type<='Z',last=d->dictd || (*types && !types[seq]);size_t len;
    if(!binary && !(type>='a'&&type<='z')){status=EXR_FORMAT;goto done;}
    if(last)len=n-at;
    else if(binary) {if(n-at<4){status=EXR_FORMAT;goto done;}len=be32(bytes+at);at+=4;}
    else {unsigned char *zero=memchr(bytes+at,0,n-at);if(!zero){status=EXR_FORMAT;goto done;}len=(size_t)(zero-(bytes+at));}
    if(len>n-at){status=EXR_FORMAT;goto done;}
    if(!binary) {
      if(!line_break(&text) || !text_field(&text,bytes+at,len,strchr("hgxy",type)!=NULL)) {status=EXR_FORMAT;goto done;}
    }
    at+=len;if(!last && !binary)at++;
    if(last)break;
  }
  if(*types && !d->dictd && seq!=strlen(types) && !(n==0 && strlen(types)==1)){status=EXR_FORMAT;goto done;}
  while(text.size && text.data[text.size-1]=='\n')text.size--;
  if(!exr_append(&text,"",1)){status=EXR_MEMORY;goto done;}
  /* Validate before handing text to a platform UTF-8 decoder. */
  {size_t p=0;uint32_t cp;while(p+1<text.size)if(!exr_next(text.data,text.size-1,&p,&cp)){status=EXR_ENCODING;goto done;}}
  *pos=speech(text.data);if(!*pos){status=EXR_MEMORY;goto done;}
  *out=text.data;text.data=NULL;
done:free(bytes);free(text.data);return status;
}
static size_t lower_key(const dict_key *keys,size_t n,const char *query) {
  size_t lo=0,hi=n;while(lo<hi){size_t mid=lo+(hi-lo)/2;if(strcmp(keys[mid].key,query)<0)lo=mid+1;else hi=mid;}return lo;
}
void exr_dictionary_results_free(exr_dictionary_result *results,size_t count) {
  for(size_t i=0;i<count;i++){free(results[i].word);free(results[i].definition);free(results[i].part_of_speech);free(results[i].dictionary);}free(results);
}
exr_status exr_dictionary_query(exr_dictionary *const *dicts,size_t count,const char *query,size_t limit,
  exr_dictionary_result **out,size_t *out_count,exr_error *e) {
  if(out)*out=NULL;
  if(out_count)*out_count=0;
  if(!out || !out_count || !query || (!dicts&&count) || count>64 || !limit || limit>256)
    return exr_fail(e,EXR_ARGUMENT,"Invalid dictionary query arguments");
  for(size_t i=0;i<count;i++)if(!dicts[i])return EXR_ARGUMENT;
  if(strlen(query)>4096)return EXR_LIMIT;
  if(!*query || !count)return EXR_OK;
  char *fold=fold_word(query);if(!fold)return exr_fail(e,EXR_ENCODING,"Invalid query UTF-8");
  size_t used=0;exr_status status=EXR_OK;
  exr_dictionary_result *results=calloc(count*limit,sizeof(*results));if(!results){free(fold);return EXR_MEMORY;}
  for(size_t i=0;i<count;i++) {
    exr_dictionary *d=dicts[i];size_t begin=used;
    for(unsigned stage=0;stage<6 && used==begin;stage++) {
      int syn=stage==2||stage==5,prefix=stage==1||stage==4;
      const dict_key *keys=syn ? (stage==2 ? d->synonyms:d->synfolded) : stage<3 ? d->keys:d->folded;
      size_t n=(size_t)(syn ? d->info.synwordcount:d->info.wordcount);const char *q=stage<3 ? query:fold;
      for(size_t j=lower_key(keys,n,q);j<n && used-begin<limit;j++) {
        if(prefix ? strncmp(keys[j].key,q,strlen(q)) : strcmp(keys[j].key,q))break;
        size_t entry=keys[j].entry;int duplicate=0;
        for(size_t k=begin;k<used;k++)if(results[k].entry_index==entry)duplicate=1;
        if(duplicate)continue;
        exr_dictionary_result *r=&results[used++];r->dictionary_index=i;r->entry_index=entry;
        r->match=stage>=3 ? EXR_DICT_FOLDED:(exr_dictionary_match)stage;
        r->word=exr_copy(d->entries[entry].word,strlen(d->entries[entry].word));
        r->dictionary=exr_copy(d->info.bookname,strlen(d->info.bookname));
        if(!r->word || !r->dictionary){status=EXR_MEMORY;goto fail;}
        status=definition(d,&d->entries[entry],&r->definition,&r->part_of_speech,e);if(status!=EXR_OK)goto fail;
      }
    }
  }
  free(fold);if(!used){free(results);results=NULL;}*out=results;*out_count=used;return EXR_OK;
fail:free(fold);exr_dictionary_results_free(results,used);return exr_fail(e,status,"Cannot decode dictionary definition");
}
