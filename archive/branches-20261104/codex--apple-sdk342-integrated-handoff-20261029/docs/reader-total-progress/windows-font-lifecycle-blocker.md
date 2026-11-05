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
