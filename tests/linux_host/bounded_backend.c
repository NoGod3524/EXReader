/* SPDX-License-Identifier: MIT */
#include "../../examples/linux/reading.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks;
static int stop;
static int cancelled(void *unused) { (void)unused;return stop; }
#define CHECK(x) do { checks++;if(!(x)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x);exit(1); } } while(0)
static void execute(linux_reader *reader,reader_command *command,reader_result *result) {
  reader_result_free(result);linux_reader_execute(reader,command,result);
  CHECK(result->status==EXR_OK);
  if(result->has_frame) {
    command->part=result->part;
    reader_command accepted={0};reader_result saved={0};
    accepted.action=READER_COMMIT;accepted.book=result->book;accepted.part=result->part;accepted.start=result->start;
    linux_reader_execute(reader,&accepted,&saved);CHECK(saved.status==EXR_OK);reader_result_free(&saved);
  }
}
int main(int argc,char **argv) {
  linux_reader *reader=NULL;reader_result result={0};reader_command command={0};exr_error error={0};
  exr_control control={cancelled,NULL,NULL};int64_t book,note;size_t start,part,steps=0;
  if(argc!=4) return 2;
  CHECK(linux_reader_open(argv[1],argv[2],&control,&reader,&error)==EXR_OK);
  command.action=READER_IMPORT;command.path=argv[3];command.font=24;execute(reader,&command,&result);
  CHECK(result.has_frame && result.bounded && result.part==0 && result.page==0 && result.text_size>37);
  CHECK(result.chapter.explicit_snapshot_bytes==0 && result.width<=4096 && result.height<=4096);
  book=result.book;command.book=book;
  command.action=READER_NOTE_ADD;command.start=result.start+30;command.end=result.start+37;
  command.comment="Linux chapter annotation";execute(reader,&command,&result);
  CHECK(result.note_count==1 && result.notes[0].part==0);note=result.notes[0].id;
  command.action=READER_FONT;command.font=26;execute(reader,&command,&result);
  CHECK(result.has_frame && result.font==26 && result.part==0 && result.start==0);
  command.action=READER_NEXT;
  while(result.part<2 && steps++<100) execute(reader,&command,&result);
  CHECK(steps<100 && result.part==2 && result.start==0);
  command.action=READER_PREVIOUS;execute(reader,&command,&result);
  CHECK(result.part==1 && result.page>0);
  command.action=READER_NOTE_JUMP;command.note=note;execute(reader,&command,&result);
  CHECK(result.has_frame && result.part==0 && result.page==0 && result.select_range);
  CHECK(result.selected_start==30 && result.selected_end==37 && result.position==30 && result.note_count==1);
  command.action=READER_FONT;command.font=28;execute(reader,&command,&result);
  CHECK(result.position==30 && result.start==0);
  reader_result_free(&result);linux_reader_close(reader);reader=NULL;
  CHECK(linux_reader_open(argv[1],argv[2],&control,&reader,&error)==EXR_OK);
  command.action=READER_OPEN;execute(reader,&command,&result);
  CHECK(result.position==30 && result.start==0 && result.note_count==1);
  command.action=READER_NEXT;execute(reader,&command,&result);start=result.start;part=result.part;
  CHECK(start>0);
  reader_result_free(&result);linux_reader_close(reader);reader=NULL;
  CHECK(linux_reader_open(argv[1],argv[2],&control,&reader,&error)==EXR_OK);
  command.action=READER_OPEN;execute(reader,&command,&result);
  CHECK(result.part==part && result.start==start && result.note_count==1);
  stop=1;command.action=READER_NEXT;reader_result_free(&result);linux_reader_execute(reader,&command,&result);
  CHECK(result.status==EXR_CANCELLED && !result.has_frame);stop=0;
  command.action=READER_OPEN;execute(reader,&command,&result);CHECK(result.start==start);
  command.action=READER_NOTE_REMOVE;command.note=note;execute(reader,&command,&result);CHECK(result.note_count==0);
  reader_result_free(&result);linux_reader_close(reader);
  printf("{\"backend_passed\":true,\"checks\":%u,\"scope\":\"installed SDK Linux reading backend only\"}\n",checks);
  return 0;
}
