/* SPDX-License-Identifier: MIT */
#include "reader_projection.h"
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
#include <reader_selector_bytes_detail.h>
#endif
#include <catalog.h>
#include <sqlite3.h>
#include <opds.h>
#include <algorithm>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <memory>
#include <set>
#include <string>
#include <thread>
#include <vector>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <bcrypt.h>
#elif !defined(__APPLE__) && !defined(__ANDROID__)
#include <sys/random.h>
#endif

namespace {
struct failure { reader_revision_status code; const char *message; int database=0; };
[[noreturn]] void reject(reader_revision_status code,const char *message,int database=0) { throw failure{code,message,database}; }
void check(int status) { if(status!=SQLITE_OK) reject(READER_REV_DATABASE,"Product database operation failed",status); }
struct statement {
  sqlite3_stmt *s=nullptr;
  statement(sqlite3 *db,const char *sql) { check(sqlite3_prepare_v2(db,sql,-1,&s,nullptr)); }
  ~statement(){sqlite3_finalize(s);}
  void bind(int index,const std::string &value) { check(sqlite3_bind_text64(s,index,value.data(),value.size(),SQLITE_TRANSIENT,SQLITE_UTF8)); }
  int next() { int status=sqlite3_step(s);if(status!=SQLITE_ROW && status!=SQLITE_DONE) check(status);return status; }
};
std::string text(sqlite3_stmt *s,int index) {
  const unsigned char *value=sqlite3_column_text(s,index);int bytes=sqlite3_column_bytes(s,index);
  return value ? std::string((const char *)value,(size_t)bytes):std::string();
}
void execute(sqlite3 *db,const char *sql) { check(sqlite3_exec(db,sql,nullptr,nullptr,nullptr)); }
int64_t scalar(sqlite3 *db,const char *sql) {
  statement q(db,sql);if(q.next()!=SQLITE_ROW) reject(READER_REV_DATABASE,"Missing product database scalar");return sqlite3_column_int64(q.s,0);
}
struct transaction {
  sqlite3 *db;bool committed=false;
  explicit transaction(sqlite3 *database,const char *begin="BEGIN IMMEDIATE"):db(database){execute(db,begin);}
  ~transaction(){if(!committed) sqlite3_exec(db,"ROLLBACK",nullptr,nullptr,nullptr);}
  void commit(){execute(db,"COMMIT");committed=true;}
};
size_t unicode(const std::string &s) {
  size_t count=0;
  for(size_t i=0;i<s.size();) {
    unsigned a=(unsigned char)s[i++],value=a;size_t n=0;
    if(a==0) reject(READER_REV_FORMAT,"NUL is not allowed in revision text");
    if(a<128) { ++count;continue; }
    if(a>=0xc2 && a<=0xdf){value=a&31;n=1;}
    else if(a>=0xe0 && a<=0xef){value=a&15;n=2;}
    else if(a>=0xf0 && a<=0xf4){value=a&7;n=3;}
    else reject(READER_REV_FORMAT,"Invalid UTF-8 revision text");
    if(n>s.size()-i) reject(READER_REV_FORMAT,"Incomplete UTF-8 revision text");
    for(size_t j=0;j<n;j++){unsigned b=(unsigned char)s[i++];if((b&0xc0)!=0x80)reject(READER_REV_FORMAT,"Invalid UTF-8 revision text");value=(value<<6)|(b&63);}
    if((n==1&&value<128)||(n==2&&value<2048)||(n==3&&value<65536)||value>0x10ffff||(value>=0xd800&&value<=0xdfff))
      reject(READER_REV_FORMAT,"Invalid UTF-8 scalar");
    ++count;
  }
  return count;
}
bool hex(const std::string &s,size_t size) {
  if(s.size()!=size) return false;
  for(char c:s) if(!((c>='0'&&c<='9')||(c>='a'&&c<='f')))return false;
  return true;
}
void identifier(const std::string &s) { if(!hex(s,32))reject(READER_REV_FORMAT,"Invalid global revision/entity ID"); }
std::string book(const std::string &s) {
  size_t colon=s.find(':');std::string format=s.substr(0,colon);
  if(colon==std::string::npos || !hex(s.substr(colon+1),64) ||
    (format!="epub"&&format!="pdf"&&format!="cbz"&&format!="txt"&&format!="html"&&format!="fb2"&&format!="docx"&&format!="rtf"&&format!="mobi"))
    reject(READER_REV_FORMAT,"Invalid global book identity");
  return format;
}
bool kind(const std::string &s){return s=="book"||s=="shelf"||s=="tag"||s=="series"||s=="membership"||s=="progress"||s=="annotation";}
void entity_identity(const std::string &type,const std::string &key){
  if(type=="book"||type=="progress")book(key);
  else if(type=="shelf"||type=="tag"||type=="series")identifier(key);
  else if(type=="annotation"){size_t colon=key.rfind(':');if(colon==std::string::npos)reject(READER_REV_FORMAT,"Invalid annotation identity");book(key.substr(0,colon));identifier(key.substr(colon+1));}
  else {size_t first=key.find(':'),second=key.find(':',first==std::string::npos?0:first+1);if(first==std::string::npos||second==std::string::npos)reject(READER_REV_FORMAT,"Invalid membership identity");std::string group=key.substr(0,first);if(group!="shelf"&&group!="tag"&&group!="series")reject(READER_REV_FORMAT,"Invalid membership kind");identifier(key.substr(first+1,second-first-1));book(key.substr(second+1));}
}
struct value {std::string key,type,atom;std::vector<size_t> children;size_t depth=0;
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
  std::string path{};
#endif
};
struct json {
  std::vector<value> nodes;
  json(sqlite3 *db,const std::string &wire,bool raw=false) {
    unicode(wire);statement valid(db,"SELECT json_valid(?1,1)");valid.bind(1,wire);
    if(valid.next()!=SQLITE_ROW || sqlite3_column_int(valid.s,0)!=1)reject(READER_REV_FORMAT,"Strict JSON is required");
    statement query(db,"SELECT id,parent,key,type,CASE WHEN type IN('object','array') THEN NULL ELSE atom END FROM json_tree(?1)");query.bind(1,wire);
    std::map<int64_t,size_t> ids;
    while(query.next()==SQLITE_ROW) {
      if(nodes.size()>=20000)reject(READER_REV_LIMIT,"Revision JSON value limit exceeded");
      size_t index=nodes.size();value n{text(query.s,2),text(query.s,3),text(query.s,4),{},0};
      if(n.key.size()>128||(!raw&&n.atom.size()>65536))reject(READER_REV_LIMIT,"Revision JSON string limit exceeded");
      if(!raw){unicode(n.key);if(n.type=="text")unicode(n.atom);}
      if(sqlite3_column_type(query.s,1)!=SQLITE_NULL){
        auto parent=ids.find(sqlite3_column_int64(query.s,1));if(parent==ids.end())reject(READER_REV_FORMAT,"Invalid JSON traversal");
        value &p=nodes[parent->second];n.depth=p.depth+1;
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
        if(raw)n.path=p.path+"."+n.key;
#endif
        if(n.depth>=32)reject(READER_REV_LIMIT,"Revision JSON depth limit exceeded");
        if(p.type=="object")for(size_t child:p.children)if(nodes[child].key==n.key)reject(READER_REV_FORMAT,"Duplicate JSON object key");
        p.children.push_back(index);
      }
            size_t atom_limit=65536;
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
      if(raw&&n.type=="text"&&n.path==".payload.location.selector.exact.base64"){
        statement shape(db,"SELECT json_extract(?1,'$.payload.location.anchor_version')=3 AND json_extract(?1,'$.payload.location.mode')='fixed_page'");shape.bind(1,wire);
        if(shape.next()==SQLITE_ROW&&sqlite3_column_int(shape.s,0)==1)atom_limit=87384;
      }
#else
      (void)raw;
#endif
      if(n.atom.size()>atom_limit)reject(READER_REV_LIMIT,"Revision JSON string limit exceeded");
      if(raw){unicode(n.key);if(n.type=="text")unicode(n.atom);}
      ids.emplace(sqlite3_column_int64(query.s,0),index);nodes.push_back(std::move(n));
    }
    if(nodes.empty() || nodes[0].type!="object")reject(READER_REV_FORMAT,"Revision must be an object");
  }
  const value &at(size_t index)const{return nodes[index];}
  size_t field(size_t object,const char *name,bool required=true)const{
    if(at(object).type!="object")reject(READER_REV_FORMAT,"Revision object expected");
    for(size_t i:at(object).children)if(at(i).key==name)return i;
    if(required)reject(READER_REV_FORMAT,"Missing revision field");
    return SIZE_MAX;
  }
  void fields(size_t object,std::initializer_list<const char *> required,std::initializer_list<const char *> optional={})const{
    std::set<std::string> names;for(const char *name:required){field(object,name);names.insert(name);}for(const char *name:optional)names.insert(name);
    for(size_t i:at(object).children)if(!names.count(at(i).key))reject(READER_REV_FORMAT,"Unknown revision field");
  }
  std::string string(size_t index,size_t bytes=65536,size_t scalars=65536,bool nonempty=false)const{
    const value &v=at(index);if(v.type!="text")reject(READER_REV_FORMAT,"Revision string expected");
    if(v.atom.size()>bytes || unicode(v.atom)>scalars)reject(READER_REV_LIMIT,"Revision text limit exceeded");
    if(nonempty && v.atom.empty())reject(READER_REV_FORMAT,"Empty revision field");
    return v.atom;
  }
  uint64_t integer(size_t index)const{
    const value &v=at(index);if(v.type!="integer" || v.atom.empty() || v.atom[0]=='-')reject(READER_REV_FORMAT,"Nonnegative integer expected");
    uint64_t result=0;for(char c:v.atom){if(c<'0'||c>'9'||result>((uint64_t)INT64_MAX-(unsigned)(c-'0'))/10)reject(READER_REV_FORMAT,"Integer exceeds signed storage range");result=result*10+(unsigned)(c-'0');}return result;
  }
};
struct revision {std::string id,kind,key,operation,location,sha,book_key;std::vector<std::string> parents;size_t bytes=0;uint64_t source_bytes=0;};
bool selector(const json &j,size_t index,uint64_t version,const std::string &mode) {
  if(version==2&&mode=="reflow_global")j.fields(index,{"exact","prefix","suffix","start","end","chapter"});
  else j.fields(index,{"exact","prefix","suffix","start","end"});
  std::string exact=j.string(j.field(index,"exact"),65536,65536,version==1);
  j.string(j.field(index,"prefix"),version==2?128:4096,version==2?32:65536);
  j.string(j.field(index,"suffix"),version==2?128:4096,version==2?32:65536);
  uint64_t start=j.integer(j.field(index,"start")),end=j.integer(j.field(index,"end"));if(end<start)reject(READER_REV_FORMAT,"Selector end precedes start");
  if(version==2){
    if(end-start!=exact.size())reject(READER_REV_FORMAT,"Selector span differs from quote bytes");
    if(mode=="reflow_global"){
      size_t chapter=j.field(index,"chapter");if(j.at(chapter).type!="null")j.string(chapter,1024,1024,true);
    }
  }
  return exact.empty();
}
void location(const json &j,size_t index,const revision &r,const std::string &book_key,bool raw) {
  std::string format=book(book_key),mode=j.string(j.field(index,"mode"),16);
  if(mode!=r.location)reject(READER_REV_FORMAT,"Location mode differs from revision envelope");
  uint64_t version=j.integer(j.field(index,"anchor_version"));
  if(version!=1&&version!=2&&!(raw&&version==3&&mode=="fixed_page"))reject(READER_REV_FORMAT,"Unsupported anchor version");
  if(mode=="epub_chapter"&&version==2)j.fields(index,{"mode","parser_version","anchor_version","part_path","part","selector"});
  else if(mode=="epub_chapter")j.fields(index,{"mode","parser_version","anchor_version","part_path","selector"});
  else if(mode=="reflow_global")j.fields(index,{"mode","parser_version","anchor_version","selector"});
  else if(mode=="fixed_page")j.fields(index,{"mode","parser_version","anchor_version","page_id","page","selector"});
  else reject(READER_REV_FORMAT,"Unknown reading location mode");
  j.string(j.field(index,"parser_version"),64,64,true);
  if((mode=="fixed_page")!=(format=="pdf"||format=="cbz") || (mode=="epub_chapter"&&format!="epub"))reject(READER_REV_FORMAT,"Book format and reading location disagree");
  if(mode=="epub_chapter")j.string(j.field(index,"part_path"),1024,1024,true);
  if(mode=="epub_chapter"&&version==2)j.integer(j.field(index,"part"));
  if(mode=="fixed_page"){j.string(j.field(index,"page_id"),256,256,true);j.integer(j.field(index,"page"));}
    bool point=false;
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
  if(version==3){
    size_t s=j.field(index,"selector");j.fields(s,{"exact","prefix","suffix","start","end"});
    auto bytes=[&](const char *name,size_t limit,size_t scalars){
      size_t item=j.field(s,name);j.fields(item,{"base64","size"});uint64_t count=j.integer(j.field(item,"size"));
      if(count>limit)reject(READER_REV_LIMIT,"Raw selector byte limit exceeded");
      size_t data=j.field(item,"base64");if(j.at(data).type=="null"){if(count)reject(READER_REV_FORMAT,"NULL raw selector has bytes");return count;}
      if(j.at(data).type!="text")reject(READER_REV_FORMAT,"Raw selector Base64 must be text or null");
      std::string decoded;auto status=reader_selector_bytes_detail::decode(j.at(data).atom,(size_t)count,limit,scalars,decoded);
      if(status!=reader_selector_bytes_detail::result::ok)reject(status==reader_selector_bytes_detail::result::limit?READER_REV_LIMIT:READER_REV_FORMAT,"Invalid raw selector Base64 or UTF-8");
      return count;
    };
    uint64_t exact=bytes("exact",65536,SIZE_MAX);bytes("prefix",128,32);bytes("suffix",128,32);
    uint64_t start=j.integer(j.field(s,"start")),end=j.integer(j.field(s,"end"));
    if(end<start||end-start!=exact)reject(READER_REV_FORMAT,"Raw selector span differs from bytes");
    point=exact==0;
  }else
#endif
  point=selector(j,j.field(index,"selector"),version,mode);
  if(version>=2&&r.kind=="progress"&&!point)reject(READER_REV_FORMAT,"Progress requires a point selector");
}
revision parse(sqlite3 *db,const std::string &wire,const char *expected,bool raw=false) {
  if(wire.size()<2 || wire.size()>READER_REVISION_MAX_BYTES)reject(READER_REV_LIMIT,"Revision byte limit exceeded");
  json j(db,wire,raw);j.fields(0,{"version","id","entity_kind","entity_key","operation","location_kind","parents","payload"},{"display_time"});
  if(j.integer(j.field(0,"version"))!=1)reject(READER_REV_FORMAT,"Unsupported revision version");
  revision r;r.bytes=wire.size();r.id=j.string(j.field(0,"id"),32);identifier(r.id);
  r.kind=j.string(j.field(0,"entity_kind"),16);r.key=j.string(j.field(0,"entity_key"),256,256,true);if(!kind(r.kind))reject(READER_REV_FORMAT,"Unknown revision entity");
  r.operation=j.string(j.field(0,"operation"),8);if(r.operation!="put"&&r.operation!="delete"&&r.operation!="restore")reject(READER_REV_FORMAT,"Unknown revision operation");
  r.location=j.string(j.field(0,"location_kind"),16);
  bool reading=r.kind=="progress"||r.kind=="annotation";
  if(reading ? (r.location!="epub_chapter"&&r.location!="reflow_global"&&r.location!="fixed_page"):r.location!="none")reject(READER_REV_FORMAT,"Explicit location kind is required");
  size_t time=j.field(0,"display_time",false);if(time!=SIZE_MAX)j.string(time,128,128);
  size_t parents=j.field(0,"parents");if(j.at(parents).type!="array")reject(READER_REV_FORMAT,"Parent array expected");
  if(j.at(parents).children.size()>READER_REVISION_MAX_PARENTS)reject(READER_REV_LIMIT,"Parent set limit exceeded");
  std::set<std::string> seen;
  for(size_t p:j.at(parents).children){std::string id=j.string(p,32);identifier(id);if(id==r.id)reject(READER_REV_CYCLE,"A revision cannot parent itself");if(!seen.insert(id).second)reject(READER_REV_FORMAT,"Duplicate parent ID");r.parents.push_back(id);}
  entity_identity(r.kind,r.key);
  if(reading){std::string key=r.kind=="progress"?r.key:r.key.substr(0,r.key.rfind(':'));std::string format=book(key);if((r.location=="fixed_page")!=(format=="pdf"||format=="cbz")||(r.location=="epub_chapter"&&format!="epub"))reject(READER_REV_FORMAT,"Envelope location and book format disagree");}
  if(r.kind=="book"||r.kind=="progress")r.book_key=r.key;
  else if(r.kind=="annotation")r.book_key=r.key.substr(0,r.key.rfind(':'));
  else if(r.kind=="membership")r.book_key=r.key.substr(r.key.find(':',r.key.find(':')+1)+1);
  size_t payload=j.field(0,"payload");
  if(r.operation=="delete") {if(j.at(payload).type!="null")reject(READER_REV_FORMAT,"Delete payload must be null");}
  else if(r.kind=="book") {
    j.fields(payload,{"format","source_sha256","source_bytes","title","author","favorite"});
    std::string format=j.string(j.field(payload,"format"),8),sha=j.string(j.field(payload,"source_sha256"),64);
    r.source_bytes=j.integer(j.field(payload,"source_bytes"));
    if(format+":"+sha!=r.key || !r.source_bytes)reject(READER_REV_FORMAT,"Immutable original identity mismatch");
    j.string(j.field(payload,"title"),16384,4096);j.string(j.field(payload,"author"),16384,4096);
    if(j.at(j.field(payload,"favorite")).type!="true"&&j.at(j.field(payload,"favorite")).type!="false")reject(READER_REV_FORMAT,"Favorite must be boolean");
  } else if(r.kind=="tag"||r.kind=="series") {j.fields(payload,{"name"});j.string(j.field(payload,"name"),1024,256,true);}
  else if(r.kind=="shelf") {
    j.fields(payload,{"name","parent_id","ordinal"});j.string(j.field(payload,"name"),1024,256,true);j.integer(j.field(payload,"ordinal"));
    size_t parent=j.field(payload,"parent_id");if(j.at(parent).type!="null")identifier(j.string(parent,32));
  } else if(r.kind=="membership") {
    j.fields(payload,{"book_key","collection_kind","collection_id","ordinal"});std::string b=j.string(j.field(payload,"book_key"),72),group=j.string(j.field(payload,"collection_kind"),8),id=j.string(j.field(payload,"collection_id"),32);
    book(b);identifier(id);if(group+":"+id+":"+b!=r.key)reject(READER_REV_FORMAT,"Membership payload identity mismatch");j.integer(j.field(payload,"ordinal"));
  } else {
    if(r.kind=="progress")j.fields(payload,{"book_key","location"});else j.fields(payload,{"book_key","annotation_id","location","text"});
    std::string b=j.string(j.field(payload,"book_key"),72);book(b);
    if(r.kind=="progress") {if(b!=r.key)reject(READER_REV_FORMAT,"Progress book identity mismatch");}
    else {std::string id=j.string(j.field(payload,"annotation_id"),32);identifier(id);if(b+":"+id!=r.key)reject(READER_REV_FORMAT,"Annotation identity mismatch");j.string(j.field(payload,"text"),65536);}
    location(j,j.field(payload,"location"),r,b,raw);
  }
  char hash[65];opds_sha256_hex(wire.data(),wire.size(),hash);r.sha=hash;
  if(expected && (!hex(expected,64)||r.sha!=expected))reject(READER_REV_HASH,"Revision transport SHA-256 mismatch");
  return r;
}
void info(const revision &r,reader_revision_info *out) {
  if(!out)return;
  std::memset(out,0,sizeof(*out));
  std::memcpy(out->revision_id,r.id.c_str(),r.id.size());std::memcpy(out->entity_kind,r.kind.c_str(),r.kind.size());std::memcpy(out->entity_key,r.key.c_str(),r.key.size());
  std::memcpy(out->operation,r.operation.c_str(),r.operation.size());std::memcpy(out->location_kind,r.location.c_str(),r.location.size());std::memcpy(out->sha256,r.sha.c_str(),r.sha.size());out->bytes=r.bytes;out->parent_count=r.parents.size();
  std::memcpy(out->book_key,r.book_key.c_str(),r.book_key.size());out->source_bytes=r.source_bytes;
}
}

