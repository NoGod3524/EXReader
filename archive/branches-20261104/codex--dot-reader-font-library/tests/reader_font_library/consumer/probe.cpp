// SPDX-License-Identifier: MIT
#include <reader_font_library.h>
#include <exr/core.h>
#include <algorithm>
#include <chrono>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
#ifndef _WIN32
#include <csignal>
#include <sys/resource.h>
#endif
namespace fs=std::filesystem;
#define CHECK(x) do{if(!(x))throw std::runtime_error(std::string("line ")+std::to_string(__LINE__)+": "+#x);}while(0)
static void pass(const char*s){std::cout<<"CASE "<<s<<std::endl;}
static std::string path(const fs::path&p){return p.u8string();}
static std::vector<unsigned char> bytes(const fs::path&p){std::ifstream f(p,std::ios::binary);CHECK(f.good());return {std::istreambuf_iterator<char>(f),std::istreambuf_iterator<char>()};}
static void save(const fs::path&p,const std::string&s){std::ofstream f(p,std::ios::binary);f<<s;CHECK(f.good());}
struct owner {rfl_library*p=nullptr;~owner(){if(p)rfl_close(p,nullptr);}};
static void open(owner&l,const fs::path&p,const rfl_limits*limits=nullptr){fs::create_directories(p);rfl_error e{};auto s=rfl_open(path(p).c_str(),limits,&l.p,&e);if(s)throw std::runtime_error(std::to_string(s)+": "+e.message);}
static rfl_record add(owner&l,const fs::path&p){rfl_record r{};int created=0;rfl_error e{};auto s=rfl_import_file(l.p,path(p).c_str(),"Selected font",nullptr,&r,&created,&e);if(s)throw std::runtime_error(std::to_string(s)+": "+e.message);CHECK(created==1);return r;}
static size_t count(owner&l){size_t n=999;CHECK(rfl_count(l.p,&n,nullptr)==RFL_OK);return n;}
struct source {std::vector<unsigned char> data;size_t max_read=65536,calls=0,zero_starts=0;bool changing=false;rfl_source*declaration=nullptr;};
static rfl_status read_source(void*c,uint64_t offset,void*b,size_t cap,size_t*n){auto&s=*static_cast<source*>(c);CHECK(cap<=65536);s.calls++;if(s.declaration)s.declaration->bytes=UINT64_MAX;if(!offset&&++s.zero_starts==2&&s.changing)s.data[10]^=1;*n=offset>=s.data.size()?0:std::min({cap,s.max_read,s.data.size()-size_t(offset)});if(*n)std::memcpy(b,s.data.data()+offset,*n);return RFL_OK;}
static rfl_status excessive_read(void*,uint64_t,void*,size_t cap,size_t*n){*n=cap+1;return RFL_OK;}
static rfl_status throwing_read(void*,uint64_t,void*,size_t,size_t*){throw std::runtime_error("host callback exception");}
struct control {rfl_library*library=nullptr;std::string stage;bool cancel=false,reenter=false,pause=false;fs::path ready,source_path;bool mutate=false;size_t polls=0;fs::path quota_directory;uint64_t quota=0;};
static int progress(void*c,const char*stage,uint64_t done,uint64_t){auto&s=*static_cast<control*>(c);s.polls++;if(s.quota){uint64_t total=0;for(const auto&e:fs::directory_iterator(s.quota_directory)){auto n=e.path().filename().u8string();if(n==".rfl-tmp-font"||e.path().extension()==".font")total+=e.file_size();}CHECK(total<=s.quota);}if(s.reenter){size_t n=99;CHECK(rfl_count(s.library,&n,nullptr)==RFL_BUSY&&n==0);CHECK(rfl_close(s.library,nullptr)==RFL_BUSY);}
  if(s.stage==stage){if(s.mutate&&done){std::ofstream f(s.source_path,std::ios::binary|std::ios::trunc);f<<"modified";s.mutate=false;}
    if(s.pause){save(s.ready,stage);while(true)std::this_thread::sleep_for(std::chrono::milliseconds(50));}return s.cancel?1:0;}return 0;}
