/* SPDX-License-Identifier: MIT */
#define _GNU_SOURCE 1
#define _DARWIN_C_SOURCE 1
#include "pc02_io.h"
#include "../../src/lm.h"
#include <sys/stat.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <string.h>
#include <stdio.h>
#ifdef __APPLE__
#include <sys/acl.h>
#endif
int pc02io_same(const pc02_identity *a,const pc02_identity *b){return a->device==b->device&&a->inode==b->inode;
}
void pc02io_put64(unsigned char *p,uint64_t n){for(unsigned k=0;k<8;k++){p[k]=(unsigned char)n;
n>>=8;
}}
uint64_t pc02io_get64(const unsigned char *p){uint64_t n=0;
for(unsigned k=0;k<8;k++)n|=(uint64_t)p[k]<<(8*k);
return n;
}
void pc02io_putid(unsigned char *p,const pc02_identity *id){pc02io_put64(p,id->device);
pc02io_put64(p+8,id->inode);
}
pc02_identity pc02io_getid(const unsigned char *p){pc02_identity id={pc02io_get64(p),pc02io_get64(p+8)};
return id;
}
static int acl_clear(int fd){
#ifdef __APPLE__
 acl_t acl=acl_get_fd_np(fd,ACL_TYPE_EXTENDED);
 if(!acl)return errno==ENOENT;
 acl_entry_t entry;
 int which=ACL_FIRST_ENTRY,ok=acl_valid(acl)==0;
 while(ok){
  errno=0;
  int result=acl_get_entry(acl,which,&entry);
  if(result==-1){if(errno!=EINVAL)ok=0;
  break;
  }
  if(result!=0){ok=0;
  break;
  }
  which=ACL_NEXT_ENTRY;
  acl_tag_t tag;
  if(acl_get_tag_type(entry,&tag)||tag!=ACL_EXTENDED_DENY){ok=0;
  break;
  }
 }
 if(acl_free(acl))ok=0;
 return ok;
#else
 (void)fd;
 return 1;
#endif
}
int pc02io_identity(int fd,int directory,int private_mode,pc02_identity *id){
 struct stat s;
 if(fstat(fd,&s)||!acl_clear(fd)||s.st_uid!=geteuid()||
    (directory?!S_ISDIR(s.st_mode):(!S_ISREG(s.st_mode)||s.st_nlink!=1))||
    (private_mode?(s.st_mode&07777)!=(directory?0700:0600):(s.st_mode&0022)!=0))return 0;
 id->device=(uint64_t)s.st_dev;
 id->inode=(uint64_t)s.st_ino;
 return 1;
}
static int times_equal(const struct stat *a,const struct stat *b){
#ifdef __APPLE__
 return a->st_mtimespec.tv_sec==b->st_mtimespec.tv_sec&&a->st_mtimespec.tv_nsec==b->st_mtimespec.tv_nsec&&
  a->st_ctimespec.tv_sec==b->st_ctimespec.tv_sec&&a->st_ctimespec.tv_nsec==b->st_ctimespec.tv_nsec;
#else
 return a->st_mtim.tv_sec==b->st_mtim.tv_sec&&a->st_mtim.tv_nsec==b->st_mtim.tv_nsec&&
  a->st_ctim.tv_sec==b->st_ctim.tv_sec&&a->st_ctim.tv_nsec==b->st_ctim.tv_nsec;
#endif
}
int pc02io_hash(int fd,pc02_file *out){
 struct stat before,after;
 pc02_identity id,check;
 unsigned char bytes[65536];
 uint64_t at=0;
 lm_sha hash;
 memset(out,0,sizeof(*out));
 if(!pc02io_identity(fd,0,0,&id)||fstat(fd,&before)||before.st_size<0)return 0;
 lm_sha_init(&hash);
 while(at<(uint64_t)before.st_size){
  size_t size=(size_t)(((uint64_t)before.st_size-at)>sizeof(bytes)?sizeof(bytes):((uint64_t)before.st_size-at));
  ssize_t n=pread(fd,bytes,size,(off_t)at);
  if(n<0&&errno==EINTR)continue;
  if(n<=0)return 0;
  lm_sha_add(&hash,bytes,(size_t)n);
  at+=(uint64_t)n;
 }
 if(!pc02io_identity(fd,0,0,&check)||!pc02io_same(&id,&check)||fstat(fd,&after)||
    after.st_size!=before.st_size||!times_equal(&before,&after))return 0;
 pc02io_putid(out->identity,&id);
 pc02io_put64(out->size,at);
 lm_sha_hex(&hash,out->sha);
 return 1;
}
int pc02io_equal(const pc02_file *a,const pc02_file *b){return !memcmp(a,b,sizeof(*a));
}
int pc02io_match(int parent,const char *leaf,const pc02_file *expected){
 int fd=openat(parent,leaf,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
 pc02_file actual;
 struct stat s;
 int ok=fd>=0&&pc02io_hash(fd,&actual)&&
 pc02io_equal(&actual,expected)&&!fstatat(parent,leaf,&s,AT_SYMLINK_NOFOLLOW)&&S_ISREG(s.st_mode)&&
 (uint64_t)s.st_dev==pc02io_get64(expected->identity)&&(uint64_t)s.st_ino==pc02io_get64(expected->identity+8);
 if(fd>=0&&close(fd))ok=0;
 return ok;
}
int pc02io_absent(int parent,const char *leaf){struct stat s;
return fstatat(parent,leaf,&s,AT_SYMLINK_NOFOLLOW)<0&&errno==ENOENT;
}
int pc02io_quiet(int parent,const char *leaf){
 const char *suffix[]={"-wal","-shm","-journal"};
 char path[512];
 for(unsigned k=0;k<3;k++){
  int n=snprintf(path,sizeof(path),"%s%s",leaf,suffix[k]);
  if(n<=0||(size_t)n>=sizeof(path)||!pc02io_absent(parent,path))return 0;
 }
 return 1;
}
int pc02io_copy(int source,int destination,const pc02_file *expected){
 pc02_file before,after,copied;
 struct stat st;
 unsigned char bytes[65536];
 uint64_t at=0,total=pc02io_get64(expected->size);
 if(!pc02io_hash(source,&before)||!pc02io_equal(&before,expected)||fstat(destination,&st)||st.st_size)return 0;
 while(at<total){
  size_t n=(size_t)((total-at)>sizeof(bytes)?sizeof(bytes):total-at);
  ssize_t got=pread(source,bytes,n,(off_t)at);
  if(got<0&&errno==EINTR)continue;
  if(got<=0)return 0;
  size_t written=0;
  while(written<(size_t)got){ssize_t put=pwrite(destination,bytes+written,(size_t)got-written,(off_t)(at+written));
   if(put<0&&errno==EINTR)continue;
   if(put<=0)return 0;
   written+=(size_t)put;
   }
  at+=(uint64_t)got;
 }
 if(fsync(destination)||!pc02io_hash(source,&after)||!pc02io_equal(&after,expected)||!pc02io_hash(destination,&copied))return 0;
 return !memcmp(copied.size,expected->size,8)&&!strcmp(copied.sha,expected->sha);
}
int pc02io_leaf(const char *p){
 size_t n=p?strlen(p):0;
 if(!n||n>255||!strcmp(p,".")||!strcmp(p,".."))return 0;
 for(size_t k=0;k<n;k++)if(!((p[k]>='a'&&p[k]<='z')||(p[k]>='A'&&p[k]<='Z')||
  (p[k]>='0'&&p[k]<='9')||p[k]=='.'||p[k]=='_'||p[k]=='-'))return 0;
 return 1;
}
