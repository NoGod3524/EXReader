# Android original save: independent candidate evidence

Source: `748e93713c643243a96bab54f5ca1464a2f39efd`.
[Run 40603049703, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40603049703)
passed on the actual Android host in an API 34 x86_64 emulator.

The test opens the shelf original-export action and the real Android DocumentsUI,
selects Downloads, saves an EPUB, and compares the destination byte count and
SHA-256 with the original fixture. It verifies the installed APK against the
built APK, then checks both named results in the same-run report.
Artifact `12780380289` has 40510883 bytes and SHA-256
`e03942f47d365c991862738c5d4236beb01406b734ee5d91e66d099039b4e657`.
The progress audit authenticates the artifact and reads both passing cases.

The previous run 40602271905 remained in DocumentsUI after a touchscreen tap
and failed; the succeeding driver used the system control's accessibility click.
This observation covers the emulator and this EPUB save path. Physical-device
and unified-source acceptance remain separate.
