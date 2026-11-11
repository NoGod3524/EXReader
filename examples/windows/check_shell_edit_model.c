/* SPDX-License-Identifier: MIT */
/* One executable checks transaction granularity, exact paragraph bytes,
   Unicode boundaries, history branching and protected objects against #119. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <exreader.h>
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "shell_edit_model.inc"

static void equal(const edit_model *m,const char *expected) {
  assert(m->size==strlen(expected)); assert(!memcmp(m->text,expected,m->size+1));
}
static void write_text(const char *directory,const char *name,const edit_model *m) {
  char path[4096]; snprintf(path,sizeof(path),"%s/%s.utf8",directory,name);
  FILE *f=fopen(path,"wb"); assert(f); assert(fwrite(m->text,1,m->size,f)==m->size); assert(!fclose(f));
}
int main(int argc,char **argv) {
  assert(argc==2); edit_model m={0};
  assert(edit_seed(&m,"",0)==EXR_OK);
  for (size_t i=0;i<10;i++) assert(edit_replace(&m,m.size,m.size,"x",1,1)==EXR_OK);
  equal(&m,"xxxxxxxxxx"); assert(edit_history_move(&m,0)==EXR_OK); equal(&m,"");
  assert(!edit_dirty(&m)); assert(edit_history_move(&m,1)==EXR_OK); equal(&m,"xxxxxxxxxx");
  edit_model_free(&m);

  assert(edit_seed(&m,"",0)==EXR_OK);
  const char *chinese="\xe4\xbd\xa0\xe5\xa5\xbd\xe4\xb8\x96\xe7\x95\x8c";
  write_text(argv[1],"cjk-model-before",&m);
  assert(edit_replace(&m,0,0,chinese,strlen(chinese),0)==EXR_OK);
  equal(&m,chinese); assert(m.cursor==1 && !m.tx);
  write_text(argv[1],"cjk-model-result",&m);
  assert(edit_history_move(&m,0)==EXR_OK); equal(&m,"");
  write_text(argv[1],"cjk-model-one-undo",&m);
  assert(edit_history_move(&m,1)==EXR_OK); equal(&m,chinese);
  edit_model_free(&m);

  const char *baseline="Alpha\n\xe4\xbd\xa0\xe5\xa5\xbd\nOmega";
  assert(edit_seed(&m,baseline,strlen(baseline))==EXR_OK);
  write_text(argv[1],"undo-before",&m);
  char expected[2048]; strcpy(expected,baseline);
  for (int i=0;i<20;i++) {
    char token[32]; snprintf(token,sizeof(token)," [%02d]",i); strcat(expected,token);
    assert(edit_replace(&m,m.size,m.size,token,strlen(token),0)==EXR_OK);
  }
  equal(&m,expected); write_text(argv[1],"redo-before",&m);
  for (int i=0;i<20;i++) assert(edit_history_move(&m,0)==EXR_OK);
  equal(&m,baseline); write_text(argv[1],"undo-after",&m); assert(!edit_dirty(&m));
  for (int i=0;i<20;i++) assert(edit_history_move(&m,1)==EXR_OK);
  equal(&m,expected); write_text(argv[1],"redo-after",&m);
  assert(edit_history_move(&m,0)==EXR_OK);
  assert(edit_replace(&m,m.size,m.size,"!",1,0)==EXR_OK);
  assert(edit_history_move(&m,1)==EXR_ARGUMENT);
  edit_model_free(&m);

  assert(edit_seed(&m,"ab\ncd\nef",8)==EXR_OK);
  assert(edit_replace(&m,1,7,"X\n\nY",4,0)==EXR_OK); equal(&m,"aX\n\nYf");
  assert(m.count==3); assert(edit_history_move(&m,0)==EXR_OK); equal(&m,"ab\ncd\nef");
  m.selection=(edit_selection){2,2}; assert(edit_enter(&m)==EXR_OK); equal(&m,"ab\n\ncd\nef");
  assert(edit_history_move(&m,0)==EXR_OK); equal(&m,"ab\ncd\nef");
  m.selection=(edit_selection){1,7}; assert(edit_enter(&m)==EXR_OK); equal(&m,"a\nf");
  assert(edit_history_move(&m,0)==EXR_OK); equal(&m,"ab\ncd\nef");
  edit_model_free(&m);

  const char *graphemes="A\xf0\x9f\x98\x80" "e\xcc\x81";
  assert(edit_seed(&m,graphemes,strlen(graphemes))==EXR_OK);
  assert(edit_boundary(&m,m.size,0)==5); assert(edit_boundary(&m,5,0)==1);
  assert(edit_replace(&m,5,m.size,"",0,0)==EXR_OK); equal(&m,"A\xf0\x9f\x98\x80");
  assert(edit_replace(&m,2,3,"?",1,0)==EXR_UNSUPPORTED);
  assert(edit_history_move(&m,0)==EXR_OK); equal(&m,graphemes);
  for (int i=0;i<120;i++) assert(edit_replace(&m,m.size,m.size,"x",1,0)==EXR_OK);
  for (int i=0;i<100;i++) assert(edit_history_move(&m,0)==EXR_OK);
  assert(edit_history_move(&m,0)==EXR_ARGUMENT);
  for (int i=0;i<100;i++) assert(edit_history_move(&m,1)==EXR_OK);
  edit_model_free(&m);

  assert(edit_seed(&m,"\xcc\x81Z",3)==EXR_OK);
  assert(edit_replace(&m,0,0,"e",1,0)==EXR_OK); equal(&m,"e\xcc\x81Z");
  assert(m.selection.focus==3 && m.selection.anchor==3);
  assert(edit_replace(&m,3,3,"!",1,0)==EXR_OK); equal(&m,"e\xcc\x81!Z");
  assert(edit_history_move(&m,0)==EXR_OK); equal(&m,"e\xcc\x81Z");
  assert(edit_history_move(&m,0)==EXR_OK); equal(&m,"\xcc\x81Z");
  edit_model_free(&m);

  exr_edit_run runs[3]={{0}}; runs[0].text="ab"; runs[0].text_size=2;
  runs[0].props.present=EXR_EDIT_BOLD; runs[0].props.bold=1;
  runs[1].kind=EXR_EDIT_OPAQUE_RUN; runs[1].opaque_xml="<drawing/>"; runs[1].opaque_size=10;
  runs[2].text="cd"; runs[2].text_size=2;
  exr_edit_block block={0}; block.runs=runs; block.run_count=3;
  assert(exr_edit_doc_create(NULL,0,&block,1,NULL,0,NULL,&m.doc)==EXR_OK);
  assert(edit_refresh(&m)==EXR_OK); assert(edit_mark_saved(&m));
  assert(edit_replace(&m,1,1,"Z",1,0)==EXR_OK); equal(&m,"aZb\xef\xbf\xbc" "cd");
  const exr_edit_block *changed=exr_edit_block_at(m.doc,0);
  assert(changed->runs[0].props.bold && changed->runs[1].props.bold);
  assert(edit_replace(&m,0,m.size,"",0,0)==EXR_UNSUPPORTED);
  assert(edit_history_move(&m,0)==EXR_OK); equal(&m,"ab\xef\xbf\xbc" "cd");
  edit_model_free(&m);
  assert(edit_seed(&m,"one\ntwo",7)==EXR_OK);
  size_t section_count=0;
  const exr_edit_section *original=exr_edit_sections(m.doc,&section_count); assert(section_count==1);
  exr_edit_section sections[2]={original[0],original[0]}; sections[1].id=99;
  exr_edit_block blocks[2]={*exr_edit_block_at(m.doc,0),*exr_edit_block_at(m.doc,1)};
  blocks[1].section_id=99; exr_edit_doc *multi=NULL;
  assert(exr_edit_doc_create(sections,2,blocks,2,NULL,0,NULL,&multi)==EXR_OK);
  edit_model_free(&m); m.doc=multi; assert(edit_refresh(&m)==EXR_OK); assert(edit_mark_saved(&m));
  assert(edit_replace(&m,5,5,"X",1,0)==EXR_OK); equal(&m,"one\ntXwo");
  assert(exr_edit_block_at(m.doc,1)->section_id==99);
  assert(edit_history_move(&m,0)==EXR_OK); equal(&m,"one\ntwo");
  assert(edit_history_move(&m,1)==EXR_OK); assert(exr_edit_block_at(m.doc,1)->section_id==99);
  edit_model_free(&m);
  puts("PASS: burst undo; single CJK result; 20 undo/redo; paragraph replacement/split; graphemes/joined caret; branch/depth; protected opaque runs; section inheritance");
  return 0;
}
