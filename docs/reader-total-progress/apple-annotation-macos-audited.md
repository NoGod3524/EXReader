# macOS annotation exchange independent audit

Independent audit [40928332937](https://github.com/NoGod3524/EXReader/actions/runs/40928332937), source a24e24fa1577c6dd685b304c2506e3db90346eb8, job 123639751398 passed. Its exact retained artifact 12920419850 is 1607 bytes, SHA-256 4da7db9ca2cea780f00992f412b43fdc4253ede85aae4689d82265510f92d44a.

Original: run 40923468266, attempt 1, source 622b9558f79eda07211e15c51bffcd728da6c553, native macOS job 123625260629 completed successfully. Exact original artifact 12920073975: 316382076 bytes, SHA-256 11792b2252650bf055fe035b92a4f7e83b0d7bf248fb404a432d4a651d16e4ac. At independent audit time the other hosts were running; the report explicitly records original_run_status=in_progress, original_run_conclusion=null and whole_run_accepted=false.

The independent Actions job rehashed the original archive, reread all five native xcresult bundles (5 feature + 13 base + 13 navigation/records + 4 search + 4 theme cases), verified exact original test-file hashes, checked 14 original PNG attachments, and extracted/rehashed all five original app binaries with matching EXRSourceSHA and bundle ID. It also verified actual OS dark/light command records. Every one of the 39 cases passed.

The annotation case selects a real system directory for JSONL and Markdown, imports valid and invalid files with the native file chooser, verifies preview, rejection, revision identity after invalid input, cancellation, confirmation and duplicates. Its in-process check reads the actual selected-folder JSONL and Markdown, verifies complete JSONL structure, wire byte count/hash and cross-format book/annotation/revision identity. Original exported payload files are not separately retained; the independent audit relies on that actual native XCTest result for their content checks. NULL selectors, concurrent heads and native directory cancellation are also tested.

Program SHA-256 values independently read from retained app ZIPs:

```json
{
  "wave3": "1014a409d972a11201613a9010c0edbb39e0d25bb8ebf6f0741dc7b19684ebb8",
  "base": "3309586f4fcb1c0dcbc587df6c9c35723cf4846d8cb6a3186dcedf0a80b522f2",
  "control": "ff542e1ce7dc1b22d752ef1b7f3b1ed077a7640649eac3d47545aaaa5ca54edc",
  "search": "662987b12396ead95a4a5a7158ee83a477a1d5b9776f56aaf8d7f8d716aa0079",
  "theme": "d69c6894b80470431384b497b1ac9e5be4aba46a30570b8d6209fe8ed6a5d40e"
}
```

This grants only H.macos.annotation_exchange for SDK 3.41 on the Actions macOS host. It does not grant iPhone/iPad, physical devices, SDK 3.42, whole original run or final common-source acceptance. Earlier failures 40911433448 and 40920156829 remain unchanged.
