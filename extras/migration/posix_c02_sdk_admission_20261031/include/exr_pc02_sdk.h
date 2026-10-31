/* SPDX-License-Identifier: MIT */
#ifndef EXR_PC02_SDK_H
#define EXR_PC02_SDK_H
#include <exr_pc02.h>
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {size_t books;uint64_t original_bytes;} pc02_sdk_proof;
/* Desktop Linux/macOS hosts and tools share this fixed per-user authority.
   It comes from the account database, never a package or environment override.
   This function and shared open create nothing. */
int pc02_user_authority(char *,size_t);
int pc02_sdk_open_user(const char *library,pc02_lease **);
int pc02_sdk_enroll_user(const char *library,int create_library,pc02_sdk_proof *);
int pc02_sdk_recover_enrollment_user(const char *library,pc02_sdk_proof *);
/* Mobile callers supply only their fixed, OS-attested app-container scope and
   fixed relative authority. Explicit enrollment is separate from ordinary open. */
int pc02_sdk_enroll_in(pc02_scope *,const char *,const char *,int,pc02_sdk_proof *);
int pc02_sdk_recover_enrollment_in(pc02_scope *,const char *,const char *,pc02_sdk_proof *);
#ifdef __cplusplus
}
#endif
#endif
