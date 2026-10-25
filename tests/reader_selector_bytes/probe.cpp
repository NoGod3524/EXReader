/* SPDX-License-Identifier: MIT */
#include <reader_reading_commands.h>
#include <reader_annotation_view.h>
#include <reader_projection.h>
#include <exreader.h>
#include <sqlite3.h>
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
extern "C" int selector_bytes_c_api(void);
namespace fs=std::filesystem;
static const std::string book="pdf:5627a430fa04cbe11d38eb2682e336ef21e147d445753ed46ed11a7d5e3167cc";
static const std::string bookmark(32,'b'),highlight(32,'c');
static unsigned sequence=100;
static void check(bool pass,const std::string &name){if(!pass)throw std::runtime_error(name);std::cout<<"PASS "<<name<<std::endl;}
static void check(bool pass,const char *name){check(pass,std::string(name));}
static std::string id(){char buffer[33];std::snprintf(buffer,sizeof(buffer),"%032x",sequence++);return buffer;}
static std::string read(const fs::path &p){std::ifstream f(p,std::ios::binary);if(!f)throw std::runtime_error("read "+p.u8string());std::ostringstream s;s<<f.rdbuf();return s.str();}
static void write(const fs::path &p,const std::string &s){std::ofstream f(p,std::ios::binary);f.write(s.data(),(std::streamsize)s.size());if(!f)throw std::runtime_error("write "+p.u8string());}
struct fixed {
  std::string original;exr_fixed_document *doc=nullptr;exr_fixed_text *text=nullptr;exr_fixed_anchor point{},range{};
  explicit fixed(const fs::path &path):original(read(path)){
    exr_error e{};check(original.size()==8845,"same real PDF size");
    check(exr_fixed_open_memory(EXR_PDF,original.data(),original.size(),nullptr,&doc,&e)==EXR_OK,e.message);
    size_t count=0;const auto *pages=exr_fixed_pages(doc,&count);check(count>0&&!std::strcmp(pages[0].id,"page-1"),"same page-1 route");
    check(exr_fixed_load_text(doc,0,nullptr,&text,&e)==EXR_OK,e.message);size_t n=0;const char *p=exr_fixed_text_string(text,&n);
    check(n>0&&std::memchr(p,0,n),"actual PDF public text contains NUL");
    check(exr_fixed_anchor_create("page-1",text,0,0,&point,&e)==EXR_OK,e.message);
    check(point.start==0&&point.end==0&&std::memchr(point.suffix,0,point.suffix_size),"actual zero point suffix contains NUL");
    check(exr_fixed_anchor_create("page-1",text,0,n,&range,&e)==EXR_OK,e.message);
    check(range.exact_size>0&&std::memchr(range.exact,0,range.exact_size),"actual nonempty range exact contains NUL");
  }
  ~fixed(){exr_fixed_anchor_free(&point);exr_fixed_anchor_free(&range);exr_fixed_text_free(text);exr_fixed_free(doc);}
};
static reader_rs_capture capture(const exr_fixed_anchor &a){reader_rs_capture c{};c.mode=READER_RS_FIXED_PAGE;c.fixed=&a;return c;}
static bool same(const char *a,size_t an,const char *b,size_t bn){return (!a)==(!b)&&an==bn&&(!an||!std::memcmp(a,b,an));}
static void original_v2(fixed &pdf,const fs::path &folder){
  reader_revisions *store=nullptr;reader_revision_error re{};check(reader_revisions_open((folder/"legacy.sqlite").u8string().c_str(),&store,&re)==READER_REV_OK,re.message);
  reader_rs_envelope e{};e.revision_id="00000000000000000000000000000001";e.operation="put";e.entity_kind="progress";e.book_key=book.c_str();e.parser_version=exr_version();
  auto c=capture(pdf.point);char *wire=nullptr;size_t n=0;reader_rs_error error{};
  check(reader_rs_encode_v2(store,&e,&c,0,&wire,&n,&error)==READER_RS_NOT_REPRESENTABLE&&error.gap==READER_RS_GAP_NUL&&!wire&&!n,"old v2 actual PDF GAP_NUL unchanged");
  /* Deterministic public-SDK TXT captures compare old v1/v2 wire byte-for-byte. */
  std::string text="A real public SDK text capture has enough context for stable matching.";exr_document *document=nullptr;exr_error se{};
  check(exr_document_open_memory(EXR_TXT,text.data(),text.size(),&document,&se)==EXR_OK,se.message);
  exr_anchor a{};check(exr_anchor_create(document,2,6,&a,&se)==EXR_OK,se.message);reader_rs_capture tc{};tc.mode=READER_RS_REFLOW_GLOBAL;tc.anchor=&a;
  const char *sha=std::getenv("SELECTOR_TXT_SHA");check(sha&&std::strlen(sha)==64,"actual compatibility TXT identity supplied");
  std::string txt="txt:"+std::string(sha);e.entity_kind="annotation";e.annotation_id=bookmark.c_str();e.book_key=txt.c_str();e.note_text="kept";
  check(reader_rs_encode(store,&e,&tc,&wire,&n,&error)==READER_RS_OK,error.message);write(folder/"v1-wire.json",std::string(wire,n));reader_rs_free(wire);
  check(reader_rs_encode_v2(store,&e,&tc,0,&wire,&n,&error)==READER_RS_OK,error.message);write(folder/"v2-wire.json",std::string(wire,n));reader_rs_free(wire);
  exr_anchor_free(&a);exr_document_free(document);reader_revisions_close(&store,&re);
}
static void legacy_refuse(const fs::path &input,const fs::path &work){
  reader_revisions *store=nullptr;reader_revision_error e{};check(reader_revisions_open((work/"old-receive.sqlite").u8string().c_str(),&store,&e)==READER_REV_OK,e.message);auto body=read(input);reader_revision_info info{};
  check(reader_revision_validate(store,body.data(),body.size(),nullptr,&info,&e)==READER_REV_FORMAT,"actual legacy entry rejects anchor3");reader_rs_record r{};reader_rs_error error{};check(reader_rs_decode(store,body.data(),body.size(),&r,&error)!=READER_RS_OK&&!r.has_location&&!r.exact,"old decoder never mistakes anchor3 for v2");reader_revisions_close(&store,&e);
}
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
struct history {
  reader_revisions *store=nullptr;
  explicit history(const fs::path &p){reader_revision_error e{};check(reader_revisions_open_raw_v3(p.u8string().c_str(),&store,&e)==READER_REV_OK,e.message);}
  ~history(){reader_revision_error e{};reader_revisions_close(&store,&e);}
};
struct record {
  reader_rs_record r{};~record(){reader_rs_record_free(&r);}
};
static std::vector<std::string> heads(history &h,const std::string &entity,const std::string &key){
  std::vector<std::string> result;reader_revision_state state{};reader_revision_error e{};
  check(reader_revision_heads_raw_v3(h.store,entity.c_str(),key.c_str(),[](void *p,const reader_revision_head *row){static_cast<std::vector<std::string> *>(p)->emplace_back(row->revision_id);return 0;},&result,&state,&e)==READER_REV_OK,e.message);return result;
}
static std::string retained(history &h,const std::string &rid){char *p=nullptr;size_t n=0;reader_revision_info i{};reader_revision_error e{};check(reader_revision_get_raw_v3(h.store,rid.c_str(),&p,&n,&i,&e)==READER_REV_OK,e.message);std::string s(p,n);reader_revision_bytes_free(p);return s;}
static std::string selected(history &h,const char *kind,const std::string &key,reader_revision_status expected=READER_REV_OK){
  char *p=nullptr;size_t n=0;reader_revision_info i{};reader_revision_selection state{};reader_revision_error e{};
  auto st=reader_revision_selected_raw_v3(h.store,kind,key.c_str(),&p,&n,&i,&state,&e);check(st==expected,"selected status "+std::to_string(expected));
  if(st!=READER_REV_OK){check(!p&&!n&&state.kind==READER_SELECTION_PENDING_PARENTS,"missing parent hides capture");return {};}
  std::string s(p,n);reader_revision_bytes_free(p);return s;
}
static std::string apply(history &h,reader_rc_kind kind,const reader_rs_capture *cap,const std::string &aid="",reader_rc_operation op=READER_RC_PUT,const char *body=""){
  std::string rid=id(),key=kind==READER_RC_PROGRESS?book:book+":"+aid;auto old=heads(h,kind==READER_RC_PROGRESS?"progress":"annotation",key);std::vector<const char *> pointers;for(auto &x:old)pointers.push_back(x.c_str());
  reader_rc_context ctx{};ctx.store=h.store;ctx.revision_id=rid.c_str();ctx.parser_version=exr_version();ctx.expected_heads=pointers.data();ctx.expected_count=pointers.size();
  reader_rc_command cmd{};cmd.kind=kind;cmd.operation=op;cmd.book_key=book.c_str();cmd.annotation_id=aid.c_str();cmd.capture=cap;cmd.text=kind==READER_RC_PROGRESS||op==READER_RC_DELETE?nullptr:body;
  std::string prior;if(kind==READER_RC_NOTE_TEXT)prior=selected(h,"annotation",key);
  reader_rc_result r{};reader_rc_error e{};auto st=reader_rc_apply_fixed_v3(&ctx,&cmd,&r,&e);check(st==READER_RC_OK,std::string("actual command ")+e.message);check(r.created==1,"new revision committed");
  std::string wire=retained(h,rid);check(reader_rc_apply_fixed_v3(&ctx,&cmd,&r,&e)==READER_RC_OK&&!r.created,"stable retry exact no-op");check(retained(h,rid)==wire,"retry kept exact raw wire");
  record fresh;reader_rs_error decode_error{};check(reader_rs_decode_raw_v3(h.store,wire.data(),wire.size(),&fresh.r,&decode_error)==READER_RS_OK,decode_error.message);
  if(op==READER_RC_DELETE)check(!fresh.r.has_location&&!fresh.r.exact,"delete has no invented selector");
  else if(kind==READER_RC_NOTE_TEXT){
    record before;check(reader_rs_decode_raw_v3(h.store,prior.data(),prior.size(),&before.r,&decode_error)==READER_RS_OK,decode_error.message);
    check(fresh.r.anchor_version==before.r.anchor_version&&fresh.r.start==before.r.start&&fresh.r.end==before.r.end&&same(fresh.r.exact,fresh.r.exact_size,before.r.exact,before.r.exact_size)&&same(fresh.r.prefix,fresh.r.prefix_size,before.r.prefix,before.r.prefix_size)&&same(fresh.r.suffix,fresh.r.suffix_size,before.r.suffix,before.r.suffix_size),"NOTE_TEXT retains actual version bytes and NULL tags");
  }else{
    auto &actual=*cap->fixed;check(fresh.r.anchor_version==3&&fresh.r.start==actual.start&&fresh.r.end==actual.end&&same(fresh.r.exact,fresh.r.exact_size,actual.exact,actual.exact_size)&&same(fresh.r.prefix,fresh.r.prefix_size,actual.prefix,actual.prefix_size)&&same(fresh.r.suffix,fresh.r.suffix_size,actual.suffix,actual.suffix_size),"command wireCapture equals actual SDK nullable bytes");
  }
  return wire;
}
static std::vector<std::string> pending(history &h){std::vector<std::string> out;reader_revision_error e{};check(reader_revision_outbox_raw_v3(h.store,100,[](void *p,const reader_revision_outbox_row *r){static_cast<std::vector<std::string> *>(p)->emplace_back(r->wire,r->info.bytes);return 0;},&out,&e)==READER_REV_OK,e.message);return out;}
static void decode(history &h,const std::string &wire,record &r){reader_rs_error e{};check(reader_rs_decode_raw_v3(h.store,wire.data(),wire.size(),&r.r,&e)==READER_RS_OK,e.message);}
static void view(history &h,bool pending_parent){
  reader_av_view *v=nullptr;reader_av_error e{};check(reader_av_open_raw_v3(h.store,book.c_str(),nullptr,&v,&e)==READER_AV_OK,e.message);reader_av_cursor from{};reader_av_cursor_start(v,1,&from,&e);reader_av_page p{};
  check(reader_av_page_get(v,&from,100,&p,&e)==READER_AV_ARGUMENT&&!p.items,"legacy view entry refuses raw view");
  check(reader_av_page_get_raw_v3(v,&from,100,&p,&e)==READER_AV_OK,e.message);check(p.count>0,"typed view has real annotations");
  for(size_t k=0;k<p.count;k++){auto &r=p.items[k];if(pending_parent)check(r.state==READER_AV_STATE_PENDING_PARENTS&&!r.exact&&!r.content_available,"typed pending has no selector");else check(r.state==READER_AV_STATE_SAFE&&r.anchor_version==3&&r.content_available,"typed SAFE anchor3");}
  reader_av_page_free(&p);reader_av_close(&v,&e);
}
static void receive(history &h,const std::string &wire){reader_revision_info i{};reader_revision_error e{};int created=0;
  check(reader_revision_validate_raw_v3(h.store,wire.data(),wire.size(),nullptr,&i,&e)==READER_REV_OK,e.message);
  std::string expected=i.sha256;
  check(reader_revision_receive_raw_v3(h.store,wire.data(),wire.size(),expected.c_str(),&i,&created,&e)==READER_REV_OK,e.message);
}
static void resolve(history &h,fixed &pdf,const std::string &wire){
  record r;decode(h,wire,r);exr_anchor_match match{};size_t page=SIZE_MAX;reader_rs_error e{};
  check(reader_rs_resolve_fixed(pdf.doc,&r.r,nullptr,&page,&match,&e)==READER_RS_ARGUMENT,"legacy resolve refuses anchor3");
  check(reader_rs_resolve_fixed_v3(pdf.doc,&r.r,nullptr,&page,&match,&e)==READER_RS_OK&&match.state==EXR_ANCHOR_FOUND&&page==0,e.message);
  exr_fixed_anchor actual{};exr_error se{};check(exr_fixed_anchor_create("page-1",pdf.text,match.start,match.end,&actual,&se)==EXR_OK,se.message);
  check(actual.start==r.r.start&&actual.end==r.r.end&&same(actual.exact,actual.exact_size,r.r.exact,r.r.exact_size)&&same(actual.prefix,actual.prefix_size,r.r.prefix,r.r.prefix_size)&&same(actual.suffix,actual.suffix_size,r.r.suffix,r.r.suffix_size),"actual recapture exact nullable bytes");exr_fixed_anchor_free(&actual);
  exr_control cancelled{};cancelled.cancelled=[](void *){return 1;};match.state=EXR_ANCHOR_FOUND;
  check(reader_rs_resolve_fixed_v3(pdf.doc,&r.r,&cancelled,&page,&match,&e)!=READER_RS_OK&&match.state!=EXR_ANCHOR_FOUND,"cancelled raw resolution never grants FOUND");
  auto correct=r.r.page;r.r.page=99;check(reader_rs_resolve_fixed_v3(pdf.doc,&r.r,nullptr,&page,&match,&e)==READER_RS_IDENTITY,"wrong page hint never guesses");r.r.page=correct;
}
static void seed(fixed &pdf,const fs::path &work){
  history h(work/"sender.sqlite");reader_revision_info i{};reader_revision_error e{};int made=0;
  std::string b="{\"version\":1,\"id\":\"00000000000000000000000000000001\",\"entity_kind\":\"book\",\"entity_key\":\""+book+"\",\"operation\":\"put\",\"location_kind\":\"none\",\"parents\":[],\"payload\":{\"format\":\"pdf\",\"source_sha256\":\""+book.substr(4)+"\",\"source_bytes\":8845,\"title\":\"actual PDF\",\"author\":\"\",\"favorite\":false}}";
  check(reader_revision_local_raw_v3(h.store,b.data(),b.size(),&i,&made,&e)==READER_REV_OK&&made,e.message);
  auto point=capture(pdf.point),range=capture(pdf.range);apply(h,READER_RC_PROGRESS,&point);std::string progress=apply(h,READER_RC_PROGRESS,&point);
  apply(h,READER_RC_BOOKMARK,&point,bookmark,READER_RC_PUT,"point");std::string mark=apply(h,READER_RC_BOOKMARK,&point,bookmark,READER_RC_PUT,"point twice");
  apply(h,READER_RC_HIGHLIGHT,&range,highlight,READER_RC_PUT,"range");apply(h,READER_RC_NOTE_TEXT,nullptr,highlight,READER_RC_PUT,"edited");
  reader_rs_capture none{};none.mode=READER_RS_FIXED_PAGE;apply(h,READER_RC_HIGHLIGHT,&none,highlight,READER_RC_DELETE);std::string high=apply(h,READER_RC_HIGHLIGHT,&range,highlight,READER_RC_RESTORE,"restored");
  fs::create_directories(work/"packet");for(auto &w:pending(h)){reader_revision_info row{};check(reader_revision_validate_raw_v3(h.store,w.data(),w.size(),nullptr,&row,&e)==READER_REV_OK,e.message);write(work/"packet"/(std::string(row.revision_id)+".json"),w);}
  for(auto &entry:std::vector<std::pair<std::string,const exr_fixed_anchor *>>{{"point",&pdf.point},{"range",&pdf.range}}){auto &a=*entry.second;write(work/("sdk-"+entry.first+"-exact.bin"),std::string(a.exact,a.exact_size));write(work/("sdk-"+entry.first+"-prefix.bin"),std::string(a.prefix,a.prefix_size));write(work/("sdk-"+entry.first+"-suffix.bin"),std::string(a.suffix,a.suffix_size));}
  write(work/"progress.json",progress);write(work/"bookmark.json",mark);write(work/"highlight.json",high);
  write(work/"original.pdf",pdf.original);view(h,false);resolve(h,pdf,progress);resolve(h,pdf,high);
  char *bytes=nullptr;size_t n=0;check(reader_revision_get(h.store,i.revision_id,&bytes,&n,&i,&e)==READER_REV_ARGUMENT&&!bytes,"legacy revision API refuses raw store");
  auto before=pending(h);sqlite3 *lock=nullptr;check(sqlite3_open((work/"sender.sqlite").u8string().c_str(),&lock)==SQLITE_OK,"open transaction failure injector");check(sqlite3_exec(lock,"BEGIN IMMEDIATE",nullptr,nullptr,nullptr)==SQLITE_OK,"hold independent writer lock");
  std::string rid=id();auto hs=heads(h,"progress",book);const char *parent=hs[0].c_str();reader_rc_context ctx{};ctx.store=h.store;ctx.revision_id=rid.c_str();ctx.parser_version=exr_version();ctx.expected_heads=&parent;ctx.expected_count=1;reader_rc_command command{};command.kind=READER_RC_PROGRESS;command.book_key=book.c_str();command.capture=&point;reader_rc_result result{};reader_rc_error problem{};
  check(reader_rc_apply_fixed_v3(&ctx,&command,&result,&problem)!=READER_RC_OK&&!result.created,"blocked writer transaction fails cleanly");sqlite3_exec(lock,"ROLLBACK",nullptr,nullptr,nullptr);sqlite3_close(lock);check(pending(h)==before,"failed transaction retained exact outbox");
}
static void accept(fixed &pdf,const fs::path &work,bool reopening){
  history h(work/"receiver.sqlite");auto progress=read(work/"progress.json"),mark=read(work/"bookmark.json");
  if(!reopening){
    receive(h,progress);receive(h,mark);selected(h,"progress",book,READER_REV_UNSAFE);view(h,true);
    for(auto &p:fs::directory_iterator(work/"packet"))receive(h,read(p.path()));
  }
  auto before=pending(h);check(before.empty(),"remote receive never creates outbox");view(h,false);
  for(auto &p:std::vector<std::pair<const char *,std::string>>{{"progress",book},{"annotation",book+":"+bookmark},{"annotation",book+":"+highlight}}){auto wire=selected(h,p.first,p.second);resolve(h,pdf,wire);}
  receive(h,progress);check(pending(h)==before,"read-only resolve and duplicate receive keep outbox empty");
  reader_av_options options{};options.struct_size=sizeof(options);options.cancel=[](void *){return 1;};reader_av_view *v=nullptr;reader_av_error ve{};reader_av_open_raw_v3(h.store,book.c_str(),&options,&v,&ve);reader_av_cursor from{};reader_av_cursor_start(v,1,&from,&ve);reader_av_page page{};check(reader_av_page_get_raw_v3(v,&from,10,&page,&ve)==READER_AV_CANCELLED&&!page.items&&!page.count,"raw typed cancellation discards entire page");reader_av_close(&v,&ve);
  std::cout<<"PASS "<<(reopening?"third process reopen":"second process receive")<<std::endl;
}
static void protocol(const fs::path &work,const fs::path &input){history h(work/"protocol.sqlite");auto wire=read(input);reader_revision_info i{};reader_revision_error e{};auto status=reader_revision_validate_raw_v3(h.store,wire.data(),wire.size(),nullptr,&i,&e);std::cout<<"STATUS "<<status<<std::endl;}
static void receive_wire(const fs::path &work,const fs::path &input){history h(work/"graph.sqlite");auto wire=read(input);reader_revision_info i{};reader_revision_error e{};int made=0;auto status=reader_revision_validate_raw_v3(h.store,wire.data(),wire.size(),nullptr,&i,&e);std::string expected=i.sha256;if(status==READER_REV_OK)status=reader_revision_receive_raw_v3(h.store,wire.data(),wire.size(),expected.c_str(),&i,&made,&e);std::cout<<"STATUS "<<status<<std::endl;
  if(status==READER_REV_OK){reader_revision_state g{};reader_revision_heads_raw_v3(h.store,i.entity_kind,i.entity_key,nullptr,nullptr,&g,&e);std::cout<<"GRAPH "<<g.heads<<" "<<g.missing_parents<<" "<<g.foreign_parents<<" "<<g.projection_safe<<std::endl;}}
