/* SPDX-License-Identifier: MIT */
#include "reader_search.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <new>
#include <string>
#include <utility>
#include <vector>
#include <thread>

namespace {
struct failure { reader_search_status code; int sdk; const char *message; };
[[noreturn]] void reject(reader_search_status code,const char *message,int sdk=0){throw failure{code,sdk,message};}
void check_sdk(exr_status status,const char *message){
  if(status==EXR_OK)return;
  reject(status==EXR_CANCELLED?READER_SEARCH_CANCELLED:READER_SEARCH_SDK,message,(int)status);
}
reader_search_status report(reader_search_error *e,const failure &f){
  if(e){e->code=f.code;e->sdk_code=f.sdk;std::snprintf(e->message,sizeof(e->message),"%s",f.message);}
  return f.code;
}
template<class Function>reader_search_status call(reader_search_error *e,Function function){
  if(e)std::memset(e,0,sizeof(*e));
  try{function();return READER_SEARCH_OK;}
  catch(const failure &f){return report(e,f);}
  catch(...){return report(e,{READER_SEARCH_MEMORY,0,"Cannot allocate search memory"});}
}
char *copy_string(const char *text){
  if(!text)return nullptr;
  size_t n=std::strlen(text);char *out=(char *)std::malloc(n+1);
  if(!out)throw std::bad_alloc();
  std::memcpy(out,text,n+1);return out;
}
/* Strict UTF-8 (RFC 3629): no overlong forms, surrogates or values above U+10FFFF, and no NUL. */
bool well_formed(const unsigned char *s,size_t n){
  size_t i=0;
  while(i<n){
    unsigned char c=s[i];
    if(!c)return false;
    if(c<0x80){i++;continue;}
    size_t extra;unsigned lo=0x80,hi=0xbf;
    if(c>=0xc2&&c<=0xdf)extra=1;
    else if(c>=0xe0&&c<=0xef){extra=2;if(c==0xe0)lo=0xa0;if(c==0xed)hi=0x9f;}
    else if(c>=0xf0&&c<=0xf4){extra=3;if(c==0xf0)lo=0x90;if(c==0xf4)hi=0x8f;}
    else return false;
    if(i+extra>=n)return false;
    if(s[i+1]<lo||s[i+1]>hi)return false;
    for(size_t k=2;k<=extra;k++)if((s[i+k]&0xc0)!=0x80)return false;
    i+=extra+1;
  }
  return true;
}
uint64_t fnv(uint64_t h,const void *data,size_t n){
  const unsigned char *p=(const unsigned char *)data;
  for(size_t i=0;i<n;i++){h^=p[i];h*=1099511628211ull;}
  return h;
}
void add_peak(uint64_t &peak,uint64_t now){if(now>peak)peak=now;}

/* Releases hits that never reached a result. */
struct hit_list {
  std::vector<reader_search_hit> hits;
  ~hit_list(){clear();}
  void clear(){
    for(reader_search_hit &h:hits){
      std::free(h.part_path);std::free(h.page_id);std::free(h.page_label);
      exr_anchor_free(&h.anchor);exr_fixed_anchor_free(&h.fixed);
    }
    hits.clear();
  }
};
struct busy_guard {
  int &flag;
  explicit busy_guard(int &f):flag(f){flag=1;}
  ~busy_guard(){flag=0;}
};
}

struct reader_search {
  const std::thread::id owner=std::this_thread::get_id();
  reader_search_mode mode=READER_SEARCH_REFLOW;
  std::string query;
  std::vector<uint32_t> prefix; /* KMP failure table: streaming state survives block boundaries */
  uint64_t binding=0;
  exr_control control{};
  const exr_document *document=nullptr;
  exr_publication *publication=nullptr;
  exr_font *font=nullptr;
  exr_layout_config layout{};
  exr_chapter_options chapter{};
  exr_fixed_document *fixed=nullptr;
  uint64_t units=0;
  reader_search_cursor cursor{};
  int busy=0;
  reader_search_stats stats{};
  const exr_control *ctl()const{return control.cancelled||control.progress?&control:nullptr;}
  void poll()const{if(control.cancelled&&control.cancelled(control.context))reject(READER_SEARCH_CANCELLED,"Search cancelled by the caller",(int)EXR_CANCELLED);}
};

