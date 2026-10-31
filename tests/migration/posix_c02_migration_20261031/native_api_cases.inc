/* SPDX-License-Identifier: MIT */
/* Included by pc02_test.c. Native bytes only: no SDK qualification claim. */
#define PC02_NATIVE_API_HEAD_CONFIRM_SNAPSHOTS 1
typedef struct {
 fixture f;
 pc02_lease *h;
 pc02_cap *cap;
 pc02_pending_record pending;
 pc02_member members[2];
 char input_sha[65];
} native_tx;
static int nt_id(const char *path,pc02_identity *id){
 int fd=open(path,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
 int ok=fd>=0&&identity_fd(fd,id);
 if(fd>=0&&close(fd))ok=0;
 return ok;
}
static int nt_path(native_tx *t,const char *leaf,char out[PATH_BYTES]){return join(out,t->f.directory,leaf);
}
static int nt_content(int fd,const char *expected){
 struct stat st;
 char bytes[64];
 size_t size=strlen(expected);
 return fd>=0&&size<=sizeof(bytes)&&!fstat(fd,&st)&&st.st_size==(off_t)size&&
 pread(fd,bytes,size,0)==(ssize_t)size&&!memcmp(bytes,expected,size);
}
static int nt_native_proof(void *context,const char *path,int fd,const pc02_pending_record *pending,const char *end){
 native_tx *t=context;
 (void)path;
 return pending&&pending->generation==t->pending.generation&&!strcmp(pending->seal,t->pending.seal)&&
 !strcmp(pending->manifest,manifest)&&!strcmp(pending->input,t->input_sha)&&end&&!strcmp(end,terminal)&&nt_content(fd,"published\n");
}
static int nt_member_proof(void *context,int original,int prepared){
 const pc02_member *m=context;
 if(!strcmp(m->target,"library.sqlite"))return nt_content(original,"original\n")&&nt_content(prepared,"published\n");
 return (m->original_present?nt_content(original,"old mirror\n"):original==-1)&&nt_content(prepared,"new mirror\n");
}
static int nt_reject_member(void *context,int original,int prepared){(void)context;
(void)original;
(void)prepared;
return 0;
}
static int nt_start(native_tx *t,const fixture *f,const pc02_controls *controls,int mirror_present){
 char path[PATH_BYTES];
 pc02_metadata_info info;
 char sha[65];
 memset(t,0,sizeof(*t));
 t->f=*f;
 if(!pc02_open(f->authority,f->library,PC02_OWNER,NULL,controls,&t->h))return 0;
 pc02_member *db=&t->members[0],*mirror=&t->members[1];
 strcpy(db->target,"library.sqlite");
 strcpy(db->stage,"private.sqlite");
 strcpy(db->retained,"retained.sqlite");
 db->original_present=1;
 if(!nt_id(f->library,&db->original)||!nt_path(t,db->stage,path)||!file_write(path,"published\n",10)||!nt_id(path,&db->prepared))return 0;
 strcpy(mirror->target,"library.sqlite.legacy-map.json");
 strcpy(mirror->stage,"private-mirror.json");
 strcpy(mirror->retained,"retained-mirror.json");
 mirror->original_present=mirror_present;
 if(mirror_present){
  if(!nt_path(t,mirror->target,path)||!file_write(path,"old mirror\n",11)||!nt_id(path,&mirror->original))return 0;
 }
 if(!nt_path(t,mirror->stage,path)||!file_write(path,"new mirror\n",11)||!nt_id(path,&mirror->prepared))return 0;
 if(!pc02_metadata_write(t->h,PC02_META_INPUT,NULL,t->members,sizeof(t->members),t->input_sha,&info)||
    !pc02_begin(t->h,manifest,t->input_sha,&t->cap)||!pc02_pending(t->h,&t->pending)||
    !pc02_metadata_write(t->h,PC02_META_PREPARED,t->cap,t->members,sizeof(t->members),sha,&info))return 0;
 return 1;
}
static int nt_fresh(native_tx *t,const char *name,int mirror){
 fixture f={0};
 return fresh(&f,name,1)&&nt_start(t,&f,NULL,mirror);
}
static void nt_abandon(native_tx *t){
 pc02_lease *reader=NULL;
 expect(pc02_abandon(t->h,t->cap)&&!pc02_cap_check(t->h,t->cap)&&pc02_close(t->h),"explicit abandonment releases only memory and handles");
 t->h=NULL;
 t->cap=NULL;
 expect(!opened(&t->f,PC02_SHARED,&reader)&&!reader,"original native PENDING survives abandonment");
}
static void native_metadata_case(void){
 const char *name="native-immutable-input-prepared-and-borrow";
 native_tx t;
 pc02_metadata_info info;
 size_t n=0;
 pc02_member readback[2];
 pc02_pending_record wrong;
 char sha[65];
 begin_case(name);
 expect(nt_fresh(&t,name,1),"actual INPUT/PENDING/PREPARED objects");
 expect(pc02_metadata_read(t.h,PC02_META_INPUT,&t.pending,readback,sizeof(readback),&n,&info)==1&&
  n==sizeof(t.members)&&!memcmp(readback,t.members,n)&&!strcmp(info.payload_sha256,t.input_sha),"registered immutable INPUT exact bytes and native identity");
 wrong=t.pending;
 wrong.generation++;
 expect(pc02_metadata_read(t.h,PC02_META_INPUT,&wrong,readback,sizeof(readback),&n,&info)==-1,"different exact descriptor never adopts INPUT");
 expect(pc02_metadata_read(t.h,PC02_META_PREPARED,&t.pending,readback,sizeof(readback),&n,&info)==1&&
  n==sizeof(t.members)&&!memcmp(readback,t.members,n),"PREPARED remains bound to original INPUT and pending seal");
 expect(pc02_borrow(t.h)&&!pc02_prepare_publish(t.h,t.cap)&&!pc02_abandon(t.h,t.cap)&&
  !pc02_metadata_write(t.h,PC02_META_PREPARED,t.cap,"x",1,sha,&info),"all native mutation/failure release waits for last borrow");
 expect(pc02_unborrow(t.h),"last source closes");
 nt_abandon(&t);
 end_case(name);
}
static void native_metadata_negative(unsigned kind){
 const char *names[]={"native-input-inode-replacement","native-input-complete-tail","native-input-permission-change"};
 const char *name=names[kind];
 native_tx t;
 char leaf[128],path[PATH_BYTES],retained[PATH_BYTES];
 unsigned char bytes[4096];
 pc02_member data[2];
 size_t n=0;
 pc02_metadata_info info;
 begin_case(name);
 expect(nt_fresh(&t,name,0),"actual prepared transaction");
 snprintf(leaf,sizeof(leaf),"input-%016llx-%s",(unsigned long long)t.pending.generation,t.input_sha);
 expect(route_path(&t.f,leaf,path),"original registered INPUT path");
 if(kind==0){
  struct stat st;
  expect(!stat(path,&st)&&st.st_size>0&&st.st_size<=(off_t)sizeof(bytes),"bounded actual envelope");
  n=(size_t)st.st_size;
  expect(file_read(path,bytes,n),"capture all original bytes");
  strcpy(retained,path);
  strcat(retained,".retained");
  expect(!rename(path,retained)&&file_write(path,bytes,n),"replace object retaining complete original and its native ID");
 }else if(kind==1){
  int fd=open(path,O_WRONLY|O_APPEND|O_CLOEXEC);
  expect(fd>=0&&write(fd,"x",1)==1&&!fsync(fd),"append contradictory complete tail without deleting prefix");
  if(fd>=0)close(fd);
 }else expect(!chmod(path,0644),"actual relaxed metadata permission");
 expect(pc02_metadata_read(t.h,PC02_META_INPUT,&t.pending,data,sizeof(data),&n,&info)==-1,"changed complete metadata refuses without fallback");
 nt_abandon(&t);
 end_case(name);
}
static int nt_floor(native_tx *t,unsigned count,pc02_floor *floor){
 if(!pc02_floor_read(t->h,&t->pending,floor))return 0;
 for(unsigned k=0;k<count;k++){char text[64],sha[65];
 snprintf(text,sizeof(text),"actual-line-%u",k+1);
 wh_sha256_hex(text,strlen(text),sha);
  pc02_floor next;
  if(!pc02_floor_advance(t->h,t->cap,floor,sha,&next))return 0;
  *floor=next;
 }
 return 1;
}
static void native_floor_case(void){
 const char *name="native-floor-cas-head-and-temp";
 native_tx t;
 pc02_floor first,current,next;
 char sha[65],path[PATH_BYTES];
 begin_case(name);
 expect(nt_fresh(&t,name,0),"actual private journal descriptor");
 expect(nt_floor(&t,1,&first)&&first.count==1,"first immutable floor and independent head durable");
 current=first;
 wh_sha256_hex("second actual line",18,sha);
 expect(pc02_floor_advance(t.h,t.cap,&current,sha,&next)&&next.count==2,"strict next floor");
 expect(!pc02_floor_advance(t.h,t.cap,&first,sha,&current),"old expected floor never upgrades implicitly");
 expect(route_path(&t.f,".metadata-uncommitted-fixture",path)&&file_write(path,"partial",7),"preserve real uncommitted temp");
 expect(pc02_floor_read(t.h,&t.pending,&current)&&current.count==2&&!strcmp(current.chain_sha256,next.chain_sha256),"temp never becomes a committed floor");
 nt_abandon(&t);
 end_case(name);
}
static void native_floor_negative(unsigned kind){
 const char *names[]={"native-floor-hole","native-floor-last-rollback","native-floor-inode-replacement","native-floor-complete-tail","native-floor-noncanonical-name"};
 const char *name=names[kind];
 native_tx t;
 pc02_floor floor;
 char leaf[128],path[PATH_BYTES],retained[PATH_BYTES];
 begin_case(name);
 expect(nt_fresh(&t,name,0)&&nt_floor(&t,kind==1?1:3,&floor),"actual committed floors and head");
 unsigned slot=kind==1?1:(kind==0?2:3);
 snprintf(leaf,sizeof(leaf),"floor-%016llx-%03u",(unsigned long long)t.pending.generation,slot);
 expect(route_path(&t.f,leaf,path),"actual floor path");
 if(kind<=2){
  char saved[128];
  snprintf(saved,sizeof(saved),".retained-floor-%03u",slot);
  expect(route_path(&t.f,saved,retained)&&!rename(path,retained),"retain original exact floor object");
  if(kind==2){unsigned char bytes[2048];
  struct stat st;
  expect(!stat(retained,&st)&&st.st_size>0&&st.st_size<=(off_t)sizeof(bytes)&&
   file_read(retained,bytes,(size_t)st.st_size)&&file_write(path,bytes,(size_t)st.st_size),"same bytes under distinct native ID cannot replace floor");
   }
 }else if(kind==3){
  int fd=open(path,O_WRONLY|O_APPEND|O_CLOEXEC);
  expect(fd>=0&&write(fd,"x",1)==1&&!fsync(fd),"contradictory complete floor bytes retained");
  if(fd>=0)close(fd);
 }else{strcat(path,"x");
 expect(file_write(path,"x",1),"actual noncanonical final name");
 }
 expect(!pc02_floor_read(t.h,&t.pending,&floor),"hole/rollback/rebinding/complete contradiction never becomes older valid floor");
 nt_abandon(&t);
 end_case(name);
}
static void native_members_case(int mirror){
 const char *name=mirror?"native-two-members-original-mirror":"native-two-members-absent-mirror";
 native_tx t;
 unsigned state=99;
 pc02_grant grant;
 begin_case(name);
 expect(nt_fresh(&t,name,mirror),"actual original and reserved private members");
 expect(pc02_member_observe(t.h,&t.members[0],&state)&&state==0,"original database native identity");
 expect(pc02_prepare_publish(t.h,t.cap),"all SDK borrows closed before publication");
 expect(!pc02_member_publish(t.h,t.cap,&t.members[0],nt_reject_member,NULL)&&
  pc02_member_observe(t.h,&t.members[0],&state)&&state==0,"proof refusal leaves original and stage untouched");
 expect(pc02_member_publish(t.h,t.cap,&t.members[0],nt_member_proof,&t.members[0])&&
  pc02_member_observe(t.h,&t.members[0],&state)&&state==2,"database published with original actual inode retained");
 expect(pc02_member_publish(t.h,t.cap,&t.members[1],nt_member_proof,&t.members[1])&&
  pc02_member_observe(t.h,&t.members[1],&state)&&state==2,"mirror published with exact original-present contract");
 expect(pc02_finish(t.h,t.cap,terminal,nt_native_proof,&t,&grant),"independent native content proof before CLEAN");
 pc02_member reread[2];
 size_t size=0;
 pc02_metadata_info meta;
 int clean=0;
 pc02_pending_record exact;
 expect(pc02_descriptor(t.h,&exact,&clean)&&clean&&pc02_metadata_read(t.h,PC02_META_PREPARED,&exact,reread,sizeof(reread),&size,&meta)==1&&
  size==sizeof(t.members)&&!memcmp(reread,t.members,size),"immutable PREPARED still binds original B after actual Binding replacement");
 expect(pc02_close(t.h),"terminal actual native owner closes");
 pc02_lease *reader=NULL;
 expect(opened(&t.f,PC02_SHARED,&reader)&&pc02_close(reader),"fresh registered reader after both members");
 end_case(name);
}
static int native_publish_child(int argc,char **argv){
 if(argc!=8)return 61;
 fixture f={0};
 native_tx t;
 pc02_grant grant;
 strcpy(f.authority,argv[2]);
 strcpy(f.library,argv[3]);
 strcpy(f.directory,argv[3]);
 char *slash=strrchr(f.directory,'/');
 if(!slash)return 62;
 *slash=0;
 barrier b={atoi(argv[6]),atoi(argv[7]),(unsigned)strtoul(argv[5],NULL,10)};
 pc02_controls control={&b,at_phase,0,0};
 if(!nt_start(&t,&f,&control,0)||!pc02_prepare_publish(t.h,t.cap)||
    !pc02_member_publish(t.h,t.cap,&t.members[0],nt_member_proof,&t.members[0]))return 63;
 if(!pc02_member_publish(t.h,t.cap,&t.members[1],nt_member_proof,&t.members[1])||
    !pc02_finish(t.h,t.cap,terminal,nt_native_proof,&t,&grant)||!pc02_close(t.h))return 65;
 return 0;
}
static void native_member_kill_case(unsigned phase){
 char name[80];
 fixture f={0};
 child c={0};
 native_tx t;
 pc02_metadata_info info;
 size_t n=0;
 int clean=0;
 unsigned state=99;
 snprintf(name,sizeof(name),"native-member-process-kill-%u",phase);
 begin_case(name);
 expect(fresh(&f,name,1)&&spawn_command("--migration-child",&f,PC02_OWNER,phase,&c),"fresh actual publisher process");
 int at=reached(&c);
 expect(at,"exact native rename barrier");
 if(!at){finish_child(&c,1);
 end_case(name);
 return;
 }
 expect(finish_child(&c,1),"SIGKILL after native rename");
 pc02_lease *reader=NULL;
 expect(!opened(&f,PC02_SHARED,&reader)&&!reader,"PENDING persists after actual process death");
 memset(&t,0,sizeof(t));
 t.f=f;
 expect(opened(&f,PC02_RECOVER,&t.h)&&pc02_descriptor(t.h,&t.pending,&clean)&&!clean,"fresh authority exact B descriptor");
 strcpy(t.input_sha,t.pending.input);
 expect(pc02_metadata_read(t.h,PC02_META_INPUT,&t.pending,t.members,sizeof(t.members),&n,&info)==1&&n==sizeof(t.members),"original immutable member identities recovered from actual authority bytes");
 expect(pc02_member_observe(t.h,&t.members[0],&state)&&state==(phase==1301?1u:2u),"native interrupted member state is exact");
 pc02_grant grant;
 expect(pc02_resume(t.h,&t.pending,&t.cap)&&pc02_prepare_publish(t.h,t.cap)&&
  pc02_member_publish(t.h,t.cap,&t.members[0],nt_member_proof,&t.members[0])&&
  pc02_member_publish(t.h,t.cap,&t.members[1],nt_member_proof,&t.members[1]),"synchronous recovery preserves both original IDs and publishes exact stages");
 expect(pc02_finish(t.h,t.cap,terminal,nt_native_proof,&t,&grant)&&pc02_close(t.h),"new independent content proof before recovered CLEAN");
 expect(opened(&f,PC02_SHARED,&reader)&&pc02_close(reader),"new reader after exact recovery");
 end_case(name);
}
static void native_head_negative(unsigned kind){
 const char *name=kind?"native-head-complete-contradictory-tail":"native-head-inode-replacement";
 native_tx t;
 pc02_floor floor;
 char leaf[128],path[PATH_BYTES],retained[PATH_BYTES];
 begin_case(name);
 expect(nt_fresh(&t,name,0)&&nt_floor(&t,1,&floor),"actual INPUT registered committed head");
 snprintf(leaf,sizeof(leaf),"commit-head-%016llx-%s",(unsigned long long)t.pending.generation,t.input_sha);
 expect(route_path(&t.f,leaf,path),"independent committed head path");
 if(!kind){
  unsigned char bytes[2048];
  struct stat st;
  strcpy(retained,path);
  strcat(retained,".retained");
  expect(!stat(path,&st)&&st.st_size>0&&st.st_size<=(off_t)sizeof(bytes)&&file_read(path,bytes,(size_t)st.st_size)&&
   !rename(path,retained)&&file_write(path,bytes,(size_t)st.st_size),"same head bytes cannot replace INPUT registered native ID");
 }else{
  int fd=open(path,O_WRONLY|O_APPEND|O_CLOEXEC);
  expect(fd>=0&&write(fd,"x",1)==1&&!fsync(fd),"keep exact complete original prefix and contradictory suffix");
  if(fd>=0)close(fd);
 }
 expect(!pc02_floor_read(t.h,&t.pending,&floor),"changed or torn committed head never downgrades floor");
 nt_abandon(&t);
 end_case(name);
}
typedef struct {barrier wait;unsigned published;} native_floor_barrier;
static void native_floor_pause(void *context,unsigned phase){
 native_floor_barrier *b=context;
 if(phase==1402&&++b->published==3)at_phase(&b->wait,phase);
}
static int native_floor_child(int argc,char **argv){
 if(argc!=8)return 66;
 fixture f={0};
 native_tx t;
 pc02_floor floor;
 strcpy(f.authority,argv[2]);
 strcpy(f.library,argv[3]);
 strcpy(f.directory,argv[3]);
 char *slash=strrchr(f.directory,'/');
 if(!slash)return 67;
 *slash=0;
 native_floor_barrier b={{atoi(argv[6]),atoi(argv[7]),1402},0};
 pc02_controls controls={&b,native_floor_pause,0,0};
 if(!nt_start(&t,&f,&controls,0)||!nt_floor(&t,1,&floor))return 68;
 return pc02_abandon(t.h,t.cap)&&pc02_close(t.h)?0:69;
}
/* Separate original-source fd observations; retained copies have their own IDs. */
static int nt_capture_head(const fixture *f,const char *leaf,const char *label,struct stat *out){
 char path[PATH_BYTES],raw_path[PATH_BYTES],json_path[PATH_BYTES],raw_leaf[80],json_leaf[80];
 unsigned char bytes[1024];
 char hash[65],record[1024];
 struct stat first={0},after={0};
 int fd=-1,ok=0,n;
 size_t got=0,size=0;
 if(!route_path(f,leaf,path)||snprintf(raw_leaf,sizeof(raw_leaf),"head-%s.raw",label)>=(int)sizeof(raw_leaf)||
    snprintf(json_leaf,sizeof(json_leaf),"head-%s.json",label)>=(int)sizeof(json_leaf)||
    !join(raw_path,f->directory,raw_leaf)||!join(json_path,f->directory,json_leaf))return 0;
 fd=open(path,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
 if(fd<0)return 0;
 ok=!fstat(fd,&first)&&S_ISREG(first.st_mode)&&first.st_uid==geteuid()&&first.st_nlink==1&&
    (first.st_mode&07777)==0600&&first.st_size>=464&&first.st_size<=(off_t)sizeof(bytes);
 if(ok)size=(size_t)first.st_size;
 while(ok&&got<size){
  ssize_t amount=pread(fd,bytes+got,size-got,(off_t)got);
  if(amount<0&&errno==EINTR)continue;
  if(amount<=0){ok=0;break;}
  got+=(size_t)amount;
 }
 if(ok)ok=!fstat(fd,&after)&&first.st_dev==after.st_dev&&first.st_ino==after.st_ino&&
          first.st_size==after.st_size&&first.st_mode==after.st_mode&&first.st_uid==after.st_uid&&
          first.st_nlink==after.st_nlink;
 if(close(fd))ok=0;
 if(!ok)return 0;
 wh_sha256_hex(bytes,size,hash);
 n=snprintf(record,sizeof(record),
  "{\"schema\":\"pc02-head-confirm-snapshot-v1\",\"source_head_name\":\"%s\",\"method\":\"fstat\","
  "\"device\":%llu,\"inode\":%llu,\"mode\":%u,\"uid\":%llu,\"gid\":%llu,\"links\":%llu,\"bytes\":%llu,\"sha256\":\"%s\"}\n",
  leaf,(unsigned long long)(uint64_t)first.st_dev,(unsigned long long)(uint64_t)first.st_ino,
  (unsigned)first.st_mode,(unsigned long long)first.st_uid,(unsigned long long)first.st_gid,
  (unsigned long long)first.st_nlink,(unsigned long long)size,hash);
 if(n<0||(size_t)n>=sizeof(record)||!file_write(raw_path,bytes,size)||!file_write(json_path,record,(size_t)n))return 0;
 *out=first;
 return 1;
}
static void native_floor_confirm_case(void){
 const char *name="native-floor-confirm-process-kill";
 fixture f={0};
 child c={0};
 native_tx t;
 pc02_floor floor={0},wrong={0},after={0};
 char leaf[128],path[PATH_BYTES];
 struct stat before={0},confirmed={0};
 int clean=0;
 begin_case(name);
 expect(fresh(&f,name,1)&&spawn_command("--floor-child",&f,PC02_OWNER,1402,&c),"fresh floor publisher process");
 int at=reached(&c);
 expect(at,"complete immutable floor published before any head record");
 if(!at){finish_child(&c,1);end_case(name);return;}
 expect(finish_child(&c,1),"real kill preserves complete floor and shorter valid head");
 memset(&t,0,sizeof(t));
 t.f=f;
 expect(opened(&f,PC02_RECOVER,&t.h)&&pc02_descriptor(t.h,&t.pending,&clean)&&!clean&&
  pc02_floor_read(t.h,&t.pending,&floor)&&floor.count==1,"fresh owner includes complete floor without downgrading its tip");
 snprintf(leaf,sizeof(leaf),"commit-head-%016llx-%s",(unsigned long long)t.pending.generation,t.pending.input);
 expect(route_path(&f,leaf,path)&&nt_capture_head(&f,leaf,"before-confirm",&before)&&before.st_size==464,"original registered head has exactly its durable initial header");
 expect(pc02_resume(t.h,&t.pending,&t.cap),"only exact fresh pending capability can confirm");
 wrong=floor;
 wrong.count=0;
 expect(!pc02_floor_confirm(t.h,t.cap,&wrong),"old expected count never auto-upgrades or appends");
 expect(pc02_floor_confirm(t.h,t.cap,&floor)&&pc02_floor_read(t.h,&t.pending,&after)&&
  after.count==floor.count&&!strcmp(after.chain_sha256,floor.chain_sha256),"exact confirmation fills head without adding or replacing any floor");
 expect(nt_capture_head(&f,leaf,"after-confirm",&confirmed)&&confirmed.st_size==736&&confirmed.st_dev==before.st_dev&&confirmed.st_ino==before.st_ino,"same registered head now includes exactly one canonical actual record");
 nt_abandon(&t);
 end_case(name);
}
static int native_migration_cases_main(void){
 native_metadata_case();
 for(unsigned k=0;k<3;k++)native_metadata_negative(k);
 native_floor_case();
 for(unsigned k=0;k<5;k++)native_floor_negative(k);
 native_floor_confirm_case();
 native_head_negative(0);
 native_head_negative(1);
 native_members_case(0);
 native_members_case(1);
 native_member_kill_case(1301);
 native_member_kill_case(1302);
 printf("{\"source\":\"%s\",\"cases\":%u,\"checks\":%u,\"failed\":%u,\"passed\":%s,\"native_posix\":true,\"migration_api\":true,\"process_kill\":true,\"power_loss\":false,\"actual_sdk\":false,\"host_wiring\":false}\n",
 SOURCE_SHA,cases,checks,failures,failures?"false":"true");
 return failures?1:0;
}
