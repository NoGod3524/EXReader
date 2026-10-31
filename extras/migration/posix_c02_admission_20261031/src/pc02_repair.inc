/* SPDX-License-Identifier: MIT */
#include "exr_pc02_repair_scan.h"
#include "exr_pc02_repair_store.h"
#define PR_LIMIT (4u*1024u*1024u)
#define PR_PARTS 520u
#define PR_PLANS 256u
#define PR_PLAN 1u
#define PR_APPLIED 2u
#define PR_DONE 3u
#define PR_GUARD 4u
#define PR_ROUTE 1u
#define PR_JOURNAL 2u
#define PR_STATE 1u
#define PR_HEAD 2u
#define PR_BINDING 3u
#define PR_INPUT 4u
#define PR_PREPARED 5u
#define PR_ACK 6u
#define PR_FLOOR 7u
typedef struct {unsigned char identity[16],bytes[8];
char sha256[65],leaf[96];
}
pr_ref;
typedef struct {
 unsigned char identity[16],bytes[8];
 char sha256[65],leaf[256];
 unsigned char space,role,saved_identity[16],saved_bytes[8];
 char saved_sha256[65],saved_leaf[16];
}
pr_part;
typedef struct {
 unsigned char sequence[8],first[8],route_identity[16];
 pr_ref previous_plan,previous_done,guard;
 unsigned char archive_identity[16];
 char archive_leaf[96];
 unsigned char origin_binding[B_BYTES];
 pc02_repair_description description;
 unsigned char generation[8];
 char pending_seal[65],manifest[65],input[65],terminal_sha256[65];
 unsigned char before_begin,publish_intent,committed,aborted,terminal,member_states[2];
 unsigned char state_keep[8],head_keep[8],state_extra[8],head_extra[8],state_record[S_BYTES],head_record[272];
 char state_target_sha256[65],head_target_sha256[65];
 unsigned char part_count[8];
}
pr_plan;
typedef struct {
 pr_ref plan;
 unsigned char state_identity[16],state_bytes[8],head_identity[16],head_bytes[8];
 char state_sha256[65],head_sha256[65];
}
pr_applied;
typedef struct {
 unsigned char first[8],last[8],route_identity[16];
 pr_ref guard,last_plan,last_applied,previous_done;
 unsigned char binding[B_BYTES],state_identity[16],state_bytes[8],head_identity[16],head_bytes[8];
 char state_prefix_sha256[65],head_prefix_sha256[65];
}
pr_done;
_Static_assert(sizeof(pr_ref)==185&&sizeof(pr_part)==452,"repair reference wire");
_Static_assert(sizeof(pr_plan)==5039&&sizeof(pr_applied)==363&&sizeof(pr_done)==1254,"repair protected wire");
_Static_assert(sizeof(pc02_repair_description)==2951,"repair description wire");
typedef struct {
 pc02_lease *h;
 pc02rs_state state;
 pc02rs_tx tx;
 pc02_pending_record pending;
 pc02_repair_description description;
 unsigned char origin_binding[B_BYTES];
 pc02rp_blob state_raw,head_raw,input_raw,prepared_raw,acks[256],floors[256];
 int head,journal,archive;
 char input_leaf[128],prepared_leaf[128],head_leaf[128],archive_path[PATH_CAP];
 size_t ack_count,floor_count;
 unsigned before_begin;
 pc02_repair_schema schema;
 pc02_repair_prove prove;
 void *context;
}
pr_context;
static int pr_access(pc02_lease *);
static int pr_retire(pc02_lease *);
static int pr_name(const char *prefix,uint64_t sequence,char out[96]){
 int n=snprintf(out,96,"%s-%06u",prefix,(unsigned)sequence);
 return sequence&&sequence<=PR_PLANS&&n>0&&n<96;
}
static void pr_info_ref(pr_ref *out,const char *leaf,const pc02rp_info *info){
 memset(out,0,sizeof(*out));
 putid(out->identity,&info->identity);
 put64(out->bytes,info->bytes);
 memcpy(out->sha256,info->sha256,65);
 strcpy(out->leaf,leaf);
}
static int pr_ref_valid(const pr_ref *r){
 return memchr(r->leaf,0,sizeof(r->leaf))&&leaf_ok(r->leaf)&&nonzero(r->sha256)&&get64(r->identity+8);
}
static pc02rp_info pr_ref_info(const pr_ref *ref){
 pc02rp_info info;
 info.identity=getid(ref->identity);
 info.bytes=get64(ref->bytes);
 memcpy(info.sha256,ref->sha256,65);
 return info;
}
static int pr_read_object(pc02_lease *h,const pr_ref *ref,unsigned kind,uint64_t sequence,pc02rp_blob *out){
 if(!pr_ref_valid(ref))return 0;
 pc02rp_info exact=pr_ref_info(ref);
 return pc02rp_read(h->route_dir,ref->leaf,kind,sequence,&exact,out);
}
static int pr_put(pc02_lease *h,const char *leaf,unsigned kind,uint64_t sequence,const void *data,size_t size,pr_ref *out){
 pc02rp_info info;
 if(!pc02rp_write(h->route_dir,leaf,kind,sequence,data,size,&info))return 0;
 pr_info_ref(out,leaf,&info);
 return 1;
}
static int pr_read_named(pc02_lease *h,const char *prefix,unsigned kind,uint64_t sequence,pc02rp_blob *blob,pr_ref *ref){
 char leaf[96];
 if(!pr_name(prefix,sequence,leaf)||
  !pc02rp_read(h->route_dir,leaf,kind,sequence,NULL,blob))return 0;
 pr_info_ref(ref,leaf,&blob->info);
 return 1;
}
static int pr_scan_names(pc02_lease *h,unsigned *last,unsigned *last_done){
 unsigned char plans[PR_PLANS+1]={0},done[PR_PLANS+1]={0};
 int fd=-1,ok=0;
 DIR *dir=NULL;
 *last=*last_done=0;
 fd=openat(h->route_dir,".",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
 if(fd<0)return 0;
 dir=fdopendir(fd);
 if(!dir){close(fd);
 return 0;
 }
 for(;;){
  errno=0;
  struct dirent *e=readdir(dir);
  if(!e){if(errno)goto finish;
  break;
  }
  const char *prefix=NULL;
  unsigned char *set=NULL;
  if(!strncmp(e->d_name,"repair-plan-",12)){prefix="repair-plan";
  set=plans;
  }
  else if(!strncmp(e->d_name,"repair-done-",12)){prefix="repair-done";
  set=done;
  }
  else if(!strncmp(e->d_name,"repair-applied-",15))prefix="repair-applied";
  else continue;
  const char *digits=e->d_name+strlen(prefix)+1;
  if(strlen(digits)!=6||strspn(digits,"0123456789")!=6)goto finish;
  unsigned n=(unsigned)strtoul(digits,NULL,10);
  if(!n||n>PR_PLANS)goto finish;
  char expected[96];
  if(!pr_name(prefix,n,expected)||strcmp(expected,e->d_name))goto finish;
  if(set){if(set[n])goto finish;
  set[n]=1;
  }
  if(set==plans&&n>*last)*last=n;
  if(set==done&&n>*last_done)*last_done=n;
 }
 for(unsigned k=1;k<=*last;k++)if(!plans[k])goto finish;
 if(*last_done>*last)goto finish;
 ok=1;
finish:
 if(closedir(dir))ok=0;
 return ok;
}
static int pr_blob_prefix(int fd,uint64_t size,const char sha256[65],const pc02_identity *expected){
 pc02rp_blob raw={0};
 int ok=pc02rp_read_raw(fd,PR_LIMIT,&raw)&&sameid(&raw.info.identity,expected)&&raw.bytes>=size;
 if(ok){char sha[65];
 wh_sha256_hex(raw.data,(size_t)size,sha);
 ok=!memcmp(sha,sha256,65);
 }
 pc02rp_free(&raw);
 return ok;
}
static int pr_archive_open(pc02_lease *h,const pr_plan *plan){
 if(!memchr(plan->archive_leaf,0,sizeof(plan->archive_leaf))||!leaf_ok(plan->archive_leaf))return -1;
 int fd=openat(h->route_dir,plan->archive_leaf,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
 pc02_identity id,expected=getid(plan->archive_identity);
 struct stat named;
 if(fd<0||!metadata(fd,1,1,&id)||!sameid(&id,&expected)||
  fstatat(h->route_dir,plan->archive_leaf,&named,AT_SYMLINK_NOFOLLOW)||
  (uint64_t)named.st_dev!=id.device||(uint64_t)named.st_ino!=id.inode){if(fd>=0)close(fd);
  return -1;
  }
 return fd;
}

static int pr_sources_validate(pc02_lease *h,const pr_plan *plan,const pr_part *parts,size_t count){
 pc02_identity expected=getid(plan->description.journal_identity),actual;
 struct stat named;
 if(!memchr(plan->description.journal,0,64)||!leaf_ok(plan->description.journal))return 0;
 int journal=openat(h->parent,plan->description.journal,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
 if(journal<0||!metadata(journal,1,1,&actual)||!sameid(&actual,&expected)||
    fstatat(h->parent,plan->description.journal,&named,AT_SYMLINK_NOFOLLOW)||
    (uint64_t)named.st_dev!=actual.device||(uint64_t)named.st_ino!=actual.inode){
  if(journal>=0)close(journal);
  return 0;
 }
 int ok=1;
 for(size_t k=0;k<count;k++){
  const pr_part *p=&parts[k];
  if(p->space!=PR_ROUTE&&p->space!=PR_JOURNAL){ok=0;
  break;
  }
  if(p->role==PR_STATE||p->role==PR_HEAD||p->role==PR_BINDING)continue;
  if((p->role==PR_ACK)!=(p->space==PR_JOURNAL)||p->role<PR_INPUT||p->role>PR_FLOOR){ok=0;
  break;
  }
  int directory=p->space==PR_ROUTE?h->route_dir:journal;
  int fd=regular_open(directory,p->leaf,O_RDONLY,1,NULL);
  pc02rp_blob raw={0};
  expected=getid(p->identity);
  if(fd<0||!pc02rp_read_raw(fd,PR_LIMIT,&raw)||!sameid(&raw.info.identity,&expected)||
     raw.bytes!=get64(p->bytes)||memcmp(raw.info.sha256,p->sha256,65))ok=0;
  pc02rp_free(&raw);
  if(fd>=0&&close(fd))ok=0;
  if(!ok)break;
 }
 if(close(journal))ok=0;
 return ok;
}

static int pr_parts_validate(pc02_lease *h,const pr_plan *plan,const pr_part *parts,size_t count){
 if(count!=get64(plan->part_count)||!count||count>PR_PARTS)return 0;
 pc02_identity route=getid(plan->route_identity);
 if(!sameid(&route,&h->route_id)||!binding_valid(h,plan->origin_binding))return 0;
 int directory=pr_archive_open(h,plan);
 if(directory<0)return 0;
 int ok=1;
 for(size_t k=0;k<count;k++){
  const pr_part *part=&parts[k];
  pc02_identity expected=getid(part->saved_identity);
  pc02rp_blob raw={0};
  if(!memchr(part->saved_leaf,0,sizeof(part->saved_leaf))||!leaf_ok(part->saved_leaf)||
     !memchr(part->leaf,0,sizeof(part->leaf))||!leaf_ok(part->leaf)||!nonzero(part->sha256)||
     !nonzero(part->saved_sha256)||get64(part->bytes)!=get64(part->saved_bytes)||
     memcmp(part->sha256,part->saved_sha256,65)){ok=0;
     break;
     }
  int fd=regular_open(directory,part->saved_leaf,O_RDONLY,1,NULL);
  if(fd<0||!pc02rp_read_raw(fd,PR_LIMIT,&raw)||!sameid(&raw.info.identity,&expected)||
    raw.info.bytes!=get64(part->saved_bytes)||memcmp(raw.info.sha256,part->saved_sha256,65))ok=0;
  pc02rp_free(&raw);
  if(fd>=0&&close(fd))ok=0;
  if(!ok)break;
 }
 if(close(directory))ok=0;
 return ok&&pr_sources_validate(h,plan,parts,count);
}
static int pr_plan_read(pc02_lease *h,unsigned sequence,pc02rp_blob *raw,pr_ref *ref,pr_plan **plan,pr_part **parts){
 if(!pr_read_named(h,"repair-plan",PR_PLAN,sequence,raw,ref)||raw->bytes<sizeof(pr_plan))return 0;
 *plan=(pr_plan *)raw->data;
 size_t count=(size_t)get64((*plan)->part_count);
 if(get64((*plan)->sequence)!=sequence||!count||count>PR_PARTS||
    raw->bytes!=sizeof(pr_plan)+count*sizeof(pr_part))return 0;
 *parts=(pr_part *)(raw->data+sizeof(pr_plan));
 return pr_parts_validate(h,*plan,*parts,count);
}
static int pr_plan_shape(const pr_plan *p){
 uint64_t sk=get64(p->state_keep),hk=get64(p->head_keep),se=get64(p->state_extra),he=get64(p->head_extra);
 return sk&&sk<=PR_LIMIT&&se<=PR_LIMIT-sk&&hk>=464&&hk<=PR_LIMIT&&he<=PR_LIMIT-hk&&sk%S_BYTES==0&&(hk-464)%272==0&&(se==0||se==S_BYTES)&&he==0&&
  nonzero(p->state_target_sha256)&&nonzero(p->head_target_sha256)&&
  p->before_begin<=1&&p->publish_intent<=1&&p->committed<=1&&p->aborted<=1&&p->terminal<=1;
}
static const pr_part *pr_part_role(const pr_part *p,size_t count,unsigned role){
 const pr_part *found=NULL;
 for(size_t k=0;k<count;k++)if(p[k].role==role){if(found)return NULL;
 found=&p[k];
 }
 return found;
}

static void pr_context_free(pr_context *c){
 if(!c)return;
 pc02rp_free(&c->state_raw);
 pc02rp_free(&c->head_raw);
 pc02rp_free(&c->input_raw);
 pc02rp_free(&c->prepared_raw);
 for(unsigned k=0;k<256;k++){pc02rp_free(&c->acks[k]);
 pc02rp_free(&c->floors[k]);
 }
 if(c->head>=0)close(c->head);
 if(c->journal>=0)close(c->journal);
 if(c->archive>=0)close(c->archive);
 destroy(c->h);
 free(c);
}
static pr_context *pr_open(const char *root,const char *library,const pc02_controls *controls){
 pr_context *c=calloc(1,sizeof(*c));
 if(!c)return NULL;
 c->head=c->journal=c->archive=-1;
 c->h=allocate();
 if(!c->h)goto fail;
 c->h->mode=PC02_RECOVER;
 if(controls)c->h->controls=*controls;
 if(!root_open(c->h,root,0)||!library_parent(c->h,library)||!open_route(c->h,0))goto fail;
 c->h->binding_file=regular_open(c->h->route_dir,"binding",O_RDONLY,1,&c->h->binding_id);
 if(c->h->binding_file<0||!read_record(c->h->binding_file,c->h->binding,B_BYTES)||
    !binding_valid(c->h,c->h->binding))goto fail;
 pc02_identity self=getid(c->h->binding+224);
 if(!sameid(&self,&c->h->binding_id)||!pc02rp_read_raw(c->h->state_file,PR_LIMIT,&c->state_raw))goto fail;
 pc02rs_blob state_blob={c->state_raw.info.identity,c->state_raw.data,c->state_raw.bytes};
 if(!sameid(&state_blob.identity,&c->h->state_id)||!pc02rs_state_prefix(&state_blob,&c->state))goto fail;
 c->h->seen.kind=c->state.kind;
 c->h->seen.sequence=c->state.sequence;
 c->h->seen.generation=c->state.generation;
 c->h->seen.target=c->state.target;
 c->h->seen.pending=c->state.pending;
 memcpy(c->h->seen.seal,c->state.seal,65);
 memcpy(c->h->seen.previous_clean,c->state.previous_clean,65);
 memcpy(c->h->seen.terminal,c->state.terminal,65);
 if(flock(c->h->registry,LOCK_UN))goto fail;
 return c;
fail:pr_context_free(c);
return NULL;
}
static int pr_raw_at(int directory,const char *leaf,pc02rp_blob *raw){
 int fd=regular_open(directory,leaf,O_RDONLY,1,NULL);
 int ok=fd>=0&&pc02rp_read_raw(fd,PR_LIMIT,raw);
 if(fd>=0&&close(fd))ok=0;
 return ok;
}
static int pr_meta(pr_context *c,const char *leaf,unsigned kind,uint64_t generation,const char *input,
 const char *pending,const unsigned char *origin,pc02rp_blob *out){
 if(!pr_raw_at(c->h->route_dir,leaf,out))return 0;
 const unsigned char *b=out->data;
 char sha[65],zero[65];
 zero_sha(zero);
 size_t n=out->bytes;
 if(n<PM_HEAD+64||n>PM_HEAD+PM_LIMIT+64||memcmp(b,"PC02M001",8)||get64(b+8)!=kind||
    get64(b+16)!=generation||get64(b+24)!=n-PM_HEAD-64||get64(b+480)||
    !binding_valid(c->h,b+48)||memcmp(b+352,input,64)||
    memcmp(b+416,kind==PC02_META_INPUT?zero:pending,64))goto invalid;
 pc02_identity self=getid(b+32);
 if(!sameid(&self,&out->info.identity))goto invalid;
 wh_sha256_hex(b,n-64,sha);
 if(memcmp(sha,b+n-64,64))goto invalid;
 wh_sha256_hex(b+PM_HEAD,n-PM_HEAD-64,sha);
 if(memcmp(sha,b+488,64)||(kind==PC02_META_INPUT&&memcmp(sha,input,64))||
    (origin&&memcmp(origin,b+48,B_BYTES)))goto invalid;
 return 1;
invalid:pc02rp_free(out);
return 0;
}
static int pr_origin(pr_context *c){
 const unsigned char *origin=c->input_raw.data+48;
 pc02_repair_description *d=&c->description;
 if(memcmp(d->original_grant,origin+88,8)||memcmp(d->original_grant+8,origin+96,64)||
    memcmp(d->original_grant+72,origin+40,16))return 0;
 if(c->before_begin){
  if(memcmp(origin,c->h->binding,B_BYTES)||c->state.kind=='B'||c->state.generation==UINT64_MAX||
     c->pending.generation!=c->state.generation+1)return 0;
 }
 else{
  uint64_t g=c->pending.generation;
  if(!g||get64(origin+88)!=g-1||g>UINT64_MAX/2)return 0;
  uint64_t offset=(g*2-1)*S_BYTES;
  if(offset>c->state_raw.bytes||c->state_raw.bytes-offset<S_BYTES)return 0;
  const unsigned char *begin=c->state_raw.data+(size_t)offset;
  if(begin[8]!='B'||memcmp(begin+S_SEAL,c->pending.seal,64)||memcmp(begin+224,origin+40,16)||memcmp(begin+240,origin+96,64))return 0;
  uint64_t current=get64(c->h->binding+88);
  if(current==g-1){if(memcmp(origin,c->h->binding,B_BYTES))return 0;
  }
  else if(current!=g)return 0;
 }
 memcpy(c->origin_binding,origin,B_BYTES);
 return 1;
}
static void pr_native_member(const pc02_repair_member *w,pc02_member *out){
 memset(out,0,sizeof(*out));
 memcpy(out->target,w->target,256);
 memcpy(out->stage,w->stage,256);
 memcpy(out->retained,w->retained,256);
 out->original_present=w->original_present;
 out->original=getid(w->original);
 out->prepared=getid(w->prepared);
}
static int pr_desc(pr_context *c){
 pc02_repair_description *d=&c->description;
 wh_binding b;
 wh_gates g;
 char manifest[EXR_WH_LINE_MAX],sha[65];
 memset(d,0,sizeof(*d));
 const void *prepared=c->prepared_raw.data?c->prepared_raw.data+PM_HEAD:NULL;
 size_t prepared_bytes=c->prepared_raw.data?c->prepared_raw.bytes-PM_HEAD-64:0;
 if(!c->schema(c->context,c->input_raw.data+PM_HEAD,c->input_raw.bytes-PM_HEAD-64,prepared,prepared_bytes,d))return 0;
 memcpy(&b,d->binding,sizeof(b));
 memcpy(&g,d->gates,sizeof(g));
 if(!wh_manifest(&b,&g,manifest)||d->mirror_present>1||d->has_prepared>1||
    !memchr(d->journal,0,64)||!leaf_ok(d->journal)||!memchr(d->pack_leaf,0,64)||!leaf_ok(d->pack_leaf)||
    !memchr(d->token,0,49)||strlen(d->token)!=48||strspn(d->token,"0123456789abcdef")!=48||
    d->has_prepared!=(prepared!=NULL))return 0;
 wh_sha256_hex(manifest,strlen(manifest),sha);
 if(c->before_begin)memcpy(c->pending.manifest,sha,65);
 else if(memcmp(sha,c->pending.manifest,65))return 0;
 for(unsigned k=0;k<2;k++){
  pc02_member m;
  pr_native_member(&d->members[k],&m);
  unsigned char saved_kind=c->h->seen.kind;
  if(c->before_begin)c->h->seen.kind='I';
  int member_names=pm_member_names(c->h,&m);
  c->h->seen.kind=saved_kind;
  if(!member_names||m.original_present!=(!k||d->mirror_present)||
     memcmp(d->members[k].original,d->original[k].identity,16)||
     (d->has_prepared&&memcmp(d->members[k].prepared,d->prepared[k].identity,16)))return 0;
 }
 if(memcmp(d->original[0].identity,d->original_grant+72,16))return 0;
 return pr_origin(c);
}
static int pr_select_input(pr_context *c,const char *leaf,uint64_t generation,const char input[65]){
 pc02rp_free(&c->input_raw);
 pc02rp_free(&c->prepared_raw);
 if(strlen(leaf)>=sizeof(c->input_leaf)||!pr_meta(c,leaf,PC02_META_INPUT,generation,input,NULL,NULL,&c->input_raw))return 0;
 strcpy(c->input_leaf,leaf);
 c->pending.generation=generation;
 memcpy(c->pending.input,input,65);
 if(!c->before_begin)c->pending=c->state.pending;
 if(!pm_name(PC02_META_PREPARED,generation,input,0,c->prepared_leaf))return 0;
 if(!missing(c->h->route_dir,c->prepared_leaf)){
  if(c->before_begin||!pr_meta(c,c->prepared_leaf,PC02_META_PREPARED,generation,input,c->pending.seal,
   c->input_raw.data+48,&c->prepared_raw))return 0;
 }
 if(!pr_desc(c))return 0;
 if(c->before_begin){
  unsigned char expected[S_BYTES];
  pc02rs_blob state={c->state_raw.info.identity,c->state_raw.data,c->state_raw.bytes};
  char empty_terminal[65];zero_sha(empty_terminal);
  if(!pc02rs_state_next(&c->state,'B',c->pending.manifest,c->pending.input,empty_terminal,&c->state.target,expected)||
     !pc02rs_state_tail(&state,&c->state,expected))return 0;
  memcpy(c->pending.seal,expected+S_SEAL,64);
  c->pending.seal[64]=0;
 }
 return 1;
}
static int pr_choose_input(pr_context *c){
 if(c->state.kind=='B'||(c->state.kind=='C'&&!c->state.tail_bytes)){
  char leaf[128];
  c->before_begin=0;
  c->pending=c->state.pending;
  return pm_name(PC02_META_INPUT,c->pending.generation,c->pending.input,0,leaf)&&
   pr_select_input(c,leaf,c->pending.generation,c->pending.input);
 }
 if(!c->state.tail_bytes||c->state.kind=='B'||c->state.generation==UINT64_MAX)return 0;
 c->before_begin=1;
 uint64_t generation=c->state.generation+1;
 char prefix[64],chosen[128]={0},input[65]={0};
 unsigned found=0;
 int n=snprintf(prefix,sizeof(prefix),"input-%016llx-",(unsigned long long)generation);
 if(n<=0||n>=(int)sizeof(prefix))return 0;
 int fd=openat(c->h->route_dir,".",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
 if(fd<0)return 0;
 DIR *directory=fdopendir(fd);
 if(!directory){close(fd);
 return 0;
 }
 int ok=0;
 for(;;){
  errno=0;
  struct dirent *entry=readdir(directory);
  if(!entry){if(errno)goto finish;
  break;
  }
  if(strncmp(entry->d_name,prefix,(size_t)n))continue;
  const char *sha=entry->d_name+n;
  if(strlen(sha)!=64||strspn(sha,"0123456789abcdef")!=64)goto finish;
  char candidate[65];
  memcpy(candidate,sha,65);
  if(pr_select_input(c,entry->d_name,generation,candidate)){
   if(++found>1)goto finish;
   strcpy(chosen,entry->d_name);
   memcpy(input,candidate,65);
  }
 }
 if(found==1)ok=pr_select_input(c,chosen,generation,input);
finish:
 if(closedir(directory))ok=0;
 return ok;
}
static int pr_collect(pr_context *c){
 pc02_identity head_id=getid(c->input_raw.data+552),journal_id=getid(c->description.journal_identity),observed;
 struct stat named;
 if(!pm_head_name(c->pending.generation,c->pending.input,c->head_leaf))return 0;
 c->head=regular_open(c->h->route_dir,c->head_leaf,O_RDWR,1,&observed);
 if(c->head<0||!sameid(&head_id,&observed)||!pc02rp_read_raw(c->head,PR_LIMIT,&c->head_raw))return 0;
 c->journal=openat(c->h->parent,c->description.journal,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
 if(c->journal<0||!metadata(c->journal,1,1,&observed)||!sameid(&journal_id,&observed)||
  fstatat(c->h->parent,c->description.journal,&named,AT_SYMLINK_NOFOLLOW)||
  (uint64_t)named.st_dev!=observed.device||(uint64_t)named.st_ino!=observed.inode)return 0;
 unsigned char seen[257]={0};
 unsigned largest=0;
 int fd=openat(c->journal,".",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
 if(fd<0)return 0;
 DIR *dir=fdopendir(fd);
 if(!dir){close(fd);
 return 0;
 }
 int ok=0;
 for(;;){
  errno=0;
  struct dirent *e=readdir(dir);
  if(!e){if(errno)goto done;
  break;
  }
  const char *name=e->d_name;
  if(!strcmp(name,".")||!strcmp(name,".."))continue;
  if(!strncmp(name,".pending-",9)){
   const char *v=name+9;
   char *end=NULL;
   if(*v<'1'||*v>'9')goto done;
   errno=0;
   unsigned long long pid=strtoull(v,&end,10);
   if(errno||!pid||!end||*end!='-'||end[1]<'1'||end[1]>'9')goto done;
   v=end+1;
   errno=0;
   unsigned long long serial=strtoull(v,&end,10);
   if(errno||!serial||!end||*end)goto done;
   int temp=regular_open(c->journal,name,O_RDONLY,1,NULL);
   if(temp<0)goto done;
   if(close(temp))goto done;
   continue;
  }
  if(strlen(name)!=7||strncmp(name,"ack-",4)||strspn(name+4,"0123456789")!=3)goto done;
  unsigned k=(unsigned)strtoul(name+4,NULL,10);
  if(!k||k>256||seen[k])goto done;
  seen[k]=1;
  if(k>largest)largest=k;
  if(!pr_raw_at(c->journal,name,&c->acks[k-1]))goto done;
 }
 for(unsigned k=1;k<=largest;k++)if(!seen[k])goto done;
 c->ack_count=largest;
 ok=1;
done:
 if(closedir(dir))ok=0;
 if(!ok)return 0;
 unsigned floor_count=0;
 if(!pm_floor_slots(c->h,c->pending.generation,&floor_count))return 0;
 c->floor_count=floor_count;
 for(unsigned k=1;k<=floor_count;k++){char leaf[128];
 if(!pm_name(PM_FLOOR,c->pending.generation,c->pending.input,k,leaf)||
  !pr_raw_at(c->h->route_dir,leaf,&c->floors[k-1]))return 0;
  }
 unsigned char header[464]={0};
 memcpy(header,"PC02F001",8);
 put64(header+8,c->pending.generation);
 memcpy(header+16,c->pending.input,64);
 memcpy(header+80,c->origin_binding,B_BYTES);
 putid(header+384,&head_id);
 seal(header,400);
 pc02rs_blob acks[256],floors[256],head={c->head_raw.info.identity,c->head_raw.data,c->head_raw.bytes};
 for(unsigned k=0;k<largest;k++){acks[k].identity=c->acks[k].info.identity;
 acks[k].data=c->acks[k].data;
 acks[k].bytes=c->acks[k].bytes;
 }
 for(unsigned k=0;k<floor_count;k++){floors[k].identity=c->floors[k].info.identity;
 floors[k].data=c->floors[k].data;
 floors[k].bytes=c->floors[k].bytes;
 }
 wh_binding b;
 wh_gates g;
 memcpy(&b,c->description.binding,sizeof(b));
 memcpy(&g,c->description.gates,sizeof(g));
 if(!pc02rs_transaction(&head,header,floors,floor_count,acks,largest,&b,&g,&c->pending,&c->tx))return 0;
 if(c->before_begin){
  if(largest||floor_count||c->tx.head_count||c->tx.head_tail_bytes)return 0;
  for(unsigned k=0;k<2;k++){
   int stage=regular_open(c->h->parent,c->description.members[k].stage,O_RDONLY,1,NULL);
   struct stat s;
   int empty=stage>=0&&!fstat(stage,&s)&&!s.st_size;
   if(stage>=0&&close(stage))empty=0;
   if(!empty)return 0;
  }
 }
 else if(c->state.tail_bytes){
  if(c->state.kind!='B'||c->tx.head_tail_bytes||!c->tx.terminal||
     c->tx.head_count!=floor_count||floor_count!=largest)return 0;
 }
 else if(c->state.kind=='C'&&c->tx.head_tail_bytes)return 0;
 return 1;
}

static int pr_current_members(pr_context *c,unsigned states[2]){
 for(unsigned k=0;k<2;k++){
  pc02_member m;
  pr_native_member(&c->description.members[k],&m);
  int stage=pm_member_entry(c->h,m.stage,&m.prepared,1),stage_absent=missing(c->h->parent,m.stage);
  int prepared=pm_member_entry(c->h,m.target,&m.prepared,1),target_absent=missing(c->h->parent,m.target);
  int retained_absent=missing(c->h->parent,m.retained);
  if(!m.original_present){
   if(!retained_absent)return 0;
   if(stage&&target_absent)states[k]=0;
   else if(stage_absent&&prepared)states[k]=2;
   else return 0;
  }
  else{
   int original=pm_member_entry(c->h,m.target,&m.original,0),retained=pm_member_entry(c->h,m.retained,&m.original,0);
   if(stage&&original&&retained_absent)states[k]=0;
   else if(stage&&target_absent&&retained)states[k]=1;
   else if(stage_absent&&prepared&&retained)states[k]=2;
   else return 0;
  }
 }
 if(c->before_begin||!c->tx.publish_intent){if(states[0]||states[1])return 0;
 }
 else if(!c->description.has_prepared||(states[0]!=2&&states[1]!=0))return 0;
 if(c->tx.committed&&(states[0]!=2||states[1]!=2))return 0;
 if(c->tx.aborted&&(states[0]||states[1]))return 0;
 return 1;
}
static int pr_fill_plan(pr_context *c,pr_plan *p,unsigned sequence,unsigned first,const pr_ref *previous,const pr_ref *previous_done){
 memset(p,0,sizeof(*p));
 put64(p->sequence,sequence);
 put64(p->first,first);
 putid(p->route_identity,&c->h->route_id);
 if(previous)p->previous_plan=*previous;
 if(previous_done)p->previous_done=*previous_done;
 memcpy(p->origin_binding,c->origin_binding,B_BYTES);
 p->description=c->description;
 put64(p->generation,c->pending.generation);
 memcpy(p->pending_seal,c->pending.seal,65);
 memcpy(p->manifest,c->pending.manifest,65);
 memcpy(p->input,c->pending.input,65);
 memcpy(p->terminal_sha256,c->tx.last_line_sha256,65);
 p->before_begin=(unsigned char)c->before_begin;
 p->publish_intent=(unsigned char)c->tx.publish_intent;
 p->committed=(unsigned char)c->tx.committed;
 p->aborted=(unsigned char)c->tx.aborted;
 p->terminal=(unsigned char)c->tx.terminal;
 unsigned states[2];
 if(!pr_current_members(c,states))return 0;
 p->member_states[0]=(unsigned char)states[0];
 p->member_states[1]=(unsigned char)states[1];
 if(c->state.tail_bytes&&c->tx.head_tail_bytes)return 0;
 put64(p->state_keep,c->state.keep_bytes);
 put64(p->head_keep,c->tx.head_keep_bytes);
 if(c->state.tail_bytes&&!c->before_begin){
  if(!c->tx.terminal||c->tx.committed==c->tx.aborted)return 0;
  pc02_identity target=getid(c->tx.committed?c->description.prepared[0].identity:c->description.original[0].identity);
  pc02rs_blob state={c->state_raw.info.identity,c->state_raw.data,c->state_raw.bytes};
  if(!pc02rs_state_next(&c->state,'C',c->pending.manifest,c->pending.input,c->tx.last_line_sha256,&target,p->state_record)||
     !pc02rs_state_tail(&state,&c->state,p->state_record))return 0;
  uint64_t generation=get64(c->h->binding+88);
  if(generation==c->pending.generation){
   pc02_identity bound=getid(c->h->binding+40);
   if(memcmp(c->h->binding+96,p->state_record+S_SEAL,64)||!sameid(&target,&bound))return 0;
   put64(p->state_extra,S_BYTES);
  }
  else if(generation+1!=c->pending.generation||memcmp(c->h->binding,c->origin_binding,B_BYTES))return 0;
 }
 if(c->tx.head_tail_bytes)memcpy(p->head_record,c->tx.next_head,272);
 size_t state_size=(size_t)get64(p->state_keep)+(size_t)get64(p->state_extra);
 unsigned char *target=malloc(state_size);
 if(!target)return 0;
 memcpy(target,c->state_raw.data,(size_t)get64(p->state_keep));
 if(get64(p->state_extra))memcpy(target+get64(p->state_keep),p->state_record,S_BYTES);
 wh_sha256_hex(target,state_size,p->state_target_sha256);
 free(target);
 wh_sha256_hex(c->head_raw.data,(size_t)get64(p->head_keep),p->head_target_sha256);
 return pr_plan_shape(p);
}
static int pr_archive_create(pr_context *c,pr_plan *p){
 char leaf[96];
 pc02_identity id;
 int fd=-1;
 for(unsigned k=0;k<1024;k++){
  int n=snprintf(leaf,sizeof(leaf),"repair-archive-%06u-%ld-%u",(unsigned)get64(p->sequence),(long)getpid(),k);
  if(n<=0||n>=(int)sizeof(leaf))return 0;
  if(!mkdirat(c->h->route_dir,leaf,0700))break;
  if(errno!=EEXIST||k==1023)return 0;
 }
 fd=openat(c->h->route_dir,leaf,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
 if(fd<0||!metadata(fd,1,1,&id)||fsync(fd)||fsync(c->h->route_dir)){if(fd>=0)close(fd);
 return 0;
 }
 c->archive=fd;
 strcpy(p->archive_leaf,leaf);
 putid(p->archive_identity,&id);
 return directory_path(fd,c->archive_path);
}
static int pr_save_part(pr_context *c,pr_part *out,unsigned space,unsigned role,const char *leaf,int source,const pc02rp_info *expected,unsigned index){
 memset(out,0,sizeof(*out));
 if(strlen(leaf)>=sizeof(out->leaf))return 0;
 strcpy(out->leaf,leaf);
 out->space=(unsigned char)space;
 out->role=(unsigned char)role;
 int n=snprintf(out->saved_leaf,sizeof(out->saved_leaf),"raw-%04u",index);
 if(n<=0||n>=(int)sizeof(out->saved_leaf))return 0;
 pc02rp_info original,saved;
 if(!pc02rp_archive(source,c->archive,out->saved_leaf,PR_LIMIT,&original,&saved)||
    !sameid(&original.identity,&expected->identity)||original.bytes!=expected->bytes||
    memcmp(original.sha256,expected->sha256,65))return 0;
 putid(out->identity,&original.identity);
 put64(out->bytes,original.bytes);
 memcpy(out->sha256,original.sha256,65);
 putid(out->saved_identity,&saved.identity);
 put64(out->saved_bytes,saved.bytes);
 memcpy(out->saved_sha256,saved.sha256,65);
 return 1;
}
static int pr_save_named(pr_context *c,pr_part *part,unsigned space,unsigned role,const char *leaf,const pc02rp_info *expected,unsigned index){
 int dir=space==PR_ROUTE?c->h->route_dir:c->journal;
 int fd=regular_open(dir,leaf,O_RDONLY,1,NULL);
 int ok=fd>=0&&pr_save_part(c,part,space,role,leaf,fd,expected,index);
 if(fd>=0&&close(fd))ok=0;
 return ok;
}
static int pr_archive_all(pr_context *c,pr_plan *p,pr_part *parts,size_t *count){
 size_t n=0;
 pc02rp_blob binding={0};
 if(!pr_archive_create(c,p)||!pc02rp_read_raw(c->h->binding_file,PR_LIMIT,&binding))goto bad;
 if(!pr_save_part(c,&parts[n],PR_ROUTE,PR_STATE,"state",c->h->state_file,&c->state_raw.info,(unsigned)n))goto bad;
 n++;
 if(!pr_save_part(c,&parts[n],PR_ROUTE,PR_HEAD,c->head_leaf,c->head,&c->head_raw.info,(unsigned)n))goto bad;
 n++;
 if(!pr_save_part(c,&parts[n],PR_ROUTE,PR_BINDING,"binding",c->h->binding_file,&binding.info,(unsigned)n))goto bad;
 n++;
 if(!pr_save_named(c,&parts[n],PR_ROUTE,PR_INPUT,c->input_leaf,&c->input_raw.info,(unsigned)n))goto bad;
 n++;
 if(c->prepared_raw.data){
  if(!pr_save_named(c,&parts[n],PR_ROUTE,PR_PREPARED,c->prepared_leaf,&c->prepared_raw.info,(unsigned)n))goto bad;
  n++;
 }
 for(unsigned k=0;k<c->ack_count;k++){
  char leaf[32];
  snprintf(leaf,sizeof(leaf),"ack-%03u",k+1);
  if(!pr_save_named(c,&parts[n],PR_JOURNAL,PR_ACK,leaf,&c->acks[k].info,(unsigned)n))goto bad;
  n++;
 }
 for(unsigned k=0;k<c->floor_count;k++){
  char leaf[128];
  if(!pm_name(PM_FLOOR,c->pending.generation,c->pending.input,k+1,leaf)||
   !pr_save_named(c,&parts[n],PR_ROUTE,PR_FLOOR,leaf,&c->floors[k].info,(unsigned)n))goto bad;
   n++;
 }
 put64(p->part_count,n);
 *count=n;
 pc02rp_free(&binding);
 if(fsync(c->archive)||fsync(c->h->route_dir)||!pr_parts_validate(c->h,p,parts,n))return 0;
 phase(c->h,PC02_REPAIR_ARCHIVE_DURABLE);
 return 1;
bad:pc02rp_free(&binding);
return 0;
}
static int pr_source_immutable(pr_context *c,const pr_part *parts,size_t count){
 for(size_t k=0;k<count;k++){
  if(parts[k].role==PR_STATE||parts[k].role==PR_HEAD||parts[k].role==PR_BINDING)continue;
  int dir=parts[k].space==PR_ROUTE?c->h->route_dir:c->journal;
  pc02rp_blob raw={0};
  int fd=regular_open(dir,parts[k].leaf,O_RDONLY,1,NULL);
  pc02_identity expected=getid(parts[k].identity);
  int ok=fd>=0&&pc02rp_read_raw(fd,PR_LIMIT,&raw)&&sameid(&raw.info.identity,&expected)&&
   raw.info.bytes==get64(parts[k].bytes)&&!memcmp(raw.info.sha256,parts[k].sha256,65);
  pc02rp_free(&raw);
  if(fd>=0&&close(fd))ok=0;
  if(!ok)return 0;
 }
 return 1;
}
static int pr_prove(pr_context *c,const pr_plan *p){
 pc02_repair_view view;
 memset(&view,0,sizeof(view));
 view.library=c->h->library;
 view.archive_directory=c->archive_path;
 view.parent_directory=c->h->parent;
 view.archive_directory_fd=c->archive;
 view.description=&p->description;
 view.pending.generation=get64(p->generation);
 memcpy(view.pending.seal,p->pending_seal,65);
 memcpy(view.pending.manifest,p->manifest,65);
 memcpy(view.pending.input,p->input,65);
 view.before_begin=p->before_begin;
 view.publish_intent=p->publish_intent;
 view.committed=p->committed;
 view.aborted=p->aborted;
 view.terminal=p->terminal;
 view.member_states[0]=p->member_states[0];
 view.member_states[1]=p->member_states[1];
 memcpy(view.terminal_sha256,p->terminal_sha256,65);
 return c->prove&&c->prove(c->context,&view);
}


typedef struct {
 unsigned last,last_done,first,active;
 pr_ref latest_ref,applied_ref,done_ref,guard_ref;
 pc02rp_blob latest;
 pr_plan *plan;
 pr_part *parts;
}
pr_ledger;
static int pr_zero_ref(const pr_ref *r){pr_ref zero={0};
return !memcmp(r,&zero,sizeof(zero));
}
static int pr_equal_ref(const pr_ref *a,const pr_ref *b){return !memcmp(a,b,sizeof(*a));
}
static int pr_guard_name(unsigned first,char out[96]){
 int n=snprintf(out,96,"repair-guard-%06u.retired",first);
 return first&&first<=PR_PLANS&&n>0&&n<96;
}
static int pr_guard_read(pc02_lease *h,const pr_ref *ref,unsigned first,pc02rp_blob *raw){
 pr_ref locate=*ref;
 if(!pr_ref_valid(ref)||strcmp(ref->leaf,"repair.guard"))return 0;
 if(!missing(h->route_dir,"repair.guard")&&pr_read_object(h,&locate,PR_GUARD,first,raw))return 1;
 pc02rp_free(raw);
 if(!pr_guard_name(first,locate.leaf))return 0;
 return pr_read_object(h,&locate,PR_GUARD,first,raw);
}
static int pr_guard_matches(pc02_lease *h,const pr_plan *plan,const pr_part *parts,size_t count){
 pc02rp_blob guard={0};
 int ok=0;
 unsigned first=(unsigned)get64(plan->first);
 if(!pr_guard_read(h,&plan->guard,first,&guard)||guard.bytes!=sizeof(*plan)+count*sizeof(*parts))goto done;
 pr_plan proposed=*(pr_plan *)guard.data,expected=*plan;
 memset(&expected.guard,0,sizeof(expected.guard));
 if(memcmp(&proposed,&expected,sizeof(expected))||memcmp(guard.data+sizeof(expected),parts,count*sizeof(*parts)))goto done;
 ok=1;
done:pc02rp_free(&guard);
return ok;
}
static int pr_head_prefix(pc02_lease *h,const pr_plan *p,const unsigned char id[16],uint64_t bytes,const char sha[65]){
 char leaf[128];
 pc02_identity actual=getid(id);
 if(!pm_head_name(get64(p->generation),p->input,leaf))return 0;
 int fd=regular_open(h->route_dir,leaf,O_RDONLY,1,NULL);
 int ok=fd>=0&&pr_blob_prefix(fd,bytes,sha,&actual);
 if(fd>=0&&close(fd))ok=0;
 return ok;
}
static int pr_applied_read(pc02_lease *h,unsigned seq,const pr_ref *plan,pc02rp_blob *raw,pr_ref *ref){
 if(!pr_read_named(h,"repair-applied",PR_APPLIED,seq,raw,ref)||raw->bytes!=sizeof(pr_applied))return 0;
 return pr_equal_ref(&((pr_applied *)raw->data)->plan,plan);
}
static int pr_minimum(pc02_lease *h,const pr_plan *plan,const pr_part *parts,size_t count,const pr_applied *applied){
 const pr_part *state_part=pr_part_role(parts,count,PR_STATE),*head_part=pr_part_role(parts,count,PR_HEAD);
 if(!state_part||!head_part||memcmp(applied->state_identity,state_part->identity,16)||
    memcmp(applied->head_identity,head_part->identity,16)||
    get64(applied->state_bytes)!=get64(plan->state_keep)+get64(plan->state_extra)||
    get64(applied->head_bytes)!=get64(plan->head_keep)+get64(plan->head_extra)||
    memcmp(applied->state_sha256,plan->state_target_sha256,65)||
    memcmp(applied->head_sha256,plan->head_target_sha256,65))return 0;
 pc02_identity expected=getid(applied->state_identity);
 return pr_blob_prefix(h->state_file,get64(applied->state_bytes),applied->state_sha256,&expected)&&
  pr_head_prefix(h,plan,applied->head_identity,get64(applied->head_bytes),applied->head_sha256);
}
static int pr_done_read(pc02_lease *h,unsigned last,pr_ledger *l,const pr_ref *previous,pc02rp_blob *out,pr_ref *ref){
 if(!pr_read_named(h,"repair-done",PR_DONE,last,out,ref)||out->bytes!=sizeof(pr_done))return 0;
 const pr_done *d=(const pr_done *)out->data;
 pr_plan *p=l->plan;
 pc02rp_blob applied={0};
 pr_ref applied_ref;
 int ok=0;
 if(get64(d->last)!=last||get64(d->first)!=get64(p->first)||memcmp(d->route_identity,p->route_identity,16)||
    !pr_equal_ref(&d->guard,&p->guard)||!pr_equal_ref(&d->last_plan,&l->latest_ref)||
    !pr_equal_ref(&d->previous_done,previous)||!binding_valid(h,d->binding)||
    !pr_applied_read(h,last,&l->latest_ref,&applied,&applied_ref)||
    !pr_equal_ref(&d->last_applied,&applied_ref)||
    !pr_minimum(h,p,l->parts,(size_t)get64(p->part_count),(const pr_applied *)applied.data))goto done;
 pc02_identity state_id=getid(d->state_identity),binding_target=getid(d->binding+40);
 const pr_part *head_part=pr_part_role(l->parts,(size_t)get64(p->part_count),PR_HEAD);
 if(!head_part||memcmp(d->head_identity,head_part->identity,16))goto done;
 if(!sameid(&state_id,&h->state_id)||get64(d->state_bytes)<get64(p->state_keep)||
    !nonzero(d->state_prefix_sha256)||!nonzero(d->head_prefix_sha256)||
    !pr_blob_prefix(h->state_file,get64(d->state_bytes),d->state_prefix_sha256,&state_id)||
    !pr_head_prefix(h,p,d->head_identity,get64(d->head_bytes),d->head_prefix_sha256))goto done;
 uint64_t current=get64(h->binding+88),finished=get64(d->binding+88);
 if(current<finished||(current==finished&&memcmp(h->binding,d->binding,B_BYTES)))goto done;
 if(p->before_begin){
  if(memcmp(d->binding,p->origin_binding,B_BYTES)||get64(d->state_bytes)!=get64(p->state_keep))goto done;
 }
 else{
  if(finished!=get64(p->generation)||!binding_target.inode||get64(d->state_bytes)<S_BYTES)goto done;
  unsigned char last_state[S_BYTES];
  if(!io_read(h->state_file,last_state,S_BYTES,(off_t)(get64(d->state_bytes)-S_BYTES))||
     last_state[8]!='C'||get64(last_state+24)!=finished||memcmp(last_state+S_SEAL,d->binding+96,64)||
     memcmp(last_state+224,d->binding+40,16))goto done;
 }
 ok=1;
done:pc02rp_free(&applied);
return ok;
}
static void pr_ledger_free(pr_ledger *l){pc02rp_free(&l->latest);
memset(l,0,sizeof(*l));
}
static int pr_ledger_read(pc02_lease *h,pr_ledger *l){
 memset(l,0,sizeof(*l));
 unsigned named_done=0;
 if(!pr_scan_names(h,&l->last,&named_done))return 0;
 pr_ref previous_plan={0},previous_done={0},epoch_guard={0};
 unsigned first=0,closed=0;
 int ok=0;
 for(unsigned k=1;k<=l->last;k++){
  pc02rp_blob raw={0};
  pr_ref ref;
  pr_plan *p;
  pr_part *parts;
  if(!pr_plan_read(h,k,&raw,&ref,&p,&parts)||!pr_plan_shape(p))goto fail_record;
  if(!pr_equal_ref(&p->previous_plan,&previous_plan)||!pr_equal_ref(&p->previous_done,&previous_done))goto fail_record;
  if(k<l->last){
   pc02rp_blob prior_applied={0};pr_ref prior_ref;
   int retained=pr_applied_read(h,k,&ref,&prior_applied,&prior_ref)&&
    pr_minimum(h,p,parts,(size_t)get64(p->part_count),(const pr_applied *)prior_applied.data);
   pc02rp_free(&prior_applied);if(!retained)goto fail_record;
  }
  if(!first||closed){
   first=k;
   closed=0;
   epoch_guard=p->guard;
   if(get64(p->first)!=first||!pr_guard_matches(h,p,parts,(size_t)get64(p->part_count)))goto fail_record;
  }
  else if(get64(p->first)!=first||!pr_equal_ref(&p->guard,&epoch_guard))goto fail_record;
  pc02rp_free(&l->latest);
  l->latest=raw;
  memset(&raw,0,sizeof(raw));
  l->plan=(pr_plan *)l->latest.data;
  l->parts=(pr_part *)(l->latest.data+sizeof(pr_plan));
  l->latest_ref=ref;
  previous_plan=ref;
  l->first=first;
  l->guard_ref=epoch_guard;
  char done_name[96];
  if(!pr_name("repair-done",k,done_name))goto fail;
  if(!missing(h->route_dir,done_name)){
   pc02rp_blob done_raw={0};
   pr_ref done_ref;
   if(!pr_done_read(h,k,l,&previous_done,&done_raw,&done_ref)){pc02rp_free(&done_raw);
   goto fail;
   }
   pc02rp_free(&done_raw);
   previous_done=done_ref;
   l->last_done=k;
   l->done_ref=done_ref;
   closed=1;
  }
  continue;
fail_record:pc02rp_free(&raw);
goto fail;
 }
 if(l->last_done!=named_done)goto fail;
 l->active=l->last&&!closed;
 if(l->active){
  if(missing(h->route_dir,"repair.guard"))goto fail;
  pc02rp_blob guard={0};
  if(!pr_guard_read(h,&l->guard_ref,l->first,&guard)){pc02rp_free(&guard);
  goto fail;
  }
  pc02rp_free(&guard);
  char applied_name[96];
  if(!pr_name("repair-applied",l->last,applied_name))goto fail;
  if(!missing(h->route_dir,applied_name)){
   pc02rp_blob applied={0};
   if(!pr_applied_read(h,l->last,&l->latest_ref,&applied,&l->applied_ref)||
      !pr_minimum(h,l->plan,l->parts,(size_t)get64(l->plan->part_count),(pr_applied *)applied.data)){
    pc02rp_free(&applied);
    goto fail;
   }
   pc02rp_free(&applied);
  }
 }
 ok=1;
fail:if(!ok)pr_ledger_free(l);
return ok;
}
static int pr_access(pc02_lease *h){
 pr_ledger *l=calloc(1,sizeof(*l));
 if(!l)return 0;
 int ok=pr_ledger_read(h,l);
 if(ok){
  if(!l->last)ok=missing(h->route_dir,"repair.guard");
  else if(l->active)ok=h->mode==PC02_RECOVER&&!pr_zero_ref(&l->applied_ref);
  else ok=missing(h->route_dir,"repair.guard");
 }
 pr_ledger_free(l);
 free(l);
 return ok;
}


static int pr_saved_blob(pc02_lease *h,const pr_plan *p,const pr_part *part,pc02rp_blob *raw){
 int directory=pr_archive_open(h,p);
 if(directory<0)return 0;
 int fd=regular_open(directory,part->saved_leaf,O_RDONLY,1,NULL);
 pc02_identity id=getid(part->saved_identity);
 int ok=fd>=0&&pc02rp_read_raw(fd,PR_LIMIT,raw)&&sameid(&id,&raw->info.identity)&&
  raw->info.bytes==get64(part->saved_bytes)&&!memcmp(raw->info.sha256,part->saved_sha256,65);
 if(fd>=0&&close(fd))ok=0;
 if(close(directory))ok=0;
 if(ok){raw->info.identity=getid(part->identity);
 raw->info.bytes=get64(part->bytes);
 memcpy(raw->info.sha256,part->sha256,65);
 }
 else pc02rp_free(raw);
 return ok;
}
static void pr_observed_state(pr_context *c){
 c->h->seen.kind=c->state.kind;
 c->h->seen.sequence=c->state.sequence;
 c->h->seen.generation=c->state.generation;
 c->h->seen.target=c->state.target;
 c->h->seen.pending=c->state.pending;
 memcpy(c->h->seen.seal,c->state.seal,65);
 memcpy(c->h->seen.previous_clean,c->state.previous_clean,65);
 memcpy(c->h->seen.terminal,c->state.terminal,65);
}
static int pr_restore_context(pr_context *c,const pr_plan *p,const pr_part *parts,size_t count){
 const pr_part *sp=pr_part_role(parts,count,PR_STATE);
 pc02rp_blob archived={0};
 pr_plan *derived=NULL;
 int ok=0;
 if(!sp||!pr_saved_blob(c->h,p,sp,&archived))goto done;
 pc02rp_free(&c->state_raw);
 c->state_raw=archived;
 memset(&archived,0,sizeof(archived));
 pc02rs_blob state={c->state_raw.info.identity,c->state_raw.data,c->state_raw.bytes};
 if(!pc02rs_state_prefix(&state,&c->state))goto done;
 pr_observed_state(c);
 if(!pr_choose_input(c)||!pr_collect(c))goto done;
 derived=malloc(sizeof(*derived));
 if(!derived||!pr_fill_plan(c,derived,(unsigned)get64(p->sequence),
  (unsigned)get64(p->first),&p->previous_plan,&p->previous_done))goto done;
 if(memcmp(&derived->description,&p->description,sizeof(p->description))||
    memcmp(derived->origin_binding,p->origin_binding,B_BYTES)||memcmp(derived->generation,p->generation,8)||
    memcmp(derived->pending_seal,p->pending_seal,65)||memcmp(derived->manifest,p->manifest,65)||
    memcmp(derived->input,p->input,65)||memcmp(derived->terminal_sha256,p->terminal_sha256,65)||
    derived->before_begin!=p->before_begin||derived->publish_intent!=p->publish_intent||
    derived->committed!=p->committed||derived->aborted!=p->aborted||derived->terminal!=p->terminal||
    memcmp(derived->member_states,p->member_states,2)||memcmp(derived->state_keep,p->state_keep,16)||
    memcmp(derived->state_extra,p->state_extra,16)||memcmp(derived->state_target_sha256,p->state_target_sha256,65)||
    memcmp(derived->head_target_sha256,p->head_target_sha256,65)||!pr_source_immutable(c,parts,count))goto done;
 c->archive=pr_archive_open(c->h,p);
 if(c->archive<0||!directory_path(c->archive,c->archive_path))goto done;
 ok=1;
done:free(derived);
pc02rp_free(&archived);
return ok;
}
static int pr_apply_one(pr_context *c,const pr_plan *p,const pr_part *part,int fd,uint64_t keep,uint64_t extra,
 const unsigned char *record,const char target_sha[65]){
 pc02rp_blob original={0},now={0};
 int ok=0;
 unsigned char *target=NULL;
 if(!part||keep>PR_LIMIT||extra>PR_LIMIT-keep||!pr_saved_blob(c->h,p,part,&original)||
    original.bytes<keep||!pc02rp_read_raw(fd,PR_LIMIT,&now)||
    !sameid(&now.info.identity,&original.info.identity))goto done;
 size_t target_size=(size_t)(keep+extra),maximum=original.bytes>target_size?original.bytes:target_size;
 if(now.bytes<keep||now.bytes>maximum)goto done;
 target=malloc(target_size?target_size:1);
 if(!target)goto done;
 memcpy(target,original.data,(size_t)keep);
 if(extra)memcpy(target+keep,record,(size_t)extra);
 char sha[65];
 wh_sha256_hex(target,target_size,sha);
 if(memcmp(sha,target_sha,65))goto done;
 if(extra){
  if(now.bytes>target_size||memcmp(now.data,target,now.bytes))goto done;
 }
 else if(now.bytes>original.bytes||memcmp(now.data,original.data,now.bytes))goto done;
 if(extra&&(!io_write(fd,record,(size_t)extra,(off_t)keep)))goto done;
 if(ftruncate(fd,(off_t)target_size)||fsync(fd)||fsync(c->h->route_dir))goto done;
 pc02rp_free(&now);
 if(!pc02rp_read_raw(fd,PR_LIMIT,&now)||!sameid(&now.info.identity,&original.info.identity)||
    now.bytes!=target_size||memcmp(now.info.sha256,target_sha,65)||memcmp(now.data,target,target_size))goto done;
 ok=1;
done:free(target);
pc02rp_free(&original);
pc02rp_free(&now);
return ok;
}
static int pr_apply(pr_context *c,const pr_plan *p,const pr_part *parts,size_t count,const pr_ref *plan_ref,pr_ref *applied_ref){
 const pr_part *sp=pr_part_role(parts,count,PR_STATE),*hp=pr_part_role(parts,count,PR_HEAD);
 if(!route_current(c->h)||!binding_current(c->h)||!pr_source_immutable(c,parts,count)||
    !pr_prove(c,p)||!route_current(c->h)||!binding_current(c->h)||!pr_source_immutable(c,parts,count))return 0;
 if(!pr_apply_one(c,p,sp,c->h->state_file,get64(p->state_keep),get64(p->state_extra),p->state_record,p->state_target_sha256))return 0;
 phase(c->h,PC02_REPAIR_STATE_APPLIED);
 if(!pr_apply_one(c,p,hp,c->head,get64(p->head_keep),get64(p->head_extra),p->head_record,p->head_target_sha256))return 0;
 phase(c->h,PC02_REPAIR_HEAD_APPLIED);
 pr_applied applied;
 memset(&applied,0,sizeof(applied));
 applied.plan=*plan_ref;
 memcpy(applied.state_identity,sp->identity,16);
 memcpy(applied.head_identity,hp->identity,16);
 put64(applied.state_bytes,get64(p->state_keep)+get64(p->state_extra));
 put64(applied.head_bytes,get64(p->head_keep)+get64(p->head_extra));
 memcpy(applied.state_sha256,p->state_target_sha256,65);
 memcpy(applied.head_sha256,p->head_target_sha256,65);
 char leaf[96];
 if(!pr_name("repair-applied",(unsigned)get64(p->sequence),leaf)||
  !pr_put(c->h,leaf,PR_APPLIED,get64(p->sequence),&applied,sizeof(applied),applied_ref))return 0;
 phase(c->h,PC02_REPAIR_APPLIED_DURABLE);
 return 1;
}
static int pr_guard_retire(pc02_lease *h,const pr_ref *guard,unsigned first){
 char leaf[96];
 pc02rp_blob raw={0};
 int ok=0;
 if(!pr_guard_name(first,leaf))return 0;
 if(missing(h->route_dir,"repair.guard")){
  pr_ref old=*guard;
  strcpy(old.leaf,leaf);
  return pr_read_object(h,&old,PR_GUARD,first,&raw)?(pc02rp_free(&raw),1):0;
 }
 if(!pr_read_object(h,guard,PR_GUARD,first,&raw))goto done;
 pc02rp_free(&raw);
 if(!pm_noreplace(h->route_dir,"repair.guard",leaf)||fsync(h->route_dir))goto done;
 pr_ref retired=*guard;
 strcpy(retired.leaf,leaf);
 if(!pr_read_object(h,&retired,PR_GUARD,first,&raw))goto done;
 phase(h,PC02_REPAIR_RETIRED_DURABLE);
 ok=1;
done:pc02rp_free(&raw);
return ok;
}
static int pr_retire(pc02_lease *h){
 pr_ledger *l=calloc(1,sizeof(*l));
 pc02rp_blob state_raw={0},head_raw={0};
 int ok=0;
 if(!l||h->borrows||!route_current(h)||!binding_current(h)||!pr_ledger_read(h,l))goto done;
 if(!l->last){ok=missing(h->route_dir,"repair.guard");
 goto done;
 }
 if(!l->active){ok=pr_guard_retire(h,&l->guard_ref,l->first);
 goto done;
 }
 pr_plan *p=l->plan;
 if(pr_zero_ref(&l->applied_ref)||!authoritative_state(h,&h->seen)||h->seen.kind=='B')goto done;
 if(p->before_begin){if(memcmp(h->binding,p->origin_binding,B_BYTES)||h->seen.generation+1!=get64(p->generation))goto done;
 }
 else if(h->seen.kind!='C'||h->seen.generation!=get64(p->generation)||
    memcmp(h->seen.pending.seal,p->pending_seal,65)||memcmp(h->seen.pending.input,p->input,65))goto done;
 char head_leaf[128];
 if(!pm_head_name(get64(p->generation),p->input,head_leaf))goto done;
 int fd=regular_open(h->route_dir,head_leaf,O_RDONLY,1,NULL);
 int read_head=fd>=0&&pc02rp_read_raw(fd,PR_LIMIT,&head_raw);
 if(fd>=0&&close(fd))read_head=0;
 if(!read_head||!pc02rp_read_raw(h->state_file,PR_LIMIT,&state_raw))goto done;
 pr_done d;
 memset(&d,0,sizeof(d));
 put64(d.first,l->first);
 put64(d.last,l->last);
 putid(d.route_identity,&h->route_id);
 d.guard=l->guard_ref;
 d.last_plan=l->latest_ref;
 d.last_applied=l->applied_ref;
 d.previous_done=p->previous_done;
 memcpy(d.binding,h->binding,B_BYTES);
 putid(d.state_identity,&state_raw.info.identity);
 put64(d.state_bytes,state_raw.bytes);
 putid(d.head_identity,&head_raw.info.identity);
 put64(d.head_bytes,head_raw.bytes);
 memcpy(d.state_prefix_sha256,state_raw.info.sha256,65);
 memcpy(d.head_prefix_sha256,head_raw.info.sha256,65);
 char leaf[96];
 pr_ref ignored;
 if(!pr_name("repair-done",l->last,leaf)||!pr_put(h,leaf,PR_DONE,l->last,&d,sizeof(d),&ignored)||
    !pr_guard_retire(h,&l->guard_ref,l->first))goto done;
 ok=1;
done:pc02rp_free(&state_raw);
pc02rp_free(&head_raw);
if(l){pr_ledger_free(l);
free(l);
}
return ok;
}


static int pr_commit_orphan_guard(pr_context *c,pr_ledger *l){
 if(l->active||missing(c->h->route_dir,"repair.guard"))return 1;
 if(l->last&&l->last_done==l->last){
  pc02rp_blob old={0};
  if(pr_read_object(c->h,&l->guard_ref,PR_GUARD,l->first,&old)){
   pc02rp_free(&old);
   return pr_guard_retire(c->h,&l->guard_ref,l->first);
  }
  pc02rp_free(&old);
 }
 unsigned seq=l->last+1;
 if(seq>PR_PLANS)return 0;
 pc02rp_blob raw={0};
 pr_ref guard_ref;
 pc02rp_info info;
 if(!pc02rp_read(c->h->route_dir,"repair.guard",PR_GUARD,seq,NULL,&raw)||raw.bytes<sizeof(pr_plan))return 0;
 info=raw.info;
 pr_info_ref(&guard_ref,"repair.guard",&info);
 pr_plan *p=(pr_plan *)raw.data;
 size_t count=(size_t)get64(p->part_count);
 int ok=0;
 if(get64(p->sequence)!=seq||get64(p->first)!=seq||!pr_zero_ref(&p->guard)||
    !pr_equal_ref(&p->previous_plan,&l->latest_ref)||!pr_equal_ref(&p->previous_done,&l->done_ref)||
    !count||count>PR_PARTS||raw.bytes!=sizeof(*p)+count*sizeof(pr_part)||!pr_plan_shape(p)||
    !pr_parts_validate(c->h,p,(pr_part *)(raw.data+sizeof(*p)),count))goto done;
 p->guard=guard_ref;
 char leaf[96];
 pr_ref ignored;
 if(!pr_name("repair-plan",seq,leaf)||!pr_put(c->h,leaf,PR_PLAN,seq,raw.data,raw.bytes,&ignored))goto done;
 phase(c->h,PC02_REPAIR_PLAN_DURABLE);
 ok=1;
done:pc02rp_free(&raw);
return ok;
}
static int pr_finish_prebegin(pr_context *c,const pr_plan *p,int *restored){
 if(!p->before_begin)return 1;
 state now;
 if(!load_state(c->h,&now)||now.kind=='B'||memcmp(c->h->binding,p->origin_binding,B_BYTES))return 0;
 c->h->seen=now;
 if(!pr_retire(c->h))return 0;
 if(restored)*restored=1;
 return 1;
}
int pc02_repair_prepare(const char *root,const char *library,pc02_repair_schema schema,pc02_repair_prove prove,
 void *context,const pc02_controls *controls,int *restored_clean){
 if(restored_clean)*restored_clean=0;
 if(!schema||!prove)return 0;
 pr_context *c=pr_open(root,library,controls);
 pr_ledger *l=calloc(1,sizeof(*l));
 unsigned char *payload=NULL;
 int ok=0;
 if(!c||!l)goto done;
 c->schema=schema;
 c->prove=prove;
 c->context=context;
 if(!pr_ledger_read(c->h,l)||!pr_commit_orphan_guard(c,l))goto done;
 pr_ledger_free(l);
 if(!pr_ledger_read(c->h,l))goto done;
 if(l->active&&pr_zero_ref(&l->applied_ref)){
  if(!pr_restore_context(c,l->plan,l->parts,(size_t)get64(l->plan->part_count))||
     !pr_apply(c,l->plan,l->parts,(size_t)get64(l->plan->part_count),&l->latest_ref,&l->applied_ref)||
     !pr_finish_prebegin(c,l->plan,restored_clean))goto done;
  ok=1;
  goto done;
 }
 if(l->active&&l->plan->before_begin){
  if(!pr_restore_context(c,l->plan,l->parts,(size_t)get64(l->plan->part_count))||
     !pr_prove(c,l->plan)||!pr_source_immutable(c,l->parts,(size_t)get64(l->plan->part_count))||
     !pr_finish_prebegin(c,l->plan,restored_clean))goto done;
  ok=1;
  goto done;
 }
 if(!l->active&&!missing(c->h->route_dir,"repair.guard"))goto done;
 if(!c->state.tail_bytes&&c->state.kind=='I'){ok=1;
 goto done;
 }
 if(!pr_choose_input(c)||!pr_collect(c))goto done;
 if(!c->state.tail_bytes&&!c->tx.head_tail_bytes){ok=1;
 goto done;
 }
 unsigned seq=l->last+1,first=l->active?l->first:seq;
 if(seq>PR_PLANS)goto done;
 payload=calloc(1,sizeof(pr_plan)+PR_PARTS*sizeof(pr_part));
 if(!payload)goto done;
 pr_plan *p=(pr_plan *)payload;
 pr_part *parts=(pr_part *)(payload+sizeof(*p));
 size_t count=0;
 if(!pr_fill_plan(c,p,seq,first,&l->latest_ref,&l->done_ref)||!pr_archive_all(c,p,parts,&count))goto done;
 size_t bytes=sizeof(*p)+count*sizeof(*parts);
 if(l->active)p->guard=l->guard_ref;
 else{
  if(!pr_put(c->h,"repair.guard",PR_GUARD,first,payload,bytes,&p->guard))goto done;
 }
 char leaf[96];
 pr_ref plan_ref,applied_ref;
 if(!pr_name("repair-plan",seq,leaf)||!pr_put(c->h,leaf,PR_PLAN,seq,payload,bytes,&plan_ref))goto done;
 phase(c->h,PC02_REPAIR_PLAN_DURABLE);
 if(!pr_apply(c,p,parts,count,&plan_ref,&applied_ref)||!pr_finish_prebegin(c,p,restored_clean))goto done;
 ok=1;
done:
 free(payload);
 if(l){pr_ledger_free(l);
 free(l);
 }
 pr_context_free(c);
 return ok;
}