namespace {
/* Bytes are matched through one KMP automaton so a hit that straddles two 32 KiB
   blocks needs no joined buffer. After a hit the automaton restarts, which is the
   documented leftmost non-overlapping rule and equals the SDK find loops. */
struct scan_state {
  const unsigned char *query;size_t size;const uint32_t *prefix;
  size_t matched=0,at=0;           /* automaton state, absolute chapter offset of the next byte */
  size_t capacity=0;
  std::vector<std::pair<size_t,size_t>> found; /* reserved up front; sink never allocates */
  bool full=false;
  const reader_search *search=nullptr;
};
exr_status stop(exr_error *error,exr_status code,const char *message){
  if(error){error->code=code;std::snprintf(error->message,sizeof(error->message),"%s",message);}
  return code;
}
exr_status sink(void *context,const char *utf8,size_t size,exr_error *error){
  scan_state *s=(scan_state *)context;
  const reader_search *search=s->search;
  if(search->control.cancelled&&search->control.cancelled(search->control.context))
    return stop(error,EXR_CANCELLED,"Search cancelled by the caller");
  const unsigned char *bytes=(const unsigned char *)utf8;
  for(size_t i=0;i<size;i++){
    unsigned char b=bytes[i];
    while(s->matched&&b!=s->query[s->matched])s->matched=s->prefix[s->matched-1];
    if(b==s->query[s->matched])s->matched++;
    if(s->matched==s->size){
      size_t end=s->at+i+1;
      s->found.emplace_back(end-s->size,end);
      s->matched=0;
      if(s->found.size()>=s->capacity){
        s->full=true;s->at+=i+1;
        return stop(error,EXR_LIMIT,"Search batch is full");
      }
    }
  }
  s->at+=size;
  return EXR_OK;
}
void make_hit(hit_list &out,reader_search_mode mode,uint64_t unit,uint64_t start,uint64_t end){
  reader_search_hit h{};
  h.mode=mode;h.unit=unit;h.start=start;h.end=end;
  out.hits.push_back(h); /* anchors are filled in place afterwards; the entry owns nothing yet */
}

void scan_reflow(reader_search &s,size_t max_hits,reader_search_cursor &c,hit_list &out){
  size_t size=0;exr_document_text(s.document,&size);
  if(c.offset>size)reject(READER_SEARCH_ARGUMENT,"Cursor lies past the document text");
  out.hits.reserve(max_hits);
  size_t at=(size_t)c.offset;
  while(out.hits.size()<max_hits){
    s.poll();
    size_t start=SIZE_MAX,end=SIZE_MAX;exr_error e{};
    check_sdk(exr_document_find(s.document,s.query.c_str(),at,&start,&end,&e),"Public reflow find failed");
    if(start==SIZE_MAX){s.stats.bytes_scanned+=size-at;at=size;c.complete=1;break;}
    s.stats.bytes_scanned+=end-at;
    make_hit(out,READER_SEARCH_REFLOW,0,start,end);
    check_sdk(exr_anchor_create(s.document,start,end,&out.hits.back().anchor,&e),"Public reflow anchor capture failed");
    at=end;
  }
  c.offset=at;c.unit=0;
  s.stats.units_scanned+=1;
}

void scan_fixed(reader_search &s,size_t max_hits,reader_search_cursor &c,hit_list &out){
  size_t pages=0;const exr_fixed_page *list=exr_fixed_pages(s.fixed,&pages);
  if(c.unit>pages)reject(READER_SEARCH_ARGUMENT,"Cursor lies past the last page");
  out.hits.reserve(max_hits);
  while(c.unit<pages&&out.hits.size()<max_hits){
    s.poll();
    size_t page=(size_t)c.unit;exr_fixed_text *text=nullptr;exr_error e{};
    check_sdk(exr_fixed_load_text(s.fixed,page,s.ctl(),&text,&e),"Public fixed text load failed");
    struct release{exr_fixed_text *t;~release(){exr_fixed_text_free(t);}} guard{text}; /* one page text at a time */
    size_t size=0;exr_fixed_text_string(text,&size);
    if(c.offset>size)reject(READER_SEARCH_ARGUMENT,"Cursor lies past the page text");
    size_t at=(size_t)c.offset;bool missed=false;
    s.stats.units_scanned+=1;
    while(out.hits.size()<max_hits){
      s.poll();
      size_t start=SIZE_MAX,end=SIZE_MAX;
      check_sdk(exr_fixed_text_find(text,s.query.data(),s.query.size(),at,s.ctl(),&start,&end,&e),"Public fixed find failed");
      if(start==SIZE_MAX){s.stats.bytes_scanned+=size-at;missed=true;break;}
      s.stats.bytes_scanned+=end-at;
      make_hit(out,READER_SEARCH_FIXED,page,start,end);
      reader_search_hit &h=out.hits.back();
      check_sdk(exr_fixed_anchor_create(list[page].id,text,start,end,&h.fixed,&e),"Public fixed anchor capture failed");
      h.page_id=copy_string(list[page].id);h.page_label=copy_string(list[page].label);
      at=end;
    }
    if(missed){c.unit=page+1;c.offset=0;}else c.offset=at;
  }
  if(c.unit>=pages)c.complete=1;
}

struct pager_guard {exr_pager *p=nullptr;~pager_guard(){exr_pager_free(p);}};
void scan_epub(reader_search &s,size_t max_hits,reader_search_cursor &c,hit_list &out){
  size_t count=0;const exr_part *parts=exr_publication_parts(s.publication,&count);
  if(c.unit>count)reject(READER_SEARCH_ARGUMENT,"Cursor lies past the last spine item");
  out.hits.reserve(max_hits);
  while(c.unit<count&&out.hits.size()<max_hits){
    s.poll();
    size_t part=(size_t)c.unit;
    if(!parts[part].in_reading_order){c.unit=part+1;c.offset=0;continue;}
    pager_guard guard;exr_error e{};
    check_sdk(exr_publication_pager_create(s.publication,part,s.font,&s.layout,&s.chapter,&guard.p,&e),"Public bounded pager creation failed");
    exr_chapter_stats sdk=exr_pager_chapter_statistics(guard.p);
    size_t total=sdk.projection_bytes;
    add_peak(s.stats.sdk_max_projection_bytes,total);
    if(c.offset>total)reject(READER_SEARCH_ARGUMENT,"Cursor lies past the chapter text");
    s.stats.units_scanned+=1;
    scan_state scan;scan.query=(const unsigned char *)s.query.data();scan.size=s.query.size();scan.prefix=s.prefix.data();
    scan.search=&s;scan.at=(size_t)c.offset;scan.capacity=max_hits-out.hits.size();scan.found.reserve(scan.capacity);
    size_t first=scan.at;
    exr_status status=exr_pager_read_text(guard.p,first,total,sink,&scan,s.ctl(),&e);
    s.stats.bytes_scanned+=scan.at-first;
    add_peak(s.stats.sdk_peak_parse_workspace_bytes,exr_pager_chapter_statistics(guard.p).peak_parse_workspace_bytes);
    /* The sink stopped the stream because the batch is full; that is not an error. */
    if(status!=EXR_OK&&!scan.full)check_sdk(status,"Public bounded text stream failed");
    /* Only after the SDK stream has returned may the pager capture selectors. */
    for(const auto &range:scan.found){
      s.poll();
      make_hit(out,READER_SEARCH_EPUB,part,range.first,range.second);
      reader_search_hit &h=out.hits.back();
      check_sdk(exr_pager_anchor_create(guard.p,range.first,range.second,s.ctl(),&h.anchor,&e),"Public bounded anchor capture failed");
      h.part_path=copy_string(parts[part].path);
    }
    if(scan.full)c.offset=scan.found.empty()?c.offset:scan.found.back().second;
    else{c.unit=part+1;c.offset=0;}
  }
  if(c.unit>=count)c.complete=1;
}

uint64_t result_bytes(const hit_list &h){
  uint64_t n=sizeof(reader_search_hit)*h.hits.capacity();
  for(const reader_search_hit &x:h.hits){
    n+=x.anchor.exact?std::strlen(x.anchor.exact):0;n+=x.anchor.prefix?std::strlen(x.anchor.prefix):0;
    n+=x.anchor.suffix?std::strlen(x.anchor.suffix):0;n+=x.anchor.chapter?std::strlen(x.anchor.chapter):0;
    n+=x.fixed.exact_size+x.fixed.prefix_size+x.fixed.suffix_size;
    n+=x.part_path?std::strlen(x.part_path):0;n+=x.page_id?std::strlen(x.page_id):0;n+=x.page_label?std::strlen(x.page_label):0;
  }
  return n;
}

void build_prefix(reader_search &s){
  s.prefix.assign(s.query.size(),0);
  size_t j=0;
  for(size_t i=1;i<s.query.size();i++){
    while(j&&s.query[i]!=s.query[j])j=s.prefix[j-1];
    if(s.query[i]==s.query[j])j++;
    s.prefix[i]=(uint32_t)j;
  }
}
void setup(reader_search &s,reader_search_mode mode,uint64_t units,const char *query,size_t query_size,const reader_search_options *options){
  if(!query||!query_size)reject(READER_SEARCH_QUERY,"Search query is empty");
  if(query_size>READER_SEARCH_QUERY_MAX)reject(READER_SEARCH_QUERY,"Search query exceeds 4096 bytes");
  if(!well_formed((const unsigned char *)query,query_size))reject(READER_SEARCH_QUERY,"Search query is not well-formed UTF-8 without NUL");
  if(options&&options->struct_size!=sizeof(*options))reject(READER_SEARCH_ARGUMENT,"Unsupported search option size");
  s.mode=mode;s.units=units;s.query.assign(query,query_size);build_prefix(s);
  uint64_t h=1469598103934665603ull;
  uint32_t m=(uint32_t)mode;h=fnv(h,&m,sizeof(m));h=fnv(h,&units,sizeof(units));
  uint64_t n=query_size;h=fnv(h,&n,sizeof(n));h=fnv(h,query,query_size);
  s.binding=h;
  s.cursor={};s.cursor.version=2;s.cursor.mode=(uint32_t)mode;s.cursor.binding=h;
  if(options){
    s.control=options->control;
    if(options->source_key){size_t size=0;while(size<=READER_SEARCH_SOURCE_KEY_MAX&&options->source_key[size])++size;
      if(!size||size>READER_SEARCH_SOURCE_KEY_MAX||!well_formed((const unsigned char *)options->source_key,size))reject(READER_SEARCH_ARGUMENT,"Invalid verified search source key");
      std::memcpy(s.cursor.source_key,options->source_key,size+1);
    }
    if(options->resume){
      const reader_search_cursor &r=*options->resume;
      if(!s.cursor.source_key[0]||r.version!=2||r.mode!=(uint32_t)mode||r.binding!=h||r.reserved||r.complete>1||
          !std::memchr(r.source_key,0,sizeof(r.source_key))||std::strcmp(r.source_key,s.cursor.source_key))
        reject(READER_SEARCH_ARGUMENT,"Cursor belongs to another search, query or source");
      if(mode==READER_SEARCH_REFLOW?(r.unit!=0||r.offset>units||(r.complete&&r.offset!=units)):
          (r.unit>units||(r.unit==units&&r.offset)||(r.complete&&r.unit!=units)))reject(READER_SEARCH_ARGUMENT,"Cursor lies outside its verified source");
      s.cursor=r;
    }
  }
  s.stats.peak_module_bytes=sizeof(reader_search)+s.query.size()+s.prefix.size()*sizeof(uint32_t);
}
}

