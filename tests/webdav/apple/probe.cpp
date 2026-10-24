/* SPDX-License-Identifier: MIT */
#include <TargetConditionals.h>
#define main source_consumer_main
#include "../consumer/main.cpp"
#undef main
#include <atomic>
#include <chrono>
#include <thread>

int apple_dav_probe(int argc,char **argv){
  if(argc!=12)return 2;
  std::string action=argv[1];
  if(action!="mkcol"&&action!="put"&&action!="native-owner"&&action!="native-reentry")
    return source_consumer_main(argc,argv);
  exr_webdav_config config{};config.root_url=argv[2];config.authorization=argv[3];
  config.timeout_ms=(unsigned)std::strtoul(argv[10],nullptr,10);
  exr_webdav_client *client=nullptr;exr_webdav_error error{};
  auto status=exr_webdav_create(&config,&client,&error);
  cancel_state cancel{std::strtoull(argv[11],nullptr,10),0};exr_webdav_control control{cancelled,progress,&cancel};
  bool owner_ok=false,reentry_ok=false,callback_owner=true,settled=true;uint64_t received=0;
  if(status==EXR_DAV_OK){
    if(action=="mkcol")status=exr_webdav_make_collection(client,argv[4],&control,&error);
    else if(action=="put"){
      std::string file=std::string(argv[5])+"/"+argv[6];
      status=exr_webdav_publish_file(client,argv[4],file.c_str(),std::strtoull(argv[7],nullptr,10),&control,&error);
    }else if(action=="native-owner"){
      std::thread other([&]{exr_webdav_listing listing{};exr_webdav_error local{};
        owner_ok=exr_webdav_list(client,"",nullptr,&listing,&local)==EXR_DAV_ARGUMENT;
        exr_webdav_listing_free(&listing);exr_webdav_free(client);});other.join();
      exr_webdav_listing listing{};status=exr_webdav_list(client,"",nullptr,&listing,&error);exr_webdav_listing_free(&listing);
    }else{
      struct callback_state {exr_webdav_client *client;std::thread::id owner;bool entered=false,refused=true,on_owner=true;uint64_t calls=0;};
      callback_state state{client,std::this_thread::get_id()};
      exr_webdav_control nested{};nested.context=&state;
      nested.progress=[](void *context,uint64_t){auto &s=*(callback_state *)context;++s.calls;
        s.on_owner=s.on_owner&&(s.owner==std::this_thread::get_id());
        if(!s.entered){s.entered=true;exr_webdav_listing listing{};exr_webdav_error local{};
          s.refused=exr_webdav_list(s.client,"",nullptr,&listing,&local)==EXR_DAV_ARGUMENT;
          exr_webdav_listing_free(&listing);exr_webdav_free(s.client);}};
      exr_webdav_download download{};
      status=exr_webdav_download_file(client,argv[4],argv[5],argv[6],&nested,&download,&error);
      received=download.bytes;reentry_ok=state.entered&&state.refused;callback_owner=state.on_owner;
      uint64_t calls=state.calls;std::this_thread::sleep_for(std::chrono::milliseconds(100));settled=calls==state.calls;
    }
  }
  exr_webdav_free(client);
  std::cout<<"{\"status\":"<<(int)status<<",\"http_status\":"<<error.http_status
    <<",\"owner_ok\":"<<(owner_ok?"true":"false")<<",\"reentry_ok\":"<<(reentry_ok?"true":"false")
    <<",\"callback_owner\":"<<(callback_owner?"true":"false")<<",\"settled\":"<<(settled?"true":"false")
    <<",\"bytes\":"<<received<<",\"progress\":"<<cancel.received<<"}\n";
  return 0;
}
#if !TARGET_OS_IPHONE
int main(int argc,char **argv){return apple_dav_probe(argc,argv);}
#endif
