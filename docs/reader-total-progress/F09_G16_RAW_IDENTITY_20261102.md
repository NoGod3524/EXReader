# F09 original G16 evidence identity inspection

Base fb05934bc68400359118d2b0ea67321fa53edbdd. Candidate-only investigation; no old contract or product changes.

Exactly three artifacts from source e9e20eada714bc6b8045d3e943ac46ff26844559, run41363868404/A1:
- macOS13106229495:5431651 bytes, SHA256 0f8aef287a742778eceb2b25844c0209d879d77686e7818c612f9aa181069d18
- iPhone13106354573:151712130 bytes, SHA256 b5083d8dc48d0cc7a79788bb834ec75f372a304a83710a3402282d33fbba2da2
- iPad13107061378:88419007 bytes, SHA256 e26850c738007e51bf0569c010443f10856db57d5402fe5a9a3da260ea5f88de

One Ubuntu22 job <=10 minutes; inspector alarm480 seconds leaves upload time. No retries, application builds, device work or artifact code execution. ZIP operations only in Actions. Pinned download total245562788 bytes; declared expanded and cumulative payload reads<=2GiB; member<=512MiB, count<=30000. Selected UTF8 text/metadata<=16MiB per member and128MiB total. Unsafe paths, duplicates, encryption, symlinks/special files fail closed. Original archives are deleted from runner temp storage after inspection; only sanitized reports are uploaded.

Member inventory covers original archive metadata. Selection: report/summary/manifest/a11y/accessibility/snapshot/tree/build/settings/compile/log JSON, LOG, TXT, XML, JSONL; app Info.plist plus its declared executable bytes only for SHA256. No executable loading. Full source text and binary payload are not published; hashes and limited sanitized excerpts identify originals. Credentials and URL userinfo/query/fragment are redacted.

stdout prints the review summary with up to16 ranked text members per platform, limited excerpts, explicit omissions, identity and missing fields. Uploaded report retains full selected-member inventory/metadata summary. Original AX node completeness cannot be inferred from summary states or substring counts. Compile flags are observations, not automatically bound to a program. mode_binding_verified remains false until independent evidence review; no candidate reevaluation is performed. Historical six G16 blockers and formal98/108 remain unchanged.

Exact raw marker/schema source: tests/reader_a11y_apple/A11yAuditSupport.swift at e9, emit EXR_A11Y_STATE followed by JSON; kind=state, step/platform/test/element_count/elements. Original audit_collect.py parse_records61-84 parses this marker. Standalone state JSON attachments use the same payload. This inspector counts all parsed records, preserves per-record hashes, counts actual elements and target nodes, and reports source/program identity fields present or missing.
Important producer limitation: flatten() retains at most240 nodes; capture() omits anonymous nodes from elements. Even valid complete JSON records are NOT the entire original AX tree. Report-to-log SHA checks are explicit and separate from unresolved compile-mode/program linkage.
