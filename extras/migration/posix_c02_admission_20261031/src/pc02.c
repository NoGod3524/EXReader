/* SPDX-License-Identifier: MIT */
#define _GNU_SOURCE 1
#define _DARWIN_C_SOURCE 1
#include "exr_pc02.h"
#include <exr_wh.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/file.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
#ifdef __APPLE__
#include <TargetConditionals.h>
#include <sys/acl.h>
#endif
#ifndef O_CLOEXEC
#define O_CLOEXEC 0
#endif
#define PINS 128u
#define PATH_CAP 4096u
#define B_BYTES 304u
#define B_SEAL 240u
#define S_BYTES 368u
#define S_SEAL 304u
#define A_BYTES 120u
#define A_SEAL 56u
/* ponytail: bounded append-only authority; a new qualified checkpoint is needed
   after 2047 transactions. Refuse begin before consuming finish capacity. */
#define MAX_STATES 4096u
typedef struct {int fd;
 pc02_identity id;
 char path[PATH_CAP];
 } pin;
typedef struct {unsigned char kind;
 uint64_t sequence,generation;
 char seal[65],previous_clean[65],terminal[65];
 pc02_identity target;
 pc02_pending_record pending;
 } state;
struct pc02_scope {int fd;pc02_identity id;mode_t mode;char path[PATH_CAP];};
struct pc02_cap {struct pc02_cap *next;struct pc02_lease *owner;
 uint64_t generation;
 char seal[65];
 };
struct pc02_lease {
 pin pins[PINS];
 unsigned pin_count,mode,borrows;
 int root,parent,route_dir,registry,authority_file,lease_file,state_file,binding_file,target_file,scope_file;
 int active,poisoned,transition;
 pc02_identity root_id,parent_id,route_id,lease_id,state_id,binding_id,authority_id,registry_id;
 char root_path[PATH_CAP],library[PATH_CAP],leaf[256],route[65],scope_path[PATH_CAP];
 pc02_identity scope_id;
 mode_t scope_mode;
 unsigned char binding[B_BYTES],anchor[A_BYTES];
 state seen;
 pc02_controls controls;
 struct pc02_cap *caps,*current;
};
static void put64(unsigned char *p,uint64_t n){unsigned k;
 for(k=0;
 k<8;
 k++){p[k]=(unsigned char)n;
 n>>=8;
 }}
static uint64_t get64(const unsigned char *p){unsigned k;
 uint64_t n=0;
 for(k=0;
 k<8;
 k++)n|=(uint64_t)p[k]<<(8*k);
 return n;
 }
static void putid(unsigned char *p,const pc02_identity *id){put64(p,id->device);
 put64(p+8,id->inode);
 }
static pc02_identity getid(const unsigned char *p){pc02_identity id={get64(p),get64(p+8)};
 return id;
 }
static int sameid(const pc02_identity *a,const pc02_identity *b){return a->device==b->device&&a->inode==b->inode;
 }
static int hex64(const char *s){unsigned k;
 if(!s)return 0;
 for(k=0;
 k<64;
 k++)if(!((s[k]>='0'&&s[k]<='9')||(s[k]>='a'&&s[k]<='f')))return 0;
 return !s[64];
 }
static int nonzero(const char *s){unsigned k;
 if(!hex64(s))return 0;
 for(k=0;
 k<64;
 k++)if(s[k]!='0')return 1;
 return 0;
 }
static void zero_sha(char out[65]){memset(out,'0',64);
 out[64]=0;
 }
static void id_from_stat(const struct stat *s,pc02_identity *id){id->device=(uint64_t)s->st_dev;
 id->inode=(uint64_t)s->st_ino;
 }
static int access_acl(int fd){
#if defined(__APPLE__)
 acl_t acl=acl_get_fd_np(fd,ACL_TYPE_EXTENDED);
 if(!acl)return errno==ENOENT;
 acl_entry_t entry;int which=ACL_FIRST_ENTRY,result=0,ok=1;
 while((result=acl_get_entry(acl,which,&entry))==1){
  acl_tag_t tag;which=ACL_NEXT_ENTRY;
  if(acl_get_tag_type(entry,&tag)||tag!=ACL_EXTENDED_DENY){ok=0;break;}
 }
 if(result<0)ok=0;
 acl_free(acl);
 return ok;
#else
 (void)fd;return 1;
#endif
}
static int metadata(int fd,int directory,int private_mode,pc02_identity *id){
 struct stat s;
 if(fstat(fd,&s)||!access_acl(fd)||(directory?!S_ISDIR(s.st_mode):!S_ISREG(s.st_mode)))return 0;
 if(directory){
  if(private_mode){if(s.st_uid!=geteuid()||(s.st_mode&07777)!=0700)return 0;
 }
  else if((s.st_uid!=geteuid()&&s.st_uid!=0)||(s.st_mode&0022))return 0;
 }else if(s.st_uid!=geteuid()||s.st_nlink!=1||
    (private_mode?(s.st_mode&07777)!=0600:(s.st_mode&0022)!=0))return 0;
 if(id)id_from_stat(&s,id);
 return 1;
}
static int io_read(int fd,void *data,size_t n,off_t at){
 unsigned char *p=data;
 while(n){ssize_t r=pread(fd,p,n,at);
 if(r<0&&errno==EINTR)continue;
 if(r<=0)return 0;
 p+=r;
 n-=(size_t)r;
 at+=r;
 }return 1;
}
static int io_write(int fd,const void *data,size_t n,off_t at){
 const unsigned char *p=data;
 while(n){ssize_t r=pwrite(fd,p,n,at);
 if(r<0&&errno==EINTR)continue;
 if(r<=0)return 0;
 p+=r;
 n-=(size_t)r;
 at+=r;
 }return 1;
}
static int size_exact(int fd,off_t expected){struct stat s;
 return !fstat(fd,&s)&&s.st_size==expected;
 }
