/* SPDX-License-Identifier: MIT */
#include <reader_metadata.h>
#include <catalog.h>
#include <sqlite3.h>
#include <chrono>
#include <atomic>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <thread>
#include <vector>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
#endif
static std::string quote(const std::string &s){std::string out="\"";for(unsigned char c:s){if(c=='\"'||c=='\\'){out+='\\';out+=(char)c;}else if(c<32){char b[8];std::snprintf(b,sizeof(b),"\\u%04x",c);out+=b;}else out+=(char)c;}return out+'\"';}
static void pause(const std::string &marker){std::ofstream f(std::filesystem::u8path(marker));f<<"ready";f.close();for(;;)std::this_thread::sleep_for(std::chrono::seconds(1));}
int main(int argc,char **argv){try{
  std::vector<std::string> args;
#ifdef _WIN32
  int count=0;wchar_t **wide=CommandLineToArgvW(GetCommandLineW(),&count);if(!wide)return 2;
  for(int i=0;i<count;i++){int n=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide[i],-1,nullptr,0,nullptr,nullptr);if(!n)return 2;std::vector<char> v((size_t)n);WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide[i],-1,v.data(),n,nullptr,nullptr);args.emplace_back(v.data());}LocalFree(wide);(void)argc;(void)argv;
#else
  for(int i=0;i<argc;++i)args.emplace_back(argv[i]);
