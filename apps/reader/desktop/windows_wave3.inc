/* SPDX-License-Identifier: MIT
 * C09: native Windows adoption of annotation import/export, the font library,
 * original export, jump history and the read-only sync status view.
 *
 * Included once by examples/reader.c after windows_records.inc. Threading:
 *   - dialogs, the font library, jump history and the sync snapshot live on the
 *     UI thread (every one of those modules is owner-thread bound);
 *   - annotation preview/commit/export, original export and history navigation
 *     run on the host's one serialized SDK worker as JOB_WAVE3;
 *   - nothing here opens a second SDK, store or parser.
 */
#define COBJMACROS
#include <shobjidl.h>
#include <bcrypt.h>

enum { IDC_W3_ANNOTATIONS = 47001, IDC_W3_FONTS, IDC_W3_ORIGINALS, IDC_W3_BACK, IDC_W3_FORWARD, IDC_W3_SYNC };
enum { IDC_W3_ROWS = 47101, IDC_W3_MESSAGE, IDC_W3_B1 = 47111, IDC_W3_B2, IDC_W3_B3, IDC_W3_B4, IDC_W3_B5, IDC_W3_CLOSE = 47120 };
enum { W3_NONE = 0, W3_ANNOTATIONS, W3_FONTS, W3_ORIGINALS, W3_SYNC };
enum { W3A_PREVIEW = 1, W3A_COMMIT, W3A_EXPORT, W3A_ORIGINALS, W3A_HISTORY };
#define W3_MAX_ROWS 4096u

typedef struct { uint64_t index; int outcome, found, committed, created, duplicate, revision_code; } w3_row;

struct w3_job {
  int action;
  unsigned long ui_generation;
  char *path, *out_jsonl, *out_markdown, *title, *directory, *wire;
  size_t wire_bytes;
  char confirm[65];
  reader_ai3_stats ai_stats;
  reader_ai3_error ai_error;
  reader_ai3_status ai_status;
  w3_row *rows;
  size_t row_count;
  reader_annotation_export_stats ex_stats;
  reader_annotation_export_error ex_error;
  reader_annotation_export_status ex_status;
  int64_t ids[ROE_MAX_ITEMS];
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
  char original_keys[ROE_MAX_ITEMS][73];
  exr_source txt_source;HANDLE txt_handle;
#endif
  size_t id_count;
  roe_result *roe;
  roe_status roe_code;
  host_session fresh;
  int fresh_open;
  int ran;
};

static struct {
  HWND dialog, rows, message, controls[6];
  int kind, running;
  unsigned long generation;
  int64_t book_id;
  /* annotations */
  char *import_path;
  char fingerprint[65];
  int preview_ok;
  w3_row *row_data;
  size_t row_count;
  /* originals */
  roe_result *roe;
  wchar_t export_directory[HOST_PATH];
  int64_t original_ids[ROE_MAX_ITEMS];
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
  char original_keys[ROE_MAX_ITEMS][73];
#endif
  size_t original_count;
  /* fonts */
  rfl_library *fonts;
  rfl_lease *lease, *pending_lease;
  exr_font *original_font, *old_font;
  char selected_hash[RFL_HASH_BYTES], pending_hash[RFL_HASH_BYTES];
  host_job *font_job;
  rfl_record *records;
  size_t record_count;
  int fonts_uncertain;
  /* history */
  reader_jh *jh;
  reader_jh_item pending_item;
  int has_pending_item;
} w3;

#ifdef EXR_WINDOWS_FONT_REVIEW
/* Review build only: observe results returned by the real library calls. */
static unsigned w3_review_leases;
static void w3_review_event(const char *operation, rfl_status status) {
  wchar_t path[HOST_PATH]; FILE *file;
  if (swprintf(path, HOST_PATH, L"%ls\\font-lease-review.log", g.data_dir) < 0) return;
  file = _wfopen(path, L"ab");
  if (!file) return;
  fprintf(file, "%s %d %u\n", operation, (int)status, w3_review_leases);
  fclose(file);
}
static rfl_status w3_review_open(rfl_library *library, const char *hash, unsigned face, rfl_lease **lease, rfl_error *error) {
  rfl_status result = rfl_font_open(library, hash, face, lease, error);
  if (result == RFL_OK) ++w3_review_leases;
  w3_review_event("open", result); return result;
}
static rfl_status w3_review_release(rfl_lease *lease, rfl_error *error) {
  rfl_status result = rfl_lease_release(lease, error);
  if (result == RFL_OK && w3_review_leases) --w3_review_leases;
  w3_review_event("release", result); return result;
}
static rfl_status w3_review_close(rfl_library *library, rfl_error *error) {
  rfl_status result = rfl_close(library, error);
  w3_review_event("close", result); return result;
}
#define rfl_font_open w3_review_open
#define rfl_lease_release w3_review_release
#define rfl_close w3_review_close
#endif

/* ---------------------------------------------------------------- helpers */

static const wchar_t *w3_format_name(exr_format format) {
  switch (format) {
    case EXR_EPUB: return L"epub"; case EXR_PDF: return L"pdf"; case EXR_CBZ: return L"cbz"; case EXR_TXT: return L"txt";
    case EXR_HTML: return L"html"; case EXR_FB2: return L"fb2"; case EXR_DOCX: return L"docx"; case EXR_RTF: return L"rtf";
    case EXR_MOBI: return L"mobi"; default: return NULL;
  }
}

/* "format:sha256" derived from the already verified source identity of the open
   book (projection key "sdk:projection:format:mode:digest:bytes"): no second hash. */
static int w3_book_key(char out[73]) {
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
  if (g.session.active && g.session.txt) {
    if (strncmp(g.session.txt_key, "txt:", 4) || strlen(g.session.txt_key) != 68) return 0;
    memcpy(out, g.session.txt_key, 69);
    return 1;
  }
#endif
  const wchar_t *wide = w3_format_name(g.current.format);
  const char *at = g.session.source_key;
  char format[8], hash[65];
  int colons = 0;
  size_t i = 0;
  if (!wide || !g.session.active) return 0;
  for (i = 0; wide[i] && i < 7; i++) format[i] = (char)wide[i];
  format[i] = 0;
  for (; *at; at++) if (*at == ':' && ++colons == 4) { at++; break; }
  if (colons != 4) return 0;
  for (i = 0; i < 64 && at[i] && at[i] != ':'; i++) hash[i] = at[i];
  if (i != 64) return 0;
  hash[64] = 0;
  snprintf(out, 73, "%s:%s", format, hash);
  return 1;
}

/* First-open book identity is prepared before later read-only import preview.
   The SDK source is independently verified and the owner checks its mapping. */
#ifdef EXR_READER_WINDOWS_RAW3
static exr_status w3_prepare_open(host_job *job, const exr_book *book, exr_error *error) {
  char hash[65], key[73];uint64_t bytes=0;
  exr_control control={job_cancel_check,NULL,job};
  const wchar_t *wide=w3_format_name(book->format);
  char *format=wide?host_utf8(wide):NULL,*database=host_utf8(g.product_path);
  wchar_t pending[HOST_PATH];winrecords_request request={0};winrecords_response response={0};
  if(!format||!database){free(format);free(database);return EXR_MEMORY;}
  EnterCriticalSection(&g.library_lock);
  exr_status status=reader_catalog_sdk_original_identity(g.library,book->id,&control,hash,&bytes,error);
  LeaveCriticalSection(&g.library_lock);
  int length=swprintf(pending,HOST_PATH,L"%ls.reading.pending",g.product_path);
  if(status==EXR_OK&&(length<0||length>=HOST_PATH)) status=EXR_LIMIT;
  if(status==EXR_OK){
    snprintf(key,sizeof(key),"%s:%s",format,hash);
    request.database=database;request.pending_path=pending;request.book_key=key;
    request.sdk_book=book->id;request.source_bytes=bytes;request.action=WINRECORDS_BOOTSTRAP;
    request.context=job;request.cancelled=winrecords_cancelled;
    status=winrecords_execute(&request,&response);
    if(status!=EXR_OK&&error)snprintf(error->message,sizeof(error->message),"%s",response.message);
  }
  winrecords_response_free(&response);free(format);free(database);return status;
}
#endif

static reader_revisions *w3_revisions_open(void) {
  char *database = host_utf8(g.product_path);
  reader_revisions *store = NULL;
  if (!database) return NULL;
  if (reader_revisions_open(database, &store, NULL) != READER_REV_OK) store = NULL;
  free(database);
  return store;
}

static void w3_random_id(char out[33]) {
  unsigned char bytes[16];
  size_t i;
  if (BCryptGenRandom(NULL, bytes, sizeof(bytes), BCRYPT_USE_SYSTEM_PREFERRED_RNG) < 0) memset(bytes, 0, sizeof(bytes));
  for (i = 0; i < 16; i++) snprintf(out + i * 2, 3, "%02x", bytes[i]);
}

static void w3_message(const wchar_t *text) {
  if (w3.message) SetWindowTextW(w3.message, text);
  set_status(text);
}

static void w3_rows_reset(void) { if (w3.rows) SendMessageW(w3.rows, LB_RESETCONTENT, 0, 0); }
static void w3_row_add(const wchar_t *text) { if (w3.rows) SendMessageW(w3.rows, LB_ADDSTRING, 0, (LPARAM)text); }

static int w3_busy(void) { return g.job || g.pending || g.closing || w3.running; }

/* ------------------------------------------------------------ job plumbing */

static void w3_job_free(w3_job *job) {
  if (!job) return;
  free(job->path); free(job->out_jsonl); free(job->out_markdown); free(job->title); free(job->directory); free(job->wire);
  free(job->rows);
  if (job->roe) roe_result_free(job->roe);
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
  if (job->txt_handle) CloseHandle(job->txt_handle);
#endif
  if (job->fresh_open) session_clear(&job->fresh);
  free(job);
}

