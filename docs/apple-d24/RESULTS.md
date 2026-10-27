# D24 Apple maximum system type — scoped handoff

## Accepted source and immutable evidence

- Branch: `codex/dot-d24-apple-large-type`.
- Common candidate: `2f215f5793a7344d22db350276ba9f8a07abe86f`.
- **Tested source: `55078af169822787295e3ac1958375c1c12c0086`.**
- [Actions run 40473318130, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40473318130).
- SDK jobs 122085392739 (iOS simulator), 122085392834 (macOS): success.
- Native jobs 122087055655 (iPhone), 122087055568 (iPad): success.
- Authentication job 122111954342: success, `accepted=true`, `failures=[]`.
- Each native host: D24 1, unchanged wave3 5, base 13, reading/navigation 13, search 4, theme 4: **40/40**. These are the same source and same run/attempt, not borrowed greens.
- This report-only commit is not a new tested source. Workflow ignores `docs/apple-d24/**`.

## Product work and discovered baseline

The candidate already had compact reading controls, a horizontal tools scroller, 44-point back control, and fixed-size busy feedback. These were reused. Historical Apple reports and failure evidence were not rewritten.

ReaderScreen now has explicit compact tools show/hide, stable 44-point header targets, nonwrapping scrollable tool contents, and one full-size location/progress/status information row. It preserves text scaling rather than reducing the system category. Dismissed reading sheets restore the intended accessibility focus target in code.

The full native AX tree revealed the remaining independent account banner consuming 59.5 points during reading. With D21/coordinator agreement, minimal presentation-only routing now suppresses that redundant banner in reading mode and retains `account.choose` in the native reading More menu. Chooser dismissal restores the intended More focus target; account/session owners and switching lifecycle are unchanged. Account presentation routing is isolated in commit `e26bf241f5d4899420817be2b9355ba4e51da64c`.

The theme driver originally booted a second simulator while the D24 SE remained resident. The D24 wrapper now shuts down its simulator before calling the unchanged theme driver. No original boot timeout, test, SDK, assertion, or budget was increased.

## Actual native simulator measurements

Maximum actual OS content size: `accessibility-extra-extra-extra-large`. The test independently checks the native preferred caption size exceeds 20 points.

| Device / orientation | Window | Reading page | Height share |
|---|---|---|---|
| iPhone SE (3rd generation), portrait | 375 × 667 | 367 × 440.5 | 66.04% |
| iPhone SE, landscape, tools shown | 667 × 375 | 659 × 168.5 | 44.93% |
| iPhone SE, landscape, tools hidden | 667 × 375 | 659 × 252 | 67.20% |
| iPad mini (A17 Pro), portrait | 744 × 1133 | 736 × 869.5 | 76.74% |
| iPad mini, landscape, tools shown | 1133 × 744 | 1125 × 480.5 | 64.58% |
| iPad mini, landscape, tools hidden | 1133 × 744 | 1125 × 564 | 75.81% |

Both used iOS simulator runtime 26.2. Original minimum page shares remain portrait 45%, landscape 35%, tools hidden 50%.

Executed behavior includes real book import/open, maximum-type portrait/landscape, back and tool toggle reachability, account menu open/close without location loss, toolbar hiding with increased readable area, toolbar redisplay, actual next page, font increase, notes open/close preserving font and location, rotation back, library exit and reopen preserving font. Screenshots, native AX trees, xcresult, packaged host, resource identities and link maps are retained.

## Exact same-run artifact identity

Authentication downloaded and parsed these artifacts **inside Actions only** and checked original ZIP bytes/digests and same-source program identities.

| Artifact ID | Role | ZIP bytes | SHA-256 |
|---|---|---:|---|
| 12723156461 | native iPhone | 382653176 | a043dea8d2dadd4795473227aad952b905d624b121c2444b3b2091995fa2ef7f |
| 12722812689 | native iPad | 415096403 | 59037e610198d21f6dd25e2d0ac53fefee80e28c47da5d65be2b86d0b94e9f9a |
| 12719253437 | simulator SDK | 22199638 | 80a5dfc8e109162c1ca2d6d867451aa5cc01d2f9cc0b3131be6fc2ca30d07f97 |
| 12719008508 | macOS SDK | 22206676 | b9876c46565cd682a5ad822355dc4d3309e900e57f9e6606d23d10d615650397 |

## Retained failure lineage

- Run 40447145387 / source 1f1bfddd1d91006dbbc892f2f99d3d7c8a43cecf: iPhone page 109/375 (29.07%) failed the unchanged 35% threshold; theme second-simulator boot hit original 180-second timeout. iPad 40/40 passed.
- Run 40448821790 / source 45f7767f4ba6efc8f18e550ba8c2ab34b2b6ed04: same iPhone area and boot failures; iPad passed; authenticator correctly rejected partial acceptance.
- Run 40452725380 / source 71d7cb2ac5aab7beef2ad1950a044f1ca82d95f0: header chrome alone did not recover the missing page height. iPhone theme passed after simulator release; historical native-share presentation test failed waiting for the actual share sheet. Raw evidence retained; no old assertion changed.
- Run 40466189218 / source d8c5692bd44cd639f22495422e9175182aa0b62b: both devices passed all 39 historical cases and page/behavior checks. The new D24 test incorrectly asserted hittability on the menu's anonymous internal child; the identified outer menu and subsequent real account open/close worked. Final test targets the identified native `reader.more`, retains its hittability assertion and adds full-window containment. This is not a relaxed threshold or historical-test modification.
- No failed run was deleted or canceled to manufacture acceptance.
- One GitHub create_tree attempt was initially rejected for perceived missing approval. Publishing stopped; after the coordinator supplied the user's explicit Git/push/fix-and-rerun authorization, the same action was reviewed once and accepted. No alternate tool bypass was used.

## Files and integration

Product:
- `examples/apple/HostViews.swift`: ReaderScreen; one read-only HostRootView route preference.
- `examples/apple/HostAccountViews.swift`: presentation routing/environment only, agreed with D21; no HostAccount/HostModel/session behavior changes.

Own verification:
- `.github/workflows/reader-d24-apple-large-type.yml`
- `tests/apple_d24/run_ui.py`
- `tests/apple_d24/ui/LargeTypeUITests.swift`
- `tests/apple_d24/verify.py`
- `docs/apple-d24/PLAN.md`, this report.

Integrate the D24 branch commit sequence normally from the common candidate (or review/cherry-pick its scoped commits in order); do not replace directories. D21's HostViews LibraryScreen hunks do not overlap D24 ReaderScreen/root preference; review the shared file rather than overwrite it. The account routing commit is isolated above. Run the composed source's native suites after composition; this run cannot certify a different composed SHA. No main merge, PR, tag, release or default-branch change was performed.

## Explicit limits

This is accepted **simulator UI scope**, not physical-device acceptance. Actual VoiceOver spoken output and physical iPhone/iPad behavior remain untested; adding accessibility focus state and passing native UI reachability do not establish real screen-reader speech/focus correctness. No macOS native large-type UI acceptance is claimed. SDK source, ABI, original budgets, historical tests and historical failure evidence were not modified. No local/user-machine builds, tests, syntax checks, benchmark, fixture generation or artifact parsing were run.
