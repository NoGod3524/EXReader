/* SPDX-License-Identifier: MIT
 * Opt-in native POSIX new-target coordinator. No SDK/SQLite is carried across
 * spawn. The only inherited non-stdio descriptor is a separate OFD liveness
 * lease; never explicitly unlock it, and never confuse it with the outer lease.
 */
#define _GNU_SOURCE 1
#define _DARWIN_C_SOURCE 1
#include "lm_new_target.h"
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <stdint.h>
#ifndef _WIN32
#include <unistd.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/file.h>
#include <sys/wait.h>
#include <sys/resource.h>
#include <sys/statvfs.h>
#include <dirent.h>
#include <spawn.h>
#include <signal.h>
#include <time.h>
#ifdef __APPLE__
#include <mach-o/dyld.h>
#include <sys/mount.h>
#else
#include <sys/vfs.h>
#endif
extern char **environ;
#endif
#define N_LIMIT (64ull*1024*1024)
#define N_TOTAL (512ull*1024*1024)
#define N_RECORDS 32u
#define N_NAMES 128u
#define N_RECORD_SIZE 8192u
#define N_MAGIC "EXRCREATE1"
static int ne(lm_err *e,const char *s){char code[96];snprintf(code,sizeof(code),"%s",s);lm_err_set(e,code,"%s (native errno %d)",code,errno);return 0;}
#ifdef _WIN32
int ln_route(lm_new_target **o,const char *x,const char *c,const char *t,const char *p,const char *f,int a,int r,int q,int d,int b,const char *i,lm_cancel_fn cb,void *ctx,int *h,lm_err *e){(void)x;(void)c;(void)t;(void)p;(void)f;(void)r;(void)q;(void)d;(void)b;(void)i;(void)cb;(void)ctx;*o=NULL;*h=0;return a?ne(e,"recovery-platform-unqualified"):1;}
void ln_owner_active(lm_new_target *n,int active){(void)n;(void)active;}
int ln_validate(lm_new_target *n,ln_prefix *v,lm_err *e){(void)n;(void)v;return ne(e,"recovery-platform-unqualified");}
int ln_ledger(lm_new_target *n,const void *b,size_t z,lm_err *e){(void)n;(void)b;(void)z;return ne(e,"recovery-platform-unqualified");}
int ln_scan_begin(lm_new_target *n,const char *t,const char *o,const char *nonce,const char *m,const char *q,lm_mirror_file *r,int *fd,int *slot,lm_err *e){(void)n;(void)t;(void)o;(void)nonce;(void)m;(void)q;(void)r;(void)fd;(void)slot;return ne(e,"recovery-platform-unqualified");}
void ln_scan_spawned(lm_new_target *n,int slot){(void)n;(void)slot;}
int ln_scan_finished(lm_new_target *n,int slot,lm_err *e){(void)n;(void)slot;return ne(e,"recovery-platform-unqualified");}
void ln_report(lm_new_target *n,lm_sb *b){(void)n;lm_sb_str(b,"{\"supported\":false,\"full_p0_acceptance\":false}");}
int ln_child_enter(int fd,const char *q,const char *t,const char *p,const char *f,const char *kind,lm_err *e){(void)kind;(void)fd;(void)q;(void)t;(void)p;(void)f;return ne(e,"recovery-platform-unqualified");}
int ln_child_pause(const char *p,lm_err *e){(void)p;return ne(e,"recovery-platform-unqualified");}
int ln_child_plan(const void *b,size_t z,lm_err *e){(void)b;(void)z;return ne(e,"recovery-platform-unqualified");}
void ln_child_report(lm_sb *b){lm_sb_str(b,"null");}
int ln_child_nonce_matches(const char *nonce){(void)nonce;return 0;}
int ln_child_worker_enter(const char *q,const char *t,const char *f,const char *mode,lm_err *e){(void)mode;(void)q;(void)t;(void)f;return ne(e,"recovery-platform-unqualified");}
#else
static double now(void){struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))return -1;return t.tv_sec+t.tv_nsec/1e9;}
static void identity(const struct stat *s,char id[33]){snprintf(id,33,"%016llx%016llx",(unsigned long long)s->st_dev,(unsigned long long)s->st_ino);}
static int path(char out[4096],const char *root,const char *leaf,lm_err *e){if(snprintf(out,4096,"%s/%s",root,leaf)>=4096)return ne(e,"create-path-bound");return 1;}
static int validhex(const char *s,size_t n){return s&&strlen(s)==n&&strspn(s,"0123456789abcdef")==n;}
static int same(const lm_mirror_file *a,const lm_mirror_file *b){return lm_mirror_same_file(a,b)&&lm_mirror_same_bytes(a,b);}
static int js(const jv *j,const char *key,char *out,size_t cap){const jv *v=lm_get(j,key);if(!v||v->t!=J_STR||v->n>=cap||strlen(v->s)!=v->n)return 0;memcpy(out,v->s,v->n+1);return 1;}
static int ju(const jv *j,const char *key,unsigned *out,unsigned cap){uint64_t x;if(!lm_json_uint(lm_get(j,key),&x)||x>cap)return 0;*out=(unsigned)x;return 1;}
static void fj(lm_sb *b,const lm_mirror_file *f){lm_sb_fmt(b,"[%d,\"%s\",\"%s\",%llu]",f->present,f->identity,f->sha,(unsigned long long)f->size);}
static int fp(const jv *j,lm_mirror_file *f){uint64_t x;memset(f,0,sizeof(*f));if(!j||j->t!=J_ARR||j->n!=4||!lm_json_uint(j->items[0],&x)||x>1||j->items[1]->t!=J_STR||j->items[2]->t!=J_STR)return 0;f->present=(int)x;if((f->present&&(!validhex(j->items[1]->s,32)||!validhex(j->items[2]->s,64)))||(!f->present&&(j->items[1]->n||j->items[2]->n)))return 0;if(!lm_json_uint(j->items[3],&x)||x>N_LIMIT)return 0;f->size=x;strcpy(f->identity,j->items[1]->s);strcpy(f->sha,j->items[2]->s);return f->present||!x;}
static int syncdir(const char *p,lm_err *e){int fd=open(p,O_RDONLY|O_NOFOLLOW|O_DIRECTORY|O_CLOEXEC),ok;if(fd<0)return ne(e,"create-directory-open");ok=fsync(fd)==0;if(close(fd))ok=0;return ok?1:ne(e,"create-directory-sync");}
static int dir(const char *p,char id[33],int private,lm_err *e){struct stat s;if(lstat(p,&s)||!S_ISDIR(s.st_mode)||(s.st_uid!=geteuid()&&s.st_uid!=0)||(s.st_mode&(private?077:022)))return ne(e,"create-directory-custody");identity(&s,id);return 1;}
/* All hashes here run without a same-process SDK owner, except public adoption.
 * Actual target aliases opened during that narrow fence are quarantined rather
 * than closed (classic POSIX SQLite process locks). */
static char fenced_target[33];
static int snap(const char *p,int hash,uint64_t bound,lm_mirror_file *f,char **bytes,size_t *size,lm_err *e){
  struct stat s,a,z,entry;int fd=-1;char id[33],digest[65];unsigned char buf[8192];ssize_t k;uint64_t total=0;lm_sha sha;lm_sb b;memset(f,0,sizeof(*f));if(bytes)*bytes=NULL;if(size)*size=0;lm_sb_init(&b);
  if(lstat(p,&s)){if(errno==ENOENT)return 1;return ne(e,"create-file-stat");}if(!S_ISREG(s.st_mode)||s.st_nlink!=1||s.st_size<0)return ne(e,"create-file-type-or-alias");identity(&s,f->identity);f->present=1;f->size=(uint64_t)s.st_size;if(!hash)return 1;
  if(fenced_target[0]&&!strcmp(f->identity,fenced_target))return ne(e,"create-fenced-target-alias");
  fd=open(p,O_RDONLY|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC);if(fd<0)return ne(e,"create-file-open");if(fstat(fd,&a))return ne(e,"create-unknown-fd-quarantined");identity(&a,id);if(fenced_target[0]&&!strcmp(id,fenced_target))return ne(e,"create-target-fd-quarantined");
  if(strcmp(id,f->identity)||!S_ISREG(a.st_mode)||a.st_nlink!=1||a.st_size<0||(uint64_t)a.st_size>bound){ne(e,"create-opened-file-bound");goto bad;}
  lm_sha_init(&sha);while((k=read(fd,buf,sizeof(buf)))>0){if((uint64_t)k>bound-total){ne(e,"create-read-bound");goto bad;}total+=(uint64_t)k;lm_sha_add(&sha,buf,(size_t)k);if(bytes){lm_sb_add(&b,(const char*)buf,(size_t)k);if(b.oom){ne(e,"create-allocation");goto bad;}}}if(k<0||total!=(uint64_t)a.st_size){ne(e,"create-file-read");goto bad;}lm_sha_hex(&sha,f->sha);
  if(lseek(fd,0,SEEK_SET)<0){ne(e,"create-rehash-seek");goto bad;}total=0;lm_sha_init(&sha);while((k=read(fd,buf,sizeof(buf)))>0){if((uint64_t)k>bound-total){ne(e,"create-rehash-bound");goto bad;}total+=(uint64_t)k;lm_sha_add(&sha,buf,(size_t)k);}lm_sha_hex(&sha,digest);
  if(k<0||total!=(uint64_t)a.st_size||strcmp(digest,f->sha)||fstat(fd,&z)||lstat(p,&entry)||a.st_dev!=z.st_dev||a.st_ino!=z.st_ino||a.st_size!=z.st_size||a.st_mtime!=z.st_mtime||a.st_ctime!=z.st_ctime||entry.st_dev!=a.st_dev||entry.st_ino!=a.st_ino||entry.st_nlink!=1){ne(e,"create-file-changed");goto bad;}
  if(close(fd)){fd=-1;ne(e,"create-file-close");goto bad;}fd=-1;if(bytes){if(!b.p){b.p=calloc(1,1);if(!b.p)return ne(e,"create-allocation");}*bytes=b.p;b.p=NULL;if(size)*size=(size_t)total;}lm_sb_free(&b);return 1;
 bad:if(fd>=0)close(fd);lm_sb_free(&b);return 0;
}
static int exact(const char *p,const lm_mirror_file *want,int hash,lm_err *e){lm_mirror_file got;if(!snap(p,hash,hash?want->size:0,&got,NULL,NULL,e))return 0;return lm_mirror_same_file(&got,want)&&(!hash||lm_mirror_same_bytes(&got,want))?1:ne(e,"create-artifact-changed");}
static int write_new(const char *p,const void *data,size_t size,lm_err *e){int fd;size_t off=0;char parent[4096],*slash;if(size>N_LIMIT)return ne(e,"create-write-bound");fd=open(p,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);if(fd<0)return ne(e,"create-exclusive-file");while(off<size){ssize_t n=write(fd,(const char*)data+off,size-off);if(n<=0){close(fd);return ne(e,"create-write");}off+=(size_t)n;}if(fsync(fd)){close(fd);return ne(e,"create-file-sync");}if(close(fd))return ne(e,"create-file-close");strcpy(parent,p);slash=strrchr(parent,'/');if(!slash)return ne(e,"create-write-parent");*slash=0;return syncdir(parent,e);}
static int absent(const char *p,lm_err *e){struct stat s;if(!lstat(p,&s)||errno!=ENOENT)return ne(e,"create-conflicting-path");return 1;}
static int sidecars_absent(const char *p,lm_err *e){const char *ends[]={"-wal","-shm","-journal"};char q[4096];unsigned i;for(i=0;i<3;i++){if(snprintf(q,sizeof(q),"%s%s",p,ends[i])>=4096||!absent(q,e))return 0;}return 1;}
static int random_nonce(char out[33],lm_err *e){int fd=open("/dev/urandom",O_RDONLY|O_CLOEXEC),i;unsigned char b[16];size_t n=0;if(fd<0)return ne(e,"create-random");while(n<16){ssize_t k=read(fd,b+n,16-n);if(k<=0){close(fd);return ne(e,"create-random-read");}n+=(size_t)k;}if(close(fd))return ne(e,"create-random-close");for(i=0;i<16;i++)snprintf(out+2*i,3,"%02x",b[i]);return 1;}
static int enabled(const char *key,const char *value){const char *g=getenv("EXR_MIGRATE_TEST_FAULTS"),*v=getenv(key);return g&&!strcmp(g,"1")&&v&&!strcmp(v,value);}
static int phase_selected(const char *list,const char *phase){size_t n=strlen(phase);if(!list)return 0;while(*list){const char *end=strchr(list,',');if((end?(size_t)(end-list):strlen(list))==n&&!memcmp(list,phase,n))return 1;if(!end)break;list=end+1;}return 0;}
static int pause_at(const char *root,const char *nonce,const char *phase,lm_err *e){char p[4096],name[96];double start;const char *g=getenv("EXR_MIGRATE_TEST_FAULTS");if(!g||strcmp(g,"1")||!phase_selected(getenv("EXR_CREATE_PAUSE"),phase))return 1;snprintf(name,sizeof(name),"%s.ready",phase);if(!path(p,root,name,e)||!write_new(p,nonce,32,e))return 0;snprintf(name,sizeof(name),"%s.go",phase);if(!path(p,root,name,e))return 0;start=now();while(start>=0&&now()-start<25){lm_mirror_file f;char *data=NULL;size_t n=0;struct timespec delay={0,10000000};if(!snap(p,1,9,&f,&data,&n,e))return 0;if(f.present){int ok=n==9&&!memcmp(data,"continue\n",9);free(data);return ok?1:ne(e,"create-pause-token");}free(data);nanosleep(&delay,NULL);}return ne(e,"create-pause-timeout");}
/* Child request is canonical, identity-bound, private and parent-written before
 * spawn. FD3 carries the already-held OFD lock across exec. The child leaves it
 * open through process exit; CLOSE or LOCK_UN would invalidate this contract. */
