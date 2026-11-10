/* SPDX-License-Identifier: MIT */
#ifndef EXR_LCP_INTERNAL_H
#define EXR_LCP_INTERNAL_H
#include "formats_internal.h"
#include <miniz.h>
/* No plaintext archive is produced. The context retains only the content key
   and the encryption directory; callers own the decrypted resource buffers. */
exr_status exr_lcp_open(mz_zip_archive *zip, const char *passphrase, void **out, exr_error *error);
void exr_lcp_free(void *context);
int exr_lcp_has(const void *context, const char *path);
exr_status exr_lcp_decode(void *context, const char *path, void **bytes, size_t *size,
                          const exr_resource_allocator *allocator, exr_error *error);
#endif
