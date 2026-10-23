# Apple product import mapping

This adapter joins the native Apple host's existing SDK library to the separate
product catalog in `apps/reader/store/001_catalog.sql`. It uses the installed
public SDK and Apple Foundation, CryptoKit and system SQLite. The shared Swift
binding, product schema and frozen SDK trees are unchanged.

## Import and recovery

1. The host reads the chosen external URL once into a private staging directory,
   in chunks of at most 64 KiB. It hashes those actual copied bytes and checks
   cancellation and the format's limit: EPUB 128 MiB, other supported formats
   32 MiB. A changed source length is rejected.
2. The existing SDK import receives this stable private path. The adapter opens
   `exr_library_source`, reads its actual stored bytes in at most 64 KiB chunks,
   and compares SHA-256 and length to the private copy. Every acquired source is
   released on success, error or cancellation.
3. The existing `HostCancelBox.commit` establishes publication. A failure or
   cancellation before it compensates only a newly created SDK row. An existing
   row is retained.
4. One product SQLite transaction writes a missing `reader_books` row and its
   `reader_local_books` mapping. The global key is `format:sha256`; the SDK ID is
   local to this library. Its location kind comes from the actual stored mode:
   `fixed_page`, bounded `epub_chapter`, or snapshot `reflow_global`.
5. A product transaction failure after publication keeps the SDK original. The
   host refreshes its SDK bookshelf and reports “书籍已保存，产品索引待修复”. On
   startup, one SDK enumeration supplies a scan of IDs missing from local
   mappings. Repair hashes only those candidates and creates their missing
   product mapping without reimporting the original.

An existing product row retains its title, author, sort title, favorite and
deleted state. New sort titles use NFC; display-title bytes are retained.
Import does not replace revisions, tombstones or outbox entries. Historical
identical SDK rows are retained; ascending repair and attachment select the
smallest SDK ID and that row's actual storage mode.

SDK import/publication and startup mapping repair are serialized across models
in the same process. Startup's enumeration participates in that boundary, so a
second window cannot repair an SDK row still awaiting created-only compensation.
Reading and rendering retain their existing owner queues.

Private copies have a process-wide active lease. Another window's startup
cleanup skips live imports and removes copies whose process has ended. Normal
completion explicitly closes the copy; removal errors are reported, and startup
retries abandoned copies. This protects PDF's later path opens as well as EPUB
stream reads.

## Separate acceptance

The independent workflow is `.github/workflows/reader-apple-import-mapping.yml`.
It builds the unchanged installed macOS and simulator SDKs and runs:

- the original exact eight production catalog checks;
- 16 macOS cases using the actual public SDK: fingerprints, three location
  modes, both orderings of legacy snapshot/bounded duplicates, preserved user
  metadata and history, NFC, HTML/XHTML identity, cancellation, source release,
  transaction failure and repair, external PDF replacement, changing length,
  source limits with a valid EPUB above 32 MiB, and another model's cleanup of
  an interrupted copy while an active PDF remains readable;
- five actual UI cases on each of macOS, iPhone simulator and iPad simulator,
  with 22 named steps and 14 named attachments per platform. They cover format
  mapping and stored reading, cancellation, process termination between the
  SDK and product transactions, process termination inside the product
  transaction, and a retained SDK book whose product index initially fails.

The special observers are compiled only for the independent review app. The
regular Apple UI project still selects the original test source and keeps its
13 UI cases, 67 named steps and 50 attachments. Its original 21 self-checks,
SDK 21, Model 18, Bounded 15 and 97 evidence-rejection checks remain separate
requirements in `.github/workflows/wp13-apple.yml`.

## Final same-source acceptance

Tested implementation: `a14ef94d1ae0e4f3d2db04621011a0ec2a6be32c`.
Both runs completed successfully on attempt 1, with every job on that source:

