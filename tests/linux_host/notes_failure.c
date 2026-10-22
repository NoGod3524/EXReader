/* SPDX-License-Identifier: MIT */
#include <gtk/gtk.h>
#include <exreader.h>
#include <stdio.h>
#include <stdlib.h>
static int fail_reads;
static exr_status query_notes(exr_library *l,int64_t id,exr_note **out,size_t *count,exr_error *error) {
  if(fail_reads) { *out=NULL;*count=0;error->code=EXR_DATABASE;return EXR_DATABASE; }
  return exr_library_notes(l,id,out,count,error);
}
#define exr_library_notes query_notes
#define main exreader_host_main
#include "../../examples/linux/reader.c"
#undef main
#undef exr_library_notes
static unsigned checks;
static void require(int condition,const char *name) {
  if(!condition) { fprintf(stderr,"FAIL %s\n",name);exit(1); } checks++;
}
static unsigned rows(void) {
  GList *children=gtk_container_get_children(GTK_CONTAINER(notes));unsigned n=g_list_length(children);
  g_list_free(children);return n;
}
int main(int argc,char **argv) {
  if(argc!=3) return 2;
  gtk_init(NULL,NULL);home=g_strdup(argv[2]);g_mkdir_with_parents(home,0700);
  settings_path=g_build_filename(home,"reader.ini",NULL);settings=g_key_file_new();
  char *db=g_build_filename(home,"library.sqlite",NULL);exr_error error={0};
  require(exr_library_open(db,&library,&error)==EXR_OK,"open real library");g_free(db);
  require(exr_font_open(argv[1],&font,&error)==EXR_OK,"open real font");
  window=gtk_window_new(GTK_WINDOW_TOPLEVEL);label=gtk_label_new("");image=gtk_image_new();
  text=gtk_text_view_new();comment=gtk_entry_new();notes=gtk_list_box_new();stack=gtk_stack_new();
  gtk_stack_add_named(GTK_STACK(stack),gtk_label_new("reader"),"reader");
  const char *body="Reader note body with stable original bytes.";
  int64_t first=0,second=0,note_id=0;
  require(exr_library_import(library,EXR_TXT,body,strlen(body),"Original",&first,&error)==EXR_OK,"import original");
  require(exr_library_import(library,EXR_TXT,body,strlen(body),"Candidate",&second,&error)==EXR_OK,"import candidate");
  exr_note note={0};note.book_id=first;note.start=0;note.end=6;note.text="existing";
  require(exr_library_note(library,&note,&note_id,&error)==EXR_OK,"persist existing note");
  open_id(first);require(book_id==first&&note_count==1&&rows()==1&&last_error==0,"show original book and note");
  exr_document *old_document=document;exr_pager *old_pager=pager;size_t old_start=page_start,old_end=page_end;
  GdkPixbuf *old_pixels=gtk_image_get_pixbuf(GTK_IMAGE(image));
  fail_reads=1;
  require(!refresh_notes(first)&&last_error==EXR_DATABASE&&note_count==1&&rows()==1,"failed query retains existing notes and error");
  open_id(second);
  require(book_id==first&&document==old_document&&pager==old_pager&&page_start==old_start&&page_end==old_end&&
    gtk_image_get_pixbuf(GTK_IMAGE(image))==old_pixels&&last_error==EXR_DATABASE&&note_count==1&&rows()==1,
    "candidate note failure retains original document pager pixels and notes");
  GtkTextBuffer *buffer=gtk_text_view_get_buffer(GTK_TEXT_VIEW(text));GtkTextIter a,b;
  gtk_text_buffer_get_iter_at_offset(buffer,&a,0);gtk_text_buffer_get_iter_at_offset(buffer,&b,6);
  gtk_text_buffer_select_range(buffer,&a,&b);gtk_entry_set_text(GTK_ENTRY(comment),"added during refresh failure");
  add_note();require(last_error==EXR_DATABASE&&note_count==1&&rows()==1,"add does not mask refresh failure");
  exr_note *actual=NULL;size_t count=0;
  require(exr_library_notes(library,first,&actual,&count,&error)==EXR_OK&&count==2,"both notes remain persisted after add");
  exr_notes_free(actual,count);
  gtk_list_box_select_row(GTK_LIST_BOX(notes),gtk_list_box_get_row_at_index(GTK_LIST_BOX(notes),0));
  delete_note();require(last_error==EXR_DATABASE&&note_count==1&&rows()==1,"delete does not mask refresh failure");
  require(exr_library_notes(library,first,&actual,&count,&error)==EXR_OK&&count==1&&
    !strcmp(actual[0].text,"added during refresh failure"),"only selected note was removed");
  exr_notes_free(actual,count);fail_reads=0;
  require(refresh_notes(first)&&note_count==1&&rows()==1,"recover notes after query succeeds");
  exr_pager_free(pager);exr_document_free(document);exr_font_free(font);exr_library_close(library);
  g_key_file_free(settings);g_free(settings_path);g_free(home);
  printf("{\"passed\":true,\"checks\":%u,\"kind\":\"GTK note query fault regression\"}\n",checks);return 0;
}
