# Original import public streaming-hash boundary (2026-10-29)

## Scope

Owner-approved isolated sixteen-path implementation: eight production files in
OPDSHash/ProductCatalog and eight additive acceptance files. Base
`8f8acf3234cba747165f001c0c96efe1b911e6ad`; feature branch
`codex/reader-original-hash-boundary-20261029`.

The original importer is cross-platform. This removes its unconditional private
OriginalExport `sha256.inc` include on every platform. The installed independent
`EXReaderOPDSHash` 0.1.0 package reuses the existing OPDS SHA algorithm, with no
second constants/implementation, network/SDK dependency, or generic OPDS helper
exports. Four public stream functions wrap bounded opaque context state; three
owner-unique implementation functions cannot resolve to the Revisions helper.
Normal OPDS compilation remains unchanged. Revisions/ReadingState are not edited.

Importer read loops remain 65,536 bytes, retain positive <=INT64_MAX input size,
callbacks, handle checks, copy verification, no-replace publication, staged
recovery, and verified Windows handle sharing. Provider MEMORY/ARGUMENT/STATE map
to ROI_MEMORY/ROI_ARGUMENT/ROI_IO through a noncopyable RAII adapter, including
boolean verification paths. Message length overflow is rejected before mutation;
final bit length preserves the prior unsigned modulo-2^64 encoding. No huge-file
runtime correctness claim is made.

## Explicit dependency prerequisite

Build/install `extras/opds` with `EXREADER_OPDS_HASH_ONLY=ON` into a fresh prefix,
then provide canonical `READER_ORIGINAL_HASH_PREFIX` or process-scoped
`EXREADER_ORIGINAL_HASH_PREFIX` to ProductCatalog and installed consumers. Both
selectors, if present, must agree. Existing builders can inherit the process hook
even when they overwrite CMAKE_PREFIX_PATH. No original build script is changed;
unprepared old configurations now honestly lack a required dependency.

Exact-version package discovery is restricted to the chosen config directory.
The imported target's origin, static type, canonical archive/include paths and
usage requirements are checked on initial and repeated discovery. Relocation
selects the relocated hash prefix, not a recorded producer path.

## Acceptance and limits

All execution is GitHub Actions-only. The new workflow runs scope/parser controls
and six separate target producers (Windows, Linux, macOS, Android x86_64 API26,
iOS arm64 device and simulator), each capped at35 minutes with4 build workers.
Authentication is20 minutes; protocol10. This does not change old workflow
budgets or rerun the old successful F07 capture. No SDK build is required.

Desktop jobs execute unchanged catalog tests and `original_import_actions.py`:
16,792,975 bytes, SHA256
`4f45393b25817f506a51b56cc5d61599556e4dd5b0bd59aa00f7eb43cbfc0a86`,
duplicate/cancel/crash/recovery/corruption and Windows same-handle checks. New
stream controls compare fragmented known vectors against normal OPDS and Python
hashlib, allocation/lifecycle/overflow controls, and real-importer fake-provider
fault mappings. Test-only fake provider/internal source inclusion is isolated
from installed production probes and never accepted as production provider proof.

All targets require installed-only final consumer links plus relocated links,
both archive orders with normal OPDS and the unchanged actual Revisions helper,
actual archive/member bytes and native symbol outputs, original Ninja commands,
response files, maps, imported target paths, install manifests and exact relevant
object dependency records. Missing relevant dependencies fail. Unrelated zero-
dependency groups are not credited as source coverage. Mobile evidence is
compile/final-link only: no emulator/device runtime is claimed.

Package controls reject missing/wrong/conflicting prefixes, foreign pre-created
targets, changed target usage requirements and incompatible-machine archives.
Independent authentication downloads original same-run artifact ZIPs in Actions,
checks API digest/size/source/attempt and all nested file hashes, and replays the
semantic contract. Safe extraction rejects aliases, links, traversal and
file/directory collisions (2GiB/member,8GiB total fail-closed limits).

