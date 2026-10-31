/* SPDX-License-Identifier: MIT */
#define _GNU_SOURCE 1
#define _DARWIN_C_SOURCE 1
#include "pc02_io.h"
#include "pc02_journal.h"
#include "pc02_transform.h"
#include "pc02_build.h"
#include <exr_pc02_sdk.h>
#include "../../src/lm.h"
#include <sys/stat.h>
#ifdef __APPLE__
#include <sys/mount.h>
#include <sys/random.h>
#else
#include <sys/vfs.h>
#endif
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef __APPLE__
#include <mach-o/dyld.h>
#endif
#define P2_PATH 4096
typedef struct {
 char magic[8];
 wh_binding binding;
 wh_gates gates;
 char library[P2_PATH],pack[P2_PATH],authority[P2_PATH],token[49];
 char stages[2][64],retained[2][64],journal[64],pack_copy[64];
 pc02_file original,mirror,source_pack,private_pack;
 unsigned char staged[2][16],journal_identity[16],original_grant[88],mirror_present,allow_partial;
}
p2_input;
typedef struct {char magic[8],input_sha[65];
pc02_file files[2];
}
p2_prepared;
_Static_assert(sizeof(pc02_file)==89&&sizeof(wh_binding)==296&&sizeof(wh_gates)==325,"frozen wire field sizes");
_Static_assert(sizeof(p2_input)==13844&&sizeof(p2_prepared)==251,"canonical provider payload sizes");
typedef struct {
 p2_input input;
 p2_prepared prepared;
 pc02_lease *lease;
 pc02_cap *cap;
 pc02_pending_record pending;
 pc02_journal journal;
 pc02_controls controls;
 int parent,pack,original,mirror,stages[2];
 char parent_path[P2_PATH],stage_path[2][P2_PATH],pack_path[P2_PATH],mirror_path[P2_PATH],mirror_leaf[256];
 int recovered,has_prepared,publish_intent,published,aborted,clean,repair_schema;
 const char *repair_library,*repair_authority;
 size_t initial_count;
 unsigned member;
 const char *operation;
}
p2_owner;
static void phase(void *context,unsigned point){
 p2_owner *o=context;
 (void)o;
 (void)point;
#ifdef PC02_MIGRATION_TEST_CONTROLS
 const char *want=getenv("EXR_PC02_PHASE"),*seq=getenv("EXR_PC02_SEQUENCE"),*member=getenv("EXR_PC02_MEMBER");
 const char *ready=getenv("EXR_PC02_READY_FD"),*go=getenv("EXR_PC02_GO_FD");
 const char *need_cap=getenv("EXR_PC02_REQUIRE_CAP");
 if(need_cap&&!o->cap)return;
 if(!want||!ready||!go||strtoul(want,NULL,10)!=point||
    (seq&&strtoull(seq,NULL,10)!=o->journal.tip.line_count)||(member&&strtoul(member,NULL,10)!=o->member))return;
 char value='r';
 printf("{\"barrier\":%u,\"sequence\":%llu,\"member\":%u}\n",point,(unsigned long long)o->journal.tip.line_count,o->member);
 fflush(stdout);
 if(write(atoi(ready),&value,1)!=1||read(atoi(go),&value,1)!=1||value!='g')_exit(92);
#endif
}
static int text(const char *s,size_t capacity,int leaf){
 size_t n=0;
 while(n<capacity&&s[n])n++;
 if(!n||n==capacity)return 0;
 for(size_t k=n+1;k<capacity;k++)if(s[k])return 0;
 return !leaf||pc02io_leaf(s);
}
static int hex(const char *s,size_t n){for(size_t k=0;k<n;k++)if(!((s[k]>='0'&&s[k]<='9')||(s[k]>='a'&&s[k]<='f')))return 0;
return s[n]==0;
}
static int absolute(const char *s){return s&&s[0]=='/'&&strlen(s)<P2_PATH;
}
static int supported_filesystem(int fd){
 struct statfs info;
 if(fstatfs(fd,&info))return 0;
#ifdef __APPLE__
 return !strcmp(info.f_fstypename,"apfs");
#else
 return (unsigned long)info.f_type==0xef53ul;
#endif
}
static int child_path(p2_owner *o,const char *leaf,char out[P2_PATH]){
 int n=snprintf(out,P2_PATH,"%s%s%s",o->parent_path,!strcmp(o->parent_path,"/")?"":"/",leaf);
 return n>0&&n<P2_PATH;
}
static int paths(p2_owner *o){
 const char *actual=o->repair_schema?o->input.library:pc02_library_path(o->lease),*slash;
 if(!actual||strcmp(actual,o->input.library)||!(slash=strrchr(actual,'/')))return 0;
 size_t n=slash==actual?1:(size_t)(slash-actual);
 memcpy(o->parent_path,actual,n);
 o->parent_path[n]=0;
 int length=snprintf(o->mirror_leaf,sizeof(o->mirror_leaf),"%s.legacy-map.json",slash+1);
 if(length<=0||length>255||!child_path(o,o->mirror_leaf,o->mirror_path)||
    !child_path(o,o->input.pack_copy,o->pack_path))return 0;
 for(unsigned k=0;k<2;k++)if(!child_path(o,o->input.stages[k],o->stage_path[k]))return 0;
 return 1;
}
static void id_text(const unsigned char id[16],char out[49]){
 static const char digits[]="0123456789abcdef";
 memset(out,'0',48);
 out[48]=0;
 for(unsigned k=0;k<16;k++){out[k*2]=digits[id[k]>>4];
 out[k*2+1]=digits[id[k]&15];
 }
}
static void gates(wh_gates *g){
 const char *names[]={"PC02-native-authority-v1","PC02-synchronous-two-member-v1","PC02-exact-ack-floor-v1","PC02-actual-SDK-proof-v1","PC02-no-workers-v1"};
 char *out[]={g->admission,g->publisher,g->recovery,g->observer,g->fault};
 for(unsigned k=0;k<5;k++)wh_sha256_hex(names[k],strlen(names[k]),out[k]);
}
static int executable(pc02_file *file){
 int fd=-1,ok=0;
#ifdef __APPLE__
 char link[P2_PATH],resolved[P2_PATH];
 uint32_t size=sizeof(link);
 if(_NSGetExecutablePath(link,&size)||!realpath(link,resolved))return 0;
 fd=open(resolved,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
#else
 fd=open("/proc/self/exe",O_RDONLY|O_CLOEXEC);
#endif
 if(fd>=0)ok=pc02io_hash(fd,file);
 if(fd>=0&&close(fd))ok=0;
 return ok;
}
static int binding(p2_owner *o){
 pc02_file binary;
 wh_binding *b=&o->input.binding;
 if(!executable(&binary))return 0;
 strcpy(b->source,PC02_BUILD_SOURCE);
 strcpy(b->run,PC02_BUILD_RUN);
 strcpy(b->attempt,PC02_BUILD_ATTEMPT);
 strcpy(b->artifact,binary.sha);
 strcpy(b->provider,PC02_PROVIDER_SHA);
 strcpy(b->sdk,"3.42.0-8357eafa");
#ifdef __APPLE__
 strcpy(b->platform,"macos-apfs");
#else
 strcpy(b->platform,"linux-ext4");
#endif
 gates(&o->input.gates);
 return wh_binding_valid(b);
}
static int file_valid(const pc02_file *f){pc02_identity id=pc02io_getid(f->identity);
return id.inode&&hex(f->sha,64);
}
static int id_at(p2_owner *o,const char *leaf,const unsigned char expected[16],int private_mode){
 pc02_identity id,want=pc02io_getid(expected);
 struct stat st;
 int fd=openat(o->parent,leaf,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
 int ok=fd>=0&&pc02io_identity(fd,0,private_mode,&id)&&pc02io_same(&id,&want)&&
 !fstatat(o->parent,leaf,&st,AT_SYMLINK_NOFOLLOW)&&S_ISREG(st.st_mode)&&
 (uint64_t)st.st_dev==id.device&&(uint64_t)st.st_ino==id.inode;
 if(fd>=0&&close(fd))ok=0;
 return ok;
}
static size_t rows(p2_owner *,wh_record *);
static int input_valid(p2_owner *o){
 p2_input *i=&o->input;
 wh_gates expected;
 char manifest[EXR_WH_LINE_MAX],authority[P2_PATH];
 const wh_binding *b=&i->binding;
 if(o->repair_schema){if(!o->repair_authority)return 0;strcpy(authority,o->repair_authority);}
 else if(!pc02_user_authority(authority,sizeof(authority)))return 0;
 if(memcmp(i->magic,"PC02IN01",8)||!text(b->source,sizeof(b->source),0)||!text(b->run,sizeof(b->run),0)||
    !text(b->attempt,sizeof(b->attempt),0)||!text(b->artifact,sizeof(b->artifact),0)||!text(b->platform,sizeof(b->platform),0)||
    !text(b->sdk,sizeof(b->sdk),0)||!text(b->provider,sizeof(b->provider),0)||!wh_binding_valid(b)||
    strcmp(b->provider,PC02_PROVIDER_SHA)||strcmp(b->sdk,"3.42.0-8357eafa")||
    !text(i->library,sizeof(i->library),0)||!absolute(i->library)||!text(i->pack,sizeof(i->pack),0)||!absolute(i->pack)||
    !text(i->authority,sizeof(i->authority),0)||strcmp(authority,i->authority)||
    !hex(i->token,48)||i->mirror_present>1||i->allow_partial>1||!file_valid(&i->original)||
    !file_valid(&i->source_pack)||!file_valid(&i->private_pack)||memcmp(i->source_pack.size,i->private_pack.size,8)||
    strcmp(i->source_pack.sha,i->private_pack.sha))return 0;
#ifdef __APPLE__
 if(strcmp(b->platform,"macos-apfs"))return 0;
#else
 if(strcmp(b->platform,"linux-ext4"))return 0;
#endif
 gates(&expected);
 if(memcmp(&expected,&i->gates,sizeof(expected))||!wh_manifest(b,&i->gates,manifest))return 0;
 for(unsigned k=0;k<2;k++){
  char name[64];
  if(!text(i->stages[k],64,1)||!text(i->retained[k],64,1)||!pc02io_get64(i->staged[k]+8))return 0;
  snprintf(name,sizeof(name),"c02-%s-%u.stage",i->token,k);
  if(strcmp(name,i->stages[k]))return 0;
  snprintf(name,sizeof(name),"c02-%s-%u.retained",i->token,k);
  if(strcmp(name,i->retained[k]))return 0;
 }
 char name[64];
 snprintf(name,sizeof(name),"c02-%s.journal",i->token);
 if(strcmp(name,i->journal))return 0;
 snprintf(name,sizeof(name),"c02-%s.pack",i->token);
 if(strcmp(name,i->pack_copy)||!text(i->journal,64,1)||
    !text(i->pack_copy,64,1)||!pc02io_get64(i->journal_identity+8))return 0;
 if(i->mirror_present){if(!file_valid(&i->mirror))return 0;
 }
 else{pc02_file zero={0};
 if(memcmp(&zero,&i->mirror,sizeof(zero)))return 0;
 }
 if(memcmp(i->original_grant+72,i->original.identity,16))return 0;
 if(o->repair_schema){
  char grant_seal[65];memcpy(grant_seal,i->original_grant+8,64);grant_seal[64]=0;
  if(!hex(grant_seal,64))return 0;
 }
 else if(o->recovered){
  unsigned char begin[304]={0};
  char sha[65],manifest_sha[65];
  if(pc02io_get64(i->original_grant)==UINT64_MAX||pc02io_get64(i->original_grant)+1!=o->pending.generation)return 0;
  memcpy(begin,"PC02S001",8);
  begin[8]='B';
  pc02io_put64(begin+16,o->pending.generation*2);
  pc02io_put64(begin+24,o->pending.generation);
  memcpy(begin+32,o->pending.manifest,64);
  memcpy(begin+96,o->pending.input,64);
  memset(begin+160,'0',64);
  memcpy(begin+224,i->original.identity,16);
  memcpy(begin+240,i->original_grant+8,64);
  wh_sha256_hex(begin,sizeof(begin),sha);
  wh_sha256_hex(manifest,strlen(manifest),manifest_sha);
  if(strcmp(sha,o->pending.seal)||strcmp(manifest_sha,o->pending.manifest))return 0;
 }
 else{
  pc02_grant grant;
  if(!pc02_grant_get(o->lease,&grant)||grant.generation!=pc02io_get64(i->original_grant)||
   memcmp(grant.seal,i->original_grant+8,64))return 0;
 }
 wh_record snapshot_rows[3];
 size_t row_count=rows(o,snapshot_rows);
 return wh_snapshot_valid(snapshot_rows,row_count)&&paths(o);
}
static int reserve_file(p2_owner *o,const char *leaf,unsigned char id[16]){
 pc02_identity actual;
 int fd=openat(o->parent,leaf,O_RDWR|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
 if(fd<0)return -1;
 if(!pc02io_identity(fd,0,1,&actual)||fsync(fd)||fsync(o->parent)){close(fd);
 return -1;
 }
 pc02io_putid(id,&actual);
 return fd;
}
static int create_input(p2_owner *o,const char *library,const char *pack,int partial){
 unsigned char random[24];
 pc02_grant grant;
 pc02_identity parent,journal_id;
 pc02_metadata_info metadata;
 char input_sha[65];
 int source=-1,copy=-1,journal=-1,ok=0;
 pc02_file observed;
 memcpy(o->input.magic,"PC02IN01",8);
 strcpy(o->input.library,library);
 strcpy(o->input.pack,pack);
 o->input.allow_partial=(unsigned char)partial;
 if(!pc02_user_authority(o->input.authority,sizeof(o->input.authority))||!pc02_parent_fd(o->lease,&o->parent,&parent)||
    !pc02_grant_get(o->lease,&grant)||!binding(o)||getentropy(random,sizeof(random)))goto done;
 pc02io_put64(o->input.original_grant,grant.generation);
 memcpy(o->input.original_grant+8,grant.seal,64);
 pc02io_putid(o->input.original_grant+72,&grant.target);
 static const char digits[]="0123456789abcdef";
 for(unsigned k=0;k<24;k++){o->input.token[k*2]=digits[random[k]>>4];
 o->input.token[k*2+1]=digits[random[k]&15];
 }
 for(unsigned k=0;k<2;k++){snprintf(o->input.stages[k],64,"c02-%s-%u.stage",o->input.token,k);
 snprintf(o->input.retained[k],64,"c02-%s-%u.retained",o->input.token,k);
 }
 snprintf(o->input.journal,64,"c02-%s.journal",o->input.token);
 snprintf(o->input.pack_copy,64,"c02-%s.pack",o->input.token);
 if(!paths(o))goto done;
 const char *leaf=strrchr(library,'/')+1;
 if(!pc02io_quiet(o->parent,leaf))goto done;
 o->original=openat(o->parent,leaf,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
 if(o->original<0||!pc02io_hash(o->original,&o->input.original)||memcmp(o->input.original.identity,o->input.original_grant+72,16))goto done;
 o->mirror=openat(o->parent,o->mirror_leaf,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
 if(o->mirror<0){if(!pc02io_absent(o->parent,o->mirror_leaf))goto done;
 }
 else{if(!pc02io_hash(o->mirror,&o->input.mirror))goto done;
 o->input.mirror_present=1;
 }
 source=open(pack,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
 if(source<0||!pc02io_hash(source,&o->input.source_pack))goto done;
 for(unsigned k=0;k<2;k++){
  if(!pc02io_absent(o->parent,o->input.retained[k]))goto done;
  o->stages[k]=reserve_file(o,o->input.stages[k],o->input.staged[k]);
  if(o->stages[k]<0)goto done;
 }
 unsigned char copy_id[16];
 copy=reserve_file(o,o->input.pack_copy,copy_id);
 if(copy<0||!pc02io_copy(source,copy,&o->input.source_pack)||!pc02io_hash(copy,&o->input.private_pack)||
    memcmp(copy_id,o->input.private_pack.identity,16))goto done;
 int current=open(pack,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
 int same_source=current>=0&&pc02io_hash(current,&observed)&&pc02io_equal(&observed,&o->input.source_pack);
 if(current>=0&&close(current))same_source=0;
 if(!same_source)goto done;
 if(mkdirat(o->parent,o->input.journal,0700))goto done;
 journal=openat(o->parent,o->input.journal,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
 if(journal<0||!pc02io_identity(journal,1,1,&journal_id)||fsync(journal)||fsync(o->parent))goto done;
 pc02io_putid(o->input.journal_identity,&journal_id);
 if(!input_valid(o)||!pc02io_quiet(o->parent,leaf)||
    !pc02io_hash(o->original,&observed)||!pc02io_equal(&observed,&o->input.original)||
    !pc02_metadata_write(o->lease,PC02_META_INPUT,NULL,&o->input,sizeof(o->input),input_sha,&metadata))goto done;
 o->pack=copy;
 copy=-1;
 phase(o,900);
 ok=1;
done:
 if(source>=0&&close(source))ok=0;
 if(copy>=0&&close(copy))ok=0;
 if(journal>=0&&close(journal))ok=0;
 return ok;
}
static int private_pack(p2_owner *o){
 if(o->pack<0)o->pack=openat(o->parent,o->input.pack_copy,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
 pc02_file file;
 return o->pack>=0&&pc02io_hash(o->pack,&file)&&pc02io_equal(&file,&o->input.private_pack)&&
  pc02io_match(o->parent,o->input.pack_copy,&o->input.private_pack);
}
static int original_state(p2_owner *o){
 const char *leaf=strrchr(o->input.library,'/')+1;
 if(!private_pack(o)||!pc02_check(o->lease)||!pc02io_quiet(o->parent,leaf)||
    !pc02io_match(o->parent,leaf,&o->input.original)||
    !(o->input.mirror_present?pc02io_match(o->parent,o->mirror_leaf,&o->input.mirror):pc02io_absent(o->parent,o->mirror_leaf)))return 0;
 for(unsigned k=0;k<2;k++)if(!id_at(o,o->input.stages[k],o->input.staged[k],1)||
  !pc02io_absent(o->parent,o->input.retained[k]))return 0;
 return 1;
}
static int prepared_read(p2_owner *o){
 pc02_metadata_info metadata;
 size_t size=0;
 if(pc02_metadata_read(o->lease,PC02_META_PREPARED,&o->pending,&o->prepared,sizeof(o->prepared),&size,&metadata)!=1||
    size!=sizeof(o->prepared)||memcmp(o->prepared.magic,"PC02OUT1",8)||strcmp(o->prepared.input_sha,o->pending.input))return 0;
 for(unsigned k=0;k<2;k++)if(!file_valid(&o->prepared.files[k])||!pc02io_get64(o->prepared.files[k].size)||
  memcmp(o->prepared.files[k].identity,o->input.staged[k],16))return 0;
 o->has_prepared=1;
 return 1;
}
static void member(p2_owner *o,unsigned k,pc02_member *m){
 memset(m,0,sizeof(*m));
 strcpy(m->target,k?o->mirror_leaf:strrchr(o->input.library,'/')+1);
 strcpy(m->stage,o->input.stages[k]);
 strcpy(m->retained,o->input.retained[k]);
 m->original_present=!k||o->input.mirror_present;
 m->original=pc02io_getid(k?o->input.mirror.identity:o->input.original.identity);
 m->prepared=pc02io_getid(o->input.staged[k]);
}
static int sdk_verify(p2_owner *o,const char *database,const char *mirror){
 if(!pc02_borrow(o->lease))return 0;
 int ok=pc02t_verify(o->pack,database,o->pack_path,mirror);
 if(!pc02_unborrow(o->lease))ok=0;
 return ok;
}
static int published_state(p2_owner *o){
 if(!o->has_prepared||!private_pack(o)||!pc02_check(o->lease))return 0;
 const char *leaf=strrchr(o->input.library,'/')+1;
 for(unsigned k=0;k<2;k++){
  pc02_member m;
  unsigned state=99;
  member(o,k,&m);
  if(!pc02_member_observe(o->lease,&m,&state)||state!=2||
     !pc02io_match(o->parent,m.target,&o->prepared.files[k])||
     !(m.original_present?pc02io_match(o->parent,m.retained,k?&o->input.mirror:&o->input.original):pc02io_absent(o->parent,m.retained)))return 0;
 }
 if(!pc02io_quiet(o->parent,leaf)||!pc02io_quiet(o->parent,o->input.retained[0])||
    !sdk_verify(o,o->input.library,o->mirror_path))return 0;
 return pc02io_match(o->parent,leaf,&o->prepared.files[0])&&pc02io_match(o->parent,o->mirror_leaf,&o->prepared.files[1]);
}
static wh_step checked(void *context,void *cap){
 p2_owner *o=context;
 return cap&&cap==o->cap&&pc02_cap_check(o->lease,o->cap)&&private_pack(o)?WH_STEP_OK:WH_STEP_UNCERTAIN;
}
static wh_step acquire(void *context,const wh_binding *b,const wh_gates *g,void **cap,char lease[49]){
 p2_owner *o=context;
 char line[EXR_WH_LINE_MAX],manifest_sha[65],input_sha[65];
 if(memcmp(b,&o->input.binding,sizeof(*b))||memcmp(g,&o->input.gates,sizeof(*g))||!wh_manifest(b,g,line))return WH_STEP_UNCERTAIN;
 wh_sha256_hex(line,strlen(line),manifest_sha);
 wh_sha256_hex(&o->input,sizeof(o->input),input_sha);
 if(!(o->recovered?pc02_resume(o->lease,&o->pending,&o->cap):pc02_begin(o->lease,manifest_sha,input_sha,&o->cap))||
    !pc02_pending(o->lease,&o->pending)||strcmp(o->pending.manifest,manifest_sha)||strcmp(o->pending.input,input_sha)||
    (o->recovered&&!pc02j_catchup(&o->journal,o->cap)))return WH_STEP_UNCERTAIN;
 *cap=o->cap;
 strcpy(lease,o->input.token);
 phase(o,901);
 return checked(o,o->cap);
}
static wh_step reacquire(void *context,const wh_binding *b,const wh_gates *g,const char *prior,void **cap,char lease[49]){
 p2_owner *o=context;
 if(!o->recovered||(prior[0]&&strcmp(prior,o->input.token)))return WH_STEP_UNCERTAIN;
 return acquire(context,b,g,cap,lease);
}
static size_t rows(p2_owner *o,wh_record *out){
 const pc02_file *files[3];
 const char *names[3];
 size_t n=0;
 files[n]=&o->input.original;
 names[n++]="library.sqlite";
 if(o->input.mirror_present){files[n]=&o->input.mirror;
 names[n++]="mirror.json";
 }
 files[n]=&o->input.source_pack;
 names[n++]="pack.exrpack";
 for(size_t k=0;k<n;k++){memset(&out[k],0,sizeof(out[k]));
 id_text(files[k]->identity,out[k].id);
  strcpy(out[k].path,names[k]);
  out[k].size=pc02io_get64(files[k]->size);
  strcpy(out[k].sha,files[k]->sha);
  }
 return n;
}
static wh_step snapshot(void *context,void *cap,wh_record *out,size_t capacity,size_t *count){
 p2_owner *o=context;
 if(checked(o,cap)!=WH_STEP_OK||capacity<3||!original_state(o))return WH_STEP_UNCERTAIN;
 if(o->recovered&&!o->initial_count)return WH_STEP_FAILED;
 *count=rows(o,out);
 phase(o,902);
 return wh_snapshot_valid(out,*count)?WH_STEP_OK:WH_STEP_UNCERTAIN;
}
static int private_copy(p2_owner *o){
 const char *leaf=strrchr(o->input.library,'/')+1;
 if(o->original<0)o->original=openat(o->parent,leaf,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
 int stage=openat(o->parent,o->input.stages[0],O_RDWR|O_NOFOLLOW|O_CLOEXEC);
 int ok=stage>=0&&id_at(o,o->input.stages[0],o->input.staged[0],1)&&pc02io_quiet(o->parent,leaf)&&
  pc02io_copy(o->original,stage,&o->input.original)&&pc02io_quiet(o->parent,leaf)&&
  id_at(o,o->input.stages[0],o->input.staged[0],1);
 if(stage>=0&&close(stage))ok=0;
 return ok;
}
static wh_step import_rows(void *context,void *cap,const wh_record *actual,size_t count,char stage[49]){
 p2_owner *o=context;
 wh_record expected[3];
 size_t n=rows(o,expected);
 if(checked(o,cap)!=WH_STEP_OK||count!=n||memcmp(actual,expected,n*sizeof(*actual))||!original_state(o))return WH_STEP_UNCERTAIN;
 if(!private_copy(o)||!pc02_borrow(o->lease))return WH_STEP_UNCERTAIN;
 int ok=pc02t_build(o->pack,o->pack_path,o->stage_path[0],o->stage_path[1],
  o->input.mirror_present?o->mirror_path:NULL,o->input.allow_partial);
 if(!pc02_unborrow(o->lease))return WH_STEP_UNCERTAIN;
 if(!ok)return original_state(o)?WH_STEP_FAILED:WH_STEP_UNCERTAIN;
 if(!original_state(o))return WH_STEP_UNCERTAIN;
 strcpy(stage,o->input.token);
 phase(o,903);
 return WH_STEP_OK;
}
static wh_step verify(void *context,void *cap,const char *stage,const wh_record *actual,size_t count){
 p2_owner *o=context;
 wh_record expected[3];
 size_t n=rows(o,expected);
 pc02_metadata_info metadata;
 char sha[65];
 if(checked(o,cap)!=WH_STEP_OK||strcmp(stage,o->input.token)||count!=n||memcmp(actual,expected,n*sizeof(*actual))||
    !original_state(o)||!sdk_verify(o,o->stage_path[0],o->stage_path[1]))return WH_STEP_UNCERTAIN;
 memset(&o->prepared,0,sizeof(o->prepared));
 memcpy(o->prepared.magic,"PC02OUT1",8);
 strcpy(o->prepared.input_sha,o->pending.input);
 for(unsigned k=0;k<2;k++){
  int fd=openat(o->parent,o->input.stages[k],O_RDWR|O_NOFOLLOW|O_CLOEXEC);
  int ok=fd>=0&&!fsync(fd)&&pc02io_hash(fd,&o->prepared.files[k])&&!memcmp(o->prepared.files[k].identity,o->input.staged[k],16);
  if(fd>=0&&close(fd))ok=0;
  if(!ok)return WH_STEP_UNCERTAIN;
 }
 if(!pc02_metadata_write(o->lease,PC02_META_PREPARED,o->cap,&o->prepared,sizeof(o->prepared),sha,&metadata))return WH_STEP_UNCERTAIN;
 o->has_prepared=1;
 phase(o,904);
 return WH_STEP_OK;
}
static int member_proof(void *context,int original,int prepared){
 p2_owner *o=context;
 pc02_file actual;
 unsigned k=o->member;
 const pc02_file *old=k?&o->input.mirror:&o->input.original;
 int present=!k||o->input.mirror_present;
 return (present?(original>=0&&pc02io_hash(original,&actual)&&pc02io_equal(&actual,old)):original==-1)&&
 pc02io_hash(prepared,&actual)&&pc02io_equal(&actual,&o->prepared.files[k]);
}
static int close_file(int *fd){if(*fd<0)return 1;
int before=*fd;
*fd=-1;
return close(before)==0;
}
static int publish_members(p2_owner *o){
 if(!o->has_prepared||!pc02_prepare_publish(o->lease,o->cap))return 0;
 if(!close_file(&o->original)||!close_file(&o->mirror))return 0;
 for(unsigned k=0;k<2;k++)if(!close_file(&o->stages[k]))return 0;
 for(unsigned k=0;k<2;k++){
  pc02_member m;
  member(o,k,&m);
  o->member=k;
  if(!pc02_member_publish(o->lease,o->cap,&m,member_proof,o))return 0;
  phase(o,905+k);
 }
 return published_state(o);
}
static wh_step publish(void *context,void *cap,const char *stage,wh_pub *published){
 p2_owner *o=context;
 *published=WH_PUB_UNKNOWN;
 if(checked(o,cap)!=WH_STEP_OK||strcmp(stage,o->input.token)||!publish_members(o))return WH_STEP_UNCERTAIN;
 o->published=1;
 *published=WH_PUB_YES;
 return WH_STEP_OK;
}
static wh_step inspect(void *context,void *cap,const char *stage,const char *content,wh_pub *published){
 p2_owner *o=context;
 wh_record saved[3];
 char digest[65];
 size_t n=rows(o,saved);
 *published=WH_PUB_UNKNOWN;
 if(checked(o,cap)!=WH_STEP_OK||!wh_content_digest(saved,n,digest)||(content[0]&&strcmp(content,digest))||
    (stage[0]&&strcmp(stage,o->input.token)))return WH_STEP_UNCERTAIN;
 if(o->publish_intent){
  if(strcmp(stage,o->input.token)||!content[0]||!prepared_read(o)||!publish_members(o))return WH_STEP_UNCERTAIN;
  o->published=1;
  *published=WH_PUB_YES;
  return WH_STEP_OK;
 }
 if(!original_state(o))return WH_STEP_UNCERTAIN;
 o->aborted=1;
 *published=WH_PUB_NO;
 return WH_STEP_OK;
}
static wh_step discard(void *context,void *cap,const char *stage){
 p2_owner *o=context;
 if(checked(o,cap)!=WH_STEP_OK||strcmp(stage,o->input.token)||!original_state(o))return WH_STEP_UNCERTAIN;
 o->aborted=1;
 return WH_STEP_OK;
}
#include "pc02_repair_owner.inc"
static int terminal_proof(void *context,const char *path,int target,const pc02_pending_record *pending,const char *terminal){
 p2_owner *o=context;
 (void)path;
 pc02_identity actual;
 int committed=0,aborted=0;
 if(!pending||pending->generation!=o->pending.generation||strcmp(pending->seal,o->pending.seal)||
    strcmp(pending->input,o->pending.input)||strcmp(pending->manifest,o->pending.manifest)||
    !pc02j_scan(&o->journal)||strcmp(terminal,o->journal.tip.last_line_sha)||!o->journal.count)return 0;
 for(size_t k=1;k<o->journal.count;k++){
  unsigned seq,event;
  if(sscanf(o->journal.lines[k],"EXRWH2 %u %u",&seq,&event)!=2)return 0;
  if(event==11)committed=1;
  if(event==14)aborted=1;
 }
 unsigned seq,event;
 if(sscanf(o->journal.lines[o->journal.count-1],"EXRWH2 %u %u",&seq,&event)!=2||event!=12||
  !pc02io_identity(target,0,0,&actual))return 0;
 pc02_identity expected=pc02io_getid(committed?o->prepared.files[0].identity:o->input.original.identity);
 if(!pc02io_same(&actual,&expected))return 0;
 return committed&&!aborted?published_state(o):aborted&&!committed&&original_state(o);
}
static wh_step release(void *context,void *cap){
 p2_owner *o=context;
 pc02_grant grant;
 if(checked(o,cap)!=WH_STEP_OK||!pc02j_catchup(&o->journal,o->cap))return WH_STEP_UNCERTAIN;
 phase(o,907);
 if(!pc02_finish(o->lease,o->cap,o->journal.tip.last_line_sha,terminal_proof,o,&grant))return WH_STEP_UNCERTAIN;
 o->cap=NULL;
 phase(o,908);
 return WH_STEP_OK;
}
static wh3_tx_status append(void *context,void *cap,const wh3_tip *expected,const char *line,wh3_tip *actual){
 p2_owner *o=context;
 return cap==o->cap?pc02j_append(&o->journal,o->cap,expected,line,actual):WH3_TX_UNCERTAIN;
}
static int history(p2_owner *o){
 if(!pc02j_scan(&o->journal))return 0;
 o->initial_count=o->journal.count;
 for(size_t k=1;k<o->journal.count;k++){
  unsigned seq,event;
  if(sscanf(o->journal.lines[k],"EXRWH2 %u %u",&seq,&event)!=2)return 0;
  if(event==9)o->publish_intent=1;
 }
 return 1;
}
static void cleanup(p2_owner *o){
 if(!o)return;
 close_file(&o->pack);
 close_file(&o->original);
 close_file(&o->mirror);
 for(unsigned k=0;k<2;k++)close_file(&o->stages[k]);
 (void)pc02j_close(&o->journal);
 if(o->cap){(void)pc02_abandon(o->lease,o->cap);
 o->cap=NULL;
 }
 (void)pc02_close(o->lease);
 free(o);
}
static int verify_command(p2_owner *o,const char *library,const char *pack){
 char authority[P2_PATH],mirror[P2_PATH];
 pc02_file before,after;
 const char *physical;
 if(!pc02_user_authority(authority,sizeof(authority))||
    !pc02_open(authority,library,PC02_SHARED,NULL,NULL,&o->lease)||
    !(physical=pc02_library_path(o->lease)))return 0;
 int n=snprintf(mirror,sizeof(mirror),"%s.legacy-map.json",physical);
 if(n<=0||n>=P2_PATH)return 0;
 o->pack=open(pack,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
 if(o->pack<0||!pc02io_hash(o->pack,&before)||!pc02_borrow(o->lease))return 0;
 int ok=pc02t_verify(o->pack,physical,pack,mirror);
 if(!pc02_unborrow(o->lease)||!pc02io_hash(o->pack,&after)||!pc02io_equal(&before,&after)||!pc02_check(o->lease))ok=0;
 return ok;
}
int main(int argc,char **argv){
 p2_owner *o=NULL;
 wh3_session *session=NULL;
 wh_report report={0};
 wh_provider provider={0};
 wh3_backend backend={0};
 int recover=0,verify_only=0,partial=0,ok=0;
 char authority[P2_PATH];
 size_t size=0;
 pc02_metadata_info metadata;
 if(strcmp(exr_version(),"3.42.0")){fputs("C02 requires the actual frozen SDK 3.42.0.\n",stderr);
 return 2;
 }
 if(argc==2&&!strcmp(argv[1],"--version")){
  printf("exreader-c02-migrate %s provider=%s SDK=3.42.0 synchronous-posix\n",PC02_BUILD_SOURCE,PC02_PROVIDER_SHA);
  return 0;
 }
 if(argc<3||!absolute(argv[2]))goto usage;
 recover=!strcmp(argv[1],"recover");
 verify_only=!strcmp(argv[1],"verify");
 if(recover){if(argc!=3)goto usage;
 }
 else{
  if(strcmp(argv[1],"migrate")&&!verify_only)goto usage;
  if(argc<4||!absolute(argv[3]))goto usage;
  if(argc==5&&!strcmp(argv[4],"--allow-partial")&&!verify_only)partial=1;
  else if(argc!=4)goto usage;
 }
 if(!pc02_user_authority(authority,sizeof(authority)))return 2;
 o=calloc(1,sizeof(*o));
 if(!o)return 2;
 o->recovered=recover;
 o->parent=o->pack=o->original=o->mirror=o->stages[0]=o->stages[1]=o->journal.directory=-1;
 o->controls.context=o;
 o->controls.phase=phase;
#ifdef PC02_MIGRATION_TEST_CONTROLS
 const char *fault=getenv("EXR_PC02_SHORT_PHASE");
 if(fault){o->controls.fault=PC02_SHORT_WRITE;
 o->controls.fault_phase=(unsigned)strtoul(fault,NULL,10);
 }
#endif
 if(verify_only){o->operation="shared-actual-SDK-verify";
 ok=verify_command(o,argv[2],argv[3]);
 goto done;
 }
 o->operation="exclusive-native-admission";
 if(recover){
  int restored=0;o->operation="explicit-protected-tail-repair";
  o->repair_library=argv[2];o->repair_authority=authority;
  if(!pc02_repair_prepare(authority,argv[2],repair_schema,repair_prove,o,&o->controls,&restored))goto done;
  if(restored){puts("{\"status\":\"restored_original_registered_clean\",\"live_capability\":false}");ok=1;goto done;}
 }
 if(!pc02_open(authority,argv[2],recover?PC02_RECOVER:PC02_OWNER,NULL,&o->controls,&o->lease))goto done;
 pc02_identity parent;
 if(!pc02_parent_fd(o->lease,&o->parent,&parent)||!supported_filesystem(o->parent))goto done;
 int root=open(authority,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
 int supported=root>=0&&supported_filesystem(root);
 if(root>=0&&close(root))supported=0;
 if(!supported)goto done;
 if(recover){
  o->operation="original-exact-descriptor";
  if(!pc02_descriptor(o->lease,&o->pending,&o->clean)){
   pc02_grant grant;
   if(!pc02_check(o->lease)||!pc02_grant_get(o->lease,&grant))goto done;
   puts("{\"status\":\"registered_clean_without_pending\",\"live_capability\":false}");
   ok=1;
   goto done;
  }
  if(pc02_metadata_read(o->lease,PC02_META_INPUT,&o->pending,&o->input,sizeof(o->input),&size,&metadata)!=1||
     size!=sizeof(o->input)||strcmp(argv[2],o->input.library)||!input_valid(o)||!private_pack(o))goto done;
 }
 else{
  o->operation="immutable-input-and-private-pack";
  if(!create_input(o,argv[2],argv[3],partial))goto done;
 }
 pc02_identity journal_id=pc02io_getid(o->input.journal_identity);
 o->operation="registered-real-ACK-journal";
 if(!pc02j_open(&o->journal,o->lease,o->parent,o->input.journal,&journal_id,&o->input.binding,&o->input.gates,&o->pending))goto done;
 o->journal.context=o;
 o->journal.phase=phase;
 if(recover){
  if(!history(o)||(o->publish_intent&&!prepared_read(o)))goto done;
  if(o->journal.count){
   unsigned seq,event;
   if(sscanf(o->journal.lines[o->journal.count-1],"EXRWH2 %u %u",&seq,&event)==2&&event==12){
    pc02_grant grant;
    o->operation="exact-terminal-native-completion";
    if(o->clean)ok=pc02_reconcile(o->lease,&o->pending,o->journal.tip.last_line_sha,terminal_proof,o,&grant);
    else ok=pc02_resume(o->lease,&o->pending,&o->cap)&&release(o,o->cap)==WH_STEP_OK;
    if(ok)puts("{\"status\":\"recovered_exact_terminal\",\"live_capability\":false}");
    goto done;
   }
  }
  if(o->clean)goto done;
 }
 provider.abi=EXR_WH_ABI;
 provider.identity_sha=PC02_PROVIDER_SHA;
 provider.context=o;
 provider.acquire=acquire;
 provider.reacquire=reacquire;
 provider.check=checked;
 provider.snapshot=snapshot;
 provider.import_rows=import_rows;
 provider.verify=verify;
 provider.publish=publish;
 provider.inspect=inspect;
 provider.discard=discard;
 provider.release=release;
 backend.abi=EXR_WH3_ABI;
 backend.context=o;
 backend.append=append;
 o->operation="synchronous-immutable-provider";
 session=wh3_create(&o->input.binding,&o->input.gates,&provider,&backend);
 if(!session)goto done;
 if(recover&&o->journal.count)wh3_recover(session,o->journal.pointers,o->journal.count,&report);
 else wh3_run(session,&report);
 printf("{\"status\":\"%s\",\"detail\":\"%s\",\"sequence\":%u,\"live_capability\":%s,\"source\":\"%s\",\"provider\":\"%s\"}\n",
  wh_status_name(report.status),report.detail,report.seq,report.live_lease?"true":"false",PC02_BUILD_SOURCE,PC02_PROVIDER_SHA);
 ok=report.status==WH_COMPLETED||report.status==WH_ROLLED_BACK;
 if(ok&&!wh3_dispose(session))ok=0;
done:
 if(!ok)fprintf(stderr,"C02 refused/pending; original objects and all failure bytes retained (operation %s, errno %d).\n",o&&o->operation?o->operation:"initial",errno);
 if(!ok&&session){fflush(NULL);
 _Exit(2);
 }
 cleanup(o);
 return ok?(report.status==WH_ROLLED_BACK&&!recover?3:0):2;
usage:
 fputs("Usage: exreader-c02-migrate migrate /absolute/LIBRARY /absolute/PACK [--allow-partial]\n"
       "       exreader-c02-migrate recover /absolute/LIBRARY\n"
       "       exreader-c02-migrate verify /absolute/LIBRARY /absolute/PACK\n"
       "Explicit exreader-c02-admission enrollment is required before any migration.\n",stderr);
 return 64;
}
