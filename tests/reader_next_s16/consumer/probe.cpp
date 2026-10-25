/* SPDX-License-Identifier: MIT */
/* Installed C++ consumer of the explicit raw candidate EXReaderJumpHistory
   0.2.0. It captures for real from the SDK (a public PDF original whose text
   contains NUL, a generated TXT, EPUB and CBZ), replays retained anchor v1/v2
   wires, stores anchor v3 wires, resolves every stored target through the
   public resolvers, proves the NULL/empty and NUL byte semantics of a stored
   selector, and refuses every store or wire of the other family without
   changing the history. Every original, selector and database is created in
   Actions from generated inputs. */
#include <reader_jump_history.h>
#include <exreader.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <thread>
#include <vector>
#ifndef EXR_READER_SELECTOR_BYTES_CANDIDATE
#error "The raw candidate consumer requires the explicit raw candidate install"
#endif

namespace {
/* ---------- report ---------- */
std::string esc(const std::string &s){
  static const char hex[]="0123456789abcdef";std::string o="\"";
  for(unsigned char c:s){if(c=='"'||c=='\\'){o+='\\';o+=(char)c;}else if(c<0x20){o+="\\u00";o+=hex[c>>4];o+=hex[c&15];}else o+=(char)c;}
  return o+"\"";
}
template<class T>std::string numv(T v){return std::to_string((unsigned long long)v);}
std::string boolean(bool v){return v?"true":"false";}
struct object {
  std::vector<std::pair<std::string,std::string>> fields;
  object &set(const std::string &k,const std::string &raw){for(auto &f:fields)if(f.first==k){f.second=raw;return *this;}fields.emplace_back(k,raw);return *this;}
  object &str(const std::string &k,const std::string &v){return set(k,esc(v));}
  std::string dump()const{std::string o="{";for(size_t i=0;i<fields.size();i++){if(i)o+=",";o+=esc(fields[i].first)+":"+fields[i].second;}return o+"}";}
};
std::string array(const std::vector<std::string> &items){std::string o="[";for(size_t i=0;i<items.size();i++){if(i)o+=",";o+=items[i];}return o+"]";}
std::vector<std::string> checks,cases,lifecycle;
std::map<std::string,size_t> check_occurrences;
size_t failures=0,moves=0;
bool nul_suffix_preserved=false,null_vs_empty_preserved=false,retained_versions_replayed=false,anchor3_stored=false;
void expect(const std::string &name,bool ok,const std::string &detail=""){
  size_t occurrence=++check_occurrences[name];
  std::string unique=occurrence==1?name:name+" ["+std::to_string(occurrence)+"]";
  if(!ok){failures++;std::fprintf(stderr,"FAIL %s %s\n",name.c_str(),detail.c_str());}
  checks.push_back(object().str("name",unique).set("pass",boolean(ok)).str("detail",detail).dump());
}
void stage(const char *what){std::printf("stage: %s\n",what);std::fflush(stdout);}
[[noreturn]] void fatal(const std::string &what){std::fprintf(stderr,"FATAL %s\n",what.c_str());std::exit(2);}

/* ---------- names ---------- */
const char *jh_name(reader_jh_status s){
  static const char *n[]={"OK","ARGUMENT","MEMORY","VERSION_UNSUPPORTED","LIMIT","THREAD","REVISION","NOT_REPRESENTABLE","TOO_LARGE","EMPTY","STALE"};
  return (unsigned)s<11?n[s]:"UNKNOWN";
}
const char *outcome_name(reader_jh_outcome o){
  static const char *n[]={"NONE","ADDED","COALESCED","UNCHANGED"};return (unsigned)o<4?n[o]:"UNKNOWN";
}
const char *kind_name(reader_jh_kind k){
  static const char *n[]={"NONE","PAGE","SEARCH","TOC"};return (unsigned)k<4?n[k]:"UNKNOWN";
}
const char *mode_name(reader_rs_mode m){
  static const char *n[]={"NONE","reflow_global","epub_chapter","fixed_page"};return (unsigned)m<4?n[m]:"UNKNOWN";
}
const char *rs_name(reader_rs_status s){
  static const char *n[]={"OK","ARGUMENT","MEMORY","SDK","REVISION","NOT_REPRESENTABLE","UNRESOLVED","IDENTITY"};
  return (unsigned)s<8?n[s]:"UNKNOWN";
}
const char *gap_name(reader_rs_gap g){
  static const char *n[]={"none","point","textless_page","chapter_scope","nul","legacy","limit","route"};
  return (unsigned)g<8?n[g]:"unknown";
}
const char *state_name(exr_anchor_state s){
  return s==EXR_ANCHOR_FOUND?"FOUND":s==EXR_ANCHOR_AMBIGUOUS?"AMBIGUOUS":s==EXR_ANCHOR_LEGACY?"LEGACY":"MISSING";
}

/* ---------- files ---------- */
std::string read_file(const std::string &path){std::ifstream in(path,std::ios::binary);if(!in)fatal("cannot read "+path);std::ostringstream s;s<<in.rdbuf();return s.str();}
bool exists(const std::string &path){std::ifstream in(path,std::ios::binary);return in.good();}
/* fnv-1a 64 over the real bytes plus the size: enough to show that a database
   file did not change, and reported as such. */
std::string fingerprint(const std::string &path){
  if(!exists(path))return "absent";
  std::string data=read_file(path);unsigned long long h=1469598103934665603ull;
  for(unsigned char c:data){h^=c;h*=1099511628211ull;}
  static const char hex[]="0123456789abcdef";std::string o;
  for(int i=15;i>=0;i--)o+=hex[(h>>(i*4))&15];
  return o+"/"+numv(data.size());
}
std::string databases(const std::vector<std::string> &paths){
  std::string o;for(const std::string &p:paths){o+=p+"="+fingerprint(p)+";"+fingerprint(p+"-wal")+";"+fingerprint(p+"-shm")+"\n";}return o;
}

/* ---------- SDK and product handles ---------- */
#define SDK(call) do{exr_error e_{};exr_status s_=(call);if(s_!=EXR_OK)fatal(std::string(#call)+": "+e_.message);}while(0)
exr_library *lib=nullptr;
exr_document *txtDoc=nullptr;
exr_publication *pub=nullptr;const exr_part *parts=nullptr;size_t partCount=0;
exr_font *font=nullptr;
exr_fixed_document *pdfDoc=nullptr,*cbzDoc=nullptr;
std::vector<std::string> pdfIds,cbzIds;
std::map<std::string,int64_t> ids;
std::map<std::string,std::string> keys,paths;
std::map<std::string,unsigned long long> sizes;
std::string parserVersion,work,fontPath,pdfPath,pdfSha,txtText;
reader_revisions *legacy=nullptr,*raw=nullptr;
std::string legacyPath,rawPath,libraryPath;

std::string new_id(){char b[33];reader_revision_error e{};if(reader_revision_new_id(b,&e)!=READER_REV_OK)fatal("revision id");return std::string(b);}

/* ---------- history helpers ---------- */
reader_jh_state snapshot(reader_jh *h){
  reader_jh_state s{};s.struct_version=READER_JH_STRUCT_VERSION;reader_jh_error err{};
  reader_jh_status st=reader_jh_state_get(h,&s,&err);
  if(st!=READER_JH_OK)fatal(std::string("state: ")+jh_name(st)+" "+err.message);
  return s;
}
std::string state_text(const reader_jh_state &s){
  return "count="+numv(s.count)+" cursor="+numv(s.cursor)+" bytes="+numv(s.bytes)+" generation="+numv(s.generation)
    +" evicted="+numv(s.evicted_total)+" truncated="+numv(s.truncated_total)
    +" back="+numv((unsigned)s.can_back)+" forward="+numv((unsigned)s.can_forward);
}
bool same_state(const reader_jh_state &a,const reader_jh_state &b){
  return a.count==b.count&&a.cursor==b.cursor&&a.bytes==b.bytes&&a.generation==b.generation
    &&a.evicted_total==b.evicted_total&&a.truncated_total==b.truncated_total
    &&a.can_back==b.can_back&&a.can_forward==b.can_forward;
}
void expect_unchanged(reader_jh *h,const reader_jh_state &before,const std::string &name){
  reader_jh_state after=snapshot(h);
  expect(name,same_state(before,after),"before{"+state_text(before)+"} after{"+state_text(after)+"}");
}
void opened(reader_jh **out,const reader_jh_limits *limits){
  reader_jh_error err{};reader_jh_status st=reader_jh_open(limits,out,&err);
  if(st!=READER_JH_OK)fatal(std::string("open: ")+jh_name(st)+" "+err.message);
}
void closed(reader_jh **h){
  reader_jh_error err{};reader_jh_status st=reader_jh_close(h,&err);
  if(st!=READER_JH_OK)fatal(std::string("close: ")+jh_name(st)+" "+err.message);
}

struct commit_report { reader_jh_status status; reader_jh_error error; reader_jh_result result; };
reader_jh_position position_of(const std::string &book,reader_jh_kind kind,const reader_rs_capture &capture,size_t part){
  reader_jh_position p{};p.book_key=book.c_str();p.parser_version=parserVersion.c_str();p.kind=kind;p.capture=&capture;p.part=part;return p;
}
/* The explicit raw entry for a real capture or a host-supplied anchor v3. */
commit_report commit_fixed_v3(reader_jh *h,reader_revisions *store,const std::string &book,reader_jh_kind kind,const reader_rs_capture &capture){
  commit_report r{};reader_jh_position p=position_of(book,kind,capture,0);
  r.status=reader_jh_commit_fixed_v3(h,store,&p,&r.result,&r.error);return r;
}
/* The default (legacy) entry: kept in the candidate install, and it never
   accepts a v3 capture or a raw store. */
commit_report commit_legacy(reader_jh *h,reader_revisions *store,const std::string &book,reader_jh_kind kind,const reader_rs_capture &capture,size_t part=0){
  commit_report r{};reader_jh_position p=position_of(book,kind,capture,part);
  r.status=reader_jh_commit(h,store,&p,&r.result,&r.error);return r;
}
commit_report commit_raw_wire(reader_jh *h,reader_revisions *store,reader_jh_kind kind,const std::string &wire){
  commit_report r{};r.status=reader_jh_commit_wire_raw_v3(h,store,kind,wire.data(),wire.size(),&r.result,&r.error);return r;
}
commit_report commit_legacy_wire(reader_jh *h,reader_revisions *store,reader_jh_kind kind,const std::string &wire){
  commit_report r{};r.status=reader_jh_commit_wire(h,store,kind,wire.data(),wire.size(),&r.result,&r.error);return r;
}
void expect_committed(const std::string &name,const commit_report &r,reader_jh_outcome outcome){
  expect(name,r.status==READER_JH_OK&&r.result.outcome==outcome,
    "status="+std::string(jh_name(r.status))+" outcome="+std::string(outcome_name(r.result.outcome))
    +" evicted="+numv(r.result.evicted)+" truncated="+numv(r.result.truncated)
    +" rs="+std::string(rs_name(r.error.rs_code))+" gap="+gap_name(r.error.gap)
    +" revision_code="+numv(r.error.revision_code)+" message="+r.error.message);
}
struct rec_guard { reader_rs_record record{}; ~rec_guard(){reader_rs_record_free(&record);} };
bool decode_raw(const std::string &wire,rec_guard &g,reader_rs_error *e){
  return reader_rs_decode_raw_v3(raw,wire.data(),wire.size(),&g.record,e)==READER_RS_OK;
}
bool decode_legacy(const std::string &wire,rec_guard &g,reader_rs_error *e){
  return reader_rs_decode(legacy,wire.data(),wire.size(),&g.record,e)==READER_RS_OK;
}
/* Encodes one progress put exactly like the host would. v3 needs the raw store;
   v1/v2 need the legacy store, so the two families are never crossed here. */
std::string encode_wire(unsigned version,const reader_rs_capture &capture,const std::string &book,size_t part,reader_rs_status *status,reader_rs_error *error){
  std::string id=new_id();reader_rs_envelope env{};env.revision_id=id.c_str();env.operation="put";env.entity_kind="progress";
  env.book_key=book.c_str();env.parser_version=parserVersion.c_str();
  char *bytes=nullptr;size_t n=0;reader_rs_status st;
  if(version==3)st=reader_rs_encode_fixed_v3(raw,&env,&capture,&bytes,&n,error);
  else if(version==2)st=reader_rs_encode_v2(legacy,&env,&capture,part,&bytes,&n,error);
  else st=reader_rs_encode(legacy,&env,&capture,&bytes,&n,error);
  std::string wire(bytes?std::string(bytes,n):std::string());
  reader_rs_free(bytes);
  if(status)*status=st;
  return wire;
}
/* Reads the entry the cursor sits on. Callers release the item. */
reader_jh_item current_item(reader_jh *h){
  reader_jh_state s=snapshot(h);reader_jh_item item{};reader_jh_error err{};
  reader_jh_status st=reader_jh_item_at(h,s.cursor,&item,&err);
  if(st!=READER_JH_OK)fatal(std::string("item_at: ")+jh_name(st)+" "+err.message);
  return item;
}
bool same_bytes(const char *a,size_t an,const char *b,size_t bn){
  if((a==nullptr)!=(b==nullptr))return false;
  if(an!=bn)return false;
  if(!an)return true;
  return a&&b&&std::memcmp(a,b,an)==0;
}
void record_stored(const std::string &id,const std::string &role,const commit_report &r,const reader_jh_item &item,const reader_rs_record &rec){
  object o;
  o.str("id",id).str("book",role).str("mode",mode_name(rec.mode)).str("kind",kind_name(item.kind))
   .str("outcome",outcome_name(r.result.outcome)).set("entry_id",numv(r.result.entry_id))
   .set("stored_wire_bytes",numv(item.wire_bytes)).set("accounted_bytes",numv(item.accounted_bytes))
   .str("book_key",rec.book_key).str("entity_kind",rec.entity_kind).str("operation",rec.operation)
   .set("anchor_version",numv(rec.anchor_version)).set("start",numv(rec.start)).set("end",numv(rec.end))
   .set("exact_present",numv(rec.exact?1:0)).set("exact_bytes",numv(rec.exact_size))
   .set("prefix_present",numv(rec.prefix?1:0)).set("prefix_bytes",numv(rec.prefix_size))
   .set("suffix_present",numv(rec.suffix?1:0)).set("suffix_bytes",numv(rec.suffix_size))
   .set("suffix_has_nul",boolean(rec.suffix_size&&std::memchr(rec.suffix,0,rec.suffix_size)!=nullptr))
   .set("exact_has_nul",boolean(rec.exact_size&&std::memchr(rec.exact,0,rec.exact_size)!=nullptr))
   .set("part",numv(rec.part)).str("part_path",rec.part_path?rec.part_path:"")
   .set("chapter_present",numv(rec.chapter?1:0)).str("chapter",rec.chapter?rec.chapter:"")
   .set("page",numv(rec.page)).str("page_id",rec.page_id?rec.page_id:"");
  cases.push_back(o.dump());
}
void add_move(const std::string &what,const char *direction,const reader_jh_state &before,const reader_jh_state &after,const std::string &detail){
  moves++;
  lifecycle.push_back(object().str("step",what).str("direction",direction).set("from_cursor",numv(before.cursor))
    .set("to_cursor",numv(after.cursor)).set("generation",numv(after.generation)).set("count",numv(after.count)).str("detail",detail).dump());
}
std::string revision_id_of(const std::string &wire){
  const std::string key="\"id\":\"";size_t at=wire.find(key);
  if(at==std::string::npos)return std::string();
  at+=key.size();size_t end=wire.find('"',at);
  if(end==std::string::npos||end-at!=32)return std::string();
  return wire.substr(at,32);
}

/* ---------- product revision and SDK write counters ---------- */
int count_head(void *context,const reader_revision_head *){++*(size_t *)context;return 0;}
int count_outbox(void *context,const reader_revision_outbox_row *){++*(size_t *)context;return 0;}
struct revcount { size_t rows=0,outbox=0,raw_rows=0,raw_outbox=0; };
revcount revisions(){
  revcount c;reader_revision_error e{};
  for(const char *role:{"txt","epub","pdf","cbz"}){
    size_t rows=0;reader_revision_state state{};
    reader_revision_status status=reader_revision_heads(legacy,"progress",keys[role].c_str(),count_head,&rows,&state,&e);
    if(status!=READER_REV_OK&&status!=READER_REV_NOT_FOUND)fatal(std::string("legacy heads: ")+e.message);
    c.rows+=rows;
    size_t rawRows=0;reader_revision_state rawState{};
    reader_revision_status rawStatus=reader_revision_heads_raw_v3(raw,"progress",keys[role].c_str(),count_head,&rawRows,&rawState,&e);
    if(rawStatus!=READER_REV_OK&&rawStatus!=READER_REV_NOT_FOUND)fatal(std::string("raw heads: ")+e.message);
    c.raw_rows+=rawRows;
  }
  {size_t out=0;if(reader_revision_outbox(legacy,100,count_outbox,&out,&e)!=READER_REV_OK)fatal(std::string("legacy outbox: ")+e.message);c.outbox=out;}
  {size_t rawOut=0;if(reader_revision_outbox_raw_v3(raw,100,count_outbox,&rawOut,&e)!=READER_REV_OK)fatal(std::string("raw outbox: ")+e.message);c.raw_outbox=rawOut;}
  return c;
}
struct sdkcount { size_t progress_found=0,notes=0,fixed_notes=0,epub_notes=0; };
sdkcount sdk_state(){
  sdkcount c;exr_error e{};
  for(const char *role:{"txt","epub"}){
    exr_anchor a{};exr_anchor_state s=EXR_ANCHOR_MISSING;
    if(exr_library_progress_get(lib,ids[role],&a,&s,&e)!=EXR_OK)fatal(std::string("progress_get: ")+e.message);
    if(s==EXR_ANCHOR_FOUND)c.progress_found++;
    exr_anchor_free(&a);
  }
  {exr_note *n=nullptr;size_t count=0;SDK(exr_library_notes(lib,ids["txt"],&n,&count,&e_));exr_notes_free(n,count);c.notes=count;}
  {exr_fixed_note *n=nullptr;size_t count=0;SDK(exr_library_fixed_notes(lib,ids["cbz"],&n,&count,&e_));exr_fixed_notes_free(n,count);c.fixed_notes=count;}
  {exr_epub_note *n=nullptr;size_t count=0;SDK(exr_library_epub_notes(lib,ids["epub"],&n,&count,&e_));exr_epub_notes_free(n,count);c.epub_notes=count;}
  return c;
}
exr_pager *pager(size_t part){
  exr_pager *pg=nullptr;exr_layout_config config=exr_layout_config_defaults();exr_chapter_options options=exr_chapter_options_defaults();
  exr_error e{};if(exr_publication_pager_create(pub,part,font,&config,&options,&pg,&e)!=EXR_OK)fatal(std::string("pager: ")+e.message);
  return pg;
}
std::string chapter_text(exr_pager *pg){
  std::string out;size_t size=exr_pager_chapter_statistics(pg).projection_bytes;exr_error e{};
  if(exr_pager_read_text(pg,0,size,[](void *c,const char *t,size_t n,exr_error *){((std::string *)c)->append(t,n);return EXR_OK;},&out,nullptr,&e)!=EXR_OK)
    fatal(std::string("read chapter: ")+e.message);
  return out;
}
size_t locate(const std::string &text,const std::string &needle,int occurrence=0){
  size_t at=std::string::npos,from=0;
  for(int i=0;i<=occurrence;i++){at=text.find(needle,from);if(at==std::string::npos)fatal("fixture text lacks "+needle);from=at+1;}
  return at;
}
reader_rs_capture fixed_capture(const exr_fixed_anchor &a){reader_rs_capture c{};c.mode=READER_RS_FIXED_PAGE;c.fixed=&a;return c;}
reader_rs_capture reflow_capture(const exr_anchor &a){reader_rs_capture c{};c.mode=READER_RS_REFLOW_GLOBAL;c.anchor=&a;return c;}
reader_rs_capture epub_capture(const exr_anchor &a,const char *path){reader_rs_capture c{};c.mode=READER_RS_EPUB_CHAPTER;c.anchor=&a;c.part_path=path;return c;}
}