static char child_nonce[33],child_root[4096],child_plan[4096],child_target[4096];
static int child_live=-1;
static char child_request_path[4096],child_live_path[4096],child_pack_path[4096],child_font_path[4096],child_output_id[33];
static lm_mirror_file child_request_id,child_live_id,child_image_id,child_pack_id,child_font_id;
static int child_guard(lm_err *e){char id[33];struct stat st;
  if(child_live<0||fstat(child_live,&st))return ne(e,"create-child-live-fd-lost");identity(&st,id);
  if(strcmp(id,child_live_id.identity)||!dir(child_root,id,1,e)||strcmp(id,child_output_id)||!exact(child_request_path,&child_request_id,1,e)||!exact(child_live_path,&child_live_id,1,e)||!exact(child_target,&child_image_id,0,e)||(child_pack_id.present&&!exact(child_pack_path,&child_pack_id,1,e))||(child_font_id.present&&!exact(child_font_path,&child_font_id,1,e)))return ne(e,"create-child-envelope-changed");return 1;
}
int ln_child_enter(int fd,const char *request,const char *target,const char *pack,const char *font,const char *expected_kind,lm_err *e){
  char *raw=NULL,msg[128],nonce[33],live[4096],image[4096],source[4096],font_value[4096],id[33],output_id[33],kind[16];size_t size=0;lm_mirror_file req,live_id,image_id,pack_id,font_id;struct stat s;int independent=-1,ok=0;jv *j=NULL;struct rlimit cap;
  umask(077);
  if(fd!=3||!snap(request,1,N_RECORD_SIZE,&req,&raw,&size,e)||!req.present)goto done;j=lm_json_parse(raw,size,msg,sizeof(msg));
  if(!j||j->t!=J_OBJ||j->n!=12||!js(j,"nonce",nonce,sizeof(nonce))||!validhex(nonce,32)||!js(j,"live",live,sizeof(live))||!js(j,"target",image,sizeof(image))||strcmp(target,image)||!js(j,"pack",source,sizeof(source))||strcmp(pack?pack:"-",source)||!js(j,"font",font_value,sizeof(font_value))||strcmp(font?font:"-",font_value)||!js(j,"kind",kind,sizeof(kind))||!js(j,"output",child_root,sizeof(child_root))||!js(j,"output_identity",output_id,sizeof(output_id))||!fp(lm_get(j,"live_file"),&live_id)||!fp(lm_get(j,"image_file"),&image_id)||!fp(lm_get(j,"pack_file"),&pack_id)||!fp(lm_get(j,"font_file"),&font_id))goto done;
  if(!expected_kind||strcmp(kind,expected_kind)||(strcmp(kind,"import")&&strcmp(kind,"seal")&&strcmp(kind,"observe")&&strcmp(kind,"create-capture")&&strcmp(kind,"create-scan"))){ne(e,"create-child-kind-refused");goto done;}
  if(!live_id.present||!image_id.present||(!strcmp(kind,"import")?!pack_id.present:pack_id.present)||(!strcmp(font_value,"-")?font_id.present:!font_id.present)){ne(e,"create-child-required-binding");goto done;}
  {char base[4096],want[4096],name[96],*slash;strcpy(base,child_root);slash=strrchr(base,'/');if(!slash)goto done;*slash=0;
    if(!path(want,child_root,"request.json",e)||strcmp(want,request))goto done;
    if(!strcmp(kind,"import")){
      snprintf(name,sizeof(name),"import-%s",nonce);if(!path(want,base,name,e)||strcmp(want,child_root))goto done;
      snprintf(name,sizeof(name),"image-%s.sqlite",nonce);if(!path(want,base,name,e)||strcmp(want,target))goto done;
      snprintf(name,sizeof(name),"live-%s.lock",nonce);if(!path(want,base,name,e)||strcmp(want,live))goto done;
      {const char *leaf=strrchr(source,'/');char producer[33];if(!leaf||strncmp(source,base,strlen(base))||leaf!=source+strlen(base)||strlen(leaf+1)!=41||strncmp(leaf+1,"pack-",5)||strcmp(leaf+38,".bin"))goto done;memcpy(producer,leaf+6,32);producer[32]=0;if(!validhex(producer,32))goto done;}
    }else if(!strcmp(kind,"seal")||!strcmp(kind,"observe")){
      snprintf(name,sizeof(name),"%s-%s",kind,nonce);if(!path(want,base,name,e)||strcmp(want,child_root))goto done;
      snprintf(name,sizeof(name),"live-%s.lock",nonce);if(!path(want,base,name,e)||strcmp(want,live))goto done;
      if(!strcmp(kind,"observe")){if(snprintf(want,sizeof(want),"%s.migration-recovery",target)>=4096||strcmp(want,base))goto done;}
      else if(strncmp(target,base,strlen(base))||target[strlen(base)]!='/')goto done;
    }else {
      const char *leaf=strrchr(child_root,'/');const char *prefix=!strcmp(kind,"create-capture")?"cap-":"scan-";
      if(!leaf||strncmp(leaf+1,prefix,strlen(prefix))||strncmp(leaf+1+strlen(prefix),nonce,32)||snprintf(want,sizeof(want),"%s.migration-recovery",target)>=4096||strcmp(want,base)||strncmp(live,base,strlen(base))||live[strlen(base)]!='/')goto done;
    }
  }
  if(!dir(child_root,id,1,e)||strcmp(id,output_id))goto done;
  if(fstat(fd,&s)||!S_ISREG(s.st_mode)||s.st_nlink!=1||s.st_uid!=geteuid()||(s.st_mode&077))goto done;identity(&s,id);if(strcmp(id,live_id.identity)||!exact(live,&live_id,1,e)||!exact(image,&image_id,0,e)||(pack_id.present&&!exact(source,&pack_id,1,e))||(font_id.present&&!exact(font_value,&font_id,1,e)))goto done;
  independent=open(live,O_RDWR|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC);if(independent<0)goto done;
  if(flock(independent,LOCK_EX|LOCK_NB)==0){/* Lost inherited lock: refuse, never repair it. */close(independent);independent=-1;ne(e,"create-child-inherited-lock-not-held");goto done;}
  if(errno!=EWOULDBLOCK&&errno!=EAGAIN)goto done;close(independent);independent=-1;
  if(fcntl(fd,F_SETFD,FD_CLOEXEC))goto done;child_live=fd;strcpy(child_nonce,nonce);strcpy(child_target,target);if(!path(child_plan,child_root,"planned-ledger.bin",e))goto done;
  cap.rlim_cur=cap.rlim_max=N_LIMIT;if(setrlimit(RLIMIT_FSIZE,&cap))goto done;cap.rlim_cur=cap.rlim_max=30;if(setrlimit(RLIMIT_CPU,&cap))goto done;
  if(!pause_at(child_root,child_nonce,"child-before-open",e))goto done;
  if(!exact(live,&live_id,1,e)||!exact(target,&image_id,0,e))goto done;
  if(!strcmp(kind,"import")&&(!sidecars_absent(target,e)||image_id.size!=0))goto done;
  strcpy(child_request_path,request);strcpy(child_live_path,live);strcpy(child_pack_path,source);strcpy(child_font_path,font_value);strcpy(child_output_id,output_id);
  child_request_id=req;child_live_id=live_id;child_image_id=image_id;child_pack_id=pack_id;child_font_id=font_id;strcpy(fenced_target,image_id.identity);ok=child_guard(e);
 done:if(independent>=0)close(independent);free(raw);lm_json_free(j);return ok?1:ne(e,e->code[0]?e->code:"create-child-request-refused");
}
int ln_child_pause(const char *phase,lm_err *e){return child_live>=0&&pause_at(child_root,child_nonce,phase,e)&&child_guard(e);}
int ln_child_plan(const void *data,size_t size,lm_err *e){return child_live>=0&&size&&write_new(child_plan,data,size,e);}
void ln_child_report(lm_sb *b){lm_sb_fmt(b,"{\"nonce\":\"%s\",\"liveness_fd\":%d,\"retained_until_exit\":true}",child_nonce,child_live);}
int ln_child_nonce_matches(const char *nonce){return child_live>=0&&nonce&&!strcmp(nonce,child_nonce);}
int ln_child_worker_enter(const char *request,const char *target,const char *font,const char *mode,lm_err *e){return ln_child_enter(3,request,target,"-",font,mode,e);}
#ifndef EXR_NEW_TARGET_WORKER_ONLY
enum { NP_ANCHOR,NP_ATTEMPT,NP_FINISHED,NP_VERIFY,NP_SEALED,NP_ADOPT,NP_ACK,NP_PUBLIC_VERIFY };
typedef struct {
  unsigned ordinal,phase,attempt;char run[33],producer[33],previous[65],self[33],import_token[64],verify_token[64],observe_token[64];
  lm_mirror_file image,live,request,result,plan,copy,baseline,mirror,observed_result,observed_copy,observed_baseline,projection,observed_projection;
} NRecord;
struct lm_new_target {
  char target[4096],parent[4096],root[4096],exe[4096],worker[4096],pack[4096],font[4096],barrier_path[4096],pending[4096],mirror_path[4096],run_dir[4096];
  char nonce[33],target_path_sha[65],root_id[33],parent_id[33],phase[64],reason[96];
  lm_mirror_file exe_id,worker_id,font_id,pack_id,lease_id,barrier_id,anchor_id,registry,slots[8],uses[8],ids[N_RECORDS];
  int slot_fds[8],slot_active[8];unsigned slot_used[8];
  NRecord anchor,records[N_RECORDS];unsigned count,attempt,held_count,worker_serial;int held[16],lease,partial,preview,handled,acknowledged,published,recover;
  uint64_t bytes,blocks;unsigned names;double started;lm_cancel_fn cancelled;void *context;char inject[64];
};
void ln_owner_active(lm_new_target *n,int active){if(active&&n&&n->count)strcpy(fenced_target,n->records[n->count-1].image.identity);else fenced_target[0]=0;}
static int nerror(lm_new_target *n,lm_err *e,const char *s){if(!n->reason[0])snprintf(n->reason,sizeof(n->reason),"%s",s);return ne(e,s);}
static int inventory_walk(lm_new_target *n,const char *p,unsigned depth,lm_err *e){DIR *d;struct dirent *v;if(depth>3)return nerror(n,e,"create-directory-depth");d=opendir(p);if(!d)return nerror(n,e,"create-inventory-open");while((v=readdir(d))){char q[4096];struct stat s;if(!strcmp(v->d_name,".")||!strcmp(v->d_name,".."))continue;if(++n->names>N_NAMES||!path(q,p,v->d_name,e)||lstat(q,&s)){closedir(d);return nerror(n,e,"create-name-cap-or-stat");}if(s.st_uid!=geteuid()||(s.st_mode&077)){closedir(d);return nerror(n,e,"create-private-custody");}if(S_ISDIR(s.st_mode)){if(!inventory_walk(n,q,depth+1,e)){closedir(d);return 0;}}else if(S_ISREG(s.st_mode)&&s.st_nlink==1&&s.st_size>=0){if((uint64_t)s.st_size>N_TOTAL-n->bytes||(uint64_t)s.st_blocks>N_TOTAL/512-n->blocks){closedir(d);return nerror(n,e,"create-evidence-cap");}n->bytes+=(uint64_t)s.st_size;n->blocks+=(uint64_t)s.st_blocks;}else{closedir(d);return nerror(n,e,"create-evidence-kind");}}
  return closedir(d)==0?1:nerror(n,e,"create-inventory-close");}
