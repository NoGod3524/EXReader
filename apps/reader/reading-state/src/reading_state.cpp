/* SPDX-License-Identifier: MIT */
#include "reading_internal.h"
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
  out+=",\"selector\":{\"exact\":";quote(out,exact,exact_size);
  out+=",\"prefix\":";quote(out,prefix,prefix_size);out+=",\"suffix\":";quote(out,suffix,suffix_size);
  out+=",\"start\":"+std::to_string((unsigned long long)start)+",\"end\":"+std::to_string((unsigned long long)end);
  if(version==2&&c->mode==READER_RS_REFLOW_GLOBAL){out+=",\"chapter\":";if(c->anchor->chapter)quote(out,c->anchor->chapter);else out+="null";}
  out+="}}";
  return out;
}
char *copy(const std::string &s){char *out=(char *)std::malloc(s.size()+1);if(!out)throw std::bad_alloc();std::memcpy(out,s.data(),s.size());out[s.size()]=0;return out;}
void validate(reader_revisions *store,const std::string &wire,reader_revision_info *info){
  reader_revision_error e{};reader_revision_status status=reader_revision_validate(store,wire.data(),wire.size(),nullptr,info,&e);
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
static reader_rs_status encode(reader_revisions *store,const reader_rs_envelope *v,const reader_rs_capture *c,unsigned version,size_t part,char **wire,size_t *bytes,reader_rs_error *error){
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
      if(!v->parser_version)reject(READER_RS_ARGUMENT,"Parser version is required for a location");
      out+="{\"book_key\":";quote(out,v->book_key);
      if(annotation){out+=",\"annotation_id\":";quote(out,v->annotation_id);}
      out+=",\"location\":"+location(c,v->parser_version,version,part);
      if(annotation){out+=",\"text\":";quote(out,v->note_text);}
      out+='}';
    }
    out+='}';
    reader_revision_info info{};validate(store,out,&info);
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
extern "C" reader_rs_status reader_rs_decode(reader_revisions *store,const void *wire,size_t bytes,reader_rs_record *out,reader_rs_error *error){
  if(out)std::memset(out,0,sizeof(*out));
  reader_rs_status status=call(error,[&]{
    if(!store||!wire||!out)reject(READER_RS_ARGUMENT,"Missing wire or record output");
    std::string w((const char *)wire,bytes);reader_revision_info info{};validate(store,w,&info);
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
    out->exact=column(q.s,6,&out->exact_size);out->prefix=column(q.s,7,&out->prefix_size);out->suffix=column(q.s,8,&out->suffix_size);
    out->start=(uint64_t)sqlite3_column_int64(q.s,9);out->end=(uint64_t)sqlite3_column_int64(q.s,10);
    out->note_text=column(q.s,11);
    if(present(q.s,12))out->part=(uint64_t)sqlite3_column_int64(q.s,12);
    out->chapter=column(q.s,13);
  });
  if(status!=READER_RS_OK)reader_rs_record_free(out);
  return status;
}
