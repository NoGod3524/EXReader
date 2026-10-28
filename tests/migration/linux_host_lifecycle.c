/* SPDX-License-Identifier: MIT */
#include "../../examples/linux/reading.h"
#include <stdio.h>
#include <stdlib.h>
int main(int argc,char **argv) {
  linux_reader *reader=NULL;
  exr_error error={0};
  reader_command command={0};
  reader_result result={0};
  int expected;
  if(argc!=4) return 2;
  expected=atoi(argv[3]);
  if(linux_reader_open(argv[1],argv[2],NULL,&reader,&error)!=EXR_OK) {
    fprintf(stderr,"reader open: %s\n",error.message);return 1;
  }
  command.action=READER_SHELF;command.font=24;command.zoom=100;
  linux_reader_execute(reader,&command,&result);
  if(result.status!=EXR_OK || !result.has_shelf || result.book_count!=(size_t)expected) {
    fprintf(stderr,"shelf status=%d count=%zu expected=%d\n",(int)result.status,result.book_count,expected);
    reader_result_free(&result);linux_reader_close(reader);return 1;
  }
  printf("real GTK reader owner observed %zu books, then closed\n",result.book_count);
  reader_result_free(&result);linux_reader_close(reader);return 0;
}
