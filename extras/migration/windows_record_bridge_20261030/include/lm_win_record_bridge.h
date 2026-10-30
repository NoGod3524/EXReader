/* SPDX-License-Identifier: MIT */
#ifndef LM_WIN_RECORD_BRIDGE_H
#define LM_WIN_RECORD_BRIDGE_H
#include <lm_win_publish.h>
typedef struct lm_rb lm_rb;
typedef struct {
 int write_attempted, flushed, verified;
 wr_identity identity;
 char sha[65];
} lm_rb_result;
/* Live-process bridge only. Caller retains exclusive admission, trusted target
 * handle and (after attach) custody through every call. No worker inheritance.
 * Creates named invalid 4096-byte reservations; failures NEVER delete evidence.
 * session must be an ordinal-zero codec-valid binding. Phase policy belongs to
 * the coordinator; neither a record nor successful write grants COMMIT/reopen. */
int lm_rb_prepare(wr_context *original,HANDLE target,
 const lm_wr_record *session,unsigned slots,lm_rb **out,wr_error *error);
int lm_rb_attach(lm_rb *,lm_wp_custody *,wr_error *);
int lm_rb_write_once(lm_rb *,unsigned slot,const lm_wr_record *,
 lm_rb_result *,wr_error *);
void lm_rb_close(lm_rb *);
#endif
