#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
/* ---- TXT reading position: product content identity + canonical offset ----
   A product TXT original has no SDK book identity, so the position is the
   pager's own normalized projection offset for the top of the accepted page,
   captured together with a bounded window of the real projected text. Every
   product write and read runs on the serialized host worker; the UI only hands
   over copied values and never touches the revision store. */
static int txt_store_open(reader_txt_progress **store, exr_error *error) {
  char *path = host_utf8(g.product_path);
  reader_txp_error detail = {0};
  reader_txp_status status;
  int raw = 0;
#ifdef EXR_READER_WINDOWS_RAW3
  raw = 1;
#endif
  if (!path) { if (error) error->code = EXR_MEMORY; return 0; }
  status = reader_txp_open(path, raw, store, &detail);
  free(path);
  if (status != READER_TXP_OK) {
    if (error) {
      error->code = status == READER_TXP_MEMORY ? EXR_MEMORY : EXR_DATABASE;
      snprintf(error->message, sizeof(error->message), "%s", detail.message);
    }
    return 0;
  }
  return 1;
}

/* Reads [offset, offset+size) of the same normalized projection the page ranges
   use. Paragraph separators are the single synthesized newline the page text
   path uses, so a captured window compares byte for byte. */
static exr_status txt_window(const exr_source *source, uint64_t offset, size_t size,
                             char *buffer, size_t *written, exr_error *error) {
  exr_txt_cursor *cursor = NULL;
  exr_status status;
  size_t filled = 0;
  uint64_t at = 0;
  const char *text = NULL;
  size_t length = 0;
  if (written) *written = 0;
  status = exr_txt_cursor_create(source, &cursor, error);
  if (status != EXR_OK) return status;
  while (filled < size) {
    status = exr_txt_cursor_next(cursor, &at, &text, &length, error);
    if (status != EXR_OK || !text) { if (status == EXR_OK) status = EXR_FORMAT; break; }
    if (at + (uint64_t)length < offset + (uint64_t)filled) continue;
    if (at > offset + (uint64_t)filled) {
      if (at != offset + (uint64_t)filled + 1) { status = EXR_FORMAT; break; }
      buffer[filled++] = '\n';
    }
    if (at + (uint64_t)length > offset + (uint64_t)filled) {
      const size_t skip = (size_t)(offset + (uint64_t)filled - at);
      size_t take = length - skip;
      if (take > size - filled) take = size - filled;
      memcpy(buffer + filled, text + skip, take);
      filled += take;
    }
  }
  if (cursor) exr_txt_cursor_free(cursor);
  if (written) *written = filled;
  return status;
}

typedef struct {
  char *title, *author, *sort;
  uint64_t bytes;
  int favorite, found;
} txt_book_metadata;
static int txt_metadata_row(void *context, const reader_catalog_row *row) {
  txt_book_metadata *meta = context;
  if (meta->found) return 1;
  meta->title = host_strdup(row->title ? row->title : "");
  meta->author = host_strdup(row->author ? row->author : "");
  meta->sort = host_strdup(row->sort_title ? row->sort_title : "");
  meta->bytes = row->source_bytes;
  meta->favorite = row->favorite;
  meta->found = meta->title && meta->author && meta->sort;
  return 1;
}
static void txt_metadata_clear(txt_book_metadata *meta) {
  free(meta->title); free(meta->author); free(meta->sort);
  memset(meta, 0, sizeof(*meta));
}
/* The retained book revision is the product content identity. It is bootstrapped
   from the verified catalog row exactly once and never rewritten afterwards. */
