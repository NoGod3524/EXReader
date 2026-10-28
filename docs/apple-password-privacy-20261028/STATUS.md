# Apple password privacy — bounded F10 source candidate

Base: `8f8acf3234cba747165f001c0c96efe1b911e6ad`; installed SDK **3.42.0**.
Proposed branch: `codex/apple-password-privacy-20261028`.
Owned additions: `tests/apple_password_privacy_20261028/**`, this document,
`.github/workflows/apple-password-privacy-20261028.yml` only.

**Source preparation only. No remote commit/ref, Actions run or native pass.**
F10 publication has not been attempted or denied. Bounded publication and
Actions validation were authorized on 2026-10-28; publication is **pending final
amended-byte source review**. Denials from other work packages do not belong to
F10. No local build, syntax check, fixture generation, test or artifact parsing
was performed. Source reading/writing and source-file hashing are not execution
evidence. No Codex task, user computer, main push, PR, tag or release is used.

## Real credential route, with an explicit missing feature

The unchanged `HostAccountViews.swift` presents Remember / Update, but no
dedicated Forget control. The unchanged `HostAccounts.updateCredentials` deletes
the profile's stored credential when Remember is off, while keeping the supplied
authorization transiently in that process. This package exercises that actual
UI route; it does not add a Forget button, call the owner directly, replace the
credential backend, or label uncheck-and-update as a dedicated Forget action.

| Stage | Actual native operation | Required independent observation |
|---|---|---|
| `remember_closed` | Connect with Remember on; import one fixture EPUB; terminate | Account/original intact, no unexpected sync, clean captured private files/logs |
| `remember_reopened` | Launch a new process and manually sync | Full 256-shard sweep authenticated with the remembered synthetic credential |
| `session_closed` | New process; Update with a different synthetic credential and Remember off; sync; terminate | Full sweep uses only the new session credential; original unchanged |
| `session_reopened_missing` | New process; manually sync again | Native missing-credential failure and no new server request |

The new test runs separately on macOS, iPhone Simulator and iPad Simulator.
Actual loopback TLS uses a one-run certificate trusted only on the disposable
Actions runner/simulator; no public account/server is contacted. Credentials are
cryptographically random synthetic canaries generated only in Actions. The
fixture records credential *roles*, not Authorization bytes. Synthetic oracle
inputs are deliberately retained, labeled as test inputs, separately from
product snapshots so authentication can reconstruct every search variant.

Opening Update also observes the displayed username and SecureField values.
**An empty or masked SecureField is not evidence that a secret is absent.**
Restart behavior, authenticated network identity, and the retained byte scans
are separate evidence. Compact sync controls put state in their label and
failure detail in accessibility value; the test handles both layouts without
changing the product UI.

## Streaming privacy scope

At each checkpoint the app is terminated before inspection. Every regular file
under the actual product roots is streamed, including hidden files, SQLite/WAL,
cache, downloads and files larger than 64 MiB. macOS roots are the EXReader
Application Support profile and this package's preferences, cache and saved
state; absent optional roots are reported. Simulator scope is the **entire app
data container**. Captured EXReaderHost unified logs include info/debug events.
No extension whitelist, file-count cap, unreadable-file exemption, symlink
following or large-file skip can produce acceptance. Special/linked entries
and unreadable files refuse. Empty primary roots refuse.

Search variants include raw username/password, user:password, Basic header,
hex in both cases, padded/unpadded standard and URL-safe base64, ordinary and
fully percent-escaped URL forms, UTF-16/UTF-32 endian forms, and JSON escaping.
Overlap is the longest needle minus one, so a match spanning a chunk boundary
is not lost. These are enumerated variants, **not a claim about every possible
encoding, encryption, fragmentation or transformed secret**.

