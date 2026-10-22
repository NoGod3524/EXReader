/* SPDX-License-Identifier: MIT */
#include <gtk/gtk.h>
#include <exreader.h>
#include <stdio.h>
#include <string.h>

/* ponytail: a small reflow reference host, with explicit 8 MiB snapshot input.
   Large EPUBs should use the separate publication/window reader consumer. */
#define EXR_HOST_INPUT_LIMIT (8u*1024u*1024u)
static GtkWidget *window,*image,*label,*shelf,*notes,*text,*comment,*stack;
static exr_library *library;
static exr_font *font;
static exr_document *document;
static exr_pager *pager;
static exr_book *books;
static size_t book_count,page_number,page_start,page_end,note_count,selection_start,selection_end;
static int64_t book_id;
static int font_size=24,last_error;
static guint sequence;
static char *home,*settings_path,*state_path;
static GKeyFile *settings;

static void state(void) {
  if(!state_path) return;
  GtkTextIter a,b;size_t selected=0;
  if(gtk_text_buffer_get_selection_bounds(gtk_text_view_get_buffer(GTK_TEXT_VIEW(text)),&a,&b))
    selected=(size_t)(gtk_text_iter_get_offset(&b)-gtk_text_iter_get_offset(&a));
  char *data=g_strdup_printf("[host]\nsequence=%u\nerror=%d\nbook=%"G_GINT64_FORMAT"\nbooks=%zu\npage=%zu\nstart=%zu\nend=%zu\nfont=%d\nnotes=%zu\nselected=%zu\nselection_start=%zu\nselection_end=%zu\nvisible=%d\nfocused=%d\n",
    ++sequence,last_error,book_id,book_count,page_number,page_start,page_end,font_size,note_count,selected,
    selection_start,selection_end,gtk_widget_get_visible(window),gtk_window_is_active(GTK_WINDOW(window)));
  g_file_set_contents(state_path,data,-1,NULL);g_free(data);
}
static void status(exr_status code,const char *message) {
  last_error=(int)code;gtk_label_set_text(GTK_LABEL(label),message);state();
}
static gboolean save_settings(void) {
  GError *error=NULL;
  g_key_file_set_int64(settings,"reader","book",book_id);
  g_key_file_set_integer(settings,"reader","font",font_size);
  if(!g_key_file_save_to_file(settings,settings_path,&error)) {
    status(EXR_IO,"Could not save reading settings");g_clear_error(&error);return FALSE;
  }
  return TRUE;
}
static gboolean save_progress(void) {
  if(!document || !book_id) return TRUE;
  exr_error error={0};exr_anchor anchor={0};
  exr_status s=exr_anchor_create(document,page_start,page_start,&anchor,&error);
  if(s==EXR_OK) s=exr_library_progress(library,book_id,&anchor,&error);
  exr_anchor_free(&anchor);
  if(s!=EXR_OK) { status(s,"Could not save reading position");return FALSE; }
  return save_settings();
}
static void rows_clear(GtkWidget *box) {
  GList *children=gtk_container_get_children(GTK_CONTAINER(box));
  for(GList *p=children;p;p=p->next) gtk_widget_destroy(GTK_WIDGET(p->data));
  g_list_free(children);
}
static void refresh_shelf(void) {
  exr_book *next=NULL;size_t count=0;exr_error error={0};
  exr_status s=exr_library_books(library,"",&next,&count,&error);
  if(s!=EXR_OK) { status(s,"Could not read bookshelf");return; }
  exr_books_free(books,book_count);books=next;book_count=count;rows_clear(shelf);
  for(size_t i=0;i<count;i++) {
    GtkWidget *row=gtk_list_box_row_new(),*title=gtk_label_new(books[i].title);
    int64_t *id=g_new(int64_t,1);*id=books[i].id;
    g_object_set_data_full(G_OBJECT(row),"book-id",id,g_free);
    gtk_container_add(GTK_CONTAINER(row),title);gtk_container_add(GTK_CONTAINER(shelf),row);
  }
  gtk_widget_show_all(shelf);
}
static void refresh_notes(void) {
  exr_note *entries=NULL;size_t count=0;exr_error error={0};rows_clear(notes);note_count=0;
  if(!book_id) return;
  exr_status s=exr_library_notes(library,book_id,&entries,&count,&error);
  if(s!=EXR_OK) { status(s,"Could not read notes");return; }
  note_count=count;
  for(size_t i=0;i<count;i++) {
    GtkWidget *row=gtk_list_box_row_new(),*title=gtk_label_new(entries[i].text);
    exr_note *copy=g_new0(exr_note,1);copy->id=entries[i].id;copy->start=entries[i].start;copy->end=entries[i].end;
    g_object_set_data_full(G_OBJECT(row),"note",copy,g_free);
    gtk_label_set_ellipsize(GTK_LABEL(title),PANGO_ELLIPSIZE_END);
    gtk_container_add(GTK_CONTAINER(row),title);gtk_container_add(GTK_CONTAINER(notes),row);
  }
  exr_notes_free(entries,count);gtk_widget_show_all(notes);
}
static exr_status frame(exr_pager *p,exr_document *doc,size_t index,gboolean seek,size_t position,
                        GdkPixbuf **pixels,const exr_page **out,size_t *found) {
  exr_error error={0};const exr_layout *layout=NULL;exr_status s;
  size_t size;exr_document_text(doc,&size);
  for(size_t i=index;i<20000;i++) {
    s=exr_pager_get(p,i,&layout,&error);if(s!=EXR_OK) return s;
    const exr_page *pg=exr_layout_pages(layout,NULL);
    if(!pg || pg->start>pg->end || pg->end>size) return EXR_FORMAT;
    if(seek && pg->end<=position && pg->end<size) continue;
    exr_bitmap bitmap={0};s=exr_render_page_color(layout,exr_layout_font(layout),0,&bitmap,&error);
    if(s!=EXR_OK) return s;
    if(bitmap.channels!=4 || bitmap.width>4096 || bitmap.height>4096) { exr_bitmap_free(&bitmap);return EXR_FORMAT; }
    *pixels=gdk_pixbuf_new(GDK_COLORSPACE_RGB,TRUE,8,(int)bitmap.width,(int)bitmap.height);
    if(!*pixels) { exr_bitmap_free(&bitmap);return EXR_MEMORY; }
    for(unsigned y=0;y<bitmap.height;y++)
      memcpy(gdk_pixbuf_get_pixels(*pixels)+(size_t)y*gdk_pixbuf_get_rowstride(*pixels),
             bitmap.pixels+(size_t)y*bitmap.stride,(size_t)bitmap.width*4);
    exr_bitmap_free(&bitmap);*out=pg;*found=i;return EXR_OK;
  }
  return EXR_LIMIT;
}
static void present(GdkPixbuf *pixels,const exr_page *pg,size_t index) {
  const char *all=exr_document_text(document,NULL);page_number=index;page_start=pg->start;page_end=pg->end;
  selection_start=selection_end=0;
  gtk_image_set_from_pixbuf(GTK_IMAGE(image),pixels);g_object_unref(pixels);
  gtk_text_buffer_set_text(gtk_text_view_get_buffer(GTK_TEXT_VIEW(text)),all+page_start,(int)(page_end-page_start));
  gtk_stack_set_visible_child_name(GTK_STACK(stack),"reader");
  char *caption=g_strdup_printf("Page %zu | %d px | %zu notes",page_number+1,font_size,note_count);
  status(EXR_OK,caption);g_free(caption);save_progress();state();
}
static gboolean show_page(size_t index,gboolean seek,size_t position) {
  if(!pager) return FALSE;
  GdkPixbuf *pixels=NULL;const exr_page *pg=NULL;size_t found=0;
  exr_status s=frame(pager,document,index,seek,position,&pixels,&pg,&found);
  if(s!=EXR_OK) { status(s,s==EXR_ARGUMENT?"End of book":"Could not display page");return FALSE; }
  present(pixels,pg,found);return TRUE;
}
static void open_id(int64_t id) {
  exr_document *doc=NULL;exr_pager *p=NULL;exr_error error={0};exr_anchor point={0};exr_anchor_state anchor_state;
  exr_layout_config config=exr_layout_config_defaults();GdkPixbuf *pixels=NULL;const exr_page *pg=NULL;size_t found=0;
  if(!save_progress()) return;
  exr_status s=exr_library_document(library,id,&doc,&error);
  config.page=(exr_layout_options){520,640,28,(float)font_size,1.5f,8};
  if(s==EXR_OK) s=exr_pager_create(doc,font,&config,&p,&error);
  if(s==EXR_OK) s=exr_pager_set_cache(p,3,8*1024*1024,&error);
  if(s==EXR_OK) s=exr_library_progress_get(library,id,&point,&anchor_state,&error);
  if(s==EXR_OK) s=frame(p,doc,0,TRUE,point.start,&pixels,&pg,&found);
  exr_anchor_free(&point);
  if(s!=EXR_OK) { exr_pager_free(p);exr_document_free(doc);status(s,"Could not open book");return; }
  exr_pager_free(pager);exr_document_free(document);pager=p;document=doc;book_id=id;
  refresh_notes();present(pixels,pg,found);
}
static exr_format format_for(const char *path) {
  const char *ext=strrchr(path,'.');if(!ext) return EXR_CUSTOM;
  if(!g_ascii_strcasecmp(ext,".epub")) return EXR_EPUB;
  if(!g_ascii_strcasecmp(ext,".txt")) return EXR_TXT;
  if(!g_ascii_strcasecmp(ext,".html") || !g_ascii_strcasecmp(ext,".xhtml")) return EXR_HTML;
  if(!g_ascii_strcasecmp(ext,".fb2")) return EXR_FB2;
  if(!g_ascii_strcasecmp(ext,".rtf")) return EXR_RTF;
  if(!g_ascii_strcasecmp(ext,".docx")) return EXR_DOCX;
  if(!g_ascii_strcasecmp(ext,".mobi")) return EXR_MOBI;
  return EXR_CUSTOM;
}
static void import_path(const char *path) {
  exr_format format=format_for(path);exr_error error={0};int64_t id=0;int created=0;
  if(format==EXR_CUSTOM) { status(EXR_UNSUPPORTED,"Choose EPUB, TXT, HTML, FB2, RTF, DOCX or MOBI");return; }
  FILE *file=fopen(path,"rb");if(!file) { status(EXR_IO,"Could not read file");return; }
  /* Read once with a fixed cap; do not trust a prior path stat after opening. */
  unsigned char *data=g_try_malloc(EXR_HOST_INPUT_LIMIT+1u);
  if(!data) { fclose(file);status(EXR_MEMORY,"Not enough memory");return; }
  size_t n=fread(data,1,EXR_HOST_INPUT_LIMIT+1u,file);int failed=ferror(file);fclose(file);
  if(failed || !n || n>EXR_HOST_INPUT_LIMIT) {
    g_free(data);status(n>EXR_HOST_INPUT_LIMIT?EXR_LIMIT:EXR_IO,"File must be nonempty and no larger than 8 MiB");return;
  }
  char *title=g_path_get_basename(path);
  exr_status s=exr_library_import_unique(library,format,data,n,title,&id,&created,&error);
  g_free(title);g_free(data);
  if(s!=EXR_OK) { status(s,"Could not import file");return; }
  refresh_shelf();open_id(id);
}
static void import_dialog(void) {
  GtkWidget *dialog=gtk_file_chooser_dialog_new("Import book",GTK_WINDOW(window),GTK_FILE_CHOOSER_ACTION_OPEN,
    "Cancel",GTK_RESPONSE_CANCEL,"Import",GTK_RESPONSE_ACCEPT,NULL);
  if(gtk_dialog_run(GTK_DIALOG(dialog))==GTK_RESPONSE_ACCEPT) {
    char *path=gtk_file_chooser_get_filename(GTK_FILE_CHOOSER(dialog));gtk_widget_destroy(dialog);
    import_path(path);g_free(path);
  } else { gtk_widget_destroy(dialog);state(); }
}
static void resize_font(int delta) {
  if(!document || font_size+delta<12 || font_size+delta>48) return;
  int old=font_size;exr_pager *p=NULL;exr_error error={0};
  exr_layout_config config=exr_layout_config_defaults();font_size+=delta;
  config.page=(exr_layout_options){520,640,28,(float)font_size,1.5f,8};
  exr_status s=exr_pager_create(document,font,&config,&p,&error);
  if(s==EXR_OK) s=exr_pager_set_cache(p,3,8*1024*1024,&error);
  GdkPixbuf *pixels=NULL;const exr_page *pg=NULL;size_t found=0;
  if(s==EXR_OK) s=frame(p,document,0,TRUE,page_start,&pixels,&pg,&found);
  if(s!=EXR_OK) { exr_pager_free(p);font_size=old;status(s,"Could not change font size");return; }
  exr_pager_free(pager);pager=p;present(pixels,pg,found);
}
static void add_note(void) {
  GtkTextBuffer *buffer=gtk_text_view_get_buffer(GTK_TEXT_VIEW(text));GtkTextIter a,b;
  if(!document || !gtk_text_buffer_get_selection_bounds(buffer,&a,&b)) { status(EXR_ARGUMENT,"Select page text first");return; }
  const char *all=exr_document_text(document,NULL)+page_start;
  exr_note note={0};exr_error error={0};int64_t id=0;
  note.book_id=book_id;note.start=page_start+(size_t)(g_utf8_offset_to_pointer(all,gtk_text_iter_get_offset(&a))-all);
  note.end=page_start+(size_t)(g_utf8_offset_to_pointer(all,gtk_text_iter_get_offset(&b))-all);
  note.text=(char *)gtk_entry_get_text(GTK_ENTRY(comment));
  exr_status s=exr_library_note(library,&note,&id,&error);
  if(s!=EXR_OK) { status(s,"Could not save note");return; }
  selection_start=note.start;selection_end=note.end;refresh_notes();status(EXR_OK,"Note saved");
}
static void delete_note(void) {
  GtkListBoxRow *row=gtk_list_box_get_selected_row(GTK_LIST_BOX(notes));
  if(!row) { status(EXR_ARGUMENT,"Select a note first");return; }
  exr_note *note=g_object_get_data(G_OBJECT(row),"note");exr_error error={0};
  exr_status s=exr_library_remove_note(library,note->id,&error);
  if(s==EXR_OK) { refresh_notes();status(EXR_OK,"Note deleted"); }
  else status(s,"Could not delete note");
}
static void shelf_activated(GtkListBox *box,GtkListBoxRow *row,gpointer unused) {
  (void)box;(void)unused;int64_t *id=g_object_get_data(G_OBJECT(row),"book-id");open_id(*id);
}
static void note_activated(GtkListBox *box,GtkListBoxRow *row,gpointer unused) {
  (void)box;(void)unused;exr_note *note=g_object_get_data(G_OBJECT(row),"note");
  if(note->start==SIZE_MAX) { status(EXR_ARGUMENT,"This note has no resolved location");return; }
  size_t start=note->start,end=note->end;
  if(show_page(0,TRUE,start)) {
    const char *all=exr_document_text(document,NULL);GtkTextBuffer *buffer=gtk_text_view_get_buffer(GTK_TEXT_VIEW(text));
    GtkTextIter a,b;end=MIN(end,page_end);
    gtk_text_buffer_get_iter_at_offset(buffer,&a,(int)g_utf8_pointer_to_offset(all+page_start,all+start));
    gtk_text_buffer_get_iter_at_offset(buffer,&b,(int)g_utf8_pointer_to_offset(all+page_start,all+end));
    gtk_text_buffer_select_range(buffer,&a,&b);selection_start=start;selection_end=end;state();
  }
}
static void focus_list(GtkWidget *box) {
  GtkListBoxRow *row=gtk_list_box_get_selected_row(GTK_LIST_BOX(box));
  if(!row) row=gtk_list_box_get_row_at_index(GTK_LIST_BOX(box),0);
  if(row) { gtk_list_box_select_row(GTK_LIST_BOX(box),row);gtk_widget_grab_focus(GTK_WIDGET(row)); }
  else gtk_widget_grab_focus(box);
}
static void action(GtkWidget *widget,gpointer name) {
  (void)widget;const char *a=name;
  if(!strcmp(a,"import")) import_dialog();
  else if(!strcmp(a,"shelf")) { save_progress();refresh_shelf();gtk_stack_set_visible_child_name(GTK_STACK(stack),"shelf");focus_list(shelf);state(); }
  else if(!strcmp(a,"previous")) { if(page_number) show_page(page_number-1,FALSE,0);else status(EXR_ARGUMENT,"First page"); }
  else if(!strcmp(a,"next")) show_page(page_number+1,FALSE,0);
  else if(!strcmp(a,"bigger")) resize_font(2);
  else if(!strcmp(a,"smaller")) resize_font(-2);
  else if(!strcmp(a,"text")) { gtk_widget_grab_focus(text);state(); }
  else if(!strcmp(a,"note")) add_note();
  else if(!strcmp(a,"notes")) { focus_list(notes);state(); }
  else if(!strcmp(a,"delete")) delete_note();
  else if(!strcmp(a,"comment")) { gtk_widget_grab_focus(comment);state(); }
}
static gboolean key(GtkWidget *w,GdkEventKey *event,gpointer unused) {
  (void)w;(void)unused;
  static const char *names[]={"import","shelf","previous","next","bigger","smaller","text","note","notes","delete","comment"};
  if(event->state & (GDK_CONTROL_MASK|GDK_MOD1_MASK|GDK_SUPER_MASK)) return FALSE;
  if(event->keyval>=GDK_KEY_F1 && event->keyval<=GDK_KEY_F11) { action(NULL,(gpointer)names[event->keyval-GDK_KEY_F1]);return TRUE; }
  return FALSE;
}
static gboolean focus_changed(GtkWidget *w,GdkEventFocus *event,gpointer unused) {
  (void)w;(void)unused;if(!event->in) save_progress();state();return FALSE;
}
static gboolean close_window(GtkWidget *w,GdkEvent *event,gpointer unused) {
  (void)w;(void)event;(void)unused;return !save_progress();
}
static void destroyed(GtkWidget *w,gpointer unused) { (void)w;(void)unused;gtk_main_quit(); }
static void selection_changed(GtkTextBuffer *buffer,GtkTextIter *iter,GtkTextMark *mark,gpointer unused) {
  (void)buffer;(void)iter;(void)mark;(void)unused;state();
}
static GtkWidget *scroll(GtkWidget *child) {
  GtkWidget *s=gtk_scrolled_window_new(NULL,NULL);gtk_container_add(GTK_CONTAINER(s),child);return s;
}
int main(int argc,char **argv) {
  if(argc==2 && !strcmp(argv[1],"--version")) { printf("%s %u\n",exr_version(),exr_abi_version());return 0; }
  if(argc!=1 && argc!=3 && argc!=4) { fprintf(stderr,"Usage: exreader-linux [FONT STATE_DIRECTORY [OBSERVATION_FILE]]\n");return 2; }
  char *default_font=NULL;
  if(argc==1) {
    char *executable=g_file_read_link("/proc/self/exe",NULL);
    if(!executable) return 2;
    char *bin=g_path_get_dirname(executable),*package=g_path_get_dirname(bin);
    default_font=g_build_filename(package,"Reader.otf",NULL);
    g_free(executable);g_free(bin);g_free(package);
    home=g_build_filename(g_get_user_data_dir(),"exreader",NULL);
  } else home=g_strdup(argv[2]);
  state_path=argc==4?g_strdup(argv[3]):NULL;
  if(g_mkdir_with_parents(home,0700)) return 2;
  settings_path=g_build_filename(home,"reader.ini",NULL);settings=g_key_file_new();
  g_key_file_load_from_file(settings,settings_path,G_KEY_FILE_NONE,NULL);
  int size=g_key_file_get_integer(settings,"reader","font",NULL);if(size>=12 && size<=48) font_size=size;
  int64_t last=g_key_file_get_int64(settings,"reader","book",NULL);
  exr_error error={0};char *db=g_build_filename(home,"library.sqlite",NULL);
  exr_status s=exr_library_open(db,&library,&error);g_free(db);
  if(s!=EXR_OK || exr_font_open(default_font?default_font:argv[1],&font,&error)!=EXR_OK) {
    fprintf(stderr,"Could not open the library or reader font\n");exr_library_close(library);g_free(default_font);return 2;
  }
  g_free(default_font);
  gtk_init(NULL,NULL);window=gtk_window_new(GTK_WINDOW_TOPLEVEL);
  gtk_window_set_title(GTK_WINDOW(window),"EXReader Linux");gtk_window_set_default_size(GTK_WINDOW(window),1040,820);
  GtkWidget *root=gtk_box_new(GTK_ORIENTATION_VERTICAL,6),*toolbar=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,4);
  gtk_container_add(GTK_CONTAINER(window),root);gtk_box_pack_start(GTK_BOX(root),toolbar,FALSE,FALSE,0);
  const char *names[]={"import","shelf","previous","next","bigger","smaller","text","note","notes","delete"};
  const char *titles[]={"Import F1","Shelf F2","Previous F3","Next F4","A+ F5","A− F6","Text F7","Add note F8","Notes F9","Delete F10"};
  for(size_t i=0;i<G_N_ELEMENTS(names);i++) {
    GtkWidget *button=gtk_button_new_with_label(titles[i]);gtk_box_pack_start(GTK_BOX(toolbar),button,FALSE,FALSE,0);
    g_signal_connect(button,"clicked",G_CALLBACK(action),(gpointer)names[i]);
  }
  label=gtk_label_new("Import a book to start reading");gtk_box_pack_start(GTK_BOX(root),label,FALSE,FALSE,0);
  stack=gtk_stack_new();gtk_box_pack_start(GTK_BOX(root),stack,TRUE,TRUE,0);
  shelf=gtk_list_box_new();gtk_list_box_set_activate_on_single_click(GTK_LIST_BOX(shelf),TRUE);
  atk_object_set_name(gtk_widget_get_accessible(shelf),"Bookshelf");
  gtk_stack_add_named(GTK_STACK(stack),scroll(shelf),"shelf");
  GtkWidget *reader=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,8),*right=gtk_box_new(GTK_ORIENTATION_VERTICAL,6);
  image=gtk_image_new();gtk_box_pack_start(GTK_BOX(reader),scroll(image),TRUE,TRUE,0);
  atk_object_set_name(gtk_widget_get_accessible(image),"Rendered page; selectable text is in the adjacent panel");
  text=gtk_text_view_new();gtk_text_view_set_editable(GTK_TEXT_VIEW(text),FALSE);
  atk_object_set_name(gtk_widget_get_accessible(text),"Selectable page text");
  gtk_text_view_set_wrap_mode(GTK_TEXT_VIEW(text),GTK_WRAP_WORD_CHAR);gtk_widget_set_size_request(text,320,250);
  gtk_box_pack_start(GTK_BOX(right),scroll(text),TRUE,TRUE,0);
  comment=gtk_entry_new();gtk_entry_set_placeholder_text(GTK_ENTRY(comment),"Comment (F11); select text, then Add note");
  atk_object_set_name(gtk_widget_get_accessible(comment),"Annotation comment");
  gtk_box_pack_start(GTK_BOX(right),comment,FALSE,FALSE,0);
  notes=gtk_list_box_new();gtk_widget_set_size_request(notes,320,120);
  atk_object_set_name(gtk_widget_get_accessible(notes),"Saved notes; activate to return to selected text");
  gtk_box_pack_start(GTK_BOX(right),scroll(notes),TRUE,TRUE,0);gtk_box_pack_start(GTK_BOX(reader),right,FALSE,FALSE,0);
  gtk_stack_add_named(GTK_STACK(stack),reader,"reader");
  g_signal_connect(window,"key-press-event",G_CALLBACK(key),NULL);
  g_signal_connect(window,"focus-in-event",G_CALLBACK(focus_changed),NULL);
  g_signal_connect(window,"focus-out-event",G_CALLBACK(focus_changed),NULL);
  g_signal_connect(window,"delete-event",G_CALLBACK(close_window),NULL);
  g_signal_connect(window,"destroy",G_CALLBACK(destroyed),NULL);
  g_signal_connect(shelf,"row-activated",G_CALLBACK(shelf_activated),NULL);
  g_signal_connect(notes,"row-activated",G_CALLBACK(note_activated),NULL);
  g_signal_connect(gtk_text_view_get_buffer(GTK_TEXT_VIEW(text)),"mark-set",G_CALLBACK(selection_changed),NULL);
  refresh_shelf();gtk_widget_show_all(window);gtk_window_present(GTK_WINDOW(window));
  if(last) open_id(last);
  state();gtk_main();
  exr_pager_free(pager);exr_document_free(document);exr_books_free(books,book_count);
  exr_library_close(library);exr_font_free(font);g_key_file_free(settings);
  g_free(home);g_free(settings_path);g_free(state_path);return 0;
}
