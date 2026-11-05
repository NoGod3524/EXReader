/* SPDX-License-Identifier: MIT */
/* Installed public-API migration consumer. Shared capture/readback helpers are
   derived from the unchanged G03 consumer. No SQL is used by this probe.
   produce exits before consume reopens the same files under an actual SDK. */
#include <reader_reading_commands.h>
#include <reader_commands.h>
#include <reader_navigation.h>
#include <exreader.h>
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
std::vector<std::string> retained;
std::string folder,fixtures,font;
std::string nz(const char *s){return s?s:"";}
void save(const std::string &label,const std::string &role,const std::string &id){
  back b=readback(id);if(!b.ok)fatal("retained readback "+label);
  write_file(folder+"/"+id+".wire",b.wire);
  retained.push_back(label+"\t"+role+"\t"+id);
}
void life(const std::string &role,const std::string &label,reader_rc_kind kind,const cap &c){
  entity en=kind==READER_RC_PROGRESS?make_progress(keys[role]):make_annotation(keys[role],new_id());
  view want=c.want();std::string id;
  auto apply=[&](const char *suffix,reader_rc_operation op,const reader_rs_capture *capture,reader_rc_kind k,const view *expected){
    if(!commit(label,suffix,en,k,op,capture,c.part,kind==READER_RC_PROGRESS?nullptr:"migration note 中文🙂",expected,&id))fatal("command "+label+suffix);
    save(label+"-"+suffix,role,id);
  };
  apply("put",READER_RC_PUT,&c.c,kind,&want);
  if(kind!=READER_RC_PROGRESS)apply("note",READER_RC_PUT,nullptr,READER_RC_NOTE_TEXT,&want);
  reader_rs_capture del{};del.mode=c.c.mode;
  // Delete's body must be absent, not the regular note text.
  if(!commit(label,"delete",en,kind,READER_RC_DELETE,&del,0,nullptr,nullptr,&id))fatal("delete "+label);
  save(label+"-delete",role,id);
  apply("restore",READER_RC_RESTORE,&c.c,kind,&want);
}
struct opened {
  exr_document *doc=nullptr;exr_fixed_document *fixed=nullptr;exr_publication *pub=nullptr;exr_pager *pager=nullptr;exr_font *fnt=nullptr;
  const exr_part *parts=nullptr;const exr_fixed_page *pages=nullptr;size_t part=1,count=0;std::string text;
  opened(const std::string &role){
    if(role=="txt"||role=="epubg"){
      SDK(exr_library_document(lib,ids[role],&doc,&e_));size_t n=0;const char *s=exr_document_text(doc,&n);text.assign(s?s:"",n);
    }else if(role=="epub"){
      exr_source src{};SDK(exr_library_source(lib,ids[role],&src,&e_));exr_error e{};
      if(exr_publication_open_source(&src,&pub,&e)!=EXR_OK){src.release(src.context);fatal(e.message);}
      parts=exr_publication_parts(pub,&count);if(count<2)fatal("spine");
      SDK(exr_font_open(font.c_str(),&fnt,&e_));exr_layout_config cfg=exr_layout_config_defaults();exr_chapter_options opts=exr_chapter_options_defaults();
      SDK(exr_publication_pager_create(pub,part,fnt,&cfg,&opts,&pager,&e_));size_t n=exr_pager_chapter_statistics(pager).projection_bytes;
      SDK(exr_pager_read_text(pager,0,n,[](void *p,const char *s,size_t n,exr_error *){((std::string *)p)->append(s,n);return EXR_OK;},&text,nullptr,&e_));
    }else{
      exr_fixed_open_options opts{};opts.struct_size=sizeof(opts);SDK(exr_library_fixed_source(lib,ids[role],&opts,&fixed,&e_));pages=exr_fixed_pages(fixed,&count);
      exr_fixed_text *t=nullptr;SDK(exr_fixed_load_text(fixed,0,nullptr,&t,&e_));size_t n=0;const char *s=exr_fixed_text_string(t,&n);text.assign(s?s:"",n);exr_fixed_text_free(t);
    }
  }
  capture_ptr capture(size_t a,size_t b){if(doc)return reflow_cap(doc,a,b);if(pub)return epub_cap(pager,parts[part].path,part,a,b);return fixed_cap(fixed,pages,0,a,b);}
  ~opened(){if(pager)exr_pager_free(pager);if(pub)exr_publication_free(pub);if(fnt)exr_font_free(fnt);if(doc)exr_document_free(doc);if(fixed)exr_fixed_free(fixed);}
};
std::string product_snapshot(){
  std::vector<std::string> rows;
  for(const char *kind:{"book","progress","annotation"}){
    reader_revision_error e{};
    reader_revision_status st=reader_revision_entities_page(store,kind,nullptr,1,100,[](void *p,const reader_revision_entity_row *r){
      ((std::vector<std::string> *)p)->push_back(nz(r->entity_key)+"|"+num(r->selection.kind)+"|"+num(r->selection.graph.revisions)+"|"+num(r->selection.graph.heads)+"|"+nz(r->wire));return 0;},&rows,&e);
    if(st!=READER_REV_OK)fatal("snapshot entities");
  }
  for(const row &r:outbox())rows.push_back(r.id+"|"+r.sha+"|"+r.key);
  std::sort(rows.begin(),rows.end());std::string s;for(auto &r:rows)s+=r+"\n";return s;
}
void produce(){
  SDK(exr_library_import(lib,EXR_TXT,originals["txt"].data(),originals["txt"].size(),"txt",&ids["txt"],&e_));
  SDK(exr_library_import_file(lib,EXR_EPUB,paths["epub"].c_str(),"epub",&ids["epub"],&e_));
  SDK(exr_library_import(lib,EXR_EPUB,originals["epub"].data(),originals["epub"].size(),"epub-global",&ids["epubg"],&e_));
  SDK(exr_library_import_file(lib,EXR_PDF,paths["pdf"].c_str(),"pdf",&ids["pdf"],&e_));
  SDK(exr_library_import_file(lib,EXR_CBZ,paths["cbz"].c_str(),"cbz",&ids["cbz"],&e_));
  for(const char *r:{"txt","epub","pdf","cbz"})add_book(r);
  keys["epubg"]=keys["epub"];
  for(const char *role:{"txt","epubg","epub","pdf","cbz"}){
    opened o(role);size_t a=0,b=0;
    if(o.doc||o.pub){std::string needle=std::string(role)=="txt"?"Unique context beta":"阅读进度";a=locate(o.text,needle);b=a+needle.size();}
    else if(std::string(role)=="pdf"){a=locate(o.text,"Shared quote");b=a+std::strlen("Shared quote");}
    auto point=o.capture(a,a);auto range=o.capture(a,b);
    life(role,std::string(role)+"-progress",READER_RC_PROGRESS,*point);
    life(role,std::string(role)+"-bookmark",READER_RC_BOOKMARK,*point);
    if(a!=b)life(role,std::string(role)+"-highlight",READER_RC_HIGHLIGHT,*range);
    if(std::string(role)=="txt"){
      SDK(exr_library_progress(lib,ids[role],&point->a,&e_));
      exr_note note{};note.book_id=ids[role];note.start=a;note.end=b;note.text=const_cast<char *>("SDK original note");int64_t note_id=0;SDK(exr_library_note(lib,&note,&note_id,&e_));
      entity en=make_annotation(keys[role],new_id());std::string id=new_id();std::string wire=raw_wire(en,id,"put",&range->c,0,"wire v1 original",{},true);
      expect(raw_local(wire),"v1-real-capture-committed");save("txt-v1",role,id);
      const size_t at=locate(o.text,"AMBIGUOUS TARGET",1);auto am=o.capture(at,at+std::strlen("AMBIGUOUS TARGET"));
      entity amb=make_annotation(keys[role],new_id());view want=am->want();
      if(!commit("ambiguous","put",amb,READER_RC_HIGHLIGHT,READER_RC_PUT,&am->c,0,"ambiguous",&want,&id))fatal("ambiguous");save("txt-ambiguous",role,id);
      entity tomb=make_annotation(keys[role],new_id());
      if(!commit("tombstone","put",tomb,READER_RC_HIGHLIGHT,READER_RC_PUT,&range->c,0,"delete me",nullptr,&id))fatal("tomb create");
      reader_rs_capture dc{};dc.mode=range->c.mode;if(!commit("tombstone","delete",tomb,READER_RC_HIGHLIGHT,READER_RC_DELETE,&dc,0,nullptr,nullptr,&id))fatal("tomb delete");save("txt-tombstone",role,id);
      entity conflict=make_annotation(keys[role],new_id());std::string root;
      if(!commit("conflict","root",conflict,READER_RC_HIGHLIGHT,READER_RC_PUT,&range->c,0,"root",nullptr,&root))fatal("conflict root");
      for(int i=0;i<2;i++){id=new_id();wire=raw_wire(conflict,id,"put",&range->c,0,i?"right":"left",{root},false);expect(raw_local(wire),"conflict-sibling-"+num(i));save("txt-conflict-"+num(i),role,id);}
    }else if(std::string(role)=="epub"){
      exr_epub_location loc{};loc.part=point->part;loc.path=const_cast<char *>(point->c.part_path);loc.selector=point->a;SDK(exr_library_epub_progress(lib,ids[role],&loc,&e_));
      exr_epub_note note{};note.book_id=ids[role];note.location.part=range->part;note.location.path=const_cast<char *>(range->c.part_path);note.location.selector=range->a;note.text=const_cast<char *>("SDK bounded note");int64_t note_id=0;SDK(exr_library_epub_note(lib,&note,&note_id,&e_));
    }else if(std::string(role)=="pdf"){
      exr_fixed_note note{};note.book_id=ids[role];note.page=0;note.start=a;note.end=b;note.text=const_cast<char *>("SDK fixed note");int64_t note_id=0;SDK(exr_library_fixed_note(lib,&note,nullptr,&note_id,&e_));
    }
  }
  std::string list;for(auto &r:retained)list+=r+"\n";write_file(folder+"/records.tsv",list);
  std::string bookids;for(auto &r:ids)bookids+=r.first+"\t"+num(r.second)+"\n";write_file(folder+"/ids.tsv",bookids);
  write_file(folder+"/producer-parser.txt",parser);
  write_file(folder+"/sdk.snapshot",sdk_snapshot());write_file(folder+"/product.snapshot",product_snapshot());
}
const char *match_name(exr_anchor_state s){return s==EXR_ANCHOR_FOUND?"FOUND":s==EXR_ANCHOR_MISSING?"MISSING":s==EXR_ANCHOR_AMBIGUOUS?"AMBIGUOUS":"LEGACY";}
std::vector<std::string> migration_rows;
void consume(){
  std::ifstream bi(folder+"/ids.tsv");std::string role;int64_t id;while(bi>>role>>id)ids[role]=id;
  keys["epubg"]=keys["epub"];
  const std::string old_parser=read_file(folder+"/producer-parser.txt");
  expect(sdk_snapshot()==read_file(folder+"/sdk.snapshot"),"reopened-sdk-notes-progress-originals-equal-producer");
  expect(product_snapshot()==read_file(folder+"/product.snapshot"),"reopened-product-history-outbox-equal-producer");
  std::ifstream manifest(folder+"/records.tsv");std::string line;
  while(std::getline(manifest,line)){
    std::stringstream in(line);std::string label,rid;std::getline(in,label,'\t');std::getline(in,role,'\t');std::getline(in,rid);
    back b=readback(rid);expect(b.ok&&b.wire==read_file(folder+"/"+rid+".wire"),label+": exact retained wire unchanged");
    reader_rs_record r{};reader_rs_error e{};auto decoded=reader_rs_decode(store,b.wire.data(),b.wire.size(),&r,&e);expect(decoded==READER_RS_OK,label+": decode");
    if(decoded!=READER_RS_OK)fatal("cannot decode retained "+label);
    reader_revision_state graph{};heads_of(b.info.entity_kind,b.info.entity_key,&graph);
    object row;row.str("label",label).str("role",role).str("wire_sha256",b.info.sha256).str("revision",rid).str("producer_parser",old_parser).str("consumer_parser",parser).str("record_parser",r.parser_version)
      .str("wire_hex",hexbytes(b.wire)).set("anchor_version",num(r.anchor_version)).set("has_location",boolean(r.has_location!=0)).set("graph_safe",boolean(graph.projection_safe!=0)).set("deleted",boolean(graph.deleted!=0));
    if(!r.has_location){row.str("admission","TOMBSTONE_REJECTED");expect(!std::strcmp(r.operation,"delete"),label+": no selector tombstone");}
    else{
      expect(old_parser==r.parser_version,label+": genuine producer parser retained");
      opened o(role);exr_anchor_match m{};size_t part=SIZE_MAX,page=SIZE_MAX;reader_rs_status resolved;
      if(o.doc)resolved=reader_rs_resolve_reflow(o.doc,&r,nullptr,&m,&e);
      else if(o.pub){resolved=reader_rs_epub_record_part(o.pub,&r,&part,&e);if(resolved==READER_RS_OK)resolved=reader_rs_resolve_epub(o.pub,o.pager,part,&r,nullptr,&m,&e);}
      else resolved=reader_rs_resolve_fixed(o.fixed,&r,nullptr,&page,&m,&e);
      bool ambiguous=label=="txt-ambiguous";expect(ambiguous?(resolved==READER_RS_UNRESOLVED&&m.state==EXR_ANCHOR_AMBIGUOUS):(resolved==READER_RS_OK&&m.state==EXR_ANCHOR_FOUND),label+": expected public resolve");
      std::string actual;if(m.state==EXR_ANCHOR_FOUND&&m.end<=o.text.size())actual=o.text.substr(m.start,m.end-m.start);
      if(m.state==EXR_ANCHOR_FOUND){
        expect(m.start==r.start&&m.end==r.end&&actual==std::string(r.exact,r.exact_size),label+": original offsets and quote stable");
        auto recaptured=o.capture(m.start,m.end);view v=recaptured->want((unsigned)r.anchor_version);view dv=decode_view(b.wire);
        row.set("v1_classification_gap",num(reader_rs_classify(&recaptured->c)));
        expect(v.start==dv.start&&v.end==dv.end&&v.exact==dv.exact&&v.prefix==dv.prefix&&v.suffix==dv.suffix&&v.chapter==dv.chapter&&v.part_path==dv.part_path&&v.page_id==dv.page_id&&v.part==dv.part&&v.page==dv.page,label+": recaptured quote context and route stable");
      }
      const char *admission=!graph.projection_safe?"CONFLICT_REJECTED":graph.deleted?"TOMBSTONE_REJECTED":old_parser!=parser?"PARSER_IDENTITY_REJECTED":m.state==EXR_ANCHOR_FOUND?"FOUND":"UNRESOLVED";
      row.str("admission",admission).set("resolve_status",num(resolved)).str("match",match_name(m.state)).set("start",num(m.start)).set("end",num(m.end)).set("part",num(part)).set("page",num(page)).str("actual_text",actual).str("exact",std::string(r.exact,r.exact_size)).str("prefix",std::string(r.prefix,r.prefix_size)).str("suffix",std::string(r.suffix,r.suffix_size)).str("chapter",nz(r.chapter)).str("part_path",nz(r.part_path)).str("page_id",nz(r.page_id));
      if(label=="txt-v1"){
        exr_anchor legacy{};legacy.start=r.start;legacy.end=r.end;exr_anchor_match lm{};SDK(exr_anchor_resolve_ex(o.doc,&legacy,nullptr,&lm,&e_));expect(lm.state==EXR_ANCHOR_LEGACY,"offset-only-legacy-not-found");
        std::string wrong=read_file(fixtures+"/spacer.txt"),edited=read_file(fixtures+"/book-edited.txt");
        for(auto pair:{std::make_pair("wrong-book",wrong),std::make_pair("changed-content",edited)}){
          exr_document *d=nullptr;SDK(exr_document_open_memory(EXR_TXT,pair.second.data(),pair.second.size(),&d,&e_));exr_anchor_match mm{};reader_rs_error ee{};auto rs=reader_rs_resolve_reflow(d,&r,nullptr,&mm,&ee);
          expect(rs==READER_RS_UNRESOLVED&&mm.state==EXR_ANCHOR_MISSING,std::string(pair.first)+"-missing-no-fallback");exr_document_free(d);
        }
        for(auto pair:{std::make_pair("bad-wire",std::string("{")),std::make_pair("bad-unicode",b.wire+std::string(1,(char)0xff))}){
          reader_rs_record bad{};reader_rs_error be{};expect(reader_rs_decode(store,pair.second.data(),pair.second.size(),&bad,&be)!=READER_RS_OK,std::string(pair.first)+"-rejected");reader_rs_record_free(&bad);
        }
        std::string unknown=b.wire;const std::string needle="\"anchor_version\":1";size_t at=unknown.find(needle);if(at==std::string::npos)fatal("v1 version field");unknown.replace(at,needle.size(),"\"anchor_version\":99");reader_rs_record bad{};reader_rs_error be{};expect(reader_rs_decode(store,unknown.data(),unknown.size(),&bad,&be)!=READER_RS_OK,"unknown-anchor-version-rejected");reader_rs_record_free(&bad);
      }
      if(label=="epub-highlight-put"){
        exr_publication *missing=nullptr;SDK(exr_publication_open((fixtures+"/missing-spine.epub").c_str(),&missing,&e_));size_t p=SIZE_MAX;reader_rs_error ee{};expect(reader_rs_epub_record_part(missing,&r,&p,&ee)==READER_RS_IDENTITY&&p==SIZE_MAX,"missing-spine-rejected-without-guess");exr_publication_free(missing);
      }
      if(label=="pdf-highlight-put"){
        std::string recorded=keys[role]+"@"+r.parser_version,live=keys[role]+"@"+parser;
        reader_navigation_options no{};no.struct_size=sizeof(no);no.source_key=recorded.c_str();reader_navigation *nav=nullptr;reader_navigation_error ne{};
        expect(reader_navigation_open_pages(o.fixed,&no,&nav,&ne)==READER_NAVIGATION_OK,"source-key-snapshot-open");
        reader_navigation_resolve_options ro{};ro.struct_size=sizeof(ro);ro.explicit_part=READER_NAVIGATION_NONE;ro.source_key=live.c_str();reader_navigation_target target{};
        auto ns=reader_navigation_resolve_page(nav,0,o.fixed,&ro,&target,&ne);
        expect(ns==(old_parser==parser?READER_NAVIGATION_OK:READER_NAVIGATION_MISMATCH),"real-navigation-parser-qualified-source-contract");
        if(old_parser!=parser)expect(!target.kind&&!target.part_id,"parser-mismatch-produces-no-navigation-target");reader_navigation_target_free(&target);
        std::string wrong="txt:"+shas["spacer"]+"@"+parser;ro.source_key=wrong.c_str();expect(reader_navigation_resolve_page(nav,0,o.fixed,&ro,&target,&ne)==READER_NAVIGATION_MISMATCH,"wrong-original-hash-rejected");reader_navigation_target_free(&target);reader_navigation_close(&nav,&ne);
        row.set("navigation_identity_status",num(ns));
      }
    }
    reader_rs_record_free(&r);migration_rows.push_back(row.dump());
  }
  expect(sdk_snapshot()==read_file(folder+"/sdk.snapshot"),"readonly-probe-sdk-notes-progress-originals-unchanged");
  expect(product_snapshot()==read_file(folder+"/product.snapshot"),"readonly-probe-product-history-outbox-unchanged");
}
}
int main(int argc,char **argv){
  if(argc<6)fatal("usage: produce|consume folder fixtures font report [role=sha]");
  std::string mode=argv[1];folder=argv[2];fixtures=argv[3];font=argv[4];
  for(int i=6;i<argc;i++){std::string p=argv[i];size_t at=p.find('=');shas[p.substr(0,at)]=p.substr(at+1);}
  for(auto pair:{std::make_pair("txt","book.txt"),std::make_pair("epub","book.epub"),std::make_pair("pdf","pages.pdf"),std::make_pair("cbz","pages.cbz")}){
    paths[pair.first]=fixtures+"/"+pair.second;formats[pair.first]=pair.first;originals[pair.first]=read_file(paths[pair.first]);sizes[pair.first]=originals[pair.first].size();keys[pair.first]=std::string(pair.first)+":"+shas[pair.first];
  }
  parser=std::string("exreader-sdk-")+exr_version();SDK(exr_library_open((folder+"/library.sqlite").c_str(),&lib,&e_));
  reader_revision_error re{};if(reader_revisions_open((folder+"/product.sqlite").c_str(),&store,&re)!=READER_REV_OK)fatal(re.message);
  if(mode=="produce")produce();else if(mode=="consume")consume();else fatal("mode");
  expect(reader_revisions_close(&store,&re)==READER_REV_OK,"all-product-handles-closed");exr_library_close(lib);lib=nullptr;
  object result;result.str("mode",mode).str("sdk_version",exr_version()).str("parser_version",parser).set("checks",array(checks)).set("failures",num(failures)).set("records",array(migration_rows)).set("produced_count",num(retained.size()));write_file(argv[5],result.dump()+"\n");
  return failures?1:0;
}
