/* SPDX-License-Identifier: MIT */
#include "reading_internal.h"
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
#include <reader_projection.h>
#include <reader_selector_bytes_v1.h>
#include "reader_reading_state_retained_raw_v1.h"
#endif
#include <sqlite3.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <new>
#include <string>

namespace {
const char *mode_name(reader_rs_mode mode){
  return mode==READER_RS_REFLOW_GLOBAL?"reflow_global":mode==READER_RS_EPUB_CHAPTER?"epub_chapter":mode==READER_RS_FIXED_PAGE?"fixed_page":nullptr;
}
/* RFC 8259 string; UTF-8 is copied unchanged, so retained bytes stay exact. */
void quote(std::string &out,const char *text,size_t size){
  static const char hex[]="0123456789abcdef";
  out+='"';
  for(size_t i=0;i<size;i++){
    unsigned char c=(unsigned char)text[i];
    if(c=='"'||c=='\\'){out+='\\';out+=(char)c;}
    else if(c<0x20){out+="\\u00";out+=hex[c>>4];out+=hex[c&15];}
    else out+=(char)c;
  }
  out+='"';
}
void quote(std::string &out,const char *text){quote(out,text?text:"",text?std::strlen(text):0);}
bool bounded(const char *text,size_t limit){size_t n=0;while(n<=limit&&text[n])n++;return n<=limit;}
reader_rs_gap gap_of(const reader_rs_capture *c){
  if(c->mode==READER_RS_FIXED_PAGE){
    const exr_fixed_anchor *a=c->fixed;
    if(!a->exact_size)return a->prefix_size||a->suffix_size?READER_RS_GAP_POINT:READER_RS_GAP_TEXTLESS_PAGE;
    if(!bounded(a->page_id,256))return READER_RS_GAP_LIMIT;
    if(std::memchr(a->exact,0,a->exact_size)||(a->prefix_size&&std::memchr(a->prefix,0,a->prefix_size))||
       (a->suffix_size&&std::memchr(a->suffix,0,a->suffix_size)))return READER_RS_GAP_NUL;
    return READER_RS_GAP_NONE;
  }
  const exr_anchor *a=c->anchor;
  if(!a->exact)return READER_RS_GAP_LEGACY;
  if(!a->exact[0])return READER_RS_GAP_POINT;
  if(c->mode==READER_RS_REFLOW_GLOBAL)return a->chapter&&a->chapter[0]?READER_RS_GAP_CHAPTER_SCOPE:READER_RS_GAP_NONE;
  if(!bounded(c->part_path,1024))return READER_RS_GAP_LIMIT;
  if(a->chapter&&std::strcmp(a->chapter,c->part_path))return READER_RS_GAP_ROUTE;
  return READER_RS_GAP_NONE;
}
void require_capture(const reader_rs_capture *c){
  if(!c||!mode_name(c->mode))reject(READER_RS_ARGUMENT,"Missing reading capture mode");
  if(c->mode==READER_RS_FIXED_PAGE){
    const exr_fixed_anchor *a=c->fixed;
    if(!a||!a->page_id||!a->page_id[0]||(a->exact_size&&!a->exact)||(a->prefix_size&&!a->prefix)||(a->suffix_size&&!a->suffix)||
       a->start==SIZE_MAX||a->end<a->start||a->end-a->start!=a->exact_size)reject(READER_RS_ARGUMENT,"Fixed capture is not an SDK selector");
    return;
  }
  const exr_anchor *a=c->anchor;
  if(!a||a->start==SIZE_MAX||a->end<a->start||(a->exact&&a->end-a->start!=std::strlen(a->exact)))reject(READER_RS_ARGUMENT,"Text capture is not an SDK selector");
  if(c->mode==READER_RS_EPUB_CHAPTER&&(!c->part_path||!c->part_path[0]))reject(READER_RS_ARGUMENT,"EPUB capture requires its exact part path");
}
std::string location(const reader_rs_capture *c,const char *parser,unsigned version,size_t part){
  std::string out="{\"mode\":";quote(out,mode_name(c->mode));
  out+=",\"parser_version\":";quote(out,parser);out+=",\"anchor_version\":"+std::to_string(version);
  const char *exact,*prefix,*suffix;size_t exact_size,prefix_size,suffix_size,start,end;
  if(c->mode==READER_RS_FIXED_PAGE){
    const exr_fixed_anchor *a=c->fixed;
    out+=",\"page_id\":";quote(out,a->page_id);out+=",\"page\":"+std::to_string((unsigned long long)c->page);
    exact=a->exact;prefix=a->prefix;suffix=a->suffix;exact_size=a->exact_size;prefix_size=a->prefix_size;suffix_size=a->suffix_size;start=a->start;end=a->end;
  }else{
    const exr_anchor *a=c->anchor;
    if(c->mode==READER_RS_EPUB_CHAPTER){out+=",\"part_path\":";quote(out,c->part_path);if(version==2)out+=",\"part\":"+std::to_string((unsigned long long)part);}
    exact=a->exact;prefix=a->prefix?a->prefix:"";suffix=a->suffix?a->suffix:"";
    exact_size=std::strlen(exact);prefix_size=std::strlen(prefix);suffix_size=std::strlen(suffix);start=a->start;end=a->end;
  }
  #ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
  if(version==3){
    auto raw=[&](const char *value,size_t count){
      if(count>65536)reject(READER_RS_NOT_REPRESENTABLE,"Raw selector exceeds its byte bound",READER_RS_GAP_LIMIT);
      out+="{\"base64\":";
      if(value){
        size_t size=0;auto status=reader_revision_selector_encode_v1(value,count,nullptr,0,&size);
        if(status==READER_SELECTOR_V1_MEMORY)throw std::bad_alloc();
        if(status!=READER_SELECTOR_V1_OK)reject(READER_RS_NOT_REPRESENTABLE,"Invalid raw selector bytes",READER_RS_GAP_LIMIT);
        std::string encoded(size,'\0');
        status=reader_revision_selector_encode_v1(value,count,encoded.data(),encoded.size(),&size);
        if(status==READER_SELECTOR_V1_MEMORY)throw std::bad_alloc();
        if(status!=READER_SELECTOR_V1_OK)reject(READER_RS_NOT_REPRESENTABLE,"Cannot encode raw selector bytes",READER_RS_GAP_LIMIT);
        quote(out,encoded.data(),encoded.size());
      }else out+="null";
      out+=",\"size\":"+std::to_string(count)+"}";
    };
    out+=",\"selector\":{\"exact\":";raw(exact,exact_size);out+=",\"prefix\":";raw(prefix,prefix_size);out+=",\"suffix\":";raw(suffix,suffix_size);
    out+=",\"start\":"+std::to_string(start)+",\"end\":"+std::to_string(end)+"}}";return out;
  }
#endif
  out+=",\"selector\":{\"exact\":";quote(out,exact,exact_size);
  out+=",\"prefix\":";quote(out,prefix,prefix_size);out+=",\"suffix\":";quote(out,suffix,suffix_size);
  out+=",\"start\":"+std::to_string((unsigned long long)start)+",\"end\":"+std::to_string((unsigned long long)end);
  if(version==2&&c->mode==READER_RS_REFLOW_GLOBAL){out+=",\"chapter\":";if(c->anchor->chapter)quote(out,c->anchor->chapter);else out+="null";}
  out+="}}";
  return out;
}
char *copy(const std::string &s){char *out=(char *)std::malloc(s.size()+1);if(!out)throw std::bad_alloc();std::memcpy(out,s.data(),s.size());out[s.size()]=0;return out;}
void validate(reader_revisions *store,const std::string &wire,reader_revision_info *info,bool raw=false){
    reader_revision_error e{};reader_revision_status status;
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
  if(raw)status=reader_revision_validate_raw_v3(store,wire.data(),wire.size(),nullptr,info,&e);else
#else
  (void)raw;
#endif
  status=reader_revision_validate(store,wire.data(),wire.size(),nullptr,info,&e);
  if(status!=READER_REV_OK)reject(READER_RS_REVISION,"Revision module refused the reading-state wire",READER_RS_GAP_NONE,0,(int)status);
}
struct database {
  sqlite3 *db=nullptr;
  database(){if(sqlite3_open_v2(":memory:",&db,SQLITE_OPEN_READWRITE|SQLITE_OPEN_CREATE,nullptr)!=SQLITE_OK)reject(READER_RS_MEMORY,"Cannot open the in-memory JSON reader");}
  ~database(){sqlite3_close(db);}
};
struct statement {
  sqlite3_stmt *s=nullptr;
  statement(sqlite3 *db,const char *sql){if(sqlite3_prepare_v2(db,sql,-1,&s,nullptr)!=SQLITE_OK)reject(READER_RS_MEMORY,"Cannot prepare the JSON reader");}
  ~statement(){sqlite3_finalize(s);}
};
bool present(sqlite3_stmt *s,int column){return sqlite3_column_type(s,column)!=SQLITE_NULL;}
char *column(sqlite3_stmt *s,int column,size_t *size=nullptr){
  if(!present(s,column)){if(size)*size=0;return nullptr;}
  const unsigned char *text=sqlite3_column_text(s,column);int n=sqlite3_column_bytes(s,column);
  if(!text&&n)throw std::bad_alloc();
  if(size)*size=(size_t)n;
  return copy(std::string((const char *)(text?text:(const unsigned char *)""),(size_t)n));
}
void field(char *out,size_t capacity,const std::string &value){if(value.size()>=capacity)reject(READER_RS_REVISION,"Decoded field exceeds its fixed buffer");std::memcpy(out,value.c_str(),value.size()+1);}
}

