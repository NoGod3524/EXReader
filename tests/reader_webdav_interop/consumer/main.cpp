/* SPDX-License-Identifier: MIT */
/* Installed-module driver for real-service interoperability. It only calls the
   public EXReaderWebDAV/EXReaderRevisions/EXReaderSync C APIs. The test
   Authorization value is read from the environment, never from argv, and is
   never written to stdout/stderr. */
#include <reader_sync.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#include <vector>
namespace fs=std::filesystem;
static std::string quoted(const char *text){
  std::string out="\"";
  for(const unsigned char *p=(const unsigned char *)(text?text:"");*p;p++){
    if(*p=='"'||*p=='\\'){out+='\\';out+=(char)*p;}
    else if(*p<32){char e[8];std::snprintf(e,sizeof(e),"\\u%04x",*p);out+=e;}
    else out+=(char)*p;
  }
  return out+'"';
}
struct host {fs::path originals;uint64_t received=0,cancel_at=UINT64_MAX;};
static int original(void *opaque,const char *key,char *path,size_t capacity){
  auto &h=*(host *)opaque;std::string k=key;size_t colon=k.find(':');
  std::string value=(h.originals/(k.substr(colon+1)+"."+k.substr(0,colon))).string();
  if(value.size()>=capacity||!fs::exists(value))return 1;
  std::memcpy(path,value.c_str(),value.size()+1);return 0;
}
static int cancel(void *opaque){auto &h=*(host *)opaque;return h.received>=h.cancel_at;}
static void progress(void *opaque,uint64_t received){((host *)opaque)->received=received;}
static uint64_t number(const std::string &s){return std::strtoull(s.c_str(),nullptr,10);}
static exr_webdav_client *client(const std::string &root,uint64_t download,size_t listing,size_t entries,exr_webdav_error &error,exr_webdav_status &status){
  exr_webdav_config config{};config.root_url=root.c_str();config.authorization=std::getenv("READER_INTEROP_AUTH");
  config.max_download_bytes=download;config.max_listing_bytes=listing;config.max_entries=entries;config.timeout_ms=60000;
  exr_webdav_client *dav=nullptr;status=exr_webdav_create(&config,&dav,&error);return dav;
}
static void dav_result(exr_webdav_status status,const exr_webdav_error &error,const std::string &extra=""){
  std::cout<<"{\"status\":"<<(int)status<<",\"http_status\":"<<error.http_status<<",\"message\":"<<quoted(error.message)<<extra<<"}\n";
}
static int dav(const std::vector<std::string> &a){
  host h;exr_webdav_control control{cancel,progress,&h};exr_webdav_error error{};exr_webdav_status status;
  const std::string &op=a[1],&root=a[2];
  if(op=="dav-list"&&a.size()==6){
    exr_webdav_client *c=client(root,0,(size_t)number(a[4]),(size_t)number(a[5]),error,status);exr_webdav_listing listing{};
    if(c)status=exr_webdav_list(c,a[3].c_str(),&control,&listing,&error);
    std::string entries=",\"entries\":[";
    for(size_t i=0;i<listing.count;i++){const auto &e=listing.entries[i];if(i)entries+=',';
      entries+="{\"resource\":"+quoted(e.resource)+",\"display_name\":"+quoted(e.display_name)+",\"etag\":"+quoted(e.etag)+
        ",\"bytes\":"+std::to_string(e.bytes)+",\"has_size\":"+std::to_string(e.has_size)+",\"collection\":"+std::to_string(e.collection)+"}";}
    dav_result(status,error,entries+"]");exr_webdav_listing_free(&listing);exr_webdav_free(c);return 0;
  }
  if(op=="dav-get"&&a.size()==7){
    exr_webdav_client *c=client(root,number(a[6]),0,0,error,status);exr_webdav_download download{};
    if(c)status=exr_webdav_download_file(c,a[3].c_str(),a[4].c_str(),a[5].c_str(),&control,&download,&error);
    dav_result(status,error,",\"bytes\":"+std::to_string(download.bytes)+",\"published\":"+std::to_string(download.published));exr_webdav_free(c);return 0;
  }
  if(op=="dav-mkcol"&&a.size()==4){
    exr_webdav_client *c=client(root,0,0,0,error,status);
    if(c)status=exr_webdav_make_collection(c,a[3].c_str(),&control,&error);
    dav_result(status,error);exr_webdav_free(c);return 0;
  }
  if(op=="dav-put"&&a.size()==6){
    exr_webdav_client *c=client(root,0,0,0,error,status);
    if(c)status=exr_webdav_publish_file(c,a[3].c_str(),a[4].c_str(),number(a[5]),&control,&error);
    dav_result(status,error);exr_webdav_free(c);return 0;
  }
  return 2;
}
static int sync(const std::vector<std::string> &a){
  if(a.size()!=10)return 2;
  host h{fs::path(a[5])};h.cancel_at=a[9]=="-"?UINT64_MAX:number(a[9]);
  exr_webdav_error de{};exr_webdav_status ds;exr_webdav_client *c=client(a[2],0,0,0,de,ds);
  if(!c){std::cout<<"{\"status\":3,\"dav_code\":"<<(int)ds<<",\"revision_code\":0,\"http_status\":"<<de.http_status<<"}\n";return 0;}
  reader_revisions *revisions=nullptr;reader_revision_error re{};reader_revision_status rs=reader_revisions_open(a[3].c_str(),&revisions,&re);
  if(rs){exr_webdav_free(c);std::cout<<"{\"status\":4,\"dav_code\":0,\"revision_code\":"<<(int)rs<<",\"http_status\":0}\n";return 0;}
  reader_sync_config config{c,revisions,a[4].c_str(),original,&h};reader_sync *s=nullptr;reader_sync_error error{};reader_sync_report report{};
  int status=reader_sync_create(&config,&s,&error);exr_webdav_control control{cancel,progress,&h};
  if(!status)status=reader_sync_step(s,(unsigned)number(a[6]),a[7]=="-"?"":a[7].c_str(),(size_t)number(a[8]),&control,&report,&error);
  std::cout<<"{\"status\":"<<status<<",\"dav_code\":"<<error.dav_code<<",\"revision_code\":"<<error.revision_code<<",\"http_status\":"<<error.http_status
    <<",\"message\":"<<quoted(error.message)<<",\"pushed\":"<<report.pushed<<",\"pulled\":"<<report.pulled<<",\"originals_verified\":"<<report.originals_verified
    <<",\"pending_metadata\":"<<report.pending_metadata<<",\"pending_local_original\":"<<report.pending_local_original
    <<",\"remaining_in_shard\":"<<report.remaining_in_shard<<",\"shard_complete\":"<<report.shard_complete<<",\"shard\":"<<report.shard
    <<",\"next_shard\":"<<report.next_shard<<",\"shard_count\":"<<report.shard_count<<",\"after\":"<<quoted(report.after)
    <<",\"full_library_complete\":"<<report.full_library_complete<<"}\n";
  reader_sync_free(s);reader_revisions_close(&revisions,nullptr);exr_webdav_free(c);return 0;
}
static int head(void *opaque,const reader_revision_head *h){
  auto &v=*(std::string *)opaque;if(!v.empty())v+=',';
  v+="{\"id\":"+quoted(h->revision_id)+",\"operation\":"+quoted(h->operation)+",\"complete\":"+std::to_string(h->complete)+"}";return 0;
}
static int revision(const std::vector<std::string> &a){
  reader_revisions *store=nullptr;reader_revision_error error{};reader_revision_info info{};reader_revision_state state{};
  int created=0;std::string heads;reader_revision_status status=reader_revisions_open(a[2].c_str(),&store,&error);
  if(status==READER_REV_OK){
    if(a[1]=="local"&&a.size()==4){
      std::ifstream input(a[3],std::ios::binary);std::string wire((std::istreambuf_iterator<char>(input)),{});
      status=reader_revision_local(store,wire.data(),wire.size(),&info,&created,&error);
    }else if(a[1]=="get"&&a.size()==5){
      char *wire=nullptr;size_t bytes=0;status=reader_revision_get(store,a[3].c_str(),&wire,&bytes,&info,&error);
      if(status==READER_REV_OK){std::ofstream output(a[4],std::ios::binary);output.write(wire,(std::streamsize)bytes);if(!output)return 3;}
      reader_revision_bytes_free(wire);
    }else if(a[1]=="heads"&&a.size()==5)status=reader_revision_heads(store,a[3].c_str(),a[4].c_str(),head,&heads,&state,&error);
    else{reader_revisions_close(&store,nullptr);return 2;}
  }
  if(store&&reader_revisions_close(&store,nullptr)!=READER_REV_OK)return 4;
  std::cout<<"{\"status\":"<<(int)status<<",\"created\":"<<created<<",\"id\":"<<quoted(info.revision_id)<<",\"sha256\":"<<quoted(info.sha256)
    <<",\"bytes\":"<<info.bytes<<",\"state\":{\"revisions\":"<<state.revisions<<",\"heads\":"<<state.heads<<",\"missing_parents\":"<<state.missing_parents
    <<",\"projection_safe\":"<<state.projection_safe<<",\"deleted\":"<<state.deleted<<"},\"heads\":["<<heads<<"]}\n";
  return 0;
}
int main(int argc,char **argv){try{
  std::vector<std::string> a(argv,argv+argc);if(a.size()<3)return 2;
  if(!a[1].compare(0,4,"dav-"))return dav(a);
  if(a[1]=="sync")return sync(a);
  return revision(a);
}catch(...){std::cerr<<"interop consumer failed\n";return 2;}}