static exr_status txt_bootstrap(reader_txt_progress *store, const char *key, exr_error *error) {
  reader_catalog *catalog = NULL;
  reader_catalog_error catalog_error = {0};
  reader_txp_book book = {0};
  reader_txp_result result = {0};
  reader_txp_error detail = {0};
  txt_book_metadata meta = {0};
  char *path = host_utf8(g.product_path);
  int found = 0, code = 0;
  reader_txp_status status;
  exr_status outcome = EXR_DATABASE;
  if (!path) return EXR_MEMORY;
  if (reader_catalog_open(path, &catalog, &catalog_error)) { free(path); return EXR_DATABASE; }
  code = reader_catalog_metadata(catalog, key, txt_metadata_row, &meta, &found, &catalog_error);
  reader_catalog_close(&catalog, &catalog_error);
  free(path);
  if (code || !found || !meta.found || !meta.bytes) { txt_metadata_clear(&meta); return EXR_NOT_FOUND; }
  book.book_key = key;
  book.title = meta.title;
  book.author = meta.author;
  book.sort_title = meta.sort;
  book.source_bytes = meta.bytes;
  book.favorite = meta.favorite;
  status = reader_txp_ensure_book(store, &book, &result, &detail);
  if (status == READER_TXP_OK) outcome = EXR_OK;
  else if (status == READER_TXP_IDENTITY) outcome = EXR_FORMAT;
  else if (status == READER_TXP_ARGUMENT) outcome = EXR_ARGUMENT;
  else if (status == READER_TXP_MEMORY) outcome = EXR_MEMORY;
  else outcome = EXR_DATABASE;
  if (outcome != EXR_OK && error) {
    error->code = outcome;
    snprintf(error->message, sizeof(error->message), "%s",
             detail.message[0] ? detail.message : "Cannot retain the product book identity");
  }
  txt_metadata_clear(&meta);
  return outcome;
}

static const wchar_t *txt_status_note(reader_txp_status status) {
  switch (status) {
    case READER_TXP_MISSING: return L"这本书还没有保存过阅读位置；从第一页开始。";
    case READER_TXP_CONFLICT: return L"这本书存在多个并发阅读位置记录；未选择、未覆盖，从第一页开始。";
    case READER_TXP_PENDING: return L"阅读位置记录缺少父记录；保留原记录，从第一页开始。";
    case READER_TXP_BLOCKED: return L"阅读位置记录需要显式恢复；保留原记录，从第一页开始。";
    case READER_TXP_LEGACY: return L"存在旧版阅读位置记录；本机不据此跳转，原记录保留。";
    case READER_TXP_BOOTSTRAP: return L"这本书还没有产品内容身份记录；从第一页开始。";
    case READER_TXP_UNSAFE: return L"阅读位置记录刚被其他写入改变；未覆盖，从第一页开始。";
    default: return L"无法读取阅读位置记录；从第一页开始，原记录未被覆盖。";
  }
}

/* Restore step for one opened product original. Only an exact anchor v2 point
   whose captured text still matches the current projection is used; everything
   else keeps the page at the beginning and blocks the automatic overwrite. */
