/* SPDX-License-Identifier: MIT */
#ifndef READER_ACCOUNT_PROFILES_H
#define READER_ACCOUNT_PROFILES_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define READER_ACCOUNT_PROFILES_VERSION_STRING "0.1.0"
#define READER_ACCOUNT_PROFILES_ABI_VERSION 1u
#define READER_ACCOUNT_PROFILES_FORMAT_VERSION 1u

#if defined(_WIN32) && defined(READER_ACCOUNT_PROFILES_BUILD_SHARED)
#define READER_ACCOUNT_PROFILES_API __declspec(dllexport)
#elif defined(_WIN32) && defined(READER_ACCOUNT_PROFILES_USE_SHARED)
#define READER_ACCOUNT_PROFILES_API __declspec(dllimport)
#else
#define READER_ACCOUNT_PROFILES_API
#endif

/* Hard limits. Every one is enforced on add/load and covered by a named test. */
#define READER_ACCOUNT_PROFILES_MAX_PROFILES 32u
#define READER_ACCOUNT_PROFILES_UUID_BYTES 36u
#define READER_ACCOUNT_PROFILES_MAX_NAME_BYTES 128u     /* UTF-8, excluding NUL */
#define READER_ACCOUNT_PROFILES_MAX_URL_BYTES 1024u     /* ASCII, excluding NUL */
#define READER_ACCOUNT_PROFILES_MAX_STORE_PATH_BYTES 2048u /* UTF-8, excluding NUL */
#define READER_ACCOUNT_PROFILES_MAX_PATH_BYTES 2304u    /* every derived path */
#define READER_ACCOUNT_PROFILES_MAX_FILE_BYTES 131072u  /* profiles.json */
#define READER_ACCOUNT_PROFILES_DEFAULT_LOCK_TIMEOUT_MS 2000u
#define READER_ACCOUNT_PROFILES_MAX_LOCK_TIMEOUT_MS 10000u

/* Non-secret account profile records and their isolated on-disk mapping.

   What it is: a small, versioned, device-local list of user-named profiles. A
   profile is {profile_id, account_id, root_url, display_name}. The profile id
   alone selects the directory tree, so two accounts that share one URL, and one
   account that uses two URLs, never share a product database, private transfer
   directory or staged-original directory.

   What it is not: no credential, token, password, Authorization header, cookie
   or URL userinfo/query is ever stored, accepted or echoed (SECRET status).
   It never opens, creates, rebinds, copies or deletes a product database, never
   touches the SDK, never talks to the network and never changes the session
   module. Activation is two-phase: prepare_activation() produces and verifies
   a plan; the HOST then closes its existing reader_session/SDK handles and only
   afterwards feeds the plan to reader_session_create() (see the installed
   example). Nothing here starts, stops or observes a session.

   Store layout under the caller's absolute store directory S:
     S/profiles.json              the document (written atomically)
     S/profiles.json.tmp          crash leftover only; removed by the next writer
     S/.lock                      cross-process writer lock
     S/profiles/<profile_id>/library.sqlite   product path handed to the session
     S/profiles/<profile_id>/private/         session private directory
     S/profiles/<profile_id>/originals/       session staged originals
   <profile_id> is a lowercase 36-character UUID, so a directory name is ASCII
   and cannot contain a separator, "..", a drive or a case-folded duplicate.

   Memory ownership: every struct is a plain caller-owned value; the library
   never retains a pointer to caller memory, never allocates anything the
   caller must free and keeps no global state. Paths are borrowed UTF-8 for one
   call. Large structs (list ~42 KB, activation ~7 KB) should live on the heap
   or in static storage in a GUI thread with a small stack.

   Threads and re-entry: all functions are re-entrant and thread-safe with
   respect to the library's own memory (there is none shared). Concurrent
   mutations of one store, from threads or processes, are serialised by an
   exclusive OS file lock on S/.lock held for one read-modify-write. A call that
   cannot get the lock within lock_timeout_ms returns LOCKED with no change.
   Calling back into the same store from the cancel callback is unsupported (it
   would return LOCKED). Do not call these from a UI thread with a long lock
   timeout: file I/O and fsync are synchronous.

   Cancellation: the control callback is polled on the calling thread before the
   lock, while waiting for it, after the read, before and during the temporary
   write and once more immediately before the rename. The rename is the commit
   boundary: before it CANCELLED leaves profiles.json byte-for-byte unchanged and
   removes the temporary; after it the result is OK even if the callback would
   now cancel. Errors that happen after the rename (directory flush) are not
   reported because the new document is already visible.

   Cross-process policy: readers never lock; they see either the previous or the
   next whole document because replacement is by rename. Writers lock, re-read,
   verify the document (unknown version or damage is returned and never
   overwritten), optionally compare expected_generation (CONFLICT) and replace.
   Processes killed anywhere leave the old document and release the lock. */
