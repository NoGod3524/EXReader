# EXReader handoff acceptance — 2026-10-29

The fixed 108-item catalog remains **95/108** at accepted run [40928834086 attempt 2](https://github.com/NoGod3524/EXReader/actions/runs/40928834086/attempts/2), source `5d4ec0ebd94fa3fabbf19af016073aef2877ac20`. Foundation 12/12, host 82/84, final 1/12. Independent host outcomes and final common-source outcomes retain separate scope.

The original annotation candidate `622b9558f79eda07211e15c51bffcd728da6c553` in [40923468266](https://github.com/NoGod3524/EXReader/actions/runs/40923468266) has completed. macOS passed all 39 native cases and is already independently accepted. Both mobile hosts failed the four-minute annotation test; each host's base, reading/navigation, search and real OS-theme suites passed. Those failures remain unmodified.

Mobile repair candidate: `55ec49020383ef5073f47502b300ab0b5d0a7cae`, branch `codex/apple-mobile-annotations-handoff-20261029`, [40935165396](https://github.com/NoGod3524/EXReader/actions/runs/40935165396). It changes native picker/tap helpers, using file cells and handling hidden extensions. All five feature test bodies and the original native driver must remain byte-identical to the failed source. It receives no completion credit before finished producer results and independent verification.

`tools/reader_composition/apple_annotation_handoff_independent.py` prepares that independent verification. It requires explicit producer source, run, job and archive ID/size/digest, authenticates the original archive, rereads all 39 xcresult cases, rehashes five retained programs, verifies original screenshots and actual dark/light commands, and checks all five feature test bodies plus the full driver against the failed baseline. It runs only in Actions. No pending run has been substituted for acceptance.

Parallel mainline work is isolated: the Apple SDK 3.42 host driver must use actual 3.42 inputs and preserve existing product changes; Windows migration qualification must resolve three remaining file-handle lifecycle failures without weakening original checks. Their source changes receive their own source-bound validation.

No default-branch merge, PR, tag or Release is part of this handoff. Builds, syntax checks, fixture generation, benchmarks and artifact parsing remain Actions-only.
