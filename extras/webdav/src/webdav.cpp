/* SPDX-License-Identifier: MIT */
#include "exr_webdav.h"
#include <algorithm>
#include <chrono>
#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <memory>
#include <new>
#include <set>
#include <string>
#include <vector>
#include <filesystem>
#ifdef EXR_WEBDAV_APPLE_URLSESSION
#include "apple_transport.h"
#include <thread>
#endif
#ifdef __ANDROID__
#if __ANDROID_API__ < 26
#error "Android WebDAV requires API 26 or newer"
#endif
#include "exr_webdav_android.h"
#include <thread>
#include <mutex>
#include <map>
#include <sys/syscall.h>
#include <linux/fs.h>
#endif
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <winhttp.h>
#include <objbase.h>
#include <xmllite.h>
#include <shlwapi.h>
#else
#ifndef __ANDROID__
#ifndef EXR_WEBDAV_APPLE_URLSESSION
#include <curl/curl.h>
#include <pthread.h>
#include <signal.h>
#include <time.h>
#endif
#include <libxml/xmlreader.h>
#endif
#include <fcntl.h>
#include <unistd.h>
#include <sys/stat.h>
#include <cerrno>
#endif

namespace {
struct failure { exr_webdav_status code; const char *message; int http; };
[[noreturn]] void reject(exr_webdav_status code,const char *message,int http=0) { throw failure{code,message,http}; }
bool stop(const exr_webdav_control *c) { return c && c->cancelled && c->cancelled(c->context); }
void cancelled(const exr_webdav_control *c) { if(stop(c)) reject(EXR_DAV_CANCELLED,"Transfer cancelled"); }
bool utf8(const std::string &s) {
  for(size_t i=0;i<s.size();) {
    unsigned a=(unsigned char)s[i++],value=a;size_t n=0;
    if(a<128) { if(a<32 || a==127) return false;continue; }
    if(a>=0xc2 && a<=0xdf) { value=a&31;n=1; }
    else if(a>=0xe0 && a<=0xef) { value=a&15;n=2; }
    else if(a>=0xf0 && a<=0xf4) { value=a&7;n=3; }
    else return false;
    if(n>s.size()-i) return false;
    for(size_t j=0;j<n;j++) { unsigned b=(unsigned char)s[i++];if((b&0xc0)!=0x80) return false;value=(value<<6)|(b&63); }
    if((n==1 && value<128)||(n==2 && value<2048)||(n==3 && value<65536)||value>0x10ffff||(value>=0xd800&&value<=0xdfff)) return false;
  }
  return true;
}
int hex(char c) { return c>='0'&&c<='9' ? c-'0':c>='a'&&c<='f' ? c-'a'+10:c>='A'&&c<='F' ? c-'A'+10:-1; }
std::string path(const std::string &input,bool absolute) {
  if(input.size()>4096 || (!input.empty() && ((input[0]=='/')!=absolute)) || (absolute && input.empty()))
    reject(EXR_DAV_ARGUMENT,"Invalid resource path");
  std::string out,segment;
  auto finish=[&]() {
    if(segment=="." || segment==".." || !utf8(segment)) reject(EXR_DAV_ARGUMENT,"Ambiguous resource path");
    // A literal percent is valid; a second encoded escape remains ambiguous.
    for(size_t n=0;n+2<segment.size();n++)
      if(segment[n]=='%'&&hex(segment[n+1])>=0&&hex(segment[n+2])>=0)
        reject(EXR_DAV_ARGUMENT,"Doubly encoded resource segment");
    segment.clear();
  };
  for(size_t i=0;i<input.size();i++) {
    unsigned char ch=(unsigned char)input[i];
    if(ch=='/') {
      if(i && input[i-1]=='/') reject(EXR_DAV_ARGUMENT,"Empty resource segment");
      finish();out+='/';continue;
    }
    if(ch=='%') {
      if(i+2>=input.size() || hex(input[i+1])<0 || hex(input[i+2])<0) reject(EXR_DAV_ARGUMENT,"Invalid resource encoding");
      unsigned char decoded=(unsigned char)(hex(input[i+1])*16+hex(input[i+2]));
      if(decoded=='/' || decoded=='\\' || decoded<32 || decoded==127)
        reject(EXR_DAV_ARGUMENT,"Ambiguous encoded resource segment");
      segment+=(char)decoded;out+='%';
      out+=(char)std::toupper((unsigned char)input[++i]);out+=(char)std::toupper((unsigned char)input[++i]);
    } else {
      if(ch<=32 || ch>=127 || ch=='\\' || ch=='?' || ch=='#' || ch=='"' || ch=='<' || ch=='>')
        reject(EXR_DAV_ARGUMENT,"Resource paths require safe URI encoding");
      segment+=(char)ch;out+=(char)ch;
    }
  }
  finish();return out;
}
struct url { std::string origin,host,path;unsigned port=443; };
url parse(const std::string &input) {
  if(input.size()>8192 || input.compare(0,8,"https://")) reject(EXR_DAV_ARGUMENT,"An HTTPS URL is required");
  size_t slash=input.find('/',8);if(slash==std::string::npos) reject(EXR_DAV_ARGUMENT,"A collection path is required");
  std::string authority=input.substr(8,slash-8);url u;
  size_t colon=authority.find(':');u.host=authority.substr(0,colon);
  if(u.host.empty() || u.host.size()>253 || u.host.front()=='.' || u.host.back()=='.') reject(EXR_DAV_ARGUMENT,"Invalid HTTPS host");
  for(char &c:u.host) {
    if(!((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='-'||c=='.'))
      reject(EXR_DAV_ARGUMENT,"Only DNS and IPv4 HTTPS hosts are supported");
    c=(char)std::tolower((unsigned char)c);
  }
  if(colon!=std::string::npos) {
    std::string port=authority.substr(colon+1);unsigned value=0;
    if(port.empty() || port.size()>5) reject(EXR_DAV_ARGUMENT,"Invalid HTTPS port");
    for(char c:port) { if(c<'0'||c>'9') reject(EXR_DAV_ARGUMENT,"Invalid HTTPS port");value=value*10+(unsigned)(c-'0'); }
    if(!value || value>65535) reject(EXR_DAV_ARGUMENT,"Invalid HTTPS port");
    u.port=value;
  }
  u.origin="https://"+u.host+":"+std::to_string(u.port);u.path=path(input.substr(slash),true);return u;
}
std::string full(const url &u) { return u.origin+u.path; }
std::string trim(std::string s) {
  size_t begin=s.find_first_not_of(" \t\r\n");if(begin==std::string::npos) return {};
  return s.substr(begin,s.find_last_not_of(" \t\r\n")-begin+1);
}
uint64_t number(const std::string &s) {
  if(s.empty()) reject(EXR_DAV_FORMAT,"Missing byte length");
  uint64_t v=0;
  for(char c:s) { if(c<'0'||c>'9'||v>(UINT64_MAX-(unsigned)(c-'0'))/10) reject(EXR_DAV_FORMAT,"Invalid byte length");v=v*10+(unsigned)(c-'0'); }
  return v;
}
#ifdef _WIN32
std::wstring wide(const std::string &s) {
  int n=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,s.c_str(),-1,NULL,0);
  if(!n) reject(EXR_DAV_ARGUMENT,"Invalid UTF-8 path");std::vector<wchar_t> result((size_t)n);
  if(!MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,s.c_str(),-1,result.data(),n)) reject(EXR_DAV_ARGUMENT,"Invalid UTF-8 path");
  return result.data();
}
std::string narrow(const wchar_t *s) {
  if(!s) return {};
  int n=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,s,-1,NULL,0,NULL,NULL);
  if(!n) reject(EXR_DAV_FORMAT,"Invalid XML text");std::vector<char> result((size_t)n);
  if(!WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,s,-1,result.data(),n,NULL,NULL)) reject(EXR_DAV_FORMAT,"Invalid XML text");
  return result.data();
}
struct internet { HINTERNET h=nullptr; ~internet(){if(h) WinHttpCloseHandle(h);} };
#endif

