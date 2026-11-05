# Common-source OpenType and Windows TXT validation

This record identifies the tested source. It does not transfer results to later commits.

- Candidate: `0ec6d3aa34297f30e016af9f1cb2416ed79709f2`, branch `codex/reader-history-ot-relay-prep`.
- SDK tree matches `5b7a34ee4f1ce38cf3bcd7cf0220575f4ecf7da9` for `src`, `include`, `cmake`, `CMakeLists.txt`, and `bindings`.
- [Windows composed host, 40625252266, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40625252266): success. Artifact `12789337609`, 612778 bytes, SHA-256 `91d4d388cc0ebc067da0c1d06a923b2c497eee815bb7ada23176a7c1e320a921`.
- [OpenType acceptance, 40625252334, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40625252334): Linux, Windows, macOS and authentication jobs succeeded. Authentication artifact `12788829106`, 431 bytes, SHA-256 `72e4429b103611eef423a739b952dcb12b4527fdd12d9facfc6d73069363a28e`.

The original host failure, history root cause and independent corrected-host evidence are recorded in [Windows TXT history recovery](../WINDOWS-TXT-HISTORY-RECOVERY.md). The independent OpenType acceptance and retained failed run are recorded in [OpenType acceptance integration](ot-cache-acceptance-integration.md).

Apple-Android relay, Android font and GTK runs were still in progress when this record was written. Each remains subject to its own source and same-run final acceptance.
