# Native product catalog adapter

This C11 product module opens the existing `001_catalog.sql` in an independent
EXRP/schema-1 database. It does not change the SDK or open the SDK's private
tables. Windows and GTK hosts will call it on their existing worker after
verifying source bytes through public SDK APIs.

The API covers startup/open, atomic book identity plus local mapping, removing a
local mapping and bounded title/keyset pages. An attach never replaces existing
metadata, revisions, tombstones or outbox records. Historical duplicate sources
select the smallest SDK ID and that ID's actual location kind. Hosts supply NFC
`sort_title`; the adapter validates UTF-8 and binds every metadata value.

Calls belong to the creating worker. Page callbacks borrow each row until they
return; they must copy data for the UI and cannot reenter the catalog. Pages are
limited to 200 and use an indexed `(sort_title,book_key)` continuation. First
and continuation queries are separate, avoiding an optional-cursor OR scan.

The standalone project fetches public SQLite 3.54.0 with the same archive hash
and compile limits used by the frozen SDK. This is an explicit product
dependency; it uses no private SDK headers or vendor targets. Desktop host
integration must verify the final SQLite provider/linkage and consume the
installed public SDK. The module has no SDK-source hashing or import code yet.

The generated migration literal must match the original SQL byte-for-byte. The
cloud executable checks migration identity, foreign-file retention, transaction
rollback, conflicting identities/modes, duplicate selection, retained local
metadata/history, owner-thread/reentry refusal, busy-writer retry, shelf triggers
and 2,500 metadata rows over keyset pages. It inspects the query actually
executed by the adapter and requires its continuation to use the title index.

All compilation and execution run in `reader-catalog-native.yml` on Linux,
Windows and macOS. These adapter checks grant no desktop UI, import recovery,
WebDAV or UI performance acceptance. Host wiring and the SDK-original mapping
checks follow on this branch.
