// SPDX-License-Identifier: MIT
#include <exr_webdav.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <string>

extern "C" int __real_linkat(int,const char*,int,const char*,int);
extern "C" int __real_unlinkat(int,const char*,int);
static struct stat directory_identity{};
static std::string temporary_name,mode;
static int hold=-1,link_attempts=0,link_committed=0,target_unlinks=0;
static int injected=0,permission_changed=0,unlink_error=0,hook_error=0;
static bool same_at_link=false;
static bool same_directory(int fd) {
  struct stat st{};
  return fstat(fd,&st)==0 && st.st_dev==directory_identity.st_dev && st.st_ino==directory_identity.st_ino;
}
static bool temp_leaf(const char *s) {
  if(!s || std::strlen(s)!=48 || std::strncmp(s,".exr-webdav-",12)!=0 || std::strcmp(s+44,".tmp")!=0) return false;
  for(int i=12;i<44;i++) if(!std::strchr("0123456789abcdef",s[i])) return false;
  return true;
}
extern "C" int __wrap_linkat(int from,const char *oldname,int to,const char *newname,int flags) {
  const bool target=same_directory(from)&&same_directory(to)&&temp_leaf(oldname)&&newname&&std::strcmp(newname,"book.epub")==0&&flags==0;
  if(target) ++link_attempts;
  const int rc=__real_linkat(from,oldname,to,newname,flags);
  const int saved=errno;
  if(target && rc==0) {
    ++link_committed;temporary_name=oldname;
    struct stat a{},b{};
    same_at_link=fstatat(from,oldname,&a,AT_SYMLINK_NOFOLLOW)==0&&fstatat(to,newname,&b,AT_SYMLINK_NOFOLLOW)==0&&a.st_dev==b.st_dev&&a.st_ino==b.st_ino&&a.st_nlink==2;
    if(mode=="eacces_persistent") {
      if(fchmod(hold,0500)==0) permission_changed=1;else hook_error=errno;
    }
  }
  errno=saved;return rc;
}
extern "C" int __wrap_unlinkat(int fd,const char *name,int flags) {
  if(link_committed && same_directory(fd) && name && temporary_name==name && flags==0) {
    ++target_unlinks;
    if(mode=="eio_once" && injected==0) {++injected;unlink_error=EIO;errno=EIO;return -1;}
    const int rc=__real_unlinkat(fd,name,flags);
    const int saved=errno;
    if(rc!=0) unlink_error=saved;
    errno=saved;return rc;
  }
  return __real_unlinkat(fd,name,flags);
}
int main(int argc,char **argv) {
  if(argc!=4 || geteuid()==0) return 2;
  mode=argv[3];
  if(mode!="normal"&&mode!="eio_once"&&mode!="eacces_persistent"&&mode!="existing") return 2;
  hold=open(argv[2],O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
  if(hold<0 || fstat(hold,&directory_identity)!=0) return 3;
  exr_webdav_config config{};config.root_url=argv[1];config.timeout_ms=15000;
  exr_webdav_client *client=nullptr;exr_webdav_error error{};
  exr_webdav_download download{};
  auto status=exr_webdav_create(&config,&client,&error);
  if(status==EXR_DAV_OK)
    status=exr_webdav_download_file(client,"book.epub",argv[2],"book.epub",nullptr,&download,&error);
  exr_webdav_free(client);
  // The temporary destructor has run; observe residue before fixture cleanup.
  struct stat residue{},target{};
  const bool temp_exists=!temporary_name.empty()&&fstatat(hold,temporary_name.c_str(),&residue,AT_SYMLINK_NOFOLLOW)==0;
  const bool target_exists=fstatat(hold,"book.epub",&target,AT_SYMLINK_NOFOLLOW)==0;
  const bool same_inode=temp_exists&&target_exists&&residue.st_dev==target.st_dev&&residue.st_ino==target.st_ino;
  struct stat permissions{};fstat(hold,&permissions);
  const unsigned mode_before_restore=permissions.st_mode&0777;
  const bool restored=fchmod(hold,0700)==0;
  // An unrelated unlink remains real even with the target fault armed.
  int control=openat(hold,"unrelated.tmp",O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);
  bool unrelated=false;
  if(control>=0) {close(control);unrelated=__wrap_unlinkat(hold,"unrelated.tmp",0)==0;}
  std::printf("{\"source\":\"%s\",\"status\":%d,\"published\":%d,\"bytes\":%llu,"
    "\"link_attempts\":%d,\"link_committed\":%d,\"same_at_link\":%s,"
    "\"target_unlinks\":%d,\"injected\":%d,\"unlink_errno\":%d,"
    "\"permission_changed\":%d,\"hook_error\":%d,\"directory_mode_before_restore\":%u,"
    "\"restored\":%s,\"unrelated_unlink_ok\":%s,\"temp_name\":\"%s\","
    "\"temp_exists\":%s,\"same_inode\":%s,\"target_nlink\":%llu,\"uid\":%u}\n",
    SOURCE_SHA,(int)status,download.published,(unsigned long long)download.bytes,
    link_attempts,link_committed,same_at_link?"true":"false",
    target_unlinks,injected,unlink_error,permission_changed,hook_error,mode_before_restore,
    restored?"true":"false",unrelated?"true":"false",temporary_name.c_str(),
    temp_exists?"true":"false",same_inode?"true":"false",(unsigned long long)target.st_nlink,(unsigned)geteuid());
  close(hold);
  return restored&&unrelated&&!hook_error?0:4;
}
