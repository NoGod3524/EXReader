/* SPDX-License-Identifier: MIT
 * Explicit Windows record-format candidate; never grants recovery admission. */
#ifndef LM_RECOVERY_WIN32_RECORD_H
#define LM_RECOVERY_WIN32_RECORD_H
#include "lm.h"
#include "lm_recovery_win32_platform.h"
#define LM_WR_RECORD_MAX 4096u
typedef struct {
  unsigned ordinal,phase;
  char source[41],run[33],root[49],parent[49],target[49];
  char previous_id[49],previous_sha[65],payload_sha[65];
} lm_wr_record;
int lm_wr_record_encode(const lm_wr_record *record,lm_sb *bytes);
int lm_wr_record_decode(const void *bytes,size_t size,lm_wr_record *record);
int lm_wr_record_links(const lm_wr_record *next,const lm_wr_record *previous,
                      const wr_identity *previous_id);
int lm_wr_record_write(wr_context *context,const WCHAR *leaf,HANDLE target,
                       const lm_wr_record *record,HANDLE *retained,
                       wr_identity *observed,wr_error *error);
int lm_wr_record_read(wr_context *context,const WCHAR *leaf,HANDLE target,
                      lm_wr_record *record,HANDLE *retained,
                      wr_identity *observed,wr_error *error);
#endif
