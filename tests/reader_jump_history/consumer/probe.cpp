/* SPDX-License-Identifier: MIT */
/* Installed C++ consumer of EXReaderJumpHistory: real frozen-SDK captures for
   TXT, EPUB, PDF and CBZ, a real product revision store, back/forward moves with
   a public re-resolve before every move, cancellation, coalescing, eviction,
   unknown versions, item lifetime and proof that no product or SDK write occurs.
   Every original, selector and database is created in Actions from generated
   inputs. */
#include <reader_jump_history.h>
#include <exreader.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <map>
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
size_t failures=0,moves=0;
void expect(const std::string &name,bool ok,const std::string &detail=""){
  if(!ok){failures++;std::fprintf(stderr,"FAIL %s %s\n",name.c_str(),detail.c_str());}
  checks.push_back(object().str("name",name).set("pass",boolean(ok)).str("detail",detail).dump());
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
struct side { const char *name; exr_library *lib=nullptr; reader_revisions *store=nullptr;
  std::string lib_path,product_path; std::map<std::string,int64_t> ids; };
side S{"owner"};
std::map<std::string,std::string> keys,paths,formats;
std::map<std::string,unsigned long long> sizes;
std::string parser_version,work,font_path;
void open_side(){
  exr_error e{};if(exr_library_open(S.lib_path.c_str(),&S.lib,&e)!=EXR_OK)fatal(std::string("library open: ")+e.message);
  reader_revision_error r{};if(reader_revisions_open(S.product_path.c_str(),&S.store,&r)!=READER_REV_OK)fatal(std::string("revisions open: ")+r.message);
}
void close_side(){
  if(S.lib){exr_library_close(S.lib);S.lib=nullptr;}
  if(S.store){reader_revision_error r{};reader_revisions_close(&S.store,&r);}
}

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
/* The documented atomicity guarantee: an error return leaves the history alone. */
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
commit_report commit_capture(reader_jh *h,const std::string &role,reader_jh_kind kind,const reader_rs_capture &capture,size_t part){
  commit_report r{};reader_jh_position p{keys[role].c_str(),parser_version.c_str(),kind,&capture,part};
  r.status=reader_jh_commit(h,S.store,&p,&r.result,&r.error);return r;
}
commit_report commit_wire(reader_jh *h,reader_jh_kind kind,const std::string &wire){
  commit_report r{};r.status=reader_jh_commit_wire(h,S.store,kind,wire.data(),wire.size(),&r.result,&r.error);return r;
}
void expect_committed(const std::string &name,const commit_report &r,reader_jh_outcome outcome){
  expect(name,r.status==READER_JH_OK&&r.result.outcome==outcome,
    "status="+std::string(jh_name(r.status))+" outcome="+std::string(outcome_name(r.result.outcome))
    +" evicted="+numv(r.result.evicted)+" truncated="+numv(r.result.truncated)
    +" rs="+std::string(rs_name(r.error.rs_code))+" gap="+gap_name(r.error.gap)
    +" revision_code="+numv(r.error.revision_code)+" message="+r.error.message);
}
bool decode_item(const reader_jh_item &item,reader_rs_record *rec,reader_rs_error *err){
  return reader_rs_decode(S.store,item.wire,item.wire_bytes,rec,err)==READER_RS_OK;
}
/* Reads the entry the cursor sits on. Callers release the item. */
reader_jh_item current_item(reader_jh *h){
  reader_jh_state s=snapshot(h);reader_jh_item item{};reader_jh_error err{};
  reader_jh_status st=reader_jh_item_at(h,s.cursor,&item,&err);
  if(st!=READER_JH_OK)fatal(std::string("item_at: ")+jh_name(st)+" "+err.message);
  return item;
}
void record_stored(const std::string &id,const std::string &role,const commit_report &r,const reader_jh_item &item,const reader_rs_record &rec){
  object o;
  o.str("id",id).str("book",role).str("mode",mode_name(rec.mode)).str("kind",kind_name(item.kind))
   .str("outcome",outcome_name(r.result.outcome)).set("entry_id",numv(r.result.entry_id))
   .set("stored_wire_bytes",numv(item.wire_bytes)).set("accounted_bytes",numv(item.accounted_bytes))
   .str("book_key",rec.book_key).str("entity_kind",rec.entity_kind).str("operation",rec.operation)
   .set("anchor_version",numv(rec.anchor_version)).set("start",numv(rec.start)).set("end",numv(rec.end))
   .set("exact_bytes",numv(rec.exact_size)).set("prefix_bytes",numv(rec.prefix_size)).set("suffix_bytes",numv(rec.suffix_size))
   .set("part",numv(rec.part)).str("part_path",rec.part_path?rec.part_path:"")
   .set("page",numv(rec.page)).str("page_id",rec.page_id?rec.page_id:"");
  cases.push_back(o.dump());
}
void add_move(const std::string &what,const char *direction,const reader_jh_state &before,const reader_jh_state &after,const std::string &detail){
  moves++;
  lifecycle.push_back(object().str("step",what).str("direction",direction).set("from_cursor",numv(before.cursor))
    .set("to_cursor",numv(after.cursor)).set("generation",numv(after.generation)).set("count",numv(after.count)).str("detail",detail).dump());
}
/* The wire the history stores carries a transient revision ID that was never
   inserted; read it back out of the JSON so the run can prove it is not a row. */
std::string revision_id_of(const std::string &wire){
  const std::string key="\"id\":\"";size_t at=wire.find(key);
  if(at==std::string::npos)return std::string();
  at+=key.size();size_t end=wire.find('"',at);
  if(end==std::string::npos||end-at!=32)return std::string();
  return wire.substr(at,32);
}
size_t locate(const std::string &text,const std::string &needle,int occurrence=0){
  size_t at=std::string::npos,from=0;
  for(int i=0;i<=occurrence;i++){at=text.find(needle,from);if(at==std::string::npos)fatal("fixture text lacks "+needle);from=at+1;}
  return at;
}

/* ---------- SDK objects ---------- */
exr_document *docTxt=nullptr;
std::string textTxt;
exr_publication *pub=nullptr;
const exr_part *parts=nullptr;size_t partCount=0;
exr_font *font=nullptr;
struct fixeddoc { const char *role; exr_fixed_document *doc; std::vector<std::string> ids; };
fixeddoc pdf{"pdf",nullptr,{}},cbz{"cbz",nullptr,{}};
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

/* ---------- product revision and SDK write counters ---------- */
int count_head(void *context,const reader_revision_head *){++*(size_t *)context;return 0;}
int count_outbox(void *context,const reader_revision_outbox_row *){++*(size_t *)context;return 0;}
struct revcount { size_t rows=0,outbox=0; };
revcount revisions(){
  revcount c;reader_revision_error e{};
  for(const char *role:{"txt","epub","pdf","cbz"}){
    size_t rows=0;reader_revision_state state{};
    reader_revision_status status=reader_revision_heads(S.store,"progress",keys[role].c_str(),count_head,&rows,&state,&e);
    if(status!=READER_REV_OK&&status!=READER_REV_NOT_FOUND)fatal(std::string("heads: ")+e.message);
    c.rows+=rows;
  }
  size_t out=0;if(reader_revision_outbox(S.store,100,count_outbox,&out,&e)!=READER_REV_OK)fatal(std::string("outbox: ")+e.message);
  c.outbox=out;return c;
}
struct sdkcount { size_t progress_found=0,notes=0,fixed_notes=0,epub_notes=0; };
sdkcount sdk_state(){
  sdkcount c;exr_error e{};
  /* Fixed-page books store page positions instead of a reflow selector, so the
     reflow progress getter is asked only about the reflow and EPUB books. */
  for(const char *role:{"txt","epub"}){
    exr_anchor a{};exr_anchor_state s=EXR_ANCHOR_MISSING;
    if(exr_library_progress_get(S.lib,S.ids[role],&a,&s,&e)!=EXR_OK)fatal(std::string("progress_get: ")+e.message);
    if(s==EXR_ANCHOR_FOUND)c.progress_found++;
    exr_anchor_free(&a);
  }
  {exr_note *n=nullptr;size_t count=0;SDK(exr_library_notes(S.lib,S.ids["txt"],&n,&count,&e_));exr_notes_free(n,count);c.notes=count;}
  {exr_fixed_note *n=nullptr;size_t count=0;SDK(exr_library_fixed_notes(S.lib,S.ids["pdf"],&n,&count,&e_));exr_fixed_notes_free(n,count);c.fixed_notes=count;}
  {exr_epub_note *n=nullptr;size_t count=0;SDK(exr_library_epub_notes(S.lib,S.ids["epub"],&n,&count,&e_));exr_epub_notes_free(n,count);c.epub_notes=count;}
  return c;
}
std::string fixed_text(exr_fixed_document *d,size_t page){
  exr_fixed_text *t=nullptr;exr_error e{};
  if(exr_fixed_load_text(d,page,nullptr,&t,&e)!=EXR_OK)fatal(std::string("load text: ")+e.message);
  size_t n=0;const char *s=exr_fixed_text_string(t,&n);std::string out(s?s:"",n);exr_fixed_text_free(t);return out;
}
}

