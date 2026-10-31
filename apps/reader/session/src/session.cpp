/* SPDX-License-Identifier: MIT */
#include "reader_session.h"
#ifdef EXR_READER_SESSION_MANAGED
#include "reader_session_managed.h"
#endif
#include <atomic>
#include <condition_variable>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#else
#include <fcntl.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <unistd.h>
#endif
namespace fs=std::filesystem;
namespace {
bool bounded(const char *s,size_t maximum){if(!s||!*s)return false;for(size_t n=0;n<=maximum;n++)if(!s[n])return true;return false;}
bool uuid(const char *s){if(!bounded(s,36)||std::strlen(s)!=36)return false;for(size_t n=0;n<36;n++){
  if(n==8||n==13||n==18||n==23){if(s[n]!='-')return false;}
  else if(!((s[n]>='0'&&s[n]<='9')||(s[n]>='a'&&s[n]<='f')))return false;
}return true;}
void wipe(std::string &s){volatile char *p=s.empty()?nullptr:&s[0];for(size_t i=0;i<s.size();i++)p[i]=0;s.clear();}
struct failure {reader_session_status code;reader_sync_error error{};};
struct account_binding {
#ifdef _WIN32
  HANDLE file=INVALID_HANDLE_VALUE;
  ~account_binding(){if(file!=INVALID_HANDLE_VALUE)CloseHandle(file);}
#else
  int file=-1;
  ~account_binding(){if(file>=0)close(file);}
#endif
  void bind(const fs::path &product,const std::string &account,const std::string &root){
    const std::string expected="EXReader account v1\n"+account+"\n"+root+"\n";
    fs::path name=product;name+=".sync-account";char buffer[8400]{};size_t size=0;
#ifdef _WIN32
    file=CreateFileW(name.c_str(),GENERIC_READ|GENERIC_WRITE,0,nullptr,OPEN_ALWAYS,FILE_ATTRIBUTE_NORMAL|FILE_FLAG_OPEN_REPARSE_POINT|FILE_FLAG_WRITE_THROUGH,nullptr);
    if(file==INVALID_HANDLE_VALUE)throw failure{READER_SESSION_ACCOUNT};
    BY_HANDLE_FILE_INFORMATION info{};DWORD got=0;
    if(!GetFileInformationByHandle(file,&info)||(info.dwFileAttributes&(FILE_ATTRIBUTE_REPARSE_POINT|FILE_ATTRIBUTE_DIRECTORY))||
       info.nNumberOfLinks!=1||info.nFileSizeHigh||info.nFileSizeLow>=sizeof(buffer)||!ReadFile(file,buffer,sizeof(buffer),&got,nullptr))throw failure{READER_SESSION_ACCOUNT};
    size=got;
    if(!size){DWORD wrote=0;if(!WriteFile(file,expected.data(),(DWORD)expected.size(),&wrote,nullptr)||wrote!=expected.size()||!FlushFileBuffers(file))throw failure{READER_SESSION_IO};}
#else
    file=open(name.c_str(),O_RDWR|O_CREAT|O_CLOEXEC|O_NOFOLLOW,0600);
    struct stat info{};
    if(file<0||flock(file,LOCK_EX|LOCK_NB)||fstat(file,&info)||!S_ISREG(info.st_mode)||info.st_nlink!=1||
       info.st_size<0||(uint64_t)info.st_size>=sizeof(buffer)||(info.st_mode&077)||info.st_uid!=getuid())throw failure{READER_SESSION_ACCOUNT};
    ssize_t got=read(file,buffer,sizeof(buffer));if(got<0)throw failure{READER_SESSION_IO};size=(size_t)got;
    if(!size){
      ssize_t wrote=write(file,expected.data(),expected.size());if(wrote<0||(size_t)wrote!=expected.size()||fsync(file))throw failure{READER_SESSION_IO};
      int directory=open(name.parent_path().c_str(),O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
      if(directory<0)throw failure{READER_SESSION_IO};
      int status=fsync(directory);close(directory);if(status)throw failure{READER_SESSION_IO};
    }
#endif
    if(size&&(size!=expected.size()||std::memcmp(buffer,expected.data(),size)))throw failure{READER_SESSION_ACCOUNT};
  }
};
}
struct reader_session {
  const bool raw_api;explicit reader_session(bool raw=false):raw_api(raw){}
  std::string product,directory,originals,account,root,authorization;
  exr_webdav_config limits{};
#ifdef EXR_READER_SESSION_MANAGED
  std::string managed_profile;exr_webdav_managed_snapshot managed_view{};bool cleanup_requested=false;
#endif
  std::mutex mutex;std::condition_variable changed;std::thread worker;
  std::atomic<bool> cancelled{false};std::atomic<uint64_t> transferred{0};
  bool pending=false,running=false,closing=false;
  reader_session_snapshot view{};
  ~reader_session(){wipe(authorization);}
};
namespace {
struct connection {
  reader_revisions *revisions=nullptr;exr_webdav_client *dav=nullptr;reader_sync *sync=nullptr;account_binding binding;
  ~connection(){reader_sync_free(sync);if(revisions)reader_revisions_close(&revisions,nullptr);exr_webdav_free(dav);}
};
int original(void *opaque,const char *key,char *out,size_t capacity){
  auto &s=*(reader_session *)opaque;std::string k=key;size_t colon=k.find(':');if(colon==std::string::npos)return 1;
  std::string format=k.substr(0,colon),hash=k.substr(colon+1);
  if(format!="epub"&&format!="pdf"&&format!="cbz"&&format!="txt"&&format!="html"&&format!="fb2"&&format!="docx"&&format!="rtf"&&format!="mobi")return 1;
  if(hash.size()!=64)return 1;
  for(char c:hash)if(!((c>='0'&&c<='9')||(c>='a'&&c<='f')))return 1;
  std::string value=(fs::u8path(s.originals)/fs::u8path(hash+"."+format)).u8string();
  if(value.size()>=capacity||!fs::exists(fs::u8path(value)))return 1;
  std::memcpy(out,value.c_str(),value.size()+1);return 0;
}
int cancellation(void *p){return ((reader_session *)p)->cancelled.load()?1:0;}
void progress(void *p,uint64_t bytes){((reader_session *)p)->transferred.store(bytes);}
std::unique_ptr<connection> connect(reader_session &s){
  std::unique_ptr<connection> c(new connection);exr_webdav_config config=s.limits;
  config.root_url=s.root.c_str();config.authorization=s.authorization.c_str();exr_webdav_error de{};
  if(exr_webdav_create(&config,&c->dav,&de)!=EXR_DAV_OK){failure f{READER_SESSION_SYNC};f.error.dav_code=(int)de.code;throw f;}
#ifdef EXR_READER_SESSION_MANAGED
  if(!s.managed_profile.empty()){
    auto code=exr_webdav_managed_enable(c->dav,s.managed_profile.c_str(),&de);
    {std::lock_guard<std::mutex> lock(s.mutex);exr_webdav_managed_observe(c->dav,&s.managed_view);}
    if(code!=EXR_DAV_OK){failure f{READER_SESSION_SYNC};f.error.dav_code=(int)de.code;throw f;}
  }
#endif
  reader_revision_error re{};
  auto open_history=reader_revisions_open;
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
  if(s.raw_api)open_history=reader_revisions_open_raw_v3;
#endif
  if(open_history(s.product.c_str(),&c->revisions,&re)!=READER_REV_OK){failure f{READER_SESSION_SYNC};f.error.revision_code=(int)re.code;throw f;}
  c->binding.bind(fs::canonical(fs::u8path(s.product)),s.account,s.root);
  reader_sync_config sc{c->dav,c->revisions,s.directory.c_str(),original,&s};reader_sync_error se{};
  auto create_sync=reader_sync_create;
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
  if(s.raw_api)create_sync=reader_sync_create_raw_v3;
#endif
  if(create_sync(&sc,&c->sync,&se)!=READER_SYNC_OK)throw failure{READER_SESSION_SYNC,se};
  return c;
}
void work(reader_session *s){
  std::unique_ptr<connection> c;unsigned shard=0;std::string after;bool finished=false;
  for(;;){
    {
      std::unique_lock<std::mutex> lock(s->mutex);s->changed.wait(lock,[&]{return s->pending||s->closing
#ifdef EXR_READER_SESSION_MANAGED
        ||s->cleanup_requested
#endif
        ;});
      if(s->closing)break;
#ifdef EXR_READER_SESSION_MANAGED
      if(s->cleanup_requested){
        s->running=true;lock.unlock();c.reset();
        exr_webdav_managed_snapshot observed{};
        exr_webdav_managed_recover_profile(s->managed_profile.c_str(),&observed);
        lock.lock();s->managed_view=observed;s->cleanup_requested=false;s->running=false;continue;
      }
#endif
      s->pending=false;s->running=true;s->view.attempt++;
      if(finished){shard=0;after.clear();s->view.steps=s->view.pushed=s->view.pulled=s->view.originals_verified=0;
        s->view.pending_metadata_observations=s->view.pending_original_observations=0;s->view.completed_shards=0;s->view.shard=0;s->view.after[0]=0;finished=false;}
      s->view.status=READER_SESSION_OK;s->view.error={};
    }
    reader_session_state result=READER_SESSION_FAILED;reader_session_status status=READER_SESSION_OK;reader_sync_error error{};
    try{
      if(s->cancelled.load()){result=READER_SESSION_CANCELLED;}
      else{
        if(!c)c=connect(*s);
        exr_webdav_control control{cancellation,progress,s};
        for(;;){
          auto advance=reader_sync_step;
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
          if(s->raw_api)advance=reader_sync_step_raw_v3;
#endif
          reader_sync_report report{};reader_sync_status step=advance(c->sync,shard,after.c_str(),100,&control,&report,&error);
          {
            std::lock_guard<std::mutex> lock(s->mutex);
#ifdef EXR_READER_SESSION_MANAGED
            if(!s->managed_profile.empty())exr_webdav_managed_observe(c->dav,&s->managed_view);
#endif
            s->view.pushed+=report.pushed;s->view.pulled+=report.pulled;s->view.originals_verified+=report.originals_verified;
            s->view.pending_metadata_observations+=report.pending_metadata;s->view.pending_original_observations+=report.pending_local_original;
            if(step==READER_SYNC_OK){s->view.steps++;after=report.after;
              if(report.shard_complete){s->view.completed_shards++;if(shard==255){s->view.completed_sweeps++;finished=true;}else shard=report.next_shard;}
              s->view.shard=shard;std::snprintf(s->view.after,sizeof(s->view.after),"%s",after.c_str());}
          }
          if(step!=READER_SYNC_OK){status=step==READER_SYNC_CANCELLED?READER_SESSION_OK:READER_SESSION_SYNC;result=step==READER_SYNC_CANCELLED?READER_SESSION_CANCELLED:READER_SESSION_FAILED;break;}
          if(finished){result=READER_SESSION_FINISHED;break;}
        }
      }
    }catch(const failure &f){status=f.code;error=f.error;}catch(...){status=READER_SESSION_IO;}
    {std::lock_guard<std::mutex> lock(s->mutex);
#ifdef EXR_READER_SESSION_MANAGED
      if(c&&!s->managed_profile.empty())exr_webdav_managed_observe(c->dav,&s->managed_view);
#endif
      s->running=false;s->view.status=status;s->view.error=error;s->view.state=s->closing?READER_SESSION_CLOSING:result;}
  }
  c.reset();
  {std::lock_guard<std::mutex> lock(s->mutex);
#ifdef EXR_READER_SESSION_MANAGED
    s->cleanup_requested=false;
#endif
    s->view.state=READER_SESSION_CLOSED;}
}
}
static reader_session_status create_session(bool raw_api,const reader_session_config *config,reader_session **out,const char *managed_profile=nullptr){
  if(out)*out=nullptr;
  if(!out||!config||!bounded(config->product_path,8192)||!bounded(config->private_directory,8192)||
    !bounded(config->original_directory,8192)||!uuid(config->account_id)||!bounded(config->dav.root_url,8192)||
    (config->dav.authorization&&*config->dav.authorization&&!bounded(config->dav.authorization,8192)))return READER_SESSION_ARGUMENT;
#ifdef EXR_READER_SESSION_MANAGED
  if(managed_profile&&(!raw_api||!bounded(managed_profile,8192)))return READER_SESSION_ARGUMENT;
#else
  (void)managed_profile;
#endif
  try{
    for(const char *p:{config->private_directory,config->original_directory}){fs::path folder=fs::u8path(p);if(fs::is_symlink(fs::symlink_status(folder))||!fs::is_directory(folder))return READER_SESSION_ARGUMENT;}
    std::unique_ptr<reader_session> s(new reader_session(raw_api));s->product=config->product_path;s->directory=config->private_directory;s->originals=config->original_directory;
    s->account=config->account_id;s->root=config->dav.root_url;s->authorization=config->dav.authorization?config->dav.authorization:"";
    s->limits=config->dav;s->limits.root_url=s->limits.authorization=nullptr;
#ifdef EXR_READER_SESSION_MANAGED
    if(managed_profile){s->managed_profile=managed_profile;s->managed_view.enabled=1;}
#endif
    s->worker=std::thread(work,s.get());*out=s.release();return READER_SESSION_OK;
  }catch(...){return READER_SESSION_IO;}
}
extern "C" reader_session_status reader_session_start(reader_session *s){if(!s)return READER_SESSION_ARGUMENT;std::lock_guard<std::mutex> lock(s->mutex);
  if(s->closing)return READER_SESSION_ARGUMENT;
  if(s->pending||s->running
#ifdef EXR_READER_SESSION_MANAGED
    ||s->cleanup_requested
#endif
    )return READER_SESSION_BUSY;
  s->cancelled.store(false);s->transferred.store(0);s->pending=true;s->view.state=READER_SESSION_RUNNING;s->changed.notify_one();return READER_SESSION_OK;
}
extern "C" reader_session_status reader_session_cancel(reader_session *s){if(!s)return READER_SESSION_ARGUMENT;std::lock_guard<std::mutex> lock(s->mutex);
  if(s->closing)return READER_SESSION_ARGUMENT;
#ifdef EXR_READER_SESSION_MANAGED
  if(s->cleanup_requested)return READER_SESSION_OK; /* Bounded offline recovery drains before CLOSED. */
#endif
  if(s->pending||s->running){s->cancelled.store(true);s->view.state=READER_SESSION_CANCELLING;}return READER_SESSION_OK;
}
extern "C" reader_session_status reader_session_observe(reader_session *s,reader_session_snapshot *out){if(out)*out={};if(!s||!out)return READER_SESSION_ARGUMENT;
  std::lock_guard<std::mutex> lock(s->mutex);*out=s->view;out->transfer_bytes=s->transferred.load();return READER_SESSION_OK;
}
extern "C" reader_session_status reader_session_request_close(reader_session *s){if(!s)return READER_SESSION_ARGUMENT;std::lock_guard<std::mutex> lock(s->mutex);
  if(s->view.state==READER_SESSION_CLOSED)return READER_SESSION_OK;
  s->closing=true;s->cancelled.store(true);s->view.state=READER_SESSION_CLOSING;s->changed.notify_one();return READER_SESSION_OK;
}
extern "C" reader_session_status reader_session_destroy(reader_session **pointer){if(!pointer||!*pointer)return READER_SESSION_ARGUMENT;reader_session *s=*pointer;
  {std::lock_guard<std::mutex> lock(s->mutex);if(s->view.state!=READER_SESSION_CLOSED)return READER_SESSION_BUSY;}
  s->worker.join();delete s;*pointer=nullptr;return READER_SESSION_OK;
}

extern "C" reader_session_status reader_session_create(const reader_session_config *c,reader_session **s){return create_session(false,c,s);}
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
extern "C" reader_session_status reader_session_create_raw_v3(const reader_session_config *c,reader_session **s){return create_session(true,c,s);}
#endif

#ifdef EXR_READER_SESSION_MANAGED
extern "C" reader_session_status reader_session_create_managed_raw_v3(const reader_session_config *c,const char *profile,reader_session **out) {
  if(!profile){if(out)*out=nullptr;return READER_SESSION_ARGUMENT;}
  return create_session(true,c,out,profile);
}
extern "C" reader_session_status reader_session_managed_observe(reader_session *s,exr_webdav_managed_snapshot *out) {
  if(out)*out={};
  if(!s||!out)return READER_SESSION_ARGUMENT;
  std::lock_guard<std::mutex> lock(s->mutex);
  if(s->managed_profile.empty())return READER_SESSION_ARGUMENT;
  *out=s->managed_view;out->recovery_running=s->cleanup_requested?1:0;return READER_SESSION_OK;
}
extern "C" reader_session_status reader_session_managed_retry_cleanup(reader_session *s) {
  if(!s)return READER_SESSION_ARGUMENT;
  std::lock_guard<std::mutex> lock(s->mutex);
  if(s->managed_profile.empty()||s->closing)return READER_SESSION_ARGUMENT;
  if(s->running||s->pending||s->cleanup_requested)return READER_SESSION_BUSY;
  s->cleanup_requested=true;s->changed.notify_one();return READER_SESSION_OK;
}
#endif
