/* SPDX-License-Identifier: MIT */
/* F10 GTK temp-file recovery: real abrupt-exit residues from forked writers
   (write, fsync, _exit(77) before publish) must be removed by the startup
   cleanup in linux_reader_open once the library lock is held, while every
   look-alike that is not an owned private stage is kept, and a second process
   cannot clean while the first holds the library. */
#define _POSIX_C_SOURCE 200809L
#include "../../examples/linux/reading.h"
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
#define CHECK(x) do { if(!(x)) { fprintf(stderr,"FAIL %d: %s (errno %d)\n",__LINE__,#x,errno);exit(1); } } while(0)

static char home[4096];
static const char *path(const char *name) {
  static char buffers[8][4300];static int next;char *out=buffers[next++%8];
  snprintf(out,4300,"%s/%s",home,name);return out;
}
static int exists(const char *name) { struct stat info;return lstat(path(name),&info)==0; }
static void write_file(const char *name,const char *text) {
  int file=open(path(name),O_WRONLY|O_CREAT|O_TRUNC|O_CLOEXEC,0600);CHECK(file>=0);
  CHECK(write(file,text,strlen(text))==(ssize_t)strlen(text));CHECK(!fsync(file));CHECK(!close(file));
}
/* A real interrupted writer: create the stage exactly as the host does,
   write and flush, then die before rename/link/unlink. */
static void abrupt_writer(const char *name) {
  pid_t child=fork();CHECK(child>=0);
  if(!child) {
    int file=open(path(name),O_RDWR|O_CREAT|O_EXCL|O_CLOEXEC,0600);
    if(file<0) _exit(3);
    if(write(file,"partial",7)!=7 || fsync(file)) _exit(4);
    _exit(77);
  }
  int status=0;CHECK(waitpid(child,&status,0)==child);CHECK(WIFEXITED(status) && WEXITSTATUS(status)==77);
  CHECK(exists(name));
}

int main(int argc,char **argv) {
  if(argc!=3) { fprintf(stderr,"usage: %s WORK_DIR FONT\n",argv[0]);return 2; }
  snprintf(home,sizeof(home),"%s/scavenge-home",argv[1]);
  CHECK(!mkdir(argv[1],0700) || errno==EEXIST);CHECK(!mkdir(home,0700));
  CHECK(!mkdir(path("sync-work"),0700));CHECK(!mkdir(path("sync-originals"),0700));CHECK(!mkdir(path("sync-work/nested"),0700));
  const char *hex="0123456789abcdef0123456789abcdef";char webdav_a[128],webdav_b[128],webdav_nested[160];
  snprintf(webdav_a,sizeof(webdav_a),"sync-work/.exr-webdav-%s.tmp",hex);
  snprintf(webdav_b,sizeof(webdav_b),"sync-originals/.exr-webdav-%s.tmp","fedcba9876543210fedcba9876543210");
  snprintf(webdav_nested,sizeof(webdav_nested),"sync-work/nested/.exr-webdav-%s.tmp",hex);
  /* Residues the cleanup must remove (4). */
  abrupt_writer("account.ini.tmp-Ab12Cd");
  abrupt_writer("library.sqlite.product.sqlite.reading.pending.Zx9Yw8");
  abrupt_writer(webdav_a);abrupt_writer(webdav_b);
  puts("PASS four_real_abrupt_exit_stages_present_before_startup");
  /* Look-alikes the cleanup must keep (7). */
  write_file("account.ini","[account]\nid=kept\n");
  write_file("keep.bin","keep");
  CHECK(!symlink(path("keep.bin"),path("account.ini.tmp-Sym123")));
  CHECK(!link(path("keep.bin"),path("account.ini.tmp-Hrd123")));
  CHECK(!mkdir(path("library.sqlite.product.sqlite.reading.pending.Dir123"),0700));
  write_file("account.ini.tmp-toolong1","x");
  write_file("account.ini.tmp-Bad!12","x");
  write_file(webdav_nested,"x");
  char short_webdav[96];snprintf(short_webdav,sizeof(short_webdav),"sync-work/.exr-webdav-%.31s.tmp",hex);
  write_file(short_webdav,"x");
  /* First process takes the library lock and runs the production startup. */
  char database[4300];snprintf(database,sizeof(database),"%s/library.sqlite",home);
  linux_reader *reader=NULL;exr_error error={0};
  CHECK(linux_reader_open(database,argv[2],NULL,&reader,&error)==EXR_OK);
  linux_scavenge_counts counts=linux_reader_scavenged(reader);
  CHECK(!exists("account.ini.tmp-Ab12Cd") && !exists("library.sqlite.product.sqlite.reading.pending.Zx9Yw8"));
  CHECK(!exists(webdav_a) && !exists(webdav_b));
  CHECK(exists("account.ini") && exists("keep.bin") && exists("account.ini.tmp-Sym123") && exists("account.ini.tmp-Hrd123"));
  CHECK(exists("library.sqlite.product.sqlite.reading.pending.Dir123") && exists("account.ini.tmp-toolong1"));
  CHECK(exists("account.ini.tmp-Bad!12") && exists(webdav_nested) && exists(short_webdav));
  char buffer[32]={0};int file=open(path("keep.bin"),O_RDONLY|O_CLOEXEC);CHECK(file>=0);
  CHECK(read(file,buffer,sizeof(buffer)-1)==4 && !strcmp(buffer,"keep"));close(file);
  /* Matching-name symlink, hard link and directory are counted as kept. */
  CHECK(counts.removed==4 && counts.kept==3);
  printf("PASS startup_scavenger removed=%u kept=%u: interrupted account.ini, pending-records and WebDAV stages removed; "
         "symlink, hard link, directory, malformed, nested and non-matching names kept; published files untouched\n",
         counts.removed,counts.kept);
  /* While this process holds the library, a second process must not clean. */
  abrupt_writer("account.ini.tmp-Live99");
  pid_t child=fork();CHECK(child>=0);
  if(!child) {
    linux_reader *second=NULL;exr_error second_error={0};
    exr_status status=linux_reader_open(database,argv[2],NULL,&second,&second_error);
    _exit(status==EXR_IO && !second ? 0:1);
  }
  int status=0;CHECK(waitpid(child,&status,0)==child);CHECK(WIFEXITED(status) && WEXITSTATUS(status)==0);
  CHECK(exists("account.ini.tmp-Live99"));
  puts("PASS second_process_refused_by_library_lock_and_cleaned_nothing");
  linux_reader_close(reader);reader=NULL;
  CHECK(linux_reader_open(database,argv[2],NULL,&reader,&error)==EXR_OK);
  counts=linux_reader_scavenged(reader);CHECK(!exists("account.ini.tmp-Live99") && counts.removed==1);
  linux_reader_close(reader);
  puts("PASS next_startup_after_release_removes_the_remaining_stage");
  return 0;
}
