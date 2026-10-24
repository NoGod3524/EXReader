/* SPDX-License-Identifier: MIT */
/* Scheme dispatch for the host transport slot: the frozen module performs exactly one
   GET per call and owns redirects, credentials, budgets and logging; this layer only
   chooses the socket implementation for http and the platform TLS one for https. */
#include "browser_internal.h"
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

int reader_opds_fail(opds_error *error, int code, const char *fmt, ...) {
  va_list ap;
  if (error) {
    memset(error, 0, sizeof *error);
    error->code = (opds_status)code;
    va_start(ap, fmt);
    vsnprintf(error->message, sizeof error->message, fmt, ap);
    va_end(ap);
  }
  return code;
}

static opds_status dispatch(void *context, const opds_request *request, unsigned timeout_ms,
                            const opds_control *control, opds_head_fn head, opds_body_fn body,
                            void *user, opds_error *error) {
  (void)context;
  if (!request || !request->url || !head || !body)
    return reader_opds_fail(error, OPDS_ARGUMENT, "request, head and body callbacks are required");
  if (request->method && strcmp(request->method, "GET"))
    return reader_opds_fail(error, OPDS_UNSUPPORTED, "only GET is supported");
  if ((request->accept && strpbrk(request->accept, "\r\n")) ||
      (request->authorization && strpbrk(request->authorization, "\r\n")))
    return reader_opds_fail(error, OPDS_ARGUMENT, "header values must not contain line breaks");
  if (!strncmp(request->url, "http://", 7))
    return opds_socket_transport()->fetch(NULL, request, timeout_ms, control, head, body, user, error);
  if (!strncmp(request->url, "https://", 8)) {
#if READER_OPDS_TLS
    return reader_opds_platform_tls_fetch(request, timeout_ms, control, head, body, user, error);
#else
    return reader_opds_fail(error, OPDS_NEEDS_HOST, "this build carries no TLS transport");
#endif
  }
  return reader_opds_fail(error, OPDS_NEEDS_HOST, "only plain http and https URLs are supported");
}

static const opds_transport default_transport = {dispatch, NULL};

const opds_transport *reader_opds_default_transport(void) { return &default_transport; }

int reader_opds_tls_available(void) { return READER_OPDS_TLS ? 1 : 0; }
