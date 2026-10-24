/* SPDX-License-Identifier: MIT */
/* Installed consumer: drives an actual reader_session plus its own revisions
 * handle and prints one JSON line per command for the Actions acceptance
 * script. No network handle, no SQL and no store pointer leaves this file. */
#include <reader_session.h>
#include <reader_sync_view.h>
#include <cstdio>
#include <cstdlib>
#include <iostream>
#include <string>
#include <thread>
#include <vector>
#ifdef _WIN32
#include <windows.h>
#include <shellapi.h>
#endif
extern "C" int c_contract(void);
namespace {
std::string quote(const std::string &s){
  std::string out="\"";
  for(unsigned char c:s){
    if(c=='"'||c=='\\'){out+='\\';out+=(char)c;}
    else if(c<32){char b[8];std::snprintf(b,sizeof(b),"\\u%04x",c);out+=b;}
    else out+=(char)c;
  }
  return out+"\"";
}
std::vector<std::string> arguments(int argc,char **argv){
  std::vector<std::string> a;
#ifdef _WIN32
  int count=0;wchar_t **wide=CommandLineToArgvW(GetCommandLineW(),&count);if(!wide)return a;
  for(int n=0;n<count;n++){
    int bytes=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide[n],-1,nullptr,0,nullptr,nullptr);
    if(!bytes){LocalFree(wide);return {};}
    std::vector<char> value((size_t)bytes);
    WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide[n],-1,value.data(),bytes,nullptr,nullptr);
    a.emplace_back(value.data());
  }
  LocalFree(wide);(void)argc;(void)argv;
#else
  (void)argc;(void)argv;for(int n=0;n<argc;n++)a.emplace_back(argv[n]);
