/* SPDX-License-Identifier: MIT */
#define _GNU_SOURCE 1
#define _DARWIN_C_SOURCE 1
#include <exr_pc02.h>
#include <exr_wh.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <fcntl.h>
#include <unistd.h>
#include <signal.h>
#include <poll.h>
#include <dirent.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#ifndef SOURCE_SHA
#define SOURCE_SHA "unknown"
#endif
#define PATH_BYTES 4096
typedef struct {char directory[PATH_BYTES],authority[PATH_BYTES],library[PATH_BYTES];
 } fixture;
typedef struct {const char *bytes;
 unsigned calls;
 } proof;
typedef struct {int ready,go;
 unsigned phase;
 } barrier;
static char work[PATH_BYTES],self[PATH_BYTES],manifest[65],input[65],terminal[65];
static unsigned checks,failures,cases,case_start,case_failures,fixture_count;
static int join(char out[PATH_BYTES],const char *root,const char *leaf){
 size_t a=strlen(root),b=strlen(leaf);
 if(a+b+2>PATH_BYTES)return 0;
 memcpy(out,root,a);
 out[a]='/';
 memcpy(out+a+1,leaf,b+1);
 return 1;
}
static int file_write(const char *path,const void *bytes,size_t n){
 int fd=open(path,O_RDWR|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
 size_t at=0;
 int ok=fd>=0;
 while(ok&&at<n){ssize_t put=write(fd,(const char *)bytes+at,n-at);
 if(put<=0)ok=0;
 else at+=(size_t)put;
 }
 if(ok&&fsync(fd))ok=0;
 if(fd>=0)close(fd);
 return ok;
}
static int file_read(const char *path,void *bytes,size_t n){
 int fd=open(path,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
 struct stat s;
 size_t at=0;
 int ok=fd>=0&&!fstat(fd,&s)&&s.st_size==(off_t)n;
 while(ok&&at<n){ssize_t got=read(fd,(char *)bytes+at,n-at);
 if(got<=0)ok=0;
 else at+=(size_t)got;
 }
 if(fd>=0)close(fd);
 return ok;
}
static int exact_proof(void *context,const char *path,int fd,const pc02_pending_record *pending,const char *end){
 proof *p=context;
 char data[64];
 struct stat s;
 size_t n=strlen(p->bytes);
 (void)path;
 p->calls++;
 if(n>sizeof(data)||fstat(fd,&s)||s.st_size!=(off_t)n||pread(fd,data,n,0)!=(ssize_t)n||memcmp(data,p->bytes,n))return 0;
 if(pending&&(!end||strcmp(pending->manifest,manifest)||strcmp(pending->input,input)||strcmp(end,terminal)))return 0;
 return 1;
}
static int reject_proof(void *context,const char *path,int fd,const pc02_pending_record *pending,const char *end){
 (void)context;
 (void)path;
 (void)fd;
 (void)pending;
 (void)end;
 return 0;
}
static void expect(int condition,const char *message){
 checks++;
 if(!condition){failures++;
 fprintf(stderr,"FAIL %s errno=%d\n",message,errno);
 }
}
static void begin_case(const char *name){cases++;
 case_start=checks;
 case_failures=failures;
 printf("CASE %u %s\n",cases,name);
 fflush(stdout);
 }
static void end_case(const char *name){printf("{\"case\":\"%s\",\"checks\":%u,\"failed\":%u}\n",name,checks-case_start,failures-case_failures);
 fflush(stdout);
 }
static int fresh(fixture *f,const char *name,int enroll){
 char directory[96];
 proof p={"original\n",0};
 snprintf(directory,sizeof(directory),"%02u-%s",++fixture_count,name);
 if(!join(f->directory,work,directory)||mkdir(f->directory,0700)||!join(f->authority,f->directory,"authority")||
 !join(f->library,f->directory,"library.sqlite")||!pc02_authority_create(f->authority)||
 !file_write(f->library,"original\n",9))return 0;
 return !enroll||pc02_enroll(f->authority,f->library,0,exact_proof,&p,NULL);
}
static int route_path(const fixture *f,const char *leaf,char out[PATH_BYTES]){
 DIR *d=opendir(f->authority);
 struct dirent *e;
 char route[PATH_BYTES];
 int found=0;
 if(!d)return 0;
 while((e=readdir(d)))if(strlen(e->d_name)==64&&strspn(e->d_name,"0123456789abcdef")==64){
  if(found||!join(route,f->authority,e->d_name)){closedir(d);
 return 0;
 }found=1;
 }
 closedir(d);
 return found&&join(out,route,leaf);
}
static int opened(const fixture *f,unsigned mode,pc02_lease **h){
 return pc02_open(f->authority,f->library,mode,NULL,NULL,h);
}
static void at_phase(void *context,unsigned phase){
 barrier *b=context;
 char value='r';
 if(phase!=b->phase)return;
 if(write(b->ready,&value,1)!=1)_exit(93);
 if(read(b->go,&value,1)!=1||value!='g')_exit(94);
}
static int publish_fixture(const char *library){
 char stage[PATH_BYTES],retained[PATH_BYTES];
 size_t n=strlen(library);
 if(n+16>=PATH_BYTES)return 0;
 strcpy(stage,library);
 strcat(stage,".private");
 strcpy(retained,library);
 strcat(retained,".retained");
 return file_write(stage,"published\n",10)&&!rename(library,retained)&&!rename(stage,library);
}
static int child_main(int argc,char **argv){
 pc02_lease *h=NULL;
 pc02_cap *cap=NULL;
 pc02_grant grant;
 pc02_pending_record descriptor;
 unsigned mode=(unsigned)strtoul(argv[4],NULL,10),phase=(unsigned)strtoul(argv[5],NULL,10);
 barrier b={atoi(argv[6]),atoi(argv[7]),phase};
 pc02_controls controls={&b,at_phase,0,0};
 proof p={"published\n",0};
 if(argc!=8||!pc02_open(argv[2],argv[3],mode,NULL,&controls,&h))return 81;
 if(phase==9000){at_phase(&b,9000);
 return pc02_close(h)?0:82;
 }
 if(mode!=PC02_OWNER||!pc02_begin(h,manifest,input,&cap))return 83;
 if(!pc02_pending(h,&descriptor))return 84;
 char path[PATH_BYTES];
 if(strlen(argv[3])+24>=sizeof(path))return 85;
 strcpy(path,argv[3]);
 strcat(path,".producer-descriptor");
 if(!file_write(path,&descriptor,sizeof(descriptor))||!pc02_prepare_publish(h,cap)||!publish_fixture(argv[3]))return 86;
 if(!pc02_finish(h,cap,terminal,exact_proof,&p,&grant))return 87;
 return pc02_close(h)?0:88;
}
typedef struct {pid_t pid;
 int ready,go;
 } child;
static int spawn_child(const fixture *f,unsigned mode,unsigned phase,child *out){
 int ready[2]={-1,-1},go[2]={-1,-1};
 char modes[16],phases[16],ready_fd[16],go_fd[16];
 pid_t pid;
 if(pipe(ready)||pipe(go))return 0;
 for(unsigned k=0;
 k<2;
 k++)if(fcntl(ready[k],F_SETFD,FD_CLOEXEC)||fcntl(go[k],F_SETFD,FD_CLOEXEC))return 0;
 snprintf(modes,sizeof(modes),"%u",mode);
 snprintf(phases,sizeof(phases),"%u",phase);
 snprintf(ready_fd,sizeof(ready_fd),"%d",ready[1]);
 snprintf(go_fd,sizeof(go_fd),"%d",go[0]);
 pid=fork();
 if(pid<0)return 0;
 if(!pid){
  if(fcntl(ready[1],F_SETFD,0)||fcntl(go[0],F_SETFD,0))_exit(90);
  execl(self,self,"--child",f->authority,f->library,modes,phases,ready_fd,go_fd,(char *)NULL);
 _exit(91);
 }
 close(ready[1]);
 close(go[0]);
 out->pid=pid;
 out->ready=ready[0];
 out->go=go[1];
 return 1;
}
static int reached(child *c){
 struct pollfd pollfd={c->ready,POLLIN|POLLHUP,0};
 char value=0;
 int status;
 do{status=poll(&pollfd,1,15000);
 }while(status<0&&errno==EINTR);
 return status>0&&read(c->ready,&value,1)==1&&value=='r';
}
static int finish_child(child *c,int killed){
 int status=0;
 char go='g';
 if(killed){if(kill(c->pid,SIGKILL))return 0;
 }
 else if(write(c->go,&go,1)!=1)return 0;
 if(waitpid(c->pid,&status,0)!=c->pid)return 0;
 close(c->ready);
 close(c->go);
 return killed?(WIFSIGNALED(status)&&WTERMSIG(status)==SIGKILL):(WIFEXITED(status)&&WEXITSTATUS(status)==0);
}
static void missing_and_enroll_case(void){
 const char *name="missing-explicit-enrollment";
 fixture f={0};
 pc02_lease *h=NULL;
 proof p={"original\n",0};
 begin_case(name);
 expect(fresh(&f,name,0),"new independent authority and regular target");
 expect(!opened(&f,PC02_SHARED,&h)&&!h,"ordinary missing route refused without creation");
 expect(!pc02_authority_create(f.authority),"existing authority is never reinitialized");
 expect(pc02_enroll(f.authority,f.library,0,exact_proof,&p,NULL)&&p.calls==1,"explicit actual initial proof");
 expect(!pc02_enroll(f.authority,f.library,0,exact_proof,&p,NULL),"existing route is never adopted");
 expect(opened(&f,PC02_SHARED,&h),"fresh independently registered reader");
 expect(pc02_close(h),"reader close");
 end_case(name);
}
static void create_case(void){
 const char *name="explicit-create";
 fixture f={0};
 pc02_lease *h=NULL;
 proof p={"",0};
 begin_case(name);
 expect(fresh(&f,name,0),"fresh authority");
 expect(!unlink(f.library),"test removes only its private target");
 expect(pc02_enroll(f.authority,f.library,1,exact_proof,&p,NULL),"CREATE_NEW target explicit proof");
 expect(!pc02_enroll(f.authority,f.library,1,exact_proof,&p,NULL),"CREATE_NEW never overwrites");
 expect(opened(&f,PC02_SHARED,&h),"created registered reader");
 expect(pc02_close(h),"created reader close");
 end_case(name);
}
static void borrow_case(void){
 const char *name="last-borrow-retains-shared";
 fixture f={0};
 pc02_lease *a=NULL,*b=NULL,*owner=NULL;
 begin_case(name);
 expect(fresh(&f,name,1),"enrolled fixture");
 expect(opened(&f,PC02_SHARED,&a)&&opened(&f,PC02_SHARED,&b),"two shared owners");
 expect(pc02_borrow(a)&&!pc02_close(a),"live native borrow refuses owner close");
 expect(!opened(&f,PC02_OWNER,&owner),"owner cannot pass outstanding shared source");
 expect(pc02_close(b)&&pc02_unborrow(a)&&pc02_close(a),"last native teardown releases shared lease");
 expect(opened(&f,PC02_OWNER,&owner),"owner after last borrow");
 expect(pc02_close(owner),"clean owner close leaves CLEAN");
 end_case(name);
}
static void lock_order_case(unsigned first){
 const char *name=first==PC02_SHARED?"child-shared-before-owner":"child-owner-before-shared";
 fixture f={0};
 child c={0};
 pc02_lease *h=NULL;
 begin_case(name);
 expect(fresh(&f,name,1),"enrolled fixture");
 expect(spawn_child(&f,first,9000,&c),"fresh exec child");
 int at=reached(&c);
 expect(at,"pipe confirms actual first lock");
 if(!at){finish_child(&c,1);
 end_case(name);
 return;
 }
 expect(!opened(&f,first==PC02_SHARED?PC02_OWNER:PC02_SHARED,&h),"opposite lock order refuses actual process");
 expect(finish_child(&c,0),"child actual cleanup terminal");
 expect(opened(&f,PC02_SHARED,&h),"reader after clean owner process closes");
 expect(pc02_close(h),"reader close");
 end_case(name);
}
static void pending_kill_case(unsigned phase){
 char name[64];
 fixture f={0};
 child c={0};
 pc02_lease *h=NULL,*reader=NULL;
 pc02_cap *cap=NULL;
 pc02_pending_record exact,bad;
 pc02_grant grant;
 proof p={"original\n",0};
 snprintf(name,sizeof(name),"process-kill-pending-%u",phase);
 begin_case(name);
 expect(fresh(&f,name,1),"enrolled fixture");
 expect(spawn_child(&f,PC02_OWNER,phase,&c),"fresh pending child");
 int at=reached(&c);
 expect(at,"deterministic real pending barrier");
 if(!at){finish_child(&c,1);
 end_case(name);
 return;
 }
 expect(!opened(&f,PC02_SHARED,&reader),"reader refuses live pending");
 expect(finish_child(&c,1),"SIGKILL actual mutation holder");
 expect(!opened(&f,PC02_SHARED,&reader),"new reader still refuses after owner death");
 expect(opened(&f,PC02_RECOVER,&h)&&pc02_pending(h,&exact),"fresh independent authority exposes exact pending descriptor");
 bad=exact;
 bad.seal[0]=bad.seal[0]=='a'?'b':'a';
 expect(!pc02_resume(h,&bad,&cap)&&!cap,"resealed/old descriptor cannot issue capability");
 expect(pc02_resume(h,&exact,&cap)&&cap,"fresh exact native capability");
 expect(!pc02_close(h),"active capability cannot close or clear pending");
 expect(pc02_finish(h,cap,terminal,exact_proof,&p,&grant)&&p.calls==1,"actual original and terminal proof before recovered CLEAN");
 expect(pc02_close(h),"recovered holder closes");
 expect(opened(&f,PC02_SHARED,&reader),"fresh reader only after proof and Binding");
 expect(pc02_close(reader),"reader close");
 end_case(name);
}
static void stale_case(void){
 const char *name="stale-grants-and-descriptors";
 fixture f={0};
 pc02_lease *h=NULL,*reader=NULL;
 pc02_cap *cap=NULL,*old_cap=NULL;
 pc02_grant old={0},current={0};
 pc02_pending_record first={0},second={0};
 proof p={"original\n",0};
 begin_case(name);
 expect(fresh(&f,name,1)&&opened(&f,PC02_OWNER,&h),"enrolled exclusive holder");
 expect(pc02_grant_get(h,&old)&&pc02_begin(h,manifest,input,&cap)&&pc02_pending(h,&first),"capture first exact pending");
 old_cap=cap;
 expect(pc02_finish(h,cap,terminal,exact_proof,&p,&current)&&current.generation==old.generation+1,"first proven finish");
 expect(pc02_begin(h,manifest,input,&cap)&&pc02_pending(h,&second)&&second.generation==first.generation+1,"second transaction generation");
 expect(!pc02_prepare_publish(h,old_cap),"old capability pointer never aliases the newly issued capability");
 expect(pc02_finish(h,cap,terminal,exact_proof,&p,&current)&&pc02_close(h),"second proven finish");
 h=NULL;
 expect(!pc02_open(f.authority,f.library,PC02_SHARED,&old,NULL,&reader)&&!reader,"old independently held CLEAN grant refuses without another live holder");
 expect(pc02_open(f.authority,f.library,PC02_SHARED,&current,NULL,&reader)&&pc02_close(reader),"exact current authority grant");
 expect(opened(&f,PC02_RECOVER,&h),"fresh explicit recovery object");
 expect(!pc02_resume(h,&first,&cap)&&!cap,"old pending descriptor never reactivates current CLEAN");
 expect(pc02_close(h),"recovery observation close");
 end_case(name);
}
static void lost_finish_case(unsigned phase){
 char name[64],descriptor_path[PATH_BYTES];
 fixture f={0};
 child c={0};
 pc02_lease *h=NULL,*reader=NULL;
 pc02_pending_record exact,bad;
 pc02_grant grant;
 proof p={"published\n",0};
 snprintf(name,sizeof(name),"process-kill-finish-%u",phase);
 begin_case(name);
 expect(fresh(&f,name,1),"enrolled fixture");
 expect(spawn_child(&f,PC02_OWNER,phase,&c),"fresh actual publisher child");
 int at=reached(&c);
 expect(at,"exact native finish barrier");
 if(!at){finish_child(&c,1);
 end_case(name);
 return;
 }
 expect(finish_child(&c,1),"kill actual publisher");
 if(phase<PC02_BINDING_PUBLISHED)expect(!opened(&f,PC02_SHARED,&reader),"CLEAN without independent new Binding refuses reader");
 else expect(opened(&f,PC02_SHARED,&reader)&&pc02_close(reader),"fully readable independently published Binding permits reader");
 strcpy(descriptor_path,f.library);
 strcat(descriptor_path,".producer-descriptor");
 expect(file_read(descriptor_path,&exact,sizeof(exact)),"original producer exact descriptor retained");
 expect(opened(&f,PC02_RECOVER,&h),"fresh lost-finish recovery");
 bad=exact;
 bad.generation++;
 expect(!pc02_reconcile(h,&bad,terminal,exact_proof,&p,&grant),"different generation cannot reconcile");
 expect(!pc02_reconcile(h,&exact,terminal,reject_proof,NULL,&grant),"independent actual proof refusal cannot publish Binding");
 expect(pc02_reconcile(h,&exact,terminal,exact_proof,&p,&grant)&&p.calls==1,"exact original descriptor and actual published proof reconcile");
 expect(pc02_close(h),"reconciled holder close");
 expect(opened(&f,PC02_SHARED,&reader),"reader after independently proven reconciliation");
 expect(pc02_close(reader),"reader close");
 end_case(name);
}
static void enrollment_kill_case(unsigned phase){
 char name[64];
 fixture f={0};
 proof p={"original\n",0};
 pc02_lease *reader=NULL;
 snprintf(name,sizeof(name),"enrollment-process-death-%u",phase);
 begin_case(name);
 expect(fresh(&f,name,0),"unregistered initial fixture");
 int ready[2],go[2];
 expect(!pipe(ready)&&!pipe(go),"enrollment barrier pipes");
 pid_t pid=fork();
 expect(pid>=0,"real enrollment process");
 if(!pid){
  close(ready[0]);
 close(go[1]);
 barrier b={ready[1],go[0],phase};
 pc02_controls controls={&b,at_phase,0,0};
  _exit(pc02_enroll(f.authority,f.library,0,exact_proof,&p,&controls)?0:99);
 }
 close(ready[1]);
 close(go[0]);
 child c={pid,ready[0],go[1]};
 int at=reached(&c);
 expect(at,"actual enrollment barrier");
 if(!at){finish_child(&c,1);
 end_case(name);
 return;
 }
 expect(finish_child(&c,1),"kill explicit enrollment owner");
 expect(!pc02_enroll(f.authority,f.library,0,exact_proof,&p,NULL),"ordinary enrollment never fills partial namespace");
 expect(pc02_recover_enrollment(f.authority,f.library,exact_proof,&p,NULL),"explicit original identity-bound intent recovery");
 expect(opened(&f,PC02_SHARED,&reader),"reader after enrollment recovery actual proof");
 expect(pc02_close(reader),"reader close");
 end_case(name);
}
static void begin_fault_case(unsigned fault){
 char name[64];fixture f={0};pc02_lease *h=NULL,*reader=NULL;pc02_cap *cap=NULL;
 pc02_pending_record exact={0};pc02_grant grant={0};proof p={"original\n",0};
 pc02_controls controls={NULL,NULL,fault,PC02_PENDING_WRITTEN};
 snprintf(name,sizeof(name),"native-begin-fault-%u",fault);begin_case(name);
 expect(fresh(&f,name,1),"enrolled fixture");
 expect(pc02_open(f.authority,f.library,PC02_OWNER,NULL,&controls,&h),"exclusive native fault holder");
 expect(!pc02_begin(h,manifest,input,&cap)&&!cap,"unknown native record result never returns capability");
 expect(pc02_close(h),"close without capability never emits CLEAN");h=NULL;
 expect(!opened(&f,PC02_SHARED,&reader),"unknown BEGIN stays refused after close");
 if(fault==PC02_SHORT_WRITE){
  expect(!opened(&f,PC02_RECOVER,&h)&&!h,"real short-written tail is not silently adopted");
 }else{
  expect(opened(&f,PC02_RECOVER,&h)&&pc02_pending(h,&exact),"fresh process custody observes complete native PENDING");
  expect(pc02_resume(h,&exact,&cap),"fresh resume syncs exact complete PENDING before capability");
  expect(pc02_finish(h,cap,terminal,exact_proof,&p,&grant)&&p.calls==1,"independent original proof precedes recovered CLEAN");
  expect(pc02_close(h),"recovered fault holder closes");
  expect(opened(&f,PC02_SHARED,&reader)&&pc02_close(reader),"new reader after proven recovery");
 }
 end_case(name);
}
static void negative_case(unsigned kind){
 static const char *names[]={"replaced-target","target-hardlink","replaced-state","partial-state","permissive-authority-file","legacy-pending","symlink-library-prefix","replaced-authority","replaced-binding","root-permissions","symlink-authority-ancestor"};
 const char *name=names[kind];
 fixture f={0};
 pc02_lease *h=NULL;
 char path[PATH_BYTES],retained[PATH_BYTES];
 begin_case(name);
 expect(fresh(&f,name,1),"enrolled fixture");
 if(kind==0){strcpy(retained,f.library);
 strcat(retained,".original");
 expect(!rename(f.library,retained)&&file_write(f.library,"original\n",9),"replace target by distinct actual inode");
 }
 if(kind==1){expect(join(path,f.directory,"library-hardlink")&&!link(f.library,path),"actual post-enrollment hardlink");
 }
 if(kind==2||kind==8){
  unsigned char bytes[4096];
 size_t n=kind==2?368:304;
  expect(route_path(&f,kind==2?"state":"binding",path)&&file_read(path,bytes,n),"capture original protected record");
  strcpy(retained,path);
 strcat(retained,".retained");
  expect(!rename(path,retained)&&file_write(path,bytes,n),"replace authority object retaining old bytes");
 }
 if(kind==3){expect(route_path(&f,"state",path),"state path");
 int fd=open(path,O_WRONLY|O_APPEND);
 expect(fd>=0&&write(fd,"x",1)==1&&!fsync(fd),"actual torn suffix");
 if(fd>=0)close(fd);
 }
 if(kind==4){expect(route_path(&f,"binding",path)&&!chmod(path,0644),"actual relaxed authority permissions");
 }
 if(kind==5){strcpy(path,f.library);
 strcat(path,".migration-pending.json");
 expect(file_write(path,"pending",7),"actual legacy pending marker");
 }
 if(kind==6){
  strcpy(retained,f.library);strcat(retained,".regular");
  expect(!rename(f.library,retained)&&!symlink(retained,f.library),"actual library target symlink on the registered route");
 }
 if(kind==7){unsigned char bytes[120];
 expect(join(path,f.authority,"authority")&&file_read(path,bytes,sizeof(bytes)),"capture root anchor");
 strcpy(retained,path);
 strcat(retained,".retained");
 expect(!rename(path,retained)&&file_write(path,bytes,sizeof(bytes)),"replace root anchor inode with same bytes");
 }
 if(kind==9)expect(!chmod(f.authority,0755),"actual nonprivate authority root");
 if(kind==10){
  strcpy(retained,f.directory);strcat(retained,".retained");
  expect(!rename(f.directory,retained)&&!symlink(retained,f.directory),"actual registered authority/library ancestor becomes symlink");
 }
 int admitted=opened(&f,PC02_SHARED,&h);
 expect(!admitted&&!h,"ordinary reader refuses malformed/changed authority before SDK");
 if(admitted)pc02_close(h);
 if(kind==3){expect(!opened(&f,PC02_RECOVER,&h)&&!h,"partial tail is never silently repaired or adopted");
 }
 end_case(name);
}
int main(int argc,char **argv){
 memset(manifest,'a',64);
 manifest[64]=0;
 memset(input,'b',64);
 input[64]=0;
 memset(terminal,'c',64);
 terminal[64]=0;
 if(argc==8&&!strcmp(argv[1],"--child"))return child_main(argc,argv);
 if(argc!=2||!realpath(argv[0],self)||!realpath(argv[1],work)){fputs("usage: posix-c02-admission-check EXISTING_PRIVATE_WORKDIR\n",stderr);
 return 64;
 }
 missing_and_enroll_case();
 create_case();
 borrow_case();
 lock_order_case(PC02_SHARED);
 lock_order_case(PC02_OWNER);
 pending_kill_case(PC02_PENDING_WRITTEN);
 pending_kill_case(PC02_PENDING_DURABLE);
 stale_case();
 lost_finish_case(PC02_CLEAN_DURABLE);
 lost_finish_case(PC02_BINDING_WRITTEN);
 lost_finish_case(PC02_BINDING_PUBLISHED);
 lost_finish_case(PC02_BINDING_DURABLE);
 enrollment_kill_case(PC02_ENROLL_INTENT);
 enrollment_kill_case(PC02_ENROLL_STATE);
 for(unsigned k=1;k<=3;k++)begin_fault_case(k);
 for(unsigned k=0;
 k<11;
 k++)negative_case(k);
 printf("{\"source\":\"%s\",\"cases\":%u,\"checks\":%u,\"failed\":%u,\"passed\":%s,\"native_posix\":true,\"process_kill\":true,\"power_loss\":false,\"actual_sdk\":false,\"host_wiring\":false}\n",SOURCE_SHA,cases,checks,failures,failures?"false":"true");
 return failures?1:0;
}
