/* SPDX-License-Identifier: MIT */
/* Included inside webdav.cpp's private namespace; Linux opt-in only. */
struct managed_fd {
  int value=-1;
  managed_fd()=default;
  explicit managed_fd(int v):value(v){}
  ~managed_fd(){if(value>=0)close(value);}
  managed_fd(const managed_fd &)=delete;
  managed_fd &operator=(const managed_fd &)=delete;
};
uint32_t managed_crc(const std::string &s) {
  uint32_t c=0xffffffffu;
  for(unsigned char b:s){c^=b;for(int i=0;i<8;i++)c=(c>>1)^(0xedb88320u&(0u-(c&1u)));}
  return ~c;
}
bool managed_hex(const std::string &s,size_t n) {
  if(s.size()!=n)return false;
  for(char c:s)if(!((c>='0'&&c<='9')||(c>='a'&&c<='f')))return false;
  return true;
}
#ifdef EXR_WEBDAV_MANAGED_TEST_HOOKS
extern "C" void exr_webdav_managed_test_hook(const char *);
#define MANAGED_HOOK(p) exr_webdav_managed_test_hook(p)
#else
#define MANAGED_HOOK(p) ((void)0)
#endif
struct managed_pool {
  managed_fd parent,directory,lock;
  std::string profile;
  exr_webdav_managed_snapshot view{};
  exr_wc_root *handles[EXR_WEBDAV_MANAGED_ROOT_LIMIT]{};
  std::thread::id owner=std::this_thread::get_id();
  bool poisoned=false;
  managed_pool(){view.enabled=1;view.status=EXR_WC_REFUSED;}
  ~managed_pool(){for(auto &r:handles)exr_wc_close(&r);}
  [[noreturn]] void fail(int code,const char *message,int error=0) {
    view.status=code;view.native_error=error;
    if(code==EXR_WC_UNCERTAIN){poisoned=true;view.receipt_uncertain=1;}
    reject(code==EXR_WC_LIMIT?EXR_DAV_LIMIT:EXR_DAV_IO,message);
  }
  void check_owner() {
    if(owner!=std::this_thread::get_id())reject(EXR_DAV_ARGUMENT,"Managed client requires its enabling worker");
  }
  static bool private_dir(int fd) {
    struct stat s{};
    return fd>=0 && !fstat(fd,&s) && S_ISDIR(s.st_mode) && s.st_uid==geteuid() && !(s.st_mode&077);
  }
  static bool private_file(int fd) {
    struct stat s{};
    return fd>=0 && !fstat(fd,&s) && S_ISREG(s.st_mode) && s.st_uid==geteuid() && !(s.st_mode&077) && s.st_nlink==1;
  }
  std::string registry() const {
    std::string value="EXReader managed registry 1\n"+profile+"\n"+std::to_string(view.roots)+"\n";
    for(unsigned i=0;i<view.roots;i++){
      const auto &r=view.root[i];value+=std::string(r.leaf)+" "+(r.unbound?"-":r.uuid)+"\n";
    }
    char crc[10];std::snprintf(crc,sizeof(crc),"%08x",managed_crc(value));
    return value+crc+"\n";
  }
  void save() {
    if(poisoned)fail(EXR_WC_UNCERTAIN,"Download cleanup records need attention");
    const std::string bytes=registry();
    managed_fd next(openat(directory.value,"registry.next",O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600));
    if(next.value<0)fail(EXR_WC_UNCERTAIN,"Cannot safely update download cleanup records",errno);
    size_t offset=0;
    while(offset<bytes.size()){
      ssize_t n=write(next.value,bytes.data()+offset,bytes.size()-offset);
      if(n<0 && errno==EINTR)continue;
      if(n<=0)fail(EXR_WC_UNCERTAIN,"Cannot write download cleanup records",errno);
      offset+=(size_t)n;
    }
    if(fsync(next.value))fail(EXR_WC_UNCERTAIN,"Cannot flush download cleanup records",errno);
    MANAGED_HOOK("registry_next");
    if(renameat(directory.value,"registry.next",directory.value,"registry") || fsync(directory.value))
      fail(EXR_WC_UNCERTAIN,"Download cleanup record update is uncertain",errno);
  }
  void load() {
    managed_fd file(openat(directory.value,"registry",O_RDONLY|O_CLOEXEC|O_NOFOLLOW));
    struct stat s{};
    if(!private_file(file.value)||fstat(file.value,&s)||s.st_size<=0||s.st_size>16384)
      fail(EXR_WC_REFUSED,"Download cleanup records cannot be verified",errno);
    std::string bytes((size_t)s.st_size,'\0');size_t offset=0;
    while(offset<bytes.size()){
      ssize_t n=read(file.value,&bytes[offset],bytes.size()-offset);
      if(n<0 && errno==EINTR)continue;
      if(n<=0)fail(EXR_WC_REFUSED,"Download cleanup records are incomplete",errno);
      offset+=(size_t)n;
    }
    std::istringstream input(bytes);std::string magic,binding,count,line;
    if(!std::getline(input,magic)||magic!="EXReader managed registry 1"||
       !std::getline(input,binding)||binding!=profile||!std::getline(input,count)||
       count.empty()||count.size()>2||count.find_first_not_of("0123456789")!=std::string::npos)
      fail(EXR_WC_REFUSED,"Download cleanup profile identity differs");
    unsigned total=(unsigned)std::stoul(count);
    if(total>EXR_WEBDAV_MANAGED_ROOT_LIMIT)fail(EXR_WC_REFUSED,"Download cleanup registry exceeds its limit");
    std::set<std::string> leaves,uuids;
    for(unsigned i=0;i<total;i++){
      if(!std::getline(input,line))fail(EXR_WC_REFUSED,"Download cleanup records are incomplete");
      size_t space=line.find(' ');std::string leaf=line.substr(0,space),id=space==std::string::npos?"":line.substr(space+1);
      if(leaf.substr(0,5)!="root-"||!managed_hex(leaf.substr(5),32)||!leaves.insert(leaf).second||
         (id!="-"&&(!managed_hex(id,32)||!uuids.insert(id).second)))
        fail(EXR_WC_REFUSED,"Download cleanup root identity is invalid");
      auto &r=view.root[i];std::snprintf(r.leaf,sizeof(r.leaf),"%s",leaf.c_str());r.unbound=id=="-";
      if(!r.unbound)std::snprintf(r.uuid,sizeof(r.uuid),"%s",id.c_str());
    }
    view.roots=total;
    if(registry()!=bytes)fail(EXR_WC_REFUSED,"Download cleanup record checksum differs");
  }
  void summarize() {
    view.cleanup_pending=0;view.receipt_uncertain=poisoned?1:0;
    bool available=view.roots<EXR_WEBDAV_MANAGED_ROOT_LIMIT;
    for(unsigned i=0;i<view.roots;i++){
      auto &r=view.root[i];view.cleanup_pending+=r.pending;
      if(r.unbound||(r.status!=EXR_WC_OK&&!r.pending))++view.cleanup_pending;
      if(r.receipt_uncertain)view.receipt_uncertain=1;
      if(handles[i]&&r.status==EXR_WC_OK&&!r.pending&&!r.refused&&!r.receipt_uncertain&&r.slots<64)available=true;
    }
    view.capacity_exhausted=!available;
  }
  void inspect(unsigned i) {
    auto &r=view.root[i];r.slots=0;r.pending=0;
    for(unsigned j=0;j<64;j++){
      exr_wc_info info{};
      if(exr_wc_inspect(handles[i],j,&info)!=EXR_WC_OK)break;
      r.slots++;if(info.state!=EXR_WC_CLEANED)r.pending++;
    }
    summarize();
  }
  void open(const char *name) {
    if(!name||!*name||strnlen(name,8193)>8192||!utf8(name))fail(EXR_WC_ARGUMENT,"Invalid download cleanup profile");
    std::filesystem::path p=std::filesystem::u8path(name);
    if(!p.is_absolute()||p.lexically_normal()!=std::filesystem::canonical(p))
      fail(EXR_WC_REFUSED,"Download cleanup profile must be a canonical private directory");
    profile=p.u8string();parent.value=::open(name,O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
    if(!private_dir(parent.value))fail(EXR_WC_REFUSED,"Download cleanup profile is not private",errno);
    bool fresh=mkdirat(parent.value,"webdav-managed-v1",0700)==0;
    if(!fresh && errno!=EEXIST)fail(EXR_WC_IO,"Cannot create download cleanup directory",errno);
    directory.value=openat(parent.value,"webdav-managed-v1",O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
    if(!private_dir(directory.value))fail(EXR_WC_REFUSED,"Download cleanup directory cannot be verified",errno);
    if(fresh && fsync(parent.value))fail(EXR_WC_UNCERTAIN,"Download cleanup directory creation is uncertain",errno);
    lock.value=openat(directory.value,"registry.lock",O_RDWR|O_CLOEXEC|O_NOFOLLOW|(fresh?(O_CREAT|O_EXCL):0),0600);
    if(!private_file(lock.value))fail(EXR_WC_REFUSED,"Download cleanup lock cannot be verified",errno);
    if(flock(lock.value,LOCK_EX|LOCK_NB))fail(errno==EWOULDBLOCK?EXR_WC_BUSY:EXR_WC_IO,"Download cleanup is busy",errno);
    struct stat st{};
    if(fstatat(directory.value,"registry.next",&st,AT_SYMLINK_NOFOLLOW)==0 || errno!=ENOENT)
      fail(EXR_WC_UNCERTAIN,"Download cleanup record update needs attention",errno);
    if(fresh)save();else load();
    // Only a bounded, explicitly registered namespace may be used.
    int scan=openat(directory.value,".",O_RDONLY|O_DIRECTORY|O_CLOEXEC);
    DIR *dir=scan<0?nullptr:fdopendir(scan);
    if(!dir){if(scan>=0)close(scan);fail(EXR_WC_IO,"Cannot inspect download cleanup directory",errno);}
    bool unknown=false;unsigned entries=0;errno=0;
    while(auto *e=readdir(dir)){
      std::string leaf=e->d_name;if(leaf=="."||leaf=="..")continue;
      if(++entries>EXR_WEBDAV_MANAGED_ROOT_LIMIT+2){unknown=true;break;}
      bool known=leaf=="registry"||leaf=="registry.lock";
      for(unsigned i=0;i<view.roots;i++)if(leaf==view.root[i].leaf)known=true;
      if(!known){unknown=true;break;}
    }
    int scan_error=errno;closedir(dir);
    if(unknown||scan_error)fail(EXR_WC_REFUSED,"Unregistered download cleanup files were preserved",scan_error);
    view.status=EXR_WC_OK;
    for(unsigned i=0;i<view.roots;i++){
      auto &r=view.root[i];if(r.unbound)continue;
      r.status=exr_wc_open_at(directory.value,r.leaf,r.uuid,&handles[i]);
      if(r.status!=EXR_WC_OK){if(view.status==EXR_WC_OK)view.status=r.status;continue;}
      exr_wc_recovery_report rep{};
      r.status=exr_wc_recover(handles[i],0,64,&rep);
      r.receipt_uncertain=rep.receipt_uncertain;r.refused=rep.refused;
      view.cleaned+=rep.cleaned;
      if(rep.native_error)view.native_error=rep.native_error;
      inspect(i);
    }
    summarize();
  }
  unsigned select() {
    check_owner();view.published=0;
    if(view.status!=EXR_WC_OK||poisoned)fail(view.status,"Download cleanup is unavailable",view.native_error);
    for(unsigned i=0;i<view.roots;i++){
      const auto &r=view.root[i];
      if(handles[i]&&r.status==EXR_WC_OK&&!r.pending&&!r.refused&&!r.receipt_uncertain&&r.slots<64)return i;
    }
    if(view.roots==EXR_WEBDAV_MANAGED_ROOT_LIMIT){view.capacity_exhausted=1;fail(EXR_WC_LIMIT,"Temporary download capacity is exhausted");}
    unsigned char random[16];managed_fd entropy(::open("/dev/urandom",O_RDONLY|O_CLOEXEC));
    if(entropy.value<0||read(entropy.value,random,sizeof(random))!=(ssize_t)sizeof(random))
      fail(EXR_WC_IO,"Cannot allocate a download cleanup identity",errno);
    std::string leaf="root-";const char *hex="0123456789abcdef";
    for(unsigned char b:random){leaf+=hex[b>>4];leaf+=hex[b&15];}
    unsigned i=view.roots++;auto &r=view.root[i];r.unbound=1;
    std::snprintf(r.leaf,sizeof(r.leaf),"%s",leaf.c_str());save();
    MANAGED_HOOK("registry_allocating");
    r.status=exr_wc_create_at(directory.value,r.leaf,&handles[i],r.uuid);
    if(r.status!=EXR_WC_OK){summarize();fail(r.status,"Cannot create a registered download cleanup root",errno);}
    MANAGED_HOOK("root_created");
    r.unbound=0;save();MANAGED_HOOK("registry_ready");summarize();return i;
  }
};
class managed_temporary {
  managed_pool &pool;unsigned index=0;exr_wc_tx *tx=nullptr;managed_fd destination;int file=-1;
  std::string leaf;
public:
  managed_temporary(managed_pool &p,const char *folder,const char *name):pool(p),leaf(name) {
    pool.check_owner();pool.view.published=0;
    if(leaf.empty()||leaf.size()>120||leaf.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.")!=std::string::npos||leaf[0]=='.')
      reject(EXR_DAV_ARGUMENT,"Managed destination requires a bounded plain filename");
    destination.value=::open(folder,O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
    if(!managed_pool::private_dir(destination.value))pool.fail(EXR_WC_REFUSED,"Download destination is not private",errno);
    struct stat a{},b{};if(fstat(destination.value,&a)||fstat(pool.directory.value,&b)||a.st_dev!=b.st_dev)
      pool.fail(EXR_WC_REFUSED,"Download destination must share the cleanup filesystem",errno);
    index=pool.select();auto &r=pool.view.root[index];
    int code=exr_wc_begin(pool.handles[index],&tx,&file);
    if(code!=EXR_WC_OK){r.status=code;r.receipt_uncertain=code==EXR_WC_UNCERTAIN;pool.inspect(index);pool.fail(code,"Cannot reserve managed download staging",errno);}
    MANAGED_HOOK("managed_owned");
  }
  ~managed_temporary() {
    if(!tx)return;
    auto &r=pool.view.root[index];
    if(!r.receipt_uncertain){
      exr_wc_cleanup_result result{};
      int code=exr_wc_cleanup(tx,pool.view.published?0:1,&result);
      if(code!=EXR_WC_OK && code!=EXR_WC_IO)r.status=code;
      r.receipt_uncertain=result.receipt_uncertain;
      if(result.native_error)pool.view.native_error=result.native_error;
    }
    exr_wc_tx_close(&tx);pool.inspect(index);
  }
  void write(const void *bytes,size_t size) {
    const char *p=(const char *)bytes;
    while(size){ssize_t n=::write(file,p,size);if(n<0&&errno==EINTR)continue;
      if(n<=0)reject(EXR_DAV_IO,"Cannot write managed download");
      p+=n;size-=(size_t)n;}
  }
  void publish(const exr_webdav_control *control) {
    cancelled(control);auto &r=pool.view.root[index];
    int code=exr_wc_seal(tx);file=-1;
    if(code!=EXR_WC_OK){r.status=code;r.receipt_uncertain=code==EXR_WC_UNCERTAIN;pool.fail(code,"Cannot seal managed download",errno);}
    MANAGED_HOOK("managed_sealed");cancelled(control);
    exr_wc_publish_result result{};code=exr_wc_publish_at(tx,destination.value,leaf.c_str(),&result);
    pool.view.published=result.published;r.receipt_uncertain=result.receipt_uncertain;
    if(result.native_error)pool.view.native_error=result.native_error;
    if(result.published){MANAGED_HOOK("managed_published");return;}
    if(code==EXR_WC_UNCERTAIN)r.status=code;
    reject(code==EXR_WC_EXISTS?EXR_DAV_EXISTS:EXR_DAV_IO,"Managed destination publication refused");
  }
};
#undef MANAGED_HOOK
