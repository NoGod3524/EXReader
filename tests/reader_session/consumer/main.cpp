/* SPDX-License-Identifier: MIT */
#include <reader_session.h>
#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>
#ifdef _WIN32
#include <windows.h>
#include <shellapi.h>
#endif
extern "C" int c_contract(void);
int main(int argc,char **argv){try{
  std::vector<std::string> a;
#ifdef _WIN32
  int count=0;wchar_t **wide=CommandLineToArgvW(GetCommandLineW(),&count);if(!wide)return 2;
  for(int n=0;n<count;n++){int bytes=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide[n],-1,nullptr,0,nullptr,nullptr);if(!bytes)return 2;
    std::vector<char> value((size_t)bytes);WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide[n],-1,value.data(),bytes,nullptr,nullptr);a.emplace_back(value.data());}
  LocalFree(wide);(void)argc;(void)argv;
#else
  for(int n=0;n<argc;n++)a.emplace_back(argv[n]);
#endif
  if(c_contract()||a.size()!=7)return 2;
  reader_session_config config{};config.dav.root_url=a[1].c_str();config.dav.authorization=std::getenv("READER_TEST_AUTH");
  config.product_path=a[2].c_str();config.private_directory=a[3].c_str();config.original_directory=a[4].c_str();config.account_id=a[5].c_str();config.dav.timeout_ms=(unsigned)std::stoul(a[6]);
  reader_session *session=nullptr;int created=reader_session_create(&config,&session);std::cout<<"{\"create\":"<<created<<"}"<<std::endl;if(created)return 0;
  std::string line;while(std::getline(std::cin,line)){
    int code=0;
    if(line=="start")code=reader_session_start(session);
    else if(line=="cancel")code=reader_session_cancel(session);
    else if(line=="close")code=reader_session_request_close(session);
    else if(line=="destroy")code=reader_session_destroy(&session);
    else if(line!="observe")return 2;
    reader_session_snapshot v{};if(session)reader_session_observe(session,&v);
    std::cout<<"{\"code\":"<<code<<",\"state\":"<<(int)v.state<<",\"status\":"<<(int)v.status<<",\"attempt\":"<<v.attempt<<",\"sweeps\":"<<v.completed_sweeps
      <<",\"steps\":"<<v.steps<<",\"shard\":"<<v.shard<<",\"completed_shards\":"<<v.completed_shards<<",\"after\":\""<<v.after<<"\",\"pushed\":"<<v.pushed<<",\"pulled\":"<<v.pulled
      <<",\"originals_verified\":"<<v.originals_verified<<",\"pending_metadata\":"<<v.pending_metadata_observations<<",\"pending_original\":"<<v.pending_original_observations
      <<",\"dav_code\":"<<v.error.dav_code<<",\"revision_code\":"<<v.error.revision_code<<",\"http_status\":"<<v.error.http_status<<",\"full_library_complete\":"<<v.full_library_complete<<"}"<<std::endl;
    if(!session)return 0;
  }
  // An abnormal host exit is tested separately; never hide it with a destructor
  // that synchronously blocks the GUI on network work.
  return 3;
}catch(...){std::cerr<<"Session consumer failed\n";return 2;}}
