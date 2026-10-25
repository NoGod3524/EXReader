# D06: action, shortcut and focus consistency audit

Implementation baseline: `0889f7d1e9a537c6c1b05456547e016b26e1cd85`.
Approved SDK: `edddc463c06ed5731195cdb8f06b2df6dff7699e` (3.41.0 / ABI1 / core3.40.0).
No production files are changed. Audit completion is not keyboard or product acceptance.

## Separate identities

| Mode | Actual program producer source | Fixed reference documentation |
|---|---|---|
| Windows default and compact | eab342ef456be4a8a1811e5249e3c217d906ce8a / 40201283788 attempt 1 | f355525b74ae261db536c56200e46643919ef323 |
| GTK compact | 57203a52aee439be5194ee0a4b13563a975e8daf / 40206458217 attempt 1 | 9fc407a5cce5a0bfe644a60bd8dc29f84dea6d0e |
| Android reference, no new execution yet | 4a04a9cc74dde67f755c87e87b278d63a254a3ac | caa84411ae79c866c28cf982243b6cb80b4bbe49 |
| macOS reference, no new execution yet | 15dab6b2270dc296ed6239db67ced2e22d255e65 | 44eabdc86b3b84d986f81dbaf8cee92b1829cea8 |
| iPhone and iPad rejected candidate | 72c6bbdd14ebf3be453fa7f0da81119d52675eb5 / 40203714083 failed | no collective grant |

The new workflow authenticates original ZIP bytes, expiry and producer SHA in Actions,
then launches the actual binaries again in fresh isolated profiles. New driver report
`source_sha` is the harness event SHA, **not** the binary source; execution envelopes
separately bind target checkout, producer source, binary hashes, run and attempt.
Old tests are unchanged. Logs, screenshots and focus reports are hashed and re-read
by a same-run verifier. Old successful reports never substitute for new execution.

## Reuse and coverage delta

G12 Windows audit found keyboard and semantics gaps (49 checks, eight blocking findings,
not a screen reader pass); G13 uses actual AT-SPI and X11 focus; G15 Android uses
UiAutomator semantics, not TalkBack speech; G16 records macOS/iPhone/iPad separately,
including retained earlier overlap-judge failures. See existing `docs/READER-A11Y-*`.
J08 is a standalone keyboard translation component: its Ctrl+T/Command+T map does
**not** establish that any host wires it in. J navigation/search/record/settings
owners already provide native event tools; this package does not duplicate their framework.

Reused new execution: Windows search keyboard's 17 named native checks (Ctrl+F,
query focus, Enter, full Tab cycle, Shift+Tab, locate, cancel/close focus recovery),
Windows compact's system picker cancellation/import/open/previous/next/Alt+Left/
resume/records/search/directory/settings routes, GTK compact's 46 named controls,
real menu/keyboard input and AT-SPI focus including import cancel, records row focus,
close restore, library and continue. Additional Windows input ownership probe adds
left/right/space/letter in query and repeated Ctrl+F; it does not claim repeat-submit.

Coverage still pending: default GTK new execution; Apple three targets; Android new
UI execution; hardware keyboards/DPAD on mobile; repeated submit across all dialogs;
full modal focus trapping in every surface; NVDA/Narrator/Orca/VoiceOver/TalkBack speech.
No missing surface is substituted with a private API. See `actions.md` for static
mapping, context, focus promises and explicit unknowns.

## Retained first failure and expanded second run

Run 40215158098 / attempt 1, harness 43f2d96df2e43d4e31a041ae37b7881dd9297115:
guard passed, GTK job 121234630458 and Windows job 121234630520 failed before
native execution. Artifact metadata authenticated, but Python forwarded an API bearer
header onto the signed storage redirect and storage returned HTTP 401. The next harness
strips that header only across origins, leaving ZIP size/digest/expiry checks unchanged.
Zero native actions in the first run; original job logs remain the failure record.

Second run also attempts Android original search/navigation native UI on API34 x86_64,
plus separate macOS/iPhone/iPad native SwiftUI representative paths. Apple uses unchanged
project generator, newly built actual target app, and original authenticated SDK/product
artifact from 40203714083. The SDK producer is 72c6, target app macOS is 15dab and mobile
72c6; no collective success is inherited from the failed producer run. All Apple builds
explicitly disable signing. If macOS XCTest requires signing, its refusal is retained,
not bypassed. Native query typing tests focused input; no external keyboard grant.