static host_job *w3_job_new(int action) {
  host_job *job = job_new(JOB_WAVE3);
  if (!job) return NULL;
  job->w3 = calloc(1, sizeof(*job->w3));
  if (!job->w3) { job_release(job); return NULL; }
  job->w3->action = action;
  job->w3->ui_generation = w3.generation;
  job->book_id = g.has_current ? g.current.id : 0;
  job->generation = g.frame.generation;
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
  if (g.session.txt) snprintf(job->txt_key,sizeof(job->txt_key),"%s",g.session.txt_key);
#endif
  return job;
}

static exr_status w3_verify_current(host_job *job, char key[73]) {
  char source[256];
  exr_control control = { job_cancel_check, NULL, job };
  exr_status status;
  if (!g.session.active || job->book_id != g.current.id || job->generation != g.frame.generation) return EXR_ARGUMENT;
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
  if (g.session.txt) {
    if(strcmp(job->txt_key,g.session.txt_key)) return EXR_ARGUMENT;
    status=winrecords_txt_source(job,&job->w3->txt_source,&job->w3->txt_handle);
    if(status!=EXR_OK) return status;
    if(strncmp(job->txt_key,"txt:",4)||strlen(job->txt_key)!=68) return EXR_FORMAT;
    memcpy(key,job->txt_key,69);return EXR_OK;
  }
#endif
  status = winreader_identity(job->book_id, g.current.format, g.session.fixed, g.session.bounded, source, &control, &job->error);
  if (status != EXR_OK) return status;
  if (strcmp(source, g.session.source_key) || !w3_book_key(key)) return EXR_FORMAT;
  return EXR_OK;
}

typedef struct { host_job *job; w3_job *w; } w3_context;

static int w3_cancelled(void *context) { return job_cancel_flag(((w3_context *)context)->job); }

static int w3_ai_item(void *context, const reader_ai3_item *item) {
  w3_context *c = context;
  w3_row *row;
  if (c->w->row_count >= W3_MAX_ROWS) return 0;
  if (c->w->row_count == 0 || !c->w->rows) {
    c->w->rows = calloc(W3_MAX_ROWS, sizeof(*c->w->rows));
    if (!c->w->rows) return 1;
  }
  row = &c->w->rows[c->w->row_count++];
  row->index = item->index; row->outcome = (int)item->outcome; row->found = (int)item->found;
  row->committed = item->committed; row->created = item->created; row->duplicate = item->exact_duplicate;
  row->revision_code = item->revision_code;
  return 0;
}

/* Only a public SDK FOUND in an independently reopened original counts. */
static int w3_ai_resolve(void *context, const reader_rs_record *record, uint64_t index) {
  w3_context *c = context;
  size_t unit = 0;
  exr_anchor_match match;
  exr_pager *temporary = NULL;
  exr_status status;
  (void)index;
  memset(&match, 0, sizeof(match));
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
  if (g.session.txt) {
    if(!c->w->txt_handle) return 0;
    status=winrecords_txt_match(c->job,&c->w->txt_source,record,&match);
    return status==EXR_OK;
  }
#endif
  if (!c->w->fresh_open) {
    if (winreader_fresh(c->job, &c->w->fresh) != EXR_OK) return 0;
    c->w->fresh_open = 1;
  }
  status = winrecords_resolve(c->job, &c->w->fresh, record, &unit, &match, &temporary);
  exr_pager_free(temporary);
  return status == EXR_OK;
}

static int w3_roe_enter(void *context) { (void)context; EnterCriticalSection(&g.library_lock); return 0; }
static void w3_roe_leave(void *context) { (void)context; LeaveCriticalSection(&g.library_lock); }
static int w3_roe_cancelled(void *context) { return job_cancel_flag((host_job *)context); }

#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
/* Verify each product TXT on its retained immutable handle before publishing
   the mixed batch. The exporter borrows those handles only during the call. */
static exr_status w3_roe_mixed(host_job *job,roe_exporter *exporter,const roe_options *options) {
  w3_job *w=job->w3;reader_catalog *catalog=NULL;reader_catalog_error ce={0};
  reader_original_callbacks callbacks={job,job_cancel_check,NULL};
  roe_mixed_selection selection[ROE_MAX_ITEMS]={0};exr_source sources[ROE_MAX_ITEMS]={0};
  HANDLE handles[ROE_MAX_ITEMS]={0};char *database=NULL,*root=NULL;
  exr_status status=EXR_OK;int product=0;
  for(size_t i=0;i<w->id_count;i++) if(w->original_keys[i][0]) product=1;
  if(product) {
    database=host_utf8(g.product_path);root=host_utf8(g.original_root);
    if(!database||!root) { status=EXR_MEMORY;goto done; }
    if(reader_catalog_open(database,&catalog,&ce)) { status=EXR_DATABASE;goto done; }
  }
  for(size_t i=0;i<w->id_count;i++) {
    selection[i].book_id=w->ids[i];
    if(w->original_keys[i][0]) {
      void *opened=NULL;uint64_t size=0;
      reader_original_status rs=reader_original_verified_handle(catalog,root,w->original_keys[i],&callbacks,&opened,&size);
      if(rs!=ROI_OK) { status=rs==ROI_CANCELLED?EXR_CANCELLED:rs==ROI_MEMORY?EXR_MEMORY:EXR_IO;goto done; }
      handles[i]=(HANDLE)opened;sources[i].size=size;sources[i].context=opened;sources[i].read_at=txt_read;
      selection[i].source=&sources[i];selection[i].format=EXR_TXT;
      selection[i].expected_sha256=w->original_keys[i]+4;
    }
  }
  if(catalog && reader_catalog_close(&catalog,&ce)) { status=EXR_DATABASE;goto done; }
  w->roe_code=roe_run_mixed(exporter,selection,w->id_count,options,&w->roe);
done:
  if(catalog) reader_catalog_close(&catalog,&ce);
  for(size_t i=0;i<w->id_count;i++) if(handles[i]) CloseHandle(handles[i]);
  free(database);free(root);return status;
}
#endif

static exr_status w3_run(host_job *job) {
  w3_job *w = job->w3;
  char key[73];
  exr_status status;
  w3_context context;
  context.job = job; context.w = w;
  if (w->action == W3A_ORIGINALS) {
    roe_exporter *exporter = NULL;
    roe_owner owner;
#ifndef EXR_READER_WINDOWS_TXT_PROGRESS
    roe_selection selection[ROE_MAX_ITEMS];
    size_t i;
#endif
    roe_options options;
    memset(&owner, 0, sizeof(owner)); memset(&options, 0, sizeof(options));
    owner.enter = w3_roe_enter; owner.leave = w3_roe_leave;
    w->roe_code = roe_create(g.library, &owner, &exporter);
    if (w->roe_code != ROE_OK) { w->ran = 1; return EXR_OK; }
#ifndef EXR_READER_WINDOWS_TXT_PROGRESS
    for (i = 0; i < w->id_count; i++) { selection[i].book_id = w->ids[i]; selection[i].display_name = NULL; }
#endif
    options.directory = w->directory; options.naming = ROE_HASH_NAME;
    options.callbacks.cancelled = w3_roe_cancelled; options.callbacks.context = job;
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
    status = w3_roe_mixed(job, exporter, &options);
#else
    w->roe_code = roe_run(exporter, selection, w->id_count, &options, &w->roe);
    status = EXR_OK;
#endif
    roe_destroy(&exporter);
    w->ran = 1;
    return status;
  }
  status = w3_verify_current(job, key);
  if (status != EXR_OK) return status;
  if (w->action == W3A_HISTORY) {
    reader_revisions *store = w3_revisions_open();
    reader_rs_error error;
    reader_rs_status code;
    memset(&error, 0, sizeof(error));
    if (!store) return EXR_DATABASE;
    code = reader_rs_decode(store, w->wire, w->wire_bytes, &job->records.record, &error);
    reader_revisions_close(&store, NULL);
    if (code != READER_RS_OK || strcmp(job->records.record.book_key, key)) return EXR_FORMAT;
    job->direction = 1; job->note_start = job->note_end = g.frame.range_start;
    if (g.session.fixed) job->note_start = job->note_end = 0;
    w->ran = 1;
    return winrecords_route(job);
  }
  {
    reader_revisions *store = w3_revisions_open();
    if (!store) return EXR_DATABASE;
    if (w->action == W3A_EXPORT) {
      reader_annotation_export_options options;
      memset(&options, 0, sizeof(options));
      options.struct_size = sizeof(options); options.revisions = store; options.book_key = key;
      options.book_title = w->title; options.jsonl_path = w->out_jsonl; options.markdown_path = w->out_markdown;
      options.cancel = w3_cancelled; options.cancel_context = &context;
      w->ex_status = reader_annotation_export_raw3_run(&options, &w->ex_stats, &w->ex_error);
    } else {
      reader_ai3_options options;
      memset(&options, 0, sizeof(options));
      options.struct_size = sizeof(options); options.revisions = store; options.jsonl_path = w->path;
      options.target_book_key = key;
      options.mode = w->action == W3A_COMMIT ? READER_AI3_COMMIT : READER_AI3_PREVIEW;
      memcpy(options.confirm_fingerprint, w->confirm, sizeof(options.confirm_fingerprint));
      options.policy = READER_AI3_RESOLVE_REQUIRED; options.resolve = w3_ai_resolve;
      options.cancel = w3_cancelled; options.item = w3_ai_item; options.context = &context;
      w->ai_status = reader_annotation_import_raw3_run(&options, &w->ai_stats, &w->ai_error);
    }
    reader_revisions_close(&store, NULL);
    w->ran = 1;
  }
  return EXR_OK;
}

