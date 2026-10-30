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
/* Explicit initial-custody transfer, not a sharing-mode retry at publication.
 * Prepare while original qualification pins are live. On success caller closes
 * original wr_context; new opaque custody keeps continuous deny-delete pins.
 * SHARE_WRITE admits directory-content writes, so every selected leaf and
 * identity is checked independently. Does not authorize migration/reopen. */
typedef struct lm_wp_custody lm_wp_custody;
int lm_wp_custody_prepare(wr_context *qualified,lm_wp_custody **out,wr_error *error);
int lm_wp_custody_check(lm_wp_custody *custody,wr_error *error);
void lm_wp_custody_close(lm_wp_custody *custody);
int lm_wp_publish_prepared(lm_wp_custody *custody,HANDLE source,
 const WCHAR *source_leaf,const WCHAR *public_leaf,const wr_identity *expected_source,
 const char expected_sha[65],lm_wp_result *result,wr_error *error);
#endif