extern "C" reader_rs_gap reader_rs_classify(const reader_rs_capture *capture){
  try{require_capture(capture);}catch(...){return READER_RS_GAP_NONE;}
  return gap_of(capture);
}
extern "C" void reader_rs_free(void *memory){std::free(memory);}
static reader_rs_status encode(reader_revisions *store,const reader_rs_envelope *v,const reader_rs_capture *c,unsigned version,size_t part,char **wire,size_t *bytes,reader_rs_error *error,bool raw_api=false){
  if(wire)*wire=nullptr;
  if(bytes)*bytes=0;
  return call(error,[&]{
    if(!store||!v||!c||!wire||!bytes||!v->revision_id||!v->operation||!v->entity_kind||!v->book_key||!mode_name(c->mode)||(v->parent_count&&!v->parents))
      reject(READER_RS_ARGUMENT,"Missing reading-state envelope");
    bool annotation=!std::strcmp(v->entity_kind,"annotation"),deleted=!std::strcmp(v->operation,"delete");
    if(!annotation&&std::strcmp(v->entity_kind,"progress"))reject(READER_RS_ARGUMENT,"Reading state is progress or annotation");
    if(annotation&&!v->annotation_id)reject(READER_RS_ARGUMENT,"Annotation requires its global ID");
    std::string key=v->book_key;if(annotation)key+=std::string(":")+v->annotation_id;
    std::string out="{\"version\":1,\"id\":";quote(out,v->revision_id);
    out+=",\"entity_kind\":";quote(out,v->entity_kind);out+=",\"entity_key\":";quote(out,key.c_str());
    out+=",\"operation\":";quote(out,v->operation);out+=",\"location_kind\":";quote(out,mode_name(c->mode));
    out+=",\"parents\":[";
    for(size_t i=0;i<v->parent_count;i++){if(!v->parents[i])reject(READER_RS_ARGUMENT,"Missing parent ID");if(i)out+=',';quote(out,v->parents[i]);}
    out+="],\"payload\":";
    if(deleted)out+="null";
    else{
      require_capture(c);
      if(version==3&&c->mode==READER_RS_FIXED_PAGE&&(c->fixed->exact_size>65536||c->fixed->prefix_size>128||c->fixed->suffix_size>128))
        reject(READER_RS_NOT_REPRESENTABLE,"Raw selector exceeds its byte bound",READER_RS_GAP_LIMIT);
      reader_rs_gap gap=gap_of(c);
      if(version==1&&gap!=READER_RS_GAP_NONE)reject(READER_RS_NOT_REPRESENTABLE,"SDK capture has no lossless wire v1 selector",gap);
      if(version==2){
        if(c->mode!=READER_RS_FIXED_PAGE&&!c->anchor->exact)reject(READER_RS_NOT_REPRESENTABLE,"Legacy offsets are not a v2 capture",READER_RS_GAP_LEGACY);
        if(c->mode==READER_RS_EPUB_CHAPTER&&c->anchor->chapter&&std::strcmp(c->anchor->chapter,c->part_path))
          reject(READER_RS_NOT_REPRESENTABLE,"Captured chapter and EPUB route disagree",READER_RS_GAP_ROUTE);
        if(c->mode==READER_RS_FIXED_PAGE){const exr_fixed_anchor *a=c->fixed;
          if((a->exact_size&&std::memchr(a->exact,0,a->exact_size))||(a->prefix_size&&std::memchr(a->prefix,0,a->prefix_size))||
             (a->suffix_size&&std::memchr(a->suffix,0,a->suffix_size)))reject(READER_RS_NOT_REPRESENTABLE,"NUL selector bytes are not representable",READER_RS_GAP_NUL);
        }
        if(gap==READER_RS_GAP_LIMIT||gap==READER_RS_GAP_ROUTE)reject(READER_RS_NOT_REPRESENTABLE,"Capture route exceeds the wire contract",gap);
      }
      if(version==3&&c->mode!=READER_RS_FIXED_PAGE)reject(READER_RS_ARGUMENT,"Anchor3 is fixed_page only");
      if(!v->parser_version)reject(READER_RS_ARGUMENT,"Parser version is required for a location");
      out+="{\"book_key\":";quote(out,v->book_key);
      if(annotation){out+=",\"annotation_id\":";quote(out,v->annotation_id);}
      out+=",\"location\":"+location(c,v->parser_version,version,part);
      if(annotation){out+=",\"text\":";quote(out,v->note_text);}
      out+='}';
    }
    out+='}';
    reader_revision_info info{};validate(store,out,&info,raw_api);
    *wire=copy(out);*bytes=out.size();
  });
}
extern "C" reader_rs_status reader_rs_encode(reader_revisions *store,const reader_rs_envelope *v,const reader_rs_capture *c,char **wire,size_t *bytes,reader_rs_error *error){
  return encode(store,v,c,1,0,wire,bytes,error);
}
extern "C" reader_rs_status reader_rs_encode_v2(reader_revisions *store,const reader_rs_envelope *v,const reader_rs_capture *c,size_t part,char **wire,size_t *bytes,reader_rs_error *error){
  return encode(store,v,c,2,part,wire,bytes,error);
}
extern "C" void reader_rs_record_free(reader_rs_record *r){
  if(!r)return;
  std::free(r->part_path);std::free(r->page_id);std::free(r->exact);std::free(r->prefix);std::free(r->suffix);std::free(r->note_text);std::free(r->chapter);
  std::memset(r,0,sizeof(*r));
}
static reader_rs_status decode(bool raw_api,reader_revisions *store,const void *wire,size_t bytes,reader_rs_record *out,reader_rs_error *error){
  if(out)std::memset(out,0,sizeof(*out));
  reader_rs_status status=call(error,[&]{
    if(!store||!wire||!out)reject(READER_RS_ARGUMENT,"Missing wire or record output");
    if(raw_api&&(bytes<2||bytes>READER_REVISION_MAX_BYTES))reject(READER_RS_REVISION,"Raw wire exceeds its bounded envelope",READER_RS_GAP_NONE,0,READER_REV_LIMIT);
    std::string w((const char *)wire,bytes);reader_revision_info info{};validate(store,w,&info,raw_api);
    if(std::strcmp(info.entity_kind,"progress")&&std::strcmp(info.entity_kind,"annotation"))reject(READER_RS_ARGUMENT,"Wire is not reading state");
    database json;statement q(json.db,"SELECT json_extract(?1,'$.location_kind'),json_extract(?1,'$.payload.location.parser_version'),"
      "json_extract(?1,'$.payload.location.anchor_version'),json_extract(?1,'$.payload.location.part_path'),"
      "json_extract(?1,'$.payload.location.page_id'),json_extract(?1,'$.payload.location.page'),"
      "json_extract(?1,'$.payload.location.selector.exact'),json_extract(?1,'$.payload.location.selector.prefix'),"
      "json_extract(?1,'$.payload.location.selector.suffix'),json_extract(?1,'$.payload.location.selector.start'),"
      "json_extract(?1,'$.payload.location.selector.end'),json_extract(?1,'$.payload.text'),"
      "json_extract(?1,'$.payload.location.part'),json_extract(?1,'$.payload.location.selector.chapter')");
    if(sqlite3_bind_text64(q.s,1,w.data(),w.size(),SQLITE_TRANSIENT,SQLITE_UTF8)!=SQLITE_OK||sqlite3_step(q.s)!=SQLITE_ROW)reject(READER_RS_MEMORY,"Cannot read validated wire JSON");
    field(out->entity_kind,sizeof(out->entity_kind),info.entity_kind);field(out->operation,sizeof(out->operation),info.operation);
    field(out->book_key,sizeof(out->book_key),info.book_key);
    if(!std::strcmp(info.entity_kind,"annotation")){std::string key=info.entity_key;field(out->annotation_id,sizeof(out->annotation_id),key.substr(key.rfind(':')+1));}
    std::string mode=(const char *)sqlite3_column_text(q.s,0);
    out->mode=mode=="reflow_global"?READER_RS_REFLOW_GLOBAL:mode=="epub_chapter"?READER_RS_EPUB_CHAPTER:READER_RS_FIXED_PAGE;
    out->has_location=present(q.s,1);
    if(!out->has_location)return;
    field(out->parser_version,sizeof(out->parser_version),(const char *)sqlite3_column_text(q.s,1));
    out->anchor_version=(uint64_t)sqlite3_column_int64(q.s,2);
    out->part_path=column(q.s,3);out->page_id=column(q.s,4);
    if(present(q.s,5))out->page=(uint64_t)sqlite3_column_int64(q.s,5);
    #ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
    if(out->anchor_version==3){
      statement raw(json.db,"SELECT json_extract(?1,'$.payload.location.selector.exact.base64'),json_extract(?1,'$.payload.location.selector.exact.size'),json_extract(?1,'$.payload.location.selector.prefix.base64'),json_extract(?1,'$.payload.location.selector.prefix.size'),json_extract(?1,'$.payload.location.selector.suffix.base64'),json_extract(?1,'$.payload.location.selector.suffix.size')");
      if(sqlite3_bind_text64(raw.s,1,w.data(),w.size(),SQLITE_TRANSIENT,SQLITE_UTF8)!=SQLITE_OK||sqlite3_step(raw.s)!=SQLITE_ROW)reject(READER_RS_MEMORY,"Cannot read validated raw selector");
      auto take=[&](int col,size_t limit,size_t scalars,size_t &count)->char *{
        count=(size_t)sqlite3_column_int64(raw.s,col+1);if(!present(raw.s,col))return nullptr;
        const char *p=(const char *)sqlite3_column_text(raw.s,col);size_t n=(size_t)sqlite3_column_bytes(raw.s,col);std::string decoded;
        size_t size=0;auto status=reader_revision_selector_decode_v1(p,n,count,limit,scalars,nullptr,0,&size);
        if(status==READER_SELECTOR_V1_MEMORY)throw std::bad_alloc();
        if(status!=READER_SELECTOR_V1_OK)reject(READER_RS_REVISION,"Invalid validated raw selector");
        decoded.resize(size);
        status=reader_revision_selector_decode_v1(p,n,count,limit,scalars,decoded.data(),decoded.size(),&size);
        if(status==READER_SELECTOR_V1_MEMORY)throw std::bad_alloc();
        if(status!=READER_SELECTOR_V1_OK)reject(READER_RS_REVISION,"Invalid validated raw selector");
        return copy(decoded);
      };
      out->exact=take(0,65536,SIZE_MAX,out->exact_size);out->prefix=take(2,128,32,out->prefix_size);out->suffix=take(4,128,32,out->suffix_size);
    }else
#endif
    {out->exact=column(q.s,6,&out->exact_size);out->prefix=column(q.s,7,&out->prefix_size);out->suffix=column(q.s,8,&out->suffix_size);}
    out->start=(uint64_t)sqlite3_column_int64(q.s,9);out->end=(uint64_t)sqlite3_column_int64(q.s,10);
    out->note_text=column(q.s,11);
    if(present(q.s,12))out->part=(uint64_t)sqlite3_column_int64(q.s,12);
    out->chapter=column(q.s,13);
  });
  if(status!=READER_RS_OK)reader_rs_record_free(out);
  return status;
}

