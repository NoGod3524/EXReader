/* SPDX-License-Identifier: MIT
 * Installed-package consumer of the production Win32 owner. All fixtures,
 * processes and assertions run in Actions; this is not installed in the app.
 */
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <bcrypt.h>
#include "windows_records_owner.h"
#include "windows_raw3_apis.h"
#include <reader_commands.h>
#include <reader_metadata.h>
#include <reader_session.h>
#include <reader_sync.h>
#include <catalog.h>
#include <exreader.h>
#include <sqlite3.h>
#include <algorithm>
#include <array>
#include <climits>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#ifdef EXR_READER_WINDOWS_RAW3
#define reader_revision_validate reader_revision_validate_raw_v3
#define reader_revision_local_reading reader_revision_local_reading_raw_v3
#define reader_revision_receive reader_revision_receive_raw_v3
#define reader_revision_outbox reader_revision_outbox_raw_v3
#endif
namespace fs=std::filesystem;
namespace {
struct Check {std::string name;bool pass;std::string detail;};
std::vector<Check> checks;
std::string current_mode;
const std::string txt="A genuine public SDK capture has enough context for independently finding this selected range after reopening the original book.";
void require(bool ok,const std::string &name){if(!ok)throw std::runtime_error(name);}
void expect(bool ok,const std::string &name,const std::string &detail="") {checks.push_back({name,ok,detail});}
void group(const std::string &name,const std::function<void()> &body) {
  try{body();}catch(const std::exception &e){expect(false,name+": setup or execution",e.what());}
}
std::string read(const fs::path &p){std::ifstream f(p,std::ios::binary);require((bool)f,"Cannot read "+p.u8string());std::ostringstream s;s<<f.rdbuf();return s.str();}
void write(const fs::path &p,const std::string &s){std::ofstream f(p,std::ios::binary);f.write(s.data(),(std::streamsize)s.size());f.flush();require((bool)f,"Cannot write "+p.u8string());}
std::string quote(const std::string &s){std::string out="\"";const char *h="0123456789abcdef";for(unsigned char c:s){if(c=='"'||c=='\\'){out+='\\';out+=(char)c;}else if(c<32){out+="\\u00";out+=h[c>>4];out+=h[c&15];}else out+=(char)c;}return out+'"';}
std::string sha(const std::string &s){BCRYPT_ALG_HANDLE a=nullptr;std::array<unsigned char,32>d{};require(s.size()<=ULONG_MAX,"Hash input bounded");require(BCryptOpenAlgorithmProvider(&a,BCRYPT_SHA256_ALGORITHM,nullptr,0)>=0,"Open SHA256");auto st=BCryptHash(a,nullptr,0,(PUCHAR)s.data(),(ULONG)s.size(),d.data(),(ULONG)d.size());BCryptCloseAlgorithmProvider(a,0);require(st>=0,"Hash bytes");std::string out;const char *h="0123456789abcdef";for(auto c:d){out+=h[c>>4];out+=h[c&15];}return out;}
std::string new_id(){char id[33]{};require(reader_revision_new_id(id,nullptr)==READER_REV_OK,"Public new revision identity");return id;}
bool same(const char *a,size_t an,const char *b,size_t bn){return (!a)==(!b)&&an==bn&&(!an||!std::memcmp(a,b,an));}
struct Library {exr_library *p=nullptr;explicit Library(const std::string &path){exr_error e{};require(exr_library_open(path.c_str(),&p,&e)==EXR_OK,std::string("Open SDK library: ")+e.message);}~Library(){exr_library_close(p);}};
struct Revisions {reader_revisions *p=nullptr;explicit Revisions(const std::string &path){reader_revision_error e{};require(reader_revisions_open(path.c_str(),&p,&e)==READER_REV_OK,std::string("Open installed revisions: ")+e.message);}~Revisions(){reader_revisions_close(&p,nullptr);}};
struct Decoded {reader_rs_record r{};~Decoded(){reader_rs_record_free(&r);}};
struct Response {winrecords_response r{};exr_status status=EXR_ARGUMENT;~Response(){winrecords_response_free(&r);}Response()=default;Response(const Response&)=delete;Response& operator=(const Response&)=delete;};
struct Capture {reader_rs_capture c{};exr_anchor a{};exr_fixed_anchor f{};size_t part=0;~Capture(){exr_anchor_free(&a);exr_fixed_anchor_free(&f);}};
struct CaptureContext {
  std::string sdk_path;int64_t sdk_id=0;exr_format format=EXR_TXT;bool range=false;
  unsigned captures=0,historical_calls=0,found=0;int stop_phase=0;fs::path marker;
  std::wstring pending;
};
exr_status real_capture(void *opaque,const reader_rs_record *historical,reader_rs_capture *c,exr_anchor *a,exr_fixed_anchor *f,size_t *part) {
  auto &ctx=*(CaptureContext *)opaque;
  try {
    ++ctx.captures;if(historical)++ctx.historical_calls;
    Library sdk(ctx.sdk_path);exr_error e{};*c={};*a={};*f={};*part=0;
    exr_anchor_match m{};size_t begin=ctx.range?2:0,end=ctx.range?12:0;
    if(ctx.format==EXR_PDF){
      exr_fixed_document *document=nullptr;exr_fixed_text *text=nullptr;
      auto status=exr_library_fixed(sdk.p,ctx.sdk_id,nullptr,&document,&e);
      if(status!=EXR_OK)return status;
      size_t page=0;
      if(historical){
#ifdef EXR_READER_WINDOWS_RAW3
        auto rs=historical->anchor_version==3?reader_rs_resolve_fixed_v3(document,historical,nullptr,&page,&m,nullptr):reader_rs_resolve_fixed(document,historical,nullptr,&page,&m,nullptr);
#else
        auto rs=reader_rs_resolve_fixed(document,historical,nullptr,&page,&m,nullptr);
#endif
        if(rs!=READER_RS_OK||m.state!=EXR_ANCHOR_FOUND){exr_fixed_free(document);return EXR_ARGUMENT;}
        ++ctx.found;begin=m.start;end=m.end;
      }
      status=exr_fixed_load_text(document,page,nullptr,&text,&e);
      size_t n=0;const char *bytes=status==EXR_OK?exr_fixed_text_string(text,&n):nullptr;
      if(!historical){begin=0;end=ctx.range?n:0;}
      size_t count=0;const auto *pages=exr_fixed_pages(document,&count);
      if(status==EXR_OK&&pages&&page<count&&bytes)status=exr_fixed_anchor_create(pages[page].id,text,begin,end,f,&e);
      else if(status==EXR_OK)status=EXR_FORMAT;
      exr_fixed_text_free(text);exr_fixed_free(document);
      if(status!=EXR_OK)return status;c->mode=READER_RS_FIXED_PAGE;c->fixed=f;c->page=page;
    }else{
      exr_document *document=nullptr;auto status=exr_library_document(sdk.p,ctx.sdk_id,&document,&e);if(status!=EXR_OK)return status;
      if(historical){if(reader_rs_resolve_reflow(document,historical,nullptr,&m,nullptr)!=READER_RS_OK||m.state!=EXR_ANCHOR_FOUND){exr_document_free(document);return EXR_ARGUMENT;}++ctx.found;begin=m.start;end=m.end;}
      status=exr_anchor_create(document,begin,end,a,&e);exr_document_free(document);
      if(status!=EXR_OK)return status;c->mode=READER_RS_REFLOW_GLOBAL;c->anchor=a;
    }
    return EXR_OK;
  }catch(...){return EXR_IO;}
}
void phase_marker(void *opaque,int phase){
  auto &ctx=*(CaptureContext *)opaque;if(ctx.stop_phase!=phase)return;
  /* The external driver kills this real process after observing a flushed file.
     No return value, database change or commit outcome is simulated here. */
  std::string pending=read(fs::path(ctx.pending));
  std::string json="{\"phase\":"+std::to_string(phase)+",\"pid\":"+std::to_string(GetCurrentProcessId())+",\"pending_bytes\":"+std::to_string(pending.size())+",\"pending_sha256\":"+quote(sha(pending))+",\"private_magic\":"+quote(pending.substr(0,8))+"}\n";
  HANDLE h=CreateFileW(ctx.marker.c_str(),GENERIC_WRITE,FILE_SHARE_READ,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL|FILE_FLAG_WRITE_THROUGH,nullptr);
  if(h==INVALID_HANDLE_VALUE)ExitProcess(91);
  DWORD n=0;bool ok=WriteFile(h,json.data(),(DWORD)json.size(),&n,nullptr)&&n==json.size()&&FlushFileBuffers(h);CloseHandle(h);if(!ok)ExitProcess(92);
  std::cout<<"{\"type\":\"phase_marker\",\"phase\":"<<phase<<"}"<<std::endl;
  for(;;)Sleep(1000);
}
struct Book {
  fs::path root;std::string sdk_path,database,key,original,title,format,hash;std::wstring pending;int64_t id=0;CaptureContext context;
  Book(const fs::path &folder,const fs::path &pdf,bool fixed):root(folder){
    fs::create_directories(root);sdk_path=(root/"sdk.sqlite").u8string();database=(root/"product.sqlite").u8string();pending=(root/"pending.bin").wstring();
    original=fixed?read(pdf):txt;format=fixed?"pdf":"txt";hash=sha(original);key=format+":"+hash;
    Library sdk(sdk_path);exr_error e{};int created=0;
    require(exr_library_import_unique(sdk.p,fixed?EXR_PDF:EXR_TXT,original.data(),original.size(),"Windows owner public original",&id,&created,&e)==EXR_OK,std::string("Import real original: ")+e.message);
    void *retained=nullptr;size_t size=0;require(exr_library_blob(sdk.p,id,0,&retained,&size,&e)==EXR_OK,"Read retained original through SDK");
    bool identical=size==original.size()&&(!size||!std::memcmp(retained,original.data(),size));exr_free(retained);require(identical,"SDK original exact byte identity");
    exr_book *books=nullptr;size_t count=0;require(exr_library_books(sdk.p,nullptr,&books,&count,&e)==EXR_OK,"Public SDK book metadata");
    for(size_t i=0;i<count;i++)if(books[i].id==id)title=books[i].title?books[i].title:"";exr_books_free(books,count);require(!title.empty(),"Imported title present");
    reader_catalog *catalog=nullptr;require(reader_catalog_open(database.c_str(),&catalog,nullptr)==0,"Open installed product catalog");
    reader_catalog_book b{};b.format=format.c_str();b.sha256=hash.c_str();b.title=title.c_str();b.author="";b.sort_title=title.c_str();b.location_kind=fixed?"fixed_page":"reflow_global";b.source_bytes=original.size();b.sdk_book_id=id;
    int attached=reader_catalog_attach(catalog,&b,nullptr);reader_catalog_close(&catalog,nullptr);require(attached==0,"Actual public product mapping attach");
    context.sdk_path=sdk_path;context.sdk_id=id;context.format=fixed?EXR_PDF:EXR_TXT;context.pending=pending;
  }
  winrecords_request request(int action){winrecords_request r{};r.database=database.c_str();r.book_key=key.c_str();r.pending_path=pending.c_str();r.sdk_book=id;r.source_bytes=original.size();r.action=action;r.kind=READER_RC_PROGRESS;r.direction=1;r.context=&context;r.capture=real_capture;r.phase=phase_marker;return r;}
};
void invoke(const winrecords_request &r,Response &out){out.status=winrecords_execute(&r,&out.r);}
void succeeded(Response &out,const std::string &where){require(out.status==EXR_OK,where+": "+out.r.message);}
struct Selected {std::string bytes;reader_revision_info info{};reader_revision_selection selection{};reader_revision_status status=READER_REV_ARGUMENT;};
Selected selected(Book &b,bool progress,const std::string &annotation=""){
  Revisions store(b.database);Selected out;char *p=nullptr;size_t n=0;std::string entity=progress?b.key:b.key+":"+annotation;
  out.status=reader_revision_selected(store.p,progress?"progress":"annotation",entity.c_str(),&p,&n,&out.info,&out.selection,nullptr);if(p)out.bytes.assign(p,n);reader_revision_bytes_free(p);return out;
}
std::string retained(Book &b,const std::string &rid){Revisions s(b.database);char *p=nullptr;size_t n=0;reader_revision_info i{};require(reader_revision_get(s.p,rid.c_str(),&p,&n,&i,nullptr)==READER_REV_OK,"Retained revision get");std::string out(p,n);reader_revision_bytes_free(p);return out;}
void decode(Book &b,const std::string &wire,Decoded &out){Revisions s(b.database);require(reader_rs_decode(s.p,wire.data(),wire.size(),&out.r,nullptr)==READER_RS_OK,"Installed decode retained wire");}
bool equal_location(const reader_rs_record &a,const reader_rs_record &b){return a.mode==b.mode&&a.has_location==b.has_location&&a.anchor_version==b.anchor_version&&a.start==b.start&&a.end==b.end&&a.part==b.part&&a.page==b.page&&same(a.exact,a.exact_size,b.exact,b.exact_size)&&same(a.prefix,a.prefix_size,b.prefix,b.prefix_size)&&same(a.suffix,a.suffix_size,b.suffix,b.suffix_size)&&!std::strcmp(a.parser_version,b.parser_version)&&(!a.page_id)==(!b.page_id)&&std::string(a.page_id?a.page_id:"")==std::string(b.page_id?b.page_id:"")&&(!a.part_path)==(!b.part_path)&&std::string(a.part_path?a.part_path:"")==std::string(b.part_path?b.part_path:"")&&(!a.chapter)==(!b.chapter)&&std::string(a.chapter?a.chapter:"")==std::string(b.chapter?b.chapter:"");}
std::string product_snapshot(Book &b){
  sqlite3 *db=nullptr;require(sqlite3_open_v2(b.database.c_str(),&db,SQLITE_OPEN_READONLY,nullptr)==SQLITE_OK,"Read-only product snapshot");
  std::vector<std::string> tables;sqlite3_stmt *q=nullptr;require(sqlite3_prepare_v2(db,"SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name",-1,&q,nullptr)==SQLITE_OK,"Snapshot table list");
  while(sqlite3_step(q)==SQLITE_ROW)tables.emplace_back((const char*)sqlite3_column_text(q,0));sqlite3_finalize(q);std::string all;
  for(const auto &table:tables){std::string sql="SELECT * FROM \""+table+"\" ORDER BY rowid";require(sqlite3_prepare_v2(db,sql.c_str(),-1,&q,nullptr)==SQLITE_OK,"Snapshot product table");all+=table+'\n';int rc;
    while((rc=sqlite3_step(q))==SQLITE_ROW){for(int j=0;j<sqlite3_column_count(q);j++){int n=sqlite3_column_bytes(q,j);const void *v=sqlite3_column_blob(q,j);all+=std::to_string(sqlite3_column_type(q,j))+":"+std::to_string(n)+":";if(n)all.append((const char*)v,(size_t)n);all+='|';}all+='\n';}require(rc==SQLITE_DONE,"Snapshot rows complete");sqlite3_finalize(q);
  }sqlite3_close(db);return sha(all);
}
std::string sdk_snapshot(Book &b){
  Library lib(b.sdk_path);exr_error e{};exr_book *books=nullptr;size_t n=0;require(exr_library_books(lib.p,nullptr,&books,&n,&e)==EXR_OK,"Public SDK state snapshot");std::string state;
  for(size_t i=0;i<n;i++)state+=std::to_string(books[i].id)+":"+std::to_string(books[i].position)+":"+std::to_string(books[i].status)+":"+std::to_string(books[i].favorite)+";";exr_books_free(books,n);
  if(b.format=="pdf"){exr_fixed_note *notes=nullptr;n=0;require(exr_library_fixed_notes(lib.p,b.id,&notes,&n,&e)==EXR_OK,"Fixed SDK notes snapshot");state+="notes="+std::to_string(n);exr_fixed_notes_free(notes,n);}
  else{exr_note *notes=nullptr;n=0;require(exr_library_notes(lib.p,b.id,&notes,&n,&e)==EXR_OK,"Reflow SDK notes snapshot");state+="notes="+std::to_string(n);exr_notes_free(notes,n);exr_anchor p{};exr_anchor_state st{};require(exr_library_progress_get(lib.p,b.id,&p,&st,&e)==EXR_OK,"Public progress snapshot");state+="progress="+std::to_string(st)+":"+std::to_string(p.start)+":"+std::to_string(p.end);exr_anchor_free(&p);}
  void *bytes=nullptr;size_t size=0;require(exr_library_blob(lib.p,b.id,0,&bytes,&size,&e)==EXR_OK,"Original snapshot");state+=sha(std::string((const char*)bytes,size));exr_free(bytes);return sha(state);
}
void capture_now(Book &b,Capture &out,const reader_rs_record *historical=nullptr){require(real_capture(&b.context,historical,&out.c,&out.a,&out.f,&out.part)==EXR_OK,"Actual independent SDK capture or FOUND");}
bool same_capture(const reader_rs_record &r,const Capture &c){if(r.mode!=c.c.mode)return false;if(r.mode==READER_RS_FIXED_PAGE)return r.page==c.c.page&&r.start==c.f.start&&r.end==c.f.end&&same(r.exact,r.exact_size,c.f.exact,c.f.exact_size)&&same(r.prefix,r.prefix_size,c.f.prefix,c.f.prefix_size)&&same(r.suffix,r.suffix_size,c.f.suffix,c.f.suffix_size)&&r.page_id&&!std::strcmp(r.page_id,c.f.page_id);return r.start==c.a.start&&r.end==c.a.end&&same(r.exact,r.exact_size,c.a.exact,c.a.exact?std::strlen(c.a.exact):0)&&same(r.prefix,r.prefix_size,c.a.prefix,c.a.prefix?std::strlen(c.a.prefix):0)&&same(r.suffix,r.suffix_size,c.a.suffix,c.a.suffix?std::strlen(c.a.suffix):0);}
void owner_save(Book &b,reader_rc_kind kind,reader_rc_operation op,const std::string &annotation,const Selected *head,const char *body,const char *version,Response &out){auto r=b.request(WINRECORDS_SAVE);r.kind=kind;r.operation=op;r.annotation_id=annotation.c_str();r.body=body;r.version=version;if(head){r.head=head->info.revision_id;r.sha256=head->info.sha256;}invoke(r,out);}
void read_found(Book &b,bool progress,const std::string &aid,unsigned version,const std::string &label){
  auto before=product_snapshot(b),sdk_before=sdk_snapshot(b);auto head=selected(b,progress,aid);require(head.status==READER_REV_OK,"Selected safe head for READ");
  auto r=b.request(WINRECORDS_READ);r.progress_target=progress?1:0;r.annotation_id=aid.c_str();r.head=head.info.revision_id;r.sha256=head.info.sha256;Response out;invoke(r,out);succeeded(out,label+" owner READ");expect(out.r.record.anchor_version==version,label+" READ exact source version");
  Capture fresh;auto found_before=b.context.found;capture_now(b,fresh,&out.r.record);expect(b.context.found==found_before+1&&same_capture(out.r.record,fresh),label+" fresh independent public FOUND and byte-for-byte recapture");
  expect(product_snapshot(b)==before,label+" LIST/READ/FOUND has zero product writes");expect(sdk_snapshot(b)==sdk_before,label+" owner read leaves SDK notes/progress/original unchanged");
}
void bootstrap(Book &b){Revisions s(b.database);uint64_t bytes=0;auto st=reader_revision_book_identity(s.p,b.key.c_str(),&bytes,nullptr);if(st==READER_REV_OK){require(bytes==b.original.size(),"Retained book identity");return;}require(st==READER_REV_NOT_FOUND,"Missing book history before explicit bootstrap");std::string rid=new_id();reader_command_context ctx{s.p,rid.c_str(),nullptr,0};reader_book_command cmd{};cmd.operation=READER_COMMAND_PUT;cmd.book_key=b.key.c_str();cmd.format=b.format.c_str();cmd.source_sha256=b.hash.c_str();cmd.title=b.title.c_str();cmd.author="";cmd.sort_title=b.title.c_str();cmd.source_bytes=b.original.size();reader_command_result result{};require(reader_command_apply_book(&ctx,&cmd,&result,nullptr)==READER_COMMAND_OK,"Public typed book bootstrap");}
#ifdef EXR_READER_WINDOWS_RAW3
#undef reader_revisions_open
#endif
reader_rs_status encode_legacy_source(Book &b,unsigned version,const reader_rs_envelope &env,const Capture &cap,char **bytes,size_t *n,reader_rs_error *error){
  reader_revisions *legacy=nullptr;reader_revision_error re{};
  require(reader_revisions_open((b.root/"legacy-encoder.sqlite").u8string().c_str(),&legacy,&re)==READER_REV_OK,std::string("Open actual legacy encoder store: ")+re.message);
  auto status=version==1?reader_rs_encode(legacy,&env,&cap.c,bytes,n,error):reader_rs_encode_v2(legacy,&env,&cap.c,cap.part,bytes,n,error);
  reader_revisions_close(&legacy,nullptr);return status;
}
#ifdef EXR_READER_WINDOWS_RAW3
#define reader_revisions_open reader_revisions_open_raw_v3
#endif
std::string seed(Book &b,unsigned version,const std::string &aid,const char *parser,bool nullable=false,const Selected *parent=nullptr,bool remote=false){
  bootstrap(b);b.context.range=true;Capture cap;capture_now(b,cap);exr_fixed_anchor null_expression{};
  if(nullable){/* A retained NULL transport expression, explicitly not an SDK capture. */null_expression.page_id=cap.f.page_id;cap.c.fixed=&null_expression;cap.c.page=0;}
  std::string rid=new_id();const char *p=parent?parent->info.revision_id:nullptr;reader_rs_envelope e{};e.revision_id=rid.c_str();e.operation="put";e.entity_kind="annotation";e.book_key=b.key.c_str();e.annotation_id=aid.c_str();e.parents=parent?&p:nullptr;e.parent_count=parent?1:0;e.note_text="retained source";e.parser_version=parser;
  Revisions s(b.database);char *bytes=nullptr;size_t n=0;reader_rs_error error{};reader_rs_status st;
#ifdef EXR_READER_WINDOWS_RAW3
  if(version==3)st=reader_rs_encode_fixed_v3(s.p,&e,&cap.c,&bytes,&n,&error);else
#endif
  st=encode_legacy_source(b,version,e,cap,&bytes,&n,&error);
  require(st==READER_RS_OK,std::string("Encode genuine selected source: ")+error.message);std::string wire(bytes,n);reader_rs_free(bytes);reader_revision_info info{};int created=0;
  const auto transport_sha=sha(wire);
  auto status=remote?reader_revision_receive(s.p,wire.data(),wire.size(),transport_sha.c_str(),&info,&created,nullptr):reader_revision_local_reading(s.p,wire.data(),wire.size(),parent?&p:nullptr,parent?1:0,&info,&created,nullptr);
  require(status==READER_REV_OK&&created,"Commit real retained selected source");return rid;
}
void roundtrip(Book &b,const std::string &aid,unsigned version,const std::string &source_rid){
  const auto original_wire=retained(b,source_rid);Decoded original;decode(b,original_wire,original);read_found(b,false,aid,version,"v"+std::to_string(version));
  auto head=selected(b,false,aid);Response edit;owner_save(b,READER_RC_NOTE_TEXT,READER_RC_PUT,aid,&head,"edited by real owner",nullptr,edit);succeeded(edit,"NOTE_TEXT");auto edited=selected(b,false,aid);Decoded er;decode(b,edited.bytes,er);
  expect(edit.r.committed&&edit.r.created&&er.r.note_text&&!std::strcmp(er.r.note_text,"edited by real owner")&&equal_location(original.r,er.r),"v"+std::to_string(version)+" NOTE_TEXT preserves version and nullable selector bytes");
  head=edited;Response removed;owner_save(b,READER_RC_HIGHLIGHT,READER_RC_DELETE,aid,&head,nullptr,nullptr,removed);succeeded(removed,"mode-only DELETE");auto deleted=selected(b,false,aid);Decoded tomb;decode(b,deleted.bytes,tomb);expect(removed.r.committed&&tomb.r.mode==original.r.mode&&!tomb.r.has_location&&!tomb.r.exact&&!tomb.r.prefix&&!tomb.r.suffix,"v"+std::to_string(version)+" real owner DELETE persists mode-only tombstone");
  auto req=b.request(WINRECORDS_HISTORY);req.annotation_id=aid.c_str();req.head=deleted.info.revision_id;req.sha256=deleted.info.sha256;auto before=product_snapshot(b);Response versions;invoke(req,versions);succeeded(versions,"HISTORY");bool found=false;for(size_t i=0;i<versions.r.version_count;i++)found|=source_rid==versions.r.versions[i];expect(found&&versions.r.history_complete,"v"+std::to_string(version)+" history exposes exact original retained version");expect(product_snapshot(b)==before,"v"+std::to_string(version)+" history read has no writes");
  unsigned actual=b.context.found;Response restored;owner_save(b,READER_RC_HIGHLIGHT,READER_RC_RESTORE,aid,&deleted,nullptr,source_rid.c_str(),restored);succeeded(restored,"RESTORE after FOUND");auto live=selected(b,false,aid);Decoded rr;decode(b,live.bytes,rr);expect(restored.r.committed&&b.context.found==actual+1&&equal_location(original.r,rr.r),"v"+std::to_string(version)+" owner RESTORE independently FOUND keeps source representation");
  expect(retained(b,source_rid)==original_wire,"v"+std::to_string(version)+" original retained wire never rewritten");read_found(b,false,aid,version,"restored-v"+std::to_string(version));
}
void fixed_suite(const fs::path &work,const fs::path &pdf){
  Book b(work/"fixed",pdf,true);require(b.original.size()==8845,"Original PDF is actual 8845-byte selector fixture");Capture point;capture_now(b,point);expect(point.f.exact&&point.f.exact_size==0&&point.f.suffix&&std::memchr(point.f.suffix,0,point.f.suffix_size),"Real SDK point allocated empty exact and NUL suffix");b.context.range=true;Capture range;capture_now(b,range);expect(range.f.exact_size>0&&std::memchr(range.f.exact,0,range.f.exact_size),"Real SDK nonempty range contains NUL");b.context.range=false;
  const auto sdk_before=sdk_snapshot(b);Response progress;owner_save(b,READER_RC_PROGRESS,READER_RC_PUT,"",nullptr,nullptr,nullptr,progress);
#ifdef EXR_READER_WINDOWS_RAW3
  succeeded(progress,"fixed3 progress");expect(progress.r.committed&&progress.r.created,"Actual Win32 owner commits fixed3 point");read_found(b,true,"",3,"fixed3 point progress");
  Response bookmark;owner_save(b,READER_RC_BOOKMARK,READER_RC_PUT,"",nullptr,"point bookmark",nullptr,bookmark);succeeded(bookmark,"fixed3 bookmark");std::string bid=bookmark.r.saved_annotation;read_found(b,false,bid,3,"fixed3 point bookmark");
  b.context.range=true;Response highlight;owner_save(b,READER_RC_HIGHLIGHT,READER_RC_PUT,"",nullptr,"NUL range",nullptr,highlight);succeeded(highlight,"fixed3 highlight");std::string aid=highlight.r.saved_annotation,rid=highlight.r.saved_revision;
  auto req=b.request(WINRECORDS_LIST);Response list;invoke(req,list);succeeded(list,"fixed3 LIST");bool mark=false,high=false;for(size_t i=0;i<list.r.page.count;i++){const auto &item=list.r.page.items[i];if(bid==item.annotation_id)mark=item.content_available&&item.anchor_version==3&&item.exact&&item.exact_size==0;if(aid==item.annotation_id)high=item.content_available&&item.anchor_version==3&&item.exact_size&&std::memchr(item.exact,0,item.exact_size);}expect(mark&&high,"Real owner LIST retains empty/NUL counted selectors");
  roundtrip(b,aid,3,rid);expect(sdk_snapshot(b)==sdk_before,"All fixed3 owner commands leave public SDK notes/progress/original unchanged");
#else
  expect(progress.status!=EXR_OK&&!progress.r.committed&&!fs::exists(fs::path(b.pending)),"Legacy real owner refuses NUL fixed capture without publishing private bytes");
#endif
}
#ifdef EXR_READER_WINDOWS_RAW3
void parser_suite(const fs::path &work,const fs::path &pdf){
  const char *parsers[]={"9.99.0","unknown-parser","exreader-sdk-exreader-sdk-3.41.0"};
  for(size_t i=0;i<3;i++){
    Book b(work/("parser-"+std::to_string(i)),pdf,false);std::string aid=new_id(),rid=seed(b,2,aid,parsers[i]);auto original_wire=retained(b,rid);auto current=selected(b,false,aid);auto before=product_snapshot(b);unsigned captures=b.context.captures;
    auto r=b.request(WINRECORDS_READ);r.annotation_id=aid.c_str();r.head=current.info.revision_id;r.sha256=current.info.sha256;Response denied;invoke(r,denied);expect(denied.status!=EXR_OK,"Parser "+std::to_string(i)+" READ rejects before SDK resolve");expect(product_snapshot(b)==before&&b.context.captures==captures,"Parser "+std::to_string(i)+" READ has zero writes/captures");
    Response edit;owner_save(b,READER_RC_NOTE_TEXT,READER_RC_PUT,aid,&current,"must not edit unsupported parser",nullptr,edit);expect(edit.status!=EXR_OK&&!edit.r.committed&&product_snapshot(b)==before&&!fs::exists(fs::path(b.pending)),"Parser "+std::to_string(i)+" NOTE_TEXT rejects with zero extra writes");
    current=selected(b,false,aid);Response del;owner_save(b,READER_RC_HIGHLIGHT,READER_RC_DELETE,aid,&current,nullptr,nullptr,del);succeeded(del,"Delete unsupported parser source explicitly");auto tomb=selected(b,false,aid);before=product_snapshot(b);captures=b.context.captures;
    auto history=b.request(WINRECORDS_HISTORY);history.annotation_id=aid.c_str();history.head=tomb.info.revision_id;history.sha256=tomb.info.sha256;Response list;invoke(history,list);succeeded(list,"Unsupported parser HISTORY");expect(list.r.version_count==0,"Parser "+std::to_string(i)+" history never offers unsupported restore");
    Response restore;owner_save(b,READER_RC_HIGHLIGHT,READER_RC_RESTORE,aid,&tomb,nullptr,rid.c_str(),restore);expect(restore.status!=EXR_OK&&!restore.r.committed&&product_snapshot(b)==before&&b.context.captures==captures&&!fs::exists(fs::path(b.pending)),"Parser "+std::to_string(i)+" RESTORE rejects before capture and with zero extra writes");expect(retained(b,rid)==original_wire,"Parser "+std::to_string(i)+" rejected records retained byte-for-byte");
  }
}
void null_suite(const fs::path &work,const fs::path &pdf){
  Book b(work/"null-transport",pdf,true);std::string aid=new_id(),rid=seed(b,3,aid,exr_version(),true,nullptr,true);auto current=selected(b,false,aid);Decoded n;decode(b,current.bytes,n);require(n.r.has_location&&n.r.anchor_version==3&&!n.r.exact&&!n.r.prefix&&!n.r.suffix,"Explicit retained NULL transport shape");const auto before=product_snapshot(b),sdk_before=sdk_snapshot(b);
  Response list;auto lr=b.request(WINRECORDS_LIST);invoke(lr,list);succeeded(list,"NULL LIST");expect(list.r.page.count==1&&!list.r.page.items[0].content_available&&!list.r.page.items[0].exact,"NULL transport has no usable UI list content");
  Capture output;unsigned found=b.context.found;auto status=real_capture(&b.context,&n.r,&output.c,&output.a,&output.f,&output.part);expect(status!=EXR_OK&&b.context.found==found,"NULL transport never grants independent FOUND/jump");
  Response edit;owner_save(b,READER_RC_NOTE_TEXT,READER_RC_PUT,aid,&current,"blocked NULL edit",nullptr,edit);expect(edit.status!=EXR_OK&&!edit.r.committed&&product_snapshot(b)==before&&!fs::exists(fs::path(b.pending)),"NULL owner NOTE_TEXT rejects with zero writes");
  Response del;owner_save(b,READER_RC_HIGHLIGHT,READER_RC_DELETE,aid,&current,nullptr,nullptr,del);succeeded(del,"NULL source explicit delete");auto tomb=selected(b,false,aid);auto deleted=product_snapshot(b);auto history=b.request(WINRECORDS_HISTORY);history.annotation_id=aid.c_str();history.head=tomb.info.revision_id;history.sha256=tomb.info.sha256;Response versions;invoke(history,versions);succeeded(versions,"NULL HISTORY");expect(!versions.r.version_count,"NULL historical source never offered as restorable");
  Response restore;owner_save(b,READER_RC_HIGHLIGHT,READER_RC_RESTORE,aid,&tomb,nullptr,rid.c_str(),restore);expect(restore.status!=EXR_OK&&!restore.r.committed&&b.context.found==found&&product_snapshot(b)==deleted&&!fs::exists(fs::path(b.pending)),"NULL restore never grants navigation or writes after failed public resolve");expect(sdk_snapshot(b)==sdk_before,"NULL tests never write SDK notes/progress/original");
}
#endif
void compatibility(const fs::path &work,const fs::path &pdf){
#ifdef EXR_READER_WINDOWS_RAW3
  for(unsigned version:{1u,2u}){Book b(work/("compat-v"+std::to_string(version)),pdf,false);std::string aid=new_id(),rid=seed(b,version,aid,exr_version());roundtrip(b,aid,version,rid);}
#else
  Book b(work/"legacy-txt",pdf,false);b.context.range=true;Response saved;owner_save(b,READER_RC_HIGHLIGHT,READER_RC_PUT,"",nullptr,"legacy true SDK source",nullptr,saved);succeeded(saved,"Actual legacy owner TXT save");read_found(b,false,saved.r.saved_annotation,2,"Actual legacy v2 owner");
#endif
}
void fresh(const fs::path &work,const fs::path &pdf){Book b(work/"fixed",pdf,true);auto current=selected(b,true);require(current.status==READER_REV_OK,"Fresh process progress exists");read_found(b,true,"",3,"fresh-process fixed3");}
void child(const fs::path &work,const fs::path &pdf,int phase,const fs::path &marker,bool legacy){
  Book b(work,pdf,!legacy);b.context.range=legacy;b.context.stop_phase=phase;b.context.marker=marker;auto req=b.request(WINRECORDS_SAVE);req.kind=legacy?READER_RC_HIGHLIGHT:READER_RC_PROGRESS;req.body=legacy?"real legacy pending":nullptr;
  Response result;invoke(req,result);throw std::runtime_error("Child owner returned before external kill: "+std::string(result.r.message));
}
std::string pending_revision(Book &b){auto req=b.request(WINRECORDS_LIST);Response out;invoke(req,out);succeeded(out,"Inspect real pending request");require(out.r.pending&&!out.r.pending_corrupt&&std::strlen(out.r.pending_revision)==32,"Real intact pending revision");return out.r.pending_revision;}
void reject_pending(const fs::path &work,const fs::path &pdf,bool legacy_book){
  Book b(work,pdf,!legacy_book);auto original=read(fs::path(b.pending));auto before=product_snapshot(b);b.context.range=legacy_book;Response out;owner_save(b,legacy_book?READER_RC_HIGHLIGHT:READER_RC_PROGRESS,READER_RC_PUT,"",nullptr,legacy_book?"must not replace":nullptr,nullptr,out);
  expect(out.status!=EXR_OK&&!out.r.committed&&read(fs::path(b.pending))==original&&product_snapshot(b)==before,"Existing old/new private intent excludes a second writer without migration");
  expect(original.size()>44&&(original.substr(0,8)=="EXRRD001"||original.substr(0,8)=="EXRRD002"),"Actual production private format magic retained");
}
#ifdef EXR_READER_WINDOWS_RAW3
void newer_progress(Book &b,const Selected &prior){
  Capture cap;capture_now(b,cap);Revisions store(b.database);auto rid=new_id();const char *parent=prior.info.revision_id;reader_rs_envelope env{};env.revision_id=rid.c_str();env.operation="put";env.entity_kind="progress";env.book_key=b.key.c_str();env.parents=&parent;env.parent_count=1;env.parser_version=exr_version();char *bytes=nullptr;size_t n=0;require(reader_rs_encode_fixed_v3(store.p,&env,&cap.c,&bytes,&n,nullptr)==READER_RS_OK,"Encode genuine newer remote progress");std::string wire(bytes,n);reader_rs_free(bytes);reader_revision_info info{};int created=0;require(reader_revision_receive(store.p,wire.data(),wire.size(),sha(wire).c_str(),&info,&created,nullptr)==READER_REV_OK&&created,"Receive actual newer head after original retained RID");
}
void verify_child(const fs::path &work,const fs::path &pdf,int phase,bool legacy){
  Book b(work,pdf,!legacy);auto original=read(fs::path(b.pending));require(original.substr(0,8)==(legacy?"EXRRD001":"EXRRD002"),"Actual legacy/OFF or raw/ON producer private magic");write(work/"pending-before-retry.bin",original);std::string rid=pending_revision(b);auto before=product_snapshot(b);
  b.context.range=legacy;Response refused;owner_save(b,legacy?READER_RC_HIGHLIGHT:READER_RC_PROGRESS,READER_RC_PUT,"",nullptr,legacy?"second pending forbidden":nullptr,nullptr,refused);expect(refused.status!=EXR_OK&&!refused.r.committed&&read(fs::path(b.pending))==original&&product_snapshot(b)==before,"Real pending retains exact original bytes and excludes new private save");
  Selected newer;std::string original_wire;
  if(phase==2){Revisions store(b.database);char *bytes=nullptr;size_t size=0;reader_revision_info info{};auto st=reader_revision_get(store.p,rid.c_str(),&bytes,&size,&info,nullptr);expect(st==READER_REV_NOT_FOUND&&!bytes&&!size,"Before-commit real kill retained no committed request RID");reader_revision_bytes_free(bytes);}
  if(phase==3){auto current=selected(b,true);require(current.status==READER_REV_OK&&rid==current.info.revision_id,"After-commit killed process retained actual durable RID");original_wire=current.bytes;newer_progress(b,current);newer=selected(b,true);require(newer.status==READER_REV_OK&&rid!=newer.info.revision_id,"Newer actual head selected before retry");before=product_snapshot(b);}
  auto req=b.request(WINRECORDS_RETRY);Response out;invoke(req,out);succeeded(out,"Retry actual killed-process request");expect(out.r.committed&&out.r.created==(phase==2?1:0)&&rid==out.r.saved_revision&&!fs::exists(fs::path(b.pending)),phase==2?"Before-commit kill exact retry commits once and clears only original pending":"After-commit kill exact retry created0 and clears only original pending");
  if(phase==3){auto after=selected(b,true);expect(after.bytes==newer.bytes&&product_snapshot(b)==before&&retained(b,rid)==original_wire,"Retained RID retry after receiving newer head neither rolls back head nor rewrites/requeues bytes");}
  auto retained_wire=retained(b,rid);Decoded decoded;decode(b,retained_wire,decoded);expect(decoded.r.anchor_version==(legacy?2u:3u),"Retry preserves original explicit writer version");
  read_found(b,!legacy,legacy?decoded.r.annotation_id:"",legacy?2:3,legacy?"Legacy OFF to raw retry":"Kill-boundary fresh owner");
  write(work/"committed-request-wire.json",retained_wire);
}
#endif
std::string report(const fs::path &work){
  bool ok=!checks.empty();for(const auto &c:checks)ok&=c.pass;
  wchar_t executable[32768];DWORD n=GetModuleFileNameW(nullptr,executable,32768);std::string exe_hash=n&&n<32768?sha(read(fs::path(std::wstring(executable,n)))):"unavailable";
  std::ostringstream s;s<<"{\"ok\":"<<(ok?"true":"false")<<",\"mode\":"<<quote(current_mode)<<",\"source_sha\":"<<quote(PROBE_SOURCE_SHA)<<",\"owner_source_sha256\":"<<quote(PROBE_OWNER_SHA)<<",\"sdk_version\":"<<quote(exr_version())<<",\"program_sha256\":"<<quote(exe_hash)<<",\"pid\":"<<GetCurrentProcessId()<<",\"scope\":\"actual Win32 records owner and installed modules only\",\"host_ui_accepted\":false,\"same_source_bidirectional\":false,\"profile\":";
#ifdef EXR_READER_WINDOWS_RAW3
  s<<"\"raw3\"";
#else
  s<<"\"legacy\"";
#endif
  s<<",\"versions\":{\"revisions\":"<<quote(READER_REVISIONS_VERSION)<<",\"commands\":"<<quote(READER_COMMANDS_VERSION)<<",\"metadata\":"<<quote(READER_METADATA_VERSION)<<",\"reading_state\":"<<quote(READER_READING_STATE_VERSION)<<",\"reading_commands\":"<<quote(READER_READING_COMMANDS_VERSION)<<",\"annotation_view\":"<<quote(READER_ANNOTATION_VIEW_VERSION)<<",\"sync\":"<<quote(READER_SYNC_VERSION)<<",\"session\":"<<quote(READER_SESSION_VERSION)<<"},\"checks\":[";
  for(size_t i=0;i<checks.size();i++){if(i)s<<',';const auto &c=checks[i];s<<"{\"name\":"<<quote(c.name)<<",\"pass\":"<<(c.pass?"true":"false")<<",\"detail\":"<<quote(c.detail)<<'}';}s<<"]}";fs::create_directories(work);write(work/("report-"+current_mode+".json"),s.str()+"\n");return s.str();
}
}
int main(int argc,char **argv){
  if(argc<4){std::cerr<<"usage: windows-owner-probe MODE WORK-DIR REAL-NUL-PDF [PHASE MARKER]\n";return 2;}
  current_mode=argv[1];fs::path work=fs::u8path(argv[2]),pdf=fs::u8path(argv[3]);
  try{
    require(std::getenv("GITHUB_ACTIONS")&&std::string(std::getenv("GITHUB_ACTIONS"))=="true","Actions-only execution");require(!std::strcmp(exr_version(),"3.41.0"),"Exact installed SDK3.41.0");
    if(current_mode=="suite"){
      group("actual fixed owner",[&]{fixed_suite(work,pdf);});group("compatibility sources",[&]{compatibility(work,pdf);});
#ifdef EXR_READER_WINDOWS_RAW3
      group("parser admission",[&]{parser_suite(work,pdf);});group("explicit NULL transport",[&]{null_suite(work,pdf);});
#endif
    }else if(current_mode=="fresh"){group("fresh-process read",[&]{fresh(work,pdf);});}
    else if(current_mode=="child"){require(argc==6,"child requires PHASE MARKER");child(work,pdf,std::stoi(argv[4]),fs::u8path(argv[5]),false);}
    else if(current_mode=="legacy-child"){require(argc==5,"legacy-child requires MARKER");child(work,pdf,2,fs::u8path(argv[4]),true);}
    else if(current_mode=="reject-private"){reject_pending(work,pdf,false);}
    else if(current_mode=="reject-legacy-private"){reject_pending(work,pdf,true);}
#ifdef EXR_READER_WINDOWS_RAW3
    else if(current_mode=="verify-child"){require(argc==5,"verify-child requires PHASE");verify_child(work,pdf,std::stoi(argv[4]),false);}
    else if(current_mode=="legacy-retry"){verify_child(work,pdf,2,true);}
#endif
    else throw std::runtime_error("Unknown mode or unsupported profile: "+current_mode);
  }catch(const std::exception &e){expect(false,"uncaught probe failure",e.what());}
  try{std::cout<<report(work)<<std::endl;}catch(const std::exception &e){std::cerr<<e.what()<<std::endl;return 1;}
  bool ok=!checks.empty();for(const auto &c:checks)ok&=c.pass;return ok?0:1;
}
