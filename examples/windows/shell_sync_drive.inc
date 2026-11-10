/* SPDX-License-Identifier: MIT */
/* Acceptance hooks for the 云同步 page. Only the settings button, the edit
   boxes and the buttons are driven; the engine, worker thread and window
   messages are the production ones. */
static void sy_drive_pump(unsigned ms) {
  ULONGLONG end=GetTickCount64()+ms;MSG m;
  while(GetTickCount64()<end) {
    while(PeekMessageW(&m,NULL,0,0,PM_REMOVE)) {
      /* The drive timer must not re-enter this unfinished sync_wait step. */
      if(m.hwnd==g.window && m.message==WM_TIMER && m.wParam==1) continue;
      TranslateMessage(&m);DispatchMessageW(&m);
    }
    Sleep(10);
  }
}
static int sy_drive(const char *action) {
  if(!strcmp(action,"sync_open")) {
    if(!shell_panel_open) shell_toggle_settings();
    SendMessageW(shell_panel,WM_COMMAND,IDC_SHELL_SYNC,0);
    return sy_panel && IsWindowVisible(sy_panel) && !shell_panel_open;
  }
  if(!strcmp(action,"sync_fill")) { /* sync_fill|url|user|password */
    if(!sy_panel) return 0;
    dict_set_text(GetDlgItem(sy_panel,SY_ID_URL),drive_args[1]);
    dict_set_text(GetDlgItem(sy_panel,SY_ID_USER),drive_args[2]);
    dict_set_text(GetDlgItem(sy_panel,SY_ID_PASS),drive_args[3]);
    return 1;
  }
  if(!strcmp(action,"sync_click")) { /* sync_click|save|now|clear|close */
    int id=!strcmp(drive_args[1],"save") ? SY_ID_SAVE : !strcmp(drive_args[1],"now") ? SY_ID_NOW :
      !strcmp(drive_args[1],"clear") ? SY_ID_CLEAR : SY_ID_CLOSE;
    if(!sy_panel) return 0;
    SendMessageW(sy_panel,WM_COMMAND,id,0);return 1;
  }
  if(!strcmp(action,"sync_wait")) { /* sync_wait|max_ms : pump until the worker finished */
    ULONGLONG end=GetTickCount64()+(unsigned)atoi(drive_args[1]);
    sy_drive_pump(50);
    while(sy_busy && GetTickCount64()<end) sy_drive_pump(50);
    sy_drive_pump(100);
    return !sy_busy;
  }
  if(!strcmp(action,"sync_check")) { /* sync_check|code|substring|queue_count : status text must be on screen */
    wchar_t raw[2048];GetWindowTextW(GetDlgItem(sy_panel,SY_ID_STATUS),raw,2048);char *text=host_utf8(raw);
    int ok=text && sy_last_code==atoi(drive_args[1]) && (!drive_args[2][0] || strstr(text,drive_args[2])) &&
      (atoi(drive_args[3])<0 || sy_queue_count==atoi(drive_args[3]));
    printf("sync_check code=%d queue=%d shown=%s\n",sy_last_code,sy_queue_count,text ? text:"");
    free(text);return ok;
  }
  if(!strcmp(action,"sync_pass_empty")) { /* the password edit never keeps the secret after a click */
    wchar_t raw[64];GetWindowTextW(GetDlgItem(sy_panel,SY_ID_PASS),raw,64);return raw[0]==0;
  }
  return 0;
}
