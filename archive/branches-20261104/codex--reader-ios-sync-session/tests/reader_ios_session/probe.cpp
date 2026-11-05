/* SPDX-License-Identifier: MIT */
#define READER_V2_WEBDAV_TEST 1
#define READER_V2_SESSION_TEST 1
#define READER_V2_ENTRY original_reading_v2_main
#include "../reader_reading_v2/consumer/probe.cpp"
#include <reader_session.h>
#include <chrono>
#include <thread>

namespace {
std::vector<std::string> session_runs;
void session_sweep(side &device){
  std::string work=transport_work+"/"+device.name+"-cache";
  std::string originals=&device==&A?transport_work+"/A-originals":work;
  std::filesystem::create_directories(std::filesystem::u8path(work));
  std::filesystem::create_directories(std::filesystem::u8path(originals));
  reader_session_config config{};config.product_path=device.product_path.c_str();
  config.private_directory=work.c_str();config.original_directory=originals.c_str();
  config.account_id="743c61f9-22e4-4df5-aa2b-4bc1e0a19861";
  config.dav.root_url=webdav_root.c_str();config.dav.authorization=std::getenv("READER_TEST_AUTH");config.dav.timeout_ms=15000;
  reader_session *session=nullptr;
  if(reader_session_create(&config,&session)!=READER_SESSION_OK||!session)fatal("actual account session create");
  auto began=std::chrono::steady_clock::now();
  if(reader_session_start(session)!=READER_SESSION_OK)fatal("actual account session start");
  auto returned=std::chrono::steady_clock::now();
  reader_session_snapshot view{};size_t polls=0;
  for(;;){
    if(reader_session_observe(session,&view)!=READER_SESSION_OK)fatal("account observe");++polls;
    if(view.state==READER_SESSION_FINISHED||view.state==READER_SESSION_FAILED||view.state==READER_SESSION_CANCELLED)break;
    if(std::chrono::steady_clock::now()-began>std::chrono::seconds(120))fatal("account sweep outer deadline");
    std::this_thread::sleep_for(std::chrono::milliseconds(5));
  }
  bool complete=view.state==READER_SESSION_FINISHED&&view.status==READER_SESSION_OK&&view.completed_shards==256&&
    view.completed_sweeps==1&&!view.full_library_complete&&!view.pending_metadata_observations&&!view.pending_original_observations;
  expect(complete,std::string(device.name)+" actual session finishes all256 shards without claiming a permanent complete library");
  if(!complete)fatal("account sweep refused "+num(view.state)+"/"+num(view.status)+"/"+num(view.error.dav_code));
  network_pushed+=view.pushed;network_pulled+=view.pulled;
  session_runs.push_back(object().str("device",device.name).set("shards",num(view.completed_shards)).set("sweeps",num(view.completed_sweeps))
    .set("pushed",num(view.pushed)).set("pulled",num(view.pulled)).set("originals_verified",num(view.originals_verified))
    .set("observations",num(polls)).set("start_microseconds",num((unsigned long long)std::chrono::duration_cast<std::chrono::microseconds>(returned-began).count())).dump());
  if(reader_session_destroy(&session)!=READER_SESSION_BUSY||!session)fatal("destroy before CLOSED was accepted");
  if(reader_session_request_close(session)!=READER_SESSION_OK)fatal("session close");
  while(reader_session_observe(session,&view)==READER_SESSION_OK&&view.state!=READER_SESSION_CLOSED){
    if(std::chrono::steady_clock::now()-began>std::chrono::seconds(140))fatal("account close outer deadline");
    std::this_thread::sleep_for(std::chrono::milliseconds(5));
  }
  if(view.state!=READER_SESSION_CLOSED||reader_session_destroy(&session)!=READER_SESSION_OK||session)fatal("CLOSED session destroy");
}
void session_transfer(side &from,side &to){
  auto outgoing=pending(from);if(outgoing.empty())fatal("session has no actual pending revision");
  session_sweep(from);expect(pending(from).empty(),"session remote immutable verification acks the actual outbox");
  session_sweep(to);
  for(const auto &row:outgoing){
    char *left=nullptr,*right=nullptr;size_t ln=0,rn=0;
    expect(reader_revision_get(from.store,row.id.c_str(),&left,&ln,nullptr,nullptr)==READER_REV_OK&&
      reader_revision_get(to.store,row.id.c_str(),&right,&rn,nullptr,nullptr)==READER_REV_OK&&ln==rn&&std::string(left,ln)==std::string(right,rn),
      "actual account session preserves the exact retained revision bytes");
    reader_revision_bytes_free(left);reader_revision_bytes_free(right);
  }
}
}
int ios_reader_session_probe(int argc,char **argv){
  int result=original_reading_v2_main(argc,argv);
  std::string path;for(int i=1;i+1<argc;i+=2)if(!std::strcmp(argv[i],"--report"))path=argv[i+1];
  std::ofstream report(path+".sessions.json",std::ios::binary);
  report<<object().set("accepted",boolean(result==0&&session_runs.size()==38)).set("sessions",array(session_runs))
    .set("count",num(session_runs.size())).set("sdk_pointers_passed_to_network",boolean(false)).dump()<<"\n";
  return result||session_runs.size()!=38?1:0;
}
