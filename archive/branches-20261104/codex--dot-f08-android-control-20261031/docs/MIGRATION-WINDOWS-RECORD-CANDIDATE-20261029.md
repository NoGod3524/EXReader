# Windows recovery record format candidate

`EXR_MIGRATION_WINDOWS_RECORD_CANDIDATE` is a separate default-off native
Windows tools-library build. It installs production record codec/I/O sources
independently of the original migration executables and frozen SDK. An external
consumer links only the installed archive and headers. No test source is part
of that archive.

`EXRWINRECOVERY1`, version 1, has a canonical bounded JSON representation with
a SHA256 seal, source/run identity and ordinal. Root, public parent, target and
predecessor each use the complete volume64 plus FileID128 representation:
48 lowercase hexadecimal characters and a NUL in each 49-byte in-memory field.
The predecessor link checks its complete native identity and recomputes its
canonical byte hash; matching only the leading 32 characters is insufficient.
The POSIX recovery and legacy v3 mirror formats remain unchanged and are
rejected by this codec, including unknown versions or noncanonical bytes.

The I/O functions use the existing qualified Windows private-root adapter to
create exclusively, flush, reread, and retain the actual record handle. They
recheck the actual root/parent and target handle identities and preserve any
partial or uncertain files on failure. They do not parse public paths from the
record or adopt unknown roots. SHA256 is an integrity check within the existing
owned-root assumptions, not authentication against a same-user rewrite.

Actions creates disposable records on real NTFS and checks an independently
compiled installed consumer, tail-byte identity changes, truncation, missing
NUL, canonical/seal/version failures, duplicate publication, actual handle
round trips and precursor binding. The eight original Windows capability
refusals also run against the same source. This is the persistent-format slice;
it grants no migration admission, directory-fsync equivalence, worker liveness
proof or completed Windows `lr_*` implementation. Host recovery remains refused.
