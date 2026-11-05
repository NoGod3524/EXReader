/* SPDX-License-Identifier: MIT */
/* Installed public API consumer. The separate fault target alone adds hooks. */
#include <exr_webdav_managed.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <thread>
#include <chrono>
#include <fcntl.h>
#include <unistd.h>
#include <sys/stat.h>
#include <cerrno>
static unsigned long long received=0;
static void progress(void *,uint64_t n){received=n;}
static int cancellation(void *){return std::getenv("MANAGED_CANCEL")&&received>0;}
static void observation(const char *label,int status,const exr_webdav_managed_snapshot &s,int published=0,uint64_t bytes=0) {
  printf("OBS {\"label\":\"%s\",\"pid\":%ld,\"euid\":%u,\"status\":%d,\"enabled\":%d,\"pool_status\":%d,"
    "\"published\":%d,\"bytes\":%llu,\"last_published\":%d,\"pending\":%u,\"uncertain\":%d,\"errno\":%d,\"exhausted\":%d,\"cleaned\":%u,\"roots\":[",
    label,(long)getpid(),(unsigned)geteuid(),status,s.enabled,s.status,published,(unsigned long long)bytes,
    s.published,s.cleanup_pending,s.receipt_uncertain,s.native_error,s.capacity_exhausted,s.cleaned);
  for(unsigned i=0;i<s.roots;i++){
    const auto &r=s.root[i];
    printf("%s{\"leaf\":\"%s\",\"uuid\":\"%s\",\"slots\":%u,\"pending\":%u,\"status\":%d,\"uncertain\":%d,\"unbound\":%d}",
      i?",":"",r.leaf,r.uuid,r.slots,r.pending,r.status,r.receipt_uncertain,r.unbound);
  }
  printf("]}\n");fflush(stdout);
}
#ifdef EXR_MANAGED_FAULT_WORKER
static const char *profile;
static void hook(const char *phase) {
  const char *requested=std::getenv("MANAGED_HOLD");
  if(requested&&!std::strcmp(requested,phase)){
    printf("HELD %s %ld\n",phase,(long)getpid());fflush(stdout);for(;;)pause();
  }
  const char *deny=std::getenv("MANAGED_DENY");
  if(!deny||std::strcmp(deny,phase))return;
  namespace fs=std::filesystem;
  for(const auto &root:fs::directory_iterator(fs::path(profile)/"webdav-managed-v1")){
    if(root.path().filename().string().rfind("root-",0)!=0)continue;
    if(!std::strcmp(phase,"linked")){if(chmod(root.path().c_str(),0500))std::abort();}
    else for(const auto &tx:fs::directory_iterator(root.path())){
      if(tx.path().filename().string().rfind("tx-",0))continue;
      if(chmod(tx.path().c_str(),0500))std::abort();
      // Existing payload unlink is checked by the component. The independent
      // canary uses a separate private directory to avoid an unknown tx entry.
      fs::path cd=fs::path(profile)/"canary";fs::create_directory(cd);chmod(cd.c_str(),0700);
      int fd=open((cd/"c").c_str(),O_WRONLY|O_CREAT|O_EXCL,0600);if(fd<0)std::abort();close(fd);
      chmod(cd.c_str(),0500);errno=0;int rc=unlink((cd/"c").c_str());int e=errno;struct stat st{};stat(cd.c_str(),&st);
      printf("CANARY {\"pid\":%ld,\"euid\":%u,\"rc\":%d,\"errno\":%d,\"mode\":%u}\n",
        (long)getpid(),(unsigned)geteuid(),rc,e,(unsigned)(st.st_mode&07777));fflush(stdout);
      chmod(cd.c_str(),0700);unlink((cd/"c").c_str());rmdir(cd.c_str());
    }
  }
}
extern "C" void exr_wc_test_hook(const char *phase,uint32_t,uint32_t){hook(phase);}
extern "C" void exr_webdav_managed_test_hook(const char *phase){hook(phase);}
#endif
int main(int argc,char **argv){
  if(argc<3)return 2;
#ifdef EXR_MANAGED_FAULT_WORKER
  profile=argv[2];
#endif
  exr_webdav_managed_snapshot view{};
  if(!std::strcmp(argv[1],"recover")){
    int rc=exr_webdav_managed_recover_profile(argv[2],&view);observation("recover",rc,view);return 0;
  }
  if(argc<7)return 2;
  exr_webdav_config config{};config.root_url=argv[3];config.authorization=std::getenv("MANAGED_AUTH");config.timeout_ms=5000;
  exr_webdav_client *client=nullptr;exr_webdav_error error{};
  if(exr_webdav_create(&config,&client,&error)!=EXR_DAV_OK)return 3;
  int enabled=exr_webdav_managed_enable(client,argv[2],&error);
  exr_webdav_managed_observe(client,&view);observation("enable",enabled,view);
  if(!std::strcmp(argv[1],"hold")){
    printf("HELD client %ld\n",(long)getpid());fflush(stdout);for(;;)pause();
  }
  unsigned count=argc>7?(unsigned)std::strtoul(argv[7],nullptr,10):1;
  for(unsigned i=0;i<count;i++){
    std::string name=argv[5];if(count>1)name+="-"+std::to_string(i);
    received=0;exr_webdav_control control{cancellation,progress,nullptr};exr_webdav_download result{};
    int code=exr_webdav_download_file(client,argv[6],argv[4],name.c_str(),&control,&result,&error);
    exr_webdav_managed_observe(client,&view);observation("download",code,view,result.published,result.bytes);
    if(code!=EXR_DAV_OK)break;
  }
  exr_webdav_free(client);return 0;
}