static int inventory(lm_new_target *n,uint64_t reserve,lm_err *e){struct statvfs disk;n->bytes=n->blocks=0;n->names=0;if(!inventory_walk(n,n->root,0,e))return 0;if(reserve>N_TOTAL||n->bytes>N_TOTAL-reserve||n->blocks*512>N_TOTAL-reserve||statvfs(n->root,&disk)||(uint64_t)disk.f_bavail<reserve/(disk.f_frsize?disk.f_frsize:1)+1)return nerror(n,e,"create-evidence-reservation");return 1;}
static int cancel(lm_new_target *n,lm_err *e){if(n->cancelled&&n->cancelled(n->context))return nerror(n,e,"cancelled");if(now()<0||now()-n->started>120)return nerror(n,e,"create-coordinator-deadline");return 1;}
static int npause(lm_new_target *n,const char *phase,lm_err *e){snprintf(n->phase,sizeof(n->phase),"%s",phase);return cancel(n,e)&&pause_at(n->run_dir,n->nonce,phase,e)&&cancel(n,e);}
static int nfile(char p[4096],lm_new_target *n,const char *kind,const char *run,const char *ext,lm_err *e){char leaf[128];if(!validhex(run,32))return nerror(n,e,"create-producer-run");snprintf(leaf,sizeof(leaf),"%s-%s%s",kind,run,ext);return path(p,n->root,leaf,e);}
static int nrecord_path(char p[4096],lm_new_target *n,unsigned ordinal,lm_err *e){char leaf[40];snprintf(leaf,sizeof(leaf),"record-%02u.json",ordinal);return path(p,n->root,leaf,e);}
static int noutput(char p[4096],lm_new_target *n,const char *token,const char *leaf,lm_err *e){char d[4096];if(strlen(token)>63||!strlen(token)||strspn(token,"abcdefghijklmnopqrstuvwxyz0123456789-")!=strlen(token))return nerror(n,e,"create-output-token");return path(d,n->root,token,e)&&path(p,d,leaf,e);}
static void record_text(lm_new_target *n,const NRecord *r,lm_sb *b){
  lm_sb_fmt(b,"{\"magic\":\"%s\",\"ordinal\":%u,\"phase\":%u,\"attempt\":%u,\"run\":\"%s\",\"producer\":\"%s\",\"previous\":\"%s\",\"self\":\"%s\",\"target_path_sha\":\"%s\",\"root\":\"%s\",\"parent\":\"%s\",\"import_token\":\"%s\",\"verify_token\":\"%s\",\"observe_token\":\"%s\",\"exe\":",N_MAGIC,r->ordinal,r->phase,r->attempt,r->run,r->producer,r->previous,r->self,n->target_path_sha,n->root_id,n->parent_id,r->import_token,r->verify_token,r->observe_token);fj(b,&n->exe_id);lm_sb_str(b,",\"worker\":");fj(b,&n->worker_id);lm_sb_str(b,",\"font\":");fj(b,&n->font_id);lm_sb_str(b,",\"pack\":");fj(b,&n->pack_id);lm_sb_str(b,",\"lease\":");fj(b,&n->lease_id);lm_sb_str(b,",\"barrier\":");fj(b,&n->barrier_id);lm_sb_str(b,",\"registry\":");fj(b,&n->registry);
#define NF(key) lm_sb_str(b,",\"" #key "\":");fj(b,&r->key)
  NF(image);NF(live);NF(request);NF(result);NF(plan);NF(copy);NF(baseline);NF(mirror);NF(observed_result);NF(observed_copy);NF(observed_baseline);NF(projection);NF(observed_projection);
#undef NF
  lm_sb_str(b,"}\n");if(b->oom||!b->p||b->n<2){b->oom=1;return;}{char h[65];lm_sha_bytes(b->p,b->n,h);b->n-=2;b->p[b->n]=0;lm_sb_fmt(b,",\"seal\":\"%s\"}\n",h);}
}
static int record_write(lm_new_target *n,const char *p,NRecord *r,lm_mirror_file *id,lm_err *e){int fd;struct stat s;lm_sb b;size_t off=0;if(!inventory(n,N_RECORD_SIZE,e))return 0;fd=open(p,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);if(fd<0)return nerror(n,e,"create-record-exclusive");if(fstat(fd,&s)){close(fd);return nerror(n,e,"create-record-stat");}identity(&s,r->self);lm_sb_init(&b);record_text(n,r,&b);if(b.oom||b.n>N_RECORD_SIZE){close(fd);lm_sb_free(&b);return nerror(n,e,"create-record-bound");}while(off<b.n){ssize_t k=write(fd,b.p+off,b.n-off);if(k<=0){close(fd);lm_sb_free(&b);return nerror(n,e,"create-record-write");}off+=(size_t)k;}lm_sb_free(&b);if(fsync(fd)){close(fd);return nerror(n,e,"create-record-sync");}if(close(fd)||!syncdir(n->root,e))return 0;return snap(p,1,N_RECORD_SIZE,id,NULL,NULL,e);}
static int record_read(lm_new_target *n,const char *p,NRecord *r,lm_mirror_file *id,int anchor,lm_err *e){char *raw=NULL,msg[128],magic[32],target_sha[65],rid[33],pid[33];size_t size=0;lm_sb b;jv *j=NULL;int ok=0;lm_mirror_file exe,worker,font,pack,lease,barrier,registry;memset(r,0,sizeof(*r));lm_sb_init(&b);if(!snap(p,1,N_RECORD_SIZE,id,&raw,&size,e)||!id->present)goto done;j=lm_json_parse(raw,size,msg,sizeof(msg));
  if(!j||j->t!=J_OBJ||j->n!=35||!js(j,"magic",magic,sizeof(magic))||strcmp(magic,N_MAGIC)||!ju(j,"ordinal",&r->ordinal,N_RECORDS)||!ju(j,"phase",&r->phase,NP_PUBLIC_VERIFY)||!ju(j,"attempt",&r->attempt,2)||!js(j,"run",r->run,sizeof(r->run))||!validhex(r->run,32)||!js(j,"producer",r->producer,sizeof(r->producer))||(!anchor&&!validhex(r->producer,32))||!js(j,"previous",r->previous,sizeof(r->previous))||(!anchor&&!validhex(r->previous,64))||!js(j,"self",r->self,sizeof(r->self))||strcmp(r->self,id->identity)||!js(j,"target_path_sha",target_sha,sizeof(target_sha))||strcmp(target_sha,n->target_path_sha)||!js(j,"root",rid,sizeof(rid))||strcmp(rid,n->root_id)||!js(j,"parent",pid,sizeof(pid))||strcmp(pid,n->parent_id)||!js(j,"import_token",r->import_token,sizeof(r->import_token))||!js(j,"verify_token",r->verify_token,sizeof(r->verify_token))||!js(j,"observe_token",r->observe_token,sizeof(r->observe_token)))goto done;
#define PF(key,ptr) if(!fp(lm_get(j,key),ptr))goto done
  PF("exe",&exe);PF("worker",&worker);PF("font",&font);PF("pack",&pack);PF("lease",&lease);PF("barrier",&barrier);PF("registry",&registry);
  PF("image",&r->image);PF("live",&r->live);PF("request",&r->request);PF("result",&r->result);PF("plan",&r->plan);PF("copy",&r->copy);PF("baseline",&r->baseline);PF("mirror",&r->mirror);PF("observed_result",&r->observed_result);PF("observed_copy",&r->observed_copy);PF("observed_baseline",&r->observed_baseline);PF("projection",&r->projection);PF("observed_projection",&r->observed_projection);
#undef PF
  if(anchor){if(!same(&exe,&n->exe_id)||!same(&worker,&n->worker_id)||!same(&font,&n->font_id))goto done;n->pack_id=pack;n->lease_id=lease;n->barrier_id=barrier;n->registry=registry;}
  else if(!same(&exe,&n->exe_id)||!same(&worker,&n->worker_id)||!same(&font,&n->font_id)||!same(&pack,&n->pack_id)||!same(&lease,&n->lease_id)||!same(&barrier,&n->barrier_id)||!same(&registry,&n->registry))goto done;
  record_text(n,r,&b);if(b.oom||size!=b.n||memcmp(raw,b.p,size))goto done;ok=1;
 done:free(raw);lm_json_free(j);lm_sb_free(&b);return ok?1:nerror(n,e,"create-record-canonical-binding");}