static int safe_path(const char *path){
 size_t n,k,start;
 if(!path||(n=strlen(path))<2||n>=PATH_CAP||path[0]!='/'||path[n-1]=='/')return 0;
 start=1;
 for(k=1;
 k<=n;
 k++)if(path[k]=='/'||!path[k]){
  size_t len=k-start;
 if(!len||(len==1&&path[start]=='.')||(len==2&&path[start]=='.'&&path[start+1]=='.'))return 0;
  start=k+1;
 }return 1;
}
static int leaf_ok(const char *leaf){
 size_t k,n=strlen(leaf);
 if(!n||n>=256||leaf[n-1]=='.'||leaf[n-1]==' ')return 0;
 if(!strcmp(leaf,".")||!strcmp(leaf,".."))return 0;
 for(k=0;
 k<n;
 k++){char c=leaf[k];
 if(!((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='.'||c=='_'||c=='-'))return 0;
 }
 return 1;
}
static int authority_current(pc02_lease *h);
static int duplicate_fd(int fd){
#ifdef F_DUPFD_CLOEXEC
 return fcntl(fd,F_DUPFD_CLOEXEC,3);
#else
 int copy=fcntl(fd,F_DUPFD,3);
 if(copy>=0&&fcntl(copy,F_SETFD,FD_CLOEXEC)){close(copy);
 return -1;
 }
 return copy;
#endif
}
static int relative_valid(const char *path){
 size_t k,n,start=0;
 if(!path||!(n=strlen(path))||n>=PATH_CAP||path[0]=='/'||path[n-1]=='/')return 0;
 for(k=0;
 k<=n;
 k++)if(!path[k]||path[k]=='/'){
  size_t length=k-start;
  if(!length||length>255||(length==1&&path[start]=='.')||
     (length==2&&path[start]=='.'&&path[start+1]=='.'))return 0;
  start=k+1;
 }
 return 1;
}
static int directory_path(int fd,char path[PATH_CAP]){
 pc02_identity original,observed;
 if(!metadata(fd,1,0,&original))return 0;
#ifdef __APPLE__
 if(fcntl(fd,F_GETPATH,path))return 0;
#else
 char descriptor[64];
 ssize_t n;
 if(snprintf(descriptor,sizeof(descriptor),"/proc/self/fd/%d",fd)>=(int)sizeof(descriptor))return 0;
 n=readlink(descriptor,path,PATH_CAP-1);
 if(n<=0||(size_t)n>=PATH_CAP-1)return 0;
 path[n]=0;
#endif
 if(!safe_path(path))return 0;
 int probe=open(path,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
 if(probe<0)return 0;
 int ok=metadata(probe,1,0,&observed)&&sameid(&original,&observed);
 close(probe);
 return ok;
}
static int scope_metadata(int fd,pc02_identity *id,mode_t *mode){
 struct stat s;
 if(!metadata(fd,1,0,id)||fstat(fd,&s)||s.st_uid!=geteuid()||
    (s.st_mode&07022)||(s.st_mode&0700)!=0700)return 0;
 if(mode)*mode=s.st_mode&07777;
 return 1;
}
static int scope_current(int fd,const pc02_identity *expected,mode_t mode,const char *path){
 pc02_identity actual;mode_t observed;
 char physical[PATH_CAP];
 return scope_metadata(fd,&actual,&observed)&&observed==mode&&sameid(&actual,expected)&&
 directory_path(fd,physical)&&!strcmp(path,physical);
}
int pc02_scope_create(int trusted,const pc02_identity *expected,pc02_scope **out){
 pc02_scope *scope=NULL;
 pc02_identity actual;
 int copy=-1;
 if(out)*out=NULL;
 if(!out||!expected)return 0;
 copy=duplicate_fd(trusted);
 mode_t mode;
 if(copy<0||!scope_metadata(copy,&actual,&mode)||!sameid(&actual,expected))goto fail;
 scope=calloc(1,sizeof(*scope));
 if(!scope)goto fail;
 scope->fd=copy;
 scope->id=actual;
 scope->mode=mode;
 if(!directory_path(copy,scope->path)||!scope_current(copy,&scope->id,scope->mode,scope->path))goto fail;
 *out=scope;
 return 1;
fail:
 if(copy>=0)close(copy);
 free(scope);
 return 0;
}
int pc02_scope_close(pc02_scope *scope){
 if(!scope)return 1;
 close(scope->fd);
 free(scope);
 return 1;
}
static const char *scope_relative(pc02_lease *h,const char *path){
 size_t n=strlen(h->scope_path);
 if(strncmp(path,h->scope_path,n)|| (path[n]&&path[n]!='/'))return NULL;
 const char *relative=path+n+(path[n]=='/');
 if(relative[0]&&!relative_valid(relative))return NULL;
 return relative;
}
static int scope_directory(pc02_lease *h,const char *path){
 const char *relative=scope_relative(h,path);
 char component[256];
 size_t at=0;
 if(!relative)return -1;
 int current=duplicate_fd(h->scope_file);
 if(current<0)return -1;
 while(relative[at]){
  size_t end=at;
 while(relative[end]&&relative[end]!='/')end++;
  memcpy(component,relative+at,end-at);
 component[end-at]=0;
  int next=openat(current,component,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
  close(current);
 current=next;
  if(current<0)return -1;
  if(!metadata(current,1,0,NULL)){close(current);
 return -1;
 }
  at=end+(relative[end]=='/');
 }
 return current;
}
static int add_scope_pin(pc02_lease *h,int fd,const char *path,int private_mode){
 pc02_identity id;
 if(h->pin_count>=PINS||!metadata(fd,1,private_mode,&id)){close(fd);
 return -1;
 }
 h->pins[h->pin_count].fd=fd;
 h->pins[h->pin_count].id=id;
 strcpy(h->pins[h->pin_count].path,path);
 h->pin_count++;
 return fd;
}
static int pin_scope_chain(pc02_lease *h,const char *path,int final_private){
 const char *relative=scope_relative(h,path);
 char component[256],prefix[PATH_CAP];
 size_t at=0,n;
 if(!relative||!scope_current(h->scope_file,&h->scope_id,h->scope_mode,h->scope_path))return -1;
 int current=duplicate_fd(h->scope_file);
 if(current<0)return -1;
 if(add_scope_pin(h,current,h->scope_path,0)<0)return -1;
 strcpy(prefix,h->scope_path);
 n=strlen(prefix);
 while(relative[at]){
  size_t end=at;
 while(relative[end]&&relative[end]!='/')end++;
  memcpy(component,relative+at,end-at);
 component[end-at]=0;
  int next=openat(current,component,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
  if(next<0)return -1;
  if(n+1+end-at>=sizeof(prefix)){close(next);
 return -1;
 }
  prefix[n++]='/';
 memcpy(prefix+n,component,end-at+1);
 n+=end-at;
  if(add_scope_pin(h,next,prefix,relative[end]?0:final_private)<0)return -1;
  current=next;
 at=end+(relative[end]=='/');
 }
 return current;
}
static int scoped_pins_current(pc02_lease *h){
 if(!scope_current(h->scope_file,&h->scope_id,h->scope_mode,h->scope_path))return 0;
 for(unsigned k=0;
 k<h->pin_count;
 k++){
  pc02_identity actual;
  if(!metadata(h->pins[k].fd,1,0,&actual)||!sameid(&actual,&h->pins[k].id))return 0;
  int fd=scope_directory(h,h->pins[k].path);
 if(fd<0)return 0;
  int ok=metadata(fd,1,0,&actual)&&sameid(&actual,&h->pins[k].id);
  close(fd);
 if(!ok)return 0;
 }
 return metadata(h->root,1,1,NULL)&&authority_current(h);
}
static int pin_dir(pc02_lease *h,const char *path,int private_mode){
 int fd;
 pc02_identity id;
 if(h->pin_count>=PINS)return -1;
 fd=open(path,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
 if(fd<0||!metadata(fd,1,private_mode,&id)){if(fd>=0)close(fd);
 return -1;
 }
 h->pins[h->pin_count].fd=fd;
 h->pins[h->pin_count].id=id;
 strcpy(h->pins[h->pin_count].path,path);
 h->pin_count++;
 return fd;
}
static int pin_chain(pc02_lease *h,const char *path,int final_private){
 if(h->scope_file>=0)return pin_scope_chain(h,path,final_private);
 size_t k,n=strlen(path);
 char prefix[PATH_CAP];
 int fd=-1;
 if(path[0]!='/'||n>=PATH_CAP)return -1;
 fd=pin_dir(h,"/",0);
 if(fd<0)return -1;
 if(n==1)return final_private?-1:fd;
 for(k=1;
 k<=n;
 k++)if(k==n||path[k]=='/'){
  if(k==1)continue;
 memcpy(prefix,path,k);
 prefix[k]=0;
  fd=pin_dir(h,prefix,k==n?final_private:0);
 if(fd<0)return -1;
 }return fd;
}
static int pins_current(pc02_lease *h){
 if(h->scope_file>=0)return scoped_pins_current(h);
 unsigned k;
 for(k=0;
 k<h->pin_count;
 k++){
  int fd;
 pc02_identity actual;
  if(!metadata(h->pins[k].fd,1,0,&actual)||!sameid(&actual,&h->pins[k].id))return 0;
  fd=open(h->pins[k].path,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
  if(fd<0)return 0;
  int ok=metadata(fd,1,0,&actual)&&sameid(&actual,&h->pins[k].id);
 close(fd);
 if(!ok)return 0;
 }
 return metadata(h->root,1,1,NULL)&&authority_current(h);
}
static int entry_id(int directory,const char *leaf,int fd,int private_mode,pc02_identity *id){
 struct stat path;
 pc02_identity a,b;
 if(!metadata(fd,0,private_mode,&a)||
  fstatat(directory,leaf,&path,AT_SYMLINK_NOFOLLOW)||!S_ISREG(path.st_mode))return 0;
 id_from_stat(&path,&b);
 if(!sameid(&a,&b))return 0;
 if(id)*id=a;
 return 1;
}
static int authority_current(pc02_lease *h){
 pc02_identity actual;
 unsigned char bytes[A_BYTES];
 if(h->authority_file<0)return 1;
 return entry_id(h->root,"authority",h->authority_file,1,&actual)&&sameid(&actual,&h->authority_id)&&
 size_exact(h->authority_file,A_BYTES)&&io_read(h->authority_file,bytes,A_BYTES,0)&&!memcmp(bytes,h->anchor,A_BYTES)&&
 entry_id(h->root,"registry.lock",h->registry,1,&actual)&&sameid(&actual,&h->registry_id)&&size_exact(h->registry,16);
}
static int regular_open(int directory,const char *leaf,int flags,int private_mode,pc02_identity *id){
 int fd=openat(directory,leaf,flags|O_NOFOLLOW|O_CLOEXEC,0600);
 if(fd<0)return -1;
 if(!entry_id(directory,leaf,fd,private_mode,id)){close(fd);
 errno=EINVAL;
 return -1;
 }return fd;
}
static int missing(int directory,const char *leaf){struct stat s;
 return fstatat(directory,leaf,&s,AT_SYMLINK_NOFOLLOW)<0&&errno==ENOENT;
 }
static int sealed(const unsigned char *bytes,size_t seal,const char *magic){
 char sha[65];
 if(memcmp(bytes,magic,8))return 0;
 wh_sha256_hex(bytes,seal,sha);
 return !memcmp(bytes+seal,sha,64);
}
static void seal(unsigned char *bytes,size_t at){char sha[65];
 wh_sha256_hex(bytes,at,sha);
 memcpy(bytes+at,sha,64);
 }
static int read_record(int fd,unsigned char *bytes,size_t n){return size_exact(fd,(off_t)n)&&io_read(fd,bytes,n,0);
 }
static void phase(pc02_lease *h,unsigned at){if(h->controls.phase)h->controls.phase(h->controls.context,at);
 }
static int sync_controlled(pc02_lease *h,int fd,unsigned at){
 if(h->controls.fault==PC02_SYNC_FAIL&&h->controls.fault_phase==at)return 0;
 return fsync(fd)==0;
}
static int legacy_clear(pc02_lease *h){
 static const char *suffix[]={".migration-recovery",".migration-pending.json",".migrate-lock"};
 unsigned k;
 char name[320];
 for(k=0;
 k<3;
 k++){if(snprintf(name,sizeof(name),"%s%s",h->leaf,suffix[k])>=(int)sizeof(name)||!missing(h->parent,name))return 0;
 }return 1;
}
static pc02_lease *allocate(void){
 pc02_lease *h=calloc(1,sizeof(*h));
 if(!h)return NULL;
 h->root=h->parent=h->route_dir=h->registry=h->authority_file=h->lease_file=h->state_file=h->binding_file=h->target_file=h->scope_file=-1;
 return h;
}
static pc02_lease *allocate_in(pc02_scope *scope){
 if(!scope||!scope_current(scope->fd,&scope->id,scope->mode,scope->path))return NULL;
 pc02_lease *h=allocate();
 if(!h)return NULL;
 h->scope_file=duplicate_fd(scope->fd);
 if(h->scope_file<0){free(h);
 return NULL;
 }
 h->scope_id=scope->id;
 h->scope_mode=scope->mode;
 strcpy(h->scope_path,scope->path);
 return h;
}
static int scope_join(pc02_scope *scope,const char *relative,char path[PATH_CAP]){
 if(!scope||!scope_current(scope->fd,&scope->id,scope->mode,scope->path)||!relative_valid(relative))return 0;
 size_t a=strlen(scope->path),b=strlen(relative);
 if(a+b+2>PATH_CAP)return 0;
 memcpy(path,scope->path,a);
 path[a]='/';
 memcpy(path+a+1,relative,b+1);
 return 1;
}
static int scope_paths(pc02_scope *scope,const char *authority,const char *library,
 char root[PATH_CAP],char target[PATH_CAP]){
 if(!scope_join(scope,authority,root)||!scope_join(scope,library,target))return 0;
 size_t a=strlen(authority),b=strlen(library);
 if(!strcmp(authority,library)||(a<b&&!strncmp(authority,library,a)&&library[a]=='/')||
    (b<a&&!strncmp(authority,library,b)&&authority[b]=='/'))return 0;
 return 1;
}
static void destroy(pc02_lease *h){
 unsigned k;
 if(!h)return;
 int *fds[]={&h->route_dir,&h->registry,&h->authority_file,&h->lease_file,&h->state_file,&h->binding_file,&h->target_file,&h->scope_file};
 for(k=0;
 k<sizeof(fds)/sizeof(fds[0]);
 k++)if(*fds[k]>=0)close(*fds[k]);
 for(k=0;
 k<h->pin_count;
 k++)close(h->pins[k].fd);
 while(h->caps){pc02_cap *next=h->caps->next;free(h->caps);h->caps=next;}
 free(h);
}
static int root_open(pc02_lease *h,const char *root,int exclusive){
 unsigned char anchor[A_BYTES];
 int fd;
 pc02_identity lock={0};
 if(!safe_path(root))return 0;
 strcpy(h->root_path,root);
 h->root=pin_chain(h,root,1);
 if(h->root<0||!metadata(h->root,1,1,&h->root_id))return 0;
 fd=regular_open(h->root,"authority",O_RDONLY,1,&h->authority_id);
 if(fd<0)return 0;
 h->authority_file=fd;
 int ok=read_record(fd,anchor,sizeof(anchor))&&sealed(anchor,A_SEAL,"PC02A001");
 if(!ok)return 0;
 memcpy(h->anchor,anchor,sizeof(anchor));
 pc02_identity expected=getid(anchor+8);
 if(!sameid(&expected,&h->root_id))return 0;
 h->registry=regular_open(h->root,"registry.lock",O_RDWR,1,&lock);
 h->registry_id=lock;
 expected=getid(anchor+24);
 if(h->registry<0||!sameid(&expected,&lock)||!size_exact(h->registry,16))return 0;
 unsigned char text[16];
 if(!io_read(h->registry,text,sizeof(text),0)||memcmp(text,"PC02-REGISTRY\n\0\0\0",16))return 0;
 pc02_identity self_id=getid(anchor+40);
 return sameid(&self_id,&h->authority_id)&&!flock(h->registry,(exclusive?LOCK_EX:LOCK_SH)|LOCK_NB)&&pins_current(h);
}
static int library_parent(pc02_lease *h,const char *library){
 char parent[PATH_CAP],material[320];
 const char *slash;
 size_t n,k;
 if(!safe_path(library)||(slash=strrchr(library,'/'))==NULL||!leaf_ok(slash+1))return 0;
 strcpy(h->library,library);
 strcpy(h->leaf,slash+1);
 n=(size_t)(slash-library);
 if(!n)strcpy(parent,"/");
 else{memcpy(parent,library,n);
 parent[n]=0;
 }
 unsigned prior=h->pin_count;
 h->parent=pin_chain(h,parent,0);
 if(h->parent<0||!metadata(h->parent,1,0,&h->parent_id))return 0;
 if(h->scope_file>=0)for(unsigned j=prior;j<h->pin_count;j++)if(sameid(&h->pins[j].id,&h->root_id))return 0;
 char folded[256];
 strcpy(folded,h->leaf);
 for(k=0;
 folded[k];
 k++)if(folded[k]>='A'&&folded[k]<='Z')folded[k]=(char)(folded[k]-'A'+'a');
 int bytes=snprintf(material,sizeof(material),"PC02-ROUTE1\n%016llx%016llx\n%s\n",
  (unsigned long long)h->parent_id.device,(unsigned long long)h->parent_id.inode,folded);
 if(bytes<0||(size_t)bytes>=sizeof(material))return 0;
 wh_sha256_hex(material,(size_t)bytes,h->route);
 return legacy_clear(h)&&pins_current(h);
}
static int open_route(pc02_lease *h,int create){
 if(create&&mkdirat(h->root,h->route,0700))return 0;
 h->route_dir=openat(h->root,h->route,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
 if(h->route_dir<0||!metadata(h->route_dir,1,1,&h->route_id))return 0;
 h->lease_file=regular_open(h->route_dir,"lease",O_RDWR|(create?(O_CREAT|O_EXCL):0),1,&h->lease_id);
 if(h->lease_file<0||flock(h->lease_file,(h->mode==PC02_SHARED?LOCK_SH:LOCK_EX)|LOCK_NB))return 0;
 h->state_file=regular_open(h->route_dir,"state",O_RDWR|(create?(O_CREAT|O_EXCL):0),1,&h->state_id);
 return h->state_file>=0&&pins_current(h);
}
static void binding_encode(pc02_lease *h,const state *s,unsigned char bytes[B_BYTES]){
 memset(bytes,0,B_BYTES);
 memcpy(bytes,"PC02B001",8);
 putid(bytes+8,&h->root_id);
 putid(bytes+24,&h->parent_id);
 putid(bytes+40,&s->target);
 putid(bytes+56,&h->lease_id);
 putid(bytes+72,&h->state_id);
 put64(bytes+88,s->generation);
 memcpy(bytes+96,s->seal,64);
 memcpy(bytes+160,h->route,64);
 seal(bytes,B_SEAL);
}
static int binding_valid(pc02_lease *h,const unsigned char bytes[B_BYTES]){
 pc02_identity id;
 if(!sealed(bytes,B_SEAL,"PC02B001")||memcmp(bytes+160,h->route,64))return 0;
 id=getid(bytes+8);
 if(!sameid(&id,&h->root_id))return 0;
 id=getid(bytes+24);
 if(!sameid(&id,&h->parent_id))return 0;
 id=getid(bytes+56);
 if(!sameid(&id,&h->lease_id))return 0;
 id=getid(bytes+72);
 return sameid(&id,&h->state_id);
}
static int binding_current(pc02_lease *h){
 unsigned char bytes[B_BYTES];
 pc02_identity id;
 int fd=regular_open(h->route_dir,"binding",O_RDONLY,1,&id);
 if(fd<0)return 0;
 int ok=sameid(&id,&h->binding_id)&&read_record(fd,bytes,sizeof(bytes))&&!memcmp(bytes,h->binding,sizeof(bytes));
 close(fd);
 return ok;
}
static int route_current(pc02_lease *h){
 struct stat s;
 pc02_identity id;
 if(!pins_current(h)||!metadata(h->route_dir,1,1,&id)||!sameid(&id,&h->route_id)||
 fstatat(h->root,h->route,&s,AT_SYMLINK_NOFOLLOW)||!S_ISDIR(s.st_mode))return 0;
 id_from_stat(&s,&id);
 if(!sameid(&id,&h->route_id))return 0;
 return entry_id(h->route_dir,"lease",h->lease_file,1,&id)&&sameid(&id,&h->lease_id)&&
 entry_id(h->route_dir,"state",h->state_file,1,&id)&&sameid(&id,&h->state_id)&&legacy_clear(h);
}
static void state_bytes(unsigned char bytes[S_BYTES],unsigned char kind,uint64_t sequence,uint64_t generation,
 const char *manifest,const char *input,const char *terminal,const pc02_identity *target,const char *previous){
 memset(bytes,0,S_BYTES);
 memcpy(bytes,"PC02S001",8);
 bytes[8]=kind;
 put64(bytes+16,sequence);
 put64(bytes+24,generation);
 memcpy(bytes+32,manifest,64);
 memcpy(bytes+96,input,64);
 memcpy(bytes+160,terminal,64);
 putid(bytes+224,target);
 memcpy(bytes+240,previous,64);
 seal(bytes,S_SEAL);
}
static int load_state(pc02_lease *h,state *out){
 struct stat s;
 unsigned char bytes[S_BYTES],zero[7]={0};
 state current={0};
 char last[65];
 uint64_t count,k;
 if(fstat(h->state_file,&s)||s.st_size<=0||s.st_size%(off_t)S_BYTES||s.st_size>(off_t)(S_BYTES*MAX_STATES))return 0;
 count=(uint64_t)s.st_size/S_BYTES;
 zero_sha(last);
 for(k=0;
 k<count;
 k++){
  char manifest[65],input[65],terminal[65];
 pc02_identity target;
 uint64_t generation;
  if(!io_read(h->state_file,bytes,sizeof(bytes),(off_t)(k*S_BYTES))||!sealed(bytes,S_SEAL,"PC02S001")||
   memcmp(bytes+9,zero,7)||get64(bytes+16)!=k+1||memcmp(bytes+240,last,64))return 0;
  memcpy(manifest,bytes+32,64);
 manifest[64]=0;
 memcpy(input,bytes+96,64);
 input[64]=0;
 memcpy(terminal,bytes+160,64);
 terminal[64]=0;
  if(!hex64(manifest)||!hex64(input)||!hex64(terminal))return 0;
 target=getid(bytes+224);
 generation=get64(bytes+24);
  if(!k){
   char z[65];
 zero_sha(z);
   if(bytes[8]!='I'||generation||memcmp(manifest,z,65)||memcmp(input,z,65)||memcmp(terminal,z,65))return 0;
  }else if(bytes[8]=='B'){
   if(current.kind=='B'||current.generation==UINT64_MAX||generation!=current.generation+1||
    !nonzero(manifest)||!nonzero(input)||nonzero(terminal)||!sameid(&target,&current.target))return 0;
   memcpy(current.previous_clean,last,65);
 current.pending.generation=generation;
   memcpy(current.pending.manifest,manifest,65);
 memcpy(current.pending.input,input,65);
   memcpy(current.pending.seal,bytes+S_SEAL,64);
 current.pending.seal[64]=0;
  }else if(bytes[8]=='C'){
   if(current.kind!='B'||generation!=current.generation||memcmp(manifest,current.pending.manifest,65)||
    memcmp(input,current.pending.input,65)||!nonzero(terminal))return 0;
  }else return 0;
  current.kind=bytes[8];
 current.sequence=k+1;
 current.generation=generation;
 current.target=target;
  memcpy(current.terminal,terminal,65);
 memcpy(last,bytes+S_SEAL,64);
 last[64]=0;
 memcpy(current.seal,last,65);
 }
 *out=current;
 return route_current(h);
}
static int state_same(const state *a,const state *b){
 return a->kind==b->kind&&a->sequence==b->sequence&&a->generation==b->generation&&
 !memcmp(a->seal,b->seal,65)&&sameid(&a->target,&b->target);
}
static int descriptor_same(const pc02_pending_record *a,const pc02_pending_record *b){
 return a&&b&&a->generation==b->generation&&hex64(a->seal)&&hex64(a->manifest)&&hex64(a->input)&&
 !memcmp(a->seal,b->seal,65)&&!memcmp(a->manifest,b->manifest,65)&&!memcmp(a->input,b->input,65);
}
static int target_current(pc02_lease *h,int allow_transition){
 pc02_identity actual,expected=getid(h->binding+40);
 int fd=regular_open(h->parent,h->leaf,O_RDONLY,0,&actual);
 if(fd<0)return allow_transition&&missing(h->parent,h->leaf);
 int ok=allow_transition||sameid(&actual,&expected);
 close(fd);
 return ok;
}
static int authoritative_state(pc02_lease *h,const state *s){
 uint64_t generation=get64(h->binding+88);
 if(s->kind!='B'&&s->generation==generation&&!memcmp(s->seal,h->binding+96,64)){
  pc02_identity expected=getid(h->binding+40);
 return sameid(&expected,&s->target);
 }
 return h->mode==PC02_RECOVER&&generation!=UINT64_MAX&&s->generation==generation+1&&
   !memcmp(s->previous_clean,h->binding+96,64);
}
int pc02_check(pc02_lease *h){
 state actual;
 if(!h||h->poisoned||!route_current(h)||!binding_current(h)||!load_state(h,&actual)||!state_same(&actual,&h->seen))return 0;
 if(h->active){
  uint64_t generation=get64(h->binding+88);
  if(actual.kind!='B'||generation==UINT64_MAX||actual.generation!=generation+1||memcmp(actual.previous_clean,h->binding+96,64))return 0;
 }else if(!authoritative_state(h,&actual))return 0;
 return target_current(h,h->mode==PC02_RECOVER||(h->active&&h->transition));
}
static int append_state(pc02_lease *h,unsigned char kind,uint64_t generation,const char *manifest,const char *input,
 const char *terminal,const pc02_identity *target,unsigned at){
 unsigned char bytes[S_BYTES],verify[S_BYTES];
 off_t offset=(off_t)(h->seen.sequence*S_BYTES);
 state actual;
 if(h->poisoned||h->seen.sequence>=MAX_STATES||!route_current(h)||!size_exact(h->state_file,offset))return 0;
 state_bytes(bytes,kind,h->seen.sequence+1,generation,manifest,input,terminal,target,h->seen.seal);
 if(h->controls.fault==PC02_SHORT_WRITE&&h->controls.fault_phase==at){
  (void)io_write(h->state_file,bytes,S_BYTES-1,offset);
 h->poisoned=1;
 return 0;
 }
 if(!io_write(h->state_file,bytes,sizeof(bytes),offset)){h->poisoned=1;
 return 0;
 }phase(h,at);
 if(!sync_controlled(h,h->state_file,at)||
    (h->controls.fault==PC02_READBACK_FAIL&&h->controls.fault_phase==at)){h->poisoned=1;
 return 0;
 }
 int fd=regular_open(h->route_dir,"state",O_RDONLY,1,NULL);
 int ok=fd>=0&&size_exact(fd,offset+S_BYTES)&&io_read(fd,verify,sizeof(verify),offset)&&!memcmp(bytes,verify,sizeof(bytes));
 if(fd>=0)close(fd);
 if(!ok||!load_state(h,&actual)||actual.kind!=kind||actual.generation!=generation||memcmp(actual.seal,bytes+S_SEAL,64)){
  h->poisoned=1;
 return 0;
 }
 h->seen=actual;
 phase(h,at+1);
 return 1;
}
static int publish_binding(pc02_lease *h,const unsigned char candidate[B_BYTES],int initial){
 char temporary[96];
 unsigned serial;
 int fd=-1;
 unsigned char check[B_BYTES],bytes[B_BYTES];
 pc02_identity id;
 if(!route_current(h)||(initial?!missing(h->route_dir,"binding"):!binding_current(h)))return 0;
 for(serial=0;
 serial<1024;
 serial++){
  snprintf(temporary,sizeof(temporary),"binding-next-%lu-%u",(unsigned long)getpid(),serial);
  fd=regular_open(h->route_dir,temporary,O_RDWR|O_CREAT|O_EXCL,1,&id);
  if(fd>=0)break;
 if(errno!=EEXIST)return 0;
 }
 if(fd<0)return 0;
 memcpy(bytes,candidate,B_BYTES);
 putid(bytes+224,&id);seal(bytes,B_SEAL);
 if(!io_write(fd,bytes,B_BYTES,0)||fsync(fd)||!read_record(fd,check,B_BYTES)||memcmp(check,bytes,B_BYTES)){
  if(fd>=0)close(fd);
 return 0;
 }
 close(fd);
 phase(h,PC02_BINDING_WRITTEN);
 if(!route_current(h)||(initial?!missing(h->route_dir,"binding"):!binding_current(h))||
    renameat(h->route_dir,temporary,h->route_dir,"binding"))return 0;
 phase(h,PC02_BINDING_PUBLISHED);
 if(fsync(h->route_dir))return 0;
 fd=regular_open(h->route_dir,"binding",O_RDONLY,1,&id);
 pc02_identity expected=getid(bytes+224);
 if(fd<0||!sameid(&id,&expected)||!read_record(fd,check,B_BYTES)||memcmp(check,bytes,B_BYTES)){if(fd>=0)close(fd);
 return 0;
 }
 if(h->binding_file>=0)close(h->binding_file);
 h->binding_file=fd;
 h->binding_id=id;
 memcpy(h->binding,bytes,B_BYTES);
 phase(h,PC02_BINDING_DURABLE);
 return binding_current(h)&&route_current(h);
}
static int authority_create_h(pc02_lease *h,const char *root){
 char parent[PATH_CAP],leaf[256];
 const char *slash;
 size_t n;
 int anchor=-1,ok=0;
 unsigned char bytes[A_BYTES]={0},lock[16]="PC02-REGISTRY\n";
 pc02_identity lock_id;
 if(!h||!safe_path(root)||(slash=strrchr(root,'/'))==NULL||strlen(slash+1)>=sizeof(leaf))goto done;
 strcpy(leaf,slash+1);
 n=(size_t)(slash-root);
 if(!n)strcpy(parent,"/");
 else{memcpy(parent,root,n);
 parent[n]=0;
 }
 h->parent=pin_chain(h,parent,0);
 if(h->parent<0||mkdirat(h->parent,leaf,0700))goto done;
 h->root=pin_chain(h,root,1);
 if(h->root<0||!metadata(h->root,1,1,&h->root_id))goto done;
 h->registry=regular_open(h->root,"registry.lock",O_RDWR|O_CREAT|O_EXCL,1,&lock_id);
 if(h->registry<0||flock(h->registry,LOCK_EX|LOCK_NB)||!io_write(h->registry,lock,sizeof(lock),0)||fsync(h->registry))goto done;
 memcpy(bytes,"PC02A001",8);
 putid(bytes+8,&h->root_id);
 putid(bytes+24,&lock_id);
 anchor=regular_open(h->root,"authority",O_RDWR|O_CREAT|O_EXCL,1,&h->authority_id);
 if(anchor<0)goto done;
 putid(bytes+40,&h->authority_id);seal(bytes,A_SEAL);
 if(!io_write(anchor,bytes,sizeof(bytes),0)||fsync(anchor)||fsync(h->root)||fsync(h->parent))goto done;
 unsigned char verify[A_BYTES];
 ok=read_record(anchor,verify,sizeof(verify))&&!memcmp(verify,bytes,sizeof(bytes))&&pins_current(h);
done:
 if(anchor>=0)close(anchor);
 destroy(h);
 return ok;
}
static int enrollment_proof(pc02_lease *h,pc02_prove prove,void *context,const pc02_identity *expected){
 pc02_identity actual;
 if(!prove||!route_current(h)||h->target_file<0||!entry_id(h->parent,h->leaf,h->target_file,0,&actual)||
    !sameid(&actual,expected)||!prove(context,h->library,h->target_file,NULL,NULL)||
    !entry_id(h->parent,h->leaf,h->target_file,0,&actual)||!sameid(&actual,expected)||
    fsync(h->target_file)||fsync(h->parent)||!route_current(h))return 0;
 return 1;
}
static int enroll_h(pc02_lease *h,const char *root,const char *library,int create_library,pc02_prove prove,void *context,const pc02_controls *controls){
 unsigned char intent[B_BYTES],initial[S_BYTES];
 char zero[65];
 pc02_identity target;
 int fd=-1,ok=0;
 state first={0};
 if(!h||!prove)goto done;
 h->mode=PC02_OWNER;
 if(controls)h->controls=*controls;
 if(!root_open(h,root,1)||!library_parent(h,library)||!missing(h->root,h->route)||!open_route(h,1))goto done;
 h->target_file=regular_open(h->parent,h->leaf,O_RDWR|(create_library?(O_CREAT|O_EXCL):0),0,&target);
 if(h->target_file<0||!size_exact(h->lease_file,0)||!size_exact(h->state_file,0))goto done;
 zero_sha(zero);
 state_bytes(initial,'I',1,0,zero,zero,zero,&target,zero);
 first.kind='I';
 first.sequence=1;
 first.target=target;
 memcpy(first.seal,initial+S_SEAL,64);
 first.seal[64]=0;
 binding_encode(h,&first,intent);
 fd=regular_open(h->route_dir,"enrollment",O_RDWR|O_CREAT|O_EXCL,1,NULL);
 if(fd<0||!io_write(fd,intent,sizeof(intent),0)||fsync(fd)||fsync(h->lease_file)||fsync(h->state_file)||
    fsync(h->route_dir)||fsync(h->root)||fsync(h->parent))goto done;
 unsigned char readback[B_BYTES];
 if(!read_record(fd,readback,sizeof(readback))||memcmp(readback,intent,sizeof(intent)))goto done;
 phase(h,PC02_ENROLL_INTENT);
 if(!enrollment_proof(h,prove,context,&target)||!io_write(h->state_file,initial,sizeof(initial),0)||fsync(h->state_file)||
    !load_state(h,&h->seen)||!state_same(&first,&h->seen))goto done;
 phase(h,PC02_ENROLL_STATE);
 if(!publish_binding(h,intent,1))goto done;
 phase(h,PC02_ENROLL_BOUND);
 ok=1;
done:
 if(fd>=0)close(fd);
 destroy(h);
 return ok;
}
static int recover_enrollment_h(pc02_lease *h,const char *root,const char *library,pc02_prove prove,void *context,const pc02_controls *controls){
 unsigned char intent[B_BYTES],initial[S_BYTES],check[B_BYTES];
 pc02_identity target;
 char zero[65];
 int fd=-1,binding=-1,ok=0;
 state first={0};
 if(!h||!prove)goto done;
 h->mode=PC02_RECOVER;
 if(controls)h->controls=*controls;
 if(!root_open(h,root,1)||!library_parent(h,library)||!open_route(h,0))goto done;
 fd=regular_open(h->route_dir,"enrollment",O_RDONLY,1,NULL);
 if(fd<0||!read_record(fd,intent,sizeof(intent))||!binding_valid(h,intent)||get64(intent+88))goto done;
 target=getid(intent+40);
 h->target_file=regular_open(h->parent,h->leaf,O_RDWR,0,NULL);
 if(h->target_file<0)goto done;
 zero_sha(zero);
 state_bytes(initial,'I',1,0,zero,zero,zero,&target,zero);
 if(memcmp(intent+96,initial+S_SEAL,64)||!enrollment_proof(h,prove,context,&target))goto done;
 if(size_exact(h->state_file,0)){
  if(!io_write(h->state_file,initial,sizeof(initial),0)||fsync(h->state_file))goto done;
 }else{
  unsigned char existing[S_BYTES];
 if(!read_record(h->state_file,existing,sizeof(existing))||memcmp(existing,initial,sizeof(initial)))goto done;
 }
 first.kind='I';
 first.sequence=1;
 first.target=target;
 memcpy(first.seal,initial+S_SEAL,64);
 first.seal[64]=0;
 if(fsync(h->state_file)||!load_state(h,&h->seen)||!state_same(&first,&h->seen))goto done;
 pc02_identity current_id;
 binding=regular_open(h->route_dir,"binding",O_RDONLY,1,&current_id);
 if(binding>=0){
  ok=read_record(binding,check,sizeof(check))&&binding_valid(h,check)&&!memcmp(check,intent,224);
  pc02_identity encoded=getid(check+224);
  ok=ok&&sameid(&current_id,&encoded);
  goto done;
 }
 if(!missing(h->route_dir,"binding")||!publish_binding(h,intent,1))goto done;
 ok=1;
done:
 if(fd>=0)close(fd);
 if(binding>=0)close(binding);
 destroy(h);
 return ok;
}
static int open_h(pc02_lease *h,const char *root,const char *library,unsigned mode,const pc02_grant *expected,const pc02_controls *controls,pc02_lease **out){
 int ok=0;
 pc02_identity target;
 if(out)*out=NULL;
 if(!h||!out||mode<PC02_SHARED||mode>PC02_RECOVER)goto done;
 h->mode=mode;
 if(controls)h->controls=*controls;
 if(!root_open(h,root,0)||!library_parent(h,library)||!open_route(h,0))goto done;
 h->binding_file=regular_open(h->route_dir,"binding",O_RDONLY,1,&h->binding_id);
 if(h->binding_file<0||!read_record(h->binding_file,h->binding,B_BYTES)||!binding_valid(h,h->binding)||
    !load_state(h,&h->seen)||!authoritative_state(h,&h->seen))goto done;
 pc02_identity self_id=getid(h->binding+224);
 if(!sameid(&self_id,&h->binding_id))goto done;
 target=getid(h->binding+40);
 if(expected&&(!hex64(expected->seal)||expected->generation!=get64(h->binding+88)||
    memcmp(expected->seal,h->binding+96,64)||!sameid(&expected->target,&target)))goto done;
 h->target_file=regular_open(h->parent,h->leaf,O_RDONLY,0,NULL);
 if(h->target_file<0&&!(mode==PC02_RECOVER&&missing(h->parent,h->leaf)))goto done;
 if(!pc02_check(h))goto done;
 if(flock(h->registry,LOCK_UN))goto done;
 *out=h;
 ok=1;
done:
 if(!ok)destroy(h);
 return ok;
}
int pc02_grant_get(pc02_lease *h,pc02_grant *out){
 if(!h||!out||!pc02_check(h))return 0;
 memset(out,0,sizeof(*out));
 out->generation=get64(h->binding+88);
 memcpy(out->seal,h->binding+96,64);
 out->target=getid(h->binding+40);
 return 1;
}
int pc02_borrow(pc02_lease *h){if(!h||h->borrows==UINT_MAX||!pc02_check(h))return 0;
 h->borrows++;
 return 1;
 }
int pc02_unborrow(pc02_lease *h){if(!h||!h->borrows)return 0;
 h->borrows--;
 return 1;
 }
static int issue_cap(pc02_lease *h,pc02_cap **out){
 pc02_cap *cap=calloc(1,sizeof(*cap));if(!cap)return 0;
 cap->owner=h;cap->generation=h->seen.generation;memcpy(cap->seal,h->seen.seal,65);
 cap->next=h->caps;h->caps=cap;h->current=cap;h->active=1;*out=cap;return 1;
}
int pc02_begin(pc02_lease *h,const char manifest[65],const char input[65],pc02_cap **cap){
 char zero[65];
 if(cap)*cap=NULL;
 if(!h||!cap||h->mode!=PC02_OWNER||h->active||h->borrows||h->seen.kind=='B'||
   !nonzero(manifest)||!nonzero(input)||h->seen.generation==UINT64_MAX||h->seen.sequence>MAX_STATES-2||!pc02_check(h))return 0;
 zero_sha(zero);
 if(!append_state(h,'B',h->seen.generation+1,manifest,input,zero,&h->seen.target,PC02_PENDING_WRITTEN))return 0;
 return issue_cap(h,cap);
}
int pc02_pending(pc02_lease *h,pc02_pending_record *out){
 if(out)memset(out,0,sizeof(*out));
 if(!h||!out||h->mode==PC02_SHARED||h->seen.kind!='B'||!pc02_check(h))return 0;
 *out=h->seen.pending;
 return 1;
}
int pc02_resume(pc02_lease *h,const pc02_pending_record *exact,pc02_cap **cap){
 if(cap)*cap=NULL;
 if(!h||!cap||h->mode!=PC02_RECOVER||h->active||h->borrows||h->seen.kind!='B'||
    !descriptor_same(exact,&h->seen.pending)||!pc02_check(h))return 0;
 if(fsync(h->state_file)||fsync(h->route_dir)||!pc02_check(h)||!issue_cap(h,cap))return 0;
 h->transition=1;
 return 1;
}
static int live_cap(pc02_lease *h,pc02_cap *cap){
 return h&&cap==h->current&&h->active&&cap->owner==h&&cap->generation==h->seen.generation&&
 !memcmp(cap->seal,h->seen.pending.seal,65)&&pc02_check(h);
}
int pc02_prepare_publish(pc02_lease *h,pc02_cap *cap){if(!live_cap(h,cap)||h->borrows)return 0;
 h->transition=1;
 return 1;
 }
static int actual_proof(pc02_lease *h,const char *terminal,pc02_prove prove,void *context,pc02_identity *target){
 int fd;
 if(!prove||!nonzero(terminal)||h->borrows||!route_current(h)||!binding_current(h))return 0;
 fd=regular_open(h->parent,h->leaf,O_RDWR,0,target);
 if(fd<0)return 0;
 int ok=prove(context,h->library,fd,&h->seen.pending,terminal)&&route_current(h)&&binding_current(h);
 pc02_identity after;
 if(!entry_id(h->parent,h->leaf,fd,0,&after)||!sameid(target,&after)||fsync(fd)||fsync(h->parent))ok=0;
 close(fd);
 return ok;
}
int pc02_finish(pc02_lease *h,pc02_cap *cap,const char terminal[65],pc02_prove prove,void *context,pc02_grant *grant){
 pc02_identity target;
 unsigned char bytes[B_BYTES];
 if(!live_cap(h,cap)||!actual_proof(h,terminal,prove,context,&target)||!live_cap(h,cap)){
  if(h&&cap==h->current&&h->active)h->poisoned=1;
 return 0;
 }
 if(!append_state(h,'C',h->seen.generation,h->seen.pending.manifest,h->seen.pending.input,terminal,&target,PC02_CLEAN_WRITTEN))return 0;
 binding_encode(h,&h->seen,bytes);
 if(!publish_binding(h,bytes,0)){h->poisoned=1;
 return 0;
 }
 h->active=0;
 h->transition=0;
 h->current=NULL;
 if(h->target_file>=0)close(h->target_file);
 h->target_file=regular_open(h->parent,h->leaf,O_RDONLY,0,NULL);
 pc02_grant local;
 return pc02_grant_get(h,grant?grant:&local);
}
int pc02_reconcile(pc02_lease *h,const pc02_pending_record *exact,const char terminal[65],pc02_prove prove,void *context,pc02_grant *grant){
 pc02_identity target;
 unsigned char bytes[B_BYTES];
 if(!h||h->mode!=PC02_RECOVER||h->active||h->borrows||h->seen.kind!='C'||!descriptor_same(exact,&h->seen.pending)||
   !nonzero(terminal)||memcmp(terminal,h->seen.terminal,65)||!pc02_check(h)||
   !actual_proof(h,terminal,prove,context,&target)||!sameid(&target,&h->seen.target)||!pc02_check(h))return 0;
 if(fsync(h->state_file)||fsync(h->route_dir)||!pc02_check(h))return 0;
 binding_encode(h,&h->seen,bytes);
 if(memcmp(bytes,h->binding,224)&&!publish_binding(h,bytes,0)){h->poisoned=1;
 return 0;
 }
 pc02_grant local;
 return pc02_grant_get(h,grant?grant:&local);
}
int pc02_close(pc02_lease *h){if(!h)return 1;
 if(h->active||h->borrows)return 0;
 destroy(h);
 return 1;
 }

int pc02_authority_create(const char *root){
 return authority_create_h(allocate(),root);
}
int pc02_enroll(const char *root,const char *library,int create_library,
 pc02_prove prove,void *context,const pc02_controls *controls){
 return enroll_h(allocate(),root,library,create_library,prove,context,controls);
}
int pc02_recover_enrollment(const char *root,const char *library,
 pc02_prove prove,void *context,const pc02_controls *controls){
 return recover_enrollment_h(allocate(),root,library,prove,context,controls);
}
int pc02_open(const char *root,const char *library,unsigned mode,
 const pc02_grant *expected,const pc02_controls *controls,pc02_lease **out){
 return open_h(allocate(),root,library,mode,expected,controls,out);
}
int pc02_authority_create_in(pc02_scope *scope,const char *authority){
 char root[PATH_CAP];pc02_lease *h=allocate_in(scope);
 if(!h||!scope_join(scope,authority,root)){destroy(h);return 0;}
 return authority_create_h(h,root);
}
int pc02_enroll_in(pc02_scope *scope,const char *authority,const char *library,int create_library,
 pc02_prove prove,void *context,const pc02_controls *controls){
 char root[PATH_CAP],target[PATH_CAP];pc02_lease *h=allocate_in(scope);
 if(!h||!scope_paths(scope,authority,library,root,target)){destroy(h);return 0;}
 return enroll_h(h,root,target,create_library,prove,context,controls);
}
int pc02_recover_enrollment_in(pc02_scope *scope,const char *authority,const char *library,
 pc02_prove prove,void *context,const pc02_controls *controls){
 char root[PATH_CAP],target[PATH_CAP];pc02_lease *h=allocate_in(scope);
 if(!h||!scope_paths(scope,authority,library,root,target)){destroy(h);return 0;}
 return recover_enrollment_h(h,root,target,prove,context,controls);
}
int pc02_open_in(pc02_scope *scope,const char *authority,const char *library,unsigned mode,
 const pc02_grant *expected,const pc02_controls *controls,pc02_lease **out){
 char root[PATH_CAP],target[PATH_CAP];pc02_lease *h=allocate_in(scope);
 if(out)*out=NULL;
 if(!h||!scope_paths(scope,authority,library,root,target)){destroy(h);return 0;}
 return open_h(h,root,target,mode,expected,controls,out);
}
const char *pc02_library_path(pc02_lease *h){
 return pc02_check(h)?h->library:NULL;
}
#include "pc02_migration.inc"
