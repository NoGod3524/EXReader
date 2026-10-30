# Migration recovery candidate in the public product source

This stage builds on the public-module Windows startup composition
`10672a5325e721b6ae43be43e3f2e6865e1cf4d0`. The original public base did
not contain the production recovery candidate, mirror implementation or native
Windows qualification adapter. This stage carries the production files and five prerequisite/qualification
suites from
`0c0a24bf53b1efecb515ac5e6a8dfcf1a8f8e101`.

Actions compares all production/frozen suite Git blobs with that source and
admits only the exact complete-token helper repair described below. The SDK core, ABI,
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

## Completed producer results

Actions `40949223801`, attempt 1, source
`be3f9f5610125d1ff969add1169028111b398a22`, completed success:
Linux 131/131, macOS 131/131 and Windows 8/8 capability refusals, total 270/270.
The POSIX groups remain 41 preflight + 22 handoff + 32 actual importer +
36 new-target groups on each host. Producer success supplies no independent
audit or catalog credit.

| Host | Job | Original ZIP artifact | Bytes | SHA256 |
| --- | --- | --- | --- | --- |
| Linux | 123712573306 | 12930499541 | 19503796 | c42772e380ddf4b84a75fe406ee7c687b6e15bf40013ff7a080a0390dfe0b62f |
| macOS | 123712572899 | 12932484375 | 19520617 | c2a42eb5ba3e399a4dd5a0050be00131362b594e17450cf591a7ad630b0f58e0 |
| Windows refusal | 123712573269 | 12930546852 | 32135 | f762cf6bcc533c69260c4a02097ca0e72d75fd642aaee6432d5a1daa6f1f2357 |

The earlier common production source
`00e12b8b66ac2c66245e462ef4931a724671cd34` separately passed Windows
43/43 + 24/24 qualification and actual product startup 10/10 in
`40946864077`, job `123704417841`. Those are that source's results;
they are not transferred to the later helper-repair source.
Qualification ZIP `12929323885` is 3803103 bytes,
SHA256 `bef43407363a857f82230747c03ae0c7218d9170b015bdaaa2813bbd3731edf7`.
Startup ZIP `12929038419` is 3367907 bytes,
SHA256 `134f3034990b47b5fb0e8cd844e45d4c6c4818535ce740dc5112bdfaddba3696`.

The separate full-FileID Windows persistent-format slice is documented in
`docs/MIGRATION-WINDOWS-RECORD-CANDIDATE-20261029.md` on
`codex/windows-record-format-candidate-20261029`.
Its tested source is `2743f32a4eccd5823657da19cb4f77f2411424af`,
run `40950523121`, job `123717117262`: installed native consumer 27/27
plus original Windows refusal 8/8. Its ZIP `12931496665` is 131650 bytes,
SHA256 `fe9906afd12bf2644cf584f627b525cd17d9e2f007615b2297a5d423f67611ec`.
This separate-source result is not a combined final-product acceptance.

Windows `lr_*` recovery, a real Windows full-scanner worker, public/private
mirror publication and actual host suspend/migrate/reopen remain unimplemented.
The new 49-byte record format is a default-off tools-library candidate;
it grants no recovery admission or power-loss durability. The fixed 108-entry
catalog is unchanged. Per the user's latest stop instruction, this round ends
after result documentation and the root's necessary acceptance/integration;
no next Windows worker or recovery package is started.
