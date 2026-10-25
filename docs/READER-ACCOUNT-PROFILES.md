# J13 reader account profiles

Secret-free account-profile records and the isolated directory mapping the host
later feeds to the existing `reader_session`. Package:
`apps/reader/account-profiles/` (README, public header, C sources, CMake
package). Consumers and the cloud checker: `tests/reader_account_profiles/`.
Workflow: `.github/workflows/reader-account-profiles.yml`.

- Fixed implementation start: `f43baf9182d75907c0cb5d6f77048f27bca8c950`
- Frozen SDK: `9854061be331fe603a1822d9b2b36ee357154927` (3.40.0, ABI 1), unchanged
- Branch: `codex/reader-account-profiles` (never the default branch)
- Ownership: only `apps/reader/account-profiles/**`, `tests/reader_account_profiles/**`,
  `.github/workflows/reader-account-profiles.yml`, this document and
  `docs/validation/reader-account-profiles.json` change. Product schema, wire v1, reading
  anchor v1/v2, the session/sync/revision/webdav packages and the protected SDK tree
  are byte-identical to the fixed start; the workflow proves it with `git diff`.

## What the component is

A device-local list of user-named profiles, each exactly
`{profile_id, account_id, root_url, display_name}`. The profile id alone selects the
directory tree `S/profiles/<profile_id>/{library.sqlite,private,originals}`, so two
accounts that share one URL, and one account that uses two URLs, never share a
product database, a private transfer directory or a staged-original directory.

It stores no credential, token, password, cookie, `Authorization` header, URL userinfo,
query or fragment. It never opens, creates, rebinds, copies or deletes a product
database, never touches the SDK, never talks to the network and never changes the
session module. Activation is two-phase: `prepare_activation()` returns a verified plan,
the host closes its existing session/SDK handles, then `verify_activation()` re-checks
that plan and only afterwards the host calls `reader_session_create()` with the plan's
three paths plus the profile's account and root URL.

The binding file is not invented here: it is exactly what the fixed
`apps/reader/session/src/session.cpp` already writes,
`<product_path>.sync-account` containing
`"EXReader account v1\n<account_id>\n<root_url>\n"`. A non-empty library without a
binding, or bound to another account or URL, returns `BINDING`; a local product
database is never silently adopted. The installed C++ consumer proves the two
sides agree by driving the real session.

The complete input/output, ownership, thread, error, cancellation, commit-boundary
and limit contract is in `apps/reader/account-profiles/README.md` and the public header.

## Cloud acceptance

Everything — configure, compile, tests, fixtures, process kills, junctions and the
real session — runs only in GitHub Actions. The workflow has four named steps of
interest per platform:

1. guard: `HEAD == GITHUB_SHA`, fixed start is an ancestor, protected SDK tree,
   product SQL, product provider, session, sync, revisions and webdav are
   unchanged, and every changed path is inside the ownership list above;
2. build and install the unchanged host chain (product catalog, webdav, revisions,
   sync, session) and then `EXReaderAccountProfiles` into its own prefix;
3. compile an independent C consumer, an independent C++ consumer that links the
   real `reader_session`, and a worker that alone is built from package sources with
   explicit test hooks (the installed library cannot be paused, failed or
   cancelled through environment variables);
4. judge the named cases, then on Linux rebuild package plus probes with
   AddressSanitizer and UndefinedBehaviorSanitizer and record `failures=0`.

A second job downloads the three same-run artifacts through the authenticated API,
recomputes each ZIP SHA-256, refuses mismatched id/bytes/digest/expiry, requires
the identical named case set and an all-pass outcome on every platform, requires
the real-session case on every platform, and refuses a set of deliberately
mutated reports.

### Named cases

