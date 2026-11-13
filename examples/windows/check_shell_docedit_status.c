/* SPDX-License-Identifier: MIT */
/* gcc -std=c11 -Wall -Wextra -Werror -Iinclude
     examples/windows/check_shell_docedit_status.c -o <temp>/check-status.exe */
#include <exr/edit.h>
#include <assert.h>
#include <stdio.h>
#include <string.h>
#define DE_STATUS_COUNTS_ONLY
#include "shell_docedit_status.inc"

int main(void) {
  exr_edit_run run={0};exr_edit_block block={0};
  block.kind=EXR_EDIT_PARAGRAPH;block.runs=&run;block.run_count=1;
  de_status_counts before={0},after={0};de_status_count_block(&block,&before);
  run.text="\xe7\x94\xb2\xe4\xb9\x99\xe4\xb8\x99\xe4\xb8\x81\xe6\x88\x8a"
    "\xe5\xb7\xb1\xe5\xba\x9a\xe8\xbe\x9b\xe5\xa3\xac\xe7\x99\xb8";
  run.text_size=strlen(run.text);de_status_count_block(&block,&after);
  assert(after.words-before.words==10 && after.characters-before.characters==10);
  printf("PASS ten Chinese scalars: words +%zu, characters +%zu\n",
    after.words-before.words,after.characters-before.characters);
  run.text="A\xf0\x9f\x99\x82\xe4\xb8\xad \t\xe3\x80\x80";
  run.text_size=strlen(run.text);after=(de_status_counts){0};
  de_status_count_block(&block,&after);
  assert(after.words==3 && after.characters==6 && after.paragraphs==1);
  puts("PASS Latin/Chinese/emoji and Unicode whitespace: words=3 characters=6 paragraphs=1");
  exr_edit_cell cell={0};cell.blocks=&block;cell.block_count=1;
  exr_edit_row row={0};row.cells=&cell;row.cell_count=1;
  exr_edit_table table={0};table.rows=&row;table.row_count=1;
  exr_edit_block outer={0};outer.kind=EXR_EDIT_TABLE;outer.table=&table;
  after=(de_status_counts){0};de_status_count_block(&outer,&after);
  assert(after.words==3 && after.characters==6 && after.paragraphs==1);
  puts("PASS table cell text included once");
  run.kind=EXR_EDIT_OPAQUE_RUN;after=(de_status_counts){0};
  de_status_count_block(&outer,&after);
  assert(!after.words && !after.characters && after.paragraphs==1);
  puts("PASS opaque XML excluded; empty paragraph retained");
  /* Woman technologist = three code points; e + combining acute = two. */
  run.kind=EXR_EDIT_TEXT;
  run.text="\xf0\x9f\x91\xa9\xe2\x80\x8d\xf0\x9f\x92\xbb"
    "e\xcc\x81";
  run.text_size=strlen(run.text);after=(de_status_counts){0};
  de_status_count_block(&block,&after);
  assert(after.words==5 && after.characters==5);
  puts("PASS joined emoji and combining mark counted as five code points");
  exr_edit_run split[2]={run,run};
  block.runs=split;block.run_count=2;after=(de_status_counts){0};
  de_status_count_block(&block,&after);
  assert(after.words==10 && after.characters==10 && after.paragraphs==1);
  puts("PASS formatting runs do not add characters or paragraphs");
  return 0;
}
