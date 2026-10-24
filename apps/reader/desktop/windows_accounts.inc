/* SPDX-License-Identifier: MIT
 * Windows account owner work. Included once by examples/reader.c after the
 * metadata owner glue. Every function here runs on the serialized host job
 * worker (or, for the small state readers, on the UI thread while no job is
 * running). No UI, network thread, JSON or direct SQL belongs here. */
enum { ACCT_STAGE_BEGIN = 1, ACCT_STAGE_NEXT, ACCT_RECV_BEGIN, ACCT_RECV_NEXT };
enum { ACCT_LOAD_RESPONSE = 1, ACCT_SET_RESPONSE, ACCT_FORGET_RESPONSE };
typedef struct { char *key, *sort, *title; int64_t id; uint64_t bytes; } acct_book;
typedef struct { char key[257], revision[33]; int kind, deleted; } acct_row;
typedef struct {
  exr_credentials_store *credentials;
  exr_credentials_status open_status, last_credential;
  char id[37], root[2100], user[2100];
  unsigned char *secret;
  size_t secret_size;
  int secret_remember, bound, loaded, staging, receiving, response;
  acct_book page[50];
  size_t count, index;
  char *cursor_title, *cursor_key, *last_title, *last_key;
  uint64_t seen, prepared, existing, pending, failed, bootstraps;
  int rkind;
  char after[260];
  uint64_t projected, concurrent, pending_parents, blocked, tombstones, project_failed;
  uint64_t imported, import_waiting, import_failed;
} acct_owner;

static struct {
  acct_owner owner;
  volatile LONG cancelled;
  wchar_t home[HOST_PATH], configuration[HOST_PATH], work[HOST_PATH], originals[HOST_PATH];
  /* UI thread state (windows_accounts_ui.inc) */
  HWND dialog, root, user, password, remember, message, detail;
  reader_session *session;
  reader_session_snapshot view;
  unsigned long generation, received_attempt;
  int want_stage, want_receive, exit_wanted, closing_session, dialog_close_wanted;
  int have_secret, recv_failed, recv_done, stage_failed;
  wchar_t notice[512], detail_text[768];
} acct;

