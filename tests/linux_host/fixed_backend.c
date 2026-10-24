/* SPDX-License-Identifier: MIT */
#include "../../examples/linux/reading.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks,groups;
static int stopped;
static int cancelled(void *unused) { (void)unused;return stopped; }
#define CHECK(x) do { checks++;if(!(x)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x);exit(1); } } while(0)
static void passed(const char *name) { groups++;printf("PASS %s\n",name); }
static void run(linux_reader *reader,reader_command *command,reader_result *result,exr_status expected,int commit) {
  reader_result_free(result);linux_reader_execute(reader,command,result);CHECK(result->status==expected);
  if(expected!=EXR_OK) CHECK(!result->has_frame);
  if(result->has_frame && commit) {
    reader_command accepted={0};reader_result saved={0};
    accepted.action=READER_COMMIT;accepted.book=result->book;accepted.part=result->part;
    accepted.start=result->start;accepted.page=result->page;
    linux_reader_execute(reader,&accepted,&saved);CHECK(saved.status==EXR_OK);reader_result_free(&saved);
    command->page=result->page;
  }
}
int main(int argc,char **argv) {
  if(argc!=4) return 2;
  linux_reader *reader=NULL;reader_command command={0};reader_result result={0};exr_error error={0};
  exr_control control={cancelled,NULL,NULL};char path[4096];int64_t pdf_id,note_id,cbz_id;
  CHECK(linux_reader_open(argv[1],argv[2],&control,&reader,&error)==EXR_OK);
  snprintf(path,sizeof(path),"%s/Pages.pdf",argv[3]);command.action=READER_IMPORT;command.path=path;
  command.font=24;command.zoom=100;run(reader,&command,&result,EXR_OK,1);pdf_id=result.book;command.book=pdf_id;
  CHECK(result.fixed && result.page_count==3 && result.page==0 && result.width==600 && result.height==800);
  CHECK(strstr(result.text,"Fixed page 1.") && result.text_size>40 && result.start==0);passed("pdf_public_source_render_and_text");
  run(reader,&command,&result,EXR_OK,1);CHECK(result.book==pdf_id && result.book_count==1);passed("pdf_exact_duplicate");
  command.action=READER_PREVIOUS;run(reader,&command,&result,EXR_ARGUMENT,0);
  command.action=READER_NOTE_ADD;command.start=0;command.end=12;command.comment="Fixed note";
  run(reader,&command,&result,EXR_OK,1);CHECK(result.note_count==1);note_id=result.notes[0].id;
  command.action=READER_NEXT;run(reader,&command,&result,EXR_OK,1);CHECK(result.page==1 && strstr(result.text,"Fixed page 2."));
  command.action=READER_NOTE_JUMP;command.note=note_id;run(reader,&command,&result,EXR_OK,1);
  CHECK(result.page==0 && result.select_range && result.selected_start==0 && result.selected_end==12);
  passed("page_local_note_capture_and_unique_jump");
  command.action=READER_NEXT;run(reader,&command,&result,EXR_OK,0);CHECK(result.page==1);
  reader_command stale={0};reader_result save={0};stale.action=READER_COMMIT;stale.book=pdf_id;
  linux_reader_execute(reader,&stale,&save);CHECK(save.status==EXR_ARGUMENT);reader_result_free(&save);
  stale.page=1;linux_reader_execute(reader,&stale,&save);CHECK(save.status==EXR_OK);reader_result_free(&save);command.page=1;
  command.page=0;command.action=READER_NOTE_ADD;run(reader,&command,&result,EXR_ARGUMENT,0);command.page=1;
  passed("stale_fixed_page_commit_and_note_refused");
  command.action=READER_ZOOM;command.zoom=150;run(reader,&command,&result,EXR_OK,1);
  CHECK(result.width==900 && result.height==1200 && result.page==1 && result.font==24);
  command.zoom=400;run(reader,&command,&result,EXR_LIMIT,0);
  command.zoom=24;run(reader,&command,&result,EXR_ARGUMENT,0);
  command.action=READER_FONT;run(reader,&command,&result,EXR_ARGUMENT,0);passed("zoom_and_font_refusal_keep_fixed_session");
  stopped=1;command.action=READER_NEXT;run(reader,&command,&result,EXR_CANCELLED,0);stopped=0;
  command.action=READER_NEXT;run(reader,&command,&result,EXR_OK,1);CHECK(result.page==2 && result.zoom==150);
  run(reader,&command,&result,EXR_ARGUMENT,0);passed("cancel_and_last_page_boundary");
  reader_result_free(&result);linux_reader_close(reader);reader=NULL;
  CHECK(linux_reader_open(argv[1],argv[2],&control,&reader,&error)==EXR_OK);
  command.action=READER_OPEN;command.zoom=150;run(reader,&command,&result,EXR_OK,1);
  CHECK(result.page==2 && result.position==2 && result.note_count==1);passed("reopen_restores_fixed_page_and_note");
  command.action=READER_NOTE_REMOVE;command.note=note_id;run(reader,&command,&result,EXR_OK,1);CHECK(!result.note_count);
  command.action=READER_IMPORT;snprintf(path,sizeof(path),"%s/Rotated.pdf",argv[3]);command.zoom=100;
  run(reader,&command,&result,EXR_OK,1);CHECK(result.width==800 && result.height==600);passed("rotated_page_geometry");
  command.book=result.book;command.action=READER_IMPORT;snprintf(path,sizeof(path),"%s/Repeated.pdf",argv[3]);
  run(reader,&command,&result,EXR_OK,1);command.book=result.book;
  const char *target=strstr(result.text,"selection target");CHECK(target && target-result.text>32);
  command.start=(size_t)(target-result.text);command.end=command.start+16;command.action=READER_NOTE_ADD;
  run(reader,&command,&result,EXR_OK,1);CHECK(result.note_count==1);command.note=result.notes[0].id;
  command.action=READER_NEXT;run(reader,&command,&result,EXR_OK,1);CHECK(result.page==1);
  command.action=READER_NOTE_JUMP;run(reader,&command,&result,EXR_ARGUMENT,0);
  CHECK(strstr(result.message,"ambiguous"));command.action=READER_PREVIOUS;
  run(reader,&command,&result,EXR_OK,1);CHECK(result.page==0);passed("repeated_quote_refuses_guessed_note_location");
  snprintf(path,sizeof(path),"%s/Pages.cbz",argv[3]);command.action=READER_IMPORT;
  run(reader,&command,&result,EXR_OK,1);command.book=result.book;cbz_id=result.book;
  CHECK(result.fixed && result.page_count==3 && !result.text_size && result.width==600 && result.height==800);
  command.action=READER_NOTE_ADD;command.start=0;command.end=1;run(reader,&command,&result,EXR_ARGUMENT,0);
  command.action=READER_NEXT;run(reader,&command,&result,EXR_OK,1);CHECK(result.page==1);
  command.action=READER_IMPORT;run(reader,&command,&result,EXR_OK,1);CHECK(result.book==cbz_id && result.page==1);
  passed("cbz_streaming_pages_duplicate_and_no_fake_text_note");
  command.action=READER_IMPORT;snprintf(path,sizeof(path),"%s/Too-large.pdf",argv[3]);run(reader,&command,&result,EXR_LIMIT,0);
  snprintf(path,sizeof(path),"%s/Broken.pdf",argv[3]);run(reader,&command,&result,EXR_FORMAT,0);
  command.action=READER_NEXT;run(reader,&command,&result,EXR_OK,1);CHECK(result.book==cbz_id && result.page==2);
  passed("bad_import_keeps_accepted_fixed_document_alive");
  reader_result_free(&result);linux_reader_close(reader);
  CHECK(groups==11);
  printf("{\"accepted\":true,\"checks\":%u,\"groups\":%u,\"source_sha\":\"%s\",\"run_id\":\"%s\",\"attempt\":\"%s\"}\n",
    checks,groups,getenv("GITHUB_SHA"),getenv("GITHUB_RUN_ID"),getenv("GITHUB_RUN_ATTEMPT"));
  return 0;
}
