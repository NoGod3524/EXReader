/* SPDX-License-Identifier: MIT */
/* Installed C++ consumer of EXReaderSearch. Reuses the unchanged reading-state
   probe's report/fixture/library helpers (its own main is renamed away) and drives
   real frozen-SDK sources: a TXT reflow document, a repeated-spine EPUB, a long
   EPUB chapter, a multi-page PDF and generated fixed documents. Every expectation
   is compared with an independent full-text scan (std::string::find over the SDK's
   own normalized text), never with the module's streaming path. */
#define main legacy_probe_main
#include "../../reader_reading_state/consumer/probe.cpp"
#undef main
#include <reader_search.h>
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <functional>
#include <map>
#include <set>
#include <tuple>
extern "C" unsigned long long search_probe_peak_memory(void);

namespace {
using triple=std::tuple<uint64_t,size_t,size_t>; /* unit,start,end */
struct rec {
  uint64_t unit=0,start=0,end=0;
  std::string path,page_id,exact,prefix,suffix,chapter;
  bool has_chapter=false;
};
struct run {
  std::vector<rec> hits;std::vector<size_t> batches;std::vector<reader_search_cursor> cursors;
  reader_search_status status=READER_SEARCH_OK;bool complete=false,contract=true;
  reader_search_stats stats{};reader_search_error error{};
};
using opener=std::function<reader_search_status(const reader_search_options *,reader_search **,reader_search_error *)>;
using visitor=std::function<void(const reader_search_hit &)>;
opener reflow_open(const exr_document *d,std::string q){
  return [=](const reader_search_options *o,reader_search **s,reader_search_error *e){return reader_search_open_reflow(d,q.data(),q.size(),o,s,e);};
}
opener epub_open(exr_publication *p,exr_font *f,std::string q){
  return [=](const reader_search_options *o,reader_search **s,reader_search_error *e){return reader_search_open_epub(p,f,nullptr,nullptr,q.data(),q.size(),o,s,e);};
}
opener fixed_open(exr_fixed_document *d,std::string q){
  return [=](const reader_search_options *o,reader_search **s,reader_search_error *e){return reader_search_open_fixed(d,q.data(),q.size(),o,s,e);};
}
rec copy_hit(const reader_search_hit &h){
  rec r;r.unit=h.unit;r.start=h.start;r.end=h.end;
  if(h.part_path)r.path=h.part_path;
  if(h.page_id)r.page_id=h.page_id;
  if(h.mode==READER_SEARCH_FIXED){
    r.exact.assign(h.fixed.exact?h.fixed.exact:"",h.fixed.exact_size);r.prefix.assign(h.fixed.prefix?h.fixed.prefix:"",h.fixed.prefix_size);
    r.suffix.assign(h.fixed.suffix?h.fixed.suffix:"",h.fixed.suffix_size);
  }else{
    r.exact=h.anchor.exact?h.anchor.exact:"";r.prefix=h.anchor.prefix?h.anchor.prefix:"";r.suffix=h.anchor.suffix?h.anchor.suffix:"";
    r.has_chapter=h.anchor.chapter!=nullptr;if(h.anchor.chapter)r.chapter=h.anchor.chapter;
  }
  return r;
}
bool same_cursor(const reader_search_cursor &a,const reader_search_cursor &b){return !std::memcmp(&a,&b,sizeof(a));}
run collect(const opener &open,size_t max,const visitor &visit=nullptr,const exr_control *control=nullptr,
            const reader_search_cursor *resume=nullptr,size_t limit=SIZE_MAX){
  run r;reader_search_options o{};o.struct_size=sizeof(o);if(control)o.control=*control;o.resume=resume;
  reader_search *s=nullptr;r.status=open(&o,&s,&r.error);if(r.status!=READER_SEARCH_OK)return r;
  for(size_t b=0;b<limit;b++){
    reader_search_result res{};reader_search_status st=reader_search_next(s,max,&res,&r.error);
    if(st!=READER_SEARCH_OK){r.status=st;break;}
    if(res.count>max||(res.count==0&&!res.complete)||(!res.complete&&res.count!=max)||(res.count==0&&res.hits))r.contract=false;
    r.batches.push_back(res.count);r.cursors.push_back(res.next);
    for(size_t i=0;i<res.count;i++){r.hits.push_back(copy_hit(res.hits[i]));if(visit)visit(res.hits[i]);}
    r.complete=res.complete!=0;reader_search_result_free(&res);
    if(r.complete)break;
  }
  reader_search_stats_get(s,&r.stats,nullptr);reader_search_close(&s,nullptr);return r;
}
std::vector<triple> triples(const run &r){std::vector<triple> v;for(const rec &h:r.hits)v.emplace_back(h.unit,h.start,h.end);return v;}
std::vector<std::pair<size_t,size_t>> find_all(const std::string &text,const std::string &q){
  std::vector<std::pair<size_t,size_t>> v;size_t at=0;
  for(;;){size_t p=text.find(q,at);if(p==std::string::npos)break;v.emplace_back(p,p+q.size());at=p+q.size();}
  return v;
}
std::vector<triple> truth_reflow(const exr_document *d,const std::string &q){
  size_t n=0;const char *t=exr_document_text(d,&n);std::vector<triple> v;
  for(auto &r:find_all(std::string(t,n),q))v.emplace_back(0,r.first,r.second);return v;
}
std::vector<triple> truth_epub(exr_publication *p,const std::string &q){
  size_t count=0;const exr_part *parts=exr_publication_parts(p,&count);std::vector<triple> v;
  for(size_t i=0;i<count;i++){
    if(!parts[i].in_reading_order)continue;
    exr_document *d=nullptr;SDK(exr_publication_load(p,i,&d,&e_));size_t n=0;const char *t=exr_document_text(d,&n);
    for(auto &r:find_all(std::string(t,n),q))v.emplace_back(i,r.first,r.second);exr_document_free(d);
  }
  return v;
}
std::vector<triple> truth_fixed(exr_fixed_document *f,const std::string &q){
  size_t count=0;exr_fixed_pages(f,&count);std::vector<triple> v;
  for(size_t i=0;i<count;i++){
    exr_fixed_text *t=nullptr;SDK(exr_fixed_load_text(f,i,nullptr,&t,&e_));size_t n=0;const char *s=exr_fixed_text_string(t,&n);
    for(auto &r:find_all(std::string(s?s:"",n),q))v.emplace_back(i,r.first,r.second);exr_fixed_text_free(t);
  }
  return v;
}
std::string qstr(size_t bytes,char c){return std::string(bytes,c);}

/* ---------- generated fixed documents (CJK, emoji, NUL-free) ---------- */
struct fx {
  std::vector<std::string> pages,ids;int fail_page=-1;int loads=0;
  std::vector<exr_fixed_page> directory;exr_fixed_document *doc=nullptr;
};
exr_status fx_text(void *context,size_t page,const exr_control *control,exr_fixed_text **out,exr_error *error){
  fx *f=(fx *)context;f->loads++;
  if((int)page==f->fail_page){error->code=EXR_IO;std::snprintf(error->message,sizeof(error->message),"injected provider failure");return EXR_IO;}
  return exr_fixed_text_create(f->pages[page].data(),f->pages[page].size(),nullptr,0,control,out,error);
}
exr_status fx_draw(void *,size_t,const double *,const exr_draw_sink *,const exr_control *,exr_error *){return EXR_OK;}
void fx_build(fx &f){
  f.ids.clear();f.directory.clear();
  for(size_t i=0;i<f.pages.size();i++)f.ids.push_back("gen-page-"+std::to_string(i)+"-"+(i%2?"b":"a"));
  for(size_t i=0;i<f.pages.size();i++){
    exr_fixed_page p{};p.id=f.ids[i].c_str();p.label=nullptr;
    p.geometry.bounds[2]=100;p.geometry.bounds[3]=100;p.geometry.unit_scale=1;f.directory.push_back(p);
  }
  exr_fixed_input in{};in.struct_size=sizeof(in);in.title="generated";in.pages=f.directory.data();in.page_count=f.directory.size();
  in.draw=fx_draw;in.context=&f;in.text=fx_text;SDK(exr_fixed_create(&in,&f.doc,&e_));
}

/* ---------- control helpers ---------- */
struct trip {int calls=0,at=-1;};
int trip_fn(void *c){trip *t=(trip *)c;if(t->at<0)return 0;return t->calls++>=t->at;}
struct reenter {reader_search *s=nullptr;std::vector<reader_search_status> seen;};
int reenter_fn(void *c){
  reenter *r=(reenter *)c;
  if(r->s){
    reader_search_result res{};reader_search_cursor cur{};reader_search_stats st{};reader_search *copy=r->s;
    r->seen.push_back(reader_search_next(r->s,1,&res,nullptr));r->seen.push_back(reader_search_cursor_get(r->s,&cur,nullptr));
    r->seen.push_back(reader_search_stats_get(r->s,&st,nullptr));r->seen.push_back(reader_search_close(&copy,nullptr));
    if(copy!=r->s)r->seen.push_back(READER_SEARCH_OK); /* handle must be kept */
  }
  return 0;
}
struct block_sink {std::vector<size_t> boundaries;size_t at=0,chunks=0;};
exr_status block_fn(void *c,const char *,size_t size,exr_error *){block_sink *b=(block_sink *)c;b->at+=size;b->boundaries.push_back(b->at);b->chunks++;return EXR_OK;}

std::vector<std::string> cases_out,measurements;
/* ---------- product compatibility: encode_v2 (never inserted), decode, public resolve ---------- */
struct tally {size_t found=0,ambiguous=0,other=0,mislocated=0,not_ok=0;};
void compat(tally &t,const char *role,const reader_rs_capture &cap,size_t part,size_t start,size_t end,
            const std::function<reader_rs_status(const reader_rs_record *,exr_anchor_match *)> &resolve){
  std::string id=new_id(),aid=new_id();
  reader_rs_envelope env{};env.revision_id=id.c_str();env.operation="put";env.entity_kind="annotation";env.book_key=keys[role].c_str();
  env.annotation_id=aid.c_str();env.note_text="search hit";env.parser_version=parser_version.c_str();
  char *wire=nullptr;size_t bytes=0;reader_rs_error error{};
  if(reader_rs_encode_v2(A.store,&env,&cap,part,&wire,&bytes,&error)!=READER_RS_OK){t.not_ok++;expect(false,std::string("encode_v2 accepts a search hit: ")+error.message);return;}
  reader_rs_record record{};reader_rs_status d=reader_rs_decode(B.store,wire,bytes,&record,&error);reader_rs_free(wire);
  if(d!=READER_RS_OK){t.not_ok++;expect(false,std::string("decode of an encoded search hit: ")+error.message);return;}
  exr_anchor_match m{};reader_rs_status st=resolve(&record,&m);reader_rs_record_free(&record);
  if(st==READER_RS_OK&&m.state==EXR_ANCHOR_FOUND){t.found++;if(m.start!=start||m.end!=end)t.mislocated++;}
  else if(st==READER_RS_UNRESOLVED&&m.state==EXR_ANCHOR_AMBIGUOUS){t.ambiguous++;if(m.start!=SIZE_MAX)t.mislocated++;}
  else{t.other++;}
}
void tally_case(const std::string &id,const char *mode,const std::string &query,const run &r,const tally &t){
  cases_out.push_back(object().str("id",id).str("mode",mode).set("query_bytes",num(query.size())).str("query_hex",hexbytes(query.data(),query.size()))
    .set("hits",num(r.hits.size())).set("batches",array([&]{std::vector<std::string> v;for(size_t b:r.batches)v.push_back(num(b));return v;}()))
    .set("complete",boolean(r.complete)).set("found",num(t.found)).set("ambiguous",num(t.ambiguous)).set("other",num(t.other))
    .set("mislocated",num(t.mislocated)).set("bytes_scanned",num(r.stats.bytes_scanned)).dump());
}
}

