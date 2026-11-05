# Android 3.40 sender provenance (source-only preparation)

## Historical anchors

- Actual reading UI host: `047648865e509d5835b7d6e1389681e314d94e28`.
- Frozen public SDK: `9854061be331fe603a1822d9b2b36ee357154927`, version `3.40.0`.
- Historical host CMake requires `find_package(EXReader 3.40.0 EXACT CONFIG REQUIRED)`.
- Reading UI run `40131364703`, attempt 1, artifact `12575367601`.
- Owner/HTTPS historical run `40428878676`, attempt 1, artifact `12701815512`.
- Inventory pins all source/run/branch/ZIP identities; no latest-success lookup.

## Admission order

1. Obtain coordinator clearance against the other Android task before pushing.
2. Run the inventory only. It performs no build, fixture generation or emulator work.
3. If a complete historical package exists, authenticate and consume it unchanged.
4. Otherwise preserve both historical artifacts and add a separate clean sender.

## Clean sender design if required

Build the historical host and installed SDK unchanged. The workflow must first
prove protected production trees match the historical commit and the SDK trees
match the frozen SDK. Only dedicated instrumentation and a newly generated debug
fixture CA may differ. Record both the workflow source and historical host source;
do not identify a new producer run as the old run.

Use the historical reading runner's positive accessibility helpers for real TXT
progress, point bookmark, selection highlight and note edit, optionally EPUB.
Original import uses the public installed SDK; no database prefill. Do not use
its later negative graph injections, bulk pagination injection, synthetic record
apply calls or direct revision writes. Do not run that historical negative suite
against the sender store. Retain old checks separately and unchanged.

Capture original identity and the public SDK version/provider from the actual
app. Read persisted revisions/outbox only for observation. Save the complete
original bytes, original exact revision bytes and ancestor closure. Drive the
existing real sync dialog to enter per-run HTTPS credentials and explicitly sync.
Start with an empty TLS WebDAV fixture, and accept wire only from authenticated
app PUT requests. Compare server-received bytes with the persisted app revisions
and original bytes. No server.retain, prefilled remote revisions or fabricated
payloads. Retain authentication digests, not credentials, and scrub all uploads.

## Consumer contract

An immutable artifact must include a manifest with producer run/attempt/source,
historical host SHA, SDK SHA and actual runtime version, APK hashes, original
book identities, byte lengths and SHA-256 hashes, exact revision file hashes,
selector/parser provenance, parent relationships, UI report/screenshots and
authenticated HTTPS request/state evidence. The 3.42 receiver must retain its
existing policy: read unchanged bytes, distinguish historical parser acceptance
from navigation semantics, and never relabel 3.40 as 3.41 or weaken EXACT matching.

Physical-device evidence and six-platform completion are not established by an
API 34 x86_64 emulator sender. An inventory success is not sender acceptance.
