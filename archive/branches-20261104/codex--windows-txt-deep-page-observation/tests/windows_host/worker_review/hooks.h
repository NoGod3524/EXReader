/* SPDX-License-Identifier: MIT
 * Cloud-only fault gates at public SDK call boundaries. The distributed host
 * does not compile this file or accept the observation message. */
static volatile LONG review_armed, review_entered, review_offset_remaining, review_notes_fail, review_shelf_fail;
static volatile LONG review_offset_calls, review_offset_injected;
static HANDLE review_event;
static DWORD review_note_thread;
#ifdef EXR_HOST_SHELF_REVIEW
static void host_update_controls(void);
#endif
static int review_query_failure(int kind) {
  return InterlockedExchange(kind == 1 ? &review_notes_fail : &review_shelf_fail, 0) != 0;
}
static void review_pause(int stage, host_job *job) {
  if (stage == 1) review_note_thread = GetCurrentThreadId();
  if (!stage || InterlockedCompareExchange(&review_armed, 0, 0) != stage) return;
  InterlockedExchange(&review_entered, stage);
  while (WaitForSingleObject(review_event, 10) != WAIT_OBJECT_0 && (!job || !job_cancel_flag(job))) {}
  InterlockedExchange(&review_armed, 0);
}
static exr_status review_offset_get(exr_pager *pager, size_t index, const exr_layout **out, exr_error *error) {
  exr_status status = exr_pager_get(pager, index, out, error);
  LONG left = InterlockedCompareExchange(&review_offset_remaining, 0, 0);
  InterlockedIncrement(&review_offset_calls);
  if (left > 0 && InterlockedDecrement(&review_offset_remaining) == 0 && status == EXR_OK) {
    InterlockedIncrement(&review_offset_injected);
    *out = NULL;
    if (error) { error->code = EXR_LIMIT; strcpy(error->message, "Cloud regression: public page lookup returned EXR_LIMIT"); }
    return EXR_LIMIT;
  }
  return status;
}
static LRESULT review_message(HWND window, WPARAM code, LPARAM value) {
  if (code == 10) return (LRESULT)(g.has_current ? g.current.id : 0);
  if (code == 11) return (LRESULT)g.frame.page;
  if (code == 12) return (LRESULT)current_note_count();
  if (code == 13) return (LRESULT)g.shelf_count;
  if (code == 14) return g.job || g.pending
#ifdef EXR_HOST_SHELF_REVIEW
    || g.shelf_need_refresh
#endif
    ;
  if (code == 15) return g.frame.fixed;
  if (code == 16) return g.selection.active ? (LRESULT)(g.selection.start < g.selection.end ? g.selection.end - g.selection.start : g.selection.start - g.selection.end) : 0;
  if (code == 17) return dragging;
  if (code == 18) return InterlockedCompareExchange(&review_entered, 0, 0);
  if (code == 19) return (LRESULT)g.session.book_id;
  if (code == 25) return (LRESULT)review_note_thread;
  if (code == 26) return (LRESULT)GetWindowThreadProcessId(window, NULL);
  if (code == 27) return InterlockedCompareExchange(&review_offset_calls, 0, 0);
  if (code == 28) return InterlockedCompareExchange(&review_offset_injected, 0, 0);
  if ((code >= 101 && code <= 105)
#ifdef EXR_READER_WINDOWS_NAVIGATION
      || code == 106 || code == 107
#endif
#ifdef EXR_READER_WINDOWS_RECORDS
      || code == 108 || code == 109 || code == 110
#endif
  ) {
    wchar_t name[100];
    swprintf(name, 100, L"Local\\EXReaderWorkerReview-%lu", GetCurrentProcessId());
    if (!review_event) review_event = CreateEventW(NULL, TRUE, FALSE, name);
    ResetEvent(review_event);
    InterlockedExchange(&review_entered, 0);
    InterlockedExchange(&review_armed, (LONG)code - 100);
    return review_event != NULL;
  }
#ifdef EXR_READER_WINDOWS_TXT_RECOVERY
  if (code == 306) {
    if (!g.session.txt || !value || value > 10000 || g.job || g.pending) return 0;
    page_step((int)value);
    return g.job != NULL;
  }
#endif
  if (code == 200) { if (review_event) SetEvent(review_event); return 1; }
  if (code == 300) {
    InterlockedExchange(&review_offset_calls, 0); InterlockedExchange(&review_offset_injected, 0);
    InterlockedExchange(&review_offset_remaining, (LONG)value); return 1;
  }
  if (code == 301) { InterlockedExchange(&review_notes_fail, 1); return 1; }
  if (code == 302) { InterlockedExchange(&review_shelf_fail, 1); return 1; }
#ifdef EXR_HOST_SHELF_REVIEW
  if (code == 305) return g.shelf_filter_pending;
  if (code == 303) {
    shelf_clear();
    SendMessageW(g.books, LB_RESETCONTENT, 0, 0);
    return 1;
  }
  if (code == 304) {
    int ok=reload_shelf()==EXR_OK;
    host_update_controls();
    return ok;
  }
#endif
  return 0;
}
static void review_shutdown(void) { if (review_event) { CloseHandle(review_event); review_event = NULL; } }
