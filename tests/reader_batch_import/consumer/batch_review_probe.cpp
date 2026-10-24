/* SPDX-License-Identifier: MIT */
#include <reader_batch_import.h>
#include <atomic>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <string>
#include <thread>
#include <vector>
#ifdef _WIN32
#include <windows.h>
#else
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#endif
namespace fs=std::filesystem;
static void write_file(const fs::path &path,char value,size_t bytes=196608){
  fs::create_directories(path.parent_path());std::ofstream out(path,std::ios::binary);std::string block(bytes,value);out.write(block.data(),block.size());
  if(!out)throw std::runtime_error("fixture write failed");
}
static bool stamp(const fs::path &path,unsigned nanos){
#ifdef _WIN32
  HANDLE file=CreateFileW(path.c_str(),FILE_WRITE_ATTRIBUTES,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,nullptr,OPEN_EXISTING,0,nullptr);
  if(file==INVALID_HANDLE_VALUE)return false;
  ULARGE_INTEGER value;value.QuadPart=(UINT64_C(13200000000)*10000000)+nanos/100;
  FILETIME time{value.LowPart,value.HighPart};bool ok=SetFileTime(file,nullptr,nullptr,&time)!=0;CloseHandle(file);return ok;
#else
  timespec times[2]={{1600000000,0},{1600000000,(long)nanos}};return utimensat(AT_FDCWD,path.c_str(),times,0)==0;
#endif
}
struct edit_state{fs::path path;bool edited=false,ok=true;};
static void edit(void *opaque,exr_stage,uint64_t done,uint64_t){
  auto &state=*(edit_state *)opaque;if(state.edited||done<65536)return;state.edited=true;
#ifdef _WIN32
  FILE *file=_wfopen(state.path.c_str(),L"r+b");
#else
  FILE *file=std::fopen(state.path.c_str(),"r+b");
#endif
  if(!file){state.ok=false;return;}
  std::string replacement(65536,'B');state.ok=std::fseek(file,65536,SEEK_SET)==0&&std::fwrite(replacement.data(),1,replacement.size(),file)==replacement.size();
  if(std::fclose(file)!=0)state.ok=false;
  if(!stamp(state.path,900000000))state.ok=false;
}
static int import_one(const fs::path &base,const fs::path &source,bool rewrite,bool expect_commit){
  fs::create_directories(base/"stage");exr_library *library=nullptr;exr_error sdk{};
  std::string db=(base/"library.sqlite").u8string(),path=source.u8string(),stage=(base/"stage").u8string();
  if(exr_library_open(db.c_str(),&library,&sdk)!=EXR_OK)return 2;
  reader_batch_item item{sizeof(item),path.c_str(),nullptr,EXR_TXT};reader_batch_import_options options;reader_batch_import_options_init(&options);options.staging_dir=stage.c_str();
  edit_state state{source};if(rewrite){options.control.progress=edit;options.control.context=&state;}
  reader_batch_result *results=nullptr;size_t count=0;reader_batch_error error{};
  reader_batch_status status=reader_batch_import(library,&item,1,&options,&results,&count,&error);
  bool committed=count==1&&results&&results[0].committed==1;
  bool ok=status==READER_BATCH_OK&&count==1&&committed==expect_commit;
  if(!expect_commit)ok=ok&&results&&results[0].status==READER_BATCH_ITEM_FAILED;
  if(rewrite)ok=ok&&state.edited&&state.ok;
  std::printf("status=%d count=%zu committed=%d detail=%s edited=%d fixture_ok=%d\n",status,count,committed,results?results[0].message:error.message,state.edited,state.ok);
  reader_batch_results_free(results,count);exr_library_close(library);return ok?0:1;
}
static int directory_budget(const fs::path &base){
  fs::path root=base/"tree";for(int i=0;i<3;i++)write_file(root/("child-"+std::to_string(i))/"book.txt",'A',128);
  reader_batch_scan_options options;reader_batch_scan_options_init(&options);std::string text=root.u8string();options.root=text.c_str();options.recursive=1;options.max_directories=2;options.batch_size=1;
  reader_batch_enumerator *scan=nullptr;reader_batch_error error{};if(reader_batch_enumerate_open(&options,&scan,&error)!=READER_BATCH_OK)return 2;
  size_t total=0;int complete=0,truncated=0;reader_batch_status status=READER_BATCH_OK;
  while(!complete&&!truncated){reader_batch_candidate *items=nullptr;size_t count=0;status=reader_batch_enumerate_next(scan,&items,&count,&complete,&truncated,&error);total+=count;reader_batch_candidates_free(items,count);if(status!=READER_BATCH_OK)break;}
  reader_batch_enumerate_close(scan);std::printf("candidates=%zu complete=%d truncated=%d status=%d\n",total,complete,truncated,status);
  return status==READER_BATCH_OK&&total<=1&&complete==0&&truncated==1?0:1;
}
static int concurrent(const fs::path &base){
  constexpr int workers=8;std::atomic<int> ready{0},failures{0};std::atomic<bool> go{false};std::vector<std::thread> threads;
  for(int i=0;i<workers;i++){fs::path folder=base/std::to_string(i);fs::create_directories(folder/"stage");write_file(folder/"source.txt",'A',1024);}
  for(int i=0;i<workers;i++)threads.emplace_back([&,i]{
    fs::path folder=base/std::to_string(i);std::string db=(folder/"library.sqlite").u8string(),source=(folder/"source.txt").u8string(),stage=(folder/"stage").u8string();
    exr_library *library=nullptr;exr_error sdk{};bool opened=exr_library_open(db.c_str(),&library,&sdk)==EXR_OK;
    ready.fetch_add(1);while(!go.load(std::memory_order_acquire))std::this_thread::yield();
    if(!opened){failures++;return;}
    reader_batch_item item{sizeof(item),source.c_str(),nullptr,EXR_TXT};reader_batch_import_options options;reader_batch_import_options_init(&options);options.staging_dir=stage.c_str();
    for(int n=0;n<8;n++){reader_batch_result *out=nullptr;size_t count=0;reader_batch_error error{};reader_batch_status status=reader_batch_import(library,&item,1,&options,&out,&count,&error);
      if(status!=READER_BATCH_OK||count!=1||!out||!out[0].committed)failures++;reader_batch_results_free(out,count);}
    exr_library_close(library);
  });
  while(ready.load()!=workers)std::this_thread::yield();go.store(true,std::memory_order_release);for(auto &thread:threads)thread.join();
  std::printf("independent_owner_threads=%d imports=64 failures=%d\n",workers,failures.load());return failures.load()?1:0;
}
int main(int argc,char **argv){
  try{if(argc!=3)return 2;fs::path base=fs::u8path(argv[2]);fs::create_directories(base);std::string action=argv[1];
    if(action=="directory-budget")return directory_budget(base);
    if(action=="parent-link")return import_one(base,base/"root/parent/book.txt",false,false);
    if(action=="copy-change"){fs::path source=base/"source.txt";write_file(source,'A');if(!stamp(source,100000000))return 2;return import_one(base,source,true,false);}
    if(action=="concurrent")return concurrent(base);
    return 2;
  }catch(const std::exception &error){std::fprintf(stderr,"fixture error: %s\n",error.what());return 2;}
}
