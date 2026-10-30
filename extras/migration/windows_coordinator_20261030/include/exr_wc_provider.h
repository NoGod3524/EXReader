/* SPDX-License-Identifier: MIT
 * Private provider interface (installed under include/.../private). */
#ifndef EXR_WC_PROVIDER_H
#define EXR_WC_PROVIDER_H
#include "exr_wc.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef enum { WC_STEP_OK = 0, WC_STEP_FAILED = 1, WC_STEP_UNCERTAIN = 2 } wc_step;
typedef enum { WC_PUB_NO = 0, WC_PUB_YES = 1, WC_PUB_UNKNOWN = 2 } wc_pub;

/* FAILED = no effect remains. UNCERTAIN = effect may remain. A NULL function is
   a missing provider part and keeps the run pending. */
typedef struct wc_provider {
  uint32_t abi;
  const char *identity_sha;   /* must equal binding->provider */
  void *context;
  wc_step (*admit)(void *, const wc_binding *, char lease[EXR_WC_ID_BYTES]);          /* C01 */
  wc_step (*snapshot)(void *, wc_record *rows, size_t capacity, size_t *count);
  wc_step (*import)(void *, const wc_binding *, const wc_record *rows, size_t count,
                    char staged[EXR_WC_ID_BYTES]);
  wc_step (*verify)(void *, const char staged[EXR_WC_ID_BYTES], const wc_record *rows, size_t count);
  wc_step (*publish)(void *, const char staged[EXR_WC_ID_BYTES], wc_pub *published);  /* publisher */
  wc_step (*recover)(void *, const char staged[EXR_WC_ID_BYTES], wc_pub *published);  /* publisher/engine */
  wc_step (*discard)(void *, const char staged[EXR_WC_ID_BYTES]);
  wc_step (*release)(void *, const char lease[EXR_WC_ID_BYTES]);                      /* C01 */
} wc_provider;

/* Reference filesystem provider: real logical snapshot of a source directory
   tree, exclusive staging copy, content re-verification and conservative discard.
   admit/publish/recover/release stay NULL until the owning native components
   are attached with wc_fs_attach(); until then the run is pending. */
typedef struct wc_fs wc_fs;
int wc_fs_open(const char *source_dir, const char *destination_parent, const char *identity_sha,
               wc_fs **out, wc_provider *provider);
void wc_fs_attach(wc_provider *provider,
                  wc_step (*admit)(void *, const wc_binding *, char *),
                  wc_step (*publish)(void *, const char *, wc_pub *),
                  wc_step (*recover)(void *, const char *, wc_pub *),
                  wc_step (*release)(void *, const char *), void *context);
const char *wc_fs_staging_path(const wc_fs *fs);
void wc_fs_close(wc_fs *fs);
#ifdef __cplusplus
}
#endif
#endif