static void nullable(fixed &pdf,const fs::path &work){
  history h(work/"nullable.sqlite");reader_rs_envelope env{};env.revision_id="00000000000000000000000000000055";env.entity_kind="annotation";env.annotation_id=bookmark.c_str();env.operation="put";env.book_key=book.c_str();env.parser_version=exr_version();env.note_text="nullable expression";
  exr_fixed_anchor expression{};expression.page_id=pdf.point.page_id;auto c=capture(expression);char *w=nullptr;size_t n=0;reader_rs_error e{};
  check(reader_rs_encode_fixed_v3(h.store,&env,&c,&w,&n,&e)==READER_RS_OK,e.message);std::string wire(w,n);reader_rs_free(w);receive(h,wire);record r;decode(h,wire,r);
  check(!r.r.exact&&!r.r.prefix&&!r.r.suffix&&!r.r.exact_size&&!r.r.prefix_size&&!r.r.suffix_size,"NULL exact prefix suffix are not empty strings");
  exr_anchor_match m{};m.state=EXR_ANCHOR_FOUND;size_t p=0;check(reader_rs_resolve_fixed_v3(pdf.doc,&r.r,nullptr,&p,&m,&e)==READER_RS_ARGUMENT&&m.state!=EXR_ANCHOR_FOUND,"NULL exact expression cannot grant FOUND");
  /* Import book identity from the actual sender's unchanged raw wire. */
  for(auto &file:fs::directory_iterator(work/"packet")){auto body=read(file.path());reader_revision_info info{};reader_revision_error re{};reader_revision_validate_raw_v3(h.store,body.data(),body.size(),nullptr,&info,&re);if(!std::strcmp(info.entity_kind,"book"))receive(h,body);}
  apply(h,READER_RC_NOTE_TEXT,nullptr,bookmark,READER_RC_PUT,"nullable edit");
  reader_av_view *v=nullptr;reader_av_error av{};reader_av_open_raw_v3(h.store,book.c_str(),nullptr,&v,&av);reader_av_cursor cursor{};reader_av_cursor_start(v,1,&cursor,&av);reader_av_page page{};check(reader_av_page_get_raw_v3(v,&cursor,10,&page,&av)==READER_AV_OK&&page.count==1&&!page.items[0].exact&&!page.items[0].prefix&&!page.items[0].suffix&&!page.items[0].content_available,"typed nullable expression preserves NULL and hides usable capture");reader_av_page_free(&page);reader_av_close(&v,&av);
  /* An empty allocated selector is distinct and still decodes allocated. */
  char empty[1]={0};expression.exact=empty;expression.prefix=empty;expression.suffix=empty;env.revision_id="00000000000000000000000000000056";
  check(reader_rs_encode_fixed_v3(h.store,&env,&c,&w,&n,&e)==READER_RS_OK,e.message);record empty_record;decode(h,std::string(w,n),empty_record);reader_rs_free(w);check(empty_record.r.exact&&empty_record.r.prefix&&empty_record.r.suffix&&!empty_record.r.exact_size,"allocated empty selector presence preserved");
}
static void versions(const fs::path &work){
  history h(work/"versions.sqlite");reader_revision_error e{};reader_revision_info info{};int made=0;
  std::string text="A real public SDK text capture has enough context for stable matching.";
  std::string key="txt:"+std::string(std::getenv("SELECTOR_TXT_SHA"));
  std::string b="{\"version\":1,\"id\":\"00000000000000000000000000009999\",\"entity_kind\":\"book\",\"entity_key\":\""+key+"\",\"operation\":\"put\",\"location_kind\":\"none\",\"parents\":[],\"payload\":{\"format\":\"txt\",\"source_sha256\":\""+key.substr(4)+"\",\"source_bytes\":"+std::to_string(text.size())+",\"title\":\"actual compatibility TXT\",\"author\":\"\",\"favorite\":false}}";
  check(reader_revision_local_raw_v3(h.store,b.data(),b.size(),&info,&made,&e)==READER_REV_OK,e.message);
  exr_document *doc=nullptr;exr_error se{};check(exr_document_open_memory(EXR_TXT,text.data(),text.size(),&doc,&se)==EXR_OK,se.message);exr_anchor a{};check(exr_anchor_create(doc,2,6,&a,&se)==EXR_OK,se.message);reader_rs_capture c{};c.mode=READER_RS_REFLOW_GLOBAL;c.anchor=&a;
  for(unsigned version:{1u,2u}){
    auto wire=read(work.parent_path()/"candidate-legacy"/(version==1?"v1-wire.json":"v2-wire.json"));
    receive(h,wire);record old;decode(h,wire,old);std::string annotation=old.r.annotation_id,entity=key+":"+annotation,original_id="00000000000000000000000000000001";
    auto command=[&](reader_rc_kind kind,reader_rc_operation op,const reader_rs_capture *cap,unsigned requested){
      auto previous=heads(h,"annotation",entity);std::vector<const char *> ptrs;for(auto &p:previous)ptrs.push_back(p.c_str());std::string rid=id();reader_rc_context ctx{};ctx.store=h.store;ctx.revision_id=rid.c_str();ctx.parser_version=exr_version();ctx.expected_heads=ptrs.data();ctx.expected_count=ptrs.size();reader_rc_command cmd{};cmd.kind=kind;cmd.operation=op;cmd.book_key=key.c_str();cmd.annotation_id=annotation.c_str();cmd.capture=cap;cmd.text=op==READER_RC_DELETE?nullptr:"version preserved";reader_rc_result result{};reader_rc_error error{};
      auto status=reader_rc_apply_raw_v3(&ctx,&cmd,requested,&result,&error);check(status==READER_RC_OK,error.message);auto out=retained(h,rid);record r;decode(h,out,r);
      if(op==READER_RC_DELETE)check(!r.r.has_location,"legacy-source tombstone has no anchor version");else check(r.r.anchor_version==version&&same(r.r.exact,r.r.exact_size,a.exact,std::strlen(a.exact)),"explicit legacy restore or NOTE_TEXT keeps source version and bytes");return out;
    };
    command(READER_RC_NOTE_TEXT,READER_RC_PUT,nullptr,3);
    reader_rs_capture mode{};mode.mode=READER_RS_REFLOW_GLOBAL;command(READER_RC_HIGHLIGHT,READER_RC_DELETE,&mode,version);command(READER_RC_HIGHLIGHT,READER_RC_RESTORE,&c,version);
    check(retained(h,original_id)==wire,"reading legacy wire never rewrites retained bytes");
    /* Isolate two original source IDs that were deliberately identical in the
       byte comparison above; the second compatibility case uses another store. */
    if(version==1){reader_revision_error close{};reader_revisions_close(&h.store,&close);fs::path second=work/"versions2.sqlite";check(reader_revisions_open_raw_v3(second.u8string().c_str(),&h.store,&close)==READER_REV_OK,close.message);check(reader_revision_local_raw_v3(h.store,b.data(),b.size(),&info,&made,&e)==READER_REV_OK,e.message);}
  }
  reader_rc_context ctx{};ctx.store=h.store;ctx.revision_id="00000000000000000000000000007777";reader_rc_command cmd{};cmd.kind=READER_RC_HIGHLIGHT;cmd.book_key=key.c_str();cmd.annotation_id=bookmark.c_str();cmd.capture=&c;cmd.text="unsupported";reader_rc_result result{};reader_rc_error error{};auto before=pending(h);
  check(reader_rc_apply_raw_v3(&ctx,&cmd,4,&result,&error)==READER_RC_ARGUMENT&&!result.created&&pending(h)==before,"unknown explicit writer version refuses without commit");
  exr_anchor_free(&a);exr_document_free(doc);
}
#endif
int main(int argc,char **argv){try{
  check(selector_bytes_c_api()==0,"installed C ABI and legacy MAX2");if(argc<4)return 2;std::string mode=argv[1];fs::path work=fs::u8path(argv[3]);fs::create_directories(work);
  std::cout<<"SDK "<<exr_version()<<std::endl;
  if(mode=="legacy-refuse"){legacy_refuse(fs::u8path(argv[2]),work);return 0;}
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
  if(mode=="protocol"){protocol(work,fs::u8path(argv[2]));return 0;}
  if(mode=="receive-wire"){receive_wire(work,fs::u8path(argv[2]));return 0;}
  if(mode=="versions"){versions(work);return 0;}
#endif
  fixed pdf(fs::u8path(argv[2]));if(mode=="legacy"){original_v2(pdf,work);return 0;}
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
  if(mode=="seed")seed(pdf,work);else if(mode=="receive")accept(pdf,work,false);else if(mode=="reopen")accept(pdf,work,true);else if(mode=="nullable")nullable(pdf,work);else return 2;
#else
  return 2;
#endif
  return 0;
}catch(const std::exception &e){std::cerr<<"FAIL "<<e.what()<<std::endl;return 1;}}
