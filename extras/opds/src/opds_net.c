/* SPDX-License-Identifier: MIT */
/* Reference transport: plain HTTP/1.1 over sockets. One request per connection, no
   redirect following, no TLS (https is NEEDS_HOST), identity encoding only.
   Timeouts are inactivity timeouts: each connect/send/receive wait may take at most
   timeout_ms; cancellation is polled every <=50 ms while waiting. */
#include "opds_internal.h"
#include <ctype.h>
#include <errno.h>

#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
typedef SOCKET sock_t;
#define BAD_SOCK INVALID_SOCKET
#define CLOSE_SOCK closesocket
static int would_block(void) { int e = WSAGetLastError(); return e == WSAEWOULDBLOCK || e == WSAEINPROGRESS; }
static int interrupted(void) { return WSAGetLastError() == WSAEINTR; }
static void set_nonblock(sock_t s) { u_long on = 1; ioctlsocket(s, FIONBIO, &on); }
static unsigned long long now_ms(void) { return (unsigned long long)GetTickCount64(); }
#else
#include <fcntl.h>
#include <netdb.h>
#include <poll.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>
typedef int sock_t;
#ifndef MSG_NOSIGNAL
#define MSG_NOSIGNAL 0 /* e.g. macOS: SIGPIPE is the host's to ignore */
#endif
#define BAD_SOCK (-1)
#define CLOSE_SOCK close
static int would_block(void) { return errno == EINPROGRESS || errno == EWOULDBLOCK || errno == EAGAIN; }
static int interrupted(void) { return errno == EINTR; }
static void set_nonblock(sock_t s) { int f = fcntl(s, F_GETFL, 0); fcntl(s, F_SETFL, f | O_NONBLOCK); }
static unsigned long long now_ms(void) {
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return (unsigned long long)t.tv_sec * 1000ull + (unsigned long long)t.tv_nsec / 1000000ull;
}
#endif

/* 1 ready, 0 timeout, -1 cancelled, -2 error */
static int wait_sock(sock_t s, int want_write, unsigned timeout_ms, const opds_control *ctl) {
  unsigned long long deadline = now_ms() + timeout_ms;
  for (;;) {
    unsigned long long now = now_ms();
    unsigned slice;
    int r;
    if (ctl && ctl->cancelled && ctl->cancelled(ctl->context)) return -1;
    if (now >= deadline) return 0;
    slice = (unsigned)(deadline - now < 50 ? deadline - now : 50);
#ifdef _WIN32
    {
      fd_set set, ex; struct timeval tv;
      FD_ZERO(&set); FD_SET(s, &set); FD_ZERO(&ex); FD_SET(s, &ex); /* failed connects arrive as exceptions */
      tv.tv_sec = 0; tv.tv_usec = (long)slice * 1000;
      r = select(0, want_write ? NULL : &set, want_write ? &set : NULL, want_write ? &ex : NULL, &tv);
    }
#else
    {
      struct pollfd p;
      p.fd = s; p.events = (short)(want_write ? POLLOUT : POLLIN); p.revents = 0;
      r = poll(&p, 1, (int)slice);
      if (r > 0 && (p.revents & (POLLERR | POLLNVAL)) && !(p.revents & (POLLIN | POLLOUT))) return -2;
    }
#endif
    if (r > 0) return 1;
    if (r < 0 && !interrupted()) return -2;
  }
}

static opds_status wait_status(int w, opds_error *e, const char *what) {
  if (w == 1) return OPDS_OK;
  if (w == 0) return opds_fail(e, OPDS_TIMEOUT, "timed out waiting for %s", what);
  if (w == -1) return opds_fail(e, OPDS_CANCELLED, "cancelled while waiting for %s", what);
  return opds_fail(e, OPDS_IO, "socket error while waiting for %s", what);
}

typedef struct { char host[256]; char port[8]; char hostport[270]; char path[OPDS_URL_MAX]; } target;