static int acquire(const char *p,const lm_mirror_file *want,int *out,lm_err *e){int fd;struct stat s;char id[33];if(!exact(p,want,1,e))return 0;fd=open(p,O_RDWR|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC);if(fd<0)return ne(e,"create-lease-open");if(fstat(fd,&s))return ne(e,"create-lease-stat");identity(&s,id);if(fenced_target[0]&&!strcmp(id,fenced_target))return ne(e,"create-lease-target-fd-quarantined");if(strcmp(id,want->identity)||!S_ISREG(s.st_mode)||s.st_nlink!=1)return ne(e,"create-lease-identity");if(flock(fd,LOCK_EX|LOCK_NB)){close(fd);return ne(e,"create-child-or-coordinator-alive");}if(!exact(p,want,1,e)){close(fd);return 0;}*out=fd;return 1;}
static int slot_path(lm_new_target *n,unsigned i,int use,char p[4096],lm_err *e){char name[48];if(i>=8)return ne(e,"create-slot-range");snprintf(name,sizeof(name),"worker-slot-%02u.%s",i,use?"use":"lock");return path(p,n->root,name,e);}
static int registry_make(lm_new_target *n,lm_err *e){unsigned i;char p[4096],nonce[33];lm_sb b;lm_sb_init(&b);lm_sb_str(&b,"{\"magic\":\"EXRCREATE1-SLOTS\",\"slots\":[");
  for(i=0;i<8;i++){if(!random_nonce(nonce,e)||!slot_path(n,i,0,p,e)||!write_new(p,nonce,32,e)||!snap(p,1,32,&n->slots[i],NULL,NULL,e)||!slot_path(n,i,1,p,e)||!write_new(p,"",0,e)||!snap(p,1,0,&n->uses[i],NULL,NULL,e))goto bad;if(i)lm_sb_str(&b,",");lm_sb_str(&b,"[");fj(&b,&n->slots[i]);lm_sb_str(&b,",");fj(&b,&n->uses[i]);lm_sb_str(&b,"]");}
  lm_sb_str(&b,"]}\n");if(b.oom||b.n>N_RECORD_SIZE||!path(p,n->root,"worker-slots.json",e)||!write_new(p,b.p,b.n,e)||!snap(p,1,N_RECORD_SIZE,&n->registry,NULL,NULL,e))goto bad;lm_sb_free(&b);return 1;
 bad:lm_sb_free(&b);return 0;
}
static void use_text(lm_sb *b,unsigned slot,const char *nonce,const char *token,const char *output,const char *head,const lm_mirror_file *request){lm_sb_fmt(b,"{\"magic\":\"EXRCREATE1-WORKER\",\"slot\":%u,\"nonce\":\"%s\",\"token\":\"%s\",\"output_identity\":\"%s\",\"predecessor\":\"%s\",\"request\":",slot,nonce,token,output,head);fj(b,request);lm_sb_str(b,"}\n");}
static int registry_validate(lm_new_target *n,lm_err *e){char p[4096],*raw=NULL,msg[128];size_t size=0;jv *j=NULL;const jv *slots;lm_mirror_file f;unsigned i;int ok=0;
  if(!path(p,n->root,"worker-slots.json",e)||!snap(p,1,N_RECORD_SIZE,&f,&raw,&size,e)||!same(&f,&n->registry))goto done;j=lm_json_parse(raw,size,msg,sizeof(msg));slots=lm_get(j,"slots");if(!j||j->t!=J_OBJ||j->n!=2||!lm_get_str(j,"magic")||strcmp(lm_get_str(j,"magic"),"EXRCREATE1-SLOTS")||!slots||slots->t!=J_ARR||slots->n!=8)goto done;
  for(i=0;i<8;i++){const jv *row=slots->items[i];char *use_raw=NULL;size_t use_size=0;lm_mirror_file use;struct stat st;char id[33];
    if(!row||row->t!=J_ARR||row->n!=2||!fp(row->items[0],&n->slots[i])||!fp(row->items[1],&n->uses[i])||!n->slots[i].present||n->slots[i].size!=32||!n->uses[i].present||n->uses[i].size||!slot_path(n,i,0,p,e)||!exact(p,&n->slots[i],1,e))goto done;
    if(n->slot_fds[i]>=0){if(fstat(n->slot_fds[i],&st))goto done;identity(&st,id);if(strcmp(id,n->slots[i].identity))goto done;}
    else if(!n->slot_active[i]&&!acquire(p,&n->slots[i],&n->slot_fds[i],e))goto done;
    if(!slot_path(n,i,1,p,e)||!snap(p,1,N_RECORD_SIZE,&use,&use_raw,&use_size,e)||!lm_mirror_same_file(&use,&n->uses[i])){free(use_raw);goto done;}
    n->slot_used[i]=use_size?1:0;
    if(use_size){jv *u=lm_json_parse(use_raw,use_size,msg,sizeof(msg));lm_sb canonical;char nonce[33],token[64],output[33],head[65],dirpath[4096],request[4096];unsigned number;lm_mirror_file request_id;int valid=0;lm_sb_init(&canonical);
      if(u&&u->t==J_OBJ&&u->n==7&&lm_get_str(u,"magic")&&!strcmp(lm_get_str(u,"magic"),"EXRCREATE1-WORKER")&&ju(u,"slot",&number,7)&&number==i&&js(u,"nonce",nonce,sizeof(nonce))&&validhex(nonce,32)&&js(u,"token",token,sizeof(token))&&strlen(token)>0&&strspn(token,"abcdefghijklmnopqrstuvwxyz0123456789-")==strlen(token)&&js(u,"output_identity",output,sizeof(output))&&validhex(output,32)&&js(u,"predecessor",head,sizeof(head))&&validhex(head,64)&&fp(lm_get(u,"request"),&request_id)){
        use_text(&canonical,i,nonce,token,output,head,&request_id);
        if(!canonical.oom&&canonical.n==use_size&&!memcmp(canonical.p,use_raw,use_size)&&path(dirpath,n->root,token,e)&&dir(dirpath,id,1,e)&&!strcmp(id,output)&&path(request,dirpath,"request.json",e)&&exact(request,&request_id,1,e)){
          unsigned k;int found=!strcmp(head,n->anchor_id.sha);for(k=0;k<N_RECORDS;k++){lm_mirror_file record;if(!nrecord_path(p,n,k,e)||!snap(p,1,N_RECORD_SIZE,&record,NULL,NULL,e))break;if(record.present&&!strcmp(record.sha,head))found=1;}valid=found;
        }
      }lm_sb_free(&canonical);lm_json_free(u);free(use_raw);if(!valid)goto done;
    }else free(use_raw);
  }ok=1;
 done:free(raw);lm_json_free(j);return ok?1:ne(e,e->code[0]?e->code:"create-worker-registry-refused");
}
int ln_scan_begin(lm_new_target *n,const char *target,const char *output,const char *nonce,const char *mode,const char *request,lm_mirror_file *request_id,int *fd,int *slot,lm_err *e){unsigned i,k;char lock[4096],use_path[4096],id[33],head[65],p[4096];const char *token=strrchr(output,'/');lm_sb b,use;lm_mirror_file image,empty={0},use_now;int use_fd=-1;struct stat st;size_t off=0;*fd=-1;*slot=-1;lm_sb_init(&b);lm_sb_init(&use);
  if(!token||!validhex(nonce,32)||!registry_validate(n,e)||!dir(output,id,1,e)||!snap(target,0,0,&image,NULL,NULL,e)||!image.present)goto bad;token++;memset(image.sha,'0',64);image.sha[64]=0;
  for(i=0;i<8;i++)if(!n->slot_used[i]&&!n->slot_active[i]&&n->slot_fds[i]>=0)break;if(i==8){ne(e,"create-worker-slot-capacity");goto bad;}
  if(!slot_path(n,i,0,lock,e)||!slot_path(n,i,1,use_path,e))goto bad;
  lm_sb_str(&b,"{\"nonce\":");lm_sb_json(&b,nonce,32);lm_sb_str(&b,",\"live\":");lm_sb_json(&b,lock,strlen(lock));lm_sb_str(&b,",\"target\":");lm_sb_json(&b,target,strlen(target));lm_sb_str(&b,",\"pack\":\"-\",\"font\":");lm_sb_json(&b,n->font,strlen(n->font));lm_sb_str(&b,",\"kind\":");lm_sb_json(&b,mode,strlen(mode));lm_sb_str(&b,",\"output\":");lm_sb_json(&b,output,strlen(output));lm_sb_str(&b,",\"output_identity\":");lm_sb_json(&b,id,32);lm_sb_str(&b,",\"live_file\":");fj(&b,&n->slots[i]);lm_sb_str(&b,",\"image_file\":");fj(&b,&image);lm_sb_str(&b,",\"pack_file\":");fj(&b,&empty);lm_sb_str(&b,",\"font_file\":");fj(&b,&n->font_id);lm_sb_str(&b,"}\n");
  if(b.oom||b.n>N_RECORD_SIZE||!write_new(request,b.p,b.n,e)||!snap(request,1,N_RECORD_SIZE,request_id,NULL,NULL,e))goto bad;
  strcpy(head,n->anchor_id.sha);for(k=0;k<N_RECORDS;k++){lm_mirror_file record;if(!nrecord_path(p,n,k,e)||!snap(p,1,N_RECORD_SIZE,&record,NULL,NULL,e))goto bad;if(!record.present)break;strcpy(head,record.sha);}
  use_text(&use,i,nonce,token,id,head,request_id);if(use.oom||use.n>N_RECORD_SIZE||!snap(use_path,1,0,&use_now,NULL,NULL,e)||!same(&use_now,&n->uses[i]))goto bad;
  use_fd=open(use_path,O_WRONLY|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC);if(use_fd<0)goto bad;if(fstat(use_fd,&st)){use_fd=-1;ne(e,"create-use-unknown-fd-quarantined");goto bad;}identity(&st,id);if(fenced_target[0]&&!strcmp(id,fenced_target)){use_fd=-1;ne(e,"create-use-target-fd-quarantined");goto bad;}if(strcmp(id,n->uses[i].identity)||st.st_size||!S_ISREG(st.st_mode)||st.st_nlink!=1)goto bad;
  while(off<use.n){ssize_t z=write(use_fd,use.p+off,use.n-off);if(z<=0)goto bad;off+=(size_t)z;}if(fsync(use_fd)||close(use_fd)){use_fd=-1;goto bad;}use_fd=-1;if(!syncdir(n->root,e))goto bad;n->slot_used[i]=1;*slot=(int)i;*fd=n->slot_fds[i];lm_sb_free(&b);lm_sb_free(&use);return 1;
 bad:if(use_fd>=0)close(use_fd);lm_sb_free(&b);lm_sb_free(&use);return ne(e,e->code[0]?e->code:"create-worker-use-refused");
}
void ln_scan_spawned(lm_new_target *n,int slot){if(n&&slot>=0&&slot<8){/* caller closed duplicate, never unlocked */n->slot_fds[slot]=-1;n->slot_active[slot]=1;}}
int ln_scan_finished(lm_new_target *n,int slot,lm_err *e){if(!n||slot<0||slot>=8)return ne(e,"create-worker-slot-state");n->slot_active[slot]=0;return registry_validate(n,e);}
static int held(lm_new_target *n,const char *p,const lm_mirror_file *f,lm_err *e){unsigned i;struct stat s;char id[33];for(i=0;i<n->held_count;i++){if(fstat(n->held[i],&s))return nerror(n,e,"create-liveness-fd-lost");identity(&s,id);if(!strcmp(id,f->identity))return exact(p,f,1,e);}if(n->held_count>=16)return nerror(n,e,"create-liveness-cap");if(!acquire(p,f,&n->held[n->held_count],e))return 0;n->held_count++;return 1;}
static int guard(lm_new_target *n,lm_err *e){char id[33],p[4096];struct stat s;if(!dir(n->root,id,1,e)||strcmp(id,n->root_id)||!dir(n->parent,id,0,e)||strcmp(id,n->parent_id))return nerror(n,e,"create-directory-changed");if(!exact(n->exe,&n->exe_id,1,e)||!exact(n->worker,&n->worker_id,1,e)||(n->font_id.present&&!exact(n->font,&n->font_id,1,e))||!exact(n->barrier_path,&n->barrier_id,1,e)||!absent(n->pending,e))return 0;if(!path(p,n->root,"lease",e)||!exact(p,&n->lease_id,1,e)||fstat(n->lease,&s))return nerror(n,e,"create-outer-lease");identity(&s,id);if(strcmp(id,n->lease_id.identity))return nerror(n,e,"create-outer-lease-changed");return inventory(n,0,e);}
static int chain(lm_new_target *n,lm_err *e){char p[4096];NRecord a,prev={0};lm_mirror_file id;unsigned i,seen=0;int end=0;
  if(!path(p,n->root,"anchor.json",e)||!record_read(n,p,&a,&id,1,e)||a.phase||a.ordinal||a.attempt||a.previous[0]||a.producer[0])return nerror(n,e,"create-anchor-shape");if(n->anchor_id.present&&!same(&n->anchor_id,&id))return nerror(n,e,"create-anchor-changed");n->anchor=a;n->anchor_id=id;
  for(i=0;i<N_RECORDS;i++){NRecord x;lm_mirror_file f;unsigned phase=seen?prev.phase:NP_ANCHOR;if(!nrecord_path(p,n,i,e)||!snap(p,1,N_RECORD_SIZE,&f,NULL,NULL,e))return 0;if(!f.present){end=1;continue;}if(end)return nerror(n,e,"create-record-gap");
    /* The C suffix has its own strict parser. Its first ordinal starts exactly
     * after ACK; no creation parser adopts or skips arbitrary JSON records. */
    if(phase==NP_ACK)break;
    if(!record_read(n,p,&x,&f,0,e)||x.ordinal!=i||strcmp(x.previous,seen?n->ids[i-1].sha:n->anchor_id.sha))return nerror(n,e,"create-record-chain");
    if(i<n->count&&!same(&f,&n->ids[i]))return nerror(n,e,"create-record-replaced");
    if(x.phase==NP_ATTEMPT){if(!((phase==NP_ANCHOR&&x.attempt==1)||(phase==NP_ATTEMPT&&prev.attempt==1&&x.attempt==2))||strcmp(x.producer,x.run)||!x.image.present||x.image.size||!x.live.present||!x.request.present)return nerror(n,e,"create-attempt-edge");}
    else {if(x.attempt!=prev.attempt||strcmp(x.producer,prev.producer)||strcmp(x.import_token,prev.import_token))return nerror(n,e,"create-attempt-lineage");
      if(x.phase==NP_FINISHED){if(phase!=NP_ATTEMPT||!x.result.present||!x.plan.present||!lm_mirror_same_file(&x.image,&prev.image))return nerror(n,e,"create-finished-edge");}
      else if(x.phase==NP_VERIFY){if((phase!=NP_FINISHED&&phase!=NP_VERIFY)||!x.live.present||!x.request.present||strcmp(x.verify_token,prev.verify_token)==0)return nerror(n,e,"create-verifier-edge");}
      else if(x.phase==NP_SEALED){if(phase!=NP_VERIFY||!x.copy.present||!x.baseline.present||!x.mirror.present||!same(&x.image,&prev.image)||!same(&x.plan,&prev.plan))return nerror(n,e,"create-sealed-edge");}
      else if(x.phase==NP_PUBLIC_VERIFY){if((phase!=NP_SEALED&&phase!=NP_PUBLIC_VERIFY)||!x.live.present||!x.request.present||!same(&x.image,&prev.image)||!same(&x.copy,&prev.copy)||!same(&x.baseline,&prev.baseline)||!same(&x.plan,&prev.plan)||!same(&x.mirror,&prev.mirror)||!x.observe_token[0]||!strcmp(x.observe_token,prev.observe_token))return nerror(n,e,"create-public-verifier-edge");}
      else if(x.phase==NP_ADOPT){if((phase!=NP_SEALED&&phase!=NP_PUBLIC_VERIFY)||!same(&x.image,&prev.image)||!same(&x.plan,&prev.plan)||!same(&x.copy,&prev.copy)||!same(&x.baseline,&prev.baseline)||!same(&x.mirror,&prev.mirror)||!same(&x.projection,&prev.projection)||(phase==NP_PUBLIC_VERIFY&&(!x.observed_result.present||!x.observed_copy.present||!x.observed_baseline.present||!x.observed_projection.present||strcmp(x.observe_token,prev.observe_token)))||(phase==NP_SEALED&&(x.observed_result.present||x.observed_copy.present||x.observed_baseline.present||x.observed_projection.present)))return nerror(n,e,"create-adopt-edge");}
      else if(x.phase==NP_ACK){if(phase!=NP_ADOPT||!same(&x.image,&prev.image)||!same(&x.mirror,&prev.mirror)||!same(&x.plan,&prev.plan)||!same(&x.copy,&prev.copy)||!same(&x.baseline,&prev.baseline)||!same(&x.result,&prev.result)||!same(&x.observed_result,&prev.observed_result)||!same(&x.observed_copy,&prev.observed_copy)||!same(&x.observed_baseline,&prev.observed_baseline)||strcmp(x.observe_token,prev.observe_token)||!same(&x.projection,&prev.projection)||!same(&x.observed_projection,&prev.observed_projection))return nerror(n,e,"create-ack-edge");}
      else return nerror(n,e,"create-phase-edge");}
    n->records[i]=x;n->ids[i]=f;prev=x;seen++;
  }
  if(seen<n->count)return nerror(n,e,"create-record-removed");n->count=seen;n->attempt=seen?prev.attempt:0;if(!guard(n,e)||!registry_validate(n,e))return 0;
  /* Retained original pack and every distinct worker request/liveness/result
   * remain identity-bound. A liveness acquisition is not a wait-status proof. */
  if(!nfile(p,n,"pack",a.run,".bin",e)||!exact(p,&n->pack_id,1,e))return 0;
  for(i=0;i<seen;i++){NRecord *x=&n->records[i];if(x->phase==NP_ATTEMPT||x->phase==NP_VERIFY||x->phase==NP_PUBLIC_VERIFY){if(!nfile(p,n,"live",x->run,".lock",e)||!exact(p,&x->live,1,e))return 0;if(!noutput(p,n,x->phase==NP_ATTEMPT?x->import_token:x->phase==NP_VERIFY?x->verify_token:x->observe_token,"request.json",e)||!exact(p,&x->request,1,e))return 0;}
    if(x->phase==NP_FINISHED){if(!noutput(p,n,x->import_token,"stdout.json",e)||!exact(p,&x->result,1,e)||!noutput(p,n,x->import_token,"planned-ledger.bin",e)||!exact(p,&x->plan,1,e))return 0;}}
  if(seen&&prev.phase>=NP_SEALED){lm_mirror_file image;int exists;if(!nfile(p,n,"image",prev.producer,".sqlite",e)||!snap(p,0,0,&image,NULL,NULL,e))return 0;exists=image.present;
    if(exists){if((prev.phase==NP_ADOPT||prev.phase==NP_ACK||prev.phase==NP_PUBLIC_VERIFY)||!exact(p,&prev.image,1,e)||!absent(n->target,e))return nerror(n,e,"create-public-private-disposition");}
    else {if(!snap(n->target,0,0,&image,NULL,NULL,e)||!lm_mirror_same_file(&image,&prev.image))return nerror(n,e,"create-public-identity-lost");n->published=1;}
    if(!noutput(p,n,prev.verify_token,"clone.sqlite",e)||!exact(p,&prev.copy,1,e)||!noutput(p,n,prev.verify_token,"baseline.bin",e)||!exact(p,&prev.baseline,1,e))return 0;
    if(!noutput(p,n,prev.import_token,"planned-ledger.bin",e)||!exact(p,&prev.plan,1,e)||!noutput(p,n,prev.verify_token,"stdout.json",e)||!exact(p,&prev.result,1,e)||!noutput(p,n,prev.verify_token,"public-projection.jsonl",e)||!exact(p,&prev.projection,1,e))return 0;
    if(prev.observed_result.present){if(!prev.observed_copy.present||!prev.observed_baseline.present||!noutput(p,n,prev.observe_token,"stdout.json",e)||!exact(p,&prev.observed_result,1,e)||!noutput(p,n,prev.observe_token,"clone.sqlite",e)||!exact(p,&prev.observed_copy,1,e)||!noutput(p,n,prev.observe_token,"baseline.bin",e)||!exact(p,&prev.observed_baseline,1,e)||!noutput(p,n,prev.observe_token,"public-projection.jsonl",e)||!exact(p,&prev.observed_projection,1,e))return 0;}
    else if(prev.observed_copy.present||prev.observed_baseline.present||prev.observed_projection.present)return nerror(n,e,"create-partial-observation-proof");
  }
  return 1;
}
static int append_record(lm_new_target *n,NRecord *x,lm_err *e){char p[4096];lm_mirror_file f;if(n->count+8>=N_RECORDS-12||!chain(n,e))return nerror(n,e,"create-prefix-record-reservation");x->ordinal=n->count;strcpy(x->previous,n->count?n->ids[n->count-1].sha:n->anchor_id.sha);if(!nrecord_path(p,n,n->count,e)||!record_write(n,p,x,&f,e))return 0;n->records[n->count]=*x;n->ids[n->count++]=f;return chain(n,e);}
static int exclude_workers(lm_new_target *n,lm_err *e){unsigned i;char p[4096];for(i=0;i<n->count;i++){NRecord *x=&n->records[i];if(x->phase==NP_ATTEMPT||x->phase==NP_VERIFY||x->phase==NP_PUBLIC_VERIFY){if(!nfile(p,n,"live",x->run,".lock",e)||!held(n,p,&x->live,e))return 0;}}return 1;}
static int copy_file(const char *src,const lm_mirror_file *want,const char *dest,lm_mirror_file *made,lm_err *e){char *raw=NULL;size_t size=0;lm_mirror_file got;int ok=0;if(!snap(src,1,N_LIMIT,&got,&raw,&size,e)||!same(&got,want)||!got.present)goto done;if(!write_new(dest,raw,size,e)||!snap(dest,1,N_LIMIT,made,NULL,NULL,e)||!lm_mirror_same_bytes(made,want))goto done;ok=1;done:free(raw);return ok?1:ne(e,e->code[0]?e->code:"create-copy-binding");}
static int request_make(lm_new_target *n,NRecord *x,const char *kind,const char *image,lm_err *e){
  char live[4096],output[4096],request[4096],oid[33];lm_sb b;lm_mirror_file empty={0};const char *token=!strcmp(kind,"import")?x->import_token:!strcmp(kind,"seal")?x->verify_token:x->observe_token;
  if(!nfile(live,n,"live",x->run,".lock",e)||!write_new(live,x->run,32,e)||!snap(live,1,32,&x->live,NULL,NULL,e)||!path(output,n->root,token,e)||mkdir(output,0700)||!syncdir(n->root,e)||!dir(output,oid,1,e))return 0;
  lm_sb_init(&b);lm_sb_str(&b,"{\"nonce\":");lm_sb_json(&b,x->run,32);lm_sb_str(&b,",\"live\":");lm_sb_json(&b,live,strlen(live));lm_sb_str(&b,",\"target\":");lm_sb_json(&b,image,strlen(image));lm_sb_str(&b,",\"pack\":");lm_sb_json(&b,!strcmp(kind,"import")?n->pack:"-",!strcmp(kind,"import")?strlen(n->pack):1);lm_sb_str(&b,",\"font\":");lm_sb_json(&b,n->font,strlen(n->font));lm_sb_str(&b,",\"kind\":");lm_sb_json(&b,kind,strlen(kind));lm_sb_str(&b,",\"output\":");lm_sb_json(&b,output,strlen(output));lm_sb_str(&b,",\"output_identity\":");lm_sb_json(&b,oid,32);lm_sb_str(&b,",\"live_file\":");fj(&b,&x->live);lm_sb_str(&b,",\"image_file\":");fj(&b,&x->image);lm_sb_str(&b,",\"pack_file\":");fj(&b,!strcmp(kind,"import")?&n->pack_id:&empty);lm_sb_str(&b,",\"font_file\":");fj(&b,&n->font_id);lm_sb_str(&b,"}\n");
  if(b.oom||b.n>N_RECORD_SIZE||!path(request,output,"request.json",e)||!write_new(request,b.p,b.n,e)||!snap(request,1,N_RECORD_SIZE,&x->request,NULL,NULL,e)){lm_sb_free(&b);return 0;}lm_sb_free(&b);return 1;
}
static int drain(int fd,int log,uint64_t *total,int *eof,lm_err *e){char b[4096];ssize_t k;while((k=read(fd,b,sizeof(b)))>0){size_t off=0;if((uint64_t)k>1048576-*total)return ne(e,"create-child-log-cap");*total+=(uint64_t)k;while(off<(size_t)k){ssize_t w=write(log,b+off,(size_t)k-off);if(w<=0)return ne(e,"create-child-log-write");off+=(size_t)w;}}if(k==0)*eof=1;else if(errno!=EAGAIN&&errno!=EWOULDBLOCK&&errno!=EINTR)return ne(e,"create-child-pipe");return 1;}
static int spawn_child(lm_new_target *n,NRecord *x,int importer,const char *image,lm_err *e){
  char request[4096],output[4096],live[4096],logs[2][4096],pidfile[4096],pidtext[64];const char *token=importer==1?x->import_token:importer==2?x->observe_token:x->verify_token;int fd=-1,pipes[2][2]={{-1,-1},{-1,-1}},log[2]={-1,-1},eof[2]={0,0},status=0,reaped=0,spawned=0,ok=0,ha=0,ht=0;pid_t pid=-1;posix_spawn_file_actions_t a;posix_spawnattr_t attr;double start;uint64_t total=0;unsigned i;struct stat s;char logids[2][33];
  if(!path(output,n->root,token,e)||!path(request,output,"request.json",e)||!nfile(live,n,"live",x->run,".lock",e)||!acquire(live,&x->live,&fd,e))goto done;
  if(!path(logs[0],output,"stdout.json",e)||!path(logs[1],output,"stderr.txt",e))goto done;
  for(i=0;i<2;i++){log[i]=open(logs[i],O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);if(log[i]<0||fstat(log[i],&s)||pipe(pipes[i]))goto done;identity(&s,logids[i]);if(fcntl(pipes[i][0],F_SETFD,FD_CLOEXEC)||fcntl(pipes[i][1],F_SETFD,FD_CLOEXEC)||fcntl(pipes[i][0],F_SETFL,O_NONBLOCK))goto done;}
  if(posix_spawn_file_actions_init(&a))goto done;ha=1;if(posix_spawnattr_init(&attr))goto done;ht=1;
  if(posix_spawn_file_actions_addopen(&a,0,"/dev/null",O_RDONLY,0)||posix_spawn_file_actions_adddup2(&a,pipes[0][1],1)||posix_spawn_file_actions_adddup2(&a,pipes[1][1],2)||posix_spawn_file_actions_adddup2(&a,fd,3))goto done;
#ifdef __APPLE__
  if(posix_spawnattr_setflags(&attr,POSIX_SPAWN_CLOEXEC_DEFAULT|POSIX_SPAWN_SETPGROUP)||posix_spawnattr_setpgroup(&attr,0))goto done;
#else
  if(posix_spawn_file_actions_addclosefrom_np(&a,4)||posix_spawnattr_setflags(&attr,POSIX_SPAWN_SETPGROUP)||posix_spawnattr_setpgroup(&attr,0))goto done;
#endif
  if(!npause(n,importer==1?"spawn-gap":importer==2?"observe-spawn-gap":"seal-spawn-gap",e)||!chain(n,e)||!exact(request,&x->request,1,e)||!exact(image,&x->image,importer==1?1:0,e))goto done;
  if(importer==1){char *args[24];unsigned z=0;args[z++]=n->exe;args[z++]="migrate";args[z++]="--private-create-request";args[z++]=request;args[z++]="--target";args[z++]=(char*)image;args[z++]="--pack";args[z++]=n->pack;args[z++]="--recovery-font";args[z++]=n->font;if(n->partial)args[z++]="--allow-partial";if(n->preview)args[z++]="--dry-run";if(n->inject[0]){args[z++]="--inject";args[z++]=n->inject;}args[z]=NULL;if(posix_spawn(&pid,n->exe,&a,&attr,args,environ))goto done;}
  else {char *args[]={n->worker,importer==2?"observe":"seal",(char*)image,output,x->run,n->font,"none",NULL};if(posix_spawn(&pid,n->worker,&a,&attr,args,environ))goto done;}
  spawned=1;/* Never LOCK_UN: child holds the same OFD lock. */if(close(fd)){fd=-1;goto done;}fd=-1;for(i=0;i<2;i++){close(pipes[i][1]);pipes[i][1]=-1;}
  if(!path(pidfile,output,"child.pid",e))goto done;snprintf(pidtext,sizeof(pidtext),"%ld\n",(long)pid);if(!write_new(pidfile,pidtext,strlen(pidtext),e))goto done;
  if(!npause(n,importer==1?"child-spawned":importer==2?"observe-child-spawned":"seal-child-spawned",e))goto done;
  start=now();while(!reaped||!eof[0]||!eof[1]){pid_t got;struct timespec delay={0,10000000};if(!drain(pipes[0][0],log[0],&total,&eof[0],e)||!drain(pipes[1][0],log[1],&total,&eof[1],e)||!inventory(n,0,e)||!cancel(n,e))goto done;if(!reaped){got=waitpid(pid,&status,WNOHANG);if(got==pid)reaped=1;else if(got<0&&errno!=EINTR)goto done;}if(start<0||now()-start>35){ne(e,"create-child-deadline");goto done;}if(!reaped||!eof[0]||!eof[1])nanosleep(&delay,NULL);}
  if(!WIFEXITED(status)||WEXITSTATUS(status)){ne(e,"create-child-exit-refused");goto done;}
  for(i=0;i<2;i++)if(fsync(log[i]))goto done;
  if(!snap(logs[0],1,1048576,&x->result,NULL,NULL,e)||strcmp(x->result.identity,logids[0])||!exclude_workers(n,e)||!chain(n,e)||(importer!=2&&!sidecars_absent(image,e)))goto done;
  ok=1;
 done:
  if(spawned&&!reaped){kill(-pid,SIGKILL);while(waitpid(pid,&status,0)<0&&errno==EINTR){}reaped=1;}
  /* If descendants kept the streams alive, terminate only this spawned group.
   * No process matching a name/PID from an older attempt is ever killed. */
  if(spawned&&(!eof[0]||!eof[1]))kill(-pid,SIGKILL);
  if(fd>=0)close(fd);if(ha)posix_spawn_file_actions_destroy(&a);if(ht)posix_spawnattr_destroy(&attr);
  for(i=0;i<2;i++){unsigned k;for(k=0;k<2;k++)if(pipes[i][k]>=0)close(pipes[i][k]);if(log[i]>=0){if(fsync(log[i]))ok=0;if(close(log[i]))ok=0;}}
  if(!ok&&!e->code[0])ne(e,"create-child-transport-refused");return ok;
}
static int result_check(lm_new_target *n,NRecord *x,int importer,lm_err *e){char p[4096],*raw=NULL,msg[128],nonce[33],digest[65],target_id[33];size_t size=0;lm_mirror_file f;jv *j=NULL;int ok=0;if(!noutput(p,n,importer==1?x->import_token:importer==2?x->observe_token:x->verify_token,"stdout.json",e)||!snap(p,1,1048576,&f,&raw,&size,e)||!same(&f,&x->result))goto done;j=lm_json_parse(raw,size,msg,sizeof(msg));if(!j||j->t!=J_OBJ)goto done;
  if(importer==1){const jv *child=lm_get(j,"creation_child"),*atomic=lm_get(j,"atomicity"),*tx=lm_get(atomic,"transaction");const char *result=lm_get_str(j,"result"),*commit=lm_get_str(tx,"target_commit");if(!result||strcmp(result,"success")||!commit||strcmp(commit,"committed")||!js(child,"nonce",nonce,sizeof(nonce))||strcmp(nonce,x->run))goto done;
    if(!noutput(p,n,x->import_token,"planned-ledger.bin",e)||!snap(p,1,N_LIMIT,&x->plan,NULL,NULL,e)||!x->plan.present||!x->plan.size)goto done;
  }else {const char *reported_mode=lm_get_str(j,"mode");const jv *passed=lm_get(j,"passed"),*found=lm_get(j,"ledger_found");if(!reported_mode||strcmp(reported_mode,importer==2?"observe":"seal")||!passed||passed->t!=J_BOOL||!passed->b||!found||found->t!=J_BOOL||!found->b||!js(j,"nonce",nonce,sizeof(nonce))||strcmp(nonce,x->run)||!js(j,"target_identity",target_id,sizeof(target_id))||strcmp(target_id,x->image.identity)||!js(j,"baseline_sha256",digest,sizeof(digest)))goto done;
    if(!noutput(p,n,importer==2?x->observe_token:x->verify_token,"baseline.bin",e)||!snap(p,1,N_LIMIT,&x->baseline,NULL,NULL,e)||!x->baseline.present||strcmp(digest,x->baseline.sha)||!noutput(p,n,importer==2?x->observe_token:x->verify_token,"clone.sqlite",e)||!snap(p,1,N_LIMIT,&x->copy,NULL,NULL,e)||!x->copy.present)goto done;
    if(!js(j,"projection_sha256",digest,sizeof(digest))||!noutput(p,n,importer==2?x->observe_token:x->verify_token,"public-projection.jsonl",e)||!snap(p,1,N_LIMIT,&x->projection,NULL,NULL,e)||!x->projection.present||strcmp(digest,x->projection.sha))goto done;
    if(!noutput(p,n,importer==2?x->observe_token:x->verify_token,"ledger.bin",e)||!snap(p,1,N_LIMIT,&f,NULL,NULL,e)||!lm_mirror_same_bytes(&f,&x->plan))goto done;
  }ok=1;
 done:free(raw);lm_json_free(j);return ok?1:nerror(n,e,"create-child-result-binding");}
