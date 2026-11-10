/* SPDX-License-Identifier: MIT */
/* Console acceptance for the OPDS engine parser + WinHTTP network layer against
   a real catalog. Usage: check_shell_opds <root-feed-url> <out-dir> [slow-url]
   Writes <out-dir>/opds-net.json; exit 0 only when every check passed. */
#include <winsock2.h>
#include "opds_net.h"
#include <exr/opds.h>
#include <direct.h>
#include <process.h>

static int failures;
static FILE *report;
/* Accept TCP connections, then deliberately send nothing. An event makes
   cleanup bounded and lets WinHTTP retry without a server-side close. */
static SOCKET slow_listener = INVALID_SOCKET;
static HANDLE slow_stop;
static volatile LONG slow_accepted;
static unsigned __stdcall slow_serve(void *unused) {
  SOCKET clients[16];
  int count = 0;
  (void)unused;
  while (WaitForSingleObject(slow_stop, 0) == WAIT_TIMEOUT) {
    fd_set reads;
    struct timeval tv = {0, 50000};
    FD_ZERO(&reads); FD_SET(slow_listener, &reads);
    if (select(0, &reads, NULL, NULL, &tv) > 0) {
      SOCKET c = accept(slow_listener, NULL, NULL);
      if (c != INVALID_SOCKET) {
        InterlockedIncrement(&slow_accepted);
        if (count < 16) clients[count++] = c; else closesocket(c);
      }
    }
  }
  for (int i = 0; i < count; i++) closesocket(clients[i]);
  return 0;
}
static void check(const char *name, int ok, const char *detail) {
  fprintf(report, "%s{\"check\":\"%s\",\"pass\":%s,\"detail\":\"%s\"}", "\n  ", name, ok ? "true" : "false", detail);
  fprintf(report, ",");
  if (!ok) failures++;
  fprintf(stderr, "%s %s %s\n", ok ? "PASS" : "FAIL", name, detail);
}
static void json_escape(const char *s, char *out, size_t size) {
  size_t o = 0;
  for (; *s && o + 8 < size; s++) {
    if (*s == '"' || *s == '\\') out[o++] = '\\';
    if ((unsigned char)*s < 32) { out[o++] = ' '; continue; }
    out[o++] = *s;
  }
  out[o] = 0;
}
static void timeout_check(void) {
  WSADATA wsa;
  struct sockaddr_in address = {0};
  int size = sizeof(address), ready = 0;
  HANDLE thread = NULL;
  char url[128], detail[512], safe[600];
  onet_options options = {0};
  onet_result result;
  onet_buffer body;
  DWORD started;
  int ok;
  if (WSAStartup(MAKEWORD(2, 2), &wsa)) { check("local_slow_server", 0, "WSAStartup"); return; }
  slow_listener = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
  address.sin_family = AF_INET;
  address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  slow_stop = CreateEventW(NULL, TRUE, FALSE, NULL);
  if (slow_listener != INVALID_SOCKET && slow_stop &&
      !bind(slow_listener, (struct sockaddr *)&address, sizeof(address)) &&
      !listen(slow_listener, 16) && !getsockname(slow_listener, (struct sockaddr *)&address, &size))
    thread = (HANDLE)_beginthreadex(NULL, 0, slow_serve, NULL, 0, NULL);
  if (thread) {
    ready = 1;
    snprintf(url, sizeof(url), "http://127.0.0.1:%u/slow.opds", (unsigned)ntohs(address.sin_port));
    options.resolve_ms = options.connect_ms = options.send_ms = options.receive_ms = 700;
    started = GetTickCount();
    ok = onet_fetch(url, &options, 0, &body, &result);
    snprintf(detail, sizeof(detail), "code=%s win_error=%lu http=%d elapsed_ms=%lu accepted=%ld message=%s",
             onet_name(result.code), result.win_error, result.http_status,
             (unsigned long)(GetTickCount() - started), (long)slow_accepted, result.message);
    json_escape(detail, safe, sizeof(safe));
    check("error_timeout_local_accept_no_response", !ok && result.code == ONET_TIMEOUT &&
          result.win_error == ERROR_WINHTTP_TIMEOUT && result.http_status == 0 &&
          slow_accepted > 0 && result.message[0] && GetTickCount() - started < 6000, safe);
    free(body.data);
    SetEvent(slow_stop);
    check("local_slow_server_join", WaitForSingleObject(thread, 2000) == WAIT_OBJECT_0, "server stopped");
    CloseHandle(thread);
  }
  if (!ready) check("local_slow_server", 0, "socket setup failed");
  if (slow_listener != INVALID_SOCKET) closesocket(slow_listener);
  if (slow_stop) CloseHandle(slow_stop);
  WSACleanup();
}
static void url_check(void) {
  char input[2048], output[2048];
  memset(input, 'a', sizeof(input));
  memcpy(input, "http://example.org/", 19);
  input[2046] = 0;
  onet_secure(input, output, sizeof(output));
  check("https_upgrade_exact_fit", strlen(output) == 2047 && !strncmp(output, "https://", 8), "2047 bytes plus terminator");
  input[2046] = 'a'; input[2047] = 0;
  onet_secure(input, output, sizeof(output));
  check("https_upgrade_overflow_rejected", !output[0], "overlong address becomes bad_url");
  onet_secure("http://127.0.0.1/feed", output, sizeof(output));
  check("loopback_http_preserved", !strcmp(output, "http://127.0.0.1/feed"), "local fixtures remain reachable");
}
static int load(const char *url, int use_cache, exr_opds_feed *feed, onet_result *r, const onet_options *o) {
  onet_buffer b;
  exr_error e = {0};
  if (!onet_fetch(url, o, use_cache, &b, r)) return 0;
  if (exr_opds_parse(b.data, b.size, url, feed, &e) != EXR_OK) {
    onet_fail(r, ONET_NETWORK, "%s", e.message);
    free(b.data);
    return 0;
  }
  free(b.data);
  return 1;
}
static const exr_opds_entry *first_download(const exr_opds_feed *f, int *index) {
  /* prefer the largest edition (the one with images) like the host does */
  const exr_opds_entry *best = NULL;
  for (size_t i = 0; i < f->entry_count; i++)
    if (f->entries[i].download_url && (!best || f->entries[i].size > best->size)) { best = &f->entries[i]; if (index) *index = (int)i; }
  return best;
}
int main(int argc, char **argv) {
  onet_options o = {0};
  onet_result r;
  exr_opds_feed root = {0}, page1 = {0}, page2 = {0}, detail = {0}, found = {0};
  char detail_text[4096], safe[4200], path[600];
  wchar_t wpath[600];
  int ok;
  SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
  if (argc < 3) return 2;
  _mkdir(argv[2]);
  snprintf(path, sizeof(path), "%s/opds-net.json", argv[2]);
  report = fopen(path, "wb");
  if (!report) return 2;
  fprintf(report, "{\"root\":\"%s\",\"checks\":[", argv[1]);
  url_check();
  timeout_check();
  if (!strcmp(argv[1], "--timeout-only")) goto finish;
  /* 1. root feed + a book list with >= 20 entries */
  ok = load(argv[1], 1, &root, &r, &o);
  snprintf(detail_text, sizeof(detail_text), "title=%s entries=%zu search_description=%s", ok && root.title ? root.title : "", root.entry_count,
           ok && root.search_description_url ? root.search_description_url : "none");
  json_escape(detail_text, safe, sizeof(safe));
  check("root_feed", ok && root.entry_count > 0, safe);
  {
    const char *list_url = NULL;
    char url[2048];
    for (size_t i = 0; ok && i < root.entry_count; i++)
      if (root.entries[i].detail_url && root.entries[i].title && !strcmp(root.entries[i].title, "Popular")) list_url = root.entries[i].detail_url;
    if (!list_url) { snprintf(url, sizeof(url), "https://www.gutenberg.org/ebooks/search.opds/?sort_order=downloads"); list_url = url; }
    ok = load(list_url, 1, &page1, &r, &o);
    snprintf(detail_text, sizeof(detail_text), "url=%s entries=%zu first=%s next=%s", list_url, page1.entry_count,
             page1.entry_count && page1.entries[0].title ? page1.entries[0].title : "", page1.next_url ? page1.next_url : "none");
    json_escape(detail_text, safe, sizeof(safe));
    check("list_ge_20", ok && page1.entry_count >= 20, safe);
  }
  /* 2. next page gives different entries */
  if (page1.next_url) {
    size_t same = 0;
    ok = load(page1.next_url, 1, &page2, &r, &o);
    for (size_t i = 0; ok && i < page2.entry_count; i++)
      for (size_t j = 0; j < page1.entry_count; j++)
        if (page2.entries[i].detail_url && page1.entries[j].detail_url && !strcmp(page2.entries[i].detail_url, page1.entries[j].detail_url)) same++;
    snprintf(detail_text, sizeof(detail_text), "page1=%zu page2=%zu overlap=%zu page2_first=%s", page1.entry_count, page2.entry_count, same,
             page2.entry_count && page2.entries[0].title ? page2.entries[0].title : "");
    json_escape(detail_text, safe, sizeof(safe));
    check("next_page_differs", ok && page2.entry_count > 0 && same == 0, safe);
  } else check("next_page_differs", 0, "no next link");
  /* 3. open the first book, download its best EPUB */
  if (page1.entry_count && page1.entries[0].detail_url) {
    ok = load(page1.entries[0].detail_url, 1, &detail, &r, &o);
    {
      int index = -1;
      const exr_opds_entry *e = ok ? first_download(&detail, &index) : NULL;
      snprintf(detail_text, sizeof(detail_text), "book=%s editions=%zu pick=%d format=%s size=%llu url=%s", page1.entries[0].title ? page1.entries[0].title : "",
               detail.entry_count, index, e ? e->format : "", e ? (unsigned long long)e->size : 0ULL, e ? e->download_url : "");
      json_escape(detail_text, safe, sizeof(safe));
      check("book_detail_has_download", e && !strcmp(e->format, "epub"), safe);
      if (e) {
        FILE *f;
        char head[4] = {0};
        char target[600];
        onet_result d;
        snprintf(target, sizeof(target), "%s/downloaded.epub", argv[2]);
        MultiByteToWideChar(CP_UTF8, 0, target, -1, wpath, 600);
        ok = onet_download(e->download_url, wpath, &o, &d);
        f = ok ? fopen(target, "rb") : NULL;
        if (f) { fread(head, 1, 2, f); fseek(f, 0, SEEK_END); }
        snprintf(detail_text, sizeof(detail_text), "bytes=%ld content_type=%s final=%s magic=%s", f ? ftell(f) : -1L, d.content_type, d.final_url, f && head[0] == 'P' && head[1] == 'K' ? "PK" : "bad");
        json_escape(detail_text, safe, sizeof(safe));
        check("download_epub", ok && f && head[0] == 'P' && head[1] == 'K', safe);
        if (f) fclose(f);
      }
    }
  } else check("book_detail_has_download", 0, "no detail link");
  /* 4. OpenSearch: description document -> template -> results */
  {
    char *tmpl = NULL, *url = NULL;
    exr_error e = {0};
    onet_buffer b;
    ok = 0;
    if (root.search_description_url && onet_fetch(root.search_description_url, &o, 1, &b, &r)) {
      ok = exr_opds_parse_search(b.data, b.size, root.search_description_url, &tmpl, &e) == EXR_OK;
      free(b.data);
    }
    if (ok) {
      char secure[2048];
      ok = exr_opds_search_url(tmpl, "dracula", &url, &e) == EXR_OK;
      if (ok) { onet_secure(url, secure, sizeof(secure)); ok = load(secure, 1, &found, &r, &o); snprintf(detail_text, sizeof(detail_text), "template=%s query=%s entries=%zu first=%s", tmpl, secure, found.entry_count, found.entry_count && found.entries[0].title ? found.entries[0].title : ""); }
    }
    if (!ok) snprintf(detail_text, sizeof(detail_text), "failed: %s %s", r.message, e.message);
    json_escape(detail_text, safe, sizeof(safe));
    check("opensearch_ge_1", ok && found.entry_count >= 1, safe);
    exr_free(tmpl); exr_free(url);
  }
  /* 5. errors: 404, timeout, plain http, cache */
  {
    onet_buffer b;
    ok = onet_fetch("https://www.gutenberg.org/ebooks/99999999.opds", &o, 0, &b, &r);
    snprintf(detail_text, sizeof(detail_text), "code=%s http=%d message=%s", onet_name(r.code), r.http_status, r.message);
    json_escape(detail_text, safe, sizeof(safe));
    check("error_404", !ok && r.code == ONET_NOT_FOUND && r.http_status == 404 && r.message[0], safe);
    ok = onet_fetch("http://example.com/opds", &o, 0, &b, &r);
    snprintf(detail_text, sizeof(detail_text), "code=%s message=%s", onet_name(r.code), r.message);
    json_escape(detail_text, safe, sizeof(safe));
    check("error_plain_http_rejected", !ok && r.code == ONET_NOT_HTTPS, safe);
    if (argc > 3) {
      onet_options slow = {0};
      DWORD t0 = GetTickCount();
      slow.receive_ms = 1500;
      ok = onet_fetch(argv[3], &slow, 0, &b, &r);
      snprintf(detail_text, sizeof(detail_text), "code=%s elapsed_ms=%lu message=%s", onet_name(r.code), (unsigned long)(GetTickCount() - t0), r.message);
      json_escape(detail_text, safe, sizeof(safe));
      check("error_timeout", !ok && r.code == ONET_TIMEOUT && GetTickCount() - t0 < 6000, safe);
    }
    {
      unsigned hits = onet_cache_hits;
      ok = onet_fetch(argv[1], &o, 1, &b, &r);
      snprintf(detail_text, sizeof(detail_text), "second fetch from_cache=%d hits=%u", r.from_cache, onet_cache_hits);
      json_escape(detail_text, safe, sizeof(safe));
      check("cache_hit_within_ttl", ok && r.from_cache && onet_cache_hits == hits + 1, safe);
      free(b.data);
      onet_cache_ttl_ms = 0;
      ok = onet_fetch(argv[1], &o, 1, &b, &r);
      snprintf(detail_text, sizeof(detail_text), "fetch with expired ttl from_cache=%d", r.from_cache);
      json_escape(detail_text, safe, sizeof(safe));
      check("cache_expires", ok && !r.from_cache, safe);
      free(b.data);
      check("cache_ttl_is_10_minutes", ONET_CACHE_MS == 600000, "ONET_CACHE_MS=600000");
    }
  }
finish:
  fprintf(report, "\n  {\"check\":\"end\",\"pass\":%s,\"detail\":\"failures=%d\"}\n]}\n", failures ? "false" : "true", failures);
  fclose(report);
  exr_opds_feed_free(&root); exr_opds_feed_free(&page1); exr_opds_feed_free(&page2); exr_opds_feed_free(&detail); exr_opds_feed_free(&found);
  return failures ? 1 : 0;
}
