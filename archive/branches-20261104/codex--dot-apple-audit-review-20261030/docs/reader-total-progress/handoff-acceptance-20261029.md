# EXReader handoff acceptance — 2026-10-29

The fixed 108-item catalog remains **95/108** at accepted run [40928834086 attempt 2](https://github.com/NoGod3524/EXReader/actions/runs/40928834086/attempts/2), source `5d4ec0ebd94fa3fabbf19af016073aef2877ac20`. Foundation 12/12, host 82/84, final 1/12. Independent host outcomes and final common-source outcomes retain separate scope.

The original annotation candidate `622b9558f79eda07211e15c51bffcd728da6c553` in [40923468266](https://github.com/NoGod3524/EXReader/actions/runs/40923468266) has completed. macOS passed all 39 native cases and is already independently accepted. Both mobile hosts failed the four-minute annotation test; each host's base, reading/navigation, search and real OS-theme suites passed. Those failures remain unmodified.

Mobile repair candidate: `55ec49020383ef5073f47502b300ab0b5d0a7cae`, branch `codex/apple-mobile-annotations-handoff-20261029`, [40935165396](https://github.com/NoGod3524/EXReader/actions/runs/40935165396). It changes native picker/tap helpers, using file cells and handling hidden extensions. All five feature test bodies and the original native driver must remain byte-identical to the failed source. It receives no completion credit before finished producer results and independent verification.

`tools/reader_composition/apple_annotation_handoff_independent.py` prepares that independent verification. It requires explicit producer source, run, job and archive ID/size/digest, authenticates the original archive, rereads all 39 xcresult cases, rehashes five retained programs, verifies original screenshots and actual dark/light commands, and checks all five feature test bodies plus the full driver against the failed baseline. It runs only in Actions. No pending run has been substituted for acceptance.

Parallel mainline work is isolated: the Apple SDK 3.42 host driver must use actual 3.42 inputs and preserve existing product changes; Windows migration qualification must resolve three remaining file-handle lifecycle failures without weakening original checks. Their source changes receive their own source-bound validation.

No default-branch merge, PR, tag or Release is part of this handoff. Builds, syntax checks, fixture generation, benchmarks and artifact parsing remain Actions-only.

## Active source-bound runs

- Mobile annotation producer [40935165396](https://github.com/NoGod3524/EXReader/actions/runs/40935165396), source `55ec49020383ef5073f47502b300ab0b5d0a7cae`: both SDK builds passed; three native hosts started. Source review separately confirmed all five feature test bodies are identical to `622b9558`.
- Real Apple 3.42 producer [40935524467](https://github.com/NoGod3524/EXReader/actions/runs/40935524467), source `148a5b11f9e65e87520eddff98e5365e83e98c30`: SDK builds passed, native admission failed before any case. Independent retained-ZIP inspection [40936609291](https://github.com/NoGod3524/EXReader/actions/runs/40936609291) found exactly one omitted SDK file, `examples/android/.gitignore`, with every transmitted file digest matching. Repair `6be10b3de1e7f9e98bab72db586a66e571199034` keeps complete file-set checks, transports hidden SDK files, retains early failure receipts, and includes the mobile picker helper. New-source SDKs must be rebuilt; old artifacts are not relabeled.
- Windows migration [40936421939](https://github.com/NoGod3524/EXReader/actions/runs/40936421939), source `ed734a879c933b78006ce9e78e89921d3c44fe69`: new same-directory fixture rename stimulus and original 67-group/30-minute gate. Earlier guard failure [40936057156](https://github.com/NoGod3524/EXReader/actions/runs/40936057156) executed no qualification groups and remains retained. Even a passing qualification does not enable Windows production recovery or grant F12.

The independent mobile workflow waits on the already-running exact producer on Ubuntu, then audits each completed host on macOS. It does not dispatch production tests. Its reports receive no catalog credit until explicitly pinned and reread by the fixed progress audit.

## Further mainline checkpoint

Independent mobile audit workflow [40937262016](https://github.com/NoGod3524/EXReader/actions/runs/40937262016) is waiting for the existing producer, not rerunning it. Its source is `82f0bc538024dbd7bedfead76724d307eb683719`.

The 3.42 transport repair is executing in [40937013878](https://github.com/NoGod3524/EXReader/actions/runs/40937013878), source `6be10b3de1e7f9e98bab72db586a66e571199034`; both SDK installations passed and native testing started. The next full Apple candidate is `bd28d4946f17a184dd3cd47a584cf49fce34e973`, branch `codex/apple-sdk342-full-handoff-20261029`, [40937997549](https://github.com/NoGod3524/EXReader/actions/runs/40937997549), queued when checked. It is based on public-module candidate `e6b899284744b95dc832db92ed16324711ff5362`, preserving those module blobs while applying Apple host functionality, the older-record upgrade policy and unchanged-budget original suites. This supersedes neither old host evidence nor any six-platform final gate.

Windows qualification [40936421939](https://github.com/NoGod3524/EXReader/actions/runs/40936421939) completed **66/67**: 43/43 frozen prerequisite and 23/24 native groups. The same-directory helper passed its own no-replace and parent controls and let g15/g17 pass. g10 reached a real downstream refusal. Retained-only inspection [40937534551](https://github.com/NoGod3524/EXReader/actions/runs/40937534551) found the child refused a temporarily missing request before the intended identity-replacement boundary: `regular-open`, Windows error 2, `target_sdk_open_attempted=false`. The original expected reason must not be broadened; the next test-only synchronization candidate will wait for the actual first-envelope-checked boundary before replacing the fixture.

The separate product next step is a Windows startup gate before ordinary `exr_library_open`: an already-present migration pending/recovery/lock marker must prevent an accidental normal open, with a visible diagnostic and untouched user data; an ordinary profile or legacy-sidecar-only profile must still open. This is a cooperative startup prerequisite, not implementation of missing Windows recovery or a claim to eliminate all races.

No new fixed-catalog item has been accepted at this checkpoint; the verified total remains **95/108**.