/* ------------------------------------------------------------ dialog frame */

static void w3_controls(void) {
  int busy = w3_busy(), book = g.has_current && g.session.active && g.frame.valid;
  if (!w3.dialog) return;
  EnableWindow(w3.controls[0], !busy && (w3.kind == W3_SYNC || w3.kind == W3_FONTS || w3.kind == W3_ORIGINALS ? 1 : book));
  if (w3.controls[1]) EnableWindow(w3.controls[1], !busy && (w3.kind != W3_ANNOTATIONS || book));
  if (w3.controls[2]) EnableWindow(w3.controls[2], !busy && (w3.kind == W3_FONTS || (w3.kind == W3_ANNOTATIONS && w3.preview_ok && book)));
  if (w3.controls[3]) EnableWindow(w3.controls[3], w3.kind == W3_FONTS ? !busy : w3.running);
  if (w3.controls[4]) EnableWindow(w3.controls[4], 0);
  if (w3.kind == W3_FONTS && w3.fonts_uncertain) {
    int i;
    for (i = 0; i < 4; i++) EnableWindow(w3.controls[i], FALSE);
  }
  EnableWindow(w3.controls[5], !g.closing);
}

static void w3_close(void) {
  HWND window = w3.dialog;
  if (g.job && g.job->kind == JOB_WAVE3 && g.job->w3 && g.job->w3->action != W3A_HISTORY)
    InterlockedExchange(&g.job->cancel, 1);
  w3.generation++;
  w3.dialog = NULL; w3.rows = w3.message = NULL; memset(w3.controls, 0, sizeof(w3.controls));
  w3.running = 0; w3.kind = W3_NONE;
  if (window) DestroyWindow(window);
  free(w3.import_path); w3.import_path = NULL; w3.fingerprint[0] = 0; w3.preview_ok = 0;
  free(w3.row_data); w3.row_data = NULL; w3.row_count = 0;
  free(w3.records); w3.records = NULL; w3.record_count = 0;
  if (w3.roe) { roe_result_free(w3.roe); w3.roe = NULL; }
  w3.original_count = 0;
  host_restore_content_focus();
}

static void w3_dialog_command(int id, int notification);

static LRESULT CALLBACK w3_procedure(HWND window, UINT message, WPARAM wparam, LPARAM lparam) {
  if (message == WM_CLOSE) { w3_close(); return 0; }
  if (message == WM_COMMAND) { w3_dialog_command(LOWORD(wparam), HIWORD(wparam)); return 0; }
  return DefWindowProcW(window, message, wparam, lparam);
}

static int w3_create(int kind, const wchar_t *title, const wchar_t *intro, const wchar_t *const *labels, int count, int multiple) {
  WNDCLASSW type;
  HWND window, label;
  HINSTANCE instance = GetModuleHandleW(NULL);
  int i;
  if (w3.dialog) { SetForegroundWindow(w3.dialog); return 0; }
  if (g.job || g.pending || g.closing) { set_status(L"当前有后台任务，完成后再打开。"); return 0; }
  memset(&type, 0, sizeof(type));
  type.lpfnWndProc = w3_procedure; type.hInstance = instance; type.hCursor = LoadCursor(NULL, IDC_ARROW);
  type.hbrBackground = (HBRUSH)(COLOR_BTNFACE + 1); type.lpszClassName = L"EXReaderWave3";
  if (!RegisterClassW(&type) && GetLastError() != ERROR_CLASS_ALREADY_EXISTS) return 0;
  window = CreateWindowExW(WS_EX_CONTROLPARENT, type.lpszClassName, title, WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU,
    CW_USEDEFAULT, CW_USEDEFAULT, 820, 600, g.window, NULL, instance, NULL);
  if (!window) return 0;
  w3.dialog = window; w3.kind = kind; w3.running = 0; w3.generation++;
  w3.book_id = g.has_current ? g.current.id : 0;
  label = make_static(window, 0, intro); MoveWindow(label, 12, 12, 780, 40, TRUE);
  w3.rows = CreateWindowExW(WS_EX_CLIENTEDGE, L"LISTBOX", title,
    WS_CHILD | WS_VISIBLE | WS_TABSTOP | WS_VSCROLL | LBS_NOTIFY | LBS_NOINTEGRALHEIGHT | (multiple ? LBS_EXTENDEDSEL : 0),
    12, 56, 780, 300, window, (HMENU)(INT_PTR)IDC_W3_ROWS, NULL, NULL);
  SendMessageW(w3.rows, WM_SETFONT, (WPARAM)GetStockObject(DEFAULT_GUI_FONT), TRUE);
  w3.message = make_static(window, IDC_W3_MESSAGE, L""); MoveWindow(w3.message, 12, 364, 780, 72, TRUE);
  memset(w3.controls, 0, sizeof(w3.controls));
  for (i = 0; i < count && i < 5; i++) {
    w3.controls[i] = make_button(window, IDC_W3_B1 + i, labels[i]);
    MoveWindow(w3.controls[i], 12 + i * 156, 446, 150, 32, TRUE);
  }
  w3.controls[5] = make_button(window, IDC_W3_CLOSE, L"关闭(&C)");
  MoveWindow(w3.controls[5], 692, 488, 100, 32, TRUE);
  ShowWindow(window, SW_SHOW); SetFocus(w3.rows);
  return 1;
}

/* ------------------------------------------------------- annotation dialog */

static void w3_show_annotations(void) {
  static const wchar_t *labels[] = { L"导出标注…(&E)", L"预览导入文件…(&P)", L"确认导入(&I)", L"取消任务(&X)" };
  if (!g.has_current || !g.session.active || !g.frame.valid) { set_status(L"请先打开一本书，再导入或导出它的标注。"); return; }
  if (!w3_create(W3_ANNOTATIONS, L"标注导入与导出",
      L"导出当前书的全部标注为可移植文件；导入前先预览：显示冲突、未解析位置和NULL位置，明确确认后才写入。", labels, 4, 0)) return;
  w3_message(L"尚未选择导入文件。导入只新增历史版本，不修改原书。");
  w3_controls();
}

static void w3_path_utf8(const wchar_t *path, char **out) { *out = host_utf8(path); }

static void w3_annotations_export(void) {
  wchar_t path[HOST_PATH] = { 0 }, markdown[HOST_PATH];
  OPENFILENAMEW choose;
  host_job *job;
  size_t length;
  if (w3_busy()) return;
  memset(&choose, 0, sizeof(choose));
  choose.lStructSize = sizeof(choose); choose.hwndOwner = w3.dialog;
  choose.lpstrFilter = L"可移植标注 (*.jsonl)\0*.jsonl\0\0";
  choose.lpstrFile = path; choose.nMaxFile = HOST_PATH; choose.lpstrDefExt = L"jsonl";
  choose.Flags = OFN_OVERWRITEPROMPT | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR | OFN_EXPLORER;
  if (!GetSaveFileNameW(&choose)) {
    w3_message(CommDlgExtendedError() ? L"无法打开系统保存窗口。" : L"已取消导出；没有写入任何文件。");
    return;
  }
  length = wcslen(path);
  if (length > 6 && !_wcsicmp(path + length - 6, L".jsonl")) length -= 6;
  if (length + 3 >= HOST_PATH) { w3_message(L"导出路径过长，请选择更短的文件名。"); return; }
  wmemcpy(markdown, path, length); markdown[length] = 0;
  wcscat(markdown, L".md");
  if (GetFileAttributesW(markdown) != INVALID_FILE_ATTRIBUTES &&
      MessageBoxW(w3.dialog, L"对应的 Markdown 文件已经存在。是否同时替换它？", L"确认替换 Markdown",
        MB_YESNO | MB_ICONQUESTION | MB_DEFBUTTON2) != IDYES) {
    w3_message(L"已取消导出；没有替换任何文件。");
    return;
  }
  job = w3_job_new(W3A_EXPORT);
  if (!job) { w3_message(L"内存不足，无法开始导出。"); return; }
  w3_path_utf8(path, &job->w3->out_jsonl); w3_path_utf8(markdown, &job->w3->out_markdown);
  job->w3->title = g.current.title ? host_strdup(g.current.title) : NULL;
  if (!job->w3->out_jsonl || !job->w3->out_markdown) { job_release(job); w3_message(L"路径无法转换为UTF-8。"); return; }
  w3.running = 1; w3_message(L"正在导出标注…可随时取消，取消不会留下半个文件。");
  job_submit(job); if (!g.job) w3.running = 0;
  w3_controls();
}

static void w3_annotations_preview(void) {
  wchar_t path[HOST_PATH] = { 0 };
  OPENFILENAMEW choose;
  host_job *job;
  if (w3_busy()) return;
  memset(&choose, 0, sizeof(choose));
  choose.lStructSize = sizeof(choose); choose.hwndOwner = w3.dialog;
  choose.lpstrFilter = L"可移植标注 (*.jsonl)\0*.jsonl\0所有文件\0*.*\0\0";
  choose.lpstrFile = path; choose.nMaxFile = HOST_PATH;
  choose.Flags = OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR | OFN_EXPLORER;
  if (!GetOpenFileNameW(&choose)) {
    w3_message(CommDlgExtendedError() ? L"无法打开系统文件窗口。" : L"已取消；没有读取或写入任何内容。");
    return;
  }
  job = w3_job_new(W3A_PREVIEW);
  if (!job) { w3_message(L"内存不足，无法预览。"); return; }
  w3_path_utf8(path, &job->w3->path);
  if (!job->w3->path) { job_release(job); w3_message(L"路径无法转换为UTF-8。"); return; }
  free(w3.import_path); w3.import_path = host_strdup(job->w3->path);
  w3.preview_ok = 0; w3.fingerprint[0] = 0; w3_rows_reset();
  if (!w3.import_path) { job_release(job); w3_message(L"内存不足，无法保存预览文件路径。"); w3_controls(); return; }
  w3.running = 1; w3_message(L"正在只读校验整个文件并在原书中核对位置，尚不写入…");
  job_submit(job); if (!g.job) w3.running = 0;
  w3_controls();
}

