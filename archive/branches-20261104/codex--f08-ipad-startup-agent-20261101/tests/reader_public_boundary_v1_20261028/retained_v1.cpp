/* SPDX-License-Identifier: MIT */
#include <reader_reading_state_retained_raw_v1.h>
#include <reader_selector_bytes_v1.h>
#if defined(EXR_READER_PURE_CAPTURE_CANDIDATE) && EXR_READER_PURE_CAPTURE_CANDIDATE == 1
#include <reader_reading_state_capture_raw_candidate.h>
#endif
#include <exreader.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <new>
#include <stdexcept>
#include <string>
static int allocation_fault;
void *operator new(std::size_t n){
  if(allocation_fault){const int fault=allocation_fault;allocation_fault=0;if(fault==1)throw std::bad_alloc();throw 7;}
  if(void *p=std::malloc(n?n:1)){return p;}
  throw std::bad_alloc();
}
void operator delete(void *p) noexcept {std::free(p);}
void operator delete(void *p,std::size_t) noexcept {std::free(p);}
namespace fs=std::filesystem;
static unsigned checks;
static void check(bool ok,const char *what){++checks;if(!ok)throw std::runtime_error(what);std::cout<<"PASS "<<what<<'\n';}
static std::string read(const fs::path &path){std::ifstream f(path,std::ios::binary);check(bool(f),"fixture open");return {std::istreambuf_iterator<char>(f),{}};}
static void write(const fs::path &path,const std::string &value){std::ofstream f(path,std::ios::binary);f.write(value.data(),static_cast<std::streamsize>(value.size()));check(bool(f),"wire evidence saved");}
static std::string book(const char *format,const char *key){
#ifdef _WIN32
  char sha[65]{};size_t count=0;check(getenv_s(&count,sha,sizeof(sha),key)==0&&count==65,"actual fixture SHA supplied");
#else
  const char *sha=std::getenv(key);check(sha&&std::strlen(sha)==64,"actual fixture SHA supplied");
#endif
  return std::string(format)+":"+sha;
}
static std::string encode(reader_revisions *store,const reader_rs_envelope &env,const reader_rs_capture &capture,unsigned version,size_t part){
  char *wire=nullptr;size_t count=0;reader_rs_error error{};
  check(reader_rs_encode_retained_raw_v1(store,&env,&capture,version,part,&wire,&count,&error)==READER_RS_OK,error.message);
  std::string value(wire,count);reader_rs_free(wire);
#if defined(EXR_READER_PURE_CAPTURE_CANDIDATE) && EXR_READER_PURE_CAPTURE_CANDIDATE == 1
  check(reader_rs_encode_capture_raw_candidate(store,&env,&capture,version,part,&wire,&count,&error)==READER_RS_OK,error.message);
  check(value==std::string(wire,count),"existing optional pure API exact wire equivalence");reader_rs_free(wire);
#endif
  reader_rs_record record{};
  check(reader_rs_decode_raw_v3(store,value.data(),value.size(),&record,&error)==READER_RS_OK,error.message);
  check(record.anchor_version==version,"API revision independent of wire version");
  if(capture.mode==READER_RS_EPUB_CHAPTER&&version==2)check(record.part==part&&!std::strcmp(record.part_path,capture.part_path),"actual repeated EPUB spine index preserved");
  reader_rs_record_free(&record);return value;
}
static void invalid(reader_revisions *store,const reader_rs_envelope *env,const reader_rs_capture *capture,unsigned version){
  char *wire=reinterpret_cast<char *>(1);size_t size=999;reader_rs_error error{};
  check(reader_rs_encode_retained_raw_v1(store,env,capture,version,0,&wire,&size,&error)==READER_RS_ARGUMENT&&!wire&&!size,"invalid entry clears outputs");
}
static void no_writes(reader_revisions *store,const reader_rs_envelope &env){
  reader_revision_error error{};reader_revision_info info{};reader_revision_state state{};char *wire=nullptr;size_t size=0,rows=0;
  check(reader_revision_get_raw_v3(store,env.revision_id,&wire,&size,&info,&error)==READER_REV_NOT_FOUND&&!wire&&!size,"pure encoder did not insert revision");
  check(reader_revision_heads_raw_v3(store,env.entity_kind,env.book_key,[](void *p,const reader_revision_head *){++*static_cast<size_t *>(p);return 0;},&rows,&state,&error)==READER_REV_OK&&rows==0,"pure encoder did not add heads");
  check(reader_revision_outbox_raw_v3(store,100,[](void *p,const reader_revision_outbox_row *){++*static_cast<size_t *>(p);return 0;},&rows,&error)==READER_REV_OK&&rows==0,"pure encoder did not write outbox");
}
int main(int argc,char **argv){
  try {
    check(argc==5,"arguments: fixtures PDF font work");const fs::path fixtures=argv[1],pdfpath=argv[2],work=argv[4];fs::create_directories(work);
    check(!std::strcmp(READER_RS_RETAINED_RAW_API_VERSION,"1.0.0"),"public retained API version");
    // Deliberate test-process allocator failure, not an SDK/VFS/return shim.
    const std::string encoded(256,'A');char destination[192];std::memset(destination,'!',sizeof(destination));
    for(int fault:{1,2}){size_t count=9;allocation_fault=fault;auto status=reader_revision_selector_decode_v1(encoded.data(),encoded.size(),192,192,192,destination,sizeof(destination),&count);allocation_fault=0;
      check(status==READER_SELECTOR_V1_MEMORY&&count==0&&destination[0]=='!',"allocation/unexpected exception does not cross public C boundary");}
    reader_revisions *raw=nullptr,*legacy=nullptr;reader_revision_error re{};
    check(reader_revisions_open_raw_v3((work/"raw.sqlite").string().c_str(),&raw,&re)==READER_REV_OK,re.message);
    check(reader_revisions_open((work/"legacy.sqlite").string().c_str(),&legacy,&re)==READER_REV_OK,re.message);
    reader_rs_envelope env{};env.revision_id="00000000000000000000000000000001";env.operation="put";env.entity_kind="progress";env.parser_version=exr_version();
    auto text=read(fixtures/"book.txt");auto key=book("txt","BOUNDARY_TXT_SHA");env.book_key=key.c_str();exr_error se{};exr_document *doc=nullptr;exr_anchor anchor{};
    check(exr_document_open_memory(EXR_TXT,text.data(),text.size(),&doc,&se)==EXR_OK,se.message);
    check(exr_anchor_create(doc,0,6,&anchor,&se)==EXR_OK,se.message);reader_rs_capture capture{};capture.mode=READER_RS_REFLOW_GLOBAL;capture.anchor=&anchor;
    for(unsigned version:{1u,2u}){
      if(version==2){
        char *rejected=reinterpret_cast<char *>(1);size_t rejected_size=9;reader_rs_error rejected_error{};
        check(reader_rs_encode_retained_raw_v1(raw,&env,&capture,2,0,&rejected,&rejected_size,&rejected_error)==READER_RS_REVISION&&!rejected&&!rejected_size,
              "v2 progress refuses a non-point selector without relaxing revision validation");
        exr_anchor_free(&anchor);check(exr_anchor_create(doc,0,0,&anchor,&se)==EXR_OK,se.message);
      }
      const auto value=encode(raw,env,capture,version,0);write(work/("wire-v"+std::to_string(version)+".json"),value);
      char *old=nullptr;size_t size=0;reader_rs_error error{};
      auto status=version==1?reader_rs_encode(legacy,&env,&capture,&old,&size,&error):reader_rs_encode_v2(legacy,&env,&capture,0,&old,&size,&error);
      check(status==READER_RS_OK,error.message);check(value==std::string(old,size),"legacy v1/v2 wire bytes unchanged");reader_rs_free(old);
    }
    invalid(raw,&env,&capture,0);invalid(raw,&env,&capture,4);invalid(raw,&env,&capture,3);invalid(raw,nullptr,&capture,1);invalid(raw,&env,nullptr,1);invalid(nullptr,&env,&capture,1);
    {char *wire=reinterpret_cast<char *>(1);size_t count=9;reader_rs_error error{};
      check(reader_rs_encode_retained_raw_v1(legacy,&env,&capture,1,0,&wire,&count,&error)!=READER_RS_OK&&!wire&&!count,"legacy store refused by raw public entry");}
    no_writes(raw,env);exr_anchor_free(&anchor);exr_document_free(doc);
    auto pdf=read(pdfpath);key=book("pdf","BOUNDARY_PDF_SHA");env.book_key=key.c_str();exr_fixed_document *fixed=nullptr;exr_fixed_text *fixed_text=nullptr;exr_fixed_anchor point{};
    check(exr_fixed_open_memory(EXR_PDF,pdf.data(),pdf.size(),nullptr,&fixed,&se)==EXR_OK,se.message);
    check(exr_fixed_load_text(fixed,0,nullptr,&fixed_text,&se)==EXR_OK,se.message);
    check(exr_fixed_anchor_create("page-1",fixed_text,0,0,&point,&se)==EXR_OK,se.message);
    check(std::memchr(point.suffix,0,point.suffix_size)!=nullptr,"real SDK PDF capture contains embedded NUL");
    capture={};capture.mode=READER_RS_FIXED_PAGE;capture.fixed=&point;write(work/"wire-v3.json",encode(raw,env,capture,3,0));no_writes(raw,env);
    exr_fixed_anchor_free(&point);exr_fixed_text_free(fixed_text);exr_fixed_free(fixed);
    auto epub=read(fixtures/"book.epub");key=book("epub","BOUNDARY_EPUB_SHA");env.book_key=key.c_str();exr_publication *publication=nullptr;exr_font *font=nullptr;
    check(exr_publication_open_memory(EXR_EPUB,epub.data(),epub.size(),&publication,&se)==EXR_OK,se.message);
    check(exr_font_open(argv[3],&font,&se)==EXR_OK,se.message);size_t parts_count=0;const exr_part *parts=exr_publication_parts(publication,&parts_count);
    check(parts_count==3&&!std::strcmp(parts[0].path,parts[2].path),"actual EPUB repeated spine fixture");
    for(size_t part=0;part<parts_count;++part){
      exr_pager *pager=nullptr;auto config=exr_layout_config_defaults();auto options=exr_chapter_options_defaults();
      check(exr_publication_pager_create(publication,part,font,&config,&options,&pager,&se)==EXR_OK,se.message);
      check(exr_pager_anchor_create(pager,0,0,nullptr,&anchor,&se)==EXR_OK,se.message);capture={};capture.mode=READER_RS_EPUB_CHAPTER;capture.anchor=&anchor;capture.part_path=parts[part].path;
      write(work/("wire-epub-"+std::to_string(part)+".json"),encode(raw,env,capture,2,part));exr_anchor_free(&anchor);exr_pager_free(pager);
    }
    no_writes(raw,env);exr_publication_free(publication);exr_font_free(font);reader_revisions_close(&raw,&re);reader_revisions_close(&legacy,&re);
    std::cout<<"PUBLIC_RETAINED_V1 checks="<<checks<<" passed=true\n";return 0;
  }catch(const std::exception &e){std::cerr<<"FAIL "<<e.what()<<'\n';return 1;}
}
