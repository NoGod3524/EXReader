# Reader real-corpus acceptance

This directory is the complete consumer and protocol for `F5: real document
compatibility acceptance`. It does not modify the engine, the historical
corpus tools or any prior expectation.

## What is fixed

- `manifest.json` pins nine public formats, two independently published real
  files per format, source URL, byte count, SHA-256 (filled once by the cloud
  `pin` job and reviewed before acceptance), author, publication, licence and
  redistribution basis.
- `expect` records the operation outcomes declared before execution. An empty
  text layer or empty authored navigation is a document property and is written
  as `empty`; it is not converted into a pass.
- No engine result may select, replace or reclassify a sample.

## Consumer operations

The consumer links only the installed SDK (`find_package(EXReader CONFIG)`):

1. public library import plus original-byte readback (`exr_library_blob`);
2. open through the public reflow or fixed API;
3. public title and, for fixed documents, metadata entries;
4. authored navigation (EPUB publication navigation, other reflow resources);
5. first, middle and last page rendering, full sequential traversal, one step
   back;
6. exact text search and capture/resolve of a real anchor on the same document;
7. reopen from the same path, recount pages and resolve the captured anchor
   again.

Fixed-only formats (PDF/CBZ) report navigation as `not_exposed`; CBZ reports
zero text as `empty` and anchors as `not_exposed`. These are listed as real
capability boundaries in the summary, not hidden.

## Modes

```sh
python3 tests/reader_real_corpus/run_acceptance.py pin --out build/pin
python3 tests/reader_real_corpus/run_acceptance.py collect --out build/corpus
python3 tests/reader_real_corpus/run_acceptance.py run --out build/corpus \
  --consumer build/consumer/exreader-real-corpus-consumer \
  --font /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf
python3 tests/reader_real_corpus/run_acceptance.py aggregate \
  --summaries windows.json linux.json --out aggregate.json
```

`pin` downloads only, records final URL/bytes/SHA-256 and never runs the SDK.
`run` refuses a byte-count or SHA-256 mismatch, records every file and
operation, and keeps collecting after a bad document. The summary is
`accepted:true` only when all 18 real files pass on the platform.

## Boundary fixtures

`make_boundary.py` creates tiny non-public files (empty text, truncated EPUB
header, non-PDF) in a temporary directory. They are run separately by the CI
protocol job to prove clean rejection, and never enter `manifest.json` or any
real-document count.
