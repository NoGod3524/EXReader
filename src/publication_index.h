/* SPDX-License-Identifier: MIT */
/* Private implementation included by publication.c to share its exact folding,
   word-boundary rules and publication lifetime. All file integers are LE64.
   A block is an inverted list ordered by (token, byte offset). Scalar tokens
   support substrings; word hashes accelerate WHOLE_WORD. Hash collisions only
   add candidates: the original projection always verifies non-CJK matches. */
#ifndef EXR_PUBLICATION_INDEX_H
#define EXR_PUBLICATION_INDEX_H

enum { IX_HEADER=64, IX_PART=32, IX_BLOCK=24, IX_POST=16 };
#define IX_MAGIC UINT64_C(0x31584449525845)
#define IX_SEED UINT64_C(14695981039346656037)
typedef struct { uint64_t key, offset; } index_post;
struct publication_search_index {
  FILE *file;
  index_post *buffer;
  size_t capacity, limit, peak, text_bytes, next, bytes;
  int io_error;
};
static uint64_t ix_hash(uint64_t h,const void *data,size_t n) {
  const unsigned char *s=data;
  while(n--) {h^=*s++;h*=UINT64_C(1099511628211);}return h;
}
static void ix_put(void *out,uint64_t v) {
  unsigned char *s=out;for(size_t i=0;i<8;i++) {s[i]=(unsigned char)v;v>>=8;}
}
static uint64_t ix_get(const void *in) {
  const unsigned char *s=in;uint64_t v=0;
  for(size_t i=8;i;i--) v=(v<<8)|s[i-1];
  return v;
}
static size_t ix_memory(const publication_search_index *ix) {return sizeof(*ix)+ix->capacity*sizeof(index_post);}
static void publication_index_free(publication_search_index *ix) {
  if(ix) {if(ix->file) fclose(ix->file);free(ix->buffer);free(ix);}
}
static int ix_read(publication_search_index *ix,size_t at,void *out,size_t n) {
  if(at>ix->bytes || n>ix->bytes-at || at>INT32_MAX ||
     fseek(ix->file,(long)at,SEEK_SET) || fread(out,1,n,ix->file)!=n) {ix->io_error=1;return 0;}
  return 1;
}
static int ix_write(publication_search_index *ix,size_t at,const void *data,size_t n) {
  if(at>INT32_MAX || n>(size_t)INT32_MAX-at || fseek(ix->file,(long)at,SEEK_SET) ||
     fwrite(data,1,n,ix->file)!=n) {ix->io_error=1;return 0;}
  if(at+n>ix->bytes) ix->bytes=at+n;
  return 1;
}
static int ix_values(publication_search_index *ix,size_t at,uint64_t *values,size_t n) {
  unsigned char raw[32];
  if(n>4 || !ix_read(ix,at,raw,n*8)) return 0;
  for(size_t i=0;i<n;i++) values[i]=ix_get(raw+i*8);
  return 1;
}
static int ix_write_values(publication_search_index *ix,size_t at,const uint64_t *values,size_t n) {
  unsigned char raw[32];if(n>4) return 0;
  for(size_t i=0;i<n;i++) ix_put(raw+i*8,values[i]);
  return ix_write(ix,at,raw,n*8);
}
static exr_status ix_resize(publication_search_index *ix,exr_error *e) {
  size_t budget=ix->limit ? ix->limit:ix->text_bytes/10*3+(ix->text_bytes%10)*3/10;
  if(!ix->limit && budget<512) budget=512;
  if(budget<512) return exr_fail(e,EXR_LIMIT,"Index memory budget is below 512 bytes");
  size_t cap=(budget-sizeof(*ix))/sizeof(index_post);
  if(cap>4096) cap=4096;
  if(cap!=ix->capacity) {
    free(ix->buffer);ix->buffer=NULL;ix->capacity=0;
    ix->buffer=malloc(cap*sizeof(index_post));
    if(!ix->buffer) return exr_fail(e,EXR_MEMORY,"Index workspace allocation failed");
    ix->capacity=cap;
  }
  if(ix_memory(ix)>ix->peak) ix->peak=ix_memory(ix);
  return EXR_OK;
}
static exr_status ix_create(exr_publication *p,size_t limit,publication_search_index **out,exr_error *e) {
  unsigned char zero[IX_HEADER]={0};publication_search_index *ix=calloc(1,sizeof(*ix));
  *out=NULL;if(!ix) return exr_fail(e,EXR_MEMORY,"Index allocation failed");
  ix->limit=limit;
  exr_status status=ix_resize(ix,e);
  if(status!=EXR_OK) {publication_index_free(ix);return status;}
  ix->file=tmpfile();
  if(!ix->file) {publication_index_free(ix);return exr_fail(e,EXR_IO,"Cannot create index spool");}
  setvbuf(ix->file,NULL,_IONBF,0);
  ix_write(ix,0,zero,sizeof(zero));
  for(size_t i=0;i<p->count;i++) ix_write(ix,IX_HEADER+i*IX_PART,zero,IX_PART);
  if(ix->io_error) {publication_index_free(ix);return exr_fail(e,EXR_IO,"Cannot initialize index spool");}
  *out=ix;return EXR_OK;
}
static uint32_t ix_accent(uint32_t cp) {
  /* Same explicit Latin-1 scope as legacy case folding, plus combining marks.
     No locale, stemming or Unicode expansion can change literal semantics. */
  uint32_t lower=search_fold(cp,0),base=0;
  if(lower>=0xe0 && lower<=0xe5) base='a';
  else if(lower==0xe7) base='c';
  else if(lower>=0xe8 && lower<=0xeb) base='e';
  else if(lower>=0xec && lower<=0xef) base='i';
  else if(lower==0xf1) base='n';
  else if(lower>=0xf2 && lower<=0xf6) base='o';
  else if(lower>=0xf9 && lower<=0xfc) base='u';
  else if(lower==0xfd || lower==0xff) base='y';
  if(base) return cp!=lower ? base-32:base;
  return cp;
}
static int ix_mark(uint32_t cp) {return cp>=0x300 && cp<=0x36f;}
static uint32_t ix_key(uint32_t cp) {return search_fold(ix_accent(cp),0);}
static uint64_t ix_word_hash(const char *s,size_t n) {
  uint64_t h=IX_SEED;size_t at=0;uint32_t cp;
  while(at<n && exr_next(s,n,&at,&cp)) {
    unsigned char bytes[8];if(ix_mark(cp)) continue;
    ix_put(bytes,ix_key(cp));h=ix_hash(h,bytes,8);
  }
  return h|UINT64_C(0x8000000000000000);
}
static int ix_compare(const void *a,const void *b) {
  const index_post *x=a,*y=b;
  if(x->key!=y->key) return x->key<y->key ? -1:1;
  return x->offset<y->offset ? -1:x->offset>y->offset;
}
static int ix_flush(publication_search_index *ix,size_t n,size_t lo,size_t hi) {
  if(!n) return 1;
  qsort(ix->buffer,n,sizeof(index_post),ix_compare);
  for(size_t i=0;i<n;i++) {
    uint64_t key=ix->buffer[i].key,offset=ix->buffer[i].offset;
    ix_put((unsigned char *)ix->buffer+i*IX_POST,key);
    ix_put((unsigned char *)ix->buffer+i*IX_POST+8,offset);
  }
  uint64_t header[]={lo,hi,n};
  return ix_write_values(ix,ix->bytes,header,3) && ix_write(ix,ix->bytes,ix->buffer,n*IX_POST);
}
static exr_status ix_part(exr_publication *p,publication_search_index *ix,const exr_control *control,exr_error *e) {
  exr_document *doc=NULL;size_t part=ix->next,original=ix->bytes,old_text=ix->text_bytes;
  size_t n=0,at=0,used=0,lo=0,hi=0,word_end=0,next_poll=0;uint32_t cp;
  exr_status status=exr_control_cancel(control,e);if(status!=EXR_OK) return status;
  if(!p->parts[part].in_reading_order) {ix->next++;return EXR_OK;}
  const char *s;
  if(p->search && p->search[part].text) {s=p->search[part].text;n=p->search[part].size;}
  else {
    status=exr_publication_load(p,part,&doc,e);if(status!=EXR_OK) return status;
    s=exr_document_text(doc,&n);
  }
  if(n>EXR_MAX_TEXT || n>SIZE_MAX-ix->text_bytes) {status=exr_fail(e,EXR_LIMIT,"Index text exceeds limit");goto done;}
  ix->text_bytes+=n;status=ix_resize(ix,e);if(status!=EXR_OK) goto done;
  uint64_t entry[]={ix->bytes,n,ix->bytes+n,0};
  if(!ix_write(ix,ix->bytes,s,n)) {status=EXR_IO;goto done;}
  while(at<n) {
    size_t start=at;
    if(at>=next_poll) {status=exr_control_cancel(control,e);if(status!=EXR_OK) goto done;next_poll=at+4096;}
    if(!exr_next(s,n,&at,&cp)) {status=exr_fail(e,EXR_ENCODING,"Index text is not UTF-8");goto done;}
    /* Keep a scalar and its optional word token in the same block. */
    if(used+2>ix->capacity) {
      if(!ix_flush(ix,used,lo,hi)) {status=EXR_IO;goto done;}used=0;
    }
    if(!used) lo=start;
    hi=start;ix->buffer[used++]=(index_post){ix_key(cp),start};
    if(start>=word_end && search_word(cp)) {
      size_t end=at;
      while(end<n) {
        size_t next=end;uint32_t c;
        if(end>=next_poll) {status=exr_control_cancel(control,e);if(status!=EXR_OK) goto done;next_poll=end+4096;}
        if(!exr_next(s,n,&next,&c) || !search_word(c)) break;
        end=next;
      }
      word_end=end;ix->buffer[used++]=(index_post){ix_word_hash(s+start,end-start),start};
    }
  }
  if(!ix_flush(ix,used,lo,hi)) {status=EXR_IO;goto done;}
  entry[3]=ix->bytes;
  if(!ix_write_values(ix,IX_HEADER+part*IX_PART,entry,4)) {status=EXR_IO;goto done;}
  ix->next++;
done:
  exr_document_free(doc);
  if(status!=EXR_OK) {
    ix->bytes=original;ix->text_bytes=old_text;
    /* A cancelled part must not retain a workspace sized for uncommitted text. */
    ix_resize(ix,NULL);
  }
  if(status==EXR_IO) return exr_fail(e,EXR_IO,"Index spool write failed (2 GiB file limit)");
  return status;
}
static void ix_stats(const exr_publication *p,exr_index_stats *out) {
  if(!out) return;
  memset(out,0,sizeof(*out));out->total_parts=p->count;
  if(p->index) {
    publication_search_index *ix=p->index;out->text_bytes=ix->text_bytes;out->memory_bytes=ix_memory(ix);
    out->peak_memory_bytes=ix->peak;out->disk_bytes=ix->bytes;out->indexed_parts=ix->next;
    out->complete=ix->next==p->count;
  }
}
exr_status exr_publication_index_info(exr_publication *p,exr_index_stats *out,exr_error *e) {
  if(out) memset(out,0,sizeof(*out));
  if(!p || !out || p->busy || p->searching) return exr_fail(e,EXR_ARGUMENT,"Invalid index info arguments");
  ix_stats(p,out);return exr_fail(e,EXR_OK,"");
}
exr_status exr_publication_index_build(exr_publication *p,size_t limit,size_t max_parts,
  const exr_control *control,exr_index_stats *stats,exr_error *e) {
  exr_status status;if(stats) memset(stats,0,sizeof(*stats));
  if(!p || p->busy || p->searching) return exr_fail(e,EXR_ARGUMENT,"Invalid index build arguments");
  if(limit && limit<512) return exr_fail(e,EXR_LIMIT,"Index memory budget is below 512 bytes");
  status=exr_control_cancel(control,e);if(status!=EXR_OK) return status;
  if(!p->index) {status=ix_create(p,limit,&p->index,e);if(status!=EXR_OK) return status;}
  p->index->limit=limit;p->index->io_error=0;status=ix_resize(p->index,e);p->searching=1;
  size_t done=0;
  while(status==EXR_OK && p->index->next<p->count && (!max_parts || done<max_parts)) {
    status=ix_part(p,p->index,control,e);done++;
  }
  p->searching=0;ix_stats(p,stats);
  return status==EXR_OK ? exr_fail(e,EXR_OK,""):status;
}
/* Loaded blocks use the one bounded workspace. A smaller replacement budget
   can still search old, larger blocks through binary disk reads. */
