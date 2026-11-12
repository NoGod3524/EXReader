/* SPDX-License-Identifier: MIT */
/* OPDS network layer for the Windows host: WinHTTP GET with HTTPS only (plain
   http is accepted for loopback test servers only), explicit timeouts,
   redirects, readable error mapping, cancellation, and a 10 minute in-memory
   feed cache. Header-only (static functions) so the reader and the console
   probe share one implementation. Messages are UTF-8, Chinese first. */
#ifndef EXR_OPDS_NET_H
#define EXR_OPDS_NET_H
#include <windows.h>
#include <winhttp.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _MSC_VER
#pragma comment(lib, "winhttp.lib")
#endif
typedef enum {
  ONET_OK = 0, ONET_BAD_URL, ONET_NOT_HTTPS, ONET_TIMEOUT, ONET_DNS, ONET_CONNECT, ONET_TLS,
  ONET_REDIRECT, ONET_AUTH, ONET_FORBIDDEN, ONET_NOT_FOUND, ONET_RATE, ONET_SERVER, ONET_HTTP,
  ONET_CANCELLED, ONET_TOO_BIG, ONET_IO, ONET_NETWORK
} onet_code;
typedef struct {
  onet_code code;
  int http_status;       /* 0 when no response arrived */
  unsigned long win_error;
  char message[256];     /* readable UTF-8 */
  char final_url[2048];  /* after redirects */
  char content_type[96];
  int from_cache;
} onet_result;
typedef struct {
  unsigned resolve_ms, connect_ms, send_ms, receive_ms; /* 0 = default */
  uint64_t max_bytes;                                   /* 0 = 64 MiB */
  volatile LONG *cancel;                                /* nonzero aborts between chunks */
  int (*sink)(void *context, const void *data, size_t size); /* nonzero return = stop with ONET_IO */
  void (*progress)(void *context, uint64_t done, uint64_t total);
  void *context;
  const char *accept;
} onet_options;
typedef struct { char *data; size_t size, capacity; uint64_t limit; } onet_buffer;

