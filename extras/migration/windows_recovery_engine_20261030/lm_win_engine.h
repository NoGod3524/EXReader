/* SPDX-License-Identifier: MIT */
#ifndef LM_WIN_ENGINE_H
#define LM_WIN_ENGINE_H
#include "lm_recovery_win32_platform.h"
typedef enum { LM_WE_REFUSED=0,LM_WE_OBSERVED=1,LM_WE_UNCERTAIN=2 } lm_we_state;
typedef struct {
 lm_we_state state;
 DWORD worker_exit;
 int worker_terminal,descendants_terminal;
 char source[41],nonce[33],root[49],parent[49],target[49];
 char worker_sha[65],target_sha[65];
 unsigned long long bytes;
} lm_we_result;
/* Caller retains root and target custody for the entire call. No path, SDK,
 * migration admission, COMMIT or reopen authorization is returned.
 * Worker path must name the actual installed image; the image is held with
 * write/delete sharing denied until the job and all descendants are terminal.
 * Output leaf is exclusive-created and ALWAYS retained, including failures. */
int lm_we_observe(wr_context *root,HANDLE target,const WCHAR *worker_path,
 const char expected_worker_sha[65],const char nonce[33],
 const WCHAR *output_leaf,DWORD timeout_ms,lm_we_result *result,wr_error *error);
#endif
