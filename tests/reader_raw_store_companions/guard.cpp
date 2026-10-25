#include <reader_sync.h>
#include <filesystem>
#include <cstdlib>
#include <thread>
#include <iostream>
int main(int argc,char **argv){
  if(argc!=3)return 2;namespace fs=std::filesystem;fs::path work=fs::u8path(argv[2]);fs::create_directories(work);
  exr_webdav_config dc{};dc.root_url=argv[1];dc.authorization=std::getenv("READER_TEST_AUTH");exr_webdav_client *dav=nullptr;if(exr_webdav_create(&dc,&dav,nullptr)!=EXR_DAV_OK)return 1;
  reader_revisions *raw=nullptr,*old=nullptr;reader_sync *sync=nullptr;reader_sync_report report{};reader_sync_error error{};
  if(reader_revisions_open_raw_v3((work/"raw.sqlite").u8string().c_str(),&raw,nullptr)!=READER_REV_OK)return 1;
  reader_sync_config c{dav,raw,argv[2],nullptr,nullptr};if(reader_sync_create_raw_v3(&c,&sync,&error)!=READER_SYNC_OK)return 1;
  if(reader_sync_step(sync,0,"",100,nullptr,&report,&error)!=READER_SYNC_ARGUMENT||report.pushed||report.pulled)return 1;
  reader_sync_status wrong=READER_SYNC_OK;std::thread thread([&]{wrong=reader_sync_step_raw_v3(sync,0,"",100,nullptr,&report,&error);});thread.join();if(wrong!=READER_SYNC_ARGUMENT)return 1;reader_sync_free(sync);sync=nullptr;
  if(reader_revisions_open((work/"old.sqlite").u8string().c_str(),&old,nullptr)!=READER_REV_OK)return 1;c.revisions=old;
  if(reader_sync_create_raw_v3(&c,&sync,&error)!=READER_SYNC_OK)return 1;
  if(reader_sync_step_raw_v3(sync,0,"",100,nullptr,&report,&error)!=READER_SYNC_REVISION||error.revision_code!=READER_REV_ARGUMENT||report.pushed||report.pulled)return 1;
  reader_sync_free(sync);reader_revisions_close(&old,nullptr);reader_revisions_close(&raw,nullptr);exr_webdav_free(dav);
  std::cout<<"{\"accepted\":true,\"legacy_step_refused\":true,\"wrong_owner_refused\":true,\"wrong_store_capability_refused\":true}"<<std::endl;return 0;
}
