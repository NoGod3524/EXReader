/* SPDX-License-Identifier: MIT */
#include <reader_commands.h>
#include <sqlite3.h>
#include <chrono>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
#endif
static std::string quote(const std::string &s){std::string out="\"";for(unsigned char c:s){if(c=='"'||c=='\\'){out+='\\';out+=(char)c;}else if(c<32){char b[8];std::snprintf(b,sizeof(b),"\\u%04x",c);out+=b;}else out+=(char)c;}return out+'"';}
static std::string read(const std::string &path){std::ifstream f(std::filesystem::u8path(path),std::ios::binary);if(!f)throw std::runtime_error("missing input");return std::string(std::istreambuf_iterator<char>(f),{});}
static std::string marker;
static void pause(){std::ofstream f(std::filesystem::u8path(marker));f<<"ready";f.close();for(;;)std::this_thread::sleep_for(std::chrono::seconds(1));}
static void pause_sql(sqlite3_context *,int,sqlite3_value **){pause();}
static int install_pause(sqlite3 *db,char **,const sqlite3_api_routines *){return sqlite3_create_function_v2(db,"reader_test_pause",0,SQLITE_UTF8|SQLITE_INNOCUOUS,nullptr,pause_sql,nullptr,nullptr,nullptr);}
int main(int argc,char **argv){try{
  std::vector<std::string> args;
#ifdef _WIN32
  int count=0;wchar_t **wide=CommandLineToArgvW(GetCommandLineW(),&count);if(!wide)return 2;
  for(int i=0;i<count;i++){int n=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide[i],-1,nullptr,0,nullptr,nullptr);if(!n)return 2;std::vector<char> v((size_t)n);WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide[i],-1,v.data(),n,nullptr,nullptr);args.emplace_back(v.data());}LocalFree(wide);(void)argc;(void)argv;
#else
  for(int i=0;i<argc;++i)args.emplace_back(argv[i]);
#endif
  if(args.size()<3)return 2;
  if(args[1]=="utf16"){
    std::string raw=read(args.at(3));if(raw.size()%2)return 2;std::vector<uint16_t> wide;
    for(size_t i=0;i<raw.size();i+=2)wide.push_back((uint16_t)((unsigned char)raw[i]|((unsigned char)raw[i+1]<<8)));
    std::vector<char> out(std::stoul(args.at(4)),1);size_t bytes=9;reader_command_error error{};
    auto status=reader_command_utf16(wide.data(),wide.size(),out.empty()?nullptr:out.data(),out.size(),&bytes,&error);
    std::cout<<"{\"status\":"<<status<<",\"bytes\":"<<bytes<<",\"text\":"<<quote(out.empty()?"":out.data())<<"}\n";return 0;
  }
  if(args[1]=="group-before"||args[1]=="group-after"){
    marker=args.at(11);if(args[1]=="group-before"&&sqlite3_auto_extension((void(*)(void))install_pause)!=SQLITE_OK)return 2;
  }
  reader_revisions *store=nullptr;reader_revision_error opened{};
  auto open_status=reader_revisions_open(args[2].c_str(),&store,&opened);
  reader_command_error error{};reader_command_result result{};reader_command_status status=READER_COMMAND_REVISION;
  std::string extra;
  if(open_status==READER_REV_OK){
    if(args[1]=="identity"){
      status=READER_COMMAND_OK;extra=",\"sqlite_version\":"+quote(sqlite3_libversion())+",\"sqlite_source_id\":"+quote(sqlite3_sourceid())+",\"header_source_id\":"+quote(SQLITE_SOURCE_ID);
    }else{
      std::vector<std::string> parents;std::vector<const char *> pointers;
      if(args.at(4)!="-"){size_t start=0;for(;;){size_t end=args[4].find(',',start);parents.push_back(args[4].substr(start,end==std::string::npos?end:end-start));if(end==std::string::npos)break;start=end+1;}}
      for(const auto &parent:parents)pointers.push_back(parent.c_str());
      reader_command_context context{store,args.at(3)=="-"?nullptr:args[3].c_str(),pointers.data(),pointers.size()};
      if(args[1].rfind("group",0)==0){
        std::string name=args.at(8)=="-"?"":read(args[8]);
        reader_group_command input{(reader_command_operation)std::stoi(args.at(6)),(reader_group_kind)std::stoi(args.at(5)),
          args.at(7)=="-"?nullptr:args[7].c_str(),name.c_str(),args.at(9)=="-"?nullptr:args[9].c_str(),std::stoull(args.at(10))};
        status=reader_command_apply_group(&context,&input,&result,&error);
      }else if(args[1]=="book"){
        std::string title=read(args.at(11)),author=read(args.at(12)),sort=read(args.at(13));
        reader_book_command input{(reader_command_operation)std::stoi(args.at(5)),args.at(6).c_str(),args.at(7).c_str(),args.at(8).c_str(),
          title.c_str(),author.c_str(),sort.c_str(),std::stoull(args.at(9)),std::stoi(args.at(10))};
        status=reader_command_apply_book(&context,&input,&result,&error);
      }else if(args[1]=="member"){
        reader_membership_command input{(reader_command_operation)std::stoi(args.at(6)),(reader_group_kind)std::stoi(args.at(5)),
          args.at(7).c_str(),args.at(8).c_str(),std::stoull(args.at(9))};
        status=reader_command_apply_membership(&context,&input,&result,&error);
      }else if(args[1]=="wrong-thread"){
        reader_group_command input{READER_COMMAND_PUT,READER_GROUP_TAG,nullptr,"Wrong thread",nullptr,0};
        std::thread worker([&]{status=reader_command_apply_group(&context,&input,&result,&error);});worker.join();
      }else return 2;
      if(args[1]=="group-after"&&status==READER_COMMAND_OK)pause();
    }
  }else error.revision=opened;
  reader_revision_error closed{};if(store&&reader_revisions_close(&store,&closed)!=READER_REV_OK)return 4;
  std::cout<<"{\"status\":"<<status<<",\"revision_status\":"<<error.revision.code<<",\"sqlite_code\":"<<error.revision.sqlite_code
    <<",\"key\":"<<quote(result.entity_key)<<",\"id\":"<<quote(result.revision_id)<<",\"created\":"<<result.created<<",\"applied\":"<<result.applied<<extra<<"}\n";
  return 0;
}catch(const std::exception &){std::cerr<<"typed consumer input/output failure\n";return 2;}}
