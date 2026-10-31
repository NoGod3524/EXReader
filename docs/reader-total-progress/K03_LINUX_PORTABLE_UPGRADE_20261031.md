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

The user then lifted the correction limit for this conversation.

Run 41174578730 / attempt 1 (b6c2d31151677fdff3a0a81e7231415d1360c32b): B built (SDK 3.42.0, entry
69c2ceac…50e5; A entry e87554e6…9673, SDK 3.42.0); item 1 passed; items 2 and 11 failed with "never idle" after the
first import (book=1 imported, last STATUS busy=1), the rest blocked. Cause (driver): after a frame the host queues the
position commit and clears busy in `state()` without printing a STATUS line (reader.c READER_COMMIT branch), so the
STATUS busy field is not an idle signal. Correction 2: idle is a quiet-stdout window, and a reading key rejected with
"Reading operation in progress" is repeated. No product change.

Run 41175145440 / attempt 1 (48a3643978a2bc0c850598777986864d3f87ed9a): B built and installed again with the same
entry hashes; the driver did not start — a SyntaxError introduced by correction 2 (a bytes literal split by a raw
newline). No UI item ran. Correction 3 restores `b'\n'`.

Run 41175497127 / attempt 1 (d59c1276b69cb7a9e4cfc94854fd0307c40a2971): driver ran. Items 1-6, 10 and 11 passed;
items 7, 8, 12 failed and item 9 passed vacuously. Observations: the second writer *was* refused, but the host reports
every library-open failure as code 3 "Could not open library or font" (the "already in use" text is only inside the
error struct), so the test's expected message was wrong; the failed assertion then skipped closing the running B, whose
flock on `library.sqlite.product.lock` made later launches (items 8, 9, 12) fail with `book=0`. Item 9's "passed" is
therefore not accepted: it reopened a locked profile. Also noted: A and B both resume with the status "Position not
unique; saved chapter offset shown, original point retained" (a product message, identical in A and B).
Correction 4 (driver only): item 7 asserts code 3 + the same text visible in the label + the raw kernel flock holder
(`/proc/locks`: only the writer PID holds the lock, none after it closes) and always closes the second process; item 9
now requires the library to reopen with the original book, the pre-kill note to be confirmed and to survive; item 5
requires the shelf in the UI to list exactly three books after reopen; items 8 and 12 carry explicit messages.

Further results are appended below. Scope of any result: F12 Linux portable
update slice only — not F11, not six-platform F12, not formal release or signing, not licensing/documentation.

## Result
Run 41176158414 / attempt 1 (1d30c8111e6a0ac75f3ea35ff305fbcf034477a0), after four driver/workflow-only corrections
(attempts 41174389797, 41174578730, 41175145440, 41175497127 are kept as the failure history above): success.

| Job | ID | Result |
|---|---|---|
| Real A -> B GTK matrix | 124464039211 | success |
| Independent evidence check | 124465363916 | success (`accepted: true`, no findings) |

| Artifact | ID | Bytes | Digest |
|---|---|---|---|
| k03-evidence-41176158414-1 | 13032718240 | 449856 | sha256:b11adb294ec8371a3b1a3d145f2d615ef2146686a0b9ba2cd8b26228e12745c5 |
| k03-b-package-41176158414-1 | 13032907739 | 18573921 | sha256:8501bb5fa5152af3ace135e354586aac484ceecc82a8d25850b82276f5b54d08 |
| k03-independent-check-41176158414-1 | 13033012644 | 1102 | sha256:2de51c22912b08f44191b6c82cf2fcf7cb3378a7769eb2b725cea4e1030d39d0 |

Identity: A source 8f8acf32…, SDK 3.42.0, entry sha256 e87554e64e2eea23f6b81b004c8fe17f6657ec64d4a64906292969f165e29673;
B source = the run SHA on product baseline 8232e91c, SDK 3.42.0, entry sha256
69c2ceac39b5d2b03997a49bae309637c8eb56d07894b043f6e3cd64d14150e5 (different binaries). The profile written by A
reports library `user_version` 7; A and B are the same SDK/schema generation, so this is a program-path update, not a
schema migration.

Per item: 1-12 passed (summary passed 12, failed 0, blocked 0); not-run: B-modified profile back into A (no downgrade
contract; promised nowhere) and cross-schema migration (no older-schema source authorized).

Proven: both packages run through the unmodified no-argument launcher from a space/non-ASCII path and an unrelated CWD
with the default profile under the isolated XDG_DATA_HOME; a profile built by real UI input in A (PDF, TXT, EPUB, page
position, note, font setting, shelf with a member) is reopened by B at the same book and page with the same three
original-byte hashes, the A note, shelf and setting; B's own edit survives close/reopen with no duplicate import (UI
shelf lists exactly three books); the profile flock (`/proc/locks`) lets only one writer in and the second process shows
the refusal; a damaged B copy exits 127 without touching A, B or the profile; B SIGKILLed by PID keeps the
confirmed pre-kill note and reopens; the pre-update backup opened by the original A matches; a repeated A -> B -> B on
an independent profile adds nothing; moving/removing synthetic program directories leaves the profile intact.

Not proven / not claimed: cross-schema migration; downgrade; power-loss durability (SIGKILL only); signature or
auto-update machinery (none exists); other distributions (Ubuntu 22.04 runner only); release/signing; F11; other
platforms. Observations for the product owner, not defects fixed here: the host reports every library-open failure as
code 3 "Could not open library or font" (the specific "already in use" text is not surfaced), and both A and B resume
with "Position not unique; saved chapter offset shown, original point retained".

Next owner: fixed inputs are A artifact 12811449234, source 1d30c811…, the three artifacts above. Re-check offline:
`python3 -I tests/gtk_portable_upgrade_20261031/check.py <k03-evidence>/evidence --report check.json`.
