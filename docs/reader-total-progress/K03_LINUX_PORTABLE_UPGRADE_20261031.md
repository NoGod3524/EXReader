# K03 — real Linux portable A -> B update and user library retention (2026-10-31)

## Scope and authorization
Owner: Claude. The user approved every item of the K03 package in this conversation: branch
`claude/k03-linux-portable-upgrade-20261031`, commit and push from the local Git/gh route on this device, the
push-triggered workflow, the Actions budget (Linux build/package/UI matrix 150 min, independent evidence check 20 min;
one initial run plus at most one targeted correction), and fetching this package's CI metadata and artifacts, including
the A artifact below. No build, test, fixture or ZIP parsing ran locally. Formal ledger 95/108 unchanged.

Only three new paths (enforced by the workflow against 8232e91cd7b9296dfcdd3096b96317eb3fa1008a):
`tests/gtk_portable_upgrade_20261031/`, `.github/workflows/claude-k03-linux-portable-upgrade-20261031.yml`, this document.
No production code, SDK, old test, C02, `tools/reader_wave3_package/delivery.py`, J01/J02 material is changed.

## Fixed inputs
- A (old package, consumed byte-for-byte, never rebuilt): artifact 12811449234 `f06-linux-40678657371-1`, run
  40678657371 attempt 1 (workflow "SDK 3.42 same-run aggregate admission", which calls `gtk-sdk342-package.yml`),
  source 8f8acf3234cba747165f001c0c96efe1b911e6ad, 18545727 bytes,
  sha256:be3a91161939b3b61bce041feaa06679d03120af9f53abea02bab141d5665641. The outer ZIP size/digest, the inner manifest,
  archive digest, every file and SHA256SUMS are re-checked with the shipped `unpack.py`; the inner manifest's source
  SHA must be 8f8acf32.
- B (new package): product tree 8232e91c (only the three test paths differ), built in the same job by the unchanged
  recipe that produced A: `tests/gtk_sdk342_package/run.py build` (explicit SDK 3.42.0, real GTK build dependencies,
  original raw/legacy checks, F06 packaging and entry verification). That recipe, `tools/build_linux_host.py`,
  `tools/reader_wave3_package/*` and `tests/reader_f06_packages/identity.py` are byte-identical between 8f8acf32 and
  8232e91c. The recipe's own source guard pins an older base and is not run; this workflow's path guard replaces it.
  After packaging the B build tree is moved away so nothing can resolve into it.
- Fixtures: an EPUB from `tools/run_benchmarks.make_epub`, a PDF from `tests/linux_host/generate_fixed.pdf`, one UTF-8
  TXT; names with spaces and non-ASCII characters.

## Method
Every product launch runs the package's own `EXReader-Linux/Start-EXReader.sh` with no arguments (wrapped only by
`stdbuf -oL` so the host's own STATUS stdout is line-buffered), from an unrelated working directory, with isolated
`XDG_DATA_HOME`/`XDG_CONFIG_HOME`/`XDG_CACHE_HOME`; the default profile is therefore `$XDG_DATA_HOME/exreader`.
The explicit `FONT STATE_DIRECTORY` path is never used. A and B are unpacked side by side under
`K03 程序 目录/A 旧版 EXReader` and `.../B 新版 EXReader`. Input is real X11 keyboard/mouse (xdotool) under Xvfb+Openbox;
observation is the host's STATUS lines, AT-SPI (accessible tree, status label, bookshelf rows), screenshots, `/proc/PID`
(exe path and hash, argv, cwd) and, only after the writer exited, read queries on scratch copies of the profile
(an untouched copy of every snapshot is kept). The database is never modified by the test.

Matrix (each item recorded passed / failed / blocked with raw observations):
1. A first run in a clean environment through the no-argument launcher; process exe = authenticated A entry.
2. Real UI profile: import PDF, TXT, EPUB; page forward; add a note; change Font size in Reading settings; create a
   shelf and classify the book in Library collections.
3. Close A; closed-state backup of the whole profile directory; record the library `user_version`, tables, book source
   hashes, notes, shelves, preferences.
4. B from its own path opens the same profile: same last book and page, three shelf rows, process exe = B entry.
5. B pages forward, adds its own note, closes; books (ids, original hashes), A's notes, shelves and settings retained;
   B reopens with a new PID and no duplicate import.
6. Program paths with spaces/non-ASCII, unrelated CWD, packaged font/dependencies (no build tree in `ldd`), no data in
   program directories or the CWD.
7. A launched on the profile while B runs: the profile lock (`library.sqlite.product.lock`) refuses the second writer
   with a visible message; B closes cleanly and its data is complete.
8. A damaged synthetic B copy (program file removed) fails to start; A, B and the profile are unchanged; the good B
   still opens. No signature verifier is claimed.
9. B is SIGKILLed by its own PID after a confirmed note and an unconfirmed page turn; reopen keeps every previously
   committed record; whether the last note and page survived is recorded, not assumed. Not a power-loss proof.
10. The pre-update backup is restored into a new isolated directory and opened by the original A: same books, notes,
    last book and page. The updated profile is kept as evidence.
11. Repeated A -> B -> B on an independent profile: no duplicate or changed books.
12. Moving the B program directory and deleting a synthetic copy keeps the profile; B from the moved path opens it.
No uninstaller or user cleanup is run. Not run: handing the B-modified profile back to A (no downgrade contract, not
promised; backup restore is item 10) and cross-schema migration (A and B record their actual `user_version`).

The independent job re-derives the conclusions from the uploaded evidence only (file hashes, process records, A/B
identity, and its own reads of the profile copies), without the driver's pass/fail.

## Status
Initial run 41174389797 / attempt 1 (a0542af3561470d6dbaa1639b71049129da3dd46): failed in "Build B" at
`raw-product-configure` — `apps/reader/store/native/CMakeLists.txt:91` requires READER_ORIGINAL_HASH_PREFIX or
EXREADER_ORIGINAL_HASH_PREFIX (installed OPDSHash), a dependency added between 8f8acf32 and 8232e91c that the A-era
recipe does not stage. No B package was produced and no UI item ran; that run's artifacts are kept unmodified.
Single targeted correction: the workflow stages OPDSHash from this same tree (`extras/opds`, `EXREADER_OPDS_HASH_ONLY=ON`,
canonical prefix, as `dot-integration-candidate-20261031.yml` does) and exports the prefix before running the unchanged
recipe. No recipe, product or guard change.

Correction run results, artifact IDs and digests are appended below. Scope of any result: F12 Linux portable
update slice only — not F11, not six-platform F12, not formal release or signing, not licensing/documentation.