static void w3_annotations_commit(void) {
  host_job *job;
  if (w3_busy() || !w3.preview_ok || !w3.import_path || strlen(w3.fingerprint) != 64) return;
  if (MessageBoxW(w3.dialog, L"把已预览的标注写入当前书的阅读记录？\n只新增共享历史版本；重复项不会再次入队；可随时取消，已提交的保留。",
      L"确认导入标注", MB_OKCANCEL | MB_ICONQUESTION) != IDOK) { w3_message(L"已取消确认；没有写入任何内容。"); return; }
  job = w3_job_new(W3A_COMMIT);
  if (!job) return;
  job->w3->path = host_strdup(w3.import_path);
  memcpy(job->w3->confirm, w3.fingerprint, sizeof(job->w3->confirm));
  if (!job->w3->path) { job_release(job); return; }
  w3.running = 1; w3_message(L"正在逐项提交；每项是独立事务。");
  job_submit(job); if (!g.job) w3.running = 0;
  w3_controls();
}

static void w3_fill_import_rows(const w3_row *rows, size_t count) {
  static const wchar_t *outcomes[] = { L"新增", L"完全重复", L"存在冲突", L"缺少父版本", L"恢复受阻", L"已拒绝" };
  static const wchar_t *found[] = { L"删除项·无需定位", L"原书中已找到", L"原书中未找到", L"NULL位置已保留·不可定位", L"未核对" };
  size_t i;
  wchar_t line[256];
  w3_rows_reset();
  for (i = 0; i < count && i < 500; i++) {
    int o = rows[i].outcome, f = rows[i].found;
    swprintf(line, 256, L"第 %llu 项 · %ls · %ls%ls%ls", (unsigned long long)rows[i].index + 1,
      o >= 0 && o < 6 ? outcomes[o] : L"未知", f >= 0 && f < 5 ? found[f] : L"未知",
      rows[i].committed ? L" · 已提交" : L"", rows[i].revision_code ? L" · 修订模块拒绝" : L"");
    w3_row_add(line);
  }
  if (count > 500) { swprintf(line, 256, L"…另有 %llu 项未显示", (unsigned long long)(count - 500)); w3_row_add(line); }
}

static void w3_annotation_accept(host_job *job) {
  w3_job *w = job->w3;
  wchar_t message[900];
  const reader_ai3_stats *s = &w->ai_stats;
  if (job->status != EXR_OK) {
    describe_error(message, 900, L"标注任务未执行", job->status, &job->error);
    w3_message(message);
    return;
  }
  w3_fill_import_rows(w->rows, w->row_count);
  if (w->action == W3A_PREVIEW) {
    if (w->ai_status == READER_AI3_OK && s->validated && !s->unresolved && strlen(s->fingerprint) == 64) {
      memcpy(w3.fingerprint, s->fingerprint, sizeof(w3.fingerprint)); w3.preview_ok = 1;
      swprintf(message, 900, L"预览完成，尚未写入：标注 %llu · 头版本 %llu · 将新增 %llu · 重复 %llu · 找到 %llu · NULL保留 %llu · "
        L"未导入的历史 %llu。指纹 %.12hs…。核对后点“确认导入”。",
        (unsigned long long)s->annotations, (unsigned long long)s->head_wires, (unsigned long long)s->would_create,
        (unsigned long long)s->would_duplicate, (unsigned long long)s->found, (unsigned long long)s->null_preserved,
        (unsigned long long)s->omitted_history, s->fingerprint);
    } else if (w->ai_status == READER_AI3_UNRESOLVED) {
      swprintf(message, 900, L"预览拒绝：%llu 项无法在当前原书中找到，未写入任何内容。",
        (unsigned long long)s->unresolved);
    } else if (w->ai_status == READER_AI3_CANCELLED) {
      wcscpy(message, L"预览已取消；没有写入任何内容。");
    } else {
      swprintf(message, 900, L"预览拒绝（状态 %d，第 %llu 行）：%.120hs。没有写入任何内容。", (int)w->ai_status,
        (unsigned long long)w->ai_error.line, w->ai_error.message);
    }
  } else {
    if (w->ai_status == READER_AI3_OK) {
      swprintf(message, 900, L"导入完成：新提交 %llu · 重复 %llu · 共提交 %llu。", (unsigned long long)s->created,
        (unsigned long long)s->duplicates, (unsigned long long)s->committed);
    } else if (w->ai_status == READER_AI3_CANCELLED) {
      swprintf(message, 900, L"已取消：已提交 %llu 项并保留；从头重试时重复项不会再次入队（下一项 %llu）。",
        (unsigned long long)s->committed, (unsigned long long)s->next_index);
    } else {
      swprintf(message, 900, L"导入未完成（状态 %d）：%.120hs。已提交 %llu 项并保留。", (int)w->ai_status,
        w->ai_error.message, (unsigned long long)s->committed);
    }
    w3.preview_ok = 0; w3.fingerprint[0] = 0;
  }
  w3_message(message);
}

static void w3_export_accept(host_job *job) {
  w3_job *w = job->w3;
  wchar_t message[600];
  if (job->status != EXR_OK) { describe_error(message, 600, L"导出未执行", job->status, &job->error); w3_message(message); return; }
  if (w->ex_status == READER_ANNOTATION_EXPORT_OK) {
    swprintf(message, 600, L"导出完成：标注 %llu · 当前 %llu · 已删除 %llu · 冲突 %llu · JSONL%ls · Markdown%ls。",
      (unsigned long long)w->ex_stats.annotations, (unsigned long long)w->ex_stats.current,
      (unsigned long long)w->ex_stats.tombstones, (unsigned long long)w->ex_stats.concurrent,
      w->ex_stats.jsonl_published ? L"已发布" : L"未发布", w->ex_stats.markdown_published ? L"已发布" : L"未发布");
  } else if (w->ex_status == READER_ANNOTATION_EXPORT_CANCELLED) {
    wcscpy(message, L"导出已取消；未留下临时文件，原有导出保持不变。");
  } else {
    swprintf(message, 600, L"导出失败（状态 %d）：%.120hs。原有导出保持不变。", (int)w->ex_status, w->ex_error.message);
  }
  w3_message(message);
}

/* ------------------------------------------------------------- font dialog */

static int w3_font_progress(void *context, const char *stage, uint64_t done, uint64_t total) {
  (void)context; (void)stage; (void)done; (void)total;
  return 0;
}

static int w3_fonts_open(void) {
  wchar_t directory[HOST_PATH], full[HOST_PATH];
  char *utf8;
  rfl_limits limits;
  rfl_error error;
  DWORD length;
  if (w3.fonts) return 1;
  if (swprintf(directory, HOST_PATH, L"%ls\\fonts", g.data_dir) < 0) return 0;
  CreateDirectoryW(directory, NULL);
  length = GetFullPathNameW(directory, HOST_PATH, full, NULL);
  if (!length || length >= HOST_PATH) return 0;
  utf8 = host_utf8(full);
  if (!utf8) return 0;
  limits = rfl_limits_default();
  memset(&error, 0, sizeof(error));
  if (rfl_open(utf8, &limits, &w3.fonts, &error) != RFL_OK) w3.fonts = NULL;
  free(utf8);
  return w3.fonts != NULL;
}

static void w3_font_save_choice(const char *hash) {
  wchar_t path[HOST_PATH];
  FILE *file;
  if (swprintf(path, HOST_PATH, L"%ls\\wave3-font.txt", g.data_dir) < 0) return;
  file = _wfopen(path, L"wb");
  if (!file) return;
  fputs(hash ? hash : "", file);
  fclose(file);
}

static void w3_fonts_fill(void) {
  rfl_error error;
  size_t count = 0, i;
  wchar_t line[400];
  free(w3.records); w3.records = NULL; w3.record_count = 0;
  w3_rows_reset();
  w3_row_add(w3.selected_hash[0] ? L"内置 Reader.otf（默认）" : L"内置 Reader.otf（默认）· 当前使用");
  if (!w3.fonts || rfl_count(w3.fonts, &count, &error) != RFL_OK || !count) return;
  w3.records = calloc(count, sizeof(*w3.records));
  if (!w3.records) return;
  for (i = 0; i < count; i++) {
    wchar_t *name;
    if (rfl_get(w3.fonts, i, &w3.records[i], &error) != RFL_OK) break;
    name = host_wide(w3.records[i].display_name, strlen(w3.records[i].display_name));
    swprintf(line, 400, L"%ls · %llu 字节 · %.12hs%ls", name ? name : L"字体", (unsigned long long)w3.records[i].bytes,
      w3.records[i].hash, !strcmp(w3.records[i].hash, w3.selected_hash) ? L" · 当前使用" : L"");
    free(name);
    w3_row_add(line);
    w3.record_count++;
  }
}

