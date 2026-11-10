/* SPDX-License-Identifier: MIT */
/* Acceptance sends the production HWND handlers and records accepted state. */
  if(!strcmp(action,"shelf_return")) {
    if(!strcmp(drive_args[1],"escape"))select_drive_key(VK_ESCAPE,0,0);
    else if(!strcmp(drive_args[1],"ctrlw"))select_drive_key('W',0,1);
    else SendMessageW(g.window,WM_COMMAND,IDC_SHELL_BACK,0);
    drive_step_finish(1,"return requested");return 0;
  }
  if(!strcmp(action,"shelf_open")) {
    int index=atoi(drive_args[1]);RECT r={0};
    if(index<0 || index>=shelf_count || !shelf_visible) {drive_step_finish(0,"shelf row unavailable");return 0;}
    (void)r;
    int row=shelf_index(shelf_recent[index].id);
    if(!sm_drive_click(SM_HIT_BOOK,row,0)){drive_step_finish(0,"book is outside the shelf viewport");return 0;}
    drive_step_finish(1,"shelf row clicked");return 0;
  }
  if(!strcmp(action,"shelf_dump")) {
    size_t bytes=g.frame.valid ? g.frame.bitmap.stride*g.frame.bitmap.height:0;
    char json[1024];int n=snprintf(json,sizeof(json),
      "{\"shelf\":%d,\"reading\":%d,\"bar_hidden\":%d,\"books\":%d,\"edge\":%d,\"book\":%lld,\"part\":%zu,\"page\":%zu,\"range\":[%zu,%zu],\"raster_fnv\":\"%016llx\",\"selection\":%d,\"select_valid\":%d,\"builds\":%lu,\"pending_exit\":%d}\n",
      shelf_visible,shell_active,shell_bar_hidden,shelf_count,shell_tap_edge,(long long)g.frame.book_id,g.frame.part,g.frame.page,
      g.frame.range_start,g.frame.range_end,fnv1a(g.frame.bitmap.pixels,bytes),g.selection.active,select_valid,shell_pager_builds,shelf_exit_pending);
    drive_step_finish(select_drive_write(drive_args[1],".state.json",json,(size_t)n),"shelf state recorded");return 0;
  }
  if(!strcmp(action,"gesture_pointer")) {
    UINT m=!strcmp(drive_args[1],"down") ? WM_LBUTTONDOWN:!strcmp(drive_args[1],"double") ? WM_LBUTTONDBLCLK:!strcmp(drive_args[1],"up") ? WM_LBUTTONUP:WM_MOUSEMOVE;
    SendMessageW(g.page,m,m==WM_LBUTTONUP ? 0:MK_LBUTTON,MAKELPARAM(atoi(drive_args[2]),atoi(drive_args[3])));
    drive_step_finish(1,"pointer dispatched");return 0;
  }
  if(!strcmp(action,"gesture_tap") || !strcmp(action,"gesture_swipe")) {
    RECT r;GetClientRect(g.page,&r);
    int x=!strcmp(action,"gesture_tap") ? (int)(r.right*atof(drive_args[1])/100):r.right/2;
    int y=shell_px(8,shell_dpi),delta=!strcmp(action,"gesture_swipe") ? atoi(drive_args[1]):0;
    SendMessageW(g.page,WM_LBUTTONDOWN,MK_LBUTTON,MAKELPARAM(x,y));
    if(delta) SendMessageW(g.page,WM_MOUSEMOVE,MK_LBUTTON,MAKELPARAM(x+delta,y));
    SendMessageW(g.page,WM_LBUTTONUP,0,MAKELPARAM(x+delta,y));
    drive_step_finish(1,"gesture dispatched");return 0;
  }
  if(!strcmp(action,"gesture_ratio")) {
    SendMessageW(shell_panel,WM_COMMAND,atoi(drive_args[1])==20 ? IDC_SHELL_TAP20:IDC_SHELL_TAP25,0);
    drive_step_finish(1,"settings ratio selected");return 0;
  }
  if(!strcmp(action,"gesture_overlay")) {
    shell_zone_overlay=atoi(drive_args[1]);page_dirty(g.page,1);drive_step_finish(1,"tap region guide toggled");return 0;
  }
