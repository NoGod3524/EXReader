/* SPDX-License-Identifier: MIT
 * Additive Windows native adapter. Not linked by any production target yet. */
#ifndef LM_RECOVERY_WIN32_PLATFORM_H
#define LM_RECOVERY_WIN32_PLATFORM_H
#ifndef _WIN32
#error Windows-only qualification adapter
#endif
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0A00
#endif
#include <windows.h>
#include <stdint.h>
#include <stddef.h>
#define WR_PATH 4096
#define WR_PINS 64
#define WR_WRITE_TOTAL (64ull*1024*1024)
#define WR_RECORD_MAX (1024u*1024u)
typedef struct { ULONGLONG volume; unsigned char file[16]; DWORD attributes,links; ULONGLONG size; } wr_identity;
typedef struct { DWORD native; const char *reason; DWORD cleanup_native,wait_result; LONG ntstatus; ULONG_PTR io_information; int cleanup_unconfirmed; int rename_attempted; LONG rename_ntstatus,rename_io_status; ULONG_PTR rename_information; } wr_error;
typedef struct {
 HANDLE pins[WR_PINS];wr_identity identities[WR_PINS];unsigned count;
 WCHAR paths[WR_PINS][WR_PATH],path[WR_PATH];
 HANDLE directory;wr_identity root;
 uint64_t written;unsigned entries;
 unsigned char user[SECURITY_MAX_SID_SIZE],system[SECURITY_MAX_SID_SIZE],admins[SECURITY_MAX_SID_SIZE];
 BYTE acl[512];SECURITY_DESCRIPTOR descriptor;SECURITY_ATTRIBUTES security;
} wr_context;
typedef struct { HANDLE process,thread;DWORD pid;int cleanup_unconfirmed; } wr_process;
int wr_cleanup_uncertain(void);
int wr_utf8(const char *input,WCHAR out[WR_PATH],wr_error *e);
int wr_identity_get(HANDLE h,int directory,wr_identity *id,wr_error *e);
int wr_identity_equal(const wr_identity *a,const wr_identity *b);
void wr_identity_text(const wr_identity *id,char out[49]);
int wr_prepare(wr_context *c,const WCHAR *path,int create,wr_error *e);
HANDLE wr_directory_new(wr_context *c,const WCHAR *leaf,wr_identity *id,wr_error *e);
int wr_recheck(wr_context *c,wr_error *e);
int wr_private_acl(HANDLE h,int directory,wr_context *c,wr_error *e);
int wr_data_acl(HANDLE h,wr_context *c,wr_error *e);
int wr_join(wr_context *c,const WCHAR *leaf,WCHAR out[WR_PATH],wr_error *e);
HANDLE wr_open(wr_context *c,const WCHAR *leaf,DWORD access,DWORD sharing,int create,wr_error *e);
int wr_write_new(wr_context *c,const WCHAR *leaf,const void *bytes,size_t size,int sync,HANDLE *retained,wr_error *e);
int wr_read(HANDLE h,void **bytes,size_t *size,size_t maximum,wr_error *e);
int wr_flush(HANDLE h,wr_error *e);
int wr_rename_new(wr_context *c,HANDLE source,const WCHAR *leaf,wr_error *e);
HANDLE wr_job(wr_error *e);
int wr_spawn(HANDLE job,const WCHAR *exe,WCHAR *command,HANDLE *inherit,size_t count,HANDLE input,HANDLE output,int fail_before_resume,wr_process *p,wr_error *e);
int wr_wait(wr_process *p,DWORD milliseconds,DWORD *status,wr_error *e);
int wr_terminate(wr_process *p,wr_error *e);
void wr_process_close(wr_process *p);
void wr_close(wr_context *c);
#endif
