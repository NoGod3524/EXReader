/* SPDX-License-Identifier: MIT */
#ifndef READER_OPDS_BROWSER_INTERNAL_H
#define READER_OPDS_BROWSER_INTERNAL_H
#include "reader_opds_browser.h"

/* Set by the build: 1 when an https transport is compiled in. */
#ifndef READER_OPDS_TLS
#define READER_OPDS_TLS 0
#endif

int reader_opds_fail(opds_error *error, int code, const char *fmt, ...);

/* Implemented once per platform: WinHTTP on Windows, libcurl elsewhere.
   Performs exactly one request, never follows a redirect, uses the system trust
   store and the request's authorization value only. */
#if READER_OPDS_TLS
opds_status reader_opds_platform_tls_fetch(const opds_request *request, unsigned timeout_ms,
                                           const opds_control *control, opds_head_fn head,
                                           opds_body_fn body, void *user, opds_error *error);
#endif
#endif