#endif
  if(args.size()<4)return 2;
  std::string key="txt:"+std::string(64,'a'),sha(64,'a'),extra;
  if(args[1]=="seed"){
    reader_catalog *catalog=nullptr;reader_catalog_error error{};
    if(reader_catalog_open(args[2].c_str(),&catalog,&error))return 3;
    reader_catalog_book book{"txt",sha.c_str(),"用户已编辑标题😀","用户作者","用户已编辑标题😀","reflow_global",123,777,1};
    if(reader_catalog_attach(catalog,&book,&error)||reader_catalog_close(&catalog,&error))return 4;
    std::cout<<"{\"status\":0,\"sqlite_version\":"<<quote(sqlite3_libversion())<<",\"sqlite_source_id\":"<<quote(sqlite3_sourceid())<<",\"header_source_id\":"<<quote(SQLITE_SOURCE_ID)<<"}\n";return 0;
  }
  reader_metadata_owner *owner=nullptr;reader_metadata_error error{};reader_metadata_result result{};
  reader_metadata_status status=reader_metadata_open(args[2].c_str(),args[3].c_str(),&owner,&error);
  reader_metadata_snapshot *snapshot=nullptr;
  if(status==READER_METADATA_OK){
    std::string mode="finish";
    if(args[1]=="book"||args[1]=="bootstrap"||args[1]=="favorite"){
      status=reader_metadata_prepare_book(owner,key.c_str(),&snapshot,&error);
      const reader_metadata_view *view=reader_metadata_snapshot_view(snapshot);
      if(view){extra=",\"title\":"+quote(view->book.title)+",\"author\":"+quote(view->book.author)+",\"sort\":"+quote(view->book.sort_title)+",\"favorite\":"+std::to_string(view->book.favorite)+",\"heads\":"+std::to_string(view->head_count)+",\"bootstrap\":"+std::to_string(view->needs_bootstrap);}
      if(args[1]=="bootstrap"&&view){reader_metadata_verified_source source{"txt",sha.c_str(),std::stoull(args.at(4))};status=reader_metadata_stage_bootstrap(owner,snapshot,&source,&result,&error);mode=args.at(5);}
      else if(args[1]=="favorite"&&view){reader_book_command input=view->book;input.favorite=std::stoi(args.at(4));status=reader_metadata_stage_book(owner,snapshot,&input,&result,&error);mode=args.at(5);}
      else mode="inspect";
    }else if(args[1]=="group"){
      auto kind=(reader_group_kind)std::stoi(args.at(4));std::string group=args.at(5)=="-"?"":args[5],parent=args.at(7)=="-"?"":args[7];
      status=reader_metadata_prepare_group(owner,kind,group.c_str(),&snapshot,&error);
      if(status==READER_METADATA_OK){reader_group_command input{(reader_command_operation)std::stoi(args.at(9)),kind,group.c_str(),args.at(6).c_str(),parent.c_str(),std::stoull(args.at(8))};status=reader_metadata_stage_group(owner,snapshot,&input,&result,&error);}
      mode=args.at(10);
    }else if(args[1]=="inspect-group"){
      status=reader_metadata_prepare_group(owner,(reader_group_kind)std::stoi(args.at(4)),args.at(5).c_str(),&snapshot,&error);
      const reader_metadata_view *view=reader_metadata_snapshot_view(snapshot);if(view)extra=",\"name\":"+quote(view->group.name)+",\"parent\":"+quote(view->group.parent_id)+",\"ordinal\":"+std::to_string(view->group.ordinal)+",\"deleted\":"+std::to_string(view->deleted)+",\"present\":"+std::to_string(view->present)+",\"heads\":"+std::to_string(view->head_count);
      mode="inspect";
    }else if(args[1]=="member"){
      auto kind=(reader_group_kind)std::stoi(args.at(4));status=reader_metadata_prepare_membership(owner,kind,args.at(5).c_str(),key.c_str(),&snapshot,&error);
      if(status==READER_METADATA_OK||status==READER_METADATA_NEEDS_BOOTSTRAP){reader_membership_command input{(reader_command_operation)std::stoi(args.at(7)),kind,args.at(5).c_str(),key.c_str(),std::stoull(args.at(6))};status=reader_metadata_stage_membership(owner,snapshot,&input,&result,&error);}
      mode=args.at(8);
    }else if(args[1]=="pending"){status=reader_metadata_pending(owner,&result,&error);mode="inspect";}
    else if(args[1]=="abandon"){status=reader_metadata_abandon_pending(owner,&error);mode="inspect";}
    else if(args[1]=="apply"){status=reader_metadata_apply_pending(owner,&result,&error);mode="inspect";}
    else if(args[1]=="finish"){status=reader_metadata_finish_pending(owner,&result,&error);mode="inspect";}
    else if(args[1]=="wrong-thread"){
      std::thread other([&]{status=reader_metadata_pending(owner,&result,&error);});other.join();mode="inspect";
    }else if(args[1]=="second-owner"){
      reader_metadata_owner *other=nullptr;status=reader_metadata_open(args[2].c_str(),args[3].c_str(),&other,&error);if(other)return 5;mode="inspect";
    }else if(args[1]=="snapshot-race"){
      status=reader_metadata_prepare_group(owner,READER_GROUP_TAG,args.at(4).c_str(),&snapshot,&error);
      if(status!=READER_METADATA_OK)return 8;
      const reader_metadata_view *initial=reader_metadata_snapshot_view(snapshot);
      if(!initial||initial->head_count!=1)return 9;
      std::string first=initial->heads[0];reader_metadata_snapshot_free(snapshot);snapshot=nullptr;
      std::atomic<int> writer_error{0};std::atomic<bool> started{false};
      std::thread writer([&]{
        reader_revisions *store=nullptr;reader_revision_error e{};
        if(reader_revisions_open(args[2].c_str(),&store,&e)){writer_error=1;started=true;return;}
        started=true;std::string parent=first;
        for(int i=0;i<24;++i){
          char next[33];if(reader_revision_new_id(next,&e)){writer_error=2;break;}
          const char *head=parent.c_str();reader_command_context context{store,next,&head,1};
          std::string name="v"+std::string(next);reader_group_command input{READER_COMMAND_PUT,READER_GROUP_TAG,args[4].c_str(),name.c_str(),nullptr,0};
          reader_command_result committed{};reader_command_error command_error{};
          if(reader_command_apply_group(&context,&input,&committed,&command_error)){writer_error=3;break;}
          parent=next;std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
        if(reader_revisions_close(&store,&e))writer_error=4;
      });
      while(!started)std::this_thread::yield();
      int coherent=0,conflicts=0,mismatched=0;
      for(int i=0;i<240;++i){
        auto prepared=reader_metadata_prepare_group(owner,READER_GROUP_TAG,args[4].c_str(),&snapshot,&error);
        if(prepared==READER_METADATA_OK){const auto *v=reader_metadata_snapshot_view(snapshot);if(!v||v->head_count!=1||v->group.name!="v"+std::string(v->heads[0]))++mismatched;else ++coherent;}
        else if(prepared==READER_METADATA_CONFLICT)++conflicts;else ++mismatched;
        reader_metadata_snapshot_free(snapshot);snapshot=nullptr;
      }
      writer.join();if(writer_error||mismatched||!coherent)return 10;
      status=READER_METADATA_OK;extra=",\"coherent\":"+std::to_string(coherent)+",\"conflicts\":"+std::to_string(conflicts);mode="inspect";
    }else if(args[1]=="cleanup-denied"){
      status=reader_metadata_prepare_group(owner,READER_GROUP_TAG,nullptr,&snapshot,&error);
      reader_group_command input{READER_COMMAND_PUT,READER_GROUP_TAG,nullptr,"Committed cleanup refusal",nullptr,0};
      if(status==READER_METADATA_OK)status=reader_metadata_stage_group(owner,snapshot,&input,&result,&error);
      if(status==READER_METADATA_OK)status=reader_metadata_apply_pending(owner,&result,&error);
      if(status==READER_METADATA_OK){
#ifdef _WIN32
        std::filesystem::path pending=std::filesystem::u8path(args[3]);
        HANDLE held=CreateFileW(pending.c_str(),GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
        if(held==INVALID_HANDLE_VALUE)return 7;
        status=reader_metadata_finish_pending(owner,&result,&error);CloseHandle(held);
#else
        auto parent=std::filesystem::u8path(args[3]).parent_path();auto permissions=std::filesystem::status(parent).permissions();
        std::filesystem::permissions(parent,std::filesystem::perms::owner_read|std::filesystem::perms::owner_exec);
        status=reader_metadata_finish_pending(owner,&result,&error);std::filesystem::permissions(parent,permissions);
#endif
      }
      mode="inspect";
    }else return 2;
    if(status==READER_METADATA_OK){
      if(mode=="apply"||mode=="apply-wait")status=reader_metadata_apply_pending(owner,&result,&error);
      else if(mode=="finish")status=reader_metadata_finish_pending(owner,&result,&error);
      if(mode=="stage-wait"||mode=="apply-wait")pause(args.back());
    }
  }
  reader_metadata_snapshot_free(snapshot);
  reader_metadata_error closed{};if(owner&&reader_metadata_close(&owner,&closed)!=READER_METADATA_OK)return 6;
  std::cout<<"{\"status\":"<<status<<",\"revision_status\":"<<error.command.revision.code<<",\"key\":"<<quote(result.command.entity_key)<<",\"id\":"<<quote(result.command.revision_id)<<",\"created\":"<<result.command.created<<",\"applied\":"<<result.command.applied<<",\"committed\":"<<result.committed<<",\"pending\":"<<result.pending<<extra<<"}\n";return 0;
}catch(const std::exception &){std::cerr<<"metadata consumer input/output failure\n";return 2;}}