static void w3_show_fonts(void) {
  static const wchar_t *labels[] = { L"导入字体文件…(&I)", L"使用所选字体(&U)", L"恢复内置字体(&D)", L"删除所选字体(&R)" };
  if (!w3_fonts_open()) { set_status(L"无法打开字体库目录；字体与书库保持不变。"); return; }
  if (!w3_create(W3_FONTS, L"字体库", L"导入本地字体到私有字体库，并选择阅读使用的字体。导入失败不会改变当前字体或画面。", labels, 4, 0)) return;
  if (w3.fonts_uncertain) w3_row_add(L"字体库需要在重启后恢复，当前字体继续保留。");
  else w3_fonts_fill();
  w3_message(w3.fonts_uncertain ? L"字体库上次提交状态不确定。请重启程序恢复字体库；当前字体与画面继续保留。" :
    L"选择一行后点“使用所选字体”。切换会保留当前阅读位置。");
  w3_controls();
}

static void w3_font_apply(const char *hash) {
  rfl_lease *lease = NULL;
  exr_font *font = NULL;
  rfl_error error;
  host_job *job;
  exr_anchor anchor = {0};
  exr_error anchor_error = {0};
  memset(&error, 0, sizeof(error));
  if (g.job || g.pending || g.closing) { w3_message(L"当前有后台任务，完成后再切换字体。"); return; }
  if (hash) {
    if (rfl_font_open(w3.fonts, hash, 0, &lease, &error) != RFL_OK || rfl_lease_font(lease, &font, &error) != RFL_OK || !font) {
      if (lease) rfl_lease_release(lease, &error);
      w3_message(L"字体无法打开；当前字体与画面保持不变。");
      return;
    }
  } else font = w3.original_font;
  if (hash && !strcmp(hash, w3.selected_hash)) { if (lease) rfl_lease_release(lease, &error); w3_message(L"已经在使用这个字体。"); return; }
  if (font == g.font) { if (lease) rfl_lease_release(lease, &error); w3_message(L"已经在使用这个字体。"); return; }
  if (!g.has_current || !g.session.active || g.session.fixed) {
    rfl_lease *old = w3.lease;
    g.font = font; w3.lease = lease;
    if (old) rfl_lease_release(old, &error);
    snprintf(w3.selected_hash, sizeof(w3.selected_hash), "%s", hash ? hash : "");
    w3_font_save_choice(hash);
    w3_fonts_fill(); w3_message(g.session.fixed ? L"字体已选择；当前固定页面保持不变。" : L"字体已选择；下次打开书籍时使用。");
    return;
  }
  if (!g.frame.valid || g.frame.book_id != g.current.id || g.session.book_id != g.current.id) {
    if (lease) rfl_lease_release(lease, &error);
    w3_message(L"当前阅读位置不可用；字体与画面保持不变。"); return;
  }
  if (!g.session.txt && !g.session.bounded &&
      exr_anchor_create(g.session.document, g.frame.range_start, g.frame.range_start,
                        &anchor, &anchor_error) != EXR_OK) {
    if (lease) rfl_lease_release(lease, &error);
    w3_message(L"无法建立当前位置的锚点；字体与画面保持不变。"); return;
  }
  job = job_new(JOB_LAYOUT);
  if (!job) { exr_anchor_free(&anchor); if (lease) rfl_lease_release(lease, &error); w3_message(L"内存不足，字体未切换。"); return; }
  job->book_id = g.current.id; job->font_percent = g.font_percent; job->font_relayout = 1;
  job->anchor = anchor; job->has_anchor = !g.session.txt && !g.session.bounded;
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
  if(g.session.txt) {
    job->txt_offset=(uint64_t)g.frame.range_start;
    snprintf(job->txt_key,sizeof(job->txt_key),"%s",g.session.txt_key);
    g.txt_force_save=1;
  }
#endif
  w3.old_font = g.font; w3.pending_lease = lease; w3.font_job = job;
  snprintf(w3.pending_hash, sizeof(w3.pending_hash), "%s", hash ? hash : "");
  g.font = font;
  w3_message(L"正在用新字体重新排版当前书；失败时保留旧画面。");
  job_submit(job);
}

static void w3_fonts_command(int id) {
  LRESULT selected = w3.rows ? SendMessageW(w3.rows, LB_GETCURSEL, 0, 0) : LB_ERR;
  rfl_error error;
  memset(&error, 0, sizeof(error));
  if (w3.fonts_uncertain) {
    w3_message(L"字体库提交状态不确定，请重启程序恢复后再操作。当前字体与画面继续保留。");
    return;
  }
  if (id == IDC_W3_B1) {
    wchar_t path[HOST_PATH] = { 0 }, *name, *dot;
    OPENFILENAMEW choose;
    char *utf8, *label;
    rfl_record record;
    rfl_control control;
    int created = 0;
    rfl_status status;
    memset(&choose, 0, sizeof(choose));
    choose.lStructSize = sizeof(choose); choose.hwndOwner = w3.dialog;
    choose.lpstrFilter = L"字体 (*.ttf;*.otf;*.ttc)\0*.ttf;*.otf;*.ttc\0\0";
    choose.lpstrFile = path; choose.nMaxFile = HOST_PATH;
    choose.Flags = OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR | OFN_EXPLORER;
    if (!GetOpenFileNameW(&choose)) { w3_message(CommDlgExtendedError() ? L"无法打开系统文件窗口。" : L"已取消；字体库没有变化。"); return; }
    name = wcsrchr(path, L'\\'); name = name ? name + 1 : path;
    utf8 = host_utf8(path);
    dot = wcsrchr(name, L'.');
    label = NULL;
    if (dot) *dot = 0;
    label = host_utf8(name);
    if (!utf8 || !label || !label[0] || strlen(label) > 255) {
      free(utf8); free(label); w3_message(L"文件名无法作为字体名称；字体库没有变化。"); return;
    }
    memset(&record, 0, sizeof(record)); memset(&control, 0, sizeof(control));
    control.progress = w3_font_progress;
    SetCursor(LoadCursor(NULL, IDC_WAIT));
    status = rfl_import_file(w3.fonts, utf8, label, &control, &record, &created, &error);
    SetCursor(LoadCursor(NULL, IDC_ARROW));
    free(utf8); free(label);
    if (status == RFL_COMMIT_UNCERTAIN) {
      w3.fonts_uncertain = 1;
      w3_message(L"字体导入的提交状态不确定。请重启程序恢复字体库；当前字体与画面继续保留。");
      w3_controls();
    } else if (status != RFL_OK) {
      wchar_t message[400];
      swprintf(message, 400, L"字体导入失败（%d）：%.150hs。当前字体与字体库保持不变。", (int)status, error.message);
      w3_message(message);
    } else {
      w3_fonts_fill();
      w3_message(created ? L"字体已导入并通过校验。选择它即可使用。" : L"字体库中已有相同字体，未重复导入。");
    }
    return;
  }
  if (id == IDC_W3_B3) { w3_font_apply(NULL); return; }
  if (selected == LB_ERR || selected < 1 || (size_t)selected > w3.record_count) {
    if (id == IDC_W3_B2 && selected == 0) { w3_font_apply(NULL); return; }
    w3_message(L"请先在列表中选择一个已导入的字体。");
    return;
  }
  if (id == IDC_W3_B2) { w3_font_apply(w3.records[selected - 1].hash); return; }
  if (id == IDC_W3_B4) {
    rfl_status status;
    if (!strcmp(w3.records[selected - 1].hash, w3.selected_hash)) { w3_message(L"正在使用的字体不能删除；请先恢复内置字体。"); return; }
    status = rfl_remove(w3.fonts, w3.records[selected - 1].hash, &error);
    if (status == RFL_OK) { w3_fonts_fill(); w3_message(L"字体已从字体库删除。"); }
    else if (status == RFL_COMMIT_UNCERTAIN) {
      w3.fonts_uncertain = 1;
      w3_message(L"字体删除的提交状态不确定。请重启程序恢复字体库；当前字体与画面继续保留。");
      w3_controls();
    }
    else w3_message(status == RFL_BUSY ? L"字体仍在使用，未删除。" : L"字体无法删除；字体库保持原状。");
  }
}

/* One owner decision after the reopen job: success releases the old lease only
   after the previous pager/session was replaced; failure keeps the old frame
   and releases the candidate (pagers first) before the new lease. */
static void w3_after_font_job(host_job *job) {
  rfl_error error;
  int accepted = job->kind == JOB_LAYOUT && job->have_frame && !job->candidate_pager;
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
  if (g.session.txt)
    accepted = accepted && job->txt_key[0] && !strcmp(job->txt_key,g.session.txt_key);
#endif
  int success = job->status == EXR_OK && !job_cancel_flag(job) && accepted && g.session.active &&
    g.current.id == job->book_id;
  memset(&error, 0, sizeof(error));
  w3.font_job = NULL;
  if (success) {
    rfl_lease *old = w3.lease;
    w3.lease = w3.pending_lease; w3.pending_lease = NULL;
    if (old) rfl_lease_release(old, &error);
    snprintf(w3.selected_hash, sizeof(w3.selected_hash), "%s", w3.pending_hash);
    w3_font_save_choice(w3.selected_hash[0] ? w3.selected_hash : NULL);
    if (w3.kind == W3_FONTS) w3_fonts_fill();
    set_status(L"已切换字体，并保持阅读位置。");
    if (w3.message) SetWindowTextW(w3.message, L"已切换字体，并保持阅读位置。");
  } else {
    g.font = w3.old_font;
    session_clear(&job->candidate);
    exr_pager_free(job->candidate_pager); job->candidate_pager = NULL;
    if (w3.pending_lease) rfl_lease_release(w3.pending_lease, &error);
    w3.pending_lease = NULL;
    set_status(L"字体切换失败或已取消；已保留旧字体与当前画面。");
    if (w3.message) SetWindowTextW(w3.message, L"字体切换失败或已取消；已保留旧字体与当前画面。");
  }
  w3.old_font = NULL;
  w3_controls();
}

