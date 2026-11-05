/* SPDX-License-Identifier: MIT */
#include "reader_jump_history.h"
#include <atomic>
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <new>
#include <memory>
#include <string>
#include <thread>
#include <utility>
#include <vector>

namespace {
struct failure { reader_jh_status code; reader_rs_status rs; reader_rs_gap gap; int revision; const char *message; };
[[noreturn]] void reject(reader_jh_status code,const char *message,reader_rs_status rs=READER_RS_OK,reader_rs_gap gap=READER_RS_GAP_NONE,int revision=0){
  throw failure{code,rs,gap,revision,message};
}
/* Entry tickets remain unique across live histories and close/reopen cycles.
   A peek from another history must never complete this history's neighbor. */
std::atomic<uint64_t> next_entry_id{1};
uint64_t entry_id(){
  uint64_t id=next_entry_id.load(std::memory_order_relaxed);
  for(;;){
    if(id==UINT64_MAX)reject(READER_JH_LIMIT,"History entry identifiers are exhausted");
    if(next_entry_id.compare_exchange_weak(id,id+1,std::memory_order_relaxed))return id;
  }
}
reader_jh_status report(reader_jh_error *e,const failure &f){
  if(e){e->code=f.code;e->rs_code=f.rs;e->gap=f.gap;e->revision_code=f.revision;std::snprintf(e->message,sizeof(e->message),"%s",f.message);}
  return f.code;
}
struct entry {
  uint64_t id; reader_jh_kind kind; std::string book, key, wire;
  size_t bytes() const { return book.size()+key.size()+wire.size(); }
};
}

struct reader_jh {
  std::thread::id owner;
  uint32_t max_entries=READER_JH_DEFAULT_ENTRIES, max_bytes=READER_JH_DEFAULT_BYTES;
  std::vector<entry> list;
  size_t cursor=0, bytes=0;   /* cursor is meaningful only while list is not empty */
  uint64_t generation=0, evicted_total=0, truncated_total=0;
};

