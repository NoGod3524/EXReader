/* SPDX-License-Identifier: MIT */
#include <reader_conflict_actions.h>
#include <sqlite3.h>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <map>
#include <sstream>
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
static std::map<std::string,std::string> options;
static std::string option(const char *name,const char *fallback=""){
  auto found=options.find(name);if(found==options.end())return fallback;
  return !found->second.empty()&&found->second[0]=='@'?read(found->second.substr(1)):found->second;
}
static int number(const char *name,int fallback=0){auto f=options.find(name);return f==options.end()?fallback:std::stoi(f->second);}
static const char *optional(const std::string &value){return value.empty()||value=="-"?nullptr:value.c_str();}
static std::vector<std::string> split(const std::string &value){
  std::vector<std::string> out;if(value.empty()||value=="-")return out;size_t start=0;
  for(;;){size_t end=value.find(',',start);out.push_back(value.substr(start,end==std::string::npos?end:end-start));if(end==std::string::npos)break;start=end+1;}
  return out;
}
static const char *kBook="txt:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
struct cancel_state {int polls=0,after=-1;reader_conflict_owner *reenter=nullptr;int reenter_status=-1;};
static int cancel_poll(void *context){
  auto &state=*static_cast<cancel_state *>(context);++state.polls;
  if(state.reenter&&state.reenter_status<0){
    reader_conflict_target probe{};probe.kind=READER_CONFLICT_TARGET_BOOK;probe.book_key=kBook;
    reader_conflict_snapshot *inner=nullptr;state.reenter_status=(int)reader_conflict_prepare(state.reenter,&probe,nullptr,&inner,nullptr);reader_conflict_snapshot_free(inner);
  }
  return state.after>=0&&state.polls>state.after;
}
static std::string head_json(const reader_conflict_view *view){
  std::string out="[";
  for(size_t n=0;n<view->head_count;++n){const auto &h=view->heads[n];if(n)out+=',';
    out+="{\"id\":"+quote(h.head.revision_id)+",\"operation\":"+quote(h.head.operation)+",\"sha256\":"+quote(h.head.sha256)+",\"complete\":"+std::to_string(h.head.complete)
      +",\"requires_restore\":"+std::to_string(h.head.requires_restore)+",\"info_id\":"+quote(h.info.revision_id)+",\"wire\":"+quote(std::string(h.wire,h.wire_bytes))+"}";}
  return out+']';
}
static std::string error_json(const reader_conflict_error &e){
  return ",\"message\":"+quote(e.message)+",\"revision_code\":"+std::to_string((int)e.revision.code)+",\"command_code\":"+std::to_string((int)e.command.code);
}
static std::string book_text,group_text,annotation_text;
static reader_conflict_target target(){
  std::string kind=option("target");
  reader_conflict_target t{};t.group_kind=(reader_group_kind)number("gk");
  book_text=option("book");group_text=option("gid");annotation_text=option("ann");
  t.book_key=optional(book_text);t.group_id=optional(group_text);t.annotation_id=optional(annotation_text);
  t.kind=kind=="book"?READER_CONFLICT_TARGET_BOOK:kind=="group"?READER_CONFLICT_TARGET_GROUP:kind=="membership"?READER_CONFLICT_TARGET_MEMBERSHIP:
    kind=="progress"?READER_CONFLICT_TARGET_PROGRESS:READER_CONFLICT_TARGET_ANNOTATION;
  if(kind=="bad")t.kind=(reader_conflict_target_kind)99;
  return t;
}
int main(int argc,char **argv){try{
  std::vector<std::string> args;
#ifdef _WIN32
  int count=0;wchar_t **wide=CommandLineToArgvW(GetCommandLineW(),&count);if(!wide)return 2;
  for(int i=0;i<count;i++){int n=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide[i],-1,nullptr,0,nullptr,nullptr);if(!n)return 2;std::vector<char> v((size_t)n);WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide[i],-1,v.data(),n,nullptr,nullptr);args.emplace_back(v.data());}LocalFree(wide);(void)argc;(void)argv;
#else
  for(int i=0;i<argc;++i)args.emplace_back(argv[i]);