/* ----------------------------------------------------------- original export */

static int w3_choose_directory(wchar_t directory[HOST_PATH]) {
  IFileOpenDialog *dialog = NULL;
  IShellItem *item = NULL;
  PWSTR path = NULL;
  DWORD options = 0;
  HRESULT hr = CoInitializeEx(NULL, COINIT_APARTMENTTHREADED);
  int chosen = 0, uninit = SUCCEEDED(hr);
  if (FAILED(hr) && hr != RPC_E_CHANGED_MODE) return -1;
  hr = CoCreateInstance(&CLSID_FileOpenDialog, NULL, CLSCTX_INPROC_SERVER, &IID_IFileOpenDialog, (void **)&dialog);
  if (FAILED(hr)) { if (uninit) CoUninitialize(); return -1; }
  IFileOpenDialog_GetOptions(dialog, &options);
  IFileOpenDialog_SetOptions(dialog, options | FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM | FOS_PATHMUSTEXIST);
  IFileOpenDialog_SetTitle(dialog, L"选择导出原件的目录");
  hr = IFileOpenDialog_Show(dialog, w3.dialog);
  if (SUCCEEDED(hr) && SUCCEEDED(IFileOpenDialog_GetResult(dialog, &item))) {
    if (SUCCEEDED(IShellItem_GetDisplayName(item, SIGDN_FILESYSPATH, &path)) && path && wcslen(path) < HOST_PATH) {
      wcscpy(directory, path); chosen = 1;
    }
    if (path) CoTaskMemFree(path);
    IShellItem_Release(item);
  }
  IFileOpenDialog_Release(dialog);
  if (uninit) CoUninitialize();
  return hr == HRESULT_FROM_WIN32(ERROR_CANCELLED) ? 0 : chosen ? 1 : -1;
}

static void w3_show_originals(void) {
  static const wchar_t *labels[] = { L"选择目录并导出(&E)", L"", L"", L"取消任务(&X)" };
  size_t i;
  wchar_t line[320];
  if (!g.shelf_count) { set_status(L"书架中没有可导出的原件。"); return; }
  if (!w3_create(W3_ORIGINALS, L"导出原件", L"选择书架中的书（可多选），再选择目录；导出的是导入时保存的原始文件，不覆盖已有文件。", labels, 4, 1)) return;
  ShowWindow(w3.controls[1], SW_HIDE); ShowWindow(w3.controls[2], SW_HIDE);
  w3.original_count = 0;
  for (i = 0; i < g.shelf_count && i < ROE_MAX_ITEMS; i++) {
    wchar_t *title = g.shelf[i].title ? host_wide(g.shelf[i].title, strlen(g.shelf[i].title)) : NULL;
    swprintf(line, 320, L"%ls", title ? title : L"未命名");
    free(title);
    w3_row_add(line);
    w3.original_ids[w3.original_count] = g.shelf[i].id;
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
    w3.original_keys[w3.original_count][0]=0;
    if(g.shelf[i].id==0 && g.shelf[i].format==EXR_TXT && g.shelf_cursors && g.shelf_cursors[i].key)
      snprintf(w3.original_keys[w3.original_count],sizeof(w3.original_keys[0]),"%s",g.shelf_cursors[i].key);
#endif
    w3.original_count++;
  }
  w3_message(L"选择一本或多本书，然后点“选择目录并导出”。");
  w3_controls();
}

static void w3_originals_export(void) {
  host_job *job;
  int selected[ROE_MAX_ITEMS];
  int count, i, chosen;
  if (w3_busy()) return;
  count = (int)SendMessageW(w3.rows, LB_GETSELITEMS, ROE_MAX_ITEMS, (LPARAM)selected);
  if (count <= 0) { w3_message(L"请先选择至少一本书。"); return; }
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
  for(i=0;i<count;i++) {
    if((size_t)selected[i]>=w3.original_count ||
       (w3.original_ids[selected[i]]<=0 && strncmp(w3.original_keys[selected[i]],"txt:",4))) {
      w3_message(L"\u6240\u9009\u4e66\u7c4d\u5c1a\u672a\u4e0b\u8f7d\uff0c\u672a\u5f00\u59cb\u5bfc\u51fa\u3002");return;
    }
  }
#endif
  chosen = w3_choose_directory(w3.export_directory);
  if (chosen == 0) { w3_message(L"已取消选择目录；没有创建任何文件。"); return; }
  if (chosen < 0) { w3_message(L"无法打开系统目录选择器。"); return; }
  job = w3_job_new(W3A_ORIGINALS);
  if (!job) { w3_message(L"内存不足，无法开始导出。"); return; }
  for (i = 0; i < count; i++) {
    if ((size_t)selected[i] >= w3.original_count) continue;
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
    if(w3.original_ids[selected[i]]<=0 && !w3.original_keys[selected[i]][0]) continue;
    snprintf(job->w3->original_keys[job->w3->id_count],sizeof(job->w3->original_keys[0]),"%s",w3.original_keys[selected[i]]);
#else
    if(w3.original_ids[selected[i]]<=0) continue;
#endif
    job->w3->ids[job->w3->id_count++] = w3.original_ids[selected[i]];
  }
  w3_path_utf8(w3.export_directory, &job->w3->directory);
  if (!job->w3->id_count || !job->w3->directory) { job_release(job); w3_message(L"所选书籍尚未下载到本机，无法导出原件。"); return; }
  w3.running = 1; w3_message(L"正在导出原件…可取消；已发布的文件不会回滚。");
  job_submit(job); if (!g.job) w3.running = 0;
  w3_controls();
}

static void w3_originals_accept(host_job *job) {
  w3_job *w = job->w3;
  wchar_t message[500], line[640];
  size_t i, ok = 0;
  if (job->status != EXR_OK) { describe_error(message, 500, L"原件导出未执行", job->status, &job->error); w3_message(message); return; }
  w3_rows_reset();
  w3.original_count = 0;
  if (w->roe) {
    for (i = 0; i < w->roe->count; i++) {
      const roe_item *item = &w->roe->items[i];
      wchar_t *path = host_wide(item->output_path, strlen(item->output_path));
      const wchar_t *state = item->status == ROE_OK ? (item->created ? L"已导出" : L"已存在·内容一致") :
        item->status == ROE_CONFLICT ? L"拒绝·同名文件内容不同" : item->status == ROE_CANCELLED ? L"已取消" : L"失败";
      if (item->status == ROE_OK) ok++;
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
      if(w->original_keys[i][0]) {
        wchar_t *key=host_wide(w->original_keys[i],strlen(w->original_keys[i]));
        swprintf(line,640,L"%ls · %ls · %llu 字节 · %ls",key?key:L"TXT",state,
          (unsigned long long)item->bytes,path?path:L"");
        free(key);
      } else
#endif
      swprintf(line, 640, L"书 %lld · %ls · %llu 字节 · %ls", (long long)item->book_id, state,
        (unsigned long long)item->bytes, path ? path : L"");
      free(path);
      w3_row_add(line);
      w3.original_ids[w3.original_count] = item->book_id;
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
      snprintf(w3.original_keys[w3.original_count],sizeof(w3.original_keys[0]),"%s",w->original_keys[i]);
#endif
      w3.original_count++;
    }
  }
  swprintf(message, 500, L"原件导出结束：%llu / %llu 项成功（状态 %d）。已发布的文件不会回滚。", (unsigned long long)ok,
    (unsigned long long)(w->roe ? w->roe->count : 0), (int)w->roe_code);
  w3_message(message);
}

/* ------------------------------------------------------------------- sync */

static void w3_sync_refresh(void) {
  reader_sync_view_snapshot *snapshot = NULL;
  reader_sync_view_error error;
  reader_sync_view_summary summary;
  reader_sync_view_status captured;
  char *database;
  wchar_t line[400], message[500];
  w3_rows_reset();
  if (!acct.session) {
    w3_row_add(L"同步状态：未知（本次运行尚未启动同步会话）");
    w3_row_add(L"待处理与冲突：未知。此页面只读，不会替你重试、确认或发布任何内容。");
    w3_message(L"状态未知不等于已同步：请先在“同步账号”中启动同步，再刷新本页。");
    return;
  }
  memset(&error, 0, sizeof(error)); memset(&summary, 0, sizeof(summary));
  database = host_utf8(g.product_path);
  captured = w3_sync_capture(acct.session, database, &snapshot, &error);
  free(database);
  if (captured != READER_SYNC_VIEW_OK ||
      reader_sync_view_summary_get(snapshot, &summary) != READER_SYNC_VIEW_OK) {
    reader_sync_view_release(&snapshot);
    w3_row_add(L"同步状态：未知（无法读取，读取没有改变任何数据）");
    swprintf(message, 500, L"状态读取失败：%.90hs。", error.message);
    w3_message(message);
    return;
  }
  swprintf(line, 400, L"同步阶段：%hs · 原因：%hs", reader_sync_view_phase_text(summary.phase), reader_sync_view_reason_text(summary.reason));
  w3_row_add(line);
  swprintf(line, 400, L"扫描：已完成 %llu 轮，当前分片 %u / %u（一轮扫描完成不等于整库已同步；整库完成：%ls）",
    (unsigned long long)summary.completed_sweeps, summary.completed_shards, summary.shard_count, summary.library_complete ? L"是" : L"否");
  w3_row_add(line);
  if (summary.outbox_included)
    swprintf(line, 400, L"待处理记录：%llu 条%ls · 其中重试过 %llu 条", (unsigned long long)summary.pending_records,
      summary.more_may_exist ? L"（队列可能更长）" : L"", (unsigned long long)summary.retried_records);
  else wcscpy(line, L"待处理记录：未知（本次未读取待处理队列）");
  w3_row_add(line);
  if (summary.conflicts_checked)
    swprintf(line, 400, L"冲突记录：%llu 条", (unsigned long long)summary.conflict_records);
  else wcscpy(line, L"冲突记录：未知（未检查）");
  w3_row_add(line);
  {
    reader_sync_view_row rows[READER_SYNC_VIEW_MAX_ROWS];
    size_t copied = 0, i;
    if (reader_sync_view_rows(snapshot, 0, rows, READER_SYNC_VIEW_MAX_ROWS, &copied) == READER_SYNC_VIEW_OK) {
      for (i = 0; i < copied; i++) {
        swprintf(line, 400, L"待处理 · %hs %hs · 尝试 %lld 次 · %ls · 原因 %hs", rows[i].entity_kind, rows[i].operation,
          (long long)rows[i].attempts, rows[i].conflict ? L"存在冲突" : L"无冲突", reader_sync_view_reason_text(rows[i].last_reason));
        w3_row_add(line);
      }
    }
  }
  reader_sync_view_release(&snapshot);
  w3_message(L"只读快照：未改变任何数据。状态未知、待处理、冲突分别显示。");
}

