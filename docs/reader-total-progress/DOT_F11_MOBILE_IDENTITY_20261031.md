# F11 mobile identity candidate
Baseline: dfd44687ba5b7ea976ed59de74da875f9ba4253c.
Formal acceptance remains 95/108. Four new paths only; old packager, workflows,
SDK, owners, signing, licenses and Apple UI suites are unchanged.

The existing assemble gate compares source and SDK strings but does not bind
Apple producer platform/target/files to actual payload. A device arm64 payload
can therefore be labelled a simulator delivery without that packaging gate
rejecting it. Existing Android installed APK hashes and ELF machine checks
already exist and are not claimed missing.

This independent pre-deployment gate reads real Mach-O CPU/load-command platform
and ELF class/machine/type fields, compares actual producer file hashes, and
fails closed. It is not wired into old workflows and does not alter them.
Its new workflow makes the gate contract mandatory, with no continue-on-error.

One Actions run: Ubuntu compiles a minimal ELF shared object; macOS compiles
minimal simulator executable/dylib. Three positive and sixteen negative cases after independent review.
Negative cases are re-packed with fresh outer hashes; binary corruption cases
also refresh producer hashes, requiring actual binary-field rejection.
These are compiler-built synthetic contract fixtures, NOT EXReader deployment
or Android ABI/runtime compatibility proof. Old real packages are not downloaded
or parsed locally. Actual product-package admission remains a separately
authorized Actions integration step; no claim that this run validates old packages.

The original ten S20 selftest checks and original mobile contract assertions run
unchanged. Existing real deployment assertions and all old failures remain
unaltered, not replaced by these nineteen cases. No six-platform rebuild/UI run,
physical device, certificate, account or signing changes. Result pending.

Independent review revision: fixture SDK identity is explicitly 3.42.0.
Gate rejects actual filesystem inventory divergence and symlinks, and requires
executable MH_EXECUTE (2) versus SDK dylib MH_DYLIB (6).
Original 12 negative controls retained; 4 added: undeclared dylib, symlink,
wrong executable kind and wrong dylib kind. Total 3 positive + 16 negative.
The first two new controls mutate the unpacked directory after manifest sealing;
the other binary controls refresh producer hashes and outer records.
Generated ZIP hashes are fixture records only: this gate does not authenticate
the ZIP archive. Actual outer archive authentication is the upstream unpack
tool's responsibility. This gate checks its unpacked directory and manifest.