File identity, size, mtime and ctime are checked before/after streaming; a final
directory/file inventory detects mutations of earlier files and already-scanned
directory prefixes while later files or roots are read. Actual archive members
are then streamed and compared with scan digests; all roots are rescanned before
the checkpoint is published. Copied macOS preferences are checked against the
actual source again. This requires quiescent product output, not an adversarial
filesystem that can perfectly forge/change metadata between observations.
The complete optional macOS-root namespace is inventoried with `lstat` before
classification and rechecked at publication: a previously absent preference,
cache or saved-state root appearing late refuses, as does a dangling symlink.

Actions-only rejection fixtures cover every configured encoded variant across
chunk boundaries, clean and leaking files over 64 MiB, symlinks, unreadable and
empty roots, in-place overwrite of an already-read prefix, earlier-file and
earlier-root mutation, additions in an earlier directory, late creation of an
absent optional root, dangling optional roots, and canaries in file or empty
directory names. Reports contain variant labels, not matching secret bytes. These
scanner tests never count as product privacy acceptance.

## Retained identity and independent authentication

The scope guard requires the exact base as ancestor, exact checked-out source,
and **additions only** in the owned paths. Frozen SDK, production owners, old
tests/assertions and existing budgets remain unchanged. The existing SDK342
builder supplies raw selector/wave3/page-theme products. A new adapter changes
only generated SDK-version guards, generated bundle/configuration, and selects
the new test target. All production Swift source bytes are recorded unchanged.
The existing review fixture import control supplies the EPUB; this does not
award production-import UI coverage or replace the credential controls.

Actions retains the original xcresult, stage screenshots, typed-input oracle,
request-role log, all private snapshots, source EPUB, actual program ZIP,
packaged SDK runtime, link map, SDK identity and original/derived generators.
The aggregate job authenticates same-source/run/attempt producer jobs and API
artifact ID/digest/size/expiry, checks every member's digest, rereads the original
native case and attachments, rescans every snapshot byte independently, verifies
the actual account and original EPUB BLOB, and repeats actual program/provider
inspection. Older greens or synthetic scanner fixtures cannot satisfy it.
Before extraction, the entire ZIP namespace rejects normalized NFC/case-folded
parent aliases, duplicate names and file/directory collisions, along with links,
special entries and traversal. Archive resource limits are 8 GiB per member and
32 GiB total uncompressed bytes: exceeding a limit fails the whole evidence
gate, never truncates or skips a file. These extraction safeguards are distinct
from the streaming scanner, which has no per-file size exclusion. Actions-only
controls cover case/Unicode aliases, parent aliases, file/directory collisions,
ordinary implicit/explicit directories and both resource-limit refusals.

The workflow has one proposed feature-branch push trigger, no dispatch and no
built-in retry. New job limits: contract 10, SDK 90, native 90, authentication 30
minutes; the new native case uses default/max 240/360 seconds. Existing suite
limits are untouched. All builds/tests/fixtures/artifact work is Actions-only.

## Remaining gaps and stopping boundary

* **Dedicated Forget UI is absent and untested; full F10 stays false.** A future
  owner/UI change needs separate scope/authorization.
* Physical-device Keychain/access-group behavior is not established by a macOS
  host and simulators. Keychain bytes are not dumped/scanned: remembered storage
  there is expected, and deletion is inferred from the real restart/network
  behavior, not direct database inspection or forensic erasure.
* Logs means the retained readable unified-log export and logs inside the named
  product roots. Private/redacted OS logging payloads, arbitrary system logs,
  process memory, crash/core dumps outside those roots, and separately isolated
  product stdout/stderr are not proven secret-free. XCTest activity logs and the
  synthetic input file intentionally contain test inputs and are not mislabeled
  as product-output absence evidence.
* Simulator TLS trust, macOS Keychain prompts, native field values, real sweep
  completion and emitted log coverage remain runtime questions. A failure must
  stay failed/blocked; do not loosen assertions, skip bytes or change an owner.
* No native case, scanner control, source syntax or original-artifact validator
  has run. Final source review, publication and Actions execution remain pending; there is no remote
  SHA/run URL to report and no product acceptance to grant.
