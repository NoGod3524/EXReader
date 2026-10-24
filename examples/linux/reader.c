/* SPDX-License-Identifier: MIT */
#include <gtk/gtk.h>
#include "reading.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#ifdef EXR_READER_ACCOUNT
#include <reader_session.h>
#include <exr_credentials.h>
#endif

static GtkWidget *window,*image,*label,*shelf,*notes,*text,*comment,*stack,*bigger,*smaller;
static size_t book_count,page_number,page_start,page_end,note_count,selection_start,selection_end,part;
static size_t position,projection_bytes,index_bytes,workspace_bytes,windows_evicted,snapshot_bytes;
static int64_t book_id;
static int font_size=24,last_error,bounded,fixed,zoom_percent=100;
static size_t fixed_pages;
static guint sequence;
static guint frame_generation,painted_generation;
static char *home,*settings_path,*state_path,*page_text;
static GKeyFile *settings;
static GAsyncQueue *queue;
static GThread *thread;
static gint generation=1;
static int worker_generation;
static gboolean busy,saving,save_failed,closing,close_after_save;
static gboolean choosing_file;
static gboolean profile_writable;
typedef struct { reader_command command;char *path,*comment;int generation,stop,shelf_generation; } host_job;
typedef struct { reader_result value;reader_action action;int generation,profile_writable,shelf_generation; } host_result;
static void stop_worker(void);
#ifdef EXR_READER_ACCOUNT
static void accounts_open(GtkWidget *,gpointer);
static void accounts_apply(host_result *);
static gboolean accounts_opened(void);
static gboolean accounts_defer_exit(void);
static char *accounts_observation(void);
static void accounts_cleanup(void);
static gboolean close_window(GtkWidget *,GdkEvent *,gpointer);
#endif
#ifdef EXR_READER_DESKTOP_METADATA
static gboolean metadata_running;
static GtkWidget *metadata_dialog,*metadata_title,*metadata_author,*metadata_favorite,*metadata_message;
static char *metadata_key;
static uint64_t metadata_token;
static int64_t metadata_book;
static void metadata_apply(host_result *);
static void metadata_edit(GtkWidget *,gpointer);
static void collections_open(GtkWidget *,gpointer);
static void collections_apply(host_result *);
static gboolean collections_opened(void);
static char *collections_observation(void);
static void open_id(int64_t);
#endif
#ifdef EXR_READER_PRODUCT_CATALOG
static GtkWidget *shelf_scroll,*search;
static gint shelf_generation;
static gboolean shelf_loading,shelf_before,shelf_after,shelf_restoring,shelf_pending,shelf_filter_pending;
static guint search_timer,viewport_timer,restore_timer,shelf_edge_idle;
static unsigned shelf_queries,shelf_evicted,shelf_max_cached;
static unsigned shelf_layout,restore_layout;
static char *shelf_query,*shelf_top_key,*shelf_selected_key,*restore_key;
static double shelf_top_offset,restore_offset;
static void shelf_request(int direction,gboolean anchor);
static void shelf_remember(void);
static GtkWidget *shelf_top_row(void);
static gboolean shelf_save_viewport(gpointer unused);
static void shelf_schedule_restore(void);
static void shelf_scrolled(GtkAdjustment *adjustment,gpointer unused);
static gboolean shelf_check_edges(gpointer unused) {
  (void)unused;shelf_edge_idle=0;
  shelf_scrolled(gtk_scrolled_window_get_vadjustment(GTK_SCROLLED_WINDOW(shelf_scroll)),NULL);
  return G_SOURCE_REMOVE;
}
#endif