extern "C" reader_search_status reader_search_open_reflow(const exr_document *document,const char *query,size_t query_size,
  const reader_search_options *options,reader_search **out,reader_search_error *error){
  if(out)*out=nullptr;
  return call(error,[&]{
    if(!out||!document)reject(READER_SEARCH_ARGUMENT,"Missing search output or document");
    size_t size=0;exr_document_text(document,&size);
    std::unique_ptr<reader_search> s(new reader_search);
    setup(*s,READER_SEARCH_REFLOW,size,query,query_size,options);
    s->document=document;
    *out=s.release();
  });
}
extern "C" reader_search_status reader_search_open_epub(exr_publication *publication,exr_font *font,
  const exr_layout_config *layout,const exr_chapter_options *chapter,const char *query,size_t query_size,
  const reader_search_options *options,reader_search **out,reader_search_error *error){
  if(out)*out=nullptr;
  return call(error,[&]{
    if(!out||!publication)reject(READER_SEARCH_ARGUMENT,"Missing search output or publication");
    size_t count=0;exr_publication_parts(publication,&count);
    std::unique_ptr<reader_search> s(new reader_search);
    setup(*s,READER_SEARCH_EPUB,count,query,query_size,options);
    s->publication=publication;s->font=font;
    s->layout=layout?*layout:exr_layout_config_defaults();
    s->chapter=chapter?*chapter:exr_chapter_options_defaults();
    *out=s.release();
  });
}
extern "C" reader_search_status reader_search_open_fixed(exr_fixed_document *document,const char *query,size_t query_size,
  const reader_search_options *options,reader_search **out,reader_search_error *error){
  if(out)*out=nullptr;
  return call(error,[&]{
    if(!out||!document)reject(READER_SEARCH_ARGUMENT,"Missing search output or fixed document");
    size_t pages=0;exr_fixed_pages(document,&pages);
    std::unique_ptr<reader_search> s(new reader_search);
    setup(*s,READER_SEARCH_FIXED,pages,query,query_size,options);
    s->fixed=document;
    *out=s.release();
  });
}