static const char *onet_name(onet_code c) {
  static const char *names[] = {"ok", "bad_url", "not_https", "timeout", "dns", "connect", "tls", "redirect", "auth",
    "forbidden", "not_found", "rate_limited", "server_error", "http_error", "cancelled", "too_big", "io", "network"};
  return (unsigned)c < sizeof(names) / sizeof(*names) ? names[c] : "unknown";
}
static void onet_fail(onet_result *r, onet_code code, const char *fmt, ...) {
  va_list args;
  r->code = code;
  va_start(args, fmt);
  vsnprintf(r->message, sizeof(r->message), fmt, args);
  va_end(args);
}
static int onet_sink_buffer(void *context, const void *data, size_t size) {
  onet_buffer *b = context;
  if (b->limit && b->size + size > b->limit) return 1;
  if (b->size + size + 1 > b->capacity) {
    size_t cap = b->capacity ? b->capacity : 65536;
    char *p;
    while (cap < b->size + size + 1) cap *= 2;
    p = realloc(b->data, cap);
    if (!p) return 1;
    b->data = p; b->capacity = cap;
  }
  memcpy(b->data + b->size, data, size);
  b->size += size;
  b->data[b->size] = 0;
  return 0;
}
static wchar_t *onet_wide(const char *s) {
  int n = MultiByteToWideChar(CP_UTF8, 0, s, -1, NULL, 0);
  wchar_t *w = n > 0 ? malloc((size_t)n * sizeof(wchar_t)) : NULL;
  if (w && !MultiByteToWideChar(CP_UTF8, 0, s, -1, w, n)) { free(w); w = NULL; }
  return w;
}
static int onet_loopback(const wchar_t *host) {
  return !_wcsicmp(host, L"127.0.0.1") || !_wcsicmp(host, L"localhost") || !_wcsicmp(host, L"[::1]") || !_wcsicmp(host, L"::1");
}
/* http:// -> https:// for URLs found in catalogs and typed by the user. */
static void onet_secure(const char *url, char *out, size_t size) {
  if (!_strnicmp(url, "http://", 7) && _strnicmp(url + 7, "127.0.0.1", 9) && _strnicmp(url + 7, "localhost", 9))
    snprintf(out, size, "https://%s", url + 7);
  else snprintf(out, size, "%s", url);
}
static void onet_map_win_error(onet_result *r, DWORD e, unsigned receive_ms) {
  r->win_error = e;
  switch (e) {
    case ERROR_WINHTTP_TIMEOUT: onet_fail(r, ONET_TIMEOUT, "连接超时：%u 秒内没有收到服务器响应，请检查网络或稍后重试。", (receive_ms + 999) / 1000); break;
    case ERROR_WINHTTP_NAME_NOT_RESOLVED: onet_fail(r, ONET_DNS, "无法解析域名，请检查书源地址或网络连接。"); break;
    case ERROR_WINHTTP_CANNOT_CONNECT: case ERROR_WINHTTP_CONNECTION_ERROR:
      onet_fail(r, ONET_CONNECT, "无法连接到服务器，请检查书源地址或网络连接。"); break;
    case ERROR_WINHTTP_SECURE_FAILURE: case ERROR_WINHTTP_SECURE_CERT_CN_INVALID: case ERROR_WINHTTP_SECURE_CERT_DATE_INVALID:
    case ERROR_WINHTTP_SECURE_INVALID_CA: case ERROR_WINHTTP_SECURE_CERT_REV_FAILED: case ERROR_WINHTTP_SECURE_INVALID_CERT:
    case ERROR_WINHTTP_SECURE_CERT_REVOKED: case ERROR_WINHTTP_SECURE_CERT_WRONG_USAGE: case ERROR_WINHTTP_SECURE_CHANNEL_ERROR:
      onet_fail(r, ONET_TLS, "安全连接失败：服务器证书无效或已过期，已拒绝连接。"); break;
    case ERROR_WINHTTP_REDIRECT_FAILED:
      onet_fail(r, ONET_REDIRECT, "重定向失败：重定向次数过多，或被重定向到了不安全的 http 地址。"); break;
    case ERROR_WINHTTP_INVALID_URL: case ERROR_WINHTTP_UNRECOGNIZED_SCHEME:
      onet_fail(r, ONET_BAD_URL, "书源地址无效。"); break;
    case ERROR_WINHTTP_OPERATION_CANCELLED: onet_fail(r, ONET_CANCELLED, "已取消。"); break;
    default: onet_fail(r, ONET_NETWORK, "网络错误（代码 %lu），请稍后重试。", (unsigned long)e);
  }
}
static void onet_map_status(onet_result *r, int status) {
  r->http_status = status;
  if (status == 401) onet_fail(r, ONET_AUTH, "该书源需要登录（HTTP 401），目前不支持账号密码。");
  else if (status == 403) onet_fail(r, ONET_FORBIDDEN, "没有访问权限（HTTP 403）。");
  else if (status == 404 || status == 410) onet_fail(r, ONET_NOT_FOUND, "地址不存在（HTTP %d），请检查书源地址。", status);
  else if (status == 408 || status == 504) onet_fail(r, ONET_TIMEOUT, "服务器响应超时（HTTP %d），请稍后重试。", status);
  else if (status == 429) onet_fail(r, ONET_RATE, "请求过于频繁（HTTP 429），请稍后再试。");
  else if (status >= 500) onet_fail(r, ONET_SERVER, "书源服务器出错（HTTP %d），请稍后再试。", status);
  else onet_fail(r, ONET_HTTP, "服务器返回了意外的状态（HTTP %d）。", status);
}
/* One GET. Body bytes go to options->sink; on non-2xx nothing is delivered. */
static int onet_get(const char *url, const onet_options *o, onet_result *r) {
  URL_COMPONENTS u;
  wchar_t host[256], path[2048], extra[2048], *wurl = NULL;
  HINTERNET session = NULL, connection = NULL, request = NULL;
  unsigned rs = o->resolve_ms ? o->resolve_ms : 10000, cs = o->connect_ms ? o->connect_ms : 10000;
  unsigned ss = o->send_ms ? o->send_ms : 15000, vs = o->receive_ms ? o->receive_ms : 30000;
  uint64_t limit = o->max_bytes ? o->max_bytes : (uint64_t)64 * 1024 * 1024, total = 0, done = 0;
  DWORD status = 0, size = sizeof(status), flags;
  char chunk[32768];
  memset(r, 0, sizeof(*r));
  snprintf(r->final_url, sizeof(r->final_url), "%s", url);
  if (!url || !(wurl = onet_wide(url))) { onet_fail(r, ONET_BAD_URL, "书源地址无效。"); return 0; }
  memset(&u, 0, sizeof(u));
  u.dwStructSize = sizeof(u);
  u.lpszHostName = host; u.dwHostNameLength = 256;
  u.lpszUrlPath = path; u.dwUrlPathLength = 2048;
  u.lpszExtraInfo = extra; u.dwExtraInfoLength = 2048;
  if (!WinHttpCrackUrl(wurl, 0, 0, &u) || (u.nScheme != INTERNET_SCHEME_HTTPS && u.nScheme != INTERNET_SCHEME_HTTP)) {
    onet_fail(r, ONET_BAD_URL, "书源地址无效，请输入以 https:// 开头的地址。"); goto done;
  }
  if (u.nScheme == INTERNET_SCHEME_HTTP && !onet_loopback(host)) {
    onet_fail(r, ONET_NOT_HTTPS, "仅支持 HTTPS 书源，已拒绝不安全的 http:// 地址。"); goto done;
  }
  if (o->cancel && *o->cancel) { onet_fail(r, ONET_CANCELLED, "已取消。"); goto done; }
  session = WinHttpOpen(L"EXReader/1.0 (OPDS)", WINHTTP_ACCESS_TYPE_DEFAULT_PROXY, WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
  if (!session) { onet_map_win_error(r, GetLastError(), vs); goto done; }
  WinHttpSetTimeouts(session, (int)rs, (int)cs, (int)ss, (int)vs);
  connection = WinHttpConnect(session, host, u.nPort, 0);
  if (!connection) { onet_map_win_error(r, GetLastError(), vs); goto done; }
  wcscat(path, extra);
  request = WinHttpOpenRequest(connection, L"GET", path, NULL, WINHTTP_NO_REFERER, WINHTTP_DEFAULT_ACCEPT_TYPES,
                               u.nScheme == INTERNET_SCHEME_HTTPS ? WINHTTP_FLAG_SECURE : 0);
  if (!request) { onet_map_win_error(r, GetLastError(), vs); goto done; }
  {
    DWORD policy = WINHTTP_OPTION_REDIRECT_POLICY_DISALLOW_HTTPS_TO_HTTP, redirects = 10;
    WinHttpSetOption(request, WINHTTP_OPTION_REDIRECT_POLICY, &policy, sizeof(policy));
    WinHttpSetOption(request, WINHTTP_OPTION_MAX_HTTP_AUTOMATIC_REDIRECTS, &redirects, sizeof(redirects));
  }
  {
    wchar_t header[256];
    wchar_t *accept = o->accept ? onet_wide(o->accept) : NULL;
    swprintf(header, 256, L"Accept: %ls", accept ? accept : L"*/*");
    free(accept);
    WinHttpAddRequestHeaders(request, header, (DWORD)-1, WINHTTP_ADDREQ_FLAG_ADD);
  }
  if (!WinHttpSendRequest(request, WINHTTP_NO_ADDITIONAL_HEADERS, 0, WINHTTP_NO_REQUEST_DATA, 0, 0, 0) ||
      !WinHttpReceiveResponse(request, NULL)) { onet_map_win_error(r, GetLastError(), vs); goto done; }
  if (!WinHttpQueryHeaders(request, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER, WINHTTP_HEADER_NAME_BY_INDEX, &status, &size, WINHTTP_NO_HEADER_INDEX)) {
    onet_map_win_error(r, GetLastError(), vs); goto done;
  }
  r->http_status = (int)status;
  {
    wchar_t final_url[2048], type[96];
    DWORD n = sizeof(final_url), t = sizeof(type);
    if (WinHttpQueryOption(request, WINHTTP_OPTION_URL, final_url, &n))
      WideCharToMultiByte(CP_UTF8, 0, final_url, -1, r->final_url, (int)sizeof(r->final_url), NULL, NULL);
    if (WinHttpQueryHeaders(request, WINHTTP_QUERY_CONTENT_TYPE, WINHTTP_HEADER_NAME_BY_INDEX, type, &t, WINHTTP_NO_HEADER_INDEX))
      WideCharToMultiByte(CP_UTF8, 0, type, -1, r->content_type, (int)sizeof(r->content_type), NULL, NULL);
  }
  if (status < 200 || status >= 300) { onet_map_status(r, (int)status); goto done; }
  flags = WINHTTP_QUERY_CONTENT_LENGTH | WINHTTP_QUERY_FLAG_NUMBER;
  {
    DWORD length = 0, n = sizeof(length);
    if (WinHttpQueryHeaders(request, flags, WINHTTP_HEADER_NAME_BY_INDEX, &length, &n, WINHTTP_NO_HEADER_INDEX)) total = length;
  }
  if (total > limit) { onet_fail(r, ONET_TOO_BIG, "文件过大（超过 %llu MB），已停止。", (unsigned long long)(limit >> 20)); goto done; }
  for (;;) {
    DWORD got = 0;
    if (o->cancel && *o->cancel) { onet_fail(r, ONET_CANCELLED, "已取消。"); goto done; }
    if (!WinHttpReadData(request, chunk, sizeof(chunk), &got)) { onet_map_win_error(r, GetLastError(), vs); goto done; }
    if (!got) break;
    done += got;
    if (done > limit) { onet_fail(r, ONET_TOO_BIG, "文件过大（超过 %llu MB），已停止。", (unsigned long long)(limit >> 20)); goto done; }
    if (o->sink && o->sink(o->context, chunk, got)) { onet_fail(r, ONET_IO, "无法保存下载内容（磁盘或内存不足）。"); goto done; }
    if (o->progress) o->progress(o->context, done, total);
  }
  if (total && done < total) { onet_fail(r, ONET_NETWORK, "下载不完整（%llu / %llu 字节）。", (unsigned long long)done, (unsigned long long)total); goto done; }
  r->code = ONET_OK;
done:
  if (request) WinHttpCloseHandle(request);
  if (connection) WinHttpCloseHandle(connection);
  if (session) WinHttpCloseHandle(session);
  free(wurl);
  return r->code == ONET_OK;
}

/* ---- 10 minute feed cache ------------------------------------------- */
#define ONET_CACHE_SLOTS 32
#define ONET_CACHE_MS (10ULL * 60 * 1000)
typedef struct { char *url; char *data; size_t size; ULONGLONG at; } onet_cache_entry;
static onet_cache_entry onet_cache[ONET_CACHE_SLOTS];
static ULONGLONG onet_cache_ttl_ms = ONET_CACHE_MS;
static unsigned onet_cache_hits, onet_cache_misses;
static CRITICAL_SECTION onet_cache_lock;
static int onet_cache_ready;
static void onet_cache_init(void) { if (!onet_cache_ready) { InitializeCriticalSection(&onet_cache_lock); onet_cache_ready = 1; } }
static inline void onet_cache_clear(void) {
  onet_cache_init();
  EnterCriticalSection(&onet_cache_lock);
  for (int i = 0; i < ONET_CACHE_SLOTS; i++) { free(onet_cache[i].url); free(onet_cache[i].data); memset(&onet_cache[i], 0, sizeof(onet_cache[i])); }
  LeaveCriticalSection(&onet_cache_lock);
}
/* Fetches a small document into memory (<= 16 MiB), serving it from the cache
   when it is younger than the TTL. use_cache == 0 bypasses and refreshes. */
static int onet_fetch(const char *url, const onet_options *base, int use_cache, onet_buffer *out, onet_result *r) {
  onet_options o = *base;
  int slot = -1;
  ULONGLONG now = GetTickCount64();
  onet_cache_init();
  memset(out, 0, sizeof(*out));
  EnterCriticalSection(&onet_cache_lock);
  for (int i = 0; i < ONET_CACHE_SLOTS; i++)
    if (onet_cache[i].url && !strcmp(onet_cache[i].url, url)) {
      if (use_cache && now - onet_cache[i].at < onet_cache_ttl_ms) {
        out->data = malloc(onet_cache[i].size + 1);
        if (out->data) {
          memcpy(out->data, onet_cache[i].data, onet_cache[i].size + 1);
          out->size = onet_cache[i].size;
          onet_cache_hits++;
          LeaveCriticalSection(&onet_cache_lock);
          memset(r, 0, sizeof(*r));
          snprintf(r->final_url, sizeof(r->final_url), "%s", url);
          r->http_status = 200; r->from_cache = 1;
          return 1;
        }
      }
      slot = i;
      break;
    }
  onet_cache_misses++;
  LeaveCriticalSection(&onet_cache_lock);
  out->limit = (uint64_t)16 * 1024 * 1024;
  o.sink = onet_sink_buffer; o.context = out; o.progress = NULL; o.max_bytes = out->limit;
  if (!o.accept) o.accept = "application/atom+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.1";
  if (!onet_get(url, &o, r)) { free(out->data); memset(out, 0, sizeof(*out)); return 0; }
  EnterCriticalSection(&onet_cache_lock);
  if (slot < 0) {
    ULONGLONG oldest = ~0ULL;
    slot = 0;
    for (int i = 0; i < ONET_CACHE_SLOTS; i++) {
      if (!onet_cache[i].url) { slot = i; break; }
      if (onet_cache[i].at < oldest) { oldest = onet_cache[i].at; slot = i; }
    }
  }
  free(onet_cache[slot].url); free(onet_cache[slot].data);
  onet_cache[slot].url = _strdup(url);
  onet_cache[slot].data = malloc(out->size + 1);
  if (onet_cache[slot].url && onet_cache[slot].data) {
    memcpy(onet_cache[slot].data, out->data, out->size + 1);
    onet_cache[slot].size = out->size; onet_cache[slot].at = GetTickCount64();
  } else { free(onet_cache[slot].url); free(onet_cache[slot].data); memset(&onet_cache[slot], 0, sizeof(onet_cache[slot])); }
  LeaveCriticalSection(&onet_cache_lock);
  return 1;
}

/* ---- download to a file ---------------------------------------------- */
typedef struct { HANDLE file; uint64_t written; void (*progress)(void *, uint64_t, uint64_t); void *context; } onet_file_sink;
static int onet_sink_file(void *context, const void *data, size_t size) {
  onet_file_sink *s = context;
  DWORD n = 0;
  if (!WriteFile(s->file, data, (DWORD)size, &n, NULL) || n != size) return 1;
  s->written += n;
  return 0;
}
/* Streams into "<path>.part" and renames on success; the partial file is
   removed on any failure or cancellation. */
static int onet_download(const char *url, const wchar_t *path, const onet_options *base, onet_result *r) {
  wchar_t part[MAX_PATH * 2];
  onet_options o = *base;
  onet_file_sink sink;
  swprintf(part, MAX_PATH * 2, L"%ls.part", path);
  memset(&sink, 0, sizeof(sink));
  sink.file = CreateFileW(part, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
  if (sink.file == INVALID_HANDLE_VALUE) { memset(r, 0, sizeof(*r)); onet_fail(r, ONET_IO, "无法创建下载文件（错误 %lu）。", GetLastError()); return 0; }
  o.sink = onet_sink_file; o.context = &sink;
  if (!o.max_bytes) o.max_bytes = (uint64_t)512 * 1024 * 1024;
  if (!o.accept) o.accept = "application/epub+zip, application/pdf, */*;q=0.5";
  if (onet_get(url, &o, r)) {
    if (!FlushFileBuffers(sink.file) || !CloseHandle(sink.file)) { sink.file = INVALID_HANDLE_VALUE; onet_fail(r, ONET_IO, "无法写入下载文件。"); }
    else {
      sink.file = INVALID_HANDLE_VALUE;
      if (MoveFileExW(part, path, MOVEFILE_REPLACE_EXISTING)) return 1;
      onet_fail(r, ONET_IO, "无法保存下载文件（错误 %lu）。", GetLastError());
    }
  }
  if (sink.file != INVALID_HANDLE_VALUE) CloseHandle(sink.file);
  DeleteFileW(part);
  return 0;
}
#endif
