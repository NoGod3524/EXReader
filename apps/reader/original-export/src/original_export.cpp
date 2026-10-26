/* SPDX-License-Identifier: MIT */
#ifndef _WIN32
#define _FILE_OFFSET_BITS 64
#endif
#include "reader_original_export.h"
#include <algorithm>
#include <atomic>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <new>
#include <set>
#include <string>
#include <thread>
#include <vector>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#else
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#endif
struct roe_exporter {
  exr_library *library; roe_owner owner; std::thread::id thread; bool busy=false;
};
namespace {
std::mutex owners_mutex;
std::set<exr_library *> owners;
std::atomic<unsigned long long> serial{0};
struct failure { roe_status status; };
void need(bool ok, roe_status status) { if (!ok) throw failure{status}; }
#include "sha256.inc"
void digest(Sha256 &s,char out[65]) {
  static const char chars[]="0123456789abcdef"; unsigned char bytes[32]; s.finish(bytes);
  for(size_t i=0;i<32;i++){out[2*i]=chars[bytes[i]>>4];out[2*i+1]=chars[bytes[i]&15];} out[64]=0;
}
struct gate {
  roe_exporter *e;
  explicit gate(roe_exporter *p):e(p){ need(e->owner.enter(e->owner.context)==0,ROE_OWNER); }
  ~gate(){e->owner.leave(e->owner.context);}
};
struct busy_guard { roe_exporter *e; explicit busy_guard(roe_exporter *p):e(p){e->busy=true;} ~busy_guard(){e->busy=false;} };
const char *extension(exr_format f) {
  static const char *names[]={"","txt","html","fb2","epub","docx","rtf","mobi","pdf","cbz"};
  return f>=EXR_TXT&&f<=EXR_CBZ?names[static_cast<unsigned>(f)]:nullptr;
}
bool utf8(const std::string &s) {
  for(size_t i=0;i<s.size();) {
    unsigned c=static_cast<unsigned char>(s[i++]), n=0, v=0, minimum=0;
    if(c<0x80){if(c<32||c==127)return false;continue;}
    if(c>=0xc2&&c<=0xdf){n=1;v=c&31;minimum=0x80;}
    else if(c>=0xe0&&c<=0xef){n=2;v=c&15;minimum=0x800;}
    else if(c>=0xf0&&c<=0xf4){n=3;v=c&7;minimum=0x10000;} else return false;
    if(i+n>s.size())return false;
    while(n--){c=static_cast<unsigned char>(s[i++]);if((c&0xc0)!=0x80)return false;v=(v<<6)|(c&63);}
    if(v<minimum||v>0x10ffff||(v>=0xd800&&v<=0xdfff))return false;
  } return true;
}
std::string bounded(const char *p,size_t max) {
  need(p!=nullptr,ROE_ARGUMENT);size_t n=0;while(n<=max&&p[n])++n;
  need(n&&n<=max,ROE_ARGUMENT);std::string s(p,n);need(utf8(s),ROE_ARGUMENT);return s;
}
bool reserved(std::string s) {
  for(char &c:s)if(c>='a'&&c<='z')c=static_cast<char>(c-'a'+'A');
  return s=="CON"||s=="PRN"||s=="AUX"||s=="NUL"||s=="CLOCK$"||
    (s.size()==4&&(s.substr(0,3)=="COM"||s.substr(0,3)=="LPT")&&s[3]>='0'&&s[3]<='9');
}
std::string slug(const char *p) {
  std::string s=bounded(p,64);need(!reserved(s),ROE_ARGUMENT);
  for(unsigned char c:s)need((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='_'||c=='-',ROE_ARGUMENT);
  return s;
}
void pathcopy(char *out,const std::string &s){need(s.size()<ROE_PATH_CAP,ROE_ARGUMENT);std::memcpy(out,s.c_str(),s.size()+1);}
#ifdef _WIN32
std::wstring wide(const std::string &s) {
  int n=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,s.c_str(),-1,nullptr,0);need(n>0,ROE_ARGUMENT);
  std::wstring r(static_cast<size_t>(n),L'\0');need(MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,s.c_str(),-1,&r[0],n)==n,ROE_ARGUMENT);r.resize(static_cast<size_t>(n-1));return r;
}
using file=HANDLE;const file invalid=INVALID_HANDLE_VALUE;
void closefile(file f){if(f!=invalid)CloseHandle(f);}
bool writefile(file f,const void *p,size_t n){DWORD done=0;return WriteFile(f,p,static_cast<DWORD>(n),&done,nullptr)&&done==n;}
size_t readfile(file f,void *p,size_t n){DWORD done=0;return ReadFile(f,p,static_cast<DWORD>(n),&done,nullptr)?done:0;}
bool rewindfile(file f){LARGE_INTEGER zero{};return SetFilePointerEx(f,zero,nullptr,FILE_BEGIN)!=0;}
bool flushfile(file f){return FlushFileBuffers(f)!=0;}
bool regular(file f,uint64_t *size=nullptr){BY_HANDLE_FILE_INFORMATION i{};if(!GetFileInformationByHandle(f,&i)||i.dwFileAttributes&(FILE_ATTRIBUTE_REPARSE_POINT|FILE_ATTRIBUTE_DIRECTORY)||i.nNumberOfLinks!=1)return false;if(size)*size=(uint64_t(i.nFileSizeHigh)<<32)|i.nFileSizeLow;return true;}
#else
using file=int;constexpr file invalid=-1;
void closefile(file f){if(f!=invalid)close(f);}
bool writefile(file f,const void *p,size_t n){const char *b=static_cast<const char *>(p);while(n){ssize_t done=write(f,b,n);if(done<0&&errno==EINTR)continue;if(done<=0)return false;b+=done;n-=static_cast<size_t>(done);}return true;}
size_t readfile(file f,void *p,size_t n){ssize_t done;do{done=read(f,p,n);}while(done<0&&errno==EINTR);return done>0?static_cast<size_t>(done):0;}
bool rewindfile(file f){return lseek(f,0,SEEK_SET)==0;}
bool flushfile(file f){return fsync(f)==0;}
bool regular(file f,uint64_t *size=nullptr){struct stat s{};if(fstat(f,&s)||!S_ISREG(s.st_mode)||s.st_nlink!=1||s.st_size<0)return false;if(size)*size=static_cast<uint64_t>(s.st_size);return true;}
#endif
struct handle { file f=invalid; ~handle(){closefile(f);} };
struct directory {
  std::string path;
#ifdef _WIN32
  std::vector<file> held;
#else
  file fd=invalid;
#endif
  ~directory(){
#ifdef _WIN32
    for(file f:held)closefile(f);
#else
    closefile(fd);
#endif
  }
  void open(const char *input) {
    path=bounded(input,3500);
#ifdef _WIN32
    for(char &c:path)if(c=='\\')c='/';
    need(path.size()>3&&((path[0]>='A'&&path[0]<='Z')||(path[0]>='a'&&path[0]<='z'))&&path[1]==':'&&path[2]=='/',ROE_ARGUMENT);
    size_t start=3;
#else
    need(path[0]=='/'&&path.size()>1,ROE_ARGUMENT);size_t start=1;
#ifdef __ANDROID__
    constexpr int traversal_access=O_PATH;
#else
    constexpr int traversal_access=O_RDONLY;
#endif
    fd=::open("/",traversal_access|O_DIRECTORY|O_CLOEXEC);need(fd!=invalid,ROE_IO);
#endif
    need(path.back()!='/',ROE_ARGUMENT);
    for(size_t pos=start;pos<=path.size();) {
      size_t end=path.find('/',pos);if(end==std::string::npos)end=path.size();std::string part=path.substr(pos,end-pos);
      need(!part.empty()&&part!="."&&part!=".."&&part.back()!='.'&&part.back()!=' '&&!reserved(part),ROE_ARGUMENT);
      need(part.find_first_of(":\\*?\"<>|")==std::string::npos,ROE_ARGUMENT);
#ifdef _WIN32
      std::wstring w=wide(path.substr(0,end));
      file h=CreateFileW(w.c_str(),FILE_READ_ATTRIBUTES,FILE_SHARE_READ|FILE_SHARE_WRITE,nullptr,OPEN_EXISTING,FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
      need(h!=invalid,ROE_IO);BY_HANDLE_FILE_INFORMATION i{};
      if(!GetFileInformationByHandle(h,&i)||(i.dwFileAttributes&FILE_ATTRIBUTE_REPARSE_POINT)||!(i.dwFileAttributes&FILE_ATTRIBUTE_DIRECTORY)){closefile(h);throw failure{ROE_ARGUMENT};}
      try{held.push_back(h);}catch(...){closefile(h);throw;}
#else
      int access=end==path.size()?O_RDONLY:traversal_access;
      file next=openat(fd,part.c_str(),access|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);need(next!=invalid,ROE_ARGUMENT);closefile(fd);fd=next;
#endif
      if(end==path.size())break;
      pos=end+1;
    }
  }
  file create(const std::string &leaf) {
#ifdef _WIN32
    return CreateFileW(wide(path+"/"+leaf).c_str(),GENERIC_READ|GENERIC_WRITE,FILE_SHARE_READ,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL|FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
#else
    return openat(fd,leaf.c_str(),O_RDWR|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
#endif
  }
  file existing(const std::string &leaf) {
#ifdef _WIN32
    return CreateFileW(wide(path+"/"+leaf).c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
#else
    return openat(fd,leaf.c_str(),O_RDONLY|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC);
#endif
  }
  bool remove(const std::string &leaf) {
#ifdef _WIN32
    return DeleteFileW(wide(path+"/"+leaf).c_str())!=0;
#else
    return unlinkat(fd,leaf.c_str(),0)==0;
#endif
  }
  bool publish(const std::string &tmp,const std::string &dst) {
#ifdef _WIN32
    return MoveFileExW(wide(path+"/"+tmp).c_str(),wide(path+"/"+dst).c_str(),MOVEFILE_WRITE_THROUGH)!=0;
#else
    return linkat(fd,tmp.c_str(),fd,dst.c_str(),0)==0;
#endif
  }
  bool sync(){
#ifdef _WIN32
    return true; // MOVEFILE_WRITE_THROUGH is the supported publication barrier.
#else
    return fsync(fd)==0;
#endif
  }
};
bool hashfile(file f,uint64_t size,char out[65],unsigned char (&buf)[65536]) {
  Sha256 s;s.init();if(!rewindfile(f))return false;
  uint64_t pos=0;while(pos<size){size_t n=readfile(f,buf,static_cast<size_t>(std::min<uint64_t>(sizeof(buf),size-pos)));if(!n)return false;s.update(buf,n);pos+=n;}
  if(readfile(f,buf,1)!=0)return false;
  digest(s,out);return true;
}
struct source_set {
  roe_exporter *e;exr_source sources[ROE_MAX_ITEMS]{};
  explicit source_set(roe_exporter *p):e(p){}
  ~source_set(){/* release is an SDK operation; caller retains host owner lease
      across source lifetimes below, including unwind. */
    for(auto &s:sources)if(s.release)s.release(s.context);
  }
};
void notify(const roe_options &o,size_t i,roe_event ev,const roe_item &r){if(o.callbacks.progress)o.callbacks.progress(o.callbacks.context,i,ev,&r);}
bool cancelled(const roe_options &o){return o.callbacks.cancelled&&o.callbacks.cancelled(o.callbacks.context)!=0;}
}
extern "C" roe_status roe_create(exr_library *library,const roe_owner *owner,roe_exporter **out){
  if(out)*out=nullptr;
  if(!out||!library||!owner||!owner->enter||!owner->leave)return ROE_ARGUMENT;
  try {std::lock_guard<std::mutex> lock(owners_mutex);if(owners.count(library))return ROE_OWNER;
    auto *p=new roe_exporter{library,*owner,std::this_thread::get_id(),false};
    try{owners.insert(library);}catch(...){delete p;throw;}*out=p;return ROE_OK;
  }catch(...){return ROE_MEMORY;}
}
extern "C" roe_status roe_destroy(roe_exporter **p){
  if(!p||!*p)return ROE_ARGUMENT;
  roe_exporter *e=*p;
  if(e->thread!=std::this_thread::get_id()||e->busy)return ROE_OWNER;
  try{std::lock_guard<std::mutex> lock(owners_mutex);owners.erase(e->library);delete e;*p=nullptr;return ROE_OK;}catch(...){return ROE_MEMORY;}
}
extern "C" void roe_result_free(roe_result *r){std::free(r);}
extern "C" roe_status roe_run(roe_exporter *e,const roe_selection *selected,size_t count,const roe_options *options,roe_result **out){
  if(out)*out=nullptr;
  if(!e||!selected||!options||!out||!count)return ROE_ARGUMENT;
  if(e->thread!=std::this_thread::get_id()||e->busy)return ROE_OWNER;
  if(count>ROE_MAX_ITEMS)return ROE_LIMIT;
  roe_result *result=static_cast<roe_result *>(std::calloc(1,sizeof(roe_result)));if(!result)return ROE_MEMORY;
  *out=result;result->count=count;for(size_t i=0;i<count;i++){result->items[i].book_id=selected[i].book_id;result->items[i].status=ROE_PENDING;}
  busy_guard busy(e);
  try {
    const roe_options o=*options;
    const uint64_t book=o.per_book_bytes?o.per_book_bytes:ROE_DEFAULT_BOOK_BYTES,batch=o.batch_bytes?o.batch_bytes:ROE_DEFAULT_BATCH_BYTES;
    need(book<=ROE_DEFAULT_BOOK_BYTES&&batch<=ROE_HARD_BATCH_BYTES,ROE_LIMIT);
    need(o.naming==ROE_HASH_NAME||o.naming==ROE_DISPLAY_NAME,ROE_ARGUMENT);
    std::string labels[ROE_MAX_ITEMS];for(size_t i=0;i<count;i++){need(selected[i].book_id>0,ROE_ARGUMENT);if(o.naming==ROE_DISPLAY_NAME)labels[i]=slug(selected[i].display_name);}
    directory dir;dir.open(o.directory);need(!cancelled(o),ROE_CANCELLED);
    /* Snapshot public formats. SDK 3.40 has no per-ID format getter; this public
       metadata query is SDK-bounded (EXR_MAX_ITEMS), not original-byte loading. */
    gate owner_lease(e);
    {exr_book *books=nullptr;size_t n=0;exr_error error{};
      exr_status st=exr_library_books(e->library,nullptr,&books,&n,&error);need(st==EXR_OK,ROE_SOURCE);
      for(size_t i=0;i<count;i++)for(size_t j=0;j<n;j++)if(books[j].id==selected[i].book_id){result->items[i].format=books[j].format;break;}
      exr_books_free(books,n);
    }
    uint64_t total=0;
    /* One host lease covers all sources, SDK calls, and their release.
       Progress callbacks run after SDK calls return, never inside the SDK. */
    source_set sources(e);
    for(size_t i=0;i<count;i++){
      roe_item &r=result->items[i];need(extension(r.format)!=nullptr,ROE_SOURCE);
      exr_error error{};r.sdk_status=exr_library_source(e->library,r.book_id,&sources.sources[i],&error);
      need(r.sdk_status==EXR_OK,ROE_SOURCE);r.bytes=sources.sources[i].size;
      need(r.bytes<=book&&r.bytes<=batch-total,ROE_LIMIT);total+=r.bytes;
    }
    for(size_t i=0;i<count;i++){
      roe_item &r=result->items[i];std::string temp;bool temporary=false;
      try{
        need(!cancelled(o),ROE_CANCELLED);
        temp=".roe-v1-"+std::to_string(
#ifdef _WIN32
          GetCurrentProcessId()
#else
          getpid()
#endif
        )+"-"+std::to_string(++serial)+".part";
        pathcopy(r.cleanup_path,dir.path+"/"+temp);
        handle f;f.f=dir.create(temp);need(f.f!=invalid,ROE_IO);temporary=true;r.cleanup_pending=1;
        notify(o,i,ROE_STAGED,r);Sha256 sha;sha.init();unsigned char buffer[65536];uint64_t pos=0;
        while(pos<r.bytes){need(!cancelled(o),ROE_CANCELLED);size_t got;
          {const exr_source &s=sources.sources[i];got=s.read_at(s.context,pos,buffer,static_cast<size_t>(std::min<uint64_t>(sizeof(buffer),r.bytes-pos)));}
          if(!got||got>std::min<uint64_t>(sizeof(buffer),r.bytes-pos)){r.sdk_status=EXR_IO;throw failure{ROE_SOURCE};}
          need(writefile(f.f,buffer,got),ROE_IO);sha.update(buffer,got);pos+=got;notify(o,i,ROE_COPYING,r);
        }
        digest(sha,r.original_sha256);need(flushfile(f.f),ROE_IO);char verified[65];
        need(hashfile(f.f,r.bytes,verified,buffer)&&std::strcmp(verified,r.original_sha256)==0,ROE_IO);
        std::string name=(o.naming==ROE_DISPLAY_NAME?labels[i]+"--":"")+r.original_sha256+"."+extension(r.format);
        pathcopy(r.output_path,dir.path+"/"+name);need(!cancelled(o),ROE_CANCELLED);
        closefile(f.f);f.f=invalid;
        if(dir.publish(temp,name)){
          r.committed=1;r.created=1;r.status=ROE_OK;
#ifdef _WIN32
          temporary=false;r.cleanup_pending=0;r.cleanup_path[0]=0;
#endif
          r.durable=dir.sync()?1:0;
        }else{
          handle existing;existing.f=dir.existing(name);uint64_t size=0;char existing_hash[65];
          need(existing.f!=invalid&&regular(existing.f,&size)&&size==r.bytes&&hashfile(existing.f,size,existing_hash,buffer)&&std::strcmp(existing_hash,r.original_sha256)==0,ROE_CONFLICT);
          r.committed=1;r.created=0;r.durable=1;r.status=ROE_OK;
        }
        if(temporary){if(dir.remove(temp)){temporary=false;if(dir.sync()){r.cleanup_pending=0;r.cleanup_path[0]=0;}else r.status=ROE_CLEANUP;}else r.status=ROE_CLEANUP;}
        if(!r.durable&&r.status==ROE_OK)r.status=ROE_IO;
        notify(o,i,ROE_PUBLISHED,r);
      }catch(const failure &f){r.status=f.status;}
      catch(const std::bad_alloc &){r.status=ROE_MEMORY;}
      catch(...){r.status=ROE_IO;}
      if(temporary){if(dir.remove(temp)){if(dir.sync()){r.cleanup_pending=0;r.cleanup_path[0]=0;}}else{r.cleanup_pending=1;}}
      if(r.status!=ROE_OK){result->status=r.status;for(size_t j=i+1;j<count;j++)result->items[j].status=r.status==ROE_CANCELLED?ROE_CANCELLED:ROE_PENDING;return result->status;}
    }
    result->status=ROE_OK;
  }catch(const failure &f){result->status=f.status;for(size_t i=0;i<count;i++)if(result->items[i].status==ROE_PENDING)result->items[i].status=f.status;}
  catch(const std::bad_alloc &){result->status=ROE_MEMORY;}
  catch(...){result->status=ROE_IO;}
  return result->status;
}
