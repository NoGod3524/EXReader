/* SPDX-License-Identifier: MIT */
#ifndef _WIN32
#define _FILE_OFFSET_BITS 64
#endif
#include "original_import.h"
#include <algorithm>
#include <cerrno>
#include <cstring>
#include <string>
#include <vector>
#include <cstdio>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#else
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#ifdef __ANDROID__
#include <linux/fs.h>
#include <sys/syscall.h>
#endif
#endif
namespace {
struct failure { reader_original_status status; };
void need(bool ok, reader_original_status s) { if(!ok) throw failure{s}; }
#include "../original-export/src/sha256.inc"
void digest(Sha256 &s,char out[65]) { static const char h[]="0123456789abcdef"; unsigned char b[32]; s.finish(b); for(size_t i=0;i<32;i++){out[i*2]=h[b[i]>>4];out[i*2+1]=h[b[i]&15];}out[64]=0; }
std::string bounded(const char *p,size_t max) { need(p!=nullptr,ROI_ARGUMENT); size_t n=0; while(n<=max&&p[n])++n; need(n&&n<=max,ROI_ARGUMENT); return std::string(p,n); }
bool reserved(std::string s) {
  for(char &c:s)if(c>='a'&&c<='z')c=static_cast<char>(c-'a'+'A');
  return s=="CON"||s=="PRN"||s=="AUX"||s=="NUL"||s=="CLOCK$"||
    (s.size()==4&&(s.substr(0,3)=="COM"||s.substr(0,3)=="LPT")&&s[3]>='0'&&s[3]<='9');
}
#ifdef _WIN32
std::wstring wide(const std::string &s) {
  int n=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,s.c_str(),-1,nullptr,0);need(n>0,ROI_ARGUMENT);
  std::wstring r(static_cast<size_t>(n),L'\0');need(MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,s.c_str(),-1,&r[0],n)==n,ROI_ARGUMENT);r.resize(static_cast<size_t>(n-1));return r;
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
    need(path.size()>3&&((path[0]>='A'&&path[0]<='Z')||(path[0]>='a'&&path[0]<='z'))&&path[1]==':'&&path[2]=='/',ROI_ARGUMENT);
    size_t start=3;
#else
    need(path[0]=='/'&&path.size()>1,ROI_ARGUMENT);size_t start=1;
#ifdef __ANDROID__
    constexpr int traversal_access=O_PATH;
#else
    constexpr int traversal_access=O_RDONLY;
#endif
    fd=::open("/",traversal_access|O_DIRECTORY|O_CLOEXEC);need(fd!=invalid,ROI_IO);
