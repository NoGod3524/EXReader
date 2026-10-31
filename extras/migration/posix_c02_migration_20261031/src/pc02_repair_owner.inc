
static int repair_schema(void *context,const void *input,size_t input_bytes,const void *prepared,size_t prepared_bytes,
 pc02_repair_description *d){
 p2_owner *o=context;
 if(input_bytes!=sizeof(o->input)||(prepared&&prepared_bytes!=sizeof(o->prepared))||(!prepared&&prepared_bytes))return 0;
 memcpy(&o->input,input,sizeof(o->input));
 if(!o->repair_library||!memchr(o->input.library,0,sizeof(o->input.library))||strcmp(o->input.library,o->repair_library))return 0;
 memset(&o->prepared,0,sizeof(o->prepared));
 o->repair_schema=1;
 int valid=input_valid(o);
 o->repair_schema=0;
 if(!valid)return 0;
 if(prepared){
  memcpy(&o->prepared,prepared,sizeof(o->prepared));
  char sha[65];
  wh_sha256_hex(&o->input,sizeof(o->input),sha);
  if(memcmp(o->prepared.magic,"PC02OUT1",8)||!hex(o->prepared.input_sha,64)||strcmp(o->prepared.input_sha,sha))return 0;
  for(unsigned k=0;k<2;k++)if(!file_valid(&o->prepared.files[k])||!pc02io_get64(o->prepared.files[k].size)||
    memcmp(o->prepared.files[k].identity,o->input.staged[k],16))return 0;
 }
 memset(d,0,sizeof(*d));
 memcpy(d->binding,&o->input.binding,sizeof(o->input.binding));
 memcpy(d->gates,&o->input.gates,sizeof(o->input.gates));
 memcpy(d->original_grant,o->input.original_grant,88);
 memcpy(&d->original[0],&o->input.original,89);
 memcpy(&d->original[1],&o->input.mirror,89);
 memcpy(d->prepared,o->prepared.files,sizeof(d->prepared));
 memcpy(&d->pack,&o->input.private_pack,89);
 strcpy(d->journal,o->input.journal);
 strcpy(d->pack_leaf,o->input.pack_copy);
 strcpy(d->token,o->input.token);
 memcpy(d->journal_identity,o->input.journal_identity,16);
 d->mirror_present=o->input.mirror_present;
 d->has_prepared=(unsigned char)(prepared!=NULL);
 for(unsigned k=0;k<2;k++){
  pc02_member m;
  member(o,k,&m);
  strcpy(d->members[k].target,m.target);
  strcpy(d->members[k].stage,m.stage);
  strcpy(d->members[k].retained,m.retained);
  d->members[k].original_present=(unsigned char)m.original_present;
  pc02io_putid(d->members[k].original,&m.original);
  pc02io_putid(d->members[k].prepared,&m.prepared);
 }
 return 1;
}
static int repair_clone(const pc02_repair_view *v,unsigned ordinal,const char *source,const pc02_repair_file *expected,
 char out[P2_PATH]){
 int input=-1,output=-1,ok=0;
 pc02_file wanted,observed;
 char leaf[96];
 memcpy(&wanted,expected,sizeof(wanted));
 if(!pc02io_quiet(v->parent_directory,source)||!pc02io_match(v->parent_directory,source,&wanted))return 0;
 input=openat(v->parent_directory,source,O_RDONLY|O_NONBLOCK|O_NOFOLLOW|O_CLOEXEC);
 if(input<0)return 0;
 for(unsigned k=0;k<1024;k++){
  int n=snprintf(leaf,sizeof(leaf),"proof-%ld-%u-%u.image",(long)getpid(),ordinal,k);
  if(n<=0||n>=(int)sizeof(leaf))goto done;
  output=openat(v->archive_directory_fd,leaf,O_RDWR|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
  if(output>=0)break;
  if(errno!=EEXIST)goto done;
 }
 if(output<0||!pc02io_hash(input,&observed)||!pc02io_equal(&observed,&wanted)||
    !pc02io_copy(input,output,&wanted)||fsync(v->archive_directory_fd)||
    !pc02io_match(v->parent_directory,source,&wanted))goto done;
 int n=snprintf(out,P2_PATH,"%s/%s",v->archive_directory,leaf);
 if(n<=0||n>=P2_PATH)goto done;
 ok=1;
done:if(input>=0&&close(input))ok=0;
if(output>=0&&close(output))ok=0;
return ok;
}
static int repair_prove(void *context,const pc02_repair_view *v){
 p2_owner *o=context;
 const pc02_repair_description *d=v->description;
 char original[2][P2_PATH],prepared[2][P2_PATH],pack[P2_PATH];
 int pack_fd=-1,ok=0;
 pc02_file expected;
 memcpy(&expected,&d->pack,sizeof(expected));
 if(strcmp(v->library,o->input.library)||memcmp(d->binding,&o->input.binding,sizeof(o->input.binding))||
    !supported_filesystem(v->parent_directory)||!supported_filesystem(v->archive_directory_fd)||
    !pc02io_match(v->parent_directory,d->pack_leaf,&expected))return 0;
 for(unsigned k=0;k<2;k++){
  const pc02_repair_member *m=&d->members[k];
  if(m->original_present&&!repair_clone(v,k,v->member_states[k]?m->retained:m->target,&d->original[k],original[k]))goto done;
  if(v->publish_intent&&(!d->has_prepared||
    !repair_clone(v,k+2,v->member_states[k]==2?m->target:m->stage,&d->prepared[k],prepared[k])))goto done;
 }
 if(!pc02t_original_verify(original[0],d->mirror_present?original[1]:NULL))goto done;
 if(v->publish_intent){
  int n=snprintf(pack,sizeof(pack),"%s/%s",o->parent_path,d->pack_leaf);
  if(n<=0||n>=P2_PATH)goto done;
  pack_fd=openat(v->parent_directory,d->pack_leaf,O_RDONLY|O_NONBLOCK|O_NOFOLLOW|O_CLOEXEC);
  if(pack_fd<0||!pc02io_hash(pack_fd,&expected)||memcmp(&expected,&d->pack,sizeof(expected))||
     !pc02t_original_verify(prepared[0],prepared[1])||
     !pc02t_verify(pack_fd,prepared[0],pack,prepared[1]))goto done;
 }
 memcpy(&expected,&d->pack,sizeof(expected));
 if(!pc02io_match(v->parent_directory,d->pack_leaf,&expected))goto done;
 for(unsigned k=0;k<2;k++){
  const pc02_repair_member *m=&d->members[k];
  if(m->original_present){memcpy(&expected,&d->original[k],sizeof(expected));
   if(!pc02io_match(v->parent_directory,v->member_states[k]?m->retained:m->target,&expected))goto done;
  }
  if(v->publish_intent){memcpy(&expected,&d->prepared[k],sizeof(expected));
   if(!pc02io_match(v->parent_directory,v->member_states[k]==2?m->target:m->stage,&expected))goto done;
  }
 }
 ok=1;
done:if(pack_fd>=0&&close(pack_fd))ok=0;
return ok;
}
