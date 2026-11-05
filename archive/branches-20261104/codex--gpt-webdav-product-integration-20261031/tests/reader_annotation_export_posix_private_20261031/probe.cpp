// SPDX-License-Identifier: MIT
// Installed production module; no product hooks and no payload reads by exec child.
#include <reader_annotation_export.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <dirent.h>
#include <fcntl.h>
#include <unistd.h>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
struct State {
  std::string self,dir;
  bool cancel=false,checked=false,ok=true;
  unsigned temps=0,exec_checks=0;
};
static int scan(unsigned long long dev,unsigned long long ino) {
  long limit=sysconf(_SC_OPEN_MAX);
  if(limit<0 || limit>65536)limit=65536;
  for(int fd=0;fd<limit;fd++){
    struct stat s{};
    if(fstat(fd,&s)==0 && (unsigned long long)s.st_dev==dev &&
       (unsigned long long)s.st_ino==ino)return 42;
  }
  return 0;
}
static int child(const std::string &self,const struct stat &s) {
  std::string d=std::to_string((unsigned long long)s.st_dev);
  std::string i=std::to_string((unsigned long long)s.st_ino);
  pid_t pid=fork();
  if(pid<0)return -1;
  if(!pid){execl(self.c_str(),self.c_str(),"--scan",d.c_str(),i.c_str(),(char*)nullptr);_exit(127);}
  int status=0;
  while(waitpid(pid,&status,0)<0){if(errno!=EINTR)return -1;}
  return WIFEXITED(status)?WEXITSTATUS(status):-1;
}
static int poll(void *p) {
  State &s=*static_cast<State*>(p);
  if(!s.checked){
    s.checked=true;
    DIR *dir=opendir(s.dir.c_str());
    if(!dir){s.ok=false;return 1;}
    while(auto *entry=readdir(dir)){
      if(std::strncmp(entry->d_name,".exr-export-",12))continue;
      std::string path=s.dir+"/"+entry->d_name;
      struct stat st{};
      if(lstat(path.c_str(),&st) || !S_ISREG(st.st_mode) || (st.st_mode&0777)!=0600){s.ok=false;continue;}
      ++s.temps;
      bool found=false;
      long limit=sysconf(_SC_OPEN_MAX);if(limit<0 || limit>65536)limit=65536;
      for(int fd=0;fd<limit;fd++){
        struct stat actual{};
        if(fstat(fd,&actual)==0 && actual.st_dev==st.st_dev && actual.st_ino==st.st_ino){
          found=true;
          int flags=fcntl(fd,F_GETFD);
          if(flags<0 || !(flags&FD_CLOEXEC))s.ok=false;
        }
      }
      if(!found || child(s.self,st)!=0)s.ok=false;
      ++s.exec_checks;
    }
    closedir(dir);
    if(s.temps!=2)s.ok=false;
  }
  return !s.ok || s.cancel;
}
int main(int argc,char **argv){
  if(argc==4 && !std::strcmp(argv[1],"--scan"))
    return scan(std::strtoull(argv[2],nullptr,10),std::strtoull(argv[3],nullptr,10));
  if(argc!=7)return 2;
  // Prove the exec observer detects a genuinely inherited descriptor first.
  std::string control=std::string(argv[2])+"/inherit-control";
  int fd=open(control.c_str(),O_RDWR|O_CREAT|O_EXCL,0600);struct stat st{};
  if(fd<0 || fstat(fd,&st))return 3;
  bool detector=child(argv[1],st)==42 && fcntl(fd,F_SETFD,FD_CLOEXEC)==0 && child(argv[1],st)==0;
  close(fd);unlink(control.c_str());if(!detector)return 4;
  State state;state.self=argv[1];state.dir=argv[2];state.cancel=!std::strcmp(argv[6],"cancel");
  reader_revisions *r=nullptr;reader_revision_error re{};
  if(reader_revisions_open(argv[3],&r,&re)!=READER_REV_OK)return 5;
  std::string json=state.dir+"/output.jsonl",md=state.dir+"/output.md";
  reader_annotation_export_options o{};o.struct_size=sizeof(o);o.revisions=r;o.book_key=argv[4];
  o.jsonl_path=json.c_str();o.markdown_path=md.c_str();o.cancel=poll;o.cancel_context=&state;
  if(!std::strcmp(argv[6],"budget"))o.max_output_bytes=1;
  mode_t old=umask((mode_t)std::strtoul(argv[5],nullptr,8));
  reader_annotation_export_stats stats{};reader_annotation_export_error error{};
  auto status=reader_annotation_export_run(&o,&stats,&error);umask(old);
  reader_revisions_close(&r,&re);
  bool budget=!std::strcmp(argv[6],"budget");
  bool pass=state.ok && (budget || (state.checked && state.temps==2 && state.exec_checks==2));
  if(state.cancel)pass=pass && status==READER_ANNOTATION_EXPORT_CANCELLED && !stats.jsonl_published && !stats.markdown_published;
  else if(budget)pass=pass && status==READER_ANNOTATION_EXPORT_LIMIT && !stats.jsonl_published && !stats.markdown_published;
  else pass=pass && status==READER_ANNOTATION_EXPORT_OK && stats.jsonl_published && stats.markdown_published;
  std::printf("{\"source\":\"%s\",\"passed\":%s,\"status\":%d,\"temps\":%u,\"exec_checks\":%u,\"detector_control\":true,\"annotations\":%llu}\n",
    SOURCE_SHA,pass?"true":"false",(int)status,state.temps,state.exec_checks,(unsigned long long)stats.annotations);
  return pass?0:6;
}
