# C02 Apple host qualification

This candidate is executed only in GitHub Actions. It has not passed merely because
these files exist. The workflow builds the unchanged SDK 3.42 source at
8357eafa28423a7ab93ba08b823af80f01ad1505, installs the current-source C02 helper
and products, builds the production bundle, and separately runs the same
HostLibrary/HostModel sources in an instrumented native app. Each job is limited
to 15 minutes; SDK, products, and runtime use separate jobs and authenticate
same-run/attempt source and installed-file digests.

Run by dispatching dot-c02-apple-host-20261031.yml on the candidate branch.
The target matrix is macos and iphonesimulator. The simulator bundle is installed
and launched with simctl; its NSHomeDirectory is the actual application data
container. The desktop authority is derived from getpwuid(geteuid()), never HOME.
No migration package or command line may select an authority.

The runtime exercises 14 cases: model admission before SDK/catalog and explicit
create, real enrollment recovery after external kill at phase1002, unknown open,
clean SDK open, pending refusal after external kill at phase1102, missing Binding,
same-byte replaced library, last document owner, final release, independent
HostLibrary reopen, last publication owner, last fixed-page owner, fresh-process
pending refusal, and fresh-state preservation of existing SDK/catalog bytes.
The six common host adapter cases are in admission.json/cases; all additional
cases are retained in extended_cases and original per-process runtime JSON.
No report labels these host tests a complete C02 qualification.

Runtime artifact ZIP paths are rooted directly at evidence contents:
- receipt.json: source/run/attempt/platform and both executable digests.
- admission.json, observations.log: six common runtime observations plus extended
  cases and complete raw phase reports.
- runtime/PHASE/: original JSON and durable barrier markers from the app container.
- PHASE.log: native process output.
- PHASE-native-map.json: actual roots mapped to native/PHASE/authority,
  native/PHASE/libraries, and native/PHASE/model.
- native/PHASE/authority/: original authority.bin, registry.lock, and every route
  directory, binding, state, lease, enrollment, and preserved invalid fixture.
- bundles/production.app and bundles/runtime.app: actual signed bundles.
- source-files.json, build.json, production-product-link.json, runtime-link.map,
  runtime-symbols.txt, file-hashes.json: source, installation, link and file identity.

Maps are captured with open(O_NOFOLLOW|O_CLOEXEC) followed by fstat. File digests
come from the same descriptor. Every directory and file has device, inode, mode,
uid, nlink, size, and euid; regular files additionally have SHA256. Runtime Swift
records use links/bytes for nlink/size. Per-case observations also record actual
library and parent fstat identities. iOS scope_factory observations are captured
in the production factory from its actual opened descriptor, before
pc02_scope_create, and include expected/actual device and inode, mode, uid, euid
and CLOEXEC. Scope identity is independently captured, never decoded from the
native records.

The driver preserves original native directories after every process, including
failed processes. Fresh refusal checks exact native snapshots. Marker phase,
producer source and actual euid must match before Actions terminates a process.
The production application contains no review counters or barrier callbacks.
