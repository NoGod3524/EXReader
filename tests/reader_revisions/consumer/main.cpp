/* SPDX-License-Identifier: MIT */
#include <reader_revisions.h>
#include <reader_projection.h>
#include <sqlite3.h>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#include <thread>
#include <vector>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
#endif
static std::string quote(const std::string &s){std::string out="\"";for(unsigned char c:s){if(c=='"'||c=='\\'){out+='\\';out+=(char)c;}else if(c<32){char b[8];std::snprintf(b,sizeof(b),"\\u%04x",c);out+=b;}else out+=(char)c;}return out+'"';}
static std::string read(const std::string &name){std::ifstream file(std::filesystem::u8path(name),std::ios::binary);if(!file)throw std::runtime_error("input unavailable");return std::string(std::istreambuf_iterator<char>(file),{});}
static std::string marker;
static void pause_marker(){std::ofstream file(std::filesystem::u8path(marker),std::ios::binary);file<<"ready";file.close();for(;;)std::this_thread::sleep_for(std::chrono::seconds(1));}
static void pause_sql(sqlite3_context *,int,sqlite3_value **){pause_marker();}
static int install_pause(sqlite3 *db,char **,const sqlite3_api_routines *){return sqlite3_create_function_v2(db,"reader_test_pause",0,SQLITE_UTF8|SQLITE_INNOCUOUS,nullptr,pause_sql,nullptr,nullptr,nullptr);}
static std::string metadata(const reader_revision_info &i){return "\"id\":"+quote(i.revision_id)+",\"kind\":"+quote(i.entity_kind)+",\"key\":"+quote(i.entity_key)+",\"operation\":"+quote(i.operation)+",\"location\":"+quote(i.location_kind)+",\"sha256\":"+quote(i.sha256)+",\"bytes\":"+std::to_string(i.bytes);}
struct observations {reader_revisions *store;std::vector<std::string> heads,queue;bool reentry=false;int nested=-1;std::vector<std::string> annotations;size_t stop=0;std::string database,mutation;};
static int head(void *opaque,const reader_revision_head *h){auto &o=*(observations *)opaque;o.heads.push_back("{\"id\":"+quote(h->revision_id)+",\"operation\":"+quote(h->operation)+",\"complete\":"+std::to_string(h->complete)+",\"requires_restore\":"+std::to_string(h->requires_restore)+"}");if(o.reentry){char *wire=nullptr;size_t n=0;reader_revision_error e{};o.nested=reader_revision_get(o.store,h->revision_id,&wire,&n,nullptr,&e);reader_revision_bytes_free(wire);}return 0;}
static int queued(void *opaque,const reader_revision_outbox_row *r){auto &o=*(observations *)opaque;o.queue.push_back("{"+metadata(r->info)+",\"wire\":"+quote(std::string(r->wire,r->info.bytes))+",\"queue_id\":"+std::to_string(r->queue_id)+",\"attempts\":"+std::to_string(r->attempts)+",\"last_error\":"+quote(r->last_error)+"}");return 0;}
static int annotation(void *opaque,const reader_revision_annotation_row *r){
  auto &o=*(observations *)opaque;
  o.annotations.push_back("{\"annotation_id\":"+quote(r->annotation_id)+",\"selection_kind\":"+std::to_string(r->selection.kind)+",\"revisions\":"+std::to_string(r->selection.graph.revisions)+",\"heads\":"+std::to_string(r->selection.graph.heads)+",\"deleted\":"+std::to_string(r->selection.graph.deleted)+","+metadata(r->info)+",\"wire\":"+(r->wire?quote(std::string(r->wire,r->info.bytes)):"null")+"}");
  if(o.reentry){char *wire=nullptr;size_t n=0;reader_revision_error error{};o.nested=reader_revision_get(o.store,r->info.revision_id,&wire,&n,nullptr,&error);reader_revision_bytes_free(wire);}
  if(!o.mutation.empty()){
    std::string wire=read(o.mutation);o.mutation.clear();reader_revisions *other=nullptr;reader_revision_error error{};reader_revision_info info{};int created=0;
    o.nested=reader_revisions_open(o.database.c_str(),&other,&error);
    if(o.nested==READER_REV_OK)o.nested=reader_revision_validate(other,wire.data(),wire.size(),nullptr,&info,&error);
    if(o.nested==READER_REV_OK)o.nested=reader_revision_receive(other,wire.data(),wire.size(),info.sha256,nullptr,&created,&error);
    if(other&&reader_revisions_close(&other,&error)!=READER_REV_OK)o.nested=READER_REV_DATABASE;
  }
  return o.stop&&o.annotations.size()>=o.stop;
}
static std::string array(const std::vector<std::string> &v){std::string out="[";for(size_t i=0;i<v.size();i++){if(i)out+=',';out+=v[i];}return out+"]";}
int main(int argc,char **argv){try{
  std::vector<std::string> args;
#ifdef _WIN32
  int count=0;wchar_t **wide=CommandLineToArgvW(GetCommandLineW(),&count);if(!wide)return 2;
  for(int i=0;i<count;i++){int n=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide[i],-1,nullptr,0,nullptr,nullptr);if(!n)return 2;std::vector<char> value((size_t)n);WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide[i],-1,value.data(),n,nullptr,nullptr);args.emplace_back(value.data());}LocalFree(wide);(void)argc;(void)argv;