installed-c-consumer, installed-cpp-session-consumer, validate-unicode-names,
validate-utf8-refusals, validate-uuid, validate-url-rules, secret-url-refused,
add-load-roundtrip-unicode, duplicate-id-and-pair,
same-url-different-account-isolation, same-account-different-url-isolation,
profile-count-limit, file-limit-lowered, unknown-version-preserved,
corrupt-format-preserved, noncanonical-bytes-preserved, cancelled-add-before-lock,
cancelled-save-preserves, failed-save-preserves, lock-timeout-and-recovery,
real-termination-releases-lock, crash-before-rename-leftover,
concurrent-processes-no-lost-update, thread-reentrancy, generation-conflict,
argument-and-struct-size, activation-derived-paths, no-directory-before-activation,
unsafe-link-rejected, hardlink-library-rejected, binding-missing-refused,
binding-mismatch-refused, binding-match-accepted, verify-tampered-plan,
verify-stale-plan, verify-missing-profile, unicode-store-path, secret-scan,
no-sdk-or-product-dependency, cross-account-real-session.

### Evidence

- Platform artifact: `reader-account-profiles-<platform>-<run>-<attempt>` containing
  `ap-evidence/result.json`, `ap-logs/check.log`, the whole work tree with every
  produced document and every failure, the installed prefix and the build logs.
- Same-run evidence artifact: `reader-account-profiles-evidence-<run>-<attempt>`
  containing `ap-artifact-evidence/artifacts.json`.
- Identity: `source_sha`, `run_id`, `attempt`, artifact id, non-zero bytes,
  declared `sha256` digest and recorded expiry and a recomputed digest must all agree.

## Reproduction

    git clone https://github.com/NoGod3524/EXReader
    git checkout codex/reader-account-profiles
    # push or dispatch the workflow; nothing is built locally
    gh run watch <run-id>

The checker is invoked by the workflow as

    python3 tests/reader_account_profiles/check_account_profiles.py \
      --probe build/ap-consumer/profiles-probe \
      --session build/ap-consumer/profiles-session-consumer \
      --worker build/ap-consumer/profiles-worker \
      --prefix build/ap-prefix --work build/ap-work \
      --output build/ap-evidence --platform <Linux|Windows|macOS>

## Cloud record

Same-source run: [40127110929 attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40127110929),
workflow `.github/workflows/reader-account-profiles.yml`, tested source
`b1c7467af0b9faf843b9ec988df49c0476c74ee9`.

| job | id | conclusion |
| --- | --- | --- |
| account profiles (ubuntu-22.04) | 120970784004 | success |
| account profiles (windows-2022) | 120970784075 | success |
| account profiles (macos-15) | 120970784047 | success |
| same-run artifact evidence | 120971062350 | success |

| artifact | id | bytes | sha256 | expires |
| --- | --- | --- | --- | --- |
| reader-account-profiles-Linux-40127110929-1 | 12573753172 | 1247476 | `0bac87b3bd626896c5c2d2fde43f29dd6aa3d9e97edd7d1ac5aa5e56053b1ddc` | 2027-01-22T19:50:25Z |
| reader-account-profiles-Windows-40127110929-1 | 12573323555 | 1237680 | `6657842b7b15dcb910631d6bc22436cb1ea19f1330240c6e171a5bf10f9df5af` | 2027-01-22T19:50:25Z |
| reader-account-profiles-macOS-40127110929-1 | 12573183555 | 938161 | `7d02c297134756ef295bd5f1b23f7f82d2821e9aa849685f48bc36d7a970117f` | 2027-01-22T19:50:25Z |
| reader-account-profiles-evidence-40127110929-1 | 12573243659 | 956 | `41d45aca6d600d6cd0543cb41cc782ba21b9901c314083cd8a33b19b43ab8f07` | 2027-01-22T19:50:25Z |

Every declared digest was recomputed from the downloaded ZIP in the cloud evidence
job and matched, the three platform case sets were identical, 40 of 40 cases
passed on each platform, nine mutated reports were rejected by the validator, and
the Linux AddressSanitizer plus UndefinedBehaviorSanitizer run recorded
`failures=0`.

### Real-session cross-account proof