typedef enum {
  READER_ACCOUNT_PROFILES_OK = 0,
  READER_ACCOUNT_PROFILES_ARGUMENT = 1,    /* null pointer, struct_size, relative store path, bad option */
  READER_ACCOUNT_PROFILES_IO = 2,          /* open/read/write/fsync/rename failed; system_error set */
  READER_ACCOUNT_PROFILES_FORMAT = 3,      /* damaged or non-canonical document */
  READER_ACCOUNT_PROFILES_VERSION = 4,     /* well-formed header with an unsupported version */
  READER_ACCOUNT_PROFILES_INVALID = 5,     /* UUID, display name or URL violates the field rules */
  READER_ACCOUNT_PROFILES_SECRET = 6,      /* URL carries userinfo, query or fragment */
  READER_ACCOUNT_PROFILES_CANCELLED = 7,   /* caller control asked to stop before commit */
  READER_ACCOUNT_PROFILES_LIMIT = 8,       /* profile count or file size limit */
  READER_ACCOUNT_PROFILES_NOT_FOUND = 9,   /* no such profile id */
  READER_ACCOUNT_PROFILES_EXISTS = 10,     /* duplicate profile id or {account_id, root_url} pair */
  READER_ACCOUNT_PROFILES_CONFLICT = 11,   /* expected_generation differs, or plan no longer matches */
  READER_ACCOUNT_PROFILES_LOCKED = 12,     /* writer lock not obtained in time */
  READER_ACCOUNT_PROFILES_UNSAFE_PATH = 13,/* link/junction/reparse, non-directory, hard link or foreign object */
  READER_ACCOUNT_PROFILES_BINDING = 14     /* existing product library is bound to another account/URL or is unbound */
} reader_account_profiles_status;

/* Zero-initialise and set struct_size. */
typedef struct {
  uint32_t struct_size;
  reader_account_profiles_status status;
  int system_error;   /* errno / GetLastError when status is IO, else 0 */
  size_t offset;      /* byte offset in profiles.json for FORMAT/VERSION */
  char message[192];  /* fixed text; never contains a URL or a name */
} reader_account_profiles_error;

/* Return nonzero to cancel. Called synchronously on the calling thread. */
typedef int (*reader_account_profiles_cancel_fn)(void *context);
typedef struct {
  reader_account_profiles_cancel_fn cancelled;
  void *context;
} reader_account_profiles_control;

enum { READER_ACCOUNT_PROFILES_CHECK_GENERATION = 1u };

/* Zero-initialise and set struct_size; every field is optional. */
typedef struct {
  uint32_t struct_size;
  reader_account_profiles_control control;
  uint32_t flags;              /* READER_ACCOUNT_PROFILES_CHECK_GENERATION */
  uint64_t expected_generation;/* compared under the lock when the flag is set */
  uint32_t lock_timeout_ms;    /* 0 = 2000; >10000 is ARGUMENT */
  size_t max_file_bytes;       /* 0 = 131072; may only lower it, larger is ARGUMENT */
} reader_account_profiles_options;

/* One profile. Strings are NUL-terminated and fixed-capacity.
   profile_id/account_id: lowercase 8-4-4-4-12 hex UUID, not all zero.
   root_url: https://host[:port]/path/ — ASCII, ends with '/', no userinfo, query,
     fragment, space, backslash or quote; stored and compared byte for byte (the
     session binds the exact string, so the library never rewrites it).
   display_name: 1..128 bytes of strictly valid UTF-8, no C0/C1 control, no
     leading or trailing space; kept byte for byte (no normalisation). */
typedef struct {
  uint32_t struct_size;
  char profile_id[READER_ACCOUNT_PROFILES_UUID_BYTES + 1u];
  char account_id[READER_ACCOUNT_PROFILES_UUID_BYTES + 1u];
  char root_url[READER_ACCOUNT_PROFILES_MAX_URL_BYTES + 1u];
  char display_name[READER_ACCOUNT_PROFILES_MAX_NAME_BYTES + 1u];
} reader_account_profile;

typedef struct {
  uint32_t struct_size;
  uint64_t generation;  /* 0 = no document yet; +1 per committed mutation */
  uint32_t count;
  reader_account_profile profiles[READER_ACCOUNT_PROFILES_MAX_PROFILES];
} reader_account_profiles_list;

/* A verified, not yet active plan. The three paths are exactly what
   reader_session_config.product_path / private_directory / original_directory
   expect; account_id and root_url feed account_id / dav.root_url. The plan holds
   no credential: the host adds Authorization from the credentials module. */
