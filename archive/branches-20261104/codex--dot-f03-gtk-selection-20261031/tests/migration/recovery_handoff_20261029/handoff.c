/* SPDX-License-Identifier: MIT
 * Actions-only POSIX handoff consumer, never a production recovery command.
 * Reuse the frozen public SQLite serializer and bounded file utilities, not its
 * capture/verification decisions. No inherited SDK handle reaches a scanner.
 */
#define _GNU_SOURCE 1
#define _DARWIN_C_SOURCE 1
#define main frozen_preflight_main
#include "../recovery_preflight_20261029/probe.c"
#undef main
#include <dirent.h>
#include <signal.h>
#include <spawn.h>
#include <sys/file.h>
#include <sys/resource.h>
#include <sys/wait.h>
#ifdef __APPLE__
#include <sys/mount.h>
#else
#include <sys/vfs.h>
#endif

extern char **environ;
#define H_TOTAL (512ull*1024*1024)
#define H_RECORDS 32
#define H_PATHS 128
#define H_MAGIC "EXRHANDOFF1"
enum { H_BASE=1,H_PREPARED=2,H_MIRROR=3,H_ACK=4,H_FRESH=5,H_RESTORE_PREP=6,H_RESTORED=7 };
static const char *hnames[]={"baseline.bin","catalog.bin","catalog7.bin",
  "pending.original","mirror.preimage","plan1.json","plan2.json","pack.original"};
