/* SPDX-License-Identifier: MIT */
#ifndef LM_NEW_TARGET_H
#define LM_NEW_TARGET_H
#include "lm_mirror.h"
typedef struct lm_new_target lm_new_target;
/* Shared prefix view; no released-fence receipt grants transaction admission. */
typedef struct {
  unsigned records,registry_reserve; int lease;
  char root_id[33],parent_id[33],target_id[33],run[33],pack_sha[65];
  lm_mirror_file tail,lease_file,barrier,worker,font,mirror;
} ln_prefix;
int ln_route(lm_new_target **out,const char *exe,const char *command,const char *target,
             const char *pack,const char *font,int create,int recover,int partial,
             int preview,int break_lock,const char *inject,lm_cancel_fn cb,void *context,
             int *handled,lm_err *e);
void ln_owner_active(lm_new_target *n,int active);
int ln_validate(lm_new_target *n,ln_prefix *view,lm_err *e);
int ln_ledger(lm_new_target *n,const void *data,size_t size,lm_err *e);
int ln_scan_begin(lm_new_target *n,const char *target,const char *output,const char *nonce,const char *mode,const char *request,lm_mirror_file *request_id,int *fd,int *slot,lm_err *e);
void ln_scan_spawned(lm_new_target *n,int slot);
int ln_scan_finished(lm_new_target *n,int slot,lm_err *e);
void ln_report(lm_new_target *n,lm_sb *out);
/* Only fresh exec children with the exact inherited OFD lease/request qualify. */
int ln_child_enter(int fd,const char *request,const char *target,const char *pack,
                   const char *font,const char *expected_kind,lm_err *e);
int ln_child_pause(const char *phase,lm_err *e);
int ln_child_plan(const void *data,size_t size,lm_err *e);
void ln_child_report(lm_sb *out);
int ln_child_nonce_matches(const char *nonce);
int ln_child_worker_enter(const char *request,const char *target,const char *font,const char *mode,lm_err *e);
#endif
