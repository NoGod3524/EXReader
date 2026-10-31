/* SPDX-License-Identifier: MIT */
#define _DARWIN_C_SOURCE 1
#define _POSIX_C_SOURCE 200809L
#define _XOPEN_SOURCE 700
#include <exr_pc02_sdk.h>
#include <exr/library.h>
#include <pwd.h>
#include <unistd.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
#include <errno.h>
int pc02_user_authority(char *out,size_t capacity) {
 struct passwd entry,*found=NULL;char data[16384],home_path[PATH_MAX];int n;
 if(!out||!capacity)return 0;
 out[0]=0;
 if(getpwuid_r(geteuid(),&entry,data,sizeof(data),&found)||!found||!entry.pw_dir||
    !realpath(entry.pw_dir,home_path))return 0;
 n=snprintf(out,capacity,"%s/.exreader-c02-admission",home_path);
 return n>0&&(size_t)n<capacity;
}
static int quiet(const char *path) {
 const char *suffix[]={"-wal","-shm","-journal"};char next[PATH_MAX];struct stat st;
 for(size_t k=0;k<3;k++){
  int n=snprintf(next,sizeof(next),"%s%s",path,suffix[k]);
  if(n<0||(size_t)n>=sizeof(next)||lstat(next,&st)==0||errno!=ENOENT)return 0;
 }
 return 1;
}
static int same_target(const char *path,int fd) {
 struct stat expected,actual;int other=open(path,O_RDONLY|O_CLOEXEC|O_NOFOLLOW),ok=0;
 if(other<0)return 0;
 ok=!fstat(fd,&expected)&&!fstat(other,&actual)&&S_ISREG(actual.st_mode)&&
    actual.st_nlink==1&&actual.st_dev==expected.st_dev&&actual.st_ino==expected.st_ino;
 close(other);return ok;
}
static int initial_proof(void *context,const char *path,int fd,
 const pc02_pending_record *pending,const char *terminal) {
 pc02_sdk_proof *result=context;exr_library *library=NULL;exr_book *books=NULL;
 exr_error error={0};exr_source source={0};size_t count=0;uint64_t total=0;
 unsigned char buffer[65536];int ok=0;
 if(!result||pending||terminal||!same_target(path,fd)||!quiet(path)||
    exr_library_open(path,&library,&error)!=EXR_OK)goto done;
 if(exr_library_books(library,NULL,&books,&count,&error)!=EXR_OK)goto done;
 for(size_t k=0;k<count;k++){
  uint64_t offset=0;
  if(exr_library_source(library,books[k].id,&source,&error)!=EXR_OK||
     !source.read_at||!source.release||UINT64_MAX-total<source.size)goto done;
  while(offset<source.size){
   size_t want=(size_t)((source.size-offset)>sizeof(buffer)?sizeof(buffer):source.size-offset);
   if(source.read_at(source.context,offset,buffer,want)!=want)goto done;
   offset+=want;
  }
  total+=source.size;source.release(source.context);memset(&source,0,sizeof(source));
 }
 result->books=count;result->original_bytes=total;ok=1;
done:
 if(source.release)source.release(source.context);
 exr_books_free(books,count);exr_library_close(library);
 return ok&&same_target(path,fd)&&quiet(path);
}
int pc02_sdk_open_user(const char *path,pc02_lease **out) {
 char authority[PATH_MAX];
 if(out)*out=NULL;
 return out&&pc02_user_authority(authority,sizeof(authority))&&
   pc02_open(authority,path,PC02_SHARED,NULL,NULL,out);
}
int pc02_sdk_enroll_user(const char *path,int create,pc02_sdk_proof *proof) {
 char authority[PATH_MAX];
 if(proof)memset(proof,0,sizeof(*proof));
 return proof&&pc02_user_authority(authority,sizeof(authority))&&
   (pc02_enroll(authority,path,create,initial_proof,proof,NULL)||
    (pc02_authority_create(authority)&&pc02_enroll(authority,path,create,initial_proof,proof,NULL)));
}
int pc02_sdk_recover_enrollment_user(const char *path,pc02_sdk_proof *proof) {
 char authority[PATH_MAX];
 if(proof)memset(proof,0,sizeof(*proof));
 return proof&&pc02_user_authority(authority,sizeof(authority))&&
   pc02_recover_enrollment(authority,path,initial_proof,proof,NULL);
}
int pc02_sdk_enroll_in(pc02_scope *scope,const char *authority,const char *path,int create,pc02_sdk_proof *proof) {
 if(proof)memset(proof,0,sizeof(*proof));
 return proof&&(pc02_enroll_in(scope,authority,path,create,initial_proof,proof,NULL)||
   (pc02_authority_create_in(scope,authority)&&
    pc02_enroll_in(scope,authority,path,create,initial_proof,proof,NULL)));
}
int pc02_sdk_recover_enrollment_in(pc02_scope *scope,const char *authority,const char *path,pc02_sdk_proof *proof) {
 if(proof)memset(proof,0,sizeof(*proof));
 return proof&&pc02_recover_enrollment_in(scope,authority,path,initial_proof,proof,NULL);
}
