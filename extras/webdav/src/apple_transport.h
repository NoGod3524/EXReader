/* SPDX-License-Identifier: MIT */
#ifndef EXR_APPLE_TRANSPORT_H
#define EXR_APPLE_TRANSPORT_H
#include "exr_webdav.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Private language bridge. All callbacks run synchronously on the caller;
   Foundation delegates retain only internal buffers, never this context. */
typedef struct {
  const char *url, *authorization, *method;
  uint64_t upload_bytes;
  unsigned timeout_ms;
  void *context;
  int (*cancelled)(void *);
  exr_webdav_status (*headers)(void *, int, const char *, const char *);
  exr_webdav_status (*receive)(void *, const void *, size_t);
  exr_webdav_status (*read)(void *, void *, size_t, size_t *);
} exr_apple_request;
exr_webdav_status exr_apple_http(const exr_apple_request *, exr_webdav_error *);
#ifdef __cplusplus
}
#endif
#endif
