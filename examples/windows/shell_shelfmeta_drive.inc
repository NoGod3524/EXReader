/* SPDX-License-Identifier: MIT */
/* Shelf-metadata acceptance actions. Clicks go through the production hit
   map / dialog commands; only the clock and the foreground flag are injected
   (offscreen windows are never foreground). */
static int sm_drive_book(const char *needle) {
  for(size_t s=0;s<g.shelf_count;s++) if(g.shelf[s].title && strstr(g.shelf[s].title,needle))return (int)s;
  return -1;
}
static int sm_drive_click(int kind,int arg,int right) {
  RedrawWindow(sm_view,NULL,NULL,RDW_INVALIDATE|RDW_UPDATENOW);
  for(int i=0;i<sm_hit_count;i++) if(sm_hits[i].kind==kind && sm_hits[i].arg==arg) {
    RECT r=sm_hits[i].r;int x=(r.left+r.right)/2,y=(r.top+r.bottom)/2;
    if(right)return 0; /* TrackPopupMenu is modal; menu commands use sm_context */
    SendMessageW(sm_view,WM_LBUTTONDOWN,MK_LBUTTON,MAKELPARAM(x,y));SendMessageW(sm_view,WM_LBUTTONUP,0,MAKELPARAM(x,y));
    return 1;
  }
  return 0;
}
static int sm_drive_dump(const char *name) {
  sm_collect_tags();cv_text j={0};
  wchar_t *path=sm_path;char *upath=host_utf8(path);
  cv_text_string(&j,"{\"shelf_path\":");cv_text_json(&j,upath ? upath:"");free(upath);
  cv_text_format(&j,",\"writable\":%d,\"saves\":%d,\"save_failures\":%d,\"view\":\"%s\",\"mode\":%d,\"filter\":%d,\"visible\":%d,\"edit_open\":%d,",
    sm_writable,sm_saves,sm_save_failures,sm_list ? "list":"grid",sm_mode,sm_filter,sm_view && IsWindowVisible(sm_view),
    sm_edit_panel && IsWindowVisible(sm_edit_panel));
  SCROLLINFO scroll={.cbSize=sizeof(scroll),.fMask=SIF_ALL};GetScrollInfo(sm_view,SB_VERT,&scroll);
  cv_text_format(&j,"\"scroll\":%d,\"scroll_max\":%d,\"scroll_page\":%u,",sm_scroll,scroll.nMax,scroll.nPage);
  char today[11];sm_date(sm_now(),today);
  uint64_t total=0;for(int i=0;i<sm_count;i++)total+=sm_entries[i].read_ms;
  cv_text_format(&j,"\"today\":\"%s\",\"streak\":%llu,\"total_read_ms\":%llu,\"days\":[",today,(unsigned long long)sm_streak(),(unsigned long long)total);
  for(int i=0;i<sm_day_count;i++)cv_text_format(&j,"%s[\"%s\",%llu]",i ? ",":"",sm_days[i].date,(unsigned long long)sm_days[i].ms);
  cv_text_string(&j,"],\"tags\":[");
  for(int t=0;t<sm_tag_total;t++) {
    int n=0;for(size_t s=0;s<g.shelf_count;s++)n+=g.shelf[s].id>0 && sm_has_tag(sm_book_entry(s),sm_tags[t]);
    cv_text_string(&j,t ? ",[":"[");cv_text_json(&j,sm_tags[t]);cv_text_format(&j,",%d]",n);
  }
  int saved=sm_filter,order[1024],n;
  sm_filter=-1;n=sm_order(order);
  cv_text_string(&j,"],\"order\":[");
  for(int i=0;i<n;i++) {
    int s=order[i],e=sm_book_entry((size_t)s);sm_entry *x=e>=0 ? &sm_entries[e]:NULL;
    sm_cover_cache *c=sm_cover(e);
    if(i)cv_text_string(&j,",\n");
    cv_text_format(&j,"{\"shelf\":%d,\"id\":%lld,",s,(long long)g.shelf[s].id);
    annot_json_string(&j,"library_title",g.shelf[s].title);cv_text_string(&j,",");
    annot_json_string(&j,"title",sm_title((size_t)s));cv_text_string(&j,",");annot_json_string(&j,"author",sm_author((size_t)s));
    cv_text_string(&j,",");annot_json_string(&j,"series",x ? x->series:NULL);
    cv_text_string(&j,",\"series_index\":");if(x && x->has_index)cv_text_format(&j,"%g",x->series_index);else cv_text_string(&j,"null");
    cv_text_string(&j,",\"tags\":[");for(int t=0;x && t<x->tag_count;t++){if(t)cv_text_string(&j,",");cv_text_json(&j,x->tags[t]);}
    cv_text_string(&j,"],");annot_json_string(&j,"cover",x ? x->cover:NULL);
    cv_text_format(&j,",\"cover_decoded\":[%d,%d],\"sha256\":\"%s\",\"read_ms\":%llu,\"opens\":%llu,\"last_read_ms\":%llu,\"page_turns\":%llu,\"page\":%llu,\"page_count\":%llu,\"part\":%llu,\"part_count\":%llu,\"progress\":%.4f}",
      c ? c->w:0,c ? c->h:0,x ? x->sha:"",x ? (unsigned long long)x->read_ms:0ULL,x ? (unsigned long long)x->opens:0ULL,x ? (unsigned long long)x->last_ms:0ULL,
      x ? (unsigned long long)x->turns:0ULL,x ? (unsigned long long)x->page:0ULL,x ? (unsigned long long)x->page_count:0ULL,
      x ? (unsigned long long)x->part:0ULL,x ? (unsigned long long)x->part_count:0ULL,x ? x->progress:0.0);
  }
  cv_text_string(&j,"],\"filters\":{");
  sm_filter=-2;cv_text_format(&j,"\"(untagged)\":%d",sm_order(order));
  for(int t=0;t<sm_tag_total;t++){sm_filter=t;cv_text_string(&j,",");cv_text_json(&j,sm_tags[t]);cv_text_format(&j,":%d",sm_order(order));}
  sm_filter=-1;cv_text_format(&j,",\"(all)\":%d}}\n",sm_order(order));
  sm_filter=saved;
  int ok=!j.failed && select_drive_write(name,".shelf.json",j.data,j.size);cv_text_free(&j);return ok;
}
static int sm_drive(const char *action) {
  if(!strcmp(action,"sm_show")){sm_show(atoi(drive_args[1]));return IsWindowVisible(sm_view)!=0 || shelf_exit_pending;}
  if(!strcmp(action,"sm_hide")){sm_hide();return !IsWindowVisible(sm_view);}
  if(!strcmp(action,"sm_scroll")) {
    SendMessageW(sm_view,WM_VSCROLL,atoi(drive_args[1]) ? SB_BOTTOM:SB_TOP,0);UpdateWindow(sm_view);return 1;
  }
  if(!strcmp(action,"sm_dump"))return sm_drive_dump(drive_args[1]);
  if(!strcmp(action,"sm_click")) {
    const char *k=drive_args[1];
    if(!strcmp(k,"grid"))return sm_drive_click(SM_HIT_GRID,0,0);
    if(!strcmp(k,"list"))return sm_drive_click(SM_HIT_LIST,0,0);
    if(!strcmp(k,"stats"))return sm_drive_click(SM_HIT_STATS,0,0);
    if(!strcmp(k,"shelf"))return sm_drive_click(SM_HIT_SHELF,0,0);
    if(!strcmp(k,"back"))return sm_drive_click(SM_HIT_BACK,0,0);
    if(!strcmp(k,"all"))return sm_drive_click(SM_HIT_TAG,-1,0);
    if(!strcmp(k,"untagged"))return sm_drive_click(SM_HIT_TAG,-2,0);
    if(!strcmp(k,"tag")) {
      sm_collect_tags();
      for(int t=0;t<sm_tag_total;t++) if(!strcmp(sm_tags[t],drive_args[2]))return sm_drive_click(SM_HIT_TAG,t,0) && sm_filter==t;
      return 0;
    }
    if(!strcmp(k,"book"))return sm_drive_click(SM_HIT_BOOK,sm_drive_book(drive_args[2]),0);
    return 0;
  }
  if(!strcmp(action,"sm_context")) {
    int s=sm_drive_book(drive_args[1]);if(s<0)return 0;
    sm_context(s,!strcmp(drive_args[2],"open") ? 1:2);
    return !strcmp(drive_args[2],"open") || (sm_edit_panel && IsWindowVisible(sm_edit_panel));
  }
  if(!strcmp(action,"sm_field")) {
    if(!sm_edit_panel || !IsWindowVisible(sm_edit_panel))return 0;
    wchar_t *w=host_wide(drive_args[2],strlen(drive_args[2]));if(!w)return 0;
    SetDlgItemTextW(sm_edit_panel,SM_ID_TITLE+atoi(drive_args[1]),w);free(w);return 1;
  }
  if(!strcmp(action,"sm_tagpick")) { /* click a known tag in the dialog list */
    wchar_t *w=host_wide(drive_args[1],strlen(drive_args[1]));if(!w)return 0;
    LRESULT i=SendDlgItemMessageW(sm_edit_panel,SM_ID_TAGLIST,LB_FINDSTRINGEXACT,(WPARAM)-1,(LPARAM)w);free(w);
    if(i<0)return 0;
    SendDlgItemMessageW(sm_edit_panel,SM_ID_TAGLIST,LB_SETCURSEL,i,0);
    SendMessageW(sm_edit_panel,WM_COMMAND,MAKEWPARAM(SM_ID_TAGLIST,LBN_SELCHANGE),0);return 1;
  }
  if(!strcmp(action,"sm_cover")) { /* the file dialog's result */
    wchar_t *w=host_wide(drive_args[1],strlen(drive_args[1]));if(!w)return 0;
    wcsncpy(sm_edit_cover,w,HOST_PATH-1);free(w);sm_edit_cover_clear=0;sm_edit_cover_state();return 1;
  }
  if(!strcmp(action,"sm_nocover")){SendMessageW(sm_edit_panel,WM_COMMAND,SM_ID_NOCOVER,0);return 1;}
  if(!strcmp(action,"sm_save")) {
    int failures=sm_save_failures;SendMessageW(sm_edit_panel,WM_COMMAND,SM_ID_SAVE,0);
    int closed=!IsWindowVisible(sm_edit_panel);
    return drive_argc>1 && !strcmp(drive_args[1],"expect_fail") ? (!closed && sm_save_failures==failures+1):closed;
  }
  if(!strcmp(action,"sm_cancel")){SendMessageW(sm_edit_panel,WM_COMMAND,SM_ID_CANCEL,0);return 1;}
  if(!strcmp(action,"sm_fail_next")){sm_fail_next=1;return 1;}
  if(!strcmp(action,"sm_foreground")){sm_focus(atoi(drive_args[1]));return 1;}
  if(!strcmp(action,"sm_clock")) {
    if(!strcmp(drive_args[1],"freeze")) {
      uint64_t base=drive_argc>2 && drive_args[2][0] ? strtoull(drive_args[2],NULL,10):annot_time();
      sm_frozen_base=base;sm_clock_offset=0;sm_last_tick=sm_last_activity=sm_now();return 1;
    }
    if(!strcmp(drive_args[1],"advance")) {
      /* advance in <=1 s steps so each timer interval is evaluated like the 1 s WM_TIMER */
      uint64_t total=strtoull(drive_args[2],NULL,10);
      for(uint64_t done=0;done<total;) {uint64_t step=min(1000ULL,total-done);sm_clock_offset+=(int64_t)step;done+=step;sm_tick();}
      return 1;
    }
    return 0;
  }
  return 0;
}
