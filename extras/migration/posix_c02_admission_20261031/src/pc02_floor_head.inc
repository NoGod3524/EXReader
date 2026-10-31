/* SPDX-License-Identifier: MIT */
/* INPUT registers this append-only, independent committed-prefix floor. */
#define PF_HEAD 464u
#define PF_RECORD 272u
static int pm_head_name(uint64_t generation,const char input[65],char out[128]){
 int n=snprintf(out,128,"commit-head-%016llx-%s",(unsigned long long)generation,input);
 return n>0&&n<128;
}
static int pm_input_head(pc02_lease *h,const pc02_pending_record *exact,pc02_identity *head){
 char leaf[128];
 unsigned char *bytes=NULL;
 const unsigned char *payload;
 size_t n=0,size;
 pc02_metadata_info info;
 if(!pm_name(PC02_META_INPUT,exact->generation,exact->input,0,leaf)||
    pm_read_raw(h,leaf,&bytes,&n,&info)!=1)return 0;
 int ok=pm_parse(h,PC02_META_INPUT,exact,0,bytes,n,&info,&payload,&size);
 if(ok){*head=getid(bytes+552);
 ok=head->inode!=0;
 }
 free(bytes);
 return ok;
}
static int pm_head_create(pc02_lease *h,uint64_t generation,const char input[65],pc02_identity *head){
 char leaf[128];
 int fd=-1,again=-1,ok=0;
 unsigned char bytes[PF_HEAD],check[PF_HEAD];
 pc02_identity id;
 if(!pm_head_name(generation,input,leaf))return 0;
 fd=openat(h->route_dir,leaf,O_RDWR|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
 if(fd<0||!entry_id(h->route_dir,leaf,fd,1,head))goto done;
 memset(bytes,0,sizeof(bytes));
 memcpy(bytes,"PC02F001",8);
 put64(bytes+8,generation);
 memcpy(bytes+16,input,64);
 memcpy(bytes+80,h->binding,B_BYTES);
 putid(bytes+384,head);
 seal(bytes,400);
 if(!pc02_check(h)||!io_write(fd,bytes,sizeof(bytes),0)||fsync(fd))goto done;
 again=regular_open(h->route_dir,leaf,O_RDONLY,1,&id);
 if(again<0||!sameid(head,&id)||!size_exact(again,PF_HEAD)||!io_read(again,check,sizeof(check),0)||
    memcmp(bytes,check,sizeof(bytes))||fsync(h->route_dir)||!pc02_check(h))goto done;
 ok=1;
done:
 if(fd>=0&&close(fd))ok=0;
 if(again>=0&&close(again))ok=0;
 return ok;
}
static int pm_head_load(pc02_lease *h,const pc02_pending_record *exact,unsigned char **out,size_t *bytes,unsigned *count){
 pc02_identity expected,self;
 pc02_metadata_info info;
 char leaf[128];
 unsigned char *raw=NULL;
 size_t n=0;
 *out=NULL;
 *bytes=0;
 *count=0;
 if(!pm_input_head(h,exact,&expected)||!pm_head_name(exact->generation,exact->input,leaf)||
    pm_read_raw(h,leaf,&raw,&n,&info)!=1)return 0;
 int ok=0;
 if(n<PF_HEAD||(n-PF_HEAD)%PF_RECORD||(n-PF_HEAD)/PF_RECORD>256||
    !sealed(raw,400,"PC02F001")||get64(raw+8)!=exact->generation||memcmp(raw+16,exact->input,64)||
    !pm_origin(h,exact,raw+80)||!sameid(&info.identity,&expected))goto done;
 self=getid(raw+384);
 if(!sameid(&self,&expected))goto done;
 const unsigned char *previous=raw+400;
 for(size_t at=PF_HEAD;at<n;at+=PF_RECORD){
  const unsigned char *r=raw+at;
  char line[65],floor[65];
  memcpy(line,r+16,64);
  line[64]=0;
  memcpy(floor,r+80,64);
  floor[64]=0;
  if(!sealed(r,208,"PC02H001")||get64(r+8)!=(at-PF_HEAD)/PF_RECORD+1||
     !nonzero(line)||!nonzero(floor)||memcmp(r+144,previous,64))goto done;
  previous=r+208;
 }
 *out=raw;
 *bytes=n;
 *count=(unsigned)((n-PF_HEAD)/PF_RECORD);
 ok=1;
done:
 if(!ok)free(raw);
 return ok;
}
static int pm_head_catchup(pc02_lease *h,pc02_cap *cap,unsigned largest){
 unsigned char *raw=NULL;
 size_t size=0;
 unsigned count=0;
 char leaf[128];
 int fd=-1,again=-1,ok=0;
 pc02_identity expected,id;
 unsigned char previous[64];
 if(!live_cap(h,cap)||!pm_head_load(h,&h->seen.pending,&raw,&size,&count)||count>largest||
    !pm_input_head(h,&h->seen.pending,&expected)||!pm_head_name(h->seen.generation,h->seen.pending.input,leaf))goto done;
 memcpy(previous,raw+(count?PF_HEAD+(count-1)*PF_RECORD+208:400),64);
 fd=regular_open(h->route_dir,leaf,O_RDWR,1,&id);
 if(fd<0||!sameid(&id,&expected)||!size_exact(fd,(off_t)size))goto done;
 for(unsigned slot=count+1;slot<=largest;slot++){
  unsigned char payload[PM_FLOOR_BYTES],record[PF_RECORD],verify[PF_RECORD];
  pc02_metadata_info info;
  size_t got=0;
  if(pm_read(h,PM_FLOOR,&h->seen.pending,slot,payload,sizeof(payload),&got,&info)!=1||
     got!=sizeof(payload)||get64(payload+136)!=slot||!live_cap(h,cap))goto done;
  memset(record,0,sizeof(record));
  memcpy(record,"PC02H001",8);
  put64(record+8,slot);
  memcpy(record+16,payload+144,64);
  memcpy(record+80,info.sha256,64);
  memcpy(record+144,previous,64);
  seal(record,208);
  off_t at=(off_t)(PF_HEAD+(slot-1)*PF_RECORD);
  if(!size_exact(fd,at))goto done;
  if(h->controls.fault==PC02_SHORT_WRITE&&h->controls.fault_phase==1501){
   (void)io_write(fd,record,PF_RECORD-1,at);
   goto done;
  }
  if(!io_write(fd,record,sizeof(record),at))goto done;
  phase(h,1501);
  if(!sync_controlled(h,fd,1501)||(h->controls.fault==PC02_READBACK_FAIL&&h->controls.fault_phase==1501))goto done;
  again=regular_open(h->route_dir,leaf,O_RDONLY,1,&id);
  if(again<0||!sameid(&id,&expected)||!size_exact(again,at+PF_RECORD)||!io_read(again,verify,sizeof(verify),at)||
     memcmp(record,verify,sizeof(record))||!entry_id(h->route_dir,leaf,fd,1,&id)||
     !sameid(&id,&expected)||fsync(h->route_dir)||!live_cap(h,cap))goto done;
  if(close(again)){again=-1;
  goto done;
  }again=-1;
  memcpy(previous,record+208,64);
  phase(h,1502);
 }
 ok=1;
done:
 if(fd>=0&&close(fd))ok=0;
 if(again>=0&&close(again))ok=0;
 free(raw);
 return ok;
}