extern "C" reader_search_status reader_search_next(reader_search *search,size_t max_hits,reader_search_result *result,reader_search_error *error){
  if(result)std::memset(result,0,sizeof(*result));
  if(search&&search->owner!=std::this_thread::get_id())return call(error,[&]{reject(READER_SEARCH_ARGUMENT,"Search requires its creating owner");});
  if(search&&search->busy)return call(error,[&]{reject(READER_SEARCH_BUSY,"Search handle is inside a call; reentry refused");});
  reader_search_status status=call(error,[&]{
    if(!search||!result)reject(READER_SEARCH_ARGUMENT,"Missing search handle or result");
    if(max_hits<1||max_hits>READER_SEARCH_BATCH_MAX)reject(READER_SEARCH_ARGUMENT,"A batch is 1 to 100 hits");
    busy_guard guard(search->busy);
    search->stats.calls++;
    reader_search_cursor c=search->cursor;
    hit_list out;
    if(!c.complete){
      switch(search->mode){
        case READER_SEARCH_REFLOW:scan_reflow(*search,max_hits,c,out);break;
        case READER_SEARCH_EPUB:scan_epub(*search,max_hits,c,out);break;
        case READER_SEARCH_FIXED:scan_fixed(*search,max_hits,c,out);break;
      }
    }
    add_peak(search->stats.peak_module_bytes,sizeof(reader_search)+search->query.size()+search->prefix.size()*sizeof(uint32_t)+result_bytes(out));
    reader_search_hit *array=nullptr;
    if(!out.hits.empty()){
      array=(reader_search_hit *)std::malloc(out.hits.size()*sizeof(*array));
      if(!array)throw std::bad_alloc();
      std::memcpy(array,out.hits.data(),out.hits.size()*sizeof(*array));
    }
    result->hits=array;result->count=out.hits.size();result->next=c;result->complete=c.complete?1:0;
    out.hits.clear(); /* ownership moved to the result */
    search->cursor=c;
    search->stats.hits_returned+=result->count;
  });
  if(status!=READER_SEARCH_OK&&search&&result){
    search->stats.failed_calls++;
    std::memset(result,0,sizeof(*result));
  }
  return status;
}

