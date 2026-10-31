# Linux C02 plus managed WebDAV joint candidate
Status: initial run preserved with a failed test adapter; sole targeted correction prepared, not yet run.
Owner: this conversation, exclusive branch codex/gpt-c02-webdav-joint-20261031.
Shared worktrees are untouched. Source/Git/docs use the authorized lap25002 native terminal, saved official instabox@0.8.52, and the existing VM. Desktop Commander is quota-blocked and unused.

Fixed product base: 8232e91cd7b9296dfcdd3096b96317eb3fa1008a
C02 product: d32603dc65bccfd65901239d21cb65cd10bca168
C02 audit: 5d9fc903ab015c50c3ce25b57a2680218bb0d419; final seal: 721188e553be4c8cffe9fbfb204f8a544a64bfe9
WebDAV product: 044824f91ddae2ea49994350d308d079a69048ab
SDK: 7271829a829bfa6aaa47b73077c493f71af27ad3
Cleanup core: dba079b550f9ec83054e6b7b0b7475f43bc1739f

The adjacent manifest is the exhaustive imported path/blob/mode list and new owned path list.
Only examples/linux/reader.c is a content merge: retain WebDAV worker startup/shutdown and replace only its open-error formatting line with C02's frozen line.
C02 reading.c acquires admission before any SDK/catalog open, and releases after all owned SDK objects.
The existing GTK main worker retains one linux_reader throughout its queue lifetime.
Managed recovery must drain/join, session must reach CLOSED and join/destroy, then the main worker may close the reader and release admission.
No new public API or SDK change is planned. Desktop CMake retains WebDAV's Linux content; C02's Windows entry change is excluded.
C02 Linux modules, frozen coordinators and the lm source closure are exact blobs, not a branch cherry-pick.
Unchanged original C02 testers may be materialized inside Actions only and are inventoried separately from the product source.
WebDAV's 30 original paths remain exact except the named reader.c merge.

Original contracts: C02 28+10+17 native groups, actual migration 36 plus 20 repair cases, original GTK lifecycle and raw decoders; WebDAV 25 transport cases, 21 GTK records, TLS/session counts and controls.
New cross groups: admission before recovery/network; both migration custody orders; all asynchronous and retained SDK owners; cancellation and ordered shutdown; process death/reopen and independent pending states; published target identity and cleanup-only retry.
Fixtures enroll explicitly with the installed C02 tool using the real non-root OS user's authority. No automatic enrollment or adoption.
C02 migration PENDING and WebDAV cleanup-pending are separate. Cleanup never grants C02 CLEAN.
Target dev/ino/size/hash remain stable; link counts follow the actual alias removal contract.
Installed GTK has no test hooks; fault controls remain separate test binaries.
Original ABI2 known-six reds and artifacts remain evidence, not rewritten results.

CI budget per round: admission10 + native60 + GTK120 + Windows30 + macOS30 + audit25 =275 runner-minutes.
One initial and at most one evidenced correction, total550. No automatic rerun/dispatch.
Each product run is bound to its full commit SHA. Later documentation seals use [skip ci].
No main/shared branch, PR, tag, release, external owner branch, UI/Apple/F08 expansion or formal-score change is authorized.

## Implementation and provenance review
The first candidate imports exactly the registered 88 product/dependency paths and records every runtime tester blob separately.
The complete import inventory and the only reader.c line merge are checked against immutable Git objects before any run.
The candidate is constructed without a local worktree, checkout or shared index mutation.
Eight new Python scripts and the single branch-specific workflow are in the approved owned paths.
No build, project syntax check, fixture, test or ZIP operation has run in the local computer or VM.

The original WebDAV build/assertion body is retained. The new recipe only stages frozen C02 plus search/navigation dependencies,
passes EXR_C02_PREFIX, and packages the already-built managed host with the explicit admission CLI.
CMake Unix Makefiles retain real link.txt files for the host, admission CLI and GTK harness.
The frozen GTK driver's path-only mapping points its unchanged static-input assertions at this actual combined host,
SDK and C02 installation. Its SDK source receipt names the approved fixed SDK; the mapping and both source hashes are retained.
The original UI scenario/assertion body is retained. Its fixture adapter explicitly creates/checks library admission before launch.
The original C02 testers are fixed to the product-source tester commit; independent raw decoders are fixed to the audit commit.
The native decoder's single feature-contract lookup uses the test-source commit rather than assuming tests were authored at H.
Product/receipt provenance checks still require the actual new H/run/attempt. No assertion is removed.
In the separate verifier, native semantics consume the producer's authenticated original fstat snapshot and original bytes;
they do not substitute new file identities created while unpacking.
All six joint groups retain partial evidence on failure. Independent controls cover SIGKILL, target identity, valid-prefix rollback,
cleanup-only request counts, premature lease release and failure to release after final joins.
This candidate does not transfer the old complete-c02 or full-product labels to H.

## Initial round and sole targeted correction
Initial source: ac6309d1e7dd00233a735ab3fa1b5084bf32cd49.
Run 41222658017 / attempt 1 is completed/failure. Admission, c02_linux, Legacy Windows and Legacy macOS succeeded.
GTK job 124600309439 stopped before product compilation at the adapter's unique generator-expression assertion.
The same generic text appears in the real build helper and the preserved mixed-prefix negative-control configure command.
The correction restricts the expression to the build helper's build-type argument. The control command and every original assertion remain.
Independent job 124601474160 refused with producer job gtk; no GTK or cross-group result is claimed for this round.
Ordinary C02 logs report native 28/207 + 10/81 + 17/130, and actual migration 36 plus repair20, all failed=0.
The correction changes only this new build adapter and this document. No frozen product/source/assertion change is introduced.
The full new H must rerun all corresponding jobs and authenticate its own original ZIPs; old green jobs are not spliced into acceptance.

Initial artifacts retained:
- joint-gtk-41222658017-1: id=13050572710, bytes=3597, sha256:0eefff31a7c0b9473738de7948ff7617219b480ba3944ea588903b7ba2b69e9a
- joint-Windows-41222658017-1: id=13050493426, bytes=2356353, sha256:2d23550e52dd46d2d9a9c97aca91da7dbd086696bae6851c4a1f26724c6c2c43
- joint-independent-41222658017-1: id=13050458726, bytes=309, sha256:48ec7f9dcc1c71d8559e6751cf2591869b04e9bdb9f2b7a5492a20c627090f08
- joint-c02-linux-41222658017-1: id=13050279165, bytes=29218427, sha256:862ba06d9f5f5522ab884adf803c1319539892a71e976550cec68155c45183a4
- joint-macOS-41222658017-1: id=13050153344, bytes=1339464, sha256:0ba93ebe8baf8c9f7e0dc7e33e8aaab134ab264a53d77310f998b23989f0eabb
- joint-admission-41222658017-1: id=13049993890, bytes=4422, sha256:131436ec598f0a908de64920b40caa155194148b2742b51559796bf78502f46b
