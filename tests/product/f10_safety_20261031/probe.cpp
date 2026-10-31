/* SPDX-License-Identifier: MIT
 * Test-only installed public raw API consumer. No source inclusion, SDK
 * imitation, private database mutation or production hooks. */
#include <reader_session.h>
#include <reader_revisions.h>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#ifndef EXR_READER_SELECTOR_BYTES_CANDIDATE
#error Expected installed raw candidate capability
#endif
namespace fs=std::filesystem;
struct owner {fs::path originals;};
static int original(void *p,const char *key,char *out,size_t n) {
  std::string k=key;auto colon=k.find(':');if(colon==std::string::npos)return 1;
  std::string v=(((owner*)p)->originals/(k.substr(colon+1)+"."+k.substr(0,colon))).u8string();
  if(v.size()>=n||!fs::exists(fs::u8path(v)))return 1;
  std::memcpy(out,v.c_str(),v.size()+1);return 0;
}
int main(int argc,char **argv) {try {
  if(argc!=7)return 2;
  std::string mode=argv[1];fs::path root=argv[2];
  std::string db=(root/"catalog.sqlite").u8string(),cache=(root/"cache").u8string(),orig=(root/"originals").u8string();
  if(mode=="seed"){
    std::ifstream f(argv[6],std::ios::binary);std::string wire((std::istreambuf_iterator<char>(f)),{});
    reader_revisions *r=nullptr;reader_revision_error e{};reader_revision_info i{};int made=0;
    int code=reader_revisions_open_raw_v3(db.c_str(),&r,&e);
    if(!code)code=reader_revision_local_raw_v3(r,wire.data(),wire.size(),&i,&made,&e);
    if(r)reader_revisions_close(&r,nullptr);
    std::cout<<"{\"seed\":"<<code<<",\"created\":"<<made<<"}"<<std::endl;return code?3:0;
  }
  exr_webdav_config dc{};dc.root_url=argv[3];dc.authorization=std::getenv("F10_AUTH");dc.timeout_ms=15000;
  if(mode=="session"){
    reader_session_config cfg{};cfg.product_path=db.c_str();cfg.private_directory=cache.c_str();cfg.original_directory=orig.c_str();cfg.account_id=argv[4];cfg.dav=dc;
    reader_session *s=nullptr;int code=reader_session_create_raw_v3(&cfg,&s);
    std::cout<<"{\"create\":"<<code<<"}"<<std::endl;if(code)return 3;
    std::string line;while(std::getline(std::cin,line)){
      if(line=="start")code=reader_session_start(s);
      else if(line=="cancel")code=reader_session_cancel(s);
      else if(line=="close")code=reader_session_request_close(s);
      else if(line=="destroy")code=reader_session_destroy(&s);
      else if(line!="observe")return 4;
      reader_session_snapshot v{};if(s)reader_session_observe(s,&v);
      std::cout<<"{\"code\":"<<code<<",\"alive\":"<<(s?1:0)<<",\"state\":"<<(int)v.state<<",\"status\":"<<(int)v.status<<"}"<<std::endl;
      if(!s)return 0;
    }return 5;
  }
  if(mode!="step")return 2;
  reader_revisions *r=nullptr;reader_revision_error re{};int code=reader_revisions_open_raw_v3(db.c_str(),&r,&re);
  exr_webdav_client *dav=nullptr;exr_webdav_error de{};reader_sync *sync=nullptr;reader_sync_error se{};reader_sync_report report{};
  owner own{fs::u8path(orig)};
  if(!code)code=exr_webdav_create(&dc,&dav,&de);
  reader_sync_config cfg{dav,r,cache.c_str(),original,&own};
  if(!code)code=reader_sync_create_raw_v3(&cfg,&sync,&se);
  if(!code)code=reader_sync_step_raw_v3(sync,(unsigned)std::stoul(argv[5]),"",100,nullptr,&report,&se);
  std::cout<<"{\"status\":"<<code<<",\"pushed\":"<<report.pushed<<",\"pulled\":"<<report.pulled<<",\"originals_verified\":"<<report.originals_verified<<",\"dav_code\":"<<(int)se.dav_code<<"}"<<std::endl;
  reader_sync_free(sync);if(r)reader_revisions_close(&r,nullptr);exr_webdav_free(dav);return 0;
}catch(...){std::cerr<<"F10 probe exception (redacted)\n";return 6;}}