static void state(void) {
  if(!state_path) return;
  GtkTextIter a,b;size_t selected=0;
  if(gtk_text_buffer_get_selection_bounds(gtk_text_view_get_buffer(GTK_TEXT_VIEW(text)),&a,&b))
    selected=(size_t)(gtk_text_iter_get_offset(&b)-gtk_text_iter_get_offset(&a));
  char *data=g_strdup_printf("[host]\nsequence=%u\nerror=%d\nbook=%"G_GINT64_FORMAT"\nbooks=%zu\npage=%zu\nstart=%zu\nend=%zu\nfont=%d\nnotes=%zu\nselected=%zu\nselection_start=%zu\nselection_end=%zu\nvisible=%d\nfocused=%d\nbounded=%d\npart=%zu\nbusy=%d\nsaving=%d\ngeneration=%d\nsave_failed=%d\n",
    ++sequence,last_error,book_id,book_count,page_number,page_start,page_end,font_size,note_count,selected,
    selection_start,selection_end,gtk_widget_get_visible(window),gtk_window_is_active(GTK_WINDOW(window)),
    bounded,part,busy,saving,g_atomic_int_get(&generation),save_failed);
  char *metrics=g_strdup_printf("position=%zu\nprojection_bytes=%zu\nindex_bytes=%zu\nworkspace_bytes=%zu\nwindows_evicted=%zu\nsnapshot_bytes=%zu\nreader_visible=%d\nfixed=%d\nzoom=%d\npages=%zu\n",
    position,projection_bytes,index_bytes,workspace_bytes,windows_evicted,snapshot_bytes,
    !strcmp(gtk_stack_get_visible_child_name(GTK_STACK(stack)),"reader"),fixed,zoom_percent,fixed_pages);
  char *complete=g_strconcat(data,metrics,NULL);g_free(data);g_free(metrics);data=complete;
#ifdef EXR_READER_PRODUCT_CATALOG
  int64_t first_id=0,last_id=0,top_id=0;GtkWidget *top=shelf_top_row();
  GList *rows=gtk_container_get_children(GTK_CONTAINER(shelf));
  if(rows) {
    first_id=*(int64_t *)g_object_get_data(G_OBJECT(rows->data),"book-id");
    last_id=*(int64_t *)g_object_get_data(G_OBJECT(g_list_last(rows)->data),"book-id");
  }
  if(top) top_id=*(int64_t *)g_object_get_data(G_OBJECT(top),"book-id");
  g_list_free(rows);
  char *cache_metrics=g_strdup_printf("shelf_first_id=%"G_GINT64_FORMAT"\nshelf_last_id=%"G_GINT64_FORMAT"\nshelf_top_id=%"G_GINT64_FORMAT"\n",first_id,last_id,top_id);
  complete=g_strconcat(data,cache_metrics,NULL);g_free(data);g_free(cache_metrics);data=complete;
  char *shelf_metrics=g_strdup_printf("shelf_loading=%d\nshelf_generation=%d\nshelf_queries=%u\nshelf_evicted=%u\nshelf_max_cached=%u\nshelf_before=%d\nshelf_after=%d\nshelf_restoring=%d\nshelf_pending=%d\n",
    shelf_loading,g_atomic_int_get(&shelf_generation),shelf_queries,shelf_evicted,shelf_max_cached,
    shelf_before,shelf_after,shelf_restoring,shelf_pending);
  complete=g_strconcat(data,shelf_metrics,NULL);g_free(data);g_free(shelf_metrics);data=complete;
#endif
  GtkWidget *viewport=gtk_widget_get_ancestor(image,GTK_TYPE_SCROLLED_WINDOW);int x=0,y=0;
  if(viewport && gtk_widget_translate_coordinates(viewport,window,0,0,&x,&y)) {
    char *bounds=g_strdup_printf("page_x=%d\npage_y=%d\npage_width=%d\npage_height=%d\nframe_generation=%u\npainted_generation=%u\n",
      x,y,gtk_widget_get_allocated_width(viewport),gtk_widget_get_allocated_height(viewport),frame_generation,painted_generation);
    complete=g_strconcat(data,bounds,NULL);g_free(data);g_free(bounds);data=complete;
  }
#ifdef EXR_READER_PRODUCT_CATALOG
  char *keys=g_strdup_printf("[shelf]\ntop_key=%s\nselected_key=%s\ntop_offset=%.3f\n",
    shelf_top_key ? shelf_top_key:"",shelf_selected_key ? shelf_selected_key:"",shelf_top_offset);
  complete=g_strconcat(data,keys,NULL);g_free(data);g_free(keys);data=complete;
#endif
#ifdef EXR_READER_DESKTOP_METADATA
  char *organization=collections_observation();
  complete=g_strconcat(data,organization,NULL);g_free(data);g_free(organization);data=complete;
#endif
#ifdef EXR_READER_ACCOUNT
  char *account=accounts_observation();
  complete=g_strconcat(data,account,NULL);g_free(data);g_free(account);data=complete;
#endif
  g_file_set_contents(state_path,data,-1,NULL);g_free(data);
}
static void status(exr_status code,const char *message) {
  g_print("STATUS code=%d book=%"G_GINT64_FORMAT" part=%zu page=%zu busy=%d saving=%d generation=%d message=%s\n",
    (int)code,book_id,part,page_number,busy,saving,g_atomic_int_get(&generation),message);
  last_error=(int)code;gtk_label_set_text(GTK_LABEL(label),message);state();
}
static gboolean save_settings(void) {
  /* No profile writes before the worker has successfully opened its library.
     In product builds that also proves ownership of the profile lifetime lock. */
  if(!profile_writable) return TRUE;
  GError *error=NULL;
  g_key_file_set_int64(settings,"reader","book",book_id);g_key_file_set_integer(settings,"reader","font",font_size);
  g_key_file_set_integer(settings,"reader","zoom",zoom_percent);
#ifdef EXR_READER_PRODUCT_CATALOG
  g_key_file_set_string(settings,"shelf","query",shelf_query ? shelf_query:"");
  g_key_file_set_string(settings,"shelf","top_key",shelf_top_key ? shelf_top_key:"");
  g_key_file_set_string(settings,"shelf","selected_key",shelf_selected_key ? shelf_selected_key:"");
  g_key_file_set_double(settings,"shelf","top_offset",shelf_top_offset);
#endif
  if(!g_key_file_save_to_file(settings,settings_path,&error)) {
    status(EXR_IO,"Could not save reading settings");g_clear_error(&error);return FALSE;
  }
  return TRUE;
}
static void rows_clear(GtkWidget *box) {
  GList *children=gtk_container_get_children(GTK_CONTAINER(box));
  for(GList *p=children;p;p=p->next) gtk_widget_destroy(GTK_WIDGET(p->data));
  g_list_free(children);
}
static void shelf_present(reader_result *result) {
#ifdef EXR_READER_PRODUCT_CATALOG
  shelf_pending=result->shelf_pending;gtk_widget_set_sensitive(search,!shelf_pending);
  if(result->cursors) {
    if(result->shelf_direction && book_count+result->book_count>150 &&
       !strcmp(gtk_stack_get_visible_child_name(GTK_STACK(stack)),"shelf")) {
      GtkAdjustment *adjustment=gtk_scrolled_window_get_vadjustment(GTK_SCROLLED_WINDOW(shelf_scroll));
      GtkListBoxRow *first=GTK_LIST_BOX_ROW(shelf_top_row());
      GtkListBoxRow *last=gtk_list_box_get_row_at_y(GTK_LIST_BOX(shelf),
        (int)(gtk_adjustment_get_value(adjustment)+gtk_adjustment_get_page_size(adjustment)-1));
      size_t drop=book_count+result->book_count-150;
      int first_index=first ? gtk_list_box_row_get_index(first):0;
      int last_index=last ? gtk_list_box_row_get_index(last):(int)book_count-1;
      if((result->shelf_direction>0 && first_index<(int)drop) ||
         (result->shelf_direction<0 && last_index>=(int)(book_count-drop))) {
        shelf_loading=FALSE;return; /* The user reversed while this page was in flight. */
      }
    }
    if(result->shelf_direction) shelf_remember();
    g_free(restore_key);restore_key=g_strdup(shelf_top_key);restore_offset=shelf_top_offset;
    shelf_restoring=TRUE;restore_layout=shelf_layout+1;
    if(!result->shelf_direction) rows_clear(shelf);
    gboolean trimmed=FALSE;
    GList *old_rows=gtk_container_get_children(GTK_CONTAINER(shelf));size_t old_count=g_list_length(old_rows);
    while(old_count+result->book_count>150) {
      GList *item=result->shelf_direction<0 ? g_list_last(old_rows):old_rows;
      gtk_widget_destroy(GTK_WIDGET(item->data));old_rows=g_list_delete_link(old_rows,item);
      old_count--;shelf_evicted++;trimmed=TRUE;
    }
    g_list_free(old_rows);
    for(size_t i=0;i<result->book_count;i++) {
      exr_book *book=&result->books[i];reader_shelf_cursor *cursor=&result->cursors[i];
      GtkWidget *row=gtk_list_box_row_new();char *caption=g_strdup_printf("%s%s\n%s",book->title,book->favorite ? " ★":"",book->author);
      GtkWidget *title=gtk_label_new(caption);g_free(caption);
      gtk_label_set_xalign(GTK_LABEL(title),0);gtk_label_set_ellipsize(GTK_LABEL(title),PANGO_ELLIPSIZE_END);
      gtk_widget_set_size_request(row,-1,48);
      int64_t *id=g_new(int64_t,1);*id=book->id;g_object_set_data_full(G_OBJECT(row),"book-id",id,g_free);
      g_object_set_data_full(G_OBJECT(row),"book-key",g_strdup(cursor->key),g_free);
      g_object_set_data_full(G_OBJECT(row),"sort-title",g_strdup(cursor->sort_title),g_free);
      gtk_container_add(GTK_CONTAINER(row),title);
      if(!book->id) { gtk_widget_set_sensitive(row,FALSE);gtk_widget_set_tooltip_text(row,"Book has not been downloaded to this device"); }
      gtk_list_box_insert(GTK_LIST_BOX(shelf),row,result->shelf_direction<0 ? (int)i:-1);
      if(shelf_selected_key && !strcmp(shelf_selected_key,cursor->key)) gtk_list_box_select_row(GTK_LIST_BOX(shelf),GTK_LIST_BOX_ROW(row));
    }
    GList *children=gtk_container_get_children(GTK_CONTAINER(shelf));size_t count=g_list_length(children);
    shelf_before=result->shelf_direction>0 ? shelf_before:result->shelf_before;
    shelf_after=result->shelf_direction<0 ? shelf_after:result->shelf_after;
    if(trimmed) {
      if(result->shelf_direction<0) shelf_after=TRUE;else shelf_before=TRUE;
    }
    book_count=count;shelf_max_cached=MAX(shelf_max_cached,(unsigned)count);g_list_free(children);
    gtk_widget_show_all(shelf);gtk_widget_queue_resize(shelf);shelf_loading=FALSE;shelf_schedule_restore();
    return;
  }
#endif
#ifdef EXR_READER_PRODUCT_CATALOG
  shelf_loading=shelf_restoring=shelf_before=shelf_after=FALSE;
#endif
  rows_clear(shelf);book_count=result->book_count;
  for(size_t i=0;i<result->book_count;i++) {
    GtkWidget *row=gtk_list_box_row_new(),*title=gtk_label_new(result->books[i].title);
    int64_t *id=g_new(int64_t,1);*id=result->books[i].id;g_object_set_data_full(G_OBJECT(row),"book-id",id,g_free);
    gtk_container_add(GTK_CONTAINER(row),title);gtk_container_add(GTK_CONTAINER(shelf),row);
  }
  gtk_widget_show_all(shelf);
}
#ifdef EXR_READER_PRODUCT_CATALOG
static GtkWidget *shelf_top_row(void) {
  if(!shelf_scroll) return NULL;
  GtkAdjustment *adjustment=gtk_scrolled_window_get_vadjustment(GTK_SCROLLED_WINDOW(shelf_scroll));
  return GTK_WIDGET(gtk_list_box_get_row_at_y(GTK_LIST_BOX(shelf),(int)gtk_adjustment_get_value(adjustment)));
}
static void shelf_allocated(GtkWidget *widget,GtkAllocation *allocation,gpointer unused) {
  (void)widget;(void)allocation;(void)unused;shelf_layout++;
  if(!shelf_edge_idle) shelf_edge_idle=g_idle_add(shelf_check_edges,NULL);
}
static void shelf_remember(void) {
  if(shelf_filter_pending || shelf_restoring || !shelf_scroll || strcmp(gtk_stack_get_visible_child_name(GTK_STACK(stack)),"shelf")) return;
  GtkWidget *row=shelf_top_row();if(!row) return;
  GtkAllocation allocation;gtk_widget_get_allocation(row,&allocation);
  GtkAdjustment *adjustment=gtk_scrolled_window_get_vadjustment(GTK_SCROLLED_WINDOW(shelf_scroll));
  g_free(shelf_top_key);shelf_top_key=g_strdup(g_object_get_data(G_OBJECT(row),"book-key"));
  shelf_top_offset=gtk_adjustment_get_value(adjustment)-allocation.y;
}
static gboolean shelf_restore(gpointer unused) {
  (void)unused;
  if(!shelf_restoring || strcmp(gtk_stack_get_visible_child_name(GTK_STACK(stack)),"shelf")) {
    restore_timer=0;return G_SOURCE_REMOVE;
  }
  if(book_count && shelf_layout<restore_layout) return G_SOURCE_CONTINUE;
  GList *children=gtk_container_get_children(GTK_CONTAINER(shelf));GtkWidget *anchor=NULL;
  for(GList *p=children;p;p=p->next) {
    const char *key=g_object_get_data(G_OBJECT(p->data),"book-key");
    if(key && restore_key && !strcmp(key,restore_key)) { anchor=p->data;break; }
  }
  if(!anchor) { anchor=children ? children->data:NULL;restore_offset=0; }
  if(anchor && gtk_widget_get_allocated_height(anchor)<=1) { g_list_free(children);return G_SOURCE_CONTINUE; }
  GtkAdjustment *adjustment=gtk_scrolled_window_get_vadjustment(GTK_SCROLLED_WINDOW(shelf_scroll));
  GtkAllocation allocation={0};if(anchor) gtk_widget_get_allocation(anchor,&allocation);
  double maximum=MAX(gtk_adjustment_get_lower(adjustment),gtk_adjustment_get_upper(adjustment)-gtk_adjustment_get_page_size(adjustment));
  gtk_adjustment_set_value(adjustment,CLAMP(allocation.y+restore_offset,0,maximum));
  g_list_free(children);shelf_restoring=FALSE;shelf_remember();
  if(viewport_timer) g_source_remove(viewport_timer);
  viewport_timer=g_timeout_add(300,shelf_save_viewport,NULL);
  state();restore_timer=0;shelf_scrolled(adjustment,NULL);return G_SOURCE_REMOVE;
}
static void shelf_schedule_restore(void) {
  if(shelf_restoring && !restore_timer) restore_timer=g_timeout_add(30,shelf_restore,NULL);
}
static gboolean shelf_save_viewport(gpointer unused) {
  (void)unused;viewport_timer=0;shelf_remember();save_settings();state();return G_SOURCE_REMOVE;
}
static void shelf_scrolled(GtkAdjustment *adjustment,gpointer unused) {
  (void)unused;
  if(shelf_filter_pending || shelf_restoring || !shelf_query || strcmp(gtk_stack_get_visible_child_name(GTK_STACK(stack)),"shelf")) return;
  shelf_remember();if(viewport_timer) g_source_remove(viewport_timer);
  viewport_timer=g_timeout_add(300,shelf_save_viewport,NULL);
  double value=gtk_adjustment_get_value(adjustment),page=gtk_adjustment_get_page_size(adjustment);
  if(!shelf_loading && !busy && page>1) {
    if(shelf_after && value+page>=gtk_adjustment_get_upper(adjustment)-120) shelf_request(1,FALSE);
    else if(shelf_before && value<120) shelf_request(-1,FALSE);
  }
}
static void shelf_selected(GtkListBox *box,GtkListBoxRow *row,gpointer unused) {
  (void)box;(void)unused;if(!row) return;
  g_free(shelf_selected_key);shelf_selected_key=g_strdup(g_object_get_data(G_OBJECT(row),"book-key"));
  if(!shelf_restoring) { save_settings();state(); }
}
static gboolean shelf_search_due(gpointer unused) {
  (void)unused;search_timer=0;
  if(busy || saving || save_failed) { search_timer=g_timeout_add(200,shelf_search_due,NULL);return G_SOURCE_REMOVE; }
  shelf_request(0,FALSE);return G_SOURCE_REMOVE;
}
static void shelf_search_changed(GtkEditable *entry,gpointer unused) {
  (void)entry;(void)unused;
  g_free(shelf_query);shelf_query=g_strdup(gtk_entry_get_text(GTK_ENTRY(search)));
  g_clear_pointer(&shelf_top_key,g_free);shelf_top_offset=0;
  shelf_filter_pending=TRUE;shelf_restoring=FALSE;
  /* Reject already queued responses immediately; debounce only the new query. */
  g_atomic_int_inc(&shelf_generation);shelf_loading=FALSE;
  if(search_timer) g_source_remove(search_timer);
  search_timer=g_timeout_add(200,shelf_search_due,NULL);
}
#endif
static void notes_present(reader_result *result) {
  rows_clear(notes);note_count=result->note_count;
  for(size_t i=0;i<result->note_count;i++) {
    GtkWidget *row=gtk_list_box_row_new(),*title=gtk_label_new(result->notes[i].text);
    int64_t *id=g_new(int64_t,1);*id=result->notes[i].id;g_object_set_data_full(G_OBJECT(row),"note-id",id,g_free);
    gtk_label_set_ellipsize(GTK_LABEL(title),PANGO_ELLIPSIZE_END);
    gtk_container_add(GTK_CONTAINER(row),title);gtk_container_add(GTK_CONTAINER(notes),row);
  }
  gtk_widget_show_all(notes);
}
static void job_free(host_job *job) {
  g_free(job->path);g_free(job->comment);
  g_free((gpointer)job->command.query);g_free((gpointer)job->command.cursor_title);
  g_free((gpointer)job->command.cursor_key);g_free((gpointer)job->command.anchor_key);
  g_free((gpointer)job->command.metadata_key);g_free((gpointer)job->command.metadata_title);
  g_free((gpointer)job->command.metadata_author);
  g_free((gpointer)job->command.collection_parent);g_free((gpointer)job->command.collection_id);
  g_free((gpointer)job->command.collection_name);g_free((gpointer)job->command.collection_position);
  g_free((gpointer)job->command.collection_book_key);g_free((gpointer)job->command.collection_group_cursor);
  g_free((gpointer)job->command.collection_member_cursor);
  g_free((gpointer)job->command.account_root);g_free((gpointer)job->command.account_id);
  reader_secret_free((char *)job->command.account_user);reader_secret_free((char *)job->command.account_password);g_free(job);
}
static void queue_commit(void) {
  host_job *job=g_new0(host_job,1);job->generation=g_atomic_int_get(&generation);
  job->command.action=READER_COMMIT;job->command.book=book_id;job->command.part=part;job->command.start=page_start;
  job->command.page=page_number;
  busy=saving=TRUE;g_async_queue_push(queue,job);state();
}
static void pixels_free(guchar *pixels,gpointer unused) { (void)unused;free(pixels); }
static gboolean apply_result(gpointer data) {
  host_result *done=data;reader_result *result=&done->value;
#ifdef EXR_READER_ACCOUNT
  if(done->action>=READER_ACCOUNT_LOAD && done->action<=READER_ACCOUNT_STAGE_NEXT) {
    accounts_apply(done);goto free_result;
  }
#endif
#ifdef EXR_READER_DESKTOP_METADATA
  if(done->action>=READER_COLLECTIONS_LIST && done->action<=READER_COLLECTIONS_DISCARD) {
    collections_apply(done);goto free_result;
  }
  if(done->action>=READER_METADATA_PREPARE && done->action<=READER_METADATA_DISCARD) {
    metadata_apply(done);goto free_result;
  }
#endif
#ifdef EXR_READER_PRODUCT_CATALOG
  if(done->action==READER_SHELF_QUERY) {
    if(closing || done->generation!=g_atomic_int_get(&generation) ||
       done->shelf_generation!=g_atomic_int_get(&shelf_generation)) goto free_result;
    shelf_loading=FALSE;
    if(result->status==EXR_OK && result->has_shelf) { shelf_filter_pending=FALSE;shelf_present(result); }
    else status(result->status,result->message);
    state();goto free_result;
  }
#endif
  if(done->generation!=g_atomic_int_get(&generation)) goto free_result;
  profile_writable=done->profile_writable;
  if(result->has_shelf) {
#ifdef EXR_READER_PRODUCT_CATALOG
    if(done->shelf_generation==g_atomic_int_get(&shelf_generation)) {
      shelf_filter_pending=FALSE;shelf_present(result);
    }
#else
    shelf_present(result);
#endif
  }
  if(done->action==READER_COMMIT) {
    gboolean retrying=save_failed;
    busy=saving=FALSE;save_failed=result->status!=EXR_OK;
    if(save_failed) { close_after_save=FALSE;status(result->status,"Position save failed; F12 retries, book switch and close are blocked"); }
    else { if(retrying) status(EXR_OK,"Position saved");else state();if(close_after_save) stop_worker(); }
    goto free_result;
  }
  if(result->status!=EXR_OK) { busy=FALSE;status(result->status,result->message);goto free_result; }
  if(result->has_frame) {
    GdkPixbuf *pixels=gdk_pixbuf_new_from_data(result->pixels,GDK_COLORSPACE_RGB,TRUE,8,
      (int)result->width,(int)result->height,(int)result->stride,pixels_free,NULL);
    if(!pixels) { busy=FALSE;status(EXR_MEMORY,"Page presentation failed; accepted page retained");goto free_result; }
    notes_present(result);
    result->pixels=NULL;gtk_image_set_from_pixbuf(GTK_IMAGE(image),pixels);g_object_unref(pixels);
    frame_generation++;
    book_id=result->book;part=result->part;bounded=result->bounded;font_size=result->font;
    fixed=result->fixed;fixed_pages=result->page_count;if(fixed) zoom_percent=result->zoom;
    if(bigger) gtk_button_set_label(GTK_BUTTON(bigger),fixed ? "Zoom + F5":"A+ F5");
    if(smaller) gtk_button_set_label(GTK_BUTTON(smaller),fixed ? "Zoom - F6":"A− F6");
    page_number=result->page;page_start=result->start;page_end=result->end;selection_start=selection_end=0;
    position=result->position;projection_bytes=result->chapter.projection_bytes;index_bytes=result->chapter.index_bytes;
    workspace_bytes=result->chapter.peak_parse_workspace_bytes;windows_evicted=result->chapter.windows_evicted;
    snapshot_bytes=result->chapter.explicit_snapshot_bytes;
    g_free(page_text);page_text=result->text;result->text=NULL;
    gtk_text_buffer_set_text(gtk_text_view_get_buffer(GTK_TEXT_VIEW(text)),page_text,(int)result->text_size);
    gtk_stack_set_visible_child_name(GTK_STACK(stack),"reader");
    if(result->select_range) {
      GtkTextBuffer *buffer=gtk_text_view_get_buffer(GTK_TEXT_VIEW(text));GtkTextIter a,b;size_t end=MIN(result->selected_end,page_end);
      if(result->selected_start>=page_start && result->selected_start<=end) {
        gtk_text_buffer_get_iter_at_offset(buffer,&a,(int)g_utf8_pointer_to_offset(page_text,page_text+result->selected_start-page_start));
        gtk_text_buffer_get_iter_at_offset(buffer,&b,(int)g_utf8_pointer_to_offset(page_text,page_text+end-page_start));
        gtk_text_buffer_select_range(buffer,&a,&b);selection_start=result->selected_start;selection_end=end;
      }
    }
    g_print("FRAME book=%"G_GINT64_FORMAT" bounded=%d part=%zu page=%zu start=%zu end=%zu text=%zu bitmap=%zu index=%zu workspace=%zu evicted=%zu generation=%d\n",
      book_id,bounded,part,page_number,page_start,page_end,result->text_size,result->stride*result->height,
      result->chapter.index_bytes,result->chapter.peak_parse_workspace_bytes,result->chapter.windows_evicted,done->generation);
    status(EXR_OK,result->message);save_settings();queue_commit();
  } else {
    notes_present(result);
    selection_start=result->selected_start;selection_end=result->selected_end;busy=FALSE;status(EXR_OK,result->message);
  }
free_result:
  reader_result_free(result);g_free(done);return G_SOURCE_REMOVE;
}
static gboolean worker_stopped(gpointer unused) { (void)unused;gtk_widget_destroy(window);return G_SOURCE_REMOVE; }
static int worker_cancelled(void *unused) { (void)unused;return worker_generation!=g_atomic_int_get(&generation); }
static gpointer work(gpointer font_path) {
  linux_reader *reader=NULL;exr_error error={0};char *database=g_build_filename(home,"library.sqlite",NULL);
  exr_control control={worker_cancelled,NULL,NULL};exr_status opened=linux_reader_open(database,font_path,&control,&reader,&error);
  g_free(database);g_free(font_path);
  for(;;) {
    host_job *job=g_async_queue_pop(queue);if(job->stop) { job_free(job);break; }
    int barrier=job->command.action==READER_COMMIT;
#ifdef EXR_READER_DESKTOP_METADATA
    barrier=barrier || (job->command.action>=READER_METADATA_PREPARE && job->command.action<=READER_COLLECTIONS_DISCARD);
#endif
#ifdef EXR_READER_ACCOUNT
    barrier=barrier || (job->command.action>=READER_ACCOUNT_LOAD && job->command.action<=READER_ACCOUNT_STAGE_NEXT);
#endif
    if(!barrier && job->generation!=g_atomic_int_get(&generation)) { job_free(job);continue; }
    worker_generation=barrier ? g_atomic_int_get(&generation):job->generation;
    host_result *result=g_new0(host_result,1);result->generation=job->generation;result->action=job->command.action;
    result->shelf_generation=job->shelf_generation;
    result->profile_writable=opened==EXR_OK;
    if(opened==EXR_OK) linux_reader_execute(reader,&job->command,&result->value);
    else { result->value.status=opened;strcpy(result->value.message,"Could not open library or font"); }
    g_idle_add(apply_result,result);job_free(job);
  }
  linux_reader_close(reader);g_idle_add(worker_stopped,NULL);return NULL;
}
#ifdef EXR_READER_PRODUCT_CATALOG
static void shelf_request(int direction,gboolean anchor) {
#ifdef EXR_READER_ACCOUNT
  if(accounts_opened()) return;
#endif
#ifdef EXR_READER_DESKTOP_METADATA
  if(collections_opened()) return;
#endif
  if(closing || busy || saving || save_failed || shelf_pending) return;
  host_job *job=g_new0(host_job,1);job->generation=g_atomic_int_get(&generation);
  job->shelf_generation=g_atomic_int_add(&shelf_generation,1)+1;
  job->command.action=READER_SHELF_QUERY;job->command.direction=direction;
  job->command.query=g_strdup(shelf_query ? shelf_query:"");
  if(anchor && shelf_top_key) job->command.anchor_key=g_strdup(shelf_top_key);
  if(direction) {
    GList *children=gtk_container_get_children(GTK_CONTAINER(shelf));
    GList *item=direction<0 ? children:g_list_last(children);
    if(item) {
      job->command.cursor_title=g_strdup(g_object_get_data(G_OBJECT(item->data),"sort-title"));
      job->command.cursor_key=g_strdup(g_object_get_data(G_OBJECT(item->data),"book-key"));
    }
    g_list_free(children);
  }
  shelf_loading=TRUE;shelf_queries++;g_async_queue_push(queue,job);state();
}
#endif
static void submit(reader_action action,int64_t id,const char *path,int size) {
  if(closing) return;
  if(save_failed) { status(EXR_DATABASE,"Position was not saved; F12 retries before leaving");return; }
  if(busy) { status(EXR_OK,"Reading operation in progress; current page retained");return; }
  host_job *job=g_new0(host_job,1);job->generation=g_atomic_int_add(&generation,1)+1;
#ifdef EXR_READER_PRODUCT_CATALOG
  shelf_remember();job->shelf_generation=g_atomic_int_add(&shelf_generation,1)+1;shelf_loading=FALSE;
  job->command.query=g_strdup(shelf_query ? shelf_query:"");
  job->command.anchor_key=g_strdup(shelf_top_key);
#endif
  job->command.action=action;job->command.book=id;job->command.part=part;job->command.page=page_number;
  job->command.font=action==READER_ZOOM ? font_size:size;
  job->command.zoom=action==READER_ZOOM ? size:zoom_percent;
  if(path) { job->path=g_strdup(path);job->command.path=job->path; }
  if(action==READER_NOTE_ADD) {
    GtkTextIter a,b;GtkTextBuffer *buffer=gtk_text_view_get_buffer(GTK_TEXT_VIEW(text));
    if(!page_text || !gtk_text_buffer_get_selection_bounds(buffer,&a,&b)) { job_free(job);status(EXR_ARGUMENT,"Select page text first");return; }
    job->command.start=page_start+(size_t)(g_utf8_offset_to_pointer(page_text,gtk_text_iter_get_offset(&a))-page_text);
    job->command.end=page_start+(size_t)(g_utf8_offset_to_pointer(page_text,gtk_text_iter_get_offset(&b))-page_text);
    job->comment=g_strdup(gtk_entry_get_text(GTK_ENTRY(comment)));job->command.comment=job->comment;
  }
  if(action==READER_NOTE_REMOVE || action==READER_NOTE_JUMP) {
    GtkListBoxRow *row=gtk_list_box_get_selected_row(GTK_LIST_BOX(notes));
    if(!row) { job_free(job);status(EXR_ARGUMENT,"Select a note first");return; }
    int64_t *note=g_object_get_data(G_OBJECT(row),"note-id");job->command.note=*note;
  }
  busy=TRUE;status(EXR_OK,"Reading in worker");g_async_queue_push(queue,job);
}
#ifdef EXR_READER_DESKTOP_METADATA
#include "metadata_ui.inc"
#include "collections_ui.inc"
#endif
#ifdef EXR_READER_ACCOUNT
#include "accounts_ui.inc"
#endif
static void open_id(int64_t id) { submit(READER_OPEN,id,NULL,font_size); }
static void import_dialog(void) {
  if(busy || closing || save_failed) { state();return; }
  GtkWidget *dialog=gtk_file_chooser_dialog_new("Import book",GTK_WINDOW(window),GTK_FILE_CHOOSER_ACTION_OPEN,
    "Cancel",GTK_RESPONSE_CANCEL,"Import",GTK_RESPONSE_ACCEPT,NULL);
  choosing_file=TRUE;
  int response=gtk_dialog_run(GTK_DIALOG(dialog));choosing_file=FALSE;
  if(response==GTK_RESPONSE_ACCEPT) {
    char *path=gtk_file_chooser_get_filename(GTK_FILE_CHOOSER(dialog));gtk_widget_destroy(dialog);
    submit(READER_IMPORT,0,path,font_size);g_free(path);
  } else { gtk_widget_destroy(dialog);state(); }
}
static void focus_list(GtkWidget *box) {
  GtkListBoxRow *row=gtk_list_box_get_selected_row(GTK_LIST_BOX(box));if(!row) row=gtk_list_box_get_row_at_index(GTK_LIST_BOX(box),0);
  if(row) { gtk_list_box_select_row(GTK_LIST_BOX(box),row);gtk_widget_grab_focus(GTK_WIDGET(row)); } else gtk_widget_grab_focus(box);
}
static void action(GtkWidget *widget,gpointer name) {
  (void)widget;const char *a=name;
#ifdef EXR_READER_DESKTOP_METADATA
  if(metadata_running) { status(EXR_OK,"Finishing a book edit; its accepted result will be retained");return; }
#endif
  if(!strcmp(a,"import")) import_dialog();
  else if(!strcmp(a,"shelf")) {
    gtk_stack_set_visible_child_name(GTK_STACK(stack),"shelf");focus_list(shelf);
#ifdef EXR_READER_PRODUCT_CATALOG
    shelf_schedule_restore();
    if(shelf_pending) submit(READER_SHELF,0,NULL,font_size);
    else if(shelf_filter_pending) shelf_request(0,FALSE);
#endif
    state();
  }
  else if(!strcmp(a,"previous")) submit(READER_PREVIOUS,book_id,NULL,font_size);
  else if(!strcmp(a,"next")) submit(READER_NEXT,book_id,NULL,font_size);
  else if(!strcmp(a,"bigger")) submit(fixed ? READER_ZOOM:READER_FONT,book_id,NULL,fixed ? zoom_percent+25:font_size+2);
  else if(!strcmp(a,"smaller")) submit(fixed ? READER_ZOOM:READER_FONT,book_id,NULL,fixed ? zoom_percent-25:font_size-2);
  else if(!strcmp(a,"text")) { gtk_widget_grab_focus(text);state(); }
  else if(!strcmp(a,"note")) submit(READER_NOTE_ADD,book_id,NULL,font_size);
  else if(!strcmp(a,"notes")) { focus_list(notes);state(); }
  else if(!strcmp(a,"delete")) submit(READER_NOTE_REMOVE,book_id,NULL,font_size);
  else if(!strcmp(a,"comment")) { gtk_widget_grab_focus(comment);state(); }
  else if(!strcmp(a,"save")) { if(!busy && save_failed && book_id) queue_commit(); }
  else if(!strcmp(a,"cancel") && busy && !saving) {
    g_atomic_int_inc(&generation);busy=FALSE;status(EXR_CANCELLED,"Cancellation requested; accepted position retained");
  }
}
static gboolean key(GtkWidget *w,GdkEventKey *event,gpointer unused) {
  (void)w;(void)unused;
  if(choosing_file) return FALSE;
#ifdef EXR_READER_ACCOUNT
  if(accounts_opened()) return TRUE;
  if((event->state&GDK_CONTROL_MASK) && (event->state&GDK_SHIFT_MASK) && (event->keyval==GDK_KEY_A || event->keyval==GDK_KEY_a)) {
    accounts_open(NULL,NULL);return TRUE;
  }
#endif
#ifdef EXR_READER_DESKTOP_METADATA
  if((event->state&GDK_CONTROL_MASK) && (event->state&GDK_SHIFT_MASK) && (event->keyval==GDK_KEY_C || event->keyval==GDK_KEY_c)) {
    collections_open(NULL,NULL);return TRUE;
  }
  if((event->state&GDK_CONTROL_MASK) && event->keyval==GDK_KEY_e) {
    metadata_edit(NULL,NULL);return TRUE;
  }
#endif
#ifdef EXR_READER_PRODUCT_CATALOG
  if((event->state&GDK_CONTROL_MASK) && event->keyval==GDK_KEY_f) {
    gtk_stack_set_visible_child_name(GTK_STACK(stack),"shelf");shelf_schedule_restore();gtk_widget_grab_focus(search);return TRUE;
  }
#endif
  static const char *names[]={"import","shelf","previous","next","bigger","smaller","text","note","notes","delete","comment","save"};
  if(event->state & (GDK_CONTROL_MASK|GDK_MOD1_MASK|GDK_SUPER_MASK)) return FALSE;
  if(event->keyval==GDK_KEY_Escape) { action(NULL,"cancel");return TRUE; }
  if(event->keyval>=GDK_KEY_F1 && event->keyval<=GDK_KEY_F12) { action(NULL,(gpointer)names[event->keyval-GDK_KEY_F1]);return TRUE; }
  return FALSE;
}
static void shelf_activated(GtkListBox *box,GtkListBoxRow *row,gpointer unused) {
  (void)box;(void)unused;int64_t *id=g_object_get_data(G_OBJECT(row),"book-id");
  if(id && *id>0) open_id(*id);else status(EXR_ARGUMENT,"Download this book before opening it");
}
static void note_activated(GtkListBox *box,GtkListBoxRow *row,gpointer unused) {
  (void)box;(void)row;(void)unused;submit(READER_NOTE_JUMP,book_id,NULL,font_size);
}
static gboolean focus_changed(GtkWidget *w,GdkEventFocus *event,gpointer unused) {
  (void)w;(void)event;(void)unused;state();return FALSE;
}
static void page_allocated(GtkWidget *widget,GtkAllocation *allocation,gpointer unused) {
  (void)widget;(void)allocation;(void)unused;state();
}
static gboolean page_painted(GtkWidget *widget,cairo_t *context,gpointer unused) {
  (void)widget;(void)context;(void)unused;painted_generation=frame_generation;state();return FALSE;
}
static void stop_worker(void) {
#ifdef EXR_READER_ACCOUNT
  if(accounts_defer_exit()) return;
#endif
  if(closing) return;
  closing=TRUE;g_atomic_int_inc(&generation);host_job *stop=g_new0(host_job,1);stop->stop=1;g_async_queue_push(queue,stop);state();
}
static gboolean close_window(GtkWidget *w,GdkEvent *event,gpointer unused) {
  (void)w;(void)event;(void)unused;
#ifdef EXR_READER_ACCOUNT
  if(accounts_defer_exit()) return TRUE;
#endif
#ifdef EXR_READER_DESKTOP_METADATA
  if(metadata_running) { close_after_save=TRUE;return TRUE; }
#endif
  if(save_failed) { if(!busy) queue_commit();status(EXR_DATABASE,"Retrying position; close again after success");return TRUE; }
#ifdef EXR_READER_PRODUCT_CATALOG
  shelf_remember();
#endif
  if(!save_settings()) return TRUE;
  if(saving) close_after_save=TRUE;else stop_worker();return TRUE;
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
  char *font_path=NULL;
  if(argc==1) {
    char *executable=g_file_read_link("/proc/self/exe",NULL);if(!executable) return 2;
    char *bin=g_path_get_dirname(executable),*package=g_path_get_dirname(bin);
    font_path=g_build_filename(package,"Reader.otf",NULL);g_free(executable);g_free(bin);g_free(package);
    home=g_build_filename(g_get_user_data_dir(),"exreader",NULL);
  } else { home=g_strdup(argv[2]);font_path=g_strdup(argv[1]); }
  state_path=argc==4 ? g_strdup(argv[3]):NULL;if(g_mkdir_with_parents(home,0700)) return 2;
  settings_path=g_build_filename(home,"reader.ini",NULL);settings=g_key_file_new();
  g_key_file_load_from_file(settings,settings_path,G_KEY_FILE_NONE,NULL);
  int size=g_key_file_get_integer(settings,"reader","font",NULL);if(size>=12 && size<=48) font_size=size;
  int zoom=g_key_file_get_integer(settings,"reader","zoom",NULL);if(zoom>=25 && zoom<=400) zoom_percent=zoom;
  int64_t last=g_key_file_get_int64(settings,"reader","book",NULL);
#ifdef EXR_READER_PRODUCT_CATALOG
  shelf_query=g_key_file_get_string(settings,"shelf","query",NULL);
  if(!shelf_query || !g_utf8_validate(shelf_query,-1,NULL) || g_utf8_strlen(shelf_query,-1)>256) {
    g_free(shelf_query);shelf_query=g_strdup("");
  }
  shelf_top_key=g_key_file_get_string(settings,"shelf","top_key",NULL);
  shelf_selected_key=g_key_file_get_string(settings,"shelf","selected_key",NULL);
  if(shelf_top_key && strlen(shelf_top_key)>72) g_clear_pointer(&shelf_top_key,g_free);
  if(shelf_selected_key && strlen(shelf_selected_key)>72) g_clear_pointer(&shelf_selected_key,g_free);
  shelf_top_offset=g_key_file_get_double(settings,"shelf","top_offset",NULL);
  if(!isfinite(shelf_top_offset) || shelf_top_offset<0 || shelf_top_offset>256) shelf_top_offset=0;
#endif
  gtk_init(NULL,NULL);window=gtk_window_new(GTK_WINDOW_TOPLEVEL);
  gtk_window_set_title(GTK_WINDOW(window),"EXReader Linux");gtk_window_set_default_size(GTK_WINDOW(window),1040,820);
  GtkWidget *root=gtk_box_new(GTK_ORIENTATION_VERTICAL,6),*toolbar=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,4);
  gtk_container_add(GTK_CONTAINER(window),root);gtk_box_pack_start(GTK_BOX(root),toolbar,FALSE,FALSE,0);
  const char *names[]={"import","shelf","previous","next","bigger","smaller","text","note","notes","delete"};
  const char *titles[]={"Import F1","Shelf F2","Previous F3","Next F4","A+ F5","A− F6","Text F7","Add note F8","Notes F9","Delete F10"};
  for(size_t i=0;i<G_N_ELEMENTS(names);i++) {
    GtkWidget *button=gtk_button_new_with_label(titles[i]);gtk_box_pack_start(GTK_BOX(toolbar),button,FALSE,FALSE,0);
    if(i==4) bigger=button;else if(i==5) smaller=button;
    g_signal_connect(button,"clicked",G_CALLBACK(action),(gpointer)names[i]);
  }
  label=gtk_label_new("Import a book to start reading");gtk_box_pack_start(GTK_BOX(root),label,FALSE,FALSE,0);
  stack=gtk_stack_new();gtk_box_pack_start(GTK_BOX(root),stack,TRUE,TRUE,0);
  shelf=gtk_list_box_new();gtk_list_box_set_activate_on_single_click(GTK_LIST_BOX(shelf),TRUE);
  atk_object_set_name(gtk_widget_get_accessible(shelf),"Bookshelf");