extern "C" void reader_search_result_free(reader_search_result *result){
  if(!result)return;
  for(size_t i=0;i<result->count;i++){
    reader_search_hit &h=result->hits[i];
    std::free(h.part_path);std::free(h.page_id);std::free(h.page_label);
    exr_anchor_free(&h.anchor);exr_fixed_anchor_free(&h.fixed);
  }
  std::free(result->hits);
  std::memset(result,0,sizeof(*result));
}

extern "C" reader_search_status reader_search_cursor_get(const reader_search *search,reader_search_cursor *cursor,reader_search_error *error){
  if(cursor)std::memset(cursor,0,sizeof(*cursor));
  return call(error,[&]{
    if(!search||!cursor)reject(READER_SEARCH_ARGUMENT,"Missing search handle or cursor");
    if(search->owner!=std::this_thread::get_id())reject(READER_SEARCH_ARGUMENT,"Search requires its creating owner");
    if(search->busy)reject(READER_SEARCH_BUSY,"Search handle is inside a call; reentry refused");
    *cursor=search->cursor;
  });
}
extern "C" reader_search_status reader_search_stats_get(const reader_search *search,reader_search_stats *stats,reader_search_error *error){
  if(stats)std::memset(stats,0,sizeof(*stats));
  return call(error,[&]{
    if(!search||!stats)reject(READER_SEARCH_ARGUMENT,"Missing search handle or statistics");
    if(search->owner!=std::this_thread::get_id())reject(READER_SEARCH_ARGUMENT,"Search requires its creating owner");
    if(search->busy)reject(READER_SEARCH_BUSY,"Search handle is inside a call; reentry refused");
    *stats=search->stats;
  });
}
extern "C" reader_search_status reader_search_close(reader_search **search,reader_search_error *error){
  return call(error,[&]{
    if(!search)reject(READER_SEARCH_ARGUMENT,"Missing search handle");
    if(!*search)return;
    if((*search)->owner!=std::this_thread::get_id())reject(READER_SEARCH_ARGUMENT,"Search requires its creating owner");
    if((*search)->busy)reject(READER_SEARCH_BUSY,"Search handle is inside a call; close refused");
    delete *search;*search=nullptr;
  });
}
