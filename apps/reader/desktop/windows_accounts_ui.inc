/* SPDX-License-Identifier: MIT
 * UI-thread side of the Windows account feature. The secondary entry is the
 * "账号" button or Ctrl+Shift+A; the default shelf gains no resident panel.
 * The native session owns its network thread; this file only controls and
 * observes it, and never waits for the network on the UI thread. */
static void finish_close(HWND window);
static INT_PTR CALLBACK acct_dialog_procedure(HWND, UINT, WPARAM, LPARAM);

static const wchar_t *acct_state_name(reader_session_state state) {
  switch (state) {
    case READER_SESSION_IDLE: return L"IDLE";
    case READER_SESSION_RUNNING: return L"RUNNING";
    case READER_SESSION_CANCELLING: return L"CANCELLING";
    case READER_SESSION_CANCELLED: return L"CANCELLED";
    case READER_SESSION_FINISHED: return L"FINISHED";
    case READER_SESSION_FAILED: return L"FAILED";
    case READER_SESSION_CLOSING: return L"CLOSING";
    case READER_SESSION_CLOSED: return L"CLOSED";
  }
  return L"?";
}
static int acct_session_live(void) {
  return acct.session && (acct.view.state == READER_SESSION_RUNNING || acct.view.state == READER_SESSION_CANCELLING);
}
static int acct_job_running(void) { return g.job && account_job_kind(g.job->kind); }
static int acct_busy(void) {
  return g.job != NULL || g.pending != NULL || acct_session_live() || acct.closing_session || acct.want_stage;
}
static void acct_notice(const wchar_t *text) {
  copy_wstring(acct.notice, 512, text);
  if (acct.message) SetWindowTextW(acct.message, acct.notice);
  set_status(acct.notice);
}
static void acct_detail_refresh(void) {
  acct_owner *o = &acct.owner; wchar_t *at = acct.detail_text; size_t left = sizeof(acct.detail_text) / sizeof(wchar_t);
  int n;
  const reader_session_snapshot *v = &acct.view;
  const wchar_t *credential = !acct.have_secret ? L"未设置" : o->secret_remember ? L"系统安全存储" : L"仅本次会话";
  n = swprintf(at, left, L"凭据：%ls\r\n", credential);
  if (n > 0) { at += n; left -= (size_t)n; }
  if (!acct_job_running()) {
    n = swprintf(at, left, L"本机原书：已检查 %llu，新暂存 %llu，已存在 %llu，待处理 %llu，失败 %llu\r\n",
      (unsigned long long)o->seen, (unsigned long long)o->prepared, (unsigned long long)o->existing,
      (unsigned long long)o->pending, (unsigned long long)o->failed);
    if (n > 0) { at += n; left -= (size_t)n; }
  }
  if (acct.session) {
    n = swprintf(at, left, L"同步：第 %llu 次尝试，状态 %ls，上传 %llu，接收 %llu，已核对原件 %llu，等待元数据 %llu，等待本机原件 %llu\r\n",
      (unsigned long long)v->attempt, acct_state_name(v->state), (unsigned long long)v->pushed, (unsigned long long)v->pulled,
      (unsigned long long)v->originals_verified, (unsigned long long)v->pending_metadata_observations,
      (unsigned long long)v->pending_original_observations);
    if (n > 0) { at += n; left -= (size_t)n; }
    if (v->state == READER_SESSION_FAILED && v->error.message[0]) {
      wchar_t *text = host_wide(v->error.message, strlen(v->error.message));
      n = swprintf(at, left, L"错误：%ls\r\n", text ? text : L"");
      free(text);
      if (n > 0) { at += n; left -= (size_t)n; }
    }
  }
  if (!acct_job_running())
    swprintf(at, left, L"接收：已应用 %llu，并发版本 %llu（不自动选择），待依赖 %llu，受限 %llu，墓碑 %llu（保留本机副本），"
      L"已导入 %llu，等待原件 %llu，导入失败 %llu，应用失败 %llu",
      (unsigned long long)o->projected, (unsigned long long)o->concurrent, (unsigned long long)o->pending_parents,
      (unsigned long long)o->blocked, (unsigned long long)o->tombstones, (unsigned long long)o->imported,
      (unsigned long long)o->import_waiting, (unsigned long long)o->import_failed, (unsigned long long)o->project_failed);
  if (acct.detail) SetWindowTextW(acct.detail, acct.detail_text);
}
static void acct_controls(void) {
  if (!acct.dialog) return;
  int busy = acct_busy();
  int retry_session = acct.session && (acct.view.state == READER_SESSION_FAILED || acct.view.state == READER_SESSION_CANCELLED);
  EnableWindow(acct.dialog, TRUE);
  EnableWindow(GetDlgItem(acct.dialog, IDC_ACCOUNT_APPLY), !busy && !g.closing);
  EnableWindow(GetDlgItem(acct.dialog, IDC_ACCOUNT_SYNC), !busy && !g.closing && acct.have_secret && g.product_ready && !g.product_pending);
  EnableWindow(GetDlgItem(acct.dialog, IDC_ACCOUNT_CANCEL), busy && !acct.closing_session);
  EnableWindow(GetDlgItem(acct.dialog, IDC_ACCOUNT_RETRY), !busy && !g.closing && (retry_session || acct.stage_failed || acct.recv_failed));
  EnableWindow(GetDlgItem(acct.dialog, IDC_ACCOUNT_FORGET), !busy && !g.closing);
  EnableWindow(acct.root, !busy); EnableWindow(acct.user, !busy); EnableWindow(acct.password, !busy);
  EnableWindow(acct.remember, !busy);
}
static void acct_timer(void) { if (g.window) SetTimer(g.window, 5, 150, NULL); }
static host_job *acct_job(int kind, int action) {
  host_job *job = job_new(kind);
  if (job) job->account_action = action;
  return job;
}
static void acct_begin_stage(void) {
  host_job *job;
  InterlockedExchange(&acct.cancelled, 0);
  acct.stage_failed = acct.recv_failed = acct.recv_done = 0; acct.want_stage = 0;
  job = acct_job(JOB_ACCOUNT_STAGE, ACCT_STAGE_BEGIN);
  if (!job) { acct_notice(L"无法建立同步准备任务。"); acct_controls(); return; }
  acct_notice(L"正在准备本机原书；完成前不会启动网络。");
  job_submit(job); acct_timer(); acct_controls();
}
static void acct_begin_receive(void) {
  host_job *job = acct_job(JOB_ACCOUNT_RECEIVE, ACCT_RECV_BEGIN);
  if (!job) { acct.recv_failed = 1; acct_notice(L"无法建立接收任务。"); acct_controls(); return; }
  acct.recv_failed = acct.recv_done = 0;
  acct_notice(L"正在应用云端书籍信息并导入已下载的原书。");
  job_submit(job); acct_controls();
}
static void acct_start_network(void) {
  acct_owner *o = &acct.owner;
  char *pair = NULL, *encoded = NULL, *authorization = NULL, *product = host_utf8(g.product_path);
  char *work = host_utf8(acct.work), *originals = host_utf8(acct.originals);
  reader_session_config config = {0}; reader_session_status code = READER_SESSION_ARGUMENT;
  size_t user_bytes = o->secret ? strlen((const char *)o->secret) : 0;
  if (o->secret && product && work && originals && user_bytes && user_bytes + 1 < o->secret_size) {
    pair = malloc(o->secret_size + 1); encoded = malloc((o->secret_size + 2) / 3 * 4 + 8);
    authorization = malloc((o->secret_size + 2) / 3 * 4 + 16);
    if (pair && encoded && authorization) {
      memcpy(pair, o->secret, o->secret_size); pair[user_bytes] = ':';
      acct_base64((const unsigned char *)pair, o->secret_size, encoded);
      snprintf(authorization, (o->secret_size + 2) / 3 * 4 + 16, "Basic %s", encoded);
      config.product_path = product; config.private_directory = work; config.original_directory = originals;
      config.account_id = o->id; config.dav.root_url = o->root; config.dav.authorization = authorization;
      config.dav.timeout_ms = 15000;
      code = reader_session_create(&config, &acct.session);
      if (code == READER_SESSION_OK) { acct.generation++; code = reader_session_start(acct.session); }
      if (acct.session) reader_session_observe(acct.session, &acct.view);
    }
  }
  if (pair) { exr_credentials_wipe(pair, o->secret_size); free(pair); }
  if (encoded) { exr_credentials_wipe(encoded, strlen(encoded)); free(encoded); }
  if (authorization) { exr_credentials_wipe(authorization, strlen(authorization)); free(authorization); }
  free(product); free(work); free(originals);
  if (code != READER_SESSION_OK) {
    acct.stage_failed = 1;
    acct_notice(code == READER_SESSION_ACCOUNT ? L"此书库已绑定其他账号或地址；未发起任何网络请求。" : L"同步无法启动；书库保持不变。");
  } else acct_notice(L"正在扫描云端记录；可随时取消。已下载的原书会在扫描完成后导入。");
  acct_timer(); acct_detail_refresh(); acct_controls();
}
static wchar_t *acct_read_edit(HWND edit) {
  int length = GetWindowTextLengthW(edit);
  wchar_t *value;
  if (length < 0 || length > 4096) return NULL;
  value = calloc((size_t)length + 1, sizeof(*value));
  if (value && GetWindowTextW(edit, value, length + 1) != length) { free(value); return NULL; }
  return value;
}
static void acct_secure_free(wchar_t *value) {
  if (!value) return;
  SecureZeroMemory(value, wcslen(value) * sizeof(*value)); free(value);
}
static void acct_apply(void) {
  wchar_t *root = acct_read_edit(acct.root), *user = acct_read_edit(acct.user), *password = acct_read_edit(acct.password);
  host_job *job = acct_job(JOB_ACCOUNT_SET, 0);
  if (!job || !root || !user || !password) {
    if (job) job_release(job);
    acct_secure_free(root); acct_secure_free(user); acct_secure_free(password);
    acct_notice(L"无法读取输入。"); return;
  }
  job->account_root = host_utf8(root); job->account_user = host_utf8(user); job->account_password = host_utf8(password);
  job->account_remember = SendMessageW(acct.remember, BM_GETCHECK, 0, 0) == BST_CHECKED;
  acct_secure_free(root); acct_secure_free(user); acct_secure_free(password);
  SetWindowTextW(acct.password, L"");
  if (!job->account_root || !job->account_user || !job->account_password) {
    job_release(job); acct_notice(L"输入包含无效字符。"); return;
  }
  acct_notice(L"正在应用账号设置。"); job_submit(job); acct_controls();
}
static void acct_sync(void) {
  if (acct_busy() || !acct.have_secret) return;
  if (acct.session) {
    /* A new connection prepares the local library again, so retire the old one first. */
    reader_session_request_close(acct.session); acct.closing_session = 1; acct.want_stage = 1;
    acct_notice(L"正在关闭上一次连接，随后重新准备并扫描。"); acct_timer(); acct_controls(); return;
  }
  acct_begin_stage();
}
static void acct_cancel(void) {
  InterlockedExchange(&acct.cancelled, 1);
  if (g.job && account_job_kind(g.job->kind)) InterlockedExchange(&g.job->cancel, 1);
  if (acct.session && acct_session_live()) reader_session_cancel(acct.session);
  acct.want_stage = 0;
  acct_notice(L"正在取消；已保存的书籍信息和已暂存的原书会保留。");
  acct_controls();
}
static void acct_retry(void) {
  if (acct_busy() || g.closing) return;
  InterlockedExchange(&acct.cancelled, 0);
  if (acct.session && (acct.view.state == READER_SESSION_FAILED || acct.view.state == READER_SESSION_CANCELLED)) {
    reader_session_status code = reader_session_start(acct.session);
    reader_session_observe(acct.session, &acct.view);
    acct.stage_failed = 0;
    acct_notice(code == READER_SESSION_OK ? L"已从上次成功的位置继续扫描。" : L"无法继续扫描，请稍后再试。");
  } else if (acct.recv_failed) acct_begin_receive();
  else if (acct.stage_failed && acct.have_secret) acct_begin_stage();
  acct_timer(); acct_detail_refresh(); acct_controls();
}
static void acct_forget(void) {
  host_job *job;
  if (acct_busy()) return;
  job = acct_job(JOB_ACCOUNT_FORGET, 0);
  if (!job) return;
  acct_notice(L"正在删除保存的凭据。"); job_submit(job); acct_controls();
}
static void acct_dialog_close(void) {
  if (!acct.dialog) return;
  if (acct_session_live()) reader_session_cancel(acct.session); /* Back cancels; the handle stays for Retry. */
  if (g.job && account_job_kind(g.job->kind)) { InterlockedExchange(&acct.cancelled, 1); InterlockedExchange(&g.job->cancel, 1); }
  DestroyWindow(acct.dialog);
}
static HWND acct_entry(HWND parent, int id, int y, DWORD extra) {
  HWND entry = CreateWindowExW(WS_EX_CLIENTEDGE, L"EDIT", L"", WS_CHILD | WS_VISIBLE | WS_TABSTOP | ES_AUTOHSCROLL | extra,
    120, y, 480, 26, parent, (HMENU)(INT_PTR)id, NULL, NULL);
  SendMessageW(entry, WM_SETFONT, (WPARAM)GetStockObject(DEFAULT_GUI_FONT), TRUE);
  SendMessageW(entry, EM_SETLIMITTEXT, 2000, 0);
  return entry;
}
static INT_PTR CALLBACK acct_dialog_procedure(HWND dialog, UINT message, WPARAM wparam, LPARAM lparam) {
  (void)lparam;
  switch (message) {
    case WM_INITDIALOG: {
      acct.dialog = dialog;
      SetWindowTextW(dialog, L"账号与同步");
      MoveWindow(make_static(dialog, 0, L"服务器地址(&U)"), 18, 20, 98, 22, TRUE);
      acct.root = acct_entry(dialog, IDC_ACCOUNT_ROOT, 16, 0);
      MoveWindow(make_static(dialog, 0, L"用户名(&N)"), 18, 58, 98, 22, TRUE);
      acct.user = acct_entry(dialog, IDC_ACCOUNT_USER, 54, 0);
      MoveWindow(make_static(dialog, 0, L"密码(&P)"), 18, 96, 98, 22, TRUE);
      acct.password = acct_entry(dialog, IDC_ACCOUNT_PASSWORD, 92, ES_PASSWORD);
      acct.remember = CreateWindowExW(0, L"BUTTON", L"保存到系统安全存储（取消勾选则仅本次会话）(&R)", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_AUTOCHECKBOX,
        120, 126, 480, 26, dialog, (HMENU)(INT_PTR)IDC_ACCOUNT_REMEMBER, NULL, NULL);
      SendMessageW(acct.remember, WM_SETFONT, (WPARAM)GetStockObject(DEFAULT_GUI_FONT), TRUE);
      SendMessageW(acct.remember, BM_SETCHECK, BST_CHECKED, 0);
      MoveWindow(make_button(dialog, IDC_ACCOUNT_APPLY, L"应用(&A)"), 18, 162, 90, 30, TRUE);
      MoveWindow(make_button(dialog, IDC_ACCOUNT_SYNC, L"立即同步(&S)"), 116, 162, 100, 30, TRUE);
      MoveWindow(make_button(dialog, IDC_ACCOUNT_CANCEL, L"取消(&C)"), 224, 162, 80, 30, TRUE);
      MoveWindow(make_button(dialog, IDC_ACCOUNT_RETRY, L"重试(&T)"), 312, 162, 80, 30, TRUE);
      MoveWindow(make_button(dialog, IDC_ACCOUNT_FORGET, L"忘记凭据(&F)"), 400, 162, 100, 30, TRUE);
      MoveWindow(make_button(dialog, IDC_ACCOUNT_CLOSE, L"关闭(&X)"), 508, 162, 92, 30, TRUE);
      acct.message = make_static(dialog, IDC_ACCOUNT_MESSAGE, acct.notice);
      MoveWindow(acct.message, 18, 204, 582, 44, TRUE);
      acct.detail = make_static(dialog, IDC_ACCOUNT_DETAIL, L"");
      MoveWindow(acct.detail, 18, 252, 582, 132, TRUE);
      if (acct.owner.root[0]) {
        wchar_t *root = host_wide(acct.owner.root, strlen(acct.owner.root)), *user = host_wide(acct.owner.user, strlen(acct.owner.user));
        if (root) SetWindowTextW(acct.root, root);
        if (user && acct.have_secret) SetWindowTextW(acct.user, user);
        free(root); free(user);
      }
      SendMessageW(acct.remember, BM_SETCHECK, acct.have_secret && !acct.owner.secret_remember ? BST_UNCHECKED : BST_CHECKED, 0);
      acct_detail_refresh(); acct_controls();
      SetFocus(acct.root);
      return FALSE;
    }
    case WM_COMMAND: {
      int id = LOWORD(wparam);
      if (id == IDC_ACCOUNT_APPLY) acct_apply();
      else if (id == IDC_ACCOUNT_SYNC) acct_sync();
      else if (id == IDC_ACCOUNT_CANCEL) acct_cancel();
      else if (id == IDC_ACCOUNT_RETRY) acct_retry();
      else if (id == IDC_ACCOUNT_FORGET) acct_forget();
      else if (id == IDC_ACCOUNT_CLOSE || id == IDCANCEL) acct_dialog_close();
      else if (id == IDOK) acct_apply();
      return TRUE;
    }
    case WM_CLOSE:
      acct_dialog_close();
      return TRUE;
    case WM_DESTROY:
      acct.dialog = acct.root = acct.user = acct.password = acct.remember = acct.message = acct.detail = NULL;
      if (g.window && IsWindow(g.window)) {
        host_a11y_owner_enabled(1);
        if (!g.closing) { SetActiveWindow(g.window); SetFocus(g.account_button); product_shelf_schedule(0, 0); }
      }
      return TRUE;
  }
  return FALSE;
}
static void acct_open_dialog(void) {
  union { DWORD alignment; unsigned char bytes[sizeof(DLGTEMPLATE) + 6]; } data = {0};
  DLGTEMPLATE *dialog;
  host_job *job;
  RECT parent; HWND window;
  if (acct.dialog || g.closing || g.metadata_dialog || g.metadata_running) return;
  memset(&data, 0, sizeof(data));
  dialog = (DLGTEMPLATE *)data.bytes;
  dialog->style = WS_POPUP | WS_CAPTION | WS_SYSMENU | DS_MODALFRAME; dialog->cx = 340; dialog->cy = 210;
  window = CreateDialogIndirectParamW(GetModuleHandleW(NULL), dialog, g.window, acct_dialog_procedure, 0);
  if (!window) { set_status(L"无法打开账号窗口。"); return; }
  GetWindowRect(g.window, &parent);
  SetWindowPos(window, HWND_TOP, parent.left + 120, parent.top + 80, 640, 470, SWP_SHOWWINDOW);
  host_a11y_owner_enabled(0); SetForegroundWindow(window); SetFocus(acct.root);
  if (!acct.owner.loaded && !g.job && !g.pending) {
    job = acct_job(JOB_ACCOUNT_LOAD, 0);
    if (job) { acct_notice(L"正在读取账号设置。"); job_submit(job); }
  }
  acct_timer(); acct_controls();
}
/* Called for every finished account job after the worker was joined. */
static void acct_job_accept(host_job *job) {
  acct_owner *o = &acct.owner;
  host_job *next;
  int ok = job->status == EXR_OK, cancelled = job->status == EXR_CANCELLED;
  acct.have_secret = o->secret != NULL;
  if (job->kind == JOB_ACCOUNT_LOAD || job->kind == JOB_ACCOUNT_SET || job->kind == JOB_ACCOUNT_FORGET) {
    if (acct.dialog) {
      if (o->root[0]) { wchar_t *root = host_wide(o->root, strlen(o->root)); if (root) SetWindowTextW(acct.root, root); free(root); }
      if (acct.have_secret) { wchar_t *user = host_wide(o->user, strlen(o->user)); if (user) SetWindowTextW(acct.user, user); free(user); }
      if (acct.have_secret) SendMessageW(acct.remember, BM_SETCHECK, o->secret_remember ? BST_CHECKED : BST_UNCHECKED, 0);
    }
    if (job->kind == JOB_ACCOUNT_FORGET && acct.dialog) SetWindowTextW(acct.password, L"");
    acct_notice(job->message[0] ? job->message : ok ? L"账号设置已更新。" : L"账号操作未完成。");
  } else if (job->kind == JOB_ACCOUNT_STAGE) {
    if (g.closing || acct.exit_wanted) { o->staging = 0; }
    else if (ok && o->staging && !g.pending) {
      next = acct_job(JOB_ACCOUNT_STAGE, ACCT_STAGE_NEXT);
      if (next) {
        wchar_t text[160];
        swprintf(text, 160, L"正在准备本机原书：已检查 %llu 本，新暂存 %llu，已存在 %llu。",
          (unsigned long long)o->seen, (unsigned long long)o->prepared, (unsigned long long)o->existing);
        acct_notice(text); job_submit(next);
      } else { o->staging = 0; acct.stage_failed = 1; acct_notice(L"无法继续准备本机原书。"); }
    } else if (ok && !o->staging) acct_start_network();
    else {
      o->staging = 0; acct.stage_failed = !cancelled;
      acct_notice(cancelled ? L"准备已取消；已保存的书籍信息和已暂存的原书会保留。可重试。" :
        job->message[0] ? job->message : L"本机原书准备失败；书库未改变，可重试。");
    }
  } else if (job->kind == JOB_ACCOUNT_RECEIVE) {
    if (g.closing || acct.exit_wanted) { o->receiving = 0; }
    else if (ok && o->receiving && !g.pending) {
      next = acct_job(JOB_ACCOUNT_RECEIVE, ACCT_RECV_NEXT);
      if (next) job_submit(next); else { o->receiving = 0; acct.recv_failed = 1; acct_notice(L"无法继续接收云端书籍。"); }
    } else if (ok) {
      wchar_t text[256];
      acct.recv_done = 1;
      if (o->import_failed)
        swprintf(text, 256, L"同步已完成，但 %llu 本原书的书目映射待恢复；正在自动修复，也可点击“刷新”。",
          (unsigned long long)o->import_failed);
      else
        swprintf(text, 256, L"同步完成：已应用 %llu 项，导入 %llu 本；并发 %llu、墓碑 %llu 保持显式状态。",
          (unsigned long long)o->projected, (unsigned long long)o->imported, (unsigned long long)o->concurrent, (unsigned long long)o->tombstones);
      acct_notice(text);
      if (o->import_failed) { /* repair mappings from the committed SDK imports */
        host_job *repair = job_new(JOB_PRODUCT_REPAIR);
        if (repair) { g.product_ready = 0; job_submit(repair); }
      } else product_shelf_schedule(0, 0);
    } else {
      o->receiving = 0; acct.recv_failed = !cancelled;
      acct_notice(cancelled ? L"接收已取消；已应用的信息会保留。可重试。" : job->message[0] ? job->message : L"接收云端书籍失败，可重试。");
    }
  }
  acct_detail_refresh(); acct_controls();
}
static void acct_tick(void) {
  reader_session_state previous = acct.view.state;
  if (acct.session) {
    reader_session_observe(acct.session, &acct.view);
    if (acct.exit_wanted && acct.view.state != READER_SESSION_CLOSING && acct.view.state != READER_SESSION_CLOSED && !acct.closing_session) {
      reader_session_request_close(acct.session); acct.closing_session = 1;
    }
    if (acct.view.state == READER_SESSION_CLOSED) {
      if (reader_session_destroy(&acct.session) == READER_SESSION_OK) {
        memset(&acct.view, 0, sizeof(acct.view)); acct.closing_session = 0; acct.received_attempt = 0;
        if (g.closing) { finish_close(g.window); return; }
        if (acct.want_stage && !g.job && !g.pending) acct_begin_stage();
      }
    } else if (previous != acct.view.state && !acct.exit_wanted) {
      if (acct.view.state == READER_SESSION_FAILED) {
        InterlockedExchange(&acct.cancelled, 0);
        acct_notice(L"同步失败，已保留已完成的部分。可点击“重试”继续。");
      } else if (acct.view.state == READER_SESSION_CANCELLED) acct_notice(L"同步已取消；已完成的部分会保留。可重试。");
    }
    if (acct.session && acct.view.state == READER_SESSION_FINISHED && acct.received_attempt != acct.view.attempt &&
        !g.job && !g.pending && !g.closing && !acct.exit_wanted) {
      acct.received_attempt = acct.view.attempt; acct_begin_receive();
    }
  }
  if (!acct_job_running() || acct.dialog) acct_detail_refresh();
  acct_controls();
}
/* Window close: cancel, request session closure, and keep polling until CLOSED. */
static void acct_exit(void) {
  acct.exit_wanted = 1; acct.want_stage = 0;
  InterlockedExchange(&acct.cancelled, 1);
  if (acct.dialog) DestroyWindow(acct.dialog);
  if (acct.session) {
    reader_session_request_close(acct.session); acct.closing_session = 1;
    acct_timer();
  }
}
static int acct_exit_blocked(void) { return acct.session != NULL; }
static void acct_shutdown(void) {
  if (acct.session) {
    int waited = 0;
    reader_session_request_close(acct.session);
    for (;;) {
      reader_session_observe(acct.session, &acct.view);
      if (acct.view.state == READER_SESSION_CLOSED) break;
      if (++waited > 1200) ExitProcess(1);
      Sleep(50);
    }
    reader_session_destroy(&acct.session);
  }
  acct_owner_free();
}