#ifdef EXR_READER_PRODUCT_CATALOG
  GtkWidget *shelf_panel=gtk_box_new(GTK_ORIENTATION_VERTICAL,4);
  search=gtk_search_entry_new();gtk_entry_set_placeholder_text(GTK_ENTRY(search),"Search title or author (Ctrl+F)");
  gtk_entry_set_max_length(GTK_ENTRY(search),256);gtk_entry_set_text(GTK_ENTRY(search),shelf_query);
  atk_object_set_name(gtk_widget_get_accessible(search),"Search bookshelf");
  shelf_scroll=scroll(shelf);
#ifdef EXR_READER_DESKTOP_METADATA
  GtkWidget *shelf_actions=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,4);
  gtk_box_pack_start(GTK_BOX(shelf_actions),search,TRUE,TRUE,0);
  GtkWidget *edit=gtk_button_new_with_label("Details");
  gtk_widget_set_tooltip_text(edit,"Edit selected book (Ctrl+E)");
  atk_object_set_name(gtk_widget_get_accessible(edit),"Edit book details");
  gtk_box_pack_end(GTK_BOX(shelf_actions),edit,FALSE,FALSE,0);
  g_signal_connect(edit,"clicked",G_CALLBACK(metadata_edit),NULL);
  GtkWidget *more=gtk_menu_button_new();gtk_button_set_label(GTK_BUTTON(more),"_More");
  gtk_button_set_use_underline(GTK_BUTTON(more),TRUE);atk_object_set_name(gtk_widget_get_accessible(more),"More library actions");
  GtkWidget *menu=gtk_menu_new(),*organize=gtk_menu_item_new_with_label("Collections…");
  gtk_menu_shell_append(GTK_MENU_SHELL(menu),organize);g_signal_connect(organize,"activate",G_CALLBACK(collections_open),NULL);
