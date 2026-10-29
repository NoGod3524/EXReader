/* SPDX-License-Identifier: MIT
 * Existing-target recovery candidate only. Frozen SDK and legacy binaries do
 * not use this module. No database-file replacement or evidence retirement. */
#define _GNU_SOURCE 1
#define _DARWIN_C_SOURCE 1
#include "lm_recovery.h"
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <time.h>
#include <stdint.h>
#ifndef _WIN32
#include <unistd.h>
#include <fcntl.h>
#include <dirent.h>
#include <sys/stat.h>
#include <sys/file.h>
#include <sys/wait.h>
#include <sys/statvfs.h>
#include <spawn.h>
#include <signal.h>
#ifdef __APPLE__
#include <mach-o/dyld.h>
#include <sys/mount.h>
#else
#include <sys/vfs.h>
#endif
extern char **environ;
#endif
#define R_LIMIT ((uint64_t)LM_RECOVERY_LIMIT)
#define R_TOTAL (512ull*1024*1024)
#define R_RECORDS 32u
#define R_NAMES 128u
#define R_RESERVE 12u
#define R_RECORD_BYTES 8192u
#define R_MAGIC "EXRRECOVERY1"
enum { RP_ANCHOR=0,RP_BASE=1,RP_OPENING=2,RP_PREP=3,RP_MIRROR=4,RP_ACK=5,RP_FRESH=6,RP_RESTORE_PREP=7,RP_RESTORED=8 };
typedef struct {
  unsigned ordinal,phase,generation;char run[33],previous[65],self[33],base_token[64],pack[65];
  lm_mirror_file baseline,before,after,preimage,plan,pack_file;
} RRecord;
struct lm_recovery {
  char target[4096],pack_path[4096],font[4096],root[4096],policy_root[4096],parent[4096],worker[4096],barrier[4096],pending[4096],run_dir[4096];
  char nonce[33],root_id[33],parent_id[33],target_id[33],pack_sha[65],phase[48],route[16],worker_reason[96];
  lm_mirror_file anchor_id,lease_id,barrier_id,worker_id,font_id,target_before,pack_input,record_ids[R_RECORDS];
  RRecord records[R_RECORDS],base,anchor;unsigned count,generation,scan_serial,attempt_records,quarantined;
  int lease,owner_active,opening,attempted,compared,acknowledged,alias_race_seen,rollback_valid,rollback_status,commit_status,failed,read_only,new_root,root_seen,ledger_found;
  uint64_t bytes,blocks,reserved,projected;char reason[64];
  lm_cancel_fn cancelled;void *context;
};
static int rr(lm_recovery *r,lm_err *e,const char *code){if(r&&!r->failed){r->failed=1;snprintf(r->reason,sizeof(r->reason),"%s",code);}lm_err_set(e,code,"%s (native errno %d)",code,errno);return 0;}
static int rp(char *out,const char *base,const char *name,lm_recovery *r,lm_err *e){if(snprintf(out,4096,"%s/%s",base,name)>=4096)return rr(r,e,"recovery-path-bound");return 1;}
static int hex(const char *s,size_t n){return s&&strlen(s)==n&&strspn(s,"0123456789abcdef")==n;}
static int rtoken(const char *s){size_t n=strlen(s);return n>0&&n<64&&strspn(s,"0123456789abcdef-capruns")==n&&strchr(s,'/')==NULL;}
static int rf_same(const lm_mirror_file *a,const lm_mirror_file *b){return lm_mirror_same_file(a,b)&&lm_mirror_same_bytes(a,b);}
const char *lr_original_target(lm_recovery *r){return r?r->target:NULL;}
int lr_open_attempted(lm_recovery *r){return r?r->attempted:0;}
#ifdef _WIN32
int lr_gate(lm_recovery **out,const char *exe,const char *cmd,const char *target,const char *pack,const char *font,int br,lm_cancel_fn cb,void *c,lm_err *e){(void)exe;(void)cmd;(void)target;(void)pack;(void)font;(void)br;(void)cb;(void)c;*out=NULL;return rr(NULL,e,"recovery-platform-unqualified");}
#define STUB(name,args) int name args{return rr(r,e,"recovery-platform-unqualified");}
STUB(lr_prepare,(lm_recovery *r,const lm_pack *p,int recover,lm_err *e))
STUB(lr_opening,(lm_recovery *r,lm_err *e))
STUB(lr_compare_restore,(lm_recovery *r,exr_library *owner,lm_err *e))
STUB(lr_publish,(lm_recovery *r,const void *p,size_t n,lm_err *e))
STUB(lr_ack,(lm_recovery *r,exr_status s,lm_err *e))
STUB(lr_complete,(lm_recovery *r,lm_err *e))
STUB(lr_read_view,(lm_recovery *r,char **p,lm_err *e))
STUB(lr_snapshot,(lm_recovery *r,const char *p,int h,uint64_t max,lm_mirror_file *f,char **b,size_t *n,lm_err *e))
STUB(lr_read,(lm_recovery *r,const char *p,char **b,size_t *n,size_t max,lm_err *e))
STUB(lr_write_new,(lm_recovery *r,const char *p,const void *b,size_t n,lm_err *e))
STUB(lr_pause,(lm_recovery *r,const char *p,lm_err *e))
#else
static double rn(void){struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))return -1;return t.tv_sec+t.tv_nsec/1e9;}
static void rid(const struct stat *s,char out[33]){snprintf(out,33,"%016llx%016llx",(unsigned long long)s->st_dev,(unsigned long long)s->st_ino);}
static int rdir(lm_recovery *r,const char *p,char id[33],int private,lm_err *e){struct stat s;if(lstat(p,&s)||!S_ISDIR(s.st_mode)||(s.st_uid!=geteuid()&&s.st_uid!=0)||(s.st_mode&(private?077:022)))return rr(r,e,"recovery-directory-custody");if(id)rid(&s,id);return 1;}
static int rrandom(char out[33],lm_err *e){int fd=open("/dev/urandom",O_RDONLY|O_CLOEXEC);unsigned char b[16];size_t n=0;int i;if(fd<0)return rr(NULL,e,"recovery-random-open");while(n<sizeof(b)){ssize_t k=read(fd,b+n,sizeof(b)-n);if(k<=0){close(fd);return rr(NULL,e,"recovery-random-read");}n+=(size_t)k;}if(close(fd))return rr(NULL,e,"recovery-random-close");for(i=0;i<16;i++)snprintf(out+i*2,3,"%02x",b[i]);return 1;}
int lr_snapshot(lm_recovery *r,const char *p,int hash,uint64_t max,lm_mirror_file *f,char **bytes,size_t *size,lm_err *e){
  struct stat before,opened,end,entry;int fd=-1;char id[33],got[65];lm_sha sha;lm_sb out;unsigned char b[8192];ssize_t n;uint64_t total=0;
  memset(f,0,sizeof(*f));if(bytes)*bytes=NULL;if(size)*size=0;lm_sb_init(&out);
  if(lstat(p,&before)){if(errno==ENOENT)return 1;return rr(r,e,"recovery-file-stat");}
  if(!S_ISREG(before.st_mode)||before.st_nlink!=1||before.st_size<0)return rr(r,e,"recovery-file-kind-or-alias");
  rid(&before,id);f->present=1;strcpy(f->identity,id);f->size=(uint64_t)before.st_size;
  if(!hash)return 1;
  if(r&&r->target_id[0]&&!strcmp(id,r->target_id))return rr(r,e,"recovery-input-target-alias");
  if(r&&r->owner_active&&!r->alias_race_seen){const char *enabled=getenv("EXR_MIGRATE_TEST_FAULTS"),*fault=getenv("EXR_RECOVERY_FAULT");
    if(enabled&&!strcmp(enabled,"1")&&fault&&!strcmp(fault,"snapshot-race")&&strstr(p,"/anchor.json")){r->alias_race_seen=1;if(!lr_pause(r,"snapshot-race",e))return 0;}}
  fd=open(p,O_RDONLY|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC);if(fd<0)return rr(r,e,"recovery-file-open");
  if(fstat(fd,&opened)){if(r)r->quarantined++;return rr(r,e,"recovery-unknown-fd-quarantined");}
  rid(&opened,id);if(r&&r->target_id[0]&&!strcmp(id,r->target_id)){r->quarantined++;
    {const char *enabled=getenv("EXR_MIGRATE_TEST_FAULTS"),*fault=getenv("EXR_RECOVERY_FAULT");
      /* Native stop is an observation channel only. Do not rescan/write an
       * already invalid evidence tree or close the quarantined target fd. */
      if(enabled&&!strcmp(enabled,"1")&&fault&&!strcmp(fault,"snapshot-race"))raise(SIGSTOP);}
    return rr(r,e,"recovery-target-fd-quarantined");}
  if(strcmp(id,f->identity)||!S_ISREG(opened.st_mode)||opened.st_nlink!=1||opened.st_size<0||(uint64_t)opened.st_size>max){rr(r,e,"recovery-opened-file-bound");goto bad;}
  lm_sha_init(&sha);
  while((n=read(fd,b,sizeof(b)))>0){if((uint64_t)n>max-total){rr(r,e,"recovery-read-bound");goto bad;}total+=(uint64_t)n;lm_sha_add(&sha,b,(size_t)n);if(bytes){lm_sb_add(&out,(const char*)b,(size_t)n);if(out.oom){rr(r,e,"recovery-read-allocation");goto bad;}}}
  if(n<0||total!=(uint64_t)opened.st_size){rr(r,e,"recovery-file-read");goto bad;}lm_sha_hex(&sha,f->sha);
  if(lseek(fd,0,SEEK_SET)<0){rr(r,e,"recovery-rehash-seek");goto bad;}lm_sha_init(&sha);total=0;
  while((n=read(fd,b,sizeof(b)))>0){if((uint64_t)n>max-total){rr(r,e,"recovery-rehash-bound");goto bad;}total+=(uint64_t)n;lm_sha_add(&sha,b,(size_t)n);}lm_sha_hex(&sha,got);
  if(n<0||total!=(uint64_t)opened.st_size||strcmp(got,f->sha)||fstat(fd,&end)||lstat(p,&entry)||opened.st_dev!=end.st_dev||opened.st_ino!=end.st_ino||opened.st_size!=end.st_size||opened.st_mtime!=end.st_mtime||opened.st_ctime!=end.st_ctime||entry.st_dev!=opened.st_dev||entry.st_ino!=opened.st_ino||entry.st_nlink!=1){rr(r,e,"recovery-file-changed");goto bad;}
  if(close(fd)){fd=-1;rr(r,e,"recovery-file-close");goto bad;}fd=-1;
  if(bytes){if(!out.p){out.p=malloc(1);if(!out.p)return rr(r,e,"recovery-empty-allocation");out.p[0]=0;}*bytes=out.p;if(size)*size=(size_t)total;out.p=NULL;}lm_sb_free(&out);return 1;
 bad:if(fd>=0)close(fd);lm_sb_free(&out);return 0;
}
int lr_read(lm_recovery *r,const char *p,char **b,size_t *n,size_t max,lm_err *e){lm_mirror_file f;if(!lr_snapshot(r,p,1,max,&f,b,n,e))return 0;if(!f.present)return rr(r,e,"recovery-file-missing");return 1;}
static int rsame(lm_recovery *r,const char *p,const lm_mirror_file *want,int hash,lm_err *e){lm_mirror_file got;if(!lr_snapshot(r,p,hash,R_LIMIT,&got,NULL,NULL,e))return 0;if(!lm_mirror_same_file(&got,want)||(hash&&!lm_mirror_same_bytes(&got,want)))return rr(r,e,"recovery-artifact-changed");return 1;}
static int rsyncdir(lm_recovery *r,const char *p,lm_err *e){int fd=open(p,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC),ok;if(fd<0)return rr(r,e,"recovery-parent-open");ok=fsync(fd)==0;if(close(fd))ok=0;return ok?1:rr(r,e,"recovery-parent-sync");}
static int rsyncfile(lm_recovery *r,const char *p,lm_err *e){int fd;struct stat s;char id[33];fd=open(p,O_RDONLY|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC);if(fd<0)return rr(r,e,"recovery-sync-open");if(fstat(fd,&s)){r->quarantined++;return rr(r,e,"recovery-sync-unknown-quarantined");}rid(&s,id);if(!strcmp(id,r->target_id)){r->quarantined++;return rr(r,e,"recovery-sync-target-quarantined");}if(!S_ISREG(s.st_mode)||s.st_nlink!=1){close(fd);return rr(r,e,"recovery-sync-kind");}if(fsync(fd)){close(fd);return rr(r,e,"recovery-file-sync");}if(close(fd))return rr(r,e,"recovery-sync-close");return 1;}
static int rinventory_walk(lm_recovery *r,const char *p,unsigned *names,unsigned depth,lm_err *e){DIR *d;struct dirent *entry;if(depth>3)return rr(r,e,"recovery-depth-bound");d=opendir(p);if(!d)return rr(r,e,"recovery-inventory-open");while((entry=readdir(d))){char q[4096];struct stat s;if(!strcmp(entry->d_name,".")||!strcmp(entry->d_name,".."))continue;if(++*names>R_NAMES||!rp(q,p,entry->d_name,r,e)||lstat(q,&s)){closedir(d);return rr(r,e,"recovery-name-bound-or-stat");}if(s.st_uid!=geteuid()||(s.st_mode&077)){closedir(d);return rr(r,e,"recovery-private-artifact");}if(S_ISDIR(s.st_mode)){if(!rinventory_walk(r,q,names,depth+1,e)){closedir(d);return 0;}}else if(S_ISREG(s.st_mode)&&s.st_nlink==1&&s.st_size>=0){char id[33];rid(&s,id);if(!strcmp(id,r->target_id)||(uint64_t)s.st_size>R_TOTAL-r->bytes||(uint64_t)s.st_blocks>R_TOTAL/512-r->blocks){closedir(d);return rr(r,e,"recovery-evidence-bound-or-target-alias");}r->bytes+=(uint64_t)s.st_size;r->blocks+=(uint64_t)s.st_blocks;}else{closedir(d);return rr(r,e,"recovery-special-evidence");}}
  if(closedir(d))return rr(r,e,"recovery-inventory-close");return 1;}
