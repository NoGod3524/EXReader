/* SPDX-License-Identifier: MIT */
#define _GNU_SOURCE 1
#define _DARWIN_C_SOURCE 1
#include <exr_pc02_repair_store.h>
#include <exr_wh.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#if defined(__APPLE__)
#include <sys/acl.h>
#elif defined(__linux__)
#include <sys/xattr.h>
#include <sys/syscall.h>
#endif

#define RP_LIMIT (4u*1024u*1024u)
#define RP_HEADER 112u
#define RP_SEAL 64u

static uint64_t rp64(const unsigned char *p){
 uint64_t value=0;
 for(unsigned k=0;k<8;k++)value|=(uint64_t)p[k]<<(8*k);
 return value;
}
static void rpput64(unsigned char *p,uint64_t value){
 for(unsigned k=0;k<8;k++)p[k]=(unsigned char)(value>>(8*k));
}
static pc02_identity rpid(const unsigned char *p){
 pc02_identity id={rp64(p),rp64(p+8)};
 return id;
}
static int rpsame(pc02_identity a,pc02_identity b){
 return a.device==b.device&&a.inode==b.inode;
}
static pc02_identity rpstatid(const struct stat *s){
 pc02_identity id={(uint64_t)s->st_dev,(uint64_t)s->st_ino};
 return id;
}
static int rphex(const unsigned char *p){
 for(unsigned k=0;k<64;k++)if(!((p[k]>='0'&&p[k]<='9')||(p[k]>='a'&&p[k]<='f')))return 0;
 return 1;
}
static int rpinfo_valid(const pc02rp_info *p){
 return p&&p->identity.inode&&p->bytes<=RP_LIMIT&&p->sha256[64]==0&&
  rphex((const unsigned char *)p->sha256);
}
static int rpinfo_same(const pc02rp_info *a,const pc02rp_info *b){
 return rpinfo_valid(a)&&rpinfo_valid(b)&&rpsame(a->identity,b->identity)&&
  a->bytes==b->bytes&&!memcmp(a->sha256,b->sha256,65);
}
static int rpleaf(const char *leaf){
 size_t n=0;
 if(!leaf)return 0;
 while(n<256&&leaf[n])n++;
 if(!n||n==256||leaf[n-1]=='.'||leaf[n-1]==' '||
    !strcmp(leaf,".")||!strcmp(leaf,".."))return 0;
 for(size_t k=0;k<n;k++){
  char c=leaf[k];
  if(!((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||
       c=='.'||c=='_'||c=='-'))return 0;
 }
 return 1;
}
#if defined(__linux__)
static int rpnoacl(int fd,const char *name){
 ssize_t count=fgetxattr(fd,name,NULL,0);
 if(count>=0)return 0;
 return errno==ENODATA||errno==ENOTSUP||errno==EOPNOTSUPP;
}
#endif
static int rpacl(int fd,int directory){
#if defined(__APPLE__)
 acl_t acl=acl_get_fd_np(fd,ACL_TYPE_EXTENDED);
 (void)directory;
 if(!acl)return errno==ENOENT;
 acl_entry_t entry;
 int which=ACL_FIRST_ENTRY,ok=acl_valid(acl)==0;
 while(ok){
  errno=0;
  int result=acl_get_entry(acl,which,&entry);
  if(result==-1){if(errno!=EINVAL)ok=0;break;}
  if(result!=0){ok=0;break;}
  acl_tag_t tag;
  which=ACL_NEXT_ENTRY;
  if(acl_get_tag_type(entry,&tag)||tag!=ACL_EXTENDED_DENY){ok=0;break;}
 }
 if(acl_free(acl))ok=0;
 return ok;
#elif defined(__linux__)
 return rpnoacl(fd,"system.posix_acl_access")&&
  (!directory||rpnoacl(fd,"system.posix_acl_default"));
#else
 (void)fd;
 (void)directory;
 return 0;
#endif
}
static int rpmetadata(int fd,int directory,struct stat *out){
 struct stat s;
 if(fstat(fd,&s)||!rpacl(fd,directory)||s.st_uid!=geteuid()||
    (s.st_mode&07777)!=(directory?0700:0600)||
    (directory?!S_ISDIR(s.st_mode):!S_ISREG(s.st_mode))||
    (!directory&&s.st_nlink!=1)||!s.st_ino)return 0;
 if(out)*out=s;
 return 1;
}
static int rpstable(const struct stat *a,const struct stat *b){
 if(a->st_dev!=b->st_dev||a->st_ino!=b->st_ino||a->st_size!=b->st_size||
    a->st_mode!=b->st_mode||a->st_uid!=b->st_uid||a->st_gid!=b->st_gid||
    a->st_nlink!=b->st_nlink)return 0;
#if defined(__APPLE__)
 return a->st_mtimespec.tv_sec==b->st_mtimespec.tv_sec&&
  a->st_mtimespec.tv_nsec==b->st_mtimespec.tv_nsec&&
  a->st_ctimespec.tv_sec==b->st_ctimespec.tv_sec&&
  a->st_ctimespec.tv_nsec==b->st_ctimespec.tv_nsec;
#else
 return a->st_mtim.tv_sec==b->st_mtim.tv_sec&&a->st_mtim.tv_nsec==b->st_mtim.tv_nsec&&
  a->st_ctim.tv_sec==b->st_ctim.tv_sec&&a->st_ctim.tv_nsec==b->st_ctim.tv_nsec;
#endif
}
static int rpdir_current(int directory,const struct stat *expected){
 struct stat actual;
 return rpmetadata(directory,1,&actual)&&actual.st_dev==expected->st_dev&&
  actual.st_ino==expected->st_ino&&actual.st_uid==expected->st_uid&&
  actual.st_gid==expected->st_gid&&actual.st_mode==expected->st_mode;
}
static int rpread(int fd,unsigned char *data,size_t bytes){
 size_t done=0;
 unsigned char extra;
 while(done<bytes){
  ssize_t count=pread(fd,data+done,bytes-done,(off_t)done);
  if(count<0&&errno==EINTR)continue;
  if(count<=0)return 0;
  done+=(size_t)count;
 }
 for(;;){
  ssize_t count=pread(fd,&extra,1,(off_t)bytes);
  if(count<0&&errno==EINTR)continue;
  return count==0;
 }
}
static int rpwrite(int fd,const unsigned char *data,size_t bytes){
 size_t done=0;
 while(done<bytes){
  ssize_t count=pwrite(fd,data+done,bytes-done,(off_t)done);
  if(count<0&&errno==EINTR)continue;
  if(count<=0)return 0;
  done+=(size_t)count;
 }
 return 1;
}
void pc02rp_free(pc02rp_blob *blob){
 if(!blob)return;
 free(blob->data);
 memset(blob,0,sizeof(*blob));
}
int pc02rp_read_raw(int fd,size_t maximum,pc02rp_blob *out){
 struct stat before,middle,after;
 pc02rp_blob blob={0};
 unsigned char *second=NULL;
 char digest[65];
 size_t bytes;
 int ok=0;
 if(out)memset(out,0,sizeof(*out));
 if(!out||maximum>RP_LIMIT||!rpmetadata(fd,0,&before)||before.st_size<0||
    (uint64_t)before.st_size>maximum)return 0;
 bytes=(size_t)before.st_size;
 blob.data=malloc(bytes?bytes:1);
 second=malloc(bytes?bytes:1);
 if(!blob.data||!second||!rpread(fd,blob.data,bytes)||!rpmetadata(fd,0,&middle)||
    !rpstable(&before,&middle))goto done;
 wh_sha256_hex(blob.data,bytes,blob.info.sha256);
 if(!rpread(fd,second,bytes)||!rpmetadata(fd,0,&after)||!rpstable(&before,&after))goto done;
 wh_sha256_hex(second,bytes,digest);
 if(memcmp(blob.info.sha256,digest,65)||memcmp(blob.data,second,bytes))goto done;
 blob.info.identity=rpstatid(&before);
 blob.info.bytes=bytes;
 blob.bytes=bytes;
 *out=blob;
 blob.data=NULL;
 ok=1;
done:
 free(second);
 pc02rp_free(&blob);
 return ok;
}
static int rpnamed(int directory,const char *leaf,pc02rp_blob *out){
 struct stat parent,named,opened,after;
 pc02rp_blob blob={0};
 int fd=-1,ok=0;
 if(out)memset(out,0,sizeof(*out));
 if(!out||!rpleaf(leaf)||!rpmetadata(directory,1,&parent))return 0;
 fd=openat(directory,leaf,O_RDONLY|O_NONBLOCK|O_NOFOLLOW|O_CLOEXEC);
 if(fd<0||!rpmetadata(fd,0,&opened)||!pc02rp_read_raw(fd,RP_LIMIT,&blob)||
    !rpmetadata(fd,0,&after)||!rpstable(&opened,&after)||
    fstatat(directory,leaf,&named,AT_SYMLINK_NOFOLLOW)||!rpstable(&after,&named)||
    !S_ISREG(named.st_mode)||named.st_uid!=geteuid()||(named.st_mode&07777)!=0600||
    named.st_nlink!=1||!rpsame(rpstatid(&named),blob.info.identity)||
    named.st_size<0||(uint64_t)named.st_size!=blob.info.bytes||
    !rpdir_current(directory,&parent))goto done;
 if(close(fd)){fd=-1;goto done;}
 fd=-1;
 *out=blob;
 blob.data=NULL;
 ok=1;
done:
 if(fd>=0&&close(fd))ok=0;
 pc02rp_free(&blob);
 return ok;
}
static int rpnoreplace(int directory,const char *from,const char *to){
#if defined(__APPLE__)
 return renameatx_np(directory,from,directory,to,RENAME_EXCL)==0;
#elif defined(__linux__) && defined(SYS_renameat2)
 return syscall(SYS_renameat2,directory,from,directory,to,1u)==0;
#else
 (void)directory;
 (void)from;
 (void)to;
 errno=ENOTSUP;
 return 0;
#endif
}
static int rppublish(int directory,const char *leaf,const unsigned char *payload,size_t bytes,
 uint64_t kind,uint64_t sequence,pc02rp_info *saved){
 struct stat parent,created;
 pc02rp_blob readback={0};
 unsigned char *wrapped=NULL;
 const unsigned char *raw=payload;
 size_t total=bytes;
 char temp[96],digest[65];
 int fd=-1,ok=0;
 pc02_identity identity;
 if(saved)memset(saved,0,sizeof(*saved));
 if(!saved||!rpleaf(leaf)||(!payload&&bytes)||bytes>RP_LIMIT||
    !rpmetadata(directory,1,&parent))return 0;
 if(kind){
  if(!sequence||!bytes||bytes>RP_LIMIT-RP_HEADER-RP_SEAL)return 0;
  total=RP_HEADER+bytes+RP_SEAL;
 }
 for(unsigned serial=0;serial<1024;serial++){
  int n=snprintf(temp,sizeof(temp),"repair-next-%lu-%u",(unsigned long)getpid(),serial);
  if(n<=0||(size_t)n>=sizeof(temp))goto done;
  fd=openat(directory,temp,O_RDWR|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
  if(fd>=0)break;
  if(errno!=EEXIST)goto done;
 }
 if(fd<0||!rpmetadata(fd,0,&created)||created.st_size!=0||!rpdir_current(directory,&parent))goto done;
 identity=rpstatid(&created);
 if(kind){
  wrapped=calloc(1,total);
  if(!wrapped)goto done;
  memcpy(wrapped,"PC02R001",8);
  rpput64(wrapped+8,kind);
  rpput64(wrapped+16,sequence);
  rpput64(wrapped+24,bytes);
  rpput64(wrapped+32,identity.device);
  rpput64(wrapped+40,identity.inode);
  wh_sha256_hex(payload,bytes,digest);
  memcpy(wrapped+48,digest,64);
  memcpy(wrapped+RP_HEADER,payload,bytes);
  wh_sha256_hex(wrapped,total-RP_SEAL,digest);
  memcpy(wrapped+total-RP_SEAL,digest,64);
  raw=wrapped;
 }
 if(!rpwrite(fd,raw,total)||fsync(fd)||!rpdir_current(directory,&parent))goto done;
 if(!rpnamed(directory,temp,&readback)||!rpsame(readback.info.identity,identity)||
    readback.bytes!=total||memcmp(readback.data,raw,total))goto done;
 pc02rp_free(&readback);
 if(!rpdir_current(directory,&parent)||!rpnoreplace(directory,temp,leaf)||
    fsync(directory)||!rpdir_current(directory,&parent)||
    !rpnamed(directory,leaf,&readback)||!rpsame(readback.info.identity,identity)||
    readback.bytes!=total||memcmp(readback.data,raw,total))goto done;
 *saved=readback.info;
 ok=1;
done:
 if(fd>=0&&close(fd))ok=0;
 pc02rp_free(&readback);
 free(wrapped);
 if(!ok)memset(saved,0,sizeof(*saved));
 return ok;
}
int pc02rp_archive(int source_fd,int directory,const char *leaf,size_t maximum,
 pc02rp_info *original,pc02rp_info *saved){
 pc02rp_blob before={0},after={0};
 pc02rp_info copy={0};
 int ok=0;
 if(original)memset(original,0,sizeof(*original));
 if(saved)memset(saved,0,sizeof(*saved));
 if(!original||!saved||!pc02rp_read_raw(source_fd,maximum,&before))return 0;
 if(!rppublish(directory,leaf,before.data,before.bytes,0,0,&copy)||
    !pc02rp_read_raw(source_fd,maximum,&after)||!rpinfo_same(&before.info,&after.info)||
    before.bytes!=after.bytes||memcmp(before.data,after.data,before.bytes)||
    rpsame(copy.identity,before.info.identity)||copy.bytes!=before.info.bytes||memcmp(copy.sha256,before.info.sha256,65))goto done;
 *original=before.info;
 *saved=copy;
 ok=1;
done:
 pc02rp_free(&before);
 pc02rp_free(&after);
 return ok;
}
int pc02rp_write(int directory,const char *leaf,uint64_t kind,uint64_t sequence,
 const void *payload,size_t bytes,pc02rp_info *saved){
 if(saved)memset(saved,0,sizeof(*saved));
 if(!kind||!sequence||!payload||!bytes)return 0;
 return rppublish(directory,leaf,payload,bytes,kind,sequence,saved);
}
int pc02rp_read(int directory,const char *leaf,uint64_t kind,uint64_t sequence,
 const pc02rp_info *exact,pc02rp_blob *out){
 pc02rp_blob raw={0};
 char digest[65];
 size_t bytes;
 int ok=0;
 if(out)memset(out,0,sizeof(*out));
 if(!out||!kind||!sequence||(exact&&!rpinfo_valid(exact))||
    !rpnamed(directory,leaf,&raw)||raw.bytes<RP_HEADER+1+RP_SEAL)goto done;
 if(memcmp(raw.data,"PC02R001",8)||rp64(raw.data+8)!=kind||
    rp64(raw.data+16)!=sequence||!rpsame(rpid(raw.data+32),raw.info.identity)||
    !rphex(raw.data+48)||!rphex(raw.data+raw.bytes-RP_SEAL)||
    (exact&&!rpinfo_same(exact,&raw.info)))goto done;
 uint64_t declared=rp64(raw.data+24);
 if(!declared||declared>RP_LIMIT-RP_HEADER-RP_SEAL||
    declared!=raw.bytes-RP_HEADER-RP_SEAL)goto done;
 bytes=(size_t)declared;
 wh_sha256_hex(raw.data+RP_HEADER,bytes,digest);
 if(memcmp(digest,raw.data+48,64))goto done;
 wh_sha256_hex(raw.data,raw.bytes-RP_SEAL,digest);
 if(memcmp(digest,raw.data+raw.bytes-RP_SEAL,64))goto done;
 memmove(raw.data,raw.data+RP_HEADER,bytes);
 raw.bytes=bytes;
 *out=raw;
 raw.data=NULL;
 ok=1;
done:
 pc02rp_free(&raw);
 return ok;
}
