/* SPDX-License-Identifier: MIT */
#define _POSIX_C_SOURCE 200809L
#include <exreader.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static const char *mutable_path;
static int stop,late_cancel,cancel_on,calls,opens;
static unsigned checks;
#define CHECK(x) do { checks++;if(!(x)) { fprintf(stderr,"FAIL %d %s\n",__LINE__,#x);exit(1); } } while(0)
static int cancelled(void *unused) {
  (void)unused;calls++;return stop || (cancel_on && calls>=cancel_on);
}
static exr_status consume_snapshot(exr_library *library,exr_format format,const char *path,const char *title,
                                   int64_t *id,int *created,exr_error *error) {
  CHECK(!strncmp(path,"/proc/self/fd/",14));opens++;
  FILE *original=fopen(mutable_path,"wb");CHECK(original);
  CHECK(fwrite("changed after snapshot",1,22,original)==22);CHECK(!fclose(original));
  exr_status status=exr_library_import_file_unique(library,format,path,title,id,created,error);
  if(late_cancel) stop=1;
  return status;
}
#define exr_library_import_file_unique consume_snapshot
#include "../../examples/linux/reading.c"
#undef exr_library_import_file_unique
static void copy_file(const char *from,const char *to) {
  FILE *input=fopen(from,"rb"),*output=fopen(to,"wb");CHECK(input && output);
  unsigned char buffer[65536];size_t size;
  while((size=fread(buffer,1,sizeof(buffer),input))) CHECK(fwrite(buffer,1,size,output)==size);
  CHECK(!ferror(input));CHECK(!fclose(input));CHECK(!fclose(output));
}
static size_t books(linux_reader *reader) {
  exr_book *all=NULL;size_t count=0;exr_error error={0};
  CHECK(exr_library_books(reader->library,"",&all,&count,&error)==EXR_OK);exr_books_free(all,count);return count;
}
int main(int argc,char **argv) {
  if(argc!=5) return 2;
  linux_reader *reader=NULL;exr_error error={0};reader_result result={0};reader_command command={0};
  exr_control control={cancelled,NULL,NULL};mutable_path=argv[4];
  CHECK(linux_reader_open(argv[1],argv[2],&control,&reader,&error)==EXR_OK);
  copy_file(argv[3],mutable_path);command.action=READER_IMPORT;command.path=mutable_path;command.font=24;command.zoom=100;
  linux_reader_execute(reader,&command,&result);CHECK(result.status==EXR_OK && result.fixed && result.has_frame);
  CHECK(strstr(result.text,"Fixed page 1.") && books(reader)==1 && opens==1);
  int64_t id=result.book;reader_result_free(&result);
  reader_command commit={0};commit.action=READER_COMMIT;commit.book=id;
  linux_reader_execute(reader,&commit,&result);CHECK(result.status==EXR_OK);reader_result_free(&result);
  /* Copy cancellation precedes the SDK file entry and cannot publish a book. */
  copy_file(argv[3],mutable_path);cancel_on=3;calls=0;
  linux_reader_execute(reader,&command,&result);CHECK(result.status==EXR_CANCELLED && !result.has_frame && opens==1);
  cancel_on=0;reader_result_free(&result);CHECK(books(reader)==1);
  /* A late cancelled duplicate must never compensate away the old book. */
  copy_file(argv[3],mutable_path);late_cancel=1;calls=0;
  linux_reader_execute(reader,&command,&result);CHECK(result.status==EXR_CANCELLED && !result.has_frame && opens==2);
  stop=late_cancel=0;reader_result_free(&result);CHECK(books(reader)==1);
  /* A distinct, valid original cancelled after commit is compensated once. */
  copy_file(argv[3],mutable_path);FILE *suffix=fopen(mutable_path,"ab");CHECK(suffix);
  CHECK(fwrite("\n% distinct original\n",1,21,suffix)==21);CHECK(!fclose(suffix));late_cancel=1;
  linux_reader_execute(reader,&command,&result);CHECK(result.status==EXR_CANCELLED && !result.has_frame && opens==3);
  stop=late_cancel=0;reader_result_free(&result);CHECK(books(reader)==1);
  command.action=READER_NEXT;command.book=id;
  linux_reader_execute(reader,&command,&result);CHECK(result.status==EXR_OK && result.page==1 && result.book==id);
  reader_result_free(&result);linux_reader_close(reader);
  printf("{\"accepted\":true,\"checks\":%u,\"scope\":\"private PDF snapshot and created-only cancellation\"}\n",checks);
  return 0;
}