static index_post ix_post(publication_search_index *ix,size_t block,size_t i,int cached) {
  unsigned char bytes[IX_POST];const unsigned char *s=bytes;
  if(cached) s=(const unsigned char *)ix->buffer+i*IX_POST;
  else if(!ix_read(ix,block+IX_BLOCK+i*IX_POST,bytes,IX_POST)) return (index_post){0,0};
  return (index_post){ix_get(s),ix_get(s+8)};
}
static size_t ix_lower(publication_search_index *ix,size_t block,size_t n,uint64_t key,size_t offset,int cached) {
  size_t lo=0,hi=n;
  while(lo<hi) {
    size_t mid=lo+(hi-lo)/2;index_post v=ix_post(ix,block,mid,cached);
    if(v.key<key || (v.key==key && v.offset<offset)) lo=mid+1;else hi=mid;
  }
  return lo;
}
static uint32_t ix_cp(publication_search_index *ix,size_t base,size_t n,size_t *at) {
  unsigned char raw[4];uint32_t cp=0;size_t count=n-*at,pos=0;if(count>4) count=4;
  if(!count || !ix_read(ix,base+*at,raw,count)) return 0;
  if(!exr_next((const char *)raw,count,&pos,&cp)) {ix->io_error=1;return 0;}
  *at+=pos;return cp;
}
static uint32_t ix_before(publication_search_index *ix,size_t base,size_t n,size_t at) {
  unsigned char byte;
  if(!at) return 0;
  do {at--;if(!ix_read(ix,base+at,&byte,1)) return 0;} while(at && (byte&0xc0)==0x80);
  return ix_cp(ix,base,n,&at);
}
static int ix_match(publication_search_index *ix,const uint64_t entry[4],size_t start,const char *q,size_t bytes,
                    unsigned flags,size_t *length) {
  size_t at=start,qa=0;uint32_t first=0,last=0;
  while(qa<bytes) {
    uint32_t want=0,cp=0;exr_next(q,bytes,&qa,&want);
    if((flags&EXR_INDEX_IGNORE_DIACRITICS) && ix_mark(want)) continue;
    if(flags&EXR_INDEX_IGNORE_DIACRITICS) want=ix_accent(want);
    want=search_fold(want,flags);
    do {if(at>=entry[1]) return 0;cp=ix_cp(ix,(size_t)entry[0],(size_t)entry[1],&at);}
    while((flags&EXR_INDEX_IGNORE_DIACRITICS) && ix_mark(cp) && !ix->io_error);
    if(!first) first=cp;
    last=cp;
    if(flags&EXR_INDEX_IGNORE_DIACRITICS) cp=ix_accent(cp);
    if(ix->io_error || search_fold(cp,flags)!=want) return 0;
  }
  if(flags&EXR_INDEX_IGNORE_DIACRITICS) {
    while(at<entry[1]) {size_t next=at;uint32_t cp=ix_cp(ix,(size_t)entry[0],(size_t)entry[1],&next);if(!ix_mark(cp)) break;at=next;}
  }
  if(flags&EXR_SEARCH_WHOLE_WORD) {
    size_t next=at;uint32_t before=ix_before(ix,(size_t)entry[0],(size_t)entry[1],start);
    uint32_t after=at<entry[1] ? ix_cp(ix,(size_t)entry[0],(size_t)entry[1],&next):0;
    if((search_word(before) && search_word(first)) || (search_word(last) && search_word(after))) return 0;
  }
  *length=at-start;return !ix->io_error;
}
exr_status exr_publication_index_search(exr_publication *p,const char *q,unsigned flags,exr_index_cursor *cursor,
  size_t max_results,exr_search_fn callback,void *context,const exr_control *control,size_t *count,exr_error *e) {
  size_t bytes=0,qa=0,first_at=0,hits=0;uint32_t first=0,cp;int cjk=1,word=1;
  exr_status status=EXR_OK;exr_index_cursor next={0};
  if(count) *count=0;
  if(!p || p->busy || p->searching || !q || !count || !cursor ||
     cursor->next.part>p->count || (flags&~7u)) return exr_fail(e,EXR_ARGUMENT,"Invalid indexed search arguments");
  while(bytes<=1024*1024 && q[bytes]) bytes++;
  if(!bytes) return exr_fail(e,EXR_ARGUMENT,"Empty search needle");
  if(bytes>1024*1024) return exr_fail(e,EXR_LIMIT,"Search needle exceeds 1 MiB");
  while(qa<bytes) {
    size_t start=qa;if(!exr_next(q,bytes,&qa,&cp)) return exr_fail(e,EXR_ENCODING,"Search needle is not UTF-8");
    if(!exr_projection_cjk(cp)) cjk=0;
    if(!search_word(cp)) word=0;
    if((flags&EXR_INDEX_IGNORE_DIACRITICS) && ix_mark(cp)) continue;
    if(!first) {first=cp;first_at=start;}
  }
  if(!first) return exr_fail(e,EXR_ARGUMENT,"Search needle contains only ignored marks");
  if(cursor->done) return exr_fail(e,EXR_OK,"");
  status=exr_control_cancel(control,e);if(status!=EXR_OK) return status;
  if(!p->index) {status=ix_create(p,0,&p->index,e);if(status!=EXR_OK) return status;}
  publication_search_index *ix=p->index;ix->io_error=0;next=*cursor;p->searching=1;
  uint64_t key=(word && (flags&EXR_SEARCH_WHOLE_WORD)) ? ix_word_hash(q,bytes):ix_key(first);
  for(size_t part=next.next.part;part<p->count;part++) {
    status=exr_control_cancel(control,e);if(status!=EXR_OK) goto done;
    while(ix->next<=part) {status=ix_part(p,ix,control,e);if(status!=EXR_OK) goto done;}
    if(!p->parts[part].in_reading_order) continue;
    uint64_t entry[4];if(!ix_values(ix,IX_HEADER+part*IX_PART,entry,4)) goto io_failed;
    size_t from=part==cursor->next.part ? cursor->next.offset:0;
    if(from>entry[1]) {status=exr_fail(e,EXR_ARGUMENT,"Search offset exceeds part text");goto done;}
    for(size_t block=(size_t)entry[2];block<entry[3];) {
      uint64_t h[3];if(!ix_values(ix,block,h,3)) goto io_failed;
      size_t n=(size_t)h[2];int cached=n<=ix->capacity;
      status=exr_control_cancel(control,e);if(status!=EXR_OK) goto done;
      if(h[1]<from) {block+=IX_BLOCK+n*IX_POST;continue;}
      if(cached && !ix_read(ix,block+IX_BLOCK,ix->buffer,n*IX_POST)) goto io_failed;
      size_t i=ix_lower(ix,block,n,key,from,cached);
      for(;i<n;i++) {
        index_post v=ix_post(ix,block,i,cached);size_t length=0;
        if(v.key!=key) break;
        if((hits&63)==0) {status=exr_control_cancel(control,e);if(status!=EXR_OK) goto done;}
        if(cjk) {
          /* Positional intersection, including repeated scalars. At a block
             boundary verify against the stored text instead of losing a hit. */
          int match=1;size_t a=0;
          while(a<bytes) {
            size_t shift=a;exr_next(q,bytes,&a,&cp);
            if(v.offset+shift>h[1]) {match=ix_match(ix,entry,(size_t)v.offset,q,bytes,flags,&length);break;}
            size_t j=ix_lower(ix,block,n,ix_key(cp),(size_t)v.offset+shift,cached);
            index_post other=j<n ? ix_post(ix,block,j,cached):(index_post){0,0};
            if(other.key!=ix_key(cp) || other.offset!=v.offset+shift) {match=0;break;}
          }
          if(!match) continue;
          if(!length) length=bytes;
        } else if(!ix_match(ix,entry,(size_t)v.offset,q+first_at,bytes-first_at,flags,&length)) continue;
        exr_search_result result={1,part,(size_t)v.offset,length};hits++;
        /* Any byte inside the delivered first scalar rounds forward on resume. */
        next.next=(exr_text_position){part,(size_t)v.offset+1};next.done=0;
        if(callback) {
          p->busy=1;int more=callback(context,&result);p->busy=0;
          if(!more) goto done;
        }
        if(max_results && hits>=max_results) goto done;
      }
      if(ix->io_error) goto io_failed;
      block+=IX_BLOCK+n*IX_POST;
    }
    next.next=(exr_text_position){part+1,0};
  }
  next.done=1;goto done;
io_failed:
  status=exr_fail(e,EXR_IO,"Cannot read index spool");
done:
  p->searching=0;
  if(ix->io_error && status==EXR_OK) status=exr_fail(e,EXR_IO,"Cannot read index spool");
  if(status==EXR_OK) {*count=hits;*cursor=next;return exr_fail(e,EXR_OK,"");}
  return status;
}
static uint64_t ix_directory(const exr_publication *p) {
  uint64_t h=IX_SEED;unsigned char bytes[8];ix_put(bytes,p->count);h=ix_hash(h,bytes,8);
  for(size_t i=0;i<p->count;i++) {
    const exr_part *part=&p->parts[i];
    h=ix_hash(h,part->id,strlen(part->id)+1);h=ix_hash(h,part->path,strlen(part->path)+1);
    ix_put(bytes,part->in_reading_order!=0);h=ix_hash(h,bytes,8);
  }
  return h;
}
exr_status exr_publication_index_save(exr_publication *p,const char *path,const char *revision,
  const exr_control *control,exr_error *e) {
  if(!p || !p->index || p->busy || p->searching || !path || !revision || !*revision)
    return exr_fail(e,EXR_ARGUMENT,"Invalid index save arguments");
  publication_search_index *ix=p->index;exr_status status=exr_control_cancel(control,e);
  if(status!=EXR_OK) return status;
  if(!ix->capacity) return exr_fail(e,EXR_MEMORY,"Index workspace unavailable; retry build before saving");
  /* Stage before opening the destination: it can be the loaded cache itself. */
  FILE *out=tmpfile();if(!out) return exr_fail(e,EXR_IO,"Cannot stage saved index");
  setvbuf(out,NULL,_IONBF,0);p->searching=1;ix->io_error=0;
  unsigned char header[IX_HEADER]={0};uint64_t hash=IX_SEED;
  if(fwrite(header,1,sizeof(header),out)!=sizeof(header)) status=EXR_IO;
  for(size_t at=IX_HEADER;status==EXR_OK && at<ix->bytes;) {
    size_t n=ix->bytes-at;if(n>ix->capacity*IX_POST) n=ix->capacity*IX_POST;
    status=exr_control_cancel(control,e);if(status!=EXR_OK) break;
    if(!ix_read(ix,at,ix->buffer,n) || fwrite(ix->buffer,1,n,out)!=n) {status=EXR_IO;break;}
    hash=ix_hash(hash,ix->buffer,n);at+=n;
  }
  uint64_t values[]={IX_MAGIC,ix_hash(IX_SEED,revision,strlen(revision)),ix_directory(p),p->count,
    ix->next,ix->text_bytes,ix->bytes,hash};
  for(size_t i=0;i<8;i++) ix_put(header+i*8,values[i]);
  if(status==EXR_OK && (fseek(out,0,SEEK_SET) || fwrite(header,1,sizeof(header),out)!=sizeof(header))) status=EXR_IO;
  if(status==EXR_OK) {
    fclose(ix->file);ix->file=out;out=NULL;
    FILE *destination=exr_fopen(path,"wb");
    if(!destination) status=EXR_IO;
    else {
      setvbuf(destination,NULL,_IONBF,0);
      if(fseek(ix->file,0,SEEK_SET)) status=EXR_IO;
      for(size_t at=0;status==EXR_OK && at<ix->bytes;) {
        size_t n=ix->bytes-at;if(n>ix->capacity*IX_POST) n=ix->capacity*IX_POST;
        status=exr_control_cancel(control,e);if(status!=EXR_OK) break;
        if(fread(ix->buffer,1,n,ix->file)!=n || fwrite(ix->buffer,1,n,destination)!=n) {status=EXR_IO;break;}
        at+=n;
      }
      if(fclose(destination) && status==EXR_OK) status=EXR_IO;
    }
  }
  if(out && fclose(out) && status==EXR_OK) status=EXR_IO;
  p->searching=0;
  return status==EXR_IO ? exr_fail(e,EXR_IO,"Cannot save index"):status==EXR_OK ? exr_fail(e,EXR_OK,""):status;
}
/* Validate structure as well as checksum: persisted offsets are untrusted. */
static int ix_validate(exr_publication *p,publication_search_index *ix,const exr_control *control,exr_error *e) {
  size_t end=IX_HEADER+p->count*IX_PART,total=0;
  for(size_t part=0;part<p->count;part++) {
    uint64_t v[4];if(exr_control_cancel(control,e)!=EXR_OK) return 0;
    if(!ix_values(ix,IX_HEADER+part*IX_PART,v,4)) return 0;
    if(part>=ix->next || !p->parts[part].in_reading_order) {if(v[0] || v[1] || v[2] || v[3]) return 0;continue;}
    if(v[0]!=end || v[1]>EXR_MAX_TEXT || v[2]!=v[0]+v[1] || v[3]<v[2] || v[3]>ix->bytes) return 0;
    total+=(size_t)v[1];size_t block=(size_t)v[2],previous=0;int have_block=0;
    while(block<v[3]) {
      uint64_t h[3];if(v[3]-block<IX_BLOCK || !ix_values(ix,block,h,3)) return 0;
      if(!h[2] || h[2]>4096 || h[0]>h[1] || h[1]>=v[1] || (have_block && h[0]<=previous) ||
         h[2]>(v[3]-block-IX_BLOCK)/IX_POST) return 0;
      int cached=h[2]<=ix->capacity;
      if(cached && !ix_read(ix,block+IX_BLOCK,ix->buffer,(size_t)h[2]*IX_POST)) return 0;
      index_post before={0,0};
      for(size_t i=0;i<h[2];i++) {
        index_post a=ix_post(ix,block,i,cached);
        if(!a.key || a.offset<h[0] || a.offset>h[1] || (i && ix_compare(&before,&a)>=0)) return 0;
        before=a;
      }
      previous=(size_t)h[1];have_block=1;block+=IX_BLOCK+(size_t)h[2]*IX_POST;
    }
    if(block!=v[3] || (v[1] && !have_block)) return 0;
    end=(size_t)v[3];
  }
  return !ix->io_error && end==ix->bytes && total==ix->text_bytes;
}
exr_status exr_publication_index_load(exr_publication *p,const char *path,const char *revision,size_t limit,
  const exr_control *control,exr_index_stats *stats,exr_error *e) {
  if(stats) memset(stats,0,sizeof(*stats));
  if(!p || p->busy || p->searching || !path || !revision || !*revision)
    return exr_fail(e,EXR_ARGUMENT,"Invalid index load arguments");
  if(limit && limit<512) return exr_fail(e,EXR_LIMIT,"Index memory budget is below 512 bytes");
  exr_status status=exr_control_cancel(control,e);if(status!=EXR_OK) return status;
  FILE *file=exr_fopen(path,"rb");if(!file) return exr_fail(e,EXR_IO,"Cannot open saved index");
  setvbuf(file,NULL,_IONBF,0);publication_search_index *ix=NULL;unsigned char header[IX_HEADER];uint64_t h[8];
  if(fread(header,1,sizeof(header),file)!=sizeof(header)) {status=EXR_FORMAT;goto done;}
  for(size_t i=0;i<8;i++) h[i]=ix_get(header+i*8);
  if(h[0]!=IX_MAGIC || h[1]!=ix_hash(IX_SEED,revision,strlen(revision)) || h[2]!=ix_directory(p) ||
     h[3]!=p->count || h[4]>p->count || h[5]>SIZE_MAX || h[6]<IX_HEADER+p->count*IX_PART || h[6]>INT32_MAX) {
    status=EXR_FORMAT;goto done;
  }
  ix=calloc(1,sizeof(*ix));if(!ix) {status=EXR_MEMORY;goto done;}
  ix->file=file;file=NULL;ix->limit=limit;ix->next=(size_t)h[4];ix->text_bytes=(size_t)h[5];ix->bytes=(size_t)h[6];
  status=ix_resize(ix,e);if(status!=EXR_OK) goto done;
  uint64_t hash=IX_SEED;p->searching=1;
  for(size_t at=IX_HEADER;at<ix->bytes;) {
    size_t n=ix->bytes-at;if(n>ix->capacity*IX_POST) n=ix->capacity*IX_POST;
    status=exr_control_cancel(control,e);if(status!=EXR_OK) goto done;
    if(!ix_read(ix,at,ix->buffer,n)) {status=EXR_FORMAT;goto done;}
    hash=ix_hash(hash,ix->buffer,n);at+=n;
  }
  if(fgetc(ix->file)!=EOF || hash!=h[7] || !ix_validate(p,ix,control,e)) {
    status=exr_control_cancel(control,e);if(status==EXR_OK) status=EXR_FORMAT;goto done;
  }
  if(ix->next<p->count) {
    /* Partial cache must become writable; complete caches remain read-only. */
    FILE *copy=tmpfile();if(!copy) {status=EXR_IO;goto done;}setvbuf(copy,NULL,_IONBF,0);
    for(size_t at=0;at<ix->bytes;) {
      size_t n=ix->bytes-at;if(n>ix->capacity*IX_POST) n=ix->capacity*IX_POST;
      status=exr_control_cancel(control,e);
      if(status!=EXR_OK || !ix_read(ix,at,ix->buffer,n) || fwrite(ix->buffer,1,n,copy)!=n) {
        if(status==EXR_OK) status=EXR_IO;
        break;
      }
      at+=n;
    }
    if(status!=EXR_OK) {fclose(copy);goto done;}
    fclose(ix->file);ix->file=copy;
  }
  publication_index_free(p->index);p->index=ix;ix=NULL;ix_stats(p,stats);
done:
  p->searching=0;if(file) fclose(file);publication_index_free(ix);
  if(status==EXR_FORMAT) return exr_fail(e,EXR_FORMAT,"Stale, corrupt or incompatible index");
  if(status==EXR_MEMORY) return exr_fail(e,EXR_MEMORY,"Index allocation failed");
  if(status==EXR_IO) return exr_fail(e,EXR_IO,"Cannot copy partial index");
  return status==EXR_OK ? exr_fail(e,EXR_OK,""):status;
}
#endif