static int acct_cancel_check(void *context) {
  return InterlockedCompareExchange(&acct.cancelled, 0, 0) != 0 || job_cancel_flag((host_job *)context);
}
static void acct_secret_clear(acct_owner *o) {
  if (o->secret) { exr_credentials_wipe(o->secret, o->secret_size); free(o->secret); }
  o->secret = NULL; o->secret_size = 0; o->secret_remember = 0;
}
static void acct_page_clear(acct_owner *o) {
  for (size_t i = 0; i < o->count; i++) { free(o->page[i].key); free(o->page[i].sort); free(o->page[i].title); }
  memset(o->page, 0, sizeof(o->page)); o->count = o->index = 0;
}
static void acct_owner_free(void) {
  acct_owner *o = &acct.owner;
  acct_secret_clear(o); acct_page_clear(o);
  if (o->credentials) exr_credentials_close(o->credentials);
  o->credentials = NULL;
  free(o->cursor_title); free(o->cursor_key); o->cursor_title = o->cursor_key = NULL;
  free(o->last_title); free(o->last_key); o->last_title = o->last_key = NULL;
}
static int acct_reparse_free(const wchar_t *path, int want_directory) {
  DWORD attributes = GetFileAttributesW(path);
  if (attributes == INVALID_FILE_ATTRIBUTES || (attributes & FILE_ATTRIBUTE_REPARSE_POINT)) return 0;
  return want_directory ? (attributes & FILE_ATTRIBUTE_DIRECTORY) != 0 : (attributes & FILE_ATTRIBUTE_DIRECTORY) == 0;
}
static int acct_directory(const wchar_t *path, int create) {
  if (GetFileAttributesW(path) == INVALID_FILE_ATTRIBUTES) {
    if (!create || GetLastError() != ERROR_FILE_NOT_FOUND || !CreateDirectoryW(path, NULL)) return 0;
  }
  return acct_reparse_free(path, 1);
}
static int acct_uuid(const char *id) {
  if (!id || strlen(id) != 36) return 0;
  for (size_t i = 0; i < 36; i++) {
    char c = id[i];
    if (i == 8 || i == 13 || i == 18 || i == 23) { if (c != '-') return 0; }
    else if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return 0;
  }
  return 1;
}
static int acct_root_valid(const char *root) {
  exr_webdav_config config = {0}; exr_webdav_client *dav = NULL; exr_webdav_error error = {0};
  if (!root || strlen(root) >= sizeof(acct.owner.root)) return 0;
  config.root_url = root;
  exr_webdav_status code = exr_webdav_create(&config, &dav, &error);
  exr_webdav_free(dav);
  return code == EXR_DAV_OK;
}
static void acct_new_uuid(char out[37]) {
  unsigned char b[16];
  static const char hex[] = "0123456789abcdef";
  if (BCryptGenRandom(NULL, b, sizeof(b), BCRYPT_USE_SYSTEM_PREFERRED_RNG) != 0) memset(b, 0x5a, sizeof(b));
  b[6] = (unsigned char)((b[6] & 0x0f) | 0x40); b[8] = (unsigned char)((b[8] & 0x3f) | 0x80);
  size_t at = 0;
  for (size_t i = 0; i < 16; i++) {
    if (i == 4 || i == 6 || i == 8 || i == 10) out[at++] = '-';
    out[at++] = hex[b[i] >> 4]; out[at++] = hex[b[i] & 15];
  }
  out[at] = 0;
}
static void acct_base64(const unsigned char *in, size_t size, char *out) {
  static const char table[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  size_t at = 0;
  for (size_t i = 0; i < size; i += 3) {
    unsigned value = (unsigned)in[i] << 16;
    if (i + 1 < size) value |= (unsigned)in[i + 1] << 8;
    if (i + 2 < size) value |= in[i + 2];
    out[at++] = table[(value >> 18) & 63]; out[at++] = table[(value >> 12) & 63];
    out[at++] = i + 1 < size ? table[(value >> 6) & 63] : '=';
    out[at++] = i + 2 < size ? table[value & 63] : '=';
  }
  out[at] = 0;
}
static void acct_text(host_job *job, const wchar_t *text) { copy_wstring(job->message, 512, text); }

/* 0 absent, 1 valid, -1 refused. The only persisted fields are UUID and exact root. */
static int acct_configuration(char id[37], char root[2100]) {
  HANDLE file = CreateFileW(acct.configuration, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING,
                            FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OPEN_REPARSE_POINT, NULL);
  char data[4400]; DWORD got = 0; int valid = 0;
  BY_HANDLE_FILE_INFORMATION info;
  if (file == INVALID_HANDLE_VALUE) return GetLastError() == ERROR_FILE_NOT_FOUND ? 0 : -1;
  if (GetFileInformationByHandle(file, &info) && !(info.dwFileAttributes & (FILE_ATTRIBUTE_REPARSE_POINT | FILE_ATTRIBUTE_DIRECTORY)) &&
      info.nNumberOfLinks == 1 && !info.nFileSizeHigh && info.nFileSizeLow > 0 && info.nFileSizeLow < sizeof(data) &&
      ReadFile(file, data, info.nFileSizeLow, &got, NULL) && got == info.nFileSizeLow) {
    data[got] = 0;
    if (!memchr(data, 0, got) && !strncmp(data, "[account]\r\nid=", 14)) {
      char *line = data + 14, *end = strstr(line, "\r\n");
      if (end && end - line == 36) {
        memcpy(id, line, 36); id[36] = 0;
        char *second = end + 2;
        if (!strncmp(second, "root=", 5)) {
          char *tail = strstr(second + 5, "\r\n");
          if (tail && tail[2] == 0 && (size_t)(tail - (second + 5)) < 2100) {
            memcpy(root, second + 5, (size_t)(tail - (second + 5))); root[tail - (second + 5)] = 0;
            valid = acct_uuid(id) && acct_root_valid(root);
          }
        }
      }
    }
  }
  CloseHandle(file);
  return valid ? 1 : -1;
}
static exr_status acct_ready(host_job *job) {
  acct_owner *o = &acct.owner;
  if (!acct.home[0]) {
    wcsncpy(acct.home, g.library_path, HOST_PATH - 1);
    wchar_t *slash = wcsrchr(acct.home, L'\\'), *forward = wcsrchr(acct.home, L'/');
    if (forward > slash) slash = forward;
    if (slash) *slash = 0; else wcscpy(acct.home, L".");
    swprintf(acct.configuration, HOST_PATH, L"%ls\\account.ini", acct.home);
    swprintf(acct.work, HOST_PATH, L"%ls\\sync-work", acct.home);
    swprintf(acct.originals, HOST_PATH, L"%ls\\sync-originals", acct.home);
    acct_new_uuid(o->id); o->root[0] = 0;
    o->open_status = exr_credentials_open("org.exreader.reader.webdav", &o->credentials);
  }
  if (!acct_directory(acct.home, 0)) { acct_text(job, L"账号配置需要本机书库目录。"); return EXR_IO; }
  if (!o->loaded) {
    char id[37], root[2100];
    int read = acct_configuration(id, root);
    if (read < 0) { acct_text(job, L"账号配置无效，已原样保留；请使用新的书库目录。"); return EXR_DATABASE; }
    if (read) { memcpy(o->id, id, 37); memcpy(o->root, root, sizeof(o->root)); o->bound = 1; }
    o->loaded = 1;
  }
  return EXR_OK;
}
static exr_status acct_bind(host_job *job) {
  acct_owner *o = &acct.owner;
  char id[37], root[2100];
  if (!job->account_root || !acct_root_valid(job->account_root)) {
    acct_text(job, L"请输入以 / 结尾的 HTTPS WebDAV 集合地址。"); return EXR_ARGUMENT;
  }
  int read = acct_configuration(id, root);
  int same = read == 1 && !strcmp(id, o->id) && !strcmp(root, job->account_root);
  if (read < 0 || (read == 1 && !same) || (o->bound && strcmp(o->root, job->account_root))) {
    acct_text(job, L"此书库已绑定账号和精确地址；其他账号请使用独立书库。"); return EXR_ARGUMENT;
  }
  if (same) { o->bound = 1; return EXR_OK; }
  wchar_t temporary[HOST_PATH]; char data[2400];
  swprintf(temporary, HOST_PATH, L"%ls.tmp-%08lx", acct.configuration, (unsigned long)GetCurrentProcessId());
  int size = snprintf(data, sizeof(data), "[account]\r\nid=%s\r\nroot=%s\r\n", o->id, job->account_root);
  HANDLE file = CreateFileW(temporary, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL | FILE_FLAG_WRITE_THROUGH, NULL);
  DWORD wrote = 0; int ok = file != INVALID_HANDLE_VALUE && size > 0 &&
    WriteFile(file, data, (DWORD)size, &wrote, NULL) && wrote == (DWORD)size && FlushFileBuffers(file);
  if (file != INVALID_HANDLE_VALUE) CloseHandle(file);
  /* No replacement flag: an existing binding is never overwritten. */
  if (ok) ok = MoveFileExW(temporary, acct.configuration, MOVEFILE_WRITE_THROUGH) != 0;
  if (!ok) { DeleteFileW(temporary); acct_text(job, L"账号地址无法保存；已有配置未被替换。"); return EXR_IO; }
  o->bound = 1; snprintf(o->root, sizeof(o->root), "%s", job->account_root);
  return EXR_OK;
}
static int acct_secret_valid(const unsigned char *data, size_t size, size_t *user_bytes) {
  const unsigned char *zero;
  if (!data || size < 3 || size > EXR_CREDENTIALS_SECRET_MAX) return 0;
  zero = memchr(data, 0, size);
  if (!zero || zero == data || zero == data + size - 1) return 0;
  *user_bytes = (size_t)(zero - data);
  return !memchr(data, ':', *user_bytes) && !memchr(zero + 1, 0, size - *user_bytes - 1);
}
static exr_status acct_secret_adopt(acct_owner *o, unsigned char *data, size_t size, int remember) {
  size_t user_bytes = 0;
  if (!acct_secret_valid(data, size, &user_bytes) || user_bytes >= sizeof(o->user)) {
    exr_credentials_wipe(data, size); free(data); return EXR_ARGUMENT;
  }
  acct_secret_clear(o);
  o->secret = data; o->secret_size = size; o->secret_remember = remember;
  memcpy(o->user, data, user_bytes); o->user[user_bytes] = 0;
  return EXR_OK;
}
static exr_status acct_load_job(host_job *job) {
  acct_owner *o = &acct.owner;
  exr_status status = acct_ready(job);
  o->response = ACCT_LOAD_RESPONSE; o->last_credential = EXR_CRED_OK;
  if (status != EXR_OK) return status;
  if (o->secret) { acct_text(job, o->secret_remember ? L"已载入系统安全存储中的凭据；密码保持隐藏。" : L"凭据仅在本次会话内有效。"); return EXR_OK; }
  unsigned char data[EXR_CREDENTIALS_SECRET_MAX]; size_t size = 0;
  exr_credentials_status code = o->credentials ? exr_credentials_get(o->credentials, o->id, data, sizeof(data), &size) : o->open_status;
  o->last_credential = code;
  if (code == EXR_CRED_OK) {
    unsigned char *copy = malloc(size);
    if (!copy) { exr_credentials_wipe(data, sizeof(data)); return EXR_MEMORY; }
    memcpy(copy, data, size);
    status = acct_secret_adopt(o, copy, size, 1);
    acct_text(job, status == EXR_OK ? L"已载入系统安全存储中的凭据；密码保持隐藏。" : L"系统保存的凭据无效，未使用。");
    status = EXR_OK;
  } else if (code == EXR_CRED_UNAVAILABLE) {
    acct_text(job, L"UNAVAILABLE：系统安全存储不可用。可取消勾选“保存到系统安全存储”，仅本次会话使用。");
  } else if (code == EXR_CRED_NOT_FOUND) {
    acct_text(job, o->bound ? L"此账号没有已保存的凭据。" : L"尚未配置账号。");
  } else acct_text(job, L"系统安全存储读取失败，未使用任何凭据。");
  exr_credentials_wipe(data, sizeof(data));
  return status;
}
static exr_status acct_set_job(host_job *job) {
  acct_owner *o = &acct.owner;
  exr_status status = acct_ready(job);
  o->response = ACCT_SET_RESPONSE; o->last_credential = EXR_CRED_ARGUMENT;
  if (status != EXR_OK) return status;
  const char *user = job->account_user, *password = job->account_password;
  if (!user || !password || !user[0] || !password[0] || strlen(user) + 1 + strlen(password) > EXR_CREDENTIALS_SECRET_MAX) {
    acct_text(job, L"请输入用户名和密码，总长度需在安全存储限制内。"); return EXR_ARGUMENT;
  }
  size_t size = strlen(user) + 1 + strlen(password), user_bytes = 0;
  unsigned char *data = malloc(size);
  if (!data) return EXR_MEMORY;
  memcpy(data, user, strlen(user) + 1); memcpy(data + strlen(user) + 1, password, strlen(password));
  if (!acct_secret_valid(data, size, &user_bytes)) {
    exr_credentials_wipe(data, size); free(data); acct_text(job, L"凭据必须是有效文本，用户名不能含冒号。"); return EXR_ARGUMENT;
  }
  status = acct_bind(job);
  if (status != EXR_OK) { exr_credentials_wipe(data, size); free(data); return status; }
  exr_credentials_status code = EXR_CRED_OK;
  if (job->account_remember) code = o->credentials ? exr_credentials_put(o->credentials, o->id, data, size) : o->open_status;
  o->last_credential = code;
  if (code == EXR_CRED_OK) {
    acct_secret_adopt(o, data, size, job->account_remember);
    acct_text(job, job->account_remember ? L"凭据已保存到系统安全存储。" : L"仅本次会话使用这些凭据；退出后不会保留。");
  } else {
    exr_credentials_wipe(data, size); free(data);
    acct_text(job, code == EXR_CRED_UNAVAILABLE ?
      L"UNAVAILABLE：凭据未保存。请取消勾选“保存到系统安全存储”，仅本次会话使用。" :
      L"凭据未保存：系统安全存储报告错误。");
  }
  return EXR_OK;
}
static exr_status acct_forget_job(host_job *job) {
  acct_owner *o = &acct.owner;
  exr_status status = acct_ready(job);
  o->response = ACCT_FORGET_RESPONSE;
  if (status != EXR_OK) return status;
  acct_secret_clear(o);
  exr_credentials_status code = o->credentials ? exr_credentials_delete(o->credentials, o->id) : o->open_status;
  o->last_credential = code;
  acct_text(job, code == EXR_CRED_OK || code == EXR_CRED_NOT_FOUND ? L"已删除保存的凭据；账号地址仍保持绑定。" :
    L"系统安全存储不可用或失败，无法确认删除；本次会话内存中的凭据已清除。");
  return EXR_OK;
}

/* ---- local original staging ------------------------------------------ */
static HANDLE acct_open_private(const wchar_t *path, uint64_t *size) {
  HANDLE file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING,
                            FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_SEQUENTIAL_SCAN, NULL);
  BY_HANDLE_FILE_INFORMATION info;
  if (file == INVALID_HANDLE_VALUE) return file;
  if (!GetFileInformationByHandle(file, &info) || (info.dwFileAttributes & (FILE_ATTRIBUTE_REPARSE_POINT | FILE_ATTRIBUTE_DIRECTORY)) ||
      info.nNumberOfLinks != 1) { CloseHandle(file); return INVALID_HANDLE_VALUE; }
  if (size) *size = ((uint64_t)info.nFileSizeHigh << 32) | info.nFileSizeLow;
  return file;
}
/* Streams 64 KiB blocks; EXR_OK only for exact length and SHA-256. */
static exr_status acct_file_matches(const wchar_t *path, const char *hash, uint64_t bytes, host_job *job) {
  uint64_t size = 0, total = 0;
  HANDLE file = acct_open_private(path, &size);
  exr_status status = EXR_DATABASE;
  BCRYPT_ALG_HANDLE algorithm = NULL; BCRYPT_HASH_HANDLE digest = NULL;
  unsigned char block[65536], value[32]; DWORD got = 0;
  if (file == INVALID_HANDLE_VALUE) return GetLastError() == ERROR_FILE_NOT_FOUND ? EXR_IO : EXR_DATABASE;
  if (size != bytes || bytes > EXR_SIDELOAD_STREAM_LIMIT) goto done;
  if (BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, NULL, 0) != 0 ||
      BCryptCreateHash(algorithm, &digest, NULL, 0, NULL, 0, 0) != 0) { status = EXR_MEMORY; goto done; }
  for (;;) {
    if (acct_cancel_check(job)) { status = EXR_CANCELLED; goto done; }
    if (!ReadFile(file, block, sizeof(block), &got, NULL)) { status = EXR_IO; goto done; }
    if (!got) break;
    total += got;
    if (total > bytes || BCryptHashData(digest, block, got, 0) != 0) goto done;
  }
  if (total == bytes && BCryptFinishHash(digest, value, sizeof(value), 0) == 0) {
    char hex[65];
    for (int i = 0; i < 32; i++) snprintf(hex + i * 2, 3, "%02x", value[i]);
    if (!strcmp(hex, hash)) status = EXR_OK;
  }
