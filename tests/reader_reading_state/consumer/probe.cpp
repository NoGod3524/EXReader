/* SPDX-License-Identifier: MIT */
/* Installed C++ consumer: real frozen-SDK captures, wire v1 compatibility, and
   two independent SDK libraries plus two schema1 product catalogs. Every
   original, selector and database is created in Actions from generated inputs. */
#include <reader_reading_state.h>
#include <reader_projection.h>
#include <catalog.h>
#include <exreader.h>
#include <sqlite3.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

namespace {
/* ---------- report ---------- */
std::string esc(const std::string &s){
  static const char hex[]="0123456789abcdef";std::string o="\"";
  for(unsigned char c:s){if(c=='"'||c=='\\'){o+='\\';o+=(char)c;}else if(c<0x20){o+="\\u00";o+=hex[c>>4];o+=hex[c&15];}else o+=(char)c;}
  return o+"\"";
}
std::string num(unsigned long long v){return std::to_string(v);}
std::string snum(long long v){return std::to_string(v);}
std::string boolean(bool v){return v?"true":"false";}
struct object {
  std::vector<std::pair<std::string,std::string>> fields;
  object &set(const std::string &k,const std::string &raw){for(auto &f:fields)if(f.first==k){f.second=raw;return *this;}fields.emplace_back(k,raw);return *this;}
  object &str(const std::string &k,const std::string &v){return set(k,esc(v));}
  std::string dump()const{std::string o="{";for(size_t i=0;i<fields.size();i++){if(i)o+=",";o+=esc(fields[i].first)+":"+fields[i].second;}return o+"}";}
};
std::string array(const std::vector<std::string> &items){std::string o="[";for(size_t i=0;i<items.size();i++){if(i)o+=",";o+=items[i];}return o+"]";}
std::vector<std::string> checks,cases,lifecycle,exchanged;
size_t failures=0,receiver_found=0,receiver_mislocated=0,unresolved_writes=0;
void expect(bool ok,const std::string &name,const std::string &detail=""){
  if(!ok){failures++;std::fprintf(stderr,"FAIL %s %s\n",name.c_str(),detail.c_str());}
  checks.push_back(object().str("name",name).set("pass",boolean(ok)).str("detail",detail).dump());
}
void stage(const char *what){std::printf("stage: %s\n",what);std::fflush(stdout);}
[[noreturn]] void fatal(const std::string &what){std::fprintf(stderr,"FATAL %s\n",what.c_str());std::exit(2);}
std::string hexbytes(const char *p,size_t n){static const char h[]="0123456789abcdef";std::string o;for(size_t i=0;i<n;i++){o+=h[(unsigned char)p[i]>>4];o+=h[(unsigned char)p[i]&15];}return o;}
const char *state_name(exr_anchor_state s){return s==EXR_ANCHOR_FOUND?"FOUND":s==EXR_ANCHOR_AMBIGUOUS?"AMBIGUOUS":s==EXR_ANCHOR_LEGACY?"LEGACY":"MISSING";}
const char *gap_name(reader_rs_gap g){
  static const char *n[]={"none","point","textless_page","chapter_scope","nul","legacy","limit","route"};return (unsigned)g<8?n[g]:"unknown";
}
const char *rs_name(reader_rs_status s){
  static const char *n[]={"OK","ARGUMENT","MEMORY","SDK","REVISION","NOT_REPRESENTABLE","UNRESOLVED","IDENTITY"};return (unsigned)s<8?n[s]:"UNKNOWN";
}
std::string read_file(const std::string &path){std::ifstream in(path,std::ios::binary);if(!in)fatal("cannot read "+path);std::ostringstream s;s<<in.rdbuf();return s.str();}

/* ---------- SDK and product handles ---------- */
#define SDK(call) do{exr_error e_{};exr_status s_=(call);if(s_!=EXR_OK)fatal(std::string(#call)+": "+e_.message);}while(0)
struct side {
  const char *name;exr_library *lib=nullptr;reader_revisions *store=nullptr;reader_catalog *catalog=nullptr;
  std::string lib_path,product_path;
  std::map<std::string,int64_t> ids; /* book role -> this library's own SDK ID */
};
std::map<std::string,std::string> keys,shas,paths,formats;
std::map<std::string,uint64_t> sizes;
std::string parser_version;
void open_side(side &s){
  exr_error e{};if(exr_library_open(s.lib_path.c_str(),&s.lib,&e)!=EXR_OK)fatal(std::string("library open: ")+e.message);
  reader_revision_error r{};if(reader_revisions_open(s.product_path.c_str(),&s.store,&r)!=READER_REV_OK)fatal(std::string("revisions open: ")+r.message);
  reader_catalog_error c{};if(reader_catalog_open(s.product_path.c_str(),&s.catalog,&c))fatal(std::string("catalog open: ")+c.message);
}
void close_side(side &s){
  exr_library_close(s.lib);s.lib=nullptr;reader_revision_error r{};reader_revisions_close(&s.store,&r);reader_catalog_error c{};reader_catalog_close(&s.catalog,&c);
}
int64_t import(side &s,const std::string &role,exr_format format,bool file){
  int64_t id=0;exr_error e{};exr_status status;
  if(file)status=exr_library_import_file(s.lib,format,paths[role].c_str(),role.c_str(),&id,&e);
  else{std::string data=read_file(paths[role]);status=exr_library_import(s.lib,format,data.data(),data.size(),role.c_str(),&id,&e);}
  if(status!=EXR_OK)fatal("import "+role+": "+e.message);
  void *blob=nullptr;size_t size=0;std::string original=read_file(paths[role]);
  SDK(exr_library_blob(s.lib,id,0,&blob,&size,&e_));
  expect(size==original.size()&&!std::memcmp(blob,original.data(),size),std::string(s.name)+" stores exact original "+role);
  exr_free(blob);s.ids[role]=id;return id;
}
int64_t catalog_id(side &s,const std::string &role){
  struct ctx {int64_t id=0;} c;int found=0;reader_catalog_error e{};
  if(reader_catalog_find(s.catalog,keys[role].c_str(),nullptr,[](void *p,const reader_catalog_row *row){((ctx *)p)->id=row->sdk_book_id;return 0;},&c,&found,&e)||!found)fatal("catalog find "+role);
  return c.id;
}
void attach(side &s,const std::string &role,const char *kind){
  reader_catalog_book b{};std::string title="Reading state "+role;
  b.format=formats[role].c_str();b.sha256=shas[role].c_str();b.title=title.c_str();b.author="";b.sort_title=title.c_str();
  b.location_kind=kind;b.source_bytes=sizes[role];b.sdk_book_id=s.ids[role];b.favorite=0;
  reader_catalog_error e{};if(reader_catalog_attach(s.catalog,&b,&e))fatal("attach "+role+": "+e.message);
  expect(catalog_id(s,role)==s.ids[role],std::string(s.name)+" catalog maps "+role+" only to its own SDK ID");
}

/* ---------- literal and proposed wire renderers (diagnostic only) ---------- */
struct sel {std::string exact,prefix,suffix;size_t start=0,end=0;bool has_chapter=false;std::string chapter;};
sel from(const exr_anchor &a){sel s;s.exact=a.exact?a.exact:"";s.prefix=a.prefix?a.prefix:"";s.suffix=a.suffix?a.suffix:"";s.start=a.start;s.end=a.end;s.has_chapter=a.chapter!=nullptr;if(a.chapter)s.chapter=a.chapter;return s;}
sel from(const exr_fixed_anchor &a){sel s;s.exact.assign(a.exact?a.exact:"",a.exact_size);s.prefix.assign(a.prefix?a.prefix:"",a.prefix_size);s.suffix.assign(a.suffix?a.suffix:"",a.suffix_size);s.start=a.start;s.end=a.end;return s;}
struct target {const char *kind;std::string role,aid,mode,part_path,page_id;size_t page=0;std::string text;};
std::string new_id(){char id[33];reader_revision_error e{};if(reader_revision_new_id(id,&e)!=READER_REV_OK)fatal("new id");return id;}
/* anchor_version 1 renders exactly what v1 has fields for; 2 is the proposal:
   empty exact only for start==end, and reflow carries the SDK chapter scope. */
std::string render(const target &t,const sel &s,int anchor_version,const std::string &id){
  std::string book=keys[t.role],key=std::string(t.kind)=="annotation"?book+":"+t.aid:book;
  std::string loc="{\"mode\":"+esc(t.mode)+",\"parser_version\":"+esc(parser_version)+",\"anchor_version\":"+num((unsigned)anchor_version);
  if(t.mode=="epub_chapter")loc+=",\"part_path\":"+esc(t.part_path);
  if(t.mode=="fixed_page")loc+=",\"page_id\":"+esc(t.page_id)+",\"page\":"+num(t.page);
  loc+=",\"selector\":{\"exact\":"+esc(s.exact)+",\"prefix\":"+esc(s.prefix)+",\"suffix\":"+esc(s.suffix)+",\"start\":"+num(s.start)+",\"end\":"+num(s.end);
  if(anchor_version==2&&t.mode=="reflow_global")loc+=",\"chapter\":"+(s.has_chapter?esc(s.chapter):std::string("null"));
  loc+="}}";
  std::string payload="{\"book_key\":"+esc(book);
  if(std::string(t.kind)=="annotation")payload+=",\"annotation_id\":"+esc(t.aid);
  payload+=",\"location\":"+loc;
  if(std::string(t.kind)=="annotation")payload+=",\"text\":"+esc(t.text);
  payload+="}";
  return "{\"version\":1,\"id\":"+esc(id)+",\"entity_kind\":"+esc(t.kind)+",\"entity_key\":"+esc(key)+",\"operation\":\"put\",\"location_kind\":"+esc(t.mode)+",\"parents\":[],\"payload\":"+payload+"}";
}
struct verdict {reader_revision_status status;std::string message;};
verdict validate(reader_revisions *store,const std::string &wire){reader_revision_error e{};reader_revision_info i{};reader_revision_status st=reader_revision_validate(store,wire.data(),wire.size(),nullptr,&i,&e);return {st,st?e.message:""};}
/* Proposal receiver: read the v2 bytes back (never the in-memory capture). */
struct v2record {sel s;std::string page_id;uint64_t page=0;};
v2record read_v2(const std::string &wire){
  sqlite3 *db=nullptr;sqlite3_stmt *q=nullptr;v2record r;
  if(sqlite3_open_v2(":memory:",&db,SQLITE_OPEN_READWRITE|SQLITE_OPEN_CREATE,nullptr)!=SQLITE_OK)fatal("json db");
  const char *sql="SELECT json_extract(?1,'$.payload.location.selector.exact'),json_extract(?1,'$.payload.location.selector.prefix'),"
    "json_extract(?1,'$.payload.location.selector.suffix'),json_extract(?1,'$.payload.location.selector.start'),json_extract(?1,'$.payload.location.selector.end'),"
    "json_extract(?1,'$.payload.location.selector.chapter'),json_extract(?1,'$.payload.location.page_id'),json_extract(?1,'$.payload.location.page'),json_valid(?1,1)";
  if(sqlite3_prepare_v2(db,sql,-1,&q,nullptr)!=SQLITE_OK||sqlite3_bind_text64(q,1,wire.data(),wire.size(),SQLITE_TRANSIENT,SQLITE_UTF8)!=SQLITE_OK||sqlite3_step(q)!=SQLITE_ROW||sqlite3_column_int(q,8)!=1)fatal("v2 read");
  auto col=[&](int i){const unsigned char *t=sqlite3_column_text(q,i);return t?std::string((const char *)t,(size_t)sqlite3_column_bytes(q,i)):std::string();};
  r.s.exact=col(0);r.s.prefix=col(1);r.s.suffix=col(2);r.s.start=(size_t)sqlite3_column_int64(q,3);r.s.end=(size_t)sqlite3_column_int64(q,4);
  r.s.has_chapter=sqlite3_column_type(q,5)!=SQLITE_NULL;r.s.chapter=col(5);r.page_id=col(6);r.page=(uint64_t)sqlite3_column_int64(q,7);
  sqlite3_finalize(q);sqlite3_close(db);return r;
}
exr_anchor as_anchor(sel &s,bool chapter){exr_anchor a{};a.start=s.start;a.end=s.end;a.exact=&s.exact[0];a.prefix=&s.prefix[0];a.suffix=&s.suffix[0];a.chapter=chapter&&s.has_chapter?&s.chapter[0]:nullptr;return a;}

/* ---------- shared case record ---------- */
struct observation {
  object o;
  void capture(const sel &s){o.set("capture",object().set("start",num(s.start)).set("end",num(s.end)).set("exact_bytes",num(s.exact.size()))
    .str("exact_hex",hexbytes(s.exact.data(),s.exact.size())).set("prefix_bytes",num(s.prefix.size())).set("suffix_bytes",num(s.suffix.size()))
    .set("chapter",s.has_chapter?esc(s.chapter):"null").dump());}
};
void literal_and_adapter(observation &ob,side &sender,const target &t,const sel &s,const reader_rs_capture &capture,std::string *wire){
  verdict literal=validate(sender.store,render(t,s,1,new_id()));
  ob.o.set("v1_literal",object().set("status",num((unsigned)literal.status)).str("message",literal.message).dump());
  reader_rs_envelope env{};std::string id=new_id();env.revision_id=id.c_str();env.operation="put";env.entity_kind=t.kind;env.book_key=keys[t.role].c_str();
  env.annotation_id=t.aid.c_str();env.note_text=t.text.c_str();env.parser_version=parser_version.c_str();
  char *bytes=nullptr;size_t n=0;reader_rs_error e{};reader_rs_status st=reader_rs_encode(sender.store,&env,&capture,&bytes,&n,&e);
  ob.o.set("adapter",object().str("status",rs_name(st)).str("gap",gap_name(e.gap)).str("classify",gap_name(reader_rs_classify(&capture))).set("revision_code",num((unsigned)e.revision_code)).dump());
  if(st==READER_RS_OK&&wire)wire->assign(bytes,n);
  reader_rs_free(bytes);
  if(st!=READER_RS_OK){
    std::string v2=render(t,s,2,new_id());verdict old=validate(sender.store,v2);
    ob.o.set("v2_proposal",object().set("bytes",num(v2.size())).set("v1_client_status",num((unsigned)old.status)).str("v1_client_message",old.message).dump());
    expect(old.status==READER_REV_FORMAT,t.role+"/"+t.aid+" proposal refused by an unchanged v1 client");
  }
}
void receiver_result(observation &ob,const char *path,reader_rs_status st,const exr_anchor_match &m,const sel &expected,bool persisted,const std::string &note=""){
  bool found=st==READER_RS_OK&&m.state==EXR_ANCHOR_FOUND;
  if(found){receiver_found++;if(m.start!=expected.start||m.end!=expected.end)receiver_mislocated++;}
  if(!found&&persisted)unresolved_writes++;
  ob.o.set("receiver",object().str("path",path).str("status",rs_name(st)).str("state",state_name(m.state))
    .set("start",m.state==EXR_ANCHOR_FOUND?num(m.start):"null").set("end",m.state==EXR_ANCHOR_FOUND?num(m.end):"null")
    .set("expected_start",num(expected.start)).set("expected_end",num(expected.end)).set("sdk_persisted",boolean(persisted)).str("note",note).dump());
}
size_t count_notes(side &s,int64_t book){exr_note *n=nullptr;size_t c=0;SDK(exr_library_notes(s.lib,book,&n,&c,&e_));exr_notes_free(n,c);return c;}
size_t count_fixed(side &s,int64_t book){exr_fixed_note *n=nullptr;size_t c=0;SDK(exr_library_fixed_notes(s.lib,book,&n,&c,&e_));exr_fixed_notes_free(n,c);return c;}
size_t count_epub(side &s,int64_t book){exr_epub_note *n=nullptr;size_t c=0;SDK(exr_library_epub_notes(s.lib,book,&n,&c,&e_));exr_epub_notes_free(n,c);return c;}

side A{"A"},B{"B"};
size_t locate(const std::string &text,const std::string &needle,int occurrence=0){
  size_t at=std::string::npos,from=0;for(int i=0;i<=occurrence;i++){at=text.find(needle,from);if(at==std::string::npos)fatal("fixture text lacks "+needle);from=at+1;}return at;
}

/* ---------- reflow (TXT, global storage) ---------- */
struct reflow {exr_document *a=nullptr,*b=nullptr;std::string text;int64_t ida=0,idb=0;};
void reflow_case(reflow &r,const std::string &role,const char *kind,const std::string &aid,size_t start,size_t end,const char *label,bool active_reader=false){
  observation ob;ob.o.str("id",label).str("book",role).str("kind",std::string(kind)=="progress"?"progress":aid.rfind("bm",0)==0?"bookmark":"highlight")
    .str("sdk_capture","exr_anchor_create").str("mode","reflow_global");
  exr_anchor a{};exr_error e{};exr_status cs=exr_anchor_create(r.a,start,end,&a,&e);
  ob.o.set("capture_status",num((unsigned)cs));
  if(cs!=EXR_OK){ob.o.str("capture_message",e.message);cases.push_back(ob.o.dump());exr_anchor_free(&a);return;}
  sel s=from(a);ob.capture(s);
  exr_anchor_match self{};SDK(exr_anchor_resolve_ex(r.a,&a,nullptr,&self,&e_));ob.o.str("sender_resolve",state_name(self.state));
  target t{kind,role,aid,"reflow_global","","",0,std::string("note ")+label};
  reader_rs_capture c{};c.mode=READER_RS_REFLOW_GLOBAL;c.anchor=&a;std::string wire;
  literal_and_adapter(ob,A,t,s,c,&wire);
  size_t notes_before=count_notes(B,r.idb);
  if(!wire.empty()){
    reader_rs_record rec{};reader_rs_error re{};
    if(reader_rs_decode(B.store,wire.data(),wire.size(),&rec,&re)!=READER_RS_OK)fatal("decode reflow");
    exr_anchor_match own{};reader_rs_error oe{};reader_rs_resolve_reflow(r.a,&rec,nullptr,&own,&oe);
    expect(own.state==self.state&&own.start==self.start&&own.end==self.end,std::string(label)+" decoded v1 resolves identically on the sender");
    exr_anchor_match m{};int64_t note=0;reader_rs_status st;
    if(std::string(kind)=="annotation")st=reader_rs_store_reflow_note(B.lib,r.idb,r.b,&rec,0,&note,&m,&re);
    else st=reader_rs_resolve_reflow(r.b,&rec,nullptr,&m,&re);
    receiver_result(ob,"v1",st,m,s,note>0);
    expect((count_notes(B,r.idb)==notes_before+1)==(note>0),std::string(label)+" SDK note count follows FOUND only");
    reader_rs_record_free(&rec);
  }else{
    /* Proposed v2 round trip through bytes; SDK writes only after FOUND. */
    std::string v2=render(t,s,2,new_id());v2record rec=read_v2(v2);
    exr_anchor q=as_anchor(rec.s,true);exr_anchor_match m{};SDK(exr_anchor_resolve_ex(r.b,&q,nullptr,&m,&e_));
    bool persisted=false;std::string note;
    if(m.state==EXR_ANCHOR_FOUND&&!a.exact[0]&&!(a.chapter&&a.chapter[0])){
      if(std::string(kind)=="progress"){
        exr_anchor before{};exr_anchor_state bs{};SDK(exr_library_progress_get(B.lib,r.idb,&before,&bs,&e_));
        if(active_reader){
          note="active reader: FOUND candidate offered, stored progress and view unchanged";
          exr_anchor after{};exr_anchor_state as{};SDK(exr_library_progress_get(B.lib,r.idb,&after,&as,&e_));
          expect(after.start==before.start&&as==bs,std::string(label)+" remote progress does not move the active reader");exr_anchor_free(&after);
        }
        exr_anchor point{};SDK(exr_anchor_create(r.b,m.start,m.start,&point,&e_));SDK(exr_library_progress(B.lib,r.idb,&point,&e_));exr_anchor_free(&point);
        exr_anchor got{};exr_anchor_state gs{};SDK(exr_library_progress_get(B.lib,r.idb,&got,&gs,&e_));
        expect(gs==EXR_ANCHOR_FOUND&&got.start==m.start,std::string(label)+" receiver SDK progress persisted after close");exr_anchor_free(&got);exr_anchor_free(&before);
        persisted=true;
      }else{
        exr_note n{};n.book_id=r.idb;n.start=n.end=m.start;n.text=const_cast<char *>("bookmark");int64_t id=0;
        SDK(exr_library_note(B.lib,&n,&id,&e_));persisted=id>0;
        expect(count_notes(B,r.idb)==notes_before+1,std::string(label)+" receiver point note persisted");
      }
    }
    receiver_result(ob,"v2_proposal",READER_RS_OK,m,s,persisted,note);
  }
  cases.push_back(ob.o.dump());exr_anchor_free(&a);
}

/* ---------- lifecycle on one v1 highlight ---------- */
struct sent {std::string id,sha;};
std::vector<sent> pending(side &s){
  std::vector<sent> rows;reader_revision_error e{};
  reader_revision_outbox(s.store,100,[](void *p,const reader_revision_outbox_row *row){((std::vector<sent> *)p)->push_back({row->info.revision_id,row->info.sha256});return 0;},&rows,&e);
  return rows;
}
void deliver(side &from,side &to,const std::string &id,bool ack=true){
  char *wire=nullptr;size_t n=0;reader_revision_info info{};reader_revision_error e{};
  if(reader_revision_get(from.store,id.c_str(),&wire,&n,&info,&e)!=READER_REV_OK)fatal("get "+id);
  int created=0;reader_revision_info got{};reader_revision_status st=reader_revision_receive(to.store,wire,n,info.sha256,&got,&created,&e);
  expect(st==READER_REV_OK&&!std::strcmp(got.sha256,info.sha256),std::string("receive ")+id+" keeps exact bytes");
  exchanged.push_back(object().str("revision_id",id).str("from",from.name).str("to",to.name).str("sha256",info.sha256).set("bytes",num(n)).set("created",boolean(created!=0)).dump());
  reader_revision_bytes_free(wire);
  if(ack){reader_revision_status a=reader_revision_ack(from.store,id.c_str(),info.sha256,&e);(void)a;}
}
void flush(side &from,side &to){for(const sent &s:pending(from))deliver(from,to,s.id);}
std::vector<std::string> heads(side &s,const char *kind,const std::string &key,reader_revision_state *state=nullptr){
  std::vector<std::string> ids;reader_revision_state st{};reader_revision_error e{};
  reader_revision_heads(s.store,kind,key.c_str(),[](void *p,const reader_revision_head *h){((std::vector<std::string> *)p)->push_back(h->revision_id);return 0;},&ids,&st,&e);
  if(state)*state=st;return ids;
}
std::string local(side &s,const std::string &role,const std::string &aid,const char *op,const exr_anchor *a,const std::string &text,const std::vector<std::string> &parents,std::string *id_out=nullptr){
  std::vector<const char *> p;for(auto &x:parents)p.push_back(x.c_str());
  std::string id=new_id();reader_rs_envelope env{};env.revision_id=id.c_str();env.operation=op;env.entity_kind="annotation";env.book_key=keys[role].c_str();
  env.annotation_id=aid.c_str();env.parents=p.empty()?nullptr:p.data();env.parent_count=p.size();env.note_text=text.c_str();env.parser_version=parser_version.c_str();
  reader_rs_capture c{};c.mode=READER_RS_REFLOW_GLOBAL;c.anchor=a;char *w=nullptr;size_t n=0;reader_rs_error e{};
  if(reader_rs_encode(s.store,&env,&c,&w,&n,&e)!=READER_RS_OK)fatal(std::string("encode lifecycle: ")+e.message);
  reader_revision_info info{};int created=0;reader_revision_error re{};
  reader_revision_status st=reader_revision_local(s.store,w,n,&info,&created,&re);
  expect(st==READER_REV_OK&&created==1,std::string(s.name)+" local "+op+" commits history+outbox");
  /* Exact retry: same ID and bytes is a no-op and never requeues. */
  int again=1;st=reader_revision_local(s.store,w,n,&info,&again,&re);expect(st==READER_REV_OK&&again==0,std::string(s.name)+" exact local retry is idempotent");
  std::string wire(w,n);reader_rs_free(w);if(id_out)*id_out=id;return wire;
}
struct applied {std::string selection;std::string action;size_t notes=0;std::string text;};
const char *selection_name(reader_selection_kind k){static const char *n[]={"MISSING","PENDING_PARENTS","CONCURRENT","BLOCKED_RESTORE","SAFE"};return n[k];}
/* Receiver/sender projection into its own SDK library. SDK note ownership is
   reconciled by exact content (range+text) because schema1 has no global
   annotation->SDK note map; see the documented gap. */
applied apply(side &s,reflow &r,int64_t book,const exr_document *doc,const std::string &key,int64_t &mapped){
  applied out;char *w=nullptr;size_t n=0;reader_revision_info info{};reader_revision_selection chosen{};reader_revision_error e{};
  reader_revision_status st=reader_revision_selected(s.store,"annotation",key.c_str(),&w,&n,&info,&chosen,&e);
  out.selection=selection_name(chosen.kind);size_t before=count_notes(s,book);
  if(st==READER_REV_OK){
    reader_rs_record rec{};reader_rs_error re{};if(reader_rs_decode(s.store,w,n,&rec,&re)!=READER_RS_OK)fatal("decode selected");
    if(!std::strcmp(rec.operation,"delete")){
      if(mapped){SDK(exr_library_remove_note(s.lib,mapped,&e_));mapped=0;out.action="removed";}else out.action="tombstone-no-local-note";
    }else{
      if(!mapped){ /* restart reconciliation: adopt an identical existing note instead of duplicating */
        exr_anchor_match m{};reader_rs_error me{};
        if(reader_rs_resolve_reflow(doc,&rec,nullptr,&m,&me)==READER_RS_OK){
          exr_note *notes=nullptr;size_t c=0;SDK(exr_library_notes(s.lib,book,&notes,&c,&e_));
          for(size_t i=0;i<c;i++)if(notes[i].start==m.start&&notes[i].end==m.end&&notes[i].text&&rec.note_text&&!std::strcmp(notes[i].text,rec.note_text)){mapped=notes[i].id;out.action="adopted";}
          exr_notes_free(notes,c);
        }
      }
      if(out.action!="adopted"){
        int64_t id=0;exr_anchor_match m{};reader_rs_status rs=reader_rs_store_reflow_note(s.lib,book,doc,&rec,mapped,&id,&m,&re);
        out.action=rs==READER_RS_OK?(mapped?"updated":"created"):std::string("kept-record-")+rs_name(rs);if(rs==READER_RS_OK)mapped=id;
      }
    }
    reader_rs_record_free(&rec);reader_revision_bytes_free(w);
  }else out.action="no-sdk-write";
  (void)r;out.notes=count_notes(s,book);
  if(out.action=="no-sdk-write")expect(out.notes==before,std::string(s.name)+" unsafe selection leaves SDK notes unchanged");
  if(mapped){exr_note *notes=nullptr;size_t c=0;SDK(exr_library_notes(s.lib,book,&notes,&c,&e_));for(size_t i=0;i<c;i++)if(notes[i].id==mapped&&notes[i].text)out.text=notes[i].text;exr_notes_free(notes,c);}
  return out;
}
void step(const std::string &name,const applied &a,const applied &b,const std::string &extra=""){
  lifecycle.push_back(object().str("step",name).str("A_selection",a.selection).str("A_action",a.action).set("A_notes",num(a.notes)).str("A_text",a.text)
    .str("B_selection",b.selection).str("B_action",b.action).set("B_notes",num(b.notes)).str("B_text",b.text).str("detail",extra).dump());
}
}