static int rinventory(lm_recovery *r,uint64_t reserve,lm_err *e){unsigned n=0;struct statvfs disk;r->bytes=r->blocks=0;if(!rinventory_walk(r,r->root,&n,0,e))return 0;if(reserve>R_TOTAL||r->bytes>R_TOTAL-reserve||r->blocks*512>R_TOTAL-reserve)return rr(r,e,"recovery-evidence-reservation");if(statvfs(r->root,&disk)||(uint64_t)disk.f_bavail<reserve/(disk.f_frsize?disk.f_frsize:1)+1)return rr(r,e,"recovery-free-space-reservation");r->reserved=reserve;return 1;}
int lr_write_new(lm_recovery *r,const char *p,const void *data,size_t n,lm_err *e){int fd;size_t off=0;char parent[4096],*slash;if(n>R_LIMIT)return rr(r,e,"recovery-write-bound");if(r&&r->root[0]&&lm_path_state(r->root)==1&&!rinventory(r,n,e))return 0;
  fd=open(p,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);if(fd<0)return rr(r,e,"recovery-exclusive-create");while(off<n){ssize_t k=write(fd,(const char*)data+off,n-off);if(k<=0){close(fd);return rr(r,e,"recovery-file-write");}off+=(size_t)k;}if(fsync(fd)){close(fd);return rr(r,e,"recovery-file-sync");}if(close(fd))return rr(r,e,"recovery-file-close");snprintf(parent,sizeof(parent),"%s",p);slash=strrchr(parent,'/');if(slash)*slash=0;else strcpy(parent,".");return rsyncdir(r,parent,e);}
