/* SPDX-License-Identifier: MIT */
/* https transport for POSIX builds (Linux, macOS): libcurl with the system trust store,
   no proxy, no cookies, no redirect following and identity encoding only. One request
   per call, as the frozen OPDS module requires. */
#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#include "browser_internal.h"
#include <curl/curl.h>
#include <ctype.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
  opds_head_fn head;
  opds_body_fn body;
  void *user;
  const opds_control *control;
  int status;
  long long length;
  char ctype[256], location[1024], www[160];
  int head_called;
  int skip;
  int stopped;
  int cancelled;
  size_t discarded;
} curl_ctx;

static void copy_value(const char *value, size_t n, char *out, size_t cap) {
  size_t begin = 0, end = n;
  if (!cap) return;
  while (begin < end && (value[begin] == ' ' || value[begin] == '\t')) begin++;
  while (end > begin && (value[end - 1] == ' ' || value[end - 1] == '\t' || value[end - 1] == '\r')) end--;
  if (end - begin >= cap) end = begin + cap - 1;
  memcpy(out, value + begin, end - begin);
  out[end - begin] = 0;
}

static int starts_with_ci(const char *text, const char *prefix) {
  for (; *prefix; text++, prefix++)
    if (tolower((unsigned char)*text) != tolower((unsigned char)*prefix)) return 0;
  return 1;
}

static int header_is(const char *line, size_t n, const char *name) {
  size_t l = strlen(name), i;
  if (n <= l || line[l] != ':') return 0;
  for (i = 0; i < l; i++)
    if (tolower((unsigned char)line[i]) != tolower((unsigned char)name[i])) return 0;
  return 1;
}

static void deliver_head(curl_ctx *c) {
  opds_response response;
  if (c->head_called) return;
  if (c->status >= 100 && c->status < 200) return; /* interim response: wait for the final one */
  c->head_called = 1;
  memset(&response, 0, sizeof response);
  response.status = c->status;
  response.content_type = c->ctype[0] ? c->ctype : NULL;
  response.location = c->location[0] ? c->location : NULL;
  response.www_authenticate = c->www[0] ? c->www : NULL;
  response.content_length = c->length;
  if (c->head(c->user, &response)) c->skip = 1;
  if (c->status == 204 || c->status == 304 || (c->status >= 100 && c->status < 200)) c->skip = 1;
}

static size_t on_header(char *data, size_t size, size_t count, void *user) {
  curl_ctx *c = (curl_ctx *)user;
  size_t n = size * count;
  if (n >= 5 && starts_with_ci(data, "HTTP/")) {
    const char *space = (const char *)memchr(data, ' ', n);
    c->status = 0;
    c->length = -1;
    c->ctype[0] = c->location[0] = c->www[0] = 0;
    c->head_called = 0;
    c->skip = 0;
    c->stopped = 0;
    if (space) {
      const char *p = space + 1;
      size_t i;
      for (i = 0; i < 3 && p + i < data + n; i++) {
        if (p[i] < '0' || p[i] > '9') break;
        c->status = c->status * 10 + (p[i] - '0');
      }
    }
    return n;
  }
  if (n >= 2 && data[0] == '\r' && data[1] == '\n') {
    deliver_head(c);
    return n;
  }
  {
    const char *colon = (const char *)memchr(data, ':', n);
    size_t vn;
    const char *value;
    if (!colon) return n;
    value = colon + 1;
    vn = (size_t)(data + n - value);
    if (header_is(data, n, "Content-Type")) copy_value(value, vn, c->ctype, sizeof c->ctype);
    else if (header_is(data, n, "Location")) copy_value(value, vn, c->location, sizeof c->location);
    else if (header_is(data, n, "WWW-Authenticate") && !c->www[0]) copy_value(value, vn, c->www, sizeof c->www);
    else if (header_is(data, n, "Content-Length")) {
      size_t i = 0;
      long long total = 0;
      int digits = 0;
      while (i < vn && (value[i] == ' ' || value[i] == '\t')) i++;
      for (; i < vn; i++) {
        if (value[i] < '0' || value[i] > '9') { digits = 0; break; }
        if (total > (9223372036854775807LL - 9) / 10) { digits = 0; break; }
        total = total * 10 + (value[i] - '0');
        digits = 1;
      }
      c->length = digits ? total : -1;
    }
  }
  return n;
}

static size_t on_body(char *data, size_t size, size_t count, void *user) {
  curl_ctx *c = (curl_ctx *)user;
  size_t n = size * count;
  if (c->skip) {
    c->discarded += n;
    if (c->discarded > (size_t)(1u << 20)) { c->stopped = 2; return 0; }
    return n;
  }
  if (c->control && c->control->cancelled && c->control->cancelled(c->control->context)) {
    c->cancelled = 1;
    return 0;
  }
  if (c->body(c->user, data, n)) { c->stopped = 1; return 0; }
  return n;
}

static int on_progress(void *user, curl_off_t dt, curl_off_t dn, curl_off_t ut, curl_off_t un) {
  curl_ctx *c = (curl_ctx *)user;
  (void)dt; (void)dn; (void)ut; (void)un;
  if (c->control && c->control->cancelled && c->control->cancelled(c->control->context)) {
    c->cancelled = 1;
    return 1;
  }
  return 0;
}

static pthread_once_t init_once = PTHREAD_ONCE_INIT;
static void init_curl(void) { curl_global_init(CURL_GLOBAL_DEFAULT); }