int main(int argc,char **argv){
  std::string fixtures,font,work,report_path;
  for(int i=1;i+1<argc;i+=2){
    std::string k=argv[i],v=argv[i+1];
    if(k=="--fixtures")fixtures=v;else if(k=="--font")font=v;else if(k=="--work")work=v;else if(k=="--report")report_path=v;
    else if(k=="--sha"){size_t eq=v.find('=');if(eq==std::string::npos)fatal("bad --sha");shas[v.substr(0,eq)]=v.substr(eq+1);}
    else fatal("unknown argument "+k);
  }
  if(fixtures.empty()||font.empty()||work.empty()||report_path.empty())fatal("usage: --fixtures D --font F --work W --report R --sha role=hex...");
  const char *roles[][3]={{"txt","book.txt","txt"},{"edited","book-edited.txt","txt"},{"spacer","spacer.txt","txt"},{"epub","book.epub","epub"},{"pdf","pages.pdf","pdf"},{"cbz","pages.cbz","cbz"}};
  for(auto &r:roles){paths[r[0]]=fixtures+"/"+r[1];formats[r[0]]=r[2];sizes[r[0]]=read_file(paths[r[0]]).size();if(!shas.count(r[0]))fatal(std::string("missing sha ")+r[0]);keys[r[0]]=std::string(r[2])+":"+shas[r[0]];}
  parser_version=std::string("exreader-sdk-")+exr_version();
  A.lib_path=work+"/A-library.sqlite";A.product_path=work+"/A-product.sqlite";B.lib_path=work+"/B-library.sqlite";B.product_path=work+"/B-product.sqlite";
  open_side(A);open_side(B);
  stage("opened libraries and catalogs");
  /* B imports an unrelated book first, so the same originals get different SDK IDs. */
  import(B,"spacer",EXR_TXT,false);
  for(side *s:{&A,&B}){import(*s,"txt",EXR_TXT,false);import(*s,"edited",EXR_TXT,false);import(*s,"epub",EXR_EPUB,true);import(*s,"pdf",EXR_PDF,true);import(*s,"cbz",EXR_CBZ,true);}
  int64_t mem_a=0,mem_b=0;{std::string data=read_file(paths["epub"]);SDK(exr_library_import(A.lib,EXR_EPUB,data.data(),data.size(),"epub-global",&mem_a,&e_));SDK(exr_library_import(B.lib,EXR_EPUB,data.data(),data.size(),"epub-global",&mem_b,&e_));}
  for(const char *role:{"txt","epub","pdf","cbz"})expect(A.ids[role]!=B.ids[role],std::string("independent SDK IDs differ for ")+role,num((unsigned long long)A.ids[role])+"/"+num((unsigned long long)B.ids[role]));
  stage("imported originals");
  for(side *s:{&A,&B}){attach(*s,"txt","reflow_global");attach(*s,"epub","epub_chapter");attach(*s,"pdf","fixed_page");attach(*s,"cbz","fixed_page");}

  stage("attached catalogs");
  /* ---- reflow TXT ---- */
  reflow r;r.ida=catalog_id(A,"txt");r.idb=catalog_id(B,"txt");
  SDK(exr_library_document(A.lib,r.ida,&r.a,&e_));SDK(exr_library_document(B.lib,r.idb,&r.b,&e_));
  {size_t na=0,nb=0;const char *ta=exr_document_text(r.a,&na),*tb=exr_document_text(r.b,&nb);r.text.assign(ta,na);expect(na==nb&&!std::memcmp(ta,tb,na),"both libraries normalize identical TXT text");}
  const std::string &T=r.text;
  /* Receiver is mid-book: its own stored progress is the active view. */
  size_t view=locate(T,"Unique context beta");{exr_anchor p{};SDK(exr_anchor_create(r.b,view,view,&p,&e_));SDK(exr_library_progress(B.lib,r.idb,&p,&e_));exr_anchor_free(&p);}
  size_t first3=locate(T,"读");
  reflow_case(r,"txt","annotation","a0000000000000000000000000000001",0,first3+std::strlen("读"),"txt-highlight-start");
  size_t emoji=locate(T,"🙂");reflow_case(r,"txt","annotation","a0000000000000000000000000000002",emoji-std::strlen("同步"),emoji+std::strlen("🙂测"),"txt-highlight-multibyte-boundary");
  size_t last=T.rfind("🎉终");if(last==std::string::npos)fatal("fixture lacks end quote");
  lifecycle.push_back(object().str("step","txt-end-quote").set("end",num(last+std::strlen("🎉终"))).set("text_bytes",num(T.size())).dump());
  reflow_case(r,"txt","annotation","a0000000000000000000000000000003",last,last+std::strlen("🎉终"),"txt-highlight-end");
  size_t dup=locate(T,"The repeated phrase appears here.",1);reflow_case(r,"txt","annotation","a0000000000000000000000000000004",dup,dup+std::strlen("The repeated phrase appears here."),"txt-highlight-duplicate-text-unique-context");
  size_t amb=locate(T,"AMBIGUOUS TARGET",1);reflow_case(r,"txt","annotation","a0000000000000000000000000000005",amb,amb+std::strlen("AMBIGUOUS TARGET"),"txt-highlight-ambiguous");
  reflow_case(r,"txt","annotation","a0000000000000000000000000000006",emoji+1,emoji+2,"txt-invalid-utf8-offset-refused");
  reflow_case(r,"txt","progress","",emoji,emoji,"txt-progress-point-multibyte",true);
  reflow_case(r,"txt","progress","",0,0,"txt-progress-point-start");
  reflow_case(r,"txt","progress","",T.size(),T.size(),"txt-progress-point-end");
  reflow_case(r,"txt","annotation","bm000000000000000000000000000001",locate(T,"Tail alpha"),locate(T,"Tail alpha"),"txt-bookmark-point");
  {/* Cross-document capture: real SDK quote from a different original. */
    observation ob;ob.o.str("id","txt-missing-cross-original").str("book","edited->txt").str("kind","highlight").str("sdk_capture","exr_anchor_create").str("mode","reflow_global");
    exr_document *ed=nullptr;SDK(exr_library_document(A.lib,A.ids["edited"],&ed,&e_));size_t n=0;const char *etext=exr_document_text(ed,&n);std::string et(etext,n);
    size_t at=locate(et,"Edited quote appears only here.");exr_anchor a{};SDK(exr_anchor_create(ed,at,at+std::strlen("Edited quote appears only here."),&a,&e_));sel s=from(a);ob.capture(s);
    target t{"annotation","edited","a00000000000000000000000000000ed","reflow_global","","",0,"cross"};reader_rs_capture c{};c.mode=READER_RS_REFLOW_GLOBAL;c.anchor=&a;std::string wire;
    literal_and_adapter(ob,A,t,s,c,&wire);
    reader_rs_record rec{};reader_rs_error re{};if(reader_rs_decode(B.store,wire.data(),wire.size(),&rec,&re)!=READER_RS_OK)fatal("decode cross");
    int64_t note=0;exr_anchor_match m{};size_t before=count_notes(B,r.idb);
    reader_rs_status st=reader_rs_store_reflow_note(B.lib,r.idb,r.b,&rec,0,&note,&m,&re);
    expect(std::string(rec.book_key)!=keys["txt"],"cross-original record names a different global book; host must not route it to txt");
    expect(st==READER_RS_UNRESOLVED&&m.state==EXR_ANCHOR_MISSING&&count_notes(B,r.idb)==before,"forced cross-original resolve is MISSING and writes nothing");
    receiver_result(ob,"v1(forced-into-wrong-book)",st,m,s,note>0,"identity check precedes resolve in product routing");
    reader_rs_record_free(&rec);exr_anchor_free(&a);exr_document_free(ed);cases.push_back(ob.o.dump());
  }
  {exr_anchor p{};exr_anchor_state ps{};SDK(exr_library_progress_get(B.lib,r.idb,&p,&ps,&e_));lifecycle.push_back(object().str("step","receiver-progress-after-cases").set("start",num(p.start)).str("state",state_name(ps)).dump());exr_anchor_free(&p);}

  stage("reflow cases done");
  /* ---- EPUB stored in memory/global mode: chapter-scoped reflow selector ---- */
  {
    exr_document *ga=nullptr,*gb=nullptr;SDK(exr_library_document(A.lib,mem_a,&ga,&e_));SDK(exr_library_document(B.lib,mem_b,&gb,&e_));
    size_t n=0;const char *gtext=exr_document_text(ga,&n);std::string gt(gtext,n);size_t at=locate(gt,"第二章节独有文字");
    observation ob;ob.o.str("id","epub-global-chapter-scope").str("book","epub(memory import)").str("kind","highlight").str("sdk_capture","exr_anchor_create").str("mode","reflow_global");
    exr_anchor a{};SDK(exr_anchor_create(ga,at,at+std::strlen("第二章节独有文字"),&a,&e_));sel s=from(a);ob.capture(s);
    exr_anchor_match self{};SDK(exr_anchor_resolve_ex(ga,&a,nullptr,&self,&e_));ob.o.str("sender_resolve",state_name(self.state));
    target t{"annotation","epub","a000000000000000000000000000000c","reflow_global","","",0,"chapter scope"};reader_rs_capture c{};c.mode=READER_RS_REFLOW_GLOBAL;c.anchor=&a;
    literal_and_adapter(ob,A,t,s,c,nullptr);
    std::string v2=render(t,s,2,new_id());v2record rec=read_v2(v2);exr_anchor scoped=as_anchor(rec.s,true),dropped=as_anchor(rec.s,false);
    exr_anchor_match ms{},md{};SDK(exr_anchor_resolve_ex(gb,&scoped,nullptr,&ms,&e_));SDK(exr_anchor_resolve_ex(gb,&dropped,nullptr,&md,&e_));
    ob.o.set("scope_comparison",object().str("with_chapter",state_name(ms.state)).str("chapter_dropped",state_name(md.state)).dump());
    receiver_result(ob,"v2_proposal",READER_RS_OK,ms,s,false,"no SDK write: global EPUB progress/notes are not used by the bounded product path");
    exr_anchor_free(&a);exr_document_free(ga);exr_document_free(gb);cases.push_back(ob.o.dump());
  }

  stage("global EPUB case done");
  /* ---- EPUB bounded chapter-local ---- */
  exr_font *fnt=nullptr;SDK(exr_font_open(font.c_str(),&fnt,&e_));
  {
    int64_t ea=catalog_id(A,"epub"),eb=catalog_id(B,"epub");
    exr_publication *pa=nullptr,*pb=nullptr;
    for(auto pr:{std::make_pair(&A,ea),std::make_pair(&B,eb)}){exr_source src{};SDK(exr_library_source(pr.first->lib,pr.second,&src,&e_));exr_publication **out=pr.first==&A?&pa:&pb;exr_error e{};if(exr_publication_open_source(&src,out,&e)!=EXR_OK){src.release(src.context);fatal(std::string("publication: ")+e.message);}}
    size_t count=0;const exr_part *parts=exr_publication_parts(pa,&count);
    std::vector<std::string> spine;for(size_t i=0;i<count;i++)spine.push_back(esc(parts[i].path?parts[i].path:""));
    lifecycle.push_back(object().str("step","epub-spine").set("paths",array(spine)).dump());
    exr_layout_config config=exr_layout_config_defaults();exr_chapter_options options=exr_chapter_options_defaults();
    auto pager=[&](exr_publication *p,size_t part){exr_pager *pg=nullptr;SDK(exr_publication_pager_create(p,part,fnt,&config,&options,&pg,&e_));return pg;};
    auto chapter_text=[&](exr_pager *pg){std::string out;size_t size=exr_pager_chapter_statistics(pg).projection_bytes;
      SDK(exr_pager_read_text(pg,0,size,[](void *c,const char *t,size_t n,exr_error *){((std::string *)c)->append(t,n);return EXR_OK;},&out,nullptr,&e_));return out;};
    auto epub_case=[&](size_t part,const char *kind,const std::string &aid,size_t start,size_t end,const char *label){
      observation ob;ob.o.str("id",label).str("book","epub").str("kind",std::string(kind)=="progress"?"progress":aid.rfind("bm",0)==0?"bookmark":"highlight")
        .str("sdk_capture","exr_pager_anchor_create").str("mode","epub_chapter").set("part",num(part)).str("part_path",parts[part].path);
      exr_pager *ga=pager(pa,part);exr_anchor a{};SDK(exr_pager_anchor_create(ga,start,end,nullptr,&a,&e_));sel s=from(a);ob.capture(s);
      exr_document *pd=nullptr;SDK(exr_publication_load(pa,part,&pd,&e_));exr_anchor d{};exr_error de{};exr_status ds=exr_anchor_create(pd,start,end,&d,&de);
      ob.o.set("pager_equals_part_document_capture",boolean(ds==EXR_OK&&from(d).exact==s.exact&&from(d).prefix==s.prefix&&from(d).suffix==s.suffix&&from(d).chapter==s.chapter));exr_anchor_free(&d);exr_document_free(pd);
      exr_anchor_match self{};SDK(exr_pager_anchor_resolve(ga,&a,nullptr,&self,&e_));ob.o.str("sender_resolve",state_name(self.state));
      target t{kind,"epub",aid,"epub_chapter",parts[part].path,"",0,std::string("note ")+label};reader_rs_capture c{};c.mode=READER_RS_EPUB_CHAPTER;c.anchor=&a;c.part_path=parts[part].path;std::string wire;
      literal_and_adapter(ob,A,t,s,c,&wire);
      size_t before=count_epub(B,eb);
      if(!wire.empty()){
        reader_rs_record rec{};reader_rs_error re{};if(reader_rs_decode(B.store,wire.data(),wire.size(),&rec,&re)!=READER_RS_OK)fatal("decode epub");
        exr_anchor_match own{};reader_rs_error oe{};reader_rs_resolve_epub(pa,ga,part,&rec,nullptr,&own,&oe);
        if(oe.code!=READER_RS_IDENTITY)expect(own.state==self.state&&own.start==self.start,std::string(label)+" decoded v1 resolves identically on the sender");
        size_t bp=SIZE_MAX;reader_rs_status route=reader_rs_epub_part(pb,rec.part_path,&bp,&re);exr_anchor_match m{};int64_t note=0;reader_rs_status st=route;
        if(route==READER_RS_OK){exr_pager *gb=pager(pb,bp);st=reader_rs_store_epub_note(B.lib,eb,pb,gb,bp,&rec,0,&note,&m,&re);exr_pager_free(gb);}
        receiver_result(ob,"v1",st,m,s,note>0,route==READER_RS_OK?"":std::string("route refused: ")+gap_name(re.gap));
        expect((count_epub(B,eb)==before+1)==(note>0),std::string(label)+" SDK EPUB note count follows FOUND only");
        reader_rs_record_free(&rec);
      }else{
        std::string v2=render(t,s,2,new_id());v2record rec=read_v2(v2);size_t bp=SIZE_MAX;reader_rs_error re{};
        reader_rs_status route=reader_rs_epub_part(pb,parts[part].path,&bp,&re);exr_anchor_match m{};bool persisted=false;std::string note;
        if(route==READER_RS_OK){
          exr_pager *gb=pager(pb,bp);exr_anchor q=as_anchor(rec.s,false);q.chapter=s.has_chapter?&rec.s.chapter[0]:nullptr;
          SDK(exr_pager_anchor_resolve(gb,&q,nullptr,&m,&e_));
          if(m.state==EXR_ANCHOR_FOUND&&std::string(kind)=="progress"){
            exr_epub_location loc{};loc.part=bp;loc.path=const_cast<char *>(parts[part].path);SDK(exr_pager_anchor_create(gb,m.start,m.start,nullptr,&loc.selector,&e_));
            SDK(exr_library_epub_progress(B.lib,eb,&loc,&e_));exr_anchor_free(&loc.selector);
            exr_epub_location got{};int present=0;SDK(exr_library_epub_progress_get(B.lib,eb,&got,&present,&e_));
            expect(present&&got.part==bp&&got.selector.start==m.start,std::string(label)+" receiver SDK EPUB progress persisted");exr_epub_location_free(&got);persisted=true;
          }else if(m.state==EXR_ANCHOR_FOUND)note="FOUND; SDK bounded EPUB notes require a nonempty quote, so the bookmark stays a product record";
          exr_pager_free(gb);
        }else note=std::string("route refused: ")+gap_name(re.gap);
        receiver_result(ob,"v2_proposal",route,m,s,persisted,note);
      }
      exr_anchor_free(&a);exr_pager_free(ga);cases.push_back(ob.o.dump());
    };
    size_t unique=SIZE_MAX,repeated=SIZE_MAX;
    for(size_t i=0;i<count;i++){size_t same=0;for(size_t j=0;j<count;j++)same+=!std::strcmp(parts[i].path,parts[j].path);if(same==1&&unique==SIZE_MAX)unique=i;if(same>1&&repeated==SIZE_MAX)repeated=i;}
    if(unique==SIZE_MAX||repeated==SIZE_MAX)fatal("fixture spine lacks unique and repeated parts");
    exr_pager *probe=pager(pa,unique);std::string ct=chapter_text(probe);exr_pager_free(probe);
    probe=pager(pa,repeated);std::string rt=chapter_text(probe);exr_pager_free(probe);
    lifecycle.push_back(object().str("step","epub-chapter-text").set("unique_bytes",num(ct.size())).set("repeated_bytes",num(rt.size())).dump());
    size_t q=locate(ct,"阅读进度");epub_case(unique,"annotation","a0000000000000000000000000000e01",q,q+std::strlen("阅读进度"),"epub-highlight-chapter");
    size_t tail=ct.rfind("章末🌙");if(tail==std::string::npos)fatal("chapter lacks end quote");
    lifecycle.push_back(object().str("step","epub-end-quote").set("end",num(tail+std::strlen("章末🌙"))).set("chapter_bytes",num(ct.size())).dump());
    epub_case(unique,"annotation","a0000000000000000000000000000e02",tail,tail+std::strlen("章末🌙"),"epub-highlight-chapter-end");
    epub_case(unique,"progress","",q,q,"epub-progress-point");
    epub_case(unique,"annotation","bm00000000000000000000000000e001",0,0,"epub-bookmark-chapter-start");
    size_t rq=locate(rt,"Repeated spine chapter");epub_case(repeated,"annotation","a0000000000000000000000000000e03",rq,rq+std::strlen("Repeated spine chapter"),"epub-highlight-repeated-spine-route");
    exr_publication_free(pa);exr_publication_free(pb);
  }

  stage("bounded EPUB cases done");
  /* ---- fixed PDF and CBZ ---- */
  auto fixed_book=[&](const std::string &role){
    int64_t ia=catalog_id(A,role),ib=catalog_id(B,role);exr_fixed_open_options o{};o.struct_size=sizeof(o);
    exr_fixed_document *da=nullptr,*db=nullptr;SDK(exr_library_fixed(A.lib,ia,&o,&da,&e_));SDK(exr_library_fixed(B.lib,ib,&o,&db,&e_));
    size_t count=0;const exr_fixed_page *pages=exr_fixed_pages(da,&count);std::vector<std::string> ids;for(size_t i=0;i<count;i++)ids.push_back(esc(pages[i].id));
    lifecycle.push_back(object().str("step",role+"-pages").set("page_ids",array(ids)).dump());
    auto text_of=[&](exr_fixed_document *d,size_t page){exr_fixed_text *t=nullptr;SDK(exr_fixed_load_text(d,page,nullptr,&t,&e_));size_t n=0;const char *s=exr_fixed_text_string(t,&n);std::string out(s?s:"",n);exr_fixed_text_free(t);return out;};
    auto fixed_case=[&](size_t page,const char *kind,const std::string &aid,size_t start,size_t end,const char *label){
      observation ob;ob.o.str("id",label).str("book",role).str("kind",std::string(kind)=="progress"?"progress":aid.rfind("bm",0)==0?"bookmark":"highlight")
        .str("sdk_capture","exr_fixed_anchor_create").str("mode","fixed_page").set("page",num(page)).str("page_id",pages[page].id);
      exr_fixed_text *ta=nullptr;SDK(exr_fixed_load_text(da,page,nullptr,&ta,&e_));size_t tn=0;exr_fixed_text_string(ta,&tn);ob.o.set("page_text_bytes",num(tn));
      exr_fixed_anchor a{};SDK(exr_fixed_anchor_create(pages[page].id,ta,start,end,&a,&e_));sel s=from(a);ob.capture(s);
      exr_anchor_match self{};SDK(exr_fixed_anchor_resolve(pages[page].id,ta,&a,nullptr,&self,&e_));ob.o.str("sender_resolve",state_name(self.state));exr_fixed_text_free(ta);
      target t{kind,role,aid,"fixed_page","",pages[page].id,page,std::string("note ")+label};reader_rs_capture c{};c.mode=READER_RS_FIXED_PAGE;c.fixed=&a;c.page=page;std::string wire;
      literal_and_adapter(ob,A,t,s,c,&wire);size_t before=count_fixed(B,ib);
      if(!wire.empty()){
        reader_rs_record rec{};reader_rs_error re{};if(reader_rs_decode(B.store,wire.data(),wire.size(),&rec,&re)!=READER_RS_OK)fatal("decode fixed");
        exr_anchor_match m{};int64_t note=0;reader_rs_status st=reader_rs_store_fixed_note(B.lib,ib,db,&rec,0,&note,&m,&re);
        receiver_result(ob,"v1",st,m,s,note>0);
        expect((count_fixed(B,ib)==before+1)==(note>0),std::string(label)+" SDK fixed note count follows FOUND only");reader_rs_record_free(&rec);
      }else{
        std::string v2=render(t,s,2,new_id());v2record rec=read_v2(v2);size_t bp=SIZE_MAX;reader_rs_error re{};
        reader_rs_status route=reader_rs_fixed_page(db,rec.page_id.c_str(),&bp,&re);exr_anchor_match m{};bool persisted=false;
        if(route==READER_RS_OK&&bp==rec.page){
          exr_fixed_text *tb=nullptr;SDK(exr_fixed_load_text(db,bp,nullptr,&tb,&e_));exr_fixed_anchor q{};q.start=rec.s.start;q.end=rec.s.end;q.page_id=&rec.page_id[0];
          q.exact=&rec.s.exact[0];q.prefix=&rec.s.prefix[0];q.suffix=&rec.s.suffix[0];q.exact_size=rec.s.exact.size();q.prefix_size=rec.s.prefix.size();q.suffix_size=rec.s.suffix.size();
          SDK(exr_fixed_anchor_resolve(rec.page_id.c_str(),tb,&q,nullptr,&m,&e_));exr_fixed_text_free(tb);
          if(m.state==EXR_ANCHOR_FOUND&&std::string(kind)=="progress"){
            exr_book *books=nullptr;size_t bc=0;SDK(exr_library_books(B.lib,nullptr,&books,&bc,&e_));
            for(size_t i=0;i<bc;i++)if(books[i].id==ib){exr_book u=books[i];u.position=bp;SDK(exr_library_update(B.lib,&u,&e_));persisted=true;}
            exr_books_free(books,bc);SDK(exr_library_books(B.lib,nullptr,&books,&bc,&e_));
            for(size_t i=0;i<bc;i++)if(books[i].id==ib)expect(books[i].position==bp,std::string(label)+" receiver SDK page progress persisted");
            exr_books_free(books,bc);
          }else if(m.state==EXR_ANCHOR_FOUND){
            exr_fixed_note n{};n.book_id=ib;n.page=bp;n.start=n.end=m.start;n.text=const_cast<char *>("bookmark");int64_t id=0;
            SDK(exr_library_fixed_note(B.lib,&n,nullptr,&id,&e_));persisted=id>0;
            expect(count_fixed(B,ib)==before+1,std::string(label)+" receiver fixed point note persisted");
          }
        }
        receiver_result(ob,"v2_proposal",route,m,s,persisted);
      }
      exr_fixed_anchor_free(&a);cases.push_back(ob.o.dump());
    };
    if(role=="pdf"){
      std::string p0=text_of(da,0),p1=text_of(da,1),p2=text_of(da,2);
      expect(text_of(db,0)==p0&&text_of(db,1)==p1,"both libraries extract identical PDF page text");
      lifecycle.push_back(object().str("step","pdf-page-text").set("bytes",array({num(p0.size()),num(p1.size()),num(p2.size())})).dump());
      size_t s0=locate(p0,"Shared quote across pages.");fixed_case(0,"annotation","a0000000000000000000000000000f01",s0,s0+std::strlen("Shared quote across pages."),"pdf-highlight-page-scoped");
      size_t s1=locate(p1,"selection target");fixed_case(1,"annotation","a0000000000000000000000000000f02",s1,s1+std::strlen("selection target"),"pdf-highlight-ambiguous-repeated-lines");
      fixed_case(0,"annotation","bm00000000000000000000000000f001",s0,s0,"pdf-bookmark-point");
      fixed_case(2,"annotation","bm00000000000000000000000000f002",0,0,"pdf-textless-page-bookmark");
      fixed_case(1,"progress","",0,0,"pdf-progress-page-start");
    }else{
      fixed_case(1,"annotation","bm00000000000000000000000000c001",0,0,"cbz-textless-page-bookmark");
      fixed_case(1,"progress","",0,0,"cbz-progress-textless-page");
    }
    exr_fixed_free(da);exr_fixed_free(db);
  };
  fixed_book("pdf");fixed_book("cbz");

  stage("fixed cases done");
  /* ---- v1 lifecycle: identity, heads, tombstone, retry, offline order, separate recovery ---- */
  {
    const std::string aid="a00000000000000000000000000001fe",key=keys["txt"]+":"+aid;
    size_t at=locate(T,"The repeated phrase appears here.",0);exr_anchor a{};SDK(exr_anchor_create(r.a,at,at+std::strlen("The repeated phrase appears here."),&a,&e_));
    int64_t ma=0,mb=0;std::string h1,h2,h3a,h3b,h4,h5,h6,h7,o1,o2,o3;
    local(A,"txt",aid,"put",&a,"first note",{},&h1);applied sa=apply(A,r,r.ida,r.a,key,ma);
    auto rows=pending(A);expect(rows.size()==1&&rows[0].id==h1,"one outbox row for the new local revision");
    {reader_revision_error e{};expect(reader_revision_retry(A.store,h1.c_str(),READER_REV_DATABASE,&e)==READER_REV_OK,"failed upload records a fixed retry token");}
    flush(A,B);deliver(A,B,h1,false);/* exact duplicate delivery after ack */
    step("create-and-exact-retry",sa,apply(B,r,r.idb,r.b,key,mb));
    expect(pending(A).empty(),"ack removed only the outbox row");
    local(A,"txt",aid,"put",&a,"edited note",{h1},&h2);sa=apply(A,r,r.ida,r.a,key,ma);flush(A,B);step("edit",sa,apply(B,r,r.idb,r.b,key,mb));
    local(A,"txt",aid,"put",&a,"A concurrent",heads(A,"annotation",key),&h3a);sa=apply(A,r,r.ida,r.a,key,ma);
    local(B,"txt",aid,"put",&a,"B concurrent",heads(B,"annotation",key),&h3b);applied sb=apply(B,r,r.idb,r.b,key,mb);
    step("concurrent-local-before-exchange",sa,sb);
    flush(A,B);flush(B,A);reader_revision_state st{};heads(A,"annotation",key,&st);
    expect(st.heads==2&&!st.projection_safe,"both concurrent heads retained");
    step("concurrent-after-exchange",apply(A,r,r.ida,r.a,key,ma),apply(B,r,r.idb,r.b,key,mb),"SDK notes keep each side's last safe text");
    local(A,"txt",aid,"put",&a,"merged note",heads(A,"annotation",key),&h4);flush(A,B);
    step("merge",apply(A,r,r.ida,r.a,key,ma),apply(B,r,r.idb,r.b,key,mb));
    local(A,"txt",aid,"delete",&a,"",heads(A,"annotation",key),&h5);flush(A,B);
    step("tombstone",apply(A,r,r.ida,r.a,key,ma),apply(B,r,r.idb,r.b,key,mb));
    local(A,"txt",aid,"put",&a,"implicit resurrection",{h5},&h6);flush(A,B);
    step("put-after-delete-blocked",apply(A,r,r.ida,r.a,key,ma),apply(B,r,r.idb,r.b,key,mb));
    local(A,"txt",aid,"restore",&a,"restored note",{h5,h6},&h7);
    {reader_revision_state rs{};heads(A,"annotation",key,&rs);lifecycle.push_back(object().str("step","restore-heads-on-A").set("heads",num(rs.heads)).set("safe",boolean(rs.projection_safe!=0)).dump());}
    flush(A,B);step("restore",apply(A,r,r.ida,r.a,key,ma),apply(B,r,r.idb,r.b,key,mb));
    /* Offline: three chained edits delivered newest-first. */
    local(A,"txt",aid,"put",&a,"offline one",heads(A,"annotation",key),&o1);local(A,"txt",aid,"put",&a,"offline two",{o1},&o2);local(A,"txt",aid,"put",&a,"offline three",{o2},&o3);
    deliver(A,B,o3);step("offline-newest-first",apply(A,r,r.ida,r.a,key,ma),apply(B,r,r.idb,r.b,key,mb),"missing parents keep SDK unchanged");
    deliver(A,B,o2);step("offline-middle",applied{},apply(B,r,r.idb,r.b,key,mb));
    deliver(A,B,o1);step("offline-complete",applied{},apply(B,r,r.idb,r.b,key,mb));
    /* SDK and product are separate commits. After both commit, a restart loses
       the in-memory note map; reconcile must adopt the committed note once. */
    std::string c1,c2;local(A,"txt",aid,"put",&a,"after crash",heads(A,"annotation",key),&c1);flush(A,B);
    applied before=apply(B,r,r.idb,r.b,key,mb);
    auto restart=[&]{exr_document_free(r.b);r.b=nullptr;close_side(B);open_side(B);mb=0;SDK(exr_library_document(B.lib,r.idb,&r.b,&e_));};
    restart();applied first=apply(B,r,r.idb,r.b,key,mb);mb=0;applied second=apply(B,r,r.idb,r.b,key,mb);
    step("restart-after-sdk-commit",applied{},first,"in-memory SDK note map lost; identical content is adopted");step("restart-reconcile-again",applied{},second,"second reconcile adopts again");
    expect(first.action=="adopted"&&second.action=="adopted"&&second.notes==before.notes,"restart reconcile adopts the committed SDK note without duplication");
    /* Product commit succeeds, SDK step is interrupted, then the edit arrives
       after restart: schema1 has no annotation->SDK note map, so the stale
       note cannot be identified. Recorded as an open gap, not a pass. */
    local(A,"txt",aid,"put",&a,"edit across restart",heads(A,"annotation",key),&c2);flush(A,B);restart();
    applied gap=apply(B,r,r.idb,r.b,key,mb);
    step("restart-before-sdk-step-with-new-text",applied{},gap,"durable annotation map gap");
    lifecycle.push_back(object().str("step","durable-annotation-map-gap").set("notes_before",num(second.notes)).set("notes_after",num(gap.notes))
      .set("stale_note_retained",boolean(gap.notes>second.notes)).dump());
    {int64_t bad=0;exr_anchor_match m{};reader_rs_error re{};char *w=nullptr;size_t n=0;reader_revision_info i{};reader_revision_selection sl{};reader_revision_error e{};
     reader_revision_selected(B.store,"annotation",key.c_str(),&w,&n,&i,&sl,&e);reader_rs_record rec{};reader_rs_decode(B.store,w,n,&rec,&re);
     reader_rs_status fs=reader_rs_store_reflow_note(B.lib,999999,r.b,&rec,0,&bad,&m,&re);
     reader_revision_state after{};heads(B,"annotation",key,&after);
     expect(fs==READER_RS_SDK&&after.projection_safe&&pending(B).empty(),"failed SDK write leaves product history and outbox untouched");
     reader_rs_record_free(&rec);reader_revision_bytes_free(w);}
    exr_anchor_free(&a);
  }
  {exr_anchor p{};exr_anchor_state ps{};SDK(exr_library_progress_get(B.lib,r.idb,&p,&ps,&e_));lifecycle.push_back(object().str("step","receiver-progress-final").set("start",num(p.start)).str("state",state_name(ps)).dump());exr_anchor_free(&p);}

  expect(receiver_mislocated==0,"zero receiver FOUND results at a different range",num(receiver_mislocated));
  expect(unresolved_writes==0,"zero SDK writes without FOUND",num(unresolved_writes));
  exr_document_free(r.a);exr_document_free(r.b);exr_font_free(fnt);
  object sdk_ids;for(const char *role:{"spacer","txt","edited","epub","pdf","cbz"}){sdk_ids.set(role,object().set("A",A.ids.count(role)?snum(A.ids[role]):"null").set("B",snum(B.ids[role])).dump());}
  object books;for(const char *role:{"txt","edited","spacer","epub","pdf","cbz"})books.set(role,object().str("book_key",keys[role]).set("bytes",num(sizes[role])).dump());
  close_side(A);close_side(B);
  object out;out.str("sdk_version",exr_version()).str("parser_version",parser_version).str("revisions_version",READER_REVISIONS_VERSION).str("adapter_version",READER_READING_STATE_VERSION)
    .str("sqlite_version",sqlite3_libversion()).str("sqlite_source_id",sqlite3_sourceid()).set("books",books.dump()).set("sdk_ids",sdk_ids.dump())
    .set("cases",array(cases)).set("lifecycle",array(lifecycle)).set("exchanged",array(exchanged)).set("checks",array(checks))
    .set("receiver_found",num(receiver_found)).set("receiver_mislocated",num(receiver_mislocated)).set("unresolved_writes",num(unresolved_writes)).set("failures",num(failures));
  std::ofstream rep(report_path,std::ios::binary);rep<<out.dump()<<"\n";
  std::printf("reading-state probe: %zu cases, %zu checks, %zu failures\n",cases.size(),checks.size(),failures);
  return failures?1:0;
}
