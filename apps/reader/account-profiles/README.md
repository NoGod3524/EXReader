# EXReaderAccountProfiles

Device-local, secret-free account profiles and their isolated directory mapping.
This package is a small C library with a C ABI, its own CMake package and no
dependency on the SDK, the product catalog, SQLite, the network or any host UI.

## What it records

A profile is exactly four non-secret fields:

| field | rule |
| --- | --- |
| `profile_id` | lowercase 8-4-4-4-12 UUID, not all zero; the directory name |
| `account_id` | lowercase 8-4-4-4-12 UUID, not all zero; the session account |
| `root_url` | `https://host[:port]/path/`, ASCII, trailing slash, byte-exact |
| `display_name` | 1..128 bytes of valid UTF-8, no C0/C1 control, no leading/trailing space |

A credential, token, password, `Authorization` header, cookie, URL userinfo,
query or fragment is never accepted, stored, echoed or returned. `root_url` is
never rewritten: the existing session binds the exact string.

## Store layout

Under one caller-supplied absolute directory `S`:

    S/profiles.json                          the document (replaced atomically)
    S/profiles.json.tmp                      crash leftover; removed by the next writer
    S/.lock                                  cross-process writer lock
    S/profiles/<profile_id>/library.sqlite   product path for reader_session
    S/profiles/<profile_id>/private/         session private directory
    S/profiles/<profile_id>/originals/       session staged originals

`<profile_id>` is a lowercase UUID, so a directory name is ASCII, cannot contain a
separator, `..`, a drive or a case-folded duplicate.

## Public contract

`include/reader_account_profiles.h` is the complete surface. Semantics that the
tests pin:

- **Input/output.** All structures are caller-owned plain values. `struct_size` must
  equal `sizeof` of the exact structure; strings are borrowed NUL-terminated UTF-8 for
  the duration of one call. `load` writes `*out` only on `OK`; every other status
  leaves the caller's value untouched. `prepare_activation` writes its plan only on
  `OK`.
- **Memory ownership.** The library never allocates anything the caller must free,
  never retains a caller pointer and keeps no global mutable state. Large values
  (`list` ~39 KB, `activation` ~7.6 KB) should live on the heap or in static
  storage on a small-stack UI thread.
- **Threads and re-entry.** Functions are re-entrant and share no library memory.
  Concurrent mutations of one store, from threads or processes, are serialised by an
  exclusive OS file lock on `S/.lock` held for one read-modify-write. A caller that
  cannot get the lock within `lock_timeout_ms` gets `LOCKED` with no change. Calling
  back into the same store from the cancel callback is unsupported.
- **Cancellation.** The control callback is polled on the calling thread: before the
  lock, while waiting for it, after the read, before and during the temporary write,
  and once more immediately before the rename. The rename is the commit boundary:
  `CANCELLED` before it leaves `profiles.json` byte-for-byte unchanged and removes
  the temporary; after it the result is `OK`.
- **Errors.** `reader_account_profiles_error` carries the status, an OS error when the
  status is `IO`, a byte offset in `profiles.json` for `FORMAT`/`VERSION`/`INVALID`,
  and a fixed message. Messages never contain a URL or a name.
- **Commit boundary and crash policy.** Writers lock, re-read, verify the document
  (unknown version or damage is reported and never overwritten), optionally compare
  `expected_generation` (`CONFLICT`) and replace by rename plus directory flush.
  Processes killed anywhere leave the previous document and release the lock; the
  next writer removes a leftover `.tmp`.

## Activation is two-phase

`prepare_activation` verifies, under the writer lock, that every component of `S`
and of `profiles`, `<profile_id>`, `private` and `originals` is a real directory
(no symlink, junction or reparse point), creates the three directories with mode
`0700` when absent, rejects a `library.sqlite` that is a link, a directory or a
multiply linked file, and requires an existing library to be bound to exactly this
account and this root URL.

The binding file is the contract the existing `reader_session` already writes:
`<product_path>.sync-account`, containing exactly

    EXReader account v1
    <account_id>
    <root_url>

A non-empty library without a binding, or bound to another account or URL, returns
`BINDING`: a local product database is never silently adopted. `remove` deletes
the record only; the directory stays, so re-adding the same id re-attaches it
subject to the same binding check.

The host then closes its existing `reader_session`/SDK handles, calls
`verify_activation` to re-check the plan and the path chain, and only then feeds the
plan to `reader_session_create` (`product_path`, `private_directory`,
`original_directory`, `account_id`, `dav.root_url`). The host adds
`Authorization` from its own credentials module; this package never sees it. Nothing
here starts, stops or observes a session.

## Hard limits

| limit | value |
| --- | --- |
| profiles per store | 32 |
| `display_name` | 128 bytes |
| `root_url` | 1024 bytes |
| store directory | 2048 bytes |
| any derived path | 2304 bytes |
| `profiles.json` | 131072 bytes (`max_file_bytes` may only lower it) |
| lock timeout | 2000 ms default, 10000 ms maximum |

## Build and install

    cmake -S apps/reader/account-profiles -B build/ap -G Ninja \
          -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=<prefix>
    cmake --build build/ap --parallel 4
    cmake --install build/ap

Consumers use `find_package(EXReaderAccountProfiles 0.1.0 EXACT CONFIG REQUIRED)` and
`EXReaderAccountProfiles::reader_account_profiles`. The installed target has no
interface link library, so no SDK or product package is pulled in.