This narrow boundary does not establish full F07, fix SQLite final-provider
ownership, clear other private dependencies, prove original system toolchain/DLL
bytes, or establish mobile behavior. `f07_accepted` and `full_six_accepted` remain
false. Historical authenticated Windows failures remain immutable.

## State

Authored source pending independent whole-packet review and first Actions run.
No local builds, syntax checks, tests, fixtures or native/artifact parsing run.

The Android binary discriminator also reads the actual ELF Android ABI note
(API26), in addition to target driver/sysroot/cache flags. It follows the
[platform CRT note layout](https://android.1.googlesource.com/platform/bionic/+/6aa3bdfb161af9c190df44efa1c3160fc6b71314/libc/arch-common/bionic/crtbrand.S).
A small host-Linux ELF negative is compiled only in the Android producer and
coherently substituted into a copy of evidence; matching x86_64 ELF headers alone
must not pass. This is not system-toolchain provenance or Android runtime proof.

## First actual run and bounded validation follow-up

Original source `3597b549340450929c693c31fd3d2f7bf254bbf6`, run
[40813101185](https://github.com/NoGod3524/EXReader/actions/runs/40813101185),
attempt1: protocol passed; Linux producer passed the narrow boundary and desktop
behavior with559 retained files. Its raw upload12870588607 is15,257,921 bytes,
SHA256 `dcf81f2f1fe4dda46cdd90cb3782d62850f306bb86f23ae73e6288580d8ba063`.
The aggregate failed and did not independently authenticate all targets.

Windows completed its build/runtime/control stages then failed on DUMPBIN's
parenthesized display annotation after a decorated C++ linkage name. Android and
both iOS targets built and installed the two new owners but failed the unchanged
Revisions helper's cross-root ProductCatalog package lookup. The bounded runner
repair selects the exact same-target installed ProductCatalog config directory;
no old owner is changed. The COFF parser keeps the actual decorated linkage name
and permits only a bounded parenthesized display suffix on C++-decorated names.

macOS failed the strict exact built-vs-installed archive byte comparison. No
cause or allowance is inferred. Commit marker `[hash-archive-diagnostic]` runs
protocol plus a pinned-original diagnostic only; all six producers and normal
authentication are skipped. The diagnostic authenticates original macOS upload
12871351856 (15,151,587 bytes, SHA256
`ff875ece2f5d27128a83798f0309f237a72daeb5997ab5118fe8f0794fe03b16`), original
source/run/failed job and unchanged owner bytes before extracting in Actions.
It reports complete archive member payload identities and raw header/index
records, total byte difference count and explicitly bounded offset preview.
Only its JSON report is uploaded. The original equality guard and all admission
requirements remain unchanged. No native build is repeated by this diagnostic.

## Authenticated archive difference and explicit bounded criterion

The no-build diagnostic [40814640832/1](https://github.com/NoGod3524/EXReader/actions/runs/40814640832)
at `531f10863f7395d2601317262fca3d78094b952b` passed protocol and original-upload
inspection; all native producers and normal authentication were skipped.
Diagnostic artifact12871463973 is1429 bytes, SHA256
`1e8282c6b5fb797532b251da28580f2e767542b04bc2729e3fec88b17c236568`.
The original importer pair has31840 bytes in both files and differs at exactly
offset33: first BSD index-header timestamp1793245046 versus1793245047. Index
payload and the30736-byte `original_import.cpp.o` payload are byte-identical.
The4728-byte hash archive is completely identical. This identifies the bytes,
not the particular ar/ranlib invocation that changed them. The first diagnostic
did not expose the decoded index name; the next pinned replay must prove it.

The owner explicitly authorized a NEW narrow validation criterion on2026-10-29,
not a change to old suites or a broad archive metadata exemption. On macOS only,
a pair may differ solely in the canonical12-byte timestamp field of the first
BSD extended-name index, whose decoded name must be exactly `__.SYMDEF` or
`__.SYMDEF SORTED`. Canonical numeric/name/alignment/padding checks reject malformed
or duplicate index headers. All other bytes—including index content, UID/GID,
mode, member names/order, object timestamps, object payloads and padding—remain
exact. Linux, Windows, Android and both iOS targets still require entire-archive
byte equality. [LLVM's archive reader](https://llvm.org/doxygen/Object_2Archive_8cpp_source.html)
documents these reserved BSD index names; its
[writer](https://www.llvm.org/docs/doxygen/ArchiveWriter_8cpp_source.html) distinguishes
timestamps from payloads. This format reference does not identify the producer's
actual tool binary.

Both original file hashes, lengths and bytes remain retained. The comparison
hash is labeled and computed in memory only; it never replaces an original hash
or rewrites a file. The result exposes exact equality versus timestamp equivalence,
the decoded index name, original timestamps and every permitted differing offset.
Exact installed member/object/compile-dependency, native symbol, final link/map,
relocation and runtime bindings remain required. Synthetic malformed-header,
unknown/duplicate-index, membership/order, index-content/object-content, nonmacOS,
numeric/alignment/padding and truncation controls run only in Actions. Two actual
macOS evidence mutations alter built index content and object content separately;
they must reach the intended rejection and restore originals byte-for-byte.

The next run retains `[hash-archive-diagnostic]`: protocol/adversarial controls
and the same authenticated failed-original ZIP only. It must expose the actual
known index name and bounded equivalence. Old failed source/run remains failed;
accepted/full-F07/full-six stay false. This is not a fresh native build or full
same-source target acceptance; that requires a separately authorized later run.

## Second full run: partial passes, three original unknowns

Full run [40816180401/1](https://github.com/NoGod3524/EXReader/actions/runs/40816180401)
used source `1198abce384aabe78bc23450db0c38be487706e1`, exactly the reviewed tree
`1452cab6ff071efa5a3bdedc790adee5adacde15`. Linux and macOS passed boundary plus
desktop runtime; iOS-device passed installed-only final-link/member/dependency
proof (no mobile runtime). macOS's actual index-content/object-content mutation
controls passed. Its current archive pair was exact; the older unequal pair
remains separately authenticated. Aggregate failed because three producers failed.

Windows now refuses a weak COFF external; the original log does not identify its
row/fallback. Android now refuses an unclassified linker-escape operand. iOS
simulator now refuses entire-archive inequality, correctly retaining the
macOS-only normalization rule. No weak-symbol, Android escape or simulator
criterion is relaxed from these messages alone.

`[hash-retained-diagnostic]` skips all native producers, normal authentication and
the earlier archive diagnostic. A new no-build job pins all six original upload
IDs, sizes and SHA256 digests, exact source/run/attempt and original job results.
It authenticates original failure ZIPs before printing every retained weak-row
context plus advertised fallback-row candidates, the exact final Android linker
commands/response identities and existing binding failures, and both simulator
archive/index/object identities and precise differing offsets. These are
unadmitted diagnostics, never fallback-symbol ownership or simulator acceptance.

The same job independently replays the three original green producers using the
EXACT historical `package_contract.py` and `test_contract.py` bytes from commit
1198abce. The historical16-path scope and all retained source records are verified
against Git; all eight current owner files must still equal that source. A narrow
historical identity/guard binding uses the original SHA/run/attempt and checked
source inventory, not current-source identity. Original ZIP/nested hashes,
complete file inventory, every native proof predicate and actual-evidence
mutation controls run unchanged. It compares the result with the original
producer result. Each green target is reported explicitly under
`independently_replayed_original_green`; overall accepted/full-six/full-F07 stay
false. Original iOS-device proof remains compile/final-link only.

Only the new diagnostic JSON is uploaded, not original ZIPs or unpacked files.
API/parse/replay errors are retained as failures with any already established
partial results; the job remains failed unless all planned diagnostic/replay
parts finish. This run cannot relabel old artifacts as fresh-source native proof
and performs no native build or test executable invocation.