done:
  if (digest) BCryptDestroyHash(digest);
  if (algorithm) BCryptCloseAlgorithmProvider(algorithm, 0);
  CloseHandle(file);
  return status;
}
static int acct_receive_local(void *opaque, const reader_catalog_row *row) {
  acct_owner *o = opaque;
  if (o->count >= 50) return 1;
  acct_book *book = &o->page[o->count++];
  book->key = host_strdup(row->book_key); book->sort = host_strdup(row->sort_title);
  book->title = host_strdup(row->title); book->id = row->sdk_book_id; book->bytes = row->source_bytes;
  return !book->key || !book->sort || !book->title;
}
static int acct_open_metadata(reader_metadata_owner **owner, reader_metadata_error *error) {
  char *database = host_utf8(g.product_path), *pending;
  if (!database) return 0;
  size_t length = strlen(database) + 32; pending = malloc(length);
  if (!pending) { free(database); return 0; }
  snprintf(pending, length, "%s.commands.pending", database);
  reader_metadata_status code = reader_metadata_open(database, pending, owner, error);
  free(database); free(pending);
  return code == READER_METADATA_OK;
}
static exr_status acct_pending_check(host_job *job) {
  reader_metadata_owner *owner = NULL; reader_metadata_error error = {0}; reader_metadata_result pending = {0};
  if (!acct_open_metadata(&owner, &error)) { acct_text(job, L"无法读取书籍编辑状态，已停止准备。"); return EXR_DATABASE; }
  reader_metadata_status code = reader_metadata_pending(owner, &pending, &error);
  reader_metadata_close(&owner, &error);
  if (code == READER_METADATA_NO_PENDING) return EXR_OK;
  acct_text(job, L"请先完成之前的书籍编辑恢复，再准备同步。");
  return EXR_DATABASE;
}
static exr_status acct_bootstrap(host_job *job, const acct_book *book, const char *hash, uint64_t bytes) {
  reader_metadata_owner *owner = NULL; reader_metadata_error error = {0};
  reader_metadata_snapshot *snapshot = NULL; reader_metadata_result submitted = {0};
  if (!acct_open_metadata(&owner, &error)) { acct_text(job, L"无法打开书籍历史。"); return EXR_DATABASE; }
  reader_metadata_status code = reader_metadata_prepare_book(owner, book->key, &snapshot, &error);
  const reader_metadata_view *view = reader_metadata_snapshot_view(snapshot);
  if (code == READER_METADATA_NEEDS_BOOTSTRAP) {
    if (!view || strcmp(view->book.source_sha256, hash) || view->book.source_bytes != bytes) code = READER_METADATA_CONFLICT;
    else {
      reader_metadata_verified_source proof = {view->book.format, hash, bytes};
      code = reader_metadata_stage_bootstrap(owner, snapshot, &proof, &submitted, &error);
      if (code == READER_METADATA_OK) code = reader_metadata_finish_pending(owner, &submitted, &error);
      if (code == READER_METADATA_OK) acct.owner.bootstraps++;
    }
  } else if (code == READER_METADATA_CONFLICT && view && view->present && view->graph.revisions && !view->needs_bootstrap &&
             !strcmp(view->book.book_key, book->key) && !strcmp(view->book.source_sha256, hash) && view->book.source_bytes == bytes) {
    /* Original identity is independently proven. Stage bytes but keep every head. */
    code = READER_METADATA_OK;
  }
  reader_metadata_snapshot_free(snapshot);
  reader_metadata_close(&owner, &error);
  if (code == READER_METADATA_OK) return EXR_OK;
  acct_text(job, L"无法准备这本书的历史；已保留版本和未完成的修改。");
  return EXR_DATABASE;
}
static exr_status acct_prepare_book(host_job *job, const acct_book *book) {
  acct_owner *o = &acct.owner;
  exr_source probe = {0}; exr_error error = {0};
  char hash[65]; uint64_t bytes = 0;
  exr_control control = {acct_cancel_check, NULL, job};
  EnterCriticalSection(&g.library_lock);
  exr_status status = exr_library_source(g.library, book->id, &probe, &error);
  int available = status == EXR_OK && probe.read_at && probe.release && probe.size && probe.size <= EXR_SIDELOAD_STREAM_LIMIT && probe.size == book->bytes;
  if (status == EXR_OK && probe.release) probe.release(probe.context);
  if (!available) { LeaveCriticalSection(&g.library_lock); o->pending++; return EXR_OK; }
  status = reader_catalog_sdk_original_identity(g.library, book->id, &control, hash, &bytes, &error);
  LeaveCriticalSection(&g.library_lock);
  if (status == EXR_CANCELLED) return status;
  const char *colon = strchr(book->key, ':');
  if (status != EXR_OK || !colon || strcmp(colon + 1, hash) || bytes != book->bytes || bytes > EXR_SIDELOAD_STREAM_LIMIT) {
    o->failed++; acct_text(job, L"本机原书身份与书目不一致，未暂存。"); return EXR_DATABASE;
  }
  status = acct_pending_check(job);
  if (status != EXR_OK) { o->failed++; return status; }
  status = acct_bootstrap(job, book, hash, bytes);
  if (status != EXR_OK) { o->failed++; return status; }
  size_t format_bytes = (size_t)(colon - book->key);
  if (!format_bytes || format_bytes > 4) { o->failed++; return EXR_ARGUMENT; }
  wchar_t destination[HOST_PATH]; wchar_t name[96];
  swprintf(name, 96, L"%hs.%.*hs", hash, (int)format_bytes, book->key);
  swprintf(destination, HOST_PATH, L"%ls\\%ls", acct.originals, name);
  if (GetFileAttributesW(destination) != INVALID_FILE_ATTRIBUTES) {
    status = acct_file_matches(destination, hash, bytes, job);
    if (status == EXR_OK) o->existing++;
  } else if (GetLastError() == ERROR_FILE_NOT_FOUND) {
    char *utf8 = host_utf8(destination);
    exr_sideload_options options = {0}; uint64_t written = 0;
    if (!utf8) return EXR_MEMORY;
    options.struct_size = sizeof(options); options.control = control;
    EnterCriticalSection(&g.library_lock);
    status = exr_sideload_export_original(g.library, book->id, utf8, &options, &written, &error);
    LeaveCriticalSection(&g.library_lock);
    free(utf8);
    if (status == EXR_OK && written == bytes) { o->prepared++; status = acct_file_matches(destination, hash, bytes, job); }
    else if (status == EXR_OK) status = EXR_IO;
  } else status = EXR_IO;
  if (status != EXR_OK && status != EXR_CANCELLED) {
    o->failed++; acct_text(job, L"原书无法暂存或校验；已有文件未被替换。");
  }
  return status;
}
static exr_status acct_stage_job(host_job *job) {
  acct_owner *o = &acct.owner; exr_status status;
  if (job->account_action == ACCT_STAGE_BEGIN) {
    status = acct_ready(job);
    if (status != EXR_OK) return status;
    if (!o->bound || !o->secret || !acct_directory(acct.work, 1) || !acct_directory(acct.originals, 1)) {
      acct_text(job, L"请先应用凭据和账号地址，再准备同步。"); return EXR_IO;
    }
    status = acct_pending_check(job);
    if (status != EXR_OK) return status;
    acct_page_clear(o); free(o->cursor_title); free(o->cursor_key); o->cursor_title = o->cursor_key = NULL;
    o->seen = o->prepared = o->existing = o->pending = o->failed = o->bootstraps = 0;
    o->staging = 1;
  }
  if (!o->staging) return EXR_ARGUMENT;
  if (acct_cancel_check(job)) { o->staging = 0; return EXR_CANCELLED; }
  if (o->index == o->count) {
    reader_catalog *catalog = NULL; reader_catalog_error error = {0};
    char *path = host_utf8(g.product_path);
    acct_page_clear(o);
    if (!path) { o->staging = 0; return EXR_MEMORY; }
    int code = reader_catalog_open(path, &catalog, &error); free(path);
    if (!code) {
      code = reader_catalog_local_page(catalog, o->cursor_title, o->cursor_key, NULL, 1, 50, acct_receive_local, o, &error);
      reader_catalog_close(&catalog, &error);
    }
    if (code) { o->staging = 0; acct_text(job, L"无法按页读取本机书目。"); return EXR_DATABASE; }
    if (!o->count) { o->staging = 0; return EXR_OK; }
    acct_book *last = &o->page[o->count - 1];
    free(o->cursor_title); free(o->cursor_key);
    o->cursor_title = host_strdup(last->sort); o->cursor_key = host_strdup(last->key);
    if (!o->cursor_title || !o->cursor_key) { o->staging = 0; return EXR_MEMORY; }
  }
  o->seen++;
  status = acct_prepare_book(job, &o->page[o->index++]);
  if (status != EXR_OK || (o->index == o->count && o->count < 50)) o->staging = 0;
  return status;
}