static void rfile_json(lm_sb *b,const lm_mirror_file *f){lm_sb_fmt(b,"[%d,\"%s\",\"%s\",%llu]",f->present,f->identity,f->sha,(unsigned long long)f->size);}
static int rfile_parse(const jv *j,lm_mirror_file *f){uint64_t z;memset(f,0,sizeof(*f));if(!j||j->t!=J_ARR||j->n!=4||!lm_json_uint(j->items[0],&z)||z>1||j->items[1]->t!=J_STR||j->items[2]->t!=J_STR)return 0;f->present=(int)z;if((f->present&&(!hex(j->items[1]->s,32)||!hex(j->items[2]->s,64)))||(!f->present&&(j->items[1]->n||j->items[2]->n)))return 0;if(!lm_json_uint(j->items[3],&z)||z>R_LIMIT)return 0;strcpy(f->identity,j->items[1]->s);strcpy(f->sha,j->items[2]->s);f->size=z;return f->present||!z;}
static void rrecord_text(lm_recovery *r,const RRecord *x,lm_sb *b){
  lm_sb_fmt(b,"{\"magic\":\"%s\",\"ordinal\":%u,\"phase\":%u,\"generation\":%u,\"run\":\"%s\",\"previous\":\"%s\",\"self\":\"%s\",\"base_token\":\"%s\",\"pack\":\"%s\",\"target\":\"%s\",\"root\":\"%s\",\"parent\":\"%s\",\"baseline\":",R_MAGIC,x->ordinal,x->phase,x->generation,x->run,x->previous,x->self,x->base_token,x->pack,r->target_id,r->root_id,r->parent_id);rfile_json(b,&x->baseline);lm_sb_str(b,",\"before\":");rfile_json(b,&x->before);lm_sb_str(b,",\"after\":");rfile_json(b,&x->after);lm_sb_str(b,",\"preimage\":");rfile_json(b,&x->preimage);lm_sb_str(b,",\"plan\":");rfile_json(b,&x->plan);lm_sb_str(b,",\"pack_file\":");rfile_json(b,&x->pack_file);lm_sb_str(b,",\"lease\":");rfile_json(b,&r->lease_id);lm_sb_str(b,",\"barrier\":");rfile_json(b,&r->barrier_id);lm_sb_str(b,",\"worker\":");rfile_json(b,&r->worker_id);lm_sb_str(b,",\"font\":");rfile_json(b,&r->font_id);lm_sb_str(b,"}\n");
  {char seal[65];if(b->oom||!b->p||b->n<2||b->p[b->n-2]!='}'||b->p[b->n-1]!='\n'){b->oom=1;return;}lm_sha_bytes(b->p,b->n,seal);b->n-=2;b->p[b->n]=0;lm_sb_fmt(b,",\"seal\":\"%s\"}\n",seal);}
}
static int rrecord_write(lm_recovery *r,const char *p,RRecord *x,lm_mirror_file *id,int sync,lm_err *e){int fd;struct stat s;lm_sb b;size_t off=0;
  if(!rinventory(r,R_RECORD_BYTES,e))return 0;fd=open(p,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);if(fd<0)return rr(r,e,"recovery-record-create");if(fstat(fd,&s)){close(fd);return rr(r,e,"recovery-record-stat");}rid(&s,x->self);lm_sb_init(&b);rrecord_text(r,x,&b);
  if(b.oom||b.n>R_RECORD_BYTES){close(fd);lm_sb_free(&b);return rr(r,e,"recovery-record-bound");}
  while(off<b.n){ssize_t k=write(fd,b.p+off,b.n-off);if(k<=0){close(fd);lm_sb_free(&b);return rr(r,e,"recovery-record-write");}off+=(size_t)k;}
  if(sync&&fsync(fd)){close(fd);lm_sb_free(&b);return rr(r,e,"recovery-record-sync");}if(close(fd)){lm_sb_free(&b);return rr(r,e,"recovery-record-close");}lm_sb_free(&b);
  if(!lr_snapshot(r,p,1,R_RECORD_BYTES,id,NULL,NULL,e))return 0;return !sync||rsyncdir(r,r->root,e);
}
static int ruint(const jv *j,const char *key,unsigned *out,unsigned max){uint64_t n;if(!lm_json_uint(lm_get(j,key),&n)||n>max)return 0;*out=(unsigned)n;return 1;}
static int rstr(const jv *j,const char *key,char *out,size_t max){const jv *v=lm_get(j,key);if(!v||v->t!=J_STR||v->n>=max||strlen(v->s)!=v->n)return 0;memcpy(out,v->s,v->n+1);return 1;}
static int rrecord_read(lm_recovery *r,const char *p,RRecord *x,lm_mirror_file *id,int anchor,lm_err *e){char *raw=NULL,error[128],text[65],targetid[33],rootid[33],parentid[33];size_t n=0;jv *j=NULL;lm_sb expected;lm_mirror_file lease,barrier,worker,font;int ok=0;memset(x,0,sizeof(*x));lm_sb_init(&expected);
  if(!lr_snapshot(r,p,1,R_RECORD_BYTES,id,&raw,&n,e)||!id->present)goto done;j=lm_json_parse(raw,n,error,sizeof(error));
  if(!j||j->t!=J_OBJ||j->n!=23||!rstr(j,"magic",text,sizeof(text))||strcmp(text,R_MAGIC)||!ruint(j,"ordinal",&x->ordinal,R_RECORDS)||!ruint(j,"phase",&x->phase,RP_RESTORED)||!ruint(j,"generation",&x->generation,R_RECORDS)||!rstr(j,"run",x->run,sizeof(x->run))||!hex(x->run,32)||!rstr(j,"previous",x->previous,sizeof(x->previous))||(!anchor&&!hex(x->previous,64))||!rstr(j,"self",x->self,sizeof(x->self))||strcmp(x->self,id->identity)||!rstr(j,"base_token",x->base_token,sizeof(x->base_token))||(!anchor&&!rtoken(x->base_token))||!rstr(j,"pack",x->pack,sizeof(x->pack))||!hex(x->pack,64)||!rstr(j,"target",targetid,sizeof(targetid))||strcmp(targetid,r->target_id)||!rstr(j,"root",rootid,sizeof(rootid))||strcmp(rootid,r->root_id)||!rstr(j,"parent",parentid,sizeof(parentid))||strcmp(parentid,r->parent_id)||!rfile_parse(lm_get(j,"baseline"),&x->baseline)||!rfile_parse(lm_get(j,"before"),&x->before)||!rfile_parse(lm_get(j,"after"),&x->after)||!rfile_parse(lm_get(j,"preimage"),&x->preimage)||!rfile_parse(lm_get(j,"plan"),&x->plan)||!rfile_parse(lm_get(j,"pack_file"),&x->pack_file)||!rfile_parse(lm_get(j,"lease"),&lease)||!rfile_parse(lm_get(j,"barrier"),&barrier)||!rfile_parse(lm_get(j,"worker"),&worker)||!rfile_parse(lm_get(j,"font"),&font)){rr(r,e,"recovery-record-format");goto done;}
  if(anchor){r->lease_id=lease;r->barrier_id=barrier;r->worker_id=worker;r->font_id=font;}
  else if(!rf_same(&lease,&r->lease_id)||!rf_same(&barrier,&r->barrier_id)||!rf_same(&worker,&r->worker_id)||!rf_same(&font,&r->font_id)){rr(r,e,"recovery-record-input-binding");goto done;}
  rrecord_text(r,x,&expected);if(expected.oom||expected.n!=n||memcmp(expected.p,raw,n)){rr(r,e,"recovery-record-canonical-bytes");goto done;}ok=1;
 done:lm_json_free(j);free(raw);lm_sb_free(&expected);if(!ok&&!r->failed)rr(r,e,"recovery-record-missing");return ok;
}
static int rname(lm_recovery *r,char p[4096],unsigned n,lm_err *e){char name[40];snprintf(name,sizeof(name),"record-%02u.json",n);return rp(p,r->root,name,r,e);}
static int rguard(lm_recovery *r,lm_err *e){char id[33],p[4096];lm_mirror_file target,absent;struct stat s;
  if(!rdir(r,r->root,id,1,e)||strcmp(id,r->root_id)||!rdir(r,r->parent,id,0,e)||strcmp(id,r->parent_id)||!lr_snapshot(r,r->target,0,0,&target,NULL,NULL,e)||!target.present||strcmp(target.identity,r->target_id))return rr(r,e,"recovery-target-or-directory-changed");
  if(!lr_snapshot(r,r->pending,0,0,&absent,NULL,NULL,e)||absent.present)return rr(r,e,"recovery-foreign-legacy-intent");
  if(!rsame(r,r->worker,&r->worker_id,1,e))return 0;
  if(r->pack_input.present&&!rsame(r,r->pack_path,&r->pack_input,1,e))return 0;
  if(r->read_only==2){struct stat policy;
    if(lstat(r->policy_root,&policy)==0||errno!=ENOENT){r->root_seen=1;return rr(r,e,"recovery-policy-appeared-during-read");}
    if(lstat(r->barrier,&policy)==0||errno!=ENOENT)return rr(r,e,"recovery-barrier-appeared-during-read");
    if(r->font_id.present&&!rsame(r,r->font,&r->font_id,1,e))return 0;return rinventory(r,0,e);}
  if(!rsame(r,r->barrier,&r->barrier_id,1,e))return 0;
  if(r->font_id.present&&!rsame(r,r->font,&r->font_id,1,e))return 0;
  if(!rp(p,r->root,"lease",r,e)||!rsame(r,p,&r->lease_id,1,e)||fstat(r->lease,&s))return rr(r,e,"recovery-lease-changed");rid(&s,id);if(strcmp(id,r->lease_id.identity))return rr(r,e,"recovery-lease-fd-changed");return rinventory(r,0,e);
}
static int rimmutable(lm_recovery *r,const char *path,const lm_mirror_file *want,uint64_t *bytes,lm_err *e){
  lm_mirror_file got;
  if(want->size>R_LIMIT||want->size>R_TOTAL-*bytes)return rr(r,e,"recovery-immutable-read-bound");
  *bytes+=want->size;
  /* Reuse actual-fd target-alias quarantine. Do not introduce a raw descriptor
   * close under the SDK writer. Bound both passes by the recorded byte size. */
  if(!lr_snapshot(r,path,1,want->size,&got,NULL,NULL,e))return 0;
  if(!rf_same(&got,want))return rr(r,e,"recovery-artifact-changed");
  return 1;
}
static int ractive_evidence(lm_recovery *r,lm_err *e){
  char directory[4096],path[4096],name[96];const RRecord *base=&r->base;
  const RRecord *plans[R_RECORDS];unsigned i,j,plans_n=0;uint64_t bytes=0;
  if(!r->count)return 1; /* An anchor before first BASE has no admitted files. */
  if(!base->baseline.present||!base->pack_file.present||strcmp(base->pack_file.sha,base->pack)||
     base->preimage.present!=base->before.present||
     (base->preimage.present&&!lm_mirror_same_bytes(&base->preimage,&base->before)))return rr(r,e,"recovery-base-evidence-binding");
  if(!rtoken(base->base_token)||!rp(directory,r->root,base->base_token,r,e)||!rp(path,directory,"baseline.bin",r,e)||
     !rimmutable(r,path,&base->baseline,&bytes,e))return 0;
  snprintf(name,sizeof(name),"pack-%s.bin",base->run);
  if(!rp(path,r->root,name,r,e)||!rimmutable(r,path,&base->pack_file,&bytes,e))return 0;
  snprintf(name,sizeof(name),"before-%s.bin",base->run);
  if(!rp(path,r->root,name,r,e)||!rimmutable(r,path,&base->preimage,&bytes,e))return 0;
  /* Plan filenames belong to their original PREP producer. Later OPENING or
   * RESTORE records may carry that descriptor with a different invocation run.
   * Work/restore files are intentionally excluded: publication consumes them. */
  for(i=0;i<r->count;i++){
    const RRecord *x=&r->records[i];
    if(x->generation!=r->generation||x->phase!=RP_PREP)continue;
    if(!x->plan.present||!x->after.present||!lm_mirror_same_bytes(&x->plan,&x->after))return rr(r,e,"recovery-plan-byte-binding");
    for(j=0;j<plans_n;j++)if(!strcmp(plans[j]->run,x->run))break;
    if(j<plans_n){if(!rf_same(&plans[j]->plan,&x->plan))return rr(r,e,"recovery-plan-run-rebound");continue;}
    plans[plans_n++]=x;snprintf(name,sizeof(name),"plan-%s.bin",x->run);
    if(!rp(path,r->root,name,r,e)||!rimmutable(r,path,&x->plan,&bytes,e))return 0;
  }
  return 1;
}
/* Canonical append graph. A record is never accepted merely because its hash is
 * present: every edge, generation and immutable baseline binding is checked. */
