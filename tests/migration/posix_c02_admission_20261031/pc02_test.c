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
static int spawn_command(const char *command,const fixture *f,unsigned mode,unsigned phase,child *out){
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
  execl(self,self,command,f->authority,f->library,modes,phases,ready_fd,go_fd,(char *)NULL);
 _exit(91);
 }
 close(ready[1]);
 close(go[0]);
 out->pid=pid;
 out->ready=ready[0];
 out->go=go[1];
 return 1;
}
static int spawn_child(const fixture *f,unsigned mode,unsigned phase,child *out){return spawn_command("--child",f,mode,phase,out);}
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
 pc02_pending_record exact={0},bad;
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
typedef struct {fixture f;
 char context[PATH_BYTES],outside[PATH_BYTES];
 int fd;
 pc02_identity id;
 pc02_scope *scope;
 } scoped_fixture;
static int identity_fd(int fd,pc02_identity *id){
 struct stat s;
 if(fstat(fd,&s))return 0;
 id->device=(uint64_t)s.st_dev;
 id->inode=(uint64_t)s.st_ino;
 return 1;
}
static int scoped_fixture_open(scoped_fixture *s,const char *name,int registered){
 char label[96];
 memset(s,0,sizeof(*s));
 s->fd=-1;
 snprintf(label,sizeof(label),"%02u-%s",++fixture_count,name);
 if(!join(s->f.directory,work,label)||mkdir(s->f.directory,0700)||
    !join(s->outside,s->f.directory,"outside")||mkdir(s->outside,0700))return 0;
 char system[PATH_BYTES];
 if(!join(system,s->f.directory,"trusted-system")||mkdir(system,0770)||chmod(system,0770)||
    !join(s->context,system,"app-container")||mkdir(s->context,0700)||
    !join(s->f.authority,s->context,"authority")||!join(s->f.library,s->context,"library.sqlite"))return 0;
 s->fd=open(s->context,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
 if(s->fd<0||!identity_fd(s->fd,&s->id)||!pc02_scope_create(s->fd,&s->id,&s->scope))return 0;
 if(!registered)return 1;
 proof p={"original\n",0};
 return pc02_authority_create_in(s->scope,"authority")&&file_write(s->f.library,"original\n",9)&&
 pc02_enroll_in(s->scope,"authority","library.sqlite",0,exact_proof,&p,NULL);
}
static void scoped_fixture_close(scoped_fixture *s){
 pc02_scope_close(s->scope);
 s->scope=NULL;
 if(s->fd>=0)close(s->fd);
 s->fd=-1;
}
static int scoped_open(scoped_fixture *s,unsigned mode,pc02_lease **h){
 return pc02_open_in(s->scope,"authority","library.sqlite",mode,NULL,NULL,h);
}
static void scoped_lifetime_case(void){
 const char *name="scope-fd-lifetime-and-sdk-path";
 scoped_fixture s;
 pc02_lease *h=NULL;
 begin_case(name);
 expect(scoped_fixture_open(&s,name,0),"trusted private Context fd under system-style group-writable ancestor");
 expect(!pc02_authority_create(s.f.authority),"default strict Linux behavior still rejects these ancestors");
 expect(pc02_authority_create_in(s.scope,"authority")&&file_write(s.f.library,"original\n",9),"explicit authority inside the trusted fd");
 proof p={"original\n",0};
 expect(pc02_enroll_in(s.scope,"authority","library.sqlite",0,exact_proof,&p,NULL)&&p.calls==1,"scoped actual enrollment proof");
 expect(scoped_open(&s,PC02_SHARED,&h),"scoped registered reader");
 const char *actual=pc02_library_path(h);
 char bytes[9];
 expect(actual&&file_read(actual,bytes,sizeof(bytes))&&!memcmp(bytes,"original\n",9),"checked fd-derived SDK path addresses actual expected object");
 scoped_fixture_close(&s);
 expect(pc02_check(h)&&pc02_borrow(h)&&!pc02_close(h),"lease owns its CLOEXEC scope duplicate after factory closes");
 expect(pc02_unborrow(h)&&pc02_close(h),"last borrowed owner releases scoped lease");
 end_case(name);
}
static void scoped_identity_case(void){
 const char *name="scope-native-identity-and-private-mode";
 scoped_fixture s;
 pc02_scope *bad=NULL;
 begin_case(name);
 expect(scoped_fixture_open(&s,name,0),"private scoped fixture");
 pc02_identity wrong=s.id;
 wrong.inode++;
 expect(!pc02_scope_create(s.fd,&wrong,&bad)&&!bad,"digest or wrong native identity cannot create scope");
 expect(!chmod(s.context,0775)&&!pc02_scope_create(s.fd,&s.id,&bad)&&!bad,"group-writable anchor rejects before path operations");
 expect(!chmod(s.context,0700),"restore fixture permissions");
 char file[PATH_BYTES];
 expect(join(file,s.context,"not-directory")&&file_write(file,"x",1),"actual regular file fd");
 int fd=open(file,O_RDONLY|O_CLOEXEC);
 pc02_identity id={0};
 expect(fd>=0&&identity_fd(fd,&id)&&!pc02_scope_create(fd,&id,&bad)&&!bad,"regular fd never grants Context authority");
 if(fd>=0)close(fd);
 scoped_fixture_close(&s);
 end_case(name);
}
static void scoped_escape_case(void){
 const char *name="scope-relative-path-escape";
 scoped_fixture s;
 pc02_lease *h=NULL;
 begin_case(name);
 expect(scoped_fixture_open(&s,name,1),"registered scoped fixture");
 const char *bad[]={"../escape","/absolute","authority/../escape","authority//escape","authority/.","."};
 proof p={"original\n",0};
 for(unsigned k=0;
 k<sizeof(bad)/sizeof(bad[0]);
 k++){
  expect(!pc02_authority_create_in(s.scope,bad[k]),"authority path cannot escape or normalize ambiguously");
  expect(!pc02_open_in(s.scope,"authority",bad[k],PC02_SHARED,NULL,NULL,&h)&&!h,"library path cannot escape scope");
 }
 expect(!pc02_enroll_in(s.scope,"authority","authority/library.sqlite",1,exact_proof,&p,NULL)&&!p.calls,"authority cannot be reused as library namespace");
 expect(scoped_open(&s,PC02_SHARED,&h)&&pc02_close(h),"original scoped library unchanged after refusals");
 scoped_fixture_close(&s);
 end_case(name);
}
static void scoped_symlink_case(void){
 const char *name="scope-symlink-escape";
 scoped_fixture s;
 pc02_lease *h=NULL;
 begin_case(name);
 expect(scoped_fixture_open(&s,name,1),"registered scoped fixture");
 char linkpath[PATH_BYTES],outside[PATH_BYTES];
 expect(join(linkpath,s.context,"foreign")&&
  join(outside,s.outside,"library.sqlite")&&file_write(outside,"outside\n",8)&&!symlink(s.outside,linkpath),"native link to a distinct private namespace");
 expect(!pc02_authority_create_in(s.scope,"foreign/authority"),"relative authority traversal refuses symlink");
 expect(!pc02_open_in(s.scope,"authority","foreign/library.sqlite",PC02_SHARED,NULL,NULL,&h)&&!h,"relative library traversal refuses symlink");
 char retained[PATH_BYTES];
 expect(join(retained,s.context,"retained.sqlite")&&!rename(s.f.library,retained)&&!symlink(outside,s.f.library),"actual registered target becomes symlink");
 expect(!scoped_open(&s,PC02_SHARED,&h)&&!h,"registered target symlink never opens SDK");
 char bytes[8];
 expect(file_read(outside,bytes,sizeof(bytes))&&!memcmp(bytes,"outside\n",8),"outside object untouched");
 scoped_fixture_close(&s);
 end_case(name);
}
static void scoped_rebind_case(void){
 const char *name="scope-anchor-path-rebinding";
 scoped_fixture s;
 pc02_lease *h=NULL;
 begin_case(name);
 expect(scoped_fixture_open(&s,name,1)&&scoped_open(&s,PC02_SHARED,&h),"live scoped owner");
 char moved[PATH_BYTES];
 size_t n=strlen(s.context);
 expect(n+10<sizeof(moved),"bounded renamed fixture");
 strcpy(moved,s.context);
 strcat(moved,".retained");
 expect(!rename(s.context,moved)&&!mkdir(s.context,0700),"actual context path now names a distinct directory");
 expect(!pc02_check(h)&&!pc02_library_path(h),"old scope ID and SDK path cannot rebind");
 pc02_lease *fresh=NULL;
 expect(!scoped_open(&s,PC02_SHARED,&fresh)&&!fresh,"factory does not adopt replacement context");
 expect(pc02_close(h),"identity refusal does not synthesize CLEAN or delete evidence");
 scoped_fixture_close(&s);
 end_case(name);
}
static void scoped_permission_case(void){
 const char *name="scope-anchor-permission-drift";
 scoped_fixture s;
 pc02_lease *h=NULL;
 begin_case(name);
 expect(scoped_fixture_open(&s,name,1)&&scoped_open(&s,PC02_SHARED,&h),"live private Context scope");
 expect(!chmod(s.context,0755),"actual anchor permission drift");
 expect(!pc02_check(h)&&!pc02_library_path(h),"scope captured-mode drift refuses checked SDK path");
 pc02_lease *fresh=NULL;
 expect(!scoped_open(&s,PC02_SHARED,&fresh)&&!fresh,"no implicit broader-scope adoption");
 expect(pc02_close(h)&&!chmod(s.context,0700),"close only releases lifetime; restore test fixture");
 expect(scoped_open(&s,PC02_SHARED,&fresh)&&pc02_close(fresh),"exact unchanged authority works after explicit mode restoration");
 scoped_fixture_close(&s);
 end_case(name);
}
static int scoped_child_main(int argc,char **argv){
 unsigned long long device=0,inode=0;
 char tail;
 if(argc!=8||strlen(argv[3])!=32||sscanf(argv[3],"%16llx%16llx%c",&device,&inode,&tail)!=2)return 71;
 int fd=open(argv[2],O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
 pc02_scope *scope=NULL;
 pc02_identity expected={(uint64_t)device,(uint64_t)inode};
 pc02_lease *h=NULL;
 pc02_cap *cap=NULL;
 barrier b={atoi(argv[6]),atoi(argv[7]),(unsigned)strtoul(argv[5],NULL,10)};
 pc02_controls controls={&b,at_phase,0,0};
 proof p={"original\n",0};
 pc02_grant grant={0};
 if(fd<0||!pc02_scope_create(fd,&expected,&scope))return 72;
 close(fd);
 if(!pc02_open_in(scope,"authority","library.sqlite",PC02_OWNER,NULL,&controls,&h))return 73;
 pc02_scope_close(scope);
 if(!pc02_begin(h,manifest,input,&cap))return 74;
 if(!pc02_finish(h,cap,terminal,exact_proof,&p,&grant))return 75;
 return pc02_close(h)?0:76;
}
static void scoped_pending_case(void){
 const char *name="scope-process-death-and-exact-recovery";
 scoped_fixture s;
 pc02_lease *h=NULL,*reader=NULL;
 pc02_cap *cap=NULL;
 pc02_pending_record exact={0},bad={0};
 pc02_grant grant={0};
 proof p={"original\n",0};
 child c={0};
 begin_case(name);
 expect(scoped_fixture_open(&s,name,1),"registered private context");
 fixture args={0};
 strcpy(args.authority,s.context);
 snprintf(args.library,sizeof(args.library),"%016llx%016llx",(unsigned long long)s.id.device,(unsigned long long)s.id.inode);
 expect(spawn_command("--scope-child",&args,PC02_OWNER,PC02_PENDING_DURABLE,&c),"fresh exec in fixed trusted Context");
 int at=reached(&c);
 expect(at,"scoped native durable PENDING barrier");
 if(!at){finish_child(&c,1);
 scoped_fixture_close(&s);
 end_case(name);
 return;
 }
 expect(!scoped_open(&s,PC02_SHARED,&reader),"scoped reader refuses live migration");
 expect(finish_child(&c,1),"kill actual scoped holder");
 expect(!scoped_open(&s,PC02_SHARED,&reader),"persistent scoped PENDING after process death");
 expect(scoped_open(&s,PC02_RECOVER,&h)&&pc02_pending(h,&exact),"fresh scoped exact descriptor");
 bad=exact;
 bad.generation++;
 expect(!pc02_resume(h,&bad,&cap)&&!cap,"stale scoped recovery descriptor refuses");
 expect(pc02_resume(h,&exact,&cap)&&pc02_finish(h,cap,terminal,exact_proof,&p,&grant)&&p.calls==1,"actual original proof before scoped CLEAN");
 expect(pc02_close(h)&&scoped_open(&s,PC02_SHARED,&reader)&&pc02_close(reader),"new scoped reader after independent finish");
 scoped_fixture_close(&s);
 end_case(name);
}
static void scoped_readonly_mode_case(unsigned mode){
 char name[80];scoped_fixture s;pc02_lease *h=NULL;struct stat st;
 snprintf(name,sizeof(name),"scope-readonly-anchor-%04o",mode);begin_case(name);
 expect(scoped_fixture_open(&s,name,0),"fresh private fixture before trusted factory");
 pc02_scope_close(s.scope);s.scope=NULL;
 expect(!chmod(s.context,(mode_t)mode)&&pc02_scope_create(s.fd,&s.id,&s.scope),"factory accepts euid-owned anchor without group/other write");
 proof p={"original\n",0};
 expect(pc02_authority_create_in(s.scope,"authority")&&file_write(s.f.library,"original\n",9)&&
  pc02_enroll_in(s.scope,"authority","library.sqlite",0,exact_proof,&p,NULL),"actual scoped authority and library enrollment");
 expect(!stat(s.f.authority,&st)&&(st.st_mode&07777)==0700,"authority remains strictly private");
 expect(scoped_open(&s,PC02_SHARED,&h)&&pc02_check(h)&&pc02_library_path(h),"actual reader under captured readonly/traverse anchor");
 expect(!chmod(s.context,mode==0755?0711:0755)&&!pc02_check(h)&&!pc02_library_path(h),"safe-to-safe mode drift still refuses existing scope");
 expect(pc02_close(h),"mode drift only releases the owner");
 pc02_lease *fresh=NULL;
 expect(!scoped_open(&s,PC02_SHARED,&fresh)&&!fresh,"factory scope cannot silently adopt mode change");
 expect(!chmod(s.context,(mode_t)mode)&&scoped_open(&s,PC02_SHARED,&fresh)&&pc02_close(fresh),"exact captured mode restoration retains original authority");
 scoped_fixture_close(&s);end_case(name);
}
static void scoped_write_mode_case(void){
 const char *name="scope-group-other-write-rejected";scoped_fixture s;
 begin_case(name);expect(scoped_fixture_open(&s,name,0),"private anchor fixture");
 unsigned modes[]={0775,0702,0777};
 for(unsigned k=0;k<sizeof(modes)/sizeof(modes[0]);k++){
  pc02_scope *bad=NULL;
  expect(!chmod(s.context,(mode_t)modes[k])&&!pc02_scope_create(s.fd,&s.id,&bad)&&!bad,"trusted native ID cannot authorize group/other writable anchor");
 }
 expect(!chmod(s.context,0700),"restore only this test fixture");
 scoped_fixture_close(&s);end_case(name);
}
static int scoped_cases_main(void){
 scoped_lifetime_case();
 scoped_identity_case();
 scoped_escape_case();
 scoped_symlink_case();
 scoped_rebind_case();
 scoped_permission_case();
 scoped_pending_case();
 scoped_readonly_mode_case(0755);
 scoped_readonly_mode_case(0711);
 scoped_write_mode_case();
 printf("{\"source\":\"%s\",\"cases\":%u,\"checks\":%u,\"failed\":%u,\"passed\":%s,\"native_posix\":true,\"scoped\":true,\"process_kill\":true,\"power_loss\":false,\"actual_sdk\":false,\"host_wiring\":false}\n",SOURCE_SHA,cases,checks,failures,failures?"false":"true");
 return failures?1:0;
}
#include "../posix_c02_migration_20261031/native_api_cases.inc"
int main(int argc,char **argv){
 memset(manifest,'a',64);
 manifest[64]=0;
 memset(input,'b',64);
 input[64]=0;
 memset(terminal,'c',64);
 terminal[64]=0;
 if(argc==8&&!strcmp(argv[1],"--child"))return child_main(argc,argv);
 if(argc==8&&!strcmp(argv[1],"--scope-child"))return scoped_child_main(argc,argv);
 if(argc==8&&!strcmp(argv[1],"--migration-child"))return native_publish_child(argc,argv);
 if(argc==8&&!strcmp(argv[1],"--floor-child"))return native_floor_child(argc,argv);
 if(argc==3&&!strcmp(argv[1],"--migration-cases")){
  if(!realpath(argv[0],self)||!realpath(argv[2],work))return 64;
  return native_migration_cases_main();
 }
 if(argc==3&&!strcmp(argv[1],"--scope-cases")){
  if(!realpath(argv[0],self)||!realpath(argv[2],work))return 64;
  return scoped_cases_main();
 }
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
