/* SPDX-License-Identifier: MIT */
/* Installed C++ consumer of EXReaderReadingCommands. Every selector is a real
   public-SDK capture over originals generated in Actions; every result is read
   back through the public revision API (get/validate/decode/heads/selected/
   outbox), never from the producer's own output. Modes: suite (default), and
   setup/race/verify for two real processes on one product catalog. */
#include <reader_reading_commands.h>
#include <reader_commands.h>
#include <exreader.h>
#include <sqlite3.h>
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <functional>
#include <map>
#include <memory>
#include <set>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

namespace {
/* ---------- report ---------- */
std::string esc(const std::string &s){
  static const char hex[]="0123456789abcdef";std::string o="\"";
  for(unsigned char c:s){if(c=='"'||c=='\\'){o+='\\';o+=(char)c;}else if(c<0x20){o+="\\u00";o+=hex[c>>4];o+=hex[c&15];}else o+=(char)c;}
  return o+"\"";
}
std::string num(unsigned long long v){return std::to_string(v);}
std::string boolean(bool v){return v?"true":"false";}
struct object {
  std::vector<std::pair<std::string,std::string>> fields;
  object &set(const std::string &k,const std::string &raw){for(auto &f:fields)if(f.first==k){f.second=raw;return *this;}fields.emplace_back(k,raw);return *this;}
  object &str(const std::string &k,const std::string &v){return set(k,esc(v));}
  std::string dump()const{std::string o="{";for(size_t i=0;i<fields.size();i++){if(i)o+=",";o+=esc(fields[i].first)+":"+fields[i].second;}return o+"}";}
};
std::string array(const std::vector<std::string> &items){std::string o="[";for(size_t i=0;i<items.size();i++){if(i)o+=",";o+=items[i];}return o+"]";}
std::vector<std::string> checks,cases;
size_t failures=0;
void expect(bool ok,const std::string &name,const std::string &detail=""){
  if(!ok){failures++;std::fprintf(stderr,"FAIL %s %s\n",name.c_str(),detail.c_str());}
  checks.push_back(object().str("name",name).set("pass",boolean(ok)).str("detail",detail).dump());
}
[[noreturn]] void fatal(const std::string &what){std::fprintf(stderr,"FATAL %s\n",what.c_str());std::exit(2);}
void stage(const char *what){std::printf("stage: %s\n",what);std::fflush(stdout);}
std::string read_file(const std::string &path){std::ifstream in(path,std::ios::binary);if(!in)fatal("cannot read "+path);std::ostringstream s;s<<in.rdbuf();return s.str();}
void write_file(const std::string &path,const std::string &data){std::ofstream out(path,std::ios::binary);out<<data;if(!out)fatal("cannot write "+path);}
std::string hexbytes(const std::string &s){static const char h[]="0123456789abcdef";std::string o;for(unsigned char c:s){o+=h[c>>4];o+=h[c&15];}return o;}
#define SDK(call) do{exr_error e_{};exr_status s_=(call);if(s_!=EXR_OK)fatal(std::string(#call)+": "+e_.message);}while(0)

/* ---------- state ---------- */
exr_library *lib=nullptr;reader_revisions *store=nullptr;
std::map<std::string,std::string> keys,shas,paths,formats,originals;
std::map<std::string,int64_t> ids;
std::map<std::string,uint64_t> sizes;
std::string parser;

std::string new_id(){char id[33];reader_revision_error e{};if(reader_revision_new_id(id,&e)!=READER_REV_OK)fatal("new id");return id;}
const char *rc_name(reader_rc_status s){static const char *n[]={"OK","ARGUMENT","MEMORY","ENCODE","UNSAFE","REVISION","SOURCE"};return (unsigned)s<7?n[s]:"UNKNOWN";}
const char *mode_name(reader_rs_mode m){return m==READER_RS_REFLOW_GLOBAL?"reflow_global":m==READER_RS_EPUB_CHAPTER?"epub_chapter":"fixed_page";}

/* ---------- decoded view of retained bytes ---------- */
struct view {
  std::string kind,op,book,aid,parser,mode,part_path,page_id,exact,prefix,suffix,chapter,text;
  bool has_chapter=false,has_location=false;
  uint64_t version=0,part=0,page=0,start=0,end=0;
};
bool sel_eq(const view &a,const view &b){
  return a.has_location&&b.has_location&&a.mode==b.mode&&a.version==b.version&&a.part==b.part&&a.page==b.page&&a.start==b.start&&a.end==b.end&&
    a.part_path==b.part_path&&a.page_id==b.page_id&&a.exact==b.exact&&a.prefix==b.prefix&&a.suffix==b.suffix&&a.has_chapter==b.has_chapter&&
    a.chapter==b.chapter&&a.parser==b.parser;
}
view decode_view(const std::string &wire){
  view v;reader_rs_record r{};reader_rs_error e{};
  if(reader_rs_decode(store,wire.data(),wire.size(),&r,&e)!=READER_RS_OK)return v;
  v.kind=r.entity_kind;v.op=r.operation;v.book=r.book_key;v.aid=r.annotation_id;v.has_location=r.has_location!=0;
  v.mode=mode_name(r.mode);
  if(r.has_location){
    v.parser=r.parser_version;v.version=r.anchor_version;v.part=r.part;v.page=r.page;v.start=r.start;v.end=r.end;
    v.part_path=r.part_path?r.part_path:"";v.page_id=r.page_id?r.page_id:"";
    v.exact.assign(r.exact?r.exact:"",r.exact_size);v.prefix.assign(r.prefix?r.prefix:"",r.prefix_size);v.suffix.assign(r.suffix?r.suffix:"",r.suffix_size);
    v.has_chapter=r.chapter!=nullptr;v.chapter=r.chapter?r.chapter:"";v.text=r.note_text?r.note_text:"";
  }
  reader_rs_record_free(&r);return v;
}

/* ---------- real SDK captures ---------- */
struct cap {
  exr_anchor a{};exr_fixed_anchor f{};reader_rs_capture c{};size_t part=0;
  cap()=default;cap(const cap &)=delete;cap &operator=(const cap &)=delete;
  ~cap(){exr_anchor_free(&a);exr_fixed_anchor_free(&f);}
  view want(unsigned version=2)const{
    view v;v.has_location=true;v.mode=mode_name(c.mode);v.version=version;v.parser=parser;
    if(c.mode==READER_RS_FIXED_PAGE){
      v.page_id=f.page_id;v.page=c.page;v.start=f.start;v.end=f.end;v.exact.assign(f.exact?f.exact:"",f.exact_size);
      v.prefix.assign(f.prefix?f.prefix:"",f.prefix_size);v.suffix.assign(f.suffix?f.suffix:"",f.suffix_size);
    }else{
      v.start=a.start;v.end=a.end;v.exact=a.exact?a.exact:"";v.prefix=a.prefix?a.prefix:"";v.suffix=a.suffix?a.suffix:"";
      if(c.mode==READER_RS_EPUB_CHAPTER){v.part_path=c.part_path;v.part=version==2?part:0;}
      else if(version==2){v.has_chapter=a.chapter!=nullptr;v.chapter=a.chapter?a.chapter:"";}
    }
    return v;
  }
};
using capture_ptr=std::unique_ptr<cap>;
capture_ptr reflow_cap(exr_document *doc,size_t start,size_t end){
  capture_ptr p(new cap);exr_error e{};
  if(exr_anchor_create(doc,start,end,&p->a,&e)!=EXR_OK)fatal(std::string("anchor: ")+e.message);
  p->c.mode=READER_RS_REFLOW_GLOBAL;p->c.anchor=&p->a;return p;
}
capture_ptr epub_cap(exr_pager *pager,const char *path,size_t part,size_t start,size_t end){
  capture_ptr p(new cap);exr_error e{};
  if(exr_pager_anchor_create(pager,start,end,nullptr,&p->a,&e)!=EXR_OK)fatal(std::string("pager anchor: ")+e.message);
  p->c.mode=READER_RS_EPUB_CHAPTER;p->c.anchor=&p->a;p->c.part_path=path;p->part=part;return p;
}
capture_ptr fixed_cap(exr_fixed_document *doc,const exr_fixed_page *pages,size_t page,size_t start,size_t end){
  capture_ptr p(new cap);exr_error e{};exr_fixed_text *t=nullptr;
  if(exr_fixed_load_text(doc,page,nullptr,&t,&e)!=EXR_OK)fatal(std::string("fixed text: ")+e.message);
  exr_status s=exr_fixed_anchor_create(pages[page].id,t,start,end,&p->f,&e);exr_fixed_text_free(t);
  if(s!=EXR_OK)fatal(std::string("fixed anchor: ")+e.message);
  p->c.mode=READER_RS_FIXED_PAGE;p->c.fixed=&p->f;p->c.page=page;return p;
}
size_t locate(const std::string &text,const std::string &needle,int occurrence=0){
  size_t at=std::string::npos,from=0;for(int i=0;i<=occurrence;i++){at=text.find(needle,from);if(at==std::string::npos)fatal("fixture text lacks "+needle);from=at+1;}return at;
}

/* ---------- command and public readback ---------- */
struct outcome {reader_rc_status st;reader_rc_result res;reader_rc_error err;};
outcome run(reader_rc_kind kind,reader_rc_operation op,const std::string &book,const std::string &aid,const reader_rs_capture *capture,size_t part,
    const char *text,const std::string &rev,const std::vector<std::string> &heads,const char *parser_version=nullptr){
  std::vector<const char *> hp;for(auto &h:heads)hp.push_back(h.c_str());
  reader_rc_context ctx{};ctx.store=store;ctx.revision_id=rev.c_str();ctx.expected_heads=hp.empty()?nullptr:hp.data();ctx.expected_count=hp.size();
  ctx.parser_version=parser_version?parser_version:parser.c_str();
  reader_rc_command cmd{};cmd.kind=kind;cmd.operation=op;cmd.book_key=book.c_str();cmd.annotation_id=aid.empty()?nullptr:aid.c_str();
  cmd.capture=capture;cmd.part=part;cmd.text=text;
  outcome o{};o.st=reader_rc_apply(&ctx,&cmd,&o.res,&o.err);return o;
}
std::string describe(const outcome &o){
  return std::string(rc_name(o.st))+" rev="+std::to_string(o.err.revision.code)+" enc="+std::to_string((int)o.err.encode.code)+"/"+std::to_string((int)o.err.encode.gap)+" "+o.err.message;
}
struct back {bool ok=false;std::string wire;reader_revision_info info{};view v;std::vector<std::string> parents;};
std::vector<std::string> parse_parents(const std::string &wire){
  std::vector<std::string> out;size_t at=wire.find("\"parents\":[");if(at==std::string::npos)return out;
  size_t i=at+11;while(i<wire.size()&&wire[i]!=']'){if(wire[i]=='"'){size_t j=wire.find('"',i+1);out.push_back(wire.substr(i+1,j-i-1));i=j+1;}else ++i;}
  std::sort(out.begin(),out.end());return out;
}
back readback(const std::string &id){
  back b;char *w=nullptr;size_t n=0;reader_revision_error e{};
  if(reader_revision_get(store,id.c_str(),&w,&n,&b.info,&e)!=READER_REV_OK)return b;
  b.wire.assign(w,n);reader_revision_bytes_free(w);
  reader_revision_info vi{};
  if(reader_revision_validate(store,b.wire.data(),b.wire.size(),b.info.sha256,&vi,&e)!=READER_REV_OK)return b;
  b.v=decode_view(b.wire);b.parents=parse_parents(b.wire);b.ok=true;return b;
}
std::vector<std::string> heads_of(const char *kind,const std::string &key,reader_revision_state *state=nullptr){
  std::vector<std::string> out;reader_revision_state st{};reader_revision_error e{};
  reader_revision_heads(store,kind,key.c_str(),[](void *p,const reader_revision_head *h){((std::vector<std::string> *)p)->push_back(h->revision_id);return 0;},&out,&st,&e);
  std::sort(out.begin(),out.end());if(state)*state=st;return out;
}
struct row {std::string id,sha,key;};
std::vector<row> outbox(){
  std::vector<row> rows;reader_revision_error e{};
  reader_revision_outbox(store,100,[](void *p,const reader_revision_outbox_row *r){((std::vector<row> *)p)->push_back({r->info.revision_id,r->info.sha256,r->info.entity_key});return 0;},&rows,&e);
  return rows;
}
void drain(){for(const row &r:outbox()){reader_revision_error e{};reader_revision_ack(store,r.id.c_str(),r.sha.c_str(),&e);}}
size_t outbox_count(const std::string &id){size_t n=0;for(const row &r:outbox())n+=r.id==id;return n;}

struct entity {bool progress=false;std::string book,aid,key;std::vector<std::string> heads;
  const char *kind()const{return progress?"progress":"annotation";}};
entity make_progress(const std::string &book){entity e;e.progress=true;e.book=book;e.key=book;e.heads=heads_of("progress",e.key);return e;}
entity make_annotation(const std::string &book,const std::string &aid){entity e;e.book=book;e.aid=aid;e.key=book+":"+aid;e.heads=heads_of("annotation",e.key);return e;}
std::string state_text(const entity &e){
  reader_revision_state st{};std::vector<std::string> h=heads_of(e.kind(),e.key,&st);std::string o;
  for(auto &x:h)o+=x+",";
  o+="|"+num(st.revisions)+"/"+num(st.heads)+"/"+num(st.missing_parents)+"/"+num(st.projection_safe)+"/"+num(st.deleted)+"|";
  std::vector<std::string> ob;for(const row &r:outbox())ob.push_back(r.id);std::sort(ob.begin(),ob.end());for(auto &x:ob)o+=x+",";
  return o;
}
std::vector<std::string> sorted(std::vector<std::string> v){std::sort(v.begin(),v.end());v.erase(std::unique(v.begin(),v.end()),v.end());return v;}

/* One committed command: every property is read back through public APIs. */
bool commit(const std::string &label,const std::string &what,entity &e,reader_rc_kind kind,reader_rc_operation op,const reader_rs_capture *capture,
    size_t part,const char *text,const view *want,std::string *rev_out=nullptr,const char *expected_op=nullptr){
  const std::string N=label+" "+what+": ";std::string rev=new_id();size_t before=outbox().size();std::vector<std::string> parents=sorted(e.heads);
  outcome o=run(kind,op,e.book,e.aid,capture,part,text,rev,e.heads);
  bool ok=o.st==READER_RC_OK&&o.res.created==1&&rev==o.res.revision_id;
  expect(ok,N+"commits one new revision",describe(o));
  if(!ok)return false;
  if(e.aid.empty()&&!e.progress){e.aid=o.res.annotation_id;e.key=e.book+":"+e.aid;}
  back b=readback(rev);expect(b.ok,N+"retained bytes revalidate");if(!b.ok)return false;
  const char *opname=expected_op?expected_op:op==READER_RC_PUT?"put":op==READER_RC_DELETE?"delete":"restore";
  expect(std::string(o.res.sha256)==b.info.sha256&&o.res.bytes==b.wire.size()&&b.info.bytes==b.wire.size(),N+"result digest and size equal the retained original");
  expect(std::string(b.info.operation)==opname&&e.key==b.info.entity_key&&e.key==o.res.entity_key,N+"operation and entity identity read back");
  expect(b.parents==parents,N+"wire parents are the complete observed heads",num(b.parents.size())+" vs "+num(parents.size()));
  if(op==READER_RC_DELETE)expect(!b.v.has_location,N+"tombstone carries no location");
  else if(want){
    expect(sel_eq(b.v,*want),N+"selector read back equals the SDK capture",b.v.mode+" v"+num(b.v.version));
    if(!e.progress&&text)expect(b.v.text==text,N+"annotation text read back");
  }
  reader_revision_state st{};std::vector<std::string> hs=heads_of(e.kind(),e.key,&st);
  expect(hs.size()==1&&hs[0]==rev&&st.projection_safe&&(st.deleted!=0)==(op==READER_RC_DELETE),N+"history has exactly the new safe head");
  expect(outbox().size()==before+1&&outbox_count(rev)==1,N+"one new outbox row");
  char *sw=nullptr;size_t sn=0;reader_revision_info si{};reader_revision_selection sel{};reader_revision_error se{};
  reader_revision_status ss=reader_revision_selected(store,e.kind(),e.key.c_str(),&sw,&sn,&si,&sel,&se);
  expect(ss==READER_REV_OK&&sel.kind==READER_SELECTION_SAFE&&sn==b.wire.size()&&sw&&!std::memcmp(sw,b.wire.data(),sn),N+"selected head is the exact new bytes");
  reader_revision_bytes_free(sw);
  e.heads={rev};if(rev_out)*rev_out=rev;return true;
}
bool refused(const std::string &label,const std::string &what,entity &e,reader_rc_kind kind,reader_rc_operation op,const reader_rs_capture *capture,
    size_t part,const char *text,reader_rc_status want,const std::vector<std::string> *heads=nullptr,int revision_code=-1,const std::string &rev_in=""){
  const std::string N=label+" "+what+": ";std::string rev=rev_in.empty()?new_id():rev_in,s0=state_text(e);
  outcome o=run(kind,op,e.book,e.aid,capture,part,text,rev,heads?*heads:e.heads);
  bool ok=o.st==want&&o.res.created==0&&(revision_code<0||o.err.revision.code==(reader_revision_status)revision_code);
  expect(ok,N+"is refused with the expected status",describe(o));
  expect(state_text(e)==s0,N+"history and outbox are unchanged");
  expect(!readback(rev).ok,N+"refused revision is not retained");
  expect(std::strlen(o.err.message)<160&&o.err.message[0],N+"error text is fixed and bounded");
  return ok;
}

/* ---------- SDK source, notes and progress snapshot ---------- */
std::string sdk_snapshot(){
  std::ostringstream o;
  for(const char *role:{"txt","epub","pdf","cbz","epubg"}){
    int64_t id=ids[role];exr_error e{};
    void *blob=nullptr;size_t size=0;exr_status bs=exr_library_blob(lib,id,0,&blob,&size,&e);
    const std::string &orig=originals[std::strcmp(role,"epubg")?role:"epub"];
    o<<role<<":blob="<<bs<<"/"<<size<<"/"<<(bs==EXR_OK&&size==orig.size()&&!std::memcmp(blob,orig.data(),size));if(blob)exr_free(blob);
    exr_note *n=nullptr;size_t c=0;exr_status ns=exr_library_notes(lib,id,&n,&c,&e);o<<" notes="<<ns<<"/"<<c;
    for(size_t i=0;ns==EXR_OK&&i<c;i++)o<<"["<<n[i].id<<","<<n[i].start<<","<<n[i].end<<","<<(n[i].text?n[i].text:"")<<"]";
    if(ns==EXR_OK)exr_notes_free(n,c);
    exr_fixed_note *fn=nullptr;size_t fc=0;exr_status fs=exr_library_fixed_notes(lib,id,&fn,&fc,&e);o<<" fixed="<<fs<<"/"<<fc;if(fs==EXR_OK)exr_fixed_notes_free(fn,fc);
    exr_epub_note *en=nullptr;size_t ec=0;exr_status es=exr_library_epub_notes(lib,id,&en,&ec,&e);o<<" epub="<<es<<"/"<<ec;if(es==EXR_OK)exr_epub_notes_free(en,ec);
    if(!std::strcmp(role,"txt")||!std::strcmp(role,"epubg")){
      exr_anchor p{};exr_anchor_state ps{};exr_status st=exr_library_progress_get(lib,id,&p,&ps,&e);
      o<<" progress="<<st<<"/"<<(int)ps<<"/"<<p.start<<"/"<<p.end;if(st==EXR_OK)exr_anchor_free(&p);
    }
    if(!std::strcmp(role,"epub")){
      exr_epub_location loc{};int present=0;exr_status st=exr_library_epub_progress_get(lib,id,&loc,&present,&e);
      o<<" epub_progress="<<st<<"/"<<present<<"/"<<loc.part;if(st==EXR_OK)exr_epub_location_free(&loc);
    }
    o<<"\n";
  }
  exr_book *books=nullptr;size_t bc=0;exr_error e{};
  if(exr_library_books(lib,nullptr,&books,&bc,&e)==EXR_OK){for(size_t i=0;i<bc;i++)o<<"book "<<books[i].id<<" pos="<<books[i].position<<"\n";exr_books_free(books,bc);}
  return o.str();
}

/* ---------- lifecycle of one subject through every command ---------- */
struct subject {std::string label;reader_rc_kind kind;std::string book;const cap *capture;view want;std::function<void(const std::string &)> extra;};
void lifecycle(const subject &s,const std::string &forced_aid=""){
  size_t f0=failures;const std::string base=sdk_snapshot();
  bool progress=s.kind==READER_RC_PROGRESS;
  entity e=progress?make_progress(s.book):make_annotation(s.book,forced_aid.empty()?new_id():forced_aid);
  if(!progress&&forced_aid=="-"){e.aid.clear();e.key=e.book;}
  std::string h1,h2,h3,h4;const reader_rs_capture *c=&s.capture->c;size_t part=s.capture->part;
  reader_rs_capture dc{};dc.mode=c->mode;
  if(!commit(s.label,"create",e,s.kind,READER_RC_PUT,c,part,progress?nullptr:"first note \xe2\x9c\x93",&s.want,&h1))return;
  if(s.extra)s.extra(readback(h1).wire);
  std::string last=h1;
  if(!progress){
    view keep=s.want;
    if(!commit(s.label,"note-body edit keeps the selector",e,READER_RC_NOTE_TEXT,READER_RC_PUT,nullptr,0,"second \xe7\xbc\x96\xe8\xbe\x91 \xf0\x9f\x99\x82",&keep,&h2))return;
    outcome retry=run(READER_RC_NOTE_TEXT,READER_RC_PUT,e.book,e.aid,nullptr,0,"second \xe7\xbc\x96\xe8\xbe\x91 \xf0\x9f\x99\x82",h2,{h1});
    expect(retry.st==READER_RC_OK&&retry.res.created==0&&std::string(retry.res.sha256)==readback(h2).info.sha256&&heads_of("annotation",e.key)==std::vector<std::string>{h2}&&outbox_count(h2)==1,
      s.label+" lost-response retry of the edit with the same ID is an exact no-op",describe(retry));
    last=h2;
  }
  std::string before=state_text(e);
  if(!commit(s.label,"explicit delete",e,s.kind,READER_RC_DELETE,&dc,0,nullptr,nullptr,&h3))return;
  if(!progress)refused(s.label,"note edit over a tombstone",e,READER_RC_NOTE_TEXT,READER_RC_PUT,nullptr,0,"no",READER_RC_SOURCE);
  refused(s.label,"implicit put after delete",e,s.kind,READER_RC_PUT,c,part,progress?nullptr:"resurrect",READER_RC_UNSAFE);
  if(!commit(s.label,"explicit restore",e,s.kind,READER_RC_RESTORE,c,part,progress?nullptr:"restored note",&s.want,&h4))return;
  std::vector<std::string> stale{last};
  refused(s.label,"stale observed head",e,s.kind==READER_RC_NOTE_TEXT?READER_RC_NOTE_TEXT:s.kind,READER_RC_PUT,c,part,progress?nullptr:"stale",READER_RC_UNSAFE,&stale);
  if(!progress)refused(s.label,"stale note edit",e,READER_RC_NOTE_TEXT,READER_RC_PUT,nullptr,0,"stale edit",READER_RC_UNSAFE,&stale);
  expect(sdk_snapshot()==base,s.label+" source books, SDK notes and current progress are unchanged");
  drain();
  cases.push_back(object().str("label",s.label).str("kind",progress?"progress":s.kind==READER_RC_BOOKMARK?"bookmark":"highlight").str("mode",s.want.mode)
    .set("version",num(s.want.version)).set("passed",boolean(failures==f0)).dump());
  (void)before;
}

/* ---------- raw helpers for scenarios the commands refuse to create ---------- */
std::string raw_wire(const entity &e,const std::string &rev,const char *op,const reader_rs_capture *capture,size_t part,const char *text,const std::vector<std::string> &parents,bool v1){
  std::vector<const char *> pp;for(auto &p:parents)pp.push_back(p.c_str());
  reader_rs_envelope env{};env.revision_id=rev.c_str();env.operation=op;env.entity_kind=e.kind();env.book_key=e.book.c_str();env.annotation_id=e.progress?nullptr:e.aid.c_str();
  env.parents=pp.empty()?nullptr:pp.data();env.parent_count=pp.size();env.note_text=text;env.parser_version=parser.c_str();
  char *w=nullptr;size_t n=0;reader_rs_error re{};
  reader_rs_status st=v1?reader_rs_encode(store,&env,capture,&w,&n,&re):reader_rs_encode_v2(store,&env,capture,part,&w,&n,&re);
  if(st!=READER_RS_OK)fatal(std::string("raw encode: ")+re.message);
  std::string out(w,n);reader_rs_free(w);return out;
}
bool raw_local(const std::string &wire){
  reader_revision_info i{};int created=0;reader_revision_error e{};
  return reader_revision_local(store,wire.data(),wire.size(),&i,&created,&e)==READER_REV_OK&&created==1;
}
std::string raw_reading(const std::string &wire,const std::vector<std::string> &heads){
  std::vector<const char *> hp;for(auto &h:heads)hp.push_back(h.c_str());
  reader_revision_info i{};int created=0;reader_revision_error e{};
  return reader_revision_local_reading(store,wire.data(),wire.size(),hp.empty()?nullptr:hp.data(),hp.size(),&i,&created,&e)==READER_REV_OK&&created==1?i.revision_id:"";
}
void add_book(const std::string &role){
  reader_book_command b{};b.operation=READER_COMMAND_PUT;b.book_key=keys[role].c_str();b.format=formats[role].c_str();b.source_sha256=shas[role].c_str();
  std::string title="Reading commands "+role;b.title=title.c_str();b.author="";b.sort_title=title.c_str();b.source_bytes=sizes[role];b.favorite=0;
  reader_command_context ctx{};ctx.store=store;reader_command_result res{};reader_command_error err{};
  if(reader_command_apply_book(&ctx,&b,&res,&err)!=READER_COMMAND_OK)fatal(std::string("book command ")+role+": "+err.message);
}

/* ---------- two-process modes ---------- */
std::string arg_value(int argc,char **argv,const char *name){for(int i=1;i+1<argc;i++)if(!std::strcmp(argv[i],name))return argv[i+1];return "";}
int mode_setup(const std::string &db,const std::string &params){
  reader_revision_error re{};if(reader_revisions_open(db.c_str(),&store,&re)!=READER_REV_OK)fatal(re.message);
  parser=std::string("exreader-sdk-")+exr_version();
  const std::string sha(64,'1'),book="txt:"+sha;
  reader_book_command b{};b.operation=READER_COMMAND_PUT;b.book_key=book.c_str();b.format="txt";b.source_sha256=sha.c_str();b.title="race";b.author="";b.sort_title="race";b.source_bytes=40;
  reader_command_context ctx{};ctx.store=store;reader_command_result res{};reader_command_error err{};
  if(reader_command_apply_book(&ctx,&b,&res,&err)!=READER_COMMAND_OK)fatal(err.message);
  exr_node_input nodes[4];exr_chapter_input chapter;exr_document_input input;exr_document *doc=nullptr;exr_error e{};
  std::memset(nodes,0,sizeof(nodes));std::memset(&chapter,0,sizeof(chapter));std::memset(&input,0,sizeof(input));
  nodes[0].kind=EXR_NODE_DOCUMENT;nodes[0].parent=SIZE_MAX;nodes[1].kind=EXR_NODE_CHAPTER;nodes[1].parent=0;nodes[2].kind=EXR_NODE_PARAGRAPH;nodes[2].parent=1;
  nodes[3].kind=EXR_NODE_TEXT;nodes[3].parent=2;nodes[3].text="race target text for the highlight";
  chapter.path="c.xhtml";chapter.root=1;chapter.in_reading_order=1;input.nodes=nodes;input.node_count=4;input.chapters=&chapter;input.chapter_count=1;
  if(exr_document_create(&input,&doc,&e)!=EXR_OK)fatal(e.message);
  capture_ptr c=reflow_cap(doc,5,11);entity en=make_annotation(book,new_id());std::string head;
  if(!commit("race-setup","create",en,READER_RC_HIGHLIGHT,READER_RC_PUT,&c->c,0,"race",nullptr,&head))fatal("setup commit");
  exr_document_free(doc);
  object o;o.str("book",book).str("aid",en.aid).str("head",head).set("outbox_before",num(outbox().size()));write_file(params,o.dump()+"\n");
  reader_revisions_close(&store,&re);return failures?1:0;
}
std::string json_field(const std::string &json,const std::string &name){
  size_t at=json.find("\""+name+"\":\"");if(at==std::string::npos)return "";at+=name.size()+4;return json.substr(at,json.find('"',at)-at);
}
int mode_race(const std::string &db,const std::string &params,const std::string &barrier,const std::string &rev,const std::string &out){
  std::string p=read_file(params);reader_revision_error re{};
  if(reader_revisions_open(db.c_str(),&store,&re)!=READER_REV_OK)fatal(re.message);
  for(int i=0;i<30000&&!std::ifstream(barrier).good();i++)std::this_thread::sleep_for(std::chrono::milliseconds(1));
  reader_rs_capture dc{};dc.mode=READER_RS_REFLOW_GLOBAL;
  outcome o=run(READER_RC_HIGHLIGHT,READER_RC_DELETE,json_field(p,"book"),json_field(p,"aid"),&dc,0,nullptr,rev,{json_field(p,"head")});
  object r;r.str("rev",rev).str("status",rc_name(o.st)).set("created",num(o.res.created)).set("revision_code",num((unsigned)o.err.revision.code)).str("message",o.err.message);
  write_file(out,r.dump()+"\n");reader_revisions_close(&store,&re);return 0;
}
int mode_verify(const std::string &db,const std::string &params,const std::string &revs,const std::string &out){
  std::string p=read_file(params);reader_revision_error re{};
  if(reader_revisions_open(db.c_str(),&store,&re)!=READER_REV_OK)fatal(re.message);
  std::string book=json_field(p,"book"),aid=json_field(p,"aid"),head=json_field(p,"head"),key=book+":"+aid;
  std::vector<std::string> ids_;std::stringstream ss(revs);std::string item;while(std::getline(ss,item,','))ids_.push_back(item);
  reader_revision_state st{};std::vector<std::string> hs=heads_of("annotation",key,&st);
  size_t retained=0;for(auto &i:ids_)retained+=readback(i).ok;
  size_t rows=0;for(const row &r:outbox())rows+=r.key==key;
  object o;o.set("heads",array([&]{std::vector<std::string> v;for(auto &h:hs)v.push_back(esc(h));return v;}())).set("retained_racers",num(retained)).set("outbox_rows_for_entity",num(rows))
    .set("revisions",num(st.revisions)).set("safe",boolean(st.projection_safe!=0)).set("deleted",boolean(st.deleted!=0)).str("original_head",head);
  write_file(out,o.dump()+"\n");reader_revisions_close(&store,&re);return 0;
}
}