#ifdef EXR_READER_ACCOUNT
  GtkWidget *account=gtk_menu_item_new_with_label("Account / Sync…");
  gtk_menu_shell_append(GTK_MENU_SHELL(menu),account);g_signal_connect(account,"activate",G_CALLBACK(accounts_open),NULL);
#endif
  gtk_widget_show_all(menu);gtk_menu_button_set_popup(GTK_MENU_BUTTON(more),menu);
  gtk_widget_set_tooltip_text(more,"Organize shelves, tags and series (Ctrl+Shift+C)");
  gtk_box_pack_end(GTK_BOX(shelf_actions),more,FALSE,FALSE,0);
  gtk_box_pack_start(GTK_BOX(shelf_panel),shelf_actions,FALSE,FALSE,0);
#else
  gtk_box_pack_start(GTK_BOX(shelf_panel),search,FALSE,FALSE,0);
#endif
  gtk_box_pack_start(GTK_BOX(shelf_panel),shelf_scroll,TRUE,TRUE,0);
  gtk_stack_add_named(GTK_STACK(stack),shelf_panel,"shelf");
  g_signal_connect(search,"changed",G_CALLBACK(shelf_search_changed),NULL);
  g_signal_connect(shelf,"row-selected",G_CALLBACK(shelf_selected),NULL);
  g_signal_connect(shelf,"size-allocate",G_CALLBACK(shelf_allocated),NULL);
  g_signal_connect(gtk_scrolled_window_get_vadjustment(GTK_SCROLLED_WINDOW(shelf_scroll)),"value-changed",G_CALLBACK(shelf_scrolled),NULL);
#else
  gtk_stack_add_named(GTK_STACK(stack),scroll(shelf),"shelf");
#endif
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
  g_signal_connect(gtk_widget_get_ancestor(image,GTK_TYPE_SCROLLED_WINDOW),"size-allocate",G_CALLBACK(page_allocated),NULL);
  g_signal_connect_after(image,"draw",G_CALLBACK(page_painted),NULL);
  gtk_widget_show_all(window);gtk_window_present(GTK_WINDOW(window));queue=g_async_queue_new();
  thread=g_thread_new("reading",work,font_path);submit(last ? READER_OPEN:READER_SHELF,last,NULL,font_size);
  state();gtk_main();g_thread_join(thread);g_async_queue_unref(queue);
#ifdef EXR_READER_ACCOUNT
  accounts_cleanup();
#endif
#ifdef EXR_READER_PRODUCT_CATALOG
  g_free(shelf_query);g_free(shelf_top_key);g_free(shelf_selected_key);g_free(restore_key);
#endif
#ifdef EXR_READER_DESKTOP_METADATA
  g_free(metadata_key);
#endif
  g_key_file_free(settings);g_free(home);g_free(settings_path);g_free(state_path);g_free(page_text);return 0;
}