static int import_attempt(lm_new_target *n,lm_err *e){NRecord x={0};char image[4096];unsigned attempt=n->attempt+1;if(attempt>2||!exclude_workers(n,e)||!absent(n->target,e)||!sidecars_absent(n->target,e)||!inventory(n,7*N_LIMIT+4*1048576,e))return nerror(n,e,"create-private-attempt-reservation");
  if(!random_nonce(x.run,e))return 0;strcpy(x.producer,x.run);x.phase=NP_ATTEMPT;x.attempt=attempt;snprintf(x.import_token,sizeof(x.import_token),"import-%s",x.run);
  if(!nfile(image,n,"image",x.producer,".sqlite",e)||!write_new(image,"",0,e)||!snap(image,1,N_LIMIT,&x.image,NULL,NULL,e)||!request_make(n,&x,"import",image,e)||!append_record(n,&x,e)||!npause(n,"private-attempt-durable",e))return 0;
  if(!spawn_child(n,&x,1,image,e)||!result_check(n,&x,1,e)||!snap(image,1,N_LIMIT,&x.image,NULL,NULL,e)||!x.image.present||!x.image.size||!npause(n,"child-exited-before-finished",e))return 0;
  x.phase=NP_FINISHED;if(!append_record(n,&x,e)||!npause(n,"private-finished-durable",e))return 0;return 1;
}
static int seal_image(lm_new_target *n,lm_err *e){NRecord x=n->records[n->count-1];char image[4096],p[4096];unsigned i,verifiers=0;for(i=0;i<n->count;i++)if(n->records[i].phase==NP_VERIFY)verifiers++;
  if(verifiers>=2||!exclude_workers(n,e)||!absent(n->target,e)||!nfile(image,n,"image",x.producer,".sqlite",e)||!exact(image,&x.image,1,e)||!sidecars_absent(image,e)||!inventory(n,6*N_LIMIT+4*1048576,e))return nerror(n,e,"create-seal-reservation-or-state");
  x.phase=NP_VERIFY;if(!random_nonce(x.run,e))return 0;snprintf(x.verify_token,sizeof(x.verify_token),"seal-%s",x.run);memset(&x.result,0,sizeof(x.result));if(!request_make(n,&x,"seal",image,e)||!append_record(n,&x,e)||!npause(n,"seal-request-durable",e)||!spawn_child(n,&x,0,image,e)||!result_check(n,&x,0,e)||!exact(image,&x.image,1,e)||!sidecars_absent(image,e))return 0;
  if(!nfile(p,n,"mirror",x.producer,".bin",e)){return 0;}{char plan[4096];if(!noutput(plan,n,x.import_token,"planned-ledger.bin",e)||!copy_file(plan,&x.plan,p,&x.mirror,e))return 0;}
  x.phase=NP_SEALED;if(!append_record(n,&x,e)||!npause(n,"sealed-before-publish",e))return 0;return 1;
}
static int rename_no_replace(const char *from,const char *to,lm_err *e){
#ifdef __APPLE__
  if(renameatx_np(AT_FDCWD,from,AT_FDCWD,to,RENAME_EXCL))return ne(e,errno==EXDEV?"create-cross-filesystem-refused":"create-no-replace-refused");
#else
  if(renameat2(AT_FDCWD,from,AT_FDCWD,to,RENAME_NOREPLACE))return ne(e,errno==EXDEV?"create-cross-filesystem-refused":"create-no-replace-refused");
#endif
  return 1;
}
static int sync_image(const char *p,const lm_mirror_file *want,lm_err *e){int fd;struct stat s;char id[33];if(!exact(p,want,1,e))return 0;fd=open(p,O_RDONLY|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC);if(fd<0)return ne(e,"create-image-sync-open");if(fstat(fd,&s)){close(fd);return ne(e,"create-image-sync-stat");}identity(&s,id);if(fenced_target[0]&&!strcmp(id,fenced_target))return ne(e,"create-lease-target-fd-quarantined");if(strcmp(id,want->identity)||!S_ISREG(s.st_mode)||s.st_nlink!=1){close(fd);return ne(e,"create-image-sync-binding");}if(fsync(fd)){close(fd);return ne(e,"create-image-sync");}if(close(fd))return ne(e,"create-image-close");return exact(p,want,1,e);}
/* Ambiguous visibility: bind a new liveness request before a real public SDK
 * owner is opened. The child independently captures the COMPLETE current state
 * and public projections while that same owner fences writers. Changed ordinary
 * metadata is preserved; the exact planned ledger is still required. This is
 * current-state adoption only, never permission to replay the sealed image. */
