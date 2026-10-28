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