static opds_status parse_target(const char *url, target *t, opds_error *e) {
  const char *p = url, *auth, *end, *at = NULL, *colon = NULL;
  size_t hl;
  if (!strncmp(url, "https://", 8)) return opds_fail(e, OPDS_NEEDS_HOST, "https needs a host-supplied TLS transport");
  if (strncmp(url, "http://", 7)) return opds_fail(e, OPDS_UNSUPPORTED, "only http:// URLs are handled by the socket transport");
  auth = p + 7; end = auth;
  while (*end && *end != '/' && *end != '?') end++;
  for (const char *c = auth; c < end; c++) if (*c == '@') at = c;
  if (at) auth = at + 1;
  if (auth < end && *auth == '[') {
    const char *rb = (const char *)memchr(auth, ']', (size_t)(end - auth));
    if (!rb) return opds_fail(e, OPDS_ARGUMENT, "bad IPv6 host");
    if (rb + 1 < end && rb[1] == ':') colon = rb + 1;
    hl = (size_t)(rb - auth) - 1;
    if (hl == 0 || hl >= sizeof t->host) return opds_fail(e, OPDS_ARGUMENT, "bad host");
    memcpy(t->host, auth + 1, hl); t->host[hl] = 0;
  } else {
    for (const char *c = end; c > auth; c--) if (c[-1] == ':') { colon = c - 1; break; }
    hl = (size_t)((colon ? colon : end) - auth);
    if (hl == 0 || hl >= sizeof t->host) return opds_fail(e, OPDS_ARGUMENT, "bad host");
    memcpy(t->host, auth, hl); t->host[hl] = 0;
  }
  if (colon) {
    size_t pl = (size_t)(end - colon - 1);
    if (pl == 0 || pl >= sizeof t->port) return opds_fail(e, OPDS_ARGUMENT, "bad port");
    for (size_t i = 0; i < pl; i++) if (!isdigit((unsigned char)colon[1 + i])) return opds_fail(e, OPDS_ARGUMENT, "bad port");
    memcpy(t->port, colon + 1, pl); t->port[pl] = 0;
  } else strcpy(t->port, "80");
  if (strchr(t->host, ':')) snprintf(t->hostport, sizeof t->hostport, "[%s]%s%s", t->host, strcmp(t->port, "80") ? ":" : "", strcmp(t->port, "80") ? t->port : "");
  else snprintf(t->hostport, sizeof t->hostport, "%s%s%s", t->host, strcmp(t->port, "80") ? ":" : "", strcmp(t->port, "80") ? t->port : "");
  if (strlen(end) == 0) strcpy(t->path, "/");
  else if (*end == '?') snprintf(t->path, sizeof t->path, "/%s", end);
  else if (strlen(end) >= sizeof t->path) return opds_fail(e, OPDS_LIMIT, "URL too long");
  else strcpy(t->path, end);
  for (const char *c = t->path; *c; c++) if ((unsigned char)*c <= 0x20) return opds_fail(e, OPDS_ARGUMENT, "URL contains unescaped whitespace");
  return OPDS_OK;
}

static opds_status connect_to(const target *t, unsigned timeout_ms, const opds_control *ctl, sock_t *out, opds_error *e) {
  struct addrinfo hints, *res = NULL, *ai;
  opds_status st = OPDS_IO;
  memset(&hints, 0, sizeof hints);
  hints.ai_family = AF_UNSPEC; hints.ai_socktype = SOCK_STREAM;
  if (getaddrinfo(t->host, t->port, &hints, &res) != 0 || !res) return opds_fail(e, OPDS_IO, "cannot resolve host");
  for (ai = res; ai; ai = ai->ai_next) {
    sock_t s = socket(ai->ai_family, ai->ai_socktype, ai->ai_protocol);
    int r;
    if (s == BAD_SOCK) continue;
    set_nonblock(s);
    r = connect(s, ai->ai_addr, (int)ai->ai_addrlen);
    if (r != 0 && !would_block()) { CLOSE_SOCK(s); continue; }
    if (r != 0) {
      int w = wait_sock(s, 1, timeout_ms, ctl);
      if (w != 1) { CLOSE_SOCK(s); st = wait_status(w, e, "connection"); if (w == -1 || w == 0) { freeaddrinfo(res); return st; } continue; }
      {
        int soerr = 0;
#ifdef _WIN32
        int len = (int)sizeof soerr;
        getsockopt(s, SOL_SOCKET, SO_ERROR, (char *)&soerr, &len);
#else
        socklen_t len = sizeof soerr;
        getsockopt(s, SOL_SOCKET, SO_ERROR, &soerr, &len);
#endif
        if (soerr) { CLOSE_SOCK(s); continue; }
      }
    }
    freeaddrinfo(res);
    *out = s;
    return OPDS_OK;
  }
  freeaddrinfo(res);
  return opds_fail(e, st, "connection failed");
}