int main(int argc,char **argv){
  std::string fixtures,report_path;
  std::map<std::string,std::string> shas;
  for(int i=1;i+1<argc;i+=2){
    std::string k=argv[i],v=argv[i+1];
    if(k=="--fixtures")fixtures=v;else if(k=="--font")font_path=v;else if(k=="--work")work=v;else if(k=="--report")report_path=v;
    else if(k=="--sha"){size_t eq=v.find('=');if(eq==std::string::npos)fatal("bad --sha");shas[v.substr(0,eq)]=v.substr(eq+1);}
    else fatal("unknown argument "+k);
  }
  if(fixtures.empty()||font_path.empty()||work.empty()||report_path.empty())fatal("usage: --fixtures D --font F --work W --report R --sha role=hex...");
  const char *roleTable[][3]={{"txt","book.txt","txt"},{"epub","book.epub","epub"},{"pdf","pages.pdf","pdf"},{"cbz","pages.cbz","cbz"}};
  for(auto &r:roleTable){
    paths[r[0]]=fixtures+"/"+r[1];formats[r[0]]=r[2];sizes[r[0]]=read_file(paths[r[0]]).size();
    if(!shas.count(r[0]))fatal(std::string("missing sha for ")+r[0]);
    keys[r[0]]=std::string(r[2])+":"+shas[r[0]];
  }
  parser_version=std::string("exreader-sdk-")+exr_version();
  S.lib_path=work+"/library.sqlite";S.product_path=work+"/product.sqlite";
  open_side();
  for(const char *role:{"txt","epub","pdf","cbz"}){
    std::string data=read_file(paths[role]);exr_format format=EXR_TXT;
    if(!std::strcmp(role,"epub"))format=EXR_EPUB;else if(!std::strcmp(role,"pdf"))format=EXR_PDF;else if(!std::strcmp(role,"cbz"))format=EXR_CBZ;
    int64_t id=0;exr_error e{};
    if(exr_library_import(S.lib,format,data.data(),data.size(),role,&id,&e)!=EXR_OK)fatal(std::string("import ")+role+": "+e.message);
    S.ids[role]=id;
  }
  stage("imported four originals");
  SDK(exr_library_document(S.lib,S.ids["txt"],&docTxt,&e_));
  {size_t n=0;const char *p=exr_document_text(docTxt,&n);textTxt.assign(p,n);}
  SDK(exr_font_open(font_path.c_str(),&font,&e_));
  {exr_source src{};SDK(exr_library_source(S.lib,S.ids["epub"],&src,&e_));
   exr_error e{};if(exr_publication_open_source(&src,&pub,&e)!=EXR_OK){src.release(src.context);fatal(std::string("publication: ")+e.message);}
   parts=exr_publication_parts(pub,&partCount);}
  {exr_fixed_open_options o{};o.struct_size=sizeof(o);SDK(exr_library_fixed(S.lib,S.ids["pdf"],&o,&pdf.doc,&e_));SDK(exr_library_fixed(S.lib,S.ids["cbz"],&o,&cbz.doc,&e_));
   for(fixeddoc *d:{&pdf,&cbz}){size_t count=0;const exr_fixed_page *pages=exr_fixed_pages(d->doc,&count);
     for(size_t i=0;i<count;i++)d->ids.push_back(pages[i].id?pages[i].id:"");}}
  expect("the fixture EPUB spine has three parts",partCount==3,numv(partCount));
  expect("the fixture PDF has three pages",pdf.ids.size()==3,numv(pdf.ids.size()));
  expect("the fixture CBZ has three pages",cbz.ids.size()==3,numv(cbz.ids.size()));
  size_t uniquePart=SIZE_MAX,repeatedPart=SIZE_MAX;
  for(size_t i=0;i<partCount;i++){size_t same=0;
    for(size_t j=0;j<partCount;j++)same+=(parts[i].path&&parts[j].path&&!std::strcmp(parts[i].path,parts[j].path))?1:0;
    if(same==1&&uniquePart==SIZE_MAX)uniquePart=i;
    if(same>1&&repeatedPart==SIZE_MAX)repeatedPart=i;}
  if(uniquePart==SIZE_MAX||repeatedPart==SIZE_MAX)fatal("fixture spine lacks unique and repeated parts");
  std::vector<std::string> dbs{S.lib_path,S.product_path};
  revcount revs_before=revisions();
  sdkcount sdk_before=sdk_state();
  std::string fingerprint_before=databases(dbs);
  expect("the revision store and the SDK library start empty",revs_before.rows==0&&revs_before.outbox==0&&sdk_before.progress_found==0
    &&sdk_before.notes==0&&sdk_before.fixed_notes==0&&sdk_before.epub_notes==0,
    "rows="+numv(revs_before.rows)+" outbox="+numv(revs_before.outbox)+" progress="+numv(sdk_before.progress_found));

  /* ---------------- A: one history across four real formats ---------------- */
  stage("history across four formats");
  reader_jh *H=nullptr;opened(&H,nullptr);
  reader_jh_state s0=snapshot(H);
  expect("the default limit is 64 entries and 256 KiB",s0.max_entries==READER_JH_DEFAULT_ENTRIES&&s0.max_bytes==READER_JH_DEFAULT_BYTES,state_text(s0));
  expect("an opened history is empty",s0.count==0&&s0.cursor==0&&s0.bytes==0&&!s0.can_back&&!s0.can_forward,state_text(s0));
  {
    reader_jh_item item{};reader_jh_error err{};
    expect("peek back on an empty history is EMPTY",reader_jh_peek(H,READER_JH_BACK,&item,&err)==READER_JH_EMPTY,err.message);
    expect("a refused peek returns a zeroed item",item.wire==nullptr&&item.wire_bytes==0&&item.entry_id==0);
    expect("peek forward on an empty history is EMPTY",reader_jh_peek(H,READER_JH_FORWARD,&item,&err)==READER_JH_EMPTY,err.message);
    expect("item_at outside an empty history is ARGUMENT",reader_jh_item_at(H,0,&item,&err)==READER_JH_ARGUMENT,err.message);
    reader_jh_state bad{};bad.struct_version=99;
    expect("state_get refuses an unknown struct version",reader_jh_state_get(H,&bad,&err)==READER_JH_VERSION_UNSUPPORTED,err.message);
  }
  size_t first3=locate(textTxt,"读");
  exr_anchor aTxt1{};SDK(exr_anchor_create(docTxt,first3,first3,&aTxt1,&e_));
  reader_rs_capture cTxt1{};cTxt1.mode=READER_RS_REFLOW_GLOBAL;cTxt1.anchor=&aTxt1;
  commit_report rTxt1=commit_capture(H,"txt",READER_JH_PAGE,cTxt1,0);
  expect_committed("a real TXT reflow capture is stored as ADDED",rTxt1,READER_JH_ADDED);
  {reader_jh_item it=current_item(H);reader_rs_record rec{};reader_rs_error re{};
   if(!decode_item(it,&rec,&re))fatal(std::string("decode stored txt wire: ")+re.message);
   expect("the stored TXT wire names the original by its generated SHA-256",std::string(rec.book_key)==keys["txt"],rec.book_key);
   record_stored("txt-page-first","txt",rTxt1,it,rec);reader_rs_record_free(&rec);reader_jh_item_release(&it);}
  commit_report rTxt1b=commit_capture(H,"txt",READER_JH_PAGE,cTxt1,0);
  expect_committed("the same landing again is UNCHANGED",rTxt1b,READER_JH_UNCHANGED);
  expect("UNCHANGED keeps the entry id and the single entry",rTxt1b.result.entry_id==rTxt1.result.entry_id&&snapshot(H).count==1,
    "entry_id="+numv(rTxt1b.result.entry_id)+" "+state_text(snapshot(H)));
  size_t eta=locate(textTxt,"The repeated phrase appears here.");
  exr_anchor aTxt2{};SDK(exr_anchor_create(docTxt,eta,eta,&aTxt2,&e_));
  reader_rs_capture cTxt2{};cTxt2.mode=READER_RS_REFLOW_GLOBAL;cTxt2.anchor=&aTxt2;
  commit_report rTxt2=commit_capture(H,"txt",READER_JH_PAGE,cTxt2,0);
  expect_committed("a page turn inside one book coalesces",rTxt2,READER_JH_COALESCED);
  expect("coalescing keeps one TXT entry",snapshot(H).count==1,state_text(snapshot(H)));
  std::string chapterUnique;
  {exr_pager *pg=pager(uniquePart);chapterUnique=chapter_text(pg);exr_pager_free(pg);}
  size_t q=locate(chapterUnique,"阅读跳转在这里");
  exr_anchor aEpub{};{exr_pager *pg=pager(uniquePart);SDK(exr_pager_anchor_create(pg,q,q,nullptr,&aEpub,&e_));exr_pager_free(pg);}
  reader_rs_capture cEpub{};cEpub.mode=READER_RS_EPUB_CHAPTER;cEpub.anchor=&aEpub;cEpub.part_path=parts[uniquePart].path;
  commit_report rEpub=commit_capture(H,"epub",READER_JH_SEARCH,cEpub,uniquePart);
  expect_committed("a real EPUB chapter capture is stored as ADDED",rEpub,READER_JH_ADDED);
  uint64_t epubEntry=rEpub.result.entry_id;
  {reader_jh_item it=current_item(H);reader_rs_record rec{};reader_rs_error re{};
   if(!decode_item(it,&rec,&re))fatal(std::string("decode stored epub wire: ")+re.message);
   expect("the stored EPUB wire keeps the spine index of the visible part",rec.part==(uint64_t)uniquePart,
     "part="+numv(rec.part)+" expected="+numv(uniquePart)+" path="+(rec.part_path?rec.part_path:""));
   record_stored("epub-chapter-search","epub",rEpub,it,rec);reader_rs_record_free(&rec);reader_jh_item_release(&it);}
  std::string pageOne=fixed_text(pdf.doc,0);
  size_t ps=locate(pageOne,"Shared quote across pages.");
  exr_fixed_anchor aPdf{};exr_fixed_text *pdfText=nullptr;
  SDK(exr_fixed_load_text(pdf.doc,0,nullptr,&pdfText,&e_));
  SDK(exr_fixed_anchor_create(pdf.ids[0].c_str(),pdfText,ps,ps,&aPdf,&e_));
  reader_rs_capture cPdf{};cPdf.mode=READER_RS_FIXED_PAGE;cPdf.fixed=&aPdf;cPdf.page=0;
  commit_report rPdf=commit_capture(H,"pdf",READER_JH_TOC,cPdf,0);
  expect_committed("a real PDF page capture is stored as ADDED",rPdf,READER_JH_ADDED);
  {reader_jh_item it=current_item(H);reader_rs_record rec{};reader_rs_error re{};
   if(!decode_item(it,&rec,&re))fatal(std::string("decode stored pdf wire: ")+re.message);
   expect("the stored PDF wire keeps the page ID and the page number",rec.page_id&&pdf.ids[0]==rec.page_id&&rec.page==0,
     "page_id="+(rec.page_id?std::string(rec.page_id):std::string("null")));
   record_stored("pdf-page-one","pdf",rPdf,it,rec);reader_rs_record_free(&rec);reader_jh_item_release(&it);}
  exr_fixed_text_free(pdfText);exr_fixed_anchor_free(&aPdf);
  exr_fixed_anchor aCbz{};exr_fixed_text *cbzText=nullptr;
  SDK(exr_fixed_load_text(cbz.doc,1,nullptr,&cbzText,&e_));
  SDK(exr_fixed_anchor_create(cbz.ids[1].c_str(),cbzText,0,0,&aCbz,&e_));
  reader_rs_capture cCbz{};cCbz.mode=READER_RS_FIXED_PAGE;cCbz.fixed=&aCbz;cCbz.page=1;
  commit_report rCbz=commit_capture(H,"cbz",READER_JH_PAGE,cCbz,0);
  expect_committed("a real CBZ textless page point is stored as ADDED",rCbz,READER_JH_ADDED);
  {reader_jh_item it=current_item(H);reader_rs_record rec{};reader_rs_error re{};
   if(!decode_item(it,&rec,&re))fatal(std::string("decode stored cbz wire: ")+re.message);
   expect("a textless fixed page stores an empty quote with has_location set",rec.exact_size==0&&rec.has_location);
   record_stored("cbz-textless-point","cbz",rCbz,it,rec);reader_rs_record_free(&rec);reader_jh_item_release(&it);}
  exr_fixed_text_free(cbzText);exr_fixed_anchor_free(&aCbz);
  reader_jh_state s4=snapshot(H);
  expect("four landings across four books leave four entries",s4.count==4&&s4.cursor==3,state_text(s4));
  expect("the newest entry has nothing ahead of it",s4.can_forward==0&&s4.can_back==1,state_text(s4));

  /* ---------------- B: back and forward, always re-resolved first ---------- */
  stage("back and forward");
  {
    reader_jh_state before=snapshot(H);reader_jh_item it{};reader_jh_error err{};
    reader_jh_status st=reader_jh_peek(H,READER_JH_BACK,&it,&err);
    expect("peek back names the pdf entry",st==READER_JH_OK&&std::string(it.book_key)==keys["pdf"],
      "status="+std::string(jh_name(st))+" book="+(st==READER_JH_OK?std::string(it.book_key):std::string("")));
    expect("peek does not move the cursor",same_state(before,snapshot(H)));
    reader_rs_record rec{};reader_rs_error re{};bool found=false;
    if(decode_item(it,&rec,&re)){
      exr_anchor_match m{};size_t page=SIZE_MAX;
      reader_rs_status rs=reader_rs_fixed_page(pdf.doc,rec.page_id,&page,&re);
      if(rs==READER_RS_OK)rs=reader_rs_resolve_fixed(pdf.doc,&rec,nullptr,&page,&m,&re);
      found=rs==READER_RS_OK&&m.state==EXR_ANCHOR_FOUND&&m.start==rec.start&&m.end==rec.end&&page==rec.page;
      expect("the host re-resolves the PDF target on its own SDK owner",found,
        "status="+std::string(rs_name(rs))+" state="+std::string(state_name(m.state))+" page="+numv(page));
      reader_rs_record_free(&rec);
    }else expect("the PDF target decodes",false,re.message);
    if(found){reader_jh_status c=reader_jh_complete(H,&it,&err);expect("complete moves the cursor after FOUND",c==READER_JH_OK,err.message);}
    add_move("back-pdf","BACK",before,snapshot(H),"resolved FOUND then completed");
    reader_jh_item_release(&it);
  }
  {
    reader_jh_state before=snapshot(H);reader_jh_item it{};reader_jh_error err{};
    reader_jh_status st=reader_jh_peek(H,READER_JH_BACK,&it,&err);
    expect("peek back names the epub entry",st==READER_JH_OK&&it.entry_id==epubEntry,
      "status="+std::string(jh_name(st))+" entry="+numv(it.entry_id)+" expected="+numv(epubEntry));
    reader_rs_record rec{};reader_rs_error re{};bool found=false;std::string detail="not decoded";
    if(decode_item(it,&rec,&re)){
      size_t part=SIZE_MAX;reader_rs_status rs=reader_rs_epub_record_part(pub,&rec,&part,&re);
      if(rs==READER_RS_OK){exr_pager *pg=pager(part);exr_anchor_match m{};rs=reader_rs_resolve_epub(pub,pg,part,&rec,nullptr,&m,&re);exr_pager_free(pg);
        found=rs==READER_RS_OK&&m.state==EXR_ANCHOR_FOUND&&m.start==rec.start;detail="part="+numv(part)+" state="+state_name(m.state);}
    }
    expect("the host re-resolves the EPUB target on its own SDK owner",found,detail);
    if(found){reader_jh_status c=reader_jh_complete(H,&it,&err);expect("complete moves onto the epub entry",c==READER_JH_OK,err.message);}
    add_move("back-epub","BACK",before,snapshot(H),"resolved FOUND then completed");
    reader_rs_record_free(&rec);reader_jh_item_release(&it);
  }
  {
    reader_jh_state before=snapshot(H);reader_jh_item it{};reader_jh_error err{};
    reader_jh_status st=reader_jh_peek(H,READER_JH_BACK,&it,&err);
    expect("peek back names the coalesced txt entry",st==READER_JH_OK&&std::string(it.book_key)==keys["txt"],err.message);
    reader_rs_record rec{};reader_rs_error re{};bool found=false;std::string detail="not decoded";
    if(decode_item(it,&rec,&re)){
      exr_anchor_match m{};reader_rs_status rs=reader_rs_resolve_reflow(docTxt,&rec,nullptr,&m,&re);
      found=rs==READER_RS_OK&&m.state==EXR_ANCHOR_FOUND&&m.start==rec.start&&m.end==rec.end;
      detail="status="+std::string(rs_name(rs))+" state="+state_name(m.state)+" start="+numv(rec.start);
    }
    expect("the host re-resolves the TXT target on its own SDK owner",found,detail);
    if(found){reader_jh_status c=reader_jh_complete(H,&it,&err);expect("complete moves onto the txt entry",c==READER_JH_OK,err.message);}
    add_move("back-txt-oldest","BACK",before,snapshot(H),"resolved FOUND then completed");
    reader_rs_record_free(&rec);reader_jh_item_release(&it);
  }
  {reader_jh_item it{};reader_jh_error err{};reader_jh_state before=snapshot(H);
   expect("nothing is behind the oldest entry",reader_jh_peek(H,READER_JH_BACK,&it,&err)==READER_JH_EMPTY,err.message);
   expect("a refused peek behind the oldest entry changes nothing",same_state(before,snapshot(H)));}
  {reader_jh_state before=snapshot(H);reader_jh_item it{};reader_jh_error err{};
   reader_jh_status st=reader_jh_peek(H,READER_JH_FORWARD,&it,&err);
   reader_rs_record rec{};reader_rs_error re{};bool found=false;
   if(st==READER_JH_OK&&decode_item(it,&rec,&re)){
     size_t part=SIZE_MAX;reader_rs_status rs=reader_rs_epub_record_part(pub,&rec,&part,&re);
     if(rs==READER_RS_OK){exr_pager *pg=pager(part);exr_anchor_match m{};rs=reader_rs_resolve_epub(pub,pg,part,&rec,nullptr,&m,&re);exr_pager_free(pg);
       found=rs==READER_RS_OK&&m.state==EXR_ANCHOR_FOUND;}
   }
   expect("forward returns the entry that was left behind",found,"status="+std::string(jh_name(st)));
   if(found){reader_jh_error ce{};expect("complete moves forward",reader_jh_complete(H,&it,&ce)==READER_JH_OK,ce.message);}
   add_move("forward-epub","FORWARD",before,snapshot(H),"resolved FOUND then completed");
   reader_rs_record_free(&rec);reader_jh_item_release(&it);}
  /* Cancellation: a peeked target that is never completed moves nothing. */
  {reader_jh_state before=snapshot(H);reader_jh_item it{};reader_jh_error err{};
   expect("a forward peek succeeds before a cancel",reader_jh_peek(H,READER_JH_FORWARD,&it,&err)==READER_JH_OK,err.message);
   reader_jh_item_release(&it);
   expect_unchanged(H,before,"a cancelled jump leaves the cursor and generation alone");}
  /* Stale: a landing after the peek invalidates the item. */
  {reader_jh_state before=snapshot(H);reader_jh_item it{};reader_jh_error err{};
   expect("a forward peek succeeds before the history changes",reader_jh_peek(H,READER_JH_FORWARD,&it,&err)==READER_JH_OK,err.message);
   exr_anchor stale{};SDK(exr_anchor_create(docTxt,eta,eta,&stale,&e_));
   reader_rs_capture staleC{};staleC.mode=READER_RS_REFLOW_GLOBAL;staleC.anchor=&stale;
   commit_report rs2=commit_capture(H,"txt",READER_JH_SEARCH,staleC,0);
   expect_committed("a search landing after a forward peek truncates forward",rs2,READER_JH_ADDED);
   reader_jh_state mid=snapshot(H);
   reader_jh_error ce{};
   expect("complete refuses an item the history has moved past",reader_jh_complete(H,&it,&ce)==READER_JH_STALE,ce.message);
   expect_unchanged(H,mid,"a stale complete moves nothing");
   exr_anchor_free(&stale);reader_jh_item_release(&it);}
  /* Ambiguity never becomes FOUND and never moves the cursor. */
  {size_t amb=locate(textTxt,"AMBIGUOUS TARGET",1);
   exr_anchor ambiguous{};SDK(exr_anchor_create(docTxt,amb,amb,&ambiguous,&e_));
   reader_rs_capture ambC{};ambC.mode=READER_RS_REFLOW_GLOBAL;ambC.anchor=&ambiguous;
   commit_report rAmb=commit_capture(H,"txt",READER_JH_SEARCH,ambC,0);
   expect_committed("an ambiguous place can still be recorded",rAmb,READER_JH_ADDED);
   size_t other=locate(textTxt,"Jump beta start.");
   exr_anchor otherA{};SDK(exr_anchor_create(docTxt,other,other,&otherA,&e_));
   reader_rs_capture otherC{};otherC.mode=READER_RS_REFLOW_GLOBAL;otherC.anchor=&otherA;
   commit_report rOther=commit_capture(H,"txt",READER_JH_SEARCH,otherC,0);
   expect_committed("a later landing clears the forward stack",rOther,READER_JH_ADDED);
   reader_jh_state before=snapshot(H);reader_jh_item it{};reader_jh_error err{};
   reader_jh_status st=reader_jh_peek(H,READER_JH_BACK,&it,&err);
   reader_rs_record rec{};reader_rs_error re{};std::string state="not decoded";
   if(st==READER_JH_OK&&decode_item(it,&rec,&re)){
     exr_anchor_match m{};reader_rs_status rs=reader_rs_resolve_reflow(docTxt,&rec,nullptr,&m,&re);
     state=std::string(rs_name(rs))+"/"+state_name(m.state);
     expect("an ambiguous target is not reported as found",rs==READER_RS_UNRESOLVED&&m.state==EXR_ANCHOR_AMBIGUOUS,state);
     expect("an unresolved target does not move the cursor",same_state(before,snapshot(H)),state);
   }else expect("the ambiguous target decodes",false,re.message);
   reader_rs_record_free(&rec);reader_jh_item_release(&it);
   exr_anchor_free(&otherA);exr_anchor_free(&ambiguous);}
  /* Repeated spine: the stored index addresses the part, the path alone cannot. */
  {std::string repeatedChapter;{exr_pager *pg=pager(repeatedPart);repeatedChapter=chapter_text(pg);exr_pager_free(pg);}
   size_t ra=locate(repeatedChapter,"Repeated spine chapter");
   exr_anchor aRep{};{exr_pager *pg=pager(repeatedPart);SDK(exr_pager_anchor_create(pg,ra,ra,nullptr,&aRep,&e_));exr_pager_free(pg);}
   reader_rs_capture cRep{};cRep.mode=READER_RS_EPUB_CHAPTER;cRep.anchor=&aRep;cRep.part_path=parts[repeatedPart].path;
   commit_report rRep=commit_capture(H,"epub",READER_JH_SEARCH,cRep,repeatedPart);
   expect_committed("a repeated spine part is still a stored landing",rRep,READER_JH_ADDED);
   reader_jh_item it=current_item(H);reader_rs_record rec{};reader_rs_error re{};
   if(decode_item(it,&rec,&re)){
     expect("the stored wire keeps the repeated part index",rec.part==(uint64_t)repeatedPart,"part="+numv(rec.part));
     size_t byPath=SIZE_MAX;reader_rs_status pathStatus=reader_rs_epub_part(pub,rec.part_path,&byPath,&re);
     expect("a repeated spine path is refused when only the path is known",
       pathStatus==READER_RS_IDENTITY&&re.gap==READER_RS_GAP_ROUTE,"status="+std::string(rs_name(pathStatus))+" gap="+gap_name(re.gap));
     size_t byIndex=SIZE_MAX;reader_rs_status indexStatus=reader_rs_epub_record_part(pub,&rec,&byIndex,&re);
     expect("the stored spine index addresses the repeated part",indexStatus==READER_RS_OK&&byIndex==repeatedPart,"part="+numv(byIndex));
     bool found=false;
     if(indexStatus==READER_RS_OK){exr_pager *pg=pager(byIndex);exr_anchor_match m{};reader_rs_status rs=reader_rs_resolve_epub(pub,pg,byIndex,&rec,nullptr,&m,&re);
       found=rs==READER_RS_OK&&m.state==EXR_ANCHOR_FOUND&&m.start==rec.start;exr_pager_free(pg);}
     expect("the repeated spine target re-resolves FOUND through its index",found);
     record_stored("epub-repeated-spine","epub",rRep,it,rec);
   }else expect("the repeated spine target decodes",false,re.message);
   reader_rs_record_free(&rec);reader_jh_item_release(&it);exr_anchor_free(&aRep);}
  /* Textless fixed page: a point with no quote is a real position. */
  {reader_jh_state before=snapshot(H);
   exr_fixed_anchor aTextless{};exr_fixed_text *t=nullptr;
   SDK(exr_fixed_load_text(pdf.doc,2,nullptr,&t,&e_));
   SDK(exr_fixed_anchor_create(pdf.ids[2].c_str(),t,0,0,&aTextless,&e_));
   reader_rs_capture cTextless{};cTextless.mode=READER_RS_FIXED_PAGE;cTextless.fixed=&aTextless;cTextless.page=2;
   commit_report rTextless=commit_capture(H,"pdf",READER_JH_PAGE,cTextless,0);
   expect_committed("a textless PDF page point is stored as ADDED",rTextless,READER_JH_ADDED);
   exr_fixed_text_free(t);exr_fixed_anchor_free(&aTextless);
   exr_anchor back{};SDK(exr_anchor_create(docTxt,first3,first3,&back,&e_));
   reader_rs_capture backC{};backC.mode=READER_RS_REFLOW_GLOBAL;backC.anchor=&back;
   expect_committed("the following landing is ADDED",commit_capture(H,"txt",READER_JH_SEARCH,backC,0),READER_JH_ADDED);
   reader_jh_item it{};reader_jh_error err{};
   expect("peek back returns the textless page",reader_jh_peek(H,READER_JH_BACK,&it,&err)==READER_JH_OK,err.message);
   reader_rs_record rec{};reader_rs_error re{};bool found=false;
   if(decode_item(it,&rec,&re)){exr_anchor_match m{};size_t page=SIZE_MAX;
     reader_rs_status rs=reader_rs_fixed_page(pdf.doc,rec.page_id,&page,&re);
     if(rs==READER_RS_OK)rs=reader_rs_resolve_fixed(pdf.doc,&rec,nullptr,&page,&m,&re);
     found=rs==READER_RS_OK&&m.state==EXR_ANCHOR_FOUND&&page==2;}
   expect("a textless fixed page target resolves FOUND",found);
   expect("the textless target still has an entry",it.entry_id==rTextless.result.entry_id,"entry="+numv(it.entry_id));
   add_move("back-textless-pdf","BACK",before,snapshot(H),"resolved FOUND; cursor left by cancel");
   reader_rs_record_free(&rec);reader_jh_item_release(&it);
   exr_anchor_free(&back);}
  {
    reader_jh_state s=snapshot(H);
    expect("the history still holds every recorded landing",s.count>=6,state_text(s));
    reader_jh_item it=current_item(H);
    std::string id=revision_id_of(it.wire?std::string(it.wire,it.wire_bytes):std::string());
    char *bytes=nullptr;size_t size=0;reader_revision_info info{};reader_revision_error re{};
    reader_revision_status st=id.empty()?READER_REV_FORMAT:reader_revision_get(S.store,id.c_str(),&bytes,&size,&info,&re);
    expect("the transient position ID is not a stored product revision",!id.empty()&&st==READER_REV_NOT_FOUND,
      "id="+(id.empty()?std::string("missing"):id)+" status="+numv((unsigned)st));
    reader_revision_bytes_free(bytes);reader_jh_item_release(&it);
    closed(&H);
  }
  exr_anchor_free(&aTxt1);exr_anchor_free(&aTxt2);exr_anchor_free(&aEpub);

  /* ---------------- C: limits, eviction and hard caps ---------------- */
  stage("limits and eviction");
  reader_jh_limits lim{};lim.struct_version=READER_JH_STRUCT_VERSION;lim.max_entries=4;
  reader_jh *H2=nullptr;opened(&H2,&lim);
  size_t base=locate(textTxt,"Filler line 0000");
  for(int i=0;i<6;i++){
    exr_anchor p{};SDK(exr_anchor_create(docTxt,base+(size_t)i*40,base+(size_t)i*40,&p,&e_));
    reader_rs_capture c{};c.mode=READER_RS_REFLOW_GLOBAL;c.anchor=&p;
    commit_report r=commit_capture(H2,"txt",READER_JH_SEARCH,c,0);
    expect("search landing "+numv((size_t)i)+" is ADDED",r.status==READER_JH_OK&&r.result.outcome==READER_JH_ADDED,
      std::string(jh_name(r.status))+" "+r.error.message);
    if(i>=4)expect("overflowing the entry cap reports the dropped entry",r.result.evicted==1,"evicted="+numv(r.result.evicted));
    exr_anchor_free(&p);
  }
  {reader_jh_state s=snapshot(H2);
   expect("the entry cap keeps exactly four entries",s.count==4,state_text(s));
   expect("the entry cap dropped the two oldest",s.evicted_total==2,state_text(s));
   expect("the newest entry is current after eviction",s.cursor==3&&!s.can_forward,state_text(s));
   reader_jh_item it{};reader_jh_error err{};
   expect("item_at(0) reads the oldest kept entry",reader_jh_item_at(H2,0,&it,&err)==READER_JH_OK&&it.index==0,err.message);
   reader_rs_record rec{};reader_rs_error re{};
   if(decode_item(it,&rec,&re))expect("eviction kept the newest four positions",rec.start==(uint64_t)(base+2*40+0),
     "start="+numv(rec.start)+" expected="+numv(base+2*40));
   else expect("the oldest kept entry decodes",false,re.message);
   reader_rs_record_free(&rec);reader_jh_item_release(&it);}
  closed(&H2);
  lim.max_entries=64;lim.max_bytes=4096;
  reader_jh *H3=nullptr;opened(&H3,&lim);
  {reader_jh_state s=snapshot(H3);expect("the byte budget is applied",s.max_bytes==4096&&s.max_entries==64,state_text(s));}
  /* A selection is not a reading position: the installed validator refuses a
     non-point progress selector, so the history refuses it too and nothing
     changes. That is also why one legitimate entry (bounded by book_key, a
     <=1024 byte EPUB part path, 32-scalar context and its wire) cannot exceed
     the 4 KiB byte floor on its own, so the budget is proven by eviction and
     the per-entry cap by the wire API below. */
  {reader_jh_state before=snapshot(H3);
   exr_anchor selection{};SDK(exr_anchor_create(docTxt,base,base+4400,&selection,&e_));
   reader_rs_capture c{};c.mode=READER_RS_REFLOW_GLOBAL;c.anchor=&selection;
   commit_report r=commit_capture(H3,"txt",READER_JH_SEARCH,c,0);
   expect("a progress selection is refused by the installed validator",
     r.status==READER_JH_REVISION&&r.error.rs_code==READER_RS_REVISION,
     std::string(jh_name(r.status))+" rs="+rs_name(r.error.rs_code)+" revision_code="+numv(r.error.revision_code)+" "+r.error.message);
   expect_unchanged(H3,before,"a refused selection leaves the history untouched");
   exr_anchor_free(&selection);}
  for(int i=0;i<16;i++){
    exr_anchor p{};SDK(exr_anchor_create(docTxt,base+(size_t)i*40,base+(size_t)i*40,&p,&e_));
    reader_rs_capture c{};c.mode=READER_RS_REFLOW_GLOBAL;c.anchor=&p;
    commit_report r=commit_capture(H3,"txt",READER_JH_SEARCH,c,0);
    if(r.status!=READER_JH_OK)fatal("byte-budget landing "+numv((size_t)i)+": "+jh_name(r.status)+" "+r.error.message);
    exr_anchor_free(&p);
  }
  {reader_jh_state s=snapshot(H3);
   expect("the byte budget is never exceeded",s.bytes<=4096,state_text(s));
   expect("the byte budget evicts the oldest entries",s.evicted_total>0,state_text(s));
   expect("the byte budget keeps the newest entry current",s.count>0&&s.cursor==s.count-1,state_text(s));}
  {std::string huge(READER_JH_MAX_ENTRY_BYTES+1,'A');
   commit_report r=commit_wire(H3,READER_JH_PAGE,huge);
   expect("a wire above the per-entry cap is TOO_LARGE",r.status==READER_JH_TOO_LARGE,std::string(jh_name(r.status))+" "+r.error.message);}
  closed(&H3);
  {reader_jh_limits l{};l.struct_version=READER_JH_STRUCT_VERSION;l.max_entries=READER_JH_MAX_ENTRIES+1;
   reader_jh *h=nullptr;reader_jh_error err{};
   expect("257 entries is refused above the hard cap",reader_jh_open(&l,&h,&err)==READER_JH_LIMIT&&h==nullptr,err.message);}
  {reader_jh_limits l{};l.struct_version=READER_JH_STRUCT_VERSION;l.max_bytes=READER_JH_MIN_BYTES-1;
   reader_jh *h=nullptr;reader_jh_error err{};
   expect("a byte budget below the floor is refused",reader_jh_open(&l,&h,&err)==READER_JH_LIMIT&&h==nullptr,err.message);}
  {reader_jh_limits l{};l.struct_version=READER_JH_STRUCT_VERSION;l.max_bytes=READER_JH_MAX_BYTES+1;
   reader_jh *h=nullptr;reader_jh_error err{};
   expect("a byte budget above the hard cap is refused",reader_jh_open(&l,&h,&err)==READER_JH_LIMIT&&h==nullptr,err.message);}
  {reader_jh_limits l{};l.struct_version=READER_JH_STRUCT_VERSION;l.max_entries=READER_JH_MAX_ENTRIES;
   reader_jh *h=nullptr;reader_jh_error err{};
   reader_jh_status st=reader_jh_open(&l,&h,&err);
   expect("the 256 entry cap opens",st==READER_JH_OK,err.message);
   if(st==READER_JH_OK){reader_jh_state s=snapshot(h);expect("the 256 entry cap is reported",s.max_entries==READER_JH_MAX_ENTRIES,state_text(s));closed(&h);}}
  {reader_jh_limits l{};l.struct_version=READER_JH_STRUCT_VERSION;l.max_bytes=READER_JH_MAX_BYTES;
   reader_jh *h=nullptr;reader_jh_error err{};
   reader_jh_status st=reader_jh_open(&l,&h,&err);
   expect("the 1 MiB byte cap opens",st==READER_JH_OK,err.message);
   if(st==READER_JH_OK){reader_jh_state s=snapshot(h);expect("the 1 MiB byte cap is reported",s.max_bytes==READER_JH_MAX_BYTES,state_text(s));closed(&h);}}
  {reader_jh_limits l{};l.struct_version=READER_JH_STRUCT_VERSION+1;
   reader_jh *h=nullptr;reader_jh_error err{};
   expect("an unknown limits struct version is refused",reader_jh_open(&l,&h,&err)==READER_JH_VERSION_UNSUPPORTED&&h==nullptr,err.message);}

  /* ---------------- D: refused inputs never change the history ---------------- */
  stage("error paths");
  reader_jh *E=nullptr;opened(&E,nullptr);
  exr_anchor eAnchor{};SDK(exr_anchor_create(docTxt,0,0,&eAnchor,&e_));
  exr_anchor eSelection{};SDK(exr_anchor_create(docTxt,0,first3+std::strlen("读"),&eSelection,&e_));
  reader_rs_capture eSelCapture{};eSelCapture.mode=READER_RS_REFLOW_GLOBAL;eSelCapture.anchor=&eSelection;
  reader_rs_capture eCapture{};eCapture.mode=READER_RS_REFLOW_GLOBAL;eCapture.anchor=&eAnchor;
  expect_committed("the error-case landing is ADDED",commit_capture(E,"txt",READER_JH_PAGE,eCapture,0),READER_JH_ADDED);
  reader_jh_state eb=snapshot(E);
  reader_jh_result rr{};reader_jh_error err{};
  reader_jh_position pos{keys["txt"].c_str(),parser_version.c_str(),READER_JH_PAGE,&eCapture,0};
  {reader_jh_position p=pos;p.kind=(reader_jh_kind)0;
   expect("a landing without a kind is ARGUMENT",reader_jh_commit(E,S.store,&p,&rr,&err)==READER_JH_ARGUMENT,err.message);}
  {reader_jh_position p=pos;p.kind=(reader_jh_kind)4;
   expect("an unknown landing kind is ARGUMENT",reader_jh_commit(E,S.store,&p,&rr,&err)==READER_JH_ARGUMENT,err.message);}
  {reader_jh_position p=pos;p.capture=nullptr;
   expect("a missing capture is ARGUMENT",reader_jh_commit(E,S.store,&p,&rr,&err)==READER_JH_ARGUMENT,err.message);}
  {reader_jh_position p=pos;p.book_key=nullptr;
   expect("a missing book key is ARGUMENT",reader_jh_commit(E,S.store,&p,&rr,&err)==READER_JH_ARGUMENT,err.message);}
  {reader_jh_position p=pos;p.parser_version=nullptr;
   expect("a missing parser version is ARGUMENT",reader_jh_commit(E,S.store,&p,&rr,&err)==READER_JH_ARGUMENT,err.message);}
  expect("a missing result is ARGUMENT",reader_jh_commit(E,S.store,&pos,nullptr,&err)==READER_JH_ARGUMENT,err.message);
  expect("a missing revision store is ARGUMENT",reader_jh_commit(E,nullptr,&pos,&rr,&err)==READER_JH_ARGUMENT,err.message);
  expect("a null position is ARGUMENT",reader_jh_commit(E,S.store,nullptr,&rr,&err)==READER_JH_ARGUMENT,err.message);
  expect_unchanged(E,eb,"every refused commit left the entry alone");
  {char rid[33];reader_revision_error ie{};
   if(reader_revision_new_id(rid,&ie)!=READER_REV_OK)fatal("new revision id");
   char *aw=nullptr;size_t an=0;reader_rs_error re{};
   std::string annotationId(32,'0');annotationId[0]='a';annotationId[30]='c';annotationId[31]='7';
   reader_rs_envelope aenv{};aenv.revision_id=rid;aenv.operation="put";aenv.entity_kind="annotation";
   aenv.annotation_id=annotationId.c_str();aenv.book_key=keys["txt"].c_str();
   aenv.parser_version=parser_version.c_str();aenv.note_text="not a position";
   reader_rs_status as=reader_rs_encode_v2(S.store,&aenv,&eSelCapture,0,&aw,&an,&re);
   expect("the installed encoder accepts an annotation as a control",as==READER_RS_OK,std::string(rs_name(as))+" "+re.message);
   if(as==READER_RS_OK){std::string wire(aw,an);reader_rs_free(aw);
     commit_report r=commit_wire(E,READER_JH_PAGE,wire);
     expect("an annotation wire is not a reading position",r.status==READER_JH_ARGUMENT,std::string(jh_name(r.status))+" "+r.error.message);}
   else reader_rs_free(aw);
   if(reader_revision_new_id(rid,&ie)!=READER_REV_OK)fatal("new revision id");
   char *dw=nullptr;size_t dn=0;
   reader_rs_envelope denv{};denv.revision_id=rid;denv.operation="delete";denv.entity_kind="progress";
   denv.book_key=keys["txt"].c_str();denv.parser_version=parser_version.c_str();
   reader_rs_capture dcap{};dcap.mode=READER_RS_REFLOW_GLOBAL;dcap.anchor=nullptr;
   reader_rs_status ds=reader_rs_encode_v2(S.store,&denv,&dcap,0,&dw,&dn,&re);
   bool deleteRefused=false;std::string deleteDetail=std::string(rs_name(ds))+" "+re.message;
   if(ds==READER_RS_OK){
     std::string wire(dw,dn);reader_rs_free(dw);dw=nullptr;
     commit_report r=commit_wire(E,READER_JH_PAGE,wire);
     deleteRefused=r.status==READER_JH_ARGUMENT;
     deleteDetail=std::string(jh_name(r.status))+" "+r.error.message;
   }else{
     deleteRefused=true;
     deleteDetail=std::string("the installed encoder refuses a progress delete: ")+rs_name(ds)+" "+re.message;
   }
   reader_rs_free(dw);
   expect("a delete wire is not a reading position",deleteRefused,deleteDetail);}
  {reader_jh_item cur{};reader_jh_error ce{};
   expect("the stored entry is readable for wire mutation",reader_jh_item_at(E,0,&cur,&ce)==READER_JH_OK,ce.message);
   std::string good(cur.wire?cur.wire:"",cur.wire_bytes);reader_jh_item_release(&cur);
   std::string truncated=good.substr(0,good.size()/2);
   commit_report rt=commit_wire(E,READER_JH_PAGE,truncated);
   expect("a truncated position wire is refused",
     rt.status==READER_JH_REVISION||rt.status==READER_JH_ARGUMENT,std::string(jh_name(rt.status))+" "+rt.error.message);
   const std::string declared="\"anchor_version\":2";
   size_t at=good.find(declared);
   if(at!=std::string::npos){
     std::string version3=good;version3.replace(at,declared.size(),"\"anchor_version\":3");
     commit_report rv=commit_wire(E,READER_JH_PAGE,version3);
     expect("an unknown anchor version is refused",
       rv.status==READER_JH_REVISION||rv.status==READER_JH_ARGUMENT,std::string(jh_name(rv.status))+" "+rv.error.message);
   }else expect("the stored wire declares anchor version 2",false);}
  expect_unchanged(E,eb,"every refused wire left the entry alone");
  {reader_jh_item it{};reader_jh_error ie{};
   expect("item_at reads the only entry",reader_jh_item_at(E,0,&it,&ie)==READER_JH_OK,ie.message);
   it.struct_version=99;
   expect("complete refuses an unknown item version",reader_jh_complete(E,&it,&ie)==READER_JH_VERSION_UNSUPPORTED,ie.message);
   it.struct_version=READER_JH_STRUCT_VERSION;it.direction=(reader_jh_direction)0;
   expect("complete refuses an item that was not peeked",reader_jh_complete(E,&it,&ie)==READER_JH_ARGUMENT,ie.message);
   it.direction=READER_JH_BACK;
   expect("complete refuses to move behind the first entry",reader_jh_complete(E,&it,&ie)==READER_JH_STALE,ie.message);
   expect("refused completes keep the item usable",it.wire!=nullptr&&it.wire_bytes>0);
   reader_jh_item_release(&it);}
  expect_unchanged(E,eb,"refused completes left the cursor alone");
  closed(&E);
  exr_anchor_free(&eSelection);
  exr_anchor_free(&eAnchor);

  /* Equal per-handle counters are not a ticket to another history. Both the
     same wire and different positions must keep the target cursor unchanged. */
  stage("history instance tickets");
  exr_anchor ticketFirst{},ticketSecond{};
  SDK(exr_anchor_create(docTxt,first3,first3,&ticketFirst,&e_));
  SDK(exr_anchor_create(docTxt,eta,eta,&ticketSecond,&e_));
  reader_rs_capture ticket1{},ticket2{};ticket1.mode=ticket2.mode=READER_RS_REFLOW_GLOBAL;
  ticket1.anchor=&ticketFirst;ticket2.anchor=&ticketSecond;
  for(bool identical:{true,false}){
    const std::string label=identical?"identical positions":"different positions";
    reader_jh *source=nullptr,*target=nullptr;opened(&source,nullptr);opened(&target,nullptr);
    for(reader_jh *h:{source,target}){
      const reader_rs_capture &first=(h==target&&!identical)?ticket2:ticket1;
      const reader_rs_capture &second=(h==target&&!identical)?ticket1:ticket2;
      if(commit_capture(h,"txt",READER_JH_SEARCH,first,0).status!=READER_JH_OK ||
         commit_capture(h,"txt",READER_JH_SEARCH,second,0).status!=READER_JH_OK)fatal("instance ticket setup");
    }
    reader_jh_item foreign{},own{};reader_jh_error ie{};
    if(reader_jh_peek(source,READER_JH_BACK,&foreign,&ie)!=READER_JH_OK ||
       reader_jh_peek(target,READER_JH_BACK,&own,&ie)!=READER_JH_OK)fatal("instance ticket peek");
    reader_jh_state before=snapshot(target);
    expect("foreign history ticket is STALE with "+label,
      reader_jh_complete(target,&foreign,&ie)==READER_JH_STALE,ie.message);
    expect_unchanged(target,before,"foreign history ticket leaves state unchanged with "+label);
    expect("own history ticket remains valid with "+label,
      reader_jh_complete(target,&own,&ie)==READER_JH_OK,ie.message);
    reader_jh_item_release(&own);closed(&source);
    opened(&source,nullptr);
    if(commit_capture(source,"txt",READER_JH_SEARCH,ticket1,0).status!=READER_JH_OK ||
       commit_capture(source,"txt",READER_JH_SEARCH,ticket2,0).status!=READER_JH_OK)fatal("reopened ticket setup");
    before=snapshot(source);
    expect("closed history ticket is STALE after reopen with "+label,
      reader_jh_complete(source,&foreign,&ie)==READER_JH_STALE,ie.message);
    expect_unchanged(source,before,"closed history ticket leaves state unchanged with "+label);
    reader_jh_item_release(&foreign);closed(&source);closed(&target);
  }
  exr_anchor_free(&ticketFirst);exr_anchor_free(&ticketSecond);

  /* ---------------- E: one owner thread at a time ---------------- */
  stage("thread ownership");
  reader_jh *T=nullptr;opened(&T,nullptr);
  {exr_anchor a{};SDK(exr_anchor_create(docTxt,0,0,&a,&e_));
   reader_rs_capture c{};c.mode=READER_RS_REFLOW_GLOBAL;c.anchor=&a;
   if(commit_capture(T,"txt",READER_JH_PAGE,c,0).status!=READER_JH_OK)fatal("thread setup landing");
   reader_rs_capture c2=c;exr_anchor b{};SDK(exr_anchor_create(docTxt,eta,eta,&b,&e_));
   c2.anchor=&b;
   if(commit_capture(T,"txt",READER_JH_SEARCH,c2,0).status!=READER_JH_OK)fatal("thread setup landing 2");
   exr_anchor_free(&a);exr_anchor_free(&b);}
  struct thread_results { reader_jh_status peek=READER_JH_OK,commit=READER_JH_OK,state=READER_JH_OK,close=READER_JH_OK,adopt=READER_JH_OK; } tr{};
  std::thread worker([&]{
    reader_jh_item item{};reader_jh_error ie{};
    tr.peek=reader_jh_peek(T,READER_JH_BACK,&item,&ie);
    reader_jh_result rr{};
    tr.commit=reader_jh_commit_wire(T,S.store,READER_JH_PAGE,"{}",2,&rr,&ie);
    reader_jh_state s{};s.struct_version=READER_JH_STRUCT_VERSION;
    tr.state=reader_jh_state_get(T,&s,&ie);
    tr.close=reader_jh_close(&T,&ie);
    tr.adopt=reader_jh_adopt_thread(T,&ie);
  });
  worker.join();
  {reader_jh_item item{};reader_jh_error ie{};
   expect("a foreign thread cannot peek",tr.peek==READER_JH_THREAD,std::string(jh_name(tr.peek)));
   expect("a foreign thread cannot commit",tr.commit==READER_JH_THREAD,std::string(jh_name(tr.commit)));
   expect("a foreign thread cannot read the state",tr.state==READER_JH_THREAD,std::string(jh_name(tr.state)));
   expect("a foreign thread cannot close the handle",tr.close==READER_JH_THREAD&&T!=nullptr,std::string(jh_name(tr.close)));
   expect("adopt_thread hands ownership to the caller",tr.adopt==READER_JH_OK,std::string(jh_name(tr.adopt)));
   expect("the previous owner is refused after adoption",reader_jh_peek(T,READER_JH_BACK,&item,&ie)==READER_JH_THREAD,ie.message);
   expect("adopt_thread returns ownership",reader_jh_adopt_thread(T,&ie)==READER_JH_OK,ie.message);
   expect("the owner can peek again",reader_jh_peek(T,READER_JH_BACK,&item,&ie)==READER_JH_OK,ie.message);
   reader_jh_item_release(&item);}
  closed(&T);

  /* ---------------- F: released sources and closed histories ---------------- */
  stage("item lifetime");
  reader_jh *L=nullptr;opened(&L,nullptr);
  exr_anchor lAnchor{};SDK(exr_anchor_create(docTxt,0,0,&lAnchor,&e_));
  reader_rs_capture lCapture{};lCapture.mode=READER_RS_REFLOW_GLOBAL;lCapture.anchor=&lAnchor;
  expect_committed("the lifetime landing is ADDED",commit_capture(L,"txt",READER_JH_PAGE,lCapture,0),READER_JH_ADDED);
  reader_jh_item held{};reader_jh_error lErr{};
  expect("item_at reads the entry",reader_jh_item_at(L,0,&held,&lErr)==READER_JH_OK,lErr.message);
  std::string wireCopy(held.wire?held.wire:"",held.wire_bytes);
  expect("the item carries the wire and its book key",
    wireCopy.size()==held.wire_bytes&&held.wire_bytes>0&&std::string(held.book_key)==keys["txt"]);
  expect("clear drops the entry",reader_jh_clear(L,&lErr)==READER_JH_OK,lErr.message);
  {reader_jh_state s=snapshot(L);expect("clear empties the history",s.count==0&&s.bytes==0,state_text(s));}
  expect("an item outlives the history contents",held.wire!=nullptr&&std::string(held.wire,held.wire_bytes)==wireCopy);
  closed(&L);
  expect("an item outlives the closed history",held.wire!=nullptr&&std::string(held.wire,held.wire_bytes)==wireCopy);
  {reader_rs_record rec{};reader_rs_error re{};
   expect("a released-history item still decodes through the installed validator",
     reader_rs_decode(S.store,held.wire,held.wire_bytes,&rec,&re)==READER_RS_OK&&std::string(rec.book_key)==keys["txt"],re.message);
   reader_rs_record_free(&rec);}
  reader_jh_item_release(&held);
  expect("release zeroes the item",held.wire==nullptr&&held.wire_bytes==0&&held.entry_id==0&&held.book_key[0]==0);
  reader_jh_item_release(nullptr);
  reader_jh *L2=nullptr;opened(&L2,nullptr);
  {exr_fixed_text *t=nullptr;SDK(exr_fixed_load_text(cbz.doc,0,nullptr,&t,&e_));
   exr_fixed_anchor fa{};SDK(exr_fixed_anchor_create(cbz.ids[0].c_str(),t,0,0,&fa,&e_));
   reader_rs_capture c{};c.mode=READER_RS_FIXED_PAGE;c.fixed=&fa;c.page=0;
   expect_committed("a cbz point is stored before its source is released",commit_capture(L2,"cbz",READER_JH_PAGE,c,0),READER_JH_ADDED);
   exr_fixed_text_free(t);exr_fixed_anchor_free(&fa);}
  {reader_jh_item it{};reader_jh_error ie{};
   expect("the entry survives the released SDK text",reader_jh_item_at(L2,0,&it,&ie)==READER_JH_OK,ie.message);
   reader_rs_record rec{};reader_rs_error re{};
   expect("the surviving entry still decodes",reader_rs_decode(S.store,it.wire,it.wire_bytes,&rec,&re)==READER_RS_OK,re.message);
   reader_rs_record_free(&rec);reader_jh_item_release(&it);}
  closed(&L2);
  exr_anchor_free(&lAnchor);

  /* ---------------- G: no product, SDK or catalog write ---------------- */
  stage("no write proof");
  revcount revs_after=revisions();
  sdkcount sdk_after=sdk_state();
  std::string fingerprint_after=databases(dbs);
  expect("no product revision and no outbox row was created",
    revs_after.rows==0&&revs_after.outbox==0&&revs_after.rows==revs_before.rows&&revs_after.outbox==revs_before.outbox,
    "rows="+numv(revs_after.rows)+" outbox="+numv(revs_after.outbox));
  expect("no SDK progress record was written",
    sdk_after.progress_found==sdk_before.progress_found&&sdk_after.progress_found==0,numv(sdk_after.progress_found));
  expect("no SDK note was written",
    sdk_after.notes==sdk_before.notes&&sdk_after.fixed_notes==sdk_before.fixed_notes&&sdk_after.epub_notes==sdk_before.epub_notes
    &&sdk_after.notes==0&&sdk_after.fixed_notes==0&&sdk_after.epub_notes==0,
    "notes="+numv(sdk_after.notes)+" fixed="+numv(sdk_after.fixed_notes)+" epub="+numv(sdk_after.epub_notes));
  expect("the library and product databases are byte-identical after the whole run",
    fingerprint_after==fingerprint_before,"before and after fingerprints differ");
  exr_document_free(docTxt);docTxt=nullptr;
  exr_fixed_free(pdf.doc);pdf.doc=nullptr;exr_fixed_free(cbz.doc);cbz.doc=nullptr;
  exr_publication_free(pub);pub=nullptr;exr_font_free(font);font=nullptr;
  close_side();
  std::string fingerprint_closed=databases(dbs);
  /* Control: the same measurement must catch a real public write. */
  open_side();
  {exr_document *doc=nullptr;exr_error e{};
   if(exr_library_document(S.lib,S.ids["txt"],&doc,&e)!=EXR_OK)fatal(std::string("control document: ")+e.message);
   exr_anchor point{};exr_error pe{};
   if(exr_anchor_create(doc,0,0,&point,&pe)!=EXR_OK)fatal(std::string("control anchor: ")+pe.message);
   exr_error we{};reader_rs_capture c{};c.mode=READER_RS_REFLOW_GLOBAL;c.anchor=&point;
   char rid[33];reader_revision_error ie{};
   if(reader_revision_new_id(rid,&ie)!=READER_REV_OK)fatal("control revision id");
   reader_rs_envelope env{};env.revision_id=rid;env.operation="put";env.entity_kind="progress";
   env.book_key=keys["txt"].c_str();env.parser_version=parser_version.c_str();
   char *wire=nullptr;size_t bytes=0;reader_rs_error re{};
   reader_rs_status es=reader_rs_encode_v2(S.store,&env,&c,0,&wire,&bytes,&re);
   expect("the control position encodes",es==READER_RS_OK,std::string(rs_name(es))+" "+re.message);
   if(es==READER_RS_OK){
     if(exr_library_progress(S.lib,S.ids["txt"],&point,&we)!=EXR_OK)fatal(std::string("control progress: ")+we.message);
     reader_revision_info info{};int created=0;
     reader_revision_status ls=reader_revision_local(S.store,wire,bytes,&info,&created,&ie);
     expect("the control product and SDK writes commit",ls==READER_REV_OK&&created==1,std::string("revision status ")+numv((unsigned)ls));
   }
   reader_rs_free(wire);exr_anchor_free(&point);exr_document_free(doc);}
  close_side();
  std::string fingerprint_control=databases(dbs);
  expect("the same measurement detects real product and SDK writes",fingerprint_control!=fingerprint_closed,
    "control fingerprint equals the untouched fingerprint");

  /* ---------------- report ---------------- */
  object books;
  for(const char *role:{"txt","epub","pdf","cbz"})
    books.set(role,object().str("book_key",keys[role]).set("bytes",numv(sizes[role])).set("sdk_id",numv(S.ids[role])).dump());
  object noWrite;
  noWrite.set("revision_rows",numv(revs_after.rows)).set("outbox_rows",numv(revs_after.outbox))
    .set("sdk_progress_records",numv(sdk_after.progress_found)).set("sdk_notes",numv(sdk_after.notes))
    .set("sdk_fixed_notes",numv(sdk_after.fixed_notes)).set("sdk_epub_notes",numv(sdk_after.epub_notes))
    .set("databases_unchanged",boolean(fingerprint_after==fingerprint_before))
    .set("control_write_changed",boolean(fingerprint_control!=fingerprint_closed))
    .str("fingerprint_before",fingerprint_before).str("fingerprint_after",fingerprint_after)
    .str("fingerprint_closed",fingerprint_closed).str("fingerprint_control",fingerprint_control);
  object out;
  out.str("sdk_version",exr_version()).str("parser_version",parser_version)
    .str("jump_history_version",READER_JH_VERSION).str("reading_state_version",READER_READING_STATE_VERSION)
    .str("revisions_version",READER_REVISIONS_VERSION)
    .set("books",books.dump()).set("no_write",noWrite.dump())
    .set("cases",array(cases)).set("lifecycle",array(lifecycle)).set("checks",array(checks))
    .set("cases_total",numv(cases.size())).set("checks_total",numv(checks.size())).set("moves",numv(moves))
    .set("failures",numv(failures));
  std::ofstream rep(report_path,std::ios::binary);rep<<out.dump()<<"\n";rep.close();
  std::printf("jump-history probe: %zu cases, %zu checks, %zu moves, %zu failures\n",cases.size(),checks.size(),moves,failures);
  return failures?1:0;
}
