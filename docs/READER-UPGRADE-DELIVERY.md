# Upgrade, import and delivery status

There is not yet a validated, installable final native product for all six
targets. The [build instructions](../README.md#构建) produce the SDK and tools;
they are not a mobile app installer. Obtain a platform package only when its
publisher provides installation, signing and upgrade instructions for that
package. Keep the old installation and a restorable backup until the new
product has been verified. Do not copy an open SQLite database: close the app
and use its supported backup procedure, including its originals and product
catalog. A product catalog and SDK library are separate stores.

## Older libraries

The native product catalog adapter upgrades EXRP versions 1 and 2 to version 3
when opened. That operation alone does not establish that an old app library,
all reading records, or a downgrade works on a particular device. The old
IndexedDB/backup migration is a separate command-line tool, not a native app
upgrade button. Its historical [instructions](WP12-LEGACY-MIGRATION.md) explain how to
export from the old application's own origin, inspect the pack, run a dry run,
migrate and verify. Close the target app first and retain the source export,
target backup, report and `<library>.legacy-map.json` together. On SDK 3.41 the
tool accepts a new target or an existing SDK schema 6 or 7 target. Schema 6 is
snapshotted before the SDK upgrades the stage to schema 7; `dump` and `verify`
refuse schema 6 until migration, so they cannot silently upgrade the original.
Close and checkpoint the old library first; a WAL, SHM or rollback journal
sidecar causes a refusal. Other target versions are refused. Review the report before using partial migration: unresolved
annotations remain in the ledger, audio originals are not imported, and files
above 128 MiB are rejected. Real user libraries, macOS and a real Tauri window
were not covered by the recorded tool acceptance; see the
[independent review](WP12-MIGRATION-REVIEW.md).

For a source build, install the SDK with its library component, configure and
install `extras/migration` against that prefix as described in the migration
instructions. The migration prefix contains the executable in `bin` and the
exporter, backup converter, instructions and project license in
`share/exreader-legacy-migration`. It is not a self-contained SDK distribution;
retain the SDK's dependency license and notice materials as well.

## Import and sync

Use the file import offered by the specific native host and keep your original
files until the imported books have been opened and checked. Supported formats,
size limits, file permissions and import entry points depend on the host and
build; the SDK build alone does not establish their product availability.

For a host with WebDAV support, configure your own HTTPS WebDAV collection and
account using that host's account controls. Verify the server certificate and
use credentials appropriate for that service. The protocol stores immutable
originals and revisions in its own namespace; it does not synchronize a live
SQLite database. A pending operation, conflict, or incomplete scan is not proof
that another device has received all data. Keep independent backups, resolve
reported conflicts in the host, and verify the books and reading records on the
other device. The [protocol and tested scope](READER-WEBDAV-SYNC.md) describe
the transport; individual platform and device acceptance remains separate.

## Packaging and licensing evidence

The [distribution inventory](READER-DISTRIBUTION-INVENTORY.md) records desktop
SDK and optional-module materials at source `93d2ad0db2d75af50eddc0843a4da9c7090a15aa`,
run [40095313750](https://github.com/NoGod3524/EXReader/actions/runs/40095313750),
attempt 1. Material inventory passed, but release readiness did not: 60 distinct
installed files contained build-machine paths. That historical result is not
proof of the current native host bundles, mobile packages, signing or final
dependency licenses. Final delivery still needs same-source installed artifact
inventories and license/notice review, path remediation, platform upgrade and
old-library checks, and user instructions checked against the actual packages.
F12 remains pending until those results are available.

The earlier candidate's push run [40627111572](https://github.com/NoGod3524/EXReader/actions/runs/40627111572),
attempt 1, at `622c9edb13fd3f1b9466be1cbd9d9f6d5c737093` failed on both Linux
and Windows and failed the combined gate. Installed payload verification passed
on both platforms. On Linux, 27 of 65 named scenarios passed; `dump` rejected
the SDK 3.41-created schema 7 target with `target-schema`, and the browser
chain failed after publication when checking reopened originals. Preserve this
run and its uploaded failure evidence. The follow-up run
[40627983295](https://github.com/NoGod3524/EXReader/actions/runs/40627983295)
failed its new Windows old-library check because the Python test held an open
SQLite connection; the original named scenarios passed on both platforms.

The repaired candidate `d86cae5411cd8f5806db7eb4ab38bb60b4d04bfc`, run
[40628744097](https://github.com/NoGod3524/EXReader/actions/runs/40628744097)
attempt 1, passed all three jobs. Linux and Windows each passed the original
65 scenarios/135 checks, 31 review checks and 17 browser-chain checks; the
combined gate and its 29 rejection/positive checks passed. Both platforms also
created a schema 6 library using the original SDK and migrator from
`c2d23c29a3b2096c2236fdb414dcd1e66d3243b4` and verified refusal, dry-run and
failed-publication preservation, successful upgrade of its book and annotation,
verification and retry. This synthetic fixture is not a real user library or a
six-platform host upgrade acceptance.

The same run verified the five installed migrator materials and checked the
two installed documents whose examples previously exposed a user-specific path
on Linux and Windows. The SDK and ABI source tree was guarded against the
`f34a4f27` base. The historical G09 inventory has not been rerun against this
candidate: its package-only scope guard does not admit the integrated branch.
Upstream pkg-config prefixes and archive-member paths still require remediation
and a new same-source distribution audit; the documented historical 60-file
finding is not a count of the current candidate.
