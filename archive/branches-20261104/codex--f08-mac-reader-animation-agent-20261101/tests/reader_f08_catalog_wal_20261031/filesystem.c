/* Exercise the production filesystem fallback without mounting or changing a database. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <linux/magic.h>
#include <stdlib.h>
#include <string.h>
#include <sys/vfs.h>
int statfs(const char *path,struct statfs *out) {
  int (*real_statfs)(const char *,struct statfs *)=dlsym(RTLD_NEXT,"statfs");
  if(!real_statfs) { errno=ENOSYS;return -1; }
  int result=real_statfs(path,out);
  const char *mode=getenv("F08_FILESYSTEM");
  if(result==0 && mode && strstr(path,"product-")) {
    if(!strcmp(mode,"error")) { errno=EACCES;return -1; }
    out->f_type=!strcmp(mode,"nfs") ? NFS_SUPER_MAGIC:0;
  }
  return result;
}
