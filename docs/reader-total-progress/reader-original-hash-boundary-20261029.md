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

## Original replay established; bounded three-cause validation repair

No-build diagnostic [40817738583/1](https://github.com/NoGod3524/EXReader/actions/runs/40817738583)
at `d5849d5e0403bae53d4c12680fcd17041bd71ce3` authenticated and independently
replayed the original Linux/macOS desktop-boundary and iOS-device link-only
proofs with their unchanged historical verifier and actual-evidence controls.
Its report upload12873605336 is4762 bytes, SHA256
`9b27626f2c78c812da265d119f74418ae9cf8e41268b2beec133f29f840ecd55`.
This is partial original-source acceptance, not current-source/full-six acceptance.

Three actual retained facts now replace the generic failures:
- Windows importer has exactly three observed `WeakExternal` vector-deleting
  destructors for `std::exception`, `std::bad_alloc` and
  `std::bad_array_new_length`, with printed `No library search` fallback indices
  pointing to same-object scalar-deleting strong functions. Text alone is not
  enough: the new predicate requires ordinary x64 COFF symbol/auxiliary bytes,
  exact observed name pairs, zero/UNDEF function weak shape, characteristic1,
  reserved-zero auxiliary bytes, a nonauxiliary target index, one exact strong
  function definition in retained executable code-section bytes, and exact
  DUMPBIN index/name/section/auxiliary agreement. Unknown pairs, public/hash weak
  entries, missing/weak/data/out-of-object fallback, library search, aliases,
  cycles, malformed bounds and missing text rows remain rejected. Weak names
  remain classified as imports and cannot grant public function exports. The
  result proves fallback availability only; an already-linked override/final
  CRT provider is NOT established. Microsoft's
  [PE/COFF auxiliary-format specification](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format)
  supplies the structural basis. No runtime/library flags are changed.
- Every Android final command contains exactly
  `-Xlinker --dependency-file=CMakeFiles/probe.dir/link.d`. Only that literal
  relative output pathname in that exact operand form is newly classified, at
  most once. No parent/absolute path, alternative tokenization, duplicate,
  appended library option, target/sysroot escape or other linker escape is
  admitted. Driver/target/API/sysroot/runtime and exact input/map/image bindings
  remain mandatory. [CMake documents linker-generated dependency outputs](https://cmake.org/cmake/help/v4.0/variable/CMAKE_LINK_DEPENDS_USE_LINKER.html);
  no toolchain setting is disabled or changed to suppress the evidence.
- Simulator importer31712-byte build/install archives differ at offset33 only:
  first decoded `__.SYMDEF SORTED` timestamp1793247040→1793247041. The928-byte
  index body and ordered object payloads are identical; its hash archive is exact.
  The proposed explicit criterion extension is only to measured iOS-simulator,
  with the identical strict first-index parser and all outside-field bytes exact.
  iOS-device/Android/Linux/Windows remain full-byte-equality targets. Original
  archive hashes are retained; no rearchive or source/budget change occurs.

The next diagnostic reuses the same pinned originals and historical green replay.
It must prove actual COFF binary/auxiliary/text binding, classify the exact six
Android output operands, and validate the precise simulator equivalence. Original
predicate failures and new bounded predicate results are separate fields. Pure
COFF adversarial controls reject malformed/auxiliary/self/weak/data/private/hash
fallbacks and library-search modes; original object memory mutations separately
exercise library-search/self-fallback rejection. Actual Android command mutations
inject foreign output/library spellings and must fail. Actual simulator index
content mutation must fail outside the timestamp allowance. All originals remain
unchanged, overall acceptance stays false, and the diagnostic performs no native
build or executable invocation. A later full native run requires separate approval.
# Bounded Windows common-data classification (retained replay first)

Retained diagnostic `40820419048/1` at
`55ea5761ab8dacfd57fb1922bd618ef38271a1b3` preserved five strict common-symbol
refusals: four normal OPDS objects and one Revisions OPDS helper contain
`?_OptionsStorage@?1??__local_stdio_printf_options@@9@9`. The original upload
hashes and failed run remain unchanged. Three importer weak fallback bindings,
six Android final-command checks, and simulator timestamp/index controls passed
in that diagnostic; this was not native or all-six acceptance.

The new classification is **data only**, restricted to normal/Revisions roles.
It requires the exact decorated name, an ordinary x64 COFF record with external
storage class 2, section 0, value/size 8, type 0 and zero auxiliary records, and
matching DUMPBIN index/name/value/nonfunction text with complete row inventory.
No function, public API, undefined import or final-provider credit is granted.
Other common names, sizes, types or owners are rejected, including every public,
private and legacy hash name. This follows Microsoft's distinction between an
undefined reference (zero value) and common-data size (nonzero value) in its
[PE/COFF specification](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format).

New Actions-only controls cover wrong name/size/type/storage/section/auxiliary,
duplicate/missing/text-mismatched records, hash-owner and hash-API substitution,
and attempted function-map credit. The pinned-original diagnostic separately
reproduces the historical refusal and mutates each actual common record's size,
function type and owner. Original source identity is never relabeled current;
old failures and raw hashes remain retained. No production, SDK, budget, old
test or workflow change is part of this four-validation-file repair.

## Pinned second-full-run dependency diagnostics (no native rebuild)

The same-tree full run `40821799960/1`, source
`900366e7d91b973f13fe2e52945d25742e0bee71`, passed five producer jobs:
Linux/macOS desktop behavior and Android/iOS-device/iOS-simulator installed-only
link evidence. Windows advanced beyond symbol checks, then failed the exact
object-key dependency coverage predicate. The ordinary aggregate stopped at its
unchanged upstream gate. Five green producers alone are not independent admission.

The new `--dependency-diagnostic` profile pins that run, protocol/six job IDs,
all six original upload IDs, sizes and SHA256 digests. Existing original transport,
historical sixteen-file source reconstruction, unchanged owner-byte checks and
exact historical verifier/mutation replay authenticate the five original green
uploads first. The earlier `--retained-diagnostic` profile remains available.

Failed Windows diagnostics bind retained Ninja output to its exact original
command and hash, compare the actual archive build rule/object list, and bind
the original build directory to retained CMake cache. They retain exact expected
and observed keys, dependency status/count, object hashes, missing keys and
bounded lexical comparisons/collisions. Lexical matches are observations only:
no separator/case/alias acceptance, status waiver or coverage predicate changes.
Unsupported format or identity mismatch still fails with partial JSON retained.

The existing `[hash-retained-diagnostic]` marker now selects this pinned profile.
It still skips all native producers, ordinary authentication and old archive
diagnostics, and uploads only `diagnostic.json`. Overall/current-source, six-target
and F07 acceptance flags remain false. This three-file workflow/auth/document
change does not alter production owners, parser criteria, tests or budgets.

## Measured Windows separator-only object identity repair

Pinned replay `40823790866/1` at
`7a4ebd7ac16a8e99a0ffe8a7a7bee84db294200e` independently authenticated all five
green `900366e7` producers. Both Windows archive rules use backslash relative
object names; Ninja dependency groups use the same case-sensitive names with
forward slashes. Their one-to-one groups are VALID with four hash dependencies
and three importer dependencies. Object hashes and original commands/cache
were retained; there were no canonical collisions. No coverage was granted then.

The four-validation-file successor changes only this measured identity rule:
Windows relative object spelling may replace backslash with forward slash.
Empty/dot/parent/absolute/drive paths, case changes, duplicate normalized spellings
and case-ambiguous keys are rejected. Expected archive-rule objects and observed
dependency groups remain one-to-one, with original spellings retained. The VALID,
advertised row count, exact compiled-source/public-header checks and unique
object-byte-to-archive-member binding remain required. Retained object files must
match the exact declared build directory and object path after separator mapping.

Synthetic controls cover separators, collisions, case, traversal/absolute paths,
stale groups and truncated counts. Actual evidence mutations add separator
collision, STALE, missing dependency row and altered compiled object bytes to the
existing private-include/missing-object/member/provider controls. They must fail
at their intended guards, not merely at a changed inventory hash.

Before another native build, the pinned diagnostic replays the repaired current
contract and mutation controls over the original failed Windows upload under its
historical source identity. Its inventory is explicitly reconstructed from that
authenticated ZIP: it is **not** an original completed producer manifest and does
not admit Windows, current-source native evidence, six targets or F07. The five
green uploads still use the unchanged historical verifier. All original failures,
raw ZIP hashes and object spellings remain retained. Owners, workflow, old tests,
SDK, build flags and budgets are unchanged by this repair.