extern "C" reader_rs_status reader_rs_decode(reader_revisions *s,const void *w,size_t n,reader_rs_record *r,reader_rs_error *e){return decode(false,s,w,n,r,e);}
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
extern "C" reader_rs_status reader_rs_decode_raw_v3(reader_revisions *s,const void *w,size_t n,reader_rs_record *r,reader_rs_error *e){return decode(true,s,w,n,r,e);}
extern "C" reader_rs_status reader_rs_encode_fixed_v3(reader_revisions *s,const reader_rs_envelope *e,const reader_rs_capture *c,char **w,size_t *n,reader_rs_error *error){
  if(w)*w=nullptr;
  if(n)*n=0;
  if(!c||c->mode!=READER_RS_FIXED_PAGE)return call(error,[&]{reject(READER_RS_ARGUMENT,"Anchor3 is fixed_page only");});
  return encode(s,e,c,3,0,w,n,error,true);
}
/* Public API revision v1 over the existing raw-v3 store encoder. */
extern "C" reader_rs_status reader_rs_encode_retained_raw_v1(reader_revisions *s,const reader_rs_envelope *e,const reader_rs_capture *c,unsigned version,size_t part,char **w,size_t *n,reader_rs_error *error){
  if(w)*w=nullptr;
  if(n)*n=0;
  if(version<1 || version>3 || (version==3 && (!c || c->mode!=READER_RS_FIXED_PAGE)))
    return call(error,[&]{reject(READER_RS_ARGUMENT,"Retained raw encode requires anchor 1/2, or fixed_page anchor3");});
  return encode(s,e,c,version,part,w,n,error,true);
}
#endif

#if defined(EXR_READER_PURE_CAPTURE_CANDIDATE) && EXR_READER_PURE_CAPTURE_CANDIDATE == 1
#include "reader_reading_state_capture_raw_candidate.h"
extern "C" reader_rs_status reader_rs_encode_capture_raw_candidate(
    reader_revisions *s,const reader_rs_envelope *e,const reader_rs_capture *c,
    unsigned version,size_t part,char **w,size_t *n,reader_rs_error *error) {
  if(w)*w=nullptr;
  if(n)*n=0;
  if(version<1 || version>3 || (version==3 && (!c || c->mode!=READER_RS_FIXED_PAGE))) {
    return call(error,[&]{
      reject(READER_RS_ARGUMENT,"Pure raw capture requires anchor 1/2, or fixed_page anchor3");
    });
  }
  return encode(s,e,c,version,part,w,n,error,true);
}
#endif