static int observe_public(lm_new_target *n,NRecord *x,lm_err *e){
  exr_library *owner=NULL;exr_error error={0};void *ledger=NULL;size_t size=0;int found=0,ok=0;unsigned i,observations=0;lm_mirror_file sealed_copy=x->copy,sealed_baseline=x->baseline,sealed_result=x->result,sealed_projection=x->projection;
  for(i=0;i<n->count;i++)if(n->records[i].phase==NP_PUBLIC_VERIFY)observations++;
  if(observations>=2||!exclude_workers(n,e)||!chain(n,e)||!inventory(n,6*N_LIMIT+4*1048576,e))return nerror(n,e,"create-public-observation-reservation");
  x->phase=NP_PUBLIC_VERIFY;if(!random_nonce(x->run,e))return 0;snprintf(x->observe_token,sizeof(x->observe_token),"observe-%s",x->run);
  if(!request_make(n,x,"observe",n->target,e)||!append_record(n,x,e)||!npause(n,"public-owner-before-open",e)||!chain(n,e)||!exact(n->target,&x->image,0,e))return 0;
  if(exr_library_migration_open(n->target,&owner,&error)!=EXR_OK)return nerror(n,e,"create-public-owner-open-refused");strcpy(fenced_target,x->image.identity);
  if(!npause(n,"public-owner-open",e)||!spawn_child(n,x,2,n->target,e)||!result_check(n,x,2,e))goto done;
  if(exr_library_migration_ledger_get(owner,&ledger,&size,&found,&error)!=EXR_OK||!found||!ln_ledger(n,ledger,size,e)||!chain(n,e)||!exact(n->target,&x->image,0,e))goto done;
  x->observed_result=x->result;x->observed_copy=x->copy;x->observed_baseline=x->baseline;x->observed_projection=x->projection;ok=1;
 done:
  exr_free(ledger);if(owner){if(exr_library_migration_finish(owner,0,&error)!=EXR_OK)ok=0;exr_library_close(owner);}fenced_target[0]=0;
  x->copy=sealed_copy;x->baseline=sealed_baseline;x->result=sealed_result;x->projection=sealed_projection;
  if(!ok)return nerror(n,e,e->code[0]?e->code:"create-public-current-state-refused");
  if(!npause(n,"public-observation-before-adopt",e)||!syncdir(n->root,e)||!syncdir(n->parent,e)||!chain(n,e)||!exact(n->target,&x->image,0,e))return 0;
  {char p[4096];if(!noutput(p,n,x->observe_token,"stdout.json",e)||!exact(p,&x->observed_result,1,e)||!noutput(p,n,x->observe_token,"clone.sqlite",e)||!exact(p,&x->observed_copy,1,e)||!noutput(p,n,x->observe_token,"baseline.bin",e)||!exact(p,&x->observed_baseline,1,e)||!noutput(p,n,x->observe_token,"public-projection.jsonl",e)||!exact(p,&x->observed_projection,1,e))return 0;}
  x->phase=NP_ADOPT;strcpy(x->run,n->nonce);return append_record(n,x,e);
}
static int no_suffix_yet(lm_new_target *n,lm_err *e){unsigned i;char p[4096];lm_mirror_file f;DIR *d;struct dirent *v;
  for(i=n->count;i<N_RECORDS;i++)if(!nrecord_path(p,n,i,e)||!snap(p,0,0,&f,NULL,NULL,e)||f.present)return nerror(n,e,"create-premature-suffix-record");
  d=opendir(n->root);if(!d)return nerror(n,e,"create-final-root-open");while((v=readdir(d))){unsigned ordinal;char tail;if(!strncmp(v->d_name,"record-",7)&&(sscanf(v->d_name,"record-%u.json%c",&ordinal,&tail)!=1||ordinal>=n->count||strlen(v->d_name)!=14)){closedir(d);return nerror(n,e,"create-foreign-record-name");}}return closedir(d)==0?1:nerror(n,e,"create-final-root-close");
}
static int publish_image(lm_new_target *n,lm_err *e){NRecord x=n->records[n->count-1];char image[4096],mirror[4096];lm_mirror_file current;int private_present;
  if(!exclude_workers(n,e)||!chain(n,e)||!nfile(image,n,"image",x.producer,".sqlite",e)||!snap(image,0,0,&current,NULL,NULL,e))return 0;private_present=current.present;
  if((x.phase==NP_SEALED&&!private_present)||x.phase==NP_PUBLIC_VERIFY){if(!observe_public(n,&x,e))return 0;}
  if(x.phase==NP_SEALED){
    if(!sidecars_absent(image,e)||!sidecars_absent(n->target,e)||!absent(n->target,e)||!absent(n->mirror_path,e)||!inventory(n,6*N_LIMIT+4*1048576+12*N_RECORD_SIZE+1048576,e)||n->count+8+12>=N_RECORDS||n->names+24+12>N_NAMES)return nerror(n,e,"create-future-C-reservation");
    if(!sync_image(image,&x.image,e)||!npause(n,"before-public-rename",e)||!chain(n,e)||!sidecars_absent(image,e)||!sidecars_absent(n->target,e)||!absent(n->target,e)||!exact(image,&x.image,1,e)||!rename_no_replace(image,n->target,e))return 0;n->published=1;
    if(!npause(n,"public-before-sync",e)||!syncdir(n->root,e)||!syncdir(n->parent,e)||!npause(n,"public-synced-before-adopt",e)||!chain(n,e))return 0;
    x.phase=NP_ADOPT;strcpy(x.run,n->nonce);if(!append_record(n,&x,e))return 0;
  }
  if(!nfile(mirror,n,"mirror",x.producer,".bin",e)||!snap(n->mirror_path,1,N_LIMIT,&current,NULL,NULL,e))return 0;
  if(!current.present){if(!exact(mirror,&x.mirror,1,e)||!rename_no_replace(mirror,n->mirror_path,e))return 0;}
  else if(!same(&current,&x.mirror))return nerror(n,e,"create-foreign-mirror");
  if(!npause(n,"mirror-before-sync",e)||!syncdir(n->root,e)||!syncdir(n->parent,e)||!exact(n->mirror_path,&x.mirror,1,e)||!chain(n,e))return 0;
  x.phase=NP_ACK;strcpy(x.run,n->nonce);if(!append_record(n,&x,e)||!npause(n,"create-ack-durable",e)||!exclude_workers(n,e)||!chain(n,e)||!exact(n->target,&x.image,0,e)||!exact(n->mirror_path,&x.mirror,1,e)||!no_suffix_yet(n,e))return 0;n->acknowledged=1;return 1;
}
static int executable_paths(lm_new_target *n,lm_err *e){char self[4096],*slash;
#ifdef __APPLE__
  uint32_t z=sizeof(self);if(_NSGetExecutablePath(self,&z))return ne(e,"create-executable-path");
#else
  ssize_t z=readlink("/proc/self/exe",self,sizeof(self)-1);if(z<0||(size_t)z>=sizeof(self)-1)return ne(e,"create-executable-path");self[z]=0;
#endif
  if(!realpath(self,n->exe))return ne(e,"create-executable-resolve");strcpy(self,n->exe);slash=strrchr(self,'/');if(!slash)return ne(e,"create-executable-parent");*slash=0;if(!path(n->worker,self,"exreader-migration-recovery-worker",e)||!snap(n->exe,1,N_LIMIT,&n->exe_id,NULL,NULL,e)||!n->exe_id.present||!snap(n->worker,1,N_LIMIT,&n->worker_id,NULL,NULL,e)||!n->worker_id.present)return 0;return 1;
}
static int initialize(lm_new_target *n,const char *source,lm_err *e){char p[4096];NRecord a={0};lm_mirror_file input;lm_pack pack={0};uint64_t projected;int ok=0;
  if(!absent(n->target,e)||!sidecars_absent(n->target,e)||!absent(n->mirror_path,e)||!absent(n->barrier_path,e)||!absent(n->pending,e)||!source||!snap(source,1,N_LIMIT,&input,NULL,NULL,e)||!input.present||!lm_pack_open(source,&pack,e)||!lm_pack_verify(&pack,n->cancelled,n->context,e)||strcmp(pack.sha,input.sha))goto done;
  projected=2*pack.size+8*pack.manifest_len+(uint64_t)pack.books->n*8*1048576+(uint64_t)pack.notes->n*131072+16*1048576;if(projected>N_LIMIT){ne(e,"create-import-growth-bound");goto done;}
  if(mkdir(n->root,0700)||!dir(n->root,n->root_id,1,e)||!path(p,n->root,"lease",e)||!write_new(p,n->nonce,32,e)||!snap(p,1,32,&n->lease_id,NULL,NULL,e)||!acquire(p,&n->lease_id,&n->lease,e))goto done;
  if(!registry_make(n,e)||!write_new(n->barrier_path,n->nonce,32,e)||!snap(n->barrier_path,1,32,&n->barrier_id,NULL,NULL,e)||!nfile(n->pack,n,"pack",n->nonce,".bin",e)||!copy_file(source,&input,n->pack,&n->pack_id,e))goto done;
  strcpy(a.run,n->nonce);if(!path(p,n->root,"anchor.json",e)||!record_write(n,p,&a,&n->anchor_id,e)||!syncdir(n->parent,e))goto done;n->anchor=a;ok=1;
 done:lm_pack_close(&pack);return ok;
}
/* Complete bytes visible after a failed prior fsync are not a durable receipt.
 * Re-establish every admitted prefix/registry write under the same outer lease,
 * before any SDK open or read-view admission. No database image is rewritten. */