namespace {
/* Every state change happens after the last operation that can throw, so an
   error return always leaves the history exactly as it was. */
template<class Function>reader_jh_status guarded(reader_jh *h,reader_jh_error *e,Function function){
  if(e)std::memset(e,0,sizeof(*e));
  try{
    if(!h)reject(READER_JH_ARGUMENT,"Missing history handle");
    if(std::this_thread::get_id()!=h->owner)reject(READER_JH_THREAD,"History used on a thread that does not own it");
    function();return READER_JH_OK;
  }
  catch(const failure &f){return report(e,f);}
  catch(...){return report(e,{READER_JH_MEMORY,READER_RS_OK,READER_RS_GAP_NONE,0,"Cannot allocate jump-history memory"});}
}
void part_of(std::string &k,const char *text,size_t size){k+=std::to_string(size);k+=':';if(size)k.append(text,size);k+='|';}
void number_of(std::string &k,unsigned long long v){k+=std::to_string(v);k+='|';}
/* Identity of a place, never of a revision: the transient revision ID, the
   parser version and the anchor version are excluded so two captures of one
   place compare equal. The EPUB spine index and the fixed page ID are included,
   so a repeated spine path stays an unambiguous place. An anchor v3 wire is the
   explicit byte form of the same selector, so it also records selector presence:
   identical offsets with a NULL context and with an allocated empty context are
   two different stored wires and never collapse into one entry. */
std::string location_key(const reader_rs_record &r){
  std::string k;number_of(k,(unsigned)r.mode);
  part_of(k,r.book_key,std::strlen(r.book_key));
  part_of(k,r.part_path,r.part_path?std::strlen(r.part_path):0);
  number_of(k,r.part);
  part_of(k,r.page_id,r.page_id?std::strlen(r.page_id):0);
  number_of(k,r.page);number_of(k,r.start);number_of(k,r.end);
  /* Anchor v3 keeps the selector as explicit bytes: presence and length are part
     of the identity, so a NULL context never becomes an allocated empty one and
     an embedded NUL never ends a selector. v1/v2 keep the identical key. */
  if(r.anchor_version==3){number_of(k,r.exact?1:0);number_of(k,r.prefix?1:0);number_of(k,r.suffix?1:0);}
  part_of(k,r.exact,r.exact_size);part_of(k,r.prefix,r.prefix_size);part_of(k,r.suffix,r.suffix_size);
  number_of(k,r.chapter?1:0);part_of(k,r.chapter,r.chapter?std::strlen(r.chapter):0);
  return k;
}
struct record_guard { reader_rs_record record{}; ~record_guard(){reader_rs_record_free(&record);} };
reader_jh_result make_result(const reader_jh *h,reader_jh_outcome outcome,size_t evicted,size_t truncated){
  reader_jh_result r{};r.outcome=outcome;r.entry_id=h->list[h->cursor].id;r.evicted=evicted;r.truncated=truncated;r.generation=h->generation;return r;
}
void commit_wire(reader_jh *h,reader_revisions *store,reader_jh_kind kind,std::string wire,reader_jh_result *result,bool raw){
  if(!store||!result||kind<READER_JH_PAGE||kind>READER_JH_TOC||wire.empty())reject(READER_JH_ARGUMENT,"Missing revision store, kind, wire or result");
  record_guard g;reader_rs_error re{};
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
  reader_rs_status rs=raw?reader_rs_decode_raw_v3(store,wire.data(),wire.size(),&g.record,&re)
                        :reader_rs_decode(store,wire.data(),wire.size(),&g.record,&re);
#else
  (void)raw; /* the default install has no raw entry point, so raw is always false */
  reader_rs_status rs=reader_rs_decode(store,wire.data(),wire.size(),&g.record,&re);
#endif
  if(rs==READER_RS_REVISION)reject(READER_JH_REVISION,"Revision module refused the position wire",rs,re.gap,re.revision_code);
  if(rs==READER_RS_MEMORY)reject(READER_JH_MEMORY,"Cannot decode the position wire",rs);
  if(rs!=READER_RS_OK)reject(READER_JH_ARGUMENT,"Cannot decode the position wire",rs,re.gap,re.revision_code);
  const reader_rs_record &r=g.record;
  if(std::strcmp(r.entity_kind,"progress")||std::strcmp(r.operation,"put")||!r.has_location||!r.exact)
    reject(READER_JH_ARGUMENT,"Only a progress put with a location is a reading position");
  entry fresh{0,kind,r.book_key,location_key(r),std::move(wire)};
  if(fresh.bytes()>READER_JH_MAX_ENTRY_BYTES||fresh.bytes()>h->max_bytes)reject(READER_JH_TOO_LARGE,"One history entry exceeds its byte limit");
  bool have=!h->list.empty();
  if(have&&h->list[h->cursor].key==fresh.key){*result=make_result(h,READER_JH_UNCHANGED,0,0);return;}
  bool coalesce=have&&kind==READER_JH_PAGE&&h->list[h->cursor].kind==READER_JH_PAGE&&h->list[h->cursor].book==fresh.book;
  size_t keep=have?(coalesce?h->cursor:h->cursor+1):0;
  h->list.reserve(keep+1); /* the only allocation that can fail after validation */
  fresh.id=entry_id(); /* reject exhaustion before changing the history */
  size_t forward=have?h->list.size()-(h->cursor+1):0;
  for(size_t i=keep;i<h->list.size();i++)h->bytes-=h->list[i].bytes();
  h->list.erase(h->list.begin()+(std::ptrdiff_t)keep,h->list.end());
  h->bytes+=fresh.bytes();h->list.push_back(std::move(fresh));
  size_t drop=0;
  while(drop+1<h->list.size()&&((size_t)(h->list.size()-drop)>(size_t)h->max_entries||h->bytes>(size_t)h->max_bytes)){h->bytes-=h->list[drop].bytes();drop++;}
  if(drop)h->list.erase(h->list.begin(),h->list.begin()+(std::ptrdiff_t)drop);
  h->cursor=h->list.size()-1;h->generation++;h->evicted_total+=drop;h->truncated_total+=forward;
  *result=make_result(h,coalesce?READER_JH_COALESCED:READER_JH_ADDED,drop,forward);
}
void fill(reader_jh_item *out,const entry &e,size_t index,reader_jh_direction direction,uint64_t generation){
  char *copy=(char *)std::malloc(e.wire.size()+1);if(!copy)throw std::bad_alloc();
  std::memcpy(copy,e.wire.data(),e.wire.size());copy[e.wire.size()]=0;
  std::memset(out,0,sizeof(*out));out->struct_version=READER_JH_STRUCT_VERSION;out->direction=direction;out->kind=e.kind;
  out->entry_id=e.id;out->generation=generation;out->index=index;out->accounted_bytes=e.bytes();
  std::snprintf(out->book_key,sizeof(out->book_key),"%s",e.book.c_str());out->wire=copy;out->wire_bytes=e.wire.size();
}
}

