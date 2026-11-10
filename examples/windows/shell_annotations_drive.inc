/* SPDX-License-Identifier: MIT */
/* Acceptance operations use production selection, command and editor paths. */
static int annot_drive_dump(const char *name) {
  annot_sync();annot_resolve();cv_text j={0};
  cv_text_format(&j,"{\"count\":%d,\"dirty\":%d,\"prompts\":%d,\"book_sha256\":\"%s\",\"font\":%.0f,\"part\":%llu,\"page\":%llu,\"items\":[",annot_count,annot_storage.dirty,annot_prompt_count,annot_hash,(double)shell_font,(unsigned long long)g.frame.part,(unsigned long long)g.frame.page);
  for(int i=0;i<annot_count;i++) {
    shell_annotation *a=&annotations[i];HRGN region=annot_region(a);RECT box;int visible=GetRgnBox(region,&box)!=NULLREGION;DeleteObject(region);
    POINT p={0};int marker=annot_marker(a,&p);
    if(i)cv_text_string(&j,",");
    cv_text_format(&j,"{\"found\":%d,\"color\":%d,\"start\":[%llu,%llu],\"end\":[%llu,%llu],\"visible\":%d,\"bounds\":[%ld,%ld,%ld,%ld],\"marker\":[%d,%ld,%ld],",a->found,a->color,
      (unsigned long long)a->range.start.part,(unsigned long long)a->range.start.offset,(unsigned long long)a->range.end.part,(unsigned long long)a->range.end.offset,visible,box.left,box.top,box.right,box.bottom,marker,p.x,p.y);
    annot_json_string(&j,"text",a->text);cv_text_string(&j,"}");
  }
  wchar_t title[512];GetWindowTextW(g.window,title,512);char *utf8_title=host_utf8(title),*error=host_utf8(annot_last_error);
  cv_text_string(&j,"],");annot_json_string(&j,"title",utf8_title ? utf8_title:"");cv_text_string(&j,",");annot_json_string(&j,"error",error ? error:"");
  free(utf8_title);free(error);
  cv_text_string(&j,"}\n");int ok=!j.failed && select_drive_write(name,".annotations.json",j.data,j.size);cv_text_free(&j);return ok;
}
static int annot_drive(const char *action) {
  if(!strcmp(action,"annot_request_close")) {PostMessageW(g.window,WM_CLOSE,0,0);return 1;}
  if(!strcmp(action,"annot_answer")) {annot_test_answer=!strcmp(drive_args[1],"yes") ? IDYES:!strcmp(drive_args[1],"no") ? IDNO:IDCANCEL;return 1;}
  if(!strcmp(action,"annot_save"))return annot_save();
  if(!strcmp(action,"annot_autosave")) {annot_autosave();return annot_storage.autosaved==annot_storage.revision;}
  if(!strcmp(action,"annot_cancel")) {annot_cancel_edit();return 1;}
  if(!strcmp(action,"annot_prompt")) {
    wchar_t *expected=host_wide(drive_args[1],strlen(drive_args[1]));int ok=expected && wcsstr(annot_last_prompt,expected)!=NULL;free(expected);return ok;
  }
  if(!strcmp(action,"annot_dump"))return annot_drive_dump(drive_args[1]);
  if(!strcmp(action,"annot_command"))return annot_command(atoi(drive_args[1]));
  if(!strcmp(action,"annot_close")){annot_close();annot_selected=-1;page_dirty(g.page,0);return 1;}
  if(!strcmp(action,"annot_edit")) {
    if(!annot_panel || !IsWindowVisible(annot_panel))return 0;
    wchar_t *wide=host_wide(drive_args[1],strlen(drive_args[1]));if(!wide)return 0;
    /* WM_SETTEXT omits EN_CHANGE on multiline edits; replace selection like typing. */
    SendMessageW(annot_edit,EM_SETSEL,0,-1);SendMessageW(annot_edit,EM_REPLACESEL,TRUE,(LPARAM)wide);free(wide);
    if(drive_argc>2 && drive_args[2][0]) {
      int id=10+atoi(drive_args[2]);CheckRadioButton(annot_panel,10,12,id);
      SendMessageW(annot_panel,WM_COMMAND,MAKEWPARAM(id,BN_CLICKED),0);
    }
    if(drive_argc<=3 || strcmp(drive_args[3],"preview")) {
      SendMessageW(annot_panel,WM_COMMAND,1,0);return !IsWindowVisible(annot_panel);
    }
    return 1;
  }
  if(!strcmp(action,"annot_pick")) {
    int i=atoi(drive_args[1]);if(i<0 || i>=annot_count)return 0;
    POINT p={0};
    if(drive_argc>2 && !strcmp(drive_args[2],"marker")) {
      if(!annot_marker(&annotations[i],&p))return 0;
    } else {
      HRGN region=annot_region(&annotations[i]);RECT box;int found=GetRgnBox(region,&box)!=NULLREGION;DeleteObject(region);
      if(!found)return 0;
      p.x=g.view.dx+box.left+1;p.y=g.view.dy+box.top+1;
    }
    SendMessageW(g.page,WM_LBUTTONDOWN,MK_LBUTTON,MAKELPARAM(p.x,p.y));SendMessageW(g.page,WM_LBUTTONUP,0,MAKELPARAM(p.x,p.y));
    return annot_selected==i;
  }
  return 0;
}