static int load(lm_new_target *n,lm_err *e){char p[4096];NRecord a;unsigned i;lm_mirror_file use;
  if(!dir(n->root,n->root_id,1,e)||!path(p,n->root,"anchor.json",e)||!record_read(n,p,&a,&n->anchor_id,1,e)||!path(p,n->root,"lease",e)||!acquire(p,&n->lease_id,&n->lease,e)||!chain(n,e)||!exclude_workers(n,e)||!nfile(n->pack,n,"pack",a.run,".bin",e))return 0;
  if(!path(p,n->root,"anchor.json",e)||!sync_image(p,&n->anchor_id,e)||!path(p,n->root,"worker-slots.json",e)||!sync_image(p,&n->registry,e))return 0;
  for(i=0;i<n->count;i++)if(!nrecord_path(p,n,i,e)||!sync_image(p,&n->ids[i],e))return 0;
  for(i=0;i<8;i++)if(!slot_path(n,i,1,p,e)||!snap(p,1,N_RECORD_SIZE,&use,NULL,NULL,e)||!lm_mirror_same_file(&use,&n->uses[i])||!sync_image(p,&use,e))return 0;
  return syncdir(n->root,e)&&syncdir(n->parent,e)&&chain(n,e)&&exclude_workers(n,e);
}
int ln_route(lm_new_target **out,const char *exe,const char *cmd,const char *target,const char *pack,const char *font,int create,int recover,int partial,int preview,int br,const char *inject,lm_cancel_fn cb,void *context,int *handled,lm_err *e){
  lm_new_target *n;char raw[4096],leaf[4096],*slash,root[4096],anchor[4096],*data=NULL;size_t z=0;lm_mirror_file f;struct stat s;int root_exists=0,known=0;*out=NULL;*handled=0;(void)exe;
  if(!target||!*target||strlen(target)>3500||!strncmp(target,"file:",5)||strchr(target,'?'))return create?ne(e,"create-target-path"):1;
  strcpy(raw,target);slash=strrchr(raw,'/');if(slash){strcpy(leaf,slash+1);if(slash==raw)slash[1]=0;else *slash=0;}else{strcpy(leaf,raw);strcpy(raw,".");}if(!leaf[0]||!strcmp(leaf,".")||!strcmp(leaf,".."))return ne(e,"create-target-leaf");
  if(!realpath(raw,root))return create?ne(e,"create-parent-resolve"):1;if(snprintf(raw,sizeof(raw),"%s/%s",root,leaf)>=3500)return ne(e,"create-canonical-path-bound");snprintf(anchor,sizeof(anchor),"%s.migration-recovery/anchor.json",raw);snprintf(root,sizeof(root),"%s.migration-recovery",raw);
  if(!lstat(root,&s)){root_exists=1;if(snap(anchor,1,N_RECORD_SIZE,&f,&data,&z,e)&&f.present){char msg[128];jv *j=lm_json_parse(data,z,msg,sizeof(msg));const char *magic=lm_get_str(j,"magic");known=magic&&!strcmp(magic,N_MAGIC);lm_json_free(j);}free(data);if(!known){if(create)return ne(e,"create-foreign-or-partial-profile");return 1;}}
  else if(errno!=ENOENT)return ne(e,"create-profile-stat");
  if(!create&&!known)return 1;if(br)return ne(e,"create-break-lock-unsupported");
  if(create&&strcmp(cmd,"migrate")&&strcmp(cmd,"recover-migration"))return ne(e,"create-command-required");
  n=calloc(1,sizeof(*n));if(!n)return ne(e,"create-allocation");*out=n;n->lease=-1;{unsigned i;for(i=0;i<8;i++)n->slot_fds[i]=-1;}n->started=now();n->cancelled=cb;n->context=context;n->partial=partial;n->preview=preview;n->recover=recover;strcpy(n->target,raw);strcpy(n->root,root);strcpy(n->parent,raw);slash=strrchr(n->parent,'/');*slash=0;if(!n->parent[0])strcpy(n->parent,"/");
  lm_sha_bytes(n->target,strlen(n->target),n->target_path_sha);snprintf(n->barrier_path,sizeof(n->barrier_path),"%s.migrate-lock",raw);snprintf(n->pending,sizeof(n->pending),"%s.migration-pending.json",raw);snprintf(n->mirror_path,sizeof(n->mirror_path),"%s.legacy-map.json",raw);
  if(inject)snprintf(n->inject,sizeof(n->inject),"%s",inject);if(!random_nonce(n->nonce,e)||!dir(n->parent,n->parent_id,0,e)||!executable_paths(n,e))goto failed;
  if(font&&strcmp(font,"-")){if(!realpath(font,n->font)||!snap(n->font,1,N_LIMIT,&n->font_id,NULL,NULL,e)||!n->font_id.present)goto failed;}else strcpy(n->font,"-");
  {struct statfs fs;if(statfs(n->parent,&fs))goto failed;
#ifdef __APPLE__
    if(strcmp(fs.f_fstypename,"apfs")){ne(e,"create-filesystem-unqualified");goto failed;}
#else
    if((unsigned long)fs.f_type!=0xef53ul){ne(e,"create-filesystem-unqualified");goto failed;}
#endif
  }
  if(root_exists){if(!load(n,e))goto failed;}else{if(!create||!initialize(n,pack,e))goto failed;}
  if(!nfile(n->run_dir,n,"create-run",n->nonce,"",e)||mkdir(n->run_dir,0700)||!syncdir(n->root,e)||!chain(n,e))goto failed;
  if(n->count&&n->records[n->count-1].phase==NP_ACK){n->acknowledged=1;return 1;}
  if(!create||(!recover&&root_exists)){ne(e,"create-explicit-recovery-required");goto failed;}
  n->handled=1;*handled=1;if(!npause(n,"creation-anchor-durable",e))goto failed;
  if(!n->count||n->records[n->count-1].phase==NP_ATTEMPT){if(!import_attempt(n,e))goto failed;}
  if(n->records[n->count-1].phase==NP_FINISHED||n->records[n->count-1].phase==NP_VERIFY){if(!seal_image(n,e))goto failed;}
  if(!publish_image(n,e))goto failed;return 1;
 failed:if(!n->reason[0])snprintf(n->reason,sizeof(n->reason),"%s",e->code[0]?e->code:"create-operation-refused");return 0;
}
int ln_validate(lm_new_target *n,ln_prefix *v,lm_err *e){NRecord *x;if(!n||!chain(n,e)||!exclude_workers(n,e)||!n->count||(x=&n->records[n->count-1])->phase!=NP_ACK)return ne(e,"create-prefix-not-acknowledged");
  memset(v,0,sizeof(*v));v->records=n->count;v->registry_reserve=8;v->lease=n->lease;strcpy(v->root_id,n->root_id);strcpy(v->parent_id,n->parent_id);strcpy(v->target_id,x->image.identity);strcpy(v->run,x->run);strcpy(v->pack_sha,n->pack_id.sha);v->tail=n->ids[n->count-1];v->lease_file=n->lease_id;v->barrier=n->barrier_id;v->worker=n->worker_id;v->font=n->font_id;v->mirror=x->mirror;return 1;}
