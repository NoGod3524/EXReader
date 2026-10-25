/* SPDX-License-Identifier: MIT */
/* Installed F3 reading preferences: immutable job submission and acceptance.
 *
 * One preference selection becomes one job on the existing single SDK worker.
 * The worker lays out, renders and saves strictly; only a job that finished all
 * three publishes its frame and its record. */

static void prefs_show(void);
static void prefs_dialog_refresh(void);
static void prefs_dialog_closed(void);
static int prefs_ui_open(void);
static void prefs_notice(const wchar_t *text);
static void prefs_dialog_controls(void);
static void page_step(int direction);

static exr_status prefs_job(host_job *job) {
  if (job_cancel_flag(job)) return EXR_CANCELLED;
  return prefs_write(&job->prefs, job->message, 512);
}

static int prefs_submit(const reader_preferences *next, int persist) {
  host_job *job;
  if (g.closing || g.job || g.pending) return 0;
  if (g.has_current && g.frame.valid && g.frame.fixed && g.session.active) {
    job = job_new(JOB_GO);
    if (!job) { set_status(L"内存不足，无法应用阅读设置。"); return 0; }
    job->book_id = g.current.id;
    job->target_page = g.frame.page;
    job->zoom_percent = (int)next->fixed_page_zoom;
  } else if (g.has_current && g.frame.valid && g.session.active) {
    exr_anchor anchor = {0};
    exr_error error = {0};
    if (!g.session.bounded &&
        exr_anchor_create(g.session.document, g.frame.range_start, g.frame.range_start,
                          &anchor, &error) != EXR_OK) {
      wchar_t message[512];
      describe_error(message, 512, L"无法建立设置重排锚点", error.code, &error);
      set_status(message);
      return 0;
    }
    job = job_new(JOB_LAYOUT);
    if (!job) { exr_anchor_free(&anchor); set_status(L"内存不足，无法应用阅读设置。"); return 0; }
    job->book_id = g.current.id;
    job->font_percent = (int)(next->font_size + 0.5f);
    job->anchor = anchor;
    job->has_anchor = !g.session.bounded;
  } else {
    job = job_new(JOB_PREFERENCES);
    if (!job) { set_status(L"内存不足，无法保存阅读设置。"); return 0; }
    job->book_id = 0;
  }
  job->prefs = *next;
  job->prefs_valid = 1;
  job->prefs_persist = persist ? 1 : 0;
  job_submit(job);
  return 1;
}

/* Latest system appearance while busy replaces any earlier pending value. */
static void prefs_system_changed(void) {
  reader_preferences_theme now = prefs_sample_system();
  if ((int)now == prefs.system_theme) return;
  prefs.system_theme = (int)now;
  prefs.system_events++;
  if (!prefs.active || prefs.value.theme != READER_PREFERENCES_THEME_SYSTEM) return;
  prefs.theme_pending = 1;
}

/* Re-render the accepted page for a new system appearance. Never saves: the
   stored record keeps only the "system" choice. */
static void prefs_pump(void) {
  if (!prefs.theme_pending || g.closing) return;
  if (g.job || g.pending || !g.has_current || !g.frame.valid || !g.session.active) return;
  if (g.frame.fixed) { prefs.theme_pending = 0; return; }
  prefs.theme_pending = 0;
  prefs_submit(&prefs.value, 0);
}

/* After every completion: take at most one coalesced turn, then a pending
   system-appearance re-render. Both use the existing single worker. */
static void prefs_after_complete(void) {
  if (g.closing) return;
  if (prefs_ui_open() && prefs_ui.running) {
    prefs_ui.running = 0;
    prefs_dialog_controls();
    prefs_notice(prefs.last_ok ? L"当前的阅读设置已生效。" : L"设置未应用，原设置保持不变。");
  }
  if (prefs_turn_pending && !g.job && !g.pending) {
    int turn = prefs_turn_pending;
    prefs_turn_pending = 0;
    if (!prefs_ui_open()) page_step(turn);
  }
  prefs_pump();
}

static void prefs_accept(host_job *job) {
  if (job->status == EXR_OK) {
    prefs.value = job->prefs;
    prefs.active = 1;
    prefs.corrupt = 0;
    prefs.file_present = 1;
    prefs.load_status = READER_PREFERENCES_OK;
    set_statusf(L"阅读设置已保存：字号 %.1f 磅，行距 %.2f。",
                (double)prefs.value.font_size, (double)prefs.value.line_spacing);
  } else if (job->status == EXR_CANCELLED) {
    set_status(L"阅读设置未应用；当前画面与设置保持不变。");
  } else {
    if (job->message[0]) set_status(job->message);
    else set_status(L"阅读设置未能保存或应用，原设置保持不变。");
  }
  prefs_dialog_refresh();
  host_update_controls();
}
