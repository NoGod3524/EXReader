/* SPDX-License-Identifier: MIT */
/* SDK-owner account work. No GTK, network thread, JSON or direct SQL here. */
typedef struct { char *key,*sort;int64_t id;uint64_t bytes; } account_local_book;
typedef struct {
  exr_credentials_store *credentials;exr_credentials_status open_status;
  char *home,*configuration,*work,*originals,*root,*cursor_title,*cursor_key;
  char id[37];unsigned char *secret;size_t secret_size;int secret_remember,bound,loaded,staging;
  account_local_book page[50];size_t count,index;
  uint64_t seen,prepared,existing,pending,failed,bootstraps;
} account_owner;
typedef struct { linux_reader *reader;reader_account_control *shared; } account_control;

static int accounts_cancelled(void *opaque) {
  account_control *control=opaque;
  return (control->shared && g_atomic_int_get(&control->shared->cancelled)) ||
    (control->reader->control.cancelled && control->reader->control.cancelled(control->reader->control.context));
}
static void accounts_progress(void *opaque,exr_stage stage,uint64_t done,uint64_t total) {
  (void)stage;account_control *control=opaque;if(!control->shared) return;
  g_atomic_int_set(&control->shared->current_bytes,(gint)done);
  g_atomic_int_set(&control->shared->total_bytes,(gint)total);
}
static void accounts_secret_clear(account_owner *owner) {
  if(owner->secret) { exr_credentials_wipe(owner->secret,owner->secret_size);free(owner->secret); }
  owner->secret=NULL;owner->secret_size=0;owner->secret_remember=0;
}
static void accounts_page_clear(account_owner *owner) {
  for(size_t i=0;i<owner->count;i++) { free(owner->page[i].key);free(owner->page[i].sort); }
  memset(owner->page,0,sizeof(owner->page));owner->count=owner->index=0;
}
static void accounts_free(linux_reader *reader) {
  account_owner *owner=reader->account_data;if(!owner) return;
  accounts_secret_clear(owner);accounts_page_clear(owner);exr_credentials_close(owner->credentials);
  g_free(owner->home);g_free(owner->configuration);g_free(owner->work);g_free(owner->originals);
  g_free(owner->root);g_free(owner->cursor_title);g_free(owner->cursor_key);free(owner);reader->account_data=NULL;
}
static int accounts_private_directory(const char *path,int create) {
  struct stat info;
  if(lstat(path,&info)<0) {
    if(!create || errno!=ENOENT || mkdir(path,0700)<0 || lstat(path,&info)<0) return 0;
  }
  return S_ISDIR(info.st_mode) && info.st_uid==geteuid() && !(info.st_mode&077);
}
static int accounts_private_file(const struct stat *info) {
  return S_ISREG(info->st_mode) && info->st_nlink==1 && info->st_uid==geteuid() && !(info->st_mode&077);
}
static int accounts_uuid(const char *id) {
  if(!id || !g_uuid_string_is_valid(id) || strlen(id)!=36) return 0;
  for(size_t i=0;i<36;i++) if(id[i]>='A' && id[i]<='F') return 0;
  return 1;
}
static int accounts_root(const char *root) {
  exr_webdav_config config={0};exr_webdav_client *dav=NULL;exr_webdav_error error={0};
  config.root_url=root;exr_webdav_status code=exr_webdav_create(&config,&dav,&error);exr_webdav_free(dav);
  return code==EXR_DAV_OK;
}
/* 0 absent, 1 valid, -1 refused. The only persisted fields are UUID and exact root. */
static int accounts_configuration(account_owner *owner,char **id,char **root) {
  *id=*root=NULL;int file=open(owner->configuration,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
  if(file<0) return errno==ENOENT ? 0:-1;
  struct stat before,after;char data[16385];size_t at=0;int valid=0;
  if(fstat(file,&before)<0 || !accounts_private_file(&before) || before.st_size<=0 || before.st_size>16384) goto done;
  while(at<(size_t)before.st_size) {
    ssize_t got=read(file,data+at,(size_t)before.st_size-at);
    if(got<0 && errno==EINTR) continue;
    if(got<=0) goto done;
    at+=(size_t)got;
  }
  if(fstat(file,&after)<0 || before.st_size!=after.st_size || before.st_mtim.tv_sec!=after.st_mtim.tv_sec ||
     before.st_mtim.tv_nsec!=after.st_mtim.tv_nsec) goto done;
  if(memchr(data,0,at)) goto done;
  data[at]=0;GKeyFile *settings=g_key_file_new();gsize groups_count=0,keys_count=0;
  if(!g_key_file_load_from_data(settings,data,at,G_KEY_FILE_NONE,NULL)) { g_key_file_free(settings);goto done; }
  char **groups=g_key_file_get_groups(settings,&groups_count),**keys=g_key_file_get_keys(settings,"account",&keys_count,NULL);
  if(groups_count==1 && !strcmp(groups[0],"account") && keys_count==2 &&
      ((!strcmp(keys[0],"id") && !strcmp(keys[1],"root")) || (!strcmp(keys[1],"id") && !strcmp(keys[0],"root")))) {
    *id=g_key_file_get_string(settings,"account","id",NULL);*root=g_key_file_get_string(settings,"account","root",NULL);
    valid=accounts_uuid(*id) && accounts_root(*root);
  }
  g_strfreev(groups);g_strfreev(keys);g_key_file_free(settings);
done:
  close(file);
  if(!valid) { g_clear_pointer(id,g_free);g_clear_pointer(root,g_free);return -1; }
  return 1;
}
static exr_status accounts_ready(linux_reader *reader,reader_result *result,account_owner **out) {
  account_owner *owner=reader->account_data;
  if(!owner) {
    owner=calloc(1,sizeof(*owner));if(!owner) return EXR_MEMORY;reader->account_data=owner;
    owner->home=g_path_get_dirname(reader->catalog_path);
    owner->configuration=g_build_filename(owner->home,"account.ini",NULL);
    owner->work=g_build_filename(owner->home,"sync-work",NULL);owner->originals=g_build_filename(owner->home,"sync-originals",NULL);
    owner->root=g_strdup("");char *id=g_uuid_string_random();memcpy(owner->id,id,37);g_free(id);
    owner->open_status=exr_credentials_open("org.exreader.reader.webdav",&owner->credentials);
  }
  *out=owner;
  if(!accounts_private_directory(owner->home,0)) {
    snprintf(result->message,sizeof(result->message),"Account storage requires an app-private library directory");return EXR_IO;
  }
  if(!owner->loaded) {
    char *id=NULL,*root=NULL;int read=accounts_configuration(owner,&id,&root);
    if(read<0) { snprintf(result->message,sizeof(result->message),"Account configuration is invalid and has been retained");return EXR_DATABASE; }
    if(read) { memcpy(owner->id,id,37);g_free(owner->root);owner->root=root;root=NULL;owner->bound=1; }
    g_free(id);g_free(root);owner->loaded=1;
  }
  return EXR_OK;
}
static exr_status accounts_bind(account_owner *owner,const reader_command *command,reader_result *result) {
  if(!command->account_id || strcmp(command->account_id,owner->id) || !accounts_root(command->account_root)) {
    snprintf(result->message,sizeof(result->message),"Enter an HTTPS WebDAV collection root ending with /");return EXR_ARGUMENT;
  }
  char *id=NULL,*root=NULL;int read=accounts_configuration(owner,&id,&root);
  int same=read==1 && !strcmp(id,owner->id) && !strcmp(root,command->account_root);
  g_free(id);g_free(root);
  if(read<0 || (read==1 && !same) || (owner->bound && (read!=1 || strcmp(owner->root,command->account_root)))) {
    snprintf(result->message,sizeof(result->message),"This library is bound to its account and exact root; use a separate library for another account");return EXR_ARGUMENT;
  }
  if(same) { owner->bound=1;return EXR_OK; }
  GKeyFile *settings=g_key_file_new();g_key_file_set_string(settings,"account","id",owner->id);
  g_key_file_set_string(settings,"account","root",command->account_root);gsize size=0;
  char *data=g_key_file_to_data(settings,&size,NULL);g_key_file_free(settings);
  char *temporary=g_strdup_printf("%s.tmp-XXXXXX",owner->configuration);int file=g_mkstemp_full(temporary,O_RDWR|O_CLOEXEC,0600);
  int code=0,published=0;size_t at=0;
  if(file<0) code=1;
  while(!code && at<size) {
    ssize_t wrote=write(file,data+at,size-at);if(wrote<0 && errno==EINTR) continue;
    if(wrote<=0) code=1;else at+=(size_t)wrote;
  }
  if(file>=0) { if(!code && fsync(file)) code=1;if(close(file)) code=1; }
  if(!code) { if(link(temporary,owner->configuration)) code=1;else published=1; }
  if(file>=0 && unlink(temporary)<0 && errno!=ENOENT) code=1;
  g_free(temporary);g_free(data);
  if(published) {
    owner->bound=1;g_free(owner->root);owner->root=g_strdup(command->account_root);
    int directory=open(owner->home,O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
    if(directory<0) code=1;else { if(fsync(directory)) code=1;close(directory); }
  }
  if(code) { snprintf(result->message,sizeof(result->message),"Account root could not be saved; existing configuration was not replaced");return EXR_IO; }
  return EXR_OK;
}
static int accounts_secret_valid(const unsigned char *data,size_t size,size_t *user_bytes) {
  if(!data || size<3 || size>EXR_CREDENTIALS_SECRET_MAX) return 0;
  const unsigned char *zero=memchr(data,0,size);if(!zero || zero==data || zero==data+size-1) return 0;
  *user_bytes=(size_t)(zero-data);
  return !memchr(data,':',*user_bytes) && !memchr(zero+1,0,size-*user_bytes-1) &&
    g_utf8_validate((const char *)data,(gssize)*user_bytes,NULL) &&
    g_utf8_validate((const char *)zero+1,(gssize)(size-*user_bytes-1),NULL);
}
static exr_status accounts_secret_result(account_owner *owner,reader_result *result,const unsigned char *data,size_t size,int remember) {
  size_t user_bytes=0;
  if(!accounts_secret_valid(data,size,&user_bytes)) {
    result->account_credential_status=EXR_CRED_IO;snprintf(result->message,sizeof(result->message),"Stored credentials are invalid; they were not used");return EXR_OK;
  }
  result->account_user=strndup((const char *)data,user_bytes);
  result->account_password=strndup((const char *)data+user_bytes+1,size-user_bytes-1);
  if(!result->account_user || !result->account_password) return EXR_MEMORY;
  result->account_remember=remember;result->account_credential_status=EXR_CRED_OK;
  snprintf(result->message,sizeof(result->message),"%s",remember ? "Saved credentials loaded; password remains masked":"Credentials available for this app session only");
  (void)owner;return EXR_OK;
}
static exr_status accounts_load(account_owner *owner,const reader_command *command,reader_result *result) {
  result->account_response=1;
  if(!command->account_saved_only && owner->secret)
    return accounts_secret_result(owner,result,owner->secret,owner->secret_size,owner->secret_remember);
  unsigned char data[EXR_CREDENTIALS_SECRET_MAX];size_t size=0;
  exr_credentials_status code=owner->credentials ? exr_credentials_get(owner->credentials,owner->id,data,sizeof(data),&size):owner->open_status;
  result->account_credential_status=code;exr_status status=EXR_OK;
  if(code==EXR_CRED_OK) status=accounts_secret_result(owner,result,data,size,1);
  else snprintf(result->message,sizeof(result->message),"%s",code==EXR_CRED_UNAVAILABLE ?
    "Secure storage is unavailable. Choose this app session only":
    code==EXR_CRED_NOT_FOUND ? "No saved credentials for this account":"Secure storage could not be read; credentials were not used");
  exr_credentials_wipe(data,sizeof(data));return status;
}
static exr_status accounts_set(account_owner *owner,const reader_command *command,reader_result *result) {
  result->account_response=2;result->account_credential_status=EXR_CRED_ARGUMENT;
  const char *user=command->account_user,*password=command->account_password;
  if(!user || !password || !user[0] || !password[0] || strlen(user)>EXR_CREDENTIALS_SECRET_MAX ||
     strlen(password)>EXR_CREDENTIALS_SECRET_MAX || strlen(user)+1+strlen(password)>EXR_CREDENTIALS_SECRET_MAX) {
    snprintf(result->message,sizeof(result->message),"Enter a username and password within the secure storage limit");return EXR_ARGUMENT;
  }
  size_t size=strlen(user)+1+strlen(password),user_bytes=0;unsigned char *data=malloc(size);
  if(!data) return EXR_MEMORY;
  memcpy(data,user,strlen(user)+1);memcpy(data+strlen(user)+1,password,strlen(password));
  if(!accounts_secret_valid(data,size,&user_bytes)) {
    exr_credentials_wipe(data,size);free(data);snprintf(result->message,sizeof(result->message),"Credentials must be valid text; the username cannot contain a colon");return EXR_ARGUMENT;
  }
  exr_status status=accounts_bind(owner,command,result);
  if(status!=EXR_OK) { exr_credentials_wipe(data,size);free(data);return status; }
  exr_credentials_status code=EXR_CRED_OK;
  if(command->account_remember) code=owner->credentials ? exr_credentials_put(owner->credentials,owner->id,data,size):owner->open_status;
  result->account_credential_status=code;result->account_remember=command->account_remember;
  if(code==EXR_CRED_OK) {
    accounts_secret_clear(owner);owner->secret=data;owner->secret_size=size;owner->secret_remember=command->account_remember;
    snprintf(result->message,sizeof(result->message),"%s",command->account_remember ?
      "Credentials saved in system secure storage":"Using credentials for this app session only");
  } else {
    exr_credentials_wipe(data,size);free(data);
    snprintf(result->message,sizeof(result->message),"%s",code==EXR_CRED_UNAVAILABLE ?
      "Secure storage is unavailable; credentials were not saved. Choose this app session only":"Credentials were not saved. Try again or use this app session only");
  }
  return EXR_OK;
}
static exr_status accounts_pending(linux_reader *reader,reader_result *result) {
  exr_status status=metadata_ready(reader,result);if(status!=EXR_OK) return status;
  reader_metadata_result pending={0};reader_metadata_error error={0};
  reader_metadata_status code=reader_metadata_pending(reader->metadata,&pending,&error);
  if(code==READER_METADATA_NO_PENDING) return EXR_OK;
  result->metadata_pending=code==READER_METADATA_OK;
  snprintf(result->message,sizeof(result->message),"Finish the earlier library edit recovery before preparing a scan");return EXR_DATABASE;
}
static exr_status accounts_bootstrap(linux_reader *reader,const account_local_book *book,const char *hash,uint64_t bytes,reader_result *result,int *created) {
  reader_metadata_snapshot *snapshot=NULL;reader_metadata_error error={0};reader_metadata_result submitted={0};*created=0;
  reader_metadata_status code=reader_metadata_prepare_book(reader->metadata,book->key,&snapshot,&error);
  const reader_metadata_view *view=reader_metadata_snapshot_view(snapshot);
  if(code==READER_METADATA_NEEDS_BOOTSTRAP) {
    if(!view || strcmp(view->book.source_sha256,hash) || view->book.source_bytes!=bytes) code=READER_METADATA_CONFLICT;
    else {
      reader_metadata_verified_source proof={view->book.format,hash,bytes};
      code=reader_metadata_stage_bootstrap(reader->metadata,snapshot,&proof,&submitted,&error);
      if(code==READER_METADATA_OK) code=reader_metadata_finish_pending(reader->metadata,&submitted,&error);
      if(code==READER_METADATA_OK) *created=1;
    }
  } else if(code==READER_METADATA_CONFLICT && view && view->present && view->graph.revisions && !view->needs_bootstrap &&
      !strcmp(view->book.book_key,book->key) && !strcmp(view->book.source_sha256,hash) && view->book.source_bytes==bytes) {
    /* Original identity is proven independently. Stage its bytes while keeping
       every existing head and product field; raw sync does not select a head. */
    code=READER_METADATA_OK;
  }
  reader_metadata_snapshot_free(snapshot);
  if(code==READER_METADATA_OK) return EXR_OK;
  snprintf(result->message,sizeof(result->message),"Book history could not be prepared; retained versions and pending edits were kept");
  return metadata_pending_failure(reader,result,code,&error);
}
static exr_status accounts_file_matches(const char *path,const char *hash,uint64_t bytes,account_control *control) {
  int file=open(path,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);if(file<0) return EXR_IO;
  struct stat before,after;exr_status status=EXR_DATABASE;GChecksum *sum=NULL;uint64_t total=0;unsigned char data[65536];
  if(fstat(file,&before)<0 || !accounts_private_file(&before) || before.st_size<0 ||
     (uint64_t)before.st_size!=bytes || bytes>EXR_SIDELOAD_STREAM_LIMIT) goto done;
  sum=g_checksum_new(G_CHECKSUM_SHA256);if(!sum) { status=EXR_MEMORY;goto done; }
  for(;;) {
    if(accounts_cancelled(control)) { status=EXR_CANCELLED;goto done; }
    ssize_t got=read(file,data,sizeof(data));if(got<0 && errno==EINTR) continue;
    if(got<0) { status=EXR_IO;goto done; }
    if(!got) break;
    total+=(uint64_t)got;if(total>bytes) goto done;
    g_checksum_update(sum,data,(gssize)got);
    accounts_progress(control,EXR_STAGE_READ,total,bytes);
  }
  if(fstat(file,&after)<0 || before.st_ino!=after.st_ino || before.st_size!=after.st_size ||
     before.st_mtim.tv_sec!=after.st_mtim.tv_sec || before.st_mtim.tv_nsec!=after.st_mtim.tv_nsec) goto done;
  if(total==bytes && !strcmp(g_checksum_get_string(sum),hash)) status=EXR_OK;
done:
  if(sum) g_checksum_free(sum);
  close(file);return status;
}
static int accounts_receive_local(void *opaque,const reader_catalog_row *row) {
  account_owner *owner=opaque;if(owner->count>=50) return 1;
  account_local_book *book=&owner->page[owner->count++];book->key=strdup(row->book_key);book->sort=strdup(row->sort_title);
  book->id=row->sdk_book_id;book->bytes=row->source_bytes;return !book->key || !book->sort;
}
static exr_status accounts_prepare_book(linux_reader *reader,account_owner *owner,const account_local_book *book,account_control *control,reader_result *result) {
  if(control->shared) {
    g_atomic_int_set(&control->shared->current_bytes,0);
    g_atomic_int_set(&control->shared->total_bytes,book->bytes<=EXR_SIDELOAD_STREAM_LIMIT ? (gint)book->bytes:0);
  }
  exr_source probe={0};exr_error error={0};exr_status status=exr_library_source(reader->library,book->id,&probe,&error);
  if(status!=EXR_OK) { owner->pending++;return EXR_OK; }
  int available=probe.read_at && probe.release && probe.size && probe.size<=EXR_SIDELOAD_STREAM_LIMIT && probe.size==book->bytes;
  if(probe.release) probe.release(probe.context);
  if(!available) { owner->pending++;return EXR_OK; }
  char hash[65];uint64_t bytes=0;exr_control options={accounts_cancelled,accounts_progress,control};
  status=reader_catalog_sdk_original_identity(reader->library,book->id,&options,hash,&bytes,&error);
  if(status==EXR_CANCELLED) return status;
  const char *colon=strchr(book->key,':');
  if(status!=EXR_OK || !colon || strcmp(colon+1,hash) || bytes!=book->bytes || bytes>EXR_SIDELOAD_STREAM_LIMIT) {
    owner->failed++;snprintf(result->message,sizeof(result->message),"Stored original identity did not match; it was not staged");return EXR_DATABASE;
  }
  status=accounts_pending(reader,result);if(status!=EXR_OK) { owner->failed++;return status; }
  int bootstrapped=0;status=accounts_bootstrap(reader,book,hash,bytes,result,&bootstrapped);
  owner->bootstraps+=(uint64_t)bootstrapped;if(status!=EXR_OK) { owner->failed++;return status; }
  size_t format_bytes=(size_t)(colon-book->key);
  if(!format_bytes || format_bytes>4) { owner->failed++;return EXR_ARGUMENT; }
  char filename[80];snprintf(filename,sizeof(filename),"%s.%.*s",hash,(int)format_bytes,book->key);
  char *destination=g_build_filename(owner->originals,filename,NULL);struct stat info;
  if(lstat(destination,&info)==0) {
    status=accounts_file_matches(destination,hash,bytes,control);
    if(status==EXR_OK) owner->existing++;
  } else if(errno==ENOENT) {
    exr_sideload_options export_options={0};export_options.struct_size=sizeof(export_options);export_options.control=options;
    uint64_t written=0;status=exr_sideload_export_original(reader->library,book->id,destination,&export_options,&written,&error);
    if(status==EXR_OK && written==bytes) { owner->prepared++;status=accounts_file_matches(destination,hash,bytes,control); }
    else if(status==EXR_OK) status=EXR_IO;
  } else status=EXR_IO;
  g_free(destination);
  if(status!=EXR_OK && status!=EXR_CANCELLED) {
    owner->failed++;snprintf(result->message,sizeof(result->message),"An original could not be staged or verified; existing files were not replaced");
  }
  return status;
}
static exr_status accounts_stage(linux_reader *reader,account_owner *owner,const reader_command *command,reader_result *result) {
  account_control control={reader,command->account_control};exr_status status=EXR_OK;result->account_response=4;
  if(command->action==READER_ACCOUNT_STAGE_BEGIN) {
    status=accounts_pending(reader,result);if(status!=EXR_OK) return status;
    if(!owner->bound || !owner->secret || !accounts_private_directory(owner->work,1) || !accounts_private_directory(owner->originals,1)) {
      snprintf(result->message,sizeof(result->message),"Apply credentials and a private account root before scanning");return EXR_IO;
    }
    accounts_page_clear(owner);g_clear_pointer(&owner->cursor_title,g_free);g_clear_pointer(&owner->cursor_key,g_free);
    owner->seen=owner->prepared=owner->existing=owner->pending=owner->failed=owner->bootstraps=0;owner->staging=1;
  }
  if(!owner->staging) return EXR_ARGUMENT;
  if(accounts_cancelled(&control)) { owner->staging=0;return EXR_CANCELLED; }
  if(owner->index==owner->count) {
    accounts_page_clear(owner);reader_catalog_error error={0};
    int code=reader_catalog_local_page(reader->catalog,owner->cursor_title,owner->cursor_key,NULL,1,50,accounts_receive_local,owner,&error);
    if(code) { owner->staging=0;return EXR_DATABASE; }
    for(size_t i=0;i<owner->count;i++) if(!owner->page[i].key || !owner->page[i].sort) { owner->staging=0;return EXR_MEMORY; }
    if(!owner->count) { owner->staging=0;return EXR_OK; }
    account_local_book *last=&owner->page[owner->count-1];
    g_free(owner->cursor_title);g_free(owner->cursor_key);owner->cursor_title=g_strdup(last->sort);owner->cursor_key=g_strdup(last->key);
  }
  owner->seen++;status=accounts_prepare_book(reader,owner,&owner->page[owner->index++],&control,result);
  if(status!=EXR_OK || (owner->index==owner->count && owner->count<50)) owner->staging=0;
  return status;
}
static void accounts_execute(linux_reader *reader,const reader_command *command,reader_result *result) {
  account_owner *owner=NULL;result->status=accounts_ready(reader,result,&owner);result->has_account=1;
  if(result->status!=EXR_OK) return;
  result->account_credential_status=EXR_CRED_OK;
  if(command->action==READER_ACCOUNT_LOAD) result->status=accounts_load(owner,command,result);
  else if(command->action==READER_ACCOUNT_SET) result->status=accounts_set(owner,command,result);
  else if(command->action==READER_ACCOUNT_DELETE) {
    result->account_response=3;accounts_secret_clear(owner);
    exr_credentials_status code=owner->credentials ? exr_credentials_delete(owner->credentials,owner->id):owner->open_status;
    result->account_credential_status=code;
    snprintf(result->message,sizeof(result->message),"%s",code==EXR_CRED_OK || code==EXR_CRED_NOT_FOUND ?
      "Saved credentials removed; account root remains bound":"Secure storage unavailable or failed; saved deletion was not confirmed. Session memory was cleared");
  } else result->status=accounts_stage(reader,owner,command,result);
  result->account_id=strdup(owner->id);result->account_root=strdup(owner->root);result->account_bound=owner->bound;
  result->account_more=owner->staging;result->account_page_rows=owner->count;
  result->account_seen=owner->seen;result->account_prepared=owner->prepared;result->account_existing=owner->existing;
  result->account_pending=owner->pending;result->account_failed=owner->failed;result->account_bootstraps=owner->bootstraps;
  if(!result->account_id || !result->account_root) result->status=EXR_MEMORY;
  if(result->status==EXR_CANCELLED) snprintf(result->message,sizeof(result->message),"Preparation cancelled; previously saved book details and staged originals are retained");
}