class temporary {
#ifdef _WIN32
  HANDLE file=INVALID_HANDLE_VALUE;std::wstring directory,name,dest;
#else
  int directory=-1,file=-1;std::string name,dest;
#endif
public:
  temporary(const std::string &folder,const std::string &leaf) {
    if(folder.empty() || !utf8(folder) || leaf.empty() || leaf.size()>240 || !utf8(leaf) ||
       leaf=="." || leaf==".." || leaf.find_first_of("/\\:*?\"<>|")!=std::string::npos || leaf.back()=='.' || leaf.back()==' ')
      reject(EXR_DAV_ARGUMENT,"Destination requires a private directory and plain filename");
    std::string stem=leaf.substr(0,leaf.find('.'));
    for(char &ch:stem) ch=(char)std::toupper((unsigned char)ch);
    if(stem=="CON"||stem=="PRN"||stem=="AUX"||stem=="NUL"||
       (stem.size()==4&&(stem.compare(0,3,"COM")==0||stem.compare(0,3,"LPT")==0)&&stem[3]>='1'&&stem[3]<='9'))
      reject(EXR_DAV_ARGUMENT,"Reserved destination filename");
#ifdef _WIN32
    directory=wide(folder);dest=directory+L"\\"+wide(leaf);
    DWORD attributes=GetFileAttributesW(directory.c_str());
    if(attributes==INVALID_FILE_ATTRIBUTES || !(attributes&FILE_ATTRIBUTE_DIRECTORY) || (attributes&FILE_ATTRIBUTE_REPARSE_POINT))
      reject(EXR_DAV_IO,"Private destination directory is unavailable");
    static volatile LONG serial=0;
    for(unsigned attempt=0;attempt<64;attempt++) {
      name=directory+L"\\.exr-webdav-"+std::to_wstring(GetCurrentProcessId())+L"-"+std::to_wstring(InterlockedIncrement(&serial))+L".tmp";
      file=CreateFileW(name.c_str(),GENERIC_WRITE,0,NULL,CREATE_NEW,FILE_ATTRIBUTE_NORMAL|FILE_FLAG_OPEN_REPARSE_POINT,NULL);
      if(file!=INVALID_HANDLE_VALUE) return;
      if(GetLastError()!=ERROR_FILE_EXISTS && GetLastError()!=ERROR_ALREADY_EXISTS) break;
    }
#else
    directory=open(folder.c_str(),O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
    if(directory<0) reject(EXR_DAV_IO,"Private destination directory is unavailable");
    try {
      dest=leaf;
      for(unsigned attempt=0;attempt<64;attempt++) {
      unsigned char random[16];int entropy=open("/dev/urandom",O_RDONLY|O_CLOEXEC);
      ssize_t got=entropy<0 ? -1:read(entropy,random,sizeof(random));if(entropy>=0) close(entropy);
      if(got!=(ssize_t)sizeof(random)) break;
      name=".exr-webdav-";for(unsigned char c:random) { static const char h[]="0123456789abcdef";name+=h[c>>4];name+=h[c&15]; }name+=".tmp";
      file=openat(directory,name.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
        if(file>=0) return;
        if(errno!=EEXIST) break;
      }
    } catch(...) {
      close(directory);directory=-1;throw;
    }
    close(directory);directory=-1;
#endif
    name.clear();reject(EXR_DAV_IO,"Cannot create private download temporary file");
  }
  ~temporary() {
#ifdef _WIN32
    if(file!=INVALID_HANDLE_VALUE) CloseHandle(file);
    if(!name.empty()) DeleteFileW(name.c_str());
#else
    if(file>=0) close(file);
    if(directory>=0) { if(!name.empty()) unlinkat(directory,name.c_str(),0);close(directory); }
#endif
  }
  void write(const void *data,size_t bytes) {
    const unsigned char *p=(const unsigned char *)data;
    while(bytes) {
#ifdef _WIN32
      DWORD got=0;if(!WriteFile(file,p,(DWORD)bytes,&got,NULL)||!got) reject(EXR_DAV_IO,"Cannot write private download");
#else
      ssize_t got=::write(file,p,bytes);if(got<0 && errno==EINTR) continue;if(got<=0) reject(EXR_DAV_IO,"Cannot write private download");
#endif
      p+=got;bytes-=(size_t)got;
    }
  }
  void publish(const exr_webdav_control *control) {
#ifdef _WIN32
    if(!FlushFileBuffers(file)) reject(EXR_DAV_IO,"Cannot flush private download");
    CloseHandle(file);file=INVALID_HANDLE_VALUE;cancelled(control);
    if(!MoveFileExW(name.c_str(),dest.c_str(),MOVEFILE_WRITE_THROUGH)) {
      DWORD code=GetLastError();reject(code==ERROR_ALREADY_EXISTS||code==ERROR_FILE_EXISTS ? EXR_DAV_EXISTS:EXR_DAV_IO,"Destination publication refused");
    }
#else
    if(fsync(file)!=0) reject(EXR_DAV_IO,"Cannot flush private download");
    cancelled(control);
#ifdef __ANDROID__
    // App SELinux permits rename but not hard links. The libc wrapper starts at
    // API 30; the public NDK syscall entry supports the API 26 kernel baseline.
    // Unsupported kernels/filesystems fail closed; never fall back to replace.
    if(syscall(SYS_renameat2,directory,name.c_str(),directory,dest.c_str(),RENAME_NOREPLACE)!=0)
      reject(errno==EEXIST ? EXR_DAV_EXISTS:EXR_DAV_IO,"Destination publication refused");
#else
    if(linkat(directory,name.c_str(),directory,dest.c_str(),0)!=0) reject(errno==EEXIST ? EXR_DAV_EXISTS:EXR_DAV_IO,"Destination publication refused");
    unlinkat(directory,name.c_str(),0);
#endif
#endif
    name.clear();
  }
};
struct sink {
  uint64_t maximum,received=0;const exr_webdav_control *control;
  std::vector<unsigned char> *buffer=nullptr;temporary *file=nullptr;
  exr_webdav_write_observer observer=nullptr;void *observer_context=nullptr;
  void append(const void *data,size_t bytes) {
    cancelled(control);if(bytes>maximum-received) reject(EXR_DAV_LIMIT,"Transfer byte limit exceeded");
    if(file) { file->write(data,bytes);if(observer) observer(observer_context,data,bytes); }
    else { const unsigned char *p=(const unsigned char *)data;buffer->insert(buffer->end(),p,p+bytes); }
    received+=(uint64_t)bytes;if(control && control->progress) control->progress(control->context,received);
  }
};
struct response { int status=0;std::string location;uint64_t length=0;bool has_length=false; };
struct upload {
  std::FILE *file=nullptr;uint64_t length=0,sent=0;const exr_webdav_control *control;
  upload(const char *name,uint64_t expected,const exr_webdav_control *c):length(expected),control(c){
    if(!name || !expected || expected>UINT64_C(128)*1024*1024)reject(EXR_DAV_ARGUMENT,"Invalid bounded upload file");
    std::filesystem::path p=std::filesystem::u8path(name);
    if(std::filesystem::is_symlink(std::filesystem::symlink_status(p)) || !std::filesystem::is_regular_file(p) || std::filesystem::file_size(p)!=expected)
      reject(EXR_DAV_IO,"Upload source is not a regular exact-length private file");
#ifdef _WIN32
    file=_wfopen(p.c_str(),L"rb");
#else
    int fd=open(name,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);if(fd>=0)file=fdopen(fd,"rb");if(fd>=0&&!file)close(fd);
#endif
    if(!file)reject(EXR_DAV_IO,"Upload source is unavailable");
  }
  ~upload(){if(file)std::fclose(file);}
  size_t read(void *data,size_t capacity){
    cancelled(control);size_t want=(size_t)std::min<uint64_t>(capacity,length-sent);
    size_t got=std::fread(data,1,want,file);if(got!=want)reject(EXR_DAV_IO,"Upload source changed or became unreadable");
    sent+=got;if(control&&control->progress)control->progress(control->context,sent);return got;
  }
};
bool redirect(int status) { return status==301||status==302||status==307||status==308; }
void head(const response &r,int expected,sink &s) {
  if(redirect(r.status)) return;
  if(r.status==401) reject(EXR_DAV_AUTH,"Credentials required for the configured origin",401);
  bool accepted=r.status==expected || (expected==-201&&(r.status==201||r.status==405)) ||
    (expected==-202&&(r.status==201||r.status==204||r.status==412));
  if(!accepted) reject(EXR_DAV_HTTP,"Server rejected the WebDAV request",r.status);
  if(r.has_length && r.length>s.maximum) reject(EXR_DAV_LIMIT,"Declared response exceeds byte limit",r.status);
}
using clock_type=std::chrono::steady_clock;
long remaining(clock_type::time_point deadline) {
  auto ms=std::chrono::duration_cast<std::chrono::milliseconds>(deadline-clock_type::now()).count();
  if(ms<=0) reject(EXR_DAV_IO,"HTTPS transfer timed out");
  return (long)std::min<int64_t>(ms,120000);
}
}

struct exr_webdav_client {
  url root;std::string authorization;uint64_t max_download;size_t max_listing,max_entries;unsigned timeout;
#ifdef __ANDROID__
  std::thread::id android_owner=std::this_thread::get_id();
  bool android_active=false;
  jobject android_backend=nullptr;
#endif
#ifdef EXR_WEBDAV_APPLE_URLSESSION
  std::thread::id apple_owner=std::this_thread::get_id();
  bool apple_active=false;
#endif
};

namespace {
#ifdef EXR_WEBDAV_APPLE_URLSESSION
struct apple_operation {
  exr_webdav_client *client;
  explicit apple_operation(exr_webdav_client *value):client(value){
    if(client->apple_owner!=std::this_thread::get_id()||client->apple_active)
      reject(EXR_DAV_ARGUMENT,"Native HTTPS client requires its creating worker without reentry");
    client->apple_active=true;
  }
  ~apple_operation(){client->apple_active=false;}
};
#endif
#ifdef _WIN32
std::string header(HINTERNET request,DWORD kind) {
  DWORD bytes=0;WinHttpQueryHeaders(request,kind,NULL,NULL,&bytes,NULL);
  if(GetLastError()==ERROR_WINHTTP_HEADER_NOT_FOUND) return {};
  if(bytes>16384 || GetLastError()!=ERROR_INSUFFICIENT_BUFFER) reject(EXR_DAV_FORMAT,"Invalid HTTPS response headers");
  std::vector<wchar_t> value(bytes/sizeof(wchar_t)+1);
  if(!WinHttpQueryHeaders(request,kind,NULL,value.data(),&bytes,NULL)) reject(EXR_DAV_IO,"Cannot read HTTPS response headers");
  return narrow(value.data());
}
response perform(exr_webdav_client &client,const url &u,const char *method,int expected,sink &s,clock_type::time_point deadline,upload *input=nullptr) {
  internet session,connection,request;response r;std::wstring host=wide(u.host),target=wide(u.path),verb=wide(method);
  session.h=WinHttpOpen(L"EXReader-WebDAV/0.1.0",WINHTTP_ACCESS_TYPE_NO_PROXY,WINHTTP_NO_PROXY_NAME,WINHTTP_NO_PROXY_BYPASS,0);
  if(!session.h) reject(EXR_DAV_IO,"Cannot create native HTTPS session");
  int timeout=(int)remaining(deadline);
  if(!WinHttpSetTimeouts(session.h,timeout,timeout,timeout,timeout)) reject(EXR_DAV_IO,"Cannot bound native HTTPS timeouts");
  connection.h=WinHttpConnect(session.h,host.c_str(),(INTERNET_PORT)u.port,0);
  if(!connection.h) reject(EXR_DAV_IO,"Cannot connect HTTPS origin");
  request.h=WinHttpOpenRequest(connection.h,verb.c_str(),target.c_str(),NULL,WINHTTP_NO_REFERER,WINHTTP_DEFAULT_ACCEPT_TYPES,WINHTTP_FLAG_SECURE|WINHTTP_FLAG_ESCAPE_DISABLE);
  if(!request.h) reject(EXR_DAV_IO,"Cannot create native HTTPS request");
  DWORD features=WINHTTP_DISABLE_REDIRECTS|WINHTTP_DISABLE_COOKIES|WINHTTP_DISABLE_AUTHENTICATION;
  if(!WinHttpSetOption(request.h,WINHTTP_OPTION_DISABLE_FEATURE,&features,sizeof(features))) reject(EXR_DAV_IO,"Cannot isolate HTTPS credentials");
  std::wstring headers=L"Accept-Encoding: identity\r\n";
  const char *body="";
  if(!std::strcmp(method,"PROPFIND")) { headers+=L"Depth: 1\r\nContent-Type: application/xml; charset=utf-8\r\n";body="<?xml version=\"1.0\"?><d:propfind xmlns:d=\"DAV:\"><d:prop><d:displayname/><d:resourcetype/><d:getcontentlength/><d:getetag/></d:prop></d:propfind>"; }
  if(input)headers+=L"If-None-Match: *\r\nContent-Type: application/octet-stream\r\n";
  if(!client.authorization.empty()) headers+=L"Authorization: "+wide(client.authorization)+L"\r\n";
  cancelled(s.control);
  if(!WinHttpSendRequest(request.h,headers.c_str(),(DWORD)-1L,input?WINHTTP_NO_REQUEST_DATA:(LPVOID)body,input?0:(DWORD)std::strlen(body),input?(DWORD)input->length:(DWORD)std::strlen(body),0)) {
    DWORD error=GetLastError();reject(error==ERROR_WINHTTP_SECURE_FAILURE ? EXR_DAV_TLS:EXR_DAV_IO,"Native HTTPS request failed");
  }
  if(input){unsigned char buffer[65536];while(input->sent<input->length){size_t got=input->read(buffer,sizeof(buffer));DWORD wrote=0;if(!WinHttpWriteData(request.h,buffer,(DWORD)got,&wrote)||wrote!=got)reject(EXR_DAV_IO,"Native HTTPS upload failed");remaining(deadline);}}
  if(!WinHttpReceiveResponse(request.h,NULL)){DWORD error=GetLastError();reject(error==ERROR_WINHTTP_SECURE_FAILURE?EXR_DAV_TLS:EXR_DAV_IO,"Native HTTPS response failed");}
  DWORD code=0,bytes=sizeof(code);
  if(!WinHttpQueryHeaders(request.h,WINHTTP_QUERY_STATUS_CODE|WINHTTP_QUERY_FLAG_NUMBER,NULL,&code,&bytes,NULL)) reject(EXR_DAV_IO,"Missing HTTPS status");
  r.status=(int)code;r.location=header(request.h,WINHTTP_QUERY_LOCATION);
  std::string length=header(request.h,WINHTTP_QUERY_CONTENT_LENGTH);r.has_length=!length.empty();if(r.has_length) r.length=number(length);
  head(r,expected,s);if(redirect(r.status)) return r;
  unsigned char buffer[65536];
  for(;;) {
    cancelled(s.control);DWORD wait=(DWORD)remaining(deadline);
    if(!WinHttpSetOption(request.h,WINHTTP_OPTION_RECEIVE_TIMEOUT,&wait,sizeof(wait))) reject(EXR_DAV_IO,"Cannot bound HTTPS receive timeout");
    DWORD got=0;if(!WinHttpReadData(request.h,buffer,sizeof(buffer),&got)) reject(EXR_DAV_IO,"Native HTTPS body read failed");
    if(!got) break;s.append(buffer,got);
  }
  if(r.has_length && r.length!=s.received) reject(EXR_DAV_IO,"Incomplete HTTPS response body");return r;
}
#elif defined(__ANDROID__)
#include "android_transport.inc"
#elif defined(EXR_WEBDAV_APPLE_URLSESSION)
response perform(exr_webdav_client &client,const url &u,const char *method,int expected,sink &s,clock_type::time_point deadline,upload *input=nullptr){
  struct context {
    sink *output;upload *input;int expected;response result{};
    failure error{EXR_DAV_OK,"",0};
  } state{&s,input,expected};
  exr_apple_request request{};std::string target=full(u);
  request.url=target.c_str();request.authorization=client.authorization.c_str();request.method=method;
  request.timeout_ms=(unsigned)remaining(deadline);request.upload_bytes=input?input->length:0;request.context=&state;
  request.cancelled=[](void *value){return stop(((context *)value)->output->control)?1:0;};
  /* No C++ exception crosses the Objective-C language bridge. */
  request.headers=[](void *value,int status,const char *location,const char *length){
    auto &state=*(context *)value;
    try{
      state.result.status=status;state.result.location=location;
      if(*length){state.result.length=number(trim(length));state.result.has_length=true;}
      head(state.result,state.expected,*state.output);return EXR_DAV_OK;
    }catch(const failure &error){state.error=error;return error.code;}
    catch(...){state.error={EXR_DAV_MEMORY,"Cannot allocate HTTPS headers",0};return EXR_DAV_MEMORY;}
  };
  request.receive=[](void *value,const void *bytes,size_t count){
    auto &state=*(context *)value;
    try{state.output->append(bytes,count);return EXR_DAV_OK;}
    catch(const failure &error){state.error=error;return error.code;}
    catch(...){state.error={EXR_DAV_MEMORY,"Cannot allocate HTTPS body",0};return EXR_DAV_MEMORY;}
  };
  if(input)request.read=[](void *value,void *bytes,size_t capacity,size_t *count){
    auto &state=*(context *)value;
    try{*count=state.input->read(bytes,capacity);return EXR_DAV_OK;}
    catch(const failure &error){state.error=error;return error.code;}
    catch(...){state.error={EXR_DAV_MEMORY,"Cannot read upload source",0};return EXR_DAV_MEMORY;}
  };
  cancelled(s.control);exr_webdav_error error{};exr_webdav_status status=exr_apple_http(&request,&error);
  if(state.error.code!=EXR_DAV_OK)throw state.error;
  cancelled(s.control);
  if(status!=EXR_DAV_OK)reject(status,"Native HTTPS transfer failed",error.http_status);
  head(state.result,expected,s);
  if(state.result.has_length&&!redirect(state.result.status)&&state.result.length!=s.received)
    reject(EXR_DAV_IO,"Incomplete HTTPS response body");
  return state.result;
}
#else
/* NOSIGNAL keeps libcurl from changing process-wide handlers. TLS backends
   can still write a close_notify to a reset peer, including during cleanup.
   Mask only this worker and retain any signal already pending on entry. */
class sigpipe_scope {
  sigset_t set{},previous{};
  bool was_pending=false;
public:
  sigpipe_scope() {
    sigemptyset(&set);sigaddset(&set,SIGPIPE);
    if(pthread_sigmask(SIG_BLOCK,&set,&previous))reject(EXR_DAV_IO,"Cannot guard native HTTPS worker signals");
    sigset_t pending{};
    if(sigpending(&pending)) {
      pthread_sigmask(SIG_SETMASK,&previous,nullptr);
      reject(EXR_DAV_IO,"Cannot inspect native HTTPS worker signals");
    }
    was_pending=sigismember(&pending,SIGPIPE)==1;
  }
  sigpipe_scope(const sigpipe_scope &)=delete;
  sigpipe_scope &operator=(const sigpipe_scope &)=delete;
  ~sigpipe_scope() noexcept {
    sigset_t pending{};
    if(!was_pending&&!sigpending(&pending)&&sigismember(&pending,SIGPIPE)==1) {
#ifdef __APPLE__
      /* Darwin has no sigtimedwait. A pipe error queues SIGPIPE to this
         blocked worker; another worker cannot consume that directed signal. */
      int received=0;sigwait(&set,&received);
#else
      timespec zero{};
      while(sigtimedwait(&set,nullptr,&zero)<0&&errno==EINTR) {}
#endif
    }
    pthread_sigmask(SIG_SETMASK,&previous,nullptr);
  }
};
struct curl_context { response r;sink *output;upload *input=nullptr;int expected;size_t header_bytes=0;failure error{EXR_DAV_OK,"",0}; };
size_t curl_head(char *data,size_t size,size_t count,void *opaque) {
  auto &c=*(curl_context *)opaque;size_t n=size*count;
  try {
    if(n>32768-c.header_bytes) reject(EXR_DAV_LIMIT,"HTTPS header limit exceeded");
    c.header_bytes+=n;
    std::string line(data,n);
    if(line.compare(0,5,"HTTP/")==0) {
      c.r=response{};size_t space=line.find(' ');if(space==std::string::npos) reject(EXR_DAV_FORMAT,"Invalid HTTPS status");
      c.r.status=std::atoi(line.c_str()+space+1);
    } else if(line=="\r\n") { if(c.r.status>=200) head(c.r,c.expected,*c.output); }
    else {
      size_t colon=line.find(':');if(colon!=std::string::npos) {
        std::string key=line.substr(0,colon);for(char &ch:key) ch=(char)std::tolower((unsigned char)ch);
        std::string value=trim(line.substr(colon+1));
        if(key=="location") { if(value.size()>8192 || !c.r.location.empty()) reject(EXR_DAV_FORMAT,"Invalid redirect header");c.r.location=value; }
        if(key=="content-length") { uint64_t length=number(value);if(c.r.has_length&&length!=c.r.length) reject(EXR_DAV_FORMAT,"Conflicting byte lengths");c.r.length=length;c.r.has_length=true; }
      }
    }
    return n;
  } catch(const failure &e) { c.error=e;return 0; } catch(...) { c.error={EXR_DAV_MEMORY,"Cannot allocate HTTPS headers",0};return 0; }
}
size_t curl_body(char *data,size_t size,size_t count,void *opaque) {
  auto &c=*(curl_context *)opaque;size_t n=size*count;
  try { if(redirect(c.r.status)) return 0;c.output->append(data,n);return n; }
  catch(const failure &e) { c.error=e;return 0; } catch(...) { c.error={EXR_DAV_MEMORY,"Cannot allocate HTTPS body",0};return 0; }
}
int curl_progress(void *opaque,curl_off_t,curl_off_t,curl_off_t,curl_off_t) { return stop(((curl_context *)opaque)->output->control) ? 1:0; }
size_t curl_read(char *data,size_t size,size_t count,void *opaque){auto &c=*(curl_context *)opaque;try{return c.input->read(data,size*count);}catch(const failure &e){c.error=e;return CURL_READFUNC_ABORT;}catch(...){c.error={EXR_DAV_MEMORY,"Cannot read upload source",0};return CURL_READFUNC_ABORT;}}
response perform(exr_webdav_client &client,const url &u,const char *method,int expected,sink &s,clock_type::time_point deadline,upload *input=nullptr) {
  sigpipe_scope signals; /* Before handle: restored after curl_easy_cleanup. */
  static const CURLcode initialized=curl_global_init(CURL_GLOBAL_DEFAULT);
  if(initialized!=CURLE_OK) reject(EXR_DAV_IO,"Cannot initialize native HTTPS transport");
  std::unique_ptr<CURL,decltype(&curl_easy_cleanup)> handle(curl_easy_init(),curl_easy_cleanup);
  if(!handle) reject(EXR_DAV_MEMORY,"Cannot create native HTTPS session");
  curl_context context;context.output=&s;context.expected=expected;context.input=input;CURL *h=handle.get();std::string target=full(u);
  std::unique_ptr<curl_slist,decltype(&curl_slist_free_all)> headers(nullptr,curl_slist_free_all);
  auto add=[&](const std::string &v) {
    curl_slist *next=curl_slist_append(headers.get(),v.c_str());
    if(!next) reject(EXR_DAV_MEMORY,"Cannot create HTTPS headers");
    headers.release();headers.reset(next);
  };
  add("Accept-Encoding: identity");
  if(!client.authorization.empty()) add("Authorization: "+client.authorization);
  const char *body="<?xml version=\"1.0\"?><d:propfind xmlns:d=\"DAV:\"><d:prop><d:displayname/><d:resourcetype/><d:getcontentlength/><d:getetag/></d:prop></d:propfind>";
  if(!std::strcmp(method,"PROPFIND")) { add("Depth: 1");add("Content-Type: application/xml; charset=utf-8"); }
  if(input){add("If-None-Match: *");add("Content-Type: application/octet-stream");add("Expect:");}
  curl_easy_setopt(h,CURLOPT_URL,target.c_str());curl_easy_setopt(h,CURLOPT_CUSTOMREQUEST,method);
  curl_easy_setopt(h,CURLOPT_HTTPHEADER,headers.get());curl_easy_setopt(h,CURLOPT_PROXY,"");
#if LIBCURL_VERSION_NUM >= 0x075500
  curl_easy_setopt(h,CURLOPT_PROTOCOLS_STR,"https");
#else
  curl_easy_setopt(h,CURLOPT_PROTOCOLS,(long)CURLPROTO_HTTPS);
#endif
  curl_easy_setopt(h,CURLOPT_FOLLOWLOCATION,0L);
  curl_easy_setopt(h,CURLOPT_SSL_VERIFYPEER,1L);curl_easy_setopt(h,CURLOPT_SSL_VERIFYHOST,2L);
  curl_easy_setopt(h,CURLOPT_NOSIGNAL,1L);curl_easy_setopt(h,CURLOPT_TIMEOUT_MS,remaining(deadline));
  curl_easy_setopt(h,CURLOPT_HEADERFUNCTION,curl_head);curl_easy_setopt(h,CURLOPT_HEADERDATA,&context);
  curl_easy_setopt(h,CURLOPT_WRITEFUNCTION,curl_body);curl_easy_setopt(h,CURLOPT_WRITEDATA,&context);
  curl_easy_setopt(h,CURLOPT_XFERINFOFUNCTION,curl_progress);curl_easy_setopt(h,CURLOPT_XFERINFODATA,&context);curl_easy_setopt(h,CURLOPT_NOPROGRESS,0L);
  if(!std::strcmp(method,"PROPFIND")) { curl_easy_setopt(h,CURLOPT_POSTFIELDS,body);curl_easy_setopt(h,CURLOPT_POSTFIELDSIZE,(long)std::strlen(body)); }
  if(input){curl_easy_setopt(h,CURLOPT_UPLOAD,1L);curl_easy_setopt(h,CURLOPT_READFUNCTION,curl_read);curl_easy_setopt(h,CURLOPT_READDATA,&context);curl_easy_setopt(h,CURLOPT_INFILESIZE_LARGE,(curl_off_t)input->length);}
  cancelled(s.control);CURLcode result=curl_easy_perform(h);
  if(context.error.code!=EXR_DAV_OK) throw context.error;
  cancelled(s.control);
  if(redirect(context.r.status)) return context.r;
  if(result!=CURLE_OK) reject(result==CURLE_PEER_FAILED_VERIFICATION || result==CURLE_SSL_CONNECT_ERROR ? EXR_DAV_TLS:EXR_DAV_IO,"Native HTTPS transfer failed");
  head(context.r,expected,s);return context.r;
}
#endif

url resolve(exr_webdav_client &client,const url &current,const std::string &reference) {
  url result=current;
  if(reference.compare(0,8,"https://")==0) result=parse(reference);
  else if(reference.empty() || reference.find("://")!=std::string::npos || reference.compare(0,2,"//")==0)
    reject(EXR_DAV_REDIRECT,"Unsafe remote resource or redirect");
  else if(reference[0]=='/') result.path=path(reference,true);
  else {
    size_t slash=current.path.find_last_of('/');result.path=path(current.path.substr(0,slash+1)+reference,true);
  }
  if(result.origin!=client.root.origin || result.path.compare(0,client.root.path.size(),client.root.path))
    reject(EXR_DAV_REDIRECT,"Remote resource leaves the configured HTTPS origin or collection");
  return result;
}
url fetch(exr_webdav_client &client,url u,const char *method,int expected,sink &s) {
  auto deadline=clock_type::now()+std::chrono::milliseconds(client.timeout);std::set<std::string> visited;
  for(unsigned redirects=0;;redirects++) {
    cancelled(s.control);if(!visited.insert(full(u)).second) reject(EXR_DAV_REDIRECT,"Redirect loop refused");
    response r=perform(client,u,method,expected,s,deadline);
    if(!redirect(r.status)) { cancelled(s.control);return u; }
    if(redirects>=4 || r.location.empty()) reject(EXR_DAV_REDIRECT,"Redirect budget exceeded or location absent");
    u=resolve(client,u,r.location);
  }
}
struct node { std::string name,ns,text;std::vector<node> children; };
node xml(const std::vector<unsigned char> &bytes,size_t maximum_entries) {
  node document;std::vector<node *> stack{&document};size_t responses=0,response_depth=0,response_elements=0,outside_elements=0;
  auto event=[&](int kind,const std::string &name,const std::string &ns,const std::string &text,bool empty) {
    if(kind==1) {
      if(name.size()>128 || ns.size()>1024) reject(EXR_DAV_LIMIT,"WebDAV XML name limit exceeded");
      // Budget each Depth:1 response independently. Apache includes separate
      // successful/missing property groups, so 2000 valid entries can exceed
      // the former global 20000 elements while staying below the byte ceiling.
      if(stack.size()==2&&name=="response"&&ns=="DAV:") {
        if(++responses>maximum_entries+1)reject(EXR_DAV_LIMIT,"WebDAV XML response limit exceeded");
        response_depth=stack.size();response_elements=0;
      }
      if(stack.size()>32 || (response_depth?++response_elements>32:++outside_elements>128))
        reject(EXR_DAV_LIMIT,"WebDAV XML structure limit exceeded");
      stack.back()->children.push_back(node{name,ns,{}, {}});
      if(!empty) stack.push_back(&stack.back()->children.back());
      else if(response_depth==stack.size())response_depth=0;
    } else if(kind==2) {
      if(stack.size()<=1) reject(EXR_DAV_FORMAT,"Invalid WebDAV XML nesting");
      if(response_depth&&stack.size()==response_depth+1)response_depth=0;
      stack.pop_back();
    }
    else if(kind==3) { if(text.size()>65536-stack.back()->text.size()) reject(EXR_DAV_LIMIT,"WebDAV XML text limit exceeded");stack.back()->text+=text; }
  };
#ifdef _WIN32
  IStream *raw=SHCreateMemStream(bytes.data(),(UINT)bytes.size());
  if(!raw) reject(EXR_DAV_MEMORY,"Cannot create XML input stream");
  std::unique_ptr<IStream,void(*)(IStream *)> stream(raw,[](IStream *p){p->Release();});
  IXmlReader *reader=nullptr;
  if(FAILED(CreateXmlReader(__uuidof(IXmlReader),(void **)&reader,NULL))) reject(EXR_DAV_IO,"Cannot create native XML reader");
  std::unique_ptr<IXmlReader,void(*)(IXmlReader *)> owner(reader,[](IXmlReader *p){p->Release();});
  if(FAILED(reader->SetProperty(XmlReaderProperty_DtdProcessing,DtdProcessing_Prohibit)) || FAILED(reader->SetInput(raw))) reject(EXR_DAV_FORMAT,"Cannot configure safe XML reader");
  XmlNodeType type;HRESULT status;
  while((status=reader->Read(&type))==S_OK) {
    const wchar_t *name=L"",*ns=L"",*value=L"";
    if(type==XmlNodeType_Element) {
      if(FAILED(reader->GetLocalName(&name,NULL))||FAILED(reader->GetNamespaceUri(&ns,NULL))) reject(EXR_DAV_FORMAT,"Invalid WebDAV XML names");
      event(1,narrow(name),narrow(ns),{},reader->IsEmptyElement()!=FALSE);
    } else if(type==XmlNodeType_EndElement) event(2,{},{},{},false);
    else if(type==XmlNodeType_Text||type==XmlNodeType_CDATA||type==XmlNodeType_Whitespace) {
      if(FAILED(reader->GetValue(&value,NULL))) reject(EXR_DAV_FORMAT,"Invalid WebDAV XML text");event(3,{},{},narrow(value),false);
    } else if(type==XmlNodeType_DocumentType) reject(EXR_DAV_FORMAT,"DTD is not allowed");
  }
  if(FAILED(status)) reject(EXR_DAV_FORMAT,"Malformed WebDAV XML");
#elif defined(__ANDROID__)
  android_xml(bytes,event);
#else
  xmlTextReaderPtr raw=xmlReaderForMemory((const char *)bytes.data(),(int)bytes.size(),NULL,NULL,XML_PARSE_NONET|XML_PARSE_NOERROR|XML_PARSE_NOWARNING);
  if(!raw) reject(EXR_DAV_FORMAT,"Cannot create safe XML reader");
  std::unique_ptr<_xmlTextReader,decltype(&xmlFreeTextReader)> reader(raw,xmlFreeTextReader);int status;
  while((status=xmlTextReaderRead(raw))==1) {
    int type=xmlTextReaderNodeType(raw);
    auto text=[](const xmlChar *s) { return s ? std::string((const char *)s):std::string(); };
    if(type==XML_READER_TYPE_ELEMENT) event(1,text(xmlTextReaderConstLocalName(raw)),text(xmlTextReaderConstNamespaceUri(raw)),{},xmlTextReaderIsEmptyElement(raw)==1);
    else if(type==XML_READER_TYPE_END_ELEMENT) event(2,{},{},{},false);
    else if(type==XML_READER_TYPE_TEXT||type==XML_READER_TYPE_CDATA||type==XML_READER_TYPE_WHITESPACE||type==XML_READER_TYPE_SIGNIFICANT_WHITESPACE) event(3,{},{},text(xmlTextReaderConstValue(raw)),false);
    else if(type==XML_READER_TYPE_DOCUMENT_TYPE||type==XML_READER_TYPE_ENTITY_REFERENCE) reject(EXR_DAV_FORMAT,"DTD and external entities are not allowed");
  }
  if(status<0) reject(EXR_DAV_FORMAT,"Malformed WebDAV XML");
#endif
  if(stack.size()!=1 || document.children.size()!=1) reject(EXR_DAV_FORMAT,"Missing WebDAV XML root");
  return std::move(document.children[0]);
}
bool dav(const node &n,const char *name) { return n.ns=="DAV:" && n.name==name; }
const node *child(const node &n,const char *name,bool required=false) {
  const node *found=nullptr;for(const auto &value:n.children) if(dav(value,name)) { if(found) reject(EXR_DAV_FORMAT,"Duplicate WebDAV property");found=&value; }
  if(!found && required) reject(EXR_DAV_FORMAT,"Missing WebDAV property");
  return found;
}
bool success(const node &n) { int code=0;return std::sscanf(n.text.c_str(),"%*15s %d",&code)==1 && code>=200 && code<300; }
char *copy(const std::string &s) { char *out=(char *)std::malloc(s.size()+1);if(!out) throw std::bad_alloc();std::memcpy(out,s.c_str(),s.size()+1);return out; }
std::string component_title(const std::string &component) {
  std::string title;
  for(size_t n=0;n<component.size();n++) {
    if(component[n]=='%'){title+=(char)(hex(component[n+1])*16+hex(component[n+2]));n+=2;}
    else title+=component[n];
  }
  return title;
}
exr_webdav_status report(exr_webdav_error *e,const failure &f) {
  if(e) { e->code=f.code;e->http_status=f.http;std::snprintf(e->message,sizeof(e->message),"%s",f.message); }return f.code;
}
void clean(exr_webdav_error *e) { if(e) std::memset(e,0,sizeof(*e)); }
}

#ifdef __ANDROID__
extern "C" exr_webdav_status exr_webdav_android_initialize(JNIEnv *env) { return android_initialize(env); }
#endif
extern "C" exr_webdav_status exr_webdav_create(const exr_webdav_config *config,exr_webdav_client **out,exr_webdav_error *error) {
  clean(error);if(out) *out=nullptr;
  try {
    if(!config || !out || !config->root_url) reject(EXR_DAV_ARGUMENT,"Missing WebDAV configuration");
    std::unique_ptr<exr_webdav_client> c(new exr_webdav_client);c->root=parse(config->root_url);
    if(c->root.path.back()!='/') reject(EXR_DAV_ARGUMENT,"Root collection URL must end in slash");
    c->authorization=config->authorization ? config->authorization:"";
    if(c->authorization.size()>8192) reject(EXR_DAV_ARGUMENT,"Authorization value too long");
    for(unsigned char ch:c->authorization) if(ch<32 || ch>=127) reject(EXR_DAV_ARGUMENT,"Invalid Authorization value");
    c->max_download=config->max_download_bytes ? config->max_download_bytes:UINT64_C(128)*1024*1024;
    c->max_listing=config->max_listing_bytes ? config->max_listing_bytes:4*1024*1024;
    c->max_entries=config->max_entries ? config->max_entries:2000;c->timeout=config->timeout_ms ? config->timeout_ms:30000;
    if(c->max_download>UINT64_C(128)*1024*1024 || c->max_listing>4*1024*1024 || c->max_entries>2000 || c->timeout>120000)
      reject(EXR_DAV_ARGUMENT,"WebDAV limits exceed module ceilings");
#ifdef __ANDROID__
    android_create(c.get());
#endif
    *out=c.release();return EXR_DAV_OK;
  } catch(const failure &f) { return report(error,f); } catch(...) { return report(error,{EXR_DAV_MEMORY,"Cannot create WebDAV client",0}); }
}
extern "C" void exr_webdav_free(exr_webdav_client *client) {
#ifdef __ANDROID__
  if(!android_release(client))return;
#endif
#ifdef EXR_WEBDAV_APPLE_URLSESSION
  if(client&&(client->apple_owner!=std::this_thread::get_id()||client->apple_active))return;
#endif
  delete client;
}
extern "C" void exr_webdav_listing_free(exr_webdav_listing *listing) {
  if(!listing) return;
  for(size_t i=0;i<listing->count;i++) { std::free(listing->entries[i].resource);std::free(listing->entries[i].display_name);std::free(listing->entries[i].etag); }
  std::free(listing->entries);std::memset(listing,0,sizeof(*listing));
}
extern "C" exr_webdav_status exr_webdav_list(exr_webdav_client *client,const char *collection,const exr_webdav_control *control,exr_webdav_listing *out,exr_webdav_error *error) {
  clean(error);if(out) std::memset(out,0,sizeof(*out));
  try {
    if(!client || !collection || !out) reject(EXR_DAV_ARGUMENT,"Missing collection request");
#ifdef __ANDROID__
    android_operation operation(client);
#elif defined(EXR_WEBDAV_APPLE_URLSESSION)
    apple_operation operation(client);
#endif
    std::string resource=path(collection,false);if(!resource.empty() && resource.back()!='/') reject(EXR_DAV_ARGUMENT,"Collection resource must end in slash");
    url current=client->root;current.path+=resource;std::vector<unsigned char> bytes;sink s{client->max_listing,0,control,&bytes,nullptr};
    current=fetch(*client,current,"PROPFIND",207,s);node root=xml(bytes,client->max_entries);
    if(!dav(root,"multistatus")) reject(EXR_DAV_FORMAT,"Response is not DAV multistatus");
    std::set<std::string> seen;
    for(const node &response_node:root.children) {
      cancelled(control);if(!dav(response_node,"response")) continue;
      const node *href=child(response_node,"href",true);url target=resolve(*client,current,trim(href->text));
      if(target.path==current.path) continue;
      if(target.path.compare(0,current.path.size(),current.path)) reject(EXR_DAV_FORMAT,"Depth-one response is outside its collection");
      std::string relative=target.path.substr(current.path.size()),component=relative;
      if(!component.empty() && component.back()=='/') component.pop_back();
      if(component.empty() || component.find('/')!=std::string::npos) reject(EXR_DAV_FORMAT,"Response exceeds Depth one");
      if(!seen.insert(target.path).second) reject(EXR_DAV_FORMAT,"Duplicate WebDAV resource");
      if(seen.size()>client->max_entries) reject(EXR_DAV_LIMIT,"Collection entry limit exceeded");
      const node *status=child(response_node,"status");if(status && !success(*status)) reject(EXR_DAV_HTTP,"A WebDAV resource could not be listed");
      const node *prop=nullptr;
      for(const node &ps:response_node.children) if(dav(ps,"propstat")) {
        const node *st=child(ps,"status",true);if(success(*st)) { if(prop) reject(EXR_DAV_FORMAT,"Multiple successful property groups are unsupported");prop=child(ps,"prop",true); }
      }
      if(!prop) reject(EXR_DAV_FORMAT,"Missing successful WebDAV properties");
      const node *type=child(*prop,"resourcetype",true),*length=child(*prop,"getcontentlength"),*display=child(*prop,"displayname"),*etag=child(*prop,"getetag");
      bool folder=child(*type,"collection")!=nullptr;
      if(folder!=(target.path.back()=='/')) reject(EXR_DAV_FORMAT,"Collection href and resource type disagree");
      std::string title=display ? display->text:component_title(component),tag=etag ? etag->text:"";
      if(title.size()>1024 || tag.size()>1024 || !utf8(title) || !utf8(tag)) reject(EXR_DAV_FORMAT,"Invalid WebDAV display metadata");
      auto *entries=(exr_webdav_entry *)std::realloc(out->entries,(out->count+1)*sizeof(*out->entries));if(!entries) throw std::bad_alloc();out->entries=entries;
      exr_webdav_entry &entry=out->entries[out->count++];std::memset(&entry,0,sizeof(entry));
      entry.resource=copy(target.path.substr(client->root.path.size()));entry.display_name=copy(title);entry.etag=copy(tag);
      entry.collection=folder;entry.has_size=length!=nullptr;entry.bytes=length ? number(trim(length->text)):0;
    }
    cancelled(control);return EXR_DAV_OK;
  } catch(const failure &f) { exr_webdav_listing_free(out);return report(error,f); } catch(...) { exr_webdav_listing_free(out);return report(error,{EXR_DAV_MEMORY,"Cannot allocate WebDAV listing",0}); }
}
static exr_webdav_status download_file(exr_webdav_client *client,const char *resource,const char *directory,const char *filename,const exr_webdav_control *control,exr_webdav_write_observer observer,void *observer_context,exr_webdav_download *out,exr_webdav_error *error) {
  clean(error);if(out) std::memset(out,0,sizeof(*out));
  try {
    if(!client || !resource || !directory || !filename || !out) reject(EXR_DAV_ARGUMENT,"Missing download request");
#ifdef __ANDROID__
    android_operation operation(client);
#elif defined(EXR_WEBDAV_APPLE_URLSESSION)
    apple_operation operation(client);
#endif
    std::string relative=path(resource,false);if(relative.empty() || relative.back()=='/') reject(EXR_DAV_ARGUMENT,"Download requires a file resource");
    cancelled(control);temporary file(directory,filename);sink s{client->max_download,0,control,nullptr,&file,observer,observer_context};url target=client->root;target.path+=relative;
    fetch(*client,target,"GET",200,s);file.publish(control);out->bytes=s.received;out->published=1;return EXR_DAV_OK;
  } catch(const failure &f) { return report(error,f); } catch(...) { return report(error,{EXR_DAV_MEMORY,"Cannot allocate WebDAV transfer",0}); }
}
extern "C" exr_webdav_status exr_webdav_download_file(exr_webdav_client *client,const char *resource,const char *directory,const char *filename,const exr_webdav_control *control,exr_webdav_download *out,exr_webdav_error *error) {
  return download_file(client,resource,directory,filename,control,nullptr,nullptr,out,error);
}
extern "C" exr_webdav_status exr_webdav_download_observed(exr_webdav_client *client,const char *resource,const char *directory,const char *filename,const exr_webdav_control *control,exr_webdav_write_observer observer,void *observer_context,exr_webdav_download *out,exr_webdav_error *error) {
  return download_file(client,resource,directory,filename,control,observer,observer_context,out,error);
}
extern "C" exr_webdav_status exr_webdav_make_collection(exr_webdav_client *client,const char *collection,const exr_webdav_control *control,exr_webdav_error *error){
  clean(error);try{
    if(!client||!collection)reject(EXR_DAV_ARGUMENT,"Missing immutable collection request");
#ifdef __ANDROID__
    android_operation operation(client);
#elif defined(EXR_WEBDAV_APPLE_URLSESSION)
    apple_operation operation(client);
#endif
    std::string relative=path(collection,false);if(relative.empty()||relative.back()!='/')reject(EXR_DAV_ARGUMENT,"A non-root collection resource is required");
    url target=client->root;target.path+=relative;std::vector<unsigned char> body;sink output{65536,0,control,&body,nullptr};
    response r=perform(*client,target,"MKCOL",-201,output,clock_type::now()+std::chrono::milliseconds(client->timeout));
    if(redirect(r.status))reject(EXR_DAV_REDIRECT,"Immutable writes do not follow redirects");
    cancelled(control);return EXR_DAV_OK;
  }catch(const failure &f){return report(error,f);}catch(...){return report(error,{EXR_DAV_IO,"Cannot create immutable remote collection",0});}
}
extern "C" exr_webdav_status exr_webdav_publish_file(exr_webdav_client *client,const char *resource,const char *name,uint64_t bytes,const exr_webdav_control *control,exr_webdav_error *error){
  clean(error);try{
    if(!client||!resource)reject(EXR_DAV_ARGUMENT,"Missing immutable upload request");
#ifdef __ANDROID__
    android_operation operation(client);
#elif defined(EXR_WEBDAV_APPLE_URLSESSION)
    apple_operation operation(client);
#endif
    std::string relative=path(resource,false);if(relative.empty()||relative.back()=='/'||bytes>client->max_download)reject(EXR_DAV_ARGUMENT,"Invalid bounded immutable upload");
    upload input(name,bytes,control);url target=client->root;target.path+=relative;std::vector<unsigned char> body;sink output{65536,0,control,&body,nullptr};
    response r=perform(*client,target,"PUT",-202,output,clock_type::now()+std::chrono::milliseconds(client->timeout),&input);
    if(redirect(r.status))reject(EXR_DAV_REDIRECT,"Immutable writes do not follow redirects");
    if(r.status==412)reject(EXR_DAV_EXISTS,"Remote immutable identity requires verification",412);
    cancelled(control);return EXR_DAV_OK;
  }catch(const failure &f){return report(error,f);}catch(...){return report(error,{EXR_DAV_IO,"Cannot publish immutable private file",0});}
}
