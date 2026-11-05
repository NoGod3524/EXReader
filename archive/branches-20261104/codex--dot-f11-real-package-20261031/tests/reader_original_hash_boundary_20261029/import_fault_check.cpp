/* Test-only public-provider failure adapter around the actual importer. */
#include <opds_sha256_stream.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
extern "C" {
opds_sha256_stream_status real_create(opds_sha256_stream **);
opds_sha256_stream_status real_update(opds_sha256_stream *,const void *,size_t);
opds_sha256_stream_status real_finish(opds_sha256_stream *,char[65]);
void real_destroy(opds_sha256_stream **);
}
static int fail_stage, fail_instance, instance, live, destroys;
static opds_sha256_stream_status injected;
static bool selected(int stage) { return fail_stage==stage && instance==fail_instance; }
extern "C" opds_sha256_stream_status opds_sha256_stream_create(opds_sha256_stream **out) {
  ++instance;
  auto status=real_create(out); if(*out)++live;
  // A partially allocated failed create must also be cleaned by the consumer.
  return selected(1) ? injected : status;
}
extern "C" opds_sha256_stream_status opds_sha256_stream_update(opds_sha256_stream *c,const void *p,size_t n) {
  return selected(2) ? injected : real_update(c,p,n);
}
extern "C" opds_sha256_stream_status opds_sha256_stream_finish_hex(opds_sha256_stream *c,char out[65]) {
  if(selected(3)){std::memset(out,0,65);return injected;}
  return real_finish(c,out);
}
extern "C" void opds_sha256_stream_destroy(opds_sha256_stream **c) {
  if(c&&*c){--live;++destroys;} real_destroy(c);
}
#include ORIGINAL_IMPORT_SOURCE
static void require(bool ok,const char *s){if(!ok){std::fprintf(stderr,"FAULT FAIL %s\n",s);std::exit(1);}}
static void reset(int stage,int which,opds_sha256_stream_status status){require(live==0,"no retained contexts");fail_stage=stage;fail_instance=which;injected=status;instance=0;destroys=0;}
static void staged(void *,int event){if(event==3)throw 1;}
int main(int argc,char **argv) {
  require(argc==2,"root argument"); namespace fs=std::filesystem;
  fs::path base=fs::absolute(argv[1]);fs::create_directories(base);
  auto src=base/"source";fs::create_directory(src);
  {std::ofstream out(src/"input.txt",std::ios::binary);out<<"abc";}
  const char *key_expected="txt:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";
  int serial=0;
  for(auto status:{OPDS_SHA256_STREAM_MEMORY,OPDS_SHA256_STREAM_ARGUMENT,OPDS_SHA256_STREAM_STATE}) {
    reader_original_status want=status==OPDS_SHA256_STREAM_MEMORY?ROI_MEMORY:status==OPDS_SHA256_STREAM_ARGUMENT?ROI_ARGUMENT:ROI_IO;
    for(int stage=1;stage<=3;stage++) for(int which=1;which<=2;which++) {
      auto root=base/("import-"+std::to_string(++serial));fs::create_directory(root);
      reader_catalog *c=nullptr;reader_catalog_error e{};
      require(!reader_catalog_open((root/"db").string().c_str(),&c,&e),"catalog");
      reset(stage,which,status);char key[69]{};
      require(reader_original_import(c,root.string().c_str(),src.string().c_str(),"input.txt","A","B","A",nullptr,key)==want,"initial/copied status");
      require(live==0 && destroys==which,"throw cleanup exactly once");
      require(!fs::exists(root/(std::string(key_expected+4)+".txt")),"no published ready bytes");
      reset(0,0,OPDS_SHA256_STREAM_OK);require(reader_original_recover(c,root.string().c_str())==ROI_OK,"fault recovery");
      require(reader_original_import(c,root.string().c_str(),src.string().c_str(),"input.txt","A","B","A",nullptr,key)==ROI_OK,"success after fault");
      require(!std::strcmp(key,key_expected),"real provider exact identity");
      reset(stage,1,status);char path[4096]{};
      require(reader_original_verified_path(c,root.string().c_str(),key,path,sizeof path)==want && !path[0],"verify status");
      require(live==0 && destroys==1,"verify cleanup");
#ifdef _WIN32
      reset(stage,1,status);void *held=nullptr;uint64_t bytes=0;
      require(reader_original_verified_handle(c,root.string().c_str(),key,nullptr,&held,&bytes)==want && !held && !bytes,"held handle status");
      require(live==0 && destroys==1,"held cleanup");
#endif
      require(!reader_catalog_close(&c,&e),"close");
    }
    for(int stage=1;stage<=3;stage++) {
      auto root=base/("recovery-"+std::to_string(++serial));fs::create_directory(root);
      reader_catalog *c=nullptr;reader_catalog_error e{};char key[69]{};
      require(!reader_catalog_open((root/"db").string().c_str(),&c,&e),"recovery catalog");
      reset(0,0,OPDS_SHA256_STREAM_OK);reader_original_callbacks cb{nullptr,nullptr,staged};
      require(reader_original_import(c,root.string().c_str(),src.string().c_str(),"input.txt","A","B","A",&cb,key)==ROI_MEMORY,"published staged interruption");
      reset(stage,1,status);require(reader_original_recover(c,root.string().c_str())==want,"recovery provider status");
      require(live==0 && destroys==1,"recovery cleanup");
      reset(0,0,OPDS_SHA256_STREAM_OK);require(reader_original_recover(c,root.string().c_str())==ROI_OK,"recovery retry");
      require(!reader_catalog_close(&c,&e),"recovery close");
    }
  }
  require(live==0,"all contexts released");puts("IMPORT_FAULT_OK");return 0;
}
