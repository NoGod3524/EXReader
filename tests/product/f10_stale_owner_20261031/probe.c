/* SPDX-License-Identifier: MIT */
#define _POSIX_C_SOURCE 200809L
#include <exr_webdav_cleanup.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>
static const char data[]="synthetic snapshot owned by this test only";
static const char *which;
static int failures,checks;
static void check(const char *name,long actual,long expected) {
  printf("{\"check\":\"%s\",\"actual\":%ld,\"expected\":%ld}\n",name,actual,expected);
  fflush(stdout);checks++;if(actual!=expected)failures++;
}
static void need(int yes) {if(!yes){perror("fixture");exit(90);}}
static void writeall(int fd,const void *buf,size_t n) {
  const char *p=buf;while(n){ssize_t k=write(fd,p,n);need(k>0);p+=k;n-=(size_t)k;}
}
static void readall(int fd,void *buf,size_t n) {
  char *p=buf;while(n){ssize_t k=read(fd,p,n);need(k>0);p+=k;n-=(size_t)k;}
}
static void file(const char *p) {int f=open(p,O_CREAT|O_EXCL|O_WRONLY,0600);need(f>=0);writeall(f,data,sizeof data);close(f);}
static int intact(const char *p) {char b[sizeof data];int f=open(p,O_RDONLY|O_NOFOLLOW);if(f<0)return 0;ssize_t n=read(f,b,sizeof b);close(f);return n==(ssize_t)sizeof b&&!memcmp(b,data,sizeof b);}
void exr_wc_test_hook(const char *phase,uint32_t slot,uint32_t state) {
  (void)slot;(void)state;const char *stop=getenv("F10_STOP");
  if(stop&&!strcmp(stop,phase))kill(getpid(),SIGKILL);
}
typedef struct {char uuid[33];exr_wc_info info;} saved;
static int parentfd(void) {return open(".",O_RDONLY|O_DIRECTORY|O_CLOEXEC);}
static saved dead(int sealed,int lockcheck) {
  int p[2],status;need(pipe(p)==0);pid_t pid=fork();need(pid>=0);
  if(!pid){
    close(p[0]);saved s={0};exr_wc_root *r=NULL;exr_wc_tx *tx=NULL;int fd=-1,par=parentfd();
    need(exr_wc_create_at(par,"root",&r,s.uuid)==EXR_WC_OK);
    need(exr_wc_begin(r,&tx,&fd)==EXR_WC_OK);writeall(fd,data,sizeof data);
    if(sealed)need(exr_wc_seal(tx)==EXR_WC_OK);
    need(exr_wc_inspect(r,0,&s.info)==EXR_WC_OK);writeall(p[1],&s,sizeof s);close(p[1]);
    for(;;)pause();
  }
  close(p[1]);saved s;readall(p[0],&s,sizeof s);close(p[0]);
  if(lockcheck){exr_wc_root *r=NULL;int par=parentfd();check("active_owner_busy",exr_wc_open_at(par,"root",s.uuid,&r),EXR_WC_BUSY);close(par);}
  need(kill(pid,SIGKILL)==0);need(waitpid(pid,&status,0)==pid);
  check("actual_sigkill",WIFSIGNALED(status)?WTERMSIG(status):0,SIGKILL);
  check("different_process",pid!=getpid(),1);return s;
}
static void paths(saved *s,char *dir,char *payload) {
  snprintf(dir,128,"root/tx-%s",s->info.transaction_id);
  snprintf(payload,160,"%s/payload",dir);
}
static void state(exr_wc_root *r,unsigned want) {exr_wc_info i;need(exr_wc_inspect(r,0,&i)==0);check("receipt_state",i.state,want);}
static void stale_case(void) {
  int sealed=strcmp(which,"owned-kill")!=0&&strcmp(which,"legacy-owned-pending")!=0; saved s=dead(sealed,!strcmp(which,"active-owner"));
  char dir[128],payload[160];paths(&s,dir,payload);
  struct stat initial;need(lstat(payload,&initial)==0);check("actual_snapshot_bytes",initial.st_size,sizeof data);
  exr_wc_root *r=NULL;exr_wc_cleanup_result result;int par=parentfd();
  if(!strcmp(which,"wrong-uuid")){s.uuid[0]=s.uuid[0]=='a'?'b':'a';check("open_refused",exr_wc_open_at(par,"root",s.uuid,&r),EXR_WC_REFUSED);check("payload_preserved",intact(payload),1);close(par);return;}
  if(!strcmp(which,"residual-receipt-next")){file("root/.receipt.next");check("open_refused",exr_wc_open_at(par,"root",s.uuid,&r),EXR_WC_REFUSED);check("payload_preserved",intact(payload),1);close(par);return;}
  if(!strcmp(which,"corrupt-receipt")){int f=open("root/.receipt",O_WRONLY);need(f>=0);need(pwrite(f,"X",1,0)==1);close(f);check("open_refused",exr_wc_open_at(par,"root",s.uuid,&r),EXR_WC_REFUSED);check("payload_preserved",intact(payload),1);close(par);return;}
  need(exr_wc_open_at(par,"root",s.uuid,&r)==0);
  exr_wc_info expected=s.info;int code=EXR_WC_REFUSED;
  if(!strcmp(which,"owned-kill")||!strcmp(which,"sealed-kill")||!strcmp(which,"active-owner")||!strcmp(which,"historical-device"))code=EXR_WC_OK;
  if(!strcmp(which,"unregistered-residue")){file("root/.reader-sync-foreign.tmp");code=EXR_WC_OK;}
  if(!strcmp(which,"historical-device"))expected.directory_device=expected.payload_device=UINT64_MAX;
  if(!strcmp(which,"wrong-id"))expected.transaction_id[0]=expected.transaction_id[0]=='a'?'b':'a';
  if(!strcmp(which,"wrong-slot")){expected.slot=1;code=EXR_WC_ARGUMENT;}
  if(!strcmp(which,"wrong-inode"))expected.payload_inode++;
  if(!strcmp(which,"wrong-state"))expected.state=EXR_WC_OWNED;
  if(!strcmp(which,"wrong-bytes"))expected.bytes++;
  if(!strcmp(which,"extra-entry")){char x[160];snprintf(x,sizeof x,"%s/extra",dir);file(x);}
  if(!strcmp(which,"payload-replaced")){need(rename(payload,"held-original")==0);file(payload);}
  if(!strcmp(which,"directory-replaced")){need(rename(dir,"held-directory")==0);need(mkdir(dir,0700)==0);file(payload);}
  if(!strcmp(which,"payload-symlink")){need(rename(payload,"held-original")==0);need(symlink("../../held-original",payload)==0);}
  if(!strcmp(which,"directory-symlink")){need(rename(dir,"held-directory")==0);need(symlink("../held-directory",dir)==0);}
  if(!strcmp(which,"extra-hardlink"))need(link(payload,"held-link")==0);
  if(!strcmp(which,"foreign-payload-owner")){pid_t p=fork();need(p>=0);if(!p){execlp("sudo","sudo","-n","chown","0",payload,(char*)NULL);_exit(93);}int status;need(waitpid(p,&status,0)==p);need(WIFEXITED(status)&&WEXITSTATUS(status)==0);struct stat st;need(lstat(payload,&st)==0);check("actual_foreign_uid",st.st_uid,0);}
  if(!strcmp(which,"payload-permissions"))need(chmod(payload,0644)==0);
  if(!strcmp(which,"directory-permissions"))need(chmod(dir,0755)==0);
  if(!strcmp(which,"sealed-size")){int f=open(payload,O_WRONLY|O_APPEND);need(f>=0);writeall(f,"x",1);close(f);}
  if(!strcmp(which,"legacy-owned-pending")){
    exr_wc_recovery_report rep;check("old_recover_status",exr_wc_recover(r,0,64,&rep),EXR_WC_OK);
    check("old_pending",rep.pending,1);check("payload_preserved",intact(payload),1);code=EXR_WC_OK;
  }
  if(!strcmp(which,"permission-retry")){
    need(chmod(dir,0500)==0);
    check("permission_failure",exr_wc_abandon_stale(r,&expected,&result),EXR_WC_IO);
    check("pending",result.pending,1);check("native_eacces",result.native_error,EACCES);
    check("payload_preserved",intact(payload),1);need(chmod(dir,0700)==0);code=EXR_WC_OK;
  }
  struct stat before,after;int existed=lstat(payload,&before)==0;
  int rc=exr_wc_abandon_stale(r,&expected,&result);check("abandon_status",rc,code);
  if(code==EXR_WC_OK){
    check("removed",result.removed,1);check("directory_absent",access(dir,F_OK)<0&&errno==ENOENT,1);
    state(r,EXR_WC_CLEANED);
    check("same_identity_idempotent",exr_wc_abandon_stale(r,&expected,&result),EXR_WC_OK);
    expected.transaction_id[0]=expected.transaction_id[0]=='a'?'b':'a';
    check("cleaned_wrong_id_refused",exr_wc_abandon_stale(r,&expected,&result),EXR_WC_REFUSED);
  }else{
    check("rejected_path_identity_preserved",existed&&lstat(payload,&after)==0&&before.st_ino==after.st_ino&&before.st_size==after.st_size,1);
    state(r,s.info.state);
  }
  if(!strcmp(which,"unregistered-residue"))check("unknown_residue_preserved",intact("root/.reader-sync-foreign.tmp"),1);
  check("close",exr_wc_close(&r),EXR_WC_OK);close(par);
}
static void borrowed(void) {
  int par=parentfd(),fd=-1,ro=-1;char uuid[33];exr_wc_root *r=NULL;exr_wc_tx *tx=NULL;exr_wc_info i;exr_wc_cleanup_result result;
  need(exr_wc_create_at(par,"root",&r,uuid)==0);need(exr_wc_begin(r,&tx,&fd)==0);writeall(fd,data,sizeof data);
  check("owned_borrow_refused",exr_wc_borrow_sealed_fd(tx,&ro),EXR_WC_REFUSED);check("failed_fd_negative",ro,-1);
  need(exr_wc_inspect(r,0,&i)==0);check("active_tx_busy",exr_wc_abandon_stale(r,&i,&result),EXR_WC_BUSY);
  need(exr_wc_seal(tx)==0);
  if(!strcmp(which,"borrow-replaced")){
    need(exr_wc_inspect(r,0,&i)==0);char payload[160];snprintf(payload,sizeof payload,"root/tx-%s/payload",i.transaction_id);
    need(rename(payload,"held-original")==0);file(payload);
    check("replacement_borrow_refused",exr_wc_borrow_sealed_fd(tx,&ro),EXR_WC_REFUSED);
    check("failed_fd_negative_again",ro,-1);
  }else{
    char b[sizeof data];check("sealed_borrow",exr_wc_borrow_sealed_fd(tx,&ro),EXR_WC_OK);
    check("kernel_readonly",fcntl(ro,F_GETFL)&O_ACCMODE,O_RDONLY);
    ssize_t n=pread(ro,b,sizeof b,0);check("exact_snapshot_read",n==(ssize_t)sizeof b&&!memcmp(b,data,sizeof b),1);
    errno=0;ssize_t wr=write(ro,"x",1);int we=errno;check("write_refused",wr,-1);check("write_errno",we,EBADF);
    check("root_close_busy",exr_wc_close(&r),EXR_WC_BUSY);
    check("cleanup",exr_wc_cleanup(tx,1,&result),EXR_WC_OK);
    errno=0;int fr=fcntl(ro,F_GETFD),fe=errno;check("borrow_closed_after_cleanup",fr,-1);check("closed_errno",fe,EBADF);
  }
  check("tx_close",exr_wc_tx_close(&tx),EXR_WC_OK);check("root_close",exr_wc_close(&r),EXR_WC_OK);close(par);
}
static void lifetime(void) {
  int par=parentfd(),fd=-1;char uuid[33];exr_wc_root *r=NULL;exr_wc_tx *tx=NULL;exr_wc_cleanup_result res;
  need(exr_wc_create_at(par,"root",&r,uuid)==0);
  unsigned complete=0;
  for(unsigned j=0;j<64;j++){
    if(exr_wc_begin(r,&tx,&fd)!=0)break;
    writeall(fd,data,sizeof data);
    if(exr_wc_seal(tx)||exr_wc_cleanup(tx,1,&res)||exr_wc_tx_close(&tx))break;
    complete++;
  }
  check("unchanged_64_slots",complete,64);check("slot65_limit",exr_wc_begin(r,&tx,&fd),EXR_WC_LIMIT);
  exr_wc_recovery_report rep;check("old_recover_status",exr_wc_recover(r,0,64,&rep),EXR_WC_OK);
  check("old_inspected64",rep.inspected,64);check("old_pending0",rep.pending,0);
  check("root_close",exr_wc_close(&r),EXR_WC_OK);close(par);
}
static void published(void) {
  int par=parentfd(),fd=-1;char uuid[33];exr_wc_root *r=NULL;exr_wc_tx *tx=NULL;exr_wc_publish_result p;exr_wc_cleanup_result cr;exr_wc_info i;
  need(exr_wc_create_at(par,"root",&r,uuid)==0);need(exr_wc_begin(r,&tx,&fd)==0);writeall(fd,data,sizeof data);need(exr_wc_seal(tx)==0);
  check("publish",exr_wc_publish_at(tx,par,"published",&p),EXR_WC_OK);check("published_flag",p.published,1);
  need(exr_wc_inspect(r,0,&i)==0);need(exr_wc_tx_close(&tx)==0);
  check("new_abandon_published_refused",exr_wc_abandon_stale(r,&i,&cr),EXR_WC_REFUSED);
  exr_wc_recovery_report rep;check("old_recover_status",exr_wc_recover(r,0,64,&rep),EXR_WC_OK);
  check("old_cleaned1",rep.cleaned,1);check("published_preserved",intact("published"),1);
  check("root_close",exr_wc_close(&r),EXR_WC_OK);close(par);
}
static void interrupted(void) {
  saved s=dead(1,0);int status;pid_t p=fork();need(p>=0);
  if(!p){
    const char *phase=!strcmp(which,"cleanup-kill-payload")?"alias_unlinked":"transaction_removed";
    need(setenv("F10_STOP",phase,1)==0);exr_wc_root *r=NULL;exr_wc_cleanup_result res;int par=parentfd();
    need(exr_wc_open_at(par,"root",s.uuid,&r)==0);exr_wc_abandon_stale(r,&s.info,&res);_exit(91);
  }
  need(waitpid(p,&status,0)==p);check("cleanup_actual_sigkill",WIFSIGNALED(status)?WTERMSIG(status):0,SIGKILL);
  int par=parentfd();exr_wc_root *r=NULL;exr_wc_cleanup_result res;
  need(exr_wc_open_at(par,"root",s.uuid,&r)==0);check("resume_after_partial_cleanup",exr_wc_abandon_stale(r,&s.info,&res),EXR_WC_OK);
  state(r,EXR_WC_CLEANED);check("close",exr_wc_close(&r),EXR_WC_OK);close(par);
}
static void uncertain_state(void) {
  int p[2],status;need(pipe(p)==0);pid_t child=fork();need(child>=0);
  if(!child){
    close(p[0]);char uuid[33];int par=parentfd(),fd=-1;exr_wc_root *r=NULL;exr_wc_tx *tx=NULL;exr_wc_publish_result result;
    need(exr_wc_create_at(par,"root",&r,uuid)==0);writeall(p[1],uuid,sizeof uuid);close(p[1]);
    need(setenv("F10_STOP",!strcmp(which,"reserved-refused")?"directory_created":"publish_intent",1)==0);
    need(exr_wc_begin(r,&tx,&fd)==0);writeall(fd,data,sizeof data);need(exr_wc_seal(tx)==0);
    exr_wc_publish_at(tx,par,"published",&result);_exit(92);
  }
  close(p[1]);char uuid[33];readall(p[0],uuid,sizeof uuid);close(p[0]);need(waitpid(child,&status,0)==child);
  check("actual_boundary_sigkill",WIFSIGNALED(status)?WTERMSIG(status):0,SIGKILL);
  int par=parentfd();exr_wc_root *r=NULL;exr_wc_info i;exr_wc_cleanup_result cr;exr_wc_recovery_report rep;
  need(exr_wc_open_at(par,"root",uuid,&r)==0);need(exr_wc_inspect(r,0,&i)==0);
  check("expected_state",i.state,!strcmp(which,"reserved-refused")?EXR_WC_RESERVED:EXR_WC_PUBLISH_INTENT);
  check("new_abandon_refused",exr_wc_abandon_stale(r,&i,&cr),EXR_WC_REFUSED);
  check("old_recover_status",exr_wc_recover(r,0,64,&rep),EXR_WC_OK);check("old_pending1",rep.pending,1);
  check("close",exr_wc_close(&r),EXR_WC_OK);close(par);
}
int main(int argc,char **argv) {
  if(argc!=2||geteuid()==0)return 2;
  which=argv[1];
  if(!strncmp(which,"borrow",6))borrowed();
  else if(!strcmp(which,"lifetime64"))lifetime();
  else if(!strcmp(which,"legacy-published"))published();
  else if(!strncmp(which,"cleanup-kill",12))interrupted();
  else if(!strcmp(which,"reserved-refused")||!strcmp(which,"intent-refused"))uncertain_state();
  else stale_case();
  printf("{\"summary\":true,\"checks\":%d,\"failures\":%d,\"euid\":%lu}\n",checks,failures,(unsigned long)geteuid());
  return failures?1:0;
}
