# Windows F07 — retained static ownership and private-entry audit

Independent additive source packet; **not executed or accepted yet**.
Base `8f8acf3234cba747165f001c0c96efe1b911e6ad`.
Branch `codex/reader-windows-f07-audit-20261028`.
Owned: new `tests/reader_windows_f07_audit_20261028/**`, this document, and the
matching new workflow. No SDK/product/old tests/budgets change.

## Frozen evidence, not another build

The successful capture is source `739089d782c2d76f2708446175ccd24fce3b2e3b`,
[run 40776571774 attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40776571774).
Raw artifact **12854809371**, **96047453 bytes**, SHA-256
`8fa16dfeae48214991b35231070b6842ff2720a0a4a37c1d7247980c57fec1ea`.
Capture authentication artifact **12855277110**, **4625 bytes**, SHA-256
`cdb8ae819bc03c8f7623862c08ac0a24e3139946674830ffb73efadfa6924a8a`.
Both original uploads expire 2027-01-26T22:00:39Z; expiration fails closed.

Only Actions downloads/parses binaries/archives, runs syntax/protocol fixtures,
and invokes native inspectors. No compiler, build, installation, EXE launch,
reproduction of the successful capture, or user computer is involved. The old
failed capture run 40772840276 is preserved and never credited.

The frozen successful capture validator is copied byte-for-byte under a unique
module name and SHA-256 checked against its original Git source. It revalidates
every snapshot member, actual EXE/map/final response closure and full nested F06
package/unpacked byte identity. API IDs/source/run/attempt/expiry and original
raw ZIP size/digest are pinned, not just artifact names or producer booleans.

## Ownership and unresolved boundaries

* Actual installed CMake target namespaces and exact imported archive locations
  assign package ownership, including private SDK vendor archives. Exact module
  install manifests own headers; all installed headers must be accounted for.
  A manifest spanning multiple exported packages is reported ambiguous rather
  than granting every package the whole stage's public declarations.
* COFF external, weak and C++ decorated dependencies are replayed from original
  archives and exact host inputs and compared with retained diagnostics. A
  dependency requires same-package definition or declared public API, unique
  defining package and exported dependency closure. Unknown imports fail closed;
  there is no blanket C++/CRT/helper prefix exemption.
  A direct x64 COFF/archive parser also binds each object member and weak
  auxiliary fallback target; unsupported import/LTCG/object formats fail closed.
* Host-local archives/objects have a separate WindowsHost owner. Final map
  archive-basename/member attribution resolves only against exact final expanded
  response-file inputs and rejects duplicate basenames. SDK public definitions
  must come from the SDK and the exact member defining the symbol; final sqlite3
  definitions must have one product owner. Explicit map paths cannot borrow a
  different directory's same basename; input-bearing switches are accounted for.
* The actual retained Ninja dependency databases expose header-only dependencies
  for every object in actual exported-archive build rules, and actual host inputs.
  A single observed object cannot certify a multi-object target. Explicitly private installed C++ headers never
  become public APIs merely because they were installed. Missing target/header
  coverage is a gap, not proof of absence.
  Captured CMake source roots also classify cross-package implementation includes
  (including noninstalled `.inc` files). Repository/generated dependency paths
  lacking a unique source/public owner remain explicit coverage gaps; this initial
  audit does not grant complete source-boundary clearance for those paths.
* Original MSVC/Windows SDK external static library bytes, original dumpbin
  hashes and original platform DLL bytes were **not retained**. Current-run dumpbin/Ninja
  are inspectors only. Exact observed PE imports describe dynamic edges but
  remain unverified provider findings; ordinal/unknown rows fail closed. No current-run system
  archive or all-CRT whitelist is substituted for the missing original bytes.

A second Windows job independently redownloads original capture bytes and
replays the native/manifest/map/header audit, authenticates the first audit's
raw upload and compares the complete semantic report. It distinguishes
**authenticated findings** from acceptance. A final admission step is expected
to fail: `windows_f07_accepted=false` and `full_six_platform_f07_accepted=false`
remain fixed while original external-input provenance is missing. Actual private
entry/header findings are separately recorded, never hidden behind that gap.

New budgets: protocol 10, inspection 30, independent replay 30 minutes. Existing
budgets unchanged. No main/PR/tag/release and no full behavior/device/admission
claim. Source review precedes publication; protocol tests are not native evidence.
