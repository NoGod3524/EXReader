/* SPDX-License-Identifier: MIT */
/* Private implementation included after the original admission API. */
#include <dirent.h>
#if defined(__linux__)
#include <sys/syscall.h>
#endif
#define PM_HEAD 568u
#define PM_LIMIT 65536u
#define PM_FLOOR 3u
#define PM_FLOOR_BYTES 272u
static int pm_noreplace(int directory,const char *from,const char *to){
#if defined(__APPLE__)
 return renameatx_np(directory,from,directory,to,RENAME_EXCL)==0;
#elif defined(__linux__) && defined(SYS_renameat2)
 return syscall(SYS_renameat2,directory,from,directory,to,1u)==0;
#else
 (void)directory;(void)from;(void)to;errno=ENOTSUP;return 0;
#endif
}
int pc02_cap_check(pc02_lease *h,pc02_cap *cap){return live_cap(h,cap);}
int pc02_abandon(pc02_lease *h,pc02_cap *cap){
 if(!h||!cap||!h->active||cap!=h->current||cap->owner!=h||h->borrows)return 0;
 h->current=NULL;h->active=0;h->poisoned=1;return 1;
}
int pc02_parent_fd(pc02_lease *h,int *fd,pc02_identity *id){
 if(fd)*fd=-1;
 if(!h||!fd||!id||h->mode==PC02_SHARED||!pc02_check(h))return 0;
 *fd=h->parent;*id=h->parent_id;return 1;
}
int pc02_descriptor(pc02_lease *h,pc02_pending_record *out,int *clean){
 if(out)memset(out,0,sizeof(*out));if(clean)*clean=0;
 if(!h||!out||!clean||h->mode==PC02_SHARED||h->seen.kind=='I'||!pc02_check(h))return 0;
 *out=h->seen.pending;*clean=h->seen.kind=='C';return 1;
}
static int pm_name(unsigned phase,uint64_t generation,const char input[65],uint64_t slot,char out[128]){
 int n;
 if(!generation||!nonzero(input))return 0;
 if(phase==PM_FLOOR){
  if(!slot||slot>256)return 0;
  n=snprintf(out,128,"floor-%016llx-%03u",(unsigned long long)generation,(unsigned)slot);
 }else{
  if((phase!=PC02_META_INPUT&&phase!=PC02_META_PREPARED)||slot)return 0;
  n=snprintf(out,128,"%s-%016llx-%s",phase==PC02_META_INPUT?"input":"prepared",
   (unsigned long long)generation,input);
 }
 return n>0&&n<128;
}
static int pm_exact(pc02_lease *h,const pc02_pending_record *exact){
 return h&&h->mode!=PC02_SHARED&&h->seen.kind!='I'&&descriptor_same(exact,&h->seen.pending)&&pc02_check(h);
}
static int pm_origin(pc02_lease *h,const pc02_pending_record *exact,const unsigned char origin[B_BYTES]){
 unsigned char begin[S_BYTES];uint64_t index;pc02_identity old_target,selected;
 if(!pm_exact(h,exact)||!binding_valid(h,origin)||!exact->generation||
    get64(origin+88)!=exact->generation-1)return 0;
 index=h->seen.sequence-(h->seen.kind=='C'?2u:1u);
 if(!io_read(h->state_file,begin,S_BYTES,(off_t)(index*S_BYTES))||
    !sealed(begin,S_SEAL,"PC02S001")||begin[8]!='B'||get64(begin+24)!=exact->generation||
    memcmp(begin+S_SEAL,exact->seal,64)||memcmp(begin+240,origin+96,64))return 0;
 old_target=getid(begin+224);selected=getid(origin+40);
 if(!sameid(&old_target,&selected))return 0;
 if(get64(h->binding+88)==get64(origin+88))return !memcmp(origin,h->binding,B_BYTES);
 return h->seen.kind=='C'&&get64(h->binding+88)==exact->generation&&
  !memcmp(h->binding+96,h->seen.seal,64);
}
static int pm_read_raw(pc02_lease *h,const char *leaf,unsigned char **out,size_t *size,pc02_metadata_info *info){
 int fd=-1,again=-1,ok=0;struct stat st;pc02_identity id,check;
 unsigned char *bytes=NULL,*copy=NULL;size_t n=0;
 *out=NULL;*size=0;memset(info,0,sizeof(*info));
 fd=regular_open(h->route_dir,leaf,O_RDONLY,1,&id);
 if(fd<0)return missing(h->route_dir,leaf)?0:-1;
 if(fstat(fd,&st)||st.st_size<=0||st.st_size>(off_t)(PM_LIMIT+8192))goto done;
 n=(size_t)st.st_size;bytes=malloc(n);copy=malloc(n);
 if(!bytes||!copy||!io_read(fd,bytes,n,0)||!size_exact(fd,(off_t)n))goto done;
 again=regular_open(h->route_dir,leaf,O_RDONLY,1,&check);
 if(again<0||!sameid(&id,&check)||!size_exact(again,(off_t)n)||!io_read(again,copy,n,0)||
    memcmp(bytes,copy,n)||!size_exact(fd,(off_t)n)||!size_exact(again,(off_t)n)||
    !entry_id(h->route_dir,leaf,fd,1,&check)||!sameid(&id,&check))goto done;
 info->identity=id;info->bytes=n;wh_sha256_hex(bytes,n,info->sha256);ok=1;
done:
 if(fd>=0&&close(fd))ok=0;if(again>=0&&close(again))ok=0;free(copy);
 if(!ok){free(bytes);return -1;}*out=bytes;*size=n;return 1;
}
static int pm_input_head(pc02_lease *,const pc02_pending_record *,pc02_identity *);
static int pm_parse(pc02_lease *h,unsigned phase,const pc02_pending_record *exact,uint64_t slot,
 const unsigned char *bytes,size_t n,pc02_metadata_info *info,const unsigned char **payload,size_t *size){
 char sha[65],zero[65];pc02_identity self;
 zero_sha(zero);
 if(n<PM_HEAD+64||n>PM_HEAD+PM_LIMIT+64||memcmp(bytes,"PC02M001",8)||get64(bytes+8)!=phase||
    get64(bytes+16)!=exact->generation||get64(bytes+24)!=(uint64_t)(n-PM_HEAD-64)||
    get64(bytes+480)!=slot||memcmp(bytes+352,exact->input,64)||
    memcmp(bytes+416,phase==PC02_META_INPUT?zero:exact->seal,64)||
    !pm_origin(h,exact,bytes+48))return 0;
 self=getid(bytes+32);if(!sameid(&self,&info->identity))return 0;
 pc02_identity head=getid(bytes+552),registered;
 if(!head.inode||(phase!=PC02_META_INPUT&&(!pm_input_head(h,exact,&registered)||!sameid(&head,&registered))))return 0;
 wh_sha256_hex(bytes,n-64,sha);if(memcmp(sha,bytes+n-64,64))return 0;
 *size=n-PM_HEAD-64;*payload=bytes+PM_HEAD;
 wh_sha256_hex(*payload,*size,sha);
 if(memcmp(sha,bytes+488,64)||(phase==PC02_META_INPUT&&memcmp(sha,exact->input,64)))return 0;
 memcpy(info->payload_sha256,sha,65);return pm_exact(h,exact);
}
static int pm_read(pc02_lease *h,unsigned phase,const pc02_pending_record *exact,uint64_t slot,
 void *payload,size_t capacity,size_t *size,pc02_metadata_info *info){
 char leaf[128];unsigned char *bytes=NULL;const unsigned char *data=NULL;size_t n=0,count=0;int result;
 if(size)*size=0;if(info)memset(info,0,sizeof(*info));
 if(!size||!info||!payload||!pm_exact(h,exact)||!pm_name(phase,exact->generation,exact->input,slot,leaf))return -1;
 result=pm_read_raw(h,leaf,&bytes,&n,info);if(result!=1)return result;
 if(!pm_parse(h,phase,exact,slot,bytes,n,info,&data,&count)||count>capacity)result=-1;
 else{memcpy(payload,data,count);*size=count;}
 free(bytes);return result;
}
int pc02_metadata_read(pc02_lease *h,unsigned phase,const pc02_pending_record *exact,
 void *data,size_t capacity,size_t *size,pc02_metadata_info *info){
 if(phase!=PC02_META_INPUT&&phase!=PC02_META_PREPARED)return -1;
 return pm_read(h,phase,exact,0,data,capacity,size,info);
}
#include "pc02_floor_head.inc"
static void pm_phase(pc02_lease *h,unsigned at){phase(h,at);}
static int pm_write(pc02_lease *h,unsigned phase,pc02_cap *cap,uint64_t slot,const void *data,size_t count,
 char payload_sha[65],pc02_metadata_info *info){
 int fd=-1,verify=-1,ok=0;char input[65],pending[65],leaf[128],temporary[128];
 unsigned char *bytes=NULL,*readback=NULL;pc02_identity id,actual,head;uint64_t generation;
 if(!h||!data||!count||count>PM_LIMIT||!payload_sha||!info||h->borrows)return 0;
 if(phase==PC02_META_INPUT){
  if(cap||h->mode!=PC02_OWNER||h->active||h->seen.kind=='B'||!pc02_check(h)||get64(h->binding+88)==UINT64_MAX)return 0;
  generation=get64(h->binding+88)+1;zero_sha(pending);wh_sha256_hex(data,count,input);
 }else{
  if((phase!=PC02_META_PREPARED&&phase!=PM_FLOOR)||!live_cap(h,cap))return 0;
  generation=h->seen.pending.generation;memcpy(input,h->seen.pending.input,65);memcpy(pending,h->seen.pending.seal,65);
 }
 if(!pm_name(phase,generation,input,slot,leaf)||!missing(h->route_dir,leaf))return 0;
 if(phase==PC02_META_INPUT){if(!pm_head_create(h,generation,input,&head)){h->poisoned=1;return 0;}}
 else if(!pm_input_head(h,&h->seen.pending,&head))return 0;
 size_t n=PM_HEAD+count+64;bytes=calloc(1,n);readback=malloc(n);
 if(!bytes||!readback)goto done;
 for(unsigned serial=0;serial<1024;serial++){
  if(snprintf(temporary,sizeof(temporary),".metadata-%ld-%u",(long)getpid(),serial)>=(int)sizeof(temporary))goto done;
  fd=openat(h->route_dir,temporary,O_RDWR|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
  if(fd>=0)break;if(errno!=EEXIST)goto done;
 }
 if(fd<0||!entry_id(h->route_dir,temporary,fd,1,&id))goto done;
 memcpy(bytes,"PC02M001",8);put64(bytes+8,phase);put64(bytes+16,generation);put64(bytes+24,count);
 putid(bytes+32,&id);memcpy(bytes+48,h->binding,B_BYTES);memcpy(bytes+352,input,64);
 memcpy(bytes+416,pending,64);put64(bytes+480,slot);wh_sha256_hex(data,count,payload_sha);
 memcpy(bytes+488,payload_sha,64);putid(bytes+552,&head);memcpy(bytes+PM_HEAD,data,count);
 char sha[65];wh_sha256_hex(bytes,n-64,sha);memcpy(bytes+n-64,sha,64);
 if(h->controls.fault==PC02_SHORT_WRITE&&h->controls.fault_phase==1401){
  (void)io_write(fd,bytes,n-1,0);goto done;
 }
 if(!io_write(fd,bytes,n,0))goto done;pm_phase(h,1401);
 if(!sync_controlled(h,fd,1401)||(h->controls.fault==PC02_READBACK_FAIL&&h->controls.fault_phase==1401))goto done;
 verify=regular_open(h->route_dir,temporary,O_RDONLY,1,&actual);
 if(verify<0||!sameid(&id,&actual)||!size_exact(verify,(off_t)n)||!io_read(verify,readback,n,0)||memcmp(bytes,readback,n))goto done;
 if(close(verify)){verify=-1;goto done;}verify=-1;
 if(!pc02_check(h)||!pm_noreplace(h->route_dir,temporary,leaf))goto done;pm_phase(h,1402);
 if(fsync(h->route_dir))goto done;
 verify=regular_open(h->route_dir,leaf,O_RDONLY,1,&actual);
 if(verify<0||!sameid(&id,&actual)||!size_exact(verify,(off_t)n)||!io_read(verify,readback,n,0)||
    memcmp(bytes,readback,n)||!entry_id(h->route_dir,leaf,fd,1,&actual)||!sameid(&id,&actual)||!pc02_check(h))goto done;
 info->identity=id;info->bytes=n;memcpy(info->payload_sha256,payload_sha,65);
 wh_sha256_hex(bytes,n,info->sha256);ok=1;pm_phase(h,1403);
done:
 if(fd>=0&&close(fd))ok=0;if(verify>=0&&close(verify))ok=0;free(bytes);free(readback);
 if(!ok&&h)h->poisoned=1;return ok;
}
int pc02_metadata_write(pc02_lease *h,unsigned phase,pc02_cap *cap,const void *data,size_t count,
 char payload_sha[65],pc02_metadata_info *info){
 if(phase!=PC02_META_INPUT&&phase!=PC02_META_PREPARED)return 0;
 return pm_write(h,phase,cap,0,data,count,payload_sha,info);
}
static void pm_floor_empty(const pc02_pending_record *exact,pc02_floor *out){
 memset(out,0,sizeof(*out));memcpy(out->manifest,exact->manifest,65);
 zero_sha(out->last_line_sha256);zero_sha(out->chain_sha256);
}
static int pm_floor_same(const pc02_floor *a,const pc02_floor *b){
 return a&&b&&a->count==b->count&&!memcmp(a->manifest,b->manifest,65)&&
 !memcmp(a->last_line_sha256,b->last_line_sha256,65)&&!memcmp(a->chain_sha256,b->chain_sha256,65);
}
static int pm_floor_slots(pc02_lease *h,uint64_t generation,unsigned *largest){
 unsigned char seen[257]={0};int fd=-1,ok=0;DIR *directory=NULL;pc02_identity id;
 *largest=0;fd=openat(h->route_dir,".",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
 if(fd<0||!metadata(fd,1,1,&id)||!sameid(&id,&h->route_id))goto done;
 directory=fdopendir(fd);if(!directory)goto done;fd=-1;
 for(;;){
  errno=0;struct dirent *entry=readdir(directory);
  if(!entry){if(errno)goto done;break;}
  const char *name=entry->d_name;if(strncmp(name,"floor-",6))continue;
  if(strlen(name)!=26||name[22]!='-')goto done;
  char digits[17];memcpy(digits,name+6,16);digits[16]=0;
  if(strspn(digits,"0123456789abcdef")!=16)goto done;
  char *end=NULL;errno=0;unsigned long long g=strtoull(digits,&end,16);
  if(errno||!g||!end||*end)goto done;
  unsigned slot=0;
  for(unsigned k=23;k<26;k++){if(name[k]<'0'||name[k]>'9')goto done;slot=slot*10+(unsigned)(name[k]-'0');}
  if(!slot||slot>256)goto done;
  if((uint64_t)g==generation){if(seen[slot])goto done;seen[slot]=1;if(slot>*largest)*largest=slot;}
 }
 for(unsigned k=1;k<=*largest;k++)if(!seen[k])goto done;
 ok=1;
done:
 if(directory&&closedir(directory))ok=0;if(fd>=0&&close(fd))ok=0;return ok;
}
int pc02_floor_read(pc02_lease *h,const pc02_pending_record *exact,pc02_floor *out){
 unsigned largest=0,head_count=0;unsigned char data[PM_FLOOR_BYTES],*head=NULL;size_t size,head_bytes=0;pc02_metadata_info info;
 if(!out||!pm_exact(h,exact)||!pm_floor_slots(h,exact->generation,&largest)||
    !pm_head_load(h,exact,&head,&head_bytes,&head_count))return 0;
 if(head_count>largest){free(head);return 0;}
 pc02_floor current;pm_floor_empty(exact,&current);
 for(unsigned k=1;k<=largest;k++){
  if(pm_read(h,PM_FLOOR,exact,k,data,sizeof(data),&size,&info)!=1||size!=sizeof(data)||
     get64(data)!=current.count||memcmp(data+8,current.last_line_sha256,64)||
     memcmp(data+72,current.chain_sha256,64)||get64(data+136)!=k||memcmp(data+208,exact->manifest,64)){free(head);return 0;}
  if(k<=head_count){const unsigned char *r=head+PF_HEAD+(k-1)*PF_RECORD;
   if(memcmp(r+16,data+144,64)||memcmp(r+80,info.sha256,64)){free(head);return 0;}}

  char line[65];memcpy(line,data+144,64);line[64]=0;if(!nonzero(line)){free(head);return 0;}
  current.count=k;memcpy(current.last_line_sha256,line,65);memcpy(current.chain_sha256,info.sha256,65);
 }
 free(head);if(!pm_exact(h,exact))return 0;*out=current;return 1;
}
int pc02_floor_advance(pc02_lease *h,pc02_cap *cap,const pc02_floor *expected,
 const char line[65],pc02_floor *out){
 pc02_floor actual,check;pc02_metadata_info info;unsigned char bytes[PM_FLOOR_BYTES];char sha[65];
 if(!out||!expected||!nonzero(line)||!live_cap(h,cap)||h->borrows||
    !pc02_floor_read(h,&h->seen.pending,&actual)||!pm_floor_same(expected,&actual)||actual.count>=256)return 0;
 memset(bytes,0,sizeof(bytes));put64(bytes,actual.count);memcpy(bytes+8,actual.last_line_sha256,64);
 memcpy(bytes+72,actual.chain_sha256,64);put64(bytes+136,actual.count+1);
 memcpy(bytes+144,line,64);memcpy(bytes+208,actual.manifest,64);
 if(!pm_write(h,PM_FLOOR,cap,actual.count+1,bytes,sizeof(bytes),sha,&info)||
    !pm_head_catchup(h,cap,(unsigned)(actual.count+1))||
    !pc02_floor_read(h,&h->seen.pending,&check)||check.count!=actual.count+1||
    memcmp(check.last_line_sha256,line,65)||memcmp(check.chain_sha256,info.sha256,65)){
  h->poisoned=1;return 0;
 }
 *out=check;return 1;
}
static int pm_member_names(pc02_lease *h,const pc02_member *m){
 char mirror[320];
 if(!m||!memchr(m->target,0,sizeof(m->target))||!memchr(m->stage,0,sizeof(m->stage))||
    !memchr(m->retained,0,sizeof(m->retained))||!leaf_ok(m->target)||!leaf_ok(m->stage)||!leaf_ok(m->retained)||
    !strcmp(m->target,m->stage)||!strcmp(m->target,m->retained)||!strcmp(m->stage,m->retained)||
    (m->original_present!=0&&m->original_present!=1)||!m->prepared.inode)return 0;
 if(snprintf(mirror,sizeof(mirror),"%s.legacy-map.json",h->leaf)>=(int)sizeof(mirror))return 0;
 if(strcmp(m->target,h->leaf)&&strcmp(m->target,mirror))return 0;
 if(!strcmp(m->target,h->leaf)){
  pc02_identity target=getid(h->binding+40);
  if(!m->original_present)return 0;
  if(h->seen.kind=='C'){
   unsigned char b[S_BYTES];uint64_t index=h->seen.sequence-2;
   if(!io_read(h->state_file,b,S_BYTES,(off_t)(index*S_BYTES))||!sealed(b,S_SEAL,"PC02S001")||b[8]!='B')return 0;
   target=getid(b+224);
  }
  if(!sameid(&m->original,&target))return 0;
 }
 return !m->original_present||!sameid(&m->original,&m->prepared);
}
static int pm_member_entry(pc02_lease *h,const char *leaf,const pc02_identity *expected,int private_mode){
 pc02_identity actual;int fd=regular_open(h->parent,leaf,O_RDONLY,private_mode,&actual);
 if(fd<0)return 0;int ok=sameid(&actual,expected);if(close(fd))ok=0;return ok;
}
int pc02_member_observe(pc02_lease *h,const pc02_member *m,unsigned *out){
 if(!h||!out||h->mode==PC02_SHARED||!pc02_check(h)||!pm_member_names(h,m))return 0;
 int stage=pm_member_entry(h,m->stage,&m->prepared,1),stage_absent=missing(h->parent,m->stage);
 int prepared=pm_member_entry(h,m->target,&m->prepared,1),target_absent=missing(h->parent,m->target);
 int retained_absent=missing(h->parent,m->retained);
 if(!m->original_present){
  if(!retained_absent)return 0;
  if(stage&&target_absent){*out=0;return 1;}
  if(stage_absent&&prepared){*out=2;return 1;}
  return 0;
 }
 int original=pm_member_entry(h,m->target,&m->original,0);
 int retained=pm_member_entry(h,m->retained,&m->original,0);
 if(stage&&original&&retained_absent){*out=0;return 1;}
 if(stage&&target_absent&&retained){*out=1;return 1;}
 if(stage_absent&&prepared&&retained){*out=2;return 1;}
 return 0;
}
static int pm_member_proof(pc02_lease *h,const pc02_member *m,unsigned state,pc02_member_prove prove,void *context){
 int original=-1,prepared=-1,ok=0;pc02_identity id;
 if(m->original_present){
  original=regular_open(h->parent,state?m->retained:m->target,O_RDONLY,0,&id);
  if(original<0||!sameid(&id,&m->original))goto done;
 }
 prepared=regular_open(h->parent,state==2?m->target:m->stage,O_RDWR,1,&id);
 if(prepared<0||!sameid(&id,&m->prepared)||!prove(context,original,prepared)||fsync(prepared))goto done;
 unsigned after;
 if(!pc02_member_observe(h,m,&after)||after!=state)goto done;ok=1;
done:
 if(original>=0&&close(original))ok=0;if(prepared>=0&&close(prepared))ok=0;return ok;
}
int pc02_member_publish(pc02_lease *h,pc02_cap *cap,const pc02_member *m,pc02_member_prove prove,void *context){
 unsigned state,next;int attempted=0;
 if(!prove||!live_cap(h,cap)||h->borrows||!h->transition||
    !pc02_member_observe(h,m,&state)||!pm_member_proof(h,m,state,prove,context))return 0;
 if(!state&&m->original_present){
  attempted=1;
  if(!pm_noreplace(h->parent,m->target,m->retained)||fsync(h->parent))goto failed;
  pm_phase(h,1301);
  if(!live_cap(h,cap)||!pc02_member_observe(h,m,&next)||next!=1)goto failed;
  state=1;
 }
 if(state!=2){
  attempted=1;
  if(!pm_noreplace(h->parent,m->stage,m->target)||fsync(h->parent))goto failed;
  pm_phase(h,1302);
 }
 if(!live_cap(h,cap)||!pc02_member_observe(h,m,&next)||next!=2||
    !pm_member_proof(h,m,2,prove,context)||fsync(h->parent))goto failed;
 pm_phase(h,1303);return live_cap(h,cap);
failed:
 if(attempted)h->poisoned=1;return 0;
}