typedef struct {
  uint32_t struct_size;
  uint64_t store_generation;
  reader_account_profile profile;
  char product_path[READER_ACCOUNT_PROFILES_MAX_PATH_BYTES + 1u];
  char private_directory[READER_ACCOUNT_PROFILES_MAX_PATH_BYTES + 1u];
  char original_directory[READER_ACCOUNT_PROFILES_MAX_PATH_BYTES + 1u];
} reader_account_profiles_activation;

READER_ACCOUNT_PROFILES_API uint32_t reader_account_profiles_abi_version(void);
READER_ACCOUNT_PROFILES_API const char *reader_account_profiles_status_name(reader_account_profiles_status status);
READER_ACCOUNT_PROFILES_API void reader_account_profiles_error_clear(reader_account_profiles_error *error);

/* Field rules only (struct_size, UUIDs, name, URL). Returns OK, ARGUMENT,
   INVALID or SECRET. No file is touched. */
reader_account_profiles_status
READER_ACCOUNT_PROFILES_API reader_account_profiles_validate(const reader_account_profile *profile,
                                 reader_account_profiles_error *error);

/* Read the document. A missing document is OK with generation 0 and count 0.
   *out is written only on OK; on every other status it is untouched. Damaged or
   unknown-version documents are reported (FORMAT/VERSION) and never modified.
   Lock-free. Order of profiles is insertion order. */
reader_account_profiles_status
READER_ACCOUNT_PROFILES_API reader_account_profiles_load(const char *store_dir, reader_account_profiles_list *out,
                             const reader_account_profiles_options *options,
                             reader_account_profiles_error *error);

/* Append a profile. EXISTS if the id or the exact {account_id, root_url} pair is
   present; LIMIT beyond 32 profiles or 128 KiB. Does not create directories.
   new_generation may be NULL. Commit boundary: the rename (see above). */
reader_account_profiles_status
READER_ACCOUNT_PROFILES_API reader_account_profiles_add(const char *store_dir, const reader_account_profile *profile,
                            const reader_account_profiles_options *options,
                            uint64_t *new_generation, reader_account_profiles_error *error);

/* Change only display_name. Account and URL are immutable: to point at another
   URL or account add a new profile, which gets a new empty library. */
reader_account_profiles_status
READER_ACCOUNT_PROFILES_API reader_account_profiles_rename(const char *store_dir, const char *profile_id,
                               const char *display_name,
                               const reader_account_profiles_options *options,
                               uint64_t *new_generation, reader_account_profiles_error *error);

/* Remove the record only. The profile directory and its library are never
   deleted by this package; re-adding the same id re-attaches it, subject to the
   binding check in prepare_activation. */
reader_account_profiles_status
READER_ACCOUNT_PROFILES_API reader_account_profiles_remove(const char *store_dir, const char *profile_id,
                               const reader_account_profiles_options *options,
                               uint64_t *new_generation, reader_account_profiles_error *error);

/* Build a pending activation plan for an existing profile. Under the writer
   lock it creates (mode 0700) S/profiles/<id>/{private,originals} when absent
   and verifies every component of S itself, profiles, <id>, private and
   originals is a real directory (no symlink, junction or reparse point; a
   file in the way is UNSAFE_PATH), that library.sqlite is absent or a
   single-link regular file, and that an existing library is bound to exactly
   this account and URL. A non-empty library without a binding file, or bound to
   other values, returns BINDING: the library is never silently adopted.
   *out is written only on OK. Never starts a session. */
reader_account_profiles_status
READER_ACCOUNT_PROFILES_API reader_account_profiles_prepare_activation(const char *store_dir, const char *profile_id,
                                           const reader_account_profiles_options *options,
                                           reader_account_profiles_activation *out,
                                           reader_account_profiles_error *error);

/* Re-check a plan immediately before enabling it, after the host closed the
   previous session: the profile still exists with the same id, account and URL
   (CONFLICT/NOT_FOUND otherwise), the path chain is still link-free
   (UNSAFE_PATH), and the binding still matches (BINDING). Paths in the plan must
   equal the derived paths (ARGUMENT otherwise). Lock-free and side-effect free.
   The check cannot make a later race with a same-user attacker impossible; it
   narrows the window to the host's own session-create call. */
reader_account_profiles_status
READER_ACCOUNT_PROFILES_API reader_account_profiles_verify_activation(const char *store_dir,
                                          const reader_account_profiles_activation *plan,
                                          const reader_account_profiles_options *options,
                                          reader_account_profiles_error *error);

#ifdef __cplusplus
}
#endif
#endif