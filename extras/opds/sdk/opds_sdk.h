/* SPDX-License-Identifier: MIT */
/* Optional glue between the OPDS client and the public EXReader SDK (exreader.h only). */
#ifndef OPDS_SDK_H
#define OPDS_SDK_H
#include "opds.h"
#ifdef __cplusplus
extern "C" {
#endif
/* opds_verify_fn: EPUB is opened through exr_publication_open, its first part loaded and
   its text read. Other types return OPDS_UNSUPPORTED ("cannot judge"), never OK. */
opds_status opds_sdk_verify(void *context, const char *path, const char *media_type,
                            char *detail, size_t detail_cap);
/* Opens a published book and writes "title" into out; OPDS_OK only for EPUB. */
opds_status opds_sdk_read_title(const char *path, char *title, size_t cap, size_t *parts, char *detail, size_t detail_cap);
#ifdef __cplusplus
}
#endif
#endif