static void w3_show_sync(void) {
  static const wchar_t *labels[] = { L"刷新(&F)" };
  if (!w3_create(W3_SYNC, L"同步状态", L"只读的同步状态：不重试、不确认、不修改任何记录。", labels, 1, 0)) return;
  w3_sync_refresh();
  w3_controls();
}

/* ---------------------------------------------------------------- history */

static void w3_history_land(host_job *job) {
  char key[73], id[33];
  reader_revisions *store;
  reader_rs_capture capture;
  exr_anchor anchor;
  exr_fixed_anchor fixed;
  reader_rs_envelope envelope;
  reader_rs_error error;
  reader_jh_result result;
  reader_jh_error history_error;
  exr_control control;
  exr_status status = EXR_OK;
  char *wire = NULL;
  size_t bytes = 0, unit, start;
  reader_rs_status code;
  reader_jh_kind kind = job->kind == JOB_OPEN || (!job->use_offset && !job->resolved_selection) ? READER_JH_PAGE : READER_JH_TOC;
  if (!w3.jh || !g.session.active || !g.frame.valid || !w3_book_key(key)) return;
  memset(&capture, 0, sizeof(capture)); memset(&anchor, 0, sizeof(anchor)); memset(&fixed, 0, sizeof(fixed));
  memset(&control, 0, sizeof(control)); memset(&error, 0, sizeof(error));
  unit = g.session.fixed ? g.frame.page : g.frame.part;
  start = g.frame.range_start;
  EnterCriticalSection(&g.library_lock);
  if (g.session.fixed) {
    exr_fixed_text *text = NULL;
    size_t count = 0;
    const exr_fixed_page *pages = exr_fixed_pages(g.session.fixed_document, &count);
    exr_error sdk_error = { 0 };
    if (!pages || unit >= count) status = EXR_ARGUMENT;
    if (status == EXR_OK) status = exr_fixed_load_text(g.session.fixed_document, unit, &control, &text, &sdk_error);
    if (status == EXR_OK) status = exr_fixed_anchor_create(pages[unit].id, text, 0, 0, &fixed, &sdk_error);
    exr_fixed_text_free(text);
    capture.mode = READER_RS_FIXED_PAGE; capture.fixed = &fixed; capture.page = unit;
  } else if (g.session.bounded) {
    size_t count = 0;
    const exr_part *parts = exr_publication_parts(g.session.publication, &count);
    exr_error sdk_error = { 0 };
    if (!parts || unit >= count) status = EXR_ARGUMENT;
    if (status == EXR_OK) status = exr_pager_anchor_create(g.session.pager, start, start, &control, &anchor, &sdk_error);
    capture.mode = READER_RS_EPUB_CHAPTER; capture.anchor = &anchor;
    capture.part_path = status == EXR_OK ? parts[unit].path : NULL;
  } else {
    exr_error sdk_error = { 0 };
    status = exr_anchor_create(g.session.document, start, start, &anchor, &sdk_error);
    capture.mode = READER_RS_REFLOW_GLOBAL; capture.anchor = &anchor;
  }
  LeaveCriticalSection(&g.library_lock);
  if (status == EXR_OK && (store = w3_revisions_open()) != NULL) {
    w3_random_id(id);
    memset(&envelope, 0, sizeof(envelope));
    envelope.revision_id = id; envelope.operation = "put"; envelope.entity_kind = "progress";
    envelope.book_key = key; envelope.parser_version = exr_version();
    code = g.session.fixed ? reader_rs_encode_fixed_v3(store, &envelope, &capture, &wire, &bytes, &error)
                           : reader_rs_encode_capture_raw_candidate(store, &envelope, &capture, 2, unit, &wire, &bytes, &error);
    if (code == READER_RS_OK) {
      memset(&history_error, 0, sizeof(history_error));
      reader_jh_commit_wire_raw_v3(w3.jh, store, kind, wire, bytes, &result, &history_error);
    }
    reader_rs_free(wire);
    reader_revisions_close(&store, NULL);
  }
  exr_anchor_free(&anchor);
  exr_fixed_anchor_free(&fixed);
}

#if defined(EXR_READER_WINDOWS_TXT_PROGRESS) && defined(EXR_READER_WINDOWS_SEARCH)
/* Called after the target frame is accepted on the history owner thread.
   Both anchors were captured by the serialized search worker. */
static void w3_txt_search_history_land(host_job *job) {
  reader_revisions *store;
  reader_rs_capture capture = {0};
  reader_rs_envelope envelope = {0};
  reader_rs_error error = {0};
  reader_jh_result result;
  reader_jh_error history_error;
  char key[73], id[33], *wire[2] = {NULL, NULL};
  size_t bytes[2] = {0, 0};
  exr_anchor *anchors[2] = {&job->txt_history_before, &job->txt_history_after};
  if (!w3.jh || !w3_book_key(key) || strcmp(key, job->txt_key)) {
    job->txt_history_failed = 1; return;
  }
  store = w3_revisions_open();
  if (!store) { job->txt_history_failed = 1; return; }
  capture.mode = READER_RS_REFLOW_GLOBAL;
  envelope.operation = "put"; envelope.entity_kind = "progress";
  envelope.book_key = key; envelope.parser_version = exr_version();
  for (size_t i = 0; i < 2; i++) {
    w3_random_id(id); envelope.revision_id = id; capture.anchor = anchors[i];
    reader_rs_status code = reader_rs_encode_capture_raw_candidate(store, &envelope, &capture, 2, 0,
                                                                    &wire[i], &bytes[i], &error);
    if (code != READER_RS_OK) {
      if (getenv("EXR_TRACE_TXT")) {
        fprintf(stderr,"TXT_HISTORY encode index=%llu code=%d message=%s\n",
                (unsigned long long)i,(int)code,error.message); fflush(stderr);
      }
      job->txt_history_failed = 1; break;
    }
  }
  if (!job->txt_history_failed) {
    for (size_t i = 0; i < 2; i++) {
      memset(&history_error, 0, sizeof(history_error));
      reader_jh_status code = reader_jh_commit_wire_raw_v3(w3.jh, store,
        i ? READER_JH_SEARCH : READER_JH_PAGE, wire[i], bytes[i], &result, &history_error);
      if (code != READER_JH_OK) {
        if (getenv("EXR_TRACE_TXT")) {
          fprintf(stderr,"TXT_HISTORY commit index=%llu code=%d message=%s\n",
                  (unsigned long long)i,(int)code,history_error.message); fflush(stderr);
        }
        job->txt_history_failed = 1; break;
      }
    }
  }
  reader_rs_free(wire[0]); reader_rs_free(wire[1]);
  reader_revisions_close(&store, NULL);
}
#endif

static void w3_history_go(int direction) {
  reader_jh_error error;
  reader_jh_item item;
  reader_jh_status status;
  host_job *job;
  char key[73];
  if (!w3.jh || w3_busy() || !g.has_current || !g.session.active || !g.frame.valid || !w3_book_key(key)) {
    set_status(L"当前不能使用跳转历史。");
    return;
  }
  memset(&error, 0, sizeof(error)); memset(&item, 0, sizeof(item));
  status = reader_jh_peek(w3.jh, direction < 0 ? READER_JH_BACK : READER_JH_FORWARD, &item, &error);
  if (status == READER_JH_EMPTY) { set_status(direction < 0 ? L"没有可后退的位置。" : L"没有可前进的位置。"); return; }
  if (status != READER_JH_OK) { set_status(L"跳转历史暂不可用；位置没有改变。"); return; }
  if (strcmp(item.book_key, key)) {
    reader_jh_item_release(&item);
    set_status(L"该历史位置属于另一本书；请先打开那本书。历史游标没有移动。");
    return;
  }
  job = w3_job_new(W3A_HISTORY);
  if (!job) { reader_jh_item_release(&item); return; }
  job->w3->wire = malloc(item.wire_bytes ? item.wire_bytes : 1);
  if (!job->w3->wire) { job_release(job); reader_jh_item_release(&item); return; }
  memcpy(job->w3->wire, item.wire, item.wire_bytes); job->w3->wire_bytes = item.wire_bytes;
  if (w3.has_pending_item) reader_jh_item_release(&w3.pending_item);
  w3.pending_item = item; w3.has_pending_item = 1;
  set_status(direction < 0 ? L"正在后退到上一个位置，成功定位后才会记录。" : L"正在前进到下一个位置，成功定位后才会记录。");
  job_submit(job);
}