opds_status reader_opds_platform_tls_fetch(const opds_request *request, unsigned timeout_ms,
                                           const opds_control *control, opds_head_fn head,
                                           opds_body_fn body, void *user, opds_error *error) {
  CURL *handle;
  CURLcode code;
  struct curl_slist *headers = NULL;
  curl_ctx ctx;
  opds_status status;
  char line[1200];
  long response_code = 0;
  curl_off_t length = -1;

  memset(&ctx, 0, sizeof ctx);
  ctx.head = head;
  ctx.body = body;
  ctx.user = user;
  ctx.control = control;
  ctx.length = -1;
  pthread_once(&init_once, init_curl);
  handle = curl_easy_init();
  if (!handle) return reader_opds_fail(error, OPDS_MEMORY, "libcurl is unavailable");
  headers = curl_slist_append(headers, "Accept-Encoding: identity");
  headers = curl_slist_append(headers, "Expect:");
  if (request->accept) {
    snprintf(line, sizeof line, "Accept: %s", request->accept);
    headers = curl_slist_append(headers, line);
  }
  if (request->authorization) {
    snprintf(line, sizeof line, "Authorization: %s", request->authorization);
    headers = curl_slist_append(headers, line);
  }
  curl_easy_setopt(handle, CURLOPT_URL, request->url);
  curl_easy_setopt(handle, CURLOPT_HTTPGET, 1L);
  curl_easy_setopt(handle, CURLOPT_FOLLOWLOCATION, 0L);
  curl_easy_setopt(handle, CURLOPT_MAXREDIRS, 0L);
  curl_easy_setopt(handle, CURLOPT_NOSIGNAL, 1L);
  curl_easy_setopt(handle, CURLOPT_HTTP_VERSION, (long)CURL_HTTP_VERSION_1_1);
  curl_easy_setopt(handle, CURLOPT_CONNECTTIMEOUT_MS, (long)timeout_ms);
  /* The public transport contract forbids ambient proxy configuration. */
  curl_easy_setopt(handle, CURLOPT_PROXY, "");
  curl_easy_setopt(handle, CURLOPT_LOW_SPEED_LIMIT, 1L);
  curl_easy_setopt(handle, CURLOPT_LOW_SPEED_TIME, (long)((timeout_ms + 999) / 1000));
  curl_easy_setopt(handle, CURLOPT_SSL_VERIFYPEER, 1L);
  curl_easy_setopt(handle, CURLOPT_SSL_VERIFYHOST, 2L);
  curl_easy_setopt(handle, CURLOPT_HTTPHEADER, headers);
  curl_easy_setopt(handle, CURLOPT_HEADERFUNCTION, on_header);
  curl_easy_setopt(handle, CURLOPT_HEADERDATA, &ctx);
  curl_easy_setopt(handle, CURLOPT_WRITEFUNCTION, on_body);
  curl_easy_setopt(handle, CURLOPT_WRITEDATA, &ctx);
  curl_easy_setopt(handle, CURLOPT_NOPROGRESS, 0L);
  curl_easy_setopt(handle, CURLOPT_XFERINFOFUNCTION, on_progress);
  curl_easy_setopt(handle, CURLOPT_XFERINFODATA, &ctx);
#if LIBCURL_VERSION_NUM >= 0x075500
  curl_easy_setopt(handle, CURLOPT_PROTOCOLS_STR, "http,https");
#else
  curl_easy_setopt(handle, CURLOPT_PROTOCOLS, (long)(CURLPROTO_HTTP | CURLPROTO_HTTPS));
#endif
  code = curl_easy_perform(handle);
  if (code == CURLE_OK) curl_easy_getinfo(handle, CURLINFO_RESPONSE_CODE, &response_code);
  if (code == CURLE_OK) curl_easy_getinfo(handle, CURLINFO_CONTENT_LENGTH_DOWNLOAD_T, &length);
  if (!ctx.head_called && ctx.status != 0) deliver_head(&ctx);
  if (ctx.length < 0 && length >= 0) ctx.length = (long long)length;
  if (code == CURLE_OK) {
    status = OPDS_OK;
  } else if (ctx.skip && (code == CURLE_OK || code == CURLE_WRITE_ERROR)) {
    status = OPDS_OK;
  } else if (ctx.cancelled) {
    status = reader_opds_fail(error, OPDS_CANCELLED, "cancelled during the TLS transfer");
  } else if (ctx.stopped == 1) {
    status = reader_opds_fail(error, OPDS_ABORTED, "transfer stopped by the caller");
  } else if (code == CURLE_OPERATION_TIMEDOUT || code == CURLE_OPERATION_TIMEOUTED) {
    status = reader_opds_fail(error, OPDS_TIMEOUT, "the TLS request timed out");
  } else if (code == CURLE_ABORTED_BY_CALLBACK) {
    status = reader_opds_fail(error, OPDS_CANCELLED, "cancelled during the TLS transfer");
  } else if (code == CURLE_WRITE_ERROR) {
    status = reader_opds_fail(error, OPDS_ABORTED, "transfer stopped by the caller");
  } else if (code == CURLE_UNSUPPORTED_PROTOCOL) {
    status = reader_opds_fail(error, OPDS_NEEDS_HOST, "libcurl refuses this URL scheme");
  } else if (code == CURLE_SSL_CONNECT_ERROR || code == CURLE_PEER_FAILED_VERIFICATION) {
    status = reader_opds_fail(error, OPDS_IO, "TLS verification or handshake failed: %s", curl_easy_strerror(code));
  } else {
    status = reader_opds_fail(error, OPDS_IO, "TLS request failed: %s", curl_easy_strerror(code));
  }
  curl_slist_free_all(headers);
  curl_easy_cleanup(handle);
  return status;
}
#endif /* !_WIN32 */