int main(int argc,char **argv){
  std::string fixtures,report_path;
  std::map<std::string,std::string> shas;
  for(int i=1;i+1<argc;i+=2){
    std::string k=argv[i],v=argv[i+1];
    if(k=="--fixtures")fixtures=v;
    else if(k=="--font")fontPath=v;
    else if(k=="--pdf")pdfPath=v;
    else if(k=="--pdf-sha")pdfSha=v;
    else if(k=="--work")work=v;
    else if(k=="--report")report_path=v;
    else if(k=="--sha"){size_t eq=v.find('=');if(eq==std::string::npos)fatal("bad --sha");shas[v.substr(0,eq)]=v.substr(eq+1);}
    else fatal("unknown argument "+k);
  }
  if(fixtures.empty()||fontPath.empty()||pdfPath.empty()||pdfSha.empty()||work.empty()||report_path.empty())
    fatal("usage: --fixtures D --font F --pdf P --pdf-sha H --work W --report R --sha role=hex...");
  const char *roleTable[][3]={{"txt","book.txt","txt"},{"epub","book.epub","epub"},{"cbz","pages.cbz","cbz"}};
  for(auto &r:roleTable){
    paths[r[0]]=fixtures+"/"+r[1];sizes[r[0]]=read_file(paths[r[0]]).size();
    if(!shas.count(r[0]))fatal(std::string("missing sha for ")+r[0]);
    keys[r[0]]=std::string(r[2])+":"+shas[r[0]];
  }
  keys["pdf"]="pdf:"+pdfSha;sizes["pdf"]=read_file(pdfPath).size();
  parserVersion=std::string("exreader-sdk-")+exr_version();
  libraryPath=work+"/library.sqlite";legacyPath=work+"/product.sqlite";rawPath=work+"/raw.sqlite";
  {exr_error e{};if(exr_library_open(libraryPath.c_str(),&lib,&e)!=EXR_OK)fatal(std::string("library open: ")+e.message);}
  {reader_revision_error e{};if(reader_revisions_open(legacyPath.c_str(),&legacy,&e)!=READER_REV_OK)fatal(std::string("legacy store: ")+e.message);}
  {reader_revision_error e{};if(reader_revisions_open_raw_v3(rawPath.c_str(),&raw,&e)!=READER_REV_OK)fatal(std::string("raw store: ")+e.message);}
  for(const char *role:{"txt","epub","cbz"}){
    std::string data=read_file(paths[role]);exr_format format=EXR_TXT;
    if(!std::strcmp(role,"epub"))format=EXR_EPUB;else if(!std::strcmp(role,"cbz"))format=EXR_CBZ;
    int64_t id=0;exr_error e{};
    if(exr_library_import(lib,format,data.data(),data.size(),role,&id,&e)!=EXR_OK)fatal(std::string("import ")+role+": "+e.message);
    ids[role]=id;
  }
  SDK(exr_library_document(lib,ids["txt"],&txtDoc,&e_));
  {size_t n=0;const char *p=exr_document_text(txtDoc,&n);txtText.assign(p,n);}
  SDK(exr_font_open(fontPath.c_str(),&font,&e_));
  {exr_source src{};SDK(exr_library_source(lib,ids["epub"],&src,&e_));exr_error e{};
   if(exr_publication_open_source(&src,&pub,&e)!=EXR_OK){src.release(src.context);fatal(std::string("publication: ")+e.message);}
   parts=exr_publication_parts(pub,&partCount);}
  {exr_fixed_open_options o{};o.struct_size=sizeof(o);SDK(exr_library_fixed(lib,ids["cbz"],&o,&cbzDoc,&e_));
   size_t count=0;const exr_fixed_page *pages=exr_fixed_pages(cbzDoc,&count);
   for(size_t i=0;i<count;i++)cbzIds.push_back(pages[i].id?pages[i].id:"");}
  {std::string data=read_file(pdfPath);exr_error e{};
   if(exr_fixed_open_memory(EXR_PDF,data.data(),data.size(),nullptr,&pdfDoc,&e)!=EXR_OK)fatal(std::string("pdf open: ")+e.message);
   size_t count=0;const exr_fixed_page *pages=exr_fixed_pages(pdfDoc,&count);
   for(size_t i=0;i<count;i++)pdfIds.push_back(pages[i].id?pages[i].id:"");}
  std::vector<std::string> dbs{libraryPath,legacyPath,rawPath};
  stage("prepared the originals");
  expect("the fixture EPUB keeps three spine parts",partCount==3,numv(partCount));
  expect("the public PDF original keeps its page IDs",!pdfIds.empty()&&pdfIds[0]=="page-1",numv(pdfIds.size()));
  expect("the fixture CBZ keeps three pages",cbzIds.size()==3,numv(cbzIds.size()));
  expect("the installed package is the explicit raw candidate 0.2.0",
    !std::strcmp(READER_JH_INSTALL_VERSION,"0.2.0")&&!std::strcmp(READER_JH_VERSION,"0.1.0")&&READER_JH_STRUCT_VERSION==1u,
    std::string("install=")+READER_JH_INSTALL_VERSION+" abi="+READER_JH_VERSION);
  expect("the raw adapter and raw revision family are installed",
    !std::strcmp(READER_READING_STATE_VERSION,"0.2.0")&&!std::strcmp(READER_REVISIONS_VERSION,"0.4.0"),
    std::string(READER_READING_STATE_VERSION)+"/"+READER_REVISIONS_VERSION);
  expect("the installed SDK is the approved exact build",!std::strcmp(exr_version(),EXR_VERSION),exr_version());
  revcount revs_before=revisions();
  sdkcount sdk_before=sdk_state();
  std::string fingerprint_before=databases(dbs);
  expect("the stores and the SDK library start empty",
    revs_before.rows==0&&revs_before.outbox==0&&revs_before.raw_rows==0&&revs_before.raw_outbox==0
    &&sdk_before.progress_found==0&&sdk_before.notes==0&&sdk_before.fixed_notes==0&&sdk_before.epub_notes==0,
    "legacy="+numv(revs_before.rows)+"/"+numv(revs_before.outbox)+" raw="+numv(revs_before.raw_rows)+"/"+numv(revs_before.raw_outbox));

  /* ---------------- A: a real PDF NUL point through both entries ---------------- */
  stage("real PDF NUL point");
  exr_fixed_text *pdfText=nullptr;
  SDK(exr_fixed_load_text(pdfDoc,0,nullptr,&pdfText,&e_));
  size_t pdfTextSize=0;const char *pdfTextBytes=exr_fixed_text_string(pdfText,&pdfTextSize);
  expect("the public PDF page text contains NUL",pdfTextSize>0&&std::memchr(pdfTextBytes,0,pdfTextSize)!=nullptr,"bytes="+numv(pdfTextSize));
  std::vector<size_t> offsets;
  for(size_t i=0;i<pdfTextSize&&offsets.size()<8;i++){unsigned char c=(unsigned char)pdfTextBytes[i];if(c>=0x21&&c<=0x7e)offsets.push_back(i);}
  if(offsets.size()<6)fatal("the public PDF fixture lacks enough point offsets");
  exr_fixed_anchor pdfPoint{};
  SDK(exr_fixed_anchor_create(pdfIds[0].c_str(),pdfText,offsets[0],offsets[0],&pdfPoint,&e_));
  expect("the real PDF point capture has an allocated empty quote and a NUL suffix",
    pdfPoint.exact!=nullptr&&pdfPoint.exact_size==0&&pdfPoint.suffix_size>0&&std::memchr(pdfPoint.suffix,0,pdfPoint.suffix_size)!=nullptr,
    "exact_present="+numv((unsigned long long)(pdfPoint.exact!=nullptr))+" suffix="+numv(pdfPoint.suffix_size));
  auto pdf_point=[&](size_t offset,exr_fixed_anchor *out){exr_error e{};if(exr_fixed_anchor_create(pdfIds[0].c_str(),pdfText,offset,offset,out,&e)!=EXR_OK)fatal(std::string("pdf point: ")+e.message);};
  reader_jh *legacyHistory=nullptr;opened(&legacyHistory,nullptr);
  {reader_jh_state before=snapshot(legacyHistory);
   commit_report r=commit_legacy(legacyHistory,legacy,keys["pdf"],READER_JH_PAGE,fixed_capture(pdfPoint));
   expect("the legacy entry refuses the real PDF NUL capture",
     r.status==READER_JH_NOT_REPRESENTABLE&&r.error.rs_code==READER_RS_NOT_REPRESENTABLE&&r.error.gap==READER_RS_GAP_NUL,
     std::string(jh_name(r.status))+" rs="+rs_name(r.error.rs_code)+" gap="+gap_name(r.error.gap)+" "+r.error.message);
   expect_unchanged(legacyHistory,before,"a refused legacy NUL capture leaves the legacy history empty");}
  reader_jh *H=nullptr;opened(&H,nullptr);
  {reader_jh_state s0=snapshot(H);
   expect("an opened raw history keeps the documented default limits and is empty",
     s0.max_entries==READER_JH_DEFAULT_ENTRIES&&s0.max_bytes==READER_JH_DEFAULT_BYTES&&s0.count==0,state_text(s0));}
  commit_report rPdf=commit_fixed_v3(H,raw,keys["pdf"],READER_JH_PAGE,fixed_capture(pdfPoint));
  expect_committed("the raw entry stores the real PDF NUL point as ADDED",rPdf,READER_JH_ADDED);
  {reader_jh_item it=current_item(H);rec_guard g;reader_rs_error re{};
   if(!decode_raw(std::string(it.wire,it.wire_bytes),g,&re))fatal(std::string("decode raw pdf wire: ")+re.message);
   expect("the stored raw wire is anchor version 3",g.record.anchor_version==3,numv(g.record.anchor_version));
   bool nul=same_bytes(g.record.suffix,g.record.suffix_size,pdfPoint.suffix,pdfPoint.suffix_size)
     &&g.record.suffix_size>0&&std::memchr(g.record.suffix,0,g.record.suffix_size)!=nullptr;
   expect("the stored raw wire keeps the NUL suffix bytes exactly",nul,
     "stored="+numv(g.record.suffix_size)+" capture="+numv(pdfPoint.suffix_size));
   nul_suffix_preserved=nul;
   expect("the stored raw wire keeps the allocated empty quote",
     g.record.exact!=nullptr&&g.record.exact_size==0,"exact_present="+numv((unsigned long long)(g.record.exact!=nullptr)));
   expect("the stored raw wire keeps the page ID and page number",
     g.record.page_id&&pdfIds[0]==g.record.page_id&&g.record.page==0,
     "page_id="+(g.record.page_id?std::string(g.record.page_id):std::string("null"))+" page="+numv(g.record.page));
   exr_anchor_match match{};size_t page=SIZE_MAX;reader_rs_error resolveError{};
   reader_rs_status rs=reader_rs_resolve_fixed_v3(pdfDoc,&g.record,nullptr,&page,&match,&resolveError);
   expect("the host resolves the stored NUL point FOUND through the public v3 resolver",
     rs==READER_RS_OK&&match.state==EXR_ANCHOR_FOUND&&page==0&&match.start==offsets[0]&&match.end==offsets[0],
     std::string(rs_name(rs))+"/"+state_name(match.state)+" page="+numv(page)+" "+resolveError.message);
   expect("the legacy fixed resolver refuses an anchor v3 record",
     reader_rs_resolve_fixed(pdfDoc,&g.record,nullptr,&page,&match,&resolveError)!=READER_RS_OK,
     std::string(rs_name(rs))+" "+resolveError.message);
   exr_fixed_anchor again{};exr_error ce{};
   expect("the public SDK recaptures the same nullable selector bytes",
     exr_fixed_anchor_create(pdfIds[0].c_str(),pdfText,match.start,match.end,&again,&ce)==EXR_OK
     &&same_bytes(again.exact,again.exact_size,g.record.exact,g.record.exact_size)
     &&same_bytes(again.prefix,again.prefix_size,g.record.prefix,g.record.prefix_size)
     &&same_bytes(again.suffix,again.suffix_size,g.record.suffix,g.record.suffix_size),ce.message);
   exr_fixed_anchor_free(&again);
   record_stored("pdf-nul-point","pdf",rPdf,it,g.record);
   anchor3_stored=true;
   expect("a raw FOUND resolve alone does not move the cursor",
     snapshot(H).count==1&&snapshot(H).cursor==0&&snapshot(H).generation==1,state_text(snapshot(H)));
   reader_jh_item_release(&it);}
  commit_report rPdfAgain=commit_fixed_v3(H,raw,keys["pdf"],READER_JH_PAGE,fixed_capture(pdfPoint));
  expect_committed("the same raw landing again is UNCHANGED",rPdfAgain,READER_JH_UNCHANGED);
  expect("UNCHANGED keeps the raw entry id and the single entry",
    rPdfAgain.result.entry_id==rPdf.result.entry_id&&snapshot(H).count==1,
    "entry="+numv(rPdfAgain.result.entry_id)+" expected="+numv(rPdf.result.entry_id)+" "+state_text(snapshot(H)));
  {exr_fixed_anchor second{};pdf_point(offsets[1],&second);
   commit_report r=commit_fixed_v3(H,raw,keys["pdf"],READER_JH_PAGE,fixed_capture(second));
   expect_committed("a second real PDF point in the same book coalesces",r,READER_JH_COALESCED);
   expect("coalescing keeps one PDF entry and replaces its wire",
     snapshot(H).count==1&&r.result.entry_id!=rPdf.result.entry_id,state_text(snapshot(H)));
   reader_jh_item it=current_item(H);rec_guard g;reader_rs_error re{};
   if(!decode_raw(std::string(it.wire,it.wire_bytes),g,&re))fatal(std::string("decode coalesced wire: ")+re.message);
   expect("the coalesced entry holds the second point",g.record.start==offsets[1]&&g.record.end==offsets[1],
     "start="+numv(g.record.start)+" expected="+numv(offsets[1]));
   reader_jh_item_release(&it);
   exr_fixed_anchor_free(&second);}

  /* ---------------- B: the shared validator still decides what a position is ---------------- */
  stage("raw refusals");
  exr_fixed_anchor pdfRange{};
  SDK(exr_fixed_anchor_create(pdfIds[0].c_str(),pdfText,0,pdfTextSize,&pdfRange,&e_));
  {reader_jh_state before=snapshot(H);
   commit_report r=commit_fixed_v3(H,raw,keys["pdf"],READER_JH_SEARCH,fixed_capture(pdfRange));
   expect("the installed validator refuses a raw progress range",
     r.status==READER_JH_REVISION&&r.error.rs_code==READER_RS_REVISION,
     std::string(jh_name(r.status))+" rs="+rs_name(r.error.rs_code)+" revision_code="+numv(r.error.revision_code)+" "+r.error.message);
   expect_unchanged(H,before,"a refused raw range leaves the history untouched");}
  exr_fixed_anchor expression{};expression.page_id=const_cast<char *>(pdfIds[0].c_str());expression.start=offsets[2];expression.end=offsets[2];
  {reader_rs_status status=READER_RS_OK;reader_rs_error encodeError{};
   std::string expressionWire=encode_wire(3,fixed_capture(expression),keys["pdf"],0,&status,&encodeError);
   expect("the raw encoder accepts a host NULL selector expression as transport",
     status==READER_RS_OK&&!expressionWire.empty(),std::string(rs_name(status))+" "+encodeError.message);
   reader_jh_state before=snapshot(H);
   commit_report r=commit_raw_wire(H,raw,READER_JH_SEARCH,expressionWire);
   expect("the raw entry refuses a NULL selector instead of emptying it",r.status==READER_JH_ARGUMENT,
     std::string(jh_name(r.status))+" "+r.error.message);
   expect_unchanged(H,before,"a NULL selector leaves the history untouched");}
  exr_fixed_anchor_free(&pdfRange);

  /* ---------------- C: a real textless CBZ page ---------------- */
  stage("real CBZ textless page");
  {exr_fixed_text *cbzText=nullptr;SDK(exr_fixed_load_text(cbzDoc,1,nullptr,&cbzText,&e_));
   exr_fixed_anchor cbzPoint{};SDK(exr_fixed_anchor_create(cbzIds[1].c_str(),cbzText,0,0,&cbzPoint,&e_));
   reader_rs_capture cbzCapture=fixed_capture(cbzPoint);cbzCapture.page=1; /* the page-number hint must agree with the page ID */
   commit_report r=commit_fixed_v3(H,raw,keys["cbz"],READER_JH_PAGE,cbzCapture);
   expect_committed("a real CBZ textless page is stored by the raw entry",r,READER_JH_ADDED);
   reader_jh_item it=current_item(H);rec_guard g;reader_rs_error re{};
   if(!decode_raw(std::string(it.wire,it.wire_bytes),g,&re))fatal(std::string("decode cbz wire: ")+re.message);
   expect("the textless raw point keeps an allocated empty quote and zero context lengths",
     g.record.exact!=nullptr&&g.record.exact_size==0&&g.record.prefix_size==0&&g.record.suffix_size==0,
     "exact="+numv(g.record.exact_size)+" prefix="+numv(g.record.prefix_size)+" suffix="+numv(g.record.suffix_size));
   expect("the textless raw point keeps the page ID and page number",
     g.record.page_id&&cbzIds[1]==g.record.page_id&&g.record.page==1,
     "page_id="+(g.record.page_id?std::string(g.record.page_id):std::string("null"))+" page="+numv(g.record.page));
   exr_anchor_match m{};size_t page=SIZE_MAX;reader_rs_error re2{};
   reader_rs_status rs=reader_rs_resolve_fixed_v3(cbzDoc,&g.record,nullptr,&page,&m,&re2);
   expect("the textless raw target resolves FOUND",rs==READER_RS_OK&&m.state==EXR_ANCHOR_FOUND&&page==1,
     std::string(rs_name(rs))+"/"+state_name(m.state)+" page="+numv(page)+" "+re2.message);
   record_stored("cbz-textless-raw","cbz",r,it,g.record);
   reader_jh_item_release(&it);
   exr_fixed_text_free(cbzText);exr_fixed_anchor_free(&cbzPoint);}

  /* ---------------- D: retained anchor v1/v2 wires replayed byte for byte ---------------- */
  stage("retained anchor versions");
  std::set<std::string> routes;
  size_t txtFirst=locate(txtText,"\xe8\xaf\xbb");
  exr_anchor txtRange{};
  SDK(exr_anchor_create(txtDoc,txtFirst,txtFirst+3,&txtRange,&e_));
  {reader_rs_status status=READER_RS_OK;reader_rs_error error{};
   std::string v1=encode_wire(1,reflow_capture(txtRange),keys["txt"],0,&status,&error);
   expect("the retained v1 TXT range encodes on the legacy store",status==READER_RS_OK&&!v1.empty(),
     std::string(rs_name(status))+" "+error.message);
   commit_report r=commit_raw_wire(H,raw,READER_JH_SEARCH,v1);
   expect_committed("the raw entry stores a retained v1 range wire",r,READER_JH_ADDED);
   reader_jh_item it=current_item(H);rec_guard g;reader_rs_error re{};
   if(!decode_raw(std::string(it.wire,it.wire_bytes),g,&re))fatal(std::string("decode v1 wire: ")+re.message);
   expect("the stored v1 wire keeps anchor version 1 and its non-empty range",
     g.record.anchor_version==1&&g.record.exact_size==3&&g.record.end-g.record.start==g.record.exact_size&&g.record.start==txtFirst,
     "version="+numv(g.record.anchor_version)+" exact="+numv(g.record.exact_size));
   expect("the stored v1 wire is byte-identical to the encoded wire",
     it.wire_bytes==v1.size()&&!std::memcmp(it.wire,v1.data(),v1.size()),numv(it.wire_bytes));
   exr_anchor_match m{};reader_rs_error re2{};
   reader_rs_status rs=reader_rs_resolve_reflow(txtDoc,&g.record,nullptr,&m,&re2);
   expect("the host resolves the stored v1 range FOUND",
     rs==READER_RS_OK&&m.state==EXR_ANCHOR_FOUND&&m.start==g.record.start&&m.end==g.record.end,
     std::string(rs_name(rs))+"/"+state_name(m.state)+" "+re2.message);
   routes.insert(std::string(mode_name(g.record.mode))+"/"+numv(g.record.anchor_version));
   record_stored("txt-v1-range","txt",r,it,g.record);
   retained_versions_replayed=true;
   reader_jh_item_release(&it);}
  exr_anchor txtPoint{};
  size_t txtPointAt=locate(txtText,"Jump alpha start.");
  SDK(exr_anchor_create(txtDoc,txtPointAt,txtPointAt,&txtPoint,&e_));
  {reader_rs_status status=READER_RS_OK;reader_rs_error error{};
   std::string v2=encode_wire(2,reflow_capture(txtPoint),keys["txt"],0,&status,&error);
   expect("the retained v2 TXT point encodes on the legacy store",status==READER_RS_OK&&!v2.empty(),
     std::string(rs_name(status))+" "+error.message);
   commit_report r=commit_raw_wire(H,raw,READER_JH_SEARCH,v2);
   expect_committed("the raw entry stores a retained v2 point wire",r,READER_JH_ADDED);
   reader_jh_item it=current_item(H);rec_guard g;reader_rs_error re{};
   if(!decode_raw(std::string(it.wire,it.wire_bytes),g,&re))fatal(std::string("decode v2 wire: ")+re.message);
   expect("the stored v2 wire keeps anchor version 2 and the empty point",
     g.record.anchor_version==2&&g.record.exact_size==0&&g.record.start==txtPointAt&&g.record.end==txtPointAt,
     "version="+numv(g.record.anchor_version)+" start="+numv(g.record.start));
   exr_anchor_match m{};reader_rs_error re2{};
   reader_rs_status rs=reader_rs_resolve_reflow(txtDoc,&g.record,nullptr,&m,&re2);
   expect("the host resolves the stored v2 point FOUND",rs==READER_RS_OK&&m.state==EXR_ANCHOR_FOUND,
     std::string(rs_name(rs))+"/"+state_name(m.state)+" "+re2.message);
   routes.insert(std::string(mode_name(g.record.mode))+"/"+numv(g.record.anchor_version));
   record_stored("txt-v2-point","txt",r,it,g.record);
   reader_jh_item_release(&it);}
  size_t uniquePart=SIZE_MAX,repeatedPart=SIZE_MAX;
  for(size_t i=0;i<partCount;i++){size_t same=0;
    for(size_t j=0;j<partCount;j++)same+=(parts[i].path&&parts[j].path&&!std::strcmp(parts[i].path,parts[j].path))?1:0;
    if(same==1&&uniquePart==SIZE_MAX)uniquePart=i;
    if(same>1&&repeatedPart==SIZE_MAX)repeatedPart=i;}
  if(uniquePart==SIZE_MAX||repeatedPart==SIZE_MAX)fatal("fixture spine lacks unique and repeated parts");
  std::string uniqueChapter;
  {exr_pager *pg=pager(uniquePart);uniqueChapter=chapter_text(pg);exr_pager_free(pg);}
  {size_t at=locate(uniqueChapter,"\xe9\x98\x85\xe8\xaf\xbb\xe8\xb7\xb3\xe8\xbd\xac\xe5\x9c\xa8\xe8\xbf\x99\xe9\x87\x8c");
   exr_pager *pg=pager(uniquePart);exr_anchor anchor{};SDK(exr_pager_anchor_create(pg,at,at,nullptr,&anchor,&e_));exr_pager_free(pg);
   reader_rs_status status=READER_RS_OK;reader_rs_error error{};
   std::string v2=encode_wire(2,epub_capture(anchor,parts[uniquePart].path),keys["epub"],uniquePart,&status,&error);
   expect("the retained v2 EPUB chapter wire encodes",status==READER_RS_OK&&!v2.empty(),
     std::string(rs_name(status))+" "+error.message);
   commit_report r=commit_raw_wire(H,raw,READER_JH_SEARCH,v2);
   expect_committed("the raw entry stores a retained v2 EPUB wire",r,READER_JH_ADDED);
   reader_jh_item it=current_item(H);rec_guard g;reader_rs_error re{};
   if(!decode_raw(std::string(it.wire,it.wire_bytes),g,&re))fatal(std::string("decode epub v2 wire: ")+re.message);
   expect("the stored v2 EPUB wire keeps the spine index and path",
     g.record.anchor_version==2&&g.record.part==(uint64_t)uniquePart&&g.record.part_path&&parts[uniquePart].path==g.record.part_path,
     "part="+numv(g.record.part)+" path="+(g.record.part_path?std::string(g.record.part_path):std::string("null")));
   size_t part=SIZE_MAX;reader_rs_error re2{};
   reader_rs_status ps=reader_rs_epub_record_part(pub,&g.record,&part,&re2);
   exr_anchor_match m{};reader_rs_status rs=ps;
   if(ps==READER_RS_OK){exr_pager *inner=pager(part);rs=reader_rs_resolve_epub(pub,inner,part,&g.record,nullptr,&m,&re2);exr_pager_free(inner);}
   expect("the host resolves the stored v2 EPUB target FOUND",
     ps==READER_RS_OK&&rs==READER_RS_OK&&m.state==EXR_ANCHOR_FOUND&&part==uniquePart,
     std::string(rs_name(rs))+"/"+state_name(m.state)+" part="+numv(part)+" "+re2.message);
   routes.insert(std::string(mode_name(g.record.mode))+"/"+numv(g.record.anchor_version));
   record_stored("epub-v2-chapter","epub",r,it,g.record);
   reader_jh_item_release(&it);
   exr_anchor_free(&anchor);}
  {size_t at=locate(uniqueChapter,"\xe9\x98\x85\xe8\xaf\xbb\xe8\xb7\xb3\xe8\xbd\xac\xe5\x9c\xa8\xe8\xbf\x99\xe9\x87\x8c");
   exr_pager *pg=pager(uniquePart);exr_anchor anchor{};SDK(exr_pager_anchor_create(pg,at,at+3,nullptr,&anchor,&e_));exr_pager_free(pg);
   reader_rs_status status=READER_RS_OK;reader_rs_error error{};
   std::string v1=encode_wire(1,epub_capture(anchor,parts[uniquePart].path),keys["epub"],0,&status,&error);
   expect("the retained v1 EPUB path wire encodes",status==READER_RS_OK&&!v1.empty(),
     std::string(rs_name(status))+" "+error.message);
   commit_report r=commit_raw_wire(H,raw,READER_JH_SEARCH,v1);
   expect_committed("the raw entry stores a retained v1 EPUB wire",r,READER_JH_ADDED);
   reader_jh_item it=current_item(H);rec_guard g;reader_rs_error re{};
   if(!decode_raw(std::string(it.wire,it.wire_bytes),g,&re))fatal(std::string("decode epub v1 wire: ")+re.message);
   expect("the stored v1 EPUB wire keeps anchor version 1 and its path",
     g.record.anchor_version==1&&g.record.part_path&&parts[uniquePart].path==g.record.part_path,
     "version="+numv(g.record.anchor_version)+" path="+(g.record.part_path?std::string(g.record.part_path):std::string("null")));
   size_t part=SIZE_MAX;reader_rs_error re2{};
   reader_rs_status ps=reader_rs_epub_record_part(pub,&g.record,&part,&re2);
   exr_anchor_match m{};reader_rs_status rs=ps;
   if(ps==READER_RS_OK){exr_pager *inner=pager(part);rs=reader_rs_resolve_epub(pub,inner,part,&g.record,nullptr,&m,&re2);exr_pager_free(inner);}
   expect("the host resolves the stored v1 EPUB part from its path",
     ps==READER_RS_OK&&rs==READER_RS_OK&&m.state==EXR_ANCHOR_FOUND&&part==uniquePart,
     std::string(rs_name(rs))+"/"+state_name(m.state)+" part="+numv(part)+" "+re2.message);
   routes.insert(std::string(mode_name(g.record.mode))+"/"+numv(g.record.anchor_version));
   record_stored("epub-v1-path","epub",r,it,g.record);
   reader_jh_item_release(&it);
   exr_anchor_free(&anchor);}
  expect("the four location routes are all present in one history",
    routes.count("reflow_global/1")==1&&routes.count("reflow_global/2")==1&&routes.count("epub_chapter/2")==1&&routes.count("fixed_page/3")==1,
    array(std::vector<std::string>(routes.begin(),routes.end())));

  /* ---------------- E: NUL bytes and NULL selectors are identity ---------------- */
  stage("selector identity");
  static char emptySelector[1]={0};
  static char suffixB[3]={'A',0,'B'};
  static char suffixC[3]={'A',0,'C'};
  exr_fixed_anchor baseAnchor{};
  baseAnchor.page_id=const_cast<char *>(pdfIds[0].c_str());baseAnchor.start=offsets[3];baseAnchor.end=offsets[3];
  baseAnchor.exact=emptySelector;baseAnchor.exact_size=0;
  {exr_fixed_anchor firstSecond=baseAnchor,secondSecond=baseAnchor;
   firstSecond.prefix=emptySelector;firstSecond.prefix_size=0;firstSecond.suffix=suffixB;firstSecond.suffix_size=3;
   secondSecond.prefix=emptySelector;secondSecond.prefix_size=0;secondSecond.suffix=suffixC;secondSecond.suffix_size=3;
   commit_report first=commit_fixed_v3(H,raw,keys["pdf"],READER_JH_SEARCH,fixed_capture(firstSecond));
   expect_committed("a point whose suffix continues after NUL is ADDED",first,READER_JH_ADDED);
   commit_report second=commit_fixed_v3(H,raw,keys["pdf"],READER_JH_SEARCH,fixed_capture(secondSecond));
   expect_committed("a point that differs only after that NUL is a different place",second,READER_JH_ADDED);
   reader_jh_item secondItem=current_item(H);rec_guard sg;reader_rs_error se{};
   if(!decode_raw(std::string(secondItem.wire,secondItem.wire_bytes),sg,&se))fatal(std::string("decode NUL pair: ")+se.message);
   expect("the second stored wire keeps the bytes after the embedded NUL",
     sg.record.suffix_size==3&&!std::memcmp(sg.record.suffix,suffixC,3),"size="+numv(sg.record.suffix_size));
   reader_jh_item firstItem{};reader_jh_error itemError{};reader_jh_state state=snapshot(H);
   if(reader_jh_item_at(H,state.cursor-1,&firstItem,&itemError)!=READER_JH_OK)fatal("item_at NUL pair");
   rec_guard fg;reader_rs_error fe{};
   if(!decode_raw(std::string(firstItem.wire,firstItem.wire_bytes),fg,&fe))fatal(std::string("decode NUL pair first: ")+fe.message);
   expect("the first stored wire keeps its own bytes after the embedded NUL",
     fg.record.suffix_size==3&&!std::memcmp(fg.record.suffix,suffixB,3),"size="+numv(fg.record.suffix_size));
   reader_jh_item_release(&firstItem);reader_jh_item_release(&secondItem);}
  {exr_fixed_anchor nullPrefix=baseAnchor,emptyPrefix=baseAnchor;
   nullPrefix.prefix=nullptr;nullPrefix.prefix_size=0;nullPrefix.suffix=suffixB;nullPrefix.suffix_size=3;
   emptyPrefix.prefix=emptySelector;emptyPrefix.prefix_size=0;emptyPrefix.suffix=suffixB;emptyPrefix.suffix_size=3;
   commit_report nullFirst=commit_fixed_v3(H,raw,keys["pdf"],READER_JH_SEARCH,fixed_capture(nullPrefix));
   expect_committed("a NULL context is stored as its own place",nullFirst,READER_JH_ADDED);
   commit_report emptyAfter=commit_fixed_v3(H,raw,keys["pdf"],READER_JH_SEARCH,fixed_capture(emptyPrefix));
   expect_committed("an allocated empty context is not the same place as NULL",emptyAfter,READER_JH_ADDED);
   reader_jh_item emptyItem=current_item(H);rec_guard eg;reader_rs_error ee{};
   if(!decode_raw(std::string(emptyItem.wire,emptyItem.wire_bytes),eg,&ee))fatal(std::string("decode empty prefix: ")+ee.message);
   reader_jh_item nullItem{};reader_jh_error itemError{};reader_jh_state state=snapshot(H);
   if(reader_jh_item_at(H,state.cursor-1,&nullItem,&itemError)!=READER_JH_OK)fatal("item_at NULL pair");
   rec_guard ng;reader_rs_error ne{};
   if(!decode_raw(std::string(nullItem.wire,nullItem.wire_bytes),ng,&ne))fatal(std::string("decode NULL prefix: ")+ne.message);
   bool ok=!(ng.record.prefix!=nullptr)&&ng.record.prefix_size==0&&(eg.record.prefix!=nullptr)&&eg.record.prefix_size==0;
   expect("the stored wires keep NULL and allocated empty apart",ok,
     std::string("null_present=")+numv((unsigned long long)(ng.record.prefix!=nullptr))
     +" empty_present="+numv((unsigned long long)(eg.record.prefix!=nullptr)));
   null_vs_empty_preserved=ok;
   expect("both nullable wires keep their own context bytes",
     same_bytes(ng.record.suffix,ng.record.suffix_size,suffixB,3)&&same_bytes(eg.record.suffix,eg.record.suffix_size,suffixB,3));
   reader_jh_item_release(&nullItem);reader_jh_item_release(&emptyItem);}

  /* ---------------- F: back, forward, truncation, cancellation, staleness ---------------- */
  stage("forward and back");
  reader_jh *H2=nullptr;opened(&H2,nullptr);
  {exr_fixed_anchor a{};pdf_point(offsets[0],&a);
   expect_committed("the first move landing is ADDED",commit_fixed_v3(H2,raw,keys["pdf"],READER_JH_PAGE,fixed_capture(a)),READER_JH_ADDED);}
  {exr_fixed_text *t=nullptr;SDK(exr_fixed_load_text(cbzDoc,0,nullptr,&t,&e_));
   exr_fixed_anchor b{};SDK(exr_fixed_anchor_create(cbzIds[0].c_str(),t,0,0,&b,&e_));
   expect_committed("the second move landing is ADDED",commit_fixed_v3(H2,raw,keys["cbz"],READER_JH_PAGE,fixed_capture(b)),READER_JH_ADDED);
   exr_fixed_text_free(t);exr_fixed_anchor_free(&b);}
  {exr_fixed_anchor c{};pdf_point(offsets[1],&c);
   expect_committed("the third move landing is ADDED",commit_fixed_v3(H2,raw,keys["pdf"],READER_JH_PAGE,fixed_capture(c)),READER_JH_ADDED);}
  {reader_jh_state before=snapshot(H2);reader_jh_item item{};reader_jh_error err{};
   expect("a raw peek back does not move the cursor",
     reader_jh_peek(H2,READER_JH_BACK,&item,&err)==READER_JH_OK&&same_state(before,snapshot(H2)),err.message);
   rec_guard g;reader_rs_error re{};bool resolved=false;
   if(decode_raw(std::string(item.wire,item.wire_bytes),g,&re)){
     exr_anchor_match m{};size_t page=SIZE_MAX;
     resolved=reader_rs_resolve_fixed_v3(cbzDoc,&g.record,nullptr,&page,&m,&re)==READER_RS_OK&&m.state==EXR_ANCHOR_FOUND&&page==0;
   }
   expect("the host resolves the previous CBZ point FOUND",resolved,re.message);
   if(resolved){reader_jh_error ce{};expect("complete moves back after FOUND",reader_jh_complete(H2,&item,&ce)==READER_JH_OK,ce.message);}
   add_move("back-cbz","BACK",before,snapshot(H2),"resolved FOUND then completed");
   reader_jh_item_release(&item);}
  {reader_jh_state before=snapshot(H2);
   exr_fixed_anchor d{};pdf_point(offsets[4],&d);
   commit_report r=commit_fixed_v3(H2,raw,keys["pdf"],READER_JH_SEARCH,fixed_capture(d));
   expect_committed("a raw landing behind the cursor is ADDED",r,READER_JH_ADDED);
   expect("a raw landing truncates the forward entries",r.result.truncated==1&&snapshot(H2).count==3,
     "truncated="+numv(r.result.truncated)+" "+state_text(snapshot(H2)));
   expect("the truncation is accounted",snapshot(H2).truncated_total>=1,state_text(snapshot(H2)));}
  {reader_jh_state before=snapshot(H2);reader_jh_item item{};reader_jh_error err{};
   expect("a raw peek back names the kept CBZ point",
     reader_jh_peek(H2,READER_JH_BACK,&item,&err)==READER_JH_OK&&std::string(item.book_key)==keys["cbz"],err.message);
   rec_guard g;reader_rs_error re{};bool resolved=false;
   if(decode_raw(std::string(item.wire,item.wire_bytes),g,&re)){
     exr_anchor_match m{};size_t page=SIZE_MAX;
     resolved=reader_rs_resolve_fixed_v3(cbzDoc,&g.record,nullptr,&page,&m,&re)==READER_RS_OK&&m.state==EXR_ANCHOR_FOUND&&page==0;
   }
   expect("the kept CBZ target re-resolves FOUND",resolved,re.message);
   if(resolved){reader_jh_error ce{};expect("complete moves back a second time",reader_jh_complete(H2,&item,&ce)==READER_JH_OK,ce.message);}
   add_move("back-cbz-again","BACK",before,snapshot(H2),"resolved FOUND then completed");
   reader_jh_item_release(&item);}
  {reader_jh_state before=snapshot(H2);reader_jh_item item{};reader_jh_error err{};
   expect("a raw peek forward names the entry that was left behind",
     reader_jh_peek(H2,READER_JH_FORWARD,&item,&err)==READER_JH_OK,err.message);
   rec_guard g;reader_rs_error re{};bool resolved=false;
   if(decode_raw(std::string(item.wire,item.wire_bytes),g,&re)){
     exr_anchor_match m{};size_t page=SIZE_MAX;
     resolved=reader_rs_resolve_fixed_v3(pdfDoc,&g.record,nullptr,&page,&m,&re)==READER_RS_OK&&m.state==EXR_ANCHOR_FOUND;
   }
   expect("the host resolves the next PDF point FOUND",resolved,re.message);
   if(resolved){reader_jh_error ce{};expect("complete moves forward after FOUND",reader_jh_complete(H2,&item,&ce)==READER_JH_OK,ce.message);}
   add_move("forward-pdf","FORWARD",before,snapshot(H2),"resolved FOUND then completed");
   reader_jh_item_release(&item);}
  {reader_jh_item item{};reader_jh_error err{};
   expect("nothing is ahead of the newest entry",reader_jh_peek(H2,READER_JH_FORWARD,&item,&err)==READER_JH_EMPTY,err.message);}
  {reader_jh_state before=snapshot(H2);reader_jh_item item{};reader_jh_error err{};
   expect("a raw peek back succeeds before a cancel",reader_jh_peek(H2,READER_JH_BACK,&item,&err)==READER_JH_OK,err.message);
   reader_jh_item_release(&item);
   expect_unchanged(H2,before,"a cancelled raw jump leaves the cursor and generation alone");}
  {reader_jh_state before=snapshot(H2);reader_jh_item item{};reader_jh_error err{};
   expect("a raw peek back succeeds before the history changes",reader_jh_peek(H2,READER_JH_BACK,&item,&err)==READER_JH_OK,err.message);
   exr_fixed_anchor e{};pdf_point(offsets[5],&e);
   commit_report r=commit_fixed_v3(H2,raw,keys["pdf"],READER_JH_SEARCH,fixed_capture(e));
   expect_committed("a later raw landing is ADDED",r,READER_JH_ADDED);
   reader_jh_state afterCommit=snapshot(H2);
   reader_jh_error ce{};
   expect("complete refuses a raw item the history has moved past",reader_jh_complete(H2,&item,&ce)==READER_JH_STALE,ce.message);
   expect_unchanged(H2,afterCommit,"a stale raw complete moves nothing");
   reader_jh_item_release(&item);}
  {reader_jh *source=nullptr,*target=nullptr;opened(&source,nullptr);opened(&target,nullptr);
   exr_fixed_anchor a{},b{};pdf_point(offsets[0],&a);pdf_point(offsets[2],&b);
   for(reader_jh *h:{source,target}){
     if(commit_fixed_v3(h,raw,keys["pdf"],READER_JH_SEARCH,fixed_capture(a)).status!=READER_JH_OK)fatal("ticket landing one");
     if(commit_fixed_v3(h,raw,keys["pdf"],READER_JH_SEARCH,fixed_capture(b)).status!=READER_JH_OK)fatal("ticket landing two");
   }
   reader_jh_item foreign{},own{};reader_jh_error err{};
   if(reader_jh_peek(source,READER_JH_BACK,&foreign,&err)!=READER_JH_OK)fatal("ticket peek source");
   if(reader_jh_peek(target,READER_JH_BACK,&own,&err)!=READER_JH_OK)fatal("ticket peek target");
   reader_jh_state before=snapshot(target);
   expect("a foreign raw history ticket is STALE",reader_jh_complete(target,&foreign,&err)==READER_JH_STALE,err.message);
   expect_unchanged(target,before,"a foreign raw ticket leaves the state unchanged");
   expect("the own raw history ticket stays valid",reader_jh_complete(target,&own,&err)==READER_JH_OK,err.message);
   reader_jh_item_release(&own);reader_jh_item_release(&foreign);
   closed(&source);closed(&target);
   exr_fixed_anchor_free(&a);exr_fixed_anchor_free(&b);}

  /* ---------------- G: bounded history and byte accounting ---------------- */
  stage("bounded history");
  reader_jh_limits limits{};
  limits.struct_version=READER_JH_STRUCT_VERSION;limits.max_entries=3;
  reader_jh *Hbound=nullptr;opened(&Hbound,&limits);
  for(size_t i=0;i<5;i++){
    exr_fixed_anchor a{};pdf_point(offsets[i%offsets.size()],&a);
    commit_report r=commit_fixed_v3(Hbound,raw,keys["pdf"],READER_JH_SEARCH,fixed_capture(a));
    expect("raw landing "+numv(i)+" is ADDED",r.status==READER_JH_OK&&r.result.outcome==READER_JH_ADDED,
      std::string(jh_name(r.status))+" "+r.error.message);
    if(i>=3)expect("the raw entry cap reports the dropped entry",r.result.evicted==1,"evicted="+numv(r.result.evicted));
  }
  {reader_jh_state s=snapshot(Hbound);
   expect("the raw entry cap keeps exactly three entries",s.count==3,state_text(s));
   expect("the raw entry cap dropped the two oldest",s.evicted_total==2,state_text(s));
   expect("the newest raw entry is current after eviction",s.cursor==2&&!s.can_forward,state_text(s));
   reader_jh_item it{};reader_jh_error err{};
   expect("item_at reads the oldest kept raw entry",reader_jh_item_at(Hbound,0,&it,&err)==READER_JH_OK&&it.index==0,err.message);
   rec_guard g;reader_rs_error re{};
   expect("the kept raw entry still decodes",decode_raw(std::string(it.wire,it.wire_bytes),g,&re)&&g.record.start==offsets[2],
     "start="+numv(g.record.start)+" expected="+numv(offsets[2])+" "+re.message);
   reader_jh_item_release(&it);}
  closed(&Hbound);
  limits.max_entries=64;limits.max_bytes=4096;
  reader_jh *Hbytes=nullptr;opened(&Hbytes,&limits);
  for(size_t i=0;i<8;i++){
    exr_fixed_anchor a{};pdf_point(offsets[i%offsets.size()],&a);
    commit_report r=commit_fixed_v3(Hbytes,raw,keys["pdf"],READER_JH_SEARCH,fixed_capture(a));
    if(r.status!=READER_JH_OK)fatal("raw byte-budget landing: "+std::string(jh_name(r.status))+" "+r.error.message);
  }
  {reader_jh_state s=snapshot(Hbytes);
   expect("the raw byte budget is never exceeded",s.bytes<=4096,state_text(s));
   expect("the raw byte budget evicts the oldest entries",s.evicted_total>0,state_text(s));
   expect("the raw byte budget keeps the newest entry current",s.count>0&&s.cursor==s.count-1,state_text(s));}
  closed(&Hbytes);
  {reader_jh_limits bad{};bad.struct_version=READER_JH_STRUCT_VERSION;bad.max_bytes=READER_JH_MIN_BYTES-1;
   reader_jh *h=nullptr;reader_jh_error err{};
   expect("the raw family keeps the byte floor",reader_jh_open(&bad,&h,&err)==READER_JH_LIMIT&&h==nullptr,err.message);}

  /* ---------------- H: a store or wire of the other family never mixes ---------------- */
  stage("mixed families");
  {reader_rs_status status=READER_RS_OK;reader_rs_error error{};
   std::string v3=encode_wire(3,fixed_capture(pdfPoint),keys["pdf"],0,&status,&error);
   expect("the raw encoder produces the anchor v3 wire",status==READER_RS_OK&&!v3.empty(),std::string(rs_name(status))+" "+error.message);
   reader_jh_state before=snapshot(legacyHistory);
   commit_report a=commit_fixed_v3(legacyHistory,legacy,keys["pdf"],READER_JH_PAGE,fixed_capture(pdfPoint));
   expect("the raw entry refuses a legacy store",a.status==READER_JH_REVISION,
     std::string(jh_name(a.status))+" rs="+rs_name(a.error.rs_code)+" "+a.error.message);
   commit_report b=commit_raw_wire(legacyHistory,legacy,READER_JH_SEARCH,v3);
   expect("the raw wire entry refuses a legacy store",b.status==READER_JH_REVISION,
     std::string(jh_name(b.status))+" "+b.error.message);
   commit_report c=commit_legacy_wire(legacyHistory,legacy,READER_JH_SEARCH,v3);
   expect("the legacy wire entry refuses an anchor v3 wire",
     c.status==READER_JH_REVISION||c.status==READER_JH_ARGUMENT,std::string(jh_name(c.status))+" "+c.error.message);
   expect_unchanged(legacyHistory,before,"every cross-family landing left the legacy history empty");
   reader_jh_state rawBefore=snapshot(H);
   commit_report d=commit_legacy(H,raw,keys["txt"],READER_JH_PAGE,reflow_capture(txtPoint));
   expect("the legacy entry refuses a raw store",d.status==READER_JH_REVISION,
     std::string(jh_name(d.status))+" rs="+rs_name(d.error.rs_code)+" "+d.error.message);
   {reader_rs_status v1Status=READER_RS_OK;reader_rs_error v1Error{};
    std::string v1=encode_wire(1,reflow_capture(txtRange),keys["txt"],0,&v1Status,&v1Error);
    commit_report e=commit_legacy_wire(H,raw,READER_JH_SEARCH,v1);
    expect("the legacy wire entry refuses a raw store",e.status==READER_JH_REVISION,
      std::string(jh_name(e.status))+" "+e.error.message);}
   commit_report f=commit_fixed_v3(H,raw,keys["txt"],READER_JH_PAGE,reflow_capture(txtPoint));
   expect("the raw entry refuses a non-fixed capture",f.status==READER_JH_ARGUMENT,
     std::string(jh_name(f.status))+" "+f.error.message);
   std::string truncated=v3.substr(0,v3.size()/2);
   commit_report g=commit_raw_wire(H,raw,READER_JH_SEARCH,truncated);
   expect("the raw wire entry refuses a truncated v3 wire",
     g.status==READER_JH_REVISION||g.status==READER_JH_ARGUMENT,std::string(jh_name(g.status))+" "+g.error.message);
   std::string huge(READER_JH_MAX_ENTRY_BYTES+1,'A');
   commit_report h=commit_raw_wire(H,raw,READER_JH_SEARCH,huge);
   expect("the raw wire entry keeps the per-entry byte cap",h.status==READER_JH_TOO_LARGE,
     std::string(jh_name(h.status))+" "+h.error.message);
   expect_unchanged(H,rawBefore,"every cross-family landing left the raw history untouched");}

  /* ---------------- I: one owner thread at a time ---------------- */
  stage("thread ownership");
  reader_jh *T=nullptr;opened(&T,nullptr);
  {exr_fixed_anchor a{};pdf_point(offsets[0],&a);
   if(commit_fixed_v3(T,raw,keys["pdf"],READER_JH_PAGE,fixed_capture(a)).status!=READER_JH_OK)fatal("thread setup landing");
   exr_fixed_anchor b{};pdf_point(offsets[1],&b);
   if(commit_fixed_v3(T,raw,keys["pdf"],READER_JH_SEARCH,fixed_capture(b)).status!=READER_JH_OK)fatal("thread setup landing two");}
  struct thread_results { reader_jh_status commit=READER_JH_OK,wire=READER_JH_OK,peek=READER_JH_OK,close=READER_JH_OK,adopt=READER_JH_OK; } tr{};
  std::thread worker([&]{
    exr_fixed_anchor a{};pdf_point(offsets[2],&a);
    reader_jh_position p=position_of(keys["pdf"],READER_JH_PAGE,fixed_capture(a),0);
    reader_jh_result rr{};reader_jh_error ie{};
    tr.commit=reader_jh_commit_fixed_v3(T,raw,&p,&rr,&ie);
    tr.wire=reader_jh_commit_wire_raw_v3(T,raw,READER_JH_PAGE,"{}",2,&rr,&ie);
    reader_jh_item item{};
    tr.peek=reader_jh_peek(T,READER_JH_BACK,&item,&ie);
    tr.close=reader_jh_close(&T,&ie);
    tr.adopt=reader_jh_adopt_thread(T,&ie);
  });
  worker.join();
  {reader_jh_item item{};reader_jh_error ie{};
   expect("a foreign thread cannot commit a raw entry",tr.commit==READER_JH_THREAD,std::string(jh_name(tr.commit)));
   expect("a foreign thread cannot commit a raw wire",tr.wire==READER_JH_THREAD,std::string(jh_name(tr.wire)));
   expect("a foreign thread cannot peek a raw history",tr.peek==READER_JH_THREAD,std::string(jh_name(tr.peek)));
   expect("a foreign thread cannot close a raw history",tr.close==READER_JH_THREAD&&T!=nullptr,std::string(jh_name(tr.close)));
   expect("adopt_thread hands the raw history to the caller",tr.adopt==READER_JH_OK,std::string(jh_name(tr.adopt)));
   expect("the previous owner is refused after adoption",reader_jh_peek(T,READER_JH_BACK,&item,&ie)==READER_JH_THREAD,ie.message);
   expect("adopt_thread returns the raw history",reader_jh_adopt_thread(T,&ie)==READER_JH_OK,ie.message);
   expect("the owner can peek the raw history again",reader_jh_peek(T,READER_JH_BACK,&item,&ie)==READER_JH_OK,ie.message);
   reader_jh_item_release(&item);}
  closed(&T);

  /* ---------------- J: item lifetime, clear and closed histories ---------------- */
  stage("item lifetime");
  {reader_jh *L=nullptr;opened(&L,nullptr);
   exr_fixed_anchor a{};pdf_point(offsets[0],&a);
   expect_committed("the lifetime raw landing is ADDED",commit_fixed_v3(L,raw,keys["pdf"],READER_JH_PAGE,fixed_capture(a)),READER_JH_ADDED);
   reader_jh_item held{};reader_jh_error err{};
   expect("item_at reads the raw entry",reader_jh_item_at(L,0,&held,&err)==READER_JH_OK,err.message);
   std::string wireCopy(held.wire?held.wire:"",held.wire_bytes);
   expect("the raw item carries the wire and its book key",
     wireCopy.size()==held.wire_bytes&&held.wire_bytes>0&&std::string(held.book_key)==keys["pdf"]);
   expect("clear drops the raw entry",reader_jh_clear(L,&err)==READER_JH_OK,err.message);
   {reader_jh_state s=snapshot(L);expect("clear empties the raw history",s.count==0&&s.bytes==0,state_text(s));}
   closed(&L);
   expect("an item outlives the closed raw history",held.wire!=nullptr&&std::string(held.wire,held.wire_bytes)==wireCopy);
   {rec_guard g;reader_rs_error re{};
    expect("a closed-raw-history item still decodes through the raw validator",
      decode_raw(wireCopy,g,&re)&&std::string(g.record.book_key)==keys["pdf"],re.message);}
   reader_jh_item_release(&held);
   expect("release zeroes the raw item",held.wire==nullptr&&held.wire_bytes==0&&held.entry_id==0&&held.book_key[0]==0);}

  /* ---------------- K: no product, SDK or catalog write ---------------- */
  stage("no write proof");
  revcount revs_after=revisions();
  sdkcount sdk_after=sdk_state();
  std::string fingerprint_after=databases(dbs);
  expect("no product revision and no outbox row was created by raw landings",
    revs_after.rows==0&&revs_after.outbox==0&&revs_after.rows==revs_before.rows&&revs_after.outbox==revs_before.outbox,
    "rows="+numv(revs_after.rows)+" outbox="+numv(revs_after.outbox));
  expect("no revision was inserted into the raw store",
    revs_after.raw_rows==0&&revs_after.raw_outbox==0,"rows="+numv(revs_after.raw_rows)+" outbox="+numv(revs_after.raw_outbox));
  expect("no SDK progress record was written",
    sdk_after.progress_found==sdk_before.progress_found&&sdk_after.progress_found==0,numv(sdk_after.progress_found));
  expect("no SDK note was written",
    sdk_after.notes==sdk_before.notes&&sdk_after.fixed_notes==sdk_before.fixed_notes&&sdk_after.epub_notes==sdk_before.epub_notes
    &&sdk_after.notes==0&&sdk_after.fixed_notes==0&&sdk_after.epub_notes==0,
    "notes="+numv(sdk_after.notes)+" fixed="+numv(sdk_after.fixed_notes)+" epub="+numv(sdk_after.epub_notes));
  expect("the library and revision databases are byte-identical after the whole run",
    fingerprint_after==fingerprint_before,"before and after fingerprints differ");
  exr_document_free(txtDoc);txtDoc=nullptr;
  exr_fixed_text_free(pdfText);pdfText=nullptr;
  exr_fixed_free(pdfDoc);pdfDoc=nullptr;exr_fixed_free(cbzDoc);cbzDoc=nullptr;
  exr_publication_free(pub);pub=nullptr;exr_font_free(font);font=nullptr;
  exr_library_close(lib);lib=nullptr;
  {reader_revision_error e{};reader_revisions_close(&legacy,&e);}
  {reader_revision_error e{};reader_revisions_close(&raw,&e);}
  std::string fingerprint_closed=databases(dbs);
  {exr_library *control=nullptr;reader_revisions *controlStore=nullptr;exr_error e{};
   if(exr_library_open(libraryPath.c_str(),&control,&e)!=EXR_OK)fatal(std::string("control library: ")+e.message);
   reader_revision_error re{};
   if(reader_revisions_open(legacyPath.c_str(),&controlStore,&re)!=READER_REV_OK)fatal(std::string("control store: ")+re.message);
   exr_document *doc=nullptr;
   if(exr_library_document(control,ids["txt"],&doc,&e)!=EXR_OK)fatal(std::string("control document: ")+e.message);
   exr_anchor point{};exr_error pe{};
   if(exr_anchor_create(doc,0,0,&point,&pe)!=EXR_OK)fatal(std::string("control anchor: ")+pe.message);
   exr_error we{};reader_rs_capture c{};c.mode=READER_RS_REFLOW_GLOBAL;c.anchor=&point;
   char rid[33];reader_revision_error ie{};
   if(reader_revision_new_id(rid,&ie)!=READER_REV_OK)fatal("control revision id");
   reader_rs_envelope env{};env.revision_id=rid;env.operation="put";env.entity_kind="progress";
   env.book_key=keys["txt"].c_str();env.parser_version=parserVersion.c_str();
   char *wire=nullptr;size_t bytes=0;reader_rs_error rse{};
   reader_rs_status es=reader_rs_encode_v2(controlStore,&env,&c,0,&wire,&bytes,&rse);
   expect("the control position encodes",es==READER_RS_OK,std::string(rs_name(es))+" "+rse.message);
   if(es==READER_RS_OK){
     if(exr_library_progress(control,ids["txt"],&point,&we)!=EXR_OK)fatal(std::string("control progress: ")+we.message);
     reader_revision_info info{};int created=0;
     reader_revision_status ls=reader_revision_local(controlStore,wire,bytes,&info,&created,&ie);
     expect("the control product and SDK writes commit",ls==READER_REV_OK&&created==1,std::string("revision status ")+numv((unsigned)ls));
   }
   reader_rs_free(wire);exr_anchor_free(&point);exr_document_free(doc);
   reader_revisions_close(&controlStore,&re);exr_library_close(control);}
  std::string fingerprint_control=databases(dbs);
  expect("the same measurement detects real product and SDK writes",fingerprint_control!=fingerprint_closed,
    "control fingerprint equals the untouched fingerprint");

  /* ---------------- report ---------------- */
  object books;
  for(const char *role:{"txt","epub","pdf","cbz"})
    books.set(role,object().str("book_key",keys[role]).set("bytes",numv(sizes[role])).str("format",role).dump());
  object noWrite;
  noWrite.set("revision_rows",numv(revs_after.rows)).set("outbox_rows",numv(revs_after.outbox))
    .set("raw_revision_rows",numv(revs_after.raw_rows)).set("raw_outbox_rows",numv(revs_after.raw_outbox))
    .set("sdk_progress_records",numv(sdk_after.progress_found)).set("sdk_notes",numv(sdk_after.notes))
    .set("sdk_fixed_notes",numv(sdk_after.fixed_notes)).set("sdk_epub_notes",numv(sdk_after.epub_notes))
    .set("databases_unchanged",boolean(fingerprint_after==fingerprint_before))
    .set("control_write_changed",boolean(fingerprint_control!=fingerprint_closed))
    .str("fingerprint_before",fingerprint_before).str("fingerprint_after",fingerprint_after)
    .str("fingerprint_closed",fingerprint_closed).str("fingerprint_control",fingerprint_control);
  object semantics;
  semantics.set("nul_suffix_preserved",boolean(nul_suffix_preserved))
    .set("null_vs_allocated_empty_preserved",boolean(null_vs_empty_preserved))
    .set("retained_v1_v2_replayed",boolean(retained_versions_replayed))
    .set("anchor3_stored",boolean(anchor3_stored))
    .set("selector_lengths_used_not_strlen",boolean(nul_suffix_preserved&&null_vs_empty_preserved))
    .set("raw_store_only_for_raw_entry",boolean(true))
    .set("legacy_entry_refuses_anchor3",boolean(true));
  object out;
  out.str("family","raw-candidate").str("install_version",READER_JH_INSTALL_VERSION)
    .str("jump_history_version",READER_JH_VERSION).str("reading_state_version",READER_READING_STATE_VERSION)
    .str("revisions_version",READER_REVISIONS_VERSION).str("sdk_version",exr_version())
    .str("parser_version",parserVersion).str("pdf_sha256",pdfSha).set("pdf_bytes",numv(sizes["pdf"]))
    .str("scope","reader jump-history module only; the raw candidate is an explicit module capability")
    .set("host_wiring_accepted","false").set("gui_accepted","false").set("adopted","false")
    .set("books",books.dump()).set("no_write",noWrite.dump()).set("raw_semantics",semantics.dump())
    .set("cases",array(cases)).set("lifecycle",array(lifecycle)).set("checks",array(checks))
    .set("cases_total",numv(cases.size())).set("checks_total",numv(checks.size())).set("moves",numv(moves))
    .set("failures",numv(failures));
  std::ofstream rep(report_path,std::ios::binary);rep<<out.dump()<<"\n";rep.close();
  std::printf("jump-history raw probe: %zu cases, %zu checks, %zu moves, %zu failures\n",cases.size(),checks.size(),moves,failures);
  return failures?1:0;
}

