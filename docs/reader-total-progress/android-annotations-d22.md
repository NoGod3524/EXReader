# Android annotation exchange: D22 retained evidence

Source: `92d453e374725896a7d1666c313e5d369ff83b3c`.
[Run 40460333186, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40460333186) completed successfully, including the retained C11 actual Android host on the API 34 x86_64 emulator.

The first phase creates bookmarks in the reader, exports JSONL and Markdown, saves JSONL through the host destination flow, and rejects an import for the wrong book without writing. The restore phase checks preview before writes, explicit confirmation, import of real revisions and outbox entries, duplicate reimport, tampered-input refusal and navigation to an imported bookmark. The Android framework picker and destination are stubbed in these cases; physical DocumentsUI and physical devices are separately assessed.

The retained same-run artifact `12715880811` has 112475779 bytes and SHA-256 `369380a70797fd8bc1e5b3212720b716d3c010436c0a4cf1825b780bf79ded06`. The fixed catalog audit verifies the original artifact in Actions and reads named passing checks from the first and restore phase reports.
