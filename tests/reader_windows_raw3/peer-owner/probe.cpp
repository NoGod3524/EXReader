/* SPDX-License-Identifier: MIT
 * Read an existing actual GUI receiver profile. No import, attach, receive or save.
 */
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <bcrypt.h>
#include "windows_records_owner.h"
#include "windows_raw3_apis.h"
#include <catalog.h>
#include <exreader.h>
#include <sqlite3.h>
#include <algorithm>
#include <array>
#include <climits>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
namespace fs = std::filesystem;
namespace {
void need(bool ok,const std::string &why){if(!ok)throw std::runtime_error(why);}
std::string read(const fs::path &p){std::ifstream f(p,std::ios::binary);need(bool(f),"read: "+p.u8string());std::ostringstream s;s<<f.rdbuf();return s.str();}
std::string quote(const std::string &v){std::string s="\"";const char *h="0123456789abcdef";for(unsigned char c:v){if(c=='"'||c=='\\'){s+='\\';s+=char(c);}else if(c<32){s+="\\u00";s+=h[c>>4];s+=h[c&15];}else s+=char(c);}return s+'"';}
std::string sha(const std::string &v){need(v.size()<=ULONG_MAX,"bounded hash");BCRYPT_ALG_HANDLE a=nullptr;std::array<unsigned char,32>d{};need(BCryptOpenAlgorithmProvider(&a,BCRYPT_SHA256_ALGORITHM,nullptr,0)>=0,"hash open");auto s=BCryptHash(a,nullptr,0,(PUCHAR)v.data(),(ULONG)v.size(),d.data(),(ULONG)d.size());BCryptCloseAlgorithmProvider(a,0);need(s>=0,"hash bytes");std::string r;const char *h="0123456789abcdef";for(auto c:d){r+=h[c>>4];r+=h[c&15];}return r;}
struct Field {bool present=false;std::string bytes;};
Field text(const char *p){return {p!=nullptr,p?std::string(p):std::string()};}
Field blob(const char *p,size_t n){need(p||!n,"NULL with nonzero length");return {p!=nullptr,p?std::string(p,n):std::string()};}
bool operator==(const Field &a,const Field &b){return a.present==b.present&&a.bytes==b.bytes;}
std::string serialized(const Field &f){return f.present?std::to_string(f.bytes.size())+":"+f.bytes:"NULL;";}
struct Input {
 std::string bytes;size_t at=8;
 explicit Input(const fs::path &p):bytes(read(p)){need(bytes.size()<=4*1024*1024&&bytes.substr(0,8)=="EXRPEER1","bounded expected frame");}
 uint64_t number(unsigned n=8){need(at<=bytes.size()&&n<=bytes.size()-at,"truncated expected frame");uint64_t v=0;for(unsigned i=0;i<n;i++)v|=uint64_t((unsigned char)bytes[at++])<<(8*i);return v;}
 Field field(){auto n=number(4);if(n==0xffffffff)return {};need(n<=262144&&n<=bytes.size()-at,"bounded expected field");Field f{true,bytes.substr(at,(size_t)n)};at+=(size_t)n;return f;}
 std::string string(){auto f=field();need(f.present&&f.bytes.find('\0')==std::string::npos,"required expected text");return f.bytes;}
};
bool hex(const std::string &s,size_t n){return s.size()==n&&s.find_first_not_of("0123456789abcdef")==std::string::npos;}
struct Book {std::string key,format,hash;uint64_t bytes=0;int64_t id=0;};
struct Wire {std::string id,hash;uint64_t bytes=0;};
struct Expected {std::string id,role,kind;uint64_t version=0;std::array<uint64_t,4> numbers{};std::array<Field,5> route{};std::array<Field,3> selectors{};};
struct Capture {reader_rs_capture c{};exr_anchor a{};exr_fixed_anchor f{};size_t part=0;~Capture(){exr_anchor_free(&a);exr_fixed_anchor_free(&f);}};
struct Library {exr_library *p=nullptr;explicit Library(const fs::path &path){need(fs::is_regular_file(path),"existing GUI SDK required");exr_error e{};need(exr_library_open(path.u8string().c_str(),&p,&e)==EXR_OK,e.message);}~Library(){exr_library_close(p);}};
struct Source {exr_source s{};~Source(){if(s.release)s.release(s.context);}};
struct Objects {exr_document *doc=nullptr;exr_publication *pub=nullptr;exr_pager *pager=nullptr;exr_fixed_document *fixed=nullptr;exr_fixed_text *page=nullptr;~Objects(){exr_fixed_text_free(page);exr_fixed_free(fixed);exr_pager_free(pager);exr_publication_free(pub);exr_document_free(doc);}};
struct Product {reader_catalog *catalog=nullptr;reader_revisions *revisions=nullptr;explicit Product(const fs::path &p){need(fs::is_regular_file(p),"existing GUI product required");need(reader_catalog_open(p.u8string().c_str(),&catalog,nullptr)==0,"open catalog");need(reader_revisions_open(p.u8string().c_str(),&revisions,nullptr)==READER_REV_OK,"open raw history");}~Product(){reader_revisions_close(&revisions,nullptr);reader_catalog_close(&catalog,nullptr);}};
struct Response {winrecords_response r{};~Response(){winrecords_response_free(&r);}};
struct Context {fs::path sdk;Book book;exr_font *font=nullptr;unsigned calls=0,found=0;std::string error;};
exr_status capture(void *opaque,const reader_rs_record *r,reader_rs_capture *c,exr_anchor *a,exr_fixed_anchor *f,size_t *part){
 auto &ctx=*static_cast<Context *>(opaque);++ctx.calls;*c={};*a={};*f={};*part=0;
 try {
  need(r&&r->has_location&&r->exact,"NULL/absent selector never authorizes FOUND");
  need(r->start<=SIZE_MAX&&r->end<=SIZE_MAX&&r->start<=r->end&&r->end-r->start==r->exact_size,"bounded exact selector");
  Library sdk(ctx.sdk);Objects o;exr_error e{};exr_anchor_match match{};
  if(r->mode==READER_RS_FIXED_PAGE){
   need(ctx.book.format=="pdf"||ctx.book.format=="cbz","fixed format");
   need(exr_library_fixed_source(sdk.p,ctx.book.id,nullptr,&o.fixed,&e)==EXR_OK,e.message);
   size_t count=0,hits=0,page=SIZE_MAX;auto pages=exr_fixed_pages(o.fixed,&count);
   for(size_t i=0;i<count;i++)if(r->page_id&&pages[i].id&&!std::strcmp(r->page_id,pages[i].id)){++hits;page=i;}
   need(hits==1&&page==r->page,"unique page ID and actual page hint");
   need(exr_fixed_load_text(o.fixed,page,nullptr,&o.page,&e)==EXR_OK,e.message);
   exr_fixed_anchor old{};old.start=(size_t)r->start;old.end=(size_t)r->end;old.page_id=r->page_id;
   old.exact=r->exact;old.prefix=r->prefix;old.suffix=r->suffix;old.exact_size=r->exact_size;old.prefix_size=r->prefix_size;old.suffix_size=r->suffix_size;
   need(exr_fixed_anchor_resolve(pages[page].id,o.page,&old,nullptr,&match,&e)==EXR_OK,e.message);
   need(match.state==EXR_ANCHOR_FOUND,"public fixed resolve did not return FOUND");
   need(exr_fixed_anchor_create(pages[page].id,o.page,match.start,match.end,f,&e)==EXR_OK,e.message);
   c->mode=READER_RS_FIXED_PAGE;c->fixed=f;c->page=page;
  }else{
   exr_anchor old{};old.start=(size_t)r->start;old.end=(size_t)r->end;old.exact=r->exact;old.prefix=r->prefix;old.suffix=r->suffix;
   if(r->mode==READER_RS_EPUB_CHAPTER){
    need(ctx.book.format=="epub"&&r->part_path,"EPUB route");Source source;
    need(exr_library_source(sdk.p,ctx.book.id,&source.s,&e)==EXR_OK,e.message);
    need(exr_publication_open_source(&source.s,&o.pub,&e)==EXR_OK,e.message);source.s.release=nullptr;
    size_t n=0;auto parts=exr_publication_parts(o.pub,&n);need(r->part<n&&parts[r->part].path&&!std::strcmp(parts[r->part].path,r->part_path),"actual spine index/path");
    *part=(size_t)r->part;old.chapter=r->part_path;auto config=exr_layout_config_defaults();auto options=exr_chapter_options_defaults();
    options.workspace_budget=8*1024*1024;options.window_bytes=64*1024;
    need(exr_publication_pager_create(o.pub,*part,ctx.font,&config,&options,&o.pager,&e)==EXR_OK,e.message);
    need(exr_pager_anchor_resolve(o.pager,&old,nullptr,&match,&e)==EXR_OK,e.message);
    need(match.state==EXR_ANCHOR_FOUND,"public EPUB resolve did not return FOUND");
    need(exr_pager_anchor_create(o.pager,match.start,match.end,nullptr,a,&e)==EXR_OK,e.message);
    c->mode=READER_RS_EPUB_CHAPTER;c->part_path=r->part_path;
   }else{
    need(ctx.book.format=="txt"&&r->mode==READER_RS_REFLOW_GLOBAL,"TXT reflow route");old.chapter=r->chapter;
    need(exr_library_document(sdk.p,ctx.book.id,&o.doc,&e)==EXR_OK,e.message);
    need(exr_anchor_resolve_ex(o.doc,&old,nullptr,&match,&e)==EXR_OK,e.message);
    need(match.state==EXR_ANCHOR_FOUND,"public TXT resolve did not return FOUND");
    need(exr_anchor_create(o.doc,match.start,match.end,a,&e)==EXR_OK,e.message);c->mode=READER_RS_REFLOW_GLOBAL;
   }
   c->anchor=a;
  }
  ++ctx.found;return EXR_OK;
 }catch(const std::exception &e){ctx.error=e.what();return EXR_ARGUMENT;}
}
int book_row(void *p,const reader_catalog_row *row){auto &b=*static_cast<Book *>(p);if(!row||row->deleted||!row->book_key||b.key!=row->book_key||!row->format||b.format!=row->format||row->source_bytes!=b.bytes||row->sdk_book_id<=0)return 1;b.id=row->sdk_book_id;return 0;}
void append(std::string &s,const char *p){s+=serialized(text(p));}
void anchor_state(std::string &s,const exr_anchor &a){s+=std::to_string(a.start)+":"+std::to_string(a.end)+":";for(auto p:{a.exact,a.prefix,a.suffix,a.chapter})append(s,p);}
std::string sdk_state(const fs::path &path){
 Library sdk(path);exr_error e{};exr_book *rows=nullptr;size_t count=0;need(exr_library_books(sdk.p,nullptr,&rows,&count,&e)==EXR_OK,e.message);std::string state;
 for(size_t i=0;i<count;i++){
  auto &b=rows[i];state+=std::to_string(b.id)+":"+std::to_string(b.format)+":"+std::to_string(b.position)+":"+std::to_string(b.status)+":"+std::to_string(b.favorite)+":";
  append(state,b.title);append(state,b.author);append(state,b.tags);
  if(b.format==EXR_PDF||b.format==EXR_CBZ){
   exr_fixed_note *notes=nullptr;size_t n=0;need(exr_library_fixed_notes(sdk.p,b.id,&notes,&n,&e)==EXR_OK,e.message);
   state+="fixed:"+std::to_string(n)+":";for(size_t j=0;j<n;j++){auto &x=notes[j];state+=std::to_string(x.id)+":"+std::to_string(x.page)+":"+std::to_string(x.start)+":"+std::to_string(x.end)+":";append(state,x.text);append(state,x.anchor.page_id);state+=serialized(blob(x.anchor.exact,x.anchor.exact_size))+serialized(blob(x.anchor.prefix,x.anchor.prefix_size))+serialized(blob(x.anchor.suffix,x.anchor.suffix_size));}exr_fixed_notes_free(notes,n);
  }else{
   exr_library_epub_info info{};info.struct_size=sizeof(info);bool bounded=false;
   if(b.format==EXR_EPUB){need(exr_library_epub_info_get(sdk.p,b.id,&info,&e)==EXR_OK,e.message);bounded=info.bounded_storage!=0;}
   if(bounded){
    exr_epub_location progress{};int present=0;need(exr_library_epub_progress_get(sdk.p,b.id,&progress,&present,&e)==EXR_OK,e.message);state+="epub-progress:"+std::to_string(present)+":"+std::to_string(progress.part)+":";append(state,progress.path);anchor_state(state,progress.selector);exr_epub_location_free(&progress);
    exr_epub_note *notes=nullptr;size_t n=0;need(exr_library_epub_notes(sdk.p,b.id,&notes,&n,&e)==EXR_OK,e.message);state+="epub-notes:"+std::to_string(n)+":";for(size_t j=0;j<n;j++){auto &x=notes[j];state+=std::to_string(x.id)+":"+std::to_string(x.location.part)+":";append(state,x.text);append(state,x.location.path);anchor_state(state,x.location.selector);}exr_epub_notes_free(notes,n);
   }else{
    exr_anchor progress{};exr_anchor_state match{};need(exr_library_progress_get(sdk.p,b.id,&progress,&match,&e)==EXR_OK,e.message);state+="global-progress:"+std::to_string(match)+":";anchor_state(state,progress);exr_anchor_free(&progress);
    exr_note *notes=nullptr;size_t n=0;need(exr_library_notes(sdk.p,b.id,&notes,&n,&e)==EXR_OK,e.message);state+="global-notes:"+std::to_string(n)+":";for(size_t j=0;j<n;j++){auto &x=notes[j];state+=std::to_string(x.id)+":"+std::to_string(x.start)+":"+std::to_string(x.end)+":";append(state,x.text);anchor_state(state,x.anchor);}exr_notes_free(notes,n);
   }
  }
 }exr_books_free(rows,count);return sha(state);
}
/* Product DB only. The SDK is observed exclusively through public APIs above. */
std::string product_state(const fs::path &path){
 sqlite3 *db=nullptr;need(sqlite3_open_v2(path.u8string().c_str(),&db,SQLITE_OPEN_READONLY,nullptr)==SQLITE_OK,"read-only product snapshot");sqlite3_stmt *q=nullptr;std::vector<std::string> tables;std::string state;
 need(sqlite3_prepare_v2(db,"SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name",-1,&q,nullptr)==SQLITE_OK,"product tables");
 while(sqlite3_step(q)==SQLITE_ROW)tables.emplace_back((const char *)sqlite3_column_text(q,0));sqlite3_finalize(q);
 for(const auto &table:tables){need(table.find('"')==std::string::npos,"known product table name");auto sql="SELECT * FROM \""+table+"\" ORDER BY rowid";need(sqlite3_prepare_v2(db,sql.c_str(),-1,&q,nullptr)==SQLITE_OK,"product row snapshot");state+=table+'\n';int rc;
  while((rc=sqlite3_step(q))==SQLITE_ROW){for(int i=0;i<sqlite3_column_count(q);i++){int n=sqlite3_column_bytes(q,i);auto p=sqlite3_column_blob(q,i);state+=std::to_string(sqlite3_column_type(q,i))+":"+std::to_string(n)+":";if(n)state.append((const char *)p,(size_t)n);state+='|';}state+='\n';}need(rc==SQLITE_DONE,"product rows complete");sqlite3_finalize(q);
 }sqlite3_close(db);return sha(state);
}
std::string originals(exr_library *sdk,const std::vector<Book> &books,const fs::path &packet){
 exr_book *rows=nullptr;size_t count=0;need(exr_library_books(sdk,nullptr,&rows,&count,nullptr)==EXR_OK,"public SDK original metadata");std::map<int64_t,exr_format> formats;for(size_t i=0;i<count;i++)formats.emplace(rows[i].id,rows[i].format);exr_books_free(rows,count);
 std::string all;for(const auto &b:books){auto expected_format=b.format=="pdf"?EXR_PDF:b.format=="cbz"?EXR_CBZ:b.format=="epub"?EXR_EPUB:EXR_TXT;need(formats.count(b.id)&&formats.at(b.id)==expected_format,"actual SDK book format matches source identity");Source source;need(exr_library_source(sdk,b.id,&source.s,nullptr)==EXR_OK&&source.s.size==b.bytes&&b.bytes<=128*1024*1024,"existing actual SDK original source");std::string data((size_t)b.bytes,'\0');size_t at=0;while(at<data.size()){size_t request=std::min<size_t>(65536,data.size()-at);size_t n=source.s.read_at(source.s.context,at,&data[at],request);need(n&&n<=request,"actual original short read");at+=n;}auto peer=read(packet/(b.hash+'.'+b.format));need(data==peer&&sha(data)==b.hash,"actual stored original differs from authenticated peer");all+=b.key+":"+sha(data)+';';}return sha(all);
}
void transport_equal(const reader_rs_record &r,const Expected &x){
 std::array<uint64_t,4> n={uint64_t(r.mode),r.mode==READER_RS_FIXED_PAGE?r.page:r.mode==READER_RS_EPUB_CHAPTER?r.part:0,r.start,r.end};
 std::array<Field,5> route={text(r.book_key),text(r.parser_version),text(r.part_path),text(r.page_id),text(r.chapter)};
 std::array<Field,3> selectors={blob(r.exact,r.exact_size),blob(r.prefix,r.prefix_size),blob(r.suffix,r.suffix_size)};
 need(r.has_location&&r.anchor_version==x.version&&n==x.numbers&&route==x.route&&selectors==x.selectors,"owner READ differs from original manifest capture/NULL tags");
 need(!std::strcmp(r.operation,"put")||!std::strcmp(r.operation,"restore"),"positive capture needs live original wire");
 need(x.kind=="progress"?!std::strcmp(r.entity_kind,"progress"):!std::strcmp(r.entity_kind,"annotation"),"original record kind");
}
void fresh_equal(const Capture &fresh,const Expected &x){
 const bool fixed=fresh.c.mode==READER_RS_FIXED_PAGE;std::array<uint64_t,4> n={uint64_t(fresh.c.mode),fixed?fresh.c.page:fresh.c.mode==READER_RS_EPUB_CHAPTER?fresh.part:0,fixed?fresh.f.start:fresh.a.start,fixed?fresh.f.end:fresh.a.end};
 auto route=x.route;route[2]=text(fresh.c.part_path);route[3]=fixed?text(fresh.f.page_id):Field{};route[4]=fixed?Field{}:text(fresh.a.chapter);
 auto expected_route=x.route;
 // Exactly the existing Mac/Windows host reconstruction: transport chapter
 // remains NULL; the actual bounded SDK anchor is scoped by part_path.
 if(fresh.c.mode==READER_RS_EPUB_CHAPTER)expected_route[4]=x.route[2];
 std::array<Field,3> selectors=fixed?std::array<Field,3>{blob(fresh.f.exact,fresh.f.exact_size),blob(fresh.f.prefix,fresh.f.prefix_size),blob(fresh.f.suffix,fresh.f.suffix_size)}:std::array<Field,3>{text(fresh.a.exact),text(fresh.a.prefix),text(fresh.a.suffix)};
 need(n==x.numbers&&route==expected_route&&selectors==x.selectors,"real public recapture differs byte-for-byte from host-reconstructed manifest capture");
}
}
int main(int argc,char **argv){
 if(argc!=6){std::cerr<<"usage: windows-peer-owner PROFILE PACKET EXPECTED.bin FONT OUTPUT.json\n";return 2;}
 fs::path profile=fs::u8path(argv[1]),packet=fs::u8path(argv[2]),expected=fs::u8path(argv[3]),fontfile=fs::u8path(argv[4]),output=fs::u8path(argv[5]);
 std::vector<std::string> reports;bool ok=false;std::string failure,before_product,after_product,before_sdk,after_sdk,expected_sha;
 exr_font *font=nullptr;
 try{
  need(std::getenv("GITHUB_ACTIONS")&&std::string(std::getenv("GITHUB_ACTIONS"))=="true","Windows Actions only");need(std::getenv("GITHUB_SHA")&&std::string(std::getenv("GITHUB_SHA"))==PROBE_SOURCE_SHA,"actual Actions source equals compiled consumer");need(!std::strcmp(exr_version(),"3.41.0")&&READER_REVISION_ANCHOR_MAX_VERSION==2,"frozen SDK/MAX2");
  const auto sdk=profile/"library.sqlite",database=profile/"library.sqlite.product.sqlite";const auto pending=fs::path(database.wstring()+L".reading.pending");
  need(fs::is_regular_file(sdk)&&fs::is_regular_file(database),"existing GUI receive profile, no bootstrap permitted");
  Input input(expected);expected_sha=sha(input.bytes);auto manifest_sha=input.string();need(manifest_sha=="f0960b35374e12827a8966f7022dc3f632e44c87419ca1482288386fb8031566"&&sha(read(packet/"manifest.json"))==manifest_sha,"fixed original Mac manifest");
  need(input.number()==4,"exact four originals");std::vector<Book> books;std::set<std::string> formats;
  for(unsigned i=0;i<4;i++){Book b;b.key=input.string();b.format=input.string();b.hash=input.string();b.bytes=input.number();need(hex(b.hash,64)&&b.key==b.format+":"+b.hash&&b.bytes>0,"original identity");formats.insert(b.format);books.push_back(b);}need(formats==std::set<std::string>{"txt","epub","pdf","cbz"},"exact four formats");
  need(input.number()==15,"exact fifteen original wires");std::vector<Wire> wires;std::set<std::string> ids;
  for(unsigned i=0;i<15;i++){Wire w;w.id=input.string();w.hash=input.string();w.bytes=input.number();need(hex(w.id,32)&&hex(w.hash,64)&&w.bytes>0&&w.bytes<=1048576&&ids.insert(w.id).second,"wire identity");wires.push_back(w);}
  need(input.number()==11,"exact eleven capture records");std::vector<Expected> records;ids.clear();
  for(unsigned i=0;i<11;i++){Expected x;x.id=input.string();x.role=input.string();x.kind=input.string();x.version=input.number();for(auto &n:x.numbers)n=input.number();for(auto &f:x.route)f=input.field();for(auto &f:x.selectors)f=input.field();need(hex(x.id,32)&&ids.insert(x.id).second&&x.selectors[0].present,"unique actual selector; NULL never counts as FOUND");records.push_back(x);}need(input.at==input.bytes.size(),"no trailing expected bytes");
  before_product=product_state(database);before_sdk=sdk_state(sdk);
  Product product(database);for(auto &b:books){int found=0;need(reader_catalog_metadata(product.catalog,b.key.c_str(),book_row,&b,&found,nullptr)==0&&found&&b.id>0,"actual GUI local mapping");}
  Library original_sdk(sdk);auto before_originals=originals(original_sdk.p,books,packet);
  for(const auto &w:wires){char *bytes=nullptr;size_t n=0;reader_revision_info info{};auto status=reader_revision_get(product.revisions,w.id.c_str(),&bytes,&n,&info,nullptr);std::string got=bytes?std::string(bytes,n):std::string();reader_revision_bytes_free(bytes);need(status==READER_REV_OK&&n==w.bytes&&sha(got)==w.hash&&got==read(packet/(w.id+".json")),"actual GUI-retained original wire identity");}
  need(exr_font_open(fontfile.u8string().c_str(),&font,nullptr)==EXR_OK,"actual installed test font");
  for(const auto &x:records){
   auto bi=std::find_if(books.begin(),books.end(),[&](const Book &b){return x.route[0].present&&b.key==x.route[0].bytes;});need(bi!=books.end(),"capture original book mapping");
   const auto wi=std::find_if(wires.begin(),wires.end(),[&](const Wire &w){return w.id==x.id;});need(wi!=wires.end(),"capture original revision present");
   char *wire=nullptr;size_t n=0;reader_revision_info info{};need(reader_revision_get(product.revisions,x.id.c_str(),&wire,&n,&info,nullptr)==READER_REV_OK,"actual retained record");reader_rs_record decoded{};auto status=reader_rs_decode(product.revisions,wire,n,&decoded,nullptr);reader_revision_bytes_free(wire);need(status==READER_RS_OK,"decode annotation identity");std::string annotation=decoded.annotation_id;reader_rs_record_free(&decoded);
   Context context;context.sdk=sdk;context.book=*bi;context.font=font;winrecords_request request{};auto db=database.u8string();auto pending_w=pending.wstring();request.database=db.c_str();request.pending_path=pending_w.c_str();request.book_key=bi->key.c_str();request.sdk_book=bi->id;request.source_bytes=bi->bytes;request.action=WINRECORDS_READ;request.progress_target=x.kind=="progress";request.annotation_id=annotation.c_str();request.head=x.id.c_str();request.sha256=wi->hash.c_str();request.context=&context;request.capture=capture;
   Response response;need(winrecords_execute(&request,&response.r)==EXR_OK,std::string("actual owner READ: ")+response.r.message);need(context.calls==0,"READ is decode-only; never self-reported as FOUND");transport_equal(response.r.record,x);
   Capture fresh;auto resolved=request.capture(request.context,&response.r.record,&fresh.c,&fresh.a,&fresh.f,&fresh.part);need(resolved==EXR_OK,"independent SDK callback: "+context.error);need(context.calls==1&&context.found==1,"exact one independent public FOUND");fresh_equal(fresh,x);
   Context rejected;rejected.sdk=sdk;rejected.book=*bi;rejected.font=font;auto null_record=response.r.record;null_record.exact=nullptr;null_record.exact_size=0;Capture null_capture;
   need(capture(&rejected,&null_record,&null_capture.c,&null_capture.a,&null_capture.f,&null_capture.part)!=EXR_OK&&rejected.calls==1&&rejected.found==0,"NULL callback negative must never claim FOUND");
   std::ostringstream row;row<<"{\"revision_id\":"<<quote(x.id)<<",\"book_key\":"<<quote(bi->key)<<",\"role\":"<<quote(x.role)<<",\"kind\":"<<quote(x.kind)<<",\"wire_sha256\":"<<quote(wi->hash)<<",\"actual_owner_READ\":true,\"owner_READ_callback_calls\":0,\"independent_sdk_callback_calls\":1,\"found\":true,\"retained_manifest_capture_equal\":true,\"fresh_capture_equal\":true,\"NULL_callback_negative_refused\":true,\"epub_chapter_reconstructed_from_part_path\":"<<(x.numbers[0]==2?"true":"false")<<"}";reports.push_back(row.str());
  }
  need(originals(original_sdk.p,books,packet)==before_originals,"stored original bytes unchanged after all resolve/capture");after_product=product_state(database);after_sdk=sdk_state(sdk);need(before_product==after_product&&before_sdk==after_sdk,"SDK progress/notes or product rows/history/outbox changed");need(reports.size()==11,"all eleven real captures completed");ok=true;
 }catch(const std::exception &e){failure=e.what();}
 exr_font_free(font);
 wchar_t executable[32768];auto size=GetModuleFileNameW(nullptr,executable,32768);std::string program="unavailable";try{need(size&&size<32768,"consumer path");program=sha(read(fs::path(std::wstring(executable,size))));}catch(...){ok=false;failure+="; consumer executable identity unavailable";}
 std::ostringstream report;report<<"{\"accepted\":"<<(ok?"true":"false")<<",\"source_sha\":"<<quote(PROBE_SOURCE_SHA)<<",\"owner_source_sha256\":"<<quote(PROBE_OWNER_SHA)<<",\"program_sha256\":"<<quote(program)<<",\"pid\":"<<GetCurrentProcessId()<<",\"run_id\":"<<quote(std::getenv("GITHUB_RUN_ID")?std::getenv("GITHUB_RUN_ID"):"")<<",\"attempt\":"<<quote(std::getenv("GITHUB_RUN_ATTEMPT")?std::getenv("GITHUB_RUN_ATTEMPT"):"")<<",\"sdk_version\":"<<quote(exr_version())<<",\"manifest_sha256\":\"f0960b35374e12827a8966f7022dc3f632e44c87419ca1482288386fb8031566\",\"expected_sha256\":"<<quote(expected_sha)<<",\"actual_owner_reads_and_FOUND\":"<<reports.size()<<",\"product_before\":"<<quote(before_product)<<",\"product_after\":"<<quote(after_product)<<",\"sdk_before\":"<<quote(before_sdk)<<",\"sdk_after\":"<<quote(after_sdk)<<",\"failure\":"<<quote(failure)<<",\"same_source_bidirectional\":false,\"host_ui_accepted\":false,\"complete_product\":false,\"records\":[";
 for(size_t i=0;i<reports.size();i++){if(i)report<<',';report<<reports[i];}report<<"]}\n";
 try{std::ofstream stream(output,std::ios::binary);stream<<report.str();stream.flush();need(bool(stream),"write report");std::cout<<report.str();}catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}return ok?0:1;
}