static opds_status send_all(sock_t s, const char *d, size_t n, unsigned timeout_ms, const opds_control *ctl, opds_error *e) {
  while (n) {
    int w = wait_sock(s, 1, timeout_ms, ctl), k;
    if (w != 1) return wait_status(w, e, "send");
#ifdef _WIN32
    k = send(s, d, (int)(n > 65536 ? 65536 : n), 0);
#else
    k = (int)send(s, d, n > 65536 ? 65536 : n, MSG_NOSIGNAL);
#endif
    if (k < 0) { if (would_block() || interrupted()) continue; return opds_fail(e, OPDS_IO, "send failed"); }
    d += k; n -= (size_t)k;
  }
  return OPDS_OK;
}

/* returns >0 bytes, 0 eof, <0 negated status code-ish via *st */
static long recv_some(sock_t s, void *buf, size_t n, unsigned timeout_ms, const opds_control *ctl, opds_status *st, opds_error *e) {
  for (;;) {
    int w = wait_sock(s, 0, timeout_ms, ctl), k;
    if (w != 1) { *st = wait_status(w, e, "response data"); return -1; }
#ifdef _WIN32
    k = recv(s, (char *)buf, (int)n, 0);
#else
    k = (int)recv(s, buf, n, 0);
#endif
    if (k < 0) { if (would_block() || interrupted()) continue; *st = opds_fail(e, OPDS_IO, "receive failed"); return -1; }
    return k;
  }
}

static int hdr_is(const char *line, size_t n, const char *name) {
  size_t l = strlen(name);
  return n > l && line[l] == ':' && opds_ascii_iprefix(line, name);
}

typedef struct { opds_head_fn head; opds_body_fn body; void *user; } sinks;

static opds_status deliver(const sinks *k, const void *d, size_t n, opds_error *e) {
  if (n && k->body(k->user, d, n)) return opds_fail(e, OPDS_ABORTED, "transfer stopped by the caller");
  return OPDS_OK;
}

