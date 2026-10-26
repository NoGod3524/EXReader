// SPDX-License-Identifier: MIT
#include "reader_font_library.h"
#include "sha256.hpp"
#include <algorithm>
#include <array>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <map>
#include <memory>
#include <string>
#include <thread>
#include <vector>
#ifdef _WIN32
#include <windows.h>
#else
#include <fcntl.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#ifdef __ANDROID__
#include <linux/fs.h>
#include <sys/syscall.h>
#endif
#endif
namespace fs=std::filesystem;
namespace {
using rfl_detail::sha256;
struct failure { rfl_status code; const char *message; };
void need(bool value,rfl_status code,const char *message){if(!value)throw failure{code,message};}
bool utf8(const std::string &s,bool name){
  for(size_t i=0;i<s.size();){unsigned c=static_cast<unsigned char>(s[i++]);uint32_t cp=c;unsigned n=0;
    if(c>=0xc2&&c<=0xdf){cp=c&31;n=1;}else if(c>=0xe0&&c<=0xef){cp=c&15;n=2;}else if(c>=0xf0&&c<=0xf4){cp=c&7;n=3;}else if(c>=0x80)return false;
    if(i+n>s.size())return false;
    for(unsigned j=0;j<n;++j){unsigned b=static_cast<unsigned char>(s[i++]);if((b&0xc0)!=0x80)return false;cp=(cp<<6)|(b&63);}
    if((n==1&&cp<128)||(n==2&&cp<2048)||(n==3&&cp<65536)||cp>0x10ffff||(cp>=0xd800&&cp<=0xdfff)||!cp)return false;
    if(name&&(cp<32||(cp>=127&&cp<=159)||cp=='/'||cp=='\\'))return false;
  }return true;
}
std::string string_arg(const char *p,size_t max,bool name){need(p,RFL_ARGUMENT,"null string");size_t n=0;while(n<=max&&p[n])++n;need(n&&n<=max,RFL_LIMIT,"string length");std::string s(p,n);need(utf8(s,name),RFL_ENCODING,"invalid UTF-8/display name");return s;}
bool hash_valid(const std::string&s){return s.size()==64&&s.find_first_not_of("0123456789abcdef")==std::string::npos;}
std::string hash_arg(const char *p){auto s=string_arg(p,64,false);need(hash_valid(s),RFL_ARGUMENT,"invalid content hash");return s;}
fs::path path_arg(const char *p){auto s=string_arg(p,4096,false);auto path=fs::u8path(s);need(path.is_absolute()&&path==path.lexically_normal(),RFL_ARGUMENT,"absolute normalized path required");
#ifdef _WIN32
  need(s.find('?')==std::string::npos&&s.find(':',2)==std::string::npos,RFL_ARGUMENT,"device/stream paths unsupported");
#endif
  return path;
}
struct file {
#ifdef _WIN32
  HANDLE h=INVALID_HANDLE_VALUE;
  file()=default;explicit file(HANDLE v):h(v){};bool valid()const{return h!=INVALID_HANDLE_VALUE;}
  void close(){if(valid())CloseHandle(h);h=INVALID_HANDLE_VALUE;}
#else
  int h=-1;
  file()=default;explicit file(int v):h(v){};bool valid()const{return h>=0;}
  void close(){if(valid())::close(h);h=-1;}
#endif
  ~file(){close();}file(const file&)=delete;file&operator=(const file&)=delete;
  file(file&&o)noexcept:h(o.h){
#ifdef _WIN32
    o.h=INVALID_HANDLE_VALUE;
#else
    o.h=-1;
#endif
  }
  file&operator=(file&&o)noexcept{close();std::swap(h,o.h);return *this;}
};
struct fingerprint { uint64_t size,a,b,c,d; bool operator==(const fingerprint&o)const{return size==o.size&&a==o.a&&b==o.b&&c==o.c&&d==o.d;} };
fingerprint stat_file(file&f,bool directory=false){
#ifdef _WIN32
  BY_HANDLE_FILE_INFORMATION s{};need(GetFileInformationByHandle(f.h,&s)!=0,RFL_IO,"stat file");
  need(!(s.dwFileAttributes&FILE_ATTRIBUTE_REPARSE_POINT)&&bool(s.dwFileAttributes&FILE_ATTRIBUTE_DIRECTORY)==directory&&GetFileType(f.h)==FILE_TYPE_DISK,RFL_ARGUMENT,"not ordinary file/directory or reparse point");
  return {(uint64_t(s.nFileSizeHigh)<<32)|s.nFileSizeLow,s.dwVolumeSerialNumber,(uint64_t(s.nFileIndexHigh)<<32)|s.nFileIndexLow,(uint64_t(s.ftLastWriteTime.dwHighDateTime)<<32)|s.ftLastWriteTime.dwLowDateTime,s.nNumberOfLinks};
#else
  struct stat s{};need(fstat(f.h,&s)==0,RFL_IO,"stat file");need(directory?S_ISDIR(s.st_mode):S_ISREG(s.st_mode),RFL_ARGUMENT,"not ordinary file/directory");
#ifdef __APPLE__
  return {uint64_t(s.st_size),uint64_t(s.st_dev),uint64_t(s.st_ino),uint64_t(s.st_mtimespec.tv_sec)*1000000000+uint64_t(s.st_mtimespec.tv_nsec),uint64_t(s.st_ctimespec.tv_sec)*1000000000+uint64_t(s.st_ctimespec.tv_nsec)};
#else
  return {uint64_t(s.st_size),uint64_t(s.st_dev),uint64_t(s.st_ino),uint64_t(s.st_mtim.tv_sec)*1000000000+uint64_t(s.st_mtim.tv_nsec),uint64_t(s.st_ctim.tv_sec)*1000000000+uint64_t(s.st_ctim.tv_nsec)};
#endif
#endif
}
file absolute_open(const fs::path&p,bool directory){
#ifdef _WIN32
  fs::path prefix=p.root_path();std::vector<file> parents;
  auto relative=p.relative_path();size_t index=0,total=size_t(std::distance(relative.begin(),relative.end()));
  for(const auto &part:relative){prefix/=part;bool dir=++index<total||directory;
    file f(CreateFileW(prefix.c_str(),GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,nullptr,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT|(dir?FILE_FLAG_BACKUP_SEMANTICS:0),nullptr));
    need(f.valid(),GetLastError()==ERROR_FILE_NOT_FOUND?RFL_MISSING:RFL_IO,"open selected path");stat_file(f,dir);parents.push_back(std::move(f));
  }need(!parents.empty(),RFL_ARGUMENT,"root directory unsupported");return std::move(parents.back());
#else
#ifdef __ANDROID__
  constexpr int traversal_access=O_PATH;
#else
  constexpr int traversal_access=O_RDONLY;
#endif
  file current(::open("/",traversal_access|O_DIRECTORY|O_CLOEXEC));need(current.valid(),RFL_IO,"open root");
  auto relative=p.relative_path();size_t index=0,total=size_t(std::distance(relative.begin(),relative.end()));
  for(const auto &part:relative){bool intermediate=++index<total;bool dir=intermediate||directory;int access=intermediate?traversal_access:O_RDONLY;file next(openat(current.h,part.c_str(),access|O_CLOEXEC|O_NOFOLLOW|O_NONBLOCK|(dir?O_DIRECTORY:0)));need(next.valid(),errno==ENOENT?RFL_MISSING:RFL_IO,"open nofollow selected path");stat_file(next,dir);current=std::move(next);}return current;
#endif
}
size_t read_at(file&f,uint64_t offset,void *buffer,size_t capacity){
#ifdef _WIN32
  LARGE_INTEGER position{};position.QuadPart=static_cast<LONGLONG>(offset);need(SetFilePointerEx(f.h,position,nullptr,FILE_BEGIN)!=0,RFL_IO,"seek");DWORD got=0;need(ReadFile(f.h,buffer,static_cast<DWORD>(capacity),&got,nullptr)!=0,RFL_IO,"read");return got;
#else
  ssize_t got;do{got=pread(f.h,buffer,capacity,static_cast<off_t>(offset));}while(got<0&&errno==EINTR);need(got>=0,RFL_IO,"read");return size_t(got);
#endif
}
void write_all(file&f,const void *data,size_t size){auto p=static_cast<const unsigned char*>(data);while(size){
#ifdef _WIN32
  DWORD n=0;need(WriteFile(f.h,p,static_cast<DWORD>(size),&n,nullptr)!=0&&n,RFL_IO,"write (disk full or access denied)");
#else
  ssize_t n;do{n=::write(f.h,p,size);}while(n<0&&errno==EINTR);need(n>0,RFL_IO,"write (disk full or access denied)");
#endif
  p+=n;size-=size_t(n);
}}
void flush(file&f){
#ifdef _WIN32
  need(FlushFileBuffers(f.h)!=0,RFL_IO,"flush file");
#else
  need(fsync(f.h)==0,RFL_IO,"flush file");
#endif
}
struct mapping {const void *bytes=nullptr;size_t size=0;
#ifdef _WIN32
  HANDLE section=nullptr;
#endif
  explicit mapping(file&f){auto s=stat_file(f);need(s.size&&s.size<=64ull*1024*1024,RFL_LIMIT,"mapping bound");size=size_t(s.size);
#ifdef _WIN32
    section=CreateFileMappingW(f.h,nullptr,PAGE_READONLY,0,0,nullptr);need(section!=nullptr,RFL_IO,"map section");bytes=MapViewOfFile(section,FILE_MAP_READ,0,0,0);if(!bytes){CloseHandle(section);section=nullptr;throw failure{RFL_IO,"map view"};}
#else
    bytes=mmap(nullptr,size,PROT_READ,MAP_PRIVATE,f.h,0);need(bytes!=MAP_FAILED,RFL_IO,"map font");
#endif
  }
  ~mapping(){
#ifdef _WIN32
    if(bytes)UnmapViewOfFile(bytes);if(section)CloseHandle(section);
#else
    if(bytes&&bytes!=MAP_FAILED)munmap(const_cast<void*>(bytes),size);
#endif
  }
};
using font_ptr=std::unique_ptr<exr_font,decltype(&exr_font_free)>;
font_ptr sdk_open(file&f,unsigned face){mapping m(f);exr_font_input input{m.bytes,m.size,face};exr_font *out=nullptr;exr_error e{};auto status=exr_font_create(&input,1,&out,&e);need(status==EXR_OK,RFL_FONT,"frozen SDK rejected selected font/face");return font_ptr(out,&exr_font_free);}
std::string digest(file&f){auto before=stat_file(f);need(before.size<=64ull*1024*1024,RFL_LIMIT,"hash bound");std::array<unsigned char,65536> b{};sha256 hash;uint64_t at=0;while(at<before.size){size_t n=read_at(f,at,b.data(),size_t(std::min<uint64_t>(b.size(),before.size-at)));need(n,RFL_CHANGED,"font truncated");hash.add(b.data(),n);at+=n;}need(read_at(f,at,b.data(),1)==0&&before==stat_file(f),RFL_CHANGED,"font changed");return hash.finish();}
std::string hex(const std::string&s){static const char c[]="0123456789abcdef";std::string out;for(unsigned char x:s){out+=c[x>>4];out+=c[x&15];}return out;}
std::string unhex(const std::string&s){need(!(s.size()%2)&&s.size()<=510,RFL_CORRUPT,"manifest name length");std::string out;for(size_t i=0;i<s.size();i+=2){auto a=std::string("0123456789abcdef").find(s[i]),b=std::string("0123456789abcdef").find(s[i+1]);need(a<16&&b<16,RFL_CORRUPT,"manifest name hex");out+=char(a*16+b);}need(!out.empty()&&utf8(out,true),RFL_CORRUPT,"manifest name UTF-8");return out;}
rfl_record record(const std::string&hash,const std::string&name,uint64_t size){rfl_record r{};std::memcpy(r.hash,hash.c_str(),hash.size()+1);std::memcpy(r.display_name,name.c_str(),name.size()+1);r.bytes=size;return r;}
}
struct rfl_library {
  fs::path path;file directory,lock;rfl_limits limits{};std::map<std::string,rfl_record> records;std::map<std::string,size_t> leases;
  std::thread::id owner=std::this_thread::get_id();bool busy=false,poisoned=false;size_t live_count=0;uint64_t live_bytes=0;
};
struct rfl_lease {rfl_library *owner;std::string hash;font_ptr font;};
namespace {
file child(rfl_library&l,const std::string&name,bool create=false){
#ifdef _WIN32
  file f(CreateFileW((l.path/fs::u8path(name)).c_str(),create?(GENERIC_READ|GENERIC_WRITE):GENERIC_READ,FILE_SHARE_READ,nullptr,create?CREATE_NEW:OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,nullptr));
  need(f.valid(),GetLastError()==ERROR_FILE_NOT_FOUND?RFL_MISSING:RFL_IO,"open managed file");
#else
  file f(openat(l.directory.h,name.c_str(),(create?O_RDWR|O_CREAT|O_EXCL:O_RDONLY)|O_CLOEXEC|O_NOFOLLOW|O_NONBLOCK,0600));need(f.valid(),errno==ENOENT?RFL_MISSING:RFL_IO,"open managed file");
#endif
  stat_file(f);return f;
}
bool exists(rfl_library&l,const std::string&name){
#ifdef _WIN32
  auto a=GetFileAttributesW((l.path/fs::u8path(name)).c_str());if(a!=INVALID_FILE_ATTRIBUTES)return true;need(GetLastError()==ERROR_FILE_NOT_FOUND,RFL_IO,"managed file attributes");return false;
#else
  struct stat s{};if(fstatat(l.directory.h,name.c_str(),&s,AT_SYMLINK_NOFOLLOW)==0)return true;need(errno==ENOENT,RFL_IO,"managed file attributes");return false;
#endif
}
void unlink_child(rfl_library&l,const std::string&name){if(!exists(l,name))return;{auto f=child(l,name);}
#ifdef _WIN32
  need(DeleteFileW((l.path/fs::u8path(name)).c_str())!=0,RFL_IO,"unlink managed file");
#else
  need(unlinkat(l.directory.h,name.c_str(),0)==0,RFL_IO,"unlink managed file");
#endif
}
void directory_sync(rfl_library&l){
#ifdef _WIN32
  (void)l; // file flush + same-volume MoveFileEx WRITE_THROUGH; power-loss durability not promised
#else
  need(fsync(l.directory.h)==0,RFL_IO,"sync directory");
#endif
}
void rename_child(rfl_library&l,const std::string&from,const std::string&to,bool replace){
#ifdef _WIN32
  need(MoveFileExW((l.path/fs::u8path(from)).c_str(),(l.path/fs::u8path(to)).c_str(),MOVEFILE_WRITE_THROUGH|(replace?MOVEFILE_REPLACE_EXISTING:0))!=0,RFL_IO,"atomic rename");
#else
  if(replace)need(renameat(l.directory.h,from.c_str(),l.directory.h,to.c_str())==0,RFL_IO,"atomic manifest rename");
  else{
#ifdef __ANDROID__
    need(syscall(__NR_renameat2,l.directory.h,from.c_str(),l.directory.h,to.c_str(),RENAME_NOREPLACE)==0,RFL_IO,"exclusive font rename");
#else
    need(linkat(l.directory.h,from.c_str(),l.directory.h,to.c_str(),0)==0,RFL_IO,"exclusive font publish");need(unlinkat(l.directory.h,from.c_str(),0)==0,RFL_IO,"unlink published temporary");
#endif
  }
#endif
}
std::string encode(const std::map<std::string,rfl_record>&records){std::string out="RFL1\n";for(const auto&p:records)out+=p.first+" "+std::to_string(p.second.bytes)+" "+hex(p.second.display_name)+"\n";return out;}
void commit(rfl_library&l,const std::map<std::string,rfl_record>&records){
  auto text=encode(records);unlink_child(l,".rfl-tmp-manifest");{auto f=child(l,".rfl-tmp-manifest",true);write_all(f,text.data(),text.size());flush(f);}
  rename_child(l,".rfl-tmp-manifest","manifest.rfl",true);
  try{directory_sync(l);}catch(...){l.poisoned=true;throw failure{RFL_COMMIT_UNCERTAIN,"manifest published but directory durability uncertain; reopen"};}
}
void load(rfl_library&l){
  // Dedicated namespace: bound enumeration even for an externally damaged
  // directory, and never adopt/delete unrelated original user files.
  size_t inventory=0;
  for(const auto&e:fs::directory_iterator(l.path)){
    need(++inventory<=261,RFL_LIMIT,"private-directory entry limit");auto n=e.path().filename().u8string();
    bool managed=n.size()==69&&n.substr(64)==".font"&&hash_valid(n.substr(0,64));
    need(managed||n==".rfl-lock"||n=="manifest.rfl"||n==".rfl-initialized"||n==".rfl-tmp-font"||n==".rfl-tmp-manifest",RFL_CORRUPT,"unrelated entry in dedicated private directory");
  }
  if(!exists(l,"manifest.rfl")){need(!exists(l,".rfl-initialized"),RFL_MISSING,"manifest missing from initialized directory");
    for(const auto&e:fs::directory_iterator(l.path)){auto n=e.path().filename().u8string();need(!(n.size()==69&&n.substr(64)==".font"),RFL_MISSING,"manifest missing with managed fonts");}commit(l,{});
  }
  auto f=child(l,"manifest.rfl");auto st=stat_file(f);need(st.size<=160*1024,RFL_CORRUPT,"manifest too large");std::string s(size_t(st.size),'\0');size_t at=0;while(at<s.size()){size_t n=read_at(f,at,&s[at],s.size()-at);need(n,RFL_CORRUPT,"manifest truncated");at+=n;}
  need(s.rfind("RFL",0)==0,RFL_CORRUPT,"manifest magic");need(s.rfind("RFL1\n",0)==0,RFL_MANIFEST_VERSION,"unknown manifest version");
  size_t pos=5;uint64_t total=0;std::string last;
  while(pos<s.size()){auto end=s.find('\n',pos);need(end!=std::string::npos,RFL_CORRUPT,"manifest incomplete record");auto line=s.substr(pos,end-pos);auto a=line.find(' '),b=line.find(' ',a==std::string::npos?0:a+1);need(a==64&&b!=std::string::npos,RFL_CORRUPT,"manifest fields");auto hash=line.substr(0,a),number=line.substr(a+1,b-a-1);need(hash_valid(hash)&&hash>last&&!number.empty()&&number.size()<10&&number.find_first_not_of("0123456789")==std::string::npos,RFL_CORRUPT,"manifest identity/size/order");uint64_t size=std::stoull(number);need(std::to_string(size)==number&&size&&size<=64ull*1024*1024,RFL_CORRUPT,"manifest size limit");need(size<=l.limits.font_bytes,RFL_LIMIT,"stored font exceeds configured limit");auto name=unhex(line.substr(b+1));l.records.emplace(hash,record(hash,name,size));total+=size;need(l.records.size()<=l.limits.entries&&total<=l.limits.directory_bytes,RFL_LIMIT,"stored fonts exceed configured budget");last=hash;pos=end+1;}
  for(const auto&p:l.records){auto font=child(l,p.first+".font");need(stat_file(font).size==p.second.bytes&&digest(font)==p.first,RFL_CORRUPT,"stored font identity changed");auto validated=sdk_open(font,0);}
  if(!exists(l,".rfl-initialized")){auto marker=child(l,".rfl-initialized",true);write_all(marker,"RFL1\n",5);flush(marker);directory_sync(l);}
  else{auto marker=child(l,".rfl-initialized");char signature[5]{};need(stat_file(marker).size==5&&read_at(marker,0,signature,5)==5&&std::memcmp(signature,"RFL1\n",5)==0,RFL_CORRUPT,"initialization marker");}
  unlink_child(l,".rfl-tmp-font");unlink_child(l,".rfl-tmp-manifest");
  for(const auto&e:fs::directory_iterator(l.path)){auto n=e.path().filename().u8string();if(n.size()==69&&n.substr(64)==".font"&&hash_valid(n.substr(0,64))&&!l.records.count(n.substr(0,64))){auto orphan=child(l,n);need(digest(orphan)==n.substr(0,64),RFL_CORRUPT,"unreferenced file does not match managed hash");orphan.close();unlink_child(l,n);}}
  directory_sync(l);
}
struct operation {rfl_library&l;explicit operation(rfl_library*p,bool allow_poison=false):l(*checked(p)){need(l.owner==std::this_thread::get_id(),RFL_THREAD,"wrong owner thread");need(!l.busy,RFL_BUSY,"callback reentry");need(allow_poison||!l.poisoned,RFL_COMMIT_UNCERTAIN,"reopen after uncertain commit");l.busy=true;}static rfl_library*checked(rfl_library*p){need(p,RFL_ARGUMENT,"null library");return p;}~operation(){l.busy=false;}};
template<typename F>rfl_status boundary(rfl_error *e,F fn)noexcept{if(e)*e={};try{fn();return RFL_OK;}catch(const failure&x){if(e){e->code=x.code;std::snprintf(e->message,sizeof(e->message),"%s",x.message);}return x.code;}catch(const std::bad_alloc&){if(e){e->code=RFL_MEMORY;std::snprintf(e->message,sizeof(e->message),"allocation failed");}return RFL_MEMORY;}catch(...){if(e){e->code=RFL_IO;std::snprintf(e->message,sizeof(e->message),"native operation or callback exception");}return RFL_IO;}}
void poll(const rfl_control*c,const char*stage,uint64_t done,uint64_t total,bool can_cancel=true){if(c&&c->progress){int stop=c->progress(c->context,stage,done,total);need(!stop||!can_cancel,RFL_CANCELLED,"cancelled before commit");}}
void import(rfl_library&l,const rfl_source&s,const std::string&name,const rfl_control*c,rfl_record*out,int*created){
  need(s.read&&s.bytes,RFL_ARGUMENT,"empty source");need(s.bytes<=l.limits.font_bytes,RFL_LIMIT,"font byte limit");
  uint64_t current=0;for(const auto&p:l.records)current+=p.second.bytes;
  // A full directory can still deduplicate, without allocating an over-budget
  // temporary font. Two bounded passes authenticate the immutable source first.
  if(l.records.size()>=l.limits.entries||current+s.bytes>l.limits.directory_bytes){
    std::array<unsigned char,65536> scratch{};std::string previous;
    for(unsigned pass=0;pass<2;++pass){sha256 h;uint64_t at=0;while(at<s.bytes){poll(c,"verify",at,s.bytes);size_t cap=size_t(std::min<uint64_t>(scratch.size(),s.bytes-at)),n=0;auto st=s.read(s.context,at,scratch.data(),cap,&n);need(st==RFL_OK,st,"source quota preflight read");need(n&&n<=cap,RFL_CHANGED,"source quota preflight length");h.add(scratch.data(),n);at+=n;}size_t extra=0;auto st=s.read(s.context,s.bytes,scratch.data(),1,&extra);need(st==RFL_OK,st,"source quota preflight EOF");need(!extra,RFL_CHANGED,"source length underreported");auto value=h.finish();if(pass)need(value==previous,RFL_CHANGED,"source changed between quota preflight passes");previous=value;}
    auto found=l.records.find(previous);need(found!=l.records.end(),RFL_LIMIT,"directory font budget");auto existing=child(l,previous+".font");need(digest(existing)==previous,RFL_CORRUPT,"existing duplicate changed");auto validated=sdk_open(existing,0);poll(c,"validated",s.bytes,s.bytes);*out=found->second;*created=0;return;
  }
  unlink_child(l,".rfl-tmp-font");struct cleanup{rfl_library&l;~cleanup(){try{unlink_child(l,".rfl-tmp-font");unlink_child(l,".rfl-tmp-manifest");}catch(...){}}} cleanup{l};
  sha256 first;std::array<unsigned char,65536>b{};
  {auto temp=child(l,".rfl-tmp-font",true);uint64_t offset=0;
    while(offset<s.bytes){poll(c,"copy",offset,s.bytes);size_t capacity=size_t(std::min<uint64_t>(b.size(),s.bytes-offset)),n=0;auto status=s.read(s.context,offset,b.data(),capacity,&n);need(status==RFL_OK,status,"source read failed");need(n&&n<=capacity,RFL_CHANGED,"source truncated or invalid read length");write_all(temp,b.data(),n);first.add(b.data(),n);offset+=n;}
    size_t extra=0;auto status=s.read(s.context,s.bytes,b.data(),1,&extra);need(status==RFL_OK,status,"source EOF read failed");need(extra==0,RFL_CHANGED,"source length underreported");flush(temp);
  }
  auto hash=first.finish();sha256 second;uint64_t offset=0;
  while(offset<s.bytes){poll(c,"verify",offset,s.bytes);size_t cap=size_t(std::min<uint64_t>(b.size(),s.bytes-offset)),n=0;auto status=s.read(s.context,offset,b.data(),cap,&n);need(status==RFL_OK,status,"source reread failed");need(n&&n<=cap,RFL_CHANGED,"source reread truncated");second.add(b.data(),n);offset+=n;}
  size_t extra=0;auto status=s.read(s.context,s.bytes,b.data(),1,&extra);need(status==RFL_OK,status,"source EOF reread failed");need(!extra&&second.finish()==hash,RFL_CHANGED,"source changed between passes");
  {auto temp=child(l,".rfl-tmp-font");need(stat_file(temp).size==s.bytes&&digest(temp)==hash,RFL_CHANGED,"copied bytes changed");auto validated=sdk_open(temp,0);}
  poll(c,"validated",s.bytes,s.bytes);
  auto found=l.records.find(hash);if(found!=l.records.end()){auto previous=child(l,hash+".font");need(digest(previous)==hash,RFL_CORRUPT,"existing duplicate changed");*out=found->second;*created=0;return;}
  uint64_t total=s.bytes;for(const auto&p:l.records)total+=p.second.bytes;need(l.records.size()<l.limits.entries&&total<=l.limits.directory_bytes,RFL_LIMIT,"directory font budget");
  auto next=l.records;auto r=record(hash,name,s.bytes);next.emplace(hash,r);bool published=false;
  try{need(!exists(l,hash+".font"),RFL_CORRUPT,"content path conflict; reopen to recover");rename_child(l,".rfl-tmp-font",hash+".font",false);published=true;directory_sync(l);poll(c,"file-published",s.bytes,s.bytes);commit(l,next);}
  catch(...){if(published&&!l.poisoned){try{unlink_child(l,hash+".font");directory_sync(l);}catch(...){l.poisoned=true;throw failure{RFL_COMMIT_UNCERTAIN,"precommit rollback cleanup failed; reopen"};}}throw;}
  l.records.swap(next);*out=r;*created=1;
  // Observation after commit cannot turn a successful durable commit into failure.
  try{poll(c,"committed",s.bytes,s.bytes,false);}catch(...){}
}
struct file_source {file *f;fingerprint original;};
rfl_status file_read(void*context,uint64_t offset,void*b,size_t cap,size_t*n){return boundary(nullptr,[&]{auto &s=*static_cast<file_source*>(context);need(stat_file(*s.f)==s.original,RFL_CHANGED,"selected file changed after open");*n=read_at(*s.f,offset,b,cap);need(stat_file(*s.f)==s.original,RFL_CHANGED,"selected file changed while reading");});}
}
extern "C" {
rfl_limits rfl_limits_default(void){return {16ull*1024*1024,128ull*1024*1024,64};}
rfl_status rfl_open(const char*directory,const rfl_limits*limits,rfl_library**out,rfl_error*e){if(out)*out=nullptr;return boundary(e,[&]{need(out,RFL_ARGUMENT,"null output");auto l=std::make_unique<rfl_library>();l->path=path_arg(directory);l->limits=limits?*limits:rfl_limits_default();need(l->limits.font_bytes&&l->limits.font_bytes<=64ull*1024*1024&&l->limits.directory_bytes&&l->limits.directory_bytes<=512ull*1024*1024&&l->limits.entries&&l->limits.entries<=256,RFL_LIMIT,"invalid hard limits");l->directory=absolute_open(l->path,true);
#ifdef _WIN32
  l->lock=file(CreateFileW((l->path/L".rfl-lock").c_str(),GENERIC_READ|GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_WRITE,nullptr,OPEN_ALWAYS,FILE_FLAG_OPEN_REPARSE_POINT,nullptr));need(l->lock.valid(),RFL_IO,"open directory lock");stat_file(l->lock);OVERLAPPED ov{};need(LockFileEx(l->lock.h,LOCKFILE_EXCLUSIVE_LOCK|LOCKFILE_FAIL_IMMEDIATELY,0,1,0,&ov)!=0,RFL_BUSY,"directory already locked");
#else
  l->lock=file(openat(l->directory.h,".rfl-lock",O_RDWR|O_CREAT|O_CLOEXEC|O_NOFOLLOW|O_NONBLOCK,0600));need(l->lock.valid(),RFL_IO,"open directory lock");stat_file(l->lock);need(flock(l->lock.h,LOCK_EX|LOCK_NB)==0,RFL_BUSY,"directory already locked");
#endif
  load(*l);*out=l.release();});}
rfl_status rfl_close(rfl_library*l,rfl_error*e){return boundary(e,[&]{{operation op(l,true);need(l->leases.empty(),RFL_BUSY,"font leases active");}delete l;});}
rfl_status rfl_import_file(rfl_library*l,const char*path,const char*name,const rfl_control*c,rfl_record*out,int*created,rfl_error*e){if(out)*out={};if(created)*created=0;return boundary(e,[&]{operation op(l);need(out&&created,RFL_ARGUMENT,"null outputs");auto label=string_arg(name,255,true);auto f=absolute_open(path_arg(path),false);file_source source{&f,stat_file(f)};rfl_source s{source.original.size,file_read,&source};import(*l,s,label,c,out,created);});}
rfl_status rfl_import_source(rfl_library*l,const rfl_source*s,const char*name,const rfl_control*c,rfl_record*out,int*created,rfl_error*e){if(out)*out={};if(created)*created=0;return boundary(e,[&]{operation op(l);need(s&&out&&created,RFL_ARGUMENT,"null arguments");auto label=string_arg(name,255,true);const rfl_source snapshot=*s;import(*l,snapshot,label,c,out,created);});}
rfl_status rfl_count(rfl_library*l,size_t*out,rfl_error*e){if(out)*out=0;return boundary(e,[&]{operation op(l);need(out,RFL_ARGUMENT,"null count");*out=l->records.size();});}
rfl_status rfl_get(rfl_library*l,size_t index,rfl_record*out,rfl_error*e){if(out)*out={};return boundary(e,[&]{operation op(l);need(out,RFL_ARGUMENT,"null record");need(index<l->records.size(),RFL_NOT_FOUND,"index absent");auto it=l->records.begin();std::advance(it,index);*out=it->second;});}
rfl_status rfl_find(rfl_library*l,const char*hash,rfl_record*out,rfl_error*e){if(out)*out={};return boundary(e,[&]{operation op(l);need(out,RFL_ARGUMENT,"null record");auto h=hash_arg(hash);auto it=l->records.find(h);need(it!=l->records.end(),RFL_NOT_FOUND,"hash absent");*out=it->second;});}
rfl_status rfl_font_open(rfl_library*l,const char*hash,unsigned face,rfl_lease**out,rfl_error*e){if(out)*out=nullptr;return boundary(e,[&]{operation op(l);need(out,RFL_ARGUMENT,"null lease output");need(face<=65535,RFL_UNSUPPORTED,"named-instance encoding unsupported");auto h=hash_arg(hash);auto it=l->records.find(h);need(it!=l->records.end(),RFL_NOT_FOUND,"hash absent");need(l->live_count<32&&l->live_bytes+it->second.bytes<=128ull*1024*1024,RFL_LIMIT,"live lease budget");auto f=child(*l,h+".font");need(stat_file(f).size==it->second.bytes&&digest(f)==h,RFL_CORRUPT,"stored font changed");auto font=sdk_open(f,face);auto lease=std::make_unique<rfl_lease>(rfl_lease{l,h,std::move(font)});++l->leases[h];++l->live_count;l->live_bytes+=it->second.bytes;*out=lease.release();});}
rfl_status rfl_lease_font(rfl_lease*lease,exr_font**out,rfl_error*e){if(out)*out=nullptr;return boundary(e,[&]{need(lease&&out,RFL_ARGUMENT,"null lease/output");operation op(lease->owner);*out=lease->font.get();});}
rfl_status rfl_lease_release(rfl_lease*lease,rfl_error*e){return boundary(e,[&]{need(lease,RFL_ARGUMENT,"null lease");operation op(lease->owner,true);auto &m=lease->owner->leases;auto it=m.find(lease->hash);need(it!=m.end()&&it->second,RFL_CORRUPT,"lease accounting");if(!--it->second)m.erase(it);--lease->owner->live_count;lease->owner->live_bytes-=lease->owner->records.at(lease->hash).bytes;delete lease;});}
rfl_status rfl_remove(rfl_library*l,const char*hash,rfl_error*e){return boundary(e,[&]{operation op(l);auto h=hash_arg(hash);need(l->records.count(h),RFL_NOT_FOUND,"hash absent");need(!l->leases.count(h),RFL_BUSY,"font is leased");auto next=l->records;next.erase(h);commit(*l,next);l->records.swap(next);try{unlink_child(*l,h+".font");directory_sync(*l);}catch(...){l->poisoned=true;throw failure{RFL_COMMIT_UNCERTAIN,"removal committed; cleanup uncertain; reopen"};}});}
}