static exr_status txt_restore(host_session *session, const char *key, size_t *page,
                              wchar_t *note, size_t capacity, exr_error *error) {
  reader_txt_progress *store = NULL;
  reader_txp_position saved = {0};
  reader_txp_result meta = {0};
  reader_txp_error detail = {0};
  reader_txp_status status;
  exr_control control = {host_cancel_check, NULL, NULL};
  if (page) *page = 0;
  if (note && capacity) note[0] = 0;
  if (!key || !key[0]) { copy_wstring(note, capacity, L"缺少书籍身份；从第一页开始。"); return EXR_OK; }
  if (!txt_store_open(&store, error)) {
    session->hold_progress = 1;
    copy_wstring(note, capacity, L"无法打开阅读位置记录；从第一页开始，原记录未被覆盖。");
    if (error) memset(error, 0, sizeof(*error));
    return EXR_OK;
  }
  status = reader_txp_load(store, key, &saved, &meta, &detail);
  reader_txp_close(&store);
  if (status != READER_TXP_OK) {
    session->hold_progress = 1;
    copy_wstring(note, capacity, txt_status_note(status));
    if (error) memset(error, 0, sizeof(*error));
    return EXR_OK;
  }
  if (saved.context_bytes) {
    char window[READER_TXP_CONTEXT_BYTES];
    size_t got = 0;
    int matches = 0;
    exr_status read = txt_window(&session->txt_source, saved.offset, saved.context_bytes,
                                 window, &got, &control, error);
    if (read != EXR_OK) {
      session->hold_progress = 1;
      copy_wstring(note, capacity, L"无法核对已保存的文本位置；从第一页开始，原记录未被覆盖。");
      if (error) memset(error, 0, sizeof(*error));
      return EXR_OK;
    }
    if (reader_txp_match(&saved, window, saved.offset, got, &matches, &detail) != READER_TXP_OK || !matches) {
      session->hold_progress = 1;
      copy_wstring(note, capacity, L"保存的内容位置与当前文本投影不一致；未跳转，原记录保留。");
      return EXR_OK;
    }
  }
  {
    exr_status located = EXR_OK;
    size_t found = 0;
    if (saved.offset > (uint64_t)SIZE_MAX) located = EXR_ARGUMENT;
    else located = page_for_offset(session, (size_t)saved.offset, &control, &found, NULL, NULL, error);
    if (located != EXR_OK) {
      session->hold_progress = 1;
      copy_wstring(note, capacity, L"保存的内容位置不在当前分页范围内；从第一页开始，原记录保留。");
      if (error) memset(error, 0, sizeof(*error));
      return EXR_OK;
    }
    if (page) *page = found;
  }
  copy_wstring(note, capacity, L"已按内容位置恢复到上次阅读位置。");
  return EXR_OK;
}

/* One durable position write for the accepted page. Failure keeps the previous
   record: the module refuses on stale, concurrent, pending or blocked history
   and the catalog/revision transaction either commits or not. */
static exr_status job_txt_progress(host_job *job) {
  reader_txt_progress *store = NULL;
  reader_txp_position position = {0};
  reader_txp_result result = {0};
  reader_txp_error detail = {0};
  reader_txp_status status;
  exr_status outcome;
  if (!txt_store_open(&store, &job->error)) return EXR_DATABASE;
  status = reader_txp_capture(&position, job->txt_offset, job->txt_context, job->txt_context_bytes, &detail);
  if (status != READER_TXP_OK) {
    reader_txp_close(&store);
    job->error.code = EXR_ARGUMENT;
    snprintf(job->error.message, sizeof(job->error.message), "%s", detail.message);
    return EXR_ARGUMENT;
  }
  status = reader_txp_save(store, job->txt_key, exr_version(), &position, &result, &detail);
  if (status == READER_TXP_BOOTSTRAP) {
    /* First write for a book imported before this feature existed. */
    outcome = txt_bootstrap(store, job->txt_key, &job->error);
    if (outcome == EXR_OK)
      status = reader_txp_save(store, job->txt_key, exr_version(), &position, &result, &detail);
    else { reader_txp_close(&store); return outcome; }
  }
  reader_txp_close(&store);
  if (status == READER_TXP_OK) {
    job->txt_saved_offset = position.offset;
    job->txt_saved_valid = 1;
    return EXR_OK;
  }
  if (status == READER_TXP_UNSAFE || status == READER_TXP_CONFLICT || status == READER_TXP_PENDING ||
      status == READER_TXP_BLOCKED || status == READER_TXP_LEGACY || status == READER_TXP_LIMIT) {
    job->error.code = EXR_DATABASE;
    snprintf(job->error.message, sizeof(job->error.message), "%s",
             detail.message[0] ? detail.message : "The reading position was not written");
    return EXR_DATABASE;
  }
  job->error.code = status == READER_TXP_MEMORY ? EXR_MEMORY : EXR_DATABASE;
  snprintf(job->error.message, sizeof(job->error.message), "%s",
           detail.message[0] ? detail.message : "The reading position was not written");
  return job->error.code;
}
#endif
