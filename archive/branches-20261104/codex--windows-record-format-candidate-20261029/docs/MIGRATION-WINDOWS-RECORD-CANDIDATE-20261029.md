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

Verified producer source is
`2743f32a4eccd5823657da19cb4f77f2411424af`, Actions run `40950523121`,
job `123717117262`: installed consumer 27/27, original Windows recovery refusal
8/8, success. Original ZIP artifact `12931496665` is 131650 bytes, SHA256
`fe9906afd12bf2644cf584f627b525cd17d9e2f007615b2297a5d423f67611ec`.
The actual NTFS record was 523 bytes. No independent audit or catalog credit
is supplied by the producer result.

Retained failed predecessors are `40949525149` at
`613fbca5ef101880fbdd16faee4b3a0fcf321e6d` (installed production library
completed; consumer sizeof control hit MSVC C4127 under /W4 /WX), and
`40949972717` at `6e661223550308bd84a0fbd9b9c660bc0c779d8e` (consumer built;
the mixed-separator fixture path was refused by native canonical admission).
The repairs changed only the check dispatch helper and workflow path conversion.
All production record files and all 27 control expressions are unchanged from
the first candidate. The accepted run keeps /W4 /WX and native path validation.