int main(int argc,char **argv){
  std::string fixtures,font,work,report_path;
  for(int i=1;i+1<argc;i+=2){std::string k=argv[i],v=argv[i+1];
    if(k=="--fixtures")fixtures=v;else if(k=="--font")font=v;else if(k=="--work")work=v;else if(k=="--report")report_path=v;
    else if(k=="--sha"){size_t equal=v.find('=');shas[v.substr(0,equal)]=v.substr(equal+1);}else fatal("unknown argument");}
  const char *roles[][3]={{"txt","book.txt","txt"},{"epub","book.epub","epub"},{"pdf","pages.pdf","pdf"},{"long","long.epub","epub"}};
  for(auto &r:roles){paths[r[0]]=fixtures+"/"+r[1];formats[r[0]]=r[2];sizes[r[0]]=read_file(paths[r[0]]).size();if(!shas.count(r[0]))fatal("missing digest");keys[r[0]]=std::string(r[2])+":"+shas[r[0]];}
  parser_version=std::string("exreader-sdk-")+exr_version();
  A.lib_path=work+"/A-library.sqlite";A.product_path=work+"/A-product.sqlite";B.lib_path=work+"/B-library.sqlite";B.product_path=work+"/B-product.sqlite";
  open_side(A);open_side(B);
  for(side *s:{&A,&B}){import(*s,"txt",EXR_TXT,false);import(*s,"epub",EXR_EPUB,true);import(*s,"pdf",EXR_PDF,true);import(*s,"long",EXR_EPUB,true);
    attach(*s,"txt","reflow_global");attach(*s,"epub","epub_chapter");attach(*s,"pdf","fixed_page");attach(*s,"long","epub_chapter");}
  for(const char *role:{"txt","epub","pdf","long"}){
    std::string id=new_id(),wire="{\"version\":1,\"id\":"+esc(id)+",\"entity_kind\":\"book\",\"entity_key\":"+esc(keys[role])+",\"operation\":\"put\",\"location_kind\":\"none\",\"parents\":[],\"payload\":{\"format\":"+esc(formats[role])+",\"source_sha256\":"+esc(shas[role])+",\"source_bytes\":"+num(sizes[role])+",\"title\":"+esc(role)+",\"author\":\"\",\"favorite\":false}}";
    reader_revision_error error{};int created=0;if(reader_revision_local(A.store,wire.data(),wire.size(),nullptr,&created,&error)!=READER_REV_OK)fatal("book seed");
  }
  flush(A,B);
  exr_document *ta=nullptr,*tb=nullptr;SDK(exr_library_document(A.lib,A.ids["txt"],&ta,&e_));SDK(exr_library_document(B.lib,B.ids["txt"],&tb,&e_));
  exr_font *fnt=nullptr;SDK(exr_font_open(font.c_str(),&fnt,&e_));
  exr_publication *pa=nullptr,*pb=nullptr,*la=nullptr,*lb=nullptr;
  for(side *s:{&A,&B})for(const char *role:{"epub","long"}){
    exr_source source{};SDK(exr_library_source(s->lib,s->ids[role],&source,&e_));exr_error e{};
    exr_publication **slot=!std::strcmp(role,"epub")?(s==&A?&pa:&pb):(s==&A?&la:&lb);
    if(exr_publication_open_source(&source,slot,&e)!=EXR_OK){source.release(source.context);fatal("publication open");}
  }
  exr_fixed_open_options fopts{};fopts.struct_size=sizeof(fopts);exr_fixed_document *fa=nullptr,*fb=nullptr;
  SDK(exr_library_fixed(A.lib,A.ids["pdf"],&fopts,&fa,&e_));SDK(exr_library_fixed(B.lib,B.ids["pdf"],&fopts,&fb,&e_));
  /* Preexisting state that search must never change. */
  exr_anchor progress_in{};SDK(exr_anchor_create(ta,6,6,&progress_in,&e_));SDK(exr_library_progress(A.lib,A.ids["txt"],&progress_in,&e_));
  const size_t progress_start=progress_in.start;exr_anchor_free(&progress_in);
  auto notes_total=[&]{size_t n=0;n+=count_notes(A,A.ids["txt"]);for(const char *r:{"epub","long"})n+=count_epub(A,A.ids[r]);n+=count_fixed(A,A.ids["pdf"]);return n;};
  const size_t notes_before=notes_total(),outbox_a=pending(A).size(),outbox_b=pending(B).size();
  std::map<std::string,size_t> heads_before;
  for(const char *r:{"txt","epub","pdf","long"})heads_before[r]=heads(A,"progress",keys[r]).size();

  /* Cached B-side pagers so a hit resolves through an independent SDK instance. */
  exr_layout_config config=exr_layout_config_defaults();exr_chapter_options options=exr_chapter_options_defaults();
  std::map<std::pair<exr_publication *,size_t>,exr_pager *> pagers;
  auto pager_for=[&](exr_publication *p,size_t part){auto key=std::make_pair(p,part);auto it=pagers.find(key);if(it!=pagers.end())return it->second;
    exr_pager *pg=nullptr;SDK(exr_publication_pager_create(p,part,fnt,&config,&options,&pg,&e_));pagers[key]=pg;return pg;};

  /* ===== query validation ===== */
  stage("query validation");
  {
    auto status_of=[&](const std::string &q){reader_search *s=nullptr;reader_search_error e{};reader_search_status st=reader_search_open_reflow(ta,q.data(),q.size(),nullptr,&s,&e);
      expect(st==READER_SEARCH_OK?s!=nullptr:s==nullptr,"open sets the handle only on success");reader_search_close(&s,nullptr);return st;};
    expect(status_of(std::string())==READER_SEARCH_QUERY,"empty query is refused");
    expect(status_of(std::string("ab\0cd",5))==READER_SEARCH_QUERY,"embedded NUL is refused");
    expect(status_of(std::string("\xc0\x80",2))==READER_SEARCH_QUERY,"overlong UTF-8 is refused");
    expect(status_of(std::string("\xed\xa0\x80",3))==READER_SEARCH_QUERY,"UTF-16 surrogate in UTF-8 is refused");
    expect(status_of(std::string("\xf4\x90\x80\x80",4))==READER_SEARCH_QUERY,"value above U+10FFFF is refused");
    expect(status_of(std::string("\xf5\x80\x80\x80",4))==READER_SEARCH_QUERY,"invalid lead byte F5 is refused");
    expect(status_of(std::string("ok\xe4\xb8",4))==READER_SEARCH_QUERY,"truncated sequence is refused");
    expect(status_of(std::string("\x80",1))==READER_SEARCH_QUERY,"stray continuation byte is refused");
    expect(status_of(qstr(4097,'a'))==READER_SEARCH_QUERY,"4097-byte query is refused");
    expect(status_of(qstr(4096,'a'))==READER_SEARCH_OK,"4096-byte query is accepted");
    expect(status_of(std::string("\xf0\x9f\x99\x82",4))==READER_SEARCH_OK,"four-byte scalar query is accepted");
    reader_search *s=nullptr;reader_search_error e{};reader_search_options bad{};bad.struct_size=1;
    expect(reader_search_open_reflow(ta,"a",1,&bad,&s,&e)==READER_SEARCH_ARGUMENT&&!s,"wrong option struct size is refused");
    expect(reader_search_open_reflow(nullptr,"a",1,nullptr,&s,&e)==READER_SEARCH_ARGUMENT&&!s,"missing document is refused");
    expect(reader_search_open_reflow(ta,"a",1,nullptr,nullptr,&e)==READER_SEARCH_ARGUMENT,"missing output is refused");
    reader_search_result r{};
    expect(reader_search_next(nullptr,1,&r,&e)==READER_SEARCH_ARGUMENT,"next without handle is refused");
    expect(reader_search_open_reflow(ta,"a",1,nullptr,&s,&e)==READER_SEARCH_OK,"open for batch limits");
    expect(reader_search_next(s,0,&r,&e)==READER_SEARCH_ARGUMENT&&!r.hits&&!r.count,"batch of 0 is refused with an empty result");
    expect(reader_search_next(s,101,&r,&e)==READER_SEARCH_ARGUMENT,"batch of 101 is refused");
    reader_search_cursor c0{};expect(reader_search_cursor_get(s,&c0,&e)==READER_SEARCH_OK&&c0.offset==0&&!c0.complete,"refused batches do not advance the cursor");
    expect(reader_search_close(&s,&e)==READER_SEARCH_OK&&!s,"close clears the handle");
    expect(reader_search_close(&s,&e)==READER_SEARCH_OK,"closing a NULL handle is harmless");
    expect(reader_search_close(nullptr,&e)==READER_SEARCH_ARGUMENT,"close without a handle pointer is refused");
    reader_search_result_free(&r);reader_search_result_free(&r);reader_search_result_free(nullptr);expect(true,"result free is idempotent on an empty result");
  }

  /* ===== reflow TXT ===== */
  stage("reflow");
  size_t text_bytes=0;const char *text_ptr=exr_document_text(ta,&text_bytes);const std::string text(text_ptr,text_bytes);
  struct reflow_case {const char *id;std::string query;size_t max;};
  const std::vector<reflow_case> reflows={
    {"reflow-chinese","中文",100},{"reflow-emoji","🙂",100},{"reflow-start","开头",100},{"reflow-end","终点",100},
    {"reflow-no-hit","absent-token-xyz",100},{"reflow-duplicate","repeat-phrase",3},{"reflow-overlap","aa",100},
    {"reflow-ambiguous","AMBIGUOUS TARGET",100},{"reflow-250","Z-hit",100},{"reflow-exact-100","E-hit",100},
    {"reflow-single-batches","Z-hit",1},{"reflow-case-sensitive","z-HIT",100},{"reflow-multibyte-tail","🙂🎉",100}};
  std::map<std::string,run> reflow_runs;
  for(const reflow_case &c:reflows){
    tally t;
    run r=collect(reflow_open(ta,c.query),c.max,[&](const reader_search_hit &h){
      reader_rs_capture cap{};cap.mode=READER_RS_REFLOW_GLOBAL;cap.anchor=&h.anchor;
      if(t.found+t.ambiguous+t.other+t.not_ok<40)compat(t,"txt",cap,0,h.start,h.end,[&](const reader_rs_record *rec,exr_anchor_match *m){return reader_rs_resolve_reflow(tb,rec,nullptr,m,nullptr);});});
    auto expected=truth_reflow(ta,c.query);
    expect(r.status==READER_SEARCH_OK&&r.complete&&r.contract,std::string(c.id)+" completes with the batch contract");
    expect(triples(r)==expected,std::string(c.id)+" matches the independent full-text scan");
    bool exact=true,boundary=true,sorted=true;
    for(size_t i=0;i<r.hits.size();i++){
      exact=exact&&r.hits[i].exact==c.query&&text.compare(r.hits[i].start,c.query.size(),c.query)==0;
      boundary=boundary&&(r.hits[i].start==0||((unsigned char)text[r.hits[i].start]&0xc0)!=0x80)&&(r.hits[i].end==text_bytes||((unsigned char)text[r.hits[i].end]&0xc0)!=0x80);
      if(i&&r.hits[i].start<r.hits[i-1].end)sorted=false;
    }
    expect(exact&&boundary&&sorted,std::string(c.id)+" hits are exact, on scalar boundaries and non-overlapping");
    expect(t.not_ok==0&&t.mislocated==0&&t.other==0,std::string(c.id)+" every sampled hit encodes and resolves FOUND or AMBIGUOUS without a wrong range");
    tally_case(c.id,"reflow",c.query,r,t);reflow_runs[c.id]=r;
  }
  expect(reflow_runs["reflow-no-hit"].hits.empty()&&reflow_runs["reflow-no-hit"].batches==std::vector<size_t>{0},"no-hit search ends with one empty complete batch");
  expect(reflow_runs["reflow-start"].hits.size()>=1&&reflow_runs["reflow-start"].hits[0].start==0,"hit at the very start of the text");
  expect(!reflow_runs["reflow-end"].hits.empty()&&reflow_runs["reflow-end"].hits.back().end==text_bytes,"hit at the very end of the text");
  expect(reflow_runs["reflow-250"].batches==(std::vector<size_t>{100,100,50}),"250 hits continue as 100, 100, 50");
  expect(reflow_runs["reflow-exact-100"].batches==(std::vector<size_t>{100,0}),"exactly 100 hits end with a separate empty complete batch");
  expect(reflow_runs["reflow-overlap"].hits.size()>=4,"overlap fixture yields hits");
  {
    const std::string q="aa";const auto &h=reflow_runs["reflow-overlap"].hits;bool disjoint=true;
    for(size_t i=1;i<h.size();i++)disjoint=disjoint&&h[i].start>=h[i-1].end;
    expect(disjoint,"aa over aaaa gives leftmost non-overlapping hits");(void)q;
  }
  expect(reflow_runs["reflow-case-sensitive"].hits.empty(),"search is case-sensitive");
  expect(reflow_runs["reflow-single-batches"].batches.size()==251&&reflow_runs["reflow-single-batches"].hits.size()==250,"batch size 1 walks every hit then ends complete");
  expect(reflow_runs["reflow-ambiguous"].hits.size()==2,"ambiguous fixture has two identical-context hits");
  /* resume from a stored cursor equals continuing */
  {
    run ref=collect(reflow_open(ta,"Z-hit"),100);run resumed=collect(reflow_open(ta,"Z-hit"),100,nullptr,nullptr,&ref.cursors[0]);
    const std::vector<triple> all=triples(ref);std::vector<triple> tail(all.begin()+100,all.end());
    expect(triples(resumed)==tail&&resumed.complete,"a stored cursor resumes at the next hit in a new handle");
    reader_search_cursor wrong=ref.cursors[0];wrong.binding^=1;reader_search *s=nullptr;reader_search_options o{};o.struct_size=sizeof(o);o.resume=&wrong;
    expect(reader_search_open_reflow(ta,"Z-hit",5,&o,&s,nullptr)==READER_SEARCH_ARGUMENT&&!s,"a cursor bound to a different query is refused");
    o.resume=&ref.cursors[0];expect(reader_search_open_reflow(ta,"E-hit",5,&o,&s,nullptr)==READER_SEARCH_ARGUMENT&&!s,"a cursor is not reusable for another query");
    wrong=ref.cursors[0];wrong.mode=READER_SEARCH_EPUB;o.resume=&wrong;
    expect(reader_search_open_reflow(ta,"Z-hit",5,&o,&s,nullptr)==READER_SEARCH_ARGUMENT&&!s,"a cursor of another source mode is refused");
    reader_search_cursor done=ref.cursors.back();o.resume=&done;
    expect(reader_search_open_reflow(ta,"Z-hit",5,&o,&s,nullptr)==READER_SEARCH_OK,"a complete cursor opens");
    reader_search_result res{};expect(reader_search_next(s,10,&res,nullptr)==READER_SEARCH_OK&&res.count==0&&res.complete,"a complete cursor returns an empty complete batch");
    reader_search_result_free(&res);reader_search_close(&s,nullptr);
  }

  /* ===== EPUB with a repeated spine path ===== */
  stage("epub");
  size_t part_count=0;const exr_part *parts=exr_publication_parts(pa,&part_count);
  expect(part_count==3&&!std::strcmp(parts[0].path,parts[2].path),"fixture keeps a repeated spine path");
  struct epub_case {const char *id;std::string query;size_t max;};
  const std::vector<epub_case> epubs={
    {"epub-token","SEARCHTOKEN",100},{"epub-token-single","SEARCHTOKEN",1},{"epub-chinese","第二章节",100},{"epub-emoji","🙂",100},
    {"epub-repeated-spine","Repeated spine",100},{"epub-no-hit","absent-token-xyz",100},{"epub-cross-chapter","alpha-to-beta",100}};
  std::map<std::string,run> epub_runs;
  for(const epub_case &c:epubs){
    tally t;
    run r=collect(epub_open(pa,fnt,c.query),c.max,[&](const reader_search_hit &h){
      reader_rs_capture cap{};cap.mode=READER_RS_EPUB_CHAPTER;cap.anchor=&h.anchor;cap.part_path=h.part_path;
      compat(t,"epub",cap,(size_t)h.unit,h.start,h.end,[&](const reader_rs_record *rec,exr_anchor_match *m){
        size_t routed=SIZE_MAX;if(reader_rs_epub_record_part(pb,rec,&routed,nullptr)!=READER_RS_OK||routed!=h.unit)return READER_RS_IDENTITY;
        return reader_rs_resolve_epub(pb,pager_for(pb,routed),routed,rec,nullptr,m,nullptr);});});
    auto expected=truth_epub(pa,c.query);
    expect(r.status==READER_SEARCH_OK&&r.complete&&r.contract,std::string(c.id)+" completes with the batch contract");
    expect(triples(r)==expected,std::string(c.id)+" matches the independent per-chapter scan");
    bool route=true;for(const rec &h:r.hits)route=route&&h.path==parts[h.unit].path&&h.exact==c.query;
    expect(route,std::string(c.id)+" keeps the spine index, verbatim part path and exact quote");
    expect(t.not_ok==0&&t.mislocated==0&&t.other==0,std::string(c.id)+" every hit encodes and resolves FOUND or AMBIGUOUS without a wrong range");
    tally_case(c.id,"epub",c.query,r,t);epub_runs[c.id]=r;
  }
  {
    const run &r=epub_runs["epub-token"];std::set<uint64_t> units;for(const rec &h:r.hits)units.insert(h.unit);
    expect(units.count(0)&&units.count(1)&&units.count(2),"hits come from the repeated chapter at both spine indices and from another chapter");
    expect(triples(epub_runs["epub-token-single"])==triples(r)&&epub_runs["epub-token-single"].batches.size()==r.hits.size()+1,
           "batch size 1 crosses chapters through cursors and ends complete");
    expect(epub_runs["epub-cross-chapter"].hits.empty(),"a quote split across two chapters is never a hit");
    expect(epub_runs["epub-repeated-spine"].hits.size()==2&&epub_runs["epub-repeated-spine"].hits[0].path==epub_runs["epub-repeated-spine"].hits[1].path&&
           epub_runs["epub-repeated-spine"].hits[0].unit!=epub_runs["epub-repeated-spine"].hits[1].unit,
           "a repeated spine path yields one hit per spine index with the same verbatim path");
  }

  /* ===== long EPUB chapter: block-straddling hits and raw measurements ===== */
  stage("long chapter");
  {
    std::string needle;for(int i=0;i<33;i++)needle+="NEEDLE-ALPHA-BETA-GAMMA-";
    const unsigned long long rss0=search_probe_peak_memory();
    block_sink bs;exr_chapter_stats base{};
    {
      exr_pager *pg=nullptr;SDK(exr_publication_pager_create(la,0,fnt,&config,&options,&pg,&e_));
      exr_chapter_stats st=exr_pager_chapter_statistics(pg);
      SDK(exr_pager_read_text(pg,0,st.projection_bytes,block_fn,&bs,nullptr,&e_));
      base=exr_pager_chapter_statistics(pg);exr_pager_free(pg);
    }
    const unsigned long long rss1=search_probe_peak_memory();
    auto t0=std::chrono::steady_clock::now();
    run timed=collect(epub_open(la,fnt,needle),100);
    const double ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-t0).count();
    const unsigned long long rss2=search_probe_peak_memory();
    const auto expected=truth_epub(la,needle);
    expect(timed.status==READER_SEARCH_OK&&timed.complete&&timed.contract,"long chapter search completes with the batch contract");
    expect(triples(timed)==expected,"long chapter hits equal the independent full-chapter scan");
    size_t straddle=0;for(const triple &t:expected)for(size_t b:bs.boundaries)if(std::get<1>(t)<b&&b<std::get<2>(t))straddle++;
    expect(straddle>=1&&bs.chunks>=20,"long chapter has hits that straddle observed 32 KiB stream block boundaries",
           "straddle="+num(straddle)+" chunks="+num(bs.chunks));
    expect(timed.stats.bytes_scanned==base.projection_bytes,"every chapter byte is scanned exactly once across batches",
           "scanned="+num(timed.stats.bytes_scanned)+" projection="+num(base.projection_bytes));
    expect(timed.batches.size()>=2&&timed.batches[0]==100,"long chapter continues across 100-hit batches");
    size_t sampled=0;tally lt;
    run verified=collect(epub_open(la,fnt,needle),100,[&](const reader_search_hit &h){
      if((sampled++%50)!=0)return;
      reader_rs_capture cap{};cap.mode=READER_RS_EPUB_CHAPTER;cap.anchor=&h.anchor;cap.part_path=h.part_path;
      compat(lt,"long",cap,(size_t)h.unit,h.start,h.end,[&](const reader_rs_record *rec,exr_anchor_match *m){
        return reader_rs_resolve_epub(lb,pager_for(lb,0),0,rec,nullptr,m,nullptr);});});
    expect(lt.not_ok==0&&lt.mislocated==0&&lt.found>=1,"sampled long-chapter hits resolve FOUND on the independent instance");
    tally_case("epub-long-needle","epub",needle,verified,lt);
    measurements.push_back(object().str("id","epub-long-chapter").set("source_bytes",num(sizes["long"])).set("projection_bytes",num(base.projection_bytes))
      .set("hits",num(timed.hits.size())).set("batches",num(timed.batches.size())).set("stream_chunks",num(bs.chunks)).set("straddling_hits",num(straddle))
      .set("peak_rss_before",num(rss0)).set("peak_rss_after_sdk_stream_only",num(rss1)).set("peak_rss_after_search",num(rss2))
      .set("sdk_peak_parse_workspace_bytes",num(base.peak_parse_workspace_bytes)).set("sdk_windows_loaded",num(base.windows_loaded))
      .set("sdk_windows_evicted",num(base.windows_evicted)).set("module_bytes_scanned",num(timed.stats.bytes_scanned))
      .set("module_units_scanned",num(timed.stats.units_scanned)).set("module_peak_accounted_bytes",num(timed.stats.peak_module_bytes))
      .set("module_seen_sdk_peak_parse_workspace_bytes",num(timed.stats.sdk_peak_parse_workspace_bytes)).set("elapsed_ms",std::to_string(ms))
      .str("note","single observation; not a performance claim; peak RSS is a process-wide monotone high-water mark").dump());
  }

  /* ===== fixed pages: real PDF and generated documents ===== */
  stage("fixed");
  size_t pdf_pages=0;const exr_fixed_page *pdf_list=exr_fixed_pages(fa,&pdf_pages);
  expect(pdf_pages==4,"PDF fixture has four pages including an empty one");
  struct fixed_case {const char *id;std::string query;size_t max;};
  const std::vector<fixed_case> pdfs={
    {"pdf-shared-quote","Shared quote across pages.",100},{"pdf-ambiguous","selection target",100},{"pdf-line","Second distinct line",100},
    {"pdf-no-hit","absent-token-xyz",100},{"pdf-page-word","page",1},{"pdf-fixed-page","Fixed page",100}};
  std::map<std::string,run> fixed_runs;
  for(const fixed_case &c:pdfs){
    tally t;
    run r=collect(fixed_open(fa,c.query),c.max,[&](const reader_search_hit &h){
      reader_rs_capture cap{};cap.mode=READER_RS_FIXED_PAGE;cap.fixed=&h.fixed;cap.page=(size_t)h.unit;
      compat(t,"pdf",cap,0,h.start,h.end,[&](const reader_rs_record *rec,exr_anchor_match *m){size_t resolved=SIZE_MAX;return reader_rs_resolve_fixed(fb,rec,nullptr,&resolved,m,nullptr);});});
    expect(r.status==READER_SEARCH_OK&&r.complete&&r.contract,std::string(c.id)+" completes with the batch contract");
    expect(triples(r)==truth_fixed(fa,c.query),std::string(c.id)+" matches the independent per-page scan");
    bool route=true;for(const rec &h:r.hits)route=route&&h.page_id==pdf_list[h.unit].id&&h.exact==c.query;
    expect(route,std::string(c.id)+" keeps the exact page ID, page hint and quote");
    expect(t.not_ok==0&&t.mislocated==0&&t.other==0,std::string(c.id)+" every hit encodes and resolves FOUND or AMBIGUOUS without a wrong range");
    tally_case(c.id,"fixed",c.query,r,t);fixed_runs[c.id]=r;
  }
  expect(fixed_runs["pdf-shared-quote"].hits.size()==2&&fixed_runs["pdf-shared-quote"].hits[0].unit==0&&fixed_runs["pdf-shared-quote"].hits[1].unit==3,
         "multi-page PDF hits keep distinct pages around an empty page");
  expect(fixed_runs["pdf-ambiguous"].hits.size()>=3,"repeated identical lines give one hit each");
  expect(fixed_runs["pdf-page-word"].batches.size()==fixed_runs["pdf-page-word"].hits.size()+1,"PDF batch size 1 crosses pages and ends complete");
  expect(fixed_runs["pdf-no-hit"].hits.empty(),"empty page and absent query produce no hit");
  {
    fx f;
    f.pages={"你好🙂世界🙂","","aaaa","abc"};
    for(int p=0;p<3;p++){std::string page;for(int i=0;i<60;i++)page+="Z-hit "+std::to_string(i)+" ";f.pages.push_back(page);}
    f.pages.push_back("尾🙂");fx_build(f);
    struct gen {const char *id;std::string query;size_t max;};
    const std::vector<gen> gens={{"gen-emoji","🙂",100},{"gen-chinese-start","你好",100},{"gen-chinese-end","世界🙂",100},{"gen-overlap","aa",100},
      {"gen-no-hit","absent-token-xyz",100},{"gen-last-page-end","尾🙂",100},{"gen-180","Z-hit",100}};
    for(const gen &c:gens){
      run r=collect(fixed_open(f.doc,c.query),c.max);
      expect(r.status==READER_SEARCH_OK&&r.complete&&r.contract,std::string(c.id)+" completes with the batch contract");
      expect(triples(r)==truth_fixed(f.doc,c.query),std::string(c.id)+" matches the independent per-page scan");
      bool ok=true;for(const rec &h:r.hits){const std::string &page=f.pages[h.unit];ok=ok&&h.exact==c.query&&h.page_id==f.ids[h.unit]&&
        (h.start==0||((unsigned char)page[h.start]&0xc0)!=0x80)&&(h.end==page.size()||((unsigned char)page[h.end]&0xc0)!=0x80);}
      expect(ok,std::string(c.id)+" hits stay on scalar boundaries with the generated page ID");
      tally none;tally_case(c.id,"fixed",c.query,r,none);
      if(std::string(c.id)=="gen-180")expect(r.hits.size()==180&&r.batches==(std::vector<size_t>{100,80}),"180 fixed hits continue mid-page across 100 then 80");
      if(std::string(c.id)=="gen-overlap")expect(r.hits.size()==2&&r.hits[0].end==2&&r.hits[1].start==2,"aa over aaaa on a page gives two adjacent non-overlapping hits");
      if(std::string(c.id)=="gen-emoji")expect(r.hits.size()==3,"emoji hits on three pages");
    }
    /* Only one page text is alive at a time and the cursor resumes mid-page. */
    f.loads=0;run once=collect(fixed_open(f.doc,"Z-hit"),100);
    expect(f.loads>=f.pages.size()&&f.loads<=f.pages.size()+2,"each page text is loaded about once per search",num(f.loads));

    /* ----- SDK error: failed batch is not a result and keeps the previous cursor ----- */
    fx g;g.pages={"Z-hit one","Z-hit two","Z-hit three","Z-hit four"};g.fail_page=2;fx_build(g);
    fx healthy;healthy.pages=g.pages;fx_build(healthy);run ref=collect(fixed_open(healthy.doc,"Z-hit"),2);
    reader_search *s=nullptr;reader_search_options o{};o.struct_size=sizeof(o);reader_search_error er{};
    expect(reader_search_open_fixed(g.doc,"Z-hit",5,&o,&s,&er)==READER_SEARCH_OK,"open before an injected failure");
    reader_search_result r1{},r2{};reader_search_cursor c1{},c2{};
    expect(reader_search_next(s,2,&r1,&er)==READER_SEARCH_OK&&r1.count==2,"first batch before the failing page succeeds");
    reader_search_cursor_get(s,&c1,nullptr);
    reader_search_status st=reader_search_next(s,2,&r2,&er);
    expect(st==READER_SEARCH_SDK&&er.sdk_code==(int)EXR_IO&&!r2.hits&&r2.count==0&&!r2.complete,"a failing provider returns an SDK error and an empty result");
    reader_search_cursor_get(s,&c2,nullptr);
    expect(same_cursor(c1,c2)&&c1.unit==1,"the failed batch leaves the previous successful cursor");
    g.fail_page=-1;reader_search_result r3{};
    expect(reader_search_next(s,2,&r3,&er)==READER_SEARCH_OK&&r3.count==2&&r3.hits[0].unit==2&&r3.hits[1].unit==3,"retry after the provider recovers returns the same next batch");
    reader_search_stats stats{};reader_search_stats_get(s,&stats,nullptr);
    expect(stats.failed_calls==1&&stats.calls==3,"statistics count the failed call");
    reader_search_result_free(&r1);reader_search_result_free(&r2);reader_search_result_free(&r3);reader_search_close(&s,nullptr);
    expect(ref.hits.size()==4,"healthy twin provides the reference");
    exr_fixed_free(g.doc);exr_fixed_free(healthy.doc);
    /* a document without a text provider is an SDK error, not an empty book */
    {
      exr_fixed_page p{};p.id="only";p.geometry.bounds[2]=10;p.geometry.bounds[3]=10;p.geometry.unit_scale=1;
      exr_fixed_input in{};in.struct_size=sizeof(in);in.title="none";in.pages=&p;in.page_count=1;in.draw=fx_draw;exr_fixed_document *plain=nullptr;SDK(exr_fixed_create(&in,&plain,&e_));
      run r=collect(fixed_open(plain,"a"),10);expect(r.status==READER_SEARCH_SDK,"fixed document without text is an SDK error rather than an empty result");exr_fixed_free(plain);
    }

    /* ----- cancellation sweeps: every poll point, cursor kept, retry identical ----- */
    auto equal_tail=[&](const reader_search_result &res,const run &reference,size_t from){
      if(res.count+from>reference.hits.size())return false;
      for(size_t i=0;i<res.count;i++){const rec &x=reference.hits[from+i];if(res.hits[i].unit!=x.unit||res.hits[i].start!=x.start||res.hits[i].end!=x.end)return false;}
      return true;};
    auto sweep=[&](const std::string &id,const opener &open,size_t max){
      run reference=collect(open,max,nullptr,nullptr,nullptr,2);
      if(reference.batches.size()<2||reference.batches[0]!=max)fatal(id+" sweep needs two full batches");
      int cancelled=0;bool finished=false,ok=true;
      for(int k=0;k<2000&&!finished;k++){
        trip t;exr_control ctl{trip_fn,nullptr,&t};reader_search_options so{};so.struct_size=sizeof(so);so.control=ctl;
        reader_search *h=nullptr;reader_search_error e{};if(open(&so,&h,&e)!=READER_SEARCH_OK)fatal(id+" sweep open");
        reader_search_result a{},b{},again{};reader_search_cursor before{},after{};
        if(reader_search_next(h,max,&a,&e)!=READER_SEARCH_OK||!equal_tail(a,reference,0))ok=false;
        reader_search_cursor_get(h,&before,nullptr);t.calls=0;t.at=k;
        reader_search_status s2=reader_search_next(h,max,&b,&e);
        if(s2==READER_SEARCH_CANCELLED){
          cancelled++;reader_search_cursor_get(h,&after,nullptr);
          if(b.hits||b.count||!same_cursor(before,after))ok=false;
          t.at=-1;if(reader_search_next(h,max,&again,&e)!=READER_SEARCH_OK||!equal_tail(again,reference,max)||again.count!=reference.batches[1])ok=false;
        }else if(s2==READER_SEARCH_OK){finished=true;if(!equal_tail(b,reference,max)||b.count!=reference.batches[1])ok=false;}
        else ok=false;
        reader_search_result_free(&a);reader_search_result_free(&b);reader_search_result_free(&again);reader_search_close(&h,nullptr);
        if(!ok)break;
      }
      expect(ok&&cancelled>0&&finished,id+" cancellation at every poll point keeps the cursor and the retry returns the identical batch","cancelled="+num(cancelled));
    };
    sweep("cancel-reflow",reflow_open(ta,"Z-hit"),5);
    sweep("cancel-epub",epub_open(pa,fnt,"SEARCHTOKEN"),2);
    sweep("cancel-fixed",fixed_open(f.doc,"Z-hit"),70);

    /* ----- reentry through the control callback is refused with BUSY ----- */
    auto reentry=[&](const std::string &id,const opener &open,size_t max){
      reenter r;exr_control ctl{reenter_fn,nullptr,&r};reader_search_options ro{};ro.struct_size=sizeof(ro);ro.control=ctl;
      reader_search *h=nullptr;if(open(&ro,&h,nullptr)!=READER_SEARCH_OK)fatal(id+" open");r.s=h;
      reader_search_result res{};reader_search_status st=reader_search_next(h,max,&res,nullptr);
      bool busy=!r.seen.empty()&&r.seen.size()%4==0;for(reader_search_status v:r.seen)busy=busy&&v==READER_SEARCH_BUSY;
      r.s=nullptr;reader_search_cursor c{};
      expect(st==READER_SEARCH_OK&&res.count==max&&busy,id+" reentrant next/cursor/stats/close return BUSY and the outer call succeeds","seen="+num(r.seen.size()));
      expect(reader_search_cursor_get(h,&c,nullptr)==READER_SEARCH_OK&&c.offset>0,id+" handle is intact after refused reentry");
      reader_search_result_free(&res);reader_search_close(&h,nullptr);
    };
    reentry("reentry-reflow",reflow_open(ta,"Z-hit"),4);
    reentry("reentry-epub",epub_open(pa,fnt,"SEARCHTOKEN"),2);
    reentry("reentry-fixed",fixed_open(f.doc,"Z-hit"),4);
    exr_fixed_free(f.doc);
  }

  /* ===== search leaves the source, notes, progress and product history unchanged ===== */
  stage("immutability");
  {
    for(const char *role:{"txt","epub","pdf","long"}){
      void *blob=nullptr;size_t size=0;SDK(exr_library_blob(A.lib,A.ids[role],0,&blob,&size,&e_));const std::string original=read_file(paths[role]);
      expect(size==original.size()&&!std::memcmp(blob,original.data(),size),std::string("source bytes of ")+role+" are unchanged");exr_free(blob);
    }
    exr_anchor progress{};exr_anchor_state state{};SDK(exr_library_progress_get(A.lib,A.ids["txt"],&progress,&state,&e_));
    expect(progress.start==progress_start,"current reading progress is unchanged");exr_anchor_free(&progress);
    expect(notes_total()==notes_before,"no SDK note was created");
    expect(pending(A).size()==outbox_a&&pending(B).size()==outbox_b,"no product revision was inserted or queued");
    bool same=true;for(const char *r:{"txt","epub","pdf","long"})same=same&&heads(A,"progress",keys[r]).size()==heads_before[r];
    expect(same,"product progress heads are unchanged");
    /* A hit's capture is byte-identical to the plain public capture, so old v1/v2 encoders see nothing new. */
    run first=collect(reflow_open(ta,"中文"),1,nullptr,nullptr,nullptr,1);expect(first.hits.size()==1,"reference hit for encoder comparison");
    exr_anchor plain{};SDK(exr_anchor_create(ta,first.hits[0].start,first.hits[0].end,&plain,&e_));
    exr_anchor viaSearch{};
    run keep=collect(reflow_open(ta,"中文"),1,[&](const reader_search_hit &h){
      viaSearch.start=h.anchor.start;viaSearch.end=h.anchor.end;
      reader_rs_capture a{};a.mode=READER_RS_REFLOW_GLOBAL;a.anchor=&h.anchor;reader_rs_capture b{};b.mode=READER_RS_REFLOW_GLOBAL;b.anchor=&plain;
      for(int version=1;version<=2;version++){
        std::string id=new_id(),aid=new_id();reader_rs_envelope env{};env.revision_id=id.c_str();env.operation="put";env.entity_kind="annotation";env.book_key=keys["txt"].c_str();
        env.annotation_id=aid.c_str();env.note_text="n";env.parser_version=parser_version.c_str();char *w1=nullptr,*w2=nullptr;size_t n1=0,n2=0;
        reader_rs_status s1=version==1?reader_rs_encode(A.store,&env,&a,&w1,&n1,nullptr):reader_rs_encode_v2(A.store,&env,&a,0,&w1,&n1,nullptr);
        reader_rs_status s2=version==1?reader_rs_encode(A.store,&env,&b,&w2,&n2,nullptr):reader_rs_encode_v2(A.store,&env,&b,0,&w2,&n2,nullptr);
        expect(s1==s2&&n1==n2&&(!w1||!std::memcmp(w1,w2,n1)),std::string("wire v")+num(version)+" bytes of a search hit equal the plain SDK capture");
        reader_rs_free(w1);reader_rs_free(w2);}
    },nullptr,nullptr,1);
    exr_anchor_free(&plain);(void)keep;
  }

  for(auto &entry:pagers)exr_pager_free(entry.second);
  exr_fixed_free(fa);exr_fixed_free(fb);exr_publication_free(pa);exr_publication_free(pb);exr_publication_free(la);exr_publication_free(lb);
  exr_document_free(ta);exr_document_free(tb);exr_font_free(fnt);close_side(A);close_side(B);
  object report;report.set("cases",array(cases_out)).set("checks",array(checks)).set("measurements",array(measurements)).set("failures",num(failures));
  std::ofstream output(report_path,std::ios::binary);output<<report.dump()<<"\n";return failures?1:0;
}