#endif
    need(path.back()!='/',ROI_ARGUMENT);
    for(size_t pos=start;pos<=path.size();) {
      size_t end=path.find('/',pos);if(end==std::string::npos)end=path.size();std::string part=path.substr(pos,end-pos);
      need(!part.empty()&&part!="."&&part!=".."&&part.back()!='.'&&part.back()!=' '&&!reserved(part),ROI_ARGUMENT);
      need(part.find_first_of(":\\*?\"<>|")==std::string::npos,ROI_ARGUMENT);
#ifdef _WIN32
      std::wstring w=wide(path.substr(0,end));
      file h=CreateFileW(w.c_str(),FILE_READ_ATTRIBUTES,FILE_SHARE_READ|FILE_SHARE_WRITE,nullptr,OPEN_EXISTING,FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
      need(h!=invalid,ROI_IO);BY_HANDLE_FILE_INFORMATION i{};
      if(!GetFileInformationByHandle(h,&i)||(i.dwFileAttributes&FILE_ATTRIBUTE_REPARSE_POINT)||!(i.dwFileAttributes&FILE_ATTRIBUTE_DIRECTORY)){closefile(h);throw failure{ROI_ARGUMENT};}
      try{held.push_back(h);}catch(...){closefile(h);throw;}
#else
      int access=end==path.size()?O_RDONLY:traversal_access;
      file next=openat(fd,part.c_str(),access|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);need(next!=invalid,ROI_ARGUMENT);closefile(fd);fd=next;
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
#elif defined(__ANDROID__)
    return syscall(__NR_renameat2,fd,tmp.c_str(),fd,dst.c_str(),RENAME_NOREPLACE)==0;
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
struct row { std::string key, ref, state; };
int capture(void *p,const reader_catalog_original_row *r) { auto *v=static_cast<std::vector<row> *>(p); v->push_back({r->book_key,r->storage_ref,r->state}); return 0; }
struct meta { uint64_t bytes=0; };
int capture_meta(void *p,const reader_catalog_row *r) { static_cast<meta *>(p)->bytes=r->source_bytes; return 0; }
bool valid_key(const std::string &k) { if(k.size()!=68||k.compare(0,4,"txt:")) return false; for(size_t i=4;i<k.size();++i) if(!((k[i]>='0'&&k[i]<='9')||(k[i]>='a'&&k[i]<='f'))) return false; return true; }
std::string leaf(const std::string &k) { return k.substr(4)+".txt"; }
std::string temp(const std::string &k) { return "."+k.substr(4)+".tmp"; }
bool absent_remove(directory &d,const std::string &name) {
  if(d.remove(name)) return true;
#ifdef _WIN32
  return GetLastError()==ERROR_FILE_NOT_FOUND;
#else
  return errno==ENOENT;
#endif
}
bool verify(directory &d,const std::string &name,const std::string &k,uint64_t expected=0) {
  handle h; h.f=d.existing(name); uint64_t n=0, after=0; char hash[65]; unsigned char buf[65536];
  return h.f!=invalid && regular(h.f,&n) && n>0 && (!expected||n==expected) && hashfile(h.f,n,hash,buf) && regular(h.f,&after) && n==after && k.substr(4)==hash;
}
void check_catalog(int status) { need(status==0,ROI_CATALOG); }
void notify(const reader_original_callbacks *c,int event) { if(c&&c->event)c->event(c->context,event); }
bool cancelled(const reader_original_callbacks *c) { return c&&c->cancelled&&c->cancelled(c->context); }
void reconcile(reader_catalog *c,directory &d,const row &r) {
  need(valid_key(r.key)&&r.ref==leaf(r.key),ROI_CORRUPT);
  reader_catalog_error e{};
  if(r.state=="ready") return;
  if(r.state=="staged") need(absent_remove(d,temp(r.key)) && d.sync(),ROI_IO);
  if(r.state=="staged" && verify(d,r.ref,r.key)) {
    check_catalog(reader_catalog_original_transition(c,r.key.c_str(),"staged","ready",&e)); return;
  }
  if(r.state=="staged") check_catalog(reader_catalog_original_transition(c,r.key.c_str(),"staged","deleting",&e));
  else need(r.state=="deleting",ROI_CORRUPT);
  need(absent_remove(d,temp(r.key)) && absent_remove(d,r.ref) && d.sync(),ROI_IO);
  check_catalog(reader_catalog_original_forget(c,r.key.c_str(),&e));
}
std::vector<row> find(reader_catalog *c,const std::string &key) {
  std::vector<row> v; int found=0; reader_catalog_error e{};
  check_catalog(reader_catalog_original_find(c,key.c_str(),capture,&v,&found,&e)); return v;
}
void verify_ready(reader_catalog *c,directory &d,const std::string &key) {
  need(valid_key(key),ROI_ARGUMENT); auto v=find(c,key);
  need(v.size()==1&&v[0].state=="ready"&&v[0].ref==leaf(key),ROI_CORRUPT);
  meta m; int found=0; reader_catalog_error e{};
  check_catalog(reader_catalog_metadata(c,key.c_str(),capture_meta,&m,&found,&e));
  need(found && m.bytes && verify(d,v[0].ref,key,m.bytes),ROI_CORRUPT);
}
}
extern "C" reader_original_status reader_original_recover(reader_catalog *c,const char *root) {
  if(!c||!root)return ROI_ARGUMENT;
  try { directory d; d.open(root); std::string cursor;
    for(;;) { std::vector<row> rows; reader_catalog_error e{};
      check_catalog(reader_catalog_original_page(c,cursor.empty()?nullptr:cursor.c_str(),200,capture,&rows,&e));
      if(rows.empty())break;
      for(const auto &r:rows) reconcile(c,d,r);
      cursor=rows.back().key;
    } return ROI_OK;
  } catch(const failure &f){return f.status;} catch(...){return ROI_MEMORY;}
}
extern "C" reader_original_status reader_original_verified_path(reader_catalog *c,const char *root,const char *key,char *path,size_t capacity) {
  if(!c||!root||!key||!path||!capacity)return ROI_ARGUMENT;
  path[0]=0;
  try { directory d; d.open(root); std::string k=bounded(key,68); verify_ready(c,d,k);
    std::string p=d.path+"/"+leaf(k); need(p.size()<capacity,ROI_ARGUMENT); std::memcpy(path,p.c_str(),p.size()+1); return ROI_OK;
  } catch(const failure &f){return f.status;} catch(...){return ROI_MEMORY;}
}
extern "C" reader_original_status reader_original_import(reader_catalog *c,const char *root,const char *source_dir,const char *source_name,const char *title,const char *author,const char *sort_title,const reader_original_callbacks *cb,char key[69]) {
  if(!c||!root||!source_dir||!source_name||!title||!author||!sort_title||!key)return ROI_ARGUMENT;
  key[0]=0;
  try { directory d,src; d.open(root); src.open(source_dir); std::string name=bounded(source_name,255);
    need(name!="."&&name!=".."&&name.find_first_of("/\\:*?\"<>|")==std::string::npos,ROI_ARGUMENT);
    handle input; input.f=src.existing(name); uint64_t size=0,after=0; need(input.f!=invalid&&regular(input.f,&size)&&size>0&&size<=INT64_MAX,ROI_IO);
    need(!cancelled(cb),ROI_CANCELLED); unsigned char buf[65536]; char hash[65];
    Sha256 source_hash; source_hash.init(); need(rewindfile(input.f),ROI_IO);
    uint64_t hashed=0; while(hashed<size) { need(!cancelled(cb),ROI_CANCELLED); size_t n=readfile(input.f,buf,static_cast<size_t>(std::min<uint64_t>(sizeof(buf),size-hashed))); need(n>0,ROI_IO); source_hash.update(buf,n); hashed+=n; }
    digest(source_hash,hash); need(regular(input.f,&after)&&after==size,ROI_IO);
    std::string k=std::string("txt:")+hash; std::memcpy(key,k.c_str(),69);
    auto existing=find(c,k); if(!existing.empty()) { need(existing[0].state=="ready",ROI_CATALOG); verify_ready(c,d,k); return ROI_DUPLICATE; }
    need(!cancelled(cb),ROI_CANCELLED);
    reader_catalog_book b{}; b.format="txt";b.sha256=hash;b.title=title;b.author=author;b.sort_title=sort_title;b.source_bytes=size;
    reader_catalog_error e{}; std::string dst=leaf(k),tmp=temp(k);
    check_catalog(reader_catalog_original_stage(c,&b,dst.c_str(),&e)); notify(cb,1);
    need(!cancelled(cb),ROI_CANCELLED);
    handle output; output.f=d.create(tmp); need(output.f!=invalid,ROI_IO); need(rewindfile(input.f),ROI_IO);
    uint64_t pos=0; while(pos<size) { need(!cancelled(cb),ROI_CANCELLED); size_t n=readfile(input.f,buf,static_cast<size_t>(std::min<uint64_t>(sizeof(buf),size-pos))); need(n&&writefile(output.f,buf,n),ROI_IO); pos+=n; notify(cb,2); }
    need(regular(input.f,&after)&&after==size,ROI_IO); need(flushfile(output.f),ROI_IO);
    char copied[65]; need(hashfile(output.f,size,copied,buf)&&std::strcmp(hash,copied)==0,ROI_CORRUPT);
    need(!cancelled(cb),ROI_CANCELLED); closefile(output.f);output.f=invalid;
    need(d.publish(tmp,dst),ROI_IO); notify(cb,3);
    need(absent_remove(d,tmp)&&d.sync(),ROI_IO);
    check_catalog(reader_catalog_original_transition(c,k.c_str(),"staged","ready",&e)); return ROI_OK;
  } catch(const failure &f){return f.status;} catch(...){return ROI_MEMORY;}
}