static int rchain(lm_recovery *r,lm_err *e){
  char p[4096];RRecord anchor,previous={0},base={0};lm_mirror_file id;unsigned i,seen=0;int gap=0;
  if(!rp(p,r->root,"anchor.json",r,e)||!rrecord_read(r,p,&anchor,&id,1,e))return 0;
  if(anchor.phase!=RP_ANCHOR||anchor.ordinal||anchor.generation||anchor.previous[0]||anchor.base_token[0])return rr(r,e,"recovery-anchor-shape");
  if(r->anchor_id.present&&!rf_same(&id,&r->anchor_id))return rr(r,e,"recovery-anchor-changed");r->anchor_id=id;r->anchor=anchor;
  for(i=0;i<R_RECORDS;i++){
    RRecord x;lm_mirror_file f;unsigned pp=seen?previous.phase:RP_ANCHOR;int edge=0;
    if(!rname(r,p,i,e)||!lr_snapshot(r,p,1,R_RECORD_BYTES,&f,NULL,NULL,e))return 0;
    if(!f.present){gap=1;continue;}if(gap)return rr(r,e,"recovery-record-gap");
    if(!rrecord_read(r,p,&x,&f,0,e)||x.ordinal!=i||strcmp(x.previous,seen?r->record_ids[i-1].sha:r->anchor_id.sha))return rr(r,e,"recovery-record-chain");
    if(i<r->count&&!rf_same(&f,&r->record_ids[i]))return rr(r,e,"recovery-record-replaced");
    if(x.phase==RP_BASE){edge=!seen&&x.generation==1&&rf_same(&x.before,&anchor.before)&&!strcmp(x.pack,anchor.pack);base=x;}
    else if(x.phase==RP_FRESH){edge=pp==RP_ACK&&x.generation==previous.generation+1;base=x;}
    else {
      if(x.generation!=base.generation||strcmp(x.base_token,base.base_token)||strcmp(x.pack,base.pack)||!rf_same(&x.baseline,&base.baseline)||!rf_same(&x.preimage,&base.preimage)||!rf_same(&x.pack_file,&base.pack_file))return rr(r,e,"recovery-generation-binding");
      switch(x.phase){
      case RP_OPENING:edge=pp==RP_BASE||pp==RP_FRESH||pp==RP_OPENING||pp==RP_PREP||pp==RP_MIRROR||pp==RP_RESTORE_PREP||pp==RP_RESTORED;break;
      case RP_PREP:edge=pp==RP_OPENING||pp==RP_RESTORED;break;
      case RP_MIRROR:edge=pp==RP_PREP&&rf_same(&x.after,&previous.after)&&rf_same(&x.plan,&previous.plan);break;
      case RP_ACK:edge=pp==RP_MIRROR&&rf_same(&x.after,&previous.after)&&rf_same(&x.plan,&previous.plan);break;
      case RP_RESTORE_PREP:edge=pp==RP_OPENING;break;
      case RP_RESTORED:edge=pp==RP_RESTORE_PREP&&rf_same(&x.after,&previous.after);break;
      default:break;
      }
    }
    if(!edge||!x.baseline.present||!x.pack_file.present)return rr(r,e,"recovery-record-edge");r->records[i]=x;r->record_ids[i]=f;previous=x;seen++;
  }
  if(seen<r->count)return rr(r,e,"recovery-record-removed");
  {DIR *d=opendir(r->root);struct dirent *v;if(!d)return rr(r,e,"recovery-root-read");while((v=readdir(d))){unsigned n;char tail;if(!strncmp(v->d_name,"record-",7)&&(sscanf(v->d_name,"record-%u.json%c",&n,&tail)!=1||n>=R_RECORDS||strlen(v->d_name)!=14)){closedir(d);return rr(r,e,"recovery-foreign-record");}}closedir(d);}
  r->count=seen;r->base=base;r->generation=base.generation;return rguard(r,e)&&ractive_evidence(r,e);
}
static int rappend(lm_recovery *r,RRecord *x,int sync,lm_err *e){char p[4096];lm_mirror_file id;if(r->count>=R_RECORDS||r->attempt_records>=R_RESERVE)return rr(r,e,"recovery-record-capacity");if(!rchain(r,e))return 0;x->ordinal=r->count;strcpy(x->run,r->nonce);strcpy(x->previous,r->count?r->record_ids[r->count-1].sha:r->anchor_id.sha);if(!rname(r,p,r->count,e)||!rrecord_write(r,p,x,&id,sync,e))return 0;r->records[r->count]=*x;r->record_ids[r->count++]=id;r->attempt_records++;return rchain(r,e);}
static int rlease(lm_recovery *r,int create,lm_err *e){char p[4096],id[33];struct stat s;lm_mirror_file before;if(!rp(p,r->root,"lease",r,e))return 0;if(create&&!lr_write_new(r,p,r->nonce,32,e))return 0;if(!lr_snapshot(r,p,1,32,&before,NULL,NULL,e)||!before.present)return rr(r,e,"recovery-lease-missing");if(r->lease_id.present&&!rf_same(&before,&r->lease_id))return rr(r,e,"recovery-lease-replaced");r->lease=open(p,O_RDWR|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC);if(r->lease<0)return rr(r,e,"recovery-lease-open");if(fstat(r->lease,&s)){r->quarantined++;return rr(r,e,"recovery-lease-unknown-fd");}rid(&s,id);if(!strcmp(id,r->target_id)){r->quarantined++;return rr(r,e,"recovery-lease-target-fd");}if(strcmp(id,before.identity)||!S_ISREG(s.st_mode)||s.st_nlink!=1)return rr(r,e,"recovery-lease-fd-identity");if(flock(r->lease,LOCK_EX|LOCK_NB))return rr(r,e,"recovery-lease-busy");r->lease_id=before;return rsame(r,p,&before,1,e);/* lease intentionally retained through process exit */}
static int rtest(const char *name){const char *a=getenv("EXR_MIGRATE_TEST_FAULTS"),*b=getenv("EXR_RECOVERY_FAULT");return a&&!strcmp(a,"1")&&b&&!strcmp(b,name);}
static int rphase_selected(const char *list,const char *phase){size_t n=strlen(phase);const char *p=list;if(!p)return 0;while(*p){const char *end=strchr(p,',');size_t size=end?(size_t)(end-p):strlen(p);if(size==n&&!memcmp(p,phase,n))return 1;if(!end)break;p=end+1;}return 0;}
int lr_pause(lm_recovery *r,const char *phase,lm_err *e){const char *g=getenv("EXR_MIGRATE_TEST_FAULTS"),*v=getenv("EXR_RECOVERY_PAUSE");char p[4096],name[96];double start;snprintf(r->phase,sizeof(r->phase),"%s",phase);if(r->cancelled&&r->cancelled(r->context))return rr(r,e,"cancelled");if(!g||strcmp(g,"1")||!rphase_selected(v,phase))return 1;
  snprintf(name,sizeof(name),"%s.ready",phase);if(!rp(p,r->run_dir,name,r,e)||!lr_write_new(r,p,r->nonce,32,e))return 0;start=rn();if(start<0)return rr(r,e,"recovery-clock");
  snprintf(name,sizeof(name),"%s.go",phase);if(!rp(p,r->run_dir,name,r,e))return 0;
  while(rn()-start<30){struct timespec delay={0,10000000};lm_mirror_file f;char *b=NULL;size_t n=0;if(r->cancelled&&r->cancelled(r->context))return rr(r,e,"cancelled");if(!lr_snapshot(r,p,1,9,&f,&b,&n,e))return 0;if(f.present){int ok=n==9&&!memcmp(b,"continue\n",9);free(b);return ok?1:rr(r,e,"recovery-rendezvous-token");}free(b);nanosleep(&delay,NULL);}return rr(r,e,"recovery-rendezvous-deadline");}
static int rrun_dir(lm_recovery *r,lm_err *e){char name[64];snprintf(name,sizeof(name),"run-%s",r->nonce);if(!rp(r->run_dir,r->root,name,r,e)||mkdir(r->run_dir,0700))return rr(r,e,"recovery-run-create");return rsyncdir(r,r->root,e);}
static int rworker_path(lm_recovery *r,const char *exe,lm_err *e){char self[4096],resolved[4096],*slash;(void)exe;
#ifdef __APPLE__
  uint32_t n=sizeof(self);if(_NSGetExecutablePath(self,&n))return rr(r,e,"recovery-executable-path");
#else
  ssize_t n=readlink("/proc/self/exe",self,sizeof(self)-1);if(n<0||(size_t)n>=sizeof(self)-1)return rr(r,e,"recovery-executable-path");self[n]=0;
#endif
  if(!realpath(self,resolved)||(slash=strrchr(resolved,'/'))==NULL)return rr(r,e,"recovery-executable-resolve");*slash=0;return rp(r->worker,resolved,"exreader-migration-recovery-worker",r,e);}