int ln_ledger(lm_new_target *n,const void *data,size_t size,lm_err *e){char p[4096],*raw=NULL;size_t z=0;lm_mirror_file f;int ok;if(!n||!n->count)return ne(e,"create-ledger-context");if(!noutput(p,n,n->records[n->count-1].import_token,"planned-ledger.bin",e)||!snap(p,1,N_LIMIT,&f,&raw,&z,e)||!same(&f,&n->records[n->count-1].plan)){free(raw);return 0;}ok=size==z&&data&&!memcmp(data,raw,z);free(raw);return ok?1:ne(e,"create-ledger-lineage");}
void ln_report(lm_new_target *n,lm_sb *b){lm_sb_str(b,"{\"protocol\":\"EXRCREATE1\",\"profile\":\"POSIX-private-DELETE\",\"phase\":");lm_sb_json(b,n?n->phase:"preopen-refusal",strlen(n?n->phase:"preopen-refusal"));lm_sb_str(b,",\"reason\":");lm_sb_json(b,n?n->reason:"",strlen(n?n->reason:""));lm_sb_fmt(b,",\"private_attempts\":%u,\"records\":%u,\"public_name_observed\":%s,\"creation_acknowledged\":%s,\"explicit_recovery_required\":%s,\"full_p0_acceptance\":false,\"physical_power_loss_qualified\":false,\"evidence_retirement\":\"never\"",n?n->attempt:0,n?n->count:0,n&&n->published?"true":"false",n&&n->acknowledged?"true":"false",n&&!n->acknowledged?"true":"false");
  lm_sb_str(b,",\"private_import_report\":");
  if(n){unsigned i;const NRecord *finished=NULL;for(i=0;i<n->count;i++)if(n->records[i].phase==NP_FINISHED)finished=&n->records[i];
    if(finished){char p[4096];lm_err e={{0},{0}};if(noutput(p,n,finished->import_token,"stdout.json",&e)){lm_sb_str(b,"{\"parent_successful_wait_recorded\":true,\"path\":");lm_sb_json(b,p,strlen(p));lm_sb_str(b,",\"file\":");fj(b,&finished->result);lm_sb_str(b,"}");}else lm_sb_str(b,"null");}else lm_sb_str(b,"null");
  }else lm_sb_str(b,"null");lm_sb_str(b,"}");
}
#endif /* coordinator, not worker */
#endif /* POSIX */
