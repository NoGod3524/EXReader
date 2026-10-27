# Reader catalog v1

`001_catalog.sql` creates a separate **product metadata** SQLite database. It
does not migrate the SDK's schema 7, store original book bytes or credentials,
or implement a sync client. SQLite 3.18+ is sufficient; JSON1 is not required.

Open one catalog beside one local SDK library. Before migration, require
`application_id=0`, `user_version=0` and an empty main schema. The SQL checks
those conditions again inside its transaction; run it only once. On any error,
explicitly roll back and keep the previous database. On later opens require
`application_id=1163416144` (`EXRP`) and a supported `user_version` (1 or 2);
reject other identities or versions. Enable `foreign_keys=ON` on **every** connection; use
`trusted_schema=OFF` where supported. The migration sets both for its connection.
Use the host owner queue and a bounded busy timeout. A future migration must be
explicit; do not rerun this file with `IF NOT EXISTS` added.

## Books and organization

`reader_books.book_key` is lowercase `format:sha256` of the exact original
bytes, for example `epub:<64 lowercase hex digits>`. The format names are
protocol values, not numeric SDK enums. Source identity and byte length are
immutable. A changed source is a different book. Titles are display strings;
the host supplies a stable, Unicode-normalized `sort_title` for binary ordering.

`reader_local_books` maps that global key to an ID in this device's one SDK
library and records `epub_chapter`, `reflow_global` or `fixed_page` storage.
This table never syncs. Its presence means a local import was recorded, not
that an SDK handle remains open. The host must reconcile interrupted import
and mapping commits through public SDK APIs; the two databases are not one
atomic transaction. Never delete a deduplicated existing SDK book to undo a
failed metadata write.

Shelf, tag, series and revision IDs are random UUIDs encoded as 32 lowercase
hex digits. Shelf depth includes the root and is limited to eight. Triggers
reject cycles and moves that make any descendant too deep. Tags are independent
of the shelf tree; books can belong to several shelves, tags and series.
`ordinal` is a nonnegative integer ordering key, with `book_key` breaking ties.
Hosts decide how to assign/rebalance order, rename duplicates and handle a
deleted shelf's children. Names do not act as identity.
Use explicit metadata updates, never `INSERT OR REPLACE` on catalog entities.

Page queries use bounded limits and keyset cursors, not `OFFSET`:

```sql
SELECT book_key,title,format FROM reader_books
WHERE deleted=0 AND (sort_title,book_key)>(?1,?2)
ORDER BY sort_title,book_key LIMIT ?3;

SELECT b.book_key,b.title,m.ordinal FROM reader_book_shelves m
JOIN reader_books b ON b.book_key=m.book_key
WHERE m.shelf_id=?1 AND b.deleted=0 AND (m.ordinal,m.book_key)>(?2,?3)
ORDER BY m.ordinal,m.book_key LIMIT ?4;
```

Use the same membership cursor for series. Tags have a reverse-lookup index;
display ordering of a filtered tag result remains a host query choice.
Thumbnail caching, virtualization and UI frame budgets are separate work.

## Offline sync records

`reader_revisions` retains immutable wire JSON and its SHA-256. The host must
validate the full JSON, size, hash, IDs, entity/operation agreement and causal
parent IDs **before** inserting it. JSON contains the versioned payload and
parent revision set. The database checks structural columns; it does not parse
JSON, verify hashes or resolve a revision graph. Replaying an existing ID is a
no-op only after comparing the complete stored bytes and columns; a reused ID
with different content is an error, never an `INSERT OR REPLACE`.

Save a local metadata change, its revision and `reader_outbox` row in one
catalog transaction. `revision_id` is unique in the queue. Deleting an outbox
row after verified upload does not erase its revision. `attempts` and
`last_error` are local retry state; errors must be redacted. No device time
decides which remote edit wins.

Delete is an immutable `operation='delete'` revision, exposed by
`reader_tombstones`. Never infer deletion from a missing remote listing. Keep
concurrent edits and tombstones; an old edit is not authorization to restore.
An explicit restore revision names the competing heads, including the
tombstone, as parents. `deleted` in the catalog tables is only the host's
current projection; SQL does not choose heads or prevent a host from making a
wrong conflict decision. Initial v1 does not prune revision history.

Progress and annotation JSON must preserve their location kind, original book
identity, selectors and parser/anchor version. Resolve through the appropriate
public SDK pager/document/fixed API before navigation; only `FOUND` authorizes
an exact jump. Retain unresolved or ambiguous remote data without guessing.
Apply SDK changes on its existing owner queue, never by writing private tables
or copying a live SQLite database. Import, network transport, conflict UI,
WebDAV object paths, TLS and platform secure credential storage remain host
work; none is supplied by this schema.

Cloud contract check (standard-library Python only):

```text
python tests/reader_catalog/check_schema.py --output build/reader-catalog/result.json
```

It exercises database constraints, failure rollback, retained delete/conflict
records and indexed keyset pages over thousands of metadata rows. It does not
measure UI rendering or test a WebDAV server.

The native product catalog upgrades version 1 to version 2 with
`002_originals.sql`. It preserves SDK mappings and records a separate relative
reference for product-owned content, with staged, ready and deleting states.
The host is responsible for verifying the content hash, durable file publication,
containment, and restart reconciliation. This is a storage prerequisite only:
there is no bounded TXT import or reopen host path yet. The revisions adapter
accepts both versions; other independently deployed v1-only adapters still need
an update before they can use a v2 catalog.