static void render(rfl_lease*lease,unsigned expected_face){exr_font*f=nullptr;CHECK(rfl_lease_font(lease,&f,nullptr)==RFL_OK&&f);CHECK(exr_font_count(f)==1&&exr_font_has_glyph(f,0,'A'));exr_font_input src{};CHECK(exr_font_source(f,0,&src,nullptr)==EXR_OK&&src.face_index==expected_face&&src.size);exr_shaped_glyph*g=nullptr;size_t n=0;auto options=exr_shape_defaults();CHECK(exr_shape(f,0,"office",6,&options,&g,&n,nullptr)==EXR_OK&&n>0);exr_free(g);
  exr_document*d=nullptr;exr_layout*l=nullptr;CHECK(exr_document_open_memory(EXR_TXT,"A native font layout.",21,&d,nullptr)==EXR_OK);CHECK(exr_layout_create(d,f,nullptr,&l,nullptr)==EXR_OK);CHECK(exr_layout_pages(l,&n)&&n==1);exr_layout_free(l);exr_document_free(d);}
static void suite(const fs::path&root,const fs::path&fixtures){
  owner l;open(l,root/"main");auto ttf=fixtures/"font.ttf",otf=fixtures/"font.otf",ttc=fixtures/"font.ttc";CHECK(count(l)==0);pass("empty-library");
  {auto dir=root/"unrelated";fs::create_directory(dir);save(dir/"original.ttf","user original");owner unrelated;CHECK(rfl_open(path(dir).c_str(),nullptr,&unrelated.p,nullptr)==RFL_CORRUPT&&!unrelated.p);CHECK(bytes(dir/"original.ttf")==std::vector<unsigned char>({'u','s','e','r',' ','o','r','i','g','i','n','a','l'}));}pass("unrelated-private-directory-file-preserved");
  auto first=add(l,ttf);CHECK(count(l)==1&&first.bytes==fs::file_size(ttf));pass("ttf-import-content-identity");
  rfl_record r{};int created=99;CHECK(rfl_import_file(l.p,path(ttf).c_str(),"Different name",nullptr,&r,&created,nullptr)==RFL_OK&&!created&&!std::strcmp(r.display_name,first.display_name)&&!std::strcmp(r.hash,first.hash));pass("deduplicate-preserves-record");
  CHECK(rfl_find(l.p,first.hash,&r,nullptr)==RFL_OK&&!std::strcmp(r.hash,first.hash));CHECK(rfl_get(l.p,0,&r,nullptr)==RFL_OK);CHECK(rfl_get(l.p,1,&r,nullptr)==RFL_NOT_FOUND&&!r.hash[0]);pass("find-list-bounds");
  rfl_lease*lease=nullptr;CHECK(rfl_font_open(l.p,first.hash,0,&lease,nullptr)==RFL_OK);render(lease,0);pass("sdk-glyph-shape-layout");
  CHECK(rfl_remove(l.p,first.hash,nullptr)==RFL_BUSY&&rfl_close(l.p,nullptr)==RFL_BUSY);render(lease,0);pass("leased-remove-close-busy");
  std::thread wrong([&]{size_t n=4;exr_font*f=nullptr;CHECK(rfl_count(l.p,&n,nullptr)==RFL_THREAD&&!n);CHECK(rfl_lease_font(lease,&f,nullptr)==RFL_THREAD&&!f);CHECK(rfl_lease_release(lease,nullptr)==RFL_THREAD);CHECK(rfl_remove(l.p,first.hash,nullptr)==RFL_THREAD);});wrong.join();render(lease,0);CHECK(rfl_lease_release(lease,nullptr)==RFL_OK);pass("wrong-thread-preserves-owner-and-lease");
  std::vector<rfl_lease*> held;for(unsigned i=0;i<32;++i){CHECK(rfl_font_open(l.p,first.hash,0,&lease,nullptr)==RFL_OK);held.push_back(lease);}CHECK(rfl_font_open(l.p,first.hash,0,&lease,nullptr)==RFL_LIMIT&&!lease);for(auto p:held)CHECK(rfl_lease_release(p,nullptr)==RFL_OK);pass("bounded-live-lease-count");
  auto second=add(l,otf);CHECK(rfl_font_open(l.p,second.hash,0,&lease,nullptr)==RFL_OK);render(lease,0);CHECK(rfl_lease_release(lease,nullptr)==RFL_OK);pass("otf-sdk-validation");
  auto collection=add(l,ttc);CHECK(rfl_font_open(l.p,collection.hash,1,&lease,nullptr)==RFL_OK);render(lease,1);CHECK(rfl_lease_release(lease,nullptr)==RFL_OK);CHECK(rfl_font_open(l.p,collection.hash,2,&lease,nullptr)==RFL_FONT&&!lease);CHECK(rfl_font_open(l.p,collection.hash,65536,&lease,nullptr)==RFL_UNSUPPORTED&&!lease);pass("ttc-explicit-face-and-invalid-face");
  CHECK(rfl_close(l.p,nullptr)==RFL_OK);l.p=nullptr;open(l,root/"main");CHECK(count(l)==3&&rfl_find(l.p,first.hash,&r,nullptr)==RFL_OK);pass("manifest-close-reopen");
  owner locked;CHECK(rfl_open(path(root/"main").c_str(),nullptr,&locked.p,nullptr)==RFL_BUSY&&!locked.p);pass("same-process-exclusive-directory-lock");
  for(const auto&name:std::vector<std::string>{"../x","slash/name","back\\name",std::string("\xc0\x80",2),std::string("\xed\xa0\x80",3),"control\n",std::string(256,'x')}){created=9;std::memset(&r,1,sizeof(r));CHECK(rfl_import_file(l.p,path(ttf).c_str(),name.c_str(),nullptr,&r,&created,nullptr)!=RFL_OK&&!created&&!r.hash[0]);}pass("display-name-unicode-path-injection-bounds");
  auto unicode=root/fs::u8path(u8"选择字体-😀.ttf");fs::copy_file(ttf,unicode);CHECK(rfl_import_file(l.p,path(unicode).c_str(),u8"字体 😀",nullptr,&r,&created,nullptr)==RFL_OK&&!created);pass("unicode-selected-path-and-display");
  for(auto bad:std::vector<fs::path>{fixtures/"bad.ttf",fixtures/"truncated.ttf"}){CHECK(rfl_import_file(l.p,path(bad).c_str(),"bad",nullptr,&r,&created,nullptr)==RFL_FONT&&!r.hash[0]&&!created&&count(l)==3);}pass("bad-and-truncated-preserve-library");
  CHECK(rfl_import_file(l.p,path(fixtures).c_str(),"directory",nullptr,&r,&created,nullptr)!=RFL_OK);pass("nonregular-source-rejected");
  const auto original=bytes(ttf);source src{original};rfl_source s{src.data.size(),read_source,&src};src.max_read=13;owner streaming;open(streaming,root/"streaming");CHECK(rfl_import_source(streaming.p,&s,"bounded source",nullptr,&r,&created,nullptr)==RFL_OK&&created&&src.calls>100&&!std::strcmp(r.hash,first.hash));pass("bounded-source-short-reads-and-hash");
  src.declaration=&s;CHECK(rfl_import_source(streaming.p,&s,"snapshot",nullptr,&r,&created,nullptr)==RFL_OK&&!created);src.declaration=nullptr;s.bytes=src.data.size();pass("source-contract-snapshot-bounds");
  rfl_source excessive{100,excessive_read,nullptr};CHECK(rfl_import_source(streaming.p,&excessive,"excessive",nullptr,&r,&created,nullptr)==RFL_CHANGED&&!created&&!r.hash[0]);excessive.read=throwing_read;CHECK(rfl_import_source(streaming.p,&excessive,"throwing",nullptr,&r,&created,nullptr)==RFL_IO&&!created&&!r.hash[0]);pass("invalid-source-return-and-exception-contained");
  auto calls=src.calls;s.bytes=67108865;CHECK(rfl_import_source(streaming.p,&s,"oversized",nullptr,&r,&created,nullptr)==RFL_LIMIT&&src.calls==calls&&!r.hash[0]);s.bytes=src.data.size();pass("advertised-font-hard-limit-before-read");
  src.max_read=65536;src.zero_starts=0;s.bytes=src.data.size()-1;CHECK(rfl_import_source(streaming.p,&s,"short-declared",nullptr,&r,&created,nullptr)==RFL_CHANGED&&!r.hash[0]);pass("underreported-source-rejected");
  s.bytes=src.data.size()+1;CHECK(rfl_import_source(streaming.p,&s,"truncated",nullptr,&r,&created,nullptr)==RFL_CHANGED&&!r.hash[0]);pass("source-truncation-rejected");
  s.bytes=src.data.size();src.zero_starts=0;src.changing=true;CHECK(rfl_import_source(streaming.p,&s,"changing",nullptr,&r,&created,nullptr)==RFL_CHANGED&&!r.hash[0]);src.changing=false;pass("source-midstream-change-rejected");
  control ctl;ctl.library=l.p;ctl.reenter=true;rfl_control c{progress,&ctl};CHECK(rfl_import_file(l.p,path(ttf).c_str(),"reentry",&c,&r,&created,nullptr)==RFL_OK&&!created&&ctl.polls);pass("callback-reentry-rejected");
  for(const auto&stage:{"copy","verify","validated","file-published"}){owner cancel;auto dir=root/(std::string("cancel-")+stage);open(cancel,dir);auto old=add(cancel,ttf);ctl={};ctl.stage=stage;ctl.cancel=true;c.context=&ctl;CHECK(rfl_import_file(cancel.p,path(otf).c_str(),"cancel",&c,&r,&created,nullptr)==RFL_CANCELLED&&!created&&!r.hash[0]&&count(cancel)==1);CHECK(rfl_find(cancel.p,old.hash,&r,nullptr)==RFL_OK);add(cancel,otf);CHECK(count(cancel)==2);}pass("cancel-each-stage-retry-preserves-old");
  auto mutable_path=root/"mutable.ttf";fs::copy_file(ttf,mutable_path);ctl={};ctl.stage="copy";ctl.mutate=true;ctl.source_path=mutable_path;c.context=&ctl;CHECK(rfl_import_file(l.p,path(mutable_path).c_str(),"mutable",&c,&r,&created,nullptr)==RFL_CHANGED&&!r.hash[0]);pass("selected-file-post-open-change-rejected");
  auto limits=rfl_limits_default();limits.font_bytes=first.bytes;owner exact;open(exact,root/"exact",&limits);add(exact,ttf);pass("font-exact-byte-boundary");
  limits.font_bytes=first.bytes-1;owner small;open(small,root/"small",&limits);CHECK(rfl_import_file(small.p,path(ttf).c_str(),"large",nullptr,&r,&created,nullptr)==RFL_LIMIT&&!r.hash[0]&&count(small)==0);pass("font-over-byte-boundary");
  limits=rfl_limits_default();limits.entries=1;owner one;open(one,root/"one",&limits);add(one,ttf);CHECK(rfl_import_file(one.p,path(otf).c_str(),"full",nullptr,&r,&created,nullptr)==RFL_LIMIT&&count(one)==1);CHECK(rfl_import_file(one.p,path(ttf).c_str(),"duplicate",nullptr,&r,&created,nullptr)==RFL_OK&&!created);pass("directory-entry-limit-dedupe-at-capacity");
  limits=rfl_limits_default();limits.directory_bytes=first.bytes;owner budget;open(budget,root/"budget",&limits);add(budget,ttf);CHECK(rfl_import_file(budget.p,path(otf).c_str(),"full",nullptr,&r,&created,nullptr)==RFL_LIMIT&&count(budget)==1);pass("directory-byte-limit-preserves-old");
  ctl={};ctl.quota=first.bytes;ctl.quota_directory=root/"budget";c.context=&ctl;CHECK(rfl_import_file(budget.p,path(ttf).c_str(),"full duplicate",&c,&r,&created,nullptr)==RFL_OK&&!created&&ctl.polls);pass("quota-deduplication-no-oversized-temporary");
  CHECK(rfl_close(exact.p,nullptr)==RFL_OK);exact.p=nullptr;limits=rfl_limits_default();limits.font_bytes=first.bytes-1;CHECK(rfl_open(path(root/"exact").c_str(),&limits,&exact.p,nullptr)==RFL_LIMIT&&!exact.p);pass("reopen-lower-budget-classified-limit");
  for(unsigned which=0;which<3;++which){limits=rfl_limits_default();if(which==0)limits.font_bytes=67108865;if(which==1)limits.directory_bytes=536870913;if(which==2)limits.entries=257;owner hard;fs::create_directories(root/"hard");CHECK(rfl_open(path(root/"hard").c_str(),&limits,&hard.p,nullptr)==RFL_LIMIT&&!hard.p);}pass("hard-limits-reject-oversized-config");
  CHECK(rfl_remove(l.p,second.hash,nullptr)==RFL_OK&&count(l)==2&&!fs::exists(root/"main"/(std::string(second.hash)+".font")));CHECK(rfl_remove(l.p,second.hash,nullptr)==RFL_NOT_FOUND);pass("explicit-remove-and-not-found");
  CHECK(bytes(ttf)==original);CHECK(fs::file_size(ttf)==first.bytes);pass("selected-original-never-removed");
  // Inject a real filesystem conflict, not an internal failure bypass.
  owner conflict;open(conflict,root/"conflict");save(root/"conflict"/(std::string(first.hash)+".font"),"conflict");CHECK(rfl_import_file(conflict.p,path(ttf).c_str(),"conflict",nullptr,&r,&created,nullptr)==RFL_CORRUPT&&!r.hash[0]&&count(conflict)==0);pass("content-path-conflict-no-overwrite");
  for(const auto&case_name:{"unknown","corrupt","missing-file","missing-manifest","marker-corrupt"}){auto dir=root/case_name;owner broken;open(broken,dir);auto existing=add(broken,ttf);CHECK(rfl_close(broken.p,nullptr)==RFL_OK);broken.p=nullptr;rfl_status expected=RFL_CORRUPT;if(std::string(case_name)=="unknown"){save(dir/"manifest.rfl","RFL9\n");expected=RFL_MANIFEST_VERSION;}else if(std::string(case_name)=="corrupt")save(dir/"manifest.rfl","RFL1\nnot-a-record\n");else if(std::string(case_name)=="missing-file"){fs::remove(dir/(std::string(existing.hash)+".font"));expected=RFL_MISSING;}else if(std::string(case_name)=="marker-corrupt")save(dir/".rfl-initialized","WRONG");else{fs::remove(dir/"manifest.rfl");expected=RFL_MISSING;}CHECK(rfl_open(path(dir).c_str(),nullptr,&broken.p,nullptr)==expected&&!broken.p);}pass("manifest-version-corrupt-missing-classification");
  {auto dir=root/"tampered";owner tampered;open(tampered,dir);auto t=add(tampered,ttf);CHECK(rfl_close(tampered.p,nullptr)==RFL_OK);tampered.p=nullptr;auto data=original;data[10]^=1;save(dir/(std::string(t.hash)+".font"),std::string(data.begin(),data.end()));CHECK(rfl_open(path(dir).c_str(),nullptr,&tampered.p,nullptr)==RFL_CORRUPT&&!tampered.p);CHECK(fs::exists(dir/(std::string(t.hash)+".font")));}pass("stored-hash-tampering-rejected");
#ifndef _WIN32
  auto link=root/"symlink.ttf";fs::create_symlink(ttf,link);CHECK(rfl_import_file(l.p,path(link).c_str(),"link",nullptr,&r,&created,nullptr)!=RFL_OK);auto dlink=root/"dirlink";fs::create_directory_symlink(root/"main",dlink);owner symlink;CHECK(rfl_open(path(dlink).c_str(),nullptr,&symlink.p,nullptr)!=RFL_OK);pass("posix-source-and-directory-symlinks-rejected");
#endif
}
int main(int argc,char**argv){try{CHECK(argc>=3);std::string mode=argv[1];fs::path root=fs::u8path(argv[2]);if(mode=="suite"){CHECK(argc==4);suite(root,fs::u8path(argv[3]));return 0;}
  if(mode=="status"){owner l;auto status=rfl_open(path(root).c_str(),nullptr,&l.p,nullptr);std::cout<<"STATUS "<<status<<std::endl;return 0;}
  owner l;open(l,root);
  if(mode=="list"){rfl_record r{};for(size_t i=0;i<count(l);++i){CHECK(rfl_get(l.p,i,&r,nullptr)==RFL_OK);std::cout<<r.hash<<std::endl;}return 0;}
  if(mode=="pause"){CHECK(argc==6);control ctl;ctl.stage=argv[4];ctl.pause=true;ctl.ready=fs::u8path(argv[5]);rfl_control c{progress,&ctl};rfl_record r{};int created=0;CHECK(rfl_import_file(l.p,argv[3],"pause",&c,&r,&created,nullptr)==RFL_OK);return 0;}
  if(mode=="remove"){CHECK(argc==4);auto status=rfl_remove(l.p,argv[3],nullptr);size_t n=999;auto query=rfl_count(l.p,&n,nullptr);std::cout<<"STATUS "<<status<<" COUNT "<<query<<std::endl;return 0;}
  if(mode=="import"){CHECK(argc==4);auto r=add(l,fs::u8path(argv[3]));std::cout<<r.hash<<std::endl;return 0;}
#ifndef _WIN32
  if(mode=="write-full"){CHECK(argc==4);std::signal(SIGXFSZ,SIG_IGN);struct rlimit limit{65536,65536};CHECK(setrlimit(RLIMIT_FSIZE,&limit)==0);rfl_record r{};int created=3;CHECK(rfl_import_file(l.p,argv[3],"full",nullptr,&r,&created,nullptr)==RFL_IO&&!r.hash[0]&&!created);pass("posix-real-short-write-preserves-old");return 0;}
#endif
  throw std::runtime_error("unknown mode");
}catch(const std::exception&e){std::cerr<<e.what()<<std::endl;return 1;}}
