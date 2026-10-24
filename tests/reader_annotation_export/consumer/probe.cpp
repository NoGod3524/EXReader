// SPDX-License-Identifier: MIT
// Installed-package driver. All paths and titles arrive hex-encoded UTF-8 ("-" = absent)
// so the narrow command line can carry any Unicode on every platform.
//   probe receive-batch <db> <batch>
//   probe export <db> <book> <title-hex|-> <jsonl-hex|-> <md-hex|-> <max_bytes> [key=value...]
//     keys: cancel_after=N  fsize=N (POSIX RLIMIT_FSIZE applied at the first poll)
//           lock=<path-hex> (Windows: hold the target open without delete sharing)
//           thread=1 (call from a non-owner thread)  short_struct=1  null_options=1
//           advance_at_poll=N go=<path-hex> done=<path-hex> advance_wait=N
//             (block inside the cancel callback until a second process has committed a revision)
//           reenter=1 [reenter_at=N] reenter_path=<path-hex> [reenter_stats=1]
//             (call the public entry again from the cancel callback)
#include <reader_annotation_export.h>
#include <reader_projection.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iterator>
#include <map>
#include <string>
#include <thread>
#include <vector>
#include <chrono>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#else
#include <fcntl.h>
#include <signal.h>
#include <sys/resource.h>
#include <unistd.h>
#endif

