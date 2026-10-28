# Windows F07 raw dependency capture — source-only candidate

## Status and scope

Base: `8f8acf3234cba747165f001c0c96efe1b911e6ad`, frozen SDK source
`8357eafa28423a7ab93ba08b823af80f01ad1505`, SDK version `3.42.0`.
Dedicated branch: `codex/reader-windows-f07-capture-20261028`.

This package was prepared **without execution or publication** on 2026-10-28. No build, syntax
check, test, fixture construction, native inspection or artifact parsing was run
outside Actions. These new sources have only been read and edited. An independent
Linux capture author reviewed the final source, including final-link/response
closure and complete nested F06 checks, and cleared the capture-only scope at
21:31 UTC. The parent relayed explicit user authorization at 21:31 UTC for
bounded branch publication and Actions validation. Any exact action denial must
still stop publication; no alternate GitHub write route may evade that denial.

The [original F06 run 40678657371, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40678657371)
used the base above. Its [Windows final upload 12812276328](https://github.com/NoGod3524/EXReader/actions/runs/40678657371/artifacts/12812276328)
was recorded by the separate original-package audit as 17,696,295 bytes,
SHA-256 `0206e54988ca50e3feae37d7f83457ab959d052ef350fb55eb9269007c2c9cd2`.
Those retained bytes do not include the final map and installed static module
archive closure. A later build cannot retroactively establish that old EXE's
static provider ownership. This package does not download or replace it.

## Preserve the old producer, collect new evidence

`run.py build` imports and calls the unchanged
`tests/reader_f06_packages/build.py::windows()`, then invokes unchanged
`tests/reader_f06_packages/identity.py package windows ...`. The original SDK
preset, 23 installed modules, raw selector flags, pure capture flag, annotation
import/font-library options, content-bound cloud import, TXT progress,
`EXReaderWave3` target, package checks (at least 26), archive unpacking and
relocated Windows dependency verifier remain intact.

The wrapper observes the existing shared `host_build.run` helper; it does not
replace the producer body. The **only build-command difference** is `--verbose`
when absent and native Ninja `-- -d keeprsp`. These preserve diagnostics, not
compiler/linker/feature choices. There is no forced response-file generation,
relink, provider injection or new `/MAP` option. The existing
`apps/reader/desktop/windows_feature_integration.cmake` already emits
`windows-host.map` for the final target. Empty response-file lists are explicit
when Ninja did not generate any; existing `.rsp` files are retained verbatim.

The old F06 source guard cannot admit these new paths. The new source guard is
stricter for this package: base ancestry, exact full checkout SHA, dedicated
branch, clean tracked tree, **added files only** under this new test directory,
this new workflow and this document. Every old source/test/budget/product path
therefore remains byte-identical to the common base; the SDK is also compared
with its frozen source separately.

## Retained raw material

The new same-source capture contains:

- Full `sdk-stage`, `product-stage`, and `raw-stage` installed trees: actual
  static archives, public headers, exported CMake packages and dependencies.
- The complete actual `host` build tree: final `EXReaderWave3.exe`, existing
  `windows-host.map`, host `.obj`/`.lib`, Ninja files and generated response files.
- Actual CMake cache, Ninja graph/rules, install manifests, Ninja state and every
  generated `.rsp` from each SDK/product/module build.
- `ninja -t commands` from every actual build directory, original versus actual
  build argument journal, unchanged F06 build logs and producer console.
- Raw `dumpbin /symbols` for the captured installed archives and host objects/
  libraries; `/headers`, `/imports`, `/exports`, `/dependents` for the actual EXE.
- Original new-run F06 archive, manifest, configuration, result, unpacked entry,
  payload, page image and application log, all bound to the same full source SHA,
  Actions run and attempt. Host, payload, nested archive and relocated EXE hashes
  must agree. Install-manifest entries must be present under their actual prefix.

One inner `snapshot.zip` preserves repo-relative paths and dotfiles. Its manifest
records byte count and SHA-256 for **every** file. The producer recomputes those
bindings; an independent Linux Actions job fetches the original upload ZIP,
checks GitHub artifact ID/name/run/source/attempt/expiry/size/digest against job
outputs, verifies successful upstream jobs, rejects unsafe/aliased ZIP paths,
rehashes every raw member and rechecks the nested F06 executable and identities.
It does not trust producer booleans alone. Failure retains available partial
evidence and never becomes capture acceptance.

## Gates and remaining gaps

New jobs only: protocol 10 minutes, Windows capture 100 minutes, authentication
30 minutes. No existing workflow or budget changes. The Windows timeout equals
the old standalone F06 budget; additional diagnostics must fit it, and any
timeout remains a failure rather than a reason to relax an old requirement.

`capture_complete=true` and `f06_identity_verified=true` mean only that the new
Windows evidence is complete and byte-authenticated. **`f07_accepted=false`
remains unconditional.** A subsequent adjudicator still needs to establish the
actual single SDK/product SQLite provider and audit private/undefined entries
for all installed modules against their exact public package ownership. Raw
symbol output is input to that review, not its conclusion.

Other platforms, six-platform common-source final admission, full behavioral
regression, real device coverage, shipping, signing and releases are not granted.
No existing test, product owner, migration implementation, SDK or formal total-
progress catalog is edited. No main push, PR, tag, release, Codex launch, user-PC
execution or remote repository write is part of this source-only handoff.

## First authorized Actions evidence

After approval, publish only the reviewed owned additions on the dedicated
branch. Preserve any failed attempt. Inspect the three new job results, upload
ID/digest/expiry and authenticated summary at the exact new SHA; record direct
run and artifact links here only after they exist. The first run may reveal
strict shape/path/tool-output incompatibilities; none have been tested or
presumed passing in this source-only packet.
