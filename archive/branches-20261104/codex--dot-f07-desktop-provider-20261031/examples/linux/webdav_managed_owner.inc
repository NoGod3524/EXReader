/* SPDX-License-Identifier: MIT */
/* GTK holds copied observations only. This worker never receives an SDK,
 * session, DAV, root, transaction or GTK handle. */
static struct {
  GThread *worker;
  gint done;
  guint timer;
  gboolean started,exit_wanted;
  char *profile;
  GtkWidget *badge,*dialog_badge,*retry;
  exr_webdav_managed_snapshot worker_view,view;
} managed_owner;
static char *managed_caption(void) {
  const exr_webdav_managed_snapshot *v=&managed_owner.view;
  if(managed_owner.worker||v->recovery_running)return g_strdup("Checking temporary downloads…");
  if(v->status==3)return g_strdup("Download cleanup is busy. Saved books remain available");
  if(v->status==7||v->receipt_uncertain)return g_strdup("Download cleanup records need attention. Saved files are kept");
  if(v->capacity_exhausted||v->status==5)return g_strdup("Temporary download capacity is exhausted. Saved books remain available");
  if(v->status)return g_strdup("Download cleanup could not start. Saved books remain available");
  if(v->cleanup_pending)return g_strdup_printf("Temporary downloads need cleanup (%u). Saved books remain available",v->cleanup_pending);
  return g_strdup("Temporary downloads are up to date");
}
static void managed_present(void) {
  char *caption=managed_caption();
  GtkWidget *labels[]={managed_owner.badge,managed_owner.dialog_badge};
  for(size_t i=0;i<G_N_ELEMENTS(labels);i++)if(labels[i]){
    gtk_label_set_text(GTK_LABEL(labels[i]),caption);
    atk_object_set_name(gtk_widget_get_accessible(labels[i]),caption);
  }
  g_free(caption);
}
static gpointer managed_recover_worker(gpointer unused) {
  (void)unused;
  exr_webdav_managed_recover_profile(managed_owner.profile,&managed_owner.worker_view);
  g_atomic_int_set(&managed_owner.done,1);return NULL;
}
static gboolean managed_reaped(gpointer unused) {
  (void)unused;
  if(!g_atomic_int_get(&managed_owner.done))return G_SOURCE_CONTINUE;
  g_thread_join(managed_owner.worker);managed_owner.worker=NULL;
  managed_owner.view=managed_owner.worker_view;managed_owner.timer=0;
  managed_present();state();
  if(managed_owner.exit_wanted){managed_owner.exit_wanted=FALSE;close_window(window,NULL,NULL);}
  return G_SOURCE_REMOVE;
}
static void managed_launch(void) {
  if(managed_owner.worker||closing||!profile_writable)return;
  managed_owner.started=TRUE;
  if(!managed_owner.profile)managed_owner.profile=g_canonicalize_filename(home,NULL);
  g_atomic_int_set(&managed_owner.done,0);
  managed_owner.worker=g_thread_new("download-cleanup",managed_recover_worker,NULL);
  managed_owner.timer=g_timeout_add(50,managed_reaped,NULL);managed_present();
}
static void managed_startup(void) { if(!managed_owner.started)managed_launch(); }
static gboolean managed_defer_exit(void) {
  if(!managed_owner.worker)return FALSE;
  managed_owner.exit_wanted=TRUE;return TRUE;
}
static char *managed_observation(void) {
  const exr_webdav_managed_snapshot *v=&managed_owner.view;
  GKeyFile *f=g_key_file_new();const char *g="managed";
  g_key_file_set_integer(f,g,"started",managed_owner.started);
  g_key_file_set_integer(f,g,"recovering",managed_owner.worker!=NULL||v->recovery_running);
  g_key_file_set_integer(f,g,"enabled",v->enabled);g_key_file_set_integer(f,g,"status",v->status);
  g_key_file_set_integer(f,g,"published",v->published);g_key_file_set_integer(f,g,"pending",v->cleanup_pending);
  g_key_file_set_integer(f,g,"uncertain",v->receipt_uncertain);g_key_file_set_integer(f,g,"native_error",v->native_error);
  g_key_file_set_integer(f,g,"exhausted",v->capacity_exhausted);g_key_file_set_integer(f,g,"roots",v->roots);
  g_key_file_set_integer(f,g,"cleaned",v->cleaned);
  char *caption=managed_caption();g_key_file_set_string(f,g,"notice",caption);g_free(caption);
  for(unsigned i=0;i<v->roots;i++){
    char group[32];g_snprintf(group,sizeof(group),"managed-root-%u",i);
    const exr_webdav_managed_root_snapshot *r=&v->root[i];
    g_key_file_set_string(f,group,"leaf",r->leaf);g_key_file_set_string(f,group,"uuid",r->uuid);
    g_key_file_set_integer(f,group,"slots",r->slots);g_key_file_set_integer(f,group,"pending",r->pending);
    g_key_file_set_integer(f,group,"status",r->status);g_key_file_set_integer(f,group,"uncertain",r->receipt_uncertain);
    g_key_file_set_integer(f,group,"unbound",r->unbound);
  }
  char *result=g_key_file_to_data(f,NULL,NULL);g_key_file_free(f);return result;
}
static void managed_shutdown(void) {
  if(managed_owner.timer)g_source_remove(managed_owner.timer);
  if(managed_owner.worker){g_thread_join(managed_owner.worker);managed_owner.worker=NULL;}
  g_free(managed_owner.profile);managed_owner.profile=NULL;
}
