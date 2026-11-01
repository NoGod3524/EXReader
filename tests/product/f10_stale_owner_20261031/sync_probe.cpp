/* SPDX-License-Identifier: MIT
 * Installed public consumers. Hook build is labelled separately; old build
 * uses the sealed b5e7 WebDAV library, not an imitation old parser. */
#include <exr_webdav.h>
#include <exr_webdav_managed.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <filesystem>
#include <iostream>
#include <string>
#include <vector>
#include <unistd.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <signal.h>
#ifndef F10_OLD_CLIENT
#include <exr_webdav_cleanup.h>
#endif
#if !defined(F10_OLD_CLIENT) && !defined(F10_BOUNDARY)
#include <reader_sync.h>
#include <reader_revisions.h>
#endif
namespace fs=std::filesystem;
static void row(const char *key,long long value){std::cout<<"{\""<<key<<"\":"<<value<<"}"<<std::endl;}
#ifdef F10_BOUNDARY
extern "C" void exr_webdav_managed_test_hook(const char *name){
  const char *wanted=std::getenv("F10_KILL_AT");
  if(wanted&&std::strcmp(wanted,name)==0){row("boundary",1);raise(SIGKILL);}
}
#endif
#ifndef F10_OLD_CLIENT
static const std::string body(131079,'Q');
struct reader {int fd=-1;std::string mode;uint64_t offset=0;unsigned calls=0;bool failed=false;};
static exr_webdav_status source(void *ctx,uint64_t offset,void *buffer,size_t count,size_t *got){
  auto &r=*(reader*)ctx;*got=0;r.calls++;
  if(offset!=r.offset||offset>body.size()||count>body.size()-offset){r.failed=true;return EXR_DAV_IO;}
  if(r.mode=="throw")throw 42;
  if(r.mode=="error"){r.failed=true;return EXR_DAV_IO;}
  if(r.mode=="cancel"){r.failed=true;return EXR_DAV_CANCELLED;}
  if(r.mode=="short"){*got=count-1;return EXR_DAV_OK;}
  if(r.mode=="overflow"){*got=count+1;return EXR_DAV_OK;}
  if(r.fd>=0){ssize_t n=pread(r.fd,buffer,count,(off_t)offset);if(n!=(ssize_t)count)return EXR_DAV_IO;}
  else std::memcpy(buffer,body.data()+offset,count);
  *got=count;r.offset+=count;return EXR_DAV_OK;
}
static uint32_t crc(const std::string &s){uint32_t c=~0u;for(unsigned char b:s){c^=b;for(int i=0;i<8;i++)c=(c>>1)^(0xedb88320u&(0u-(c&1)));}return ~c;}
static void capacity(const fs::path &profile,bool mixed){
  fs::create_directory(profile/"webdav-managed-v1");chmod((profile/"webdav-managed-v1").c_str(),0700);
  int d=open((profile/"webdav-managed-v1").c_str(),O_RDONLY|O_DIRECTORY);
  int lock=openat(d,"registry.lock",O_CREAT|O_EXCL|O_WRONLY,0600);close(lock);
  std::string reg=std::string("EXReader managed registry ")+(mixed?"2":"1")+"\n"+profile.string()+"\n16\n";
  for(unsigned i=0;i<16;i++){
    char leaf[38];std::snprintf(leaf,sizeof(leaf),"root-%032x",i+1);
    exr_wc_root *root=nullptr;char uuid[33]{};
    if(exr_wc_create_at(d,leaf,&root,uuid)!=EXR_WC_OK)throw 1;
    exr_wc_close(&root);
    reg+=std::string(leaf)+" "+uuid+(mixed?(i==15?" S":" D"):"")+"\n";
  }
  char h[10];std::snprintf(h,sizeof(h),"%08x",crc(reg));reg+=std::string(h)+"\n";
  int f=openat(d,"registry",O_CREAT|O_EXCL|O_WRONLY,0600);
  if(write(f,reg.data(),reg.size())!=(ssize_t)reg.size())throw 1;
  fsync(f);close(f);fsync(d);close(d);
}
#endif
#if !defined(F10_OLD_CLIENT) && !defined(F10_BOUNDARY)
static int original(void *context,const char *key,char *out,size_t size){
  std::string k=key;size_t pos=k.find(':');if(pos==std::string::npos)return 1;
  std::string name=(*(fs::path*)context/(k.substr(pos+1)+"."+k.substr(0,pos))).string();
  if(name.size()>=size||!fs::exists(name))return 1;
  std::memcpy(out,name.c_str(),name.size()+1);return 0;
}
static void inspect_received(reader_revisions *rev,const char *wire_path){
  std::ifstream input(wire_path);std::string expected((std::istreambuf_iterator<char>(input)),{});
  reader_revision_info info{};int code=reader_revision_validate_raw_v3(rev,expected.data(),expected.size(),nullptr,&info,nullptr);
  if(code){row("inspect_error",code);return;}
  char *wire=nullptr;size_t bytes=0;reader_revision_info actual{};
  code=reader_revision_get_raw_v3(rev,info.revision_id,&wire,&bytes,&actual,nullptr);
  row("received",code==READER_REV_OK);row("exact_wire",code==READER_REV_OK&&bytes==expected.size()&&std::memcmp(wire,expected.data(),bytes)==0);
  reader_revision_bytes_free(wire);
}
static int step(const fs::path &profile,const char *url,const char *wire_path,bool seed,bool pull=false,bool inspect_only=false){
  reader_revisions *rev=nullptr;reader_revision_error re{};
  std::string db=(profile/"catalog.sqlite").string();
  int status=reader_revisions_open_raw_v3(db.c_str(),&rev,&re);
  if(status){row("status",status);return 1;}
  if(inspect_only){inspect_received(rev,wire_path);reader_revisions_close(&rev,nullptr);return 0;}
  if(seed){
    std::ifstream in(wire_path);std::string wire((std::istreambuf_iterator<char>(in)),{});
    reader_revision_info info{};int created=0;
    status=reader_revision_local_raw_v3(rev,wire.data(),wire.size(),&info,&created,&re);
    row("seed",status);reader_revisions_close(&rev,nullptr);return status?1:0;
  }
  exr_webdav_client *dav=nullptr;exr_webdav_error de{};exr_webdav_config dc{};
  dc.root_url=url;dc.timeout_ms=15000;
  status=exr_webdav_create(&dc,&dav,&de);
  std::string cache=(profile/"cache").string(),managed=(profile/"managed").string();
  if(!status)status=exr_webdav_managed_enable(dav,managed.c_str(),&de);
  reader_sync *sync=nullptr;reader_sync_error se{};reader_sync_report result{};
  fs::path originals=profile/"originals";
  reader_sync_config cfg{dav,rev,cache.c_str(),original,&originals};
  if(!status)status=reader_sync_create_raw_v3(&cfg,&sync,&se);
  exr_webdav_control control{};std::string stop=(profile/"cancel").string();
  control.context=&stop;control.cancelled=[](void *p){return fs::exists(*(std::string*)p)?1:0;};
  if(!status)status=reader_sync_step_raw_v3(sync,0,"",100,&control,&result,&se);
  row("status",status);row("pushed",result.pushed);row("dav_code",se.dav_code);row("revision_code",se.revision_code);
  if(pull){row("pulled",result.pulled);row("after_empty",result.after[0]==0);inspect_received(rev,wire_path);}
  unsigned pending=0;
  auto count=[](void *ctx,const reader_revision_outbox_row *){++*(unsigned*)ctx;return 0;};
  reader_revision_outbox_raw_v3(rev,100,count,&pending,nullptr);row("outbox",pending);
  exr_webdav_managed_snapshot view{};exr_webdav_managed_observe(dav,&view);row("cleanup_pending",view.cleanup_pending);
  reader_sync_free(sync);reader_revisions_close(&rev,nullptr);exr_webdav_free(dav);return 0;
}
#endif
int main(int argc,char **argv){try{
  if(argc<3)return 2;std::string mode=argv[1];fs::path profile=fs::absolute(argv[2]);
#ifdef F10_OLD_CLIENT
  exr_webdav_managed_snapshot view{};row("recover",exr_webdav_managed_recover_profile(profile.c_str(),&view));return 0;
#else
  if(mode=="capacity"){capacity(profile,argc>3&&std::string(argv[3])=="mixed");row("prepared",1);return 0;}
  if(mode=="legacy-owned"){
    std::ifstream f(profile/"webdav-managed-v1/registry");std::string line;for(int i=0;i<4;i++)std::getline(f,line);
    size_t split=line.find(' ');std::string leaf=line.substr(0,split),uuid=line.substr(split+1);
    int d=open((profile/"webdav-managed-v1").c_str(),O_RDONLY|O_DIRECTORY);exr_wc_root *root=nullptr;exr_wc_tx *tx=nullptr;int fd=-1;
    if(exr_wc_open_at(d,leaf.c_str(),uuid.c_str(),&root)||exr_wc_begin(root,&tx,&fd))throw 1;
    if(write(fd,body.data(),body.size())!=(ssize_t)body.size())throw 1;
    row("owned",1);raise(SIGKILL);return 8;
  }
#if !defined(F10_BOUNDARY)
  if(mode=="step"||mode=="seed"||mode=="pull"||mode=="inspect"){if(argc!=5)return 2;return step(profile,argv[3],argv[4],mode=="seed",mode=="pull",mode=="inspect");}
#endif
  if(mode=="recover-current"){exr_webdav_managed_snapshot view{};row("recover",exr_webdav_managed_recover_profile(profile.c_str(),&view));row("pending",view.cleanup_pending);return 0;}
  const char *url=argc>3?argv[3]:"https://localhost:1/dav/";
  exr_webdav_config cfg{};cfg.root_url=url;cfg.timeout_ms=10000;
  exr_webdav_client *dav=nullptr;exr_webdav_error error{};
  int code=exr_webdav_create(&cfg,&dav,&error);row("create",code);if(code)return 3;
  if(mode=="get-error"){
    unsigned calls=0;uint64_t received=123;
    auto consume=[](void *context,const void *,size_t)->exr_webdav_status{++*(unsigned*)context;return EXR_DAV_IO;};
    code=exr_webdav_read_stream(dav,"body",body.size(),consume,&calls,nullptr,&received,&error);
    row("get",code);row("calls",calls);row("received",received);exr_webdav_free(dav);return 0;
  }
  if(mode=="callback"){
    reader r;r.mode=argc>4?argv[4]:"normal";
    uint64_t size=r.mode=="zero"?0:r.mode=="limit"?UINT64_C(128)*1024*1024+1:body.size();
    code=exr_webdav_publish_source(dav,"body",size,source,&r,nullptr,&error);
    row("put",code);row("calls",r.calls);row("offset",r.offset);exr_webdav_free(dav);return 0;
  }
  code=exr_webdav_managed_enable(dav,profile.c_str(),&error);row("enable",code);
  if(code){exr_webdav_free(dav);return 0;}
  exr_webdav_owned_snapshot *snapshot=nullptr;int fd=-1;std::string command;
  while(std::getline(std::cin,command)){
    if(command=="begin")row("begin",exr_webdav_snapshot_begin(dav,&snapshot,&fd,&error));
    else if(command=="busy"){
      exr_webdav_owned_snapshot *other=nullptr;int otherfd=-1;
      row("busy",exr_webdav_snapshot_begin(dav,&other,&otherfd,&error));
      exr_webdav_snapshot_close(&other,&error);
    }else if(command=="write")row("write",write(fd,body.data(),body.size()));
    else if(command=="seal")row("seal",exr_webdav_snapshot_seal(snapshot,body.size(),&fd,&error));
    else if(command=="put"){reader r;r.fd=fd;row("put",exr_webdav_publish_source(dav,"body",body.size(),source,&r,nullptr,&error));row("offset",r.offset);}
    else if(command=="close"){row("close",exr_webdav_snapshot_close(&snapshot,&error));row("fd_closed",fcntl(fd,F_GETFD)==-1);}
    else if(command=="observe"){exr_webdav_managed_snapshot v{};exr_webdav_managed_observe(dav,&v);row("roots",v.roots);row("pending",v.cleanup_pending);}
    else if(command=="download"){exr_webdav_download d{};row("download",exr_webdav_download_file(dav,"body",profile.c_str(),"downloaded",nullptr,&d,&error));}
    else if(command=="exit")break;
    else return 4;
  }
  exr_webdav_snapshot_close(&snapshot,&error);exr_webdav_free(dav);return 0;
#endif
}catch(...){row("exception",1);return 5;}}