int lr_gate(lm_recovery **out,const char *exe,const char *cmd,const char *target,const char *pack,const char *font,int br,lm_cancel_fn cb,void *context,lm_err *e){
  lm_recovery *r=calloc(1,sizeof(*r));struct stat s;char *slash,initial[33];*out=r;if(!r)return rr(NULL,e,"recovery-allocation");r->lease=-1;r->commit_status=-1;r->rollback_status=-1;r->cancelled=cb;r->context=context;
  if(!target||!target[0]||!strncmp(target,"file:",5)||strchr(target,'?'))return rr(r,e,"recovery-existing-target-required");if(lstat(target,&s)||!S_ISREG(s.st_mode)||s.st_nlink!=1||s.st_uid!=geteuid())return rr(r,e,"recovery-existing-regular-owned-target-required");rid(&s,initial);
  if(!realpath(target,r->target)||strlen(r->target)>3500)return rr(r,e,"recovery-target-path");strcpy(r->parent,r->target);slash=strrchr(r->parent,'/');if(!slash)return rr(r,e,"recovery-target-parent");if(slash==r->parent)slash[1]=0;else *slash=0;
  if(!rdir(r,r->parent,r->parent_id,0,e))return 0;
  {struct statfs fs;if(statfs(r->parent,&fs))return rr(r,e,"recovery-filesystem-stat");
#ifdef __APPLE__
  if(strcmp(fs.f_fstypename,"apfs"))return rr(r,e,"recovery-filesystem-unqualified");
#else
  if((unsigned long)fs.f_type!=0xef53ul)return rr(r,e,"recovery-filesystem-unqualified");
#endif
  }
  snprintf(r->root,sizeof(r->root),"%s.migration-recovery",r->target);snprintf(r->barrier,sizeof(r->barrier),"%s.migrate-lock",r->target);snprintf(r->pending,sizeof(r->pending),"%s.migration-pending.json",r->target);
  strcpy(r->policy_root,r->root);if(lstat(r->root,&s)==0||errno!=ENOENT)r->root_seen=1;
  if(br)return rr(r,e,"recovery-break-lock-unsupported");if(lstat(r->pending,&s)==0||errno!=ENOENT)return rr(r,e,"recovery-legacy-intent-unqualified");if(!strcmp(cmd,"recover-mirror"))return rr(r,e,"recovery-explicit-pack-required");if(!strcmp(cmd,"inspect"))return rr(r,e,"recovery-inspect-target-unsupported");
  if(pack&&(!realpath(pack,r->pack_path)||strlen(r->pack_path)>3500))return rr(r,e,"recovery-pack-path");if(font){if(!realpath(font,r->font)||strlen(r->font)>3500)return rr(r,e,"recovery-font-path");}else strcpy(r->font,"-");
  if(!rrandom(r->nonce,e)||!rworker_path(r,exe,e)||!lr_snapshot(r,r->target,0,0,&r->target_before,NULL,NULL,e)||!r->target_before.present||strcmp(initial,r->target_before.identity))return rr(r,e,"recovery-target-gate-changed");strcpy(r->target_id,initial);return 1;
}
static int rmirror(lm_recovery *r,char p[4096],lm_err *e){if(snprintf(p,4096,"%s.legacy-map.json",r->target)>=4096)return rr(r,e,"recovery-mirror-path");return 1;}
static int rinit(lm_recovery *r,lm_err *e){struct stat s;char p[4096];RRecord x={0};
  if(lstat(r->barrier,&s)==0||errno!=ENOENT)return rr(r,e,"recovery-existing-barrier");if(mkdir(r->root,0700))return rr(r,e,"recovery-anchor-root-create");r->new_root=1;r->root_seen=1;if(!rdir(r,r->root,r->root_id,1,e)||!rlease(r,1,e))return 0;
  if(!lr_snapshot(r,r->worker,1,R_LIMIT,&r->worker_id,NULL,NULL,e)||!r->worker_id.present)return rr(r,e,"recovery-worker-missing");if(strcmp(r->font,"-")&&(!lr_snapshot(r,r->font,1,R_LIMIT,&r->font_id,NULL,NULL,e)||!r->font_id.present))return rr(r,e,"recovery-font-missing");
  if(!lr_write_new(r,r->barrier,r->nonce,32,e)||!lr_snapshot(r,r->barrier,1,32,&r->barrier_id,NULL,NULL,e))return 0;strcpy(x.run,r->nonce);strcpy(x.pack,r->pack_sha);if(!rmirror(r,p,e)||!lr_snapshot(r,p,1,R_LIMIT,&x.before,NULL,NULL,e))return 0;
  if(!rp(p,r->root,"anchor.json",r,e)||!rrecord_write(r,p,&x,&r->anchor_id,0,e)||!rrun_dir(r,e)||!lr_pause(r,"S1-anchor-before-sync",e)||!rsyncfile(r,p,e)||!rsyncdir(r,r->root,e)||!rsyncdir(r,r->parent,e))return 0;return rchain(r,e);
}
static int rload(lm_recovery *r,lm_err *e){char p[4096];RRecord x;unsigned i;r->root_seen=1;if(!rdir(r,r->root,r->root_id,1,e)||!rp(p,r->root,"anchor.json",r,e)||!rrecord_read(r,p,&x,&r->anchor_id,1,e)||!rlease(r,0,e)||!rchain(r,e))return 0;
  if(!rsyncfile(r,p,e))return 0;for(i=0;i<r->count;i++)if(!rname(r,p,i,e)||!rsyncfile(r,p,e))return 0;if(!rsyncdir(r,r->root,e)||!rsyncdir(r,r->parent,e)||!rrun_dir(r,e))return 0;return rchain(r,e);
}
static int rpipe(int p[2]){if(pipe(p))return 0;if(fcntl(p[0],F_SETFD,FD_CLOEXEC)||fcntl(p[1],F_SETFD,FD_CLOEXEC)||fcntl(p[0],F_SETFL,O_NONBLOCK)){close(p[0]);close(p[1]);p[0]=p[1]=-1;return 0;}return 1;}
static int rdrain(lm_recovery *r,int fd,int log,uint64_t *total,int *eof,lm_err *e){char b[4096];ssize_t n;while((n=read(fd,b,sizeof(b)))>0){size_t off=0;if((uint64_t)n>65536-*total)return rr(r,e,"recovery-worker-log-bound");*total+=(uint64_t)n;while(off<(size_t)n){ssize_t k=write(log,b+off,(size_t)n-off);if(k<=0)return rr(r,e,"recovery-worker-log-write");off+=(size_t)k;}}if(!n)*eof=1;else if(errno!=EAGAIN&&errno!=EWOULDBLOCK&&errno!=EINTR)return rr(r,e,"recovery-worker-pipe-read");return 1;}
static int rscan(lm_recovery *r,int capture,char token[64],lm_mirror_file *baseline,lm_err *e){
  char dir[4096],request[4096],report[4096],errors[4096],dest[4096],pidpath[4096],id[33],report_nonce[33],reported_sha[65],reported_id[33],reported_mode[16],msg[128],log_id[2][33];
  lm_sb envelope;lm_mirror_file request_id;int pipes[2][2]={{-1,-1},{-1,-1}},logs[2]={-1,-1},eof[2]={0,0},status=0,reaped=0,spawned=0,ok=0;pid_t pid=-1;uint64_t bytes=0;double start=0;char *raw=NULL;size_t n=0;jv *j=NULL;posix_spawn_file_actions_t actions;posix_spawnattr_t attr;int have_actions=0,have_attr=0;char actual_nonce[33];
  memset(baseline,0,sizeof(*baseline));lm_sb_init(&envelope);if(++r->scan_serial>99||!rinventory(r,(capture?6:3)*R_LIMIT+4u*1048576,e))goto done;
  snprintf(token,64,"%s-%s-%02u",capture?"cap":"scan",r->nonce,r->scan_serial);if(!rp(dir,r->root,token,r,e)||mkdir(dir,0700)||!rsyncdir(r,r->root,e)||!rdir(r,dir,id,1,e)){rr(r,e,"recovery-worker-root");goto done;}
  lm_sb_str(&envelope,"{\"nonce\":");lm_sb_json(&envelope,r->nonce,strlen(r->nonce));lm_sb_str(&envelope,",\"worker_sha\":");lm_sb_json(&envelope,r->worker_id.sha,strlen(r->worker_id.sha));lm_sb_str(&envelope,",\"target_identity\":");lm_sb_json(&envelope,r->target_id,strlen(r->target_id));lm_sb_str(&envelope,",\"output_identity\":");lm_sb_json(&envelope,id,strlen(id));lm_sb_str(&envelope,",\"mode\":");lm_sb_json(&envelope,capture?"capture":"scan",capture?7:4);lm_sb_str(&envelope,",\"target\":");lm_sb_json(&envelope,r->target,strlen(r->target));lm_sb_str(&envelope,",\"font\":");lm_sb_json(&envelope,r->font,strlen(r->font));lm_sb_str(&envelope,"}\n");
  if(envelope.oom||!rp(request,dir,"request.json",r,e)||!lr_write_new(r,request,envelope.p,envelope.n,e)||!lr_snapshot(r,request,1,R_RECORD_BYTES,&request_id,NULL,NULL,e)||!lr_pause(r,capture?"worker-request":"owner-worker-request",e)||!rguard(r,e)||!rsame(r,request,&request_id,1,e))goto done;
  snprintf(msg,sizeof(msg),"worker-%02u.stdout",r->scan_serial);if(!rp(report,r->run_dir,msg,r,e))goto done;snprintf(msg,sizeof(msg),"worker-%02u.stderr",r->scan_serial);if(!rp(errors,r->run_dir,msg,r,e))goto done;
  logs[0]=open(report,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);logs[1]=open(errors,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);if(logs[0]<0||logs[1]<0||!rpipe(pipes[0])||!rpipe(pipes[1])){rr(r,e,"recovery-worker-transport");goto done;}
  {int k;struct stat st;for(k=0;k<2;k++){if(fstat(logs[k],&st)){rr(r,e,"recovery-log-fd-stat");goto done;}rid(&st,log_id[k]);}}
  if(posix_spawn_file_actions_init(&actions)){rr(r,e,"recovery-spawn-actions");goto done;}have_actions=1;if(posix_spawnattr_init(&attr)){rr(r,e,"recovery-spawn-attributes");goto done;}have_attr=1;
  if(posix_spawn_file_actions_addopen(&actions,0,"/dev/null",O_RDONLY,0)||posix_spawn_file_actions_adddup2(&actions,pipes[0][1],1)||posix_spawn_file_actions_adddup2(&actions,pipes[1][1],2)){rr(r,e,"recovery-spawn-stdio");goto done;}
#ifdef __APPLE__
  if(posix_spawnattr_setflags(&attr,POSIX_SPAWN_CLOEXEC_DEFAULT)){rr(r,e,"recovery-spawn-close-default");goto done;}
#else
  if(posix_spawn_file_actions_addclosefrom_np(&actions,3)){rr(r,e,"recovery-spawn-closefrom");goto done;}
#endif
  strcpy(actual_nonce,r->nonce);if(rtest("wrong-nonce")||(!capture&&rtest("owner-wrong-nonce")))actual_nonce[0]=actual_nonce[0]=='a'?'b':'a';
  {char *argv[]={r->worker,capture?"capture":"scan",r->target,dir,actual_nonce,r->font,"none",NULL};int rc=posix_spawn(&pid,r->worker,&actions,&attr,argv,environ);if(rc){errno=rc;rr(r,e,"recovery-worker-spawn");goto done;}}spawned=1;close(pipes[0][1]);pipes[0][1]=-1;close(pipes[1][1]);pipes[1][1]=-1;
  snprintf(msg,sizeof(msg),"worker-%02u.pid",r->scan_serial);if(!rp(pidpath,r->run_dir,msg,r,e))goto done;snprintf(msg,sizeof(msg),"%ld\n",(long)pid);if(!lr_write_new(r,pidpath,msg,strlen(msg),e))goto done;
  if((capture&&rtest("stop-worker"))||(!capture&&(rtest("owner-stop-worker")||rtest("owner-timeout")))){if(kill(pid,SIGSTOP)||waitpid(pid,&status,WUNTRACED)!=pid||!WIFSTOPPED(status)){rr(r,e,"recovery-worker-stop-calibration");goto done;}if(!lr_pause(r,"worker-stopped",e))goto done;if(!rtest("owner-timeout")&&kill(pid,SIGCONT))goto done;}
  if((rtest("kill-worker")||(!capture&&rtest("owner-kill-worker")))&&kill(pid,SIGKILL)){rr(r,e,"recovery-worker-kill-control");goto done;}
  start=rn();while(!reaped||!eof[0]||!eof[1]){struct timespec delay={0,10000000};pid_t got;
    if(!rdrain(r,pipes[0][0],logs[0],&bytes,&eof[0],e)||!rdrain(r,pipes[1][0],logs[1],&bytes,&eof[1],e))goto done;
    if(!reaped){got=waitpid(pid,&status,WNOHANG);if(got==pid)reaped=1;else if(got<0&&errno!=EINTR){rr(r,e,"recovery-worker-wait");goto done;}}
    if(start<0||rn()-start>30){rr(r,e,"recovery-worker-deadline");goto done;}if(r->cancelled&&r->cancelled(r->context)){rr(r,e,"cancelled");goto done;}if(!reaped||!eof[0]||!eof[1])nanosleep(&delay,NULL);
  }
  if(fsync(logs[0])||fsync(logs[1])){rr(r,e,"recovery-worker-log-sync");goto done;}
  {lm_mirror_file transport;if(!lr_snapshot(r,report,1,65536,&transport,&raw,&n,e)||!transport.present||strcmp(transport.identity,log_id[0])){rr(r,e,"recovery-worker-stdout-identity");goto done;}}
j=lm_json_parse(raw,n,msg,sizeof(msg));
  if(j&&j->t==J_OBJ)rstr(j,"reason",r->worker_reason,sizeof(r->worker_reason));
  {const jv *passed=lm_get(j,"passed"),*found=lm_get(j,"ledger_found");if(!WIFEXITED(status)||WEXITSTATUS(status)||!j||j->t!=J_OBJ||!passed||passed->t!=J_BOOL||!passed->b||!found||found->t!=J_BOOL||!rstr(j,"mode",reported_mode,sizeof(reported_mode))||strcmp(reported_mode,capture?"capture":"scan")||!rstr(j,"nonce",report_nonce,sizeof(report_nonce))||strcmp(report_nonce,r->nonce)||!rstr(j,"target_identity",reported_id,sizeof(reported_id))||strcmp(reported_id,r->target_id)||!rstr(j,"baseline_sha256",reported_sha,sizeof(reported_sha))||!hex(reported_sha,64)){rr(r,e,"recovery-worker-result-refused");goto done;}r->ledger_found=found->b;}
  if(!lr_pause(r,capture?"worker-result":"owner-worker-result",e)||!rp(dest,dir,"baseline.bin",r,e)||!lr_snapshot(r,dest,1,R_LIMIT,baseline,NULL,NULL,e)||!baseline->present||strcmp(baseline->sha,reported_sha)||!rsame(r,request,&request_id,1,e)||!rdir(r,dir,reported_id,1,e)||strcmp(id,reported_id)||!rguard(r,e)){rr(r,e,"recovery-worker-output-binding");goto done;}
  {lm_mirror_file transport;char digest[65];lm_sha_bytes(raw,n,digest);if(!lr_snapshot(r,report,1,65536,&transport,NULL,NULL,e)||!transport.present||strcmp(transport.identity,log_id[0])||strcmp(transport.sha,digest)){rr(r,e,"recovery-worker-stdout-changed");goto done;}}ok=1;
 done:
  if(spawned&&!reaped){kill(pid,SIGKILL);while(waitpid(pid,&status,0)<0&&errno==EINTR){}reaped=1;}
  if(have_actions)posix_spawn_file_actions_destroy(&actions);if(have_attr)posix_spawnattr_destroy(&attr);
  {int i,k;for(i=0;i<2;i++){for(k=0;k<2;k++)if(pipes[i][k]>=0)close(pipes[i][k]);if(logs[i]>=0){if(fsync(logs[i]))rr(r,e,"recovery-worker-log-final-sync");if(close(logs[i]))rr(r,e,"recovery-worker-log-final-close");}}}
  lm_json_free(j);free(raw);lm_sb_free(&envelope);if(!ok&&!r->failed)rr(r,e,"recovery-worker-incomplete");return ok&&!r->failed;
}
static int rartifact(lm_recovery *r,char p[4096],const char *kind,const char *run,lm_err *e){char name[96];if(!hex(run,32))return rr(r,e,"recovery-artifact-run");snprintf(name,sizeof(name),"%s-%s.bin",kind,run);return rp(p,r->root,name,r,e);}
static int rbaseline_path(lm_recovery *r,char p[4096],const RRecord *x,lm_err *e){char d[4096];if(!rtoken(x->base_token)||!rp(d,r->root,x->base_token,r,e))return 0;return rp(p,d,"baseline.bin",r,e);}
static int rcopy(lm_recovery *r,const char *source,const lm_mirror_file *want,const char *dest,lm_mirror_file *made,lm_err *e){char *data=NULL;size_t n=0;lm_mirror_file got;int ok=0;if(!lr_snapshot(r,source,1,R_LIMIT,&got,&data,&n,e)||!rf_same(&got,want)||!got.present){rr(r,e,"recovery-copy-source-changed");goto done;}if(!lr_write_new(r,dest,data,n,e)||!lr_snapshot(r,dest,1,R_LIMIT,made,NULL,NULL,e)||!made->present||!lm_mirror_same_bytes(made,want)){rr(r,e,"recovery-copy-result");goto done;}ok=1;done:free(data);return ok;}
static int requal(lm_recovery *r,const char *a,const lm_mirror_file *want,const char *b,const lm_mirror_file *other,lm_err *e){char *x=NULL,*y=NULL;size_t nx=0,ny=0;lm_mirror_file fx,fy;int ok=0;if(!lr_snapshot(r,a,1,R_LIMIT,&fx,&x,&nx,e)||!rf_same(&fx,want)||!lr_snapshot(r,b,1,R_LIMIT,&fy,&y,&ny,e)||!rf_same(&fy,other)||!fx.present||!fy.present||nx!=ny||memcmp(x,y,nx))rr(r,e,"recovery-full-baseline-parity-mismatch");else ok=1;free(x);free(y);return ok;}
static const RRecord *rlast_mirror(lm_recovery *r){unsigned i=r->count;while(i){const RRecord *x=&r->records[--i];if(x->generation!=r->generation)break;if(x->phase!=RP_OPENING)return x;}return &r->base;}
static int rcurrent(lm_recovery *r,lm_mirror_file *expected,lm_err *e){const RRecord *x=rlast_mirror(r);char p[4096];lm_mirror_file now;if(!rmirror(r,p,e)||!lr_snapshot(r,p,1,R_LIMIT,&now,NULL,NULL,e))return 0;
  if(x->phase==RP_BASE||x->phase==RP_FRESH)*expected=x->before;
  else if(x->phase==RP_PREP||x->phase==RP_RESTORE_PREP){if(rf_same(&now,&x->before))*expected=x->before;else *expected=x->after;}
  else *expected=x->after;
  if(!rf_same(&now,expected))return rr(r,e,"recovery-foreign-mirror");return 1;
}
static int rledger_file(lm_recovery *r,const char *token,const RRecord *ack,lm_err *e){char d[4096],p[4096],plan[4096];lm_mirror_file ledger;if(!r->ledger_found)return rr(r,e,"recovery-ack-ledger-absent");if(!rp(d,r->root,token,r,e)||!rp(p,d,"ledger.bin",r,e)||!lr_snapshot(r,p,1,R_LIMIT,&ledger,NULL,NULL,e)||!ledger.present||!rartifact(r,plan,"plan",ack->run,e))return 0;return requal(r,plan,&ack->plan,p,&ledger,e);}
static int rbound(lm_recovery *r,const lm_pack *pack,lm_err *e){uint64_t total=r->base.baseline.size,values[5],i;values[0]=pack->size;values[1]=pack->size;values[2]=pack->manifest_len;values[3]=(uint64_t)pack->books->n;values[4]=(uint64_t)pack->notes->n;
  if(values[2]>R_LIMIT/8||values[3]>R_LIMIT/(8u*1024u*1024u)||values[4]>R_LIMIT/131072)return rr(r,e,"recovery-import-growth-bound");values[2]*=8;values[3]*=8u*1024u*1024u;values[4]*=131072;for(i=0;i<5;i++){if(values[i]>R_LIMIT-total)return rr(r,e,"recovery-import-growth-bound");total+=values[i];}if(total>R_LIMIT-16u*1024u*1024u)return rr(r,e,"recovery-import-growth-bound");r->projected=total+16u*1024u*1024u;
  /* Two separate planned mirror files + preimage, up to eight records and
   * bounded logs. This does NOT claim a bound on frozen SQLite target sidecars. */
  return rinventory(r,3*r->projected+R_RESERVE*R_RECORD_BYTES+1048576,e);
}
int lr_prepare(lm_recovery *r,const lm_pack *pack,int recover,lm_err *e){
  struct stat s;char mirror[4096],p[4096],token[64];RRecord next={0},prior={0};lm_mirror_file base;int exists;
  if(!r||!pack||!pack->books||!pack->notes||!hex(pack->sha,64))return rr(r,e,"recovery-pack-required");strcpy(r->pack_sha,pack->sha);
  if(!lr_snapshot(r,r->pack_path,1,R_LIMIT,&r->pack_input,NULL,NULL,e)||!r->pack_input.present||strcmp(r->pack_input.sha,pack->sha)||fstat(fileno(pack->f),&s))return rr(r,e,"recovery-pack-identity-or-hash");
  {char opened[33];rid(&s,opened);if(strcmp(opened,r->pack_input.identity))return rr(r,e,"recovery-pack-open-handle-changed");}
  exists=lstat(r->root,&s)==0;if(!exists&&errno!=ENOENT)return rr(r,e,"recovery-root-stat");if(exists){if(!rload(r,e))return 0;}else if(!rinit(r,e))return 0;
  if(r->count>R_RECORDS-R_RESERVE)return rr(r,e,"recovery-record-capacity-before-open");
  if(r->count)prior=r->records[r->count-1];
  if(r->count&&prior.phase!=RP_ACK){if(!recover)return rr(r,e,"recovery-explicit-retry-required");if(strcmp(r->base.pack,r->pack_sha))return rr(r,e,"recovery-original-pack-required");strcpy(r->route,"R");if(!rbaseline_path(r,p,&r->base,e)||!rsame(r,p,&r->base.baseline,1,e))return 0;if(!rartifact(r,p,"pack",r->base.run,e)||!rsame(r,p,&r->base.pack_file,1,e)||strcmp(r->base.pack_file.sha,r->pack_sha))return rr(r,e,"recovery-original-pack-evidence");return rbound(r,pack,e);}
  if(!r->count&&strcmp(r->pack_sha,r->anchor.pack))return rr(r,e,"recovery-anchor-original-pack-required");
  if(!r->count&&!r->new_root&&!recover)return rr(r,e,"recovery-explicit-retry-required");strcpy(r->route,r->count?"C":"initial");
  if(r->count){lm_mirror_file current;if(!rcurrent(r,&current,e))return 0;}
  if(!rscan(r,1,token,&base,e))return 0;if(r->count&&!rledger_file(r,token,&prior,e))return 0;
  next.phase=r->count?RP_FRESH:RP_BASE;next.generation=r->count?prior.generation+1:1;strcpy(next.run,r->nonce);strcpy(next.base_token,token);strcpy(next.pack,r->pack_sha);next.baseline=base;
  if(!rmirror(r,mirror,e)||!lr_snapshot(r,mirror,1,R_LIMIT,&next.before,NULL,NULL,e))return 0;
  if(r->count&&!rf_same(&next.before,&prior.after))return rr(r,e,"recovery-ack-mirror-changed");
  if(!r->count&&!rf_same(&next.before,&r->anchor.before))return rr(r,e,"recovery-anchor-mirror-changed");
  if(next.before.present){if(!rartifact(r,p,"before",r->nonce,e)||!rcopy(r,mirror,&next.before,p,&next.preimage,e))return 0;}
  if(!rartifact(r,p,"pack",r->nonce,e)||!rcopy(r,r->pack_path,&r->pack_input,p,&next.pack_file,e))return 0;
  if(!rappend(r,&next,1,e)||!rbound(r,pack,e)||!lr_pause(r,"S2-baseline-durable",e))return 0;return 1;
}
int lr_opening(lm_recovery *r,lm_err *e){RRecord x;if(!r||r->opening||!r->count||r->count>R_RECORDS-R_RESERVE)return rr(r,e,"recovery-opening-capacity-or-state");x=r->records[r->count-1];x.phase=RP_OPENING;if(!rappend(r,&x,1,e))return 0;r->opening=1;return lr_pause(r,"SDK-opening-durable",e)&&rchain(r,e);}
static int rrestore(lm_recovery *r,lm_err *e){const RRecord *prior=rlast_mirror(r);RRecord restore;lm_mirror_file now,made;char mirror[4096],pre[4096],work[4096],archive[4096];int need=0;
  if(!rcurrent(r,&now,e)||!rmirror(r,mirror,e))return 0;
  if(prior->phase==RP_BASE||prior->phase==RP_FRESH)return 1;
  if(prior->phase==RP_RESTORED){if(!lm_mirror_same_bytes(&now,&r->base.before))return rr(r,e,"recovery-restored-byte-binding");return 1;}
  /* A PREP before rename can still match the original bytes/identity. Keep the
   * unused plan and all evidence; no need to replace an unchanged mirror. */
  if(prior->phase==RP_PREP&&rf_same(&now,&prior->before)&&lm_mirror_same_bytes(&now,&r->base.before))return 1;
  if(prior->phase==RP_RESTORE_PREP&&rf_same(&now,&prior->after)&&lm_mirror_same_bytes(&now,&r->base.before))return rsyncdir(r,r->root,e)&&rsyncdir(r,r->parent,e);
  restore=r->records[r->count-1];restore.phase=RP_RESTORE_PREP;restore.before=now;memset(&restore.after,0,sizeof(restore.after));
  if(now.present){if(!rartifact(r,archive,"saved-mirror",r->nonce,e)||!rcopy(r,mirror,&now,archive,&made,e))return 0;}
  if(r->base.preimage.present){if(!rartifact(r,pre,"before",r->base.run,e)||!rartifact(r,work,"restore",r->nonce,e)||!rcopy(r,pre,&r->base.preimage,work,&restore.after,e))return 0;}
  if(!rappend(r,&restore,1,e))return 0;need=1;
  if(!lr_pause(r,"restore-prepared",e)||!rchain(r,e)||!rsame(r,mirror,need?&restore.before:&restore.after,1,e))return 0;
  if(need){if(restore.after.present){if(!rsame(r,work,&restore.after,1,e)||rename(work,mirror))return rr(r,e,"recovery-restore-rename");}else if(restore.before.present&&unlink(mirror))return rr(r,e,"recovery-restore-unlink");}
  if(!rsyncdir(r,r->root,e)||!rsyncdir(r,r->parent,e)||!rsame(r,mirror,&restore.after,1,e))return 0;restore.phase=RP_RESTORED;return rappend(r,&restore,1,e);
}
int lr_compare_restore(lm_recovery *r,exr_library *owner,lm_err *e){char token[64],dir[4096],current[4096],original[4096];lm_mirror_file got;if(!r||!r->owner_active||!owner)return rr(r,e,"recovery-owner-required");if(!lr_pause(r,"S3-owner-open",e)||!rscan(r,0,token,&got,e)||!rp(dir,r->root,token,r,e)||!rp(current,dir,"baseline.bin",r,e)||!rbaseline_path(r,original,&r->base,e)||!requal(r,original,&r->base.baseline,current,&got,e))return 0;
  /* The scan's committed snapshot is compared in full while this exact SDK
   * writer is alive. It cannot attest the SDK's private uncommitted pages. */
  if(!strcmp(r->route,"C")){unsigned i=r->count;const RRecord *ack=NULL;void *data=NULL;size_t n=0;int found=0;exr_error error={0};char plan[4096],*bytes=NULL;size_t size=0;
    while(i){const RRecord *x=&r->records[--i];if(x->phase==RP_ACK){ack=x;break;}}if(!ack||!rledger_file(r,token,ack,e)||!rartifact(r,plan,"plan",ack->run,e)||!lr_read(r,plan,&bytes,&size,R_LIMIT,e))return 0;
    if(exr_library_migration_ledger_get(owner,&data,&n,&found,&error)!=EXR_OK||!found||n!=size||memcmp(data,bytes,size)){free(bytes);exr_free(data);return rr(r,e,"recovery-owner-ledger-lineage");}free(bytes);exr_free(data);
  }
  if(!strcmp(r->route,"R")&&!rrestore(r,e))return 0;r->compared=1;return lr_pause(r,"owner-compared",e);
}
int lr_publish(lm_recovery *r,const void *ledger,size_t n,lm_err *e){RRecord x;char mirror[4096],plan[4096],work[4096];lm_mirror_file before;
  if(!r||!r->owner_active||!r->compared||n>r->projected||!n)return rr(r,e,"recovery-publish-state-or-bound");if(!rcurrent(r,&before,e)||!rmirror(r,mirror,e)||!rartifact(r,plan,"plan",r->nonce,e)||!rartifact(r,work,"work",r->nonce,e))return 0;x=r->records[r->count-1];x.phase=RP_PREP;x.before=before;
  if(!lr_write_new(r,plan,ledger,n,e)||!lr_snapshot(r,plan,1,R_LIMIT,&x.plan,NULL,NULL,e)||!lr_write_new(r,work,ledger,n,e)||!lr_snapshot(r,work,1,R_LIMIT,&x.after,NULL,NULL,e)||!rappend(r,&x,1,e)||!lr_pause(r,"S4-prepared",e)||!rchain(r,e)||!rsame(r,mirror,&before,1,e)||!rsame(r,work,&x.after,1,e))return 0;
  if(rename(work,mirror))return rr(r,e,"recovery-mirror-publish");if(!lr_pause(r,"mirror-published-before-sync",e))return 0;
  if(rtest("mirror-sync-ebadf")){int result=fsync(-1);if(result!=-1||errno!=EBADF)return rr(r,e,"recovery-sync-fault-calibration");return rr(r,e,"recovery-mirror-sync-injected-native-ebadf");}
  if(!rsyncdir(r,r->root,e)||!rsyncdir(r,r->parent,e)||!rsame(r,mirror,&x.after,1,e))return 0;x.phase=RP_MIRROR;if(!rappend(r,&x,1,e))return 0;return lr_pause(r,"S5-mirror-durable",e)&&rchain(r,e)&&rsame(r,mirror,&x.after,1,e);
}
int lr_ack(lm_recovery *r,exr_status status,lm_err *e){RRecord x;char p[4096],mirror[4096];if(r)r->commit_status=(int)status;if(!r||!r->owner_active||!r->count||status!=EXR_OK||r->records[r->count-1].phase!=RP_MIRROR)return rr(r,e,"recovery-real-commit-required");
  if(!lr_pause(r,"S6-commit-before-ack",e)||!rchain(r,e)||!rmirror(r,mirror,e)||!rsame(r,mirror,&r->records[r->count-1].after,1,e))return 0;x=r->records[r->count-1];x.phase=RP_ACK;if(!rappend(r,&x,0,e)||!lr_pause(r,"S7-ack-before-sync",e)||!rname(r,p,r->count-1,e)||!rsyncfile(r,p,e)||!rsyncdir(r,r->root,e)||!rsyncdir(r,r->parent,e)||!rchain(r,e)||!rsame(r,mirror,&x.after,1,e))return 0;r->acknowledged=1;return 1;
}
int lr_complete(lm_recovery *r,lm_err *e){char mirror[4096];if(!r||r->owner_active||!r->acknowledged||r->commit_status!=EXR_OK)return rr(r,e,"recovery-completion-state");if(!lr_pause(r,"S8-owner-closed",e)||!rchain(r,e)||!rmirror(r,mirror,e)||!rsame(r,mirror,&r->records[r->count-1].after,1,e))return 0;snprintf(r->phase,sizeof(r->phase),"commit-acknowledged");return 1;}
int lr_read_view(lm_recovery *r,char **view,lm_err *e){struct stat s;char token[64],dir[4096],p[4096],original_mirror[4096],clone_mirror[4096],ledger_path[4096];lm_mirror_file baseline,mirror,ledger,copied;RRecord ack;int exists;*view=NULL;if(!r)return rr(r,e,"recovery-read-context");exists=lstat(r->root,&s)==0;if(!exists&&errno!=ENOENT)return rr(r,e,"recovery-root-stat");
  if(exists){if(!rload(r,e))return 0;if(!r->count||r->records[r->count-1].phase!=RP_ACK)return rr(r,e,"recovery-read-pending-preopen-refusal");ack=r->records[r->count-1];{lm_mirror_file f;if(!rcurrent(r,&f,e))return 0;}r->read_only=1;}
  else {
    /* A read command does not create a permanent recovery policy. It captures
     * a coherent private read view and opens the SDK only on that clone. */
    if(lstat(r->barrier,&s)==0||errno!=ENOENT)return rr(r,e,"recovery-existing-barrier");r->read_only=2;
    if(snprintf(r->root,sizeof(r->root),"%s.migration-read-%s",r->target,r->nonce)>=sizeof(r->root)||mkdir(r->root,0700)||!rdir(r,r->root,r->root_id,1,e)||!rsyncdir(r,r->parent,e))return rr(r,e,"recovery-read-view-root");
    if(!lr_snapshot(r,r->worker,1,R_LIMIT,&r->worker_id,NULL,NULL,e)||!r->worker_id.present)return rr(r,e,"recovery-worker-missing");if(strcmp(r->font,"-")&&(!lr_snapshot(r,r->font,1,R_LIMIT,&r->font_id,NULL,NULL,e)||!r->font_id.present))return rr(r,e,"recovery-font-missing");if(!rrun_dir(r,e))return 0;
  }
  if(!rmirror(r,original_mirror,e)||!lr_snapshot(r,original_mirror,1,R_LIMIT,&mirror,NULL,NULL,e))return 0;
  if(!rscan(r,1,token,&baseline,e))return 0;if(exists){char mirror[4096];if(!rledger_file(r,token,&ack,e)||!rchain(r,e)||!rmirror(r,mirror,e)||!rsame(r,mirror,&ack.after,1,e))return 0;}if(!rguard(r,e)||!rp(dir,r->root,token,r,e)||!rp(p,dir,"clone.sqlite",r,e))return 0;
  if(!rsame(r,original_mirror,&mirror,1,e))return 0;
  if(mirror.present){
    if(r->ledger_found){if(!rp(ledger_path,dir,"ledger.bin",r,e)||!lr_snapshot(r,ledger_path,1,R_LIMIT,&ledger,NULL,NULL,e)||!ledger.present||!requal(r,original_mirror,&mirror,ledger_path,&ledger,e))return rr(r,e,"recovery-read-original-mirror-divergence");}
    if(snprintf(clone_mirror,sizeof(clone_mirror),"%s.legacy-map.json",p)>=sizeof(clone_mirror)||!rcopy(r,original_mirror,&mirror,clone_mirror,&copied,e))return 0;
  }
  if(!rguard(r,e)||!rsame(r,original_mirror,&mirror,1,e)||(exists&&!rchain(r,e)))return 0;
  *view=malloc(strlen(p)+1);if(!*view)return rr(r,e,"recovery-read-view-allocation");strcpy(*view,p);snprintf(r->phase,sizeof(r->phase),"private-snapshot-read");return 1;
}
#endif /* POSIX protocol */
void lr_owner_attempted(lm_recovery *r){if(r)r->attempted=1;}
void lr_owner_started(lm_recovery *r){if(r)r->owner_active=1;}
void lr_owner_closed(lm_recovery *r){if(r)r->owner_active=0;/* lease and quarantined fds survive until process exit */}
void lr_rollback(lm_recovery *r,exr_status s){if(r){r->rollback_valid=1;r->rollback_status=(int)s;snprintf(r->phase,sizeof(r->phase),"rollback-requested-recovery-required");}}
void lr_report(lm_recovery *r,lm_sb *b){
  lm_sb_str(b,"{\"protocol\":\"existing-target-recovery-v1\",\"product_p0_accepted\":false,\"physical_cleanup_verified\":false,\"historical_rollback_proven\":false,\"io_observation\":\"not-installed\",\"evidence_retirement\":\"never\",\"scope\":\"existing-target-native-POSIX\",\"phase\":");
  lm_sb_json(b,r?r->phase:"preopen-refusal",strlen(r?r->phase:"preopen-refusal"));lm_sb_str(b,",\"reason\":");lm_sb_json(b,r?r->reason:"recovery-platform-unqualified",strlen(r?r->reason:"recovery-platform-unqualified"));
  lm_sb_str(b,",\"worker_reason\":");lm_sb_json(b,r?r->worker_reason:"",strlen(r?r->worker_reason:""));lm_sb_str(b,",\"route\":");lm_sb_json(b,r?r->route:"",strlen(r?r->route:""));
  lm_sb_fmt(b,",\"target_sdk_open_attempted\":%s,\"same_owner_comparison\":%s,\"commit_acknowledged\":%s,\"explicit_recovery_required\":%s,\"records\":%u,\"generation\":%u,\"quarantined_descriptors\":%u,\"evidence_bytes\":%llu,\"projected_import_bytes\":%llu,\"rollback_requested\":",r&&r->attempted?"true":"false",r&&r->compared?"true":"false",r&&r->acknowledged?"true":"false",r&&!r->acknowledged&&(r->opening||(r->root_seen&&(!r->count||r->records[r->count-1].phase!=RP_ACK)))?"true":"false",r?r->count:0,r?r->generation:0,r?r->quarantined:0,(unsigned long long)(r?r->bytes:0),(unsigned long long)(r?r->projected:0));
  lm_sb_str(b,r&&r->rollback_valid?"true":r&&r->commit_status==EXR_OK?"false":"null");lm_sb_str(b,",\"rollback_sdk_status\":");if(r&&r->rollback_valid)lm_sb_fmt(b,"%d",r->rollback_status);else lm_sb_str(b,"null");lm_sb_str(b,",\"commit_sdk_status\":");if(r&&r->commit_status>=0)lm_sb_fmt(b,"%d",r->commit_status);else lm_sb_str(b,"null");lm_sb_str(b,"}");
}
