/* SPDX-License-Identifier: MIT */
#include <reader_original_export.h>
#include <reader_commands.h>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#else
#include <sys/stat.h>
#include <csignal>
#endif
namespace fs=std::filesystem;
static void check(bool v,const char *s){if(!v)throw std::runtime_error(s);}
static std::string quote(const std::string &s){std::string r="\"";for(unsigned char c:s){if(c=='"'||c=='\\'){r+='\\';r+=static_cast<char>(c);}else if(c<32){char b[7];std::snprintf(b,sizeof b,"\\u%04x",c);r+=b;}else r+=static_cast<char>(c);}return r+'"';}
static std::string read(const fs::path &p){std::ifstream f(p,std::ios::binary);check(bool(f),"read fixture");return std::string(std::istreambuf_iterator<char>(f),{});}
static void write(const fs::path &p,const void *data,size_t n){std::ofstream f(p,std::ios::binary);f.write(static_cast<const char *>(data),static_cast<std::streamsize>(n));check(bool(f),"write output");}
static exr_library *open(const char *path){exr_library *l=nullptr;exr_error er{};check(exr_library_open(path,&l,&er)==EXR_OK,"library open");return l;}
static void seed(const char *db,const char *fixtures,const char *product){
  exr_library *l=open(db);exr_error er{};
  const char *exts[]={"txt","html","fb2","epub","docx","rtf","mobi","pdf","cbz"};
  for(int i=1;i<=11;i++){
    std::string file=i<=9?std::string("book.")+exts[i-1]:i==10?"large.txt":"changed.txt";
    std::string data=read(fs::u8path(fixtures)/file);int64_t id=0;
    if(exr_library_import(l,i<=9?static_cast<exr_format>(i):EXR_TXT,data.data(),data.size(),"../CON untrusted same title",&id,&er)!=EXR_OK){std::cerr<<file<<":"<<er.message<<std::endl;throw std::runtime_error("import");}
    check(id==i,"seed IDs");
  }
  exr_note note{};note.book_id=1;note.start=0;note.end=6;note.text=const_cast<char *>("preserve note");int64_t nid=0;
  check(exr_library_note(l,&note,&nid,&er)==EXR_OK,"seed note");
  exr_book *books=nullptr;size_t n=0;check(exr_library_books(l,nullptr,&books,&n,&er)==EXR_OK,"seed books");
  for(size_t i=0;i<n;i++)if(books[i].id==1){books[i].position=7;check(exr_library_update(l,&books[i],&er)==EXR_OK,"seed progress");}
  exr_books_free(books,n);exr_library_close(l);
  reader_revisions *store=nullptr;reader_revision_error re{};check(reader_revisions_open(product,&store,&re)==READER_REV_OK,"product open");
  reader_command_context c{};c.store=store;c.revision_id="11111111111111111111111111111111";
  reader_group_command group{};group.operation=READER_COMMAND_PUT;group.kind=READER_GROUP_SHELF;group.id="22222222222222222222222222222222";group.name="Preserve history and outbox";
  reader_command_result result{};reader_command_error error{};check(reader_command_apply_group(&c,&group,&result,&error)==READER_COMMAND_OK,"seed product history");
  check(reader_revisions_close(&store,&re)==READER_REV_OK,"product close");std::cout<<"{\"seeded\":11}"<<std::endl;
}
struct state {
  std::string mode,db,dir;roe_exporter *e=nullptr;roe_options *o=nullptr;bool leased=false,stop=false,fired=false;int reentry=0;int events=0;
#ifdef _WIN32
  HANDLE hold=INVALID_HANDLE_VALUE;
#endif
};
static int enter(void *p){auto &s=*static_cast<state *>(p);if(s.mode=="ownerdeny"||s.leased)return 1;s.leased=true;return 0;}
static void leave(void *p){static_cast<state *>(p)->leased=false;}
static int cancel(void *p){auto &s=*static_cast<state *>(p);return s.mode=="cancel0"||s.stop;}
static void progress(void *p,size_t index,roe_event ev,const roe_item *r){
  auto &s=*static_cast<state *>(p);s.events++;check(s.leased,"owner lease held at callback");
  if(s.mode=="reentry"&&!s.fired){s.fired=true;roe_result *nested=nullptr;roe_selection selected{1,nullptr};s.reentry=roe_run(s.e,&selected,1,s.o,&nested);check(!nested&&s.reentry==ROE_OWNER,"reentry refused");check(roe_destroy(&s.e)==ROE_OWNER,"destroy reentry refused");check(enter(&s)==1,"same owner SDK refused");}
  if(s.mode=="cancelafter1"&&ev==ROE_PUBLISHED&&index==0)s.stop=true;
  if(s.mode=="invalidate"&&ev==ROE_COPYING&&!s.fired){s.fired=true;exr_library *other=open(s.db.c_str());exr_book *books=nullptr;size_t n=0;exr_error er{};check(exr_library_books(other,nullptr,&books,&n,&er)==EXR_OK,"other books");books[0].favorite=!books[0].favorite;check(exr_library_update(other,&books[0],&er)==EXR_OK,"other invalidates source");exr_books_free(books,n);exr_library_close(other);}
  if(s.mode=="kill"&&ev==ROE_COPYING){std::cout<<"READY "<<r->cleanup_path<<std::endl;std::this_thread::sleep_for(std::chrono::minutes(10));}
  if(s.mode=="cleanfail"&&ev==ROE_COPYING&&!s.fired){s.fired=true;s.stop=true;
#ifdef _WIN32
    std::wstring w=fs::u8path(r->cleanup_path).wstring();s.hold=CreateFileW(w.c_str(),GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,nullptr,OPEN_EXISTING,0,nullptr);check(s.hold!=INVALID_HANDLE_VALUE,"hold temporary deletion lock");
#else
    check(chmod(s.dir.c_str(),0500)==0,"make cleanup fail");
#endif
  }
}
static void output(roe_status code,const roe_result *r,const state &s){
  std::cout<<"{\"status\":"<<code<<",\"reentry\":"<<s.reentry<<",\"events\":"<<s.events<<",\"items\":[";
  if(r)for(size_t i=0;i<r->count;i++){const auto &v=r->items[i];if(i)std::cout<<',';std::cout<<"{\"id\":"<<v.book_id<<",\"status\":"<<v.status<<",\"committed\":"<<v.committed<<",\"created\":"<<v.created<<",\"durable\":"<<v.durable<<",\"cleanup_pending\":"<<v.cleanup_pending<<",\"format\":"<<v.format<<",\"bytes\":"<<v.bytes<<",\"hash\":"<<quote(v.original_sha256)<<",\"path\":"<<quote(v.output_path)<<",\"cleanup_path\":"<<quote(v.cleanup_path)<<'}';}
  std::cout<<"]}"<<std::endl;
}
static void run(int argc,char **argv){
  check(argc>=6,"export args");state s;s.db=argv[2];s.dir=argv[3];s.mode=argv[4];exr_library *lib=open(argv[2]);roe_owner owner{enter,leave,&s};check(roe_create(lib,&owner,&s.e)==ROE_OK,"exporter create");
  roe_options o{};o.directory=argv[3];o.callbacks={cancel,progress,&s};s.o=&o;
  if(s.mode=="badutf")o.directory="/bad\xffpath";
  std::string slug="Readable_Name";if(s.mode=="display"||s.mode=="badslug"||s.mode=="device"){o.naming=ROE_DISPLAY_NAME;if(s.mode=="badslug")slug="../escape";if(s.mode=="device")slug="CON";}
  if(s.mode=="booklimit")o.per_book_bytes=1;if(s.mode=="batchlimit")o.batch_bytes=1;if(s.mode=="hardlimit")o.batch_bytes=ROE_HARD_BATCH_BYTES+1;
  std::vector<roe_selection> selected;std::stringstream ids(argv[5]);std::string id;while(std::getline(ids,id,','))selected.push_back({std::stoll(id),slug.c_str()});
  roe_result *r=nullptr;roe_status status;
  if(s.mode=="wrongthread"){status=ROE_OK;std::thread t([&]{status=roe_run(s.e,selected.data(),selected.size(),&o,&r);});t.join();}
  else status=roe_run(s.e,selected.data(),selected.size(),&o,&r);
  output(status,r,s);roe_result_free(r);
#ifdef _WIN32
  if(s.hold!=INVALID_HANDLE_VALUE)CloseHandle(s.hold);
#else
  if(s.mode=="cleanfail")check(chmod(s.dir.c_str(),0700)==0,"restore directory");
#endif
  check(roe_destroy(&s.e)==ROE_OK,"destroy");check(!s.leased,"released owner");exr_library_close(lib);
}
static int outbox(void *p,const reader_revision_outbox_row *r){auto *out=static_cast<std::string *>(p);*out+=std::to_string(r->queue_id)+":"+std::to_string(r->attempts)+":"+r->wire+"\n";return 0;}
static void inspect(const char *db,const char *dir,const char *product){
  fs::create_directories(fs::u8path(dir));exr_library *l=open(db);exr_error er{};exr_book *books=nullptr;size_t n=0;check(exr_library_books(l,nullptr,&books,&n,&er)==EXR_OK,"inspect books");std::ostringstream meta;
  for(size_t i=0;i<n;i++){auto &b=books[i];void *data=nullptr;size_t bytes=0;check(exr_library_blob(l,b.id,0,&data,&bytes,&er)==EXR_OK,"inspect original");write(fs::u8path(dir)/(std::to_string(b.id)+".original"),data,bytes);exr_free(data);
    meta<<b.id<<':'<<b.format<<':'<<b.position<<':'<<b.favorite<<':'<<b.title<<'\n';
    if(b.id==1){exr_note *notes=nullptr;size_t nn=0;check(exr_library_notes(l,b.id,&notes,&nn,&er)==EXR_OK,"notes");for(size_t k=0;k<nn;k++)meta<<notes[k].id<<':'<<notes[k].start<<':'<<notes[k].end<<':'<<notes[k].text<<'\n';exr_notes_free(notes,nn);exr_anchor a{};exr_anchor_state st;check(exr_library_progress_get(l,1,&a,&st,&er)==EXR_OK,"progress");meta<<"progress:"<<st<<':'<<a.start<<':'<<a.end<<'\n';exr_anchor_free(&a);}
  }exr_books_free(books,n);exr_library_close(l);std::string m=meta.str();write(fs::u8path(dir)/"sdk.txt",m.data(),m.size());
  reader_revisions *store=nullptr;reader_revision_error error{};check(reader_revisions_open(product,&store,&error)==READER_REV_OK,"inspect product");char *wire=nullptr;size_t bytes=0;reader_revision_info info{};check(reader_revision_get(store,"11111111111111111111111111111111",&wire,&bytes,&info,&error)==READER_REV_OK,"retained history");write(fs::u8path(dir)/"history.json",wire,bytes);reader_revision_bytes_free(wire);
  std::string q;check(reader_revision_outbox(store,100,outbox,&q,&error)==READER_REV_OK&&!q.empty(),"outbox retained");write(fs::u8path(dir)/"outbox.txt",q.data(),q.size());check(reader_revisions_close(&store,&error)==READER_REV_OK,"close product");std::cout<<"{\"inspected\":11}"<<std::endl;
}
int main(int argc,char **argv){try{
#ifndef _WIN32
  std::signal(SIGXFSZ,SIG_IGN);
#endif
  check(argc>=2,"command");std::string command=argv[1];
  if(command=="seed"){check(argc==5,"seed args");seed(argv[2],argv[3],argv[4]);}
  else if(command=="inspect"){check(argc==5,"inspect args");inspect(argv[2],argv[3],argv[4]);}
  else if(command=="export")run(argc,argv);else throw std::runtime_error("unknown command");return 0;
}catch(const std::exception &e){std::cerr<<e.what()<<std::endl;return 1;}}
