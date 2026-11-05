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

The first Actions run 40938965113 at source
86d817824c41e72508a0a0d44d7e34fc6e562978 is retained as failure. SDK/current
product/old producer builds completed; the native driver reached its last
visible-message check after the first nine cases and observed the required
Chinese text and visible rectangle. It then failed its hardcoded GetDlgItem(1)
button lookup. The corrected driver waits for and enumerates the actual single
visible enabled Button belonging to that same observed dialog; all original
text, data-preservation and positive-startup assertions remain. Per-case partial
results are now saved, with passed=false until the full ten-case round completes.
The product gate source is unchanged in this driver-only repair.

The public-module composition starts at
`bd28d4946f17a184dd3cd47a584cf49fce34e973`. Only the three product gate
files and the original ten-case driver are carried from
`2fff53ff6734ec2b495c841e6669aef562e170d7`; Actions compares their exact
bytes and keeps the public source SDK unchanged. The standalone OPDSHash
owner is built and installed separately, then supplied through the explicit
catalog prefix. The earlier ten-case success is historical evidence; this
composition requires its own actual-product result.

This composition still contains the older migration CLI without the POSIX
recovery candidate or Windows qualification sources. Recovery integration
must first import and verify those separately; their presence cannot be
inferred from the public-module base.
