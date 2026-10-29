/* SPDX-License-Identifier: MIT */
#ifndef LM_RECOVERY_H
#define LM_RECOVERY_H
#include "lm_mirror.h"
typedef struct lm_recovery lm_recovery;
#define LM_RECOVERY_LIMIT (64u*1024u*1024u)
int lr_gate(lm_recovery **out,const char *executable,const char *command,
            const char *target,const char *pack,const char *font,int break_lock,
            lm_cancel_fn cancelled,void *context,lm_err *e);
int lr_prepare(lm_recovery *r,const lm_pack *pack,int recover,lm_err *e);
int lr_opening(lm_recovery *r,lm_err *e);
void lr_owner_attempted(lm_recovery *r);
void lr_owner_started(lm_recovery *r);
int lr_compare_restore(lm_recovery *r,exr_library *owner,lm_err *e);
int lr_publish(lm_recovery *r,const void *ledger,size_t size,lm_err *e);
int lr_ack(lm_recovery *r,exr_status actual_commit_status,lm_err *e);
void lr_rollback(lm_recovery *r,exr_status actual_rollback_status);
void lr_owner_closed(lm_recovery *r);
int lr_complete(lm_recovery *r,lm_err *e);
int lr_read_view(lm_recovery *r,char **view,lm_err *e);
int lr_snapshot(lm_recovery *r,const char *path,int hash,uint64_t max,
                lm_mirror_file *f,char **bytes,size_t *size,lm_err *e);
int lr_read(lm_recovery *r,const char *path,char **bytes,size_t *size,size_t max,lm_err *e);
int lr_write_new(lm_recovery *r,const char *path,const void *data,size_t size,lm_err *e);
int lr_pause(lm_recovery *r,const char *phase,lm_err *e);
void lr_report(lm_recovery *r,lm_sb *json);
const char *lr_original_target(lm_recovery *r);
int lr_open_attempted(lm_recovery *r);
#endif
