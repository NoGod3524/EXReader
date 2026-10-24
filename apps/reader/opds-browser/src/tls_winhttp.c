/* SPDX-License-Identifier: MIT */
/* https transport for Windows builds: WinHTTP, system trust store, no proxy, no
   cookies, no automatic redirects and identity encoding only. One request per call,
   as the frozen OPDS module requires. */
#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#include <winhttp.h>
#include "browser_internal.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

#ifndef WINHTTP_ACCESS_TYPE_NO_PROXY
#define WINHTTP_ACCESS_TYPE_NO_PROXY 1
#endif

#define WINHTTP_UA L"EXReader-OPDS/0.1"

static opds_status win_fail(opds_error *error, const char *what) {
  DWORD code = GetLastError();
  if (code == ERROR_WINHTTP_TIMEOUT) return reader_opds_fail(error, OPDS_TIMEOUT, "%s timed out", what);
  if (code == ERROR_WINHTTP_SECURE_FAILURE)
    return reader_opds_fail(error, OPDS_IO, "%s failed TLS verification", what);
  return reader_opds_fail(error, OPDS_IO, "%s failed (WinHTTP %lu)", what, (unsigned long)code);
}

static wchar_t *to_wide(const char *text) {
  int n;
  wchar_t *w;
  if (!text) return NULL;
  n = MultiByteToWideChar(CP_UTF8, 0, text, -1, NULL, 0);
  if (n <= 0) return NULL;
  w = (wchar_t *)malloc((size_t)n * sizeof(*w));
  if (!w) return NULL;
  if (!MultiByteToWideChar(CP_UTF8, 0, text, -1, w, n)) { free(w); return NULL; }
  return w;
}

static wchar_t *header_line(const wchar_t *name, const wchar_t *value) {
  size_t n = wcslen(name) + wcslen(value) + 4;
  wchar_t *line = (wchar_t *)malloc(n * sizeof(*line));
  if (!line) return NULL;
  if (swprintf(line, n, L"%ls: %ls\r\n", name, value) < 0) { free(line); return NULL; }
  return line;
}

static int header_string(HINTERNET request, DWORD info, char *out, size_t cap) {
  wchar_t value[1024];
  DWORD size = (DWORD)sizeof value;
  DWORD index = 0;
  int written;
  if (cap) out[0] = 0;
  if (!cap) return 0;
  if (!WinHttpQueryHeaders(request, info, WINHTTP_HEADER_NAME_BY_INDEX, value, &size, &index)) return 0;
  written = WideCharToMultiByte(CP_UTF8, 0, value, -1, out, (int)cap, NULL, NULL);
  if (!written) { out[0] = 0; return 0; }
  out[cap - 1] = 0;
  return 1;
}

static int64_t content_length(HINTERNET request) {
  wchar_t value[64];
  DWORD size = (DWORD)sizeof value;
  DWORD index = 0;
  int64_t total = -1;
  size_t i;
  if (!WinHttpQueryHeaders(request, WINHTTP_QUERY_CONTENT_LENGTH, WINHTTP_HEADER_NAME_BY_INDEX, value, &size, &index))
    return -1;
  for (i = 0; value[i]; i++) {
    if (value[i] < L'0' || value[i] > L'9') return -1;
    if (total < 0) total = 0;
    if (total > (INT64_MAX - 9) / 10) return -1;
    total = total * 10 + (int64_t)(value[i] - L'0');
  }
  return total;
}