struct reader_revisions {const bool raw_v3;explicit reader_revisions(bool raw=false):raw_v3(raw){} sqlite3 *db=nullptr;std::thread::id owner=std::this_thread::get_id();bool active=false;};

namespace {
struct guard {
  reader_revisions *store;
  explicit guard(reader_revisions *s,bool raw_api=false):store(s){if(s&&s->raw_v3!=raw_api)reject(READER_REV_ARGUMENT,"Use the explicit API matching this store capability");if(!s||s->owner!=std::this_thread::get_id()||s->active)reject(READER_REV_OWNER,"Revision store requires its creating worker without reentry");s->active=true;}
  ~guard(){store->active=false;}
};
struct graph_node {std::string id,operation,sha;std::vector<std::string> parents;size_t pending=0;bool complete=true,blocked=false,head=true;};
struct graph {
  sqlite3 *db;std::map<std::string,graph_node> nodes;reader_revision_state state{};uint64_t original_bytes=0;
  graph(sqlite3 *database,const std::string &kind,const std::string &key,bool raw=false):db(database){
    statement q(db,"SELECT revision_id,operation,body_sha256,body_json FROM reader_revisions WHERE entity_kind=?1 AND entity_key=?2 ORDER BY revision_id");q.bind(1,kind);q.bind(2,key);
    while(q.next()==SQLITE_ROW){
      if(nodes.size()>=READER_REVISION_MAX_ENTITY_HISTORY)reject(READER_REV_LIMIT,"Entity revision history limit exceeded");
      std::string wire=text(q.s,3);revision r=parse(db,wire,text(q.s,2).c_str(),raw);
      if(r.id!=text(q.s,0)||r.operation!=text(q.s,1)||r.kind!=kind||r.key!=key)reject(READER_REV_HASH,"Retained revision columns differ from wire bytes");
      if(r.source_bytes){if(original_bytes&&original_bytes!=r.source_bytes)reject(READER_REV_FORMAT,"Revision changes immutable original byte length");original_bytes=r.source_bytes;}
      graph_node n;n.id=r.id;n.operation=r.operation;n.sha=r.sha;n.parents=std::move(r.parents);nodes.emplace(r.id,std::move(n));
    }
    std::set<std::string> missing,foreign;
    std::map<std::string,std::vector<graph_node *>> children;
    for(auto &pair:nodes)for(const std::string &p:pair.second.parents){
      auto parent=nodes.find(p);if(parent!=nodes.end()){parent->second.head=false;++pair.second.pending;children[p].push_back(&pair.second);}
      else {statement known(db,"SELECT 1 FROM reader_revisions WHERE revision_id=?1");known.bind(1,p);if(known.next()==SQLITE_ROW)foreign.insert(p);else missing.insert(p);}
    }
    std::vector<graph_node *> ready;for(auto &pair:nodes)if(!pair.second.pending)ready.push_back(&pair.second);
    size_t processed=0;
    while(processed<ready.size()){
      graph_node &n=*ready[processed++];bool deleted_parent=false,direct_tombstone=false;
      for(const std::string &id:n.parents){auto p=nodes.find(id);if(p==nodes.end()){n.complete=false;continue;}n.complete=n.complete&&p->second.complete;deleted_parent=deleted_parent||p->second.operation=="delete"||p->second.blocked;direct_tombstone=direct_tombstone||p->second.operation=="delete";}
      if(n.operation=="put")n.blocked=deleted_parent;
      if(n.operation=="restore")n.blocked=!direct_tombstone;
      for(graph_node *child:children[n.id])if(--child->pending==0)ready.push_back(child);
    }
    if(processed!=nodes.size())reject(READER_REV_CYCLE,"Revision causal cycle refused");
    state.revisions=nodes.size();state.missing_parents=missing.size();state.foreign_parents=foreign.size();
    graph_node *only=nullptr;for(auto &pair:nodes)if(pair.second.head){++state.heads;only=&pair.second;if(pair.second.blocked)state.requires_restore=1;}
    state.projection_safe=state.heads==1&&only&&only->complete&&!only->blocked&&!state.missing_parents&&!state.foreign_parents;
    state.deleted=state.projection_safe&&only->operation=="delete";
  }
};
std::string wire_input(const void *bytes,size_t size){if(!bytes||size<2||size>READER_REVISION_MAX_BYTES)reject(READER_REV_LIMIT,"Revision byte limit exceeded");return std::string((const char *)bytes,size);}
revision retained(reader_revisions *store,const std::string &id,std::string *body=nullptr){
  identifier(id);statement q(store->db,"SELECT body_json,body_sha256,entity_kind,entity_key,operation FROM reader_revisions WHERE revision_id=?1");q.bind(1,id);
  if(q.next()!=SQLITE_ROW)reject(READER_REV_NOT_FOUND,"Revision not found");
  std::string wire=text(q.s,0);revision r=parse(store->db,wire,text(q.s,1).c_str(),store->raw_v3);
  if(r.id!=id||r.kind!=text(q.s,2)||r.key!=text(q.s,3)||r.operation!=text(q.s,4))reject(READER_REV_HASH,"Retained revision identity mismatch");
  if(body)*body=std::move(wire);
  return r;
}
bool already_retained(reader_revisions *store,const revision &r,const std::string &wire){
  {
    statement existing(store->db,"SELECT body_json,body_sha256,entity_kind,entity_key,operation FROM reader_revisions WHERE revision_id=?1");existing.bind(1,r.id);
    if(existing.next()==SQLITE_ROW){
      if(text(existing.s,0)!=wire||text(existing.s,1)!=r.sha||text(existing.s,2)!=r.kind||text(existing.s,3)!=r.key||text(existing.s,4)!=r.operation)reject(READER_REV_COLLISION,"Revision ID is already bound to different bytes");
      return true;
    }
  }
  return false;
}
bool store_revision(reader_revisions *store,const revision &r,const std::string &wire,bool local){
  if(already_retained(store,r,wire))return false;
  for(const std::string &id:r.parents){statement parent(store->db,"SELECT entity_kind,entity_key FROM reader_revisions WHERE revision_id=?1");parent.bind(1,id);
    if(parent.next()==SQLITE_ROW){if(text(parent.s,0)!=r.kind||text(parent.s,1)!=r.key)reject(READER_REV_FORMAT,"Parent belongs to a different entity");}
    else if(local)reject(READER_REV_MISSING_PARENT,"Local parent has not been received");
  }
  {
    statement insert(store->db,"INSERT INTO reader_revisions(revision_id,entity_kind,entity_key,operation,body_json,body_sha256) VALUES(?1,?2,?3,?4,?5,?6)");
    insert.bind(1,r.id);insert.bind(2,r.kind);insert.bind(3,r.key);insert.bind(4,r.operation);insert.bind(5,wire);insert.bind(6,r.sha);insert.next();
  }
  graph checked(store->db,r.kind,r.key,store->raw_v3);(void)checked;
  if(local){statement enqueue(store->db,"INSERT INTO reader_outbox(revision_id) VALUES(?1)");enqueue.bind(1,r.id);enqueue.next();}
  return true;
}
void commit(reader_revisions *store,const std::string &wire,bool local,const char *expected,reader_revision_info *output,int *created){
  revision r=parse(store->db,wire,expected,store->raw_v3);transaction tx(store->db);
  bool inserted=store_revision(store,r,wire,local);tx.commit();if(inserted&&created)*created=1;info(r,output);
}
std::set<std::string> head_ids(const graph &g){std::set<std::string> ids;for(const auto &pair:g.nodes)if(pair.second.head)ids.insert(pair.first);return ids;}
std::string safe_head(const graph &g){if(!g.state.projection_safe)reject(READER_REV_UNSAFE,"Entity has no complete safe unique head");return *head_ids(g).begin();}
reader_selection_kind selection_kind(const graph &g){
  if(!g.state.heads)return READER_SELECTION_MISSING;
  if(g.state.missing_parents||g.state.foreign_parents)return READER_SELECTION_PENDING_PARENTS;
  if(g.state.heads>1)return READER_SELECTION_CONCURRENT;
  return g.state.projection_safe?READER_SELECTION_SAFE:READER_SELECTION_BLOCKED_RESTORE;
}
void selected_payload(reader_revisions *store,const char *type,const std::string &key,reader_revision_selection &selection,reader_revision_info &out,std::string &body){
  graph current(store->db,type,key,store->raw_v3);selection.graph=current.state;selection.kind=selection_kind(current);
  if(selection.kind==READER_SELECTION_SAFE){revision r=retained(store,safe_head(current),&body);info(r,&out);}
}
bool product_exists(sqlite3 *db,const std::string &table,const std::string &column,const std::string &key,bool active=false){
  std::string sql="SELECT 1 FROM "+table+" WHERE "+column+"=?1"+(active?" AND deleted=0":"");statement q(db,sql.c_str());q.bind(1,key);return q.next()==SQLITE_ROW;
}
void require_active(sqlite3 *db,const std::string &table,const std::string &column,const std::string &key){
  if(!product_exists(db,table,column,key,true))reject(READER_REV_UNSAFE,"Referenced product metadata has not become active");
}
void apply_product(reader_revisions *store,const revision &r,const std::string &wire,const char *sort_title){
  if(r.kind=="progress"||r.kind=="annotation")reject(READER_REV_ARGUMENT,"Reading entities use selected payloads, not metadata or SDK writes");
  json j(store->db,wire);size_t payload=j.field(0,"payload");bool deleted=r.operation=="delete";
  if(r.kind=="book"){
    graph history(store->db,"book",r.key,store->raw_v3);uint64_t bytes=history.original_bytes;
    if(!bytes)reject(READER_REV_UNSAFE,"Original book metadata has not arrived");
    bool exists=product_exists(store->db,"reader_books","book_key",r.key);
    if(exists){statement known(store->db,"SELECT source_bytes FROM reader_books WHERE book_key=?1");known.bind(1,r.key);known.next();if((uint64_t)sqlite3_column_int64(known.s,0)!=bytes)reject(READER_REV_FORMAT,"Product original identity differs from revision history");}
    std::string title,author,sort;int favorite=0;
    if(!deleted){if(!sort_title)reject(READER_REV_ARGUMENT,"Host NFC book sort title is required");sort=sort_title;
      if(sort.size()>16384||unicode(sort)>4096)reject(READER_REV_LIMIT,"Host book sort title exceeds its limit");
      title=j.string(j.field(payload,"title"));author=j.string(j.field(payload,"author"));favorite=j.at(j.field(payload,"favorite")).type=="true";
    }
    if(deleted&&exists){statement q(store->db,"UPDATE reader_books SET deleted=1 WHERE book_key=?1");q.bind(1,r.key);q.next();return;}
    statement q(store->db,exists?"UPDATE reader_books SET title=?2,author=?3,sort_title=?4,favorite=?5,deleted=0 WHERE book_key=?1":
      "INSERT INTO reader_books(book_key,title,author,sort_title,favorite,deleted,format,source_sha256,source_bytes) VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9)");
    q.bind(1,r.key);q.bind(2,title);q.bind(3,author);q.bind(4,sort);check(sqlite3_bind_int(q.s,5,favorite));
    if(!exists){size_t colon=r.key.find(':');check(sqlite3_bind_int(q.s,6,deleted));q.bind(7,r.key.substr(0,colon));q.bind(8,r.key.substr(colon+1));check(sqlite3_bind_int64(q.s,9,(sqlite3_int64)bytes));}q.next();return;
  }
  if(r.kind=="shelf"||r.kind=="tag"||r.kind=="series"){
    std::string table=r.kind=="shelf"?"reader_shelves":r.kind=="tag"?"reader_tags":"reader_series";
    std::string column=r.kind=="shelf"?"shelf_id":r.kind=="tag"?"tag_id":"series_id";
    bool exists=product_exists(store->db,table,column,r.key);std::string name=deleted?r.key:j.string(j.field(payload,"name"));
    if(deleted&&exists){std::string sql="UPDATE "+table+" SET deleted=1 WHERE "+column+"=?1";statement q(store->db,sql.c_str());q.bind(1,r.key);q.next();return;}
    std::string sql=exists?"UPDATE "+table+" SET name=?2,deleted=?3":"INSERT INTO "+table+"("+column+",name,deleted";
    if(r.kind=="shelf"){
      std::string parent;uint64_t ordinal=0;bool has_parent=false;
      if(!deleted){size_t index=j.field(payload,"parent_id");has_parent=j.at(index).type!="null";if(has_parent){parent=j.string(index);require_active(store->db,"reader_shelves","shelf_id",parent);}ordinal=j.integer(j.field(payload,"ordinal"));}
      sql+=exists?",parent_id=?4,ordinal=?5 WHERE shelf_id=?1":",parent_id,ordinal) VALUES(?1,?2,?3,?4,?5)";
      statement q(store->db,sql.c_str());q.bind(1,r.key);q.bind(2,name);check(sqlite3_bind_int(q.s,3,deleted));if(has_parent)q.bind(4,parent);else check(sqlite3_bind_null(q.s,4));check(sqlite3_bind_int64(q.s,5,(sqlite3_int64)ordinal));q.next();
    }else{
      sql+=exists?" WHERE "+column+"=?1":") VALUES(?1,?2,?3)";statement q(store->db,sql.c_str());q.bind(1,r.key);q.bind(2,name);check(sqlite3_bind_int(q.s,3,deleted));q.next();
    }return;
  }
  size_t first=r.key.find(':'),second=r.key.find(':',first+1);std::string group=r.key.substr(0,first),id=r.key.substr(first+1,second-first-1),book_key=r.key.substr(second+1);
  std::string table=group=="shelf"?"reader_book_shelves":group=="tag"?"reader_book_tags":"reader_book_series";
  std::string column=group=="shelf"?"shelf_id":group=="tag"?"tag_id":"series_id";
  if(deleted){std::string sql="DELETE FROM "+table+" WHERE "+column+"=?1 AND book_key=?2";statement q(store->db,sql.c_str());q.bind(1,id);q.bind(2,book_key);q.next();return;}
  require_active(store->db,"reader_books","book_key",book_key);require_active(store->db,group=="shelf"?"reader_shelves":group=="tag"?"reader_tags":"reader_series",column,id);
  std::string where=" WHERE "+column+"=?1 AND book_key=?2",lookup="SELECT 1 FROM "+table+where;statement found(store->db,lookup.c_str());found.bind(1,id);found.bind(2,book_key);bool exists=found.next()==SQLITE_ROW;
  if(group=="tag"&&exists)return;
  std::string sql=exists?"UPDATE "+table+" SET ordinal=?3"+where:"INSERT INTO "+table+"("+column+",book_key"+(group=="tag"?") VALUES(?1,?2)":",ordinal) VALUES(?1,?2,?3)");
  statement q(store->db,sql.c_str());q.bind(1,id);q.bind(2,book_key);if(group!="tag")check(sqlite3_bind_int64(q.s,3,(sqlite3_int64)j.integer(j.field(payload,"ordinal"))));q.next();
}
reader_revision_status report(reader_revision_error *e,const failure &f){if(e){e->code=f.code;e->sqlite_code=f.database;std::snprintf(e->message,sizeof(e->message),"%s",f.message);}return f.code;}
template<class Function>reader_revision_status call(reader_revision_error *e,Function function){if(e)std::memset(e,0,sizeof(*e));try{function();return READER_REV_OK;}catch(const failure &f){return report(e,f);}catch(...){return report(e,{READER_REV_MEMORY,"Cannot allocate bounded revision state"});}}
}