#else
  for(int i=0;i<argc;i++)args.emplace_back(argv[i]);
#endif
  if(args.size()<3)return 2;
  if(args[1]=="crash-before-outbox"){if(args.size()!=5)return 2;marker=args[4];if(sqlite3_auto_extension((void(*)(void))install_pause)!=SQLITE_OK)return 2;}
  if(args[1]=="crash-project-before-metadata"){if(args.size()!=7)return 2;marker=args[6];if(sqlite3_auto_extension((void(*)(void))install_pause)!=SQLITE_OK)return 2;}
  reader_revisions *store=nullptr;reader_revision_error error{};reader_revision_info info{};reader_revision_state state{};int created=0,applied=0,nested=-1;std::string extra;
  reader_revision_status status=reader_revisions_open(args[2].c_str(),&store,&error);observations observed{store,{},{},false,-1};
  if(status==READER_REV_OK){
    const std::string &action=args[1];
    if(action=="identity"){
      sqlite3 *db=nullptr;if(sqlite3_open(":memory:",&db)!=SQLITE_OK)return 3;sqlite3_stmt *s=nullptr;
      if(sqlite3_prepare_v2(db,"SELECT json_valid('{\"v\":1}',1),(SELECT count(*) FROM json_tree('[1]'))",-1,&s,nullptr)!=SQLITE_OK||sqlite3_step(s)!=SQLITE_ROW)return 3;
      extra=",\"sqlite_version\":"+quote(sqlite3_libversion())+",\"sqlite_source_id\":"+quote(sqlite3_sourceid())+",\"header_source_id\":"+quote(SQLITE_SOURCE_ID)+",\"json_smoke\":"+std::to_string(sqlite3_column_int(s,0)==1&&sqlite3_column_int(s,1)==2)+",\"compile_options\":[";
      for(int i=0;sqlite3_compileoption_get(i);i++){if(i)extra+=',';extra+=quote(sqlite3_compileoption_get(i));}extra+=']';sqlite3_finalize(s);sqlite3_close(db);
    }else if(action=="local"||action=="receive"||action=="validate"||action=="crash-before-outbox"||action=="crash-after-commit"){
      if(args.size()<4)return 2;std::string wire=read(args[3]);
      if(action=="receive")status=reader_revision_receive(store,wire.data(),wire.size(),args.at(4).c_str(),&info,&created,&error);
      else if(action=="validate")status=reader_revision_validate(store,wire.data(),wire.size(),args.size()>4&&args[4]!="-"?args[4].c_str():nullptr,&info,&error);
      else status=reader_revision_local(store,wire.data(),wire.size(),&info,&created,&error);
      if(action=="crash-after-commit"&&status==READER_REV_OK){marker=args.at(4);pause_marker();}
    }else if(action=="project-local"||action=="crash-project-before-metadata"||action=="crash-project-after-commit"||action=="reading-local"||action=="crash-reading-after-commit"){
      std::string wire=read(args.at(3));std::vector<std::string> expected;std::vector<const char *> heads;
      if(args.at(4)!="-"){size_t start=0;for(;;){size_t end=args[4].find(',',start);expected.push_back(args[4].substr(start,end==std::string::npos?end:end-start));if(end==std::string::npos)break;start=end+1;}}
      for(const auto &id:expected)heads.push_back(id.c_str());
      if(action=="reading-local"||action=="crash-reading-after-commit")
        status=reader_revision_local_reading(store,wire.data(),wire.size(),heads.data(),heads.size(),&info,&created,&error);
      else status=reader_revision_local_project(store,wire.data(),wire.size(),heads.data(),heads.size(),args.at(5)=="-"?nullptr:args[5].c_str(),&info,&created,&applied,&error);
      if(action=="crash-project-after-commit"&&status==READER_REV_OK){marker=args.at(6);pause_marker();}
      if(action=="crash-reading-after-commit"&&status==READER_REV_OK){marker=args.at(6);pause_marker();}
    }else if(action=="project-remote"){
      status=reader_revision_project(store,args.at(3).c_str(),args.at(4).c_str(),args.at(5).c_str(),args.at(6)=="-"?nullptr:args[6].c_str(),&info,&error);
    }else if(action=="receive-batch"){
      std::ifstream lines(std::filesystem::u8path(args.at(3)),std::ios::binary);if(!lines)return 3;std::string line;size_t accepted=0;
      while(std::getline(lines,line)){if(line.size()<66||line[64]!=' ')return 2;std::string sha=line.substr(0,64),body=line.substr(65);status=reader_revision_receive(store,body.data(),body.size(),sha.c_str(),&info,&created,&error);if(status!=READER_REV_OK)break;++accepted;}
      extra=",\"accepted_count\":"+std::to_string(accepted);
    }else if(action=="annotations-page"||action=="annotations-wrong-thread"){
      observed.stop=(size_t)std::stoul(args.at(7));observed.reentry=args.at(8)=="reentry";
      if(args.at(8)=="mutate"){observed.database=args[2];observed.mutation=args.at(9);}
      auto invoke=[&]{status=reader_revision_annotations_page(store,args.at(3)=="NULL"?nullptr:args[3].c_str(),args.at(4)=="-"?nullptr:args[4].c_str(),std::stoi(args.at(5)),(size_t)std::stoul(args.at(6)),args.at(8)=="null-callback"?nullptr:annotation,&observed,&error);};
      if(action=="annotations-wrong-thread"){std::thread worker(invoke);worker.join();}else invoke();
      nested=observed.nested;extra=",\"annotations\":"+array(observed.annotations);
    }else if(action=="selected"){
      char *wire=nullptr;size_t bytes=0;reader_revision_selection selection{};
      status=reader_revision_selected(store,args.at(3).c_str(),args.at(4).c_str(),&wire,&bytes,&info,&selection,&error);state=selection.graph;
      extra=",\"selection_kind\":"+std::to_string(selection.kind);
      if(status==READER_REV_OK){std::ofstream output(std::filesystem::u8path(args.at(5)),std::ios::binary);output.write(wire,(std::streamsize)bytes);if(!output)return 3;}else if(wire||bytes)return 3;
      reader_revision_bytes_free(wire);
    }else if(action=="get"){
      char *wire=nullptr;size_t bytes=0;status=reader_revision_get(store,args.at(3).c_str(),&wire,&bytes,&info,&error);
      if(status==READER_REV_OK){std::ofstream output(std::filesystem::u8path(args.at(4)),std::ios::binary);output.write(wire,(std::streamsize)bytes);if(!output)return 3;}reader_revision_bytes_free(wire);
    }else if(action=="heads"||action=="reentry"){
      observed.reentry=action=="reentry";status=reader_revision_heads(store,args.at(3).c_str(),args.at(4).c_str(),head,&observed,&state,&error);nested=observed.nested;
    }else if(action=="outbox")status=reader_revision_outbox(store,args.size()>3?(size_t)std::stoul(args[3]):100,queued,&observed,&error);
    else if(action=="ack")status=reader_revision_ack(store,args.at(3).c_str(),args.at(4).c_str(),&error);
    else if(action=="retry")status=reader_revision_retry(store,args.at(3).c_str(),(reader_revision_status)std::stoi(args.at(4)),&error);
    else if(action=="newid"){char id[33];status=reader_revision_new_id(id,&error);extra=",\"new_id\":"+quote(id);}
    else if(action=="wrong-thread"){std::thread worker([&]{status=reader_revision_heads(store,"tag","00000000000000000000000000000001",nullptr,nullptr,&state,&error);});worker.join();}
    else return 2;
  }
  reader_revision_error close{};if(store&&reader_revisions_close(&store,&close)!=READER_REV_OK)return 4;
  std::cout<<"{\"status\":"<<(int)status<<",\"sqlite_code\":"<<error.sqlite_code<<",\"message\":"<<quote(error.message)<<",\"created\":"<<created<<",\"applied\":"<<applied<<','<<metadata(info)
    <<",\"state\":{\"revisions\":"<<state.revisions<<",\"heads\":"<<state.heads<<",\"missing_parents\":"<<state.missing_parents<<",\"foreign_parents\":"<<state.foreign_parents
    <<",\"projection_safe\":"<<state.projection_safe<<",\"deleted\":"<<state.deleted<<",\"requires_restore\":"<<state.requires_restore<<"},\"heads\":"<<array(observed.heads)<<",\"outbox\":"<<array(observed.queue)<<",\"nested_status\":"<<nested<<extra<<"}\n";
  return 0;
}catch(const std::exception &){std::cerr<<"consumer input/output failure\n";return 2;}}
