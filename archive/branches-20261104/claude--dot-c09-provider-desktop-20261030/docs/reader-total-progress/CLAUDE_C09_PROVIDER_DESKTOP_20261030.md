# C09: Windows/macOS final-program provider audit (F07 desktop remainder)

Branch `claude/dot-c09-provider-desktop-20261030`, exact base `441a5ae2653dcbeef7a25b3e38c7a7adee12911f`.
Additions only: `tests/reader_provider_desktop_remaining_20261030/**`,
`.github/workflows/claude_c09_provider_desktop_20261030.yml`,
`scripts/audit/claude_c09_provider_desktop_20261030.py`, this document.
No SDK, product build owner, CMake, old test or old assertion is edited. The owner recipes
(`tests/windows_sdk342/build.py`, `tests/apple_sdk342_package/run.py`) run unchanged; this package only reads
the maps and installed libraries they already produce (`host/windows-host.map`, `host/product-link.map`).

Not an acceptance document. `f07_accepted` and `full_six_platform_f07_accepted` are written `false` by every code
path, the 95/108 count is untouched, and Linux 675/672/3 weak is existing evidence that this package neither
re-accepts nor relies on.

## Result summary

| Platform | Real final-program evidence | Status |
|---|---|---|
| macOS | real `product-link.map`, real final image, real installed SDK/product libraries; audit passed with 0 findings and 7/7 negative controls rejected | **evidence collected, not complete** (pending items below) |
| Windows | real SDK/product build succeeded (OPDSHash prerequisite satisfied in cycle 2); audit then failed: my MSVC map parser selected no library members from the real `windows-host.map` | **pending, no Windows evidence; not fabricated** |
| Full F07 | needs both platforms plus the manager's review | **not accepted, remains pending** |

## Runs (repository NoGod3524/EXReader, all attempt 1; evidence binds only to its own run)

| Run | Source | Result |
|---|---|---|
| 41088611960 | `9267772b91598761759882230011808c7a9c6751` | protocol success. windows failed at build (job 124176246861): `READER_ORIGINAL_HASH_PREFIX` missing. macos audit (job 124176246520) failed: 34 `sdk_entry_without_selected_sdk_owner` plus 2 `sdk_runtime_identity_mismatch`. |
| 41090328010 | `03469a171506f41ea0eb34a4369d970437092342` | protocol success. windows failed at build (job 124182229745): prefix not canonical (mixed separators). macos audit (job 124182229895) failed: 21 `sdk_symbol_not_bound_to_sdk_runtime` (all `sqlite3_*`) plus 2 identity mismatches; 44 imports unresolved. |
| 41091277686 | `82c4a08c51ba2bfa67cb8899bb9e26609dc47eaf` | protocol success (job 124185481703, artifact 12994276425, 503 B, sha256 `2c802848...73ba`). macos success (job 124185481281, artifact 12993044119, 2807062 B, sha256 `cdf449e58c2f43bbcb0b18747c9c6ce694b24331ccf8cdefbdc5b1325bf7bfcb`). windows failed in the audit step (job 124185481790, artifact 12993253798, 8956408 B, sha256 `b4cb373476c179d93994608399c48e7d59c9e6c5778717c4f885145009a1fe76`). |

The budget was the initial run plus two diagnostic fix-and-verify cycles; all three are used. Failures are retained
above. Raw ZIPs were not downloaded or parsed locally; every statement is from plain Actions log lines.

### Why each failure happened (all my defects or missing prerequisites, none waived)

- Windows build: the unchanged GTK/Windows builders need an installed OPDSHash prefix and a canonical (forward-slash)
  path, as C05 already documented for Linux. Fixed by building `extras/opds` in the workflow and passing `cygpath -m`.
- macOS 34 then 21 findings: the SDK is a dynamic `libexreader` runtime there; unselected static SDK archives are not
  providers, so the C05 rule was a rule defect for this platform (same class as the Linux SQLite rule defect). The
  replacement rule requires every SDK symbol a selected product member references to be bound to the bundled SDK
  runtime in the final image import table; `sqlite3_*` stays with the product-owned SQLite rule.