static reader_revision_status reader_revisions_open_impl(bool raw_api,const char *path,reader_revisions **out,reader_revision_error *error){
  if(out)*out=nullptr;
  return call(error,[&]{
    if(!path||!*path||!out)reject(READER_REV_ARGUMENT,"Missing product catalog path/output");
    unicode(path);
    std::unique_ptr<reader_revisions> store(new reader_revisions(raw_api));
    int status=sqlite3_open_v2(path,&store->db,SQLITE_OPEN_READWRITE|SQLITE_OPEN_CREATE|SQLITE_OPEN_FULLMUTEX,nullptr);
    if(status!=SQLITE_OK){if(store->db)sqlite3_close_v2(store->db);store->db=nullptr;check(status);}
    try{
      check(sqlite3_extended_result_codes(store->db,1));check(sqlite3_busy_timeout(store->db,5000));execute(store->db,"PRAGMA foreign_keys=ON; PRAGMA trusted_schema=OFF; PRAGMA synchronous=FULL;");
      int64_t identity=scalar(store->db,"PRAGMA application_id"),version=scalar(store->db,"PRAGMA user_version");
      if(identity!=1163416144||(version!=1&&version!=2&&version!=3)){if(identity||version||scalar(store->db,"SELECT count(*) FROM sqlite_master WHERE name NOT GLOB 'sqlite_*'"))reject(READER_REV_DATABASE,"Foreign product catalog identity/version");execute(store->db,reader_catalog_migration(nullptr));}
      version=scalar(store->db,"PRAGMA user_version");
      if(scalar(store->db,"PRAGMA application_id")!=1163416144||(version!=1&&version!=2&&version!=3)||scalar(store->db,"PRAGMA foreign_keys")!=1)reject(READER_REV_DATABASE,"Product catalog contract was not established");
      if(scalar(store->db,"SELECT json_valid('{\"version\":1}',1)")!=1||scalar(store->db,"SELECT count(*) FROM json_tree('[1]')")!=2)reject(READER_REV_DATABASE,"Installed product SQLite lacks required strict JSON support");
      statement schema(store->db,"SELECT revision_id,body_json,body_sha256 FROM reader_revisions LIMIT 0");schema.next();
    }catch(...){sqlite3_exec(store->db,"ROLLBACK",nullptr,nullptr,nullptr);sqlite3_close_v2(store->db);store->db=nullptr;throw;}
    *out=store.release();
  });
}
extern "C" reader_revision_status reader_revisions_close(reader_revisions **pointer,reader_revision_error *error){return call(error,[&]{
  if(!pointer)reject(READER_REV_ARGUMENT,"Missing revision store output");
  if(!*pointer)return;
  reader_revisions *store=*pointer;if(store->owner!=std::this_thread::get_id()||store->active)reject(READER_REV_OWNER,"Revision store requires its creating worker without reentry");check(sqlite3_close(store->db));delete store;*pointer=nullptr;
});}
extern "C" reader_revision_status reader_revision_new_id(char out[33],reader_revision_error *error){return call(error,[&]{
  if(!out)reject(READER_REV_ARGUMENT,"Missing revision ID output");
  out[0]=0;unsigned char bytes[16];
#ifdef _WIN32
  if(BCryptGenRandom(nullptr,bytes,sizeof(bytes),BCRYPT_USE_SYSTEM_PREFERRED_RNG)<0)reject(READER_REV_DATABASE,"System random ID generation failed");
#elif defined(__ANDROID__) || defined(__APPLE__)
  /* Public OS CSPRNG on Apple and Bionic (Android minSdk 26). */
  arc4random_buf(bytes,sizeof(bytes));
#else
  size_t used=0;while(used<sizeof(bytes)){ssize_t got=getrandom(bytes+used,sizeof(bytes)-used,0);if(got<0&&errno==EINTR)continue;if(got<=0)reject(READER_REV_DATABASE,"System random ID generation failed");used+=(size_t)got;}
#endif
  bytes[6]=(unsigned char)((bytes[6]&15)|64);bytes[8]=(unsigned char)((bytes[8]&63)|128);const char *hex="0123456789abcdef";
  for(size_t i=0;i<sizeof(bytes);i++){out[i*2]=hex[bytes[i]>>4];out[i*2+1]=hex[bytes[i]&15];}out[32]=0;
});}
static reader_revision_status reader_revision_validate_impl(bool raw_api,reader_revisions *store,const void *bytes,size_t count,const char *expected,reader_revision_info *out,reader_revision_error *error){if(out)std::memset(out,0,sizeof(*out));return call(error,[&]{guard owner(store,raw_api);revision r=parse(store->db,wire_input(bytes,count),expected,store->raw_v3);info(r,out);});}
static reader_revision_status reader_revision_local_impl(bool raw_api,reader_revisions *store,const void *bytes,size_t count,reader_revision_info *out,int *created,reader_revision_error *error){if(created)*created=0;if(out)std::memset(out,0,sizeof(*out));return call(error,[&]{guard owner(store,raw_api);commit(store,wire_input(bytes,count),true,nullptr,out,created);});}
static reader_revision_status reader_revision_receive_impl(bool raw_api,reader_revisions *store,const void *bytes,size_t count,const char *expected,reader_revision_info *out,int *created,reader_revision_error *error){if(created)*created=0;if(out)std::memset(out,0,sizeof(*out));return call(error,[&]{guard owner(store,raw_api);if(!expected)reject(READER_REV_ARGUMENT,"Remote transport SHA-256 is required");commit(store,wire_input(bytes,count),false,expected,out,created);});}
static reader_revision_status reader_revision_get_impl(bool raw_api,reader_revisions *store,const char *id,char **wire,size_t *bytes,reader_revision_info *out,reader_revision_error *error){if(wire)*wire=nullptr;if(bytes)*bytes=0;if(out)std::memset(out,0,sizeof(*out));return call(error,[&]{
  guard owner(store,raw_api);if(!id||!wire||!bytes)reject(READER_REV_ARGUMENT,"Missing revision lookup output");std::string body;revision r=retained(store,id,&body);char *copy=(char *)std::malloc(body.size()+1);if(!copy)throw std::bad_alloc();std::memcpy(copy,body.data(),body.size());copy[body.size()]=0;*wire=copy;*bytes=body.size();info(r,out);
});}
extern "C" void reader_revision_bytes_free(void *bytes){std::free(bytes);}
static reader_revision_status reader_revision_heads_impl(bool raw_api,reader_revisions *store,const char *entity_kind,const char *entity_key,reader_revision_head_fn visit,void *context,reader_revision_state *out,reader_revision_error *error){if(out)std::memset(out,0,sizeof(*out));return call(error,[&]{
  guard owner(store,raw_api);if(!entity_kind||!entity_key||!kind(entity_kind)||!out)reject(READER_REV_ARGUMENT,"Missing revision entity query");graph g(store->db,entity_kind,entity_key,store->raw_v3);*out=g.state;
  if(visit)for(const auto &pair:g.nodes)if(pair.second.head){reader_revision_head head{};std::memcpy(head.revision_id,pair.first.c_str(),32);std::memcpy(head.operation,pair.second.operation.c_str(),pair.second.operation.size());std::memcpy(head.sha256,pair.second.sha.c_str(),64);head.complete=pair.second.complete;head.requires_restore=pair.second.blocked;if(visit(context,&head))break;}
});}
static reader_revision_status reader_revision_book_identity_impl(bool raw_api,reader_revisions *store,const char *key,uint64_t *bytes,reader_revision_error *error){
  if(bytes)*bytes=0;
  return call(error,[&]{guard owner(store,raw_api);if(!key||!bytes)reject(READER_REV_ARGUMENT,"Missing global book identity/output");book(key);graph g(store->db,"book",key,store->raw_v3);if(!g.original_bytes)reject(READER_REV_NOT_FOUND,"Verified original book metadata has not arrived");*bytes=g.original_bytes;});
}
static reader_revision_status reader_revision_local_project_impl(bool raw_api,reader_revisions *store,const void *bytes,size_t count,const char *const *expected,size_t expected_count,const char *sort_title,reader_revision_info *out,int *created,int *applied,reader_revision_error *error){
  if(created)*created=0;
  if(applied)*applied=0;
  if(out)std::memset(out,0,sizeof(*out));
  return call(error,[&]{guard owner(store,raw_api);if(expected_count>32||(expected_count&&!expected))reject(READER_REV_ARGUMENT,"Expected head set must contain at most 32 IDs");
    std::string wire=wire_input(bytes,count);revision r=parse(store->db,wire,nullptr,store->raw_v3);transaction tx(store->db);
    if(already_retained(store,r,wire)){tx.commit();info(r,out);return;}
    std::set<std::string> observed;for(size_t n=0;n<expected_count;n++){if(!expected[n])reject(READER_REV_ARGUMENT,"Missing expected head ID");identifier(expected[n]);if(!observed.insert(expected[n]).second)reject(READER_REV_ARGUMENT,"Duplicate expected head ID");}
    graph before(store->db,r.kind,r.key,store->raw_v3);std::set<std::string> parents(r.parents.begin(),r.parents.end());
    if(head_ids(before)!=observed||parents!=observed)reject(READER_REV_UNSAFE,"Expected heads or new parent set differs from current history");
    store_revision(store,r,wire,true);graph after(store->db,r.kind,r.key,store->raw_v3);
    if(safe_head(after)!=r.id)reject(READER_REV_UNSAFE,"Local revision did not form a complete safe unique head");
    apply_product(store,r,wire,sort_title);tx.commit();info(r,out);if(created)*created=1;if(applied)*applied=1;
  });
}
static reader_revision_status reader_revision_local_reading_impl(bool raw_api,reader_revisions *store,const void *bytes,size_t count,const char *const *expected,size_t expected_count,reader_revision_info *out,int *created,reader_revision_error *error){
  if(created)*created=0;
  if(out)std::memset(out,0,sizeof(*out));
  return call(error,[&]{guard owner(store,raw_api);if(expected_count>32||(expected_count&&!expected))reject(READER_REV_ARGUMENT,"Expected head set must contain at most 32 IDs");
    std::string wire=wire_input(bytes,count);revision r=parse(store->db,wire,nullptr,store->raw_v3);
    if(r.kind!="progress"&&r.kind!="annotation")reject(READER_REV_ARGUMENT,"Reading transaction requires progress or annotation");
    transaction tx(store->db);
    if(already_retained(store,r,wire)){tx.commit();info(r,out);return;}
    std::set<std::string> observed;for(size_t n=0;n<expected_count;n++){if(!expected[n])reject(READER_REV_ARGUMENT,"Missing expected head ID");identifier(expected[n]);if(!observed.insert(expected[n]).second)reject(READER_REV_ARGUMENT,"Duplicate expected head ID");}
    graph before(store->db,r.kind,r.key,store->raw_v3);std::set<std::string> parents(r.parents.begin(),r.parents.end());
    if(head_ids(before)!=observed||parents!=observed)reject(READER_REV_UNSAFE,"Expected heads or new parent set differs from current history");
    graph original(store->db,"book",r.book_key,store->raw_v3);if(!original.original_bytes)reject(READER_REV_NOT_FOUND,"Verified original book metadata has not arrived");
    store_revision(store,r,wire,true);graph after(store->db,r.kind,r.key,store->raw_v3);
    if(safe_head(after)!=r.id)reject(READER_REV_UNSAFE,"Reading revision did not form a complete safe unique head");
    tx.commit();info(r,out);if(created)*created=1;
  });
}
static reader_revision_status reader_revision_project_impl(bool raw_api,reader_revisions *store,const char *entity_kind,const char *entity_key,const char *expected,const char *sort_title,reader_revision_info *out,reader_revision_error *error){
  if(out)std::memset(out,0,sizeof(*out));
  return call(error,[&]{guard owner(store,raw_api);if(!entity_kind||!entity_key||!expected||!kind(entity_kind))reject(READER_REV_ARGUMENT,"Missing restricted product projection identity");identifier(expected);transaction tx(store->db);
    graph current(store->db,entity_kind,entity_key,store->raw_v3);if(safe_head(current)!=expected)reject(READER_REV_UNSAFE,"Expected safe head changed before metadata projection");
    std::string wire;revision r=retained(store,expected,&wire);apply_product(store,r,wire,sort_title);tx.commit();info(r,out);
  });
}
static reader_revision_status reader_revision_selected_impl(bool raw_api,reader_revisions *store,const char *entity_kind,const char *entity_key,char **wire,size_t *bytes,reader_revision_info *out,reader_revision_selection *selection,reader_revision_error *error){
  if(wire)*wire=nullptr;
  if(bytes)*bytes=0;
  if(out)std::memset(out,0,sizeof(*out));
  if(selection)std::memset(selection,0,sizeof(*selection));
  return call(error,[&]{guard owner(store,raw_api);if(!entity_kind||!entity_key||!kind(entity_kind)||!wire||!bytes||!selection)reject(READER_REV_ARGUMENT,"Missing selected revision output");transaction tx(store->db,"BEGIN");
    graph current(store->db,entity_kind,entity_key,store->raw_v3);selection->graph=current.state;
    if(!current.state.heads){selection->kind=READER_SELECTION_MISSING;reject(READER_REV_NOT_FOUND,"No revision history exists for the entity");}
    if(current.state.missing_parents||current.state.foreign_parents){selection->kind=READER_SELECTION_PENDING_PARENTS;reject(READER_REV_UNSAFE,"Selected history still has pending or foreign parents");}
    if(current.state.heads>1){selection->kind=READER_SELECTION_CONCURRENT;reject(READER_REV_UNSAFE,"Concurrent heads require explicit user resolution");}
    if(!current.state.projection_safe){selection->kind=READER_SELECTION_BLOCKED_RESTORE;reject(READER_REV_UNSAFE,"An implicit resurrection remains blocked");}
    std::string body;revision r=retained(store,safe_head(current),&body);
    std::unique_ptr<char,decltype(&std::free)> copy((char *)std::malloc(body.size()+1),std::free);if(!copy)throw std::bad_alloc();std::memcpy(copy.get(),body.data(),body.size());copy.get()[body.size()]=0;
    tx.commit();selection->kind=READER_SELECTION_SAFE;*wire=copy.release();*bytes=body.size();info(r,out);
  });
}
static reader_revision_status reader_revision_annotations_page_impl(bool raw_api,reader_revisions *store,const char *book_key,const char *after_id,int direction,size_t limit,reader_revision_annotation_fn visit,void *context,reader_revision_error *error){
  return call(error,[&]{guard owner(store,raw_api);
    if(!book_key||!visit||!limit||limit>100||(direction!=1&&direction!=-1))reject(READER_REV_ARGUMENT,"Annotation page requires book, callback, direction and limit 1..100");
    book(book_key);if(after_id)identifier(after_id);
    std::string prefix=std::string(book_key)+":",lower=prefix,upper=prefix+"g";
    if(after_id){if(direction==1)lower+=after_id;else upper=prefix+after_id;}
    transaction tx(store->db,"BEGIN");std::vector<std::string> keys;
    {
      statement q(store->db,direction==1?
        "SELECT DISTINCT entity_key FROM reader_revisions WHERE entity_kind='annotation' AND entity_key>?1 AND entity_key<?2 ORDER BY entity_key LIMIT ?3":
        "SELECT DISTINCT entity_key FROM reader_revisions WHERE entity_kind='annotation' AND entity_key>?1 AND entity_key<?2 ORDER BY entity_key DESC LIMIT ?3");
      q.bind(1,lower);q.bind(2,upper);check(sqlite3_bind_int(q.s,3,(int)limit));
      while(q.next()==SQLITE_ROW)keys.push_back(text(q.s,0));
    }
    for(const std::string &key:keys){
      std::string id=key.substr(prefix.size());identifier(id);
      reader_revision_annotation_row row{};row.annotation_id=id.c_str();std::string body;
      selected_payload(store,"annotation",key,row.selection,row.info,body);
      if(row.selection.kind==READER_SELECTION_SAFE)row.wire=body.c_str();
      if(visit(context,&row))break;
    }
    tx.commit();
  });
}
static reader_revision_status reader_revision_entities_page_impl(bool raw_api,reader_revisions *store,const char *type,const char *after_key,int direction,size_t limit,reader_revision_entity_fn visit,void *context,reader_revision_error *error){
  return call(error,[&]{guard owner(store,raw_api);
    if(!type||!kind(type)||!visit||!limit||limit>100||(direction!=1&&direction!=-1))reject(READER_REV_ARGUMENT,"Entity page requires kind, callback, direction and limit 1..100");
    if(after_key)entity_identity(type,after_key);
    transaction tx(store->db,"BEGIN");std::vector<std::string> keys;
    {
      statement q(store->db,direction==1?
        "SELECT DISTINCT entity_key FROM reader_revisions WHERE entity_kind=?1 AND entity_key>?2 ORDER BY entity_key LIMIT ?3":
        "SELECT DISTINCT entity_key FROM reader_revisions WHERE entity_kind=?1 AND entity_key<?2 ORDER BY entity_key DESC LIMIT ?3");
      q.bind(1,type);q.bind(2,after_key?after_key:direction==1?"":"\x7f");check(sqlite3_bind_int(q.s,3,(int)limit));
      while(q.next()==SQLITE_ROW)keys.push_back(text(q.s,0));
    }
    for(const auto &key:keys){reader_revision_entity_row row{};row.entity_key=key.c_str();std::string body;
      selected_payload(store,type,key,row.selection,row.info,body);
      if(row.selection.kind==READER_SELECTION_SAFE)row.wire=body.c_str();
      if(visit(context,&row))break;
    }
    tx.commit();
  });
}
static reader_revision_status reader_revision_book_title_impl(bool raw_api,reader_revisions *store,const char *id,char **title,reader_revision_error *error){
  if(title)*title=nullptr;
  return call(error,[&]{guard owner(store,raw_api);if(!id||!title)reject(READER_REV_ARGUMENT,"Book title requires retained revision and output");
    std::string body;revision r=retained(store,id,&body);
    if(r.kind!="book"||r.operation=="delete")reject(READER_REV_ARGUMENT,"Book title requires a non-delete book revision");
    json j(store->db,body);std::string value=j.string(j.field(j.field(0,"payload"),"title"));
    char *copy=(char *)std::malloc(value.size()+1);if(!copy)throw std::bad_alloc();std::memcpy(copy,value.c_str(),value.size()+1);*title=copy;
  });
}
static reader_revision_status reader_revision_outbox_impl(bool raw_api,reader_revisions *store,size_t limit,reader_revision_outbox_fn visit,void *context,reader_revision_error *error){return call(error,[&]{
  guard owner(store,raw_api);if(!visit||!limit||limit>100)reject(READER_REV_ARGUMENT,"Outbox limit must be 1..100");statement q(store->db,"SELECT revision_id,queue_id,attempts,last_error FROM reader_outbox ORDER BY queue_id LIMIT ?1");check(sqlite3_bind_int(q.s,1,(int)limit));
  while(q.next()==SQLITE_ROW){std::string body,id=text(q.s,0),last=text(q.s,3);revision r=retained(store,id,&body);reader_revision_outbox_row row{};info(r,&row.info);row.wire=body.data();row.queue_id=sqlite3_column_int64(q.s,1);row.attempts=sqlite3_column_int64(q.s,2);row.last_error=last.c_str();if(visit(context,&row))break;}
});}
static reader_revision_status reader_revision_retry_impl(bool raw_api,reader_revisions *store,const char *id,reader_revision_status reason,reader_revision_error *error){return call(error,[&]{
  guard owner(store,raw_api);if(!id||reason<=READER_REV_OK||reason>READER_REV_NOT_FOUND)reject(READER_REV_ARGUMENT,"Retry requires a module status token");identifier(id);transaction tx(store->db);statement q(store->db,"UPDATE reader_outbox SET attempts=attempts+1,last_error=?2 WHERE revision_id=?1 AND attempts<2147483647");q.bind(1,id);q.bind(2,"revision_error_"+std::to_string((int)reason));q.next();if(sqlite3_changes(store->db)!=1)reject(READER_REV_NOT_FOUND,"Pending revision not found or retry counter exhausted");tx.commit();
});}
static reader_revision_status reader_revision_ack_impl(bool raw_api,reader_revisions *store,const char *id,const char *expected,reader_revision_error *error){return call(error,[&]{
  guard owner(store,raw_api);if(!id||!expected)reject(READER_REV_ARGUMENT,"Ack requires revision ID and verified SHA-256");transaction tx(store->db);revision r=retained(store,id);if(r.sha!=expected)reject(READER_REV_HASH,"Ack SHA-256 differs from retained original");statement q(store->db,"DELETE FROM reader_outbox WHERE revision_id=?1");q.bind(1,id);q.next();tx.commit();
});}