Identical on all three platforms (raw record kept at
`ap-work/session/session-consumer.json` in each artifact):

    prepare_a=0 prepare_b=0 distinct=true
    create_a=0 state_a=5 status_a=5 closed_a=1 destroy_a=0
    binding_a=true verify_a=0
    borrow_create=0 borrow_state=5 borrow_status=4 borrow_closed=1
    own_b_create=0 own_b_status=5 own_b_closed=1
    binding_b=true verify_b=0

`status=4` is `READER_SESSION_ACCOUNT`: the real, unchanged session refused to reuse
account A's product library when it was handed account B's identity, so a second
account cannot borrow the first account's local library. `status=5` is
`READER_SESSION_SYNC` from the loopback URL that refuses the connection; no remote
transfer is claimed. `verify_a`/`verify_b=0` show that this package accepts exactly the binding
file the real session writes.

## Scope and limitations

- The package is a component. Wiring it into the Windows, GTK, Android, Apple or
  other host UIs, and the credentials backend that adds `Authorization`, stay with
  root and the host owners. This document does not claim host or product
  integration.
- No real account secret, private document or user cloud drive is used. The
  real-session proof uses a loopback URL that refuses the connection, so only the
  local binding, product-database and refusal paths are exercised; no remote
  transfer is claimed.
- `add`/`rename`/`remove`/`load` trust the caller-supplied store directory and rely on the operating
  system; `prepare_activation` and `verify_activation` verify every component of that path and
  create the profile directories themselves.
- `thread-reentrancy` adds from four threads of one process; because the library holds
  no shared memory, true parallelism is additionally covered by the eight-process
  exclusion case. No wider race freedom is claimed.
- Cancellation is polled, not asynchronous: a callback that never returns blocks
  the call exactly as documented.
- The two-phase commit cannot make a same-user attacker race impossible between
  `verify_activation()` and the host's own `reader_session_create()`; it narrows the window.
- Android and Apple platform grants are not claimed. Only the three desktop
  runners in the workflow are in scope.

## Retained failures

Every earlier attempt is kept in its own run; nothing was deleted, retargeted or
turned into an expected refusal.

| run | source | real failure | resolution |
| --- | --- | --- | --- |
| 40123173113 | f5b04d48 | package build: the binding presence flag was not declared | declared it in the binding read block |
| 40124406060 | a8f8c01c | Linux: `-Wformat-truncation` on the plan product copy; macOS: the probe used a non-existent list member | bounded copy plus the public `profiles` member |
| 40124868582 | be4ec926 | probe and worker truncated profile fields through `snprintf` | bounded `copy_field` helper |
| 40125587687 | 187b6796 | the checker passed relative store paths and expected a 129-byte name the struct cannot hold | resolve the work root; judge the oversized stored name as `FORMAT` |
| 40126050835 | d8ff6cd2 | the binding path was built with a separator instead of the product-path suffix (four named cases) | append `.sync-account` to the product path |
| 40126331462 | 91cbcb0e | platforms green, evidence job required its own not-yet-uploaded artifact | authenticate the three upstream artifacts before the record is uploaded |

## Acceptance

`docs/validation/reader-account-profiles.json` records `accepted: true` for this component
only, bound to run 40127110929 attempt 1 at `b1c7467af0b9faf843b9ec988df49c0476c74ee9`. The
evidence commit is documentation-only and carries `[skip ci]`, so the final HEAD
differs from the tested source only in this document and the validation record.
Root still owns host wiring and the joint re-verification on common source.
# Root activation 边界修复候选

独立分支 `codex/reader-account-profiles-review` 从交回 `2d67b87830a1fabad602aef2ac7bdb3ef579190e` 接续。verify此前只重新核private目录链，遗漏originals；现两个派生目录都核查。共享UUID校验去掉无界strlen，在37字节内完成，拒绝整个固定容量plan无NUL的输入。

新增两个安装消费者场景：prepare完成后真实替换originals为符号链接/Windows junction，verify必须UNSAFE_PATH且不触碰目标；整个activation在独立堆分配中填满非NUL，必须INVALID，Linux另在ASan/UBSan下执行。原40项及真实session跨账号隔离、所有严格工件认证保留；当前候选待Actions同源验证，原交回的通过不转授。