namespace {
std::string unhex(const std::string &h){
  if(h=="-")return std::string();
  std::string out;
  for(size_t i=0;i+1<h.size();i+=2)out.push_back((char)std::strtol(h.substr(i,2).c_str(),nullptr,16));
  return out;
}
std::string esc(const std::string &s){
  std::string o="\"";
  for(char ch:s){unsigned char c=(unsigned char)ch;
    if(c=='"'||c=='\\'){o.push_back('\\');o.push_back(ch);}
    else if(c<0x20){char b[8];std::snprintf(b,sizeof(b),"\\u%04x",c);o+=b;}
    else o.push_back(ch);}
  return o+"\"";
}
bool path_exists(const std::string &p){
#ifdef _WIN32
  int n=MultiByteToWideChar(CP_UTF8,0,p.c_str(),-1,nullptr,0);
  std::wstring w((size_t)n,L'\0');MultiByteToWideChar(CP_UTF8,0,p.c_str(),-1,&w[0],n);
  return GetFileAttributesW(w.c_str())!=INVALID_FILE_ATTRIBUTES;
#else
  return ::access(p.c_str(),F_OK)==0;
#endif
}
void path_touch(const std::string &p){
  if(p.empty())return;
#ifdef _WIN32
  int n=MultiByteToWideChar(CP_UTF8,0,p.c_str(),-1,nullptr,0);
  std::wstring w((size_t)n,L'\0');MultiByteToWideChar(CP_UTF8,0,p.c_str(),-1,&w[0],n);
  HANDLE h=CreateFileW(w.c_str(),GENERIC_WRITE,0,nullptr,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr);
  if(h!=INVALID_HANDLE_VALUE)CloseHandle(h);
#else
  int fd=::open(p.c_str(),O_WRONLY|O_CREAT|O_TRUNC,0666);
  if(fd>=0)::close(fd);
#endif
}
/* Deterministic handshake: the export blocks inside its own cancel callback
   until the harness has let a second process commit the advance revision. */
bool path_wait(const std::string &p,int seconds){
  if(p.empty())return true;
  for(int i=0;i<seconds*200;i++){
    if(path_exists(p))return true;
    std::this_thread::sleep_for(std::chrono::milliseconds(5));
  }
  return false;
}
struct poll_state {
  unsigned long polls=0,cancel_after=0;
  long long fsize=-1;
  bool limited=false;
  unsigned long advance_at=0;bool advanced=false;int advance_timeout=0;
  std::string go,done;int advance_wait=60;
  unsigned long reenter_at=0;bool reentered=false;
  reader_annotation_export_options *nested=nullptr;
  reader_annotation_export_stats *nested_stats=nullptr;
  reader_annotation_export_error *nested_error=nullptr;
  int reenter_status=-1;
};
int poll(void *context){
  poll_state &s=*(poll_state *)context;
  ++s.polls;
#ifndef _WIN32
  if(s.fsize>=0&&!s.limited){
    s.limited=true;signal(SIGXFSZ,SIG_IGN);
    struct rlimit r;getrlimit(RLIMIT_FSIZE,&r);r.rlim_cur=(rlim_t)s.fsize;setrlimit(RLIMIT_FSIZE,&r);
  }
#endif
  if(s.advance_at&&s.polls==s.advance_at&&!s.advanced){
    s.advanced=true;path_touch(s.go);
    if(!path_wait(s.done,s.advance_wait)){s.advance_timeout=1;return 1;}
  }
  if(s.reenter_at&&s.polls==s.reenter_at&&!s.reentered&&s.nested){
    s.reentered=true;
    s.reenter_status=(int)reader_annotation_export_run(s.nested,s.nested_stats,s.nested_error);
  }
  return s.cancel_after&&s.polls>=s.cancel_after;
}
int receive_batch(const std::string &db,const std::string &batch){
  reader_revisions *store=nullptr;reader_revision_error e{};
  if(reader_revisions_open(db.c_str(),&store,&e)!=READER_REV_OK){std::printf("{\"status\":1,\"message\":%s}\n",esc(e.message).c_str());return 0;}
  std::ifstream in(batch,std::ios::binary);
  std::string data((std::istreambuf_iterator<char>(in)),std::istreambuf_iterator<char>());
  size_t accepted=0,created=0,line=0,pos=0;std::string rejected="[";
  while(pos<data.size()){
    size_t end=data.find('\n',pos);if(end==std::string::npos)end=data.size();
    std::string row=data.substr(pos,end-pos);pos=end+1;++line;
    std::string sha=row.substr(0,64),wire=row.substr(65);int made=0;reader_revision_info info{};reader_revision_error re{};
    reader_revision_status s=reader_revision_receive(store,wire.data(),wire.size(),sha.c_str(),&info,&made,&re);
    if(s==READER_REV_OK){++accepted;created+=(size_t)made;}
    else{if(rejected.size()>1)rejected+=",";rejected+="{\"line\":"+std::to_string(line)+",\"status\":"+std::to_string((int)s)+",\"message\":"+esc(re.message)+"}";}
  }
  rejected+="]";
  reader_revisions_close(&store,&e);
  std::printf("{\"status\":0,\"accepted\":%zu,\"created\":%zu,\"lines\":%zu,\"rejected\":%s}\n",accepted,created,line,rejected.c_str());
  return 0;
}
int do_export(int argc,char **argv){
  if(argc<8){std::fprintf(stderr,"usage\n");return 2;}
  std::string db=argv[2],book=argv[3],title=unhex(argv[4]),jsonl=unhex(argv[5]),md=unhex(argv[6]);
  unsigned long long max_bytes=std::strtoull(argv[7],nullptr,10);
  poll_state ps;std::map<std::string,std::string> opt;
  for(int i=8;i<argc;i++){std::string a=argv[i];size_t eq=a.find('=');opt[a.substr(0,eq)]=a.substr(eq+1);}
  if(opt.count("cancel_after"))ps.cancel_after=std::strtoul(opt["cancel_after"].c_str(),nullptr,10);
  if(opt.count("fsize"))ps.fsize=std::atoll(opt["fsize"].c_str());
  reader_revisions *store=nullptr;reader_revision_error e{};
  if(reader_revisions_open(db.c_str(),&store,&e)!=READER_REV_OK){std::printf("{\"status\":-1,\"message\":%s}\n",esc(e.message).c_str());return 0;}
  reader_annotation_export_options o{};o.struct_size=opt.count("short_struct")?1:sizeof(o);o.revisions=store;o.book_key=book.c_str();
  o.book_title=title.empty()&&std::string(argv[4])=="-"?nullptr:title.c_str();
  o.jsonl_path=std::string(argv[5])=="-"?nullptr:jsonl.c_str();o.markdown_path=std::string(argv[6])=="-"?nullptr:md.c_str();
  o.max_output_bytes=max_bytes;o.cancel=poll;o.cancel_context=&ps;
  reader_annotation_export_stats st{};reader_annotation_export_error er{};
  if(opt.count("advance_at_poll")){
    ps.advance_at=std::strtoul(opt["advance_at_poll"].c_str(),nullptr,10);
    ps.go=unhex(opt.count("go")?opt["go"]:"-");ps.done=unhex(opt.count("done")?opt["done"]:"-");
    if(opt.count("advance_wait"))ps.advance_wait=std::atoi(opt["advance_wait"].c_str());
  }
  reader_annotation_export_options nested{};reader_annotation_export_stats nested_stats{};reader_annotation_export_error nested_error{};
  std::string nested_path=unhex(opt.count("reenter_path")?opt["reenter_path"]:"-");
  if(opt.count("reenter")){
    nested.struct_size=sizeof(nested);nested.revisions=store;nested.book_key=book.c_str();
    nested.book_title=o.book_title;nested.jsonl_path=nested_path.empty()?nullptr:nested_path.c_str();
    ps.nested=&nested;ps.nested_error=&nested_error;
    ps.nested_stats=opt.count("reenter_stats")?&st:&nested_stats;
    ps.reenter_at=opt.count("reenter_at")?std::strtoul(opt["reenter_at"].c_str(),nullptr,10):2;
  }
  std::string lock_note;
#ifdef _WIN32
  HANDLE lock=INVALID_HANDLE_VALUE;
  if(opt.count("lock")){std::string p=unhex(opt["lock"]);int n=MultiByteToWideChar(CP_UTF8,0,p.c_str(),-1,nullptr,0);std::wstring w((size_t)n,L'\0');
    MultiByteToWideChar(CP_UTF8,0,p.c_str(),-1,&w[0],n);lock=CreateFileW(w.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(lock==INVALID_HANDLE_VALUE){std::printf("{\"status\":-1,\"message\":\"lock failed\"}\n");return 0;}}
#else
  if(opt.count("lock"))lock_note="lock is Windows-only";
#endif
  reader_annotation_export_status status;
  if(opt.count("null_options"))status=reader_annotation_export_run(nullptr,&st,&er);
  else if(opt.count("thread")){std::thread t([&]{status=reader_annotation_export_run(&o,&st,&er);});t.join();}
  else status=reader_annotation_export_run(&o,&st,&er);
#ifdef _WIN32
  if(lock!=INVALID_HANDLE_VALUE)CloseHandle(lock);
#endif
  std::printf("{\"status\":%d,\"revision_code\":%d,\"rs_code\":%d,\"os_error\":%d,\"message\":%s,\"polls\":%lu,\"note\":%s,"
    "\"advanced\":%d,\"advance_timeout\":%d,"
    "\"reenter\":{\"status\":%d,\"code\":%d,\"message\":%s,\"annotations\":%llu,\"jsonl_published\":%d},"
    "\"stats\":{\"annotations\":%llu,\"current\":%llu,\"tombstones\":%llu,\"pending_parents\":%llu,\"concurrent\":%llu,\"blocked_restore\":%llu,"
    "\"head_wires\":%llu,\"jsonl_bytes\":%llu,\"markdown_bytes\":%llu,\"jsonl_published\":%d,\"markdown_published\":%d}}\n",
    (int)status,er.revision_code,er.rs_code,er.os_error,esc(er.message).c_str(),ps.polls,esc(lock_note).c_str(),
    ps.advanced?1:0,ps.advance_timeout,
    ps.reenter_status,nested_error.code,esc(nested_error.message).c_str(),
    (unsigned long long)nested_stats.annotations,nested_stats.jsonl_published,
    (unsigned long long)st.annotations,(unsigned long long)st.current,(unsigned long long)st.tombstones,(unsigned long long)st.pending_parents,
    (unsigned long long)st.concurrent,(unsigned long long)st.blocked_restore,(unsigned long long)st.head_wires,
    (unsigned long long)st.jsonl_bytes,(unsigned long long)st.markdown_bytes,st.jsonl_published,st.markdown_published);
  reader_revisions_close(&store,&e);
  return 0;
}
}  // namespace

int main(int argc,char **argv){
  if(argc>=4&&!std::strcmp(argv[1],"receive-batch"))return receive_batch(argv[2],argv[3]);
  if(argc>=2&&!std::strcmp(argv[1],"export"))return do_export(argc,argv);
  std::fprintf(stderr,"unknown action\n");return 2;
}
