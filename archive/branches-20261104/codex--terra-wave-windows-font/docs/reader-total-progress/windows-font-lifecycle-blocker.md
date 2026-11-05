# Windows font lifecycle: candidate evidence

The previous Windows wave-3 evidence in `reader-wave3-c09/root-validation.json`
passed the native font UI but did not directly measure host leases. The former
saved-progress reopen could also replace a live frame with an older position.
The earlier refusal guard at `aa11c05a` was a mitigation, not acceptance.

Source `6a3c5ccc63f9b98ca0f948122f2a0c338097a1da` passed the focused native
Windows acceptance in [run 40629003915, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40629003915).
Font changes use the current live frame and existing document/chapter pager
APIs; a candidate page is accepted only when it contains the original logical
point. A fixed page is retained. Failure retains the old font and frame.

The review-only host records actual font-library open, release and close return
codes. The native UI test observes noninitial bounded EPUB and ordinary HTML
positions; imports and applies a font; verifies bad-font rollback while a local
font is active; reapplies the selected font; injects a layout error after a
replacement lease is opened; switches between imported fonts while progress is
held; restores the built-in font; and checks release and library close at exit.
The held state and layout error are review-only injections; they are not claims
of a real filesystem failure. The earlier UI run 40375338225 includes restart
coverage. The review build is not the packaged product executable, and the
six-platform same-source product acceptance remains separate.

The original Actions artifact is `12791071176`, 214037 bytes, SHA-256
`fe656c5300504ac50e823ab9a73be982381c53fb07f61edc2332623183fd2c65`.
Run 40627703951 failed before the host launched because of a Python module
name collision; its failure is preserved. Runs 40628069828 and 40628517983
passed earlier iterations. The existing 32-lease and 128 MiB budgets and frozen
assertions are unchanged. The blocked D13 experiment was not run.

The fixed-catalog Actions audit [40629504633, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40629504633)
at source `ebc227ef3a44111f1bf6b971e513417acaaed0ac` authenticated the original
artifact and all eight named cases. It completed with no evidence problems and
counts this host outcome as verified. The full same-source delivery remains
separately unaccepted.

## Same-source TXT follow-up

The earlier review did not exercise the TXT-enabled host. Source
`c7a1ccdcac6a6f56b0ccf92da9d9a6fb08435719` passed [run 40631109809,
attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40631109809).
One TXT-enabled native review executable, SHA-256
`5593b25334b7cdab1ed205210863ca520847753bcf1a0fbd05d13ee7a08d17ba`,
passed the unchanged eight EPUB/HTML lifecycle checks and five additional long
TXT checks. An Actions-side binding compares both reports' source, run,
attempt and executable hash. The original artifact is `12791274325`, 1474708
bytes, SHA-256 `397f0921d2877483260ff92466c91315b669eede160983d3dd78d36acc218afb`.

The native TXT test imports the frozen 16,792,975-byte original and starts at a
noninitial page boundary. It verifies the same normalized byte point in each
accepted page and durable progress across repeated font changes, checks that
navigation establishes a new point, and checks bad-font and injected invalid
candidate rollback with the old frame and lease preserved. The invalid page is
injected only in the review build. The point is retained across successive
font-only relayouts and invalidated when the frame changes through navigation.
No all-format acceptance is claimed; the new run tests EPUB, HTML and TXT.

[Run 40630252484](https://github.com/NoGod3524/EXReader/actions/runs/40630252484)
failed before switching fonts: its new test incorrectly assumed adjacent TXT
page ranges had no separator; the observed end was 727 and the next start was
728. The failure artifact remains intact. The corrected boundary test passed
in [run 40630623987](https://github.com/NoGod3524/EXReader/actions/runs/40630623987)
and again in the final same-source run. Original assertions and frozen budgets
remain unchanged.

The updated fixed-catalog audit [40631611219, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40631611219)
at `60f3dbc2d58e0a1d8287fcc605c3be042ac5b0e0` authenticated the eight prior
cases, five TXT cases and same-source binding from the original artifact, with
no evidence problems. This result does not extend the tested format scope.