opds_status reader_opds_platform_tls_fetch(const opds_request *request, unsigned timeout_ms,
                                           const opds_control *control, opds_head_fn head,
                                           opds_body_fn body, void *user, opds_error *error) {
  HINTERNET session = NULL, connection = NULL, handle = NULL;
  wchar_t *target = NULL, *host = NULL, *accept = NULL, *auth = NULL, *line = NULL;
  wchar_t path[8192];
  URL_COMPONENTS parts;
  opds_response response;
  opds_status status = OPDS_OK;
  char ctype[256], location[1024], www[160];
  DWORD flags = 0, feature = 0, code = 0, size = 0, index = 0;
  unsigned char buffer[16384];
  int port;

  ctype[0] = location[0] = www[0] = 0;
  memset(&response, 0, sizeof response);
  memset(&parts, 0, sizeof parts);
  target = to_wide(request->url);
  if (!target) return reader_opds_fail(error, OPDS_MEMORY, "out of memory");
  parts.dwStructSize = sizeof parts;
  parts.dwSchemeLength = (DWORD)-1;
  parts.dwHostNameLength = (DWORD)-1;
  parts.dwUrlPathLength = (DWORD)-1;
  parts.dwExtraInfoLength = (DWORD)-1;
  if (!WinHttpCrackUrl(target, 0, 0, &parts)) {
    status = reader_opds_fail(error, OPDS_ARGUMENT, "URL cannot be parsed");
    goto done;
  }
  if (parts.nScheme == INTERNET_SCHEME_HTTPS) flags = WINHTTP_FLAG_SECURE;
  else if (parts.nScheme != INTERNET_SCHEME_HTTP) {
    status = reader_opds_fail(error, OPDS_NEEDS_HOST, "only http and https URLs are supported");
    goto done;
  }
  host = (wchar_t *)malloc(((size_t)parts.dwHostNameLength + 1) * sizeof(*host));
  if (!host) { status = reader_opds_fail(error, OPDS_MEMORY, "out of memory"); goto done; }
  memcpy(host, parts.lpszHostName, (size_t)parts.dwHostNameLength * sizeof(*host));
  host[parts.dwHostNameLength] = 0;
  port = (int)parts.nPort;
  {
    size_t used = 0;
    if (parts.dwUrlPathLength) {
      if ((size_t)parts.dwUrlPathLength + 2 >= sizeof path / sizeof(*path)) {
        status = reader_opds_fail(error, OPDS_LIMIT, "URL path too long");
        goto done;
      }
      memcpy(path, parts.lpszUrlPath, (size_t)parts.dwUrlPathLength * sizeof(*path));
      used = (size_t)parts.dwUrlPathLength;
    }
    if (parts.dwExtraInfoLength) {
      if (used + (size_t)parts.dwExtraInfoLength + 2 >= sizeof path / sizeof(*path)) {
        status = reader_opds_fail(error, OPDS_LIMIT, "URL path too long");
        goto done;
      }
      memcpy(path + used, parts.lpszExtraInfo, (size_t)parts.dwExtraInfoLength * sizeof(*path));
      used += (size_t)parts.dwExtraInfoLength;
    }
    if (!used) { path[0] = L'/'; used = 1; }
    path[used] = 0;
  }
  if (control && control->cancelled && control->cancelled(control->context)) {
    status = reader_opds_fail(error, OPDS_CANCELLED, "cancelled before connecting");
    goto done;
  }
  session = WinHttpOpen(WINHTTP_UA, WINHTTP_ACCESS_TYPE_NO_PROXY, WINHTTP_NO_PROXY_NAME,
                        WINHTTP_NO_PROXY_BYPASS, 0);
  if (!session) { status = win_fail(error, "opening an HTTP session"); goto done; }
  {
    int t = timeout_ms > 0x7fffffffu ? 0x7fffffff : (int)timeout_ms;
    if (!WinHttpSetTimeouts(session, t, t, t, t)) { status = win_fail(error, "setting timeouts"); goto done; }
  }
  connection = WinHttpConnect(session, host, (INTERNET_PORT)port, 0);
  if (!connection) { status = win_fail(error, "connecting"); goto done; }
  handle = WinHttpOpenRequest(connection, L"GET", path, NULL, WINHTTP_NO_REFERER,
                              WINHTTP_DEFAULT_ACCEPT_TYPES, flags);
  if (!handle) { status = win_fail(error, "opening the request"); goto done; }
  feature = WINHTTP_DISABLE_REDIRECTS;
  if (!WinHttpSetOption(handle, WINHTTP_OPTION_DISABLE_FEATURE, &feature, sizeof feature)) {
    status = win_fail(error, "disabling redirects");
    goto done;
  }
  feature = WINHTTP_DISABLE_COOKIES;
  WinHttpSetOption(handle, WINHTTP_OPTION_DISABLE_FEATURE, &feature, sizeof feature);
  line = header_line(L"Accept-Encoding", L"identity");
  if (!line) { status = reader_opds_fail(error, OPDS_MEMORY, "out of memory"); goto done; }
  WinHttpAddRequestHeaders(handle, line, (DWORD)-1, WINHTTP_ADDREQ_FLAG_ADD);
  free(line);
  line = NULL;
  if (request->accept) {
    accept = to_wide(request->accept);
    if (!accept) { status = reader_opds_fail(error, OPDS_MEMORY, "out of memory"); goto done; }
    line = header_line(L"Accept", accept);
    if (!line) { status = reader_opds_fail(error, OPDS_MEMORY, "out of memory"); goto done; }
    WinHttpAddRequestHeaders(handle, line, (DWORD)-1, WINHTTP_ADDREQ_FLAG_ADD);
    free(line);
    line = NULL;
  }
  if (request->authorization) {
    auth = to_wide(request->authorization);
    if (!auth) { status = reader_opds_fail(error, OPDS_MEMORY, "out of memory"); goto done; }
    line = header_line(L"Authorization", auth);
    if (!line) { status = reader_opds_fail(error, OPDS_MEMORY, "out of memory"); goto done; }
    WinHttpAddRequestHeaders(handle, line, (DWORD)-1, WINHTTP_ADDREQ_FLAG_ADD | WINHTTP_ADDREQ_FLAG_REPLACE);
    free(line);
    line = NULL;
  }
  if (!WinHttpSendRequest(handle, WINHTTP_NO_ADDITIONAL_HEADERS, 0, WINHTTP_NO_REQUEST_DATA, 0, 0, 0)) {
    status = win_fail(error, "sending the request");
    goto done;
  }
  if (!WinHttpReceiveResponse(handle, NULL)) { status = win_fail(error, "receiving the response"); goto done; }
  size = (DWORD)sizeof code;
  index = 0;
  if (!WinHttpQueryHeaders(handle, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
                           WINHTTP_HEADER_NAME_BY_INDEX, &code, &size, &index)) {
    status = win_fail(error, "reading the response status");
    goto done;
  }
  header_string(handle, WINHTTP_QUERY_CONTENT_TYPE, ctype, sizeof ctype);
  header_string(handle, WINHTTP_QUERY_LOCATION, location, sizeof location);
  header_string(handle, WINHTTP_QUERY_WWW_AUTHENTICATE, www, sizeof www);
  response.status = (int)code;
  response.content_type = ctype[0] ? ctype : NULL;
  response.location = location[0] ? location : NULL;
  response.www_authenticate = www[0] ? www : NULL;
  response.content_length = content_length(handle);
  if (head(user, &response)) goto done;
  if (response.status == 204 || response.status == 304 || (response.status >= 100 && response.status < 200)) goto done;
  for (;;) {
    DWORD read = 0;
    if (control && control->cancelled && control->cancelled(control->context)) {
      status = reader_opds_fail(error, OPDS_CANCELLED, "cancelled during the TLS transfer");
      goto done;
    }
    if (!WinHttpReadData(handle, buffer, (DWORD)sizeof buffer, &read)) {
      status = win_fail(error, "reading the response body");
      goto done;
    }
    if (!read) break;
    if (body(user, buffer, (size_t)read)) {
      status = reader_opds_fail(error, OPDS_ABORTED, "transfer stopped by the caller");
      goto done;
    }
  }
done:
  if (handle) WinHttpCloseHandle(handle);
  if (connection) WinHttpCloseHandle(connection);
  if (session) WinHttpCloseHandle(session);
  free(target);
  free(host);
  free(accept);
  free(auth);
  free(line);
  return status;
}
#endif /* _WIN32 */
