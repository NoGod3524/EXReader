/* SPDX-License-Identifier: MIT */
/* Optional installed F3 settings. SDK work and atomic saves stay on the owner. */
static struct {
  GtkWidget *dialog,*content,*return_focus,*resume_focus,*message,*font,*line,*paragraph,*margin,*theme,*direction,*input,*zoom,*colors[4];
  GtkCssProvider *css;
  GDBusProxy *portal;
  GtkSettings *platform;
  gulong theme_watch,dark_watch;
  reader_preferences pending;
  reader_preferences_legacy legacy;
  char *path;
  gboolean running,awaiting_commit,want_close,exit_wanted,persist,cleaned;
  int load_status,save_status,portal_color;
  unsigned portal_events,portal_version;
  unsigned deferred_closes;
  unsigned actions;
  unsigned gesture_events,gesture_turns,press_frame;
  size_t bitmap_width,bitmap_height;
  double press_x,press_y;
  gboolean pressed;
} preferences;
static void preferences_style(void);
static void preferences_queue(const reader_preferences *,gboolean);
static gboolean preferences_opened(void) { return preferences.dialog!=NULL; }
static gboolean preferences_busy(void) { return preferences.running; }
static void preferences_notice(const char *value) {
  if(preferences.message) {
    atk_object_set_name(gtk_widget_get_accessible(preferences.message),value);
    gtk_label_set_text(GTK_LABEL(preferences.message),value);
  }
}
static void preferences_initialize(void) {
  appearance=reader_preferences_defaults();preferences.path=g_build_filename(home,"preferences.json",NULL);
  preferences.legacy.struct_size=sizeof(preferences.legacy);
  if(g_key_file_has_key(settings,"reader","font",NULL)) {
    preferences.legacy.present|=READER_PREFERENCES_LEGACY_FONT_SIZE;
    preferences.legacy.font_size=(float)g_key_file_get_integer(settings,"reader","font",NULL);
  }
  if(g_key_file_has_key(settings,"reader","zoom",NULL)) {
    preferences.legacy.present|=READER_PREFERENCES_LEGACY_FIXED_ZOOM;
    preferences.legacy.fixed_page_zoom=(uint32_t)g_key_file_get_integer(settings,"reader","zoom",NULL);
  }
  if(g_file_test(preferences.path,G_FILE_TEST_EXISTS)) {
    reader_preferences candidate=appearance;reader_preferences_error problem={0};
    preferences.load_status=reader_preferences_load(preferences.path,&candidate,NULL,&problem);
    if(preferences.load_status==READER_PREFERENCES_OK) {
      if(520-2*candidate.margin<candidate.font_size*1.5f || 640-2*candidate.margin<candidate.font_size*candidate.line_spacing)
        preferences.load_status=READER_PREFERENCES_RANGE;
      else appearance=candidate;
    }
  }
  font_size=(int)lroundf(appearance.font_size);zoom_percent=(int)appearance.fixed_page_zoom;
}
static void preferences_prepare(reader_command *command) {
  command->preferences_set=1;command->preferences=command->action==READER_SETTINGS ? preferences.pending:appearance;
  if(command->action==READER_FONT) command->preferences.font_size=(float)command->font;
  if(command->action==READER_ZOOM) command->preferences.fixed_page_zoom=(uint32_t)command->zoom;
  if(command->action==READER_SETTINGS) {
    command->font=(int)lroundf(command->preferences.font_size);command->zoom=(int)command->preferences.fixed_page_zoom;
  }
  if(command->action==READER_SETTINGS || command->action==READER_FONT || command->action==READER_ZOOM) {
    if(profile_writable && (command->action!=READER_SETTINGS || preferences.persist)) command->preferences_path=g_strdup(preferences.path);
    preferences.running=TRUE;preferences.awaiting_commit=FALSE;
    if(preferences.dialog) {
      g_clear_object(&preferences.resume_focus);GtkWidget *focus=gtk_window_get_focus(GTK_WINDOW(preferences.dialog));
      GtkWidget *combos[]={preferences.theme,preferences.direction,preferences.input};
      for(size_t i=0;focus && i<G_N_ELEMENTS(combos);i++)
        if(focus==combos[i] || gtk_widget_is_ancestor(focus,combos[i])) { focus=combos[i];break; }
      if(focus) preferences.resume_focus=g_object_ref(focus);
    }
  }
}
static void preferences_destroyed(GtkWidget *widget,gpointer unused) {
  (void)widget;(void)unused;preferences.dialog=preferences.message=NULL;
  if(preferences.content) gtk_widget_set_sensitive(preferences.content,TRUE);
  preferences.content=NULL;
  if(!closing && !preferences.exit_wanted) {
    gtk_window_present(GTK_WINDOW(window));
    if(preferences.return_focus && gtk_widget_get_toplevel(preferences.return_focus)==window &&
       gtk_widget_get_visible(preferences.return_focus) && gtk_widget_is_sensitive(preferences.return_focus))
      gtk_widget_grab_focus(preferences.return_focus);
    else gtk_widget_grab_focus(search);
  }
  g_clear_object(&preferences.return_focus);g_clear_object(&preferences.resume_focus);preferences.want_close=FALSE;state();
}
static void preferences_close(void) {
  if(preferences.running) { preferences.want_close=TRUE;preferences_notice("Finishing settings safely…");return; }
  if(preferences.dialog) gtk_widget_destroy(preferences.dialog);
}
static gboolean preferences_delete(GtkWidget *widget,GdkEvent *event,gpointer unused) {
  (void)widget;(void)event;(void)unused;preferences_close();return TRUE;
}
static void preferences_response(GtkDialog *dialog,int response,gpointer unused) {
  (void)dialog;(void)response;(void)unused;preferences_close();
}
static void preferences_exit(void) {
  preferences.exit_wanted=preferences.want_close=TRUE;close_after_save=TRUE;
  preferences.deferred_closes++;
  preferences_notice("Finishing settings before closing…");
  state();
}
static void preferences_result(const reader_result *result,reader_action action) {
  if(result->status==EXR_OK && result->has_preferences) {
    appearance=result->preferences;preferences_style();
    font_size=(int)lroundf(appearance.font_size);zoom_percent=(int)appearance.fixed_page_zoom;
    if((action==READER_SETTINGS && preferences.persist) || action==READER_FONT || action==READER_ZOOM)
      preferences.load_status=READER_PREFERENCES_OK;
  }
  if(result->status==EXR_OK && result->has_frame) { preferences.bitmap_width=result->width;preferences.bitmap_height=result->height; }
  if(action==READER_SETTINGS || action==READER_FONT || action==READER_ZOOM) {
    preferences.save_status=(int)result->status;
    preferences.awaiting_commit=result->status==EXR_OK && result->has_frame;
    preferences.running=preferences.awaiting_commit;
    preferences_notice(result->status==EXR_OK ? "Settings applied":"Settings could not be saved or applied; previous settings retained");
  } else if(action==READER_COMMIT && preferences.awaiting_commit) {
    preferences.running=preferences.awaiting_commit=FALSE;
    if(result->status!=EXR_OK) preferences_notice("Position save failed. Close settings and press F12 to retry");
  }
  if(!preferences.running) {
    if(preferences.dialog) {
      gtk_widget_set_sensitive(gtk_dialog_get_content_area(GTK_DIALOG(preferences.dialog)),TRUE);
      if(preferences.resume_focus && gtk_widget_get_toplevel(preferences.resume_focus)==preferences.dialog)
        gtk_widget_grab_focus(preferences.resume_focus);
      g_clear_object(&preferences.resume_focus);
    }
    if(preferences.want_close) preferences_close();
    if(preferences.exit_wanted && !busy && !saving && !closing) {
      preferences.exit_wanted=FALSE;close_window(window,NULL,NULL);
    }
  }
  state();
}
static void preferences_queue(const reader_preferences *candidate,gboolean persist) {
  if(closing || busy || saving || save_failed || preferences.running || !profile_writable) return;
  preferences.pending=*candidate;preferences.persist=persist;
  submit(READER_SETTINGS,book_id,NULL,(int)lroundf(candidate->font_size));
  if(preferences.running && preferences.dialog)
    gtk_widget_set_sensitive(gtk_dialog_get_content_area(GTK_DIALOG(preferences.dialog)),FALSE);
}
static void preferences_adjust(gboolean increase) {
  reader_preferences candidate=appearance;
  if(fixed) {
    int zoom=(int)candidate.fixed_page_zoom+(increase ? 25:-25);
    if(zoom<25 || zoom>400) { status(EXR_ARGUMENT,"Zoom must be between 25 and 400 percent");return; }
    candidate.fixed_page_zoom=(uint32_t)zoom;
  } else candidate.font_size+=increase ? 2.0f:-2.0f;
  preferences_queue(&candidate,TRUE);
}
static void preferences_style(void) {
  if(!window) return;
  int dark=reader_preferences_effective_theme(&appearance,(reader_preferences_theme)appearance_system_theme)==READER_PREFERENCES_THEME_DARK;
  const uint8_t *fg=dark ? appearance.dark_foreground:appearance.light_foreground,*bg=dark ? appearance.dark_background:appearance.light_background;
  char css[512],foreground_alpha[32],background_alpha[32];
  g_ascii_formatd(foreground_alpha,sizeof(foreground_alpha),"%.3f",fg[3]/255.0);
  g_ascii_formatd(background_alpha,sizeof(background_alpha),"%.3f",bg[3]/255.0);
  g_snprintf(css,sizeof(css),
    ".exreader-appearance,.exreader-appearance textview text,.exreader-appearance entry{color:rgba(%u,%u,%u,%s);background-color:rgba(%u,%u,%u,%s);}",
    fg[0],fg[1],fg[2],foreground_alpha,bg[0],bg[1],bg[2],background_alpha);
  if(!preferences.css) {
    preferences.css=gtk_css_provider_new();gtk_style_context_add_provider_for_screen(gdk_screen_get_default(),GTK_STYLE_PROVIDER(preferences.css),GTK_STYLE_PROVIDER_PRIORITY_APPLICATION+1);
  }
  gtk_css_provider_load_from_data(preferences.css,css,-1,NULL);
  gtk_style_context_add_class(gtk_widget_get_style_context(window),"exreader-appearance");
}
static void preferences_platform_update(void) {
  if(preferences.cleaned) return;
  guint value=READER_PREFERENCES_THEME_LIGHT;
  if(preferences.portal_color==1) value=READER_PREFERENCES_THEME_DARK;
  else if(preferences.portal_color!=2 && preferences.platform) {
    gboolean dark=FALSE;char *name=NULL;
    g_object_get(preferences.platform,"gtk-application-prefer-dark-theme",&dark,"gtk-theme-name",&name,NULL);
    if(dark || (name && (g_str_has_suffix(name,"-dark") || g_str_has_suffix(name,":dark")))) value=READER_PREFERENCES_THEME_DARK;
    g_free(name);
  }
  if(value!=appearance_system_theme) {
    appearance_system_theme=value;
    if(appearance.theme==READER_PREFERENCES_THEME_SYSTEM) preferences_style();
    state();
  }
}
static void preferences_gtk_theme(GObject *object,GParamSpec *property,gpointer unused) {
  (void)object;(void)property;(void)unused;preferences_platform_update();
}
static void preferences_portal_value(GVariant *value) {
  while(g_variant_is_of_type(value,G_VARIANT_TYPE_VARIANT)) {
    GVariant *inner=g_variant_get_variant(value);g_variant_unref(value);value=inner;
  }
  if(g_variant_is_of_type(value,G_VARIANT_TYPE_UINT32)) {
    guint scheme=g_variant_get_uint32(value);preferences.portal_color=scheme<=2 ? (int)scheme:0;preferences.portal_events++;
  }
  g_variant_unref(value);preferences_platform_update();
}
static void preferences_portal_signal(GDBusProxy *proxy,gchar *sender,gchar *signal,GVariant *parameters,gpointer unused) {
  (void)proxy;(void)sender;(void)unused;
  if(!strcmp(signal,"SettingChanged") && g_variant_is_of_type(parameters,G_VARIANT_TYPE("(ssv)"))) {
    const char *space,*key;GVariant *value=NULL;g_variant_get(parameters,"(&s&sv)",&space,&key,&value);
    if(!strcmp(space,"org.freedesktop.appearance") && !strcmp(key,"color-scheme")) preferences_portal_value(value);
    else g_variant_unref(value);
  }
}
static void preferences_portal_read(GObject *object,GAsyncResult *result,gpointer unused) {
  (void)unused;GError *problem=NULL;GVariant *reply=g_dbus_proxy_call_finish(G_DBUS_PROXY(object),result,&problem);
  if(reply) { if(g_variant_is_of_type(reply,G_VARIANT_TYPE("(v)"))) preferences_portal_value(g_variant_get_child_value(reply,0));g_variant_unref(reply); }
  g_clear_error(&problem);
}
static void preferences_portal_ready(GObject *object,GAsyncResult *result,gpointer unused) {
  (void)object;(void)unused;GError *problem=NULL;GDBusProxy *proxy=g_dbus_proxy_new_for_bus_finish(result,&problem);g_clear_error(&problem);
  if(preferences.cleaned) { g_clear_object(&proxy);return; }
  preferences.portal=proxy;if(!proxy) return;
  GVariant *version=g_dbus_proxy_get_cached_property(proxy,"version");
  if(version) { if(g_variant_is_of_type(version,G_VARIANT_TYPE_UINT32)) preferences.portal_version=g_variant_get_uint32(version);g_variant_unref(version); }
  g_signal_connect(proxy,"g-signal",G_CALLBACK(preferences_portal_signal),NULL);
  g_dbus_proxy_call(proxy,"Read",g_variant_new("(ss)","org.freedesktop.appearance","color-scheme"),G_DBUS_CALL_FLAGS_NONE,1500,NULL,preferences_portal_read,NULL);
}
static void preferences_platform_start(void) {
  preferences.platform=gtk_settings_get_default();
  preferences.theme_watch=g_signal_connect(preferences.platform,"notify::gtk-theme-name",G_CALLBACK(preferences_gtk_theme),NULL);
  preferences.dark_watch=g_signal_connect(preferences.platform,"notify::gtk-application-prefer-dark-theme",G_CALLBACK(preferences_gtk_theme),NULL);
  preferences_platform_update();
  g_dbus_proxy_new_for_bus(G_BUS_TYPE_SESSION,G_DBUS_PROXY_FLAGS_NONE,NULL,"org.freedesktop.portal.Desktop",
    "/org/freedesktop/portal/desktop","org.freedesktop.portal.Settings",NULL,preferences_portal_ready,NULL);
}
static void preferences_combo_focus(GtkWidget *widget,gpointer unused) {
  (void)unused;GTK_WIDGET_CLASS(g_type_class_peek(GTK_TYPE_WIDGET))->grab_focus(widget);g_signal_stop_emission_by_name(widget,"grab-focus");
}
static GtkWidget *preferences_field(GtkWidget *grid,int row,const char *name,GtkWidget *widget) {
  GtkWidget *caption=gtk_label_new(name);gtk_label_set_xalign(GTK_LABEL(caption),0);
  gtk_label_set_mnemonic_widget(GTK_LABEL(caption),widget);
  gtk_grid_attach(GTK_GRID(grid),caption,0,row,1,1);gtk_grid_attach(GTK_GRID(grid),widget,1,row,1,1);
  atk_object_set_name(gtk_widget_get_accessible(widget),name);gtk_widget_set_hexpand(widget,TRUE);return widget;
}
static GtkWidget *preferences_spin(GtkWidget *grid,int row,const char *name,double minimum,double maximum,double step) {
  GtkWidget *widget=gtk_spin_button_new_with_range(minimum,maximum,step);gtk_spin_button_set_digits(GTK_SPIN_BUTTON(widget),2);
  return preferences_field(grid,row,name,widget);
}
static GtkWidget *preferences_combo(GtkWidget *grid,int row,const char *name,const char *const *names,size_t count) {
  GtkWidget *widget=gtk_combo_box_text_new();for(size_t i=0;i<count;i++) gtk_combo_box_text_append_text(GTK_COMBO_BOX_TEXT(widget),names[i]);
  gtk_widget_set_can_focus(widget,TRUE);g_signal_connect(widget,"grab-focus",G_CALLBACK(preferences_combo_focus),NULL);
  return preferences_field(grid,row,name,widget);
}
static void preferences_fill(const reader_preferences *p) {
  gtk_spin_button_set_value(GTK_SPIN_BUTTON(preferences.font),p->font_size);gtk_spin_button_set_value(GTK_SPIN_BUTTON(preferences.line),p->line_spacing);
  gtk_spin_button_set_value(GTK_SPIN_BUTTON(preferences.paragraph),p->paragraph_spacing);gtk_spin_button_set_value(GTK_SPIN_BUTTON(preferences.margin),p->margin);
  gtk_combo_box_set_active(GTK_COMBO_BOX(preferences.theme),(int)p->theme-1);gtk_combo_box_set_active(GTK_COMBO_BOX(preferences.direction),(int)p->page_turn_direction-1);
  gtk_combo_box_set_active(GTK_COMBO_BOX(preferences.input),(int)p->page_turn_input-1);gtk_spin_button_set_value(GTK_SPIN_BUTTON(preferences.zoom),p->fixed_page_zoom);
  const uint8_t *colors[]={p->light_foreground,p->light_background,p->dark_foreground,p->dark_background};
  for(size_t i=0;i<4;i++) { char color[10];g_snprintf(color,sizeof(color),"#%02X%02X%02X%02X",colors[i][0],colors[i][1],colors[i][2],colors[i][3]);gtk_entry_set_text(GTK_ENTRY(preferences.colors[i]),color); }
}
static void preferences_save(GtkWidget *button,gpointer unused) {
  (void)button;(void)unused;if(preferences.running) return;
  preferences.actions++;
  GtkWidget *numbers[]={preferences.font,preferences.line,preferences.paragraph,preferences.margin,preferences.zoom};
  for(size_t i=0;i<G_N_ELEMENTS(numbers);i++) gtk_spin_button_update(GTK_SPIN_BUTTON(numbers[i]));
  reader_preferences p=appearance;p.font_size=(float)gtk_spin_button_get_value(GTK_SPIN_BUTTON(preferences.font));
  p.line_spacing=(float)gtk_spin_button_get_value(GTK_SPIN_BUTTON(preferences.line));p.paragraph_spacing=(float)gtk_spin_button_get_value(GTK_SPIN_BUTTON(preferences.paragraph));
  p.margin=(float)gtk_spin_button_get_value(GTK_SPIN_BUTTON(preferences.margin));p.theme=(uint32_t)gtk_combo_box_get_active(GTK_COMBO_BOX(preferences.theme))+1;
  p.page_turn_direction=(uint32_t)gtk_combo_box_get_active(GTK_COMBO_BOX(preferences.direction))+1;p.page_turn_input=(uint32_t)gtk_combo_box_get_active(GTK_COMBO_BOX(preferences.input))+1;
  p.fixed_page_zoom=(uint32_t)gtk_spin_button_get_value_as_int(GTK_SPIN_BUTTON(preferences.zoom));
  uint8_t *colors[]={p.light_foreground,p.light_background,p.dark_foreground,p.dark_background};
  for(size_t i=0;i<4;i++) {
    const char *value=gtk_entry_get_text(GTK_ENTRY(preferences.colors[i]));size_t length=strlen(value);
    if((length!=7 && length!=9) || value[0]!='#') { preferences_notice("Use #RRGGBB or #RRGGBBAA colors");state();return; }
    for(size_t j=1;j<length;j++) if(g_ascii_xdigit_value(value[j])<0) { preferences_notice("Use hexadecimal colors");state();return; }
    for(size_t j=0;j<4;j++) colors[i][j]=j==3 && length==7 ? 255:(uint8_t)(16*g_ascii_xdigit_value(value[1+2*j])+g_ascii_xdigit_value(value[2+2*j]));
  }
  preferences_queue(&p,TRUE);
}
static void preferences_defaults(GtkWidget *button,gpointer unused) {
  (void)button;(void)unused;reader_preferences p=reader_preferences_defaults();preferences_fill(&p);preferences_notice("Defaults shown. Save to apply them");preferences.actions++;state();
}
static void preferences_reload(GtkWidget *button,gpointer unused) {
  (void)button;(void)unused;reader_preferences p=appearance;reader_preferences_error problem={0};
  preferences.actions++;
  preferences.load_status=reader_preferences_load(preferences.path,&p,NULL,&problem);
  if(preferences.load_status!=READER_PREFERENCES_OK) { preferences_notice("Settings file could not be loaded; current valid settings retained");state();return; }
  preferences_fill(&p);preferences_queue(&p,FALSE);
}
static void preferences_import(GtkWidget *button,gpointer unused) {
  (void)button;(void)unused;reader_preferences p=appearance;reader_preferences_error problem={0};
  preferences.actions++;
  if(!preferences.legacy.present) { preferences_notice("No old appearance settings were found");state();return; }
  if(reader_preferences_import_legacy(&p,&preferences.legacy,NULL,&problem)!=READER_PREFERENCES_OK) { preferences_notice("Old appearance values were invalid; current settings retained");state();return; }
  preferences_fill(&p);preferences_notice("Old font and zoom shown. Save to apply this explicit import");state();
}
static void preferences_open(GtkWidget *button,gpointer unused) {
  (void)button;(void)unused;
  if(closing || busy || saving || save_failed || preferences.dialog || !profile_writable) return;
#ifdef EXR_READER_DESKTOP_METADATA
  if(metadata_running || metadata_dialog || collections_opened()) return;
#endif
#ifdef EXR_READER_ACCOUNT
  if(accounts_opened()) return;
#endif
  preferences.want_close=preferences.exit_wanted=FALSE;
  GtkWidget *focus=gtk_window_get_focus(GTK_WINDOW(window));if(focus) preferences.return_focus=g_object_ref(focus);
  preferences.content=gtk_bin_get_child(GTK_BIN(window));gtk_widget_set_sensitive(preferences.content,FALSE);
  preferences.dialog=gtk_dialog_new_with_buttons("Reading settings",GTK_WINDOW(window),GTK_DIALOG_MODAL|GTK_DIALOG_DESTROY_WITH_PARENT,"_Close",GTK_RESPONSE_CLOSE,NULL);
  GtkWindowGroup *group=gtk_window_group_new();gtk_window_group_add_window(group,GTK_WINDOW(preferences.dialog));g_object_unref(group);
  gtk_style_context_add_class(gtk_widget_get_style_context(preferences.dialog),"exreader-appearance");
  GtkWidget *area=gtk_dialog_get_content_area(GTK_DIALOG(preferences.dialog)),*grid=gtk_grid_new();gtk_container_set_border_width(GTK_CONTAINER(area),16);
  gtk_grid_set_column_spacing(GTK_GRID(grid),18);gtk_grid_set_row_spacing(GTK_GRID(grid),6);gtk_box_pack_start(GTK_BOX(area),grid,TRUE,TRUE,0);
  preferences.font=preferences_spin(grid,0,"Font size",4,256,.5);preferences.line=preferences_spin(grid,1,"Line spacing",1,5,.1);
  preferences.paragraph=preferences_spin(grid,2,"Paragraph spacing",0,1024,1);preferences.margin=preferences_spin(grid,3,"Page margin",0,1024,1);
  const char *themes[]={"Light","Dark","System"},*directions[]={"Left to right","Right to left","Vertical"},*inputs[]={"Tap","Swipe","Tap and swipe","Hardware keys"};
  preferences.theme=preferences_combo(grid,4,"Theme",themes,3);preferences.direction=preferences_combo(grid,5,"Page turn direction",directions,3);
  preferences.input=preferences_combo(grid,6,"Page turn input",inputs,4);preferences.zoom=preferences_spin(grid,7,"Fixed page zoom",25,400,25);gtk_spin_button_set_digits(GTK_SPIN_BUTTON(preferences.zoom),0);
  const char *colors[]={"Light foreground","Light background","Dark foreground","Dark background"};
  for(size_t i=0;i<4;i++) { preferences.colors[i]=preferences_field(grid,8+(int)i,colors[i],gtk_entry_new());gtk_entry_set_max_length(GTK_ENTRY(preferences.colors[i]),9); }
  GtkWidget *notice=gtk_label_new("Theme changes the interface. Reading pages stay light; page themes are not available yet. Fixed pages keep their original colors.");
  gtk_label_set_line_wrap(GTK_LABEL(notice),TRUE);gtk_box_pack_start(GTK_BOX(area),notice,FALSE,FALSE,8);
  GtkWidget *actions=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,8);gtk_box_pack_start(GTK_BOX(area),actions,FALSE,FALSE,6);
  const char *names[]={"_Defaults","_Reload","_Import old appearance","_Save"};GCallback callbacks[]={G_CALLBACK(preferences_defaults),G_CALLBACK(preferences_reload),G_CALLBACK(preferences_import),G_CALLBACK(preferences_save)};
  for(size_t i=0;i<4;i++) { GtkWidget *item=gtk_button_new_with_mnemonic(names[i]);gtk_box_pack_start(GTK_BOX(actions),item,FALSE,FALSE,0);g_signal_connect(item,"clicked",callbacks[i],NULL); }
  preferences.message=gtk_label_new(preferences.load_status ? "A settings file could not be loaded. Current valid values were retained":"Changes apply only when you save");
  gtk_label_set_line_wrap(GTK_LABEL(preferences.message),TRUE);gtk_box_pack_start(GTK_BOX(area),preferences.message,FALSE,FALSE,6);preferences_fill(&appearance);
  g_signal_connect(preferences.dialog,"destroy",G_CALLBACK(preferences_destroyed),NULL);g_signal_connect(preferences.dialog,"delete-event",G_CALLBACK(preferences_delete),NULL);
  g_signal_connect(preferences.dialog,"response",G_CALLBACK(preferences_response),NULL);gtk_widget_show_all(preferences.dialog);gtk_widget_grab_focus(preferences.font);state();
}
static gboolean preferences_turn_key(GdkEventKey *event) {
  if(appearance.page_turn_input!=READER_PREFERENCES_INPUT_HARDWARE_KEYS || !book_id || busy || saving ||
     strcmp(gtk_stack_get_visible_child_name(GTK_STACK(stack)),"reader") || (event->state&(GDK_CONTROL_MASK|GDK_MOD1_MASK|GDK_SUPER_MASK))) return FALSE;
  GtkWidget *focus=gtk_window_get_focus(GTK_WINDOW(window));if(GTK_IS_ENTRY(focus) || GTK_IS_TEXT_VIEW(focus)) return FALSE;
  int next=-1;
  if(event->keyval==GDK_KEY_Page_Down) next=1;else if(event->keyval==GDK_KEY_Page_Up) next=0;
  else if(appearance.page_turn_direction==READER_PREFERENCES_TURN_VERTICAL) {
    if(event->keyval==GDK_KEY_Down) next=1;else if(event->keyval==GDK_KEY_Up) next=0;
  } else if(event->keyval==GDK_KEY_Right) next=appearance.page_turn_direction==READER_PREFERENCES_TURN_LTR;
  else if(event->keyval==GDK_KEY_Left) next=appearance.page_turn_direction==READER_PREFERENCES_TURN_RTL;
  if(next<0) return FALSE;
  submit(next ? READER_NEXT:READER_PREVIOUS,book_id,NULL,font_size);return TRUE;
}
static gboolean preferences_page_press(GtkWidget *widget,GdkEventButton *event,gpointer unused) {
  (void)widget;(void)unused;preferences.pressed=event->button==1 && !preferences_opened() && !busy && !saving;
  preferences.press_x=event->x;preferences.press_y=event->y;preferences.press_frame=frame_generation;return preferences.pressed;
}
static gboolean preferences_page_release(GtkWidget *widget,GdkEventButton *event,gpointer unused) {
  (void)unused;if(!preferences.pressed || event->button!=1) return FALSE;preferences.pressed=FALSE;preferences.gesture_events++;
  if(!book_id || busy || saving || preferences_opened() || preferences.press_frame!=frame_generation ||
     strcmp(gtk_stack_get_visible_child_name(GTK_STACK(stack)),"reader")) { state();return TRUE; }
  double dx=event->x-preferences.press_x,dy=event->y-preferences.press_y;
  int input=(int)appearance.page_turn_input,next=-1,vertical=appearance.page_turn_direction==READER_PREFERENCES_TURN_VERTICAL;
  double delta=vertical ? dy:dx;
  if((input==READER_PREFERENCES_INPUT_SWIPE || input==READER_PREFERENCES_INPUT_TAP_AND_SWIPE) && fabs(delta)>=40)
    next=appearance.page_turn_direction==READER_PREFERENCES_TURN_RTL ? delta>0:delta<0;
  else if((input==READER_PREFERENCES_INPUT_TAP || input==READER_PREFERENCES_INPUT_TAP_AND_SWIPE) && hypot(dx,dy)<=12) {
    next=vertical ? event->y>=gtk_widget_get_allocated_height(widget)/2.0:event->x>=gtk_widget_get_allocated_width(widget)/2.0;
    if(appearance.page_turn_direction==READER_PREFERENCES_TURN_RTL) next=!next;
  }
  if(next>=0) { preferences.gesture_turns++;submit(next ? READER_NEXT:READER_PREVIOUS,book_id,NULL,font_size); }
  else state();
  return TRUE;
}
static char *preferences_observation(void) {
  char *selected=preferences_import_dialog ? gtk_file_chooser_get_filename(GTK_FILE_CHOOSER(preferences_import_dialog)):NULL;
  char *digest=selected ? g_compute_checksum_for_string(G_CHECKSUM_SHA256,selected,-1):g_strdup("");
  GtkWidget *accept=preferences_import_dialog ? gtk_dialog_get_widget_for_response(GTK_DIALOG(preferences_import_dialog),GTK_RESPONSE_ACCEPT):NULL;
  GtkWidget *focus=preferences_import_dialog ? gtk_window_get_focus(GTK_WINDOW(preferences_import_dialog)):NULL;
  char *entry_digest=GTK_IS_ENTRY(focus) ? g_compute_checksum_for_string(G_CHECKSUM_SHA256,gtk_entry_get_text(GTK_ENTRY(focus)),-1):g_strdup("");
  char *value=g_strdup_printf("[preferences]\nvisible=%d\nrunning=%d\nload_status=%d\nsave_status=%d\nfont=%.3f\nline=%.3f\nparagraph=%.3f\nmargin=%.3f\ntheme=%u\nsystem_theme=%u\neffective_theme=%u\ndirection=%u\ninput=%u\nzoom=%u\nportal_version=%u\nportal_events=%u\nbitmap_width=%zu\nbitmap_height=%zu\ndeferred_closes=%u\nactions=%u\ngesture_events=%u\ngesture_turns=%u\n[native_import]\nvisible=%d\nselected_sha256=%s\naccept_sensitive=%d\nactive=%d\nentry_focused=%d\nentry_sha256=%s\nfocus_type=%s\n",
    preferences.dialog!=NULL,preferences.running,preferences.load_status,preferences.save_status,(double)appearance.font_size,(double)appearance.line_spacing,
    (double)appearance.paragraph_spacing,(double)appearance.margin,appearance.theme,appearance_system_theme,
    (unsigned)reader_preferences_effective_theme(&appearance,(reader_preferences_theme)appearance_system_theme),appearance.page_turn_direction,appearance.page_turn_input,appearance.fixed_page_zoom,preferences.portal_version,preferences.portal_events,
    preferences.bitmap_width,preferences.bitmap_height,preferences.deferred_closes,preferences.actions,preferences.gesture_events,preferences.gesture_turns,
    preferences_import_dialog && gtk_widget_get_mapped(preferences_import_dialog),digest,accept && gtk_widget_is_sensitive(accept),
    preferences_import_dialog && gtk_window_is_active(GTK_WINDOW(preferences_import_dialog)),GTK_IS_ENTRY(focus),entry_digest,focus ? G_OBJECT_TYPE_NAME(focus):"");
  g_free(entry_digest);g_free(digest);g_free(selected);return value;
}
static void preferences_import_changed(GtkFileChooser *chooser,gpointer unused) {
  (void)chooser;(void)unused;state();
}
static gboolean preferences_import_mapped(GtkWidget *widget,GdkEventAny *event,gpointer unused) {
  (void)widget;(void)event;(void)unused;state();return FALSE;
}
static void preferences_import_entry(GtkEditable *entry,gpointer unused) { (void)entry;(void)unused;state(); }
static void preferences_import_focus(GtkWindow *dialog,GtkWidget *focus,gpointer unused) {
  (void)dialog;(void)unused;
  if(GTK_IS_ENTRY(focus) && !g_object_get_data(G_OBJECT(focus),"import-entry-observed")) {
    g_object_set_data(G_OBJECT(focus),"import-entry-observed",GINT_TO_POINTER(1));
    g_signal_connect(focus,"changed",G_CALLBACK(preferences_import_entry),NULL);
  }
  state();
}
static void preferences_import_activity(GObject *object,GParamSpec *property,gpointer unused) {
  (void)object;(void)property;(void)unused;state();
}
static void preferences_cleanup(void) {
  preferences.cleaned=TRUE;
  if(preferences.platform) { g_signal_handler_disconnect(preferences.platform,preferences.theme_watch);g_signal_handler_disconnect(preferences.platform,preferences.dark_watch); }
  g_clear_object(&preferences.portal);g_clear_object(&preferences.css);g_clear_object(&preferences.return_focus);g_clear_object(&preferences.resume_focus);g_free(preferences.path);
}