extern "C" reader_jh_status reader_jh_open(const reader_jh_limits *limits,reader_jh **out,reader_jh_error *error){
  if(error)std::memset(error,0,sizeof(*error));
  if(out)*out=nullptr;
  try{
    if(!out)reject(READER_JH_ARGUMENT,"Missing history output");
    uint32_t entries=READER_JH_DEFAULT_ENTRIES,bytes=READER_JH_DEFAULT_BYTES;
    if(limits){
      if(limits->struct_version!=READER_JH_STRUCT_VERSION)reject(READER_JH_VERSION_UNSUPPORTED,"Unknown reader_jh_limits version");
      if(limits->max_entries>READER_JH_MAX_ENTRIES)reject(READER_JH_LIMIT,"max_entries is above the hard cap of 256");
      if(limits->max_bytes>READER_JH_MAX_BYTES||(limits->max_bytes&&limits->max_bytes<READER_JH_MIN_BYTES))reject(READER_JH_LIMIT,"max_bytes is outside 4096..1048576");
      if(limits->max_entries)entries=limits->max_entries;
      if(limits->max_bytes)bytes=limits->max_bytes;
    }
    reader_jh *h=new reader_jh();h->owner=std::this_thread::get_id();h->max_entries=entries;h->max_bytes=bytes;*out=h;
    return READER_JH_OK;
  }
  catch(const failure &f){return report(error,f);}
  catch(...){return report(error,{READER_JH_MEMORY,READER_RS_OK,READER_RS_GAP_NONE,0,"Cannot allocate jump-history memory"});}
}
extern "C" reader_jh_status reader_jh_close(reader_jh **handle,reader_jh_error *error){
  if(error)std::memset(error,0,sizeof(*error));
  if(!handle)return report(error,{READER_JH_ARGUMENT,READER_RS_OK,READER_RS_GAP_NONE,0,"Missing history pointer"});
  if(!*handle)return READER_JH_OK;
  if(std::this_thread::get_id()!=(*handle)->owner)return report(error,{READER_JH_THREAD,READER_RS_OK,READER_RS_GAP_NONE,0,"History closed on a thread that does not own it"});
  delete *handle;*handle=nullptr;return READER_JH_OK;
}
extern "C" reader_jh_status reader_jh_adopt_thread(reader_jh *h,reader_jh_error *error){
  if(error)std::memset(error,0,sizeof(*error));
  if(!h)return report(error,{READER_JH_ARGUMENT,READER_RS_OK,READER_RS_GAP_NONE,0,"Missing history handle"});
  h->owner=std::this_thread::get_id();return READER_JH_OK;
}
extern "C" reader_jh_status reader_jh_clear(reader_jh *h,reader_jh_error *error){
  return guarded(h,error,[&]{
    if(h->list.empty())return;
    h->list.clear();h->bytes=0;h->cursor=0;h->generation++;
  });
}
extern "C" reader_jh_status reader_jh_commit(reader_jh *h,reader_revisions *store,const reader_jh_position *p,reader_jh_result *result,reader_jh_error *error){
  return guarded(h,error,[&]{
    if(!store||!p||!p->capture||!p->book_key||!p->parser_version||!result)reject(READER_JH_ARGUMENT,"Missing revision store, position or result");
    if(p->kind<READER_JH_PAGE||p->kind>READER_JH_TOC)reject(READER_JH_ARGUMENT,"Landing kind must be page, search or table of contents");
    char id[33];reader_revision_error ie{};
    if(reader_revision_new_id(id,&ie)!=READER_REV_OK)reject(READER_JH_REVISION,"Cannot create a transient revision ID",READER_RS_OK,READER_RS_GAP_NONE,(int)ie.code);
    reader_rs_envelope env{};env.revision_id=id;env.operation="put";env.entity_kind="progress";env.book_key=p->book_key;env.parser_version=p->parser_version;
    char *bytes=nullptr;size_t n=0;reader_rs_error re{};
    reader_rs_status rs=reader_rs_encode_v2(store,&env,p->capture,p->part,&bytes,&n,&re);
    std::unique_ptr<char,decltype(&reader_rs_free)> owned(bytes,&reader_rs_free);
    if(rs!=READER_RS_OK){
      if(rs==READER_RS_NOT_REPRESENTABLE)reject(READER_JH_NOT_REPRESENTABLE,"Capture has no lossless position wire",rs,re.gap);
      if(rs==READER_RS_REVISION)reject(READER_JH_REVISION,"Revision module refused the position wire",rs,re.gap,re.revision_code);
      if(rs==READER_RS_MEMORY)reject(READER_JH_MEMORY,"Cannot encode the position wire",rs);
      reject(READER_JH_ARGUMENT,"Capture is not usable as a position",rs,re.gap);
    }
    std::string wire(owned.get(),n);
    commit_wire(h,store,p->kind,std::move(wire),result,false);
  });
}
extern "C" reader_jh_status reader_jh_commit_wire(reader_jh *h,reader_revisions *store,reader_jh_kind kind,const void *wire,size_t bytes,reader_jh_result *result,reader_jh_error *error){
  return guarded(h,error,[&]{
    if(!wire||!bytes)reject(READER_JH_ARGUMENT,"Missing position wire");
    if(bytes>READER_JH_MAX_ENTRY_BYTES)reject(READER_JH_TOO_LARGE,"Position wire exceeds the entry byte limit");
    commit_wire(h,store,kind,std::string((const char *)wire,bytes),result,false);
  });
}
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
extern "C" reader_jh_status reader_jh_commit_fixed_v3(reader_jh *h,reader_revisions *store,const reader_jh_position *p,reader_jh_result *result,reader_jh_error *error){
  return guarded(h,error,[&]{
    if(!store||!p||!p->capture||!p->book_key||!p->parser_version||!result)reject(READER_JH_ARGUMENT,"Missing revision store, position or result");
    if(p->kind<READER_JH_PAGE||p->kind>READER_JH_TOC)reject(READER_JH_ARGUMENT,"Landing kind must be page, search or table of contents");
    char id[33];reader_revision_error ie{};
    if(reader_revision_new_id(id,&ie)!=READER_REV_OK)reject(READER_JH_REVISION,"Cannot create a transient revision ID",READER_RS_OK,READER_RS_GAP_NONE,(int)ie.code);
    reader_rs_envelope env{};env.revision_id=id;env.operation="put";env.entity_kind="progress";env.book_key=p->book_key;env.parser_version=p->parser_version;
    char *bytes=nullptr;size_t n=0;reader_rs_error re{};
    /* Anchor v3 is fixed_page only; the installed raw encoder refuses every
       other capture before any byte is produced. */
    reader_rs_status rs=reader_rs_encode_fixed_v3(store,&env,p->capture,&bytes,&n,&re);
    std::unique_ptr<char,decltype(&reader_rs_free)> owned(bytes,&reader_rs_free);
    if(rs!=READER_RS_OK){
      if(rs==READER_RS_NOT_REPRESENTABLE)reject(READER_JH_NOT_REPRESENTABLE,"Capture has no lossless raw position wire",rs,re.gap);
      if(rs==READER_RS_REVISION)reject(READER_JH_REVISION,"Revision module refused the position wire",rs,re.gap,re.revision_code);
      if(rs==READER_RS_MEMORY)reject(READER_JH_MEMORY,"Cannot encode the position wire",rs);
      reject(READER_JH_ARGUMENT,"Capture is not usable as a raw position",rs,re.gap);
    }
    std::string wire(owned.get(),n);
    commit_wire(h,store,p->kind,std::move(wire),result,true);
  });
}
extern "C" reader_jh_status reader_jh_commit_wire_raw_v3(reader_jh *h,reader_revisions *store,reader_jh_kind kind,const void *wire,size_t bytes,reader_jh_result *result,reader_jh_error *error){
  return guarded(h,error,[&]{
    if(!wire||!bytes)reject(READER_JH_ARGUMENT,"Missing position wire");
    if(bytes>READER_JH_MAX_ENTRY_BYTES)reject(READER_JH_TOO_LARGE,"Position wire exceeds the entry byte limit");
    commit_wire(h,store,kind,std::string((const char *)wire,bytes),result,true);
  });
}
#endif
extern "C" reader_jh_status reader_jh_peek(reader_jh *h,reader_jh_direction direction,reader_jh_item *out,reader_jh_error *error){
  if(out)std::memset(out,0,sizeof(*out));
  return guarded(h,error,[&]{
    if(!out||(direction!=READER_JH_BACK&&direction!=READER_JH_FORWARD))reject(READER_JH_ARGUMENT,"Missing item or direction");
    size_t at;
    if(h->list.empty())reject(READER_JH_EMPTY,"History is empty");
    if(direction==READER_JH_BACK){if(!h->cursor)reject(READER_JH_EMPTY,"Nothing behind the current position");at=h->cursor-1;}
    else{if(h->cursor+1>=h->list.size())reject(READER_JH_EMPTY,"Nothing ahead of the current position");at=h->cursor+1;}
    fill(out,h->list[at],at,direction,h->generation);
  });
}
extern "C" reader_jh_status reader_jh_item_at(reader_jh *h,size_t index,reader_jh_item *out,reader_jh_error *error){
  if(out)std::memset(out,0,sizeof(*out));
  return guarded(h,error,[&]{
    if(!out||index>=h->list.size())reject(READER_JH_ARGUMENT,"Missing item or index outside the history");
    fill(out,h->list[index],index,(reader_jh_direction)0,h->generation);
  });
}
extern "C" reader_jh_status reader_jh_complete(reader_jh *h,const reader_jh_item *item,reader_jh_error *error){
  return guarded(h,error,[&]{
    if(!item)reject(READER_JH_ARGUMENT,"Missing item");
    if(item->struct_version!=READER_JH_STRUCT_VERSION){
      if(!item->struct_version)reject(READER_JH_ARGUMENT,"Item was not read by reader_jh_peek");
      reject(READER_JH_VERSION_UNSUPPORTED,"Unknown reader_jh_item version");
    }
    if(item->direction!=READER_JH_BACK&&item->direction!=READER_JH_FORWARD)reject(READER_JH_ARGUMENT,"Item was not read by reader_jh_peek");
    if(item->generation!=h->generation||h->list.empty())reject(READER_JH_STALE,"History changed after the item was read");
    size_t at=h->cursor;
    if(item->direction==READER_JH_BACK){if(!at)reject(READER_JH_STALE,"No entry behind the cursor");at--;}
    else{if(at+1>=h->list.size())reject(READER_JH_STALE,"No entry ahead of the cursor");at++;}
    if(h->list[at].id!=item->entry_id||item->index!=at)reject(READER_JH_STALE,"Item no longer names the neighbor entry");
    h->cursor=at;h->generation++;
  });
}
extern "C" void reader_jh_item_release(reader_jh_item *item){
  if(!item)return;
  std::free(item->wire);std::memset(item,0,sizeof(*item));
}
extern "C" reader_jh_status reader_jh_state_get(reader_jh *h,reader_jh_state *out,reader_jh_error *error){
  return guarded(h,error,[&]{
    if(!out)reject(READER_JH_ARGUMENT,"Missing state output");
    if(out->struct_version&&out->struct_version!=READER_JH_STRUCT_VERSION)reject(READER_JH_VERSION_UNSUPPORTED,"Unknown reader_jh_state version");
    std::memset(out,0,sizeof(*out));out->struct_version=READER_JH_STRUCT_VERSION;
    out->count=h->list.size();out->cursor=h->list.empty()?0:h->cursor;out->bytes=h->bytes;out->max_entries=h->max_entries;out->max_bytes=h->max_bytes;
    out->can_back=!h->list.empty()&&h->cursor>0;out->can_forward=!h->list.empty()&&h->cursor+1<h->list.size();
    out->generation=h->generation;out->evicted_total=h->evicted_total;out->truncated_total=h->truncated_total;
  });
}