static void w3_history_accept(host_job *job) {
  reader_jh_error error;
  int moved = 0;
  memset(&error, 0, sizeof(error));
  if (job->status == EXR_OK && job->have_frame) {
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
    /* The bounded page quote identifies the page; it is not a selection. */
    if (g.session.txt && w3.has_pending_item && w3.pending_item.kind == READER_JH_PAGE)
      job->resolved_selection = 0;
#endif
    job->kind = JOB_GO;
    handle_job_complete(job);
    moved = g.has_current && g.frame.valid && job->frame.valid == 0;
#if defined(EXR_READER_WINDOWS_TXT_PROGRESS) && defined(EXR_READER_WINDOWS_SEARCH)
    if (moved && g.session.txt && job->note_start >= g.frame.range_start &&
        job->note_start < g.frame.range_end) {
      g.frame.txt_history_point = job->note_start;
      g.frame.txt_has_history_point = 1;
      if (getenv("EXR_TRACE_TXT")) {
        fprintf(stderr,"TXT_HISTORY restored_point=%llu\n",(unsigned long long)job->note_start);
        fflush(stderr);
      }
    }
#endif
  } else {
    wchar_t message[600];
    describe_error(message, 600, job->status == EXR_CANCELLED ? L"已取消，历史游标没有移动" : L"未能在当前原书中找到该历史位置，历史游标没有移动", job->status, &job->error);
    set_status(message);
  }
  if (moved && w3.jh && w3.has_pending_item) reader_jh_complete(w3.jh, &w3.pending_item, &error);
  if (w3.has_pending_item) { reader_jh_item_release(&w3.pending_item); w3.has_pending_item = 0; }
}

/* ------------------------------------------------------------------ glue */

static void w3_dialog_command(int id, int notification) {
  (void)notification;
  if (id == IDC_W3_CLOSE || id == IDCANCEL) { w3_close(); return; }
  if (id == IDC_W3_B4 && w3.kind != W3_FONTS) { job_cancel_button(); return; }
  if (w3.running || g.job || g.pending) return;
  switch (w3.kind) {
    case W3_ANNOTATIONS:
      if (id == IDC_W3_B1) w3_annotations_export();
      else if (id == IDC_W3_B2) w3_annotations_preview();
      else if (id == IDC_W3_B3) w3_annotations_commit();
      break;
    case W3_FONTS: if (id >= IDC_W3_B1 && id <= IDC_W3_B4) w3_fonts_command(id); break;
    case W3_ORIGINALS: if (id == IDC_W3_B1) w3_originals_export(); break;
    case W3_SYNC: if (id == IDC_W3_B1) w3_sync_refresh(); break;
  }
}

static void w3_accept(host_job *job) {
  w3_job *w = job->w3;
  int current = w3.dialog && w->ui_generation == w3.generation;
  w3.running = 0;
  if (w->action == W3A_HISTORY) { w3_history_accept(job); return; }
  if (!current) { w3_controls(); return; }
  if (w->action == W3A_PREVIEW || w->action == W3A_COMMIT) {
    w3_annotation_accept(job);
    if (w3.row_data) { free(w3.row_data); w3.row_data = NULL; }
  } else if (w->action == W3A_EXPORT) w3_export_accept(job);
  else if (w->action == W3A_ORIGINALS) w3_originals_accept(job);
  w3_controls();
}

static void w3_after_complete(host_job *job) {
  if (job == w3.font_job) { w3_after_font_job(job); return; }
}

/* Called before job_release when the serialized worker could not start. */
static void w3_failed_to_start(host_job *job) {
  if (job == w3.font_job) { w3_after_font_job(job); return; }
  if (!job->w3) return;
  w3.running = 0;
  if (job->w3->action == W3A_HISTORY && w3.has_pending_item) {
    reader_jh_item_release(&w3.pending_item);
    w3.has_pending_item = 0;
  }
  if (w3.dialog && job->w3->ui_generation == w3.generation)
    w3_message(L"无法启动后台任务；请重试。");
  w3_controls();
}

static void w3_book_changed(void) {
  if (w3.dialog && w3.kind == W3_ANNOTATIONS) w3_close();
}

static int w3_command(int id) {
  switch (id) {
    case IDC_W3_ANNOTATIONS: w3_show_annotations(); return 1;
    case IDC_W3_FONTS: w3_show_fonts(); return 1;
    case IDC_W3_ORIGINALS: w3_show_originals(); return 1;
    case IDC_W3_SYNC: w3_show_sync(); return 1;
    case IDC_W3_BACK: w3_history_go(-1); return 1;
    case IDC_W3_FORWARD: w3_history_go(1); return 1;
  }
  return 0;
}

static int w3_translate(MSG *message) {
  if (message->message == WM_KEYDOWN && (GetKeyState(VK_CONTROL) & 0x8000) && !(GetKeyState(VK_SHIFT) & 0x8000) &&
      (message->wParam == VK_OEM_4 || message->wParam == VK_OEM_6) && g.window && IsWindowEnabled(g.window) &&
      (message->hwnd == g.window || IsChild(g.window, message->hwnd))) {
    w3_history_go(message->wParam == VK_OEM_4 ? -1 : 1);
    return 1;
  }
  if (!w3.dialog || (message->hwnd != w3.dialog && !IsChild(w3.dialog, message->hwnd))) return 0;
  if (message->message == WM_KEYDOWN && message->wParam == VK_ESCAPE) { if (w3.running) job_cancel_button(); else w3_close(); return 1; }
  return IsDialogMessageW(w3.dialog, message) != 0;
}

static void w3_menu_install(HMENU library, HMENU reading) {
  AppendMenuW(library, MF_STRING, IDC_W3_ORIGINALS, L"导出原件…");
  AppendMenuW(library, MF_STRING, IDC_W3_SYNC, L"同步状态…");
  AppendMenuW(reading, MF_STRING, IDC_W3_BACK, L"后退到上一个位置\tCtrl+[");
  AppendMenuW(reading, MF_STRING, IDC_W3_FORWARD, L"前进到下一个位置\tCtrl+]");
  AppendMenuW(reading, MF_STRING, IDC_W3_ANNOTATIONS, L"标注导入与导出…");
  AppendMenuW(reading, MF_STRING, IDC_W3_FONTS, L"字体库…");
}

static void w3_menu_update(HMENU menu) {
  reader_jh_state state;
  reader_jh_error error;
  int idle = !g.job && !g.pending && !g.closing, book = g.has_current && g.session.active && g.frame.valid;
  int back = 0, forward = 0;
  memset(&state, 0, sizeof(state)); memset(&error, 0, sizeof(error));
  if (w3.jh && reader_jh_state_get(w3.jh, &state, &error) == READER_JH_OK) { back = state.can_back; forward = state.can_forward; }
  EnableMenuItem(menu, IDC_W3_BACK, MF_BYCOMMAND | (idle && book && back ? MF_ENABLED : MF_GRAYED));
  EnableMenuItem(menu, IDC_W3_FORWARD, MF_BYCOMMAND | (idle && book && forward ? MF_ENABLED : MF_GRAYED));
  EnableMenuItem(menu, IDC_W3_ANNOTATIONS, MF_BYCOMMAND | (idle && book ? MF_ENABLED : MF_GRAYED));
  EnableMenuItem(menu, IDC_W3_FONTS, MF_BYCOMMAND | (idle ? MF_ENABLED : MF_GRAYED));
  EnableMenuItem(menu, IDC_W3_ORIGINALS, MF_BYCOMMAND | (idle && g.shelf_count ? MF_ENABLED : MF_GRAYED));
  EnableMenuItem(menu, IDC_W3_SYNC, MF_BYCOMMAND | (!g.closing ? MF_ENABLED : MF_GRAYED));
}

static void w3_startup(void) {
  reader_jh_error error;
  wchar_t path[HOST_PATH];
  char saved[80] = { 0 };
  FILE *file;
  memset(&error, 0, sizeof(error));
  w3.original_font = g.font;
  reader_jh_open(NULL, &w3.jh, &error);
  if (swprintf(path, HOST_PATH, L"%ls\\wave3-font.txt", g.data_dir) < 0) return;
  file = _wfopen(path, L"rb");
  if (!file) return;
  if (!fgets(saved, sizeof(saved), file)) saved[0] = 0;
  fclose(file);
  if (strlen(saved) == 64 && w3_fonts_open()) {
    rfl_lease *lease = NULL;
    exr_font *font = NULL;
    rfl_error font_error;
    memset(&font_error, 0, sizeof(font_error));
    if (rfl_font_open(w3.fonts, saved, 0, &lease, &font_error) == RFL_OK && rfl_lease_font(lease, &font, &font_error) == RFL_OK && font) {
      g.font = font; w3.lease = lease; snprintf(w3.selected_hash, sizeof(w3.selected_hash), "%s", saved);
    } else if (lease) rfl_lease_release(lease, &font_error);
  }
}

static void w3_shutdown(void) {
  rfl_error error;
  reader_jh_error history_error;
  memset(&error, 0, sizeof(error)); memset(&history_error, 0, sizeof(history_error));
  w3_close();
  if (w3.has_pending_item) { reader_jh_item_release(&w3.pending_item); w3.has_pending_item = 0; }
  if (w3.original_font) g.font = w3.original_font;
  if (w3.pending_lease) { rfl_lease_release(w3.pending_lease, &error); w3.pending_lease = NULL; }
  if (w3.lease) { rfl_lease_release(w3.lease, &error); w3.lease = NULL; }
  if (w3.fonts) { rfl_close(w3.fonts, &error); w3.fonts = NULL; }
  if (w3.jh) reader_jh_close(&w3.jh, &history_error);
}
