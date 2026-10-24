/* SPDX-License-Identifier: MIT */
#include <exr_sideload.h>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>
namespace fs=std::filesystem;
extern "C" int export_c_contract(void);
static std::vector<std::string> checks;
static void require(bool value){if(!value)throw std::runtime_error("original export assertion");}
static void record(const char *name){checks.emplace_back(name);std::cout<<"PASS "<<name<<std::endl;}
static std::string read(const fs::path &path){std::ifstream input(path,std::ios::binary);require(bool(input));return {std::istreambuf_iterator<char>(input),{}};}
static void write(const fs::path &path,const std::string &bytes){std::ofstream output(path,std::ios::binary);output.write(bytes.data(),(std::streamsize)bytes.size());require(bool(output));}
static void no_temps(const fs::path &root){for(const auto &entry:fs::directory_iterator(root))require(entry.path().filename().u8string().find(".exr-export-")==std::string::npos);}
struct progress_state {
  fs::path destination;uint64_t done=0,total=0,cancel_at=UINT64_MAX;int completed=0;
  bool before_publish=true,race=false,mutate=false;exr_library *other=nullptr;int writes=0;
};
static int cancelled(void *opaque){auto &s=*(progress_state *)opaque;return s.done>=s.cancel_at||(s.completed>=2&&s.cancel_at==UINT64_MAX-1);}
static void progress(void *opaque,exr_stage stage,uint64_t done,uint64_t total){
  auto &s=*(progress_state *)opaque;require(stage==EXR_STAGE_EXPORT);s.done=done;s.total=total;
  if(total&&done==total)++s.completed;
  if(!s.race)require(!fs::exists(s.destination));
  if(s.mutate&&done>=65536&&!s.writes){int64_t id=0;exr_error error{};const char text[]="foreign connection commit";
    require(exr_library_import(s.other,EXR_TXT,text,sizeof(text)-1,"other",&id,&error)==EXR_OK);++s.writes;}
  if(s.race&&s.completed==2)write(s.destination,"racing destination");
}
int main(int argc,char **argv){try{
  require(argc==3&&export_c_contract()==0);fs::path fixtures=fs::u8path(argv[1]),root=fs::u8path(argv[2]);
  fs::create_directories(root);exr_library *library=nullptr;exr_error error{};std::string database=(root/fs::u8path("原件.sqlite")).u8string();
  require(exr_library_open(database.c_str(),&library,&error)==EXR_OK);
  int64_t txt=0;
  for(const auto &item:std::vector<std::pair<const char *,exr_format>>{{"book.txt",EXR_TXT},{"book.epub",EXR_EPUB},{"pages.pdf",EXR_PDF},{"pages.cbz",EXR_CBZ}}){
    fs::path input=fixtures/item.first,destination=root/fs::u8path(std::string("导出-")+item.first);std::string original=read(input);int64_t id=0;
    if(item.second==EXR_TXT)require(exr_library_import(library,item.second,original.data(),original.size(),"original",&id,&error)==EXR_OK);
    else require(exr_library_import_file(library,item.second,input.u8string().c_str(),"original",&id,&error)==EXR_OK);
    if(item.second==EXR_TXT)txt=id;
    progress_state observed{};observed.destination=destination;exr_sideload_options options{};options.struct_size=sizeof(options);options.control={cancelled,progress,&observed};
    uint64_t bytes=999;require(exr_sideload_export_original(library,id,destination.u8string().c_str(),&options,&bytes,&error)==EXR_OK);
    require(bytes==original.size()&&read(destination)==original&&observed.done==original.size()&&observed.completed==2);no_temps(root);
    record(item.second==EXR_TXT?"txt_original_atomic_utf8_path":item.second==EXR_EPUB?"epub_original_atomic_utf8_path":item.second==EXR_PDF?"pdf_original_atomic_utf8_path":"cbz_original_atomic_utf8_path");
  }
  std::string large(1024*1024,'x');large.back()='\n';int64_t big=0;
  require(exr_library_import(library,EXR_TXT,large.data(),large.size(),"large",&big,&error)==EXR_OK);
  fs::path dest=root/"large.txt";uint64_t bytes=0;
  require(exr_sideload_export_original(library,big,dest.u8string().c_str(),nullptr,&bytes,&error)==EXR_OK&&bytes==large.size()&&read(dest)==large);no_temps(root);
  record("multichunk_original_matches_after_source_release");
  write(dest,"existing destination");bytes=999;
  require(exr_sideload_export_original(library,big,dest.u8string().c_str(),nullptr,&bytes,&error)==EXR_IO&&bytes==0&&read(dest)=="existing destination");no_temps(root);
  record("existing_destination_is_never_replaced");
  for(int mode=0;mode<3;mode++){
    progress_state observed{};observed.destination=root/("cancel-"+std::to_string(mode));observed.cancel_at=mode==0?0:mode==1?65536:UINT64_MAX-1;
    exr_sideload_options options{};options.struct_size=sizeof(options);options.control={cancelled,progress,&observed};bytes=999;
    require(exr_sideload_export_original(library,big,observed.destination.u8string().c_str(),&options,&bytes,&error)==EXR_CANCELLED&&bytes==0&&!fs::exists(observed.destination));no_temps(root);
    record(mode==0?"cancel_before_source_has_no_file":mode==1?"cancel_during_copy_removes_only_own_temporary":"cancel_after_source_release_prevents_publication");
  }
  exr_sideload_options options{};options.struct_size=sizeof(options);options.max_input_bytes=65535;dest=root/"too-large";bytes=999;
  require(exr_sideload_export_original(library,big,dest.u8string().c_str(),&options,&bytes,&error)==EXR_LIMIT&&bytes==0&&!fs::exists(dest));no_temps(root);
  options.struct_size=1;require(exr_sideload_export_original(library,txt,dest.u8string().c_str(),&options,&bytes,&error)==EXR_ARGUMENT&&bytes==0);
  require(exr_sideload_export_original(library,0,dest.u8string().c_str(),nullptr,&bytes,&error)==EXR_ARGUMENT&&bytes==0);
  require(exr_sideload_export_original(library,txt,dest.u8string().c_str(),nullptr,nullptr,&error)==EXR_ARGUMENT);record("limits_and_incomplete_arguments_do_not_publish");
  dest=root/"missing-parent"/"output";bytes=999;
  require(exr_sideload_export_original(library,big,dest.u8string().c_str(),nullptr,&bytes,&error)==EXR_IO&&bytes==0&&!fs::exists(dest));no_temps(root);
  record("file_creation_failure_leaves_no_destination_or_temporary");
  progress_state race{};race.destination=root/"racing.txt";race.race=true;options={};options.struct_size=sizeof(options);options.control={cancelled,progress,&race};bytes=999;
  require(exr_sideload_export_original(library,big,race.destination.u8string().c_str(),&options,&bytes,&error)==EXR_IO&&bytes==0&&read(race.destination)=="racing destination");no_temps(root);
  record("concurrent_destination_creation_is_preserved_at_atomic_publish");
  progress_state mutation{};mutation.destination=root/"invalidated.txt";mutation.mutate=true;
  require(exr_library_open(database.c_str(),&mutation.other,&error)==EXR_OK);options.control={cancelled,progress,&mutation};bytes=999;
  require(exr_sideload_export_original(library,big,mutation.destination.u8string().c_str(),&options,&bytes,&error)==EXR_IO&&bytes==0&&mutation.writes==1&&!fs::exists(mutation.destination));no_temps(root);
  exr_library_close(mutation.other);record("foreign_owner_commit_invalidates_source_without_partial_publication");
  dest=root/"after-close.txt";bytes=999;require(exr_sideload_export_original(library,big,dest.u8string().c_str(),nullptr,&bytes,&error)==EXR_OK&&bytes==large.size());
  exr_library_close(library);require(read(dest)==large);no_temps(root);record("exported_original_remains_readable_after_sdk_owner_close");
  require(checks.size()==14);std::cout<<"{\"accepted\":true,\"checks\":[";
  for(size_t i=0;i<checks.size();i++){if(i)std::cout<<',';std::cout<<'"'<<checks[i]<<'"';}
  std::cout<<"],\"count\":"<<checks.size()<<"}\n";return 0;
}catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}}