- macOS identity mismatch: the owner recipe ad-hoc re-signs each bundled `libexreader*.dylib`, so bytes differ from the
  installed SDK file. Identity is now UUID + `__TEXT` dump + export table, with both SHA-256 values still recorded and
  `byte_identical: false` reported.
- Windows audit: `Publics by Value` lines of the real map did not match my regular expression, so zero members were
  selected. I did not see the real map text in a log, so the correct format is not established. No further run was
  allowed, so this is the blocker.

## macOS final-program evidence (run 41091277686, source `82c4a08c`)

- Final image `.../host/EXReader.app/Contents/MacOS/EXReader`, 5645760 B, sha256
  `1e8d3354f78ccd5df66fadda479ce8b9e84190d1bfb68ca95314d91558498a3e`, from the real Apple `-map`
  (`product-link.map`): 39 selected archive members, 56 archives with native `nm -m -g` tables, 62 installed
  libraries (path, size, sha256 recorded in the artifact; roles sdk/product/host).
- Provider ownership: `findings: {}`. 47 of 47 `sqlite3_*` references are resolved by the selected product catalog
  (`resolved_by_selected_product`), ProductCatalog archives `libreader_catalog.a`, `libreader_catalog_sqlite.a`,
  `libreader_original_import.a`.
- SDK runtime identity: bundled `libexreader.*.dylib` copies equal the installed SDK file by UUID,
  `__TEXT` digest and 2738-symbol export digest (status `ok`, byte-identical false because of ad-hoc re-signing).
- Dynamic imports: 1461 imports from the real image; 1460 explained against the installed SDK runtime exports or the
  macOS 15.5 SDK `.tbd` stubs (including `reexports:` symbol blocks); 42 weak imports among them.
  **Pending:** `_$s12CoreGraphics7CGFloatVMn` (weak, from `libswiftCoreGraphics`) is not in its stub closure; the
  symbol text appears only in `libswiftCoreFoundation.tbd`. Not guessed.
- Weak definitions: 94, all `coalesced_weak_definition_no_strong_definer` among selected members.
- Negative controls run on the real evidence, each raised its expected kind: wrong SDK role swap, foreign SQLite
  provider in the SDK root, duplicate provider (copy of the real SQLite owner member), missing SQLite owner, unowned
  link input, system SQLite dependency, wrong SDK runtime identity (7 of 7).
- **Pending (explicit):** 22 Swift host objects (`EXReader-1.o` ...) are deleted by the owner `swiftc` before the audit,
  so their members could not be inspected; they are covered only through the final image symbol table (SDK binding,
  `sqlite3*` definitions). `evidence_complete` is therefore `false`.

## Windows

No Windows provider conclusion exists. The unchanged owner build succeeded in cycle 2, the audit step started, and
its MSVC map parser failed closed with `MSVC map selects no library members`. Not established: installed library
identities, selected members, dynamic imports (`dumpbin`), delay-load/weak explanations, Windows negative controls
(the code exists and is synthetic-tested only). The retained Windows artifact 12993253798 contains the real
`windows-host.map`, `EXReaderWave3.exe` and CMake cache for the next owner of this work to read in Actions.
If this work continues: read the first `Publics by Value` lines of that map inside Actions, correct `MAP_LINE` in
`pd_win.py`, and rerun on a new source; do not combine it with run 41091277686.

## Self-tests

Synthetic cases in `test_pd.py` (COFF archive builder with long names/COMDAT/weak/import members, MSVC and dumpbin
text, Mach-O `nm -m` in both header styles, Apple map, `otool -L`, `.tbd` including `reexports:`, policy rules, every
negative control, dynamic-SDK filter, additions-only scope) passed in the protocol job of every run. py_compile of
every owned file ran in Actions in the protocol, windows and macos jobs; no local syntax check or test was run.

## Not claimed

Windows provider ownership; complete macOS evidence; Windows/macOS F07; six-platform F07; any change to 95/108.
