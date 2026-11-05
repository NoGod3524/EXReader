# Apple maximum-type reading and organization — accepted handoff

- Tested source: `3d3ebc6c3eecf2c1e8ca62ae9f0fe16ac80097ee`
- Branch: `codex/dot-apple-large-type-drivers`
- Base: `716c1409168960a276e282ce694d32ed82497bc9` (durable organizer candidate)
- Final same-source run: https://github.com/NoGod3524/EXReader/actions/runs/40691898228 (attempt 1, all five jobs successful, completed 2026-10-28 13:59 UTC).
- iPhone: 43/43; iPad: 43/43. Each preserves original D24 + 39 historical cases and adds actual ordinary-size import setup + two maximum-type organizer flows. All builds, fixtures, XCTest, result parsing and ZIP authentication ran in Actions.

## Actual scope

Maximum accessibility system type is set and read back. Original D24 reading portrait/landscape/recovery checks remain unchanged. Added flows use actual imported EPUB and actual reading → bookshelf → organization → shelf/tag/series selection, refresh, create/name/save, Done → reading → Back. Full-window/scroll-viewport containment, hittability, keyboard dismissal and the eight-scroll limit remain strict. Setup imports at ordinary size only; production probes run at maximum size. Simulator results do not establish physical-device or VoiceOver acceptance.

## Roots and narrow fixes

Only product file changed is `examples/apple/HostViews.swift`, within HostOrganizationPanel. The former 400pt minimum with fixed controls puts Done at y=-56.5 and leaves the group viewport zero-height in 667x375 maximum-type landscape. Pinned header and a single iOS scrolling form remove that minimum (desktop retains original sizing). Accessibility-size actions become vertical, and keyboard Done dismisses name/ordinal focus. Storage, migration, original-save and organization-toggle behavior/tests were not changed.

Two driver issues are distinct: the initial test-only import fixture button was taller than its small scroll viewport; default-size real application setup is now explicitly separate. Later short scrolls still flung past controls; documented slow drag with terminal hold fixes momentum without coordinate tapping or relaxed assertions. The user's historical pair of large-font driver failures was not uniquely identifiable; these independently reproduced failures must not be mislabeled as that pair.

## Same-round raw artifacts

Each URL is under https://github.com/NoGod3524/EXReader/actions/runs/40691898228/artifacts/ . Expiration is 2026-11-27; download before expiration for durable raw retention.

| Artifact | ID | Bytes | SHA-256 |
|---|---:|---:|---|
| iPhone native xcresults, screenshots/AX, logs, executables and manifests |12821228139|504976304|aefa5b911897b174534f72b1abe8ec3546424fc08899ccf203016a5ced7c4c79|
| iPad native |12820803557|538698661|d50062e8af2f4d5de8e8ec2384c65d7df3a98c06c0ec26f611228f3c7d961742|
| macOS build SDK/modules |12818175607|22412724|863780360ddcb3d247c6ff0a3aaaa13766dc2b76b2e2ca3b8ac9c5b78467f5e1|
| simulator SDK/modules |12817153592|22404765|4ba2a444e29d2d847467bc5ebbd951ab397743e8f42a2a1839ab419f41ef1676|
| Ubuntu authentication summary |12822205885|6752|f52e9fbead2f03526c40b9d26724bb4ad6eee1ea2135c9f0b127955389563208|

Authentication job 122861353734 downloaded/hashed original ZIPs inside Actions, checked source/run/attempt and every recorded evidence file, phase count, tests and actual program identities: accepted=true, failures=[]. Dynamic SDK is 3.41.0, not 3.42 acceptance. Native jobs: iPhone122830408170, iPad122830408311. SDK jobs122828543050/122828543874.

## Retained failure lineage

All old runs remain intact; initial failed probe retained verbatim at `tests/apple_large_type_drivers/retained/OrganizationLargeTypeUITests-initial.swift`.

- 40649528425 / e1df2706d38d310148a560079b77d9a6b992f865: iPhone old40 passed, new2 setup failures; iPad42 passed.
- 40673513910 / fbd16c509a8b818dd88c914b5d465a70f52bc32b: actual landscape organizer Done offscreen; iPad focused passed.
- 40677656931 / 83e909def5c43eb3d86ae11c4611980d68f8789f: Actions-only authenticated raw log geometry inspection.
- 40678267136 / 39740c65f261ddc0c760757e3469f6fc8a5d778e: header fixed; new create flow exposed action wrapping/keyboard.
- 40682402006 / 0e5c6498d6a567fe23aa6126ac947d4126c93851: iPad focused passed; iPhone landscape scroll overshoot.
- 40685292576 / 4b654fc25c984b8acae278cc9977ab421e412e4a: short drag inertia failure preserved.
- 40688338294 / 28039e02538a97d8b18f53846be48026cbc784a0: focused iPhone green; not used instead of final common-source round.

## Integration and remaining boundaries

Apply only the HostOrganizationPanel change plus `tests/apple_large_type_drivers`, its two workflows and documentation relative to the recorded base; do not import unrelated source history. Keep focused workflow manual-only. Compose with current owner's original-save/toggle/migration work carefully, then run new common-source validation; this run cannot certify a different composition. No default branch merge, tag or release was performed. No SDK or original tests changed, no timeout/attempt budget enlarged.

Next proposed independent package: after the coordinator's P0 migration-safe SDK3.42 common candidate is fixed, port these isolated tests/workflow to that exact source and verify installed SDK/module identities plus 43 native cases on each simulator. Exit requires new same-round source/ZIP authentication. Physical-device VoiceOver remains an external-capability gap and must be recorded separately, not inferred from XCTest accessibility trees.