typedef struct {
  char magic[16],self[33],root_id[33],target_id[33],nonce[33];
  lm_mirror_file input[8],scanner,lease,barrier,mirror;
  unsigned char reserved[32];
  char seal[65];
} HAnchor;
typedef struct {
  char magic[16],self[33],previous[65],run[33],parent[33];
  uint32_t ordinal,phase,work,version;
  lm_mirror_file before,after,baseline;
  unsigned char reserved[32];
  char seal[65];
} HRecord;
_Static_assert(sizeof(HAnchor)<=8192,"anchor bound");
_Static_assert(sizeof(HRecord)<=8192,"record bound");
static HAnchor ha;
static HRecord hr[H_RECORDS];
static lm_mirror_file hrecid[H_RECORDS],hanchorid;
static unsigned hcount;
static int hlease=-1,hopen,hattempt,hrollback=-1,hcommit=-1,hnative,hchild_status=-1;
static int hbackup_steps,hbackup_pages,hbackup_reserved,hcancel,hguard_opens,hguard_outputs;
static uint64_t hbytes,hblocks,hreserve;
static const char *hctl,*hscanner,*hrun,*hentry;
static char hbarrier[4096],hphase[64]="start",hroute[8]="none";
static double hstart;
static const char *hfilesystem="unqualified";
static int hactive_owner,hquarantined,hrace_seen;
static int hstage(const char *s);
static double hnow(void){struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t)){reject("monotonic-clock-read");return -1;}return t.tv_sec+t.tv_nsec/1e9;}
static int hpath(char *out,const char *base,const char *name){
  if(snprintf(out,4096,"%s/%s",base,name)>=4096){reject("path-bound");return 0;}return 1;
}
static int htoken(const char *s){size_t i;if(strlen(s)!=32)return 0;for(i=0;i<32;i++)if(!strchr("0123456789abcdef",s[i]))return 0;return 1;}
static int hz(const char *s,size_t n){return memchr(s,0,n)!=NULL;}
static int hidvalid(const lm_mirror_file *f){return (f->present==0||f->present==1)&&hz(f->identity,sizeof(f->identity))&&hz(f->sha,sizeof(f->sha));}
static int hdir(const char *path,char id[33]){
  struct stat s;if(lstat(path,&s)||!S_ISDIR(s.st_mode)||s.st_uid!=geteuid()||(s.st_mode&077)!=0){reject("private-directory-custody");return 0;}
  if(id)snprintf(id,33,"%016llx%016llx",(unsigned long long)s.st_dev,(unsigned long long)s.st_ino);return 1;
}
static int hsnapshot(const char *path,int hash,lm_mirror_file *f,char **bytes,size_t *size){
  struct stat s,opened,after,entry;char before[33],actual[33],digest[65];int fd=-1;lm_sha sha;lm_sb data;unsigned char buffer[8192];size_t total=0;ssize_t n;
  memset(f,0,sizeof(*f));if(bytes)*bytes=NULL;if(size)*size=0;lm_sb_init(&data);
  if(lstat(path,&s)){
    if(errno==ENOENT)return 1;reject("file-precheck-stat");return 0;
  }
  if(!S_ISREG(s.st_mode)||s.st_uid!=geteuid()||s.st_nlink!=1||s.st_size<0){reject("file-precheck-custody-or-link");return 0;}
  snprintf(before,sizeof(before),"%016llx%016llx",(unsigned long long)s.st_dev,(unsigned long long)s.st_ino);
  if(!hash){f->present=1;strcpy(f->identity,before);f->size=(uint64_t)s.st_size;return 1;}
  if(ha.target_id[0]&&!strcmp(before,ha.target_id)){reject("input-aliases-sdk-target");return 0;}
  if(hactive_owner&&!hrace_seen&&!strcmp(fault,"snapshot-race")){
    char watched[4096];hpath(watched,root,"pending.original");if(!strcmp(path,watched)){hrace_seen=1;if(!hstage("snapshot-race"))return 0;}
  }
  fd=open(path,O_RDONLY|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC);if(fd<0){hnative=errno;reject("file-open");return 0;}
  if(fstat(fd,&opened)){/* An unknown fd must not be closed while it could be the
                        * SDK inode. Bound and quarantine until process exit. */
    hquarantined++;reject("file-fstat-unknown-quarantined");return 0;}
  snprintf(actual,sizeof(actual),"%016llx%016llx",(unsigned long long)opened.st_dev,(unsigned long long)opened.st_ino);
  if(ha.target_id[0]&&!strcmp(actual,ha.target_id)){
    /* Crucial POSIX rule: even a failed alias open must NOT be closed under the
       process's SQLite fcntl writer. CLOEXEC + process-exit quarantine, not an
       optimistic pre-lstat/close. This attempt cannot subsequently COMMIT. */
    hquarantined++;reject("opened-target-alias-quarantined");return 0;
  }
  if(strcmp(before,actual)||!S_ISREG(opened.st_mode)||opened.st_uid!=geteuid()||opened.st_nlink!=1||opened.st_size<0||(uint64_t)opened.st_size>LIMIT){reject("opened-file-custody-or-bound");goto done;}
  lm_sha_init(&sha);
  while((n=read(fd,buffer,sizeof(buffer)))>0){
    if((size_t)n>LIMIT-total){reject("file-read-bound");goto done;}lm_sha_add(&sha,buffer,(size_t)n);
    if(bytes){lm_sb_add(&data,(const char*)buffer,(size_t)n);if(data.oom){reject("file-allocation");goto done;}}total+=(size_t)n;
  }
  if(n<0||total!=(size_t)opened.st_size){reject("file-read");goto done;}lm_sha_hex(&sha,f->sha);
  if(lseek(fd,0,SEEK_SET)<0){reject("file-rehash-seek");goto done;}lm_sha_init(&sha);total=0;
  while((n=read(fd,buffer,sizeof(buffer)))>0){if((size_t)n>LIMIT-total){reject("file-rehash-bound");goto done;}lm_sha_add(&sha,buffer,(size_t)n);total+=(size_t)n;}
  lm_sha_hex(&sha,digest);
  if(n<0||total!=(size_t)opened.st_size||strcmp(digest,f->sha)||fstat(fd,&after)||lstat(path,&entry)||
     opened.st_dev!=after.st_dev||opened.st_ino!=after.st_ino||opened.st_size!=after.st_size||
     opened.st_mtime!=after.st_mtime||opened.st_ctime!=after.st_ctime||
     entry.st_dev!=opened.st_dev||entry.st_ino!=opened.st_ino||entry.st_nlink!=1||!S_ISREG(entry.st_mode)){
    reject("file-final-identity-or-bytes");goto done;}
  f->present=1;strcpy(f->identity,actual);f->size=total;
  if(bytes){*bytes=data.p;data.p=NULL;if(!*bytes){*bytes=malloc(1);if(!*bytes){reject("empty-file-allocation");goto done;}(*bytes)[0]=0;}if(size)*size=total;}
done:
  if(close(fd))reject("owned-file-close");lm_sb_free(&data);return !failed;
}
static int hsnap(const char *path,int hash,lm_mirror_file *f){return hsnapshot(path,hash,f,NULL,NULL);}
static int hread(const char *path,char **p,size_t *n){lm_mirror_file f;if(!hsnapshot(path,1,&f,p,n)||!f.present){reject("owned-evidence-read");return 0;}return 1;}
static int hsame(const char *path,const lm_mirror_file *f,int hash){lm_mirror_file now;
  if(!hsnap(path,hash,&now))return 0;
  if(!lm_mirror_same_file(f,&now)||(hash&&!lm_mirror_same_bytes(f,&now))){reject("owned-identity-or-bytes-changed");return 0;}return 1;
}
static int hinventory_walk(const char *dir,unsigned *paths,unsigned depth){
  DIR *d;struct dirent *e;struct stat s;char p[4096];
  if(depth>3||!hdir(dir,NULL)){reject("namespace-depth");return 0;}d=opendir(dir);if(!d){reject("inventory-open");return 0;}
  while((e=readdir(d))!=NULL&&!failed){
    if(!strcmp(e->d_name,".")||!strcmp(e->d_name,".."))continue;
    if(++*paths>H_PATHS){reject("path-count-budget");break;}
    if(!hpath(p,dir,e->d_name)||lstat(p,&s)){reject("inventory-stat");break;}
    if(S_ISDIR(s.st_mode)){if(!hinventory_walk(p,paths,depth+1))break;continue;}
    if(!S_ISREG(s.st_mode)||s.st_uid!=geteuid()||s.st_nlink!=1||(s.st_mode&077)!=0||s.st_size<0){reject("namespace-mode-link-or-special");break;}
    if((uint64_t)s.st_size>H_TOTAL-hbytes||(uint64_t)s.st_blocks>H_TOTAL/512-hblocks){reject("cumulative-byte-budget");break;}
    hbytes+=(uint64_t)s.st_size;hblocks+=(uint64_t)s.st_blocks;
  }
  if(closedir(d))reject("inventory-close");return !failed;
}
static int hinventory(uint64_t reserve){unsigned paths=0;hbytes=hblocks=0;
  if(!hinventory_walk(root,&paths,0))return 0;
  if(reserve>H_TOTAL||hbytes>H_TOTAL-reserve||hblocks*512>H_TOTAL-reserve){reject("allocation-reservation-budget");return 0;}
  hreserve=reserve;return 1;
}
static int hsyncdir(const char *dir,int inject){int fd=open(dir,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC),rc;
  if(fd<0){hnative=errno;reject("parent-open");return 0;}
  if(inject){if(close(fd)){hnative=errno;reject("calibration-close");return 0;}errno=0;rc=fsync(fd);hnative=errno;
    if(rc==0||hnative!=EBADF){reject("sync-ebadf-not-calibrated");return 0;}reject("actual-sync-descriptor-ebadf");return 0;}
  rc=fsync(fd);if(rc){hnative=errno;reject("parent-sync");}if(close(fd)){hnative=errno;reject("parent-close");}return !failed;
}
static int hsyncfile(const char *path){int fd=open(path,O_RDONLY|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC);
  if(fd<0){hnative=errno;reject("owned-evidence-sync-open");return 0;}
  {struct stat s;char id[33];if(fstat(fd,&s)){hquarantined++;reject("sync-fstat-unknown-quarantined");return 0;}
    snprintf(id,sizeof(id),"%016llx%016llx",(unsigned long long)s.st_dev,(unsigned long long)s.st_ino);
    if(ha.target_id[0]&&!strcmp(id,ha.target_id)){hquarantined++;reject("sync-target-alias-quarantined");return 0;}
    if(!S_ISREG(s.st_mode)||s.st_nlink!=1||s.st_uid!=geteuid()){close(fd);reject("sync-file-custody");return 0;}}
  if(fsync(fd)){hnative=errno;reject("owned-evidence-file-sync");}if(close(fd))reject("owned-evidence-sync-close");return !failed;
}
static int hnew(const char *path,const void *p,size_t n,int durable){
  int fd;size_t off=0;if(n>LIMIT||!hinventory(n))return 0;
  fd=open(path,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
  if(fd<0){hnative=errno;reject("exclusive-create");return 0;}
  while(off<n){ssize_t k=write(fd,(const char*)p+off,n-off);if(k<=0){hnative=errno;reject("write");break;}off+=(size_t)k;}
  if(durable&&fsync(fd)){hnative=errno;reject("file-sync");}if(close(fd)){hnative=errno;reject("file-close");}
  if(!failed&&durable){char parent[4096],*slash;snprintf(parent,sizeof(parent),"%s",path);slash=strrchr(parent,'/');if(slash)*slash=0;else strcpy(parent,".");return hsyncdir(parent,0);}
  return !failed;
}
static int hstage(const char *s){
  char ready[4096],go[4096],base[128];int fd;double until=hnow()+30;struct timespec pause={0,10000000};
  snprintf(hphase,sizeof(hphase),"%s",s);snprintf(base,sizeof(base),"%s.ready",s);hpath(ready,hctl,base);snprintf(base,sizeof(base),"%s.go",s);hpath(go,hctl,base);
  fd=open(ready,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);if(fd<0){reject("rendezvous-create");return 0;}
  if(write(fd,s,strlen(s))!=(ssize_t)strlen(s)){reject("rendezvous-write");}if(close(fd))reject("rendezvous-close");
  while(!failed&&hnow()<until&&hnow()-hstart<120){
    struct stat s;if(!lstat(go,&s)){char *token=NULL;size_t n=0;int valid=hread(go,&token,&n)&&n>=8&&n<=9&&!memcmp(token,"continue",8);free(token);
      if(valid)return 1;reject("rendezvous-token");return 0;}
    if(errno!=ENOENT){reject("rendezvous-read");return 0;}nanosleep(&pause,NULL);
  }reject("rendezvous-deadline");return 0;
}
static void hfailed_pause(const char *phase){int prior=failed;const char *why=reason;failed=0;hstage(phase);failed=1;if(prior)reason=why;}
static int htarget(void){lm_mirror_file t,side;char p[4096];const char *suffix[]={"-journal","-wal","-shm"};unsigned i;
  if(!hsnap(target,0,&t)||!t.present||strcmp(t.identity,ha.target_id)){reject("target-identity");return 0;}
  for(i=0;i<3;i++){if(snprintf(p,sizeof(p),"%s%s",target,suffix[i])>=4096){reject("sidecar-path");return 0;}
    if(!hsnap(p,0,&side))return 0;if(side.present&&!strcmp(t.identity,side.identity)){reject("sidecar-alias");return 0;}}
  return 1;
}
static int hrecord_name(char path[4096],unsigned n){char name[40];snprintf(name,sizeof(name),"record-%02u.bin",n);return hpath(path,root,name);}
static int hread_fixed(const char *path,void *out,size_t n){char *p=NULL;size_t z=0;int ok=hread(path,&p,&z);if(ok&&z==n)memcpy(out,p,n);else{reject("record-size");ok=0;}free(p);return ok;}
static int hfile_record(const char *path,void *data,size_t n,char self[33],char seal[65],int durable){
  int fd;struct stat st;size_t off=0;if(n>8192||!hinventory(n))return 0;
  fd=open(path,O_RDWR|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);if(fd<0){hnative=errno;reject("record-create");return 0;}
  if(fstat(fd,&st)){reject("record-fstat");close(fd);return 0;}
  snprintf(self,33,"%016llx%016llx",(unsigned long long)st.st_dev,(unsigned long long)st.st_ino);
  memset(seal,0,65);lm_sha_bytes(data,n,seal);
  while(off<n){ssize_t k=write(fd,(const char*)data+off,n-off);if(k<=0){hnative=errno;reject("record-write");break;}off+=(size_t)k;}
  if(durable&&fsync(fd)){hnative=errno;reject("record-sync");}if(close(fd)){hnative=errno;reject("record-close");}
  return !failed&&(!durable||hsyncdir(root,0));
}
static int hseal(void *data,size_t n,char seal[65]){char saved[65],digest[65];
  if(!hz(seal,65)||strlen(seal)!=64){reject("record-seal-format");return 0;}memcpy(saved,seal,65);memset(seal,0,65);lm_sha_bytes(data,n,digest);memcpy(seal,saved,65);
  if(strcmp(saved,digest)){reject("record-seal-mismatch");return 0;}return 1;
}
static int hinputs(void){char p[4096],id[33];unsigned i,j;lm_mirror_file current;
  if(!hdir(root,id)||strcmp(id,ha.root_id)){reject("root-identity");return 0;}
  for(i=0;i<8;i++){hpath(p,root,hnames[i]);if(!ha.input[i].present||!hsame(p,&ha.input[i],1))return 0;
    for(j=0;j<i;j++)if(!strcmp(ha.input[i].identity,ha.input[j].identity)){reject("input-alias");return 0;}}
  if(!hsame(hscanner,&ha.scanner,1)||!hsame(hbarrier,&ha.barrier,1))return 0;
  hpath(p,root,"lease");if(!hsame(p,&ha.lease,1))return 0;
  if(!hsnap(target,0,&current)||!current.present||strcmp(current.identity,ha.target_id)){reject("target-identity");return 0;}
  return htarget()&&hinventory(0);
}
static int hchain(void){char p[4096],prev[65];HRecord r;lm_mirror_file f;unsigned i;char zero[32]={0};
  hcount=0;lm_sha_bytes(&ha,sizeof(ha),prev);
  hpath(p,root,"anchor.bin");if(!hsame(p,&hanchorid,1)||!hinputs())return 0;
  {DIR *d=opendir(root);struct dirent *entry;if(!d){reject("record-directory");return 0;}
    while((entry=readdir(d))!=NULL){if(!strncmp(entry->d_name,"record-",7)){
      unsigned n;
      if(strlen(entry->d_name)!=13||entry->d_name[7]<'0'||entry->d_name[7]>'9'||entry->d_name[8]<'0'||entry->d_name[8]>'9'||strcmp(entry->d_name+9,".bin")){reject("unknown-record-name");break;}
      n=(unsigned)(entry->d_name[7]-'0')*10+(unsigned)(entry->d_name[8]-'0');if(n>=H_RECORDS){reject("unknown-record-number");break;}}}
    if(closedir(d))reject("record-directory-close");if(failed)return 0;}
  for(i=0;i<H_RECORDS;i++){
    hrecord_name(p,i);if(!hsnap(p,1,&f))return 0;
    if(!f.present){unsigned j;for(j=i+1;j<H_RECORDS;j++){hrecord_name(p,j);if(lm_path_state(p)!=0){reject("record-gap");return 0;}}break;}
    if(!hread_fixed(p,&r,sizeof(r))||!hz(r.magic,sizeof(r.magic))||!hz(r.self,sizeof(r.self))||!hz(r.previous,sizeof(r.previous))||!hz(r.run,sizeof(r.run))||!hz(r.parent,sizeof(r.parent))||!hidvalid(&r.before)||!hidvalid(&r.after)||!hidvalid(&r.baseline)||strcmp(r.magic,H_MAGIC)||strcmp(r.self,f.identity)||strcmp(r.previous,prev)||r.ordinal!=i||r.version!=1||!htoken(r.run)||memcmp(r.reserved,zero,32)){
      reject("record-chain-binding");return 0;}
    if(!hseal(&r,sizeof(r),r.seal))return 0;
    if(i==0){if(r.phase!=H_BASE||r.work!=1||strcmp(r.parent,ha.nonce)){reject("record-base");return 0;}}
    else {
      HRecord *prior=&hr[i-1];
      if(strcmp(r.parent,prior->run)||r.work<1||r.work>2){reject("record-parent");return 0;}
      if(r.phase==H_FRESH){if(prior->phase!=H_ACK||r.work!=prior->work+1){reject("record-fresh-order");return 0;}}
      else if(r.phase==H_PREPARED){if((prior->phase!=H_BASE&&prior->phase!=H_FRESH&&prior->phase!=H_RESTORED)||r.work!=prior->work){reject("record-prepared-order");return 0;}}
      else if(r.phase==H_MIRROR){if(prior->phase!=H_PREPARED||r.work!=prior->work||memcmp(&r.after,&prior->after,sizeof(r.after))){reject("record-mirror-order");return 0;}}
      else if(r.phase==H_ACK){if(prior->phase!=H_MIRROR||r.work!=prior->work||memcmp(&r.after,&prior->after,sizeof(r.after))){reject("record-ack-order");return 0;}}
      else if(r.phase==H_RESTORE_PREP){if(prior->phase!=H_MIRROR||r.work!=prior->work||memcmp(&r.before,&prior->after,sizeof(r.before))){reject("record-restore-order");return 0;}}
      else if(r.phase==H_RESTORED){if(prior->phase!=H_RESTORE_PREP||r.work!=prior->work||memcmp(&r.after,&prior->after,sizeof(r.after))){reject("record-restored-order");return 0;}}
      else {reject("record-phase");return 0;}
    }
    if(r.phase==H_FRESH){char name[96];snprintf(name,sizeof(name),"scan-%s/baseline.bin",r.run);hpath(p,root,name);if(!hsame(p,&r.baseline,1))return 0;}
    if(r.phase==H_RESTORE_PREP){char name[96];snprintf(name,sizeof(name),"archive-%s",r.run);hpath(p,root,name);if(!hsame(p,&r.baseline,1))return 0;}
    hr[i]=r;hrecid[i]=f;strcpy(prev,f.sha);hcount=i+1;
  }
  if(!hcount){reject("baseline-not-durable");return 0;}return !failed;
}
static int happend(unsigned phase,unsigned work,const lm_mirror_file *before,const lm_mirror_file *after,const lm_mirror_file *base,int durable){
  HRecord r;char p[4096];if(hcount>=H_RECORDS){reject("record-count-budget");return 0;}memset(&r,0,sizeof(r));
  strcpy(r.magic,H_MAGIC);r.ordinal=hcount;r.phase=phase;r.work=work;r.version=1;strcpy(r.run,hrun);
  if(hcount){strcpy(r.previous,hrecid[hcount-1].sha);strcpy(r.parent,hr[hcount-1].run);}else{lm_sha_bytes(&ha,sizeof(ha),r.previous);strcpy(r.parent,ha.nonce);}
  if(before)r.before=*before;if(after)r.after=*after;if(base)r.baseline=*base;
  hrecord_name(p,hcount);if(!hfile_record(p,&r,sizeof(r),r.self,r.seal,durable)||!hsnap(p,1,&hrecid[hcount]))return 0;
  hr[hcount++]=r;return 1;
}
static int hlease_take(int create){char p[4096],fdid[33];struct stat s;lm_mirror_file f;
  hpath(p,root,"lease");if(create&&!hnew(p,hrun,32,1))return 0;
  if(!hsnap(p,1,&f)||!f.present){reject("lease-missing");return 0;}
  if(!strcmp(fault,"lease-replace")&&!hstage("lease-snapshot"))return 0;
  hlease=open(p,O_RDWR|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC);if(hlease<0){hnative=errno;reject("lease-open");return 0;}
  if(fstat(hlease,&s)||s.st_nlink!=1||s.st_uid!=geteuid()||(s.st_mode&077)||!(fcntl(hlease,F_GETFD)&FD_CLOEXEC)){reject("lease-fd-custody");return 0;}
  snprintf(fdid,sizeof(fdid),"%016llx%016llx",(unsigned long long)s.st_dev,(unsigned long long)s.st_ino);
  if(strcmp(fdid,f.identity)){reject("lease-open-fd-identity");return 0;}
  if(flock(hlease,LOCK_EX|LOCK_NB)){hnative=errno;reject("lease-busy");return 0;}
  if(!hsame(p,&f,1))return 0;
  if(create)ha.lease=f;else if(!lm_mirror_same_file(&ha.lease,&f)||!lm_mirror_same_bytes(&ha.lease,&f)){reject("lease-binding");return 0;}
  /* Deliberately never close/unlock hlease: process exit is the boundary. */
  return 1;
}
static int hinit(void){char p[4096];lm_mirror_file t;unsigned i;
  memset(&ha,0,sizeof(ha));strcpy(ha.magic,H_MAGIC);strcpy(ha.nonce,hrun);
  if(!hdir(root,ha.root_id)||!hsnap(target,0,&t)||!t.present)return 0;strcpy(ha.target_id,t.identity);
  for(i=0;i<8;i++){hpath(p,root,hnames[i]);if(!hsnap(p,1,&ha.input[i])||!ha.input[i].present){reject("initial-provenance-missing");return 0;}}
  if(!hsnap(hscanner,1,&ha.scanner)||!ha.scanner.present||!hlease_take(1))return 0;
  if(!hnew(hbarrier,hrun,32,1)||!hsnap(hbarrier,1,&ha.barrier))return 0;
  hpath(p,root,"mirror.json");if(!hsnap(p,1,&ha.mirror))return 0;
  hpath(p,root,"anchor.bin");if(!hfile_record(p,&ha,sizeof(ha),ha.self,ha.seal,0)||!hsnap(p,1,&hanchorid)||!hstage("S1"))return 0;
  hsyncfile(p);
  for(i=0;i<8&&!failed;i++){hpath(p,root,hnames[i]);hsyncfile(p);}
  if(ha.mirror.present&&!failed){hpath(p,root,"mirror.json");hsyncfile(p);}
  if(failed||!hsyncdir(root,0)||!happend(H_BASE,1,NULL,&ha.mirror,&ha.input[0],1)||!hstage("S2"))return 0;
  return hchain();
}
static int hload(void){char p[4096],zero[32]={0};unsigned i;
  hpath(p,root,"anchor.bin");if(!hsnap(p,1,&hanchorid)||!hanchorid.present||!hread_fixed(p,&ha,sizeof(ha))){reject("anchor-provenance-missing-or-invalid");return 0;}
  if(!hz(ha.magic,sizeof(ha.magic))||!hz(ha.self,sizeof(ha.self))||!hz(ha.root_id,sizeof(ha.root_id))||!hz(ha.target_id,sizeof(ha.target_id))||!hz(ha.nonce,sizeof(ha.nonce))||strcmp(ha.magic,H_MAGIC)||strcmp(ha.self,hanchorid.identity)||!htoken(ha.nonce)||memcmp(ha.reserved,zero,32)){reject("anchor-binding");return 0;}
  if(!hseal(&ha,sizeof(ha),ha.seal))return 0;
  for(i=0;i<8;i++)if(!hidvalid(&ha.input[i])){reject("anchor-input-format");return 0;}
  if(!hidvalid(&ha.scanner)||!hidvalid(&ha.lease)||!hidvalid(&ha.barrier)||!hidvalid(&ha.mirror)){reject("anchor-artifact-format");return 0;}
  if(!hlease_take(0)||!hchain())return 0;
  /* A visible complete ACK is not necessarily durable. Re-establish file and
     directory ordering before opening a successor owner; never infer sync. */
  for(i=0;i<=hcount;i++){if(i==hcount)hpath(p,root,"anchor.bin");else hrecord_name(p,i);if(!hsyncfile(p))return 0;}
  if(!hsyncdir(root,0)||!hchain())return 0;
  if(hr[hcount-1].phase==H_ACK){hpath(p,root,"mirror.json");if(!hsame(p,&hr[hcount-1].after,1)||!hsyncfile(p)||!hsyncdir(root,0))return 0;}
  return !failed;
}
static int hgate(void){char p[4096];hpath(p,root,"anchor.bin");
  if(!strcmp(hentry,"help")||!strcmp(hentry,"version")||!strcmp(hentry,"inspect-no-target"))return 1;
  if(lm_path_state(p)!=0||lm_path_state(hbarrier)!=0){reject("pre-open-policy-refusal");return 0;}
  reject("no-provenance-no-admission");return 0;
}
static int hpipe(int pair[2]){if(pipe(pair)){hnative=errno;reject("pipe-create");return 0;}
  if(fcntl(pair[0],F_SETFD,FD_CLOEXEC)||fcntl(pair[1],F_SETFD,FD_CLOEXEC)||fcntl(pair[0],F_SETFL,O_NONBLOCK)){reject("pipe-flags");close(pair[0]);close(pair[1]);pair[0]=pair[1]=-1;return 0;}return 1;}
static int hdrain(int from,int to,size_t *total){char b[4096];ssize_t n;
  for(;;){n=read(from,b,sizeof(b));if(n==0||(n<0&&(errno==EAGAIN||errno==EWOULDBLOCK)))return 1;
    if(n<0){if(errno==EINTR)continue;reject("scanner-pipe-read");return 0;}
    if((size_t)n>65536-*total){reject("scanner-log-hard-bound");return 0;}
    {size_t off=0;while(off<(size_t)n){ssize_t k=write(to,b+off,(size_t)n-off);if(k<=0){reject("scanner-log-write");return 0;}off+=(size_t)k;}}
    *total+=(size_t)n;
  }
}
static int hscan(unsigned work,lm_mirror_file *out){
  char dir[4096],name[80],cat[4096],op[4096],ep[4096],envelope[4096],dest[4096],report[4096];
  int ofd=-1,efd=-1,rc,st=0,success=0,opipe[2]={-1,-1},epipe[2]={-1,-1};size_t log_bytes=0;pid_t pid=-1;posix_spawn_file_actions_t fa;posix_spawnattr_t attr;
  lm_mirror_file exe,env_id,output_id;lm_sb env;char *raw=NULL;size_t n=0;char error[128],dir_id[33],dir_now[33];jv *json=NULL;double end;
  snprintf(name,sizeof(name),"scan-%s",hrun);hpath(dir,root,name);
  if(!hinventory(2ull*LIMIT+16*1024*1024)||mkdir(dir,0700)){hnative=errno;reject("scanner-exclusive-directory");return 0;}
  hpath(cat,root,work==1?"catalog.bin":"catalog7.bin");hpath(dest,dir,"baseline.bin");hpath(report,dir,"report.json");
  hpath(op,hctl,"scanner.stdout.txt");hpath(ep,hctl,"scanner.stderr.txt");hpath(envelope,dir,"envelope.json");
  if(!hsnap(hscanner,1,&exe)||!lm_mirror_same_file(&exe,&ha.scanner)||!lm_mirror_same_bytes(&exe,&ha.scanner)){reject("scanner-executable-binding");return 0;}
  if(!hdir(dir,dir_id))return 0;
  lm_sb_init(&env);lm_sb_fmt(&env,"{\"nonce\":\"%s\",\"executable_sha\":\"%s\",\"target_id\":\"%s\",\"catalog_id\":\"%s\",\"catalog_sha\":\"%s\",\"root_id\":\"%s\",\"output_directory_id\":\"%s\",\"work\":%u,\"argv\":[",hrun,exe.sha,ha.target_id,ha.input[work==1?1:2].identity,ha.input[work==1?1:2].sha,ha.root_id,dir_id,work);
  {const char *args[]={hscanner,"scan",target,dir,cat,hrun,"none","qualification-only"};unsigned i;for(i=0;i<8;i++){if(i)lm_sb_str(&env,",");lm_sb_json(&env,args[i],strlen(args[i]));}lm_sb_str(&env,"]}");}
  if(env.oom||!hnew(envelope,env.p,env.n,1)||!hsnap(envelope,1,&env_id)){lm_sb_free(&env);return 0;}lm_sb_free(&env);
  if(!hstage("scanner-request")||!hsame(envelope,&env_id,1)||!hchain())return 0;
  ofd=open(op,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);efd=open(ep,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);
  if(ofd<0||efd<0){reject("scanner-log-open");goto done;}
  if(!hpipe(opipe)||!hpipe(epipe))goto done;
  rc=posix_spawn_file_actions_init(&fa);if(rc){hnative=rc;reject("spawn-actions");goto done;}
  rc=posix_spawnattr_init(&attr);if(rc){posix_spawn_file_actions_destroy(&fa);hnative=rc;reject("spawn-attributes");goto done;}
  rc=posix_spawn_file_actions_adddup2(&fa,opipe[1],STDOUT_FILENO);
  if(!rc)rc=posix_spawn_file_actions_adddup2(&fa,epipe[1],STDERR_FILENO);
#if defined(__APPLE__)
  if(!rc)rc=posix_spawnattr_setflags(&attr,POSIX_SPAWN_CLOEXEC_DEFAULT);
#elif defined(__linux__)
  if(!rc)rc=posix_spawn_file_actions_addclosefrom_np(&fa,3);
#else
#error "Native close-all spawn semantics must be qualified"
#endif
  if(rc){hnative=rc;reject("spawn-descriptor-isolation");}
  else {char *args[]={(char*)hscanner,"scan",(char*)target,dir,cat,(char*)hrun,"none","qualification-only",NULL};
    rc=posix_spawn(&pid,hscanner,&fa,&attr,args,environ);if(rc){hnative=rc;reject("spawn");}}
  posix_spawnattr_destroy(&attr);posix_spawn_file_actions_destroy(&fa);
  if(opipe[1]>=0){close(opipe[1]);opipe[1]=-1;}if(epipe[1]>=0){close(epipe[1]);epipe[1]=-1;}
  if(pid<0||failed)goto done;
  {char p[4096],b[64];hpath(p,hctl,"scanner.pid");snprintf(b,sizeof(b),"%ld\n",(long)pid);int fd=open(p,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);if(fd<0||write(fd,b,strlen(b))!=(ssize_t)strlen(b))reject("scanner-pid-output");if(fd>=0)close(fd);}
  if(!strcmp(fault,"scanner-paused")){
    if(kill(pid,SIGSTOP)||waitpid(pid,&st,WUNTRACED)!=pid||!WIFSTOPPED(st)){reject("scanner-stop-not-calibrated");goto done;}
    if(!hstage("scanner-live"))goto done;
  }
  if(!strcmp(fault,"kill-scanner")){kill(pid,SIGKILL);}
  end=hnow()+30;
  while(!failed){pid_t w;if(!hdrain(opipe[0],ofd,&log_bytes)||!hdrain(epipe[0],efd,&log_bytes))break;
    w=waitpid(pid,&st,WNOHANG);if(w==pid){pid=-1;hdrain(opipe[0],ofd,&log_bytes);hdrain(epipe[0],efd,&log_bytes);break;}if(w<0){reject("scanner-wait");break;}
    if(hnow()>end||hnow()-hstart>120){reject("scanner-deadline");break;}struct timespec pause={0,10000000};nanosleep(&pause,NULL);}
  hchild_status=st;
  if(pid>=0||!WIFEXITED(st)||WEXITSTATUS(st)){reject("scanner-status");goto done;}
  if(!hsame(envelope,&env_id,1)||!hsame(hscanner,&exe,1)||!hchain())goto done;
  if(!hstage("scanner-result")||!hsame(envelope,&env_id,1))goto done;
  if(!hread(op,&raw,&n)||n>65536){reject("scanner-report-bound");goto done;}
  json=lm_json_parse(raw,n,error,sizeof(error));if(!json||!lm_get_str(json,"mode")||strcmp(lm_get_str(json,"mode"),"scan")||!lm_get(json,"passed")||lm_get(json,"passed")->t!=J_BOOL||!lm_get(json,"passed")->b){reject("scanner-incomplete-report");goto done;}
  if(!hnew(report,raw,n,1)||!hsnap(dest,1,&output_id))goto done;
  if(!output_id.present){reject("scanner-baseline-output-missing");goto done;}
  if(!hstage("scanner-complete")||!hsame(dest,&output_id,1)||!hsame(envelope,&env_id,1)||!hdir(dir,dir_now)||strcmp(dir_id,dir_now)||!hchain()){reject("scanner-final-binding");goto done;}
  *out=output_id;success=1;
done:
  if(pid>=0){kill(pid,SIGKILL);while(waitpid(pid,&st,0)<0&&errno==EINTR){}hchild_status=st;}
  if(opipe[0]>=0){if(ofd>=0)hdrain(opipe[0],ofd,&log_bytes);close(opipe[0]);}if(opipe[1]>=0)close(opipe[1]);
  if(epipe[0]>=0){if(efd>=0)hdrain(epipe[0],efd,&log_bytes);close(epipe[0]);}if(epipe[1]>=0)close(epipe[1]);
  if(ofd>=0&&close(ofd))reject("scanner-stdout-close");if(efd>=0&&close(efd))reject("scanner-stderr-close");
  free(raw);lm_json_free(json);return success&&!failed;
}
static int hledger(exr_library *owner,unsigned work){char p[4096],*want=NULL;void *actual=NULL;size_t n=0,z=0;int found=0;exr_error e={0};
  hpath(p,root,work==1?"plan1.json":"plan2.json");if(!hread(p,&want,&n))return 0;
  sdk_status=exr_library_migration_ledger_get(owner,&actual,&z,&found,&e);
  if(sdk_status!=EXR_OK||!found||z!=n||memcmp(want,actual,n))reject("acknowledged-lineage-mismatch");
  free(want);exr_free(actual);return !failed;
}
static int hrestore(unsigned work){char dest[4096],copy[4096],archive[4096],source[4096],name[96];HRecord r;lm_mirror_file after,arch;char *data=NULL;size_t n=0;
  if(!hchain())return 0;r=hr[hcount-1];hpath(dest,root,"mirror.json");
  if(r.phase==H_MIRROR){
    if(work!=1||!hsame(dest,&r.after,1)){reject("restore-original-route");return 0;}
    snprintf(name,sizeof(name),"archive-%s",hrun);hpath(archive,root,name);
    if(!hread(dest,&data,&n)||!hnew(archive,data,n,1)||!hsnap(archive,1,&arch)){free(data);return 0;}free(data);data=NULL;
    memset(&after,0,sizeof(after));
    if(ha.mirror.present){
      snprintf(name,sizeof(name),"restore-%s",hrun);hpath(copy,root,name);hpath(source,root,"mirror.preimage");
      if(!hread(source,&data,&n)||!hnew(copy,data,n,1)||!hsnap(copy,1,&after)){free(data);return 0;}free(data);
      if(!lm_mirror_same_bytes(&after,&ha.mirror)){reject("restore-preimage-bytes");return 0;}
    }
    if(!happend(H_RESTORE_PREP,work,&r.after,&after,&arch,1))return 0;r=hr[hcount-1];
  }
  if(r.phase!=H_RESTORE_PREP){reject("restore-state");return 0;}
  if(!hstage("restore-prepared")||!hchain()||!htarget())return 0;r=hr[hcount-1];
  {lm_mirror_file current;if(!hsnap(dest,1,&current))return 0;
    if(lm_mirror_same_file(&current,&r.before)&&lm_mirror_same_bytes(&current,&r.before)){
      if(r.after.present){snprintf(name,sizeof(name),"restore-%s",r.run);hpath(copy,root,name);if(!hsame(copy,&r.after,1))return 0;if(rename(copy,dest)){hnative=errno;reject("restore-rename");return 0;}}
      else if(unlink(dest)){hnative=errno;reject("restore-unlink");return 0;}
    }else if(!lm_mirror_same_file(&current,&r.after)||!lm_mirror_same_bytes(&current,&r.after)){reject("restore-foreign-destination");return 0;}}
  if(!hstage("restore-published")||!hchain()||!hsame(dest,&r.after,1)||!hsyncdir(root,!strcmp(fault,"restore-sync")))return 0;
  return happend(H_RESTORED,work,NULL,&r.after,NULL,1);
}
static int hmirror(unsigned work){char dest[4096],copy[4096],plan[4096],name[64];lm_mirror_file before,after;char *bytes=NULL;size_t n=0;HRecord last;
  if(!hchain())return 0;last=hr[hcount-1];hpath(dest,root,"mirror.json");hpath(plan,root,work==1?"plan1.json":"plan2.json");
  if(last.phase==H_RESTORE_PREP){if(!hrestore(work))return 0;last=hr[hcount-1];}
  if(last.phase==H_BASE||last.phase==H_FRESH||last.phase==H_RESTORED){
    if(!hsnap(dest,1,&before)||!lm_mirror_same_file(&before,&last.after)||!lm_mirror_same_bytes(&before,&last.after)){reject("mirror-before-ownership");return 0;}
    snprintf(name,sizeof(name),"mirror-work-%u",work);hpath(copy,root,name);
    if(!hread(plan,&bytes,&n)||!hnew(copy,bytes,n,1)||!hsnap(copy,1,&after)){free(bytes);return 0;}free(bytes);
    if(!happend(H_PREPARED,work,&before,&after,NULL,1))return 0;last=hr[hcount-1];
  }
  if(last.phase==H_PREPARED){
    if(!hstage("S4")||!hchain()||!htarget())return 0;last=hr[hcount-1];
    if(!hsnap(dest,1,&before))return 0;
    snprintf(name,sizeof(name),"mirror-work-%u",work);hpath(copy,root,name);
    if(lm_mirror_same_file(&before,&last.before)&&lm_mirror_same_bytes(&before,&last.before)){
      if(!hsame(copy,&last.after,1))return 0;
      if(rename(copy,dest)){hnative=errno;reject("actual-mirror-rename-refusal");return 0;}
    }else if(!lm_mirror_same_file(&before,&last.after)||!lm_mirror_same_bytes(&before,&last.after)){reject("foreign-mirror-transition");return 0;}
    if(!hsame(dest,&last.after,1)||!hstage("mirror-published")||!hchain()||!hsame(dest,&last.after,1)||!hsyncdir(root,!strcmp(fault,"mirror-sync")))return 0;
    if(!happend(H_MIRROR,work,NULL,&last.after,NULL,1))return 0;
  }else if(last.phase!=H_MIRROR){reject("mirror-state");return 0;}
  return hsame(dest,&hr[hcount-1].after,1)&&hchain();
}
static int hmutate(exr_library *owner,unsigned work){exr_book *books=NULL;size_t n=0,i;exr_error e={0};char p[4096],*ledger=NULL;size_t z=0;int found=0;
  sdk_status=exr_library_books(owner,"",&books,&n,&e);if(sdk_status!=EXR_OK){reject("sdk-books");goto done;}
  for(i=0;i<n;i++)if(books[i].id==1){exr_book change=books[i];change.title=work==1?"handoff-work-one":"handoff-work-two";sdk_status=exr_library_update(owner,&change,&e);found=1;break;}
  if(!found||sdk_status!=EXR_OK){reject("sdk-title-update");goto done;}
  hpath(p,root,work==1?"plan1.json":"plan2.json");if(!hread(p,&ledger,&z))goto done;
  sdk_status=exr_library_migration_ledger_set(owner,ledger,z,&e);if(sdk_status!=EXR_OK)reject("sdk-ledger-write");
done:exr_books_free(books,n);free(ledger);return !failed;
}
static int hadmit(int create){exr_library *owner=NULL;exr_error e={0};lm_mirror_file scanned;unsigned work=1;HRecord last;char p[4096];int ok=0;
  if(strcmp(hentry,"protocol-admit")){reject("explicit-protocol-entry-required");goto done;}
  if(!(create?hinit():hload()))goto done;
  last=hr[hcount-1];
  if(last.phase==H_ACK){if(last.work!=1){reject("no-further-work-planned");goto done;}work=2;strcpy(hroute,"C");}
  else {work=last.work;strcpy(hroute,"R");}
  if(!hchain()||!hinputs())goto done;hattempt++;hopen++;
  sdk_status=exr_library_migration_open(target,&owner,&e);if(sdk_status!=EXR_OK){reject("sdk-owner-open");goto done;}
  hactive_owner=1;
  if(!hstage("S3")||!hchain())goto done;
  if(!strcmp(hroute,"C")){
    hpath(p,root,"mirror.json");if(!hsame(p,&last.after,1)||!hledger(owner,1))goto done;
  }
  if(!hscan(work,&scanned)){hfailed_pause("scanner-refused");goto done;}
  if(!strcmp(hroute,"R")){
    const lm_mirror_file *expected=&ha.input[0];unsigned i;
    for(i=0;i<hcount;i++)if(hr[i].phase==H_FRESH&&hr[i].work==work)expected=&hr[i].baseline;
    if(scanned.size!=expected->size||strcmp(scanned.sha,expected->sha)){reject("full-baseline-parity-mismatch");goto done;}
    /* Full bytes, not digest-only evidence. */
    {char current[4096],name[96],*a=NULL,*b=NULL;size_t an=0,bn=0;unsigned i;
      snprintf(name,sizeof(name),"scan-%s/baseline.bin",hrun);hpath(current,root,name);hpath(p,root,"baseline.bin");
      for(i=0;i<hcount;i++)if(hr[i].phase==H_FRESH&&hr[i].work==work){snprintf(name,sizeof(name),"scan-%s/baseline.bin",hr[i].run);hpath(p,root,name);}
      if(!hread(current,&a,&an)||!hread(p,&b,&bn)||an!=bn||memcmp(a,b,an))reject("full-baseline-bytes-mismatch");free(a);free(b);if(failed)goto done;}
  }else{
    if(!happend(H_FRESH,work,NULL,&last.after,&scanned,1))goto done;
  }
  if(!strcmp(fault,"restore")||!strcmp(fault,"restore-sync")){
    if(hrestore(work))reject("mirror-restored-still-pending");goto done;
  }
  if(!hstage("compared")||!hchain()||!htarget()||!hmirror(work)||!hmutate(owner,work)||!hstage("S5")||!hchain()||!htarget())goto done;
  hpath(p,root,"mirror.json");if(!hsame(p,&hr[hcount-1].after,1))goto done;
  if(!strcmp(fault,"close-only")){
    exr_library_close(owner);owner=NULL;if(!hstage("close-only"))goto done;
    reject("void-close-only-still-pending");goto done;
  }
  if(!strcmp(fault,"rollback")){
    hrollback=exr_library_migration_finish(owner,0,&e);sdk_status=hrollback;exr_library_close(owner);owner=NULL;
    if(!hstage("rollback-finished"))goto done;reject("requested-rollback-retains-evidence");goto done;
  }
  hcommit=exr_library_migration_finish(owner,1,&e);sdk_status=hcommit;
  if(hcommit!=EXR_OK){reject("sdk-commit-non-ok");goto done;}
  if(!hstage("S6")||!hchain()||!htarget()||!hsame(p,&hr[hcount-1].after,1))goto done;
  if(!happend(H_ACK,work,NULL,&hr[hcount-1].after,NULL,0)||!hstage("S7"))goto done;
  {char ack[4096];hrecord_name(ack,hcount-1);hsyncfile(ack);}
  if(failed||!hsyncdir(root,!strcmp(fault,"ack-sync"))||!hchain())goto done;
  exr_library_close(owner);owner=NULL;
  if(!hstage("S8")||!hchain()||!htarget()||!hsame(p,&hr[hcount-1].after,1))goto done;
  ok=1;
done:
  if(owner){if(failed&&hcommit==-1)hfailed_pause("identity-refused");if(hcommit!=EXR_OK){hrollback=exr_library_migration_finish(owner,0,&e);}exr_library_close(owner);owner=NULL;}
  hactive_owner=0;
  return ok&&!failed;
}
static int hresource(void){sqlite3 *src=NULL,*dst=NULL;sqlite3_backup *b=NULL;char p[4096];int rc=SQLITE_OK,pages=0,page_size=0,maxpages=0;double end;int ok=0;
  if(!strcmp(fault,"file-cap")){
    int fd;struct stat st;void (*prior)(int);hpath(p,root,"file-cap-control");if(!hinventory(LIMIT))return 0;
    fd=open(p,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);if(fd<0){reject("file-cap-create");return 0;}
    prior=signal(SIGXFSZ,SIG_IGN);errno=0;rc=ftruncate(fd,(off_t)LIMIT+1);hnative=errno;
    if(rc!=-1||hnative!=EFBIG||fstat(fd,&st)||st.st_size!=0)reject("native-file-cap-not-enforced");
    signal(SIGXFSZ,prior);if(close(fd))reject("file-cap-close");if(!failed)reject("actual-native-file-size-refusal");return 0;
  }
  if(!hinventory(4ull*LIMIT)||!open_db(target,0,&src)||!execsql(src,"BEGIN")||!scalar(src,"PRAGMA page_count",&pages)||!scalar(src,"PRAGMA page_size",&page_size))goto done;
  if(page_size<=0||page_size>65536||pages<0||(uint64_t)pages*page_size>LIMIT){reject("backup-page-byte-bound");goto done;}
  hpath(p,root,"resource-clone.sqlite");{int fd=open(p,O_CREAT|O_EXCL|O_WRONLY|O_CLOEXEC,0600);if(fd<0){reject("clone-exclusive-create");goto done;}close(fd);}
  if(!sqlok(NULL,sqlite3_open_v2(p,&dst,SQLITE_OPEN_READWRITE|SQLITE_OPEN_PRIVATECACHE,NULL),"clone-open")||!configure(dst))goto done;
  {char sql[128];snprintf(sql,sizeof(sql),"PRAGMA page_size=%d;PRAGMA max_page_count=%u",page_size,LIMIT/(unsigned)page_size);if(!execsql(dst,sql)||!scalar(dst,"PRAGMA max_page_count",&maxpages)||maxpages>(int)(LIMIT/(unsigned)page_size))goto done;}
  b=sqlite3_backup_init(dst,"main",src,"main");if(!b){sqlok(dst,sqlite3_errcode(dst),"backup-init");goto done;}
  end=hnow()+30;
  do{
    if(hnow()>end){reject("backup-monotonic-deadline");break;}
    if(!strcmp(fault,"cancel")&&hbackup_steps>0){hcancel=1;reject("backup-explicit-cancel");break;}
    if(++hbackup_steps>4096){reject("backup-step-bound");break;}
    if(hbackup_reserved>(!strcmp(fault,"work-cap")?64:16384)-64){reject("backup-cumulative-work-bound");break;}hbackup_reserved+=64;
    rc=sqlite3_backup_step(b,64);hbackup_pages=sqlite3_backup_pagecount(b)-sqlite3_backup_remaining(b);
    if(!strcmp(fault,"deadline")&&hbackup_steps==1)end=hnow();
    if(hbackup_pages>16384||(uint64_t)sqlite3_backup_pagecount(b)*page_size>LIMIT){reject("backup-live-page-bound");break;}
    if(rc!=SQLITE_OK&&rc!=SQLITE_DONE){sqlok(dst,rc,"backup-real-error");break;}
  }while(rc!=SQLITE_DONE);
  if(rc==SQLITE_DONE&&!failed)ok=1;
done:
  if(b)sqlok(dst,sqlite3_backup_finish(b),"backup-finish");close_db(&dst);close_db(&src);if(!hinventory(0))ok=0;return ok&&!failed;
}
int main(int argc,char **argv){int ok=0;struct rlimit limit;char p[4096];
  if(!getenv("GITHUB_ACTIONS")||strcmp(getenv("GITHUB_ACTIONS"),"true")||argc!=10)return 2;
  mode=argv[1];target=argv[2];root=argv[3];hctl=argv[4];hscanner=argv[5];hrun=argv[6];fault=argv[7];hentry=argv[8];
  if(strcmp(argv[9],"qualification-only")||!htoken(hrun)||SQLITE_VERSION_NUMBER!=3054000||sqlite3_libversion_number()!=3054000||strcmp(SQLITE_SOURCE_ID,sqlite3_sourceid()))return 2;
  umask(077);hstart=hnow();if(hstart<0)return 2;
  limit.rlim_cur=limit.rlim_max=LIMIT;if(setrlimit(RLIMIT_FSIZE,&limit))return 2;
  limit.rlim_cur=limit.rlim_max=30;if(setrlimit(RLIMIT_CPU,&limit))return 2;
  if(snprintf(hbarrier,sizeof(hbarrier),"%s.migrate-lock",target)>=4096)return 2;
  if(!hdir(root,NULL)||!hdir(hctl,NULL))goto report;
  {struct statfs fs;if(statfs(root,&fs)){reject("filesystem-observation");goto report;}
#ifdef __APPLE__
    if(strcmp(fs.f_fstypename,"apfs")){reject("local-filesystem-not-qualified");goto report;}hfilesystem="apfs";
#else
    if((unsigned long)fs.f_type!=0xef53ul){reject("local-filesystem-not-qualified");goto report;}hfilesystem="ext-family";
#endif
  }
  if(!strcmp(mode,"init"))ok=hadmit(1);
  else if(!strcmp(mode,"admit"))ok=hadmit(0);
  else if(!strcmp(mode,"gate"))ok=hgate();
  else if(!strcmp(mode,"resource"))ok=hresource();
  else if(!strcmp(mode,"lease")){
    if(hload()){
      int fd;hpath(p,root,"lease");fd=open(p,O_RDONLY|O_CLOEXEC);if(fd<0||close(fd))reject("unrelated-lease-fd-close");
      fd=open("/dev/null",O_RDONLY|O_CLOEXEC);if(fd<0||close(fd))reject("unrelated-fd-close");
      ok=!failed&&hstage("lease-held");
    }
  }else if(!strcmp(mode,"sync-control")){
    char active[4096];hpath(active,root,"disposable-active");if(hnew(active,"unsafe old pointer",18,1)&&!unlink(active))hsyncdir(root,1);else reject("unsafe-control-unlink");
  }else reject("unknown-mode");
report:
  fprintf(stderr,"qualified local filesystem: %s; no power-loss guarantee\n",hfilesystem);
  fprintf(stderr,"quarantined target/unknown descriptors until process exit: %d\n",hquarantined);
  printf("{\"mode\":\"%s\",\"phase\":\"%s\",\"passed\":%s,\"reason\":\"%s\",\"route\":\"%s\",\"sdk_open_attempts\":%d,\"sqlite_gate_opens\":%d,\"output_gate_attempts\":%d,\"sdk_status\":%d,\"rollback_status\":%d,\"commit_status\":%d,\"native_errno\":%d,\"scanner_status\":%d,\"records\":%u,\"evidence_bytes\":%llu,\"allocated_blocks\":%llu,\"reserved_bytes\":%llu,\"backup_steps\":%d,\"backup_pages\":%d,\"backup_reserved_pages\":%d,\"cancel_observed\":%s,\"io_observation\":\"not-installed\",\"physical_cleanup_verified\":false,\"historical_rollback_proved\":false,\"product_admission\":false,\"full_p0_acceptance\":false}\n",mode,hphase,ok&&!failed?"true":"false",reason,hroute,hattempt,hguard_opens,hguard_outputs,sdk_status,hrollback,hcommit,hnative,hchild_status,hcount,(unsigned long long)hbytes,(unsigned long long)hblocks,(unsigned long long)hreserve,hbackup_steps,hbackup_pages,hbackup_reserved,hcancel?"true":"false");
  fflush(stdout);return ok&&!failed?0:3;
}
