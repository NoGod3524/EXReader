/* SPDX-License-Identifier: MIT */
#define _GNU_SOURCE 1
#define _DARWIN_C_SOURCE 1
#include "pc02_journal.h"
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <dirent.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#if defined(__linux__)
#include <sys/syscall.h>
#endif
#include "pc02_io.h"
#define same pc02io_same
static int identity(int fd,int directory,pc02_identity *id){return pc02io_identity(fd,directory,1,id);
}
static int exact(pc02_journal *j){
 struct stat s;
 pc02_identity id;
 if(!pc02_check(j->lease)||!identity(j->directory,1,&id)||!same(&id,&j->identity)||
    fstatat(j->parent,j->leaf,&s,AT_SYMLINK_NOFOLLOW)||!S_ISDIR(s.st_mode))return 0;
 id.device=(uint64_t)s.st_dev;
 id.inode=(uint64_t)s.st_ino;
 return same(&id,&j->identity);
}
#define PJ_HEAD 296u
static int read_line(pc02_journal *j,const char *leaf,unsigned ordinal,char line[EXR_WH_LINE_MAX],pc02_identity *observed,char raw_sha[65]){
 int fd=openat(j->directory,leaf,O_RDONLY|O_NOFOLLOW|O_CLOEXEC),ok=0;
 struct stat s,after;
 pc02_identity id,self;
 unsigned char bytes[PJ_HEAD+EXR_WH_LINE_MAX+64];
 char sha[65];
 size_t at=0,n=0;
 if(fd<0)return 0;
 if(!identity(fd,0,&id)||fstat(fd,&s)||s.st_size<=(off_t)(PJ_HEAD+64)||s.st_size>(off_t)sizeof(bytes))goto done;
 while(at<(size_t)s.st_size){
  ssize_t got=pread(fd,bytes+at,(size_t)s.st_size-at,(off_t)at);
  if(got<0&&errno==EINTR)continue;
  if(got<=0)goto done;
  at+=(size_t)got;
 }
 n=(size_t)pc02io_get64(bytes+224);
 self=pc02io_getid(bytes+8);
 if(!n||n>=EXR_WH_LINE_MAX||PJ_HEAD+n+64!=(size_t)s.st_size||memcmp(bytes,"PC02ACK1",8)||
    !same(&self,&id)||pc02io_get64(bytes+24)!=ordinal||memcmp(bytes+32,j->manifest_sha,64)||
    memcmp(bytes+96,j->pending->input,64)||memcmp(bytes+160,j->pending->seal,64)||memchr(bytes+PJ_HEAD,0,n))goto done;
 wh_sha256_hex(bytes,PJ_HEAD+n,sha);
 if(memcmp(sha,bytes+PJ_HEAD+n,64))goto done;
 wh_sha256_hex(bytes+PJ_HEAD,n,sha);
 if(memcmp(sha,bytes+232,64)||fstat(fd,&after)||after.st_size!=s.st_size||
    fstatat(j->directory,leaf,&after,AT_SYMLINK_NOFOLLOW)||!S_ISREG(after.st_mode)||
    after.st_dev!=s.st_dev||after.st_ino!=s.st_ino||after.st_size!=s.st_size)goto done;
 memcpy(line,bytes+PJ_HEAD,n);
 line[n]=0;
 if(observed)*observed=id;
 if(raw_sha)wh_sha256_hex(bytes,(size_t)s.st_size,raw_sha);
 ok=1;
done:
 if(close(fd))ok=0;
 return ok;
}
static int tip_equal(const wh3_tip *a,const wh3_tip *b){
 return a->line_count==b->line_count&&!memcmp(a->manifest_sha,b->manifest_sha,65)&&!memcmp(a->last_line_sha,b->last_line_sha,65);
}
int pc02j_open(pc02_journal *j,pc02_lease *lease,int parent,const char *leaf,const pc02_identity *id,
 const wh_binding *binding,const wh_gates *gates,const pc02_pending_record *pending){
 if(!j||!lease||!leaf||!id||strlen(leaf)>=sizeof(j->leaf)||strchr(leaf,'/'))return 0;
 memset(j,0,sizeof(*j));
 j->directory=-1;
 j->lease=lease;
 j->parent=parent;
 j->identity=*id;
 strcpy(j->leaf,leaf);
 j->binding=binding;
 j->gates=gates;
 j->pending=pending;
 char manifest[EXR_WH_LINE_MAX];
 if(!wh_manifest(binding,gates,manifest))return 0;
 wh_sha256_hex(manifest,strlen(manifest),j->manifest_sha);
 j->directory=openat(parent,leaf,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
 return j->directory>=0&&exact(j);
}
int pc02j_scan(pc02_journal *j){
 unsigned char seen[257]={0};
 unsigned largest=0;
 DIR *directory=NULL;
 int fd=-1,ok=0;
 char manifest[EXR_WH_LINE_MAX];
 if(!j||!exact(j)||!wh_manifest(j->binding,j->gates,manifest))return 0;
 fd=openat(j->directory,".",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
 if(fd<0)return 0;
 directory=fdopendir(fd);
 if(!directory){close(fd);
 return 0;
 }
 memset(j->lines,0,sizeof(j->lines));
 j->temps=0;
 for(;;){
  errno=0;
  struct dirent *e=readdir(directory);
  if(!e){if(errno)goto done;
  break;
  }
  const char *name=e->d_name;
  if(!strcmp(name,".")||!strcmp(name,".."))continue;
  if(!strncmp(name,".pending-",9)){
   const char *v=name+9;
   if(*v<'1'||*v>'9')goto done;
   char *end=NULL;
   errno=0;
   unsigned long long pid=strtoull(v,&end,10);
   if(errno||!pid||pid>2147483647u||!end||*end!='-'||end[1]<'1'||end[1]>'9')goto done;
   v=end+1;
   errno=0;
   unsigned long long serial=strtoull(v,&end,10);
   if(errno||!serial||serial>4294967295u||!end||*end||j->temps>=1024)goto done;
   int temp=openat(j->directory,name,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
   pc02_identity tid;
   int valid=temp>=0&&identity(temp,0,&tid);
   if(temp>=0&&close(temp))valid=0;
   if(!valid)goto done;
   j->temps++;
   continue;
  }
  if(strlen(name)!=7||strncmp(name,"ack-",4))goto done;
  unsigned n=0;
  for(unsigned k=4;k<7;k++){if(name[k]<'0'||name[k]>'9')goto done;
  n=n*10+(unsigned)(name[k]-'0');
  }
  if(!n||n>256||seen[n])goto done;
  seen[n]=1;
  if(n>largest)largest=n;
  if(!read_line(j,name,n,j->lines[n-1],&j->ack_identity[n-1],j->ack_raw_sha[n-1]))goto done;
 }
 for(unsigned k=1;k<=largest;k++){if(!seen[k])goto done;
 j->pointers[k-1]=j->lines[k-1];
 }
 if(largest&&!wh_journal_check(j->binding,j->gates,j->pointers,largest))goto done;
 memset(&j->tip,0,sizeof(j->tip));
 j->tip.line_count=largest;
 wh_sha256_hex(manifest,strlen(manifest),j->tip.manifest_sha);
 if(largest)wh_sha256_hex(j->lines[largest-1],strlen(j->lines[largest-1]),j->tip.last_line_sha);
 else{memset(j->tip.last_line_sha,'0',64);
 j->tip.last_line_sha[64]=0;
 }
 if(!pc02_floor_read(j->lease,j->pending,&j->floor)||j->floor.count>largest||strcmp(j->floor.manifest,j->tip.manifest_sha))goto done;
 if(j->floor.count){char sha[65];
 wh_sha256_hex(j->lines[j->floor.count-1],strlen(j->lines[j->floor.count-1]),sha);
  if(strcmp(sha,j->floor.last_line_sha256))goto done;
  }
 for(uint64_t k=1;k<=j->floor.count;k++){
  char sha[65];
  wh_sha256_hex(j->lines[k-1],strlen(j->lines[k-1]),sha);
  if(!pc02_floor_check_ack(j->lease,j->pending,k,sha,&j->ack_identity[k-1],j->ack_raw_sha[k-1]))goto done;
 }
 if(!exact(j))goto done;
 j->count=largest;
 ok=1;
done:
 if(closedir(directory))ok=0;
 return ok;
}
int pc02j_catchup(pc02_journal *j,pc02_cap *cap){
 if(!pc02_cap_check(j->lease,cap)||!pc02j_scan(j))return 0;
 wh3_tip before=j->tip;
 while(j->floor.count<j->count){
  char sha[65];
  pc02_floor after;
  size_t at=(size_t)j->floor.count;
  wh_sha256_hex(j->lines[at],strlen(j->lines[at]),sha);
  if(!pc02_floor_advance_ack(j->lease,cap,&j->floor,sha,&j->ack_identity[at],j->ack_raw_sha[at],&after))return 0;
  j->floor=after;
 }
 return pc02_floor_confirm(j->lease,cap,&j->floor)&&pc02j_scan(j)&&tip_equal(&before,&j->tip);
}
static int write_all(int fd,const char *line,size_t size){
 size_t at=0;
 while(at<size){ssize_t n=pwrite(fd,line+at,size-at,(off_t)at);
 if(n<0&&errno==EINTR)continue;
 if(n<=0)return 0;
 at+=(size_t)n;
 }
 return 1;
}
static size_t make_record(pc02_journal *j,unsigned ordinal,const pc02_identity *id,const char *line,size_t n,unsigned char *bytes,char raw_sha[65]){
 char sha[65];
 memset(bytes,0,PJ_HEAD);
 memcpy(bytes,"PC02ACK1",8);
 pc02io_putid(bytes+8,id);
 pc02io_put64(bytes+24,ordinal);
 memcpy(bytes+32,j->manifest_sha,64);
 memcpy(bytes+96,j->pending->input,64);
 memcpy(bytes+160,j->pending->seal,64);
 pc02io_put64(bytes+224,n);
 wh_sha256_hex(line,n,sha);
 memcpy(bytes+232,sha,64);
 memcpy(bytes+PJ_HEAD,line,n);
 wh_sha256_hex(bytes,PJ_HEAD+n,sha);
 memcpy(bytes+PJ_HEAD+n,sha,64);
 wh_sha256_hex(bytes,PJ_HEAD+n+64,raw_sha);
 return PJ_HEAD+n+64;
}
static int publish(int fd,const char *from,const char *to){
#if defined(__APPLE__)
 return renameatx_np(fd,from,fd,to,RENAME_EXCL)==0;
#elif defined(__linux__) && defined(SYS_renameat2)
 return syscall(SYS_renameat2,fd,from,fd,to,1u)==0;
#else
 (void)fd;
 (void)from;
 (void)to;
 return 0;
#endif
}
static void cut(pc02_journal *j,unsigned phase){if(j->phase)j->phase(j->context,phase);
}
wh3_tx_status pc02j_append(pc02_journal *j,pc02_cap *cap,const wh3_tip *expected,const char *line,wh3_tip *out){
 int fd=-1,ok=0;
 char final[32],temp[64],readback[EXR_WH_LINE_MAX],wanted_raw[65],actual_raw[65];
 unsigned char record[PJ_HEAD+EXR_WH_LINE_MAX+64];
 size_t record_size=0;
 pc02_identity id,actual;
 size_t size=line?strlen(line):0;
 if(!j||!expected||!out||!size||size>=EXR_WH_LINE_MAX||!pc02_cap_check(j->lease,cap)||!pc02j_scan(j))return WH3_TX_UNCERTAIN;
 if(!tip_equal(expected,&j->tip))return WH3_TX_MISMATCH;
 if(j->count>=256||j->floor.count!=j->count)return WH3_TX_UNCERTAIN;
 strcpy(j->lines[j->count],line);
 j->pointers[j->count]=j->lines[j->count];
 if(!wh_journal_check(j->binding,j->gates,j->pointers,j->count+1))return WH3_TX_UNCERTAIN;
 snprintf(final,sizeof(final),"ack-%03u",(unsigned)j->count+1);
 for(unsigned k=0;k<1024;k++){
  snprintf(temp,sizeof(temp),".pending-%ld-%u",(long)getpid(),++j->serial);
  fd=openat(j->directory,temp,O_RDWR|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
  if(fd>=0)break;
  if(errno!=EEXIST)return WH3_TX_UNCERTAIN;
 }
 if(fd<0||!identity(fd,0,&id))goto done;
 record_size=make_record(j,(unsigned)j->count+1,&id,line,size,record,wanted_raw);
 if(!write_all(fd,(const char *)record,record_size))goto done;
 cut(j,1601);
 if(fsync(fd)||!read_line(j,temp,(unsigned)j->count+1,readback,&actual,actual_raw)||!same(&id,&actual)||
    strcmp(line,readback)||strcmp(wanted_raw,actual_raw))goto done;
 cut(j,1602);
 if(!pc02_cap_check(j->lease,cap)||!exact(j)||!publish(j->directory,temp,final))goto done;
 cut(j,1603);
 if(fsync(j->directory)||!read_line(j,final,(unsigned)j->count+1,readback,&actual,actual_raw)||!same(&id,&actual)||
    strcmp(line,readback)||strcmp(wanted_raw,actual_raw))goto done;
 cut(j,1604);
 wh3_tip desired=*expected;
 desired.line_count++;
 wh_sha256_hex(line,size,desired.last_line_sha);
 pc02_floor floor;
 if(!pc02_floor_advance_ack(j->lease,cap,&j->floor,desired.last_line_sha,&id,actual_raw,&floor)||!pc02j_scan(j)||
    !tip_equal(&j->tip,&desired)||j->floor.count!=desired.line_count)goto done;
 cut(j,1605);
 *out=desired;
 ok=1;
done:
 if(fd>=0&&close(fd))ok=0;
 return ok?WH3_TX_OK:WH3_TX_UNCERTAIN;
}
int pc02j_close(pc02_journal *j){if(!j||j->directory<0)return 1;
int ok=close(j->directory)==0;
j->directory=-1;
return ok;
}
