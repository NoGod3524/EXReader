/* SPDX-License-Identifier: MIT */
#include <exr_webdav.h>
#include <cstdio>
#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
#endif
static std::string quoted(const char *text) {
  std::string result="\"";
  for(const unsigned char *p=(const unsigned char *)text;*p;p++) {
    if(*p=='"'||*p=='\\') { result+='\\';result+=(char)*p; }
    else if(*p<32) { char escape[8];std::snprintf(escape,sizeof(escape),"\\u%04x",*p);result+=escape; }
    else result+=(char)*p;
  }
  return result+'"';
}
struct cancel_state { uint64_t after,received; };
static int cancelled(void *opaque) { auto &s=*(cancel_state *)opaque;return s.after!=UINT64_MAX && s.received>=s.after; }
static void progress(void *opaque,uint64_t bytes) { ((cancel_state *)opaque)->received=bytes; }
int main(int argc,char **argv) {
  std::vector<std::string> args;
#ifdef _WIN32
  int count=0;wchar_t **wide=CommandLineToArgvW(GetCommandLineW(),&count);
  if(!wide) return 2;
  for(int i=0;i<count;i++) {
    int bytes=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide[i],-1,NULL,0,NULL,NULL);
    if(!bytes) { LocalFree(wide);return 2; }
    std::vector<char> value((size_t)bytes);WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide[i],-1,value.data(),bytes,NULL,NULL);args.emplace_back(value.data());
  }
  LocalFree(wide);(void)argc;(void)argv;
#else
  for(int i=0;i<argc;i++) args.emplace_back(argv[i]);
#endif
  if(args.size()!=12) return 2;
  exr_webdav_config config={};config.root_url=args[2].c_str();config.authorization=args[3].c_str();
  config.max_download_bytes=std::strtoull(args[7].c_str(),NULL,10);config.max_listing_bytes=(size_t)std::strtoull(args[8].c_str(),NULL,10);
  config.max_entries=(size_t)std::strtoull(args[9].c_str(),NULL,10);config.timeout_ms=(unsigned)std::strtoul(args[10].c_str(),NULL,10);
  cancel_state state{std::strtoull(args[11].c_str(),NULL,10),0};exr_webdav_control control{cancelled,progress,&state};
  exr_webdav_client *client=nullptr;exr_webdav_error error={};exr_webdav_listing listing={};exr_webdav_download download={};int first=-1;
  exr_webdav_status status=exr_webdav_create(&config,&client,&error);
  if(status==EXR_DAV_OK) {
    if(args[1]=="list") status=exr_webdav_list(client,args[4].c_str(),&control,&listing,&error);
    else {
      if(args[1]=="recover") first=exr_webdav_download_file(client,"error500",args[5].c_str(),"first-failed.epub",&control,&download,&error);
      status=exr_webdav_download_file(client,args[4].c_str(),args[5].c_str(),args[6].c_str(),&control,&download,&error);
    }
  }
  std::cout<<"{\"status\":"<<(int)status<<",\"http_status\":"<<error.http_status<<",\"message\":"<<quoted(error.message)
    <<",\"bytes\":"<<download.bytes<<",\"published\":"<<download.published<<",\"first_status\":"<<first<<",\"entries\":[";
  for(size_t i=0;i<listing.count;i++) {
    if(i) std::cout<<',';const auto &e=listing.entries[i];
    std::cout<<"{\"resource\":"<<quoted(e.resource)<<",\"display_name\":"<<quoted(e.display_name)<<",\"etag\":"<<quoted(e.etag)
      <<",\"bytes\":"<<e.bytes<<",\"has_size\":"<<e.has_size<<",\"collection\":"<<e.collection<<'}';
  }
  std::cout<<"]}\n";exr_webdav_listing_free(&listing);exr_webdav_free(client);return 0;
}