/* ---- receive: SAFE metadata first, then verified private-file import ----- */
typedef struct { acct_row rows[50]; size_t count; int overflow; } acct_page;
static int acct_collect(void *context, const reader_revision_entity_row *row) {
  acct_page *page = context;
  if (page->count >= 50 || strlen(row->entity_key) >= sizeof(page->rows[0].key)) { page->overflow = 1; return 1; }
  acct_row *copy = &page->rows[page->count++];
  snprintf(copy->key, sizeof(copy->key), "%s", row->entity_key);
  copy->kind = (int)row->selection.kind; copy->deleted = row->selection.graph.deleted;
  copy->revision[0] = 0;
  if (row->selection.kind == READER_SELECTION_SAFE) snprintf(copy->revision, sizeof(copy->revision), "%s", row->info.revision_id);
  return 0;
}
static const char *const acct_kinds[] = {"book", "shelf", "tag", "series", "membership"};
static char *acct_nfc_title(const char *title) {
  wchar_t *wide = host_wide(title, strlen(title)); char *result;
  if (!wide) return NULL;
  result = metadata_normalized_title(wide, NULL);
  free(wide);
  return result;
}
static exr_status acct_project_step(host_job *job) {
  acct_owner *o = &acct.owner; reader_revisions *store = NULL; reader_revision_error error = {0};
  acct_page *page = calloc(1, sizeof(*page)); exr_status status = EXR_OK;
  char *path = host_utf8(g.product_path);
  if (!page || !path) { free(page); free(path); return EXR_MEMORY; }
  if (reader_revisions_open(path, &store, &error) != READER_REV_OK) { free(page); free(path); acct_text(job, L"无法打开修订历史。"); return EXR_DATABASE; }
  free(path);
  const char *kind = acct_kinds[o->rkind];
  if (reader_revision_entities_page(store, kind, o->after[0] ? o->after : NULL, 1, 50, acct_collect, page, &error) != READER_REV_OK || page->overflow) {
    status = EXR_DATABASE; acct_text(job, L"无法分页读取接收到的修订。");
  } else if (!page->count) {
    o->rkind++; o->after[0] = 0;
  } else {
    snprintf(o->after, sizeof(o->after), "%s", page->rows[page->count - 1].key);
    for (size_t i = 0; i < page->count && status == EXR_OK; i++) {
      acct_row *row = &page->rows[i];
      if (acct_cancel_check(job)) { status = EXR_CANCELLED; break; }
      if (row->kind == READER_SELECTION_CONCURRENT) { o->concurrent++; continue; }
      if (row->kind == READER_SELECTION_PENDING_PARENTS) { o->pending_parents++; continue; }
      if (row->kind != READER_SELECTION_SAFE) { o->blocked++; continue; }
      if (row->deleted) { o->tombstones++; continue; }
      char *title = NULL, *sort = NULL; reader_revision_error local = {0};
      if (o->rkind == 0) {
        if (reader_revision_book_title(store, row->revision, &title, &local) != READER_REV_OK) { o->project_failed++; continue; }
        sort = acct_nfc_title(title);
        reader_revision_bytes_free(title);
        if (!sort) { o->project_failed++; continue; }
      }
      reader_revision_status code = reader_revision_project(store, kind, row->key, row->revision, sort, NULL, &local);
      free(sort);
      if (code == READER_REV_OK) o->projected++;
      else if (code == READER_REV_MISSING_PARENT || code == READER_REV_UNSAFE) o->pending_parents++;
      else o->project_failed++;
    }
  }
  reader_revisions_close(&store, &error);
  free(page);
  return status;
}
static int acct_cloud_visit(void *context, const reader_catalog_row *row) {
  acct_owner *o = context;
  if (o->count >= 50) return 1;
  /* The borrowed query cursor stays untouched until the page call returns. */
  free(o->last_title); free(o->last_key);
  o->last_title = host_strdup(row->sort_title); o->last_key = host_strdup(row->book_key);
  if (!o->last_title || !o->last_key) return 1;
  o->seen++;
  if (row->sdk_book_id || row->deleted) return 0;
  acct_book *book = &o->page[o->count++];
  book->key = host_strdup(row->book_key); book->sort = host_strdup(row->sort_title);
  book->title = host_strdup(row->title); book->bytes = row->source_bytes;
  return !book->key || !book->sort || !book->title;
}
static exr_status acct_import_one(host_job *job, const acct_book *book) {
  acct_owner *o = &acct.owner;
  const char *colon = strchr(book->key, ':');
  if (!colon || strlen(colon + 1) != 64 || (size_t)(colon - book->key) > 4) { o->import_failed++; return EXR_OK; }
  char hash[65]; snprintf(hash, sizeof(hash), "%s", colon + 1);
  wchar_t path[HOST_PATH];
  swprintf(path, HOST_PATH, L"%ls\\%hs.%.*hs", acct.work, hash, (int)(colon - book->key), book->key);
  if (GetFileAttributesW(path) == INVALID_FILE_ATTRIBUTES) { o->import_waiting++; return EXR_OK; }
  exr_status status = acct_file_matches(path, hash, book->bytes, job);
  if (status == EXR_CANCELLED) return status;
  if (status != EXR_OK) { o->import_failed++; acct_text(job, L"云端原书校验失败，未导入。"); return EXR_OK; }
  char format[8]; snprintf(format, sizeof(format), "%.*s", (int)(colon - book->key), book->key);
  exr_format kind = product_format(format);
  char *utf8 = host_utf8(path);
  if (kind == EXR_CUSTOM || !utf8) { free(utf8); o->import_failed++; return EXR_OK; }
  exr_sideload_options options = {0}; exr_sideload_result result = {0}; exr_error error = {0};
  options.struct_size = sizeof(options); result.struct_size = sizeof(result);
  options.control.cancelled = acct_cancel_check; options.control.context = job;
  EnterCriticalSection(&g.library_lock);
  status = exr_sideload_import_file(g.library, kind, utf8, book->title, &options, &result, &error);
  LeaveCriticalSection(&g.library_lock);
  free(utf8);
  if (status == EXR_CANCELLED) return status;
  if (status != EXR_OK) { o->import_failed++; acct_text(job, L"云端原书导入失败；已保留下载的文件。"); return EXR_OK; }
  /* A committed SDK import wins over cancellation: map it so no orphan remains. */
  exr_book sdk = {0};
  status = local_book_copy(result.book_id, &sdk, &error);
  if (status == EXR_OK) {
    reader_catalog *catalog = NULL; reader_catalog_error catalog_error = {0};
    char *product = host_utf8(g.product_path);
    char key[READER_BOOK_KEY_CAPACITY] = "";
    int code = product ? reader_catalog_open(product, &catalog, &catalog_error) : 1;
    free(product);
    if (!code) {
      EnterCriticalSection(&g.library_lock);
      status = reader_catalog_sdk_attach(catalog, g.library, &sdk, NULL, key, &error);
      LeaveCriticalSection(&g.library_lock);
      reader_catalog_close(&catalog, &catalog_error);
    } else status = EXR_DATABASE;
    if (status == EXR_OK && strcmp(key, book->key)) status = EXR_DATABASE;
  }
  book_clear(&sdk);
  if (status == EXR_OK) o->imported++;
  else { o->import_failed++; acct_text(job, L"原书已导入，但书目映射待恢复；将自动修复，也可重启后重试。"); }
  return EXR_OK;
}
static exr_status acct_import_step(host_job *job) {
  acct_owner *o = &acct.owner;
  if (o->index == o->count) {
    reader_catalog *catalog = NULL; reader_catalog_error error = {0};
    char *path = host_utf8(g.product_path);
    acct_page_clear(o);
    if (!path) return EXR_MEMORY;
    int code = reader_catalog_open(path, &catalog, &error); free(path);
    for (int guard = 0; !code && !o->count && guard < 64; guard++) {
      uint64_t before = o->seen;
      code = reader_catalog_page(catalog, o->cursor_title, o->cursor_key, 50, acct_cloud_visit, o, &error);
      if (code) break;
      if (o->seen == before) { o->rkind = 6; break; } /* no further rows */
      free(o->cursor_title); free(o->cursor_key);
      o->cursor_title = o->last_title; o->cursor_key = o->last_key; o->last_title = o->last_key = NULL;
    }
    if (catalog) reader_catalog_close(&catalog, &error);
    if (code) { acct_text(job, L"无法按页读取云端书目。"); return EXR_DATABASE; }
    if (o->rkind == 6 || !o->count) return EXR_OK;
  }
  if (acct_cancel_check(job)) return EXR_CANCELLED;
  return acct_import_one(job, &o->page[o->index++]);
}
static exr_status acct_receive_job(host_job *job) {
  acct_owner *o = &acct.owner; exr_status status;
  if (job->account_action == ACCT_RECV_BEGIN) {
    status = acct_ready(job);
    if (status != EXR_OK) return status;
    if (!acct_directory(acct.work, 1)) { acct_text(job, L"同步缓存目录不可用。"); return EXR_IO; }
    acct_page_clear(o); free(o->cursor_title); free(o->cursor_key); o->cursor_title = o->cursor_key = NULL;
    o->rkind = 0; o->after[0] = 0; o->seen = 0;
    o->projected = o->concurrent = o->pending_parents = o->blocked = o->tombstones = o->project_failed = 0;
    o->imported = o->import_waiting = o->import_failed = 0;
    o->receiving = 1;
  }
  if (!o->receiving) return EXR_ARGUMENT;
  if (acct_cancel_check(job)) { o->receiving = 0; return EXR_CANCELLED; }
  if (o->rkind < 5) {
    status = acct_project_step(job);
    if (status == EXR_OK && o->rkind == 5) { /* entering the import phase */
      free(o->cursor_title); free(o->cursor_key); o->cursor_title = o->cursor_key = NULL; o->seen = 0;
    }
  } else if (o->rkind == 5) status = acct_import_step(job);
  else status = EXR_OK;
  if (status != EXR_OK || o->rkind >= 6) o->receiving = 0;
  return status;
}
static exr_status account_job_run(host_job *job) {
  switch (job->kind) {
    case JOB_ACCOUNT_LOAD: return acct_load_job(job);
    case JOB_ACCOUNT_SET: return acct_set_job(job);
    case JOB_ACCOUNT_FORGET: return acct_forget_job(job);
    case JOB_ACCOUNT_STAGE: return acct_stage_job(job);
    case JOB_ACCOUNT_RECEIVE: return acct_receive_job(job);
    default: return EXR_ARGUMENT;
  }
}
