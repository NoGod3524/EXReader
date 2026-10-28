# macOS organization: original successful cases from a failed run

Coordinator scope review, 2026-10-28. This is a proposed independent host outcome,
counted only after the fixed audit authenticates the retained original evidence.

[Run 40635727935, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40635727935)
used source `716c1409168960a276e282ce694d32ed82497bc9`.
The full run remains **failure**: iPhone and iPad failed and the combined summary
was skipped. Only [macOS job 122642119295](https://github.com/NoGod3524/EXReader/actions/runs/40635727935/job/122642119295)
completed its actual native execution and original evidence collector successfully.

Original artifact **12799455200**, name
`apple-organization-macos-40635727935-1`, is **4,796,037 bytes**, SHA-256
`1f327fe705f7db3fadbe478f3d54300ce8948928b26ca80865ee17c9dd297417`.
The original collector recorded executable SHA-256
`c7cdb0875a62a2312dc407051f9ec707e5b19ae7f9dbb46f12a08178c8155ade`.
The retained ZIP contains the original XCTest result, xcodebuild log, validated
report and exported step/screenshot attachments; this audit does not claim to
recover an unretained app binary from that ZIP.

## Six actual passing native cases

- `testGroupLifecycleAndProcessRestart`: create, rename, delete, restore, restart.
- `testMembershipAndProcessRestart`: real import, add membership, restart, remove.
- `testTagAndSeriesPersist`: create tag and series, reopen each after restart.
- `testStagedIntentSurvivesTerminationAndRetry`: staged intent, terminated process,
  reopen, explicit retry and persisted result.
- `testNestedShelfSurvivesRestart`: parent and child shelves persist.
- `testStaleEditDoesNotOverwriteCompetingRevision`: stale edit refused and competing
  revision retained.

The source [original collector](https://github.com/NoGod3524/EXReader/blob/716c1409168960a276e282ce694d32ed82497bc9/tests/apple_host/organization/collect.py)
required all six Passed results, exact ordered step attachments, PNG screenshots
and application source identity. The new narrow audit adapter reauthenticates
the outer ZIP, exact successful macOS job and steps, source/run/attempt/report,
six passing xcodebuild lines and all twelve original case attachments. It does
not accept arbitrary string case lists or change any original assertion.

Only **H.macos.organization** is proposed. iPhone/iPad organization, other Apple
host features, final same-source six-platform organization (F03), physical
devices and screen-reader acceptance remain separately ungranted.
