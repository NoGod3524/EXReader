/* SPDX-License-Identifier: MIT */
#ifndef EXR_PC02_H
#define EXR_PC02_H
#include <stdint.h>
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct pc02_scope pc02_scope;
typedef struct pc02_lease pc02_lease;
typedef struct pc02_cap pc02_cap;
typedef struct {uint64_t device,inode;} pc02_identity;
typedef struct {uint64_t generation;char seal[65];pc02_identity target;} pc02_grant;
typedef struct {uint64_t generation;char seal[65],manifest[65],input[65];} pc02_pending_record;
enum {PC02_SHARED=1,PC02_OWNER=2,PC02_RECOVER=3};
enum {PC02_ENROLL_INTENT=1001,PC02_ENROLL_STATE=1002,PC02_ENROLL_BOUND=1003,
 PC02_PENDING_WRITTEN=1101,PC02_PENDING_DURABLE=1102,
 PC02_CLEAN_WRITTEN=1201,PC02_CLEAN_DURABLE=1202,
 PC02_BINDING_WRITTEN=1203,PC02_BINDING_PUBLISHED=1204,PC02_BINDING_DURABLE=1205};
enum {PC02_NO_FAULT=0,PC02_SHORT_WRITE=1,PC02_SYNC_FAIL=2,PC02_READBACK_FAIL=3};
typedef struct {void *context;void (*phase)(void *,unsigned);unsigned fault,fault_phase;} pc02_controls;
/* Caller is trusted to prove actual SDK content, publication/abort and terminal
   workers for this exact descriptor and journal terminal SHA. The descriptor
   and terminal are NULL during explicit initial enrollment. fd is borrowed:
   do not close or modify it; all SDK handles/sources must close before return. */
typedef int (*pc02_prove)(void *,const char *library,int fd,
 const pc02_pending_record *,const char *terminal_sha);
/* authority_root is independent host configuration, outside migration packages
   and the library namespace: e.g. app no-backup/Application Support/state root.
   Its final directory must be euid-owned mode0700, files mode0600; ancestors
   must be euid/root-owned and deny group/other writes. Ordinary open creates
   nothing. These application locks do not isolate hostile same-user code.
   Library ancestors support UTF-8; the final basename is portable ASCII
   [A-Za-z0-9._-], folded to lowercase in the route to bind case aliases. */
/* Explicit platform scope. The fixed host factory, not a migration package,
   supplies the already-open application container and independently captured
   native identity. The anchor must be euid-owned, with owner rwx and no special
   or group/other write bits; 0755/0711 are accepted. Its captured permissions
   must remain exact throughout the scope lifetime. Each lease keeps its
   own CLOEXEC duplicate; closing the factory scope cannot release a live lease.
   OS ancestors above this trusted fd are outside the strict Linux path walk.
   Relative paths below it are still traversed with openat/O_NOFOLLOW and their
   permissions/identities checked. Scope and authority must be fixed for every
   reader and migrator sharing this library. */
int pc02_scope_create(int trusted_context_directory,const pc02_identity *expected,pc02_scope **);
int pc02_scope_close(pc02_scope *);
int pc02_authority_create_in(pc02_scope *,const char *authority_relative);
int pc02_enroll_in(pc02_scope *,const char *authority_relative,const char *library_relative,
 int create_library,pc02_prove,void *,const pc02_controls *);
int pc02_recover_enrollment_in(pc02_scope *,const char *authority_relative,
 const char *library_relative,pc02_prove,void *,const pc02_controls *);
int pc02_open_in(pc02_scope *,const char *authority_relative,const char *library_relative,
 unsigned mode,const pc02_grant *expected,const pc02_controls *,pc02_lease **);
/* Borrowed path, valid only while the checked lease lives. Scoped leases expose
   the actual directory-fd-derived path, never an unvalidated package spelling. */
const char *pc02_library_path(pc02_lease *);
int pc02_authority_create(const char *authority_root);
/* Explicit only. A new route is reserved before prove; an existing incomplete
   route is never filled in or adopted by this call. create_library uses O_EXCL. */
int pc02_enroll(const char *authority_root,const char *library,int create_library,
 pc02_prove,void *,const pc02_controls *);
int pc02_recover_enrollment(const char *authority_root,const char *library,
 pc02_prove,void *,const pc02_controls *);
