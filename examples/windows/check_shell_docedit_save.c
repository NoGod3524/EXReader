/* SPDX-License-Identifier: MIT */
/* Console acceptance: no HWND, input injection or GUI automation. */
#define main docedit_existing_acceptance_main
#include "check_shell_docedit.c"
#undef main

int main(int argc,char **argv) {
  assert(argc==3);setvbuf(stdout,NULL,_IONBF,0);
  SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);
  wchar_t *directory=host_wide(argv[2],strlen(argv[2]));assert(directory);
  ensure_directory(directory);copy_wstring(g.data_dir,HOST_PATH,directory);
  path_join(shelf_json_path,HOST_PATH,directory,L"recent-books.json");free(directory);
  /* Set up the same recent-book data used by a real open document. */
  g.has_current=1;g.current.id=7;shelf_loaded=1;shelf_count=1;
  shelf_book *book=&shelf_recent[0];book->id=7;
  book->path=host_strdup(argv[1]);book->title=host_strdup("L11");book->author=host_strdup("");
  book->cover=calloc(1,4);assert(book->cover); /* No cover decode/library needed. */
  exr_error error={0};assert(exr_edit_docx_open(argv[1],NULL,&de.doc,&error)==EXR_OK);
  strcpy(de.path,argv[1]);
  exr_edit_run run={0};run.text="L11 中文 save-as";run.text_size=strlen(run.text);
  exr_edit_id id;assert(exr_edit_insert_paragraph(de.doc,0,&run,1,NULL,&id)==EXR_OK);
  de.dirty=1;
  char target[MAX_PATH];snprintf(target,sizeof(target),"%s/new document \xe4\xb8\xad\xe6\x96\x87.docx",argv[2]);
  char *expected=model_text(de.doc);
  assert(de_save_as(target));assert(!de.dirty && de.saved);
  file_text_equal(de.path,expected);free(expected);
  assert(!strcmp(book->path,de.path) && book->opened>0);
  assert(GetFileAttributesW(shelf_json_path)!=INVALID_FILE_ATTRIBUTES);
  puts("PASS Save As new path: exr_edit_docx_open text_equal=1 dirty=0 recent_path=updated recent_json=written");
  assert(exr_edit_set_run_text(de.doc,id,0,"Ctrl+S",6)==EXR_OK);de.dirty=1;
  assert(de_key('S',1,0) && !de.dirty);
  expected=model_text(de.doc);file_text_equal(de.path,expected);free(expected);
  puts("PASS Ctrl+S: overwrites Save As destination text_equal=1 dirty=0");
  char saved[MAX_PATH];strcpy(saved,de.path);
  expected=model_text(de.doc);
  wchar_t *wide=host_wide(saved,strlen(saved));assert(wide);
  assert(SetFileAttributesW(wide,FILE_ATTRIBUTE_READONLY));
  assert(exr_edit_set_run_text(de.doc,id,0,"unsaved",7)==EXR_OK);de.dirty=1;
  assert(!de_save() && de.dirty==1 && de_save_error==ERROR_ACCESS_DENIED);
  assert(wcsstr(g.status_text,L"5") && wcsstr(g.status_text,L"修改仍保留"));
  wchar_t reason[512];
  assert(FormatMessageW(FORMAT_MESSAGE_FROM_SYSTEM|FORMAT_MESSAGE_IGNORE_INSERTS,
    NULL,ERROR_ACCESS_DENIED,0,reason,512,NULL));
  assert(wcsstr(g.status_text,reason));
  assert(!strcmp(de.path,saved));
  file_text_equal(saved,expected);free(expected);
  assert(!de_save_as(saved) && de.dirty==1 && de_save_error==ERROR_ACCESS_DENIED);
  assert(!strcmp(book->path,saved));
  puts("PASS read-only Save As: dirty=1 reason_shown=1 recent_path_unchanged=1");
  assert(SetFileAttributesW(wide,FILE_ATTRIBUTE_NORMAL));free(wide);
  printf("PASS read-only save: dirty=%d error=%lu reason_shown=1 path_unchanged=1\n",de.dirty,(unsigned long)de_save_error);
  char missing[MAX_PATH];snprintf(missing,sizeof(missing),"%s/missing/no.docx",argv[2]);
  assert(!de_save_as(missing) && de.dirty==1 && de_save_error);
  assert(!strcmp(saved,de.path) && !strcmp(book->path,saved));
  puts("PASS failed Save As: dirty=1 active_path_unchanged=1 recent_path_unchanged=1");
  assert(de_key('S',1,1) && de.dirty==1); /* Headless dialog path: requires injection. */
  assert(wcsstr(g.status_text,L"另存为需要目标路径"));
  assert(!de_save_as("") && de.dirty==1);
  assert(de_save());
  exr_edit_doc_free(de.doc);de.doc=NULL;shelf_destroy();
  puts("L11 console acceptance PASS (no HWND / no SendInput)");return 0;
}
