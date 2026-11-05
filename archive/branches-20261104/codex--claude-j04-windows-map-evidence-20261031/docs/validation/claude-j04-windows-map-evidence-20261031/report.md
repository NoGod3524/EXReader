# J04 Windows MAP evidence parser — result: old parser misread (derived); package's own machine verdict is wrong

C09 stays sealed (its three runs, report and failure are untouched). This is a separate package: **one** Actions run, 41155430302 attempt 1 (commit b07b3528 on `codex/claude-j04-windows-map-evidence-20261031`), evidence artifact 13025037310 (sha256:57671b0a...59204). No rerun is permitted by the budget.

## Identity (verified in the run)
C09 run 41091277686/1, source 82c4a08c51ba2bfa67cb8899bb9e26609dc47eaf, Windows artifact 12993253798 (`c09-windows-41091277686-1`, 8956408 bytes, sha256 b4cb3734...1fe76) → entry `windows-sdk342/host/windows-host.map`, 6514500 bytes, sha256 9132c51ca3a9cd31b298505b35da67452d378c83543b9aa7bb5674287cdbe7ad, utf-8, 53496 lines, MSVC `Publics by Value` header at line 69.

## Facts established
1. The old `pd_win.parse_msvc_map` reproduces `MSVC map selects no library members` on these exact bytes.
2. Its line regex `MAP_LINE` is **not** the problem: it matches 53421 symbol lines after the anchor.
3. The `Lib:Object` column of the real map is `<archive base name without .lib>:<member>.obj`, e.g. `exr_vendor_webp:dec_clip_tables.c.obj`, `libucrt:...`, `exr_pdf:...`. The old `MEMBER` regex requires `….lib:`, so every one of them is classed as a loose object and `members` stays empty.
4. From the J04 objects output (771 distinct inputs): 750 are `name:member.obj` from 57 archive base names (libucrt 262, exr_vendor_aom 61, LIBCMT 47, exr_vendor_webp 39, libvcruntime 35, … exr_pdf 24, 14 reader_* / exr_* product libraries); 19 are DLL import stubs (`kernel32:KERNEL32.dll` …); loose items: `reader.c.obj`, `windows_wave3_bridge.cpp.obj`, `<absolute>`, `<linker-defined>`, `<common>`, `* linker generated manifest res *`.

## Verdict
**Old parser misread** (real members exist; wrong archive-name assumption). The map is neither truncated nor of an unrecognised format.

## Defect in this package, stated plainly
J04's own parser carried the same `.lib`/`.a` assumption, so its recorded machine verdict is `no_archive_members_in_map` with 0 archive members. That label is wrong. The correct conclusion above is derived afterwards from the retained J04 output text (`objects-windows-host.map.json`), not from a new parse of the artifact. A corrected parser would need a new run, which needs a new approval.

## Still not established (so C09 remains not passed)
Mapping archive base names to installed `.lib` files and identities (needs the build's LIB path/`resolve_input`), dynamic imports via `dumpbin`, weak/delay-load explanations, Windows negative controls, and any Windows provider-ownership conclusion. No Windows product or C09 acceptance is claimed.

## Addendum: corrected parser, run 41156867582 attempt 1 (commit 270b9ca2) — machine verdict now matches
Run 41156510546 (commit d0d3298c) failed on a SyntaxError in my test strings (no analysis happened). Run 41156867582 succeeded; evidence artifact 13025406603 (sha256:87513ae6...58d4c). It re-authenticated the same C09 artifact/map (map sha256 9132c51c...bdb7ad) and, with the parser now recognising MSVC archive base-name members and separating DLL import stubs:
- verdict **old_parser_misread**, reproduced old failure `MSVC map selects no library members` (old regex still hits 53421 lines);
- **750 archive members from 57 archives** with source line numbers (`members-windows-host.map.json`), 15 import stubs, 6 loose/linker-generated inputs, 65 unrecognised lines retained (headers/section tables);
- 10 controls pass (4 synthetic positives incl. base-name form, 6 negatives incl. truncated, garbage, loose-objects-only, import stub, unrecognised map ≠ pass).
This supersedes the mislabelled machine verdict in the first run (kept above). Runs used by J04: 3 (first run, failed syntax, corrected). Still not established: mapping archive base names to installed `.lib` identities, dumpbin imports, weak/delay-load explanation, Windows negative controls; C09 and the Windows product remain not accepted.