static opds_status fetch(void *context, const opds_request *rq, unsigned timeout_ms, const opds_control *ctl,
                         opds_head_fn head, opds_body_fn body, void *user, opds_error *e) {
  target t;
  sock_t s = BAD_SOCK;
  opds_status st;
  char req[OPDS_URL_MAX + 1400];
  char hbuf[32768];
  size_t hlen = 0, hend = 0;
  opds_response r;
  char loc[OPDS_URL_MAX], ctype[256], www[256];
  int64_t clen = -1;
  int chunked = 0, wsa = 0;
  sinks k;
  (void)context;
  if (!rq || !rq->url || !head || !body) return opds_fail(e, OPDS_ARGUMENT, "request, head and body callbacks are required");
  if (rq->method && strcmp(rq->method, "GET")) return opds_fail(e, OPDS_UNSUPPORTED, "only GET is supported");
  if ((rq->accept && strpbrk(rq->accept, "\r\n")) || (rq->authorization && strpbrk(rq->authorization, "\r\n")))
    return opds_fail(e, OPDS_ARGUMENT, "header values must not contain line breaks");
  if ((st = parse_target(rq->url, &t, e)) != OPDS_OK) return st;
  if (ctl && ctl->cancelled && ctl->cancelled(ctl->context)) return opds_fail(e, OPDS_CANCELLED, "cancelled before connecting");
#ifdef _WIN32
  { WSADATA d; if (WSAStartup(MAKEWORD(2, 2), &d)) return opds_fail(e, OPDS_IO, "Winsock unavailable"); wsa = 1; }
#endif
  k.head = head; k.body = body; k.user = user;
  if ((st = connect_to(&t, timeout_ms, ctl, &s, e)) != OPDS_OK) goto done;
  snprintf(req, sizeof req, "GET %s HTTP/1.1\r\nHost: %s\r\nUser-Agent: opds-client/" OPDS_MODULE_VERSION "\r\nAccept: %s\r\nAccept-Encoding: identity\r\nConnection: close\r\n%s%s%s\r\n",
           t.path, t.hostport, rq->accept ? rq->accept : "*/*",
           rq->authorization ? "Authorization: " : "", rq->authorization ? rq->authorization : "", rq->authorization ? "\r\n" : "");
  if ((st = send_all(s, req, strlen(req), timeout_ms, ctl, e)) != OPDS_OK) goto done;
  for (;;) {
    long n;
    for (size_t i = 3; i < hlen; i++) if (!memcmp(hbuf + i - 3, "\r\n\r\n", 4)) { hend = i + 1; break; }
    if (hend) break;
    if (hlen >= sizeof hbuf) { st = opds_fail(e, OPDS_LIMIT, "response header too large"); goto done; }
    n = recv_some(s, hbuf + hlen, sizeof hbuf - hlen, timeout_ms, ctl, &st, e);
    if (n < 0) goto done;
    if (n == 0) { st = opds_fail(e, OPDS_IO, "connection closed before the response header ended"); goto done; }
    hlen += (size_t)n;
  }
  memset(&r, 0, sizeof r);
  loc[0] = ctype[0] = www[0] = 0;
  {
    size_t pos = 0;
    int first = 1;
    while (pos < hend - 2) {
      char *nl = (char *)memchr(hbuf + pos, '\n', hend - pos);
      size_t ll = nl ? (size_t)(nl - (hbuf + pos)) : hend - pos;
      const char *line = hbuf + pos;
      size_t trimmed = ll;
      if (trimmed && line[trimmed - 1] == '\r') trimmed--;
      if (first) {
        int code = 0;
        if (trimmed < 12 || strncmp(line, "HTTP/1.", 7) || line[8] != ' ') { st = opds_fail(e, OPDS_FORMAT, "malformed HTTP status line"); goto done; }
        for (int q = 9; q < 12; q++) { if (!isdigit((unsigned char)line[q])) { st = opds_fail(e, OPDS_FORMAT, "malformed HTTP status line"); goto done; } code = code * 10 + (line[q] - '0'); }
        r.status = code;
        first = 0;
      } else if (trimmed) {
        const char *v;
        size_t vl;
        const char *colon = (const char *)memchr(line, ':', trimmed);
        if (!colon) { st = opds_fail(e, OPDS_FORMAT, "malformed HTTP header"); goto done; }
        v = colon + 1;
        while (v < line + trimmed && (*v == ' ' || *v == '\t')) v++;
        vl = (size_t)(line + trimmed - v);
        if (hdr_is(line, trimmed, "Location")) { if (vl >= sizeof loc) { st = opds_fail(e, OPDS_LIMIT, "Location too long"); goto done; } memcpy(loc, v, vl); loc[vl] = 0; }
        else if (hdr_is(line, trimmed, "Content-Type")) { size_t c = vl < sizeof ctype - 1 ? vl : sizeof ctype - 1; memcpy(ctype, v, c); ctype[c] = 0; }
        else if (hdr_is(line, trimmed, "WWW-Authenticate")) { if (!www[0]) { size_t c = vl < sizeof www - 1 ? vl : sizeof www - 1; memcpy(www, v, c); www[c] = 0; } }
        else if (hdr_is(line, trimmed, "Content-Length")) {
          int64_t acc = 0;
          if (!vl) { st = opds_fail(e, OPDS_FORMAT, "bad Content-Length"); goto done; }
          for (size_t q = 0; q < vl; q++) {
            if (!isdigit((unsigned char)v[q])) { st = opds_fail(e, OPDS_FORMAT, "bad Content-Length"); goto done; }
            if (acc > (INT64_MAX - 9) / 10) { st = opds_fail(e, OPDS_LIMIT, "Content-Length too large"); goto done; }
            acc = acc * 10 + (v[q] - '0');
          }
          clen = acc;
        } else if (hdr_is(line, trimmed, "Transfer-Encoding")) {
          if (vl >= 7 && opds_ascii_iprefix(v, "chunked")) chunked = 1;
          else if (vl) { st = opds_fail(e, OPDS_UNSUPPORTED, "unsupported Transfer-Encoding"); goto done; }
        } else if (hdr_is(line, trimmed, "Content-Encoding")) {
          if (vl && !opds_ascii_iprefix(v, "identity")) { st = opds_fail(e, OPDS_UNSUPPORTED, "compressed responses are not supported"); goto done; }
        }
      }
      pos += ll + 1;
    }
  }
  r.location = loc[0] ? loc : NULL; r.content_type = ctype[0] ? ctype : NULL;
  r.www_authenticate = www[0] ? www : NULL; r.content_length = chunked ? -1 : clen;
  if (head(user, &r)) { st = OPDS_OK; goto done; }
  if (r.status == 204 || r.status == 304 || (r.status >= 100 && r.status < 200)) { st = OPDS_OK; goto done; }
  {
    /* body */
    unsigned char buf[16384];
    const unsigned char *lead = (const unsigned char *)hbuf + hend;
    size_t lead_n = hlen - hend;
    int64_t got = 0;
    if (!chunked) {
      if (lead_n && clen >= 0 && (int64_t)lead_n > clen) lead_n = (size_t)clen;
      if ((st = deliver(&k, lead, lead_n, e)) != OPDS_OK) goto done;
      got = (int64_t)lead_n;
      while (clen < 0 || got < clen) {
        size_t want = sizeof buf;
        long n;
        if (clen >= 0 && (int64_t)want > clen - got) want = (size_t)(clen - got);
        n = recv_some(s, buf, want, timeout_ms, ctl, &st, e);
        if (n < 0) goto done;
        if (n == 0) { if (clen >= 0) { st = opds_fail(e, OPDS_IO, "response body truncated"); goto done; } break; }
        if ((st = deliver(&k, buf, (size_t)n, e)) != OPDS_OK) goto done;
        got += n;
      }
    } else {
      /* chunked: state machine over a byte stream made of lead + socket */
      enum { SIZE, DATA, CRLF, DONE } state = SIZE;
      char line[40];
      size_t ll = 0;
      unsigned long long left = 0;
      size_t li = 0;
      const unsigned char *src = lead;
      size_t srcn = lead_n;
      for (;;) {
        if (state == DONE) break;
        if (li >= srcn) {
          long n = recv_some(s, buf, sizeof buf, timeout_ms, ctl, &st, e);
          if (n < 0) goto done;
          if (n == 0) { st = opds_fail(e, OPDS_IO, "chunked body truncated"); goto done; }
          src = buf; srcn = (size_t)n; li = 0;
        }
        if (state == SIZE) {
          unsigned char ch = src[li++];
          if (ch == '\n') {
            char *end;
            line[ll] = 0;
            for (size_t q = 0; q < ll; q++) if (line[q] == ';' || line[q] == '\r') { line[q] = 0; break; }
            if (!line[0]) { st = opds_fail(e, OPDS_FORMAT, "bad chunk size"); goto done; }
            left = strtoull(line, &end, 16);
            if (*end) { st = opds_fail(e, OPDS_FORMAT, "bad chunk size"); goto done; }
            ll = 0;
            state = left ? DATA : DONE;
          } else if (ll + 1 < sizeof line) line[ll++] = (char)ch;
          else { st = opds_fail(e, OPDS_FORMAT, "chunk size line too long"); goto done; }
        } else if (state == DATA) {
          size_t take = srcn - li;
          if ((unsigned long long)take > left) take = (size_t)left;
          if ((st = deliver(&k, src + li, take, e)) != OPDS_OK) goto done;
          li += take; left -= take;
          if (!left) state = CRLF;
        } else { /* CRLF after data */
          if (src[li++] == '\n') state = SIZE;
        }
      }
    }
  }
  st = OPDS_OK;
done:
  if (s != BAD_SOCK) CLOSE_SOCK(s);
#ifdef _WIN32
  if (wsa) WSACleanup();
#else
  (void)wsa;
#endif
  return st;
}

static const opds_transport socket_transport = {fetch, NULL};
const opds_transport *opds_socket_transport(void) { return &socket_transport; }
