# Independent 3.41 to 3.42 selector and annotation proof (prepared)

This design is not an acceptance result. Run all builds, fixture creation,
tests, and archive authentication only in Actions. Do not modify the existing
3.41 suite or its future-version refusal.

1. Compile the actual Apple owner twice from the same candidate product source,
   with separate installed SDK trees from 5b7a34ee4f1ce38cf3bcd7cf0220575f4ecf7da9
   (3.41) and 8357eafa28423a7ab93ba08b823af80f01ad1505 (3.42); prove the
   corresponding SDK tree identity. Before production changes, run a clearly
   labelled test-only owner copy; after this proof passes, run the actual owner
   on a new source SHA. Use independent processes. Record executable, installed library, source, run and attempt
   identities. Do not identify a manufactured protocol fixture as an Android sender.
2. On 3.41 import the Actions-authored `AnchorSource.pdf`, select a real nonempty range using
   its public fixed-text snapshot, and submit a highlight with anchor version 3.
   Retain the original PDF, database/profile, request, revision wire, exported
   JSONL and hashes. Inspect the actual wire for v3, nonempty exact bytes and
   the actual producer parser tag before consuming it.
3. On 3.42 import the same PDF into a fresh owner profile and verify its actual
   format, byte length and hash. Preview the unmodified JSONL through the real
   `HostWave3AnnotationResolver` and require FOUND, no write and one new head;
   confirm using the returned fingerprint, then decode and verify original
   revision/wire and no outbox addition. Preview and confirm that same file a
   second time: exact duplicate, no new revision or outbox. Preserve both profiles,
   reports and all actual binaries in the original authenticated artifact.
4. For MISSING and AMBIGUOUS use separate, explicitly labelled adversarial
   fixtures produced inside Actions. Capture an actual nonempty 3.41 selector
   with fixed context; pass the unchanged selector to the 3.42 public resolver
   against, respectively, a document with the quote removed and one with two
   byte-identical quote-plus-context occurrences. Require the public status to
   be MISSING or AMBIGUOUS, never FOUND. Save originals, altered fixtures,
   exact selectors and reports. Do not claim either altered input is the original
   book; the production owner must independently reject its different fingerprint
   before any commit. If the fixed-page fixture cannot yield both cases, retain
   the failure rather than weakening the assertion.
5. Exercise explicit old/current tags and unknown, future, altered patch,
   duplicated prefix, empty and whitespace cases. The original 3.41 policy
   must still reject 3.42. Preserve original 19-case checks, original artifacts,
   unchanged controls and failures. Android 3.40 sending, iOS UI, physical device,
   signing and distribution remain separate unclaimed scopes.

`AnnotationInterop.swift`, `annotation_driver.py`, and the labelled fixture
generator are unexecuted drafts for steps 1–4. `ParserMatrix.swift` and its
driver are an unexecuted draft of step 5. The separate acceptance workflow and
original-ZIP authenticator are prepared for a later candidate branch, but no
production policy or authenticated Actions run exists yet. Do not
promote a production parser policy based only on these files or on a package pass.
