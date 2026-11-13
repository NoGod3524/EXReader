/* SPDX-License-Identifier: MIT */
/* Console-only checks of the real shell selection and engine transaction. */
#define main docedit_existing_acceptance_main
#include "check_shell_docedit.c"
#undef main
#include "shell_docedit_find.inc"

static void find_seed(const char *text) {
  de_close();memset(&de,0,sizeof(de));
  exr_edit_run run={0};run.text=text;run.text_size=strlen(text);
  exr_edit_block block={0};block.runs=&run;block.run_count=1;
  assert(exr_edit_doc_create(NULL,0,&block,1,NULL,0,NULL,&de.doc)==EXR_OK);
  reset_caret();
}
int main(void) {
  find_seed("abc abc abc");
  for(size_t i=0;i<4;i++) {
    assert(de_find_next("abc",0));
    assert(de.sel_anchor_byte==(i%3)*4 && de.caret_byte==(i%3)*4+3 && de_selected());
  }
  assert(de_find_next("abc",1));
  assert(de.sel_anchor_byte==8 && de.caret_byte==11);
  puts("PASS find: 3 selected hits, forward/backward wrap");
  assert(de_find_replace("abc","XYZ",1));same_text("\n[block]XYZ XYZ XYZ");
  assert(de_key('Z',1,0));same_text("\n[block]abc abc abc");
  assert(de_key('Y',1,0));same_text("\n[block]XYZ XYZ XYZ");
  puts("PASS replace all: 3 replacements, one Ctrl+Z restores all, Ctrl+Y reapplies");
  find_seed("ababa");
  assert(de_find_next("aba",0));assert(de.sel_anchor_byte==0);
  assert(de_find_next("aba",0));assert(de.sel_anchor_byte==2);
  assert(de_find_replace("aba","X",1));same_text("\n[block]Xba");
  assert(de_key('Z',1,0));same_text("\n[block]ababa");
  puts("PASS overlapping navigation and non-overlapping replace all");
  find_seed("abc abc");
  assert(de_find_next("abc",0));assert(de_find_replace("abc","",0));
  same_text("\n[block] abc");assert(de_key('Z',1,0));same_text("\n[block]abc abc");
  assert(!de_find_replace("missing","X",1));
  assert(!de_find_next("",0));
  puts("PASS replace current, empty replacement, missing/empty query");
  de_close();memset(&de,0,sizeof(de));
  exr_edit_run runs[3]={{0}};
  runs[0].text="a";runs[0].text_size=1;runs[0].props.present=EXR_EDIT_BOLD;runs[0].props.bold=1;
  runs[1].text="b";runs[1].text_size=1;runs[2].text="c abc";runs[2].text_size=5;
  exr_edit_block block={0};block.runs=runs;block.run_count=3;
  assert(exr_edit_doc_create(NULL,0,&block,1,NULL,0,NULL,&de.doc)==EXR_OK);reset_caret();
  assert(de_find_next("abc",0));assert(de.caret_run==2 && de.caret_byte==1);
  assert(!de_find_replace("abc","\xff",0));same_text("\n[block]abc abc");assert(!de.dirty);
  assert(de_find_replace("abc","XYZ",1));same_text("\n[block]XYZ XYZ");
  assert(exr_edit_block_at(de.doc,0)->runs[0].props.bold);
  assert(de_key('Z',1,0));same_text("\n[block]abc abc");
  puts("PASS cross-run replace, style retention, failure rollback");
  find_seed("\xe4\xb8\xad\xf0\x9f\x99\x82 \xe4\xb8\xad\xf0\x9f\x99\x82");
  assert(de_find_next("\xf0\x9f\x99\x82",0));assert(de.sel_anchor_byte==3 && de.caret_byte==7);
  assert(de_find_replace("\xf0\x9f\x99\x82","X",1));same_text("\n[block]\xe4\xb8\xadX \xe4\xb8\xadX");
  assert(de_key('Z',1,0));
  puts("PASS UTF-8 Chinese/emoji search and replace");
  de_close();return 0;
}