extern "C" reader_revision_status reader_revisions_open(const char *path,reader_revisions **out,reader_revision_error *error){return reader_revisions_open_impl(false,path,out,error);}
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
extern "C" reader_revision_status reader_revisions_open_raw_v3(const char *path,reader_revisions **out,reader_revision_error *error){return reader_revisions_open_impl(true,path,out,error);}
#endif
extern "C" reader_revision_status reader_revision_validate(reader_revisions *store,const void *bytes,size_t count,const char *expected,reader_revision_info *out,reader_revision_error *error){return reader_revision_validate_impl(false,store,bytes,count,expected,out,error);}
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
extern "C" reader_revision_status reader_revision_validate_raw_v3(reader_revisions *store,const void *bytes,size_t count,const char *expected,reader_revision_info *out,reader_revision_error *error){return reader_revision_validate_impl(true,store,bytes,count,expected,out,error);}
#endif
extern "C" reader_revision_status reader_revision_local(reader_revisions *store,const void *bytes,size_t count,reader_revision_info *out,int *created,reader_revision_error *error){return reader_revision_local_impl(false,store,bytes,count,out,created,error);}
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
extern "C" reader_revision_status reader_revision_local_raw_v3(reader_revisions *store,const void *bytes,size_t count,reader_revision_info *out,int *created,reader_revision_error *error){return reader_revision_local_impl(true,store,bytes,count,out,created,error);}
#endif
extern "C" reader_revision_status reader_revision_receive(reader_revisions *store,const void *bytes,size_t count,const char *expected,reader_revision_info *out,int *created,reader_revision_error *error){return reader_revision_receive_impl(false,store,bytes,count,expected,out,created,error);}
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
extern "C" reader_revision_status reader_revision_receive_raw_v3(reader_revisions *store,const void *bytes,size_t count,const char *expected,reader_revision_info *out,int *created,reader_revision_error *error){return reader_revision_receive_impl(true,store,bytes,count,expected,out,created,error);}
#endif
extern "C" reader_revision_status reader_revision_get(reader_revisions *store,const char *id,char **wire,size_t *bytes,reader_revision_info *out,reader_revision_error *error){return reader_revision_get_impl(false,store,id,wire,bytes,out,error);}
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
extern "C" reader_revision_status reader_revision_get_raw_v3(reader_revisions *store,const char *id,char **wire,size_t *bytes,reader_revision_info *out,reader_revision_error *error){return reader_revision_get_impl(true,store,id,wire,bytes,out,error);}
#endif
extern "C" reader_revision_status reader_revision_heads(reader_revisions *store,const char *entity_kind,const char *entity_key,reader_revision_head_fn visit,void *context,reader_revision_state *out,reader_revision_error *error){return reader_revision_heads_impl(false,store,entity_kind,entity_key,visit,context,out,error);}
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
extern "C" reader_revision_status reader_revision_heads_raw_v3(reader_revisions *store,const char *entity_kind,const char *entity_key,reader_revision_head_fn visit,void *context,reader_revision_state *out,reader_revision_error *error){return reader_revision_heads_impl(true,store,entity_kind,entity_key,visit,context,out,error);}
#endif
extern "C" reader_revision_status reader_revision_book_identity(reader_revisions *store,const char *key,uint64_t *bytes,reader_revision_error *error){return reader_revision_book_identity_impl(false,store,key,bytes,error);}
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
extern "C" reader_revision_status reader_revision_book_identity_raw_v3(reader_revisions *store,const char *key,uint64_t *bytes,reader_revision_error *error){return reader_revision_book_identity_impl(true,store,key,bytes,error);}
#endif
extern "C" reader_revision_status reader_revision_local_project(reader_revisions *store,const void *bytes,size_t count,const char *const *expected,size_t expected_count,const char *sort_title,reader_revision_info *out,int *created,int *applied,reader_revision_error *error){return reader_revision_local_project_impl(false,store,bytes,count,expected,expected_count,sort_title,out,created,applied,error);}
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
extern "C" reader_revision_status reader_revision_local_project_raw_v3(reader_revisions *store,const void *bytes,size_t count,const char *const *expected,size_t expected_count,const char *sort_title,reader_revision_info *out,int *created,int *applied,reader_revision_error *error){return reader_revision_local_project_impl(true,store,bytes,count,expected,expected_count,sort_title,out,created,applied,error);}
#endif
extern "C" reader_revision_status reader_revision_local_reading(reader_revisions *store,const void *bytes,size_t count,const char *const *expected,size_t expected_count,reader_revision_info *out,int *created,reader_revision_error *error){return reader_revision_local_reading_impl(false,store,bytes,count,expected,expected_count,out,created,error);}
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
extern "C" reader_revision_status reader_revision_local_reading_raw_v3(reader_revisions *store,const void *bytes,size_t count,const char *const *expected,size_t expected_count,reader_revision_info *out,int *created,reader_revision_error *error){return reader_revision_local_reading_impl(true,store,bytes,count,expected,expected_count,out,created,error);}
#endif
extern "C" reader_revision_status reader_revision_project(reader_revisions *store,const char *entity_kind,const char *entity_key,const char *expected,const char *sort_title,reader_revision_info *out,reader_revision_error *error){return reader_revision_project_impl(false,store,entity_kind,entity_key,expected,sort_title,out,error);}
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
extern "C" reader_revision_status reader_revision_project_raw_v3(reader_revisions *store,const char *entity_kind,const char *entity_key,const char *expected,const char *sort_title,reader_revision_info *out,reader_revision_error *error){return reader_revision_project_impl(true,store,entity_kind,entity_key,expected,sort_title,out,error);}
#endif
extern "C" reader_revision_status reader_revision_selected(reader_revisions *store,const char *entity_kind,const char *entity_key,char **wire,size_t *bytes,reader_revision_info *out,reader_revision_selection *selection,reader_revision_error *error){return reader_revision_selected_impl(false,store,entity_kind,entity_key,wire,bytes,out,selection,error);}
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
extern "C" reader_revision_status reader_revision_selected_raw_v3(reader_revisions *store,const char *entity_kind,const char *entity_key,char **wire,size_t *bytes,reader_revision_info *out,reader_revision_selection *selection,reader_revision_error *error){return reader_revision_selected_impl(true,store,entity_kind,entity_key,wire,bytes,out,selection,error);}
#endif
extern "C" reader_revision_status reader_revision_annotations_page(reader_revisions *store,const char *book_key,const char *after_id,int direction,size_t limit,reader_revision_annotation_fn visit,void *context,reader_revision_error *error){return reader_revision_annotations_page_impl(false,store,book_key,after_id,direction,limit,visit,context,error);}
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
extern "C" reader_revision_status reader_revision_annotations_page_raw_v3(reader_revisions *store,const char *book_key,const char *after_id,int direction,size_t limit,reader_revision_annotation_fn visit,void *context,reader_revision_error *error){return reader_revision_annotations_page_impl(true,store,book_key,after_id,direction,limit,visit,context,error);}
#endif
extern "C" reader_revision_status reader_revision_entities_page(reader_revisions *store,const char *type,const char *after_key,int direction,size_t limit,reader_revision_entity_fn visit,void *context,reader_revision_error *error){return reader_revision_entities_page_impl(false,store,type,after_key,direction,limit,visit,context,error);}
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
extern "C" reader_revision_status reader_revision_entities_page_raw_v3(reader_revisions *store,const char *type,const char *after_key,int direction,size_t limit,reader_revision_entity_fn visit,void *context,reader_revision_error *error){return reader_revision_entities_page_impl(true,store,type,after_key,direction,limit,visit,context,error);}
#endif
extern "C" reader_revision_status reader_revision_book_title(reader_revisions *store,const char *id,char **title,reader_revision_error *error){return reader_revision_book_title_impl(false,store,id,title,error);}
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
extern "C" reader_revision_status reader_revision_book_title_raw_v3(reader_revisions *store,const char *id,char **title,reader_revision_error *error){return reader_revision_book_title_impl(true,store,id,title,error);}
#endif
extern "C" reader_revision_status reader_revision_outbox(reader_revisions *store,size_t limit,reader_revision_outbox_fn visit,void *context,reader_revision_error *error){return reader_revision_outbox_impl(false,store,limit,visit,context,error);}
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
extern "C" reader_revision_status reader_revision_outbox_raw_v3(reader_revisions *store,size_t limit,reader_revision_outbox_fn visit,void *context,reader_revision_error *error){return reader_revision_outbox_impl(true,store,limit,visit,context,error);}
#endif
extern "C" reader_revision_status reader_revision_retry(reader_revisions *store,const char *id,reader_revision_status reason,reader_revision_error *error){return reader_revision_retry_impl(false,store,id,reason,error);}
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
extern "C" reader_revision_status reader_revision_retry_raw_v3(reader_revisions *store,const char *id,reader_revision_status reason,reader_revision_error *error){return reader_revision_retry_impl(true,store,id,reason,error);}
#endif
extern "C" reader_revision_status reader_revision_ack(reader_revisions *store,const char *id,const char *expected,reader_revision_error *error){return reader_revision_ack_impl(false,store,id,expected,error);}
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
extern "C" reader_revision_status reader_revision_ack_raw_v3(reader_revisions *store,const char *id,const char *expected,reader_revision_error *error){return reader_revision_ack_impl(true,store,id,expected,error);}
#endif