| Cloud run | Jobs | Result |
| --- | ---: | --- |
| [40021705710](https://github.com/NoGod3524/EXReader/actions/runs/40021705710) | 6/6 | Exact catalog 8; public-SDK mapping 16; macOS, iPhone and iPad each 5 UI cases / 22 named steps / 14 attachments; each strict collector accepted with no problems |
| [40021705532](https://github.com/NoGod3524/EXReader/actions/runs/40021705532) | 8/8 | Original Apple suite: each platform 13 UI cases / 67 steps / 50 attachments and 21 self-checks; SDK 21, Model 18 and Bounded 15; strict summary and all 97 evidence-rejection regressions accepted |

The completed native, three mapping UI, package, three original UI and summary
logs were read in the cloud. Native mapping cases passed without failures or
skips; all original UI cases passed with zero failures. The original summary
reported `accepted=true` and `problems=[]`, and its rejection review reported
`accepted=true, gate_review_checks=97`. Old candidate results contribute no
credit to these two final runs.

All 14 required artifacts were present, nonempty and unexpired at review.
Their API records carry the final source and their own run IDs; each upload
log's artifact ID and SHA-256 match its API record. The six independent
artifacts expire on 2027-01-21; the eight original-suite artifacts expire on
2026-11-22. Artifacts were not downloaded locally.

| Run | Job | Artifact ID | Bytes | API and upload SHA-256 |
| --- | --- | ---: | ---: | --- |
| 40021705532 | package | 12532691295 | 129638514 | `9dc8e7c090718f2e94deffabddcd11aa9fc2f7d4f2264f8f6a29130ddbec9520` |
| 40021705532 | sdk (iphoneos) | 12532146151 | 18540184 | `8e52d56e6e64da309a0f6b46591cf21dee6b0ba64ba1546a565b56e1afd63c99` |
| 40021705532 | sdk (iphonesimulator) | 12532580137 | 18837244 | `e12d26af2a7de7e092e8722e7c5b21de4bee972b80688d725829278d749b5c63` |
| 40021705532 | sdk (macos) | 12531797878 | 18837314 | `1c3feecf98ffd7c575d0d9eb5e3490c8c6beaf65ff0f56d28d36408ab672719f` |
| 40021705532 | summary | 12533156948 | 67291 | `edc226005a13ce6ff9ac9103a8504fa077cfc04acdd09e800568a61aa79a9989` |
| 40021705532 | uitest (ipad) | 12532547976 | 46610109 | `bd5b872642ca18701d00214e990397f4e43eb39973c2ace3d23237d2cf597699` |
| 40021705532 | uitest (iphone) | 12531934739 | 37326283 | `28e9b5258d263bb60171043298a120c990185e4421afd7560cd2a0ae92cb8d4c` |
| 40021705532 | uitest (macos) | 12532541772 | 36716140 | `d2da97f6ea62391a801976f3a590fd32fd891f25bffa88d3470a79f0e58fc52c` |
| 40021705710 | Mapping UI ipad | 12532711865 | 28892627 | `218345752c6200874bf7ace43f56d9cbb3d5968f57fb4930d3f24c8cb3a7e3ba` |
| 40021705710 | Mapping UI iphone | 12532633217 | 28674178 | `ada05401a403933d27736fb2dca29c5bf3280437f01406a8ffaa997fcdf83350` |
| 40021705710 | Mapping UI macos | 12531803312 | 28397237 | `c660b3948a9ea03c5d37e7788872c97443729651d520e4d308e742beaa5c12e5` |
| 40021705710 | native | 12532680130 | 686570 | `656ca6c506d9568f01d475e62b259c32003e632d19bde87ad558f635a5298d4a` |
| 40021705710 | SDK iphonesimulator | 12531648414 | 18837315 | `a16cee45d31b2346b80ed7f6a212581aa60132cafcd66c8a83fbf7b40b90c2ca` |
| 40021705710 | SDK macos | 12531338035 | 18837349 | `9c660cabe12e669b50483d9b11c38d79204d1d2df477efcc170dc8bc2094d062` |

The frozen SDK's eight protected trees and all shared bindings remain byte
identical to `9854061be331fe603a1822d9b2b36ee357154927`. The product migration
`apps/reader/store/001_catalog.sql` is unchanged from the Apple catalog base.
The merge of PR7 ancestry adds no SDK change.

## Candidate record

The branch is `codex/reader-apple-import-mapping`, based on Apple head
`05496414c8dd85d7db290e3ba6c9cc9ccb2ab6ce`, with verified CPU-baseline head
`220585e8248918096b9fc2c389ea5ad2389d388b` merged without rewriting history.
The SDK baseline remains `9854061be331fe603a1822d9b2b36ee357154927`.

- Initial implementation `fd81fd64f1f26558cc0fbf20bbdb28a2d9500252`, independent
  run [40019491690](https://github.com/NoGod3524/EXReader/actions/runs/40019491690):
  exact catalog 8 and the then-current 15 SDK mapping cases passed. This
  candidate predates the multi-window lease and retained-import status fixes;
  iPhone and iPad's then-current four UI cases passed. macOS's four cases
  failed at startup observation: the test read only accessibility `label`,
  while macOS exposed the displayed SwiftUI text as `value`. Its collector
  rejected the failed case set. This failed run remains unchanged.
- Revised implementation `dc1aafd2154fd289020780fc658865d71d690506`: independent
  run [40020800431](https://github.com/NoGod3524/EXReader/actions/runs/40020800431)
  and original full Apple run
  [40020800471](https://github.com/NoGod3524/EXReader/actions/runs/40020800471)
  remain separate candidates. Native exact catalog 8 and the expanded 16
  mapping cases passed, including the 34,610,870-byte EPUB and another
  model's cleanup during an active PDF import. Its macOS mapping UI's five
  cases failed at the same `label`-only startup observation and the collector
  rejected them; failed artifact `12531975180` is retained. The original
  Apple macOS suite passed all 13 cases and 67 steps on this source.
- Current implementation `a14ef94d1ae0e4f3d2db04621011a0ec2a6be32c` keeps the
  production adapter unchanged and reads native test text from `value` when
  `label` is empty, matching the original Apple UI suite. Independent run
  [40021705710](https://github.com/NoGod3524/EXReader/actions/runs/40021705710)
  and original full Apple run
  [40021705532](https://github.com/NoGod3524/EXReader/actions/runs/40021705532)
  completed successfully on this exact source; the final record above uses
  only these two runs.

All compilation, syntax checks, test execution, SQL execution and evidence
processing occur in GitHub Actions. Physical devices, VoiceOver, cloud-drive
transport and cross-device synchronization are outside this adapter's scope.
