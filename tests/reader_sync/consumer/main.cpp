/* SPDX-License-Identifier: MIT */
#include <reader_sync.h>
#include <filesystem>
#include <iostream>
#include <string>
#include <vector>
#include <cstring>
#include <cstdlib>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
#endif
struct host {std::filesystem::path originals;uint64_t received=0,cancel_at=UINT64_MAX;};
static int original(void *opaque,const char *key,char *path,size_t capacity){auto &h=*(host *)opaque;std::string k=key;size_t colon=k.find(':');std::string value=(h.originals/std::filesystem::u8path(k.substr(colon+1)+"."+k.substr(0,colon))).u8string();if(value.size()>=capacity||!std::filesystem::exists(std::filesystem::u8path(value)))return 1;std::memcpy(path,value.c_str(),value.size()+1);return 0;}
static int cancel(void *opaque){auto &h=*(host *)opaque;return h.received>=h.cancel_at;}
static void progress(void *opaque,uint64_t received){((host *)opaque)->received=received;}
int main(int argc,char **argv){try{
  std::vector<std::string> a;
#ifdef _WIN32
  int count=0;wchar_t **wide=CommandLineToArgvW(GetCommandLineW(),&count);if(!wide)return 2;for(int n=0;n<count;n++){int bytes=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide[n],-1,nullptr,0,nullptr,nullptr);if(!bytes)return 2;std::vector<char> value((size_t)bytes);WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide[n],-1,value.data(),bytes,nullptr,nullptr);a.emplace_back(value.data());}LocalFree(wide);(void)argc;(void)argv;
#else
  for(int n=0;n<argc;n++)a.emplace_back(argv[n]);
#endif
  if(a.size()!=10)return 2;
  host h{std::filesystem::u8path(a[4])};h.cancel_at=std::stoull(a[9]);
  exr_webdav_config dav_config{};dav_config.root_url=a[1].c_str();dav_config.authorization=std::getenv("READER_TEST_AUTH");dav_config.timeout_ms=15000;
  exr_webdav_client *dav=nullptr;exr_webdav_error de{};int ds=exr_webdav_create(&dav_config,&dav,&de);
  if(ds){std::cout<<"{\"status\":3,\"dav_code\":"<<ds<<",\"http_status\":"<<de.http_status<<"}\n";return 0;}
  reader_revisions *revisions=nullptr;reader_revision_error re{};int rs=reader_revisions_open(a[2].c_str(),&revisions,&re);
  if(rs){exr_webdav_free(dav);std::cout<<"{\"status\":4,\"revision_code\":"<<rs<<"}\n";return 0;}
  reader_sync_config config{dav,revisions,a[3].c_str(),original,&h};reader_sync *sync=nullptr;reader_sync_error error{};reader_sync_report report{};
  int status=reader_sync_create(&config,&sync,&error);exr_webdav_control control{cancel,progress,&h};
  if(!status)status=reader_sync_step(sync,(unsigned)std::stoul(a[5]),a[6]=="-"?"":a[6].c_str(),(size_t)std::stoul(a[7]),&control,&report,&error);
  // a[8] is an inert host reading-position observation. The module never
  // receives it; the harness proves remote progress cannot change it.
  std::cout<<"{\"status\":"<<status<<",\"dav_code\":"<<error.dav_code<<",\"revision_code\":"<<error.revision_code<<",\"http_status\":"<<error.http_status
    <<",\"pushed\":"<<report.pushed<<",\"pulled\":"<<report.pulled<<",\"originals_verified\":"<<report.originals_verified<<",\"pending_metadata\":"<<report.pending_metadata
    <<",\"pending_local_original\":"<<report.pending_local_original<<",\"remaining_in_shard\":"<<report.remaining_in_shard<<",\"shard_complete\":"<<report.shard_complete
    <<",\"shard\":"<<report.shard<<",\"next_shard\":"<<report.next_shard<<",\"shard_count\":"<<report.shard_count<<",\"after\":\""<<report.after<<"\",\"full_library_complete\":"<<report.full_library_complete<<"}\n";
  reader_sync_free(sync);reader_revisions_close(&revisions,nullptr);exr_webdav_free(dav);return 0;
}catch(...){std::cerr<<"Installed sync consumer failed\n";return 2;}}