int pc02_open(const char *authority_root,const char *library,unsigned mode,
 const pc02_grant *expected,const pc02_controls *,pc02_lease **);
int pc02_check(pc02_lease *);
int pc02_grant_get(pc02_lease *,pc02_grant *);
int pc02_borrow(pc02_lease *);
int pc02_unborrow(pc02_lease *);
/* Manifest/input must be lowercase nonzero SHA256 values. begin flushes and
   independently reads back PENDING before returning a live opaque capability. */
int pc02_begin(pc02_lease *,const char manifest_sha[65],const char input_sha[65],pc02_cap **);
int pc02_pending(pc02_lease *,pc02_pending_record *);
int pc02_resume(pc02_lease *,const pc02_pending_record *exact,pc02_cap **);
int pc02_prepare_publish(pc02_lease *,pc02_cap *);
int pc02_finish(pc02_lease *,pc02_cap *,const char terminal_sha[65],
 pc02_prove,void *,pc02_grant *);
/* CLEAN on disk but its Binding update was not confirmed: ordinary open refuses.
   Only exact original pending descriptor + terminal + fresh actual proof can
   complete the independent Binding update. Never grants a mutation capability. */
int pc02_reconcile(pc02_lease *,const pc02_pending_record *exact,
 const char terminal_sha[65],pc02_prove,void *,pc02_grant *);
/* Externally serialize a lease, as with the SDK migration owner. close refuses
   live caps/borrows. It never writes CLEAN, repairs tails, or deletes evidence. */
int pc02_close(pc02_lease *);
/* Checked native operations used by the synchronous C02 migration provider.
   Caller externally serializes a lease. Parent fd is borrowed; do not close it.
   These helpers never infer SDK content, adopt a descriptor, or clear PENDING. */
int pc02_cap_check(pc02_lease *,pc02_cap *);
/* Explicit failure release: no live borrows, exact original cap only. It
   invalidates that cap, preserves every byte/PENDING, and permanently poisons
   this lease. close may then release handles; no CLEAN or repair is written. */
int pc02_abandon(pc02_lease *,pc02_cap *);
int pc02_parent_fd(pc02_lease *,int *borrowed,pc02_identity *);
int pc02_descriptor(pc02_lease *,pc02_pending_record *,int *complete_clean);
enum {PC02_META_INPUT=1,PC02_META_PREPARED=2};
typedef struct {
 pc02_identity identity;uint64_t bytes;char sha256[65],payload_sha256[65];
} pc02_metadata_info;
/* INPUT requires a clean OWNER, no cap; PREPARED requires this generation's
   live cap. Payload <=65536 bytes, complete file is O_EXCL + NOREPLACE + fsync.
   Pending input is the returned payload SHA. All partial temp bytes remain. */
int pc02_metadata_write(pc02_lease *,unsigned phase,pc02_cap *,
 const void *,size_t,char payload_sha256[65],pc02_metadata_info *);
/* 1=valid, 0=absent, -1=invalid/error. exact must be the authority's original
   B descriptor, including after complete C. No absence/invalid fallback. */
int pc02_metadata_read(pc02_lease *,unsigned phase,const pc02_pending_record *exact,
 void *,size_t,size_t *,pc02_metadata_info *);
typedef struct {
 uint64_t count;char manifest[65],last_line_sha256[65],chain_sha256[65];
} pc02_floor;
int pc02_floor_read(pc02_lease *,const pc02_pending_record *,pc02_floor *);
int pc02_floor_advance(pc02_lease *,pc02_cap *,const pc02_floor *exact,
 const char line_sha256[65],pc02_floor *);
typedef struct {
 char target[256],stage[256],retained[256];int original_present;
 pc02_identity original,prepared;
} pc02_member;
/* FD arguments are borrowed; original=-1 only for an originally absent mirror.
   The provider independently proves the complete original/prepared bytes and
   closes all actual SDK owners and sources before this callback returns. */
typedef int (*pc02_member_prove)(void *,int original,int prepared);
/* Exact states: 0=original+stage, 1=retained+stage, 2=retained+published.
   Only library and its .legacy-map.json mirror are admissible target names. */
int pc02_member_observe(pc02_lease *,const pc02_member *,unsigned *);
int pc02_member_publish(pc02_lease *,pc02_cap *,const pc02_member *,
 pc02_member_prove,void *);

#ifdef __cplusplus
}
#endif
#endif