int main(int argc,char **argv){
  std::string mode=arg_value(argc,argv,"--mode");
  if(mode=="setup")return mode_setup(arg_value(argc,argv,"--db"),arg_value(argc,argv,"--params"));
  if(mode=="race")return mode_race(arg_value(argc,argv,"--db"),arg_value(argc,argv,"--params"),arg_value(argc,argv,"--barrier"),arg_value(argc,argv,"--rev"),arg_value(argc,argv,"--out"));
  if(mode=="verify")return mode_verify(arg_value(argc,argv,"--db"),arg_value(argc,argv,"--params"),arg_value(argc,argv,"--revs"),arg_value(argc,argv,"--out"));
  std::string fixtures=arg_value(argc,argv,"--fixtures"),font=arg_value(argc,argv,"--font"),work=arg_value(argc,argv,"--work"),report_path=arg_value(argc,argv,"--report");
  if(fixtures.empty()||font.empty()||work.empty()||report_path.empty())fatal("usage: --fixtures D --font F --work W --report R --sha role=hex ...");
  for(int i=1;i+1<argc;i++)if(!std::strcmp(argv[i],"--sha")){std::string v=argv[i+1];size_t eq=v.find('=');if(eq==std::string::npos)fatal("bad --sha");shas[v.substr(0,eq)]=v.substr(eq+1);}
  const char *roles[][3]={{"txt","book.txt","txt"},{"epub","book.epub","epub"},{"pdf","pages.pdf","pdf"},{"cbz","pages.cbz","cbz"}};
  for(auto &r:roles){
    paths[r[0]]=fixtures+"/"+r[1];formats[r[0]]=r[2];originals[r[0]]=read_file(paths[r[0]]);sizes[r[0]]=originals[r[0]].size();
    if(!shas.count(r[0]))fatal(std::string("missing sha ")+r[0]);keys[r[0]]=std::string(r[2])+":"+shas[r[0]];
  }
  parser=std::string("exreader-sdk-")+exr_version();
  const std::string product=work+"/product.sqlite",library=work+"/library.sqlite";
  {exr_error e{};if(exr_library_open(library.c_str(),&lib,&e)!=EXR_OK)fatal(std::string("library: ")+e.message);
   reader_revision_error r{};if(reader_revisions_open(product.c_str(),&store,&r)!=READER_REV_OK)fatal(std::string("revisions: ")+r.message);}
  /* Originals are imported through the public SDK; the book command records only the verified identity. */
  SDK(exr_library_import(lib,EXR_TXT,originals["txt"].data(),originals["txt"].size(),"txt",&ids["txt"],&e_));
  SDK(exr_library_import_file(lib,EXR_EPUB,paths["epub"].c_str(),"epub",&ids["epub"],&e_));
  SDK(exr_library_import(lib,EXR_EPUB,originals["epub"].data(),originals["epub"].size(),"epub-global",&ids["epubg"],&e_));
  SDK(exr_library_import_file(lib,EXR_PDF,paths["pdf"].c_str(),"pdf",&ids["pdf"],&e_));
  SDK(exr_library_import_file(lib,EXR_CBZ,paths["cbz"].c_str(),"cbz",&ids["cbz"],&e_));
  for(const char *role:{"txt","epub","pdf","cbz"})add_book(role);
  stage("imported and recorded verified originals");

  exr_document *tdoc=nullptr;SDK(exr_library_document(lib,ids["txt"],&tdoc,&e_));
  size_t tn=0;const char *tt=exr_document_text(tdoc,&tn);const std::string T(tt,tn);
  {size_t v=locate(T,"Unique context beta");exr_anchor p{};SDK(exr_anchor_create(tdoc,v,v,&p,&e_));SDK(exr_library_progress(lib,ids["txt"],&p,&e_));exr_anchor_free(&p);}
  const std::string baseline=sdk_snapshot();
  const std::string &TB=keys["txt"];

  /* ---- TXT: reflow_global, UTF-8 boundaries ---- */
  size_t emoji=locate(T,"\xf0\x9f\x99\x82"),first3=locate(T,"\xe8\xaf\xbb"),last=T.rfind("\xf0\x9f\x8e\x89\xe7\xbb\x88");
  if(last==std::string::npos)fatal("fixture lacks end quote");
  {
    exr_anchor bad{};exr_error be{};
    expect(exr_anchor_create(tdoc,emoji+1,emoji+2,&bad,&be)!=EXR_OK,"SDK refuses an invalid UTF-8 boundary so no command is possible");exr_anchor_free(&bad);
    size_t a=emoji-std::strlen("\xe5\x90\x8c\xe6\xad\xa5"),b=emoji+std::strlen("\xf0\x9f\x99\x82\xe6\xb5\x8b");
    capture_ptr hl=reflow_cap(tdoc,a,b);
    expect(hl->want().exact=="\xe5\x90\x8c\xe6\xad\xa5\xf0\x9f\x99\x82\xe6\xb5\x8b","real SDK capture spans CJK and a 4-byte emoji on scalar boundaries",hexbytes(hl->want().exact));
    lifecycle({"txt-highlight",READER_RC_HIGHLIGHT,TB,hl.get(),hl->want(),nullptr});
    capture_ptr end=reflow_cap(tdoc,last,last+std::strlen("\xf0\x9f\x8e\x89\xe7\xbb\x88"));
    lifecycle({"txt-highlight-end",READER_RC_HIGHLIGHT,TB,end.get(),end->want(),nullptr});
    capture_ptr start=reflow_cap(tdoc,0,first3+std::strlen("\xe8\xaf\xbb"));
    lifecycle({"txt-highlight-start",READER_RC_HIGHLIGHT,TB,start.get(),start->want(),nullptr});
    size_t amb=locate(T,"AMBIGUOUS TARGET",1);capture_ptr am=reflow_cap(tdoc,amb,amb+std::strlen("AMBIGUOUS TARGET"));
    exr_anchor_match m{};SDK(exr_anchor_resolve_ex(tdoc,&am->a,nullptr,&m,&e_));
    expect(m.state==EXR_ANCHOR_AMBIGUOUS,"ambiguous quote resolves AMBIGUOUS in the SDK before any command");
    lifecycle({"txt-highlight-ambiguous-unknown-range",READER_RC_HIGHLIGHT,TB,am.get(),am->want(),[&](const std::string &wire){
      exr_anchor_match again{};SDK(exr_anchor_resolve_ex(tdoc,&am->a,nullptr,&again,&e_));
      expect(again.state==EXR_ANCHOR_AMBIGUOUS&&decode_view(wire).start==am->a.start,"stored ambiguous selector is not relocated or rounded");}});
    capture_ptr pt=reflow_cap(tdoc,emoji,emoji);
    expect(pt->want().exact.empty()&&pt->want().start==pt->want().end,"real SDK point capture is empty exact with start==end");
    lifecycle({"txt-bookmark",READER_RC_BOOKMARK,TB,pt.get(),pt->want(),nullptr},"-");
    capture_ptr pe=reflow_cap(tdoc,T.size(),T.size()),ps=reflow_cap(tdoc,0,0);
    lifecycle({"txt-progress",READER_RC_PROGRESS,TB,pt.get(),pt->want(),nullptr});
    lifecycle({"txt-progress-end",READER_RC_PROGRESS,TB,pe.get(),pe->want(),nullptr});
    lifecycle({"txt-progress-start",READER_RC_PROGRESS,TB,ps.get(),ps->want(),nullptr});
  }
  stage("txt done");

  /* ---- EPUB in global storage: SDK chapter scope is preserved by anchor v2 ---- */
  {
    exr_document *gd=nullptr;SDK(exr_library_document(lib,ids["epubg"],&gd,&e_));size_t n=0;const char *gt=exr_document_text(gd,&n);const std::string G(gt,n);
    size_t at=locate(G,"\xe7\xac\xac\xe4\xba\x8c\xe7\xab\xa0\xe8\x8a\x82\xe7\x8b\xac\xe6\x9c\x89\xe6\x96\x87\xe5\xad\x97");
    capture_ptr c=reflow_cap(gd,at,at+std::strlen("\xe7\xac\xac\xe4\xba\x8c\xe7\xab\xa0\xe8\x8a\x82\xe7\x8b\xac\xe6\x9c\x89\xe6\x96\x87\xe5\xad\x97"));
    expect(c->a.chapter&&c->a.chapter[0],"global EPUB capture carries an SDK chapter scope");
    reader_rs_error ce{};expect(reader_rs_classify(&c->c)==READER_RS_GAP_CHAPTER_SCOPE,"anchor v1 cannot carry the chapter scope (gap)");
    lifecycle({"epub-global-chapter-scope-highlight",READER_RC_HIGHLIGHT,keys["epub"],c.get(),c->want(),[&](const std::string &wire){
      view v=decode_view(wire);expect(v.has_chapter&&v.chapter==c->a.chapter,"anchor v2 keeps the exact chapter scope",v.chapter);}});
    exr_document_free(gd);
  }
  stage("global epub done");

  /* ---- EPUB bounded chapter pager; repeated spine part ---- */
  exr_font *fnt=nullptr;SDK(exr_font_open(font.c_str(),&fnt,&e_));
  {
    exr_source src{};SDK(exr_library_source(lib,ids["epub"],&src,&e_));exr_publication *pub=nullptr;
    {exr_error pe{};if(exr_publication_open_source(&src,&pub,&pe)!=EXR_OK){src.release(src.context);fatal(std::string("publication: ")+pe.message);}}
    size_t count=0;const exr_part *parts=exr_publication_parts(pub,&count);
    exr_layout_config config=exr_layout_config_defaults();exr_chapter_options options=exr_chapter_options_defaults();
    auto pager=[&](size_t part){exr_pager *pg=nullptr;SDK(exr_publication_pager_create(pub,part,fnt,&config,&options,&pg,&e_));return pg;};
    auto chapter_text=[&](exr_pager *pg){std::string out;size_t size=exr_pager_chapter_statistics(pg).projection_bytes;
      SDK(exr_pager_read_text(pg,0,size,[](void *c,const char *t,size_t n,exr_error *){((std::string *)c)->append(t,n);return EXR_OK;},&out,nullptr,&e_));return out;};
    size_t unique=SIZE_MAX,repeated=SIZE_MAX,second=SIZE_MAX;
    for(size_t i=0;i<count;i++){size_t same=0;for(size_t j=0;j<count;j++)same+=!std::strcmp(parts[i].path,parts[j].path);
      if(same==1&&unique==SIZE_MAX)unique=i;if(same>1&&repeated==SIZE_MAX)repeated=i;else if(same>1&&!std::strcmp(parts[i].path,parts[repeated].path))second=i;}
    if(unique==SIZE_MAX||repeated==SIZE_MAX||second==SIZE_MAX)fatal("fixture spine lacks unique and repeated parts");
    expect(second!=repeated&&!std::strcmp(parts[second].path,parts[repeated].path),"fixture spine repeats one path at two parts",num(repeated)+"/"+num(second));
    exr_pager *pu=pager(unique),*pr1=pager(repeated),*pr2=pager(second);
    const std::string ut=chapter_text(pu),rt=chapter_text(pr1),rt2=chapter_text(pr2);
    size_t q=locate(ut,"\xe9\x98\x85\xe8\xaf\xbb\xe8\xbf\x9b\xe5\xba\xa6");
    capture_ptr hu=epub_cap(pu,parts[unique].path,unique,q,q+std::strlen("\xe9\x98\x85\xe8\xaf\xbb\xe8\xbf\x9b\xe5\xba\xa6"));
    lifecycle({"epub-highlight-unique-part",READER_RC_HIGHLIGHT,keys["epub"],hu.get(),hu->want(),nullptr});
    size_t rq=locate(rt,"Repeated spine chapter"),rq2=locate(rt2,"Repeated spine chapter");
    capture_ptr h1=epub_cap(pr1,parts[repeated].path,repeated,rq,rq+std::strlen("Repeated spine chapter"));
    capture_ptr h2=epub_cap(pr2,parts[second].path,second,rq2,rq2+std::strlen("Repeated spine chapter"));
    auto repeated_check=[&](size_t want_part){return std::function<void(const std::string &)>([&,want_part](const std::string &wire){
      view v=decode_view(wire);reader_rs_record r{};reader_rs_error re{};size_t part=SIZE_MAX,by_path=SIZE_MAX;
      reader_rs_decode(store,wire.data(),wire.size(),&r,&re);
      reader_rs_status rs=reader_rs_epub_record_part(pub,&r,&part,&re);reader_rs_error pe{};
      reader_rs_status ps=reader_rs_epub_part(pub,v.part_path.c_str(),&by_path,&pe);reader_rs_record_free(&r);
      expect(v.part==want_part&&rs==READER_RS_OK&&part==want_part,"anchor v2 part index routes to the exact spine part",num(v.part)+"/"+num(part));
      expect(ps==READER_RS_IDENTITY&&pe.gap==READER_RS_GAP_ROUTE,"path alone is ambiguous for the repeated spine",num((unsigned)ps)+"/"+num((unsigned)pe.gap));});};
    lifecycle({"epub-highlight-repeated-spine-first",READER_RC_HIGHLIGHT,keys["epub"],h1.get(),h1->want(),repeated_check(repeated)});
    lifecycle({"epub-highlight-repeated-spine-second",READER_RC_HIGHLIGHT,keys["epub"],h2.get(),h2->want(),repeated_check(second)});
    expect(h1->want().part_path==h2->want().part_path&&h1->want().part!=h2->want().part,"the two repeated-spine captures share a path and differ by part");
    capture_ptr bm=epub_cap(pu,parts[unique].path,unique,0,0);
    lifecycle({"epub-bookmark",READER_RC_BOOKMARK,keys["epub"],bm.get(),bm->want(),nullptr});
    capture_ptr pg0=epub_cap(pu,parts[unique].path,unique,q,q),pg2=epub_cap(pr2,parts[second].path,second,rq2,rq2);
    lifecycle({"epub-progress-unique-part",READER_RC_PROGRESS,keys["epub"],pg0.get(),pg0->want(),nullptr});
    lifecycle({"epub-progress-repeated-spine",READER_RC_PROGRESS,keys["epub"],pg2.get(),pg2->want(),nullptr});
    exr_pager_free(pu);exr_pager_free(pr1);exr_pager_free(pr2);exr_publication_free(pub);
  }
  stage("epub done");

  /* ---- fixed pages: PDF with text, textless CBZ ---- */
  auto fixed_open=[&](const char *role,exr_fixed_document **doc){exr_fixed_open_options o{};o.struct_size=sizeof(o);SDK(exr_library_fixed(lib,ids[role],&o,doc,&e_));};
  exr_fixed_document *pdf=nullptr,*cbz=nullptr;fixed_open("pdf",&pdf);fixed_open("cbz",&cbz);
  size_t pc=0,cc=0;const exr_fixed_page *pp=exr_fixed_pages(pdf,&pc),*cp=exr_fixed_pages(cbz,&cc);
  if(pc<3||cc<2)fatal("fixture page counts");
  {
    exr_fixed_text *t0=nullptr;SDK(exr_fixed_load_text(pdf,0,nullptr,&t0,&e_));size_t n0=0;const char *s0=exr_fixed_text_string(t0,&n0);std::string P0(s0?s0:"",n0);exr_fixed_text_free(t0);
    size_t at=locate(P0,"Shared quote across pages.");
    capture_ptr hl=fixed_cap(pdf,pp,0,at,at+std::strlen("Shared quote across pages."));
    lifecycle({"pdf-highlight",READER_RC_HIGHLIGHT,keys["pdf"],hl.get(),hl->want(),nullptr});
    capture_ptr bm=fixed_cap(pdf,pp,0,at,at),pr=fixed_cap(pdf,pp,1,0,0);
    lifecycle({"pdf-bookmark",READER_RC_BOOKMARK,keys["pdf"],bm.get(),bm->want(),nullptr});
    lifecycle({"pdf-progress",READER_RC_PROGRESS,keys["pdf"],pr.get(),pr->want(),nullptr});
    capture_ptr blank=fixed_cap(pdf,pp,2,0,0);
    lifecycle({"pdf-textless-page-bookmark",READER_RC_BOOKMARK,keys["pdf"],blank.get(),blank->want(),nullptr});
    capture_ptr cb=fixed_cap(cbz,cp,1,0,0);
    lifecycle({"cbz-bookmark-textless-page",READER_RC_BOOKMARK,keys["cbz"],cb.get(),cb->want(),nullptr});
    lifecycle({"cbz-progress-textless-page",READER_RC_PROGRESS,keys["cbz"],cb.get(),cb->want(),nullptr});
    entity ce=make_annotation(keys["cbz"],new_id());
    refused("cbz","highlight over a textless page",ce,READER_RC_HIGHLIGHT,READER_RC_PUT,&cb->c,0,"nothing",READER_RC_ARGUMENT);
  }
  stage("fixed done");

  /* ---- anchor v1 compatibility: existing heads keep their anchor version ---- */
  {
    size_t at=locate(T,"The repeated phrase appears here.",0);capture_ptr hl=reflow_cap(tdoc,at,at+std::strlen("The repeated phrase appears here."));
    entity e=make_annotation(TB,new_id());std::string w=raw_wire(e,new_id(),"put",&hl->c,0,"v1 original",{},true);
    std::string h1=raw_reading(w,{});expect(!h1.empty(),"anchor v1 revision commits through the unchanged module");
    e.heads={h1};view want=hl->want(1);
    expect(sel_eq(decode_view(w),want)&&decode_view(w).version==1,"v1 original reads back as anchor_version 1");
    std::string h2;view keep=want;
    if(commit("v1-compat","edit preserves the v1 selector and version",e,READER_RC_NOTE_TEXT,READER_RC_PUT,nullptr,0,"edited over v1",&keep,&h2)){
      expect(readback(h2).v.version==1,"edited revision is still anchor_version 1");
      std::string h3;reader_rs_capture dm{};dm.mode=hl->c.mode;commit("v1-compat","delete over a v1 head",e,READER_RC_HIGHLIGHT,READER_RC_DELETE,&dm,0,nullptr,nullptr,&h3);
      view v2=hl->want(2);std::string h4;
      commit("v1-compat","restore writes a v2 anchor after the tombstone",e,READER_RC_HIGHLIGHT,READER_RC_RESTORE,&hl->c,0,"restored as v2",&v2,&h4);
    }
    drain();
  }
  stage("v1 compat done");

  /* ---- every heads state ---- */
  {
    size_t at=locate(T,"Tail alpha"),len=std::strlen("Tail alpha");capture_ptr hl=reflow_cap(tdoc,at,at+len);view want=hl->want();
    entity e=make_annotation(TB,new_id());std::string h1,h2;
    {std::vector<std::string> fake{std::string(32,'a')};
     refused("heads","no history but a claimed head",e,READER_RC_HIGHLIGHT,READER_RC_PUT,&hl->c,0,"x",READER_RC_UNSAFE,&fake);}
    commit("heads","empty set creates",e,READER_RC_HIGHLIGHT,READER_RC_PUT,&hl->c,0,"base",&want,&h1);
    {std::vector<std::string> none;refused("heads","empty set over existing history",e,READER_RC_HIGHLIGHT,READER_RC_PUT,&hl->c,0,"x",READER_RC_UNSAFE,&none);}
    {std::vector<std::string> extra{h1,std::string(32,'b')};refused("heads","superset with an unknown head",e,READER_RC_HIGHLIGHT,READER_RC_PUT,&hl->c,0,"x",READER_RC_UNSAFE,&extra);}
    {std::vector<std::string> wrong{std::string(32,'c')};refused("heads","single wrong head",e,READER_RC_HIGHLIGHT,READER_RC_PUT,&hl->c,0,"x",READER_RC_UNSAFE,&wrong);}
    commit("heads","single safe head advances",e,READER_RC_HIGHLIGHT,READER_RC_PUT,&hl->c,0,"second",&want,&h2);
    {std::vector<std::string> old{h1};refused("heads","stale head after advance",e,READER_RC_HIGHLIGHT,READER_RC_PUT,&hl->c,0,"x",READER_RC_UNSAFE,&old);}
    /* concurrent heads: two local children of the same parent */
    std::string ca=new_id(),cb=new_id();
    expect(raw_local(raw_wire(e,ca,"put",&hl->c,0,"concurrent A",{h2},false))&&raw_local(raw_wire(e,cb,"put",&hl->c,0,"concurrent B",{h2},false)),"two concurrent children commit");
    reader_revision_state st{};std::vector<std::string> hs=heads_of("annotation",e.key,&st);
    expect(hs.size()==2&&!st.projection_safe,"history has two retained concurrent heads and is not safe");
    e.heads={ca};refused("heads","one of two concurrent heads",e,READER_RC_HIGHLIGHT,READER_RC_PUT,&hl->c,0,"x",READER_RC_UNSAFE);
    e.heads=hs;refused("heads","note edit needs exactly one safe head",e,READER_RC_NOTE_TEXT,READER_RC_PUT,nullptr,0,"x",READER_RC_ARGUMENT);
    std::string merged;commit("heads","complete concurrent set merges",e,READER_RC_HIGHLIGHT,READER_RC_PUT,&hl->c,0,"merged",&want,&merged);
    expect(readback(merged).parents==sorted(hs),"merge wire names both concurrent heads");
    /* pending parents: a remote revision whose parent has not arrived */
    entity pend=make_annotation(TB,new_id());std::string missing=new_id(),pid=new_id();
    std::string pw=raw_wire(pend,pid,"put",&hl->c,0,"pending",{missing},false);
    reader_revision_info vi{},ri{};reader_revision_error ve{};int created=0;
    expect(reader_revision_validate(store,pw.data(),pw.size(),nullptr,&vi,&ve)==READER_REV_OK&&reader_revision_receive(store,pw.data(),pw.size(),std::string(vi.sha256).c_str(),&ri,&created,&ve)==READER_REV_OK&&created==1,"remote revision with a missing parent is retained");
    reader_revision_state ps{};heads_of("annotation",pend.key,&ps);expect(ps.missing_parents>0&&!ps.projection_safe,"missing parent leaves the entity pending");
    pend.heads={pid};refused("heads","head with missing parents",pend,READER_RC_HIGHLIGHT,READER_RC_PUT,&hl->c,0,"x",READER_RC_UNSAFE);
    refused("heads","note edit over pending parents",pend,READER_RC_NOTE_TEXT,READER_RC_PUT,nullptr,0,"x",READER_RC_SOURCE);
    /* book with no verified history */
    entity orphan=make_annotation("txt:"+std::string(64,'0'),new_id());
    refused("heads","book without verified history",orphan,READER_RC_HIGHLIGHT,READER_RC_PUT,&hl->c,0,"x",READER_RC_REVISION,nullptr,READER_REV_NOT_FOUND);
    drain();
  }
  stage("heads done");

  /* ---- exact retry after an uncertain response, collisions, concurrent submit ---- */
  {
    size_t at=locate(T,"Tail beta"),len=std::strlen("Tail beta");capture_ptr hl=reflow_cap(tdoc,at,at+len);view want=hl->want();
    entity e=make_annotation(TB,new_id());std::string h1;
    commit("retry","create",e,READER_RC_HIGHLIGHT,READER_RC_PUT,&hl->c,0,"created",&want,&h1);
    std::vector<std::string> none;
    outcome again=run(READER_RC_HIGHLIGHT,READER_RC_PUT,e.book,e.aid,&hl->c,0,"created",h1,none);
    expect(again.st==READER_RC_OK&&again.res.created==0&&std::string(again.res.sha256)==readback(h1).info.sha256,"retry: exact repeat with the same ID is a no-op",describe(again));
    expect(outbox_count(h1)==1&&heads_of("annotation",e.key)==std::vector<std::string>{h1},"retry: no second history entry or outbox row");
    {reader_revision_error ae{};reader_revision_status as=reader_revision_ack(store,h1.c_str(),readback(h1).info.sha256,&ae);expect(as==READER_REV_OK&&!outbox_count(h1),"retry: ack removes only the outbox row");}
    again=run(READER_RC_HIGHLIGHT,READER_RC_PUT,e.book,e.aid,&hl->c,0,"created",h1,none);
    expect(again.st==READER_RC_OK&&again.res.created==0&&outbox_count(h1)==0,"retry after ack does not requeue",describe(again));
    std::string h2;commit("retry","later edit",e,READER_RC_NOTE_TEXT,READER_RC_PUT,nullptr,0,"later",&want,&h2);
    again=run(READER_RC_HIGHLIGHT,READER_RC_PUT,e.book,e.aid,&hl->c,0,"created",h1,none);
    expect(again.st==READER_RC_OK&&again.res.created==0&&heads_of("annotation",e.key)==std::vector<std::string>{h2},"retry of the old create after a later edit stays a no-op",describe(again));
    std::string s0=state_text(e);
    outcome clash=run(READER_RC_HIGHLIGHT,READER_RC_PUT,e.book,e.aid,&hl->c,0,"different text",h1,none);
    expect(clash.st==READER_RC_REVISION&&clash.err.revision.code==READER_REV_COLLISION&&clash.res.created==0&&state_text(e)==s0,"retry: same ID with different bytes is a collision and changes nothing",describe(clash));
    refused("retry","uppercase revision ID",e,READER_RC_NOTE_TEXT,READER_RC_PUT,nullptr,0,"x",READER_RC_ARGUMENT,nullptr,-1,std::string(32,'A'));
    refused("retry","short revision ID",e,READER_RC_NOTE_TEXT,READER_RC_PUT,nullptr,0,"x",READER_RC_ARGUMENT,nullptr,-1,"abc");
    /* same process, two submits from one observation: exactly one wins */
    entity race=make_annotation(TB,new_id());std::string r1;
    commit("stale-submit","create",race,READER_RC_HIGHLIGHT,READER_RC_PUT,&hl->c,0,"race",&want,&r1);
    std::vector<std::string> seen=race.heads;
    reader_rs_capture dm{};dm.mode=READER_RS_REFLOW_GLOBAL;outcome first=run(READER_RC_HIGHLIGHT,READER_RC_DELETE,race.book,race.aid,&dm,0,nullptr,new_id(),seen);
    outcome secondo=run(READER_RC_HIGHLIGHT,READER_RC_PUT,race.book,race.aid,&hl->c,0,"late",new_id(),seen);
    reader_revision_state rs{};std::vector<std::string> hs=heads_of("annotation",race.key,&rs);
    expect(first.st==READER_RC_OK&&secondo.st==READER_RC_UNSAFE&&hs.size()==1&&hs[0]==first.res.revision_id&&rs.revisions==2,"stale second submit is rejected and history does not split",describe(secondo));
    /* the owner rule: a call from another thread changes nothing */
    entity own=make_progress(TB);capture_ptr pcap=reflow_cap(tdoc,at,at);std::string s1=state_text(own);outcome from_thread{};std::string rid=new_id();
    std::thread t([&]{from_thread=run(READER_RC_PROGRESS,READER_RC_PUT,own.book,"",&pcap->c,0,nullptr,rid,own.heads);});t.join();
    expect(from_thread.st!=READER_RC_OK&&from_thread.res.created==0&&state_text(own)==s1&&!readback(rid).ok,"call from a non-owner thread is refused and writes nothing",describe(from_thread));
    drain();
  }
  stage("retry done");

  /* ---- a lost response is retried by the stable revision ID alone ---- */
  {
    size_t at=locate(T,"Tail beta"),len=std::strlen("Tail beta");capture_ptr hl=reflow_cap(tdoc,at,at+len);view want=hl->want();
    entity e;e.book=TB;e.key=e.book; /* anonymous: the caller has no identity yet */
    std::string rev=new_id();std::vector<std::string> none;
    outcome first=run(READER_RC_HIGHLIGHT,READER_RC_PUT,e.book,"",&hl->c,0,"anonymous",rev,none);
    expect(first.st==READER_RC_OK&&first.res.created==1&&rev==first.res.revision_id&&first.res.annotation_id[0],
      "anonymous create: the first commit returns its allocated annotation identity",describe(first));
    const std::string aid=first.res.annotation_id,key=first.res.entity_key;
    expect(!aid.empty()&&key==e.book+":"+aid&&outbox_count(rev)==1&&heads_of("annotation",key)==std::vector<std::string>{rev},
      "anonymous create: one head and one outbox row under the returned identity");
    back original=readback(rev);
    expect(original.ok&&original.v.has_location&&sel_eq(original.v,want),"anonymous create: selector read back equals the SDK capture");
    /* the response is lost: only the stable revision ID and the same command survive */
    outcome again=run(READER_RC_HIGHLIGHT,READER_RC_PUT,e.book,"",&hl->c,0,"anonymous",rev,none);
    expect(again.st==READER_RC_OK&&again.res.created==0&&rev==again.res.revision_id&&aid==again.res.annotation_id&&key==again.res.entity_key,
      "anonymous retry: the same ID and command re-derive the original annotation identity",describe(again));
    expect(std::string(again.res.sha256)==original.info.sha256&&heads_of("annotation",key)==std::vector<std::string>{rev}&&outbox_count(rev)==1,
      "anonymous retry: identical bytes, no second history entry or outbox row");
    {reader_revision_error ae{};reader_revision_status as=reader_revision_ack(store,rev.c_str(),original.info.sha256,&ae);
     expect(as==READER_REV_OK&&!outbox_count(rev),"anonymous retry: ack removes the outbox row");}
    again=run(READER_RC_HIGHLIGHT,READER_RC_PUT,e.book,"",&hl->c,0,"anonymous",rev,none);
    expect(again.st==READER_RC_OK&&again.res.created==0&&aid==again.res.annotation_id&&!outbox_count(rev),
      "anonymous retry after ack is a no-op and does not requeue",describe(again));
    entity own=make_annotation(TB,aid);const std::string s0=state_text(own);
    outcome clash=run(READER_RC_HIGHLIGHT,READER_RC_PUT,e.book,"",&hl->c,0,"different anonymous payload",rev,none);
    expect(clash.st==READER_RC_REVISION&&clash.err.revision.code==READER_REV_COLLISION&&clash.res.created==0&&state_text(own)==s0&&
      heads_of("annotation",key)==std::vector<std::string>{rev},
      "anonymous retry: the same ID with a different payload is a collision and changes nothing",describe(clash));
    drain();
  }

  /* ---- a failing commit leaves history and outbox together ---- */
  {
    size_t len=std::strlen("Tail gamma");
    exr_anchor probe{};exr_error pe{};if(exr_anchor_create(tdoc,0,5,&probe,&pe)==EXR_OK)exr_anchor_free(&probe);
    capture_ptr hl=reflow_cap(tdoc,locate(T,"Tail alpha"),locate(T,"Tail alpha")+len);view want=hl->want();
    entity e=make_annotation(TB,new_id());std::string h1;commit("commit-failure","create",e,READER_RC_HIGHLIGHT,READER_RC_PUT,&hl->c,0,"base",&want,&h1);
    /* The baseline is a public readback of the settled history, so it is taken
       before the second connection locks the catalog: a locked catalog cannot be
       read either, and a degraded snapshot would prove nothing about the commit. */
    const std::string s0=state_text(e);
    expect(heads_of("annotation",e.key)==std::vector<std::string>{h1}&&outbox_count(h1)==1,
      "commit-failure: the pre-lock baseline is a settled public readback of head and outbox");
    /* BEGIN IMMEDIATE takes the catalog write lock only: reads (encode, validate,
       public readback) stay possible, so the block lands on the commit itself
       rather than on the selector. */
    sqlite3 *other=nullptr;char *msg=nullptr;
    bool locked=sqlite3_open_v2(product.c_str(),&other,SQLITE_OPEN_READWRITE,nullptr)==SQLITE_OK&&sqlite3_exec(other,"BEGIN IMMEDIATE",nullptr,nullptr,&msg)==SQLITE_OK;
    sqlite3_free(msg);expect(locked,"a second connection holds the product catalog write lock");
    if(locked){
      std::string rid=new_id();
      outcome o=run(READER_RC_HIGHLIGHT,READER_RC_PUT,e.book,e.aid,&hl->c,0,"blocked put",rid,e.heads);
      sqlite3_exec(other,"ROLLBACK",nullptr,nullptr,nullptr);
      expect(o.st==READER_RC_REVISION&&o.err.revision.code==READER_REV_DATABASE&&o.res.created==0,
        "commit blocked by a database lock fails",describe(o));
      back kept=readback(rid);const std::string after=state_text(e);
      expect(after==s0&&!kept.ok,"failed commit leaves neither history nor outbox rows",
        (kept.ok?"retained bytes exist; ":"")+after+" vs "+s0);
      outcome retry=run(READER_RC_HIGHLIGHT,READER_RC_PUT,e.book,e.aid,&hl->c,0,"blocked put",rid,e.heads);
      expect(retry.st==READER_RC_OK&&retry.res.created==1&&outbox_count(rid)==1&&readback(rid).ok,"retry with the same ID after the failure commits once",describe(retry));
      e.heads={rid};
    }
    /* the same failure on the anonymous path: the caller keeps only its stable ID */
    {
      capture_ptr an=reflow_cap(tdoc,locate(T,"Tail beta"),locate(T,"Tail beta")+std::strlen("Tail beta"));
      std::string rid=new_id();sqlite3 *second=nullptr;char *m2=nullptr;
      bool again_locked=sqlite3_open_v2(product.c_str(),&second,SQLITE_OPEN_READWRITE,nullptr)==SQLITE_OK&&sqlite3_exec(second,"BEGIN IMMEDIATE",nullptr,nullptr,&m2)==SQLITE_OK;
      sqlite3_free(m2);expect(again_locked,"a second connection holds the write lock for the anonymous retry");
      if(again_locked){
        std::vector<std::string> none;
        outcome o2=run(READER_RC_HIGHLIGHT,READER_RC_PUT,e.book,"",&an->c,0,"anonymous blocked",rid,none);
        sqlite3_exec(second,"ROLLBACK",nullptr,nullptr,nullptr);
        expect(o2.st==READER_RC_REVISION&&o2.err.revision.code==READER_REV_DATABASE&&o2.res.created==0&&!readback(rid).ok,
          "an anonymous create blocked by the write lock fails and retains nothing",describe(o2));
        outcome retry2=run(READER_RC_HIGHLIGHT,READER_RC_PUT,e.book,"",&an->c,0,"anonymous blocked",rid,none);
        expect(retry2.st==READER_RC_OK&&retry2.res.created==1&&retry2.res.annotation_id[0]&&outbox_count(rid)==1&&
          heads_of("annotation",retry2.res.entity_key)==std::vector<std::string>{rid},
          "the anonymous retry after a failed commit commits exactly once",describe(retry2));
      }
      sqlite3_close(second);
    }
    sqlite3_close(other);drain();
  }
  stage("commit failure done");

  /* ---- argument bounds, strict UTF-8 and no anchor guessing ---- */
  {
    size_t at=locate(T,"Tail alpha"),len=std::strlen("Tail alpha");capture_ptr hl=reflow_cap(tdoc,at,at+len),pt=reflow_cap(tdoc,at,at);view want=hl->want();
    entity e=make_annotation(TB,new_id());std::string h;
    commit("utf8","create",e,READER_RC_HIGHLIGHT,READER_RC_PUT,&hl->c,0,"",&want,&h);
    const std::vector<std::string> good={"plain","line\nbreak\ttab \"quote\" \\ back","e\xcc\x81 \xe4\xb8\xad\xe6\x96\x87 \xf0\x9f\x99\x82\xf0\x9f\x8e\x89","\xf4\x8f\xbf\xbf","\xef\xbf\xbd",std::string(65536,'a')};
    for(size_t i=0;i<good.size();i++){std::string nh;if(!commit("utf8","valid text "+std::to_string(i),e,READER_RC_NOTE_TEXT,READER_RC_PUT,nullptr,0,good[i].c_str(),&want,&nh))break;}
    const std::vector<std::pair<std::string,std::string>> bad={{"truncated lead","\xc3"},{"overlong NUL","\xc0\x80"},{"surrogate","\xed\xa0\x80"},{"above U+10FFFF","\xf4\x90\x80\x80"},
      {"truncated three-byte","\xe2\x82"},{"stray continuation","\x80"},{"oversize",std::string(65537,'a')}};
    for(auto &b:bad)refused("utf8","invalid text: "+b.first,e,READER_RC_NOTE_TEXT,READER_RC_PUT,nullptr,0,b.second.c_str(),READER_RC_ARGUMENT);
    refused("utf8","missing text",e,READER_RC_NOTE_TEXT,READER_RC_PUT,nullptr,0,nullptr,READER_RC_ARGUMENT);
    refused("guess","bookmark from a range capture",e,READER_RC_BOOKMARK,READER_RC_PUT,&hl->c,0,"x",READER_RC_ARGUMENT);
    refused("guess","highlight from a point capture",e,READER_RC_HIGHLIGHT,READER_RC_PUT,&pt->c,0,"x",READER_RC_ARGUMENT);
    refused("guess","highlight without any capture",e,READER_RC_HIGHLIGHT,READER_RC_PUT,nullptr,0,"x",READER_RC_ARGUMENT);
    {reader_rs_capture legacy=hl->c;exr_anchor la=hl->a;la.exact=nullptr;legacy.anchor=&la;
     refused("guess","legacy offset-only selector",e,READER_RC_HIGHLIGHT,READER_RC_PUT,&legacy,0,"x",READER_RC_ARGUMENT);}
    {reader_rs_capture bent=hl->c;exr_anchor ba=hl->a;ba.end=ba.start;bent.anchor=&ba;
     refused("guess","offsets that disagree with the quote",e,READER_RC_HIGHLIGHT,READER_RC_PUT,&bent,0,"x",READER_RC_ARGUMENT);}
    refused("guess","delete with a located capture",e,READER_RC_HIGHLIGHT,READER_RC_DELETE,&hl->c,0,nullptr,READER_RC_ARGUMENT);
    {entity pe=make_progress(TB);
     refused("args","progress carrying text",pe,READER_RC_PROGRESS,READER_RC_PUT,&pt->c,0,"x",READER_RC_ARGUMENT);
     entity pa=pe;pa.aid=new_id();
     refused("args","progress carrying an annotation ID",pa,READER_RC_PROGRESS,READER_RC_PUT,&pt->c,0,nullptr,READER_RC_ARGUMENT);
     reader_rs_capture dc{};dc.mode=READER_RS_REFLOW_GLOBAL;
     entity fresh=make_annotation(TB,new_id());
     refused("args","delete without observed history",fresh,READER_RC_HIGHLIGHT,READER_RC_DELETE,&dc,0,nullptr,READER_RC_ARGUMENT);
     refused("args","note edit of an unknown annotation",fresh,READER_RC_NOTE_TEXT,READER_RC_PUT,nullptr,0,"x",READER_RC_ARGUMENT);
     std::vector<std::string> dup{h,h};refused("args","duplicate observed heads",e,READER_RC_NOTE_TEXT,READER_RC_PUT,nullptr,0,"x",READER_RC_ARGUMENT,&dup);
     std::vector<std::string> big;for(int i=0;i<33;i++)big.push_back(new_id());refused("args","more than 32 observed heads",e,READER_RC_HIGHLIGHT,READER_RC_PUT,&hl->c,0,"x",READER_RC_ARGUMENT,&big);
     std::vector<std::string> badid{"not-a-head"};refused("args","malformed observed head",e,READER_RC_HIGHLIGHT,READER_RC_PUT,&hl->c,0,"x",READER_RC_ARGUMENT,&badid);
     entity badbook=e;badbook.book="txt:zz";refused("args","malformed book key",badbook,READER_RC_HIGHLIGHT,READER_RC_PUT,&hl->c,0,"x",READER_RC_ARGUMENT);}
    {outcome o{};reader_rc_status st=reader_rc_apply(nullptr,nullptr,&o.res,&o.err);expect(st==READER_RC_ARGUMENT&&o.res.created==0&&o.err.message[0],"null arguments are an argument error",describe(o));}
    drain();
  }
  stage("arguments done");
  {
    /* EPUB capture whose route is wrong, or absent, is not guessed. */
    exr_source src{};SDK(exr_library_source(lib,ids["epub"],&src,&e_));exr_publication *pub=nullptr;
    {exr_error pe{};if(exr_publication_open_source(&src,&pub,&pe)!=EXR_OK){src.release(src.context);fatal(std::string("publication: ")+pe.message);}}
    size_t count=0;const exr_part *parts=exr_publication_parts(pub,&count);
    exr_layout_config config=exr_layout_config_defaults();exr_chapter_options options=exr_chapter_options_defaults();
    exr_pager *pg=nullptr;SDK(exr_publication_pager_create(pub,1,fnt,&config,&options,&pg,&e_));
    capture_ptr c=epub_cap(pg,parts[1].path,1,0,0);entity e=make_annotation(keys["epub"],new_id());
    {reader_rs_capture noroute=c->c;noroute.part_path=nullptr;refused("epub-route","missing part path",e,READER_RC_BOOKMARK,READER_RC_PUT,&noroute,1,"x",READER_RC_ARGUMENT);}
    exr_anchor scoped=c->a;char other[]="other.xhtml";char own[]="b.xhtml";scoped.chapter=own;
    {reader_rs_capture wrong=c->c;wrong.anchor=&scoped;wrong.part_path=other;
     outcome o=run(READER_RC_BOOKMARK,READER_RC_PUT,e.book,e.aid,&wrong,1,"x",new_id(),{});
     expect(o.st==READER_RC_ENCODE&&o.err.encode.gap==READER_RS_GAP_ROUTE&&o.res.created==0,"chapter and route disagreement is refused as ROUTE",describe(o));}
    exr_pager_free(pg);exr_publication_free(pub);
  }
  expect(sdk_snapshot()==baseline,"after every command the source books, SDK notes and current progress equal the baseline");
  {
    /* outbox only ever holds this run's local revisions, each once. */
    std::set<std::string> seen;bool dup=false;for(const row &r:outbox())dup|=!seen.insert(r.id).second;expect(!dup,"outbox rows are unique");
  }
  exr_document_free(tdoc);exr_fixed_free(pdf);exr_fixed_free(cbz);exr_font_free(fnt);
  object books;for(const char *role:{"txt","epub","pdf","cbz"})books.set(role,object().str("book_key",keys[role]).set("bytes",num(sizes[role])).dump());
  reader_revision_error cr{};reader_revisions_close(&store,&cr);exr_library_close(lib);
  object out;out.str("sdk_version",exr_version()).str("parser_version",parser).str("revisions_version",READER_REVISIONS_VERSION).str("reading_state_version",READER_READING_STATE_VERSION)
    .str("commands_version",READER_READING_COMMANDS_VERSION).str("sqlite_version",sqlite3_libversion()).str("sqlite_source_id",sqlite3_sourceid()).set("books",books.dump())
    .set("cases",array(cases)).set("checks",array(checks)).set("failures",num(failures));
  write_file(report_path,out.dump()+"\n");
  std::printf("reading-commands probe: %zu cases, %zu checks, %zu failures\n",cases.size(),checks.size(),failures);
  return failures?1:0;
}
