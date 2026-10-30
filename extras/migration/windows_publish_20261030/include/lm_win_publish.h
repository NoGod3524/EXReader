/* SPDX-License-Identifier: MIT */
#ifndef LM_WIN_PUBLISH_H
#define LM_WIN_PUBLISH_H
#include <lm_recovery_win32_record.h>
typedef struct {
  int rename_attempted, published, verified;
  LONG ntstatus, io_status;
  wr_identity identity;
  char sha[65];
} lm_wp_result;
/* Trusted source: wr_write_new retained GR|GW|DELETE, share-read-only handle.
 * Both caller-owned handle and context remain live. Never closes/removes them.
 * False after a native success is uncertain, NOT rollback or permission to retry.
 * This primitive supplies neither migration admission nor commit acknowledgement. */
int lm_wp_publish(wr_context *private_root, HANDLE source,
                  const WCHAR *source_leaf, const WCHAR *public_leaf,
                  const wr_identity *expected_source, const char expected_sha[65],
                  lm_wp_result *result, wr_error *error);
#endif
