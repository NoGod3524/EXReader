# Windows product startup migration gate — 2026-10-29

The actual SDK 3.42 Windows product candidate now checks for existing
`.migration-recovery`, `.migration-pending.json` and `.migrate-lock` policy
before its ordinary `exr_library_open`. Present files, directories, reparse
entries and unknown inspection errors refuse startup. No target contents,
pending record or ACL is read, modified, deleted, adopted or automatically
recovered. The old standalone `.legacy-map.json` remains a valid normal-startup
case. SDK source, ABI and old test assertions are unchanged.

A normal interactive startup displays a native Chinese message explaining the
uncertain migration, asking the user to complete recovery before opening again,
and confirming that existing files have been retained. It supplies no unimplemented
automatic recovery button. Drive mode emits the exact gate/suffix/native code
for deterministic native acceptance and also exits before SDK open.

The check runs after product/profile locks and critical-section initialization,
so the established cleanup path releases only the new host's resources on
refusal. It precedes font and ordinary library opening. It does not claim to
close a race with an arbitrary standalone process starting after inspection;
cross-process shared-lock/real owner lifetime remains the subsequent product
integration. A permanent acknowledged recovery root will require a later actual
validated admission protocol; this initial gate deliberately does not infer it.

The Actions-only ten-case test launches the actual compiled EXReaderProduct,
using real SDK 3.40 schema6 fixture libraries. It checks all three marker names
as both files and directories, a pending marker with an absent target, clean
startup and legacy-sidecar-only startup reaching a real SDK schema7 upgrade,
and an actual non-drive visible Win32 dialog identified by process, window class,
visible rectangle and observed Chinese text. Refused libraries retain exact
FileID, bytes and existing namespace; only the normal empty product lock file
created by startup is permitted. Neither qualification nor full P0/F12 is closed
by these startup checks.
