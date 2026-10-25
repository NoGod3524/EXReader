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
  check(exr_document_open_memory(EXR_TXT,text.data(),text.size(),nullptr,&document,&se)==EXR_OK,se.message);
  exr_anchor a{};check(exr_anchor_create(document,2,6,&a,&se)==EXR_OK,se.message);reader_rs_capture tc{};tc.mode=READER_RS_REFLOW_GLOBAL;tc.anchor=&a;
  std::string txt="txt:"+std::string(64,'a');e.entity_kind="annotation";e.annotation_id=bookmark.c_str();e.book_key=txt.c_str();e.note_text="kept";
  check(reader_rs_encode(store,&e,&tc,&wire,&n,&error)==READER_RS_OK,error.message);write(folder/"v1-wire.json",std::string(wire,n));reader_rs_free(wire);
  check(reader_rs_encode_v2(store,&e,&tc,0,&wire,&n,&error)==READER_RS_OK,error.message);write(folder/"v2-wire.json",std::string(wire,n));reader_rs_free(wire);
  exr_anchor_free(&a);exr_document_free(document);reader_revisions_close(&store,&re);
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
  reader_rc_result r{};reader_rc_error e{};auto st=reader_rc_apply_fixed_v3(&ctx,&cmd,&r,&e);check(st==READER_RC_OK,std::string("actual command ")+e.message);check(r.created==1,"new revision committed");
  std::string wire=retained(h,rid);check(reader_rc_apply_fixed_v3(&ctx,&cmd,&r,&e)==READER_RC_OK&&!r.created,"stable retry exact no-op");check(retained(h,rid)==wire,"retry kept exact raw wire");return wire;
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
  check(reader_revision_receive_raw_v3(h.store,wire.data(),wire.size(),i.sha256,&i,&created,&e)==READER_REV_OK,e.message);
}
static void resolve(history &h,fixed &pdf,const std::string &wire){
  record r;decode(h,wire,r);exr_anchor_match match{};size_t page=SIZE_MAX;reader_rs_error e{};
  check(reader_rs_resolve_fixed(pdf.doc,&r.r,nullptr,&page,&match,&e)==READER_RS_ARGUMENT,"legacy resolve refuses anchor3");
  check(reader_rs_resolve_fixed_v3(pdf.doc,&r.r,nullptr,&page,&match,&e)==READER_RS_OK&&match.state==EXR_ANCHOR_FOUND&&page==0,e.message);
  exr_fixed_anchor actual{};exr_error se{};check(exr_fixed_anchor_create("page-1",pdf.text,match.start,match.end,&actual,&se)==EXR_OK,se.message);
  check(actual.start==r.r.start&&actual.end==r.r.end&&same(actual.exact,actual.exact_size,r.r.exact,r.r.exact_size)&&same(actual.prefix,actual.prefix_size,r.r.prefix,r.r.prefix_size)&&same(actual.suffix,actual.suffix_size,r.r.suffix,r.r.suffix_size),"actual recapture exact nullable bytes");exr_fixed_anchor_free(&actual);
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
  std::cout<<"PASS "<<(reopening?"third process reopen":"second process receive")<<std::endl;
}
static void protocol(const fs::path &work,const fs::path &input){history h(work/"protocol.sqlite");auto wire=read(input);reader_revision_info i{};reader_revision_error e{};auto status=reader_revision_validate_raw_v3(h.store,wire.data(),wire.size(),nullptr,&i,&e);std::cout<<"STATUS "<<status<<std::endl;}
#endif
int main(int argc,char **argv){try{
  check(selector_bytes_c_api()==0,"installed C ABI and legacy MAX2");if(argc<4)return 2;std::string mode=argv[1];fs::path work=fs::u8path(argv[3]);fs::create_directories(work);
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
  if(mode=="protocol"){protocol(work,fs::u8path(argv[2]));return 0;}
#endif
  fixed pdf(fs::u8path(argv[2]));if(mode=="legacy"){original_v2(pdf,work);return 0;}
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
  if(mode=="seed")seed(pdf,work);else if(mode=="receive")accept(pdf,work,false);else if(mode=="reopen")accept(pdf,work,true);else return 2;
#else
  return 2;
#endif
  return 0;
}catch(const std::exception &e){std::cerr<<"FAIL "<<e.what()<<std::endl;return 1;}}