#endif
  return a;
}
std::string rows_json(const std::vector<reader_sync_view_row> &rows){
  std::string out="[";
  for(size_t i=0;i<rows.size();i++){
    if(i)out+=',';
    const reader_sync_view_row &r=rows[i];
    out+="{\"id\":"+quote(r.revision_id)+",\"kind\":"+quote(r.entity_kind)+",\"op\":"+quote(r.operation)
      +",\"bytes\":"+std::to_string(r.bytes)+",\"attempts\":"+std::to_string(r.attempts)
      +",\"code\":"+std::to_string(r.last_revision_code)+",\"reason\":"+std::to_string((int)r.last_reason)
      +",\"conflict\":"+std::to_string(r.conflict)+"}";
  }
  return out+"]";
}
std::string summary_json(const reader_sync_view_summary &v){
  return "{\"phase\":"+std::to_string((int)v.phase)+",\"reason\":"+std::to_string((int)v.reason)
    +",\"phase_text\":"+quote(reader_sync_view_phase_text(v.phase))+",\"reason_text\":"+quote(reader_sync_view_reason_text(v.reason))
    +",\"session_status\":"+std::to_string(v.session_status)+",\"http\":"+std::to_string(v.http_status)
    +",\"dav\":"+std::to_string(v.dav_code)+",\"revision_code\":"+std::to_string(v.revision_code)
    +",\"attempt\":"+std::to_string(v.attempt)+",\"sweeps\":"+std::to_string(v.completed_sweeps)
    +",\"operations\":"+std::to_string(v.operations)+",\"pushed\":"+std::to_string(v.pushed_operations)
    +",\"pulled\":"+std::to_string(v.pulled_operations)+",\"originals_verified\":"+std::to_string(v.originals_verified_operations)
    +",\"metadata_wait\":"+std::to_string(v.metadata_wait_observations)+",\"original_wait\":"+std::to_string(v.original_wait_observations)
    +",\"transfer_bytes\":"+std::to_string(v.transfer_bytes)+",\"shard\":"+std::to_string(v.shard)
    +",\"completed_shards\":"+std::to_string(v.completed_shards)+",\"shard_count\":"+std::to_string(v.shard_count)
    +",\"cursor\":"+quote(v.cursor)+",\"sweep_complete\":"+std::to_string(v.sweep_complete)
    +",\"library_complete\":"+std::to_string(v.library_complete)+",\"resumable\":"+std::to_string(v.resumable)
    +",\"outbox_included\":"+std::to_string(v.outbox_included)+",\"pending\":"+std::to_string(v.pending_records)
    +",\"retried\":"+std::to_string(v.retried_records)+",\"conflicts\":"+std::to_string(v.conflict_records)
    +",\"more_may_exist\":"+std::to_string(v.more_may_exist)+",\"conflicts_checked\":"+std::to_string(v.conflicts_checked)+"}";
}
void emit_capture(const char *cmd,reader_sync_view_status status,const reader_sync_view_error &error,
    const reader_sync_view_summary *summary,const std::vector<reader_sync_view_row> &rows,int out_set){
  std::cout<<"{\"cmd\":\""<<cmd<<"\",\"status\":"<<(int)status<<",\"out_set\":"<<out_set
    <<",\"err_session\":"<<error.session_status<<",\"err_revision\":"<<error.revision_code
    <<",\"message\":"<<quote(error.message)<<",\"summary\":"<<(summary?summary_json(*summary):"null")
    <<",\"rows\":"<<rows_json(rows)<<"}"<<std::endl;
}
}
int main(int argc,char **argv){
  try{
    std::vector<std::string> a=arguments(argc,argv);
    if(c_contract()||a.size()!=7)return 2;
    reader_session_config config{};
    config.dav.root_url=a[1].c_str();config.dav.authorization=std::getenv("READER_TEST_AUTH");
    config.product_path=a[2].c_str();config.private_directory=a[3].c_str();
    config.original_directory=a[4].c_str();config.account_id=a[5].c_str();
    config.dav.timeout_ms=(unsigned)std::stoul(a[6]);
    reader_session *session=nullptr;
    int created=reader_session_create(&config,&session);
    std::cout<<"{\"create\":"<<created<<"}"<<std::endl;
    if(created)return 0;
    reader_revisions *revisions=nullptr;
    reader_sync_view_snapshot *snapshot=nullptr;
    auto capture=[&](const char *cmd,reader_revisions *handle,size_t limit,int conflicts){
      reader_sync_view_options options{};options.row_limit=limit;options.detect_conflicts=conflicts;
      reader_sync_view_snapshot *out=nullptr;reader_sync_view_error error{};
      reader_sync_view_status status=reader_sync_view_capture(session,handle,&options,&out,&error);
      reader_sync_view_summary summary{};
      std::vector<reader_sync_view_row> rows;
      int have=0;
      if(status==READER_SYNC_VIEW_OK&&out){
        if(reader_sync_view_summary_get(out,&summary)==READER_SYNC_VIEW_OK)have=1;
        reader_sync_view_row buffer[READER_SYNC_VIEW_MAX_ROWS];size_t copied=0;
        if(reader_sync_view_rows(out,0,buffer,READER_SYNC_VIEW_MAX_ROWS,&copied)==READER_SYNC_VIEW_OK)
          rows.assign(buffer,buffer+copied);
      }
      if(snapshot)reader_sync_view_release(&snapshot);
      snapshot=out;
      emit_capture(cmd,status,error,have?&summary:nullptr,rows,out?1:0);
    };
    std::string line;
    while(std::getline(std::cin,line)){
      if(line=="open"){
        reader_revision_error error{};
        int status=revisions?READER_REV_OK:(int)reader_revisions_open(a[2].c_str(),&revisions,&error);
        std::cout<<"{\"cmd\":\"open\",\"status\":"<<status<<"}"<<std::endl;
      }else if(line=="close-revisions"){
        reader_revision_error error{};int status=READER_REV_OK;
        if(revisions)status=(int)reader_revisions_close(&revisions,&error);
        std::cout<<"{\"cmd\":\"close-revisions\",\"status\":"<<status<<"}"<<std::endl;
      }else if(line.rfind("capture-norev ",0)==0){
        capture("capture-norev",nullptr,(size_t)std::stoul(line.substr(14)),0);
      }else if(line.rfind("capture-wrong-thread ",0)==0){
        size_t limit=(size_t)std::stoul(line.substr(21));
        reader_sync_view_snapshot *out=nullptr;reader_sync_view_error error{};reader_sync_view_status status=READER_SYNC_VIEW_OK;
        std::thread worker([&]{
          reader_sync_view_options options{};options.row_limit=limit;
          status=reader_sync_view_capture(session,revisions,&options,&out,&error);});
        worker.join();
        emit_capture("capture-wrong-thread",status,error,nullptr,{},out?1:0);
      }else if(line.rfind("capture ",0)==0){
        size_t space=line.find(' ',8);
        size_t limit=(size_t)std::stoul(line.substr(8,space-8));
        int conflicts=space==std::string::npos?0:std::stoi(line.substr(space+1));
        capture("capture",revisions,limit,conflicts);
      }else if(line.rfind("capture-threads ",0)==0){
        size_t space=line.find(' ',16);
        unsigned threads=(unsigned)std::stoul(line.substr(16,space-16));
        unsigned iterations=(unsigned)std::stoul(line.substr(space+1));
        unsigned ok=0,failed=0;int first=0;int first_revision=0;
        std::vector<std::thread> pool;
        for(unsigned n=0;n<threads;n++)pool.emplace_back([&]{
          for(unsigned i=0;i<iterations;i++){
            reader_sync_view_options options{};options.row_limit=4;
            reader_sync_view_snapshot *out=nullptr;reader_sync_view_error error{};
            reader_sync_view_status status=reader_sync_view_capture(session,nullptr,&options,&out,&error);
            if(status==READER_SYNC_VIEW_OK&&out&&reader_sync_view_release(&out)==READER_SYNC_VIEW_OK)ok++;
            else{failed++;if(!first){first=(int)status;first_revision=error.revision_code;}}
          }
        });
        for(std::thread &entry:pool)entry.join();
        std::cout<<"{\"cmd\":\"capture-threads\",\"ok\":"<<ok<<",\"failed\":"<<failed
          <<",\"first_status\":"<<first<<",\"first_revision\":"<<first_revision<<"}"<<std::endl;
      }else if(line.rfind("rows-null",0)==0){
        size_t copied=7;int status=(int)reader_sync_view_rows(snapshot,0,nullptr,4,&copied);
        std::cout<<"{\"cmd\":\"rows-null\",\"status\":"<<status<<",\"copied\":"<<copied<<"}"<<std::endl;
      }else if(line.rfind("rows ",0)==0){
        size_t space=line.find(' ',5);
        size_t offset=(size_t)std::stoul(line.substr(5,space-5));
        size_t capacity=(size_t)std::stoul(line.substr(space+1));
        reader_sync_view_row buffer[READER_SYNC_VIEW_MAX_ROWS];size_t copied=99;
        int status=(int)reader_sync_view_rows(snapshot,offset,buffer,capacity>READER_SYNC_VIEW_MAX_ROWS?READER_SYNC_VIEW_MAX_ROWS:capacity,&copied);
        std::vector<reader_sync_view_row> rows;
        if(status==READER_SYNC_VIEW_OK)rows.assign(buffer,buffer+copied);
        std::cout<<"{\"cmd\":\"rows\",\"status\":"<<status<<",\"offset\":"<<offset<<",\"copied\":"<<copied
          <<",\"rows\":"<<rows_json(rows)<<"}"<<std::endl;
      }else if(line=="summary"){
        reader_sync_view_summary summary{};
        int status=(int)reader_sync_view_summary_get(snapshot,&summary);
        std::cout<<"{\"cmd\":\"summary\",\"status\":"<<status<<",\"summary\":"<<(status==0?summary_json(summary):"null")<<"}"<<std::endl;
      }else if(line=="release"){
        int status=(int)reader_sync_view_release(&snapshot);
        std::cout<<"{\"cmd\":\"release\",\"status\":"<<status<<",\"null_after\":"<<(snapshot?0:1)<<"}"<<std::endl;
      }else if(line=="release-null"){
        reader_sync_view_snapshot *empty=nullptr;int status=(int)reader_sync_view_release(&empty);
        int null_status=(int)reader_sync_view_release(nullptr);
        std::cout<<"{\"cmd\":\"release-null\",\"status\":"<<status<<",\"null_pointer\":"<<null_status<<"}"<<std::endl;
      }else if(line=="observe"){
        reader_session_snapshot view{};int status=(int)reader_session_observe(session,&view);
        std::cout<<"{\"cmd\":\"observe\",\"status\":"<<status<<",\"state\":"<<(int)view.state
          <<",\"attempt\":"<<view.attempt<<",\"steps\":"<<view.steps<<",\"sweeps\":"<<view.completed_sweeps
          <<",\"completed_shards\":"<<view.completed_shards<<",\"pending_metadata\":"<<view.pending_metadata_observations
          <<",\"pending_original\":"<<view.pending_original_observations<<"}"<<std::endl;
      }else if(line=="start"||line=="cancel"||line=="close-session"){
        int status=line=="start"?(int)reader_session_start(session):line=="cancel"?(int)reader_session_cancel(session):(int)reader_session_request_close(session);
        std::cout<<"{\"cmd\":\""<<line<<"\",\"status\":"<<status<<"}"<<std::endl;
      }else if(line=="destroy-session"){
        int status=(int)reader_session_destroy(&session);
        std::cout<<"{\"cmd\":\"destroy-session\",\"status\":"<<status<<",\"null_after\":"<<(session?0:1)<<"}"<<std::endl;
      }else if(line=="exit"){
        std::cout<<"{\"cmd\":\"exit\"}"<<std::endl;
        return session?3:0;
      }else{
        std::cout<<"{\"cmd\":\"unknown\"}"<<std::endl;return 2;
      }
    }
    return 3;
  }catch(...){std::cerr<<"status-view consumer failed\n";return 2;}
}
