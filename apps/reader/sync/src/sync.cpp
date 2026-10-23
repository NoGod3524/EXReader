/* SPDX-License-Identifier: MIT */
#include "reader_sync.h"
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <map>
#include <memory>
#include <set>
#include <string>
#include <thread>
#include <vector>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <bcrypt.h>
#else
#include <openssl/evp.h>
#endif
namespace fs=std::filesystem;
namespace {
struct failure {reader_sync_status code;const char *message;int dav=0,revision=0,http=0;};
[[noreturn]] void reject(reader_sync_status code,const char *message){throw failure{code,message};}
void cancelled(const exr_webdav_control *c){if(c&&c->cancelled&&c->cancelled(c->context))reject(READER_SYNC_CANCELLED,"Sync step cancelled; retained work can be retried");}
void dav_check(exr_webdav_status code,const exr_webdav_error &e){if(code!=EXR_DAV_OK)throw failure{code==EXR_DAV_CANCELLED?READER_SYNC_CANCELLED:code==EXR_DAV_LIMIT?READER_SYNC_LIMIT:READER_SYNC_DAV,"WebDAV sync transfer refused",(int)code,0,e.http_status};}
void revision_check(reader_revision_status code){if(code!=READER_REV_OK)throw failure{READER_SYNC_REVISION,"Revision identity or causal state refused",0,(int)code,0};}
bool hex(const std::string &s,size_t count){if(s.size()!=count)return false;for(char c:s)if(!((c>='0'&&c<='9')||(c>='a'&&c<='f')))return false;return true;}
std::string fresh(){char id[33];revision_check(reader_revision_new_id(id,nullptr));return id;}
class digest {
#ifdef _WIN32
  BCRYPT_ALG_HANDLE algorithm=nullptr;BCRYPT_HASH_HANDLE hash=nullptr;std::vector<unsigned char> memory;
#else
  EVP_MD_CTX *hash=nullptr;
#endif
public:
  digest(){
#ifdef _WIN32
    if(BCryptOpenAlgorithmProvider(&algorithm,BCRYPT_SHA256_ALGORITHM,nullptr,0)<0)reject(READER_SYNC_IO,"Cannot create native SHA-256 provider");
    DWORD bytes=0,size=0;if(BCryptGetProperty(algorithm,BCRYPT_OBJECT_LENGTH,(PUCHAR)&size,sizeof(size),&bytes,0)<0){BCryptCloseAlgorithmProvider(algorithm,0);algorithm=nullptr;reject(READER_SYNC_IO,"Cannot size native SHA-256 state");}
    memory.resize(size);if(BCryptCreateHash(algorithm,&hash,memory.data(),size,nullptr,0,0)<0){BCryptCloseAlgorithmProvider(algorithm,0);algorithm=nullptr;reject(READER_SYNC_IO,"Cannot create native SHA-256 state");}
#else
    hash=EVP_MD_CTX_new();if(!hash||EVP_DigestInit_ex(hash,EVP_sha256(),nullptr)!=1){if(hash)EVP_MD_CTX_free(hash);hash=nullptr;reject(READER_SYNC_IO,"Cannot create native SHA-256 state");}
#endif
  }
  ~digest(){
#ifdef _WIN32
    if(hash)BCryptDestroyHash(hash);if(algorithm)BCryptCloseAlgorithmProvider(algorithm,0);
#else
    if(hash)EVP_MD_CTX_free(hash);
#endif
  }
  void append(const void *data,size_t bytes){
#ifdef _WIN32
    if(BCryptHashData(hash,(PUCHAR)data,(ULONG)bytes,0)<0)reject(READER_SYNC_IO,"Native SHA-256 update failed");
#else
    if(EVP_DigestUpdate(hash,data,bytes)!=1)reject(READER_SYNC_IO,"Native SHA-256 update failed");
#endif
  }
  std::string finish(){unsigned char out[32];
#ifdef _WIN32
    if(BCryptFinishHash(hash,out,sizeof(out),0)<0)reject(READER_SYNC_IO,"Native SHA-256 finalization failed");
#else
    unsigned count=0;if(EVP_DigestFinal_ex(hash,out,&count)!=1||count!=32)reject(READER_SYNC_IO,"Native SHA-256 finalization failed");
#endif
    std::string s;const char *h="0123456789abcdef";for(unsigned char b:out){s+=h[b>>4];s+=h[b&15];}return s;
  }
};
struct private_file {fs::path name;bool keep=false;explicit private_file(const fs::path &folder):name(folder/fs::u8path(".reader-sync-"+fresh()+".tmp")){}~private_file(){if(!keep){std::error_code e;fs::remove(name,e);}}};
std::string hash_file(const fs::path &name,uint64_t expected,const exr_webdav_control *control,fs::path *snapshot=nullptr){
  if(!expected||expected>UINT64_C(128)*1024*1024||fs::is_symlink(fs::symlink_status(name))||!fs::is_regular_file(name)||fs::file_size(name)!=expected)reject(READER_SYNC_HASH,"Original file length or type differs from its verified identity");
  std::ifstream input(name,std::ios::binary);if(!input)reject(READER_SYNC_IO,"Private original is unavailable");
  std::ofstream output;if(snapshot){output.open(*snapshot,std::ios::binary|std::ios::out);if(!output)reject(READER_SYNC_IO,"Cannot create private original snapshot");}
  digest hash;unsigned char bytes[65536];uint64_t total=0;
  while(input){cancelled(control);input.read((char *)bytes,sizeof(bytes));size_t n=(size_t)input.gcount();if(n>expected-total)reject(READER_SYNC_HASH,"Original changed while being verified");hash.append(bytes,n);if(snapshot)output.write((const char *)bytes,(std::streamsize)n);total+=n;}
  if(!input.eof()||total!=expected)reject(READER_SYNC_HASH,"Original changed or failed during verification");
  if(snapshot){output.flush();if(!output)reject(READER_SYNC_IO,"Cannot flush verified private snapshot");}
  cancelled(control);return hash.finish();
}
struct queue_row {reader_revision_info info{};std::string wire;};
int queued(void *context,const reader_revision_outbox_row *row){auto &v=*(std::vector<queue_row> *)context;queue_row q;q.info=row->info;q.wire.assign(row->wire,row->info.bytes);v.push_back(std::move(q));return 0;}
std::string shard_name(unsigned shard){char value[3];std::snprintf(value,sizeof(value),"%02x",shard);return value;}
std::string collection(const char *kind,const std::string &prefix){return std::string("exreader-sync-v1/")+kind+"/"+prefix+"/";}
std::string object_name(const std::string &key){size_t colon=key.find(':');return key.substr(colon+1)+"."+key.substr(0,colon);}
std::string object_path(const std::string &key){size_t colon=key.find(':');return collection("objects",key.substr(colon+1,2))+object_name(key);}
std::string revision_name(const reader_revision_info &i){return std::string(i.revision_id)+"-"+i.sha256+".json";}
bool revision_leaf(const std::string &s){return s.size()==102&&hex(s.substr(0,32),32)&&s[32]=='-'&&hex(s.substr(33,64),64)&&s.substr(97)==".json";}
}
struct reader_sync {exr_webdav_client *dav;reader_revisions *revisions;fs::path directory;reader_sync_original_fn original;void *context;std::thread::id owner=std::this_thread::get_id();bool active=false;};
namespace {
struct guard {reader_sync *sync;explicit guard(reader_sync *s):sync(s){if(!s||s->owner!=std::this_thread::get_id()||s->active)reject(READER_SYNC_ARGUMENT,"Sync requires its creating worker without reentry");s->active=true;}~guard(){sync->active=false;}};
struct listing {exr_webdav_listing value{};~listing(){exr_webdav_listing_free(&value);}};
struct step {
  reader_sync &s;const exr_webdav_control *control;reader_sync_report &report;
  std::map<std::string,std::set<std::string>> initialized;
  step(reader_sync &sync,const exr_webdav_control *c,reader_sync_report &r):s(sync),control(c),report(r){}
  void ensure(const std::string &folder){
    if(initialized.count(folder))return;
    size_t end=folder.find('/');while(end!=std::string::npos){std::string part=folder.substr(0,end+1);if(!initialized.count(part)){
      exr_webdav_error error{};dav_check(exr_webdav_make_collection(s.dav,part.c_str(),control,&error),error);
      listing listed;dav_check(exr_webdav_list(s.dav,part.c_str(),control,&listed.value,&error),error);
      std::set<std::string> resources;for(size_t i=0;i<listed.value.count;i++)resources.insert(listed.value.entries[i].resource);initialized.emplace(part,std::move(resources));
    }end=folder.find('/',end+1);}
  }
  void download(const std::string &resource,private_file &file){exr_webdav_error error{};exr_webdav_download result{};dav_check(exr_webdav_download_file(s.dav,resource.c_str(),s.directory.u8string().c_str(),file.name.filename().u8string().c_str(),control,&result,&error),error);}
  void publish(const std::string &resource,const fs::path &file,uint64_t bytes,const std::string &expected){
    std::string folder=resource.substr(0,resource.find_last_of('/')+1);ensure(folder);auto &entries=initialized[folder];
    if(entries.size()>=2000&&!entries.count(resource))reject(READER_SYNC_LIMIT,"Immutable shard has reached its 2000-entry discovery ceiling");
    exr_webdav_error error{};exr_webdav_status status=exr_webdav_publish_file(s.dav,resource.c_str(),file.u8string().c_str(),bytes,control,&error);
    if(status!=EXR_DAV_OK&&status!=EXR_DAV_EXISTS&&status!=EXR_DAV_IO)dav_check(status,error);
    // An interrupted response can follow a committed PUT. A fresh GET is the
    // only success/412/ambiguous-IO acknowledgement authority.
    private_file verify(s.directory);download(resource,verify);if(hash_file(verify.name,bytes,control)!=expected)reject(READER_SYNC_HASH,"Remote immutable object differs from the original bytes");
    entries.insert(resource);
  }
  bool local_original(const reader_revision_info &i){
    if(!i.book_key[0])return true;
    uint64_t bytes=0;reader_revision_status status=reader_revision_book_identity(s.revisions,i.book_key,&bytes,nullptr);
    if(status==READER_REV_NOT_FOUND){++report.pending_metadata;return false;}revision_check(status);
    char path[8192]{};
    bool available=s.original&&!s.original(s.context,i.book_key,path,sizeof(path))&&path[0]&&!path[sizeof(path)-1];
    if(!available){
      // Removing a local download must not strand its deletion/metadata queue.
      // A known-length, hash-verified immutable remote original is sufficient.
      private_file verify(s.directory);
      try{download(object_path(i.book_key),verify);}catch(const failure &f){if(f.dav==EXR_DAV_HTTP&&f.http==404){++report.pending_local_original;return false;}throw;}
      std::string key=i.book_key;if(hash_file(verify.name,bytes,control)!=key.substr(key.find(':')+1))reject(READER_SYNC_HASH,"Existing remote original identity differs");
      ++report.originals_verified;return true;
    }
    private_file snapshot(s.directory);fs::path target=snapshot.name;std::string expected=std::string(i.book_key).substr(std::string(i.book_key).find(':')+1);
    if(hash_file(fs::u8path(path),bytes,control,&target)!=expected)reject(READER_SYNC_HASH,"Local original SHA-256 differs from its global book identity");
    publish(object_path(i.book_key),snapshot.name,bytes,expected);++report.originals_verified;return true;
  }
  void push(size_t limit){
    std::vector<queue_row> rows;revision_check(reader_revision_outbox(s.revisions,limit,queued,&rows,nullptr));
    for(const auto &row:rows){cancelled(control);if(!local_original(row.info))continue;
      private_file wire(s.directory);{std::ofstream output(wire.name,std::ios::binary);output.write(row.wire.data(),(std::streamsize)row.wire.size());if(!output)reject(READER_SYNC_IO,"Cannot stage exact revision bytes");}
      std::string resource=collection("revisions",std::string(row.info.revision_id,2))+revision_name(row.info);
      publish(resource,wire.name,row.wire.size(),row.info.sha256);revision_check(reader_revision_ack(s.revisions,row.info.revision_id,row.info.sha256,nullptr));++report.pushed;
    }
  }
  void remote_original(const reader_revision_info &i){
    if(!i.book_key[0])return;
    uint64_t bytes=i.source_bytes;reader_revision_status status=bytes?READER_REV_OK:reader_revision_book_identity(s.revisions,i.book_key,&bytes,nullptr);
    if(status==READER_REV_NOT_FOUND){++report.pending_metadata;return;}revision_check(status);
    std::string key=i.book_key,expected=key.substr(key.find(':')+1);fs::path cached=s.directory/fs::u8path(object_name(key));
    if(fs::exists(cached)){if(hash_file(cached,bytes,control)!=expected)reject(READER_SYNC_HASH,"Private original cache identity differs");}
    else {private_file raw(s.directory);download(object_path(key),raw);if(hash_file(raw.name,bytes,control)!=expected)reject(READER_SYNC_HASH,"Downloaded original identity differs");fs::rename(raw.name,cached);raw.keep=true;}
    ++report.originals_verified;
  }
  void pull(unsigned shard,const std::string &after,size_t limit){
    std::string folder=collection("revisions",shard_name(shard));listing listed;exr_webdav_error error{};exr_webdav_status status=exr_webdav_list(s.dav,folder.c_str(),control,&listed.value,&error);
    if(status==EXR_DAV_HTTP&&error.http_status==404){report.shard_complete=1;report.next_shard=(shard+1)%256;return;}dav_check(status,error);
    std::vector<std::string> leaves;for(size_t n=0;n<listed.value.count;n++){
      const auto &entry=listed.value.entries[n];std::string resource=entry.resource,leaf=resource.substr(folder.size());
      if(entry.collection||!revision_leaf(leaf)||leaf.substr(0,2)!=shard_name(shard)||!entry.has_size||entry.bytes>READER_REVISION_MAX_BYTES)reject(READER_SYNC_HASH,"Immutable revision shard entry identity is invalid");
      if(leaf>after)leaves.push_back(leaf);
    }
    std::sort(leaves.begin(),leaves.end());size_t count=std::min(limit,leaves.size());
    for(size_t n=0;n<count;n++){
      cancelled(control);private_file file(s.directory);download(folder+leaves[n],file);uint64_t size=fs::file_size(file.name);if(size>READER_REVISION_MAX_BYTES)reject(READER_SYNC_LIMIT,"Revision exceeds wire byte ceiling");
      std::ifstream input(file.name,std::ios::binary);std::string wire((std::istreambuf_iterator<char>(input)),{});reader_revision_info info{};
      revision_check(reader_revision_validate(s.revisions,wire.data(),wire.size(),leaves[n].substr(33,64).c_str(),&info,nullptr));
      if(std::string(info.revision_id)!=leaves[n].substr(0,32))reject(READER_SYNC_HASH,"Remote revision ID differs from immutable path");
      // Verify a book's claimed immutable length before adopting it as the
      // authority for future references. Bad first metadata cannot poison the
      // retained book identity and block a later correct revision.
      if(info.source_bytes){uint64_t known=0;reader_revision_status book_status=reader_revision_book_identity(s.revisions,info.book_key,&known,nullptr);
        if(book_status!=READER_REV_NOT_FOUND)revision_check(book_status);
        if(book_status==READER_REV_OK&&known!=info.source_bytes)revision_check(READER_REV_FORMAT);
        remote_original(info);
      }
      // Non-book history is retained even without metadata; it remains
      // explicitly pending and is verified on the next complete sweep.
      int created=0;revision_check(reader_revision_receive(s.revisions,wire.data(),wire.size(),info.sha256,nullptr,&created,nullptr));
      if(!info.source_bytes)remote_original(info);
      ++report.pulled;std::snprintf(report.after,sizeof(report.after),"%s",leaves[n].c_str());
    }
    report.remaining_in_shard=leaves.size()-count;report.shard_complete=report.remaining_in_shard==0;
    if(report.shard_complete){report.after[0]=0;report.next_shard=(shard+1)%256;}
  }
};
template<class Function>reader_sync_status call(reader_sync_error *error,Function function){if(error)std::memset(error,0,sizeof(*error));try{function();return READER_SYNC_OK;}catch(const failure &f){if(error){error->code=f.code;error->dav_code=f.dav;error->revision_code=f.revision;error->http_status=f.http;std::snprintf(error->message,sizeof(error->message),"%s",f.message);}return f.code;}catch(...){if(error){error->code=READER_SYNC_IO;std::snprintf(error->message,sizeof(error->message),"Private sync operation failed");}return READER_SYNC_IO;}}
}
extern "C" reader_sync_status reader_sync_create(const reader_sync_config *config,reader_sync **out,reader_sync_error *error){if(out)*out=nullptr;return call(error,[&]{
  if(!config||!out||!config->dav||!config->revisions||!config->private_directory)reject(READER_SYNC_ARGUMENT,"Missing borrowed sync dependencies");
  fs::path folder=fs::u8path(config->private_directory);if(fs::is_symlink(fs::symlink_status(folder))||!fs::is_directory(folder))reject(READER_SYNC_ARGUMENT,"Sync requires a stable private cache directory");
  std::unique_ptr<reader_sync> s(new reader_sync);s->dav=config->dav;s->revisions=config->revisions;s->directory=folder;s->original=config->original;s->context=config->context;*out=s.release();
});}
extern "C" void reader_sync_free(reader_sync *sync){delete sync;}
extern "C" reader_sync_status reader_sync_step(reader_sync *sync,unsigned shard,const char *after,size_t limit,const exr_webdav_control *control,reader_sync_report *out,reader_sync_error *error){if(out)std::memset(out,0,sizeof(*out));return call(error,[&]{
  guard owner(sync);if(shard>255||!after||!out||!limit||limit>100||(*after&&!revision_leaf(after)))reject(READER_SYNC_ARGUMENT,"Invalid bounded sync shard/cursor request");
  out->shard=shard;out->next_shard=shard;out->shard_count=256;cancelled(control);step session(*sync,control,*out);session.push(limit);session.pull(shard,after,limit);
});}
