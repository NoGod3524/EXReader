# Windows Wave3 host with transaction SDK candidate

The installed SDK 3.42 Windows host candidate was tested at
`c6d68f22dae3d660c3308df443953c0f40cda475`.
[Actions 40644066200, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40644066200)
completed successfully on windows-2022. The source guard checked the SDK
source tree against transaction candidate
`8357eafa28423a7ab93ba08b823af80f01ad1505`.

The same run built and installed the SDK and reader modules, built and packaged
the Wave3 host, and passed its packaged host self-test. It passed the retained
compact native UI suite, the Wave3 native UI suite, and the actual native TXT
progress suite. The last suite exercised source-based search history and
reported a restored offset of 970000.

The [same-run artifact](https://github.com/NoGod3524/EXReader/actions/runs/40644066200/artifacts/12796818493)
is ID 12796818493, 4,950,341 bytes, SHA-256
`a83716b69099e2a0ecce391c775cead11e78575f8b7836e57f0631301a9fc690`,
expiring 2027-01-26. It contains the host, package identity, reports and logs.

This is a Windows runner result for that source. It does not establish
migration lifecycle integration, the unresolved historical migration cases,
cross-version reading-record compatibility, or six-platform acceptance.
The subsequent workflow extension adds same-source account/sync, organization,
receive cancellation and large TXT forward-scan comparison; its result is
reported separately once complete. Documentation commits are not tested source.

## Extended same-source run

[Actions 40645027546, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40645027546)
tested `f6597abbfd2ffc65db9b3741ea06a320340b9283`. The complete run failed:
the organization readback probe requested exactly SDK 3.41 while the runner
had installed 3.42; organization and receive cancellation were skipped.

The same run passed the original host, compact UI, Wave3 UI, TXT progress and
32 account checks. The real native forward-scan comparison passed 24 cases in
each of two profiles with equal page results, including current-page EOF
positioning: zero newly generated pages versus 61,456 for the from-first
reference. The seven installed SDK scan checks also passed. This is a scoped
Windows runner observation, not acceptance of the failed whole run.

[Original artifact 12798106979](https://github.com/NoGod3524/EXReader/actions/runs/40645027546/artifacts/12798106979)
is 10,685,778 bytes, SHA-256
`cab27ee93354190d93a0f7643cd9ac16642d71ddfb2f316b7f12dcc1824b9e46`.
The follow-up explicitly selects the installed SDK version for that probe;
its acceptance is determined by the follow-up run, not this failure.
