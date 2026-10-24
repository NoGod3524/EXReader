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

## Scope and limitations

- The package is a component. Wiring it into the Windows, GTK, Android, Apple or
  other host UIs, and the credentials backend that adds `Authorization`, stay with
  root and the host owners. This document does not claim host or product
  integration.
- No real account secret, private document or user cloud drive is used. The
  session proof uses a loopback URL that refuses the connection, so only the local
  binding, product-database and refusal paths are exercised; no remote transfer is
  claimed.
- `thread-reentrancy` adds from four threads of one process; because the library holds
  no shared memory, true parallelism is additionally covered by the eight-process
  exclusion case. No race inside the library is claimed beyond what those cases
  show.
- Cancellation is polled, not asynchronous: a callback that never returns blocks
  the call exactly as documented.
- The two-phase commit cannot make a same-user attacker race impossible between
  `verify_activation()` and the host's own `reader_session_create()`; it narrows the window.
- Android and Apple platform grants are not claimed. Only the three desktop
  runners in the workflow are in scope.

## Retained failures

None yet: this document was written before the first cloud run. Real failures,
retained logs and any unimplemented behaviour are appended here after the run;
they are never deleted or retargeted.

## Acceptance

`docs/validation/reader-account-profiles.json` starts at `accepted: false` / `status:
implementation-complete-cloud-pending` and is only rewritten from the real same-source
run. The evidence commit is documentation-only and carries `[skip ci]`.
