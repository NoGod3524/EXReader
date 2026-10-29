# Migration recovery candidate in the public product source

This stage builds on the public-module Windows startup composition
`10672a5325e721b6ae43be43e3f2e6865e1cf4d0`. The original public base did
not contain the production recovery candidate, mirror implementation or native
Windows qualification adapter. This stage carries those exact production files
and all five unchanged prerequisite/qualification suites from
`0c0a24bf53b1efecb515ac5e6a8dfcf1a8f8e101`.

Actions compares every imported Git blob with that source. The SDK core, ABI,
bindings, original legacy fixture data, 65 original scenarios, review cases and
browser/export tests remain unchanged. The three startup gate product files
and original ten-case driver remain exact copies of
`2fff53ff6734ec2b495c841e6669aef562e170d7`.

The new source must independently pass the original Windows 43 preflight and
24 native groups, its own actual-product ten-case startup test, and the
unchanged 270-group recovery matrix (131 on each POSIX host and eight Windows
refusal groups). Their original budgets, assertions, result files and retained
failure evidence are preserved. Prior-source passes grant no acceptance to
this composition. No catalog entry changes here.

Windows recovery remains explicitly unsupported: its `lr_*` implementation
still refuses before SDK migration open, its real recovery worker is not
installed on Windows, and Windows new-target creation remains refused. The
existing 33-byte mirror identities and qualified 49-byte Windows adapter IDs
retain their original formats; this stage neither truncates nor reinterprets
them. Full-width Windows protocol, worker supervision, cross-directory mirror
publication and the actual host suspend/migrate/reopen lifecycle remain the
next production work. Full P0, F12 and physical power-loss safety remain open.

The first common-source run, `40946864068` at
`00e12b8b66ac2c66245e462ef4931a724671cd34`, retained a Linux 21/22
handoff failure in `crash-S5`. Its original ZIP is artifact `12929848394`,
19159055 bytes, SHA256
`45cfbbfadc3d17eb6bfd773736a96472826e1cf0be908279fb1b9bce63f2ffe4`.
Actions inspection `40948832372` rehashed that ZIP and showed a fresh R retry
refused with `file-read` before its scanner completed; no COMMIT was reported.
The original helper exposed each `.go` filename before completing its nine-byte
write. The native reader checks the fstat/read byte count, so this publication
window can cause the observed safe refusal. Both helper call sites now reuse
the existing calibrated complete private no-replace token publication from the
actual importer suite. All 22 case bodies, original assertions, native helper,
budgets and failure evidence remain. Admission permits only these exact helper
edits and independently checks that every original assertion is identical.