#endif
  if(args.size()<3)return 2;
  for(size_t n=3;n<args.size();++n){size_t eq=args[n].find('=');if(eq==std::string::npos)return 2;options[args[n].substr(0,eq)]=args[n].substr(eq+1);}
  const std::string action=args[1];
  if(action=="identity"){std::cout<<"{\"sqlite_version\":"<<quote(sqlite3_libversion())<<",\"sqlite_source_id\":"<<quote(sqlite3_sourceid())<<",\"header_source_id\":"<<quote(SQLITE_SOURCE_ID)<<"}\n";return 0;}
  /* Revision-store helpers stand in for the two sync clients and the remote receiver. */
  if(action=="export"||action=="receive"||action.rfind("local-",0)==0){
    reader_revisions *store=nullptr;reader_revision_error opened{};
    if(reader_revisions_open(args[2].c_str(),&store,&opened)){std::cout<<"{\"status\":-1}\n";return 0;}
    struct closer {reader_revisions *&s;~closer(){reader_revisions_close(&s,nullptr);}} close_store{store};
    if(action=="export"){
      char *wire=nullptr;size_t bytes=0;reader_revision_info info{};reader_revision_error e{};
      auto status=reader_revision_get(store,option("id").c_str(),&wire,&bytes,&info,&e);
      if(!status){std::ofstream f(std::filesystem::u8path(option("out")),std::ios::binary);f.write(wire,(std::streamsize)bytes);}
      reader_revision_bytes_free(wire);std::cout<<"{\"status\":"<<status<<"}\n";return 0;
    }
    if(action=="receive"){
      std::string wire=read(option("wire"));reader_revision_info info{};int created=0;reader_revision_error e{};
      auto status=reader_revision_receive(store,wire.data(),wire.size(),option("sha").c_str(),&info,&created,&e);
      std::cout<<"{\"status\":"<<status<<",\"created\":"<<created<<"}\n";return 0;
    }
    std::vector<std::string> heads=split(option("heads"));std::vector<const char *> pointers;for(auto &h:heads)pointers.push_back(h.c_str());
    std::string rid=option("rid");reader_command_context context{store,optional(rid),pointers.data(),pointers.size()};
    reader_command_result result{};reader_command_error e{};reader_command_status status;
    if(action=="local-group"){
      std::string name=option("name"),id=option("gid"),parent=option("parent");
      reader_group_command c{(reader_command_operation)number("op"),(reader_group_kind)number("gk"),optional(id),name.c_str(),optional(parent),0};
      status=reader_command_apply_group(&context,&c,&result,&e);
    }else if(action=="local-book"){
      std::string key=option("book"),title=option("title"),sha=key.substr(key.find(':')+1),format=key.substr(0,key.find(':'));
      reader_book_command c{(reader_command_operation)number("op"),key.c_str(),format.c_str(),sha.c_str(),title.c_str(),"",title.c_str(),(uint64_t)number("length",123),0};
      status=reader_command_apply_book(&context,&c,&result,&e);
    }else{
      std::string group=option("gid"),book=option("book");
      reader_membership_command c{(reader_command_operation)number("op"),(reader_group_kind)number("gk"),group.c_str(),book.c_str(),0};
      status=reader_command_apply_membership(&context,&c,&result,&e);
    }
    std::cout<<"{\"status\":"<<status<<",\"id\":"<<quote(result.revision_id)<<",\"key\":"<<quote(result.entity_key)<<",\"created\":"<<result.created<<"}\n";return 0;
  }
  reader_conflict_owner *owner=nullptr;reader_conflict_error error{};
  auto opened_status=reader_conflict_open(args[2].c_str(),&owner,&error);
  if(opened_status){std::cout<<"{\"status\":"<<opened_status<<error_json(error)<<"}\n";return 0;}
  reader_conflict_target t=target();
  cancel_state cancel_prepare,cancel_resolve;cancel_prepare.after=number("cancel_prepare",-1);cancel_resolve.after=number("cancel_resolve",-1);
  if(number("reenter"))cancel_prepare.reenter=owner;
  reader_conflict_cancel cp{cancel_poll,&cancel_prepare},cr{cancel_poll,&cancel_resolve};
  reader_conflict_snapshot *snapshot=nullptr;
  auto prepared=reader_conflict_prepare(owner,&t,&cp,&snapshot,&error);
  std::ostringstream out;out<<"{\"prepare\":{\"status\":"<<prepared<<",\"polls\":"<<cancel_prepare.polls<<",\"reenter\":"<<cancel_prepare.reenter_status<<error_json(error);
  if(snapshot){
    const reader_conflict_view *v=reader_conflict_snapshot_view(snapshot);
    out<<",\"state\":"<<v->state<<",\"resolvable\":"<<v->resolvable<<",\"entity_kind\":"<<quote(v->entity_kind)<<",\"entity_key\":"<<quote(v->entity_key)
       <<",\"missing\":"<<v->graph.missing_parents<<",\"foreign\":"<<v->graph.foreign_parents<<",\"wire_bytes\":"<<v->wire_bytes<<",\"heads\":"<<head_json(v);
  }
  out<<"}";
  if(action=="lifetime"&&snapshot){
    const std::string before=head_json(reader_conflict_snapshot_view(snapshot));
    const auto closed=reader_conflict_close(&owner,&error);
    const bool stable=before==head_json(reader_conflict_snapshot_view(snapshot));
    std::thread release([&]{reader_conflict_snapshot_free(snapshot);});release.join();snapshot=nullptr;
    out<<",\"lifetime\":{\"close\":"<<closed<<",\"stable\":"<<(stable?"true":"false")<<",\"freed\":true}";
  }
  if(action=="resolve"&&snapshot){
    if(!option("race").empty()){ /* A foreign sync revision lands through another connection after the snapshot. */
      reader_revisions *other=nullptr;reader_revision_error e{};reader_revisions_open(args[2].c_str(),&other,&e);
      std::string wire=read(option("race")),sha=option("race_sha");reader_revision_info info{};int created=0;
      auto s=reader_revision_receive(other,wire.data(),wire.size(),sha.c_str(),&info,&created,&e);reader_revisions_close(&other,nullptr);
      out<<",\"race\":"<<s;
    }
    std::string target_kind=option("target");
    std::string kind=option("fn",target_kind.c_str());
    reader_command_operation op=(reader_command_operation)number("op");
    std::string rid=option("rid");
    std::string title=option("title"),author=option("author"),name=option("name"),id=option("gid"),book=option("book"),parent=option("parent");
    std::string cbook=option("cbook",book.c_str()),cid=option("cid",id.c_str());
    std::string format=cbook.substr(0,cbook.find(':')),sha=cbook.find(':')==std::string::npos?"":cbook.substr(cbook.find(':')+1);
    int rounds=number("rounds",1);
    for(int round=0;round<rounds;++round){
      if(round)name=option("retry_name",name.c_str());
      reader_conflict_result result{};reader_conflict_error e{};reader_conflict_status status=READER_CONFLICT_ARGUMENT;
      auto run=[&]{
        if(kind=="book"||kind=="progress"||kind=="annotation"){
          reader_book_command c{op,cbook.c_str(),format.c_str(),sha.c_str(),title.c_str(),author.c_str(),title.c_str(),(uint64_t)number("length",123),number("favorite")};
          status=reader_conflict_resolve_book(owner,snapshot,optional(rid),&c,&cr,&result,&e);
        }else if(kind=="group"){
          reader_group_command c{op,(reader_group_kind)number("ck",number("gk")),cid.c_str(),name.c_str(),optional(parent),0};
          status=reader_conflict_resolve_group(owner,snapshot,optional(rid),&c,&cr,&result,&e);
        }else{
          reader_membership_command c{op,(reader_group_kind)number("ck",number("gk")),cid.c_str(),cbook.c_str(),0};
          status=reader_conflict_resolve_membership(owner,snapshot,optional(rid),&c,&cr,&result,&e);
        }
      };
      if(number("thread")){std::thread worker(run);worker.join();}else run();
      out<<",\""<<(round?"retry":"resolve")<<"\":{\"status\":"<<status<<",\"polls\":"<<cancel_resolve.polls<<",\"committed\":"<<result.committed<<",\"created\":"<<result.command.created
         <<",\"applied\":"<<result.command.applied<<",\"observed\":"<<result.observed_heads<<",\"id\":"<<quote(result.command.revision_id)<<",\"key\":"<<quote(result.command.entity_key)<<error_json(e)<<"}";
      cancel_resolve.after=-1;
    }
  }
  out<<"}\n";std::cout<<out.str();
  reader_conflict_snapshot_free(snapshot);
  auto closed=reader_conflict_close(&owner,&error);
  return closed?9:0;
}catch(const std::exception &failed){std::cerr<<failed.what()<<"\n";return 3;}}
